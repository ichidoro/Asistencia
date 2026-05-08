
import sqlite3, json
from datetime import datetime, timedelta, date

DB = 'data/local_db/asistencia_local.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 1. Tablas
print('=== TABLAS ===')
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print(tables)

# 2. Empleados activos
print()
print('=== EMPLEADOS ACTIVOS (primeros 10) ===')
cur.execute('SELECT id, nombre, apellido_paterno, rut, area FROM empleados WHERE activo=1 LIMIT 10')
emps = cur.fetchall()
for e in emps:
    print(f'  ID={e["id"]} RUT={e["rut"]} {e["nombre"]} {e["apellido_paterno"]} AREA={e["area"]}')
total_emps = len(emps)
cur.execute('SELECT COUNT(*) FROM empleados WHERE activo=1')
total_emps = cur.fetchone()[0]
print(f'  ... Total empleados activos: {total_emps}')

# 3. logs_raw en el rango
print()
print('=== LOGS_RAW en 2026-03-26 a 2026-04-26 ===')
cur.execute("""
    SELECT COUNT(*) as cnt, MIN(fecha_hora) as min_fh, MAX(fecha_hora) as max_fh
    FROM logs_raw
    WHERE fecha_hora >= '2026-03-26' AND fecha_hora <= '2026-04-26 23:59:59'
""")
row = cur.fetchone()
print(f'  Total={row["cnt"]}  Min={row["min_fh"]}  Max={row["max_fh"]}')

# 3b. logs_raw por mes
cur.execute("""
    SELECT substr(fecha_hora,1,7) as mes, COUNT(*) as cnt
    FROM logs_raw
    GROUP BY mes
    ORDER BY mes DESC
    LIMIT 10
""")
print('  Por mes (ultimos 10):')
for r in cur.fetchall():
    print(f'    {r["mes"]}: {r["cnt"]} logs')

# 4. asistencias en ese rango
print()
print('=== ASISTENCIAS en 2026-03-26 a 2026-04-26 ===')
cur.execute("""
    SELECT COUNT(*) as cnt, MIN(fecha) as min_f, MAX(fecha) as max_f
    FROM asistencias
    WHERE fecha >= '2026-03-26' AND fecha <= '2026-04-26'
""")
row = cur.fetchone()
print(f'  Total={row["cnt"]}  Min={row["min_f"]}  Max={row["max_f"]}')

# 4b. Sample de asistencias en el rango
cur.execute("""
    SELECT a.empleado_id, e.nombre, e.area, a.fecha, a.estado, a.hora_entrada_real
    FROM asistencias a
    JOIN empleados e ON e.id = a.empleado_id
    WHERE a.fecha >= '2026-03-26' AND a.fecha <= '2026-04-26'
    LIMIT 10
""")
rows = cur.fetchall()
print('  Sample (max 10):')
for r in rows:
    print(f'    EmpID={r["empleado_id"]} {r["nombre"]} ({r["area"]}) | {r["fecha"]} estado={r["estado"]} entrada={r["hora_entrada_real"]}')

# 5. sync_logs
print()
print('=== SYNC_LOGS (ultimos 5) ===')
try:
    cur.execute('SELECT id, tipo, fecha_inicio, fecha_fin, estado, marcaciones_nuevas FROM sync_logs ORDER BY id DESC LIMIT 5')
    for r in cur.fetchall():
        print(f'  ID={r["id"]} tipo={r["tipo"]} {r["fecha_inicio"]}..{r["fecha_fin"]} estado={r["estado"]} nuevas={r["marcaciones_nuevas"]}')
except Exception as e:
    print(f'  Error: {e}')
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%sync%'")
    print('  Tablas sync:', [r[0] for r in cur.fetchall()])

conn.close()
print()
print('=== FIN INSPECCION ===')
