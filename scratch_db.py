import asyncio
from backend.core.database import Database

async def test():
    db = Database()
    await db.connect()
    
    asi = await db.fetch_all("SELECT * FROM asistencias WHERE empleado_id=3")
    for a in asi:
        d = dict(a)
        print(f"{d['fecha']}: {d['horas_trabajadas']} hs, {d['hora_entrada_real']} - {d['hora_salida_real']}, sem={d['num_semana_ganadora']}")
    
    await db.disconnect()

asyncio.run(test())
