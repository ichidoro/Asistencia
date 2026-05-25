import asyncio
import sys

# Append project path
sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from backend.core.database import db
from backend.repositories.empleado import EmpleadoRepository
from backend.services.sync_service import SyncService

async def check_donoso_status():
    rows = await db.fetch_all(
        "SELECT fecha, estado, num_semana_ganadora FROM asistencias WHERE empleado_id = 47 AND fecha IN ('2026-05-09', '2026-05-16', '2026-05-23') ORDER BY fecha"
    )
    for r in rows:
        print(f"  {r['fecha']}: {r['estado']} (Semana {r['num_semana_ganadora']})")

async def main():
    await db.connect()
    
    # Obtener el RUT de Donoso (ID 47)
    emp_repo = EmpleadoRepository(db)
    emp = await emp_repo.get_by_id(47)
    if not emp:
        print("Error: Empleado Donoso (ID 47) no encontrado.")
        await db.disconnect()
        return
        
    rut = emp.rut
    print(f"RUT de Donoso: {rut}")
    
    print("\n=== ESTADO INICIAL ===")
    await check_donoso_status()
    
    print("\n=== EJECUTANDO SYNC_MARCACIONES CON LA NUEVA LOGICA DE RECALCULO ===")
    sync_service = SyncService()
    # Ejecutamos con force_recalculate=True sobre el rango
    stats = await sync_service.sync_marcaciones(
        fecha_inicio="2026-04-26",
        fecha_fin="2026-05-25",
        ruts=[rut],
        force_recalculate=True
    )
    print("Stats devueltos por el sync:")
    print(stats)
    
    print("\n=== ESTADO FINAL POST-SYNC ===")
    await check_donoso_status()
    
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
