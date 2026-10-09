"""Minificado en caliente de JS/CSS propios (sin paso de build).

Solo quita comentarios y espacios: no renombra variables ni reordena nada, así que el comportamiento
no cambia. El resultado se cachea en memoria por (ruta, mtime, tamaño). Si algo falla, se sirve el
archivo original. Se desactiva con MINIFY_STATIC=0.

JS: usa `rjsmin` si está instalado (pip install rjsmin); si no, se sirve sin minificar.
CSS: minificador propio y conservador (respeta cadenas y url()).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

try:  # opcional
    import rjsmin as _rjsmin
except Exception:  # pragma: no cover
    _rjsmin = None

HABILITADO = os.environ.get("MINIFY_STATIC", "1") != "0"

_CACHE: dict[tuple, bytes] = {}

# Cadenas y url(...) se protegen antes de tocar espacios.
_TOKENS_CSS = re.compile(
    r'''(?P<c>/\*.*?\*/)|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|url\(\s*[^)'"]*\s*\)''', re.S
)


def minificar_css(css: str) -> str:
    guardados: list[str] = []

    # Una sola pasada, de izquierda a derecha: así un apóstrofe dentro de un comentario
    # no se confunde con el inicio de una cadena (ni "/*" dentro de una cadena con un comentario).
    def _token(m: re.Match) -> str:
        if m.group("c") is not None:
            return ""
        guardados.append(m.group(0))
        return f"\x00{len(guardados) - 1}\x00"

    s = _TOKENS_CSS.sub(_token, css)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r" ?([{};,>]) ?", r"\1", s)
    s = s.replace(";}", "}").strip()
    return re.sub(r"\x00(\d+)\x00", lambda m: guardados[int(m.group(1))], s)


def minificar_js(js: str) -> str:
    if _rjsmin is None:
        return js
    return _rjsmin.jsmin(js)


def _es_minificable(ruta: str) -> bool:
    r = ruta.lower().replace("\\", "/")
    if ".min." in r or r.startswith("js/libs/"):
        return False
    return r.endswith((".js", ".css"))


def contenido_minificado(path: Path, ruta_rel: str) -> bytes | None:
    """Devuelve el archivo minificado (bytes) o None si no corresponde / falla."""
    if not HABILITADO or not _es_minificable(ruta_rel):
        return None
    try:
        st = path.stat()
        clave = (str(path), st.st_mtime_ns, st.st_size)
        hit = _CACHE.get(clave)
        if hit is not None:
            return hit
        texto = path.read_text(encoding="utf-8")
        if "sourceMappingURL" in texto[-300:]:
            return None  # ya viene compilado con su source map: no tocarlo
        if ruta_rel.lower().endswith(".css"):
            out = minificar_css(texto)
        else:
            if _rjsmin is None:
                return None
            out = minificar_js(texto)
        datos = out.encode("utf-8")
        # Limpia versiones viejas del mismo archivo
        for k in [k for k in _CACHE if k[0] == clave[0]]:
            _CACHE.pop(k, None)
        _CACHE[clave] = datos
        return datos
    except Exception:
        return None


def bundle_css(raiz: Path, archivos: list[str]) -> bytes | None:
    """Une varios CSS (en orden) en uno solo, ya minificado. None si falta alguno."""
    try:
        partes = []
        firma = []
        for rel in archivos:
            p = raiz / rel
            st = p.stat()
            firma.append((rel, st.st_mtime_ns, st.st_size))
        clave = ("bundle", tuple(firma))
        hit = _CACHE.get(clave)
        if hit is not None:
            return hit
        for rel in archivos:
            t = (raiz / rel).read_text(encoding="utf-8")
            partes.append(minificar_css(t) if HABILITADO else t)
        datos = "\n".join(partes).encode("utf-8")
        for k in [k for k in _CACHE if k and k[0] == "bundle"]:
            _CACHE.pop(k, None)
        _CACHE[clave] = datos
        return datos
    except Exception:
        return None
