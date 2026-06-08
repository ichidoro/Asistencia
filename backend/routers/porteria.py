from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query
from typing import List, Dict, Any, Optional
from loguru import logger

from backend.core.database import get_db, Database
from backend.core.security import SecurityContext, RequirePermission, RequireAnyPermission, get_current_user
from backend.repositories.porteria import PorteriaRepository
from backend.services.google_drive import GoogleDriveService
from backend.schemas.porteria import (
    UbicacionCreate,
    UbicacionResponse,
    CatalogFindingCreate,
    CatalogFindingResponse,
    RondaRecordCreate,
    RondaRecordResponse,
    SyncBatchRequest
)

router = APIRouter(
    prefix="/porteria",
    tags=["Portería"]
)

# ============================================
# DEPENDENCIAS INTERNAS
# ============================================
async def get_porteria_repository(db: Database = Depends(get_db)) -> PorteriaRepository:
    return PorteriaRepository(db)


# ============================================
# ENDPOINTS: CATÁLOGO DE HALLAZGOS (ANOMALÍAS)
# ============================================

@router.get("/catalogo-hallazgos/", response_model=List[CatalogFindingResponse])
async def get_catalogo_hallazgos(
    all: bool = Query(False, description="Si es True, incluye hallazgos inactivos"),
    repo: PorteriaRepository = Depends(get_porteria_repository),
    current_user: SecurityContext = Depends(get_current_user)
):
    """Obtiene la lista de anomalías/hallazgos configurados en el catálogo."""
    return await repo.get_all_hallazgos(incluir_inactivos=all)


@router.post("/catalogo-hallazgos/", response_model=Dict[str, Any], status_code=201)
async def create_catalogo_hallazgo(
    finding: CatalogFindingCreate,
    repo: PorteriaRepository = Depends(get_porteria_repository),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.editar", "porteria.editar"]))
):
    """Crea una nueva anomalía en el catálogo."""
    nombre_normalizado = finding.nombre.strip()
    if not nombre_normalizado:
        raise HTTPException(status_code=400, detail="El nombre del hallazgo no puede estar vacío.")
    
    # Verificar si ya existe
    existente = await repo.db.fetch_one(
        "SELECT id FROM porteria_catalogo_hallazgos WHERE LOWER(nombre) = LOWER(?)",
        (nombre_normalizado,)
    )
    if existente:
        raise HTTPException(status_code=400, detail=f"El hallazgo '{nombre_normalizado}' ya existe en el catálogo.")

    new_id = await repo.create_hallazgo(nombre_normalizado)
    
    # Registrar auditoría
    await repo.db.execute(
        "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
        (
            current_user.user_id,
            current_user.username,
            "CREATE_PORTERIA_HALLAZGO_CATALOGO",
            "Porteria",
            f"Creado hallazgo en catálogo: '{nombre_normalizado}' (ID: {new_id})."
        )
    )
    return {"id": new_id, "nombre": nombre_normalizado, "message": "Hallazgo del catálogo creado exitosamente"}


@router.put("/catalogo-hallazgos/{hallazgo_id}/", response_model=Dict[str, Any])
async def update_catalogo_hallazgo(
    hallazgo_id: int,
    finding: CatalogFindingCreate,
    repo: PorteriaRepository = Depends(get_porteria_repository),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.editar", "porteria.editar"]))
):
    """Actualiza una anomalía existente del catálogo."""
    nombre_normalizado = finding.nombre.strip()
    if not nombre_normalizado:
        raise HTTPException(status_code=400, detail="El nombre del hallazgo no puede estar vacío.")

    # Verificar si el registro existe
    db_finding = await repo.get_hallazgo_by_id(hallazgo_id)
    if not db_finding:
        raise HTTPException(status_code=404, detail="Hallazgo del catálogo no encontrado")

    # Verificar si el nuevo nombre colisiona con otro registro
    colision = await repo.db.fetch_one(
        "SELECT id FROM porteria_catalogo_hallazgos WHERE LOWER(nombre) = LOWER(?) AND id != ?",
        (nombre_normalizado, hallazgo_id)
    )
    if colision:
        raise HTTPException(status_code=400, detail=f"Ya existe otro hallazgo con el nombre '{nombre_normalizado}'.")

    success = await repo.update_hallazgo(hallazgo_id, nombre_normalizado, finding.activo)
    if not success:
        raise HTTPException(status_code=500, detail="No se pudo actualizar el hallazgo en el catálogo")

    # Registrar auditoría
    await repo.db.execute(
        "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
        (
            current_user.user_id,
            current_user.username,
            "UPDATE_PORTERIA_HALLAZGO_CATALOGO",
            "Porteria",
            f"Actualizado hallazgo #{hallazgo_id}: nombre='{nombre_normalizado}', activo={finding.activo}."
        )
    )
    return {"id": hallazgo_id, "message": "Hallazgo del catálogo actualizado correctamente"}


