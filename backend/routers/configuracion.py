import re
from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks, Query
from typing import List, Dict, Any
from backend.services.configuracion_service import ConfiguracionService
from backend.repositories.configuracion import ConfiguracionRepository
from backend.core.database import get_db, Database
from backend.schemas.bono import BonoCreate, BonoResponse
from backend.schemas.justificacion import JustificacionTipoCreate, JustificacionTipoResponse, JustificacionCreate, JustificacionResponse
from backend.schemas.pagador import PagadorResponse, PagadorCreate
from backend.schemas.periodo_rrhh import PeriodoRRHHCreate, PeriodoRRHHResponse
from backend.services.calendario_service import CalendarioService
from typing import Optional
from loguru import logger
from backend.services.notification_service import NotificationService
from backend.core.events import scheduler
from backend.core.security import SecurityContext, RequirePermission, RequireAnyPermission, get_current_user

router = APIRouter(
    prefix="/configuracion",
    tags=["Configuración"]
)

# ============================================
# DEPENDENCIAS
# ============================================

async def get_config_service(db: Database = Depends(get_db)) -> ConfiguracionService:
    repository = ConfiguracionRepository(db)
    notification_service = NotificationService()
    return ConfiguracionService(repository, notification_service)

# --- BONOS ---
@router.post("/bonos/", response_model=Dict[str, Any])
async def create_bono(
    bono: BonoCreate, 
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.bonos", "configuracion.wizard"]))
):
    """Crear un nuevo Bono con sus reglas"""
    new_id = await service.create_bono(bono)
    return {"id": new_id, "message": "Bono creado exitosamente"}

@router.post("/bonos/vista-previa/", response_model=Dict[str, Any])
async def vista_previa_bono(
    bono: BonoCreate,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.bonos", "configuracion.wizard"]))
):
    """Quién recibe el bono y cuánto en el período vigente con lo que se está editando, sin guardarlo; y las personas
    con las que calza más de una regla (etapa B3c del plan de bonos)."""
    from backend.services.bono_service import BonoService
    periodo = await ConfiguracionRepository(db).get_fechas_periodo_vigente()
    if not periodo:
        raise HTTPException(status_code=400, detail="No hay un período vigente para la vista previa.")
    datos = {"nombre": bono.nombre, "activo": True, "tipo": bono.tipo or "pesos", "reglas": [r.model_dump() for r in bono.reglas],
             "efecto_inasistencia": bono.efecto_inasistencia, "efectos": dict(bono.efectos or {})}
    return await BonoService(db).vista_previa(datos, str(periodo["fecha_inicio"])[:10], str(periodo["fecha_fin"])[:10],
                                              areas_permitidas=current_user.get_areas_filter())


@router.get("/bonos/", response_model=List[BonoResponse])
async def get_bonos(
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))
):
    """Listar todos los bonos configurados"""
    return await service.get_all_bonos()

@router.put("/bonos/{bono_id}/", response_model=Dict[str, Any])
async def update_bono(
    bono_id: int,
    bono: BonoCreate,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.bonos"))
):
    """Actualizar un Bono y sus reglas"""
    updated = await service.update_bono(bono_id, bono)
    if not updated:
        raise HTTPException(status_code=404, detail="Bono no encontrado")
    return {"id": bono_id, "message": "Bono actualizado exitosamente"}

