"""
Router - Asistencia
Endpoints para procesar y consultar asistencia
"""

import json
from backend.core.fast_json import fast_json
from fastapi import APIRouter, Depends, Query, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta, timezone
from loguru import logger

from backend.services.asistencia_service import AsistenciaService
from backend.services import quantum_matrix_engine as _motor  # su reloj (_get_now_local) es el único: las pruebas lo fijan en un solo lugar
from backend.services.reglas_marcas_def import (TIPO_NO_SE_USA, propuesta_cinco_marcas, propuesta_tres_marcas, propuesta_una_marca,
                                                 secuencia_en_revision)
from backend.services.bono_service import BonoService
from backend.services.empleado_service import EmpleadoService
from backend.services.turno_service import TurnoService
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.empleado import EmpleadoRepository
from backend.repositories.turno import TurnoRepository
from backend.repositories.seguridad import SeguridadRepository
from backend.core.database import Database, get_db
from backend.core.security import SecurityContext, RequirePermission
from backend.schemas.asistencia import (
    AprobarHERequest,
    AsignacionIndividual,
    BatchSyncRequest,
    ReasignarTurnoRequest,
)


router = APIRouter(
    prefix="/asistencia",
    tags=["Asistencia"]
)

from backend.routers.asistencia_comun import get_asistencia_service  # compartido con los routers de la etapa 6

async def get_bono_service(db: Database = Depends(get_db)) -> BonoService:
    return BonoService(db)

async def get_empleado_service(db: Database = Depends(get_db)) -> EmpleadoService:
    repository = EmpleadoRepository(db)
    return EmpleadoService(repository)

async def get_turno_service(db: Database = Depends(get_db)) -> TurnoService:
    repository = TurnoRepository(db)
    return TurnoService(repository)


