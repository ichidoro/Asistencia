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
            ultimo_cierre = await db.fetch_one(
                "SELECT fecha_fin FROM periodos_rrhh WHERE estado='cerrado' ORDER BY fecha_fin DESC LIMIT 1"
            )
            if ultimo_cierre and ultimo_cierre["fecha_fin"]:
                from datetime import date
                last_fin = datetime.strptime(ultimo_cierre["fecha_fin"], "%Y-%m-%d").date()
                fecha_inicio = last_fin + timedelta(days=1)
            else:
                # Sin cierres previos: usar inicio del mes pasado
                fecha_inicio = hoy.replace(day=1) - timedelta(days=1)
                fecha_inicio = fecha_inicio.replace(day=26)  # día 26 del mes anterior
        except Exception:
            # Fallback: mes anterior día 26 → hoy
            fecha_inicio = hoy.replace(day=1) - timedelta(days=1)
            fecha_inicio = fecha_inicio.replace(day=26)

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
        # 1. Limpieza PRE-CONEXIÓN: Solo archivos .corrupt_* residuales.
        # ⚠️ NUNCA borrar .db-wal / .db-shm / .db-info / .db.meta:
        #   - .db-wal contiene transacciones no checkpointed (datos reales)
        #   - .db-shm es el índice del WAL (se regenera si falta, pero borrarlo
        #     junto al WAL causa pérdida de datos)
        #   - .db.meta contiene el frame pointer de sincronización de libsql
        #   Borrar WAL/SHM desalinea el frame pointer del .meta, causando que
        #   libsql crea estar actualizado cuando no lo está → datos perdidos.
        #   libsql maneja su propio ciclo de vida WAL de forma nativa.
        startup_manager.update(8, "Verificando estado local...")
        try:
            import os, glob
            local_dir = os.path.join("data", "local_db")
            if os.path.isdir(local_dir):
                # Solo limpiar archivos de recuperación previos (.corrupt_*)
                corrupt_files = glob.glob(os.path.join(local_dir, "*.corrupt_*"))
                deleted = 0
                for f in corrupt_files:
                    try:
                        os.remove(f)
                        deleted += 1
                        logger.debug(f"Cleanup: {os.path.basename(f)}")
                    except Exception:
                        pass
                if deleted:
                    logger.info(f"Cleanup: {deleted} archivo(s) .corrupt residuales eliminados")
                else:
                    logger.debug("Cleanup: sin archivos residuales")
        except Exception as e:
            logger.warning(f"Cleanup no critico: {e}")

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

                startup_manager.update(80, "Cargando parámetros del sistema...")
                _t = datetime.now()
                from backend.repositories.calendario import CalendarioRepository
                cal_repo = CalendarioRepository()
                
                await config_repo.init_tables()
                await turno_repo.init_tables()
                await cal_repo.init_db()
                logger.info(f"⏱️ config+turno+calendario init_tables: {(datetime.now()-_t).total_seconds():.2f}s")

                await db.clear_schema_cache()

                # Esperar a que la sincronización inicial con Turso termine
                if hasattr(db, '_bg_sync_task') and not db._bg_sync_task.done():
                    startup_manager.update(90, "Sincronizando con nube (Turso Cloud)...")
                    _t_sync = datetime.now()
                    try:
                        await db._bg_sync_task
                        logger.info(f"⏱️ Sync inicial completado en: {(datetime.now()-_t_sync).total_seconds():.2f}s")
                    except Exception as e:
                        logger.warning(f"⚠️ Sync inicial abortado/fallido: {e}")

                startup_manager.update(100, "Iniciando Dashboard...", ready=True)
                total = (datetime.now() - _t_start).total_seconds()
                logger.success(f"✅ Servidor listo y optimizado (startup background: {total:.2f}s)")

                # 4. Iniciar Sincronización Automática
                if settings.SYNC_ENABLED:
                    logger.info(f"⏰ Iniciando Sync Scheduler (Intervalo: {settings.SYNC_INTERVAL_SECONDS}s)")
                    scheduler.add_job(
                        db.sync_from_cloud,
                        'interval',
                        seconds=settings.SYNC_INTERVAL_SECONDS,
                        id='turso_sync',
                        replace_existing=True,
                        coalesce=True,          # Si se acumulan disparos, ejecutar solo 1
                        max_instances=1,        # Nunca 2 syncs en paralelo
                        misfire_grace_time=60   # Tolerar hasta 60s de retraso antes de descartar
                    )
                    scheduler.start()
                    logger.success("✅ Sync Scheduler en ejecución")

            except Exception as bg_err:
                logger.error(f"❌ Error en inicio background: {bg_err}")
                startup_manager.update(100, "Inicio parcial", ready=True, error=str(bg_err))

        # Lanzar en background — el servidor queda disponible de inmediato
        # Guardar referencia: evita que el GC destruya la tarea antes de completarse
        _startup_bg_task = asyncio.create_task(finish_startup())
        logger.info("⚡ Servidor disponible — schemas iniciando en background...")
        
        logger.info(f"🌐 API escuchando en {settings.API_HOST}:{settings.API_PORT}")
        logger.success("=" * 60)
        logger.success("✅ Servidor listo (Tareas de fondo en progreso)")
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
