import sqlite3
import libsql
from backend.core.config import settings
import sys

def upload():
    print("Conectando a base de datos local rescued.db...")
    try:
        conn_local = sqlite3.connect("rescued.db")
        cur_local = conn_local.cursor()
    except Exception as e:
        print(f"Error al abrir rescued.db: {e}")
        return

    print("Conectando a la nueva base de datos Turso...")
    try:
        conn_turso = libsql.connect(database=settings.TURSO_DATABASE_URL, auth_token=settings.TURSO_AUTH_TOKEN)
        cur_turso = conn_turso.cursor()
    except Exception as e:
        print(f"Error al conectar a Turso: {e}")
        return

    # 1. Obtener schema de la local
    cur_local.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")
    schema = cur_local.fetchall()

    for obj_type, name, sql in schema:
        try:
            print(f"Creando {obj_type} {name} en Turso...")
            cur_turso.execute(sql)
        except Exception as e:
            print(f"Aviso: {name} ya existe o hubo un error: {e}", flush=True)

    # 2. Subir data
    tables = [name for obj_type, name, sql in schema if obj_type == 'table']
    
    for table in tables:
        print(f"\n--- Subiendo tabla: {table} ---", flush=True)
        cur_local.execute(f"SELECT * FROM {table}")
        rows = cur_local.fetchall()
        if not rows:
            print("Tabla vacía.", flush=True)
            continue
            
        placeholders = ",".join(["?"] * len(rows[0]))
        sql = f"INSERT INTO {table} VALUES ({placeholders})"
        
        success = 0
        batch_size = 50
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            try:
                cur_turso.executemany(sql, batch)
                conn_turso.commit()
                success += len(batch)
                print(f"Exito! Subidos lote de {len(batch)} registros.", flush=True)
            except Exception as e:
                print(f"Fallo carga en lote para {table}: {e}", flush=True)
                print("Intentando carga fila por fila para este lote...", flush=True)
                for row in batch:
                    try:
                        cur_turso.execute(sql, row)
                        success += 1
                    except Exception as ie:
                        pass
                conn_turso.commit()
        print(f"Subidos {success}/{len(rows)} registros totales para {table}.", flush=True)

    print("\nProceso de subida finalizado! Tu base de datos ha sido restaurada.", flush=True)
    conn_local.close()
    conn_turso.close()

if __name__ == "__main__":
    print("Iniciando subida automatizada a Turso...", flush=True)
    upload()
