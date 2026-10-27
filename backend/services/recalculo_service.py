# -*- coding: utf-8 -*-
"""Recálculo del tramo abierto cuando cambia una configuración que usa el cálculo (orden del dueño, 26-10-2026).

Antes, guardar un turno o un ajuste no recalculaba nada: el cambio regía solo para los días que se volvían a calcular
(marcas nuevas, «Reprocesar» en Reportes o el próximo arranque). Ahora, al guardar:
  · un turno → se recalcula el tramo abierto de las personas de ese turno;
  · un ajuste que lee el motor → se recalcula el tramo abierto de todas las personas.
El recálculo corre en segundo plano (la pantalla no espera), uno a la vez, y sin forzar: respeta los días de un tramo ya
cerrado (por RRHH o por área) y los días validados o rechazados a mano, igual que la sincronización.
"""
import asyncio
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, Optional, Set, Tuple

from loguru import logger

# Ajustes de Configuración → Sistema que el motor lee al calcular un día (cambiar uno cambia los cálculos)
CLAVES_AJUSTE_QUE_RECALCULAN = (
    "asistencia_minimo_horas_extra_minutos",
    "asistencia_max_extras_ordinarias_dia_habil",
    "asistencia_emergencia_gap_horas",
    "asistencia_emergencia_jornada_limite_horas",
)

_candado = asyncio.Lock()
_tareas: Set[asyncio.Task] = set()


def calcular_rango(hoy: date, ultimo_cierre_fin: Optional[str], dia_cierre: Optional[int]) -> Tuple[date, date]:
    """Rango del período activo: desde el día siguiente al último período de RRHH cerrado hasta hoy. Sin cierres, desde
    el día siguiente al día de cierre configurado del mes anterior. Función pura."""
    if ultimo_cierre_fin:
        return datetime.strptime(str(ultimo_cierre_fin)[:10], "%Y-%m-%d").date() + timedelta(days=1), hoy
    inicio = hoy.replace(day=1) - timedelta(days=1)          # último día del mes anterior
    if dia_cierre:
        try:
            inicio = inicio.replace(day=int(dia_cierre) + 1)
        except ValueError:                                   # el mes anterior no tiene ese día: queda su último día
            pass
    return inicio, hoy


async def rango_periodo_activo(db) -> Tuple[date, date, Optional[str]]:
    """(inicio, fin, fecha_fin del último cierre) del período activo, leído de la base."""
    ultimo = await db.fetch_one("SELECT fecha_fin FROM periodos_rrhh WHERE estado='cerrado' ORDER BY fecha_fin DESC LIMIT 1")
    ultimo_fin = (ultimo or {}).get("fecha_fin") if ultimo else None
    dia = None
    try:
        r = await db.fetch_one("SELECT valor FROM ajustes WHERE clave = 'dia_cierre_rrhh'")
        dia = int(r["valor"]) if r and r.get("valor") not in (None, "") else None
    except Exception:
        dia = None
    inicio, fin = calcular_rango(datetime.now().date(), ultimo_fin, dia)
    return inicio, fin, (str(ultimo_fin)[:10] if ultimo_fin else None)


async def empleados_del_turno(db, turno_id: int, inicio: date, fin: date) -> Set[int]:
    """Personas con ese turno en el período: por su asignación o porque algún día del período se calculó con él."""
    ini, fi = inicio.strftime("%Y-%m-%d"), fin.strftime("%Y-%m-%d")
    filas = await db.fetch_all(
        "SELECT DISTINCT empleado_id FROM asignacion_turnos WHERE turno_id = ? AND fecha_inicio <= ? "
        "AND (fecha_fin IS NULL OR fecha_fin = '' OR fecha_fin >= ?)", (turno_id, fi, ini))
    ids = {int(r["empleado_id"]) for r in filas}
    filas = await db.fetch_all(
        "SELECT DISTINCT empleado_id FROM asistencias WHERE turno_asignado_id = ? AND fecha BETWEEN ? AND ?",
        (turno_id, ini, fi))
    ids |= {int(r["empleado_id"]) for r in filas}
    return ids


async def _recalcular(empleado_ids: Optional[Set[int]], motivo: str) -> None:
    from backend.core.database import db
    from backend.repositories.asistencia import AsistenciaRepository
    from backend.services.asistencia_service import AsistenciaService
    async with _candado:
        try:
            inicio, fin, _ = await rango_periodo_activo(db)
            if inicio > fin:
                return
            svc = AsistenciaService(AsistenciaRepository(db))
            quienes = "todas las personas" if empleado_ids is None else f"{len(empleado_ids)} personas"
            logger.info(f"🔄 [Recálculo] {motivo}: tramo abierto {inicio} → {fin}, {quienes}")
            dias, cur = 0, inicio
            while cur <= fin:
                f = cur.strftime("%Y-%m-%d")
                try:
                    await svc.procesar_dia(f, force=False, empleado_ids=empleado_ids)
                    dias += 1
                except Exception as e:
                    logger.warning(f"⚠️ [Recálculo] {motivo}: error en {f}: {e}")
                await asyncio.sleep(0.02)
                cur += timedelta(days=1)
            logger.success(f"✅ [Recálculo] {motivo}: {dias} días recalculados")
        except Exception as e:
            logger.error(f"❌ [Recálculo] {motivo}: {e}")


def lanzar(empleado_ids: Optional[Iterable[int]], motivo: str) -> None:
    """Deja el recálculo corriendo en segundo plano (uno a la vez) y vuelve enseguida."""
    ids = None if empleado_ids is None else {int(x) for x in empleado_ids}
    if ids is not None and not ids:
        return
    tarea = asyncio.create_task(_recalcular(ids, motivo))
    _tareas.add(tarea)
    tarea.add_done_callback(_tareas.discard)


async def recalcular_por_turno(db, turno_id: int, nombre: str = "") -> Dict[str, Any]:
    """Programa el recálculo del tramo abierto de las personas del turno y devuelve qué se va a recalcular."""
    inicio, fin, _ = await rango_periodo_activo(db)
    if inicio > fin:
        return {"personas": 0, "desde": None, "hasta": None}
    ids = await empleados_del_turno(db, turno_id, inicio, fin)
    lanzar(ids, f"turno {nombre or turno_id} guardado")
    return {"personas": len(ids), "desde": inicio.strftime("%Y-%m-%d"), "hasta": fin.strftime("%Y-%m-%d")}


async def recalcular_por_ajuste(db, clave: str) -> Optional[Dict[str, Any]]:
    """Si el ajuste lo usa el motor, programa el recálculo del tramo abierto de todos; si no, no hace nada."""
    if clave not in CLAVES_AJUSTE_QUE_RECALCULAN:
        return None
    inicio, fin, _ = await rango_periodo_activo(db)
    if inicio > fin:
        return None
    lanzar(None, f"ajuste {clave} guardado")
    return {"personas": "todas", "desde": inicio.strftime("%Y-%m-%d"), "hasta": fin.strftime("%Y-%m-%d")}
