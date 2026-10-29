"""Borrado permanente de una persona (orden del dueño, 28-10-2026): con días en un tramo cerrado se niega y no borra
nada; si no, limpia todas las tablas con su id dentro de una transacción (reintentando las que dependen de otra), borra
la ficha y deja el registro en logs_auditoria. Antes borraba 9 tablas sin transacción y quedaba a medias."""
import asyncio
import os
from contextlib import asynccontextmanager

os.environ.setdefault("SECRET_KEY", "x" * 40)

import pytest

from backend.repositories.empleado import EmpleadoRepository, BorradoPermanenteBloqueado


class BaseFalsa:
    def __init__(self, cerrados=None, falla_hasta_borrar=None):
        self.cerrados = cerrados or []
        self.falla_hasta_borrar = falla_hasta_borrar or {}  # tabla -> tabla que debe borrarse antes
        self.sql = []
        self.en_tx = False
        self.borradas = set()

    async def fetch_all(self, q, params=None):
        if "FROM asistencias a" in q:
            return self.cerrados
        if "information_schema.tables" in q:
            return [{"table_name": t} for t in ("asistencias", "logs_raw", "viajes_largos", "horas_extras", "empleados", "logs_auditoria")]
        if "information_schema.columns" in q:
            return [{"table_name": "asistencias", "column_name": "empleado_id"},
                    {"table_name": "viajes_largos", "column_name": "empleado_id"},
                    {"table_name": "logs_raw", "column_name": "empleado_id"},
                    {"table_name": "horas_extras", "column_name": "empleado_id"},
                    {"table_name": "logs_auditoria", "column_name": "usuario_id"},
                    {"table_name": "empleados", "column_name": "id"}]
        return []

    async def fetch_one(self, q, params=None):
        return {"id": 66, "rut": "1-9", "nombre": "OSVALDO IGNACIO", "apellido_paterno": "REYES", "apellido_materno": "RODRIGUEZ"}

    async def execute(self, q, params=None):
        assert self.en_tx, "toda escritura del borrado va dentro de la transacción"
        self.sql.append(q)
        if q.startswith("DELETE FROM "):
            tabla = q.split()[2]
            antes = self.falla_hasta_borrar.get(tabla)
            if antes and antes not in self.borradas:
                raise RuntimeError(f"llave foránea: {tabla} depende de {antes}")
            self.borradas.add(tabla)

        class R:
            rowcount = 1
        return R()

    @asynccontextmanager
    async def transaction(self):
        self.en_tx = True
        try:
            yield self
        finally:
            self.en_tx = False


def correr(coro):
    return asyncio.run(coro)


def test_con_dias_en_tramo_cerrado_no_borra_nada():
    db = BaseFalsa(cerrados=[{"fecha_inicio": "2026-09-26", "fecha_fin": "2026-10-25", "area": "SEGURIDAD", "dias": 21}])
    with pytest.raises(BorradoPermanenteBloqueado) as e:
        correr(EmpleadoRepository(db).hard_delete(66, usuario_id=9, username="admin"))
    assert db.sql == []
    assert e.value.tramos[0]["dias"] == 21


def test_borra_todas_las_tablas_la_ficha_y_deja_registro():
    db = BaseFalsa(falla_hasta_borrar={"logs_raw": "viajes_largos"})  # viajes_largos apunta a logs_raw
    borradas = correr(EmpleadoRepository(db).hard_delete(66, usuario_id=9, username="admin"))
    assert set(borradas) == {"asistencias", "viajes_largos", "logs_raw", "horas_extras"}
    assert "logs_auditoria" not in borradas  # usuario_id no es el id de una persona
    assert any(q.startswith("DELETE FROM empleados") for q in db.sql)
    registro = [q for q in db.sql if "INSERT INTO logs_auditoria" in q]
    assert len(registro) == 1
    # la ficha se borra al final y el registro después
    assert db.sql.index(next(q for q in db.sql if q.startswith("DELETE FROM empleados"))) < db.sql.index(registro[0])


def test_si_una_tabla_no_se_puede_borrar_se_deshace_todo():
    db = BaseFalsa(falla_hasta_borrar={"horas_extras": "tabla_que_no_existe"})
    with pytest.raises(RuntimeError):
        correr(EmpleadoRepository(db).hard_delete(66))
    assert not any(q.startswith("DELETE FROM empleados") for q in db.sql)
    assert not any("logs_auditoria" in q for q in db.sql)
