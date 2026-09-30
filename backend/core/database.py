"""
PostgresDatabase — reemplazo de TursoDatabase (mismo contrato público).

El código de repositorios sigue escribiendo SQL estilo SQLite con '?'; `sql_compat`
lo traduce a PostgreSQL. Las fechas se guardan como TEXT ISO, igual que antes.
"""
import asyncio
import contextvars
import re
import time
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

import asyncpg
from loguru import logger

from .config import settings
from .sql_compat import convert_placeholders, split_statements, translate_sql

# Conexión de la transacción activa (por task, no global: requests concurrentes no se pisan)
_tx_conn: contextvars.ContextVar[Optional[asyncpg.Connection]] = contextvars.ContextVar("tx_conn", default=None)

_INSERT_RE = re.compile(r"^\s*INSERT\s+INTO\s+\"?(\w+)\"?", re.IGNORECASE)


class Result:
    """Emula el cursor de libsql que los repositorios esperan (lastrowid, rowcount, fetchall)."""

    def __init__(self, rows: Optional[List[Dict[str, Any]]] = None, rowcount: int = 0, lastrowid: Optional[int] = None):
        self._rows = rows or []
        self.rowcount = rowcount
        self.lastrowid = lastrowid
        self.description = [(k,) for k in (self._rows[0].keys() if self._rows else [])]

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


def _norm_out(v: Any) -> Any:
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() and v.as_tuple().exponent >= 0 else float(v)
    return v


def _row(r: asyncpg.Record) -> Dict[str, Any]:
    return {k: _norm_out(v) for k, v in r.items()}


def _coerce(value: Any, pg_type: str) -> Any:
    """Adapta un valor Python al tipo que Postgres espera (SQLite era laxo con los tipos)."""
    if value is None:
        return None
    t = pg_type
    if t in ("text", "varchar", "bpchar", "name", "unknown"):
        if isinstance(value, datetime):
            return value.isoformat(sep=" ", timespec="seconds")
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, bool):
            return "1" if value else "0"
        return value if isinstance(value, str) else str(value)
    if t in ("int2", "int4", "int8"):
        if isinstance(value, str):
            v = value.strip()
            return None if v == "" else int(float(v))
        return int(value)
    if t in ("numeric", "float4", "float8"):
        if isinstance(value, str):
            v = value.strip()
            if v == "":
                return None
            return Decimal(v) if t == "numeric" else float(v)
        if t == "numeric":
            return Decimal(str(value))
        return float(value)
    if t == "bool":
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "t", "si", "sí")
        return bool(value)
    return value


