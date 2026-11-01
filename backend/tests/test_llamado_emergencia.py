# -*- coding: utf-8 -*-
"""Llamado de emergencia (01-11-2026): otra jornada del día, separada por 4 h o más y de menos de 3 h, se suma a las horas
extra del día («Horas límite para calificar bloque como jornada especial en vez de horas extras directas»). Antes solo quedaba
anotado y sus minutos no contaban en ningún lado (Wladimir Becerra 24-10-2026, 137 min). En un día libre se suma a la jornada
especial del día."""
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import quantum_matrix_engine as qme  # noqa: E402
from backend.services.quantum_matrix_engine import MultiBlockTensorSolver as M, QuantumMatrixEngine as Q  # noqa: E402

E, S = "Entrada", "Salida"
TURNO = {"tipo_programacion": "CICLO_INTELIGENTE", "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0,
         "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "umbral_horas_colacion": 4.0,
         "anclaje_entrada_minutos": 0, "anclaje_salida_minutos": 0}
MANANA = {"es_libre": 0, "horas_teoricas": 8.0, "hora_entrada": "08:00", "hora_salida": "16:30", "cruza_medianoche": 0}
AJUSTES = {"asistencia_emergencia_gap_horas": "4", "asistencia_emergencia_jornada_limite_horas": "3"}
# Jornada 08:00–16:30 y llamado de 21:00 a 22:17 (77 min)
MARCAS = [{"id": 1, "fecha_hora": "2026-10-20 08:00:00", "tipo": E}, {"id": 2, "fecha_hora": "2026-10-20 16:30:00", "tipo": S},
          {"id": 3, "fecha_hora": "2026-10-20 21:00:00", "tipo": E}, {"id": 4, "fecha_hora": "2026-10-20 22:17:00", "tipo": S}]


def _dia(monkeypatch, marcas, dia):
    monkeypatch.setattr(qme, "_get_now_local", lambda: datetime(2026, 10, 27, 12, 0))
    monkeypatch.setattr(qme, "REGLAS_MARCAS_ACTIVAS", {})
    return Q.solve_attendance_day(fecha="2026-10-20", empleado_id=63, logs=[dict(m) for m in marcas], turno_config=dict(TURNO),
                                  dia_config=dict(dia), global_ajustes=dict(AJUSTES),
                                  todos_ciclos_dia=[dict(dia)] if not dia.get("es_libre") else [], consumidas_previas=set())


def test_el_llamado_queda_como_bloque_aparte():
    res = M.segment_blocks([dict(m) for m in MARCAS], gap_emergencia_horas=4.0, limite_jornada_emergencia_horas=3.0)
    assert [m["id"] for m in res["bloque_principal"]] == [1, 2]
    assert [(e["hora_entrada"], e["hora_salida"], e["minutos"]) for e in res["emergencias"]] == [("21:00", "22:17", 77)]


def test_en_un_dia_de_trabajo_sus_minutos_son_horas_extra(monkeypatch):
    r = _dia(monkeypatch, MARCAS, MANANA)
    assert r["estado"] == "OK"
    assert r["minutos_extra_bruto"] == 77
    assert "[Llamado de Emergencia: 77 min de 21:00 a 22:17]" in r["observaciones"]
    assert "Llamado de emergencia: 77 min sumados a las horas extra." in r["observaciones"]
    assert r["_jornada_especial"] is None


def test_dos_llamados_el_mismo_dia_se_suman(monkeypatch):
    marcas = MARCAS + [{"id": 5, "fecha_hora": "2026-10-21 02:30:00", "tipo": E}, {"id": 6, "fecha_hora": "2026-10-21 03:00:00", "tipo": S}]
    res = M.segment_blocks([dict(m) for m in marcas], gap_emergencia_horas=4.0, limite_jornada_emergencia_horas=3.0)
    assert [e["minutos"] for e in res["emergencias"]] == [77, 30]


def test_en_un_dia_libre_se_suma_a_la_jornada_especial(monkeypatch):
    r = _dia(monkeypatch, MARCAS, {"es_libre": 1, "horas_teoricas": 0})
    je = r["_jornada_especial"]
    # 08:00–16:30 = 510 min menos 30 de colación = 480; más los 77 del llamado
    assert r["estado"] == "JORNADA_ESPECIAL" and je["minutos_trabajados"] == 557
    assert "[Llamado de Emergencia: 21:00 - 22:17 (77 min)]" in je["observaciones"]
    assert r["minutos_extra_bruto"] == 0


def test_una_marca_repetida_de_cero_minutos_no_suma():
    marcas = MARCAS[:2] + [{"id": 3, "fecha_hora": "2026-10-20 21:00:00", "tipo": E}, {"id": 4, "fecha_hora": "2026-10-20 21:00:00", "tipo": S}]
    r = {"_emergencias": [{"hora_entrada": "21:00", "hora_salida": "21:00", "minutos_netos": 0}], "minutos_extra_bruto": 0.0,
         "observaciones": "", "_jornada_especial": None}
    Q._registrar_emergencias(r)
    assert r["minutos_extra_bruto"] == 0 and r["observaciones"] == ""
    assert len(marcas) == 4


def test_sin_marcas_no_hay_colacion(monkeypatch):
    # 01-11-2026: una licencia, vacaciones o inasistencia guardaban los 30 min de colación del horario sin haber trabajado
    r = _dia(monkeypatch, [], MANANA)
    assert r["estado"] == "INASISTENCIA" and r["minutos_colacion_auto"] == 0
