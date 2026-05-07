from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

class FeriadoBase(BaseModel):
    fecha: date
    descripcion: str
    es_nacional: bool = True

class FeriadoCreate(FeriadoBase):
    pass

class FeriadoResponse(FeriadoBase):
    id: int
    
    class Config:
        from_attributes = True
