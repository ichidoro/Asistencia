import sqlite3

db_path = r"c:\Users\danie\Proyectos_Python\Asistencia\data\local_db\asistencia_local.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get the active period dates
cursor.execute("SELECT fecha_inicio, fecha_fin FROM periodos_rrhh WHERE activo = 1")
periodo = cursor.fetchone()
p_ini = periodo['fecha_inicio']
p_fin = periodo['fecha_fin']

# Query all attendance and overtime details day by day
query = """
    SELECT 
        a.fecha,
        t.nombre as turno,
        a.hora_entrada_teorica,
        a.hora_salida_teorica,
        a.hora_entrada_real,
        a.hora_salida_real,
        a.horas_trabajadas,
        a.minutos_extra_bruto,
        he.minutos_autorizados as minutos_extra_autorizados,
        he.estado as estado_he,
        he.comentario
    FROM asistencias a
    LEFT JOIN turnos t ON a.turno_asignado_id = t.id
    LEFT JOIN horas_extras he ON he.empleado_id = a.empleado_id AND he.fecha = a.fecha
    WHERE a.empleado_id = 80
      AND a.fecha BETWEEN ? AND ?
    ORDER BY a.fecha
"""

cursor.execute(query, (p_ini, p_fin))
rows = cursor.fetchall()

print(f"==========================================================================")
print(f"DATOS CIENTÍFICOS DÍA A DÍA: BADILLA MAXIMILIANO ({p_ini} al {p_fin})")
print(f"==========================================================================")

total_bruto = 0
total_aprobado = 0

for r in rows:
    fecha = r['fecha']
    turno = r['turno'] or "LIBRE"
    teorico = f"{r['hora_entrada_teorica'] or '--'} a {r['hora_salida_teorica'] or '--'}"
    real = f"{r['hora_entrada_real'] or '--'} a {r['hora_salida_real'] or '--'}"
    trabajado = r['horas_trabajadas'] or 0.0
    bruto_he = r['minutos_extra_bruto'] or 0
    aprobado_he = r['minutos_extra_autorizados'] or 0
    estado = r['estado_he'] or "SIN_REGISTRO"
    comentario = r['comentario'] or ""

    total_bruto += bruto_he
    total_aprobado += aprobado_he

    print(f"Fecha: {fecha} | Turno: {turno} ({teorico})")
    print(f"       Marcas: {real} | Trab: {trabajado:.2f}h")
    print(f"       HE Bruta (asist): {bruto_he} min ({bruto_he/60:.2f}h)")
    print(f"       HE Autorizada (he): {aprobado_he} min ({aprobado_he/60:.2f}h) | Estado: {estado} | Com: {comentario}")
    print(f"--------------------------------------------------------------------------")

print(f"TOTAL BRUTO PERIODO: {total_bruto} min ({total_bruto/60:.2f}h)")
print(f"TOTAL APROBADO PERIODO: {total_aprobado} min ({total_aprobado/60:.2f}h)")
print(f"==========================================================================")

conn.close()
