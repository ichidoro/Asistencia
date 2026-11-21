"""
Router - Asistencia: GPS y velocidades (camión del día de la libreta, recorrido, ruta y excesos de velocidad,
velocidades de los choferes en la grilla y entregas). Separado de routers/asistencia.py en la etapa 6 de la auditoría,
con el mismo código; las direcciones siguen bajo /api/asistencia (asistencia.py incluye este router).
"""
from typing import Any, Dict, List

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from backend.core.database import Database, get_db
from backend.core.security import RequirePermission, SecurityContext
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.configuracion import ConfiguracionRepository
from backend.repositories.empleado import EmpleadoRepository
from backend.routers.asistencia_comun import get_asistencia_service
from backend.services import gps_nexacol
from backend.services.asistencia_service import AsistenciaService

router = APIRouter()


_PLAN_DIA: Dict[str, Any] = {}     # fecha -> (momento, filas de Despacho Diario de Nexacol)
_VEHICULOS_GPS: Dict[str, Any] = {}  # 'v' -> (momento, vehículos de la plataforma de GPS)


@router.get("/libreta-180h/gps/patente-propuesta/")
async def patente_propuesta_libreta(
    empleado_id: int = Query(...),
    fecha: str = Query(...),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """Camión del día para la libreta: el guardado con el día; si no hay, el del chofer (acompañante enlazado) o el que planificó Despacho
    Diario en Nexacol para esta persona (mismo calce de nombres que el reporte de velocidades). Si Nexacol no responde, la lista viene vacía
    con el motivo y se elige a mano."""
    import re
    import time
    from backend.services.velocidades_choferes import patentes_planificadas
    repo = service.repository
    propia = await repo.get_libreta_180h(empleado_id, fecha)
    if propia and (propia.get('patente') or propia.get('patente_origen') == 'SIN_CAMION'):
        props = [{"vehiculo_id": propia.get('vehiculo_id'), "patente": propia.get('patente')}] if propia.get('patente') else []
        return {"success": True, "origen": propia.get('patente_origen') or 'MANUAL', "propuestas": props, "mensaje": ""}
    chofer_id = await repo.get_chofer_de_acompanante_180h(empleado_id, fecha)
    if chofer_id is not None:
        lib = await repo.get_libreta_180h(chofer_id, fecha)
        if lib and lib.get('patente'):
            return {"success": True, "origen": "CHOFER", "propuestas": [{"vehiculo_id": lib.get('vehiculo_id'), "patente": lib.get('patente')}], "mensaje": ""}
    ahora = time.time()
    try:
        previo = _PLAN_DIA.get(fecha)
        if previo and ahora - previo[0] < 300:
            dias = previo[1]
        else:
            dias = await gps_nexacol.velocidades(fecha, fecha)
            _PLAN_DIA[fecha] = (ahora, dias)
            if len(_PLAN_DIA) > 40:
                _PLAN_DIA.pop(next(iter(_PLAN_DIA)))
        previo_v = _VEHICULOS_GPS.get('v')
        if previo_v and ahora - previo_v[0] < 600:
            vehiculos = previo_v[1]
        else:
            vehiculos = await gps_nexacol.vehiculos()
            _VEHICULOS_GPS['v'] = (ahora, vehiculos)
    except gps_nexacol.GpsNexacolError as e:
        return {"success": True, "origen": "PLAN", "propuestas": [], "mensaje": f"No se pudo leer la planificación de Nexacol: {e.mensaje}"}
    personas = [dict(r) for r in await EmpleadoRepository(repo.db).get_personas_de_su_area(empleado_id)]
    norm = lambda p: re.sub(r"[^A-Z0-9]", "", str(p).upper())
    por_patente = {norm(v["patente"]): v for v in vehiculos}
    props = [{"vehiculo_id": (por_patente.get(norm(p)) or {}).get("id"), "patente": p}
             for p in patentes_planificadas(dias, personas, empleado_id, fecha)]
    return {"success": True, "origen": "PLAN", "propuestas": props,
            "mensaje": "" if props else "La planificación de Despacho Diario no trae camión para esta persona ese día: elígelo a mano."}


@router.get("/libreta-180h/gps/vehiculos/")
async def gps_vehiculos_libreta(current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))):
    """Camiones (patentes) de la plataforma de GPS, vía Nexacol, para el selector de la libreta 180h."""
    try:
        return {"success": True, "vehiculos": await gps_nexacol.vehiculos()}
    except gps_nexacol.GpsNexacolError as e:
        raise HTTPException(status_code=e.status, detail=e.mensaje)


