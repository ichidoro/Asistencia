"""Una persona sincronizada de BioAlba conserva el Artículo 22 que se le asigna en la ficha (26-11-2026)."""
import asyncio
from types import SimpleNamespace
from backend.services.empleado_service import EmpleadoService


class _Db:
    async def fetch_one(self, *a, **k):
        return {"nombre": "Cargo X", "excluido_asistencia": 0}


def test_resolve_catalogs_no_borra_art22_de_sincronizado():
    svc = object.__new__(EmpleadoService)
    svc.repository = SimpleNamespace(db=_Db())
    emp = SimpleNamespace(area_id=None, area=None, cargo_id=1, cargo=None, genero_id=None, genero=None,
                          es_manual=False, excluido_asistencia=True)
    asyncio.run(svc.resolve_catalogs(emp))
    assert emp.excluido_asistencia is True


def test_update_empleado_sin_import_local_de_date():
    import inspect
    src = inspect.getsource(EmpleadoService.update_empleado)
    assert "from datetime import date" not in src  # volvía 'date' local y rompía el cambio de área


def test_empleado_update_acepta_cargo_id():
    from backend.schemas.empleado import EmpleadoUpdate
    assert EmpleadoUpdate(cargo_id=49).model_dump(exclude_unset=True) == {"cargo_id": 49}
