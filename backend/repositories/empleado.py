"""
Repository - Empleado
Capa de acceso a datos para Empleados
"""

import json
import re
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from loguru import logger

from backend.core.database import Database
from backend.models.empleado import Empleado


class BorradoPermanenteBloqueado(Exception):
    """La persona tiene días en un tramo cerrado: se le registra la baja, no se borra (orden del dueño, 28-10-2026)."""

    def __init__(self, tramos: List[dict]):
        self.tramos = tramos
        super().__init__(f"{sum(int(t.get('dias') or 0) for t in tramos)} días en tramos cerrados")


class EmpleadoRepository:
    """
    Repository para operaciones CRUD de Empleados en la base de datos.
    Implementa el patrón Repository para abstraer el acceso a datos.
    """
    
    def __init__(self, db: Database):
        self.db = db
    
    async def create_table(self) -> None:
        """Crear tabla de empleados si no existe y asegurar esquema actualizado"""
        
        if not await self.db.table_exists("empleados"):
            query = """
            CREATE TABLE IF NOT EXISTS areas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            
            CREATE TABLE IF NOT EXISTS areas_alias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias TEXT NOT NULL UNIQUE,
                area_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (area_id) REFERENCES areas (id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS cargos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                excluido_asistencia INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            
            CREATE TABLE IF NOT EXISTS cargos_alias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias TEXT NOT NULL UNIQUE,
                cargo_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (cargo_id) REFERENCES cargos (id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS empleados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rut TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                apellido_paterno TEXT NOT NULL,
                apellido_materno TEXT NOT NULL,
                cargo TEXT,
                cargo_id INTEGER,
                area_id INTEGER,
                compania TEXT,
                email TEXT,
                telefono TEXT,
                activo INTEGER DEFAULT 1,
                fecha_nacimiento TEXT,
                fecha_ingreso TEXT,
                fecha_salida TEXT,
                tipo_contrato TEXT DEFAULT 'Indefinido',
                cant_contratos INTEGER DEFAULT 1,
                decision_vencimiento TEXT,
                es_manual INTEGER DEFAULT 0,
                excluido_asistencia INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (area_id) REFERENCES areas (id),
                FOREIGN KEY (cargo_id) REFERENCES cargos (id)
            )
            """
            
            await self.db.execute_script(query)
            
            # Crear índices
            await self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_empleados_rut ON empleados(rut)"
            )
            await self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_empleados_activo ON empleados(activo)"
            )
            await self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_empleados_area ON empleados(area_id)"
            )
            logger.info("✨ Tabla empleados creada desde cero")
        else:
            logger.debug("⚡ Tabla empleados ya existe (Saltando DDL base)")
        
        # --- NUEVO: Tabla historial_areas ---
        if not await self.db.table_exists("historial_areas"):
            query_hist = """
            CREATE TABLE IF NOT EXISTS historial_areas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER NOT NULL,
                area_id INTEGER NOT NULL,
                fecha_desde TEXT NOT NULL,
                fecha_hasta TEXT,
                es_actual INTEGER DEFAULT 1,
                validado INTEGER DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (empleado_id) REFERENCES empleados (id),
                FOREIGN KEY (area_id) REFERENCES areas (id)
            )
            """
            await self.db.execute(query_hist)
            await self.db.execute("CREATE INDEX IF NOT EXISTS idx_historial_emp ON historial_areas(empleado_id)")
            await self.db.execute("CREATE INDEX IF NOT EXISTS idx_historial_area ON historial_areas(area_id)")
            logger.info("✨ Tabla historial_areas creada")
            
            # Auto-poblar historial inicial para empleados existentes
            try:
                count_hist = await self.db.fetch_one("SELECT COUNT(*) as count FROM historial_areas")
                if count_hist["count"] == 0:
                    logger.info("🔄 Poblando historial de áreas inicial desde tabla empleados...")
                    await self.db.execute("""
                        INSERT INTO historial_areas (empleado_id, area_id, fecha_desde, es_actual, validado)
                        SELECT id, area_id, COALESCE(fecha_ingreso, '2020-01-01'), 1, 1 
                        FROM empleados 
                        WHERE area_id IS NOT NULL
                    """)
                    logger.success("✅ Historial inicial poblado exitosamente")
            except Exception as e:
                logger.error(f"❌ Error poblando historial inicial: {e}")
        else:
            logger.debug("⚡ Tabla historial_areas ya existe")

        # --- Historial de cargos con fecha (etapa B4 del plan de bonos, 22-11-2026) ---
        # El bono de un cargo se paga por los días en que la persona tuvo ese cargo. La primera vez, cada persona queda
        # con su cargo de la ficha desde su ingreso (así nada cambia hasta que alguien registre un cambio de labor).
        if not await self.db.table_exists("historial_cargos"):
            await self.db.execute("""
            CREATE TABLE IF NOT EXISTS historial_cargos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER NOT NULL,
                cargo_id INTEGER NOT NULL,
                fecha_desde TEXT NOT NULL,
                fecha_hasta TEXT,
                motivo TEXT,
                usuario TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empleado_id) REFERENCES empleados (id),
                FOREIGN KEY (cargo_id) REFERENCES cargos (id)
            )
            """)
            await self.db.execute("CREATE INDEX IF NOT EXISTS idx_hist_cargos_emp ON historial_cargos(empleado_id, fecha_desde)")
            filas = await self.db.fetch_all("SELECT id, cargo_id, fecha_ingreso FROM empleados WHERE cargo_id IS NOT NULL")
            ops = [("INSERT INTO historial_cargos (empleado_id, cargo_id, fecha_desde, motivo) VALUES (?, ?, ?, ?)",
                    (f['id'], f['cargo_id'], str(f['fecha_ingreso'] or '2000-01-01')[:10], 'Cargo de la ficha al crear el historial'))
                   for f in filas]
            if ops:
                await self.db.execute_batch(ops)
            logger.info(f"✨ Tabla historial_cargos creada: {len(ops)} personas con su cargo actual desde su ingreso")

        # Migración Inteligente: 1 sola llamada get_column_names() en vez de N column_exists() individuales
        try:
            cols_empleados = set(await self.db.get_column_names("empleados"))
            new_columns = {
                "fecha_nacimiento": "TEXT",
                "cant_contratos": "INTEGER DEFAULT 1",
                "genero": "TEXT",
                "genero_id": "INTEGER",
                "decision_vencimiento": "TEXT",
                "cargo_id": "INTEGER REFERENCES cargos(id)",
                "es_manual": "INTEGER DEFAULT 0",
                "excluido_asistencia": "INTEGER DEFAULT 0",
                "autorizado_llaves": "INTEGER DEFAULT 0",
                # 1 = el cargo se cambió a mano (ficha o cambio de labor): la sincronización con BioAlba no lo pisa (25-11-2026)
                "cargo_local": "INTEGER DEFAULT 0"
            }

            for col_name, col_def in new_columns.items():
                if col_name not in cols_empleados:
                    try:
                        await self.db.execute(f"ALTER TABLE empleados ADD COLUMN {col_name} {col_def}")
                        logger.info(f"✨ Migración: Columna '{col_name}' agregada a empleados")
                    except Exception as e:
                        logger.error(f"❌ Error agregando {col_name}: {e}")
            
            # --- NUEVO: Creación de tablas de cargos para migración de DBs existentes ---
            if not await self.db.table_exists("cargos"):
                await self.db.execute("""
                CREATE TABLE IF NOT EXISTS cargos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL UNIQUE,
                    excluido_asistencia INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                """)
                logger.info("✨ Tabla cargos creada (migración)")
            else:
                # Si cargos ya existe, verificar columna excluido_asistencia
                cols_cargos = set(await self.db.get_column_names("cargos"))
                if "excluido_asistencia" not in cols_cargos:
                    await self.db.execute("ALTER TABLE cargos ADD COLUMN excluido_asistencia INTEGER DEFAULT 0")
                    logger.info("✨ Migración: Columna 'excluido_asistencia' agregada a cargos")
            
            if not await self.db.table_exists("cargos_alias"):
                await self.db.execute("""
                CREATE TABLE IF NOT EXISTS cargos_alias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias TEXT NOT NULL UNIQUE,
                    cargo_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (cargo_id) REFERENCES cargos (id) ON DELETE CASCADE
                );
                """)
                logger.info("✨ Tabla cargos_alias creada (migración)")
                
            # --- NUEVO: Tabla de cat_generos ---
            if not await self.db.table_exists("cat_generos"):
                await self.db.execute("""
                CREATE TABLE IF NOT EXISTS cat_generos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL UNIQUE
                );
                """)
                logger.info("✨ Tabla cat_generos creada (migración)")

            # --- SANEAMIENTO Y PROTECCIÓN: Deduplicación de historial_areas ---
            try:
                # 1. Depurar duplicados en historial_areas: mantener sólo el registro con MAX(id) por empleado
                await self.db.execute("""
                    DELETE FROM historial_areas
                    WHERE id IN (
                        SELECT h1.id
                        FROM historial_areas h1
                        JOIN historial_areas h2 ON h1.empleado_id = h2.empleado_id
                        WHERE h1.es_actual = 1 AND h1.validado = 1
                          AND h2.es_actual = 1 AND h2.validado = 1
                          AND h1.id < h2.id
                    )
                """)
                logger.info("✨ Saneamiento: Duplicados en historial_areas depurados exitosamente")
            except Exception as e_hdup:
                logger.warning(f"⚠️ Saneamiento historial_areas: {e_hdup}")

            # 2. Crear índice único parcial para garantizar 1 solo registro activo/validado por empleado
            try:
                await self.db.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_historial_areas_actual_validado 
                    ON historial_areas (empleado_id) 
                    WHERE es_actual = 1 AND validado = 1
                """)
                logger.info("✨ Índice único parcial en historial_areas verificado")
            except Exception as e_idx:
                logger.warning(f"⚠️ Índice uq_historial_areas_actual_validado: {e_idx}")

            # 3. Saneamiento de empleados duplicados por RUT normalizado (si existieran)
            try:
                dup_ruts = await self.db.fetch_all("""
                    SELECT REPLACE(REPLACE(REPLACE(UPPER(rut), '.', ''), '-', ''), ' ', '') as rut_clean, COUNT(*) as cnt
                    FROM empleados
                    GROUP BY REPLACE(REPLACE(REPLACE(UPPER(rut), '.', ''), '-', ''), ' ', '')
                    HAVING COUNT(*) > 1
                """)
                for r in dup_ruts:
                    rut_clean = r['rut_clean']
                    emps = await self.db.fetch_all("""
                        SELECT id, rut, created_at, activo FROM empleados
                        WHERE REPLACE(REPLACE(REPLACE(UPPER(rut), '.', ''), '-', ''), ' ', '') = ?
                        ORDER BY id ASC
                    """, (rut_clean,))
                    if len(emps) > 1:
                        primary_id = emps[0]['id']
                        for dup in emps[1:]:
                            dup_id = dup['id']
                            logger.warning(f"🧹 Fusionando empleado duplicado ID {dup_id} hacia ID principal {primary_id} (RUT: {rut_clean})")
                            await self.db.execute("UPDATE asignacion_turnos SET empleado_id = ? WHERE empleado_id = ?", (primary_id, dup_id))
                            await self.db.execute("UPDATE asistencias SET empleado_id = ? WHERE empleado_id = ?", (primary_id, dup_id))
                            await self.db.execute("UPDATE horas_extras SET empleado_id = ? WHERE empleado_id = ?", (primary_id, dup_id))
                            await self.db.execute("UPDATE logs_raw SET empleado_id = ? WHERE empleado_id = ?", (primary_id, dup_id))
                            await self.db.execute("UPDATE historial_areas SET empleado_id = ? WHERE empleado_id = ?", (primary_id, dup_id))
                            await self.db.execute("DELETE FROM empleados WHERE id = ?", (dup_id,))
                            logger.success(f"✅ Empleado duplicado ID {dup_id} fusionado y eliminado exitosamente")
            except Exception as e_edup:
                logger.warning(f"⚠️ Saneamiento empleados duplicados: {e_edup}")
            
        except Exception as e:
            logger.warning(f"⚠️ Error en migración de esquema de empleados: {e}")
        
        logger.info("✅ Tabla empleados verificada")
    
    async def create(self, empleado: Empleado) -> Empleado:
        """Crear un nuevo empleado"""
        query = """
        INSERT INTO empleados (
            rut, nombre, apellido_paterno, apellido_materno,
            cargo, cargo_id, area_id, compania, email, telefono, genero, genero_id, activo,
            fecha_nacimiento, fecha_ingreso, fecha_salida, tipo_contrato, cant_contratos, decision_vencimiento,
            es_manual, excluido_asistencia, autorizado_llaves
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        # Mapeo manual si viene solo genero (por compatibilidad)
        gen_id = empleado.genero_id
        if gen_id is None and empleado.genero:
            g_name = str(empleado.genero).strip()
            res_gen = await self.db.fetch_one("SELECT id FROM cat_generos WHERE LOWER(nombre) = ?", (g_name.lower(),))
            if res_gen:
                gen_id = res_gen['id']
            else:
                try:
                    cursor_gen = await self.db.execute("INSERT INTO cat_generos (nombre) VALUES (?)", (g_name,))
                    gen_id = cursor_gen.lastrowid
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo crear género '{g_name}' en cat_generos (create): {e}")
            
        cursor = await self.db.execute(query, (
            empleado.rut,
            empleado.nombre,
            empleado.apellido_paterno,
            empleado.apellido_materno,
            empleado.cargo,
            empleado.cargo_id,
            empleado.area_id,
            empleado.compania,
            empleado.email,
            empleado.telefono,
            empleado.genero,
            gen_id,
            1 if empleado.activo else 0,
            empleado.fecha_nacimiento,
            empleado.fecha_ingreso,
            empleado.fecha_salida,
            empleado.tipo_contrato or "Indefinido",
            empleado.cant_contratos,
            empleado.decision_vencimiento,
            1 if empleado.es_manual else 0,
            1 if empleado.excluido_asistencia else 0,
            empleado.autorizado_llaves
        ))
        
        empleado.id = cursor.lastrowid
        
        logger.info(f"Empleado creado: {empleado.nombre_completo} (ID: {empleado.id})")
        
        # Opcional: Recargar de DB para tener los defaults aplicados (created_at, etc)
        return await self.get_by_id(empleado.id)
    
    async def get_by_id(self, empleado_id: int) -> Optional[Empleado]:
        """Obtener empleado por ID (con info de turno asignado)"""
        query = """
            SELECT e.*, COALESCE(a_hist.nombre, a_emp.nombre) as area, cg.nombre as genero_nombre, MAX(at.fecha_inicio) as fecha_asignacion_turno
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a_hist ON ha.area_id = a_hist.id
            LEFT JOIN areas a_emp ON e.area_id = a_emp.id
            LEFT JOIN cat_generos cg ON e.genero_id = cg.id
            LEFT JOIN asignacion_turnos at ON e.id = at.empleado_id
            WHERE e.id = ?
            GROUP BY e.id
        """
        
        result = await self.db.fetch_one(query, (empleado_id,))
        
        if not result:
            return None
        
        return self._dict_to_empleado(result)
    
    async def get_by_rut(self, rut: str) -> Optional[Empleado]:
        """Obtener empleado por RUT con normalización de formato"""
        if not rut:
            return None
        rut_clean = str(rut).replace(".", "").replace("-", "").strip().upper()
        query = """
            SELECT e.*, COALESCE(a_hist.nombre, a_emp.nombre) as area, cg.nombre as genero_nombre
            FROM empleados e
            LEFT JOIN (
                SELECT empleado_id, MAX(area_id) as area_id
                FROM historial_areas
                WHERE es_actual = 1 AND validado = 1
                GROUP BY empleado_id
            ) ha ON e.id = ha.empleado_id
            LEFT JOIN areas a_hist ON ha.area_id = a_hist.id
            LEFT JOIN areas a_emp ON e.area_id = a_emp.id
            LEFT JOIN cat_generos cg ON e.genero_id = cg.id
            WHERE e.rut = ? OR REPLACE(REPLACE(REPLACE(UPPER(e.rut), '.', ''), '-', ''), ' ', '') = ?
            LIMIT 1
        """
        
        result = await self.db.fetch_one(query, (rut, rut_clean))
        
        if not result:
            return None
        
        return self._dict_to_empleado(result)
    
    async def get_all(
        self, 
        skip: int = 0, 
        limit: int = 100,
        activo: Optional[bool] = None,
        sort_by: str = "apellido_paterno",
        order: str = "asc",
        areas: Optional[List[str]] = None
    ) -> List[Empleado]:
        """Obtener todos los empleados con paginación y ordenamiento filtrado por áreas"""
        query = """
            SELECT e.*, COALESCE(a_hist.nombre, a_emp.nombre) as area, cg.nombre as genero_nombre, MAX(at.fecha_inicio) as fecha_asignacion_turno
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a_hist ON ha.area_id = a_hist.id
            LEFT JOIN areas a_emp ON e.area_id = a_emp.id
            LEFT JOIN cat_generos cg ON e.genero_id = cg.id
            LEFT JOIN asignacion_turnos at ON e.id = at.empleado_id
        """
        params = []
        conditions = []
        
        if activo is not None:
            conditions.append("e.activo = ?")
            params.append(1 if activo else 0)
            
        if areas is not None and len(areas) > 0:
            placeholders = ",".join(["?"] * len(areas))
            conditions.append(f"COALESCE(a_hist.nombre, a_emp.nombre) IN ({placeholders})")
            params.extend(areas)
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " GROUP BY e.id"

        # Validación básica de columnas para evitar inyección SQL
        valid_columns = ["id", "rut", "nombre", "apellido_paterno", "cargo", "area", "compania", "tipo_contrato", "activo"]
        if sort_by not in valid_columns:
            sort_by = "apellido_paterno"
        
        direction = "DESC" if order.lower() == "desc" else "ASC"
        
        # Construcción dinámica del ORDER BY
        if sort_by == "nombre":
            query += f" ORDER BY e.apellido_paterno {direction}, e.apellido_materno {direction}, e.nombre {direction}"
        else:
            query += f" ORDER BY e.{sort_by} {direction}"
            
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, skip])
        
        results = await self.db.fetch_all(query, tuple(params))
        
        return [self._dict_to_empleado(row) for row in results]
    
    async def search(
        self,
        q: Optional[str] = None,
        area: Optional[str] = None,
        compania: Optional[str] = None,
        activo: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "apellido_paterno",
        order: str = "asc",
        areas_permitidas: Optional[List[str]] = None
    ) -> List[Empleado]:
        """Buscar empleados con filtros y ordenamiento implementando RLS por áreas"""
        query = """
            SELECT e.*, COALESCE(a_hist.nombre, a_emp.nombre) as area, cg.nombre as genero_nombre, MAX(at.fecha_inicio) as fecha_asignacion_turno
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a_hist ON ha.area_id = a_hist.id
            LEFT JOIN areas a_emp ON e.area_id = a_emp.id
            LEFT JOIN cat_generos cg ON e.genero_id = cg.id
            LEFT JOIN asignacion_turnos at ON e.id = at.empleado_id
            WHERE 1=1
        """
        params = []
        
        # Security Data Scoping
        if areas_permitidas is not None and len(areas_permitidas) > 0:
            # Si buscaron un area en específico pero no la tienen permitida, forzamos la lista
            if area and area not in areas_permitidas:
                return [] # 403 Virtual, el user buscó fuera de su scope
            placeholders = ",".join(["?"] * len(areas_permitidas))
            query += f" AND COALESCE(a_hist.nombre, a_emp.nombre) IN ({placeholders})"
            params.extend(areas_permitidas)
        
        if q:
            query += """ AND (
                e.nombre LIKE ? OR 
                e.apellido_paterno LIKE ? OR 
                e.apellido_materno LIKE ? OR
                e.rut LIKE ? OR
                e.cargo LIKE ?
            )"""
            search_pattern = f"%{q}%"
            params.extend([search_pattern] * 5)
        
        if area:
            query += " AND COALESCE(a_hist.nombre, a_emp.nombre) = ?"
            params.append(area)
        
        if compania:
            query += " AND e.compania = ?"
            params.append(compania)
        
        if activo is not None:
            query += " AND e.activo = ?"
            params.append(1 if activo else 0)
        
        query += " GROUP BY e.id"

        # Validación de ordenamiento
        valid_columns = ["id", "rut", "nombre", "apellido_paterno", "cargo", "area", "compania", "tipo_contrato", "activo"]
        if sort_by not in valid_columns:
            sort_by = "apellido_paterno"
            
        direction = "DESC" if order.lower() == "desc" else "ASC"
        
        if sort_by == "apellido_paterno":
            query += f" ORDER BY e.apellido_paterno {direction}, e.apellido_materno {direction}, e.nombre {direction}"
        else:
            query += f" ORDER BY e.{sort_by} {direction}"
            
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, skip])
        
        results = await self.db.fetch_all(query, tuple(params))
        
        return [self._dict_to_empleado(row) for row in results]
    
    async def count(self, activo: Optional[bool] = None, areas: Optional[List[str]] = None) -> int:
        """Contar empleados respetando RLS"""
        query = "SELECT COUNT(*) as total FROM empleados"
        conditions = []
        params = []
        
        if activo is not None:
            conditions.append("activo = ?")
            params.append(1 if activo else 0)
            
        if areas is not None and len(areas) > 0:
            placeholders = ",".join(["?"] * len(areas))
            query_from = """SELECT COUNT(*) as total FROM empleados e LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a_hist ON ha.area_id = a_hist.id
            LEFT JOIN areas a_emp ON e.area_id = a_emp.id"""
            conditions.append(f"COALESCE(a_hist.nombre, a_emp.nombre) IN ({placeholders})")
            params.extend(areas)
        else:
            query_from = "SELECT COUNT(*) as total FROM empleados e"

        if conditions:
            query = query_from + " WHERE " + " AND ".join(conditions)
        else:
            query = query_from
        
        result = await self.db.fetch_one(query, tuple(params) if params else None)
        
        return result["total"] if result else 0

    async def get_all_ruts(self) -> List[str]:
        """Obtener lista de todos los RUTs existentes (para filtrado eficiente)"""
        query = "SELECT rut FROM empleados"
        results = await self.db.fetch_all(query)
        return [row['rut'] for row in results]

    async def get_rut_id_map(self) -> Dict[str, int]:
        """
        Retorna un diccionario {rut: id} de todos los empleados.
        Útil para mapeos masivos en sincronización.
        """
        try:
            query = "SELECT id, rut FROM empleados WHERE rut IS NOT NULL"
            rows = await self.db.fetch_all(query)
            # Retornar mapa con RUT original y RUT limpio para mayor compatibilidad
            res = {}
            for r in rows:
                rut = str(r['rut']).strip()
                res[rut] = r['id']
                # También mapear versión limpia (sin puntos ni guión)
                rut_clean = rut.replace(".", "").replace("-", "").replace(" ", "").strip()
                res[rut_clean] = r['id']
            return res
        except Exception as e:
            logger.error(f"Error obteniendo rut_id_map: {e}")
            raise

    async def get_ruts_by_areas_with_pending(self, areas: List[str]) -> List[str]:
        """
        Obtener RUTs de empleados que:
        1. Su área actual en la tabla 'empleados' está en la lista.
        2. Tienen un cambio de área PENDIENTE (validado=0) a una de esas áreas.
        """
        if not areas:
            return []
            
        placeholders = ",".join(["?"] * len(areas))
        
        # Query que une empleados actuales + pendientes en historial
        query = f"""
            SELECT DISTINCT e.rut 
            FROM empleados e
            LEFT JOIN historial_areas ha_actual ON e.id = ha_actual.empleado_id AND ha_actual.es_actual = 1 AND ha_actual.validado = 1
            LEFT JOIN areas a_actual ON ha_actual.area_id = a_actual.id
            LEFT JOIN areas a_emp ON e.area_id = a_emp.id
            LEFT JOIN historial_areas h ON e.id = h.empleado_id
            LEFT JOIN areas a_hist ON h.area_id = a_hist.id
            WHERE COALESCE(a_actual.nombre, a_emp.nombre) IN ({placeholders})
               OR (a_hist.nombre IN ({placeholders}) AND h.validado = 0)
        """
        
        # Duplicamos los parámetros porque el placeholder se usa dos veces
        params = tuple(areas + areas)
        results = await self.db.fetch_all(query, params)
        return [row['rut'] for row in results]

    async def get_all_areas(self) -> List[str]:
        """Obtener lista de todas las áreas únicas registradas localmente"""
        query = "SELECT DISTINCT nombre as area FROM areas ORDER BY nombre ASC"
        results = await self.db.fetch_all(query)
        return [row['area'] for row in results]

    async def auto_cerrar_bajas_cumplidas(self) -> List[dict]:
        """
        Desactiva automáticamente (activo = 0) a los empleados con decisión de NO_RENOVAR
        o baja cuya fecha_salida ya se cumplió (fecha_salida <= date.today()).
        Retorna la lista de empleados desactivados para limpieza de turnos/asistencias.
        """
        import datetime
        today = datetime.date.today().isoformat()
        query_select = """
            SELECT id, fecha_salida FROM empleados
            WHERE activo = 1
              AND fecha_salida IS NOT NULL
              AND fecha_salida <= ?
              AND (decision_vencimiento LIKE 'NO_RENOVAR%' OR decision_vencimiento LIKE 'BAJA%')
        """
        rows = await self.db.fetch_all(query_select, (today,))
        if rows:
            ids = [r['id'] for r in rows]
            placeholders = ",".join(["?"] * len(ids))
            query_update = f"UPDATE empleados SET activo = 0 WHERE id IN ({placeholders})"
            await self.db.execute(query_update, tuple(ids))
            return [dict(r) for r in rows]
        return []

    async def get_upcoming_expirations(self, days: int = 30, areas: Optional[List[str]] = None) -> List[Empleado]:
        """
        Obtener empleados con contratos próximos a vencer con RLS.
        """
        import datetime
        
        today = datetime.date.today().isoformat()
        future_date = (datetime.date.today() + datetime.timedelta(days=days)).isoformat()
        
        params = []
        area_filter = ""
        
        if areas and len(areas) > 0:
            placeholders = ",".join(["?"] * len(areas))
            area_filter = f" AND COALESCE(a_hist.nombre, a_emp.nombre) IN ({placeholders})"
            params.extend(areas)
            
        params.extend([future_date, today])

        query = f"""
            SELECT e.*, COALESCE(a_hist.nombre, a_emp.nombre) as area 
            FROM empleados e
            LEFT JOIN (
                SELECT empleado_id, MAX(area_id) as area_id
                FROM historial_areas
                WHERE es_actual = 1 AND validado = 1
                GROUP BY empleado_id
            ) ha ON e.id = ha.empleado_id
            LEFT JOIN areas a_hist ON ha.area_id = a_hist.id 
            LEFT JOIN areas a_emp ON e.area_id = a_emp.id
            WHERE e.activo = 1 {area_filter}
            AND e.fecha_salida IS NOT NULL AND (e.fecha_salida <= ?)
            ORDER BY 
                CASE 
                    WHEN fecha_salida IS NULL THEN 1 
                    WHEN fecha_salida < ? THEN 0
                    ELSE 2 
                END ASC,
                fecha_salida ASC
        """
        
        results = await self.db.fetch_all(query, tuple(params))
        
        # Inyectar metadata extra para el frontend
        vencimientos = []
        for row in results:
            emp = self._dict_to_empleado(row)
            # Enriquecemos con los campos de la fila (como fecha_ingreso que ya está en emp)
            vencimientos.append(emp)
            
        return vencimientos
        
    async def get_terminated_by_month(self, month: int, year: int, areas: Optional[List[str]] = None) -> List[Empleado]:
        """
        Obtener empleados cuya fecha de salida cae en el mes con RLS.
        """
        import calendar
        from datetime import date
        
        start_date = date(year, month, 1).isoformat()
        last_day = calendar.monthrange(year, month)[1]
        end_date = date(year, month, last_day).isoformat()
        
        area_filter = ""
        params = [start_date, end_date]
        
        if areas and len(areas) > 0:
            placeholders = ",".join(["?"] * len(areas))
            area_filter = f" AND COALESCE(a_hist.nombre, a_emp.nombre) IN ({placeholders})"
            params.extend(areas)

        query = f"""
            SELECT e.*, COALESCE(a_hist.nombre, a_emp.nombre) as area
            FROM empleados e
            LEFT JOIN (
                SELECT empleado_id, MAX(area_id) as area_id
                FROM historial_areas
                WHERE es_actual = 1 AND validado = 1
                GROUP BY empleado_id
            ) ha ON e.id = ha.empleado_id
            LEFT JOIN areas a_hist ON ha.area_id = a_hist.id
            LEFT JOIN areas a_emp ON e.area_id = a_emp.id
            WHERE e.fecha_salida BETWEEN ? AND ? {area_filter}
            ORDER BY e.fecha_salida ASC
        """
        
        results = await self.db.fetch_all(query, tuple(params))
        
        empleados = []
        for row in results:
            emp = self._dict_to_empleado(row)
            empleados.append(emp)
            
        return empleados

    async def count_search(
        self,
        q: Optional[str] = None,
        area: Optional[str] = None,
        compania: Optional[str] = None,
        activo: Optional[bool] = None,
        areas_permitidas: Optional[List[str]] = None
    ) -> int:
        """Contar empleados con filtros de búsqueda y RLS"""
        query = """SELECT COUNT(*) as total FROM empleados e LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a_hist ON ha.area_id = a_hist.id
            LEFT JOIN areas a_emp ON e.area_id = a_emp.id WHERE 1=1"""
        params = []
        
        # Security Data Scoping
        if areas_permitidas is not None and len(areas_permitidas) > 0:
            if area and area not in areas_permitidas:
                return 0
            placeholders = ",".join(["?"] * len(areas_permitidas))
            query += f" AND COALESCE(a_hist.nombre, a_emp.nombre) IN ({placeholders})"
            params.extend(areas_permitidas)
        
        if q:
            query += """ AND (
                e.nombre LIKE ? OR 
                e.apellido_paterno LIKE ? OR 
                e.apellido_materno LIKE ? OR
                e.rut LIKE ? OR
                e.cargo LIKE ?
            )"""
            search_pattern = f"%{q}%"
            params.extend([search_pattern] * 5)
        
        if area:
            query += " AND COALESCE(a_hist.nombre, a_emp.nombre) = ?"
            params.append(area)
        
        if compania:
            query += " AND e.compania = ?"
            params.append(compania)
        
        if activo is not None:
            query += " AND e.activo = ?"
            params.append(1 if activo else 0)
        
        result = await self.db.fetch_one(query, tuple(params))
        
        return result["total"] if result else 0
    
    async def update(self, empleado_id: int, empleado: Empleado) -> Optional[Empleado]:
        """Actualizar empleado"""
        query = """
        UPDATE empleados SET
            rut = ?,
            nombre = ?,
            apellido_paterno = ?,
            apellido_materno = ?,
            cargo = ?,
            cargo_id = ?,
            area_id = ?,
            compania = ?,
            email = ?,
            telefono = ?,
            genero = ?,
            genero_id = ?,
            activo = ?,
            fecha_nacimiento = ?,
            fecha_ingreso = ?,
            fecha_salida = ?,
            tipo_contrato = ?,
            cant_contratos = ?,
            decision_vencimiento = ?,
            es_manual = ?,
            excluido_asistencia = ?,
            autorizado_llaves = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """
        
        # Mapeo manual si viene solo genero (por compatibilidad)
        gen_id = empleado.genero_id
        if gen_id is None and empleado.genero:
            g_name = str(empleado.genero).strip()
            res_gen = await self.db.fetch_one("SELECT id FROM cat_generos WHERE LOWER(nombre) = ?", (g_name.lower(),))
            if res_gen:
                gen_id = res_gen['id']
            else:
                try:
                    cursor_gen = await self.db.execute("INSERT INTO cat_generos (nombre) VALUES (?)", (g_name,))
                    gen_id = cursor_gen.lastrowid
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo crear género '{g_name}' en cat_generos (update): {e}")
            
        await self.db.execute(query, (
            empleado.rut,
            empleado.nombre,
            empleado.apellido_paterno,
            empleado.apellido_materno,
            empleado.cargo,
            empleado.cargo_id,
            empleado.area_id,
            empleado.compania,
            empleado.email,
            empleado.telefono,
            empleado.genero,
            gen_id,
            1 if empleado.activo else 0,
            empleado.fecha_nacimiento,
            empleado.fecha_ingreso,
            empleado.fecha_salida,
            empleado.tipo_contrato or "Indefinido",
            empleado.cant_contratos,
            empleado.decision_vencimiento,
            1 if empleado.es_manual else 0,
            1 if empleado.excluido_asistencia else 0,
            empleado.autorizado_llaves,
            empleado_id
        ))
        
        logger.info(f"Empleado actualizado: ID {empleado_id}")

        # Un cargo cambiado en la ficha o por la sincronización con BioAlba es una corrección: se corrige el tramo del
        # historial vigente hoy, sin partir el período (el cambio de labor desde una fecha tiene su propio botón)
        if empleado.cargo_id and await self.db.table_exists("historial_cargos"):
            await self.corregir_cargo_vigente(empleado_id, empleado.cargo_id)

        return await self.get_by_id(empleado_id)

    async def corregir_cargo_vigente(self, empleado_id: int, cargo_id: int) -> None:
        hoy = datetime.now().strftime('%Y-%m-%d')
        vigente = await self.db.fetch_one(
            "SELECT id, cargo_id FROM historial_cargos WHERE empleado_id = ? AND fecha_desde <= ? "
            "AND (fecha_hasta IS NULL OR fecha_hasta >= ?) ORDER BY fecha_desde DESC LIMIT 1", (empleado_id, hoy, hoy))
        if vigente and vigente['cargo_id'] != cargo_id:
            await self.db.execute("UPDATE historial_cargos SET cargo_id = ? WHERE id = ?", (cargo_id, vigente['id']))

    async def get_historial_cargos(self, empleado_id: int) -> List[Dict]:
        """El historial de cargos de una persona, del más nuevo al más antiguo (ficha, etapa B4b)."""
        filas = await self.db.fetch_all(
            "SELECT h.id, h.cargo_id, c.nombre AS cargo, h.fecha_desde, h.fecha_hasta, h.motivo, h.usuario "
            "FROM historial_cargos h LEFT JOIN cargos c ON c.id = h.cargo_id WHERE h.empleado_id = ? ORDER BY h.fecha_desde DESC",
            (empleado_id,))
        return [dict(f, fecha_desde=str(f["fecha_desde"])[:10], fecha_hasta=str(f["fecha_hasta"])[:10] if f["fecha_hasta"] else None)
                for f in filas]

    async def get_tramos_cargo(self, empleado_ids: List[int], desde: str, hasta: str) -> Dict[int, List[Dict]]:
        """Tramos del historial de cargos que tocan [desde, hasta], por persona y en orden."""
        if not empleado_ids or not await self.db.table_exists("historial_cargos"):
            return {}
        ph = ",".join("?" * len(empleado_ids))
        filas = await self.db.fetch_all(
            f"SELECT empleado_id, cargo_id, fecha_desde, fecha_hasta FROM historial_cargos WHERE empleado_id IN ({ph}) "
            "AND fecha_desde <= ? AND (fecha_hasta IS NULL OR fecha_hasta >= ?) ORDER BY empleado_id, fecha_desde",
            (*empleado_ids, hasta, desde))
        out: Dict[int, List[Dict]] = {}
        for f in filas:
            out.setdefault(f['empleado_id'], []).append(
                {"cargo_id": f['cargo_id'], "desde": str(f['fecha_desde'])[:10], "hasta": str(f['fecha_hasta'])[:10] if f['fecha_hasta'] else None})
        return out
    
    async def delete(self, empleado_id: int) -> bool:
        """Eliminar empleado (soft delete - marcar como inactivo)"""
        query = """
        UPDATE empleados SET 
            activo = 0,
            updated_at = datetime('now')
        WHERE id = ?
        """
        
        await self.db.execute(query, (empleado_id,))
        
        logger.info(f"Empleado desactivado: ID {empleado_id}")
        
        return True
    
    async def dias_en_tramos_cerrados(self, empleado_id: int) -> List[dict]:
        """Tramos cerrados en que la persona tiene días. Mismo criterio que check_fecha_cerrada: un cierre de toda la
        planta o de su área en esa fecha."""
        query = """
            SELECT cp.fecha_inicio, cp.fecha_fin, cp.area, COUNT(*) AS dias
            FROM asistencias a
            JOIN cierres_periodos cp ON a.fecha BETWEEN cp.fecha_inicio AND cp.fecha_fin
            WHERE a.empleado_id = ?
              AND (cp.area IS NULL OR cp.area = (
                    SELECT ar.nombre FROM historial_areas h
                    LEFT JOIN areas ar ON h.area_id = ar.id
                    WHERE h.empleado_id = a.empleado_id
                      AND a.fecha BETWEEN h.fecha_desde AND COALESCE(h.fecha_hasta, '2099-12-31')
                    LIMIT 1))
            GROUP BY cp.fecha_inicio, cp.fecha_fin, cp.area
            ORDER BY cp.fecha_fin DESC
        """
        return await self.db.fetch_all(query, (empleado_id,))

    async def _tablas_de_la_persona(self) -> List[tuple]:
        """Todas las tablas que guardan el id de una persona (empleado_id, empleado_receptor_id…). Se leen de la base:
        una tabla nueva queda incluida sin tocar este código."""
        bases = {r["table_name"] for r in await self.db.fetch_all(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'")}
        cols = await self.db.fetch_all(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() ORDER BY table_name, column_name")
        nombre = re.compile(r"^[a-z_][a-z0-9_]*$")
        return [(c["table_name"], c["column_name"]) for c in cols
                if c["table_name"] in bases and c["table_name"] != "empleados"
                and re.match(r"^empleado(_[a-z]+)?_id$", c["column_name"])
                and nombre.match(c["table_name"]) and nombre.match(c["column_name"])]

    async def hard_delete(self, empleado_id: int, usuario_id: Optional[int] = None, username: Optional[str] = None) -> Dict[str, int]:
        """Elimina a la persona y todo su historial, TODO O NADA (orden del dueño, 28-10-2026).

        Antes borraba 9 tablas una por una, sin transacción, y al final la ficha no se podía borrar por las tablas que
        no limpiaba (26-10-2026, Osvaldo Reyes: quedó sin días ni marcas y con la ficha vacía). Ahora:
        - se niega si la persona tiene días en un tramo cerrado (BorradoPermanenteBloqueado);
        - limpia todas las tablas con su id, en el orden que permitan las llaves entre ellas;
        - todo va en una transacción: si algo falla no se borra nada;
        - deja el registro en logs_auditoria dentro de la misma transacción.
        Devuelve cuántas filas se borraron de cada tabla."""
        cerrados = await self.dias_en_tramos_cerrados(empleado_id)
        if cerrados:
            raise BorradoPermanenteBloqueado(cerrados)
        emp = await self.db.fetch_one(
            "SELECT id, rut, nombre, apellido_paterno, apellido_materno FROM empleados WHERE id = ?", (empleado_id,))
        tablas = await self._tablas_de_la_persona()
        borradas: Dict[str, int] = {}
        logger.warning(f"⚠️ Borrado permanente del empleado ID {empleado_id}: {len(tablas)} tablas, todo o nada")
        async with self.db.transaction():
            pendientes = list(tablas)
            while pendientes:
                # Una tabla puede depender de otra por una llave foránea: las que fallan se reintentan después
                fallidas, ultimo_error = [], None
                for tabla, columna in pendientes:
                    try:
                        res = await self.db.execute(f"DELETE FROM {tabla} WHERE {columna} = ?", (empleado_id,))
                        n = int(getattr(res, "rowcount", 0) or 0)
                        if n:
                            borradas[tabla] = borradas.get(tabla, 0) + n
                    except Exception as e:
                        fallidas.append((tabla, columna))
                        ultimo_error = e
                if len(fallidas) == len(pendientes):
                    raise ultimo_error  # sin avance posible: la transacción se deshace entera
                pendientes = fallidas
            await self.db.execute("DELETE FROM empleados WHERE id = ?", (empleado_id,))
            nombre = " ".join(str((emp or {}).get(k) or "") for k in ("apellido_paterno", "apellido_materno", "nombre")).split()
            await self.db.execute(
                "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
                (usuario_id, username or "sistema", "ELIMINAR_EMPLEADO_PERMANENTE", "EMPLEADOS",
                 json.dumps({"empleado_id": empleado_id, "nombre": " ".join(nombre), "rut": (emp or {}).get("rut"),
                             "filas_borradas": borradas}, ensure_ascii=False)))
        logger.warning(f"✅ Empleado {empleado_id} eliminado para siempre: {borradas}")
        return borradas

    async def get_area_actual_para_permisos(self, empleado_id: int) -> Optional[dict]:
        """Nombre del área actual de un empleado (área_nombre), para revisar si el usuario puede verlo.
        A diferencia de las otras consultas de este archivo, no exige que el área esté validada: así la usaba
        Productos 4 al guardar una asignación (se movió de su router sin cambios, etapa 4 de la auditoría)."""
        return await self.db.fetch_one("""
            SELECT a.nombre as area_nombre
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1
            LEFT JOIN areas a ON ha.area_id = a.id
            WHERE e.id = ?
        """, (empleado_id,))

    async def get_stats_by_area(self, areas: Optional[List[str]] = None) -> List[dict]:
        """Obtener conteo de empleados por área con RLS.
        Incluye áreas con 0 empleados para que aparezcan en los selectores de la interfaz.
        """
        area_filter = ""
        params = []
        if areas and len(areas) > 0:
            placeholders = ",".join(["?"] * len(areas))
            area_filter = f" AND a.nombre IN ({placeholders})"
            params = areas

        # LEFT JOIN desde `areas` para incluir áreas con 0 empleados
        query = f"""
        SELECT a.nombre as area, COUNT(e.id) as count
        FROM areas a
        LEFT JOIN historial_areas ha ON ha.area_id = a.id AND ha.es_actual = 1 AND ha.validado = 1
        LEFT JOIN empleados e ON e.id = ha.empleado_id AND e.activo = 1
        WHERE 1=1 {area_filter}
        GROUP BY a.nombre
        ORDER BY count DESC, a.nombre ASC
        """

        results = await self.db.fetch_all(query, tuple(params) if params else None)
        return results

    async def get_birthdays(self, month: Optional[int] = None, area: Optional[str] = None, areas_permitidas: Optional[List[str]] = None) -> List[Empleado]:
        """Obtener empleados que cumplen años con RLS"""
        query = """SELECT e.*, COALESCE(a_hist.nombre, a_emp.nombre) as area FROM empleados e LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a_hist ON ha.area_id = a_hist.id
            LEFT JOIN areas a_emp ON e.area_id = a_emp.id WHERE e.activo = 1 AND e.fecha_nacimiento IS NOT NULL"""
        params = []
        
        if month:
            # En SQLite, substr(fecha_nacimiento, 6, 2) obtiene el mes de 'YYYY-MM-DD'
            query += " AND CAST(substr(fecha_nacimiento, 6, 2) AS INTEGER) = ?"
            params.append(month)
            
        if area:
            query += " AND COALESCE(a_hist.nombre, a_emp.nombre) = ?"
            params.append(area)
        elif areas_permitidas and len(areas_permitidas) > 0:
            placeholders = ",".join(["?"] * len(areas_permitidas))
            query += f" AND COALESCE(a_hist.nombre, a_emp.nombre) IN ({placeholders})"
            params.extend(areas_permitidas)
            
        query += " ORDER BY substr(fecha_nacimiento, 6, 5) ASC" # Ordenar por mes/día
        
        results = await self.db.fetch_all(query, tuple(params))
        return [self._dict_to_empleado(row) for row in results]

    async def get_unique_metadata(self, areas: Optional[List[str]] = None) -> dict:
        """Obtener listas únicas con RLS"""
        metadata = {}
        
        area_filter_clause = ""
        area_params = []
        if areas and len(areas) > 0:
            placeholders = ",".join(["?"] * len(areas))
            area_filter_clause = f" LEFT JOIN historial_areas ha ON empleados.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1 LEFT JOIN areas a_hist ON ha.area_id = a_hist.id LEFT JOIN areas a_emp ON empleados.area_id = a_emp.id WHERE COALESCE(a_hist.nombre, a_emp.nombre) IN ({placeholders})"
            area_params = areas

        # Cargos
        # If there's an area filter, apply it to cargos.
        # Note: The original query for cargos had `WHERE cargo IS NOT NULL AND cargo != ''`.
        # If `area_filter_clause` is present, we need to combine them with AND.
        cargos_query = f"SELECT DISTINCT cargo FROM empleados {area_filter_clause}"
        if area_filter_clause:
            cargos_query += " AND cargo IS NOT NULL AND cargo != '' ORDER BY cargo"
        else:
            cargos_query += " WHERE cargo IS NOT NULL AND cargo != '' ORDER BY cargo"
        metadata["cargos"] = [r["cargo"] for r in await self.db.fetch_all(cargos_query, tuple(area_params) if area_params else None)]
        
        # Áreas (Si tiene RLS, solo mostramos sus áreas)
        if areas:
            metadata["areas"] = areas
        else:
            metadata["areas"] = [r["nombre"] for r in await self.db.fetch_all("SELECT nombre FROM areas ORDER BY nombre")]
        
        # Áreas con empleados que tienen horarios asignados (para grilla de asistencia)
        metadata["areas_con_horario"] = await self.get_areas_con_horario(areas=areas)
        
        # Compañías
        # Apply area filter to companies as well.
        companias_query = f"SELECT DISTINCT compania FROM empleados {area_filter_clause}"
        if area_filter_clause:
            companias_query += " AND compania IS NOT NULL AND compania != '' ORDER BY compania"
        else:
            companias_query += " WHERE compania IS NOT NULL AND compania != '' ORDER BY compania"
        metadata["companias"] = [r["compania"] for r in await self.db.fetch_all(companias_query, tuple(area_params) if area_params else None)]
        
        return metadata

    async def get_areas_con_horario(
        self,
        areas: Optional[List[str]] = None,
        fecha_desde: Optional[str] = None,
        fecha_hasta: Optional[str] = None
    ) -> List[str]:
        """
        Obtiene las áreas que tienen empleados activos con turnos/horarios asignados.
        Si se proporcionan fechas (periodo), valida que el turno esté vigente en ese rango.
        Si no, toma asignaciones activas/recientes.
        """
        limit_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        
        query = """
            SELECT DISTINCT COALESCE(a_hist.nombre, a_emp.nombre) AS area
            FROM empleados e
            JOIN asignacion_turnos ast ON e.id = ast.empleado_id
            LEFT JOIN (
                SELECT empleado_id, MAX(area_id) as area_id
                FROM historial_areas
                WHERE es_actual = 1 AND validado = 1
                GROUP BY empleado_id
            ) ha ON e.id = ha.empleado_id
            LEFT JOIN areas a_hist ON ha.area_id = a_hist.id
            LEFT JOIN areas a_emp ON e.area_id = a_emp.id
            WHERE (e.activo = 1 OR (e.activo = 0 AND e.fecha_salida IS NOT NULL AND e.fecha_salida >= ?))
              AND (e.excluido_asistencia = 0 OR e.excluido_asistencia IS NULL)
        """
        params: list = [limit_date]

        if fecha_desde and fecha_hasta:
            query += " AND ast.fecha_inicio <= ? AND (ast.fecha_fin IS NULL OR ast.fecha_fin = '' OR ast.fecha_fin >= ?)"
            params.extend([fecha_hasta, fecha_desde])
        else:
            query += " AND (ast.fecha_fin IS NULL OR ast.fecha_fin = '' OR ast.fecha_fin >= ?)"
            params.append(limit_date)

        if areas and len(areas) > 0:
            placeholders = ",".join(["?"] * len(areas))
            query += f" AND COALESCE(a_hist.nombre, a_emp.nombre) IN ({placeholders})"
            params.extend(areas)

        query += """
            AND COALESCE(a_hist.nombre, a_emp.nombre) IS NOT NULL
            AND COALESCE(a_hist.nombre, a_emp.nombre) != ''
            ORDER BY area ASC
        """
        rows = await self.db.fetch_all(query, tuple(params))
        return [r["area"] for r in rows if r["area"]]

    async def get_lookup(self, area: Optional[str] = None, activo: Optional[bool] = None, areas_permitidas: Optional[List[str]] = None) -> List[dict]:
        """
        Obtener lista mínima de empleados (id, nombre_completo, rut) para dropdowns.
        Implementa RLS para limitar la lista a las áreas permitidas del supervisor.
        """
        query = """
            SELECT DISTINCT e.id, 
                   (e.apellido_paterno || ' ' || COALESCE(NULLIF(e.apellido_materno,''),'') || ' ' || e.nombre) as nombre_completo,
                   e.rut, COALESCE(a_hist.nombre, a_emp.nombre) as area, e.activo
            FROM empleados e
            LEFT JOIN (
                SELECT empleado_id, MAX(area_id) as area_id
                FROM historial_areas
                WHERE es_actual = 1 AND validado = 1
                GROUP BY empleado_id
            ) ha ON e.id = ha.empleado_id
            LEFT JOIN areas a_hist ON ha.area_id = a_hist.id
            LEFT JOIN areas a_emp ON e.area_id = a_emp.id
            WHERE 1=1
        """
        params = []
        
        # Security Data Scoping (RLS)
        if areas_permitidas is not None:
            if len(areas_permitidas) == 0:
                # Si se define RLS pero no tiene áreas, no ve a nadie
                return []
            
            # Si pide un área específica, debe estar en sus permitidas y la filtramos por ella sola
            if area:
                if area not in areas_permitidas:
                    return []
                query += " AND COALESCE(a_hist.nombre, a_emp.nombre) = ?"
                params.append(area)
            else:
                # Si no pide área, mostrar todas sus permitidas
                placeholders = ",".join(["?"] * len(areas_permitidas))
                query += f" AND COALESCE(a_hist.nombre, a_emp.nombre) IN ({placeholders})"
                params.extend(areas_permitidas)
        elif area:
            # Caso SuperUser: Filtra solo por el área solicitada
            query += " AND COALESCE(a_hist.nombre, a_emp.nombre) = ?"
            params.append(area)

        if activo is not None:
            query += " AND e.activo = ?"
            params.append(1 if activo else 0)
            
        query += " ORDER BY e.apellido_paterno ASC, e.apellido_materno ASC, e.nombre ASC"
        
        return await self.db.fetch_all(query, tuple(params))

    # ============================================
    # HISTORIAL DE ÁREAS (TEMPORAL VISIBILITY)
    # ============================================

    async def set_area_actual(self, empleado_id: int, area_id: int) -> None:
        """Anota el área actual en la ficha del empleado, sin tocar el historial (lo usa «confirmar cambio de área»,
        que ya cerró y validó el historial con la fecha efectiva)."""
        await self.db.execute(
            "UPDATE empleados SET area_id = ?, updated_at = datetime('now') WHERE id = ?",
            (area_id, empleado_id)
        )

    # ── Consultas que vivían en routers/asistencia.py (etapa 4 de la auditoría, sin cambios) ──

    async def get_rut(self, empleado_id: int) -> Optional[dict]:
        return await self.db.fetch_one("SELECT rut FROM empleados WHERE id = ?", [empleado_id])

    async def get_activos_del_turno(self, turno_id: int, area: Optional[str],
                                    areas_permitidas: Optional[List[str]]) -> List[dict]:
        """Empleados activos con una asignación vigente a ese turno (filtro de la grilla)."""
        extra_cond = ""
        params_emp: list = [turno_id]
        if area:
            extra_cond += " AND a.nombre = ?"
            params_emp.append(area)
        if areas_permitidas:
            ph = ",".join("?" * len(areas_permitidas))
            extra_cond += f" AND a.nombre IN ({ph})"
            params_emp.extend(areas_permitidas)
        return await self.db.fetch_all(f"""
            SELECT DISTINCT e.id,
                   (e.apellido_paterno || ' ' || COALESCE(NULLIF(e.apellido_materno,''),'') || ' ' || e.nombre) as nombre_completo,
                   e.rut, a.nombre as area, e.activo
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a ON ha.area_id = a.id
            INNER JOIN asignacion_turnos ast ON e.id = ast.empleado_id
            WHERE e.activo = 1
              AND ast.turno_id = ?
              AND (ast.fecha_fin IS NULL OR ast.fecha_fin >= date('now'))
              {extra_cond}
            ORDER BY e.apellido_paterno ASC, e.apellido_materno ASC, e.nombre ASC
        """, tuple(params_emp))

    async def get_activos_sin_turno(self, areas_permitidas: Optional[List[str]]) -> List[dict]:
        """Empleados activos sin turno vigente (aviso en la pantalla). `areas_permitidas` None o vacía = todas."""
        area_filter = ""
        params = []
        if areas_permitidas:
            placeholders = ",".join("?" for _ in areas_permitidas)
            area_filter = f" AND a.nombre IN ({placeholders})"
            params = areas_permitidas
        query = f"""
            SELECT e.id, e.nombre, e.apellido_paterno, e.apellido_materno, a.nombre as area
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a ON ha.area_id = a.id
            WHERE e.activo = 1
              {area_filter}
              AND e.id NOT IN (
                  SELECT DISTINCT empleado_id 
                  FROM asignacion_turnos 
                  WHERE fecha_fin IS NULL OR fecha_fin >= date('now')
              )
            ORDER BY e.apellido_paterno, e.apellido_materno, e.nombre
        """
        return await self.db.fetch_all(query, params)

    async def contar_sin_turno_en_area(self, area: str, fecha_inicio: str, fecha_fin: str) -> Optional[dict]:
        """Cuántos empleados estuvieron en el área en el rango sin turno asignado en ese rango."""
        query = """
            SELECT COUNT(DISTINCT e.id) as count
            FROM empleados e
            JOIN historial_areas h ON e.id = h.empleado_id
            JOIN areas ar_d ON h.area_id = ar_d.id
            WHERE ar_d.nombre = ?
              AND h.fecha_desde <= ?
              AND (h.fecha_hasta IS NULL OR h.fecha_hasta >= ?)
              AND h.validado = 1
              AND e.id NOT IN (
                  SELECT DISTINCT empleado_id 
                  FROM asignacion_turnos 
                  WHERE (fecha_inicio <= ?) AND (fecha_fin IS NULL OR fecha_fin >= ?)
              )
        """
        return await self.db.fetch_one(query, (area, fecha_fin, fecha_inicio, fecha_fin, fecha_inicio))

    async def get_generos(self) -> List[dict]:
        """El catálogo de géneros (la tabla cat_generos se crea en create_table de este archivo)."""
        return await self.db.fetch_all("SELECT id, nombre FROM cat_generos ORDER BY nombre ASC")

    async def get_historial_area_by_id(self, historial_id: int) -> Optional[dict]:
        """Un registro del historial de áreas por su id, tal como está en la tabla (SELECT *)."""
        return await self.db.fetch_one(
            "SELECT * FROM historial_areas WHERE id = ?",
            (historial_id,)
        )

    async def get_historial_areas(self, empleado_id: int) -> List[dict]:
        """Obtener el historial completo de áreas de un empleado"""
        query = """
            SELECT h.id, h.empleado_id, a.nombre as area, h.fecha_desde, h.fecha_hasta, h.es_actual, h.validado, h.created_at
            FROM historial_areas h
            LEFT JOIN areas a ON h.area_id = a.id
            WHERE h.empleado_id = ?
            ORDER BY h.fecha_desde DESC, h.id DESC
        """
        return await self.db.fetch_all(query, (empleado_id,))

    async def add_historial_area(self, empleado_id: int, area_id: int, fecha_desde: str, fecha_hasta: Optional[str] = None, es_actual: bool = True, validado: bool = True) -> int:
        """Añadir un nuevo registro de área al historial con protección de idempotencia"""
        if es_actual and validado:
            # 1. Si ya existe exactamente este registro activo y validado para la misma área, devolver su ID (evitar duplicados)
            existente = await self.db.fetch_one(
                "SELECT id FROM historial_areas WHERE empleado_id = ? AND area_id = ? AND es_actual = 1 AND validado = 1",
                (empleado_id, area_id)
            )
            if existente:
                return existente["id"]

            # 2. Desmarcar registros previos para garantizar que solo exista 1 registro actual
            await self.db.execute(
                "UPDATE historial_areas SET es_actual = 0 WHERE empleado_id = ? AND es_actual = 1",
                (empleado_id,)
            )

        query = """
            INSERT INTO historial_areas (empleado_id, area_id, fecha_desde, fecha_hasta, es_actual, validado)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        cursor = await self.db.execute(query, (
            empleado_id, area_id, fecha_desde, fecha_hasta, 
            1 if es_actual else 0, 
            1 if validado else 0
        ))
        return cursor.lastrowid

    async def update_historial_area(self, record_id: int, **kwargs) -> bool:
        """Actualizar un registro del historial (p.ej. para cerrar fechas o validar)"""
        if not kwargs:
            return False
            
        sets = []
        params = []
        for key, val in kwargs.items():
            sets.append(f"{key} = ?")
            params.append(val if not isinstance(val, bool) else (1 if val else 0))
            
        query = f"UPDATE historial_areas SET {', '.join(sets)} WHERE id = ?"
        params.append(record_id)
        
        await self.db.execute(query, tuple(params))
        return True

    def _dict_to_empleado(self, data: dict) -> Empleado:
        """Convertir diccionario de DB a modelo Empleado"""
        return Empleado(
            id=data["id"],
            rut=data["rut"],
            nombre=data["nombre"],
            apellido_paterno=data["apellido_paterno"],
            apellido_materno=data["apellido_materno"],
            cargo=data.get("cargo"),
            cargo_id=data.get("cargo_id"),
            area=data.get("area"),
            area_id=data.get("area_id"),
            compania=data.get("compania"),
            email=data.get("email"),
            telefono=data.get("telefono"),
            genero=data.get("genero"),
            genero_id=data.get("genero_id"),
            activo=bool(data.get("activo", 1)),
            fecha_nacimiento=data.get("fecha_nacimiento"),
            fecha_ingreso=data.get("fecha_ingreso"),
            fecha_salida=data.get("fecha_salida"),
            tipo_contrato=data.get("tipo_contrato", "Indefinido"),
            cant_contratos=data.get("cant_contratos", 1),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            decision_vencimiento=data.get("decision_vencimiento"),
            fecha_asignacion_turno=data.get("fecha_asignacion_turno"),
            es_manual=bool(data.get("es_manual", 0)),
            excluido_asistencia=bool(data.get("excluido_asistencia", 0)),
            autorizado_llaves=int(data.get("autorizado_llaves", 0))
        )

    async def get_nombres_areas_validadas_entre(self, empleado_id: int, fecha_inicio: str, fecha_fin: str) -> List[Dict]:
        """Nombres de las áreas validadas en que estuvo el empleado en algún momento del rango."""
        q_areas = """
        SELECT DISTINCT a.nombre as area_nombre
        FROM historial_areas ha
        JOIN areas a ON ha.area_id = a.id
        WHERE ha.empleado_id = ? AND ha.validado = 1
          AND ha.fecha_desde <= ? AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR ha.fecha_hasta >= ?)
    """
        return await self.db.fetch_all(q_areas, (empleado_id, fecha_fin, fecha_inicio))

    async def get_rut_y_nombre_por_ids(self, ids_empleados: List[int]) -> List[Dict]:
        """RUT, nombre y apellido paterno de varios empleados a la vez."""
        placeholders = ",".join("?" * len(ids_empleados))
        return await self.db.fetch_all(
            f"SELECT id, rut, nombre, apellido_paterno FROM empleados WHERE id IN ({placeholders})",
            ids_empleados
        )

    async def get_nombres_por_ids(self, ids: List[int]) -> List[Dict]:
        """Nombre y apellidos de varios empleados a la vez."""
        marcas = ", ".join("?" for _ in ids)
        return await self.db.fetch_all(f"SELECT id, nombre, apellido_paterno, apellido_materno FROM empleados WHERE id IN ({marcas})", tuple(ids))

    async def get_personas_de_su_area(self, empleado_id: int) -> List[Dict]:
        """Las personas del área del empleado (él incluido), con su nombre completo y si están activas."""
        return await self.db.fetch_all(
            """SELECT e.id, e.activo, (e.apellido_paterno || ' ' || COALESCE(NULLIF(e.apellido_materno,''),'') || ' ' || e.nombre) AS nombre_completo
           FROM empleados e WHERE e.area_id = (SELECT area_id FROM empleados WHERE id = ?)""", (empleado_id,))

    async def get_choferes_logistica_tradicional(self) -> List[Dict]:
        """Las personas con cargo CHOFER del área Logística Tradicional."""
        return await self.db.fetch_all(
            """SELECT e.id, e.rut, e.nombre, e.apellido_paterno, e.apellido_materno, e.activo,
                  (e.apellido_paterno || ' ' || COALESCE(NULLIF(e.apellido_materno,''),'') || ' ' || e.nombre) AS nombre_completo
           FROM empleados e JOIN areas a ON a.id = e.area_id
           WHERE UPPER(TRIM(e.cargo)) = 'CHOFER'
             AND UPPER(TRIM(a.nombre)) LIKE 'LOG_STICA TRADICIONAL'""")
