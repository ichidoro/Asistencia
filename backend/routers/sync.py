"""
Router - Sincronización
Endpoints para sincronizar datos desde BioAlba
"""

import json
from datetime import datetime as _dt
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Query, Depends
from typing import Dict, Any, Optional, List
from loguru import logger
from backend.schemas.sync import SyncEmpleadosRequest, SyncAsistenciaRequest, SyncPreviewRequest
from fastapi.responses import StreamingResponse
import asyncio
from pydantic import BaseModel

from backend.core.security import SecurityContext, RequirePermission
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
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.sincronizar_biometrico"))
) -> List[Dict[str, Any]]:
    """
    Buscar empleado en BioAlba por RUT.
    """
    service = SyncService()
    return await service.search_bioalba_empleado(rut)


@router.get(
    "/areas-preview/",
    summary="Previsualizar áreas de BioAlba",
    description="Retorna las áreas disponibles. Si refresh=true, escanea BioAlba en vivo (lento)."
)
async def preview_areas(
    refresh: bool = Query(False, description="Si es true, descarga el Excel completo de BioAlba para detectar nuevas áreas"),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.sincronizar_biometrico"))
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
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.sincronizar_biometrico"))
) -> List[Dict[str, Any]]:
    service = SyncService()
    areas = request.areas if request else None
    return await service.preview_empleados(areas=areas)


class ResolverAreasRequest(BaseModel):
    resoluciones: Dict[str, str]  # { "BODEGASS": "BODEGA", "NUEVA_AREA": "NUEVA_AREA" }

@router.post(
    "/resolver-areas/",
    summary="Resolver áreas desconocidas (Guardián)",
    description="Asigna alias ortográficos o crea nuevas áreas en el catálogo."
)
async def resolver_areas(
    request: ResolverAreasRequest,
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.sincronizar_biometrico"))
) -> Dict[str, Any]:
    from backend.repositories.area import AreaRepository
    await db.connect()
    area_repo = AreaRepository(db)
    
    for area_bioalba, resolucion in request.resoluciones.items():
        if area_bioalba == resolucion:
            # Create new area if it doesn't exist
            existing = await area_repo.get_area_by_name(resolucion)
            if not existing:
                await area_repo.create_area(resolucion)
        else:
            # Create alias
            area_real = await area_repo.get_area_by_name(resolucion)
            if not area_real:
                area_id = await area_repo.create_area(resolucion)
            else:
                area_id = area_real['id']
            await area_repo.create_alias(area_bioalba, area_id)
            
    return {"status": "ok", "message": "Áreas resueltas correctamente. Puede reanudar la sincronización."}



@router.post(
    "/empleados/",
    summary="Sincronizar empleados",
    description="Sincroniza empleados desde BioAlba al sistema local. Opcionalmente filtra por áreas."
)
async def sincronizar_empleados(
    background_tasks: BackgroundTasks,
    request: SyncEmpleadosRequest = None,
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.sincronizar_biometrico"))
) -> Dict[str, Any]:
    """
    Sincronizar empleados desde BioAlba.
    
    La sincronización se ejecuta en segundo plano.
    """
    # Ejecutar en background
    areas = request.areas if request else None
    background_tasks.add_task(ejecutar_sync_empleados, areas)
    
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
    request: SyncEmpleadosRequest = None
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

    if ruts and len(ruts) > MAX_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo {MAX_BATCH} empleados por sincronización masiva. Seleccionaste {len(ruts)}."
        )

    stats = await service.sync_empleados(areas=areas, ruts=ruts)
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
    request: SyncEmpleadosRequest = None
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
    MAX_BATCH = 10

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

            stats = await service.sync_empleados(areas=areas, ruts=ruts)
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
    fecha_fin: Optional[str] = Query(None, description="AAAA-MM-DD")
) -> Dict[str, Any]:
    background_tasks.add_task(ejecutar_sync_asistencia, fecha_inicio, fecha_fin)
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
    request: SyncAsistenciaRequest = None
) -> Dict[str, Any]:
    service = SyncService()
    
    _inicio = request.fecha_inicio if request and request.fecha_inicio else fecha_inicio
    _fin = request.fecha_fin if request else None
    areas = request.areas if request else None
    
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
) -> Dict[str, Any]:
    """
    Sync de marcaciones individual: descarga BioAlba y persiste solo las marcas
    del RUT del empleado dado, respetando el BioAlba Gate (solo fechas con turno asignado).
    """
    emp_row = await db.fetch_one("SELECT rut FROM empleados WHERE id = ?", (empleado_id,))
    if not emp_row:
        raise HTTPException(status_code=404, detail=f"Empleado {empleado_id} no encontrado")

    rut = str(emp_row["rut"])
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



async def ejecutar_sync_empleados(areas: List[str] = None):
    """Función helper para ejecutar sync en background"""
    service = SyncService()
    await service.sync_empleados(areas=areas)


async def ejecutar_sync_asistencia(fecha_inicio: str = None, fecha_fin: str = None):
    """Función helper para ejecutar sync de asistencia en background"""
    service = SyncService()
    await service.sync_marcaciones(fecha_inicio, fecha_fin, force_recalculate=True)
