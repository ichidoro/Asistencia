# -*- coding: utf-8 -*-
"""
auditoria_profunda.py
─────────────────────
Auditoría completa y directa: Turso vs Local SQLite
  - Diferencias de tablas (presencia)
  - Diferencias de columnas (nombre, tipo, DEFAULT, NOT NULL, PK)
  - Diferencias de conteos de filas
  - Diferencias de datos (fila a fila, columna a columna)
  - Integridad de la limpieza (datos huérfanos)
"""
import sys, os, sqlite3
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import libsql

TURSO_URL   = "libsql://asistenciaaguacol-ichidoro.aws-us-east-1.turso.io"
TURSO_TOKEN = (
    "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9."
    "eyJhIjoicnciLCJpYXQiOjE3Nzg0NjQ2MjEsImlkIjoiMDE5ZTE0YzAt"
    "NjYwMS03YzUyLWFhZjMtMzk5ZTFlNjM5ZWEyIiwicmlkIjoiODZmMjky"
    "YTUtMjMzZC00ZmYyLThmN2ItMmJkNTQ2MmY1MDYwIn0."
    "HyHa_-uEPS_2YswqpWrSvX3CyqwkB5bj-uGOA549ug68cPgVK5TXBSMMjo1e0NJWwMQa8deBHL5UREuJKKyACA"
)
LOCAL_DB = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'data', 'local_db', 'asistencia_local.db')
)

W = 70
SEP  = "=" * W
SEP2 = "-" * W

def banner(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

# ── Conexiones ───────────────────────────────────────────────────────────────
print("\nConectando a Turso...", end=" ")
try:
    turso = libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)
    print("OK")
except Exception as e:
    print(f"FALLO: {e}")
    sys.exit(1)

print("Conectando a Local...", end=" ")
try:
    local = sqlite3.connect(LOCAL_DB)
    local.row_factory = sqlite3.Row
    print("OK\n")
except Exception as e:
    print(f"FALLO: {e}")
    sys.exit(1)

def lq(sql, params=()):
    cur = local.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = [dict(zip(cols, list(r))) for r in cur.fetchall()]
    return cols, rows

def tq(sql, params=()):
    cur = turso.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = [dict(zip(cols, list(r))) for r in cur.fetchall()]
    return cols, rows

SQL_TABLES = ("SELECT name FROM sqlite_master "
              "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")

_, l_tbl = lq(SQL_TABLES)
_, t_tbl = tq(SQL_TABLES)
local_tables = {r['name'] for r in l_tbl}
turso_tables = {r['name'] for r in t_tbl}
common       = local_tables & turso_tables
only_local   = local_tables - turso_tables
only_turso   = turso_tables - local_tables

# ════════════════════════════════════════════════════════════════════════════
# 1. TABLAS
# ════════════════════════════════════════════════════════════════════════════
banner("1. TABLAS")
print(f"  Local : {len(local_tables)} tablas")
print(f"  Turso : {len(turso_tables)} tablas")
print(f"  Común : {len(common)} tablas")
if only_local:
    print(f"\n  ⚠️  SOLO EN LOCAL  : {sorted(only_local)}")
if only_turso:
    print(f"\n  ⚠️  SOLO EN TURSO  : {sorted(only_turso)}")
if not only_local and not only_turso:
    print("  ✅ Mismas tablas en ambas BDs")

# ════════════════════════════════════════════════════════════════════════════
# 2. ESQUEMAS — columna a columna
# ════════════════════════════════════════════════════════════════════════════
banner("2. ESQUEMAS (columnas: nombre, tipo, notnull, default, pk)")

