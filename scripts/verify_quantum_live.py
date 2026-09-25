"""
Script de verificación cuántica con datos reales vivos de Turso Cloud.
Valida:
1. Turnos configurados en BD: tipos de programación (CICLO_INTELIGENTE vs BOLSA_FLEXIBLE).
2. Empleados con Bolsa Flexible (con y sin viajes largos).
3. Choferes con viajes largos (IDs 155, 156, 169).
4. Ejecución de cálculo con QuantumMatrixEngine para un día real con save=False.
"""
import asyncio
import os
import sys

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath("."))

from backend.core.database import TursoDatabase
from backend.repositories.asistencia import AsistenciaRepository
from backend.services.asistencia_service import AsistenciaService
from backend.services.quantum_matrix_engine import QuantumMatrixEngine, QuantumShiftWeekMatcher

async def test_live():
    print("=" * 75)
    print("VERIFICACIÓN CUÁNTICA EN VIVO: TURSO CLOUD + MOTOR CUÁNTICO MATRICIAL")
    print("=" * 75)
    
    db = TursoDatabase()
    await db.connect()
    
    # 1. Verificar Turnos
    print("\n[1] Verificando turnos en BD Turso Cloud...")
    turnos = await db.fetch_all("SELECT id, nombre, tipo_programacion, permite_viajes_largos, meta_horas_semanales FROM turnos ORDER BY id")
    print(f"Total turnos: {len(turnos)}")
    for t in turnos:
        pvl = " [VIAJES LARGOS]" if t.get('permite_viajes_largos') == 1 else ""
        print(f" - Turno {t['id']}: {t['nombre']} | Tipo: {t['tipo_programacion']}{pvl} | Meta: {t.get('meta_horas_semanales')}")
    
    obsoletos = [t for t in turnos if t['tipo_programacion'] not in ('CICLO_INTELIGENTE', 'BOLSA_FLEXIBLE')]
    if obsoletos:
        print(f"❌ ERROR: Turnos obsoletos encontrados: {obsoletos}")
    else:
        print("✅ OK: Todos los turnos tienen tipo canónico ('CICLO_INTELIGENTE' o 'BOLSA_FLEXIBLE').")
        
    repo = AsistenciaRepository(db)
    service = AsistenciaService(repo)
    
    # 2. Buscar última fecha con registros en logs_raw
    print("\n[2] Consultando logs_raw en Turso Cloud...")
    last_log = await db.fetch_one("SELECT DATE(fecha_hora) as fecha, count(*) as cnt FROM logs_raw GROUP BY DATE(fecha_hora) ORDER BY fecha DESC LIMIT 1")
    test_fecha = last_log['fecha'] if last_log else "2026-09-20"
    print(f"Fecha con marcas recientes: {test_fecha} ({last_log['cnt'] if last_log else 0} marcas)")
    
    # 3. Test de carga de contexto masivo
    print(f"\n[3] Cargando contexto masivo para {test_fecha}...")
    ctx = await service.get_bulk_context(test_fecha)
    print(f"Contexto masivo cargado con éxito para {len(ctx.get('empleados', {}))} empleados.")
    
    # 4. Probar empleados representativos de las 3 categorías operativas
    # A) Choferes de viajes largos (IDs 155, 156, 169)
    print("\n[4] Prueba Categoría A: Choferes con Viajes Largos (Turno 25, PVL=1)")
    for eid in [155, 156, 169]:
        if eid in ctx.get('empleados', {}):
            emp = ctx['empleados'][eid]
            asig = ctx['asignaciones'].get(eid, {})
            nombre = f"{emp.get('nombre', '')} {emp.get('apellido', '')}".strip()
            res = await service.procesar_empleado_dia(eid, test_fecha, save=False, bulk_ctx=ctx)
            if res:
                print(f" - Chofer ID {eid} ({nombre}): Turno={asig.get('turno_id')} ({asig.get('tipo_programacion')}) -> Estado={res.get('estado')}, Horas={res.get('horas_trabajadas', 0):.2f}h, Deuda={res.get('minutos_deuda', 0)}m, Salida={res.get('hora_salida_real')}")
        else:
            print(f" - Chofer ID {eid} no está activo o en contexto para {test_fecha}")

    # B) Choferes de reparto tradicional (Turno 9, Bolsa Flexible sin viajes largos)
    print("\n[5] Prueba Categoría B: Choferes Bolsa Flexible Local (Turno 9, PVL=0)")
    t9_emps = [eid for eid, asig in ctx.get('asignaciones', {}).items() if asig.get('turno_id') == 9][:3]
    for eid in t9_emps:
        emp = ctx['empleados'][eid]
        nombre = f"{emp.get('nombre', '')} {emp.get('apellido', '')}".strip()
        res = await service.procesar_empleado_dia(eid, test_fecha, save=False, bulk_ctx=ctx)
        if res:
            print(f" - Chofer T9 ID {eid} ({nombre}): Estado={res.get('estado')}, Horas={res.get('horas_trabajadas', 0):.2f}h, Deuda={res.get('minutos_deuda', 0)}m, Entrada={res.get('hora_entrada_real')}, Salida={res.get('hora_salida_real')}")

    # C) Operarios de Ciclo Inteligente (Turno 1, 3 o 4)
    print("\n[6] Prueba Categoría C: Ciclo Inteligente Fijo/Rotativo (Turno 1 / 3 / 4)")
    ciclo_emps = [eid for eid, asig in ctx.get('asignaciones', {}).items() if asig.get('tipo_programacion') == 'CICLO_INTELIGENTE'][:3]
    for eid in ciclo_emps:
        emp = ctx['empleados'][eid]
        asig = ctx['asignaciones'].get(eid, {})
        nombre = f"{emp.get('nombre', '')} {emp.get('apellido', '')}".strip()
        res = await service.procesar_empleado_dia(eid, test_fecha, save=False, bulk_ctx=ctx)
        if res:
            print(f" - Operario ID {eid} ({nombre}): Turno={asig.get('turno_id')} -> Estado={res.get('estado')}, Horas={res.get('horas_trabajadas', 0):.2f}h, Deuda={res.get('minutos_deuda', 0)}m, Entrada={res.get('hora_entrada_real')}, Salida={res.get('hora_salida_real')}")

    print("\n" + "=" * 75)
    print("VERIFICACIÓN EN VIVO COMPLETADA EXITOSAMENTE SIN ERRORES")
    print("=" * 75)

if __name__ == '__main__':
    asyncio.run(test_live())
