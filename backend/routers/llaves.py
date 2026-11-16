"""
Router Llaves — Entrega y Devolución de Llaves
Gestión de llaves con control de autorizaciones por empleado
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from backend.core.database import get_db, Database
from backend.core.security import SecurityContext, get_current_user, RequirePermission
from backend.services.deshacer_porteria import permiso_deshacer, segundos_para_deshacer
from backend.repositories.llaves import LlavesRepository
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from backend.core.config import settings

def _now_chile():
    tz = ZoneInfo(settings.TIMEZONE)  # "America/Santiago"
    return datetime.now(tz).replace(tzinfo=None)
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/llaves", tags=["Llaves"])


# ============================================
# SCHEMAS
# ============================================

class LlaveCreate(BaseModel):
    nombre: str
    ubicacion: str

class LlaveUpdate(BaseModel):
    nombre: Optional[str] = None
    ubicacion: Optional[str] = None

class RegistroLlave(BaseModel):
    llave_id: int
    empleado_id: int
    tipo: str  # ENTREGA or DEVOLUCION
    observaciones: Optional[str] = ''


# ============================================
# ACCESO A DATOS
# ============================================

async def _repo(db: Database) -> LlavesRepository:
    """El repositorio de llaves con sus tablas aseguradas (las consultas viven en repositories/llaves.py)."""
    repo = LlavesRepository(db)
    await repo.init_tables()
    return repo


# ============================================
# ENDPOINTS - MAESTRO DE LLAVES
# ============================================

@router.get("/maestro/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def listar_llaves(db: Database = Depends(get_db)):
    """Listar todas las llaves activas"""
    repo = await _repo(db)
    rows = await repo.listar_activas()
    return [{"id": r["id"], "nombre": r["nombre"], "ubicacion": r["ubicacion"]} for r in rows]


@router.post("/maestro/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def crear_llave(data: LlaveCreate, db: Database = Depends(get_db)):
    """Crear una nueva llave"""
    repo = await _repo(db)
    await repo.crear(data.nombre, data.ubicacion)
    return {"ok": True, "message": f"Llave '{data.nombre}' creada"}


@router.put("/maestro/{llave_id}/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def actualizar_llave(llave_id: int, data: LlaveUpdate, db: Database = Depends(get_db)):
    """Actualizar datos de una llave"""
    repo = await _repo(db)
    if not await repo.actualizar(llave_id, data.nombre, data.ubicacion):
        raise HTTPException(400, "Nada que actualizar")
    return {"ok": True}


@router.delete("/maestro/{llave_id}/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def eliminar_llave(llave_id: int, db: Database = Depends(get_db)):
    """Desactivar una llave (soft delete)"""
    repo = await _repo(db)
    await repo.desactivar(llave_id)
    return {"ok": True}


# ============================================
# ENDPOINTS - EMPLEADOS AUTORIZADOS
# ============================================

@router.get("/autorizados/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def listar_autorizados(
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user)
):
    """Listar empleados autorizados para llaves, filtrados por áreas del usuario"""
    rows = await LlavesRepository(db).listar_autorizados(current_user.get_areas_filter())
    return [
        {
            "id": r["id"],
            "rut": r["rut"],
            "nombre": " ".join(p for p in (r["apellido_paterno"], r["apellido_materno"], r["nombre"]) if p),
            "area": r["area_nombre"]
        }
        for r in rows
    ]


# ============================================
# ENDPOINTS - ESTADO Y REGISTRO
# ============================================

@router.get("/estado/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def estado_llaves(db: Database = Depends(get_db)):
    """Estado actual de todas las llaves (disponible/entregada)"""
    repo = await _repo(db)
    llaves = await repo.listar_activas()
    resultado = []
    for ll in llaves:
        # Buscar último registro para esta llave
        ultimo = await repo.get_ultimo_movimiento(ll["id"])
        estado = "DISPONIBLE"
        entregada_a = None
        entregada_hora = None
        if ultimo and ultimo["tipo"] == "ENTREGA":
            estado = "ENTREGADA"
            entregada_a = {
                "nombre": ultimo["empleado_nombre"],
                "rut": ultimo["empleado_rut"],
                "id": ultimo["empleado_id"]
            }
            entregada_hora = f"{ultimo['fecha']} {ultimo['hora']}"
        resultado.append({
            "id": ll["id"],
            "nombre": ll["nombre"],
            "ubicacion": ll["ubicacion"],
            "estado": estado,
            "entregada_a": entregada_a,
            "entregada_hora": entregada_hora
        })
    total = len(resultado)
    disponibles = sum(1 for r in resultado if r["estado"] == "DISPONIBLE")
    return {
        "llaves": resultado,
        "total": total,
        "disponibles": disponibles,
        "fuera": total - disponibles
    }


@router.post("/registrar/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def registrar_movimiento(
    data: RegistroLlave,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user)
):
    """Registrar entrega o devolución de una llave"""
    repo = await _repo(db)

    # Validar que la llave existe
    llave = await repo.get_activa(data.llave_id)
    if not llave:
        raise HTTPException(404, "Llave no encontrada")

    # Validar que el empleado está autorizado
    emp = await repo.get_empleado_autorizado(data.empleado_id)
    if not emp:
        raise HTTPException(403, "Empleado no autorizado para llaves")

    # Validar consistencia lógica
    ultimo = await repo.get_ultimo_tipo(data.llave_id)

    if data.tipo == "ENTREGA" and ultimo and ultimo["tipo"] == "ENTREGA":
        raise HTTPException(400, "Esta llave ya está entregada. Debe devolverse primero.")
    if data.tipo == "DEVOLUCION" and (not ultimo or ultimo["tipo"] == "DEVOLUCION"):
        raise HTTPException(400, "Esta llave ya está disponible. No hay nada que devolver.")

    now = _now_chile()
    movimiento_id = await repo.registrar((
        data.llave_id, data.empleado_id, data.tipo,
        now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S'),
        current_user.user_id, current_user.username,
        data.observaciones or ''
    ))
    return {"ok": True, "message": f"Llave '{llave['nombre']}' - {data.tipo} registrada",
            "deshacer": permiso_deshacer("llave", movimiento_id, await segundos_para_deshacer(db))}


# ============================================
# ENDPOINTS - HISTORIAL
# ============================================

@router.get("/historial/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def historial_llaves(
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    llave_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db)
):
    """Historial paginado de movimientos de llaves"""
    repo = await _repo(db)
    total = await repo.contar_historial(fecha_desde, fecha_hasta, llave_id)

    offset = (page - 1) * page_size
    rows = await repo.get_historial(fecha_desde, fecha_hasta, llave_id, page_size, offset)

    registros = [
        {
            "id": r["id"],
            "llave": r["llave_nombre"],
            "ubicacion": r["ubicacion"],
            "empleado": r["empleado_nombre"],
            "rut": r["empleado_rut"],
            "tipo": r["tipo"],
            "fecha": r["fecha"],
            "hora": r["hora"],
            "guardia": r["registrado_por_nombre"],
            "observaciones": r["observaciones"]
        }
        for r in rows
    ]
    return {
        "registros": registros,
        "total": total,
        "page": page,
        "pages": (total + page_size - 1) // page_size
    }
