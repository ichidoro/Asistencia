"""Dashboard, pestaña «Indicadores»: cada indicador del tramo elegido contra el promedio de los tramos
anteriores, lo que empeoró primero (estructura B, elegida por el dueño el 27-10-2026).

Reglas (ver REGLAS_ASISTENCIA.md §8):
- Mismas definiciones que «Lo que falta hacer»: área vigente en la fecha, libreta desde «Sin reloj a
  partir de», días justificados por tipo de justificación, permiso o compensación.
- Promedio = promedio simple del valor de cada tramo anterior que tiene días programados. No hay metas:
  se compara con la propia historia.
- Un tramo cerrado guarda el cálculo de su época: la comparación lo advierte.
- Solo lee.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.core.config import settings
from backend.core.database import db as _db
from backend.services.dashboard_pendientes import _JUSTIFICADO, _LIBRETA, _area_de, _num, visible

_PROG = ("x.libreta = 0 AND x.justificado = 0 AND x.con_horas = 1 "
         "AND x.estado NOT IN ('LIBRE', 'FERIADO', 'NO_ACTIVO')")

_SQL_DIAS = f"""
    SELECT x.tramo, x.area,
           SUM(CASE WHEN {_PROG} THEN 1 ELSE 0 END) AS programados,
           SUM(CASE WHEN {_PROG} AND x.entrada = 1 THEN 1 ELSE 0 END) AS asistidos,
           SUM(CASE WHEN {_PROG} AND x.entrada = 1 AND x.minutos_atraso > 0 THEN 1 ELSE 0 END) AS con_atraso,
           SUM(CASE WHEN {_PROG} AND x.entrada = 1 THEN x.minutos_atraso ELSE 0 END) AS minutos_atraso,
           SUM(CASE WHEN x.libreta = 0 AND x.estado = 'INASISTENCIA' THEN 1 ELSE 0 END) AS faltas,
           SUM(CASE WHEN x.con_horas = 1 AND x.justificado = 1 THEN 1 ELSE 0 END) AS justificados,
           SUM(CASE WHEN x.con_horas = 1 AND x.estado LIKE 'LICENCIA%' THEN 1 ELSE 0 END) AS licencias,
           SUM(CASE WHEN {_PROG} THEN x.horas_teoricas ELSE 0 END) AS horas_programadas,
           SUM(CASE WHEN x.libreta = 0 THEN x.minutos_deuda ELSE 0 END) AS minutos_deuda
      FROM (SELECT p.id AS tramo, {_area_de('a.empleado_id', 'a.fecha')} AS area, a.estado,
                   COALESCE(a.minutos_atraso, 0) AS minutos_atraso, COALESCE(a.minutos_deuda, 0) AS minutos_deuda,
                   COALESCE(a.horas_teoricas, 0) AS horas_teoricas,
                   CASE WHEN a.hora_entrada_real IS NOT NULL AND a.hora_entrada_real <> '' THEN 1 ELSE 0 END AS entrada,
                   CASE WHEN COALESCE(a.horas_teoricas, 0) > 0 THEN 1 ELSE 0 END AS con_horas,
                   {_LIBRETA} AS libreta, {_JUSTIFICADO} AS justificado
              FROM asistencias a
              JOIN periodos_rrhh p ON a.fecha BETWEEN p.fecha_inicio AND p.fecha_fin
              LEFT JOIN turnos t ON t.id = a.turno_asignado_id
             WHERE a.fecha BETWEEN ? AND ?) x
     WHERE x.area IS NOT NULL
     GROUP BY x.tramo, x.area
"""

_SQL_HE = f"""
    SELECT p.id AS tramo, {_area_de('he.empleado_id', 'he.fecha')} AS area,
           SUM(CASE WHEN he.estado = 'APROBADO' THEN COALESCE(he.minutos_autorizados, 0) ELSE 0 END) AS minutos_he
      FROM horas_extras he JOIN periodos_rrhh p ON he.fecha BETWEEN p.fecha_inicio AND p.fecha_fin
     WHERE he.fecha BETWEEN ? AND ?
     GROUP BY 1, 2
