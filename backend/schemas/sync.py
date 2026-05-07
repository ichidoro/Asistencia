from pydantic import BaseModel
from typing import List, Optional

class SyncEmpleadosRequest(BaseModel):
    areas: Optional[List[str]] = None
    ruts: Optional[List[str]] = None  # Filtro granular por RUTs seleccionados

class SyncPreviewRequest(BaseModel):
    areas: Optional[List[str]] = None

class SyncAsistenciaRequest(BaseModel):
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    areas: Optional[List[str]] = None
