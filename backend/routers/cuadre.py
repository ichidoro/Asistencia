"""Cuadre del tramo: libro mayor de minutos y política por persona (decisión del dueño, 25-10-2026)."""
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from backend.core.database import Database, get_db
from backend.core.security import RequirePermission, SecurityContext
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.empleado import EmpleadoRepository
from backend.services.asistencia_service import AsistenciaService
from backend.services.cuadre_service import POLITICAS, CuadreService

router = APIRouter(prefix="/cuadre", tags=["Cuadre"])


class PoliticaRequest(BaseModel):
    empleado_id: int
    fecha_inicio: str
    fecha_fin: str
    politica: str                       # CERO = llevar todo a cero · PAGAR = pagar horas extra
    minutos_a_pagar: Optional[float] = None   # solo PAGAR: None = todas las que sobren
    motivo: Optional[str] = None


class ToleranciaRequest(BaseModel):
    minutos: float


def _servicio(db: Database) -> CuadreService:
    return CuadreService(AsistenciaService(AsistenciaRepository(db)))


async def _verificar_empleado(db: Database, empleado_id: int, current_user: SecurityContext):
    emp = await EmpleadoRepository(db).get_by_id(empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Empleado {empleado_id} no encontrado")
    current_user.verificar_acceso_area(emp.area, f"empleado {empleado_id}")
    return emp


@router.get("/libro/")
async def libro_empleado(
    empleado_id: int = Query(...), fecha_inicio: str = Query(...), fecha_fin: str = Query(...),
    db: Database = Depends(get_db), current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver")),
):
    await _verificar_empleado(db, empleado_id, current_user)
    try:
        return await _servicio(db).libro_empleado(empleado_id, fecha_inicio, fecha_fin)
    except Exception as e:
        logger.error(f"[Cuadre] libro de {empleado_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/libro-periodo/")
async def libro_periodo(
    fecha_inicio: str = Query(...), fecha_fin: str = Query(...), area: Optional[str] = Query(None),
    db: Database = Depends(get_db), current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver")),
):
    if not current_user.alcance_global:
        if area and area not in (current_user.areas or []):
            raise HTTPException(status_code=403, detail="No tiene permisos para el área solicitada")
        if not area and current_user.areas:
            area = current_user.areas[0]
    return await _servicio(db).libro_periodo(fecha_inicio, fecha_fin, area)


@router.post("/politica/")
async def decidir_politica(
    req: PoliticaRequest = Body(...),
    db: Database = Depends(get_db), current_user: SecurityContext = Depends(RequirePermission("marcaciones.horas_extras")),
):
    if req.politica not in POLITICAS:
        raise HTTPException(status_code=400, detail="La política debe ser CERO (llevar todo a cero) o PAGAR (pagar horas extra).")
    await _verificar_empleado(db, req.empleado_id, current_user)
    svc = _servicio(db)
    if await svc.asistencia_service.repository.check_rango_cerrado(req.fecha_inicio, req.fecha_fin, req.empleado_id):
        raise HTTPException(status_code=403, detail="El tramo está cerrado: no se puede cambiar el cuadre.")
    try:
        return await svc.decidir_politica(req.empleado_id, req.fecha_inicio, req.fecha_fin, req.politica, req.minutos_a_pagar,
                                          current_user.username, current_user.user_id, req.motivo)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.delete("/politica/")
async def quitar_politica(
    empleado_id: int = Query(...), fecha_inicio: str = Query(...), fecha_fin: str = Query(...),
    db: Database = Depends(get_db), current_user: SecurityContext = Depends(RequirePermission("marcaciones.horas_extras")),
):
    await _verificar_empleado(db, empleado_id, current_user)
    svc = _servicio(db)
    if await svc.asistencia_service.repository.check_rango_cerrado(fecha_inicio, fecha_fin, empleado_id):
        raise HTTPException(status_code=403, detail="El tramo está cerrado: no se puede cambiar el cuadre.")
    return await svc.quitar_politica(empleado_id, fecha_inicio, fecha_fin, current_user.username, current_user.user_id)


@router.get("/tolerancia/")
async def ver_tolerancia(db: Database = Depends(get_db), current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))):
    return {"minutos": await _servicio(db).repo.tolerancia_minutos()}


@router.put("/tolerancia/")
async def guardar_tolerancia(
    req: ToleranciaRequest = Body(...),
    db: Database = Depends(get_db), current_user: SecurityContext = Depends(RequirePermission("configuracion.horarios")),
):
    if req.minutos < 0 or req.minutos > 60:
        raise HTTPException(status_code=400, detail="La tolerancia va de 0 a 60 minutos.")
    svc = _servicio(db)
    await svc.repo.guardar_tolerancia(req.minutos)
    await svc._auditar(current_user.user_id, current_user.username, 'TOLERANCIA_CUADRE', {'minutos': req.minutos})
    return {"minutos": req.minutos}
