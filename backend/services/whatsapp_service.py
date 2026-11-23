"""Avisos por WhatsApp a través de la puerta wa-gateway (número propio vinculado con QR).

Sin WHATSAPP_ENABLED ni token no hace nada. `enviar` nunca lanza: un fallo de WhatsApp no debe romper lo que lo llamó.
"""
import re
from typing import Optional

import aiohttp
from loguru import logger

from backend.core.config import settings


def normalizar_telefono(tel: object) -> Optional[str]:
    """Teléfono chileno -> solo dígitos con 56 (ej. 56912345678). None si no sirve para WhatsApp."""
    d = re.sub(r"\D", "", str(tel or ""))
    if d.startswith("56") and len(d) == 11 and d[2] == "9":
        return d
    if len(d) == 9 and d[0] == "9":
        return "56" + d
    return None


def destino_valido(destino: object) -> Optional[str]:
    """Un grupo («123-456@g.us», tal como lo entrega la puerta) o un celular chileno. None si no sirve."""
    s = str(destino or "").strip()
    if re.fullmatch(r"[0-9-]+@g\.us", s) or re.fullmatch(r"[0-9]{8,20}@(s\.whatsapp\.net|lid)", s):
        return s  # grupo, o contacto del teléfono (puede ser de cualquier país)
    return normalizar_telefono(s)


def activo() -> bool:
    return bool(settings.WHATSAPP_ENABLED and settings.WHATSAPP_GATEWAY_TOKEN)


async def _llamar(metodo: str, ruta: str, cuerpo: Optional[dict] = None) -> tuple[int, dict]:
    cab = {"Authorization": f"Bearer {settings.WHATSAPP_GATEWAY_TOKEN}"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as ses:
        async with ses.request(metodo, f"{settings.WHATSAPP_GATEWAY_URL}{ruta}", json=cuerpo, headers=cab) as r:
            return r.status, await r.json(content_type=None)


async def enviar(telefono: object, texto: str) -> bool:
    """True solo si la puerta aceptó el mensaje. `telefono` es un celular o un grupo."""
    if not activo():
        return False
    num = destino_valido(telefono)
    if not num or not texto:
        logger.warning("WhatsApp: teléfono o texto inválido, no se envía.")
        return False
    try:
        codigo, resp = await _llamar("POST", "/enviar", {"to": num, "text": texto})
        if codigo != 200:
            logger.warning(f"WhatsApp: la puerta respondió {codigo}: {resp.get('error')}")
        return codigo == 200
    except Exception as e:
        logger.warning(f"WhatsApp: no se pudo enviar ({e})")
        return False


async def grupos() -> list:
    """Grupos de WhatsApp en los que está el número ([] si no está conectado)."""
    if not activo():
        return []
    try:
        codigo, r = await _llamar("GET", "/chats")
        return r.get("grupos", []) if codigo == 200 else []
    except Exception as e:
        logger.warning(f"WhatsApp: no se pudieron leer los grupos ({e})")
        return []


async def contactos() -> list:
    """Contactos agregados en el teléfono vinculado ([] si no está conectado o WhatsApp aún no los entregó)."""
    if not activo():
        return []
    try:
        codigo, r = await _llamar("GET", "/contactos")
        return r.get("contactos", []) if codigo == 200 else []
    except Exception as e:
        logger.warning(f"WhatsApp: no se pudieron leer los contactos ({e})")
        return []


async def desconectar() -> bool:
    """Cierra la sesión en WhatsApp y deja la puerta pidiendo un QR nuevo."""
    if not activo():
        return False
    try:
        codigo, _ = await _llamar("POST", "/desconectar")
        return codigo == 200
    except Exception as e:
        logger.warning(f"WhatsApp: no se pudo desconectar ({e})")
        return False


async def estado() -> dict:
    """{activo, estado, qr}: lo que necesita la pantalla de vinculación."""
    if not activo():
        return {"activo": False, "estado": "apagado", "qr": None}
    try:
        _, r = await _llamar("GET", "/qr")
        return {"activo": True, "estado": r.get("estado", "desconocido"), "qr": r.get("qr")}
    except Exception as e:
        logger.warning(f"WhatsApp: puerta sin respuesta ({e})")
        return {"activo": True, "estado": "sin_puerta", "qr": None}
