# -*- coding: utf-8 -*-
"""El ciclo del día se reconoce por los ciclos del horario de la persona, no por horas fijas del reloj
(orden del dueño, 26-10-2026: «es una coincidencia que los ciclos internos sean mañana, tarde y noche»)."""
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import quantum_matrix_engine as qme  # noqa: E402
from backend.services.quantum_matrix_engine import QuantumMatrixEngine as Q, QuantumShiftWeekMatcher  # noqa: E402

LUNES = 0


def _ciclo(entrada, salida, cruza=False, demora=0):
    return {LUNES: {'hora_entrada': entrada, 'hora_salida': salida, 'cruza_medianoche': cruza, 'es_libre': False,
                    'anclaje_salida_minutos': demora}}


def _marca(i, fecha_hora, tipo):
    return {'id': i, 'fecha_hora': fecha_hora, 'tipo': tipo}


def _ganador(turnos, logs):
    return QuantumShiftWeekMatcher.resolve_winner_week(
        empleado_id=1, fecha_str='2026-10-19', dt=datetime(2026, 10, 19), dia_semana=LUNES, logs=logs,
        turnos_dict=turnos, total_sems=len(turnos))


def test_la_noche_se_reconoce_por_el_ciclo_mas_cercano_aunque_no_se_llame_noche_ni_empiece_a_las_23():
    # Un horario con ciclos «A» 06:00–14:00, «B» 14:00–22:00 y «C» 19:00–03:00 (cruza): una ENTRADA a las 18:40 es del
    # ciclo C y su SALIDA de las 03:10 del martes cuenta para elegirlo.
    turnos = {1: _ciclo('06:00', '14:00'), 2: _ciclo('14:00', '22:00'), 3: _ciclo('19:00', '03:00', cruza=True, demora=15)}
    logs = [_marca(1, '2026-10-19 18:40:00', 'Entrada'), _marca(2, '2026-10-20 03:10:00', 'Salida')]
    assert _ganador(turnos, logs) == 3


def test_una_entrada_de_dia_no_mira_la_madrugada_siguiente():
    turnos = {1: _ciclo('07:00', '15:00'), 2: _ciclo('15:00', '23:00'), 3: _ciclo('23:00', '07:00', cruza=True)}
    logs = [_marca(1, '2026-10-19 06:55:00', 'Entrada'), _marca(2, '2026-10-19 15:05:00', 'Salida'),
            _marca(3, '2026-10-20 06:50:00', 'Entrada')]
    assert _ganador(turnos, logs) == 1


# ── Fin de la jornada por el borde más cercano del mismo tipo, sin banda fija (27-10-2026) ─────────────────────────────
TURNO = {"tipo_programacion": "CICLO_INTELIGENTE", "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0,
         "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "umbral_horas_colacion": 4.0,
         "anclaje_entrada_minutos": 0, "anclaje_salida_minutos": 0}
MANANA = {"es_libre": 0, "horas_teoricas": 7.5, "hora_entrada": "07:00", "hora_salida": "15:00", "cruza_medianoche": 0}
TARDE = {"es_libre": 0, "horas_teoricas": 7.5, "hora_entrada": "15:00", "hora_salida": "23:00", "cruza_medianoche": 0}
NOCHE = {"es_libre": 0, "horas_teoricas": 7.5, "hora_entrada": "23:00", "hora_salida": "07:00", "cruza_medianoche": 1}
TRES = [MANANA, TARDE, NOCHE]


def _dia(monkeypatch, marcas, dia, fecha="2026-10-19"):
    monkeypatch.setattr(qme, "_get_now_local", lambda: datetime(2026, 10, 25, 12, 0))
    monkeypatch.setattr(qme, "REGLAS_MARCAS_ACTIVAS", {})
    logs = [_marca(i + 1, fh, tp) for i, (fh, tp) in enumerate(marcas)]
    return Q.solve_attendance_day(fecha=fecha, empleado_id=1, logs=logs, turno_config=dict(TURNO), dia_config=dict(dia),
                                  global_ajustes={}, todos_ciclos_dia=[dict(c) for c in TRES],
                                  todos_ciclos_dia_siguiente=[dict(c) for c in TRES], consumidas_previas=set())


