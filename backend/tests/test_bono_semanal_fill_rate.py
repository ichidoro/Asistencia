"""Bono semanal Fill Rate (pedido de la persona dueña, 23-11-2026).

Se evalúa de lunes a domingo, para las personas de los horarios elegidos en el bono, con el monto semanal de la regla de su
cargo (chofer $40.000, peonetas $30.000: configurado, no escrito en el código). Un día marcado «no cumple» hace perder la
semana completa; una justificación hace lo que tenga configurado en el bono (Descanso Operativo: proporcional, porque la
empresa decidió no enviarlo). Cada semana se paga en el período donde cae su domingo. Datos inventados; sin nombres.
"""
from datetime import date, timedelta

from backend.services.bono_semanal import evaluar_persona, semanas_del_periodo

FI, FF = "2026-10-26", "2026-11-25"
DEOP, LICC = 8, 5
BONO = {"id": 9, "nombre": "Fill Rate", "periodicidad": "semanal", "efecto_inasistencia": "pierde",
        "efectos": {DEOP: "proporcion", LICC: "pierde"}}
TURNO = {5: {"es_libre": 1}, 6: {"es_libre": 1}}   # lunes a viernes de turno


def _dias(desde, hasta, estado="OK"):
    d, out = date.fromisoformat(desde), {}
    while d <= date.fromisoformat(hasta):
        out[d.isoformat()] = {"estado": "LIBRE", "horas_teoricas": 0} if d.weekday() >= 5 else {"estado": estado, "horas_teoricas": 8}
        d += timedelta(days=1)
    return out


def _evaluar(dias=None, justif=None, no_cumple=None, desde=None, hasta=None, hoy="2026-11-30", monto=40000):
    sem = semanas_del_periodo(FI, FF)
    return evaluar_persona(BONO, monto, sem, dias if dias is not None else _dias("2026-10-26", "2026-11-22"),
                           justif or {}, no_cumple or {}, set(), TURNO, False, desde, hasta, hoy)


def test_semanas_que_terminan_en_el_periodo():
    sem = semanas_del_periodo(FI, FF)
    assert [(a.isoformat(), b.isoformat()) for a, b in sem] == [
        ("2026-10-26", "2026-11-01"), ("2026-11-02", "2026-11-08"), ("2026-11-09", "2026-11-15"), ("2026-11-16", "2026-11-22")]
    # la semana del 23 al 29-11 termina en el período siguiente: va completa a ese período
    sig = semanas_del_periodo("2026-11-26", "2026-12-25")
    assert sig[0][0].isoformat() == "2026-11-23" and sig[0][1].isoformat() == "2026-11-29"


def test_todas_las_semanas_cumplidas_pagan_completo():
    r = _evaluar()
    assert r["aplica"] and r["califica"] and r["monto"] == 160000 and r["monto_completo"] == 160000
    assert [s["estado"] for s in r["semanas"]] == ["obtiene"] * 4


def test_un_dia_no_cumple_hace_perder_la_semana_completa():
    r = _evaluar(no_cumple={"2026-11-09": "sin carga completa"})
    assert r["monto"] == 120000
    s3 = r["semanas"][2]
    assert s3["estado"] == "pierde" and s3["monto"] == 0
    assert r["perdidos"] == [{"fecha": "2026-11-09", "causa": "No cumple: sin carga completa"}]
    assert r["dias"]["2026-11-09"] == "nc"
    # el peoneta, con su monto
    assert _evaluar(no_cumple={"2026-11-09": None}, monto=30000)["monto"] == 90000


def test_descanso_operativo_deja_la_semana_proporcional():
    j = {"2026-11-04": {"tipo_id": DEOP, "tipo_nombre": "Descanso Operativo"}}
    r = _evaluar(justif=j)
    s2 = r["semanas"][1]
    assert s2["estado"] == "proporcional" and s2["monto"] == round(40000 * 4 / 5)
    assert r["monto"] == 120000 + round(40000 * 4 / 5)


def test_licencia_e_inasistencia_hacen_perder_la_semana():
    j = {"2026-10-27": {"tipo_id": LICC, "tipo_nombre": "Licencia Comun"}}
    dias = _dias("2026-10-26", "2026-11-22")
    dias["2026-11-17"] = {"estado": "INASISTENCIA", "horas_teoricas": 8}
    r = _evaluar(dias=dias, justif=j)
    assert [s["estado"] for s in r["semanas"]] == ["pierde", "obtiene", "obtiene", "pierde"]
    assert r["monto"] == 80000


