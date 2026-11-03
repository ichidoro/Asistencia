# -*- coding: utf-8 -*-
"""La espera de la Bolsa Flexible se muestra como tope, no como meta.

Decisión del dueño (23-10-2026), hallazgo 5 del análisis de cierres: las 88 h
de espera son un máximo legal; la grilla mostraba «balance −88:00» en ámbar
como si faltaran horas. El exceso sobre el tope se explica como horas extra.
Desde el 03-11-2026 (diseño C elegido por el dueño) la espera es una sola columna
«USO DEL TOPE» («2:15 de 88:00 · 3 %», barra y cuánto le queda antes del tope) y la
bolsa, «AVANCE DEL CICLO» (con la raya de lo esperado a hoy).
"""
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

RAIZ = Path(__file__).resolve().parents[2]
JS = (RAIZ / "frontend/js/marcaciones_ui.js").read_text(encoding="utf-8")


def test_la_espera_es_uso_del_tope_y_la_bolsa_avance_del_ciclo():
    assert ">USO DEL TOPE</th>" in JS, "la grilla perdió la columna USO DEL TOPE de la espera"
    assert ">AVANCE DEL CICLO</th>" in JS, "la grilla perdió la columna AVANCE DEL CICLO de la bolsa"
    assert "Esperado a hoy" in JS and "mx-av-marca" in JS
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
        " antes del tope",
        "le quedan ",
        "superó el tope: ",
        " sobre lo esperado",
        "le faltan ",
        " para ir al día",
        "faltaron ",
        " como HE)",
    ):
        assert frase in m, f"el minificador rompe el texto: {frase!r}"
