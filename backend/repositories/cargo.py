"""
Repository - Cargo
Capa de acceso a datos para los Cargos (Labores) y sus Alias (Diccionario Ortográfico)
"""

from typing import List, Optional, Dict
from loguru import logger
from backend.core.database import Database

class CargoRepository:
    def __init__(self, db: Database):
        self.db = db

    async def get_all_cargos(self) -> List[dict]:
        """Obtener todos los cargos principales"""
        query = "SELECT id, nombre, created_at FROM cargos ORDER BY nombre ASC"
        return await self.db.fetch_all(query)

    async def get_cargo_by_id(self, cargo_id: int) -> Optional[dict]:
        """Obtener un cargo por su ID"""
        query = "SELECT id, nombre, created_at FROM cargos WHERE id = ?"
        return await self.db.fetch_one(query, (cargo_id,))

    async def get_cargo_by_name(self, nombre: str) -> Optional[dict]:
        """Obtener un cargo por su nombre exacto"""
        query = "SELECT id, nombre, created_at FROM cargos WHERE nombre = ?"
        return await self.db.fetch_one(query, (nombre,))

    async def find_cargo_id_by_name_or_alias(self, name_or_alias: str) -> Optional[int]:
        """
        Busca un cargo usando su nombre exacto o su alias.
        Retorna el cargo_id de la tabla cargos.
        """
        # Primero intentar por nombre exacto
        cargo = await self.get_cargo_by_name(name_or_alias)
        if cargo:
            return cargo["id"]
            
        # Si no, buscar en alias
        query = "SELECT cargo_id FROM cargos_alias WHERE alias = ?"
        alias = await self.db.fetch_one(query, (name_or_alias,))
        if alias:
            return alias["cargo_id"]
            
        return None

    async def create_cargo(self, nombre: str) -> int:
        """Crea un nuevo cargo principal"""
        query = "INSERT INTO cargos (nombre) VALUES (?)"
        cursor = await self.db.execute(query, (nombre,))
        logger.info(f"✨ Nuevo Cargo registrado en catálogo: {nombre} (ID: {cursor.lastrowid})")
        return cursor.lastrowid

    async def create_alias(self, alias: str, cargo_id: int) -> int:
        """Crea un alias asociado a un cargo principal"""
        query = "INSERT INTO cargos_alias (alias, cargo_id) VALUES (?, ?)"
        cursor = await self.db.execute(query, (alias, cargo_id))
        logger.info(f"✨ Nuevo Alias registrado para Cargo: '{alias}' -> Cargo ID {cargo_id}")
        return cursor.lastrowid

    async def get_all_aliases(self) -> List[dict]:
        """Obtener todos los alias con sus cargos destino"""
        query = """
            SELECT al.id, al.alias, al.cargo_id, c.nombre as cargo_nombre 
            FROM cargos_alias al
            JOIN cargos c ON al.cargo_id = c.id
            ORDER BY al.alias ASC
        """
        return await self.db.fetch_all(query)

    async def get_cargos_with_aliases(self) -> List[Dict]:
        """
        Obtiene todos los cargos y sus alias asociados construyendo una estructura jerárquica.
        """
        query = """
            SELECT c.id as cargo_id, c.nombre as cargo_nombre, c.excluido_asistencia,
                   al.id as alias_id, al.alias as alias_nombre
            FROM cargos c
            LEFT JOIN cargos_alias al ON c.id = al.cargo_id
            ORDER BY c.nombre ASC, al.alias ASC
        """
        rows = await self.db.fetch_all(query)
        
        # Agrupar en Python
        cargos_dict = {}
        for row in rows:
            cargo_id = row["cargo_id"]
            if cargo_id not in cargos_dict:
                cargos_dict[cargo_id] = {
                    "id": cargo_id,
                    "nombre": row["cargo_nombre"],
                    "excluido_asistencia": bool(row.get("excluido_asistencia", 0)),
                    "alias": []
                }
            
            if row["alias_id"]:
                cargos_dict[cargo_id]["alias"].append({
                    "id": row["alias_id"],
                    "alias": row["alias_nombre"]
                })
                
        return list(cargos_dict.values())

    async def delete_alias(self, alias_id: int) -> bool:
        """Elimina un alias específico (desvincular error)"""
        query = "DELETE FROM cargos_alias WHERE id = ?"
        cursor = await self.db.execute(query, (alias_id,))
        if cursor.rowcount > 0:
            logger.info(f"🗑️ Alias de Cargo ID {alias_id} eliminado exitosamente.")
            return True
        return False
