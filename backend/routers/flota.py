from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
from loguru import logger

from backend.core.config import settings
from backend.core.database import get_db, Database
from backend.core.security import SecurityContext, get_current_user, RequirePermission, RequireAnyPermission
from backend.repositories.flota import FlotaRepository

router = APIRouter(
    prefix="/flota",
    tags=["Flota Aguacol"]
)

def _now_chile():
    """Retorna datetime naive en hora de Chile"""
    tz = ZoneInfo(settings.TIMEZONE)  # "America/Santiago"
    return datetime.now(tz).replace(tzinfo=None)

def _diff_minutes(f1: str, h1: str, f2: str, h2: str) -> float:
    """Calcula la diferencia en minutos entre dos timestamps de fecha y hora"""
    try:
        dt1 = datetime.strptime(f"{f1} {h1}", "%Y-%m-%d %H:%M:%S")
        dt2 = datetime.strptime(f"{f2} {h2}", "%Y-%m-%d %H:%M:%S")
        return max(0.0, (dt2 - dt1).total_seconds() / 60.0)
    except Exception as e:
        logger.warning(f"Error parseando fechas/horas para diff: {f1} {h1} vs {f2} {h2} - {e}")
        return 0.0

@router.get("/maestro/", response_model=List[Dict[str, Any]])
async def get_maestro(
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequireAnyPermission(["configuracion.flota", "porteria.flota"]))
):
    """Obtener catálogo de vehículos activos"""
    repo = FlotaRepository(db)
    vehiculos = await repo.get_all_vehiculos()
    
    # RLS de área
    areas_permitidas = current_user.get_areas_filter()
    if areas_permitidas is not None:
        vehiculos = [v for v in vehiculos if v["area_nombre"] in areas_permitidas]
        
    return vehiculos

@router.post("/maestro/", status_code=201)
async def create_vehiculo(
    data: Dict[str, Any],
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("configuracion.flota"))
):
    """Registrar un vehículo en el catálogo"""
    patente = data.get("patente")
    area_id = data.get("area_id")
    if not patente or not area_id:
        raise HTTPException(status_code=400, detail="Patente y área son requeridas")
    
    # RLS: Verificar acceso al área destino
    area = await db.fetch_one("SELECT nombre FROM areas WHERE id = ?", (area_id,))
    if not area:
        raise HTTPException(status_code=404, detail="El área seleccionada no existe")
    current_user.verificar_acceso_area(area["nombre"], "crear vehículos en esta área")

    repo = FlotaRepository(db)
    try:
        v_id = await repo.create_vehiculo(patente, area_id)
        # Auditoría
        auditor_nombre = current_user.username or "Sistema"
        await db.execute(
            "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
            (current_user.user_id if hasattr(current_user, 'user_id') else None, 
             auditor_nombre, "CREATE", "Flota Aguacol", f"Vehículo registrado: {patente.upper().strip()}")
        )
        return {"ok": True, "id": v_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/maestro/{v_id}/")
async def update_vehiculo(
    v_id: int,
    data: Dict[str, Any],
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("configuracion.flota"))
):
    """Editar un vehículo del catálogo"""
    patente = data.get("patente")
    area_id = data.get("area_id")
    if not patente or not area_id:
        raise HTTPException(status_code=400, detail="Patente y área son requeridas")
    
    repo = FlotaRepository(db)
    vehiculo = await repo.get_vehiculo_by_id(v_id)
    if not vehiculo:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")

    # RLS: Verificar acceso al área original del vehículo
    current_user.verificar_acceso_area(vehiculo["area_nombre"], "editar este vehículo")

    # RLS: Verificar acceso al área nueva de destino
    nueva_area = await db.fetch_one("SELECT nombre FROM areas WHERE id = ?", (area_id,))
    if not nueva_area:
        raise HTTPException(status_code=404, detail="El área seleccionada no existe")
    current_user.verificar_acceso_area(nueva_area["nombre"], "asignar vehículos a esta área")

    try:
        ok = await repo.update_vehiculo(v_id, patente, area_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Vehículo no encontrado")
        # Auditoría
        auditor_nombre = current_user.username or "Sistema"
        await db.execute(
            "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
            (current_user.user_id if hasattr(current_user, 'user_id') else None, 
             auditor_nombre, "UPDATE", "Flota Aguacol", f"Vehículo ID {v_id} modificado: {patente.upper().strip()}")
        )
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/maestro/{v_id}/")
async def delete_vehiculo(
    v_id: int,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("configuracion.flota"))
):
    """Borrado lógico de un vehículo del catálogo"""
    repo = FlotaRepository(db)
    vehiculo = await repo.get_vehiculo_by_id(v_id)
    if not vehiculo:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")

    # RLS: Verificar acceso al área del vehículo
    current_user.verificar_acceso_area(vehiculo["area_nombre"], "eliminar este vehículo")
    
    ok = await repo.delete_vehiculo(v_id)
    if ok:
        # Auditoría
        auditor_nombre = current_user.username or "Sistema"
        await db.execute(
            "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
            (current_user.user_id if hasattr(current_user, 'user_id') else None, 
             auditor_nombre, "DELETE", "Flota Aguacol", f"Vehículo ID {v_id} ({vehiculo['patente']}) desactivado")
        )
    return {"ok": ok}

