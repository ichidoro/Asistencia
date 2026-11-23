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

    async def get_cargo_by_id(self, cargo_id: int) -> Optional[dict]:
        """Obtener un cargo por su ID"""
        query = "SELECT id, nombre, created_at FROM cargos WHERE id = ?"
        return await self.db.fetch_one(query, (cargo_id,))

    async def get_cargo_by_name(self, nombre: str) -> Optional[dict]:
        """Obtener un cargo por su nombre exacto"""
        query = "SELECT id, nombre, created_at FROM cargos WHERE nombre = ?"
        return await self.db.fetch_one(query, (nombre,))

    async def get_cargo_por_nombre_sin_mayusculas(self, nombre: str) -> Optional[dict]:
        """Un cargo con ese nombre sin distinguir mayúsculas."""
        return await self.db.fetch_one("SELECT nombre FROM cargos WHERE LOWER(nombre) = LOWER(?)", (nombre,))

    async def get_alias_con_nombre(self, nombre: str) -> Optional[dict]:
        """Un alias de cargo con ese nombre sin distinguir mayúsculas."""
        return await self.db.fetch_one("SELECT id FROM cargos_alias WHERE LOWER(alias) = LOWER(?)", (nombre,))

    async def set_excluido_asistencia(self, cargo_id: int, valor: int) -> None:
        """Marca el cargo como Artículo 22 (o no) y lo propaga solo a sus empleados manuales."""
        await self.db.execute("UPDATE cargos SET excluido_asistencia = ? WHERE id = ?", (valor, cargo_id))
        await self.db.execute("UPDATE empleados SET excluido_asistencia = ? WHERE cargo_id = ? AND es_manual = 1", (valor, cargo_id))

    async def get_empleados_manuales_activos(self, cargo_id: int) -> List[dict]:
        return await self.db.fetch_all("SELECT id FROM empleados WHERE cargo_id = ? AND activo = 1 AND es_manual = 1", (cargo_id,))

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

    # ── Renombrar y unir cargos (etapa B3b del plan de bonos, 22-11-2026) ──
    async def uso_del_cargo(self, cargo_id: int) -> Dict:
        """Cuántas personas lo tienen y qué reglas de bono lo nombran (para mostrarlo antes de cambiar)."""
        p = await self.db.fetch_one(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN activo = 1 THEN 1 ELSE 0 END) AS activas FROM empleados WHERE cargo_id = ?", (cargo_id,))
        reglas = []
        for r in await self.db.fetch_all(
                "SELECT b.nombre, r.cargos_req_ids, r.cargos_excl_ids FROM bono_reglas r JOIN bonos b ON b.id = r.bono_id"):
            for campo, que in (("cargos_req_ids", "lo recibe"), ("cargos_excl_ids", "lo excluye")):
                if str(cargo_id) in str(r.get(campo) or '').split(','):
                    reglas.append(f"{r['nombre']} ({que})")
        return {"personas": int((p or {}).get('total') or 0), "activas": int((p or {}).get('activas') or 0), "reglas": reglas}

    async def _rehacer_texto_reglas(self) -> None:
        """El nombre escrito de los cargos de cada regla se rehace desde la lista (solo para leerlo)."""
        nombres = {c['id']: c['nombre'] for c in await self.db.fetch_all("SELECT id, nombre FROM cargos")}
        txt = lambda v: ", ".join(nombres[int(i)] for i in str(v or '').split(',') if i.strip() and int(i) in nombres) or None
        for r in await self.db.fetch_all("SELECT id, cargos_req_ids, cargos_excl_ids FROM bono_reglas"):
            await self.db.execute("UPDATE bono_reglas SET cargo_requerido = ?, cargos_excluidos = ? WHERE id = ?",
                                  (txt(r['cargos_req_ids']), txt(r['cargos_excl_ids']), r['id']))

    async def _guardar_alias(self, alias: str, cargo_id: int) -> None:
        ya = await self.db.fetch_one("SELECT id FROM cargos_alias WHERE LOWER(alias) = LOWER(?)", (alias,))
        if ya:
            await self.db.execute("UPDATE cargos_alias SET cargo_id = ? WHERE id = ?", (cargo_id, ya['id']))
        else:
            await self.db.execute("INSERT INTO cargos_alias (alias, cargo_id) VALUES (?, ?)", (alias, cargo_id))

    async def renombrar(self, cargo_id: int, nombre_nuevo: str) -> str:
        """Cambia el nombre del cargo y el de sus personas; el nombre anterior queda como alias, así la sincronización
        con BioAlba lo sigue reconociendo. Devuelve el nombre anterior."""
        cargo = await self.get_cargo_by_id(cargo_id)
        anterior = cargo['nombre']
        async with self.db.transaction():
            # Si el nombre nuevo era un alias de este mismo cargo, deja de serlo (ahora es su nombre)
            await self.db.execute("DELETE FROM cargos_alias WHERE cargo_id = ? AND LOWER(alias) = LOWER(?)", (cargo_id, nombre_nuevo))
            await self.db.execute("UPDATE cargos SET nombre = ? WHERE id = ?", (nombre_nuevo, cargo_id))
            await self.db.execute("UPDATE empleados SET cargo = ? WHERE cargo_id = ?", (nombre_nuevo, cargo_id))
            await self._guardar_alias(anterior, cargo_id)
            await self._rehacer_texto_reglas()
        return anterior

    async def unir(self, origen_id: int, destino_id: int) -> Dict:
        """Pasa las personas, los alias y las reglas de bono del cargo origen al destino; el nombre del origen queda como
        alias del destino y el origen se borra."""
        origen, destino = await self.get_cargo_by_id(origen_id), await self.get_cargo_by_id(destino_id)
        uso = await self.uso_del_cargo(origen_id)
        async with self.db.transaction():
            await self.db.execute("UPDATE empleados SET cargo_id = ?, cargo = ? WHERE cargo_id = ?",
                                  (destino_id, destino['nombre'], origen_id))
            await self.db.execute("UPDATE cargos_alias SET cargo_id = ? WHERE cargo_id = ?", (destino_id, origen_id))
            if await self.db.table_exists("historial_cargos"):
                await self.db.execute("UPDATE historial_cargos SET cargo_id = ? WHERE cargo_id = ?", (destino_id, origen_id))
            for r in await self.db.fetch_all("SELECT id, cargos_req_ids, cargos_excl_ids FROM bono_reglas"):
                nuevos = []
                for v in (r['cargos_req_ids'], r['cargos_excl_ids']):
                    ids = [destino_id if i.strip() == str(origen_id) else int(i) for i in str(v or '').split(',') if i.strip()]
                    nuevos.append(",".join(str(i) for i in dict.fromkeys(ids)) or None)
                await self.db.execute("UPDATE bono_reglas SET cargos_req_ids = ?, cargos_excl_ids = ? WHERE id = ?", (*nuevos, r['id']))
            await self._guardar_alias(origen['nombre'], destino_id)
            await self.db.execute("DELETE FROM cargos WHERE id = ?", (origen_id,))
            await self._rehacer_texto_reglas()
        return uso

    async def delete_alias(self, alias_id: int) -> bool:
        """Elimina un alias específico (desvincular error)"""
        query = "DELETE FROM cargos_alias WHERE id = ?"
        cursor = await self.db.execute(query, (alias_id,))
        if cursor.rowcount > 0:
            logger.info(f"🗑️ Alias de Cargo ID {alias_id} eliminado exitosamente.")
            return True
        return False
