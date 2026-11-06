# -*- coding: utf-8 -*-
"""Un día que una regla de marcaciones deja «por revisar» (sin calcular) conserva sus horas extra ya decididas.

06-11-2026, Regla 4 (ENTRADA · ENTRADA): al dejar los días en revisión, el sistema borraba la fila de horas extra aunque
estuviera APROBADA o RECHAZADA, y al corregir la marca volvía «por decidir» con 0 minutos autorizados (BECERRA CASTRO,
25-06: 99 min aprobados). Ahora la fila decidida queda tal cual mientras el día está en revisión y, al corregir las marcas,
la decisión vuelve a regir.
"""
import os
from datetime import datetime

import pytest

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import quantum_matrix_engine as qme  # noqa: E402
from backend.services.quantum_matrix_engine import QuantumMatrixEngine as Q  # noqa: E402

E, S = "Entrada", "Salida"
AHORA = datetime(2026, 11, 6, 12, 0)
TURNO = {"tipo_programacion": "CICLO_INTELIGENTE", "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0,
         "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "umbral_horas_colacion": 4,
         "anclaje_entrada_minutos": 15, "anclaje_salida_minutos": 15}
DIA = {"es_libre": 0, "horas_teoricas": 8.0, "hora_entrada": "11:30", "hora_salida": "20:00", "cruza_medianoche": 0}
# Caso real: ENTRADA 09:48 y la SALIDA de las 19:57 rotulada ENTRADA por el reloj
DOS_ENTRADAS = [{"id": 1, "fecha_hora": "2026-06-25 09:48:27", "tipo": E, "manual": 0, "observaciones": None},
                {"id": 2, "fecha_hora": "2026-06-25 19:57:05", "tipo": E, "manual": 0, "observaciones": None}]
CORREGIDO = [dict(DOS_ENTRADAS[0]), dict(DOS_ENTRADAS[1], tipo=S)]
APROBADA = {"estado": "APROBADO", "minutos_bruto": 98.6, "minutos_autorizados": 98.6, "origen": "SISTEMA"}


@pytest.fixture(autouse=True)
def _reglas():
    """Regla 4 como la configuró el dueño: no se calcula sola, queda por revisar."""
    qme.REGLAS_MARCAS_ACTIVAS = {
        "EE": {"secuencia": "EE", "lectura": "NINGUNA", "colacion": "TURNO", "accion": "SOLO_REVISA",
               "opciones_revision": ["RECLASIFICAR"]},
        "ES": {"secuencia": "ES", "lectura": "EXTREMOS", "colacion": "TURNO", "accion": "CALCULA"},
    }
    qme.REGLAS_MARCAS_REBOTE = None
    yield
    qme.REGLAS_MARCAS_ACTIVAS = {}
    qme.REGLAS_MARCAS_REBOTE = None


def _dia(monkeypatch, marcas, he_previo=None):
    monkeypatch.setattr(qme, "_get_now_local", lambda: AHORA)
    return Q.solve_attendance_day(fecha="2026-06-25", empleado_id=63, logs=[dict(m) for m in marcas],
                                  turno_config=TURNO, dia_config=DIA,
                                  global_ajustes={"reglas_marcas_repetidas_minutos": "20"},
                                  todos_ciclos_dia=[DIA], consumidas_previas=set(), he_previo=he_previo)


def test_en_revision_la_hora_extra_aprobada_se_conserva(monkeypatch):
    r = _dia(monkeypatch, DOS_ENTRADAS, he_previo=dict(APROBADA))
    assert r["estado"] == "ANOMALIA" and float(r["horas_trabajadas"]) == 0
    assert r.get("_he_conservar") is True
    assert "Horas extra ya decididas (APROBADO): se conservan hasta corregir el día" in r["observaciones"]


def test_un_dia_en_anomalia_sin_regla_tambien_conserva_la_decision(monkeypatch):
    """«Apagar» una regla vuelve a calcular sus días sin ella: si uno queda en anomalía por sus marcas (caso real:
    GUTIERREZ GUTIERREZ, 05-07, 12 min aprobados), su decisión tampoco se borra."""
    qme.REGLAS_MARCAS_ACTIVAS = {}
    sola = [dict(DOS_ENTRADAS[0])]
    r = _dia(monkeypatch, sola, he_previo=dict(APROBADA))
    assert r["estado"] == "ANOMALIA"
    assert r.get("_he_conservar") is True


def test_en_revision_la_hora_extra_rechazada_se_conserva(monkeypatch):
    r = _dia(monkeypatch, DOS_ENTRADAS, he_previo=dict(APROBADA, estado="RECHAZADO", minutos_autorizados=0))
    assert r.get("_he_conservar") is True


def test_en_revision_sin_decision_no_hay_nada_que_conservar(monkeypatch):
    assert not _dia(monkeypatch, DOS_ENTRADAS).get("_he_conservar")
    assert not _dia(monkeypatch, DOS_ENTRADAS, he_previo=dict(APROBADA, estado="PENDIENTE")).get("_he_conservar")


def test_un_dia_calculado_sin_horas_extra_sigue_borrando_la_fila(monkeypatch):
    """Fuera de la revisión no cambia nada: si el día calculado ya no tiene horas extra, su fila se borra como siempre."""
    corto = [dict(CORREGIDO[0], fecha_hora="2026-06-25 11:30:00"), dict(CORREGIDO[1], fecha_hora="2026-06-25 19:00:00")]
    r = _dia(monkeypatch, corto, he_previo=dict(APROBADA))
    assert r["estado"] != "ANOMALIA"
    assert float(r["minutos_extra_bruto"] or 0) == 0
    assert not r.get("_he_conservar")


def test_al_corregir_la_marca_la_aprobacion_vuelve_a_regir(monkeypatch):
    r = _dia(monkeypatch, CORREGIDO, he_previo=dict(APROBADA))
    assert r["estado"] != "ANOMALIA"
    assert round(float(r["horas_trabajadas"]), 2) == 9.64
    assert round(float(r["minutos_extra_bruto"]), 1) == 98.6
    assert r["_he_estado"] == "APROBADO"
    assert round(float(r["_he_minutos_autorizados"]), 1) == 98.6
    assert not r.get("_he_conservar")
