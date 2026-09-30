"""
Script ETL Automatizado de Migración: Turso Cloud (LibSQL) -> PostgreSQL 16 On-Premise
Sistema de Control de Asistencia - AGUACOL SpA

Uso:
  1. Configurar variables de entorno en .env:
       TURSO_DATABASE_URL="libsql://aguacol-ichidoro.aws-us-east-1.turso.io"
       TURSO_AUTH_TOKEN="tu_token_turso"
       DATABASE_URL="postgresql://aguacol_admin:password@localhost:5432/asistencia_db"
  2. Ejecutar:
       python scripts/migrate_turso_to_postgres.py
"""

import asyncio
import os
import sys
import time
from typing import List, Dict, Any

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath(".venv/Lib/site-packages"))
sys.path.insert(0, os.path.abspath("."))

import dotenv
dotenv.load_dotenv()

import asyncpg
from backend.core.database import TursoDatabase

# Orden de migración estricto para satisfacer restricciones de Foreign Keys
TABLE_ORDER = [
    # 1. Catálogos base independientes
    "areas",
    "cargos",
    "roles",
    "permisos",
    "estados_asistencia",
    "justificacion_tipos",
    "feriados",
    "ajustes",
    "cat_generos",
    "cat_pagadores",
    "notificaciones_areas",
    "porteria_ubicaciones",
    "porteria_catalogo_hallazgos",
    "productos_elaboracion_propia",
    
    # 2. Entidades principales
    "usuarios",
    "empleados",
    "turnos",
    "flota_aguacol",
    "llaves_maestro",
    
    # 3. Tablas relacionales y configuraciones dependientes
    "turno_dias",
    "turno_areas",
    "asignacion_turnos",
    "historial_areas",
    "rol_permisos",
    "areas_alias",
    "cargos_alias",
    "periodos_rrhh",
    "periodos_empleo",
    "bonos",
    "bono_reglas",
    "bono_asignaciones",
    "area_bonos",
    
    # 4. Transaccionales primarias (Marcaciones de reloj)
    "logs_raw",
    "justificaciones",
    "visitas_registros",
    "llaves_registros",
    "flota_registros",
    "porteria_rondas_registro",
    "porteria_rondas_hallazgos",
    "articulo22_registros",
    "empleado_productos_periodo",
    "productos_4_cierres",
    
    # 5. Transaccionales calculadas (Motor Cuántico QME)
    "asistencias",
    "horas_extras",
    "jornadas_especiales",
    "intercambios_dias",
    "viajes_largos",
    "compensaciones_he_inasistencia",
    
    # 6. Auditoría y Cierres
    "cierres_periodos",
    "sync_logs",
    "logs_auditoria",
    
    # 7. ADMS Biométrico
    "adms_dispositivos",
    "adms_usuarios",
    "adms_operlog",
]

async def create_postgres_schema(pg_conn: asyncpg.Connection):
    print("🔨 Creando extensiones y tablas en PostgreSQL...")
    await pg_conn.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")
    
    # Deshabilitar FK checks temporalmente para creación y carga limpia
    await pg_conn.execute("SET session_replication_role = 'replica';")

async def migrate_table(db_turso: TursoDatabase, pg_conn: asyncpg.Connection, table_name: str):
    # 1. Obtener columnas en Turso
    cols_turso = await db_turso.fetch_all(f"PRAGMA table_info(\"{table_name}\")")
    if not cols_turso:
        print(f"⚠️ Tabla '{table_name}' no existe en Turso. Omitiendo.")
        return 0

    col_names = [c['name'] for c in cols_turso]
    
    # 2. Contar registros en Turso
    cnt_row = await db_turso.fetch_one(f"SELECT count(*) as c FROM \"{table_name}\"")
    total_rows = cnt_row['c'] if cnt_row else 0
    if total_rows == 0:
        print(f"  [{table_name:32s}] 0 filas.")
        return 0

    # 3. Leer datos en bloques desde Turso
    chunk_size = 1000
    migrated = 0
    t_start = time.time()
    
    # Construir consulta INSERT en Postgres con placeholders $1, $2...
    cols_quoted = [f'"{c}"' for c in col_names]
    placeholders = [f"${i+1}" for i in range(len(col_names))]
    insert_sql = f'INSERT INTO "{table_name}" ({", ".join(cols_quoted)}) VALUES ({", ".join(placeholders)}) ON CONFLICT DO NOTHING'

    for offset in range(0, total_rows, chunk_size):
        query = f'SELECT * FROM "{table_name}" LIMIT {chunk_size} OFFSET {offset}'
        rows = await db_turso.fetch_all(query)
        if not rows:
            break

        # Convertir rows a tuplas respetando tipos
        tuples = []
        for r in rows:
            tup = []
            for col in col_names:
                val = r.get(col)
                tup.append(val)
            tuples.append(tuple(tup))

        await pg_conn.executemany(insert_sql, tuples)
        migrated += len(tuples)

    t_elap = round(time.time() - t_start, 2)
    print(f"  [{table_name:32s}] {migrated:6d}/{total_rows:6d} filas migradas en {t_elap}s.")

    # 4. Ajustar secuencias si la tabla tiene ID auto-incremental
    if "id" in col_names:
        try:
            seq_query = f"""
                SELECT setval(pg_get_serial_sequence('"{table_name}"', 'id'), 
                              COALESCE((SELECT MAX(id) FROM "{table_name}"), 1) + 1, false)
            """
            await pg_conn.execute(seq_query)
        except Exception:
            pass  # Si no tiene secuencia serial, ignorar

    return migrated

async def main():
    pg_dsn = os.getenv("DATABASE_URL")
    if not pg_dsn or "postgres" not in pg_dsn:
        print("❌ Error: Variable DATABASE_URL debe apuntar a una instancia de PostgreSQL válida.")
        print("   Ejemplo: postgresql://aguacol_admin:password@localhost:5432/asistencia_db")
        return

    print("=========================================================================================")
    print("   ETL DE MIGRACIÓN: TURSO CLOUD (LIBSQL) ➔ POSTGRESQL 16 ON-PREMISE")
    print("=========================================================================================")

    # Conectar Turso
    print("🔌 Conectando a Turso Cloud...")
    db_turso = TursoDatabase()
    await db_turso.connect()

    # Conectar Postgres
    print(f"🔌 Conectando a PostgreSQL Local...")
    pg_conn = await asyncpg.connect(pg_dsn)

    t0 = time.time()
    try:
        await create_postgres_schema(pg_conn)
        
        print("\n🚀 Iniciando migración de datos por tabla:")
        total_migrated = 0
        for tname in TABLE_ORDER:
            cnt = await migrate_table(db_turso, pg_conn, tname)
            total_migrated += cnt

        # Reactivar integridad referencial de FKs
        await pg_conn.execute("SET session_replication_role = 'default';")

        t_total = round(time.time() - t0, 1)
        print(f"\n🎉 MIGRACIÓN COMPLETA: {total_migrated} registros transferidos en {t_total} segundos!")

    finally:
        await pg_conn.close()
        await db_turso.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
