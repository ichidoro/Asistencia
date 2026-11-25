"""
Estado de los relojes de marcación (31-10-2026; el dueño: «hay veces que se desconectan y no debemos estar buscando qué es»).

En cada ciclo del cron (cada 5 min) se lee de EasyTime la lista de relojes (/iclock/api/terminals/), la misma fuente de
las marcas, y se guarda en la tabla `ajustes`. La barra lateral lo muestra bajo «Servidor en línea» vía /api/sync/health/.

Códigos de estado de EasyTime (filtro «Estado» de su lista de dispositivos, leído el 31-10-2026):
  0 No autorizado · 1 En línea · 2 Comunicado · 3 Desconectado
Nunca debe romper la sincronización: todo está envuelto en try/except.

25-11-2026 (dueño: «la aplicación detecta ambos relojes activos y en realidad uno no está activo»): la API de EasyTime
deja el estado en «En línea» aunque el reloj deje de comunicarse; su propia pantalla lo pone en rojo según el tiempo
desde su última actividad. Por eso, si pasan más minutos sin actividad que el ajuste `relojes_minutos_sin_actividad`
(Configuración → Ajustes → Sincronización), el reloj se muestra «Sin conexión». Con 0 se usa solo el estado de EasyTime.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from loguru import logger

from backend.core.config import settings
from backend.core.database import db

_CLAVE = "estado_relojes"
ESTADOS_EASYTIME = {0: "No autorizado", 1: "En línea", 2: "Comunicado", 3: "Desconectado"}
GRUPO_POR_ESTADO = {0: "aviso", 1: "conectado", 2: "conectado", 3: "sin_conexion"}
# Sin una consulta buena en 3 ciclos del cron (como la alerta de sync_monitor) lo guardado ya no se muestra como vigente.
MINUTOS_VIGENCIA = 15


def _ahora() -> datetime:
    return datetime.now(ZoneInfo(settings.TIMEZONE)).replace(tzinfo=None)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _parse(s: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S") if s else None
    except (ValueError, TypeError):
        return None


async def _cargar() -> Dict[str, Any]:
    try:
        row = await db.fetch_one("SELECT valor FROM ajustes WHERE clave = ?", (_CLAVE,))
        return json.loads(row["valor"]) if row else {}
    except Exception as e:
        logger.warning(f"[Relojes] no se pudo leer el estado: {e}")
        return {}


async def _guardar(estado: Dict[str, Any]) -> None:
    try:
        await db.execute("INSERT OR REPLACE INTO ajustes (clave, valor) VALUES (?, ?)", (_CLAVE, json.dumps(estado)))
    except Exception as e:
        logger.warning(f"[Relojes] no se pudo guardar el estado: {e}")


async def actualizar() -> None:
    """Se llama al final de cada ciclo del cron. Si EasyTime no responde se conserva lo último leído con ok=False."""
    if not (settings.EASYTIME_URL and settings.EASYTIME_PASSWORD):
        return
    try:
        from backend.scraper.easytime_scraper import EasyTimeClient
        ahora = _fmt(_ahora())
        estado = await _cargar()
        try:
            cliente = EasyTimeClient(settings.EASYTIME_URL, settings.EASYTIME_USER, settings.EASYTIME_PASSWORD)
            relojes = await asyncio.wait_for(cliente.fetch_terminales(), timeout=45)
            estado.update({"consultado": ahora, "ok": True, "error": None, "ultimo_ok": ahora, "relojes": relojes})
        except Exception as e:
            logger.warning(f"[Relojes] no se pudo leer la lista de relojes de EasyTime: {e}")
            estado.update({"consultado": ahora, "ok": False, "error": str(e)[:300]})
        await _guardar(estado)
    except Exception as e:
        logger.warning(f"[Relojes] fallo interno (ignorado): {e}")


async def _minutos_sin_actividad() -> float:
    try:
        row = await db.fetch_one("SELECT valor FROM ajustes WHERE clave = 'relojes_minutos_sin_actividad'")
        return max(0.0, float(row["valor"])) if row and row["valor"] not in (None, "") else 0.0
    except Exception:
        return 0.0


def sin_actividad(ultima_actividad: Optional[str], ahora: datetime, umbral_min: float) -> bool:
    """True si el reloj lleva más de umbral_min minutos sin actividad. Con umbral 0 o sin fecha, no se decide aquí."""
    ult = _parse(ultima_actividad)
    return bool(umbral_min > 0 and ult is not None and (ahora - ult).total_seconds() > umbral_min * 60)


async def estado_para_pantalla() -> Optional[Dict[str, Any]]:
    """Lo que muestra la barra lateral. None si nunca se consultó."""
    est = await _cargar()
    umbral = await _minutos_sin_actividad()
    if not est.get("relojes"):
        return None
    ultimo_ok = _parse(est.get("ultimo_ok"))
    vigente = bool(est.get("ok")) and ultimo_ok is not None and (_ahora() - ultimo_ok).total_seconds() <= MINUTOS_VIGENCIA * 60
    relojes = []
    for r in est["relojes"]:
        codigo = r.get("estado")
        grupo = GRUPO_POR_ESTADO.get(codigo, "sin_dato") if vigente else "sin_dato"
        texto = ESTADOS_EASYTIME.get(codigo, f"Estado {codigo}")
        # La última actividad se compara con la hora de la consulta (lo que EasyTime respondió en ese momento)
        if vigente and grupo == "conectado" and sin_actividad(r.get("ultima_actividad"), _parse(est.get("consultado")) or _ahora(), umbral):
            grupo, texto = "sin_conexion", "Sin actividad"
        relojes.append({
            "alias": r.get("alias") or "",
            "grupo": grupo,
            "texto": texto,
            "ultima_actividad": r.get("ultima_actividad"),
        })
    return {"vigente": vigente, "ultimo_ok": est.get("ultimo_ok"), "relojes": relojes}
