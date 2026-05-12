import asyncio
from backend.services.asistencia_service import AsistenciaService
from backend.repositories.asistencia import AsistenciaRepository
from backend.core.database import get_db

async def run():
    db = await get_db()
    
    # Julian es el empleado 3
    res3 = await db.fetch_all("SELECT fecha, num_semana_ganadora, estado, horas_trabajadas, observaciones FROM asistencias WHERE empleado_id=3 AND fecha >= '2026-04-26' ORDER BY fecha ASC")
    print('=== JULIAN (EMP 3) ===')
    for r in res3:
        print(dict(r))

    emps = await db.fetch_all("SELECT id, nombres, apellidos FROM empleados WHERE area = 'SEGURIDAD'")
    for emp in emps:
        print(dict(emp))
        
    # Get Eduardo
    # Get Rudecindo

asyncio.run(run())
