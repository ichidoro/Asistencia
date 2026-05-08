import sqlite3
import asyncio
import aiohttp
from backend.core.config import settings

async def execute_http(session, url, token, statements):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    requests = [{"type": "execute", "stmt": stmt} for stmt in statements]
    requests.append({"type": "close"})
    
    body = {"requests": requests}
    async with session.post(f"{url}/v2/pipeline", headers=headers, json=body) as resp:
        return await resp.json()

def type_mapper(val):
    if val is None:
        return {"type": "null"}
    if isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    if isinstance(val, float):
        return {"type": "float", "value": val}
    if isinstance(val, str):
        return {"type": "text", "value": val}
    if isinstance(val, bytes):
        import base64
        return {"type": "blob", "base64": base64.b64encode(val).decode('utf-8')}
    return {"type": "text", "value": str(val)}

async def upload():
    print("Conectando...", flush=True)
    conn_local = sqlite3.connect("rescued.db")
    cur_local = conn_local.cursor()
    
    url = settings.TURSO_DATABASE_URL.replace("libsql://", "https://")
    token = settings.TURSO_AUTH_TOKEN
    
    cur_local.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cur_local.fetchall()]
    
    async with aiohttp.ClientSession() as session:
        # 1. DELETE FROM all tables
        print("Limpiando base de datos...", flush=True)
        for t in tables:
            print(f"Limpiando {t}...", flush=True)
            res = await execute_http(session, url, token, [{"sql": f"DELETE FROM {t}"}])
            if "results" not in res:
                print(f"Error limpiando {t}: {res}", flush=True)
        print("Limpieza completada.", flush=True)
        
        # 2. UPLOAD DATA
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
                
                stmts = []
                for row in batch:
                    args = [type_mapper(v) for v in row]
                    stmts.append({"sql": sql, "args": args})
                
                res = await execute_http(session, url, token, stmts)
                # Count successes
                if "results" in res:
                    for r in res["results"]:
                        if r["type"] == "ok":
                            success += 1
                else:
                    print(f"Error en lote: {res}", flush=True)
                
                print(f"Subiendo... {success}/{len(rows)}", flush=True)
                
            print(f"Tabla {table} completada.", flush=True)

    print("\nPROCESO FINALIZADO!", flush=True)

if __name__ == "__main__":
    asyncio.run(upload())
