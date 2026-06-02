import sys
import os
import asyncio
import time
from datetime import datetime, timedelta

# Asegurar que la carpeta raíz del proyecto esté en el path
sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\danie\Proyectos_Python\Asistencia\.env")

from backend.core.database import db
from backend.services.asistencia_service import AsistenciaService

async def run_simulation():
    print("======================================================================")
    print("SIMULACION DE RENDIMIENTO: OPTIMIZACION DEL MOTOR DE ASISTENCIA")
    print("======================================================================")
    
    # Forzar el modo NUBE PURA (sin réplica local) para medir la latencia de red de Turso.
    # Esto imita fielmente el comportamiento de Google Cloud Run en producción.
    # Debe ser seteado ANTES de connect() para que conecte directo a cloud.
    print("Forzando modo NUBE PURA (para emular latencia de Cloud Run)...")
    db._force_turso_only = True
    
    print("\nConectando a base de datos...")
    await db.connect()
    
    # ID del empleado de prueba: Rudecindo (ID 1)
    empleado_id = 1
    fecha_inicio = "2026-04-26"
    fecha_fin = "2026-06-02"
    
    # 1. Medir corrida ORIGINAL (N+1 queries en red)
    print(f"\nEjecutando version ORIGINAL para Empleado ID {empleado_id} (Periodo: {fecha_inicio} a {fecha_fin})...")
    from backend.repositories.asistencia import AsistenciaRepository
    repo = AsistenciaRepository(db)
    service = AsistenciaService(repo)
    
    t0_orig = time.time()
    res_orig = await service.reprocesar_periodo_empleado(
        empleado_id=empleado_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        force=True,  # Forzar recalculo
        collect_only=True  # No escribir en DB para evitar ensuciar
    )
    t1_orig = time.time()
    duracion_orig = t1_orig - t0_orig
    print(f"Version ORIGINAL completada en: {duracion_orig:.3f} segundos")
    
    # 2. Precargar datos en RAM para simular la optimización
    print("\nPrecargando datos en RAM para simulacion optimizada (Bulk Fetch)...")
    t0_bulk = time.time()
    
    # Estructura del caché
    mock_cache = {
        'intercambios': {},
        'compensaciones': {},
        'jornadas_especiales': {},
        'horas_extras': {}
    }
    
    # A. Intercambios
    q_inter = """
        SELECT * FROM intercambios_dias
        WHERE (empleado_solicitante_id = ? OR empleado_receptor_id = ?)
          AND (
            (fecha_origen BETWEEN ? AND ?) 
            OR (fecha_destino BETWEEN ? AND ?)
          )
          AND estado = 'APROBADO'
    """
    inter_rows = await db.fetch_all(q_inter, (empleado_id, empleado_id, fecha_inicio, fecha_fin, fecha_inicio, fecha_fin))
    for row in inter_rows:
        row_dict = dict(row)
        mock_cache['intercambios'][row_dict['fecha_origen']] = row_dict
        mock_cache['intercambios'][row_dict['fecha_destino']] = row_dict
        
    # B. Compensaciones
    q_comp = """
        SELECT * FROM compensaciones_he_inasistencia
        WHERE empleado_id = ?
          AND fecha_inasistencia BETWEEN ? AND ?
    """
    comp_rows = await db.fetch_all(q_comp, (empleado_id, fecha_inicio, fecha_fin))
    for row in comp_rows:
        row_dict = dict(row)
        f_inasist = row_dict['fecha_inasistencia']
        if f_inasist not in mock_cache['compensaciones']:
            mock_cache['compensaciones'][f_inasist] = []
        mock_cache['compensaciones'][f_inasist].append(row_dict)
        
    # C. Jornadas Especiales
    ayer_ini = (datetime.strptime(fecha_inicio, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    q_je = """
        SELECT * FROM jornadas_especiales
        WHERE empleado_id = ?
          AND fecha BETWEEN ? AND ?
    """
    je_rows = await db.fetch_all(q_je, (empleado_id, ayer_ini, fecha_fin))
    for row in je_rows:
        mock_cache['jornadas_especiales'][row['fecha']] = dict(row)
        
    # D. Horas Extras
    q_he = """
        SELECT * FROM horas_extras
        WHERE empleado_id = ?
          AND fecha BETWEEN ? AND ?
    """
    he_rows = await db.fetch_all(q_he, (empleado_id, fecha_inicio, fecha_fin))
    for row in he_rows:
        mock_cache['horas_extras'][row['fecha']] = dict(row)
        
    t1_bulk = time.time()
    duracion_bulk_fetch = t1_bulk - t0_bulk
    print(f"Datos precargados en memoria en: {duracion_bulk_fetch:.3f} segundos")
    print(f"   -> Intercambios: {len(mock_cache['intercambios'])}")
    print(f"   -> Compensaciones: {len(mock_cache['compensaciones'])}")
    print(f"   -> Jornadas Especiales: {len(mock_cache['jornadas_especiales'])}")
    print(f"   -> Horas Extras: {len(mock_cache['horas_extras'])}")
    
    # 3. Aplicar parches (Monkey-Patching de repositorio y DB)
    orig_get_intercambio = service.repository.get_intercambio_por_fecha
    orig_get_compensacion = service.repository.get_compensacion_por_fecha
    orig_get_estado_previo = service.he_repo.get_estado_previo
    orig_fetch_one = service.repository.db.fetch_one
    
    async def mock_get_intercambio(emp_id, fecha):
        return mock_cache['intercambios'].get(fecha)
        
    async def mock_get_compensacion(emp_id, fecha):
        return mock_cache['compensaciones'].get(fecha, [])
        
    async def mock_get_estado_previo(emp_id, fecha):
        return mock_cache['horas_extras'].get(fecha)
        
    async def mock_fetch_one(query, params=None):
        if "jornadas_especiales" in query and params:
            fecha_param = params[1]
            return mock_cache['jornadas_especiales'].get(fecha_param)
        return await orig_fetch_one(query, params)
        
    # Injectar parches
    service.repository.get_intercambio_por_fecha = mock_get_intercambio
    service.repository.get_compensacion_por_fecha = mock_get_compensacion
    service.he_repo.get_estado_previo = mock_get_estado_previo
    service.repository.db.fetch_one = mock_fetch_one
    
    # 4. Medir corrida OPTIMIZADA (en memoria)
    print(f"\nEjecutando version OPTIMIZADA para Empleado ID {empleado_id}...")
    t0_opt = time.time()
    res_opt = await service.reprocesar_periodo_empleado(
        empleado_id=empleado_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        force=True,
        collect_only=True
    )
    t1_opt = time.time()
    duracion_opt = t1_opt - t0_opt
    print(f"Version OPTIMIZADA completada en: {duracion_opt:.3f} segundos")
    
    # 5. Restaurar métodos originales
    service.repository.get_intercambio_por_fecha = orig_get_intercambio
    service.repository.get_compensacion_por_fecha = orig_get_compensacion
    service.he_repo.get_estado_previo = orig_get_estado_previo
    service.repository.db.fetch_one = orig_fetch_one
    
    # 6. Comparar exactitud lógica
    print("\nValidando exactitud de resultados...")
    fingerprint_orig = [r.get('estado') for r in res_orig.get('_collect', [])]
    fingerprint_opt = [r.get('estado') for r in res_opt.get('_collect', [])]
    
    match = fingerprint_orig == fingerprint_opt
    if match:
        print("Los resultados logicos son 100% identicos.")
    else:
        print("Se detectaron discrepancias en los resultados:")
        for idx, (o, p) in enumerate(zip(fingerprint_orig, fingerprint_opt)):
            if o != p:
                f_str = res_orig.get('_collect', [])[idx]['fecha']
                print(f"   -> Fecha {f_str}: Original={o} | Optimizado={p}")
                
    # 7. Informe de Tiempos
    total_dias = (datetime.strptime(fecha_fin, "%Y-%m-%d") - datetime.strptime(fecha_inicio, "%Y-%m-%d")).days + 1
    factor = duracion_orig / (duracion_opt + duracion_bulk_fetch) if (duracion_opt + duracion_bulk_fetch) > 0 else 0
    ahorro_pct = ((duracion_orig - (duracion_opt + duracion_bulk_fetch)) / duracion_orig) * 100
    
    print("\nREPORTE COMPARATIVO DE RENDIMIENTO:")
    print("----------------------------------------------------------------------")
    print(f"Periodo Procesado          : {total_dias} dias")
    print(f"Tiempo Version ORIGINAL    : {duracion_orig:.4f} segundos (~{duracion_orig/total_dias*1000:.1f}ms por dia)")
    print(f"Tiempo Pre-carga (RAM)     : {duracion_bulk_fetch:.4f} segundos")
    print(f"Tiempo Version OPTIMIZADA  : {duracion_opt:.4f} segundos (~{duracion_opt/total_dias*1000:.1f}ms por dia)")
    print(f"Tiempo Total Opt. (con bulk): {duracion_opt + duracion_bulk_fetch:.4f} segundos")
    print("----------------------------------------------------------------------")
    print(f"FACTOR DE ACELERACION      : {factor:.2f}x de velocidad")
    print(f"AHORRO DE TIEMPO           : {ahorro_pct:.1f}% menos tiempo")
    print("======================================================================\n")
    
    # Desconectar db
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(run_simulation())
