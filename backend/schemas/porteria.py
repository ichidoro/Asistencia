from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# --- Ubicaciones (Puntos de Control QR) ---
class UbicacionBase(BaseModel):
    nombre: str = Field(..., description="Nombre descriptivo de la ubicación")
    codigo: str = Field(..., description="Código único de la ubicación para el QR (ej: LOC001)")
    activo: Optional[bool] = Field(True, description="Estado de activación de la ubicación")

class UbicacionCreate(UbicacionBase):
    pass

class UbicacionResponse(UbicacionBase):
    id: int
    created_at: Optional[str] = None

    class Config:
        from_attributes = True

# --- Catálogo de Hallazgos (Anomalías) ---
class CatalogFindingBase(BaseModel):
    nombre: str = Field(..., description="Nombre descriptivo de la anomalía o estado normal")
    activo: Optional[bool] = Field(True, description="Estado de activación del hallazgo en el catálogo")

class CatalogFindingCreate(CatalogFindingBase):
    pass

class CatalogFindingResponse(CatalogFindingBase):
    id: int
    created_at: Optional[str] = None

    class Config:
        from_attributes = True

# --- Hallazgos de Rondas ---
class RondaFindingBase(BaseModel):
    hallazgo_id: Optional[int] = Field(None, description="ID de la anomalía del catálogo")
    detalle_personalizado: Optional[str] = Field(None, description="Comentarios u observaciones personalizadas del guardia")
    google_drive_file_id: Optional[str] = Field(None, description="ID de la foto en Google Drive")
    foto_url: Optional[str] = Field(None, description="URL pública de la foto en Google Drive")

class RondaFindingCreate(RondaFindingBase):
    pass

class RondaFindingResponse(RondaFindingBase):
    id: int
    registro_id: int
    hallazgo_nombre: Optional[str] = Field(None, description="Nombre de la anomalía asociada (obtenido por join)")

    class Config:
        from_attributes = True

# --- Registro de Rondas ---
class RondaRecordBase(BaseModel):
    ubicacion_id: int = Field(..., description="ID de la ubicación/punto de control perimetral visitado")
    fecha_hora: str = Field(..., description="Fecha y hora de escaneo local en formato ISO 8601")
    uuid_offline: str = Field(..., description="UUID unívoco generado por el cliente offline")

class RondaRecordCreate(RondaRecordBase):
    usuario_id: int = Field(..., description="ID del usuario (guardia) que registró la ronda")
    hallazgos: List[RondaFindingCreate] = Field(default=[], description="Lote de hallazgos/fotos reportadas en este punto de control")

class RondaRecordResponse(RondaRecordBase):
    id: int
    usuario_id: int
    sincronizado_at: str
    ubicacion_nombre: Optional[str] = None
    ubicacion_codigo: Optional[str] = None
    usuario_nombre: Optional[str] = None
    hallazgos: List[RondaFindingResponse] = []

    class Config:
        from_attributes = True

class SyncBatchRequest(BaseModel):
    rondas: List[RondaRecordCreate] = Field(..., description="Lista de registros de rondas capturados en modo offline para sincronizar")
