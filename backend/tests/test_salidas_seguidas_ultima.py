"""Salidas seguidas después de una Entrada: la jornada cierra con la ÚLTIMA Salida (Ciclo Inteligente).

Caso real: Planta Mantención 2, jueves 01-10-2026, marcas 07:52:18 Entrada · 13:24:04 Salida · 17:16:10 Salida.
El motor se quedaba con la Salida más cercana a la salida teórica (13:24) y dejaba la última (17:16) afuera: 148 min de deuda para
alguien que estuvo hasta las 17:16. Ahora se toma la primera Entrada y la última Salida, las del medio se descartan y la pausa la cubre la
colación automática del turno asignado. No se crea ninguna hora ni ventana: manda el horario/turno asignado.

La regla ya existía escrita en MultiBlockTensorSolver.collapse_consecutive_same_type ("Salidas seguidas: preserva la última"), pero solo
valía entre marcas a menos de 20 min y un selector previo (la Salida más cercana a la salida teórica) la dejaba sin efecto.
"""
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import quantum_matrix_engine as qme  # noqa: E402
from backend.services.quantum_matrix_engine import QuantumMatrixEngine as Q  # noqa: E402

# Ajustes de la pestaña Reglas de marcaciones tal como están configurados en producción
# (el cálculo los lee de la tabla `ajustes`; el código no trae el número).
AJUSTES_CONFIGURADOS = {"reglas_marcas_repetidas_minutos": "20"}

AHORA = datetime(2026, 10, 2, 12, 0)

# Configuración real de Planta Mantención 2 (sin datos de personas): colación automática 30 min, umbral 5,5 h
TURNO = {"tipo_programacion": "CICLO_INTELIGENTE", "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0,
         "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "umbral_horas_colacion": 5.5,
         "anclaje_entrada_minutos": 0, "anclaje_salida_minutos": 0}
