"""Etapa B1 del plan de bonos (docs/PLAN_BONOS.md): los bonos se calculan con las fechas del período de cierre, no con
el mes calendario (decisión de la persona dueña, 21-11-2026: «cada período tiene sus fechas»).

Antes:
- El Excel y el informe de cierre calculaban con el mes de la fecha en que se sacaban: un período ya cerrado no tenía
  ningún día en ese mes y dejaba a todos como «califica».
- Los días del inicio del período que caen en el mes anterior (26 al 31) no se revisaban.
- La grilla comparaba los días del período con los del mes de la fecha de inicio y multiplicaba el monto.
Datos inventados; sin nombres de personas.
"""
import asyncio
from datetime import date, timedelta

from backend.services.bono_service import BonoService

COMPROMISO = {"nombre": "Compromiso", "activo": 1, "reglas": [{"monto": 70000, "es_proporcional": 0}]}
TRANSPORTE = {"nombre": "Transporte", "activo": 1, "reglas": [{"monto": 30000, "es_proporcional": 1}]}


class _DB:
    def __init__(self, feriados=()):
        self.feriados = list(feriados)
        self.consultas = []

    async def fetch_all(self, sql, params=()):
        self.consultas.append((sql, params))
        if "feriados" in sql:
            return [{"fecha": f} for f in self.feriados]
        return []


def _servicio(db, bonos):
    srv = BonoService(db)

    async def _bonos():
        return bonos
    srv.config_repo.get_all_bonos = _bonos
    return srv


def _dias(inicio, fin):
    d, f = date.fromisoformat(inicio), date.fromisoformat(fin)
    while d <= f:
        yield d
        d += timedelta(days=1)


def _matriz(inicio, fin, faltas=(), extra_inicio=None, extra_fin=None):
    """Lunes a viernes de turno (8 h), sábado y domingo libres. Con extra_* agrega días fuera del período, como los que
    trae la matriz de la grilla."""
    m = {"info": {"tipo_programacion": "CICLO", "turno_dias": {}}}
    for d in _dias(extra_inicio or inicio, extra_fin or fin):
        f = d.isoformat()
        if d.weekday() >= 5:
            m[f] = {"estado": "LIBRE", "horas_teoricas": 0}
        else:
            m[f] = {"estado": "INASISTENCIA" if f in faltas else "OK", "horas_teoricas": 8}
    return m


def _dias_turno(inicio, fin):
    return sum(1 for d in _dias(inicio, fin) if d.weekday() < 5)


def _evaluar(inicio, fin, matriz, empleado=None, bonos=(COMPROMISO, TRANSPORTE), feriados=()):
    emp = {"id": 1, "cargo": "OPERARIO", "tipo_contrato": "Indefinido", "fecha_ingreso": "2020-01-01"}
    emp.update(empleado or {})
    db = _DB(feriados)
    res = asyncio.run(_servicio(db, list(bonos)).evaluar_bonos_directo(
        [emp], [], [], {1: matriz}, fecha_inicio=inicio, fecha_fin=fin))
    return res[1], db


def test_periodo_cerrado_sacado_despues_revisa_sus_dias():
    # Período 26-09 al 25-10 sacado en noviembre: la inasistencia del 08-10 hace perder Compromiso.
    r, _ = _evaluar("2026-09-26", "2026-10-25", _matriz("2026-09-26", "2026-10-25", faltas={"2026-10-08"}))
    assert r["Compromiso"]["califica"] is False
    assert "2026-10-08" in r["Compromiso"]["motivo"]
    turno = _dias_turno("2026-09-26", "2026-10-25")
    assert r["Transporte"]["monto"] == round(30000 * (turno - 1) / turno)


def test_dias_del_inicio_del_periodo_en_el_mes_anterior_se_revisan():
    r, _ = _evaluar("2026-09-26", "2026-10-25", _matriz("2026-09-26", "2026-10-25", faltas={"2026-09-28"}))
    assert r["Compromiso"]["califica"] is False
    assert "2026-09-28" in r["Compromiso"]["motivo"]


