# -*- coding: utf-8 -*-
"""Compensar una inasistencia (reglas del dueño, 27-10-2026):
- una jornada EXTRA (día libre, feriado o +2) cubre la inasistencia completa y se gasta (COMPENSATORIA);
- con horas extra, minuto a minuto: deben cubrir todo el turno del día faltado;
- una jornada especial (día libre o feriado) también puede validarse como horas extra, igual que un +2;
- una sola acción en el modal de acciones: se quitaron «Días Compensatorios» y «Reasignar / Mover»."""
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services.compensar_inasistencia import evaluar_opciones  # noqa: E402
from backend.services.quantum_matrix_engine import AttendanceAdjustmentResolver as AAR, HumanDecisionMerger  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
# Caso Mauricio Riquelme: faltó el jueves 08-10 (turno 15:00-23:00, 7 h 30) y trabajó el feriado 12-10 (3,3 h)
INASISTENCIA = {"fecha": "2026-10-08", "estado": "INASISTENCIA", "horas_teoricas": 7.5,
                "hora_entrada_teorica": "15:00", "hora_salida_teorica": "23:00"}
FERIADO = {"fecha": "2026-10-12", "estado": "JORNADA_ESPECIAL", "origen": "FERIADO", "minutos_trabajados": 199,
           "hora_entrada": "13:17:08", "hora_salida": "16:35:42"}


def test_sin_validar_el_feriado_no_sirve_y_las_horas_extra_no_alcanzan():
    op = evaluar_opciones(INASISTENCIA, [FERIADO], 28.7)
    assert op["bloqueo"] is None and op["requerido_min"] == 450 and op["turno"] == "15:00 a 23:00"
    assert op["extras"] == [] and [j["fecha"] for j in op["por_validar"]] == ["2026-10-12"]
    assert op["horas_extra"] == {"disponibles_min": 28.7, "alcanza": False}


def test_una_jornada_extra_cubre_el_dia_completo_sin_importar_sus_horas():
    op = evaluar_opciones(INASISTENCIA, [dict(FERIADO, estado="EXTRA")], 0)
    assert [(j["fecha"], j["tipo"], j["minutos"]) for j in op["extras"]] == [("2026-10-12", "feriado", 199)]


def test_un_mas_dos_extra_tambien_compensa_y_una_jornada_gastada_no_se_ofrece():
    mas_dos = {"fecha": "2026-10-10", "estado": "EXTRA", "origen": "COBERTURA_TURNO", "minutos_trabajados": 227}
    gastada = dict(FERIADO, estado="COMPENSATORIA")
    op = evaluar_opciones(INASISTENCIA, [mas_dos, gastada], 0)
    assert [(j["fecha"], j["tipo"]) for j in op["extras"]] == [("2026-10-10", "+2")] and op["por_validar"] == []


def test_las_horas_extra_deben_cubrir_todo_el_turno():
    assert evaluar_opciones(INASISTENCIA, [], 450)["horas_extra"]["alcanza"] is True
    assert evaluar_opciones(INASISTENCIA, [], 449.4)["horas_extra"]["alcanza"] is False


def test_lo_que_no_se_puede_compensar():
    assert evaluar_opciones(dict(INASISTENCIA, estado="INASISTENCIA_COMPENSADA"), [], 0)["bloqueo"] == "Esta inasistencia ya está compensada."
    assert evaluar_opciones(dict(INASISTENCIA, estado="OK"), [], 0)["bloqueo"] == "Este día no es una inasistencia."
    assert "justificación" in evaluar_opciones(INASISTENCIA, [], 0, justificada=True)["bloqueo"]
    assert "Bolsa Flexible" in evaluar_opciones(INASISTENCIA, [], 0, es_bolsa=True)["bloqueo"]
    assert evaluar_opciones(INASISTENCIA, [], 0, cerradas={"2026-10-08"})["bloqueo"] == "El tramo de este día está cerrado."
    # Una jornada en un día cerrado o ya usada no se ofrece
    extra = dict(FERIADO, estado="EXTRA")
    assert evaluar_opciones(INASISTENCIA, [extra], 0, cerradas={"2026-10-12"})["extras"] == []
    assert evaluar_opciones(INASISTENCIA, [extra], 0, usadas={"2026-10-12"})["extras"] == []


def test_el_motor_solo_compensa_con_horas_extra_si_cubren_todo_el_turno():
    dia = {"estado": "INASISTENCIA", "horas_teoricas": 7.5, "minutos_deuda": 0, "observaciones": ""}
    parcial = AAR.apply(dict(dia), "2026-10-08", None, [{"minutos": 405}], 0)
    assert parcial["estado"] == "INASISTENCIA" and "Horas extra insuficientes para compensar: 405 de 450 min" in parcial["observaciones"]
    completa = AAR.apply(dict(dia), "2026-10-08", None, [{"minutos": 450}], 0)
    assert completa["estado"] == "INASISTENCIA_COMPENSADA"


