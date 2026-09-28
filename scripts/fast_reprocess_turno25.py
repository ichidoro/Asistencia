import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(".venv/Lib/site-packages"))
sys.path.insert(0, os.path.abspath('.'))

import dotenv
dotenv.load_dotenv()

from backend.core.database import get_db
from backend.repositories.asistencia import AsistenciaRepository
from backend.services.quantum_matrix_engine import QuantumMatrixEngine

async def main():
    db = await get_db()
    repo = AsistenciaRepository(db)
    
    fecha_ini = '2026-08-26'
    fecha_fin = '2026-09-25'
    
    t25 = await db.fetch_one("SELECT * FROM turnos WHERE id = 25")
    
    # 1. Choferes
    choferes = await db.fetch_all("""
        SELECT a.empleado_id, e.nombre, e.apellido_paterno
        FROM asignacion_turnos a
        JOIN empleados e ON e.id = a.empleado_id
        WHERE a.turno_id = 25 AND e.activo = 1
        ORDER BY a.empleado_id
    """)
    chofer_ids = [c['empleado_id'] for c in choferes]
    placeholders = ",".join(str(i) for i in chofer_ids)
    
    print("=" * 80)
    print(f"🚀 REPROCESO DE ALTO RENDIMIENTO: TURNO 25 ({len(chofer_ids)} CHOFERES)")
    print(f"📅 Período: {fecha_ini} al {fecha_fin} (31 días)")
    print("=" * 80)
    
    # 2. Cargar datos en bulk
    print("⏳ Cargando logs crudos, justificaciones y viajes largos...")
    logs_raw_all = await db.fetch_all(f"""
        SELECT * FROM logs_raw
        WHERE empleado_id IN ({placeholders})
          AND fecha_hora >= '2026-08-23 00:00:00'
          AND fecha_hora <= '2026-09-27 23:59:59'
        ORDER BY fecha_hora ASC
    """)
    logs_por_emp = {}
    for l in logs_raw_all:
        logs_por_emp.setdefault(l['empleado_id'], []).append(dict(l))
        
    justs_all = await db.fetch_all(f"""
        SELECT * FROM justificaciones
        WHERE empleado_id IN ({placeholders})
          AND fecha_fin >= '{fecha_ini}' AND fecha_inicio <= '{fecha_fin}'
    """)
    justs_por_emp = {}
    for j in justs_all:
        justs_por_emp.setdefault(j['empleado_id'], []).append(dict(j))
        
    vl_all = await db.fetch_all(f"""
        SELECT * FROM viajes_largos
        WHERE empleado_id IN ({placeholders})
          AND fecha_fin >= '{fecha_ini}' AND fecha_inicio <= '{fecha_fin}'
    """)
    vl_por_emp = {}
    for v in vl_all:
        vl_por_emp.setdefault(v['empleado_id'], []).append(dict(v))
        
    # Feriados
    feriados = await db.fetch_all("SELECT fecha FROM feriados WHERE fecha BETWEEN ? AND ?", (fecha_ini, fecha_fin))
    feriados_set = {f['fecha'] for f in feriados}
    
    print(f"✅ Datos cargados: {len(logs_raw_all)} logs, {len(justs_all)} justificaciones, {len(vl_all)} viajes largos.")
    
    # Cargar configuracion real de turno_dias para Turno 25
    td_rows = await db.fetch_all("SELECT * FROM turno_dias WHERE turno_id = 25 ORDER BY dia_semana")
    td_by_dia = {r['dia_semana']: dict(r) for r in td_rows}
    print(f"✅ Cargados {len(td_by_dia)} días de configuración para Turno 25 desde la BD.")
    
    # 3. Procesar día a día para cada chofer
    t0 = time.time()
    asistencias_para_guardar = []
    
    for ch in choferes:
        emp_id = ch['empleado_id']
        nom = f"{ch['nombre']} {ch['apellido_paterno']}"
        emp_logs = logs_por_emp.get(emp_id, [])
        emp_justs = justs_por_emp.get(emp_id, [])
        emp_vls = vl_por_emp.get(emp_id, [])
        
        cur = datetime(2026, 8, 26)
        end = datetime(2026, 9, 25)
        consumidas = set()
        
        while cur <= end:
            f_str = cur.strftime("%Y-%m-%d")
            dia_sem = cur.weekday()
            cfg_dia = td_by_dia.get(dia_sem, {'es_libre': dia_sem in (5, 6), 'horas_teoricas': 0.0, 'hora_entrada': '08:00', 'hora_salida': '16:00'})
            is_hol = f_str in feriados_set
            
            vl_dia = next((v for v in emp_vls if v['fecha_inicio'] <= f_str <= v['fecha_fin']), None)
            
            res = QuantumMatrixEngine.solve_attendance_day(
                fecha=f_str,
                empleado_id=emp_id,
                logs=emp_logs,
                turno_config=dict(t25),
                dia_config=cfg_dia,
                is_holiday=is_hol,
                justificaciones=emp_justs,
                consumidas_previas=consumidas,
                viaje_largo_info=dict(vl_dia) if vl_dia else None
            )
            
            for mid in res.get('marcas_consumidas_ids', []):
                consumidas.add(mid)
                
            res['empleado_id'] = emp_id
            res['fecha'] = f_str
            res['turno_asignado_id'] = 25
            res['hora_entrada_teorica'] = cfg_dia.get('hora_entrada')
            res['hora_salida_teorica'] = cfg_dia.get('hora_salida')
            res['horas_teoricas'] = float(cfg_dia.get('horas_teoricas', 0.0) or 0.0)
            res['origen'] = 'SISTEMA'
            res['num_semana_ganadora'] = 1
            res['marcas_consumidas_ids'] = json.dumps(res.get('marcas_consumidas_ids') or [])
            
            asistencias_para_guardar.append(res)
            cur += timedelta(days=1)
            
    # 4. Guardar masivamente en Turso Cloud
    print(f"\n💾 Guardando {len(asistencias_para_guardar)} registros en tabla 'asistencias'...")
    await repo.batch_upsert_asistencia(asistencias_para_guardar, bypass_cierre_check=True)
    duracion = time.time() - t0
    print(f"✅ Guardado completado en {duracion:.2f} segundos.")
    
    # 5. Resumen final consolidado de la BD
    print("\n" + "=" * 105)
    print(f"{'EMP':<5} | {'NOMBRE':<28} | {'OK':<4} | {'ANOM':<5} | {'INAS':<5} | {'LIBRE':<6} | {'JUST':<5} | {'HORAS':<7} | {'META':<5} | {'%'}")
    print("-" * 105)
    
    for ch in choferes:
        eid = ch['empleado_id']
        nom = f"{ch['nombre']} {ch['apellido_paterno']}"
        rows = await db.fetch_all("""
            SELECT estado, horas_trabajadas
            FROM asistencias
            WHERE empleado_id = ? AND fecha BETWEEN ? AND ?
        """, (eid, fecha_ini, fecha_fin))
        
        d_ok = sum(1 for rw in rows if rw['estado'] in ('OK', 'VIAJE_LARGO'))
        d_anom = sum(1 for rw in rows if rw['estado'] == 'ANOMALIA')
        d_inas = sum(1 for rw in rows if rw['estado'] == 'INASISTENCIA')
        d_lib = sum(1 for rw in rows if rw['estado'] in ('LIBRE', 'FERIADO'))
        d_just = sum(1 for rw in rows if rw['estado'] in ('VACACIONES', 'LICENCIA_MEDICA', 'PERMISO', 'JUSTIFICADO'))
        tot_h = sum(float(rw['horas_trabajadas'] or 0.0) for rw in rows)
        pct = round(tot_h / 180.0 * 100.0, 1)
        print(f"{eid:<5} | {nom:<28} | {d_ok:<4} | {d_anom:<5} | {d_inas:<5} | {d_lib:<6} | {d_just:<5} | {round(tot_h,1):<7} | 180.0 | {pct}%")

if __name__ == '__main__':
    asyncio.run(main())
