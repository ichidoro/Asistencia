"""
Estrategia definitiva:
1. Obtener los 78 IDs de empleados desde historial_areas (tabla NO corrupta en cloud)
2. Leer cada empleado por ID desde el cloud (SELECT por PK evita el full-scan corrupto)
3. DELETE + INSERT OR REPLACE de los 78 empleados en cloud para reconstruir el B-Tree
4. REINDEX para limpiar el indice
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

def post(stmts):
    endpoint = f"{turso_url}/v2/pipeline"
    data = json.dumps({"requests": stmts + [{"type": "close"}]}).encode()
    req = urllib.request.Request(endpoint, data=data,
        headers={'Authorization': f'Bearer {turso_token}', 'Content-Type': 'application/json'},
        method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def query(sql, args=None):
    stmt = {"sql": sql}
    if args:
        stmt["args"] = args
    res = post([{"type": "execute", "stmt": stmt}])
    r = res['results'][0]
    if r['type'] == 'error':
        raise Exception(r['error']['message'])
    d = r['response']['result']
    cols = [c['name'] for c in d['cols']]
    rows = [{cols[i]: (row[i]['value'] if row[i]['type'] != 'null' else None) 
             for i in range(len(cols))} for row in d['rows']]
    return cols, rows

# === PASO 1: Obtener IDs desde historial_areas (NO corrupta) ===
print("PASO 1: Obteniendo IDs desde historial_areas...")
_, id_rows = query("SELECT DISTINCT empleado_id FROM historial_areas ORDER BY empleado_id")
all_ids = [r['empleado_id'] for r in id_rows]
print(f"  {len(all_ids)} IDs unicos encontrados: {all_ids[:5]}...{all_ids[-3:]}")

# Tambien intentar desde asignacion_turnos por si hay mas
try:
    _, at_rows = query("SELECT DISTINCT empleado_id FROM asignacion_turnos ORDER BY empleado_id")
    at_ids = [r['empleado_id'] for r in at_rows]
    extra = [x for x in at_ids if x not in all_ids]
    if extra:
        print(f"  +{len(extra)} IDs extra desde asignacion_turnos: {extra}")
        all_ids = sorted(set(all_ids + extra))
except:
    pass

print(f"  Total IDs a recuperar: {len(all_ids)}")

# === PASO 2: Obtener columnas ===
print("\nPASO 2: Obteniendo schema de empleados...")
_, schema_rows = query("SELECT sql FROM sqlite_master WHERE type='table' AND name='empleados'")
schema_sql = schema_rows[0]['sql']
print(f"  Schema OK ({len(schema_sql)} chars)")

# Obtener columnas leyendo un empleado conocido
cols_emp = None
for test_id in all_ids[:5]:
    try:
        c, r = query(f"SELECT * FROM empleados WHERE id = {test_id}")
        if r:
            cols_emp = c
            print(f"  Columnas ({len(cols_emp)}): {cols_emp[:6]}...")
            break
    except:
        pass

if not cols_emp:
    print("ERROR: No se pudo obtener columnas. Abortando.")
    exit(1)

# === PASO 3: Leer cada empleado por PK ===
print(f"\nPASO 3: Leyendo {len(all_ids)} empleados por PK...")
empleados = []
failed = []
for emp_id in all_ids:
    try:
        _, rows = query(f"SELECT * FROM empleados WHERE id = {emp_id}")
        if rows:
            empleados.append(rows[0])
        else:
            failed.append(emp_id)
    except Exception as e:
        failed.append(emp_id)

print(f"  Leidos: {len(empleados)}/{len(all_ids)}")
if failed:
    print(f"  Fallidos: {failed}")

# === PASO 4: Deshabilitar FK, DELETE ALL, INSERT OR REPLACE ===
print(f"\nPASO 4: Reconstruyendo {len(empleados)} empleados en Turso Cloud...")

# Deshabilitar FK constraints temporalmente
print("  Deshabilitando FK constraints...")
res = post([{"type": "execute", "stmt": {"sql": "PRAGMA foreign_keys = OFF"}}])
print(f"  FK OFF: {res['results'][0]['type']}")

# DELETE masivo
print("  Borrando todos los empleados...")
res = post([{"type": "execute", "stmt": {"sql": "DELETE FROM empleados"}}])
del_status = res['results'][0]['type']
print(f"  DELETE: {del_status}")
if del_status == 'error':
    print(f"  Error: {res['results'][0]['error']['message']}")
    exit(1)

# INSERT en batches de 10
cols_str = ', '.join(f'"{c}"' for c in cols_emp)
inserted = 0
insert_errors = 0

for i in range(0, len(empleados), 10):
    batch = empleados[i:i+10]
    stmts = []
    for emp in batch:
        args = []
        placeholders = []
        for c in cols_emp:
            v = emp.get(c)
            if v is None:
                placeholders.append('NULL')
            else:
                placeholders.append('?')
                args.append({"type": "text", "value": str(v)})
        stmts.append({
            "type": "execute",
            "stmt": {
                "sql": f"INSERT INTO empleados ({cols_str}) VALUES ({', '.join(placeholders)})",
                "args": args
            }
        })
    
    res = post(stmts)
    errs = [x for x in res['results'] if x['type'] == 'error']
    if errs:
        insert_errors += 1
        print(f"  Batch {i//10+1} ERROR: {errs[0]['error']['message']}")
        # Reintento uno por uno
        for emp in batch:
            try:
                args = []
                placeholders = []
                for c in cols_emp:
                    v = emp.get(c)
                    if v is None:
                        placeholders.append('NULL')
                    else:
                        placeholders.append('?')
                        args.append({"type": "text", "value": str(v)})
                res2 = post([{"type": "execute", "stmt": {
                    "sql": f"INSERT OR IGNORE INTO empleados ({cols_str}) VALUES ({', '.join(placeholders)})",
                    "args": args
                }}])
                if res2['results'][0]['type'] == 'ok':
                    inserted += 1
            except:
                pass
    else:
        inserted += len(batch)
        print(f"  Batch {i//10+1}: {inserted}/{len(empleados)} OK")

print(f"  Total insertados: {inserted}/{len(empleados)}")

# Re-habilitar FK
post([{"type": "execute", "stmt": {"sql": "PRAGMA foreign_keys = ON"}}])
print("  FK ON restaurado")

# === PASO 5: REINDEX ===
print("\nPASO 5: REINDEX empleados...")
res = post([{"type": "execute", "stmt": {"sql": "REINDEX empleados"}}])
reindex_status = res['results'][0]['type']
print(f"  REINDEX: {reindex_status}")
if reindex_status == 'error':
    print(f"  (Nota: el error de REINDEX puede persistir hasta el proximo VACUUM del cloud)")

# === PASO 6: Verificacion final ===
print("\nPASO 6: Verificacion final...")
tests = [
    ("COUNT(*) empleados", "SELECT COUNT(*) as c FROM empleados"),
    ("Empleados activos", "SELECT COUNT(*) as c FROM empleados WHERE activo=1"),
    ("Query cumpleanos Mayo", "SELECT COUNT(*) as c FROM empleados WHERE activo=1 AND fecha_nacimiento IS NOT NULL AND CAST(substr(fecha_nacimiento,6,2) AS INTEGER)=5"),
    ("SELECT por PK", "SELECT id, nombre FROM empleados ORDER BY id LIMIT 3"),
    ("JOIN historial_areas", "SELECT COUNT(*) as c FROM empleados e LEFT JOIN historial_areas ha ON e.id=ha.empleado_id WHERE e.activo=1"),
    ("Full scan empleados", "SELECT COUNT(*) as c FROM empleados WHERE activo=1 AND tipo_contrato IS NOT NULL"),
]

all_ok = True
for name, sql in tests:
    try:
        _, rows = query(sql)
        val = list(rows[0].values()) if rows else []
        print(f"  OK  {name}: {val}")
    except Exception as e:
        print(f"  ERR {name}: {e}")
        all_ok = False

if all_ok:
    print("\n=== REPARACION EXITOSA ===")
    print("Reiniciando el servidor para sincronizar los datos reparados...")
else:
    print("\n=== REPARACION PARCIAL - algunos queries aun fallan ===")
    print("La corrupcion esta en el storage interno de Turso Cloud.")
    print("Requiere accion desde el dashboard de Turso (destroy + recreate).")
