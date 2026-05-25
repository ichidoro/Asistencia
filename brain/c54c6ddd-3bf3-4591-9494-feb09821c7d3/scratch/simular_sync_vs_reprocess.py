import asyncio
import sys

# Append project path
sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from backend.core.database import db
from backend.repositories.asistencia import AsistenciaRepository
from backend.services.asistencia_service import AsistenciaService
from backend.services.sync_service import SyncService

async def check_donoso_status():
    rows = await db.fetch_all(
        "SELECT fecha, estado, num_semana_ganadora FROM asistencias WHERE empleado_id = 47 AND fecha IN ('2026-05-09', '2026-05-16', '2026-05-23') ORDER BY fecha"
    )
    for r in rows:
        print(f"  {r['fecha']}: {r['estado']} (Semana {r['num_semana_ganadora']})")

async def main():
    await db.connect()
    
    asist_repo = AsistenciaRepository(db)
    asist_service = AsistenciaService(asist_repo)
    
    print("=== ESTADO INICIAL ===")
    await check_donoso_status()
    
    print("\n=== SIMULANDO REPROCESO DE PERIODO COMPLETO (MANUAL) ===")
    # Esto simula lo que hace el usuario al dar click en 'Reprocesar'
    await asist_service.reprocesar_periodo_empleado(
        empleado_id=47,
        fecha_inicio="2026-04-26",
        fecha_fin="2026-05-25",
        force=True
    )
    print("Resultados después de reprocesar período completo:")
    await check_donoso_status()
    
    print("\n=== SIMULANDO RECALCULO DE SYNC (DIA A DIA EN BUCLE) ===")
    # Esto simula lo que hace sync_marcaciones con force_recalculate=True
    # procesando día a día con procesar_dia
    fechas = []
    # Rango de fechas 2026-04-26 a 2026-05-25
    from datetime import datetime, timedelta
    curr = datetime.strptime("2026-04-26", "%Y-%m-%d")
    end = datetime.strptime("2026-05-25", "%Y-%m-%d")
    while curr <= end:
        fechas.append(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)
        
    for fecha in fechas:
        # procesar_dia para el empleado 47
        await asist_service.procesar_dia(fecha, empleado_ids={47}, force=True)
        
    print("Resultados después del recálculo día a día (Sync):")
    await check_donoso_status()
    
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
