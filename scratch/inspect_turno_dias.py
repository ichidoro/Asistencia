import asyncio
import sys

sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from backend.core.database import db

async def main():
    await db.connect()
    
    # 1. Fetch all turno_dias for the Bolsa shift (ID 9)
    rows = await db.fetch_all("SELECT * FROM turno_dias WHERE turno_id = 9")
    print("--- turno_dias for Turno ID 9 ---")
    for r in rows:
        print(dict(r))
        
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
