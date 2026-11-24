"""Días de hoy «en curso» cuya espera ya venció (decisión del dueño, 23-11-2026).

Un día de hoy queda EN_CURSO hasta la salida del horario más «Esperar la salida hasta ___ min después» (pantalla del
horario, `ventana_en_curso_minutos`). Si la persona no vuelve a marcar, nada lo recalculaba y seguía «en curso» hasta el
día siguiente: el panel la contaba «en turno» aunque ya se hubiera ido. La grilla recalcula solo esos días (pocas filas),
no la grilla entera.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _hora(fecha: str, hhmm: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.strptime(f"{fecha} {str(hhmm).strip()[:5]}", "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None


def espera_vencida(fila: Dict[str, Any], ahora: datetime) -> bool:
    """True si ya pasó la salida teórica del día más la espera de su horario (`ventana_en_curso_turno`, que la grilla
    lee del horario). Sin salida teórica no se decide aquí."""
    fecha = str(fila.get("fecha") or "")[:10]
    salida = _hora(fecha, fila.get("hora_salida_teorica"))
    if not salida:
        return False
    entrada = _hora(fecha, fila.get("hora_entrada_teorica"))
    if entrada and salida <= entrada:          # turno que cruza la medianoche: sale al día siguiente
        salida += timedelta(days=1)
    return ahora >= salida + timedelta(minutes=int(fila.get("ventana_en_curso_turno") or 0))


def vencidos(filas: Iterable[Dict[str, Any]], hoy: str, ahora: datetime) -> List[Tuple[int, str]]:
    """(empleado, fecha) de los días de hoy en curso con la espera de su horario vencida."""
    return [(f["empleado_id"], hoy) for f in filas
            if f.get("estado") == "EN_CURSO" and str(f.get("fecha") or "")[:10] == hoy and espera_vencida(f, ahora)]
