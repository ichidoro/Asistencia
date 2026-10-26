# -*- coding: utf-8 -*-
"""Libro mayor de minutos (cuadre_service): cada minuto con un solo destino y sumas que cuadran.

Regla del dueño (25-10-2026). Los números son los de Massiel Abrigo en el tramo 26-09 → 25-10-2026 (base real):
deuda del 05-10 238,43 min más 1,94 min de segundos; perdonados 02-10 (1,35), 08-10 (2,75) y 22-10 (149,12);
horas extra 359,88 min en 8 días, aprobadas al 100 % con «Pagar todo».
"""
import os

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services.cuadre_service import hhmmss, plegar_libro  # noqa: E402
from backend.services.quantum_matrix_engine import AttendanceAdjustmentResolver  # noqa: E402


def dia(fecha, deuda=0.0, bruta=None, cond=0, he=0.0, estado_he=None, aut=0.0, teo=8.0, trab=8.0, estado='OK', comp=0.0):
    return {'fecha': fecha, 'estado': estado, 'horas_teoricas': teo, 'horas_trabajadas': trab,
            'minutos_deuda': deuda, 'minutos_deuda_bruta': (deuda if bruta is None else bruta), 'deuda_condonada': cond,
            'minutos_extra_bruto': he, 'estado_he': estado_he, 'minutos_extra_autorizados': aut, 'minutos_compensados_he': comp}


def massiel(aut_23=119.98):
    return [
        dia('2026-10-02', deuda=0.0, bruta=1.35, cond=3),
        dia('2026-10-05', deuda=238.43, trab=5.03, teo=9.0, estado='SALIDA_ADELANTADA'),
        dia('2026-10-08', deuda=0.0, bruta=2.75, cond=3),
        dia('2026-10-22', deuda=0.0, bruta=149.12, cond=3, trab=5.51),
        dia('2026-09-28', deuda=0.50), dia('2026-09-29', deuda=0.47), dia('2026-10-01', deuda=0.37),
        dia('2026-10-06', deuda=0.32), dia('2026-10-09', deuda=0.28),
        dia('2026-09-30', he=1.61, estado_he='APROBADO', aut=1.61), dia('2026-10-07', he=2.78, estado_he='APROBADO', aut=2.78),
        dia('2026-10-13', he=5.21, estado_he='APROBADO', aut=5.21), dia('2026-10-14', he=2.80, estado_he='APROBADO', aut=2.80),
        dia('2026-10-16', he=1.70, estado_he='APROBADO', aut=1.70), dia('2026-10-19', he=121.0, estado_he='APROBADO', aut=121.0),
        dia('2026-10-20', he=104.8, estado_he='APROBADO', aut=104.8), dia('2026-10-23', he=119.98, estado_he='APROBADO', aut=aut_23),
        {'fecha': '2026-10-24', 'estado': 'JORNADA_ESPECIAL', 'horas_teoricas': 0, 'horas_trabajadas': 6.5, 'jornada_adicional': {'estado': 'JORNADA_ESPECIAL'}},
    ]


def test_pagar_todo_cuadra_y_el_saldo_es_el_de_hoy():
    lb = plegar_libro(massiel())
    assert hhmmss(lb['deuda_neta']) == '4:00:22'
    assert hhmmss(lb['perdonado']) == '2:33:13'
    assert hhmmss(lb['deuda_bruta']) == '6:33:35'
    assert hhmmss(lb['he_trabajadas']) == '5:59:53'
    assert hhmmss(lb['cubierto']) == '4:00:22' and lb['pendiente'] == 0
    assert hhmmss(lb['he_a_pagar']) == '1:59:31' and lb['he_no_pagadas'] == 0 and lb['he_por_decidir'] == 0
    assert hhmmss(lb['saldo']) == '1:59:31'
    assert abs(lb['saldo'] - lb['saldo_formula_actual']) < 0.001, "el saldo debe ser el mismo que calculan hoy grilla, cierre y Excel"
    codigos = {h['codigo'] for h in lb['hallazgos']}
    assert 'identidad_deuda' not in codigos and 'identidad_horas_extra' not in codigos
    assert 'perdonazo_con_horas_a_pagar' in codigos      # se perdonó y además quedan horas a pagar: se avisa, no se esconde
    assert 'deuda_de_segundos' in codigos


