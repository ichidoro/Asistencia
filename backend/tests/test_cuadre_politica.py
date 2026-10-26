# -*- coding: utf-8 -*-
"""Política del tramo (cuadre_service.asignar_minutos) y tolerancia / perdón del tramo en el libro.

Decisión del dueño (25-10-2026): después de cubrir la deuda con horas extra hay una sola pregunta con dos
respuestas: «llevar todo a cero» (lo que falte se perdona, lo que sobre no se paga) o «pagar horas extra:
¿cuántas?» (todas, un bloque o una cantidad; el resto queda escrito como no pagado). Los números son los de
Massiel Abrigo, Gabriel Pichuante y Carlos León en el tramo 26-09 → 25-10-2026.
"""
import os

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services.cuadre_service import asignar_minutos, hhmmss, plegar_libro  # noqa: E402

MASSIEL_HE = [
    {'fecha': '2026-09-30', 'minutos_bruto': 1.61, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'excepcion': 0},
    {'fecha': '2026-10-07', 'minutos_bruto': 2.78, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'excepcion': 0},
    {'fecha': '2026-10-13', 'minutos_bruto': 5.21, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'excepcion': 0},
    {'fecha': '2026-10-14', 'minutos_bruto': 2.80, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'excepcion': 0},
    {'fecha': '2026-10-16', 'minutos_bruto': 1.70, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'excepcion': 0},
    {'fecha': '2026-10-19', 'minutos_bruto': 121.0, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'excepcion': 0},
    {'fecha': '2026-10-20', 'minutos_bruto': 104.8, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'excepcion': 0},
    {'fecha': '2026-10-23', 'minutos_bruto': 119.98, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'excepcion': 0},
]
DEUDA_MASSIEL = 240.37


def por_fecha(reparto):
    return {r['fecha']: r for r in reparto}


def test_llevar_todo_a_cero_cubre_y_no_paga_el_resto():
    reparto, resumen = asignar_minutos(MASSIEL_HE, DEUDA_MASSIEL, 'CERO')
    assert hhmmss(resumen['cubierto']) == '4:00:22' and resumen['pendiente'] == 0 and resumen['a_pagar'] == 0
    assert hhmmss(resumen['no_pagadas']) == '1:59:31'
    r = por_fecha(reparto)
    assert r['2026-10-19']['minutos_autorizados'] == 121.0 and r['2026-10-19']['usadas'] == 121.0
    assert r['2026-10-23']['estado'] == 'APROBADO' and abs(r['2026-10-23']['minutos_autorizados'] - 0.47) < 0.01
    assert r['2026-10-23']['a_pagar'] == 0


def test_pagar_todas_las_que_sobran():
    reparto, resumen = asignar_minutos(MASSIEL_HE, DEUDA_MASSIEL, 'PAGAR', None)
    assert hhmmss(resumen['a_pagar']) == '1:59:31' and resumen['no_pagadas'] == 0
    assert all(r['estado'] == 'APROBADO' for r in reparto)
    assert por_fecha(reparto)['2026-10-23']['minutos_autorizados'] == 119.98


def test_pagar_un_bloque_deja_el_resto_no_pagado():
    reparto, resumen = asignar_minutos(MASSIEL_HE, DEUDA_MASSIEL, 'PAGAR', 90.0)
    assert resumen['a_pagar'] == 90.0 and hhmmss(resumen['no_pagadas']) == '0:29:31'
    assert abs(por_fecha(reparto)['2026-10-23']['minutos_autorizados'] - 90.47) < 0.01


def test_horas_insuficientes_el_cero_dice_cuanto_falta():
    filas = [{'fecha': '2026-10-13', 'minutos_bruto': 244.0, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'excepcion': 0}]
    reparto, resumen = asignar_minutos(filas, 317.0, 'CERO')
    assert resumen['cubierto'] == 244.0 and resumen['pendiente'] == 73.0 and resumen['a_pagar'] == 0
    assert reparto[0]['minutos_autorizados'] == 244.0 and reparto[0]['estado'] == 'APROBADO'


def test_la_excepcion_a_mano_no_se_toca_y_cuenta_primero():
    filas = [{'fecha': '2026-10-06', 'minutos_bruto': 60.0, 'minutos_autorizados': 60.0, 'estado': 'APROBADO', 'excepcion': 1},
             {'fecha': '2026-10-13', 'minutos_bruto': 221.0, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'excepcion': 0}]
    reparto, resumen = asignar_minutos(filas, 178.0, 'PAGAR', 60.0)
    assert [r['fecha'] for r in reparto] == ['2026-10-13']          # la excepción no aparece en el reparto
    assert reparto[0]['usadas'] == 118.0 and reparto[0]['a_pagar'] == 60.0 and reparto[0]['minutos_autorizados'] == 178.0
    assert resumen['cubierto'] == 178.0 and resumen['a_pagar'] == 60.0 and resumen['no_pagadas'] == 43.0


