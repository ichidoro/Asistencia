"""
Main Entry Point - FastAPI Application
Sistema de Gestión de Asistencia
Python 3.13.11 - Async/Await
"""

from fastapi import FastAPI, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from loguru import logger
import sys
import uuid

# Identificador único de ejecución para cache busting agnóstico
STARTUP_ID = str(uuid.uuid4())[:8]

# Add project root to path for direct execution
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.core.config import settings
from backend.core.events import lifespan
from backend.core.database import db


# Importar routers
from backend.routers import empleados, sync, turnos, asistencia, configuracion, reportes, dashboard_api, startup, auth, seguridad, cierre
from backend.core.sys_utils import kill_process_on_port



# ============================================
# CONFIGURAR LOGGING
# ============================================

def configure_logging():
    """Configura loguru con soporte seguro para multiprocesos en Windows"""
    logger.remove()  # Remover handler por defecto
    # Console handler
    if sys.stdout is not None:
        logger.add(
            sys.stdout,
            colorize=True,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=settings.LOG_LEVEL,
            enqueue=True  # Thread-safe/Async-safe
        )

    # File handler (Simplificado para evitar WinError 32 en Windows/Reload)
    # rotation/compression DESACTIVADOS: causan conflictos de bloqueo de archivos
    # retention también desactivado: sin rotation no tiene efecto
    logger.add(
        settings.log_file_path,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=settings.LOG_LEVEL,
        enqueue=True,
        backtrace=True,
        diagnose=True
    )

configure_logging()



# ============================================
# CREAR APLICACIÓN FASTAPI
# ============================================


app = FastAPI(
    title=settings.APP_NAME,
    description="Sistema integral de gestión de asistencia con sincronización automática desde reloj control biométrico",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,  # Lifecycle events
    debug=settings.DEBUG
)


# ============================================
# MIDDLEWARE
# ============================================

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar frontend (archivos estáticos)
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")
    # Configurar Jinja2 Templates para cache busting dinámico
    templates = Jinja2Templates(directory=str(frontend_path))
    logger.info(f"Frontend montado en /static desde {frontend_path}")
else:
    templates = None
    logger.warning("Frontend no encontrado, templates no disponibles")


# Request logging middleware (opcional)
@app.middleware("http")
async def log_requests(request, call_next):
    """Log cada request"""
    logger.debug(f"Request: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.debug(f"Response: {response.status_code}")
    return response


# ============================================
# EXCEPTION HANDLERS
# ============================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handler global para excepciones no manejadas"""
    logger.error(f"Excepción no manejada: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.DEBUG else "An error occurred"
        }
    )


# ============================================
# ROUTERS
# ============================================

# Incluir router de inicio (Splash Screen)
app.include_router(startup.router, prefix="/api/startup", tags=["startup"])

# Incluir router de autenticación
app.include_router(auth.router, prefix="/api", tags=["auth"])

# Incluir router de seguridad / auditoria
app.include_router(seguridad.router, prefix="/api", tags=["seguridad"])

# Incluir router de configuración
app.include_router(configuracion.router, prefix="/api", tags=["configuracion"])

# Incluir router de empleados
app.include_router(empleados.router, prefix="/api", tags=["empleados"])

# Incluir router de sincronización
app.include_router(sync.router, prefix="/api", tags=["sync"])
app.include_router(turnos.router, prefix="/api", tags=["turnos"])
app.include_router(asistencia.router, prefix="/api", tags=["asistencia"])
app.include_router(cierre.router, prefix="/api", tags=["cierre"])
app.include_router(reportes.router, prefix="/api", tags=["reportes"])
app.include_router(dashboard_api.router, prefix="/api/dashboard", tags=["dashboard"])


# ============================================
# ENDPOINTS BÁSICOS
# ============================================

from fastapi.responses import FileResponse

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = Path(__file__).parent.parent / "frontend" / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools_json():
    """Silencia la petición automática de Chrome DevTools"""
    return {}

@app.get("/", tags=["Root"])
async def root(request: Request):
    """
    Endpoint raíz - Renderiza template con versión dinámica para cache busting
    """
    # Use the already defined frontend_path
    frontend_index = frontend_path / "index.html"
    if templates and frontend_index.exists():
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "version": settings.APP_VERSION,
                "startup_id": STARTUP_ID
            }
        )
    
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "status": "running",
        "docs": "/docs",
        "frontend": "/static/index.html"
    }

