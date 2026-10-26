"""Esperas del día de hoy y mínimo para contar hora extra: salen de la configuración, no del código (orden del dueño, 26-10-2026).

Antes el motor traía escritos: 3 horas de espera para cerrar un día con entrada y sin salida (aunque el turno dijera 0),
30 minutos (o el Rango Demora Salida si era mayor) para marcar la inasistencia de un día sin marcas, y 1 minuto como
mínimo para contar una hora extra. Ahora las dos esperas son campos del turno y el mínimo es un ajuste global.
"""
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import quantum_matrix_engine as qme  # noqa: E402
from backend.services.quantum_matrix_engine import QuantumMatrixEngine as Q  # noqa: E402

TURNO = {"tipo_programacion": "CICLO_INTELIGENTE", "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0,
         "tolerancia_salida_adelantada": 0, "descuento_colacion_auto": 1, "minutos_colacion_auto": 30,
         "umbral_horas_colacion": 4.0, "anclaje_entrada_minutos": 35, "anclaje_salida_minutos": 0,
         "ventana_en_curso_minutos": 180, "espera_inasistencia_minutos": 30}
LUNES = {"hora_entrada": "07:00", "hora_salida": "16:30", "cruza_medianoche": 0, "es_libre": 0, "horas_teoricas": 9.0,
         "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "anclaje_entrada_minutos": 35, "anclaje_salida_minutos": 0,
         "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0}
E, S = "entrada", "salida"


def _dia(monkeypatch, marcas, ahora, ajustes=None, **turno):
    monkeypatch.setattr(qme, "_get_now_local", lambda: ahora)
    t = dict(TURNO, **turno)
    logs = [{"id": i + 1, "fecha_hora": f"2026-09-28 {h}", "tipo": tp} for i, (h, tp) in enumerate(marcas)]
    aj = {"reglas_marcas_repetidas_minutos": "20"}
    aj.update(ajustes or {})
    return Q.solve_attendance_day(fecha="2026-09-28", empleado_id=1, logs=logs, turno_config=t, dia_config=dict(LUNES),
                                  global_ajustes=aj, todos_ciclos_dia=[dict(LUNES)], consumidas_previas=set())


NOCHE = datetime(2026, 9, 28, 21, 0)


# ── Mínimo para contar hora extra ──────────────────────────────────

def test_con_minimo_cero_treinta_segundos_de_mas_son_hora_extra(monkeypatch):
    r = _dia(monkeypatch, [("06:57:13", E), ("16:30:30", S)], NOCHE, {"asistencia_minimo_horas_extra_minutos": "0"})
    assert abs(r["minutos_extra_bruto"] - 0.5) < 0.01 and r["minutos_deuda"] == 0


def test_con_minimo_de_un_minuto_treinta_segundos_no_son_hora_extra(monkeypatch):
    r = _dia(monkeypatch, [("06:57:13", E), ("16:30:30", S)], NOCHE, {"asistencia_minimo_horas_extra_minutos": "1"})
    assert r["minutos_extra_bruto"] == 0 and r["minutos_deuda"] == 0


def test_sin_el_ajuste_cuenta_todo(monkeypatch):
    r = _dia(monkeypatch, [("06:57:13", E), ("16:30:30", S)], NOCHE)
    assert abs(r["minutos_extra_bruto"] - 0.5) < 0.01


def test_jornada_exacta_no_genera_hora_extra(monkeypatch):
    r = _dia(monkeypatch, [("07:00:00", E), ("16:30:00", S)], NOCHE, {"asistencia_minimo_horas_extra_minutos": "0"})
    assert r["minutos_extra_bruto"] == 0 and r["minutos_deuda"] == 0


# ── Espera para cerrar un día sin salida (hoy) ─────────────────────

def test_dentro_de_la_espera_el_dia_sigue_en_curso(monkeypatch):
    r = _dia(monkeypatch, [("06:58:00", E)], datetime(2026, 9, 28, 17, 30), ventana_en_curso_minutos=180)
    assert r["estado"] == "EN_CURSO"


def test_pasada_la_espera_el_dia_queda_con_falta_de_salida(monkeypatch):
    r = _dia(monkeypatch, [("06:58:00", E)], datetime(2026, 9, 28, 17, 30), ventana_en_curso_minutos=30)
    assert r["estado"] == "ANOMALIA" and "falta salida" in r["observaciones"]


def test_con_espera_cero_se_cierra_a_la_hora_de_salida(monkeypatch):
    r = _dia(monkeypatch, [("06:58:00", E)], datetime(2026, 9, 28, 16, 31), ventana_en_curso_minutos=0)
    assert r["estado"] == "ANOMALIA"


# ── Espera para marcar inasistencia (hoy, sin marcas) ──────────────

def test_sin_marcas_dentro_de_la_espera_no_se_marca_inasistencia(monkeypatch):
    r = _dia(monkeypatch, [], datetime(2026, 9, 28, 16, 50), espera_inasistencia_minutos=30)
    assert r is None


def test_sin_marcas_pasada_la_espera_se_marca_inasistencia(monkeypatch):
    r = _dia(monkeypatch, [], datetime(2026, 9, 28, 17, 5), espera_inasistencia_minutos=30)
    assert r is not None and r["estado"] == "INASISTENCIA"


def test_con_espera_cero_la_inasistencia_aparece_a_la_hora_de_salida(monkeypatch):
    r = _dia(monkeypatch, [], datetime(2026, 9, 28, 16, 30), espera_inasistencia_minutos=0)
    assert r is not None and r["estado"] == "INASISTENCIA"