_BASE = {"es_libre": 0, "horas_teoricas": 7.5, "descuento_colacion_auto": 1, "minutos_colacion_auto": 30,
         "anclaje_entrada_minutos": 0, "anclaje_salida_minutos": 0, "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0}
MANANA = dict(_BASE, hora_entrada="07:00", hora_salida="15:00", cruza_medianoche=0)
TARDE = dict(_BASE, hora_entrada="15:00", hora_salida="23:00", cruza_medianoche=0)
NOCHE = dict(_BASE, hora_entrada="23:00", hora_salida="07:00", cruza_medianoche=1)
E, S = "entrada", "salida"


def _dia(monkeypatch, marcas, fecha="2026-10-01", dia=MANANA, turno=None, ciclos=None, ahora=None):
    monkeypatch.setattr(qme, "_get_now_local", lambda: ahora or AHORA)
    logs = [{"id": i + 1, "fecha_hora": f"{f} {h}", "tipo": t} for i, (f, h, t) in enumerate(marcas)]
    return Q.solve_attendance_day(fecha=fecha, empleado_id=1, logs=logs, turno_config=turno or TURNO, dia_config=dia,
                                  global_ajustes=dict(AJUSTES_CONFIGURADOS), todos_ciclos_dia=ciclos or [NOCHE, MANANA, TARDE], consumidas_previas=set())


def _d(marcas):   # marcas del mismo día: [(hora, tipo)]
    return [("2026-10-01", h, t) for h, t in marcas]


# ── Lo que cambia ────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_foto_2_entrada_salida_salida_cierra_con_la_ultima_salida(monkeypatch):
    r = _dia(monkeypatch, _d([("07:52:18", E), ("13:24:04", S), ("17:16:10", S)]))
    assert r["hora_entrada_real"] == "07:52:18"
    assert r["hora_salida_real"] == "17:16:10"            # antes: 13:24:04 (la más cercana a la salida teórica)
    assert r["minutos_deuda"] == 0 and r["minutos_salida_adelantada"] == 0   # antes: 148 min de deuda
    # Llegó 52 min después y salió 136 min después en un horario de tres ciclos: jornada corrida, no atraso (27-10-2026)
    assert r["minutos_atraso"] == 0 and "Jornada corrida" in r["observaciones"]
    assert abs(r["horas_trabajadas"] - 8.8978) < 0.001     # 9 h 23 min 52 s menos 30 min de colación automática del turno
    assert round(r["minutos_extra_bruto"]) == 84
    assert set(r["marcas_consumidas_ids"]) == {1, 2, 3}    # la del medio queda consumida, no se arrastra a otro día
    assert "Salidas seguidas: se tomó la última y se descartó la de las 13:24:04." in r["observaciones"]


def test_doble_toque_de_salida_separado_por_minutos_toma_la_ultima(monkeypatch):
    # 5 min entre las dos Salidas (más que el rebote de 3 min): antes ganaba la más cercana a las 15:00, ahora la última
    r = _dia(monkeypatch, _d([("06:58:00", E), ("15:02:00", S), ("15:07:00", S)]))
    assert r["hora_salida_real"] == "15:07:00" and r["estado"] == "OK" and r["minutos_deuda"] == 0


def test_tres_salidas_seguidas_se_queda_con_la_ultima_y_avisa_las_descartadas(monkeypatch):
    r = _dia(monkeypatch, _d([("07:00:00", E), ("12:30:00", S), ("13:00:00", S), ("15:01:00", S)]))
    assert r["hora_salida_real"] == "15:01:00" and r["estado"] == "OK"
    assert set(r["marcas_consumidas_ids"]) == {1, 2, 3, 4}
    assert "Salidas seguidas: se tomó la última y se descartaron las de las 12:30:00, 13:00:00." in r["observaciones"]


def test_salida_de_mas_despues_del_regreso_de_colacion(monkeypatch):
    # E · S (sale a colación) · E (regresa) · S de más 14 min después · S final: antes cerraba a las 13:12 con la Salida de más
    r = _dia(monkeypatch, _d([("06:47:00", E), ("11:49:00", S), ("12:58:00", E), ("13:12:00", S), ("15:04:00", S)]))
    assert r["hora_salida_real"] == "15:04:00"
    assert r["minutos_colacion_real"] == 69                # la pausa real, entre la primera Salida y el regreso
    assert "13:12:00" in r["observaciones"]


def test_turno_noche_toma_la_ultima_salida_del_dia_siguiente(monkeypatch):
    # Noche 23:00 → 07:00: la Salida a colación (05:40) queda más cerca de las 07:00 que la última (08:50), pero manda la última
    marcas = [("2026-09-28", "22:48:10", E), ("2026-09-29", "05:40:00", S), ("2026-09-29", "08:50:00", S)]
    r = _dia(monkeypatch, marcas, fecha="2026-09-28", dia=NOCHE)
    assert r["hora_entrada_real"] == "22:48:10" and r["hora_salida_real"] == "08:50:00"
    assert r["minutos_deuda"] == 0 and r["minutos_salida_adelantada"] == 0
    assert set(r["marcas_consumidas_ids"]) == {1, 2, 3}
    assert abs(r["horas_trabajadas"] - 9.5306) < 0.001


def test_salida_de_mas_muy_tarde_no_paga_extra_automatica(monkeypatch):
    # Con un límite de horas extra configurado (asistencia_max_extras_ordinarias_dia_habil = 240 min), pasado ese límite todo
    # el bloque queda como Jornada Especial pendiente y el turno base se mantiene en sus horas. (Con 0 no hay límite.)
    monkeypatch.setitem(AJUSTES_CONFIGURADOS, "asistencia_max_extras_ordinarias_dia_habil", "240")
    r = _dia(monkeypatch, _d([("06:58:00", E), ("15:02:00", S), ("19:30:00", S)]))
    assert r["estado"] == "OK" and r["minutos_extra_bruto"] == 0 and r["horas_trabajadas"] == 7.5
    assert r["_jornada_especial"] is not None and "Jornada Especial" in r["observaciones"]


# ── Lo que NO cambia ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_salida_a_colacion_y_salida_a_la_hora(monkeypatch):
    r = _dia(monkeypatch, _d([("06:58:00", E), ("11:30:00", S), ("15:01:00", S)]))
    assert r["hora_salida_real"] == "15:01:00" and r["estado"] == "OK" and r["minutos_deuda"] == 0


def test_si_se_va_antes_la_ultima_salida_marca_salida_adelantada(monkeypatch):
    r = _dia(monkeypatch, _d([("06:58:00", E), ("11:30:00", S), ("13:40:00", S)]))
    assert r["hora_salida_real"] == "13:40:00"
    assert r["estado"] == "SALIDA_ADELANTADA" and round(r["minutos_salida_adelantada"]) == 80


def test_rebote_de_menos_de_3_minutos_se_queda_con_la_primera(monkeypatch):
    # Anti-rebote existente (180 s): dos Salidas a 70 s son un doble toque; sigue valiendo la primera
    r = _dia(monkeypatch, _d([("06:58:00", E), ("15:02:00", S), ("15:03:10", S)]))
    assert r["hora_salida_real"] == "15:02:00" and r["estado"] == "OK" and r["minutos_deuda"] == 0


def test_jornada_normal_con_colacion_real_no_cambia(monkeypatch):
    r = _dia(monkeypatch, _d([("06:58:00", E), ("11:30:00", S), ("12:05:00", E), ("15:01:00", S)]))
    assert r["minutos_colacion_real"] == 35 and r["hora_salida_real"] == "15:01:00"
    assert "Salidas seguidas" not in r["observaciones"]


def test_entrada_entrada_entrada_salida_conserva_la_colacion_real(monkeypatch):
    # E · E (salida a colación mal rotulada) · E (regreso) · S: se sigue leyendo como dos tramos con la pausa real de 45 min
    r = _dia(monkeypatch, _d([("06:58:00", E), ("11:45:00", E), ("12:30:00", E), ("15:01:00", S)]))
    assert r["minutos_colacion_real"] == 45 and r["hora_salida_real"] == "15:01:00"
    assert "Dos Entradas seguidas" not in r["observaciones"] and "Salidas seguidas" not in r["observaciones"]


def test_entrada_aislada_sin_salida_sigue_siendo_anomalia(monkeypatch):
    # Dos Entradas a 10 min en un día ya cerrado y nada más: no hay Salida que cerrar, queda como falta de salida
    r = _dia(monkeypatch, _d([("07:00:00", E), ("07:10:00", E)]))
    assert r["estado"] == "ANOMALIA" and "falta salida" in r["observaciones"]


def test_ultima_marca_rotulada_entrada_sigue_cerrando_el_dia(monkeypatch):
    r = _dia(monkeypatch, _d([("07:25:00", E), ("15:38:00", E)]))
    # Llegó 25 min después y salió 38 min después en un horario de tres ciclos: jornada corrida, no atraso (27-10-2026)
    assert r["hora_entrada_real"] == "07:25:00" and r["hora_salida_real"] == "15:38:00" and r["estado"] == "OK"


def test_turno_noche_salida_huerfana_inicial_sigue_descartandose(monkeypatch):
    # Una Salida suelta al comienzo del día (22:52) y la Salida de la mañana (07:02) no se juntan: no tienen Entrada antes
    marcas = [("2026-09-28", "22:52:00", S), ("2026-09-29", "07:02:00", S)]
    r = _dia(monkeypatch, marcas, fecha="2026-09-28", dia=NOCHE)
    assert "Salida huérfana inicial a las 22:52:00." in r["observaciones"]
    assert "Salidas seguidas" not in r["observaciones"]


def test_bolsa_flexible_no_se_toca(monkeypatch):
    bolsa = dict(TURNO, tipo_programacion="BOLSA_FLEXIBLE")
    r = _dia(monkeypatch, _d([("07:52:18", E), ("13:24:04", S), ("17:16:10", S)]), turno=bolsa)
    assert "Salidas seguidas" not in (r["observaciones"] if r else "")
    assert r["hora_salida_real"] == "13:24:04"             # igual que antes


def test_un_solo_ciclo_llegar_tarde_es_siempre_atraso(monkeypatch):
    # Orden del dueño (27-10-2026): la jornada corrida hacia después solo vale en horarios con dos o más ciclos ese día.
    r = _dia(monkeypatch, _d([("07:25:00", E), ("15:38:00", S)]), ciclos=[MANANA])
    assert r["estado"] == "ATRASO" and round(r["minutos_atraso"]) == 25


def test_entre_dos_ciclos_si_sale_antes_de_reponer_el_atraso_sigue_siendo_atraso(monkeypatch):
    # Llegó 25 min después y salió solo 10 min después: no repuso lo que llegó tarde.
    r = _dia(monkeypatch, _d([("07:25:00", E), ("15:10:00", S)]))
    assert r["estado"] == "ATRASO" and round(r["minutos_atraso"]) == 25


def test_quedarse_despues_dentro_del_rango_de_demora_no_repone_el_atraso(monkeypatch):
    # Con «Rango demora salida» de 45 min, salir 15:20 se cuenta como salida a las 15:00: esos minutos no reponen el atraso.
    turno = dict(TURNO, anclaje_salida_minutos=45)
    r = _dia(monkeypatch, _d([("07:10:00", E), ("15:20:00", S)]), turno=turno)
    assert r["estado"] == "ATRASO" and round(r["minutos_atraso"]) == 10
