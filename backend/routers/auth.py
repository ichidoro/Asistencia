from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from typing import Any
import json
from loguru import logger

from backend.schemas.auth import Token, UsuarioResponse
from backend.repositories.seguridad import SeguridadRepository
from backend.core.database import db
from backend.core.security import get_current_user, SecurityContext

router = APIRouter(prefix="/auth", tags=["Autenticación"])

# ── Rate Limiting en memoria ─────────────────────────────────────────────────
import time as _time
_login_attempts: dict = {}  # {ip: [timestamp, ...]}
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 300  # 5 minutos

def _check_rate_limit(ip: str) -> None:
    """Verifica y aplica rate limiting por IP. Lanza HTTPException 429 si excede."""
    now = _time.time()
    # Limpiar entradas viejas
    cutoff = now - _WINDOW_SECONDS
    if ip in _login_attempts:
        _login_attempts[ip] = [t for t in _login_attempts[ip] if t > cutoff]
        if not _login_attempts[ip]:
            del _login_attempts[ip]
    # Verificar límite
    attempts = _login_attempts.get(ip, [])
    if len(attempts) >= _MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos de inicio de sesión. Intente nuevamente en 5 minutos."
        )
    # Registrar intento
    _login_attempts.setdefault(ip, []).append(now)

def get_repo():
    return SeguridadRepository(db)

@router.post("/login/", response_model=Token)
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    repo: SeguridadRepository = Depends(get_repo)
) -> Any:
    """OAuth2 compatible token login, get an access token for future requests"""
    _check_rate_limit(request.client.host if request.client else "unknown")
    user_data = await repo.get_user_by_username(form_data.username)
    
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not repo.verify_password(form_data.password, user_data["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not user_data["activo"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo, contacte al administrador",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Convert areas from JSON string to List
    try:
        areas = json.loads(user_data.get("areas_json", "[]"))
    except (ValueError, TypeError):
        areas = []
        
    # Update last access
    try:
        await repo.db.execute("UPDATE usuarios SET ultimo_acceso = CURRENT_TIMESTAMP WHERE id = ?", (user_data["id"],))
    except Exception as e:
        logger.warning(f"No se pudo actualizar ultimo_acceso para {user_data['username']}: {e}")

    # Build token payload
    access_token = repo.create_access_token(
        data={"sub": user_data["username"]}
    )

    # Log login
    try:
        await repo.log_auditoria(user_data["id"], user_data["username"], "LOGIN", "SEGURIDAD", "Ingreso exitoso")
    except Exception as audit_err:
        logger.warning(f"⚠️ [Auth] Log de login no registrado (no crítico): {audit_err}")

    # Return JWT token + Embedded data for Splash Screen cache
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user_data["id"],
        "username": user_data["username"],
        "nombre_completo": user_data.get("nombre_completo", ""),
        "email": user_data.get("email", ""),
        "rol_id": user_data["rol_id"],
        "rol_nombre": user_data.get("rol_nombre"),
        "is_superuser": bool(user_data.get("is_superuser", 0)),
        "alcance_global": bool(user_data.get("alcance_global", 0)) or bool(user_data.get("is_superuser", 0)),
        "areas": areas,
        "ultimo_acceso": str(user_data.get("ultimo_acceso", "")) if user_data.get("ultimo_acceso") else ""
    }

@router.get("/me/", response_model=UsuarioResponse)
async def read_users_me(
    current_user: SecurityContext = Depends(get_current_user),
    repo: SeguridadRepository = Depends(get_repo)
):
    """Obtener datos del usuario logueado actualmente"""
    user_db = await repo.get_user_by_username(current_user.username)
    if not user_db:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
    try:
        areas = json.loads(user_db.get("areas_json", "[]"))
    except (ValueError, TypeError):
        areas = []
        
    return {
        "username": user_db["username"],
        "nombre_completo": user_db["nombre_completo"],
        "email": user_db["email"],
        "activo": bool(user_db["activo"]),
        "rol_id": user_db["rol_id"],
        "id": user_db["id"],
        "rol_nombre": user_db["rol_nombre"],
        "areas": areas,
        "created_at": user_db["created_at"],
        "ultimo_acceso": user_db["ultimo_acceso"]
    }

@router.get("/permissions/")
async def get_my_permissions(
    current_user: SecurityContext = Depends(get_current_user)
):
    """Obtener los permisos del usuario para configurar el frontend (Splash Screen pre-render)"""
    return {
        "permisos": current_user.permisos,
        "is_superuser": current_user.is_superuser,
        "alcance_global": current_user.alcance_global,
        "areas": current_user.areas
    }
