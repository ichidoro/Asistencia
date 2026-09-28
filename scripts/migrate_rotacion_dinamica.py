import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(".venv/Lib/site-packages"))
sys.path.insert(0, os.path.abspath("."))

import dotenv
dotenv.load_dotenv()

from backend.core.database import TursoDatabase

async def migrate():
    db = TursoDatabase()
    await db.connect()
    
    print("=== MIGRACIÓN: AGREGAR rotacion_dinamica_diaria A turnos ===")
    cols = set(await db.get_column_names("turnos"))
    if "rotacion_dinamica_diaria" not in cols:
        print("Agregando columna rotacion_dinamica_diaria...")
        await db.execute("ALTER TABLE turnos ADD COLUMN rotacion_dinamica_diaria INTEGER DEFAULT 0")
        print("Columna agregada exitosamente.")
    else:
        print("Columna rotacion_dinamica_diaria ya existe.")

    # Set Turno 23 (Planta Mantencion 2) to 1
    print("Configurando rotacion_dinamica_diaria = 1 para Turno ID 23 (Planta Mantencion 2)...")
    await db.execute("UPDATE turnos SET rotacion_dinamica_diaria = 1 WHERE id = 23")
    
    # Verify all turnos
    rows = await db.fetch_all("""
        SELECT id, nombre, tipo_programacion, rotacion_dinamica_diaria, permite_viajes_largos
        FROM turnos
        ORDER BY id
    """)
    print("\n=== ESTADO DE TURNOS POST-MIGRACIÓN ===")
    for r in rows:
        din = "SÍ (1)" if r.get('rotacion_dinamica_diaria') else "NO (0)"
        vl = "SÍ (1)" if r.get('permite_viajes_largos') else "NO (0)"
        print(f"ID {r['id']:2} | {r['nombre']:35} | Prog:{r['tipo_programacion']:18} | Dinámico:{din:7} | ViajesLargos:{vl}")

if __name__ == "__main__":
    asyncio.run(migrate())
