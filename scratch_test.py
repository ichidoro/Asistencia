import asyncio
from backend.core.database import Database
from backend.repositories.asistencia import AsistenciaRepository
from backend.services.asistencia_service import AsistenciaService

async def test():
    db = Database()
    await db.connect()
    repo = AsistenciaRepository(db)
    service = AsistenciaService(repo)

    print("Reprocesando todos los empleados de seguridad...")
    for eid in [1, 2, 3]:
        result = await service.reprocesar_periodo_empleado(
            empleado_id=eid,
            fecha_inicio="2026-04-26",
            fecha_fin="2026-05-11",
            force=True,
        )
        print(f"  Emp {eid}: {result}")

    print("\n=== HORAS EXTRAS DESPUES DEL REPROCESO ===")
    he = await db.fetch_all('SELECT empleado_id, fecha, minutos_bruto, estado FROM horas_extras WHERE empleado_id IN (1,2,3) ORDER BY empleado_id, fecha')
    for h in he:
        d = dict(h)
        print(f"  Emp {d['empleado_id']} {d['fecha']}: {d['minutos_bruto']} min ({d['minutos_bruto']/60:.1f}h) - {d['estado']}")

    print("\n=== ASISTENCIAS FINALES ===")
    for eid in [1, 2, 3]:
        asist = await db.fetch_all(
            "SELECT fecha, estado, horas_trabajadas, minutos_extra_bruto, num_semana_ganadora FROM asistencias WHERE empleado_id=? AND fecha >= '2026-04-26' ORDER BY fecha",
            (eid,)
        )
        print(f"\n  Emp {eid}:")
        for a in asist:
            d = dict(a)
            he_str = f" HE={d['minutos_extra_bruto']}min" if d.get('minutos_extra_bruto') else ""
            print(f"    {d['fecha']}: {str(d['estado']):20s} ht={d['horas_trabajadas']} sem={d['num_semana_ganadora']}{he_str}")

    await db.disconnect()

asyncio.run(test())
