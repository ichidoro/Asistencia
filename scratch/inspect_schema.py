import asyncio
import os
import sys
from loguru import logger

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.database import db

async def main():
    await db.connect()
    try:
        # Check cat_pagadores schema
        row = await db.fetch_one("SELECT sql FROM sqlite_master WHERE name = 'cat_pagadores'")
        if row:
            print("SCHEMA for cat_pagadores:", row["sql"])
        else:
            print("cat_pagadores table not found!")

        # Check unique cargos of employees
        cargos = await db.fetch_all("SELECT DISTINCT cargo FROM empleados")
        print("\nAll Unique Cargos:")
        for c in cargos:
            print(f"- {c['cargo']}")
            
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
