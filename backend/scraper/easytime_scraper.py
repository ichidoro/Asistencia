"""
EasyTime Pro (time1.controlasistencia.cl) — origen de marcaciones.

Desde el 01-10-2026 los relojes (AGUACOL / AGUACOL 2) reportan a EasyTime Pro y BioAlba dejó de
recibir marcas. Este cliente inicia sesión con una cuenta de servicio y lee las marcaciones por
la API REST (/iclock/api/transactions/, JSON paginado), que es más liviana y precisa que el Excel.

Devuelve el mismo formato que BioAlbaScraper.get_marcaciones():
    {'rut': '9138353011', 'fecha_hora': 'YYYY-MM-DD HH:MM:SS', 'tipo': 'Entrada'|'Salida', 'equipo': 'AGUACOL'}
"""

import asyncio
import calendar
import re
from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

_CSRF_RE = re.compile(r"name=['\"]csrfmiddlewaretoken['\"]\s+value=['\"]([^'\"]+)['\"]")

# EasyTime: 0 entrada, 1 salida, 2 salida a colación, 3 entrada de colación, 4 entrada HE, 5 salida HE
_ENTRADAS = {'0', '3', '4'}
_SALIDAS = {'1', '2', '5'}


def _rut_limpio(valor: Any) -> str:
    """Mismo criterio que BioAlba: solo dígitos y K, sin puntos ni guión."""
    if not valor:
        return ""
    return re.sub(r'[^0-9Kk]', '', str(valor)).upper()


class EasyTimeClient:
    PAGE_SIZE = 500
    REINTENTOS = 4
    MAX_PAGES = 200   # tope de seguridad (200k marcas)

    def __init__(self, base_url: str, usuario: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.usuario = usuario
        self.password = password

    async def _login(self, session: aiohttp.ClientSession) -> None:
        async with session.get(f"{self.base_url}/login/") as resp:
            html = await resp.text()
        m = _CSRF_RE.search(html)
        if not m:
            raise RuntimeError("EasyTime: no se encontró el token CSRF en /login/")
        token = m.group(1)
        headers = {
            "Referer": f"{self.base_url}/login/",
            "X-CSRFToken": token,
            "X-Requested-With": "XMLHttpRequest",
        }
        data = {"csrfmiddlewaretoken": token, "username": self.usuario, "password": self.password}
        async with session.post(f"{self.base_url}/login/", data=data, headers=headers) as resp:
            body = await resp.json(content_type=None)
        if body.get("ret") != 0:
            raise RuntimeError(f"EasyTime: login rechazado ({body.get('message') or body})")

    async def fetch_marcaciones(self, anio: int, mes: int,
                                ruts_set: Optional[set] = None,
                                rut_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        ultimo = calendar.monthrange(anio, mes)[1]
        inicio = f"{anio}-{mes:02d}-01 00:00:00"
        fin = f"{anio}-{mes:02d}-{ultimo:02d} 23:59:59"
        rut_filtro = _rut_limpio(rut_filter) if rut_filter else ""

        timeout = aiohttp.ClientTimeout(total=120)
        jar = aiohttp.CookieJar(unsafe=True)
        resultado: List[Dict[str, Any]] = []
        descartadas = 0
        async with aiohttp.ClientSession(timeout=timeout, cookie_jar=jar) as session:
            await self._login(session)
            pagina = 1
            while pagina <= self.MAX_PAGES:
                params = {"page": pagina, "page_size": self.PAGE_SIZE, "start_time": inicio, "end_time": fin}
                payload = None
                for intento in range(1, self.REINTENTOS + 1):
                    try:
                        async with session.get(f"{self.base_url}/iclock/api/transactions/", params=params) as resp:
                            if resp.status == 200:
                                payload = await resp.json(content_type=None)
                                break
                            error = f"HTTP {resp.status}"
                    except (aiohttp.ClientError, asyncio.TimeoutError) as e_red:
                        error = str(e_red)
                    logger.warning(f"⚠️ EasyTime página {pagina}: {error} (intento {intento}/{self.REINTENTOS})")
                    await asyncio.sleep(1.5 * intento)
                if payload is None:
                    raise RuntimeError(f"EasyTime: la página {pagina} falló tras {self.REINTENTOS} intentos")
                filas = payload.get("data") or []
                for f in filas:
                    rut = _rut_limpio(f.get("emp_code"))
                    hora = (f.get("punch_time") or "").strip()
                    if not rut or not hora:
                        continue
                    if rut_filtro and rut != rut_filtro:
                        continue
                    if ruts_set and rut not in ruts_set:
                        descartadas += 1
                        continue
                    estado = str(f.get("punch_state"))
                    tipo = "Entrada" if estado in _ENTRADAS else ("Salida" if estado in _SALIDAS else "Desconocido")
                    resultado.append({
                        "rut": rut,
                        "fecha_hora": hora,
                        "tipo": tipo,
                        "equipo": (f.get("terminal_alias") or "Manual").strip(),
                    })
                if not payload.get("next") or not filas:
                    break
                pagina += 1

        extra = f" (descartadas por RUT desconocido: {descartadas})" if descartadas else ""
        logger.info(f"✅ EasyTime {anio}-{mes:02d}: {len(resultado)} marcaciones{extra}")
        return resultado
