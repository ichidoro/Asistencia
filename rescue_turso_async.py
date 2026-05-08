import os
import sqlite3
import libsql
from backend.core.config import settings
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_row(table, rid):
    try:
        conn = libsql.connect(database=settings.TURSO_DATABASE_URL, auth_token=settings.TURSO_AUTH_TOKEN)
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table} WHERE rowid = ?", (rid,))
        row = cur.fetchone()
        conn.close()
        return rid, row
    except Exception as e:
        return rid, None

def rescue():
    print("Conectando a Turso...", flush=True)
    conn_turso = libsql.connect(database=settings.TURSO_DATABASE_URL, auth_token=settings.TURSO_AUTH_TOKEN)
    cur_turso = conn_turso.cursor()

    if os.path.exists("rescued.db"):
        os.remove("rescued.db")
    
    print("Creando base de datos local rescued.db...", flush=True)
    conn_local = sqlite3.connect("rescued.db")
    cur_local = conn_local.cursor()

    cur_turso.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")
    schema = cur_turso.fetchall()

    for obj_type, name, sql in schema:
        try:
            cur_local.execute(sql)
        except Exception as e:
            print(f"Error creando {name}: {e}", flush=True)

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
            print(f"Error global en {table}. Intentando rescate fila por fila...", flush=True)
            try:
                cur_turso.execute(f"SELECT rowid FROM {table}")
                rowids = [r[0] for r in cur_turso.fetchall()]
                print(f"IDs encontrados: {len(rowids)}", flush=True)
                
                success = 0
                failed = 0
                
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(fetch_row, table, rid): rid for rid in rowids}
                    for i, future in enumerate(as_completed(futures)):
                        rid, row = future.result()
                        if row:
                            placeholders = ",".join(["?"] * len(row))
                            cur_local.execute(f"INSERT INTO {table} VALUES ({placeholders})", row)
                            success += 1
                        else:
                            failed += 1
                            
                        if (i+1) % 100 == 0:
                            print(f"Progreso {table}: {i+1}/{len(rowids)} - OK: {success}, FAIL: {failed}", flush=True)
                            conn_local.commit()
                            
                conn_local.commit()
                print(f"Finalizado para {table}: Rescatados {success}, Fallidos {failed}.", flush=True)
            except Exception as outer_e:
                print(f"Fallo total al rescatar {table}: {outer_e}", flush=True)

    print("\nProceso de rescate finalizado!", flush=True)
    conn_local.close()

if __name__ == "__main__":
    rescue()
