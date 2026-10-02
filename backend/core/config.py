"""
Configuración del Sistema - Pydantic Settings
Carga variables de entorno desde .env de forma type-safe
"""

from pydantic import model_validator
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
    TIMEZONE: str = "America/Santiago"
    
    # ============================================
    # API
    # ============================================
    API_HOST: str = "0.0.0.0"
    API_PORT: int = int(os.environ.get("PORT", os.environ.get("APP_PORT", 8000)))
    API_RELOAD: bool = True  # Solo en development
    
    # CORS (Permitir todos los puertos locales para el frontend de reclamos)
    CORS_ORIGINS: List[str] = [
        "*",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8099",
        "http://127.0.0.1:8099",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500"
    ]
    
    # ============================================
    # POSTGRESQL (ÚNICA fuente de verdad)
    # ============================================
    DATABASE_URL: str = ""  # postgresql://user:pass@host:5432/db  (obligatorio, viene del .env)
    DB_POOL_MAX: int = 15

    # ============================================
    # CONTROL ASISTENCIA (SCRAPER)
    # ============================================
    CONTROL_ASISTENCIA_URL: str = "https://bioalba1.controlasistencia.cl"
    CONTROL_ASISTENCIA_USER: str = "aguacol"
    CONTROL_ASISTENCIA_PASSWORD: str = ""   # definir en .env

    # EasyTime Pro (desde 01-10-2026 los relojes reportan aquí en vez de BioAlba).
    # Si EASYTIME_URL y EASYTIME_PASSWORD están definidos en .env, las marcaciones se leen de EasyTime.
    EASYTIME_URL: str = ""
    EASYTIME_USER: str = ""
    EASYTIME_PASSWORD: str = ""
    # Correos (separados por coma) que reciben las alertas de la sincronización. Si está vacío, SMTP_USER.
    ALERT_EMAIL_TO: str = ""
    
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
    DOWNLOADS_DIR: Path = _WRITABLE_DIR / "downloads"
    LOGS_DIR: Path = _WRITABLE_DIR / "logs"
    TEMP_DIR: Path = _WRITABLE_DIR / "temp"
    
    # ============================================
    # SECURITY & AUTH
    # ============================================
    SECRET_KEY: str = ""   # OBLIGATORIO en .env (openssl rand -hex 32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 días
    CRON_SECRET: str = ""   # definir en .env
    
    # ============================================
    # WEBSOCKET
    # ============================================
    WS_PING_INTERVAL: int = 30
    WS_PING_TIMEOUT: int = 10
    WS_MAX_CONNECTIONS: int = 100
    
    # ============================================
    # TAREAS PROGRAMADAS
    # ============================================
    SYNC_ENABLED: bool = True
    SYNC_INTERVAL_SECONDS: int = 120
    BACKUP_ENABLED: bool = True
    BACKUP_INTERVAL_HOURS: int = 24
    BACKUP_RETENTION_DAYS: int = 30
    
    # ============================================
    # NOTIFICACIONES EMAIL
    # ============================================
    FEATURE_NOTIFICACIONES_EMAIL: bool = True
    SMTP_SERVER: Optional[str] = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = "operaciones.aguacol.spa@gmail.com"
    SMTP_PASSWORD: Optional[str] = None   # definir en .env
    EMAIL_FROM: Optional[str] = "operaciones.aguacol.spa@gmail.com"
    
    # ============================================
    # FEATURES & EXPORT
    # ============================================
    FEATURE_HORAS_EXTRAS: bool = True
    FEATURE_REPORTES_AVANZADOS: bool = True
    FEATURE_EXPORTAR_PDF: bool = True
    TESTING: bool = False
    
    # ============================================
    # GOOGLE DRIVE & PORTERIA
    # ============================================
    GOOGLE_DRIVE_FOLDER_ID: Optional[str] = None
    GOOGLE_APPLICATION_CREDENTIALS_JSON_PATH: Optional[str] = None
    
    # ============================================
    # LOGGING
    # ============================================
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_ROTATION: str = "10 MB"
    LOG_RETENTION: str = "30 days"
    LOG_FILE: str = "app.log"
    
    @property
    def db_url(self) -> str:
        return self.DATABASE_URL

    @property
    def log_file_path(self) -> Path:
        """Ruta al archivo de log principal"""
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        return self.LOGS_DIR / self.LOG_FILE
        
    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"
        
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"
        
    @property
    def is_cloud(self) -> bool:
        return bool(os.environ.get("K_SERVICE"))
    
    @model_validator(mode="after")
    def _exigir_secretos(self):
        if not self.SECRET_KEY or len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY es obligatorio en .env (>= 32 caracteres). Generar con: openssl rand -hex 32")
        return self

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Instancia global de configuración
settings = Settings()