"""

_SQL_JE = f"""
    SELECT p.id AS tramo, {_area_de('je.empleado_id', 'je.fecha')} AS area,
           SUM(COALESCE(je.minutos_trabajados, 0)) AS minutos_je
      FROM jornadas_especiales je JOIN periodos_rrhh p ON je.fecha BETWEEN p.fecha_inicio AND p.fecha_fin
     WHERE je.fecha BETWEEN ? AND ?
     GROUP BY 1, 2
"""

# Correcciones a mano (decisión del dueño, 27-10-2026): marcas a mano en días de trabajo normal en que el
# reloj también marcó; las de jornadas especiales (trabajo fuera de la planta), días libres y feriados, y los
# días hechos completos a mano no cuentan. Se cuentan marcas por persona y día y después el área de ese día.
_ESPECIAL = ("CASE WHEN EXISTS (SELECT 1 FROM jornadas_especiales je WHERE je.empleado_id = g.empleado_id AND je.fecha = g.dia) "
             "OR EXISTS (SELECT 1 FROM asistencias a2 WHERE a2.empleado_id = g.empleado_id AND a2.fecha = g.dia "
             "AND a2.estado IN ('EXTRA', 'JORNADA_ESPECIAL', 'LIBRE', 'FERIADO')) THEN 1 ELSE 0 END")
_SQL_MARCAS = f"""
    SELECT p.id AS tramo, {_area_de('m.empleado_id', 'm.dia')} AS area,
           SUM(CASE WHEN m.especial = 0 THEN m.total ELSE 0 END) AS marcas,
           SUM(CASE WHEN m.especial = 0 AND m.reloj > 0 THEN m.manuales ELSE 0 END) AS manuales
      FROM (SELECT g.*, {_ESPECIAL} AS especial
              FROM (SELECT l.empleado_id, LEFT(CAST(l.fecha_hora AS TEXT), 10) AS dia, COUNT(*) AS total,
                           SUM(CASE WHEN COALESCE(l.manual, 0) = 1 THEN 1 ELSE 0 END) AS manuales,
                           SUM(CASE WHEN COALESCE(l.manual, 0) = 0 THEN 1 ELSE 0 END) AS reloj
                      FROM logs_raw l
                     WHERE LEFT(CAST(l.fecha_hora AS TEXT), 10) BETWEEN ? AND ?
                     GROUP BY 1, 2) g) m
      JOIN periodos_rrhh p ON m.dia BETWEEN p.fecha_inicio AND p.fecha_fin
     GROUP BY 1, 2
"""

# Dotación al cierre de cada tramo, bajas (personas inactivas que salieron en el tramo) e ingresos.
_SQL_PERSONAS = f"""
    SELECT p.id AS tramo, {_area_de('e.id', 'p.fecha_fin')} AS area,
           SUM(CASE WHEN (e.fecha_ingreso IS NULL OR e.fecha_ingreso = '' OR e.fecha_ingreso <= p.fecha_fin)
                     AND (e.activo = 1 OR (e.fecha_salida IS NOT NULL AND e.fecha_salida > p.fecha_fin)) THEN 1 ELSE 0 END) AS dotacion,
           SUM(CASE WHEN e.activo = 0 AND e.fecha_salida BETWEEN p.fecha_inicio AND p.fecha_fin THEN 1 ELSE 0 END) AS bajas,
           SUM(CASE WHEN e.fecha_ingreso BETWEEN p.fecha_inicio AND p.fecha_fin THEN 1 ELSE 0 END) AS ingresos
      FROM periodos_rrhh p CROSS JOIN empleados e
     WHERE p.fecha_inicio <= ? AND p.fecha_fin >= ?
     GROUP BY 1, 2