schema_issues = {}
for table in sorted(common):
    _, lc = lq(f"PRAGMA table_info('{table}')")
    _, tc = tq(f"PRAGMA table_info('{table}')")

    # Indexar por nombre de columna
    lc_map = {c['name']: c for c in lc}
    tc_map = {c['name']: c for c in tc}
    lc_names = set(lc_map)
    tc_names = set(tc_map)

    issues = []
    # Columnas que faltan
    for col in sorted(lc_names - tc_names):
        issues.append(f"    SOLO LOCAL : columna '{col}' (tipo={lc_map[col]['type']})")
    for col in sorted(tc_names - lc_names):
        issues.append(f"    SOLO TURSO : columna '{col}' (tipo={tc_map[col]['type']})")

    # Columnas en común pero con definición distinta
    for col in sorted(lc_names & tc_names):
        lc_def = lc_map[col]
        tc_def = tc_map[col]
        diffs = []
        # Normalizar tipos para comparar
        l_type = (lc_def['type'] or '').strip().upper()
        t_type = (tc_def['type'] or '').strip().upper()
        if l_type != t_type:
            diffs.append(f"tipo: local={l_type!r} ≠ turso={t_type!r}")
        l_nn = int(lc_def.get('notnull', 0))
        t_nn = int(tc_def.get('notnull', 0))
        if l_nn != t_nn:
            diffs.append(f"notnull: local={l_nn} ≠ turso={t_nn}")
        l_df = str(lc_def.get('dflt_value') or '').strip()
        t_df = str(tc_def.get('dflt_value') or '').strip()
        if l_df != t_df:
            diffs.append(f"default: local={l_df!r} ≠ turso={t_df!r}")
        l_pk = int(lc_def.get('pk', 0))
        t_pk = int(tc_def.get('pk', 0))
        if l_pk != t_pk:
            diffs.append(f"pk: local={l_pk} ≠ turso={t_pk}")
        if diffs:
            issues.append(f"    DIFF col '{col}': {', '.join(diffs)}")

    if issues:
        schema_issues[table] = issues
        print(f"\n  ❌ {table}:")
        for i in issues:
            print(i)

if not schema_issues:
    print("  ✅ Todos los esquemas son idénticos")

# ════════════════════════════════════════════════════════════════════════════
# 3. CONTEOS DE FILAS
# ════════════════════════════════════════════════════════════════════════════
banner("3. CONTEOS DE FILAS")
print(f"  {'TABLA':<38} {'LOCAL':>7} {'TURSO':>7}  STATUS")
print(f"  {SEP2[:38]} {'-'*7} {'-'*7}  {'-'*10}")

# Sin excepciones por diseño: todas las tablas deben ser idénticas.
SOLO_LOCAL_TABLES = set()  # Vacío

count_diffs = {}
row_counts  = {}
for table in sorted(common):
    try:
        _, lr = lq(f"SELECT COUNT(*) as c FROM '{table}'")
        _, tr = tq(f"SELECT COUNT(*) as c FROM '{table}'")
        lc_n, tc_n = lr[0]['c'], tr[0]['c']
        row_counts[table] = (lc_n, tc_n)
        if lc_n == tc_n:
            status = "OK" if lc_n == 0 else f"OK ({lc_n})"
        elif table in SOLO_LOCAL_TABLES:
            # Diferencia esperada: dato auto-generado localmente, no sincronizado a Turso
            diff = lc_n - tc_n
            status = f"INFO solo-local ({'+' if diff>0 else ''}{diff})"
        else:
            diff = lc_n - tc_n
            status = f"❌ DIFF ({'+' if diff>0 else ''}{diff})"
            count_diffs[table] = (lc_n, tc_n)
        print(f"  {table:<38} {lc_n:>7} {tc_n:>7}  {status}")
    except Exception as e:
        print(f"  {table:<38} {'ERR':>7} {'ERR':>7}  {e}")

# ════════════════════════════════════════════════════════════════════════════
# 4. DATOS FILA A FILA (tablas no vacías / con diferencias)
# ════════════════════════════════════════════════════════════════════════════
banner("4. DATOS FILA A FILA (tablas con datos o diferencias)")

