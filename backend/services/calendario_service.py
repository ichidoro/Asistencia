import holidays
import asyncio
from datetime import date
from loguru import logger
from backend.repositories.calendario import CalendarioRepository

class CalendarioService:
    def __init__(self):
        self.repo = CalendarioRepository()
        # Inicialización asíncrona de la tabla se maneja en los métodos 
        # o podemos crear una tarea, pero para simplicidad llamamos al init
        # en el primer acceso o en el constructor si fuera síncrono.
        # En este caso, lo eliminamos de aquí para evitar DDL locks en cada request.
        # asyncio.create_task(self.repo.init_db())

    async def sync_chile_holidays(self, year: int):
        await self.repo.init_db()
        """Sincroniza los feriados oficiales de Chile para un año específico"""
        logger.info(f"Sincronizando feriados de Chile para el año {year}...")
        
        # Obtener feriados de Chile usando la librería holidays
        cl_holidays = holidays.Chile(years=year)
        
        count = 0
        for dt, name in sorted(cl_holidays.items()):
            await self.repo.upsert_feriado(
                fecha=str(dt),
                descripcion=name,
                es_nacional=True
            )
            count += 1
            
        logger.success(f"✅ {count} feriados de Chile sincronizados para {year}")
        return count

    async def get_feriados(self, year: int = None):
        await self.repo.init_db()
        if not year:
            year = date.today().year
        return await self.repo.get_all_feriados(year)

    async def add_custom_holiday(self, fecha: str, descripcion: str):
        await self.repo.upsert_feriado(fecha, descripcion, es_nacional=False)
        return True

    async def delete_holiday(self, holiday_id: int):
        await self.repo.delete_feriado(holiday_id)
        return True
