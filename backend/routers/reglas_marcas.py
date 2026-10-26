"""
API de la pestaña «Reglas de marcaciones» (Configuración).

El motor lee SOLO las reglas encendidas (activa = 1). Todas nacen apagadas y
se encienden una por una con «Correr esta regla», que recalcula en segundo
plano únicamente los días del tramo abierto (jornadas terminadas, sin cierres
de área o turno) cuya secuencia es la de la regla, y entrega el antes y el
después de cada día que cambió. «Apagar esta regla» deshace de la misma forma.
"""
import json
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.core.database import Database, get_db
from backend.core.security import RequirePermission, SecurityContext
from backend.repositories.reglas_marcas import AJUSTES_EDITABLES, ReglasMarcasRepository
from backend.repositories.seguridad import SeguridadRepository
from backend.services.reglas_marcas_def import pausas_de, grupo_de_secuencia, validar_regla
from backend.services.reglas_marcas_corridas import (
    JOBS, _hay_corrida_en_curso, ensayar_regla, iniciar_corrida, job_publico,
)
from backend.services.reglas_marcas_runtime import cargar as cargar_reglas_runtime

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
        r["eleccion_colacion"] = r.get("eleccion_colacion") or "PARECIDA"
        r["pausas"] = {lect: pausas_de(r["secuencia"], lect) for lect in ("RELOJ", "EXTREMOS")}
    sin_regla = [
        {"secuencia": sec, "dias": c["dias"], "dias_abiertos": c["dias_abiertos"],
         "grupo": grupo_de_secuencia(sec)}
        for sec, c in sorted(por_sec.items(), key=lambda kv: -kv[1]["dias"])
        if sec not in {r["secuencia"] for r in reglas}
    ]
    corrida = _hay_corrida_en_curso()
    return {
        "tipo": tipo,
        "tipos": await repo.tipos_horario(),
        "reglas": reglas,
        "secuencias_sin_regla": sin_regla,
        "total_jornadas": conteos["total"],
        "total_jornadas_tramo_abierto": conteos["total_abiertos"],
        "tramo_abierto_desde": desde,
        "rebote_segundos": await repo.rebote_segundos(),
        "ajustes": await repo.ajustes_reglas(),
        "ajustes_descripcion": {k: {"texto": v[0], "min": v[1], "max": v[2]} for k, v in AJUSTES_EDITABLES.items()},
        "horarios": await repo.horarios(tipo),
        "cortes_colacion": await repo.cortes_colacion(tipo),
        "motor_conectado": True,
        "corrida_en_curso": job_publico(corrida) if corrida else None,
    }


@router.get("/por-revisar/", response_model=Dict[str, Any])
async def dias_por_revisar(
    area: str = "",
    repo: ReglasMarcasRepository = Depends(_repo),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver")),
):
    """Días del tramo abierto que una regla dejó en revisión y nadie ha resuelto."""
    dias = await repo.dias_por_revisar(area=area or None)
    return {"dias": dias, "total": len(dias)}


@router.get("/evaluar/", response_model=Dict[str, Any])
async def evaluar_dia(
    empleado_id: int,
    fecha: str,
    repo: ReglasMarcasRepository = Depends(_repo),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver")),
):
    """Qué dice la regla de marcaciones sobre un día (para el cuadro Ingreso Manual)."""
    return await repo.evaluar_dia(empleado_id, fecha)


