"""Aviso por Telegram (bot de portería) cuando entra o sale una persona vigilada de Artículo 22.

Configuración por entorno (nunca en el repo, que es público): TELEGRAM_PORTERIA_TOKEN y TELEGRAM_PORTERIA_CHAT_ID.
Sin token no hace nada; sin chat id lo busca una vez en los mensajes que alguien le haya escrito al bot.
"""
import os
import re
import unicodedata
from typing import Optional

import aiohttp
from loguru import logger

# (apellido paterno, primer nombre) normalizados: «OTEIZA CANALES, DANIEL ANTONIO» y «BARBOZA., PEDRO PABLO»
VIGILADOS = {("oteiza", "daniel"), ("barboza", "pedro")}
_chat_id: Optional[str] = None


def _norm(t: object) -> str:
    sin_tildes = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", sin_tildes.lower()).strip()


def es_vigilado(paterno: object, nombre: object) -> bool:
    partes = _norm(nombre).split()
    return bool(partes) and (_norm(paterno), partes[0]) in VIGILADOS


async def _buscar_chat(ses: aiohttp.ClientSession, token: str) -> Optional[str]:
    async with ses.get(f"https://api.telegram.org/bot{token}/getUpdates") as r:
        for u in reversed((await r.json()).get("result") or []):
            chat = (u.get("message") or {}).get("chat") or {}
            if chat.get("id"):
                return str(chat["id"])
    return None


async def avisar_marca(emp: dict, tipo: str, hora: str, registrado_por: str) -> None:
    """Envía «ENTRADA/SALIDA» si el empleado es de los vigilados. Nunca lanza: un fallo de Telegram no debe romper la marca de portería."""
    global _chat_id
    token = os.getenv("TELEGRAM_PORTERIA_TOKEN")
    if not token or not es_vigilado(emp.get("apellido_paterno"), emp.get("nombre")):
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as ses:
            chat = os.getenv("TELEGRAM_PORTERIA_CHAT_ID") or _chat_id or await _buscar_chat(ses, token)
            if not chat:
                logger.warning("[ART22] Telegram: no hay chat id (escríbele al bot o define TELEGRAM_PORTERIA_CHAT_ID)")
                return
            _chat_id = chat
            nombre = " ".join(str(emp.get(k) or "").strip() for k in ("apellido_paterno", "apellido_materno", "nombre")).strip()
            icono, texto = ("🟢", "ENTRÓ a planta") if tipo == "E" else ("🔴", "SALIÓ de planta")
            msg = f"{icono} {nombre} {texto}\n🕐 {hora[:5]} · Art. 22 · registró {registrado_por}"
            async with ses.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": msg}) as r:
                if r.status != 200:
                    logger.warning(f"[ART22] Telegram respondió {r.status}: {(await r.text())[:200]}")
    except Exception as ex:
        logger.warning(f"[ART22] Telegram falló: {ex}")
