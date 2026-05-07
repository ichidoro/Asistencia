"""
Router - Empleados
Endpoints REST API para gestión de empleados
"""

from loguru import logger
from fastapi import APIRouter, Depends, Query, Path, status, HTTPException
from typing import Optional, List

from backend.core.database import Database, get_db
from backend.repositories.empleado import EmpleadoRepository
from backend.services.empleado_service import EmpleadoService
from backend.schemas.empleado import (
    EmpleadoCreate,
    EmpleadoUpdate,
    EmpleadoResponse,
    EmpleadoListResponse,
    EmpleadoLookupResponse,
    VencimientoRequest,
    ConfirmarAreaRequest,
    ReincorporarRequest
)
from backend.repositories.configuracion import ConfiguracionRepository
from backend.services.configuracion_service import ConfiguracionService
from backend.services.notification_service import NotificationService
from backend.core.security import SecurityContext, RequirePermission


#==================================
# ROUTER
router = APIRouter(
    prefix="/empleados",
    tags=["Empleados"]
)


# ============================================
# DEPENDENCY INJECTION
# ============================================

async def get_empleado_service(db: Database = Depends(get_db)) -> EmpleadoService:
    """Dependency para inyectar el servicio de empleados"""
    emp_repository = EmpleadoRepository(db)
    
    # Notificaciones
    notification_service = NotificationService()
    
    # Inyectar servicio de asistencia para Auto-Healing (Reprocesamiento)
    from backend.repositories.asistencia import AsistenciaRepository
    from backend.services.asistencia_service import AsistenciaService
    asis_service = AsistenciaService(AsistenciaRepository(db))
    
    # Inyectar servicio de configuración
    config_repository = ConfiguracionRepository(db)
    config_service = ConfiguracionService(config_repository, notification_service)
    
    return EmpleadoService(emp_repository, config_service, notification_service, asis_service)


# ============================================
# ENDPOINTS
# ============================================

