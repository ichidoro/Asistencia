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
    TIMEZONE: str = "America/Santiago"
    
    # ============================================
    # API
    # ============================================
    API_HOST: str = "0.0.0.0"  # Cloud-ready: acepta conexiones externas
    API_PORT: int = int(os.environ.get("PORT", 8000))  # Cloud Run define PORT
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
    # TURSO DATABASE (ÚNICA fuente de verdad)
    # ============================================
    TURSO_DATABASE_URL: str = "libsql://aguacol-ichidoro.aws-us-east-1.turso.io"
    TURSO_AUTH_TOKEN: str = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODAwMjM1MzUsImlkIjoiMDE5ZTcxYWItOGYwMS03NWVkLWJmMDMtMDExZjk5MjE3ZWM4IiwicmlkIjoiZmE1OTYxZWYtNDEwOS00MTY1LTkwMzMtNzA4YmI5MzNiNjkwIn0.S3g__Bhy2on3tw8xzTugeFaGR-gNlz5D0Mcg-DAStaJQ_83qgLmllMZy-n5WjANJz-oTNok6h75XY1bHCmQJDg"
    TURSO_ENCRYPTION_KEY: Optional[str] = None  # Opcional
    
    # ============================================
    # CONTROL ASISTENCIA (SCRAPER)
    # ============================================
    CONTROL_ASISTENCIA_URL: str = "https://bioalba1.controlasistencia.cl"
    CONTROL_ASISTENCIA_USER: str = "aguacol"
    CONTROL_ASISTENCIA_PASSWORD: str = "123456"
    
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
    # LOGGING
    # ============================================
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_ROTATION: str = "10 MB"
    LOG_RETENTION: str = "30 days"
    
    @property
    def log_file_path(self) -> Path:
        """Ruta al archivo de log principal"""
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        return self.LOGS_DIR / "app.log"
    
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Instancia global de configuración
settings = Settings()
