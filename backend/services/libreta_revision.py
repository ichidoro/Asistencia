"""Revisión de la libreta Art. 25 bis contra el GPS del camión (pedido del dueño, 05-11-2026).

La ventana de la libreta muestra «cosas por revisar»: la compara con el GPS y con las reglas del Art. 25 bis. Aquí solo se entrega lo que la
pantalla necesita y no tiene: los límites (ajustes editables en Configuración › Sistema › Libreta y GPS de choferes; nada escrito en el código)
y el descanso con que terminó el día anterior, porque el descanso mínimo de la ley es ininterrumpido y empieza la noche anterior.
"""
import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

# clave del ajuste -> (campo que recibe la pantalla, factor para pasarlo a la unidad de la pantalla)
AJUSTES_REVISION = {
    "libreta_conduccion_continua_max_horas": ("conduccion_continua_min", 60),
    "libreta_descanso_ininterrumpido_horas": ("descanso_min", 60),
    "libreta_tolerancia_gps_minutos": ("tolerancia_min", 1),
    "gps_velocidad_limite_kmh": ("velocidad_kmh", 1),
}

# Valores iniciales de esos ajustes (se siembran una vez; después manda lo que diga Configuración)
SEMILLAS_REVISION = [
    ("libreta_conduccion_continua_max_horas", "5",
     "Art. 25 bis: horas máximas de conducción continua que se aceptan en la libreta"),
    ("libreta_descanso_ininterrumpido_horas", "8",
     "Art. 25 bis: horas mínimas de descanso ininterrumpido antes de empezar el día (cuenta el final del día anterior)"),
    ("libreta_tolerancia_gps_minutos", "15",
     "Minutos de diferencia entre la libreta y el GPS que todavía se consideran que calzan (inicio, término y conducción)"),
    ("gps_velocidad_limite_kmh", "90",
     "Velocidad máxima de referencia de los camiones en km/h (switch de velocidad, reporte semanal y revisión de la libreta)"),
]

DESCANSO = 4  # código del descanso en los 96 tramos de la libreta (1 conducción, 2 espera, 3 tareas auxiliares, 4 descanso)


def limites_desde_ajustes(filas: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Convierte los ajustes guardados a la unidad de la pantalla. Un ajuste que falta o no es un número positivo queda en None
    (la pantalla no evalúa esa regla en vez de suponer un valor)."""
    out: Dict[str, Optional[float]] = {campo: None for campo, _ in AJUSTES_REVISION.values()}
    for f in filas or []:
        clave = f.get("clave")
        if clave not in AJUSTES_REVISION:
            continue
        campo, factor = AJUSTES_REVISION[clave]
        try:
            v = float(str(f.get("valor")).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if v < 0 or (v == 0 and campo != "tolerancia_min"):
            continue
        out[campo] = round(v * factor, 2)
    return out


def descanso_final_minutos(slots_96: Any) -> int:
    """Minutos de descanso seguidos con que termina el día (desde el último tramo que no es descanso hasta las 24:00)."""
    try:
        slots = json.loads(slots_96) if isinstance(slots_96, str) else list(slots_96 or [])
    except (TypeError, ValueError):
        return 0
    n = 0
    for v in reversed([int(x or 0) for x in slots[:96]]):
        if v != DESCANSO:
            break
        n += 1
    return n * 15


async def contexto_revision(db: Any, repository: Any, empleado_id: int, fecha: str) -> Dict[str, Any]:
    """Límites de la revisión y cómo terminó el día anterior de la misma persona (solo lectura)."""
    claves = list(AJUSTES_REVISION.keys())
    filas = await db.fetch_all(
        f"SELECT clave, valor FROM ajustes WHERE clave IN ({', '.join('?' for _ in claves)})", tuple(claves))
    limites = limites_desde_ajustes([dict(f) for f in filas])
    anterior = (date.fromisoformat(fecha) - timedelta(days=1)).isoformat()
    previa = await repository.get_libreta_180h(empleado_id, anterior)
    if previa:
        dia_anterior = {"fecha": anterior, "tiene_libreta": True, "descanso_final_min": descanso_final_minutos(previa.get("slots_96"))}
    else:
        asis = await db.fetch_one("SELECT estado FROM asistencias WHERE empleado_id = ? AND fecha = ?", (empleado_id, anterior))
        dia_anterior = {"fecha": anterior, "tiene_libreta": False, "estado": (dict(asis).get("estado") if asis else None)}
    return {"limites": limites, "dia_anterior": dia_anterior}
