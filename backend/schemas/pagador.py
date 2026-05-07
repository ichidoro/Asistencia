from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PagadorBase(BaseModel):
    nombre: str
    activo: bool = True

class PagadorCreate(PagadorBase):
    pass

class PagadorResponse(PagadorBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
