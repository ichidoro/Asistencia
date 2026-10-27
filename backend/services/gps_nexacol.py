"""
Ruta GPS de los camiones, leída de Nexacol (modelo Logística → Ruta GPS), para compararla con la libreta 180h.
Nexacol (rutas /api/reports/camiones-gps-*, sin cambios en Nexacol) entrega los puntos del día (ya sin lo que pasa dentro de la planta) y las paradas; acá se reduce el día a 96 tramos de 15 minutos
(igual que la libreta) para que la pantalla los pueda comparar tramo a tramo.
"""
import asyncio
from typing import Any, Dict, List, Optional

import aiohttp

from backend.core.config import settings
from backend.services import comunas_geo

SLOT_SEG = 900          # 15 minutos
VEL_MOVIENDO = 3        # km/h: bajo esto el camión está detenido (misma regla de Nexacol)
HUECO_MAX = 15 * 60     # sin reportar más que esto mientras se mueve: no hay dato

SIN_DATO, MOVIMIENTO, DETENIDO = 0, 1, 2
PARADA_MIN_ASISTENCIA = 3   # minutos detenido para contar como parada (Nexacol usa 5; una entrega suele durar menos)


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


def tramos_movimiento(puntos: List[Dict[str, Any]]) -> List[List[int]]:
    """[[desde_s, hasta_s], ...]: los tramos del día en que el camión andaba (segundos desde las 00:00), uno por cada recorrido entre paradas. Cada segmento entre
    dos reportes cuenta si el primero iba a más de VEL_MOVIENDO y no hay un hueco sin reportes de más de HUECO_MAX. Los de menos de 2 min (un tironeo en una cola)
    no se dibujan. Las paradas empiezan en el primer reporte detenido, donde termina el tramo: no se solapan."""
    pts = sorted(((p["s"], p["v"]) for p in puntos if isinstance(p.get("s"), (int, float)) and isinstance(p.get("v"), (int, float))), key=lambda t: t[0])
    out: List[List[int]] = []
    for (s0, v0), (s1, _) in zip(pts, pts[1:]):
        if v0 > VEL_MOVIENDO and 0 < s1 - s0 <= HUECO_MAX:
            if out and s0 - out[-1][1] <= 1:
                out[-1][1] = int(s1)
            else:
                out.append([int(s0), int(s1)])
    return [t for t in out if t[1] - t[0] >= 120]


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
    data = await _get("/api/reports/camiones-gps-ruta", {"id": vehiculo_id, "fecha": fecha, "parada_min": str(PARADA_MIN_ASISTENCIA)})
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
        "planta": {k: (data.get("casaMatriz") or {}).get(src) for k, src in (("nombre", "nombre"), ("salidas", "salidas"))},
        "tramos_mov": tramos_movimiento(puntos),
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


_CORTE_CALLE = {"st", "sitio", "parcela", "lote", "km", "local", "depto", "dpto", "casa", "block", "nro", "numero", "sn"}
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
    nombre: List[str] = []
    for w in pal:
        if w.isdigit() or w in _CORTE_CALLE:   # el número de casa o el marcador de sitio: lo que sigue es sector o detalle, no la calle
            if nombre:
                break
            continue
        if len(w) >= 3 and w not in _ABREV_CALLE:
            nombre.append(w)
    return {"pares": pares, "nombre": nombre}


def _tokens_calle(calle: Any) -> List[str]:
    return _identificadores_calle(calle)["nombre"]


def _coincide(ident: Dict[str, List[str]], palabras: Any, pares: Any) -> List[str]:
    """Las calles de la dirección que aparecen en la parada ([] si ninguna). Una esquina ("14 Norte con 6 Oriente") puede coincidir con una sola de sus dos calles."""
    if ident["pares"]:
        return [p for p in ident["pares"] if p in pares]
    return list(ident["nombre"]) if ident["nombre"] and all(t in palabras for t in ident["nombre"]) else []


