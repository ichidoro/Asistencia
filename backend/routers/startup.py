from fastapi import APIRouter
from backend.core.startup_manager import startup_manager

router = APIRouter()

@router.get("/status")
async def get_startup_status():
    """Retorna el progreso actual de inicialización del sistema"""
    return startup_manager.get_status()
