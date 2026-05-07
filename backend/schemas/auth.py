from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict
from datetime import datetime

# --- PERMISOS ---
class PermisoBase(BaseModel):
    id: str = Field(..., description="Ej: empleados.ver")
    modulo: str = Field(..., description="Ej: Empleados")
    descripcion: str

class PermisoResponse(PermisoBase):
    pass

# --- ROLES ---
class RolBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    alcance_global: bool = False

class RolCreate(RolBase):
    permisos: List[str] = [] # Lista de IDs de permisos (ej: ['empleados.ver', 'asistencia.editar'])

class RolResponse(RolBase):
    id: int
    permisos: List[PermisoResponse] = []
    
    class Config:
        from_attributes = True

# --- USUARIOS ---
class UsuarioBase(BaseModel):
    username: str
    nombre_completo: str
    email: Optional[str] = None
    activo: bool = True
    rol_id: int
    areas: Optional[List[str]] = Field(default_factory=list, description="Lista de áreas a las que tiene acceso. Si rol.alcance_global es True, esto se ignora.")

class UsuarioCreate(UsuarioBase):
    password: str

class UsuarioUpdate(BaseModel):
    nombre_completo: Optional[str] = None
    email: Optional[str] = None
    activo: Optional[bool] = None
    rol_id: Optional[int] = None
    areas: Optional[List[str]] = None
    password: Optional[str] = None # Si se envía, se cambia

class UsuarioResponse(UsuarioBase):
    id: int
    rol_nombre: Optional[str] = None
    created_at: Optional[datetime] = None
    ultimo_acceso: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# --- AUTHENTICATION ---
class LoginRequest(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Datos básicos incrustados para UI principal (Area Scoping blindado)
    user_id: int
    username: str
    rol_id: int
    is_superuser: bool = False
    alcance_global: bool
    areas: List[str]

class TokenData(BaseModel):
    user_id: Optional[int] = None
    username: Optional[str] = None
    rol_id: Optional[int] = None
    alcance_global: bool = False
    areas: List[str] = []

# --- AUDITORIA ---
class LogAuditoriaResponse(BaseModel):
    id: int
    usuario_id: int
    username: str
    accion: str
    modulo: str
    detalle: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