def test_jornada_especial_aprobada_como_hora_extra_cubre_primero():
    filas = [{'fecha': '2026-10-13', 'minutos_bruto': 100.0, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'excepcion': 0}]
    _, resumen = asignar_minutos(filas, 150.0, 'CERO', aprobadas_fijas=120.0)
    assert resumen['cubierto'] == 150.0 and resumen['pendiente'] == 0 and resumen['no_pagadas'] == 70.0


def test_politica_desconocida_se_rechaza():
    import pytest
    with pytest.raises(ValueError):
        asignar_minutos(MASSIEL_HE, 10.0, 'REGALAR')


def dia(fecha, deuda=0.0, he=0.0, estado_he=None, aut=0.0):
    return {'fecha': fecha, 'estado': 'OK', 'horas_teoricas': 8.0, 'horas_trabajadas': 8.0, 'minutos_deuda': deuda,
            'minutos_deuda_bruta': deuda, 'deuda_condonada': 0, 'minutos_extra_bruto': he, 'estado_he': estado_he,
            'minutos_extra_autorizados': aut, 'minutos_compensados_he': 0}


def test_tolerancia_deja_pasar_los_segundos_y_cuadra():
    dias = [dia('2026-09-28', deuda=0.50), dia('2026-09-29', deuda=0.47), dia('2026-10-05', deuda=238.43)]
    sin = plegar_libro(dias)
    con = plegar_libro(dias, tolerancia_min=1.0)
    assert hhmmss(sin['deuda_neta']) == '3:59:24' and any(h['codigo'] == 'deuda_de_segundos' for h in sin['hallazgos'])
    assert hhmmss(con['deuda_neta']) == '3:58:26' and abs(con['tolerado'] - 0.97) < 0.001
    assert not any(h['codigo'] == 'deuda_de_segundos' for h in con['hallazgos'])
    assert abs(con['deuda_bruta'] - (con['perdonado'] + con['cubierto'] + con['pendiente'])) < 0.01


def test_perdon_del_tramo_borra_lo_pendiente_y_no_mas():
    dias = [dia('2026-10-06', deuda=317.0), dia('2026-10-13', he=244.0, estado_he='APROBADO', aut=244.0)]
    lb = plegar_libro(dias, perdon_cuadre=73.0, hay_politica=True)
    assert lb['cubierto'] == 244.0 and lb['pendiente'] == 0 and lb['perdon_cuadre'] == 73.0 and lb['saldo'] == 0
    assert abs(lb['deuda_bruta'] - (lb['perdonado'] + lb['cubierto'] + lb['pendiente'])) < 0.01
    # Si la deuda baja (una corrección), el perdón guardado no inventa saldo a favor
    lb2 = plegar_libro([dia('2026-10-06', deuda=250.0), dias[1]], perdon_cuadre=73.0, hay_politica=True)
    assert lb2['perdon_cuadre'] == 6.0 and lb2['pendiente'] == 0 and lb2['saldo'] == 0


def test_con_politica_la_aprobacion_parcial_no_es_hallazgo():
    dias = [dia('2026-10-05', deuda=240.37), dia('2026-10-23', he=119.98, estado_he='APROBADO', aut=0.47)]
    assert any(h['codigo'] == 'aprobacion_parcial' for h in plegar_libro(dias)['hallazgos'])
    assert not any(h['codigo'] == 'aprobacion_parcial' for h in plegar_libro(dias, hay_politica=True)['hallazgos'])


def test_la_cobertura_de_turno_no_la_reescribe_la_politica():
    """Una cobertura de turno validada como horas extra (origen COBERTURA_TURNO) cuenta como aprobada fija:
    cubre deuda primero y no aparece en el reparto, así la política nunca cambia su estado ni su origen."""
    from backend.services.cuadre_service import marcar_filas_fijas
    filas = marcar_filas_fijas([
        {'fecha': '2026-10-02', 'minutos_bruto': 291.0, 'minutos_autorizados': 291.0, 'estado': 'APROBADO', 'origen': 'COBERTURA_TURNO', 'excepcion': 0},
        {'fecha': '2026-10-13', 'minutos_bruto': 60.0, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'origen': 'SISTEMA', 'excepcion': 0},
    ])
    reparto, resumen = asignar_minutos(filas, 100.0, 'CERO')
    assert [r['fecha'] for r in reparto] == ['2026-10-13']
    assert reparto[0]['estado'] == 'RECHAZADO' and reparto[0]['minutos_autorizados'] == 0.0
    assert resumen['cubierto'] == 100.0 and resumen['pendiente'] == 0 and resumen['a_pagar'] == 191.0
