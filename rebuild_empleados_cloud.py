"""
Reconstruye la tabla 'empleados' en Turso Cloud via HTTP API
para eliminar la corrupcion del B-Tree.
"""
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

def turso_pipeline(statements):
    endpoint = f"{turso_url}/v2/pipeline"
    requests = [{"type": "execute", "stmt": {"sql": s}} for s in statements]
    requests.append({"type": "close"})
    data = json.dumps({"requests": requests}).encode()
    req = urllib.request.Request(
        endpoint, data=data,
        headers={'Authorization': f'Bearer {turso_token}', 'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def turso_query(sql):
    result = turso_pipeline([sql])
    res = result['results'][0]
    if res['type'] == 'error':
        raise Exception(res['error']['message'])
    data = res['response']['result']
    cols = [c['name'] for c in data['cols']]
    rows = []
    for row in data['rows']:
        r = {}
        for i, col in enumerate(cols):
            v = row[i]
            r[col] = v['value'] if v['type'] != 'null' else None
        rows.append(r)
    return cols, rows

# 1. Leer el schema actual de empleados
print("=== 1. Leyendo schema de empleados ===")
cols, rows = turso_query("SELECT sql FROM sqlite_master WHERE type='table' AND name='empleados'")
schema_sql = rows[0]['sql']
print(f"Schema: {schema_sql[:120]}...")

# 2. Leer todos los indices de empleados
print("\n=== 2. Leyendo indices de empleados ===")
cols, index_rows = turso_query("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='empleados' AND sql IS NOT NULL")
print(f"Indices: {len(index_rows)}")
for idx in index_rows:
    print(f"  - {idx['name']}")

# 3. Leer todos los datos de empleados
print("\n=== 3. Leyendo datos de empleados desde Turso ===")
cols_emp, rows_emp = turso_query("SELECT * FROM empleados ORDER BY id")
print(f"Empleados: {len(rows_emp)} filas, {len(cols_emp)} columnas")

# 4. Reconstruir: renombrar, recrear, insertar, borrar vieja
print("\n=== 4. Reconstruyendo tabla empleados en Turso Cloud ===")

# Paso A: Renombrar tabla a backup
print("  A. Renombrando a empleados_backup...")
result = turso_pipeline(["ALTER TABLE empleados RENAME TO empleados_backup"])
if result['results'][0]['type'] == 'error':
    print(f"  ERROR: {result['results'][0]['error']}")
else:
    print("  OK")

# Paso B: Crear tabla nueva
print("  B. Creando tabla nueva...")
result = turso_pipeline([schema_sql])
if result['results'][0]['type'] == 'error':
    print(f"  ERROR: {result['results'][0]['error']}")
else:
    print("  OK")

# Paso C: Re-crear indices
print("  C. Recreando indices...")
for idx in index_rows:
    result = turso_pipeline([idx['sql']])
    status = "OK" if result['results'][0]['type'] == 'ok' else f"ERR: {result['results'][0].get('error', {}).get('message', '')}"
    print(f"    {idx['name']}: {status}")

# Paso D: Insertar datos en batches de 50
print(f"  D. Insertando {len(rows_emp)} filas en batches...")
cols_str = ', '.join(f'"{c}"' for c in cols_emp)
batch_size = 50
inserted = 0
for i in range(0, len(rows_emp), batch_size):
    batch = rows_emp[i:i+batch_size]
    stmts = []
    for row in batch:
        vals = []
        args = []
        for c in cols_emp:
            v = row[c]
            if v is None:
                vals.append('NULL')
            else:
                vals.append('?')
                args.append({"type": "text", "value": str(v)})
        vals_str = ', '.join(vals)
        stmts.append({
            "type": "execute",
            "stmt": {
                "sql": f"INSERT INTO empleados ({cols_str}) VALUES ({vals_str})",
                "args": args
            }
        })
    stmts.append({"type": "close"})
    endpoint = f"{turso_url}/v2/pipeline"
    data = json.dumps({"requests": stmts}).encode()
    req = urllib.request.Request(endpoint, data=data,
        headers={'Authorization': f'Bearer {turso_token}', 'Content-Type': 'application/json'},
        method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.loads(r.read())
    errors = [x for x in res['results'] if x['type'] == 'error']
    if errors:
        print(f"    Batch {i//batch_size+1} ERRORS: {errors[0]['error']['message']}")
        break
    inserted += len(batch)
    print(f"    Batch {i//batch_size+1}: {inserted}/{len(rows_emp)} insertados")

# Paso E: Borrar tabla backup
print("  E. Eliminando tabla backup...")
result = turso_pipeline(["DROP TABLE IF EXISTS empleados_backup"])
status = "OK" if result['results'][0]['type'] == 'ok' else f"ERR: {result['results'][0]['error']['message']}"
print(f"  {status}")

# 5. Verificar
print("\n=== 5. Verificacion final ===")
try:
    cols, rows = turso_query("SELECT COUNT(*) as c FROM empleados")
    print(f"empleados: {rows[0]['c']} filas OK")
    cols, rows = turso_query("SELECT COUNT(*) as c FROM empleados e LEFT JOIN historial_areas ha ON e.id = ha.empleado_id WHERE e.activo = 1")
    print(f"JOIN empleados+historial_areas: {rows[0]['c']} filas OK")
    cols, rows = turso_query("SELECT COUNT(*) as c FROM empleados e WHERE e.activo = 1 AND e.fecha_nacimiento IS NOT NULL AND CAST(substr(fecha_nacimiento, 6, 2) AS INTEGER) = 5")
    print(f"Query cumpleanos (la que fallaba): {rows[0]['c']} filas OK")
except Exception as e:
    print(f"ERROR: {e}")

print("\nReconstruccion de empleados en Turso Cloud completada.")
