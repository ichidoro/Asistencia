"""Historial de cierres (pedido de la persona dueña, 21-11-2026): cada cierre muestra el nombre de su período
(«Julio 2026») para saber cuál se reabre, y la ventana trae todos los cierres (antes solo los 12 últimos: con cuatro
áreas eran tres meses, y un mes más antiguo no se podía reabrir desde ahí)."""
import asyncio
import sqlite3
from pathlib import Path

from backend.repositories.asistencia import AsistenciaRepository

RAIZ = Path(__file__).resolve().parents[2]


class BaseSqlite:
    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute("CREATE TABLE periodos_rrhh (id INTEGER PRIMARY KEY, mes_cierre TEXT, fecha_inicio TEXT, fecha_fin TEXT)")
        self.con.execute("CREATE TABLE cierres_periodos (id INTEGER PRIMARY KEY, area TEXT, fecha_inicio TEXT, fecha_fin TEXT)")

    async def fetch_all(self, sql, params=()):
        return [dict(f) for f in self.con.execute(sql, params).fetchall()]


def _base():
    db = BaseSqlite()
    meses = [("Junio 2026", "2026-05-26", "2026-06-25"), ("Julio 2026", "2026-06-26", "2026-07-25"),
             ("Agosto 2026", "2026-07-26", "2026-08-25"), ("Septiembre 2026", "2026-08-26", "2026-09-25")]
    for i, (m, a, b) in enumerate(meses, 1):
        db.con.execute("INSERT INTO periodos_rrhh VALUES (?, ?, ?, ?)", (i, m, a, b))
        for j, area in enumerate(("LOGISTICA TRADICIONAL", "MANTENCION", "PRODUCCION", "SEGURIDAD")):
            db.con.execute("INSERT INTO cierres_periodos VALUES (?, ?, ?, ?)", (i * 10 + j, area, a, b))
    db.con.execute("INSERT INTO cierres_periodos VALUES (99, 'MANTENCION', '2026-01-01', '2026-01-31')")   # sin período
    return db


def test_cada_cierre_trae_el_nombre_de_su_periodo():
    filas = asyncio.run(AsistenciaRepository(_base()).get_cierres_historial(0))
    julio = [f for f in filas if f["fecha_inicio"] == "2026-06-26" and f["area"] == "MANTENCION"]
    assert len(julio) == 1 and julio[0]["mes_cierre"] == "Julio 2026"
    assert [f["mes_cierre"] for f in filas][:4] == ["Septiembre 2026"] * 4          # del más nuevo al más antiguo
    assert [f for f in filas if f["id"] == 99][0]["mes_cierre"] is None             # un cierre sin período igual aparece


def test_cero_trae_todos_y_el_limite_se_sigue_respetando():
    repo = AsistenciaRepository(_base())
    assert len(asyncio.run(repo.get_cierres_historial(0))) == 17
    assert len(asyncio.run(repo.get_cierres_historial(12))) == 12


def test_la_ventana_muestra_el_periodo_y_pide_todos():
    js = (RAIZ / "frontend" / "js" / "marcaciones_ui.js").read_text(encoding="utf-8")
    assert "/api/asistencia/periodo-rrhh/historial/?limit=0" in js
    assert "<th>Período</th>" in js and "esc(c.mes_cierre)" in js
    assert "esc(c.mes_cierre || '')" in js and "window.reabrirPeriodo = async function(id, fechaInicio, fechaFin, area, mes)" in js
