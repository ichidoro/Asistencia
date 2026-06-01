"""
Router - Sincronización
Endpoints para sincronizar datos desde BioAlba
"""

import json
from datetime import datetime as _dt
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Query, Depends
from typing import Dict, Any, Optional, List
from loguru import logger
from backend.schemas.sync import SyncEmpleadosRequest, SyncAsistenciaRequest, SyncPreviewRequest, WizardCommitAreasRequest, WizardCommitCargosRequest
from fastapi.responses import StreamingResponse
import asyncio
from pydantic import BaseModel

from backend.core.security import SecurityContext, RequirePermission, RequireAnyPermission
from backend.core.database import db
from backend.services.sync_service import SyncService


# Router
router = APIRouter(
    prefix="/sync",
    tags=["Sincronización"]
)


@router.get(
    "/search/",
    summary="Buscar empleado en BioAlba",
    description="Busca un empleado por RUT en BioAlba para pre-poblar datos de reincorporación"
)
async def search_bioalba_empleado(
    rut: str = Query(..., description="RUT del empleado (con o sin formato)"),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar", "empleados.reincorporar"]))
) -> List[Dict[str, Any]]:
    """
    Buscar empleado en BioAlba por RUT.
    """
    service = SyncService()
    return await service.search_bioalba_empleado(rut)


@router.get(
    "/guardian/check/",
    summary="Verificar Guardián de Áreas",
    description="Descarga datos de BioAlba y verifica si hay áreas no mapeadas antes de abrir el modal."
)
async def check_guardian_areas(
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar"]))
) -> Dict[str, Any]:
    service = SyncService()
    return await service.check_guardian_areas()

@router.get(
    "/areas-preview/",
    summary="Previsualizar áreas de BioAlba",
    description="Retorna las áreas disponibles. Si refresh=true, escanea BioAlba en vivo (lento)."
)
async def preview_areas(
    refresh: bool = Query(False, description="Si es true, descarga el Excel completo de BioAlba para detectar nuevas áreas"),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar"]))
) -> List[str]:
    """
    Obtener listado de áreas desde BioAlba para el selector.
    """
    logger.info(f"📡 RECIBIDO: GET /sync/areas-preview (refresh={refresh})")
    
    service = SyncService()
    return await service.get_bioalba_areas(refresh=refresh)


@router.post(
    "/empleados/preview/",
    summary="Previsualizar empleados a sincronizar",
    description="Descarga empleados de BioAlba, filtra por áreas y cruza con DB local para mostrar nuevos vs existentes."
)
async def preview_empleados(
    request: SyncPreviewRequest = None,
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar"]))
) -> List[Dict[str, Any]]:
    service = SyncService()
    resoluciones_areas = request.resoluciones_areas if request else None
    selected_cargos = request.selected_cargos if request else None

    # RLS Check
    if not current_user.alcance_global:
        areas_permitidas = set(current_user.areas or [])
        if resoluciones_areas:
            for k, v in list(resoluciones_areas.items()):
                if v != "_IGNORE_" and v not in areas_permitidas:
                    raise HTTPException(status_code=403, detail=f"No tiene permisos para mapear al área '{v}'")
        else:
            raise HTTPException(status_code=403, detail="Un usuario zonal debe especificar resoluciones_areas para su scope.")

    return await service.preview_empleados(resoluciones_areas=resoluciones_areas, selected_cargos=selected_cargos)


class WizardProviderRequest(BaseModel):
    areas: List[str]

