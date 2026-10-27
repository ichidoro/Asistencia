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


# ── Facturas del camión contra sus paradas ────────────────────────────────────────────────────────────
# Nexacol calza las facturas con el camión SOLO por la patente (las emitidas el día hábil anterior a la salida) y las agrupa por entrega
# (cliente + dirección de envío, con la coordenada de la dirección). Acá se mide cuánto está cada entrega de la parada más cercana del GPS.
CALZA_M = 150   # hasta esta distancia la entrega "calza" con una parada
CERCA_M = 500   # hasta esta, la parada es "muy cercana" (el camión paró en la cuadra de al lado, no en la dirección)


def _metros(la1: float, lo1: float, la2: float, lo2: float) -> float:
    from math import asin, cos, radians, sin, sqrt
    dla, dlo = radians(la2 - la1), radians(lo2 - lo1)
    h = sin(dla / 2) ** 2 + cos(radians(la1)) * cos(radians(la2)) * sin(dlo / 2) ** 2
    return 2 * 6371000 * asin(sqrt(h))


def cruzar_entregas(entregas: List[Dict[str, Any]], paradas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Para cada entrega, la parada más cercana y su estado; y para cada parada, la entrega a la que corresponde (si hay una a menos de CERCA_M).
    Estados: calza · cercana · lejos · sin_parada (el camión no se detuvo) · aprox (dirección ubicada solo por comuna: no se juzga) · sin_ubicacion."""
    def num(v: Any) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    ps = [(i, p) for i, p in enumerate(paradas) if num(p.get("la")) and num(p.get("lo"))]
    items: List[Dict[str, Any]] = []
    for e in entregas:
        item = {"cliente": e.get("cliente"), "calle": e.get("calle"), "comuna": e.get("comuna"), "folios": e.get("folios") or [], "kilos": e.get("kilos"),
                "exacto": bool(e.get("exacto")), "estado": "sin_ubicacion", "dist_m": None, "parada": None, "parada_idx": None}
        if num(e.get("lat")) and num(e.get("lon")):
            if not ps:
                item["estado"] = "sin_parada"
            else:
                d, i, p = min(((_metros(e["lat"], e["lon"], q["la"], q["lo"]), i, q) for i, q in ps), key=lambda t: t[0])
                item["dist_m"] = round(d)
                item["parada_idx"] = i
                item["parada"] = {k: p.get(k) for k in ("desde", "hasta", "min", "lugar")}
                item["estado"] = "aprox" if not item["exacto"] else "calza" if d <= CALZA_M else "cercana" if d <= CERCA_M else "lejos"
        items.append(item)
    # Cada parada con la entrega (de ubicación exacta) más cercana a ella, si queda a menos de CERCA_M
    por_parada: List[Any] = [None] * len(paradas)
    for it in items:
        if it["exacto"] and it["parada_idx"] is not None and it["dist_m"] is not None and it["dist_m"] <= CERCA_M:
            actual = por_parada[it["parada_idx"]]
            if actual is None or it["dist_m"] < actual["dist_m"]:
                por_parada[it["parada_idx"]] = {"cliente": it["cliente"], "dist_m": it["dist_m"], "estado": it["estado"]}
    cuenta = {k: sum(1 for it in items if it["estado"] == k) for k in ("calza", "cercana", "lejos", "sin_parada", "aprox", "sin_ubicacion")}
    return {"entregas": items, "paradas": por_parada, "resumen": {"total": len(items), **cuenta}}


async def entregas_dia(vehiculo_id: str, fecha: str) -> Dict[str, Any]:
    ruta = await _get("/api/reports/camiones-gps-ruta", {"id": vehiculo_id, "fecha": fecha})
    patente = str((ruta.get("vehiculo") or {}).get("patente") or "")
    paradas = (ruta.get("resumen") or {}).get("paradas") or []
    fac = await _get("/api/reports/camiones-gps-facturas", {"id": vehiculo_id, "patente": patente, "fecha": fecha, "geo": "1"})
    cruce = cruzar_entregas(fac.get("entregas") or [], paradas)
    return {"success": True, "patente": patente, "fecha": fecha, "salio": fac.get("salio") is not False, "desde": fac.get("desde"), "hasta": fac.get("hasta"),
            "total_facturas": fac.get("total") or 0, "umbrales": {"calza_m": CALZA_M, "cerca_m": CERCA_M}, **cruce}
