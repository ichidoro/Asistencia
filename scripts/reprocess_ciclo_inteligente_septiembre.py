import asyncio
import os
import sys
import time

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.abspath('.'))
from backend.core.database import get_db
from backend.repositories.asistencia import AsistenciaRepository
from backend.services.asistencia_service import AsistenciaService

async def main():
    db = await get_db()
    
    # 1. Obtener período oficial activo
    periodo_activo = await db.fetch_one("SELECT * FROM periodos_rrhh WHERE activo = 1 AND estado = 'abierto'")
    if not periodo_activo:
        print("ERROR: No se encontró período RRHH activo y abierto.")
        return
    
    fecha_ini = periodo_activo['fecha_inicio'] # 2026-08-26
    fecha_fin = periodo_activo['fecha_fin']    # 2026-09-25
    mes_cierre = periodo_activo['mes_cierre']  # Septiembre 2026
    
    # 2. Obtener lista de IDs EXCLUSIVAMENTE de CICLO_INTELIGENTE
    c = await db.fetch_all('''
        SELECT DISTINCT e.id, e.nombre, t.nombre as turno
        FROM empleados e
        JOIN asignacion_turnos at ON e.id = at.empleado_id
        JOIN turnos t ON at.turno_id = t.id
        WHERE e.activo = 1
          AND t.tipo_programacion = 'CICLO_INTELIGENTE'
          AND at.fecha_inicio <= ?
          AND (at.fecha_fin IS NULL OR at.fecha_fin >= ?)
        ORDER BY e.id
    ''', (fecha_fin, fecha_ini))
    
    ciclo_ids = [r['id'] for r in c]
    
    print("=" * 75)
    print(f"🚀 REPROCESO EXCLUSIVO CICLO INTELIGENTE: {mes_cierre}")
    print(f"📅 Rango estricto de RRHH: {fecha_ini} al {fecha_fin} (31 días)")
    print(f"👥 Empleados a procesar: {len(ciclo_ids)} (Bolsa Flexible EXCLUIDA)")
    print("=" * 75)
    
    placeholders = ",".join("?" for _ in ciclo_ids)
    
    # 3. Resumen previo
    prev_stats = await db.fetch_all(f"""
        SELECT estado, COUNT(*) as count 
        FROM asistencias 
        WHERE fecha BETWEEN ? AND ? 
          AND empleado_id IN ({placeholders})
        GROUP BY estado 
        ORDER BY count DESC
    """, (fecha_ini, fecha_fin, *ciclo_ids))
    print("\n📊 Estado previo de Ciclo Inteligente en 'asistencias':")
    for s in prev_stats:
        print(f"   {s['estado']}: {s['count']}")

    # 4. Ejecutar reprocesamiento con el nuevo motor cuántico
    repo = AsistenciaRepository(db)
    service = AsistenciaService(repo)
    
    t0 = time.time()
    res = await service.procesar_periodo(fecha_ini, fecha_fin, force=True, empleado_ids=ciclo_ids)
    duracion = time.time() - t0
    
    print(f"\n✅ Procesamiento completado en {duracion:.1f} segundos: {res}")
    
    # 5. Resumen posterior
    post_stats = await db.fetch_all(f"""
        SELECT estado, COUNT(*) as count 
        FROM asistencias 
        WHERE fecha BETWEEN ? AND ? 
          AND empleado_id IN ({placeholders})
        GROUP BY estado 
        ORDER BY count DESC
    """, (fecha_ini, fecha_fin, *ciclo_ids))
    print("\n📊 Estado post-reproceso en 'asistencias' (Ciclo Inteligente):")
    for s in post_stats:
        print(f"   {s['estado']}: {s['count']}")

    # 6. Auditoría de Jornadas Especiales generadas/preservadas
    je_stats = await db.fetch_all(f"""
        SELECT origen, estado, COUNT(*) as count, SUM(minutos_trabajados)/60.0 as horas_totales
        FROM jornadas_especiales 
        WHERE fecha BETWEEN ? AND ? 
          AND empleado_id IN ({placeholders})
        GROUP BY origen, estado
    """, (fecha_ini, fecha_fin, *ciclo_ids))
    print(f"\n🏷️ Jornadas Especiales detectadas en {mes_cierre} para Ciclo Inteligente:")
    for je in je_stats:
        print(f"   Origen: {je['origen']} | Estado: {je['estado']} | Cantidad: {je['count']} | Horas: {je['horas_totales']:.1f}h")

if __name__ == '__main__':
    asyncio.run(main())