@router.post(
    "/wizard/turnos/",
    summary="Data Provider: Turnos para el Wizard",
    description="Devuelve la lista de turnos disponibles y las pre-asignaciones existentes para las áreas dadas."
)
async def wizard_provider_turnos(
    request: WizardProviderRequest,
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar"]))
) -> Dict[str, Any]:
    await db.connect()
    
    # 1. Obtener todos los turnos con campos necesarios para las radio cards del wizard
    turnos_records = await db.fetch_all("""
        SELECT t.id, t.nombre, t.tipo_programacion, t.meta_horas_semanales,
               MAX(td.num_semana) as num_semanas
        FROM turnos t
        LEFT JOIN turno_dias td ON td.turno_id = t.id
        GROUP BY t.id
        ORDER BY t.nombre ASC
    """)

    # 1b. Obtener las áreas asignadas a cada turno (para poder filtrar en el frontend)
    turno_areas_records = await db.fetch_all("""
        SELECT ta.turno_id, a.nombre as area_nombre
        FROM turno_areas ta
        JOIN areas a ON a.id = ta.area_id
    """)
    # Construir dict turno_id -> [area_nombres]
    turno_areas_map = {}
    for row in turno_areas_records:
        tid = row["turno_id"]
        if tid not in turno_areas_map:
            turno_areas_map[tid] = []
        turno_areas_map[tid].append(row["area_nombre"])

    turnos = [
        {
            "id": t["id"],
            "nombre": t["nombre"],
            "es_default": False,
            "tipo_programacion": t["tipo_programacion"] or "DINAMICO_FLEXIBLE",
            "meta_horas_semanales": t["meta_horas_semanales"] or 0,
            "num_semanas": t["num_semanas"] or 1,
            "areas": turno_areas_map.get(t["id"], [])  # lista de nombres de área
        }
        for t in turnos_records
    ]
    
    # 2. Buscar asignaciones existentes para las áreas (ya sean áreas nuevas o existentes)
    from backend.repositories.area import AreaRepository
    area_repo = AreaRepository(db)
    
    pre_asignaciones = {}
    for area_name in request.areas:
        area_id = await area_repo.find_area_id_by_name_or_alias(area_name)
        if area_id:
            # Buscar turno asociado al área
            asignacion = await db.fetch_one("SELECT turno_id FROM turno_areas WHERE area_id = ?", (area_id,))
            if asignacion:
                pre_asignaciones[area_name] = asignacion['turno_id']
                
    return {
        "turnos": [dict(t) for t in turnos],
        "pre_asignaciones": pre_asignaciones
    }

@router.post(
    "/wizard/bonos/",
    summary="Data Provider: Bonos para el Wizard",
    description="Devuelve la lista de bonos disponibles y las pre-asignaciones existentes para las áreas dadas."
)
async def wizard_provider_bonos(
    request: WizardProviderRequest,
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar"]))
) -> Dict[str, Any]:
    await db.connect()
    
    # 1. Obtener todos los bonos
    bonos = await db.fetch_all("SELECT id, nombre, descripcion FROM bonos ORDER BY nombre ASC")
    
    # 2. Buscar asignaciones existentes
    from backend.repositories.area import AreaRepository
    area_repo = AreaRepository(db)
    
    pre_asignaciones = {}
    for area_name in request.areas:
        area_id = await area_repo.find_area_id_by_name_or_alias(area_name)
        if area_id:
            asignaciones = await db.fetch_all("SELECT bono_id FROM area_bonos WHERE area_id = ?", (area_id,))
            if asignaciones:
                pre_asignaciones[area_name] = [a['bono_id'] for a in asignaciones]
                
    return {
        "bonos": [dict(b) for b in bonos],
        "pre_asignaciones": pre_asignaciones
    }

class WizardCommitAllRequest(BaseModel):
    areas: Dict[str, str]
    cargos: Dict[str, str]
    generos: List[str]
    turnos: Dict[str, Optional[int]]
    bonos: Optional[Dict[str, List[int]]] = None  # area_name → [bono_ids]

