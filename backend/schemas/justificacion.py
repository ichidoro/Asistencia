from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime

# ==========================================
# SCHEMAS: TIPOS DE JUSTIFICACION
# ==========================================
class JustificacionTipoBase(BaseModel):
    nombre: str
    nomenclatura: Optional[str] = Field(None, max_length=5, description="Abreviatura para la grilla (ej. VAC)")
    descripcion: Optional[str] = None
    con_goce_sueldo: bool = True
    dias_habiles: bool = True # True: Lunes a Viernes, False: Días Corridos
    pagador: str = Field("Empleador", description="Empleador, Fonasa, Isapre, etc.")
    dias_defecto: Optional[int] = Field(None, description="Días predeterminados para cálculo automático")
    
    # Reglas Avanzadas
    min_dias: int = Field(1, description="Mínimo de días permitidos")
    max_dias: Optional[int] = Field(None, description="Máximo de días permitidos (NULL = sin límite)")
    frecuencia_anual: Optional[int] = Field(None, description="Máx veces por año (NULL = sin límite)")
    dias_corridos: bool = Field(False, description="True: Corridos (Inc. Sab/Dom), False: Hábiles")
    sobreescribe_feriados: bool = Field(False, description="True: Cuenta como justificación en feriado")
    descuenta_remuneracion: bool = Field(False, description="True: Sin goce de sueldo")
    es_horas_sindicales: bool = Field(False, description="True: Se maneja por bolsa de horas (Permiso Sindical)")
    
    # NEW: Permisos Parciales y Deuda
    es_por_horas: bool = Field(False, description="True: Permiso parcial (horas/minutos), False: Día completo")
    genera_deuda_horaria: bool = Field(False, description="True: El tiempo se suma a la deuda (Compensable)")
    
    activo: bool = True

class JustificacionTipoCreate(JustificacionTipoBase):
    pass

class JustificacionTipoResponse(JustificacionTipoBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# ==========================================
# SCHEMAS: JUSTIFICACIONES (SOLICITUD)
# ==========================================
class JustificacionBase(BaseModel):
    empleado_id: int
    tipo_id: int
    fecha_inicio: date
    fecha_fin: date
    
    # NEW: Soporte para Permisos por Horas (RRHH Manual)
    hora_inicio: Optional[str] = Field(None, description="HH:MM (Solo si es por horas)")
    hora_fin: Optional[str] = Field(None, description="HH:MM (Solo si es por horas)")
    
    observaciones: Optional[str] = None
    documento_url: Optional[str] = None # Para certificados médicos, etc.

class JustificacionCreate(JustificacionBase):
    pass

class JustificacionResponse(JustificacionBase):
    id: int
    tipo_nombre: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
