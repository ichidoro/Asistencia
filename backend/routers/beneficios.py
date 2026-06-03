from fastapi import APIRouter, Depends, Query, HTTPException, Body
from typing import List, Optional
from pydantic import BaseModel

from backend.core.security import SecurityContext, RequirePermission
from backend.core.database import get_db, Database
from backend.services.beneficio_service import BeneficioService
from backend.repositories.beneficio import BeneficioRepository

router = APIRouter(
    prefix="/beneficios",
    tags=["Beneficios"]
)

# --- Modelos Pydantic ---

class ProductoSchema(BaseModel):
    codigo: int
    descripcion: str
    tipo: str
    marca: str
    unidad: str
    max_cantidad: int
    activo: Optional[bool] = True

class AsignacionGuardarRequest(BaseModel):
    empleado_id: int
    mes: int
    anio: int
    codigos: List[Optional[int]]
    observaciones: Optional[str] = ""

# --- Endpoints de Catálogo de Productos ---

@router.get(
    "/productos",
    response_model=List[ProductoSchema],
    summary="Obtener catálogo de productos de elaboración propia"
)
async def listar_productos(
    incluir_inactivos: bool = Query(False, description="Incluir productos descontinuados"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("beneficios.ver"))
):
    try:
        repo = BeneficioRepository()
        productos = await repo.get_all_productos(incluir_inactivos=incluir_inactivos)
        return productos
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo productos: {str(e)}")

@router.post(
    "/productos",
    summary="Agregar un nuevo producto al catálogo"
)
async def crear_producto(
    prod: ProductoSchema = Body(...),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("beneficios.editar"))
):
    try:
        repo = BeneficioRepository()
        # Verificar si ya existe
        existente = await repo.get_producto_by_codigo(prod.codigo)
        if existente:
            raise HTTPException(status_code=400, detail=f"Ya existe un producto con el código {prod.codigo}.")
            
        success = await repo.create_producto(
            codigo=prod.codigo,
            descripcion=prod.descripcion,
            tipo=prod.tipo,
            marca=prod.marca,
            unidad=prod.unidad,
            max_cantidad=prod.max_cantidad
        )
        if not success:
            raise HTTPException(status_code=500, detail="Fallo al insertar el producto en la base de datos.")
            
        # Registrar en auditoría
        await db.execute(
            "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
            (
                current_user.user_id,
                current_user.username,
                "CREATE_PRODUCTO_PROPIO",
                "Beneficios",
                f"Creado producto '{prod.descripcion}' (Código: {prod.codigo}) con límite de {prod.max_cantidad} unidades."
            )
        )
        return {"success": True, "message": "Producto creado exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put(
    "/productos/{codigo}",
    summary="Modificar un producto del catálogo"
)
async def editar_producto(
    codigo: int,
    prod: ProductoSchema = Body(...),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("beneficios.editar"))
):
    try:
        if codigo != prod.codigo:
            raise HTTPException(status_code=400, detail="El código de producto en la ruta no coincide con el cuerpo.")
            
        repo = BeneficioRepository()
        existente = await repo.get_producto_by_codigo(codigo)
        if not existente:
            raise HTTPException(status_code=404, detail="El producto no existe en el catálogo.")
            
        success = await repo.update_producto(
            codigo=codigo,
            descripcion=prod.descripcion,
            tipo=prod.tipo,
            marca=prod.marca,
            unidad=prod.unidad,
            max_cantidad=prod.max_cantidad,
            activo=prod.activo
        )
        if not success:
            raise HTTPException(status_code=500, detail="Fallo al actualizar el producto en la base de datos.")
            
        # Registrar en auditoría
        await db.execute(
            "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
            (
                current_user.user_id,
                current_user.username,
                "UPDATE_PRODUCTO_PROPIO",
                "Beneficios",
                f"Modificado producto '{prod.descripcion}' (Código: {codigo}). Activo: {prod.activo}. Máximo: {prod.max_cantidad}."
            )
        )
        return {"success": True, "message": "Producto modificado exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Endpoints de Asignación y Evaluación ---

@router.get(
    "/evaluacion",
    summary="Evaluar y listar el estado del beneficio de todos los empleados en un periodo"
)
async def evaluar_periodo(
    mes: int = Query(..., description="Mes a evaluar (1-12)"),
    anio: int = Query(..., description="Año a evaluar"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("beneficios.ver"))
):
    try:
        if not (1 <= mes <= 12):
            raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
            
        service = BeneficioService()
        resultados = await service.evaluar_beneficio_empleados(mes, anio)
        return resultados
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al evaluar periodo: {str(e)}")

@router.post(
    "/asignaciones",
    summary="Guardar selección de productos para un empleado calificado"
)
async def guardar_asignacion(
    req: AsignacionGuardarRequest = Body(...),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("beneficios.editar"))
):
    try:
        service = BeneficioService()
        success, message = await service.guardar_seleccion_productos(
            empleado_id=req.empleado_id,
            mes=req.mes,
            anio=req.anio,
            codigos=req.codigos,
            observaciones=req.observaciones,
            usuario_creador_id=current_user.user_id
        )
        if not success:
            raise HTTPException(status_code=400, detail=message)
            
        # Registrar en auditoría
        await db.execute(
            "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
            (
                current_user.user_id,
                current_user.username,
                "ASSIGN_PRODUCTOS_PROPIOS",
                "Beneficios",
                f"Asignados productos {req.codigos} al empleado ID: {req.empleado_id} para el periodo {req.anio}-{req.mes:02d}."
            )
        )
        return {"success": True, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
