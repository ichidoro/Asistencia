"""Bonos de evaluación semanal: Fill Rate de choferes y peonetas (pedido de la persona dueña, 23-11-2026).

Cómo funciona:
- Se evalúa por semana, de lunes a domingo. Cada semana se paga en el período donde cae su domingo (una semana partida
  entre dos períodos va completa al período donde termina).
- A quién se le paga, igual que en todos los bonos: las áreas («todas» o «solo estas»), los horarios («todos» o «solo
  estos», bonos.turnos_ids) y la regla que calza con su cargo y contrato, de donde sale el monto semanal (por ejemplo, chofer $40.000 y peoneta $30.000):
  nada escrito en el código.
- Cada día de turno de la semana parte en «cumple». Lo hace perder: un día marcado «no cumple» en la grilla
  (bono_dias_no_cumple), o un día con justificación o inasistencia cuyo efecto configurado en el bono sea «pierde». Un
  efecto «proporcional» (por ejemplo Descanso Operativo: la empresa decidió no enviarlo) descuenta ese día en proporción;
  «asistido» cuenta como cumplido. Si falta configurar un efecto, la semana no se paga y el motivo lo dice.
- Los días libres y feriados del horario no cuentan. Los días fuera de su turno (antes del inicio del turno o después de su
  baja) tampoco: la semana se paga en proporción a los días que sí le tocaban.
"""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set

ESTADOS_NO_LABORABLES = frozenset(["LIBRE", "FERIADO"])
INASISTENCIA = frozenset(["INASISTENCIA", "FALTA"])
EFECTOS = ("asistido", "proporcion", "pierde")


def semanas_del_periodo(fecha_inicio: str, fecha_fin: str) -> List[tuple]:
    """Las semanas (lunes, domingo) cuyo domingo cae dentro del período, en orden."""
    fi, ff = date.fromisoformat(fecha_inicio[:10]), date.fromisoformat(fecha_fin[:10])
    domingo = fi + timedelta(days=(6 - fi.weekday()))
    out = []
    while domingo <= ff:
        out.append((domingo - timedelta(days=6), domingo))
        domingo += timedelta(days=7)
    return out


def _dm(iso: str) -> str:
    return f"{iso[8:10]}-{iso[5:7]}"


