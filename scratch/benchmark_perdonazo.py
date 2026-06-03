import asyncio
import time
import sys
import codecs

# Evitar UnicodeEncodeError en Windows
if sys.platform.startswith('win'):
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from backend.core.database import db
from backend.services.asistencia_service import AsistenciaService
from backend.repositories.asistencia import AsistenciaRepository

async def run_benchmark():
    await db.connect()
    repo = AsistenciaRepository(db)
    service = AsistenciaService(repo)
    
    # Obtener algunos empleados que tengan asistencias
    rows = await db.fetch_all("SELECT DISTINCT empleado_id FROM asistencias LIMIT 15")
    emp_ids = [r['empleado_id'] for r in rows]
    fecha = "2026-04-30"  # Una fecha de ejemplo
    
    if not emp_ids:
        print("No hay empleados en la BD para probar.")
        return
        
    print(f"Benchmark con {len(emp_ids)} empleados para la fecha {fecha}:")
    
    # --- 1. Enfoque Original (Concurrente por Empleado) ---
    print("\n--- Metodo Original: reprocesar_periodo_empleado concurrentemente ---")
    query = "UPDATE asistencias SET deuda_condonada = ?, updated_at = datetime('now') WHERE empleado_id = ? AND fecha = ?"
    params = [(3, emp_id, fecha) for emp_id in emp_ids]
    # Usar suppress_auto_sync=True para no medir el tiempo del update en el benchmark
    await db.executemany(query, params, suppress_auto_sync=True)
    
    t0 = time.time()
    tasks = [service.reprocesar_periodo_empleado(emp_id, fecha, fecha, force=True) for emp_id in emp_ids]
    await asyncio.gather(*tasks)
    t_orig = time.time() - t0
    print(f"Tiempo Metodo Original (Recalculo + Syncs): {t_orig:.2f} segundos")
    
    # --- 2. Enfoque Nuevo (Bulk por Dia) ---
    print("\n--- Metodo Nuevo: procesar_dia en bulk ---")
    # Revocar primero sin sync
    params_rev = [(0, emp_id, fecha) for emp_id in emp_ids]
    await db.executemany(query, params_rev, suppress_auto_sync=True)
    
    # Medir estrictamente el tiempo de procesar_dia
    t0 = time.time()
    await service.procesar_dia(fecha, force=True, empleado_ids=set(emp_ids))
    t_bulk = time.time() - t0
    print(f"Tiempo Metodo Nuevo (Bulk + Sync): {t_bulk:.2f} segundos")
    
    # Limpieza final
    params_clean = [(0, emp_id, fecha) for emp_id in emp_ids]
    await db.executemany(query, params_clean, suppress_auto_sync=True)
    await service.procesar_dia(fecha, force=True, empleado_ids=set(emp_ids))
    
    print("\nBenchmark completado con exito.")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
