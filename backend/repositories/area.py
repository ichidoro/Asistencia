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

    async def get_areas_with_aliases(self) -> List[Dict]:
        """
        Obtiene todas las áreas y sus alias asociados construyendo una estructura jerárquica:
        [
            {
                "id": 1,
                "nombre": "BODEGA",
                "alias": [{"id": 1, "alias": "BODEGASS"}, ...]
            }, ...
        ]
        """
        query = """
            SELECT a.id as area_id, a.nombre as area_nombre, a.aplica_flota as area_aplica_flota,
                   al.id as alias_id, al.alias as alias_nombre
            FROM areas a
            LEFT JOIN areas_alias al ON a.id = al.area_id
            ORDER BY a.nombre ASC, al.alias ASC
        """
        rows = await self.db.fetch_all(query)
        
        # Agrupar en Python
        areas_dict = {}
        for row in rows:
            area_id = row["area_id"]
            if area_id not in areas_dict:
                areas_dict[area_id] = {
                    "id": area_id,
                    "nombre": row["area_nombre"],
                    "aplica_flota": row["area_aplica_flota"] if ("area_aplica_flota" in row and row["area_aplica_flota"] is not None) else 0,
                    "alias": []
                }
            
            if row["alias_id"]:
                areas_dict[area_id]["alias"].append({
                    "id": row["alias_id"],
                    "alias": row["alias_nombre"]
                })
                
        return list(areas_dict.values())

    async def delete_alias(self, alias_id: int) -> bool:
        """Elimina un alias específico (desvincular error)"""
        query = "DELETE FROM areas_alias WHERE id = ?"
        cursor = await self.db.execute(query, (alias_id,))
        if cursor.rowcount > 0:
            logger.info(f"🗑️ Alias ID {alias_id} eliminado exitosamente. El Guardián volverá a interceptarlo si aparece.")
            return True
        return False
