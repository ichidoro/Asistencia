# -*- coding: utf-8 -*-
"""Reglas del cuadre decididas por el dueño (26-10-2026).

  · Toda deuda se paga con horas extra, en este orden: exceso de colación (y lo sin causa), permisos, atrasos, salidas
    adelantadas; las inasistencias compensables van al final.
  · Solo se perdonan atrasos y salidas adelantadas, de cualquier tamaño (también lo que queda dentro de la tolerancia
    del turno y el motor no marca).
  · El exceso de colación y los permisos no se perdonan nunca.
  · La guía del cuadre perdona por día, como el interruptor, lo que las horas extra no alcanzan a pagar; un día del
    borde se perdona en parte en la cuenta del cuadre; un día con marca del interruptor no se toca.
"""
import os

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services.cuadre_service import (  # noqa: E402
    aviso_inasistencia, causas_dia, hhmmss, plan_perdonazo, plegar_libro, presupuesto_he,
)


def dia(fecha, deuda=0.0, atr=0.0, sal=0.0, col=0.0, per=0.0, he=0.0, estado=None, cond=0, **extra):
    d = {'fecha': fecha, 'estado': estado or ('ATRASO' if atr else ('SALIDA_ADELANTADA' if sal else 'OK')),
         'horas_teoricas': 8.0, 'horas_trabajadas': 8.0, 'minutos_deuda': deuda, 'minutos_deuda_bruta': deuda,
         'deuda_condonada': cond, 'minutos_atraso': atr, 'minutos_salida_adelantada': sal, 'minutos_exceso_colacion': col,
         'minutos_permisos_detectados': per, 'minutos_extra_bruto': he, 'estado_he': 'PENDIENTE' if he else None,
         'minutos_extra_autorizados': 0, 'minutos_compensados_he': 0}
    d.update(extra)
    return d


def fila_he(fecha, bruto):
    return {'fecha': fecha, 'minutos_bruto': bruto, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'origen': 'SISTEMA', 'excepcion': 0}


# ── Causas de un día ────────────────────────────────────────────────

def test_las_causas_suman_la_deuda_del_dia():
    c = causas_dia(dia('2026-10-07', deuda=40.0, atr=10.0, col=30.0))
    assert c['atraso'] == 10.0 and c['colacion'] == 30.0 and c['salida'] == 0.0
    assert abs(c['atraso'] + c['salida'] + c['colacion'] + c['permiso'] + c['otra'] - 40.0) < 1e-9


def test_lo_compensado_el_mismo_dia_paga_primero_lo_que_no_se_perdona():
    # Llegó 30 min tarde, tomó 20 min de más en la colación y se quedó 25 min más: debe 25 min netos
    c = causas_dia(dia('2026-10-08', deuda=25.0, atr=30.0, col=20.0))
    assert c['atraso'] == 25.0 and c['colacion'] == 0.0


def test_lo_que_queda_dentro_de_la_tolerancia_del_turno_es_salida_adelantada():
    # Turno con Tolerancia Salida Adelantada 1 min: salió 16:29:20 con salida 16:30; el motor no lo marca, pero el día
    # debe 40 segundos y son salida adelantada
    c = causas_dia(dia('2026-09-28', deuda=0.67, hora_entrada_real='06:57:13', hora_entrada_teorica='07:00',
                       hora_salida_real='16:29:20', hora_salida_teorica='16:30', tolerancia_salida_turno=1))
    assert abs(c['salida'] - 0.6667) < 0.01 and c['atraso'] == 0.0 and c['salida_marcada'] == 0.0
    assert c['otra'] < 0.01


def test_sin_tolerancia_no_hay_minuto_fijo_que_agregue_causas():
    # Tolerancia 0: el motor marca toda salida antes de la hora; si no la marcó, el cuadre no la inventa
    c = causas_dia(dia('2026-09-28', deuda=0.67, hora_salida_real='16:29:20', hora_salida_teorica='16:30'))
    assert c['salida'] == 0.0 and abs(c['otra'] - 0.67) < 0.01


def test_lo_que_pasa_la_tolerancia_no_se_toma_como_atraso_sin_marca():
    # Tolerancia de atraso 2 min y llegó 5 min tarde sin atraso marcado (lo cubrió otra cosa): no se cuenta como atraso
    c = causas_dia(dia('2026-10-02', deuda=5.0, hora_entrada_real='07:05:00', hora_entrada_teorica='07:00',
                       tolerancia_atraso_turno=2))
    assert c['atraso'] == 0.0 and c['otra'] == 5.0


def test_un_dia_con_marca_del_interruptor_no_vuelve_a_ofrecer_esa_causa():
    # Interruptor tipo 2 (atraso): el motor ya sacó el atraso; queda la salida
    c = causas_dia(dia('2026-10-09', deuda=15.0, atr=40.0, sal=15.0, cond=2))
    assert c['atraso'] == 0.0 and c['salida'] == 15.0


