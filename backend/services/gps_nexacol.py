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
# (cliente + dirección de envío). Cada parada del GPS trae su dirección en texto ("Shell, Avenida X, Curicó, Región…"), así que la entrega se
# compara con las paradas por CALLE y COMUNA. Si la dirección de la factura tiene coordenada guardada, además se mide la distancia a la parada
# (en producción la geocodificación por red está apagada y casi ninguna dirección tiene coordenada: el texto es lo que decide).
CALZA_M = 150   # con coordenada: hasta esta distancia la entrega "calza" con una parada
CERCA_M = 500   # con coordenada: hasta esta, la parada es "muy cercana"

_ABREV_CALLE = {"av", "avda", "avenida", "calle", "cll", "pasaje", "psje", "pje", "camino", "cam", "ruta", "ruta5", "carretera", "kilometro", "km", "poblacion", "pob", "villa", "block", "depto", "dpto", "casa", "lote", "parcela", "sitio", "sector", "nro", "numero", "sn", "las", "los", "del"}


_ARTICULOS = {"de", "del", "la", "las", "los", "el", "y"}
# Calles numeradas (Talca: "14 Norte", "6 Oriente"): el número va a veces en letras ("Dos Sur", "Once Oriente")
_NUM_PALABRA = {"uno": "1", "un": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5", "seis": "6", "siete": "7", "ocho": "8", "nueve": "9", "diez": "10", "once": "11", "doce": "12",
                "trece": "13", "catorce": "14", "quince": "15", "dieciseis": "16", "diecisiete": "17", "dieciocho": "18", "diecinueve": "19", "veinte": "20"}
_DIRECCIONES = {"norte": "norte", "nte": "norte", "sur": "sur", "oriente": "oriente", "ote": "oriente", "poniente": "poniente", "pte": "poniente"}