def normalize(v):
    if v is None: return None
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (ValueError, TypeError):
        return v

data_diffs = {}
# Omitidas: solo tablas de alto volumen / puramente operacionales.
# feriados ahora se pushea a Turso en startup — debe estar en ambas BDs.
SKIP = {'logs_auditoria', 'sync_logs', 'logs_raw'}
MAX_ROWS = 50_000

for table in sorted(common):
    lc_n, tc_n = row_counts.get(table, (0,0))
    if max(lc_n, tc_n) == 0:
        continue
    if max(lc_n, tc_n) > MAX_ROWS:
        print(f"\n  ⏭️  {table}: demasiadas filas ({max(lc_n,tc_n)}) — omitido")
        continue
    if table in SKIP:
        continue
    try:
        _, l_rows = lq(f"SELECT * FROM '{table}' ORDER BY rowid")
        _, t_rows = tq(f"SELECT * FROM '{table}' ORDER BY rowid")
    except Exception as e:
        print(f"\n  {table}: error al leer — {e}")
        continue

    diffs = []
    for i in range(max(len(l_rows), len(t_rows))):
        if i >= len(l_rows):
            diffs.append({'tipo': 'SOLO_TURSO', 'fila': i+1, 'val': dict(t_rows[i])})
        elif i >= len(t_rows):
            diffs.append({'tipo': 'SOLO_LOCAL', 'fila': i+1, 'val': dict(l_rows[i])})
        else:
            all_cols = list(dict.fromkeys(list(l_rows[i]) + list(t_rows[i])))
            col_diffs = {}
            for col in all_cols:
                lv = normalize(l_rows[i].get(col))
                tv = normalize(t_rows[i].get(col))
                if str(lv) != str(tv):
                    col_diffs[col] = {'local': lv, 'turso': tv}
            if col_diffs:
                diffs.append({'tipo': 'DIFERENTE', 'fila': i+1, 'cols': col_diffs})

    if diffs:
        data_diffs[table] = diffs
        tipos = {}
        for d in diffs:
            tipos[d['tipo']] = tipos.get(d['tipo'], 0) + 1
        print(f"\n  ❌ {table}: {len(diffs)} diferencia(s) → {tipos}")
        # Mostrar detalle (max 10 por tabla)
        for d in diffs[:10]:
            if d['tipo'] in ('SOLO_TURSO', 'SOLO_LOCAL'):
                val_str = ', '.join(f"{k}={v!r}" for k,v in list(d['val'].items())[:6])
                print(f"      [{d['tipo']}] fila {d['fila']}: {val_str}")
            else:
                for col, vals in d['cols'].items():
                    print(f"      [DIFF] fila {d['fila']} col '{col}': local={vals['local']!r} ≠ turso={vals['turso']!r}")
        if len(diffs) > 10:
            print(f"      ... y {len(diffs)-10} diferencia(s) más")

# ════════════════════════════════════════════════════════════════════════════
# 5. VEREDICTO FINAL
# ════════════════════════════════════════════════════════════════════════════
banner("5. VEREDICTO FINAL")

problems = []
if only_local or only_turso:
    problems.append(f"Tablas faltantes: solo_local={sorted(only_local)}, solo_turso={sorted(only_turso)}")
if schema_issues:
    problems.append(f"Esquemas distintos en: {sorted(schema_issues.keys())}")
if count_diffs:
    problems.append(f"Conteos distintos en: {sorted(count_diffs.keys())}")
if data_diffs:
    problems.append(f"Datos distintos en:   {sorted(data_diffs.keys())}")

if not problems:
    print("\n  ✅ BASES DE DATOS 100% IDÉNTICAS — Turso = Local\n")
else:
    print(f"\n  ❌ DIFERENCIAS ENCONTRADAS ({len(problems)} categorías):\n")
    for p in problems:
        print(f"    • {p}")
    print()

turso.close()
local.close()
print(SEP + "\n")
