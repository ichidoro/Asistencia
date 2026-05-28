"""
Limpia la tabla areas dejando SOLO las 4 areas validas del sistema:
  - PRODUCCION (id=1, ya existia)
  - LOGISTICA TRADICIONAL (id=9, agregada por guardian)
  - MANTENCION (id=10, agregada por guardian)
  - SEGURIDAD (id=14, agregada por guardian)

Ademas:
  - Migra empleados de LOGISTICA (id=6) -> LOGISTICA TRADICIONAL (id=9)
  - Migra historial_areas de area_id=6 -> area_id=9
  - Elimina las 7 areas invalidas
  - Actualiza areas_json de usuarios
"""
import urllib.request, json, urllib.parse

env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

TURSO_URL = env['TURSO_DATABASE_URL'].replace('libsql://', 'https://')
TURSO_TOKEN = env['TURSO_AUTH_TOKEN']

def post_turso(stmts):
    endpoint = f"{TURSO_URL}/v2/pipeline"
    payload = json.dumps({"requests": stmts + [{"type": "close"}]}).encode()
    req = urllib.request.Request(endpoint, data=payload,
        headers={'Authorization': f'Bearer {TURSO_TOKEN}', 'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def q(sql, params=None):
    stmt = {"sql": sql}
    if params:
        stmt["args"] = params
    res = post_turso([{"type": "execute", "stmt": stmt}])
    r = res['results'][0]
    if r['type'] == 'error':
        raise Exception(r['error']['message'])
    d = r['response']['result']
    cols = [c['name'] for c in d['cols']]
    return [{cols[i]: (row[i]['value'] if row[i]['type'] != 'null' else None) for i in range(len(cols))} for row in d['rows']]

def exec_sql(sql, params=None):
    stmt = {"sql": sql}
    if params:
        stmt["args"] = params
    res = post_turso([{"type": "execute", "stmt": stmt}])
    r = res['results'][0]
    if r['type'] == 'error':
        raise Exception(r['error']['message'])
    return r['response']['result'].get('affected_row_count', 0)

# =============================================
# 1. ESTADO ACTUAL
# =============================================
print("=== ESTADO ACTUAL DE AREAS ===")
areas = q("SELECT * FROM areas ORDER BY CAST(id AS INTEGER)")
for a in areas:
    emp_count = q(f"SELECT COUNT(*) as c FROM empleados WHERE area_id={a['id']}")[0]['c']
    ha_count  = q(f"SELECT COUNT(*) as c FROM historial_areas WHERE area_id={a['id']}")[0]['c']
    print(f"  ID={a['id']:>3}: {a['nombre']:<30} | {emp_count} empleados | {ha_count} historial")

# =============================================
# 2. AREAS VALIDAS (lo que dice el usuario)
# =============================================
AREAS_VALIDAS = {
    "PRODUCCION",
    "LOGISTICA TRADICIONAL",
    "MANTENCION",
    "SEGURIDAD"
}
print(f"\nAreas validas: {sorted(AREAS_VALIDAS)}")

# Obtener IDs de areas validas
area_ids_validos = {}
for a in areas:
    if a['nombre'] in AREAS_VALIDAS:
        area_ids_validos[a['nombre']] = int(a['id'])

print(f"IDs validos encontrados: {area_ids_validos}")

# Verificar que las 4 areas existen
for nombre in AREAS_VALIDAS:
    if nombre not in area_ids_validos:
        print(f"  FALTA: {nombre} no existe en DB!")

id_logistica_trad = area_ids_validos.get("LOGISTICA TRADICIONAL")
id_produccion     = area_ids_validos.get("PRODUCCION")
id_mantencion     = area_ids_validos.get("MANTENCION")
id_seguridad      = area_ids_validos.get("SEGURIDAD")

# =============================================
# 3. MIGRAR EMPLEADOS DE AREAS INVALIDAS
# =============================================
print("\n=== MIGRACION DE EMPLEADOS ===")

# LOGISTICA (id=6) -> LOGISTICA TRADICIONAL
id_logistica_invalida = None
for a in areas:
    if a['nombre'] == 'LOGISTICA':
        id_logistica_invalida = int(a['id'])
        break

if id_logistica_invalida and id_logistica_trad:
    emp_en_logistica = q(f"SELECT COUNT(*) as c FROM empleados WHERE area_id={id_logistica_invalida}")[0]['c']
    ha_en_logistica  = q(f"SELECT COUNT(*) as c FROM historial_areas WHERE area_id={id_logistica_invalida}")[0]['c']
    print(f"  LOGISTICA (id={id_logistica_invalida}) -> LOGISTICA TRADICIONAL (id={id_logistica_trad})")
    print(f"    Empleados a migrar: {emp_en_logistica}")
    print(f"    Historial a migrar: {ha_en_logistica}")

    affected_emp = exec_sql(
        f"UPDATE empleados SET area_id={id_logistica_trad} WHERE area_id={id_logistica_invalida}"
    )
    affected_ha = exec_sql(
        f"UPDATE historial_areas SET area_id={id_logistica_trad} WHERE area_id={id_logistica_invalida}"
    )
    print(f"    Empleados migrados: {affected_emp}")
    print(f"    Historial migrado:  {affected_ha}")
else:
    print("  LOGISTICA invalida no encontrada o LOGISTICA TRADICIONAL no existe.")

# Verificar si hay otros empleados en areas invalidas
print("\n  Verificando empleados en otras areas invalidas...")
for a in areas:
    if a['nombre'] not in AREAS_VALIDAS:
        aid = int(a['id'])
        cnt = q(f"SELECT COUNT(*) as c FROM empleados WHERE area_id={aid}")[0]['c']
        cnt_ha = q(f"SELECT COUNT(*) as c FROM historial_areas WHERE area_id={aid}")[0]['c']
        if int(str(cnt)) > 0 or int(str(cnt_ha)) > 0:
            print(f"  ADVERTENCIA: {a['nombre']} (id={aid}) tiene {cnt} emp y {cnt_ha} historial!")

# =============================================
# 4. ELIMINAR AREAS INVALIDAS
# =============================================
print("\n=== ELIMINANDO AREAS INVALIDAS ===")
ids_a_eliminar = []
for a in areas:
    if a['nombre'] not in AREAS_VALIDAS:
        ids_a_eliminar.append((int(a['id']), a['nombre']))

for aid, nombre in ids_a_eliminar:
    # Verificar que no tiene empleados antes de eliminar
    emp_count = int(str(q(f"SELECT COUNT(*) as c FROM empleados WHERE area_id={aid}")[0]['c']))
    ha_count  = int(str(q(f"SELECT COUNT(*) as c FROM historial_areas WHERE area_id={aid}")[0]['c']))
    if emp_count > 0 or ha_count > 0:
        print(f"  SALTANDO {nombre} (id={aid}): aun tiene {emp_count} emp y {ha_count} historial")
        continue

    # Eliminar alias primero
    exec_sql(f"DELETE FROM areas_alias WHERE area_id={aid}")
    # Eliminar turno_areas
    try:
        exec_sql(f"DELETE FROM turno_areas WHERE area_id={aid}")
    except:
        pass
    # Eliminar area
    affected = exec_sql(f"DELETE FROM areas WHERE id={aid}")
    print(f"  Eliminada: {nombre} (id={aid}): {affected} filas")

# =============================================
# 5. ACTUALIZAR areas_json DE USUARIOS
# =============================================
print("\n=== ACTUALIZANDO areas_json DE USUARIOS ===")
usuarios = q("SELECT id, username, areas_json FROM usuarios")
areas_json_validas = json.dumps(sorted(list(AREAS_VALIDAS)))
for u in usuarios:
    old_areas = json.loads(u['areas_json'] or '[]') if u['areas_json'] else []
    new_areas = sorted([a for a in old_areas if a in AREAS_VALIDAS])

    # Admin con alcance_global -> darle todas las areas validas
    # Usuarios zonales -> filtrar solo sus areas validas
    exec_sql(
        f"UPDATE usuarios SET areas_json=? WHERE id={u['id']}",
        [{"type": "text", "value": json.dumps(new_areas if new_areas else sorted(list(AREAS_VALIDAS)))}]
    )
    print(f"  {u['username']}: {old_areas} -> {new_areas or sorted(list(AREAS_VALIDAS))}")

# =============================================
# 6. ESTADO FINAL
# =============================================
print("\n=== ESTADO FINAL DE AREAS ===")
areas_final = q("SELECT * FROM areas ORDER BY CAST(id AS INTEGER)")
for a in areas_final:
    emp_count = q(f"SELECT COUNT(*) as c FROM empleados WHERE area_id={a['id']}")[0]['c']
    print(f"  ID={a['id']:>3}: {a['nombre']:<30} | {emp_count} empleados")

print(f"\nTotal areas: {len(areas_final)}")

# =============================================
# 7. VERIFICACION DE INTEGRIDAD FK
# =============================================
print("\n=== VERIFICACION DE INTEGRIDAD FK ===")
huerfanos = q("""
    SELECT e.area_id, COUNT(*) as count
    FROM empleados e
    LEFT JOIN areas a ON e.area_id = a.id
    WHERE a.id IS NULL
    GROUP BY e.area_id
""")
if huerfanos:
    print("  ERROR: Empleados con area_id invalido:")
    for h in huerfanos:
        print(f"    area_id={h['area_id']}: {h['count']} empleados")
else:
    print("  OK: Todos los empleados tienen area_id valido")
