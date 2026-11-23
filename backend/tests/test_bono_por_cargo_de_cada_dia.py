"""Etapa B4 del plan de bonos (docs/PLAN_BONOS.md): el bono usa el cargo de cada día del período (historial de cargos con
fecha). Si la persona cambió de labor a mitad de período, un bono ligado a un cargo se paga en proporción a los días en
ese cargo (decisión de la persona dueña, 22-11-2026). Un bono que no depende del cargo no cambia, salvo que el cargo
nuevo esté excluido. Sin cambios de labor el cálculo es el de siempre. Datos inventados; sin nombres de personas.
"""
import asyncio
from datetime import date, timedelta

from backend.services.bono_service import BonoService

PI, PF = "2026-09-26", "2026-10-25"
CAMBIO = "2026-10-12"                       # desde aquí, cargo 6 (antes, cargo 8)
B = lambda nombre, reglas: {"nombre": nombre, "reglas": reglas, "efecto_inasistencia": "pierde", "efectos": {}}
CLORO = B("Cloro", [{"monto": 50000, "cargos_req_ids": [8]}])
OPERADOR = B("Operador", [{"monto": 30000, "cargos_req_ids": [6]}])
COMPROMISO = B("Compromiso", [{"monto": 70000, "cargos_excl_ids": [99]}])
SUPERVISOR = B("Supervisor", [{"monto": 100000, "cargos_req_ids": [8]}, {"monto": 80000, "cargos_req_ids": [6]}])


def _matriz(faltas=()):
    m = {"info": {"tipo_programacion": "CICLO", "turno_dias": {}}}
    d, f = date.fromisoformat(PI), date.fromisoformat(PF)
    while d <= f:
        k = d.isoformat()
        m[k] = {"estado": "LIBRE", "horas_teoricas": 0} if d.weekday() >= 5 else {"estado": "INASISTENCIA" if k in faltas else "OK", "horas_teoricas": 8}
        d += timedelta(days=1)
    return m


def _turno(a, b):
    d, f, n = date.fromisoformat(a), date.fromisoformat(b), 0
    while d <= f:
        n += d.weekday() < 5
        d += timedelta(days=1)
    return n


TRAMOS = [{"cargo_id": 8, "desde": "2020-01-01", "hasta": "2026-10-11"}, {"cargo_id": 6, "desde": CAMBIO, "hasta": None}]


def _cal(bono, tramos=TRAMOS, cargo_actual=6, faltas=()):
    emp = {"id": 1, "cargo_id": cargo_actual, "tipo_contrato": "Indefinido", "fecha_ingreso": "2020-01-01", "_tramos_cargo": tramos}
    return BonoService(None)._calificar_bono(emp, bono, [], [], _matriz(faltas), "2026-11-22", PI, PF, set())


ANTES, DESPUES, TODO = _turno(PI, "2026-10-11"), _turno(CAMBIO, PF), _turno(PI, PF)


def test_bono_del_cargo_en_proporcion_a_los_dias_en_cada_labor():
    assert _cal(CLORO)["monto"] == round(50000 * ANTES / TODO)
    assert _cal(OPERADOR)["monto"] == round(30000 * DESPUES / TODO)


def test_una_falta_en_la_labor_anterior_hace_perder_solo_ese_bono():
    falta = "2026-10-01"                    # cuando tenía el cargo 8
    assert _cal(CLORO, faltas={falta})["califica"] is False
    assert _cal(OPERADOR, faltas={falta})["monto"] == round(30000 * DESPUES / TODO)


def test_un_bono_que_no_depende_del_cargo_no_cambia():
    assert _cal(COMPROMISO)["monto"] == 70000
    # salvo que el cargo nuevo esté excluido: se paga por los días antes del cambio
    excl = B("Compromiso", [{"monto": 70000, "cargos_excl_ids": [6]}])
    assert _cal(excl)["monto"] == round(70000 * ANTES / TODO)


def test_dos_reglas_con_montos_distintos_en_el_mismo_bono():
    esperado = round((100000 * ANTES + 80000 * DESPUES) / TODO)
    assert _cal(SUPERVISOR)["monto"] == esperado


def test_sin_cambio_de_labor_es_el_calculo_de_siempre():
    un_tramo = [{"cargo_id": 6, "desde": "2020-01-01", "hasta": None}]
    assert _cal(OPERADOR, tramos=un_tramo)["monto"] == 30000
    assert _cal(OPERADOR, tramos=[])["monto"] == 30000
    assert _cal(CLORO, tramos=un_tramo)["aplica"] is False


def test_la_ficha_o_bioalba_corrigen_el_tramo_vigente_sin_partir_el_periodo():
    from backend.repositories.empleado import EmpleadoRepository

    class _DB:
        def __init__(self):
            self.updates = []

        async def fetch_one(self, q, p=()):
            return {"id": 5, "cargo_id": 8}

        async def execute(self, q, p=()):
            self.updates.append((q, p))
    db = _DB()
    asyncio.run(EmpleadoRepository(db).corregir_cargo_vigente(1, 6))
    assert db.updates == [("UPDATE historial_cargos SET cargo_id = ? WHERE id = ?", (6, 5))]
