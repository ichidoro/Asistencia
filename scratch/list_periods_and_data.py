import sys
import os
import asyncio

# Ensure project path is in sys.path
sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\danie\Proyectos_Python\Asistencia\.env")

from backend.core.database import db

async def list_data():
    await db.connect()
    try:
        # Fetch all periods
        periods = await db.fetch_all("SELECT * FROM periodos_rrhh")
        print("=== PERIODS IN DATABASE ===")
        for p in periods:
            print(f"ID={p['id']}, MesCierre={p.get('mes_cierre')}, Range={p['fecha_inicio']} to {p['fecha_fin']}, Activo={p['activo']}, Estado={p['estado']}")

        # Fetch count of assignments per period
        print("\n=== ASSIGNMENTS PER PERIOD ===")
        counts = await db.fetch_all("""
            SELECT periodo_anio, periodo_mes, COUNT(*) as count 
            FROM empleado_productos_periodo 
            GROUP BY periodo_anio, periodo_mes
        """)
        for c in counts:
            print(f"Period: {c['periodo_anio']}-{c['periodo_mes']} -> Total Assignments: {c['count']}")
            
        # Let's inspect a few assignments if any
        if counts:
            first_p = counts[0]
            sample_asigs = await db.fetch_all("""
                SELECT * FROM empleado_productos_periodo 
                WHERE periodo_mes = ? AND periodo_anio = ? 
                LIMIT 3
            """, (first_p['periodo_mes'], first_p['periodo_anio']))
            print(f"\n=== SAMPLE ASSIGNMENTS FOR {first_p['periodo_anio']}-{first_p['periodo_mes']} ===")
            for sa in sample_asigs:
                print(dict(sa))
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(list_data())
