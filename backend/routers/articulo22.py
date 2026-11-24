"""
Router Artículo 22 — Control de Presencia en Planta
Empleados excluidos de control de asistencia (Art. 22 Código del Trabajo Chile)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import asyncio
from loguru import logger

from backend.core.config import settings

def _now_chile():
    """Retorna datetime naive en hora de Chile (respeta DST automáticamente)"""
    tz = ZoneInfo(settings.TIMEZONE)  # "America/Santiago"
    return datetime.now(tz).replace(tzinfo=None)

from backend.core.database import get_db, Database
from backend.services.telegram_porteria import avisar_marca
from backend.core.security import SecurityContext, get_current_user, RequirePermission
from backend.services.deshacer_porteria import MARGEN_RED_SEGUNDOS, permiso_deshacer, segundos_para_deshacer
from backend.repositories.articulo22 import Articulo22Repository

router = APIRouter(
    prefix="/articulo22",
    tags=["Artículo 22"]
)


# ============================================
# AVISO DE TELEGRAM (vigilados)
# ============================================
_avisos_en_curso: set = set()  # referencia fuerte: asyncio solo guarda referencias débiles a las tareas y una sin dueño puede desaparecer


async def _avisar_tras_plazo(db, reg_id, emp, tipo, hora, registrador, espera):
    """Espera el plazo de Deshacer y no avisa una marca que se deshizo (sin plazo, avisa enseguida)."""
    if espera > 0 and reg_id:
        await asyncio.sleep(espera + MARGEN_RED_SEGUNDOS)
        try:
            if not await Articulo22Repository(db).existe_registro(reg_id):
                return
        except Exception as ex:
            logger.warning(f"[ART22] No se pudo revisar si la marca {reg_id} se deshizo: {ex}")
    await avisar_marca(emp, tipo, hora, registrador)


# ============================================
# INICIALIZACIÓN DE TABLA
# ============================================
async def _repo(db: Database) -> Articulo22Repository:
    """El repositorio de Artículo 22 con su tabla asegurada (las consultas viven en repositories/articulo22.py)."""
    repo = Articulo22Repository(db)
    await repo.init_tables()
    return repo


def _analizar_dia(marcas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analiza las marcas de un día (en orden de registro).

    - estadia: minutos en planta = suma de cada tramo ENTRADA→SALIDA.
    - fuera:   minutos fuera de planta entre una SALIDA y la ENTRADA siguiente del mismo día.
    - jornada: desde la primera ENTRADA hasta la última SALIDA (estadia + fuera). None si no hay salida.
    - incompleto: hay una entrada sin salida (o una salida sin entrada).
    Una hora menor que la anterior se interpreta como cruce de medianoche.
    """
    base = datetime(2000, 1, 1)
    dts: List[datetime] = []
    for m in marcas:
        t = datetime.strptime(m["hora"], "%H:%M:%S")
        dt = base.replace(hour=t.hour, minute=t.minute, second=t.second)
        while dts and dt < dts[-1]:
            dt += timedelta(days=1)
        dts.append(dt)

    estadia = fuera = 0.0
    primera_e = ultima_s = None
    i = 0
    n = len(marcas)
    cierre_previo: Optional[datetime] = None   # última salida de un tramo cerrado
    incompleto = False
    while i < n:
        if marcas[i]["tipo"] == "E" and i + 1 < n and marcas[i + 1]["tipo"] == "S":
            if primera_e is None:
                primera_e = dts[i]
            if cierre_previo is not None:
                fuera += (dts[i] - cierre_previo).total_seconds() / 60
            estadia += (dts[i + 1] - dts[i]).total_seconds() / 60
            cierre_previo = ultima_s = dts[i + 1]
            i += 2
        else:
            incompleto = True
            i += 1
    jornada = (ultima_s - primera_e).total_seconds() / 60 if primera_e and ultima_s else None
    return {"estadia": estadia, "fuera": fuera, "jornada": jornada, "incompleto": incompleto}


def _estadia_min(marcas: List[Dict[str, Any]]) -> float:
    """Minutos en planta de un día (suma de tramos ENTRADA→SALIDA)."""
    return _analizar_dia(marcas)["estadia"]


def _fmt_hm(minutos: float) -> str:
    m = int(round(minutos))
    return f"{m // 60}h {m % 60:02d}m"


# ============================================
# ENDPOINTS
# ============================================

