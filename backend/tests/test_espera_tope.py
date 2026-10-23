# -*- coding: utf-8 -*-
"""La espera de la Bolsa Flexible se muestra como tope, no como meta.

Decisión del dueño (23-10-2026), hallazgo 5 del análisis de cierres: las 88 h
de espera son un máximo legal; la grilla mostraba «balance −88:00» en ámbar
como si faltaran horas. Ahora las columnas son TOPE / USADAS / USO (porcentaje
con barra) y el exceso sobre el tope se explica como horas extra.
"""
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

RAIZ = Path(__file__).resolve().parents[2]
JS = (RAIZ / "frontend/js/marcaciones_ui.js").read_text(encoding="utf-8")


def test_las_columnas_son_tope_usadas_uso():
    assert ">TOPE</th>" in JS and ">USADAS</th>" in JS and ">USO</th>" in JS, \
        "la grilla perdió las columnas TOPE / USADAS / USO de la espera"
    assert "Espera (tope 88h)" in JS
    # El balance negativo de espera no vuelve
    assert "Balance de espera" not in JS
    assert ">BALANCE</th>" not in JS.split("esperaHeadersSub")[1].split(": ''")[0], \
        "volvió la columna BALANCE a la espera"


def test_el_tope_se_explica_y_el_exceso_es_he():
    assert "Tope mensual de espera: " in JS
    assert "no una meta" in JS
    assert "se pagan como horas extra" in JS or "se paga como horas extra" in JS
    assert "Espera usada: " in JS  # tooltip «usadas X de Y»
    assert " como HE)" in JS       # el exceso del acumulado del tooltip


def test_los_textos_sobreviven_al_minificador():
    import pytest
    rjsmin = pytest.importorskip("rjsmin")
    m = rjsmin.jsmin(JS)
    for frase in (
        "Tope mensual de espera: ",
        "Es un máximo legal, no una meta: lo que pase del tope se paga como horas extra.",
        "Superó el tope: ",
        " se pagan como horas extra",
        "Espera usada: ",
        "Horas de espera usadas en el ciclo",
        " como HE)",
    ):
        assert frase in m, f"el minificador rompe el texto: {frase!r}"
