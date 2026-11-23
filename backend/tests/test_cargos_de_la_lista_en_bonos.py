"""Etapa B3b del plan de bonos (docs/PLAN_BONOS.md): los cargos de una regla de bono se eligen de la lista de cargos y la
regla guarda su identificador, así un cambio de nombre no la rompe (vacío F). En Configuración → Cargos se puede
renombrar un cargo y unir dos (vacío Q); el nombre anterior queda como alias para la sincronización con BioAlba. La
«asistencia mínima» se quita de la pantalla: no existe en las reglas de Aguacol (decisión de la persona dueña,
22-11-2026). Datos inventados; sin nombres de personas.
"""
import asyncio
from pathlib import Path

from backend.repositories.configuracion import ConfiguracionRepository
from backend.services.bono_service import BonoService

RAIZ = Path(__file__).resolve().parents[2]


def _aplica(regla, cargo_id, cargo_texto="OTRO NOMBRE"):
    emp = {"id": 1, "cargo_id": cargo_id, "cargo": cargo_texto, "tipo_contrato": "Indefinido", "fecha_ingreso": "2020-01-01"}
    bono = {"nombre": "Bono", "reglas": [dict({"monto": 1000}, **regla)], "efecto_inasistencia": "pierde", "efectos": {}}
    return BonoService(None)._calificar_bono(emp, bono, [], [], None, "2026-11-22", "2026-10-26", "2026-11-25", set())["aplica"]


def test_la_regla_compara_el_cargo_de_la_persona_no_su_nombre():
    # El nombre escrito de la persona no importa: manda el cargo de la lista
    assert _aplica({"cargos_req_ids": [6], "cargo_requerido": "NOMBRE VIEJO"}, 6) is True
    assert _aplica({"cargos_req_ids": [6]}, 7) is False
    assert _aplica({"cargos_excl_ids": [7]}, 7) is False
    assert _aplica({"cargos_excl_ids": [7]}, 6) is True
    assert _aplica({}, 6) is True                       # sin cargos elegidos: todos


class _DB:
    def __init__(self, reglas, cargos, alias, cols=("id", "cargo_requerido", "cargos_excluidos")):
        self.reglas, self.cargos, self.alias, self.cols = reglas, cargos, alias, list(cols)
        self.updates, self.inserts = {}, []

    async def get_column_names(self, t):
        return self.cols

    async def execute(self, q, p=()):
        if q.startswith("UPDATE bono_reglas SET cargos_req_ids"):
            self.updates[p[2]] = (p[0], p[1])
        if "INSERT INTO bono_reglas" in q:
            self.inserts.append(p)

        class R:
            lastrowid = 1
        return R()

    async def fetch_all(self, q, p=()):
        if "FROM cargos_alias" in q:
            return self.alias
        if "FROM cargos" in q:
            return self.cargos
        if "FROM bono_reglas" in q:
            return self.reglas
        return []


CARGOS = [{"id": 6, "nombre": "OPERADOR DE LINEA"}, {"id": 7, "nombre": "SUPERVISOR ELABORACI"}]


def test_las_reglas_de_hoy_pasan_a_cargos_de_la_lista():
    db = _DB(reglas=[{"id": 1, "cargo_requerido": "OPERADOR DE LINEA", "cargos_excluidos": None},
                     {"id": 2, "cargo_requerido": None, "cargos_excluidos": "supervisor elaboraci, NOMBRE DE BIOALBA"},
                     {"id": 3, "cargo_requerido": "NO EXISTE", "cargos_excluidos": None}],
             cargos=CARGOS, alias=[{"alias": "NOMBRE DE BIOALBA", "cargo_id": 6}])
    asyncio.run(ConfiguracionRepository(db)._init_cargos_de_reglas())
    assert db.updates[1] == ("6", None)
    assert db.updates[2] == (None, "7,6")               # por su nombre y por su alias de BioAlba
    assert db.updates[3] == ("0", None)                 # pedía un cargo que no está: no lo recibe nadie (no «todos»)


def test_guardar_una_regla_con_cargos_de_la_lista():
    from backend.schemas.bono import BonoReglaCreate
    db = _DB(reglas=[], cargos=CARGOS, alias=[])
    asyncio.run(ConfiguracionRepository(db).create_regla_bono(5, BonoReglaCreate(monto=1000, cargos_req_ids=[6], cargos_excl_ids=[7])))
    p = db.inserts[0]
    assert (p[4], p[5], p[9], p[10]) == ("OPERADOR DE LINEA", "SUPERVISOR ELABORACI", "6", "7")


def test_una_regla_con_nombres_escritos_se_convierte():
    from backend.schemas.bono import BonoReglaCreate
    db = _DB(reglas=[], cargos=CARGOS, alias=[])
    asyncio.run(ConfiguracionRepository(db).create_regla_bono(5, BonoReglaCreate(monto=1000, cargo_requerido="operador de linea")))
    assert db.inserts[0][9] == "6"


def test_pantallas():
    js = (RAIZ / "frontend" / "js" / "configuracion_ui.js").read_text(encoding="utf-8")
    # cargos con casillas de la lista; sin «% Asist.» ni la lista de texto antigua
    assert "_htmlPickerCargos('rule-cargos-req'" in js and "_htmlPickerCargos('rule-cargos-excl'" in js
    assert "cargos_req_ids: _leerPickerCargos(" in js
    assert "rule-asistencia" not in js and "% Asist." not in js and "asistencia sobre" not in js
    assert "appendCargoToInput" not in js and "_populateCargoDropdown" not in js
    # renombrar y unir en la ficha del cargo
    assert "onclick=\"renombrarCargo(" in js and "onclick=\"unirCargo(" in js
    rutas = (RAIZ / "backend" / "routers" / "configuracion.py").read_text(encoding="utf-8")
    assert '"/cargos/{cargo_id}/renombrar/"' in rutas and '"/cargos/{cargo_id}/unir/"' in rutas and '"/cargos/{cargo_id}/uso/"' in rutas
