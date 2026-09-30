"""
Carga un archivo SQLite (copia de Turso, ver dump_turso.py) en PostgreSQL.

Requisito: el esquema ya existe en Postgres (arrancar la app una vez con DATABASE_URL
apuntando a la BD vacía: init_tables crea todo).

Uso:
  DATABASE_URL=postgresql://user:pass@host:5432/db python scripts/load_sqlite_to_postgres.py turso_copy.db [--keep]

Por defecto TRUNCA las tablas destino antes de cargar (--keep las conserva y usa ON CONFLICT DO NOTHING).
"""
import asyncio
import os
import sqlite3
import sys
from decimal import Decimal

import asyncpg

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from backend.core.sql_compat import convert_placeholders, translate_sql  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

SKIP_SUFFIXES = ("_corrupt", "_new", "_old", "_bak")


def conv(v, pgtype):
    if v is None:
        return None
    if pgtype in ("integer", "bigint", "smallint"):
        if isinstance(v, str):
            v = v.strip()
            return None if v == "" else int(float(v))
        return int(v)
    if pgtype in ("numeric", "double precision", "real"):
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                return None
        return Decimal(str(v)) if pgtype == "numeric" else float(v)
    if pgtype == "boolean":
        return bool(v)
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v if isinstance(v, str) else str(v)


async def main(path: str, keep: bool):
    dsn = os.environ["DATABASE_URL"]
    src = sqlite3.connect(path)
    src.row_factory = sqlite3.Row
    pg = await asyncpg.connect(dsn)
    pg_tables = {r["table_name"] for r in await pg.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")}
    src_tables = [r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    missing = [t for t in src_tables if t not in pg_tables and not t.endswith(SKIP_SUFFIXES)]
    for t in missing:  # tablas que la app crea de forma perezosa: crearlas desde el DDL original
        ddl = src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()[0]
        await pg.execute(translate_sql(ddl))
        for (isql,) in src.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL", (t,)):
            await pg.execute(translate_sql(isql))
        print(f"   (tabla creada desde DDL de origen: {t})")
    pg_tables |= set(missing)
    tables = [t for t in src_tables if t in pg_tables and not t.endswith(SKIP_SUFFIXES)]

    async with pg.transaction():
        await pg.execute("SET LOCAL session_replication_role = 'replica'")  # FKs off durante la carga
        if not keep:
            await pg.execute("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE")
        total = 0
        for t in tables:
            cols_pg = {r["column_name"]: r["data_type"] for r in await pg.fetch(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name=$1", t)}
            cur = src.execute(f'SELECT * FROM "{t}"')
            names = [d[0] for d in cur.description]
            use = [n for n in names if n in cols_pg]
            dropped = [n for n in names if n not in cols_pg]
            rows = cur.fetchall()
            if dropped:
                print(f"   ({t}: columnas sin destino ignoradas: {dropped})")
            if not rows:
                print(f"  {t:36s} 0")
                continue
            data = [tuple(conv(r[n], cols_pg[n]) for n in use) for r in rows]
            q = f'INSERT INTO "{t}" ({",".join(chr(34)+n+chr(34) for n in use)}) VALUES ({",".join("$%d" % (i+1) for i in range(len(use)))})'
            if keep:
                q += " ON CONFLICT DO NOTHING"
            await pg.executemany(q, data)
            total += len(data)
            print(f"  {t:36s} {len(data)}")
        # secuencias SERIAL → max(id)+1
        for t in tables:
            if not await pg.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=$1 AND column_name='id'", t):
                continue
            seq = await pg.fetchval("SELECT pg_get_serial_sequence($1, 'id')", f'"{t}"')
            if seq:
                await pg.execute(f'SELECT setval($1, COALESCE((SELECT MAX(id) FROM "{t}"), 0) + 1, false)', seq)
    print(f"\n✅ {total} filas cargadas en {len(tables)} tablas")
    await pg.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], "--keep" in sys.argv))
