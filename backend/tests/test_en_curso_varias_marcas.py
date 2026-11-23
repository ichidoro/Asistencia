"""El día de hoy con varias marcas sigue «en curso» (decisión del dueño, 23-11-2026).

Antes, con entrada, salida a colación y vuelta, la última marca se tomaba como la salida del turno: el día mostraba salida
adelantada y deuda mientras la persona seguía trabajando. Ahora sigue EN_CURSO mientras no pasa la salida del horario más
«Esperar la salida hasta ___ min después» y la última marca llegó antes de la salida menos la tolerancia de salida
adelantada. Los dos valores vienen de la pantalla del horario.
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
NOCHE = {"hora_entrada": "22:00", "hora_salida": "06:00", "cruza_medianoche": 1, "es_libre": 0, "horas_teoricas": 8.0,
         "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "anclaje_entrada_minutos": 35, "anclaje_salida_minutos": 0,
         "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0}
E, S = "entrada", "salida"
COLACION = [("06:58:00", E), ("12:00:00", S), ("12:31:00", E)]


def _dia(monkeypatch, marcas, ahora, fecha="2026-09-28", dia=None, feriado=False, **turno):
    monkeypatch.setattr(qme, "_get_now_local", lambda: ahora)
    t = dict(TURNO, **turno)
    d = dict(dia or LUNES)
    logs = [{"id": i + 1, "fecha_hora": h if " " in h else f"{fecha} {h}", "tipo": tp} for i, (h, tp) in enumerate(marcas)]
    return Q.solve_attendance_day(fecha=fecha, empleado_id=1, logs=logs, turno_config=t, dia_config=d, is_holiday=feriado,
                                  global_ajustes={"reglas_marcas_repetidas_minutos": "20"}, todos_ciclos_dia=[d],
                                  consumidas_previas=set())


def test_con_la_colacion_marcada_y_antes_de_la_salida_sigue_en_curso(monkeypatch):
    r = _dia(monkeypatch, COLACION, datetime(2026, 9, 28, 13, 0))
    assert r["estado"] == "EN_CURSO"
    assert r["minutos_deuda"] == 0 and r["minutos_salida_adelantada"] == 0 and r["minutos_extra_bruto"] == 0
    assert r["hora_entrada_real"] == "06:58:00" and r["hora_salida_real"] is None
    assert "Jornada en curso" in r["observaciones"]


def test_pasada_la_espera_del_horario_se_calcula_como_siempre(monkeypatch):
    r = _dia(monkeypatch, COLACION, datetime(2026, 9, 28, 19, 31), ventana_en_curso_minutos=180)
    assert r["estado"] != "EN_CURSO" and r["minutos_deuda"] > 0


def test_la_espera_sale_del_horario(monkeypatch):
    # misma hora (17:00): con 30 min de espera ya pasó; con 180 sigue en curso
    assert _dia(monkeypatch, COLACION, datetime(2026, 9, 28, 17, 1), ventana_en_curso_minutos=30)["estado"] != "EN_CURSO"
    assert _dia(monkeypatch, COLACION, datetime(2026, 9, 28, 17, 1), ventana_en_curso_minutos=180)["estado"] == "EN_CURSO"


def test_una_ultima_marca_dentro_de_la_tolerancia_de_salida_es_la_salida(monkeypatch):
    marcas = [("06:58:00", E), ("16:20:00", S)]
    r = _dia(monkeypatch, marcas, datetime(2026, 9, 28, 16, 25), tolerancia_salida_adelantada=15)
    assert r["estado"] != "EN_CURSO" and r["hora_salida_real"] == "16:20:00"
    # con tolerancia 5, las 16:20 todavía es antes de la salida: sigue en curso
    assert _dia(monkeypatch, marcas, datetime(2026, 9, 28, 16, 25), tolerancia_salida_adelantada=5)["estado"] == "EN_CURSO"


def test_la_salida_a_la_hora_cierra_el_dia(monkeypatch):
    r = _dia(monkeypatch, COLACION + [("16:32:00", S)], datetime(2026, 9, 28, 16, 40))
    assert r["estado"] == "OK" and r["minutos_deuda"] == 0


def test_un_dia_pasado_no_queda_en_curso(monkeypatch):
    r = _dia(monkeypatch, COLACION, datetime(2026, 9, 29, 9, 0))
    assert r["estado"] != "EN_CURSO"


def test_bolsa_flexible_no_cambia(monkeypatch):
    r = _dia(monkeypatch, COLACION, datetime(2026, 9, 28, 13, 0), tipo_programacion="BOLSA_FLEXIBLE")
    assert r["estado"] != "EN_CURSO"


def test_feriado_trabajado_no_cambia(monkeypatch):
    r = _dia(monkeypatch, COLACION, datetime(2026, 9, 28, 13, 0), feriado=True)
    assert r["estado"] != "EN_CURSO"


def test_turno_de_noche_que_termina_hoy_sigue_en_curso(monkeypatch):
    marcas = [("2026-09-28 21:58:00", E), ("2026-09-29 02:00:00", S), ("2026-09-29 02:30:00", E)]
    r = _dia(monkeypatch, marcas, datetime(2026, 9, 29, 3, 0), dia=NOCHE)
    assert r["estado"] == "EN_CURSO" and r["minutos_deuda"] == 0
