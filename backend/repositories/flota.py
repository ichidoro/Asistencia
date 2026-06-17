import os
from typing import List, Dict, Optional, Any
from loguru import logger
from backend.core.database import Database

class FlotaRepository:
    def __init__(self, db: Database):
        self.db = db

    async def init_tables(self) -> None:
        """
        Inicializa las tablas del módulo Flota Aguacol.
        Realiza la migración de la tabla areas de forma segura.
        """
        # 1. Asegurar columna aplica_flota en la tabla areas
        try:
            columns = await self.db.fetch_all("PRAGMA table_info(areas)")
            has_aplica_flota = any(c['name'] == 'aplica_flota' for c in columns)
            if not has_aplica_flota:
                logger.info("🛠️ Ejecutando migración: Agregando columna 'aplica_flota' a la tabla 'areas'...")
                await self.db.execute("ALTER TABLE areas ADD COLUMN aplica_flota INTEGER DEFAULT 0")
                logger.success("✅ Columna 'aplica_flota' agregada con éxito")
                
                # Sembrar valores iniciales para áreas que contengan 'Logística'
                await self.db.execute(
                    "UPDATE areas SET aplica_flota = 1 WHERE nombre LIKE '%Logística%' OR nombre LIKE '%LOGISTICA%'"
                )
                logger.info("🌱 Áreas de logística pre-configuradas con aplica_flota = 1")
        except Exception as e:
            logger.warning(f"⚠️ Error al verificar/migrar la columna aplica_flota en tabla areas: {e}")

        # 2. Crear tabla flota_aguacol (Catálogo de vehículos)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS flota_aguacol (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patente TEXT NOT NULL UNIQUE,
                area_id INTEGER NOT NULL,
                activo INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (area_id) REFERENCES areas (id)
            )
        """)
        logger.info("✨ Tabla 'flota_aguacol' verificada/creada")

        # 3. Crear tabla flota_registros (Historial de movimientos)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS flota_registros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flota_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                registrado_por_id INTEGER,
                registrado_por_nombre TEXT,
                observaciones TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (flota_id) REFERENCES flota_aguacol (id) ON DELETE CASCADE
            )
        """)
        logger.info("✨ Tabla 'flota_registros' verificada/creada")

        # 4. Crear Índices de Optimización
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_flota_reg_fecha ON flota_registros(fecha)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_flota_reg_vehiculo_fecha ON flota_registros(flota_id, fecha)")
        logger.info("📊 Índices para flota_registros creados/verificados")

    # --- CRUD VEHÍCULOS ---

    async def get_all_vehiculos(self, incluir_inactivos: bool = False) -> List[Dict[str, Any]]:
        query = """
            SELECT f.id, f.patente, f.area_id, f.activo, f.created_at, a.nombre as area_nombre
            FROM flota_aguacol f
            JOIN areas a ON f.area_id = a.id
        """
        if not incluir_inactivos:
            query += " WHERE f.activo = 1"
        query += " ORDER BY f.patente ASC"
        rows = await self.db.fetch_all(query)
        return [dict(r) for r in rows]

    async def get_vehiculo_by_id(self, v_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT f.id, f.patente, f.area_id, f.activo, f.created_at, a.nombre as area_nombre
            FROM flota_aguacol f
            JOIN areas a ON f.area_id = a.id
            WHERE f.id = ?
        """
        row = await self.db.fetch_one(query, (v_id,))
        return dict(row) if row else None

    async def get_vehiculo_by_patente(self, patente: str) -> Optional[Dict[str, Any]]:
        cleaned_patente = str(patente).strip().upper().replace(" ", "").replace("-", "")
        query = """
            SELECT f.id, f.patente, f.area_id, f.activo, f.created_at, a.nombre as area_nombre
            FROM flota_aguacol f
            JOIN areas a ON f.area_id = a.id
            WHERE f.patente = ? AND f.activo = 1
        """
        row = await self.db.fetch_one(query, (cleaned_patente,))
        return dict(row) if row else None

    async def create_vehiculo(self, patente: str, area_id: int) -> int:
        cleaned_patente = str(patente).strip().upper().replace(" ", "").replace("-", "")
        
        # Verificar si el área existe y aplica para flota
        area = await self.db.fetch_one("SELECT 1 FROM areas WHERE id = ? AND aplica_flota = 1", (area_id,))
        if not area:
            raise ValueError("El área seleccionada no existe o no está habilitada para tener vehículos de la flota.")

        # Si ya existe pero está inactivo, reactivarlo en vez de fallar por UNIQUE
        ex_inactivo = await self.db.fetch_one("SELECT id, activo FROM flota_aguacol WHERE patente = ?", (cleaned_patente,))
        if ex_inactivo:
            if ex_inactivo["activo"] == 0:
                await self.db.execute(
                    "UPDATE flota_aguacol SET area_id = ?, activo = 1 WHERE id = ?",
                    (area_id, ex_inactivo["id"])
                )
                logger.info(f"🔄 Vehículo reactivado: {cleaned_patente} (ID: {ex_inactivo['id']})")
                return ex_inactivo["id"]
            else:
                raise ValueError(f"Ya existe un vehículo activo registrado con la patente {cleaned_patente}.")

        query = "INSERT INTO flota_aguacol (patente, area_id, activo) VALUES (?, ?, 1)"
        cursor = await self.db.execute(query, (cleaned_patente, area_id))
        logger.info(f"✨ Vehículo registrado en la flota: {cleaned_patente} (ID: {cursor.lastrowid})")
        return cursor.lastrowid

    async def update_vehiculo(self, v_id: int, patente: str, area_id: int) -> bool:
        cleaned_patente = str(patente).strip().upper().replace(" ", "").replace("-", "")
        
        # Verificar que el área aplique para flota
        area = await self.db.fetch_one("SELECT 1 FROM areas WHERE id = ? AND aplica_flota = 1", (area_id,))
        if not area:
            raise ValueError("El área seleccionada no está habilitada para tener vehículos de la flota.")

        # Verificar duplicados de patente en otros registros
        duplicado = await self.db.fetch_one(
            "SELECT id FROM flota_aguacol WHERE patente = ? AND id != ? AND activo = 1",
            (cleaned_patente, v_id)
        )
        if duplicado:
            raise ValueError(f"Ya existe otro vehículo activo registrado con la patente {cleaned_patente}.")

        query = "UPDATE flota_aguacol SET patente = ?, area_id = ? WHERE id = ?"
        cursor = await self.db.execute(query, (cleaned_patente, area_id, v_id))
        return hasattr(cursor, 'rowcount') and cursor.rowcount > 0

    async def delete_vehiculo(self, v_id: int) -> bool:
        # Borrado lógico
        query = "UPDATE flota_aguacol SET activo = 0 WHERE id = ?"
        cursor = await self.db.execute(query, (v_id,))
        logger.info(f"🗑️ Vehículo desactivado (soft-delete) ID: {v_id}")
        return hasattr(cursor, 'rowcount') and cursor.rowcount > 0

    # --- REGISTRO DE MOVIMIENTOS Y HISTORIAL ---

    async def get_ultimo_registro_global(self, flota_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene la última marca registrada para un vehículo sin filtro de fecha"""
        query = """
            SELECT * FROM flota_registros 
            WHERE flota_id = ? 
            ORDER BY fecha DESC, hora DESC, id DESC 
            LIMIT 1
        """
        row = await self.db.fetch_one(query, (flota_id,))
        return dict(row) if row else None

    async def get_ultimo_registro_antes(self, flota_id: int, fecha: str) -> Optional[Dict[str, Any]]:
        """Obtiene la última marca registrada para un vehículo anterior a la fecha especificada"""
        query = """
            SELECT * FROM flota_registros 
            WHERE flota_id = ? AND fecha < ? 
            ORDER BY fecha DESC, hora DESC, id DESC 
            LIMIT 1
        """
        row = await self.db.fetch_one(query, (flota_id, fecha))
        return dict(row) if row else None


    async def marcar_movimiento(
        self, 
        flota_id: int, 
        tipo: str, 
        fecha: str, 
        hora: str, 
        registrado_por_id: Optional[int], 
        registrado_por_nombre: str, 
        observaciones: str = ""
    ) -> int:
        query = """
            INSERT INTO flota_registros 
            (flota_id, tipo, fecha, hora, registrado_por_id, registrado_por_nombre, observaciones)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        cursor = await self.db.execute(
            query, 
            (flota_id, tipo, fecha, hora, registrado_por_id, registrado_por_nombre, observaciones)
        )
        logger.info(f"📝 Marca registrada: {tipo} para Vehículo ID {flota_id} en {fecha} {hora}")
        return cursor.lastrowid

    async def get_registros_dia(self, fecha: str) -> List[Dict[str, Any]]:
        """Obtiene todas las marcas asociadas a una fecha, ordenadas por vehículo e id ASC"""
        query = """
            SELECT r.*, f.patente, a.nombre as area_nombre
            FROM flota_registros r
            JOIN flota_aguacol f ON r.flota_id = f.id
            JOIN areas a ON f.area_id = a.id
            WHERE r.fecha = ?
            ORDER BY r.flota_id, r.id ASC
        """
        rows = await self.db.fetch_all(query, (fecha,))
        return [dict(r) for r in rows]

    async def get_historial(
        self, 
        desde: str, 
        hasta: str, 
        area_id: Optional[int] = None, 
        patente: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
        areas_permitidas: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Obtiene el historial filtrado y paginado de marcas"""
        where_clauses = ["r.fecha BETWEEN ? AND ?"]
        params = [desde, hasta]

        if area_id:
            where_clauses.append("f.area_id = ?")
            params.append(area_id)

        if patente:
            cleaned_patente = str(patente).strip().upper().replace(" ", "").replace("-", "")
            where_clauses.append("f.patente LIKE ?")
            params.append(f"%{cleaned_patente}%")

        if areas_permitidas is not None:
            if not areas_permitidas:
                where_clauses.append("1=0")
            else:
                placeholders = ", ".join("?" for _ in areas_permitidas)
                where_clauses.append(f"a.nombre IN ({placeholders})")
                params.extend(areas_permitidas)

        where_sql = " AND ".join(where_clauses)

        # Contar total
        count_query = f"""
            SELECT COUNT(*) as total 
            FROM flota_registros r
            JOIN flota_aguacol f ON r.flota_id = f.id
            JOIN areas a ON f.area_id = a.id
            WHERE {where_sql}
        """
        count_row = await self.db.fetch_one(count_query, tuple(params))
        total = count_row["total"] if count_row else 0

        # Paginación
        offset = (page - 1) * limit
        params_query = list(params) + [limit, offset]

        select_query = f"""
            SELECT r.*, f.patente, a.nombre as area_nombre
            FROM flota_registros r
            JOIN flota_aguacol f ON r.flota_id = f.id
            JOIN areas a ON f.area_id = a.id
            WHERE {where_sql}
            ORDER BY r.fecha DESC, r.hora DESC, r.id DESC
            LIMIT ? OFFSET ?
        """
        rows = await self.db.fetch_all(select_query, tuple(params_query))

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit,
            "registros": [dict(r) for r in rows]
        }
