"""
Router Llaves — Entrega y Devolución de Llaves
Gestión de llaves con control de autorizaciones por empleado
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from backend.core.database import get_db, Database
from backend.core.security import SecurityContext, get_current_user, RequirePermission
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from backend.core.config import settings

def _now_chile():
    tz = ZoneInfo(settings.TIMEZONE)  # "America/Santiago"
    return datetime.now(tz).replace(tzinfo=None)
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/llaves", tags=["Llaves"])


# ============================================
# SCHEMAS
# ============================================

class LlaveCreate(BaseModel):
    nombre: str
    ubicacion: str

class LlaveUpdate(BaseModel):
    nombre: Optional[str] = None
    ubicacion: Optional[str] = None

class RegistroLlave(BaseModel):
    llave_id: int
    empleado_id: int
    tipo: str  # ENTREGA or DEVOLUCION
    observaciones: Optional[str] = ''


# ============================================
# INICIALIZACIÓN DE TABLAS
# ============================================

async def _ensure_tables(db: Database):
    """Crea las tablas si no existen."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS llaves_maestro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            ubicacion TEXT NOT NULL,
            activo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS llaves_registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            llave_id INTEGER NOT NULL,
            empleado_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            registrado_por_id INTEGER,
            registrado_por_nombre TEXT,
            observaciones TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (llave_id) REFERENCES llaves_maestro(id),
            FOREIGN KEY (empleado_id) REFERENCES empleados(id)
        )
    """)


# ============================================
# ENDPOINTS - MAESTRO DE LLAVES
# ============================================

@router.get("/maestro/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def listar_llaves(db: Database = Depends(get_db)):
    """Listar todas las llaves activas"""
    await _ensure_tables(db)
    rows = await db.fetch_all("SELECT * FROM llaves_maestro WHERE activo = 1 ORDER BY nombre")
    return [{"id": r["id"], "nombre": r["nombre"], "ubicacion": r["ubicacion"]} for r in rows]


@router.post("/maestro/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def crear_llave(data: LlaveCreate, db: Database = Depends(get_db)):
    """Crear una nueva llave"""
    await _ensure_tables(db)
    await db.execute(
        "INSERT INTO llaves_maestro (nombre, ubicacion) VALUES (?, ?)",
        (data.nombre, data.ubicacion)
    )
    return {"ok": True, "message": f"Llave '{data.nombre}' creada"}


@router.put("/maestro/{llave_id}/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def actualizar_llave(llave_id: int, data: LlaveUpdate, db: Database = Depends(get_db)):
    """Actualizar datos de una llave"""
    await _ensure_tables(db)
    updates, params = [], []
    if data.nombre is not None:
        updates.append("nombre = ?")
        params.append(data.nombre)
    if data.ubicacion is not None:
        updates.append("ubicacion = ?")
        params.append(data.ubicacion)
    if not updates:
        raise HTTPException(400, "Nada que actualizar")
    params.append(llave_id)
    await db.execute(
        f"UPDATE llaves_maestro SET {', '.join(updates)} WHERE id = ?",
        tuple(params)
    )
    return {"ok": True}


@router.delete("/maestro/{llave_id}/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def eliminar_llave(llave_id: int, db: Database = Depends(get_db)):
    """Desactivar una llave (soft delete)"""
    await _ensure_tables(db)
    await db.execute("UPDATE llaves_maestro SET activo = 0 WHERE id = ?", (llave_id,))
    return {"ok": True}


# ============================================
# ENDPOINTS - EMPLEADOS AUTORIZADOS
# ============================================

@router.get("/autorizados/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def listar_autorizados(
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user)
):
    """Listar empleados autorizados para llaves, filtrados por áreas del usuario"""
    areas_filter = current_user.get_areas_filter()
    query = """
        SELECT e.id, e.rut, e.nombre, e.apellido_paterno, e.apellido_materno,
               COALESCE(a.nombre, 'Sin área') as area_nombre
        FROM empleados e
        LEFT JOIN areas a ON e.area_id = a.id
        WHERE e.autorizado_llaves = 1 AND e.activo = 1
    """
    params = []
    if areas_filter is not None:
        placeholders = ','.join(['?' for _ in areas_filter])
        query += f" AND a.nombre IN ({placeholders})"
        params = areas_filter
    query += " ORDER BY e.nombre, e.apellido_paterno"
    rows = await db.fetch_all(query, tuple(params))
    return [
        {
            "id": r["id"],
            "rut": r["rut"],
            "nombre": f"{r['nombre']} {r['apellido_paterno']} {r['apellido_materno']}",
            "area": r["area_nombre"]
        }
        for r in rows
    ]


# ============================================
# ENDPOINTS - ESTADO Y REGISTRO
# ============================================

@router.get("/estado/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def estado_llaves(db: Database = Depends(get_db)):
    """Estado actual de todas las llaves (disponible/entregada)"""
    await _ensure_tables(db)
    llaves = await db.fetch_all("SELECT * FROM llaves_maestro WHERE activo = 1 ORDER BY nombre")
    resultado = []
    for ll in llaves:
        # Buscar último registro para esta llave
        ultimo = await db.fetch_one("""
            SELECT lr.*, e.nombre || ' ' || e.apellido_paterno as empleado_nombre, e.rut as empleado_rut
            FROM llaves_registros lr
            JOIN empleados e ON lr.empleado_id = e.id
            WHERE lr.llave_id = ?
            ORDER BY lr.created_at DESC LIMIT 1
        """, (ll["id"],))
        estado = "DISPONIBLE"
        entregada_a = None
        entregada_hora = None
        if ultimo and ultimo["tipo"] == "ENTREGA":
            estado = "ENTREGADA"
            entregada_a = {
                "nombre": ultimo["empleado_nombre"],
                "rut": ultimo["empleado_rut"],
                "id": ultimo["empleado_id"]
            }
            entregada_hora = f"{ultimo['fecha']} {ultimo['hora']}"
        resultado.append({
            "id": ll["id"],
            "nombre": ll["nombre"],
            "ubicacion": ll["ubicacion"],
            "estado": estado,
            "entregada_a": entregada_a,
            "entregada_hora": entregada_hora
        })
    total = len(resultado)
    disponibles = sum(1 for r in resultado if r["estado"] == "DISPONIBLE")
    return {
        "llaves": resultado,
        "total": total,
        "disponibles": disponibles,
        "fuera": total - disponibles
    }


@router.post("/registrar/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def registrar_movimiento(
    data: RegistroLlave,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user)
):
    """Registrar entrega o devolución de una llave"""
    await _ensure_tables(db)

    # Validar que la llave existe
    llave = await db.fetch_one(
        "SELECT * FROM llaves_maestro WHERE id = ? AND activo = 1",
        (data.llave_id,)
    )
    if not llave:
        raise HTTPException(404, "Llave no encontrada")

    # Validar que el empleado está autorizado
    emp = await db.fetch_one(
        "SELECT * FROM empleados WHERE id = ? AND autorizado_llaves = 1 AND activo = 1",
        (data.empleado_id,)
    )
    if not emp:
        raise HTTPException(403, "Empleado no autorizado para llaves")

    # Validar consistencia lógica
    ultimo = await db.fetch_one("""
        SELECT tipo FROM llaves_registros WHERE llave_id = ? ORDER BY created_at DESC LIMIT 1
    """, (data.llave_id,))

    if data.tipo == "ENTREGA" and ultimo and ultimo["tipo"] == "ENTREGA":
        raise HTTPException(400, "Esta llave ya está entregada. Debe devolverse primero.")
    if data.tipo == "DEVOLUCION" and (not ultimo or ultimo["tipo"] == "DEVOLUCION"):
        raise HTTPException(400, "Esta llave ya está disponible. No hay nada que devolver.")

    now = _now_chile()
    await db.execute("""
        INSERT INTO llaves_registros (llave_id, empleado_id, tipo, fecha, hora, registrado_por_id, registrado_por_nombre, observaciones)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.llave_id, data.empleado_id, data.tipo,
        now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S'),
        current_user.user_id, current_user.username,
        data.observaciones or ''
    ))
    return {"ok": True, "message": f"Llave '{llave['nombre']}' - {data.tipo} registrada"}