"""

# Qué mide cada indicador. «alto»: más es mejor; «bajo»: menos es mejor.
# Tipo «tasa» se compara área por área contra su propio promedio; «total» muestra las áreas que más suman.
INDICADORES = [
    {"id": "puntualidad", "nombre": "Puntualidad", "unidad": "%", "mejor": "alto", "tipo": "tasa",
     "definicion": "Días que llegaron a la hora sobre los días trabajados", "accion": "grilla"},
    {"id": "ausentismo", "nombre": "Ausentismo", "unidad": "%", "mejor": "bajo", "tipo": "tasa",
     "definicion": "Días no trabajados (faltas, licencias, vacaciones, permisos) sobre los programados", "accion": "grilla"},
    {"id": "faltas", "nombre": "Faltas sin aviso", "unidad": "", "mejor": "bajo", "tipo": "total",
     "definicion": "Días de trabajo sin marcas ni justificación", "accion": "grilla"},
    {"id": "minutos_atraso", "nombre": "Minutos por atraso", "unidad": "min", "mejor": "bajo", "tipo": "tasa",
     "definicion": "Minutos promedio de cada llegada tarde", "accion": "grilla"},
    {"id": "sobretiempo", "nombre": "Sobretiempo", "unidad": "%", "mejor": "bajo", "tipo": "tasa",
     "definicion": "Horas extra aprobadas sobre las horas programadas", "accion": "he"},
    {"id": "horas_extra", "nombre": "Horas extra aprobadas", "unidad": "h", "mejor": "bajo", "tipo": "total",
     "definicion": "Horas extra aprobadas en el tramo", "accion": "he"},
    {"id": "jornadas_especiales", "nombre": "Jornadas especiales", "unidad": "h", "mejor": "bajo", "tipo": "total",
     "definicion": "Horas trabajadas en días libres o feriados", "accion": "grilla"},
    {"id": "deuda", "nombre": "Deuda horaria", "unidad": "h", "mejor": "bajo", "tipo": "total",
     "definicion": "Horas que faltaron para cumplir el horario", "accion": "grilla"},
    {"id": "correcciones_manuales", "nombre": "Correcciones a mano", "unidad": "%", "mejor": "bajo", "tipo": "tasa",
     "definicion": "Marcas a mano que completan o corrigen un día de trabajo en que el reloj también marcó, sobre las marcas de esos días",
     "accion": "grilla"},
    {"id": "rotacion", "nombre": "Rotación", "unidad": "%", "mejor": "bajo", "tipo": "rotacion",
     "definicion": "Bajas sobre la dotación al cierre del tramo", "accion": "empleados"},
]

_CAMPOS = ("programados", "asistidos", "con_atraso", "minutos_atraso", "faltas", "justificados", "licencias",
           "horas_programadas", "minutos_deuda", "minutos_he", "minutos_je", "marcas", "manuales",
           "dotacion", "bajas", "ingresos")


def _div(a: float, b: float, factor: float = 1.0) -> Optional[float]:
    return a * factor / b if b else None


def calcular(s: Dict[str, float]) -> Dict[str, Optional[float]]:
    """Valor de cada indicador a partir de las sumas de un tramo (de toda la empresa o de un área)."""
    base_aus = s["programados"] + s["justificados"]
    return {
        "puntualidad": None if not s["asistidos"] else 100.0 * (1 - s["con_atraso"] / s["asistidos"]),
        "ausentismo": _div((s["programados"] - s["asistidos"]) + s["justificados"], base_aus, 100.0),
        "faltas": s["faltas"],
        "minutos_atraso": (_div(s["minutos_atraso"], s["con_atraso"]) or 0.0) if s["asistidos"] else None,
        "sobretiempo": _div(s["minutos_he"] / 60.0, s["horas_programadas"], 100.0),
        "horas_extra": s["minutos_he"] / 60.0,
        "jornadas_especiales": s["minutos_je"] / 60.0,
        "deuda": s["minutos_deuda"] / 60.0,
        "correcciones_manuales": _div(s["manuales"], s["marcas"], 100.0),
        "rotacion": _div(s["bajas"], s["dotacion"], 100.0),
    }


def comparar(valor: Optional[float], previos: List[Optional[float]], mejor: str) -> Dict[str, Any]:
    """Compara un valor con el promedio simple de los tramos anteriores que tienen dato."""
    datos = [v for v in previos if v is not None]
    if valor is None or not datos:
        return {"promedio": None, "estado": "sin_comparacion", "cambio": None}
    prom = sum(datos) / len(datos)
    diferencia = round(valor, 1) - round(prom, 1)
    if diferencia == 0:
        estado = "igual"
    else:
        peor = diferencia > 0 if mejor == "bajo" else diferencia < 0
        estado = "empeoro" if peor else "mejoro"
    cambio = None if prom == 0 else (valor - prom) / prom * 100.0
    return {"promedio": prom, "estado": estado, "cambio": cambio}


def gravedad(item: Dict[str, Any]) -> float:
    """Para ordenar: cuánto empeoró (o mejoró) en proporción a su promedio; sin promedio va al final."""
    cambio, prom, valor = item.get("cambio"), item.get("promedio"), item.get("valor")
    if prom == 0 and valor:
        return float("inf")
    if cambio is None:
        return -1.0
    return abs(cambio)


def donde(ind: Dict[str, Any], estado: str, por_area: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Áreas que explican el indicador: en una tasa, las que empeoraron contra su propio promedio (las que más);
    en un total, las que más suman en el tramo."""
    if ind["tipo"] == "total":
        filas = [{"area": a, "valor": d["valor"]} for a, d in por_area.items() if d["valor"]]
        return sorted(filas, key=lambda f: -f["valor"])[:2]
    if ind["tipo"] != "tasa":
        return []
    peores = []
    for a, d in por_area.items():
        if d["valor"] is None or d["promedio"] is None:
            continue
        dif = d["valor"] - d["promedio"]
        empeora = dif > 0 if ind["mejor"] == "bajo" else dif < 0
        if empeora and round(abs(dif), 1) > 0:
            peores.append({"area": a, "valor": d["valor"], "promedio": d["promedio"], "_dif": abs(dif)})
    peores.sort(key=lambda f: -f["_dif"])
    for f in peores:
        f.pop("_dif")
    return peores[:2] if estado == "empeoro" else peores[:1]


