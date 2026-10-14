"""Exporta (SOLO LECTURA) los turnos de Ciclo Inteligente tal como están en la app, para simularlos fuera de línea.

Uso con Docker (la imagen no trae scripts/; ver docs/DEPLOY_DOCKER_POSTGRES.md):
    docker cp scripts/exportar_turnos_ciclo.py asistencia_app:/tmp/
    docker exec -w /app asistencia_app python /tmp/exportar_turnos_ciclo.py --salida /tmp/turnos_ciclo.json
    docker cp asistencia_app:/tmp/turnos_ciclo.json .
Uso sin Docker (con el .env cargado):
    python scripts/exportar_turnos_ciclo.py
    python scripts/exportar_turnos_ciclo.py --salida /tmp/turnos.json

Por cada turno escribe: todos sus parámetros (tolerancias, anclajes, redondeo, colación automática, rotación dinámica...),
todas sus opciones/semanas con el horario de cada día (turno_dias, mezclado con los parámetros del turno igual que lo ve el motor),
cuántas personas lo tienen asignado hoy (solo el número, y cómo se reparten por semana de inicio) y los ajustes globales de asistencia.

NO incluye nombres, RUT ni marcas. Solo ejecuta SELECT: no modifica nada.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath('.'))
import dotenv

dotenv.load_dotenv()
from backend.core.database import Database  # noqa: E402
from backend.repositories.asistencia import AsistenciaRepository  # noqa: E402

VERSION_FORMATO = 1


def _json_default(o: Any) -> Any:
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


async def exportar(db: Any, hoy: str = "") -> Dict[str, Any]:
    hoy = hoy or date.today().strftime("%Y-%m-%d")
    repo = AsistenciaRepository(db)
    datos: Dict[str, Any] = {"meta": {"formato": VERSION_FORMATO, "tipo": "turnos_ciclo",
                                      "exportado_en": datetime.now().isoformat(timespec="seconds"), "hoy": hoy}}
    datos["ajustes"] = [dict(r) for r in await db.fetch_all(
        "SELECT clave, valor FROM ajustes WHERE clave LIKE ?", ("asistencia_%",))]

    turnos: List[Dict[str, Any]] = [dict(r) for r in await db.fetch_all(
        "SELECT * FROM turnos WHERE tipo_programacion = ? ORDER BY id", ("CICLO_INTELIGENTE",))]
    for t in turnos:
        # {num_semana: {dia_semana: configuración del día}}, ya con los parámetros del turno padre inyectados
        t["opciones"] = await repo.get_turno_dias_map(t["id"])
        fila = await db.fetch_one(
            "SELECT COUNT(DISTINCT a.empleado_id) AS personas FROM asignacion_turnos a "
            "JOIN empleados e ON e.id = a.empleado_id "
            "WHERE a.turno_id = ? AND a.fecha_inicio <= ? AND (a.fecha_fin IS NULL OR a.fecha_fin >= ?) AND e.activo = 1 AND (e.excluido_asistencia = 0 OR e.excluido_asistencia IS NULL)",
            (t["id"], hoy, hoy))
        t["personas_asignadas"] = int(dict(fila)["personas"]) if fila else 0
        reparto = await db.fetch_all(
            "SELECT a.semana_inicio AS semana_inicio, COUNT(DISTINCT a.empleado_id) AS personas FROM asignacion_turnos a "
            "JOIN empleados e ON e.id = a.empleado_id "
            "WHERE a.turno_id = ? AND a.fecha_inicio <= ? AND (a.fecha_fin IS NULL OR a.fecha_fin >= ?) AND e.activo = 1 AND (e.excluido_asistencia = 0 OR e.excluido_asistencia IS NULL) "
            "GROUP BY a.semana_inicio", (t["id"], hoy, hoy))
        t["reparto_semana_inicio"] = {str(dict(r)["semana_inicio"]): int(dict(r)["personas"]) for r in reparto}
    datos["turnos"] = turnos
    datos["meta"]["conteos"] = {"turnos": len(turnos), "ajustes": len(datos["ajustes"]),
                                "personas_asignadas": sum(t["personas_asignadas"] for t in turnos)}
    return datos


async def main() -> None:
    ap = argparse.ArgumentParser(description="Exporta (solo lectura) los turnos de Ciclo Inteligente para simular fuera de línea.")
    ap.add_argument("--salida", default="turnos_ciclo.json", help="Archivo de salida (por defecto turnos_ciclo.json)")
    args = ap.parse_args()

    db = Database()
    await db.connect()
    try:
        datos = await exportar(db)
    finally:
        await db.disconnect()

    with open(args.salida, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, default=_json_default)
    print(f"Listo: {args.salida} ({os.path.getsize(args.salida) / 1024:.0f} KB)")
    for k, v in datos["meta"]["conteos"].items():
        print(f"   {k:20s} {v}")
    print("El archivo no incluye nombres, RUT ni marcas.")


if __name__ == "__main__":
    asyncio.run(main())
