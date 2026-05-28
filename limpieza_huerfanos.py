"""
Limpieza de registros huerfanos en todas las tablas secundarias.
Solo elimina filas que apuntan a empleados/bonos que NO existen.
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
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.loads(r.read())
    r2 = res["results"][0]
    if r2["type"] == "error":
        raise Exception(r2["error"]["message"])
    return r2["response"]["result"].get("affected_row_count", 0)

def q(sql):
    payload = json.dumps({"requests": [{"type": "execute", "stmt": {"sql": sql}}, {"type": "close"}]}).encode()
    req = urllib.request.Request(f"{TURSO_URL}/v2/pipeline", data=payload,
        headers={"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.loads(r.read())
    d = res["results"][0]["response"]["result"]
    cols = [c["name"] for c in d["cols"]]
    return [{cols[i]: (row[i]["value"] if row[i]["type"] != "null" else None) for i in range(len(cols))} for row in d["rows"]]

print("=== LIMPIEZA DE HUERFANOS ===\n")
total_eliminado = 0

limpiezas = [
    ("historial_areas (empleado no existe)",
     "DELETE FROM historial_areas WHERE empleado_id NOT IN (SELECT id FROM empleados)"),
    ("asistencias (empleado no existe)",
     "DELETE FROM asistencias WHERE empleado_id NOT IN (SELECT id FROM empleados)"),
    ("logs_raw (empleado no existe)",
     "DELETE FROM logs_raw WHERE empleado_id NOT IN (SELECT id FROM empleados)"),
    ("justificaciones (empleado no existe)",
     "DELETE FROM justificaciones WHERE empleado_id NOT IN (SELECT id FROM empleados)"),
    ("asignacion_turnos (empleado no existe)",
     "DELETE FROM asignacion_turnos WHERE empleado_id NOT IN (SELECT id FROM empleados)"),
    ("bono_asignaciones (empleado no existe)",
     "DELETE FROM bono_asignaciones WHERE empleado_id NOT IN (SELECT id FROM empleados)"),
    ("bono_asignaciones (bono no existe)",
     "DELETE FROM bono_asignaciones WHERE bono_id NOT IN (SELECT id FROM bonos)"),
    ("horas_extras (empleado no existe)",
     "DELETE FROM horas_extras WHERE empleado_id NOT IN (SELECT id FROM empleados)"),
    ("bolsa_horas_resumen (empleado no existe)",
     "DELETE FROM bolsa_horas_resumen WHERE empleado_id NOT IN (SELECT id FROM empleados)"),
    ("jornadas_especiales (empleado no existe)",
     "DELETE FROM jornadas_especiales WHERE empleado_id NOT IN (SELECT id FROM empleados)"),
    ("periodos_empleo (empleado no existe)",
     "DELETE FROM periodos_empleo WHERE empleado_id NOT IN (SELECT id FROM empleados)"),
    ("compensaciones_he (empleado no existe)",
     "DELETE FROM compensaciones_he_inasistencia WHERE empleado_id NOT IN (SELECT id FROM empleados)"),
]

for desc, sql in limpiezas:
    try:
        n = run(sql)
        total_eliminado += n
        estado = "OK " if n == 0 else "DEL"
        print(f"  [{estado}] {desc}: {n} filas eliminadas")
    except Exception as e:
        print(f"  [ERR] {desc}: {e}")

print(f"\n  Total filas huerfanas eliminadas: {total_eliminado}")

# Verificacion final
print("\n=== VERIFICACION POST-LIMPIEZA ===\n")
checks = [
    ("historial_areas -> empleados",
     "SELECT COUNT(*) as c FROM historial_areas ha LEFT JOIN empleados e ON ha.empleado_id = e.id WHERE e.id IS NULL"),
    ("asistencias -> empleados",
     "SELECT COUNT(*) as c FROM asistencias a LEFT JOIN empleados e ON a.empleado_id = e.id WHERE e.id IS NULL"),
    ("logs_raw -> empleados",
     "SELECT COUNT(*) as c FROM logs_raw l LEFT JOIN empleados e ON l.empleado_id = e.id WHERE e.id IS NULL"),
    ("justificaciones -> empleados",
     "SELECT COUNT(*) as c FROM justificaciones j LEFT JOIN empleados e ON j.empleado_id = e.id WHERE e.id IS NULL"),
    ("asignacion_turnos -> empleados",
     "SELECT COUNT(*) as c FROM asignacion_turnos at LEFT JOIN empleados e ON at.empleado_id = e.id WHERE e.id IS NULL"),
    ("bono_asignaciones -> empleados",
     "SELECT COUNT(*) as c FROM bono_asignaciones ba LEFT JOIN empleados e ON ba.empleado_id = e.id WHERE e.id IS NULL"),
    ("horas_extras -> empleados",
     "SELECT COUNT(*) as c FROM horas_extras he LEFT JOIN empleados e ON he.empleado_id = e.id WHERE e.id IS NULL"),
]

all_ok = True
for desc, sql in checks:
    rows = q(sql)
    val = int(str(rows[0]["c"])) if rows else 0
    estado = "OK" if val == 0 else "WARN"
    if val > 0:
        all_ok = False
    print(f"  [{estado}] {desc}: {val}")

print(f"\n  {'Base de datos 100% integra y limpia.' if all_ok else 'Aun quedan inconsistencias.'}")

# Resumen final de tablas clave
print("\n=== RESUMEN FINAL ===\n")
tablas_clave = [
    ("empleados activos",       "SELECT COUNT(*) as c FROM empleados WHERE activo=1"),
    ("areas",                   "SELECT COUNT(*) as c FROM areas"),
    ("asistencias",             "SELECT COUNT(*) as c FROM asistencias"),
    ("logs_raw",                "SELECT COUNT(*) as c FROM logs_raw"),
    ("asignacion_turnos",       "SELECT COUNT(*) as c FROM asignacion_turnos"),
    ("historial_areas validos", "SELECT COUNT(*) as c FROM historial_areas WHERE es_actual=1 AND validado=1"),
    ("justificaciones",         "SELECT COUNT(*) as c FROM justificaciones"),
    ("horas_extras",            "SELECT COUNT(*) as c FROM horas_extras"),
    ("bono_asignaciones",       "SELECT COUNT(*) as c FROM bono_asignaciones"),
]
for nombre, sql in tablas_clave:
    rows = q(sql)
    print(f"  {nombre:<30}: {rows[0]['c']}")
