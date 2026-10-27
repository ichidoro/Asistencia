"""Comunas de Chile por polígono: ¿en qué comuna cae un punto? y ¿cuál es el CUT de una comuna (o localidad) escrita en una factura?

Los límites (comunas_limites.json, de Coquimbo a La Araucanía) vienen de la Mapoteca del SIIT de la Biblioteca del Congreso Nacional (mapas vectoriales, referenciales; en la versión GeoJSON
de https://github.com/jlhonora/geo), simplificados a ~40 m con backend/scripts/construir_limites_comunas.py. Fuente: Biblioteca del Congreso Nacional de Chile.
Los nombres se llevan al CUT con la tabla de Nexacol (comunas_cut.json), que incluye localidades que las facturas usan como «comuna» (p. ej. Sarmiento = comuna de Curicó, 07301).
"""
import json
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

_ARTICULOS = {"de", "del", "la", "las", "los", "el", "y"}
_LIMITES: List[Dict[str, Any]] = []
_NOMBRES: Dict[str, str] = {}
_LISTO = False


def _norm(t: Any) -> str:
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower().replace("'", "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


def _palabras(t: Any) -> Tuple[str, ...]:
    return tuple(w for w in _norm(t).split() if w not in _ARTICULOS)


def _cargar() -> None:
    global _LIMITES, _NOMBRES, _LISTO
    if _LISTO:
        return
    _LISTO = True
    aqui = os.path.dirname(__file__)
    try:
        with open(os.path.join(aqui, "comunas_limites.json"), encoding="utf8") as f:
            _LIMITES = json.load(f)
    except Exception:
        _LIMITES = []
    for c in _LIMITES:
        _NOMBRES.setdefault(" ".join(_palabras(c["n"])), c["cut"])
    try:
        with open(os.path.join(aqui, "comunas_cut.json"), encoding="utf8") as f:
            for c in json.load(f):
                _NOMBRES.setdefault(" ".join(_palabras(c["n"])), str(c["cut"]).zfill(5))
    except Exception:
        pass


def _dentro(lo: float, la: float, anillo: List[List[float]]) -> bool:
    """Rayo horizontal: ¿el punto (lo, la) está dentro del anillo?"""
    dentro = False
    j = len(anillo) - 1
    for i in range(len(anillo)):
        xi, yi = anillo[i]
        xj, yj = anillo[j]
        if (yi > la) != (yj > la) and lo < (xj - xi) * (la - yi) / ((yj - yi) or 1e-12) + xi:
            dentro = not dentro
        j = i
    return dentro


def comuna_en(la: float, lo: float) -> Optional[str]:
    """CUT (5 dígitos) de la comuna en que cae el punto, o None si queda fuera de los límites cargados."""
    _cargar()
    for c in _LIMITES:
        x0, y0, x1, y1 = c["bbox"]
        if not (x0 <= lo <= x1 and y0 <= la <= y1):
            continue
        for poly in c["polys"]:
            if _dentro(lo, la, poly[0]) and not any(_dentro(lo, la, h) for h in poly[1:]):
                return c["cut"]
    return None


def cut_de_nombre(nombre: Any) -> Optional[str]:
    """CUT de una comuna o localidad escrita como en una factura («San Francisco Mostazal», «Sarmiento»); None si no se reconoce."""
    _cargar()
    pal = _palabras(nombre)
    if not pal:
        return None
    clave = " ".join(pal)
    if clave in _NOMBRES:
        return _NOMBRES[clave]
    # una contiene a la otra palabra por palabra (p. ej. «san francisco mostazal» y «mostazal»): solo si es una única comuna
    s = set(pal)
    cuts = {cut for k, cut in _NOMBRES.items() if k and (s >= set(k.split()) or set(k.split()) >= s) and len(s & set(k.split())) >= 1 and len(set(k.split())) >= 1}
    return next(iter(cuts)) if len(cuts) == 1 else None
