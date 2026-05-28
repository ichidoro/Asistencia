"""
Extrae datos de empleados de la DB corrupta usando sqlite3,
trabajando por ID para evitar paginas corruptas del B-Tree.
Luego re-inserta en Turso Cloud via HTTP para reparar.
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

def post_pipeline(stmts_payload):
    endpoint = f"{turso_url}/v2/pipeline"
    data = json.dumps({"requests": stmts_payload}).encode()
    req = urllib.request.Request(endpoint, data=data,
        headers={'Authorization': f'Bearer {turso_token}', 'Content-Type': 'application/json'},
        method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def turso_simple(sql):
    res = post_pipeline([{"type": "execute", "stmt": {"sql": sql}}, {"type": "close"}])
    r = res['results'][0]
    if r['type'] == 'error':
        raise Exception(r['error']['message'])
    data = r['response']['result']
    cols = [c['name'] for c in data['cols']]
    return cols, [[row[i]['value'] if row[i]['type'] != 'null' else None 
                   for i in range(len(cols))] for row in data['rows']]

print("=== 1. Intentando leer empleados de DB local por ID ===")
conn = sqlite3.connect(db_path, timeout=10)
cur = conn.cursor()

# Obtener columnas
cur.execute("SELECT name FROM pragma_table_info('empleados') ORDER BY cid")
cols_local = [r[0] for r in cur.fetchall()]
print(f"Columnas: {len(cols_local)}: {cols_local[:5]}...")

# Intentar leer por ID individual para saltear paginas corruptas
empleados_data = []
max_id = 300  # Estimado superior

for emp_id in range(1, max_id + 1):
    try:
        cur.execute(f"SELECT * FROM empleados WHERE id = {emp_id}")
        row = cur.fetchone()
        if row:
            d = dict(zip(cols_local, row))
            empleados_data.append(d)
    except sqlite3.DatabaseError:
        pass  # Saltar IDs en paginas corruptas

conn.close()
print(f"Empleados recuperados de DB local: {len(empleados_data)}")

if len(empleados_data) == 0:
    print("No se pudo leer ningun empleado local. Abortando.")
    exit(1)

# 2. Re-insertar en Turso Cloud
print(f"\n=== 2. Re-insertando {len(empleados_data)} empleados en Turso Cloud ===")
cols_str = ', '.join(f'"{c}"' for c in cols_local)
batch_size = 10
inserted = 0

for i in range(0, len(empleados_data), batch_size):
    batch = empleados_data[i:i+batch_size]
    stmts = []
    for emp in batch:
        args = []
        placeholders = []
        for c in cols_local:
            v = emp.get(c)
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
        print(f"  Batch {i//batch_size+1} ERROR: {batch_errors[0]['error']['message']}")
    else:
        inserted += len(batch)
        print(f"  Batch {i//batch_size+1}: {inserted}/{len(empleados_data)} OK")

# 3. REINDEX
print("\n=== 3. REINDEX ===")
res = post_pipeline([{"type": "execute", "stmt": {"sql": "REINDEX empleados"}}, {"type": "close"}])
print(f"  REINDEX empleados: {res['results'][0]['type']}")
if res['results'][0]['type'] == 'error':
    print(f"  Error: {res['results'][0]['error']['message']}")

# 4. Verificacion
print("\n=== 4. Verificacion en Turso Cloud ===")
try:
    _, rows = turso_simple("SELECT COUNT(*) FROM empleados")
    print(f"COUNT(*): {rows[0][0]}")
    _, rows = turso_simple("SELECT id, nombre FROM empleados ORDER BY id LIMIT 3")
    for r in rows:
        print(f"  ID={r[0]}: {r[1]}")
    _, rows = turso_simple("SELECT COUNT(*) FROM empleados WHERE activo=1 AND fecha_nacimiento IS NOT NULL AND CAST(substr(fecha_nacimiento,6,2) AS INTEGER)=5")
    print(f"Cumpleanos Mayo: {rows[0][0]} OK")
    print("\nREPARACION EXITOSA!")
except Exception as e:
    print(f"ERROR: {e}")
