"""
Router - Asistencia
Endpoints para procesar y consultar asistencia
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Body, BackgroundTasks
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger

from backend.services.asistencia_service import AsistenciaService
from backend.services.bono_service import BonoService
from backend.services.empleado_service import EmpleadoService
from backend.services.turno_service import TurnoService
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.empleado import EmpleadoRepository
from backend.repositories.turno import TurnoRepository
from backend.core.database import Database, get_db
from backend.core.security import SecurityContext, RequirePermission, RequireAnyPermission
from backend.schemas.asistencia import (
    AsistenciaMatrizResponse,
    RecalcularRequest,
    AprobarHERequest,
    JustificacionCreate,
    AsignacionIndividual,
    BatchSyncRequest,
    CondonarDeudaRequest,
    IntercambioCreate,
    CompensacionCreate,
)

router = APIRouter(
    prefix="/asistencia",
    tags=["Asistencia"]
)

async def get_asistencia_service(db: Database = Depends(get_db)) -> AsistenciaService:
    repository = AsistenciaRepository(db)
    return AsistenciaService(repository)

async def get_bono_service(db: Database = Depends(get_db)) -> BonoService:
    return BonoService(db)

async def get_empleado_service(db: Database = Depends(get_db)) -> EmpleadoService:
    repository = EmpleadoRepository(db)
    return EmpleadoService(repository)

async def get_turno_service(db: Database = Depends(get_db)) -> TurnoService:
    repository = TurnoRepository(db)
    return TurnoService(repository)

@router.get("/auditoria-bloqueo/")
async def get_auditoria_bloqueo(
    fecha: Optional[str] = Query(None, description="AAAA-MM-DD (Default hoy)"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Endpoint CRÍTICO (Plan Maestro): Detecta empleados con marcas (logs_raw) 
    pero sin turno asignado (asignacion_turnos) para el área del usuario actual.
    Utiliza historial_areas (es_actual=1) para una validación dinámica.
    """
    # Ventana de Auditoría: Desde el 1 del mes actual hasta hoy (Propuesta v29 Refinada)
    # Esto asegura que cualquier marca huérfana en el mes bloquee la operación.
    now = datetime.now()
    if not fecha:
        fecha = now.strftime("%Y-%m-%d")
        
    # Calcular el primer día del mes de la 'fecha' solicitada
    try:
        dt_solicitada = datetime.strptime(fecha, "%Y-%m-%d")
        fecha_inicio_mes = dt_solicitada.replace(day=1).strftime("%Y-%m-%d")
    except Exception:
        fecha_inicio_mes = now.replace(day=1).strftime("%Y-%m-%d")

    areas_permitidas = current_user.get_areas_filter()

    # Si no tiene áreas asignadas y no tiene acceso global, no tiene nada que auditar
    if areas_permitidas is not None and not areas_permitidas:
        return {"bloqueo": False, "anomalias": [], "can_bypass": False}

    area_filter = ""
    if areas_permitidas:
        placeholders = ",".join("?" for _ in areas_permitidas)
        area_filter = f"AND a_table.nombre IN ({placeholders})"

    # Bloqueo solo por ausencia de turno asignado, no por marcaciones.
    # Regla: Si tienes turno asignado -> apareces en la grilla. Las marcaciones no determinan acceso.
    # Las marcaciones antes del turno no pueden existir (regla de negocio: se sincronizan desde la
    # fecha de asignacion de turno). Solo se bloquea si el empleado activo carece de turno vigente,
    # o si tiene marcas biometricas sin ningun turno registrado en el sistema (incorporacion anomala).
    query = f"""
        WITH anomalias AS (
            -- CRITICA (v6): Empleado con marcas fisicas Y sin ningun turno en el sistema
            -- (situacion imposible segun regla de negocio, pero auditable)
            SELECT 
                e.id, 
                e.rut, 
                e.nombre, 
                e.apellido_paterno, 
                e.apellido_materno,
                e.cargo,
                a_table.nombre as area, 
                MIN(DATE(l.fecha_hora)) as fecha,
                'CRITICA' as tipo_anomalia
            FROM logs_raw l
            JOIN empleados e ON l.empleado_id = e.id
            JOIN historial_areas h ON e.id = h.empleado_id
            LEFT JOIN areas a_table ON h.area_id = a_table.id
            WHERE h.es_actual = 1 AND e.activo = 1
              {area_filter}
              AND l.fecha_hora >= ? AND l.fecha_hora <= ?
              AND e.id NOT IN (
                  SELECT empleado_id FROM asignacion_turnos
                  WHERE fecha_fin IS NULL OR fecha_fin >= ?
              )
            GROUP BY e.id, e.rut, e.nombre, e.apellido_paterno, e.apellido_materno, e.cargo, a_table.nombre

            UNION ALL

            -- PREVENTIVA: Empleado activo sin turno vigente Y con marcaciones reales en DB.
            -- FIX BATCH ONBOARDING: Se excluyen empleados sin marcaciones para evitar
            -- falsos positivos cuando emp2/emp3 están en proceso de onboarding batch
            -- y aún no han recibido su turno ni tienen marcaciones descargadas.
            SELECT 
                e.id, 
                e.rut, 
                e.nombre, 
                e.apellido_paterno, 
                e.apellido_materno,
                e.cargo,
                a_table.nombre as area, 
                '{fecha_inicio_mes}' as fecha,
                'PREVENTIVA' as tipo_anomalia
            FROM empleados e
            JOIN historial_areas h ON e.id = h.empleado_id
            LEFT JOIN areas a_table ON h.area_id = a_table.id
            WHERE h.es_actual = 1 AND e.activo = 1
              {area_filter}
              AND e.id NOT IN (
                  SELECT empleado_id FROM asignacion_turnos 
                  WHERE (fecha_fin IS NULL OR fecha_fin >= ?)
              )
              AND EXISTS (
                  -- Solo bloquear si el empleado ya tiene marcaciones en el sistema
                  SELECT 1 FROM logs_raw lr
                  WHERE lr.empleado_id = e.id
                    AND lr.fecha_hora >= ? AND lr.fecha_hora <= ?
              )
        )
        SELECT 
            id, rut, nombre, apellido_paterno, apellido_materno, cargo, area,
            MIN(fecha) as fecha,
            MIN(tipo_anomalia) as tipo_anomalia
        FROM anomalias
        GROUP BY id, rut, nombre, apellido_paterno, apellido_materno, cargo, area
        ORDER BY MIN(fecha) ASC, apellido_paterno ASC, apellido_materno ASC, nombre ASC
    """
    
    # Consolidación de parámetros para las 2 sub-queries (CRÍTICA y PREVENTIVA)
    # Query CRITICA: areas + fecha_inicio_mes + fecha + fecha (NOT IN vigente)
    # Query PREVENTIVA: areas + fecha (NOT IN vigente) + fecha_inicio_mes + fecha (EXISTS marcaciones)
    final_params = []
    # Parámetros Query CRITICA (Marcas sin turno en absoluto)
    if areas_permitidas:
        final_params.extend(areas_permitidas)
    final_params.extend([f"{fecha_inicio_mes} 00:00:00", f"{fecha} 23:59:59", fecha])
    
    # Parámetros Query PREVENTIVA (Activos sin turno vigente Y con marcaciones reales)
    if areas_permitidas:
        final_params.extend(areas_permitidas)
    final_params.extend([fecha, f"{fecha_inicio_mes} 00:00:00", f"{fecha} 23:59:59"])

    anomalias = await db.fetch_all(query, final_params)
    
    can_bypass = bool(current_user.alcance_global or current_user.is_superuser)
    logger.info(f"🛡️ Auditoría Bloqueo: {current_user.username} | Bloqueo: {len(anomalias) > 0} | can_bypass: {can_bypass}")
    
    return {
        "bloqueo": len(anomalias) > 0,
        "anomalias": anomalias,
        "count": len(anomalias),
        "fecha_auditada": fecha,
        "desde": fecha_inicio_mes,
        "can_bypass": can_bypass
    }

