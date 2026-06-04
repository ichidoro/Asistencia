import os
import pandas as pd
from typing import List, Dict, Optional
from loguru import logger
from backend.core.database import db

class Productos4Repository:
    def __init__(self):
        self.db = db

    async def init_tables(self):
        """Inicializa las tablas de 4 Productos y siembra los productos de elaboración propia."""
        # 1. Crear tabla productos_elaboracion_propia (mismo nombre de tabla por consistencia)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS productos_elaboracion_propia (
                codigo INTEGER PRIMARY KEY,
                descripcion TEXT NOT NULL,
                tipo TEXT NOT NULL,
                marca TEXT NOT NULL,
                unidad TEXT NOT NULL,
                max_cantidad INTEGER DEFAULT 2,
                activo BOOLEAN DEFAULT 1
            )
        """)

        # 2. Crear tabla empleado_productos_periodo (mismo nombre de tabla por consistencia)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS empleado_productos_periodo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER NOT NULL,
                periodo_mes INTEGER NOT NULL,
                periodo_anio INTEGER NOT NULL,
                producto1_codigo INTEGER,
                producto2_codigo INTEGER,
                producto3_codigo INTEGER,
                producto4_codigo INTEGER,
                observaciones TEXT,
                usuario_creador_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(empleado_id) REFERENCES empleados(id),
                FOREIGN KEY(producto1_codigo) REFERENCES productos_elaboracion_propia(codigo),
                FOREIGN KEY(producto2_codigo) REFERENCES productos_elaboracion_propia(codigo),
                FOREIGN KEY(producto3_codigo) REFERENCES productos_elaboracion_propia(codigo),
                FOREIGN KEY(producto4_codigo) REFERENCES productos_elaboracion_propia(codigo),
                UNIQUE(empleado_id, periodo_mes, periodo_anio)
            )
        """)

        # --- MIGRACIÓN: Columnas de Entrega ---
        try:
            cols = set(await self.db.get_column_names("empleado_productos_periodo"))
            if "entregado" not in cols:
                await self.db.execute("ALTER TABLE empleado_productos_periodo ADD COLUMN entregado INTEGER DEFAULT 0")
                logger.info("✨ Migración: Columna 'entregado' agregada a empleado_productos_periodo")
            if "fecha_entrega" not in cols:
                await self.db.execute("ALTER TABLE empleado_productos_periodo ADD COLUMN fecha_entrega TEXT")
                logger.info("✨ Migración: Columna 'fecha_entrega' agregada a empleado_productos_periodo")
            if "usuario_entrega_id" not in cols:
                await self.db.execute("ALTER TABLE empleado_productos_periodo ADD COLUMN usuario_entrega_id INTEGER")
                logger.info("✨ Migración: Columna 'usuario_entrega_id' agregada a empleado_productos_periodo")
        except Exception as e:
            logger.warning(f"⚠️ Error al migrar columnas de entrega en empleado_productos_periodo: {e}")

        # --- TABLA DE CIERRES DE PERÍODOS DE 4 PRODUCTOS ---
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS productos_4_cierres (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                periodo_mes INTEGER NOT NULL,
                periodo_anio INTEGER NOT NULL,
                fecha_cierre TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usuario_id INTEGER NOT NULL,
                FOREIGN KEY(usuario_id) REFERENCES usuarios(id),
                UNIQUE(periodo_mes, periodo_anio)
            )
        """)
        
        # 3. Intentar sembrar desde Productos.xlsx de manera tolerante a fallos
        await self._sembrar_productos_excel()

    async def _sembrar_productos_excel(self):
        """Intenta sembrar productos desde Excel utilizando INSERT OR IGNORE."""
        try:
            excel_path = "Productos.xlsx"
            if not os.path.exists(excel_path):
                logger.warning(f"⚠️ [Productos4 Seeder] Archivo '{excel_path}' no encontrado. Se omite la siembra automatica.")
                return

            # Verificar si la tabla ya tiene registros
            row = await self.db.fetch_one("SELECT COUNT(*) as count FROM productos_elaboracion_propia")
            if row and row["count"] > 0:
                logger.info(f"☑️ [Productos4 Seeder] La tabla de productos propios ya tiene {row['count']} registros. Se omite siembra.")
                return

            # Leer Excel
            logger.info(f"💾 [Productos4 Seeder] Sembrando productos propios desde '{excel_path}'...")
            df = pd.read_excel(excel_path)
            required = {"Codigo Producto", "Descripcion", "Tipo Producto", "Marca", "Unidad", "Maximo"}
            missing = required - set(df.columns)
            if missing:
                logger.error(f"❌ [Productos4 Seeder] Error de columnas en Excel: {missing}")
                return

            operations = []
            for _, r in df.iterrows():
                query = """
                    INSERT OR IGNORE INTO productos_elaboracion_propia (codigo, descripcion, tipo, marca, unidad, max_cantidad)
                    VALUES (?, ?, ?, ?, ?, ?)
                """
                params = (
                    int(r["Codigo Producto"]),
                    str(r["Descripcion"]),
                    str(r["Tipo Producto"]),
                    str(r["Marca"]),
                    str(r["Unidad"]),
                    int(r["Maximo"])
                )
                operations.append((query, params))

            if operations:
                # Ejecutar por lotes usando el core seguro
                await self.db.execute_batch(operations)
                logger.success(f"✅ [Productos4 Seeder] Se sembraron exitosamente {len(operations)} productos.")

        except Exception as e:
            logger.error(f"⚠️ [Productos4 Seeder] Fallo no critico al sembrar productos propios: {e}")

    # --- Operaciones CRUD Catálogo ---

    async def get_all_productos(self, incluir_inactivos: bool = False) -> List[Dict]:
        query = "SELECT * FROM productos_elaboracion_propia"
        if not incluir_inactivos:
            query += " WHERE activo = 1"
        query += " ORDER BY descripcion ASC"
        rows = await self.db.fetch_all(query)
        return [dict(row) for row in rows]

    async def get_producto_by_codigo(self, codigo: int) -> Optional[Dict]:
        query = "SELECT * FROM productos_elaboracion_propia WHERE codigo = ?"
        row = await self.db.fetch_one(query, (codigo,))
        return dict(row) if row else None

    async def create_producto(self, codigo: int, descripcion: str, tipo: str, marca: str, unidad: str, max_cantidad: int) -> bool:
        query = """
            INSERT INTO productos_elaboracion_propia (codigo, descripcion, tipo, marca, unidad, max_cantidad)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        try:
            await self.db.execute(query, (codigo, descripcion, tipo, marca, unidad, max_cantidad))
            return True
        except Exception as e:
            logger.error(f"Error creando producto: {e}")
            return False

    async def update_producto(self, codigo: int, descripcion: str, tipo: str, marca: str, unidad: str, max_cantidad: int, activo: bool) -> bool:
        query = """
            UPDATE productos_elaboracion_propia
            SET descripcion = ?, tipo = ?, marca = ?, unidad = ?, max_cantidad = ?, activo = ?
            WHERE codigo = ?
        """
        try:
            await self.db.execute(query, (descripcion, tipo, marca, unidad, max_cantidad, 1 if activo else 0, codigo))
            return True
        except Exception as e:
            logger.error(f"Error actualizando producto: {e}")
            return False

    # --- Operaciones de Asignación por Periodo ---

    async def get_asignaciones_periodo(self, mes: int, anio: int) -> List[Dict]:
        query = """
            SELECT p.*, e.nombre as empleado_nombre, e.rut as empleado_rut
            FROM empleado_productos_periodo p
            JOIN empleados e ON p.empleado_id = e.id
            WHERE p.periodo_mes = ? AND p.periodo_anio = ?
        """
        rows = await self.db.fetch_all(query, (mes, anio))
        return [dict(row) for row in rows]

    async def get_asignacion_empleado(self, empleado_id: int, mes: int, anio: int) -> Optional[Dict]:
        query = """
            SELECT * FROM empleado_productos_periodo
            WHERE empleado_id = ? AND periodo_mes = ? AND periodo_anio = ?
        """
        row = await self.db.fetch_one(query, (empleado_id, mes, anio))
        return dict(row) if row else None

    async def save_asignacion(
        self, empleado_id: int, mes: int, anio: int, 
        p1: Optional[int], p2: Optional[int], p3: Optional[int], p4: Optional[int], 
        observaciones: Optional[str], usuario_creador_id: int
    ) -> bool:
        query = """
            INSERT INTO empleado_productos_periodo (
                empleado_id, periodo_mes, periodo_anio, 
                producto1_codigo, producto2_codigo, producto3_codigo, producto4_codigo, 
                observaciones, usuario_creador_id, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(empleado_id, periodo_mes, periodo_anio) DO UPDATE SET
                producto1_codigo = excluded.producto1_codigo,
                producto2_codigo = excluded.producto2_codigo,
                producto3_codigo = excluded.producto3_codigo,
                producto4_codigo = excluded.producto4_codigo,
                observaciones = excluded.observaciones,
                usuario_creador_id = excluded.usuario_creador_id,
                updated_at = CURRENT_TIMESTAMP
        """
        try:
            await self.db.execute(query, (
                empleado_id, mes, anio, p1, p2, p3, p4, observaciones, usuario_creador_id
            ))
            return True
        except Exception as e:
            logger.error(f"Error guardando asignacion de 4 Productos: {e}")
            return False

    async def get_raw_asignaciones_periodo(self, mes: int, anio: int, areas: Optional[List[str]] = None) -> List[Dict]:
        """
        Obtiene asignaciones de productos para un periodo, opcionalmente filtradas por RLS de áreas.
        """
        query = """
            SELECT p.*,
                   e.nombre || ' ' || e.apellido_paterno || ' ' || e.apellido_materno AS empleado_nombre,
                   e.rut AS empleado_rut,
                   e.cargo AS empleado_cargo,
                   a.nombre AS area_nombre,
                   u.username AS usuario_entrega_nombre
            FROM empleado_productos_periodo p
            JOIN empleados e ON p.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a ON ha.area_id = a.id
            LEFT JOIN usuarios u ON p.usuario_entrega_id = u.id
            WHERE p.periodo_mes = ? AND p.periodo_anio = ?
        """
        params = [mes, anio]
        if areas is not None and len(areas) > 0:
            placeholders = ",".join(["?"] * len(areas))
            query += f" AND a.nombre IN ({placeholders})"
            params.extend(areas)
            
        rows = await self.db.fetch_all(query, tuple(params))
        return [dict(row) for row in rows]

    async def update_delivery_status(
        self, empleado_id: int, mes: int, anio: int, entregado: bool, usuario_entrega_id: int
    ) -> bool:
        """
        Actualiza el estado de entrega del beneficio de productos propios.
        """
        if entregado:
            query = """
                UPDATE empleado_productos_periodo
                SET entregado = 1,
                    fecha_entrega = datetime('now', 'localtime'),
                    usuario_entrega_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE empleado_id = ? AND periodo_mes = ? AND periodo_anio = ?
            """
            params = (usuario_entrega_id, empleado_id, mes, anio)
        else:
            query = """
                UPDATE empleado_productos_periodo
                SET entregado = 0,
                    fecha_entrega = NULL,
                    usuario_entrega_id = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE empleado_id = ? AND periodo_mes = ? AND periodo_anio = ?
            """
            params = (empleado_id, mes, anio)
            
        try:
            await self.db.execute(query, params)
            return True
        except Exception as e:
            logger.error(f"Error actualizando estado de entrega: {e}")
            return False

    async def is_period_closed(self, mes: int, anio: int) -> bool:
        row = await self.db.fetch_one(
            "SELECT 1 FROM productos_4_cierres WHERE periodo_mes = ? AND periodo_anio = ?",
            (mes, anio)
        )
        return row is not None

    async def close_period(self, mes: int, anio: int, usuario_id: int) -> bool:
        try:
            await self.db.execute(
                """
                INSERT OR IGNORE INTO productos_4_cierres (periodo_mes, periodo_anio, usuario_id)
                VALUES (?, ?, ?)
                """,
                (mes, anio, usuario_id)
            )
            return True
        except Exception as e:
            logger.error(f"Error al cerrar periodo {anio}-{mes}: {e}")
            return False

    async def reopen_period(self, mes: int, anio: int) -> bool:
        try:
            await self.db.execute(
                "DELETE FROM productos_4_cierres WHERE periodo_mes = ? AND periodo_anio = ?",
                (mes, anio)
            )
            return True
        except Exception as e:
            logger.error(f"Error al reabrir periodo {anio}-{mes}: {e}")
            return False

    async def has_assignments_in_period(self, mes: int, anio: int) -> bool:
        row = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM empleado_productos_periodo WHERE periodo_mes = ? AND periodo_anio = ? LIMIT 1",
            (mes, anio)
        )
        return row is not None and row["count"] > 0

