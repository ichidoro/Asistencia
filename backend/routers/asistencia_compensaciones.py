"""
Router - Asistencia: intercambios de días, compensaciones, compensar una inasistencia, perdonazo de deuda e
inasistencias disponibles. Separado de routers/asistencia.py en la etapa 6 de la auditoría, con el mismo código; las
direcciones siguen bajo /api/asistencia (asistencia.py incluye este router).
"""
from fastapi import Depends, Query, HTTPException
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from loguru import logger
from backend.services.asistencia_service import AsistenciaService
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.empleado import EmpleadoRepository
from backend.repositories.seguridad import SeguridadRepository
from backend.core.security import RequirePermission, SecurityContext, RequireAnyPermission
from backend.schemas.asistencia import CondonarDeudaRequest, IntercambioCreate, CompensarInasistenciaRequest, CompensacionCreate
from backend.routers.asistencia_comun import get_asistencia_service
from fastapi import APIRouter

router = APIRouter()


@router.post("/condonar-deuda/")
async def condonar_deuda(
    request: CondonarDeudaRequest,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Condona o revoca la condonación de la deuda horaria para uno o más empleados
    en un rango de fechas. Si la deuda es condonada, los minutos de deuda se fuerzan a 0.
    """
    if not request.empleados_ids:
        raise HTTPException(status_code=400, detail="Debe especificar al menos un empleado.")

    # Generar rango de fechas
    from datetime import datetime, timedelta
    try:
        start_date = datetime.strptime(request.fecha_inicio, "%Y-%m-%d").date()
        end_date = datetime.strptime(request.fecha_fin, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Use AAAA-MM-DD.")
    
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="La fecha de inicio no puede ser mayor a la fecha de fin.")

    # RLS & Cierre Check
    emp_repo = EmpleadoRepository(service.repository.db)
    for emp_id in request.empleados_ids:
        emp = await emp_repo.get_by_id(emp_id)
        if not emp:
            raise HTTPException(status_code=404, detail=f"Empleado con ID {emp_id} no encontrado")
        current_user.verificar_acceso_area(emp.area, f"empleado con ID {emp_id}")
        
        # Validar si el rango está cerrado para este empleado
        if await service.repository.check_rango_cerrado(request.fecha_inicio, request.fecha_fin, emp_id):
            raise HTTPException(
                status_code=403, 
                detail=f"El rango solicitado para el empleado {emp.nombre_completo} se encuentra cerrado o intersecta un periodo sellado."
            )

    dias_totales = (end_date - start_date).days + 1
    fechas = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(dias_totales)]

    # Aviso del cuadre: si la deuda de esos días ya está cubierta con horas extra, perdonarla libera esas horas y
    # pasan a pagarse. Se informa el monto y se exige confirmación (la persona decide con el dato a la vista).
    if request.tipo_condonacion > 0 and not request.confirmar:
        from backend.services.cuadre_service import CuadreService, hhmmss
        cuadre = CuadreService(service)
        avisos = []
        for emp_id in request.empleados_ids:
            try:
                t_ini, t_fin = await cuadre.tramo_de(request.fecha_inicio)
                lib = await cuadre.libro_empleado(emp_id, t_ini, t_fin)
            except Exception as e:
                logger.warning(f"[Cuadre] aviso de perdonazo no evaluado para {emp_id}: {e}")
                continue
            deuda_dias = sum(float(d.get('deuda') or 0.0) for d in lib.get('dias', []) if d.get('fecha') in fechas)
            cubierto = float(lib['libro'].get('cubierto') or 0.0)
            pendiente = float(lib['libro'].get('pendiente') or 0.0)
            if deuda_dias >= 1.0 and cubierto >= 1.0 and pendiente < 1.0:
                liberados = min(deuda_dias, cubierto)
                avisos.append({"empleado_id": emp_id, "nombre": lib.get('nombre'), "minutos_liberados": round(liberados, 2),
                               "texto": f"La deuda de {lib.get('nombre')} ya está cubierta con horas extra. Si la perdonas, "
                                        f"{hhmmss(liberados)} de esas horas pasan a pagarse."})
        if avisos:
            raise HTTPException(status_code=409, detail={"codigo": "deuda_cubierta", "avisos": avisos})

    try:
        # 1. Marcar condonacion en la BD en un solo batch (N+1 optimization)
        params = [(request.tipo_condonacion, emp_id, fecha_str) for emp_id in request.empleados_ids for fecha_str in fechas]
        await AsistenciaRepository(service.repository.db).set_deuda_condonada(params)

        # 2. Reprocesar los días de los empleados en bulk usando procesar_dia
        for fecha_str in fechas:
            await service.procesar_dia(
                fecha=fecha_str,
                force=True,
                empleado_ids=set(request.empleados_ids),
            )

        accion = "condonada" if request.tipo_condonacion > 0 else "revocada"
        try:
            from backend.repositories.seguridad import SeguridadRepository
            import json as _json
            await SeguridadRepository(service.repository.db).log_auditoria(
                current_user.user_id, current_user.username, "CONDONAR_DEUDA" if request.tipo_condonacion > 0 else "REVOCAR_CONDONACION",
                "MARCACIONES", _json.dumps({"empleados_ids": request.empleados_ids, "desde": request.fecha_inicio, "hasta": request.fecha_fin,
                                            "tipo": request.tipo_condonacion, "confirmado": request.confirmar}, ensure_ascii=False))
        except Exception as audit_err:
            logger.warning(f"[Cuadre] Auditoría del perdonazo no registrada: {audit_err}")
        return {"success": True, "message": f"Deuda {accion} correctamente para {len(request.empleados_ids)} empleado(s) en {dias_totales} día(s)."}
    except Exception as e:
        logger.error(f"Error al condonar deuda: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/intercambios/")
async def get_intercambios(
    fecha_inicio: str = Query(..., description="Fecha inicial AAAA-MM-DD"),
    fecha_fin: str = Query(..., description="Fecha final AAAA-MM-DD"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequireAnyPermission(["marcaciones.ver", "marcaciones.intercambio"]))
):
    """Obtiene los intercambios de días en un rango de fechas."""
    intercambios = await service.repository.get_intercambios(fecha_inicio, fecha_fin)
    areas_filtro = current_user.get_areas_filter()
    if areas_filtro is not None:
        intercambios = [i for i in intercambios if i.get('area_nombre') in areas_filtro]
    return {"success": True, "data": intercambios}


@router.post("/intercambios/")
async def create_intercambio(
    data: IntercambioCreate,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.intercambio"))
):
    """Crea un nuevo intercambio de días y reprocesa ambas fechas."""
    # RLS Check
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(data.empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Empleado con ID {data.empleado_id} no encontrado")
    current_user.verificar_acceso_area(emp.area, "este empleado")

    # Cierre Check
    if await service.repository.check_rango_cerrado(data.fecha_origen, data.fecha_origen, data.empleado_id):
        raise HTTPException(status_code=403, detail="La fecha de origen se encuentra en un período cerrado.")
    if await service.repository.check_rango_cerrado(data.fecha_destino, data.fecha_destino, data.empleado_id):
        raise HTTPException(status_code=403, detail="La fecha de destino se encuentra en un período cerrado.")

    # Mapear parámetros correctamente para la BD
    payload = {
        'empleado_solicitante_id': data.empleado_id,
        'empleado_receptor_id': data.empleado_id,
        'fecha_origen': data.fecha_origen,
        'fecha_destino': data.fecha_destino,
        'motivo': data.observaciones,
        'usuario_id': current_user.user_id
    }
    
    intercambio_id = await service.repository.create_intercambio(payload)
    
    # Reprocesar ambas fechas (origen y destino) para que el Interceptor actúe
    await service.reprocesar_periodo_empleado(
        empleado_id=data.empleado_id,
        fecha_inicio=data.fecha_origen,
        fecha_fin=data.fecha_origen,
        force=True
    )
    await service.reprocesar_periodo_empleado(
        empleado_id=data.empleado_id,
        fecha_inicio=data.fecha_destino,
        fecha_fin=data.fecha_destino,
        force=True
    )
    
    return {"success": True, "message": "Intercambio registrado y fechas reprocesadas", "id": intercambio_id}


@router.delete("/intercambios/{intercambio_id}/")
async def delete_intercambio(
    intercambio_id: int,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.intercambio"))
):
    """Elimina un intercambio de días."""
    db = service.repository.db
    # Obtener el intercambio para saber qué fechas reprocesar
    intercambio = await service.repository.get_intercambio_by_id(intercambio_id)
    if not intercambio:
        raise HTTPException(status_code=404, detail="Intercambio no encontrado")
        
    emp_id = intercambio['empleado_solicitante_id']
    
    # RLS Check
    emp_repo = EmpleadoRepository(db)
    emp = await emp_repo.get_by_id(emp_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado asociado al intercambio no encontrado")
    current_user.verificar_acceso_area(emp.area, "este empleado")

    # Cierre Check
    if await service.repository.check_rango_cerrado(intercambio['fecha_origen'], intercambio['fecha_origen'], emp_id):
        raise HTTPException(status_code=403, detail="La fecha de origen se encuentra en un período cerrado.")
    if await service.repository.check_rango_cerrado(intercambio['fecha_destino'], intercambio['fecha_destino'], emp_id):
        raise HTTPException(status_code=403, detail="La fecha de destino se encuentra en un período cerrado.")

    await service.repository.delete_intercambio(intercambio_id)
    
    # Reprocesar sin el intercambio para volver al estado natural
    await service.reprocesar_periodo_empleado(
        empleado_id=emp_id,
        fecha_inicio=intercambio['fecha_origen'],
        fecha_fin=intercambio['fecha_origen'],
        force=True
    )
    await service.reprocesar_periodo_empleado(
        empleado_id=emp_id,
        fecha_inicio=intercambio['fecha_destino'],
        fecha_fin=intercambio['fecha_destino'],
        force=True
    )
    return {"success": True, "message": "Intercambio eliminado y fechas devueltas a estado natural"}


@router.get("/compensaciones/bolsa/")
async def get_bolsa_he_disponible(
    empleado_id: int = Query(..., description="ID del empleado"),
    fecha: str = Query(..., description="Fecha de la inasistencia YYYY-MM-DD"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.compensar"))
):
    """Obtiene el saldo de bolsa de horas extras disponible para el empleado en el periodo de la fecha dada."""
    # RLS Check
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    current_user.verificar_acceso_area(emp.area, "este empleado")

    periodo = await service.repository.get_periodo_por_fecha(fecha)
    if not periodo:
        raise HTTPException(status_code=404, detail="No se encontró un periodo para la fecha especificada.")

    bolsa = await service.repository.get_bolsa_he_disponible(
        empleado_id, periodo["fecha_inicio"], periodo["fecha_fin"]
    )
    bolsa = await _bolsa_despues_de_deuda(service, empleado_id, fecha, bolsa)
    return {"success": True, "data": bolsa, "periodo": periodo}


async def _bolsa_despues_de_deuda(service: AsistenciaService, empleado_id: int, fecha: str, bolsa: Dict[str, Any]) -> Dict[str, Any]:
    """Regla del dueño (26-10-2026): solo se compensan inasistencias con las horas extra que sobran después de pagar toda la deuda."""
    from backend.services.compensar_inasistencia import bolsa_despues_de_deuda
    return await bolsa_despues_de_deuda(service, empleado_id, fecha, bolsa)


async def _empleado_visible(service: AsistenciaService, current_user: SecurityContext, empleado_id: int):
    emp = await EmpleadoRepository(service.repository.db).get_by_id(empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    current_user.verificar_acceso_area(emp.area, "este empleado")
    return emp


@router.get("/compensar-inasistencia/opciones/")
async def opciones_compensar_inasistencia(
    empleado_id: int = Query(...),
    fecha: str = Query(..., description="Día de la inasistencia AAAA-MM-DD"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.compensar"))
):
    """Con qué se puede compensar una inasistencia: una jornada EXTRA del tramo (día completo) o horas extra (minuto a minuto)."""
    await _empleado_visible(service, current_user, empleado_id)
    from backend.services import compensar_inasistencia as ci
    return {"success": True, "data": await ci.opciones(service, empleado_id, fecha)}


@router.post("/compensar-inasistencia/")
async def compensar_inasistencia(
    req: CompensarInasistenciaRequest,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.compensar"))
):
    """Compensa una inasistencia con una jornada EXTRA (que se gasta) o con horas extra que cubran todo el turno."""
    await _empleado_visible(service, current_user, req.empleado_id)
    from backend.services import compensar_inasistencia as ci
    try:
        return await ci.compensar(service, req.empleado_id, req.fecha, req.modo, req.fecha_jornada, req.observaciones,
                                  current_user.username, current_user.user_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.delete("/compensar-inasistencia/")
async def quitar_compensacion_inasistencia(
    empleado_id: int = Query(...),
    fecha: str = Query(..., description="Día de la inasistencia AAAA-MM-DD"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.compensar"))
):
    """Quita la compensación del día: la jornada usada vuelve a ser EXTRA y las horas extra quedan libres."""
    await _empleado_visible(service, current_user, empleado_id)
    from backend.services import compensar_inasistencia as ci
    try:
        return await ci.quitar(service, empleado_id, fecha, current_user.username, current_user.user_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.get("/compensaciones/")
async def list_compensaciones(
    fecha_inicio: str = Query(..., description="Fecha inicio YYYY-MM-DD"),
    fecha_fin: str = Query(..., description="Fecha fin YYYY-MM-DD"),
    empleado_id: Optional[int] = Query(None, description="Filtrar por empleado"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequireAnyPermission(["marcaciones.ver", "marcaciones.compensar"]))
):
    """Lista las compensaciones de inasistencia en un rango de fechas."""
    compensaciones = await service.repository.get_compensaciones(fecha_inicio, fecha_fin)
    
    # Filtrar por RLS y empleado_id si aplica
    if empleado_id:
        compensaciones = [c for c in compensaciones if c['empleado_id'] == empleado_id]
        
    areas_filtro = current_user.get_areas_filter()
    if areas_filtro is not None:
        emp_repo = EmpleadoRepository(service.repository.db)
        res = []
        for c in compensaciones:
            emp = await emp_repo.get_by_id(c['empleado_id'])
            if emp and emp.area in areas_filtro:
                res.append(c)
        compensaciones = res

    return {"success": True, "data": compensaciones}


@router.post("/compensaciones/")
async def create_compensacion(
    data: CompensacionCreate,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.compensar"))
):
    """Crea una nueva compensación de inasistencia con la bolsa de horas extras del periodo."""
    db = service.repository.db
    # RLS Check
    emp_repo = EmpleadoRepository(db)
    emp = await emp_repo.get_by_id(data.empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    current_user.verificar_acceso_area(emp.area, "este empleado")

    # Cierre Check
    if await service.repository.check_rango_cerrado(data.fecha_inasistencia, data.fecha_inasistencia, data.empleado_id):
        raise HTTPException(status_code=403, detail="La fecha de inasistencia se encuentra en un período cerrado.")

    # Obtener periodo para la fecha de inasistencia
    periodo = await service.repository.get_periodo_por_fecha(data.fecha_inasistencia)
    if not periodo:
        raise HTTPException(status_code=400, detail="No se encontró un periodo para la fecha de inasistencia.")

    # Las horas extra deben alcanzar: se compensa minuto a minuto, sin compensación parcial (orden del dueño, 27-10-2026)
    bolsa = await service.repository.get_bolsa_he_disponible(
        data.empleado_id, periodo["fecha_inicio"], periodo["fecha_fin"]
    )
    bolsa = await _bolsa_despues_de_deuda(service, data.empleado_id, data.fecha_inasistencia, bolsa)
    if round(data.minutos) > round(bolsa["minutos_disponibles"]):
        raise HTTPException(
            status_code=400,
            detail=f"Saldo insuficiente de horas extras en la bolsa del periodo (Disponible: {bolsa['minutos_disponibles']} min)."
        )

    # Registrar la compensación
    payload = {
        'empleado_id': data.empleado_id,
        'fecha_inasistencia': data.fecha_inasistencia,
        'minutos': data.minutos,
        'observaciones': data.observaciones,
        'usuario_id': current_user.user_id
    }
    
    compensacion_id = await service.repository.create_compensacion(payload)
    
    # Reprocesar fecha de inasistencia
    await service.reprocesar_periodo_empleado(
        empleado_id=data.empleado_id,
        fecha_inicio=data.fecha_inasistencia,
        fecha_fin=data.fecha_inasistencia,
        force=True
    )
    
    # Registrar auditoría
    try:
        await SeguridadRepository(db).log_auditoria(
            current_user.user_id, current_user.username, 'CREATE_COMPENSACION', 'Marcaciones',
            f"Compensación ID {compensacion_id}: Inasistencia del {data.fecha_inasistencia} cubierta con {data.minutos} min de la bolsa de HE")
    except Exception as aud_err:
        logger.warning(f"No se pudo registrar auditoría de compensación: {aud_err}")
        
    return {"success": True, "message": "Compensación registrada y asistencia recalculada", "id": compensacion_id}


@router.delete("/compensaciones/{compensacion_id}/")
async def delete_compensacion(
    compensacion_id: int,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.compensar"))
):
    """Elimina una compensación y devuelve la fecha a su estado natural."""
    db = service.repository.db
    # Obtener el registro para saber a qué empleado y fechas corresponde
    c = await service.repository.get_compensacion_by_id(compensacion_id)
    if not c:
        raise HTTPException(status_code=404, detail="Compensación no encontrada")
        
    empleado_id = c['empleado_id']
    fecha_inasistencia = c['fecha_inasistencia']
    
    # RLS Check
    emp_repo = EmpleadoRepository(db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    current_user.verificar_acceso_area(emp.area, "este empleado")

    # Cierre Check
    if await service.repository.check_rango_cerrado(fecha_inasistencia, fecha_inasistencia, empleado_id):
        raise HTTPException(status_code=403, detail="La fecha de inasistencia se encuentra en un período cerrado.")

    # Eliminar
    await service.repository.delete_compensacion(compensacion_id)
    
    # Reprocesar fecha de inasistencia
    await service.reprocesar_periodo_empleado(
        empleado_id=empleado_id,
        fecha_inicio=fecha_inasistencia,
        fecha_fin=fecha_inasistencia,
        force=True
    )
    
    # Registrar auditoría
    try:
        await SeguridadRepository(db).log_auditoria(
            current_user.user_id, current_user.username, 'DELETE_COMPENSACION', 'Marcaciones',
            f"Eliminada compensación ID {compensacion_id}: Inasistencia del {fecha_inasistencia} desmarcada de la bolsa de HE")
    except Exception as aud_err:
        logger.warning(f"No se pudo registrar auditoría de eliminación de compensación: {aud_err}")
        
    return {"success": True, "message": "Compensación eliminada y asistencia recalculada"}


@router.get("/inasistencias-disponibles/{empleado_id}/")
async def get_inasistencias_disponibles(
    empleado_id: int,
    fecha_origen: Optional[str] = Query(None, description="AAAA-MM-DD"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """Retorna las fechas con INASISTENCIA limpia dentro del período activo para un empleado."""
    db = service.repository.db
    emp_repo = EmpleadoRepository(db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    current_user.verificar_acceso_area(emp.area, "este empleado")

    # Obtener asistencias en estado INASISTENCIA o FALTA
    rows = await service.repository.get_inasistencias_sin_consumir(empleado_id, fecha_origen)

    clean_dates = []
    for r in rows:
        f_str = r['fecha']
        # Verificar que no tenga Licencias/Vacaciones activas. La tabla no tiene «estado»: una justificación registrada
        # vale (auditoría del 15-11-2026: la condición «estado = 'APROBADA'» hacía caer siempre este selector).
        just = await service.repository.get_justificacion_del_dia(empleado_id, f_str)
        if not just:
            clean_dates.append({
                'fecha': f_str,
                'estado': r['estado'],
                'observaciones': r['observaciones']
            })

    return {"success": True, "inasistencias": clean_dates}