def evaluar_persona(bono: Dict[str, Any], monto_semana: float, semanas: List[tuple], dias: Dict[str, Dict[str, Any]],
                    justif_por_dia: Dict[str, Dict[str, Any]], no_cumple: Dict[str, Optional[str]], feriados: Set[str],
                    turno_dias: Dict[Any, Any], es_bolsa: bool, desde: Optional[str], hasta: Optional[str],
                    hoy: str) -> Dict[str, Any]:
    """El resultado del bono semanal de una persona en sus semanas del período.

    dias: {fecha: fila de asistencia (estado, horas_teoricas)}; justif_por_dia: {fecha: justificación (tipo_id,
    tipo_nombre)}; no_cumple: {fecha: comentario} de los días marcados en la grilla; desde/hasta: su vigencia (inicio del
    turno y baja), o None."""
    efectos = bono.get("efectos") or {}
    efecto_inas = bono.get("efecto_inasistencia")
    out_semanas, perdidos, codigos = [], [], {}
    total = 0.0
    for lunes, domingo in semanas:
        fechas = [(lunes + timedelta(days=i)).isoformat() for i in range(7)]
        vigentes = [f for f in fechas if (not desde or f >= desde) and (not hasta or f <= hasta)]
        laborables, proporcion, pierde = 0, 0, []
        en_curso = False
        for f in fechas:
            if f not in vigentes:
                codigos[f] = "fuera"
                continue
            d = dias.get(f) or {}
            estado = str(d.get("estado") or "").upper()
            j = justif_por_dia.get(f)
            dia_sem = date.fromisoformat(f).weekday()
            cfg = turno_dias.get(dia_sem) or turno_dias.get(str(dia_sem)) or {}
            es_libre_turno = bool(cfg.get("es_libre", False))
            es_feriado = f in feriados
            if es_bolsa:
                # Bolsa Flexible no tiene horas de turno por día: cuenta todo día con estado que no sea libre ni feriado,
                # y un día sin estado que en su horario no sea libre ni feriado
                laborable = estado not in ESTADOS_NO_LABORABLES and (
                    bool(estado) or (not es_libre_turno and not es_feriado))
            else:
                laborable = estado not in ESTADOS_NO_LABORABLES and (
                    float(d.get("horas_teoricas") or 0) > 0 or (j is not None and not es_libre_turno and not es_feriado)
                    or (not estado and not es_libre_turno and not es_feriado))
            if not laborable:
                codigos[f] = "libre"
                continue
            laborables += 1
            if f > hoy or estado == "PENDIENTE":
                en_curso = True
                codigos[f] = "nc" if f in no_cumple else "pendiente"
                if f in no_cumple:
                    pierde.append({"fecha": f, "causa": "No cumple" + (f": {no_cumple[f]}" if no_cumple[f] else "")})
                continue
            if f in no_cumple:
                codigos[f] = "nc"
                pierde.append({"fecha": f, "causa": "No cumple" + (f": {no_cumple[f]}" if no_cumple[f] else "")})
                continue
            if j is not None:
                ef = efectos.get(j.get("tipo_id")) or efectos.get(str(j.get("tipo_id")))
                nombre = j.get("tipo_nombre") or "la justificación"
                if ef not in EFECTOS:
                    codigos[f] = "pierde"
                    pierde.append({"fecha": f, "causa": f"Falta configurar el efecto de «{nombre}» en este bono"})
                elif ef == "pierde":
                    codigos[f] = "pierde"
                    pierde.append({"fecha": f, "causa": nombre})
                elif ef == "proporcion":
                    codigos[f] = "proporcion"
                    proporcion += 1
                else:
                    codigos[f] = "justificado"   # cuenta como cumplido (por ejemplo Descanso Operativo)
                continue
            if estado in INASISTENCIA:
                if efecto_inas == "proporcion":
                    codigos[f] = "proporcion"
                    proporcion += 1
                elif efecto_inas == "pierde":
                    codigos[f] = "pierde"
                    pierde.append({"fecha": f, "causa": "Inasistencia sin justificar"})
                else:
                    codigos[f] = "pierde"
                    pierde.append({"fecha": f, "causa": "Falta configurar el efecto de la inasistencia sin justificar en este bono"})
                continue
            codigos[f] = "ok"
        factor_vig = len(vigentes) / 7
        if pierde:
            monto, estado_sem = 0.0, "pierde"
            perdidos += pierde
        elif laborables == 0:
            monto, estado_sem = 0.0, "sin_turno"
        else:
            monto = monto_semana * factor_vig * (laborables - proporcion) / laborables
            estado_sem = "en_curso" if en_curso else ("obtiene" if round(monto) == round(monto_semana) else "proporcional")
        posible = int(round(monto))
        # Una semana que no ha terminado parte en $0: recién al cerrar su domingo se sabe si se ganó (dueño, 23-11-2026)
        if estado_sem == "en_curso":
            monto = 0
        monto = int(round(monto))
        total += monto
        out_semanas.append({"desde": lunes.isoformat(), "hasta": domingo.isoformat(), "estado": estado_sem,
                            "monto": monto, "monto_posible": posible, "monto_completo": int(round(monto_semana)), "dias_turno": laborables,
                            "dias_proporcion": proporcion, "perdidos": pierde})
    completo = int(round(monto_semana)) * len(semanas)
    perdidas = [s for s in out_semanas if s["estado"] == "pierde"]
    en_curso = [s for s in out_semanas if s["estado"] == "en_curso"]
    en_parte = [s for s in out_semanas if s["estado"] == "proporcional"]
    if not semanas:
        motivo = "Sin semanas que terminen en este período"
    elif perdidas or en_parte:
        partes = []
        if perdidas:
            partes.append(f"pierde {len(perdidas)} de {len(semanas)} semanas")
        if en_parte:
            partes.append(f"{len(en_parte)} en proporción")
        motivo = "Semanal: " + ", ".join(partes)
    else:
        motivo = f"Semanal: {len(semanas)} semanas"
    if en_curso:
        motivo += f" ({len(en_curso)} en curso: se sabe al cerrar su domingo)"
    return {"aplica": True, "califica": total > 0, "monto": int(round(total)), "monto_completo": completo,
            "proporcional": bool(en_parte) or (0 < total < completo), "semanal": True, "semanas": out_semanas,
            "dias": codigos, "perdidos": perdidos, "motivo": motivo}


