"""
Vigilancia de la sincronización automática de marcaciones (cron cada 5 min).

Antes, si EasyTime fallaba el ciclo terminaba igual con "ok / 0 nuevas" y nadie se enteraba.
Este monitor guarda el estado en la tabla `ajustes` (sobrevive a los reinicios) y avisa por correo cuando:

  - error:       3 ciclos seguidos fallan (≈15 min)               → cooldown 3 h
  - sin_marcas:  en horario laboral (lun-vie 07:00-19:00) pasan más de 2 h sin marcas nuevas
                 aunque los ciclos funcionen                        → cooldown 12 h

Cuando la condición se resuelve envía un aviso de "recuperado". Destinatarios: ALERT_EMAIL_TO del .env
(separados por coma); si no está, el correo SMTP_USER de operaciones.
Nunca debe romper la sincronización: todo está envuelto en try/except.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from loguru import logger

from backend.core.config import settings
from backend.core.database import db

_CLAVE = "monitor_sync_marcaciones"
ERRORES_PARA_ALERTA = 3
HORAS_SIN_MARCAS = 2
COOLDOWN_HORAS = {"error": 3, "sin_marcas": 12}
HORARIO_LABORAL = (7, 19)   # lunes a viernes


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
        logger.warning(f"[Monitor sync] no se pudo leer el estado: {e}")
        return {}


async def _guardar(estado: Dict[str, Any]) -> None:
    try:
        await db.execute("INSERT OR REPLACE INTO ajustes (clave, valor) VALUES (?, ?)", (_CLAVE, json.dumps(estado)))
    except Exception as e:
        logger.warning(f"[Monitor sync] no se pudo guardar el estado: {e}")


def _destinatarios() -> List[str]:
    crudo = settings.ALERT_EMAIL_TO or settings.SMTP_USER or ""
    return [x.strip() for x in crudo.split(",") if x.strip()]


async def _enviar(asunto: str, detalle: str, color: str) -> None:
    para = _destinatarios()
    if not para:
        logger.warning(f"[Monitor sync] sin destinatarios para: {asunto}")
        return
    html = (
        f'<div style="font-family:Arial,sans-serif;max-width:560px">'
        f'<h3 style="color:{color};margin:0 0 8px">{asunto}</h3>'
        f'<p style="margin:0 0 8px">{detalle}</p>'
        f'<p style="color:#64748b;font-size:12px;margin:0">Sistema de Asistencia · {_fmt(_ahora())} (hora Chile). '
        f'El detalle está en logs/cron_sync.log del servidor.</p></div>'
    )
    try:
        from backend.services.notification_service import NotificationService
        await NotificationService()._send_email(para, asunto, html)
    except Exception as e:
        logger.error(f"[Monitor sync] no se pudo enviar el correo '{asunto}': {e}")


def _condiciones(estado: Dict[str, Any], ahora: datetime) -> Dict[str, str]:
    """Devuelve {tipo: detalle} de las alertas que hoy deberían estar activas."""
    activas: Dict[str, str] = {}
    seguidos = int(estado.get("errores_seguidos", 0))
    if seguidos >= ERRORES_PARA_ALERTA:
        ult = estado.get("ultimo_error") or {}
        activas["error"] = (
            f"La sincronización de marcaciones falló {seguidos} ciclos seguidos "
            f"(desde {estado.get('error_desde', '?')}). Motivo: {ult.get('msg', 'desconocido')}. "
            f"Las marcas siguen guardadas en EasyTime y se recuperan solas cuando el problema se resuelva."
        )
    elif seguidos == 0:
        hora = ahora.hour
        laboral = ahora.weekday() < 5 and HORARIO_LABORAL[0] <= hora < HORARIO_LABORAL[1]
        ult_nuevas = _parse(estado.get("ultimas_nuevas"))
        if laboral and ult_nuevas and (ahora - ult_nuevas).total_seconds() > HORAS_SIN_MARCAS * 3600:
            activas["sin_marcas"] = (
                f"Los ciclos funcionan, pero no llegan marcas nuevas desde {estado.get('ultimas_nuevas')} "
                f"(más de {HORAS_SIN_MARCAS} h en horario laboral). Revisar que los relojes estén enviando "
                f"marcas a EasyTime. Si hoy es feriado o día sin turnos, se puede ignorar."
            )
    return activas


async def registrar_ciclo(ok: bool, nuevas: int = 0, error: Optional[str] = None) -> None:
    """Se llama al final de cada ciclo del cron. Nunca lanza excepciones."""
    try:
        ahora = _ahora()
        estado = await _cargar()
        if ok:
            estado["errores_seguidos"] = 0
            estado.pop("error_desde", None)
            estado["ultimo_ok"] = _fmt(ahora)
            if nuevas > 0 or not estado.get("ultimas_nuevas"):
                estado["ultimas_nuevas"] = _fmt(ahora)
        else:
            estado["errores_seguidos"] = int(estado.get("errores_seguidos", 0)) + 1
            estado.setdefault("error_desde", _fmt(ahora))
            estado["ultimo_error"] = {"ts": _fmt(ahora), "msg": (error or "error desconocido")[:300]}

        activas = _condiciones(estado, ahora)
        enviadas: Dict[str, str] = estado.get("alertas", {})

        for tipo, detalle in activas.items():
            ult = _parse(enviadas.get(tipo))
            if ult is None or (ahora - ult).total_seconds() >= COOLDOWN_HORAS[tipo] * 3600:
                titulo = ("⚠️ Asistencia: la sincronización de marcaciones está fallando" if tipo == "error"
                          else "⚠️ Asistencia: no llegan marcas nuevas")
                await _enviar(titulo, detalle, "#dc2626")
                enviadas[tipo] = _fmt(ahora)

        for tipo in list(enviadas.keys()):
            if tipo not in activas and (tipo == "error" and ok or tipo == "sin_marcas" and ok and nuevas > 0):
                titulo = ("✅ Asistencia: la sincronización de marcaciones se recuperó" if tipo == "error"
                          else "✅ Asistencia: volvieron a llegar marcas")
                await _enviar(titulo, "El sistema volvió a funcionar con normalidad.", "#059669")
                enviadas.pop(tipo, None)

        estado["alertas"] = enviadas
        await _guardar(estado)
    except Exception as e:
        logger.warning(f"[Monitor sync] fallo interno (ignorado): {e}")


async def estado_actual() -> Dict[str, Any]:
    est = await _cargar()
    return {
        "fuente": "easytime" if (settings.EASYTIME_URL and settings.EASYTIME_PASSWORD) else "bioalba",
        "ultimo_ok": est.get("ultimo_ok"),
        "ultimas_nuevas": est.get("ultimas_nuevas"),
        "errores_seguidos": est.get("errores_seguidos", 0),
        "ultimo_error": est.get("ultimo_error"),
    }
