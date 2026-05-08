"""
Hybrid Database - Native Turso Embedded Replicas
Usa el SDK oficial 'libsql' para sincronización nativa de bajo nivel (Frames).
"""

import libsql
import asyncio
import os
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
from contextlib import asynccontextmanager
from pathlib import Path
from loguru import logger
from datetime import datetime, date

from .config import settings


class HybridDatabase:
    """
    Database híbrida usando Turso LibSQL Native SDK:
    - READS: De SQLite local (Embedded Replica) con latencia microsegundo.
    - WRITES: Al Primary (Cloud). El SDK se encarga del ruteo.
    - SYNC: Nativo vía conn.sync() usando la cuota de 'Sincronizaciones'.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        # Rutas de DB Local
        if db_path:
            self.db_path = Path(db_path)
        elif getattr(sys, 'frozen', False):
            appdata = os.environ.get('LOCALAPPDATA', os.environ.get('APPDATA', os.path.expanduser("~")))
            self.db_path = Path(appdata) / "Aguacol_Asistencia" / "data" / "local_db" / "asistencia_local.db"
        else:
            self.db_path = Path(settings.LOCAL_DB_PATH)
            
        self.conn: Optional[libsql.Connection] = None
        
        # Turso Config
        self.use_turso = bool(
            settings.TURSO_DATABASE_URL and 
            ("libsql" in settings.TURSO_DATABASE_URL or "turso.io" in settings.TURSO_DATABASE_URL)
        )
        self.turso_url = settings.TURSO_DATABASE_URL
        self.turso_token = settings.TURSO_AUTH_TOKEN
        
        self._connected: bool = False
        self._last_sync: Optional[datetime] = None
        self._force_turso_only = False
        self._schema_cache: Dict[str, List[str]] = {}  # Caché para migraciones rápidas
        self._in_transaction: bool = False  # Control de transacciones para batching
        self._reset_lock = asyncio.Lock()
        # Lock para serializar acceso concurrente al objeto self.conn.
        # libsql (Rust) no es thread-safe para acceso simultáneo desde múltiples threads.
        # El scheduler (sync) y los requests HTTP comparten self.conn → Race Condition → WalConflict.
        # Este lock garantiza que solo una operación de escritura/sync accede a conn a la vez.
        # IMPORTANTE: Las lecturas (SELECT) también se serializan porque libsql embedded replica
        # hace auto-sync interno en cualquier cursor.execute(), incluyendo SELECT.
        self._db_lock = asyncio.Lock()
        # Semáforo para serializar syncs a Turso Cloud.
        # execute_batch dispara fire-and-forget _push_to_cloud() en cada batch.
        # Sin control, 49 batches simultáneos = 49 conn.sync() = 429 Too Many Requests.
        # Con _sync_lock: solo 1 sync activo a la vez.
        # Con _sync_pending: si ya hay uno corriendo, el nuevo se descarta (el scheduler
        # lo reintentará en 30s, los datos están seguros en WAL local).
        self._sync_lock = asyncio.Lock()
        self._sync_pending: bool = False
        
    async def connect(self, retry: bool = True) -> None:
        """Establece la conexión nativa con Turso (Embedded Replica o Remote)"""
        if self._connected:
            return
            
        async with self._reset_lock:
            if self._connected:
                return
            await self._connect_locked(retry)
            
    async def _connect_locked(self, retry: bool = True) -> None:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
            if self._force_turso_only and self.use_turso:
                logger.warning("🚀 MODO NUBE PURA: Conectando directamente a Turso Cloud (Sin Réplica Local)")
                self.conn = await asyncio.to_thread(
                    libsql.connect, 
                    database=self.turso_url, 
                    auth_token=self.turso_token
                )
            else:
                logger.info(f"🔌 Conectando a Embedded Replica: {self.db_path}")
                try:
                    # Timeout 15s: evita colgar el inicio si Turso Cloud no responde rápido.
                    self.conn = await asyncio.wait_for(
                        asyncio.to_thread(
                            libsql.connect,
                            database=str(self.db_path),
                            sync_url=self.turso_url,
                            auth_token=self.turso_token,
                            # SIN sync_interval: elimina el hilo Rust en background.
                            # RAZÓN: sync_interval lanzaba un hilo Rust paralelo que competía
                            # con APScheduler y execute_batch() sobre los mismos archivos WAL,
                            # causando Frame Mismatch y WinError 32 en Windows.
                            # El ÚNICO actor de sync ahora es el APScheduler (cada 300s) y
                            # execute_batch() al final de cada batch de importación.
                            # Benchmark de escrituras con offline=True: 72,000ms → 1ms (sin cambio).
                            offline=True,   # OFFLINE WRITES: commit() = fsync local puro (~1ms).
                        ),
                        timeout=15.0
                    )
                    logger.info("🔄 Conexión establecida con Turso Cloud (offline=True, sync manual vía APScheduler)")

                except asyncio.TimeoutError:
                    logger.warning("⏱️ Timeout de 15s al conectar con Turso Cloud. Entrando en modo LOCAL OFFLINE puro para evitar bloqueos.")
                    # Fallback puro a SQLite local (Réplica)
                    self.conn = await asyncio.to_thread(
                        libsql.connect,
                        database=str(self.db_path)
                    )
                    self.use_turso = False
                except Exception as e:
                    err_msg = str(e).lower()
                    if (("invalid local state" in err_msg or "malformed" in err_msg or "local state is incorrect" in err_msg) and retry):
                        logger.warning(f"🩹 Estado local inconsistente detectado. Eliminando DB local para re-sincronizar desde cloud...")
                        # Liberar handles residuales en Python/Rust y esperar a que el OS desbloquee el archivo
                        import gc
                        gc.collect()
                        await asyncio.sleep(1.0)
                        
                        # soft_only=False: borrar .db + aux. El servidor re-sincronizará
                        # desde cloud (ya purgado).
                        success = await self._cleanup_local_db_files(soft_only=False)
                        if not success:
                            logger.critical("🛑 Falló el cleanup del archivo DB principal (bloqueado). Abortando reconexión.")
                            raise e
                        
                        return await self._connect_locked(retry=False)
                    raise e

            self._connected = True
            
            # PRAGMAs de resiliencia y performance post-conexión
            try:
                def _apply_pragmas():
                    cursor = self.conn.cursor()
                    # Resiliencia
                    cursor.execute("PRAGMA busy_timeout = 5000")   # 5s espera ante SQLITE_BUSY
                    cursor.execute("PRAGMA journal_mode = WAL")    # WAL: lecturas concurrentes
                    # PRAGMAs de performance (guía SQLite Forum + docs Turso Embedded Replica):
                    cursor.execute("PRAGMA synchronous = NORMAL")  # WAL-safe: ahorra fsync
                    # FULL (defecto): fsync en cada commit → lento en WAL mode
                    # NORMAL: solo fsync en checkpoints → seguro porque WAL garantiza integridad
                    cursor.execute("PRAGMA cache_size = -32000")   # 32MB page cache en RAM
                    # Reduce I/O al leer las mismas páginas repetidamente (reproceso histórico)
                    cursor.execute("PRAGMA temp_store = MEMORY")   # tablas temporales en RAM
                    # Beneficia ORDER BY, GROUP BY y subconsultas de asistencias_service
                    cursor.execute("PRAGMA mmap_size = 134217728") # 128MB memory-mapped I/O
                    # Mapea el archivo DB al espacio virtual: elimina syscalls read() por página
                    # Impacto principal: lecturas del reproceso histórico (110 días × consultas)
                self._pragma_applied = True
                await asyncio.to_thread(_apply_pragmas)
                logger.debug("🛡️ PRAGMAs aplicados (busy_timeout=5000, WAL, sync=NORMAL, cache=32MB, mmap=128MB)")
            except Exception as pragma_err:
                logger.warning(f"⚠️ PRAGMAs no aplicados (no crítico en modo Cloud): {pragma_err}")

            # Sync post-conexión en BACKGROUND: no bloqueamos el arranque.
            # La réplica local ya tiene datos válidos (libsql los mantiene).
            # El sync trae cambios de Turso Cloud desde la última vez, pero
            # no es urgente — el scheduler lo repetirá cada 90s de todas formas.
            if hasattr(self.conn, 'sync') and not self._force_turso_only:
                async def _bg_initial_sync():
                    try:
                        await asyncio.wait_for(
                            asyncio.to_thread(self.conn.sync),
                            timeout=30.0
                        )
                        self._last_sync = datetime.now()
                        logger.info("☁️ Sync inicial completado en background (réplica actualizada)")
                    except asyncio.TimeoutError:
                        logger.warning("⚠️ Sync inicial timeout (>30s) — continuando con datos locales")
                    except Exception as sync_err:
                        logger.warning(f"⚠️ Sync inicial falló (no crítico): {sync_err}")
                # Guardar referencia: evita que el GC destruya la tarea antes de completarse
                self._bg_sync_task = asyncio.create_task(_bg_initial_sync())

            logger.success(f"✅ Motor LibSQL conectado (Modo: {'Cloud' if self._force_turso_only else 'Hybrid'})")

        except Exception as e:
            if "maximum recursion depth exceeded" in str(e).lower():
                logger.critical("🛑 Error de recursión crítica en conexión. Abortando para evitar crash.")
                self._connected = False
                return
            logger.error(f"❌ Error de conexión LibSQL: {e}")
            raise


    async def reset_local_db(self):
        """Desconecta, limpia archivos locales y reconecta con control de concurrencia"""
        async with self._reset_lock:
            logger.warning("🔄 Iniciando proceso de RESET de base de datos local...")
            
            if self._connected and self.conn:
                try:
                    await asyncio.to_thread(self.conn.close)
                except Exception:
                    pass
                self.conn = None
                self._connected = False
                import gc
                gc.collect()
                await asyncio.sleep(1.0)
            
            await self._cleanup_local_db_files(soft_only=False)  # Full reset: borra todo
            await asyncio.sleep(0.5)
            await self._connect_locked()
            logger.success("✅ Reset local completado — reconectado desde Turso Cloud")

    async def _cleanup_local_db_files(self, soft_only: bool = True) -> bool:
        """
        Limpia archivos de réplica local.
        
        soft_only=True (DEFAULT):  Solo archivos AUXILIARES (-wal, -shm, -info, .meta).
                                    NUNCA toca el archivo .db principal.
                                    Usar en recuperación de inconsistencias en connect().
        
        soft_only=False:           Limpieza total (incluye .db).
                                    Solo usar en reset_local_db() explícito.
        """
        import glob
        
        local_dir = str(self.db_path.parent)
        base = str(self.db_path)
        
        # Archivos auxiliares: siempre seguros de borrar (EXCEPTO .meta)
        aux_patterns = [
            base + "-wal",
            base + "-shm",
            base + "-info",
        ]
        
        meta_pattern = base + ".meta"
        
        deleted = 0
        
        if not soft_only:
            logger.warning("🗑️ Cleanup FULL: intentando eliminar .db + aux files")
            # CRÍTICO: Si no podemos eliminar/renombrar .db, NO debemos eliminar .meta
            if os.path.exists(base):
                db_deleted = False
                try:
                    os.remove(base)
                    deleted += 1
                    logger.debug(f"🗑️ Eliminado: {os.path.basename(base)}")
                    db_deleted = True
                except PermissionError:
                    corrupt_name = base + f".corrupt_{int(datetime.now().timestamp())}"
                    try:
                        os.rename(base, corrupt_name)
                        deleted += 1
                        logger.warning(f"🩹 Archivo bloqueado, movido a: {os.path.basename(corrupt_name)}")
                        db_deleted = True
                    except Exception as e2:
                        logger.error(f"🚨 Error crítico limpiando {os.path.basename(base)}: {e2}")
                        logger.critical("🛑 Abortando cleanup para NO desincronizar .db y .meta!")
                        return False # Abortar limpieza para no romper la DB
                
                # Si falló por otra razón y no está marcado como eliminado
                if not db_deleted and os.path.exists(base):
                    logger.critical("🛑 No se pudo eliminar .db. Abortando cleanup.")
                    return False
            
            patterns = aux_patterns + [meta_pattern]
        else:
            logger.debug("🧹 Cleanup SOFT: solo -wal/-shm/-info (DB y .meta preservados)")
            patterns = aux_patterns
            
        # Archivos corrupt_* siempre elegibles
        corrupt_pattern = os.path.join(local_dir, "*.corrupt_*")
        patterns.extend(glob.glob(corrupt_pattern))
        
        for f in patterns:
            if os.path.exists(f):
                try:
                    os.remove(f)
                    deleted += 1
                    logger.debug(f"🗑️ Eliminado: {os.path.basename(f)}")
                except PermissionError:
                    corrupt_name = f + f".corrupt_{int(datetime.now().timestamp())}"
                    try:
                        os.rename(f, corrupt_name)
                        deleted += 1
                        logger.warning(f"🩹 Archivo bloqueado, movido a: {os.path.basename(corrupt_name)}")
                    except Exception as e2:
                        logger.error(f"🚨 Error crítico limpiando {os.path.basename(f)}: {e2}")
        
        if deleted:
            logger.info(f"🧹 Cleanup: {deleted} archivo(s) eliminados (soft={soft_only})")
        return True

    async def _load_persistence_before_connect(self):
        """Intenta leer el modo de operación de la DB local antes de conectar el nuevo motor.
        NOTA: No usa sqlite3 directo porque corrompe el LIBSQL_WAL del archivo .db.
        El modo de operación se leerá después del connect() si es necesario.
        """
        # Modo legacy de leer ajustes eliminado — sqlite3 + libsql WAL son incompatibles.
        # Si se necesita forzar cloud-only, hacerlo via variable de entorno o config.
        pass

    async def _save_persistence_locally(self, clave: str, valor: str):
        """Guarda un ajuste en la DB usando la conexión libsql ya abierta.
        NUNCA usa sqlite3 directo — incompatible con LIBSQL_WAL."""
        try:
            if not self._connected or not self.conn:
                logger.warning(f"⚠️ No hay conexión activa para persistir ajuste {clave}")
                return
            await self.execute(
                "INSERT OR REPLACE INTO ajustes (clave, valor) VALUES (?, ?)",
                (clave, str(valor))
            )
            logger.debug(f"💾 Ajuste local persistido: {clave}={valor}")
        except Exception as e:
            logger.error(f"⚠️ No se pudo persistir ajuste local {clave}: {e}")

    async def disconnect(self) -> None:
        """Cerrar conexiones con sync final para persistir datos en Cloud"""
        if not self._connected or not self.conn:
            return

        # Sync final: empujar cualquier escritura pendiente a Turso Cloud
        # ANTES de cerrar la conexión. Esto asegura que los datos locales
        # (en WAL) se repliquen al Cloud y no se pierdan si algo externo
        # limpia los archivos WAL antes del próximo startup.
        if self.sync_supported:
            try:
                await asyncio.to_thread(self.conn.sync)
                logger.info("🔄 Sync final completado (datos locales empujados a Cloud)")
            except Exception as sync_err:
                logger.warning(f"⚠️ Sync final falló: {sync_err} (datos podrían estar solo en WAL local)")

        try:
            await asyncio.to_thread(self.conn.close)
        except Exception:
            pass  # Ignorar errores al cerrar
        self.conn = None
        self._connected = False
        # Forzar liberación de handles del Rust backend en Windows
        import gc
        gc.collect()
        await asyncio.sleep(0.5)
        logger.info("👋 Motor LibSQL desconectado")

    def _is_wal_conflict(self, e: Exception) -> bool:
        """Detecta WAL conflicts de Turso Cloud (datos locales OK, sync pendiente)"""
        msg = str(e).lower()
        return "walconflict" in msg or "wal frame" in msg

    def _is_stream_error(self, e: Exception) -> bool:
        """Detecta errores de stream expirado de Turso Cloud (Hrana 404 stream not found).
        Estos streams son cerrados por el servidor tras inactividad; la reconexión
        debe ser inmediata — no tiene sentido esperar si el stream ya está muerto."""
        msg = str(e).lower()
        return "stream not found" in msg or "status=404" in msg

    def _is_reconnect_error(self, e: Exception) -> bool:
        """Determina si un error requiere cerrar y volver a abrir la conexión o un reset"""
        msg = str(e).lower()
        reconnect_triggers = [
            "panic", "unwrap", "none", "libsql error",
            "stream not found", "404", "status=404",
            "connection closed", "broken pipe", "malformed",
            "database disk image is malformed",
            "10054", "connection error", "dispatch error",
            "sync error", "connection reset", "host remoto",
            "walconflict", "wal frame"
        ]
        return any(trigger in msg for trigger in reconnect_triggers)

    def _row_to_dict(self, cursor, row) -> Dict[str, Any]:
        """Convierte una fila de LibSQL a diccionario"""
        if row is None: return None
        d = {}
        for i, col in enumerate(cursor.description):
            d[col[0]] = row[i]
        return d

    @asynccontextmanager
    async def transaction(self):
        """Context manager para agrupar operaciones en una transacción atómica"""
        if not self._connected:
            await self.connect()
        
        was_in_transaction = self._in_transaction
        self._in_transaction = True
        try:
            def _begin():
                self.conn.cursor().execute("BEGIN")
            
            await asyncio.to_thread(_begin)
            yield self
            
            def _commit():
                try:
                    self.conn.commit()
                except Exception as commit_err:
                    err_msg = str(commit_err).lower()
                    if "walconflict" in err_msg or "wal frame" in err_msg:
                        logger.warning(f"⚠️ WAL Conflict en commit (datos locales OK, sync pendiente): {commit_err}")
                        return  # No re-raise — datos locales están a salvo
                    raise
            
            await asyncio.to_thread(_commit)
            
        except Exception as e:
            def _rollback():
                try:
                    self.conn.cursor().execute("ROLLBACK")
                except Exception:
                    pass
            await asyncio.to_thread(_rollback)
            raise e
        finally:
            self._in_transaction = was_in_transaction

    async def execute(self, query: str, params: Optional[Union[tuple, list]] = None) -> Any:
        """Ejecuta query serializado por _db_lock para escrituras (reads son libres)."""
        if not self._connected:
            await self.connect()

        is_read = query.strip().upper().startswith(("SELECT", "PRAGMA"))
        max_retries = 3
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                def _do_execute():
                    try:
                        if self.conn is None:
                            raise Exception("conn is None")
                        cursor = self.conn.cursor()
                        try:
                            cursor.execute(query, params or ())
                        except Exception as exec_err:
                            if self._is_wal_conflict(exec_err):
                                return cursor, "WAL_OK"
                            raise
                        if not self._in_transaction and not is_read:
                            try:
                                self.conn.commit()
                            except Exception as commit_err:
                                commit_msg = str(commit_err).lower()
                                if "walconflict" in commit_msg or "wal frame" in commit_msg:
                                    return cursor, "WAL_OK"
                                raise
                        return cursor, None
                    except Exception as inner_e:
                        if "malformed" in str(inner_e).lower() or "corrupt" in str(inner_e).lower():
                            logger.error(f"CORRUPTION in EXECUTE query: {query} with params: {params} -> {inner_e}")
                        if self._is_reconnect_error(inner_e):
                            return "RECONNECT", inner_e
                        raise inner_e
                    except BaseException as panic_e:
                        name = type(panic_e).__name__.lower()
                        if "panic" in name or "pyo3" in name:
                            return "RECONNECT", Exception(f"Rust Panic: {panic_e}")
                        raise panic_e

                # Lecturas: acceso directo (SQLite local es thread-safe para reads)
                # Escrituras: serializar con _db_lock para evitar race condition con scheduler
                if is_read:
                    status, error_obj = await asyncio.to_thread(_do_execute)
                else:
                    # Fase 1: Adquisición rápida del lock (máx 10s)
                    try:
                        async with asyncio.timeout(10):
                            await self._db_lock.acquire()
                    except asyncio.TimeoutError:
                        logger.warning(f"⏳ _db_lock timeout en EXECUTE (intento {attempt}/{max_retries}): {query[:60]}...")
                        last_error = asyncio.TimeoutError("db_lock timeout")
                        await asyncio.sleep(0.5)
                        continue

                    # Fase 2: Ejecución sin timeout — el commit a Cloud toma lo que necesite
                    try:
                        status, error_obj = await asyncio.to_thread(_do_execute)
                    finally:
                        self._db_lock.release()

                if status == "RECONNECT":
                    if error_obj and self._is_wal_conflict(error_obj):
                        logger.warning(f"⚠️ WAL residual post-lock en EXECUTE (retry {attempt}/{max_retries}): {query[:60]}...")
                        await asyncio.sleep(1)
                    elif error_obj and "malformed" in str(error_obj).lower():
                        logger.warning(f"🧹 Corrupción detectada en EXECUTE: {error_obj}. Resetting...")
                        await self.reset_local_db()
                    else:
                        logger.warning(f"🔄 EXECUTE retry {attempt}/{max_retries}: {error_obj}")
                        self._connected = False
                        # Stream expirado: reconectar inmediatamente (el stream ya está muerto)
                        # Otros errores de red: backoff corto antes de reintentar
                        if not self._is_stream_error(error_obj):
                            await asyncio.sleep(0.3)
                        await self.connect()
                    last_error = error_obj
                    continue

                if error_obj == "WAL_OK":
                    logger.warning(f"⚠️ WAL residual (local OK): {query[:60]}...")
                    return status

                return status

            except Exception as e:
                err_msg = str(e).lower()
                if "duplicate column name" in err_msg:
                    logger.debug(f"ℹ️ SQL: Columna ya existe (Ignorado) | Query: {query[:50]}...")
                    class DummyCursor:
                        def __init__(self): self.lastrowid = None
                        def fetchall(self): return []
                        def fetchone(self): return None
                        def close(self): pass
                    return DummyCursor()

                if self._is_wal_conflict(e):
                    logger.warning(f"⚠️ WAL residual outer (retry {attempt}/{max_retries}): {query[:60]}...")
                    await asyncio.sleep(1)
                    last_error = e
                    continue

                if self._is_reconnect_error(e) and attempt < max_retries:
                    logger.warning(f"🔄 EXECUTE retry {attempt}/{max_retries}: {e}")
                    self._connected = False
                    await asyncio.sleep(1)
                    await self.connect()
                    last_error = e
                    continue

                logger.error(f"❌ Error SQL: {e} | Query: {query} | Params: {params}")
                raise

        # Si agotamos reintentos
        if last_error and self._is_wal_conflict(last_error):
            logger.warning(f"⚠️ WAL persistente (no fatal, datos locales OK): {query[:60]}...")
            class DummyCursor:
                def __init__(self): self.lastrowid = None
                def fetchall(self): return []
                def fetchone(self): return None
                def close(self): pass
            return DummyCursor()

        logger.error(f"❌ EXECUTE falló tras {max_retries} reintentos | Query: {query[:80]}")
        if last_error:
            raise last_error

    async def fetch_all(self, query: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
        """Fetch all serializado con _db_lock (libsql hace auto-sync interno en SELECT también)"""
        if not self._connected:
            await self.connect()

        max_retries = 3
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                def _do_fetch():
                    try:
                        if self.conn is None:
                            raise Exception("conn is None")
                        cursor = self.conn.cursor()
                        rows = cursor.execute(query, params or ()).fetchall()
                        cols = [col[0] for col in cursor.description]
                        return [dict(zip(cols, row)) for row in rows], None
                    except Exception as inner_e:
                        if "malformed" in str(inner_e).lower() or "corrupt" in str(inner_e).lower():
                            logger.error(f"CORRUPTION in FETCH query: {query} with params: {params} -> {inner_e}")
                        if self._is_reconnect_error(inner_e):
                            return "RECONNECT", inner_e
                        raise inner_e
                    except BaseException as panic_e:
                        name = type(panic_e).__name__.lower()
                        if "panic" in name or "pyo3" in name:
                            return "RECONNECT", Exception(f"Rust Panic: {panic_e}")
                        raise panic_e

                # Lecturas sin _db_lock: la réplica embebida lee del archivo local
                # (no hace round-trip a la nube), es thread-safe para lecturas concurrentes.
                # Solo escrituras y sync() necesitan serialización.
                status, error_obj = await asyncio.to_thread(_do_fetch)

                if status == "RECONNECT":
                    if error_obj and self._is_wal_conflict(error_obj):
                        # Retry rápido para reads: 200ms (no 1s como escrituras)
                        logger.warning(f"⚠️ WAL en FETCH (retry {attempt}/{max_retries}): {query[:60]}...")
                        await asyncio.sleep(0.2)
                    elif error_obj and "malformed" in str(error_obj).lower():
                        logger.warning(f"🧹 Corrupción detectada en FETCH: {error_obj}. Resetting...")
                        await self.reset_local_db()
                    else:
                        logger.warning(f"🔄 FETCH retry {attempt}/{max_retries}: {error_obj}")
                        self._connected = False
                        # Stream expirado: reconectar inmediatamente (el stream ya está muerto)
                        if not self._is_stream_error(error_obj):
                            await asyncio.sleep(0.3)
                        await self.connect()
                    last_error = error_obj
                    continue

                return status

            except Exception as e:
                if self._is_wal_conflict(e):
                    logger.warning(f"⚠️ WAL outer FETCH (retry {attempt}/{max_retries}): {query[:60]}...")
                    await asyncio.sleep(0.2)
                    last_error = e
                    continue

                if self._is_reconnect_error(e) and attempt < max_retries:
                    logger.warning(f"🔄 FETCH retry {attempt}/{max_retries}: {e}")
                    self._connected = False
                    await asyncio.sleep(0.5)
                    await self.connect()
                    last_error = e
                    continue

                logger.error(f"❌ Error FetchAll: {e} | Query: {query} | Params: {params}")
                return []

        # Agotamos reintentos
        if last_error and self._is_wal_conflict(last_error):
            # WAL persistente: lanzar excepción en lugar de devolver [] vacío.
            # Devolver [] causaría que el auth diga "usuario no encontrado" → 401 incorrecto.
            # Con excepción, FastAPI devuelve 500/503 y el usuario ve un error real, no un logout.
            logger.error(f"❌ WAL persistente en FETCH tras {max_retries} reintentos — proceso externo activo: {query[:60]}...")
            raise RuntimeError("DB sync conflict — reintente en unos segundos")

        logger.error(f"❌ FETCH falló tras {max_retries} reintentos | Query: {query[:80]}")
        return []

    async def fetch_one(self, query: str, params: Optional[Tuple] = None) -> Optional[Dict[str, Any]]:
        """Fetch one con conversión a dict"""
        rows = await self.fetch_all(query, params)
        return rows[0] if rows else None

    async def execute_batch(self, operations: List[Tuple[str, Optional[Union[tuple, list]]]], suppress_auto_sync: bool = False) -> None:
        """
        Ejecuta múltiples sentencias en una transacción atómica.

        ARQUITECTURA DE DOS FASES:
        ─────────────────────────────────────────────────────────────────────────
        Fase 1 – Commit LOCAL (dentro del _db_lock, instantáneo ~ms):
            conn.commit() escribe en el WAL de SQLite local. No hay round-trip
            a la nube. El lock se libera inmediatamente después.

        Fase 2 – Sync a TURSO CLOUD (fuera del _db_lock):
            Si suppress_auto_sync=False (default): se lanza _push_to_cloud()
            como ensure_future (fire-and-forget).
            Si suppress_auto_sync=True: NO se lanza el sync automático.
            Usar cuando se ejecutarán múltiples execute_batch consecutivos
            (ej: batch de N meses de BioAlba) para evitar que conn.sync()
            de la iteración anterior compita con el cursor() de la siguiente
            sobre el objeto libsql nativo. El caller es responsable de llamar
            sync_to_cloud_explicit() al terminar la secuencia completa.
        ─────────────────────────────────────────────────────────────────────────
        """
        if not self._connected:
            await self.connect()

        max_retries = 3
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                def _do_batch_local():
                    """Solo commit LOCAL al WAL. No llama conn.sync(). Rápido: escritura en disco local, sin red."""
                    try:
                        if self.conn is None:
                            raise Exception("conn is None")
                        cursor = self.conn.cursor()
                        for query, params in operations:
                            cursor.execute(query, params or ())
                        self.conn.commit()   # WAL local — instantáneo
                        return "OK", None
                    except Exception as inner_e:
                        try:
                            if self.conn:
                                self.conn.cursor().execute("ROLLBACK")
                        except Exception:
                            pass
                        if self._is_reconnect_error(inner_e):
                            return "RECONNECT", inner_e
                        raise inner_e
                    except BaseException as panic_e:
                        name = type(panic_e).__name__.lower()
                        if "panic" in name or "pyo3" in name:
                            return "RECONNECT", Exception(f"Rust Panic: {panic_e}")
                        raise panic_e

                # ── Adquisición del lock (máx 10s) ──────────────────────────
                try:
                    async with asyncio.timeout(10):
                        await self._db_lock.acquire()
                except asyncio.TimeoutError:
                    logger.warning(f"⏳ _db_lock timeout en BATCH (intento {attempt}/{max_retries})")
                    await asyncio.sleep(0.5)
                    continue

                # ── Commit LOCAL dentro del lock ─────────────────────────────
                try:
                    status, error_obj = await asyncio.to_thread(_do_batch_local)
                finally:
                    # Lock liberado ANTES del sync a la nube → desbloquea hot path
                    self._db_lock.release()

                if status == "RECONNECT":
                    if error_obj and self._is_wal_conflict(error_obj):
                        logger.warning(f"⚠️ WAL en BATCH (retry {attempt}/{max_retries})")
                        await asyncio.sleep(1)
                    else:
                        logger.warning(f"🔄 BATCH retry {attempt}/{max_retries}: {error_obj}")
                        self._connected = False
                        if not self._is_stream_error(error_obj):
                            await asyncio.sleep(0.3)
                        await self.connect()
                    last_error = error_obj
                    continue

                # ── Sync a Turso Cloud (FUERA del lock) ──────────────────────
                # Si suppress_auto_sync=True, el caller hará sync_to_cloud_explicit()
                # al terminar toda la secuencia de batches, evitando que conn.sync()
                # de un batch previo compita con el cursor() del siguiente batch
                # sobre el objeto libsql nativo (causa del bloqueo silencioso de 22s).
                if self.sync_supported and not suppress_auto_sync:
                    # Coalescing sync: si ya hay un sync en vuelo, no lanzar otro.
                    # Evita el 429 cuando execute_batch se llama N veces en rápida
                    # sucesión (ej: reproceso de 49 empleados → 49 fire-and-forget).
                    if not self._sync_pending and not self._sync_lock.locked():
                        self._sync_pending = True
                        async def _push_to_cloud():
                            async with self._sync_lock:
                                self._sync_pending = False
                                try:
                                    await asyncio.to_thread(self.conn.sync)
                                    self._last_sync = __import__('datetime').datetime.now()
                                except Exception as sync_err:
                                    logger.warning(f"⚠️ Sync background a Turso falló (datos en WAL local): {sync_err}")
                        asyncio.ensure_future(_push_to_cloud())

                return

            except Exception as e:
                if self._is_wal_conflict(e):
                    logger.warning(f"⚠️ WAL outer BATCH (retry {attempt}/{max_retries})")
                    await asyncio.sleep(1)
                    last_error = e
                    continue

                if self._is_reconnect_error(e) and attempt < max_retries:
                    logger.warning(f"🔄 BATCH retry {attempt}/{max_retries}: {e}")
                    self._connected = False
                    await asyncio.sleep(1)
                    await self.connect()
                    last_error = e
                    continue

                logger.error(f"❌ Error BATCH: {e}")
                raise

        logger.error(f"❌ BATCH falló tras {max_retries} reintentos")
        if last_error:
            raise last_error

    async def executemany(self, query: str, params_list: List[Union[tuple, list]], suppress_auto_sync: bool = False) -> None:
        """Ejecuta la misma query con múltiples sets de parámetros."""
        operations = [(query, params) for params in params_list]
        await self.execute_batch(operations, suppress_auto_sync=suppress_auto_sync)

    async def execute_script(self, script_sql: str) -> None:
        """
        Ejecuta múltiples statements en UN SOLO round-trip a Turso Cloud.

        Usar cuando se necesita ejecutar varios DELETEs, INSERTs o DDL sin parámetros
        (ej: purgas de tablas, migraciones, seeds).

        IMPORTANTE: executescript NO soporta parámetros (?, :name). Solo valores literales.
        Para queries con parámetros usar execute_batch() en su lugar.

        Benchmark vs execute() en loop:
          - execute() × 13 tablas  → 13 round-trips ≈ 17s
          - execute_script() × 13  →  1 round-trip  ≈ 1-2s
        """
        if not self._connected:
            await self.connect()

        max_retries = 3
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                def _do_script():
                    try:
                        if self.conn is None:
                            raise Exception("conn is None")
                        cursor = self.conn.cursor()
                        cursor.executescript(script_sql)
                        # executescript hace auto-COMMIT al final del script
                        return "OK", None
                    except Exception as inner_e:
                        if self._is_reconnect_error(inner_e):
                            return "RECONNECT", inner_e
                        raise inner_e
                    except BaseException as panic_e:
                        name = type(panic_e).__name__.lower()
                        if "panic" in name or "pyo3" in name:
                            return "RECONNECT", Exception(f"Rust Panic: {panic_e}")
                        raise panic_e

                try:
                    async with asyncio.timeout(30):
                        async with self._db_lock:
                            status, error_obj = await asyncio.to_thread(_do_script)
                except asyncio.TimeoutError:
                    logger.warning(f"⏳ _db_lock timeout en SCRIPT (intento {attempt}/{max_retries})")
                    await asyncio.sleep(0.5)
                    continue

                if status == "RECONNECT":
                    if error_obj and self._is_wal_conflict(error_obj):
                        logger.warning(f"⚠️ WAL en SCRIPT (retry {attempt}/{max_retries})")
                        await asyncio.sleep(1)
                    else:
                        logger.warning(f"🔄 SCRIPT retry {attempt}/{max_retries}: {error_obj}")
                        self._connected = False
                        await asyncio.sleep(1)
                        await self.connect()
                    last_error = error_obj
                    continue

                return  # Éxito

            except Exception as e:
                if self._is_wal_conflict(e):
                    logger.warning(f"⚠️ WAL outer SCRIPT (retry {attempt}/{max_retries})")
                    await asyncio.sleep(1)
                    last_error = e
                    continue

                if self._is_reconnect_error(e) and attempt < max_retries:
                    logger.warning(f"🔄 SCRIPT retry {attempt}/{max_retries}: {e}")
                    self._connected = False
                    await asyncio.sleep(1)
                    await self.connect()
                    last_error = e
                    continue

                logger.error(f"❌ Error SCRIPT: {e}")
                raise

        logger.error(f"❌ SCRIPT falló tras {max_retries} reintentos")
        if last_error:
            raise last_error


    async def get_column_names(self, table_name: str) -> List[str]:
        """Obtiene lista de columnas de una tabla usando PRAGMA (Local rápido)"""
        if not self._connected: await self.connect()

        if table_name in self._schema_cache:
            return self._schema_cache[table_name]

        try:
            query = f"PRAGMA table_info({table_name})"
            cursor = await self.fetch_all(query)
            cols = [row['name'] for row in cursor]
            if cols:
                self._schema_cache[table_name] = cols
            return cols
        except Exception as e:
            logger.error(f"❌ Error obteniendo columnas de {table_name}: {e}")
            return []

    async def sync_from_cloud(self) -> None:
        """Sincronización Nativa delegada a LibSQL (WAL concurrente, respeta _sync_lock)."""
        if not self.sync_supported:
            return

        # Si hay un batch en progreso, ceder el turno para no saturar I/O
        if getattr(self, '_batch_in_progress', False):
            logger.debug("⏸️ sync_from_cloud: batch en progreso, sincronización diferida")
            return

        # Si ya hay un sync en vuelo (push_to_cloud del execute_batch), descartamos este turno.
        # El scheduler lo reintentará en el próximo intervalo. Los datos están seguros en WAL local.
        if self._sync_lock.locked():
            logger.debug("⏸️ sync_from_cloud: sync en vuelo, turno del scheduler descartado")
            return

        try:
            async with self._sync_lock:
                _t0 = datetime.now()
                await asyncio.to_thread(self.conn.sync)
                _elapsed = (datetime.now() - _t0).total_seconds()
                self._last_sync = datetime.now()
                # Threshold en 35s: latencia Chile→USA con Turso Cloud es 30-60s esperado.
                # Alertar solo cuando supera ese umbral indica un problema real de red.
                if _elapsed > 35:
                    logger.warning(f"⚠️ sync_from_cloud: sync lento ({_elapsed:.1f}s) — posible latencia con Turso Cloud")
                else:
                    logger.debug(f"☁️ sync_from_cloud: completado en {_elapsed:.2f}s")
        except Exception as e:
            err_msg = str(e)
            if "status=429" in err_msg or "Too Many Requests" in err_msg:
                logger.warning(f"⚠️ Sync nativo pospuesto: límite de concurrencia en Turso (429). Los datos están a salvo localmente.")
            elif "walconflict" in err_msg.lower() or "wal frame" in err_msg.lower():
                logger.debug(f"☁️ sync_from_cloud pospuesto (WAL conflict leve, resolvemos en prox iteración)")
            else:
                if "server returned a higher frame_no" in err_msg or "larger than what we sent" in err_msg:
                    # Auto-heal en background para no bloquear el hilo de exception handling
                    asyncio.create_task(self._auto_heal_sync_conflict())
                else:
                    logger.error(f"❌ Error en Sync nativo: {e}")

    async def sync_to_cloud_explicit(self) -> None:
        """
        Empuja el WAL local a Turso Cloud en un solo round-trip controlado.

        Usar al final de una secuencia de execute_batch(suppress_auto_sync=True)
        para consolidar N commits locales en 1 único conn.sync(), eliminando
        la contención sobre el objeto libsql nativo entre batches consecutivos.

        Ejemplo (batch BioAlba, 3 meses):
            for mes in meses:
                await repo.save_raw_logs(logs, suppress_auto_sync=True)  # WAL local, ~2ms
            await db.sync_to_cloud_explicit()  # 1 conn.sync() al final, ~20s
        """
        if not self.sync_supported:
            return
        try:
            t0 = asyncio.get_event_loop().time()
            await asyncio.to_thread(self.conn.sync)
            elapsed_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
            self._last_sync = datetime.now()
            logger.info(f"☁️ [Sync explícito] WAL -> Turso Cloud en {elapsed_ms}ms")
        except Exception as e:
            err_msg = str(e)
            if "server returned a higher frame_no" in err_msg or "larger than what we sent" in err_msg:
                logger.critical(f"⚠️ sync_to_cloud_explicit falló por Frame Mismatch. Iniciando Auto-Healing.")
                asyncio.create_task(self._auto_heal_sync_conflict())
            else:
                logger.warning(f"⚠️ sync_to_cloud_explicit falló (datos seguros en WAL local): {e}")

    async def _auto_heal_sync_conflict(self) -> None:
        """
        Destruye y reconstruye la réplica local cuando libsql detecta un Frame Mismatch.

        CAUSAS CONOCIDAS DEL FRAME MISMATCH:
        - El servidor Turso Cloud avanzó sus frames (otra escritura directa al cloud,
          rollback, o migración) mientras la réplica local estaba offline o desconectada.
        - La réplica local tiene un .meta file apuntando a un frame que ya no existe.
        
        PROTOCOLO DE RECUPERACIÓN:
        1. Cerrar la conexión libsql (libera el hilo de sync_interval).
        2. Esperar 3s en Windows para que el OS libere los file handles del Rust backend.
        3. Borrar TODOS los archivos locales, INCLUYENDO .meta (que guarda el frame pointer).
        4. Reconectar: libsql hace un full-clone desde Turso Cloud desde frame 0.
        """
        # Guard: Evitar ejecuciones concurrentes o bucle infinito de auto-heal
        if getattr(self, '_auto_heal_in_progress', False):
            logger.warning("⏸️ Auto-heal ya en progreso, descartando solicitud duplicada")
            return
        self._auto_heal_in_progress = True
        
        logger.critical("🚨 Frame Mismatch con Turso Cloud! Iniciando auto-recuperación de réplica...")
        try:
            # 1. Cerrar conexión y anular referencia para liberar handles del Rust backend
            if self.conn:
                try:
                    await asyncio.to_thread(self.conn.close)
                    logger.info("🔌 Conexión libsql cerrada")
                except Exception as close_err:
                    logger.warning(f"⚠️ Error al cerrar conn (ignorado): {close_err}")
                finally:
                    self.conn = None
                    self._connected = False
            
            # 2. Forzar liberación de handles de Rust en Windows
            #    El hilo de sync_interval de libsql puede tardar hasta 2-3s en soltar handles
            import gc
            gc.collect()
            await asyncio.sleep(3.0)  # Espera crítica para Windows: libera file handles del OS
            
            # 3. Borrar TODOS los archivos de réplica local, INCLUYENDO .meta
            #    .meta es el archivo que guarda el frame pointer — SIN borrarlo, el heal falla
            db_path_str = str(self.db_path)
            files_to_delete = [
                db_path_str,            # .db  — base de datos local
                db_path_str + "-wal",   # -wal — write-ahead log
                db_path_str + "-shm",   # -shm — shared memory index del WAL
                db_path_str + "-info",  # -info — FRAME POINTER (SDK Python de libsql)
                db_path_str + ".meta",  # .meta — FRAME POINTER (versiones nuevas de libsql)
            ]
            
            deleted = []
            failed = []
            for f in files_to_delete:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                        deleted.append(os.path.basename(f))
                        logger.info(f"🗑️ Eliminado: {os.path.basename(f)}")
                    except PermissionError:
                        # Último recurso: renombrar (libera el path, el handle se cierra al GC)
                        corrupt_name = f + f".corrupt_{int(datetime.now().timestamp())}"
                        try:
                            os.rename(f, corrupt_name)
                            deleted.append(os.path.basename(f) + "→.corrupt")
                            logger.warning(f"🩹 Movido a backup: {os.path.basename(corrupt_name)}")
                        except Exception as rename_err:
                            failed.append(os.path.basename(f))
                            logger.error(f"❌ No se pudo eliminar/renombrar {os.path.basename(f)}: {rename_err}")
            
            if failed:
                logger.critical(
                    f"🛑 Auto-heal PARCIAL: {len(deleted)} borrados, {len(failed)} bloqueados: {failed}. "
                    "El .meta file puede persistir. Reinicia el servidor para completar la recuperación."
                )
            else:
                logger.info(f"✅ Archivos eliminados: {', '.join(deleted)}")
            
            # 4. Reconectar — libsql hará full-clone desde Turso Cloud (frame 0)
            logger.info("🔄 Reconectando y clonando réplica desde Turso Cloud...")
            await asyncio.sleep(0.5)
            await self.connect()
            logger.success("✅ Auto-recuperación exitosa. Réplica re-sincronizada desde la nube (frame 0).")
            
        except Exception as e:
            logger.error(f"❌ Fallo en auto-recuperación: {e}")
            # Intentar reconectar de todas formas para no dejar la DB sin conexión
            try:
                if not self._connected:
                    await self.connect()
            except Exception:
                pass
        finally:
            self._auto_heal_in_progress = False



    async def initialize_v2_sync(self) -> None:
        """Mantiene compatibilidad de esquema (Stub para no romper código externo)"""
        pass

    async def get_table_names(self) -> List[str]:
        """Obtiene lista de tablas existentes (Local rápido)"""
        if not self._connected: await self.connect()
        query = "SELECT name FROM sqlite_master WHERE type='table'"
        cursor = await self.fetch_all(query)
        return [row['name'] for row in cursor]

    async def column_exists(self, table_name: str, column_name: str) -> bool:
        """Verifica si una columna existe de forma eficiente"""
        cols = await self.get_column_names(table_name)
        return column_name in cols

    async def table_exists(self, table_name: str) -> bool:
        """Verifica si una tabla existe localmente de forma instantánea usando sqlite_master"""
        if not self._connected: await self.connect()
        query = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        cursor = await self.fetch_one(query, (table_name,))
        return cursor is not None

    async def _execute_turso(self, query: str, params: Optional[Tuple] = None) -> Any:
        """
        Ejecución directa para diagnóstico de la nube.
        En modo Embedded Replica, LibSQL rutea automáticamente las escrituras a la nube.
        Para un health check, forzamos un sync para asegurar bidireccionalidad.
        """
        if not self._connected:
            await self.connect()

        try:
            if self.sync_supported:
                await self.sync_from_cloud()
            return await self.execute(query, params)
        except Exception as e:
            logger.error(f"❌ Fallo de comunicación directa con Turso: {e}")
            raise

    async def clear_schema_cache(self) -> None:
        """Limpia el caché de esquemas para forzar re-lectura"""
        self._schema_cache.clear()
        logger.debug("🧹 Schema cache limpiado")

    async def health_check(self) -> Dict[str, Any]:
        """Verifica el estado de salud de la conexión"""
        try:
            if not self._connected:
                return {"status": "disconnected", "turso": False, "local": False}

            result = await self.fetch_one("SELECT 1 as ok")
            local_ok = result is not None and result.get("ok") == 1

            return {
                "status": "healthy" if local_ok else "degraded",
                "local": local_ok,
                "turso": self.use_turso,
                "last_sync": self._last_sync.isoformat() if self._last_sync else None,
                "mode": "cloud" if self._force_turso_only else "hybrid"
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "local": False, "turso": False}

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def sync_supported(self) -> bool:
        return (
            self._connected
            and self.conn is not None
            and self.use_turso
            and not self._force_turso_only
            and hasattr(self.conn, 'sync')
        )


# Alias de compatibilidad (código existente importa 'Database')
Database = HybridDatabase

# Singleton global
db = HybridDatabase()


async def get_db() -> HybridDatabase:
    """Dependency injection para FastAPI"""
    if not db._connected:
        await db.connect()
    return db