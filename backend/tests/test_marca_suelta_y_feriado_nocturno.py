# -*- coding: utf-8 -*-
"""Revisión de la Regla 1 (27-10-2026, órdenes del dueño):
- una ENTRADA sola, lejos de la jornada, ya no se pierde sin aviso: cuenta en la secuencia del día y queda anotada;
- una jornada que cruza la medianoche es de feriado si la mayoría de sus horas cae en el feriado."""
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import quantum_matrix_engine as qme  # noqa: E402
from backend.services.quantum_matrix_engine import MultiBlockTensorSolver as M, QuantumMatrixEngine as Q, fecha_feriado_de_la_jornada  # noqa: E402

E, S = "Entrada", "Salida"
# Caso Maximiliano Badilla, sábado 10-10-2026 (Planta Mantención 2, Mañana 04:00–09:00): llegó 04:49, salió 09:19 y volvió a las
# 14:13 para otra jornada sin marcar la salida.
BADILLA = [{"id": 1, "fecha_hora": "2026-10-10 04:49:31", "tipo": E}, {"id": 2, "fecha_hora": "2026-10-10 09:19:53", "tipo": S},
           {"id": 3, "fecha_hora": "2026-10-10 14:13:21", "tipo": E}]
TURNO = {"tipo_programacion": "CICLO_INTELIGENTE", "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0,
         "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "umbral_horas_colacion": 4.0,
         "anclaje_entrada_minutos": 0, "anclaje_salida_minutos": 0}
MANANA_SABADO = {"es_libre": 0, "horas_teoricas": 4.5, "hora_entrada": "04:00", "hora_salida": "09:00", "cruza_medianoche": 0}


def _dia(monkeypatch, reglas=None, marcas=None):
    monkeypatch.setattr(qme, "_get_now_local", lambda: datetime(2026, 10, 27, 12, 0))
    monkeypatch.setattr(qme, "REGLAS_MARCAS_ACTIVAS", reglas or {})
    return Q.solve_attendance_day(fecha="2026-10-10", empleado_id=36, logs=[dict(l) for l in (marcas or BADILLA)],
                                  turno_config=dict(TURNO), dia_config=dict(MANANA_SABADO),
                                  global_ajustes={"asistencia_emergencia_gap_horas": "4", "asistencia_emergencia_jornada_limite_horas": "3"},
                                  todos_ciclos_dia=[dict(MANANA_SABADO)], consumidas_previas=set())


REGLA_1 = {"ES": {"lectura": "EXTREMOS", "colacion": "TURNO", "accion": "CALCULA"}}
REGLA_26_REVISA = {"ESE": {"lectura": "NINGUNA", "colacion": "MEDIDA", "accion": "SOLO_REVISA"}}
REGLA_28_REVISA = {"E": {"lectura": "NINGUNA", "colacion": "TURNO", "accion": "SOLO_REVISA"}}
CON_SALIDA = BADILLA + [{"id": 4, "fecha_hora": "2026-10-10 18:00:00", "tipo": S, "manual": 1}]


def test_la_entrada_sola_queda_en_el_dia_y_no_se_pierde():
    res = M.segment_blocks([dict(l) for l in BADILLA])
    assert [l["id"] for l in res["bloque_principal"]] == [1, 2]
    assert [l["id"] for l in res["marcas_sueltas"]] == [3]
    assert set(res["marcas_consumidas_ids"]) == {1, 2, 3}


def test_primero_se_cierra_la_jornada_de_la_manana_y_la_segunda_sigue_la_regla_28(monkeypatch):
    # Orden del dueño: «primero cerrar la jornada de las 4 a las 9 y luego indicar la anomalía de la segunda jornada»; esa
    # anomalía es de una ENTRADA sola: la Regla 28 encendida la deja en «Por revisar» (y frena el cierre).
    r = _dia(monkeypatch, reglas=dict(REGLA_1, **REGLA_26_REVISA, **REGLA_28_REVISA))
    assert r["estado"] == "ATRASO" and abs(r["minutos_atraso"] - 49.52) < 0.02
    assert r["hora_entrada_real"] == "04:49:31" and r["hora_salida_real"] == "09:19:53"
    assert "Segunda jornada sin SALIDA: ENTRADA de las 14:13:21, falta su SALIDA" in r["observaciones"]
    assert "Revisar las marcas (regla ENTRADA)" in r["observaciones"]


def test_con_la_regla_28_apagada_la_segunda_jornada_solo_queda_anotada(monkeypatch):
    r = _dia(monkeypatch, reglas=dict(REGLA_1, **REGLA_26_REVISA))
    assert r["estado"] == "ATRASO" and "Segunda jornada sin SALIDA: ENTRADA de las 14:13:21" in r["observaciones"]
    assert "Revisar las marcas" not in r["observaciones"]


def test_al_agregar_la_salida_la_segunda_jornada_es_un_mas_dos_por_aprobar(monkeypatch):
    r = _dia(monkeypatch, reglas=dict(REGLA_1, **REGLA_26_REVISA, **REGLA_28_REVISA), marcas=CON_SALIDA)
    assert r["estado"] == "ATRASO" and "Jornada Adicional (+2): 14:13 - 18:00" in r["observaciones"]
    assert "Segunda jornada sin SALIDA" not in r["observaciones"] and "Revisar las marcas" not in r["observaciones"]
    je = r["_jornada_especial"]
    # 14:13:21 a 18:00:00 = 3 h 47 min, bajo el mínimo de 4 h del horario: no descuenta colación
    assert je["estado"] == "JORNADA_ESPECIAL" and je["origen"] == "COBERTURA_TURNO" and je["minutos_trabajados"] == 227
    assert (je["hora_entrada"], je["hora_salida"]) == ("14:13", "18:00") and "(+2): 14:13 - 18:00" in je["observaciones"]
    assert r["minutos_extra_bruto"] == 0                                   # hasta que alguien decida, no son horas extra