@router.post("/confirmar/", response_model=Dict[str, Any])
async def confirmar_dia(
    payload: Dict[str, Any] = Body(...),
    repo: ReglasMarcasRepository = Depends(_repo),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar")),
):
    """Confirma que un día en revisión está bien. Vale mientras sus marcas no cambien."""
    try:
        empleado_id = int(payload.get("empleado_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Falta el empleado.")
    fecha = str(payload.get("fecha") or "")[:10]
    motivo = str(payload.get("motivo") or "").strip()
    if len(motivo) < 5:
        raise HTTPException(status_code=400, detail="Escriba un motivo (al menos 5 letras).")
    res = await repo.confirmar_dia(empleado_id, fecha, current_user.user_id,
                                   current_user.username, motivo)
    if res.get("error"):
        raise HTTPException(status_code=400, detail=res["error"])
    await SeguridadRepository(db).log_auditoria(
        current_user.user_id, current_user.username, "CONFIRMAR_DIA", "REGLAS_MARCAS",
        json.dumps({"empleado_id": empleado_id, "fecha": fecha,
                    "secuencia": res["secuencia"], "motivo": motivo}, ensure_ascii=False))
    return {"message": "Día confirmado: sale de «Días por revisar» mientras sus marcas no cambien."}


@router.post("/", response_model=Dict[str, Any], status_code=201)
async def crear_regla(
    payload: Dict[str, Any] = Body(...),
    repo: ReglasMarcasRepository = Depends(_repo),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission(PERMISO_EDITAR)),
):
    """Crea, desde la bandeja, una regla APAGADA para una secuencia sin regla."""
    secuencia = str(payload.get("secuencia") or "").strip().upper()
    tipo = str(payload.get("tipo") or "CICLO_INTELIGENTE").strip()
    res = await repo.crear_regla(tipo, secuencia, current_user.username)
    if res.get("error"):
        raise HTTPException(status_code=400, detail=res["error"])
    await SeguridadRepository(db).log_auditoria(
        current_user.user_id, current_user.username, "CREAR_REGLA", "REGLAS_MARCAS",
        json.dumps({"tipo_horario": tipo, "secuencia": secuencia}, ensure_ascii=False))
    return {"message": "Regla creada, apagada y lista para configurar.", "regla": res["regla"]}


@router.get("/corridas/{job_id}/", response_model=Dict[str, Any])
async def estado_corrida(
    job_id: str,
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver")),
):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Esa corrida no existe (o el servidor se reinició).")
    return job_publico(job)


async def _lanzar(regla_id: int, encender: bool, repo: ReglasMarcasRepository,
                  current_user: SecurityContext) -> Dict[str, Any]:
    regla = await repo.obtener(regla_id)
    if not regla:
        raise HTTPException(status_code=404, detail="La regla no existe.")
    if not regla.get("secuencia"):
        raise HTTPException(status_code=400, detail="La regla no tiene secuencia.")
    job = iniciar_corrida(regla, encender, current_user.user_id, current_user.username)
    if job.get("error"):
        raise HTTPException(status_code=409, detail=job["error"])
    return job_publico(job)


@router.post("/{regla_id}/correr/", response_model=Dict[str, Any], status_code=202)
async def correr_regla(
    regla_id: int,
    repo: ReglasMarcasRepository = Depends(_repo),
    current_user: SecurityContext = Depends(RequirePermission(PERMISO_EDITAR)),
):
    """Enciende la regla y recalcula SOLO sus días del tramo abierto, en segundo plano."""
    return await _lanzar(regla_id, True, repo, current_user)


@router.post("/{regla_id}/apagar/", response_model=Dict[str, Any], status_code=202)
async def apagar_regla(
    regla_id: int,
    repo: ReglasMarcasRepository = Depends(_repo),
    current_user: SecurityContext = Depends(RequirePermission(PERMISO_EDITAR)),
):
    """Apaga la regla y recalcula de vuelta sus días del tramo abierto, en segundo plano."""
    return await _lanzar(regla_id, False, repo, current_user)


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


@router.get("/{regla_id}/dias-ejemplo/", response_model=Dict[str, Any])
async def dias_ejemplo_de_la_regla(
    regla_id: int,
    repo: ReglasMarcasRepository = Depends(_repo),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver")),
):
    """Los días de ejemplo del asistente: los más recientes del tramo abierto con esta
    secuencia (marcas del reloj, sin manuales, sin cierres). Solo lectura."""
    regla = await repo.obtener(regla_id)
    if not regla:
        raise HTTPException(status_code=404, detail="La regla no existe.")
    from datetime import datetime as _dt
    desde = await repo.inicio_tramo_abierto()
    dias = await repo.dias_ejemplo(regla["tipo_horario"], regla["secuencia"], desde,
                                   _dt.now().strftime("%Y-%m-%d"), limite=4)
    total = int(dias[0]["total"]) if dias else 0
    return {"secuencia": regla["secuencia"], "desde": desde, "dias": dias, "total": total}


