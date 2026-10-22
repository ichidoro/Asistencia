# -*- coding: utf-8 -*-
"""Prorrateo de la meta de Bolsa Flexible por vigencia parcial (sin base de datos).

Decisión del dueño (22-10-2026): a quien ingresa o egresa a mitad de un tramo
RRHH no se le exigen las 180 horas completas; la meta se reparte en proporción
a los días corridos de vigencia dentro del tramo, y se avisa (sin bloquear)
cuando esos días no alcanzan los 21 que exige el art. 25 bis del Código del
Trabajo. Los casos usan los datos reales del tramo 26-09-2026 → 25-10-2026.
"""
import os
os.environ.setdefault("SECRET_KEY", "test")

from backend.services.bolsa_prorrateo import (  # noqa: E402
    DIAS_MINIMOS_BOLSA_LEY, aplicar_prorrateo, calcular_prorrateo_bolsa,
    fecha_en_vigencia,
)

TRAMO_INI = "2026-09-26"
TRAMO_FIN = "2026-10-25"  # 30 días corridos


def test_empleado_antiguo_sin_egreso_no_se_prorratea():
    assert calcular_prorrateo_bolsa("2023-06-19", None, TRAMO_INI, TRAMO_FIN) is None
    assert calcular_prorrateo_bolsa(None, None, TRAMO_INI, TRAMO_FIN) is None
    # Egreso después del tramo tampoco recorta (caso real: salida 15-11)
    assert calcular_prorrateo_bolsa("2023-06-19", "2026-11-15", TRAMO_INI, TRAMO_FIN) is None


def test_ingreso_el_7_de_octubre_caso_real_pina_y_gonzalez():
    p = calcular_prorrateo_bolsa("2026-10-07", "2026-11-15", TRAMO_INI, TRAMO_FIN)
    assert p is not None
    assert p["desde"] == "2026-10-07" and p["hasta"] == TRAMO_FIN
    assert p["dias_tramo"] == 30 and p["dias_disponibles"] == 19
    assert p["fecha_ingreso"] == "2026-10-07" and p["fecha_salida"] is None
    # 180 h = 10.800 min → 19/30 → 6.840 min = 114 h
    assert aplicar_prorrateo(10800, p) == 6840
    # 88 h de espera = 5.280 min → 3.344 min
    assert aplicar_prorrateo(5280, p) == 3344
    # 19 < 21: la ley pide repartir las 180 h en al menos 21 días
    assert p["aviso_21_dias"] is True and p["dias_minimos_ley"] == DIAS_MINIMOS_BOLSA_LEY


def test_ingreso_el_1_de_octubre_caso_real_garrido_sin_aviso():
    p = calcular_prorrateo_bolsa("2026-10-01", "2026-11-15", TRAMO_INI, TRAMO_FIN)
    assert p is not None
    assert p["dias_disponibles"] == 25 and p["aviso_21_dias"] is False
    # 180 h → 25/30 → 150 h
    assert aplicar_prorrateo(10800, p) == 9000


def test_egreso_el_13_de_octubre_caso_real_reyes():
    p = calcular_prorrateo_bolsa("2025-03-19", "2026-10-13", TRAMO_INI, TRAMO_FIN)
    assert p is not None
    assert p["desde"] == TRAMO_INI and p["hasta"] == "2026-10-13"
    assert p["dias_disponibles"] == 18 and p["aviso_21_dias"] is True
    assert p["fecha_ingreso"] is None and p["fecha_salida"] == "2026-10-13"
    assert aplicar_prorrateo(10800, p) == 6480  # 108 h


def test_tramo_siguiente_de_los_contratados_hasta_el_15_11():
    # Tramo 26-10 → 25-11 (31 días): salida el 15-11 deja exactamente 21 días → sin aviso
    p = calcular_prorrateo_bolsa("2026-10-07", "2026-11-15", "2026-10-26", "2026-11-25")
    assert p is not None
    assert p["dias_disponibles"] == 21 and p["aviso_21_dias"] is False
    assert aplicar_prorrateo(10800, p) == round(10800 * 21 / 31)


def test_sin_dias_de_vigencia_en_el_tramo_meta_cero():
    p = calcular_prorrateo_bolsa("2026-11-01", None, TRAMO_INI, TRAMO_FIN)
    assert p is not None
    assert p["dias_disponibles"] == 0 and p["factor"] == 0.0
    assert aplicar_prorrateo(10800, p) == 0


def test_fechas_fuera_de_vigencia_no_cuentan_como_programadas():
    p = calcular_prorrateo_bolsa("2026-10-07", None, TRAMO_INI, TRAMO_FIN)
    assert fecha_en_vigencia("2026-10-06", p) is False   # aún no ingresaba
    assert fecha_en_vigencia("2026-10-07", p) is True
    assert fecha_en_vigencia("2026-10-25", p) is True
    assert fecha_en_vigencia("2026-10-01", None) is True  # sin prorrateo, todo el tramo


def test_tramo_mas_corto_que_21_dias_avisa_sin_recortar_la_meta():
    # Un tramo RRHH de 15 días avisa para todos, pero el factor queda en 1.0
    p = calcular_prorrateo_bolsa("2023-01-01", None, "2026-10-01", "2026-10-15")
    assert p is not None
    assert p["aviso_21_dias"] is True and p["factor"] == 1.0
    assert aplicar_prorrateo(10800, p) == 10800


def test_entradas_invalidas_no_rompen_nada():
    assert calcular_prorrateo_bolsa("basura", None, TRAMO_INI, TRAMO_FIN) is None
    assert calcular_prorrateo_bolsa(None, None, "basura", TRAMO_FIN) is None
    assert calcular_prorrateo_bolsa(None, None, TRAMO_FIN, TRAMO_INI) is None  # tramo invertido