def test_la_salida_de_la_noche_se_toma_aunque_sea_tarde_si_es_la_mas_cercana(monkeypatch):
    # Noche 23:00–07:00 que se quedó hasta las 09:50: antes la banda de 2 h la dejaba afuera; su SALIDA más cercana es la
    # de esta noche (07:00), no la de la mañana del día siguiente (15:00).
    r = _dia(monkeypatch, [("2026-10-19 22:50:00", "Entrada"), ("2026-10-20 09:50:00", "Salida")], NOCHE)
    assert r["hora_salida_real"] == "09:50:00" and r["estado"] != "ANOMALIA"


def test_la_salida_mal_rotulada_de_la_noche_sigue_cerrando_el_turno(monkeypatch):
    # La SALIDA de las 07:02 quedó rotulada «Entrada»: está tan cerca de la SALIDA de la noche como de la ENTRADA de la mañana.
    r = _dia(monkeypatch, [("2026-10-19 23:01:00", "Entrada"), ("2026-10-20 07:02:00", "Entrada")], NOCHE)
    assert set(r["marcas_consumidas_ids"]) == {1, 2}


def test_la_entrada_de_la_noche_siguiente_empieza_otra_jornada(monkeypatch):
    r = _dia(monkeypatch, [("2026-10-19 22:50:00", "Entrada"), ("2026-10-20 22:55:00", "Entrada"),
                           ("2026-10-21 07:05:00", "Salida")], NOCHE)
    assert r["estado"] == "ANOMALIA" and set(r["marcas_consumidas_ids"]) == {1}


def test_la_tarde_que_sale_pasada_la_medianoche_se_cierra_con_esa_salida(monkeypatch):
    # Caso Orlando Carreño 05-10-2026: turno 15:00–23:00 con SALIDA a las 01:00:06.
    r = _dia(monkeypatch, [("2026-10-19 15:16:00", "Entrada"), ("2026-10-20 01:00:06", "Salida")], TARDE)
    assert r["hora_salida_real"] == "01:00:06"


def test_una_salida_de_madrugada_mas_cerca_de_la_entrada_del_dia_siguiente_no_alarga_la_jornada(monkeypatch):
    # Caso Gustavo Calderón 15/16-09-2026, Bodega 11:30–21:00 y 11:30–20:00: la SALIDA de las 04:49 del 16 queda a 7 h 49 de la
    # SALIDA del 15 (21:00) y a 6 h 41 de la ENTRADA del 16 (11:30): es del 16, no del 15.
    monkeypatch.setattr(qme, "_get_now_local", lambda: datetime(2026, 10, 25, 12, 0))
    monkeypatch.setattr(qme, "REGLAS_MARCAS_ACTIVAS", {})
    martes = {"es_libre": 0, "horas_teoricas": 9.0, "hora_entrada": "11:30", "hora_salida": "21:00", "cruza_medianoche": 0}
    miercoles = dict(martes, hora_salida="20:00", horas_teoricas=8.0)
    logs = [_marca(1, "2026-09-15 06:44:00", "Entrada"), _marca(2, "2026-09-15 14:40:55", "Salida"),
            _marca(3, "2026-09-16 04:49:34", "Salida"), _marca(4, "2026-09-16 15:10:07", "Salida")]
    r = Q.solve_attendance_day(fecha="2026-09-15", empleado_id=1, logs=logs, turno_config=dict(TURNO), dia_config=dict(martes),
                               global_ajustes={}, todos_ciclos_dia=[dict(martes)], todos_ciclos_dia_siguiente=[dict(miercoles)],
                               consumidas_previas=set())
    assert r["hora_salida_real"] == "14:40:55" and set(r["marcas_consumidas_ids"]) == {1, 2}


