import sys
import os
import asyncio

sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\danie\Proyectos_Python\Asistencia\.env")

from backend.core.database import db

async def find_duplicates():
    await db.connect()
    
    print("Loading all horas_extras...")
    he_rows = await db.fetch_all("SELECT id, empleado_id, fecha FROM horas_extras")
    seen_he = {}
    duplicates_he = []
    for r in he_rows:
        key = (r['empleado_id'], r['fecha'])
        if key in seen_he:
            duplicates_he.append((key, seen_he[key], r['id']))
        else:
            seen_he[key] = r['id']
            
    print(f"Total horas_extras rows loaded: {len(he_rows)}")
    print(f"Total duplicate combinations found in memory for horas_extras: {len(duplicates_he)}")
    for d in duplicates_he[:10]:
        print(f"Key: {d[0]}, Existing ID: {d[1]}, Duplicate ID: {d[2]}")

    print("\nLoading all asistencias...")
    asist_rows = await db.fetch_all("SELECT id, empleado_id, fecha FROM asistencias")
    seen_asist = {}
    duplicates_asist = []
    for r in asist_rows:
        key = (r['empleado_id'], r['fecha'])
        if key in seen_asist:
            duplicates_asist.append((key, seen_asist[key], r['id']))
        else:
            seen_asist[key] = r['id']
            
    print(f"Total asistencias rows loaded: {len(asist_rows)}")
    print(f"Total duplicate combinations found in memory for asistencias: {len(duplicates_asist)}")
    for d in duplicates_asist[:10]:
        print(f"Key: {d[0]}, Existing ID: {d[1]}, Duplicate ID: {d[2]}")

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(find_duplicates())
