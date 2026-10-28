"""Dashboard, pestaña «Indicadores»: el detalle de cada tacómetro («Ver detalle»).

Muestra los registros que forman el número, por persona: quién, qué día, cuántas horas, quién ingresó la
marca. Usa las mismas definiciones que el cálculo del indicador (dashboard_indicadores), así el detalle suma
lo mismo que el tacómetro. Solo lee. Ver REGLAS_ASISTENCIA.md §8.
"""
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.core.config import settings
from backend.core.database import db as _db
from backend.services.dashboard_indicadores import INDICADORES
from backend.services.dashboard_pendientes import _JUSTIFICADO, _LIBRETA, _area_de, _num, visible

_PERSONA = "e.apellido_paterno || ' ' || COALESCE(NULLIF(e.apellido_materno, ''), '') || ', ' || e.nombre"
_DIAS_SEMANA = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]

_SQL_DIAS = f"""
    SELECT a.empleado_id, {_PERSONA} AS persona, {_area_de('a.empleado_id', 'a.fecha')} AS area, a.fecha, a.estado,
           a.hora_entrada_teorica, a.hora_entrada_real, t.nombre AS turno,
           COALESCE(a.minutos_atraso, 0) AS minutos_atraso, COALESCE(a.minutos_deuda, 0) AS minutos_deuda,
           COALESCE(a.horas_teoricas, 0) AS horas_teoricas,
           CASE WHEN a.hora_entrada_real IS NOT NULL AND a.hora_entrada_real <> '' THEN 1 ELSE 0 END AS entrada,
           {_LIBRETA} AS libreta, {_JUSTIFICADO} AS justificado
      FROM asistencias a
      JOIN empleados e ON e.id = a.empleado_id
      LEFT JOIN turnos t ON t.id = a.turno_asignado_id
     WHERE a.fecha BETWEEN ? AND ?
"""
_SQL_HE = f"""
    SELECT he.empleado_id, {_PERSONA} AS persona, {_area_de('he.empleado_id', 'he.fecha')} AS area, he.fecha,
           COALESCE(he.minutos_autorizados, 0) AS minutos, he.origen
      FROM horas_extras he JOIN empleados e ON e.id = he.empleado_id
     WHERE he.fecha BETWEEN ? AND ? AND he.estado = 'APROBADO'
"""
_SQL_JE = f"""
    SELECT je.empleado_id, {_PERSONA} AS persona, {_area_de('je.empleado_id', 'je.fecha')} AS area, je.fecha,
           je.hora_entrada, je.hora_salida, COALESCE(je.minutos_trabajados, 0) AS minutos, je.estado, je.origen
      FROM jornadas_especiales je JOIN empleados e ON e.id = je.empleado_id
     WHERE je.fecha BETWEEN ? AND ?
"""
# Si el día de la marca es jornada especial, libre o feriado (no cuenta como corrección).
_ESPECIAL_L = "CASE WHEN EXISTS (SELECT 1 FROM jornadas_especiales je WHERE je.empleado_id = l.empleado_id AND je.fecha = LEFT(CAST(l.fecha_hora AS TEXT), 10)) OR EXISTS (SELECT 1 FROM asistencias a2 WHERE a2.empleado_id = l.empleado_id AND a2.fecha = LEFT(CAST(l.fecha_hora AS TEXT), 10) AND a2.estado IN ('EXTRA', 'JORNADA_ESPECIAL', 'LIBRE', 'FERIADO')) THEN 1 ELSE 0 END"
_SQL_MARCAS = f"""
    SELECT l.empleado_id, {_PERSONA} AS persona, {_area_de('l.empleado_id', 'LEFT(CAST(l.fecha_hora AS TEXT), 10)')} AS area,
           LEFT(CAST(l.fecha_hora AS TEXT), 10) AS fecha, SUBSTR(CAST(l.fecha_hora AS TEXT), 12, 5) AS hora, l.tipo,
           COALESCE(u.username, '') AS usuario, COALESCE(l.observaciones, '') AS observacion
           , {_ESPECIAL_L} AS especial,
           CASE WHEN EXISTS (SELECT 1 FROM logs_raw r WHERE r.empleado_id = l.empleado_id AND COALESCE(r.manual, 0) = 0
                              AND LEFT(CAST(r.fecha_hora AS TEXT), 10) = LEFT(CAST(l.fecha_hora AS TEXT), 10)) THEN 1 ELSE 0 END AS con_reloj
      FROM logs_raw l JOIN empleados e ON e.id = l.empleado_id LEFT JOIN usuarios u ON u.id = l.usuario_id
     WHERE COALESCE(l.manual, 0) = 1 AND LEFT(CAST(l.fecha_hora AS TEXT), 10) BETWEEN ? AND ?
"""
_SQL_MOVIMIENTOS = f"""
    SELECT e.id AS empleado_id, {_PERSONA} AS persona, e.cargo, e.tipo_contrato,
           CASE WHEN e.activo = 0 AND e.fecha_salida BETWEEN ? AND ? THEN 'Baja' ELSE 'Ingreso' END AS movimiento,
           CASE WHEN e.activo = 0 AND e.fecha_salida BETWEEN ? AND ? THEN e.fecha_salida ELSE e.fecha_ingreso END AS fecha,
           CASE WHEN e.activo = 0 AND e.fecha_salida BETWEEN ? AND ? THEN {_area_de('e.id', 'e.fecha_salida')}
                ELSE {_area_de('e.id', 'e.fecha_ingreso')} END AS area
      FROM empleados e
     WHERE (e.activo = 0 AND e.fecha_salida BETWEEN ? AND ?) OR e.fecha_ingreso BETWEEN ? AND ?
"""