def test_una_noche_sin_marcas_no_se_lleva_la_entrada_de_la_manana_siguiente(monkeypatch):
    # Caso Orlando Carreño 20/21-07-2026: no vino la noche del 20 y entró a la mañana del 21 a las 07:08. Esa ENTRADA queda
    # igual de cerca de la SALIDA de la noche (07:00) que de la ENTRADA de la mañana (07:00): la noche no tenía marcas
    # (no quedó abierta), así que la ENTRADA empieza la jornada del 21.
    r = _dia(monkeypatch, [("2026-10-20 07:08:40", "Entrada"), ("2026-10-20 14:27:07", "Salida")], NOCHE)
    assert r["estado"] == "INASISTENCIA" and not r.get("marcas_consumidas_ids")


def test_una_noche_sin_marcas_no_se_lleva_la_entrada_de_madrugada_de_la_manana(monkeypatch):
    # Caso Rudecindo Abarca 26/27-04-2026: no hizo la noche del 26 y entró a las 06:36 del 27 para su mañana (07:00). Esa ENTRADA
    # queda a 24 min del comienzo de la mañana y a 7 h 36 del de la noche: es del 27.
    r = _dia(monkeypatch, [("2026-10-20 06:36:29", "Entrada"), ("2026-10-20 15:16:10", "Salida")], NOCHE)
    assert r["estado"] == "INASISTENCIA" and not r.get("marcas_consumidas_ids")


def test_quien_llega_tarde_a_la_noche_despues_de_la_medianoche_sigue_en_su_noche(monkeypatch):
    r = _dia(monkeypatch, [("2026-10-20 00:40:00", "Entrada"), ("2026-10-20 07:05:00", "Salida")], NOCHE)
    assert set(r["marcas_consumidas_ids"]) == {1, 2} and r["estado"] == "ATRASO"


def test_llegar_horas_antes_de_un_ciclo_de_noche_no_es_atraso(monkeypatch):
    # Caso Orlando Carreño 28-06-2026: el domingo su horario solo tiene la noche (23:00–07:00) y trabajó de 07:00 a 23:00. En un
    # reloj de 24 h las 07:00 quedaban «8 h después» de las 23:00 (atraso de 480 min); con la fecha y hora llegó 16 h antes y
    # salió 8 h antes: jornada corrida, sin atraso ni salida adelantada, y las horas son las que trabajó.
    monkeypatch.setattr(qme, "_get_now_local", lambda: datetime(2026, 10, 25, 12, 0))
    monkeypatch.setattr(qme, "REGLAS_MARCAS_ACTIVAS", {})
    logs = [_marca(1, "2026-10-18 07:00:00", "Entrada"), _marca(2, "2026-10-18 15:00:00", "Salida"),
            _marca(3, "2026-10-18 16:00:00", "Entrada"), _marca(4, "2026-10-18 23:00:00", "Salida")]
    r = Q.solve_attendance_day(fecha="2026-10-18", empleado_id=1, logs=logs, turno_config=dict(TURNO), dia_config=dict(NOCHE),
                               global_ajustes={}, todos_ciclos_dia=[dict(NOCHE)], todos_ciclos_dia_siguiente=[dict(c) for c in TRES],
                               consumidas_previas=set())
    assert r["estado"] == "OK" and r["minutos_atraso"] == 0 and r["minutos_salida_adelantada"] == 0
    assert "Jornada corrida" in r["observaciones"] and abs(r["horas_trabajadas"] - 15.0) < 0.01


# ── Rotación diaria: la opción libre también compite (orden del dueño, 27-10-2026) ────────────────────────────────────────
# Planta Mantención 2 el domingo: la opción Noche trabaja de 23:00 a 07:00 y las opciones Mañana y Tarde son libres.
DOMINGO = {1: _ciclo('23:00', '07:00', cruza=True), 2: {LUNES: {'es_libre': True}}, 3: {LUNES: {'es_libre': True}}}


def _ganador_diario(logs, rotacion_dinamica=True):
    return QuantumShiftWeekMatcher.resolve_winner_week(
        empleado_id=1, fecha_str='2026-10-19', dt=datetime(2026, 10, 19), dia_semana=LUNES, logs=logs,
        turnos_dict=DOMINGO, total_sems=3, rotacion_dinamica=rotacion_dinamica)


