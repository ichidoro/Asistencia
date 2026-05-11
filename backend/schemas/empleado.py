"""
Schemas Pydantic - Empleado
DTOs para validación de datos de entrada/salida
"""

from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator
from typing import Optional
from datetime import date


class EmpleadoBase(BaseModel):
    """Schema base con campos comunes"""
    rut: str = Field(..., min_length=1, max_length=12, description="RUT del empleado (con o sin formato)")
    nombre: str = Field(default="", max_length=100, description="Nombre del empleado")
    apellido_paterno: str = Field(default="", max_length=100, description="Apellido paterno")
    apellido_materno: str = Field(default="", max_length=100, description="Apellido materno")
    cargo: Optional[str] = Field(None, max_length=100, description="Cargo del empleado")
    cargo_id: Optional[int] = Field(None, description="ID relacional del cargo")
    area_id: Optional[int] = Field(None, description="ID relacional del área")
    area: Optional[str] = Field(None, max_length=100, description="Área o departamento (Virtual/Lectura)")
    compania: Optional[str] = Field(None, max_length=100, description="Compañía")
    email: Optional[str] = Field(None, max_length=100, description="Email corporativo")
    telefono: Optional[str] = Field(None, max_length=20, description="Teléfono de contacto")
    genero: Optional[str] = Field(None, max_length=20, description="Género (Hombre/Mujer/Otro)")
    activo: bool = Field(True, description="Si el empleado está activo")
    fecha_nacimiento: Optional[str] = Field(None, description="Fecha de nacimiento (YYYY-MM-DD)")
    fecha_ingreso: Optional[str] = Field(None, description="Fecha de ingreso (YYYY-MM-DD)")
    fecha_salida: Optional[str] = Field(None, description="Fecha de salida (YYYY-MM-DD)")
    tipo_contrato: Optional[str] = Field("Temporal", description="Tipo de contrato: Indefinido o Temporal")
    cant_contratos: Optional[int] = Field(1, description="Número de contrato actual")
    
    @field_validator('rut')
    @classmethod
    def validate_rut(cls, v: str) -> str:
        """Validar formato básico del RUT"""
        # Remover puntos y guión
        rut_limpio = v.replace(".", "").replace("-", "").strip()
        
        if not rut_limpio:
            raise ValueError("RUT no puede estar vacío")
        
        if len(rut_limpio) < 2:
            raise ValueError("RUT debe tener al menos 2 caracteres")
        
        # Retornar sin formato para almacenar en DB
        return rut_limpio

    # Los validadores de fechas van en los schemas de INPUT, no en base


class _ValidateDatesMixin(BaseModel):
    """Mixin con validación de coherencia de fechas (solo para inputs: Create/Update)"""

    @model_validator(mode='after')
    def validate_dates(self) -> '_ValidateDatesMixin':
        """Validar coherencia entre fechas críticas"""
        from datetime import datetime

        f_nac = getattr(self, 'fecha_nacimiento', None)
        f_ing = getattr(self, 'fecha_ingreso', None)
        f_sal = getattr(self, 'fecha_salida', None)

        # 1. Validar que salida no sea anterior a ingreso
        if f_ing and f_sal:
            try:
                dt_ing = datetime.strptime(f_ing, "%Y-%m-%d")
                dt_sal = datetime.strptime(f_sal, "%Y-%m-%d")
                err_parse = False
            except (ValueError, TypeError):
                err_parse = True

            if not err_parse and dt_sal < dt_ing:
                raise ValueError(f"La fecha de salida ({f_sal}) no puede ser anterior a la de ingreso ({f_ing})")

        # 2. Validar sospecha de confusión con fecha de nacimiento
        if f_nac and f_sal:
            if f_nac == f_sal:
                raise ValueError("La fecha de salida no puede ser igual a la fecha de nacimiento")
            try:
                dt_nac = datetime.strptime(f_nac, "%Y-%m-%d")
                dt_sal = datetime.strptime(f_sal, "%Y-%m-%d")
                err_parse_nac = False
            except (ValueError, TypeError):
                err_parse_nac = True

            if not err_parse_nac and dt_sal < dt_nac:
                raise ValueError("La fecha de salida no puede ser anterior a la fecha de nacimiento")

        return self


class EmpleadoCreate(_ValidateDatesMixin, EmpleadoBase):
    """Schema para crear un empleado"""
    pass


class EmpleadoUpdate(_ValidateDatesMixin, BaseModel):
    """Schema para actualizar un empleado (todos los campos opcionales)"""
    rut: Optional[str] = Field(None, min_length=1, max_length=12)
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    apellido_paterno: Optional[str] = Field(None, min_length=1, max_length=100)
    apellido_materno: Optional[str] = Field(None, min_length=1, max_length=100)
    cargo: Optional[str] = Field(None, max_length=100)
    area_id: Optional[int] = None
    area: Optional[str] = Field(None, max_length=100)
    compania: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=20)
    genero: Optional[str] = Field(None, max_length=20, description="Género (Hombre/Mujer/Otro)")
    genero_id: Optional[int] = Field(None, description="ID del género en la tabla cat_generos")
    activo: Optional[bool] = True
    fecha_nacimiento: Optional[str] = None
    fecha_ingreso: Optional[str] = None
    fecha_salida: Optional[str] = None
    tipo_contrato: Optional[str] = None
    cant_contratos: Optional[int] = None


