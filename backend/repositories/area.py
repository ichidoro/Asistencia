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

    async def get_area_por_nombre_sin_mayusculas(self, nombre: str) -> Optional[dict]:
        """Un área con ese nombre sin distinguir mayúsculas."""
        return await self.db.fetch_one("SELECT nombre FROM areas WHERE LOWER(nombre) = LOWER(?)", (nombre,))

    async def get_alias_con_nombre(self, nombre: str) -> Optional[dict]:
        """Un alias de área con ese nombre sin distinguir mayúsculas."""
        return await self.db.fetch_one("SELECT id FROM areas_alias WHERE LOWER(alias) = LOWER(?)", (nombre,))

    async def contar_empleados(self, area_id: int) -> Optional[dict]:
        return await self.db.fetch_one("SELECT COUNT(*) as count FROM empleados WHERE area_id = ?", (area_id,))

    async def contar_marcas_en_su_historial(self, area_id: int) -> Optional[dict]:
        """Marcas crudas de quienes estuvieron en el área, dentro de su tiempo en ella."""
        return await self.db.fetch_one("""
            SELECT COUNT(*) as count
            FROM logs_raw l
            JOIN historial_areas ha ON l.empleado_id = ha.empleado_id
            WHERE ha.area_id = ?
              AND substr(l.fecha_hora, 1, 10) BETWEEN ha.fecha_desde AND COALESCE(ha.fecha_hasta, '2099-12-31')
        """, (area_id,))

    async def contar_asistencias_en_su_historial(self, area_id: int) -> Optional[dict]:
        """Jornadas calculadas de quienes estuvieron en el área, dentro de su tiempo en ella."""
        return await self.db.fetch_one("""
            SELECT COUNT(*) as count
            FROM asistencias a
            JOIN historial_areas ha ON a.empleado_id = ha.empleado_id
            WHERE ha.area_id = ?
              AND a.fecha BETWEEN ha.fecha_desde AND COALESCE(ha.fecha_hasta, '2099-12-31')
        """, (area_id,))

    async def contar_horas_extras_en_su_historial(self, area_id: int) -> Optional[dict]:
        """Horas extra de quienes estuvieron en el área, dentro de su tiempo en ella."""
        return await self.db.fetch_one("""
            SELECT COUNT(*) as count
            FROM horas_extras he
            JOIN historial_areas ha ON he.empleado_id = ha.empleado_id
            WHERE ha.area_id = ?
              AND he.fecha BETWEEN ha.fecha_desde AND COALESCE(ha.fecha_hasta, '2099-12-31')
        """, (area_id,))

    async def eliminar_area(self, area_id: int) -> None:
        """Borra el historial de áreas que apunta a ella y después el área (alias, bonos y turnos van en cascada)."""
        await self.db.execute("DELETE FROM historial_areas WHERE area_id = ?", (area_id,))
        await self.db.execute("DELETE FROM areas WHERE id = ?", (area_id,))

    async def set_aplica_flota(self, area_id: int, aplica_flota: int) -> None:
        await self.db.execute("UPDATE areas SET aplica_flota = ? WHERE id = ?", (aplica_flota, area_id))

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
