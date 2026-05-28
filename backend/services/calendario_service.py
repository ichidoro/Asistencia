import holidays
import asyncio
from datetime import date
from loguru import logger
from backend.repositories.calendario import CalendarioRepository

# Chile tiene ~18 feriados anuales. Si hay menos de 10 en BD consideramos el año incompleto.
_MIN_FERIADOS_YEAR = 10


class CalendarioService:
    def __init__(self):
        self.repo = CalendarioRepository()

    async def sync_chile_holidays(self, year: int) -> int:
        """Sincroniza los feriados oficiales de Chile para un año específico (upsert completo)."""
        await self.repo.init_db()
        logger.info(f"📅 [Feriados] Sincronizando Chile {year}...")
        cl_holidays = holidays.Chile(years=year)
        count = 0
        for dt, name in sorted(cl_holidays.items()):
            await self.repo.upsert_feriado(
                fecha=str(dt),
                descripcion=name,
                es_nacional=True
            )
            count += 1
        logger.success(f"✅ [Feriados] {count} feriados sincronizados para {year}")
        return count

    async def sync_feriados_rolling(self) -> dict:
        """
        Rolling Window Guard — patrón usado en sistemas de nómina modernos.

        Garantiza que SIEMPRE existan feriados en BD para:
          • El año actual completo  (sincronización inicial del año, ocurre 1 vez/año)
          • El mes actual + 2 meses adelante (ventana deslizante automática)

        Costo real:
          • Año ya cargado    → solo 2-3 COUNT(*) queries → prácticamente gratis.
          • Año faltante      → 1 sync de ~18 upserts → solo la primera vez del año.

        No depende de horarios fijos. Se llama en startup y mediante scheduler
        de intervalo relativo (cada 12h desde el inicio del servidor).
        """
        await self.repo.init_db()
        today = date.today()
        synced_years: list = []
        already_ok: list = []

        # ── 1. Garantizar año actual completo ────────────────────────────────────
        current_year = today.year
        cnt = await self.repo.count_feriados_year(current_year)
        if cnt < _MIN_FERIADOS_YEAR:
            logger.info(
                f"📅 [Rolling] Año {current_year} incompleto ({cnt} registros)"
                f" → sincronizando año completo..."
            )
            await self.sync_chile_holidays(current_year)
            synced_years.append(current_year)
        else:
            logger.debug(f"☑️  [Rolling] Año {current_year} OK ({cnt} feriados en BD)")
            already_ok.append(current_year)

        # ── 2. Ventana deslizante: mes+1 y mes+2 ─────────────────────────────────
        for delta in range(1, 3):
            m = today.month + delta
            y = today.year
            while m > 12:
                m -= 12
                y += 1

            if y in synced_years or y in already_ok:
                continue  # año ya verificado en este ciclo

            cnt_y = await self.repo.count_feriados_year(y)
            if cnt_y < _MIN_FERIADOS_YEAR:
                logger.info(
                    f"📅 [Rolling] Año {y} necesario para ventana"
                    f" ({m:02d}/{y}) → sincronizando..."
                )
                await self.sync_chile_holidays(y)
                synced_years.append(y)
            else:
                logger.debug(f"☑️  [Rolling] Año {y} OK ({cnt_y} feriados en BD)")
                already_ok.append(y)

        if synced_years:
            logger.success(f"✅ [Rolling] Nuevos años sincronizados: {synced_years}")
        else:
            logger.debug(
                f"☑️  [Rolling] Ventana completa — sin sync necesario"
                f" (años cubiertos: {already_ok})"
            )

        return {
            "synced_years": synced_years,
            "already_ok": already_ok,
            "checked_today": today.isoformat(),
        }

    async def get_feriados(self, year: int = None):
        if not year:
            year = date.today().year
        return await self.repo.get_all_feriados(year)

    async def add_custom_holiday(self, fecha: str, descripcion: str):
        await self.repo.upsert_feriado(fecha, descripcion, es_nacional=False)
        return True

    async def delete_holiday(self, holiday_id: int):
        await self.repo.delete_feriado(holiday_id)
        return True