@router.get(
    "/cumpleanos/",
    response_model=List[EmpleadoResponse],
    summary="Obtener cumpleaños",
    description="Retorna lista de empleados activos ordenados por fecha de cumpleaños (Día/Mes)."
)
async def get_cumpleanos(
    month: Optional[int] = Query(None, ge=1, le=12, description="Filtrar por mes (1-12)"),
    area: Optional[str] = Query(None, description="Filtrar por área"),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    # RLS
    areas_permitidas = current_user.filtrar_areas([area] if area else None) if not current_user.alcance_global else ([area] if area else None)
    if area and not current_user.alcance_global and area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos para el área solicitada")

    empleados = await service.get_birthdays(month, area, areas_permitidas=current_user.areas if not current_user.alcance_global else None)
    return [EmpleadoResponse(**e.to_dict()) for e in empleados]


@router.get(
    "/lookup/",
    response_model=List[EmpleadoLookupResponse],
    summary="Búsqueda rápida de empleados",
    description="Retorna una lista mínima (id, nombre, rut) optimizada para dropdowns y filtros."
)
async def get_empleados_lookup(
    area: Optional[str] = Query(None, description="Filtrar por área"),
    activo: Optional[bool] = Query(True, description="Filtrar por estado activo"),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    return await service.get_lookup(area, activo, areas_permitidas=current_user.areas)


@router.get(
    "/vencimientos/",
    response_model=List[dict],
    summary="Obtener contratos por vencer",
    description="Retorna empleados activos con fecha de salida próxima (vencimiento de contrato)."
)
async def get_contratos_por_vencer(
    days: int = Query(30, description="Días a futuro para buscar vencimientos"),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    """
    Retorna empleados activos con fecha de salida próxima o vencida con RLS.
    """
    return await service.get_expiring_contracts(days, areas_permitidas=current_user.areas if not current_user.alcance_global else None)


@router.get(
    "/historial-bajas/",
    summary="Obtener historial de bajas",
    description="Retorna lista de empleados cuyos contratos finalizaron o finalizarán en el mes especificado."
)
async def get_historial_bajas(
    month: int = Query(..., ge=1, le=12, description="Mes (1-12)"),
    year: int = Query(..., ge=2000, description="Año (YYYY)"),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    """
    Obtener historial de bajas del mes con RLS.
    """
    return await service.get_terminated_by_month(month, year, areas_permitidas=current_user.areas if not current_user.alcance_global else None)


@router.post(
    "/{empleado_id}/procesar-vencimiento/",
    response_model=EmpleadoResponse,
    summary="Procesar vencimiento de contrato",
    description="Permite renovar, desactivar o pasar a indefinido un contrato por vencer."
)
async def procesar_vencimiento(
    request: VencimientoRequest,
    empleado_id: int = Path(..., gt=0),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.editar"))
):
    # RLS: Verificar pertenencia
    emp = await service.get_empleado(empleado_id)
    if not current_user.alcance_global and emp.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos para editar este empleado")

    empleado = await service.procesar_vencimiento(
        empleado_id=empleado_id,
        accion=request.accion,
        nueva_fecha=request.nueva_fecha
    )
    return EmpleadoResponse(**empleado.to_dict())


class BajaRequest(VencimientoRequest):
    motivo: str

@router.post(
    "/{empleado_id}/baja/",
    response_model=EmpleadoResponse,
    summary="Registrar baja de empleado",
    description="Registra la renuncia o despido de un empleado, desactivándolo si corresponde."
)
async def registrar_baja_empleado(
    request: BajaRequest,
    empleado_id: int = Path(..., gt=0),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.editar"))
):
    # RLS
    emp = await service.get_empleado(empleado_id)
    if not current_user.alcance_global and emp.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos para dar de baja a este empleado")

    empleado = await service.registrar_baja(
        empleado_id=empleado_id,
        fecha_salida=request.nueva_fecha, # Reutilizamos campo nueva_fecha del schema base
        motivo=request.motivo
    )
    return EmpleadoResponse(**empleado.to_dict())


@router.post(
    "/",
    response_model=EmpleadoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear empleado",
    description="Crea un nuevo empleado en el sistema"
)
async def crear_empleado(
    empleado: EmpleadoCreate,
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.crear"))
):
    # RLS: Validar que el área elegida sea permitida para el usuario
    if not current_user.alcance_global and empleado.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail=f"No tiene permisos para crear empleados en el área {empleado.area}")

    empleado_created = await service.create_empleado(empleado)
    return EmpleadoResponse(**empleado_created.to_dict())


@router.get(
    "/",
    response_model=EmpleadoListResponse,
    summary="Listar empleados",
    description="Obtiene lista de empleados con paginación"
)
async def listar_empleados(
    skip: int = Query(0, ge=0, description="Número de registros a saltar"),
    limit: int = Query(100, ge=1, le=1000, description="Límite de registros"),
    activo: Optional[bool] = Query(None, description="Filtrar por estado activo/inactivo"),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    """
    Listar todos los empleados con paginación.
    
    Parámetros de query:
    - **skip**: Offset para paginación (default: 0)
    - **limit**: Límite de resultados (default: 100, max: 1000)
    - **activo**: Filtrar por activo=true o activo=false (opcional)
    """
    empleados, total = await service.get_all_empleados(skip, limit, activo, areas_permitidas=current_user.areas)
    
    return EmpleadoListResponse(
        empleados=[EmpleadoResponse(**e.to_dict()) for e in empleados],
        total=total,
        skip=skip,
        limit=limit
    )


@router.get(
    "/areas/",
    summary="Listar áreas",
    description="Obtiene lista de todas las áreas registradas localmente con RLS"
)
async def listar_areas(
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
) -> List[str]:
    """
    Listar todas las áreas únicas considerando RLS.
    """
    if not current_user.alcance_global:
        return current_user.areas or []
    return await service.get_distinct_areas()


@router.get(
    "/search/",
    response_model=EmpleadoListResponse,
    summary="Buscar empleados",
    description="Busca empleados por nombre, RUT, cargo, área o compañía"
)
async def buscar_empleados(
    q: Optional[str] = Query(None, description="Búsqueda por nombre, RUT o cargo"),
    area: Optional[str] = Query(None, description="Filtrar por área"),
    compania: Optional[str] = Query(None, description="Filtrar por compañía"),
    activo: Optional[bool] = Query(None, description="Filtrar por estado"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    sort_by: str = Query("nombre", description="Columna para ordenar: nombre, cargo, area, etc"),
    order: str = Query("asc", description="Orden: asc o desc"),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    """
    Buscar empleados con filtros.
    
    Parámetros de query:
    - **q**: Texto a buscar en nombre, RUT o cargo
    - **area**: Filtrar por área específica
    - **compania**: Filtrar por compañía específica
    - **activo**: Filtrar por estado activo/inactivo
    - **skip**: Offset para paginación
    - **limit**: Límite de resultados
    - **sort_by**: Columna para ordenar
    - **order**: Dirección del orden (asc/desc)
    """
    empleados, total = await service.search_empleados(
        q=q,
        area=area,
        compania=compania,
        activo=activo,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        order=order,
        areas_permitidas=current_user.areas
    )
    
    return EmpleadoListResponse(
        empleados=[EmpleadoResponse(**e.to_dict()) for e in empleados],
        total=total,
        skip=skip,
        limit=limit
    )


@router.get(
    "/matrix/",
    summary="Obtener matriz de bonos",
    description="Obtiene empleados y sus asignaciones de bonos en formato matriz",
)
async def obtener_matriz_bonos(
    q: Optional[str] = Query(None, description="Búsqueda"),
    area: Optional[str] = Query(None, description="Filtrar por área"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.bonos"))
):
    """
    Retorna:
    - columns: Lista de bonos activos (headers)
    - data: Lista de empleados con sus asignaciones (filas)
    - total: Total de empleados encontrados
    """
    return await service.get_empleados_matrix(
        q=q,
        area=area,
        skip=skip,
        limit=limit,
        areas_permitidas=current_user.areas
    )


@router.get(
    "/metadata/",
    summary="Obtener metadatos de empleados",
    description="Obtiene listas únicas de cargos, áreas y compañías para filtros"
)
async def obtener_metadatos(
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    """
    Obtener metadatos para filtros.
    
    Retorna:
    - cargos: Lista única de cargos
    - areas: Lista única de áreas
    - companias: Lista única de compañías
    """
    return await service.get_metadata(areas_permitidas=current_user.areas if not current_user.alcance_global else None)


@router.get(
    "/stats/",
    summary="Estadísticas de empleados",
    description="Obtiene estadísticas generales de empleados"
)
async def estadisticas_empleados(
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    """
    Obtener estadísticas de empleados.
    
    Retorna:
    - Total de empleados
    - Empleados activos
    - Empleados inactivos
    """
    return await service.get_stats(areas_permitidas=current_user.areas if not current_user.alcance_global else None)




@router.get(
    "/{empleado_id}/",
    response_model=EmpleadoResponse,
    summary="Obtener empleado",
    description="Obtiene los datos de un empleado específico por ID"
)
async def obtener_empleado(
    empleado_id: int = Path(..., gt=0, description="ID del empleado"),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    """
    Obtener un empleado por su ID.
    
    Retorna 404 si el empleado no existe.
    """
    empleado = await service.get_empleado(empleado_id)
    # RLS
    if not current_user.alcance_global and empleado.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos para ver este empleado")
         
    return EmpleadoResponse(**empleado.to_dict())


@router.get(
    "/{empleado_id}/historial-areas/",
    summary="Obtener historial de áreas",
    description="Retorna el historial completo de áreas de un empleado."
)
async def obtener_historial_areas(
    empleado_id: int = Path(..., gt=0),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    # RLS: Verificar pertenencia
    emp = await service.get_empleado(empleado_id)
    if not current_user.alcance_global and emp.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos para ver el historial de este empleado")

    return await service.repository.get_historial_areas(empleado_id)


@router.post(
    "/confirmar-cambio-area/",
    summary="Confirmar cambio de área",
    description="Valida un cambio de área pendiente, estableciendo la fecha efectiva."
)
async def confirmar_cambio_area(
    request: ConfirmarAreaRequest,
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.editar"))
):
    # 1. Buscar el registro histórico específico
    # Usamos DB directa para obtener el registro por ID (fetch_one garantiza dict)
    pendiente = await service.repository.db.fetch_one(
        "SELECT * FROM historial_areas WHERE id = ?",
        (request.historial_id,)
    )
    
    if not pendiente:
        raise HTTPException(status_code=404, detail="No se encontró el registro histórico")
    
    empleado_id = pendiente['empleado_id']
    nueva_area = pendiente['area']

    # RLS: Verificar pertenencia
    emp = await service.get_empleado(empleado_id)
    if not current_user.alcance_global and emp.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos para editar este empleado")

    # 2. Buscar el registro actual para cerrarlo
    historial = await service.repository.get_historial_areas(empleado_id)
    actual = next((h for h in historial if h['es_actual']), None)
    
    from datetime import datetime, timedelta
    fecha_dt = datetime.strptime(request.fecha_efectiva, "%Y-%m-%d")
    fecha_hasta_anterior = (fecha_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    
    async with service.repository.db.transaction():
        # 2.1 Validación Crítica: No permitir fecha antes del ingreso
        if emp.fecha_ingreso and request.fecha_efectiva < emp.fecha_ingreso:
             raise HTTPException(
                 status_code=400, 
                 detail=f"Error de consistencia: La fecha efectiva ({request.fecha_efectiva}) no puede ser anterior a la fecha de ingreso del empleado ({emp.fecha_ingreso})."
             )

        # 2.2 Cerrar el registro de área anterior
        if actual:
            await service.repository.update_historial_area(
                actual['id'],
                fecha_hasta=fecha_hasta_anterior,
                es_actual=False
            )
        
        # 2.3 Validar el nuevo registro de área
        await service.repository.update_historial_area(
            request.historial_id,
            fecha_desde=request.fecha_efectiva,
            es_actual=True,
            validado=True
        )
        
        # 2.4 Sincronizar campo 'area' en tabla principal de empleados
        from backend.schemas.empleado import EmpleadoUpdate
        await service.update_empleado(empleado_id, EmpleadoUpdate(area=nueva_area))

        # 2.5 Asignación inmediata de Turno (Flujo Unificado)
        if request.turno_id:
            logger.info(f"📋 Asignación atómica de turno {request.turno_id} para empleado {empleado_id} desde {request.fecha_efectiva}")
            from backend.repositories.turno import TurnoRepository
            from backend.schemas.turno import AsignacionCreate
            
            turno_repo = TurnoRepository(service.repository.db)
            # create_asignacion con reemplazar=True se encarga de cerrar el turno vigente en esa fecha
            nueva_asig = AsignacionCreate(
                empleado_id=empleado_id,
                turno_id=request.turno_id,
                fecha_inicio=request.fecha_efectiva,
                fecha_fin=None,
                reemplazar=True
            )
            await turno_repo.create_asignacion(nueva_asig)

    # 3. Gatillar reprocesamiento si es retroactivo
    from datetime import date
    hoy = date.today().strftime("%Y-%m-%d")
    
    if request.fecha_efectiva < hoy:
        logger.info(f"🔄 Cambio de área retroactivo detectado ({request.fecha_efectiva}). Gatillando reprocesamiento para ID {empleado_id}")
        try:
            from backend.services.asistencia_service import AsistenciaService
            from backend.repositories.asistencia import AsistenciaRepository
            asis_service = AsistenciaService(AsistenciaRepository(service.repository.db))
            
            # Reprocesar desde la fecha efectiva hasta hoy
            await asis_service.reprocesar_periodo_empleado(
                empleado_id=empleado_id,
                fecha_inicio=request.fecha_efectiva,
                fecha_fin=hoy,
                force=True
            )
            logger.success(f"✅ Reprocesamiento retroactivo completado para ID {empleado_id}")
        except Exception as e:
            logger.error(f"❌ Error en reprocesamiento retroactivo: {e}")
            # No lanzamos excepción para no revertir el cambio de área, ya que es una tarea secundaria

    return {"status": "success", "message": "Cambio de área confirmado y asistencia recalculada si aplica"}


@router.get(
    "/rut/{rut}/",
    response_model=EmpleadoResponse,
    summary="Obtener empleado por RUT",
    description="Obtiene los datos de un empleado específico por RUT"
)
async def obtener_empleado_por_rut(
    rut: str = Path(..., description="RUT del empleado"),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.ver"))
):
    """
    Obtener un empleado por su RUT.
    
    Retorna 404 si el empleado no existe.
    """
    empleado = await service.get_empleado_by_rut(rut)
    # RLS
    if not current_user.alcance_global and empleado.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos para ver este empleado")

    return EmpleadoResponse(**empleado.to_dict())


@router.put(
    "/{empleado_id}/",
    summary="Actualizar empleado",
    description="Actualiza los datos de un empleado existente"
)
async def actualizar_empleado(
    empleado_id: int = Path(..., gt=0, description="ID del empleado"),
    empleado_data: EmpleadoUpdate = ...,
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.editar"))
):
    """
    Actualizar un empleado existente.
    
    Solo se actualizan los campos que se envían en el request.
    Los campos omitidos mantienen su valor actual.
    
    Retorna 404 si el empleado no existe.
    """
    # RLS: El empleado debe pertenecer a sus áreas
    emp_actual = await service.get_empleado(empleado_id)
    if not current_user.alcance_global and emp_actual.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos para editar este empleado")

    # RLS: Si está cambiando de área, la nueva área también debe ser permitida
    if empleado_data.area and not current_user.alcance_global:
        if empleado_data.area not in (current_user.areas or []):
             raise HTTPException(status_code=403, detail="No puede asignar un área fuera de su alcance")

    empleado = await service.update_empleado(empleado_id, empleado_data)
    resp = EmpleadoResponse(**empleado.to_dict())
    # Incluir bonos asignados en la respuesta (campo transitorio)
    bonos = getattr(empleado, '_bonos_asignados', [])
    return {**resp.model_dump(), "bonos_asignados": bonos}



@router.delete(
    "/{empleado_id}/",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desactivar empleado",
    description="Desactiva un empleado (soft delete)"
)
async def eliminar_empleado(
    empleado_id: int = Path(..., gt=0, description="ID del empleado"),
    hard: bool = Query(False, description="Si true, elimina permanentemente"),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.eliminar"))
):
    """
    Eliminar un empleado.
    
    Por defecto hace soft delete (marca como inactivo).
    Si hard=true, elimina permanentemente del sistema.
    
    Retorna 404 si el empleado no existe.
    """
    # RLS
    emp = await service.get_empleado(empleado_id)
    if not current_user.alcance_global and emp.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos para desactivar este empleado")

    await service.delete_empleado(empleado_id, hard=hard)
    return None


@router.post(
    "/{empleado_id}/activate/",
    response_model=EmpleadoResponse,
    summary="Reactivar empleado",
    description="Reactivar un empleado que estaba inactivo"
)
async def reactivar_empleado(
    empleado_id: int = Path(..., gt=0, description="ID del empleado"),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.reincorporar"))
):
    """
    Reactivar un empleado inactivo.
    
    Retorna 404 si el empleado no existe.
    """
    # RLS
    emp = await service.get_empleado(empleado_id)
    if not current_user.alcance_global and emp.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos para reactivar este empleado")

    empleado = await service.activate_empleado(empleado_id)
    return EmpleadoResponse(**empleado.to_dict())


@router.post(
    "/{empleado_id}/reincorporar/",
    response_model=EmpleadoResponse,
    summary="Reincorporar empleado (Wizard)",
    description="Procesa la reincorporación de un empleado mediante el Wizard asistido (Periodos + Area + Turno)."
)
async def reincorporar_empleado(
    request: ReincorporarRequest,
    empleado_id: int = Path(..., gt=0),
    service: EmpleadoService = Depends(get_empleado_service),
    current_user: SecurityContext = Depends(RequirePermission("empleados.reincorporar"))
):
    """
    Endpoint principal para el flujo de Reincorporación.
    Ejecuta el cambio de estado, periodo legal, área y turno en un solo paso atómico.
    """
    # RLS: Validar que el área de destino sea permitida
    if not current_user.alcance_global and request.area not in (current_user.areas or []):
         raise HTTPException(
             status_code=403, 
             detail=f"No tiene permisos para reincorporar empleados en el área {request.area}"
         )

    empleado = await service.reincorporar_empleado(empleado_id, request)
    return EmpleadoResponse(**empleado.to_dict())
