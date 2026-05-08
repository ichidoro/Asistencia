import os
import sqlite3
import libsql
import asyncio
import aiohttp
import json
from backend.core.config import settings

async def fetch_row_http(session, url, token, table, rid):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    body = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": f"SELECT * FROM {table} WHERE rowid = ?",
                    "args": [{"type": "integer", "value": str(rid)}]
                }
            },
            {"type": "close"}
        ]
    }
    try:
        async with session.post(f"{url}/v2/pipeline", headers=headers, json=body) as resp:
            data = await resp.json()
            if "results" in data and len(data["results"]) > 0:
                res = data["results"][0]
                if res["type"] == "ok":
                    rows = res["response"]["result"]["rows"]
                    if rows:
                        # Convert values
                        mapped_row = []
                        for col in rows[0]:
                            if col["type"] == "integer":
                                mapped_row.append(int(col["value"]))
                            elif col["type"] == "float":
                                mapped_row.append(float(col["value"]))
                            elif col["type"] == "text":
                                mapped_row.append(col["value"])
                            elif col["type"] == "blob":
                                mapped_row.append(col["base64"])
                            else:
                                mapped_row.append(None)
                        return rid, mapped_row
    except Exception as e:
        pass
    return rid, None

async def process_batch(session, url, token, table, rids):
    tasks = [fetch_row_http(session, url, token, table, rid) for rid in rids]
    return await asyncio.gather(*tasks)

async def rescue_table_async(url, token, table, rowids, cur_local, conn_local):
    print(f"IDs encontrados: {len(rowids)}", flush=True)
    success = 0
    failed = 0
    
    async with aiohttp.ClientSession() as session:
        batch_size = 50
        for i in range(0, len(rowids), batch_size):
            batch = rowids[i:i+batch_size]
            results = await process_batch(session, url, token, table, batch)
            
            for rid, row in results:
                if row:
                    placeholders = ",".join(["?"] * len(row))
                    cur_local.execute(f"INSERT INTO {table} VALUES ({placeholders})", row)
                    success += 1
                else:
                    failed += 1
            conn_local.commit()
            print(f"Progreso {table}: {i+len(batch)}/{len(rowids)} - OK: {success}, FAIL: {failed}", flush=True)

    print(f"Finalizado para {table}: Rescatados {success}, Fallidos {failed}.", flush=True)

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
    
    url = settings.TURSO_DATABASE_URL.replace("libsql://", "https://")
    token = settings.TURSO_AUTH_TOKEN

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
                asyncio.run(rescue_table_async(url, token, table, rowids, cur_local, conn_local))
            except Exception as outer_e:
                print(f"Fallo total al rescatar {table}: {outer_e}", flush=True)

    print("\nProceso de rescate finalizado!", flush=True)
    conn_local.close()

if __name__ == "__main__":
    rescue()
