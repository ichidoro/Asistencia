import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from loguru import logger
from backend.core.database import Database

class PorteriaRepository:
    def __init__(self, db: Database):
        self.db = db

    async def init_tables(self):
        """Inicializa las tablas del módulo de Portería y siembra valores iniciales."""
        
        # 1. Tabla Catalogo de Hallazgos
        if not await self.db.table_exists("porteria_catalogo_hallazgos"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS porteria_catalogo_hallazgos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    activo BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("✨ Tabla 'porteria_catalogo_hallazgos' creada")
            # Sembrar catálogo inicial
            default_hallazgos = [
                "Sin novedad / Todo normal",
                "Puerta/Galpón abierto o sin candado",
                "Luz encendida innecesariamente",
                "Fuga de agua detectada",
                "Presencia de personas no autorizadas",
                "Falla en luminaria perimetral",
                "Obstrucción en vía de evacuación",
                "Otros (Especificar en detalle)"
            ]
            for h in default_hallazgos:
                await self.db.execute(
                    "INSERT INTO porteria_catalogo_hallazgos (nombre, activo) VALUES (?, 1)",
                    (h,)
                )
            logger.info("🌱 Semilla inicial del catálogo de hallazgos sembrada")

        # 2. Tabla Ubicaciones (Puntos de Control QR) [NEW]
        if not await self.db.table_exists("porteria_ubicaciones"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS porteria_ubicaciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL UNIQUE,
                    codigo TEXT NOT NULL UNIQUE,
                    activo INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("✨ Tabla 'porteria_ubicaciones' creada")
            # Sembrar ubicaciones iniciales
            default_ubicaciones = [
                ("Portería Principal", "LOC001"),
                ("Bodega Trasera", "LOC002"),
                ("Estacionamiento", "LOC003"),
                ("Galpón 1", "LOC004"),
                ("Perímetro Norte", "LOC005")
            ]
            for nombre, codigo in default_ubicaciones:
                await self.db.execute(
                    "INSERT INTO porteria_ubicaciones (nombre, codigo, activo) VALUES (?, ?, 1)",
                    (nombre, codigo)
                )
            logger.info("🌱 Semilla inicial de ubicaciones de portería sembrada")

        # Auto-healing: Si existe la columna 'area_id' en la tabla existente, la eliminamos para migrar a 'ubicacion_id'
        if await self.db.table_exists("porteria_rondas_registro"):
            columns = await self.db.fetch_all("PRAGMA table_info(porteria_rondas_registro)")
            has_area_id = any(c['name'] == 'area_id' for c in columns)
            if has_area_id:
                logger.info("🛠️ Recreando tabla porteria_rondas_registro para migrar de area_id a ubicacion_id...")
                await self.db.execute("DROP TABLE IF EXISTS porteria_rondas_hallazgos")
                await self.db.execute("DROP TABLE IF EXISTS porteria_rondas_registro")

        # 3. Tabla Registro de Rondas (Ahora referenciando ubicacion_id)
        if not await self.db.table_exists("porteria_rondas_registro"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS porteria_rondas_registro (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ubicacion_id INTEGER NOT NULL,
                    fecha_hora TEXT NOT NULL, -- ISO 8601 del dispositivo (ej: 2026-06-08T00:30:00.000Z)
                    usuario_id INTEGER NOT NULL,
                    uuid_offline TEXT UNIQUE NOT NULL, -- UUID generado localmente para evitar duplicidad
                    sincronizado_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(ubicacion_id) REFERENCES porteria_ubicaciones(id),
                    FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
                )
            """)
            logger.info("✨ Tabla 'porteria_rondas_registro' creada")

        # Índices de optimización para registros de rondas
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_porteria_rondas_reg_ubic ON porteria_rondas_registro(ubicacion_id)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_porteria_rondas_reg_fecha ON porteria_rondas_registro(fecha_hora)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_porteria_rondas_reg_uuid ON porteria_rondas_registro(uuid_offline)")

        # 4. Tabla Hallazgos reportados en rondas
        if not await self.db.table_exists("porteria_rondas_hallazgos"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS porteria_rondas_hallazgos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    registro_id INTEGER NOT NULL,
                    hallazgo_id INTEGER, -- FK a porteria_catalogo_hallazgos (puede ser NULL si es solo foto o personalizado)
                    detalle_personalizado TEXT,
                    google_drive_file_id TEXT, -- ID del archivo subido a Google Drive
                    foto_url TEXT, -- URL pública o compartida de la foto
                    FOREIGN KEY(registro_id) REFERENCES porteria_rondas_registro(id) ON DELETE CASCADE,
                    FOREIGN KEY(hallazgo_id) REFERENCES porteria_catalogo_hallazgos(id)
                )
            """)
            logger.info("✨ Tabla 'porteria_rondas_hallazgos' creada")

        # Índice de optimización para hallazgos
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_porteria_rondas_hallazgos_reg ON porteria_rondas_hallazgos(registro_id)")

    # --- CRUD Catálogo de Hallazgos ---
    
    async def get_all_hallazgos(self, incluir_inactivos: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM porteria_catalogo_hallazgos"
        if not incluir_inactivos:
            query += " WHERE activo = 1"
        query += " ORDER BY id ASC"
        return await self.db.fetch_all(query)

    async def get_hallazgo_by_id(self, hallazgo_id: int) -> Optional[Dict[str, Any]]:
        return await self.db.fetch_one(
            "SELECT * FROM porteria_catalogo_hallazgos WHERE id = ?",
            (hallazgo_id,)
        )

    async def create_hallazgo(self, nombre: str) -> int:
        cursor = await self.db.execute(
            "INSERT INTO porteria_catalogo_hallazgos (nombre, activo) VALUES (?, 1)",
            (nombre,)
        )
        return cursor.lastrowid

    async def update_hallazgo(self, hallazgo_id: int, nombre: str, activo: bool) -> bool:
        cursor = await self.db.execute(
            "UPDATE porteria_catalogo_hallazgos SET nombre = ?, activo = ? WHERE id = ?",
            (nombre, 1 if activo else 0, hallazgo_id)
        )
        return hasattr(cursor, 'rowcount') and cursor.rowcount > 0

    async def delete_hallazgo(self, hallazgo_id: int) -> bool:
        # Primero verifiquemos si está siendo usado
        uso = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM porteria_rondas_hallazgos WHERE hallazgo_id = ?",
            (hallazgo_id,)
        )
        if uso and uso['count'] > 0:
            # Si se usa, hacemos soft delete (marcar inactivo)
            cursor = await self.db.execute(
                "UPDATE porteria_catalogo_hallazgos SET activo = 0 WHERE id = ?",
                (hallazgo_id,)
            )
            return True
        else:
            # Si no se usa, hacemos hard delete
            cursor = await self.db.execute(
                "DELETE FROM porteria_catalogo_hallazgos WHERE id = ?",
                (hallazgo_id,)
            )
            return hasattr(cursor, 'rowcount') and cursor.rowcount > 0

    # --- CRUD Ubicaciones [NEW] ---

    async def get_all_ubicaciones(self, incluir_inactivos: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM porteria_ubicaciones"
        if not incluir_inactivos:
            query += " WHERE activo = 1"
        query += " ORDER BY id ASC"
        return await self.db.fetch_all(query)

    async def get_ubicacion_by_id(self, ubicacion_id: int) -> Optional[Dict[str, Any]]:
        return await self.db.fetch_one(
            "SELECT * FROM porteria_ubicaciones WHERE id = ?",
            (ubicacion_id,)
        )

    async def create_ubicacion(self, nombre: str, codigo: str) -> int:
        cursor = await self.db.execute(
            "INSERT INTO porteria_ubicaciones (nombre, codigo, activo) VALUES (?, ?, 1)",
            (nombre, codigo)
        )
        return cursor.lastrowid

    async def update_ubicacion(self, ubicacion_id: int, nombre: str, codigo: str, activo: bool) -> bool:
        cursor = await self.db.execute(
            "UPDATE porteria_ubicaciones SET nombre = ?, codigo = ?, activo = ? WHERE id = ?",
            (nombre, codigo, 1 if activo else 0, ubicacion_id)
        )
        return hasattr(cursor, 'rowcount') and cursor.rowcount > 0

    async def delete_ubicacion(self, ubicacion_id: int) -> bool:
        # Primero verifiquemos si está siendo usada en rondas
        uso = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM porteria_rondas_registro WHERE ubicacion_id = ?",
            (ubicacion_id,)
        )
        if uso and uso['count'] > 0:
            # Si se usa, hacemos soft delete (marcar inactiva)
            cursor = await self.db.execute(
                "UPDATE porteria_ubicaciones SET activo = 0 WHERE id = ?",
                (ubicacion_id,)
            )
            return True
        else:
            # Si no se usa, hacemos hard delete
            cursor = await self.db.execute(
                "DELETE FROM porteria_ubicaciones WHERE id = ?",
                (ubicacion_id,)
            )
            return hasattr(cursor, 'rowcount') and cursor.rowcount > 0

    # --- Registro y Consulta de Rondas ---

    async def get_rondas_recientes(self, limit: int = 100) -> List[Dict[str, Any]]:
        query = """
            SELECT r.*, ubi.nombre as ubicacion_nombre, ubi.codigo as ubicacion_codigo, u.username as usuario_nombre
            FROM porteria_rondas_registro r
            JOIN porteria_ubicaciones ubi ON r.ubicacion_id = ubi.id
            JOIN usuarios u ON r.usuario_id = u.id
            ORDER BY r.fecha_hora DESC
            LIMIT ?
        """
        rondas = await self.db.fetch_all(query, (limit,))
        
        # Cargar los hallazgos para cada ronda
        for r in rondas:
            r['hallazgos'] = await self.db.fetch_all("""
                SELECT rh.*, ch.nombre as hallazgo_nombre
                FROM porteria_rondas_hallazgos rh
                LEFT JOIN porteria_catalogo_hallazgos ch ON rh.hallazgo_id = ch.id
                WHERE rh.registro_id = ?
            """, (r['id'],))
            
        return rondas

    async def check_uuid_exists(self, uuid_offline: str) -> bool:
        row = await self.db.fetch_one(
            "SELECT 1 FROM porteria_rondas_registro WHERE uuid_offline = ?",
            (uuid_offline,)
        )
        return row is not None

    async def sync_rondas_batch(self, rondas_lote: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Sincroniza un lote de rondas de forma atómica y segura contra duplicados.
        Formato esperado por cada ronda:
        {
            "uuid_offline": "...",
            "ubicacion_id": 12,
            "fecha_hora": "2026-06-08T...",
            "usuario_id": 1,
            "hallazgos": [
                {
                    "hallazgo_id": 1,
                    "detalle_personalizado": "...",
                    "google_drive_file_id": "...",
                    "foto_url": "..."
                }
            ]
        }
        """
        sincronizadas = 0
        duplicadas = 0
        errores = 0

        # Procesamos registro por registro para garantizar robustez e identificar fallos unitarios
        for ronda in rondas_lote:
            uuid_offline = ronda.get("uuid_offline")
            if not uuid_offline:
                errores += 1
                continue

            # 1. Validación anti-duplicados (Idempotencia)
            if await self.check_uuid_exists(uuid_offline):
                duplicadas += 1
                continue

            try:
                # 2. Insertar registro padre
                cursor = await self.db.execute("""
                    INSERT INTO porteria_rondas_registro (ubicacion_id, fecha_hora, usuario_id, uuid_offline, sincronizado_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    ronda.get("ubicacion_id"),
                    ronda.get("fecha_hora"),
                    ronda.get("usuario_id"),
                    uuid_offline
                ))
                registro_id = cursor.lastrowid

                # 3. Insertar hallazgos asociados
                hallazgos = ronda.get("hallazgos", [])
                for h in hallazgos:
                    await self.db.execute("""
                        INSERT INTO porteria_rondas_hallazgos (registro_id, hallazgo_id, detalle_personalizado, google_drive_file_id, foto_url)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        registro_id,
                        h.get("hallazgo_id"),
                        h.get("detalle_personalizado"),
                        h.get("google_drive_file_id"),
                        h.get("foto_url")
                    ))
                
                sincronizadas += 1
            except Exception as e:
                logger.error(f"❌ Error al sincronizar ronda offline {uuid_offline}: {e}")
                errores += 1

        # Realizar un sync explícito al final del lote para garantizar almacenamiento en Turso Cloud
        if sincronizadas > 0:
            await self.db.sync_to_cloud_explicit()

        return {
            "sincronizadas": sincronizadas,
            "duplicadas": duplicadas,
            "errores": errores
        }
