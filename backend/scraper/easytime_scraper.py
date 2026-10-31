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
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

from backend.core.config import settings

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
    MAX_PEDIDOS = 400   # tope de seguridad de pedidos por descarga

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

    async def _pedir(self, session: aiohttp.ClientSession, ini: datetime, fin: datetime,
                     pagina: int = 1) -> Dict[str, Any]:
        params = {"page": pagina, "page_size": self.PAGE_SIZE,
                  "start_time": ini.strftime("%Y-%m-%d %H:%M:%S"), "end_time": fin.strftime("%Y-%m-%d %H:%M:%S")}
        error = ""
        for intento in range(1, self.REINTENTOS + 1):
            try:
                async with session.get(f"{self.base_url}/iclock/api/transactions/", params=params) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
                    error = f"HTTP {resp.status}"
            except (aiohttp.ClientError, asyncio.TimeoutError) as e_red:
                error = str(e_red)
            logger.warning(f"⚠️ EasyTime {params['start_time']}: {error} (intento {intento}/{self.REINTENTOS})")
            await asyncio.sleep(1.5 * intento)
        raise RuntimeError(f"EasyTime: el tramo {params['start_time']} → {params['end_time']} falló tras {self.REINTENTOS} intentos")

    async def _tramo(self, session: aiohttp.ClientSession, ini: datetime, fin: datetime,
                     acum: Dict[Any, Dict[str, Any]], pedidos: List[int]) -> None:
        """Trae las marcas de [ini, fin] en UNA sola página.
        La paginación de EasyTime no es estable (sin orden fijo, repite filas y salta otras: con ~3.900 marcas al mes
        se perdían ~7%, distintas en cada descarga). Por eso cada pedido debe caber en una página: si el total
        (count) la supera, el tramo se parte a la mitad. Cada página se verifica contra count y se deduplica por id."""
        pedidos[0] += 1
        if pedidos[0] > self.MAX_PEDIDOS:
            raise RuntimeError("EasyTime: demasiados pedidos en una descarga (tope de seguridad)")
        for intento in range(1, self.REINTENTOS + 1):
            payload = await self._pedir(session, ini, fin)
            total = int(payload.get("count") or 0)
            filas = payload.get("data") or []
            if total > self.PAGE_SIZE or len({f.get("id") for f in filas}) == total:
                break
            logger.warning(f"⚠️ EasyTime {ini}: llegaron {len(filas)} de {total} marcas (intento {intento}/{self.REINTENTOS})")
            await asyncio.sleep(1.5 * intento)
        else:
            raise RuntimeError(f"EasyTime: el tramo {ini} → {fin} no devuelve todas sus marcas")
        if total > self.PAGE_SIZE:
            if fin - ini < timedelta(seconds=2):
                raise RuntimeError(f"EasyTime: más de {self.PAGE_SIZE} marcas en {ini}")
            mitad = ini + (fin - ini) / 2
            mitad = mitad.replace(microsecond=0)
            await self._tramo(session, ini, mitad, acum, pedidos)
            await self._tramo(session, mitad + timedelta(seconds=1), fin, acum, pedidos)
            return
        for f in filas:
            acum[f.get("id")] = f

    async def fetch_terminales(self) -> List[Dict[str, Any]]:
        """Relojes registrados en EasyTime con su estado (código de EasyTime) y su última actividad."""
        timeout = aiohttp.ClientTimeout(total=30)
        conector = aiohttp.TCPConnector(ssl=False) if not settings.EASYTIME_VERIFY_SSL else None
        async with aiohttp.ClientSession(timeout=timeout, cookie_jar=aiohttp.CookieJar(unsafe=True), connector=conector) as session:
            await self._login(session)
            async with session.get(f"{self.base_url}/iclock/api/terminals/", params={"page_size": 100}) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"EasyTime: la lista de relojes respondió HTTP {resp.status}")
                body = await resp.json(content_type=None)
        return [{"alias": str(t.get("alias") or t.get("sn") or "").strip(),
                 "estado": t.get("state"),
                 "ultima_actividad": t.get("last_activity")}
                for t in (body.get("data") or [])]

    async def fetch_marcaciones(self, anio: int, mes: int,
                                ruts_set: Optional[set] = None,
                                rut_filter: Optional[str] = None,
                                desde: Optional[str] = None,
                                hasta: Optional[str] = None) -> List[Dict[str, Any]]:
        """Marcaciones del mes. desde/hasta ('AAAA-MM-DD', opcionales) acotan la descarga a ese rango dentro del mes."""
        primero = date(anio, mes, 1)
        ultimo = date(anio, mes, calendar.monthrange(anio, mes)[1])
        if desde:
            primero = max(primero, date.fromisoformat(desde[:10]))
        if hasta:
            ultimo = min(ultimo, date.fromisoformat(hasta[:10]))
        rut_filtro = _rut_limpio(rut_filter) if rut_filter else ""
        resultado: List[Dict[str, Any]] = []
        if primero > ultimo:
            return resultado

        timeout = aiohttp.ClientTimeout(total=120)
        jar = aiohttp.CookieJar(unsafe=True)
        descartadas = 0
        conector = None
        if not settings.EASYTIME_VERIFY_SSL:
            logger.warning("⚠️ EASYTIME_VERIFY_SSL=false: no se valida el certificado SSL de EasyTime (temporal)")
            conector = aiohttp.TCPConnector(ssl=False)
        acum: Dict[Any, Dict[str, Any]] = {}
        pedidos = [0]
        async with aiohttp.ClientSession(timeout=timeout, cookie_jar=jar, connector=conector) as session:
            await self._login(session)
            dia = primero
            while dia <= ultimo:
                await self._tramo(session, datetime.combine(dia, time(0, 0, 0)),
                                  datetime.combine(dia, time(23, 59, 59)), acum, pedidos)
                dia += timedelta(days=1)

        for f in acum.values():
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

        extra = f" (descartadas por RUT desconocido: {descartadas})" if descartadas else ""
        logger.info(f"✅ EasyTime {primero} → {ultimo}: {len(resultado)} marcaciones en {pedidos[0]} pedidos{extra}")
        return resultado
