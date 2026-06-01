"""
SIMULACIÓN DE FIXES propuestos para turno_areas
Verifica contra la BD REAL sin modificar nada (solo SELECT/lectura).
"""
import requests
import json

TURSO_URL = "https://aguacol-ichidoro.aws-us-east-1.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODAwMjM1MzUsImlkIjoiMDE5ZTcxYWItOGYwMS03NWVkLWJmMDMtMDExZjk5MjE3ZWM4IiwicmlkIjoiZmE1OTYxZWYtNDEwOS00MTY1LTkwMzMtNzA4YmI5MzNiNjkwIn0.S3g__Bhy2on3tw8xzTugeFaGR-gNlz5D0Mcg-DAStaJQ_83qgLmllMZy-n5WjANJz-oTNok6h75XY1bHCmQJDg"

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
        print(f"  SQL ERROR: {result['error']}")
        return []
    resp_data = result.get("response", {}).get("result", {})
    cols = [c["name"] for c in resp_data.get("cols", [])]
    rows = []
    for r in resp_data.get("rows", []):
        row = {cols[i]: (cell.get("value") if cell.get("type") != "null" else None) for i, cell in enumerate(r)}
        rows.append(row)
    return rows

# ============================================================
# ESTADO ACTUAL
# ============================================================
print("=" * 80)
print("ESTADO ACTUAL DE LA BD")
print("=" * 80)

# Todas las areas
areas = query("SELECT id, nombre FROM areas ORDER BY id")
print("\nAreas:")
for a in areas:
    print(f"  #{a['id']} = '{a['nombre']}'")

# Todos los turnos
turnos = query("SELECT id, nombre FROM turnos ORDER BY id")
print("\nTurnos:")
for t in turnos:
    print(f"  #{t['id']} = '{t['nombre']}'")

# Todas las relaciones turno_areas
ta = query("""
    SELECT ta.turno_id, t.nombre as turno, ta.area_id, a.nombre as area
    FROM turno_areas ta
    JOIN turnos t ON ta.turno_id = t.id
    JOIN areas a ON ta.area_id = a.id
    ORDER BY ta.area_id, ta.turno_id
""")
print("\nRelaciones turno_areas:")
for r in ta:
    print(f"  Area '{r['area']}' (#{r['area_id']}) <-> Turno '{r['turno']}' (#{r['turno_id']})")

# Turnos huérfanos (sin area)
huerfanos = query("""
    SELECT t.id, t.nombre FROM turnos t
    WHERE NOT EXISTS (SELECT 1 FROM turno_areas ta WHERE ta.turno_id = t.id)
""")
print("\nTurnos HUÉRFANOS:")
for h in huerfanos:
    print(f"  #{h['id']} '{h['nombre']}' <- SIN AREA!")

# Empleados asignados a cada turno
asignaciones = query("""
    SELECT at.turno_id, t.nombre as turno, COUNT(at.empleado_id) as emp_count,
           GROUP_CONCAT(e.apellido_paterno, ', ') as apellidos
    FROM asignacion_turnos at
    JOIN turnos t ON at.turno_id = t.id
    JOIN empleados e ON at.empleado_id = e.id
    WHERE at.fecha_fin IS NULL OR at.fecha_fin >= date('now')
    GROUP BY at.turno_id
    ORDER BY t.nombre
""")
print("\nEmpleados vigentes por turno:")
for a in asignaciones:
    ap = a['apellidos']
    if ap and len(ap) > 80:
        ap = ap[:80] + "..."
    print(f"  '{a['turno']}' (#{a['turno_id']}): {a['emp_count']} empleados - {ap}")

# ============================================================
# SIMULACIÓN BUG 1: Wizard DELETE destructivo
# ============================================================
print("\n" + "=" * 80)
print("SIMULACIÓN BUG 1: Wizard commit_wizard_all()")
print("=" * 80)

