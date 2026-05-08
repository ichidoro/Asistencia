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
                await config_repo.init_tables()
                await turno_repo.init_tables()
                logger.info(f"⏱️ config+turno init_tables: {(datetime.now()-_t).total_seconds():.2f}s")

                await db.clear_schema_cache()

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