def _norm(t: Any) -> str:
    """Minúsculas, sin tildes ni signos: "AV. O'Higgins 12" -> "av ohiggins 12"."""
    import re
    import unicodedata
    # "16 1/2 Norte" y "16½ Norte" son la misma calle
    t = re.sub(r"(\d+)\s*(?:1\s*/\s*2|½)", r"\1medio", str(t or ""))
    t = unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode().lower().replace("'", "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


def _palabras(t: Any) -> List[str]:
    return [_NUM_PALABRA.get(w, w) for w in _norm(t).split()]


def _identificadores_calle(calle: Any) -> Dict[str, List[str]]:
    """Lo que identifica la calle. En las calles numeradas la identidad es el PAR número + dirección ("14 norte", "6 oriente"): las palabras
    sueltas ("norte", "oriente") están en medio Talca y no sirven. En el resto, las palabras del nombre (sin "avenida", "pasaje", números ni artículos)."""
    pal = _palabras(calle)
    pares = [f"{pal[i]} {_DIRECCIONES[pal[i + 1]]}" for i in range(len(pal) - 1) if pal[i].isdigit() and pal[i + 1] in _DIRECCIONES]
    nombre = [w for w in pal if len(w) >= 3 and not w.isdigit() and w not in _ABREV_CALLE]
    return {"pares": pares, "nombre": nombre}


def _tokens_calle(calle: Any) -> List[str]:
    return _identificadores_calle(calle)["nombre"]


def _calle_en_lugar(ident: Dict[str, List[str]], palabras: Any, pares: Any) -> bool:
    if ident["pares"]:
        # En una esquina ("6 Oriente esquina 3 Norte") basta con que la parada esté en una de las dos calles
        return any(p in pares for p in ident["pares"])
    return bool(ident["nombre"]) and all(t in palabras for t in ident["nombre"])


def _metros(la1: float, lo1: float, la2: float, lo2: float) -> float:
    from math import asin, cos, radians, sin, sqrt
    dla, dlo = radians(la2 - la1), radians(lo2 - lo1)
    h = sin(dla / 2) ** 2 + cos(radians(la1)) * cos(radians(la2)) * sin(dlo / 2) ** 2
    return 2 * 6371000 * asin(sqrt(h))


def cruzar_entregas(entregas: List[Dict[str, Any]], paradas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Para cada entrega, la parada que le corresponde y su estado; y para cada parada, la entrega a la que corresponde.
    Estados: calza (la calle y la comuna están en la dirección de una parada, o la parada queda a ≤ CALZA_M) · cercana (con coordenada, ≤ CERCA_M)
    · comuna (el camión paró en esa comuna, pero NO se sabe en cuál de esas paradas: no se elige ninguna) · lejos (con coordenada, a más de CERCA_M de
    toda parada) · sin_parada (el camión no paró en esa comuna)."""
    def num(v: Any) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    ps = []
    for i, p in enumerate(paradas):
        pal = _palabras(p.get("lugar"))
        ps.append((i, p, set(pal), {f"{a} {b}" for a, b in zip(pal, pal[1:])}))
    items: List[Dict[str, Any]] = []
    for e in entregas:
        item = {"cliente": e.get("cliente"), "calle": e.get("calle"), "comuna": e.get("comuna"), "folios": e.get("folios") or [], "kilos": e.get("kilos"),
                "exacto": bool(e.get("exacto")), "estado": "sin_parada", "via": None, "dist_m": None, "parada": None, "parada_idx": None, "paradas_comuna": []}
        # La comuna y la calle se comparan por palabras ("San Francisco Mostazal" calza con "San Francisco de Mostazal")
        comuna = [w for w in _norm(e.get("comuna")).split() if w not in _ARTICULOS]
        ident = _identificadores_calle(e.get("calle"))
        en_comuna = [(i, p) for i, p, pal, _ in ps if comuna and all(w in pal for w in comuna)]
        # Si varias paradas coinciden en calle y comuna, la que corresponde a una entrega es la más larga
        en_calle = sorted(((i, p) for i, p, pal, pares in ps if comuna and all(w in pal for w in comuna) and _calle_en_lugar(ident, pal, pares)), key=lambda t: -(t[1].get("min") or 0))
        # con coordenada guardada: distancia a la parada más cercana
        con_coord = num(e.get("lat")) and num(e.get("lon"))
        near = min(((_metros(e["lat"], e["lon"], q["la"], q["lo"]), i, q) for i, q, _, _ in ps if num(q.get("la")) and num(q.get("lo"))), key=lambda t: t[0], default=None) if con_coord else None
        elegida = None
        if near and item["exacto"] and near[0] <= CALZA_M:
            item["estado"], item["via"], elegida = "calza", "distancia", (near[1], near[2])
        elif en_calle:
            item["estado"], item["via"], elegida = "calza", "direccion", en_calle[0]
        elif near and item["exacto"] and near[0] <= CERCA_M:
            item["estado"], item["via"], elegida = "cercana", "distancia", (near[1], near[2])
        elif en_comuna:
            # Solo se sabe que el camión paró en esa comuna: no se asigna ninguna parada (sería inventar cuál)
            item["estado"], item["via"] = "comuna", "comuna"
            item["paradas_comuna"] = [{k: p.get(k) for k in ("desde", "hasta", "min")} for _, p in en_comuna]
        elif near and item["exacto"]:
            item["estado"], item["via"], elegida = "lejos", "distancia", (near[1], near[2])
        if near:
            item["dist_m"] = round(near[0]) if item["exacto"] else None
        if elegida:
            item["parada_idx"] = elegida[0]
            item["parada"] = {k: elegida[1].get(k) for k in ("desde", "hasta", "min", "lugar")}
        items.append(item)
    # Cada parada con la entrega que le corresponde (la de mejor estado)
    peso = {"calza": 2, "cercana": 1}
    por_parada: List[Any] = [None] * len(paradas)
    for it in items:
        k = it["parada_idx"]
        if k is not None and it["estado"] in peso and (por_parada[k] is None or peso[it["estado"]] > peso[por_parada[k]["estado"]]):
            por_parada[k] = {"cliente": it["cliente"], "dist_m": it["dist_m"], "estado": it["estado"], "via": it["via"]}
    cuenta = {k: sum(1 for it in items if it["estado"] == k) for k in ("calza", "cercana", "comuna", "lejos", "sin_parada")}
    return {"entregas": items, "paradas": por_parada, "resumen": {"total": len(items), **cuenta}}


async def entregas_dia(vehiculo_id: str, fecha: str) -> Dict[str, Any]:
    ruta = await _get("/api/reports/camiones-gps-ruta", {"id": vehiculo_id, "fecha": fecha})
    patente = str((ruta.get("vehiculo") or {}).get("patente") or "")
    paradas = (ruta.get("resumen") or {}).get("paradas") or []
    fac = await _get("/api/reports/camiones-gps-facturas", {"id": vehiculo_id, "patente": patente, "fecha": fecha, "geo": "1"})
    cruce = cruzar_entregas(fac.get("entregas") or [], paradas)
    return {"success": True, "patente": patente, "fecha": fecha, "salio": fac.get("salio") is not False, "desde": fac.get("desde"), "hasta": fac.get("hasta"),
            "total_facturas": fac.get("total") or 0, "umbrales": {"calza_m": CALZA_M, "cerca_m": CERCA_M}, **cruce}
