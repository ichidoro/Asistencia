"""Etapa B6 del plan de bonos (docs/PLAN_BONOS.md), orden:
- J: la Bolsa Flexible se reconoce por sus dos nombres de tipo (BOLSA_FLEXIBLE y FLEXIBLE_BOLSA), como el resto del
  sistema; antes el cálculo de bonos solo reconocía uno.
- K: se quita el campo «labor requerida» del esquema de la regla: no existe en la base ni lo usa nadie.
- H: la lista de bonos por persona (Empleados → Asignación masiva) se arma con las mismas reglas que el cálculo de
  bonos (cargo de la lista y contrato); antes comparaba si el nombre del cargo «contenía» el de la regla.
Datos inventados; sin nombres de personas.
"""
import asyncio
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from backend.services.bono_service import BonoService

RAIZ = Path(__file__).resolve().parents[2]


def test_bolsa_por_sus_dos_nombres():
    pi, pf = "2026-09-26", "2026-10-25"
    lic = {"tipo_id": 7, "tipo_nombre": "Licencia", "fecha_inicio": "2026-10-14", "fecha_fin": "2026-10-14"}
    bono = {"nombre": "B", "reglas": [{"monto": 1000}], "efecto_inasistencia": "pierde", "efectos": {7: "pierde"}}
    for tipo in ("BOLSA_FLEXIBLE", "FLEXIBLE_BOLSA"):
        m = {"info": {"tipo_programacion": tipo, "turno_dias": {d: {"es_libre": 1 if d >= 5 else 0} for d in range(7)}}}
        d = date.fromisoformat(pi)
        while d <= date.fromisoformat(pf):
            k = d.isoformat()
            m[k] = {"estado": "LIBRE" if d.weekday() >= 5 else ("LICENCIA" if k == "2026-10-14" else "OK"), "horas_teoricas": 0}
            d += timedelta(days=1)
        emp = {"id": 1, "cargo_id": 6, "tipo_contrato": "Indefinido", "fecha_ingreso": "2020-01-01"}
        r = BonoService(None)._calificar_bono(emp, bono, [], [lic], m, "2026-11-22", pi, pf, set())
        assert r["califica"] is False, tipo


def test_sin_labor_requerida():
    from backend.schemas.bono import BonoReglaBase
    assert "labor_requerida" not in BonoReglaBase.model_fields


def test_lista_de_bonos_por_persona_con_las_reglas_del_calculo():
    from backend.services.configuracion_service import ConfiguracionService
    bonos = [{"id": 1, "nombre": "Por cargo", "activo": True, "tipo": "pesos", "reglas": [{"cargos_req_ids": [6]}]},
             {"id": 2, "nombre": "Excluye", "activo": True, "tipo": "pesos", "reglas": [{"cargos_excl_ids": [6]}]},
             {"id": 3, "nombre": "Temporal", "activo": True, "tipo": "pesos", "reglas": [{"tipo_contrato": "Temporal"}]},
             {"id": 4, "nombre": "4 Productos", "activo": True, "tipo": "beneficio", "reglas": [{}]}]

    class _DB:
        lote = None

        async def execute_batch(self, ops):
            _DB.lote = ops

    class _Repo:
        db = _DB()

        async def get_all_bonos(self):
            return bonos
    # el nombre escrito del cargo ya no importa: manda el cargo de la lista
    emp = SimpleNamespace(id=9, nombre="X", cargo="OTRO NOMBRE QUE CONTIENE CARGO", cargo_id=6, tipo_contrato="Indefinido")
    asignados = asyncio.run(ConfiguracionService(_Repo()).recalculate_assignments(emp))
    assert asignados == ["Por cargo"]
    assert [p[:2] for q, p in _DB.lote if q.startswith("INSERT")] == [(9, 1)]


def test_se_rehace_una_vez_al_arrancar():
    ev = (RAIZ / "backend" / "core" / "events.py").read_text(encoding="utf-8")
    assert "rehacer_asignaciones_una_vez()" in ev
