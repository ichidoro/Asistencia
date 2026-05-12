import asyncio
from backend.core.database import Database

async def audit():
    db = Database()
    await db.connect()
    
    # Columnas de asignacion_turnos
    print('=== COLUMNAS asignacion_turnos ===')
    cols = await db.fetch_all('PRAGMA table_info(asignacion_turnos)')
    print([dict(c)['name'] for c in cols])

    print()
    print('=== ASIGNACIONES SEGURIDAD ===')
    asigs = await db.fetch_all("""
        SELECT a.*, e.nombre, t.tipo_programacion
        FROM asignacion_turnos a
        JOIN empleados e ON a.empleado_id = e.id
        JOIN turnos t ON a.turno_id = t.id
        WHERE a.turno_id=1
        ORDER BY a.empleado_id, a.fecha_inicio DESC
    """)
    for a in asigs:
        d = dict(a)
        print(f"  Emp {d['empleado_id']} {d['nombre']}: turno={d['turno_id']} inicio={d['fecha_inicio']} fin={d.get('fecha_fin')}")

    print()
    print('=== LOGS RAW MAYO ===')
    emps_ids = list(set([a['empleado_id'] for a in asigs]))
    for eid in emps_ids:
        emp_nombre = next((a['nombre'] for a in asigs if a['empleado_id'] == eid), str(eid))
        logs = await db.fetch_all(
            "SELECT id, fecha_hora, tipo FROM logs_raw WHERE empleado_id=? AND fecha_hora >= '2026-04-25' AND fecha_hora <= '2026-05-12' ORDER BY fecha_hora",
            (eid,)
        )
        print(f"  Emp {eid} ({emp_nombre}):")
        for l in logs:
            print(f"    id={l['id']} {l['fecha_hora']} - {l['tipo']}")

    print()
    print('=== ASISTENCIAS GUARDADAS ABR25-MAY12 ===')
    print('=== (columnas de asistencias) ===')
    cols2 = await db.fetch_all('PRAGMA table_info(asistencias)')
    print([dict(c)['name'] for c in cols2])
    
    for eid in emps_ids:
        emp_nombre = next((a['nombre'] for a in asigs if a['empleado_id'] == eid), str(eid))
        asist = await db.fetch_all(
            """SELECT fecha, estado, hora_entrada_real, hora_salida_real, 
               horas_trabajadas, horas_extras, num_semana_ganadora, marcas_consumidas_ids
               FROM asistencias WHERE empleado_id=? AND fecha >= '2026-04-25' AND fecha <= '2026-05-12' 
               ORDER BY fecha""",
            (eid,)
        )
        print(f"\n  Emp {eid} ({emp_nombre}):")
        for a in asist:
            d = dict(a)
            consumidas = d.get('marcas_consumidas_ids') or '[]'
            print(f"    {d['fecha']}: {str(d['estado']):12s} entra={d['hora_entrada_real']} sale={d['hora_salida_real']} ht={d['horas_trabajadas']} he={d['horas_extras']} sem={d['num_semana_ganadora']} cons={consumidas}")
    
    await db.disconnect()

asyncio.run(audit())
