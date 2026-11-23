from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.config import settings
from backend.core.database import Database, get_db
from backend.core.security import RequirePermission, SecurityContext
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.whatsapp import WhatsappRepository
from backend.services import whatsapp_resumen, whatsapp_service
from backend.services.asistencia_service import AsistenciaService

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])
PERMISO = "configuracion.seguridad"


class Prueba(BaseModel):
    telefono: str


class ResumenIn(BaseModel):
    simular: bool = True
    aviso: str = "resumen_personal"


class ResumenCron(BaseModel):
    cron_secret: str


class AvisoIn(BaseModel):
    activo: bool


class PersonaDestinoIn(BaseModel):
    destino: str
    etiqueta: str = ""


class DestinoIn(BaseModel):
    destino: str
    etiqueta: str = ""


async def _repo(db: Database) -> WhatsappRepository:
    repo = WhatsappRepository(db)
    await repo.init_tables()
    return repo


def _hoy() -> str:
    return datetime.now(ZoneInfo(settings.TIMEZONE)).date().isoformat()


def _aviso_o_404(aviso: str) -> dict:
    if aviso not in whatsapp_resumen.AVISOS:
        raise HTTPException(404, "Ese aviso no existe.")
    return whatsapp_resumen.AVISOS[aviso]


@router.get("/estado")
async def estado(_: SecurityContext = Depends(RequirePermission(PERMISO))):
    return await whatsapp_service.estado()


@router.post("/desconectar")
async def desconectar(_: SecurityContext = Depends(RequirePermission(PERMISO))):
    """Corta la conexión: cierra la sesión del número y deja un QR nuevo para vincular otro (o el mismo)."""
    if not await whatsapp_service.desconectar():
        raise HTTPException(503, "No se pudo desconectar: la puerta de WhatsApp no respondió.")
    return {"ok": True}


@router.get("/grupos")
async def grupos(_: SecurityContext = Depends(RequirePermission(PERMISO))):
    """Grupos de WhatsApp en los que está el número, para asignarles avisos."""
    return {"grupos": await whatsapp_service.grupos()}


@router.get("/contactos")
async def contactos(_: SecurityContext = Depends(RequirePermission(PERMISO))):
    """Contactos agregados en el teléfono vinculado, para asignarles avisos."""
    return {"contactos": await whatsapp_service.contactos()}


@router.get("/personas")
async def personas(db: Database = Depends(get_db), _: SecurityContext = Depends(RequirePermission(PERMISO))):
    """Personas de Bolsa y a qué contacto llegaría su resumen (encontrado por nombre o fijado a mano)."""
    repo = await _repo(db)
    return {"personas": await whatsapp_resumen.listar_personas(AsistenciaService(AsistenciaRepository(db)), _hoy(), await repo.destinos_personas())}


@router.put("/personas/{emp_id}/destino")
async def fijar_persona(emp_id: int, datos: PersonaDestinoIn, db: Database = Depends(get_db), _: SecurityContext = Depends(RequirePermission(PERMISO))):
    destino = whatsapp_service.destino_valido(datos.destino)
    if not destino:
        raise HTTPException(400, "Destino inválido: elija un contacto o escriba un celular chileno (9 1234 5678).")
    await (await _repo(db)).fijar_persona(emp_id, destino, datos.etiqueta.strip()[:80])
    return {"ok": True}


@router.delete("/personas/{emp_id}/destino")
async def quitar_persona(emp_id: int, db: Database = Depends(get_db), _: SecurityContext = Depends(RequirePermission(PERMISO))):
    await (await _repo(db)).quitar_persona(emp_id)
    return {"ok": True}


@router.get("/config")
async def config(db: Database = Depends(get_db), _: SecurityContext = Depends(RequirePermission(PERMISO))):
    """Cada aviso automático: si está encendido y a qué chats va."""
    repo = await _repo(db)
    activos = await repo.avisos_activos()
    destinos = await repo.destinos()
    return {"avisos": [
        {"aviso": k, **v, "activo": activos.get(k, False), "destinos": [d for d in destinos if d["aviso"] == k]}
        for k, v in whatsapp_resumen.AVISOS.items()
    ]}


