"""
Router - Asistencia: asignaciones de turno (individual y en grupo), procesar y reprocesar (por persona, por período y
masivo), avance de los trabajos de reproceso, recalcular la bolsa y reasignar un turno. Separado de
routers/asistencia.py en la etapa 6 de la auditoría, con el mismo código; las direcciones siguen bajo /api/asistencia
(asistencia.py incluye este router).
"""
from fastapi import Query, Depends, Body, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from loguru import logger
from backend.services.asistencia_service import AsistenciaService
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.empleado import EmpleadoRepository
from backend.repositories.turno import TurnoRepository
from backend.repositories.seguridad import SeguridadRepository
from backend.core.security import RequirePermission, SecurityContext
from backend.schemas.asistencia import BatchSyncRequest, ReasignarTurnoRequest, AsignacionIndividual
from backend.routers.asistencia_comun import get_asistencia_service
from fastapi import APIRouter

router = APIRouter()


@router.post("/asignaciones/individual/")
async def post_asignacion_individual(
    data: AsignacionIndividual,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Onboarding RFC Paso 7: Asigna un turno oficial desde la fecha indicada (sin fecha_fin).
    Responde INMEDIATAMENTE — el job background corre SECUENCIALMENTE:
      Fase 1 (si sync_bioalba=True): Descarga marcaciones BioAlba (skip_recalc=True)
      Fase 2: reprocesar_periodo_empleado con el contexto actualizado
    Retorna `job_id` para que el frontend pueda sondear el progreso en /jobs/{job_id}/.
    """
    try:
        turno_repo = TurnoRepository(service.repository.db)

        # 1. Soft-Close: Cerrar asignación previa activa que comenzó antes de data.fecha
        await turno_repo.cerrar_asignacion_previa(data.empleado_id, data.fecha)

        # 2. Reemplazo in-place si ya existe una asignación que inicia exactamente en data.fecha
        exact_asig = await turno_repo.get_asignacion_que_inicia(data.empleado_id, data.fecha)
        if exact_asig:
            await turno_repo.set_turno_asignacion_abierta(exact_asig['id'], data.turno_id)
            logger.info(f"🔄 Turno #{exact_asig['id']} actualizado in-place a turno {data.turno_id} para emp {data.empleado_id} desde {data.fecha}")
        else:
            await turno_repo.insertar_asignacion_abierta(data.empleado_id, data.turno_id, data.fecha)
            logger.info(f"✅ Turno {data.turno_id} asignado a empleado {data.empleado_id} desde {data.fecha}")

        # 3. Neutralizar cualquier asignación futura que quede eclipsada por el nuevo turno continuo
        await turno_repo.borrar_asignaciones_posteriores(data.empleado_id, data.fecha)

        # 4. Obtener RUT del empleado para el sync individual
        emp_row = await EmpleadoRepository(service.repository.db).get_rut(data.empleado_id)
        empleado_rut = emp_row['rut'] if emp_row else None

        # 3. Generar job_id único para tracking de progreso
        import uuid
        hoy = datetime.now().date().isoformat()
        job_id = f"repr-{data.empleado_id}-{uuid.uuid4().hex[:8]}"

        # 4. Inicializar el job en el registry YA (antes de lanzar el task)
        #    Así el frontend puede empezar a ver el estado "syncing" desde el primer poll
        from backend.services.asistencia_service import _init_job as _ij
        total_days_est = (datetime.now().date() - datetime.strptime(data.fecha, "%Y-%m-%d").date()).days + 1
        _ij(job_id, data.empleado_id, total_days_est, data.fecha)

        # 5. Lanzar job SECUENCIAL en BACKGROUND
        sync_bioalba = data.sync_bioalba

        async def _reprocesar_bg():
            from backend.services.asistencia_service import _update_job, _update_job
            try:
                # ─── FASE 1: BioAlba sync (si fue solicitado) ─────────────────
                # BioAlba entrega un Excel por mes. Si el onboarding cubre varios
                # meses (ej: desde Marzo a Abril) debemos descargar cada mes por separado.
                if sync_bioalba and empleado_rut:
                    logger.info(f"☁️ [BG] Fase 1: Sync BioAlba para empleado {data.empleado_id} (RUT {empleado_rut}) desde {data.fecha}")
                    _update_job(job_id,
                        status="syncing",
                        phase_label="Descargando marcaciones desde BioAlba...",
                        pct=2,
                    )
                    try:
                        from backend.services.sync_service import SyncService
                        from datetime import date as _date
                        import calendar as _cal

                        fecha_ini_dt = datetime.strptime(data.fecha, "%Y-%m-%d").date()
                        fecha_hoy_dt = datetime.now().date()

                        # Iterar mes a mes desde el mes de inicio hasta el mes actual
                        mes_cur = fecha_ini_dt.replace(day=1)
                        meses_a_sync = []
                        while mes_cur <= fecha_hoy_dt.replace(day=1):
                            meses_a_sync.append(mes_cur.strftime("%Y-%m-%d"))
                            # Avanzar al primer día del mes siguiente
                            ultimo_dia = _cal.monthrange(mes_cur.year, mes_cur.month)[1]
                            mes_cur = (mes_cur.replace(day=ultimo_dia) + timedelta(days=1))

                        logger.info(f"📅 [BG] Descargando {len(meses_a_sync)} mes(es) de BioAlba: {meses_a_sync}")

                        for i, fecha_mes in enumerate(meses_a_sync):
                            _update_job(job_id,
                                phase_label=f"Descargando BioAlba {fecha_mes[:7]} ({i+1}/{len(meses_a_sync)})...",
                                pct=2 + int(3 * i / max(len(meses_a_sync), 1)),
                            )
                            sync_svc = SyncService()
                            await sync_svc.sync_marcaciones(
                                fecha_inicio=fecha_mes,
                                ruts=[empleado_rut],
                                skip_recalc=True,
                            )
                            logger.info(f"✅ [BG] Mes {fecha_mes[:7]} sincronizado")

                        logger.info(f"✅ [BG] Fase 1 completada: {len(meses_a_sync)} meses sincronizados de BioAlba")
                        _update_job(job_id, phase_label="Marcaciones descargadas. Iniciando cálculo...", pct=5)
                    except Exception as sync_err:
                        logger.warning(f"⚠️ [BG] Fase 1 BioAlba falló (continúa con reproceso): {sync_err}")
                        _update_job(job_id, phase_label="BioAlba no disponible. Calculando igualmente...", pct=5)
                else:
                    _update_job(job_id, phase_label="Iniciando cálculo de asistencia...", pct=2)

                # ─── FASE 2: Cálculo de asistencia día a día (con job tracking) ────────────
                logger.info(f"📊 [BG] Fase 2: Calculando asistencia {data.empleado_id}: {data.fecha} → {hoy} [job={job_id}]")
                _update_job(job_id, status="running", phase_label="Calculando asistencia día a día...")

                stats = await service.reprocesar_periodo_empleado(
                    empleado_id=data.empleado_id,
                    fecha_inicio=data.fecha,
                    fecha_fin=hoy,
                    force=True,
                    job_id=job_id,
                )
                logger.info(f"✅ [BG] Cálculo completado: {stats.get('procesados', 0)} días [job={job_id}]")

            except Exception as bg_err:
                logger.error(f"❌ [BG] Error en job {job_id}: {bg_err}")
                from backend.services.asistencia_service import _update_job as _uj
                _uj(job_id, status="error", error=str(bg_err))

        import asyncio

        # En modo batch: solo guardar el turno, NO lanzar reproceso individual
        # (el batch-sync final lo procesará todo junto evitando colisiones de _db_lock)
        if data.skip_reproceso:
            logger.info(f"[Batch] Turno {data.turno_id} guardado para emp {data.empleado_id} sin reproceso individual")
            return {
                "success": True,
                "message": "Turno asignado (batch mode - sin reproceso individual).",
                "reproceso_bg": False,
                "job_id": None,
            }

        asyncio.create_task(_reprocesar_bg())

        # 6. Responder de inmediato con job_id
        return {
            "success": True,
            "message": "Turno asignado. Job de sincronización iniciado en segundo plano.",
            "reproceso_bg": True,
            "job_id": job_id,
            "sync_bioalba": sync_bioalba,
        }
    except Exception as e:
        logger.error(f"❌ Error asignando turno: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/asignaciones/batch-sync/")
async def post_batch_sync(
    data: BatchSyncRequest,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Onboarding Batch — Fase 4: Sincroniza y procesa N empleados en un único job background.

    Optimización vs N llamadas individuales:
    - Agrupa empleados por mes único → descarga cada Excel de BioAlba UNA sola vez
    - Procesa los N empleados secuencialmente con el mismo contexto de DB
    - Retorna batch_job_id + job_ids individuales para tracking de progreso
    """
    if not data.items:
        raise HTTPException(status_code=400, detail="La lista de items está vacía")

    import uuid
    import asyncio
    import calendar as _cal
    from backend.services.asistencia_service import _init_job as _ij, _update_job

    hoy = datetime.now().date().isoformat()
    batch_job_id = f"batch-{uuid.uuid4().hex[:8]}"
    # ── 1. Recopilar RUTs para todos los empleados ────────────────────────
    # ── Fix #1: 1 sola query para todos los empleados en vez de N individuales ─
    ids_empleados = [item.empleado_id for item in data.items]
    emp_rows = await EmpleadoRepository(service.repository.db).get_rut_y_nombre_por_ids(ids_empleados)
    emp_info = {r["id"]: {"rut": r["rut"], "nombre": f"{r['apellido_paterno']} {r['nombre']}"} for r in emp_rows}

    job_ids = {}
    for item in data.items:
        total_days = (datetime.strptime(hoy, "%Y-%m-%d").date() -
                      datetime.strptime(item.fecha_inicio, "%Y-%m-%d").date()).days + 1
        jid = f"repr-{item.empleado_id}-{uuid.uuid4().hex[:8]}"
        _ij(jid, item.empleado_id, total_days, item.fecha_inicio)
        job_ids[item.empleado_id] = jid

    # ── 2. Calcular meses únicos a descargar ─────────────────────────────
    # Agrupar: mes_key → set(ruts) para minimizar descargas de BioAlba
    meses_ruts: dict = {}
    for item in data.items:
        if not getattr(item, 'sync_bioalba', True):
            continue
        rut = emp_info.get(item.empleado_id, {}).get("rut")
        if not rut:
            continue
        fecha_ini_dt = datetime.strptime(item.fecha_inicio, "%Y-%m-%d").date()
        fecha_hoy_dt = datetime.strptime(hoy, "%Y-%m-%d").date()
        mes_cur = fecha_ini_dt.replace(day=1)
        while mes_cur <= fecha_hoy_dt.replace(day=1):
            mes_key = mes_cur.strftime("%Y-%m-%d")
            meses_ruts.setdefault(mes_key, set()).add(rut)
            ultimo_dia = _cal.monthrange(mes_cur.year, mes_cur.month)[1]
            mes_cur = (mes_cur.replace(day=ultimo_dia) + timedelta(days=1))

    total_meses = len(meses_ruts)
    logger.info(
        f"🚀 [Batch {batch_job_id}] {len(data.items)} empleados | "
        f"{total_meses} mes(es) únicos a descargar de BioAlba"
    )

    async def _batch_bg():
        try:
            from backend.services.sync_service import SyncService
            from backend.core.database import db as _db


            # ── FASE A: Descargar Excels únicos (→4 50% del progreso total) ──
            for i, (mes_key, ruts) in enumerate(meses_ruts.items()):
                logger.info(
                    f"☁️ [Batch] Descargando BioAlba {mes_key[:7]} "
                    f"({i+1}/{total_meses}) para {len(ruts)} empleado(s)..."
                )
                # Progreso 5-50% repartido entre los meses
                pct_fase_a = 5 + int(45 * i / max(total_meses, 1))
                for jid in job_ids.values():
                    _update_job(jid,
                        status="syncing",
                        phase_label=f"Descargando marcaciones {mes_key[:7]}...",
                        pct=pct_fase_a,
                    )
                try:
                    sync_svc = SyncService()
                    await sync_svc.sync_marcaciones(
                        fecha_inicio=mes_key,
                        ruts=list(ruts),
                        skip_recalc=True,
                    )
                    # Actualizar al 50% max al finalizar fase A
                    pct_mes_ok = 5 + int(45 * (i + 1) / max(total_meses, 1))
                    for jid in job_ids.values():
                        _update_job(jid, pct=pct_mes_ok)
                    logger.info(f"✅ [Batch] {mes_key[:7]} descargado")
                except Exception as sync_err:
                    logger.warning(f"⚠️ [Batch] BioAlba {mes_key[:7]} falló: {sync_err}")

            # ── FASE B: Reprocesar empleados (50-95%) ──────────────────────────
            #
            # OPTIMIZACIÓN CLAVE: collect_only + feriados_preloaded
            # ─────────────────────────────────────────────────────────────────────
            # ANTES: 10 empleados × 1 execute_batch c/u → 10 conn.sync() encadenados
            #        = cada empleado espera ~25s al sync del anterior = ~253s total
            #
            # AHORA:
            #   B-1: Pre-cargar feriados 1 vez para todos los empleados
            #   B-2: Calcular cada empleado en memoria (collect_only=True, 0 writes)
            #   B-3: 1 solo execute_batch con todos los resultados (~320 registros)
            #        → 1 conn.sync() total ≈ 25s en vez de 250s
            # ─────────────────────────────────────────────────────────────────────
            total_emps = len(data.items)

            # ── Fase B-1: Pre-cargar feriados 1 vez ────────────────────────────
            for jid in job_ids.values():
                _update_job(jid, phase_label="Pre-cargando calendario de feriados...", pct=51)
            feriados_batch: dict = {}
            try:
                from backend.services.calendario_service import CalendarioService
                from datetime import datetime as _dt
                cal_svc = CalendarioService()
                anio_ini = min(
                    _dt.strptime(item.fecha_inicio, "%Y-%m-%d").year
                    for item in data.items
                )
                anio_hoy = _dt.strptime(hoy, "%Y-%m-%d").year
                for _anio in range(anio_ini, anio_hoy + 1):
                    raw = await cal_svc.get_feriados(_anio)
                    feriados_batch.update({f['fecha']: f['descripcion'] for f in raw})
                logger.info(f"[⚡ Batch] Feriados pre-cargados: {len(feriados_batch)} entradas (años {anio_ini}-{anio_hoy})")
            except Exception as fer_err:
                logger.warning(f"⚠️ [Batch] No se pudieron pre-cargar feriados: {fer_err}. Cada empleado los cargará por separado.")
                feriados_batch = None  # None → reprocesar_periodo_empleado los carga solo

            # ── Fase B-2: Calcular en memoria (collect_only=True, 0 writes a DB) ─
            all_results_to_save: list = []  # Acumula resultados de TODOS los empleados
            all_he_to_save: list = []
            all_he_to_delete: list = []
            all_je_to_save: list = []
            all_je_to_delete: list = []

            for emp_idx, item in enumerate(data.items):
                jid = job_ids.get(item.empleado_id)
                nombre = emp_info.get(item.empleado_id, {}).get("nombre", f"Emp {item.empleado_id}")
                pct_inicio_emp = 52 + int(40 * emp_idx / max(total_emps, 1))
                logger.info(f"📊 [Batch] Calculando (en memoria) {nombre} desde {item.fecha_inicio}")
                _update_job(jid,
                    status="running",
                    phase_label=f"Calculando {nombre} ({emp_idx+1}/{total_emps})...",
                    pct=pct_inicio_emp,
                )
                try:
                    result = await service.reprocesar_periodo_empleado(
                        empleado_id=item.empleado_id,
                        fecha_inicio=item.fecha_inicio,
                        fecha_fin=hoy,
                        force=True,
                        job_id=jid,
                        feriados_preloaded=feriados_batch,
                        collect_only=True,           # ← SIN escrituras a DB
                    )
                    collected = result.get('_collect', [])
                    all_results_to_save.extend(collected)
                    all_he_to_save.extend(result.get('_he_collect', []))
                    all_he_to_delete.extend(result.get('_he_delete', []))
                    all_je_to_save.extend(result.get('_je_collect', []))
                    all_je_to_delete.extend(result.get('_je_delete', []))
                    logger.info(
                        f"[⚡ Batch] {nombre}: {result.get('procesados',0)} días calculados, "
                        f"{len(collected)} a guardar, {result.get('sin_cambio',0)} sin cambio"
                    )
                except Exception as emp_err:
                    logger.error(f"❌ [Batch] Error calculando {nombre}: {emp_err}")
                    _update_job(jid, status="error", error=str(emp_err))

            # ── Fase B-3: UN SOLO batch_upsert masivo para todos los empleados ──
            if all_results_to_save or all_he_to_save or all_he_to_delete or all_je_to_save or all_je_to_delete:
                for jid in job_ids.values():
                    _update_job(jid,
                        phase_label=f"Guardando registros en la base de datos...",
                        pct=93,
                    )
                try:
                    import time as _time_mod
                    t_save = _time_mod.time()
                    
                    # 1. Guardar asistencias
                    if all_results_to_save:
                        await service.repository.batch_upsert_asistencia(all_results_to_save)
                        
                    # 2. Guardar y eliminar horas extras
                    if all_he_to_save:
                        await service.he_repo.batch_upsert(all_he_to_save)
                    if all_he_to_delete:
                        for eid_del, f_str in all_he_to_delete:
                            await service.he_repo.delete_by_empleado_fecha(eid_del, f_str)
                            
                    # 3. Guardar y eliminar jornadas especiales
                    if all_je_to_save:
                        for je_rec in all_je_to_save:
                            await service.repository.upsert_jornada_especial(je_rec)
                    if all_je_to_delete:
                        for eid_del, f_str in all_je_to_delete:
                            await service._delete_je_no_validada(eid_del, f_str)
                            
                    elapsed_save = int((_time_mod.time() - t_save) * 1000)
                    logger.info(
                        f"[⚡ Batch] Guardado completado en {elapsed_save}ms"
                    )
                except Exception as save_err:
                    logger.error(f"❌ [Batch] Error en commit masivo: {save_err}. Intentando fallback por empleado...")
                    for item in data.items:
                        emp_results = [r for r in all_results_to_save if r.get('empleado_id') == item.empleado_id]
                        if emp_results:
                            try:
                                await service.repository.batch_upsert_asistencia(emp_results)
                            except Exception as fb_err:
                                logger.error(f"❌ [Batch Fallback] emp {item.empleado_id}: {fb_err}")

            # Marcar todos los jobs como completados
            for jid in job_ids.values():
                _update_job(jid, status="done", pct=100, phase_label="Completado")

        except Exception as bg_err:
            logger.error(f"❌ [Batch {batch_job_id}] Error global: {bg_err}")
            for jid in job_ids.values():
                _update_job(jid, status="error", error=str(bg_err))

    asyncio.create_task(_batch_bg())

    return {
        "success": True,
        "batch_job_id": batch_job_id,
        "job_ids": job_ids,         # {empleado_id: job_id} para polling individual
        "meses_a_descargar": total_meses,
        "empleados": len(data.items),
        "message": f"Batch iniciado: {len(data.items)} empleados, {total_meses} mes(es) únicos de BioAlba"
    }



@router.get("/jobs/{job_id}/", summary="Estado de un job de reproceso")
async def get_job_progress(
    job_id: str,
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Retorna el estado actual de un job de reproceso iniciado en background.
    Usado por el frontend para mostrar la barra de progreso día a día.
    """
    from backend.services.asistencia_service import get_job_status
    status = get_job_status(job_id)
    if status is None:
        return {"status": "not_found", "job_id": job_id}
    return {"job_id": job_id, **status}



@router.post("/procesar/")
async def procesar_asistencia(
    fecha_inicio: str = Query(..., description="Fecha inicial AAAA-MM-DD"),
    fecha_fin: Optional[str] = Query(None, description="Fecha final AAAA-MM-DD (opcional)"),
    areas: Optional[List[str]] = Query(None, description="Filtrar por áreas específicas"),
    force: bool = Query(False, description="Forzar recálculo inclusive en días ya procesados"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Ejecuta el motor de reglas de asistencia para un periodo.
    """
    # RLS: Si no es global, solo puede procesar sus áreas
    areas_final = current_user.filtrar_areas(areas)
    
    # Si intentó filtrar áreas que no tiene permitidas, retornar 403 vía filtrado manual si fuera necesario,
    # pero filtrar_areas ya nos da la intersección segura.
    if not areas_final and not current_user.alcance_global and areas: # Only raise if areas were explicitly requested and filtered out
        raise HTTPException(status_code=403, detail="No tiene permisos para procesar las áreas solicitadas")

    stats = await service.procesar_periodo(fecha_inicio, fecha_fin, areas_final, force=force)
    return {
        "message": f"Procesamiento completado para {stats['total_dias']} días",
        "stats": stats
    }

@router.post("/reproceso-masivo-async/", status_code=202)
async def reproceso_masivo_async(
    fecha_inicio: str = Query(..., description="Fecha inicial AAAA-MM-DD"),
    fecha_fin: str = Query(..., description="Fecha final AAAA-MM-DD"),
    area: Optional[str] = Query(None, description="Filtrar por área específica (opcional)"),
    background_tasks: BackgroundTasks = None,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Lanza un reprocesamiento masivo histórico en segundo plano.
    
    - Procesa empleados activos del período indicado
    - Filtro opcional por área (respeta RLS del usuario)
    - Retorna 202 Accepted de inmediato
    - Consultar progreso en GET /reproceso-masivo-status/
    """
    from backend.services.asistencia_service import _reproceso_lock, get_reproceso_status

    # RLS: validar que el usuario pueda procesar el área solicitada
    current_user.verificar_acceso_area(area, f"reprocesar el área '{area}'") if area else None

    # Si el usuario no es global y no pasó área, restringir a sus propias áreas
    # (se convierte en la primera área permitida; si tiene varias se procesarán todas)
    area_final = area
    if current_user.get_areas_filter() is not None and not area:
        # No-global sin filtro: restringir a sus propias áreas
        if current_user.areas and len(current_user.areas) == 1:
            area_final = current_user.areas[0]

    # [SEMÁFORO] Verificar si ya hay un reprocesamiento en curso
    if _reproceso_lock.locked():
        status = get_reproceso_status()
        raise HTTPException(
            status_code=423,
            detail={
                "message": "Ya hay un reprocesamiento masivo en curso.",
                "progreso": status.get("progreso"),
                "chunks": f"{status.get('chunks_completados', 0)}/{status.get('chunks_totales', 0)}"
            }
        )
    
    # Si se especificó una área final, verificar si el rango completo está cerrado
    if area_final:
        closed = await AsistenciaRepository(service.repository.db).get_cierre_que_cubre(area_final, fecha_inicio, fecha_fin)
        if closed:
            raise HTTPException(
                status_code=403,
                detail=f"No se puede iniciar el reproceso. El período solicitado ya se encuentra cerrado para el área '{area_final}'."
            )

    # Adquirir el lock ANTES de lanzar el background task (se libera en el finally del Worker)
    await _reproceso_lock.acquire()
    
    # Lanzar la tarea en segundo plano (try/except para garantizar liberación del lock ante excepciones)
    try:
        background_tasks.add_task(
            service.reproceso_masivo_async,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            area=area_final,
        )
    except Exception:
        _reproceso_lock.release()
        raise
    
    return {
        "message": "Reprocesamiento masivo iniciado en segundo plano.",
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "area": area_final,
        "status_url": "/api/asistencia/reproceso-masivo-status/"
    }

@router.get("/reproceso-masivo-status/")
async def reproceso_masivo_status(
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Consulta el progreso del reprocesamiento masivo.
    Polling desde el frontend para mostrar barra de progreso.
    """
    from backend.services.asistencia_service import get_reproceso_status
    return get_reproceso_status()


@router.post("/recalcular-bolsa/")
async def recalcular_bolsa_endpoint(
    empleado_id: int = Body(...),
    fecha_inicio: str = Body(...),
    fecha_fin: str = Body(...),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Fuerza el recalculo completo de la Bolsa Flexible para un empleado en un periodo.
    """
    # RLS
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    current_user.verificar_acceso_area(emp.area, "este empleado")
    try:
        resultado = await service.recalcular_bolsa_periodo(empleado_id, fecha_inicio, fecha_fin)
        if resultado.get("status") != "ok":
            return {
                "success": False,
                "mensaje": f"No se pudo recalcular: {resultado.get('status')}",
                "datos": resultado
            }
        return {
            "success": True,
            "mensaje": "Bolsa recalculada exitosamente",
            "datos": resultado
        }
    except Exception as e:
        from loguru import logger
        logger.error(f"Error recalculando bolsa mensual: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.post("/reprocesar-empleado/")
async def reprocesar_empleado_endpoint(
    empleado_id: int = Body(...),
    fecha_inicio: str = Body(...),
    fecha_fin: str = Body(...),
    force: bool = Body(False),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Fuerza el reprocesamiento de asistencia para un empleado en un rango de fechas con RLS.
    Útil para corregir errores históricos de asignación de turnos (Reversión).
    """
    # RLS
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    current_user.verificar_acceso_area(emp.area, "este empleado")
    try:
        stats = await service.reprocesar_periodo_empleado(empleado_id, fecha_inicio, fecha_fin, force=force)

        return {
            "success": True,
            "mensaje": f"Reprocesamiento completado para el periodo {fecha_inicio} a {fecha_fin}",
            "stats": stats
        }
    except Exception as e:
        from loguru import logger
        logger.error(f"Error en reprocesamiento de empleado: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# [FASE 2 OPT] Endpoint de progreso del reproceso en background
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/reproceso/status/",
    summary="Estado del reproceso histórico en background",
    description=(
        "Devuelve el estado actual del reproceso masivo asíncrono. "
        "El frontend puede hacer polling cada 3s para mostrar progreso. "
        "Cuando `en_curso=false` y `error=null` el reproceso terminó exitosamente."
    )
)
async def get_reproceso_status(
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Estado del reproceso histórico que corre en background tras asignar un turno.

    Campos de respuesta:
    - `en_curso`: bool — True mientras el reproceso está activo
    - `progreso`: str | null — Descripción del chunk actual ("Chunk 3/16 ...")
    - `inicio`: str | null — ISO timestamp de inicio
    - `chunks_completados`: int — Chunks procesados hasta ahora
    - `chunks_totales`: int — Total de chunks del período
    - `pct`: int — Porcentaje 0–100
    - `error`: str | null — Mensaje de error si falló
    """
    from backend.services.asistencia_service import get_reproceso_status as _get_status
    status = _get_status()

    # Calcular porcentaje
    ct = status.get("chunks_totales", 0)
    cc = status.get("chunks_completados", 0)
    pct = int((cc / ct) * 100) if ct > 0 else (100 if not status.get("en_curso") else 0)

    return {**status, "pct": pct}


class ReprocesarPeriodoRequest(BaseModel):
    empleado_id: int
    fecha_inicio: str
    fecha_fin: str

@router.post("/reprocesar-periodo-empleado/")
async def post_reprocesar_periodo_empleado(
    req: ReprocesarPeriodoRequest,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """Reprocesa el período completo de un empleado persistiendo los resultados en DB."""
    stats = await service.reprocesar_periodo_empleado(
        empleado_id=req.empleado_id,
        fecha_inicio=req.fecha_inicio,
        fecha_fin=req.fecha_fin,
        force=True
    )
    return {"success": True, "stats": stats}


@router.post("/reasignar-turno/")
async def reasignar_turno_endpoint(
    req: ReasignarTurnoRequest,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """Reasigna el paquete completo de marcaciones de fecha_origen a fecha_destino."""
    db = service.repository.db
    emp_repo = EmpleadoRepository(db)
    emp = await emp_repo.get_by_id(req.empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    current_user.verificar_acceso_area(emp.area, "este empleado")

    # Exclusión Bolsa Flexible
    t_row = await TurnoRepository(db).get_tipo_programacion_ultima_asignacion(req.empleado_id)
    if t_row and t_row.get('tipo_programacion') == 'BOLSA_FLEXIBLE':
        raise HTTPException(status_code=400, detail="La reasignación de turno no está permitida para trabajadores en Bolsa Flexible.")

    # Cierre check
    f_min = min(req.fecha_origen, req.fecha_destino)
    f_max = max(req.fecha_origen, req.fecha_destino)
    if await service.repository.check_rango_cerrado(f_min, f_max, req.empleado_id):
        if not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Las fechas seleccionadas pertenecen a un período sellado por RRHH. Requiere perfil SuperAdmin.")

    try:
        res = await service.reasignar_bloque_turno(
            empleado_id=req.empleado_id,
            fecha_origen=req.fecha_origen,
            fecha_destino=req.fecha_destino,
            motivo=req.motivo
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error reasignando turno: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno reasignando turno: {str(e)}")

    # Registrar auditoría DT
    try:
        await SeguridadRepository(db).log_auditoria(
            current_user.user_id,
            current_user.username,
            'REASIGNAR_TURNO',
            'Marcaciones',
            f"Reasignación de turno Emp {req.empleado_id}: Mapeado bloque de {req.fecha_origen} a {req.fecha_destino}. Motivo: {req.motivo}"
        )
    except Exception as ae:
        logger.warning(f"Error registrando auditoría reasignación: {ae}")

    return {
        "success": True,
        "message": f"Turno reasignado exitosamente del {req.fecha_origen} al {req.fecha_destino}.",
        "data": res
    }
