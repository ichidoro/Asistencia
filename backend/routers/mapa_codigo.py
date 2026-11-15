"""
Configuración → Mapa del código (dueño, 15-11-2026): el grafo de graphify, solo para el súper administrador.

Los archivos los publica `scripts/publicar_mapa.py` en `backend/mapa_codigo/` (no van en /static, que es público). Además
del mapa, la pantalla dice de cuándo es y cuántos archivos del código cambiaron después de armarlo: así se sabe si está al día.
"""
import hashlib
import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse

from backend.core.security import RequirePermission, SecurityContext

router = APIRouter(prefix="/configuracion/mapa-codigo", tags=["Mapa del código"])

CARPETA = Path(__file__).resolve().parents[1] / "mapa_codigo"
RAIZ = Path(__file__).resolve().parents[2]


def _solo_super(user: SecurityContext) -> None:
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="El mapa del código es solo para el súper administrador.")


def _huella(ruta: Path) -> str:
    return hashlib.md5(ruta.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def estado_del_mapa(carpeta: Path = CARPETA, raiz: Path = RAIZ) -> Dict[str, Any]:
    """De cuándo es el mapa y qué archivos del código cambiaron o desaparecieron después de armarlo."""
    meta_f = carpeta / "meta.json"
    if not meta_f.exists() or not (carpeta / "graph.html").exists():
        return {"publicado": False}
    meta = json.loads(meta_f.read_text(encoding="utf-8"))
    cambiados, borrados = [], []
    for rel, h in (meta.get("archivos") or {}).items():
        f = raiz / rel
        if not f.is_file():
            borrados.append(rel)
        elif _huella(f) != h:
            cambiados.append(rel)
    return {"publicado": True, "armado": meta.get("armado"), "publicado_en": meta.get("publicado"),
            "commit": meta.get("commit"), "archivos_comparados": len(meta.get("archivos") or {}),
            "archivos_leidos": meta.get("archivos_leidos"), "cambiados": sorted(cambiados), "borrados": sorted(borrados),
            "al_dia": not cambiados and not borrados}


@router.get("/estado/")
async def estado(current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))):
    _solo_super(current_user)
    return estado_del_mapa()


@router.get("/grafo/", response_class=HTMLResponse)
async def grafo(current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))):
    _solo_super(current_user)
    f = CARPETA / "graph.html"
    if not f.exists():
        raise HTTPException(status_code=404, detail="El mapa todavía no se publica.")
    return HTMLResponse(f.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


@router.get("/informe/", response_class=PlainTextResponse)
async def informe(current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))):
    _solo_super(current_user)
    f = CARPETA / "GRAPH_REPORT.md"
    if not f.exists():
        raise HTTPException(status_code=404, detail="El informe todavía no se publica.")
    return PlainTextResponse(f.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})
