from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks, Query
from typing import List, Dict, Any
from backend.services.configuracion_service import ConfiguracionService
from backend.repositories.configuracion import ConfiguracionRepository
from backend.core.database import get_db, Database
from backend.schemas.bono import BonoCreate, BonoResponse
from backend.schemas.justificacion import JustificacionTipoCreate, JustificacionTipoResponse, JustificacionCreate, JustificacionResponse
from backend.schemas.pagador import PagadorResponse, PagadorCreate
from backend.services.calendario_service import CalendarioService
from typing import Optional
from loguru import logger
from backend.services.notification_service import NotificationService
from backend.core.events import scheduler
from backend.core.security import SecurityContext, RequirePermission, get_current_user

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
    current_user: SecurityContext = Depends(RequirePermission("configuracion.bonos"))
):
    """Crear un nuevo Bono con sus reglas"""
    new_id = await service.create_bono(bono)
    return {"id": new_id, "message": "Bono creado exitosamente"}

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
    current_user: SecurityContext = Depends(RequirePermission("configuracion.justificaciones"))
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
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
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
    
    # 🔄 AUTO-RECALCULO con Job Tracking para polling desde el frontend
    import uuid
    from backend.services.asistencia_service import _JOB_REGISTRY, _update_job
    job_id = f"just-{new_id}-{uuid.uuid4().hex[:8]}"
    _JOB_REGISTRY[job_id] = {"status": "running", "type": "justificacion", "empleado_id": j.empleado_id}

    async def recalculate_attendance_job(j_data, service_instance, jid):
        try:
            from backend.repositories.asistencia import AsistenciaRepository
            from backend.services.asistencia_service import AsistenciaService

            asistencia_repo = AsistenciaRepository(service_instance.repository.db) 
            asistencia_service = AsistenciaService(asistencia_repo)
            
            # ⚡ Usar reprocesar_periodo_empleado: incluye delta/diffing + batch commit
            fecha_inicio_str = j_data.fecha_inicio.strftime("%Y-%m-%d") if hasattr(j_data.fecha_inicio, 'strftime') else str(j_data.fecha_inicio)
            fecha_fin_str = j_data.fecha_fin.strftime("%Y-%m-%d") if hasattr(j_data.fecha_fin, 'strftime') else str(j_data.fecha_fin)
            
            await asistencia_service.reprocesar_periodo_empleado(
                empleado_id=j_data.empleado_id,
                fecha_inicio=fecha_inicio_str,
                fecha_fin=fecha_fin_str,
                force=True,
                job_id=jid,
            )
                
            logger.info(f"✅ Recalculo de fondo completado para empleado {j_data.empleado_id}")
            # Forzar sync para que las lecturas inmediatas vean los datos actualizados
            try:
                db_inst = service_instance.repository.db
                if db_inst.sync_supported:
                    import asyncio as _aio
                    await _aio.to_thread(db_inst.conn.sync)
                    logger.debug("🔄 Sync post-recálculo completado")
            except Exception as sync_err:
                logger.debug(f"⚠️ Sync post-recálculo no crítico: {sync_err}")
            _update_job(jid, status="done")
        except Exception as e:
            logger.error(f"⚠️ Error en recalculo de fondo: {e}")
            _update_job(jid, status="error")

    background_tasks.add_task(recalculate_attendance_job, j, service, job_id)

    return {"id": new_id, "job_id": job_id, "message": "Justificación registrada exitosamente. La asistencia se actualizará en unos segundos."}

@router.put("/justificaciones/{justificacion_id}/", response_model=Dict[str, Any])
async def update_justificacion(
    justificacion_id: int,
    j: JustificacionCreate,
    background_tasks: BackgroundTasks,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
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
            # Forzar sync para que las lecturas inmediatas vean los datos actualizados
            try:
                db_inst = service.repository.db
                if db_inst.sync_supported:
                    import asyncio as _aio
                    await _aio.to_thread(db_inst.conn.sync)
            except Exception:
                pass
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
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
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
            # Forzar sync para que las lecturas inmediatas vean los datos actualizados
            try:
                db_inst = service.repository.db
                if db_inst.sync_supported:
                    import asyncio as _aio
                    await _aio.to_thread(db_inst.conn.sync)
            except Exception:
                pass
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
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
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
    current_user: SecurityContext = Depends(RequirePermission("configuracion.bonos"))
):
    """Crear un nuevo pagador"""
    new_id = await service.create_pagador(pagador.nombre)
    return {"id": new_id, "message": "Pagador creado exitosamente"}

