import sqlite3

db_path = r"c:\Users\danie\Proyectos_Python\Asistencia\data\local_db\asistencia_local.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Restore the 2026-05-05 overtime values to the original 67.86666666666656 minutes
cursor.execute("""
    UPDATE horas_extras
    SET minutos_bruto = 67.86666666666656,
        minutos_autorizados = 67.86666666666656
    WHERE empleado_id = 80 AND fecha = '2026-05-05'
""")
conn.commit()
print("Successfully restored 2026-05-05 overtime to 67.87 minutes!")
conn.close()