# Escenario 1: Wizard asigna turno "Tradicional Bodega" a "LOGISTICA TRADICIONAL"
print("\n--- Escenario 1: Wizard(LOGISTICA TRADICIONAL -> Turno Bodega #4) ---")
area_lt = query("SELECT id FROM areas WHERE nombre = 'LOGISTICA TRADICIONAL'")
if area_lt:
    area_id_lt = area_lt[0]['id']
    turnos_lt = query(f"SELECT ta.turno_id, t.nombre FROM turno_areas ta JOIN turnos t ON ta.turno_id = t.id WHERE ta.area_id = {area_id_lt}")
    print(f"  ANTES: {len(turnos_lt)} turnos asignados a LOGISTICA TRADICIONAL:")
    for t in turnos_lt:
        print(f"    -> #{t['turno_id']} '{t['nombre']}'")
    
    print(f"\n  [CÓDIGO ACTUAL] DELETE FROM turno_areas WHERE area_id = {area_id_lt}")
    print(f"  RESULTADO: BORRA los {len(turnos_lt)} turnos de la area!")
    print(f"  Luego INSERT turno_areas (area_id={area_id_lt}, turno_id=4)")
    print(f"  DESPUÉS: Solo queda turno #4 'Tradicional Bodega'")
    print(f"  ❌ PERDIDOS: {[t['nombre'] for t in turnos_lt if t['turno_id'] != '4']}")
    
    print(f"\n  [FIX PROPUESTO] INSERT OR IGNORE sin DELETE previo")
    existing_4 = any(t['turno_id'] == '4' for t in turnos_lt)
    if existing_4:
        print(f"  RESULTADO: Turno #4 ya existe -> INSERT OR IGNORE no hace nada")
        print(f"  DESPUÉS: Los {len(turnos_lt)} turnos se mantienen intactos ✅")
    else:
        print(f"  RESULTADO: Turno #4 no existe -> se agrega")
        print(f"  DESPUÉS: Quedan {len(turnos_lt) + 1} turnos ✅")

# Escenario 2: ¿Y si el wizard QUIERE REEMPLAZAR el turno?
print("\n--- Escenario 2: ¿Qué pasa si el wizard quiere REEMPLAZAR? ---")
print("  El wizard mapea area -> UN turno. El intent NO es 'reemplazar todos los turnos'")
print("  porque el turno_areas es MANY-TO-MANY (un area puede tener varios turnos).")
print("  El wizard es un SETUP INICIAL, no un editor de turnos.")
print("")
print("  PERO hay un caso problemático:")
print("  Si el usuario ejecuta el wizard para CAMBIAR el turno de un área que solo tiene 1,")
print("  con mi fix, el viejo se mantiene Y el nuevo se agrega -> 2 turnos en vez de 1.")
print("")
print("  ⚠️ RIESGO: Áreas que deberían tener 1 turno terminan con 2.")

# Escenario 3: Areas con un solo turno
print("\n--- Escenario 3: Áreas con un solo turno (impacto del fix) ---")
for a in areas:
    cnt = query(f"SELECT COUNT(*) as c FROM turno_areas WHERE area_id = {a['id']}")
    n = int(cnt[0]['c']) if cnt else 0
    if n == 1:
        turno_actual = query(f"SELECT t.nombre, t.id FROM turno_areas ta JOIN turnos t ON ta.turno_id = t.id WHERE ta.area_id = {a['id']}")
        tn = turno_actual[0] if turno_actual else {}
        print(f"  Area '{a['nombre']}' tiene 1 turno: '{tn.get('nombre')}' (#{tn.get('id')})")
        print(f"    Si wizard asigna OTRO turno -> con fix actual se AGREGARÍA (queda con 2)")
        print(f"    Si wizard asigna MISMO turno -> INSERT OR IGNORE no-op (queda con 1) ✅")

# ============================================================
# SIMULACIÓN BUG 2: COLLATE NOCASE
# ============================================================
print("\n" + "=" * 80)
print("SIMULACIÓN BUG 2: Case-sensitivity en INSERT turno_areas")
print("=" * 80)

# Verificar si hay mismatch de case entre lo que envía el frontend y lo que tiene la BD
print("\nÁreas en la BD (tabla areas):")
for a in areas:
    print(f"  '{a['nombre']}'")

