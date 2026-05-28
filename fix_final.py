"""
Fix final: 
- Lee IDs 38-53 desde sqlite3 local (por ID individual)
- Inserta FK OFF en el mismo pipeline que los INSERTs
- Recupera los 78 empleados completos en Turso Cloud
"""
import sqlite3, urllib.request, json, os

env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

TURSO_URL = env['TURSO_DATABASE_URL'].replace('libsql://', 'https://')
TURSO_TOKEN = env['TURSO_AUTH_TOKEN']
DB_PATH = 'data/local_db/asistencia_local.db'

def post_pipeline(stmts):
    endpoint = f"{TURSO_URL}/v2/pipeline"
    payload = json.dumps({"requests": stmts + [{"type": "close"}]}).encode()
    req = urllib.request.Request(endpoint, data=payload,
        headers={'Authorization': f'Bearer {TURSO_TOKEN}', 'Content-Type': 'application/json'},
        method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def cloud_query(sql):
    res = post_pipeline([{"type": "execute", "stmt": {"sql": sql}}])
    r = res['results'][0]
    if r['type'] == 'error':
        raise Exception(r['error']['message'])
    d = r['response']['result']
    cols = [c['name'] for c in d['cols']]
    return [{cols[i]: (row[i]['value'] if row[i]['type'] != 'null' else None) for i in range(len(cols))} for row in d['rows']]

# =========================================================
# PASO 1: Estado actual del cloud
# =========================================================
print("=" * 55)
print("PASO 1: Estado actual del cloud")
rows = cloud_query("SELECT COUNT(*) as c FROM empleados")
current_count = int(rows[0]['c'])
print(f"  Empleados en cloud ahora: {current_count}")

rows = cloud_query("SELECT DISTINCT empleado_id FROM historial_areas ORDER BY empleado_id")
all_ids_str = [r['empleado_id'] for r in rows]
all_ids = [int(x) for x in all_ids_str]
print(f"  IDs necesarios (desde historial_areas): {len(all_ids)}")

# IDs ya insertados en cloud (los que sí funcionan)
try:
    rows_ok = cloud_query("SELECT id FROM empleados ORDER BY id")
    ids_ok = set(int(r['id']) for r in rows_ok)
except:
    ids_ok = set()
print(f"  IDs ya en cloud: {len(ids_ok)} -> {sorted(ids_ok)[:5]}...")

ids_missing = [x for x in all_ids if x not in ids_ok]
print(f"  IDs faltantes: {len(ids_missing)} -> {ids_missing}")

# =========================================================
# PASO 2: Leer columnas y empleados faltantes
# =========================================================
print(f"\nPASO 2: Leyendo {len(ids_missing)} empleados faltantes")

# Obtener columnas
cols_emp = None
for test_id in ids_ok:
    try:
        rows_t = cloud_query(f"SELECT * FROM empleados WHERE id={test_id}")
        if rows_t:
            cols_emp = list(rows_t[0].keys())
            break
    except:
        pass

if not cols_emp:
    print("ERROR: No se pudieron obtener columnas")
    exit(1)
print(f"  Columnas: {cols_emp}")

# Intentar leer faltantes desde Turso cloud por PK
empleados_to_insert = []
still_missing_cloud = []
for emp_id in ids_missing:
    try:
        rows_t = cloud_query(f"SELECT * FROM empleados WHERE id={emp_id}")
        if rows_t:
            empleados_to_insert.append(rows_t[0])
            print(f"  cloud ID={emp_id}: OK (nombre: {rows_t[0].get('nombre')})")
        else:
            still_missing_cloud.append(emp_id)
    except Exception as e:
        still_missing_cloud.append(emp_id)
        print(f"  cloud ID={emp_id}: FALLA ({str(e)[:40]})")

print(f"  Recuperados desde cloud: {len(empleados_to_insert)}")
print(f"  Aun faltantes (paginas corruptas): {still_missing_cloud}")

# Leer los de paginas corruptas desde sqlite3 local
if still_missing_cloud:
    print(f"\n  Leyendo {len(still_missing_cloud)} desde sqlite3 local...")
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    for emp_id in still_missing_cloud:
        try:
            cur.execute(f"SELECT * FROM empleados WHERE id = {emp_id}")
            row = cur.fetchone()
            if row:
                d = {k: row[k] for k in cols_emp if k in row.keys()}
                empleados_to_insert.append(d)
                print(f"  local  ID={emp_id}: OK (nombre: {d.get('nombre')})")
            else:
                print(f"  local  ID={emp_id}: sin datos")
        except Exception as e:
            print(f"  local  ID={emp_id}: ERROR - {e}")
    conn.close()

print(f"\n  Total empleados a insertar: {len(empleados_to_insert)}")

# =========================================================
# PASO 3: Insertar empleados faltantes con FK OFF en mismo pipeline
# =========================================================
print(f"\nPASO 3: Insertando {len(empleados_to_insert)} empleados (FK OFF mismo pipeline)")

cols_str = ', '.join(f'"{c}"' for c in cols_emp)
inserted = 0
errors = 0

for i in range(0, len(empleados_to_insert), 8):
    batch = empleados_to_insert[i:i+8]
    stmts = [
        # FK OFF como PRIMER statement del mismo pipeline
        {"type": "execute", "stmt": {"sql": "PRAGMA foreign_keys = OFF"}}
    ]
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
                "sql": f"INSERT OR REPLACE INTO empleados ({cols_str}) VALUES ({', '.join(placeholders)})",
                "args": args
            }
        })
    
    res = post_pipeline(stmts)
    batch_errors = [x for x in res['results'] if x['type'] == 'error']
    if batch_errors:
        errors += 1
        err_msg = batch_errors[0]['error']['message']
        print(f"  Batch {i//8+1} ERROR: {err_msg}")
        # Intentar uno por uno
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
            res2 = post_pipeline([
                {"type": "execute", "stmt": {"sql": "PRAGMA foreign_keys = OFF"}},
                {"type": "execute", "stmt": {
                    "sql": f"INSERT OR REPLACE INTO empleados ({cols_str}) VALUES ({', '.join(placeholders)})",
                    "args": args
                }}
            ])
            ok = [x for x in res2['results'] if x['type'] == 'ok']
            if len(ok) >= 2:
                inserted += 1
                print(f"    ID={emp.get('id')} OK individualmente")
            else:
                errs2 = [x for x in res2['results'] if x['type'] == 'error']
                if errs2:
                    print(f"    ID={emp.get('id')} FALLA: {errs2[0]['error']['message'][:60]}")
    else:
        inserted += len(batch)
        print(f"  Batch {i//8+1}: +{len(batch)} OK (total: {current_count + inserted})")

