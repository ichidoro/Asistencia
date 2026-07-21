from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PeriodoRRHHBase(BaseModel):
    mes_cierre: str
    fecha_inicio: str  # YYYY-MM-DD
    fecha_fin: str     # YYYY-MM-DD
    activo: Optional[int] = 0
    estado: Optional[str] = "abierto"  # 'abierto' o 'cerrado'

class PeriodoRRHHCreate(PeriodoRRHHBase):
    pass

class PeriodoRRHHResponse(PeriodoRRHHBase):
    id: int
    created_at: datetime
    areas_cerradas: Optional[list[str]] = []
    areas_pendientes: Optional[list[str]] = []

    class Config:
        from_attributes = True
