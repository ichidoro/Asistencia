# -*- coding: utf-8 -*-
"""Regla 3 (ENTRADA, SALIDA tres veces): «¿Cuál pausa es la colación?» se elige en el asistente (orden del dueño, 26-10-2026).

PARECIDA     = la pausa que más se parece en minutos a la colación del horario (como siempre).
CORTE_UMBRAL = las pausas que terminan antes de la ENTRADA del horario más su «Mínimo para descontar» son permiso;
               entre las demás, la que más se parece en minutos. La hora de corte sale del horario, no del código.
Casos reales: Carlos Muñoz 28-08 (la de hoy tomaba como colación una pausa de las 09:00) y Ramón Durán 19-08.
"""
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import quantum_matrix_engine as qme  # noqa: E402
from backend.services.quantum_matrix_engine import QuantumMatrixEngine as Q  # noqa: E402
from backend.services.reglas_marcas_def import pausas_de, validar_regla  # noqa: E402

TURNO = {"tipo_programacion": "CICLO_INTELIGENTE", "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0,
         "tolerancia_salida_adelantada": 0, "descuento_colacion_auto": 1, "minutos_colacion_auto": 30,
         "umbral_horas_colacion": 6.0, "anclaje_entrada_minutos": 35, "anclaje_salida_minutos": 0}
DIA = {"hora_entrada": "07:00", "hora_salida": "16:30", "cruza_medianoche": 0, "es_libre": 0, "horas_teoricas": 9.0,
       "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "anclaje_entrada_minutos": 35, "anclaje_salida_minutos": 0,
       "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0}
E, S = "entrada", "salida"


def _dia(monkeypatch, marcas, eleccion, **turno):
    monkeypatch.setattr(qme, "_get_now_local", lambda: datetime(2026, 9, 1, 12, 0))
    monkeypatch.setattr(qme, "REGLAS_MARCAS_ACTIVAS", {"ESESES": {
        "secuencia": "ESESES", "lectura": "RELOJ", "colacion": "MEDIDA", "accion": "CALCULA",
        "eleccion_colacion": eleccion}})
    t = dict(TURNO, **turno)
    logs = [{"id": i + 1, "fecha_hora": f"2026-08-28 {h}", "tipo": tp} for i, (h, tp) in enumerate(marcas)]
    return Q.solve_attendance_day(fecha="2026-08-28", empleado_id=1, logs=logs, turno_config=t, dia_config=dict(DIA),
                                  global_ajustes={"reglas_marcas_repetidas_minutos": "20"}, todos_ciclos_dia=[dict(DIA)],
                                  consumidas_previas=set())


MUNOZ = [("07:00:00", E), ("09:00:00", S), ("09:28:00", E), ("13:36:00", S), ("14:09:00", E), ("16:30:00", S)]
DURAN = [("07:00:00", E), ("12:11:00", S), ("13:18:00", E), ("13:29:00", S), ("13:59:00", E), ("16:30:00", S)]


def test_parecida_toma_la_pausa_mas_parecida_en_minutos(monkeypatch):
    r = _dia(monkeypatch, MUNOZ, "PARECIDA")
    assert r["hora_salida_colacion"] == "09:00:00" and r["minutos_permisos_detectados"] == 33


def test_corte_umbral_descarta_la_pausa_que_termina_antes_de_las_13(monkeypatch):
    r = _dia(monkeypatch, MUNOZ, "CORTE_UMBRAL")
    assert r["hora_salida_colacion"] == "13:36:00" and r["minutos_permisos_detectados"] == 28
    assert "13:00" in r["observaciones"]


def test_corte_umbral_con_dos_pausas_despues_del_corte_elige_la_mas_parecida(monkeypatch):
    r = _dia(monkeypatch, DURAN, "CORTE_UMBRAL")
    assert r["hora_salida_colacion"] == "13:29:00" and r["minutos_permisos_detectados"] == 67


def test_con_minimo_cero_decide_como_siempre(monkeypatch):
    r = _dia(monkeypatch, MUNOZ, "CORTE_UMBRAL", umbral_horas_colacion=0.0)
    assert r["hora_salida_colacion"] == "09:00:00"


def test_sin_eleccion_guardada_decide_como_siempre(monkeypatch):
    r = _dia(monkeypatch, MUNOZ, None)
    assert r["hora_salida_colacion"] == "09:00:00"


def test_la_deuda_casi_no_cambia_solo_el_nombre_de_los_minutos(monkeypatch):
    a = _dia(monkeypatch, MUNOZ, "PARECIDA")
    b = _dia(monkeypatch, MUNOZ, "CORTE_UMBRAL")
    assert abs(a["minutos_deuda"] - b["minutos_deuda"]) <= 5


def test_pausas_segun_la_lectura():
    assert pausas_de("ESESES", "RELOJ") == 2
    assert pausas_de("SSESES", "EXTREMOS") == 2
    assert pausas_de("ESES", "RELOJ") == 1
    assert pausas_de("ES", "EXTREMOS") == 0
    assert pausas_de("ESESES", "NINGUNA") == 0


def test_validacion_de_la_respuesta():
    base = {"secuencia": "ESESES", "lectura": "RELOJ", "colacion": "MEDIDA", "accion": "CALCULA", "opciones_revision": []}
    assert validar_regla(dict(base)) == ""
    assert validar_regla(dict(base, eleccion_colacion="CORTE_UMBRAL")) == ""
    assert validar_regla(dict(base, eleccion_colacion="OTRA")) != ""
