from fastapi import APIRouter, Depends, Query, HTTPException, status
from typing import List, Dict, Any
import json
from loguru import logger

from backend.core.database import db
from backend.repositories.seguridad import SeguridadRepository
from backend.core.security import SecurityContext, RequirePermission
from backend.schemas.auth import UsuarioCreate, UsuarioUpdate, RolCreate

router = APIRouter(prefix="/seguridad", tags=["Consola de Seguridad"])

def get_repo():
    return SeguridadRepository(db)

@router.get("/auditoria/")
async def get_auditoria(
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    repo: SeguridadRepository = Depends(get_repo),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.seguridad"))
):
    """Obtener bitácora de auditoría (Acciones Críticas y Bloqueos 403)"""
    logs = await repo.get_auditoria(limit, skip)
    total = await repo.count_auditoria()
    return {"data": logs, "total": total}

@router.get("/roles/")
async def get_roles(
    repo: SeguridadRepository = Depends(get_repo),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.seguridad"))
):
    """Obtener todos los roles junto con sus permisos asignados"""
    roles = await repo.get_all_roles()
    for rol in roles:
        rol["permisos"] = await repo.get_permissions_for_role(rol["id"])
    return roles

@router.get("/permisos/")
async def get_permisos(
    repo: SeguridadRepository = Depends(get_repo),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.seguridad"))
):
    """Obtener el diccionario matriz de todos los permisos existentes en el sistema"""
    return await repo.get_all_permisos()

@router.post("/roles/")
async def create_rol(
    rol: RolCreate,
    repo: SeguridadRepository = Depends(get_repo),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.seguridad"))
):
    """Crear un nuevo Rol de Seguridad con sus respectivos permisos"""
    rol_id = await repo.create_rol(rol.nombre, rol.descripcion, int(rol.alcance_global), rol.permisos)
    await repo.log_auditoria(
        current_user.user_id, current_user.username, "CREATE", "SEGURIDAD", 
        f"Rol creado: {rol.nombre} con {len(rol.permisos)} permisos"
    )
    return {"id": rol_id, "message": "Rol creado exitosamente"}

@router.put("/roles/{rol_id}/")
async def update_rol(
    rol_id: int,
    rol: RolCreate,
    repo: SeguridadRepository = Depends(get_repo),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.seguridad"))
):
    """Actualizar un Rol existente (si no es el Súper Admin global)"""
    if rol_id == 1 and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Solo el Súper Administrador puede modificar el Rol Maestro")
    
    await repo.update_rol(rol_id, rol.nombre, rol.descripcion, int(rol.alcance_global), rol.permisos)
    await repo.log_auditoria(
        current_user.user_id, current_user.username, "UPDATE", "SEGURIDAD", 
        f"Rol modificado: {rol.nombre} ({rol_id})"
    )
    return {"message": "Rol modificado exitosamente"}

@router.delete("/roles/{rol_id}/")
async def delete_rol(
    rol_id: int,
    repo: SeguridadRepository = Depends(get_repo),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.seguridad"))
):
    """Eliminar un rol de seguridad (si no está en uso y no es Súper Admin)"""
    if rol_id == 1:
        raise HTTPException(status_code=403, detail="El Rol Maestro (Súper Administrador) es inmutable y no puede ser eliminado")
        
    role_to_delete = await repo.get_rol_by_id(rol_id)
    if not role_to_delete:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
        
    if not current_user.alcance_global and role_to_delete.get("alcance_global"):
        raise HTTPException(status_code=403, detail="No tiene permisos para eliminar un rol global")
        
    in_use = await repo.check_role_in_use(rol_id)
    if in_use:
        raise HTTPException(status_code=400, detail="No se puede eliminar el rol porque está asignado a uno o más usuarios")
        
    await repo.delete_rol(rol_id)
    await repo.log_auditoria(
        current_user.user_id, current_user.username, "DELETE", "SEGURIDAD", 
        f"Rol eliminado: {role_to_delete.get('nombre')} (ID: {rol_id})"
    )
    return {"message": "Rol eliminado exitosamente"}


@router.get("/usuarios/")
async def get_usuarios(
    repo: SeguridadRepository = Depends(get_repo),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.seguridad"))
):
    """Listar todos los usuarios del sistema"""
    usuarios = await repo.get_all_usuarios()
    for user in usuarios:
        try:
            user["areas"] = json.loads(user.get("areas_json", "[]"))
        except Exception as e:
            logger.warning(f"⚠️ areas_json corrupto para usuario {user.get('username', '?')}: {e}")
            user["areas"] = []
    return usuarios

@router.post("/usuarios/")
async def create_usuario(
    user: UsuarioCreate,
    repo: SeguridadRepository = Depends(get_repo),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.seguridad"))
):
    """Crear un nuevo usuario con validación de jerarquía y RLS"""
    # 1. Validar que no intente crear un usuario global si el creador es zonal
    role_to_assign = await repo.get_rol_by_id(user.rol_id)
    if not current_user.alcance_global:
        if role_to_assign.get("alcance_global"):
            raise HTTPException(status_code=403, detail="No tiene permisos para crear usuarios administradores globales")
        
        # 2. Validar Áreas: No puede asignar áreas que él no tiene
        if user.areas:
            for area in user.areas:
                if area not in (current_user.areas or []):
                    raise HTTPException(status_code=403, detail=f"No tiene permisos para asignar el área: {area}")
    try:
        user_id = await repo.create_user(user)
        await repo.log_auditoria(
            current_user.user_id, current_user.username, "CREATE", "SEGURIDAD", 
            f"Usuario creado: {user.username} (Rol ID: {user.rol_id})"
        )
        return {"id": user_id, "message": "Usuario creado exitosamente"}
    except Exception as e:
        logger.error(f"Error creando usuario: {e}")
        raise HTTPException(status_code=400, detail="Error creando usuario. Probablemente el username ya existe.")

@router.put("/usuarios/{user_id}/")
async def update_usuario(
    user_id: int,
    user: UsuarioUpdate,
    repo: SeguridadRepository = Depends(get_repo),
    current_user: SecurityContext = Depends(RequirePermission("configuracion.seguridad"))
):
    """Actualizar datos, rol o estado de un usuario"""
    # 1. Validar jerarquía y escala de privilegios
    if not current_user.alcance_global:
        # No puede editar a un usuario que sea global
        target_user = await repo.get_user_by_id(user_id)
        target_role = await repo.get_rol_by_id(target_user.get("rol_id"))
        if target_role.get("alcance_global"):
            raise HTTPException(status_code=403, detail="No tiene permisos para modificar a un administrador global")
        
        # No puede subir de rango al usuario a global
        new_role = await repo.get_rol_by_id(user.rol_id)
        if new_role.get("alcance_global"):
            raise HTTPException(status_code=403, detail="No puede promover a un usuario a administrador global")

        # No puede asignar áreas fuera de su alcance
        if user.areas:
            for area in user.areas:
                if area not in (current_user.areas or []):
                    raise HTTPException(status_code=403, detail=f"No tiene permisos para asignar el área: {area}")

    if user_id == 9 and current_user.user_id != 9:
        raise HTTPException(status_code=403, detail="Solo el admin original puede auto-modificarse")
        
    await repo.update_user(user_id, user)
    await repo.log_auditoria(
        current_user.user_id, current_user.username, "UPDATE", "SEGURIDAD", 
        f"Usuario modificado: ID {user_id}"
    )
    return {"message": "Usuario modificado exitosamente"}