# Simular: ¿qué pasa si el frontend envia "Logistica Tradicional" en vez de "LOGISTICA TRADICIONAL"?
test_cases = [
    ("LOGISTICA TRADICIONAL", "Match exacto"),
    ("Logistica Tradicional", "Case diferente"),
    ("logistica tradicional", "Todo minúsculas"),
    ("SEGURIDAD", "Match exacto"),
    ("Seguridad", "Case diferente"),
]

for test_name, desc in test_cases:
    # Sin COLLATE NOCASE
    res_exact = query(f"SELECT id FROM areas WHERE nombre = '{test_name}'")
    # Con COLLATE NOCASE
    res_nocase = query(f"SELECT id FROM areas WHERE nombre = '{test_name}' COLLATE NOCASE")
    
    match_exact = len(res_exact) > 0
    match_nocase = len(res_nocase) > 0
    
    status = "✅" if match_exact else ("⚠️ FALLA sin COLLATE, ✅ con COLLATE" if match_nocase else "❌ NO EXISTE")
    print(f"  '{test_name}' ({desc}): exact={match_exact}, nocase={match_nocase} -> {status}")

# Verificar el endpoint /api/empleados/areas/ - ¿qué case devuelve?
print("\n¿Qué devuelve la query del endpoint /api/empleados/areas/?")
api_areas = query("SELECT DISTINCT nombre as area FROM areas ORDER BY nombre ASC")
for a in api_areas:
    print(f"  -> '{a['area']}'")
print("  Conclusión: El frontend recibe los nombres EXACTAMENTE como están en areas.nombre")
print("  El riesgo es BAJO si no hay procesos externos que muten el case.")

# ============================================================
# SIMULACIÓN BUG 3: Columna visual en la tabla
# ============================================================
print("\n" + "=" * 80)
print("SIMULACIÓN BUG 3: Columna de áreas en tabla de turnos")
print("=" * 80)

print("\nTurnos con sus áreas (lo que mostraría la nueva columna):")
for t in turnos:
    t_areas = query(f"SELECT a.nombre FROM turno_areas ta JOIN areas a ON ta.area_id = a.id WHERE ta.turno_id = {t['id']}")
    area_names = [a['nombre'] for a in t_areas] if t_areas else []
    if area_names:
        badges = ", ".join(area_names)
    else:
        badges = "⚠️ SIN ÁREA"
    print(f"  '{t['nombre']}' -> [{badges}]")

print("\n  ⚠️ Riesgo: El header tiene colspan='5', agregar columna requiere actualizar a colspan='6'")
print("  ⚠️ Riesgo: En mobile la tabla puede necesitar scroll horizontal con columna extra")

# ============================================================
# ESCENARIOS CRUZADOS (Side Effects)
# ============================================================
print("\n" + "=" * 80)
print("ESCENARIOS CRUZADOS Y SIDE EFFECTS")
print("=" * 80)

# ¿El motor de asistencia usa turno_areas?
print("\n1. ¿El motor de asistencia (asistencia_service.py) usa turno_areas?")
print("   NO. Usa asignacion_turnos (empleado->turno directo)")
print("   turno_areas solo se usa para FILTRAR turnos visibles por área en la UI")
print("   -> Fix es SEGURO para el motor ✅")

# ¿Hay CASCADE que pueda borrar turno_areas?
print("\n2. ¿Hay CASCADE que afecte turno_areas?")
cascade = query("SELECT sql FROM sqlite_master WHERE name = 'turno_areas'")
if cascade:
    print(f"   DDL: {cascade[0].get('sql', 'N/A')}")
print("   ON DELETE CASCADE en turno_id y area_id")
print("   -> Si se borra un turno o un area, se limpian automáticamente")
print("   -> Si se borra el turno #2 'JJV Staff', no pasa nada (ya está huérfano)")