def _metros(la1: float, lo1: float, la2: float, lo2: float) -> float:
    from math import asin, cos, radians, sin, sqrt
    dla, dlo = radians(la2 - la1), radians(lo2 - lo1)
    h = sin(dla / 2) ** 2 + cos(radians(la1)) * cos(radians(la2)) * sin(dlo / 2) ** 2
    return 2 * 6371000 * asin(sqrt(h))


def cruzar_entregas(entregas: List[Dict[str, Any]], paradas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Para cada entrega, la parada que le corresponde y su estado; y para cada parada, la entrega a la que corresponde.
    Estados: calza (con coordenada exacta, la parada queda a ≤ CALZA_M) · cercana (con coordenada, ≤ CERCA_M) · calle (la calle y la comuna de la factura
    están en la dirección de una parada: es la MISMA CALLE, pero el GPS no da el número ni la cuadra; en una esquina puede coincidir solo una de las dos calles)
    · comuna (el camión paró en esa comuna, pero NO se sabe en cuál de esas paradas: no se elige ninguna) · lejos (con coordenada, a más de CERCA_M de
    toda parada) · sin_parada (el camión no paró en esa comuna)."""
    def num(v: Any) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    ps = []
    for i, p in enumerate(paradas):
        pal = _palabras(p.get("lugar"))
        pcut = comunas_geo.comuna_en(p["la"], p["lo"]) if isinstance(p.get("la"), (int, float)) and isinstance(p.get("lo"), (int, float)) else None
        ps.append((i, p, set(pal), {f"{a} {b}" for a, b in zip(pal, pal[1:])}, pcut))
    items: List[Dict[str, Any]] = []
    for e in entregas:
        item = {"cliente": e.get("cliente"), "calle": e.get("calle"), "comuna": e.get("comuna"), "folios": e.get("folios") or [], "kilos": e.get("kilos"),
                "exacto": bool(e.get("exacto")), "estado": "sin_parada", "via": None, "dist_m": None, "parada": None, "parada_idx": None, "paradas_comuna": [], "coincide": [], "esquina": False, "aprendida": int(e.get("aprendida") or 0), "candidatos": 0, "comuna_la": e.get("comunaLat"), "comuna_lo": e.get("comunaLon")}
        # La comuna y la calle se comparan por palabras ("San Francisco Mostazal" calza con "San Francisco de Mostazal")
        comuna = [w for w in _norm(e.get("comuna")).split() if w not in _ARTICULOS]
        ident = _identificadores_calle(e.get("calle"))
        cut_e = comunas_geo.cut_de_nombre(e.get("comuna"))   # CUT de la comuna (o localidad) de la factura
        item["esquina"] = len(ident["pares"]) >= 2
        # Una parada es de la comuna de la factura si el texto de su dirección la nombra O si el punto cae dentro de sus límites (polígono)
        def de_la_comuna(pal: Any, pcut: Any) -> bool:
            return bool((comuna and all(w in pal for w in comuna)) or (cut_e and pcut == cut_e))
        en_comuna = [(i, p) for i, p, pal, _, pcut in ps if de_la_comuna(pal, pcut)]
        # Si varias paradas coinciden en calle y comuna, la que corresponde a una entrega es la que coincide con más calles y, luego, la más larga
        # (candidatas: cuántas paradas coinciden en calle y comuna; el aprendizaje de ubicaciones solo usa las entregas con una única candidata)
        en_calle = sorted(((i, p, c) for i, p, pal, pares, pcut in ps if de_la_comuna(pal, pcut) for c in [_coincide(ident, pal, pares)] if c), key=lambda t: (-len(t[2]), -(t[1].get("min") or 0)))
        item["candidatos"] = len(en_calle)
        # con coordenada guardada: distancia a la parada más cercana
        con_coord = num(e.get("lat")) and num(e.get("lon"))
        near = min(((_metros(e["lat"], e["lon"], q["la"], q["lo"]), i, q) for i, q, _, _, _ in ps if num(q.get("la")) and num(q.get("lo"))), key=lambda t: t[0], default=None) if con_coord else None
        elegida = None
        if near and item["exacto"] and near[0] <= CALZA_M:
            item["estado"], item["via"], elegida = "calza", "distancia", (near[1], near[2])
        elif en_calle:
            item["estado"], item["via"], elegida = "calle", "direccion", (en_calle[0][0], en_calle[0][1])
            item["coincide"] = en_calle[0][2]
        elif near and item["exacto"] and near[0] <= CERCA_M:
            item["estado"], item["via"], elegida = "cercana", "distancia", (near[1], near[2])
        elif en_comuna:
            # Solo se sabe que el camión paró en esa comuna: no se asigna ninguna parada (sería inventar cuál)
            item["estado"], item["via"] = "comuna", "comuna"
            item["paradas_comuna"] = [{k: p.get(k) for k in ("desde", "hasta", "min")} for _, p in en_comuna]
            if len(en_comuna) == 1:   # una sola parada en esa comuna: se muestra (sin marcarla en la línea de tiempo: solo coincide la comuna)
                item["parada_idx"], item["parada"] = en_comuna[0][0], {k: en_comuna[0][1].get(k) for k in ("desde", "hasta", "min", "lugar")}
        elif near and item["exacto"]:
            item["estado"], item["via"], elegida = "lejos", "distancia", (near[1], near[2])
        if near:
            item["dist_m"] = round(near[0]) if item["exacto"] else None
        if elegida:
            item["parada_idx"] = elegida[0]
            item["parada"] = {k: elegida[1].get(k) for k in ("desde", "hasta", "min", "lugar", "la", "lo")}
        items.append(item)
    # Cada parada con la entrega que le corresponde (la de mejor estado)
    peso = {"calza": 3, "calle": 2, "cercana": 1}
    por_parada: List[Any] = [None] * len(paradas)
    for it in items:
        k = it["parada_idx"]
        if k is not None and it["estado"] in peso and (por_parada[k] is None or peso[it["estado"]] > peso[por_parada[k]["estado"]]):
            por_parada[k] = {"cliente": it["cliente"], "dist_m": it["dist_m"], "estado": it["estado"], "via": it["via"]}
    cuenta = {k: sum(1 for it in items if it["estado"] == k) for k in ("calza", "calle", "cercana", "comuna", "lejos", "sin_parada")}
    return {"entregas": items, "paradas": por_parada, "resumen": {"total": len(items), **cuenta}}


RADIO_COMUNA_KM = 12   # una calle recorrida cuenta como de la comuna de la factura si queda a menos de esto del centro de la comuna...
_COMUNAS: List[Dict[str, Any]] = []   # ...o si esa comuna es una de las 2 más cercanas (por su centro) al punto: así las comunas grandes no se quedan fuera. Tabla con CUT, de Nexacol.


def _comunas_cercanas(la: float, lo: float, k: int = 2) -> List[str]:
    """Nombres normalizados de las k comunas cuyo centro queda más cerca del punto."""
    global _COMUNAS
    if not _COMUNAS:
        import json
        import os
        try:
            with open(os.path.join(os.path.dirname(__file__), "comunas_cut.json"), encoding="utf8") as f:
                _COMUNAS = json.load(f)
        except Exception:
            _COMUNAS = [{"k": "", "la": 0.0, "lo": 0.0}]
    return [c["k"] for c in sorted(_COMUNAS, key=lambda c: _metros(la, lo, c["la"], c["lo"]))[:k]]


def _hm(s: Any) -> str:
    s = int(s)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}"


def pasos_por_direccion(entregas: List[Dict[str, Any]], pasos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """¿El camión PASÓ por la calle de cada factura, aunque no se detuviera? Se compara el nombre de la calle de la factura con las calles por las que anduvo
    (nombres de OpenStreetMap, con la hora). Para no confundir calles de igual nombre de otra ciudad, la calle recorrida debe quedar a menos de RADIO_COMUNA_KM del
    centro de la comuna de la factura. En una dirección de esquina se dice además si pasó por las dos calles casi seguidas (es decir, por la esquina).
    Devuelve, por entrega: {"estado": "paso" | "no_paso", "pasadas": [{"nombre", "desde", "hasta"}], "esquina": bool, "coincide": [...]}.
    «no_paso» = no se detectó: el ajuste del recorrido a las calles puede dejar tramos sin emparejar."""
    def num(v: Any) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    pn = []
    for q in pasos:
        pal = _palabras(q.get("nombre"))
        pn.append((q, set(pal), {f"{a} {b}" for a, b in zip(pal, pal[1:])}))
    out: List[Dict[str, Any]] = []
    for e in entregas:
        ident = _identificadores_calle(e.get("calle"))
        cut_e = comunas_geo.cut_de_nombre(e.get("comuna"))
        res: Dict[str, Any] = {"estado": "no_paso", "pasadas": [], "esquina": False, "coincide": []}
        hallados = []
        for q, pal, pares in pn:
            c = _coincide(ident, pal, pares)
            if not c:
                continue
            cut_q = comunas_geo.comuna_en(q["la"], q["lo"]) if cut_e and num(q.get("la")) and num(q.get("lo")) else None
            if cut_e and cut_q:
                if cut_q != cut_e:
                    continue   # la calle recorrida queda en otra comuna (por polígono): es una calle de igual nombre de otro lugar
            elif num(e.get("comuna_la")) and num(e.get("comuna_lo")) and num(q.get("la")) and num(q.get("lo")):
                lejos = _metros(q["la"], q["lo"], e["comuna_la"], e["comuna_lo"]) > RADIO_COMUNA_KM * 1000
                if lejos and _norm(e.get("comuna")) not in _comunas_cercanas(q["la"], q["lo"]):
                    continue
            hallados.append((q, c))
        if hallados:
            res["estado"] = "paso"
            res["pasadas"] = [{"nombre": q.get("nombre"), "desde": _hm(q["desde"]), "hasta": _hm(q["hasta"])} for q, _ in hallados[:4]]
            res["coincide"] = sorted({x for _, c in hallados for x in c})
            if len(ident["pares"]) >= 2:
                por_par = [[q for q, c in hallados if par in c] for par in ident["pares"]]
                res["esquina"] = any(abs(a["desde"] - b["desde"]) <= 600 for a in por_par[0] for b in por_par[1]) if all(por_par[:2]) else False
        out.append(res)
    return out


def paso_coherente(item: Dict[str, Any], paso: Dict[str, Any]) -> Dict[str, Any]:
    """Si el camión PARÓ en la calle de la factura (misma calle, o a ≤ CALZA_M de la dirección), obviamente pasó por ella: la parada es la prueba, aunque el ajuste del
    recorrido a las calles no haya emparejado ese tramo. Sin esto salía «misma calle» junto a «no se detectó que pasara», una contradicción."""
    if paso.get("estado") == "paso" or item.get("estado") not in ("calza", "calle") or not item.get("parada"):
        return paso
    par = item["parada"]
    return {"estado": "paso", "origen": "parada", "esquina": False, "coincide": item.get("coincide") or [],
            "pasadas": [{"nombre": "", "desde": str(par.get("desde") or "")[:5], "hasta": str(par.get("hasta") or "")[:5]}]}


UMBRAL_APRENDIDA_M = 120   # dos días distintos que paran a menos de esto confirman dónde está el cliente


def clave_entrega(e: Dict[str, Any]) -> str:
    """Cliente + dirección de envío, normalizados: identifica un destino de entrega."""
    return "|".join(_norm(e.get(k)) for k in ("cliente", "calle", "comuna"))


def consolidar_ubicacion(obs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """La ubicación confirmada de un cliente: el mayor grupo de paradas de DÍAS DISTINTOS que quedan a menos de UMBRAL_APRENDIDA_M entre sí (mínimo 2 días).
    Una sola visita, o visitas que no coinciden, no confirman nada."""
    mejor = None
    for c in obs:
        grupo = [o for o in obs if _metros(c["la"], c["lo"], o["la"], o["lo"]) <= UMBRAL_APRENDIDA_M]
        dias = {o["fecha"] for o in grupo}
        if len(dias) >= 2 and (mejor is None or len(dias) > mejor[0]):
            mejor = (len(dias), grupo)
    if not mejor:
        return None
    g = mejor[1]
    return {"la": sum(o["la"] for o in g) / len(g), "lo": sum(o["lo"] for o in g) / len(g), "n": mejor[0]}


def observaciones_de(items: List[Dict[str, Any]], fecha: str, patente: str) -> List[Dict[str, Any]]:
    """Dónde paró el camión para cada entrega que se pudo atribuir a UNA sola parada (misma calle y comuna, sin ambigüedad) y cuya ubicación aún no se conoce."""
    out = []
    for it in items:
        par = it.get("parada") or {}
        if it.get("estado") == "calle" and it.get("candidatos") == 1 and not it.get("aprendida") and isinstance(par.get("la"), (int, float)) and isinstance(par.get("lo"), (int, float)):
            out.append({"clave": clave_entrega(it), "fecha": fecha, "cliente": it.get("cliente"), "calle": it.get("calle"), "comuna": it.get("comuna"),
                        "patente": patente, "la": par["la"], "lo": par["lo"], "min": par.get("min")})
    return out


async def entregas_dia(vehiculo_id: str, fecha: str, aprendidas_fn: Any = None, con_pasos: bool = True) -> Dict[str, Any]:
    ruta = await _get("/api/reports/camiones-gps-ruta", {"id": vehiculo_id, "fecha": fecha, "parada_min": str(PARADA_MIN_ASISTENCIA)})
    patente = str((ruta.get("vehiculo") or {}).get("patente") or "")
    paradas = (ruta.get("resumen") or {}).get("paradas") or []
    fac = await _get("/api/reports/camiones-gps-facturas", {"id": vehiculo_id, "patente": patente, "fecha": fecha, "geo": "1"})
    entregas = fac.get("entregas") or []
    # Direcciones cuya ubicación ya se aprendió de visitas anteriores: la entrega se mide en metros contra las paradas
    if aprendidas_fn:
        try:
            ap = await aprendidas_fn([clave_entrega(e) for e in entregas])
            for e in entregas:
                u = ap.get(clave_entrega(e))
                if u and not (e.get("lat") is not None and e.get("exacto")):
                    e["lat"], e["lon"], e["exacto"], e["aprendida"] = u["la"], u["lo"], True, u["n"]
        except Exception:
            pass   # sin la tabla de ubicaciones, simplemente se compara por nombre
    cruce = cruzar_entregas(entregas, paradas)
    # ¿Pasó por la calle de cada factura? (si esta consulta falla, la pantalla simplemente no muestra esa línea)
    try:
        if not con_pasos:
            raise GpsNexacolError(0, "sin pasos")
        calles = await _get("/api/reports/camiones-gps-calles-recorridas", {"id": vehiculo_id, "fecha": fecha})
        for it, paso in zip(cruce["entregas"], pasos_por_direccion(cruce["entregas"], calles.get("pasos") or [])):
            it["paso"] = paso_coherente(it, paso)
    except GpsNexacolError:
        pass
    return {"success": True, "patente": patente, "fecha": fecha, "salio": fac.get("salio") is not False, "desde": fac.get("desde"), "hasta": fac.get("hasta"),
            "total_facturas": fac.get("total") or 0, "umbrales": {"calza_m": CALZA_M, "cerca_m": CERCA_M}, **cruce,
            "observaciones": observaciones_de(cruce["entregas"], fecha, patente)}
