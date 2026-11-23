"""Deja a cada persona con UN solo borrador de libreta: conserva el más antiguo y borra los más recientes.

Uso (dentro del contenedor de la app):
    python -m backend.scripts.corregir_borradores_duplicados            # solo MUESTRA lo que haría (no borra nada)
    python -m backend.scripts.corregir_borradores_duplicados --aplicar  # borra de verdad

Borra igual que el botón «Borrar registro del día»: elimina el día de la libreta, sus enlaces de acompañantes y la foto, y recalcula la asistencia
del día (vuelve a quedar pendiente). No toca días validados, inasistencias marcadas ni períodos cerrados (los lista para resolverlos a mano).
Decisión 23-11-2026: una persona tiene un solo borrador a la vez; si hay dos, queda el primero.
"""
import asyncio
import sys
from pathlib import Path

from loguru import logger

from backend.core.database import db
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.seguridad import SeguridadRepository
from backend.services.asistencia_service import AsistenciaService
from backend.services.quantum_matrix_engine import libreta_es_inasistencia


async def _plan(repo):
    """{empleado_id: [(fecha, ...)]} de las personas con más de un borrador real, de la más antigua a la más reciente."""
    filas = await db.fetch_all(
        "SELECT empleado_id, fecha, observaciones FROM libreta_art25bis_dias WHERE COALESCE(cerrado, 0) = 0 ORDER BY empleado_id, fecha")
    por_persona = {}
    for f in filas:
        if libreta_es_inasistencia(f):
            continue
        por_persona.setdefault(int(f["empleado_id"]), []).append(str(f["fecha"])[:10])
    return {e: dias for e, dias in por_persona.items() if len(dias) > 1}


async def main(aplicar: bool) -> int:
    await db.connect()
    repo = AsistenciaRepository(db)
    service = AsistenciaService(repo)
    plan = await _plan(repo)
    if not plan:
        print("Nadie tiene más de un borrador. No hay nada que corregir.")
        return 0
    nombres = {int(r["id"]): f"{r['apellido_paterno'] or ''} {r['apellido_materno'] or ''} {r['nombre'] or ''}".strip()
               for r in await db.fetch_all("SELECT id, nombre, apellido_paterno, apellido_materno FROM empleados")}
    borrados, omitidos = 0, []
    for emp, dias in sorted(plan.items(), key=lambda kv: nombres.get(kv[0], "")):
        conservar, sobran = dias[0], dias[1:]
        print(f"{nombres.get(emp, emp)} (id {emp}): conserva el borrador del {conservar}; "
              f"{'BORRA' if aplicar else 'borraría'} {', '.join(sobran)}")
        if not aplicar:
            continue
        for fecha in sobran:
            if await repo.check_rango_cerrado(fecha, fecha, emp):
                omitidos.append((emp, fecha, "período cerrado"))
                continue
            await repo.delete_libreta_180h(emp, fecha)
            await repo.set_acompanantes_180h(emp, fecha, [])
            foto = Path("downloads") / "libretas_180h" / f"{emp}_{fecha}.jpg"
            try:
                foto.unlink(missing_ok=True)
            except Exception as e:  # la foto es secundaria
                logger.warning(f"No se pudo borrar la foto {foto}: {e}")
            await service.procesar_empleado_dia(emp, fecha, save=True, force=True)
            try:
                await SeguridadRepository(db).log_auditoria(
                    None, "script", "DELETE_LIBRETA_180H", "Marcaciones",
                    f"Borrador duplicado eliminado (queda el del {conservar}): empleado {emp}, fecha {fecha}")
            except Exception:
                pass
            borrados += 1
    if aplicar:
        print(f"\nListo: {borrados} borrador(es) borrado(s).")
        for emp, fecha, motivo in omitidos:
            print(f"  NO se tocó {nombres.get(emp, emp)} {fecha}: {motivo} (resolver a mano)")
    else:
        print(f"\nSimulación: {sum(len(d) - 1 for d in plan.values())} borrador(es) se borrarían en {len(plan)} persona(s). Para aplicar: --aplicar")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--aplicar" in sys.argv)))
