import sys
import os
import asyncio
import json

sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\danie\Proyectos_Python\Asistencia\.env")

from backend.core.database import db
from backend.repositories.seguridad import SeguridadRepository
from backend.schemas.auth import UsuarioCreate

async def run():
    await db.connect()
    repo = SeguridadRepository(db)
    
    # Check if testjefe already exists
    existing = await db.fetch_one("SELECT id FROM usuarios WHERE username = 'testjefe'")
    if existing:
        print("User testjefe already exists, deleting first...")
        await db.execute("DELETE FROM usuarios WHERE username = 'testjefe'")
        
    print("Creating testjefe user...")
    user_req = UsuarioCreate(
        username="testjefe",
        password="testjefe2026",
        nombre_completo="Test Jefe de Area",
        email="testjefe@aguacol.cl",
        activo=True,
        rol_id=2, # Jefe de Area
        areas=["LOGISTICA TRADICIONAL"]
    )
    user_id = await repo.create_user(user_req)
    print(f"User testjefe created with ID: {user_id}")
    
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(run())
