"""
Application Lifecycle Events
Manejo de eventos de startup y shutdown con Sync Scheduler
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import TYPE_CHECKING
import asyncio
from fastapi import FastAPI
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .database import db
from .config import settings
from backend.repositories.configuracion import ConfiguracionRepository
from backend.services.configuracion_service import ConfiguracionService
from .startup_manager import startup_manager
import backend.services.asistencia_service as asis_svc

if TYPE_CHECKING:
    from backend.services.empleado_service import EmpleadoService

# Scheduler global
scheduler = AsyncIOScheduler()


async def _recalcular_periodo_activo():
    """
    Recalcula la tabla `asistencias` para el período activo al arrancar.

    La tabla `asistencias` es un caché calculado: si el servidor estuvo apagado
    varios días, los días nuevos no tienen registro y la grilla muestra inasistencias
    incorrectas. Esta función corre en background (no bloquea la UI) y llama
    `procesar_dia` para cada día del período activo de RRHH.
    """
    try:
        from datetime import timedelta
        from backend.services.asistencia_service import AsistenciaService
        from backend.repositories.asistencia import AsistenciaRepository

        logger.info("🔄 [Startup] Iniciando recálculo automático del período activo...")

        # Determinar rango activo: desde el día después del último cierre hasta hoy
        hoy = datetime.now().date()
        fecha_inicio = None
        fecha_fin = hoy

        try:
            # Leer día de cierre configurable (por defecto 25 si no hay ajuste)
            try:
                row_dc = await db.fetch_one("SELECT valor FROM ajustes WHERE clave = 'dia_cierre_rrhh'")
                dia_inicio_periodo = (int(row_dc["valor"]) if row_dc else 25) + 1
            except Exception:
                dia_inicio_periodo = 26

            ultimo_cierre = await db.fetch_one(
                "SELECT fecha_fin FROM periodos_rrhh WHERE estado='cerrado' ORDER BY fecha_fin DESC LIMIT 1"
            )
            if ultimo_cierre and ultimo_cierre["fecha_fin"]:
                from datetime import date
                last_fin = datetime.strptime(ultimo_cierre["fecha_fin"], "%Y-%m-%d").date()
                fecha_inicio = last_fin + timedelta(days=1)
            else:
                # Sin cierres previos: usar inicio del mes pasado basado en dia configurado
                fecha_inicio = hoy.replace(day=1) - timedelta(days=1)
                fecha_inicio = fecha_inicio.replace(day=dia_inicio_periodo)
        except Exception:
            # Fallback usando día de inicio estándar
            fecha_inicio = hoy.replace(day=1) - timedelta(days=1)
            try:
                row_dc2 = await db.fetch_one("SELECT valor FROM ajustes WHERE clave = 'dia_cierre_rrhh'")
                d = (int(row_dc2["valor"]) if row_dc2 else 25) + 1
            except Exception:
                d = 26
            fecha_inicio = fecha_inicio.replace(day=d)

        if fecha_inicio > fecha_fin:
            logger.info("🔄 [Startup] Período activo vacío — sin días a recalcular.")
            return

        asist_repo = AsistenciaRepository(db)
        asist_service = AsistenciaService(asist_repo)

        dias_a_recalc = []
        cur = fecha_inicio
        while cur <= fecha_fin:
            dias_a_recalc.append(cur.strftime("%Y-%m-%d"))
            cur += timedelta(days=1)

        logger.info(f"🔄 [Startup] Recalculando {len(dias_a_recalc)} días ({fecha_inicio} → {fecha_fin})...")

        for fecha_str in dias_a_recalc:
            try:
                await asist_service.procesar_dia(fecha_str)
                # Pausa breve para no saturar el WAL durante el arranque
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.warning(f"⚠️ [Startup] Error recalculando {fecha_str}: {e}")

        logger.success(f"✅ [Startup] Recálculo automático completado: {len(dias_a_recalc)} días procesados.")

    except Exception as e:
        logger.error(f"❌ [Startup] Error en recálculo automático del período activo: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Context manager para lifecycle events de FastAPI.
    """
    # ============================================
    # STARTUP
    # ============================================
    startup_manager.update(5, "Iniciando servicios base...")
    logger.info("=" * 60)
    logger.info(f"🚀 Iniciando {settings.APP_NAME}")
    logger.info("=" * 60)
    
    try:
        # Garantizar instancia única del servidor para evitar bloqueos de base de datos
        from backend.core.sys_utils import ensure_single_instance
        ensure_single_instance()

        # 1. (Limpieza local eliminada — Turso Cloud es la única fuente de verdad)
        startup_manager.update(8, "Verificando conexión cloud...")


        # 2. Conectar a Database (descarga fresco desde Turso)
        startup_manager.update(10, "Conectando al motor de base de datos...")
        await db.connect()
        logger.success("Database conectada")

        # DEFINICIÓN DE TAREAS DE FONDO
        async def finish_startup():
            _t_start = datetime.now()
            try:
                # 2. Warmup
                startup_manager.update(25, "Optimizando motor de datos (Warmup)...")
                _t = datetime.now()
                try:
                    await db.fetch_all("SELECT COUNT(*) FROM empleados")
                    logger.info(f"⏱️ Warmup DB: {(datetime.now()-_t).total_seconds():.2f}s")
                except Exception as warmup_err:
                    logger.warning(f"⚠️ [Startup] Warmup DB falló (no crítico): {warmup_err}")

                # 3. Inicializar Esquemas
                startup_manager.update(40, "Verificando estructura de Seguridad...")
                _t = datetime.now()
                from backend.repositories.turno import TurnoRepository
                from backend.repositories.empleado import EmpleadoRepository
                from backend.repositories.seguridad import SeguridadRepository

                seguridad_repo = SeguridadRepository(db)
                emp_repo = EmpleadoRepository(db)
                config_repo = ConfiguracionRepository(db)
                turno_repo = TurnoRepository(db)

                await seguridad_repo.init_tables()
                logger.info(f"⏱️ seguridad init_tables: {(datetime.now()-_t).total_seconds():.2f}s")

                startup_manager.update(60, "Configurando entorno de Empleados...")
                _t = datetime.now()
                await emp_repo.create_table()
                logger.info(f"⏱️ empleado create_table: {(datetime.now()-_t).total_seconds():.2f}s")

                startup_manager.update(80, "Cargando parámetros del sistema y Feriados...")
                _t = datetime.now()
                from backend.services.calendario_service import CalendarioService
                cal_service = CalendarioService()
                
                await config_repo.init_tables()
                await turno_repo.init_tables()
                
                # Inicializar tablas de beneficios de productos propios
                from backend.repositories.productos_4 import Productos4Repository
                productos4_repo = Productos4Repository()
                await productos4_repo.init_tables()
                
                # Inicializar tablas de Portería
                from backend.repositories.porteria import PorteriaRepository
                porteria_repo = PorteriaRepository(db)
                await porteria_repo.init_tables()
                
                # Inicializar tablas de Flota Aguacol
                from backend.repositories.flota import FlotaRepository
                flota_repo = FlotaRepository(db)
                await flota_repo.init_tables()
                
                # Sincronizar/poblar tabla horas_extras con registros pendientes
                from backend.repositories.hora_extra import HoraExtraRepository
                he_repo = HoraExtraRepository(db)
                await he_repo.run_backfill()
                logger.info("✅ [Startup] Backfill de horas extras completado")

                # Migración: Auto-aprobar intercambios pendientes y reprocesar asistencia
                try:
                    pendientes = await db.fetch_all("SELECT * FROM intercambios_dias WHERE estado = 'PENDIENTE'")
                    if pendientes:
                        logger.info(f"🔄 [Startup Migration] Detectados {len(pendientes)} intercambios PENDIENTES. Actualizando a APROBADO...")
                        await db.execute("UPDATE intercambios_dias SET estado = 'APROBADO' WHERE estado = 'PENDIENTE'")
                        
                        from backend.services.asistencia_service import AsistenciaService
                        from backend.repositories.asistencia import AsistenciaRepository
                        asist_service = AsistenciaService(AsistenciaRepository(db))
                        
                        for p in pendientes:
                            emp_id = p['empleado_solicitante_id']
                            asyncio.create_task(asist_service.reprocesar_periodo_empleado(
                                empleado_id=emp_id,
                                fecha_inicio=p['fecha_origen'],
                                fecha_fin=p['fecha_origen'],
                                force=True
                            ))
                            asyncio.create_task(asist_service.reprocesar_periodo_empleado(
                                empleado_id=emp_id,
                                fecha_inicio=p['fecha_destino'],
                                fecha_fin=p['fecha_destino'],
                                force=True
                            ))
                        logger.success("✅ [Startup Migration] Auto-aprobación de intercambios completada y reprocesamientos en cola")
                except Exception as mig_err:
                    logger.warning(f"⚠️ [Startup Migration] Error al migrar intercambios: {mig_err}")
                
                # ── Rolling Window Sync de Feriados ──────────────────────────────
                # Garantiza año actual completo + 2 meses adelante.
                # Barato si ya están cargados (solo COUNT queries).
                # Solo hace upserts la primera vez que aparece un año nuevo.
                from datetime import date as _date
                rolling_result = await cal_service.sync_feriados_rolling()
                if rolling_result["synced_years"]:
                    logger.success(f"✅ [Startup] Feriados: años nuevos sincronizados {rolling_result['synced_years']}")
                else:
                    logger.info(f"☑️ [Startup] Feriados: ventana completa, sin sync necesario {rolling_result['already_ok']}")


                logger.info(f"⏱️ config+turno+calendario init_tables: {(datetime.now()-_t).total_seconds():.2f}s")

                await db.clear_schema_cache()

                # Sync ya fue completado en _connect_locked (bloqueante) — no hay bg_sync_task
                logger.info("☁️ Sync con Turso Cloud ya completado durante la conexión inicial.")

                startup_manager.update(100, "Iniciando Dashboard...", ready=True)
                total = (datetime.now() - _t_start).total_seconds()
                logger.success(f"✅ Servidor listo y optimizado (startup background: {total:.2f}s)")

                # Fase 2: Activar sync en tiempo real ahora que las tablas existen
                await db.enable_realtime_sync(interval=3)

                # 4. Iniciar Sincronización Automática
                if settings.SYNC_ENABLED:
                    logger.info(f"⏰ Iniciando Sync Scheduler (Intervalo: {settings.SYNC_INTERVAL_SECONDS}s)")
                # turso_sync eliminado — en modo Cloud directo no hay réplica que sincronizar
                    # Rolling Window de feriados — intervalo relativo al inicio del servidor.
                    # No usa hora fija: si el servidor arranca a las 2 PM, dispara cada 12h
                    # desde ese momento. Independiente de si hay usuarios conectados.
                    scheduler.add_job(
                        cal_service.sync_feriados_rolling,
                        'interval',
                        hours=12,
                        id='feriados_rolling',
                        replace_existing=True,
                        coalesce=True,
                        max_instances=1,
                        misfire_grace_time=300  # 5 min de tolerancia
                    )
                    # ── Purga semanal: logs_auditoria (retencion 12 meses) ────────────
                    async def _purgar_logs_auditoria():
                        try:
                            result = await db.execute(
                                "DELETE FROM logs_auditoria WHERE fecha < date('now', '-12 months')"
                            )
                            logger.info("🗑️ [Purga] logs_auditoria: registros > 12 meses eliminados")
                        except Exception as purge_err:
                            logger.warning(f"⚠️ [Purga] logs_auditoria falló: {purge_err}")

                    scheduler.add_job(
                        _purgar_logs_auditoria,
                        'interval',
                        weeks=1,
                        id='purga_auditoria',
                        replace_existing=True,
                        coalesce=True,
                        max_instances=1,
                    )

                    # ── Limpieza semanal: _JOB_REGISTRY en memoria ───────────────────
                    async def _limpiar_job_registry():
                        try:
                            registry = asis_svc._JOB_REGISTRY
                            completados = [
                                k for k, v in registry.items()
                                if v.get('status') in ('completed', 'error')
                            ]
                            # Conservar solo los últimos 50 completados
                            a_borrar = completados[:-50] if len(completados) > 50 else []
                            for k in a_borrar:
                                del registry[k]
                            if a_borrar:
                                logger.info(f"🗑️ [Purga] _JOB_REGISTRY: {len(a_borrar)} jobs viejos eliminados, {len(registry)} quedan en memoria")
                        except Exception as jreg_err:
                            logger.warning(f"⚠️ [Purga] _JOB_REGISTRY falló: {jreg_err}")

                    scheduler.add_job(
                        _limpiar_job_registry,
                        'interval',
                        weeks=1,
                        id='purga_job_registry',
                        replace_existing=True,
                        coalesce=True,
                        max_instances=1,
                    )

                    # ── Purga mensual: logs_raw (retención 6 meses) ──────────────────
                    # logs_raw = marcaciones CRUDAS de BioAlba (datos intermedios).
                    # Las asistencias YA calculadas viven en la tabla 'asistencias'
                    # y NO se tocan. Solo se limpian los datos brutos del biométrico.
                    async def _purgar_logs_raw():
                        try:
                            cutoff = "date('now', '-6 months')"
                            result = await db.execute(
                                f"DELETE FROM logs_raw WHERE fecha_hora < {cutoff}"
                            )
                            logger.info("🗑️ [Purga] logs_raw: marcaciones crudas > 6 meses eliminadas (asistencias preservadas)")
                        except Exception as purge_err:
                            logger.warning(f"⚠️ [Purga] logs_raw falló: {purge_err}")

                    scheduler.add_job(
                        _purgar_logs_raw,
                        'interval',
                        days=30,          # Cada 30 días
                        id='purga_logs_raw',
                        replace_existing=True,
                        coalesce=True,
                        max_instances=1,
                    )

                    scheduler.start()
                    logger.success("✅ Sync Scheduler en ejecución (turso_sync + feriados_rolling + purgas)")



            except Exception as bg_err:
                logger.error(f"❌ Error en inicio background: {bg_err}")
                startup_manager.update(100, "Inicio parcial", ready=True, error=str(bg_err))

        # FIX-CORRUPCION: finish_startup es BLOQUEANTE — el servidor NO acepta
        # requests hasta que TODAS las tablas estén creadas y sincronizadas.
        # Antes era background (create_task), lo que causaba race conditions:
        # - Requests llegaban antes de que las tablas existieran
        # - DDL (CREATE TABLE) corría en paralelo con queries de usuario
        # - El sync nativo competía con los CREATE TABLE
        await finish_startup()
        
        logger.info(f"🌐 API escuchando en {settings.API_HOST}:{settings.API_PORT}")
        logger.success("=" * 60)
        logger.success("✅ Servidor listo — todas las tablas creadas y sincronizadas")
        logger.success("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Error crítico en startup: {e}")
        startup_manager.update(0, "Error crítico", ready=False, error=str(e))
        raise
    
    # ============================================
    # YIELD - App está corriendo
    # ============================================
    yield
    
    # ============================================
    # SHUTDOWN
    # ============================================
    logger.info("=" * 60)
    logger.info("👋 Cerrando aplicación...")
    logger.info("=" * 60)
    
    try:
        # 1. Detener Sync Scheduler
        if scheduler.running:
            logger.info("⏰ Deteniendo Sync Scheduler (Immediate)...")
            scheduler.shutdown(wait=False)
            logger.success("✅ Sync Scheduler detenido")
        
        # 2. Cerrar conexión a DB
        logger.info("📊 Cerrando conexión a Database...")
        await db.disconnect()
        logger.success("✅ Conexión cerrada")
        
        # 3. Cerrar sesión HTTP BioAlba
        try:
            from backend.services.sync_service import _shared_scraper
            await _shared_scraper.close()
            logger.success("✅ Sesión BioAlba cerrada")
        except Exception as scraper_err:
            logger.warning(f"⚠️ [Shutdown] No se pudo cerrar sesión BioAlba (no crítico): {scraper_err}")
        
        # 4. Cleanup adicional
        logger.info("🧹 Cleanup completado")
        
        logger.success("=" * 60)
        logger.success("✅ Aplicación cerrada correctamente")
        logger.success("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Error durante shutdown: {e}")


async def on_startup():
    """Función de startup alternativa (compatibilidad)"""
    await db.connect()


async def on_shutdown():
    """Función de shutdown alternativa (compatibilidad)"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await db.disconnect()


async def get_empleado_service_internal(db_instance) -> "EmpleadoService":
    """Helper interno para evitar imports circulares pesados en startup"""
    from backend.repositories.empleado import EmpleadoRepository
    from backend.services.empleado_service import EmpleadoService
    from backend.repositories.configuracion import ConfiguracionRepository
    from backend.services.configuracion_service import ConfiguracionService
    from backend.services.notification_service import NotificationService
    
    emp_repository = EmpleadoRepository(db_instance)
    notification_service = NotificationService()
    config_repository = ConfiguracionRepository(db_instance)
    config_service = ConfiguracionService(config_repository, notification_service)
    await config_service.initialize()
    
    service = EmpleadoService(emp_repository, config_service, notification_service)
    await service.initialize()
    return service
