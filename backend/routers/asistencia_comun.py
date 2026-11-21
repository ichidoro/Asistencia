"""
Lo que comparten los routers de Asistencia (etapa 6 de la auditoría): el servicio de asistencia de cada consulta.
Se movió de routers/asistencia.py sin cambios.
"""
from fastapi import Depends

from backend.core.database import Database, get_db
from backend.repositories.asistencia import AsistenciaRepository
from backend.services.asistencia_service import AsistenciaService


async def get_asistencia_service(db: Database = Depends(get_db)) -> AsistenciaService:
    repository = AsistenciaRepository(db)
    return AsistenciaService(repository)
