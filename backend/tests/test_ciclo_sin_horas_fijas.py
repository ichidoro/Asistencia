# -*- coding: utf-8 -*-
"""El ciclo del día se reconoce por los ciclos del horario de la persona, no por horas fijas del reloj
(orden del dueño, 26-10-2026: «es una coincidencia que los ciclos internos sean mañana, tarde y noche»)."""
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services.quantum_matrix_engine import QuantumShiftWeekMatcher, banda_minutos_de  # noqa: E402

LUNES = 0


def _ciclo(entrada, salida, cruza=False, demora=0):
    return {LUNES: {'hora_entrada': entrada, 'hora_salida': salida, 'cruza_medianoche': cruza, 'es_libre': False,
                    'anclaje_salida_minutos': demora}}


def _marca(i, fecha_hora, tipo):
    return {'id': i, 'fecha_hora': fecha_hora, 'tipo': tipo}


def _ganador(turnos, logs, banda=0.0):
    return QuantumShiftWeekMatcher.resolve_winner_week(
        empleado_id=1, fecha_str='2026-10-19', dt=datetime(2026, 10, 19), dia_semana=LUNES, logs=logs,
        turnos_dict=turnos, total_sems=len(turnos), banda_minutos=banda)


def test_la_noche_se_reconoce_por_el_ciclo_mas_cercano_aunque_no_se_llame_noche_ni_empiece_a_las_23():
    # Un horario con ciclos «A» 06:00–14:00, «B» 14:00–22:00 y «C» 19:00–03:00 (cruza): una ENTRADA a las 18:40 es del
    # ciclo C y su SALIDA de las 03:10 del martes cuenta para elegirlo.
    turnos = {1: _ciclo('06:00', '14:00'), 2: _ciclo('14:00', '22:00'), 3: _ciclo('19:00', '03:00', cruza=True, demora=15)}
    logs = [_marca(1, '2026-10-19 18:40:00', 'Entrada'), _marca(2, '2026-10-20 03:10:00', 'Salida')]
    assert _ganador(turnos, logs) == 3


def test_la_salida_de_la_madrugada_se_busca_hasta_la_salida_del_ciclo_mas_su_demora_y_la_banda():
    turnos = {1: _ciclo('07:00', '15:00'), 2: _ciclo('15:00', '23:00'), 3: _ciclo('23:00', '07:00', cruza=True, demora=45)}
    entrada = _marca(1, '2026-10-19 22:50:00', 'Entrada')
    # 07:00 + 45 min de demora + 120 min de banda = 09:45: una SALIDA a las 09:30 se toma, a las 10:00 no.
    assert _ganador(turnos, [entrada, _marca(2, '2026-10-20 09:30:00', 'Salida')], banda=120) == 3
    sin_banda = [entrada, _marca(2, '2026-10-20 10:00:00', 'Salida')]
    assert _ganador(turnos, sin_banda, banda=120) == 3  # la ENTRADA sola ya calza con la noche


def test_una_entrada_de_dia_no_mira_la_madrugada_siguiente():
    turnos = {1: _ciclo('07:00', '15:00'), 2: _ciclo('15:00', '23:00'), 3: _ciclo('23:00', '07:00', cruza=True)}
    logs = [_marca(1, '2026-10-19 06:55:00', 'Entrada'), _marca(2, '2026-10-19 15:05:00', 'Salida'),
            _marca(3, '2026-10-20 06:50:00', 'Entrada')]
    assert _ganador(turnos, logs) == 1


def test_la_banda_sale_del_ajuste_en_horas_y_sin_ajuste_es_cero():
    assert banda_minutos_de({'asistencia_emergencia_banda_horas': '2.0'}) == 120
    assert banda_minutos_de({}) == 0
    assert banda_minutos_de(None) == 0


def test_no_quedan_las_horas_fijas_del_reloj_en_la_eleccion_del_ciclo():
    from pathlib import Path
    motor = (Path(__file__).resolve().parents[1] / "services" / "quantum_matrix_engine.py").read_text(encoding="utf-8")
    for fijo in ("< 1200]", "<= 180.0 for p_teo", "else 720.0", "max_sal_teo + 120.0", "class QUBOEnergyOptimizer",
                 "or '07:00'", "else '15:00'", "or '23:00'", "dur_delta >= 20.0", "redondeo_minutos"):
        assert fijo not in motor, f"volvió una hora o número fijo al motor: {fijo}"
