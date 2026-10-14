"""Horas en planta de un empleado con Artículo 22, día a día desde su primera marca (SOLO LECTURA).

Usa la misma regla que el historial del módulo: por día, cada ENTRADA seguida de una SALIDA suma su
diferencia (si la salida es menor, cruzó la medianoche). Las salidas de turnos que cruzan medianoche
están guardadas con la fecha de la entrada, por lo que la sesión se atribuye al día en que empezó.
Los meses sin marcas no aparecen. Los días con una entrada sin salida (o al revés) se avisan y suman 0.

Uso:  python scripts/horas_art22_empleado.py "Willy" "Orellana" [salida.csv]
"""
import asyncio
import csv
import os
import sys
from collections import OrderedDict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath('.'))
import dotenv
dotenv.load_dotenv()
from backend.core.database import Database


def _hm(minutos):
    m = int(round(minutos))
    return f"{m // 60}h {m % 60:02d}m"


async def main():
    nombre = sys.argv[1] if len(sys.argv) > 1 else "Willy"
    apellido = sys.argv[2] if len(sys.argv) > 2 else "Orellana"
    salida_csv = sys.argv[3] if len(sys.argv) > 3 else "horas_art22.csv"
    db = Database()
    await db.connect()
    emps = await db.fetch_all(
        """SELECT id, nombre, apellido_paterno, apellido_materno, excluido_asistencia FROM empleados
           WHERE lower(nombre) LIKE ? AND lower(apellido_paterno) LIKE ?""",
        (f"%{nombre.lower()}%", f"%{apellido.lower()}%"))
    if not emps:
        print("No se encontró el empleado.")
        return
    if len(emps) > 1:
        print("Hay varios empleados con ese nombre; ajusta los parámetros:")
        for e in emps:
            print("  ", e['id'], e['nombre'], e['apellido_paterno'], e['apellido_materno'], "art22" if e['excluido_asistencia'] else "")
        return
    e = emps[0]
    print(f"Empleado: {e['nombre']} {e['apellido_paterno']} {e['apellido_materno']} (id {e['id']})"
          + ("" if e['excluido_asistencia'] else "  ⚠ no figura con Artículo 22"))

    marcas = await db.fetch_all(
        "SELECT fecha, hora, tipo FROM articulo22_registros WHERE empleado_id = ? ORDER BY fecha, id", (e['id'],))
    if not marcas:
        print("Sin marcas en el módulo Artículo 22.")
        return
    por_dia = OrderedDict()
    for m in marcas:
        por_dia.setdefault(m['fecha'], []).append(dict(m))

    filas, meses = [], OrderedDict()
    for fecha, ms in por_dia.items():
        mins, i, aviso = 0.0, 0, ""
        while i < len(ms):
            if ms[i]['tipo'] == 'E' and i + 1 < len(ms) and ms[i + 1]['tipo'] == 'S':
                a = datetime.strptime(ms[i]['hora'], "%H:%M:%S")
                b = datetime.strptime(ms[i + 1]['hora'], "%H:%M:%S")
                if b < a:
                    b += timedelta(days=1)
                mins += (b - a).total_seconds() / 60
                i += 2
            else:
                aviso = "marca sin par (entrada sin salida o salida sin entrada)"
                i += 1
        ents = [m['hora'] for m in ms if m['tipo'] == 'E']
        sals = [m['hora'] for m in ms if m['tipo'] == 'S']
        filas.append((fecha, ents[0] if ents else "", sals[-1] if sals else "", len(ms), round(mins, 1), aviso))
        meses.setdefault(fecha[:7], []).append(mins)

    primera = filas[0][0]
    print(f"Primera marca: {primera}  |  Última: {filas[-1][0]}  |  Días con marcas: {len(filas)}\n")
    mes_actual = None
    for f in filas:
        if f[0][:7] != mes_actual:
            mes_actual = f[0][:7]
            print(f"── {mes_actual} ──")
        print(f"  {f[0]}  entrada {f[1] or '--:--:--'}  salida {f[2] or '--:--:--'}  marcas {f[3]}  → {_hm(f[4])}"
              + (f"   ⚠ {f[5]}" if f[5] else ""))
    print("\nResumen por mes (solo meses con marcas):")
    total = 0.0
    for mes, lst in meses.items():
        s = sum(lst)
        total += s
        print(f"  {mes}: {len(lst)} días, {_hm(s)}")
    print(f"\nTOTAL desde {primera}: {_hm(total)}  ({total / 60:.1f} horas) en {len(filas)} días")
    with open(salida_csv, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["fecha", "primera_entrada", "ultima_salida", "marcas", "minutos", "horas", "aviso"])
        for f in filas:
            w.writerow([f[0], f[1], f[2], f[3], f[4], round(f[4] / 60, 2), f[5]])
    print(f"CSV: {salida_csv}")
    await db.disconnect()


asyncio.run(main())
