from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.config import settings
from backend.core.database import Database, get_db
from backend.core.security import RequirePermission, SecurityContext
from backend.repositories.asistencia import AsistenciaRepository
from backend.services import whatsapp_resumen, whatsapp_service
from backend.services.asistencia_service import AsistenciaService

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])
PERMISO = "configuracion.seguridad"


class Prueba(BaseModel):
    telefono: str


class ResumenIn(BaseModel):
    simular: bool = True


class ResumenCron(BaseModel):
    cron_secret: str


@router.get("/estado")
async def estado(_: SecurityContext = Depends(RequirePermission(PERMISO))):
    return await whatsapp_service.estado()


@router.post("/prueba")
async def prueba(datos: Prueba, _: SecurityContext = Depends(RequirePermission(PERMISO))):
    """Manda un mensaje de prueba al teléfono indicado (para comprobar el vínculo antes de usarlo con personas)."""
    if not whatsapp_service.normalizar_telefono(datos.telefono):
        raise HTTPException(400, "Teléfono inválido: use un celular chileno (9 1234 5678).")
    if not await whatsapp_service.enviar(datos.telefono, "Prueba de avisos de Asistencia Aguacol. Si lees esto, WhatsApp quedó vinculado."):
        raise HTTPException(503, "No se pudo enviar: revise que WhatsApp esté vinculado y activo.")
    return {"ok": True}


async def _resumen(db: Database, simular: bool):
    hoy = datetime.now(ZoneInfo(settings.TIMEZONE)).date().isoformat()
    if not simular and not whatsapp_service.activo():
        raise HTTPException(503, "WhatsApp está apagado (WHATSAPP_ENABLED / token).")
    return await whatsapp_resumen.enviar_resumen(AsistenciaService(AsistenciaRepository(db)), hoy, simular)


@router.post("/resumen-semanal")
async def resumen_semanal(datos: ResumenIn, db: Database = Depends(get_db), _: SecurityContext = Depends(RequirePermission(PERMISO))):
    """Horas de Bolsa vs meta por persona. Por defecto solo SIMULA (no envía): devuelve a cuántos y una vista previa."""
    return await _resumen(db, datos.simular)


@router.post("/resumen-semanal/cron")
async def resumen_semanal_cron(datos: ResumenCron, db: Database = Depends(get_db)):
    """Lo llama cron-resumen-whatsapp.sh una vez por semana; envía de verdad."""
    if not datos.cron_secret or datos.cron_secret != settings.CRON_SECRET:
        raise HTTPException(401, "Clave inválida.")
    return await _resumen(db, False)