@router.post(
    "/wizard/commit-all/",
    summary="Wizard Mega-Commit: Persistir todo",
    description="Crea áreas, cargos, géneros, asignaciones de turnos y bonos por área en una sola transacción ACID."
)
async def wizard_commit_all(
    request: WizardCommitAllRequest,
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar"]))
) -> Dict[str, Any]:
    service = SyncService()
    try:
        result = await service.commit_wizard_all(
            areas=request.areas,
            cargos=request.cargos,
            generos=request.generos,
            turnos=request.turnos,
            bonos=request.bonos
        )
        return result
    except Exception as e:
        logger.error(f"Error en commit_wizard_all: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/wizard/commit/areas/",
    summary="Wizard Commit: Áreas",
    description="Confirma las áreas en la base de datos (Paso 1 del Wizard) para que puedan ser referenciadas por Bonos y Turnos."
)
async def wizard_commit_areas(
    request: WizardCommitAreasRequest,
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar"]))
) -> Dict[str, Any]:
    service = SyncService()
    try:
        result = await service.commit_wizard_areas(request.areas)
        return result
    except Exception as e:
        logger.error(f"Error en commit_wizard_areas: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/wizard/commit/cargos/",
    summary="Wizard Commit: Cargos",
    description="Confirma los cargos en la base de datos (Paso 2 del Wizard) para que puedan ser referenciados por Bonos y Turnos."
)
async def wizard_commit_cargos(
    request: WizardCommitCargosRequest,
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar"]))
) -> Dict[str, Any]:
    service = SyncService()
    try:
        result = await service.commit_wizard_cargos(request.cargos)
        return result
    except Exception as e:
        logger.error(f"Error en commit_wizard_cargos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ELIMINADO: WizardFinalizeRequest y POST /wizard/finalize/ (código muerto)
# Las áreas, cargos y turnos se commitean progresivamente vía /wizard/commit/*
# Los bonos son globales y se gestionan desde configuración.


@router.post(
    "/empleados/",
    summary="Sincronizar empleados",
    description="Sincroniza empleados desde BioAlba al sistema local. Opcionalmente filtra por áreas."
)
async def sincronizar_empleados(
    background_tasks: BackgroundTasks,
    request: SyncEmpleadosRequest = None,
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar"]))
) -> Dict[str, Any]:
    """
    Sincronizar empleados desde BioAlba.
    
    La sincronización se ejecuta en segundo plano.
    """
    areas = request.areas if request else None
    selected_cargos = request.selected_cargos if request else None

    # RLS Check
    if not current_user.alcance_global:
        if areas:
            for a in areas:
                if a not in (current_user.areas or []):
                    raise HTTPException(status_code=403, detail=f"No tiene permisos para sincronizar el área '{a}'")
        else:
            if current_user.areas:
                areas = current_user.areas
            else:
                raise HTTPException(status_code=403, detail="No tiene áreas permitidas asignadas")

    # Ejecutar en background
    background_tasks.add_task(ejecutar_sync_empleados, areas, selected_cargos)
    
    return {
        "message": "Sincronización de empleados iniciada en segundo plano",
        "status": "iniciada",
        "filters": {"areas": areas}
    }


@router.post(
    "/empleados/now/",
    summary="Sincronizar empleados (sync)",
    description="Sincroniza empleados de forma síncrona y retorna estadísticas. Máximo 10 empleados."
)
async def sincronizar_empleados_sync(
    request: SyncEmpleadosRequest = None,
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar"]))
) -> Dict[str, Any]:
    """
    Sincronizar empleados de forma síncrona.
    Espera a que termine y retorna estadísticas.
    Límite estricto: 10 empleados por batch.
    """
    MAX_BATCH = 10
    service = SyncService()
    areas = request.areas if request else None
    ruts  = request.ruts  if request else None
    selected_cargos = request.selected_cargos if request else None

    # RLS Check
    if not current_user.alcance_global:
        if areas:
            for a in areas:
                if a not in (current_user.areas or []):
                    raise HTTPException(status_code=403, detail=f"No tiene permisos para sincronizar el área '{a}'")
        else:
            if current_user.areas:
                areas = current_user.areas
            else:
                raise HTTPException(status_code=403, detail="No tiene áreas permitidas asignadas")

    if ruts and len(ruts) > MAX_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo {MAX_BATCH} empleados por sincronización masiva. Seleccionaste {len(ruts)}."
        )

    stats = await service.sync_empleados(areas=areas, ruts=ruts, selected_cargos=selected_cargos)
    return {
        "message": "Sincronización completada",
        "stats": stats
    }


