"""Entrada, Entrada, Salida: falta la salida a colación (Ciclo Inteligente).

Caso real: JJV Producción, martes 29-09-2026, marcas 06:40:19 Entrada · 13:17:43 Entrada · 16:29:22 Salida.
El motor emparejaba Entrada→Entrada (hueco >= 20 min) como una jornada completa: cerraba el día a las 13:17 con 192 min de
deuda y dejaba la Salida real de las 16:29 afuera. Una Entrada no puede cerrar la jornada si después viene una Salida.
"""
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import quantum_matrix_engine as qme  # noqa: E402
from backend.services.quantum_matrix_engine import QuantumMatrixEngine as Q  # noqa: E402

# Ajustes de la pestaña Reglas de marcaciones tal como están configurados en producción
# (el cálculo los lee de la tabla `ajustes`; el código no trae el número).
AJUSTES_CONFIGURADOS = {"reglas_marcas_repetidas_minutos": "20"}

AHORA = datetime(2026, 9, 29, 21, 0)

# Configuración real de JJV Producción (sin datos de personas)
TURNO = {"tipo_programacion": "CICLO_INTELIGENTE", "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0,
         "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "umbral_horas_colacion": 4.0,
         "anclaje_entrada_minutos": 35, "anclaje_salida_minutos": 0}
MARTES = {"hora_entrada": "07:00", "hora_salida": "16:30", "cruza_medianoche": 0, "es_libre": 0, "horas_teoricas": 9.0,
          "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "anclaje_entrada_minutos": 35, "anclaje_salida_minutos": 0,
          "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0}
E, S = "entrada", "salida"


def _dia(monkeypatch, marcas, turno=None):
    monkeypatch.setattr(qme, "_get_now_local", lambda: AHORA)
    logs = [{"id": i + 1, "fecha_hora": f"2026-09-29 {h}", "tipo": t} for i, (h, t) in enumerate(marcas)]
    return Q.solve_attendance_day(fecha="2026-09-29", empleado_id=1, logs=logs, turno_config=turno or TURNO, dia_config=MARTES,
                                  global_ajustes=dict(AJUSTES_CONFIGURADOS), todos_ciclos_dia=[MARTES], consumidas_previas=set())


def test_dos_entradas_y_salida_cierra_con_la_salida_real(monkeypatch):
    r = _dia(monkeypatch, [("06:40:19", E), ("13:17:43", E), ("16:29:22", S)])
    assert r["hora_entrada_real"] == "06:40:19"
    assert r["hora_salida_real"] == "16:29:22"          # antes: 13:17:43 (la 2ª Entrada tomada como salida)
    assert r["estado"] == "OK"
    assert r["minutos_deuda"] < 2                        # antes: 192
    assert r["minutos_salida_adelantada"] == 0
    assert "Dos Entradas seguidas" in r["observaciones"]  # queda avisado que falta una Salida
    assert set(r["marcas_consumidas_ids"]) == {1, 2, 3}


def test_entrada_entrada_sin_salida_posterior_sigue_valiendo_como_salida_mal_rotulada(monkeypatch):
    # La última marca del día quedó rotulada Entrada: sigue cerrando el día (como siempre)
    r = _dia(monkeypatch, [("07:25:00", E), ("15:38:00", E)])
    assert r["hora_entrada_real"] == "07:25:00" and r["hora_salida_real"] == "15:38:00"
    assert "Dos Entradas seguidas" not in r["observaciones"]


def test_salida_a_colacion_rotulada_como_entrada_se_mantiene(monkeypatch):
    # E, E (salida a colación mal rotulada), E (regreso), S: se sigue leyendo como dos tramos con 30 min de colación
    r = _dia(monkeypatch, [("06:40:19", E), ("12:30:00", E), ("13:00:00", E), ("16:29:22", S)])
    assert r["hora_salida_real"] == "16:29:22"
    assert r["minutos_colacion_real"] == 30
    assert "Dos Entradas seguidas" not in r["observaciones"]


def test_entrada_de_regreso_despues_de_la_colacion_sin_salida(monkeypatch):
    # E, S (colación), E (regreso), E (otra pausa sin salida), S: el día cierra con la Salida real
    r = _dia(monkeypatch, [("06:40:19", E), ("12:30:00", S), ("13:00:00", E), ("14:30:00", E), ("16:29:22", S)])
    assert r["hora_salida_real"] == "16:29:22"
    assert r["estado"] == "OK" and r["minutos_deuda"] < 2
    assert r["minutos_colacion_real"] == 30


def test_jornada_normal_no_cambia(monkeypatch):
    r = _dia(monkeypatch, [("06:58:00", E), ("12:35:00", S), ("13:10:00", E), ("16:31:00", S)])
    assert r["hora_entrada_real"] == "06:58:00" and r["hora_salida_real"] == "16:31:00"
    assert r["minutos_colacion_real"] == 35
    assert "Dos Entradas seguidas" not in r["observaciones"]


def test_bolsa_flexible_no_se_toca(monkeypatch):
    bolsa = dict(TURNO, tipo_programacion="BOLSA_FLEXIBLE")
    r = _dia(monkeypatch, [("06:40:19", E), ("13:17:43", E), ("16:29:22", S)], turno=bolsa)
    assert "Dos Entradas seguidas" not in (r["observaciones"] if r else "")
