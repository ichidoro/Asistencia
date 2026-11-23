"""Etapa B3d del plan de bonos (docs/PLAN_BONOS.md): 4 Productos deja de buscar el bono llamado «compromiso» y de
cambiarle las reglas en el código (vacío P). Tiene su propio bono «4 Productos», un beneficio en especie (sin monto en
pesos) que se configura en Configuración → Bonos como cualquier otro, y 4 Productos lo lee por su identificador
(decisión de la persona dueña, 22-11-2026: «configurarlo como un bono y no esté en el código»).
- Al crearse se llena con lo de hoy: una regla para todos y los efectos de las faltas de Compromiso; activo solo si
  Compromiso lo estaba.
- No sale en el informe de cierre, el Excel ni la grilla; no se descuenta en proporción; no se puede eliminar.
Datos inventados; sin nombres de personas.
"""
import asyncio
from pathlib import Path

import pytest

from backend.repositories.configuracion import ConfiguracionRepository

RAIZ = Path(__file__).resolve().parents[2]


class _DB:
    def __init__(self, compromiso=None, efectos_comp=(), tipos=(), ajuste=None, cols=("id", "nombre", "tipo")):
        self.compromiso, self.efectos_comp, self.tipos, self.ajuste, self.cols = compromiso, list(efectos_comp), list(tipos), ajuste, list(cols)
        self.inserts, self.efectos = [], []

    async def get_column_names(self, t):
        return self.cols

    async def table_exists(self, t):
        return True

    async def fetch_one(self, q, p=()):
        if "FROM ajustes" in q:
            return {"valor": self.ajuste} if self.ajuste else None
        if "LOWER(TRIM(nombre)) = 'compromiso'" in q:
            return self.compromiso
        return None

    async def fetch_all(self, q, p=()):
        if "FROM bono_efectos" in q:
            return self.efectos_comp
        if "FROM justificacion_tipos" in q:
            return self.tipos
        return []

    async def execute(self, q, p=()):
        self.inserts.append((q.split("(")[0].strip(), p))

        class R:
            lastrowid = 50
        return R()

    async def execute_batch(self, ops):
        self.efectos += [p for _, p in ops]


def test_se_crea_con_lo_de_compromiso():
    db = _DB(compromiso={"id": 1, "activo": 1, "efecto_inasistencia": "pierde"},
             efectos_comp=[{"tipo_id": 10, "efecto": "asistido"}, {"tipo_id": 11, "efecto": "pierde"}, {"tipo_id": 12, "efecto": "proporcion"}])
    asyncio.run(ConfiguracionRepository(db)._init_bono_productos_4())
    bono = next(p for q, p in db.inserts if q == "INSERT INTO bonos")
    assert bono[0] == "4 Productos" and bono[2] == 1 and bono[3] == "pierde"            # activo como Compromiso
    regla = next(p for q, p in db.inserts if q == "INSERT INTO bono_reglas")
    assert regla[0] == 50 and len(regla) == 2                                          # una regla para todos, sin monto, con su fecha
    assert sorted(db.efectos) == [(50, 10, "asistido"), (50, 11, "pierde"), (50, 12, "pierde")]   # en especie: sin proporción
    ajuste = next(p for q, p in db.inserts if q == "INSERT INTO ajustes")
    assert ajuste[:2] == ("bono_productos_4", "50")


def test_sin_compromiso_activo_queda_sin_uso_como_antes():
    db = _DB(compromiso={"id": 1, "activo": 0, "efecto_inasistencia": "pierde"})
    asyncio.run(ConfiguracionRepository(db)._init_bono_productos_4())
    assert next(p for q, p in db.inserts if q == "INSERT INTO bonos")[2] == 0


def test_no_se_vuelve_a_crear():
    db = _DB(ajuste="50")
    asyncio.run(ConfiguracionRepository(db)._init_bono_productos_4())
    assert not any(q == "INSERT INTO bonos" for q, _ in db.inserts)


def test_productos_4_lee_su_bono_por_identificador():
    fuente = (RAIZ / "backend" / "services" / "productos_4_service.py").read_text(encoding="utf-8")
    assert "get_id_bono_productos_4()" in fuente
    assert '== "compromiso"' not in fuente and "compromiso_beneficio" not in fuente and "import copy" not in fuente