def test_la_segunda_jornada_descuenta_su_propia_colacion(monkeypatch):
    # Orden del dueño (27-10-2026): la segunda jornada descuenta colación con la regla del horario.
    marcas = BADILLA + [{"id": 4, "fecha_hora": "2026-10-10 21:00:00", "tipo": S}]
    je = _dia(monkeypatch, reglas=dict(REGLA_1), marcas=marcas)["_jornada_especial"]
    assert je["minutos_trabajados"] == 377                                 # 6 h 47 min menos 30 min de colación


def test_en_un_dia_libre_la_segunda_jornada_se_suma_a_la_jornada_especial(monkeypatch):
    monkeypatch.setattr(qme, "_get_now_local", lambda: datetime(2026, 10, 27, 12, 0))
    monkeypatch.setattr(qme, "REGLAS_MARCAS_ACTIVAS", {})
    marcas = [{"id": 1, "fecha_hora": "2026-10-11 07:00:00", "tipo": E}, {"id": 2, "fecha_hora": "2026-10-11 11:00:00", "tipo": S},
              {"id": 3, "fecha_hora": "2026-10-11 16:00:00", "tipo": E}, {"id": 4, "fecha_hora": "2026-10-11 20:00:00", "tipo": S}]
    r = Q.solve_attendance_day(fecha="2026-10-11", empleado_id=36, logs=marcas, turno_config=dict(TURNO),
                               dia_config={"es_libre": 1, "horas_teoricas": 0},
                               global_ajustes={"asistencia_emergencia_gap_horas": "4", "asistencia_emergencia_jornada_limite_horas": "3"},
                               todos_ciclos_dia=[], consumidas_previas=set())
    je = r["_jornada_especial"]
    assert r["estado"] == "JORNADA_ESPECIAL" and je["origen"] == "DIA_LIBRE" and je["minutos_trabajados"] == 420
    assert je["observaciones"].count("Jornada Adicional (+2)") == 1


def test_el_mas_dos_aprobado_como_horas_extra_se_suma_a_las_de_la_jornada():
    base = {"minutos_extra_bruto": 20.0, "horas_teoricas": 4.5, "observaciones": "",
            "_jornada_adicional": {"minutos_netos": 227}, "_jornada_especial": {"estado": "JORNADA_ESPECIAL", "origen": "COBERTURA_TURNO"}}
    je_previo = {"estado": "HORAS_EXTRAS", "minutos_autorizados": 227, "origen": "COBERTURA_TURNO", "observaciones": "[VALIDADO_COMO_HE]"}
    r = qme.HumanDecisionMerger.apply(dict(base), "2026-10-10", None, je_previo)
    assert r["minutos_extra_bruto"] == 247 and r["_he_minutos_autorizados"] == 227 and r["_he_estado"] == "APROBADO"
    # Una cobertura (sin segunda jornada) sigue como antes: sus minutos son las horas extra del día
    cobertura = {k: v for k, v in base.items() if k != "_jornada_adicional"}
    assert qme.HumanDecisionMerger.apply(cobertura, "2026-10-10", None, je_previo)["minutos_extra_bruto"] == 227


def test_la_salida_olvidada_despues_de_colacion_es_otro_caso_regla_26(monkeypatch):
    # Caso Katherine Galaz 09-10-2026: ENTRADA 06:23, SALIDA 13:06 y vuelta de colación 13:27 sin SALIDA final: es la misma
    # jornada (vuelve antes de las 4 h), le falta la última marca y la Regla 26 la deja por revisar antes de calcular.
    marcas = [{"id": 1, "fecha_hora": "2026-10-10 06:23:42", "tipo": E}, {"id": 2, "fecha_hora": "2026-10-10 13:06:22", "tipo": S},
              {"id": 3, "fecha_hora": "2026-10-10 13:27:53", "tipo": E}]
    r = _dia(monkeypatch, reglas=dict(REGLA_1, **REGLA_26_REVISA), marcas=marcas)
    assert r["estado"] == "ANOMALIA" and "ENTRADA · SALIDA · ENTRADA" in r["observaciones"]
    assert "Segunda jornada sin SALIDA" not in r["observaciones"]


def test_la_noche_del_domingo_antes_del_feriado_es_del_feriado():
    noche = {"hora_entrada": "23:00", "hora_salida": "07:00", "cruza_medianoche": 1}
    assert fecha_feriado_de_la_jornada("2026-10-11", noche) == "2026-10-12"   # 1 h del domingo, 7 h del lunes feriado
    assert fecha_feriado_de_la_jornada("2026-10-12", noche) == "2026-10-13"   # 1 h del feriado, 7 h del martes


def test_una_jornada_de_dia_es_del_mismo_dia_y_un_empate_queda_en_el_que_empieza():
    assert fecha_feriado_de_la_jornada("2026-10-12", {"hora_entrada": "07:00", "hora_salida": "15:00"}) == "2026-10-12"
    assert fecha_feriado_de_la_jornada("2026-10-12", {"hora_entrada": "22:00", "hora_salida": "02:00", "cruza_medianoche": 1}) == "2026-10-12"
    assert fecha_feriado_de_la_jornada("2026-10-12", None) == "2026-10-12"


def test_el_calculo_del_dia_usa_la_fecha_de_feriado_de_la_jornada():
    from pathlib import Path
    servicio = (Path(__file__).resolve().parents[1] / "services" / "asistencia_service.py").read_text(encoding="utf-8")
    assert "fecha_feriado_de_la_jornada(fecha, config_dia)" in servicio and "vispera_feriado" not in servicio
