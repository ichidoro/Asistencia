"""
Reconstruye todas las areas faltantes en Turso Cloud.
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

print("=== ESTADO ACTUAL DE AREAS ===")
areas = q("SELECT * FROM areas ORDER BY CAST(id AS INTEGER)")
existing_ids = set(int(a['id']) for a in areas)
existing_names = set(a['nombre'] for a in areas)
for a in areas:
    print(f"  ID={a['id']}: {a['nombre']}")

# Empleados en area_id=2 son IDs 46,47,48 (no estan en el respaldo -> area historica)
# area_id=2 -> probablemente "ADMINISTRACION" o similar
# area_id=6 -> LOGISTICA (Choferes, Peonetas, Bodega, Facturacion)

print("\n=== INSERTANDO AREAS CON IDs ESPECIFICOS ===")
# Areas con IDs conocidos que deben existir
areas_con_id = [
    (2, "ADMINISTRACION"),   # area historica para empleados 46,47,48
    (6, "LOGISTICA"),        # area de Bodega+Logistica (26 empleados actuales)
]

for area_id, nombre in areas_con_id:
    if area_id in existing_ids:
        print(f"  area_id={area_id} ({nombre}) ya existe.")
        continue
    res = post([{"type": "execute", "stmt": {
        "sql": "INSERT INTO areas (id, nombre) VALUES (?, ?)",
        "args": [{"type": "integer", "value": str(area_id)},
                 {"type": "text", "value": nombre}]
    }}])
    r = res['results'][0]
    status = "OK" if r['type'] == 'ok' else f"ERROR: {r['error']['message']}"
    print(f"  area_id={area_id} '{nombre}': {status}")

print("\n=== INSERTANDO AREAS ADICIONALES (del areas_json de usuarios) ===")
# Estas areas existen en la configuracion de usuarios pero no tienen empleados activos
otras_areas = [
    "BODEGA PLASTICOS",
    "BODEGA TRADICIONAL",
    "LOGISTICA TRADICIONAL",
    "MANTENCION",
    "PLASTICOS PET",
    "PLASTICOS PRODUCCION",
    "PRODUCCION PLASTICOS",
    "SEGURIDAD",
]
for nombre in otras_areas:
    if nombre in existing_names:
        print(f"  '{nombre}' ya existe.")
        continue
    res = post([{"type": "execute", "stmt": {
        "sql": "INSERT OR IGNORE INTO areas (nombre) VALUES (?)",
        "args": [{"type": "text", "value": nombre}]
    }}])
    r = res['results'][0]
    affected = r['response']['result'].get('affected_row_count', 0) if r['type'] == 'ok' else 0
    status = f"insertada (ID auto)" if int(str(affected)) > 0 else "ya existia"
    if r['type'] == 'error':
        status = f"ERROR: {r['error']['message']}"
    print(f"  '{nombre}': {status}")

print("\n=== ESTADO FINAL DE AREAS ===")
areas = q("SELECT * FROM areas ORDER BY CAST(id AS INTEGER)")
for a in areas:
    try:
        cnt = q(f"SELECT COUNT(*) as c FROM empleados WHERE area_id={a['id']}")
        emp_count = cnt[0]['c']
    except:
        emp_count = '?'
    print(f"  ID={a['id']:>3}: {a['nombre']:<30} | {emp_count} empleados")

print(f"\nTotal areas: {len(areas)}")

# Verificar integridad FK
print("\n=== VERIFICACION DE FK area_id ===")
rows = q("""
    SELECT e.area_id, COUNT(*) as count
    FROM empleados e
    LEFT JOIN areas a ON e.area_id = a.id
    WHERE a.id IS NULL
    GROUP BY e.area_id
""")
if rows:
    print(f"  PROBLEMA: {len(rows)} area_id(s) en empleados sin correspondencia en areas:")
    for r in rows:
        print(f"    area_id={r['area_id']}: {r['count']} empleados huerfanos")
else:
    print("  OK: Todos los empleados tienen area_id valido en la tabla areas")
