"""Decisiones del cuadre de un tramo: política por persona y tramo, excepciones por día y tolerancia.

La política es la instrucción permanente que el dueño da para una persona en un tramo («llevar todo a cero» o
«pagar horas extra: tantas»). No guarda montos por día: cada vez que cambian los hechos (marcas nuevas, un
perdonazo, un umbral) la aplicación vuelve a repartir las horas extra del tramo con la misma instrucción.
"""
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.core.database import Database

CLAVE_TOLERANCIA = "cuadre_tolerancia_minutos"
DESCRIPCION_TOLERANCIA = ("Cuadre: minutos de deuda de un día que se dejan pasar sin cobrar (segundos de redondeo). "
                          "0 = se cobra todo.")
POLITICAS = ("CERO", "PAGAR")


class CuadreRepository:
    def __init__(self, db: Database):
        self.db = db

    async def init_tables(self):
        if not await self.db.table_exists("cuadre_politicas"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS cuadre_politicas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    fecha_inicio TEXT NOT NULL,
                    fecha_fin TEXT NOT NULL,
                    politica TEXT NOT NULL,
                    minutos_a_pagar REAL,
                    minutos_perdonados REAL DEFAULT 0,
                    decidido_por TEXT,
                    decidido_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    motivo TEXT,
                    activa INTEGER DEFAULT 1,
                    UNIQUE (empleado_id, fecha_inicio, fecha_fin)
                )
            """)
        # Una decisión tomada día por día a mano (excepción) no la pisa la política del tramo.
        try:
            if 'excepcion' not in set(await self.db.get_column_names("horas_extras")):
                await self.db.execute("ALTER TABLE horas_extras ADD COLUMN excepcion INTEGER DEFAULT 0")
        except Exception as e:
            logger.warning(f"Columna excepcion en horas_extras: {e}")
        try:
            await self.db.execute(
                "INSERT OR IGNORE INTO ajustes (clave, valor, descripcion) VALUES (?, ?, ?)",
                (CLAVE_TOLERANCIA, '0', DESCRIPCION_TOLERANCIA))
        except Exception as e:
            logger.warning(f"Ajuste {CLAVE_TOLERANCIA}: {e}")

    async def tolerancia_minutos(self) -> float:
        row = await self.db.fetch_one("SELECT valor FROM ajustes WHERE clave = ?", (CLAVE_TOLERANCIA,))
        try:
            return max(0.0, float(row['valor'])) if row else 0.0
        except (TypeError, ValueError):
            return 0.0

    async def guardar_tolerancia(self, minutos: float) -> None:
        await self.db.execute(
            "INSERT INTO ajustes (clave, valor, descripcion) VALUES (?, ?, ?) ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (CLAVE_TOLERANCIA, str(float(minutos)), DESCRIPCION_TOLERANCIA))

    async def get_politica(self, empleado_id: int, fecha_inicio: str, fecha_fin: str) -> Optional[Dict[str, Any]]:
        row = await self.db.fetch_one(
            "SELECT * FROM cuadre_politicas WHERE empleado_id = ? AND fecha_inicio = ? AND fecha_fin = ? AND activa = 1",
            (empleado_id, fecha_inicio, fecha_fin))
        return dict(row) if row else None

    async def politicas_que_cubren(self, empleado_ids: List[int], fecha: str) -> List[Dict[str, Any]]:
        if not empleado_ids:
            return []
        ph = ",".join("?" * len(empleado_ids))
        rows = await self.db.fetch_all(
            f"SELECT * FROM cuadre_politicas WHERE activa = 1 AND fecha_inicio <= ? AND fecha_fin >= ? AND empleado_id IN ({ph})",
            tuple([fecha, fecha] + list(empleado_ids)))
        return [dict(r) for r in rows]

    async def politicas_del_tramo(self, fecha_inicio: str, fecha_fin: str) -> List[Dict[str, Any]]:
        rows = await self.db.fetch_all(
            "SELECT * FROM cuadre_politicas WHERE activa = 1 AND fecha_inicio = ? AND fecha_fin = ?", (fecha_inicio, fecha_fin))
        return [dict(r) for r in rows]

    async def guardar_politica(self, empleado_id: int, fecha_inicio: str, fecha_fin: str, politica: str,
                               minutos_a_pagar: Optional[float], minutos_perdonados: float, decidido_por: str, motivo: Optional[str]) -> None:
        if politica not in POLITICAS:
            raise ValueError(f"Política desconocida: {politica}")
        await self.db.execute("""
            INSERT INTO cuadre_politicas (empleado_id, fecha_inicio, fecha_fin, politica, minutos_a_pagar, minutos_perdonados, decidido_por, decidido_en, motivo, activa)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, 1)
            ON CONFLICT(empleado_id, fecha_inicio, fecha_fin) DO UPDATE SET
                politica = excluded.politica, minutos_a_pagar = excluded.minutos_a_pagar, minutos_perdonados = excluded.minutos_perdonados,
                decidido_por = excluded.decidido_por, decidido_en = CURRENT_TIMESTAMP, motivo = excluded.motivo, activa = 1
        """, (empleado_id, fecha_inicio, fecha_fin, politica, minutos_a_pagar, float(minutos_perdonados or 0.0), decidido_por, motivo))

    async def quitar_politica(self, empleado_id: int, fecha_inicio: str, fecha_fin: str) -> None:
        await self.db.execute(
            "UPDATE cuadre_politicas SET activa = 0 WHERE empleado_id = ? AND fecha_inicio = ? AND fecha_fin = ?",
            (empleado_id, fecha_inicio, fecha_fin))

    async def filas_he(self, empleado_id: int, fecha_inicio: str, fecha_fin: str) -> List[Dict[str, Any]]:
        rows = await self.db.fetch_all(
            "SELECT fecha, minutos_bruto, minutos_autorizados, estado, origen, COALESCE(excepcion, 0) AS excepcion "
            "FROM horas_extras WHERE empleado_id = ? AND fecha BETWEEN ? AND ? ORDER BY fecha",
            (empleado_id, fecha_inicio, fecha_fin))
        return [dict(r) for r in rows]

    async def escribir_reparto(self, empleado_id: int, reparto: List[Dict[str, Any]]) -> int:
        """Escribe el reparto de la política en las filas SIN excepción. Devuelve cuántas filas tocó."""
        n = 0
        for r in reparto:
            await self.db.execute(
                "UPDATE horas_extras SET estado = ?, minutos_autorizados = ?, origen = 'POLITICA', updated_at = datetime('now') "
                "WHERE empleado_id = ? AND fecha = ? AND COALESCE(excepcion, 0) = 0 "
                "AND COALESCE(origen, '') NOT IN ('COBERTURA_TURNO', 'DIA_LIBRE', 'FERIADO', 'JORNADA_ESPECIAL')",
                (r['estado'], float(r['minutos_autorizados']), empleado_id, r['fecha']))
            n += 1
        return n

    async def marcar_excepcion(self, empleado_id: int, fecha: str, excepcion: bool = True) -> None:
        await self.db.execute(
            "UPDATE horas_extras SET excepcion = ? WHERE empleado_id = ? AND fecha = ?",
            (1 if excepcion else 0, empleado_id, fecha))
