"""
Script de regularización puntual:
Replica las marcaciones de libreta Art. 25 bis (180h) de Juan Paredes hacia Enzo Donoso
para los días 2026-10-01 al 2026-10-05 que tengan registro en la libreta.
"""
import asyncio
import os
import sys
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.abspath('.'))

from backend.core.database import Database
from backend.repositories.asistencia import AsistenciaRepository
from backend.services.asistencia_service import AsistenciaService


async def main():
    db = Database()
    await db.connect()
    repo = AsistenciaRepository(db)
    service = AsistenciaService(repo)

    print("══════════════════════════════════════════════════════════════════════")
    print("  REPLICACIÓN DE LIBRETA ART. 25 BIS: JUAN PAREDES ➔ ENZO DONOSO")
    print("  Período: 2026-10-01 al 2026-10-05")
    print("══════════════════════════════════════════════════════════════════════")

    # 1. Localizar empleados
    q_emp = "SELECT id, rut, nombre, apellido_paterno, apellido_materno FROM empleados WHERE nombre ILIKE ? OR (apellido_paterno || ' ' || COALESCE(apellido_materno, '') || ' ' || nombre) ILIKE ?"
    
    # Origen: Juan Paredes
    origen = await db.fetch_one(
        "SELECT id, rut, nombre, apellido_paterno, apellido_materno FROM empleados WHERE (nombre ILIKE '%JUAN%' AND (nombre ILIKE '%PAREDES%' OR apellido_paterno ILIKE '%PAREDES%')) LIMIT 1"
    )
    if not origen:
        # Fallback de búsqueda amplia
        origen = await db.fetch_one(
            "SELECT id, rut, nombre, apellido_paterno, apellido_materno FROM empleados WHERE nombre ILIKE '%PAREDES%' OR apellido_paterno ILIKE '%PAREDES%' LIMIT 1"
        )
    
    # Destino: Enzo Donoso
    destino = await db.fetch_one(
        "SELECT id, rut, nombre, apellido_paterno, apellido_materno FROM empleados WHERE (nombre ILIKE '%ENZO%' AND (nombre ILIKE '%DONOSO%' OR apellido_paterno ILIKE '%DONOSO%')) LIMIT 1"
    )
    if not destino:
        destino = await db.fetch_one(
            "SELECT id, rut, nombre, apellido_paterno, apellido_materno FROM empleados WHERE nombre ILIKE '%DONOSO%' OR apellido_paterno ILIKE '%DONOSO%' LIMIT 1"
        )

    if not origen:
        print("❌ Error: No se encontró al empleado origen (Juan Paredes) en la tabla empleados.")
        await db.disconnect()
        return

    if not destino:
        print("❌ Error: No se encontró al empleado destino (Enzo Donoso) en la tabla empleados.")
        await db.disconnect()
        return

    nom_origen = f"{origen.get('apellido_paterno', '')} {origen.get('nombre', '')}".strip()
    nom_destino = f"{destino.get('apellido_paterno', '')} {destino.get('nombre', '')}".strip()

    print(f"✅ Empleado Origen:  ID={origen['id']} | RUT={origen.get('rut')} | {nom_origen}")
    print(f"✅ Empleado Destino: ID={destino['id']} | RUT={destino.get('rut')} | {nom_destino}")
    print("──────────────────────────────────────────────────────────────────────")

    # 2. Consultar libretas de Juan Paredes en el rango 2026-10-01 al 2026-10-05
    f_ini = "2026-10-01"
    f_fin = "2026-10-05"
    q_lib = """
        SELECT * FROM libreta_art25bis_dias
        WHERE empleado_id = ? AND fecha BETWEEN ? AND ?
        ORDER BY fecha ASC
    """
    libretas_origen = await db.fetch_all(q_lib, (origen['id'], f_ini, f_fin))

    if not libretas_origen:
        print(f"⚠️ Aviso: Juan Paredes no tiene registros de libreta entre {f_ini} y {f_fin}.")
        await db.disconnect()
        return

    print(f"📋 Se encontraron {len(libretas_origen)} días con libreta en Juan Paredes:")
    for l in libretas_origen:
        h_cond = round(float(l.get('minutos_conduccion') or 0) / 60.0, 1)
        h_esp = round(float(l.get('minutos_espera') or 0) / 60.0, 1)
        h_aux = round(float(l.get('minutos_auxiliares') or 0) / 60.0, 1)
        h_efec = round(float(l.get('minutos_efectivos') or 0) / 60.0, 1)
        print(f"   • {l['fecha']}: {h_cond}h cond, {h_esp}h esp, {h_aux}h aux ➔ {h_efec}h efectivas (Cerrado: {l.get('cerrado')})")

    print("\n🔄 Replicando marcaciones hacia Enzo Donoso y recalculando...")

    q_upsert = """
        INSERT INTO libreta_art25bis_dias (
            empleado_id, fecha, slots_96, minutos_conduccion, minutos_espera,
            minutos_auxiliares, minutos_descanso, minutos_efectivos, cerrado,
            validador_id, observaciones, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(empleado_id, fecha) DO UPDATE SET
            slots_96 = excluded.slots_96,
            minutos_conduccion = excluded.minutos_conduccion,
            minutos_espera = excluded.minutos_espera,
            minutos_auxiliares = excluded.minutos_auxiliares,
            minutos_descanso = excluded.minutos_descanso,
            minutos_efectivos = excluded.minutos_efectivos,
            cerrado = excluded.cerrado,
            validador_id = excluded.validador_id,
            observaciones = excluded.observaciones,
            updated_at = CURRENT_TIMESTAMP
    """

    dias_replicados = 0
    for l in libretas_origen:
        fecha_dia = l['fecha']
        obs_replica = f"Copia autorizada libreta Art. 25 bis desde {nom_origen} (regularización excepcional)"
        params = (
            destino['id'],
            fecha_dia,
            l['slots_96'],
            l.get('minutos_conduccion', 0),
            l.get('minutos_espera', 0),
            l.get('minutos_auxiliares', 0),
            l.get('minutos_descanso', 0),
            l.get('minutos_efectivos', 0),
            l.get('cerrado', 0),
            l.get('validador_id'),
            obs_replica
        )
        await db.execute(q_upsert, params)

        # Recalcular inmediatamente en el motor para impactar la tabla asistencias
        try:
            res_calc = await service.procesar_empleado_dia(
                empleado_id=destino['id'],
                fecha=fecha_dia,
                save=True,
                force=True
            )
            est_res = res_calc.get('estado') if res_calc else 'OK'
            hrs_res = res_calc.get('horas_trabajadas') if res_calc else round(float(l.get('minutos_efectivos', 0)) / 60.0, 2)
            esp_res = res_calc.get('minutos_espera') if res_calc else l.get('minutos_espera', 0)
            print(f"   ✅ {fecha_dia}: Libreta replicada. Motor Asistencia ➔ Estado: {est_res}, {hrs_res}h efectivas, {round(float(esp_res)/60.0, 1)}h espera.")
            dias_replicados += 1
        except Exception as e_calc:
            print(f"   ⚠️ {fecha_dia}: Libreta replicada en BD pero error en recálculo: {e_calc}")

    print("──────────────────────────────────────────────────────────────────────")
    print(f"🎉 FINALIZADO: Se replicaron {dias_replicados} días con éxito a {nom_destino}.")
    print("══════════════════════════════════════════════════════════════════════")

    await db.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