@router.get("/libreta-180h/gps/dia/")
async def gps_dia_libreta(
    vehiculo_id: str = Query(..., pattern=r"^\d{1,6}$"),
    fecha: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """Recorrido de un camión en un día (paradas y 96 tramos de 15 min en movimiento/detenido) para compararlo con la libreta 180h."""
    try:
        return await gps_nexacol.recorrido_dia(vehiculo_id, fecha)
    except gps_nexacol.GpsNexacolError as e:
        raise HTTPException(status_code=e.status, detail=e.mensaje)


@router.get("/gps/ruta-velocidad/")
async def ruta_velocidad(
    patente: str = Query(..., pattern=r"^[A-Za-z0-9 \-]{4,10}$"),
    fecha: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver")),
):
    """Ruta del camión en un día (puntos reducidos con su velocidad), para dibujarla en el reporte semanal de velocidades que firma el chofer."""
    try:
        return await gps_nexacol.ruta_velocidad(patente, fecha)
    except gps_nexacol.GpsNexacolError as e:
        raise HTTPException(status_code=e.status, detail=e.mensaje)


@router.get("/gps/exceso-velocidad/")
async def exceso_velocidad(
    items: str = Query(..., pattern=r"^[A-Za-z0-9 \-]{4,10}:\d{4}-\d{2}-\d{2}(,[A-Za-z0-9 \-]{4,10}:\d{4}-\d{2}-\d{2}){0,39}$"),
    limite: int = Query(90, ge=30, le=200),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver")),
):
    """Segundos de cada día (patente:fecha, separados por coma) que el camión anduvo sobre el límite de velocidad, para el reporte semanal que firma el chofer."""
    import asyncio
    sem = asyncio.Semaphore(4)

    async def uno(par: str):
        pat, fecha = par.split(":", 1)
        async with sem:
            try:
                return f"{pat.strip().upper()}|{fecha}", await gps_nexacol.exceso_dia(pat, fecha, limite)
            except gps_nexacol.GpsNexacolError:
                return f"{pat.strip().upper()}|{fecha}", None
    pares = list(dict.fromkeys(items.split(",")))
    return {"success": True, "limite": limite, "segundos": dict(await asyncio.gather(*(uno(p) for p in pares)))}


async def _velocidad_de_libreta(db: Database, choferes: List[Dict[str, Any]], por_emp: Dict[str, Dict[str, Dict[str, Any]]], desde: str, hasta: str) -> None:
    """Agrega a `por_emp` la velocidad del camión de la libreta para los días con camión y sin velocidad. Solo patentes con GPS; si Nexacol falla en un día, ese día queda sin dato."""
    import asyncio
    ids = [int(c["id"]) for c in choferes]
    if not ids:
        return
    filas = await AsistenciaRepository(db).get_patentes_de_libreta(ids, desde, hasta)
    faltan = [(str(f["empleado_id"]), str(f["fecha"])[:10], str(f["patente"])) for f in filas
              if str(f["fecha"])[:10] not in por_emp.get(str(f["empleado_id"]), {})]
    if not faltan:
        return
    hoy = datetime.now().date().isoformat()
    sem = asyncio.Semaphore(4)

    async def uno(pat: str, fecha: str):
        async with sem:
            try:
                return await gps_nexacol.vel_camion_dia(pat, fecha, fecha < hoy)
            except gps_nexacol.GpsNexacolError:
                return None
    pares = list(dict.fromkeys((p, f) for _, f, p in faltan))[:60]   # tope por consulta: un mes normal trae unos pocos
    res = dict(zip(pares, await asyncio.gather(*(uno(p, f) for p, f in pares))))
    for emp, fecha, pat in faltan:
        r = res.get((pat, fecha))
        if r:
            por_emp.setdefault(emp, {})[fecha] = {"vel": r["vel"], "hora": r["hora"], "patente": pat, "comparte": False}


_VEL_CHOFERES: Dict[Any, Any] = {}  # (desde, hasta) -> (momento, filas de Nexacol): la grilla pide el mismo mes varias veces seguidas


@router.get("/gps/velocidades-choferes/")
async def velocidades_choferes(
    desde: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    hasta: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver")),
    db: Database = Depends(get_db),
):
    """Velocidad máxima del GPS de cada chofer por día, según el chofer que Despacho Diario planificó en cada camión (Nexacol). Para la grilla de Marcaciones.
    Solo los choferes de Bolsa (pedido del dueño, 30-10-2026), con la misma regla de la grilla (calcularStatsEmpleado): horario de tipo Bolsa Flexible
    o cuyo nombre contiene TRANSPORTE, vigente en el rango. Con solo el tipo quedaban fuera los de TRANSPORTE, que la grilla sí muestra en Bolsa.
    Y solo del área LOGÍSTICA TRADICIONAL (pedido del dueño, 30-10-2026: por ahora se trabaja solo con ella)."""
    import time
    from backend.core.rut import rut_visible
    from backend.services.velocidades_choferes import calzar_choferes
    ahora = time.time()
    previo = _VEL_CHOFERES.get((desde, hasta))
    try:
        if previo and ahora - previo[0] < 300:
            dias = previo[1]
        else:
            dias = await gps_nexacol.velocidades(desde, hasta)
            _VEL_CHOFERES[(desde, hasta)] = (ahora, dias)
            if len(_VEL_CHOFERES) > 24:
                _VEL_CHOFERES.pop(next(iter(_VEL_CHOFERES)))
    except gps_nexacol.GpsNexacolError as e:
        raise HTTPException(status_code=e.status, detail=e.mensaje)
    filas = await EmpleadoRepository(db).get_choferes_logistica_tradicional()
    choferes = [dict(r) for r in filas]
    por_emp, sin_calzar = calzar_choferes(dias, choferes)
    # Respaldo (20-11-2026): un día con camión en la libreta pero sin velocidad del plan (Despacho Diario no trae al chofer ese día) se completa con el GPS del camión de la libreta.
    await _velocidad_de_libreta(db, choferes, por_emp, desde, hasta)
    # Nombre y RUT de quienes tienen velocidades: el reporte semanal los imprime junto a la firma del chofer.
    personas = {
        str(c["id"]): {"nombre": " ".join(str(c.get(k) or "").strip() for k in ("nombre", "apellido_paterno", "apellido_materno") if str(c.get(k) or "").strip()), "rut": rut_visible(c.get("rut"))}
        for c in choferes if str(c["id"]) in por_emp
    }
    # Cuántos días entregó Nexacol y cuántos llegan hasta una persona: la pantalla lo muestra cuando no hay velocidades, para ver dónde se corta
    diagnostico = {"dias_plan": len(dias), "dias_con_gps": sum(1 for d in dias if d.get("velMax") is not None), "choferes": len(choferes), "con_velocidad": len(por_emp)}
    # Límite de velocidad de Configuración › Sistema (05-11-2026); sin ajuste válido va None y la pantalla no evalúa el límite
    from backend.services.libreta_revision import limites_desde_ajustes
    lim = limites_desde_ajustes([dict(f) for f in await ConfiguracionRepository(db).get_ajustes_clave_valor("gps_velocidad_limite_kmh")])
    return {"success": True, "desde": desde, "hasta": hasta, "velocidades": por_emp, "personas": personas, "sin_calzar": sin_calzar,
            "diagnostico": diagnostico, "limite_kmh": int(lim["velocidad_kmh"]) if lim["velocidad_kmh"] else None}


_APRENDIDO_EN: Dict[str, float] = {}


async def _aprender_historial(vehiculo_id: str, repo: Any) -> None:
    """Aprende en segundo plano de los últimos 21 días del camión (una vez cada 6 h): dónde paró para cada cliente, para que la próxima consulta ya tenga su ubicación."""
    import asyncio
    import time
    if time.time() - _APRENDIDO_EN.get(vehiculo_id, 0) < 6 * 3600:
        return
    _APRENDIDO_EN[vehiculo_id] = time.time()
    hoy = datetime.now().date()
    for k in range(1, 22):
        try:
            r = await gps_nexacol.entregas_dia(vehiculo_id, (hoy - timedelta(days=k)).isoformat(), aprendidas_fn=None, con_pasos=False)
            await repo.guardar(r.get("observaciones") or [])
        except Exception:
            continue
        await asyncio.sleep(0.3)


@router.get("/libreta-180h/gps/entregas/")
async def gps_entregas_libreta(
    vehiculo_id: str = Query(..., pattern=r"^\d{1,6}$"),
    fecha: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver")),
    db: Database = Depends(get_db),
):
    """Las facturas que llevaba el camión (calzadas por su patente en Nexacol) contra las paradas del GPS: cuáles calzan, cuáles quedan muy cerca y cuáles lejos."""
    try:
        from backend.repositories.entrega_ubicaciones import EntregaUbicacionesRepository
        import asyncio
        repo = EntregaUbicacionesRepository(db)
        res = await gps_nexacol.entregas_dia(vehiculo_id, fecha, aprendidas_fn=repo.aprendidas)
        try:
            await repo.guardar(res.pop("observaciones", []))
            asyncio.create_task(_aprender_historial(vehiculo_id, repo))
        except Exception as ex:   # aprender es un extra: si falla, la pantalla sigue igual
            logger.warning(f"No se pudieron guardar las ubicaciones aprendidas: {ex}")
        return res
    except gps_nexacol.GpsNexacolError as e:
        raise HTTPException(status_code=e.status, detail=e.mensaje)