def test_periodo_completo_trabajado_paga_el_monto_completo():
    # La grilla trae días fuera del período (antes y después): no cuentan ni multiplican el monto.
    m = _matriz("2026-09-26", "2026-10-25", extra_inicio="2026-09-20", extra_fin="2026-10-31")
    m["2026-09-22"]["estado"] = "INASISTENCIA"   # fuera del período: no cuenta
    r, _ = _evaluar("2026-09-26", "2026-10-25", m)
    assert r["Compromiso"]["califica"] is True and r["Compromiso"]["monto"] == 70000
    assert r["Transporte"]["monto"] == 30000


def test_periodo_con_otras_fechas_y_que_cruza_el_ano():
    # Fechas distintas a 26–25 y en dos años: los feriados se leen por las fechas del período, y se revisan sus días.
    r, db = _evaluar("2025-12-16", "2026-01-15", _matriz("2025-12-16", "2026-01-15", faltas={"2026-01-12"}),
                     feriados=["2026-01-01"])
    assert r["Compromiso"]["califica"] is False and "2026-01-12" in r["Compromiso"]["motivo"]
    sql, params = next(c for c in db.consultas if "feriados" in c[0])
    assert "2025-12-16" in params and "2026-01-15" in params


def test_ingreso_a_mitad_del_periodo_paga_en_proporcion_a_los_dias_del_periodo():
    r, _ = _evaluar("2026-09-26", "2026-10-25", _matriz("2026-09-26", "2026-10-25"),
                    empleado={"fecha_ingreso": "2026-10-12"})
    esperado = round(70000 * _dias_turno("2026-10-12", "2026-10-25") / _dias_turno("2026-09-26", "2026-10-25"))
    assert r["Compromiso"]["califica"] is True and r["Compromiso"]["monto"] == esperado


def test_salida_a_mitad_del_periodo_paga_en_proporcion():
    r, _ = _evaluar("2026-09-26", "2026-10-25", _matriz("2026-09-26", "2026-10-25"),
                    empleado={"fecha_salida": "2026-10-09", "activo": 0})
    esperado = round(70000 * _dias_turno("2026-09-26", "2026-10-09") / _dias_turno("2026-09-26", "2026-10-25"))
    assert r["Compromiso"]["monto"] == esperado


def test_termino_de_contrato_de_una_persona_activa_no_corta_el_bono():
    # En una persona activa la fecha de salida es el término del contrato, que puede renovarse: no se descuenta
    # (la grilla tampoco la usa para las activas).
    r, _ = _evaluar("2026-09-26", "2026-10-25", _matriz("2026-09-26", "2026-10-25"),
                    empleado={"fecha_salida": "2026-10-09", "activo": 1})
    assert r["Compromiso"]["monto"] == 70000


def test_productos_4_lee_los_feriados_por_las_fechas_del_periodo():
    from pathlib import Path
    fuente = (Path(__file__).resolve().parents[1] / "services" / "productos_4_service.py").read_text(encoding="utf-8")
    assert "feriados WHERE fecha BETWEEN ? AND ?" in fuente and "feriados WHERE fecha LIKE" not in fuente


def test_periodo_abierto_sin_faltas_proyecta_el_monto_completo():
    # A mitad del período abierto, quien no ha faltado va con el monto completo (no «proporcional» por los días que
    # aún no llegan).
    srv = _servicio(_DB(), [COMPROMISO])
    emp = {"id": 1, "cargo": "OPERARIO", "tipo_contrato": "Indefinido", "fecha_ingreso": "2020-01-01"}
    r = srv._calificar_bono(emp, COMPROMISO, [], [], _matriz("2026-10-26", "2026-11-25"), "2026-11-10",
                            "2026-10-26", "2026-11-25", set())
    assert r["califica"] is True and r["monto"] == 70000 and r["proporcional"] is False


def test_no_queda_el_mes_calendario_en_el_calculo():
    from pathlib import Path
    fuente = (Path(__file__).resolve().parents[1] / "services" / "bono_service.py").read_text(encoding="utf-8")
    assert "monthrange" not in fuente and "mes_inicio" not in fuente
