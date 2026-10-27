"""
Fecha de corte entre dos regímenes de control para los horarios de Libreta Art. 25 bis (180 h):

    · ANTES de la fecha de corte  → las marcas vienen del reloj biométrico (la libreta física no se exigía).
    · DESDE la fecha de corte     → ya no se marca en el reloj; las marcas se ingresan a mano en la libreta.

Cada horario tiene su propia fecha (columna `turnos.libreta_desde`, «Sin reloj a partir de» en la pantalla del horario;
orden del dueño, 27-10-2026: «cada área debe tener su fecha de partida con la libreta»). Antes era una sola fecha para
todos los horarios (ajuste `asistencia_libreta_180h_bolsa_desde`): al crearse la columna se copió a cada horario de
libreta y el ajuste se quitó (TurnoRepository). NINGÚN otro lugar del código debe escribir una fecha: todos leen de aquí.
"""
import re
from typing import Any, Dict, Optional

_RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REGIMEN_LIBRETA = "LIBRETA_180H"
REGIMEN_RELOJ = "RELOJ"
TIPOS_BOLSA = ("BOLSA_FLEXIBLE", "FLEXIBLE_BOLSA")


def normalizar_fecha_corte(valor: Any) -> Optional[str]:
    """Devuelve 'AAAA-MM-DD' si el valor es una fecha válida; si no, None."""
    if not valor:
        return None
    txt = str(valor).strip()[:10]
    if not _RE_FECHA.match(txt):
        return None
    try:
        from datetime import datetime
        datetime.strptime(txt, "%Y-%m-%d")
    except ValueError:
        return None
    return txt


def fecha_libreta_del_horario(turno: Optional[Dict[str, Any]]) -> Optional[str]:
    """La fecha «Sin reloj a partir de» del horario (None si no tiene una válida)."""
    return normalizar_fecha_corte((turno or {}).get('libreta_desde'))


def es_horario_libreta(modalidad_control: Optional[str], tipo_programacion: Optional[str]) -> bool:
    """Un horario es "de libreta" si su modalidad es LIBRETA_180H o es de Bolsa Flexible."""
    return ((modalidad_control or REGIMEN_RELOJ).strip().upper() == REGIMEN_LIBRETA
            or (tipo_programacion or "").strip().upper() in TIPOS_BOLSA)


def regimen_del_dia(
    fecha: str,
    modalidad_control: Optional[str],
    tipo_programacion: Optional[str],
    corte: Optional[str],
) -> str:
    """
    'LIBRETA_180H' o 'RELOJ' para un día concreto, con la fecha de corte del horario (`fecha_libreta_del_horario`).
    Para los horarios de libreta el régimen depende de esa fecha; sin fecha, rige la libreta en todas las fechas.
    """
    if not es_horario_libreta(modalidad_control, tipo_programacion):
        return REGIMEN_RELOJ
    if corte is None:
        return REGIMEN_LIBRETA
    return REGIMEN_LIBRETA if str(fecha)[:10] >= corte else REGIMEN_RELOJ
