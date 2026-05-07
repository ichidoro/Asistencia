from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import date, datetime

class AsistenciaMatrizResponse(BaseModel):
    success: bool
    data: List[Dict[str, Any]]
    dias: List[str]
    empleados: List[Dict[str, Any]]
    resumen: Optional[Dict[str, Any]] = None

class RecalcularRequest(BaseModel):
    empleado_id: int
    fecha_inicio: str
    fecha_fin: str
    force: bool = False

class AprobarHERequest(BaseModel):
    empleado_id: int
    fecha: str
    horas: float
    comentario: Optional[str] = None

class AsignacionIndividual(BaseModel):
    empleado_id: int
    fecha: str
    turno_id: int
    sync_bioalba: bool = True  # Si True, descarga marcaciones BioAlba como parte del job secuencial
    skip_reproceso: bool = False  # Si True (modo batch), solo guarda el turno sin lanzar job de reproceso

class BatchSyncItem(BaseModel):
    """Un empleado dentro de un job de sincronización batch."""
    empleado_id: int
    fecha_inicio: str  # YYYY-MM-DD — desde cuándo se sincroniza

class BatchSyncRequest(BaseModel):
    """Request para sincronizar N empleados en una sola llamada optimizada."""
    items: List[BatchSyncItem]

# Re-exportar JustificacionCreate para compatibilidad con el router
from .justificacion import JustificacionCreate
