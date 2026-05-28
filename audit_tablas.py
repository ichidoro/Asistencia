"""
Auditoria completa: todas las tablas de la BD vs modulos de la aplicacion.
Verifica conteos, claves foraneas y consistencia de cada tabla.
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

def q(sql):
    payload = json.dumps({"requests": [{"type": "execute", "stmt": {"sql": sql}}, {"type": "close"}]}).encode()
    req = urllib.request.Request(f"{TURSO_URL}/v2/pipeline", data=payload,
        headers={"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.loads(r.read())
    r2 = res["results"][0]
    if r2["type"] == "error":
        return []
    d = r2["response"]["result"]
    cols = [c["name"] for c in d["cols"]]
    return [{cols[i]: (row[i]["value"] if row[i]["type"] != "null" else None) for i in range(len(cols))} for row in d["rows"]]

# 1. Listar todas las tablas
tablas = q("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
nombres = [t["name"] for t in tablas if not t["name"].startswith("sqlite_") and not t["name"].startswith("libsql_")]
print(f"Total tablas: {len(nombres)}\n")

results = {}
for tabla in nombres:
    cnt = q(f"SELECT COUNT(*) as c FROM [{tabla}]")
    n = int(str(cnt[0]["c"])) if cnt else 0
    # Obtener columnas
    cols_raw = q(f"PRAGMA table_info([{tabla}])")
    cols = [c["name"] for c in cols_raw]
    results[tabla] = {"count": n, "cols": cols}

# Imprimir resumen
for tabla, info in sorted(results.items()):
    print(f"  {tabla:<40} {info['count']:>6} filas | cols: {', '.join(info['cols'][:8])}{'...' if len(info['cols'])>8 else ''}")

print("\n" + "="*80)

# 2. Verificaciones de integridad FK por tabla
print("\n=== VERIFICACIONES DE INTEGRIDAD ===\n")

checks = [
    # (descripcion, sql)
    ("empleados -> areas (area_id)",
     "SELECT COUNT(*) as c FROM empleados e LEFT JOIN areas a ON e.area_id = a.id WHERE a.id IS NULL AND e.area_id IS NOT NULL"),
    ("empleados -> cat_generos (genero_id)",
     "SELECT COUNT(*) as c FROM empleados e LEFT JOIN cat_generos cg ON e.genero_id = cg.id WHERE cg.id IS NULL AND e.genero_id IS NOT NULL"),
    ("empleados -> cargos (cargo_id)",
     "SELECT COUNT(*) as c FROM empleados e LEFT JOIN cargos c ON e.cargo_id = c.id WHERE c.id IS NULL AND e.cargo_id IS NOT NULL"),
    ("historial_areas -> empleados",
     "SELECT COUNT(*) as c FROM historial_areas ha LEFT JOIN empleados e ON ha.empleado_id = e.id WHERE e.id IS NULL"),
    ("historial_areas -> areas",
     "SELECT COUNT(*) as c FROM historial_areas ha LEFT JOIN areas a ON ha.area_id = a.id WHERE a.id IS NULL"),
    ("historial_areas activo+validado por empleado",
     "SELECT COUNT(*) as c FROM (SELECT empleado_id, COUNT(*) as n FROM historial_areas WHERE es_actual=1 AND validado=1 GROUP BY empleado_id HAVING n > 1)"),
    ("asistencias -> empleados",
     "SELECT COUNT(*) as c FROM asistencias a LEFT JOIN empleados e ON a.empleado_id = e.id WHERE e.id IS NULL"),
    ("asistencias -> turnos (turno_id)",
     "SELECT COUNT(*) as c FROM asistencias a LEFT JOIN turnos t ON a.turno_id = t.id WHERE t.id IS NULL AND a.turno_id IS NOT NULL"),
    ("logs_raw -> empleados",
     "SELECT COUNT(*) as c FROM logs_raw l LEFT JOIN empleados e ON l.empleado_id = e.id WHERE e.id IS NULL"),
    ("justificaciones -> empleados",
     "SELECT COUNT(*) as c FROM justificaciones j LEFT JOIN empleados e ON j.empleado_id = e.id WHERE e.id IS NULL"),
    ("justificaciones -> tipos (tipo_id)",
     "SELECT COUNT(*) as c FROM justificaciones j LEFT JOIN cat_tipos_justificacion ct ON j.tipo_id = ct.id WHERE ct.id IS NULL AND j.tipo_id IS NOT NULL"),
    ("asignacion_turnos -> empleados",
     "SELECT COUNT(*) as c FROM asignacion_turnos at LEFT JOIN empleados e ON at.empleado_id = e.id WHERE e.id IS NULL"),
    ("asignacion_turnos -> turnos",
     "SELECT COUNT(*) as c FROM asignacion_turnos at LEFT JOIN turnos t ON at.turno_id = t.id WHERE t.id IS NULL"),
    ("turno_dias -> turnos",
     "SELECT COUNT(*) as c FROM turno_dias td LEFT JOIN turnos t ON td.turno_id = t.id WHERE t.id IS NULL"),
    ("turno_areas -> turnos",
     "SELECT COUNT(*) as c FROM turno_areas ta LEFT JOIN turnos t ON ta.turno_id = t.id WHERE t.id IS NULL"),
    ("turno_areas -> areas",
     "SELECT COUNT(*) as c FROM turno_areas ta LEFT JOIN areas a ON ta.area_id = a.id WHERE a.id IS NULL"),
    ("bono_asignaciones -> empleados",
     "SELECT COUNT(*) as c FROM bono_asignaciones ba LEFT JOIN empleados e ON ba.empleado_id = e.id WHERE e.id IS NULL"),
    ("bono_asignaciones -> bonos",
     "SELECT COUNT(*) as c FROM bono_asignaciones ba LEFT JOIN bonos b ON ba.bono_id = b.id WHERE b.id IS NULL"),
    ("area_bonos -> areas",
     "SELECT COUNT(*) as c FROM area_bonos ab LEFT JOIN areas a ON ab.area_id = a.id WHERE a.id IS NULL"),
    ("area_bonos -> bonos",
     "SELECT COUNT(*) as c FROM area_bonos ab LEFT JOIN bonos b ON ab.bono_id = b.id WHERE b.id IS NULL"),
    ("horas_extras -> empleados",
     "SELECT COUNT(*) as c FROM horas_extras he LEFT JOIN empleados e ON he.empleado_id = e.id WHERE e.id IS NULL"),
    ("periodos_empleo -> empleados",
     "SELECT COUNT(*) as c FROM periodos_empleo pe LEFT JOIN empleados e ON pe.empleado_id = e.id WHERE e.id IS NULL"),
    ("bolsa_horas_resumen -> empleados",
     "SELECT COUNT(*) as c FROM bolsa_horas_resumen bh LEFT JOIN empleados e ON bh.empleado_id = e.id WHERE e.id IS NULL"),
    ("jornadas_especiales -> empleados",
     "SELECT COUNT(*) as c FROM jornadas_especiales je LEFT JOIN empleados e ON je.empleado_id = e.id WHERE e.id IS NULL"),
    ("usuarios (activos)",
     "SELECT COUNT(*) as c FROM usuarios WHERE activo=1"),
    ("roles (existentes)",
     "SELECT COUNT(*) as c FROM roles"),
    ("empleados activos sin asignacion_turnos",
     """SELECT COUNT(*) as c FROM empleados e
        LEFT JOIN asignacion_turnos at ON e.id = at.empleado_id AND (at.fecha_fin IS NULL OR at.fecha_fin >= date('now'))
        WHERE e.activo = 1 AND at.id IS NULL"""),
    ("empleados activos sin historial_areas valido",
     """SELECT COUNT(*) as c FROM empleados e
        LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual=1 AND ha.validado=1
        WHERE e.activo=1 AND ha.id IS NULL"""),
]

ok_count = 0
warn_count = 0
for desc, sql in checks:
    try:
        rows = q(sql)
        val = int(str(rows[0]["c"])) if rows else 0
        status = "OK " if val == 0 else "WARN"
        if val == 0:
            ok_count += 1
        else:
            warn_count += 1
        print(f"  [{status}] {desc}: {val}")
    except Exception as e:
        print(f"  [ERR] {desc}: {e}")

print(f"\n  Checks OK: {ok_count} | Warnings: {warn_count}")

# 3. Conteos clave por modulo
print("\n=== DATOS POR MODULO DE LA APLICACION ===\n")

modulos = [
    ("DASHBOARD",        "SELECT COUNT(*) as c FROM asistencias"),
    ("EMPLEADOS",        "SELECT COUNT(*) as c FROM empleados WHERE activo=1"),
    ("MARCACIONES",      "SELECT COUNT(*) as c FROM asistencias"),
    ("MARCACIONES raw",  "SELECT COUNT(*) as c FROM logs_raw"),
    ("HORARIOS/TURNOS",  "SELECT COUNT(*) as c FROM turnos"),
    ("TURNO_DIAS",       "SELECT COUNT(*) as c FROM turno_dias"),
    ("ASIGNAC.TURNOS",   "SELECT COUNT(*) as c FROM asignacion_turnos"),
    ("JUSTIFICACIONES",  "SELECT COUNT(*) as c FROM justificaciones"),
    ("HORAS EXTRAS",     "SELECT COUNT(*) as c FROM horas_extras"),
    ("BONOS ASIG.",      "SELECT COUNT(*) as c FROM bono_asignaciones"),
    ("AREA BONOS",       "SELECT COUNT(*) as c FROM area_bonos"),
    ("BOLSA HORAS",      "SELECT COUNT(*) as c FROM bolsa_horas_resumen"),
    ("PERIODOS EMPLEO",  "SELECT COUNT(*) as c FROM periodos_empleo"),
    ("JORNADAS ESP.",    "SELECT COUNT(*) as c FROM jornadas_especiales"),
    ("CALENDARIO",       "SELECT COUNT(*) as c FROM feriados"),
    ("USUARIOS",         "SELECT COUNT(*) as c FROM usuarios WHERE activo=1"),
    ("ROLES",            "SELECT COUNT(*) as c FROM roles"),
    ("CARGOS",           "SELECT COUNT(*) as c FROM cargos"),
    ("AREAS",            "SELECT COUNT(*) as c FROM areas"),
    ("TIPOS JUSTIF.",    "SELECT COUNT(*) as c FROM cat_tipos_justificacion"),
    ("ESTADOS",          "SELECT COUNT(*) as c FROM estados_empleado"),
    ("SYNC LOGS",        "SELECT COUNT(*) as c FROM sync_logs"),
    ("AUDITORIA",        "SELECT COUNT(*) as c FROM auditoria_logs"),
    ("PAGADORES",        "SELECT COUNT(*) as c FROM pagadores"),
    ("NOTIF AREAS",      "SELECT COUNT(*) as c FROM notificaciones_areas"),
]

for nombre, sql in modulos:
    try:
        rows = q(sql)
        val = rows[0]["c"] if rows else "N/A"
        print(f"  {nombre:<22}: {val:>6}")
    except Exception as e:
        print(f"  {nombre:<22}: ERROR - {e}")
