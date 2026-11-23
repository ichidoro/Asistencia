"""
Router - Asistencia: bonos semanales (Fill Rate, pedido de la persona dueña, 23-11-2026). Desde la grilla, en la vista
«Fill Rate», se marca o se quita el «no cumple» de un día de una persona. Dirección bajo /api/asistencia (asistencia.py
incluye este router).
"""
import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from backend.core.database import Database, get_db
from backend.core.security import RequirePermission, SecurityContext
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.configuracion import ConfiguracionRepository
from backend.repositories.turno import TurnoRepository

router = APIRouter()


class MarcaNoCumple(BaseModel):
    bono_id: int
    empleado_id: int
    fecha: str = Field(..., description="AAAA-MM-DD")
    no_cumple: bool = True
    comentario: Optional[str] = Field(None, max_length=300)


@router.post("/bono-semanal/no-cumple/")
async def marcar_no_cumple(
    req: MarcaNoCumple,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """Marca (no_cumple = true) o quita (false) el «no cumple» de un día. Un día marcado hace perder la semana del bono."""
    try:
        fecha = date.fromisoformat(req.fecha[:10]).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="La fecha no es válida.")
    repo = ConfiguracionRepository(db)
    bono = next((b for b in await repo.get_all_bonos() if b["id"] == req.bono_id), None)
    if not bono or not bono.get("activo") or bono.get("periodicidad") != "semanal":
        raise HTTPException(status_code=400, detail="El bono no existe o no es un bono semanal en uso.")
    if await AsistenciaRepository(db).check_fecha_cerrada(fecha, req.empleado_id):
        raise HTTPException(status_code=403, detail="Ese día está en un período cerrado: no se puede cambiar.")
    asignaciones = await TurnoRepository(db).get_asignaciones_entre(req.empleado_id, fecha, fecha)
    turnos = set(bono.get("turnos_ids") or [])   # vacío: todos los horarios
    if not asignaciones or (turnos and not any(a["turno_id"] in turnos for a in asignaciones)):
        raise HTTPException(status_code=400, detail="Ese día la persona no tiene un horario con este bono.")
    comentario = (req.comentario or "").strip() or None
    if req.no_cumple:
        await repo.marcar_dia_no_cumple(req.bono_id, req.empleado_id, fecha, comentario, current_user.username)
    else:
        await repo.quitar_dia_no_cumple(req.bono_id, req.empleado_id, fecha)
    try:
        from backend.repositories.seguridad import SeguridadRepository
        await SeguridadRepository(db).log_auditoria(
            current_user.user_id, current_user.username, "BONO_SEMANAL_NO_CUMPLE" if req.no_cumple else "BONO_SEMANAL_CUMPLE",
            "MARCACIONES", json.dumps({"bono_id": req.bono_id, "bono": bono["nombre"], "empleado_id": req.empleado_id,
                                       "fecha": fecha, "comentario": comentario}, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"[BonoSemanal] Auditoría no registrada: {e}")
    return {"ok": True, "fecha": fecha, "no_cumple": req.no_cumple}