@router.put("/avisos/{aviso}")
async def encender_aviso(aviso: str, datos: AvisoIn, db: Database = Depends(get_db), _: SecurityContext = Depends(RequirePermission(PERMISO))):
    meta = _aviso_o_404(aviso)
    repo = await _repo(db)
    if datos.activo and meta["usa_chats"] and not await repo.destinos(aviso):
        raise HTTPException(400, "Asigne al menos un chat antes de encender este aviso.")
    await repo.poner_activo(aviso, datos.activo)
    return {"ok": True}


@router.post("/avisos/{aviso}/destinos")
async def agregar_destino(aviso: str, datos: DestinoIn, db: Database = Depends(get_db), _: SecurityContext = Depends(RequirePermission(PERMISO))):
    if not _aviso_o_404(aviso)["usa_chats"]:
        raise HTTPException(400, "Ese aviso va a cada persona, no a chats asignados.")
    destino = whatsapp_service.destino_valido(datos.destino)
    if not destino:
        raise HTTPException(400, "Destino inválido: elija un contacto o grupo, o escriba un celular chileno (9 1234 5678).")
    await (await _repo(db)).agregar_destino(aviso, destino, datos.etiqueta.strip()[:80])
    return {"ok": True}


@router.delete("/destinos/{destino_id}")
async def quitar_destino(destino_id: int, db: Database = Depends(get_db), _: SecurityContext = Depends(RequirePermission(PERMISO))):
    repo = await _repo(db)
    await repo.quitar_destino(destino_id)
    # Un aviso a chats sin chats no tiene a quién enviar: se apaga solo.
    activos = await repo.avisos_activos()
    for k, v in whatsapp_resumen.AVISOS.items():
        if v["usa_chats"] and activos.get(k) and not await repo.destinos(k):
            await repo.poner_activo(k, False)
    return {"ok": True}


@router.post("/prueba")
async def prueba(datos: Prueba, _: SecurityContext = Depends(RequirePermission(PERMISO))):
    """Manda un mensaje de prueba al celular o grupo indicado (para comprobar el vínculo antes de usarlo con personas)."""
    if not whatsapp_service.destino_valido(datos.telefono):
        raise HTTPException(400, "Teléfono inválido: use un celular chileno (9 1234 5678).")
    if not await whatsapp_service.enviar(datos.telefono, "Prueba de avisos de Asistencia Aguacol. Si lees esto, WhatsApp quedó vinculado."):
        raise HTTPException(503, "No se pudo enviar: revise que WhatsApp esté vinculado y activo.")
    return {"ok": True}


@router.post("/resumen-semanal")
async def resumen_semanal(datos: ResumenIn, db: Database = Depends(get_db), _: SecurityContext = Depends(RequirePermission(PERMISO))):
    """Simula (por defecto) o envía ahora un aviso. Para el aviso a chats usa los chats asignados."""
    meta = _aviso_o_404(datos.aviso)
    if not datos.simular and not whatsapp_service.activo():
        raise HTTPException(503, "WhatsApp está apagado (WHATSAPP_ENABLED / token).")
    repo = await _repo(db)
    destinos = [d["destino"] for d in await repo.destinos(datos.aviso)] if meta["usa_chats"] else None
    return await whatsapp_resumen.enviar_resumen(AsistenciaService(AsistenciaRepository(db)), _hoy(), datos.simular, datos.aviso, destinos, await repo.destinos_personas())


@router.post("/resumen-semanal/cron")
async def resumen_semanal_cron(datos: ResumenCron, db: Database = Depends(get_db)):
    """Lo llama cron-resumen-whatsapp.sh una vez por semana; envía solo los avisos que estén encendidos."""
    if not datos.cron_secret or datos.cron_secret != settings.CRON_SECRET:
        raise HTTPException(401, "Clave inválida.")
    if not whatsapp_service.activo():
        raise HTTPException(503, "WhatsApp está apagado (WHATSAPP_ENABLED / token).")
    return await whatsapp_resumen.enviar_automaticos(AsistenciaService(AsistenciaRepository(db)), await _repo(db), _hoy())
