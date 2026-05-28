"""
Auditoria completa: compara todas las tablas de Turso Cloud con el respaldo.
1. Compara empleados.json del respaldo vs cloud
2. Obtiene conteo de filas y columnas de TODAS las tablas en cloud
3. Genera reporte detallado de diferencias
"""
import json, urllib.request, os

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
        headers={'Authorization': f'Bearer {TURSO_TOKEN}', 'Content-Type': 'application/json'},
        method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def q(sql):
    res = post([{"type": "execute", "stmt": {"sql": sql}}])
    r = res['results'][0]
    if r['type'] == 'error':
        raise Exception(r['error']['message'])
    d = r['response']['result']
    cols = [c['name'] for c in d['cols']]
    rows = [{cols[i]: (row[i]['value'] if row[i]['type'] != 'null' else None)
             for i in range(len(cols))} for row in d['rows']]
    return cols, rows

SEPARATOR = "=" * 65

# =========================================================
# PASO 1: Inventario de todas las tablas en Turso Cloud
# =========================================================
print(SEPARATOR)
print("AUDITORIA COMPLETA DE BASE DE DATOS TURSO CLOUD")
print(SEPARATOR)

print("\n[ INVENTARIO DE TABLAS ]")
_, tables = q("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
table_names = [t['name'] for t in tables]
print(f"Total tablas: {len(table_names)}")

table_stats = {}
for tname in table_names:
    try:
        # Contar filas
        _, cnt = q(f"SELECT COUNT(*) as c FROM \"{tname}\"")
        row_count = int(cnt[0]['c'])
        # Obtener columnas
        _, cols_info = q(f"PRAGMA table_info(\"{tname}\")")
        col_count = len(cols_info)
        col_names = [c['name'] for c in cols_info]
        table_stats[tname] = {
            'filas': row_count,
            'columnas': col_count,
            'col_names': col_names
        }
        print(f"  {tname:<40} {row_count:>6} filas  {col_count:>2} cols")
    except Exception as e:
        table_stats[tname] = {'filas': -1, 'columnas': -1, 'col_names': [], 'error': str(e)}
        print(f"  {tname:<40} ERROR: {e}")

# =========================================================
# PASO 2: Comparar empleados.json vs cloud
# =========================================================
print(f"\n{SEPARATOR}")
print("[ COMPARACION EMPLEADOS: RESPALDO vs TURSO CLOUD ]")
print(SEPARATOR)

with open('Respaldo/empleados.json', encoding='utf-8') as f:
    backup_emp = json.load(f)

backup_by_id = {str(e['id']): e for e in backup_emp}
backup_cols = list(backup_emp[0].keys()) if backup_emp else []

print(f"Respaldo: {len(backup_emp)} empleados, {len(backup_cols)} columnas")
print(f"Columnas respaldo: {backup_cols}")

# Leer empleados del cloud por PK
print(f"\nLeyendo empleados del cloud...")
cloud_emp = {}
all_ids_backup = sorted([int(k) for k in backup_by_id.keys()])

# Obtener todos los IDs del cloud
_, cloud_ids_rows = q("SELECT id FROM empleados ORDER BY id")
cloud_ids = [int(r['id']) for r in cloud_ids_rows]
print(f"Cloud: {len(cloud_ids)} empleados")
print(f"IDs en cloud: {cloud_ids[:5]}...{cloud_ids[-3:] if len(cloud_ids)>3 else ''}")

# IDs en backup pero no en cloud
ids_solo_backup = [i for i in all_ids_backup if i not in cloud_ids]
# IDs en cloud pero no en backup
ids_solo_cloud = [i for i in cloud_ids if i not in all_ids_backup]

print(f"\nIDs en RESPALDO pero NO en cloud ({len(ids_solo_backup)}): {ids_solo_backup}")
print(f"IDs en CLOUD pero NO en respaldo ({len(ids_solo_cloud)}): {ids_solo_cloud}")

# Leer datos completos del cloud para comparacion campo a campo
print(f"\nComparando celda por celda para empleados en comun...")
ids_en_comun = [i for i in all_ids_backup if i in cloud_ids]
diferencias = []
iguales = 0

for emp_id in ids_en_comun:
    try:
        _, rows = q(f"SELECT * FROM empleados WHERE id={emp_id}")
        if not rows:
            diferencias.append({'id': emp_id, 'tipo': 'SIN_DATOS_CLOUD', 'campo': '-', 'backup': '-', 'cloud': '-'})
            continue
        cloud_row = rows[0]
        backup_row = backup_by_id[str(emp_id)]

        emp_ok = True
        for col in backup_cols:
            bval = backup_row.get(col)
            cval = cloud_row.get(col)
            # Normalizar para comparacion
            bval_str = str(bval) if bval is not None else 'NULL'
            cval_str = str(cval) if cval is not None else 'NULL'
            # Normalizar numeros flotantes
            if bval_str.endswith('.0') and not cval_str.endswith('.0'):
                bval_str = bval_str[:-2]
            if cval_str.endswith('.0') and not bval_str.endswith('.0'):
                cval_str = cval_str[:-2]

            if bval_str != cval_str:
                diferencias.append({
                    'id': emp_id,
                    'tipo': 'DIFF_CAMPO',
                    'campo': col,
                    'backup': bval_str[:60],
                    'cloud': cval_str[:60]
                })
                emp_ok = False
        if emp_ok:
            iguales += 1
    except Exception as e:
        diferencias.append({'id': emp_id, 'tipo': 'ERROR', 'campo': '-', 'backup': '-', 'cloud': str(e)[:80]})

print(f"\nResultados comparacion:")
print(f"  Empleados identicos:    {iguales}/{len(ids_en_comun)}")
print(f"  Empleados con diffs:    {len(set(d['id'] for d in diferencias if d['tipo']=='DIFF_CAMPO'))}")
print(f"  Empleados faltantes:    {len(ids_solo_backup)}")

if diferencias:
    print(f"\nDiferencias encontradas:")
    for d in diferencias[:30]:
        print(f"  ID={d['id']} [{d['tipo']}] campo={d['campo']}")
        if d['tipo'] == 'DIFF_CAMPO':
            print(f"    Respaldo: {d['backup']}")
            print(f"    Cloud:    {d['cloud']}")
else:
    print("\n  TODOS LOS CAMPOS COINCIDEN EXACTAMENTE con el respaldo.")

# =========================================================
# PASO 3: Insertar empleados faltantes desde respaldo
# =========================================================
if ids_solo_backup:
    print(f"\n{SEPARATOR}")
    print(f"[ INSERTANDO {len(ids_solo_backup)} EMPLEADOS FALTANTES DESDE RESPALDO ]")
    print(SEPARATOR)

    cols_emp = backup_cols
    cols_str = ', '.join(f'"{c}"' for c in cols_emp)
    inserted_ok = 0

    for emp_id in ids_solo_backup:
        emp = backup_by_id[str(emp_id)]
        args = []
        placeholders = []
        for c in cols_emp:
            v = emp.get(c)
            if v is None:
                placeholders.append('NULL')
            else:
                placeholders.append('?')
                args.append({"type": "text", "value": str(v)})

        res = post([
            {"type": "execute", "stmt": {"sql": "PRAGMA foreign_keys=OFF"}},
            {"type": "execute", "stmt": {
                "sql": f"INSERT OR REPLACE INTO empleados ({cols_str}) VALUES ({', '.join(placeholders)})",
                "args": args
            }}
        ])
        ok_results = [x for x in res['results'] if x['type'] == 'ok']
        err_results = [x for x in res['results'] if x['type'] == 'error']
        if len(ok_results) >= 2:
            inserted_ok += 1
            print(f"  ID={emp_id} {emp['nombre']} {emp['apellido_paterno']}: INSERTADO OK")
        else:
            msg = err_results[0]['error']['message'] if err_results else 'unknown'
            print(f"  ID={emp_id}: ERROR - {msg}")

    print(f"\n  Total insertados: {inserted_ok}/{len(ids_solo_backup)}")

    # REINDEX tras insertar
    res = post([{"type": "execute", "stmt": {"sql": "REINDEX empleados"}}])
    ri_status = res['results'][0]['type']
    print(f"  REINDEX empleados: {ri_status}")

# =========================================================
# PASO 4: Estado final
# =========================================================
print(f"\n{SEPARATOR}")
print("[ ESTADO FINAL ]")
print(SEPARATOR)

_, cnt = q("SELECT COUNT(*) as c FROM empleados")
total_emp = int(cnt[0]['c'])
print(f"Empleados en cloud: {total_emp}/78")

_, cnt = q("SELECT COUNT(*) as c FROM empleados WHERE activo=1")
print(f"Empleados activos:  {cnt[0]['c']}")

# Verificar todas las tablas principales
checks = [
    ("empleados",         "SELECT COUNT(*) as c FROM empleados"),
    ("asistencias",       "SELECT COUNT(*) as c FROM asistencias"),
    ("historial_areas",   "SELECT COUNT(*) as c FROM historial_areas"),
    ("turno_dias",        "SELECT COUNT(*) as c FROM turno_dias"),
    ("turnos",            "SELECT COUNT(*) as c FROM turnos"),
    ("horas_extras",      "SELECT COUNT(*) as c FROM horas_extras"),
    ("cargos",            "SELECT COUNT(*) as c FROM cargos"),
    ("areas",             "SELECT COUNT(*) as c FROM areas"),
    ("bonos",             "SELECT COUNT(*) as c FROM bonos"),
    ("feriados",          "SELECT COUNT(*) as c FROM feriados"),
    ("usuarios",          "SELECT COUNT(*) as c FROM usuarios"),
]
print(f"\nConteo de tablas principales:")
for name, sql in checks:
    try:
        _, r = q(sql)
        print(f"  {name:<25} {r[0]['c']:>6} filas")
    except Exception as e:
        print(f"  {name:<25} ERROR: {e}")

print(f"\n{SEPARATOR}")
print("AUDITORIA COMPLETADA")
print(SEPARATOR)