def _cuando_cambio(updated_at) -> str:
    """«hoy a las 12:14» o «el 27-10 a las 18:05» para el aviso de cambio simultáneo. updated_at se guarda en UTC."""
    try:
        momento = updated_at if isinstance(updated_at, datetime) else datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    local = momento.astimezone(_motor._CHILE_TZ).replace(tzinfo=None)
    hora = local.strftime("%H:%M")
    return f"hoy a las {hora}" if local.date() == _motor._get_now_local().date() else f"el {local.strftime('%d-%m')} a las {hora}"

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

    anomalias = await AsistenciaRepository(db).get_anomalias_de_bloqueo(fecha, fecha_inicio_mes, areas_permitidas)
    
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

    emp_row = await EmpleadoRepository(db).get_rut(empleado_id)
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

    repo_asis = AsistenciaRepository(db)
    row = await repo_asis.get_ultimo_cambio(fecha_inicio, fecha_fin, area, current_user.get_areas_filter())
    raw_row = await repo_asis.get_resumen_marcas_crudas()
    max_raw = raw_row['max_raw_id'] if raw_row and raw_row['max_raw_id'] else 0
    count_raw = raw_row['count_raw'] if raw_row and raw_row['count_raw'] else 0

    last_asist_up = row["last_update"] if row and row["last_update"] else ""
    combined_update = f"{last_asist_up}|raw_{max_raw}_{count_raw}"

    result = {
        "last_update": combined_update,
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

    return fast_json(await service.repository.get_asistencias_periodo(
        fecha_inicio, fecha_fin, area, turno_id=turno_id, areas_permitidas=areas_permitidas
    ))

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

    return fast_json(data)



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

    return fast_json(data)


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
    fecha_inicio: Optional[str] = Query(None),
    fecha_fin: Optional[str] = Query(None),
    emp_service: EmpleadoService = Depends(get_empleado_service),
    turno_service: TurnoService = Depends(get_turno_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Endpoint consolidado para obtener empleados, turnos y áreas filtradas para los filtros con RLS.
    Soporta cascada 4 niveles: Mes/Año → Área → Horario → Empleado.
    Optimiza la performance al reducir el número de peticiones.
    """
    # RLS: Si pide un área, verificarla. Si no pide, filtrar por sus permitidas.
    if area:
        current_user.verificar_acceso_area(area, "el área solicitada")
    areas_permitidas = current_user.get_areas_filter()
    
    # 0. Áreas con empleados que tienen horarios/turnos asignados
    f_desde = fecha_inicio
    f_hasta = fecha_fin
    if not f_desde and mes and anio:
        import calendar as _cal
        _, ult = _cal.monthrange(anio, mes)
        f_desde = f"{anio:04d}-{mes:02d}-01"
        f_hasta = f"{anio:04d}-{mes:02d}-{ult:02d}"

    areas_con_horario = await emp_service.get_areas_con_horario(
        areas_permitidas=areas_permitidas,
        fecha_desde=f_desde,
        fecha_hasta=f_hasta
    )

    # 1. Obtener turnos del área (sin detalles de días para velocidad)
    turnos = await turno_service.get_all_turnos(area=area, include_details=False, areas_permitidas=areas_permitidas)
    
    # 2. Obtener empleados — si turno_id está activo, filtrar solo los asignados a ese turno
    if turno_id:
        # Cascade: solo empleados con asignación activa a ese turno
        emp_rows = await emp_service.repository.get_activos_del_turno(turno_id, area, areas_permitidas)
        empleados = [dict(r) for r in emp_rows]
    else:
        empleados = await emp_service.get_lookup(area=area, activo=True, areas_permitidas=areas_permitidas)
    
    return {
        "areas": areas_con_horario,
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
    empleados = await EmpleadoRepository(service.repository.db).get_activos_sin_turno(areas_permitidas)
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

    res = await EmpleadoRepository(service.repository.db).contar_sin_turno_en_area(area, fecha_inicio, fecha_fin)
    return {"count": res["count"] if res else 0}

@router.post("/jornada/validar/")
async def validar_jornada_endpoint(
    empleado_id: int = Body(...),
    fecha: str = Body(...),
    accion: str = Body("APROBAR"),
    observaciones: Optional[str] = Body(None),
    minutos_autorizados: Optional[float] = Body(None),
    last_updated_at: Optional[str] = Body(None, description="Fecha/Hora de la versión que el usuario está viendo"),
    parte: str = Body("JORNADA", description="JORNADA (jornada especial o +2) o LLAMADO (llamado de un día no laborable)"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Gestiona una jornada especial (APROBAR, APROBAR_COMO_HE, RECHAZAR o REVERTIR) con RLS. Con parte=LLAMADO decide el
    llamado de emergencia de un día no laborable, aparte de la jornada especial (05-11-2026). Toda decisión, también
    REVERTIR, queda en la auditoría.
    """
    parte = (parte or "JORNADA").upper()
    if parte not in ("JORNADA", "LLAMADO"):
        raise HTTPException(status_code=400, detail="Parte no válida.")
    if accion not in ("APROBAR", "APROBAR_COMO_HE", "RECHAZAR", "REVERTIR"):
        raise HTTPException(status_code=400, detail="Acción no válida.")
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
                cuando = _cuando_cambio(actual.get('updated_at'))
                raise HTTPException(
                    status_code=409,
                    detail=f"Otra persona cambió este día{' ' + cuando if cuando else ''}. Su cambio no se guardó. Cierre y vuelva a abrir el día para ver lo último."
                )

        resultado = await service.validar_jornada(
            empleado_id=empleado_id,
            fecha=fecha,
            accion=accion,
            observaciones=observaciones,
            minutos_autorizados=minutos_autorizados,
            validador_id=current_user.user_id,
            parte=parte,
        )
        if isinstance(resultado, dict) and 'error' in resultado:
            raise HTTPException(status_code=400, detail=resultado['error'])
        try:
            from backend.repositories.seguridad import SeguridadRepository
            import json as _json
            await SeguridadRepository(service.repository.db).log_auditoria(
                current_user.user_id, current_user.username,
                "REVERTIR_JORNADA" if accion == "REVERTIR" else "VALIDAR_JORNADA", "MARCACIONES",
                _json.dumps({"empleado_id": empleado_id, "empleado": f"{emp.apellido_paterno or ''} {emp.apellido_materno or ''}, {emp.nombre or ''}".strip(),
                             "fecha": fecha, "parte": parte, "accion": accion,
                             "minutos": (resultado or {}).get("minutos_extra_autorizados")}, ensure_ascii=False))
        except Exception as audit_err:
            logger.warning(f"[Jornada] Auditoría de la validación no registrada: {audit_err}")
        if parte == "LLAMADO":
            mensaje = {"APROBAR": "Llamado validado como jornada EXTRA", "APROBAR_COMO_HE": "Llamado validado como horas extra",
                       "RECHAZAR": "Llamado rechazado", "REVERTIR": "Llamado devuelto a por validar"}[accion]
        elif accion == "APROBAR_COMO_HE":
            mensaje = "Jornada especial pasada a horas extra: quedan por aprobar con las demás horas extra del día"
        elif accion == "APROBAR":
            mensaje = "Jornada especial validada como jornada extra"
        elif accion == "REVERTIR":
            mensaje = "Jornada revertida exitosamente"
        else:
            mensaje = "Jornada rechazada exitosamente"
        return {
            "success": True,
            "mensaje": mensaje,
            "asistencia": resultado
        }
    except HTTPException:
        # El aviso (400) y el conflicto de concurrencia (409) llegan tal cual a la pantalla, no como «error interno»
        raise
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

# ── Salida de un turno de noche ingresada a mano (2026-10-16) ─────────────────────────────────────────────────────────────────
# Caso Eduardo Donoso 11-10: se ingresó Entrada 23:00 y Salida 07:00 y las dos quedaron con fecha 11-10; la Salida (07:00 del 11) cayó
# en el turno de la noche anterior, sin Entrada, y el panel pedía "ingrese la Entrada faltante" (falso positivo). Una jornada no termina antes
# de empezar: la Salida igual o anterior a la Entrada es la del día siguiente.
def _hora_con_segundos(hora: Any) -> str:
    """'07:00' o '07:00:00' → '07:00:00'. Una hora que no existe (25:00, 7) es un error, no una marca."""
    h = str(hora).strip()
    h = f"{h}:00" if h.count(":") == 1 else h
    try:
        return datetime.strptime(h, "%H:%M:%S").strftime("%H:%M:%S")
    except ValueError:
        raise ValueError(f"Hora inválida: «{hora}». Use el formato HH:MM.") from None


def fecha_de_la_salida(fecha: str, hora_salida: Any, hora_entrada: Any = None, cruza_medianoche: bool = False) -> str:
    """
    Fecha (YYYY-MM-DD) en que cae la Salida de la jornada que empieza en `fecha`.
      · el turno declara que cruza la medianoche → el día siguiente;
      · la Salida es igual o anterior a la Entrada (23:00 → 07:00) → el día siguiente;
      · sin Entrada con la que compararla (y sin el aviso del turno) → la misma fecha: no se inventa nada.
    """
    manana = (datetime.strptime(fecha, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    if cruza_medianoche:
        return manana
    if hora_entrada and _hora_con_segundos(hora_salida) <= _hora_con_segundos(hora_entrada):
        return manana
    return fecha


def _marca_en_el_futuro(fecha_hora: str, ahora: datetime) -> bool:
    """
    True si la marca cae después del minuto actual. Una marca manual registra algo que YA ocurrió: una hora que todavía no llega no se mide,
    se supone (caso 17-10-2026: 22 marcas, entre ellas Salidas de las 14:00 ingresadas a las 09:30). Se compara al minuto, porque el formulario
    manda horas sin segundos: la hora de este mismo minuto es válida.
    """
    return datetime.strptime(str(fecha_hora)[:19], "%Y-%m-%d %H:%M:%S") > ahora.replace(second=59, microsecond=0)


_TIPOS_ENTRADA = ('entrada', 'entry', 'e', 'in', '1')
_TIPOS_SALIDA = ('salida', 'exit', 's', 'out', '2')


async def _hora_de_entrada_sin_cerrar(db, empleado_id: int, fecha: str) -> Optional[str]:
    """Hora (HH:MM:SS) de la última marca de `fecha` si es una Entrada (con el tipo ya corregido por una persona): una Entrada sin Salida."""
    ultima = await AsistenciaRepository(db).get_ultima_marca_del_dia(empleado_id, fecha)
    if ultima and str(ultima["tipo"] or "").strip().lower() in _TIPOS_ENTRADA:
        return str(ultima["fecha_hora"])[11:19]
    return None


def _rellena_un_hueco(marcas: List[Dict[str, Any]], fecha_hora: str, tipo: str) -> bool:
    """True si una marca suelta cae ENTRE dos marcas del día que la piden: una SALIDA entre dos Entradas (faltó la
    salida a colación) o una ENTRADA entre dos Salidas (faltó la vuelta de colación). No pisa al reloj: completa la
    secuencia, igual que la propuesta de la regla en la ventana. Antes de la primera marca o después de la última no
    cuenta, así no sirve para borrar un atraso o una salida adelantada (para eso está el Perdonazo)."""
    t = str(tipo or "").strip().lower()
    if t not in ("entrada", "salida"):
        return False
    opuesto = _TIPOS_SALIDA if t == "entrada" else _TIPOS_ENTRADA
    fh = str(fecha_hora)[:19]
    antes = [m for m in marcas if str(m["fecha_hora"])[:19] < fh]
    despues = [m for m in marcas if str(m["fecha_hora"])[:19] > fh]
    if not antes or not despues:
        return False
    return (str(antes[-1]["tipo"] or "").strip().lower() in opuesto
            and str(despues[0]["tipo"] or "").strip().lower() in opuesto)


def _duracion_texto(fh_desde: str, fh_hasta: str) -> str:
    minutos = _min_abs(fh_hasta) - _min_abs(fh_desde)
    return f"{minutos // 60} h {minutos % 60:02d} min"


@router.post("/marcaciones/manual/")
async def agregar_marcacion_manual(
    empleado_id: int,
    fecha: str,
    hora: Optional[str] = None,
    tipo: Optional[str] = Query(None, pattern="^(Entrada|Salida)$"),
    hora_entrada: Optional[str] = None,
    hora_salida: Optional[str] = None,
    observaciones: Optional[str] = None,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Agrega marcación(es) manual(es) y reprocesa la asistencia del día en una sola transacción.
    Acepta (hora + tipo) para 1 marca, o (hora_entrada + hora_salida) para ambas en 1 sola llamada.
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
        import hashlib
        db = service.repository.db
        rut = emp.rut if emp and emp.rut else str(empleado_id)
        obs_str = observaciones or "Marcación manual"

        # Blindaje: No permitir sobreescribir si ya existen ambas marcas biométricas en el reloj
        bio_logs = await AsistenciaRepository(db).get_marcas_del_reloj_del_dia(empleado_id, fecha)
        has_bio_in = any(str(b.get('tipo', '')).strip().lower() in ('entrada', 'entry', 'e', 'in', '1') for b in bio_logs)
        has_bio_out = any(str(b.get('tipo', '')).strip().lower() in ('salida', 'exit', 's', 'out', '2') for b in bio_logs)
        # Una SALIDA sola que cierra la última ENTRADA del día (segunda jornada, u olvido tras la colación) no pisa al reloj:
        # completa la marca que falta, así que se permite aunque el reloj ya tenga Entrada y Salida ese día.
        solo_salida = bool((hora_salida and not hora_entrada) or (tipo == "Salida" and hora and not hora_entrada and not hora_salida))
        cierra_entrada = solo_salida and bool(await _hora_de_entrada_sin_cerrar(db, empleado_id, fecha))
        # Una marca suelta que rellena un hueco entre dos marcas (la propuesta de la regla en «Corregir marcas del día»,
        # caso 19-11-2026: Entrada · Entrada · Salida, faltaba la salida a colación) tampoco pisa al reloj.
        rellena_hueco = False
        if has_bio_in and has_bio_out and not cierra_entrada and tipo and hora and not hora_entrada and not hora_salida:
            rellena_hueco = _rellena_un_hueco(await AsistenciaRepository(db).get_marcas_del_dia_en_orden(empleado_id, fecha),
                                              f"{fecha} {_hora_con_segundos(hora)}", tipo)
        if has_bio_in and has_bio_out and not cierra_entrada and not rellena_hueco and not getattr(current_user, 'is_superuser', False):
            raise HTTPException(
                status_code=400,
                detail="Esta jornada ya cuenta con marcaciones biométricas válidas de Entrada y Salida en el reloj. Si desea condonar un atraso o salida anticipada, utilice la función oficial de Perdonazo."
            )

        marcas_a_insertar = []
        aviso = None
        hora_entrada_ok = hora_entrada if hora_entrada and str(hora_entrada).strip() not in ('', 'null', 'undefined') else None
        if hora_entrada_ok:
            fh_ent = f"{fecha} {_hora_con_segundos(hora_entrada_ok)}"
            marcas_a_insertar.append((fh_ent, "Entrada"))
        if hora_salida and str(hora_salida).strip() not in ('', 'null', 'undefined'):
            # Blindaje contra artefacto 00:00 de salida cuando se acompaña con entrada matutina diurna
            h_sal_clean = str(hora_salida).strip()
            h_ent_clean = str(hora_entrada).strip() if hora_entrada else ""
            if h_sal_clean in ('00:00', '00:00:00') and h_ent_clean and '06:00' <= h_ent_clean <= '12:00':
                logger.warning(f"Ignorando salida espuria 00:00 para entrada matutina {h_ent_clean} de empleado {empleado_id}")
            else:
                # Sin Entrada en esta petición, se compara con la Entrada que el día dejó sin cerrar (si la hay)
                ent_ref = hora_entrada_ok or await _hora_de_entrada_sin_cerrar(db, empleado_id, fecha)
                fh_sal, aviso = await _armar_salida_manual(service, empleado_id, fecha, hora_salida, ent_ref)
                marcas_a_insertar.append((fh_sal, "Salida"))
        if not hora_entrada and not hora_salida and hora and tipo:
            if tipo == "Salida":
                fh_single, aviso = await _armar_salida_manual(service, empleado_id, fecha, hora,
                                                              await _hora_de_entrada_sin_cerrar(db, empleado_id, fecha))
            else:
                fh_single = f"{fecha} {_hora_con_segundos(hora)}"
            marcas_a_insertar.append((fh_single, tipo))

        if not marcas_a_insertar:
            raise HTTPException(status_code=400, detail="Debe proporcionar 'hora' y 'tipo' o bien 'hora_entrada' / 'hora_salida'")

        # Una marca manual registra algo que ya pasó. Si alguna cae en el futuro no se guarda ninguna (el resto se puede ingresar ahora)
        ahora = _motor._get_now_local()
        futuras = [fh for fh, _ in marcas_a_insertar if _marca_en_el_futuro(fh, ahora)]
        if futuras:
            cuando = ", ".join(f"{fh[11:16]} del {fh[8:10]}-{fh[5:7]}" for fh in futuras)
            raise HTTPException(status_code=400, detail=(
                (f"La marca de las {cuando} todavía no ocurre" if len(futuras) == 1 else f"Las marcas de las {cuando} todavía no ocurren")
                + f" (ahora son las {ahora.strftime('%H:%M')} del {ahora.strftime('%d-%m')}). "
                  "Una marca manual solo registra algo que ya pasó: ingrésela cuando ocurra."))

        for fh, t in marcas_a_insertar:
            raw_string = f"{rut}|{fh}|{t}"
            hash_val = hashlib.sha256(raw_string.encode()).hexdigest()
            await AsistenciaRepository(db).insertar_marca_manual(empleado_id, rut, fh, t, obs_str, hash_val,
                                                                 getattr(current_user, "user_id", None))

        # 2. Reprocesar asistencia del día UNA SOLA VEZ
        resultado = await service.procesar_empleado_dia(empleado_id, fecha, save=True)
        # La Salida de un turno de noche cae al día siguiente: ese día también ve la marca; si ya estaba calculado, se recalcula
        for otro_dia in sorted({fh[:10] for fh, _ in marcas_a_insertar} - {fecha}):
            if (otro_dia <= datetime.now().strftime("%Y-%m-%d") and await service.repository.get_asistencia(empleado_id, otro_dia)
                    and not await service.repository.check_fecha_cerrada(otro_dia, empleado_id)):
                await service.procesar_empleado_dia(empleado_id, otro_dia, save=True)

        return {
            "success": True,
            "mensaje": f"Se agregaron {len(marcas_a_insertar)} marcaciones manuales y se reprocesó la asistencia",
            "aviso": aviso,
            "asistencia": resultado
        }
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _armar_salida_manual(service: AsistenciaService, empleado_id: int, fecha: str, hora_salida: Any, hora_entrada: Optional[str]):
    """
    Fecha y hora completas de una Salida manual de la jornada que empieza en `fecha`, y el aviso si quedó al día siguiente.
    Si ese día siguiente está en un período cerrado no se agrega la marca (no se puede modificar).
    """
    fecha_sal = fecha_de_la_salida(fecha, hora_salida, hora_entrada)
    fh_sal = f"{fecha_sal} {_hora_con_segundos(hora_salida)}"
    if fecha_sal == fecha:
        return fh_sal, None
    if await service.repository.check_fecha_cerrada(fecha_sal, empleado_id):
        raise HTTPException(status_code=403, detail=f"La Salida cae el {fecha_sal[8:]}-{fecha_sal[5:7]} (día siguiente) y ese período está cerrado: no admite modificaciones.")
    aviso = (f"La Salida de las {fh_sal[11:16]} quedó el {fecha_sal[8:]}-{fecha_sal[5:7]} (día siguiente) porque es anterior a la Entrada: "
             "el turno cruza la medianoche.")
    if hora_entrada:
        aviso += f" Jornada de {_duracion_texto(f'{fecha} {_hora_con_segundos(hora_entrada)}', fh_sal)}: revise que sea correcta."
    return fh_sal, aviso

# ── Marcaciones del día: ver todas y elegir cuál es Entrada / Salida (2026-10-14) ─────────────────────────
# Caso Catalina Núñez 09-10: el reloj dejó la primera marca del día como "Salida" y el motor la descartaba (atraso falso de 273 min).
# La marca cruda no se toca: la reclasificación se guarda aparte (logs_tipo_override) y el motor lee el tipo ya corregido.
_COLACION_MIN, _COLACION_MAX = 20, 150  # minutos entre una salida y la siguiente entrada para considerarlas colación


def ciclo_para_marca_sola(ciclos: List[Dict[str, Any]], hora: str, tipo: str) -> Optional[Dict[str, Any]]:
    """De los ciclos del horario para ese día, el que mejor calza con una marca sola según su TIPO: una SALIDA se
    compara con la salida de cada ciclo y una ENTRADA con la entrada (distancia en el reloj de 24 horas). Sirve para
    proponer la marca que falta. Devuelve None si no hay ciclos o el tipo no se reconoce."""
    clave = 'hora_salida' if str(tipo or '').strip().lower().startswith('s') else (
        'hora_entrada' if str(tipo or '').strip().lower().startswith('e') else None)
    if not clave or not ciclos:
        return None

    def minutos(h):
        hh, mm = str(h)[:5].split(':')
        return int(hh) * 60 + int(mm)
    m = minutos(hora)

    def distancia(c):
        d = abs(minutos(c[clave]) - m)
        return min(d, 1440 - d)
    return min(ciclos, key=distancia)


def _min_abs(fh: str) -> int:
    """Minutos de una marca contados desde el año 1 (fecha + hora): sirve para medir huecos que cruzan la medianoche."""
    fh = str(fh)
    return datetime.strptime(fh[:10], "%Y-%m-%d").toordinal() * 1440 + int(fh[11:13]) * 60 + int(fh[14:16])


def _ids_de_json(txt: Any) -> Set[int]:
    """Ids de marcas guardados como texto JSON (asistencias.marcas_consumidas_ids)."""
    try:
        v = json.loads(txt) if isinstance(txt, (str, bytes)) else (txt or [])
    except Exception:
        return set()
    out: Set[int] = set()
    for x in (v if isinstance(v, list) else []):
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            pass
    return out


def marcas_que_pertenecen_al_dia(fecha: str, marcas: List[Dict[str, Any]], ids_dia: Set[int], ids_vecinos: Set[int]) -> List[Dict[str, Any]]:
    """
    De las marcas de ayer, hoy y mañana, cuáles son de la jornada de `fecha` (la columna "marcas del día" del modal):
      · las que usó el cálculo de ese día (`ids_dia`), aunque caigan en la fecha siguiente del calendario: un turno que cruza la
        medianoche cierra con una marca del día siguiente (Entrada 14:59 del 13 · Salida 00:08 del 14 son una sola jornada);
      · las que nadie usó y caen en esa fecha del calendario;
      · nunca las que usó el día anterior o el siguiente (`ids_vecinos`): la Salida de las 00:08 del 14 es del turno del 13.
    Sin cálculo previo del día (`ids_dia` vacío) queda lo que cae en la fecha del calendario menos lo que ya usó un día vecino.
    """
    out = []
    for m in marcas:
        mid = m.get("id")
        if mid in ids_dia or (str(m.get("fecha_hora", ""))[:10] == fecha and mid not in ids_vecinos):
            out.append(m)
    return sorted(out, key=lambda m: str(m.get("fecha_hora", "")))


async def _marcas_del_dia(db, empleado_id: int, fecha: str) -> List[Dict[str, Any]]:
    """Marcas (con el tipo ya corregido por una persona, si lo hubo) que pertenecen a la jornada de `fecha`. Incluye las que
    una persona dejó como «No se usa» (tipo 'No se usa'): el cálculo no las lee, pero la ventana las muestra para poder deshacerlo."""
    f = datetime.strptime(fecha, "%Y-%m-%d")
    ayer, manana = (f - timedelta(days=1)).strftime("%Y-%m-%d"), (f + timedelta(days=1)).strftime("%Y-%m-%d")
    repo = AsistenciaRepository(db)
    rows = await repo.get_marcas_entre(empleado_id, f"{ayer} 00:00:00", f"{manana} 23:59:59")
    asist = await repo.get_marcas_usadas_por_dia(empleado_id, (ayer, fecha, manana))
    usadas = {str(a["fecha"])[:10]: _ids_de_json(a["marcas_consumidas_ids"]) for a in asist}
    return marcas_que_pertenecen_al_dia(fecha, [dict(r) for r in rows], usadas.get(fecha, set()),
                                        usadas.get(ayer, set()) | usadas.get(manana, set()))


def marcas_doble_toque(rows: List[Dict[str, Any]], segundos: float) -> Dict[Any, Dict[str, Any]]:
    """Las marcas que el cálculo descarta como doble toque, con la misma limpieza que usa el motor
    (TensorMarkDeduplicator.deduplicate_and_sort). Devuelve {id descartada: {"hora": hora de la que se usó, "segundos": separación}}
    para que la ventana muestre lo mismo que ve la regla."""
    from backend.services.quantum_matrix_engine import TensorMarkDeduplicator
    descartadas: List[Any] = []
    TensorMarkDeduplicator.deduplicate_and_sort([dict(r) for r in rows], bounce_seconds=segundos, descartadas=descartadas)
    out: Dict[Any, Dict[str, Any]] = {}
    for desc, cons in descartadas:
        try:
            t_d = datetime.strptime(str(desc["fecha_hora"])[:19], "%Y-%m-%d %H:%M:%S")
            t_c = datetime.strptime(str(cons["fecha_hora"])[:19], "%Y-%m-%d %H:%M:%S")
        except (KeyError, ValueError):
            continue
        out[desc.get("id")] = {"hora": str(cons["fecha_hora"])[11:19], "segundos": int(abs((t_d - t_c).total_seconds()))}
    return out


async def _colacion_tipica(db, turno_id, hora_entrada) -> Optional[Dict[str, Any]]:
    """A qué hora salen y vuelven de colación las personas de un horario (mismo horario y misma hora de entrada): la mediana
    de la 2.ª y la 3.ª marca de los días ENTRADA · SALIDA · ENTRADA · SALIDA del reloj, sin marcas manuales, del tramo
    abierto. Se calcula con las marcas reales cada vez (≈70 ms en el horario más grande); None si no hay ningún día así."""
    import statistics
    from backend.repositories.reglas_marcas import ReglasMarcasRepository
    desde = await ReglasMarcasRepository(db).inicio_tramo_abierto()
    filas = await AsistenciaRepository(db).get_marcas_del_reloj_de_un_horario(turno_id, hora_entrada, desde)
    sale, vuelve = [], []
    for f in filas:
        if f["pat"] != "ESES" or int(f["man"] or 0):
            continue
        h = str(f["horas"]).split(",")
        sale.append(int(h[1][:2]) * 60 + int(h[1][3:5]))
        vuelve.append(int(h[2][:2]) * 60 + int(h[2][3:5]))
    if not sale:
        return None
    return {"sale": int(statistics.median(sale)), "vuelve": int(statistics.median(vuelve)), "dias": len(sale)}


async def _propuesta_dia_tres_marcas(service, empleado_id: int, fecha: str, usadas, hd, horario, col_horario: int, tipica=None,
                                     doble_toque=None):
    """Opciones para la ventana (ver propuesta_tres_marcas), con el tipo de cada marca por id, la marca nueva con su fecha y
    lo que pagaría cada una: el día se calcula en memoria con esas marcas (collect_only, no se guarda nada)."""
    from backend.repositories.reglas_marcas import ReglasMarcasRepository
    db = service.repository.db
    vc = await ReglasMarcasRepository(db).ventana_colacion()
    if tipica is None and hd.get("turno_asignado_id"):
        tipica = await _colacion_tipica(db, hd.get("turno_asignado_id"), horario["entrada"])
    fhs = [str(r["fecha_hora"])[:19] for r in usadas]
    if len(usadas) == 1:
        p = propuesta_una_marca(fhs[0], usadas[0]["tipo"], horario["entrada"], horario["salida"])
    elif len(usadas) == 5:
        p = propuesta_cinco_marcas(fhs, [r["tipo"] for r in usadas], col_horario)
    else:
        p = propuesta_tres_marcas(fhs, horario["entrada"], horario["salida"], int(vc.get("min", 20)), int(vc.get("max", 150)),
                                  col_horario, tipica, tipos=[r["tipo"] for r in usadas])
    if not p:
        return None
    marcas_dt = [datetime.strptime(x, "%Y-%m-%d %H:%M:%S") for x in fhs]
    opciones = []
    for op in p["opciones"]:
        marca = None
        if op["marca"]:
            # La marca nueva va en su lugar: después de la marca que la antecede o antes de la que la sigue (turnos de noche)
            hh, mm = map(int, op["marca"]["hora"].split(":"))
            if op["clave"] == "FALTA_ENTRADA":
                ref, antes = marcas_dt[0], True
            elif op["clave"] == "FALTA_SALIDA":
                ref, antes = marcas_dt[-1], False
            elif op["clave"] == "FALTA_VUELTA":
                ref, antes = marcas_dt[1], False
            else:
                ref, antes = marcas_dt[1], True
            dt = ref.replace(hour=hh, minute=mm, second=0)
            if antes and dt > ref:
                dt -= timedelta(days=1)
            if not antes and dt < ref:
                dt += timedelta(days=1)
            marca = dict(op["marca"], fecha_hora=dt.strftime("%Y-%m-%d %H:%M:%S"), fecha=dt.strftime("%Y-%m-%d"))
        tipos_op = {str(r["id"]): t for r, t in zip(usadas, op["tipos"])}
        # Una marca que no se usa arrastra su doble toque: si no, la descartada vuelve a contar y el día cambia de secuencia
        for r, t in zip(usadas, op["tipos"]):
            if t == TIPO_NO_SE_USA:
                for id_dt, info in (doble_toque or {}).items():
                    if str(info.get("hora")) == str(r["fecha_hora"])[11:19]:
                        tipos_op[str(id_dt)] = TIPO_NO_SE_USA
        opciones.append({"clave": op["clave"], "titulo": op["titulo"], "motivo": op["motivo"], "marca": marca,
                         "tipos": tipos_op})

    async def paga(op):
        tipos = op["tipos"]
        base = dict(usadas[0])

        def transformar(logs):
            out = []
            for l in logs:
                t = tipos.get(str(l.get("id")))
                if t == TIPO_NO_SE_USA:
                    continue
                out.append(dict(l, tipo=t) if t else l)
            if op["marca"]:
                out.append(dict(base, id=-1, fecha_hora=op["marca"]["fecha_hora"], tipo=op["marca"]["tipo"],
                                tipo_original=op["marca"]["tipo"], manual=1, observaciones=op["motivo"]))
            return out
        r = await service.reprocesar_periodo_empleado(empleado_id, fecha, fecha, force=True, collect_only=True,
                                                      transformar_logs=transformar)
        fila = next((c for c in (r.get("_collect") or []) if str(c.get("fecha")) == fecha), None)
        if not fila and r.get("sin_cambio"):
            # Con esas marcas el día da lo mismo que ya está guardado: el cálculo no lo devuelve, se lee lo guardado
            fila = await AsistenciaRepository(db).get_resultado_dia(empleado_id, fecha)
        if not fila:
            return None
        return {"horas": round(float(fila.get("horas_trabajadas") or 0), 2), "estado": fila.get("estado"),
                "deuda_min": round(float(fila.get("minutos_deuda") or 0)),
                "atraso_min": round(float(fila.get("minutos_atraso") or 0)),
                "salida_adelantada_min": round(float(fila.get("minutos_salida_adelantada") or 0))}

    for op in opciones:
        try:
            op["resultado"] = await paga(op)
        except Exception as e:
            logger.warning(f"Simulación de la opción {op['clave']} ({empleado_id} {fecha}): {e}")
            op["resultado"] = None
    return {"combinacion": p["combinacion"], "opciones": opciones, "colacion_tipica": tipica}


def sugerir_clasificacion_marcas(horas: List[str]) -> List[Dict[str, Any]]:
    """
    Sugerencia de Entrada/Salida para las marcas de un día (ya ordenadas), y cuáles serían de colación.
      · primera = Entrada, última = Salida, el resto alterna.
      · una Salida seguida de una Entrada a mitad del día, separadas por 20-150 min = colación.
    Con una cantidad impar de marcas no se puede afirmar: se devuelve la alternancia pero con `dudoso`.
    """
    n = len(horas)
    out = [{"tipo": ("Entrada" if i % 2 == 0 else "Salida"), "colacion": False} for i in range(n)]
    if n >= 2:
        out[-1]["tipo"] = "Salida"
    for i in range(1, n - 1):
        if out[i]["tipo"] == "Salida" and out[i + 1]["tipo"] == "Entrada" and i + 1 <= n - 2:
            gap = _min_abs(horas[i + 1]) - _min_abs(horas[i])
            if _COLACION_MIN <= gap <= _COLACION_MAX:
                out[i]["colacion"] = out[i + 1]["colacion"] = True
                out[i]["colacion_min"] = out[i + 1]["colacion_min"] = gap
    dudoso = n % 2 == 1 or n < 2
    for o in out:
        o["dudoso"] = dudoso
    return out


@router.get("/marcaciones/dia/")
async def marcaciones_del_dia(
    empleado_id: int = Query(...),
    fecha: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """Todas las marcaciones de la jornada con lo que dijo el reloj, el tipo que rige hoy y una sugerencia (con la colación marcada).
    Incluye la marca del día siguiente que cerró un turno que cruza la medianoche y deja fuera la que cerró el turno de ayer."""
    emp = await EmpleadoRepository(service.repository.db).get_by_id(empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    current_user.verificar_acceso_area(emp.area, "este empleado")
    # Las marcas de la jornada, no solo las del día del calendario: un turno que cruza la medianoche cierra con una marca de mañana
    rows = await _marcas_del_dia(service.repository.db, empleado_id, fecha)
    # Horario asignado de ese día (lo guarda el cálculo en la asistencia): la ventana lo propone al escribir la marca que falta
    hd = await AsistenciaRepository(service.repository.db).get_horario_y_calculo_dia(empleado_id, fecha)
    turno_repo = TurnoRepository(service.repository.db)
    # Doble toque: las marcas que el cálculo deja fuera antes de aplicar la regla. La sugerencia y la colación se calculan
    # solo con las que se usan, igual que el cálculo.
    doble_toque: Dict[Any, Dict[str, Any]] = {}
    col_horario = 0
    tp = None
    try:
        from backend.services.quantum_matrix_engine import _rebote_defecto
        if hd and hd.get("turno_asignado_id"):
            t = await turno_repo.get_tipo_y_colacion(hd["turno_asignado_id"])
            tp = (t or {}).get("tipo_programacion")
            col_horario = int(float((t or {}).get("minutos_colacion_auto") or 0))
        # Las que una persona dejó como «No se usa» tampoco las lee el cálculo
        doble_toque = marcas_doble_toque([r for r in rows if r["tipo"] != TIPO_NO_SE_USA], _rebote_defecto(tp or ""))
    except Exception as e:
        logger.warning(f"Doble toque en la ventana ({empleado_id} {fecha}): {e}")
    no_usada = lambda r: r["id"] in doble_toque or r["tipo"] == TIPO_NO_SE_USA
    usadas = [r for r in rows if not no_usada(r)]
    sug_usadas = iter(sugerir_clasificacion_marcas([str(r["fecha_hora"]) for r in usadas]))
    sug = [({"tipo": r["tipo"], "colacion": False, "dudoso": len(usadas) % 2 == 1 or len(usadas) < 2}
            if no_usada(r) else next(sug_usadas)) for r in rows]
    horario = {"entrada": (hd or {}).get("hora_entrada_teorica"), "salida": (hd or {}).get("hora_salida_teorica")}
    # Tres marcas que se usan (falta una o sobra una), en un día que una regla dejó en revisión: una o dos opciones completas
    # según el horario del día y la colación de su mismo horario (reglas_marcas_def.propuesta_tres_marcas), cada una con lo
    # que pagaría (simulación sin guardar nada).
    # A qué hora sale y vuelve de colación su horario (marcas reales; Ciclo Inteligente): la ventana lo muestra en «Horario del día»
    tipica = None
    if hd and hd.get("turno_asignado_id") and tp == "CICLO_INTELIGENTE" and horario["entrada"]:
        try:
            tipica = await _colacion_tipica(service.repository.db, hd["turno_asignado_id"], horario["entrada"])
        except Exception as e:
            logger.warning(f"Colación típica ({empleado_id} {fecha}): {e}")
    # Con UNA sola marca, el ciclo del día no es seguro (el cálculo lo elige por la marca más cercana, sin mirar su tipo).
    # La propuesta usa el ciclo del horario asignado que calza con esa marca según lo que falte.
    if len(usadas) == 1 and hd and hd.get("turno_asignado_id"):
        try:
            dia_semana = datetime.strptime(fecha, "%Y-%m-%d").weekday()
            ciclos = await turno_repo.get_ciclos_del_dia(hd["turno_asignado_id"], dia_semana)
            ciclos = [dict(c) for c in ciclos]
            hora_sola = str(usadas[0]["fecha_hora"])[11:16]
            # Si falta la ENTRADA, la marca que hay es la SALIDA: ciclo cuya salida calza. Si falta la SALIDA, la marca
            # que hay es la ENTRADA: ciclo cuya entrada calza. Así sirve aunque el reloj la haya rotulado al revés.
            como_salida = ciclo_para_marca_sola(ciclos, hora_sola, "Salida")
            como_entrada = ciclo_para_marca_sola(ciclos, hora_sola, "Entrada")
            if como_salida and como_entrada:
                horario = {"entrada": como_salida["hora_entrada"], "salida": como_entrada["hora_salida"]}
        except Exception as e:
            logger.warning(f"Ciclo para la marca sola ({empleado_id} {fecha}): {e}")
    # Una, tres o cinco marcas en un día que una regla dejó en revisión: opciones ya resueltas (con una sola marca, con el
    # horario del ciclo que calza con ella)
    propuesta = None
    if len(usadas) in (1, 3, 5) and hd and secuencia_en_revision(hd.get("observaciones")):
        try:
            propuesta = await _propuesta_dia_tres_marcas(service, empleado_id, fecha, usadas, hd, horario, col_horario, tipica,
                                                     doble_toque)
        except Exception as e:
            logger.warning(f"Propuesta de marcas ({empleado_id} {fecha}): {e}")
    return {
        "success": True,
        "fecha_cerrada": bool(await service.repository.check_fecha_cerrada(fecha, empleado_id)),
        "horario": horario,
        "propuesta": propuesta,
        # «Horario del día» y «Cálculo» de la ventana: lo que hoy tiene guardado el día (el ciclo que eligió el cálculo;
        # «horario» puede mezclar dos ciclos para proponer la marca que falta en un día de una sola marca)
        "horario_dia": {"entrada": (hd or {}).get("hora_entrada_teorica"), "salida": (hd or {}).get("hora_salida_teorica")},
        "colacion_min": col_horario,
        "colacion_tipica": tipica,
        "bolsa": tp in ("BOLSA_FLEXIBLE", "FLEXIBLE_BOLSA"),
        "calculo": ({"estado": hd.get("estado"), "horas": round(float(hd.get("horas_trabajadas") or 0), 2),
                     "atraso_min": round(float(hd.get("minutos_atraso") or 0)),
                     "salida_adelantada_min": round(float(hd.get("minutos_salida_adelantada") or 0)),
                     "deuda_min": round(float(hd.get("minutos_deuda") or 0))} if hd else None),
        "marcas": [{
            "id": r["id"], "hora": str(r["fecha_hora"])[11:19], "fecha": str(r["fecha_hora"])[:10],
            "tipo_reloj": r["tipo_original"], "tipo_actual": r["tipo"],
            "corregida": (r["tipo"] != r["tipo_original"]), "manual": bool(r["manual"]), "equipo": r.get("equipo"),
            "sugerido": s["tipo"], "colacion": s["colacion"], "colacion_min": s.get("colacion_min"), "dudoso": s["dudoso"],
            "doble_toque": doble_toque.get(r["id"]), "no_se_usa": r["tipo"] == TIPO_NO_SE_USA,
        } for r, s in zip(rows, sug)],
    }


class MarcaTipoItem(BaseModel):
    id: int
    tipo: str


class ReclasificarMarcasRequest(BaseModel):
    empleado_id: int
    fecha: str
    marcas: List[MarcaTipoItem]


@router.post("/marcaciones/reclasificar/")
async def reclasificar_marcaciones(
    req: ReclasificarMarcasRequest,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """Fija si cada marca del día es Entrada o Salida y reprocesa el día. Las marcas crudas del reloj no se modifican."""
    emp = await EmpleadoRepository(service.repository.db).get_by_id(req.empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    current_user.verificar_acceso_area(emp.area, "este empleado")
    if await service.repository.check_fecha_cerrada(req.fecha, req.empleado_id):
        raise HTTPException(status_code=403, detail="El periodo de esta fecha se encuentra cerrado y no admite modificaciones.")
    if not req.marcas:
        raise HTTPException(status_code=400, detail="No hay marcaciones para clasificar.")
    nuevos = {}
    for m in req.marcas:
        t = (m.tipo or "").strip().capitalize()
        if t not in ("Entrada", "Salida", TIPO_NO_SE_USA):
            raise HTTPException(status_code=400, detail=f"Tipo inválido para la marca {m.id}: debe ser Entrada, Salida o No se usa.")
        nuevos[m.id] = t
    db = service.repository.db
    ids = list(nuevos.keys())
    ph = ",".join("?" * len(ids))
    # Solo marcas de ESTE empleado y de ESTA jornada (no se puede tocar una marca ajena por el id)
    del_dia = {m["id"]: m for m in await _marcas_del_dia(db, req.empleado_id, req.fecha)}
    permitidas = set(del_dia)
    orig = await AsistenciaRepository(db).get_tipos_de_marcas(ids, req.empleado_id)
    orig = {r["id"]: r["tipo"] for r in orig}
    if len(orig) != len(ids) or not set(ids) <= permitidas:
        raise HTTPException(status_code=400, detail="Alguna marca no corresponde a este empleado y día.")
    # «No se usa»: solo marcas del reloj (una manual se quita) y solo si la regla del día ofrece esa opción. Deshacerlo
    # (volver a ENTRADA o SALIDA) siempre se puede.
    nuevas_sin_uso = [i for i, t in nuevos.items() if t == TIPO_NO_SE_USA and del_dia[i]["tipo"] != TIPO_NO_SE_USA]
    if nuevas_sin_uso:
        if any(del_dia[i]["manual"] for i in nuevas_sin_uso):
            raise HTTPException(status_code=400, detail="Una marca manual no se marca como «No se usa»: quítela con «Quitar».")
        from backend.repositories.reglas_marcas import ReglasMarcasRepository
        ev = await ReglasMarcasRepository(db).evaluar_dia(req.empleado_id, req.fecha)
        if not (ev.get("en_revision") and "NO_SE_USA" in ((ev.get("regla") or {}).get("opciones_efectivas") or [])):
            raise HTTPException(status_code=400, detail="La regla de este día no permite dejar una marca sin usar.")
    repo_marcas = AsistenciaRepository(db)
    for log_id, t in nuevos.items():
        await repo_marcas.quitar_correccion_de_tipo(log_id)
        if str(orig[log_id] or "").strip().lower() != t.lower():
            await repo_marcas.corregir_tipo(log_id, t, getattr(current_user, "user_id", None))
    resultado = await service.procesar_empleado_dia(req.empleado_id, req.fecha, save=True)
    # El día siguiente hereda las marcas que usó este día (turnos que cruzan la medianoche): si ya estaba calculado, se recalcula
    manana = (datetime.strptime(req.fecha, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    if (manana <= datetime.now().strftime("%Y-%m-%d") and await service.repository.get_asistencia(req.empleado_id, manana)
            and not await service.repository.check_fecha_cerrada(manana, req.empleado_id)):
        await service.procesar_empleado_dia(req.empleado_id, manana, save=True)
    logger.info(f"🕘 Marcas reclasificadas: empleado {req.empleado_id} {req.fecha} por usuario {getattr(current_user, 'username', '?')}: {nuevos}")
    return {"success": True, "mensaje": "Marcaciones clasificadas y asistencia recalculada", "asistencia": resultado}


# ── Quitar UNA marcación manual, con permiso propio y registro (2026-10-16) ───────────────────────────────────────────────────
# Las marcas del reloj no se tocan nunca. Una marca manual la puso una persona (p. ej. una Salida de turno de noche con la fecha
# equivocada) y otra con el permiso `marcaciones.eliminar_manual` puede quitarla; la copia queda en la auditoría con quién, cuándo y por qué.
_MOTIVO_MIN_LETRAS = 5


@router.delete("/marcaciones/manual/{log_id}/")
async def quitar_marcacion_manual(
    log_id: int,
    motivo: str = Query(..., description="Por qué se quita la marca; queda en la auditoría"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.eliminar_manual"))
):
    """Quita una marcación manual (nunca una del reloj), guarda su copia en la auditoría y recalcula los días que la usaban."""
    db = service.repository.db
    motivo = (motivo or "").strip()
    if len(motivo) < _MOTIVO_MIN_LETRAS:
        raise HTTPException(status_code=400, detail=f"Indique el motivo (al menos {_MOTIVO_MIN_LETRAS} letras): queda registrado en la auditoría.")
    repo_marcas = AsistenciaRepository(db)
    marca = await repo_marcas.get_marca(log_id)
    if not marca:
        raise HTTPException(status_code=404, detail="Marcación no encontrada")
    if not marca["manual"]:
        raise HTTPException(status_code=400, detail="Solo se pueden quitar marcaciones manuales: las marcas del reloj no se modifican.")
    emp = await EmpleadoRepository(db).get_by_id(marca["empleado_id"])
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    current_user.verificar_acceso_area(emp.area, "este empleado")

    # Días que cuentan esta marca: el de su fecha y, si un turno de noche la usó como Salida, el día anterior
    dia = str(marca["fecha_hora"])[:10]
    ayer = (datetime.strptime(dia, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    calculados = await repo_marcas.get_marcas_usadas_por_dia(marca["empleado_id"], (ayer, dia))
    dias = sorted({dia} | {str(a["fecha"])[:10] for a in calculados if log_id in _ids_de_json(a["marcas_consumidas_ids"])})
    for d in dias:
        if await service.repository.check_fecha_cerrada(d, marca["empleado_id"]):
            raise HTTPException(status_code=403, detail=f"El periodo del {d[8:]}-{d[5:7]} se encuentra cerrado y no admite modificaciones.")

    from backend.repositories.seguridad import SeguridadRepository
    detalle = json.dumps({
        "marca_id": log_id, "empleado_id": marca["empleado_id"], "fecha_hora": str(marca["fecha_hora"]), "tipo": marca["tipo"],
        "observaciones": marca["observaciones"], "ingresada_por_usuario_id": marca["usuario_id"], "ingresada_el": str(marca["created_at"]),
        "motivo": motivo,
    }, ensure_ascii=False)
    async with db.transaction():  # sin copia en la auditoría no se quita nada
        await SeguridadRepository(db).log_auditoria(current_user.user_id, current_user.username, "ELIMINAR_MARCA_MANUAL", "MARCACIONES", detalle)
        await repo_marcas.quitar_correccion_de_tipo(log_id)
        await repo_marcas.borrar_marca_manual(log_id)
    logger.info(f"🗑️ Marca manual {log_id} ({marca['fecha_hora']}) de empleado {marca['empleado_id']} quitada por {current_user.username}: {motivo}")

    for d in dias:
        await service.procesar_empleado_dia(marca["empleado_id"], d, save=True)
    return {"success": True, "mensaje": "Marcación manual quitada y asistencia recalculada", "dias_recalculados": dias}


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
        
        # Eliminar las marcaciones manuales de este día (la copia de lo que se borra queda en la auditoría, con quién y cuándo)
        fecha_like = f"{fecha} %"
        repo_marcas = AsistenciaRepository(db)
        a_borrar = await repo_marcas.get_marcas_manuales_del_dia(empleado_id, fecha_like)
        from backend.repositories.seguridad import SeguridadRepository
        async with db.transaction():
            if a_borrar:
                await SeguridadRepository(db).log_auditoria(
                    current_user.user_id, current_user.username, "ELIMINAR_MARCAS_MANUALES_DEL_DIA", "MARCACIONES",
                    json.dumps({"empleado_id": empleado_id, "fecha": fecha, "marcas": [
                        {"marca_id": m["id"], "fecha_hora": str(m["fecha_hora"]), "tipo": m["tipo"], "observaciones": m["observaciones"],
                         "ingresada_por_usuario_id": m["usuario_id"], "ingresada_el": str(m["created_at"])} for m in a_borrar]}, ensure_ascii=False))
            await repo_marcas.borrar_marcas_manuales_del_dia(empleado_id, fecha_like)
        
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

    repo = AsistenciaRepository(service.repository.db)
    turno_repo = TurnoRepository(service.repository.db)
    # ── Blindaje de Cierre ──
    areas_rows = await emp_repo.get_nombres_areas_validadas_entre(empleado_id, fecha_inicio, fecha_fin)
    emp_areas = [r['area_nombre'] for r in areas_rows]
    
    if emp.area and emp.area not in emp_areas:
        emp_areas.append(emp.area)
        
    if emp_areas:
        closed_overlap = await repo.get_cierre_que_se_cruza(emp_areas, fecha_inicio, fecha_fin)
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
        asigs = await turno_repo.get_asignaciones_entre(empleado_id, fecha_inicio, fecha_fin)

        if not asigs:
            return {
                "success": True,
                "mensaje": "No hay turno asignado en el período. Ningún día procesado.",
                "dias_procesados": 0, "dias_ignorados": 0, "errores": []
            }

        # ── 2. Pre-carga: detalle de días de TODOS los turnos involucrados ───
        turno_ids = list({a["turno_id"] for a in asigs})
        dias_turno_rows = await turno_repo.get_dias_de_turnos(turno_ids)
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
            logs_existentes = await repo.get_fechas_hora_marcas_entre(empleado_id, fecha_inicio, fecha_fin)
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
        uid_masivo = getattr(current_user, "user_id", None)  # quién hizo el relleno: queda en cada marca
        dias_procesados = 0
        dias_ignorados  = 0
        dias_futuros    = 0
        ahora_masivo    = _motor._get_now_local()
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

            # Salida: en un turno que cruza la medianoche cae el día siguiente (Entrada 23:00 del 11 · Salida 07:00 del 12)
            fecha_sal = fecha_de_la_salida(fecha_str, hora_salida, hora_entrada, bool(config_dia.get("cruza_medianoche")))
            fh_sal = f"{fecha_sal} {hora_salida}:00"

            # Una marca manual registra algo que ya pasó: un día cuya Entrada o Salida todavía no ocurre no se rellena
            if _marca_en_el_futuro(fh_ent, ahora_masivo) or _marca_en_el_futuro(fh_sal, ahora_masivo):
                dias_futuros += 1
                current += timedelta(days=1)
                continue

            h_ent   = hashlib.sha256(f"{rut_str}|{fh_ent}|Entrada".encode()).hexdigest()
            batch_logs.append((empleado_id, fh_ent, "Entrada", 1, "Relleno Masivo", h_ent, uid_masivo))
            h_sal  = hashlib.sha256(f"{rut_str}|{fh_sal}|Salida".encode()).hexdigest()
            batch_logs.append((empleado_id, fh_sal, "Salida", 1, "Relleno Masivo", h_sal, uid_masivo))

            dias_procesados += 1
            current += timedelta(days=1)

        # ── 6. Insert batch (1 round-trip para TODOS los días) ────────────────
        if batch_logs:
            await repo.insertar_marcas_relleno(batch_logs)
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
            "mensaje": (f"Proceso completado. Procesados: {dias_procesados}, Ignorados: {dias_ignorados}"
                        + (f", omitidos por ser futuros: {dias_futuros}" if dias_futuros else "")),
            "dias_procesados": dias_procesados,
            "dias_ignorados":  dias_ignorados,
            "dias_futuros_omitidos": dias_futuros,
            "marcas_insertadas": len(batch_logs),
            "errores": errores
        }

    except Exception as e:
        logger.error(f"Error en relleno masivo empleado {empleado_id}: {e}")
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


# ── Temas separados en su propio archivo (etapa 6 de la auditoría): mismas direcciones, bajo /api/asistencia ──
from backend.routers import asistencia_gps, asistencia_libreta, asistencia_compensaciones  # noqa: E402

router.include_router(asistencia_gps.router)
router.include_router(asistencia_libreta.router)
router.include_router(asistencia_compensaciones.router)
