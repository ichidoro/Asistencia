import asyncio
from backend.core.database import Database

async def test():
    db = Database()
    await db.connect()
    
    asi = await db.fetch_all("SELECT * FROM logs_raw WHERE empleado_id=3 AND fecha_hora LIKE '2026-05-%' ORDER BY fecha_hora ASC")
    for a in asi:
        d = dict(a)
        print(f"{d['fecha_hora']} - {d['tipo']}")
    
    await db.disconnect()

asyncio.run(test())
