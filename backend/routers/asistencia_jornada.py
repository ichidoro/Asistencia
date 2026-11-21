"""
Router - Asistencia: validar una jornada especial y aprobar horas extra (una o varias). Separado de
routers/asistencia.py en la etapa 6 de la auditoría, con el mismo código; las direcciones siguen bajo /api/asistencia
(asistencia.py incluye este router).
"""
from fastapi import Depends, Body, HTTPException
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from loguru import logger
from backend.services.asistencia_service import AsistenciaService
from backend.services import quantum_matrix_engine as _motor
from backend.repositories.empleado import EmpleadoRepository
from backend.repositories.seguridad import SeguridadRepository
from backend.core.security import SecurityContext, RequirePermission
from backend.schemas.asistencia import AprobarHERequest
from backend.routers.asistencia_comun import get_asistencia_service
from fastapi import APIRouter

router = APIRouter()


def _cuando_cambio(updated_at) -> str:
    """«hoy a las 12:14» o «el 27-10 a las 18:05» para el aviso de cambio simultáneo. updated_at se guarda en UTC."""
    try:
        momento = updated_at if isinstance(updated_at, datetime) else datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    local = momento.astimezone(_motor._CHILE_TZ).replace(tzinfo=None)
    hora = local.strftime("%H:%M")
    return f"hoy a las {hora}" if local.date() == _motor._get_now_local().date() else f"el {local.strftime('%d-%m')} a las {hora}"


@router.post("/jornada/validar/")
async def validar_jornada_endpoint(
    empleado_id: int = Body(...),
    fecha: str = Body(...),
    accion: str = Body("APROBAR"),
    observaciones: Optional[str] = Body(None),
    minutos_autorizados: Optional[float] = Body(None),
    last_updated_at: Optional[str] = Body(None, description="Fecha/Hora de la versión que el usuario está viendo"),
    parte: str = Body("JORNADA", description="JORNADA (jornada especial o +2) o LLAMADO (llamado de un día no laborable)"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Gestiona una jornada especial (APROBAR, APROBAR_COMO_HE, RECHAZAR o REVERTIR) con RLS. Con parte=LLAMADO decide el
    llamado de emergencia de un día no laborable, aparte de la jornada especial (05-11-2026). Toda decisión, también
    REVERTIR, queda en la auditoría.
    """
    parte = (parte or "JORNADA").upper()
    if parte not in ("JORNADA", "LLAMADO"):
        raise HTTPException(status_code=400, detail="Parte no válida.")
    if accion not in ("APROBAR", "APROBAR_COMO_HE", "RECHAZAR", "REVERTIR"):
        raise HTTPException(status_code=400, detail="Acción no válida.")
    # RLS: Verificar pertenencia
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    current_user.verificar_acceso_area(emp.area, "jornadas de este empleado")
    
    # Blindaje de Cierre
    if await service.repository.check_fecha_cerrada(fecha, empleado_id):
        raise HTTPException(status_code=403, detail="El periodo de esta fecha se encuentra cerrado y no admite modificaciones.")

    try:
        # Control de Concurrencia Optimista
        if last_updated_at:
            actual = await service.repository.get_asistencia(empleado_id, fecha)
            if actual and actual.get('updated_at') and actual.get('updated_at') != last_updated_at:
                cuando = _cuando_cambio(actual.get('updated_at'))
                raise HTTPException(
                    status_code=409,
                    detail=f"Otra persona cambió este día{' ' + cuando if cuando else ''}. Su cambio no se guardó. Cierre y vuelva a abrir el día para ver lo último."
                )

        resultado = await service.validar_jornada(
            empleado_id=empleado_id,
            fecha=fecha,
            accion=accion,
            observaciones=observaciones,
            minutos_autorizados=minutos_autorizados,
            validador_id=current_user.user_id,
            parte=parte,
        )
        if isinstance(resultado, dict) and 'error' in resultado:
            raise HTTPException(status_code=400, detail=resultado['error'])
        try:
            from backend.repositories.seguridad import SeguridadRepository
            import json as _json
            await SeguridadRepository(service.repository.db).log_auditoria(
                current_user.user_id, current_user.username,
                "REVERTIR_JORNADA" if accion == "REVERTIR" else "VALIDAR_JORNADA", "MARCACIONES",
                _json.dumps({"empleado_id": empleado_id, "empleado": f"{emp.apellido_paterno or ''} {emp.apellido_materno or ''}, {emp.nombre or ''}".strip(),
                             "fecha": fecha, "parte": parte, "accion": accion,
                             "minutos": (resultado or {}).get("minutos_extra_autorizados")}, ensure_ascii=False))
        except Exception as audit_err:
            logger.warning(f"[Jornada] Auditoría de la validación no registrada: {audit_err}")
        if parte == "LLAMADO":
            mensaje = {"APROBAR": "Llamado validado como jornada EXTRA", "APROBAR_COMO_HE": "Llamado validado como horas extra",
                       "RECHAZAR": "Llamado rechazado", "REVERTIR": "Llamado devuelto a por validar"}[accion]
        elif accion == "APROBAR_COMO_HE":
            mensaje = "Jornada especial pasada a horas extra: quedan por aprobar con las demás horas extra del día"
        elif accion == "APROBAR":
            mensaje = "Jornada especial validada como jornada extra"
        elif accion == "REVERTIR":
            mensaje = "Jornada revertida exitosamente"
        else:
            mensaje = "Jornada rechazada exitosamente"
        return {
            "success": True,
            "mensaje": mensaje,
            "asistencia": resultado
        }
    except HTTPException:
        # El aviso (400) y el conflicto de concurrencia (409) llegan tal cual a la pantalla, no como «error interno»
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/aprobar-he/")
async def aprobar_horas_extra(
    request: AprobarHERequest,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.horas_extras"))
):
    """
    Aprueba horas extras para un empleado y día (delegando al método batch).
    """
    # RLS: Verificar pertenencia de área
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(request.empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    current_user.verificar_acceso_area(emp.area, "HE de este empleado")

    try:
        # Convertir a formato de lote de un solo elemento
        items = [{
            "empleado_id": request.empleado_id,
            "fecha": request.fecha,
            "estado": "APROBADO" if request.horas > 0 else "RECHAZADO",
            "minutos_autorizados": request.horas * 60.0
        }]
        return await service.aprobar_horas_extras_batch(items)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/aprobar-he-batch/")
async def aprobar_horas_extra_batch(
    items: List[Dict[str, Any]] = Body(...),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.horas_extras"))
):
    """
    Aprueba o rechaza múltiples registros de horas extra a la vez (delegando al servicio).
    Cada item debe tener {empleado_id, fecha, estado, minutos_autorizados}.
    """
    try:
        # RLS: Validar pertenencia de área para cada elemento del lote antes de procesar
        emp_repo = EmpleadoRepository(service.repository.db)
        for item in items:
            emp_id = item.get('empleado_id')
            emp = await emp_repo.get_by_id(emp_id)
            if emp:
                current_user.verificar_acceso_area(emp.area, f"HE del empleado ID {emp_id}")

        return await service.aprobar_horas_extras_batch(items)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