def test_efecto_sin_configurar_no_paga_y_lo_dice():
    j = {"2026-11-03": {"tipo_id": 99, "tipo_nombre": "Otra"}}
    r = _evaluar(justif=j)
    assert r["semanas"][1]["estado"] == "pierde"
    assert "Falta configurar el efecto de «Otra»" in r["perdidos"][0]["causa"]


def test_turno_que_empieza_a_mitad_de_semana_paga_en_proporcion():
    # turno desde el miércoles 04-11: la semana 02 al 08-11 se paga por 5 de 7 días
    r = _evaluar(desde="2026-11-04")
    assert r["semanas"][0]["estado"] == "sin_turno" and r["semanas"][0]["monto"] == 0
    assert r["semanas"][1]["monto"] == round(40000 * 5 / 7)
    assert r["dias"]["2026-11-02"] == "fuera"


def test_semana_en_curso_parte_en_cero_hasta_su_domingo():
    # 23-11-2026: una semana que no ha terminado no está ganada; recién al cerrar su domingo se sabe
    r = _evaluar(dias=_dias("2026-10-26", "2026-11-18"), hoy="2026-11-18")
    s = r["semanas"][3]
    assert s["estado"] == "en_curso" and s["monto"] == 0 and s["monto_posible"] == 40000
    assert r["monto"] == 120000 and "en curso" in r["motivo"]
    # al terminar la semana, se paga
    assert _evaluar(hoy="2026-11-23")["semanas"][3]["monto"] == 40000


def test_a_quien_se_le_paga_areas_y_horarios():
    # Cualquier bono (mensual o semanal): áreas «todas» o «solo estas» y horarios «todos» o «solo estos» (23-11-2026)
    from backend.services.bono_service import BonoService
    f = BonoService.fuera_de_alcance
    emp = {"area": "LOGISTICA TRADICIONAL", "turno_id": 7}
    # por defecto, todas las áreas y todos los horarios (así quedan los bonos que ya existían)
    assert f(emp, {"area_nombres": ["PRODUCCION"], "filtra_areas": False, "turnos_ids": []}) is None
    # solo estas áreas: las marcadas antes no filtran hasta elegir «solo estas»
    assert f(emp, {"area_nombres": ["PRODUCCION"], "filtra_areas": True}) == "No aplica en su área"
    assert f(emp, {"area_nombres": ["Logistica Tradicional"], "filtra_areas": True}) is None
    # solo estos horarios
    assert f(emp, {"turnos_ids": [3, 4]}) == "Su horario no tiene este bono"
    assert f(emp, {"turnos_ids": [7]}) is None
    assert f({"area": "X", "turno_id": None}, {"turnos_ids": [7]}) == "Su horario no tiene este bono"


def test_un_bono_por_periodo_respeta_el_alcance():
    from backend.tests.test_bonos_por_periodo import COMPROMISO, _evaluar as _ev_mensual, _matriz
    solo_prod = dict(COMPROMISO, filtra_areas=True, area_nombres=["PRODUCCION"])
    r, _ = _ev_mensual(FI, FF, _matriz(FI, FF), empleado={"area": "SEGURIDAD"}, bonos=(solo_prod,))
    assert r["Compromiso"]["aplica"] is False and r["Compromiso"]["motivo"] == "No aplica en su área"
    r, _ = _ev_mensual(FI, FF, _matriz(FI, FF), empleado={"area": "PRODUCCION"}, bonos=(solo_prod,))
    assert r["Compromiso"]["aplica"] is not False and r["Compromiso"]["monto"] == 70000


def test_justificacion_que_cuenta_como_cumplida_no_descuenta():
    # 23-11-2026: el Descanso Operativo no es causal de descuento; configurado «asistido», la semana se paga completa
    bono = dict(BONO, efectos={DEOP: "asistido", LICC: "pierde"})
    r = evaluar_persona(bono, 40000, semanas_del_periodo(FI, FF), _dias("2026-10-26", "2026-11-22"),
                        {"2026-11-04": {"tipo_id": DEOP, "tipo_nombre": "Descanso Operativo"}}, {}, set(), TURNO, False,
                        None, None, "2026-11-30")
    assert r["semanas"][1]["estado"] == "obtiene" and r["semanas"][1]["monto"] == 40000
    assert r["dias"]["2026-11-04"] == "justificado"