def test_el_dia_de_la_jornada_usada():
    inter = {"fecha_origen": "2026-10-08", "fecha_destino": "2026-10-12"}
    feriado = AAR.apply({"estado": "JORNADA_ESPECIAL", "horas_teoricas": 0, "observaciones": "", "_jornada_especial": {"x": 1}},
                        "2026-10-12", inter, None, 0)
    assert feriado["estado"] == "JORNADA_COMPENSATORIA" and feriado["_jornada_especial"] is None
    # Un +2 usado: el día tenía turno, la jornada principal no cambia (solo la segunda jornada queda gastada)
    mas_dos = AAR.apply({"estado": "OK", "horas_teoricas": 4.5, "observaciones": "", "minutos_extra_bruto": 0},
                        "2026-10-12", inter, None, 0)
    assert mas_dos["estado"] == "OK"
    falta = AAR.apply({"estado": "INASISTENCIA", "horas_teoricas": 7.5, "observaciones": ""}, "2026-10-08", inter, None, 0)
    assert falta["estado"] == "INASISTENCIA_COMPENSADA"


def test_una_jornada_gastada_es_una_decision_humana_que_el_recalculo_conserva():
    previa = {"estado": "COMPENSATORIA", "observaciones": "[VALIDADO] [COMPENSA_INASISTENCIA 2026-10-08]", "minutos_autorizados": 199}
    assert HumanDecisionMerger.je_is_validated(previa)
    assert HumanDecisionMerger.merge_je_record({"estado": "JORNADA_ESPECIAL"}, previa)["estado"] == "COMPENSATORIA"


def test_una_jornada_especial_tambien_puede_pasar_a_horas_extra():
    servicio = (RAIZ / "backend" / "services" / "asistencia_service.py").read_text(encoding="utf-8")
    assert "DIA_LIBRE_NO_HE" not in servicio and "origen_he = jornada_dict.get('origen')" in servicio
    router = (RAIZ / "backend" / "routers" / "asistencia.py").read_text(encoding="utf-8")
    # El aviso del servidor llega a la pantalla (antes se convertía en «Error interno del servidor»)
    assert "    except HTTPException:\n        # El aviso (400) y el conflicto de concurrencia (409)" in router


def test_queda_una_sola_accion_para_compensar():
    index = (RAIZ / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'id="btn-reasignar-turno"' not in index and 'id="btn-quitar-compensacion"' in index
    assert "/static/js/compensar_inasistencia.js" in index and ">Compensar inasistencia<" in index
    grilla = (RAIZ / "frontend" / "js" / "marcaciones_ui.js").read_text(encoding="utf-8")
    assert "<span class=\"fw-bold\">Días Compensatorios</span>" not in grilla


def test_compensar_se_asigna_por_rol_con_un_solo_permiso():
    # Orden del dueño (27-10-2026): la acción se asigna según el perfil, desde Seguridad → Roles
    roles = (RAIZ / "frontend" / "js" / "seguridad_ui.js").read_text(encoding="utf-8")
    assert "'marcaciones.compensar':     { module: 'MARCACIONES', action: 'Compensar Inasistencias'" in roles
    assert "action: 'Días Compensatorios'" not in roles
    router = (RAIZ / "backend" / "routers" / "asistencia.py").read_text(encoding="utf-8")
    for ruta in ('@router.get("/compensar-inasistencia/opciones/")', '@router.post("/compensar-inasistencia/")',
                 '@router.delete("/compensar-inasistencia/")'):
        bloque = router[router.index(ruta):router.index(ruta) + 700]
        assert 'RequirePermission("marcaciones.compensar")' in bloque, ruta


def test_los_textos_de_la_ventana_sobreviven_al_minificador():
    import rjsmin
    for archivo, texto in (("compensar_inasistencia.js", "Esa jornada deja de pagarse con el monto fijo y queda como jornada compensatoria."),
                           ("compensar_inasistencia.js", " (después de pagar la deuda del tramo)"),
                           ("marcaciones_manuales.js", "'OK')} · ${asist.hora_entrada_real"),
                           ("marcaciones_manuales.js", "</strong> Trabajo en ")):
        js = (RAIZ / "frontend" / "js" / archivo).read_text(encoding="utf-8")
        assert texto in rjsmin.jsmin(js), (archivo, texto)
