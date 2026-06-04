from fastapi import APIRouter, Depends, Query, HTTPException, Body
from typing import List, Optional
from pydantic import BaseModel

from backend.core.security import SecurityContext, RequirePermission, RequireAnyPermission
from backend.core.database import get_db, Database
from backend.services.productos_4_service import Productos4Service
from backend.repositories.productos_4 import Productos4Repository

router = APIRouter(
    prefix="/productos-4",
    tags=["4 Productos"]
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

class EntregaGuardarRequest(BaseModel):
    empleado_id: int
    mes: int
    anio: int
    entregado: bool

# --- Endpoints de Catálogo de Productos ---

@router.get(
    "/productos",
    response_model=List[ProductoSchema],
    summary="Obtener catálogo de productos de elaboración propia"
)
async def listar_productos(
    incluir_inactivos: bool = Query(False, description="Incluir productos descontinuados"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequireAnyPermission([
        "productos_4.asignar", "productos_4.consolidar", "productos_4.entregar", "productos_4.catalogo"
    ]))
):
    try:
        repo = Productos4Repository()
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
    current_user: SecurityContext = Depends(RequirePermission("productos_4.catalogo"))
):
    try:
        repo = Productos4Repository()
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
                "4 Productos",
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
    current_user: SecurityContext = Depends(RequirePermission("productos_4.catalogo"))
):
    try:
        if codigo != prod.codigo:
            raise HTTPException(status_code=400, detail="El código de producto en la ruta no coincide con el cuerpo.")
            
        repo = Productos4Repository()
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
                "4 Productos",
                f"Modificado producto '{prod.descripcion}' (Código: {codigo}). Activo: {prod.activo}. Máximo: {prod.max_cantidad}."
            )
        )
        return {"success": True, "message": "Producto modificado exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Endpoints de Asignación, Evaluación, Consolidado y Entregas ---

@router.get(
    "/evaluacion",
    summary="Evaluar y listar el estado de calificación de todos los empleados en un periodo con RLS"
)
async def evaluar_periodo(
    mes: int = Query(..., description="Mes a evaluar (1-12)"),
    anio: int = Query(..., description="Año a evaluar"),
    area: Optional[str] = Query(None, description="Filtrar por área específica"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("productos_4.asignar"))
):
    try:
        if not (1 <= mes <= 12):
            raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
            
        # RLS: Filtrar por áreas permitidas para el usuario logueado
        requested_areas = [area] if area else None
        areas_permitidas = current_user.filtrar_areas(requested_areas)
        
        # Si el usuario no tiene acceso a ninguna de las áreas solicitadas
        if areas_permitidas is not None and not areas_permitidas:
            return []
            
        service = Productos4Service()
        resultados = await service.evaluar_beneficio_empleados(mes, anio, areas=areas_permitidas)
        return resultados
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al evaluar periodo: {str(e)}")

@router.post(
    "/asignaciones",
    summary="Guardar selección de productos para un empleado calificado con RLS"
)
async def guardar_asignacion(
    req: AsignacionGuardarRequest = Body(...),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("productos_4.asignar"))
):
    try:
        # RLS: Verificar pertenencia del empleado a un área accesible por el usuario
        emp_row = await db.fetch_one("""
            SELECT a.nombre as area_nombre 
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1
            LEFT JOIN areas a ON ha.area_id = a.id
            WHERE e.id = ?
        """, (req.empleado_id,))
        
        if not emp_row:
            raise HTTPException(status_code=404, detail="Empleado no encontrado")
            
        area_nombre = emp_row["area_nombre"] or ""
        current_user.verificar_acceso_area(area_nombre, f"asignar productos al empleado ID: {req.empleado_id}")

        service = Productos4Service()
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
                "4 Productos",
                f"Asignados productos {req.codigos} al empleado ID: {req.empleado_id} para el periodo {req.anio}-{req.mes:02d}."
            )
        )
        return {"success": True, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/consolidado",
    summary="Obtener reporte consolidado global de asignaciones del periodo (sin RLS)"
)
async def obtener_consolidado(
    mes: int = Query(..., description="Mes (1-12)"),
    anio: int = Query(..., description="Año"),
    area: Optional[str] = Query(None, description="Filtrar por área específica"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("productos_4.consolidar"))
):
    try:
        if not (1 <= mes <= 12):
            raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
            
        # Sin RLS: Permitir filtrar por area si se pasa en query, pero sin limitar por RLS de usuario
        areas_filtro = [area] if area else None
            
        service = Productos4Service()
        consolidado = await service.get_consolidado_periodo(mes, anio, areas=areas_filtro)
        return consolidado
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener consolidado: {str(e)}")

