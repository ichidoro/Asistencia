import os
import sqlite3
import libsql
from backend.core.config import settings

def rescue():
    print("Conectando a Turso...")
    conn_turso = libsql.connect(database=settings.TURSO_DATABASE_URL, auth_token=settings.TURSO_AUTH_TOKEN)
    cur_turso = conn_turso.cursor()

    if os.path.exists("rescued.db"):
        os.remove("rescued.db")
    
    print("Creando base de datos local rescued.db...")
    conn_local = sqlite3.connect("rescued.db")
    cur_local = conn_local.cursor()

    # 1. Obtener schema
    cur_turso.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")
    schema = cur_turso.fetchall()

    for obj_type, name, sql in schema:
        try:
            print(f"Creando {obj_type} {name}...", flush=True)
            cur_local.execute(sql)
        except Exception as e:
            print(f"Error creando {name}: {e}", flush=True)

    # 2. Copiar data
    tables = [name for obj_type, name, sql in schema if obj_type == 'table']
    
    for table in tables:
        print(f"\n--- Rescatando tabla: {table} ---", flush=True)
        try:
            cur_turso.execute(f"SELECT * FROM {table}")
            rows = cur_turso.fetchall()
            if not rows:
                print("Vacía o no se pudo leer globalmente.", flush=True)
                continue
            
            placeholders = ",".join(["?"] * len(rows[0]))
            cur_local.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
            conn_local.commit()
            print(f"Exito! Rescatados {len(rows)} registros.", flush=True)
        except Exception as e:
            print(f"Error global en {table}: {e}", flush=True)
            print("Intentando rescate fila por fila usando PK...", flush=True)
            try:
                # Intentar obtener los IDs
                cur_turso.execute(f"SELECT rowid FROM {table}")
                rowids = cur_turso.fetchall()
                print(f"IDs encontrados: {len(rowids)}", flush=True)
                success = 0
                for i, (rid,) in enumerate(rowids):
                    if i % 100 == 0:
                        print(f"Progreso {table}: {i}/{len(rowids)}", flush=True)
                    try:
                        cur_turso.execute(f"SELECT * FROM {table} WHERE rowid = {rid}")
                        row = cur_turso.fetchone()
                        if row:
                            placeholders = ",".join(["?"] * len(row))
                            cur_local.execute(f"INSERT INTO {table} VALUES ({placeholders})", row)
                            success += 1
                    except Exception as inner_e:
                        pass
                conn_local.commit()
                print(f"Rescatados {success} registros fila por fila.", flush=True)
            except Exception as outer_e:
                print(f"Fallo total al rescatar {table}: {outer_e}", flush=True)

    print("\nProceso de rescate finalizado!", flush=True)
    conn_local.close()

if __name__ == "__main__":
    rescue()