# =========================================================
# PASO 4: Verificacion final
# =========================================================
print(f"\nPASO 4: Verificacion final")
try:
    rows = cloud_query("SELECT COUNT(*) as c FROM empleados")
    total = int(rows[0]['c'])
    print(f"  Total empleados en cloud: {total}/78")
    
    rows = cloud_query("SELECT COUNT(*) as c FROM empleados WHERE activo=1")
    print(f"  Empleados activos: {rows[0]['c']}")
    
    rows = cloud_query(
        "SELECT COUNT(*) as c FROM empleados e "
        "LEFT JOIN historial_areas ha ON e.id=ha.empleado_id AND ha.es_actual=1 "
        "LEFT JOIN areas a ON ha.area_id=a.id WHERE e.activo=1"
    )
    print(f"  JOIN empleados+historial_areas: {rows[0]['c']} OK")
    
    rows = cloud_query(
        "SELECT COUNT(*) as c FROM empleados WHERE activo=1 "
        "AND fecha_nacimiento IS NOT NULL "
        "AND CAST(substr(fecha_nacimiento,6,2) AS INTEGER)=5"
    )
    print(f"  Cumpleanos Mayo (query problematica): {rows[0]['c']} OK")
    
    rows = cloud_query("SELECT id, nombre, apellido_paterno FROM empleados ORDER BY id LIMIT 5")
    print(f"  Primeros 5 empleados:")
    for r in rows:
        print(f"    ID={r['id']}: {r['nombre']} {r['apellido_paterno']}")
    
    if total >= 70:
        print(f"\n  REPARACION EXITOSA ({total}/78 empleados)")
    elif total >= 36:
        print(f"\n  REPARACION PARCIAL ({total}/78 empleados - mejora desde 36)")
    else:
        print(f"\n  PROBLEMA: solo {total}/78 empleados")
        
except Exception as e:
    print(f"  ERROR verificacion: {e}")
