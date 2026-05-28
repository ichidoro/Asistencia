"""
Lee empleados desde la replica local (sqlite3) y los re-inserta en Turso Cloud
para reconstruir los frames del WAL y eliminar la corrupcion.
"""
import sqlite3
import urllib.request
import json
import os

env_path = '.env'
env = {}
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

turso_url = env.get('TURSO_DATABASE_URL', '').replace('libsql://', 'https://')
turso_token = env.get('TURSO_AUTH_TOKEN', '')
db_path = 'data/local_db/asistencia_local.db'

# 1. Leer datos de la replica local con sqlite3
print("=== 1. Leyendo datos de la replica local con sqlite3 ===")
conn = sqlite3.connect(db_path, timeout=10)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT * FROM empleados ORDER BY id")
rows_local = cur.fetchall()
cols_local = [d[0] for d in cur.description]
print(f"  Empleados leidos: {len(rows_local)}")
print(f"  Columnas: {cols_local}")
conn.close()

if not rows_local:
    print("ERROR: No hay datos en replica local. Abortando.")
    exit(1)

# Convertir a lista de dicts
empleados = []
for row in rows_local:
    d = {}
    for c in cols_local:
        d[c] = row[c]
    empleados.append(d)

# 2. Re-insertar en Turso Cloud con INSERT OR REPLACE
print(f"\n=== 2. Re-insertando {len(empleados)} empleados en Turso Cloud ===")

def post_pipeline(stmts_payload):
    endpoint = f"{turso_url}/v2/pipeline"
    data = json.dumps({"requests": stmts_payload}).encode()
    req = urllib.request.Request(endpoint, data=data,
        headers={'Authorization': f'Bearer {turso_token}', 'Content-Type': 'application/json'},
        method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

cols_str = ', '.join(f'"{c}"' for c in cols_local)
batch_size = 15
inserted = 0
errors_count = 0

for i in range(0, len(empleados), batch_size):
    batch = empleados[i:i+batch_size]
    stmts = []
    for emp in batch:
        args = []
        placeholders = []
        for c in cols_local:
            v = emp[c]
            if v is None:
                placeholders.append('NULL')
            else:
                placeholders.append('?')
                args.append({"type": "text", "value": str(v)})
        vals_str = ', '.join(placeholders)
        stmts.append({
            "type": "execute",
            "stmt": {
                "sql": f"INSERT OR REPLACE INTO empleados ({cols_str}) VALUES ({vals_str})",
                "args": args
            }
        })
    stmts.append({"type": "close"})
    
    res = post_pipeline(stmts)
    batch_errors = [x for x in res['results'] if x['type'] == 'error']
    if batch_errors:
        errors_count += 1
        print(f"  Batch {i//batch_size+1} ERROR: {batch_errors[0]['error']['message']}")
    else:
        inserted += len(batch)
        print(f"  Batch {i//batch_size+1}: {inserted}/{len(empleados)} OK")

print(f"\nResultado: {inserted} insertados, {errors_count} batches con error")

# 3. REINDEX ahora que los datos estan frescos
print("\n=== 3. REINDEX empleados en Turso Cloud ===")
res = post_pipeline([{"type": "execute", "stmt": {"sql": "REINDEX empleados"}}, {"type": "close"}])
status = res['results'][0]['type']
print(f"  REINDEX: {status}")
if status == 'error':
    print(f"  ERROR: {res['results'][0]['error']['message']}")

# 4. Verificacion final
print("\n=== 4. Verificacion final en Turso Cloud ===")
def turso_query_simple(sql):
    res = post_pipeline([{"type": "execute", "stmt": {"sql": sql}}, {"type": "close"}])
    r = res['results'][0]
    if r['type'] == 'error':
        raise Exception(r['error']['message'])
    data = r['response']['result']
    cols = [c['name'] for c in data['cols']]
    rows = []
    for row in data['rows']:
        d = {}
        for i2, col in enumerate(cols):
            v = row[i2]
            d[col] = v['value'] if v['type'] != 'null' else None
        rows.append(d)
    return rows

try:
    rows = turso_query_simple("SELECT COUNT(*) as c FROM empleados")
    print(f"empleados total: {rows[0]['c']}")
    
    rows = turso_query_simple("SELECT id, nombre FROM empleados ORDER BY id LIMIT 3")
    print(f"Primeros 3 empleados:")
    for r in rows:
        print(f"  ID={r['id']}: {r['nombre']}")
    
    rows = turso_query_simple("SELECT COUNT(*) as c FROM empleados WHERE activo=1 AND fecha_nacimiento IS NOT NULL AND CAST(substr(fecha_nacimiento,6,2) AS INTEGER)=5")
    print(f"Query cumpleanos Mayo (la que fallaba): {rows[0]['c']} filas OK")
    
    print("\nREPARACION EXITOSA en Turso Cloud!")
    print("Reiniciar el servidor para que sincronice los datos reparados.")
except Exception as e:
    print(f"Verificacion ERROR: {e}")