@router.put("/pagadores/{pagador_id}/", response_model=Dict[str, Any])
async def update_pagador(
    pagador_id: int,
    pagador: PagadorCreate,
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.bonos"))
):
    """Actualizar un pagador"""
    updated = await service.update_pagador(pagador_id, pagador.nombre, pagador.activo)
    if not updated:
        raise HTTPException(status_code=404, detail="Pagador no encontrado")
    return {"id": pagador_id, "message": "Pagador actualizado exitosamente"}

# --- AJUSTES GLOBALES ---
@router.get("/ajustes/email_notificaciones_rrhh/")
async def get_email_rrhh(
    service: ConfiguracionService = Depends(get_config_service),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))
):
    """Obtener ajuste específico de email RRHH para evitar 307"""
    return await service.get_ajuste("email_notificaciones_rrhh")

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
        "dia_cierre_rrhh"
    ]
    
    if clave in claves_numericas_criticas:
        try:
            val_int = int(valor)
            if val_int < 1:
                raise ValueError("El valor no puede ser menor a 1")
            
            # Restricción especial para el cierre de RRHH para evitar problemas con Febrero
            if clave == "dia_cierre_rrhh" and val_int > 28:
                raise HTTPException(status_code=400, detail="El día de cierre no puede ser mayor a 28 para prevenir errores en Febrero.")
                
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Valor inválido para {clave}: Debe ser un número entero válido mayor a 0.")

    success = await service.set_ajuste(clave, valor)
    return {"success": success, "message": "Ajuste guardado"}

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

# --- DIAGNÓSTICO (MENÚ SECRETO 7890) ---
@router.get("/diagnostico/db-mode/")
async def get_db_mode(
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("superuser"))
):
    """Obtener modo de DB (Hybrid vs Cloud-Only)"""
    return {
        "mode": "cloud" if getattr(db, "_force_turso_only", False) else "hybrid",
        "turso_enabled": db.use_turso
    }

@router.post("/diagnostico/db-mode/")
async def set_db_mode(
    payload: Dict[str, Any] = Body(...),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("superuser"))
):
    """Cambiar modo de DB"""
    mode = payload.get("mode") # "cloud" o "hybrid"
    
    # 1. Persistir localmente de forma asíncrona para que el boot lo vea
    # Esto es CRUCIAL porque si estamos en modo 'cloud', db.execute NO escribe en el archivo local
    try:
        if hasattr(db, '_save_persistence_locally'):
            await db._save_persistence_locally("db_operation_mode", mode)
    except Exception as e:
        logger.error(f"❌ Error persistiendo localmente: {e}")

    # 2. Persistir en la nube (para que otros terminales sepan el estado si es necesario)
    try:
        await db.execute(
            "INSERT OR REPLACE INTO ajustes (clave, valor, descripcion) VALUES (?, ?, ?)",
            ("db_operation_mode", mode, "Modo de operación de base de datos (cloud/hybrid)")
        )
    except Exception as e:
        logger.error(f"❌ Error persistiendo modo de DB en la nube: {e}")

    # 3. Aplicar cambio en caliente
    if mode == "cloud":
        db._force_turso_only = True
        logger.warning("🧪 CONFIGURACIÓN: Modo Nube Pura ACTIVADO")
    else:
        db._force_turso_only = False
        logger.info("🧪 CONFIGURACIÓN: Modo Híbrido RESTAURADO")
    
    return {"status": "ok", "mode": mode}

