"""Exportación de SOLO LECTURA de los turnos de Ciclo Inteligente, tal como están en la app.

Sirve para repetir fuera de línea (simulaciones) cómo se comportaría el motor con los turnos reales. Por cada turno entrega:
  - todos sus parámetros (tolerancias, anclajes, redondeo, colación automática, rotación dinámica, ventana EN CURSO...), es decir,
    la fila completa de `turnos`;
  - todas sus opciones/semanas con el horario de cada día: `opciones` = {num_semana: {dia_semana: configuración del día}}, cada día
    con los parámetros del turno mezclados igual que los ve el motor (AsistenciaRepository.get_turno_dias_map);
  - las áreas de visibilidad, cuántas personas lo tienen asignado hoy (solo el número) y cómo se reparten por semana de inicio.
Más los ajustes globales de asistencia (`ajustes` con clave `asistencia_%`).

NO incluye nombres, RUT ni marcas. Solo ejecuta SELECT: no modifica nada.
Lo usan el endpoint GET /api/turnos/export-ciclos/ (botón "Exportar turnos" de Configuración › Horarios) y
scripts/exportar_turnos_ciclo.py.
"""
from datetime import date, datetime
from typing import Any, Dict, List

from backend.repositories.asistencia import AsistenciaRepository

VERSION_FORMATO = 1

# Personas con el turno asignado en la fecha `hoy`, sin contar bajas ni excluidos de asistencia (los que el motor no procesa).
_FILTRO_PERSONAS = (
    "a.turno_id = ? AND a.fecha_inicio <= ? AND (a.fecha_fin IS NULL OR a.fecha_fin >= ?) "
    "AND e.activo = 1 AND (e.excluido_asistencia = 0 OR e.excluido_asistencia IS NULL)"
)


async def exportar_turnos_ciclo(db: Any, hoy: str = "") -> Dict[str, Any]:
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
        areas = await db.fetch_all(
            "SELECT a.nombre AS nombre FROM turno_areas ta JOIN areas a ON ta.area_id = a.id WHERE ta.turno_id = ? ORDER BY a.nombre",
            (t["id"],))
        t["areas"] = [dict(r)["nombre"] for r in areas]
        fila = await db.fetch_one(
            "SELECT COUNT(DISTINCT a.empleado_id) AS personas FROM asignacion_turnos a "
            "JOIN empleados e ON e.id = a.empleado_id WHERE " + _FILTRO_PERSONAS, (t["id"], hoy, hoy))
        t["personas_asignadas"] = int(dict(fila)["personas"]) if fila else 0
        reparto = await db.fetch_all(
            "SELECT a.semana_inicio AS semana_inicio, COUNT(DISTINCT a.empleado_id) AS personas FROM asignacion_turnos a "
            "JOIN empleados e ON e.id = a.empleado_id WHERE " + _FILTRO_PERSONAS + " GROUP BY a.semana_inicio",
            (t["id"], hoy, hoy))
        t["reparto_semana_inicio"] = {str(dict(r)["semana_inicio"]): int(dict(r)["personas"]) for r in reparto}
    datos["turnos"] = turnos
    datos["meta"]["conteos"] = {"turnos": len(turnos), "ajustes": len(datos["ajustes"]),
                                "personas_asignadas": sum(t["personas_asignadas"] for t in turnos)}
    return datos
