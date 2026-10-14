"""Diagnóstico SOLO LECTURA de un empleado con turno que cruza la noche (Ciclo Inteligente multi-semana).

Muestra: configuración de cada semana/ciclo del turno, marcas crudas, lo guardado en `asistencias`
(incluida la semana ganadora) y qué semana elegiría hoy el selector para cada día.

Uso:  python scripts/diagnostico_turno_noche.py "Carreño" "2026-10-03" "2026-10-08"
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath('.'))
import dotenv
dotenv.load_dotenv()
from backend.core.database import Database
from backend.repositories.asistencia import AsistenciaRepository
from backend.services.quantum_matrix_engine import QuantumShiftWeekMatcher


async def main():
    ape = sys.argv[1] if len(sys.argv) > 1 else "Carreño"
    d0 = sys.argv[2] if len(sys.argv) > 2 else "2026-10-03"
    d1 = sys.argv[3] if len(sys.argv) > 3 else "2026-10-08"
    db = Database()
    await db.connect()
    emps = await db.fetch_all(
        "SELECT id, nombre, apellido_paterno, apellido_materno FROM empleados WHERE lower(apellido_paterno) LIKE ? OR lower(nombre) LIKE ?",
        (f"%{ape.lower()}%", f"%{ape.lower()}%"))
    for e in emps:
        print("empleado", e['id'], e['nombre'], e['apellido_paterno'], e['apellido_materno'])
    if len(emps) != 1:
        print("→ ajusta el nombre para que quede un solo empleado"); return
    eid = emps[0]['id']

    # La asignación vigente la resuelve el servicio; aquí se listan los turnos "Mantencion" para ver sus ciclos.
    turnos = await db.fetch_all("SELECT id, nombre, tipo_programacion, anclaje_entrada_minutos, anclaje_salida_minutos FROM turnos WHERE lower(nombre) LIKE '%mantencion%'")
    repo = AsistenciaRepository(db)
    mapas = {}
    for t in turnos:
        print(f"\n── Turno {t['id']} «{t['nombre']}» ({t['tipo_programacion']}) anclaje ent/sal: {t['anclaje_entrada_minutos']}/{t['anclaje_salida_minutos']}")
        mapa = await repo.get_turno_dias_map(t['id'])
        mapas[t['id']] = mapa
        for sem, dias in sorted(mapa.items()):
            for dia, cfg in sorted(dias.items()):
                print(f"   semana {sem} día {dia}: {'LIBRE' if cfg.get('es_libre') else str(cfg.get('hora_entrada'))+' → '+str(cfg.get('hora_salida'))}"
                      f"  cruza_medianoche={cfg.get('cruza_medianoche')}")

    ini = (datetime.strptime(d0, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d") + " 00:00:00"
    fin = (datetime.strptime(d1, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d") + " 23:59:59"
    logs = await db.fetch_all("SELECT id, fecha_hora, tipo FROM logs_raw WHERE empleado_id = ? AND fecha_hora BETWEEN ? AND ? ORDER BY fecha_hora", (eid, ini, fin))
    print(f"\n── Marcas crudas {d0}..{d1} (±1 día)")
    for l in logs:
        print("  ", l['id'], l['fecha_hora'], l['tipo'])

    ras = await db.fetch_all("SELECT * FROM asistencias WHERE empleado_id = ? AND fecha BETWEEN ? AND ? ORDER BY fecha", (eid, d0, d1))
    print("\n── Guardado en asistencias")
    for r in ras:
        r = dict(r)
        print(f"   {r['fecha']} estado={r.get('estado')} E={r.get('hora_entrada_real')} S={r.get('hora_salida_real')} "
              f"teo={r.get('hora_entrada_teorica')}→{r.get('hora_salida_teorica')} semana={r.get('num_semana_ganadora')} "
              f"horas={r.get('horas_trabajadas')} origen={r.get('origen')} obs={str(r.get('observaciones'))[:110]!r}")

    aj = await db.fetch_all("SELECT clave, valor FROM ajustes WHERE clave LIKE 'asistencia_%'")
    print("\n── Ajustes de asistencia")
    for a in aj:
        print("  ", a['clave'], '=', a['valor'])

    if mapas:
        print("\n── Qué semana elegiría hoy el selector (por turno «mantencion»)")
        cur = datetime.strptime(d0, "%Y-%m-%d")
        fin_d = datetime.strptime(d1, "%Y-%m-%d")
        while cur <= fin_d:
            f = cur.strftime("%Y-%m-%d")
            ll = [dict(l) for l in logs]
            for tid, mapa in mapas.items():
                tot = max(mapa.keys()) if mapa else 1
                w = QuantumShiftWeekMatcher.resolve_winner_week(eid, f, cur, cur.weekday(), ll, mapa, tot)
                print(f"   {f} turno {tid}: semana {w}")
            cur += timedelta(days=1)
    await db.disconnect()


asyncio.run(main())
