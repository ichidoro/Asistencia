from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from backend.core.security import SecurityContext, RequirePermission, RequireAnyPermission
from backend.services.turno_service import TurnoService
from backend.repositories.turno import TurnoRepository
from backend.services.asistencia_service import AsistenciaService
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.empleado import EmpleadoRepository
from backend.core.database import get_db, Database
from backend.schemas.turno import TurnoCreate, TurnoResponse, AsignacionCreate, AsignacionBulk, AsignacionUpdateDate
from datetime import date

router = APIRouter(
    prefix="/turnos",
    tags=["Turnos"]
)

async def get_turno_service(db: Database = Depends(get_db)) -> TurnoService:
    repository = TurnoRepository(db)
    return TurnoService(repository)

async def get_asistencia_service(db: Database = Depends(get_db)) -> AsistenciaService:
    repository = AsistenciaRepository(db)
    return AsistenciaService(repository)

@router.get("/asignaciones/matrix/")
async def get_assignments_matrix(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(...),
    area: Optional[str] = None,
    service: TurnoService = Depends(get_turno_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    """
    Obtiene la matriz de asignaciones de turnos para un periodo.
    Permite identificar qué horario tiene asignado cada empleado día a día.
    """
    if not current_user.alcance_global:
        if area:
            if area not in (current_user.areas or []):
                raise HTTPException(status_code=403, detail="No tiene permisos para el área solicitada")
        else:
            results = await service.get_assignment_matrix(month, year, area)
            areas_permitidas = set(current_user.areas or [])
            return [r for r in results if r.get('area') in areas_permitidas]

    return await service.get_assignment_matrix(month, year, area)

@router.post("/bulk-assign/")
async def bulk_assign_turnos(
    bulk: AsignacionBulk,
    background_tasks: BackgroundTasks,
    service: TurnoService = Depends(get_turno_service),
    asis_service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.horarios"))
):
    """Asignación masiva de turnos a múltiples empleados"""
    emp_repo = EmpleadoRepository(service.repository.db)
    hoy = date.today().strftime("%Y-%m-%d")
    fecha_fin_check = hoy if bulk.fecha_inicio < hoy else bulk.fecha_inicio

    for emp_id in bulk.empleados_ids:
        emp = await emp_repo.get_by_id(emp_id)
        if not emp:
            raise HTTPException(status_code=404, detail=f"Empleado con ID {emp_id} no encontrado")
        
        # RLS Check
        if not current_user.alcance_global and emp.area not in (current_user.areas or []):
            raise HTTPException(status_code=403, detail=f"No tiene permisos para el empleado {emp.nombre_completo}")
        
        # Cierre Check
        if await asis_service.repository.check_rango_cerrado(bulk.fecha_inicio, fecha_fin_check, emp_id):
            raise HTTPException(
                status_code=403,
                detail=f"La fecha de asignación ({bulk.fecha_inicio}) está en un período cerrado para el empleado {emp.nombre_completo}."
            )

    res = await service.assign_turno_bulk(bulk)
    
    # Auto-Healing: Si es retroactivo, procesar asistencia de fondo
    if bulk.fecha_inicio <= hoy:
        for eid in bulk.empleados_ids:
            background_tasks.add_task(
                asis_service.reprocesar_periodo_empleado,
                empleado_id=eid,
                fecha_inicio=bulk.fecha_inicio,
                fecha_fin=hoy,
                force=True
            )
    return res

@router.post("/", response_model=Dict[str, Any])
async def create_turno(
    turno: TurnoCreate, 
    service: TurnoService = Depends(get_turno_service),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.horarios", "configuracion.wizard"]))
):
    """Crear un nuevo Turno con sus días configurados"""
    if not current_user.alcance_global:
        if not turno.areas:
            raise HTTPException(status_code=403, detail="Un usuario zonal debe asignar al menos una área a la que tenga permisos.")
        for a in turno.areas:
            if a not in (current_user.areas or []):
                raise HTTPException(status_code=403, detail=f"No tiene permisos para asignar el área '{a}'")

    new_id = await service.create_turno(turno)
    return {"id": new_id, "message": "Turno creado exitosamente"}

@router.get("/", response_model=List[TurnoResponse])
async def get_turnos(
    area: Optional[str] = None,
    activo: Optional[bool] = None,
    service: TurnoService = Depends(get_turno_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    """Listar todos los turnos disponibles, opcionalmente filtrados por área y estado activo"""
    if not current_user.alcance_global:
        if area:
            if area not in (current_user.areas or []):
                raise HTTPException(status_code=403, detail="No tiene permisos para el área solicitada")
        else:
            return await service.get_all_turnos(area=None, areas_permitidas=current_user.areas or [], activo=activo)

    return await service.get_all_turnos(area=area, activo=activo)

@router.get("/stats/por-area")
async def get_turnos_stats_por_area(
    service: TurnoService = Depends(get_turno_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    """
    Devuelve un diccionario { "Nombre Area": cantidad_turnos }
    para ayudar al frontend a saber si un área tiene o no turnos antes de
    sincronizar o mostrar la interfaz.
    """
    stats = await service.get_stats_por_area()
    if not current_user.alcance_global:
        areas_permitidas = current_user.areas or []
        stats["areas"] = {k: v for k, v in stats.get("areas", {}).items() if k in areas_permitidas}
    return stats

@router.post("/asignar/")
async def asignar_turno(
    asignacion: AsignacionCreate,
    background_tasks: BackgroundTasks,
    service: TurnoService = Depends(get_turno_service),
    asis_service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.horarios"))
):
    """Asignar un turno a un empleado (Cierra vigencia anterior automáticamente)"""
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(asignacion.empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Empleado con ID {asignacion.empleado_id} no encontrado")
        
    # RLS Check
    if not current_user.alcance_global and emp.area not in (current_user.areas or []):
        raise HTTPException(status_code=403, detail="No tiene permisos para este empleado")
        
    # Cierre Check
    hoy = date.today().strftime("%Y-%m-%d")
    fecha_fin_check = hoy if asignacion.fecha_inicio < hoy else asignacion.fecha_inicio
    if await asis_service.repository.check_rango_cerrado(asignacion.fecha_inicio, fecha_fin_check, asignacion.empleado_id):
        raise HTTPException(
            status_code=403,
            detail=f"La fecha de asignación ({asignacion.fecha_inicio}) está en un período cerrado para el empleado {emp.nombre_completo}."
        )

    await service.assign_turno(asignacion)
    
    # [AUTO-HEALING] Si la asignación es hacia el pasado o hoy, sanar asistencia huérfana
    if asignacion.fecha_inicio <= hoy:
        background_tasks.add_task(
            asis_service.reprocesar_periodo_empleado,
            empleado_id=asignacion.empleado_id,
            fecha_inicio=asignacion.fecha_inicio,
            fecha_fin=hoy,
            force=True
        )
        
    return {"message": "Turno asignado correctamente y recalculo de fondo iniciado"}

@router.delete("/{turno_id}/", status_code=204)
async def delete_turno(
    turno_id: int,
    service: TurnoService = Depends(get_turno_service),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.horarios", "configuracion.wizard"]))
):
    """Eliminar un turno"""
    db = service.repository.db
    areas_res = await db.fetch_all(
        "SELECT a.nombre FROM turno_areas ta JOIN areas a ON ta.area_id = a.id WHERE ta.turno_id = ?",
        (turno_id,)
    )
    turno_areas = [r['nombre'] for r in areas_res]
    
    # RLS Check
    if not current_user.alcance_global:
        if not turno_areas:
            raise HTTPException(status_code=403, detail="No tiene permisos para eliminar turnos globales")
        for a in turno_areas:
            if a not in (current_user.areas or []):
                raise HTTPException(status_code=403, detail=f"No tiene permisos sobre el área '{a}' asociada a este turno")

    deleted = await service.delete_turno(turno_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Turno no encontrado")
    return

@router.put("/{turno_id}/", response_model=Dict[str, Any])
async def update_turno(
    turno_id: int,
    turno: TurnoCreate,
    service: TurnoService = Depends(get_turno_service),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.horarios", "configuracion.wizard"]))
):
    """Actualizar configuración de un turno"""
    db = service.repository.db
    areas_res = await db.fetch_all(
        "SELECT a.nombre FROM turno_areas ta JOIN areas a ON ta.area_id = a.id WHERE ta.turno_id = ?",
        (turno_id,)
    )
    existing_areas = [r['nombre'] for r in areas_res]
    
    if not current_user.alcance_global:
        if not existing_areas:
            raise HTTPException(status_code=403, detail="No tiene permisos para modificar turnos globales")
        for a in existing_areas:
            if a not in (current_user.areas or []):
                raise HTTPException(status_code=403, detail=f"No tiene permisos sobre el área '{a}' asociada a este turno")
                
        # Check that the new areas they are trying to assign are within their scope
        if not turno.areas:
            raise HTTPException(status_code=403, detail="Un usuario zonal debe asignar al menos una área a la que tenga permisos.")
        for a in turno.areas:
            if a not in (current_user.areas or []):
                raise HTTPException(status_code=403, detail=f"No tiene permisos para asignar el área '{a}'")

    updated = await service.update_turno(turno_id, turno)
    if not updated:
        raise HTTPException(status_code=404, detail="Turno no encontrado")
    return {"id": turno_id, "message": "Turno actualizado correctamente"}

@router.patch("/asignacion/update-date/")
async def update_assignment_date(
    payload: AsignacionUpdateDate,
    service: TurnoService = Depends(get_turno_service),
    asis_service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.horarios"))
):
    """
    Actualiza la fecha de inicio de la asignación de un empleado.
    Realiza limpieza de asistencia basura previa a la nueva fecha.
    """
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(payload.empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Empleado con ID {payload.empleado_id} no encontrado")

    # RLS Check
    if not current_user.alcance_global and emp.area not in (current_user.areas or []):
        raise HTTPException(status_code=403, detail="No tiene permisos para este empleado")

    # Cierre Check
    if await asis_service.repository.check_rango_cerrado(payload.nueva_fecha, payload.nueva_fecha, payload.empleado_id):
        raise HTTPException(
            status_code=403,
            detail=f"La nueva fecha de asignación ({payload.nueva_fecha}) está en un período cerrado para el empleado {emp.nombre_completo}."
        )

    await service.update_assignment_date(payload.empleado_id, payload.nueva_fecha)
    return {"message": "Fecha de asignación actualizada y basura eliminada"}