@router.post(
    "/empleados/now/stream/",
    summary="Sincronizar empleados con SSE (progreso en tiempo real)",
    description="Sincroniza empleados emitiendo Server-Sent Events con el nombre y progreso de cada empleado. Máx. 10."
)
async def sincronizar_empleados_stream(
    request: SyncEmpleadosRequest = None,
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar"]))
):
    """
    Sincroniza empleados y emite SSE con:
      - event: start    → { total }
      - event: progress → { idx, total, nombre, rut }
      - event: done     → stats completo (incluye nuevos_detalles para onboarding)
      - event: error    → { message }

    Estrategia: Inyecta un progress_callback en SyncService y usa una Queue
    para desacoplar la producción de eventos del generador SSE.
    """
    areas = request.areas if request else None
    ruts  = request.ruts  if request else None
    selected_cargos = request.selected_cargos if request else None
    MAX_BATCH = 10

    # RLS Check
    if not current_user.alcance_global:
        if areas:
            for a in areas:
                if a not in (current_user.areas or []):
                    raise HTTPException(status_code=403, detail=f"No tiene permisos para sincronizar el área '{a}'")
        else:
            if current_user.areas:
                areas = current_user.areas
            else:
                raise HTTPException(status_code=403, detail="No tiene áreas permitidas asignadas")

    if ruts and len(ruts) > MAX_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo {MAX_BATCH} empleados por sincronización masiva. Seleccionaste {len(ruts)}."
        )

    # Queue para pasar eventos desde el task al generador SSE
    progress_q: asyncio.Queue = asyncio.Queue()

    async def _run_sync():
        """Corre sync_empleados con callback de progreso → pone eventos en la Queue."""
        try:
            service = SyncService()

            # Inyectar callback antes de arrancar el sync
            async def _on_progress(idx: int, total: int, nombre: str, rut: str):
                if idx == 0:
                    # Señal especial: 'start' con el total de empleados a sincronizar
                    await progress_q.put(('start', {'total': total}))
                else:
                    await progress_q.put(('progress', {'idx': idx, 'total': total, 'nombre': nombre, 'rut': rut}))

            service._progress_callback = _on_progress

            stats = await service.sync_empleados(areas=areas, ruts=ruts, selected_cargos=selected_cargos)
            if stats and stats.get("status") == "requires_confirmation":
                await progress_q.put(('requires_confirmation', stats))
            else:
                await progress_q.put(('done', stats))
        except Exception as err:
            logger.error(f"❌ [Stream Sync] Error en task: {err}")
            await progress_q.put(('error', {'message': str(err)}))


    async def _stream():
        # Lanzar el sync en background dentro del mismo event loop
        task = asyncio.create_task(_run_sync())

        # Esperar el primer evento (start o error) desde la queue
        # El evento 'start' lo emitirá sync_empleados si tiene el callback

        # Emitir eventos a medida que llegan a la queue
        done = False
        while not done:
            try:
                event_type, data = await asyncio.wait_for(progress_q.get(), timeout=300)
            except asyncio.TimeoutError:
                yield f"event: error\ndata: {json.dumps({'message': 'Timeout esperando respuesta del servidor'})}\n\n"
                task.cancel()
                return

            if event_type == 'start':
                yield f"event: start\ndata: {json.dumps(data)}\n\n"
            elif event_type == 'progress':
                yield f"event: progress\ndata: {json.dumps(data)}\n\n"
            elif event_type == 'requires_confirmation':
                yield f"event: requires_confirmation\ndata: {json.dumps(data)}\n\n"
                done = True
            elif event_type == 'done':
                yield f"event: done\ndata: {json.dumps(data)}\n\n"
                done = True
            elif event_type == 'error':
                yield f"event: error\ndata: {json.dumps(data)}\n\n"
                done = True

        await task  # Asegurarse de que el task terminó limpiamente

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )




# Caché de 15s para el health check: evita storm de queries durante el polling del frontend.
# Sin caché: 2 queries de red × cada poll × cada usuario conectado.
# Con caché: máximo 2 queries de red cada 15s para TODOS los usuarios.
_health_cache: Dict[str, Any] = {"data": None, "ts": None}
_HEALTH_TTL_SECONDS = 15

