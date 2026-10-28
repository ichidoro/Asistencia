from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from loguru import logger
from backend.services.dashboard_pendientes import dashboard_pendientes
from backend.services.dashboard_indicadores import dashboard_indicadores
from backend.services.dashboard_detalle import dashboard_detalle
from backend.core.security import SecurityContext, RequirePermission

router = APIRouter()


@router.get("/pendientes/")
async def get_dashboard_pendientes(
    area: Optional[str] = Query("Todas"),
    current_user: SecurityContext = Depends(RequirePermission("dashboard.ver"))
):
    """
    Dashboard «Lo que falta hacer»: hoy por área, cierre del tramo por área con lo que lo
    bloquea, horas extra y jornadas por decidir y contratos por vencer, con RLS.
    """
    if area and area != "Todas":
        current_user.verificar_acceso_area(area, "el área solicitada")
    try:
        data = await dashboard_pendientes.resumen(area, areas_permitidas=current_user.get_areas_filter())
        return {"status": "success", "data": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Dashboard pendientes: {e}")
        raise HTTPException(status_code=500, detail="No se pudo armar el dashboard.")


@router.get("/indicadores/")
async def get_dashboard_indicadores(
    area: Optional[str] = Query("Todas"),
    tramo: Optional[int] = Query(None, description="id del tramo (periodos_rrhh); por defecto el último terminado"),
    current_user: SecurityContext = Depends(RequirePermission("dashboard.ver"))
):
    """
    Dashboard «Indicadores»: cada indicador del tramo contra el promedio de los tramos anteriores,
    lo que empeoró primero, con las áreas que lo explican, con RLS.
    """
    if area and area != "Todas":
        current_user.verificar_acceso_area(area, "el área solicitada")
    try:
        data = await dashboard_indicadores.resumen(tramo, area, areas_permitidas=current_user.get_areas_filter())
        return {"status": "success", "data": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Dashboard indicadores: {e}")
        raise HTTPException(status_code=500, detail="No se pudieron calcular los indicadores.")


@router.get("/indicadores/detalle/")
async def get_dashboard_indicador_detalle(
    indicador: str = Query(..., description="id del indicador (puntualidad, faltas, correcciones_manuales, ...)"),
    area: Optional[str] = Query("Todas"),
    tramo: Optional[int] = Query(None),
    current_user: SecurityContext = Depends(RequirePermission("dashboard.ver"))
):
    """
    Detalle de un tacómetro: los registros que forman el número, por persona, con RLS.
    """
    if area and area != "Todas":
        current_user.verificar_acceso_area(area, "el área solicitada")
    try:
        data = await dashboard_detalle.detalle(indicador, tramo, area, areas_permitidas=current_user.get_areas_filter())
    except Exception as e:
        logger.exception(f"Dashboard detalle: {e}")
        raise HTTPException(status_code=500, detail="No se pudo armar el detalle.")
    if data is None:
        raise HTTPException(status_code=404, detail="Ese indicador no existe.")
    return {"status": "success", "data": data}
