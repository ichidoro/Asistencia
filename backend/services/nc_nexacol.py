"""
Notas de crédito de Nexacol para el Fill Rate (25-11-2026): se busca una nota por su número y se trae el detalle completo
de sus productos. Usa la misma cuenta de solo lectura y la misma sesión que la integración del GPS (gps_nexacol).
"""
from typing import Any, Dict, List

from backend.services.gps_nexacol import GpsNexacolError, _get

RUTA = "/api/reports/camiones-nc-detalle"


async def buscar(q: str) -> List[Dict[str, Any]]:
    """Hasta 8 notas de crédito cuyo número contiene lo escrito."""
    data = await _get(RUTA, {"q": q})
    return data.get("resultados") or []


async def detalle(folio: str) -> Dict[str, Any]:
    """La nota de crédito exacta, con cliente, factura original, chofer, patente y todas sus líneas de productos."""
    data = await _get(RUTA, {"folio": folio})
    return data.get("nc") or {}


__all__ = ["buscar", "detalle", "GpsNexacolError"]
