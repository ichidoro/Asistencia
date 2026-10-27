"""Tolerancias de atraso y salida adelantada: salen solo del turno (orden del dueño, 26-10-2026).

Antes el motor traía escrito un minuto fijo: no marcaba atrasos ni salidas de 1 minuto o menos aunque el turno dijera
tolerancia 0, y con «Rango Anticipación Entrada» o «Rango Demora Salida» en 0 igual ajustaba a la hora las marcas a
menos de 60 segundos. Ahora no hay ningún valor fijo: con 0 cuenta todo, aunque sean segundos, y quien administra la
plataforma configura en cada turno la tolerancia que quiera. La deuda del día siempre cuenta el tiempo que falta.
Caso real: Héctor Acevedo, JJV Producción, 28-09-2026, salió 16:29:20 con salida 16:30.
"""
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import quantum_matrix_engine as qme  # noqa: E402
from backend.services.quantum_matrix_engine import QuantumMatrixEngine as Q  # noqa: E402

AJUSTES = {"reglas_marcas_repetidas_minutos": "20"}
AHORA = datetime(2026, 9, 28, 21, 0)
TURNO = {"tipo_programacion": "CICLO_INTELIGENTE", "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0,
         "tolerancia_salida_adelantada": 0, "descuento_colacion_auto": 1, "minutos_colacion_auto": 30,
         "umbral_horas_colacion": 4.0, "anclaje_entrada_minutos": 35, "anclaje_salida_minutos": 0}
LUNES = {"hora_entrada": "07:00", "hora_salida": "16:30", "cruza_medianoche": 0, "es_libre": 0, "horas_teoricas": 9.0,
         "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "anclaje_entrada_minutos": 35, "anclaje_salida_minutos": 0,
         "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0}
E, S = "entrada", "salida"


def _dia(monkeypatch, marcas, **turno):
    monkeypatch.setattr(qme, "_get_now_local", lambda: AHORA)
    t = dict(TURNO, **turno)
    d = dict(LUNES, **{k: v for k, v in turno.items() if k in LUNES})
    logs = [{"id": i + 1, "fecha_hora": f"2026-09-28 {h}", "tipo": tp} for i, (h, tp) in enumerate(marcas)]
    return Q.solve_attendance_day(fecha="2026-09-28", empleado_id=1, logs=logs, turno_config=t, dia_config=d,
                                  global_ajustes=dict(AJUSTES), todos_ciclos_dia=[d], consumidas_previas=set())


def test_hector_con_tolerancia_cero_queda_en_salida_adelantada(monkeypatch):
    r = _dia(monkeypatch, [("06:57:13", E), ("16:29:20", S)])
    assert r["estado"] == "SALIDA_ADELANTADA"
    assert abs(r["minutos_salida_adelantada"] - 0.67) < 0.01
    assert abs(r["minutos_deuda"] - 0.67) < 0.01


def test_con_tolerancia_de_salida_de_un_minuto_el_dia_queda_ok_pero_la_deuda_se_cuenta(monkeypatch):
    r = _dia(monkeypatch, [("06:57:13", E), ("16:29:20", S)], tolerancia_salida_adelantada=1)
    assert r["estado"] == "OK" and r["minutos_salida_adelantada"] == 0
    assert abs(r["minutos_deuda"] - 0.67) < 0.01


def test_una_salida_que_pasa_la_tolerancia_se_marca_completa(monkeypatch):
    r = _dia(monkeypatch, [("06:57:13", E), ("16:28:00", S)], tolerancia_salida_adelantada=1)
    assert r["estado"] == "SALIDA_ADELANTADA" and abs(r["minutos_salida_adelantada"] - 2.0) < 0.01


def test_atraso_de_segundos_con_tolerancia_cero_se_marca(monkeypatch):
    r = _dia(monkeypatch, [("07:00:30", E), ("16:30:00", S)])
    assert r["estado"] == "ATRASO" and abs(r["minutos_atraso"] - 0.5) < 0.01


def test_atraso_dentro_de_la_tolerancia_real_no_se_marca_y_la_deuda_se_cuenta(monkeypatch):
    r = _dia(monkeypatch, [("07:00:30", E), ("16:30:00", S)], tolerancia_retraso_descuento=1)
    assert r["estado"] == "OK" and r["minutos_atraso"] == 0
    assert abs(r["minutos_deuda"] - 0.5) < 0.01


def test_entrada_exacta_y_salida_exacta_no_marcan_nada(monkeypatch):
    r = _dia(monkeypatch, [("07:00:00", E), ("16:30:00", S)])
    assert r["estado"] == "OK" and r["minutos_atraso"] == 0 and r["minutos_salida_adelantada"] == 0


def test_sin_rango_de_anticipacion_cuenta_la_hora_real_de_entrada(monkeypatch):
    # Rango Anticipación Entrada 0: llegar 30 s antes ya no se ajusta a las 07:00; esos 30 s se trabajaron y pagan
    # los 20 s que salió antes. Salió antes menos de lo que llegó antes: jornada corrida, no salida adelantada
    # (orden del dueño, 27-10-2026), y no queda deuda.
    r = _dia(monkeypatch, [("06:59:30", E), ("16:29:40", S)], anclaje_entrada_minutos=0)
    assert r["estado"] == "OK" and r["minutos_salida_adelantada"] == 0 and "Jornada corrida" in r["observaciones"]
    assert r["minutos_deuda"] == 0


def test_con_rango_de_anticipacion_la_entrada_temprana_se_ajusta_a_la_hora(monkeypatch):
    r = _dia(monkeypatch, [("06:59:30", E), ("16:29:40", S)], anclaje_entrada_minutos=35)
    assert abs(r["minutos_deuda"] - 0.33) < 0.02


def test_un_horario_sin_colacion_no_se_guarda():
    # La colación del horario es obligatoria (orden del dueño, 27-10-2026): no hay colación de referencia aparte.
    import pytest
    from fastapi import HTTPException
    from backend.routers.turnos import _exigir_colacion
    from backend.schemas.turno import TurnoCreate
    base = {"nombre": "Prueba", "dias": []}
    with pytest.raises(HTTPException):
        _exigir_colacion(TurnoCreate(**base, descuento_colacion_auto=False, minutos_colacion_auto=30))
    with pytest.raises(HTTPException):
        _exigir_colacion(TurnoCreate(**base, descuento_colacion_auto=True, minutos_colacion_auto=0))
    _exigir_colacion(TurnoCreate(**base, descuento_colacion_auto=True, minutos_colacion_auto=60))