# ============================================
# ENDPOINTS - HISTORIAL
# ============================================

@router.get("/historial/", dependencies=[Depends(RequirePermission("porteria.llaves"))])
async def historial_llaves(
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    llave_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db)
):
    """Historial paginado de movimientos de llaves"""
    await _ensure_tables(db)
    where = []
    params = []
    if fecha_desde:
        where.append("lr.fecha >= ?")
        params.append(fecha_desde)
    if fecha_hasta:
        where.append("lr.fecha <= ?")
        params.append(fecha_hasta)
    if llave_id:
        where.append("lr.llave_id = ?")
        params.append(llave_id)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    count_row = await db.fetch_one(
        f"SELECT COUNT(*) as total FROM llaves_registros lr{where_sql}",
        tuple(params)
    )
    total = count_row["total"] if count_row else 0

    offset = (page - 1) * page_size
    rows = await db.fetch_all(f"""
        SELECT lr.*, lm.nombre as llave_nombre, lm.ubicacion,
               e.nombre || ' ' || e.apellido_paterno as empleado_nombre, e.rut as empleado_rut
        FROM llaves_registros lr
        JOIN llaves_maestro lm ON lr.llave_id = lm.id
        JOIN empleados e ON lr.empleado_id = e.id
        {where_sql}
        ORDER BY lr.created_at DESC
        LIMIT ? OFFSET ?
    """, tuple(params) + (page_size, offset))

    registros = [
        {
            "id": r["id"],
            "llave": r["llave_nombre"],
            "ubicacion": r["ubicacion"],
            "empleado": r["empleado_nombre"],
            "rut": r["empleado_rut"],
            "tipo": r["tipo"],
            "fecha": r["fecha"],
            "hora": r["hora"],
            "guardia": r["registrado_por_nombre"],
            "observaciones": r["observaciones"]
        }
        for r in rows
    ]
    return {
        "registros": registros,
        "total": total,
        "page": page,
        "pages": (total + page_size - 1) // page_size
    }


