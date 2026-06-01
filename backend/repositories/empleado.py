"""
Repository - Empleado
Capa de acceso a datos para Empleados
"""

from typing import List, Optional, Dict
from datetime import datetime
from loguru import logger

from backend.core.database import Database
from backend.models.empleado import Empleado


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
        # Migración Inteligente: 1 sola llamada get_column_names() en vez de N column_exists() individuales
        try:
            cols_empleados = set(await self.db.get_column_names("empleados"))
            new_columns = {
                "fecha_nacimiento": "TEXT",
                "cant_contratos": "INTEGER DEFAULT 1",
                "genero": "TEXT",
                "genero_id": "INTEGER",
                "decision_vencimiento": "TEXT",
                "cargo_id": "INTEGER REFERENCES cargos(id)"
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
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                """)
                logger.info("✨ Tabla cargos creada (migración)")
            
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

            
        except Exception as e:
            logger.warning(f"⚠️ Error en migración de esquema de empleados: {e}")
        
        logger.info("✅ Tabla empleados verificada")
    
    async def create(self, empleado: Empleado) -> Empleado:
        """Crear un nuevo empleado"""
        query = """
        INSERT INTO empleados (
            rut, nombre, apellido_paterno, apellido_materno,
            cargo, cargo_id, area_id, compania, email, telefono, genero, genero_id, activo,
            fecha_nacimiento, fecha_ingreso, fecha_salida, tipo_contrato, cant_contratos, decision_vencimiento
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            empleado.decision_vencimiento
        ))
        
        empleado.id = cursor.lastrowid
        
        logger.info(f"Empleado creado: {empleado.nombre_completo} (ID: {empleado.id})")
        
        # Opcional: Recargar de DB para tener los defaults aplicados (created_at, etc)
        return await self.get_by_id(empleado.id)
    
    async def get_by_id(self, empleado_id: int) -> Optional[Empleado]:
        """Obtener empleado por ID (con info de turno asignado)"""
        query = """
            SELECT e.*, a.nombre as area, cg.nombre as genero_nombre, MAX(at.fecha_inicio) as fecha_asignacion_turno
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a ON ha.area_id = a.id
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
        """Obtener empleado por RUT"""
        query = """
            SELECT e.*, a.nombre as area, cg.nombre as genero_nombre
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a ON ha.area_id = a.id
            LEFT JOIN cat_generos cg ON e.genero_id = cg.id
            WHERE e.rut = ?
        """
        
        result = await self.db.fetch_one(query, (rut,))
        
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
            SELECT e.*, a.nombre as area, cg.nombre as genero_nombre, MAX(at.fecha_inicio) as fecha_asignacion_turno
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a ON ha.area_id = a.id
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
            conditions.append(f"a.nombre IN ({placeholders})")
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
            SELECT e.*, a.nombre as area, cg.nombre as genero_nombre, MAX(at.fecha_inicio) as fecha_asignacion_turno
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a ON ha.area_id = a.id
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
            query += f" AND a.nombre IN ({placeholders})"
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
            query += " AND a.nombre = ?"
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
            LEFT JOIN areas a ON ha.area_id = a.id"""
            conditions.append(f"a.nombre IN ({placeholders})")
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

    async def get_ruts_by_areas(self, areas: List[str]) -> List[str]:
        """Obtener RUTs de empleados que pertenecen a las áreas dadas (Área Actual)"""
        if not areas:
            return []
            
        # Crear placeholders para la query IN (?, ?, ?)
        placeholders = ",".join(["?"] * len(areas))
        query = f"""SELECT e.rut FROM empleados e LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a ON ha.area_id = a.id WHERE a.nombre IN ({placeholders})"""
        
        results = await self.db.fetch_all(query, tuple(areas))
        return [row['rut'] for row in results]

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
            LEFT JOIN historial_areas h ON e.id = h.empleado_id
            LEFT JOIN areas a_hist ON h.area_id = a_hist.id
            WHERE a_actual.nombre IN ({placeholders})
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
            area_filter = f" AND a.nombre IN ({placeholders})"
            params.extend(areas)
            
        params.extend([future_date, today])

        query = f"""
            SELECT e.*, a.nombre as area 
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a ON ha.area_id = a.id 
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
            area_filter = f" AND a.nombre IN ({placeholders})"
            params.extend(areas)

        query = f"""
            SELECT e.*, a.nombre as area
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a ON ha.area_id = a.id
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
            LEFT JOIN areas a ON ha.area_id = a.id WHERE 1=1"""
        params = []
        
        # Security Data Scoping
        if areas_permitidas is not None and len(areas_permitidas) > 0:
            if area and area not in areas_permitidas:
                return 0
            placeholders = ",".join(["?"] * len(areas_permitidas))
            query += f" AND a.nombre IN ({placeholders})"
            params.extend(areas_permitidas)
        
        if q:
            query += """ AND (
                nombre LIKE ? OR 
                apellido_paterno LIKE ? OR 
                apellido_materno LIKE ? OR
                rut LIKE ? OR
                cargo LIKE ?
            )"""
            search_pattern = f"%{q}%"
            params.extend([search_pattern] * 5)
        
        if area:
            query += " AND a.nombre = ?"
            params.append(area)
        
        if compania:
            query += " AND compania = ?"
            params.append(compania)
        
        if activo is not None:
            query += " AND activo = ?"
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
            empleado_id
        ))
        
        logger.info(f"Empleado actualizado: ID {empleado_id}")
        
        return await self.get_by_id(empleado_id)
    
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
    
    async def hard_delete(self, empleado_id: int) -> bool:
        """Eliminar empleado permanentemente y todo su rastro en el sistema (Efecto Dominó)"""
        try:
            # Iniciar borrado en cascada
            logger.warning(f"⚠️ Iniciando Hard Delete (Efecto Dominó) para el empleado ID: {empleado_id}")
            
            # Borrar de tablas hijas
            await self.db.execute("DELETE FROM asignacion_turnos WHERE empleado_id = ?", (empleado_id,))
            # [ELIMINADO] DELETE FROM bolsa_horas_resumen — tabla eliminada (fantasma, causa corrupción)
            await self.db.execute("DELETE FROM asistencias WHERE empleado_id = ?", (empleado_id,))
            await self.db.execute("DELETE FROM logs_raw WHERE empleado_id = ?", (empleado_id,))
            await self.db.execute("DELETE FROM bono_asignaciones WHERE empleado_id = ?", (empleado_id,))
            await self.db.execute("DELETE FROM justificaciones WHERE empleado_id = ?", (empleado_id,))
            await self.db.execute("DELETE FROM historial_areas WHERE empleado_id = ?", (empleado_id,))
            await self.db.execute("DELETE FROM periodos_empleo WHERE empleado_id = ?", (empleado_id,))
            await self.db.execute("DELETE FROM horas_extras WHERE empleado_id = ?", (empleado_id,))
            await self.db.execute("DELETE FROM jornadas_especiales WHERE empleado_id = ?", (empleado_id,))
            
            # Finalmente, borrar al empleado
            query = "DELETE FROM empleados WHERE id = ?"
            await self.db.execute(query, (empleado_id,))
            
            logger.warning(f"✅ Empleado eliminado permanentemente junto a todo su historial: ID {empleado_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error en Hard Delete para empleado {empleado_id}: {e}")
            raise
    
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
        query = """SELECT e.*, a.nombre as area FROM empleados e LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a ON ha.area_id = a.id WHERE e.activo = 1 AND e.fecha_nacimiento IS NOT NULL"""
        params = []
        
        if month:
            # En SQLite, substr(fecha_nacimiento, 6, 2) obtiene el mes de 'YYYY-MM-DD'
            query += " AND CAST(substr(fecha_nacimiento, 6, 2) AS INTEGER) = ?"
            params.append(month)
            
        if area:
            query += " AND a.nombre = ?"
            params.append(area)
        elif areas_permitidas and len(areas_permitidas) > 0:
            placeholders = ",".join(["?"] * len(areas_permitidas))
            query += f" AND a.nombre IN ({placeholders})"
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
            area_filter_clause = f" LEFT JOIN historial_areas ha ON empleados.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1 LEFT JOIN areas a ON ha.area_id = a.id WHERE a.nombre IN ({placeholders})"
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
        
        # Compañías
        # Apply area filter to companies as well.
        companias_query = f"SELECT DISTINCT compania FROM empleados {area_filter_clause}"
        if area_filter_clause:
            companias_query += " AND compania IS NOT NULL AND compania != '' ORDER BY compania"
        else:
            companias_query += " WHERE compania IS NOT NULL AND compania != '' ORDER BY compania"
        metadata["companias"] = [r["compania"] for r in await self.db.fetch_all(companias_query, tuple(area_params) if area_params else None)]
        
        return metadata

    async def get_lookup(self, area: Optional[str] = None, activo: Optional[bool] = None, areas_permitidas: Optional[List[str]] = None) -> List[dict]:
        """
        Obtener lista mínima de empleados (id, nombre_completo, rut) para dropdowns.
        Implementa RLS para limitar la lista a las áreas permitidas del supervisor.
        """
        query = """
            SELECT e.id, 
                   (e.apellido_paterno || ' ' || COALESCE(NULLIF(e.apellido_materno,''),'') || ' ' || e.nombre) as nombre_completo,
                   e.rut, a.nombre as area, e.activo
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a ON ha.area_id = a.id
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
                query += " AND a.nombre = ?"
                params.append(area)
            else:
                # Si no pide área, mostrar todas sus permitidas
                placeholders = ",".join(["?"] * len(areas_permitidas))
                query += f" AND a.nombre IN ({placeholders})"
                params.extend(areas_permitidas)
        elif area:
            # Caso SuperUser: Filtra solo por el área solicitada
            query += " AND a.nombre = ?"
            params.append(area)

        if activo is not None:
            query += " AND e.activo = ?"
            params.append(1 if activo else 0)
            
        query += " ORDER BY e.apellido_paterno ASC, e.apellido_materno ASC, e.nombre ASC"
        
        return await self.db.fetch_all(query, tuple(params))

    # ============================================
    # HISTORIAL DE ÁREAS (TEMPORAL VISIBILITY)
    # ============================================

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
        """Añadir un nuevo registro de área al historial"""
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

    async def get_area_at_date(self, empleado_id: int, fecha: str) -> Optional[str]:
        """Obtener el área del empleado en una fecha específica"""
        query = """
            SELECT a.nombre as area 
            FROM historial_areas h
            LEFT JOIN areas a ON h.area_id = a.id
            WHERE h.empleado_id = ? 
              AND h.fecha_desde <= ? 
              AND (h.fecha_hasta IS NULL OR h.fecha_hasta >= ?)
            ORDER BY h.es_actual DESC, h.fecha_desde DESC
            LIMIT 1
        """
        result = await self.db.fetch_one(query, (empleado_id, fecha, fecha))
        return result["area"] if result else None

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
            fecha_asignacion_turno=data.get("fecha_asignacion_turno")
        )