@router.delete("/catalogo-hallazgos/{hallazgo_id}/", status_code=204)
async def delete_catalogo_hallazgo(
    hallazgo_id: int,
    repo: PorteriaRepository = Depends(get_porteria_repository),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.editar", "porteria.editar"]))
):
    """Elimina o desactiva una anomalía del catálogo (si ya se encuentra en uso en alguna ronda, se desactiva automáticamente)."""
    db_finding = await repo.get_hallazgo_by_id(hallazgo_id)
    if not db_finding:
        raise HTTPException(status_code=404, detail="Hallazgo del catálogo no encontrado")

    success = await repo.delete_finding(hallazgo_id) if hasattr(repo, 'delete_finding') else await repo.delete_hallazgo(hallazgo_id)
    if not success:
         raise HTTPException(status_code=500, detail="Error al eliminar el hallazgo del catálogo")

    # Registrar auditoría
    await repo.db.execute(
        "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
        (
            current_user.user_id,
            current_user.username,
            "DELETE_PORTERIA_HALLAZGO_CATALOGO",
            "Porteria",
            f"Eliminado/Desactivado hallazgo #{hallazgo_id} ('{db_finding['nombre']}')."
        )
    )
    return


# ============================================
# ENDPOINTS: UBICACIONES (PUNTOS DE CONTROL QR)
# ============================================

@router.get("/ubicaciones/", response_model=List[UbicacionResponse])
async def get_ubicaciones(
    all: bool = Query(False, description="Si es True, incluye ubicaciones inactivas"),
    repo: PorteriaRepository = Depends(get_porteria_repository),
    current_user: SecurityContext = Depends(get_current_user)
):
    """Obtiene la lista de ubicaciones configuradas para las rondas."""
    return await repo.get_all_ubicaciones(incluir_inactivos=all)


@router.post("/ubicaciones/", response_model=Dict[str, Any], status_code=201)
async def create_ubicacion(
    ubicacion: UbicacionCreate,
    repo: PorteriaRepository = Depends(get_porteria_repository),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.editar", "porteria.editar"]))
):
    """Crea una nueva ubicación de control."""
    nombre_normalizado = ubicacion.nombre.strip()
    codigo_normalizado = ubicacion.codigo.strip().upper()
    if not nombre_normalizado or not codigo_normalizado:
        raise HTTPException(status_code=400, detail="El nombre y código de la ubicación no pueden estar vacíos.")
    
    # Verificar si ya existe por nombre
    existente_nombre = await repo.db.fetch_one(
        "SELECT id FROM porteria_ubicaciones WHERE LOWER(nombre) = LOWER(?)",
        (nombre_normalizado,)
    )
    if existente_nombre:
        raise HTTPException(status_code=400, detail=f"La ubicación con el nombre '{nombre_normalizado}' ya existe.")

    # Verificar si ya existe por código
    existente_codigo = await repo.db.fetch_one(
        "SELECT id FROM porteria_ubicaciones WHERE LOWER(codigo) = LOWER(?)",
        (codigo_normalizado.lower(),)
    )
    if existente_codigo:
        raise HTTPException(status_code=400, detail=f"La ubicación con el código '{codigo_normalizado}' ya existe.")

    new_id = await repo.create_ubicacion(nombre_normalizado, codigo_normalizado)
    
    # Registrar auditoría
    await repo.db.execute(
        "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
        (
            current_user.user_id,
            current_user.username,
            "CREATE_PORTERIA_UBICACION",
            "Porteria",
            f"Creada ubicación: '{nombre_normalizado}' - Código: '{codigo_normalizado}' (ID: {new_id})."
        )
    )
    return {"id": new_id, "nombre": nombre_normalizado, "codigo": codigo_normalizado, "message": "Ubicación creada exitosamente"}


@router.put("/ubicaciones/{ubicacion_id}/", response_model=Dict[str, Any])
async def update_ubicacion(
    ubicacion_id: int,
    ubicacion: UbicacionCreate,
    repo: PorteriaRepository = Depends(get_porteria_repository),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.editar", "porteria.editar"]))
):
    """Actualiza una ubicación existente."""
    nombre_normalizado = ubicacion.nombre.strip()
    codigo_normalizado = ubicacion.codigo.strip().upper()
    if not nombre_normalizado or not codigo_normalizado:
        raise HTTPException(status_code=400, detail="El nombre y código de la ubicación no pueden estar vacíos.")

    # Verificar si el registro existe
    db_ubi = await repo.get_ubicacion_by_id(ubicacion_id)
    if not db_ubi:
        raise HTTPException(status_code=404, detail="Ubicación no encontrada")

    # Verificar si el nuevo nombre colisiona con otro registro
    colision_nombre = await repo.db.fetch_one(
        "SELECT id FROM porteria_ubicaciones WHERE LOWER(nombre) = LOWER(?) AND id != ?",
        (nombre_normalizado, ubicacion_id)
    )
    if colision_nombre:
        raise HTTPException(status_code=400, detail=f"Ya existe otra ubicación con el nombre '{nombre_normalizado}'.")

    # Verificar si el nuevo código colisiona con otro registro
    colision_codigo = await repo.db.fetch_one(
        "SELECT id FROM porteria_ubicaciones WHERE LOWER(codigo) = LOWER(?) AND id != ?",
        (codigo_normalizado.lower(), ubicacion_id)
    )
    if colision_codigo:
        raise HTTPException(status_code=400, detail=f"Ya existe otra ubicación con el código '{codigo_normalizado}'.")

    success = await repo.update_ubicacion(ubicacion_id, nombre_normalizado, codigo_normalizado, ubicacion.activo)
    if not success:
        raise HTTPException(status_code=500, detail="No se pudo actualizar la ubicación")

    # Registrar auditoría
    await repo.db.execute(
        "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
        (
            current_user.user_id,
            current_user.username,
            "UPDATE_PORTERIA_UBICACION",
            "Porteria",
            f"Actualizada ubicación #{ubicacion_id}: nombre='{nombre_normalizado}', código='{codigo_normalizado}', activo={ubicacion.activo}."
        )
    )
    return {"id": ubicacion_id, "message": "Ubicación actualizada correctamente"}


