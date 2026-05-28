import json
import hashlib
import secrets
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from loguru import logger
import jwt

from backend.core.database import Database
from backend.schemas.auth import (
    UsuarioCreate, UsuarioUpdate, UsuarioResponse,
    RolCreate, RolResponse, PermisoResponse
)

from backend.core.config import settings

# ELIMINADO: SECRET_KEY y ALGORITHM hardcoded. Ahora se usan desde settings.

class SeguridadRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_password_hash(self, password: str) -> str:
        """Hashing ultra-estable usando hashlib (Sin dependencias nativas volátiles)"""
        salt = secrets.token_hex(16)
        hash_obj = hashlib.sha256(f"{salt}{password}".encode('utf-8'))
        return f"{salt}${hash_obj.hexdigest()}"

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        try:
            if not hashed_password or "$" not in hashed_password:
                return False
            salt, stored_hash = hashed_password.split("$")
            hash_obj = hashlib.sha256(f"{salt}{plain_password}".encode('utf-8'))
            return secrets.compare_digest(hash_obj.hexdigest(), stored_hash)
        except Exception as e:
            logger.error(f"Error verificando password (Hashlib): {e}")
            return False

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=1440)  # 24 horas por defecto
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt

    async def init_tables(self):
        """Inicializar tablas de seguridad e Inyectar la Semilla (God Mode)"""
        
        # 1. Tabla Permisos
        if not await self.db.table_exists("permisos"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS permisos (
                    id TEXT PRIMARY KEY, -- ej: empleados.ver
                    modulo TEXT NOT NULL, -- ej: Empleados
                    descripcion TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        # 2. Tabla Roles
        if not await self.db.table_exists("roles"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL UNIQUE,
                    descripcion TEXT,
                    alcance_global INTEGER DEFAULT 0, -- 1=Ve todo, 0=Filtro por área
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        # 3. Tabla Relacional Rol_Permisos
        if not await self.db.table_exists("rol_permisos"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS rol_permisos (
                    rol_id INTEGER NOT NULL,
                    permiso_id TEXT NOT NULL,
                    PRIMARY KEY (rol_id, permiso_id),
                    FOREIGN KEY (rol_id) REFERENCES roles (id) ON DELETE CASCADE,
                    FOREIGN KEY (permiso_id) REFERENCES permisos (id) ON DELETE CASCADE
                )
            """)

        # 4. Tabla Usuarios
        if not await self.db.table_exists("usuarios"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    email TEXT,
                    activo INTEGER DEFAULT 1,
                    rol_id INTEGER NOT NULL,
                    areas_json TEXT, -- Lista JSON de áreas permitidas si no es alcance global
                    ultimo_acceso TIMESTAMP,
                    is_superuser INTEGER DEFAULT 0, -- BANDERA GOD MODE
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (rol_id) REFERENCES roles (id)
                )
            """)

        # 5. Tabla Logs Auditoría
        if not await self.db.table_exists("logs_auditoria"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS logs_auditoria (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER,
                    username TEXT,
                    accion TEXT NOT NULL, -- CREATE, UPDATE, DELETE, LOGIN, EXPORT
                    modulo TEXT NOT NULL,
                    detalle TEXT, -- JSON del cambio
                    ip_address TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        # 6. Tabla Sync Logs (Auditoría de Sincronización BioAlba)
        if not await self.db.table_exists("sync_logs"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS sync_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_inicio TEXT NOT NULL,
                    fecha_fin TEXT,
                    tipo_sync TEXT DEFAULT 'COMPLETA',
                    marcaciones_nuevas INTEGER DEFAULT 0,
                    dias_recalculados INTEGER DEFAULT 0,
                    errores INTEGER DEFAULT 0,
                    duracion_segundos REAL DEFAULT 0,
                    detalle_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        await self._inyectar_semilla_seguridad()

    async def _inyectar_semilla_seguridad(self):
        """
        Siembra permisos base, rol Super Administrador y usuario admin si no existen.

        OPTIMIZACIÓN: usa COUNT(*) primero para evitar ~60 queries individuales
        en cada arranque normal. Solo ejecuta los loops cuando el conteo no coincide
        (nuevo permiso agregado al código o primer arranque).

        Costo arranque normal  → 3-4 SELECT COUNT (más barato imposible)
        Costo primer arranque  → loop completo de inserts (solo ocurre 1 vez)
        """
        try:
            permisos_base = [
                # ── Empleados (7 permisos) ──
                ('empleados.ver',                'Empleados',      'Ver la lista general de empleados, cumpleaños y turnos asignados (Lectura)'),
                ('empleados.crear',              'Empleados',      'Crear nuevos empleados (Botón "+ Nuevo Empleado")'),
                ('empleados.editar',             'Empleados',      'Editar ficha personal, renovar/gestionar contratos y registrar bajas (desactivaciones)'),
                ('empleados.eliminar',           'Empleados',      'Eliminar de forma permanente empleados y su historial (Icono papelera roja)'),
                ('empleados.reincorporar',       'Empleados',      'Reincorporar y reactivar empleados inactivos (Asistente con BioAlba)'),
                ('empleados.bonos',              'Empleados',      'Ver matriz informativa de bonos asignados (Lectura)'),
                ('empleados.horarios',           'Empleados',      'Asignación masiva/individual de turnos y corrección de fecha inicial'),

                # ── Marcaciones (7 permisos) ──
                ('marcaciones.ver',              'Marcaciones',    'Ver la grilla de asistencia, calendarios y filtros'),
                ('marcaciones.editar',           'Marcaciones',    'Editar horas de entrada/salida, relleno masivo, tramos, perdonazo'),
                ('marcaciones.justificar',       'Marcaciones',    'Doble-clic en celda de estado -> crear/editar justificación'),
                ('marcaciones.horas_extras',     'Marcaciones',    'Modal de aprobación masiva -> aprobar/rechazar horas extras'),
                ('marcaciones.cierre_periodo',   'Marcaciones',    'Botón "Cerrar Período" -> sellar mes para liquidación'),
                ('marcaciones.bypass_cierre',    'Marcaciones',    'Desbloquear edición de meses ya cerrados (alto riesgo)'),
                ('marcaciones.sincronizar',      'Marcaciones',    'Botón "Sincronizar" en toolbar -> descargar marcaciones y reprocesar'),
                ('marcaciones.intercambio',      'Marcaciones',    'Registrar y revertir intercambios de días (Días Compensatorios)'),
                ('marcaciones.compensar',        'Marcaciones',    'Compensar inasistencias usando horas extras aprobadas'),


                # ── Reportes (4 permisos) ──
                ('reportes.ver',                 'Reportes',       'Ver tablas de reporte, gráficos de línea y filtros de período'),
                ('reportes.exportar',            'Reportes',       'Botón "Descargar Excel" -> exportar reporte consolidado'),
                ('reportes.reprocesar',          'Reportes',       'Botón "Reprocesar" -> disparar motor de cálculo desde reportes'),
                ('reportes.sincronizar',         'Reportes',       'Botón "Sincronizar" -> descargar marcaciones desde reportes'),

                # ── Configuración (10 permisos) ──
                ('configuracion.ver',            'Configuración',  'Acceso de solo lectura a todas las pestañas de configuración'),
                ('configuracion.horarios',       'Configuración',  'Pestaña Horarios -> crear, editar y eliminar turnos'),
                ('configuracion.bonos',          'Configuración',  'Pestaña Bonos -> crear, editar y eliminar bonos y pagadores'),
                ('configuracion.justificaciones','Configuración',  'Pestaña Justificaciones -> crear, editar y eliminar tipos'),
                ('configuracion.calendario',     'Configuración',  'Pestaña Calendario -> gestionar feriados'),
                ('configuracion.correo',         'Configuración',  'Pestaña Correo -> configurar SMTP y notificaciones por área'),
                ('configuracion.estados',        'Configuración',  'Pestaña Estados -> editar estados de asistencia'),
                ('configuracion.seguridad',      'Configuración',  'Pestaña Seguridad -> gestionar usuarios, roles y ver auditoría'),
                ('configuracion.wizard',         'Configuración',  'Botón "Empleados" del header -> Wizard de inicialización BioAlba'),
                ('configuracion.sistema',        'Configuración',  'Pestaña Sistema -> diagnóstico de BD y modo de conexión'),
            ]

            total_esperado = len(permisos_base)

            # ── 1. PERMISOS: 1 COUNT en vez de 29 SELECT individuales ────────────
            cnt_permisos = await self.db.fetch_one("SELECT COUNT(*) as c FROM permisos")
            cnt_permisos_bd = cnt_permisos['c'] if cnt_permisos else 0

            if cnt_permisos_bd < total_esperado:
                # Faltan permisos → primer arranque o nuevo permiso agregado al código
                nuevos_permisos = 0
                for perm_id, modulo, descripcion in permisos_base:
                    exists = await self.db.fetch_one("SELECT id FROM permisos WHERE id = ?", (perm_id,))
                    if not exists:
                        await self.db.execute(
                            "INSERT INTO permisos (id, modulo, descripcion) VALUES (?, ?, ?)",
                            (perm_id, modulo, descripcion)
                        )
                        nuevos_permisos += 1
                logger.info(f"✨ {nuevos_permisos} nuevo(s) permiso(s) base inyectado(s)")
            else:
                logger.debug(f"☑️  [Seguridad] Permisos OK ({cnt_permisos_bd}/{total_esperado}) — sin cambios")

            # 2. Sembrar el Rol base si la tabla está vacía
            count_r = await self.db.fetch_one("SELECT COUNT(*) as c FROM roles")
            if count_r and count_r['c'] == 0:
                await self.db.execute(
                    "INSERT INTO roles (id, nombre, descripcion, alcance_global) VALUES (?, ?, ?, ?)",
                    (1, 'Super Administrador', 'Control total del sistema. Ve y hace todo sin restricciones. Único acceso a la consola de seguridad para crear usuarios y modificar roles.', 1)
                )
                logger.info("✨ Rol 'Super Administrador' inyectado")

            # ── 3. ROL_PERMISOS: 1 COUNT en vez de 29 SELECT individuales ────────
            rol1_exists = await self.db.fetch_one("SELECT 1 FROM roles WHERE id = 1")
            if rol1_exists:
                cnt_rp = await self.db.fetch_one(
                    "SELECT COUNT(*) as c FROM rol_permisos WHERE rol_id = 1"
                )
                cnt_rp_bd = cnt_rp['c'] if cnt_rp else 0

                if cnt_rp_bd < total_esperado:
                    # Faltan asignaciones → primer arranque o permiso nuevo
                    rol1_perms_agregados = 0
                    for perm_id, _, _ in permisos_base:
                        exists_rp = await self.db.fetch_one(
                            "SELECT 1 FROM rol_permisos WHERE rol_id = 1 AND permiso_id = ?",
                            (perm_id,)
                        )
                        if not exists_rp:
                            await self.db.execute(
                                "INSERT INTO rol_permisos (rol_id, permiso_id) VALUES (1, ?)",
                                (perm_id,)
                            )
                            rol1_perms_agregados += 1
                    logger.info(f"✨ {rol1_perms_agregados} permiso(s) asignado(s) al Rol 1 (Super Administrador)")
                else:
                    logger.debug(f"☑️  [Seguridad] Rol 1 permisos OK ({cnt_rp_bd}/{total_esperado}) — sin cambios")

            # ── 4. USUARIO ADMIN: 1 SELECT (ya era eficiente) ────────────────
            user_exists = await self.db.fetch_one("SELECT COUNT(*) as c FROM usuarios WHERE id = 9")
            if user_exists and user_exists['c'] == 0:
                hashed_pw = self.get_password_hash("aguacol2026")
                await self.db.execute("""
                    INSERT INTO usuarios (id, username, password_hash, nombre_completo, email, activo, rol_id, is_superuser, areas_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (9, "admin", hashed_pw, "Súper Admin Creador", "admin@aguacol.cl", 1, 1, 1, "[]"))
                logger.warning("🚨 GOD MODE Activado: Usuario 'admin' (ID: 9) creado exitosamente con privilegios máximos.")
        
        except Exception as e:
            logger.error(f"Error inyectando semilla de seguridad: {e}")

    # --- Operaciones CRUD Básicas (Base para Routers) ---
    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        query = """
            SELECT u.*, r.nombre as rol_nombre, r.alcance_global 
            FROM usuarios u 
            JOIN roles r ON u.rol_id = r.id 
            WHERE u.username = ?
        """
        return await self.db.fetch_one(query, (username,))

    async def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Obtiene un usuario por su ID primario"""
        return await self.db.fetch_one("SELECT * FROM usuarios WHERE id = ?", (user_id,))

    async def get_rol_by_id(self, rol_id: int) -> Optional[Dict]:
        """Obtiene detalles de un Rol por su ID"""
        return await self.db.fetch_one("SELECT * FROM roles WHERE id = ?", (rol_id,))

    async def log_auditoria(self, usuario_id: int, username: str, accion: str, modulo: str, detalle: str = None, ip: str = None):
        """Guarda un registro inmutable en auditoría"""
        query = """
            INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle, ip_address)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        await self.db.execute(query, (usuario_id, username, accion, modulo, detalle, ip))

    async def get_permissions_for_role(self, rol_id: int) -> List[str]:
        query = "SELECT permiso_id FROM rol_permisos WHERE rol_id = ?"
        rows = await self.db.fetch_all(query, (rol_id,))
        return [r['permiso_id'] for r in rows]

    # --- Gestión Avanzada (Dashboard y Consola) ---
    async def get_all_roles(self) -> List[Dict]:
        query = "SELECT * FROM roles ORDER BY id ASC"
        return await self.db.fetch_all(query)

    async def get_all_permisos(self) -> List[Dict]:
        query = "SELECT * FROM permisos ORDER BY modulo, id"
        return await self.db.fetch_all(query)

    async def create_rol(self, nombre: str, descripcion: str, alcance_global: int, permisos: List[str]) -> int:
        query_rol = "INSERT INTO roles (nombre, descripcion, alcance_global) VALUES (?, ?, ?)"
        cursor = await self.db.execute(query_rol, (nombre, descripcion, alcance_global))
        rol_id = cursor.lastrowid
        
        if permisos:
            permisos_data = [(rol_id, p) for p in permisos]
            await self.db.executemany("INSERT INTO rol_permisos (rol_id, permiso_id) VALUES (?, ?)", permisos_data)
            
        return rol_id

    async def update_rol(self, rol_id: int, nombre: str, descripcion: str, alcance_global: int, permisos: List[str]):
        query_rol = "UPDATE roles SET nombre = ?, descripcion = ?, alcance_global = ? WHERE id = ?"
        await self.db.execute(query_rol, (nombre, descripcion, alcance_global, rol_id))
        
        # Recrear permisos
        await self.db.execute("DELETE FROM rol_permisos WHERE rol_id = ?", (rol_id,))
        
        if permisos:
            permisos_data = [(rol_id, p) for p in permisos]
            await self.db.executemany("INSERT INTO rol_permisos (rol_id, permiso_id) VALUES (?, ?)", permisos_data)

    async def get_all_usuarios(self) -> List[Dict]:
        query = """
            SELECT u.id, u.username, u.nombre_completo, u.email, u.activo,
                   u.rol_id, r.nombre as rol_nombre, r.alcance_global, 
                   u.areas_json, u.ultimo_acceso, u.is_superuser
            FROM usuarios u
            JOIN roles r ON u.rol_id = r.id
            ORDER BY u.id DESC
        """
        return await self.db.fetch_all(query)

    async def create_user(self, user: UsuarioCreate) -> int:
        hashed_pw = self.get_password_hash(user.password)
        areas_str = json.dumps(user.areas) if user.areas else "[]"
        
        query = """
            INSERT INTO usuarios (username, password_hash, nombre_completo, email, activo, rol_id, areas_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        cursor = await self.db.execute(
            query, 
            (user.username, hashed_pw, user.nombre_completo, user.email, 
             int(user.activo), user.rol_id, areas_str)
        )
        return cursor.lastrowid

    async def update_user(self, user_id: int, user: UsuarioUpdate):
        updates = []
        params = []
        
        if user.nombre_completo is not None:
            updates.append("nombre_completo = ?")
            params.append(user.nombre_completo)
        if user.email is not None:
            updates.append("email = ?")
            params.append(user.email)
        if user.activo is not None:
            updates.append("activo = ?")
            params.append(int(user.activo))
        if user.rol_id is not None:
            updates.append("rol_id = ?")
            params.append(user.rol_id)
        if user.password:
            updates.append("password_hash = ?")
            params.append(self.get_password_hash(user.password))
        if user.areas is not None:
            updates.append("areas_json = ?")
            params.append(json.dumps(user.areas))
            
        if not updates:
            return
            
        query = f"UPDATE usuarios SET {', '.join(updates)} WHERE id = ?"
        params.append(user_id)
        
        await self.db.execute(query, tuple(params))

    async def get_auditoria(self, limit: int = 100, skip: int = 0) -> List[Dict]:
        query = """
            SELECT * FROM logs_auditoria 
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        return await self.db.fetch_all(query, (limit, skip))

    async def count_auditoria(self) -> int:
        row = await self.db.fetch_one("SELECT COUNT(*) as c FROM logs_auditoria")
        return row['c'] if row else 0

    async def check_role_in_use(self, rol_id: int) -> bool:
        """Verifica si algún usuario tiene asignado este rol"""
        row = await self.db.fetch_one("SELECT COUNT(*) as c FROM usuarios WHERE rol_id = ?", (rol_id,))
        return row and row['c'] > 0

    async def delete_rol(self, rol_id: int):
        """Elimina un rol y sus asociaciones de permisos de forma definitiva"""
        await self.db.execute("DELETE FROM rol_permisos WHERE rol_id = ?", (rol_id,))
        await self.db.execute("DELETE FROM roles WHERE id = ?", (rol_id,))
