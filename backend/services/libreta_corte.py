"""
Fecha de corte entre dos regímenes de control para los horarios de Libreta Art. 25 bis (180 h):

    · ANTES de la fecha de corte  → las marcas vienen del reloj biométrico (la libreta física no se exigía).
    · DESDE la fecha de corte     → ya no se marca en el reloj; las marcas se ingresan a mano en la libreta.

La fecha vive como dato en la tabla `ajustes` (clave `asistencia_libreta_180h_bolsa_desde`) y se edita desde
Configuración. NINGÚN otro lugar del código debe escribir la fecha: todos leen de aquí.
"""
import re
from typing import Any, Dict, Optional

CLAVE_CORTE_LIBRETA = "asistencia_libreta_180h_bolsa_desde"
DESCRIPCION_CORTE_LIBRETA = (
    "Fecha (AAAA-MM-DD) desde la cual los horarios de Bolsa Flexible / Libreta 180h se controlan por libreta "
    "y no por reloj biométrico. Antes de esa fecha se usan las marcas del reloj."
)
# Valor inicial del dato en una base nueva (se siembra con INSERT OR IGNORE; después manda lo que se configure)
VALOR_INICIAL_CORTE_LIBRETA = "2026-10-01"

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


def corte_desde_ajustes(ajustes: Optional[Dict[str, Any]]) -> Optional[str]:
    return normalizar_fecha_corte((ajustes or {}).get(CLAVE_CORTE_LIBRETA))


async def obtener_corte_libreta(db) -> Optional[str]:
    """Lee la fecha de corte configurada (None si no hay una válida)."""
    row = await db.fetch_one("SELECT valor FROM ajustes WHERE clave = ?", (CLAVE_CORTE_LIBRETA,))
    return normalizar_fecha_corte(row["valor"] if row else None)


def regimen_del_dia(
    fecha: str,
    modalidad_control: Optional[str],
    tipo_programacion: Optional[str],
    corte: Optional[str],
) -> str:
    """
    'LIBRETA_180H' o 'RELOJ' para un día concreto.
    Un horario es "de libreta" si su modalidad es LIBRETA_180H o es de Bolsa Flexible; para esos horarios
    el régimen depende de la fecha de corte. Sin fecha de corte configurada, rige la libreta en todas las fechas.
    """
    es_horario_libreta = (
        (modalidad_control or REGIMEN_RELOJ).strip().upper() == REGIMEN_LIBRETA
        or (tipo_programacion or "").strip().upper() in TIPOS_BOLSA
    )
    if not es_horario_libreta:
        return REGIMEN_RELOJ
    if corte is None:
        return REGIMEN_LIBRETA
    return REGIMEN_LIBRETA if str(fecha)[:10] >= corte else REGIMEN_RELOJ
