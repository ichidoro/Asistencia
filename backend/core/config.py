"""
Configuración del Sistema - Pydantic Settings
Carga variables de entorno desde .env de forma type-safe
"""

from pydantic_settings import BaseSettings, SettingsConfigDict # touch trigger reload
from typing import List, Optional
from pathlib import Path
import os

# ============================================
# RUTAS DINÁMICAS (Entorno de Desarrollo)
# ============================================
_EXEC_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = str(_EXEC_DIR / ".env")
_WRITABLE_DIR = _EXEC_DIR



class Settings(BaseSettings):
    """
    Configuración de la aplicación usando Pydantic Settings.
    Lee automáticamente desde archivo .env
    """
    
    # ============================================
    # APLICACIÓN
    # ============================================
    APP_NAME: str = "Sistema de Gestión de Asistencia"
    APP_VERSION: str = "4.7.2"
    APP_ENV: str = "development"  # development, production, testing
    DEBUG: bool = True
    
    # ============================================
    # API
    # ============================================
    API_HOST: str = "0.0.0.0"  # Cloud-ready: acepta conexiones externas
    API_PORT: int = int(os.environ.get("PORT", 8000))  # Cloud Run define PORT
    API_RELOAD: bool = True  # Solo en development
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",  # Si usas React u otro frontend
        "https://*.run.app",     # Google Cloud Run
    ]
    
    # ============================================
    # TURSO DATABASE
    # ============================================
    TURSO_DATABASE_URL: str
    TURSO_AUTH_TOKEN: str
    
    # Embedded Replica (local)
    LOCAL_DB_PATH: str = str(_WRITABLE_DIR / "data" / "local_db" / "asistencia_local.db")
    
    # Sync Configuration
    TURSO_SYNC_URL: Optional[str] = None  # Si es diferente al DATABASE_URL
    TURSO_SYNC_INTERVAL: int = 60  # Segundos entre syncs automáticos
    TURSO_ENCRYPTION_KEY: Optional[str] = None  # Opcional
    
    # ============================================
    # CONTROL ASISTENCIA (SCRAPER)
    # ============================================
    CONTROL_ASISTENCIA_URL: str = "https://bioalba1.controlasistencia.cl"
    CONTROL_ASISTENCIA_USER: str
    CONTROL_ASISTENCIA_PASSWORD: str
    
    # Scraping Configuration
    SCRAPER_ENABLED: bool = True
    SCRAPER_INTERVAL_MINUTES: int = 60  # Cada cuántos minutos ejecutar
    SCRAPER_REQUEST_DELAY: int = 2  # Segundos entre requests
    SCRAPER_MAX_RETRIES: int = 3
    SCRAPER_TIMEOUT: int = 30  # Segundos
    
    SCRAPER_EMPLEADOS_ACTIVE: bool = True
    SCRAPER_MARCACIONES_ACTIVE: bool = True
    
    # ============================================
    # PATHS
    # ============================================
    BASE_DIR: Path = _EXEC_DIR
    DATA_DIR: Path = _WRITABLE_DIR / "data"
    DOWNLOADS_DIR: Path = DATA_DIR / "downloads"
    LOGS_DIR: Path = _WRITABLE_DIR / "logs"
    TEMP_DIR: Path = _WRITABLE_DIR / "temp"
    
    # ============================================
    # LOGGING
    # ============================================
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_FORMAT: str = "json"  # json, text
    LOG_FILE: str = "app.log"
    
    # ============================================
    # WEBSOCKET
    # ============================================
    WS_PING_INTERVAL: int = 30  # Segundos
    WS_PING_TIMEOUT: int = 10   # Segundos
    WS_MAX_CONNECTIONS: int = 100
    
    # ============================================
    # SECURITY
    # ============================================
    SECRET_KEY: str = "change-this-in-production-to-a-random-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # ============================================
    # TAREAS PROGRAMADAS
    # ============================================
    SYNC_ENABLED: bool = True
    SYNC_INTERVAL_SECONDS: int = 120  # Sync cada 2 min — único actor. Sin fire-and-forget por-write (evita mutex contention en libsql).
    
    BACKUP_ENABLED: bool = True
    BACKUP_INTERVAL_HOURS: int = 24
    BACKUP_RETENTION_DAYS: int = 30
    
    # ============================================
    # NOTIFICACIONES (Opcional)
    # ============================================
    SMTP_SERVER: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM: Optional[str] = None
    
    # ============================================
    # FEATURES FLAGS
    # ============================================
    FEATURE_HORAS_EXTRAS: bool = True
    FEATURE_REPORTES_AVANZADOS: bool = True
    FEATURE_NOTIFICACIONES_EMAIL: bool = False
    FEATURE_EXPORTAR_PDF: bool = True
    
    # ============================================
    # TIMEZONE
    # ============================================
    TIMEZONE: str = "America/Santiago"  # Chile
    
    # ============================================
    # TESTING
    # ============================================
    TESTING: bool = False
    
    # ============================================
    # PYDANTIC CONFIG
    # ============================================
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Ignorar variables extra del .env
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Crear directorios si no existen
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Si TURSO_SYNC_URL no está definido, usar TURSO_DATABASE_URL
        if not self.TURSO_SYNC_URL:
            self.TURSO_SYNC_URL = self.TURSO_DATABASE_URL
    
    @property
    def db_url(self) -> str:
        """URL para conectar a Turso"""
        return self.TURSO_DATABASE_URL
    
    @property
    def local_db_path_str(self) -> str:
        """Path de la DB local como string"""
        return str(self.LOCAL_DB_PATH)
    
    @property
    def log_file_path(self) -> Path:
        """Path completo del archivo de log"""
        return self.LOGS_DIR / self.LOG_FILE
    
    @property
    def is_development(self) -> bool:
        """Check si está en development"""
        return self.APP_ENV == "development"
    
    @property
    def is_production(self) -> bool:
        """Check si está en production"""
        return self.APP_ENV == "production"
    
    @property
    def is_testing(self) -> bool:
        """Check si está en testing"""
        return self.TESTING or self.APP_ENV == "testing"
    
    @property
    def is_cloud(self) -> bool:
        """Detecta si corre en Google Cloud Run (K_SERVICE es auto-set por Cloud Run)"""
        return bool(os.environ.get("K_SERVICE"))


# Instancia global de settings
settings = Settings()


# Helper para debug
if __name__ == "__main__":
    from loguru import logger
    logger.info("🔧 Configuración del Sistema")
    logger.info("=" * 50)
    logger.info(f"App: {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.APP_ENV}")
    logger.info(f"API: {settings.API_HOST}:{settings.API_PORT}")
    logger.info(f"Turso URL: {settings.TURSO_DATABASE_URL}")
    logger.info(f"Local DB: {settings.LOCAL_DB_PATH}")
    logger.info(f"Scraper: {'Enabled' if settings.SCRAPER_ENABLED else 'Disabled'}")
    logger.info(f"Base Dir: {settings.BASE_DIR}")
    logger.info("=" * 50)
