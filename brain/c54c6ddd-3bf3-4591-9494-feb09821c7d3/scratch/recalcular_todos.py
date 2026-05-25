import asyncio
import sys

# Append project path
sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from backend.core.database import db
from backend.repositories.asistencia import AsistenciaRepository
from backend.services.asistencia_service import AsistenciaService

async def check_status(emp_id, emp_name):
    rows = await db.fetch_all(
        "SELECT fecha, estado, num_semana_ganadora FROM asistencias WHERE empleado_id = ? AND fecha IN ('2026-05-03', '2026-05-10', '2026-05-17', '2026-05-24') ORDER BY fecha",
        (emp_id,)
    )
    print(f"\nStatus for {emp_name} (ID {emp_id}):")
    for r in rows:
        print(f"  {r['fecha']}: {r['estado']} (Semana {r['num_semana_ganadora']})")

async def main():
    await db.connect()
    
    asist_repo = AsistenciaRepository(db)
    asist_service = AsistenciaService(asist_repo)
    
    print("=== ESTADO INICIAL (RUDOCINDO & JULIAN) ===")
    await check_status(46, "Rudocindo")
    await check_status(48, "Julian")
    
    print("\n=== REPROCESANDO PERIODO CON LA LOGICA CORREGIDA ===")
    for emp_id in [46, 48]:
        await asist_service.reprocesar_periodo_empleado(
            empleado_id=emp_id,
            fecha_inicio="2026-04-26",
            fecha_fin="2026-05-25",
            force=True
        )
        
    print("\n=== ESTADO FINAL ===")
    await check_status(46, "Rudocindo")
    await check_status(48, "Julian")
    
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
