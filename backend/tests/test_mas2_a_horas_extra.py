"""Reglas del dueño (10-11-2026): el +2 (cobertura o segunda jornada) y el llamado de emergencia van directo a las horas extra
del día, por aprobar como cualquier hora extra; la jornada especial (ESP) se valida como jornada EXTRA o pasa a horas extra
por aprobar, y no se rechaza. Ver backend/docs/REGLAS_ASISTENCIA.md, sección 9."""
import copy
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import quantum_matrix_engine as qme  # noqa: E402

Q = qme.QuantumMatrixEngine
RAIZ = Path(__file__).resolve().parents[2]


def test_la_segunda_jornada_va_a_horas_extra_y_se_informa_aparte():
    res = {"minutos_extra_bruto": 30.0, "observaciones": "[Jornada Adicional (+2): 16:00 - 20:00] ", "_jornada_especial": None,
           "_jornada_adicional": {"minutos_netos": 210, "bloques": [{"hora_entrada": "16:00", "hora_salida": "20:00"}]}}
    Q._registrar_jornada_adicional(res, 1, "2026-10-10")
    assert res["minutos_extra_bruto"] == 240 and res["minutos_extra_mas2"] == 210
    assert res["observaciones"].count("Jornada Adicional (+2)") == 1 and "(3.5h netas)" in res["observaciones"]
    assert not res.get("_jornada_especial")


def test_el_llamado_va_a_horas_extra_tambien_en_un_dia_libre():
    je = {"estado": "JORNADA_ESPECIAL", "origen": "DIA_LIBRE", "minutos_trabajados": 420, "observaciones": ""}
    res = {"minutos_extra_bruto": 0.0, "observaciones": "", "_jornada_especial": je,
           "_emergencias": [{"hora_entrada": "21:00", "hora_salida": "22:17", "minutos_netos": 77}]}
    Q._registrar_emergencias(res)
    assert res["minutos_extra_bruto"] == 77 and res["minutos_extra_llamado"] == 77
    assert je["minutos_trabajados"] == 420 and not je.get("llamado_minutos")


def test_en_bolsa_el_mas_dos_suma_a_la_bolsa():
    res = {"horas_trabajadas": 8.0, "observaciones": "", "minutos_extra_bruto": 0.0,
           "_jornada_adicional": {"minutos_netos": 120, "bloques": [{"hora_entrada": "18:00", "hora_salida": "20:00"}]},
           "_emergencias": [{"minutos_netos": 30}]}
    Q._sumar_a_la_bolsa(res)
    assert res["horas_trabajadas"] == 10.5 and res["minutos_extra_bruto"] == 0
    assert "150 min sumados a la bolsa" in res["observaciones"]


def test_la_esp_pasada_a_horas_extra_queda_por_aprobar():
    base = {"minutos_extra_bruto": 0.0, "horas_teoricas": 0.0, "observaciones": "", "estado": "JORNADA_ESPECIAL",
            "_jornada_especial": {"estado": "JORNADA_ESPECIAL", "origen": "FERIADO", "minutos_trabajados": 300}}
    previa = {"estado": "HORAS_EXTRAS", "origen": "FERIADO", "observaciones": "[VALIDADO_COMO_HE]", "minutos_autorizados": 300}
    r = qme.HumanDecisionMerger.apply(copy.deepcopy(base), "2026-09-18", None, previa)
    assert r["minutos_extra_bruto"] == 300 and r["minutos_extra_esp"] == 300 and r["_he_estado"] is None
    # Como jornada EXTRA: no suma horas extra y el día queda EXTRA
    r2 = qme.HumanDecisionMerger.apply(copy.deepcopy(base), "2026-09-18", None, dict(previa, estado="EXTRA", observaciones="[VALIDADO]"))
    assert r2["minutos_extra_bruto"] == 0 and r2["estado"] == "EXTRA"


def test_la_validacion_ya_no_rechaza_ni_valida_el_mas_dos():
    servicio = (RAIZ / "backend" / "services" / "asistencia_service.py").read_text(encoding="utf-8")
    assert "'codigo': 'ESP_NO_SE_RECHAZA'" in servicio and "'codigo': 'SE_APRUEBA_COMO_HORA_EXTRA'" in servicio
    assert "_validar_llamado" not in servicio and "_sincronizar_he_con_llamado" not in servicio
    # Una jornada sin decisión que respetar se borra: también un +2 antiguo y una jornada rechazada
    assert "origen = 'COBERTURA_TURNO' OR estado = 'RECHAZADA' OR (" in servicio.replace('"\n    "', '')


def test_lo_ya_decidido_del_mas_dos_vuelve_a_quedar_por_aprobar():
    repo = (RAIZ / "backend" / "repositories" / "hora_extra.py").read_text(encoding="utf-8")
    assert "QUERY_REABRIR if reabrir else query" in repo and "(QUERY_REABRIR, [d for d in data_list if d.get('reabrir')])" in repo
    assert "estado = excluded.estado," in repo.split("QUERY_REABRIR = ")[1].split('"""')[1]
    # Nada de «50 %» ni validaciones aparte en la ventana: jornada EXTRA u horas extra por aprobar
    modal = (RAIZ / "frontend" / "js" / "marcaciones_manuales.js").read_text(encoding="utf-8")
    assert "columnas.push({ accion: 'RECHAZAR'" not in modal and "th: 'Horas extra<small>por aprobar</small>'" in modal
