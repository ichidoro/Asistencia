# -*- coding: utf-8 -*-
"""El acta del cierre trae al menos lo mismo que la previsualización.

Decisión del dueño (23-10-2026), hallazgo 4 del análisis de cierres: el acta
solo listaba estados y HE aprobadas. Ahora el cálculo de haberes/débitos vive
en UN método (calcular_haberes_debitos) que usan la previsualización y el
acta, y el acta en PDF se descarga al sellar y desde los chips de «Áreas
cerradas» de Tramos de Cierre.
"""
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

RAIZ = Path(__file__).resolve().parents[2]


def _leer(rel):
    return (RAIZ / rel).read_text(encoding="utf-8")


def test_una_sola_logica_para_previsualizacion_y_acta():
    s = _leer("backend/services/cierre_service.py")
    assert "async def calcular_haberes_debitos" in s
    assert "resumen.update(await self.calcular_haberes_debitos(" in s, \
        "la previsualización dejó de usar el cálculo compartido"
    r = _leer("backend/routers/cierre.py")
    assert "calcular_haberes_debitos" in r and '"haberes_debitos"' in r, \
        "el acta perdió los haberes/débitos"


def test_el_acta_pdf_existe_y_tiene_sus_secciones():
    js = _leer("frontend/js/marcaciones_ui.js")
    assert "descargarActaCierre" in js
    for frase in (
        "ACTA DE CIERRE DE PERÍODO",
        "Haberes (HE al 50 %)",
        "TOTAL HABERES",
        "Débitos (tiempo no trabajado, al 100 %)",
        "Otros (jornadas incompletas sin categoría)",
        "Déficit Bolsa Flexible (definitivo)",
        "TOTAL DÉBITOS",
        "HE usadas para compensar inasistencias",
        "Espera usada (tope 88 h por persona)",
        "BALANCE OPERATIVO (haberes − débitos − compensaciones)",
        "tramo en curso: el déficit aún no es exigible",
        "Descargar acta (PDF)",
    ):
        assert frase in js, f"el acta perdió la sección: {frase!r}"
    cfg = _leer("frontend/js/configuracion_ui.js")
    assert "descargarActaCierre" in cfg, \
        "los chips de Áreas cerradas ya no descargan el acta"


def test_los_textos_sobreviven_al_minificador():
    import pytest
    rjsmin = pytest.importorskip("rjsmin")
    m = rjsmin.jsmin(_leer("frontend/js/marcaciones_ui.js"))
    for frase in ("ACTA DE CIERRE DE PERÍODO", "TOTAL HABERES",
                  "BALANCE OPERATIVO (haberes − débitos − compensaciones)",
                  "tramo en curso: el déficit aún no es exigible"):
        assert frase in m, f"el minificador rompe el texto: {frase!r}"
