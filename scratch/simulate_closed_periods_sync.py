"""
Simulation Script: BioAlba Sync Optimization & SSE Stream
Verifica el comportamiento del plan de optimización de tramos cerrados y simula la emisión de SSE.
"""

import asyncio
import json
from datetime import datetime, timedelta

# Mock de base de datos y estados
class MockDB:
    def __init__(self, closures, active_employees):
        self.closures = closures
        self.active_employees = active_employees

    async def get_closed_pairs(self, fecha_inicio, fecha_fin, ruts):
        # Simula el cálculo de combinaciones cerradas
        closed_pairs = set()
        dt_ini = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        dt_fin = datetime.strptime(fecha_fin, "%Y-%m-%d")
        
        # Generar lista de días
        days = []
        curr = dt_ini
        while curr <= dt_fin:
            days.append(curr.strftime("%Y-%m-%d"))
            curr += timedelta(days=1)

        for emp in self.active_employees:
            rut = emp["rut"]
            area = emp["area"]
            for day in days:
                # Verificar si el día está cerrado para esta área
                for cl in self.closures:
                    if cl["area"] == area and cl["fecha_inicio"] <= day <= cl["fecha_fin"]:
                        closed_pairs.add((rut, day))
                        break
        return closed_pairs, len(self.active_employees) * len(days)

# Mock de progreso de sincronización
async def simulate_sync_process(db_mock, fecha_inicio, fecha_fin, ruts, callback):
    # Paso 1: Inicialización
    await callback("start", {"info": "Verificando períodos cerrados..."})
    await asyncio.sleep(0.5)

    closed_pairs, total_comb = await db_mock.get_closed_pairs(fecha_inicio, fecha_fin, ruts)
    
    # Simulación de Early Exit
    if len(closed_pairs) == total_comb:
        await callback("error", {"message": "El período seleccionado está completamente cerrado. Sync abortado."})
        return

    if len(closed_pairs) > 0:
        pct_closed = round((len(closed_pairs) / total_comb) * 100)
        await callback("info", {"message": f"Período parcialmente cerrado ({pct_closed}% de días cerrados omitidos)."})

    # Paso 2: Descarga de BioAlba
    # Determinamos los meses a descargar
    dt_ini = datetime.strptime(fecha_inicio, "%Y-%m-%d")
    dt_fin = datetime.strptime(fecha_fin, "%Y-%m-%d")
    meses = set()
    curr = dt_ini
    while curr <= dt_fin:
        meses.add((curr.year, curr.month))
        curr += timedelta(days=1)

    for anio, mes in sorted(list(meses)):
        await callback("progress", {
            "stage": "download",
            "info": f"Descargando BioAlba: {anio}-{mes:02d}...",
            "mes": mes,
            "anio": anio
        })
        await asyncio.sleep(1.0) # Simula descarga de red

    # Paso 3: Procesamiento local y recalculo
    employees_to_recalc = [emp for emp in db_mock.active_employees if emp["rut"] in ruts]
    await callback("start_recalc", {"total": len(employees_to_recalc)})
    await asyncio.sleep(0.5)

    for idx, emp in enumerate(employees_to_recalc, start=1):
        # Simular recálculo del empleado
        await callback("progress", {
            "stage": "recalc",
            "idx": idx,
            "total": len(employees_to_recalc),
            "info": f"Recalculando asistencia: {emp['nombre']}",
            "nombre": emp["nombre"]
        })
        await asyncio.sleep(0.4) # Simula procesamiento de reglas

    # Finalizar
    await callback("done", {
        "marcaciones_nuevas": 12,
        "dias_recalculados": len(employees_to_recalc) * len(meses) * 30,
        "bloqueados_por_cierre": len(closed_pairs)
    })

# Caso de prueba
async def main():
    # 1. Definir cierres
    closures = [
        {"area": "PRODUCCION", "fecha_inicio": "2026-05-01", "fecha_fin": "2026-05-25"},
        {"area": "ADMINISTRACION", "fecha_inicio": "2026-05-01", "fecha_fin": "2026-05-15"}
    ]
    # 2. Empleados
    employees = [
        {"rut": "11111111", "nombre": "Juan Pérez", "area": "PRODUCCION"},
        {"rut": "22222222", "nombre": "Ana López", "area": "ADMINISTRACION"},
        {"rut": "33333333", "nombre": "Carlos Rojas", "area": "PRODUCCION"}
    ]

    db_mock = MockDB(closures, employees)

    # Callback simulador de SSE en consola
    async def sse_callback(event_type, data):
        print(f"event: {event_type}")
        print(f"data: {json.dumps(data)}")
        print()

    print("--- SIMULACIÓN 1: Rango Parcialmente Cerrado ---")
    ruts_to_sync = ["11111111", "22222222"]
    await simulate_sync_process(db_mock, "2026-05-20", "2026-05-28", ruts_to_sync, sse_callback)

    print("\n--- SIMULACIÓN 2: Rango Totalmente Cerrado (Early Exit) ---")
    # Para PRODUCCION y rango 2026-05-10 al 20-05
    await simulate_sync_process(db_mock, "2026-05-10", "2026-05-20", ["11111111"], sse_callback)

if __name__ == "__main__":
    asyncio.run(main())
