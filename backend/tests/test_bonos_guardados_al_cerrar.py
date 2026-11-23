"""Etapa B5 del plan de bonos (docs/PLAN_BONOS.md): al cerrar un período se guarda el resultado de los bonos de cada
persona (vacío I). El informe PDF y el Excel de un período cerrado leen lo guardado: volver a sacarlos da siempre lo que
se cerró, aunque después cambien los cargos o las reglas. Al reabrir se borra (al cerrar de nuevo se guarda otra vez).
Los períodos cerrados antes de este cambio (Mayo a Octubre 2026) no tienen nada guardado y se calculan como antes:
lo ya pagado no se toca (decisión de la persona dueña, 22-11-2026). Datos inventados; sin nombres de personas.
"""
import asyncio
import json
from datetime import date
from pathlib import Path

from backend.repositories.asistencia import AsistenciaRepository

RAIZ = Path(__file__).resolve().parents[2]


class _DB:
    def __init__(self, cierre=None, filas=()):
        self.cierre, self.filas, self.lotes, self.borrados = cierre, list(filas), [], []

    async def table_exists(self, t):
        return True

    async def fetch_one(self, q, p=()):
        return self.cierre if "FROM cierres_periodos" in q else None

    async def fetch_all(self, q, p=()):
        return self.filas if "FROM bonos_cierre" in q else []

    async def execute(self, q, p=()):
        self.borrados.append((q, p))

    async def execute_batch(self, ops):
        self.lotes.append(ops)


R = {"aplica": True, "califica": False, "monto": 0, "perdidos": [{"fecha": "2026-10-08", "causa": "Inasistencia sin justificar"}]}


def test_guarda_el_resultado_completo_de_cada_bono():
    db = _DB()
    n = asyncio.run(AsistenciaRepository(db).guardar_bonos_cierre(9, {1: {"Compromiso": R}, 2: {}}))
    ops = db.lotes[0]
    assert n == 1 and ops[0] == ("DELETE FROM bonos_cierre WHERE cierre_id = ?", (9,))
    q, p = ops[1]
    assert p[:6] == (9, 1, "Compromiso", 1, 0, 0.0) and json.loads(p[6]) == R


def test_lee_lo_guardado_del_area_cerrada():
    db = _DB(cierre={"id": 9}, filas=[{"empleado_id": 1, "bono": "Compromiso", "resultado": json.dumps(R)}])
    assert asyncio.run(AsistenciaRepository(db).get_bonos_cierre("2026-10-26", "2026-11-25", "AREA")) == {1: {"Compromiso": R}}
    # sin cierre, o cerrado antes de guardar los bonos: None (se calcula como antes)
    assert asyncio.run(AsistenciaRepository(_DB()).get_bonos_cierre("2026-10-26", "2026-11-25", "AREA")) is None
    assert asyncio.run(AsistenciaRepository(_DB(cierre={"id": 9})).get_bonos_cierre("2026-10-26", "2026-11-25", "AREA")) is None


def test_al_reabrir_se_borran():
    db = _DB()
    asyncio.run(AsistenciaRepository(db).eliminar_cierre(9))
    assert ("DELETE FROM bonos_cierre WHERE cierre_id = ?", (9,)) in db.borrados


def test_el_informe_usa_lo_guardado_y_no_recalcula():
    from backend.services.report_service import ReportService

    class _Repo:
        db = None

        async def get_bonos_cierre(self, fi, ff, area):
            return {1: {"Compromiso": R}}

    class _Svc:
        repository = _Repo()

    rs = ReportService(_Svc())
    import backend.services.bono_service as bsm
    llamado = []

    class _NoUsar:
        def __init__(self, *a):
            pass

        async def evaluar_bonos_directo(self, *a, **k):
            llamado.append(1)
            return {}
    orig = bsm.BonoService
    bsm.BonoService = _NoUsar
    try:
        md = {"empleados": [{"id": 1, "nombre": "UNO", "apellido_paterno": "PERSONA", "tipo_programacion": "CICLO"}],
              "matrix": {}, "feriados": [], "data": [], "justificaciones": []}
        calc = asyncio.run(rs._calcular_filas(md, [date(2026, 10, 26), date(2026, 11, 25)], "AREA"))
    finally:
        bsm.BonoService = orig
    assert not llamado and calc["filas"][0]["bonos"] == {"Compromiso": R}


def test_el_cierre_los_guarda():
    fuente = (RAIZ / "backend" / "services" / "cierre_service.py").read_text(encoding="utf-8")
    assert "guardar_bonos_cierre(res_cierre.lastrowid" in fuente