@router.get("/estado-dia/")
async def get_estado_dia(
    fecha: Optional[str] = Query(None, description="Fecha YYYY-MM-DD, default hoy"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("porteria.flota"))
):
    """
    Retorna el estado diario consolidado de toda la flota de vehículos.
    Calcula de manera exacta:
      - Estado actual (en_planta, fuera, sin_registro)
      - Tiempo total acumulado de Estadía en Planta (hoy)
      - Tiempo total acumulado en Viaje / Fuera (hoy)
      - Cantidad de Viajes Completados (hoy)
      - Cronología de marcas por vehículo (ordenada por ID ASC)
    """
    repo = FlotaRepository(db)
    
    now = _now_chile()
    fecha_hoy = now.strftime("%Y-%m-%d")
    
    if not fecha:
        fecha = fecha_hoy
        
    es_hoy = (fecha == fecha_hoy)

    # 1. Obtener todos los vehículos activos
    vehiculos = await repo.get_all_vehiculos(incluir_inactivos=False)
    
    # RLS de área
    areas_permitidas = current_user.get_areas_filter()
    if areas_permitidas is not None:
        vehiculos = [v for v in vehiculos if v["area_nombre"] in areas_permitidas]
    
    # 2. Obtener todas las marcas registradas para esta fecha
    marcas = await repo.get_registros_dia(fecha)
    
    # Agrupar marcas por flota_id (ya vienen ordenadas por r.id ASC, que es cronológico)
    marcas_por_vehiculo = {}
    for m in marcas:
        fid = m["flota_id"]
        if fid not in marcas_por_vehiculo:
            marcas_por_vehiculo[fid] = []
        marcas_por_vehiculo[fid].append(m)

    resultado = []
    
    for veh in vehiculos:
        fid = veh["id"]
        veh_marcas = marcas_por_vehiculo.get(fid, [])
        
        # Cargar última marca anterior para heredabilidad de estado
        prev_mark = await repo.get_ultimo_registro_antes(fid, fecha)
        
        # Determinar estado inicial a las 00:00:00
        if prev_mark:
            initial_state = "en_planta" if prev_mark["tipo"] == "ENTRADA" else "fuera"
        else:
            # Por defecto, si no hay marcas previas en la historia, se asume que inicia en planta
            initial_state = "en_planta"

        # Construir lista extendida con marca virtual al inicio del día si aplica
        full_marcas = []
        if initial_state in ("en_planta", "fuera"):
            virtual_tipo = "ENTRADA" if initial_state == "en_planta" else "SALIDA"
            virtual_mark = {
                "id": -1,
                "flota_id": fid,
                "tipo": virtual_tipo,
                "fecha": fecha,
                "hora": "00:00:00",
                "registrado_por_id": None,
                "registrado_por_nombre": "Sistema",
                "observaciones": "Estado heredado del día anterior" if prev_mark else "Estado inicial por defecto",
                "virtual": True
            }
            full_marcas.append(virtual_mark)
        
        full_marcas.extend(veh_marcas)

        # Reconstruir datetimes cronológicos considerando el cruce de medianoche
        dts = []
        for idx, m in enumerate(full_marcas):
            dt = datetime.strptime(f"{m['fecha']} {m['hora']}", "%Y-%m-%d %H:%M:%S")
            if idx > 0:
                prev_m = full_marcas[idx - 1]
                prev_dt = dts[idx - 1]
                if m["fecha"] == prev_m["fecha"] and m["hora"] < prev_m["hora"]:
                    dt = dt + timedelta(days=1)
                elif dt < prev_dt:
                    days_diff = (prev_dt.date() - dt.date()) + (1 if m["hora"] < prev_m["hora"] else 0)
                    dt = dt + timedelta(days=max(1, days_diff))
            dts.append(dt)

        estadia_min = 0.0
        viaje_min = 0.0
        viajes_completados = 0
        
        # Procesar pares de marcas cronológicamente
        i = 0
        while i < len(full_marcas):
            m = full_marcas[i]
            dt_curr = dts[i]
            
            # Estadía (ENTRADA -> SALIDA)
            if m["tipo"] == "ENTRADA":
                if i + 1 < len(full_marcas) and full_marcas[i+1]["tipo"] == "SALIDA":
                    diff = (dts[i+1] - dt_curr).total_seconds() / 60.0
                    estadia_min += max(0.0, diff)
            
            # Viaje (SALIDA -> ENTRADA)
            elif m["tipo"] == "SALIDA":
                if i + 1 < len(full_marcas) and full_marcas[i+1]["tipo"] == "ENTRADA":
                    diff = (dts[i+1] - dt_curr).total_seconds() / 60.0
                    viaje_min += max(0.0, diff)
                    viajes_completados += 1
            i += 1
            
        # Evaluar sesión activa / abierta al final del periodo
        ultima_marca = full_marcas[-1] if full_marcas else None
        
        if ultima_marca:
            dt_ultima = dts[-1]
            if es_hoy:
                end_point = now
            else:
                end_point = datetime.strptime(f"{fecha} 23:59:59", "%Y-%m-%d %H:%M:%S")
                
            diff_activo = (end_point - dt_ultima).total_seconds() / 60.0
            diff_activo = max(0.0, diff_activo)
            
            if ultima_marca["tipo"] == "ENTRADA":
                estadia_min += diff_activo
            elif ultima_marca["tipo"] == "SALIDA":
                viaje_min += diff_activo

        # Formatear estadía
        estadia_h = int(estadia_min // 60)
        estadia_m = int(estadia_min % 60)
        estadia_display = f"{estadia_h}h {estadia_m:02d}m" if estadia_min > 0 else "—"
        if es_hoy and ultima_marca and ultima_marca["tipo"] == "ENTRADA":
            estadia_display += " ⏳"

        # Formatear viaje
        viaje_h = int(viaje_min // 60)
        viaje_m = int(viaje_min % 60)
        viaje_display = f"{viaje_h}h {viaje_m:02d}m" if viaje_min > 0 else "—"
        if es_hoy and ultima_marca and ultima_marca["tipo"] == "SALIDA":
            viaje_display += " ⏳"

        # Estado visual
        estado = "sin_registro"
        if ultima_marca:
            estado = "en_planta" if ultima_marca["tipo"] == "ENTRADA" else "fuera"

        # Obtener chofer activo para autocompletar si está "fuera" (en viaje/ruta)
        chofer_activo = None
        if estado == "fuera" and ultima_marca:
            # Buscar el registro de salida real (ya sea hoy o el heredado de ayer)
            salida_real = None
            for m in reversed(full_marcas):
                if m["tipo"] == "SALIDA":
                    salida_real = m
                    break
            
            if not salida_real or salida_real.get("virtual"):
                ultimo_global_marca = await repo.get_ultimo_registro_global(fid)
                if ultimo_global_marca and ultimo_global_marca["tipo"] == "SALIDA":
                    salida_real = ultimo_global_marca
            
            if salida_real and salida_real.get("observaciones"):
                obs = salida_real["observaciones"]
                match = re.search(r"Chofer:\s*([^.]+)", obs)
                if match:
                    chofer_activo = match.group(1).strip()

        resultado.append({
            "id": fid,
            "patente": veh["patente"],
            "area_id": veh["area_id"],
            "area": veh["area_nombre"],
            "estado": estado,
            "marcas": veh_marcas,
            "ultima_marca": ultima_marca["hora"] if (ultima_marca and not ultima_marca.get("virtual")) else (prev_mark["hora"] if prev_mark else None),
            "ultima_marca_tipo": ultima_marca["tipo"] if ultima_marca else None,
            "estadia_total_min": round(estadia_min, 1),
            "estadia_display": estadia_display,
            "viaje_total_min": round(viaje_min, 1),
            "viaje_display": viaje_display,
            "viajes_completados": viajes_completados,
            "chofer_activo": chofer_activo
        })

    # Estadísticas resumidas
    total = len(resultado)
    en_planta = sum(1 for r in resultado if r["estado"] == "en_planta")
    en_viaje = sum(1 for r in resultado if r["estado"] == "fuera")
    sin_registro = total - en_planta - en_viaje

    return {
        "fecha": fecha,
        "stats": {
            "total": total,
            "en_planta": en_planta,
            "en_viaje": en_viaje,
            "sin_registro": sin_registro
        },
        "vehiculos": resultado
    }


@router.post("/marcar/")
async def marcar(
    data: Dict[str, Any],
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("porteria.flota"))
):
    """
    Registrar una marca de entrada o salida para un vehículo.
    Determina secuencialmente el tipo opuesto a la última marca global.
    Resuelve sesiones cross-midnight unificando la fecha del fin de sesión a la del inicio.
    """
    flota_id = data.get("flota_id")
    observaciones = data.get("observaciones", "")
    if not flota_id:
        raise HTTPException(status_code=400, detail="flota_id requerido")

    repo = FlotaRepository(db)
    vehiculo = await repo.get_vehiculo_by_id(flota_id)
    if not vehiculo:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")

    # RLS: Verificar acceso al área del vehículo
    current_user.verificar_acceso_area(vehiculo["area_nombre"], "este vehículo de la flota")

    # Fecha y hora actual (Chile)
    now = _now_chile()
    fecha_hoy = now.strftime("%Y-%m-%d")
    hora_actual = now.strftime("%H:%M:%S")

    # Obtener última marca global del vehículo
    ultima = await repo.get_ultimo_registro_global(flota_id)
    nuevo_tipo = "ENTRADA" if (not ultima or ultima["tipo"] == "SALIDA") else "SALIDA"

    # Cross-Midnight: Si la última marca ocurrió en un día diferente a hoy,
    # atribuimos esta nueva marca a la fecha de esa última marca
    if ultima and ultima["fecha"] != fecha_hoy:
        fecha_registro = ultima["fecha"]
        logger.info(f"[FLOTA] Cross-midnight detectado para patente {vehiculo['patente']}: marca '{nuevo_tipo}' de hoy {fecha_hoy} atribuida a {fecha_registro}")
    else:
        fecha_registro = fecha_hoy

    # Registrador
    registrador = f"{current_user.nombre_completo}" if hasattr(current_user, 'nombre_completo') else (current_user.username or "Sistema")

    await repo.marcar_movimiento(
        flota_id=flota_id,
        tipo=nuevo_tipo,
        fecha=fecha_registro,
        hora=hora_actual,
        registrado_por_id=current_user.user_id if hasattr(current_user, 'user_id') else None,
        registrado_por_nombre=registrador,
        observaciones=observaciones
    )

    return {
        "ok": True,
        "tipo": nuevo_tipo,
        "tipo_label": "ENTRADA" if nuevo_tipo == "ENTRADA" else "SALIDA",
        "hora": hora_actual,
        "flota_id": flota_id,
        "patente": vehiculo["patente"]
    }

@router.get("/historial/")
async def get_historial(
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    area_id: Optional[int] = Query(None),
    patente: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("porteria.flota"))
):
    """Obtener el historial de marcas con filtros y paginación"""
    # RLS: verificar acceso si especificó un área
    if area_id:
        area_obj = await db.fetch_one("SELECT nombre FROM areas WHERE id = ?", (area_id,))
        if area_obj:
            current_user.verificar_acceso_area(area_obj["nombre"], "el área solicitada")

    repo = FlotaRepository(db)
    
    # Valores por defecto de fecha si faltan
    now = _now_chile()
    if not hasta:
        hasta = now.strftime("%Y-%m-%d")
    if not desde:
        # Últimos 7 días por defecto
        desde = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    # Obtener áreas permitidas para RLS
    areas_permitidas = current_user.get_areas_filter()

    return await repo.get_historial(
        desde=desde,
        hasta=hasta,
        area_id=area_id,
        patente=patente,
        page=page,
        limit=limit,
        areas_permitidas=areas_permitidas
    )
