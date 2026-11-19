"""Reabrir un período cerrado (decisión de la persona dueña, 18-11-2026).

1. Al reabrir, solo queda vigente el período que se reabre (antes los demás seguían vigentes: en la copia de práctica,
   después de reabrir dos meses quedaron tres vigentes a la vez).
2. Se reabre un período a la vez: si otro período ya está abierto (y no es el del día de hoy), no se reabre otro.
   Otra área del mismo período sí se puede reabrir, porque la reapertura es por área.
3. El Excel de cierre usa el logo que muestra la aplicación (antes buscaba logo.jpg, que no existe).
"""
import asyncio
import sqlite3
from pathlib import Path

from openpyxl.drawing.image import Image

from backend.repositories.configuracion import ConfiguracionRepository

RAIZ = Path(__file__).resolve().parents[2]


class BaseSqlite:
    """Base en memoria con la tabla de períodos, con la misma forma de uso que la base de la aplicación."""

    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute("CREATE TABLE periodos_rrhh (id INTEGER PRIMARY KEY, mes_cierre TEXT, fecha_inicio TEXT,"
                         " fecha_fin TEXT, activo INTEGER, estado TEXT)")

    async def execute(self, sql, params=()):
        return self.con.execute(sql, params)

    async def fetch_one(self, sql, params=()):
        fila = self.con.execute(sql, params).fetchone()
        return dict(fila) if fila else None

    async def fetch_all(self, sql, params=()):
        return [dict(f) for f in self.con.execute(sql, params).fetchall()]


def _base(*periodos):
    db = BaseSqlite()
    for p in periodos:
        db.con.execute("INSERT INTO periodos_rrhh (id, mes_cierre, fecha_inicio, fecha_fin, activo, estado)"
                       " VALUES (?, ?, ?, ?, ?, ?)", p)
    return db


JULIO = (5, "Julio 2026", "2026-06-26", "2026-07-25", 0, "cerrado")
AGOSTO = (6, "Agosto 2026", "2026-07-26", "2026-08-25", 0, "cerrado")
NOVIEMBRE = (9, "Noviembre 2026", "2026-10-26", "2026-11-25", 1, "abierto")
HOY = "2026-11-18"


def _vigentes(db):
    return [f["id"] for f in db.con.execute("SELECT id FROM periodos_rrhh WHERE activo = 1 ORDER BY id")]


def test_al_reabrir_solo_queda_vigente_el_periodo_reabierto():
    db = _base(JULIO, AGOSTO, NOVIEMBRE)
    asyncio.run(ConfiguracionRepository(db).reabrir_periodo_rrhh("2026-06-26", "2026-07-25"))
    assert _vigentes(db) == [5]
    assert db.con.execute("SELECT estado FROM periodos_rrhh WHERE id = 5").fetchone()[0] == "abierto"


def test_el_mes_en_curso_no_impide_reabrir():
    db = _base(JULIO, AGOSTO, NOVIEMBRE)
    otro = asyncio.run(ConfiguracionRepository(db).get_otro_periodo_reabierto("2026-06-26", "2026-07-25", HOY))
    assert otro is None


def test_con_un_periodo_ya_reabierto_no_se_reabre_otro():
    db = _base(JULIO, AGOSTO, NOVIEMBRE)
    repo = ConfiguracionRepository(db)
    asyncio.run(repo.reabrir_periodo_rrhh("2026-06-26", "2026-07-25"))
    otro = asyncio.run(repo.get_otro_periodo_reabierto("2026-07-26", "2026-08-25", HOY))
    assert otro and otro["mes_cierre"] == "Julio 2026"


def test_otra_area_del_mismo_periodo_si_se_puede_reabrir():
    db = _base(JULIO, AGOSTO, NOVIEMBRE)
    repo = ConfiguracionRepository(db)
    asyncio.run(repo.reabrir_periodo_rrhh("2026-06-26", "2026-07-25"))
    assert asyncio.run(repo.get_otro_periodo_reabierto("2026-06-26", "2026-07-25", HOY)) is None


def test_el_router_frena_la_segunda_reapertura_antes_de_borrar_el_cierre():
    texto = (RAIZ / "backend" / "routers" / "cierre.py").read_text(encoding="utf-8")
    cuerpo = texto[texto.index("async def reabrir_cierre("):]
    assert cuerpo.index("get_otro_periodo_reabierto(") < cuerpo.index("eliminar_cierre(")
    assert "status_code=409" in cuerpo[:cuerpo.index("eliminar_cierre(")]


def test_el_excel_de_cierre_usa_el_logo_de_la_aplicacion():
    texto = (RAIZ / "backend" / "services" / "report_service.py").read_text(encoding="utf-8")
    assert '"logo.jpg"' not in texto and '"logo-aguacol.png"' in texto
    logo = RAIZ / "frontend" / "assets" / "img" / "logo-aguacol.png"
    assert logo.exists()
    img = Image(str(logo))
    assert img.width > 0 and img.height > 0
