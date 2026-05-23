from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from typing import List, Optional, Callable
from loguru import logger
from datetime import datetime
import json

from backend.core.config import settings
from backend.core.database import db
from backend.repositories.seguridad import SeguridadRepository

# URL donde el frontend debe enviar username/password para obtener el token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

async def get_seguridad_repo() -> SeguridadRepository:
    return SeguridadRepository(db)

class SecurityContext:
    def __init__(self, user_id: int, username: str, rol_id: int, is_superuser: bool, alcance_global: bool, areas: List[str], permisos: List[str]):
        self.user_id = user_id
        self.username = username
        self.rol_id = rol_id
        self.is_superuser = is_superuser
        self.alcance_global = alcance_global
        self.areas = areas
        self.permisos = permisos

    def check_permission(self, required_permission: str) -> bool:
        if self.is_superuser:
            return True
        if required_permission and required_permission.endswith(".ver"):
            return True
        return required_permission in self.permisos

    def check_area_access(self, area: str) -> bool:
        if self.is_superuser or self.alcance_global:
            return True
        return area in self.areas

    def filtrar_areas(self, requested_areas: Optional[List[str]] = None) -> Optional[List[str]]:
        """
        Retorna la intersección segura entre las áreas solicitadas y las permitidas.
        Si es superuser o alcance global, retorna las solicitadas tal cual.
        """
        if self.is_superuser or self.alcance_global:
            return requested_areas
            
        if not requested_areas:
            return self.areas
            
        # Intersección
        return [a for a in requested_areas if a in self.areas]

async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme), 
    seguridad_repo: SeguridadRepository = Depends(get_seguridad_repo)
) -> SecurityContext:
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o sesión expirada",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # ZERO-TRUST: Verificamos en la réplica local (1ms) que el usuario siga existiendo y ACTIVO.
    # Esto es el "Blacklist anti-despedida" sin necesidad de Redis.
    # Retry: Si la DB está bajo write-contention (batch sync), reintentar 1 vez tras 200ms.
    user_db = None
    last_err = None
    for _attempt in range(5):
        try:
            user_db = await seguridad_repo.get_user_by_username(username)
            last_err = None
            break
        except Exception as e:
            last_err = e
        
        if _attempt < 4:
            import asyncio
            await asyncio.sleep(0.3)
            
    if last_err is not None:
        logger.error(f"Error de base de datos verificando usuario {username}: {last_err}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="El sistema está procesando datos, por favor reintente en unos segundos."
        )
    
    if user_db is None or not user_db.get("activo"):
        logger.warning(f"Intento de acceso con token válido pero usuario inactivo/inexistente: {username}")
        raise credentials_exception

    # Recuperamos los permisos actuales
    permisos = await seguridad_repo.get_permissions_for_role(user_db["rol_id"])
    
    try:
        areas = json.loads(user_db.get("areas_json", "[]"))
    except (ValueError, TypeError):
        areas = []

    # Construir el Contexto de Seguridad
    context = SecurityContext(
        user_id=user_db["id"],
        username=user_db["username"],
        rol_id=user_db["rol_id"],
        is_superuser=bool(user_db.get("is_superuser", 0)),
        alcance_global=bool(user_db.get("alcance_global", 0)),
        areas=areas,
        permisos=permisos
    )
    
    # Inyectar el contexto en el Request para los repositorios si fuera necesario
    request.state.user = context
    
    return context

def RequirePermission(required_permission: str):
    """Dependencia inyectable para proteger Endpoints"""
    async def permission_checker(context: SecurityContext = Depends(get_current_user)):
        if not context.check_permission(required_permission):
            logger.warning(f"Bloqueo de Seguridad: {context.username} intentó acceder a recurso que requiere {required_permission}")
            # Audit Trail
            try:
                repo = SeguridadRepository(db)
                await repo.log_auditoria(context.user_id, context.username, "INTENTO_ACCESO_DENEGADO", "SEGURIDAD", f"Requería: {required_permission}")
            except Exception as audit_err:
                logger.warning(f"⚠️ [Security] Auditoría de acceso denegado no registrada (no crítico): {audit_err}")
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tiene permisos para realizar esta acción. Requerido: {required_permission}"
            )
        return context
    return permission_checker
