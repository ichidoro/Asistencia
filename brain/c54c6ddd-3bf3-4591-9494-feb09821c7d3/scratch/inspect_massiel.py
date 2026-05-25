import sqlite3
import sys

db_path = r"c:\Users\danie\Proyectos_Python\Asistencia\data\local_db\asistencia_local.db"

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Obtener asistencia de Massiel (ID 10)
cursor.execute("""
    SELECT fecha, estado, horas_trabajadas, minutos_deuda, minutos_extra_bruto, observaciones 
    FROM asistencias 
    WHERE empleado_id = 10 AND fecha BETWEEN '2026-05-01' AND '2026-05-25' 
    ORDER BY fecha
""")

print("=== REGISTROS DE ASISTENCIA PARA MASSIEL ROXANA (01-05-2026 al 25-05-2026) ===")
rows = cursor.fetchall()
for r in rows:
    print(f"Fecha: {r['fecha']} | Estado: {r['estado']} | Horas Trab: {r['horas_trabajadas']:.2f} | Deuda: {r['minutos_deuda']} min | Extras: {r['minutos_extra_bruto']} min | Obs: {r['observaciones']}")

conn.close()
