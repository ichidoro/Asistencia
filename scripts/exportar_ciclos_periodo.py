"""Exporta (SOLO LECTURA) los datos necesarios para repetir fuera de línea el cálculo de los Ciclos Inteligentes de un rango.

Uso (en el servidor, con el .env cargado):
    python scripts/exportar_ciclos_periodo.py 2026-10-01 2026-10-14
    python scripts/exportar_ciclos_periodo.py 2026-10-01 2026-10-14 --salida /tmp/octubre.json --con-nombres

Escribe un JSON con: ajustes de asistencia, feriados, turnos CICLO_INTELIGENTE con todas sus opciones (turno_dias), asignaciones,
marcas del reloj (con el tipo ya corregido por una persona, si lo hubo), lo que hoy dice la tabla `asistencias`, justificaciones de día,
intercambios y compensaciones. Por defecto NO incluye nombres ni RUT: solo ids de empleado (`--con-nombres` agrega nombre y apellidos).

Solo ejecuta SELECT: no modifica nada.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath('.'))
import dotenv

dotenv.load_dotenv()
from backend.core.database import Database  # noqa: E402
from backend.repositories.asistencia import AsistenciaRepository, LOGS_CON_TIPO_CORREGIDO  # noqa: E402

VERSION_FORMATO = 1


def _json_default(o: Any) -> Any:
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


def _trozos(items: List[Any], n: int = 400):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _dias(fecha: str, delta: int) -> str:
    return (datetime.strptime(fecha, "%Y-%m-%d") + timedelta(days=delta)).strftime("%Y-%m-%d")


async def exportar(db: Any, desde: str, hasta: str, con_nombres: bool = False) -> Dict[str, Any]:
    repo = AsistenciaRepository(db)
    datos: Dict[str, Any] = {
        "meta": {"formato": VERSION_FORMATO, "exportado_en": datetime.now().isoformat(timespec="seconds"),
                 "desde": desde, "hasta": hasta, "con_nombres": bool(con_nombres)},
    }

    datos["ajustes"] = [dict(r) for r in await db.fetch_all(
        "SELECT clave, valor FROM ajustes WHERE clave LIKE ?", ("asistencia_%",))]
    datos["feriados"] = [dict(r) for r in await db.fetch_all(
        "SELECT fecha, descripcion FROM feriados WHERE fecha BETWEEN ? AND ? ORDER BY fecha", (_dias(desde, -2), _dias(hasta, 3)))]

    # Turnos de Ciclo Inteligente con todas sus opciones (num_semana → día de la semana → configuración del día)
    turnos = [dict(r) for r in await db.fetch_all(
        "SELECT * FROM turnos WHERE tipo_programacion = ? ORDER BY id", ("CICLO_INTELIGENTE",))]
    for t in turnos:
        t["opciones"] = await repo.get_turno_dias_map(t["id"])
    datos["turnos"] = turnos
    ids_turno = [t["id"] for t in turnos]

    # Asignaciones que tocan el rango, solo de esos turnos
    asignaciones: List[Dict[str, Any]] = []
    for lote in _trozos(ids_turno):
        marcas = ",".join("?" * len(lote))
        asignaciones += [dict(r) for r in await db.fetch_all(
            f"SELECT id, empleado_id, turno_id, fecha_inicio, fecha_fin, semana_inicio FROM asignacion_turnos "
            f"WHERE turno_id IN ({marcas}) AND fecha_inicio <= ? AND (fecha_fin IS NULL OR fecha_fin >= ?)",
            tuple(lote) + (hasta, desde))]
    datos["asignaciones"] = asignaciones
    emp_ids = sorted({a["empleado_id"] for a in asignaciones})

    if con_nombres:
        nombres: List[Dict[str, Any]] = []
        for lote in _trozos(emp_ids):
            marcas = ",".join("?" * len(lote))
            nombres += [dict(r) for r in await db.fetch_all(
                f"SELECT id, nombre, apellido_paterno, apellido_materno FROM empleados WHERE id IN ({marcas})", tuple(lote))]
        datos["empleados"] = nombres
    else:
        datos["empleados"] = [{"id": i} for i in emp_ids]

    # Marcas: ventana segura que usa el motor (día anterior a día siguiente) ampliada un día más por los turnos nocturnos
    logs: List[Dict[str, Any]] = []
    asistencias: List[Dict[str, Any]] = []
    justificaciones: List[Dict[str, Any]] = []
    compensaciones: List[Dict[str, Any]] = []
    for lote in _trozos(emp_ids):
        marcas = ",".join("?" * len(lote))
        logs += [dict(r) for r in await db.fetch_all(
            f"SELECT id, empleado_id, fecha_hora, tipo, tipo_original, manual, observaciones FROM {LOGS_CON_TIPO_CORREGIDO} "
            f"WHERE empleado_id IN ({marcas}) AND fecha_hora BETWEEN ? AND ? ORDER BY empleado_id, fecha_hora",
            tuple(lote) + (f"{_dias(desde, -1)} 00:00:00", f"{_dias(hasta, 2)} 23:59:59"))]
        asistencias += [dict(r) for r in await db.fetch_all(
            f"SELECT * FROM asistencias WHERE empleado_id IN ({marcas}) AND fecha BETWEEN ? AND ? ORDER BY empleado_id, fecha",
            tuple(lote) + (desde, hasta))]
        justificaciones += [dict(r) for r in await db.fetch_all(
            f"SELECT j.id, j.empleado_id, j.tipo_id, t.nombre AS tipo_nombre, j.fecha_inicio, j.fecha_fin "
            f"FROM justificaciones j JOIN justificacion_tipos t ON j.tipo_id = t.id "
            f"WHERE j.empleado_id IN ({marcas}) AND j.fecha_inicio <= ? AND j.fecha_fin >= ?",
            tuple(lote) + (hasta, desde))]
        compensaciones += [dict(r) for r in await db.fetch_all(
            f"SELECT empleado_id, fecha_inasistencia, minutos FROM compensaciones_he_inasistencia "
            f"WHERE empleado_id IN ({marcas}) AND fecha_inasistencia BETWEEN ? AND ?",
            tuple(lote) + (desde, hasta))]
    datos["marcas"] = logs
    datos["asistencias"] = asistencias
    datos["justificaciones"] = justificaciones
    datos["compensaciones"] = compensaciones

    datos["intercambios"] = [dict(r) for r in await db.fetch_all(
        "SELECT empleado_solicitante_id, empleado_receptor_id, fecha_origen, fecha_destino, estado FROM intercambios_dias "
        "WHERE (fecha_origen BETWEEN ? AND ?) OR (fecha_destino BETWEEN ? AND ?)", (desde, hasta, desde, hasta))]

    datos["meta"]["conteos"] = {k: len(datos[k]) for k in
                                ("ajustes", "feriados", "turnos", "asignaciones", "empleados", "marcas", "asistencias",
                                 "justificaciones", "compensaciones", "intercambios")}
    return datos


async def main() -> None:
    ap = argparse.ArgumentParser(description="Exporta (solo lectura) datos de Ciclo Inteligente para simular fuera de línea.")
    ap.add_argument("desde", help="Fecha inicial AAAA-MM-DD")
    ap.add_argument("hasta", help="Fecha final AAAA-MM-DD")
    ap.add_argument("--salida", help="Archivo de salida (por defecto exportacion_ciclos_<desde>_<hasta>.json)")
    ap.add_argument("--con-nombres", action="store_true", help="Incluye nombre y apellidos (por defecto solo ids)")
    args = ap.parse_args()
    for f in (args.desde, args.hasta):
        datetime.strptime(f, "%Y-%m-%d")
    if args.desde > args.hasta:
        sys.exit("«desde» no puede ser posterior a «hasta».")

    db = Database()
    await db.connect()
    try:
        datos = await exportar(db, args.desde, args.hasta, args.con_nombres)
    finally:
        await db.disconnect()

    salida = args.salida or f"exportacion_ciclos_{args.desde}_{args.hasta}.json"
    with open(salida, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, default=_json_default)
    print(f"Listo: {salida} ({os.path.getsize(salida) / 1024:.0f} KB)")
    for k, v in datos["meta"]["conteos"].items():
        print(f"   {k:16s} {v}")
    if not args.con_nombres:
        print("El archivo no incluye nombres ni RUT (solo ids de empleado).")


if __name__ == "__main__":
    asyncio.run(main())
