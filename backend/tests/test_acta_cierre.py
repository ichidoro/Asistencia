# -*- coding: utf-8 -*-
"""Haberes y débitos del cierre en un solo cálculo; el acta antigua ya no existe.

Decisión del dueño (23-10-2026): el cálculo de haberes/débitos vive en UN método (calcular_haberes_debitos) que usan
la previsualización del cierre y su resumen. Decisión del dueño (09-11-2026): el acta antigua (PDF armado en el
navegador desde /api/cierre/acta-resumen) se elimina; lo reemplaza el informe de cierre en PDF por tipo de horario
(ver test_informe_cierre_pdf.py).
"""
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

RAIZ = Path(__file__).resolve().parents[2]


def _leer(rel):
    return (RAIZ / rel).read_text(encoding="utf-8")


def test_una_sola_logica_para_la_previsualizacion():
    s = _leer("backend/services/cierre_service.py")
    assert "async def calcular_haberes_debitos" in s
    assert "resumen.update(await self.calcular_haberes_debitos(" in s, \
        "la previsualización dejó de usar el cálculo compartido"


def test_el_acta_antigua_ya_no_existe():
    js = _leer("frontend/js/marcaciones_ui.js")
    cfg = _leer("frontend/js/configuracion_ui.js")
    r = _leer("backend/routers/cierre.py")
    assert "descargarActaCierre" not in js and "descargarActaCierre" not in cfg
    assert "ACTA DE CIERRE DE PERÍODO" not in js
    assert "/acta-resumen" not in r and "/informe-pdf" in r
