import asyncio
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.abspath(".venv/Lib/site-packages"))
sys.path.insert(0, os.path.abspath("."))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import dotenv
dotenv.load_dotenv()

from backend.core.database import TursoDatabase
from backend.repositories.asistencia import AsistenciaRepository
from backend.services.asistencia_service import AsistenciaService

async def main():
    print("=" * 80)
    print("EJECUTANDO REPROCESO OFICIAL DE MANTENCION EN TURSO CLOUD DB")
    print("=" * 80)

    db = TursoDatabase()
    await db.connect()

    repo = AsistenciaRepository(db)
    service = AsistenciaService(repo)

    fecha_inicio = "2026-08-26"
    fecha_fin = "2026-09-25"

    mantencion_emp_ids = [36, 37, 38, 39, 170]

    for eid in mantencion_emp_ids:
        emp = await db.fetch_one("SELECT nombre, apellido_paterno FROM empleados WHERE id = ?", (eid,))
        name = f"{emp['nombre']} {emp['apellido_paterno']}"
        print(f"\n[INFO] Reprocesando empleado ID {eid}: {name} ({fecha_inicio} al {fecha_fin})...")
        
        # force=False to protect [VALIDADO] overrides
        res = await service.reprocesar_periodo_empleado(
            empleado_id=eid,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            force=False
        )
        print(f"[OK] Empleado {eid} ({name}) completado con exito: {res.get('dias_procesados', 0)} dias procesados.")

    print("\n" + "=" * 80)
    print("VERIFICACION INMEDIATA DE CASOS CRITICOS EN TURSO DB TRAS REPROCESO")
    print("=" * 80)

    # 1. Verificar Mauricio Riquelme en 04-Sep, 05-Sep, 06-Sep, 13-Sep
    for f in ['2026-09-04', '2026-09-05', '2026-09-06', '2026-09-13', '2026-09-14']:
        row = await repo.get_asistencia(170, f)
        je = await db.fetch_one("SELECT * FROM jornadas_especiales WHERE empleado_id = 170 AND fecha = ?", (f,))
        print(f"Mauricio Riquelme {f}: Estado={row.get('estado')}, Trab={row.get('horas_trabajadas')}h, Deuda={row.get('minutos_deuda')}m, Sem={row.get('num_semana_ganadora')}")
        if je:
            print(f"   -> J.Especial: {je.get('estado')}, {je.get('minutos_trabajados')} min ({je.get('origen')}) - {je.get('observaciones')}")
        else:
            print(f"   -> J.Especial: Ninguna (Limpio)")

    # 2. Verificar Orlando Carreno en 29-Ago
    row_oc = await repo.get_asistencia(37, '2026-08-29')
    je_oc = await db.fetch_one("SELECT * FROM jornadas_especiales WHERE empleado_id = 37 AND fecha = '2026-08-29'")
    print(f"\nOrlando Carreno 2026-08-29: Estado={row_oc.get('estado')}, Trab={row_oc.get('horas_trabajadas')}h, Deuda={row_oc.get('minutos_deuda')}m, Sem={row_oc.get('num_semana_ganadora')}")
    if je_oc:
        print(f"   -> J.Especial: {je_oc.get('estado')}, {je_oc.get('minutos_trabajados')} min ({je_oc.get('origen')})")
    else:
        print(f"   -> J.Especial: Ninguna (Limpio)")

    print("\n" + "=" * 80)
    print("REPROCESO DE MANTENCION CONCLUIDO EXITOSAMENTE EN BASE DE DATOS")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
