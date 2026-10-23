# -*- coding: utf-8 -*-
"""El déficit de la Bolsa Flexible recién es deuda cuando termina el tramo.

Decisión del dueño (23-10-2026), hallazgo 6 del análisis de cierres: la
pre-evaluación a mitad de tramo mostraba «déficit −789,53 h» y un balance de
−777,73 h en Logística Tradicional, cuando la meta mensual todavía no era
exigible. Ahora, mientras el tramo corre, se informa como AVANCE; el déficit
aparece solo al evaluar un rango que llega al final de su tramo ya pasado.
El exceso sobre la meta sí cuenta siempre (solo puede crecer).
"""
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services.cierre_service import bolsa_es_definitiva  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]


def test_a_mitad_de_tramo_no_es_definitivo():
    # Caso real: rango 26-09 → 20-10 evaluado el 23-10; su tramo termina el 25-10
    assert bolsa_es_definitiva("2026-10-20", "2026-10-25", "2026-10-23") is False
    # Rango que incluye el día de hoy: tampoco
    assert bolsa_es_definitiva("2026-10-25", "2026-10-25", "2026-10-23") is False


def test_con_el_tramo_terminado_si_es_definitivo():
    # El tramo completo 26-09 → 25-10 evaluado el 26-10 (al sellar)
    assert bolsa_es_definitiva("2026-10-25", "2026-10-25", "2026-10-26") is True
    # Un rango histórico fuera de todo tramo también se evalúa como definitivo
    assert bolsa_es_definitiva("2026-04-20", None, "2026-10-23") is True


def test_el_resumen_y_la_pantalla_llevan_el_avance():
    s = (RAIZ / "backend/services/cierre_service.py").read_text(encoding="utf-8")
    assert "bolsa_definitiva" in s and "bolsa_dias_restantes" in s
    assert "bolsa_meta_total_horas" in s and "bolsa_acumulado_horas" in s
    assert "acum_bolsa < meta_min and bolsa_definitiva" in s, \
        "el déficit de bolsa volvió a contarse con el tramo corriendo"
    js = (RAIZ / "frontend/js/marcaciones_ui.js").read_text(encoding="utf-8")
    assert "bolsaAvanceHtml" in js and "bolsa_definitiva" in js
    assert "avance del tramo (" in js


def test_los_textos_sobreviven_al_minificador():
    import pytest
    rjsmin = pytest.importorskip("rjsmin")
    m = rjsmin.jsmin((RAIZ / "frontend/js/marcaciones_ui.js").read_text(encoding="utf-8"))
    for frase in (
        "Bolsa Flexible — avance del tramo (",
        " de ",
        " hrs de meta",
        " · faltan ",
        " días del tramo",
        "La meta es mensual: lo que falta aún no es deuda.",
    ):
        assert frase in m, f"el minificador rompe el texto: {frase!r}"
