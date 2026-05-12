import asyncio
from backend.services.asistencia_service import AsistenciaService
from backend.repositories.asistencia import AsistenciaRepository
from backend.core.database import db
import logging
logging.basicConfig(level=logging.INFO)

async def test_reproceso():
    await db.connect()
    try:
        repo = AsistenciaRepository(db)
        service = AsistenciaService(repo)
        
        # Limpiar asistencias a partir de HOY (2026-05-12) para quitar la basura predictiva que quedo huerfana
        print("Eliminando registros huerfanos desde 2026-05-12...")
        await db.execute("DELETE FROM asistencias WHERE fecha >= '2026-05-12'")
        
        # Reprocesamos hasta el 25 de mayo
        print("Iniciando reproceso...")
        await service.reprocesar_periodo_empleado(1, "2026-04-26", "2026-05-25", force=True)
        await service.reprocesar_periodo_empleado(2, "2026-04-26", "2026-05-25", force=True)
        await service.reprocesar_periodo_empleado(3, "2026-04-26", "2026-05-25", force=True)
        
        print("Sincronizando...")
        await db.sync_to_cloud_explicit()
        
        print("Consultando resultados despues de reproceso...")
        res = await db.fetch_all("SELECT empleado_id, fecha, estado FROM asistencias WHERE fecha >= '2026-05-10' ORDER BY empleado_id, fecha")
        
        # Limpiar datos
        print("\n--- RESULTADOS EMP 1 ---")
        for r in [x for x in res if x['empleado_id'] == 1]:
            print(f"{r['fecha']}: {r['estado']}")
            
        print("\n--- RESULTADOS EMP 2 ---")
        for r in [x for x in res if x['empleado_id'] == 2]:
            print(f"{r['fecha']}: {r['estado']}")
            
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(test_reproceso())
