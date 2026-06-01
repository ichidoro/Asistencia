"""
Snapshot de datos reales para anclar el plan de correcciones
"""
import requests, json

TURSO_URL = "https://aguacol-ichidoro.aws-us-east-1.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODAwMjM1MzUsImlkIjoiMDE5ZTcxYWItOGYwMS03NWVkLWJmMDMtMDExZjk5MjE3ZWM4IiwicmlkIjoiZmE1OTYxZWYtNDEwOS00MTY1LTkwMzMtNzA4YmI5MzNiNjkwIn0.S3g__Bhy2on3tw8xzTugeFaGR-gNlz5D0Mcg-DAStaJQ_83qgLmllMZy-n5WjANJz-oTNok6h75XY1bHCmQJDg"

def query(sql):
    url = f"{TURSO_URL}/v2/pipeline"
    headers = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}
    body = {"requests": [{"type": "execute", "stmt": {"sql": sql}}, {"type": "close"}]}
    resp = requests.post(url, headers=headers, json=body, timeout=15)
    data = resp.json()
    if "results" not in data: return []
    result = data["results"][0]
    if "error" in result: 
        print(f"  ERROR: {result['error']}")
        return []
    resp_data = result.get("response", {}).get("result", {})
    cols = [c["name"] for c in resp_data.get("cols", [])]
    rows = []
    for r in resp_data.get("rows", []):
        row = {cols[i]: (cell.get("value") if cell.get("type") != "null" else None) for i, cell in enumerate(r)}
        rows.append(row)
    return rows

print("=" * 60)
print("1. ÁREAS")
print("=" * 60)
areas = query("SELECT id, nombre FROM areas ORDER BY nombre")
for a in areas: print(f"  #{a['id']} {a['nombre']}")

print("\n" + "=" * 60)
print("2. TURNOS + ÁREAS ASIGNADAS")
print("=" * 60)
turnos = query("""
    SELECT t.id, t.nombre, t.tipo_programacion, t.meta_horas_semanales,
           t.tolerancia_retraso_alerta, t.tolerancia_retraso_descuento,
           t.anclaje_entrada_minutos, t.anclaje_salida_minutos,
           t.descuento_colacion_auto, t.minutos_colacion_auto, t.umbral_horas_colacion
    FROM turnos t ORDER BY t.nombre
""")
for t in turnos:
    ta = query(f"SELECT a.nombre FROM turno_areas ta JOIN areas a ON ta.area_id = a.id WHERE ta.turno_id = {t['id']}")
    areas_str = ", ".join([r['nombre'] for r in ta]) if ta else "⚠️ SIN ÁREA"
    print(f"  #{t['id']} '{t['nombre']}' | {t['tipo_programacion']} | Meta: {t['meta_horas_semanales']}h")
    print(f"       Áreas: [{areas_str}]")
    print(f"       Tolerancias: alerta={t['tolerancia_retraso_alerta']}min, desc={t['tolerancia_retraso_descuento']}min")
    print(f"       Anclaje: entrada={t['anclaje_entrada_minutos']}min, salida={t['anclaje_salida_minutos']}min")
    print(f"       Colación: auto={t['descuento_colacion_auto']}, min={t['minutos_colacion_auto']}, umbral={t['umbral_horas_colacion']}h")

print("\n" + "=" * 60)
print("3. EMPLEADOS POR ÁREA (activos)")
print("=" * 60)
emps = query("""
    SELECT e.id, e.nombre, e.apellido_paterno, e.rut, a.nombre as area, e.cargo
    FROM empleados e
    LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1
    LEFT JOIN areas a ON ha.area_id = a.id
    WHERE e.activo = 1
    ORDER BY a.nombre, e.apellido_paterno
""")
current_area = None
for e in emps:
    if e['area'] != current_area:
        current_area = e['area']
        print(f"\n  === {current_area or 'SIN ÁREA'} ===")
    print(f"    #{e['id']} {e['apellido_paterno']} {e['nombre']} | RUT: {e['rut']} | Cargo: {e['cargo']}")

print("\n" + "=" * 60)
print("4. ROLES Y USUARIOS")
print("=" * 60)
users = query("""
    SELECT u.id, u.username, r.nombre as rol, u.alcance_global, u.areas_json
    FROM usuarios u
    LEFT JOIN roles r ON u.rol_id = r.id
    ORDER BY u.id
""")
for u in users:
    print(f"  #{u['id']} @{u['username']} | Rol: {u['rol']} | Global: {u['alcance_global']} | Áreas: {u['areas_json']}")

