"""
Modelo de Datos - Empleado
Representa un empleado en el sistema
"""

from datetime import datetime
from typing import Optional
from dataclasses import dataclass


@dataclass
class Empleado:
    """
    Modelo de dominio para Empleado
    
    Atributos principales que se almacenan en la DB
    """
    id: Optional[int] = None
    rut: str = ""
    nombre: str = ""
    apellido_paterno: str = ""
    apellido_materno: str = ""
    genero: Optional[str] = None
    
    # Información laboral
    cargo: Optional[str] = None
    cargo_id: Optional[int] = None
    area_id: Optional[int] = None
    area: Optional[str] = None  # Virtual: Nombre del área
    compania: Optional[str] = None
    
    # Contacto
    email: Optional[str] = None
    telefono: Optional[str] = None
    genero: Optional[str] = None
    genero_id: Optional[int] = None
    activo: bool = True
    
    # Fechas
    fecha_nacimiento: Optional[str] = None  # Formato: YYYY-MM-DD
    fecha_ingreso: Optional[str] = None  # Formato: YYYY-MM-DD
    fecha_salida: Optional[str] = None
    
    # Tipo de contrato
    tipo_contrato: Optional[str] = "Indefinido"  # Indefinido o Temporal
    cant_contratos: int = 1  # Número de contrato actual
    decision_vencimiento: Optional[str] = None  # RENOVAR, NO_RENOVAR, INDEFINIDO
    fecha_asignacion_turno: Optional[str] = None  # Virtual: última asignación
    
    # Auditoría
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    @property
    def nombre_completo(self) -> str:
        """Retorna el nombre completo del empleado en orden formal"""
        return f"{self.apellido_paterno} {self.apellido_materno or ''} {self.nombre}".strip().replace('  ', ' ')
    
    @property
    def rut_formateado(self) -> str:
        """Retorna el RUT con formato XX.XXX.XXX-X"""
        if not self.rut:
            return ""
        
        # Remover puntos y guión si existen
        rut_limpio = self.rut.replace(".", "").replace("-", "")
        
        if len(rut_limpio) < 2:
            return self.rut
        
        # Separar dígito verificador
        digito = rut_limpio[-1]
        numero = rut_limpio[:-1]
        
        # Formatear con puntos
        numero_formateado = ""
        for i, digit in enumerate(reversed(numero)):
            if i > 0 and i % 3 == 0:
                numero_formateado = "." + numero_formateado
            numero_formateado = digit + numero_formateado
        
        return f"{numero_formateado}-{digito}"
    
    def to_dict(self) -> dict:
        """Convierte el modelo a diccionario"""
        return {
            "id": self.id,
            "rut": self.rut,
            "nombre": self.nombre,
            "apellido_paterno": self.apellido_paterno,
            "apellido_materno": self.apellido_materno,
            "cargo": self.cargo,
            "cargo_id": self.cargo_id,
            "area_id": self.area_id,
            "area": self.area,
            "compania": self.compania,
            "email": self.email,
            "telefono": self.telefono,
            "genero": self.genero,
            "genero_id": self.genero_id,
            "activo": self.activo,
            "fecha_nacimiento": self.fecha_nacimiento,
            "fecha_ingreso": self.fecha_ingreso,
            "fecha_salida": self.fecha_salida,
            "tipo_contrato": self.tipo_contrato,
            "cant_contratos": self.cant_contratos,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "fecha_asignacion_turno": self.fecha_asignacion_turno,
            "nombre_completo": self.nombre_completo,
            "rut_formateado": self.rut_formateado
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Empleado":
        """Crea un Empleado desde un diccionario"""
        return cls(
            id=data.get("id"),
            rut=data.get("rut", ""),
            nombre=data.get("nombre", ""),
            apellido_paterno=data.get("apellido_paterno", ""),
            apellido_materno=data.get("apellido_materno", ""),
            cargo=data.get("cargo"),
            cargo_id=data.get("cargo_id"),
            area_id=data.get("area_id"),
            area=data.get("area"),
            compania=data.get("compania"),
            email=data.get("email"),
            telefono=data.get("telefono"),
            genero=data.get("genero"),
            genero_id=data.get("genero_id"),
            activo=bool(data.get("activo", True)),
            fecha_nacimiento=data.get("fecha_nacimiento"),
            fecha_ingreso=data.get("fecha_ingreso"),
            fecha_salida=data.get("fecha_salida"),
            tipo_contrato=data.get("tipo_contrato", "Indefinido"),
            cant_contratos=data.get("cant_contratos", 1),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            fecha_asignacion_turno=data.get("fecha_asignacion_turno")
        )
