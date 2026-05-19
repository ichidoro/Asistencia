from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime

# ==========================================
# SCHEMAS: REGLAS DE BONO
# ==========================================
class BonoReglaBase(BaseModel):
    monto: float = Field(..., ge=0)
    asistencia_minima: float = Field(0.0, ge=0, le=100.0, description="Porcentaje de asistencia requerido")
    tipo_contrato: Optional[str] = Field(None, description="Indefinido, Temporal, etc.")
    cargo_requerido: Optional[str] = Field(None, description="Cargo específico para este bono")
    cargos_excluidos: Optional[str] = Field(None, description="Lista separada por comas de cargos excluidos")
    labor_requerida: Optional[str] = Field(None, description="Labor específica para este bono")
    es_proporcional: bool = Field(False, description="Si es True, se descuenta por día faltado")
    version: int = Field(1, ge=1)
    fecha_inicio: date = Field(default_factory=date.today)

class BonoReglaCreate(BonoReglaBase):
    bono_id: Optional[int] = None

class BonoReglaResponse(BonoReglaBase):
    id: int
    bono_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# ==========================================
# SCHEMAS: BONOS
# ==========================================
class BonoBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    activo: bool = True

class BonoCreate(BonoBase):
    reglas: List[BonoReglaBase] = []
    area_ids: Optional[List[int]] = Field(None, description="IDs de áreas a las que asignar el bono")

class BonoResponse(BonoBase):
    id: int
    reglas: List[BonoReglaResponse] = []
    area_ids: List[int] = []   # IDs de áreas asignadas — necesario para el frontend
    created_at: datetime

    class Config:
        from_attributes = True

# ==========================================
# SCHEMAS: ASIGNACIONES DE BONO
# ==========================================
class BonoAsignacionBase(BaseModel):
    empleado_id: int
    bono_id: int
    fecha_desde: date
    fecha_hasta: Optional[date] = None

class BonoAsignacionCreate(BonoAsignacionBase):
    pass

class BonoAsignacionResponse(BonoAsignacionBase):
    id: int
    bono_nombre: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
