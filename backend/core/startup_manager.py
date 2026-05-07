from typing import Dict
from pydantic import BaseModel

class StartupStatus(BaseModel):
    progress: int
    message: str
    ready: bool
    error: str = ""

class StartupManager:
    """
    Gestiona el estado de inicialización de la aplicación para informar al Splash Screen.
    """
    def __init__(self):
        self._status = StartupStatus(
            progress=0,
            message="Iniciando sistema...",
            ready=False
        )

    def update(self, progress: int, message: str, ready: bool = False, error: str = ""):
        self._status.progress = progress
        self._status.message = message
        self._status.ready = ready
        self._status.error = error

    def get_status(self) -> StartupStatus:
        return self._status

# Instancia global
startup_manager = StartupManager()
