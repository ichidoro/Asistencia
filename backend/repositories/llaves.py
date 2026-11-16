"""
Repository - Llaves (Portería)
Acceso a datos de la entrega y devolución de llaves: llaves_maestro y llaves_registros.
Las consultas vivían en routers/llaves.py y se movieron aquí sin cambios (auditoría del código, etapa 4, 15-11-2026).
La lista de llaves activas estaba escrita dos veces en el router: ahora es una sola (listar_activas).
"""
from typing import Any, Dict, List, Optional, Sequence

from backend.core.database import Database


class LlavesRepository:
    def __init__(self, db: Database):
        self.db = db

    async def init_tables(self) -> None:
        """Crea las tablas si no existen."""
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS llaves_maestro (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                ubicacion TEXT NOT NULL,
                activo INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS llaves_registros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                llave_id INTEGER NOT NULL,
                empleado_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                registrado_por_id INTEGER,
                registrado_por_nombre TEXT,
                observaciones TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (llave_id) REFERENCES llaves_maestro(id),
                FOREIGN KEY (empleado_id) REFERENCES empleados(id)
            )
        """)

    # ── Maestro de llaves ──────────────────────────────────────────────

    async def listar_activas(self) -> List[Dict[str, Any]]:
        """Las llaves activas, por nombre."""
        return await self.db.fetch_all("SELECT * FROM llaves_maestro WHERE activo = 1 ORDER BY nombre")

    async def get_activa(self, llave_id: int) -> Optional[Dict[str, Any]]:
        """Una llave, solo si está activa."""
        return await self.db.fetch_one(
            "SELECT * FROM llaves_maestro WHERE id = ? AND activo = 1",
            (llave_id,)
        )

    async def crear(self, nombre: str, ubicacion: str) -> None:
        await self.db.execute(
            "INSERT INTO llaves_maestro (nombre, ubicacion) VALUES (?, ?)",
            (nombre, ubicacion)
        )

    async def actualizar(self, llave_id: int, nombre: Optional[str], ubicacion: Optional[str]) -> bool:
        """Cambia los datos que vengan (los None no se tocan). Devuelve False si no había nada que cambiar."""
        updates, params = [], []
        if nombre is not None:
            updates.append("nombre = ?")
            params.append(nombre)
        if ubicacion is not None:
            updates.append("ubicacion = ?")
            params.append(ubicacion)
        if not updates:
            return False
        params.append(llave_id)
        await self.db.execute(
            f"UPDATE llaves_maestro SET {', '.join(updates)} WHERE id = ?",
            tuple(params)
        )
        return True

    async def desactivar(self, llave_id: int) -> None:
        """Baja lógica: la llave deja de aparecer, pero su historial queda."""
        await self.db.execute("UPDATE llaves_maestro SET activo = 0 WHERE id = ?", (llave_id,))

    # ── Empleados autorizados ──────────────────────────────────────────

    async def listar_autorizados(self, areas: Optional[Sequence[str]]) -> List[Dict[str, Any]]:
        """Empleados activos autorizados para llaves; si `areas` no es None, solo los de esas áreas."""
        query = """
            SELECT e.id, e.rut, e.nombre, e.apellido_paterno, e.apellido_materno,
                   COALESCE(a.nombre, 'Sin área') as area_nombre
            FROM empleados e
            LEFT JOIN areas a ON e.area_id = a.id
            WHERE e.autorizado_llaves = 1 AND e.activo = 1
        """
        params = []
        if areas is not None:
            placeholders = ','.join(['?' for _ in areas])
            query += f" AND a.nombre IN ({placeholders})"
            params = areas
        query += " ORDER BY e.apellido_paterno, e.apellido_materno, e.nombre"
        return await self.db.fetch_all(query, tuple(params))

    async def get_empleado_autorizado(self, empleado_id: int) -> Optional[Dict[str, Any]]:
        """El empleado, solo si está activo y autorizado para llaves."""
        return await self.db.fetch_one(
            "SELECT * FROM empleados WHERE id = ? AND autorizado_llaves = 1 AND activo = 1",
            (empleado_id,)
        )

    # ── Movimientos ────────────────────────────────────────────────────

    async def get_ultimo_movimiento(self, llave_id: int) -> Optional[Dict[str, Any]]:
        """El último movimiento de una llave con el nombre y RUT de quien la tiene (para el estado)."""
        return await self.db.fetch_one("""
            SELECT lr.*, TRIM(e.apellido_paterno || ' ' || COALESCE(e.apellido_materno, '') || ' ' || e.nombre) as empleado_nombre, e.rut as empleado_rut
            FROM llaves_registros lr
            JOIN empleados e ON lr.empleado_id = e.id
            WHERE lr.llave_id = ?
            ORDER BY lr.created_at DESC LIMIT 1
        """, (llave_id,))

    async def get_ultimo_tipo(self, llave_id: int) -> Optional[Dict[str, Any]]:
        """Solo el tipo (ENTREGA o DEVOLUCION) del último movimiento: valida el siguiente."""
        return await self.db.fetch_one("""
            SELECT tipo FROM llaves_registros WHERE llave_id = ? ORDER BY created_at DESC LIMIT 1
        """, (llave_id,))

    async def registrar(self, valores: tuple) -> Optional[int]:
        """Guarda un movimiento y devuelve su id. `valores` va en el orden de las columnas del INSERT."""
        cur = await self.db.execute("""
            INSERT INTO llaves_registros (llave_id, empleado_id, tipo, fecha, hora, registrado_por_id, registrado_por_nombre, observaciones)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, valores)
        return getattr(cur, "lastrowid", None)

    # ── Historial ──────────────────────────────────────────────────────

    @staticmethod
    def _filtros(fecha_desde: Optional[str], fecha_hasta: Optional[str], llave_id: Optional[int]):
        where, params = [], []
        if fecha_desde:
            where.append("lr.fecha >= ?")
            params.append(fecha_desde)
        if fecha_hasta:
            where.append("lr.fecha <= ?")
            params.append(fecha_hasta)
        if llave_id:
            where.append("lr.llave_id = ?")
            params.append(llave_id)
        return (" WHERE " + " AND ".join(where)) if where else "", params

    async def contar_historial(self, fecha_desde: Optional[str], fecha_hasta: Optional[str],
                               llave_id: Optional[int]) -> int:
        where_sql, params = self._filtros(fecha_desde, fecha_hasta, llave_id)
        count_row = await self.db.fetch_one(
            f"SELECT COUNT(*) as total FROM llaves_registros lr{where_sql}",
            tuple(params)
        )
        return count_row["total"] if count_row else 0

    async def get_historial(self, fecha_desde: Optional[str], fecha_hasta: Optional[str], llave_id: Optional[int],
                            page_size: int, offset: int) -> List[Dict[str, Any]]:
        """Movimientos con la llave y la persona, del más reciente al más antiguo, paginado."""
        where_sql, params = self._filtros(fecha_desde, fecha_hasta, llave_id)
        return await self.db.fetch_all(f"""
            SELECT lr.*, lm.nombre as llave_nombre, lm.ubicacion,
                   TRIM(e.apellido_paterno || ' ' || COALESCE(e.apellido_materno, '') || ' ' || e.nombre) as empleado_nombre, e.rut as empleado_rut
            FROM llaves_registros lr
            JOIN llaves_maestro lm ON lr.llave_id = lm.id
            JOIN empleados e ON lr.empleado_id = e.id
            {where_sql}
            ORDER BY lr.created_at DESC
            LIMIT ? OFFSET ?
        """, tuple(params) + (page_size, offset))
