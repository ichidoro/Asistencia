from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from backend.core.security import SecurityContext, RequirePermission, RequireAnyPermission
from backend.services.turno_service import TurnoService
from backend.repositories.turno import TurnoRepository
from backend.services.asistencia_service import AsistenciaService
from backend.repositories.asistencia import AsistenciaRepository
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
    res = await service.assign_turno_bulk(bulk)
    
    # Auto-Healing: Si es retroactivo, procesar asistencia de fondo
    hoy = date.today().strftime("%Y-%m-%d")
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
    new_id = await service.create_turno(turno)
    return {"id": new_id, "message": "Turno creado exitosamente"}

@router.get("/", response_model=List[TurnoResponse])
async def get_turnos(
    area: Optional[str] = None,
    service: TurnoService = Depends(get_turno_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    """Listar todos los turnos disponibles, opcionalmente filtrados por área"""
    return await service.get_all_turnos(area=area)

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
    return await service.get_stats_por_area()

@router.post("/asignar/")
async def asignar_turno(
    asignacion: AsignacionCreate,
    background_tasks: BackgroundTasks,
    service: TurnoService = Depends(get_turno_service),
    asis_service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.horarios"))
):
    """Asignar un turno a un empleado (Cierra vigencia anterior automáticamente)"""
    await service.assign_turno(asignacion)
    
    # [AUTO-HEALING] Si la asignación es hacia el pasado o hoy, sanar asistencia huérfana
    hoy = date.today().strftime("%Y-%m-%d")
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
    updated = await service.update_turno(turno_id, turno)
    if not updated:
        raise HTTPException(status_code=404, detail="Turno no encontrado")
    return {"id": turno_id, "message": "Turno actualizado correctamente"}

@router.patch("/asignacion/update-date/")
async def update_assignment_date(
    payload: AsignacionUpdateDate,
    service: TurnoService = Depends(get_turno_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.horarios"))
):
    """
    Actualiza la fecha de inicio de la asignación de un empleado.
    Realiza limpieza de asistencia basura previa a la nueva fecha.
    """
    await service.update_assignment_date(payload.empleado_id, payload.nueva_fecha)
    return {"message": "Fecha de asignación actualizada y basura eliminada"}
