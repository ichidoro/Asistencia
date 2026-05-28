"""
Limpieza final de logs_raw y bono_asignaciones con estrategia alternativa.
logs_raw: usa LEFT JOIN en lugar de NOT IN (evita el error de corrupcion)
bono_asignaciones: limpia los 19 huerfanos restantes
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

def run(sql):
    payload = json.dumps({"requests": [{"type": "execute", "stmt": {"sql": sql}}, {"type": "close"}]}).encode()
    req = urllib.request.Request(f"{TURSO_URL}/v2/pipeline", data=payload,
        headers={"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read())
    r2 = res["results"][0]
    if r2["type"] == "error":
        raise Exception(r2["error"]["message"])
    return r2["response"]["result"].get("affected_row_count", 0)

def q(sql):
    payload = json.dumps({"requests": [{"type": "execute", "stmt": {"sql": sql}}, {"type": "close"}]}).encode()
    req = urllib.request.Request(f"{TURSO_URL}/v2/pipeline", data=payload,
        headers={"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read())
    d = res["results"][0]["response"]["result"]
    cols = [c["name"] for c in d["cols"]]
    return [{cols[i]: (row[i]["value"] if row[i]["type"] != "null" else None) for i in range(len(cols))} for row in d["rows"]]

print("=== LIMPIEZA FINAL ===\n")

# 1. Identificar IDs de empleados que NO existen
emp_ids = [str(int(r["id"])) for r in q("SELECT id FROM empleados")]
print(f"  Empleados en DB: {len(emp_ids)} (IDs: {emp_ids[:5]}...)")

# 2. Obtener empleado_ids huerfanos en logs_raw
orphan_emp_in_logs = q("""
    SELECT DISTINCT l.empleado_id
    FROM logs_raw l
    LEFT JOIN empleados e ON l.empleado_id = e.id
    WHERE e.id IS NULL AND l.empleado_id IS NOT NULL
""")
orphan_ids_logs = [str(int(r["empleado_id"])) for r in orphan_emp_in_logs if r["empleado_id"]]
print(f"  IDs huerfanos en logs_raw: {orphan_ids_logs}")

# 3. Eliminar logs_raw por IDs especificos (evita NOT IN con subquery grande)
total_logs = 0
if orphan_ids_logs:
    for oid in orphan_ids_logs:
        try:
            n = run(f"DELETE FROM logs_raw WHERE empleado_id = {oid}")
            print(f"    logs_raw empleado_id={oid}: {n} filas eliminadas")
            total_logs += n
        except Exception as e:
            print(f"    ERROR logs_raw empleado_id={oid}: {e}")
            # Intentar con IS
            try:
                n = run(f"DELETE FROM logs_raw WHERE empleado_id IS {oid}")
                print(f"    logs_raw (IS) empleado_id={oid}: {n} filas eliminadas")
                total_logs += n
            except Exception as e2:
                print(f"    FALLO TOTAL para {oid}: {e2}")
else:
    print("  No hay IDs huerfanos en logs_raw detectados.")

print(f"  Total logs_raw eliminados: {total_logs}")

# 4. Limpiar bono_asignaciones huerfanos restantes
print("\n  Limpiando bono_asignaciones huerfanos...")
orphan_ba = q("""
    SELECT DISTINCT ba.empleado_id
    FROM bono_asignaciones ba
    LEFT JOIN empleados e ON ba.empleado_id = e.id
    WHERE e.id IS NULL AND ba.empleado_id IS NOT NULL
""")
orphan_ids_ba = [str(int(r["empleado_id"])) for r in orphan_ba if r["empleado_id"]]
print(f"  IDs huerfanos en bono_asignaciones: {orphan_ids_ba}")

total_ba = 0
for oid in orphan_ids_ba:
    n = run(f"DELETE FROM bono_asignaciones WHERE empleado_id = {oid}")
    print(f"    bono_asignaciones empleado_id={oid}: {n} eliminados")
    total_ba += n
print(f"  Total bono_asignaciones eliminados: {total_ba}")

# 5. Verificacion final completa
print("\n=== ESTADO FINAL ===\n")
checks = [
    ("logs_raw huerfanos",         "SELECT COUNT(*) as c FROM logs_raw l LEFT JOIN empleados e ON l.empleado_id = e.id WHERE e.id IS NULL"),
    ("bono_asignaciones huerfanos","SELECT COUNT(*) as c FROM bono_asignaciones ba LEFT JOIN empleados e ON ba.empleado_id = e.id WHERE e.id IS NULL"),
    ("asistencias huerfanos",      "SELECT COUNT(*) as c FROM asistencias a LEFT JOIN empleados e ON a.empleado_id = e.id WHERE e.id IS NULL"),
    ("historial_areas huerfanos",  "SELECT COUNT(*) as c FROM historial_areas ha LEFT JOIN empleados e ON ha.empleado_id = e.id WHERE e.id IS NULL"),
    ("horas_extras huerfanos",     "SELECT COUNT(*) as c FROM horas_extras he LEFT JOIN empleados e ON he.empleado_id = e.id WHERE e.id IS NULL"),
    ("justificaciones huerfanos",  "SELECT COUNT(*) as c FROM justificaciones j LEFT JOIN empleados e ON j.empleado_id = e.id WHERE e.id IS NULL"),
    ("asignacion_turnos huerfanos","SELECT COUNT(*) as c FROM asignacion_turnos at LEFT JOIN empleados e ON at.empleado_id = e.id WHERE e.id IS NULL"),
]
all_ok = True
for desc, sql in checks:
    rows = q(sql)
    val = int(str(rows[0]["c"])) if rows else 0
    estado = "OK " if val == 0 else "WARN"
    if val > 0: all_ok = False
    print(f"  [{estado}] {desc}: {val}")

print(f"\n  {'BD 100% limpia e integra.' if all_ok else 'Quedan inconsistencias (ver WARN).'}")

# Resumen de registros validos
print("\n  Registros validos por tabla:")
tablas = [
    ("empleados activos", "SELECT COUNT(*) as c FROM empleados WHERE activo=1"),
    ("asistencias",       "SELECT COUNT(*) as c FROM asistencias"),
    ("logs_raw",          "SELECT COUNT(*) as c FROM logs_raw"),
    ("historial_areas",   "SELECT COUNT(*) as c FROM historial_areas WHERE es_actual=1 AND validado=1"),
    ("justificaciones",   "SELECT COUNT(*) as c FROM justificaciones"),
    ("horas_extras",      "SELECT COUNT(*) as c FROM horas_extras"),
    ("bono_asignaciones", "SELECT COUNT(*) as c FROM bono_asignaciones"),
    ("asignacion_turnos", "SELECT COUNT(*) as c FROM asignacion_turnos"),
]
for nombre, sql in tablas:
    rows = q(sql)
    print(f"    {nombre:<25}: {rows[0]['c']}")
