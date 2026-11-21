"""
Router - Asistencia
Endpoints para procesar y consultar asistencia
"""

from backend.core.fast_json import fast_json
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from datetime import datetime
from loguru import logger

from backend.services.asistencia_service import AsistenciaService
from backend.services.bono_service import BonoService
from backend.services.empleado_service import EmpleadoService
from backend.services.turno_service import TurnoService
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.empleado import EmpleadoRepository
from backend.repositories.turno import TurnoRepository
from backend.core.database import Database, get_db
from backend.core.security import SecurityContext, RequirePermission


router = APIRouter(
    prefix="/asistencia",
    tags=["Asistencia"]
)

from backend.routers.asistencia_comun import get_asistencia_service  # compartido con los routers de la etapa 6

async def get_bono_service(db: Database = Depends(get_db)) -> BonoService:
    return BonoService(db)

async def get_empleado_service(db: Database = Depends(get_db)) -> EmpleadoService:
    repository = EmpleadoRepository(db)
    return EmpleadoService(repository)

async def get_turno_service(db: Database = Depends(get_db)) -> TurnoService:
    repository = TurnoRepository(db)
    return TurnoService(repository)


@router.get("/auditoria-bloqueo/")
async def get_auditoria_bloqueo(
    fecha: Optional[str] = Query(None, description="AAAA-MM-DD (Default hoy)"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Endpoint CRÍTICO (Plan Maestro): Detecta empleados con marcas (logs_raw) 
    pero sin turno asignado (asignacion_turnos) para el área del usuario actual.
    Utiliza historial_areas (es_actual=1) para una validación dinámica.
    """
    # Ventana de Auditoría: Desde el 1 del mes actual hasta hoy (Propuesta v29 Refinada)
    # Esto asegura que cualquier marca huérfana en el mes bloquee la operación.
    now = datetime.now()
    if not fecha:
        fecha = now.strftime("%Y-%m-%d")
        
    # Calcular el primer día del mes de la 'fecha' solicitada
    try:
        dt_solicitada = datetime.strptime(fecha, "%Y-%m-%d")
        fecha_inicio_mes = dt_solicitada.replace(day=1).strftime("%Y-%m-%d")
    except Exception:
        fecha_inicio_mes = now.replace(day=1).strftime("%Y-%m-%d")

    areas_permitidas = current_user.get_areas_filter()

    # Si no tiene áreas asignadas y no tiene acceso global, no tiene nada que auditar
    if areas_permitidas is not None and not areas_permitidas:
        return {"bloqueo": False, "anomalias": [], "can_bypass": False}

    anomalias = await AsistenciaRepository(db).get_anomalias_de_bloqueo(fecha, fecha_inicio_mes, areas_permitidas)
    
    can_bypass = bool(current_user.alcance_global or current_user.is_superuser)
    logger.info(f"🛡️ Auditoría Bloqueo: {current_user.username} | Bloqueo: {len(anomalias) > 0} | can_bypass: {can_bypass}")
    
    return {
        "bloqueo": len(anomalias) > 0,
        "anomalias": anomalias,
        "count": len(anomalias),
        "fecha_auditada": fecha,
        "desde": fecha_inicio_mes,
        "can_bypass": can_bypass
    }

# ── Caché en memoria de Excels mensuales de BioAlba (nivel módulo) ──────────────
# Clave: (mes: int, anio: int)  →  Valor: list[dict] con todas las marcaciones del mes
# Se reutiliza entre llamadas del mismo proceso: cuando se procesa un área completa,
# cada Excel mensual se descarga UNA sola vez y sirve para todos los empleados.
# TTLCache: expira entradas después de 1h y limita a 15 meses en RAM.
# Un dict plano crecía indefinidamente; con TTLCache se acota el uso de memoria.
from cachetools import TTLCache
_bioalba_mes_cache: TTLCache = TTLCache(maxsize=15, ttl=3600)


@router.get("/empleados/{empleado_id}/primera-marcacion/")
async def get_primera_marcacion_empleado(
    empleado_id: int,
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    RFC Paso 7: Busca en BioAlba la primera marcación biométrica del empleado.

    Optimizaciones:
    1. Escanea de FECHA_LIMITE (ene 2026) → hoy: la 1ª coincidencia es la 1ª marca → para al instante.
    2. Caché de Excels mensuales: en sync de área completa, cada mes se descarga solo 1 vez.

    logs_raw está vacío por el BioAlba Gate (descarta marcaciones sin turno asignado).
    """
    from datetime import date as date_type
    from backend.scraper.bioalba_scraper import BioAlbaScraper

    emp_row = await EmpleadoRepository(db).get_rut(empleado_id)
    if not emp_row:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")

    rut_empleado = emp_row["rut"]

    # ── ÚNICO VALOR HARDCODEADO PERMITIDO EN LA APLICACIÓN ──────────────
    FECHA_LIMITE = date_type(2026, 1, 1)
    # ─────────────────────────────────────────────────────────────────────

    hoy = date_type.today()

    # Construir lista de meses desde el más antiguo al más reciente
    # → la primera coincidencia ES la primera marca, paramos de inmediato
    meses = []
    m, a = FECHA_LIMITE.month, FECHA_LIMITE.year
    while date_type(a, m, 1) <= hoy:
        meses.append((m, a))
        m += 1
        if m > 12:
            m = 1
            a += 1

    primera_fecha = None

    try:
        from backend.services.sync_service import _shared_scraper as scraper
        async with scraper:
            if not await scraper.ensure_logged_in():
                return {"empleado_id": empleado_id, "primera_marcacion": None,
                        "motivo": "No se pudo conectar a BioAlba"}

            for (mes_i, anio_i) in meses:
                clave = (mes_i, anio_i)

                # ── Caché: si ya se descargó este mes en esta sesión, reutilizar ──
                if clave not in _bioalba_mes_cache:
                    _bioalba_mes_cache[clave] = await scraper.get_marcaciones(
                        mes=mes_i, anio=anio_i
                    )
                marcaciones = _bioalba_mes_cache[clave]
                # ──────────────────────────────────────────────────────────────────

                fechas_emp = [
                    m["fecha_hora"][:10]
                    for m in marcaciones
                    if m.get("rut") == rut_empleado and m.get("fecha_hora")
                ]

                if fechas_emp:
                    # Escaneando de antiguo → nuevo: primera coincidencia = primera marca
                    primera_fecha = min(fechas_emp)
                    break  # ← no necesitamos seguir buscando

    except Exception as e:
        logger.error(f"Error buscando primera marcación BioAlba empleado {empleado_id}: {e}")
        return {"empleado_id": empleado_id, "primera_marcacion": None,
                "motivo": f"Error consultando BioAlba: {str(e)}"}

    return {"empleado_id": empleado_id, "primera_marcacion": primera_fecha}


# ── Change-detection para auto-refresh de la grilla ──────────────────────────
# Endpoint ultra-liviano: solo MAX(updated_at) + COUNT(*) para el período.
# El frontend lo pollea cada 30s y si detecta un cambio, recarga la grilla.
# TTLCache multi-clave: 5 usuarios mirando áreas distintas NO se invalidan entre sí.
# Max 20 claves (período+área), TTL 10s → máximo 1 query real cada 10s por combinación.
_change_cache: TTLCache = TTLCache(maxsize=20, ttl=10)

@router.get("/last-change/", summary="Detectar cambios recientes en asistencias")
async def get_last_change(
    fecha_inicio: str = Query(..., description="AAAA-MM-DD"),
    fecha_fin: str = Query(..., description="AAAA-MM-DD"),
    area: Optional[str] = Query(None),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Endpoint de change-detection para auto-refresh inteligente.
    Retorna el timestamp de la última modificación y el conteo de registros.
    El frontend compara estos valores con los anteriores: si cambian, recarga.
    TTLCache multi-clave (10s) para multi-usuario.
    """
    cache_key = f"{fecha_inicio}|{fecha_fin}|{area or 'ALL'}"

    # Cache hit (TTLCache maneja expiración automáticamente)
    if cache_key in _change_cache:
        return _change_cache[cache_key]

    repo_asis = AsistenciaRepository(db)
    row = await repo_asis.get_ultimo_cambio(fecha_inicio, fecha_fin, area, current_user.get_areas_filter())
    raw_row = await repo_asis.get_resumen_marcas_crudas()
    max_raw = raw_row['max_raw_id'] if raw_row and raw_row['max_raw_id'] else 0
    count_raw = raw_row['count_raw'] if raw_row and raw_row['count_raw'] else 0

    last_asist_up = row["last_update"] if row and row["last_update"] else ""
    combined_update = f"{last_asist_up}|raw_{max_raw}_{count_raw}"

    result = {
        "last_update": combined_update,
        "total_records": row["total_records"] if row else 0,
        "cache_key": cache_key,
    }

    _change_cache[cache_key] = result
    return result


@router.get("/reporte/")
async def get_reporte_asistencia(
    fecha_inicio: str = Query(..., description="AAAA-MM-DD"),
    fecha_fin: str = Query(..., description="AAAA-MM-DD"),
    area: Optional[str] = Query(None),
    turno_id: Optional[int] = Query(None),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene la asistencia procesada con RLS.
    """
    if area:
        current_user.verificar_acceso_area(area, "el área solicitada")
    areas_permitidas = current_user.get_areas_filter()

    return fast_json(await service.repository.get_asistencias_periodo(
        fecha_inicio, fecha_fin, area, turno_id=turno_id, areas_permitidas=areas_permitidas
    ))

@router.get("/stats/")
async def get_asistencia_stats(
    fecha: Optional[str] = Query(None, description="AAAA-MM-DD"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene estadísticas de asistencia diarias filtradas por RLS.
    """
    if not fecha:
        fecha = datetime.now().strftime("%Y-%m-%d")
        
    areas_permitidas = current_user.get_areas_filter()
    return await service.get_daily_stats(fecha, areas_permitidas=areas_permitidas)

@router.get("/matrix/")
async def get_asistencia_matrix(
    mes: int = Query(..., ge=1, le=12),
    anio: int = Query(..., ge=2000, le=2100),
    area: Optional[str] = Query(None),
    turno_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    service: AsistenciaService = Depends(get_asistencia_service),
    bono_service: BonoService = Depends(get_bono_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene datos para la Vista Matriz (Equipo) con RLS.
    """
    if area:
        current_user.verificar_acceso_area(area, "el área solicitada")
    areas_permitidas = current_user.get_areas_filter()

    data = await service.get_matrix_data_with_projections(mes, anio, area, turno_id, search=search, areas_permitidas=areas_permitidas)

    # Siempre incluir la lista maestra de todos los bonos activos (columnas estáticas)
    todos_bonos = await bono_service.config_repo.get_all_bonos()
    data["bonos_nombres"] = sorted([b["nombre"] for b in todos_bonos if b.get("activo")])

    # Evaluar cumplimiento de bonos para los empleados del período
    empleados = data.get("empleados", [])
    if empleados:
        asistencias = data.get("data", [])
        justificaciones = data.get("justificaciones", [])
        matrix_data = data.get("matrix", {})
        bonos_eval = await bono_service.evaluar_bonos_directo(
            empleados, asistencias, justificaciones, matrix_data, mes, anio
        )
        data["bonos_evaluacion"] = bonos_eval

    return fast_json(data)



@router.get("/matriz/")
async def get_matriz_asistencia(
    fecha_inicio: str = Query(..., description="AAAA-MM-DD"),
    fecha_fin: str = Query(..., description="AAAA-MM-DD"),
    area: Optional[str] = Query(None),
    turno_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    empleado_id: Optional[int] = Query(None),
    service: AsistenciaService = Depends(get_asistencia_service),
    bono_service: BonoService = Depends(get_bono_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Retorna la matriz de asistencia (días x empleados) para un periodo y área.
    Implementa RLS para limitar visualización según áreas permitidas.
    """
    # RLS: verificar acceso al área solicitada y calcular filtro
    if area:
        current_user.verificar_acceso_area(area, "el área solicitada")
    areas_permitidas = current_user.get_areas_filter()
    area_filter = area

    # Guard: si llegan fechas vacías (carga inicial sin selector configurado), usar mes actual
    if not fecha_inicio or not fecha_fin:
        from datetime import datetime as _dt_now
        import calendar as _cal
        hoy = _dt_now.today()
        fecha_inicio = hoy.replace(day=1).strftime("%Y-%m-%d")
        last_day = _cal.monthrange(hoy.year, hoy.month)[1]
        fecha_fin = hoy.replace(day=last_day).strftime("%Y-%m-%d")

    data = await service.get_matriz_periodo(fecha_inicio, fecha_fin, area_filter, turno_id, search, areas_permitidas=areas_permitidas, empleado_id=empleado_id)
    
    # Siempre incluir la lista maestra de todos los bonos activos (columnas estáticas)
    todos_bonos = await bono_service.config_repo.get_all_bonos()
    data["bonos_nombres"] = sorted([b["nombre"] for b in todos_bonos if b.get("activo")])

    # Evaluar cumplimiento de bonos para los empleados del período
    if "empleados" in data and data["empleados"]:
        empleados = data["empleados"]
        asistencias = data.get("data", [])
        justificaciones = data.get("justificaciones", [])
        matrix_data = data.get("matrix", {})
        
        mes_eval = None
        anio_eval = None
        if fecha_inicio:
            try:
                from datetime import datetime as _dt
                dt_start = _dt.strptime(fecha_inicio, "%Y-%m-%d")
                mes_eval = dt_start.month
                anio_eval = dt_start.year
            except Exception:
                pass

        bonos_eval = await bono_service.evaluar_bonos_directo(
            empleados, asistencias, justificaciones, matrix_data, mes_eval, anio_eval
        )
        data["bonos_evaluacion"] = bonos_eval

    return fast_json(data)


@router.get("/calendar/")
async def get_asistencia_calendar(
    empleado_id: int = Query(...),
    mes: Optional[int] = Query(None, ge=1, le=12),
    anio: Optional[int] = Query(None, ge=2000, le=2100),
    fecha_inicio: Optional[str] = Query(None),
    fecha_fin: Optional[str] = Query(None),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene datos para la Vista Calendario (Personal) con RLS.
    Retorna asistencias de todo el mes o periodo para un empleado específico,
    incluyendo proyecciones de feriados y justificaciones.
    """
    if not ((mes and anio) or (fecha_inicio and fecha_fin)):
        raise HTTPException(status_code=400, detail="Debe proveer mes y anio, o fecha_inicio y fecha_fin")

    # RLS: Verificar pertenencia
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    current_user.verificar_acceso_area(emp.area, "el calendario de este empleado")
    # Usar la lógica de matriz enriquecida con proyecciones
    rich_data = await service.get_matrix_data_with_projections(
        mes=mes or 1, 
        anio=anio or 2026, 
        empleado_id=empleado_id,
        fecha_inicio_override=fecha_inicio,
        fecha_fin_override=fecha_fin
    )
    
    # Extraer los días del único empleado en una lista plana para el calendario
    flat_data = []
    matrix = rich_data.get("matrix", {})
    
    # El empleado_id es la clave principal en rich_data["matrix"]
    emp_matrix = matrix.get(str(empleado_id), {}) or matrix.get(empleado_id, {})
    
    # Extraer fechas (excluyendo 'info')
    for key, val in emp_matrix.items():
        if key != 'info':
            flat_data.append(val)
            
    # Ordenar por fecha
    flat_data.sort(key=lambda x: x.get('fecha', ''))
    
    return {
        "success": True,
        "data": flat_data,
        "feriados": rich_data.get("feriados", []),
        "periodo": rich_data.get("periodo"),
        "info": emp_matrix.get('info', {}),  # <-- CRÍTICO: Inyección de la Meta con descuentos legales
        "empleado_info": {
            "rut": emp.rut,
            "nombre": emp.nombre,
            "apellido_paterno": emp.apellido_paterno,
            "apellido_materno": emp.apellido_materno,
            "area": emp.area,
            "cargo": emp.cargo
        }
    }

@router.get("/filters-data/")
async def get_filters_data(
    area: Optional[str] = Query(None),
    turno_id: Optional[int] = Query(None),
    mes: Optional[int] = Query(None),
    anio: Optional[int] = Query(None),
    fecha_inicio: Optional[str] = Query(None),
    fecha_fin: Optional[str] = Query(None),
    emp_service: EmpleadoService = Depends(get_empleado_service),
    turno_service: TurnoService = Depends(get_turno_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Endpoint consolidado para obtener empleados, turnos y áreas filtradas para los filtros con RLS.
    Soporta cascada 4 niveles: Mes/Año → Área → Horario → Empleado.
    Optimiza la performance al reducir el número de peticiones.
    """
    # RLS: Si pide un área, verificarla. Si no pide, filtrar por sus permitidas.
    if area:
        current_user.verificar_acceso_area(area, "el área solicitada")
    areas_permitidas = current_user.get_areas_filter()
    
    # 0. Áreas con empleados que tienen horarios/turnos asignados
    f_desde = fecha_inicio
    f_hasta = fecha_fin
    if not f_desde and mes and anio:
        import calendar as _cal
        _, ult = _cal.monthrange(anio, mes)
        f_desde = f"{anio:04d}-{mes:02d}-01"
        f_hasta = f"{anio:04d}-{mes:02d}-{ult:02d}"

    areas_con_horario = await emp_service.get_areas_con_horario(
        areas_permitidas=areas_permitidas,
        fecha_desde=f_desde,
        fecha_hasta=f_hasta
    )

    # 1. Obtener turnos del área (sin detalles de días para velocidad)
    turnos = await turno_service.get_all_turnos(area=area, include_details=False, areas_permitidas=areas_permitidas)
    
    # 2. Obtener empleados — si turno_id está activo, filtrar solo los asignados a ese turno
    if turno_id:
        # Cascade: solo empleados con asignación activa a ese turno
        emp_rows = await emp_service.repository.get_activos_del_turno(turno_id, area, areas_permitidas)
        empleados = [dict(r) for r in emp_rows]
    else:
        empleados = await emp_service.get_lookup(area=area, activo=True, areas_permitidas=areas_permitidas)
    
    return {
        "areas": areas_con_horario,
        "empleados": empleados,
        "turnos": turnos
    }

@router.get("/empleados/sin-turno-activos/")
async def get_empleados_sin_turno_activos(
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene empleados activos sin turno asignado (Filtrado por RLS).
    Útil para mostrar alertas en UI.
    """
    areas_permitidas = current_user.get_areas_filter()
    empleados = await EmpleadoRepository(service.repository.db).get_activos_sin_turno(areas_permitidas)
    return empleados


@router.get("/diagnostic/no-shift/")
async def diagnostic_no_shift(
    area: str,
    mes: int,
    anio: int,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Diagnóstico: Cuenta cuántos empleados pertenecieron a un área en un mes 
    pero no tienen turno asignado en ese periodo.
    """
    # RLS
    current_user.verificar_acceso_area(area, "esta área")

    import calendar
    last_day = calendar.monthrange(anio, mes)[1]
    fecha_inicio = f"{anio}-{mes:02d}-01"
    fecha_fin = f"{anio}-{mes:02d}-{last_day}"

    res = await EmpleadoRepository(service.repository.db).contar_sin_turno_en_area(area, fecha_inicio, fecha_fin)
    return {"count": res["count"] if res else 0}

# ── Temas separados en su propio archivo (etapa 6 de la auditoría): mismas direcciones, bajo /api/asistencia ──
from backend.routers import asistencia_gps, asistencia_libreta, asistencia_compensaciones, asistencia_periodo, asistencia_jornada, asistencia_marcas, asistencia_reprocesos  # noqa: E402

router.include_router(asistencia_gps.router)
router.include_router(asistencia_libreta.router)
router.include_router(asistencia_compensaciones.router)
router.include_router(asistencia_periodo.router)
router.include_router(asistencia_jornada.router)
router.include_router(asistencia_marcas.router)
router.include_router(asistencia_reprocesos.router)