print("\n" + "=" * 60)
print("5. ASIGNACIONES DE TURNO VIGENTES")
print("=" * 60)
asig = query("""
    SELECT at.empleado_id, e.nombre || ' ' || e.apellido_paterno as emp,
           t.nombre as turno, at.fecha_inicio, at.fecha_fin
    FROM asignacion_turnos at
    JOIN empleados e ON at.empleado_id = e.id
    JOIN turnos t ON at.turno_id = t.id
    WHERE at.fecha_fin IS NULL
    ORDER BY t.nombre, e.apellido_paterno
    LIMIT 30
""")
for a in asig:
    print(f"  {a['emp']} → '{a['turno']}' desde {a['fecha_inicio']}")

print("\n" + "=" * 60)
print("6. PERIODOS RRHH")
print("=" * 60)
periodos = query("SELECT * FROM periodos_rrhh ORDER BY fecha_inicio DESC LIMIT 5")
for p in periodos:
    print(f"  #{p.get('id')} | {p.get('fecha_inicio')} a {p.get('fecha_fin')} | Activo: {p.get('activo')} | Área: {p.get('area','TODAS')}")

print("\n" + "=" * 60)
print("7. CIERRES DE PERIODO")
print("=" * 60)
cierres = query("SELECT * FROM cierres_periodos ORDER BY fecha_cierre DESC LIMIT 10")
for c in cierres:
    print(f"  #{c.get('id')} | Área: {c.get('area')} | {c.get('fecha_inicio')} a {c.get('fecha_fin')} | Cerrado: {c.get('fecha_cierre')}")

print("\n" + "=" * 60)
print("8. ESTADÍSTICAS DE TABLAS")
print("=" * 60)
tables = ["empleados", "asistencias", "turnos", "turno_dias", "turno_areas", 
          "asignacion_turnos", "logs_raw_marcaciones", "justificaciones",
          "horas_extras", "cierres_periodos", "periodos_rrhh", "roles", 
          "usuarios", "rol_permisos", "areas", "bonos", "bono_reglas"]
for t in tables:
    count = query(f"SELECT COUNT(*) as n FROM {t}")
    print(f"  {t}: {count[0]['n'] if count else 'ERROR'} registros")

print("\n" + "=" * 60)
print("9. MUESTRA DE ASISTENCIA RECIENTE (últimos 3 días)")
print("=" * 60)
asis = query("""
    SELECT a.empleado_id, e.apellido_paterno, a.fecha, a.estado, 
           a.hora_entrada_real, a.hora_salida_real, a.horas_trabajadas,
           a.horas_teoricas, a.minutos_atraso, a.minutos_deuda,
           a.minutos_extra_bruto, a.deuda_condonada
    FROM asistencias a
    JOIN empleados e ON a.empleado_id = e.id
    WHERE a.fecha >= date('now', '-3 days')
    ORDER BY a.fecha DESC, e.apellido_paterno
    LIMIT 15
""")
for a in asis:
    print(f"  {a['fecha']} | {a['apellido_paterno']} | {a['estado']} | In:{a['hora_entrada_real']} Out:{a['hora_salida_real']} | Trab:{a['horas_trabajadas']}h Teor:{a['horas_teoricas']}h | Atraso:{a['minutos_atraso']}min Deuda:{a['minutos_deuda']}min | HE:{a['minutos_extra_bruto']}min | Condonada:{a['deuda_condonada']}")

print("\n" + "=" * 60)
print("10. BONOS CONFIGURADOS")
print("=" * 60)
bonos = query("SELECT b.id, b.nombre, b.tipo, b.monto_base FROM bonos b ORDER BY b.nombre")
for b in bonos:
    reglas = query(f"SELECT * FROM bono_reglas WHERE bono_id = {b['id']}")
    area_bonos = query(f"SELECT a.nombre FROM area_bonos ab JOIN areas a ON ab.area_id = a.id WHERE ab.bono_id = {b['id']}")
    areas_str = ", ".join([r['nombre'] for r in area_bonos]) if area_bonos else "TODAS"
    print(f"  #{b['id']} '{b['nombre']}' | Tipo: {b['tipo']} | Base: ${b['monto_base']} | Áreas: [{areas_str}]")
    for r in reglas:
        print(f"       Regla: {r}")

print("\nFIN")