class EmpleadoResponse(EmpleadoBase):
    """Schema de respuesta (incluye campos generados)"""
    id: int
    nombre_completo: str
    rut_formateado: str
    bloqueante: Optional[bool] = False
    es_procesado: Optional[bool] = False
    decision_actual: Optional[str] = None
    estado_vencimiento: Optional[str] = "Normal"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    fecha_asignacion_turno: Optional[str] = None
    
    model_config = {
        "from_attributes": True
    }


class EmpleadoListResponse(BaseModel):
    """Schema para lista de empleados con paginación"""
    empleados: list[EmpleadoResponse]
    total: int
    skip: int
    limit: int


class EmpleadoSearchParams(BaseModel):
    """Schema para parámetros de búsqueda"""
    q: Optional[str] = Field(None, description="Búsqueda por nombre, RUT o cargo")
    area: Optional[str] = Field(None, description="Filtrar por área")
    compania: Optional[str] = Field(None, description="Filtrar por compañía")
    activo: Optional[bool] = Field(None, description="Filtrar por estado activo/inactivo")
    skip: int = Field(0, ge=0, description="Offset para paginación")
    limit: int = Field(100, ge=1, le=1000, description="Límite de resultados")
class VencimientoRequest(BaseModel):
    """Schema para procesar vencimientos"""
    accion: str = Field(..., description="Acción: renovar, desactivar, indefinido")
    nueva_fecha: Optional[str] = Field(None, description="Nueva fecha de salida si aplica (YYYY-MM-DD)")


class EmpleadoLookupResponse(BaseModel):
    """Schema ultra-ligero para selectores y filtros"""
    id: int
    nombre_completo: str
    rut: str
    area: Optional[str] = None
class ConfirmarAreaRequest(BaseModel):
    """Schema para confirmar cambio de área pendiente"""
    historial_id: int = Field(..., description="ID del registro histórico a validar")
    fecha_efectiva: str = Field(..., description="Fecha en que el cambio se hace efectivo (YYYY-MM-DD)")
    turno_id: Optional[int] = Field(None, description="ID del nuevo turno a asignar (opcional)")

class ReincorporarRequest(BaseModel):
    """Payload para el Wizard de Reincorporación"""
    fecha_inicio: str = Field(..., description="Fecha de re-ingreso (YYYY-MM-DD)")
    fecha_fin: Optional[str] = Field(None, description="Fecha de término estimada si es temporal")
    tipo_contrato: str = Field(..., description="Temporal o Indefinido")
    area: str = Field(..., description="Área asignada")
    cargo: str = Field(..., description="Cargo asignado")
    compania: str = Field(..., description="Compañía")
    turno_id: int = Field(..., description="ID del turno a asignar")

    @model_validator(mode='after')
    def validate_contrato_temporal(self) -> 'ReincorporarRequest':
        """
        [REGLA INVIOLABLE] Validaciones de integridad contractual:
        1. Los contratos Temporales/Plazo Fijo DEBEN tener fecha_fin (impide contratos infinitos por error humano).
        2. Si fecha_fin existe, debe ser estrictamente >= fecha_inicio.
        """
        tipo = (self.tipo_contrato or "").strip()
        
        # Regla 1: Contrato temporal sin fecha de término = error
        if tipo in ("Temporal", "Plazo Fijo") and not self.fecha_fin:
            raise ValueError(
                f"El contrato de tipo '{tipo}' requiere una fecha de término (fecha_fin). "
                "No se permite crear contratos temporales sin fecha de vencimiento."
            )
        
        # Regla 2: Coherencia cronológica
        if self.fecha_fin:
            from datetime import datetime
            try:
                dt_inicio = datetime.strptime(self.fecha_inicio, "%Y-%m-%d")
                dt_fin = datetime.strptime(self.fecha_fin, "%Y-%m-%d")
                if dt_fin < dt_inicio:
                    raise ValueError(
                        f"La fecha de término ({self.fecha_fin}) no puede ser anterior "
                        f"a la fecha de inicio ({self.fecha_inicio})."
                    )
            except ValueError as ve:
                # Si es nuestro error de validación, re-lanzar. Si es de parsing, envolver.
                if "no puede ser anterior" in str(ve) or "requiere una fecha" in str(ve):
                    raise
                raise ValueError(
                    f"Formato de fecha inválido. Use YYYY-MM-DD. "
                    f"Inicio: '{self.fecha_inicio}', Fin: '{self.fecha_fin}'."
                )
        
        return self

