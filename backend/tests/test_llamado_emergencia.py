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


def test_en_un_dia_libre_queda_aparte_de_la_jornada_especial(monkeypatch):
    # Orden del dueño (05-11-2026): en un día que no tenía que trabajar el llamado no se suma a la jornada especial; queda
    # aparte, por validar, con su propio estado en la grilla.
    r = _dia(monkeypatch, MARCAS, {"es_libre": 1, "horas_teoricas": 0})
    je = r["_jornada_especial"]
    # 08:00–16:30 = 510 min menos 30 de colación = 480; el llamado (77) va aparte
    assert r["estado"] == "JORNADA_ESPECIAL" and je["minutos_trabajados"] == 480
    assert (je["llamado_tipo"], je["llamado_hora_entrada"], je["llamado_hora_salida"], je["llamado_minutos"], je["llamado_estado"]) == \
        ("EMERGENCIA", "21:00", "22:17", 77, "PENDIENTE")
    # La nota del día aparece una sola vez (antes se repetía con otro formato)
    assert je["observaciones"].count("Llamado de Emergencia") == 1
    assert r["minutos_extra_bruto"] == 0


def test_el_llamado_aprobado_como_horas_extra_suma_a_las_del_dia():
    base = {"minutos_extra_bruto": 0.0, "horas_teoricas": 0.0, "observaciones": "", "estado": "JORNADA_ESPECIAL",
            "_jornada_especial": {"estado": "JORNADA_ESPECIAL", "origen": "DIA_LIBRE", "minutos_trabajados": 420,
                                  "llamado_minutos": 137, "llamado_estado": "PENDIENTE", "llamado_minutos_autorizados": 0}}
    previa = {"estado": "EXTRA", "minutos_autorizados": 420, "origen": "DIA_LIBRE", "observaciones": "[VALIDADO]",
              "llamado_minutos": 137, "llamado_estado": "HORAS_EXTRAS", "llamado_minutos_autorizados": 137}
    he = {"estado": "APROBADO", "origen": "LLAMADO_EMERGENCIA", "minutos_autorizados": 137}
    import copy
    r = qme.HumanDecisionMerger.apply(copy.deepcopy(base), "2026-10-24", he, previa)
    assert r["estado"] == "EXTRA" and r["_jornada_especial"]["llamado_estado"] == "HORAS_EXTRAS"
    assert r["minutos_extra_bruto"] == 137 and r["_he_minutos_autorizados"] == 137 and r["_he_estado"] == "APROBADO"
    # Las dos partes como horas extra: la fila guarda 557; la jornada aporta 420 y el llamado 137 (no se cuenta dos veces)
    previa2 = dict(previa, estado="HORAS_EXTRAS", observaciones="[VALIDADO_COMO_HE]")
    he2 = {"estado": "APROBADO", "origen": "DIA_LIBRE", "minutos_autorizados": 557}
    r2 = qme.HumanDecisionMerger.apply(copy.deepcopy(base), "2026-10-24", he2, previa2)
    assert r2["minutos_extra_bruto"] == 557 and r2["_he_minutos_autorizados"] == 557
    # Llamado rechazado: no suma nada
    previa3 = dict(previa, llamado_estado="RECHAZADA", llamado_minutos_autorizados=0)
    r3 = qme.HumanDecisionMerger.apply(copy.deepcopy(base), "2026-10-24", None, previa3)
    assert r3["minutos_extra_bruto"] == 0 and r3["_he_estado"] is None


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
