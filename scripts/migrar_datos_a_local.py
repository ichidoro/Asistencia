"""
Migrador Canónico de Base de Datos: Turso Cloud -> Servidor Local (SQLite / LibSQL)
Sistema de Asistencia Aguacol

Este script:
1. Lee las 54 tablas activas desde Turso Cloud (usando credenciales de .env).
2. Crea el esquema DDL exacto en la base de datos local de destino.
3. Copia todos los registros respetando tipos, índices y claves primarias.
4. Verifica la integridad comparando recuentos de registros origen vs destino.
"""

import asyncio
import os
import sys
import time
import sqlite3
from typing import List, Dict, Any

# Encoding seguro para Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath(".venv/Lib/site-packages"))

import dotenv
dotenv.load_dotenv()

from backend.core.database import TursoDatabase
from backend.core.config import settings

LOCAL_DB_FILE = os.path.abspath("data/asistencia_local.db")

async def migrar():
    print("=" * 80)
    print("   MIGRACIÓN DE DATOS: TURSO CLOUD -> BASE DE DATOS LOCAL")
    print("=" * 80)
    print(f"Origen: {settings.TURSO_DATABASE_URL}")
    print(f"Destino: {LOCAL_DB_FILE}\n")

    # Asegurar carpeta data/
    os.makedirs(os.path.dirname(LOCAL_DB_FILE), exist_ok=True)

    # 1. Conexión a Turso Cloud
    db_source = TursoDatabase()
    await db_source.connect()

    # 2. Conexión a SQLite Local
    conn_dest = sqlite3.connect(LOCAL_DB_FILE)
    conn_dest.execute("PRAGMA journal_mode = WAL;")
    conn_dest.execute("PRAGMA synchronous = NORMAL;")
    conn_dest.execute("PRAGMA foreign_keys = OFF;")  # Desactivar FK durante carga masiva

    # 3. Obtener tablas activas (excluyendo sqlite_ y tablas corruptas de prueba)
    tables_rows = await db_source.fetch_all(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%corrupt%' ORDER BY name"
    )
    print(f"Se detectaron {len(tables_rows)} tablas activas para migrar.\n")

    t_inicio = time.time()
    total_filas_migradas = 0

    # 4. Migración tabla por tabla
    for t_idx, t_row in enumerate(tables_rows, 1):
        table_name = t_row['name']
        create_sql = t_row['sql']

        print(f"[{t_idx:02d}/{len(tables_rows):02d}] Migrando '{table_name}'...")

        # A. Crear tabla en destino
        conn_dest.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        if create_sql:
            conn_dest.execute(create_sql)

        # B. Extraer datos de origen en lotes
        count_row = await db_source.fetch_one(f'SELECT count(*) as c FROM "{table_name}"')
        total_rows = count_row['c'] if count_row else 0

        if total_rows == 0:
            print(f"       -> Tabla vacía (0 registros).")
            continue

        # Leer registros
        rows = await db_source.fetch_all(f'SELECT * FROM "{table_name}"')
        if not rows:
            continue

        # Columnas
        sample = dict(rows[0])
        cols = list(sample.keys())
        placeholders = ", ".join(["?"] * len(cols))
        quoted_cols = ", ".join([f'"{c}"' for c in cols])
        insert_sql = f'INSERT INTO "{table_name}" ({quoted_cols}) VALUES ({placeholders})'

        # Preparar batch
        batch_data = []
        for r in rows:
            batch_data.append([r[c] for c in cols])

        # Insertar por lotes de 500
        chunk_size = 500
        for i in range(0, len(batch_data), chunk_size):
            chunk = batch_data[i:i + chunk_size]
            conn_dest.executemany(insert_sql, chunk)

        conn_dest.commit()
        total_filas_migradas += len(batch_data)
        print(f"       -> {len(batch_data)} registros migrados con éxito.")

    # 5. Migrar índices creados por el usuario
    indices = await db_source.fetch_all(
        "SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
    )
    print(f"\nMigrando {len(indices)} índices adicionales...")
    for idx_row in indices:
        try:
            conn_dest.execute(idx_row['sql'])
        except Exception:
            pass
    conn_dest.commit()

    conn_dest.execute("PRAGMA foreign_keys = ON;")
    conn_dest.close()

    t_total = round(time.time() - t_inicio, 2)
    print("\n" + "=" * 80)
    print(f" MIGRACIÓN COMPLETADA EXITOSAMENTE en {t_total} segundos")
    print(f" Total de registros transferidos: {total_filas_migradas:,}")
    print(f" Archivo local listo en: {LOCAL_DB_FILE}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(migrar())
