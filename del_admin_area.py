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

def run(sql):
    payload = json.dumps({"requests": [{"type": "execute", "stmt": {"sql": sql}}, {"type": "close"}]}).encode()
    req = urllib.request.Request(f"{TURSO_URL}/v2/pipeline", data=payload,
        headers={"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read())
    r2 = res["results"][0]
    if r2["type"] == "error":
        raise Exception(r2["error"]["message"])
    return r2["response"]["result"].get("affected_row_count", 0)

def qry(sql):
    payload = json.dumps({"requests": [{"type": "execute", "stmt": {"sql": sql}}, {"type": "close"}]}).encode()
    req = urllib.request.Request(f"{TURSO_URL}/v2/pipeline", data=payload,
        headers={"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read())
    d = res["results"][0]["response"]["result"]
    cols = [c["name"] for c in d["cols"]]
    return [{cols[i]: row[i]["value"] for i in range(len(cols))} for row in d["rows"]]

# Eliminar los 3 registros de historial_areas huerfanos (empleados 46,47,48 que no existen)
r1 = run("DELETE FROM historial_areas WHERE area_id=2")
print(f"historial_areas de ADMINISTRACION eliminados: {r1}")

r2 = run("DELETE FROM areas_alias WHERE area_id=2")
print(f"aliases eliminados: {r2}")

r3 = run("DELETE FROM areas WHERE id=2")
print(f"area ADMINISTRACION eliminada: {r3}")

# Estado final
print("\nAreas finales:")
for a in qry("SELECT id, nombre FROM areas ORDER BY CAST(id AS INTEGER)"):
    print(f"  ID={a['id']}: {a['nombre']}")

areas = qry("SELECT id, nombre FROM areas ORDER BY CAST(id AS INTEGER)")
print(f"Total: {len(areas)} areas")

# Verificar FK
huerfanos = qry("""
    SELECT e.area_id, COUNT(*) as count
    FROM empleados e
    LEFT JOIN areas a ON e.area_id = a.id
    WHERE a.id IS NULL
    GROUP BY e.area_id
""")
if huerfanos:
    print("FK ERROR: empleados con area_id invalido!")
else:
    print("FK OK: todos los empleados tienen area valida")
