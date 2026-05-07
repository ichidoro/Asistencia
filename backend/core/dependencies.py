"""
Dependencias internas para el ciclo de vida de la aplicación
Evita importaciones circulares en el arranque (lifespan)
"""

from backend.repositories.empleado import EmpleadoRepository
from backend.services.empleado_service import EmpleadoService
from backend.repositories.configuracion import ConfiguracionRepository
from backend.services.configuracion_service import ConfiguracionService
from backend.repositories.turno import TurnoRepository
from backend.services.turno_service import TurnoService

async def get_empleado_service_internal(db):
    """Retorna una instancia de EmpleadoService inicializada"""
    repo = EmpleadoRepository(db)
    service = EmpleadoService(repo)
    await service.initialize()
    return service

async def get_configuracion_service_internal(db):
    """Retorna una instancia de ConfiguracionService inicializada"""
    repo = ConfiguracionRepository(db)
    service = ConfiguracionService(repo)
    await service.initialize()
    return service

async def get_turno_service_internal(db):
    """Retorna una instancia de TurnoService inicializada"""
    repo = TurnoRepository(db)
    service = TurnoService(repo)
    await service.initialize()
    return service