def test_con_rotacion_diaria_las_marcas_de_dia_en_domingo_son_dia_libre_trabajado():
    # Caso Víctor Muñoz 05-07-2026: vino de 09:25 a 11:28 y no marcó a las 23:00 ni después: eligió una opción libre.
    logs = [_marca(1, '2026-10-19 09:25:25', 'Entrada'), _marca(2, '2026-10-19 11:28:51', 'Salida')]
    assert DOMINGO[_ganador_diario(logs)][LUNES].get('es_libre')


def test_con_rotacion_diaria_salir_justo_cuando_empieza_la_noche_no_es_hacer_la_noche():
    # Caso Orlando Carreño 28-06-2026: 07:00–15:00 y 16:00–23:00.
    logs = [_marca(1, '2026-10-19 07:00:00', 'Entrada'), _marca(2, '2026-10-19 15:00:00', 'Salida'),
            _marca(3, '2026-10-19 16:00:00', 'Entrada'), _marca(4, '2026-10-19 23:00:00', 'Salida')]
    assert DOMINGO[_ganador_diario(logs)][LUNES].get('es_libre')


def test_con_rotacion_diaria_quien_hace_la_noche_queda_en_la_noche():
    logs = [_marca(1, '2026-10-19 22:50:00', 'Entrada'), _marca(2, '2026-10-20 07:02:00', 'Salida')]
    assert _ganador_diario(logs) == 1


def test_quien_llega_a_la_noche_pasada_la_medianoche_elige_la_noche():
    # Caso Orlando Carreño 29-06-2026 (feriado): sin marcas ese día y ENTRADA a las 00:01 del 30. Antes la elección del ciclo
    # solo miraba la madrugada si había una ENTRADA ese día y esas horas no se contaban en ningún día.
    turnos = {1: _ciclo('07:00', '15:00'), 2: _ciclo('15:00', '23:00'), 3: _ciclo('23:00', '07:00', cruza=True)}
    logs = [_marca(1, '2026-10-20 00:01:04', 'Entrada'), _marca(2, '2026-10-20 01:36:05', 'Salida'),
            _marca(3, '2026-10-20 02:03:25', 'Entrada'), _marca(4, '2026-10-20 07:03:02', 'Salida')]
    assert _ganador(turnos, logs) == 3


def test_una_entrada_de_madrugada_de_la_manana_siguiente_no_elige_la_noche():
    # Caso Rudecindo Abarca 26/27-04-2026: la ENTRADA de las 06:36 queda más cerca de la mañana siguiente (07:00).
    turnos = {1: _ciclo('07:00', '15:00'), 2: _ciclo('15:00', '23:00'), 3: _ciclo('23:00', '07:00', cruza=True)}
    logs = [_marca(1, '2026-10-20 06:36:29', 'Entrada'), _marca(2, '2026-10-20 15:16:10', 'Salida')]
    assert _ganador(turnos, logs) != 3


def test_sin_rotacion_diaria_la_eleccion_no_cambia():
    logs = [_marca(1, '2026-10-19 09:25:25', 'Entrada'), _marca(2, '2026-10-19 11:28:51', 'Salida')]
    assert _ganador_diario(logs, rotacion_dinamica=False) == 1


def test_no_quedan_las_horas_fijas_del_reloj_en_la_eleccion_del_ciclo():
    from pathlib import Path
    motor = (Path(__file__).resolve().parents[1] / "services" / "quantum_matrix_engine.py").read_text(encoding="utf-8")
    for fijo in ("< 1200]", "<= 180.0 for p_teo", "else 720.0", "max_sal_teo + 120.0", "class QUBOEnergyOptimizer",
                 "or '07:00'", "else '15:00'", "or '23:00'", "dur_delta >= 20.0", "redondeo_minutos",
                 "asistencia_emergencia_banda_horas", "banda_minutos"):
        assert fijo not in motor, f"volvió una hora o número fijo al motor: {fijo}"