class PostgresDatabase:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._connected = False
        self._schema_cache: Dict[str, List[str]] = {}
        self._id_tables: Optional[set] = None
        self._connect_lock: Optional[asyncio.Lock] = None
        self.last_activity_time: float = 0.0
        self._last_sync: Optional[datetime] = None
        # Compat con código que consultaba estos flags (routers/sync, configuracion)
        self.use_turso = False
        self._realtime_sync_active = False
        self._batch_in_progress = False

    # ───────────── conexión ─────────────
    async def connect(self, retry: bool = True) -> None:
        if self._connected and self.pool:
            return
        if self._connect_lock is None:
            self._connect_lock = asyncio.Lock()
        async with self._connect_lock:
            if self._connected and self.pool:
                return
            dsn = settings.DATABASE_URL
            if not dsn:
                raise RuntimeError("DATABASE_URL es obligatorio (postgresql://user:pass@host:5432/db)")
            attempts = 10 if retry else 1
            last: Optional[Exception] = None
            for i in range(1, attempts + 1):
                try:
                    self.pool = await asyncpg.create_pool(
                        dsn=dsn, min_size=2, max_size=int(getattr(settings, "DB_POOL_MAX", 15)),
                        max_inactive_connection_lifetime=300.0, command_timeout=120.0,
                        server_settings={"TimeZone": "UTC"},
                    )
                    self._connected = True
                    logger.success("✅ PostgreSQL conectado (asyncpg pool)")
                    return
                except Exception as e:
                    last = e
                    logger.warning(f"⏳ PostgreSQL no disponible (intento {i}/{attempts}): {e}")
                    await asyncio.sleep(min(2 * i, 10))
            logger.critical(f"❌ No se pudo conectar a PostgreSQL: {last}")
            raise last  # type: ignore[misc]

    async def disconnect(self) -> None:
        if self.pool:
            await self.pool.close()
        self.pool = None
        self._connected = False
        logger.info("👋 Pool de PostgreSQL cerrado")

    async def enable_realtime_sync(self, interval: int = 3) -> None:
        self._realtime_sync_active = True

    async def sync_from_cloud(self) -> None:
        return

    async def sync_to_cloud_explicit(self, max_retries: int = 3) -> bool:
        return True

    async def initialize_v2_sync(self) -> None:
        return

    async def _execute_turso(self, query: str, params: Optional[Tuple] = None) -> Any:
        return await self.execute(query, params)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def sync_supported(self) -> bool:
        return False

    # ───────────── ejecución de bajo nivel ─────────────
    @asynccontextmanager
    async def _conn(self):
        c = _tx_conn.get()
        if c is not None:
            yield c, True
            return
        if not self._connected:
            await self.connect()
        async with self.pool.acquire() as conn:  # type: ignore[union-attr]
            yield conn, False

    async def _run(self, conn: asyncpg.Connection, in_tx: bool, sql: str, params: tuple, mode: str):
        """mode: 'fetch' | 'exec'. Reintenta coaccionando tipos si asyncpg rechaza un parámetro."""
        async def go(args: tuple):
            if mode == "fetch":
                return await conn.fetch(sql, *args)
            return await conn.execute(sql, *args)

        async def attempt():
            try:
                return await go(params)
            except (asyncpg.exceptions.DataError, TypeError):
                stmt = await conn.prepare(sql)
                types = [p.name for p in stmt.get_parameters()]
                coerced = tuple(_coerce(v, types[i] if i < len(types) else "text") for i, v in enumerate(params))
                return await go(coerced)

        if in_tx:
            # savepoint: un error SQL no debe abortar toda la transacción (SQLite era permisivo)
            async with conn.transaction():
                return await attempt()
        return await attempt()

    async def _do(self, query: str, params: Optional[Union[tuple, list]]) -> Result:
        self.last_activity_time = time.time()
        params = tuple(params or ())
        stmts = split_statements(query)
        if len(stmts) > 1 and not params:  # script de varias sentencias
            res = Result()
            async with self.transaction():
                for st in stmts:
                    res = await self._do(st, None)
            return res
        translated = translate_sql(query)
        sql = convert_placeholders(translated)
        head = translated.lstrip().upper()
        is_select = head.startswith(("SELECT", "WITH", "VALUES"))
        m = _INSERT_RE.match(translated) if head.startswith("INSERT") else None
        add_returning = False
        if m and "RETURNING" not in head:
            if await self._table_has_id(m.group(1).lower()):
                sql += " RETURNING id"
                add_returning = True
        try:
            async with self._conn() as (conn, in_tx):
                if is_select or add_returning:
                    recs = await self._run(conn, in_tx, sql, params, "fetch")
                    rows = [_row(r) for r in recs]
                    if add_returning:
                        return Result([], rowcount=len(rows), lastrowid=rows[-1]["id"] if rows else None)
                    return Result(rows, rowcount=len(rows))
                status = await self._run(conn, in_tx, sql, params, "exec")
                n = 0
                if isinstance(status, str):
                    tail = status.split()[-1]
                    n = int(tail) if tail.isdigit() else 0
                return Result([], rowcount=n)
        except Exception as e:
            logger.error(f"❌ Error SQL: {e} | Query: {query[:300]} | Params: {params}")
            raise

    async def _table_has_id(self, table: str) -> bool:
        if self._id_tables is None:
            async with self._conn() as (conn, _):
                recs = await conn.fetch(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND column_name = 'id'")
            self._id_tables = {r["table_name"] for r in recs}
        if table not in self._id_tables:
            # tabla creada después del cache (init_tables) → verificar puntualmente
            async with self._conn() as (conn, _):
                recs = await conn.fetch(
                    "SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() "
                    "AND table_name = $1 AND column_name = 'id'", table)
            if recs:
                self._id_tables.add(table)
        return table in self._id_tables

    # ───────────── API pública (contrato TursoDatabase) ─────────────
    async def execute(self, query: str, params: Optional[Union[tuple, list]] = None) -> Any:
        return await self._do(query, params)

    async def fetch_all(self, query: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
        return (await self._do(query, params)).fetchall()

    async def fetch_one(self, query: str, params: Optional[Tuple] = None) -> Optional[Dict[str, Any]]:
        rows = await self.fetch_all(query, params)
        return rows[0] if rows else None

    @asynccontextmanager
    async def transaction(self):
        if _tx_conn.get() is not None:
            yield self
            return
        if not self._connected:
            await self.connect()
        async with self.pool.acquire() as conn:  # type: ignore[union-attr]
            async with conn.transaction():
                token = _tx_conn.set(conn)
                try:
                    yield self
                finally:
                    _tx_conn.reset(token)

    async def execute_batch(self, operations: List[Tuple[str, Optional[Union[tuple, list]]]],
                            suppress_auto_sync: bool = False) -> None:
        if not operations:
            return
        async with self.transaction():
            for query, params in operations:
                await self.execute(query, params)

    async def executemany(self, query: str, params_list: List[Union[tuple, list]],
                          suppress_auto_sync: bool = False) -> None:
        if not params_list:
            return
        async with self.transaction():
            for p in params_list:
                await self.execute(query, p)

    async def execute_script(self, script_sql: str) -> None:
        async with self.transaction():
            for stmt in split_statements(script_sql):
                await self.execute(stmt)

    # ───────────── metadatos ─────────────
    async def get_column_names(self, table_name: str) -> List[str]:
        if table_name in self._schema_cache:
            return self._schema_cache[table_name]
        rows = await self.fetch_all(
            "SELECT column_name AS name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ? ORDER BY ordinal_position",
            (table_name.lower(),))
        cols = [r["name"] for r in rows]
        if cols:
            self._schema_cache[table_name] = cols
        return cols

    async def get_table_names(self) -> List[str]:
        rows = await self.fetch_all(
            "SELECT table_name AS name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'")
        return [r["name"] for r in rows]

    async def column_exists(self, table_name: str, column_name: str) -> bool:
        return column_name in await self.get_column_names(table_name)

    async def table_exists(self, table_name: str) -> bool:
        row = await self.fetch_one(
            "SELECT table_name AS name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = ?", (table_name.lower(),))
        return row is not None

    async def clear_schema_cache(self) -> None:
        self._schema_cache.clear()
        self._id_tables = None

    async def save_setting(self, clave: str, valor: str):
        try:
            await self.execute("INSERT OR REPLACE INTO ajustes (clave, valor) VALUES (?, ?)", (clave, str(valor)))
        except Exception as e:
            logger.error(f"⚠️ No se pudo persistir ajuste {clave}: {e}")

    async def health_check(self) -> Dict[str, Any]:
        try:
            if not self._connected:
                return {"status": "disconnected", "turso": False, "local": False}
            r = await self.fetch_one("SELECT 1 AS ok")
            ok = r is not None and r.get("ok") == 1
            return {"status": "healthy" if ok else "degraded", "local": ok, "turso": False, "mode": "postgres"}
        except Exception as e:
            return {"status": "error", "error": str(e), "local": False, "turso": False}


# Alias de compatibilidad (el código importa 'Database' / 'HybridDatabase' / 'TursoDatabase')
Database = PostgresDatabase
HybridDatabase = PostgresDatabase
TursoDatabase = PostgresDatabase

# Singleton global
db = PostgresDatabase()


async def get_db() -> PostgresDatabase:
    """Dependency injection para FastAPI"""
    if not db._connected:
        await db.connect()
    return db