async def evaluar_bono_semanal(db, bono_service, bono: Dict[str, Any], empleados: List[Dict[str, Any]],
                               fecha_inicio: str, fecha_fin: str, hoy: str) -> Dict[int, Dict[str, Any]]:
    """El bono semanal para cada persona: {empleado_id: resultado}. A quien no tiene uno de los horarios del bono, o
    cuyo cargo o contrato no calza con ninguna regla, «no aplica»."""
    from backend.repositories.configuracion import ConfiguracionRepository
    semanas = semanas_del_periodo(fecha_inicio, fecha_fin)
    res: Dict[int, Dict[str, Any]] = {}
    candidatos = []
    for e in empleados:
        if e.get("excluido_asistencia"):
            res[e["id"]] = {"aplica": False, "califica": False, "monto": 0, "motivo": "Excluido de asistencia (Art 22)"}
            continue
        # ¿A quién se le paga? Áreas y horarios del bono (los mismos filtros de todos los bonos)
        fuera = bono_service.fuera_de_alcance(e, bono)
        if fuera:
            res[e["id"]] = {"aplica": False, "califica": False, "monto": 0, "motivo": fuera}
            continue
        calzan = bono_service.reglas_que_calzan(e, bono)
        if not calzan:
            res[e["id"]] = {"aplica": False, "califica": False, "monto": 0, "motivo": "No aplica por Cargo/Contrato"}
            continue
        candidatos.append((e, bono["reglas"][calzan[0]]))
    if not candidatos or not semanas:
        for e, _ in candidatos:
            res[e["id"]] = evaluar_persona(bono, 0, [], {}, {}, {}, set(), {}, False, None, None, hoy)
        for r in res.values():
            r["bono_id"] = bono["id"]
        return res
    desde, hasta = semanas[0][0].isoformat(), semanas[-1][1].isoformat()
    ids = [e["id"] for e, _ in candidatos]
    ph = ",".join("?" * len(ids))
    filas = await db.fetch_all(
        f"SELECT empleado_id, fecha, estado, horas_teoricas FROM asistencias WHERE empleado_id IN ({ph}) "
        "AND fecha BETWEEN ? AND ?", (*ids, desde, hasta))
    dias_emp: Dict[int, Dict[str, Dict]] = {}
    for r in filas:
        dias_emp.setdefault(int(r["empleado_id"]), {})[str(r["fecha"])[:10]] = dict(r)
    just = await db.fetch_all(
        f"SELECT j.empleado_id, j.fecha_inicio, j.fecha_fin, j.tipo_id, jt.nombre AS tipo_nombre FROM justificaciones j "
        f"JOIN justificacion_tipos jt ON jt.id = j.tipo_id WHERE j.empleado_id IN ({ph}) AND j.fecha_inicio <= ? "
        "AND j.fecha_fin >= ?", (*ids, hasta, desde))
    just_emp: Dict[int, Dict[str, Dict]] = {}
    for j in just:
        d0 = date.fromisoformat(str(j["fecha_inicio"])[:10])
        d1 = date.fromisoformat(str(j["fecha_fin"])[:10])
        d = max(d0, date.fromisoformat(desde))
        while d <= min(d1, date.fromisoformat(hasta)):
            just_emp.setdefault(int(j["empleado_id"]), {})[d.isoformat()] = dict(j)
            d += timedelta(days=1)
    feriados = {str(r["fecha"])[:10] for r in await db.fetch_all(
        "SELECT fecha FROM feriados WHERE fecha BETWEEN ? AND ?", (desde, hasta))}
    nc_emp: Dict[int, Dict[str, Optional[str]]] = {}
    cumple_emp: Dict[int, Set[str]] = {}
    marcas_emp: Dict[int, Dict[str, Dict[str, Any]]] = {}
    for m in await ConfiguracionRepository(db).get_dias_no_cumple([bono["id"]], desde, hasta):
        # Lo marcado de cada día, para que la ventana de la grilla lo muestre al abrirla
        marcas_emp.setdefault(int(m["empleado_id"]), {})[str(m["fecha"])[:10]] = {
            "marca": m.get("marca") or "no_cumple", "comentario": m.get("comentario"), "tiene_nc": bool(m.get("tiene_nc")),
            "razon_nc_id": m.get("razon_nc_id"), "razon_nc": m.get("razon_nc_nombre"), "usuario": m.get("usuario")}
        if (m.get("marca") or "no_cumple") == "cumple":
            cumple_emp.setdefault(int(m["empleado_id"]), set()).add(str(m["fecha"])[:10])
        else:
            # El detalle del «no cumple»: la nota de crédito y su razón, si la hubo, y el comentario
            detalle = "; ".join(x for x in ((f"nota de crédito por {m['razon_nc_nombre']}" if m.get("tiene_nc") and m.get("razon_nc_nombre") else None),
                                           m.get("comentario")) if x) or None
            nc_emp.setdefault(int(m["empleado_id"]), {})[str(m["fecha"])[:10]] = detalle
    from backend.services.bolsa_prorrateo import salida_decidida
    for e, regla in candidatos:
        salida = salida_decidida(e.get("fecha_salida"), e.get("activo"), e.get("decision_vencimiento"))
        res[e["id"]] = evaluar_persona(
            bono, float(regla.get("monto") or 0), semanas, dias_emp.get(e["id"], {}), just_emp.get(e["id"], {}),
            nc_emp.get(e["id"], {}), feriados, e.get("turno_dias") or {},
            e.get("tipo_programacion") in ("BOLSA_FLEXIBLE", "FLEXIBLE_BOLSA"),
            (e.get("inicio_turno") or None), (str(salida)[:10] if salida else None), hoy)
        # Días marcados «Cumple»: no cambian el cálculo (un día sin marca ya cumple), pero la celda lo muestra
        for f in cumple_emp.get(e["id"], ()):
            if res[e["id"]].get("dias", {}).get(f) in ("ok", "pendiente"):
                res[e["id"]]["dias"][f] = "cumple"
        res[e["id"]]["marcas"] = marcas_emp.get(e["id"], {})
    for r in res.values():
        r["bono_id"] = bono["id"]   # la grilla lo usa para marcar los días
    return res
