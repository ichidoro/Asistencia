from typing import Any
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.config import settings
from backend.core.database import Database, get_db
from backend.core.security import RequirePermission, SecurityContext
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.whatsapp import WhatsappRepository
from backend.services import alerta_velocidad, whatsapp_resumen, whatsapp_service
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


class FiltrosIn(BaseModel):
    areas: list[str] = []
    cargos: list[str] = []


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


async def _apagar_sin_chats(repo: Any) -> None:
    """Un aviso a chats sin nadie asignado no tiene a quién enviar: se apaga solo."""
    activos = await repo.avisos_activos()
    for k, v in whatsapp_resumen.AVISOS.items():
        if v["usa_chats"] and activos.get(k) and not await repo.destinos(k):
            await repo.poner_activo(k, False)


async def _revisar_velocidad(db: Database, repo: Any, destinos: list, simular: bool) -> dict:
    """Alerta de velocidad: jefatura (chats asignados) y el propio chofer (su contacto, igual que en el resumen personal)."""
    from backend.repositories.empleado import EmpleadoRepository
    choferes = [dict(r) for r in await EmpleadoRepository(db).get_choferes_logistica_tradicional()]
    return await alerta_velocidad.revisar(destinos, simular, choferes, await repo.destinos_personas())


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
async def personas(aviso: str = "resumen_personal", db: Database = Depends(get_db), _: SecurityContext = Depends(RequirePermission(PERMISO))):
    """Personas y a qué contacto llegaría el aviso (encontrado por nombre o fijado a mano). En un aviso a chats son todas las personas activas, con `recibe`."""
    meta = _aviso_o_404(aviso)
    repo = await _repo(db)
    filtro = (await repo.filtros(aviso)).get(aviso)
    if meta["usa_chats"]:
        return {"personas": await whatsapp_resumen.listar_destinatarios(db, repo, aviso, filtro)}
    return {"personas": await whatsapp_resumen.listar_personas(AsistenciaService(AsistenciaRepository(db)), _hoy(), await repo.destinos_personas(), filtro)}


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
    """Cada aviso automático: si está encendido, a qué chats va y con qué filtro de área y cargo."""
    repo = await _repo(db)
    activos = await repo.avisos_activos()
    destinos = await repo.destinos()
    filtros = await repo.filtros()
    estado = {}
    if any(str(d["destino"]).startswith(whatsapp_resumen.PREFIJO_PERSONA) for d in destinos):
        for x in await whatsapp_resumen.resolver_destinos_chat(db, [dict(d) for d in destinos], await repo.destinos_personas()):
            estado[x["id"]] = {"estado": x["estado"], "contacto": x["contacto"]}
    return {"opciones": await repo.opciones_filtro(), "avisos": [
        {"aviso": k, **v, "activo": activos.get(k, False), "destinos": [{**d, **estado.get(d["id"], {})} for d in destinos if d["aviso"] == k], "filtros": filtros.get(k, {"areas": [], "cargos": []})}
        for k, v in whatsapp_resumen.AVISOS.items()
    ]}


@router.put("/avisos/{aviso}/filtros")
async def fijar_filtros(aviso: str, datos: FiltrosIn, db: Database = Depends(get_db), _: SecurityContext = Depends(RequirePermission(PERMISO))):
    """A qué áreas y cargos se limita el aviso (vacío = todos)."""
    _aviso_o_404(aviso)
    await (await _repo(db)).fijar_filtros(aviso, datos.areas[:100], datos.cargos[:100])
    return {"ok": True}


@router.put("/avisos/{aviso}")
async def encender_aviso(aviso: str, datos: AvisoIn, db: Database = Depends(get_db), _: SecurityContext = Depends(RequirePermission(PERMISO))):
    meta = _aviso_o_404(aviso)
    repo = await _repo(db)
    if datos.activo and meta["usa_chats"] and not await repo.destinos(aviso):
        raise HTTPException(400, "Antes de encenderlo, abra «Revisar y asignar contacto por persona» y marque con «Recibe» a quien lo recibirá.")
    await repo.poner_activo(aviso, datos.activo)
    return {"ok": True}


