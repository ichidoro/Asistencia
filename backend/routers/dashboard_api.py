from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional, List
from backend.services.dashboard_service import dashboard_service
from backend.services.dashboard_analytics import dashboard_analytics
from backend.core.security import SecurityContext, get_current_user

router = APIRouter()

@router.get("/pulse/")
async def get_dashboard_pulse(
    area: Optional[str] = Query("Todas"),
    current_user: SecurityContext = Depends(get_current_user)
):
    """
    Retorna métricas diarias en tiempo real con RLS.
    """
    areas_permitidas = current_user.areas if not current_user.alcance_global else None
    
    # Si el usuario pide un área específica, validar
    area_filter = area if area != "Todas" else None
    if area_filter and not current_user.alcance_global:
        if area_filter not in (current_user.areas or []):
             raise HTTPException(status_code=403, detail="No tiene permisos para ver el área solicitada")

    try:
        data = await dashboard_service.get_pulse_today(area_filter, areas_permitidas=areas_permitidas)
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metrics/")
async def get_dashboard_metrics(
    fecha_inicio: str = Query(...),
    fecha_fin: str = Query(...),
    area: Optional[str] = Query("Todas"),
    current_user: SecurityContext = Depends(get_current_user)
):
    """
    Retorna métricas consolidadas con RLS.
    """
    areas_permitidas = current_user.areas if not current_user.alcance_global else None
    
    area_filter = area if area != "Todas" else None
    if area_filter and not current_user.alcance_global:
        if area_filter not in (current_user.areas or []):
             raise HTTPException(status_code=403, detail="No tiene permisos para ver el área solicitada")

    try:
        data = await dashboard_service.get_period_metrics(fecha_inicio, fecha_fin, area_filter, areas_permitidas=areas_permitidas)
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/composition/")
async def get_dashboard_composition(
    area: Optional[str] = Query("Todas"),
    current_user: SecurityContext = Depends(get_current_user)
):
    """
    Retorna la composición de dotación por género con RLS.
    """
    areas_permitidas = current_user.areas if not current_user.alcance_global else None
    
    area_filter = area if area != "Todas" else None
    if area_filter and not current_user.alcance_global:
        if area_filter not in (current_user.areas or []):
             raise HTTPException(status_code=403, detail="No tiene permisos para ver el área solicitada")

    try:
        data = await dashboard_service.get_gender_distribution(area_filter, areas_permitidas=areas_permitidas)
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/")
async def get_dashboard_analytics(
    fecha_inicio: str = Query(...),
    fecha_fin: str = Query(...),
    area: Optional[str] = Query("Todas"),
    horario: Optional[str] = Query("Todos"),
    current_user: SecurityContext = Depends(get_current_user)
):
    """
    Retorna toda la data para el Dashboard de un solo golpe.
    Usa el motor de analítica aislado.
    """
    areas_permitidas = current_user.areas if not current_user.alcance_global else None
    
    area_filter = area if area != "Todas" else None
    horario_filter = horario if horario != "Todos" else None

    if area_filter and not current_user.alcance_global:
        if area_filter not in (current_user.areas or []):
             raise HTTPException(status_code=403, detail="No tiene permisos para ver el área solicitada")

    try:
        data = await dashboard_analytics.get_dashboard_metrics(fecha_inicio, fecha_fin, area_filter, horario_filter, areas_permitidas=areas_permitidas)
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/desviaciones/detalle/")
async def get_dashboard_desviaciones_detalle(
    fecha_inicio: str = Query(...),
    fecha_fin: str = Query(...),
    tipo: str = Query(...),
    motivo: Optional[str] = Query(None),
    area: Optional[str] = Query("Todas"),
    horario: Optional[str] = Query("Todos"),
    current_user: SecurityContext = Depends(get_current_user)
):
    """
    Retorna el detalle (hasta 100 registros) que componen las fugas, ausencias o justificaciones.
    tipo: 'fuga', 'ausencia' o 'justificacion'
    """
    areas_permitidas = current_user.areas if not current_user.alcance_global else None
    
    area_filter = area if area != "Todas" else None
    horario_filter = horario if horario != "Todos" else None

    if area_filter and not current_user.alcance_global:
        if area_filter not in (current_user.areas or []):
             raise HTTPException(status_code=403, detail="No tiene permisos para ver el área solicitada")

    try:
        data = await dashboard_analytics.get_desviaciones_detalle(
            fecha_inicio, fecha_fin, tipo, motivo, area_filter, horario_filter, areas_permitidas=areas_permitidas
        )
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
