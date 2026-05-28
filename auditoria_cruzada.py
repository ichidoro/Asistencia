"""
Auditoria completa de la BD contra el respaldo:
- Cruza empleados del respaldo con DB
- Verifica historial_areas, marcaciones, justificaciones por cada empleado
- Reporta qué falta / qué sobra
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

def q(sql, params=None):
    stmt = {"sql": sql}
    if params:
        stmt["args"] = [{"type": "text", "value": str(p)} for p in params]
    payload = json.dumps({"requests": [{"type": "execute", "stmt": stmt}, {"type": "close"}]}).encode()
    req = urllib.request.Request(f"{TURSO_URL}/v2/pipeline", data=payload,
        headers={"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.loads(r.read())
    d = res["results"][0]["response"]["result"]
    cols = [c["name"] for c in d["cols"]]
    return [{cols[i]: (row[i]["value"] if row[i]["type"] != "null" else None) for i in range(len(cols))} for row in d["rows"]]

# Cargar respaldo
with open("respaldo/empleados.json", encoding="utf-8") as f:
    respaldo = json.load(f)

print(f"=== RESPALDO: {len(respaldo)} empleados ===\n")

# ============================================================
# 1. AREAS EN DB
# ============================================================
areas_db = {a["id"]: a["nombre"] for a in q("SELECT id, nombre FROM areas")}
areas_nombre_id = {v: k for k, v in areas_db.items()}
print("Areas en DB:")
for aid, nombre in sorted(areas_db.items()):
    print(f"  {aid}: {nombre}")

# ============================================================
# 2. EMPLEADOS EN DB (todos)
# ============================================================
emp_db_raw = q("""
    SELECT e.id, e.rut, e.nombre, e.apellido_paterno, e.activo, e.area_id,
           a.nombre as area_nombre,
           ha.id as ha_id, ha.es_actual, ha.validado
    FROM empleados e
    LEFT JOIN areas a ON e.area_id = a.id
    LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
""")
emp_db = {str(row["rut"]).strip(): row for row in emp_db_raw}

print(f"\n=== DB: {len(emp_db)} empleados ===")

# ============================================================
# 3. CRUCE: RESPALDO vs DB
# ============================================================
print("\n=== CRUCE RESPALDO vs DB ===")
ruts_respaldo = set()
ok = []
sin_historial = []
area_mal = []
solo_en_db = []

for emp in respaldo:
    rut = str(emp.get("rut", "")).strip()
    ruts_respaldo.add(rut)
    nombre = emp.get("nombre", "") or f"{emp.get('apellido_paterno','')} {emp.get('nombre','')}"
    area_backup = (emp.get("area") or "").strip().upper()

    if rut not in emp_db:
        print(f"  ❌ FALTA EN DB: {rut} | {emp.get('apellido_paterno')} | area={area_backup}")
        continue

    db_row = emp_db[rut]
    area_db = (db_row.get("area_nombre") or "").strip().upper()

    # Verificar historial activo
    if not db_row.get("ha_id"):
        sin_historial.append({"rut": rut, "nombre": emp.get("apellido_paterno"), "area": area_backup, "id": db_row["id"]})
    elif area_db != area_backup:
        area_mal.append({"rut": rut, "nombre": emp.get("apellido_paterno"), "area_backup": area_backup, "area_db": area_db, "id": db_row["id"]})
    else:
        ok.append(rut)

# Empleados en DB que no están en respaldo
for rut, row in emp_db.items():
    if rut not in ruts_respaldo:
        solo_en_db.append(rut)

print(f"\n  ✅ OK (area y historial correctos): {len(ok)}")
print(f"  ⚠️  Sin historial_areas activo (es_actual=1 validado=1): {len(sin_historial)}")
for e in sin_historial:
    print(f"     {e['rut']} | {e['nombre']} | area_backup={e['area']}")
print(f"  🔄 Area incorrecta en historial: {len(area_mal)}")
for e in area_mal:
    print(f"     {e['rut']} | {e['nombre']} | backup={e['area_backup']} | db={e['area_db']}")
print(f"  ➕ Solo en DB (no en respaldo): {len(solo_en_db)}")
for rut in solo_en_db[:10]:
    row = emp_db[rut]
    print(f"     {rut} | {row.get('apellido_paterno','')} | area={row.get('area_nombre','')}")

# ============================================================
# 4. MARCACIONES (asistencias) por empleado del respaldo
# ============================================================
print("\n=== MARCACIONES POR AREA ===")
marc_stats = q("""
    SELECT a.nombre as area, COUNT(DISTINCT e.id) as empleados_con_marc, COUNT(ast.id) as total_marcaciones
    FROM empleados e
    LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
    LEFT JOIN areas a ON ha.area_id = a.id
    LEFT JOIN asistencias ast ON e.id = ast.empleado_id
    WHERE e.activo = 1 AND a.nombre IS NOT NULL
    GROUP BY a.nombre
    ORDER BY a.nombre
""")
for r in marc_stats:
    print(f"  {r['area']}: {r['empleados_con_marc']} empleados con marcaciones, {r['total_marcaciones']} registros")

# ============================================================
# 5. JUSTIFICACIONES por area
# ============================================================
print("\n=== JUSTIFICACIONES POR AREA ===")
just_stats = q("""
    SELECT a.nombre as area, COUNT(j.id) as total_justificaciones
    FROM empleados e
    LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
    LEFT JOIN areas a ON ha.area_id = a.id
    LEFT JOIN justificaciones j ON e.id = j.empleado_id
    WHERE a.nombre IS NOT NULL
    GROUP BY a.nombre
    ORDER BY a.nombre
""")
for r in just_stats:
    print(f"  {r['area']}: {r['total_justificaciones']} justificaciones")

# ============================================================
# 6. HISTORIAL_AREAS: estado general
# ============================================================
print("\n=== HISTORIAL_AREAS: ESTADO GENERAL ===")
ha_stats = q("""
    SELECT a.nombre as area, ha.es_actual, ha.validado, COUNT(*) as c
    FROM historial_areas ha
    LEFT JOIN areas a ON ha.area_id = a.id
    GROUP BY a.nombre, ha.es_actual, ha.validado
    ORDER BY a.nombre
""")
for r in ha_stats:
    print(f"  {r['area']}: es_actual={r['es_actual']} validado={r['validado']} -> {r['c']} registros")

# ============================================================
# 7. EMPLEADOS SIN HISTORIAL ACTIVO
# ============================================================
print("\n=== EMPLEADOS SIN HISTORIAL ACTIVO (area_id del empleado como fallback) ===")
sin_ha = q("""
    SELECT e.id, e.rut, e.apellido_paterno, e.activo, e.area_id, a.nombre as area_dir
    FROM empleados e
    LEFT JOIN areas a ON e.area_id = a.id
    LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
    WHERE ha.id IS NULL AND e.activo = 1
    ORDER BY a.nombre
""")
print(f"  Total sin historial_areas activo+validado: {len(sin_ha)}")
for e in sin_ha:
    print(f"    ID={e['id']} | {e['rut']} | {e['apellido_paterno']} | area_id={e['area_id']} ({e['area_dir']})")