def _h(minutos: float) -> float:
    return round(_num(minutos) / 60.0, 1)


def _causa(estado: str) -> str:
    """Nombre legible de por qué no trabajó un día programado."""
    e = (estado or "").strip()
    if e == "INASISTENCIA":
        return "Falta sin aviso"
    if e in ("PENDIENTE", "ANOMALIA", "EN_CURSO"):
        return "Sin marca de entrada"
    return e.replace("_", " ").capitalize() if e else "Sin dato"


def _prog(r: Dict[str, Any]) -> bool:
    return (r["libreta"] == 0 and r["justificado"] == 0 and _num(r["horas_teoricas"]) > 0
            and r["estado"] not in ("LIBRE", "FERIADO", "NO_ACTIVO"))


def agrupar(filas: List[Dict[str, Any]], valores, registro, orden: str, descendente: bool = True) -> List[Dict[str, Any]]:
    """Agrupa filas por persona: `valores(filas)` da las columnas de la persona y `registro(fila)` cada registro."""
    por: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for f in filas:
        por[f["empleado_id"]].append(f)
    out = []
    for fs in por.values():
        fs.sort(key=lambda f: (str(f.get("fecha") or ""), str(f.get("hora") or "")))
        out.append({"persona": fs[0]["persona"], "area": fs[0]["area"], "valores": valores(fs),
                    "registros": [registro(f) for f in fs]})
    out.sort(key=lambda p: (-(p["valores"].get(orden) or 0) if descendente else (p["valores"].get(orden) or 0), p["persona"]))
    return out