def test_el_beneficio_no_sale_en_los_bonos_en_pesos():
    from backend.services.bono_service import BonoService

    class _Repo:
        async def get_all_bonos(self):
            return [{"id": 1, "nombre": "En pesos", "activo": True, "tipo": "pesos", "reglas": [{"monto": 1000}],
                     "efecto_inasistencia": "pierde", "efectos": {}},
                    {"id": 2, "nombre": "4 Productos", "activo": True, "tipo": "beneficio", "reglas": [{"monto": 0}],
                     "efecto_inasistencia": "pierde", "efectos": {}}]

    class _DBf:
        async def fetch_all(self, q, p=()):
            return []
    srv = BonoService(_DBf())
    srv.config_repo = _Repo()
    r = asyncio.run(srv.evaluar_bonos_directo([{"id": 1, "fecha_ingreso": "2020-01-01"}], [], [], {}, fecha_inicio="2026-10-26", fecha_fin="2026-11-25"))
    assert list(r[1]) == ["En pesos"]
    for f in ("backend/routers/asistencia.py", "backend/services/empleado_service.py", "backend/services/informe_cierre_pdf.py"):
        assert "beneficio" in (RAIZ / f).read_text(encoding="utf-8"), f


class _RepoV:
    async def get_ids_tipos_justificacion(self):
        return [10]

    async def get_ids_bonos(self):
        return [2]

    async def get_tipos_de_bonos(self):
        return {2: "beneficio"}

    async def get_id_bono_productos_4(self):
        return 2


def test_el_beneficio_no_se_descuenta_en_proporcion_ni_se_elimina():
    from fastapi import HTTPException
    from backend.schemas.bono import BonoCreate
    from backend.services.configuracion_service import ConfiguracionService
    srv = ConfiguracionService(_RepoV())
    with pytest.raises(HTTPException):
        asyncio.run(srv._validar_efectos_bono(BonoCreate(nombre="4 Productos", efecto_inasistencia="pierde", efectos={10: "proporcion"}), False, 2))
    with pytest.raises(HTTPException):
        asyncio.run(srv._validar_efectos_tipo({2: "proporcion"}))
    with pytest.raises(HTTPException) as e:
        asyncio.run(srv.delete_bono(2))
    assert "4 Productos" in e.value.detail


def test_pantalla():
    js = (RAIZ / "frontend" / "js" / "configuracion_ui.js").read_text(encoding="utf-8")
    html = (RAIZ / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'id="bono-tipo"' in html and 'id="bono-nota-beneficio"' in html
    assert "opsEfecto(b)" in js and "b.usa_productos_4 ? ''" in js


def test_antiguedad_de_4_productos_se_configura_en_el_bono():
    # Antes «a partir del segundo mes» estaba escrito en el código; ahora sale del bono (decisión del 22-11-2026)
    fuente = (RAIZ / "backend" / "services" / "productos_4_service.py").read_text(encoding="utf-8")
    assert 'antig_min = int((bono_p4 or {}).get("antiguedad_meses") or 0)' in fuente and "diff_months < antig_min" in fuente
    assert "diff_months < 1" not in fuente
    # al agregar la columna, el bono que ya existía queda con 1 mes (lo de antes)
    db = _DB(ajuste="50", cols=("id", "nombre", "tipo"))
    asyncio.run(ConfiguracionRepository(db)._init_bono_productos_4())
    assert ("UPDATE bonos SET antiguedad_meses = 1 WHERE id = ?", (50,)) in db.inserts
    # y uno nuevo se crea con 1 mes
    db2 = _DB(compromiso={"id": 1, "activo": 1, "efecto_inasistencia": "pierde"})
    asyncio.run(ConfiguracionRepository(db2)._init_bono_productos_4())
    assert any(q == "INSERT INTO bonos" for q, _ in db2.inserts)
    js = (RAIZ / "frontend" / "js" / "configuracion_ui.js").read_text(encoding="utf-8")
    assert "bono-antiguedad" in js and "antiguedad_meses, reglas" in js
