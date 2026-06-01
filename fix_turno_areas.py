"""
Corrección de datos: Asignar área a turnos huérfanos
"""
import requests
import json

TURSO_URL = "https://aguacol-ichidoro.aws-us-east-1.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODAwMjM1MzUsImlkIjoiMDE5ZTcxYWItOGYwMS03NWVkLWJmMDMtMDExZjk5MjE3ZWM4IiwicmlkIjoiZmE1OTYxZWYtNDEwOS00MTY1LTkwMzMtNzA4YmI5MzNiNjkwIn0.S3g__Bhy2on3tw8xzTugeFaGR-gNlz5D0Mcg-DAStaJQ_83qgLmllMZy-n5WjANJz-oTNok6h75XY1bHCmQJDg"

def execute_batch(stmts):
    url = f"{TURSO_URL}/v2/pipeline"
    headers = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}
    requests_list = []
    for sql, params in stmts:
        stmt = {"type": "execute", "stmt": {"sql": sql}}
        if params:
            stmt["stmt"]["args"] = [{"type": "text" if isinstance(p, str) else "integer", "value": str(p)} for p in params]
        requests_list.append(stmt)
    requests_list.append({"type": "close"})
    body = {"requests": requests_list}
    resp = requests.post(url, headers=headers, json=body, timeout=15)
    data = resp.json()
    results = data.get("results", [])
    for i, r in enumerate(results):
        if "error" in r:
            print(f"  ❌ Statement {i}: {r['error']}")
        elif r.get("type") == "close":
            pass
        else:
            affected = r.get("response", {}).get("result", {}).get("affected_row_count", 0)
            print(f"  ✅ Statement {i}: {affected} filas afectadas")
    return data

def query(sql, params=None):
    url = f"{TURSO_URL}/v2/pipeline"
    headers = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}
    stmt = {"type": "execute", "stmt": {"sql": sql}}
    if params:
        stmt["stmt"]["args"] = [{"type": "text" if isinstance(p, str) else "integer", "value": str(p)} for p in params]
    body = {"requests": [stmt, {"type": "close"}]}
    resp = requests.post(url, headers=headers, json=body, timeout=10)
    data = resp.json()
    if "results" not in data:
        return []
    result = data["results"][0]
    if "error" in result:
        return []
    resp_data = result.get("response", {}).get("result", {})
    cols = [c["name"] for c in resp_data.get("cols", [])]
    rows = []
    for r in resp_data.get("rows", []):
        row = {cols[i]: (cell.get("value") if cell.get("type") != "null" else None) for i, cell in enumerate(r)}
        rows.append(row)
    return rows

# ============================================================
# VERIFICAR ESTADO ANTES
# ============================================================
print("ESTADO ANTES:")
huerfanos = query("""
    SELECT t.id, t.nombre FROM turnos t
    WHERE NOT EXISTS (SELECT 1 FROM turno_areas ta WHERE ta.turno_id = t.id)
""")
for h in huerfanos:
    print(f"  Huérfano: #{h['id']} '{h['nombre']}'")

area_lt = query("SELECT id FROM areas WHERE nombre = 'LOGISTICA TRADICIONAL'")
if not area_lt:
    print("❌ No existe el área LOGISTICA TRADICIONAL")
    exit(1)
area_lt_id = int(area_lt[0]['id'])
print(f"\nÁrea LOGISTICA TRADICIONAL = ID #{area_lt_id}")

# ============================================================
# FIX: Asignar turnos huérfanos a LOGISTICA TRADICIONAL
# ============================================================
# Turno #5 Tradicional Facturación -> LOGISTICA TRADICIONAL
# Turno #8 Tradicional Administrativo -> LOGISTICA TRADICIONAL
# Turno #9 Tradiciomal Transporte -> LOGISTICA TRADICIONAL (con typo en nombre)

print("\nAplicando correcciones:")
stmts = [
    # Asignar huérfanos a LOGISTICA TRADICIONAL
    ("INSERT OR IGNORE INTO turno_areas (turno_id, area_id) VALUES (5, ?)", [area_lt_id]),
    ("INSERT OR IGNORE INTO turno_areas (turno_id, area_id) VALUES (8, ?)", [area_lt_id]),
    ("INSERT OR IGNORE INTO turno_areas (turno_id, area_id) VALUES (9, ?)", [area_lt_id]),
    # Corregir typo: "Tradiciomal" -> "Tradicional"
    ("UPDATE turnos SET nombre = 'Tradicional Transporte' WHERE id = 9 AND nombre = 'Tradiciomal Transporte'", None),
]

execute_batch(stmts)

# ============================================================
# VERIFICAR ESTADO DESPUÉS
# ============================================================
print("\nESTADO DESPUÉS:")
huerfanos2 = query("""
    SELECT t.id, t.nombre FROM turnos t
    WHERE NOT EXISTS (SELECT 1 FROM turno_areas ta WHERE ta.turno_id = t.id)
""")
if huerfanos2:
    for h in huerfanos2:
        print(f"  ⚠️ Aún huérfano: #{h['id']} '{h['nombre']}'")
else:
    print("  ✅ No hay turnos huérfanos")

print("\nRelaciones turno_areas completas:")
ta = query("""
    SELECT ta.turno_id, t.nombre as turno, ta.area_id, a.nombre as area
    FROM turno_areas ta
    JOIN turnos t ON ta.turno_id = t.id
    JOIN areas a ON ta.area_id = a.id
    ORDER BY a.nombre, t.nombre
""")
for r in ta:
    print(f"  {r['area']} -> '{r['turno']}' (#{r['turno_id']})")

print("\nFIN")