class DashboardIndicadores:
    def __init__(self, db=None):
        self.db = db or _db

    async def _sumas(self, desde: str, hasta: str) -> Dict[Any, Dict[str, Dict[str, float]]]:
        """{tramo: {área: {campo: suma}}} de todas las fuentes."""
        out: Dict[Any, Dict[str, Dict[str, float]]] = {}

        def acc(rows, campos):
            for r in rows:
                if not r["area"]:
                    continue
                d = out.setdefault(r["tramo"], {}).setdefault(r["area"], {c: 0.0 for c in _CAMPOS})
                for c in campos:
                    d[c] += _num(r[c])

        acc(await self.db.fetch_all(_SQL_DIAS, (desde, hasta)),
            ("programados", "asistidos", "con_atraso", "minutos_atraso", "faltas", "justificados", "licencias",
             "horas_programadas", "minutos_deuda"))
        acc(await self.db.fetch_all(_SQL_HE, (desde, hasta)), ("minutos_he",))
        acc(await self.db.fetch_all(_SQL_JE, (desde, hasta)), ("minutos_je",))
        acc(await self.db.fetch_all(_SQL_MARCAS, (desde, hasta)), ("marcas", "manuales"))
        acc(await self.db.fetch_all(_SQL_PERSONAS, (hasta, desde)), ("dotacion", "bajas", "ingresos"))
        return out

    async def resumen(self, tramo_id: Optional[int] = None, area: Optional[str] = None,
                      areas_permitidas: Optional[List[str]] = None) -> Dict[str, Any]:
        filtro = area if area and area != "Todas" else None
        hoy = datetime.now(ZoneInfo(settings.TIMEZONE)).strftime("%Y-%m-%d")
        tramos = [dict(r) for r in await self.db.fetch_all(
            "SELECT id, mes_cierre, fecha_inicio, fecha_fin FROM periodos_rrhh ORDER BY fecha_inicio")]
        if not tramos:
            return {"tramos": [], "tramo": None, "indicadores": []}
        hasta_todo = min(hoy, str(tramos[-1]["fecha_fin"]))
        sumas = await self._sumas(str(tramos[0]["fecha_inicio"]), hasta_todo)

        def suma(tid, areas=None):
            s = {c: 0.0 for c in _CAMPOS}
            for a, d in (sumas.get(tid) or {}).items():
                if visible(a, filtro, areas_permitidas) and (areas is None or a in areas):
                    for c in _CAMPOS:
                        s[c] += d[c]
            return s

        con_datos = [t for t in tramos if suma(t["id"])["programados"] > 0]
        elegibles = [t for t in con_datos if str(t["fecha_fin"]) < hoy] or con_datos
        if not elegibles:
            return {"tramos": [], "tramo": None, "indicadores": []}
        elegido = next((t for t in con_datos if t["id"] == tramo_id), None) or elegibles[-1]
        previos = [t for t in con_datos if str(t["fecha_fin"]) < str(elegido["fecha_inicio"])]

        actual = calcular(suma(elegido["id"]))
        historia = [calcular(suma(t["id"])) for t in previos]
        areas = sorted({a for t in con_datos for a in (sumas.get(t["id"]) or {})
                        if visible(a, filtro, areas_permitidas)})
        por_area_actual = {a: calcular(suma(elegido["id"], {a})) for a in areas}
        por_area_hist = {a: [calcular(suma(t["id"], {a})) for t in previos] for a in areas}
        s_act = suma(elegido["id"])

        salida = []
        for ind in INDICADORES:
            k = ind["id"]
            c = comparar(actual[k], [h[k] for h in historia], ind["mejor"])
            item = {**ind, "valor": actual[k], **c}
            pa = {}
            for a in areas:
                ca = comparar(por_area_actual[a][k], [h[k] for h in por_area_hist[a]], ind["mejor"])
                pa[a] = {"valor": por_area_actual[a][k], "promedio": ca["promedio"]}
            item["donde"] = donde(ind, c["estado"], pa)
            if k == "rotacion":
                item["detalle"] = {"bajas": int(s_act["bajas"]), "ingresos": int(s_act["ingresos"]),
                                   "dotacion": int(s_act["dotacion"])}
            if k == "ausentismo" and s_act["licencias"] > 0:
                sin_lic = [t["mes_cierre"] for t in previos if suma(t["id"])["licencias"] == 0]
                if sin_lic:
                    item["nota"] = (f"{len(sin_lic)} de {len(previos)} tramos anteriores no tienen licencias "
                                    f"registradas: el aumento puede ser en parte por eso")
            salida.append(item)

        orden = {"empeoro": 0, "mejoro": 1, "igual": 2, "sin_comparacion": 3}
        salida.sort(key=lambda i: (orden[i["estado"]], -gravedad(i)))
        return {
            "tramos": [{"id": t["id"], "mes": t["mes_cierre"], "fecha_inicio": str(t["fecha_inicio"]),
                        "fecha_fin": str(t["fecha_fin"]), "en_curso": str(t["fecha_fin"]) >= hoy} for t in con_datos],
            "tramo": {"id": elegido["id"], "mes": elegido["mes_cierre"], "fecha_inicio": str(elegido["fecha_inicio"]),
                      "fecha_fin": str(elegido["fecha_fin"]), "en_curso": str(elegido["fecha_fin"]) >= hoy},
            "comparado_con": [t["mes_cierre"] for t in previos],
            "dotacion": {"activos": int(s_act["dotacion"]), "ingresos": int(s_act["ingresos"]), "bajas": int(s_act["bajas"])},
            "indicadores": salida,
        }


dashboard_indicadores = DashboardIndicadores()
