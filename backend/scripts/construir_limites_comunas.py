"""Arma backend/services/comunas_limites.json: los límites de las comunas (de Coquimbo a La Araucanía) con su CUT, simplificados (~40 m) y con 4 decimales.

Fuente: Biblioteca del Congreso Nacional (mapas vectoriales), en la versión GeoJSON de https://github.com/jlhonora/geo. Uso: python backend/scripts/construir_limites_comunas.py
El resultado se commitea (pesa poco); este script solo hace falta si se quiere regenerar.
"""
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/jlhonora/geo/master/"
REGIONES = ["region_de_coquimbo", "region_de_valparaiso", "region_metropolitana_de_santiago", "region_del_libertador_bernardo_o'higgins", "region_del_maule", "region_del_bio-bio", "region_de_la_araucania"]
TOLERANCIA = 0.0004   # grados (~40 m)


def norm(t: str) -> str:
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower().replace("'", "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


def simplificar(pts, tol):
    """Ramer-Douglas-Peucker iterativo."""
    if len(pts) < 5:
        return pts
    marca = [False] * len(pts)
    marca[0] = marca[-1] = True
    pila = [(0, len(pts) - 1)]
    while pila:
        a, b = pila.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        n2 = dx * dx + dy * dy
        mejor, idx = -1.0, -1
        for i in range(a + 1, b):
            x0, y0 = pts[i]
            if n2 == 0:
                d = (x0 - x1) ** 2 + (y0 - y1) ** 2
            else:
                t = max(0.0, min(1.0, ((x0 - x1) * dx + (y0 - y1) * dy) / n2))
                d = (x0 - (x1 + t * dx)) ** 2 + (y0 - (y1 + t * dy)) ** 2
            if d > mejor:
                mejor, idx = d, i
        if mejor > tol * tol:
            marca[idx] = True
            pila.append((a, idx))
            pila.append((idx, b))
    return [p for p, m in zip(pts, marca) if m]


def anillos(g):
    """Lista de polígonos; cada uno = [anillo exterior, huecos...]."""
    return g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]


salida = []
for reg in REGIONES:
    url = BASE + urllib.parse.quote(reg) + "/all.geojson"
    d = json.loads(urllib.request.urlopen(url, timeout=120).read().decode("utf8"))
    for f in d["features"]:
        pr = f["properties"]
        polys = []
        for poly in anillos(f["geometry"]):
            rings = []
            for ring in poly:
                s = simplificar([(x, y) for x, y in ring], TOLERANCIA)
                if len(s) >= 4:
                    rings.append([[round(x, 4), round(y, 4)] for x, y in s])
            if rings:
                polys.append(rings)
        if not polys:
            continue
        xs = [p[0] for poly in polys for p in poly[0]]
        ys = [p[1] for poly in polys for p in poly[0]]
        salida.append({"cut": str(pr["COD_COMUNA"]).zfill(5), "n": pr["NOM_COM"], "k": norm(pr["NOM_COM"]), "bbox": [min(xs), min(ys), max(xs), max(ys)], "polys": polys})
    print(reg, "->", len(d["features"]), "comunas")
destino = Path(__file__).resolve().parent.parent / "services" / "comunas_limites.json"
destino.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
print(len(salida), "comunas;", round(destino.stat().st_size / 1e6, 2), "MB ->", destino)
