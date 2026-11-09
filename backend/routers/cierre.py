from fastapi import APIRouter, Depends, Query, HTTPException, Body
from backend.core.security import SecurityContext, RequirePermission
from backend.core.database import get_db, Database
from backend.services.cierre_service import CierreService
from pydantic import BaseModel
from datetime import datetime
from loguru import logger

router = APIRouter(
    prefix="/cierre",
    tags=["Cierre"]
)

class EjecutarCierreRequest(BaseModel):
    fecha_inicio: str
    fecha_fin: str
    area: str
    aceptar_inasistencias: bool = False

@router.get(
    "/pre-evaluacion",
    summary="Evaluar condiciones para cerrar un mes"
)
async def evaluar_cierre(
    fecha_inicio: str = Query(..., description="Fecha inicio (YYYY-MM-DD)"),
    fecha_fin: str = Query(..., description="Fecha fin (YYYY-MM-DD)"),
    area: str = Query(..., description="Área a evaluar"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.cierre_periodo"))
):
    try:
        if not area or area == 'Todas' or area.strip() == '':
            raise HTTPException(status_code=400, detail="Debe seleccionar un área específica.")
            
        d_ini = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        d_fin = datetime.strptime(fecha_fin, "%Y-%m-%d")
        diff_days = (d_fin - d_ini).days + 1
        if diff_days > 35:
            raise HTTPException(status_code=400, detail="El rango seleccionado no puede superar los 35 días.")

        service = CierreService(db)
        if not current_user.check_area_access(area):
            raise HTTPException(status_code=403, detail="No tienes permisos sobre esta área.")
        resultado = await service.evaluar_cierre(fecha_inicio, fecha_fin, area)
        return resultado
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post(
    "/ejecutar",
    summary="Sellar el periodo"
)
async def ejecutar_cierre(
    req: EjecutarCierreRequest = Body(...),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.cierre_periodo"))
):
    try:
        if not req.area or req.area == 'Todas' or req.area.strip() == '':
            raise HTTPException(status_code=400, detail="Debe seleccionar un área específica.")
            
        d_ini = datetime.strptime(req.fecha_inicio, "%Y-%m-%d")
        d_fin = datetime.strptime(req.fecha_fin, "%Y-%m-%d")
        diff_days = (d_fin - d_ini).days + 1
        if diff_days > 35:
            raise HTTPException(status_code=400, detail="El rango seleccionado no puede superar los 35 días.")

        service = CierreService(db)
        if not current_user.check_area_access(req.area):
            raise HTTPException(status_code=403, detail="No tienes permisos sobre esta área.")
        user_dict = {
            "id": current_user.user_id,
            "username": current_user.username,
            "rol_global": 1 if current_user.alcance_global else 0
        }
        res = await service.ejecutar_cierre(
            fecha_inicio=req.fecha_inicio,
            fecha_fin=req.fecha_fin,
            area=req.area,
            aceptar_inasistencias=req.aceptar_inasistencias,
            user=user_dict
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete(
    "/{cierre_id}",
    summary="Reabrir un periodo cerrado (Solo Super Admin)"
)
async def reabrir_cierre(
    cierre_id: int,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.cierre_periodo"))
):
    try:
        if not current_user.alcance_global:
            raise HTTPException(status_code=403, detail="Operación exclusiva para Administradores Generales (Super Admin).")
            
        service = CierreService(db)
        # Verificar que el cierre exista
        cierre = await db.fetch_one("SELECT * FROM cierres_periodos WHERE id = ?", (cierre_id,))
        if not cierre:
            raise HTTPException(status_code=404, detail="Registro de cierre no encontrado.")
            
        # Registrar en auditoría
        await db.execute(
            "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
            (
                current_user.user_id,
                current_user.username,
                "REAPERTURA_PERIODO",
                "Cierre",
                f"Período reabierto (eliminado cierre id {cierre_id}): {cierre['fecha_inicio']} a {cierre['fecha_fin']} para área '{cierre['area']}'."
            )
        )
        
        # Eliminar el registro de cierre
        await db.execute("DELETE FROM cierres_periodos WHERE id = ?", (cierre_id,))
        
        # También actualizar el estado en periodos_rrhh de vuelta a 'abierto' y marcarlo como vigente
        try:
            await db.execute(
                "UPDATE periodos_rrhh SET estado = 'abierto' WHERE fecha_inicio = ? AND fecha_fin = ?",
                (cierre['fecha_inicio'], cierre['fecha_fin'])
            )
            
            # Desactivar solo el periodo específico que se está reabriendo y reactivarlo
            periodo_row = await db.fetch_one(
                "SELECT id FROM periodos_rrhh WHERE fecha_inicio = ? AND fecha_fin = ?",
                (cierre['fecha_inicio'], cierre['fecha_fin'])
            )
            if periodo_row:
                await db.execute("UPDATE periodos_rrhh SET activo = 0 WHERE id = ?", (periodo_row['id'],))
                await db.execute("UPDATE periodos_rrhh SET activo = 1 WHERE id = ?", (periodo_row['id'],))
            logger.info(f"✨ periodos_rrhh actualizado a 'abierto' y marcado como Vigente para el rango {cierre['fecha_inicio']} a {cierre['fecha_fin']} (Reapertura)")
        except Exception as e_open_rrhh:
            logger.warning(f"⚠️ No se pudo actualizar el estado/vigencia en periodos_rrhh tras reapertura: {e_open_rrhh}")

        return {"success": True, "message": "Periodo reabierto exitosamente."}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _validar_informe(fecha_inicio: str, fecha_fin: str, area: str, current_user: SecurityContext):
    if not area or area == 'Todas' or area.strip() == '':
        raise HTTPException(status_code=400, detail="Debe seleccionar un área específica.")
    d_ini = datetime.strptime(fecha_inicio, "%Y-%m-%d")
    d_fin = datetime.strptime(fecha_fin, "%Y-%m-%d")
    if (d_fin - d_ini).days + 1 > 35:
        raise HTTPException(status_code=400, detail="El rango seleccionado no puede superar los 35 días.")
    if not current_user.check_area_access(area):
        raise HTTPException(status_code=403, detail="No tienes permisos sobre esta área.")


@router.get(
    "/informe-pdf",
    summary="Qué informes de cierre tiene el área (preinforme si aún no se cierra)"
)
async def informe_pdf(
    fecha_inicio: str = Query(..., description="Fecha inicio (YYYY-MM-DD)"),
    fecha_fin: str = Query(..., description="Fecha fin (YYYY-MM-DD)"),
    area: str = Query(..., description="Área"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.cierre_periodo"))
):
    """La lista de informes del área, uno por tipo de horario (sin dibujarlos): el navegador descarga cada uno desde
    /informe-pdf/archivo. Con el área cerrada en ese tramo es el informe definitivo; si no, el preinforme."""
    from backend.repositories.asistencia import AsistenciaRepository
    from backend.services.asistencia_service import AsistenciaService
    from backend.services.informe_cierre_pdf import informes_del_area
    try:
        _validar_informe(fecha_inicio, fecha_fin, area, current_user)
        res = await informes_del_area(db, AsistenciaService(AsistenciaRepository(db)), fecha_inicio, fecha_fin, area,
                                      solo_lista=True)
        return {"preinforme": res["preinforme"],
                "archivos": [{"tipo": a["tipo"], "filename": a["filename"], "titulo": a["titulo"]} for a in res["archivos"]]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al preparar el informe de cierre en PDF: {e}")
        raise HTTPException(status_code=500, detail="No se pudo generar el informe de cierre.")


@router.get(
    "/informe-pdf/archivo",
    summary="Descarga un informe de cierre en PDF (un tipo de horario del área)"
)
async def informe_pdf_archivo(
    fecha_inicio: str = Query(..., description="Fecha inicio (YYYY-MM-DD)"),
    fecha_fin: str = Query(..., description="Fecha fin (YYYY-MM-DD)"),
    area: str = Query(..., description="Área"),
    tipo: str = Query(..., description="CICLO o BOLSA"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.cierre_periodo"))
):
    """El PDF como archivo adjunto (igual que el Excel): el navegador lo descarga directo."""
    from fastapi.responses import Response
    from backend.repositories.asistencia import AsistenciaRepository
    from backend.services.asistencia_service import AsistenciaService
    from backend.services.informe_cierre_pdf import informes_del_area
    try:
        _validar_informe(fecha_inicio, fecha_fin, area, current_user)
        if tipo not in ('CICLO', 'BOLSA'):
            raise HTTPException(status_code=400, detail="Tipo de horario no válido.")
        res = await informes_del_area(db, AsistenciaService(AsistenciaRepository(db)), fecha_inicio, fecha_fin, area, tipo=tipo)
        if not res["archivos"]:
            raise HTTPException(status_code=404, detail="El área no tiene personas de ese tipo de horario en el tramo.")
        a = res["archivos"][0]
        return Response(content=a["content"], media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{a["filename"]}"'})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al generar el informe de cierre en PDF: {e}")
        raise HTTPException(status_code=500, detail="No se pudo generar el informe de cierre.")


@router.get(
    "/resumen",
    summary="Resumen ejecutivo del área antes de sellar (balance de horas por tipo de horario)"
)
async def resumen_cierre(
    fecha_inicio: str = Query(..., description="Fecha inicio (YYYY-MM-DD)"),
    fecha_fin: str = Query(..., description="Fecha fin (YYYY-MM-DD)"),
    area: str = Query(..., description="Área"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.cierre_periodo"))
):
    """Las mismas cifras del informe PDF, en un balance que parte de las horas totales y termina en lo que se carga."""
    from backend.repositories.asistencia import AsistenciaRepository
    from backend.services.asistencia_service import AsistenciaService
    from backend.services.informe_cierre_pdf import resumen_del_area
    try:
        _validar_informe(fecha_inicio, fecha_fin, area, current_user)
        return {"tipos": await resumen_del_area(db, AsistenciaService(AsistenciaRepository(db)), fecha_inicio, fecha_fin, area)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al preparar el resumen de cierre: {e}")
        raise HTTPException(status_code=500, detail="No se pudo preparar el resumen del cierre.")
