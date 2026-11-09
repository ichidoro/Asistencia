# -*- coding: utf-8 -*-
"""Resumen del cierre: la línea «otros» del tiempo perdido y las compensaciones.

Decisión del dueño (23-10-2026), hallazgos 2 y 3 del análisis del módulo de
cierres: el desglose de débitos no sumaba el total (Log. Tradicional 25,68 de
26,47 h; Producción 65,15 de 70,14 h) y las compensaciones HE↔inasistencia no
entraban al resumen aunque la grilla y el Excel sí las restan del saldo.
"""
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

RAIZ = Path(__file__).resolve().parents[2]


def _leer(rel):
    return (RAIZ / rel).read_text(encoding="utf-8")


def test_el_resumen_entrega_otros_y_compensaciones():
    s = _leer("backend/services/cierre_service.py")
    assert "deuda_otros_horas" in s, "el resumen perdió la línea «otros» del tiempo perdido"
    assert "compensaciones_horas" in s, "el resumen perdió las compensaciones"
    assert "minutos_compensados_he" in s, "el resumen ya no lee las compensaciones de los días"
    # El balance descuenta las compensaciones, igual que el Saldo Neto del Excel
    assert "he_total_hrs - deuda_total_hrs - compensaciones_hrs" in s
    # «Otros» es el total menos lo clasificado, nunca negativo
    assert "max(0.0, total_deuda_fijos_min - clasificada_min)" in s


def test_la_pantalla_del_cierre_muestra_ambas_lineas():
    # Desde el 09-11-2026 (decisión del dueño) el paso 5 del cierre es el «Resumen antes de sellar» (propuesta A):
    # lo dibuja cargarResumenCierre con /api/cierre/resumen, las mismas cifras del informe PDF.
    srv = _leer("backend/services/informe_cierre_pdf.py")
    assert "['Otros', T('otros')]" in srv, "el resumen antes de sellar perdió la fila «otros»"
    assert "'Inasistencias compensadas'" in srv and "'Compensan inasistencias'" in srv, \
        "el resumen antes de sellar perdió las compensaciones"
    js = _leer("frontend/js/marcaciones_ui.js")
    assert "window.cargarResumenCierre = async function" in js


def test_los_textos_sobreviven_al_minificador():
    import pytest
    rjsmin = pytest.importorskip("rjsmin")
    m = rjsmin.jsmin(_leer("frontend/js/marcaciones_ui.js"))
    for frase in ("Lo que se va a cargar en remuneraciones", "Calculando el resumen del área…"):
        assert frase in m, f"el minificador rompe el texto: {frase!r}"