@router.delete("/ubicaciones/{ubicacion_id}/", status_code=204)
async def delete_ubicacion(
    ubicacion_id: int,
    repo: PorteriaRepository = Depends(get_porteria_repository),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.editar", "porteria.editar"]))
):
    """Elimina o desactiva una ubicación."""
    db_ubi = await repo.get_ubicacion_by_id(ubicacion_id)
    if not db_ubi:
        raise HTTPException(status_code=404, detail="Ubicación no encontrada")

    success = await repo.delete_ubicacion(ubicacion_id)
    if not success:
         raise HTTPException(status_code=500, detail="Error al eliminar la ubicación")

    # Registrar auditoría
    await repo.db.execute(
        "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
        (
            current_user.user_id,
            current_user.username,
            "DELETE_PORTERIA_UBICACION",
            "Porteria",
            f"Eliminada/Desactivada ubicación #{ubicacion_id} ('{db_ubi['nombre']}')."
        )
    )
    return


# ============================================
# ENDPOINTS: CARGA DE FOTOS A GOOGLE DRIVE
# ============================================

@router.post("/upload-foto/", response_model=Dict[str, str])
async def upload_photo(
    file: UploadFile = File(...),
    current_user: SecurityContext = Depends(get_current_user)
):
    """
    Recibe un archivo de foto del dispositivo móvil del guardia (idealmente ya comprimido en el cliente)
    y lo sube a la carpeta de Google Drive. Retorna el drive_file_id y la URL pública.
    """
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="El archivo subido está vacío.")

        drive_service = GoogleDriveService()
        result = await drive_service.upload_photo(content, file.filename, file.content_type)
        
        if not result:
            raise HTTPException(status_code=500, detail="Fallo al cargar la imagen a Google Drive API.")
            
        return {
            "google_drive_file_id": result["id"],
            "foto_url": result["web_view_url"]
        }
    except Exception as e:
        logger.error(f"❌ Error subiendo foto de ronda: {e}")
        raise HTTPException(status_code=500, detail=f"Error en la subida de foto: {str(e)}")


# ============================================
# ENDPOINTS: REGISTRO Y SINCRONIZACIÓN DE RONDAS
# ============================================

@router.post("/rondas/sincronizar/", response_model=Dict[str, Any])
async def sync_rondas(
    payload: SyncBatchRequest,
    repo: PorteriaRepository = Depends(get_porteria_repository),
    current_user: SecurityContext = Depends(get_current_user)
):
    """
    Sincroniza un lote de registros de rondas capturados localmente en modo offline por el guardia.
    Este endpoint es idempotente basándose en el uuid_offline de cada ronda.
    """
    if not payload.rondas:
        return {"sincronizadas": 0, "duplicadas": 0, "errores": 0, "message": "El lote está vacío"}

    rondas_dict_list = []
    for r in payload.rondas:
        # Convertir objetos Pydantic a diccionarios planos para el repositorio
        r_dict = r.model_dump()
        rondas_dict_list.append(r_dict)

    res = await repo.sync_rondas_batch(rondas_dict_list)
    
    # Registrar auditoría
    await repo.db.execute(
        "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
        (
            current_user.user_id,
            current_user.username,
            "SYNC_PORTERIA_RONDAS",
            "Porteria",
            f"Sincronizado lote de rondas: {res['sincronizadas']} exitosas, {res['duplicadas']} duplicadas, {res['errores']} errores."
        )
    )

    return res


@router.get("/rondas/recientes/", response_model=List[RondaRecordResponse])
async def get_rondas_recientes(
    limit: int = Query(100, ge=1, le=500, description="Cantidad de registros a obtener"),
    repo: PorteriaRepository = Depends(get_porteria_repository),
    current_user: SecurityContext = Depends(RequireAnyPermission(["configuracion.ver", "porteria.ver"]))
):
    """Obtiene el listado de las rondas de control más recientes en la planta."""
    return await repo.get_rondas_recientes(limit=limit)


@router.get("/ping/", response_model=Dict[str, str])
async def ping_connection(current_user: SecurityContext = Depends(get_current_user)):
    """Verificación rápida de conexión de red para la tablet/celular del guardia."""
    return {"status": "ok", "message": "Conexión activa con el servidor central"}
