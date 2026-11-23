"""Desde cuándo cuenta una persona en un período: el inicio de su asignación de turno (dueño, 23-11-2026).

La fecha de ingreso de la ficha es solo referencial: BioAlba la reemplaza por la fecha de creación del usuario en el reloj
y, si la persona se fue y volvió, mantiene la antigua; además, al renovar un contrato puede quedar con la fecha del contrato
nuevo. Por eso todo lo que depende de «desde cuándo está» la persona se cuenta desde la asignación de turno: la grilla
(que ya lo hacía), los bonos en proporción, la meta de la Bolsa Flexible, la antigüedad del bono 4 Productos y el inicio
del historial de cargos.

El inicio es el del turno continuo vigente en el período: se parte por la asignación más antigua que toca el período y se
retrocede mientras haya una asignación anterior que termine el día antes (o se cruce con ella). Un cambio de turno sin
corte mantiene el inicio del primero; si la persona se fue y volvió (hay un corte), cuenta desde el turno nuevo.
"""
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional


def _fecha(valor: Any) -> Optional[date]:
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def inicio_continuo(asignaciones: Iterable[Dict[str, Any]], fecha_inicio: Any, fecha_fin: Any) -> Optional[str]:
    """Inicio (AAAA-MM-DD) del turno continuo de la persona vigente en [fecha_inicio, fecha_fin], o None si no tiene
    ninguna asignación en ese período. `asignaciones`: filas con fecha_inicio y fecha_fin (None = sin término)."""
    fi, ff = _fecha(fecha_inicio), _fecha(fecha_fin)
    tramos = []
    for a in asignaciones:
        ini = _fecha(a.get("fecha_inicio"))
        if ini is None:
            continue
        tramos.append((ini, _fecha(a.get("fecha_fin"))))
    if not tramos or fi is None or ff is None:
        return None
    en_periodo = [t for t in tramos if t[0] <= ff and (t[1] is None or t[1] >= fi)]
    if not en_periodo:
        return None
    inicio = min(t[0] for t in en_periodo)
    # Retroceder por las asignaciones anteriores pegadas (sin un día de corte entre una y otra)
    cambio = True
    while cambio:
        cambio = False
        for ini, fin in tramos:
            if ini < inicio and (fin is None or fin >= inicio - timedelta(days=1)):
                inicio = ini
                cambio = True
    return inicio.isoformat()


async def inicios_de_turno(db, empleado_ids: List[int], fecha_inicio: str, fecha_fin: str) -> Dict[int, Optional[str]]:
    """El inicio del turno continuo de cada persona en el período (ver inicio_continuo)."""
    ids = [int(i) for i in empleado_ids if i is not None]
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    filas = await db.fetch_all(
        f"SELECT empleado_id, fecha_inicio, fecha_fin FROM asignacion_turnos WHERE empleado_id IN ({ph})", tuple(ids))
    por_emp: Dict[int, List[Dict[str, Any]]] = {}
    for f in filas:
        por_emp.setdefault(int(f["empleado_id"]), []).append(dict(f))
    return {i: inicio_continuo(por_emp.get(i, []), fecha_inicio, fecha_fin) for i in ids}
