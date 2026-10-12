"""Simulación SOLO LECTURA: ¿a quién afectaría pagar automáticamente el turno nocturno de víspera de feriado?

Recorre las INASISTENCIAS ya registradas, busca las que caen el día anterior a un feriado y las separa en:
  - CAMBIARÍAN: turno nocturno (salida teórica <= entrada teórica) → pasarían a OK con el ajuste encendido.
  - NO CAMBIAN: turno diurno u otro caso → seguirían como inasistencia.
No escribe nada en la base de datos.

Uso:  python scripts/simular_vispera_feriado.py [dias_atras=365]
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath('.'))
import dotenv
dotenv.load_dotenv()
from backend.core.database import Database


def _min(h):
    try:
        p = str(h).split(':')
        return int(p[0]) * 60 + int(p[1])
    except Exception:
        return None


async def main():
    dias = int(sys.argv[1]) if len(sys.argv) > 1 else 365
    desde = (datetime.now() - timedelta(days=dias)).strftime('%Y-%m-%d')
    db = Database()
    await db.connect()
    fer = {r['fecha'][:10] for r in await db.fetch_all("SELECT fecha FROM feriados")}
    fer |= {f"{y}-01-01" for y in range(int(desde[:4]), datetime.now().year + 2)}
    filas = await db.fetch_all(
        """SELECT a.empleado_id, a.fecha, a.hora_entrada_teorica AS ent, a.hora_salida_teorica AS sal,
                  e.nombre, e.apellido_paterno
           FROM asistencias a JOIN empleados e ON e.id = a.empleado_id
           WHERE a.estado = 'INASISTENCIA' AND a.fecha >= ? ORDER BY a.fecha, e.apellido_paterno""", (desde,))
    cambian, no_cambian = [], []
    for r in filas:
        f = str(r['fecha'])[:10]
        sig = (datetime.strptime(f, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        if sig not in fer:
            continue
        ent, sal = _min(r['ent']), _min(r['sal'])
        noct = ent is not None and sal is not None and sal <= ent
        (cambian if noct else no_cambian).append((f, f"{r['nombre']} {r['apellido_paterno']}", r['ent'], r['sal']))
    print(f"INASISTENCIAS desde {desde}: {len(filas)} en total; en víspera de feriado: {len(cambian) + len(no_cambian)}")
    print(f"\nCAMBIARÍAN a OK (turno nocturno): {len(cambian)}")
    for x in cambian:
        print("  ", *x)
    print(f"\nNO CAMBIAN (turno diurno / sin horario): {len(no_cambian)}")
    for x in no_cambian:
        print("  ", *x)
    print("\nNota: es una estimación sobre lo ya registrado; las marcas reales no se tocan. "
          "Quien sí marcó nunca aparece aquí porque no es INASISTENCIA.")
    await db.disconnect()


asyncio.run(main())