# ── Orden de pago ──────────────────────────────────────────────────

def test_las_horas_extra_pagan_primero_la_colacion_y_lo_que_queda_es_atraso():
    # Ejemplo del dueño: Juan debe 30 min de atraso y 30 de exceso de colación, y tiene 30 min de horas extra
    dias = [dia('2026-10-07', deuda=30.0, atr=30.0), dia('2026-10-08', deuda=30.0, col=30.0),
            dia('2026-10-10', he=30.0, estado_he='APROBADO', minutos_extra_autorizados=30.0)]
    lb = plegar_libro(dias)
    assert lb['cubierto_causa']['colacion'] == 30.0 and lb['cubierto_causa']['atraso'] == 0.0
    assert lb['pendiente_perdonable'] == 30.0 and lb['pendiente_no_perdonable'] == 0.0


def test_el_perdon_del_cuadre_nunca_borra_colacion_ni_permisos():
    dias = [dia('2026-10-07', deuda=30.0, col=30.0), dia('2026-10-08', deuda=20.0, per=20.0)]
    lb = plegar_libro(dias, perdon_cuadre=50.0, hay_politica=True)
    assert lb['perdon_cuadre'] == 0.0 and lb['pendiente'] == 50.0 and lb['saldo'] == -50.0


def test_las_inasistencias_se_compensan_solo_con_lo_que_sobra():
    # 60 min de deuda, 60 de horas extra aprobadas y 60 ya compensados en una inasistencia: la deuda va primero
    dias = [dia('2026-10-07', deuda=60.0, atr=60.0),
            dia('2026-10-08', he=60.0, estado_he='APROBADO', minutos_extra_autorizados=60.0),
            dia('2026-10-09', estado='INASISTENCIA_COMPENSADA', minutos_compensados_he=60.0)]
    lb = plegar_libro(dias)
    assert lb['cubierto'] == 60.0 and lb['he_usadas_inasistencia'] == 0.0
    assert any(h['codigo'] == 'compensacion_sin_respaldo' for h in lb['hallazgos'])


def test_lista_congelada_el_exceso_sobre_lo_aprobado_vuelve_a_deuda():
    # La guía aprobó 20:48 (tipo 2) el 14-10; después corrigen la marca y el atraso sube a 35:00
    d = dia('2026-10-14', deuda=0.0, atr=35.0, cond=2)
    d['minutos_deuda_bruta'] = 35.0
    lb = plegar_libro([d], guiados={'2026-10-14': {'tipo': 2, 'minutos_marca': 20.8}})
    assert abs(lb['perdonado'] - 20.8) < 1e-6 and abs(lb['pendiente'] - 14.2) < 1e-6
    assert any(h['codigo'] == 'perdonazo_guiado_reabierto' for h in lb['hallazgos'])
    assert abs(lb['deuda_bruta'] - (lb['perdonado'] + lb['cubierto'] + lb['pendiente'])) < 0.01


def test_si_el_interruptor_cambia_un_dia_de_la_guia_se_avisa():
    d = dia('2026-10-14', deuda=0.0, atr=35.0, cond=3)
    d['minutos_deuda_bruta'] = 35.0
    lb = plegar_libro([d], guiados={'2026-10-14': {'tipo': 2, 'minutos_marca': 35.0}})
    assert any(h['codigo'] == 'perdonazo_guiado_cambiado' for h in lb['hallazgos'])


# ── La guía ─────────────────────────────────────────────────────────

def _plan(dias, filas):
    lb = plegar_libro(dias)
    return plan_perdonazo(dias, lb, presupuesto_he(dias, lb, filas))


def test_juan_se_perdona_el_atraso_y_queda_en_cero():
    dias = [dia('2026-10-07', deuda=30.0, atr=30.0), dia('2026-10-08', deuda=30.0, col=30.0), dia('2026-10-10', he=30.0)]
    p = _plan(dias, [fila_he('2026-10-10', 30.0)])
    assert p['total'] == 30.0 and p['queda_no_perdonable'] == 0.0
    assert p['dias'][0]['fecha'] == '2026-10-07' and p['dias'][0]['tipo'] == 2 and p['dias'][0]['efecto'] == 'pasa_a_ok'
    assert p['por_cuadre'] == 0.0


