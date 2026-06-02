import sys
import os
import asyncio

sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\danie\Proyectos_Python\Asistencia\.env")

from backend.core.database import db

async def run_rebuild():
    print("Conectando a Turso Cloud...")
    await db.connect()

    # 1. Back up valid asistencias
    print("1. Cargando asistencias validas (>= 2026-04-26)...")
    asist_rows = await db.fetch_all("SELECT * FROM asistencias WHERE fecha >= '2026-04-26'")
    print(f"   -> {len(asist_rows)} registros validos cargados.")

    # 2. Back up valid horas_extras
    print("2. Cargando horas_extras validas (>= 2026-04-26)...")
    he_rows = await db.fetch_all("SELECT * FROM horas_extras WHERE fecha >= '2026-04-26'")
    print(f"   -> {len(he_rows)} registros validos cargados.")

    # 3. Clean logs_raw
    print("3. Eliminando marcaciones crudas (logs_raw) anteriores al 2026-04-26...")
    q_logs = "DELETE FROM logs_raw WHERE SUBSTR(fecha_hora, 1, 10) < '2026-04-26'"
    await db.execute(q_logs)
    print("   -> Marcaciones crudas eliminadas.")

    # 4. Clean asignacion_turnos
    print("4. Eliminando asignaciones de turnos anteriores al 2026-04-26...")
    q_asig = "DELETE FROM asignacion_turnos WHERE fecha_inicio < '2026-04-26'"
    await db.execute(q_asig)
    print("   -> Asignaciones de turnos eliminadas.")

    # 5. Drop tables
    print("5. Eliminando tablas asistencias y horas_extras...")
    await db.execute("DROP TABLE IF EXISTS asistencias")
    await db.execute("DROP TABLE IF EXISTS horas_extras")
    print("   -> Tablas eliminadas.")

    # 6. Recreate horas_extras
    print("6. Recreando tabla horas_extras...")
    create_he_sql = """
    CREATE TABLE horas_extras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empleado_id INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        minutos_bruto REAL DEFAULT 0,
        minutos_autorizados REAL DEFAULT 0,
        estado TEXT DEFAULT 'PENDIENTE' CHECK(estado IN ('PENDIENTE','APROBADO','RECHAZADO')),
        origen TEXT DEFAULT 'SISTEMA',
        comentario TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        minutos_compensados REAL DEFAULT 0,
        FOREIGN KEY (empleado_id) REFERENCES empleados(id) ON DELETE CASCADE,
        UNIQUE(empleado_id, fecha)
    )
    """
    await db.execute(create_he_sql)
    
    # Recreate indices for horas_extras
    await db.execute("CREATE INDEX idx_he_empleado ON horas_extras (empleado_id)")
    await db.execute("CREATE INDEX idx_he_fecha ON horas_extras (fecha)")
    await db.execute("CREATE INDEX idx_he_estado ON horas_extras (estado)")
    await db.execute("CREATE INDEX idx_he_emp_fecha ON horas_extras (empleado_id, fecha)")
    print("   -> Tabla horas_extras y sus indices creados.")

    # 7. Recreate asistencias
    print("7. Recreando tabla asistencias...")
    create_asist_sql = """
    CREATE TABLE asistencias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empleado_id INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        turno_asignado_id INTEGER,
        hora_entrada_teorica TEXT,
        hora_salida_teorica TEXT,
        horas_teoricas REAL DEFAULT 0,
        hora_entrada_real TEXT,
        hora_salida_real TEXT,
        minutos_atraso INTEGER DEFAULT 0,
        minutos_colacion INTEGER DEFAULT 0,
        horas_trabajadas REAL DEFAULT 0,
        estado TEXT DEFAULT 'PENDIENTE',
        observaciones TEXT,
        hora_inicio TEXT,
        hora_fin TEXT,
        origen TEXT DEFAULT 'SISTEMA',
        detalle_tramos TEXT,
        minutos_deuda INTEGER DEFAULT 0,
        minutos_extra_bruto INTEGER DEFAULT 0,
        minutos_salida_adelantada INTEGER DEFAULT 0,
        updated_at TEXT DEFAULT (datetime('now')),
        minutos_colacion_real INTEGER DEFAULT 0,
        minutos_exceso_colacion INTEGER DEFAULT 0,
        minutos_colacion_auto INTEGER DEFAULT 0,
        minutos_permiso_personal_deuda INTEGER DEFAULT 0,
        hora_salida_colacion TEXT,
        hora_entrada_colacion TEXT,
        hora_inicio_permiso TEXT,
        hora_termino_permiso TEXT,
        minutos_permisos_detectados INTEGER DEFAULT 0,
        tiene_atraso INTEGER NOT NULL DEFAULT 0,
        tiene_salida_adelantada INTEGER NOT NULL DEFAULT 0,
        tiene_permiso INTEGER NOT NULL DEFAULT 0,
        num_semana_ganadora INTEGER DEFAULT 1,
        marcas_consumidas_ids TEXT DEFAULT '[]',
        deuda_condonada INTEGER DEFAULT 0,
        FOREIGN KEY (empleado_id) REFERENCES empleados (id)
    )
    """
    await db.execute(create_asist_sql)
    
    # Recreate indices for asistencias
    await db.execute("CREATE INDEX idx_asis_empleado_fecha ON asistencias (empleado_id, fecha)")
    await db.execute("CREATE INDEX idx_asis_fecha ON asistencias (fecha)")
    await db.execute("CREATE INDEX idx_asis_estado ON asistencias (estado)")
    await db.execute("CREATE UNIQUE INDEX idx_asistencias_emp_fecha ON asistencias (empleado_id, fecha)")
    print("   -> Tabla asistencias y sus indices creados.")

    # 8. Restore valid horas_extras
    print("8. Restaurando registros validos en horas_extras...")
    he_fields = [
        'empleado_id', 'fecha', 'minutos_bruto', 'minutos_autorizados',
        'estado', 'origen', 'comentario', 'created_at', 'updated_at',
        'minutos_compensados'
    ]
    # Insert in batches
    for r in he_rows:
        vals = tuple(r.get(f) for f in he_fields)
        q = f"INSERT INTO horas_extras ({', '.join(he_fields)}) VALUES ({', '.join('?' for _ in he_fields)})"
        await db.execute(q, vals)
    print(f"   -> {len(he_rows)} registros restaurados en horas_extras.")

    # 9. Restore valid asistencias
    print("9. Restaurando registros validos en asistencias...")
    asist_fields = [
        'empleado_id', 'fecha', 'turno_asignado_id', 'hora_entrada_teorica',
        'hora_salida_teorica', 'horas_teoricas', 'hora_entrada_real',
        'hora_salida_real', 'minutos_atraso', 'minutos_colacion',
        'horas_trabajadas', 'estado', 'observaciones', 'hora_inicio',
        'hora_fin', 'origen', 'detalle_tramos', 'minutos_deuda',
        'minutos_extra_bruto', 'minutos_salida_adelantada', 'updated_at',
        'minutos_colacion_real', 'minutos_exceso_colacion', 'minutos_colacion_auto',
        'minutos_permiso_personal_deuda', 'hora_salida_colacion', 'hora_entrada_colacion',
        'hora_inicio_permiso', 'hora_termino_permiso', 'minutos_permisos_detectados',
        'tiene_atraso', 'tiene_salida_adelantada', 'tiene_permiso',
        'num_semana_ganadora', 'marcas_consumidas_ids', 'deuda_condonada'
    ]
    for r in asist_rows:
        vals = tuple(r.get(f) for f in asist_fields)
        q = f"INSERT INTO asistencias ({', '.join(asist_fields)}) VALUES ({', '.join('?' for _ in asist_fields)})"
        await db.execute(q, vals)
    print(f"   -> {len(asist_rows)} registros restaurados en asistencias.")

    # 10. Verify integrity again
    print("\n10. Ejecutando PRAGMA integrity_check final...")
    check_rows = await db.fetch_all("PRAGMA integrity_check")
    healthy = True
    for r in check_rows:
        val = r.get('integrity_check') or str(r)
        print(f"   -> Result: {val}")
        if val != 'ok':
            healthy = False
            
    if healthy:
        print("\nSUCCESS: Base de datos Turso Cloud 100% limpia y saludable!")
    else:
        print("\nWARNING: integrity_check reporto algunos inconvenientes. Revisar mas arriba.")

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(run_rebuild())
