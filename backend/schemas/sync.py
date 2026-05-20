from pydantic import BaseModel
from typing import List, Optional, Dict

class SyncEmpleadosRequest(BaseModel):
    areas: Optional[List[str]] = None
    ruts: Optional[List[str]] = None  # Filtro granular por RUTs seleccionados
    selected_cargos: Optional[List[str]] = None

class SyncPreviewRequest(BaseModel):
    resoluciones_areas: Optional[Dict[str, str]] = None
    selected_cargos: Optional[List[str]] = None

class SyncAsistenciaRequest(BaseModel):
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    areas: Optional[List[str]] = None
