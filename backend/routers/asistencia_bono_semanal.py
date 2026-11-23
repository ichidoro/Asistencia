"""
Router - Asistencia: bonos semanales (Fill Rate, pedido de la persona dueña, 23-11-2026). Desde la grilla, en la vista
«Fill Rate», se marca o se quita el «no cumple» de un día de una persona. Dirección bajo /api/asistencia (asistencia.py
incluye este router).
"""
import json
from datetime import date
from typing import List, Optional

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
    # Nota de crédito del día (23-11-2026): si la hubo, su razón decide: culpa del chofer = no cumple; si no, cumple
    tiene_nc: bool = False
    razon_nc_id: Optional[int] = None
    # Los peonetas que iban con el chofer ese día (1 o 2, cambian de chofer): reciben la misma marca (23-11-2026)
    peonetas_ids: List[int] = Field(default_factory=list, max_length=2)


@router.get("/bono-semanal/acompanantes/")
async def acompanantes_del_dia(
    chofer_id: int,
    fecha: str,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """Los peonetas que la libreta tiene con el chofer ese día, para proponerlos al marcar el Fill Rate."""
    try:
        fecha = date.fromisoformat(fecha[:10]).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="La fecha no es válida.")
    return {"peonetas_ids": await AsistenciaRepository(db).get_acompanantes_180h(chofer_id, fecha)}


@router.post("/bono-semanal/no-cumple/")
async def marcar_no_cumple(
    req: MarcaNoCumple,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """Marca un día «no cumple» (no_cumple = true: pierde la semana del bono) o «cumple» (false)."""
    try:
        fecha = date.fromisoformat(req.fecha[:10]).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="La fecha no es válida.")
    repo = ConfiguracionRepository(db)
    bono = next((b for b in await repo.get_all_bonos() if b["id"] == req.bono_id), None)
    if not bono or not bono.get("activo") or bono.get("periodicidad") != "semanal":
        raise HTTPException(status_code=400, detail="El bono no existe o no es un bono semanal en uso.")
    personas = [req.empleado_id] + [p for p in dict.fromkeys(req.peonetas_ids) if p != req.empleado_id]
    turnos = set(bono.get("turnos_ids") or [])   # vacío: todos los horarios
    for pid in personas:
        if await AsistenciaRepository(db).check_fecha_cerrada(fecha, pid):
            raise HTTPException(status_code=403, detail="Ese día está en un período cerrado: no se puede cambiar.")
        asignaciones = await TurnoRepository(db).get_asignaciones_entre(pid, fecha, fecha)
        if not asignaciones or (turnos and not any(a["turno_id"] in turnos for a in asignaciones)):
            raise HTTPException(status_code=400, detail="Ese día " + ("la persona" if pid == req.empleado_id else "un peoneta elegido")
                                + " no tiene un horario con este bono.")
    comentario = (req.comentario or "").strip() or None
    razon = None
    no_cumple = req.no_cumple
    if req.tiene_nc:
        razon = next((r for r in await repo.get_razones_nota_credito() if r["id"] == req.razon_nc_id and r["activa"]), None)
        if not razon:
            raise HTTPException(status_code=400, detail="Elija la razón de la nota de crédito.")
        no_cumple = bool(razon["culpa_chofer"])
    # «Cumple» también queda marcado, para que la celda lo diga (23-11-2026); un día sin marca cuenta como cumplido.
    # La misma marca va a los peonetas que iban con el chofer ese día
    for pid in personas:
        await repo.marcar_dia_no_cumple(req.bono_id, pid, fecha, comentario,
                                        current_user.username, "no_cumple" if no_cumple else "cumple", razon)
    try:
        from backend.repositories.seguridad import SeguridadRepository
        await SeguridadRepository(db).log_auditoria(
            current_user.user_id, current_user.username, "BONO_SEMANAL_NO_CUMPLE" if no_cumple else "BONO_SEMANAL_CUMPLE",
            "MARCACIONES", json.dumps({"bono_id": req.bono_id, "bono": bono["nombre"], "empleado_id": req.empleado_id,
                                       "fecha": fecha, "comentario": comentario, "peonetas_ids": personas[1:],
                                       "nota_credito": ({"razon": razon["nombre"], "culpa_chofer": bool(razon["culpa_chofer"])}
                                                        if razon else None)}, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"[BonoSemanal] Auditoría no registrada: {e}")
    return {"ok": True, "fecha": fecha, "no_cumple": no_cumple, "personas": personas}
