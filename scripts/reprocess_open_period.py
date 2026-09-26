import asyncio
import os
import sys
import time

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.abspath('.venv/Lib/site-packages'))
sys.path.insert(0, os.path.abspath('.'))
import dotenv
dotenv.load_dotenv()
from backend.core.database import TursoDatabase
from backend.repositories.asistencia import AsistenciaRepository
from backend.services.asistencia_service import AsistenciaService

async def main():
    db = TursoDatabase()
    await db.connect()
    repo = AsistenciaRepository(db)
    service = AsistenciaService(repo)
    
    # 1. Obtener período abierto oficial de periodos_rrhh
    p_act = await db.fetch_one("SELECT * FROM periodos_rrhh WHERE activo = 1 LIMIT 1")
    if p_act:
        fecha_ini = p_act['fecha_inicio']
        fecha_fin = p_act['fecha_fin']
        nombre_periodo = p_act['mes_cierre']
    else:
        # Fallback al periodo conocido si no hay marca activa
        fecha_ini = '2026-08-26'
        fecha_fin = '2026-09-25'
        nombre_periodo = 'Septiembre 2026 (2026-08-26 -> 2026-09-25)'

    print(f"🚀 REPROCESANDO PERÍODO ABIERTO COMPLETO: {nombre_periodo}")
    print(f"📅 Rango de fechas: {fecha_ini} al {fecha_fin}")
    
    from datetime import datetime, timedelta
    d_curr = datetime.strptime(fecha_ini, "%Y-%m-%d")
    d_end = datetime.strptime(fecha_fin, "%Y-%m-%d")
    
    total_days = (d_end - d_curr).days + 1
    day_idx = 1
    start_total = time.time()
    
    while d_curr <= d_end:
        f_str = d_curr.strftime("%Y-%m-%d")
        t0 = time.time()
        try:
            await service.procesar_dia(f_str, force=True)
            elapsed = time.time() - t0
            print(f"  [{day_idx:02d}/{total_days:02d}] {f_str} OK en {elapsed:.1f}s", flush=True)
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  [{day_idx:02d}/{total_days:02d}] {f_str} ERROR ({e}) en {elapsed:.1f}s", flush=True)
        
        d_curr += timedelta(days=1)
        day_idx += 1

    total_time = time.time() - start_total
    print(f"\n✅ Período abierto completo reprocesado en {total_time:.1f}s ({total_time/60:.2f} min).")

    # 2. Resumen estadístico del período abierto completo
    stats = await db.fetch_all("""
        SELECT estado, COUNT(*) as count 
        FROM asistencias 
        WHERE fecha BETWEEN ? AND ? 
        GROUP BY estado 
        ORDER BY count DESC
    """, (fecha_ini, fecha_fin))
    
    print(f"\n📊 Resumen de estados en la tabla asistencias ({fecha_ini} a {fecha_fin}):")
    for s in stats:
        print(f"  {s['estado']}: {s['count']}")

    # 3. Comprobación específica de choferes Bolsa Flexible (Turnos 9 y 25)
    choferes_stats = await db.fetch_all("""
        SELECT a.turno_asignado_id, a.estado, COUNT(*) as count
        FROM asistencias a
        WHERE a.fecha BETWEEN ? AND ?
          AND a.turno_asignado_id IN (9, 25)
        GROUP BY a.turno_asignado_id, a.estado
        ORDER BY a.turno_asignado_id, count DESC
    """, (fecha_ini, fecha_fin))
    
    # 4. Comprobación específica de guardias Seguridad (Turno 1: IDs 1, 2, 3)
    seg_stats = await db.fetch_all("""
        SELECT a.empleado_id, e.nombre, e.apellido_paterno, a.fecha, a.estado, a.horas_trabajadas, a.minutos_extra_bruto
        FROM asistencias a
        JOIN empleados e ON a.empleado_id = e.id
        WHERE a.fecha BETWEEN ? AND ?
          AND a.empleado_id IN (1, 2, 3)
        ORDER BY a.empleado_id, a.fecha
    """, (fecha_ini, fecha_fin))
    print(f"\n🛡️ Asistencias Guardias Planta Seguridad ({len(seg_stats)} registros):")
    for ss in seg_stats:
        print(f"  Emp {ss['empleado_id']} ({ss['nombre']} {ss['apellido_paterno']}) {ss['fecha']}: {ss['estado']} ({ss['horas_trabajadas']}h, HE={ss['minutos_extra_bruto']})")

    # 5. Resumen de Jornadas Especiales (+2)
    je_rows = await db.fetch_all("""
        SELECT j.*, e.nombre, e.apellido_paterno
        FROM jornadas_especiales j
        JOIN empleados e ON j.empleado_id = e.id
        WHERE j.fecha BETWEEN ? AND ?
        ORDER BY j.fecha, j.empleado_id
    """, (fecha_ini, fecha_fin))
    print(f"\n⭐ Total Jornadas Especiales registradas en período ({len(je_rows)}):")
    for jr in je_rows:
        print(f"  {jr['fecha']} | Emp {jr['empleado_id']} ({jr['nombre']} {jr['apellido_paterno']}): {jr['hora_entrada']} - {jr['hora_salida']} ({round(jr['minutos_trabajados']/60.0, 1)}h netas) | {jr['estado']} | {jr['observaciones']}")

if __name__ == '__main__':
    asyncio.run(main())
