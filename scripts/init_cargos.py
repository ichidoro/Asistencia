import asyncio
from backend.core.database import db
from backend.repositories.empleado import EmpleadoRepository

async def init():
    await db.connect()
    repo = EmpleadoRepository(db)
    await repo.create_table()
    print("Tables created")

if __name__ == "__main__":
    asyncio.run(init())
