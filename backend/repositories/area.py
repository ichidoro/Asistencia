"""
Repository - Area
Capa de acceso a datos para las Áreas y sus Alias (Diccionario Ortográfico)
"""

from typing import List, Optional, Dict
from loguru import logger
from backend.core.database import Database

class AreaRepository:
    def __init__(self, db: Database):
        self.db = db

    async def get_all_areas(self) -> List[dict]:
        """Obtener todas las áreas principales"""
        query = "SELECT id, nombre, created_at FROM areas ORDER BY nombre ASC"
        return await self.db.fetch_all(query)

    async def get_area_by_id(self, area_id: int) -> Optional[dict]:
        """Obtener un área por su ID"""
        query = "SELECT id, nombre, created_at FROM areas WHERE id = ?"
        return await self.db.fetch_one(query, (area_id,))

    async def get_area_by_name(self, nombre: str) -> Optional[dict]:
        """Obtener un área por su nombre exacto"""
        query = "SELECT id, nombre, created_at FROM areas WHERE nombre = ?"
        return await self.db.fetch_one(query, (nombre,))

    async def find_area_id_by_name_or_alias(self, name_or_alias: str) -> Optional[int]:
        """
        Busca un área usando su nombre exacto o su alias.
        Retorna el area_id de la tabla areas.
        """
        # Primero intentar por nombre exacto
        area = await self.get_area_by_name(name_or_alias)
        if area:
            return area["id"]
            
        # Si no, buscar en alias
        query = "SELECT area_id FROM areas_alias WHERE alias = ?"
        alias = await self.db.fetch_one(query, (name_or_alias,))
        if alias:
            return alias["area_id"]
            
        return None

    async def create_area(self, nombre: str) -> int:
        """Crea una nueva área principal"""
        query = "INSERT INTO areas (nombre) VALUES (?)"
        cursor = await self.db.execute(query, (nombre,))
        logger.info(f"✨ Nueva Área registrada en catálogo: {nombre} (ID: {cursor.lastrowid})")
        return cursor.lastrowid

    async def create_alias(self, alias: str, area_id: int) -> int:
        """Crea un alias asociado a un área principal"""
        query = "INSERT INTO areas_alias (alias, area_id) VALUES (?, ?)"
        cursor = await self.db.execute(query, (alias, area_id))
        logger.info(f"✨ Nuevo Alias registrado: '{alias}' -> Area ID {area_id}")
        return cursor.lastrowid

    async def get_all_aliases(self) -> List[dict]:
        """Obtener todos los alias con sus áreas destino"""
        query = """
            SELECT al.id, al.alias, al.area_id, a.nombre as area_nombre 
            FROM areas_alias al
            JOIN areas a ON al.area_id = a.id
            ORDER BY al.alias ASC
        """
        return await self.db.fetch_all(query)
