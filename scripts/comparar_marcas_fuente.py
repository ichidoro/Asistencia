"""Compara las marcas de UN empleado en un rango entre EasyTime (origen) y la base local `logs_raw` (SOLO LECTURA).

Sirve para saber si una marca "faltante" nunca llegó a la base (p. ej. se perdió en una descarga antigua)
o si realmente el trabajador no la hizo. No escribe nada.

Uso:  python scripts/comparar_marcas_fuente.py "Carreño" 2026-10-01 2026-10-06
"""
import asyncio
import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath('.'))
import dotenv
dotenv.load_dotenv()
from backend.core.config import settings
from backend.core.database import Database
from backend.scraper.easytime_scraper import EasyTimeClient, _rut_limpio


async def main():
    ape = sys.argv[1] if len(sys.argv) > 1 else "Carreño"
    d0 = sys.argv[2] if len(sys.argv) > 2 else "2026-10-01"
    d1 = sys.argv[3] if len(sys.argv) > 3 else "2026-10-06"
    if not (settings.EASYTIME_URL and settings.EASYTIME_PASSWORD):
        print("Faltan EASYTIME_URL / EASYTIME_PASSWORD en el .env: ejecútalo en el servidor."); return
    db = Database()
    await db.connect()
    emps = await db.fetch_all(
        "SELECT id, rut, nombre, apellido_paterno FROM empleados WHERE lower(apellido_paterno) LIKE ? OR lower(nombre) LIKE ?",
        (f"%{ape.lower()}%", f"%{ape.lower()}%"))
    if len(emps) != 1:
        for e in emps:
            print(e['id'], e['rut'], e['nombre'], e['apellido_paterno'])
        print("→ ajusta el nombre para que quede un solo empleado"); return
    e = emps[0]
    rut = _rut_limpio(e['rut'])
    print(f"Empleado {e['id']} {e['nombre']} {e['apellido_paterno']} (RUT {rut})  {d0} → {d1}")

    cli = EasyTimeClient(settings.EASYTIME_URL, settings.EASYTIME_USER, settings.EASYTIME_PASSWORD)
    fuente = {}
    a, m = date.fromisoformat(d0), date.fromisoformat(d1)
    cur = date(a.year, a.month, 1)
    while cur <= m:
        for x in await cli.fetch_marcaciones(cur.year, cur.month, rut_filter=rut, desde=d0, hasta=d1):
            fuente[x['fecha_hora']] = x
        cur = date(cur.year + (cur.month == 12), (cur.month % 12) + 1, 1)

    local = {r['fecha_hora']: dict(r) for r in await db.fetch_all(
        "SELECT id, fecha_hora, tipo FROM logs_raw WHERE empleado_id = ? AND fecha_hora BETWEEN ? AND ?",
        (e['id'], d0 + " 00:00:00", d1 + " 23:59:59"))}

    print(f"\nEasyTime: {len(fuente)} marcas | base local: {len(local)} marcas")
    faltan = sorted(set(fuente) - set(local))
    sobran = sorted(set(local) - set(fuente))
    print(f"\nEstán en EasyTime y NO en la base local ({len(faltan)}):")
    for f in faltan:
        print("   ", f, fuente[f]['tipo'], fuente[f]['equipo'])
    print(f"\nEstán en la base local y NO en EasyTime ({len(sobran)}):")
    for f in sobran:
        print("   ", f, local[f]['tipo'], '(posible ingreso manual)')
    print("\nDetalle por día (EasyTime):")
    dia = None
    for f in sorted(fuente):
        if f[:10] != dia:
            dia = f[:10]; print(" ", dia)
        print("     ", f[11:], fuente[f]['tipo'], '' if f in local else '   ← NO está en la base local')
    await db.disconnect()


asyncio.run(main())
