from typing import List, Dict, Optional
from backend.core.database import db
from loguru import logger
from datetime import date

class CalendarioRepository:
    def __init__(self):
        self.db = db

    async def init_db(self):
        """Inicializa la tabla de feriados"""
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS feriados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL UNIQUE,
                descripcion TEXT NOT NULL,
                es_nacional INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    async def get_all_feriados(self, year: Optional[int] = None) -> List[Dict]:
        query = "SELECT * FROM feriados"
        params = []
        if year:
            query += " WHERE fecha LIKE ?"
            params.append(f"{year}-%")
        query += " ORDER BY fecha ASC"
        
        rows = await self.db.fetch_all(query, tuple(params))
        return [dict(row) for row in rows]

    async def upsert_feriado(self, fecha: str, descripcion: str, es_nacional: bool = True):
        query = """
            INSERT INTO feriados (fecha, descripcion, es_nacional)
            VALUES (?, ?, ?)
            ON CONFLICT(fecha) DO UPDATE SET
                descripcion = excluded.descripcion,
                es_nacional = excluded.es_nacional
        """
        await self.db.execute(query, (fecha, descripcion, 1 if es_nacional else 0))

    async def delete_feriado(self, feriado_id: int):
        await self.db.execute("DELETE FROM feriados WHERE id = ?", (feriado_id,))

    async def is_feriado(self, fecha: date) -> bool:
        query = "SELECT id FROM feriados WHERE fecha = ?"
        res = await self.db.fetch_one(query, (str(fecha),))
        return res is not None
