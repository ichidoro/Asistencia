import urllib.request, json, os

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

print("=== TABLA AREAS (actual) ===")
rows = q("SELECT * FROM areas ORDER BY id")
for r in rows:
    print(f"  {r}")

print(f"\nTotal: {len(rows)} area(s)")

print("\n=== SCHEMA DE AREAS ===")
rows_s = q("SELECT sql FROM sqlite_master WHERE name='areas'")
print(rows_s[0]['sql'])

print("\n=== AREA_IDs REFERENCIADOS EN HISTORIAL_AREAS ===")
rows_h = q("SELECT DISTINCT area_id, COUNT(*) as empleados FROM historial_areas GROUP BY area_id ORDER BY area_id")
for r in rows_h:
    print(f"  area_id={r['area_id']}: {r['empleados']} empleados")

print("\n=== AREA_IDs EN EMPLEADOS ===")
rows_e = q("SELECT DISTINCT area_id, COUNT(*) as count FROM empleados GROUP BY area_id ORDER BY area_id")
for r in rows_e:
    print(f"  area_id={r['area_id']}: {r['count']} empleados")

print("\n=== AREAS_ALIAS (puede tener nombres) ===")
rows_a = q("SELECT * FROM areas_alias ORDER BY id LIMIT 20")
for r in rows_a:
    print(f"  {r}")
print(f"Total: {len(rows_a)} registros")

print("\n=== USUARIOS (tienen areas_json) ===")
rows_u = q("SELECT username, areas_json FROM usuarios")
for r in rows_u:
    print(f"  {r['username']}: {r['areas_json']}")

print("\n=== TURNO_AREAS (puede tener areas) ===")
rows_ta = q("SELECT * FROM turno_areas ORDER BY id")
for r in rows_ta:
    print(f"  {r}")
