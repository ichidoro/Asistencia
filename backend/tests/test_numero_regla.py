# -*- coding: utf-8 -*-
"""Número de cada regla («Regla N») guardado en la base, en el orden de la pantalla (pedido del dueño, 26-10-2026)."""
import os

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services.reglas_marcas_def import numerar_sin_numero  # noqa: E402

# Las 29 reglas de producción al 26-10-2026: (id, secuencia)
PRODUCCION = [(1, 'E'), (2, 'S'), (3, 'ES'), (4, 'ESES'), (5, 'ESESES'), (6, 'EE'), (7, 'SS'), (8, 'EEE'), (9, 'SSSS'),
              (10, 'ESS'), (11, 'EES'), (12, 'ESSS'), (13, 'EEES'), (14, 'SSES'), (15, 'ESEE'), (16, 'EESS'), (17, 'SSEE'),
              (18, 'ESESS'), (19, 'EESES'), (20, 'ESEES'), (21, 'ESSES'), (22, 'EESSS'), (23, 'ESSSS'), (24, 'EEEEES'),
              (25, 'ESEEES'), (26, 'ESESSS'), (27, 'SSESES'), (28, 'ESE'), (29, 'SES')]


def _reglas(numeros=None):
    numeros = numeros or {}
    return [{'id': i, 'secuencia': s, 'numero': numeros.get(i)} for i, s in PRODUCCION]


def test_la_numeracion_sigue_el_orden_de_la_pantalla():
    n = numerar_sin_numero(_reglas())
    por_secuencia = {s: n[i] for i, s in PRODUCCION}
    # Bien marcadas
    assert [por_secuencia[s] for s in ('ES', 'ESES', 'ESESES')] == [1, 2, 3]
    # Se repite un tipo: de la 4 a la 25, la más antigua primero
    assert por_secuencia['EE'] == 4 and por_secuencia['SSESES'] == 25
    # Falta una marca y Una sola marca al final
    assert [por_secuencia[s] for s in ('ESE', 'SES', 'E', 'S')] == [26, 27, 28, 29]
    assert sorted(n.values()) == list(range(1, 30))


def test_las_que_ya_tienen_numero_no_se_mueven_y_una_nueva_toma_el_siguiente():
    ya = numerar_sin_numero(_reglas())
    reglas = _reglas(ya) + [{'id': 30, 'secuencia': 'EESE', 'numero': None}]
    assert numerar_sin_numero(reglas, ultimo=29) == {30: 30}
