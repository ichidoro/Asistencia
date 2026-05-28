"""
Reconstruye la tabla areas con todos los IDs y nombres correctos.
Fuentes:
1. historial_areas.nombre_area (si tiene columna)
2. Inferencia por area_id y cargos de empleados
3. usuarios.areas_json (lista completa de nombres)
"""
import urllib.request, json

env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

TURSO_URL = env['TURSO_DATABASE_URL'].replace('libsql://', 'https://')
TURSO_TOKEN = env['TURSO_AUTH_TOKEN']

def post(stmts):
    endpoint = f"{TURSO_URL}/v2/pipeline"
    payload = json.dumps({"requests": stmts + [{"type": "close"}]}).encode()
    req = urllib.request.Request(endpoint, data=payload,
        headers={'Authorization': f'Bearer {TURSO_TOKEN}', 'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def q(sql):
    res = post([{"type": "execute", "stmt": {"sql": sql}}])
    r = res['results'][0]
    if r['type'] == 'error':
        raise Exception(r['error']['message'])
    d = r['response']['result']
    cols = [c['name'] for c in d['cols']]
    return [{cols[i]: (row[i]['value'] if row[i]['type'] != 'null' else None) for i in range(len(cols))} for row in d['rows']]

# =====================================================
# 1. Ver columnas de historial_areas
# =====================================================
print("=== Columnas de historial_areas ===")
cols = q("PRAGMA table_info(historial_areas)")
for c in cols:
    print(f"  {c['cid']}: {c['name']} ({c['type']})")

print("\n=== Muestra de historial_areas ===")
rows = q("SELECT * FROM historial_areas LIMIT 5")
for r in rows:
    print(f"  {r}")

# =====================================================
# 2. Areas unicas en historial
# =====================================================
print("\n=== area_id distintos en historial_areas ===")
rows = q("SELECT DISTINCT area_id FROM historial_areas ORDER BY CAST(area_id AS INTEGER)")
for r in rows:
    print(f"  area_id={r['area_id']}")

# =====================================================
# 3. Ver si historial tiene nombre_area
# =====================================================
col_names_ha = [c['name'] for c in q("PRAGMA table_info(historial_areas)")]
print(f"\nColumnas historial_areas: {col_names_ha}")

nombre_area_col = None
for c in col_names_ha:
    if 'nombre' in c.lower() or 'area' in c.lower() and c != 'area_id':
        nombre_area_col = c
        break

if nombre_area_col:
    print(f"\nUsando columna '{nombre_area_col}' para obtener nombres:")
    rows = q(f"SELECT DISTINCT area_id, {nombre_area_col} FROM historial_areas ORDER BY CAST(area_id AS INTEGER)")
    for r in rows:
        print(f"  area_id={r['area_id']}: {r.get(nombre_area_col)}")
