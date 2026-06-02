import sys
import os
import asyncio

sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\danie\Proyectos_Python\Asistencia\.env")

from backend.core.database import db

async def run_queries():
    await db.connect()
    
    print("--- SCHEMAS ---")
    rows = await db.fetch_all("SELECT name, sql FROM sqlite_master WHERE tbl_name IN ('asistencias', 'horas_extras')")
    for r in rows:
        print(f"Name: {r['name']}")
        print(r['sql'])
        print("-" * 50)
        
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(run_queries())
