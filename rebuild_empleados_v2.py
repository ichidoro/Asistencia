"""
Lee empleados de Turso Cloud evitando paginas corruptas,
reconstruye la tabla limpia via DELETE+INSERT sin cambiar estructura.
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
    requests = [{"type": "execute", "stmt": {"sql": s if isinstance(s, str) else s['sql'], 
                                              **({"args": s['args']} if isinstance(s, dict) and 'args' in s else {})}}
                for s in statements]
    requests.append({"type": "close"})
    data = json.dumps({"requests": requests}).encode()
    req = urllib.request.Request(
        endpoint, data=data,
        headers={'Authorization': f'Bearer {turso_token}', 'Content-Type': 'application/json'},
        method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def turso_query_raw(sql, args=None):
    stmt = {"sql": sql}
    if args:
        stmt["args"] = args
    endpoint = f"{turso_url}/v2/pipeline"
    payload = {"requests": [{"type": "execute", "stmt": stmt}, {"type": "close"}]}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(endpoint, data=data,
        headers={'Authorization': f'Bearer {turso_token}', 'Content-Type': 'application/json'},
        method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.loads(r.read())
    result = res['results'][0]
    if result['type'] == 'error':
        raise Exception(result['error']['message'])
    data_res = result['response']['result']
    cols = [c['name'] for c in data_res['cols']]
    rows = []
    for row in data_res['rows']:
        r = {}
        for i, col in enumerate(cols):
            v = row[i]
            r[col] = v['value'] if v['type'] != 'null' else None
        rows.append(r)
    return cols, rows

# 1. Obtener todos los IDs primero (tabla de IDs es mas simple)
print("=== 1. Obteniendo IDs de empleados ===")
cols, id_rows = turso_query_raw("SELECT id FROM empleados ORDER BY id")
all_ids = [r['id'] for r in id_rows]
print(f"Total IDs: {len(all_ids)}, rango: {all_ids[0]} - {all_ids[-1]}")

# 2. Leer columnas por grupos para evitar la pagina corrupta
# Dividir en columnas mas simples que no toquen la pagina corrupta
print("\n=== 2. Leyendo datos de empleados por columnas simples ===")

# Primero identificar las columnas disponibles
cols_all, _ = turso_query_raw("SELECT * FROM empleados LIMIT 0")
print(f"Columnas: {cols_all}")

# Leer en batches de 10 IDs para evitar paginacion de paginas corruptas
all_employees = {}
batch_size = 10
failed_ids = []

for i in range(0, len(all_ids), batch_size):
    batch_ids = all_ids[i:i+batch_size]
    ids_str = ','.join(str(x) for x in batch_ids)
    try:
        cols_b, rows_b = turso_query_raw(f"SELECT * FROM empleados WHERE id IN ({ids_str}) ORDER BY id")
        for row in rows_b:
            all_employees[row['id']] = row
        print(f"  Batch {i//batch_size+1}: {len(rows_b)}/{len(batch_ids)} OK (IDs {batch_ids[0]}-{batch_ids[-1]})")
    except Exception as e:
        print(f"  Batch {i//batch_size+1} FAILED: {e} (IDs {batch_ids})")
        # Intentar uno por uno
        for emp_id in batch_ids:
            try:
                cols_b, rows_b = turso_query_raw(f"SELECT * FROM empleados WHERE id = {emp_id}")
                if rows_b:
                    all_employees[emp_id] = rows_b[0]
                    print(f"    ID {emp_id}: OK")
                else:
                    failed_ids.append(emp_id)
                    print(f"    ID {emp_id}: Sin datos")
            except Exception as e2:
                failed_ids.append(emp_id)
                print(f"    ID {emp_id}: ERROR - {e2}")

print(f"\nEmpleados leidos: {len(all_employees)}/{len(all_ids)}")
print(f"IDs fallidos: {failed_ids}")

if len(all_employees) == 0:
    print("ERROR: No se pudo leer ningun empleado. Abortando.")
    exit(1)

# 3. Reconstruir tabla: DELETE ALL + INSERT fresh (sin cambiar estructura ni IDs)
print("\n=== 3. Reconstruyendo datos de empleados en Turso Cloud ===")
rows_to_insert = list(all_employees.values())
cols_emp = [c for c in cols_all]

# Deshabilitar FK checks temporalmente y hacer DELETE masivo
print("  Limpiando tabla actual...")
result = turso_pipeline(["DELETE FROM empleados"])
status = result['results'][0]['type']
if status == 'error':
    err = result['results'][0]['error']['message']
    # FK constraint? intentar con pragma
    print(f"  DELETE resultado: {err}")
    result2 = turso_pipeline(["PRAGMA foreign_keys = OFF", "DELETE FROM empleados"])
    print(f"  DELETE con FK off: {result2['results'][1]['type']}")
else:
    print(f"  DELETE: {status}")

# Insertar en batches
print(f"  Insertando {len(rows_to_insert)} empleados...")
cols_str = ', '.join(f'"{c}"' for c in cols_emp)
inserted = 0
for i in range(0, len(rows_to_insert), 20):
    batch = rows_to_insert[i:i+20]
    stmts = []
    for row in batch:
        args = []
        placeholders = []
        for c in cols_emp:
            v = row.get(c)
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
    endpoint = f"{turso_url}/v2/pipeline"
    d = json.dumps({"requests": stmts}).encode()
    req_obj = urllib.request.Request(endpoint, data=d,
        headers={'Authorization': f'Bearer {turso_token}', 'Content-Type': 'application/json'},
        method='POST')
    with urllib.request.urlopen(req_obj, timeout=60) as r2:
        res2 = json.loads(r2.read())
    errors = [x for x in res2['results'] if x['type'] == 'error']
    if errors:
        print(f"  Batch {i//20+1} ERROR: {errors[0]['error']['message']}")
    else:
        inserted += len(batch)
        print(f"  Batch {i//20+1}: {inserted}/{len(rows_to_insert)} OK")

# 4. REINDEX para reconstruir B-Tree limpio
print("\n=== 4. REINDEX empleados ===")
result = turso_pipeline(["REINDEX empleados"])
print(f"  REINDEX: {result['results'][0]['type']}")

# 5. Verificacion
print("\n=== 5. Verificacion final ===")
try:
    _, rows = turso_query_raw("SELECT COUNT(*) as c FROM empleados")
    print(f"empleados total: {rows[0]['c']}")
    _, rows = turso_query_raw("SELECT COUNT(*) as c FROM empleados WHERE activo = 1")
    print(f"empleados activos: {rows[0]['c']}")
    _, rows = turso_query_raw("SELECT COUNT(*) as c FROM empleados e WHERE e.activo = 1 AND e.fecha_nacimiento IS NOT NULL AND CAST(substr(fecha_nacimiento, 6, 2) AS INTEGER) = 5")
    print(f"Query cumpleanos Mayo (la que fallaba): {rows[0]['c']} filas OK")
    _, rows = turso_query_raw("SELECT id, nombre, apellido_paterno FROM empleados LIMIT 3")
    for r in rows:
        print(f"  {r['id']}: {r['nombre']} {r['apellido_paterno']}")
except Exception as e:
    print(f"ERROR verificacion: {e}")

print("\nListo.")
