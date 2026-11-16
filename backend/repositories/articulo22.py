"""
Repository - Artículo 22 (control de presencia en planta)
Acceso a datos de la tabla articulo22_registros y de los empleados con Artículo 22.
Las consultas vivían en routers/articulo22.py y se movieron aquí sin cambios (auditoría del código, etapa 4, 16-11-2026).
La lista de empleados Art. 22 estaba escrita dos veces (una sin la columna «activo»): ahora es una sola.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.core.database import Database


class Articulo22Repository:
    def __init__(self, db: Database):
        self.db = db

    async def init_tables(self) -> None:
        """Crea la tabla si no existe."""
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS articulo22_registros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                tipo TEXT NOT NULL,
                registrado_por_id INTEGER,
                registrado_por_nombre TEXT,
                observaciones TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (empleado_id) REFERENCES empleados(id)
            )
        """)
        # Índices (CREATE INDEX IF NOT EXISTS no falla si ya existen)
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_art22_fecha ON articulo22_registros(fecha)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_art22_emp_fecha ON articulo22_registros(empleado_id, fecha)")

    # ── Empleados ──────────────────────────────────────────────────────

    async def listar_empleados(self) -> List[Dict[str, Any]]:
        """Empleados activos con Artículo 22 (excluido_asistencia = 1), con su área."""
        return await self.db.fetch_all("""
            SELECT e.id, e.rut, e.nombre, e.apellido_paterno, e.apellido_materno,
                   e.cargo, a.nombre as area_nombre, e.activo
            FROM empleados e
            LEFT JOIN areas a ON e.area_id = a.id
            WHERE e.excluido_asistencia = 1 AND e.activo = 1
            ORDER BY e.apellido_paterno, e.nombre
        """)

    async def get_empleado(self, empleado_id: int) -> Optional[Dict[str, Any]]:
        """Nombre del empleado y si tiene Artículo 22 (para validar una marca)."""
        return await self.db.fetch_one(
            "SELECT id, nombre, apellido_paterno, apellido_materno, excluido_asistencia FROM empleados WHERE id = ?",
            (empleado_id,)
        )

    # ── Marcas ─────────────────────────────────────────────────────────

    async def existe_registro(self, registro_id: int) -> bool:
        """¿Sigue existiendo la marca? (se pudo haber deshecho)."""
        return bool(await self.db.fetch_one("SELECT id FROM articulo22_registros WHERE id = ?", (registro_id,)))

    async def get_ultima_marca(self, empleado_id: int) -> Optional[Dict[str, Any]]:
        """La última marca del empleado, de cualquier día (decide si la siguiente es entrada o salida)."""
        return await self.db.fetch_one(
            "SELECT tipo, fecha, hora FROM articulo22_registros WHERE empleado_id = ? ORDER BY id DESC LIMIT 1",
            (empleado_id,)
        )

    async def registrar_marca(self, valores: tuple) -> Optional[int]:
        """Guarda una marca y devuelve su id. `valores` va en el orden de las columnas del INSERT."""
        cur = await self.db.execute(
            """INSERT INTO articulo22_registros
               (empleado_id, fecha, hora, tipo, registrado_por_id, registrado_por_nombre, observaciones)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            valores
        )
        return getattr(cur, "lastrowid", None)

    async def get_marcas_del_dia(self, fecha: str) -> List[Dict[str, Any]]:
        """Todas las marcas de un día, por empleado y en orden de registro."""
        return await self.db.fetch_all(
            """SELECT empleado_id, hora, tipo, registrado_por_nombre, observaciones
               FROM articulo22_registros
               WHERE fecha = ?
               ORDER BY empleado_id, id""",
            (fecha,)
        )

    async def get_marcas_empleado_dia(self, empleado_id: int, fecha: str) -> List[Dict[str, Any]]:
        """Hora y tipo de las marcas de un empleado en un día, en orden de registro."""
        return await self.db.fetch_all(
            "SELECT hora, tipo FROM articulo22_registros WHERE empleado_id = ? AND fecha = ? ORDER BY id",
            (empleado_id, fecha)
        )

    async def get_marcas_empleado_rango(self, empleado_id: int, desde: str, hasta: str) -> List[Dict[str, Any]]:
        """Fecha, hora y tipo de las marcas de un empleado entre dos fechas (para el resumen del rango)."""
        return await self.db.fetch_all(
            "SELECT fecha, hora, tipo FROM articulo22_registros WHERE empleado_id = ? AND fecha BETWEEN ? AND ? ORDER BY fecha, id",
            (empleado_id, desde, hasta)
        )

    # ── Historial y Excel ──────────────────────────────────────────────

    @staticmethod
    def _filtros(desde: str, hasta: str, area: Optional[str], empleado_id: Optional[int],
                 empleado_antes_que_area: bool) -> Tuple[str, List[Any]]:
        where, params = ["r.fecha BETWEEN ? AND ?"], [desde, hasta]
        orden = [("empleado", empleado_id), ("area", area)] if empleado_antes_que_area else [("area", area), ("empleado", empleado_id)]
        for clave, valor in orden:
            if not valor:
                continue
            if clave == "area":
                where.append("a.nombre = ?")
            else:
                where.append("r.empleado_id = ?")
            params.append(valor)
        return " AND ".join(where), params

    async def contar_historial(self, desde: str, hasta: str, area: Optional[str], empleado_id: Optional[int]) -> int:
        """Cuántos días-empleado con marcas hay en el rango (con los filtros)."""
        where_sql, params = self._filtros(desde, hasta, area, empleado_id, empleado_antes_que_area=False)
        count_row = await self.db.fetch_one(
            f"""SELECT COUNT(DISTINCT r.empleado_id || r.fecha) as total
                FROM articulo22_registros r
                JOIN empleados e ON r.empleado_id = e.id
                LEFT JOIN areas a ON e.area_id = a.id
                WHERE {where_sql}""",
            tuple(params)
        )
        return count_row["total"] if count_row else 0

    async def get_historial(self, desde: str, hasta: str, area: Optional[str], empleado_id: Optional[int],
                            limit: int, offset: int) -> List[Dict[str, Any]]:
        """Un resumen por empleado y día (primera entrada, última salida y cantidad de marcas), paginado."""
        where_sql, params = self._filtros(desde, hasta, area, empleado_id, empleado_antes_que_area=False)
        return await self.db.fetch_all(
            f"""SELECT r.empleado_id, r.fecha,
                       e.nombre as emp_nombre, e.apellido_paterno, e.apellido_materno,
                       e.cargo, a.nombre as area_nombre,
                       MIN(CASE WHEN r.tipo='E' THEN r.hora END) as primera_entrada,
                       MAX(CASE WHEN r.tipo='S' THEN r.hora END) as ultima_salida,
                       COUNT(*) as total_marcas
                FROM articulo22_registros r
                JOIN empleados e ON r.empleado_id = e.id
                LEFT JOIN areas a ON e.area_id = a.id
                WHERE {where_sql}
                GROUP BY r.empleado_id, r.fecha
                ORDER BY r.fecha DESC, e.apellido_paterno
                LIMIT ? OFFSET ?""",
            tuple(list(params) + [limit, offset])
        )

    async def get_marcas_para_excel(self, desde: str, hasta: str, empleado_id: Optional[int],
                                    area: Optional[str]) -> List[Dict[str, Any]]:
        """Todas las marcas del rango con los datos del empleado, ordenadas por empleado, fecha y registro."""
        where_sql, params = self._filtros(desde, hasta, area, empleado_id, empleado_antes_que_area=True)
        return await self.db.fetch_all(
            f"""SELECT r.empleado_id, r.fecha, r.hora, r.tipo, r.registrado_por_nombre, r.observaciones,
                       e.rut, e.nombre, e.apellido_paterno, e.apellido_materno, e.cargo, a.nombre AS area_nombre
                FROM articulo22_registros r
                JOIN empleados e ON r.empleado_id = e.id
                LEFT JOIN areas a ON e.area_id = a.id
                WHERE {where_sql}
                ORDER BY e.apellido_paterno, e.nombre, r.fecha, r.id""",
            tuple(params)
        )