def test_saldo_cero_deja_el_resto_como_no_pagado_y_lo_senala():
    lb = plegar_libro(massiel(aut_23=0.47))        # «Compensar deuda (saldo cero)» aprobó 28 segundos del 23-10
    assert abs(lb['saldo']) < 0.01
    assert hhmmss(lb['cubierto']) == '4:00:22' and lb['he_a_pagar'] < 0.01
    assert hhmmss(lb['he_no_pagadas']) == '1:59:31', "los minutos que hoy desaparecen deben quedar escritos como no pagados"
    parcial = next(h for h in lb['hallazgos'] if h['codigo'] == 'aprobacion_parcial')
    assert parcial['dias'] == ['2026-10-23']


def test_horas_insuficientes_dejan_pendiente_y_saldo_negativo():
    dias = [dia('2026-10-06', deuda=317.0, trab=3.0), dia('2026-10-13', he=244.0, estado_he='PENDIENTE')]
    lb = plegar_libro(dias)
    assert lb['he_por_decidir'] == 244.0 and lb['cubierto'] == 0 and lb['pendiente'] == 317.0
    assert any(h['codigo'] == 'saldo_negativo' for h in lb['hallazgos'])
    dias[1].update(estado_he='APROBADO', minutos_extra_autorizados=244.0)
    lb = plegar_libro(dias)
    assert lb['cubierto'] == 244.0 and lb['pendiente'] == 73.0 and lb['he_a_pagar'] == 0 and lb['saldo'] == -73.0


def test_bloques_y_rechazos_son_no_pagadas():
    dias = [dia('2026-10-06', deuda=178.0), dia('2026-10-13', he=281.0, estado_he='APROBADO', aut=238.0), dia('2026-10-14', he=20.0, estado_he='RECHAZADO')]
    lb = plegar_libro(dias)
    assert lb['cubierto'] == 178.0 and lb['he_a_pagar'] == 60.0 and lb['he_no_pagadas'] == 63.0
    assert lb['he_trabajadas'] == 301.0 == lb['he_usadas_deuda'] + lb['he_a_pagar'] + lb['he_no_pagadas'] + lb['he_por_decidir']


def test_aprobado_por_sobre_lo_trabajado_se_avisa():
    dias = [dia('2026-09-26', he=26.0, estado_he='APROBADO', aut=56.0)]
    lb = plegar_libro(dias)
    assert lb['he_a_pagar'] == 56.0 and lb['he_trabajadas'] == 56.0
    assert any(h['codigo'] == 'aprobado_sobre_trabajado' for h in lb['hallazgos'])


def test_dia_sin_deuda_bruta_guardada_no_inventa_perdon():
    d = dia('2026-10-22', deuda=0.0, cond=3)
    d['minutos_deuda_bruta'] = None
    lb = plegar_libro([d])
    assert lb['perdonado'] == 0 and lb['deuda_bruta'] == 0


def test_el_motor_guarda_la_deuda_antes_del_perdon():
    res = {'estado': 'SALIDA_ADELANTADA', 'minutos_deuda': 149.12, 'minutos_atraso': 0.0, 'minutos_salida_adelantada': 149.12,
           'tiene_salida_adelantada': 1, 'observaciones': ''}
    out = AttendanceAdjustmentResolver.apply(res, '2026-10-22', None, None, 3)
    assert out['minutos_deuda_bruta'] == 149.12 and out['minutos_deuda'] == 0.0 and out['deuda_condonada'] == 3


def test_excel_lee_las_columnas_del_libro():
    """El Excel escribe las mismas columnas del libro que la grilla (claves l_<campo>); «usadas» suma deuda e inasistencia.
    Una persona de Bolsa Flexible no tiene libro: solo lo trabajado y lo aprobado."""
    from backend.services.report_service import ReportService
    fila = {"esBolsa": False, "he_bruto": 999, "he_apr": 999,
            "libro": {"he_trabajadas": 359.88, "he_usadas_deuda": 240.37, "he_usadas_inasistencia": 10.0,
                      "he_a_pagar": 60.0, "he_no_pagadas": 49.51, "he_por_decidir": 0.0,
                      "deuda_bruta": 393.58, "perdonado": 153.21, "cubierto": 240.37, "pendiente": 0.0, "saldo": 60.0}}
    assert ReportService._libro_valor(fila, "l_he_usadas") == 250.37
    assert ReportService._libro_valor(fila, "l_he_a_pagar") == 60.0
    assert ReportService._libro_valor(fila, "l_deuda_bruta") == 393.58
    assert ReportService._libro_valor(fila, "l_pendiente") == 0.0
    bolsa = {"esBolsa": True, "he_bruto": 120.0, "he_apr": 90.0, "libro": {}}
    assert ReportService._libro_valor(bolsa, "l_he_trabajadas") == 120.0
    assert ReportService._libro_valor(bolsa, "l_he_a_pagar") == 90.0
    assert ReportService._libro_valor(bolsa, "l_pendiente") == 0.0
