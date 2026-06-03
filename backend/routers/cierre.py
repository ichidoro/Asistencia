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


@router.get(
    "/acta-resumen",
    summary="Resumen completo para Acta PDF"
)
async def acta_resumen(
    fecha_inicio: str = Query(...),
    fecha_fin: str = Query(...),
    area: str = Query(...),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.cierre_periodo"))
):
    """
    Genera todos los datos necesarios para el PDF del Acta de Cierre.
    Tela de araña: cruza asistencias, horas_extras, jornadas_especiales y feriados.
    """
    try:
        params_area = []
        filtro_area = ""
        joins_area_asis = ""
        joins_area_he = ""
        if area and area != 'Todas':
            joins_area_asis = """
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.validado = 1
                    AND a.fecha >= ha.fecha_desde
                    AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR a.fecha <= ha.fecha_hasta)
                LEFT JOIN areas a ON ha.area_id = a.id
            """
            joins_area_he = """
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.validado = 1
                    AND he.fecha >= ha.fecha_desde
                    AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR he.fecha <= ha.fecha_hasta)
                LEFT JOIN areas a ON ha.area_id = a.id
            """
            filtro_area = " AND a.nombre = ?"
            params_area = [area]

        base_params = tuple([fecha_inicio, fecha_fin] + params_area)

        # ── 1. Resumen por estado ─────────────────────────────────────────────
        query_resumen = f"""
            SELECT
                COUNT(DISTINCT a.empleado_id)                                                        AS total_empleados,
                SUM(CASE WHEN a.estado = 'OK' THEN 1 ELSE 0 END)                                     AS dias_ok,
                SUM(CASE WHEN a.estado IN ('ATRASO','SALIDA_ADELANTADA','ATR_SAD') THEN 1 ELSE 0 END) AS dias_con_novedad,
                SUM(CASE WHEN a.estado = 'VACACIONES' THEN 1 ELSE 0 END)                             AS vacaciones,
                SUM(CASE WHEN a.estado LIKE 'LICENCIA%' THEN 1 ELSE 0 END)                           AS licencias,
                SUM(CASE WHEN a.estado = 'JORNADA_ESPECIAL' THEN 1 ELSE 0 END)                       AS jornadas_especiales,
                SUM(CASE WHEN a.estado = 'LIBRE' THEN 1 ELSE 0 END)                                  AS dias_libres_programados,
                SUM(CASE WHEN a.estado = 'FERIADO' THEN 1 ELSE 0 END)                                AS dias_feriado,
                SUM(CASE WHEN a.estado = 'INASISTENCIA' THEN 1 ELSE 0 END)                           AS inasistencias,
                SUM(CASE WHEN a.estado = 'ANOMALIA' THEN 1 ELSE 0 END)                               AS anomalias,
                SUM(CASE WHEN a.estado = 'EN_CURSO' THEN 1 ELSE 0 END)                               AS en_curso
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            {joins_area_asis}
            WHERE a.fecha BETWEEN ? AND ?
            {filtro_area}
        """
        resumen_row = await db.fetch_one(query_resumen, base_params)
        resumen = dict(resumen_row) if resumen_row else {}

        # ── 2. Listado de empleados del periodo ───────────────────────────────
        query_empleados = f"""
            SELECT DISTINCT
                e.id,
                e.rut,
                e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS nombre_completo,
                e.cargo,
                t.nombre AS turno_nombre
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            {joins_area_asis}
            LEFT JOIN asignacion_turnos at2 ON at2.empleado_id = e.id
                AND ? BETWEEN at2.fecha_inicio AND COALESCE(at2.fecha_fin, '2099-12-31')
            LEFT JOIN turnos t ON t.id = at2.turno_id
            WHERE a.fecha BETWEEN ? AND ?
            {filtro_area}
            ORDER BY e.apellido_paterno, e.apellido_materno
        """
        empleados_rows = await db.fetch_all(query_empleados, tuple([fecha_inicio, fecha_inicio, fecha_fin] + params_area))
        empleados = [dict(r) for r in empleados_rows]

        # ── 3. Horas extras aprobadas (totales + detalle) ─────────────────────
        query_he = f"""
            SELECT
                e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS nombre_completo,
                he.fecha,
                ROUND(he.minutos_autorizados / 60.0, 2) AS horas_aprobadas,
                he.estado
            FROM horas_extras he
            JOIN empleados e ON he.empleado_id = e.id
            {joins_area_he}
            WHERE he.fecha BETWEEN ? AND ?
              AND he.estado = 'APROBADO'
            {filtro_area}
            ORDER BY e.apellido_paterno, he.fecha
        """
        he_rows = await db.fetch_all(query_he, base_params)
        he_detalle = [dict(r) for r in he_rows]
        total_he_horas = round(sum(r['horas_aprobadas'] for r in he_detalle), 2)

        # ── 4. Feriados del periodo ───────────────────────────────────────────
        feriados_rows = await db.fetch_all(
            "SELECT fecha, descripcion FROM feriados WHERE fecha BETWEEN ? AND ? ORDER BY fecha",
            (fecha_inicio, fecha_fin)
        )
        feriados = [dict(r) for r in feriados_rows]

        # ── 5. Inasistencias aceptadas (se reciben opcionalmente del frontend) ─
        # El frontend envía el listado de inasistencias que el Jefe aceptó al cerrar.
        # Se incluyen en el Acta como anexo de trazabilidad para RRHH.
        inasistencias_rows = await db.fetch_all(
            f"""
            SELECT a.fecha,
                   e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS nombre_completo,
                   a.estado
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            {joins_area_asis}
            WHERE a.fecha BETWEEN ? AND ?
              AND a.estado = 'INASISTENCIA'
            {filtro_area}
            ORDER BY e.apellido_paterno, a.fecha
            """,
            base_params
        )
        inasistencias_aceptadas = [dict(r) for r in inasistencias_rows]

        # ── 6. Datos del cierre sellado ───────────────────────────────────────
        cierre_row = await db.fetch_one(
            "SELECT * FROM cierres_periodos WHERE fecha_inicio = ? AND fecha_fin = ? AND area = ? ORDER BY id DESC LIMIT 1",
            (fecha_inicio, fecha_fin, area)
        )
        cierre_info = dict(cierre_row) if cierre_row else {}

        return {
            "periodo": {"inicio": fecha_inicio, "fin": fecha_fin},
            "area": area,
            "generado_por": current_user.username,
            "fecha_generacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cierre_info": cierre_info,
            # Datos del acta
            "resumen": resumen,
            "empleados": empleados,
            "he_detalle": he_detalle,
            "total_he_horas": total_he_horas,
            "feriados": feriados,
            "inasistencias_aceptadas": inasistencias_aceptadas,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
