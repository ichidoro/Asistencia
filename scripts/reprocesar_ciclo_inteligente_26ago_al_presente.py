import asyncio
import os
import sys
import time
from datetime import datetime

# Garantizar encoding utf-8 en Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath(".venv/Lib/site-packages"))
sys.path.insert(0, os.path.abspath("."))

import dotenv
dotenv.load_dotenv()

from backend.core.database import TursoDatabase
from backend.repositories.asistencia import AsistenciaRepository
from backend.services.asistencia_service import AsistenciaService
from backend.services.calendario_service import CalendarioService

async def main():
    db = TursoDatabase()
    await db.connect()
    repo = AsistenciaRepository(db)
    service = AsistenciaService(repo)

    # 1. Determinar fecha máxima con marcaciones reales en logs_raw
    max_log_row = await db.fetch_one("SELECT MAX(date(fecha_hora)) as max_fecha FROM logs_raw")
    f_max_logs = max_log_row['max_fecha'] if max_log_row and max_log_row['max_fecha'] else '2026-09-29'
    
    fecha_ini = '2026-08-26'
    fecha_fin = f_max_logs
    print(f"=========================================================================================")
    print(f"   REPROCESO CANÓNICO CICLO INTELIGENTE: {fecha_ini} HASTA {fecha_fin}")
    print(f"=========================================================================================")

    # 2. Obtener todos los empleados de CICLO_INTELIGENTE en el período
    query = """
        SELECT DISTINCT e.id, e.nombre, e.apellido_paterno, e.apellido_materno, ha.area_id, ar.nombre as area_nombre, t.tipo_programacion, t.id as turno_id, t.nombre as turno_nombre
        FROM empleados e
        JOIN asignacion_turnos ast ON e.id = ast.empleado_id
        JOIN turnos t ON ast.turno_id = t.id
        LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
        LEFT JOIN areas ar ON ha.area_id = ar.id
        WHERE t.tipo_programacion = 'CICLO_INTELIGENTE' 
          AND ast.fecha_inicio <= ? AND (ast.fecha_fin IS NULL OR ast.fecha_fin >= ?)
          AND e.activo = 1
          AND e.id != 999999
        ORDER BY ar.nombre, e.apellido_paterno, e.nombre
    """
    ci_employees = await db.fetch_all(query, (fecha_fin, fecha_ini))
    emp_ids = [r['id'] for r in ci_employees]
    print(f"Colaboradores de Ciclo Inteligente identificados: {len(emp_ids)}")

    # 3. Guardia de Seguridad: Asegurar que NINGÚN empleado de Bolsa Flexible esté incluido
    check_bolsa = await db.fetch_all(f"""
        SELECT DISTINCT e.id, e.nombre, t.tipo_programacion, t.nombre as turno_nombre
        FROM empleados e
        JOIN asignacion_turnos ast ON e.id = ast.empleado_id
        JOIN turnos t ON ast.turno_id = t.id
        WHERE e.id IN ({','.join(str(i) for i in emp_ids)})
          AND ast.fecha_inicio <= ? AND (ast.fecha_fin IS NULL OR ast.fecha_fin >= ?)
          AND t.tipo_programacion IN ('BOLSA_FLEXIBLE', 'FLEXIBLE_BOLSA')
    """, (fecha_fin, fecha_ini))
    
    if check_bolsa:
        print(f"⛔ ERROR CRÍTICO: Se detectaron {len(check_bolsa)} colaboradores de Bolsa Flexible en el lote:")
        for b in check_bolsa:
            print(f"   - ID {b['id']} ({b['nombre']}): Turno {b['turno_nombre']} ({b['tipo_programacion']})")
        print("Abortando reproceso para proteger integridad de Flota Transporte.")
        return

    print("🛡️ Guardia de Seguridad: 0 empleados de Bolsa Flexible en el lote. Aislamiento 100% confirmado.")

    # 4. Pre-cargar feriados
    cal_svc = CalendarioService()
    feriados = await cal_svc.get_feriados(2026)
    feriados_dict = {f['fecha']: f['descripcion'] for f in feriados}

    t0 = time.time()
    all_results_to_save = []
    all_results_to_delete = []
    all_he_to_save = []
    all_he_to_delete = []
    all_je_to_save = []
    all_je_to_delete = []

    print(f"\nIniciando cálculo matricial puro en memoria para {len(emp_ids)} colaboradores...")

    for i, emp in enumerate(ci_employees, 1):
        eid = emp['id']
        t_start = time.time()
        
        r = await service.reprocesar_periodo_empleado(
            eid, fecha_ini, fecha_fin, force=True,
            feriados_preloaded=feriados_dict,
            collect_only=True
        )
        
        c_asist = len(r.get('_collect', []))
        c_he = len(r.get('_he_collect', []))
        c_je = len(r.get('_je_collect', []))
        
        all_results_to_save.extend(r.get('_collect', []))
        all_results_to_delete.extend(r.get('_delete_collect', []))
        all_he_to_save.extend(r.get('_he_collect', []))
        all_he_to_delete.extend(r.get('_he_delete', []))
        all_je_to_save.extend(r.get('_je_collect', []))
        all_je_to_delete.extend(r.get('_je_delete', []))

        t_elapsed = round(time.time() - t_start, 2)
        if i % 10 == 0 or i == len(emp_ids) or emp.get('area_nombre') == 'MANTENCIÓN':
            nombre_full = f"{emp['nombre']} {emp['apellido_paterno'] or ''}".strip()
            print(f"[{i:02d}/{len(emp_ids):02d}] ID {eid:3d} ({nombre_full:28s}) | Área: {emp['area_nombre'] or 'N/A':15s} | Asist: {c_asist:2d}, HE: {c_he:2d}, JE: {c_je:2d} ({t_elapsed}s)")

    t_recoleccion = round(time.time() - t0, 1)
    print(f"\n✅ Recolección en memoria completada en {t_recoleccion}s.")
    print(f"Totales recopilados para persistencia:")
    print(f"  - Asistencias: {len(all_results_to_save)} upserts, {len(all_results_to_delete)} deletes")
    print(f"  - Horas Extras: {len(all_he_to_save)} upserts, {len(all_he_to_delete)} deletes")
    print(f"  - Jornadas Especiales: {len(all_je_to_save)} upserts, {len(all_je_to_delete)} deletes")

    # 5. Persistencia en lotes atómicos (chunk_size=50)
    chunk_size = 50
    t_save_start = time.time()

    if all_results_to_save:
        await repo.batch_upsert_asistencia(all_results_to_save, suppress_auto_sync=True)
        print("💾 Asistencias guardadas.")

    if all_results_to_delete:
        for i in range(0, len(all_results_to_delete), chunk_size):
            chunk = all_results_to_delete[i:i + chunk_size]
            await repo.db.executemany("DELETE FROM asistencias WHERE empleado_id = ? AND fecha = ?", chunk, suppress_auto_sync=True)
        print("🗑️ Asistencias huérfanas eliminadas.")

    if all_he_to_save:
        await service.he_repo.batch_upsert(all_he_to_save, suppress_auto_sync=True)
        print("💾 Horas extras guardadas.")

    if all_he_to_delete:
        await service.he_repo.batch_delete_by_empleado_fecha(all_he_to_delete, suppress_auto_sync=True)
        print("🗑️ Horas extras huérfanas eliminadas.")

    if all_je_to_save:
        for je_rec in all_je_to_save:
            await repo.upsert_jornada_especial(je_rec)
        print(f"💾 Jornadas especiales ({len(all_je_to_save)}) guardadas con origen trazable.")

    if all_je_to_delete:
        for i in range(0, len(all_je_to_delete), chunk_size):
            chunk = all_je_to_delete[i:i + chunk_size]
            await repo.db.executemany(
                "DELETE FROM jornadas_especiales WHERE empleado_id = ? AND fecha = ? AND estado NOT IN ('EXTRA', 'RECHAZADA') AND observaciones NOT LIKE '%[VALIDADO]%' AND observaciones NOT LIKE '%[RECHAZADO]%'",
                chunk, suppress_auto_sync=True
            )
        print("🗑️ Jornadas especiales huérfanas limpiadas (protegiendo decisiones humanas).")

    # 6. Sincronización explícita
    await db.sync_to_cloud_explicit()
    t_total = round(time.time() - t0, 1)
    print(f"\n🎉 REPROCESO DE CICLO INTELIGENTE COMPLETADO EXITOSAMENTE en {t_total}s!")

    # 7. Verificación de Mantención
    print("\n=========================================================================================")
    print("   VERIFICACIÓN POST-REPROCESO: ÁREA DE MANTENCIÓN (5 COLABORADORES)")
    print("=========================================================================================")
    mant_rows = await db.fetch_all("""
        SELECT a.empleado_id, e.nombre, e.apellido_paterno,
               SUM(a.minutos_atraso) as tot_atr,
               SUM(a.minutos_salida_adelantada) as tot_sad,
               SUM(a.minutos_exceso_colacion) as tot_col,
               SUM(a.minutos_deuda) as tot_deuda,
               SUM(CASE WHEN h.estado = 'APROBADO' THEN h.minutos_autorizados ELSE 0 END) as tot_he_apr
        FROM asistencias a
        JOIN empleados e ON a.empleado_id = e.id
        LEFT JOIN horas_extras h ON a.empleado_id = h.empleado_id AND a.fecha = h.fecha
        WHERE a.empleado_id IN (36, 37, 38, 39, 170)
          AND a.fecha BETWEEN ? AND ?
        GROUP BY a.empleado_id, e.nombre, e.apellido_paterno
        ORDER BY a.empleado_id
    """, (fecha_ini, fecha_fin))
    
    for r in mant_rows:
        def fmt_m(m):
            if not m: return "00:00:00"
            neg = m < 0
            m = abs(m)
            sec = int(round(m * 60))
            h = sec // 3600
            rem = sec % 3600
            return f"{'-' if neg else ''}{h:02d}:{rem//60:02d}:{rem%60:02d}"
        
        saldo = (r['tot_he_apr'] or 0) - (r['tot_deuda'] or 0)
        print(f"ID {r['empleado_id']:3d} | {r['nombre']} {r['apellido_paterno']}: ATR={fmt_m(r['tot_atr'])} | SAD={fmt_m(r['tot_sad'])} | COL={fmt_m(r['tot_col'])} | TNT={fmt_m(r['tot_deuda'])} | HE_APR={fmt_m(r['tot_he_apr'])} | SALDO={fmt_m(saldo)}")

if __name__ == "__main__":
    asyncio.run(main())
