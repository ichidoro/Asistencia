from fastapi import APIRouter, Depends, Query, status, Response, HTTPException
from loguru import logger
from backend.core.security import SecurityContext, RequirePermission
from typing import Optional, List
from backend.services.report_service import ReportService
from backend.repositories.asistencia import AsistenciaRepository
from backend.services.asistencia_service import AsistenciaService
from backend.core.database import get_db, Database
from datetime import datetime, date

router = APIRouter(
    prefix="/reports",
    tags=["Reportes"]
)

@router.get(
    "/asistencia/excel/",
    summary="Exportar Asistencia a Excel",
    description="Genera un archivo Excel con el reporte de asistencia detallado para el rango de fechas."
)
async def export_asistencia_excel(
    fecha_inicio: str = Query(..., description="Fecha inicio (YYYY-MM-DD)"),
    fecha_fin: str = Query(..., description="Fecha fin (YYYY-MM-DD)"),
    area: str = Query(None, description="Filtro opcional por área para exportar"),
    turno_id: Optional[int] = Query(None, description="Filtro opcional por turno para exportar"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("reportes.exportar"))
):
    # RLS Check
    if not current_user.alcance_global:
        if area:
            if area not in (current_user.areas or []):
                raise HTTPException(status_code=403, detail="No tiene permisos para el área solicitada")
        else:
            if current_user.areas:
                area = current_user.areas[0]
            else:
                raise HTTPException(status_code=403, detail="No tiene áreas permitidas asignadas")

    asistencia_repo = AsistenciaRepository(db)
    asistencia_service = AsistenciaService(asistencia_repo)
    service = ReportService(asistencia_service)
    
    excel_file = await service.generate_excel_report(fecha_inicio, fecha_fin, area, turno_id=turno_id)
    
    if not excel_file:
         return Response(status_code=status.HTTP_404_NOT_FOUND, content="No hay datos para el rango seleccionado")

    # Generar nombre de archivo
    import re
    safe_area = re.sub(r'[^a-zA-Z0-9_\-]', '_', area) if area else "Todas"
    filename = f"Reporte_Asistencia_{safe_area}_{fecha_inicio}_{fecha_fin}.xlsx"
    
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    
    return Response(
        content=excel_file.getvalue(),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers=headers
    )

@router.get(
    "/asistencia/excel-range/",
    summary="Exportar Asistencia a Excel (Rango Libre Sandbox)",
    description="Genera archivo Excel para cualquier rango personalizable sin ataduras mensuales."
)
async def export_asistencia_excel_range(
    fecha_inicio: str = Query(..., description="Fecha inicio (YYYY-MM-DD)"),
    fecha_fin: str = Query(..., description="Fecha fin (YYYY-MM-DD)"),
    area: str = Query(None, description="Filtro opcional por área para exportar"),
    turno_id: Optional[int] = Query(None, description="Filtro opcional por turno para exportar"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("reportes.exportar"))
):
    # RLS Check
    if not current_user.alcance_global:
        if area:
            if area not in (current_user.areas or []):
                raise HTTPException(status_code=403, detail="No tiene permisos para el área solicitada")
        else:
            if current_user.areas:
                area = current_user.areas[0]
            else:
                raise HTTPException(status_code=403, detail="No tiene áreas permitidas asignadas")

    asistencia_repo = AsistenciaRepository(db)
    asistencia_service = AsistenciaService(asistencia_repo)
    service = ReportService(asistencia_service)
    
    excel_file = await service.generate_excel_custom_range(fecha_inicio, fecha_fin, area, turno_id=turno_id)
    
    if not excel_file:
         return Response(status_code=status.HTTP_404_NOT_FOUND, content="No hay datos para el rango seleccionado")

    # Generar nombre de archivo
    import re
    safe_area = re.sub(r'[^a-zA-Z0-9_\-]', '_', area) if area else "Todas"
    filename = f"Reporte_Asistencia_{safe_area}_{fecha_inicio}_{fecha_fin}.xlsx"
    
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    
    return Response(
        content=excel_file.getvalue(),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers=headers
    )

@router.get(
    "/stats/",
    summary="Estadísticas de Asistencia (Charts)",
    description="Retorna datos agregados por día para gráficos (Line Chart)."
)
async def get_stats_periodo(
    fecha_inicio: str = Query(..., description="Fecha inicio (YYYY-MM-DD)"),
    fecha_fin: str = Query(..., description="Fecha fin (YYYY-MM-DD)"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("reportes.ver"))
):
    repo = AsistenciaRepository(db)
    areas_permitidas = None if current_user.alcance_global else (current_user.areas or [])
    stats = await repo.get_period_stats(fecha_inicio, fecha_fin, areas_permitidas=areas_permitidas)
    return stats

@router.post(
    "/reprocesar/",
    summary="Reprocesar Periodo desde Reportes",
    description="Dispara el motor de cálculo de asistencia desde la pantalla de Reportes. Requiere permiso propio del módulo Reportes."
)
async def reprocesar_desde_reportes(
    fecha_inicio: str = Query(..., description="Fecha inicio (YYYY-MM-DD)"),
    fecha_fin: str = Query(..., description="Fecha fin (YYYY-MM-DD)"),
    area: str = Query(None, description="Filtro opcional por área"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("reportes.reprocesar"))
):
    # RLS Check
    if not current_user.alcance_global:
        if area:
            if area not in (current_user.areas or []):
                raise HTTPException(status_code=403, detail="No tiene permisos para el área solicitada")
        else:
            if current_user.areas:
                area = current_user.areas
            else:
                raise HTTPException(status_code=403, detail="No tiene áreas permitidas asignadas")

    try:
        asistencia_repo = AsistenciaRepository(db)
        asistencia_service = AsistenciaService(asistencia_repo)
        resultado = await asistencia_service.procesar_periodo(fecha_inicio, fecha_fin, area)
        logger.info(f"[REPORTES] Reproceso ejecutado por {current_user.username}: {fecha_inicio} → {fecha_fin}")
        return {"ok": True, "resultado": resultado}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[REPORTES] Error en reproceso: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/sincronizar/",
    summary="Sincronizar BioAlba desde Reportes",
    description="Sincroniza las marcaciones desde el reloj BioAlba. Requiere permiso propio del módulo Reportes."
)
async def sincronizar_desde_reportes(
    fecha_inicio: str = Query(..., description="Fecha inicio (YYYY-MM-DD)"),
    fecha_fin: str = Query(..., description="Fecha fin (YYYY-MM-DD)"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("reportes.sincronizar"))
):
    try:
        from backend.services.sync_service import SyncService
        service = SyncService()
        
        areas_permitidas = None
        if not current_user.alcance_global:
            areas_permitidas = current_user.areas or []
            if not areas_permitidas:
                raise HTTPException(status_code=403, detail="No tiene áreas asignadas.")
        
        resultado = await service.sync_marcaciones(fecha_inicio, fecha_fin, areas_permitidas, force_recalculate=True)
        logger.info(f"[REPORTES] Sincronización ejecutada por {current_user.username}: {fecha_inicio} → {fecha_fin}")
        return {"ok": True, "resultado": resultado}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[REPORTES] Error en sincronización: {e}")
        raise HTTPException(status_code=500, detail=str(e))
