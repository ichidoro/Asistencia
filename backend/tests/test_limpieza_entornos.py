"""Guardián de la limpieza del 15-11-2026: que no vuelvan restos del desarrollo a lo que se publica.

- Una página de prueba (frontend/__e.html) se servía en producción a cualquiera.
- El mapa fuente del Dashboard dejaba ver su código.
- El registro de la app llegó a 614 MB sin cortarse y, ante un error, escribía los valores de las variables.
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FRONT = RAIZ / "frontend"

# Las únicas páginas HTML que sirve la aplicación (agregar aquí una página nueva de verdad)
PAGINAS_PUBLICADAS = {"index.html", "login.html", "manual_choferes_180h.html", "whatsapp.html"}


def test_solo_se_publican_las_paginas_de_la_aplicacion():
    sobrantes = sorted(p.name for p in FRONT.glob("*.html") if p.name not in PAGINAS_PUBLICADAS)
    assert sobrantes == [], f"páginas que no son de la aplicación en frontend/: {sobrantes}"


def test_sin_mapa_fuente_del_dashboard():
    assert not list((FRONT / "js").glob("*.map")), "hay un mapa fuente (.map) en frontend/js"
    assert "sourceMappingURL" not in (FRONT / "js" / "dashboard_react.js").read_text(encoding="utf-8")
    assert re.search(r"sourcemap:\s*false", (RAIZ / "dashboard_build" / "vite.config.js").read_text(encoding="utf-8"))


def test_registro_se_corta_y_no_escribe_variables():
    main = (RAIZ / "backend" / "main.py").read_text(encoding="utf-8")
    assert "diagnose=False" in main and "diagnose=True" not in main
    assert '"rotation": settings.LOG_ROTATION' in main and '"retention": settings.LOG_RETENTION' in main
