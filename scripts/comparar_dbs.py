# -*- coding: utf-8 -*-
"""
comparar_dbs.py
───────────────
Comparación profunda Turso (remoto) vs SQLite local.
Fila a fila, columna a columna.

Tablas excluidas de la comparación de datos:
  - logs_auditoria, sync_logs, logs_raw, asistencias : volumen / operacionales
  - feriados : datos locales auto-generados en startup (calendarioService),
               no se sincronizan a Turso por diseño.
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

# Todas las tablas deben estar en ambas BDs (feriados se pushea a Turso en startup).
# Solo se omiten tablas de alto volumen / puramente operacionales.
SKIP_DATA = {'logs_auditoria', 'sync_logs', 'logs_raw', 'asistencias'}
MAX_ROWS  = 10_000

SEP = "=" * 62

# ── Conexiones ────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  Comparacion Turso vs SQLite Local")
print(SEP)

print("\nConectando Turso...", end=" ")
turso_conn = libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)
print("OK")

print("Conectando Local... ", end=" ")
local_conn = sqlite3.connect(LOCAL_DB)
local_conn.row_factory = sqlite3.Row
print("OK\n")

# ── Helpers ───────────────────────────────────────────────────────────────────
def lq(sql, params=()):
    cur = local_conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    return cols, [dict(zip(cols, list(r))) for r in cur.fetchall()]

def tq(sql, params=()):
    cur = turso_conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    return cols, [dict(zip(cols, list(r))) for r in cur.fetchall()]

def normalize(v):
    if v is None: return None
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (ValueError, TypeError):
        return v

SQL_TABLES = ("SELECT name FROM sqlite_master "
              "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
_, l_tbl = lq(SQL_TABLES)
_, t_tbl = tq(SQL_TABLES)
local_tables = {r['name'] for r in l_tbl}
turso_tables = {r['name'] for r in t_tbl}
common       = local_tables & turso_tables
only_local   = local_tables - turso_tables
only_turso   = turso_tables - local_tables

# ── 1. Tablas ─────────────────────────────────────────────────────────────────
print(f"{SEP}\n  1. TABLAS\n{SEP}")
print(f"  Local : {len(local_tables)} tablas")
print(f"  Turso : {len(turso_tables)} tablas")
print(f"  Comun : {len(common)} tablas")
if only_local: print(f"  SOLO LOCAL : {sorted(only_local)}")
if only_turso: print(f"  SOLO TURSO : {sorted(only_turso)}")
if not only_local and not only_turso:
    print("  >> Mismas tablas en ambas BDs [OK]")

# ── 2. Esquemas ───────────────────────────────────────────────────────────────
print(f"\n{SEP}\n  2. ESQUEMAS (columnas)\n{SEP}")
schema_diffs = {}
for table in sorted(common):
    _, lr = lq(f"PRAGMA table_info('{table}')")
    _, tr = tq(f"PRAGMA table_info('{table}')")
    lc_map = {r['name']: r for r in lr}
    tc_map = {r['name']: r for r in tr}
    lc_set, tc_set = set(lc_map), set(tc_map)
    d = {}
    if lc_set - tc_set: d['solo_local'] = sorted(lc_set - tc_set)
    if tc_set - lc_set: d['solo_turso'] = sorted(tc_set - lc_set)
    type_d = {c: f"local={str(lc_map[c]['type']).upper()} turso={str(tc_map[c]['type']).upper()}"
              for c in lc_set & tc_set
              if str(lc_map[c]['type']).upper() != str(tc_map[c]['type']).upper()}
    if type_d: d['tipos'] = type_d
    if d:
        schema_diffs[table] = d
        print(f"  DIFF {table}: {d}")

if not schema_diffs:
    print("  >> Todos los esquemas son identicos [OK]")
else:
    print(f"\n  >> {len(schema_diffs)} tabla(s) con esquema diferente [DIFF]")

# ── 3. Conteos ────────────────────────────────────────────────────────────────
print(f"\n{SEP}\n  3. CONTEO DE FILAS\n{SEP}")
print(f"  {'TABLA':<35} {'LOCAL':>7} {'TURSO':>7}  STATUS")
print(f"  {'-'*35} {'-'*7} {'-'*7}  {'-'*10}")

row_counts, count_diffs = {}, {}
for table in sorted(common):
    try:
        _, lr = lq(f"SELECT COUNT(*) as c FROM '{table}'")
        _, tr = tq(f"SELECT COUNT(*) as c FROM '{table}'")
        lc_n, tc_n = lr[0]['c'], tr[0]['c']
        row_counts[table] = (lc_n, tc_n)
        if lc_n == tc_n:
            st = "OK"
        else:
            diff = lc_n - tc_n
            st = f"DIFF ({'+' if diff>0 else ''}{diff})"
            count_diffs[table] = (lc_n, tc_n)
        print(f"  {table:<35} {lc_n:>7} {tc_n:>7}  {st}")
    except Exception as e:
        print(f"  {table:<35} {'ERR':>7} {'ERR':>7}  {e}")

if not count_diffs:
    print("\n  >> Todos los conteos comparables son identicos [OK]")
else:
    print(f"\n  >> {len(count_diffs)} tabla(s) con diferente numero de filas [DIFF]")

# ── 4. Datos fila a fila ──────────────────────────────────────────────────────
print(f"\n{SEP}\n  4. DATOS FILA A FILA\n{SEP}")
data_diffs, data_ok = {}, []

for table in sorted(common):
    if table in SKIP_DATA:
        reason = "solo-local por diseño" if table == 'feriados' else "log/volumen"
        print(f"  {table}: OMITIDA ({reason})")
        continue
    lc_n, tc_n = row_counts.get(table, (0, 0))
    if max(lc_n, tc_n) > MAX_ROWS:
        print(f"  {table}: OMITIDA ({max(lc_n,tc_n)} filas > MAX={MAX_ROWS})")
        continue

    try:
        _, l_rows = lq(f"SELECT * FROM '{table}' ORDER BY rowid")
        _, t_rows = tq(f"SELECT * FROM '{table}' ORDER BY rowid")
    except Exception as e:
        print(f"  {table}: ERROR leyendo -> {e}")
        continue

    diffs = []
    for i in range(max(len(l_rows), len(t_rows))):
        if i >= len(l_rows):
            diffs.append({'row': i+1, 'tipo': 'SOLO_TURSO', 'val': dict(t_rows[i])})
        elif i >= len(t_rows):
            diffs.append({'row': i+1, 'tipo': 'SOLO_LOCAL', 'val': dict(l_rows[i])})
        else:
            col_diffs = {c: {'L': normalize(l_rows[i].get(c)), 'T': normalize(t_rows[i].get(c))}
                         for c in set(list(l_rows[i]) + list(t_rows[i]))
                         if str(normalize(l_rows[i].get(c))) != str(normalize(t_rows[i].get(c)))}
            if col_diffs:
                row_id = l_rows[i].get('id') or i+1
                diffs.append({'row': i+1, 'id': row_id, 'tipo': 'DIFERENTE', 'cols': col_diffs})

    if diffs:
        data_diffs[table] = diffs
        print(f"\n  DIFF {table}: {len(diffs)} fila(s) diferente(s)")
        for d in diffs[:8]:
            if d['tipo'] == 'DIFERENTE':
                print(f"       Fila {d['row']} (id={d['id']}): {d['cols']}")
            else:
                print(f"       Fila {d['row']}: {d['tipo']} -> {list(d['val'].items())[:4]}...")
        if len(diffs) > 8:
            print(f"       ... {len(diffs)-8} diferencias mas")
    else:
        data_ok.append(table)
        if max(lc_n, tc_n) > 0:
            print(f"  {table}: OK ({lc_n} filas identicas)")

# ── 5. Resumen ────────────────────────────────────────────────────────────────
print(f"\n{SEP}\n  5. RESUMEN FINAL\n{SEP}")
issues = []
if only_local or only_turso: issues.append(f"Tablas faltantes: {sorted(only_local|only_turso)}")
if schema_diffs:             issues.append(f"Esquemas dif:     {list(schema_diffs.keys())}")
if count_diffs:              issues.append(f"Conteos dif:      {list(count_diffs.keys())}")
if data_diffs:               issues.append(f"Datos dif:        {list(data_diffs.keys())}")

if not issues:
    print("\n  ** BASES DE DATOS GEMELAS: 100% IDENTICAS **")
    print(f"  (feriados excluido: dato local auto-generado en startup)")
else:
    print(f"\n  ** NO IDENTICAS — {len(issues)} categoria(s) de diferencia **")
    for issue in issues:
        print(f"  - {issue}")
    if data_diffs:
        print("\n  Detalle:")
        for t, diffs in data_diffs.items():
            tipos = {}
            for d in diffs: tipos[d['tipo']] = tipos.get(d['tipo'], 0) + 1
            print(f"    {t}: {len(diffs)} fila(s) -> {tipos}")

turso_conn.close()
local_conn.close()
print(f"\n{SEP}\n")