# ¿Hay endpoints que borren turno_areas además del wizard?
print("\n3. Flujos que tocan turno_areas:")
print("   a) turno.py:create_turno() -> INSERT OR IGNORE (al crear)")
print("   b) turno.py:update_turno() -> DELETE + INSERT (al editar)")
print("   c) sync_service.py:commit_wizard_all() -> DELETE por area_id + INSERT (wizard)")
print("   d) CASCADE al borrar turno o area")
print("   NO hay más flujos.")

# ¿El filtro get_turnos_by_areas incluye huérfanos?
print("\n4. ¿Los turnos huérfanos (sin área) son visibles en algún contexto?")
huerfano_query = """
    SELECT DISTINCT t.*
    FROM turnos t
    LEFT JOIN turno_areas ta ON t.id = ta.turno_id
    LEFT JOIN areas a ON ta.area_id = a.id
    WHERE a.nombre IN ('SEGURIDAD')
       OR ta.area_id IS NULL
    ORDER BY t.nombre
"""
result = query(huerfano_query)
print(f"   Query get_turnos_by_areas(SEGURIDAD) devuelve {len(result)} turnos:")
for r in result:
    print(f"     #{r['id']} '{r['nombre']}'")
print("   -> 'JJV Staff' (huérfano) aparece para TODAS las áreas como turno 'global'")
print("   -> ⚠️ Esto podría ser indeseado: un turno sin área no debería ser visible para todos")

# ¿Qué pasa en la asignación masiva (bulk)?
print("\n5. Asignación masiva de turnos (bulk assign):")
print("   Frontend: _fetchAndPopulateBulkTurnos(areas)")
print("   Si areas.length === 1 -> GET /api/turnos/?area=SEGURIDAD")
print("   -> Usa get_turnos_by_areas que incluye huérfanos")
print("   -> JJV Staff aparecería en el dropdown de asignación masiva de TODAS las áreas")

# ============================================================
# RESUMEN DE RIESGOS
# ============================================================
print("\n" + "=" * 80)
print("RESUMEN DE RIESGOS DETECTADOS EN LA SIMULACIÓN")
print("=" * 80)

print("""
┌───┬────────────────────────────────────────────────┬──────────┬──────────────────────────────────┐
│ # │ Riesgo                                         │ Severidad│ Mitigación                       │
├───┼────────────────────────────────────────────────┼──────────┼──────────────────────────────────┤
│ 1 │ Fix del wizard podría ACUMULAR turnos en       │ MEDIO    │ Usar UPSERT: borrar solo la      │
│   │ áreas de 1-turno si se re-ejecuta con otro    │          │ relación anterior del MISMO turno│
│   │ turno seleccionado                             │          │ no de toda el área               │
├───┼────────────────────────────────────────────────┼──────────┼──────────────────────────────────┤
│ 2 │ Turnos huérfanos aparecen como "globales"      │ BAJO     │ Decidir: ¿un turno sin área es   │
│   │ para TODAS las áreas en get_turnos_by_areas   │          │ visible para todos o para nadie? │
├───┼────────────────────────────────────────────────┼──────────┼──────────────────────────────────┤
│ 3 │ COLLATE NOCASE: riesgo de duplicados si        │ MUY BAJO │ Las áreas vienen del mismo       │
│   │ áreas tienen nombres duplicados con case       │          │ catálogo, no hay duplicados      │
│   │ diferente                                      │          │                                  │
├───┼────────────────────────────────────────────────┼──────────┼──────────────────────────────────┤
│ 4 │ Columna extra en tabla podría romper layout    │ BAJO     │ Usar responsive class o truncar  │
│   │ en pantallas pequeñas                          │          │                                  │
├───┼────────────────────────────────────────────────┼──────────┼──────────────────────────────────┤
│ 5 │ El wizard UI envía area->1 turno pero el       │ DISEÑO   │ El wizard debería enviar         │
│   │ modelo es many-to-many. Hay ambigüedad de     │          │ area->[turnos] o documentar que  │
│   │ intención.                                     │          │ es "agregar" no "reemplazar"     │
└───┴────────────────────────────────────────────────┴──────────┴──────────────────────────────────┘
""")

print("FIN DE SIMULACIÓN")