@router.get("/empleados/")
async def get_empleados_art22(
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("porteria.art22"))
):
    """Lista empleados con excluido_asistencia=1 incluyendo datos de ficha."""
    rows = await Articulo22Repository(db).listar_empleados()
    return [dict(r) for r in rows]


@router.post("/marcar/")
async def marcar_presencia(
    data: Dict[str, Any],
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("porteria.art22"))
):
    """
    Registra una marca de presencia. Auto-detecta tipo E/S.
    Body: { "empleado_id": int, "observaciones": str (opcional) }
    """
    repo = await _repo(db)

    empleado_id = data.get("empleado_id")
    observaciones = data.get("observaciones", "")

    if not empleado_id:
        raise HTTPException(status_code=400, detail="empleado_id requerido")

    # Verificar que sea empleado Art. 22
    emp = await repo.get_empleado(empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    if not emp.get("excluido_asistencia"):
        raise HTTPException(status_code=400, detail="Este empleado no tiene Artículo 22")

    # Fecha y hora actual (Chile)
    now = _now_chile()
    fecha_hoy = now.strftime("%Y-%m-%d")
    hora_actual = now.strftime("%H:%M:%S")

    # Obtener última marca GLOBAL del empleado (sin filtro de fecha)
    # para detectar correctamente E/S en sesiones cross-midnight
    ultima = await repo.get_ultima_marca(empleado_id)

    # Protección contra doble click / debounce en el backend (ej. 5 segundos)
    if ultima:
        try:
            last_dt = datetime.strptime(f"{ultima['fecha']} {ultima['hora']}", "%Y-%m-%d %H:%M:%S")
            time_diff = (now - last_dt).total_seconds()
            if time_diff < 5:
                logger.warning(f"[ART22] Ignorando marca duplicada para empleado {empleado_id} (diferencia: {time_diff}s)")
                nombre_emp = f"{emp.get('apellido_paterno', '')} {emp.get('nombre', '')}"
                tipo_label = "ENTRADA" if ultima["tipo"] == "E" else "SALIDA"
                return {
                    "ok": True,
                    "tipo": ultima["tipo"],
                    "tipo_label": tipo_label,
                    "hora": ultima["hora"],
                    "empleado_id": empleado_id,
                    "nombre": nombre_emp
                }
        except Exception as ex:
            logger.error(f"[ART22] Error comparando tiempos de duplicación: {ex}")

    nuevo_tipo = "E" if (not ultima or ultima["tipo"] == "S") else "S"

    # Determinar fecha de registro:
    # Si es Salida y la Entrada fue de otro día → guardar con fecha de la Entrada
    # para mantener la sesión completa en el mismo día
    if nuevo_tipo == "S" and ultima and ultima["fecha"] != fecha_hoy:
        fecha_registro = ultima["fecha"]  # Cross-midnight: atribuir al día de entrada
        logger.info(f"[ART22] Cross-midnight detectado: Salida de hoy atribuida a {fecha_registro}")
    else:
        fecha_registro = fecha_hoy

    # Registrar
    registrador = f"{current_user.nombre_completo}" if hasattr(current_user, 'nombre_completo') else (current_user.username or "Sistema")

    reg_id = await repo.registrar_marca(
        (empleado_id, fecha_registro, hora_actual, nuevo_tipo,
         current_user.user_id if hasattr(current_user, 'user_id') else None,
         registrador, observaciones)
    )
    segundos = await segundos_para_deshacer(db)

    tarea = asyncio.create_task(_avisar_tras_plazo(db, reg_id, emp, nuevo_tipo, hora_actual, registrador, segundos))
    _avisos_en_curso.add(tarea)
    tarea.add_done_callback(_avisos_en_curso.discard)
    nombre_emp = f"{emp.get('apellido_paterno', '')} {emp.get('nombre', '')}"
    tipo_label = "ENTRADA" if nuevo_tipo == "E" else "SALIDA"
    logger.info(f"[ART22] {tipo_label}: {nombre_emp} (ID={empleado_id}) a las {hora_actual} - Reg: {registrador}")

    return {
        "ok": True,
        "tipo": nuevo_tipo,
        "tipo_label": tipo_label,
        "hora": hora_actual,
        "empleado_id": empleado_id,
        "nombre": nombre_emp,
        "deshacer": permiso_deshacer("art22", reg_id, segundos)
    }


@router.get("/estado-dia/")
async def get_estado_dia(
    fecha: Optional[str] = Query(None, description="Fecha YYYY-MM-DD, default hoy"),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("porteria.art22"))
):
    """
    Estado de presencia de todos los empleados Art. 22 para un día.
    Incluye marcas, estadía acumulada, y estado actual.
    """
    repo = await _repo(db)

    if not fecha:
        fecha = _now_chile().strftime("%Y-%m-%d")

    # Obtener empleados Art. 22
    empleados = await repo.listar_empleados()

    # Obtener todas las marcas del día
    marcas = await repo.get_marcas_del_dia(fecha)

    # Agrupar marcas por empleado
    marcas_por_emp = {}
    for m in marcas:
        eid = m["empleado_id"]
        if eid not in marcas_por_emp:
            marcas_por_emp[eid] = []
        marcas_por_emp[eid].append(dict(m))

    # Calcular estado por empleado
    resultado = []
    now = _now_chile()
    es_hoy = (fecha == now.strftime("%Y-%m-%d"))

    for emp in empleados:
        eid = emp["id"]
        emp_marcas = marcas_por_emp.get(eid, [])

        nombre_completo = f"{emp.get('apellido_paterno', '')} {emp.get('apellido_materno', '')}, {emp.get('nombre', '')}"

        if not emp_marcas:
            resultado.append({
                "empleado_id": eid,
                "nombre": nombre_completo.strip(", "),
                "cargo": emp.get("cargo", ""),
                "area": emp.get("area_nombre", ""),
                "marcas": [],
                "primera_entrada": None,
                "ultima_marca": None,
                "sesion_abierta": False,
                "estado": "sin_registro",
                "estadia_total_min": 0,
                "estadia_display": "—"
            })
            continue

        # Calcular estadía acumulada
        primera_entrada = None
        ultima_marca = emp_marcas[-1]
        sesion_abierta = (ultima_marca["tipo"] == "E")
        estadia_min = 0

        i = 0
        while i < len(emp_marcas):
            m = emp_marcas[i]
            if m["tipo"] == "E":
                if primera_entrada is None:
                    primera_entrada = m["hora"]
                # Buscar la salida correspondiente
                entrada_dt = datetime.strptime(f"{fecha} {m['hora']}", "%Y-%m-%d %H:%M:%S")
                if i + 1 < len(emp_marcas) and emp_marcas[i + 1]["tipo"] == "S":
                    salida_dt = datetime.strptime(f"{fecha} {emp_marcas[i + 1]['hora']}", "%Y-%m-%d %H:%M:%S")
                    if salida_dt < entrada_dt:
                        salida_dt += timedelta(days=1)  # Cross-midnight
                    estadia_min += (salida_dt - entrada_dt).total_seconds() / 60
                    i += 2
                    continue
                elif es_hoy and sesion_abierta and i == len(emp_marcas) - 1:
                    # Sesión abierta, calcular hasta ahora
                    estadia_min += (now - entrada_dt).total_seconds() / 60
            i += 1

        horas = int(estadia_min // 60)
        mins = int(estadia_min % 60)
        display = f"{horas}h {mins:02d}m"
        if sesion_abierta and es_hoy:
            display += " ⏳"

        estado = "sin_registro"
        if emp_marcas:
            estado = "en_planta" if sesion_abierta else "fuera"

        resultado.append({
            "empleado_id": eid,
            "nombre": nombre_completo.strip(", "),
            "cargo": emp.get("cargo", ""),
            "area": emp.get("area_nombre", ""),
            "marcas": emp_marcas,
            "primera_entrada": primera_entrada,
            "ultima_marca": ultima_marca["hora"] if ultima_marca else None,
            "ultima_marca_tipo": ultima_marca["tipo"] if ultima_marca else None,
            "sesion_abierta": sesion_abierta,
            "estado": estado,
            "estadia_total_min": round(estadia_min, 1),
            "estadia_display": display
        })

    # Stats
    total = len(resultado)
    con_registro = sum(1 for r in resultado if r["estado"] != "sin_registro")
    en_planta = sum(1 for r in resultado if r["estado"] == "en_planta")

    return {
        "fecha": fecha,
        "stats": {
            "total": total,
            "con_registro": con_registro,
            "en_planta": en_planta,
            "sin_registro": total - con_registro
        },
        "empleados": resultado
    }


@router.get("/historial/")
async def get_historial(
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    empleado_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("porteria.art22"))
):
    """Historial de registros Art. 22 con filtros y paginación."""
    repo = await _repo(db)

    if not hasta:
        hasta = _now_chile().strftime("%Y-%m-%d")
    if not desde:
        desde = (datetime.strptime(hasta, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")

    # Resumen por empleado/día (consulta agrupada por empleado+fecha)
    total_records = await repo.contar_historial(desde, hasta, area, empleado_id)

    offset = (page - 1) * limit
    rows = await repo.get_historial(desde, hasta, area, empleado_id, limit, offset)

    # Para cada fila, calcular estadía
    resultado = []
    for row in rows:
        r = dict(row)
        # Obtener marcas detalladas
        marcas = await repo.get_marcas_empleado_dia(r["empleado_id"], r["fecha"])
        an = _analizar_dia([dict(m) for m in marcas])
        estadia_min = an["estadia"]

        horas = int(estadia_min // 60)
        mins = int(estadia_min % 60)
        nombre = f"{r.get('apellido_paterno', '')} {r.get('apellido_materno', '')}, {r.get('emp_nombre', '')}"

        resultado.append({
            "fecha": r["fecha"],
            "empleado_id": r["empleado_id"],
            "nombre": nombre.strip(", "),
            "cargo": r.get("cargo", ""),
            "area": r.get("area_nombre", ""),
            "primera_entrada": r.get("primera_entrada"),
            "ultima_salida": r.get("ultima_salida"),
            "total_marcas": r.get("total_marcas", 0),
            "estadia_min": round(estadia_min, 1),
            "jornada_display": _fmt_hm(an["jornada"]) if an["jornada"] is not None else None,
            "fuera_display": _fmt_hm(an["fuera"]) if an["jornada"] is not None else None,
            "incompleto": an["incompleto"],
            "estadia_display": f"{horas}h {mins:02d}m"
        })

    # Resumen de TODO el rango para un solo empleado (no solo la página visible)
    resumen = None
    if empleado_id:
        todas = await repo.get_marcas_empleado_rango(empleado_id, desde, hasta)
        por_dia: Dict[str, List[Dict[str, Any]]] = {}
        for m in todas:
            por_dia.setdefault(m["fecha"], []).append(dict(m))
        analisis = [_analizar_dia(v) for v in por_dia.values()]
        total_min = sum(x["estadia"] for x in analisis)
        total_fuera = sum(x["fuera"] for x in analisis)
        total_jornada = sum(x["jornada"] for x in analisis if x["jornada"] is not None)
        dias_con = len(por_dia)
        dias_incompletos = sum(
            1 for v in por_dia.values()
            if sum(1 for x in v if x["tipo"] == "E") != sum(1 for x in v if x["tipo"] == "S")
        )
        resumen = {
            "dias": dias_con,
            "estadia_min": round(total_min, 1),
            "estadia_display": _fmt_hm(total_min),
            "fuera_display": _fmt_hm(total_fuera),
            "jornada_display": _fmt_hm(total_jornada),
            "horas_decimal": round(total_min / 60, 2),
            "promedio_dia_display": _fmt_hm(total_min / dias_con) if dias_con else "0h 00m",
            "primera_fecha": min(por_dia) if por_dia else None,
            "ultima_fecha": max(por_dia) if por_dia else None,
            "dias_incompletos": dias_incompletos,
        }

    return {
        "resumen": resumen,
        "desde": desde,
        "hasta": hasta,
        "total": total_records,
        "page": page,
        "limit": limit,
        "pages": (total_records + limit - 1) // limit,
        "registros": resultado
    }


@router.get("/exportar-excel/")
async def exportar_excel(
    desde: str = Query(...),
    hasta: str = Query(...),
    empleado_id: Optional[int] = Query(None),
    area: Optional[str] = Query(None),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("porteria.art22"))
):
    """Excel con las marcaciones Art. 22 del rango (todos o un empleado): resumen por día, marcas y total por empleado."""
    import io
    from fastapi.responses import StreamingResponse
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    repo = await _repo(db)
    try:
        d0 = datetime.strptime(desde, "%Y-%m-%d")
        d1 = datetime.strptime(hasta, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Fechas inválidas (use AAAA-MM-DD)")
    if d1 < d0:
        raise HTTPException(status_code=400, detail="La fecha final es anterior a la inicial")
    if (d1 - d0).days > 3660:
        raise HTTPException(status_code=400, detail="El rango máximo es de 10 años")

    rows = await repo.get_marcas_para_excel(desde, hasta, empleado_id, area)
    if not rows:
        raise HTTPException(status_code=404, detail="No hay marcaciones en el rango seleccionado")

    emps: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        r = dict(r)
        e = emps.setdefault(r["empleado_id"], {
            "rut": r["rut"],
            "nombre": f"{r['apellido_paterno'] or ''} {r['apellido_materno'] or ''}, {r['nombre'] or ''}".strip(" ,"),
            "cargo": r["cargo"] or "", "area": r["area_nombre"] or "", "dias": {}})
        e["dias"].setdefault(r["fecha"], []).append(r)

    wb = Workbook()
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="1E3A8A")

    def _encabezado(ws, cols, anchos):
        ws.append(cols)
        for c in ws[1]:
            c.font, c.fill, c.alignment = head_font, head_fill, Alignment(horizontal="center", vertical="center")
        for i, w in enumerate(anchos, 1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
        ws.freeze_panes = "A2"

    ws1 = wb.active
    ws1.title = "Resumen por día"
    _encabezado(ws1, ["Fecha", "RUT", "Empleado", "Cargo", "Área", "1ª entrada", "Últ. salida", "Marcas",
                      "Jornada total (1ª entrada→últ. salida)", "Tiempo fuera de planta", "Estadía en planta (h:mm)",
                      "Estadía (horas decimal)", "Observación"],
                [12, 13, 34, 30, 22, 11, 11, 8, 20, 16, 18, 16, 36])
    ws2 = wb.create_sheet("Marcaciones")
    _encabezado(ws2, ["Fecha", "RUT", "Empleado", "Hora", "Tipo", "Registrado por", "Observaciones"],
                [12, 13, 34, 10, 10, 28, 40])
    ws3 = wb.create_sheet("Total por empleado")
    _encabezado(ws3, ["RUT", "Empleado", "Cargo", "Área", "Primera fecha", "Última fecha", "Días con marcas",
                      "Jornada total", "Tiempo fuera de planta", "Estadía en planta (h:mm)", "Horas (decimal)",
                      "Promedio por día", "Días con marca sin par"],
                [13, 34, 30, 22, 13, 13, 15, 16, 18, 18, 15, 16, 20])

    gran_total = gran_fuera = gran_jornada = 0.0
    for e in emps.values():
        tot = tot_fuera = tot_jornada = 0.0
        incompletos = 0
        for fecha in sorted(e["dias"]):
            ms = [{"hora": m["hora"], "tipo": m["tipo"]} for m in e["dias"][fecha]]
            an = _analizar_dia(ms)
            mins = an["estadia"]
            tot += mins
            tot_fuera += an["fuera"]
            tot_jornada += an["jornada"] or 0.0
            ents = [m["hora"] for m in ms if m["tipo"] == "E"]
            sals = [m["hora"] for m in ms if m["tipo"] == "S"]
            aviso = ""
            if len(ents) != len(sals):
                incompletos += 1
                aviso = "Entrada o salida sin par: no suma horas"
            ws1.append([fecha, e["rut"], e["nombre"], e["cargo"], e["area"], ents[0][:5] if ents else "",
                        sals[-1][:5] if sals else "", len(ms),
                        _fmt_hm(an["jornada"]) if an["jornada"] is not None else "",
                        _fmt_hm(an["fuera"]) if an["jornada"] is not None else "",
                        _fmt_hm(mins), round(mins / 60, 2), aviso])
            for m in e["dias"][fecha]:
                ws2.append([fecha, e["rut"], e["nombre"], m["hora"], "Entrada" if m["tipo"] == "E" else "Salida",
                            m["registrado_por_nombre"] or "", m["observaciones"] or ""])
        gran_total += tot
        gran_fuera += tot_fuera
        gran_jornada += tot_jornada
        dias = len(e["dias"])
        ws3.append([e["rut"], e["nombre"], e["cargo"], e["area"], min(e["dias"]), max(e["dias"]), dias,
                    _fmt_hm(tot_jornada), _fmt_hm(tot_fuera), _fmt_hm(tot), round(tot / 60, 2),
                    _fmt_hm(tot / dias) if dias else "", incompletos])
    if len(emps) > 1:
        ws3.append([])
        ws3.append(["", "TOTAL", "", "", "", "", "", _fmt_hm(gran_jornada), _fmt_hm(gran_fuera),
                    _fmt_hm(gran_total), round(gran_total / 60, 2)])
        for c in ws3[ws3.max_row]:
            c.font = Font(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    sufijo = f"_emp{empleado_id}" if empleado_id else ""
    nombre = f"articulo22_{desde}_a_{hasta}{sufijo}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'}
    )
