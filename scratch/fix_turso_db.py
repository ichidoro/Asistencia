import sys
import os
import asyncio

sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\danie\Proyectos_Python\Asistencia\.env")

from backend.core.database import db

async def fix_database():
    print("Conectando a Turso Cloud...")
    await db.connect()
    
    print("\n--- EJECUTANDO REINDEX ---")
    try:
        await db.execute("REINDEX")
        print("REINDEX completado con éxito.")
    except Exception as e:
        print(f"Error en REINDEX: {e}")
        
    print("\n--- EJECUTANDO VACUUM ---")
    try:
        await db.execute("VACUUM")
        print("VACUUM completado con éxito.")
    except Exception as e:
        print(f"Error en VACUUM: {e}")

    print("\n--- VERIFICANDO PRAGMA integrity_check DE NUEVO ---")
    try:
        rows = await db.fetch_all("PRAGMA integrity_check")
        for r in rows:
            print(r)
    except Exception as e:
        print(f"Error en integrity_check: {e}")

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(fix_database())