@router.delete("/bonos/{bono_id}/", status_code=204)
async def delete_bono(
    bono_id: int,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.bonos"))
):
    """Eliminar un Bono"""
    deleted = await service.delete_bono(bono_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bono no encontrado")
    return

# --- JUSTIFICACIONES ---
@router.get("/justificaciones/tipos/", response_model=List[JustificacionTipoResponse])
async def get_tipos_justificacion(
    all: bool = False,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """Listar tipos de justificación. 'all=true' para incluir inactivos."""
    if all:
        return await service.get_all_tipos_justificacion()
    return await service.get_tipos_justificacion()

@router.get("/justificaciones/calcular_fin/")
async def calcular_fin_justificacion(
    empleado_id: int = Query(...),
    tipo_id: int = Query(...),
    fecha_inicio: str = Query(...),
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Calcula automáticamente la fecha de fin de una justificación
    para que cumpla con los días efectivos (hábiles) mínimos.
    """
    fecha_fin = await service.calcular_fecha_fin_justificacion(empleado_id, fecha_inicio, tipo_id)
    return {"fecha_fin": fecha_fin}

@router.post("/justificaciones/tipos/", response_model=Dict[str, Any])
async def create_tipo_justificacion(
    tipo: JustificacionTipoCreate,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.justificaciones", "configuracion.wizard"]))
):
    """Crear un nuevo tipo de justificación/inasistencia"""
    new_id = await service.create_tipo_justificacion(tipo)
    return {"id": new_id, "message": "Tipo de justificación creado"}

@router.put("/justificaciones/tipos/{tipo_id}/", response_model=Dict[str, Any])
async def update_tipo_justificacion(
    tipo_id: int,
    tipo: JustificacionTipoCreate,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.justificaciones"))
):
    """Actualizar un tipo de justificación"""
    updated = await service.update_tipo_justificacion(tipo_id, tipo)
    if not updated:
        raise HTTPException(status_code=404, detail="Tipo de justificación no encontrado")
    return {"id": tipo_id, "message": "Tipo de justificación actualizado"}

@router.delete("/justificaciones/tipos/{tipo_id}/", status_code=204)
async def delete_tipo_justificacion(
    tipo_id: int,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.justificaciones"))
):
    """Eliminar un tipo de justificación"""
    deleted = await service.delete_tipo_justificacion(tipo_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tipo de justificación no encontrado")
    return

@router.post("/justificaciones/", response_model=Dict[str, Any])
async def create_justificacion(
    j: JustificacionCreate,
    background_tasks: BackgroundTasks,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequireAnyPermission(["marcaciones.justificar", "marcaciones.editar"]))
):
    """Registrar una justificación para un empleado con RLS"""
    # RLS: Verificar pertenencia
    from backend.repositories.empleado import EmpleadoRepository
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(j.empleado_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    if not current_user.alcance_global and emp.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos para registrar justificaciones de este empleado")

    # Blindaje de Cierre
    from backend.repositories.asistencia import AsistenciaRepository
    asistencia_repo = AsistenciaRepository(service.repository.db)
    if await asistencia_repo.check_rango_cerrado(str(j.fecha_inicio), str(j.fecha_fin), j.empleado_id):
         raise HTTPException(status_code=403, detail="El periodo de estas fechas se encuentra cerrado y no admite modificaciones.")

    new_id = await service.create_justificacion(j)
    
    # 🔄 AUTO-RECALCULO con Job Tracking e Inmediación para rangos cortos
    import uuid
    from backend.services.asistencia_service import _JOB_REGISTRY, _update_job
    job_id = f"just-{new_id}-{uuid.uuid4().hex[:8]}"
    _JOB_REGISTRY[job_id] = {"status": "running", "type": "justificacion", "empleado_id": j.empleado_id}

    fecha_inicio_str = j.fecha_inicio.strftime("%Y-%m-%d") if hasattr(j.fecha_inicio, 'strftime') else str(j.fecha_inicio)
    fecha_fin_str = j.fecha_fin.strftime("%Y-%m-%d") if hasattr(j.fecha_fin, 'strftime') else str(j.fecha_fin)

    # ⚡ FAST-PATH: Si el rango es corto (<= 5 días), reprocesar sincrónicamente antes de responder
    from datetime import datetime
    try:
        dt_i = datetime.strptime(fecha_inicio_str, "%Y-%m-%d")
        dt_f = datetime.strptime(fecha_fin_str, "%Y-%m-%d")
        dias_rango = (dt_f - dt_i).days + 1
    except Exception:
        dias_rango = 30

    if dias_rango <= 5:
        try:
            from backend.repositories.asistencia import AsistenciaRepository
            from backend.services.asistencia_service import AsistenciaService
            asistencia_repo = AsistenciaRepository(service.repository.db) 
            asistencia_service = AsistenciaService(asistencia_repo)
            await asistencia_service.reprocesar_periodo_empleado(
                empleado_id=j.empleado_id,
                fecha_inicio=fecha_inicio_str,
                fecha_fin=fecha_fin_str,
                force=True,
                job_id=job_id,
            )
            _update_job(job_id, status="done")
            logger.info(f"⚡ Recalculo sincrónico ultra-rápido completado para empleado {j.empleado_id}")
        except Exception as e:
            logger.error(f"⚠️ Error en recálculo sincrónico: {e}")
            _update_job(job_id, status="done") # igual marcar done para refrescar
    else:
        async def recalculate_attendance_job(j_data, service_instance, jid):
            try:
                from backend.repositories.asistencia import AsistenciaRepository
                from backend.services.asistencia_service import AsistenciaService
                asistencia_repo = AsistenciaRepository(service_instance.repository.db) 
                asistencia_service = AsistenciaService(asistencia_repo)
                await asistencia_service.reprocesar_periodo_empleado(
                    empleado_id=j_data.empleado_id,
                    fecha_inicio=fecha_inicio_str,
                    fecha_fin=fecha_fin_str,
                    force=True,
                    job_id=jid,
                )
                _update_job(jid, status="done")
            except Exception as e:
                logger.error(f"⚠️ Error en recalculo de fondo: {e}")
                _update_job(jid, status="error")

        background_tasks.add_task(recalculate_attendance_job, j, service, job_id)

    return {"id": new_id, "job_id": job_id, "message": "Justificación registrada exitosamente."}

@router.put("/justificaciones/{justificacion_id}/", response_model=Dict[str, Any])
async def update_justificacion(
    justificacion_id: int,
    j: JustificacionCreate,
    background_tasks: BackgroundTasks,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequireAnyPermission(["marcaciones.justificar", "marcaciones.editar"]))
):
    """Editar una justificación existente (corregir fechas, tipo, etc.) con RLS y recalculo en fondo"""
    # RLS: Verificar pertenencia del empleado
    from backend.repositories.empleado import EmpleadoRepository
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(j.empleado_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    if not current_user.alcance_global and emp.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos sobre este empleado")

    # Necesitamos las fechas originales ANTES de editar para el recálculo
    old = await service.repository.get_justificacion_by_id(justificacion_id)
    if not old:
        raise HTTPException(status_code=404, detail="Justificación no encontrada")

    # Blindaje de Cierre (verificar tanto el rango antiguo como el nuevo)
    from backend.repositories.asistencia import AsistenciaRepository
    asistencia_repo = AsistenciaRepository(service.repository.db)
    if await asistencia_repo.check_rango_cerrado(old['fecha_inicio'], old['fecha_fin'], old['empleado_id']) or \
       await asistencia_repo.check_rango_cerrado(str(j.fecha_inicio), str(j.fecha_fin), j.empleado_id):
         raise HTTPException(status_code=403, detail="El periodo de estas fechas se encuentra cerrado y no admite modificaciones.")

    # Actualizar la DB (esto incluye las validaciones de negocio en el service)
    updated = await service.update_justificacion(justificacion_id, j)
    if not updated:
        raise HTTPException(status_code=404, detail="Justificación no encontrada")

    # Recálculo en segundo plano con Job Tracking
    import uuid
    from backend.services.asistencia_service import _JOB_REGISTRY, _update_job
    job_id = f"just-upd-{justificacion_id}-{uuid.uuid4().hex[:8]}"
    _JOB_REGISTRY[job_id] = {"status": "running", "type": "justificacion_update", "empleado_id": j.empleado_id}

    async def recalc_job_put(jid):
        try:
            await service._recalcular_dias_justificacion(
                old['empleado_id'], old['fecha_inicio'], old['fecha_fin'])
            await service._recalcular_dias_justificacion(
                j.empleado_id, str(j.fecha_inicio), str(j.fecha_fin))
            logger.info(f"✅ Recálculo post-update completado para justificación {justificacion_id}")
            _update_job(jid, status="done")
        except Exception as e:
            logger.error(f"⚠️ Error en recálculo post-update: {e}")
            _update_job(jid, status="error")
    background_tasks.add_task(recalc_job_put, job_id)

    return {"success": True, "job_id": job_id, "message": "Justificación actualizada. La asistencia se recalculará en unos segundos."}

@router.delete("/justificaciones/{justificacion_id}/", response_model=Dict[str, Any])
async def delete_justificacion(
    justificacion_id: int,
    background_tasks: BackgroundTasks,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequireAnyPermission(["marcaciones.justificar", "marcaciones.editar"]))
):
    """Eliminar una justificación con RLS y auto-recálculo en segundo plano"""
    # Obtener justificación para verificar RLS
    existing = await service.repository.get_justificacion_by_id(justificacion_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Justificación no encontrada")

    from backend.repositories.empleado import EmpleadoRepository
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(existing['empleado_id'])
    if emp and not current_user.alcance_global and emp.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos sobre este empleado")

    # Blindaje de Cierre
    from backend.repositories.asistencia import AsistenciaRepository
    asistencia_repo = AsistenciaRepository(service.repository.db)
    if await asistencia_repo.check_rango_cerrado(existing['fecha_inicio'], existing['fecha_fin'], existing['empleado_id']):
         raise HTTPException(status_code=403, detail="El periodo de esta justificación se encuentra cerrado y no admite modificaciones.")

    deleted = await service.delete_justificacion(justificacion_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Justificación no encontrada")

    # Recálculo en segundo plano con Job Tracking
    import uuid
    from backend.services.asistencia_service import _JOB_REGISTRY, _update_job
    job_id = f"just-del-{justificacion_id}-{uuid.uuid4().hex[:8]}"
    _JOB_REGISTRY[job_id] = {"status": "running", "type": "justificacion_delete", "empleado_id": existing['empleado_id']}

    async def recalc_job(jid):
        try:
            await service._recalcular_dias_justificacion(
                existing['empleado_id'], existing['fecha_inicio'], existing['fecha_fin'])
            logger.info(f"✅ Recálculo post-delete completado para justificación {justificacion_id}")
            _update_job(jid, status="done")
        except Exception as e:
            logger.error(f"⚠️ Error en recálculo post-delete: {e}")
            _update_job(jid, status="error")
    background_tasks.add_task(recalc_job, job_id)

    return {"success": True, "job_id": job_id, "message": "Justificación eliminada. La asistencia se actualizará en unos segundos."}

@router.get("/justificaciones/empleado/{empleado_id}/", response_model=List[JustificacionResponse])
async def get_justificaciones(
    empleado_id: int,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """Listar justificaciones de un empleado específico con RLS"""
    # RLS: Verificar pertenencia
    from backend.repositories.empleado import EmpleadoRepository
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    if not current_user.alcance_global and emp.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos para ver justificaciones de este empleado")

    return await service.get_justificaciones_empleado(empleado_id)

@router.post("/justificaciones/cerrar/", response_model=Dict[str, Any])
async def cerrar_permiso(
    payload: Dict[str, Any] = Body(...),
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequireAnyPermission(["marcaciones.justificar", "marcaciones.editar"]))
):
    """Cierra un permiso abierto (sin hora de fin) con RLS"""
    emp_id = payload.get('empleado_id')
    fecha = payload.get('fecha')
    h_fin = payload.get('hora_fin')
    
    if not all([emp_id, fecha, h_fin]):
        raise HTTPException(status_code=400, detail="Faltan datos obligatorios (empleado_id, fecha, hora_fin)")

    # RLS: Verificar pertenencia
    from backend.repositories.empleado import EmpleadoRepository
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(emp_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    if not current_user.alcance_global and emp.area not in (current_user.areas or []):
         raise HTTPException(status_code=403, detail="No tiene permisos para modificar este empleado")
        
    success = await service.cerrar_permiso(emp_id, fecha, h_fin)
    if not success:
        raise HTTPException(status_code=404, detail="No se encontró un permiso abierto para este empleado en esta fecha")
        
    return {"success": True, "message": "Regreso registrado y asistencia actualizada"}

# --- PAGADORES ---
@router.get("/pagadores/", response_model=List[PagadorResponse])
async def get_pagadores(
    all: bool = False,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))
):
    """Listar todos los pagadores configurados"""
    return await service.get_all_pagadores(solo_activos=not all)

@router.post("/pagadores/", response_model=Dict[str, Any])
async def create_pagador(
    pagador: PagadorCreate,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.bonos", "configuracion.wizard"]))
):
    """Crear un nuevo pagador"""
    try:
        new_id = await service.create_pagador(pagador.nombre)
        return {"id": new_id, "message": "Pagador creado exitosamente"}
    except ValueError as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=400, detail="Ya existe un pagador con ese nombre.")
        raise

@router.put("/pagadores/{pagador_id}/", response_model=Dict[str, Any])
async def update_pagador(
    pagador_id: int,
    pagador: PagadorCreate,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.bonos", "configuracion.wizard"]))
):
    """Actualizar un pagador"""
    try:
        updated = await service.update_pagador(pagador_id, pagador.nombre, pagador.activo)
        if not updated:
            raise HTTPException(status_code=404, detail="Pagador no encontrado")
        return {"id": pagador_id, "message": "Pagador actualizado exitosamente"}
    except ValueError as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=400, detail="Ya existe un pagador con ese nombre.")
        raise

# --- AJUSTES GLOBALES ---
@router.get("/ajustes/email_notificaciones_rrhh/")
async def get_email_rrhh(
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))
):
    """Obtener ajuste específico de email RRHH para evitar 307"""
    return await service.get_ajuste("email_notificaciones_rrhh")

@router.get("/ajustes/email_notificaciones_cierre_rrhh/")
async def get_email_cierre_rrhh(
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))
):
    """Obtener ajuste específico de email exclusivo para Cierres de Mes"""
    return await service.get_ajuste("email_notificaciones_cierre_rrhh")

@router.get("/ajustes/")
async def get_all_ajustes(
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))
):
    """Obtener todos los ajustes globales"""
    return await service.get_all_ajustes()

@router.get("/ajustes/{clave}/")
async def get_ajuste(
    clave: str,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))
):
    """Obtener un ajuste global por clave"""
    return await service.get_ajuste(clave)

@router.post("/ajustes/{clave}/")
async def set_ajuste(
    clave: str,
    valor: str = Body(...),
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.correo"))
):
    """Guardar o actualizar un ajuste global con validaciones estrictas"""
    # 1. Validación de Reglas de Negocio Críticas para evitar Error 500
    claves_numericas_criticas = [
        "vencimiento_dias_alerta", 
        "dias_alerta_bloqueante", 
        "limite_contratos_temporales", 
        "dia_cierre_rrhh",
        "bioalba_dias_volatilidad",
        "asistencia_max_extras_ordinarias_dia_habil",
        "asistencia_minimo_horas_extra_minutos",
        "porteria_deshacer_segundos"
    ]
    
    if clave in claves_numericas_criticas:
        try:
            val_int = int(valor)
            if clave in ["bioalba_dias_volatilidad", "asistencia_max_extras_ordinarias_dia_habil", "asistencia_minimo_horas_extra_minutos", "porteria_deshacer_segundos"]:
                if val_int < 0:
                    raise ValueError("El valor no puede ser menor a 0")
            else:
                if val_int < 1:
                    raise ValueError("El valor no puede ser menor a 1")
            
            # Restricción especial para el cierre de RRHH para evitar problemas con Febrero
            if clave == "dia_cierre_rrhh" and val_int > 28:
                raise HTTPException(status_code=400, detail="El día de cierre no puede ser mayor a 28 para prevenir errores en Febrero.")
                
        except ValueError as e:
            msg_error = "Debe ser un número entero válido mayor o igual a 0." if clave == "bioalba_dias_volatilidad" else "Debe ser un número entero válido mayor a 0."
            raise HTTPException(status_code=400, detail=f"Valor inválido para {clave}: {msg_error}")

    # Límites de la revisión de la libreta y del GPS (05-11-2026): horas con decimales; tolerancia en minutos (puede ser 0); km/h enteros
    from backend.services.libreta_revision import AJUSTES_REVISION
    if clave in AJUSTES_REVISION:
        try:
            num = float(str(valor).replace(",", "."))
        except ValueError:
            raise HTTPException(status_code=400, detail="Debe ser un número.")
        if clave == "libreta_tolerancia_gps_minutos":
            if num < 0 or num > 120 or num != int(num):
                raise HTTPException(status_code=400, detail="La tolerancia es en minutos enteros, de 0 a 120.")
        elif clave == "gps_velocidad_limite_kmh":
            if num < 1 or num > 200 or num != int(num):
                raise HTTPException(status_code=400, detail="La velocidad es en km/h enteros, de 1 a 200.")
        elif num <= 0 or num > 24:
            raise HTTPException(status_code=400, detail="Las horas deben ser mayores que 0 y no más de 24.")
        valor = str(int(num)) if num == int(num) else str(num)

    success = await service.set_ajuste(clave, valor)
    # Si el motor usa este ajuste, se recalcula solo el tramo abierto de todas las personas (en segundo plano)
    recalculo = None
    if success:
        from backend.core.database import db as _db
        from backend.services.recalculo_service import recalcular_por_ajuste
        try:
            recalculo = await recalcular_por_ajuste(_db, clave)
        except Exception as e:
            logger.warning(f"[Recálculo] no se pudo programar para el ajuste {clave}: {e}")
    return {"success": success, "message": "Ajuste guardado", "recalculo": recalculo}

# --- NOTIFICACIONES POR AREA ---
@router.get("/notificaciones_areas/")
async def get_notificaciones_areas(
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))
):
    """Obtener listado de correos configurados por area"""
    return await service.get_notificaciones_areas()

@router.get("/notificaciones_areas/{area}/")
async def get_notificaciones_area(
    area: str,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))
):
    """Obtener correos configurados para un area en especifico"""
    return await service.get_notificaciones_area(area)

@router.post("/notificaciones_areas/")
async def set_notificaciones_area(
    area: str = Body(...),
    emails: str = Body(...),
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.correo"))
):
    """Guardar o actualizar correos para un area"""
    success = await service.set_notificaciones_area(area, emails)
    return {"success": success, "message": "Correos por área actualizados"}

@router.delete("/notificaciones_areas/{area}/")
async def delete_notificaciones_area(
    area: str,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.correo"))
):
    """Eliminar configuracion de correos para un area"""
    success = await service.delete_notificaciones_area(area)
    return {"success": success, "message": "Configuración por área eliminada"}

# --- FERIADOS ---
@router.get("/feriados/")
async def get_feriados(
    year: Optional[int] = None,
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))
):
    """Listar feriados usando CalendarioService"""
    service = CalendarioService()
    return await service.get_feriados(year)

@router.post("/feriados/sync/{year}/")
async def sync_feriados(
    year: int,
    current_user: SecurityContext = Depends(RequirePermission("configuracion.calendario"))
):
    service = CalendarioService()
    return {"count": await service.sync_chile_holidays(year)}

@router.post("/feriados/")
async def add_feriado(
    feriado: dict,
    current_user: SecurityContext = Depends(RequirePermission("configuracion.calendario"))
):
    service = CalendarioService()
    return await service.add_custom_holiday(feriado['fecha'], feriado['descripcion'])

@router.delete("/feriados/{id}/")
async def delete_feriado(
    id: int,
    current_user: SecurityContext = Depends(RequirePermission("configuracion.calendario"))
):
    service = CalendarioService()
    return await service.delete_holiday(id)


async def _auditar(db: Database, current_user: SecurityContext, accion: str, detalle: str) -> None:
    """Deja el cambio en el registro de auditoría (módulo «Configuracion»)."""
    from backend.repositories.seguridad import SeguridadRepository
    await SeguridadRepository(db).log_auditoria(current_user.user_id, current_user.username, accion, "Configuracion", detalle)


# ──────────────────────────────────────────────────────────────────────────────
# ESTADOS DE ASISTENCIA — Tabla Maestra Configurable
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/estados/")
async def get_estados_asistencia(
    solo_activos: bool = True,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user)
):
    """
    Retorna la tabla maestra de estados de asistencia.
    Usada por el frontend para construir los badges y tooltips dinámicamente.
    """
    rows = await ConfiguracionRepository(db).listar_estados(solo_activos)
    return [dict(r) for r in rows]


# Clases de color que el frontend sabe dibujar (Configuración → Estados + las del seed original)
_COLORES_ESTADO_VALIDOS = {
    'color-verde', 'color-azul', 'color-rojo', 'color-amarillo', 'color-naranja', 'color-purpura',
    'color-rosa', 'color-cian', 'color-lima', 'color-indigo', 'color-teal', 'color-gris', 'color-negro',
    'color-fluor-verde', 'color-fluor-azul', 'color-fluor-amarillo', 'color-fluor-rosa',
    'color-pulso-rojo', 'color-pulso-verde', 'color-pulso-azul', 'color-glitter-oro', 'color-glitter-plata',
    'badge-state-success', 'badge-state-danger', 'badge-state-warning', 'badge-state-info',
    'badge-state-neutral', 'bg-dark text-white', 'badge-inasistencia-compensada-he', 'badge-compensatorio',
    # Rojo intenso (sólido, letras blancas): días que una regla de marcaciones dejó por revisar (06-11-2026)
    'color-rojo-intenso',
}
# La sigla admite hasta 7 caracteres para que quepa una palabra completa como REVISAR (06-11-2026)
SIGLA_MAX = 7
_RE_SIGLA = re.compile(r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ.+\-]{1,%d}$" % SIGLA_MAX)
_RE_ICONO = re.compile(r"^bi-[a-z0-9-]{1,60}$")
_RE_TEXTO_SEGURO = re.compile(r"^[^<>\x00-\x08\x0b\x0c\x0e-\x1f]*$")


def _sigla_efectiva(row: dict) -> str:
    """Misma regla que el frontend: sigla propia o, si no hay, las 3 primeras letras del código."""
    sl = (row.get('short_label') or '').strip()
    if sl:
        return sl.upper()
    cod = row.get('codigo') or ''
    return 'ESP' if cod == 'JORNADA_ESPECIAL' else cod[:3].upper()


@router.put("/estados/{codigo}/")
async def update_estado_asistencia(
    codigo: str,
    payload: Dict[str, Any] = Body(...),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.estados"))
):
    """
    Actualiza los campos visuales de un estado (nombre_display, descripcion,
    color_clase, icono_bi, activo).
    El campo 'codigo' es inmutable — es la clave de BD que usa el motor.

    Validaciones: texto sin < > ni caracteres de control (se pinta en HTML), sigla de 1–5
    caracteres sin repetir entre estados activos, color e icono con formato conocido.
    Un color repetido entre estados activos NO se bloquea: se devuelve en `warnings`.
    """
    config_repo = ConfiguracionRepository(db)
    row = await config_repo.get_estado(codigo)
    if not row:
        raise HTTPException(status_code=404, detail=f"Estado '{codigo}' no encontrado")
    row = dict(row)

    allowed = ['nombre_display', 'short_label', 'descripcion', 'color_clase', 'icono_bi', 'activo', 'orden']
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No hay campos válidos para actualizar")

    # ── Validación de formato ────────────────────────────────────────────────
    for campo, maximo in (('nombre_display', 40), ('descripcion', 240), ('short_label', SIGLA_MAX)):
        if campo in updates and updates[campo] is not None:
            val = str(updates[campo]).strip()
            if len(val) > maximo:
                raise HTTPException(status_code=422, detail=f"'{campo}' admite hasta {maximo} caracteres")
            if not _RE_TEXTO_SEGURO.match(val):
                raise HTTPException(status_code=422, detail=f"'{campo}' no puede contener < > ni caracteres de control")
            updates[campo] = val
    if 'nombre_display' in updates and not updates['nombre_display']:
        raise HTTPException(status_code=422, detail="El nombre visible no puede quedar vacío")
    if 'short_label' in updates:
        sl = updates['short_label'] or ''
        if sl and not _RE_SIGLA.match(sl):
            raise HTTPException(status_code=422, detail=f"La etiqueta admite 1 a {SIGLA_MAX} letras, números, punto, + o guion")
        updates['short_label'] = sl.upper()
    if 'icono_bi' in updates:
        ic = (updates['icono_bi'] or '').strip()
        if ic and not _RE_ICONO.match(ic):
            raise HTTPException(status_code=422, detail="El icono debe tener el formato 'bi-nombre' (Bootstrap Icons)")
        updates['icono_bi'] = ic
    if 'color_clase' in updates:
        col = (updates['color_clase'] or '').strip()
        if col != row.get('color_clase') and col not in _COLORES_ESTADO_VALIDOS:
            raise HTTPException(status_code=422, detail=f"Color no válido: '{col}'")
        updates['color_clase'] = col
    if 'activo' in updates:
        updates['activo'] = 1 if updates['activo'] in (1, True, '1', 'true') else 0

    # ── Sigla única entre estados activos ────────────────────────────────────
    final = {**row, **updates}
    warnings = []
    cambia_sigla = _sigla_efectiva(final) != _sigla_efectiva(row) or int(row.get('activo') or 0) != int(final.get('activo') or 0)
    if int(final.get('activo') or 0) == 1 and cambia_sigla:
        mi_sigla = _sigla_efectiva(final)
        otros = [dict(r) for r in await config_repo.get_otros_estados_activos(codigo)]
        choque = [o['codigo'] for o in otros if _sigla_efectiva(o) == mi_sigla]
        if choque:
            raise HTTPException(
                status_code=409,
                detail=f"La etiqueta '{mi_sigla}' ya la usa el estado {', '.join(choque)}. Elige otra.")

    if int(final.get('activo') or 0) == 1:
        otros_act = [dict(r) for r in await config_repo.get_otros_estados_activos(codigo)]
        mismo_color = [o['codigo'] for o in otros_act if (o.get('color_clase') or '') == (final.get('color_clase') or '')]
        if mismo_color:
            warnings.append(f"El color de '{codigo}' es igual al de: {', '.join(mismo_color)}. "
                            "En la grilla costará distinguirlos.")

    from datetime import datetime
    updates['updated_at'] = datetime.now().isoformat()

    await config_repo.actualizar_estado(codigo, updates)
    logger.info(f"✏️ Estado '{codigo}' actualizado por usuario {current_user.username}: {updates}")
    return {"success": True, "codigo": codigo, "message": "Estado actualizado correctamente",
            "saved": {k: v for k, v in updates.items() if k != 'updated_at'}, "warnings": warnings}


@router.post("/estados/seed/")
async def seed_estados_asistencia(
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("superuser"))
):
    """
    Inicializa la tabla estados_asistencia con los valores por defecto
    del sistema si está vacía. Útil tras un reset de BD.
    """
    config_repo = ConfiguracionRepository(db)
    count_row = await config_repo.contar_estados()
    if count_row and count_row['cnt'] > 0:
        return {"message": "La tabla ya contiene datos. No se realizaron cambios.", "count": count_row['cnt']}

    seed_data = [
        ('OK',                'OK',                 'OK',  'El empleado asistió y cumplió su horario correctamente.',                    'badge-state-success',  'bi-check-circle-fill',          1, 1,  1),
        ('INASISTENCIA',      'INASISTENCIA',       'INA', 'El empleado no se presentó y no tiene marcas ni justificación.',             'badge-state-danger',   'bi-x-circle-fill',              1, 1,  2),
        ('ATRASO',            'ATRASO',             'ATR', 'El empleado llegó tarde respecto a su hora de entrada teórica.',             'badge-state-warning',  'bi-clock-fill',                 1, 1,  3),
        ('SALIDA_ADELANTADA', 'SALIDA ADELANTADA',  'SAL', 'El empleado se retiró antes de su hora de salida teórica.',                 'badge-state-info',     'bi-box-arrow-left',             1, 1,  4),
        ('EN_CURSO',          'EN TURNO',           'ENC', 'El empleado marcó entrada hoy y su turno aún no ha terminado.',              'badge-state-success',  'bi-play-circle-fill',           1, 1,  7),
        ('LIBRE',             'LIBRE',              'LIB', 'Día de descanso según el turno asignado. No es un día laboral.',             'badge-state-neutral',  'bi-cup-hot-fill',               1, 1,  8),
        ('FERIADO',           'FERIADO',            'FER', 'Día festivo legal en Chile. No es jornada laboral.',                         'badge-state-warning',  'bi-calendar-heart-fill',        1, 1,  9),
        ('EXTRA',             'JORNADA EXTRA',      'EXT', 'El empleado trabajó en un día que no le correspondía (libre o feriado).',    'badge-state-info',     'bi-plus-circle-fill',           1, 1, 10),
        ('JORNADA_ESPECIAL',  'JORNADA ESPECIAL',   'ESP', 'Excepción manual: vacaciones, licencia médica, permiso de día, etc.',        'badge-state-info',     'bi-star-fill',                  1, 1, 11),
        ('ANOMALIA',          'ANOMALÍA',           'ANO', 'Inconsistencia en marcas (ej: hay entrada pero nunca se registró salida).',  'bg-dark text-white',   'bi-exclamation-triangle-fill',  1, 1, 12),
        ('PERMISO',           'PERMISO',            'PER', 'El empleado cuenta con un permiso de horas aprobado para ese día.',          'badge-state-info',     'bi-calendar-check-fill',        1, 1, 13),
        ('INASISTENCIA_COMPENSADA', 'INASISTENCIA COMPENSADA', 'C.HE', 'Inasistencia compensada utilizando la bolsa de horas extras aprobadas.', 'badge-inasistencia-compensada-he', 'bi-clock-history', 1, 1, 14),
        ('JORNADA_COMPENSATORIA',   'JORNADA COMPENSATORIA',   'COMP', 'Día libre compensatorio por jornada trabajada en día de descanso.', 'badge-compensatorio', 'bi-arrow-left-right', 1, 1, 15),
        ('LLAMADO_EMERGENCIA',      'LLAMADO DE EMERGENCIA',   'EME',  'Llamado de emergencia en un día que la persona no tenía que trabajar (día libre, feriado o sin turno). Se valida aparte de la jornada especial: EXTRA, horas extra o rechazo.', 'color-violeta', 'bi-telephone-inbound-fill', 1, 1, 17),
    ]
    await config_repo.sembrar_estados(seed_data)
    return {"success": True, "message": f"Tabla inicializada con {len(seed_data)} estados.", "count": len(seed_data)}

# ============================================
# ÁREAS Y ALIAS (CATÁLOGO Y AUDITORÍA)
# ============================================

from pydantic import BaseModel, Field

class AreaCreateRequest(BaseModel):
    nombre: str = Field(..., min_length=1, description="Nombre del área")

class CargoCreateRequest(BaseModel):
    nombre: str = Field(..., min_length=1, description="Nombre del cargo")

@router.get("/areas/", response_model=List[Dict[str, Any]])
async def get_catalogo_areas(
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.ver", "empleados.ver", "empleados.crear", "empleados.editar"]))
):
    """Obtener el catálogo de áreas principales y sus alias (errores redirigidos)"""
    from backend.repositories.area import AreaRepository
    repo = AreaRepository(db)
    return await repo.get_areas_with_aliases()

@router.post("/areas/", response_model=Dict[str, Any])
async def create_area_manual(
    req: AreaCreateRequest,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))
):
    """Crear un área manualmente en el catálogo principal"""
    from backend.repositories.area import AreaRepository
    repo = AreaRepository(db)
    nombre_normalizado = req.nombre.strip()
    if not nombre_normalizado:
        raise HTTPException(status_code=400, detail="El nombre del área no puede estar vacío.")
    
    # Verificar si ya existe (exacto)
    existente = await repo.get_area_by_name(nombre_normalizado)
    if existente:
        raise HTTPException(status_code=400, detail=f"El área '{nombre_normalizado}' ya existe en el catálogo.")
    
    # Verificar case-insensitive
    case_exist = await repo.get_area_por_nombre_sin_mayusculas(nombre_normalizado)
    if case_exist:
        raise HTTPException(status_code=400, detail=f"Ya existe una área con este nombre pero diferente capitalización ('{case_exist['nombre']}').")

    # Verificar en alias para evitar colisiones
    alias_colision = await repo.get_alias_con_nombre(nombre_normalizado)
    if alias_colision:
        raise HTTPException(status_code=400, detail=f"El nombre '{nombre_normalizado}' ya está registrado como alias de otra área.")

    area_id = await repo.create_area(nombre_normalizado)
    
    # Registrar en auditoría
    await _auditar(db, current_user, "CREATE_AREA_MANUAL", f"Creada área manualmente: '{nombre_normalizado}' (ID: {area_id}).")
    return {"id": area_id, "nombre": nombre_normalizado, "message": "Área creada exitosamente"}

@router.delete("/areas/alias/{alias_id}", status_code=204)
async def delete_area_alias(
    alias_id: int,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))
):
    """Desvincular (eliminar) un alias. El Guardián volverá a atraparlo si reincide."""
    from backend.repositories.area import AreaRepository
    repo = AreaRepository(db)
    success = await repo.delete_alias(alias_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alias no encontrado")
    return

@router.delete("/areas/{area_id}/", status_code=204)
async def delete_area(
    area_id: int,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))
):
    """Eliminar un área principal aplicando restricciones de empleados activos y marcaciones."""
    # 1. Verificar existencia del área
    from backend.repositories.area import AreaRepository
    repo = AreaRepository(db)
    area = await repo.get_area_by_id(area_id)
    if not area:
        raise HTTPException(status_code=404, detail="El área no existe.")

    # 2. Verificar si hay empleados activos asignados a esta área actualmente
    emp_count = await repo.contar_empleados(area_id)
    if emp_count and emp_count["count"] > 0:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar el área '{area['nombre']}' porque tiene {emp_count['count']} empleado(s) activo(s) asignado(s). Por favor reasígnelos antes de intentar eliminar."
        )

    # 3. Verificar si hay marcaciones crudas (logs_raw) asociadas a empleados (activos o históricos) durante su permanencia en esta área
    logs_count = await repo.contar_marcas_en_su_historial(area_id)
    if logs_count and logs_count["count"] > 0:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar el área '{area['nombre']}' porque existen marcaciones crudas ({logs_count['count']}) asociadas a esta área en el historial."
        )

    # 4. Verificar si hay jornadas de asistencia procesadas (asistencias) asociadas a esta área en el historial
    asist_count = await repo.contar_asistencias_en_su_historial(area_id)
    if asist_count and asist_count["count"] > 0:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar el área '{area['nombre']}' porque existen jornadas de asistencia procesadas ({asist_count['count']}) asociadas a esta área en el historial."
        )

    # 5. Verificar si hay registros de horas extras calculadas (horas_extras) asociados a esta área en el historial
    he_count = await repo.contar_horas_extras_en_su_historial(area_id)
    if he_count and he_count["count"] > 0:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar el área '{area['nombre']}' porque existen registros de horas extras ({he_count['count']}) asociados a esta área en el historial."
        )

    # 6. Proceder con la eliminación
    # Primero su historial_areas (no hay marcas asociadas a esta área, es seguro limpiarlo) y después el área
    await repo.eliminar_area(area_id)

    # Registrar en auditoría
    await _auditar(db, current_user, "DELETE_AREA_MANUAL", f"Eliminada área manualmente: '{area['nombre']}' (ID: {area_id}).")
    return

@router.patch("/areas/{area_id}/aplica-flota")
async def patch_area_aplica_flota(
    area_id: int,
    data: Dict[str, Any],
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))
):
    """Activar/desactivar flag aplica_flota para un área"""
    aplica_flota = 1 if data.get("aplica_flota") else 0
    from backend.repositories.area import AreaRepository
    repo = AreaRepository(db)
    area = await repo.get_area_by_id(area_id)
    if not area:
        raise HTTPException(status_code=404, detail="El área no existe.")

    await repo.set_aplica_flota(area_id, aplica_flota)
    
    # Registrar en auditoría
    await _auditar(db, current_user, "UPDATE_AREA_FLOTA", f"Modificado flag aplica_flota para el área '{area['nombre']}' (ID: {area_id}) a {aplica_flota}.")
    return {"ok": True, "message": "Área actualizada exitosamente"}

# ============================================
# CARGOS Y ALIAS (CATÁLOGO Y AUDITORÍA)
# ============================================

@router.get("/cargos/", response_model=List[Dict[str, Any]])
async def get_catalogo_cargos(
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.ver", "empleados.ver", "empleados.crear", "empleados.editar"]))
):
    """Obtener el catálogo de cargos principales y sus alias"""
    from backend.repositories.cargo import CargoRepository
    repo = CargoRepository(db)
    return await repo.get_cargos_with_aliases()

@router.post("/cargos/", response_model=Dict[str, Any])
async def create_cargo_manual(
    req: CargoCreateRequest,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))
):
    """Crear un cargo manualmente en el catálogo principal"""
    from backend.repositories.cargo import CargoRepository
    repo = CargoRepository(db)
    nombre_normalizado = req.nombre.strip()
    if not nombre_normalizado:
        raise HTTPException(status_code=400, detail="El nombre del cargo no puede estar vacío.")
    
    # Verificar si ya existe (exacto)
    existente = await repo.get_cargo_by_name(nombre_normalizado)
    if existente:
        raise HTTPException(status_code=400, detail=f"El cargo '{nombre_normalizado}' ya existe en el catálogo.")
    
    # Verificar case-insensitive
    case_exist = await repo.get_cargo_por_nombre_sin_mayusculas(nombre_normalizado)
    if case_exist:
        raise HTTPException(status_code=400, detail=f"Ya existe un cargo con este nombre pero diferente capitalización ('{case_exist['nombre']}').")

    # Verificar en alias para evitar colisiones
    alias_colision = await repo.get_alias_con_nombre(nombre_normalizado)
    if alias_colision:
        raise HTTPException(status_code=400, detail=f"El nombre '{nombre_normalizado}' ya está registrado como alias de otro cargo.")

    cargo_id = await repo.create_cargo(nombre_normalizado)
    
    # Registrar en auditoría
    await _auditar(db, current_user, "CREATE_CARGO_MANUAL", f"Creado cargo manualmente: '{nombre_normalizado}' (ID: {cargo_id}).")
    return {"id": cargo_id, "nombre": nombre_normalizado, "message": "Cargo creado exitosamente"}

class CargoRenombrarRequest(BaseModel):
    nombre: str


class CargoUnirRequest(BaseModel):
    destino_id: int


async def _validar_nombre_cargo(repo, nombre: str, cargo_id: int) -> str:
    nombre = (nombre or '').strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre del cargo no puede estar vacío.")
    otro = await repo.get_cargo_por_nombre_sin_mayusculas(nombre)
    if otro and otro['nombre'] != (await repo.get_cargo_by_id(cargo_id))['nombre']:
        raise HTTPException(status_code=400, detail=f"Ya existe el cargo «{otro['nombre']}».")
    alias = await repo.find_cargo_id_by_name_or_alias(nombre)
    if alias and alias != cargo_id:
        raise HTTPException(status_code=400, detail=f"«{nombre}» ya es el nombre de otro cargo en BioAlba. Únalos en vez de renombrar.")
    return nombre


@router.get("/cargos/{cargo_id}/uso/", response_model=Dict[str, Any])
async def uso_del_cargo(cargo_id: int, db: Database = Depends(get_db),
                        current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))):
    """Cuántas personas tienen el cargo y qué reglas de bono lo nombran (se muestra antes de renombrar o unir)."""
    from backend.repositories.cargo import CargoRepository
    repo = CargoRepository(db)
    if not await repo.get_cargo_by_id(cargo_id):
        raise HTTPException(status_code=404, detail="Cargo no encontrado")
    return await repo.uso_del_cargo(cargo_id)


@router.put("/cargos/{cargo_id}/renombrar/", response_model=Dict[str, Any])
async def renombrar_cargo(cargo_id: int, req: CargoRenombrarRequest, db: Database = Depends(get_db),
                          current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))):
    """Cambia el nombre de un cargo (etapa B3b del plan de bonos). El anterior queda como alias para BioAlba."""
    from backend.repositories.cargo import CargoRepository
    repo = CargoRepository(db)
    if not await repo.get_cargo_by_id(cargo_id):
        raise HTTPException(status_code=404, detail="Cargo no encontrado")
    nombre = await _validar_nombre_cargo(repo, req.nombre, cargo_id)
    anterior = await repo.renombrar(cargo_id, nombre)
    ConfiguracionRepository._bonos_cache = None
    await _auditar(db, current_user, "RENOMBRAR_CARGO", f"Cargo '{anterior}' (ID: {cargo_id}) renombrado a '{nombre}'; '{anterior}' queda como alias.")
    return {"id": cargo_id, "nombre": nombre, "anterior": anterior}


@router.post("/cargos/{cargo_id}/unir/", response_model=Dict[str, Any])
async def unir_cargo(cargo_id: int, req: CargoUnirRequest, db: Database = Depends(get_db),
                     current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))):
    """Une el cargo con otro (etapa B3b): sus personas, alias y reglas de bono pasan al destino y el cargo se borra."""
    from backend.repositories.cargo import CargoRepository
    repo = CargoRepository(db)
    origen, destino = await repo.get_cargo_by_id(cargo_id), await repo.get_cargo_by_id(req.destino_id)
    if not origen or not destino:
        raise HTTPException(status_code=404, detail="Cargo no encontrado")
    if cargo_id == req.destino_id:
        raise HTTPException(status_code=400, detail="Elija otro cargo para unir.")
    uso = await repo.unir(cargo_id, req.destino_id)
    ConfiguracionRepository._bonos_cache = None
    await _auditar(db, current_user, "UNIR_CARGOS",
                   f"Cargo '{origen['nombre']}' (ID: {cargo_id}) unido en '{destino['nombre']}' (ID: {req.destino_id}): "
                   f"{uso['personas']} personas y {len(uso['reglas'])} reglas de bono; '{origen['nombre']}' queda como alias.")
    return {"origen": origen['nombre'], "destino": destino['nombre'], **uso}


@router.delete("/cargos/alias/{alias_id}", status_code=204)
async def delete_cargo_alias(
    alias_id: int,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))
):
    """Desvincular (eliminar) un alias de cargo."""
    from backend.repositories.cargo import CargoRepository
    repo = CargoRepository(db)
    success = await repo.delete_alias(alias_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alias no encontrado")
    return

@router.put("/cargos/{cargo_id}/excluir/", response_model=Dict[str, Any])
async def toggle_cargo_exclusion(
    cargo_id: int,
    excluir: bool = Query(..., description="True para excluir, False para requerir asistencia"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))
):
    """Habilitar/deshabilitar la exclusión de asistencia por cargo y propagarla a los empleados con ese cargo"""
    # Verificar si el cargo existe
    from backend.repositories.cargo import CargoRepository
    from backend.repositories.asistencia import AsistenciaRepository
    repo = CargoRepository(db)
    cargo = await repo.get_cargo_by_id(cargo_id)
    if not cargo:
        raise HTTPException(status_code=404, detail="Cargo no encontrado")

    val = 1 if excluir else 0

    # Actualizar el cargo y propagar únicamente a empleados manuales (los sincronizados nunca se excluyen por Art. 22)
    await repo.set_excluido_asistencia(cargo_id, val)

    # Limpieza para los empleados afectados (solo manuales)
    periodo_activo = await ConfiguracionRepository(db).get_fechas_periodo_vigente()
    if periodo_activo:
        f_ini = periodo_activo["fecha_inicio"]
        f_fin = periodo_activo["fecha_fin"]
        emp_rows = await repo.get_empleados_manuales_activos(cargo_id)
        for r in emp_rows:
            emp_id = r["id"]
            if excluir:
                # Si se excluye, borrar registros residuales del periodo activo
                await AsistenciaRepository(db).borrar_asistencias_y_horas_extras(emp_id, f_ini, f_fin)
                
    # Registrar auditoría
    await _auditar(db, current_user, "TOGGLE_CARGO_EXCLUSION", f"Modificado excluido_asistencia a {val} para cargo '{cargo['nombre']}' (ID: {cargo_id}) y sus empleados.")
    
    return {"id": cargo_id, "excluido_asistencia": excluir, "message": "Exclusión de cargo y empleados actualizada exitosamente"}

# ============================================
# GÉNEROS (CATÁLOGO)
# ============================================

@router.get("/generos/", response_model=List[Dict[str, Any]])
async def get_catalogo_generos(
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.ver", "empleados.ver", "empleados.crear", "empleados.editar"]))
):
    """Obtener el catálogo de géneros"""
    from backend.repositories.empleado import EmpleadoRepository
    rows = await EmpleadoRepository(db).get_generos()
    return [dict(r) for r in rows]


# ============================================
# RAZONES DE NOTA DE CRÉDITO (Fill Rate, 23-11-2026)
# ============================================

class RazonNotaCredito(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=120)
    culpa_chofer: bool = False
    # Además de decidir el Fill Rate, descuenta el valor de los productos de la nota (dueño, 23-11-2026)
    descuenta_productos: bool = False
    activa: bool = True


@router.get("/razones-nota-credito/")
async def get_razones_nota_credito(
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.ver", "marcaciones.ver"]))
):
    """Las razones de nota de crédito: cada una dice si es culpa del chofer (entonces el día no cumple el Fill Rate)."""
    return await ConfiguracionRepository(db).get_razones_nota_credito()


@router.post("/razones-nota-credito/")
async def crear_razon_nota_credito(
    req: RazonNotaCredito,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))
):
    repo = ConfiguracionRepository(db)
    nombre = req.nombre.strip()
    if any(str(r["nombre"]).strip().upper() == nombre.upper() for r in await repo.get_razones_nota_credito()):
        raise HTTPException(status_code=400, detail="Ya existe una razón con ese nombre.")
    return {"id": await repo.crear_razon_nota_credito(nombre, req.culpa_chofer, req.descuenta_productos)}


@router.put("/razones-nota-credito/{razon_id}/")
async def actualizar_razon_nota_credito(
    razon_id: int,
    req: RazonNotaCredito,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))
):
    """Edita una razón. No se borran: las que ya se usaron quedan en el historial; se desactivan."""
    repo = ConfiguracionRepository(db)
    nombre = req.nombre.strip()
    if any(r["id"] != razon_id and str(r["nombre"]).strip().upper() == nombre.upper() for r in await repo.get_razones_nota_credito()):
        raise HTTPException(status_code=400, detail="Ya existe una razón con ese nombre.")
    if not await repo.actualizar_razon_nota_credito(razon_id, nombre, req.culpa_chofer, req.activa, req.descuenta_productos):
        raise HTTPException(status_code=404, detail="La razón no existe.")
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# PERIODOS RRHH (Tramos de Cierre)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/periodos/", response_model=List[PeriodoRRHHResponse])
async def get_periodos_rrhh(
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.ver", "marcaciones.cierre_periodo", "marcaciones.ver"]))
):
    """Listar todos los tramos de cierre configurados"""
    return await service.get_all_periodos_rrhh()

@router.get("/periodos/activo/", response_model=Optional[PeriodoRRHHResponse])
async def get_periodo_rrhh_activo(
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """Obtener el tramo de cierre activo actual"""
    return await service.get_periodo_rrhh_activo()

@router.get("/periodos/activo/{area}/", response_model=Optional[PeriodoRRHHResponse])
async def get_periodo_rrhh_activo_area(
    area: str,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """Obtener el tramo de cierre activo actual para un área específica"""
    return await service.get_periodo_rrhh_activo_area(area)

@router.post("/periodos/", response_model=Dict[str, Any])
async def create_periodo_rrhh(
    periodo: PeriodoRRHHCreate,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))
):
    """Crear un nuevo tramo de cierre"""
    new_id = await service.create_periodo_rrhh(periodo)
    return {"id": new_id, "message": "Tramo de cierre creado exitosamente"}

@router.put("/periodos/{periodo_id}/", response_model=Dict[str, Any])
async def update_periodo_rrhh(
    periodo_id: int,
    periodo: PeriodoRRHHCreate,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))
):
    """Actualizar un tramo de cierre"""
    updated = await service.update_periodo_rrhh(periodo_id, periodo)
    if not updated:
        raise HTTPException(status_code=404, detail="Tramo de cierre no encontrado")
    return {"id": periodo_id, "message": "Tramo de cierre actualizado exitosamente"}

@router.delete("/periodos/{periodo_id}/", status_code=204)
async def delete_periodo_rrhh(
    periodo_id: int,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))
):
    """Eliminar un tramo de cierre"""
    deleted = await service.delete_periodo_rrhh(periodo_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tramo de cierre no encontrado")
    return

@router.post("/periodos/{periodo_id}/activar/", response_model=Dict[str, Any])
async def set_periodo_rrhh_activo(
    periodo_id: int,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.editar"))
):
    """Marcar un tramo de cierre como activo (vigente)"""
    success = await service.set_periodo_rrhh_activo(periodo_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tramo de cierre no encontrado")
    return {"success": True, "message": "Tramo de cierre marcado como activo"}