@router.get(
    "/health/",
    summary="Estado de salud del sistema",
    description="Verifica la conectividad con la base de datos local y la nube (Turso)"
)
async def system_health() -> Dict[str, Any]:
    """
    Verifica el estado de los componentes críticos.
    Respuesta cacheada 15s para evitar storm de queries en polling del frontend.
    """
    # ── Cache hit: devolver sin tocar la red ─────────────────────────────────────
    cached_ts = _health_cache["ts"]
    if cached_ts is not None and (_dt.now() - cached_ts).seconds < _HEALTH_TTL_SECONDS:
        return _health_cache["data"]

    # ── Cache miss: hacer los pings reales ───────────────────────────────
    local_ok = False
    cloud_ok = False

    try:
        await db.fetch_one("SELECT 1")
        local_ok = True
    except Exception:
        local_ok = False

    try:
        if db.use_turso:
            await db._execute_turso("SELECT 1")
            cloud_ok = True
        else:
            cloud_ok = True  # Sin Turso → sin nube → OK local
    except Exception:
        cloud_ok = False

    result = {
        "status": "ok" if local_ok and cloud_ok else "degraded",
        "local_db": "online" if local_ok else "offline",
        "cloud_db": "online" if cloud_ok else "offline",
        "sync_enabled": db.use_turso
    }

    _health_cache["data"] = result
    _health_cache["ts"] = _dt.now()
    return result



@router.get(
    "/test/",
    summary="Probar conexión",
    description="Prueba la conexión con BioAlba"
)
async def test_connection() -> Dict[str, Any]:
    """
    Probar conexión con BioAlba.
    
    Returns:
        Resultado del test
    """
    service = SyncService()
    
    if await service.test_connection():
        return {
            "status": "ok",
            "message": "Conexión exitosa con BioAlba"
        }
    else:
        return {
            "status": "error",
            "message": "Error de conexión con BioAlba"
        }


@router.post(
    "/asistencia/",
    summary="Sincronizar marcaciones",
    description="Sincroniza logs de asistencia desde BioAlba"
)
async def sincronizar_asistencia(
    background_tasks: BackgroundTasks,
    fecha_inicio: Optional[str] = Query(None, description="AAAA-MM-DD"),
    fecha_fin: Optional[str] = Query(None, description="AAAA-MM-DD"),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar"]))
) -> Dict[str, Any]:
    areas = None
    if not current_user.alcance_global:
        areas = current_user.areas or []
        if not areas:
            raise HTTPException(status_code=403, detail="No tiene áreas permitidas asignadas")

    background_tasks.add_task(ejecutar_sync_asistencia, fecha_inicio, fecha_fin, areas)
    return {
        "message": "Sincronización de asistencia iniciada en segundo plano",
        "status": "iniciada"
    }


@router.post(
    "/asistencia/now/",
    summary="Sincronizar marcaciones (sync)",
    description="Sincroniza logs de asistencia de forma síncrona. Opcionalmente filtra por áreas."
)
async def sincronizar_asistencia_sync(
    fecha_inicio: Optional[str] = Query(None, description="AAAA-MM-DD"),
    fecha_fin: Optional[str] = Query(None, description="AAAA-MM-DD"),
    request: SyncAsistenciaRequest = None,
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar"]))
) -> Dict[str, Any]:
    service = SyncService()

    # Prioridad: body > query param
    _inicio = (request.fecha_inicio if request and request.fecha_inicio else None) or fecha_inicio
    _fin    = (request.fecha_fin    if request and request.fecha_fin    else None) or fecha_fin
    areas   = request.areas if request else None

    # RLS Check
    if not current_user.alcance_global:
        if areas:
            for a in areas:
                if a not in (current_user.areas or []):
                    raise HTTPException(status_code=403, detail=f"No tiene permisos para el área '{a}'")
        else:
            if current_user.areas:
                areas = current_user.areas
            else:
                raise HTTPException(status_code=403, detail="No tiene áreas permitidas asignadas")

    logger.info(f"📅 Sync marcaciones: {_inicio} → {_fin} | áreas: {areas or 'todas'}")

    stats = await service.sync_marcaciones(_inicio, _fin, areas, force_recalculate=True)
    return {
        "message": "Sincronización de asistencia completada",
        "stats": stats,
        "filters": {"areas": areas}
    }


