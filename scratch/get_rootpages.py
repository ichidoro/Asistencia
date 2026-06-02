import sys
import os
import asyncio

sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\danie\Proyectos_Python\Asistencia\.env")

from backend.core.database import db

async def run_queries():
    await db.connect()
    
    print("--- ROOTPAGE MATCHES ---")
    rows = await db.fetch_all("SELECT type, name, tbl_name, rootpage FROM sqlite_master WHERE rootpage IN (70, 85)")
    for r in rows:
        print(dict(r))

    print("\n--- FIND DUPLICATES IN horas_extras ---")
    duplicates_he = await db.fetch_all("""
        SELECT empleado_id, fecha, COUNT(*) as c 
        FROM horas_extras 
        GROUP BY empleado_id, fecha 
        HAVING c > 1
    """)
    print(f"Total duplicate combinations in horas_extras: {len(duplicates_he)}")
    for d in duplicates_he[:5]:
        print(dict(d))

    print("\n--- FIND DUPLICATES IN asistencias ---")
    duplicates_asist = await db.fetch_all("""
        SELECT empleado_id, fecha, COUNT(*) as c 
        FROM asistencias 
        GROUP BY empleado_id, fecha 
        HAVING c > 1
    """)
    print(f"Total duplicate combinations in asistencias: {len(duplicates_asist)}")
    for d in duplicates_asist[:5]:
        print(dict(d))

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(run_queries())
