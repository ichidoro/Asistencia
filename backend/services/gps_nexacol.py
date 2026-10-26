"""
Ruta GPS de los camiones, leída de Nexacol (modelo Logística → Ruta GPS), para compararla con la libreta 180h.
Nexacol (rutas /api/reports/camiones-gps-*, sin cambios en Nexacol) entrega los puntos del día (ya sin lo que pasa dentro de la planta) y las paradas; acá se reduce el día a 96 tramos de 15 minutos
(igual que la libreta) para que la pantalla los pueda comparar tramo a tramo.
"""
import asyncio
from typing import Any, Dict, List

import aiohttp

from backend.core.config import settings

SLOT_SEG = 900          # 15 minutos
VEL_MOVIENDO = 3        # km/h: bajo esto el camión está detenido (misma regla de Nexacol)
HUECO_MAX = 15 * 60     # sin reportar más que esto mientras se mueve: no hay dato

SIN_DATO, MOVIMIENTO, DETENIDO = 0, 1, 2


class GpsNexacolError(Exception):
    def __init__(self, status: int, mensaje: str):
        super().__init__(mensaje)
        self.status = status
        self.mensaje = mensaje


def calcular_slots(puntos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """96 estados (0 sin dato / en planta, 1 en movimiento, 2 detenido) a partir de los puntos del día ({s: segundos desde las 00:00, v: km/h})."""
    acc = [[0, 0] for _ in range(96)]   # [segundos en movimiento, segundos detenido]
    pts = sorted((p for p in puntos if isinstance(p.get("s"), (int, float))), key=lambda p: p["s"])
    for a, b in zip(pts, pts[1:]):
        ini, fin = a["s"], b["s"]
        dt = fin - ini
        if dt <= 0:
            continue
        detenido = (a.get("v") or 0) <= VEL_MOVIENDO
        # Un tramo detenido puede ser largo (Nexacol junta los puntos de una parada en dos); en movimiento, un hueco largo es falta de dato.
        if not detenido and dt > HUECO_MAX:
            continue
        if detenido and dt > HUECO_MAX and (b.get("v") or 0) > VEL_MOVIENDO:
            fin = ini + HUECO_MAX  # se detuvo y arrancó en algún momento del hueco: solo se cuenta hasta el límite
        t = max(ini, 0)
        while t < fin and t < 96 * SLOT_SEG:
            slot = int(t // SLOT_SEG)
            hasta = min(fin, (slot + 1) * SLOT_SEG)
            acc[slot][1 if detenido else 0] += hasta - t
            t = hasta
    slots, min_mov, min_det = [], 0, 0
    for mov, det in acc:
        min_mov += mov
        min_det += det
        if mov + det < SLOT_SEG / 3:
            slots.append(SIN_DATO)
        else:
            slots.append(MOVIMIENTO if mov >= det else DETENIDO)
    return {"slots": slots, "min_mov": round(min_mov / 60), "min_det": round(min_det / 60)}


_cookie = {"valor": ""}
_lock = asyncio.Lock()


async def _login(ses: aiohttp.ClientSession) -> str:
    """Entra a Nexacol con la cuenta de solo lectura de esta integración y devuelve la cookie de sesión (se reutiliza hasta que Nexacol la rechace)."""
    base = settings.NEXACOL_URL.rstrip("/")
    async with ses.post(base + "/api/auth/login", json={"username": settings.NEXACOL_USUARIO, "password": settings.NEXACOL_CLAVE}) as r:
        if r.status in (401, 403, 429):
            raise GpsNexacolError(502, "Nexacol rechazó la cuenta de la integración (usuario, clave o cuenta desactivada).")
        if r.status != 200:
            raise GpsNexacolError(502, f"Nexacol respondió {r.status} al iniciar sesión.")
        morsel = r.cookies.get("bi_session")
        if not morsel or not morsel.value:
            raise GpsNexacolError(502, "Nexacol no entregó una sesión.")
        return morsel.value


async def _get(ruta: str, params: Dict[str, str]) -> Dict[str, Any]:
    if not settings.NEXACOL_URL or not settings.NEXACOL_USUARIO or not settings.NEXACOL_CLAVE:
        raise GpsNexacolError(503, "La integración con Nexacol no está configurada en este servidor.")
    url = settings.NEXACOL_URL.rstrip("/") + ruta
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=75)) as ses:
            for intento in (1, 2):
                async with _lock:
                    if not _cookie["valor"]:
                        _cookie["valor"] = await _login(ses)
                async with ses.get(url, params=params, headers={"Cookie": f"bi_session={_cookie['valor']}"}) as r:
                    if r.status == 401 and intento == 1:
                        _cookie["valor"] = ""   # la sesión venció: se entra de nuevo y se repite una vez
                        continue
                    try:
                        data = await r.json(content_type=None)
                    except Exception:
                        data = {}
                    if r.status == 403:
                        raise GpsNexacolError(502, "La cuenta de la integración no tiene permiso a Logística → Ruta GPS en Nexacol.")
                    if r.status != 200 or not data.get("success"):
                        msg = (data or {}).get("error") or f"Nexacol respondió {r.status}"
                        raise GpsNexacolError(r.status if r.status in (400, 404) else 502, msg)
                    return data
        raise GpsNexacolError(502, "No se pudo iniciar sesión en Nexacol.")
    except GpsNexacolError:
        raise
    except Exception as e:
        raise GpsNexacolError(502, f"No se pudo consultar Nexacol: {e}")


async def vehiculos() -> List[Dict[str, str]]:
    data = await _get("/api/reports/camiones-gps-vehiculos", {})
    return sorted(({"id": str(v["id"]), "patente": str(v.get("patente") or v["id"])} for v in data.get("vehiculos", [])), key=lambda v: v["patente"])


async def recorrido_dia(vehiculo_id: str, fecha: str) -> Dict[str, Any]:
    data = await _get("/api/reports/camiones-gps-ruta", {"id": vehiculo_id, "fecha": fecha})
    puntos = data.get("puntos") or []
    res = data.get("resumen") or {}
    calc = calcular_slots(puntos)
    return {
        "success": True,
        "vehiculo": data.get("vehiculo"),
        "fecha": fecha,
        "origen": data.get("origen"),
        "hay_datos": len(puntos) > 0,
        "todo_el_dia_en_planta": bool((data.get("casaMatriz") or {}).get("todoElDia")),
        "resumen": {k: res.get(k) for k in ("km", "velMax", "minMovimiento", "minTotal", "primero", "ultimo")},
        "paradas": res.get("paradas") or [],
        "slots_gps": calc["slots"],
        "min_mov_gps": calc["min_mov"],
        "min_det_gps": calc["min_det"],
    }