def test_las_horas_extra_pagan_atrasos_por_fecha_y_luego_salidas_lo_que_falta_se_perdona_desde_el_final():
    dias = [dia('2026-10-01', deuda=20.0, atr=20.0), dia('2026-10-02', deuda=30.0, sal=30.0),
            dia('2026-10-03', deuda=10.0, atr=10.0), dia('2026-10-04', deuda=40.0, sal=40.0), dia('2026-10-05', he=45.0)]
    p = _plan(dias, [fila_he('2026-10-05', 45.0)])
    # Pagan: atraso 01 (20) + atraso 03 (10) + 15 de la salida 02. Se perdonan: 15 de la salida 02 y toda la del 04
    por = {d['fecha']: d for d in p['dias']}
    assert set(por) == {'2026-10-02', '2026-10-04'}
    assert por['2026-10-04']['tipo'] == 1 and por['2026-10-04']['salida'] == 40.0 and por['2026-10-04']['efecto'] == 'pasa_a_ok'
    assert por['2026-10-02']['tipo'] == 0 and por['2026-10-02']['minutos_cuadre'] == 15.0 and por['2026-10-02']['efecto'] == 'parcial'
    assert p['total'] == 55.0 and p['por_cuadre'] == 15.0 and p['por_marca'] == 40.0


def test_lo_que_queda_dentro_de_la_tolerancia_se_perdona_en_el_cuadre_sin_marca():
    d = dia('2026-09-28', deuda=0.67, hora_salida_real='16:29:20', hora_salida_teorica='16:30', tolerancia_salida_turno=1)
    p = _plan([d], [])
    assert len(p['dias']) == 1 and p['dias'][0]['tipo'] == 0 and p['dias'][0]['efecto'] == 'tolerancia'
    assert abs(p['por_cuadre'] - 0.6667) < 0.01


def test_con_tolerancia_cero_los_segundos_marcados_se_perdonan_con_la_marca():
    # Con tolerancia 0 el motor marca los 40 s como salida adelantada: la guía los perdona con la marca y el día pasa a OK
    d = dia('2026-09-28', deuda=0.67, sal=0.67, hora_salida_real='16:29:20', hora_salida_teorica='16:30')
    p = _plan([d], [])
    assert p['dias'][0]['tipo'] == 1 and p['dias'][0]['efecto'] == 'pasa_a_ok'
    assert abs(p['por_marca'] - 0.67) < 0.01 and p['por_cuadre'] == 0.0


def test_un_dia_con_marca_del_interruptor_no_se_pisa():
    dias = [dia('2026-10-09', deuda=15.0, atr=40.0, sal=15.0, cond=2)]
    p = _plan(dias, [])
    assert p['dias'][0]['tipo'] == 0 and p['dias'][0]['minutos_cuadre'] == 15.0


def test_colacion_sin_horas_extra_queda_como_deuda_y_los_atrasos_se_perdonan():
    # María Alejandra: atrasos 41:41, colación 1:49:27, horas extra 5:39
    dias = [dia('2026-10-01', deuda=41.68, atr=41.68), dia('2026-10-02', deuda=109.45, col=109.45), dia('2026-10-03', he=5.65)]
    p = _plan(dias, [fila_he('2026-10-03', 5.65)])
    assert hhmmss(p['total']) == '0:41:41' and hhmmss(p['queda_no_perdonable']) == '1:43:48'


def test_aviso_cuando_perdonar_alcanzaria_para_compensar_una_inasistencia():
    # Juan: 30 min de atraso, una inasistencia de 8 horas y 8 horas de horas extra
    dias = [dia('2026-10-07', deuda=30.0, atr=30.0), dia('2026-10-08', estado='INASISTENCIA'),
            dia('2026-10-10', he=480.0)]
    av = aviso_inasistencia(dias, plegar_libro(dias))
    assert av and av['fecha'] == '2026-10-08' and av['minutos_inasistencia'] == 480.0
    assert av['libres_pagando'] == 450.0 and av['libres_perdonando'] == 480.0


def test_simular_sin_guia_repone_la_deuda_de_los_dias_que_puso_la_guia():
    from backend.services.cuadre_service import simular_sin_guia
    d = dia('2026-10-04', deuda=0.0, sal=0.0, cond=1, estado='OK')
    d['minutos_deuda_bruta'] = 40.0
    sim = simular_sin_guia([d], [{'fecha': '2026-10-04', 'tipo': 1, 'minutos_marca': 40.0, 'minutos_salida': 40.0}])
    assert sim[0]['deuda_condonada'] == 0 and sim[0]['minutos_deuda'] == 40.0 and sim[0]['minutos_salida_adelantada'] == 40.0
    assert causas_dia(sim[0])['salida'] == 40.0
    # Un día cuya marca ya no es la de la guía (la cambió el interruptor) no se toca
    d2 = dict(d, deuda_condonada=3)
    assert simular_sin_guia([d2], [{'fecha': '2026-10-04', 'tipo': 1, 'minutos_marca': 40.0, 'minutos_salida': 40.0}])[0] is d2