# ── Caché en memoria de Excels mensuales de BioAlba (nivel módulo) ──────────────
# Clave: (mes: int, anio: int)  →  Valor: list[dict] con todas las marcaciones del mes
# Se reutiliza entre llamadas del mismo proceso: cuando se procesa un área completa,
# cada Excel mensual se descarga UNA sola vez y sirve para todos los empleados.
# TTLCache: expira entradas después de 1h y limita a 15 meses en RAM.
# Un dict plano crecía indefinidamente; con TTLCache se acota el uso de memoria.
from cachetools import TTLCache
_bioalba_mes_cache: TTLCache = TTLCache(maxsize=15, ttl=3600)


@router.get("/empleados/{empleado_id}/primera-marcacion/")
async def get_primera_marcacion_empleado(
    empleado_id: int,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    RFC Paso 7: Busca en BioAlba la primera marcación biométrica del empleado.

    Optimizaciones:
    1. Escanea de FECHA_LIMITE (ene 2026) → hoy: la 1ª coincidencia es la 1ª marca → para al instante.
    2. Caché de Excels mensuales: en sync de área completa, cada mes se descarga solo 1 vez.

    logs_raw está vacío por el BioAlba Gate (descarta marcaciones sin turno asignado).
    """
    from datetime import date as date_type
    from backend.scraper.bioalba_scraper import BioAlbaScraper

    emp_row = await db.fetch_one("SELECT rut FROM empleados WHERE id = ?", [empleado_id])
    if not emp_row:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")

    rut_empleado = emp_row["rut"]

    # ── ÚNICO VALOR HARDCODEADO PERMITIDO EN LA APLICACIÓN ──────────────
    FECHA_LIMITE = date_type(2026, 1, 1)
    # ─────────────────────────────────────────────────────────────────────

    hoy = date_type.today()

    # Construir lista de meses desde el más antiguo al más reciente
    # → la primera coincidencia ES la primera marca, paramos de inmediato
    meses = []
    m, a = FECHA_LIMITE.month, FECHA_LIMITE.year
    while date_type(a, m, 1) <= hoy:
        meses.append((m, a))
        m += 1
        if m > 12:
            m = 1
            a += 1

    primera_fecha = None

    try:
        from backend.services.sync_service import _shared_scraper as scraper
        async with scraper:
            if not await scraper.ensure_logged_in():
                return {"empleado_id": empleado_id, "primera_marcacion": None,
                        "motivo": "No se pudo conectar a BioAlba"}

            for (mes_i, anio_i) in meses:
                clave = (mes_i, anio_i)

                # ── Caché: si ya se descargó este mes en esta sesión, reutilizar ──
                if clave not in _bioalba_mes_cache:
                    _bioalba_mes_cache[clave] = await scraper.get_marcaciones(
                        mes=mes_i, anio=anio_i
                    )
                marcaciones = _bioalba_mes_cache[clave]
                # ──────────────────────────────────────────────────────────────────

                fechas_emp = [
                    m["fecha_hora"][:10]
                    for m in marcaciones
                    if m.get("rut") == rut_empleado and m.get("fecha_hora")
                ]

                if fechas_emp:
                    # Escaneando de antiguo → nuevo: primera coincidencia = primera marca
                    primera_fecha = min(fechas_emp)
                    break  # ← no necesitamos seguir buscando

    except Exception as e:
        logger.error(f"Error buscando primera marcación BioAlba empleado {empleado_id}: {e}")
        return {"empleado_id": empleado_id, "primera_marcacion": None,
                "motivo": f"Error consultando BioAlba: {str(e)}"}

    return {"empleado_id": empleado_id, "primera_marcacion": primera_fecha}


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
        db = service.repository.db

        # 1. Insertar asignación de turno (operación rápida)
        await db.execute(
            "INSERT INTO asignacion_turnos (empleado_id, turno_id, fecha_inicio, fecha_fin) VALUES (?, ?, ?, NULL)",
            (data.empleado_id, data.turno_id, data.fecha)
        )
        logger.info(f"✅ Turno {data.turno_id} asignado a empleado {data.empleado_id} desde {data.fecha}")

        # 2. Obtener RUT del empleado para el sync individual
        emp_row = await db.fetch_one("SELECT rut FROM empleados WHERE id = ?", (data.empleado_id,))
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
    db = service.repository.db

    # ── 1. Recopilar RUTs para todos los empleados ────────────────────────
    # ── Fix #1: 1 sola query para todos los empleados en vez de N individuales ─
    ids_empleados = [item.empleado_id for item in data.items]
    placeholders = ",".join("?" * len(ids_empleados))
    emp_rows = await db.fetch_all(
        f"SELECT id, rut, nombre, apellido_paterno FROM empleados WHERE id IN ({placeholders})",
        ids_empleados
    )
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

            # ── Pausar el scheduler sync_from_cloud durante el batch ────────
            # El scheduler comparte _db_lock con execute_batch → timeouts.
            # Seteamos una flag para que sync_from_cloud se salte su turno.
            _db._batch_in_progress = True
            logger.info(f"[Batch {batch_job_id}] Scheduler sync pausado durante el batch")

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
                        await service.he_repo.batch_upsert(all_he_to_save, suppress_auto_sync=True)
                    if all_he_to_delete:
                        for eid_del, f_str in all_he_to_delete:
                            await service.he_repo.delete_by_empleado_fecha(eid_del, f_str)
                            
                    # 3. Guardar y eliminar jornadas especiales
                    if all_je_to_save:
                        for je_rec in all_je_to_save:
                            await service.repository.upsert_jornada_especial(je_rec)
                    if all_je_to_delete:
                        for eid_del, f_str in all_je_to_delete:
                            await service.repository.db.execute("DELETE FROM jornadas_especiales WHERE empleado_id = ? AND fecha = ?", (eid_del, f_str))
                            
                    elapsed_save = int((_time_mod.time() - t_save) * 1000)
                    logger.info(
                        f"[⚡ Batch] WAL local: guardado completado en {elapsed_save}ms"
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

            # ── FASE FINAL: 1 ÚNICO sync a Turso Cloud ──────────────────────────
            # Empuja TODO el WAL acumulado de una sola vez:
            #   - marcaciones Mes 1 + Mes 2 + ... + asistencia calculada (Fase B)
            # Se ejecuta DESPUÉS de que toda la escritura local está completa.
            # Ahorro vs diseño anterior: N-1 syncs intermedios eliminados.
            for jid in job_ids.values():
                _update_job(jid, phase_label="Sincronizando con Turso Cloud...", pct=97)
            try:
                import time as _time_mod
                t_sync = _time_mod.time()
                logger.info(f"☁️ [Batch] Iniciando sync final único a Turso Cloud...")
                await _db.sync_to_cloud_explicit()
                elapsed_sync = int((_time_mod.time() - t_sync) * 1000)
                logger.info(
                    f"☁️ [Batch] Sync final completado en {elapsed_sync}ms "
                    f"({len(all_results_to_save)} asistencia + marcaciones acumuladas → Turso Cloud)"
                )
            except Exception as sync_err:
                logger.error(f"❌ [Batch] Error en sync final a cloud: {sync_err}. Datos seguros en WAL local.")

            # Marcar todos los jobs como completados
            for jid in job_ids.values():
                _update_job(jid, status="done", pct=100, phase_label="Completado")

        except Exception as bg_err:
            logger.error(f"❌ [Batch {batch_job_id}] Error global: {bg_err}")
            for jid in job_ids.values():
                _update_job(jid, status="error", error=str(bg_err))
        finally:
            _db._batch_in_progress = False
            logger.info(f"[Batch {batch_job_id}] Scheduler sync restaurado")

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

    try:
        # 1. Marcar condonacion en la BD en un solo batch (N+1 optimization)
        query = "UPDATE asistencias SET deuda_condonada = ?, updated_at = datetime('now') WHERE empleado_id = ? AND fecha = ?"
        params = [(request.tipo_condonacion, emp_id, fecha_str) for emp_id in request.empleados_ids for fecha_str in fechas]
        await service.repository.db.executemany(query, params)

        # 2. Reprocesar los días de los empleados en bulk usando procesar_dia
        for fecha_str in fechas:
            await service.procesar_dia(
                fecha=fecha_str,
                force=True,
                empleado_ids=set(request.empleados_ids),
                suppress_sync=True
            )
        
        # 3. Forzar sincronización final una sola vez para toda la operación
        await service.repository.db.sync_to_cloud_explicit()

        accion = "condonada" if request.tipo_condonacion > 0 else "revocada"
        return {"success": True, "message": f"Deuda {accion} correctamente para {len(request.empleados_ids)} empleado(s) en {dias_totales} día(s)."}
    except Exception as e:
        logger.error(f"Error al condonar deuda: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

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
        db = service.repository.db
        q_closed = """
            SELECT id FROM cierres_periodos
            WHERE area = ? AND fecha_inicio <= ? AND fecha_fin >= ?
        """
        closed = await db.fetch_one(q_closed, (area_final, fecha_inicio, fecha_fin))
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


# ── Change-detection para auto-refresh de la grilla ──────────────────────────
# Endpoint ultra-liviano: solo MAX(updated_at) + COUNT(*) para el período.
# El frontend lo pollea cada 30s y si detecta un cambio, recarga la grilla.
# TTLCache multi-clave: 5 usuarios mirando áreas distintas NO se invalidan entre sí.
# Max 20 claves (período+área), TTL 10s → máximo 1 query real cada 10s por combinación.
_change_cache: TTLCache = TTLCache(maxsize=20, ttl=10)

@router.get("/last-change/", summary="Detectar cambios recientes en asistencias")
async def get_last_change(
    fecha_inicio: str = Query(..., description="AAAA-MM-DD"),
    fecha_fin: str = Query(..., description="AAAA-MM-DD"),
    area: Optional[str] = Query(None),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Endpoint de change-detection para auto-refresh inteligente.
    Retorna el timestamp de la última modificación y el conteo de registros.
    El frontend compara estos valores con los anteriores: si cambian, recarga.
    TTLCache multi-clave (10s) para multi-usuario.
    """
    cache_key = f"{fecha_inicio}|{fecha_fin}|{area or 'ALL'}"

    # Cache hit (TTLCache maneja expiración automáticamente)
    if cache_key in _change_cache:
        return _change_cache[cache_key]

    # Build query with optional area filter
    area_filter = ""
    params: list = [fecha_inicio, fecha_fin]
    if area:
        area_filter = """
            AND a.empleado_id IN (
                SELECT ha.empleado_id FROM historial_areas ha
                JOIN areas ar ON ar.id = ha.area_id
                WHERE ha.es_actual = 1 AND ar.nombre = ?
            )
        """
        params.append(area)

    # RLS: filter by user's allowed areas
    areas_permitidas = current_user.get_areas_filter()
    rls_filter = ""
    if areas_permitidas:
        placeholders = ",".join("?" for _ in areas_permitidas)
        rls_filter = f"""
            AND a.empleado_id IN (
                SELECT ha2.empleado_id FROM historial_areas ha2
                JOIN areas ar2 ON ar2.id = ha2.area_id
                WHERE ha2.es_actual = 1 AND ar2.nombre IN ({placeholders})
            )
        """
        params.extend(areas_permitidas)

    row = await db.fetch_one(f"""
        SELECT
            MAX(a.updated_at) as last_update,
            COUNT(*) as total_records
        FROM asistencias a
        WHERE a.fecha BETWEEN ? AND ?
        {area_filter}
        {rls_filter}
    """, params)

    result = {
        "last_update": row["last_update"] if row else None,
        "total_records": row["total_records"] if row else 0,
        "cache_key": cache_key,
    }

    _change_cache[cache_key] = result
    return result


@router.get("/reporte/")
async def get_reporte_asistencia(
    fecha_inicio: str = Query(..., description="AAAA-MM-DD"),
    fecha_fin: str = Query(..., description="AAAA-MM-DD"),
    area: Optional[str] = Query(None),
    turno_id: Optional[int] = Query(None),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene la asistencia procesada con RLS.
    """
    if area:
        current_user.verificar_acceso_area(area, "el área solicitada")
    areas_permitidas = current_user.get_areas_filter()

    return await service.repository.get_asistencias_periodo(
        fecha_inicio, fecha_fin, area, turno_id=turno_id, areas_permitidas=areas_permitidas
    )

@router.get("/stats/")
async def get_asistencia_stats(
    fecha: Optional[str] = Query(None, description="AAAA-MM-DD"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene estadísticas de asistencia diarias filtradas por RLS.
    """
    if not fecha:
        fecha = datetime.now().strftime("%Y-%m-%d")
        
    areas_permitidas = current_user.get_areas_filter()
    return await service.get_daily_stats(fecha, areas_permitidas=areas_permitidas)

@router.get("/matrix/")
async def get_asistencia_matrix(
    mes: int = Query(..., ge=1, le=12),
    anio: int = Query(..., ge=2000, le=2100),
    area: Optional[str] = Query(None),
    turno_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    service: AsistenciaService = Depends(get_asistencia_service),
    bono_service: BonoService = Depends(get_bono_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene datos para la Vista Matriz (Equipo) con RLS.
    """
    if area:
        current_user.verificar_acceso_area(area, "el área solicitada")
    areas_permitidas = current_user.get_areas_filter()

    data = await service.get_matrix_data_with_projections(mes, anio, area, turno_id, search=search, areas_permitidas=areas_permitidas)

    # Siempre incluir la lista maestra de todos los bonos activos (columnas estáticas)
    todos_bonos = await bono_service.config_repo.get_all_bonos()
    data["bonos_nombres"] = sorted([b["nombre"] for b in todos_bonos if b.get("activo")])

    # Evaluar cumplimiento de bonos para los empleados del período
    empleados = data.get("empleados", [])
    if empleados:
        asistencias = data.get("data", [])
        justificaciones = data.get("justificaciones", [])
        matrix_data = data.get("matrix", {})
        bonos_eval = await bono_service.evaluar_bonos_directo(
            empleados, asistencias, justificaciones, matrix_data, mes, anio
        )
        data["bonos_evaluacion"] = bonos_eval

    return data



@router.get("/matriz/")
async def get_matriz_asistencia(
    fecha_inicio: str = Query(..., description="AAAA-MM-DD"),
    fecha_fin: str = Query(..., description="AAAA-MM-DD"),
    area: Optional[str] = Query(None),
    turno_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    empleado_id: Optional[int] = Query(None),
    service: AsistenciaService = Depends(get_asistencia_service),
    bono_service: BonoService = Depends(get_bono_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Retorna la matriz de asistencia (días x empleados) para un periodo y área.
    Implementa RLS para limitar visualización según áreas permitidas.
    """
    # RLS: verificar acceso al área solicitada y calcular filtro
    if area:
        current_user.verificar_acceso_area(area, "el área solicitada")
    areas_permitidas = current_user.get_areas_filter()
    area_filter = area

    # Guard: si llegan fechas vacías (carga inicial sin selector configurado), usar mes actual
    if not fecha_inicio or not fecha_fin:
        from datetime import datetime as _dt_now
        import calendar as _cal
        hoy = _dt_now.today()
        fecha_inicio = hoy.replace(day=1).strftime("%Y-%m-%d")
        last_day = _cal.monthrange(hoy.year, hoy.month)[1]
        fecha_fin = hoy.replace(day=last_day).strftime("%Y-%m-%d")

    data = await service.get_matriz_periodo(fecha_inicio, fecha_fin, area_filter, turno_id, search, areas_permitidas=areas_permitidas, empleado_id=empleado_id)
    
    # Siempre incluir la lista maestra de todos los bonos activos (columnas estáticas)
    todos_bonos = await bono_service.config_repo.get_all_bonos()
    data["bonos_nombres"] = sorted([b["nombre"] for b in todos_bonos if b.get("activo")])

    # Evaluar cumplimiento de bonos para los empleados del período
    if "empleados" in data and data["empleados"]:
        empleados = data["empleados"]
        asistencias = data.get("data", [])
        justificaciones = data.get("justificaciones", [])
        matrix_data = data.get("matrix", {})
        
        mes_eval = None
        anio_eval = None
        if fecha_inicio:
            try:
                from datetime import datetime as _dt
                dt_start = _dt.strptime(fecha_inicio, "%Y-%m-%d")
                mes_eval = dt_start.month
                anio_eval = dt_start.year
            except Exception:
                pass

        bonos_eval = await bono_service.evaluar_bonos_directo(
            empleados, asistencias, justificaciones, matrix_data, mes_eval, anio_eval
        )
        data["bonos_evaluacion"] = bonos_eval

    return data


@router.get("/calendar/")
async def get_asistencia_calendar(
    empleado_id: int = Query(...),
    mes: Optional[int] = Query(None, ge=1, le=12),
    anio: Optional[int] = Query(None, ge=2000, le=2100),
    fecha_inicio: Optional[str] = Query(None),
    fecha_fin: Optional[str] = Query(None),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene datos para la Vista Calendario (Personal) con RLS.
    Retorna asistencias de todo el mes o periodo para un empleado específico,
    incluyendo proyecciones de feriados y justificaciones.
    """
    if not ((mes and anio) or (fecha_inicio and fecha_fin)):
        raise HTTPException(status_code=400, detail="Debe proveer mes y anio, o fecha_inicio y fecha_fin")

    # RLS: Verificar pertenencia
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    current_user.verificar_acceso_area(emp.area, "el calendario de este empleado")
    # Usar la lógica de matriz enriquecida con proyecciones
    rich_data = await service.get_matrix_data_with_projections(
        mes=mes or 1, 
        anio=anio or 2026, 
        empleado_id=empleado_id,
        fecha_inicio_override=fecha_inicio,
        fecha_fin_override=fecha_fin
    )
    
    # Extraer los días del único empleado en una lista plana para el calendario
    flat_data = []
    matrix = rich_data.get("matrix", {})
    
    # El empleado_id es la clave principal en rich_data["matrix"]
    emp_matrix = matrix.get(str(empleado_id), {}) or matrix.get(empleado_id, {})
    
    # Extraer fechas (excluyendo 'info')
    for key, val in emp_matrix.items():
        if key != 'info':
            flat_data.append(val)
            
    # Ordenar por fecha
    flat_data.sort(key=lambda x: x.get('fecha', ''))
    
    return {
        "success": True,
        "data": flat_data,
        "feriados": rich_data.get("feriados", []),
        "periodo": rich_data.get("periodo"),
        "info": emp_matrix.get('info', {}),  # <-- CRÍTICO: Inyección de la Meta con descuentos legales
        "empleado_info": {
            "rut": emp.rut,
            "nombre": emp.nombre,
            "apellido_paterno": emp.apellido_paterno,
            "apellido_materno": emp.apellido_materno,
            "area": emp.area,
            "cargo": emp.cargo
        }
    }

@router.get("/filters-data/")
async def get_filters_data(
    area: Optional[str] = Query(None),
    turno_id: Optional[int] = Query(None),
    mes: Optional[int] = Query(None),
    anio: Optional[int] = Query(None),
    emp_service: EmpleadoService = Depends(get_empleado_service),
    turno_service: TurnoService = Depends(get_turno_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Endpoint consolidado para obtener empleados y turnos para los filtros con RLS.
    Soporta cascada 4 niveles: Mes/Año → Área → Horario → Empleado.
    Optimiza la performance al reducir el número de peticiones.
    """
    # RLS: Si pide un área, verificarla. Si no pide, filtrar por sus permitidas.
    if area:
        current_user.verificar_acceso_area(area, "el área solicitada")
    areas_permitidas = current_user.get_areas_filter()
    
    # 1. Obtener turnos del área (sin detalles de días para velocidad)
    turnos = await turno_service.get_all_turnos(area=area, include_details=False, areas_permitidas=areas_permitidas)
    
    # 2. Obtener empleados — si turno_id está activo, filtrar solo los asignados a ese turno
    if turno_id:
        # Cascade: solo empleados con asignación activa a ese turno
        db = emp_service.repository.db
        extra_cond = ""
        params_emp: list = [turno_id]
        if area:
            extra_cond += " AND a.nombre = ?"
            params_emp.append(area)
        if areas_permitidas:
            ph = ",".join("?" * len(areas_permitidas))
            extra_cond += f" AND a.nombre IN ({ph})"
            params_emp.extend(areas_permitidas)
        emp_rows = await db.fetch_all(f"""
            SELECT DISTINCT e.id,
                   (e.apellido_paterno || ' ' || COALESCE(NULLIF(e.apellido_materno,''),'') || ' ' || e.nombre) as nombre_completo,
                   e.rut, a.nombre as area, e.activo
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a ON ha.area_id = a.id
            INNER JOIN asignacion_turnos ast ON e.id = ast.empleado_id
            WHERE e.activo = 1
              AND ast.turno_id = ?
              AND (ast.fecha_fin IS NULL OR ast.fecha_fin >= date('now'))
              {extra_cond}
            ORDER BY e.apellido_paterno ASC, e.apellido_materno ASC, e.nombre ASC
        """, tuple(params_emp))
        empleados = [dict(r) for r in emp_rows]
    else:
        empleados = await emp_service.get_lookup(area=area, activo=True, areas_permitidas=areas_permitidas)
    
    return {
        "empleados": empleados,
        "turnos": turnos
    }

@router.get("/empleados/sin-turno-activos/")
async def get_empleados_sin_turno_activos(
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene empleados activos sin turno asignado (Filtrado por RLS).
    Útil para mostrar alertas en UI.
    """
    areas_permitidas = current_user.get_areas_filter()
    
    area_filter = ""
    params = []
    if areas_permitidas:
        placeholders = ",".join("?" for _ in areas_permitidas)
        area_filter = f" AND a.nombre IN ({placeholders})"
        params = areas_permitidas
    query = f"""
        SELECT e.id, e.nombre, e.apellido_paterno, e.apellido_materno, a.nombre as area
        FROM empleados e
        LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
        LEFT JOIN areas a ON ha.area_id = a.id
        WHERE e.activo = 1
          {area_filter}
          AND e.id NOT IN (
              SELECT DISTINCT empleado_id 
              FROM asignacion_turnos 
              WHERE fecha_fin IS NULL OR fecha_fin >= date('now')
          )
        ORDER BY e.apellido_paterno, e.apellido_materno, e.nombre
    """
    db = service.repository.db
    empleados = await db.fetch_all(query, params)
    return empleados


@router.get("/diagnostic/no-shift/")
async def diagnostic_no_shift(
    area: str,
    mes: int,
    anio: int,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Diagnóstico: Cuenta cuántos empleados pertenecieron a un área en un mes 
    pero no tienen turno asignado en ese periodo.
    """
    # RLS
    current_user.verificar_acceso_area(area, "esta área")

    import calendar
    last_day = calendar.monthrange(anio, mes)[1]
    fecha_inicio = f"{anio}-{mes:02d}-01"
    fecha_fin = f"{anio}-{mes:02d}-{last_day}"

    query = """
        SELECT COUNT(DISTINCT e.id) as count
        FROM empleados e
        JOIN historial_areas h ON e.id = h.empleado_id
        WHERE h.area = ?
          AND h.fecha_desde <= ?
          AND (h.fecha_hasta IS NULL OR h.fecha_hasta >= ?)
          AND h.validado = 1
          AND e.id NOT IN (
              SELECT DISTINCT empleado_id 
              FROM asignacion_turnos 
              WHERE (fecha_inicio <= ?) AND (fecha_fin IS NULL OR fecha_fin >= ?)
          )
    """
    db = service.repository.db
    res = await db.fetch_one(query, (area, fecha_fin, fecha_inicio, fecha_fin, fecha_inicio))
    return {"count": res["count"] if res else 0}

@router.post("/jornada/validar/")
async def validar_jornada_endpoint(
    empleado_id: int = Body(...),
    fecha: str = Body(...),
    accion: str = Body("APROBAR"),
    last_updated_at: Optional[str] = Body(None, description="Fecha/Hora de la versión que el usuario está viendo"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Gestiona una jornada especial (APROBAR o RECHAZAR) con RLS.
    """
    # RLS: Verificar pertenencia
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    current_user.verificar_acceso_area(emp.area, "jornadas de este empleado")
    
    # Blindaje de Cierre
    if await service.repository.check_fecha_cerrada(fecha, empleado_id):
        raise HTTPException(status_code=403, detail="El periodo de esta fecha se encuentra cerrado y no admite modificaciones.")

    try:
        # Control de Concurrencia Optimista
        if last_updated_at:
            actual = await service.repository.get_asistencia(empleado_id, fecha)
            if actual and actual.get('updated_at') and actual.get('updated_at') != last_updated_at:
                raise HTTPException(
                    status_code=409, 
                    detail=f"Conflicto de Concurrencia: El registro fue modificado por otro usuario ({actual.get('updated_at')}). Por favor, refresque los datos."
                )

        resultado = await service.validar_jornada(empleado_id, fecha, accion)
        if isinstance(resultado, dict) and 'error' in resultado:
            raise HTTPException(status_code=400, detail=resultado['error'])
        mensaje = "Jornada validada exitosamente" if accion == "APROBAR" else "Jornada rechazada exitosamente"
        return {
            "success": True, 
            "mensaje": mensaje, 
            "asistencia": resultado
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/aprobar-he/")
async def aprobar_horas_extra(
    request: AprobarHERequest,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.horas_extras"))
):
    """
    Aprueba horas extras para un empleado y día (delegando al método batch).
    """
    # RLS: Verificar pertenencia de área
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(request.empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    current_user.verificar_acceso_area(emp.area, "HE de este empleado")

    try:
        # Convertir a formato de lote de un solo elemento
        items = [{
            "empleado_id": request.empleado_id,
            "fecha": request.fecha,
            "estado": "APROBADO" if request.horas > 0 else "RECHAZADO",
            "minutos_autorizados": request.horas * 60.0
        }]
        return await service.aprobar_horas_extras_batch(items)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/aprobar-he-batch/")
async def aprobar_horas_extra_batch(
    items: List[Dict[str, Any]] = Body(...),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.horas_extras"))
):
    """
    Aprueba o rechaza múltiples registros de horas extra a la vez (delegando al servicio).
    Cada item debe tener {empleado_id, fecha, estado, minutos_autorizados}.
    """
    try:
        # RLS: Validar pertenencia de área para cada elemento del lote antes de procesar
        emp_repo = EmpleadoRepository(service.repository.db)
        for item in items:
            emp_id = item.get('empleado_id')
            emp = await emp_repo.get_by_id(emp_id)
            if emp:
                current_user.verificar_acceso_area(emp.area, f"HE del empleado ID {emp_id}")

        return await service.aprobar_horas_extras_batch(items)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/marcaciones/manual/")
async def agregar_marcacion_manual(
    empleado_id: int,
    fecha: str,
    hora: str,
    tipo: str = Query(..., pattern="^(Entrada|Salida)$"),
    observaciones: Optional[str] = None,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Agrega una marcación manual y reprocesa la asistencia con RLS.
    """
    # RLS: Verificar pertenencia
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    current_user.verificar_acceso_area(emp.area, "este empleado")

    # Blindaje de Cierre
    if await service.repository.check_fecha_cerrada(fecha, empleado_id):
         raise HTTPException(status_code=403, detail="El periodo de esta fecha se encuentra cerrado y no admite modificaciones.")

    try:
        # 1. Insertar en logs_raw (con hash para respetar barrera anti-duplicados)
        import hashlib
        if hora.count(':') == 1:
            fecha_hora = f"{fecha} {hora}:00"
        else:
            fecha_hora = f"{fecha} {hora}"
            
        emp_data = await emp_repo.get_by_id(empleado_id)
        rut = emp_data.rut if emp_data else str(empleado_id)
        raw_string = f"{rut}|{fecha_hora}|{tipo or ''}"
        hash_val = hashlib.sha256(raw_string.encode()).hexdigest()

        query = """
            INSERT OR IGNORE INTO logs_raw (empleado_id, fecha_hora, tipo, manual, observaciones, hash_original)
            VALUES (?, ?, ?, 1, ?, ?)
        """
        db = service.repository.db
        await db.execute(query, (empleado_id, fecha_hora, tipo, observaciones or "Marcación manual", hash_val))
        
        # 2. Reprocesar asistencia del día
        resultado = await service.procesar_empleado_dia(empleado_id, fecha, save=True)
        
        return {
            "success": True,
            "mensaje": "Marcación manual agregada y asistencia reprocesada",
            "asistencia": resultado
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/marcaciones/manual/")
async def eliminar_jornada_especial_manual(
    empleado_id: int = Query(...),
    fecha: str = Query(...),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Elimina las marcaciones manuales de un día específico y recalcula la asistencia.
    """
    # RLS: Verificar pertenencia
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    current_user.verificar_acceso_area(emp.area, "este empleado")

    # Blindaje de Cierre
    if await service.repository.check_fecha_cerrada(fecha, empleado_id):
         raise HTTPException(status_code=403, detail="El periodo de esta fecha se encuentra cerrado y no admite modificaciones.")

    try:
        db = service.repository.db
        
        # Eliminar las marcaciones manuales de este día
        fecha_like = f"{fecha} %"
        query = """
            DELETE FROM logs_raw 
            WHERE empleado_id = ? AND manual = 1 AND fecha_hora LIKE ?
        """
        await db.execute(query, (empleado_id, fecha_like))
        
        # Reprocesar la asistencia del día
        resultado = await service.procesar_empleado_dia(empleado_id, fecha, save=True)
        
        return {
            "success": True,
            "mensaje": "Marcaciones manuales eliminadas y asistencia recalculada",
            "asistencia": resultado
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/periodo-rrhh/resumen/")
async def get_periodo_rrhh_resumen(
    empleado_id: int = Query(...),
    fecha_inicio: str = Query(...),
    fecha_fin: str = Query(...),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene el resumen de HE, Deuda y Saldo Meta para un empleado específico (Uso individual).
    """
    # RLS: Verificar que el empleado pertenece al área del usuario
    if not current_user.alcance_global:
        emp_repo = EmpleadoRepository(service.repository.db)
        emp = await emp_repo.get_by_id(empleado_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Empleado no encontrado")
        current_user.verificar_acceso_area(emp.area, "el resumen de este empleado")
    return await service.get_period_summary_rrhh(empleado_id, fecha_inicio, fecha_fin)

@router.get("/periodo-rrhh/resumen-global/")
async def get_periodo_rrhh_resumen_global(
    fecha_inicio: str = Query(...),
    fecha_fin: str = Query(...),
    area: Optional[str] = Query(None),
    turno_id: Optional[int] = Query(None),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene el resumen consolidado de todo el personal filtrado para el modal de cierre.
    """
    # RLS: Filtrar por áreas permitidas si no es global
    areas_permitidas = current_user.get_areas_filter()
    if area and areas_permitidas is not None and area not in areas_permitidas:
        raise HTTPException(status_code=403, detail="No tiene permisos para el área solicitada")
    
    # RLS: Si no es global y no especificó área, usar la primera área permitida
    area_final = area
    if not area_final and areas_permitidas:
        area_final = areas_permitidas[0] if len(areas_permitidas) == 1 else None
    return await service.get_resumen_cierre_global(fecha_inicio, fecha_fin, area_final, turno_id)

@router.get("/periodo-rrhh/ultimo-cierre/")
async def get_ultimo_cierre_rrhh(
    tipo: str = Query("RRHH"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene la información del último cierre registrado para sugerir el siguiente periodo.
    """
    # RLS: Filtrar por áreas permitidas del usuario
    cierre = await service.repository.get_ultimo_cierre_periodo(tipo)
    if cierre and not current_user.alcance_global:
        areas_permitidas = current_user.areas or []
        if cierre.get('area') and cierre['area'] not in areas_permitidas:
            return None
    return cierre

@router.get("/periodo-rrhh/historial/")
async def get_historial_cierres_rrhh(
    limit: int = Query(12),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene el historial de cierres de periodo.
    """
    # RLS: Filtrar por áreas permitidas del usuario
    cierres = await service.repository.get_cierres_historial(limit)
    if not current_user.alcance_global:
        areas_permitidas = current_user.areas or []
        cierres = [c for c in cierres if not c.get('area') or c['area'] in areas_permitidas]
    return cierres

@router.post("/periodo-rrhh/cerrar/")
async def cerrar_periodo_rrhh(
    fecha_inicio: str = Body(...),
    fecha_fin: str = Body(...),
    area: Optional[str] = Body(None),
    turno_id: Optional[int] = Body(None),
    comentario: Optional[str] = Body(None), # El frontend envía 'comentario'
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Registra el cierre y ejecuta el procesamiento masivo de saldos/bolsa.
    Permite segmentación por Área y Horario (turno_id).
    """
    # RLS: Verificar que el área enviada está en las áreas del current_user
    if area and not current_user.alcance_global:
        areas_permitidas = current_user.areas or []
        if area not in areas_permitidas:
            raise HTTPException(status_code=403, detail=f"No tiene permisos para cerrar el área '{area}'.")
    resultado = await service.ejecutar_cierre_periodo(
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        area=area,
        turno_id=turno_id,
        usuario_id=current_user.user_id,
        username=current_user.username,
        comentarios=comentario
    )
    return resultado

@router.post("/marcaciones/masivas/")
async def agregar_marcaciones_masivas(
    empleado_id: int = Body(...),
    fecha_inicio: str = Body(...),
    fecha_fin: str = Body(...),
    sobrescribir: bool = Body(False),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Relleno Masivo de Asistencia (Auto-Fill) con RLS.

    [AUDITORIA 2025 — OPT N+1] Refactorizado para eliminar N+1 queries.
    Antes:  N días × ~13 queries = 1,170 round-trips para 90 días (~23 min).
    Ahora:  ~8 queries pre-carga + 1 batch insert + 1 reproceso = ~20s para 90 días.

    Estrategia:
    1. Pre-cargar asignación vigente y todos los días de turno de una vez.
    2. Pre-cargar hashes de logs_raw existentes en el rango (para modo no-sobrescribir).
    3. Construir batch de inserts en memoria, ejecutar en 1 solo round-trip.
    4. Llamar reprocesar_periodo_empleado una vez para el período completo.
    """
    # ── RLS ───────────────────────────────────────────────────────────────────
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")

    current_user.verificar_acceso_area(emp.area, "este empleado")

    db = service.repository.db
    # ── Blindaje de Cierre ──
    q_areas = """
        SELECT DISTINCT a.nombre as area_nombre
        FROM historial_areas ha
        JOIN areas a ON ha.area_id = a.id
        WHERE ha.empleado_id = ? AND ha.validado = 1
          AND ha.fecha_desde <= ? AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR ha.fecha_hasta >= ?)
    """
    areas_rows = await db.fetch_all(q_areas, (empleado_id, fecha_fin, fecha_inicio))
    emp_areas = [r['area_nombre'] for r in areas_rows]
    
    if emp.area and emp.area not in emp_areas:
        emp_areas.append(emp.area)
        
    if emp_areas:
        placeholders = ",".join(["?"] * len(emp_areas))
        q_closure_check = f"""
            SELECT area, fecha_inicio, fecha_fin 
            FROM cierres_periodos
            WHERE area IN ({placeholders})
              AND fecha_inicio <= ?
              AND fecha_fin >= ?
            LIMIT 1
        """
        params = tuple(emp_areas) + (fecha_fin, fecha_inicio)
        closed_overlap = await db.fetch_one(q_closure_check, params)
        if closed_overlap:
            raise HTTPException(
                status_code=403, 
                detail=f"Operación denegada. El rango solicitado contiene días cerrados para el área '{closed_overlap['area']}' (Periodo cerrado: {closed_overlap['fecha_inicio']} a {closed_overlap['fecha_fin']})."
            )

    try:
        import hashlib
        start_date = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        end_date   = datetime.strptime(fecha_fin,   "%Y-%m-%d")

        # ── 1. Pre-carga: asignación de turno vigente en el período ──────────
        asigs = await db.fetch_all("""
            SELECT a.id as asig_id, a.turno_id, a.fecha_inicio as asig_desde,
                   a.fecha_fin as asig_hasta
            FROM asignacion_turnos a
            WHERE a.empleado_id = ?
              AND a.fecha_inicio <= ?
              AND (a.fecha_fin IS NULL OR a.fecha_fin >= ?)
            ORDER BY a.fecha_inicio DESC
        """, (empleado_id, fecha_fin, fecha_inicio))

        if not asigs:
            return {
                "success": True,
                "mensaje": "No hay turno asignado en el período. Ningún día procesado.",
                "dias_procesados": 0, "dias_ignorados": 0, "errores": []
            }

        # ── 2. Pre-carga: detalle de días de TODOS los turnos involucrados ───
        turno_ids = list({a["turno_id"] for a in asigs})
        ph = ",".join("?" for _ in turno_ids)
        dias_turno_rows = await db.fetch_all(
            f"SELECT * FROM turno_dias WHERE turno_id IN ({ph}) ORDER BY num_semana, dia_semana",
            tuple(turno_ids)
        )
        # Mapa: turno_id → {dia_semana → config_dia}
        dias_map: Dict[int, Dict[int, Any]] = {}
        for d in dias_turno_rows:
            dias_map.setdefault(d["turno_id"], {})[d["dia_semana"]] = d

        # ── 3. Pre-carga: hashes de logs_raw existentes en el rango ──────────
        # (para verificar si ya existe una marca sin hacer 1 query por día)
        existing_hashes: set = set()
        if not sobrescribir:
            fecha_like_start = fecha_inicio[:7]   # "YYYY-MM"
            fecha_like_end   = fecha_fin[:7]
            # Cargamos todos los logs_raw del empleado en el rango de meses
            logs_existentes = await db.fetch_all("""
                SELECT fecha_hora
                FROM logs_raw
                WHERE empleado_id = ?
                  AND fecha_hora >= ? AND fecha_hora <= ?
            """, (empleado_id, f"{fecha_inicio} 00:00:00", f"{fecha_fin} 23:59:59"))
            # Extraer solo las fechas (YYYY-MM-DD) que tienen log
            fechas_con_log: set = {row["fecha_hora"][:10] for row in logs_existentes}
        else:
            fechas_con_log = set()

        # ── 4. Detectar asignación vigente para cada día (en memoria) ─────────
        # Construir lookup: fecha → (turno_id, asig_id)
        def get_asig_para_fecha(fecha_str: str) -> Optional[Dict]:
            for a in asigs:
                desde = a["asig_desde"]
                hasta = a["asig_hasta"] or "2099-12-31"
                if desde <= fecha_str <= hasta:
                    return a
            return None

        # ── 5. Construir batch de inserts en memoria ───────────────────────────
        batch_logs: list = []
        dias_procesados = 0
        dias_ignorados  = 0
        errores: list   = []

        current = start_date
        while current <= end_date:
            fecha_str  = current.strftime("%Y-%m-%d")
            dia_semana = current.weekday()   # 0=Lunes

            asig = get_asig_para_fecha(fecha_str)
            if not asig:
                dias_ignorados += 1
                current += timedelta(days=1)
                continue

            config_dia = dias_map.get(asig["turno_id"], {}).get(dia_semana)
            if not config_dia or config_dia.get("es_libre"):
                dias_ignorados += 1
                current += timedelta(days=1)
                continue

            if not sobrescribir and fecha_str in fechas_con_log:
                dias_ignorados += 1
                current += timedelta(days=1)
                continue

            hora_entrada = config_dia.get("hora_entrada")
            hora_salida  = config_dia.get("hora_salida")
            if not hora_entrada or not hora_salida:
                dias_ignorados += 1
                current += timedelta(days=1)
                continue

            # Entrada
            fh_ent  = f"{fecha_str} {hora_entrada}:00"
            rut_str = str(emp.rut) if emp else str(empleado_id)
            h_ent   = hashlib.sha256(f"{rut_str}|{fh_ent}|Entrada".encode()).hexdigest()
            batch_logs.append((empleado_id, fh_ent, "Entrada", 1, "Relleno Masivo", h_ent))

            # Salida
            fh_sal = f"{fecha_str} {hora_salida}:00"
            h_sal  = hashlib.sha256(f"{rut_str}|{fh_sal}|Salida".encode()).hexdigest()
            batch_logs.append((empleado_id, fh_sal, "Salida", 1, "Relleno Masivo", h_sal))

            dias_procesados += 1
            current += timedelta(days=1)

        # ── 6. Insert batch (1 round-trip para TODOS los días) ────────────────
        if batch_logs:
            q_insert = """
                INSERT OR IGNORE INTO logs_raw
                    (empleado_id, fecha_hora, tipo, manual, observaciones, hash_original)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            await db.executemany(q_insert, batch_logs)
            logger.info(f"📥 [Relleno Masivo] {len(batch_logs)} marcas teóricas insertadas para empleado {empleado_id}")

            # ── 7. Un solo reproceso para todo el período ─────────────────────
            # Usa el motor optimizado con pre-carga de contexto (OPT3).
            await service.reprocesar_periodo_empleado(
                empleado_id=empleado_id,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                force=True
            )

        return {
            "success": True,
            "mensaje": f"Proceso completado. Procesados: {dias_procesados}, Ignorados: {dias_ignorados}",
            "dias_procesados": dias_procesados,
            "dias_ignorados":  dias_ignorados,
            "marcas_insertadas": len(batch_logs),
            "errores": errores
        }

    except Exception as e:
        logger.error(f"Error en relleno masivo empleado {empleado_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tramos/")
async def actualizar_tramos(
    empleado_id: int = Body(...),
    fecha: str = Body(...),
    minutos_conduccion_b: Optional[int] = Body(None),
    minutos_espera_b: Optional[int] = Body(None),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Permite registrar/modificar manualmente los tramos con RLS.
    """
    # RLS
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    current_user.verificar_acceso_area(emp.area, "este empleado")

    # Blindaje de Cierre
    if await service.is_fecha_cerrada_empleado(empleado_id, fecha):
         raise HTTPException(status_code=403, detail="El periodo correspondiente a esta fecha se encuentra cerrado y no admite modificaciones.")

    try:
        db = service.repository.db
        
        # Verificar que exista la asistencia
        actual = await service.repository.get_asistencia(empleado_id, fecha)
        if not actual:
            raise HTTPException(status_code=404, detail="No existe registro de asistencia para esta fecha. El empleado debe tener al menos una marca o turno proyectado.")
            
        # Actualizar en DB
        query = """
            UPDATE asistencias 
            SET minutos_conduccion_b = ?, minutos_espera_b = ?
            WHERE empleado_id = ? AND fecha = ?
        """
        await db.execute(query, (minutos_conduccion_b, minutos_espera_b, empleado_id, fecha))
        
        # Opcionalmente recalcular la asistencia si hubo otros cambios. Por ahora solo guardamos.
        
        updated = await service.repository.get_asistencia(empleado_id, fecha)
        return {
            "success": True,
            "mensaje": f"Tramos actualizados correctamente para el {fecha}.",
            "asistencia": updated
        }
    except Exception as e:
        from loguru import logger
        logger.error(f"Error actualizando tramos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/recalcular-bolsa/")
async def recalcular_bolsa_endpoint(
    empleado_id: int = Body(...),
    fecha_inicio: str = Body(...),
    fecha_fin: str = Body(...),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Fuerza el recalculo completo de la Bolsa Flexible (Art. 25 Bis) para un empleado en un periodo.
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

        # Forzar sync explícito a Turso inmediatamente después del reproceso.
        # Sin esto, los datos locales correctos pueden ser sobreescritos por el
        # sync automático en el próximo reinicio si Turso aún tiene datos viejos.
        try:
            await service.repository.db.sync_from_cloud()
            from loguru import logger as _log
            _log.info(f"✅ Sync post-reproceso a Turso completado (empleado {empleado_id})")
        except Exception as sync_err:
            from loguru import logger as _log
            _log.warning(f"⚠️ Sync post-reproceso no crítico: {sync_err}")

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
    intercambio = await db.fetch_one("SELECT * FROM intercambios_dias WHERE id = ?", (intercambio_id,))
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
    return {"success": True, "data": bolsa, "periodo": periodo}


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

    # Validar que tenga saldo suficiente en la bolsa
    bolsa = await service.repository.get_bolsa_he_disponible(
        data.empleado_id, periodo["fecha_inicio"], periodo["fecha_fin"]
    )
    if data.minutos > bolsa["minutos_disponibles"]:
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
        await db.execute("""
            INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle)
            VALUES (?, ?, ?, ?, ?)
        """, (current_user.user_id, current_user.username, 'CREATE_COMPENSACION', 'Marcaciones', 
              f"Compensación ID {compensacion_id}: Inasistencia del {data.fecha_inasistencia} cubierta con {data.minutos} min de la bolsa de HE"))
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
    c = await db.fetch_one("SELECT * FROM compensaciones_he_inasistencia WHERE id = ?", (compensacion_id,))
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
        await db.execute("""
            INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle)
            VALUES (?, ?, ?, ?, ?)
        """, (current_user.user_id, current_user.username, 'DELETE_COMPENSACION', 'Marcaciones', 
              f"Eliminada compensación ID {compensacion_id}: Inasistencia del {fecha_inasistencia} desmarcada de la bolsa de HE"))
    except Exception as aud_err:
        logger.warning(f"No se pudo registrar auditoría de eliminación de compensación: {aud_err}")
        
    return {"success": True, "message": "Compensación eliminada y asistencia recalculada"}

