"""
API de la pestaña «Reglas de marcaciones» (Configuración).

Etapa 1: ver y editar las reglas. El motor de cálculo todavía no las lee:
todas nacen apagadas y el botón «Correr esta regla» llega en la etapa
siguiente (regla por regla, solo tramo abierto y áreas abiertas).
"""
import json
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.core.database import Database, get_db
from backend.core.security import RequirePermission, SecurityContext
from backend.repositories.reglas_marcas import ReglasMarcasRepository
from backend.repositories.seguridad import SeguridadRepository
from backend.services.reglas_marcas_def import grupo_de_secuencia

router = APIRouter(prefix="/configuracion/reglas-marcas", tags=["Reglas de marcaciones"])

PERMISO_EDITAR = "configuracion.reglas_marcaciones"


async def _repo(db: Database = Depends(get_db)) -> ReglasMarcasRepository:
    return ReglasMarcasRepository(db)


@router.get("/", response_model=Dict[str, Any])
async def listar_reglas(
    tipo: str = "CICLO_INTELIGENTE",
    repo: ReglasMarcasRepository = Depends(_repo),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver")),
):
    """Reglas del tipo de horario, con el conteo real de jornadas por secuencia."""
    desde = await repo.inicio_tramo_abierto()
    reglas = await repo.listar(tipo)
    conteos = await repo.conteos(tipo, desde)
    por_sec = conteos["por_secuencia"]
    for r in reglas:
        c = por_sec.get(r["secuencia"], {"dias": 0, "dias_abiertos": 0})
        r["dias"] = c["dias"]
        r["dias_abiertos"] = c["dias_abiertos"]
        r["grupo"] = grupo_de_secuencia(r["secuencia"])
    sin_regla = [
        {"secuencia": sec, "dias": c["dias"], "dias_abiertos": c["dias_abiertos"],
         "grupo": grupo_de_secuencia(sec)}
        for sec, c in sorted(por_sec.items(), key=lambda kv: -kv[1]["dias"])
        if sec not in {r["secuencia"] for r in reglas}
    ]
    return {
        "tipo": tipo,
        "tipos": await repo.tipos_horario(),
        "reglas": reglas,
        "secuencias_sin_regla": sin_regla,
        "total_jornadas": conteos["total"],
        "total_jornadas_tramo_abierto": conteos["total_abiertos"],
        "tramo_abierto_desde": desde,
        "rebote_segundos": await repo.rebote_segundos(),
        "motor_conectado": False,  # etapa 1: solo configuración
    }


@router.get("/{regla_id}/dias/", response_model=Dict[str, Any])
async def dias_de_la_regla(
    regla_id: int,
    repo: ReglasMarcasRepository = Depends(_repo),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver")),
):
    """Los días del tramo abierto que hoy caen en esta secuencia (solo lectura)."""
    regla = await repo.obtener(regla_id)
    if not regla:
        raise HTTPException(status_code=404, detail="La regla no existe.")
    desde = await repo.inicio_tramo_abierto()
    dias = await repo.dias_de_secuencia(regla["tipo_horario"], regla["secuencia"], desde)
    return {"secuencia": regla["secuencia"], "desde": desde, "dias": dias}


@router.put("/rebote/", response_model=Dict[str, Any])
async def guardar_rebote(
    payload: Dict[str, Any] = Body(...),
    repo: ReglasMarcasRepository = Depends(_repo),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission(PERMISO_EDITAR)),
):
    try:
        segundos = int(payload.get("segundos"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="El rebote debe ser un número de segundos.")
    if not (0 <= segundos <= 1800):
        raise HTTPException(status_code=400, detail="El rebote debe estar entre 0 y 1800 segundos.")
    anterior = await repo.rebote_segundos()
    await repo.guardar_rebote(segundos)
    await SeguridadRepository(db).log_auditoria(
        current_user.user_id, current_user.username, "UPDATE", "REGLAS_MARCAS",
        json.dumps({"ajuste": "rebote_segundos", "antes": anterior, "despues": segundos})
    )
    return {"message": "Rebote guardado.", "segundos": segundos}


@router.put("/{regla_id}/", response_model=Dict[str, Any])
async def actualizar_regla(
    regla_id: int,
    payload: Dict[str, Any] = Body(...),
    repo: ReglasMarcasRepository = Depends(_repo),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission(PERMISO_EDITAR)),
):
    cambios = {k: payload.get(k) for k in
               ("lectura", "colacion", "accion", "opciones_revision", "nota", "activa")
               if k in payload}
    resultado = await repo.actualizar(regla_id, cambios, current_user.username)
    if resultado.get("error"):
        raise HTTPException(status_code=400, detail=resultado["error"])
    antes, despues = resultado["antes"], resultado["despues"]
    detalle = {
        "regla_id": regla_id,
        "secuencia": antes["secuencia"],
        "antes": {k: antes[k] for k in ("lectura", "colacion", "accion", "opciones_revision")},
        "despues": {k: despues[k] for k in ("lectura", "colacion", "accion", "opciones_revision")},
    }
    await SeguridadRepository(db).log_auditoria(
        current_user.user_id, current_user.username, "UPDATE", "REGLAS_MARCAS",
        json.dumps(detalle, ensure_ascii=False)
    )
    return {"message": "Regla guardada.", "regla": despues}