@router.post(
    "/asistencia/empleado/{empleado_id}/",
    summary="Sincronizar marcaciones de un empleado específico",
    description="Descarga marcaciones desde BioAlba para UN empleado, filtrando por su RUT. No afecta el resto del área."
)
async def sincronizar_asistencia_empleado(
    empleado_id: int,
    fecha_inicio: Optional[str] = Query(None, description="AAAA-MM-DD. Si no se indica, usa el mes actual."),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.wizard", "marcaciones.sincronizar", "reportes.sincronizar"]))
) -> Dict[str, Any]:
    """
    Sync de marcaciones individual: descarga BioAlba y persiste solo las marcas
    del RUT del empleado dado, respetando el BioAlba Gate (solo fechas con turno asignado).
    """
    from backend.repositories.empleado import EmpleadoRepository
    await db.connect()
    emp_repo = EmpleadoRepository(db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Empleado {empleado_id} no encontrado")

    # RLS Check
    if not current_user.alcance_global and emp.area not in (current_user.areas or []):
        raise HTTPException(status_code=403, detail="No tiene permisos para este empleado")

    rut = str(emp.rut)
    service = SyncService()
    stats = await service.sync_marcaciones(
        fecha_inicio=fecha_inicio,
        ruts=[rut],
        force_recalculate=False,
    )
    return {
        "message": f"Sincronización individual completada para empleado {empleado_id}",
        "rut": rut,
        "stats": stats,
    }




@router.get(
    "/logs/",
    summary="Logs de Sincronización",
    description="Historial reciente de sincronizaciones con BioAlba"
)
async def get_sync_logs(
    limit: int = Query(10, description="Cantidad de registros a obtener")
) -> List[Dict[str, Any]]:
    """Obtiene el historial de ejecuciones técnicas de BioAlba."""
    try:
        query = "SELECT * FROM sync_logs ORDER BY id DESC LIMIT ?"
        rows = await db.fetch_all(query, (limit,))

        results = []
        for r in rows:
            d = dict(r)
            if d.get('detalle_json'):
                try:
                    d['detalle'] = json.loads(d['detalle_json'])
                except json.JSONDecodeError as _je:
                    logger.debug(f"[SyncLogs] detalle_json mal formado en log id={d.get('id')}: {_je}")
                    d['detalle'] = {}
                del d['detalle_json']
            results.append(d)

        return results
    except Exception as e:
        logger.error(f"❌ Error obteniendo sync_logs: {e}")
        return []


@router.post(
    "/admin/reset-replica/",
    summary="Resetear réplica local de Turso",
    description=(
        "⚠️ ADMIN ONLY. Destruye y re-clona la réplica local desde Turso Cloud. "
        "Úsalo solo cuando hay errores persistentes de Frame Mismatch. "
        "El proceso tarda ~30 segundos mientras se descarga la réplica."
    )
)
async def reset_turso_replica(
    current_user: SecurityContext = Depends(RequirePermission("configuracion.seguridad"))
) -> Dict[str, Any]:
    """
    Resetea la réplica local de Turso sin reiniciar el servidor.
    
    Elimina los archivos locales (.db, -wal, -shm, -info, .meta) y
    reconecta para que libsql haga un full-clone desde Turso Cloud.
    Solo disponible para usuarios con permiso configuracion.seguridad.
    """
    logger.warning(f"⚠️ Reset de réplica solicitado por usuario: {getattr(current_user, 'username', 'desconocido')}")
    
    try:
        await db._auto_heal_sync_conflict()
        return {
            "status": "ok",
            "message": "Réplica reseteada y re-sincronizada desde Turso Cloud.",
            "detail": "La réplica local fue destruida y re-clonada exitosamente."
        }
    except Exception as e:
        logger.error(f"❌ Error en reset de réplica: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error reseteando la réplica: {str(e)}"
        )



async def ejecutar_sync_empleados(areas: List[str] = None, selected_cargos: List[str] = None):
    service = SyncService()
    await service.sync_empleados(areas=areas, selected_cargos=selected_cargos)


async def ejecutar_sync_asistencia(fecha_inicio: str = None, fecha_fin: str = None, areas: List[str] = None):
    """Función helper para ejecutar sync de asistencia en background"""
    service = SyncService()
    await service.sync_marcaciones(fecha_inicio, fecha_fin, areas=areas, force_recalculate=True)
