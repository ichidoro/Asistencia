# -*- coding: utf-8 -*-
"""«Límite HE Diaria en Día Hábil»: 0 (o sin ajuste) = sin límite, todo lo trabajado de más es hora extra; el valor se
guarda en minutos (orden del dueño, 27-10-2026: «todo es hora extra»)."""
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import quantum_matrix_engine as qme  # noqa: E402
from backend.services.quantum_matrix_engine import QuantumMatrixEngine as Q  # noqa: E402

TURNO = {"tipo_programacion": "CICLO_INTELIGENTE", "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0,
         "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "umbral_horas_colacion": 5.5,
         "anclaje_entrada_minutos": 0, "anclaje_salida_minutos": 0}
BODEGA = {"es_libre": 0, "horas_teoricas": 8.0, "hora_entrada": "11:30", "hora_salida": "20:00", "cruza_medianoche": 0}
# Calderón 02-10: 05:54–19:45 son 13 h 51; menos una colación, 13 h 21: 321 minutos sobre las 8 h esperadas.
LARGO = [{"id": 1, "fecha_hora": "2026-10-15 05:54:00", "tipo": "Entrada"},
         {"id": 2, "fecha_hora": "2026-10-15 19:45:00", "tipo": "Salida"}]


def _dia(monkeypatch, ajustes):
    monkeypatch.setattr(qme, "_get_now_local", lambda: datetime(2026, 10, 20, 12, 0))
    monkeypatch.setattr(qme, "REGLAS_MARCAS_ACTIVAS", {})
    return Q.solve_attendance_day(fecha="2026-10-15", empleado_id=1, logs=[dict(m) for m in LARGO], turno_config=dict(TURNO),
                                  dia_config=dict(BODEGA), global_ajustes=ajustes, todos_ciclos_dia=[dict(BODEGA)],
                                  consumidas_previas=set())


def test_con_cero_todo_lo_de_mas_es_hora_extra(monkeypatch):
    r = _dia(monkeypatch, {"asistencia_max_extras_ordinarias_dia_habil": "0"})
    assert round(r["minutos_extra_bruto"]) == 321 and not r.get("_jornada_especial")


def test_sin_el_ajuste_tampoco_hay_limite(monkeypatch):
    r = _dia(monkeypatch, {})
    assert round(r["minutos_extra_bruto"]) == 321 and not r.get("_jornada_especial")


def test_con_cuatro_horas_lo_de_mas_va_a_cobertura(monkeypatch):
    r = _dia(monkeypatch, {"asistencia_max_extras_ordinarias_dia_habil": "240"})
    assert r["minutos_extra_bruto"] == 0 and r["_jornada_especial"]["minutos_trabajados"] == 321


def test_el_valor_se_lee_siempre_en_minutos(monkeypatch):
    # Antes, un valor de 24 o menos se leía como horas (18 minutos = 18 horas) y nunca había cobertura.
    r = _dia(monkeypatch, {"asistencia_max_extras_ordinarias_dia_habil": "18"})
    assert r["_jornada_especial"]["minutos_trabajados"] == 321