@router.post("/avisos/{aviso}/personas/{emp_id}")
async def agregar_persona_destino(aviso: str, emp_id: int, db: Database = Depends(get_db), _: SecurityContext = Depends(RequirePermission(PERMISO))):
    """Asigna a un aviso de chats una persona de Asistencia: su WhatsApp se resuelve al enviar, como en el resumen personal."""
    if not _aviso_o_404(aviso)["usa_chats"]:
        raise HTTPException(400, "Ese aviso va a cada persona, no a chats asignados.")
    repo = await _repo(db)
    f = await repo.empleado(emp_id)
    if not f:
        raise HTTPException(404, "Esa persona no existe.")
    if whatsapp_resumen.AVISOS[aviso].get("solo_art22") and emp_id not in {int(x["id"]) for x in await repo.empleados_activos(solo_art22=True)}:
        raise HTTPException(400, "Este aviso solo se asigna a personal de Artículo 22.")
    nombre = " ".join(str(f[k] or "").strip() for k in ("nombre", "apellido_paterno", "apellido_materno") if str(f[k] or "").strip())
    await repo.agregar_destino(aviso, whatsapp_resumen.PREFIJO_PERSONA + str(emp_id), nombre[:80])
    return {"ok": True}


@router.delete("/avisos/{aviso}/personas/{emp_id}")
async def quitar_persona_destino(aviso: str, emp_id: int, db: Database = Depends(get_db), _: SecurityContext = Depends(RequirePermission(PERMISO))):
    _aviso_o_404(aviso)
    repo = await _repo(db)
    await repo.quitar_destino_de(aviso, whatsapp_resumen.PREFIJO_PERSONA + str(emp_id))
    await _apagar_sin_chats(repo)
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
    await _apagar_sin_chats(repo)
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
    destinos = await whatsapp_resumen.destinos_chat(db, repo, datos.aviso) if meta["usa_chats"] else None
    if meta.get("tiempo_real"):
        return await _revisar_velocidad(db, repo, destinos or [], datos.simular)
    return await whatsapp_resumen.enviar_resumen(AsistenciaService(AsistenciaRepository(db)), _hoy(), datos.simular, datos.aviso, destinos, await repo.destinos_personas(),
                                                 (await repo.filtros(datos.aviso)).get(datos.aviso))


@router.post("/resumen-semanal/cron")
async def resumen_semanal_cron(datos: ResumenCron, db: Database = Depends(get_db)):
    """Lo llama cron-resumen-whatsapp.sh una vez por semana; envía solo los avisos que estén encendidos."""
    if not datos.cron_secret or datos.cron_secret != settings.CRON_SECRET:
        raise HTTPException(401, "Clave inválida.")
    if not whatsapp_service.activo():
        raise HTTPException(503, "WhatsApp está apagado (WHATSAPP_ENABLED / token).")
    return await whatsapp_resumen.enviar_automaticos(AsistenciaService(AsistenciaRepository(db)), await _repo(db), _hoy())


@router.post("/alerta-velocidad/cron")
async def alerta_velocidad_cron(datos: ResumenCron, db: Database = Depends(get_db)):
    """Lo llama cron-alerta-velocidad.sh cada minuto; solo actúa si el aviso está encendido y tiene chats."""
    if not datos.cron_secret or datos.cron_secret != settings.CRON_SECRET:
        raise HTTPException(401, "Clave inválida.")
    if not whatsapp_service.activo():
        raise HTTPException(503, "WhatsApp está apagado (WHATSAPP_ENABLED / token).")
    repo = await _repo(db)
    if not (await repo.avisos_activos()).get("exceso_velocidad"):
        return {"activo": False}
    return await _revisar_velocidad(db, repo, await whatsapp_resumen.destinos_chat(db, repo, "exceso_velocidad"), False)
