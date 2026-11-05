"""
Libreta Art. 25 bis: los días se ingresan en orden dentro del tramo (orden del dueño, 04-11-2026).

Un día de libreta solo se puede ingresar directamente (guardar, validar, marcar inasistencia o reasignar el turno del chofer) si todos los
días anteriores del mismo tramo que necesitan libreta ya la tienen. Pendiente = el día que la grilla muestra en PEN: el cálculo lo deja en
estado PENDIENTE con origen LIBRETA_180H mientras no haya libreta; los libres, feriados, vacaciones, licencias y días justificados no
quedan pendientes y no frenan nada. La copia del chofer a sus acompañantes nunca se bloquea: si al acompañante le queda un día anterior
pendiente, se avisa a quien guarda para que alguien lo complete.
"""
from datetime import date
from typing import Any, Dict, List, Optional

DIAS_SEMANA = ('lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo')
ESTADO_PENDIENTE = 'PENDIENTE'
ORIGEN_LIBRETA = 'LIBRETA_180H'

# De dónde salió la patente guardada con el día: la planificación de Despacho Diario (Nexacol), elegida a mano, copiada del chofer o
# declarada «No anduvo en camión»
ORIGENES_PATENTE = ('PLAN', 'MANUAL', 'CHOFER', 'SIN_CAMION')


def fecha_legible(fecha: str) -> str:
    d = date.fromisoformat(str(fecha)[:10])
    return f"{DIAS_SEMANA[d.weekday()]} {d.strftime('%d-%m-%Y')}"


def mensaje_pendiente(pendientes: List[str]) -> str:
    """Texto para quien intenta ingresar un día con días anteriores del tramo todavía pendientes."""
    resto = len(pendientes) - 1
    extra = f" (y {resto} {'día' if resto == 1 else 'días'} más después de ese)" if resto > 0 else ""
    return f"Primero completa el {fecha_legible(pendientes[0])}{extra}: la libreta se llena en orden dentro del tramo."


def nombre_persona(fila: Optional[Dict[str, Any]]) -> str:
    """Nombre completo en mayúsculas, con los apellidos primero (como lo muestra la grilla)."""
    if not fila:
        return ''
    partes = [fila.get('apellido_paterno'), fila.get('apellido_materno'), fila.get('nombre')]
    return ' '.join(str(p).strip() for p in partes if p and str(p).strip()).upper()


async def pendientes_anteriores(service, empleado_id: int, fecha: str) -> List[str]:
    """Días anteriores a `fecha`, del mismo tramo, que siguen pendientes de libreta (de más antiguo a más nuevo)."""
    from backend.services.cuadre_service import CuadreService
    t_ini, _ = await CuadreService(service).tramo_de(fecha)
    filas = await service.repository.db.fetch_all(
        "SELECT a.fecha FROM asistencias a WHERE a.empleado_id = ? AND a.fecha >= ? AND a.fecha < ? AND a.estado = ? AND a.origen = ? "
        "AND NOT EXISTS (SELECT 1 FROM libreta_art25bis_dias l WHERE l.empleado_id = a.empleado_id AND l.fecha = a.fecha) "
        "ORDER BY a.fecha",
        (empleado_id, t_ini, fecha, ESTADO_PENDIENTE, ORIGEN_LIBRETA))
    return [str(r['fecha'])[:10] for r in filas]


async def libretas_posteriores(service, empleado_id: int, fecha: str) -> int:
    """Cuántos días posteriores a `fecha`, del mismo tramo, ya tienen libreta (para avisar al borrar un día del medio)."""
    from backend.services.cuadre_service import CuadreService
    _, t_fin = await CuadreService(service).tramo_de(fecha)
    fila = await service.repository.db.fetch_one(
        "SELECT COUNT(*) AS n FROM libreta_art25bis_dias WHERE empleado_id = ? AND fecha > ? AND fecha <= ?",
        (empleado_id, fecha, t_fin))
    return int((fila or {}).get('n') or 0)


def _slots(fila: Optional[Dict[str, Any]]) -> List[int]:
    import json
    s = (fila or {}).get('slots_96')
    if isinstance(s, str):
        try:
            s = json.loads(s)
        except Exception:
            s = []
    s = [int(x or 0) for x in (s or [])]
    return (s + [0] * 96)[:96]


def mismos_tramos(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> bool:
    """True si los dos días tienen exactamente los mismos 96 tramos (la copia del chofer sin ajustes)."""
    return _slots(a) == _slots(b)


def normalizar_patente(patente: Any, vehiculo_id: Any, origen: Any) -> Dict[str, Optional[str]]:
    """Patente, vehículo y origen tal como se guardan con el día; «No anduvo en camión» no guarda patente."""
    o = str(origen or '').strip().upper() or None
    if o not in ORIGENES_PATENTE:
        o = 'MANUAL' if patente else None
    if o == 'SIN_CAMION':
        return {'patente': None, 'vehiculo_id': None, 'patente_origen': 'SIN_CAMION'}
    p = str(patente or '').strip().upper() or None
    v = str(vehiculo_id or '').strip() or None
    return {'patente': p, 'vehiculo_id': v if p else None, 'patente_origen': o if p else None}
