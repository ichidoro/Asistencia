import sys
import os
import asyncio

sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\danie\Proyectos_Python\Asistencia\.env")

from backend.core.database import db

async def run():
    await db.connect()
    
    print("Deleting testjefe user...")
    await db.execute("DELETE FROM usuarios WHERE username = 'testjefe'")
    print("User testjefe deleted.")
    
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(run())