class DashboardDetalle:
    def __init__(self, db=None):
        self.db = db or _db

    async def _tramo(self, tramo_id: Optional[int]) -> Optional[Dict[str, Any]]:
        hoy = datetime.now(ZoneInfo(settings.TIMEZONE)).strftime("%Y-%m-%d")
        tramos = [dict(r) for r in await self.db.fetch_all(
            "SELECT id, mes_cierre, fecha_inicio, fecha_fin FROM periodos_rrhh ORDER BY fecha_inicio")]
        elegido = next((t for t in tramos if t["id"] == tramo_id), None)
        if not elegido:
            pasados = [t for t in tramos if str(t["fecha_fin"]) < hoy]
            elegido = pasados[-1] if pasados else (tramos[-1] if tramos else None)
        if elegido:
            elegido = {**elegido, "fecha_inicio": str(elegido["fecha_inicio"]), "fecha_fin": str(elegido["fecha_fin"]),
                       "hasta": min(hoy, str(elegido["fecha_fin"]))}
        return elegido

    async def _filas(self, sql: str, params, filtro, permitidas) -> List[Dict[str, Any]]:
        return [dict(r) for r in await self.db.fetch_all(sql, params) if visible(r["area"], filtro, permitidas)]

    async def detalle(self, indicador: str, tramo_id: Optional[int] = None, area: Optional[str] = None,
                      areas_permitidas: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        ind = next((i for i in INDICADORES if i["id"] == indicador), None)
        t = await self._tramo(tramo_id)
        if not ind or not t:
            return None
        filtro = area if area and area != "Todas" else None
        fi, ff = t["fecha_inicio"], t["hasta"]
        out: Dict[str, Any] = {"indicador": {k: ind[k] for k in ("id", "nombre", "definicion", "unidad", "accion")},
                               "tramo": {"id": t["id"], "mes": t["mes_cierre"], "fecha_inicio": fi, "fecha_fin": t["fecha_fin"]},
                               "resumen": [], "columnas": [], "columnas_registro": [], "personas": []}
        k = indicador

        if k in ("puntualidad", "minutos_atraso", "ausentismo", "faltas", "deuda", "sobretiempo"):
            dias = await self._filas(_SQL_DIAS, (fi, ff), filtro, areas_permitidas)

        if k in ("puntualidad", "minutos_atraso"):
            trab = [r for r in dias if _prog(r) and r["entrada"] == 1]
            atr = [r for r in trab if _num(r["minutos_atraso"]) > 0]
            min_tot = sum(_num(r["minutos_atraso"]) for r in atr)
            out["resumen"] = [{"etiqueta": "Días trabajados", "valor": len(trab)},
                              {"etiqueta": "Días con atraso", "valor": len(atr)},
                              {"etiqueta": "Minutos de atraso", "valor": round(min_tot)}]
            atr_por = defaultdict(list)
            for r in atr:
                atr_por[r["empleado_id"]].append(r)

            def val(fs):
                a = atr_por.get(fs[0]["empleado_id"], [])
                m = sum(_num(x["minutos_atraso"]) for x in a)
                return {"trabajados": len(fs), "con_atraso": len(a),
                        "puntualidad": round(100.0 * (1 - len(a) / len(fs)), 1) if fs else None,
                        "minutos": round(m), "promedio": round(m / len(a), 1) if a else 0.0}
            personas = agrupar(trab, val, lambda r: r, "con_atraso" if k == "puntualidad" else "promedio")
            for p in personas:
                p["registros"] = [{"fecha": r["fecha"], "horario": (r["hora_entrada_teorica"] or "")[:5],
                                   "entrada": (r["hora_entrada_real"] or "")[:5], "minutos": round(_num(r["minutos_atraso"]))}
                                  for r in p["registros"] if _num(r["minutos_atraso"]) > 0]
            out["personas"] = [p for p in personas if p["registros"]]
            out["columnas"] = ([{"id": "trabajados", "titulo": "Días trabajados"}, {"id": "con_atraso", "titulo": "Con atraso"},
                                {"id": "puntualidad", "titulo": "Puntualidad %"}, {"id": "minutos", "titulo": "Minutos"}]
                               if k == "puntualidad" else
                               [{"id": "con_atraso", "titulo": "Atrasos"}, {"id": "minutos", "titulo": "Minutos"},
                                {"id": "promedio", "titulo": "Minutos por atraso"}])
            out["columnas_registro"] = [{"id": "fecha", "titulo": "Fecha"}, {"id": "horario", "titulo": "Entrada del horario"},
                                        {"id": "entrada", "titulo": "Entrada real"}, {"id": "minutos", "titulo": "Minutos"}]

        elif k == "faltas":
            f = [r for r in dias if r["libreta"] == 0 and r["estado"] == "INASISTENCIA"]
            out["resumen"] = [{"etiqueta": "Faltas sin aviso", "valor": len(f)},
                              {"etiqueta": "Personas", "valor": len({r["empleado_id"] for r in f})}]
            out["personas"] = agrupar(f, lambda fs: {"faltas": len(fs)},
                                      lambda r: {"fecha": r["fecha"], "turno": r["turno"] or "",
                                                 "horario": (r["hora_entrada_teorica"] or "")[:5]}, "faltas")
            out["columnas"] = [{"id": "faltas", "titulo": "Faltas"}]
            out["columnas_registro"] = [{"id": "fecha", "titulo": "Fecha"}, {"id": "turno", "titulo": "Horario"},
                                        {"id": "horario", "titulo": "Entrada del horario"}]

        elif k == "ausentismo":
            sin = [{**r, "causa": _causa(r["estado"])} for r in dias if _prog(r) and r["entrada"] == 0]
            jus = [{**r, "causa": _causa(r["estado"])} for r in dias if _num(r["horas_teoricas"]) > 0 and r["justificado"] == 1]
            todos = sin + jus
            causas = defaultdict(int)
            for r in todos:
                causas[r["causa"]] += 1
            out["resumen"] = [{"etiqueta": c, "valor": n} for c, n in sorted(causas.items(), key=lambda x: -x[1])]
            out["personas"] = agrupar(todos, lambda fs: {"dias": len(fs)},
                                      lambda r: {"fecha": r["fecha"], "causa": r["causa"]}, "dias")
            out["columnas"] = [{"id": "dias", "titulo": "Días sin trabajar"}]
            out["columnas_registro"] = [{"id": "fecha", "titulo": "Fecha"}, {"id": "causa", "titulo": "Causa"}]

        elif k == "deuda":
            d = [r for r in dias if r["libreta"] == 0 and _num(r["minutos_deuda"]) > 0]
            out["resumen"] = [{"etiqueta": "Horas de deuda", "valor": _h(sum(_num(r["minutos_deuda"]) for r in d))},
                              {"etiqueta": "Días con deuda", "valor": len(d)}]
            out["personas"] = agrupar(d, lambda fs: {"horas": _h(sum(_num(x["minutos_deuda"]) for x in fs)), "dias": len(fs)},
                                      lambda r: {"fecha": r["fecha"], "estado": _causa(r["estado"]),
                                                 "minutos": round(_num(r["minutos_deuda"]))}, "horas")
            out["columnas"] = [{"id": "horas", "titulo": "Horas de deuda"}, {"id": "dias", "titulo": "Días"}]
            out["columnas_registro"] = [{"id": "fecha", "titulo": "Fecha"}, {"id": "estado", "titulo": "Estado del día"},
                                        {"id": "minutos", "titulo": "Minutos"}]

        elif k in ("horas_extra", "sobretiempo"):
            he = await self._filas(_SQL_HE, (fi, ff), filtro, areas_permitidas)
            prog_h = defaultdict(float)
            if k == "sobretiempo":
                for r in dias:
                    if _prog(r):
                        prog_h[r["empleado_id"]] += _num(r["horas_teoricas"])
            out["resumen"] = [{"etiqueta": "Horas extra aprobadas", "valor": _h(sum(_num(r["minutos"]) for r in he))},
                              {"etiqueta": "Personas", "valor": len({r["empleado_id"] for r in he})}]

            def val(fs):
                h = _h(sum(_num(x["minutos"]) for x in fs))
                v = {"horas": h, "dias": len(fs)}
                if k == "sobretiempo":
                    p = prog_h.get(fs[0]["empleado_id"], 0.0)
                    v.update({"programadas": round(p, 1), "sobretiempo": round(100.0 * h / p, 1) if p else None})
                return v
            out["personas"] = agrupar(he, val, lambda r: {"fecha": r["fecha"], "horas": _h(r["minutos"]),
                                                          "origen": (r["origen"] or "").replace("_", " ").capitalize()},
                                      "sobretiempo" if k == "sobretiempo" else "horas")
            out["columnas"] = ([{"id": "horas", "titulo": "Horas extra"}, {"id": "programadas", "titulo": "Horas programadas"},
                                {"id": "sobretiempo", "titulo": "Sobretiempo %"}] if k == "sobretiempo"
                               else [{"id": "horas", "titulo": "Horas extra"}, {"id": "dias", "titulo": "Días"}])
            out["columnas_registro"] = [{"id": "fecha", "titulo": "Fecha"}, {"id": "horas", "titulo": "Horas"},
                                        {"id": "origen", "titulo": "Origen"}]

        elif k == "jornadas_especiales":
            je = await self._filas(_SQL_JE, (fi, ff), filtro, areas_permitidas)
            out["resumen"] = [{"etiqueta": "Jornadas", "valor": len(je)},
                              {"etiqueta": "Horas trabajadas", "valor": _h(sum(_num(r["minutos"]) for r in je))},
                              {"etiqueta": "Personas", "valor": len({r["empleado_id"] for r in je})}]
            out["personas"] = agrupar(je, lambda fs: {"jornadas": len(fs), "horas": _h(sum(_num(x["minutos"]) for x in fs))},
                                      lambda r: {"fecha": r["fecha"], "entrada": (r["hora_entrada"] or "")[:5],
                                                 "salida": (r["hora_salida"] or "")[:5], "horas": _h(r["minutos"]),
                                                 "estado": _causa(r["estado"])}, "horas")
            out["columnas"] = [{"id": "jornadas", "titulo": "Jornadas"}, {"id": "horas", "titulo": "Horas"}]
            out["columnas_registro"] = [{"id": "fecha", "titulo": "Fecha"}, {"id": "entrada", "titulo": "Entrada"},
                                        {"id": "salida", "titulo": "Salida"}, {"id": "horas", "titulo": "Horas"},
                                        {"id": "estado", "titulo": "Estado"}]

        elif k == "correcciones_manuales":
            todas = await self._filas(_SQL_MARCAS, (fi, ff), filtro, areas_permitidas)
            m = [r for r in todas if r["especial"] == 0 and r["con_reloj"] == 1]
            fuera_je = sum(1 for r in todas if r["especial"] == 1)
            completos = [r for r in todas if r["especial"] == 0 and r["con_reloj"] == 0]
            por_usuario = defaultdict(int)
            for r in m:
                por_usuario[r["usuario"] or "Sin usuario registrado"] += 1
            out["resumen"] = [{"etiqueta": "Correcciones a mano", "valor": len(m)},
                              {"etiqueta": "Días corregidos", "valor": len({(r["empleado_id"], r["fecha"]) for r in m})},
                              {"etiqueta": "Personas", "valor": len({r["empleado_id"] for r in m})}]
            out["resumen_extra"] = [
                {"titulo": "Ingresadas por",
                 "items": [{"etiqueta": u, "valor": n} for u, n in sorted(por_usuario.items(), key=lambda x: -x[1])]},
                {"titulo": "No cuentan como corrección",
                 "items": [{"etiqueta": "marcas de jornadas especiales, días libres o feriados", "valor": fuera_je},
                           {"etiqueta": "marcas de días hechos completos a mano"
                                        + (f" ({', '.join(sorted({r['persona'] for r in completos}))})" if completos else ""),
                            "valor": len(completos)}]},
            ]
            out["personas"] = agrupar(m, lambda fs: {"marcas": len(fs), "dias": len({x["fecha"] for x in fs})},
                                      lambda r: {"fecha": r["fecha"], "hora": r["hora"], "tipo": r["tipo"] or "",
                                                 "usuario": r["usuario"] or "Sin usuario registrado",
                                                 "observacion": r["observacion"]}, "marcas")
            out["columnas"] = [{"id": "marcas", "titulo": "Correcciones"}, {"id": "dias", "titulo": "Días"}]
            out["columnas_registro"] = [{"id": "fecha", "titulo": "Fecha"}, {"id": "hora", "titulo": "Hora"},
                                        {"id": "tipo", "titulo": "Tipo"}, {"id": "usuario", "titulo": "Ingresada por"},
                                        {"id": "observacion", "titulo": "Observación"}]

        elif k == "rotacion":
            p = (fi, t["fecha_fin"]) * 5
            mv = await self._filas(_SQL_MOVIMIENTOS, p, filtro, areas_permitidas)
            bajas = [r for r in mv if r["movimiento"] == "Baja"]
            out["resumen"] = [{"etiqueta": "Bajas", "valor": len(bajas)}, {"etiqueta": "Ingresos", "valor": len(mv) - len(bajas)}]
            out["personas"] = [{"persona": r["persona"], "area": r["area"],
                                "valores": {"movimiento": r["movimiento"], "fecha": str(r["fecha"] or "")[:10],
                                            "cargo": r["cargo"] or "", "contrato": r["tipo_contrato"] or ""},
                                "registros": []}
                               for r in sorted(mv, key=lambda r: (r["movimiento"] != "Baja", str(r["fecha"] or "")))]
            out["columnas"] = [{"id": "movimiento", "titulo": "Movimiento"}, {"id": "fecha", "titulo": "Fecha"},
                               {"id": "cargo", "titulo": "Cargo"}, {"id": "contrato", "titulo": "Contrato"}]
        return out


dashboard_detalle = DashboardDetalle()
