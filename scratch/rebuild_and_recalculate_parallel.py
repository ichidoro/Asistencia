import sys
import os
import asyncio
from datetime import datetime

sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\danie\Proyectos_Python\Asistencia\.env")

from backend.core.database import db
from backend.services.asistencia_service import AsistenciaService

async def process_employee_with_sem(sem, asist_service, idx, total, emp_id, emp_name):
    async with sem:
        print(f"   [{idx}/{total}] Iniciando reprocesamiento paralelo de {emp_name} (ID: {emp_id})...", flush=True)
        try:
            # force=True forces calculation even if no marks.
            await asist_service.reprocesar_periodo_empleado(
                empleado_id=emp_id,
                fecha_inicio="2026-04-26",
                fecha_fin="2026-06-02",
                force=True
            )
            print(f"   [{idx}/{total}] Completado {emp_name} (ID: {emp_id}).", flush=True)
        except Exception as e_recalc:
            print(f"      -> ERROR al procesar {emp_name}: {e_recalc}", flush=True)

async def rebuild_and_recalc_parallel():
    print("Conectando a Turso Cloud...", flush=True)
    await db.connect()
    
    # 1. Recreate horas_extras table
    print("1. Recreando tabla horas_extras...", flush=True)
    await db.execute("DROP TABLE IF EXISTS horas_extras")
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
    await db.execute("CREATE INDEX idx_he_empleado ON horas_extras (empleado_id)")
    await db.execute("CREATE INDEX idx_he_fecha ON horas_extras (fecha)")
    await db.execute("CREATE INDEX idx_he_estado ON horas_extras (estado)")
    await db.execute("CREATE INDEX idx_he_emp_fecha ON horas_extras (empleado_id, fecha)")
    print("   -> Tabla horas_extras y indices creados.", flush=True)

    # 2. Recreate asistencias table
    print("2. Recreando tabla asistencias...", flush=True)
    await db.execute("DROP TABLE IF EXISTS asistencias")
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
    await db.execute("CREATE INDEX idx_asis_empleado_fecha ON asistencias (empleado_id, fecha)")
    await db.execute("CREATE INDEX idx_asis_fecha ON asistencias (fecha)")
    await db.execute("CREATE INDEX idx_asis_estado ON asistencias (estado)")
    await db.execute("CREATE UNIQUE INDEX idx_asistencias_emp_fecha ON asistencias (empleado_id, fecha)")
    print("   -> Tabla asistencias y indices creados.", flush=True)

    # 3. Clean logs_raw
    print("3. Eliminando marcaciones crudas (logs_raw) anteriores al 2026-04-26...", flush=True)
    await db.execute("DELETE FROM logs_raw WHERE SUBSTR(fecha_hora, 1, 10) < '2026-04-26'")
    print("   -> Marcaciones crudas eliminadas.", flush=True)

    # 4. Clean asignacion_turnos
    print("4. Eliminando asignaciones de turnos anteriores al 2026-04-26...", flush=True)
    await db.execute("DELETE FROM asignacion_turnos WHERE fecha_inicio < '2026-04-26'")
    print("   -> Asignaciones de turnos eliminadas.", flush=True)

    # 5. Get all employees and recalculate attendance
    print("5. Obteniendo empleados para reprocesamiento...", flush=True)
    employees = await db.fetch_all("SELECT id, nombre FROM empleados")
    total_emp = len(employees)
    print(f"   -> {total_emp} empleados encontrados.", flush=True)

    from backend.repositories.asistencia import AsistenciaRepository
    asist_repo = AsistenciaRepository(db)
    asist_service = AsistenciaService(asist_repo)
    
    # Usamos un semáforo de 8 para limitar la concurrencia remota a Turso
    sem = asyncio.Semaphore(8)
    
    print("6. Iniciando reprocesamiento de asistencia paralelo (sem=8) desde 2026-04-26 hasta 2026-06-02...", flush=True)
    tasks = []
    for idx, emp in enumerate(employees, 1):
        emp_id = emp['id']
        emp_name = emp['nombre']
        tasks.append(process_employee_with_sem(sem, asist_service, idx, total_emp, emp_id, emp_name))
        
    await asyncio.gather(*tasks)
    print("   -> Reprocesamiento paralelo finalizado.", flush=True)

    # 7. Clean up corrupted tables to free database space if possible
    print("7. Eliminando tablas corruptas obsoletas...", flush=True)
    try:
        await db.execute("DROP TABLE IF EXISTS asistencias_corrupt")
        print("   -> Tabla asistencias_corrupt eliminada.", flush=True)
    except Exception as e:
        print(f"   -> No se pudo eliminar asistencias_corrupt (no critico): {e}", flush=True)

    try:
        await db.execute("DROP TABLE IF EXISTS horas_extras_corrupt")
        print("   -> Tabla horas_extras_corrupt eliminada.", flush=True)
    except Exception as e:
        print(f"   -> No se pudo eliminar horas_extras_corrupt (no critico): {e}", flush=True)

    print("8. Ejecutando PRAGMA integrity_check final...", flush=True)
    check_rows = await db.fetch_all("PRAGMA integrity_check")
    healthy = True
    for r in check_rows:
        val = r.get('integrity_check') or str(r)
        print(f"   -> Result: {val}", flush=True)
        if val != 'ok':
            healthy = False

    if healthy:
        print("\nSUCCESS: Base de datos Turso Cloud reconstruida, limpia y saludable!", flush=True)
    else:
        print("\nWARNING: integrity_check reporto inconvenientes.", flush=True)

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(rebuild_and_recalc_parallel())
