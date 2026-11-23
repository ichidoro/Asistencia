"""Todo cuenta desde la asignación de turno, no desde la fecha de ingreso de la ficha (dueño, 23-11-2026).

La fecha de ingreso es solo referencial: BioAlba la reemplaza por la fecha de creación del usuario en el reloj y, si la
persona se fue y volvió, mantiene la antigua. Caso real: una persona con turno desde el 05-10 tenía en la ficha ingreso el
08-11 y su bono Compromiso de noviembre salía en proporción (11 de 21 días de turno). Ahora los bonos en proporción, la
meta de la Bolsa, la antigüedad de 4 Productos y el historial de cargos cuentan desde el inicio del turno continuo vigente
en el período. Datos inventados; sin nombres de personas.
"""
from pathlib import Path

from backend.services.inicio_turno import inicio_continuo
from backend.tests.test_bonos_por_periodo import _dias_turno, _evaluar, _matriz

RAIZ = Path(__file__).resolve().parents[2]
FI, FF = "2026-10-26", "2026-11-25"


def test_inicio_del_turno_continuo():
    a = lambda ini, fin=None: {"fecha_inicio": ini, "fecha_fin": fin}
    # un turno desde antes del período: cuenta desde su inicio
    assert inicio_continuo([a("2026-10-05")], FI, FF) == "2026-10-05"
    # turno que empieza dentro del período
    assert inicio_continuo([a("2026-11-17")], FI, FF) == "2026-11-17"
    # cambio de turno sin corte: se mantiene el inicio del primero
    assert inicio_continuo([a("2026-05-01", "2026-09-30"), a("2026-10-01")], FI, FF) == "2026-05-01"
    # se fue y volvió (con días de corte): cuenta desde el turno nuevo
    assert inicio_continuo([a("2026-04-27", "2026-06-15"), a("2026-08-03")], FI, FF) == "2026-08-03"
    # sin turno en el período
    assert inicio_continuo([a("2026-01-01", "2026-06-30")], FI, FF) is None
    assert inicio_continuo([], FI, FF) is None


def test_el_bono_cuenta_desde_el_turno_y_no_desde_la_ficha():
    # Ficha con ingreso a mitad del período, pero turno desde antes: el bono va completo
    r, _ = _evaluar(FI, FF, _matriz(FI, FF), empleado={"fecha_ingreso": "2026-11-08", "inicio_turno": "2026-10-05"})
    assert r["Compromiso"]["califica"] is True and r["Compromiso"]["monto"] == 70000
    # Turno que empieza a mitad del período: en proporción desde ese día, aunque la ficha diga otra fecha
    r, _ = _evaluar(FI, FF, _matriz(FI, FF), empleado={"fecha_ingreso": "2026-10-30", "inicio_turno": "2026-11-02"})
    esperado = round(70000 * _dias_turno("2026-11-02", FF) / _dias_turno(FI, FF))
    assert r["Compromiso"]["monto"] == esperado
    assert "turno desde 2026-11-02" in r["Compromiso"]["motivo"]


def test_la_grilla_y_4_productos_usan_el_inicio_del_turno():
    srv = (RAIZ / "backend/services/asistencia_service.py").read_text(encoding="utf-8")
    assert "emp['inicio_turno'] = inicios_turno.get(eid)" in srv
    assert "calcular_prorrateo_bolsa(\n                        emp.get('inicio_turno')," in srv, "la meta de la Bolsa volvió a la fecha de ingreso"
    p4 = (RAIZ / "backend/services/productos_4_service.py").read_text(encoding="utf-8")
    assert 'fecha_ingreso_str = emp_dict["inicio_turno"]' in p4, "4 Productos volvió a la fecha de ingreso de la ficha"
    labor = (RAIZ / "backend/services/cambio_labor.py").read_text(encoding="utf-8")
    assert 'emp.get("fecha_ingreso")' not in labor, "el historial de cargos volvió a partir desde la fecha de ingreso"


def test_articulo_22_recibe_siempre_4_productos_salvo_baja():
    # Los excluidos de asistencia (art. 22) no tienen turno: reciben siempre 4 Productos, salvo que se den de baja
    # (dueño, 23-11-2026). No se les mira la fecha de ingreso, el turno ni la asistencia.
    p4 = (RAIZ / "backend/services/productos_4_service.py").read_text(encoding="utf-8")
    i_art22 = p4.index('if getattr(emp, "excluido_asistencia", 0):\n                from backend.services.bolsa_prorrateo import baja_del_periodo')
    assert i_art22 < p4.index("if not fecha_ingreso_str:"), "el artículo 22 debe resolverse antes de mirar el turno"
    assert '"califica": not baja,' in p4
