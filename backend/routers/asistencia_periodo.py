"""
Router - Asistencia: período de RR.HH. (resumen de una persona y global, último cierre, historial de cierres y
cerrar el período). Separado de routers/asistencia.py en la etapa 6 de la auditoría, con el mismo código; las
direcciones siguen bajo /api/asistencia (asistencia.py incluye este router).
"""
from fastapi import Query, Body, HTTPException, Depends
from typing import Optional
from backend.services.asistencia_service import AsistenciaService
from backend.repositories.empleado import EmpleadoRepository
from backend.core.security import SecurityContext, RequirePermission
from backend.routers.asistencia_comun import get_asistencia_service
from fastapi import APIRouter

router = APIRouter()


@router.get("/periodo-rrhh/resumen/")
async def get_periodo_rrhh_resumen(
    empleado_id: int = Query(...),
    fecha_inicio: str = Query(...),
    fecha_fin: str = Query(...),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene el resumen de HE, Deuda y Saldo Meta para un empleado específico (Uso individual).
    """
    # RLS: Verificar que el empleado pertenece al área del usuario
    if not current_user.alcance_global:
        emp_repo = EmpleadoRepository(service.repository.db)
        emp = await emp_repo.get_by_id(empleado_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Empleado no encontrado")
        current_user.verificar_acceso_area(emp.area, "el resumen de este empleado")
    return await service.get_period_summary_rrhh(empleado_id, fecha_inicio, fecha_fin)

@router.get("/periodo-rrhh/resumen-global/")
async def get_periodo_rrhh_resumen_global(
    fecha_inicio: str = Query(...),
    fecha_fin: str = Query(...),
    area: Optional[str] = Query(None),
    turno_id: Optional[int] = Query(None),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene el resumen consolidado de todo el personal filtrado para el modal de cierre.
    """
    # RLS: Filtrar por áreas permitidas si no es global
    areas_permitidas = current_user.get_areas_filter()
    if area and areas_permitidas is not None and area not in areas_permitidas:
        raise HTTPException(status_code=403, detail="No tiene permisos para el área solicitada")
    
    # RLS: Si no es global y no especificó área, usar la primera área permitida
    area_final = area
    if not area_final and areas_permitidas:
        area_final = areas_permitidas[0] if len(areas_permitidas) == 1 else None
    return await service.get_resumen_cierre_global(fecha_inicio, fecha_fin, area_final, turno_id)

@router.get("/periodo-rrhh/ultimo-cierre/")
async def get_ultimo_cierre_rrhh(
    tipo: str = Query("RRHH"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene la información del último cierre registrado para sugerir el siguiente periodo.
    """
    # RLS: Filtrar por áreas permitidas del usuario
    cierre = await service.repository.get_ultimo_cierre_periodo(tipo)
    if cierre and not current_user.alcance_global:
        areas_permitidas = current_user.areas or []
        if cierre.get('area') and cierre['area'] not in areas_permitidas:
            return None
    return cierre

@router.get("/periodo-rrhh/historial/")
async def get_historial_cierres_rrhh(
    limit: int = Query(12),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene el historial de cierres de periodo.
    """
    # RLS: Filtrar por áreas permitidas del usuario
    cierres = await service.repository.get_cierres_historial(limit)
    if not current_user.alcance_global:
        areas_permitidas = current_user.areas or []
        cierres = [c for c in cierres if not c.get('area') or c['area'] in areas_permitidas]
    return cierres

@router.post("/periodo-rrhh/cerrar/")
async def cerrar_periodo_rrhh(
    fecha_inicio: str = Body(...),
    fecha_fin: str = Body(...),
    area: Optional[str] = Body(None),
    turno_id: Optional[int] = Body(None),
    comentario: Optional[str] = Body(None), # El frontend envía 'comentario'
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Registra el cierre y ejecuta el procesamiento masivo de saldos/bolsa.
    Permite segmentación por Área y Horario (turno_id).
    """
    # RLS: Verificar que el área enviada está en las áreas del current_user
    if area and not current_user.alcance_global:
        areas_permitidas = current_user.areas or []
        if area not in areas_permitidas:
            raise HTTPException(status_code=403, detail=f"No tiene permisos para cerrar el área '{area}'.")
    resultado = await service.ejecutar_cierre_periodo(
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        area=area,
        turno_id=turno_id,
        usuario_id=current_user.user_id,
        username=current_user.username,
        comentarios=comentario
    )
    return resultado
