from datetime import date
from typing import List, Optional, Dict, Any
from loguru import logger
from backend.core.database import Database
from backend.schemas.turno import TurnoCreate, TurnoResponse, TurnoDiaCreate, AsignacionCreate
import json

class TurnoRepository:
    def __init__(self, db: Database):
        self.db = db

    async def init_tables(self):
        """Inicializar tablas del módulo Horarios"""
        
        # 1. Tabla Turnos (Configuración)
        if not await self.db.table_exists("turnos"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS turnos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    tipo_programacion TEXT NOT NULL, -- FIJO, DINAMICO_FLEXIBLE, FLEXIBLE_BOLSA
                    meta_horas_semanales REAL DEFAULT 0.0,
                    tolerancia_retraso_alerta INTEGER DEFAULT 0,
                    tolerancia_retraso_descuento INTEGER DEFAULT 0,
                    redondeo_minutos INTEGER DEFAULT 0,
                    descuento_colacion_auto BOOLEAN DEFAULT 0,
                    minutos_colacion_auto INTEGER DEFAULT 0,
                    umbral_horas_colacion REAL DEFAULT 0.0,
                    anclaje_entrada_minutos INTEGER DEFAULT 0,
                    anclaje_salida_minutos INTEGER DEFAULT 0,
                    es_turno_cortado BOOLEAN DEFAULT 0,
                    hora_limite_ficticia TEXT,
                    area TEXT, -- Nuevo: Área de visibilidad
                    ventana_en_curso_minutos INTEGER DEFAULT 0,
                    tolerancia_exceso_colacion_minutos INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        if not await self.db.column_exists("turnos", "minutos_colacion"):
            try: await self.db.execute("ALTER TABLE turnos ADD COLUMN minutos_colacion INTEGER DEFAULT 0")
            except Exception as e: logger.debug(f"[Migration] minutos_colacion ya existe o error benigno: {e}")

        if not await self.db.column_exists("turnos", "anclaje_salida_minutos"):
            try: await self.db.execute("ALTER TABLE turnos ADD COLUMN anclaje_salida_minutos INTEGER DEFAULT 0")
            except Exception as e: logger.debug(f"[Migration] anclaje_salida_minutos ya existe o error benigno: {e}")

        if not await self.db.column_exists("turnos", "hora_limite_ficticia"):
            try: await self.db.execute("ALTER TABLE turnos ADD COLUMN hora_limite_ficticia TEXT")
            except Exception as e: logger.debug(f"[Migration] hora_limite_ficticia ya existe o error benigno: {e}")

        if not await self.db.column_exists("turnos", "area"):
            try: await self.db.execute("ALTER TABLE turnos ADD COLUMN area TEXT")
            except Exception as e: logger.debug(f"[Migration] area ya existe o error benigno: {e}")

        # Nuevas columnas para versionamiento de Turnos
        if not await self.db.column_exists("turnos", "turno_padre_id"):
            try: await self.db.execute("ALTER TABLE turnos ADD COLUMN turno_padre_id INTEGER")
            except Exception as e: logger.debug(f"[Migration] turno_padre_id ya existe o error benigno: {e}")

        if not await self.db.column_exists("turnos", "fecha_vigencia"):
            try: await self.db.execute("ALTER TABLE turnos ADD COLUMN fecha_vigencia TEXT")
            except Exception as e: logger.debug(f"[Migration] fecha_vigencia ya existe o error benigno: {e}")

        if not await self.db.column_exists("turnos", "ventana_en_curso_minutos"):
            try: await self.db.execute("ALTER TABLE turnos ADD COLUMN ventana_en_curso_minutos INTEGER DEFAULT 0")
            except Exception as e: logger.debug(f"[Migration] ventana_en_curso_minutos ya existe o error benigno: {e}")

        if not await self.db.column_exists("turnos", "tolerancia_exceso_colacion_minutos"):
            try: await self.db.execute("ALTER TABLE turnos ADD COLUMN tolerancia_exceso_colacion_minutos INTEGER DEFAULT 0")
            except Exception as e: logger.debug(f"[Migration] tolerancia_exceso_colacion_minutos ya existe o error benigno: {e}")

        if not await self.db.column_exists("turnos", "umbral_horas_colacion"):
            try: await self.db.execute("ALTER TABLE turnos ADD COLUMN umbral_horas_colacion REAL DEFAULT 0.0")
            except Exception as e: logger.debug(f"[Migration] umbral_horas_colacion ya existe o error benigno: {e}")

        if not await self.db.column_exists("turnos", "rotacion_secuencial"):
            try: await self.db.execute("ALTER TABLE turnos ADD COLUMN rotacion_secuencial BOOLEAN DEFAULT 1")
            except Exception as e: logger.debug(f"[Migration] rotacion_secuencial ya existe o error benigno: {e}")

        if not await self.db.column_exists("turnos", "semana_fallback_sin_marcas"):
            try: await self.db.execute("ALTER TABLE turnos ADD COLUMN semana_fallback_sin_marcas INTEGER DEFAULT 1")
            except Exception as e: logger.debug(f"[Migration] semana_fallback_sin_marcas ya existe o error benigno: {e}")

        # 2. Tabla Turno Dias (Detalle Semanal)
        if not await self.db.table_exists("turno_dias"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS turno_dias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turno_id INTEGER NOT NULL,
                    dia_semana INTEGER NOT NULL, -- 0=Lunes
                    num_semana INTEGER DEFAULT 1, -- BLOQUE SEMANAL (1, 2, 3...)
                    es_libre INTEGER DEFAULT 0,
                    horas_teoricas REAL DEFAULT 0,
                    hora_entrada TEXT, 
                    hora_salida TEXT,
                    cruza_medianoche INTEGER DEFAULT 0,
                    hora_entrada_2 TEXT,
                    hora_salida_2 TEXT,
                    cruza_medianoche_2 INTEGER DEFAULT 0,
                    FOREIGN KEY (turno_id) REFERENCES turnos (id) ON DELETE CASCADE
                )
            """)

        # Migraciones Manuales
        if not await self.db.column_exists("turno_dias", "num_semana"):
            try: 
                await self.db.execute("ALTER TABLE turno_dias ADD COLUMN num_semana INTEGER DEFAULT 1")
                logger.info("✨ Migración: Columna 'num_semana' agregada a turno_dias")
            except Exception as e:
                logger.error(f"❌ Error agregando columna num_semana: {e}")
        if not await self.db.column_exists("turno_dias", "hora_entrada_2"):
            try: await self.db.execute("ALTER TABLE turno_dias ADD COLUMN hora_entrada_2 TEXT")
            except Exception as e: logger.debug(f"[Migration] hora_entrada_2 ya existe o error benigno: {e}")
        if not await self.db.column_exists("turno_dias", "hora_salida_2"):
            try: await self.db.execute("ALTER TABLE turno_dias ADD COLUMN hora_salida_2 TEXT")
            except Exception as e: logger.debug(f"[Migration] hora_salida_2 ya existe o error benigno: {e}")
        if not await self.db.column_exists("turno_dias", "cruza_medianoche_2"):
            try: await self.db.execute("ALTER TABLE turno_dias ADD COLUMN cruza_medianoche_2 INTEGER DEFAULT 0")
            except Exception as e: logger.debug(f"[Migration] cruza_medianoche_2 ya existe o error benigno: {e}")
        if not await self.db.column_exists("turno_dias", "horas_teoricas"):
            try: await self.db.execute("ALTER TABLE turno_dias ADD COLUMN horas_teoricas REAL DEFAULT 0")
            except Exception as e: logger.debug(f"[Migration] horas_teoricas ya existe o error benigno: {e}")
        if not await self.db.column_exists("turno_dias", "etiqueta_bloque"):
            try: 
                await self.db.execute("ALTER TABLE turno_dias ADD COLUMN etiqueta_bloque TEXT")
                logger.info("✨ Migración: Columna 'etiqueta_bloque' agregada a turno_dias")
            except Exception as e: 
                logger.error(f"❌ Error agregando columna etiqueta_bloque: {e}")

        # ⚡ Índice compuesto para turno_dias (acelera búsqueda de config diaria en el motor)
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_turno_dias_lookup ON turno_dias(turno_id, dia_semana, num_semana)")

        # 2.5 Tabla Relacional Turno_Areas (N a N)
        if not await self.db.table_exists("turno_areas"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS turno_areas (
                    turno_id INTEGER NOT NULL,
                    area_id INTEGER NOT NULL,
                    PRIMARY KEY (turno_id, area_id),
                    FOREIGN KEY (turno_id) REFERENCES turnos (id) ON DELETE CASCADE,
                    FOREIGN KEY (area_id) REFERENCES areas (id) ON DELETE CASCADE
                )
            """)
            await self.db.execute("CREATE INDEX IF NOT EXISTS idx_turno_areas_area ON turno_areas(area_id)")

        # 3. Tabla Turno Segmentos (Micro-Shifts Opcional)
        if not await self.db.table_exists("turno_segmentos"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS turno_segmentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turno_dia_id INTEGER NOT NULL,
                    hora_inicio TEXT NOT NULL,
                    hora_fin TEXT NOT NULL,
                    FOREIGN KEY (turno_dia_id) REFERENCES turno_dias (id) ON DELETE CASCADE
                )
            """)

        # 4. Tabla Plantillas Planificación
        if not await self.db.table_exists("plantillas_planificacion"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS plantillas_planificacion (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    configuracion_json TEXT NOT NULL
                )
            """)

        # 5. Tabla Asignación Turnos
        if not await self.db.table_exists("asignacion_turnos"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS asignacion_turnos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    turno_id INTEGER NOT NULL,
                    fecha_inicio TEXT NOT NULL,
                    fecha_fin TEXT,
                    FOREIGN KEY (empleado_id) REFERENCES empleados (id),
                    FOREIGN KEY (turno_id) REFERENCES turnos (id)
                )
            """)
        # ⚡ Índices para la tabla más unida (JOIN en Matrix)
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_asig_empleado ON asignacion_turnos(empleado_id)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_asig_turno ON asignacion_turnos(turno_id)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_asig_fechas ON asignacion_turnos(fecha_inicio, fecha_fin)")
        # ⚡ Índice compuesto crítico para reproceso por periodo: acelera el filtro empleado+rango de fechas.
        # Acelera "WHERE empleado_id=? AND fecha_inicio<=? AND (fecha_fin IS NULL OR fecha_fin>=?)"
        # Sin esto, el motor hacía 3 lookups separados por cada día del periodo reprocesado.
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_asig_emp_rango ON asignacion_turnos(empleado_id, fecha_inicio, fecha_fin)")
        
        # 6. Tabla Bolsa de Horas
        if not await self.db.table_exists("bolsa_horas_resumen"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS bolsa_horas_resumen (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    periodo TEXT NOT NULL,
                    saldo_inicial REAL DEFAULT 0,
                    horas_trabajadas REAL DEFAULT 0,
                    horas_teoricas REAL DEFAULT 0,
                    saldo_final REAL DEFAULT 0,
                    FOREIGN KEY (empleado_id) REFERENCES empleados (id)
                )
            """)

        # 7. Tabla Asistencias (Marcaciones Procesadas)
        if not await self.db.table_exists("asistencias"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS asistencias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    fecha TEXT NOT NULL,
                    turno_asignado_id INTEGER,
                    hora_entrada_teorica TEXT,
                    hora_salida_teorica TEXT,
                    horas_teoricas REAL DEFAULT 0,
                    hora_entrada_real TEXT,
                    hora_salida_real TEXT,
                    minutos_atraso INTEGER DEFAULT 0,
                    minutos_colacion INTEGER DEFAULT 0,
                    horas_trabajadas REAL DEFAULT 0,
                    estado TEXT DEFAULT 'PENDIENTE', -- OK, ATRASO, INASISTENCIA, ANOMALIA
                    observaciones TEXT,
                    hora_inicio TEXT,
                    hora_fin TEXT,
                    origen TEXT DEFAULT 'SISTEMA',
                    detalle_tramos TEXT,
                    minutos_deuda INTEGER DEFAULT 0,
                    minutos_extra_bruto INTEGER DEFAULT 0,
                    minutos_salida_adelantada INTEGER DEFAULT 0,
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (empleado_id) REFERENCES empleados (id)
                )
            """)

        # Migración para agregar columnas si no existen (Escudadas para Startup Turbo ⚡)
        columns_check = [
            ("horas_teoricas", "REAL DEFAULT 0"),
            ("hora_entrada_teorica", "TEXT"),
            ("hora_salida_teorica", "TEXT"),
            ("minutos_atraso", "INTEGER DEFAULT 0"),
            ("minutos_colacion", "INTEGER DEFAULT 0"),
            ("horas_trabajadas", "REAL DEFAULT 0"),
            ("estado", "TEXT DEFAULT 'PENDIENTE'"),
            ("observaciones", "TEXT"),
            ("hora_inicio", "TEXT"),
            ("hora_fin", "TEXT"),
            ("origen", "TEXT DEFAULT 'SISTEMA'"),
            ("hora_entrada_real", "TEXT"),
            ("hora_salida_real", "TEXT"),
            ("detalle_tramos", "TEXT"),
            ("minutos_deuda", "INTEGER DEFAULT 0"),
            ("minutos_extra_bruto", "INTEGER DEFAULT 0"),
            ("minutos_salida_adelantada", "INTEGER DEFAULT 0"),
            ("updated_at", "TEXT DEFAULT '2026-01-01 00:00:00'"),
            ("minutos_colacion_real", "INTEGER DEFAULT 0"),
            ("minutos_exceso_colacion", "INTEGER DEFAULT 0"),
            ("minutos_colacion_auto", "INTEGER DEFAULT 0"),
            ("minutos_permiso_personal_deuda", "INTEGER DEFAULT 0"),
            ("hora_salida_colacion", "TEXT"),
            ("hora_entrada_colacion", "TEXT"),
            ("hora_inicio_permiso", "TEXT"),
            ("hora_termino_permiso", "TEXT"),
            ("minutos_permisos_detectados", "INTEGER DEFAULT 0"),
            # ── Flags independientes de eventos (v2.0) ──────────────────────
            # Permiten medir atrasos, salidas adelantadas y permisos como
            # métricas separadas, incluso cuando coexisten en el mismo día.
            ("tiene_atraso",             "INTEGER NOT NULL DEFAULT 0"),
            ("tiene_salida_adelantada",  "INTEGER NOT NULL DEFAULT 0"),
            ("tiene_permiso",            "INTEGER NOT NULL DEFAULT 0"),
            # ── [DT-9 y DT-10] Persistencia Atómica de Siembra ─────────────
            ("num_semana_ganadora",      "INTEGER DEFAULT 1"),
            ("marcas_consumidas_ids",    "TEXT DEFAULT '[]'"),
            # ── Condonación de Deuda (Perdonazo) ─────────────
            ("deuda_condonada",          "INTEGER DEFAULT 0"),
        ]
        for col, type_def in columns_check:
            if not await self.db.column_exists("asistencias", col):
                try:
                    await self.db.execute(f"ALTER TABLE asistencias ADD COLUMN {col} {type_def}")
                    logger.info(f"✨ Migración: Columna '{col}' agregada a asistencias")
                except Exception as mig_err:
                    logger.error(f"❌ Error crítico en migración de asistencias ({col}): {mig_err}")

        # ⚡ Índices para tabla asistencias (la más consultada del módulo Marcaciones)
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_asis_empleado_fecha ON asistencias(empleado_id, fecha)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_asis_fecha ON asistencias(fecha)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_asis_estado ON asistencias(estado)")
        await self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_asistencias_emp_fecha ON asistencias(empleado_id, fecha)")

        # 7.5. Tabla Jornadas Especiales (Días Libres/Feriados Trabajados)
        if not await self.db.table_exists("jornadas_especiales"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS jornadas_especiales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    fecha TEXT NOT NULL,
                    hora_entrada TEXT,
                    hora_salida TEXT,
                    minutos_trabajados INTEGER DEFAULT 0,
                    estado TEXT DEFAULT 'JORNADA_ESPECIAL',
                    observaciones TEXT,
                    FOREIGN KEY (empleado_id) REFERENCES empleados (id)
                )
            """)
        # ⚡ Índices para tabla jornadas_especiales
        await self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_jornadas_emp_fecha ON jornadas_especiales(empleado_id, fecha)")

        # 8. Tabla Logs Raw (Marcaciones sin procesar)
        if not await self.db.table_exists("logs_raw"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS logs_raw (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    rut TEXT,
                    fecha_hora TEXT NOT NULL,
                    tipo TEXT, -- ENTRADA/SALIDA si el sistema lo da, sino null
                    equipo TEXT,
                    hash_original TEXT UNIQUE, -- Para evitar duplicados en sync
                    created_at TEXT DEFAULT (datetime('now')),
                    manual INTEGER DEFAULT 0,
                    observaciones TEXT,
                    usuario_id INTEGER
                )
            """)

        # Migraciones para logs_raw (Escudadas ⚡)
        logs_cols = [
            ("manual", "INTEGER DEFAULT 0"),
            ("observaciones", "TEXT"),
            ("usuario_id", "INTEGER")
        ]
        for col, type_def in logs_cols:
            if not await self.db.column_exists("logs_raw", col):
                try:
                    await self.db.execute(f"ALTER TABLE logs_raw ADD COLUMN {col} {type_def}")
                    logger.info(f"✨ Migración: Columna '{col}' agregada a logs_raw")
                except Exception as mig_err:
                    logger.error(f"❌ Error crítico en migración de logs_raw ({col}): {mig_err}")

        # ⚡ Índices para logs_raw (tabla de marcaciones crudas - leida en cada recalculo)
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_logs_raw_empleado ON logs_raw(empleado_id)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_logs_raw_fecha ON logs_raw(fecha_hora)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_logs_raw_hash ON logs_raw(hash_original)")
        # ⚡ [CRÍTICO] Índice compuesto para el motor de cálculo (Overtime Lookahead + Reprocesamiento)
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_logs_raw_emp_fecha ON logs_raw(empleado_id, fecha_hora)")
        await self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_raw_unique_marca ON logs_raw(empleado_id, fecha_hora, tipo)")

        # ═══════════════════════════════════════════════════════════════════
        # 9. Tabla Horas Extras (Migración Plan v3.1 — Fase 1)
        # Desacopla lógica financiera HE de la tabla asistencias
        # ═══════════════════════════════════════════════════════════════════
        if not await self.db.table_exists("horas_extras"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS horas_extras (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    fecha TEXT NOT NULL,
                    minutos_bruto REAL DEFAULT 0,
                    minutos_autorizados REAL DEFAULT 0,
                    estado TEXT DEFAULT 'PENDIENTE' CHECK(estado IN ('PENDIENTE','APROBADO','RECHAZADO')),
                    origen TEXT DEFAULT 'SISTEMA',
                    comentario TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (empleado_id) REFERENCES empleados(id) ON DELETE CASCADE,
                    UNIQUE(empleado_id, fecha)
                )
            """)
            logger.info("✨ Migración Fase 1: Tabla 'horas_extras' creada")

        # ⚡ Índices para horas_extras
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_he_empleado ON horas_extras(empleado_id)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_he_fecha ON horas_extras(fecha)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_he_estado ON horas_extras(estado)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_he_emp_fecha ON horas_extras(empleado_id, fecha)")

        # ═══════════════════════════════════════════════════════════════════
        # 10. Fix CASCADE en jornadas_especiales (Plan v3.1 — Fase 1.2)
        # Si la FK no tiene ON DELETE CASCADE, recrear la tabla
        # ═══════════════════════════════════════════════════════════════════
        try:
            row = await self.db.fetch_one(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='jornadas_especiales'"
            )
            if row and row['sql'] and 'ON DELETE CASCADE' not in row['sql']:
                logger.info("🔧 Migración Fase 1.2: Aplicando ON DELETE CASCADE a jornadas_especiales")
                await self.db.execute("""
                    CREATE TABLE IF NOT EXISTS jornadas_especiales_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        empleado_id INTEGER NOT NULL,
                        fecha TEXT NOT NULL,
                        hora_entrada TEXT,
                        hora_salida TEXT,
                        minutos_trabajados INTEGER DEFAULT 0,
                        estado TEXT DEFAULT 'JORNADA_ESPECIAL',
                        observaciones TEXT,
                        FOREIGN KEY (empleado_id) REFERENCES empleados(id) ON DELETE CASCADE
                    )
                """)
                await self.db.execute("INSERT INTO jornadas_especiales_new SELECT * FROM jornadas_especiales")
                await self.db.execute("DROP TABLE jornadas_especiales")
                await self.db.execute("ALTER TABLE jornadas_especiales_new RENAME TO jornadas_especiales")
                await self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_jornadas_emp_fecha ON jornadas_especiales(empleado_id, fecha)")
                logger.info("✅ Migración Fase 1.2: CASCADE aplicado a jornadas_especiales")
        except Exception as e:
            logger.warning(f"⚠️ Fix CASCADE jornadas_especiales: {e}")

        # ═══════════════════════════════════════════════════════════════════
        # 11. Tabla de Compensaciones de Inasistencias con H.E.
        # ═══════════════════════════════════════════════════════════════════
        if not await self.db.column_exists("horas_extras", "minutos_compensados"):
            try:
                await self.db.execute("ALTER TABLE horas_extras ADD COLUMN minutos_compensados REAL DEFAULT 0")
                logger.info("✨ Migración: Columna 'minutos_compensados' agregada a horas_extras")
            except Exception as mig_err:
                logger.error(f"❌ Error migración de horas_extras (minutos_compensados): {mig_err}")

        if not await self.db.table_exists("compensaciones_he_inasistencia"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS compensaciones_he_inasistencia (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    fecha_inasistencia TEXT NOT NULL,
                    fecha_he TEXT NOT NULL,
                    minutos REAL NOT NULL,
                    observaciones TEXT,
                    aprobado_por INTEGER,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (empleado_id) REFERENCES empleados (id) ON DELETE CASCADE,
                    FOREIGN KEY (aprobado_por) REFERENCES usuarios (id) ON DELETE SET NULL,
                    FOREIGN KEY (empleado_id, fecha_he) REFERENCES horas_extras (empleado_id, fecha) ON DELETE CASCADE,
                    UNIQUE(empleado_id, fecha_inasistencia, fecha_he)
                )
            """)
            logger.info("✨ Tabla 'compensaciones_he_inasistencia' creada")

        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_comp_he_inas_fecha ON compensaciones_he_inasistencia (empleado_id, fecha_inasistencia)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_comp_he_fecha_he ON compensaciones_he_inasistencia (empleado_id, fecha_he)")


    async def create_turno(self, turno: TurnoCreate) -> int:
        """Crea un turno completo con sus días de configuración"""
        try:
            # 1. Insertar Turno Padre
            sql_turno = """
                INSERT INTO turnos (
                    nombre, tipo_programacion, meta_horas_semanales,
                    tolerancia_retraso_alerta, tolerancia_retraso_descuento,
                    redondeo_minutos, descuento_colacion_auto, minutos_colacion_auto, umbral_horas_colacion, es_turno_cortado,
                    anclaje_entrada_minutos, anclaje_salida_minutos, hora_limite_ficticia,
                    ventana_en_curso_minutos, tolerancia_exceso_colacion_minutos,
                    turno_padre_id, fecha_vigencia, rotacion_secuencial, semana_fallback_sin_marcas
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params_turno = (
                turno.nombre, turno.tipo_programacion, turno.meta_horas_semanales,
                turno.tolerancia_retraso_alerta, turno.tolerancia_retraso_descuento,
                turno.redondeo_minutos, 1 if turno.descuento_colacion_auto else 0, turno.minutos_colacion_auto, turno.umbral_horas_colacion, turno.es_turno_cortado,
                turno.anclaje_entrada_minutos, turno.anclaje_salida_minutos, turno.hora_limite_ficticia,
                turno.ventana_en_curso_minutos, turno.tolerancia_exceso_colacion_minutos,
                turno.turno_padre_id, turno.fecha_vigencia,
                1 if turno.rotacion_secuencial else 0, turno.semana_fallback_sin_marcas
            )
            
            cursor = await self.db.execute(sql_turno, params_turno)
            turno_id = cursor.lastrowid
            
            # Asociar a múltiples áreas
            if turno.areas:
                for area_name in turno.areas:
                    await self.db.execute("INSERT OR IGNORE INTO turno_areas (turno_id, area_id) SELECT ?, id FROM areas WHERE nombre = ?", (turno_id, area_name))
            
            # 2. Insertar Días
            sql_dia = """
                INSERT INTO turno_dias (
                    turno_id, dia_semana, num_semana, es_libre, horas_teoricas,
                    hora_entrada, hora_salida, cruza_medianoche,
                    hora_entrada_2, hora_salida_2, cruza_medianoche_2, etiqueta_bloque
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            for dia in turno.dias:
                params_dia = (
                    turno_id, dia.dia_semana, dia.num_semana, dia.es_libre, dia.horas_teoricas,
                    dia.hora_entrada, dia.hora_salida, dia.cruza_medianoche,
                    dia.hora_entrada_2, dia.hora_salida_2, dia.cruza_medianoche_2, dia.etiqueta_bloque
                )
                await self.db.execute(sql_dia, params_dia)
            
            return turno_id
            
        except Exception as e:
            logger.error(f"Error creando turno: {e}")
            # El rollback global no es fácil en hybrid, pero como es create, queda inconsistente si falla a medias.
            # Idealmente deberíamos manejar transacción distribuida, pero por ahora logueamos.
            raise

    async def get_all_turnos(self, include_details: bool = True) -> List[Dict]:
        """Obtener todos los turnos, opcionalmente con sus días"""
        try:
            # Traer cabeceras
            query = "SELECT * FROM turnos ORDER BY nombre"
            turnos_list = await self.db.fetch_all(query)
            
            if not include_details:
                return turnos_list

            # Enriquecer con días y áreas (Solo si se solicita)
            for t in turnos_list:
                dias_query = "SELECT * FROM turno_dias WHERE turno_id = ? ORDER BY dia_semana"
                dias = await self.db.fetch_all(dias_query, (t['id'],))
                t['dias'] = dias
                
                areas_query = "SELECT a.nombre FROM turno_areas ta JOIN areas a ON ta.area_id = a.id WHERE ta.turno_id = ?"
                areas_res = await self.db.fetch_all(areas_query, (t['id'],))
                t['areas'] = [r['nombre'] for r in areas_res]
            
            return turnos_list
        except Exception as e:
            logger.error(f"Error getting turnos: {e}")
            return []

    async def get_turnos_by_areas(self, areas: List[str], include_details: bool = True) -> List[Dict]:
        """
        Obtiene turnos visibles para un conjunto de áreas.
        Retorna:
          - Turnos específicos del área (t.area IN (...))
          - Turnos globales sin área asignada (t.area IS NULL o vacío) → visibles para todos
        Implementa RLS múltiple sin excluir recursos compartidos.
        """
        try:
            if not areas:
                return []
                
            placeholders = ",".join(["?"] * len(areas))
            query = f"""
                SELECT DISTINCT t.*
                FROM turnos t
                LEFT JOIN turno_areas ta ON t.id = ta.turno_id
                LEFT JOIN areas a ON ta.area_id = a.id
                WHERE a.nombre IN ({placeholders})
                   OR ta.area_id IS NULL -- Fallback para turnos huérfanos/globales
                ORDER BY t.nombre
            """
            turnos_list = await self.db.fetch_all(query, tuple(areas))

            if not include_details:
                return turnos_list

            # Enriquecer con días y áreas (Solo si se solicita)
            for t in turnos_list:
                dias_query = "SELECT * FROM turno_dias WHERE turno_id = ? ORDER BY dia_semana"
                dias = await self.db.fetch_all(dias_query, (t['id'],))
                t['dias'] = dias
                
                areas_query = "SELECT a.nombre FROM turno_areas ta JOIN areas a ON ta.area_id = a.id WHERE ta.turno_id = ?"
                areas_res = await self.db.fetch_all(areas_query, (t['id'],))
                t['areas'] = [r['nombre'] for r in areas_res]

            return turnos_list
        except Exception as e:
            logger.error(f"Error getting turnos by areas '{areas}': {e}")
            return []

    async def get_stats_por_area(self) -> Dict[str, Any]:
        """Devuelve un mapa con la cantidad de turnos asignados a cada área"""
        try:
            # Selecciona todas las areas y hace COUNT de los turnos asociados
            query = """
                SELECT a.nombre as area_nombre, COUNT(ta.turno_id) as turnos_count
                FROM areas a
                LEFT JOIN turno_areas ta ON a.id = ta.area_id
                GROUP BY a.id, a.nombre
            """
            rows = await self.db.fetch_all(query)
            # También podríamos incluir los turnos globales (si hay) y sumarlos a todas las áreas, 
            # pero estrictamente queremos saber cuántos turnos están explícitamente disponibles para el área.
            # Ojo: Si hay turnos sin área (huérfanos), aplican a todos. Sumémoslos.
            query_globales = """
                SELECT COUNT(*) as count 
                FROM turnos t 
                WHERE NOT EXISTS (SELECT 1 FROM turno_areas ta WHERE ta.turno_id = t.id)
            """
            globales_res = await self.db.fetch_one(query_globales)
            turnos_globales = globales_res['count'] if globales_res else 0
            
            areas_dict = {row['area_nombre']: row['turnos_count'] for row in rows}
            
            return {
                "areas": areas_dict,
                "globales": turnos_globales
            }
        except Exception as e:
            logger.error(f"Error en stats por área: {e}")
            return {"areas": {}, "globales": 0}

    async def create_asignacion(self, asignacion: AsignacionCreate) -> int:
        """
        Crea una asignación gestionando conflictos inteligentemente.
        Si 'reemplazar' es True, cierra solapamientos con Soft-Close (UPDATE fecha_fin).
        Si es False y hay solapamiento, levanta un ValueError o Exception manejada.
        
        [REGLA INVIOLABLE]: Jamás se ejecuta DELETE FROM asignacion_turnos.
        Los turnos solapados se cierran históricamente, nunca se borran.
        """
        try:
            # 1. Detección de solapamiento
            # Un turno A solapa con B si A.inicio <= B.fin Y A.fin >= B.inicio
            req_inicio = asignacion.fecha_inicio
            req_fin = asignacion.fecha_fin or '2099-12-31'
            
            # --- Auto-Alineación y Barrera de Fecha de Salida (Contrato) ---
            emp = await self.db.fetch_one("SELECT fecha_ingreso, fecha_salida FROM empleados WHERE id = ?", (asignacion.empleado_id,))
            if not emp:
                raise ValueError("El empleado no existe en los registros")
                
            # Logica de Cuadratura (Auto-Alineación): Si el turno empieza antes que el ingreso, lo movemos al ingreso
            if emp['fecha_ingreso'] and req_inicio < emp['fecha_ingreso']:
                old_ini = req_inicio
                asignacion.fecha_inicio = emp['fecha_ingreso']
                req_inicio = asignacion.fecha_inicio
                logger.warning(f"⚠️ Auto-Alineación: Movido inicio de turno de {old_ini} a {req_inicio} para emp {asignacion.empleado_id}")

            if emp['fecha_salida'] and req_inicio > emp['fecha_salida']:
                raise ValueError(f"No se puede asignar un turno iniciando el {req_inicio}, ya que su fecha de baja es {emp['fecha_salida']}")
            
            sql_buscar_solapes = f"""
                SELECT id, fecha_inicio, COALESCE(fecha_fin, '2099-12-31') as fecha_fin_calc
                FROM asignacion_turnos
                WHERE empleado_id = ?
                  AND fecha_inicio <= ?
                  AND COALESCE(fecha_fin, '2099-12-31') >= ?
            """
            solapes = await self.db.fetch_all(sql_buscar_solapes, (asignacion.empleado_id, req_fin, req_inicio))
            
            if solapes and not asignacion.reemplazar:
                # 2. Barrera de seguridad
                raise ValueError(f"Conflicto de asignación: el empleado ya tiene turno en todo o parte del periodo indicado ({req_inicio} al {req_fin})")

            pending_ops = []
            insert_new = True  # Flag: si ya actualizamos in-place, no crear nuevo registro

            if solapes and asignacion.reemplazar:
                # 3. Lógica de Reemplazo con Cierre Histórico (Soft-Close)
                # Identificamos cada turno existente que se interseca
                for s in solapes:
                    id_viejo = s['id']
                    ini_viejo = s['fecha_inicio']
                    fin_viejo = s['fecha_fin_calc']
                    
                    if ini_viejo >= req_inicio and fin_viejo <= req_fin:
                        # 3.1 Turno engullido entero.
                        if ini_viejo == req_inicio:
                            # Caso especial: misma fecha de inicio.
                            # NO podemos neutralizar + insertar (colisión UNIQUE en fecha_inicio).
                            # Solución: actualizar el registro EXISTENTE en su lugar con el nuevo turno.
                            # Esto preserva la clave (empleado_id, fecha_inicio) sin conflictos.
                            pending_ops.append((
                                "UPDATE asignacion_turnos SET turno_id = ?, fecha_fin = ? WHERE id = ?",
                                (asignacion.turno_id, asignacion.fecha_fin, id_viejo)
                            ))
                            insert_new = False  # Ya actualizamos in-place, no insertar nuevo
                            logger.info(f"🔄 Soft-Close (in-place): Turno #{id_viejo} actualizado con turno {asignacion.turno_id} desde [{ini_viejo}] — sin colisión UNIQUE")
                        else:
                            # fecha_inicio difiere → no hay colisión de clave, neutralizar normalmente
                            pending_ops.append((
                                "UPDATE asignacion_turnos SET fecha_fin = fecha_inicio WHERE id = ?",
                                (id_viejo,)
                            ))
                            logger.info(f"📦 Soft-Close (engullido): Turno #{id_viejo} neutralizado [{ini_viejo}] → registro 0 días")

                    elif ini_viejo < req_inicio and fin_viejo > req_fin:
                        # 3.2 Sándwich (El nuevo turno se inserta en medio del viejo)
                        # Cerrar la primera parte del viejo justo antes del nuevo turno
                        pending_ops.append(("UPDATE asignacion_turnos SET fecha_fin = date(?, '-1 day') WHERE id = ?", (req_inicio, id_viejo)))
                        # Y crear la segunda parte después del nuevo turno (continuación histórica)
                        sql_post = "INSERT INTO asignacion_turnos (empleado_id, turno_id, fecha_inicio, fecha_fin) SELECT empleado_id, turno_id, date(?, '+1 day'), ? FROM asignacion_turnos WHERE id = ?"
                        pending_ops.append((sql_post, (req_fin, s['fecha_fin_calc'] if s['fecha_fin_calc'] != '2099-12-31' else None, id_viejo)))
                        logger.info(f"🔀 Soft-Close (sándwich): Turno #{id_viejo} partido en dos alrededor de [{req_inicio} — {req_fin}]")
                    elif ini_viejo < req_inicio and fin_viejo <= req_fin:
                        # 3.3 Colisión frontal: Cerrar el viejo para que termine antes del nuevo
                        pending_ops.append(("UPDATE asignacion_turnos SET fecha_fin = date(?, '-1 day') WHERE id = ?", (req_inicio, id_viejo)))
                        logger.info(f"⏪ Soft-Close (frontal): Turno #{id_viejo} cerrado en date('{req_inicio}', '-1 day')")
                    elif ini_viejo >= req_inicio and fin_viejo > req_fin:
                        # 3.4 Colisión trasera: Atrasar el inicio del viejo para después del nuevo
                        pending_ops.append(("UPDATE asignacion_turnos SET fecha_inicio = date(?, '+1 day') WHERE id = ?", (req_fin, id_viejo)))
                        logger.info(f"⏩ Soft-Close (trasera): Turno #{id_viejo} empujado a date('{req_fin}', '+1 day')")

                # 3.5 Blindaje Final: Neutralizar cualquier registro que haya quedado
                # totalmente dentro del rango solicitado tras los acortamientos
                # (fecha_fin = fecha_inicio → registro de 0 días, sin efecto operativo)
                sql_neutralize = """
                    UPDATE asignacion_turnos 
                    SET fecha_fin = fecha_inicio
                    WHERE empleado_id = ? 
                      AND fecha_inicio >= ? 
                      AND COALESCE(fecha_fin, '2099-12-31') <= ?
                      AND fecha_fin != fecha_inicio
                """
                pending_ops.append((sql_neutralize, (asignacion.empleado_id, req_inicio, req_fin)))

            # 4. Crear nueva asignación (solo si no actualizamos in-place en 3.1)
            if insert_new:
                sql_new = """
                    INSERT INTO asignacion_turnos (empleado_id, turno_id, fecha_inicio, fecha_fin)
                    VALUES (?, ?, ?, ?)
                """
                pending_ops.append((sql_new, (
                    asignacion.empleado_id, asignacion.turno_id, 
                    asignacion.fecha_inicio, asignacion.fecha_fin
                )))

            # 5. Ejecutar TODO en un solo Batch Atómico
            if pending_ops:
                await self.db.execute_batch(pending_ops)
                
            return 1
            
        except Exception as e:
            logger.error(f"Error creando asignación: {e}")
            raise

    async def delete_turno(self, turno_id: int) -> bool:
        """Elimina un turno and sus dependencias (días)"""
        try:
            # Cloud Sync: Usar db.execute
            await self.db.execute("DELETE FROM turnos WHERE id = ?", (turno_id,))
            return True
        except Exception as e:
            logger.error(f"Error eliminando turno {turno_id}: {e}")
            return False

    async def save_raw_log(self, data: Dict[str, Any]) -> bool:
        """
        Guarda una marcación cruda individual.
        """
        return await self.save_raw_logs([data])

    async def save_raw_logs(self, data_list: List[Dict[str, Any]], suppress_auto_sync: bool = False) -> bool:
        """
        Guarda múltiples marcaciones crudas en un solo batch de Turso.
        Optimización crítica para BioAlba Sync.
        """
        if not data_list:
            return True
            
        try:
            # 1. Precargar RUTs de empleados locales para mapeo masivo
            # (Evita hacer un SELECT por cada log)
            from backend.repositories.empleado import EmpleadoRepository
            emp_repo = EmpleadoRepository(self.db)
            all_ruts_map = await emp_repo.get_rut_id_map() # Debemos implementar esto
            
            query = """
                INSERT OR IGNORE INTO logs_raw (empleado_id, rut, fecha_hora, tipo, equipo, hash_original)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            
            import hashlib
            batch_params = []
            
            for data in data_list:
                rut = str(data.get('rut', '')).strip()
                fecha_hora = data.get('fecha_hora')
                tipo = data.get('tipo', '')
                equipo = data.get('equipo', '')
                
                # Obtener ID desde el mapa precargado
                emp_id = all_ruts_map.get(rut)
                if not emp_id:
                    # Intento de fallback (limpiar RUT si el mapa usa formatos distintos)
                    rut_clean = rut.replace(".", "").replace("-", "").strip()
                    emp_id = all_ruts_map.get(rut_clean)
                
                if not emp_id and rut != "1":
                    continue # Ignorar si no existe el empleado localmente
                
                if not emp_id and rut == "1":
                    # El RUT 1 suele ser Admin, lo guardamos con un ID ficticio o lo saltamos
                    continue

                # [ATOMIC_HASH_PROTECTION]: SHA256 Sovereign Hash
                raw_string = f"{rut}|{fecha_hora}|{tipo or ''}"
                hash_val = hashlib.sha256(raw_string.encode()).hexdigest()
                
                batch_params.append((emp_id, rut, fecha_hora, tipo, equipo, hash_val))

            if batch_params:
                import asyncio
                chunk_size = 100
                for i in range(0, len(batch_params), chunk_size):
                    chunk = batch_params[i:i + chunk_size]
                    await self.db.executemany(query, chunk, suppress_auto_sync=suppress_auto_sync)
                    # Pause to allow Turso Sync Rust engine to flush frames cleanly
                    await asyncio.sleep(0.2)
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error guardando batch de raw logs: {e}")
            return False

    async def update_assignment_start_date(self, empleado_id: int, new_start_date: date) -> bool:
        """
        Actualiza la fecha de inicio de la asignación de un empleado de forma ATÓMICA.
        Cierra históricamente el turno activo actual y crea una nueva asignación limpia.
        Sincroniza la fecha de ingreso para evitar bloqueos del motor.
        
        [REGLA INVIOLABLE]: Jamás se ejecuta DELETE FROM asignacion_turnos.
        La historia completa de turnos del empleado se preserva siempre.
        """
        try:
            # 1. Identificar el turno activo actual (fecha_fin IS NULL o fecha_fin >= hoy)
            query_turno = """
                SELECT id, turno_id, fecha_inicio 
                FROM asignacion_turnos 
                WHERE empleado_id = ? 
                  AND (fecha_fin IS NULL OR fecha_fin >= date('now'))
                ORDER BY fecha_inicio DESC LIMIT 1
            """
            res_turno = await self.db.fetch_one(query_turno, [empleado_id])
            
            # Si no hay turno activo, buscar el más reciente (histórico) para heredar turno_id
            if not res_turno:
                query_fallback = "SELECT id, turno_id, fecha_inicio FROM asignacion_turnos WHERE empleado_id = ? ORDER BY fecha_inicio DESC LIMIT 1"
                res_turno = await self.db.fetch_one(query_fallback, [empleado_id])
            
            # Si no hay turnos en absoluto, usar turno por defecto (ID 1)
            turno_id = res_turno['turno_id'] if res_turno else 1

            pending_ops = []
            new_date_iso = new_start_date.isoformat()

            # 2. Soft-Close: Cerrar el turno activo actual (si existe) justo antes de la nueva fecha
            if res_turno:
                pending_ops.append((
                    "UPDATE asignacion_turnos SET fecha_fin = date(?, '-1 day') WHERE id = ? AND (fecha_fin IS NULL OR fecha_fin >= ?)",
                    (new_date_iso, res_turno['id'], new_date_iso)
                ))
                logger.info(f"📦 Soft-Close: Turno activo #{res_turno['id']} cerrado en date('{new_date_iso}', '-1 day') para emp {empleado_id}")

            # 3. Neutralizar cualquier turno futuro que quede dentro del nuevo rango
            # (fecha_fin = fecha_inicio → registro de 0 días, huella histórica inofensiva)
            pending_ops.append((
                "UPDATE asignacion_turnos SET fecha_fin = fecha_inicio WHERE empleado_id = ? AND fecha_inicio >= ? AND (fecha_fin IS NULL OR fecha_fin >= ?)",
                (empleado_id, new_date_iso, new_date_iso)
            ))

            # 4. Creación de la nueva asignación (continua, sin fecha_fin)
            pending_ops.append((
                "INSERT INTO asignacion_turnos (empleado_id, turno_id, fecha_inicio, fecha_fin) VALUES (?, ?, ?, NULL)",
                (empleado_id, turno_id, new_date_iso)
            ))

            # 5. Sincronización de Fecha de Ingreso (Ficha Maestra)
            # El motor de asistencia usa fecha_ingreso como barrera legal. Si la nueva asignación es anterior,
            # debemos mover la fecha de ingreso para que el motor 'vea' los datos.
            pending_ops.append((
                "UPDATE empleados SET fecha_ingreso = ?, activo = 1 WHERE id = ? AND (fecha_ingreso > ? OR fecha_ingreso IS NULL)",
                (new_date_iso, empleado_id, new_date_iso)
            ))

            # 6. Ejecutar Batch Atómico
            await self.db.execute_batch(pending_ops)
            logger.success(f"✨ Magia Administrativa aplicada para empleado {empleado_id}: Inicio unificado en {new_date_iso} (historia preservada)")
            
            return True
        except Exception as e:
            logger.error(f"❌ Error en Magia Administrativa (unificación): {e}")
            return False

    async def get_existing_hashes(self, mes: int, anio: int) -> set:
        """
        Retorna un SET con los hashes de los logs existentes para el mes/año.
        Optimización para no intentar insertar 2000 registros uno por uno.
        """
        try:
            # Construir filtro de fecha YYYY-MM%
            fecha_filter = f"{anio}-{mes:02d}%"
            query = "SELECT hash_original FROM logs_raw WHERE fecha_hora LIKE ?"
            rows = await self.db.fetch_all(query, (fecha_filter,))
            return {row['hash_original'] for row in rows if row['hash_original']}
        except Exception as e:
            logger.error(f"Error obteniendo hashes: {e}")
            return set()

    async def update_turno(self, turno_id: int, turno: TurnoCreate) -> bool:
        """Actualiza configuración y recrea los días"""
        try:
            # 1. Update Padre
            sql_update = """
                UPDATE turnos SET
                    nombre=?, tipo_programacion=?, meta_horas_semanales=?,
                    tolerancia_retraso_alerta=?, tolerancia_retraso_descuento=?,
                    redondeo_minutos=?, descuento_colacion_auto=?, minutos_colacion_auto=?, umbral_horas_colacion=?, es_turno_cortado=?,
                    anclaje_entrada_minutos=?, anclaje_salida_minutos=?, hora_limite_ficticia=?,
                    ventana_en_curso_minutos=?, tolerancia_exceso_colacion_minutos=?,
                    turno_padre_id=?, fecha_vigencia=?
                WHERE id=?
            """
            params = (
                turno.nombre, turno.tipo_programacion, turno.meta_horas_semanales,
                turno.tolerancia_retraso_alerta, turno.tolerancia_retraso_descuento,
                turno.redondeo_minutos, 1 if turno.descuento_colacion_auto else 0, turno.minutos_colacion_auto, turno.umbral_horas_colacion, turno.es_turno_cortado,
                turno.anclaje_entrada_minutos, turno.anclaje_salida_minutos, turno.hora_limite_ficticia,
                turno.ventana_en_curso_minutos, turno.tolerancia_exceso_colacion_minutos,
                turno.turno_padre_id, turno.fecha_vigencia,
                turno_id
            )
            await self.db.execute(sql_update, params)
            
            # 1.5 Update turno_areas
            await self.db.execute("DELETE FROM turno_areas WHERE turno_id = ?", (turno_id,))
            if turno.areas:
                for area_name in turno.areas:
                    await self.db.execute("INSERT OR IGNORE INTO turno_areas (turno_id, area_id) SELECT ?, id FROM areas WHERE nombre = ?", (turno_id, area_name))
            
            
            # 2. Recrear Días
            # Borrar anteriores
            await self.db.execute("DELETE FROM turno_dias WHERE turno_id = ?", (turno_id,))
            
            # Insertar nuevos
            sql_dia = """
                INSERT INTO turno_dias (
                    turno_id, dia_semana, num_semana, es_libre, horas_teoricas,
                    hora_entrada, hora_salida, cruza_medianoche, 
                    hora_entrada_2, hora_salida_2, cruza_medianoche_2, etiqueta_bloque
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            for dia in turno.dias:
                p_dia = (
                    turno_id, dia.dia_semana, dia.num_semana, dia.es_libre, dia.horas_teoricas,
                    dia.hora_entrada, dia.hora_salida, dia.cruza_medianoche,
                    dia.hora_entrada_2, dia.hora_salida_2, dia.cruza_medianoche_2, dia.etiqueta_bloque
                )
                await self.db.execute(sql_dia, p_dia)

            return True
            
        except Exception as e:
            logger.error(f"Error actualizando turno {turno_id}: {e}")
            raise
