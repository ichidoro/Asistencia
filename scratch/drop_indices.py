import sys
import os
import asyncio

sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\danie\Proyectos_Python\Asistencia\.env")

from backend.core.database import db

async def drop_indices():
    print("Conectando a Turso Cloud...")
    await db.connect()
    
    indices_to_drop = [
        "idx_asis_empleado_fecha",
        "idx_asis_fecha",
        "idx_asis_estado",
        "idx_asistencias_emp_fecha",
        "idx_he_empleado",
        "idx_he_fecha",
        "idx_he_estado",
        "idx_he_emp_fecha"
    ]
    
    print("\n--- DROPPING CORRUPTED INDEXES ---")
    for index_name in indices_to_drop:
        print(f"Dropping index: {index_name}...")
        try:
            await db.execute(f"DROP INDEX IF EXISTS {index_name}")
            print(f"   -> Drop index {index_name} successful.")
        except Exception as e:
            print(f"   -> Error dropping index {index_name}: {e}")
            
    print("\nExecuting PRAGMA integrity_check...")
    try:
        check_rows = await db.fetch_all("PRAGMA integrity_check")
        for r in check_rows:
            print(f"   -> Result: {r.get('integrity_check')}")
    except Exception as e:
        print(f"Error checking integrity: {e}")
        
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(drop_indices())
