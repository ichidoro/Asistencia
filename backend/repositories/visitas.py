"""
Repository - Visitas (Portería)
Acceso a datos del control de visitas: la tabla visitas_registros.
Las consultas vivían en routers/visitas.py y se movieron aquí sin cambios (auditoría del código, etapa 4, 15-11-2026).
"""
from typing import Any, Dict, List, Optional

from backend.core.database import Database


class VisitasRepository:
    def __init__(self, db: Database):
        self.db = db

    async def init_tables(self) -> None:
        """Crea la tabla si no existe. Índice solo en PK para max velocidad de escritura."""
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS visitas_registros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rut TEXT NOT NULL,
                nombre TEXT DEFAULT '',
                empresa TEXT DEFAULT '',
                motivo TEXT DEFAULT '',
                area_destino TEXT DEFAULT '',
                persona_contacto TEXT DEFAULT '',
                raw_scan TEXT DEFAULT '',
                tipo_documento TEXT DEFAULT 'MANUAL',
                tipo_marca TEXT NOT NULL DEFAULT 'E',
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                registrado_por_id INTEGER,
                registrado_por_nombre TEXT DEFAULT '',
                patente_vehiculo TEXT DEFAULT '',
                observaciones TEXT DEFAULT '',
                parse_ok INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # Solo idx_visitas_rut_fecha: necesario para E/S toggle y consulta diaria
        # Compuesto = 1 índice, no 2, minimiza overhead de escritura
        await self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_visitas_rut_fecha ON visitas_registros(rut, fecha)"
        )

    async def get_visita_previa(self, rut: str) -> Optional[Dict[str, Any]]:
        """Datos de la visita anterior de un RUT (para autocompletar) y cuántas veces ha venido."""
        return await self.db.fetch_one(
            """SELECT nombre, empresa, motivo, area_destino, persona_contacto,
                      COUNT(*) as total_visitas
               FROM visitas_registros
               WHERE rut = ? AND nombre != '' AND nombre IS NOT NULL
               GROUP BY rut
               ORDER BY created_at DESC LIMIT 1""",
            (rut,)
        )

    async def get_ultima_marca_del_dia(self, rut: str, fecha: str) -> Optional[Dict[str, Any]]:
        """Última marca (E o S) de un RUT en un día: decide si la siguiente es entrada o salida."""
        return await self.db.fetch_one(
            "SELECT tipo_marca FROM visitas_registros WHERE rut = ? AND fecha = ? ORDER BY hora DESC LIMIT 1",
            (rut, fecha)
        )

    async def registrar(self, valores: tuple) -> Optional[int]:
        """Guarda una marca de visita y devuelve su id. `valores` va en el orden de las columnas del INSERT."""
        cur = await self.db.execute(
            """INSERT INTO visitas_registros
               (rut, nombre, empresa, motivo, area_destino, persona_contacto,
                raw_scan, tipo_documento, tipo_marca, fecha, hora,
                registrado_por_id, registrado_por_nombre, patente_vehiculo,
                observaciones, parse_ok)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            valores
        )
        return getattr(cur, "lastrowid", None)

    async def get_marcas_del_dia(self, fecha: str) -> List[Dict[str, Any]]:
        """Todas las marcas de visitas de un día, de la más reciente a la más antigua."""
        return await self.db.fetch_all(
            """SELECT rut, nombre, empresa, motivo, area_destino, persona_contacto,
                      tipo_documento, tipo_marca, hora, patente_vehiculo, parse_ok
               FROM visitas_registros
               WHERE fecha = ?
               ORDER BY hora DESC""",
            (fecha,)
        )

    async def contar_historial(self, desde: str, hasta: str) -> int:
        """Cuántas visitas (un RUT en un día) hay entre dos fechas."""
        row = await self.db.fetch_one(
            "SELECT COUNT(DISTINCT rut || fecha) as total FROM visitas_registros WHERE fecha BETWEEN ? AND ?",
            (desde, hasta)
        )
        return row['total'] if row else 0

    async def get_historial(self, desde: str, hasta: str, limit: int, offset: int) -> List[Dict[str, Any]]:
        """Una fila por visita (RUT y día) con su primera entrada y su última salida, paginado."""
        return await self.db.fetch_all(
            """SELECT rut, nombre, empresa, area_destino, fecha,
                      MIN(CASE WHEN tipo_marca='E' THEN hora END) as primera_entrada,
                      MAX(CASE WHEN tipo_marca='S' THEN hora END) as ultima_salida,
                      COUNT(*) as total_marcas,
                      tipo_documento
               FROM visitas_registros
               WHERE fecha BETWEEN ? AND ?
               GROUP BY rut, fecha
               ORDER BY fecha DESC, primera_entrada DESC
               LIMIT ? OFFSET ?""",
            (desde, hasta, limit, offset)
        )
