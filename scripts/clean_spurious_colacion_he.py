import asyncio
import os
import sys

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.abspath('.'))
from backend.core.database import get_db

async def clean_colacion_he():
    db = await get_db()
    print("=== Saneamiento de Horas Extras Espurias por Colacion Reducida ===")
    
    # 1 solo query con LEFT JOIN a asistencias y LEFT JOIN a jornadas_especiales
    query = """
        SELECT he.id, he.empleado_id, he.fecha, he.minutos_bruto, he.minutos_autorizados, he.estado, he.origen,
               e.nombre, e.apellido_paterno,
               a.minutos_extra_bruto as asist_bruto, a.estado as estado_asist,
               je.id as je_id, je.estado as je_estado, je.origen as je_origen
        FROM horas_extras he
        JOIN empleados e ON he.empleado_id = e.id
        LEFT JOIN asistencias a ON he.empleado_id = a.empleado_id AND he.fecha = a.fecha
        LEFT JOIN jornadas_especiales je ON he.empleado_id = je.empleado_id AND he.fecha = je.fecha
        WHERE he.fecha BETWEEN '2026-08-26' AND '2026-09-25'
    """
    rows = await db.fetch_all(query)
    print(f"Total registros en horas_extras para Septiembre: {len(rows)}")
    
    to_delete = []
    to_update = []
    
    for r in rows:
        eid = r['empleado_id']
        f = r['fecha']
        bruto_real = float(r.get('asist_bruto') or 0.0)
        he_bruto = float(r.get('minutos_bruto') or 0.0)
        auth = float(r.get('minutos_autorizados') or 0.0)
        origen = r.get('origen') or ''
        has_je = r.get('je_id') is not None
        
        # Si NO hay jornada especial y el origen no es COBERTURA_TURNO
        if not has_je and origen != 'COBERTURA_TURNO':
            # Caso A: En la asistencia el bruto real es 0.0, pero horas_extras tenia registro espurio por colacion reducida
            if bruto_real == 0.0 and he_bruto > 0:
                print(f"[ELIMINAR] HE espuria (bruto real 0.0): {r['nombre']} {r['apellido_paterno']} - {f} ({he_bruto}m, estado: {r['estado']})")
                to_delete.append(r['id'])
            # Caso B: Bruto real es positivo pero menor al bruto grabado (caso mixto: salida tardia + colacion reducida)
            elif bruto_real > 0 and (he_bruto > bruto_real or auth > bruto_real):
                nuevo_auth = min(auth, bruto_real) if r['estado'] == 'APROBADO' else 0
                print(f"[AJUSTAR] HE mixta: {r['nombre']} {r['apellido_paterno']} - {f} (bruto: {he_bruto}m -> {bruto_real}m, auth: {auth}m -> {nuevo_auth}m)")
                to_update.append((bruto_real, nuevo_auth, r['id']))

    # Ejecutar en batch
    for hid in to_delete:
        await db.execute("DELETE FROM horas_extras WHERE id = ?", (hid,))
    for bruto_val, auth_val, hid in to_update:
        await db.execute("UPDATE horas_extras SET minutos_bruto = ?, minutos_autorizados = ? WHERE id = ?", (bruto_val, auth_val, hid))
        
    await db.sync_to_cloud_explicit()
    print(f"\nResumen: {len(to_delete)} registros huerfanos eliminados, {len(to_update)} registros mixtos ajustados.")

if __name__ == '__main__':
    asyncio.run(clean_colacion_he())
