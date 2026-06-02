import sys
import os
import asyncio
import time
from datetime import datetime

sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\danie\Proyectos_Python\Asistencia\.env")

from backend.core.database import db
from backend.services.asistencia_service import AsistenciaService
from backend.repositories.asistencia import AsistenciaRepository

async def test_performance():
    print("Conectando a base de datos...")
    await db.connect()
    
    print("Forzando modo NUBE PURA para emular Cloud Run...")
    db._force_turso_only = True
    
    empleado_id = 1
    fecha_inicio = "2026-04-26"
    fecha_fin = "2026-06-02"
    
    service = AsistenciaService(AsistenciaRepository(db))
    
    print(f"\nProcesando {fecha_inicio} a {fecha_fin} para empleado {empleado_id}...")
    t0 = time.time()
    res = await service.reprocesar_periodo_empleado(
        empleado_id=empleado_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        force=True,
        collect_only=True
    )
    t1 = time.time()
    
    duracion = t1 - t0
    print(f"\nCalculo completado exitosamente en: {duracion:.3f} segundos.")
    print(f"Resultados procesados: {len(res.get('_collect', []))} dias.")
    
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(test_performance())
