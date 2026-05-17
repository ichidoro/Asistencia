import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
from backend.database.session import Database
from backend.services.asistencia_service import AsistenciaService

async def test():
    db = Database()
    await db.connect()
    svc = AsistenciaService(db)
    res = await svc.procesar_empleado_dia(2, '2026-05-16', force=True)
    print(res)
    await db.disconnect()

asyncio.run(test())
