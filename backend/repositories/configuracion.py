from typing import List, Optional, Dict, Any
from loguru import logger
from backend.core.database import Database
from backend.schemas.bono import BonoCreate, BonoReglaCreate, BonoAsignacionCreate
from backend.schemas.justificacion import JustificacionTipoCreate, JustificacionCreate
import json

class ConfiguracionRepository:
    def __init__(self, db: Database):
        self.db = db

    async def init_tables(self):
        """Inicializar tablas de Bonos y Justificaciones"""
        
        # 1. Tabla Bonos (Maestro)
        if not await self.db.table_exists("bonos"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS bonos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    descripcion TEXT,
                    activo INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        # 2. Tabla Reglas de Bonos (Versión/Logica)
        if not await self.db.table_exists("bono_reglas"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS bono_reglas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bono_id INTEGER NOT NULL,
                    monto REAL NOT NULL,
                    asistencia_minima REAL DEFAULT 100.0,
                    tipo_contrato TEXT,
                    cargo_requerido TEXT,
                    cargos_excluidos TEXT, -- Lista separada por comas de cargos a excluir
                    es_proporcional INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 1,
                    fecha_inicio TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bono_id) REFERENCES bonos (id) ON DELETE CASCADE
                )
            """)

        # 3. Tabla Asignación de Bonos a Empleados
        if not await self.db.table_exists("bono_asignaciones"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS bono_asignaciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    bono_id INTEGER NOT NULL,
                    fecha_desde TEXT NOT NULL,
                    fecha_hasta TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (empleado_id) REFERENCES empleados (id),
                    FOREIGN KEY (bono_id) REFERENCES bonos (id)
                )
            """)

        # 4. Tabla Tipos de Justificación (Maestro)
        if not await self.db.table_exists("justificacion_tipos"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS justificacion_tipos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    descripcion TEXT,
                    con_goce_sueldo INTEGER DEFAULT 1,
                    dias_habiles INTEGER DEFAULT 1, -- DEPRECATED: Usar dias_corridos (inverso) o mantener por compatibilidad
                    pagador TEXT DEFAULT 'Empleador',
                    dias_defecto INTEGER,
                    
                    -- Reglas Avanzadas
                    min_dias INTEGER DEFAULT 1,
                    max_dias INTEGER, -- NULL = Sin límite
                    frecuencia_anual INTEGER, -- NULL = Sin límite
                    dias_corridos INTEGER DEFAULT 0, -- 0: Hábiles (L-V), 1: Corridos (L-D + Festivos)
                    sobreescribe_feriados INTEGER DEFAULT 0, -- 1: Si cae feriado, es Justificación. 0: Es Feriado.
                    descuenta_remuneracion INTEGER DEFAULT 0, -- 1: Sin goce (ej: Permiso sin goce)
                    es_horas_sindicales INTEGER DEFAULT 0, -- 1: Manejo especial por horas
    
                    activo INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        # 4.1 Tabla Maestro de Pagadores [NEW]
        if not await self.db.table_exists("cat_pagadores"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS cat_pagadores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL UNIQUE,
                    activo INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
            # Semilla inicial de Pagadores Legales (Batch ⚡)
            pagadores_legales = [
                ("Empleador", 1),
                ("Entidad de Salud (FONASA/ISAPRE)", 1),
                ("Mutual de Seguridad / ISL", 1),
                ("Sin Goce de Sueldo", 1)
            ]
            try:
                await self.db.executemany(
                    "INSERT OR IGNORE INTO cat_pagadores (nombre, activo) VALUES (?, ?)",
                    pagadores_legales
                )
            except Exception as e_p:
                logger.debug(f"Semilla pagadores: {e_p}")

        # 5. Tabla Justificaciones (Registros)
        if not await self.db.table_exists("justificaciones"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS justificaciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    tipo_id INTEGER NOT NULL,
                    fecha_inicio TEXT NOT NULL,
                    fecha_fin TEXT NOT NULL,
                    observaciones TEXT,
                    documento_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (empleado_id) REFERENCES empleados (id),
                    FOREIGN KEY (tipo_id) REFERENCES justificacion_tipos (id)
                )
            """)
        
        # ⚡ Índice compuesto para justificaciones (acelera cruce fecha↔empleado en el motor)
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_justif_emp_fechas ON justificaciones(empleado_id, fecha_inicio, fecha_fin)")

        # --- MIGRACIONES INTELIGENTES ---
        try:
            get_cols = getattr(self.db, 'get_column_names', None)
            if get_cols:
                # 1. Verificar justificacion_tipos
                cols_tipos = await get_cols("justificacion_tipos")
                new_cols_tipos = {
                    "dias_defecto": "INTEGER",
                    "min_dias": "INTEGER DEFAULT 1",
                    "max_dias": "INTEGER",
                    "frecuencia_anual": "INTEGER",
                    "dias_corridos": "INTEGER DEFAULT 0",
                    "sobreescribe_feriados": "INTEGER DEFAULT 0",
                    "descuenta_remuneracion": "INTEGER DEFAULT 0",
                    "es_horas_sindicales": "INTEGER DEFAULT 0",
                    "es_por_horas": "INTEGER DEFAULT 0",
                    "genera_deuda_horaria": "INTEGER DEFAULT 0",
                    "nomenclatura": "TEXT"
                }
                for col_name, col_def in new_cols_tipos.items():
                    if col_name not in cols_tipos:
                        await self.db.execute(f"ALTER TABLE justificacion_tipos ADD COLUMN {col_name} {col_def}")
                        logger.info(f"✨ Migración: Columna '{col_name}' agregada a justificacion_tipos")

                # 2. Verificar justificaciones
                cols_just = await get_cols("justificaciones")
                if "hora_inicio" not in cols_just:
                    await self.db.execute("ALTER TABLE justificaciones ADD COLUMN hora_inicio TEXT")
                    logger.info("✨ Migración: Columna 'hora_inicio' agregada a justificaciones")
                if "hora_fin" not in cols_just:
                    await self.db.execute("ALTER TABLE justificaciones ADD COLUMN hora_fin TEXT")
                    logger.info("✨ Migración: Columna 'hora_fin' agregada a justificaciones")

                # 3. La tabla 'asistencias' se gestiona en TurnoRepository para evitar colisiones ⚡


                # 4. Verificar bono_reglas
                cols_bono = await get_cols("bono_reglas")
                if "cargos_excluidos" not in cols_bono:
                    await self.db.execute("ALTER TABLE bono_reglas ADD COLUMN cargos_excluidos TEXT")
                    logger.info("✨ Migración: Columna 'cargos_excluidos' agregada a bono_reglas")

                # 5. Verificar cierres_periodos
                cols_cierres = await self.db.get_column_names("cierres_periodos")
                if "area" not in cols_cierres:
                    await self.db.execute("ALTER TABLE cierres_periodos ADD COLUMN area TEXT")
                    logger.info("✨ Migración: Columna 'area' agregada a cierres_periodos")
                if "turno_id" not in cols_cierres:
                    await self.db.execute("ALTER TABLE cierres_periodos ADD COLUMN turno_id INTEGER")
                    logger.info("✨ Migración: Columna 'turno_id' agregada a cierres_periodos")

        except Exception as e:
            logger.warning(f"⚠️ Error en migraciones de configuración: {e}")
        # 6. Tabla Ajustes Globales [NEW]
        if not await self.db.table_exists("ajustes"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS ajustes (
                    clave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL,
                    descripcion TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
            # Inicializar ajustes por defecto (Batch ⚡)
            ajustes_defecto = [
                ("vencimiento_dias_alerta", "45", "Días de anticipación para alertas de vencimiento"),
                ("dias_alerta_bloqueante", "5", "Días de anticipación para bloqueo de inicio"),
                ("limite_contratos_temporales", "2", "Máximo de contratos temporales antes de alertar paso a planta"),
                ("dia_cierre_rrhh", "25", "Día del mes por defecto para cierre de periodo RRHH")
            ]
            try:
                await self.db.executemany(
                    "INSERT OR IGNORE INTO ajustes (clave, valor, descripcion) VALUES (?, ?, ?)",
                    ajustes_defecto
                )
            except Exception as e_a:
                logger.debug(f"Semilla ajustes: {e_a}")

        # 7. Tabla Historial de Cierres de Periodo (RRHH) [NEW]
        if not await self.db.table_exists("cierres_periodos"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS cierres_periodos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_inicio DATE NOT NULL,
                    fecha_fin DATE NOT NULL,
                    usuario_id INTEGER,
                    username TEXT,
                    tipo_cierre TEXT DEFAULT 'RRHH',
                    comentarios TEXT,
                    area TEXT,
                    turno_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("✨ Tabla 'cierres_periodos' creada exitosamente")

        # Asegurar semilla de dia_cierre_rrhh si la tabla ya existía pero el valor no
        await self.db.execute("""
            INSERT OR IGNORE INTO ajustes (clave, valor, descripcion)
            VALUES ('dia_cierre_rrhh', '25', 'Día del mes por defecto para cierre de periodo RRHH')
        """)

        # 8. Tabla de Periodos de Empleo (Multi-Contrato) [NEW V15]
        if not await self.db.table_exists("periodos_empleo"):
            logger.info("🛠️ Creando tabla 'periodos_empleo' para gestión de reincorporaciones...")
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS periodos_empleo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    fecha_inicio DATE NOT NULL,
                    fecha_fin DATE,
                    tipo_contrato TEXT DEFAULT 'Indefinido',
                    es_activo BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (empleado_id) REFERENCES empleados(id) ON DELETE CASCADE
                )
            """)
            
            # --- MIGRACIÓN INICIAL: "Promocionar" contratos actuales ---
            try:
                logger.info("🚚 Iniciando migración de contratos actuales a 'periodos_empleo'...")
                # Insertamos un periodo para cada empleado existente usando sus fechas actuales
                await self.db.execute("""
                    INSERT INTO periodos_empleo (empleado_id, fecha_inicio, fecha_fin, tipo_contrato, es_activo)
                    SELECT id, 
                           COALESCE(fecha_ingreso, '2020-01-01'), 
                           fecha_salida, 
                           COALESCE(tipo_contrato, 'Indefinido'), 
                           activo
                    FROM empleados
                """)
                count_res = await self.db.fetch_one("SELECT COUNT(*) as count FROM periodos_empleo")
                logger.success(f"✅ Migración exitosa: {count_res['count']} periodos inicializados.")
            except Exception as e_mig:
                logger.error(f"❌ Falló migración inicial de periodos: {e_mig}")

        logger.info("✅ Tablas de configuración, ajustes y periodos inicializadas")

    # --- BONOS ---
    async def create_bono(self, bono: BonoCreate) -> int:
        try:
            logger.info("Iniciando creación de bono...")
            res = await self.db.execute(
                "INSERT INTO bonos (nombre, descripcion, activo) VALUES (?, ?, ?)",
                (bono.nombre, bono.descripcion, 1 if bono.activo else 0)
            )
            bono_id = res.lastrowid
            logger.info(f"Bono Header creado con ID: {bono_id}")

            if not bono_id or int(bono_id) <= 0:
                logger.error(f"FATAL: ID de bono inválido obtenido: {bono_id}")
                raise ValueError("No se pudo obtener un ID válido para el bono")
            
            try:
                for regla in bono.reglas:
                    logger.debug(f"Insertando regla para bono {bono_id}: {regla}")
                    await self.create_regla_bono(bono_id, regla)
                logger.info(f"Reglas insertadas correctamente para bono {bono_id}")
                return bono_id
            except Exception as e_rules:
                # Rollback manual: Eliminar el bono huérfano si fallan las reglas
                logger.error(f"Error creando reglas para bono {bono_id}: {e_rules} - Realizando Rollback")
                await self.db.execute("DELETE FROM bonos WHERE id = ?", (bono_id,))
                raise e_rules

        except Exception as e:
            logger.error(f"Error creando bono: {e}")
            raise

    async def create_regla_bono(self, bono_id: int, regla: BonoReglaCreate) -> int:
        query = """
            INSERT INTO bono_reglas (
                bono_id, monto, asistencia_minima, tipo_contrato,
                cargo_requerido, cargos_excluidos, es_proporcional,
                version, fecha_inicio
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            bono_id, regla.monto, regla.asistencia_minima, regla.tipo_contrato,
            regla.cargo_requerido, regla.cargos_excluidos, 1 if regla.es_proporcional else 0,
            regla.version, str(regla.fecha_inicio)
        )
        try:
            res = await self.db.execute(query, params)
            return res.lastrowid
        except Exception as e:
            logger.error(f"Falló inserción de regla: ID={bono_id}, Regla={regla} - Error: {e}")
            raise

    async def delete_bono(self, bono_id: int) -> bool:
        try:
            # Por ON DELETE CASCADE las reglas deberían borrarse solas si la DB lo soporta, 
            # pero lo hacemos explícito por seguridad en SQLite si PRAGMA foreign_keys no está activo
            await self.db.execute("DELETE FROM bono_reglas WHERE bono_id = ?", (bono_id,))
            res = await self.db.execute("DELETE FROM bonos WHERE id = ?", (bono_id,))
            return res.rowcount > 0
        except Exception as e:
            logger.error(f"Error eliminando bono: {e}")
            raise

    async def update_bono(self, bono_id: int, bono: BonoCreate) -> bool:
        try:
            # 1. Actualizar datos maestros
            await self.db.execute(
                "UPDATE bonos SET nombre = ?, descripcion = ?, activo = ? WHERE id = ?",
                (bono.nombre, bono.descripcion, 1 if bono.activo else 0, bono_id)
            )
            
            # 2. Reemplazar reglas (borrar anteriores e insertar nuevas)
            await self.db.execute("DELETE FROM bono_reglas WHERE bono_id = ?", (bono_id,))
            for regla in bono.reglas:
                await self.create_regla_bono(bono_id, regla)
                
            return True
        except Exception as e:
            logger.error(f"Error actualizando bono: {e}")
            raise

    async def get_all_bonos(self) -> List[Dict]:
        """Obtener todos los bonos con sus reglas"""
        try:
            # 1. Obtener Bonos
            query = "SELECT * FROM bonos ORDER BY nombre"
            bonos = await self.db.fetch_all(query)
            
            # 2. Obtener Reglas para cada bono
            result = []
            for b in bonos:
                bono_dict = dict(b)
                # Convertir activo a bool si es necesario, aunque SQLite devuelve 0/1
                bono_dict['activo'] = bool(b['activo'])
                
                query_reglas = "SELECT * FROM bono_reglas WHERE bono_id = ?"
                reglas = await self.db.fetch_all(query_reglas, (b['id'],))
                
                # Formatear reglas
                reglas_fmt = []
                for r in reglas:
                    r_dict = dict(r)
                    r_dict['es_proporcional'] = bool(r['es_proporcional'])
                    reglas_fmt.append(r_dict)
                    
                bono_dict['reglas'] = reglas_fmt
                result.append(bono_dict)
                
            return result
        except Exception as e:
            logger.error(f"Error getting all bonos: {e}")
            return []

    # --- JUSTIFICACIONES ---
    async def get_all_tipos_justificacion(self) -> List[Dict]:
        """Obtener todos los tipos, incluyendo inactivos para gestión"""
        return await self.db.fetch_all("SELECT * FROM justificacion_tipos ORDER BY nombre")

    async def create_tipo_justificacion(self, tipo: JustificacionTipoCreate) -> int:
        query = """
            INSERT INTO justificacion_tipos (
                nombre, descripcion, con_goce_sueldo, dias_habiles, pagador, dias_defecto, activo,
                min_dias, max_dias, frecuencia_anual, dias_corridos, sobreescribe_feriados, 
                descuenta_remuneracion, es_horas_sindicales,
                es_por_horas, genera_deuda_horaria, nomenclatura
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            tipo.nombre, tipo.descripcion, 
            1 if tipo.con_goce_sueldo else 0,
            1 if tipo.dias_habiles else 0,
            tipo.pagador, 
            tipo.dias_defecto,
            1 if tipo.activo else 0,
            tipo.min_dias,
            tipo.max_dias,
            tipo.frecuencia_anual,
            1 if tipo.dias_corridos else 0,
            1 if tipo.sobreescribe_feriados else 0,
            1 if tipo.descuenta_remuneracion else 0,
            1 if tipo.es_horas_sindicales else 0,
            1 if tipo.es_por_horas else 0,
            1 if tipo.genera_deuda_horaria else 0,
            tipo.nomenclatura
        )
        res = await self.db.execute(query, params)
        return res.lastrowid

    async def update_tipo_justificacion(self, tipo_id: int, tipo: JustificacionTipoCreate) -> bool:
        query = """
            UPDATE justificacion_tipos SET
                nombre = ?, descripcion = ?, con_goce_sueldo = ?,
                dias_habiles = ?, pagador = ?, dias_defecto = ?, activo = ?,
                min_dias = ?, max_dias = ?, frecuencia_anual = ?,
                dias_corridos = ?, sobreescribe_feriados = ?,
                descuenta_remuneracion = ?, es_horas_sindicales = ?,
                es_por_horas = ?, genera_deuda_horaria = ?, nomenclatura = ?
            WHERE id = ?
        """
        params = (
            tipo.nombre, tipo.descripcion, 
            1 if tipo.con_goce_sueldo else 0,
            1 if tipo.dias_habiles else 0,
            tipo.pagador,
            tipo.dias_defecto,
            1 if tipo.activo else 0,
            tipo.min_dias,
            tipo.max_dias,
            tipo.frecuencia_anual,
            1 if tipo.dias_corridos else 0,
            1 if tipo.sobreescribe_feriados else 0,
            1 if tipo.descuenta_remuneracion else 0,
            1 if tipo.es_horas_sindicales else 0,
            1 if tipo.es_por_horas else 0,
            1 if tipo.genera_deuda_horaria else 0,
            tipo.nomenclatura,
            tipo_id
        )
        res = await self.db.execute(query, params)
        return res.rowcount > 0

    async def delete_tipo_justificacion(self, tipo_id: int) -> bool:
        try:
            res = await self.db.execute("DELETE FROM justificacion_tipos WHERE id = ?", (tipo_id,))
            return res.rowcount > 0
        except Exception as e:
            logger.error(f"Error eliminando tipo justificación: {e}")
            raise

    async def get_tipos_justificacion(self) -> List[Dict]:
        return await self.db.fetch_all("SELECT * FROM justificacion_tipos WHERE activo = 1 ORDER BY nombre")

    # --- PAGADORES ---
    async def get_all_pagadores(self, solo_activos: bool = True) -> List[Dict]:
        query = "SELECT * FROM cat_pagadores"
        if solo_activos:
            query += " WHERE activo = 1"
        query += " ORDER BY nombre"
        return await self.db.fetch_all(query)

    async def create_pagador(self, nombre: str) -> int:
        res = await self.db.execute("INSERT INTO cat_pagadores (nombre, activo) VALUES (?, 1)", (nombre,))
        return res.lastrowid

    async def update_pagador(self, pagador_id: int, nombre: str, activo: bool) -> bool:
        res = await self.db.execute(
            "UPDATE cat_pagadores SET nombre = ?, activo = ? WHERE id = ?",
            (nombre, 1 if activo else 0, pagador_id)
        )
        return res.rowcount > 0

    async def create_justificacion(self, j: JustificacionCreate) -> int:
        query = """
            INSERT INTO justificaciones (
                empleado_id, tipo_id, fecha_inicio, fecha_fin, 
                hora_inicio, hora_fin, observaciones, documento_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            j.empleado_id, j.tipo_id, str(j.fecha_inicio), str(j.fecha_fin), 
            j.hora_inicio, j.hora_fin, j.observaciones, j.documento_url
        )
        res = await self.db.execute(query, params)
        return res.lastrowid

    async def get_justificaciones_empleado(self, empleado_id: int) -> List[Dict]:
        query = """
            SELECT j.*, t.nombre as tipo_nombre, t.con_goce_sueldo
            FROM justificaciones j
            JOIN justificacion_tipos t ON j.tipo_id = t.id
            WHERE j.empleado_id = ?
            ORDER BY j.fecha_inicio DESC
        """
        return await self.db.fetch_all(query, (empleado_id,))

    async def cerrar_permiso_activo(self, empleado_id: int, fecha: str, hora_fin: str) -> bool:
        """Cierra un permiso que fue abierto sin hora de fin"""
        query = """
            UPDATE justificaciones 
            SET hora_fin = ? 
            WHERE empleado_id = ? 
              AND fecha_inicio = ? 
              AND hora_fin IS NULL
        """
        res = await self.db.execute(query, (hora_fin, empleado_id, fecha))
        return res.rowcount > 0

    async def get_justificacion_by_id(self, justificacion_id: int) -> Optional[Dict]:
        """Obtiene una justificación por su ID"""
        return await self.db.fetch_one(
            "SELECT * FROM justificaciones WHERE id = ?", (justificacion_id,))

    async def update_justificacion(self, justificacion_id: int, datos: dict) -> bool:
        """Actualiza una justificación existente"""
        query = """
            UPDATE justificaciones SET
                tipo_id = ?, fecha_inicio = ?, fecha_fin = ?,
                hora_inicio = ?, hora_fin = ?, observaciones = ?,
                documento_url = ?
            WHERE id = ?
        """
        res = await self.db.execute(query, (
            datos['tipo_id'], str(datos['fecha_inicio']), str(datos['fecha_fin']),
            datos.get('hora_inicio'), datos.get('hora_fin'),
            datos.get('observaciones'), datos.get('documento_url'),
            justificacion_id
        ))
        return res.rowcount > 0

    async def delete_justificacion(self, justificacion_id: int) -> Optional[Dict]:
        """Elimina una justificación. Retorna los datos previos para recálculo."""
        existing = await self.db.fetch_one(
            "SELECT * FROM justificaciones WHERE id = ?", (justificacion_id,))
        if not existing:
            return None
        await self.db.execute(
            "DELETE FROM justificaciones WHERE id = ?", (justificacion_id,))
        logger.info(f"Justificación ID={justificacion_id} eliminada (emp={existing['empleado_id']}, "
                     f"{existing['fecha_inicio']} → {existing['fecha_fin']})")
        return existing

    async def get_justificaciones_periodo(self, fecha_inicio: str, fecha_fin: str, empleado_id: int = None) -> List[Dict]:
        """Obtiene todas las justificaciones que se traslapan con el periodo dado"""
        query = """
            SELECT j.*, t.nombre as tipo_nombre, t.nomenclatura as tipo_nomenclatura, t.con_goce_sueldo, t.pagador,
                   t.dias_corridos, t.sobreescribe_feriados, t.descuenta_remuneracion, t.es_horas_sindicales,
                   t.es_por_horas, t.genera_deuda_horaria
            FROM justificaciones j
            JOIN justificacion_tipos t ON j.tipo_id = t.id
            WHERE (date(j.fecha_inicio) <= date(?) AND date(j.fecha_fin) >= date(?))
        """
        params = [fecha_fin, fecha_inicio]
        
        if empleado_id:
            query += " AND j.empleado_id = ?"
            params.append(empleado_id)
            
        query += " ORDER BY j.fecha_inicio ASC"
        return await self.db.fetch_all(query, tuple(params))

    async def get_justificaciones_dia_empleado(self, empleado_id: int, fecha: str) -> List[Dict]:
        """Obtiene todas las justificaciones (día completo o por horas) para un empleado en una fecha"""
        query = """
            SELECT j.*, t.nombre as tipo_nombre, t.nomenclatura as tipo_nomenclatura, t.con_goce_sueldo, t.pagador,
                   t.dias_corridos, t.sobreescribe_feriados, t.descuenta_remuneracion, t.es_horas_sindicales,
                   t.es_por_horas, t.genera_deuda_horaria
            FROM justificaciones j
            JOIN justificacion_tipos t ON j.tipo_id = t.id
            WHERE j.empleado_id = ? 
              AND (date(j.fecha_inicio) <= date(?) AND date(j.fecha_fin) >= date(?))
            ORDER BY j.hora_inicio ASC
        """
        return await self.db.fetch_all(query, (empleado_id, fecha, fecha))

    async def get_justificacion_activa(self, empleado_id: int, fecha: str) -> Optional[Dict]:
        """
        Busca si existe una justificación activa para la fecha dada.
        Retorna el detalle si existe, o None.
        """
    async def get_justificacion_activa(self, empleado_id: int, fecha: str) -> Optional[Dict]:
        """
        Busca si existe una justificación activa para la fecha dada.
        Retorna el detalle si existe, o None.
        """
        query = """
            SELECT j.*, t.nombre as tipo_nombre, t.nomenclatura as tipo_nomenclatura, t.con_goce_sueldo, t.dias_habiles, t.pagador,
                   t.dias_corridos, t.sobreescribe_feriados, t.descuenta_remuneracion
            FROM justificaciones j
            JOIN justificacion_tipos t ON j.tipo_id = t.id
            WHERE j.empleado_id = ? 
            AND date(?) BETWEEN date(j.fecha_inicio) AND date(j.fecha_fin)
            ORDER BY j.id DESC
            LIMIT 1
        """
        return await self.db.fetch_one(query, (empleado_id, fecha))

    # --- ASIGNACIÓN DE BONOS (HISTÓRICOS) ---
    async def create_asignacion(self, empleado_id: int, bono_id: int, fecha_desde: str) -> int:
        """Crear una asignación explícita de bono"""
        query = """
            INSERT INTO bono_asignaciones (empleado_id, bono_id, fecha_desde, fecha_hasta)
            VALUES (?, ?, ?, NULL)
        """
        res = await self.db.execute(query, (empleado_id, bono_id, fecha_desde))
        return res.lastrowid

    async def close_asignaciones(self, empleado_id: int, fecha_hasta: str):
        """Cerrar todas las asignaciones activas de un empleado"""
        query = """
            UPDATE bono_asignaciones 
            SET fecha_hasta = ? 
            WHERE empleado_id = ? AND fecha_hasta IS NULL
        """
        await self.db.execute(query, (fecha_hasta, empleado_id))

    async def delete_today_asignaciones(self, empleado_id: int, fecha_desde: str):
        """
        Eliminar asignaciones creadas hoy (o en el futuro) para evitar duplicados 
        o rangos inválidos al recalcular el mismo día.
        """
        query = """
            DELETE FROM bono_asignaciones 
            WHERE empleado_id = ? 
            AND date(fecha_desde) >= date(?)
        """
        await self.db.execute(query, (empleado_id, fecha_desde))

    async def get_active_asignaciones(self, empleado_id: int, fecha: str) -> List[Dict]:
        """Obtener asignaciones activas para una fecha específica"""
        query = """
            SELECT a.*, b.nombre as bono_nombre, b.id as bono_id
            FROM bono_asignaciones a
            JOIN bonos b ON a.bono_id = b.id
            WHERE a.empleado_id = ?
            AND date(a.fecha_desde) <= date(?)
            AND (a.fecha_hasta IS NULL OR date(a.fecha_hasta) >= date(?))
            AND b.activo = 1
        """
        return await self.db.fetch_all(query, (empleado_id, fecha, fecha))

    async def count_justificaciones_anio(self, empleado_id: int, tipo_id: int, anio: int) -> int:
        """Contar cuántas justificaciones de este tipo tiene el empleado en el año"""
        query = """
            SELECT COUNT(*) as count
            FROM justificaciones
            WHERE empleado_id = ?
            AND tipo_id = ?
            AND strftime('%Y', fecha_inicio) = ?
        """
        res = await self.db.fetch_one(query, (empleado_id, tipo_id, str(anio)))
        return res['count'] if res else 0

    async def get_active_asignaciones_batch(self, empleado_ids: List[int], fecha: str) -> List[Dict]:
        """
        Obtener asignaciones activas para una lista de empleados en una sola query.
        Retorna lista plana de asignaciones.
        """
        if not empleado_ids:
            return []
            
        placeholders = ','.join(['?'] * len(empleado_ids))
        query = f"""
            SELECT a.*, b.nombre as bono_nombre, b.id as bono_id
            FROM bono_asignaciones a
            JOIN bonos b ON a.bono_id = b.id
            WHERE a.empleado_id IN ({placeholders})
            AND date(a.fecha_desde) <= date(?)
            AND (a.fecha_hasta IS NULL OR date(a.fecha_hasta) >= date(?))
            AND b.activo = 1
        """
        # Params: list of ids + fecha + fecha
        params = empleado_ids + [fecha, fecha]
        return await self.db.fetch_all(query, tuple(params))

    # --- AJUSTES GLOBALES ---
    async def get_all_ajustes(self) -> List[Dict]:
        return await self.db.fetch_all("SELECT * FROM ajustes ORDER BY clave")

    async def get_ajuste(self, clave: str, default: Any = None) -> Any:
        res = await self.db.fetch_one("SELECT valor FROM ajustes WHERE clave = ?", (clave,))
        return res['valor'] if res else default

    async def set_ajuste(self, clave: str, valor: str) -> bool:
        await self.db.execute(
            "INSERT OR REPLACE INTO ajustes (clave, valor) VALUES (?, ?)",
            (clave, str(valor))
        )
        return True

    async def get_notificaciones_areas(self) -> List[dict]:
        return await self.db.fetch_all("SELECT id, area, emails FROM notificaciones_areas ORDER BY area ASC")

    async def get_notificaciones_area(self, area: str) -> str:
        res = await self.db.fetch_one("SELECT emails FROM notificaciones_areas WHERE area = ?", (area,))
        return res['emails'] if res else ""

    async def set_notificaciones_area(self, area: str, emails: str) -> bool:
        # Since area is UNIQUE, we can do INSERT OR REPLACE
        await self.db.execute(
            "INSERT OR REPLACE INTO notificaciones_areas (area, emails) VALUES (?, ?)",
            (area, emails)
        )
        return True
    
    async def delete_notificaciones_area(self, area: str) -> bool:
        await self.db.execute("DELETE FROM notificaciones_areas WHERE area = ?", (area,))
        return True
