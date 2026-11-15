# -*- coding: utf-8 -*-
"""El ciclo del día se elige con las marcas como las lee la regla de marcaciones (dueño, 15-11-2026).

Caso real (sin datos de personas): sábado de un horario con rotación diaria y tres opciones (libre, 04:00-09:00 y
09:00-14:00). El reloj rotuló dos SALIDAS, 08:30 y 09:46; la regla de dos SALIDAS las lee alternando (ENTRADA 08:30,
SALIDA 09:46). Antes el ciclo se elegía con el rótulo del reloj (solo la última SALIDA) y ganaba 04:00-09:00, con 270 min
de atraso; leída como la regla, la llegada de las 08:30 elige 09:00-14:00, igual que cuando se corrige la marca a mano.
"""
from datetime import datetime

from backend.services import quantum_matrix_engine as qme
from backend.services.quantum_matrix_engine import QuantumShiftWeekMatcher, _marcas_como_las_lee_la_regla

SABADO = 5
FECHA = '2026-11-14'
TURNOS = {
    1: {SABADO: {'es_libre': True}},
    2: {SABADO: {'es_libre': False, 'hora_entrada': '04:00', 'hora_salida': '09:00', 'horas_teoricas': 4.5}},
    3: {SABADO: {'es_libre': False, 'hora_entrada': '09:00', 'hora_salida': '14:00', 'horas_teoricas': 4.5}},
}
DOS_SALIDAS = [{'id': 1, 'fecha_hora': f'{FECHA} 08:30:13', 'tipo': 'Salida'},
               {'id': 2, 'fecha_hora': f'{FECHA} 09:46:31', 'tipo': 'Salida'}]
REGLA_SS = {'SS': {'secuencia': 'SS', 'lectura': 'ALTERNADA', 'colacion': 'TURNO', 'accion': 'CALCULA'}}


def _ciclo(marcas, reglas, tipo='CICLO_INTELIGENTE'):
    token = qme.REGLAS_MARCAS_ENSAYO.set(reglas)
    try:
        return QuantumShiftWeekMatcher.resolve_winner_week(
            empleado_id=1, fecha_str=FECHA, dt=datetime(2026, 11, 14), dia_semana=SABADO, logs=marcas,
            turnos_dict=TURNOS, total_sems=3, rotacion_dinamica=True, tipo_programacion=tipo)
    finally:
        qme.REGLAS_MARCAS_ENSAYO.reset(token)


def test_elige_el_ciclo_con_la_lectura_de_la_regla(monkeypatch):
    monkeypatch.setattr(qme, '_get_now_local', lambda: datetime(2026, 11, 15, 10, 0))
    corregidas_a_mano = [dict(DOS_SALIDAS[0], tipo='Entrada'), DOS_SALIDAS[1]]
    assert _ciclo(corregidas_a_mano, REGLA_SS) == 3
    assert _ciclo(DOS_SALIDAS, REGLA_SS) == 3          # la regla lee lo mismo que la corrección a mano
    assert _ciclo(DOS_SALIDAS, {}) == 2                 # sin regla: el rótulo del reloj, como antes


def test_mismas_condiciones_que_la_regla(monkeypatch):
    monkeypatch.setattr(qme, '_get_now_local', lambda: datetime(2026, 11, 15, 10, 0))
    assert _marcas_como_las_lee_la_regla(DOS_SALIDAS, 'BOLSA_FLEXIBLE') == DOS_SALIDAS
    solo_revisa = {'SS': dict(REGLA_SS['SS'], lectura='NINGUNA', accion='SOLO_REVISA')}
    token = qme.REGLAS_MARCAS_ENSAYO.set(solo_revisa)
    try:
        assert _marcas_como_las_lee_la_regla(DOS_SALIDAS, 'CICLO_INTELIGENTE') == DOS_SALIDAS
    finally:
        qme.REGLAS_MARCAS_ENSAYO.reset(token)
    # La jornada de hoy todavía no termina: la regla no la lee y el ciclo tampoco cambia
    monkeypatch.setattr(qme, '_get_now_local', lambda: datetime(2026, 11, 14, 23, 0))
    assert _ciclo(DOS_SALIDAS, REGLA_SS) == 2


def test_no_quita_marcas_ni_toca_las_originales(monkeypatch):
    monkeypatch.setattr(qme, '_get_now_local', lambda: datetime(2026, 11, 15, 10, 0))
    token = qme.REGLAS_MARCAS_ENSAYO.set(REGLA_SS)
    try:
        leidas = _marcas_como_las_lee_la_regla(DOS_SALIDAS, 'CICLO_INTELIGENTE')
    finally:
        qme.REGLAS_MARCAS_ENSAYO.reset(token)
    assert [m['tipo'] for m in leidas] == ['Entrada', 'Salida'] and len(leidas) == 2
    assert [m['tipo'] for m in DOS_SALIDAS] == ['Salida', 'Salida']
