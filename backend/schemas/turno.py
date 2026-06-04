from pydantic import BaseModel, Field, validator
from typing import List, Optional, Literal
from datetime import date, time

# ==========================================
# SCHEMAS: MICRO-SHIFTS (SEGMENTOS)
# ==========================================
class TurnoSegmentoCreate(BaseModel):
    hora_inicio: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="HH:MM")
    hora_fin: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="HH:MM")

class TurnoSegmentoResponse(TurnoSegmentoCreate):
    id: int
    turno_dia_id: int

    class Config:
        from_attributes = True

# ==========================================
# SCHEMAS: DIAS DE TURNO
# ==========================================
class TurnoDiaCreate(BaseModel):
    dia_semana: int = Field(..., ge=0, le=6, description="0=Lunes, 6=Domingo")
    num_semana: int = Field(1, ge=1, description="Número de semana en el ciclo (1, 2, 3...)")
    etiqueta_bloque: Optional[str] = Field(None, description="Etiqueta visual del bloque (ej: Mañana, Tarde)")
    es_libre: bool = False
    horas_teoricas: float = Field(0.0, ge=0)
    hora_entrada: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    hora_salida: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    cruza_medianoche: bool = False
    hora_entrada_2: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    hora_salida_2: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    cruza_medianoche_2: bool = False
    # Opcional: Lista de segmentos para turnos cortados
    segmentos: Optional[List[TurnoSegmentoCreate]] = []

class TurnoDiaResponse(TurnoDiaCreate):
    id: int
    turno_id: int
    segmentos: List[TurnoSegmentoResponse] = []

    class Config:
        from_attributes = True

# ==========================================
# SCHEMAS: TURNOS
# ==========================================
class TurnoBase(BaseModel):
    nombre: str
    tipo_programacion: Literal['DINAMICO_FLEXIBLE', 'FLEXIBLE_BOLSA'] = 'DINAMICO_FLEXIBLE'
    tolerancia_retraso_alerta: int = 0
    tolerancia_retraso_descuento: int = 0
    redondeo_minutos: int = 0
    meta_horas_semanales: float = 0.0
    descuento_colacion_auto: bool = False
    minutos_colacion_auto: int = 0
    umbral_horas_colacion: float = 0.0 # Umbral para no descontar colación en jornadas cortas
    anclaje_entrada_minutos: int = 0 # Nuevo campo para marcas tempranas
    anclaje_salida_minutos: int = 0 # Nuevo campo para marcas tardías filtrables
    ventana_en_curso_minutos: int = 0 # (DT-4) Reemplazo de margen duro de 3h para estados EN_CURSO
    tolerancia_exceso_colacion_minutos: int = 0 # (DT-14) Margen para diferenciar colación de permisos
    es_turno_cortado: bool = False # Añadido para consistencia
    hora_limite_ficticia: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$", description="Hora trigger para la inasistencia temprana en Horarios Bolsa")
    areas: List[str] = [] # Nuevo: Lista de nombres de áreas
    turno_padre_id: Optional[int] = None # Para versionamiento: ID del turno original
    fecha_vigencia: Optional[str] = None # YYYY-MM-DD: Desde cuándo aplica esta versión
    rotacion_secuencial: bool = True
    semana_fallback_sin_marcas: int = 1
    activo: bool = True

    @validator('activo', pre=True, always=True)
    def default_activo(cls, v):
        if v is None:
            return True
        return bool(v)

class TurnoCreate(TurnoBase):
    dias: List[TurnoDiaCreate]

class TurnoResponse(TurnoBase):
    id: int
    dias: List[TurnoDiaResponse] = []
    created_at: Optional[str] = None

    class Config:
        from_attributes = True

# ==========================================
# SCHEMAS: PLANTILLAS
# ==========================================
class PlantillaCreate(BaseModel):
    nombre: str
    configuracion_json: str # JSON Stringify de la semana

class PlantillaResponse(PlantillaCreate):
    id: int

    class Config:
        from_attributes = True

# ==========================================
# SCHEMAS: ASIGNACIONES
# ==========================================
class AsignacionCreate(BaseModel):
    empleado_id: int
    turno_id: int
    fecha_inicio: str # YYYY-MM-DD
    fecha_fin: Optional[str] = None # YYYY-MM-DD
    reemplazar: bool = False # Bandera para forzar sobrescritura

class AsignacionBulk(BaseModel):
    empleados_ids: List[int]
    turno_id: int
    fecha_inicio: str # YYYY-MM-DD
    fecha_fin: Optional[str] = None # YYYY-MM-DD
    reemplazar: bool = False # Bandera para forzar sobrescritura

class AsignacionResponse(AsignacionCreate):
    id: int
    turno_nombre: Optional[str] = None

    class Config:
        from_attributes = True

class AsignacionUpdateDate(BaseModel):
    empleado_id: int
    nueva_fecha: str # YYYY-MM-DD
