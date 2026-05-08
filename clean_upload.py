import libsql
from backend.core.config import settings
import sqlite3

def clean_and_upload():
    print("Conectando a Turso...", flush=True)
    conn_turso = libsql.connect(database=settings.TURSO_DATABASE_URL, auth_token=settings.TURSO_AUTH_TOKEN)
    cur_turso = conn_turso.cursor()
    
    conn_local = sqlite3.connect("rescued.db")
    cur_local = conn_local.cursor()
    
    cur_local.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cur_local.fetchall()]
    
    # 1. Clear all existing data
    for table in tables:
        try:
            cur_turso.execute(f"DELETE FROM {table}")
            conn_turso.commit()
            print(f"Limpiada tabla {table}", flush=True)
        except Exception as e:
            print(f"No se pudo limpiar {table} (puede que no exista): {e}", flush=True)
            
    # 2. Upload
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
        print(f"Subidos {success}/{len(rows)} registros totales para {table}.", flush=True)

    print("\nProceso finalizado!", flush=True)
    conn_local.close()
    conn_turso.close()

if __name__ == "__main__":
    clean_and_upload()