@router.post("/diagnostico/sync-speed/")
async def set_sync_speed(
    payload: Dict[str, Any] = Body(...),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("superuser"))
):
    """Cambiar velocidad de sincronización (polling)"""
    seconds = payload.get("seconds", 30)
    
    # Validar rango seguro
    if seconds < 1: seconds = 1
    
    try:
        # Modificar el job en el scheduler global
        if scheduler.get_job('turso_sync'):
            scheduler.reschedule_job('turso_sync', trigger='interval', seconds=seconds)
            logger.warning(f"🧪 DIAGNÓSTICO: Sync Interval cambiado a {seconds}s")
            return {"status": "ok", "interval": seconds}
        else:
            return {"status": "error", "message": "Job turso_sync no encontrado"}
    except Exception as e:
        logger.error(f"❌ Error cambiando velocidad de sync: {e}")
        return {"status": "error", "message": str(e)}


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
    query = "SELECT * FROM estados_asistencia"
    if solo_activos:
        query += " WHERE activo = 1"
    query += " ORDER BY orden ASC"
    rows = await db.fetch_all(query)
    return [dict(r) for r in rows]


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
    """
    row = await db.fetch_one("SELECT * FROM estados_asistencia WHERE codigo = ?", (codigo,))
    if not row:
        raise HTTPException(status_code=404, detail=f"Estado '{codigo}' no encontrado")

    allowed = ['nombre_display', 'short_label', 'descripcion', 'color_clase', 'icono_bi', 'activo', 'orden']
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No hay campos válidos para actualizar")

    from datetime import datetime
    updates['updated_at'] = datetime.now().isoformat()

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [codigo]
    await db.execute(f"UPDATE estados_asistencia SET {set_clause} WHERE codigo = ?", values)
    logger.info(f"✏️ Estado '{codigo}' actualizado por usuario {current_user.username}: {updates}")
    return {"success": True, "codigo": codigo, "message": "Estado actualizado correctamente"}


@router.post("/estados/seed/")
async def seed_estados_asistencia(
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("superuser"))
):
    """
    Inicializa la tabla estados_asistencia con los valores por defecto
    del sistema si está vacía. Útil tras un reset de BD.
    """
    count_row = await db.fetch_one("SELECT COUNT(*) as cnt FROM estados_asistencia")
    if count_row and count_row['cnt'] > 0:
        return {"message": "La tabla ya contiene datos. No se realizaron cambios.", "count": count_row['cnt']}

    seed_data = [
        ('OK',                'OK',                 'OK',  'El empleado asistió y cumplió su horario correctamente.',                    'badge-state-success',  'bi-check-circle-fill',          1, 1,  1),
        ('INASISTENCIA',      'INASISTENCIA',       'INA', 'El empleado no se presentó y no tiene marcas ni justificación.',             'badge-state-danger',   'bi-x-circle-fill',              1, 1,  2),
        ('ATRASO',            'ATRASO',             'ATR', 'El empleado llegó tarde respecto a su hora de entrada teórica.',             'badge-state-warning',  'bi-clock-fill',                 1, 1,  3),
        ('SALIDA_ADELANTADA', 'SALIDA ADELANTADA',  'SAL', 'El empleado se retiró antes de su hora de salida teórica.',                 'badge-state-info',     'bi-box-arrow-left',             1, 1,  4),
        ('ATR_SAD',           'ATRASO + SAL. ADEL.','A+S', 'El empleado llegó tarde Y se fue antes. Combinación de ambos eventos.',      'badge-state-warning',  'bi-clock-fill',                 1, 1,  5),
        ('PER_ATR',           'PERMISO + ATRASO',   'P+A', 'El empleado tiene permiso registrado y además llegó tarde.',                 'badge-state-warning',  'bi-clock-fill',                 1, 1,  6),
        ('EN_CURSO',          'EN TURNO',           'ENC', 'El empleado marcó entrada hoy y su turno aún no ha terminado.',              'badge-state-success',  'bi-play-circle-fill',           1, 1,  7),
        ('LIBRE',             'LIBRE',              'LIB', 'Día de descanso según el turno asignado. No es un día laboral.',             'badge-state-neutral',  'bi-cup-hot-fill',               1, 1,  8),
        ('FERIADO',           'FERIADO',            'FER', 'Día festivo legal en Chile. No es jornada laboral.',                         'badge-state-warning',  'bi-calendar-heart-fill',        1, 1,  9),
        ('EXTRA',             'JORNADA EXTRA',      'EXT', 'El empleado trabajó en un día que no le correspondía (libre o feriado).',    'badge-state-info',     'bi-plus-circle-fill',           1, 1, 10),
        ('JORNADA_ESPECIAL',  'JORNADA ESPECIAL',   'ESP', 'Excepción manual: vacaciones, licencia médica, permiso de día, etc.',        'badge-state-info',     'bi-star-fill',                  1, 1, 11),
        ('ANOMALIA',          'ANOMALÍA',           'ANO', 'Inconsistencia en marcas (ej: hay entrada pero nunca se registró salida).',  'bg-dark text-white',   'bi-exclamation-triangle-fill',  1, 1, 12),
        ('PERMISO',           'PERMISO',            'PER', 'El empleado cuenta con un permiso de horas aprobado para ese día.',          'badge-state-info',     'bi-calendar-check-fill',        1, 1, 13),
    ]
    for row in seed_data:
        await db.execute(
            """INSERT OR IGNORE INTO estados_asistencia
               (codigo, nombre_display, short_label, descripcion, color_clase, icono_bi, es_sistema, activo, orden)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            row
        )
    return {"success": True, "message": f"Tabla inicializada con {len(seed_data)} estados.", "count": len(seed_data)}

# ============================================
# ÁREAS Y ALIAS (CATÁLOGO Y AUDITORÍA)
# ============================================

@router.get("/areas/", response_model=List[Dict[str, Any]])
async def get_catalogo_areas(
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.ver"))
):
    """Obtener el catálogo de áreas principales y sus alias (errores redirigidos)"""
    from backend.repositories.area import AreaRepository
    repo = AreaRepository(db)
    return await repo.get_areas_with_aliases()

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