@app.get("/login.html", tags=["Root"], include_in_schema=False)
async def login_redirect(request: Request):
    """Permite el acceso a login.html desde el root"""
    return templates.TemplateResponse("login.html", {"request": request, "version": settings.APP_VERSION, "startup_id": STARTUP_ID})

@app.get("/index.html", tags=["Root"], include_in_schema=False)
async def index_redirect(request: Request):
    """Permite el acceso a index.html desde el root"""
    return templates.TemplateResponse("index.html", {"request": request, "version": settings.APP_VERSION, "startup_id": STARTUP_ID})



@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check completo del sistema
    """
    # Database health
    db_health = await db.health_check()
    
    return {
        "status": "healthy" if db_health["status"] == "healthy" else "unhealthy",
        "app": {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV
        },
        "database": db_health,
        "features": {
            "horas_extras": settings.FEATURE_HORAS_EXTRAS,
            "reportes_avanzados": settings.FEATURE_REPORTES_AVANZADOS,
            "notificaciones_email": settings.FEATURE_NOTIFICACIONES_EMAIL,
            "exportar_pdf": settings.FEATURE_EXPORTAR_PDF
        },
        "scraper": {
            "enabled": settings.SCRAPER_ENABLED,
            "interval_minutes": settings.SCRAPER_INTERVAL_MINUTES
        }
    }


@app.get("/config", tags=["Config"])
async def get_config():
    """
    Obtener configuración pública del sistema
    (Solo información no sensible)
    """
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "timezone": settings.TIMEZONE,
        "features": {
            "horas_extras": settings.FEATURE_HORAS_EXTRAS,
            "reportes_avanzados": settings.FEATURE_REPORTES_AVANZADOS,
            "notificaciones_email": settings.FEATURE_NOTIFICACIONES_EMAIL,
            "exportar_pdf": settings.FEATURE_EXPORTAR_PDF
        }
    }




@app.get("/ping", tags=["Health"])
async def ping():
    """
    Ping simple para verificar que la API responde
    """
    return {"ping": "pong"}


# ============================================
# MAIN - Para ejecutar con Python directamente
# ============================================

if __name__ == "__main__":
    import uvicorn
    import webbrowser
    import threading
    import time
    
    def open_browser():
        """Abrir navegador de forma inteligente (polling al status de inicio)"""
        host = settings.API_HOST
        if host == "0.0.0.0":
            host = "localhost"
        url = f"http://{host}:{settings.API_PORT}"
        
        # Polling hasta que el servidor esté realmente listo (max 30s)
        import urllib.request
        import json
        status_url = f"{url}/api/startup/status"
        
        for _ in range(60): # 60 * 0.5s = 30s
            try:
                req = urllib.request.Request(status_url)
                with urllib.request.urlopen(req, timeout=1) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode())
                        if data.get("ready"):
                            break
            except Exception:
                pass
            time.sleep(0.5)

        logger.info(f"--- Intentando abrir navegador en {url}...")
        try:
            webbrowser.open(url)
        except Exception as e:
            logger.error(f"No se pudo abrir el navegador: {e}")

    # Auto-Kill Zombie Processes on Port 8000 (ANTES de abrir navegador)
    # Esta lógica asegura que si reiniciamos la app, el puerto se libere primero.
    try:
        if kill_process_on_port(settings.API_PORT):
            logger.info(f"--- Puerto {settings.API_PORT} limpiado y listo.")
        else:
            logger.info(f"ℹ️ El puerto {settings.API_PORT} estaba libre.")
    except Exception as e:
        logger.warning(f"Advertencia al limpiar puertos: {e}")

    # Pequeña pausa de seguridad para dar tiempo al SO a liberar el socket completamente
    time.sleep(1)

    # Iniciar hilo para abrir navegador (DESPUÉS de liberar puerto)
    threading.Thread(target=open_browser, daemon=True).start()

    logger.info(f"--- Iniciando servidor en {settings.API_HOST}:{settings.API_PORT}")
    
    uvicorn.run(
        "backend.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD and settings.is_development,
        log_level=settings.LOG_LEVEL.lower(),

        
        access_log=True
    )
