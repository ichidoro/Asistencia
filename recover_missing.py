"""
Intenta recuperar IDs 38-53 desde:
1. logs_auditoria (puede tener datos JSON de ediciones)
2. Lectura raw del WAL file de sqlite3
3. Tabla usuarios (si tienen vinculo)
"""
import sqlite3, urllib.request, json, os, struct

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
missing_ids = list(range(38, 54))  # 38..53

def post(stmts):
    endpoint = f"{TURSO_URL}/v2/pipeline"
    payload = json.dumps({"requests": stmts + [{"type": "close"}]}).encode()
    req = urllib.request.Request(endpoint, data=payload,
        headers={'Authorization': f'Bearer {TURSO_TOKEN}', 'Content-Type': 'application/json'},
        method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def cloud_query(sql):
    res = post([{"type": "execute", "stmt": {"sql": sql}}])
    r = res['results'][0]
    if r['type'] == 'error':
        raise Exception(r['error']['message'])
    d = r['response']['result']
    cols = [c['name'] for c in d['cols']]
    return [{cols[i]: (row[i]['value'] if row[i]['type'] != 'null' else None)
             for i in range(len(cols))} for row in d['rows']]

# ====================================================
# 1. Buscar en logs_auditoria del cloud
# ====================================================
print("=== 1. Buscando en logs_auditoria (cloud) ===")
recovered_from_logs = {}
try:
    rows = cloud_query(
        "SELECT * FROM logs_auditoria WHERE tabla='empleados' "
        "AND CAST(registro_id AS INTEGER) BETWEEN 38 AND 53 "
        "ORDER BY id DESC"
    )
    print(f"  Registros de auditoria para IDs 38-53: {len(rows)}")
    for row in rows:
        emp_id = int(row.get('registro_id', 0))
        datos_str = row.get('datos_nuevos') or row.get('datos_anteriores') or ''
        if datos_str and emp_id not in recovered_from_logs:
            try:
                datos = json.loads(datos_str)
                if isinstance(datos, dict) and 'nombre' in datos:
                    recovered_from_logs[emp_id] = datos
                    print(f"  ID={emp_id}: RECUPERADO desde log -> {datos.get('nombre')} {datos.get('apellido_paterno')}")
            except:
                pass
except Exception as e:
    print(f"  Error: {e}")

# ====================================================
# 2. Buscar en usuarios del cloud (pueden tener empleado_id)
# ====================================================
print("\n=== 2. Buscando en usuarios (cloud) ===")
try:
    rows = cloud_query("PRAGMA table_info(usuarios)")
    col_names = [r['name'] for r in rows]
    print(f"  Columnas usuarios: {col_names}")
    rows_u = cloud_query("SELECT * FROM usuarios")
    for r in rows_u:
        print(f"  {r}")
except Exception as e:
    print(f"  Error: {e}")

# ====================================================
# 3. Intentar leer WAL local con PRAGMA wal_checkpoint
# ====================================================
print("\n=== 3. Intentando leer desde WAL local ===")
wal_path = DB_PATH + '-wal'
if os.path.exists(wal_path):
    size = os.path.getsize(wal_path)
    print(f"  WAL file existe: {size} bytes")
    # Intentar leer DB en modo inmutable para forzar lectura desde WAL
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?immutable=1", uri=True, timeout=5)
        cur = conn.cursor()
        for emp_id in missing_ids:
            try:
                cur.execute(f"SELECT * FROM empleados WHERE id={emp_id}")
                row = cur.fetchone()
                if row:
                    print(f"  WAL immutable ID={emp_id}: OK")
            except Exception as e2:
                pass
        conn.close()
    except Exception as e:
        print(f"  WAL inmutable error: {e}")
else:
    print("  No hay WAL file local")

# ====================================================
# 4. Intentar leer con PRAGMA integrity_check desactivado
# ====================================================
print("\n=== 4. Intentando leer con sqlite3 modo bypass ===")
recovered_local = {}
conn = sqlite3.connect(DB_PATH, timeout=10)
conn.row_factory = sqlite3.Row

# Intentar con PRAGMA ignore_check_constraints
cur = conn.cursor()
for pragma in ["PRAGMA ignore_check_constraints=1", "PRAGMA foreign_keys=OFF", "PRAGMA synchronous=OFF"]:
    try:
        cur.execute(pragma)
    except:
        pass

for emp_id in missing_ids:
    for attempt in range(3):
        try:
            cur.execute(f"SELECT * FROM empleados WHERE rowid={emp_id}")
            row = cur.fetchone()
            if row:
                d = dict(row)
                recovered_local[emp_id] = d
                print(f"  rowid={emp_id}: OK -> {d.get('nombre')}")
                break
        except Exception as e:
            if attempt == 2:
                pass  # silencioso

conn.close()

print(f"\n  Recuperados via bypass local: {list(recovered_local.keys())}")

# ====================================================
# 5. Si hay recuperados, insertarlos en cloud
# ====================================================
all_recovered = {}
all_recovered.update(recovered_from_logs)
all_recovered.update(recovered_local)

print(f"\n=== 5. Total recuperados: {len(all_recovered)} ===")
if all_recovered:
    # Obtener columnas
    cols_rows = cloud_query("SELECT * FROM empleados WHERE id=1")
    cols_emp = list(cols_rows[0].keys())
    cols_str = ', '.join(f'"{c}"' for c in cols_emp)
    
    for emp_id, emp in all_recovered.items():
        args = []
        placeholders = []
        for c in cols_emp:
            v = emp.get(c) or emp.get(str(c))
            if v is None:
                placeholders.append('NULL')
            else:
                placeholders.append('?')
                args.append({"type": "text", "value": str(v)})
        
        res = post([
            {"type": "execute", "stmt": {"sql": "PRAGMA foreign_keys=OFF"}},
            {"type": "execute", "stmt": {
                "sql": f"INSERT OR REPLACE INTO empleados ({cols_str}) VALUES ({', '.join(placeholders)})",
                "args": args
            }}
        ])
        ok = [x for x in res['results'] if x['type'] == 'ok']
        print(f"  ID={emp_id}: {'INSERTADO OK' if len(ok) >= 2 else 'FALLO'}")
else:
    print("  No se pudo recuperar ningun empleado adicional de IDs 38-53.")
    print("  Estos registros estan en paginas irrecuperables.")

# ====================================================
# 6. Estado final
# ====================================================
print("\n=== Estado final ===")
rows = cloud_query("SELECT COUNT(*) as c FROM empleados")
print(f"  Empleados en cloud: {rows[0]['c']}/78")
rows = cloud_query("SELECT id FROM empleados ORDER BY id")
ids_present = [int(r['id']) for r in rows]
ids_missing = [x for x in range(1, 80) if x not in ids_present]
print(f"  IDs faltantes: {ids_missing}")
