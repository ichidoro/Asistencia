"""
Turso Cloud Database â€” ConexiÃ³n directa a Turso Cloud.
Turso es la ÃšNICA fuente de verdad. No se permite base de datos local.
"""

import libsql
import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from contextlib import asynccontextmanager
from loguru import logger
from datetime import datetime, date

from .config import settings


class TursoDatabase:
    """
    Database Turso Cloud â€” ConexiÃ³n directa al servidor Turso.
    Turso es la ÃšNICA fuente de verdad. No se permite base de datos local.
    """
    
    def __init__(self):
        self.conn: Optional[libsql.Connection] = None
        
        # Turso Config
        self.use_turso = bool(
            settings.TURSO_DATABASE_URL and 
            ("libsql" in settings.TURSO_DATABASE_URL or "turso.io" in settings.TURSO_DATABASE_URL)
        )
        
        if not self.use_turso:
            raise RuntimeError(
                "TURSO_DATABASE_URL es obligatorio. "
                "No se permite base de datos local. "
                "Configura las variables de entorno TURSO_DATABASE_URL y TURSO_AUTH_TOKEN."
            )
        
        self.turso_url = settings.TURSO_DATABASE_URL
        self.turso_token = settings.TURSO_AUTH_TOKEN
        
        self._connected: bool = False
        self._last_sync: Optional[datetime] = None
        self._force_turso_only = True  # Siempre True â€” Turso Cloud directo
        self._schema_cache: Dict[str, List[str]] = {}  # CachÃ© para migraciones rÃ¡pidas
        self._in_transaction: bool = False  # Control de transacciones para batching
        self._reset_lock = asyncio.Lock()
        # Lock para serializar acceso concurrente al objeto self.conn.
        # libsql (Rust) no es thread-safe para acceso simultÃ¡neo desde mÃºltiples threads.
        # Los requests HTTP comparten self.conn â†’ Race Condition posible.
        # Este lock garantiza que solo una operaciÃ³n accede a conn a la vez.
        self._db_lock = asyncio.Lock()
        self.last_activity_time: float = 0.0
        self._realtime_sync_active: bool = False
        self._auto_heal_in_progress: bool = False
        
        logger.info("â˜ï¸ Modo NUBE PURA (Turso directo) â€” sin rÃ©plica local")
        
        
    def _get_lock(self, name: str) -> asyncio.Lock:
        """Obtiene o recrea el lock asegurando que estÃ© vinculado al event loop actual"""
        lock_var = f"_{name}"
        lock = getattr(self, lock_var)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return lock
            
        if hasattr(lock, '_loop') and lock._loop is not None:
            if lock._loop != loop:
                logger.warning(f"ðŸ”„ Recreando {lock_var} porque el event loop actual cambiÃ³ o es diferente")
                lock = asyncio.Lock()
                setattr(self, lock_var, lock)
        return lock

    @property
    def db_lock(self) -> asyncio.Lock:
        return self._get_lock('db_lock')

    @property
    def reset_lock(self) -> asyncio.Lock:
        return self._get_lock('reset_lock')



    async def connect(self, retry: bool = True) -> None:
        """Establece la conexiÃ³n nativa con Turso (Embedded Replica o Remote)"""
        if self._connected:
            return
            
        async with self.reset_lock:
            if self._connected:
                return
            await self._connect_locked(retry)
            
    async def _connect_locked(self, retry: bool = True) -> None:
        try:
            logger.warning("ðŸš€ Conectando directamente a Turso Cloud")
            self.conn = await asyncio.to_thread(
                libsql.connect, 
                database=self.turso_url, 
                auth_token=self.turso_token
            )

            self._connected = True
            logger.info("â˜ï¸ Modo Nube Pura: Se omiten PRAGMAs locales (no soportados por Hrana)")
            self._pragma_applied = False

            logger.success("âœ… Motor LibSQL conectado (Modo: Cloud)")

        except Exception as e:
            if "maximum recursion depth exceeded" in str(e).lower():
                logger.critical("ðŸ›‘ Error de recursiÃ³n crÃ­tica en conexiÃ³n. Abortando para evitar crash.")
                self._connected = False
                return
            logger.error(f"âŒ Error de conexiÃ³n LibSQL: {e}")
            raise

    async def enable_realtime_sync(self, interval: int = 3) -> None:
        """Marca sync como activo. En modo Turso Cloud directo no hay sync local."""
        self._realtime_sync_active = True
        logger.info("â˜ï¸ Turso Cloud directo â€” no se requiere sync local")

    async def save_setting(self, clave: str, valor: str):
        """Guarda un ajuste en la DB Turso."""
        try:
            if not self._connected or not self.conn:
                logger.warning(f"âš ï¸ No hay conexiÃ³n activa para persistir ajuste {clave}")
                return
            await self.execute(
                "INSERT OR REPLACE INTO ajustes (clave, valor) VALUES (?, ?)",
                (clave, str(valor))
            )
            logger.debug(f"ðŸ’¾ Ajuste persistido en Turso: {clave}={valor}")
        except Exception as e:
            logger.error(f"âš ï¸ No se pudo persistir ajuste {clave}: {e}")

    async def disconnect(self) -> None:
        """Cerrar conexiÃ³n con Turso Cloud"""
        if not self._connected or not self.conn:
            return

        try:
            await asyncio.to_thread(self.conn.close)
        except Exception:
            pass  # Ignorar errores al cerrar
        self.conn = None

        self._connected = False
        # Forzar liberaciÃ³n de handles del Rust backend en Windows
        import gc
        gc.collect()
        await asyncio.sleep(0.5)
        logger.info("ðŸ‘‹ Motor LibSQL desconectado")

    def _is_wal_conflict(self, e: Exception) -> bool:
        """Detecta WAL conflicts de Turso Cloud (datos locales OK, sync pendiente)"""
        msg = str(e).lower()
        return "walconflict" in msg or "wal frame" in msg

    def _is_stream_error(self, e: Exception) -> bool:
        """Detecta errores de stream expirado de Turso Cloud (Hrana 404 stream not found).
        Estos streams son cerrados por el servidor tras inactividad; la reconexiÃ³n
        debe ser inmediata â€” no tiene sentido esperar si el stream ya estÃ¡ muerto."""
        msg = str(e).lower()
        return "stream not found" in msg or "status=404" in msg

    def _is_reconnect_error(self, e: Exception) -> bool:
        """Determina si un error requiere cerrar y volver a abrir la conexiÃ³n o un reset"""
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
        """Context manager para agrupar operaciones en una transacciÃ³n atÃ³mica"""
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
                        logger.warning(f"âš ï¸ WAL Conflict en commit (datos locales OK, sync pendiente): {commit_err}")
                        return  # No re-raise â€” datos locales estÃ¡n a salvo
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
        self.last_activity_time = time.time()
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

                # FIX1: Serializar lecturas Y escrituras bajo _db_lock.
                # Las lecturas sin lock competÃ­an con conn.sync() del scheduler, causando
                # corrupciÃ³n silenciosa del WAL. Ahora TODAS las operaciones son serializadas.
                # Fase 1: AdquisiciÃ³n del lock con timeout de 10s
                try:
                    async with asyncio.timeout(10):
                        await self.db_lock.acquire()
                except asyncio.TimeoutError:
                    logger.warning(f"â³ _db_lock timeout en EXECUTE (intento {attempt}/{max_retries}): {query[:60]}...")
                    last_error = asyncio.TimeoutError("db_lock timeout")
                    await asyncio.sleep(0.5)
                    continue

                # Fase 2: EjecuciÃ³n bajo lock â€” reads y writes protegidos del scheduler
                try:
                    status, error_obj = await asyncio.to_thread(_do_execute)
                finally:
                    self.db_lock.release()

                if status == "RECONNECT":
                    if error_obj and self._is_wal_conflict(error_obj):
                        logger.warning(f"âš ï¸ WAL residual post-lock en EXECUTE (retry {attempt}/{max_retries}): {query[:60]}...")
                        await asyncio.sleep(1)
                    elif error_obj and "malformed" in str(error_obj).lower():
                        logger.warning(f"ðŸ§¹ CorrupciÃ³n detectada en EXECUTE: {error_obj}. Reconectando...")
                        self._connected = False
                        await asyncio.sleep(0.3)
                        await self.connect()
                    else:
                        logger.warning(f"ðŸ”„ EXECUTE retry {attempt}/{max_retries}: {error_obj}")
                        self._connected = False
                        # Stream expirado: reconectar inmediatamente (el stream ya estÃ¡ muerto)
                        # Otros errores de red: backoff corto antes de reintentar
                        if not self._is_stream_error(error_obj):
                            await asyncio.sleep(0.3)
                        await self.connect()
                    last_error = error_obj
                    continue

                if error_obj == "WAL_OK":
                    logger.warning(f"âš ï¸ WAL residual (local OK): {query[:60]}...")
                    return status

                return status

            except Exception as e:
                err_msg = str(e).lower()
                if "duplicate column name" in err_msg:
                    logger.debug(f"â„¹ï¸ SQL: Columna ya existe (Ignorado) | Query: {query[:50]}...")
                    class DummyCursor:
                        def __init__(self): self.lastrowid = None
                        def fetchall(self): return []
                        def fetchone(self): return None
                        def close(self): pass
                    return DummyCursor()

                if self._is_wal_conflict(e):
                    logger.warning(f"âš ï¸ WAL residual outer (retry {attempt}/{max_retries}): {query[:60]}...")
                    await asyncio.sleep(1)
                    last_error = e
                    continue

                if self._is_reconnect_error(e) and attempt < max_retries:
                    logger.warning(f"ðŸ”„ EXECUTE retry {attempt}/{max_retries}: {e}")
                    self._connected = False
                    await asyncio.sleep(1)
                    await self.connect()
                    last_error = e
                    continue

                logger.error(f"âŒ Error SQL: {e} | Query: {query} | Params: {params}")
                raise

        # Si agotamos reintentos
        if last_error and self._is_wal_conflict(last_error):
            logger.warning(f"âš ï¸ WAL persistente (no fatal, datos locales OK): {query[:60]}...")
            class DummyCursor:
                def __init__(self): self.lastrowid = None
                def fetchall(self): return []
                def fetchone(self): return None
                def close(self): pass
            return DummyCursor()

        logger.error(f"âŒ EXECUTE fallÃ³ tras {max_retries} reintentos | Query: {query[:80]}")
        if last_error:
            raise last_error

    async def fetch_all(self, query: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
        """Fetch all usando conexiÃ³n Ãºnica serializada por _db_lock"""
        self.last_activity_time = time.time()
        if not self._connected:
            await self.connect()

        lock_to_use = self.db_lock
        conn_to_use = self.conn

        max_retries = 3
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                def _do_fetch():
                    try:
                        nonlocal conn_to_use
                        if conn_to_use is None:
                            raise Exception("connection is None")
                        cursor = conn_to_use.cursor()
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

                try:
                    async with asyncio.timeout(10):
                        await lock_to_use.acquire()
                except asyncio.TimeoutError:
                    logger.warning(f"â³ lock timeout en FETCH (intento {attempt}/{max_retries}): {query[:60]}...")
                    last_error = asyncio.TimeoutError("lock timeout")
                    await asyncio.sleep(0.1)
                    continue

                try:
                    status, error_obj = await asyncio.to_thread(_do_fetch)
                finally:
                    lock_to_use.release()

                if status == "RECONNECT":
                    if error_obj and self._is_wal_conflict(error_obj):
                        logger.warning(f"âš ï¸ WAL en FETCH (retry {attempt}/{max_retries}): {query[:60]}...")
                        await asyncio.sleep(0.1)
                    elif error_obj and "malformed" in str(error_obj).lower():
                        logger.warning(f"ðŸ§¹ CorrupciÃ³n detectada en FETCH: {error_obj}. Reconectando...")
                        self._connected = False
                        await asyncio.sleep(0.3)
                        await self.connect()
                        conn_to_use = self.conn
                    else:
                        logger.warning(f"ðŸ”„ FETCH retry {attempt}/{max_retries}: {error_obj}")
                        self._connected = False
                        if not self._is_stream_error(error_obj):
                            await asyncio.sleep(0.3)
                        await self.connect()
                        conn_to_use = self.conn
                    last_error = error_obj
                    continue

                return status

            except Exception as e:
                if self._is_wal_conflict(e):
                    logger.warning(f"âš ï¸ WAL outer FETCH (retry {attempt}/{max_retries}): {query[:60]}...")
                    await asyncio.sleep(0.1)
                    last_error = e
                    continue

                if self._is_reconnect_error(e) and attempt < max_retries:
                    logger.warning(f"ðŸ”„ FETCH retry {attempt}/{max_retries}: {e}")
                    self._connected = False
                    await asyncio.sleep(0.3)
                    await self.connect()
                    conn_to_use = self.conn
                    last_error = e
                    continue

                logger.error(f"âŒ Error FetchAll: {e} | Query: {query} | Params: {params}")
                return []

        # Agotamos reintentos
        if last_error and self._is_wal_conflict(last_error):
            logger.error(f"âŒ WAL persistente en FETCH tras {max_retries} reintentos â€” proceso externo activo: {query[:60]}...")
            raise RuntimeError("DB sync conflict â€” reintente en unos segundos")

        logger.error(f"âŒ FETCH fallÃ³ tras {max_retries} reintentos | Query: {query[:80]}")
        return []

    async def fetch_one(self, query: str, params: Optional[Tuple] = None) -> Optional[Dict[str, Any]]:
        """Fetch one con conversiÃ³n a dict"""
        rows = await self.fetch_all(query, params)
        return rows[0] if rows else None

    async def execute_batch(self, operations: List[Tuple[str, Optional[Union[tuple, list]]]], suppress_auto_sync: bool = False) -> None:
        """
        Ejecuta mÃºltiples sentencias en una transacciÃ³n atÃ³mica.

        ARQUITECTURA DE DOS FASES:
        â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        Fase 1 â€“ Commit LOCAL (dentro del _db_lock, instantÃ¡neo ~ms):
            conn.commit() escribe en el WAL de SQLite local. No hay round-trip
            a la nube. El lock se libera inmediatamente despuÃ©s.

        Fase 2 â€“ Sync a TURSO CLOUD (fuera del _db_lock):
            Si suppress_auto_sync=False (default): se lanza _push_to_cloud()
            como ensure_future (fire-and-forget).
            Si suppress_auto_sync=True: NO se lanza el sync automÃ¡tico.
            Usar cuando se ejecutarÃ¡n mÃºltiples execute_batch consecutivos
            (ej: batch de N meses de BioAlba) para evitar que conn.sync()
            de la iteraciÃ³n anterior compita con el cursor() de la siguiente
            sobre el objeto libsql nativo. El caller es responsable de llamar
            sync_to_cloud_explicit() al terminar la secuencia completa.
        â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        """
        self.last_activity_time = time.time()
        if not self._connected:
            await self.connect()

        max_retries = 3
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                def _do_batch_local():
                    """Solo commit LOCAL al WAL. No llama conn.sync(). RÃ¡pido: escritura en disco local, sin red."""
                    try:
                        if self.conn is None:
                            raise Exception("conn is None")
                        cursor = self.conn.cursor()
                        for query, params in operations:
                            cursor.execute(query, params or ())
                        self.conn.commit()   # WAL local â€” instantÃ¡neo
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

                # â”€â”€ AdquisiciÃ³n del lock (mÃ¡x 10s) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                try:
                    async with asyncio.timeout(10):
                        await self.db_lock.acquire()
                except asyncio.TimeoutError:
                    logger.warning(f"â³ _db_lock timeout en BATCH (intento {attempt}/{max_retries})")
                    await asyncio.sleep(0.5)
                    continue

                # â”€â”€ Commit LOCAL dentro del lock â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                try:
                    status, error_obj = await asyncio.to_thread(_do_batch_local)
                finally:
                    # Lock liberado ANTES del sync a la nube â†’ desbloquea hot path
                    self.db_lock.release()

                if status == "RECONNECT":
                    if error_obj and self._is_wal_conflict(error_obj):
                        logger.warning(f"âš ï¸ WAL en BATCH (retry {attempt}/{max_retries})")
                        await asyncio.sleep(1)
                    else:
                        logger.warning(f"ðŸ”„ BATCH retry {attempt}/{max_retries}: {error_obj}")
                        self._connected = False
                        if not self._is_stream_error(error_obj):
                            await asyncio.sleep(0.3)
                        await self.connect()
                    last_error = error_obj
                    continue

                # â”€â”€ Sync a Turso Cloud â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                # El sync a la nube lo hace EXCLUSIVAMENTE el APScheduler (sync_from_cloud).
                # Disparar un conn.sync() fire-and-forget aquÃ­ causaba contenciÃ³n de mutex
                # en el objeto libsql nativo: si el recÃ¡lculo de asistencia llegaba
                # milisegundos despuÃ©s, su thread tambiÃ©n intentaba acceder a self.conn,
                # resultando en esperas de 200-600ms por el mutex interno de Rust.
                # Los datos estÃ¡n seguros en el WAL local hasta el prÃ³ximo ciclo del scheduler.
                # suppress_auto_sync se mantiene por compatibilidad de firma con callers.
                return

            except Exception as e:
                if self._is_wal_conflict(e):
                    logger.warning(f"âš ï¸ WAL outer BATCH (retry {attempt}/{max_retries})")
                    await asyncio.sleep(1)
                    last_error = e
                    continue

                if self._is_reconnect_error(e) and attempt < max_retries:
                    logger.warning(f"ðŸ”„ BATCH retry {attempt}/{max_retries}: {e}")
                    self._connected = False
                    await asyncio.sleep(1)
                    await self.connect()
                    last_error = e
                    continue

                logger.error(f"âŒ Error BATCH: {e}")
                raise

        logger.error(f"âŒ BATCH fallÃ³ tras {max_retries} reintentos")
        if last_error:
            raise last_error

    async def executemany(self, query: str, params_list: List[Union[tuple, list]], suppress_auto_sync: bool = False) -> None:
        """Ejecuta la misma query con mÃºltiples sets de parÃ¡metros."""
        operations = [(query, params) for params in params_list]
        await self.execute_batch(operations, suppress_auto_sync=suppress_auto_sync)

    async def execute_script(self, script_sql: str) -> None:
        """
        Ejecuta mÃºltiples statements en UN SOLO round-trip a Turso Cloud.

        Usar cuando se necesita ejecutar varios DELETEs, INSERTs o DDL sin parÃ¡metros
        (ej: purgas de tablas, migraciones, seeds).

        IMPORTANTE: executescript NO soporta parÃ¡metros (?, :name). Solo valores literales.
        Para queries con parÃ¡metros usar execute_batch() en su lugar.

        Benchmark vs execute() en loop:
          - execute() Ã— 13 tablas  â†’ 13 round-trips â‰ˆ 17s
          - execute_script() Ã— 13  â†’  1 round-trip  â‰ˆ 1-2s
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
                        async with self.db_lock:
                            status, error_obj = await asyncio.to_thread(_do_script)
                except asyncio.TimeoutError:
                    logger.warning(f"â³ _db_lock timeout en SCRIPT (intento {attempt}/{max_retries})")
                    await asyncio.sleep(0.5)
                    continue

                if status == "RECONNECT":
                    if error_obj and self._is_wal_conflict(error_obj):
                        logger.warning(f"âš ï¸ WAL en SCRIPT (retry {attempt}/{max_retries})")
                        await asyncio.sleep(1)
                    else:
                        logger.warning(f"ðŸ”„ SCRIPT retry {attempt}/{max_retries}: {error_obj}")
                        self._connected = False
                        await asyncio.sleep(1)
                        await self.connect()
                    last_error = error_obj
                    continue

                return  # Ã‰xito

            except Exception as e:
                if self._is_wal_conflict(e):
                    logger.warning(f"âš ï¸ WAL outer SCRIPT (retry {attempt}/{max_retries})")
                    await asyncio.sleep(1)
                    last_error = e
                    continue

                if self._is_reconnect_error(e) and attempt < max_retries:
                    logger.warning(f"ðŸ”„ SCRIPT retry {attempt}/{max_retries}: {e}")
                    self._connected = False
                    await asyncio.sleep(1)
                    await self.connect()
                    last_error = e
                    continue

                logger.error(f"âŒ Error SCRIPT: {e}")
                raise

        logger.error(f"âŒ SCRIPT fallÃ³ tras {max_retries} reintentos")
        if last_error:
            raise last_error


    async def get_column_names(self, table_name: str) -> List[str]:
        """Obtiene lista de columnas de una tabla usando PRAGMA (Local rÃ¡pido)"""
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
            logger.error(f"âŒ Error obteniendo columnas de {table_name}: {e}")
            return []

    async def sync_from_cloud(self) -> None:
        """No-op: En modo Turso Cloud directo no hay rÃ©plica local que sincronizar."""
        return

    async def sync_to_cloud_explicit(self, max_retries: int = 3) -> bool:
        """No-op: En modo Turso Cloud directo las escrituras van directo al servidor."""
        return True


    async def initialize_v2_sync(self) -> None:
        """Mantiene compatibilidad de esquema (Stub para no romper cÃ³digo externo)"""
        pass

    async def get_table_names(self) -> List[str]:
        """Obtiene lista de tablas existentes (Local rÃ¡pido)"""
        if not self._connected: await self.connect()
        query = "SELECT name FROM sqlite_master WHERE type='table'"
        cursor = await self.fetch_all(query)
        return [row['name'] for row in cursor]

    async def column_exists(self, table_name: str, column_name: str) -> bool:
        """Verifica si una columna existe de forma eficiente"""
        cols = await self.get_column_names(table_name)
        return column_name in cols

    async def table_exists(self, table_name: str) -> bool:
        """Verifica si una tabla existe localmente de forma instantÃ¡nea usando sqlite_master"""
        if not self._connected: await self.connect()
        query = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        cursor = await self.fetch_one(query, (table_name,))
        return cursor is not None

    async def _execute_turso(self, query: str, params: Optional[Tuple] = None) -> Any:
        """
        EjecuciÃ³n directa para diagnÃ³stico de la nube.
        En modo Embedded Replica, LibSQL rutea automÃ¡ticamente las escrituras a la nube.
        Para un health check, forzamos un sync para asegurar bidireccionalidad.
        """
        if not self._connected:
            await self.connect()

        try:
            if hasattr(self.conn, 'sync') and self.use_turso:
                await self.sync_from_cloud()
            return await self.execute(query, params)
        except Exception as e:
            logger.error(f"â Œ Fallo de comunicaciÃ³n directa con Turso: {e}")
            raise

    async def clear_schema_cache(self) -> None:
        """Limpia el cachÃ© de esquemas para forzar re-lectura"""
        self._schema_cache.clear()
        logger.debug("ðŸ§¹ Schema cache limpiado")


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
        """Siempre False — no hay réplica local que sincronizar."""
        return False


# Alias de compatibilidad (código existente importa 'Database' o 'HybridDatabase')
Database = TursoDatabase
HybridDatabase = TursoDatabase

# Singleton global
db = TursoDatabase()


async def get_db() -> TursoDatabase:
    """Dependency injection para FastAPI"""
    if not db._connected:
        await db.connect()
    return db