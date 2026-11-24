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


class NotaCredito(BaseModel):
    numero: str = Field(..., min_length=1, max_length=40)
    razon_id: int
    # Solo si la razón descuenta el valor de los productos (por ejemplo, extravío de la carga)
    monto: Optional[float] = Field(None, ge=0)


class MarcaNoCumple(BaseModel):
    bono_id: int
    empleado_id: int
    fecha: str = Field(..., description="AAAA-MM-DD")
    no_cumple: bool = True
    comentario: Optional[str] = Field(None, max_length=300)
    # Notas de crédito del día (23-11-2026), cada una con su número y su razón: si alguna es culpa del chofer, no
    # cumple; si no, cumple. tiene_nc/razon_nc_id son de la ventana anterior (una sola nota sin número): se rechazan
    notas: List[NotaCredito] = Field(default_factory=list, max_length=20)
    tiene_nc: bool = False
    razon_nc_id: Optional[int] = None
    # Los peonetas que iban con el chofer ese día (1 o 2, cambian de chofer): reciben la misma marca (23-11-2026)
    peonetas_ids: List[int] = Field(default_factory=list, max_length=2)
    # Eliminar la marca del día (por si hubo un error): el día vuelve a «sin marcar», que cuenta como cumplido
    eliminar: bool = False


async def _validar_notas(repo, notas: List[NotaCredito], personas: List[int], fecha: str,
                         chofer_id: int) -> List[dict]:
    """Revisa las notas del día y las devuelve con su razón. No se acepta una nota de crédito en un día justificado
    (por ejemplo, descanso operativo: la persona no trabajó; dueño, 23-11-2026), ni sin número, ni repetida, ni sin monto
    si la razón descuenta el valor de los productos."""
    if not notas:
        return []
    for pid in personas:
        j = await repo.justificacion_del_dia(pid, fecha)
        if j:
            quien = "La persona" if pid == chofer_id else "Un peoneta elegido"
            raise HTTPException(status_code=400, detail=f"{quien} tiene «{j['nombre']}» ese día: no trabajó, así que no puede "
                                                        "tener nota de crédito.")
    razones = {r["id"]: r for r in await repo.get_razones_nota_credito()}
    out, vistos = [], set()
    for n in notas:
        numero = n.numero.strip()
        if not numero:
            raise HTTPException(status_code=400, detail="Cada nota de crédito necesita su número.")
        if numero.upper() in vistos:
            raise HTTPException(status_code=400, detail=f"La nota de crédito {numero} está repetida.")
        vistos.add(numero.upper())
        r = razones.get(n.razon_id)
        if not r or not r.get("activa"):
            raise HTTPException(status_code=400, detail=f"Elija la razón de la nota de crédito {numero}.")
        monto = float(n.monto or 0)
        if r.get("descuenta_productos") and monto <= 0:
            raise HTTPException(status_code=400, detail=f"La nota de crédito {numero} descuenta los productos: indique su valor.")
        out.append({"numero": numero, "razon": r, "monto": monto if r.get("descuenta_productos") else 0})
    return out


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
    if req.eliminar:
        borradas = await repo.quitar_marca_dia(req.bono_id, req.empleado_id, fecha)
        try:
            from backend.repositories.seguridad import SeguridadRepository
            await SeguridadRepository(db).log_auditoria(
                current_user.user_id, current_user.username, "BONO_SEMANAL_ELIMINAR_MARCA", "MARCACIONES",
                json.dumps({"bono_id": req.bono_id, "bono": bono["nombre"], "empleado_id": req.empleado_id, "fecha": fecha,
                            "borradas": borradas}, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[BonoSemanal] Auditoría no registrada: {e}")
        return {"ok": True, "fecha": fecha, "eliminada": bool(borradas), "personas": [req.empleado_id]}
    comentario = (req.comentario or "").strip() or None
    if req.tiene_nc and not req.notas:
        raise HTTPException(status_code=400, detail="Recargue la página: ahora cada nota de crédito pide su número.")
    notas = await _validar_notas(repo, req.notas, personas, fecha, req.empleado_id)
    no_cumple = any(n["razon"]["culpa_chofer"] for n in notas) if notas else req.no_cumple
    # La razón que se ve en la celda: la que hace perder el día, o la primera
    razon = next((n["razon"] for n in notas if n["razon"]["culpa_chofer"]), notas[0]["razon"] if notas else None)
    # «Cumple» también queda marcado, para que la celda lo diga (23-11-2026); un día sin marca cuenta como cumplido.
    # La misma marca va a los peonetas que iban con el chofer ese día; las notas quedan en la fila del chofer
    for pid in personas:
        await repo.marcar_dia_no_cumple(req.bono_id, pid, fecha, comentario,
                                        current_user.username, "no_cumple" if no_cumple else "cumple", razon)
    await repo.guardar_notas_credito(req.bono_id, req.empleado_id, fecha, notas, current_user.username, personas[1:])
    try:
        from backend.repositories.seguridad import SeguridadRepository
        await SeguridadRepository(db).log_auditoria(
            current_user.user_id, current_user.username, "BONO_SEMANAL_NO_CUMPLE" if no_cumple else "BONO_SEMANAL_CUMPLE",
            "MARCACIONES", json.dumps({"bono_id": req.bono_id, "bono": bono["nombre"], "empleado_id": req.empleado_id,
                                       "fecha": fecha, "comentario": comentario, "peonetas_ids": personas[1:],
                                       "notas_credito": [{"numero": n["numero"], "razon": n["razon"]["nombre"],
                                                          "culpa_chofer": bool(n["razon"]["culpa_chofer"]),
                                                          "monto": n["monto"]} for n in notas]}, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"[BonoSemanal] Auditoría no registrada: {e}")
    return {"ok": True, "fecha": fecha, "no_cumple": no_cumple, "personas": personas}