@router.post("/{regla_id}/ensayo/", response_model=Dict[str, Any])
async def ensayar_la_regla(
    regla_id: int,
    payload: Dict[str, Any] = Body(...),
    repo: ReglasMarcasRepository = Depends(_repo),
    current_user: SecurityContext = Depends(RequirePermission(PERMISO_EDITAR)),
):
    """«Cómo quedaría»: calcula los días de ejemplo con la regla del editor (esté
    guardada o no) y devuelve el antes → después. NO guarda nada en la base."""
    regla = await repo.obtener(regla_id)
    if not regla:
        raise HTTPException(status_code=404, detail="La regla no existe.")
    propuesta = {
        "secuencia": regla["secuencia"],
        "lectura": str(payload.get("lectura") or ""),
        "colacion": str(payload.get("colacion") or ""),
        "accion": str(payload.get("accion") or ""),
        "opciones_revision": payload.get("opciones_revision") or [],
        "avisa_fuera_de_ciclo": 1 if payload.get("avisa_fuera_de_ciclo") in (1, True, "1", "true") else 0,
        "eleccion_colacion": str(payload.get("eleccion_colacion") or "PARECIDA"),
    }
    motivo = validar_regla(propuesta)
    if motivo:
        raise HTTPException(status_code=400, detail=motivo)
    res = await ensayar_regla(regla, propuesta)
    if res.get("error"):
        raise HTTPException(status_code=409, detail=res["error"])
    return res


@router.put("/ajustes/", response_model=Dict[str, Any])
async def guardar_ajuste(
    payload: Dict[str, Any] = Body(...),
    repo: ReglasMarcasRepository = Depends(_repo),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission(PERMISO_EDITAR)),
):
    """Guarda uno de los ajustes de la pestaña (rebote, marcas repetidas, colación de
    referencia, minutos para «no calza con ningún ciclo»). Queda en la auditoría."""
    clave = str(payload.get("clave") or "")
    if clave not in AJUSTES_EDITABLES:
        raise HTTPException(status_code=400, detail="Ese ajuste no se puede cambiar desde esta pestaña.")
    texto, minimo, maximo = AJUSTES_EDITABLES[clave]
    try:
        valor = float(payload.get("valor"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="El valor debe ser un número.")
    if not (minimo <= valor <= maximo):
        raise HTTPException(status_code=400, detail=f"El valor debe estar entre {minimo} y {maximo}.")
    anterior = (await repo.ajustes_reglas()).get(clave)
    await repo.guardar_ajuste(clave, valor)
    await cargar_reglas_runtime(db)
    await SeguridadRepository(db).log_auditoria(
        current_user.user_id, current_user.username, "UPDATE", "REGLAS_MARCAS",
        json.dumps({"ajuste": clave, "antes": anterior, "despues": valor}, ensure_ascii=False)
    )
    return {"message": "Ajuste guardado.", "clave": clave, "valor": valor}


@router.put("/{regla_id}/", response_model=Dict[str, Any])
async def actualizar_regla(
    regla_id: int,
    payload: Dict[str, Any] = Body(...),
    repo: ReglasMarcasRepository = Depends(_repo),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission(PERMISO_EDITAR)),
):
    cambios = {k: payload.get(k) for k in
               ("lectura", "colacion", "accion", "opciones_revision", "avisa_fuera_de_ciclo", "eleccion_colacion",
                "nota", "activa")
               if k in payload}
    resultado = await repo.actualizar(regla_id, cambios, current_user.username)
    if resultado.get("error"):
        raise HTTPException(status_code=400, detail=resultado["error"])
    antes, despues = resultado["antes"], resultado["despues"]
    campos = ("lectura", "colacion", "accion", "opciones_revision", "avisa_fuera_de_ciclo", "eleccion_colacion")
    detalle = {
        "regla_id": regla_id,
        "secuencia": antes["secuencia"],
        "antes": {k: antes.get(k) for k in campos},
        "despues": {k: despues.get(k) for k in campos},
    }
    await SeguridadRepository(db).log_auditoria(
        current_user.user_id, current_user.username, "UPDATE", "REGLAS_MARCAS",
        json.dumps(detalle, ensure_ascii=False)
    )
    await cargar_reglas_runtime(db)
    return {"message": "Regla guardada.", "regla": despues}
