import sqlite3
import json

db_path = r"c:\Users\danie\Proyectos_Python\Asistencia\data\local_db\asistencia_local.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Find employee
emp_row = cursor.execute(
    "SELECT id, nombre, rut, cargo, tipo_contrato, fecha_ingreso FROM empleados WHERE nombre LIKE '%LUIS%EMILIANO%' OR nombre LIKE '%DURAN%SERRANO%'"
).fetchone()

if not emp_row:
    print("Employee not found! First 10 employees:")
    for e in cursor.execute("SELECT id, nombre FROM empleados LIMIT 10").fetchall():
        print(dict(e))
    conn.close()
    exit()

emp_id = emp_row['id']
print(f"Employee found: ID={emp_id}, Name={emp_row['nombre']}, Cargo={emp_row['cargo']}, Contrato={emp_row['tipo_contrato']}")

# Get calculated attendances with INASISTENCIA/FALTA for this employee in May 2026
print("\n--- Inasistencias / Faltas in May 2026 ---")
asis_list = cursor.execute(
    "SELECT fecha, estado, observaciones FROM asistencias WHERE empleado_id = ? AND fecha LIKE '2026-05-%' AND estado IN ('INASISTENCIA', 'FALTA') ORDER BY fecha",
    (emp_id,)
).fetchall()
for a in asis_list:
    print(dict(a))

# Get all calculate attendances for April 2026
print("\n--- All Asistencias for Employee in April 2026 ---")
all_asis = cursor.execute(
    "SELECT fecha, estado, horas_teoricas, observaciones FROM asistencias WHERE empleado_id = ? AND fecha LIKE '2026-04-%' ORDER BY fecha",
    (emp_id,)
).fetchall()
for a in all_asis:
    print(dict(a))

# Print active bonos
print("\n--- Active Bonos and Rules ---")
bonos = cursor.execute("SELECT * FROM turnos").fetchall() # Wait, bonos are in the configs, let's list tables first to check where bonos are
tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables in DB:", [t['name'] for t in tables])

# Check bonos, bono_reglas, bono_asignaciones
if 'bonos' in [t['name'] for t in tables]:
    print("\n--- Bonos Table Content ---")
    for b in cursor.execute("SELECT * FROM bonos").fetchall():
        print(dict(b))
    print("\n--- Bono Reglas Content ---")
    for r in cursor.execute("SELECT * FROM bono_reglas").fetchall():
        print(dict(r))

conn.close()