@router.get(
    "/entregas",
    summary="Obtener checklist global de entregas de productos propios para despacho (sin RLS)"
)
async def listar_entregas(
    mes: int = Query(..., description="Mes (1-12)"),
    anio: int = Query(..., description="Año"),
    area: Optional[str] = Query(None, description="Filtrar por área"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("productos_4.entregar"))
):
    try:
        if not (1 <= mes <= 12):
            raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
            
        # Sin RLS: Listar todas las asignaciones a despachar para las áreas indicadas o todas
        areas_filtro = [area] if area else None
        
        service = Productos4Service()
        consolidado = await service.get_consolidado_periodo(mes, anio, areas=areas_filtro)
        # Devolver directamente la lista de detalles del consolidado ya que contiene el listado de empleados
        return consolidado.get("detalles", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar entregas: {str(e)}")

@router.post(
    "/entregar",
    summary="Registrar la entrega física del beneficio de productos propios (sin RLS)"
)
async def registrar_entrega(
    req: EntregaGuardarRequest = Body(...),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("productos_4.entregar"))
):
    try:
        service = Productos4Service()
        success, message = await service.marcar_entrega_producto(
            empleado_id=req.empleado_id,
            mes=req.mes,
            anio=req.anio,
            entregado=req.entregado,
            usuario_entrega_id=current_user.user_id
        )
        if not success:
            raise HTTPException(status_code=400, detail=message)
            
        # Registrar en auditoría
        accion = "DELIVER_PRODUCTOS_PROPIOS" if req.entregado else "REVERT_DELIVER_PRODUCTOS_PROPIOS"
        detalle = f"Marcada como entregada la asignación del empleado ID: {req.empleado_id} para {req.anio}-{req.mes:02d}." if req.entregado else f"Revertida a pendiente la entrega del empleado ID: {req.empleado_id} para {req.anio}-{req.mes:02d}."
        
        await db.execute(
            "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
            (
                current_user.user_id,
                current_user.username,
                accion,
                "4 Productos",
                detalle
            )
        )
        return {"success": True, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CierrePeriodoRequest(BaseModel):
    mes: int
    anio: int

@router.get(
    "/periodo/status",
    summary="Obtener el estado de asignación (abierto, cerrado, bloqueado) de un periodo"
)
async def get_periodo_status(
    mes: int = Query(..., description="Mes (1-12)"),
    anio: int = Query(..., description="Año"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequireAnyPermission([
        "productos_4.asignar", "productos_4.consolidar", "productos_4.entregar"
    ]))
):
    try:
        if not (1 <= mes <= 12):
            raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
            
        service = Productos4Service()
        status_info = await service.get_period_status(mes, anio)
        return status_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/periodo/cerrar",
    summary="Cerrar el período actual para impedir nuevas asignaciones"
)
async def api_cerrar_periodo(
    req: CierrePeriodoRequest = Body(...),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("productos_4.asignar"))
):
    try:
        if not (1 <= req.mes <= 12):
            raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
            
        service = Productos4Service()
        success, message = await service.cerrar_periodo(req.mes, req.anio, current_user.user_id)
        if not success:
            raise HTTPException(status_code=400, detail=message)
            
        # Registrar en auditoría
        await db.execute(
            "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
            (
                current_user.user_id,
                current_user.username,
                "CLOSE_PERIOD_PRODUCTOS_4",
                "4 Productos",
                f"Cerrado período de asignación de productos propios para {req.anio}-{req.mes:02d}."
            )
        )
        return {"success": True, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/periodo/reabrir",
    summary="Reabrir un período de asignación previamente cerrado (Súper Administrador / Bypass)"
)
async def api_reabrir_periodo(
    req: CierrePeriodoRequest = Body(...),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("productos_4.catalogo"))  # Quien edita catálogo puede reabrir
):
    try:
        if not (1 <= req.mes <= 12):
            raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
            
        service = Productos4Service()
        success, message = await service.reabrir_periodo(req.mes, req.anio)
        if not success:
            raise HTTPException(status_code=400, detail=message)
            
        # Registrar en auditoría
        await db.execute(
            "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
            (
                current_user.user_id,
                current_user.username,
                "REOPEN_PERIOD_PRODUCTOS_4",
                "4 Productos",
                f"Reabierto período de asignación de productos propios para {req.anio}-{req.mes:02d}."
            )
        )
        return {"success": True, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

