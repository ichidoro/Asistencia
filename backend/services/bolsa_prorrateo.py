"""Prorrateo de la meta de Bolsa Flexible para vigencias parciales.

La ley (art. 25 bis del Código del Trabajo) fija para los choferes de carga
terrestre interurbana una jornada MÁXIMA de 180 horas al mes, que «no podrá
distribuirse en menos de veintiún días». No da una fórmula para una persona
que ingresa o egresa a mitad del período: exigirle las 180 horas completas
en los días que le quedan la obligaría a una carga diaria mayor que la de un
mes completo.

Criterio de la plataforma (aprobado por el dueño el 22-10-2026): la meta se
reparte en proporción a los días corridos de vigencia del contrato dentro del
tramo (fecha de ingreso y de salida de la ficha del empleado). Se usan días
corridos —no días programados— porque los días libres del tramo completo
también están dentro de la proporción: así la exigencia por día nunca supera
la de un mes completo, cualquiera sea la configuración de días libres del
turno. La meta de horas de espera (88 h, mismo artículo) se prorratea igual.

Además se avisa —sin bloquear— cuando los días corridos disponibles no
alcanzan los 21 días que exige la ley para repartir la jornada.
"""

from datetime import date
from typing import Any, Dict, Optional

# Art. 25 bis del Código del Trabajo: la jornada mensual de 180 horas
# no puede distribuirse en menos de veintiún días.
DIAS_MINIMOS_BOLSA_LEY = 21


def _leer_fecha(valor: Any) -> Optional[date]:
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except (TypeError, ValueError):
        return None


def calcular_prorrateo_bolsa(
    fecha_ingreso: Any,
    fecha_salida: Any,
    tramo_inicio: Any,
    tramo_fin: Any,
) -> Optional[Dict[str, Any]]:
    """Calcula el prorrateo de la meta de Bolsa Flexible para un tramo RRHH.

    Devuelve None cuando no hay nada que ajustar ni avisar (la vigencia cubre
    el tramo entero y el tramo alcanza los 21 días legales). Si no, devuelve
    un dict con la ventana de vigencia dentro del tramo (`desde`/`hasta`),
    los días corridos disponibles y del tramo, el `factor` a aplicar sobre la
    meta (1.0 si solo corresponde el aviso) y `aviso_21_dias`.
    """
    t_ini = _leer_fecha(tramo_inicio)
    t_fin = _leer_fecha(tramo_fin)
    if not t_ini or not t_fin or t_fin < t_ini:
        return None

    ingreso = _leer_fecha(fecha_ingreso)
    salida = _leer_fecha(fecha_salida)

    desde = max(ingreso, t_ini) if ingreso else t_ini
    hasta = min(salida, t_fin) if salida else t_fin

    dias_tramo = (t_fin - t_ini).days + 1
    dias_disponibles = (hasta - desde).days + 1 if hasta >= desde else 0
    recorta_ingreso = bool(ingreso and ingreso > t_ini)
    recorta_salida = bool(salida and salida < t_fin)
    aviso = dias_disponibles < DIAS_MINIMOS_BOLSA_LEY

    if not recorta_ingreso and not recorta_salida and not aviso:
        return None

    factor = (dias_disponibles / dias_tramo) if dias_tramo > 0 else 0.0
    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat() if hasta >= desde else desde.isoformat(),
        "dias_tramo": dias_tramo,
        "dias_disponibles": dias_disponibles,
        "factor": round(min(1.0, factor), 6),
        "fecha_ingreso": ingreso.isoformat() if recorta_ingreso else None,
        "fecha_salida": salida.isoformat() if recorta_salida else None,
        "dias_minimos_ley": DIAS_MINIMOS_BOLSA_LEY,
        "aviso_21_dias": aviso,
    }


def aplicar_prorrateo(meta_minutos: float, prorrateo: Optional[Dict[str, Any]]) -> int:
    """Aplica el factor del prorrateo a una meta en minutos (si corresponde)."""
    meta = round(meta_minutos or 0)
    factor = prorrateo.get("factor") if prorrateo else None
    # Ojo: factor puede ser 0.0 (sin vigencia en el tramo) y también debe aplicarse
    if factor is not None and factor < 1.0:
        meta = round(meta * factor)
    return meta


def fecha_en_vigencia(fecha_str: str, prorrateo: Optional[Dict[str, Any]]) -> bool:
    """True si la fecha (YYYY-MM-DD) cae dentro de la vigencia del prorrateo.

    Sin prorrateo, toda fecha del tramo está en vigencia. Los días fuera de la
    vigencia no se cuentan como programados: la persona aún no ingresaba (o ya
    había egresado), no son inasistencias ni diluyen el descuento por días
    justificados.
    """
    if not prorrateo:
        return True
    return prorrateo["desde"] <= fecha_str <= prorrateo["hasta"]
