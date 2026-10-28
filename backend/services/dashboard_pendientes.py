"""Dashboard «Lo que falta hacer»: una sola lectura con todo lo que la pantalla muestra.

Reglas (ver REGLAS_ASISTENCIA.md §8):
- El área de cada día es la vigente en esa fecha según historial_areas (igual que el cierre).
- «Con reloj» excluye a los horarios de libreta (desde su fecha «Sin reloj a partir de») y a
  los días justificados (tipo de justificación, permiso o inasistencia compensada).
- El estado del cierre de cada área sale de CierreService.bloqueos_cierre: el Dashboard y el
  asistente de cierre usan la misma revisión.
- Solo lee: no recalcula ni escribe nada.
"""
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from loguru import logger

from backend.core.config import settings
from backend.core.database import db as _db
from backend.repositories.configuracion import ConfiguracionRepository
from backend.repositories.empleado import EmpleadoRepository
from backend.services.cierre_service import CierreService
from backend.services.reglas_marcas_def import MARCA_REVISION_REGLA

# Ventana de contratos por vencer: el ajuste «Días de anticipación para alertas de vencimiento»
# (Configuración). El número de abajo es solo el respaldo si el ajuste faltara (el mismo de la semilla).
AJUSTE_DIAS_CONTRATOS = "vencimiento_dias_alerta"
DIAS_CONTRATOS_RESPALDO = 45


def _area_de(emp: str, fecha: str) -> str:
    return f"""(SELECT ar.nombre FROM historial_areas h LEFT JOIN areas ar ON ar.id = h.area_id
                 WHERE h.empleado_id = {emp} AND h.validado = 1
                   AND {fecha} >= h.fecha_desde
                   AND (h.fecha_hasta IS NULL OR h.fecha_hasta = '' OR {fecha} <= h.fecha_hasta)
                 ORDER BY h.id DESC LIMIT 1)"""


_LIBRETA = ("CASE WHEN t.modalidad_control = 'LIBRETA_180H' AND (t.libreta_desde IS NULL "
            "OR t.libreta_desde = '' OR a.fecha >= t.libreta_desde) THEN 1 ELSE 0 END")
_JUSTIFICADO = ("CASE WHEN a.justificacion_id IS NOT NULL "
                "OR UPPER(TRIM(a.estado)) IN (SELECT UPPER(TRIM(nombre)) FROM justificacion_tipos) "
                "OR a.estado IN ('PERMISO', 'INASISTENCIA_COMPENSADA', 'JORNADA_COMPENSATORIA') "
                "THEN 1 ELSE 0 END")

# Días de una persona con sus marcas: una fila por día con las banderas que usan las cuentas.
# Hoy solo cuenta a los activos; un tramo cuenta a todos los que tuvieron días en él (también
# a quien dejó la empresa después).
_DIAS = f"""
    SELECT {_area_de('a.empleado_id', 'a.fecha')} AS area, a.empleado_id, a.fecha, a.estado,
           COALESCE(a.minutos_atraso, 0) AS minutos_atraso,
           CASE WHEN a.hora_entrada_real IS NOT NULL AND a.hora_entrada_real <> '' THEN 1 ELSE 0 END AS entrada,
           CASE WHEN COALESCE(a.horas_teoricas, 0) > 0 THEN 1 ELSE 0 END AS con_horas,
           {_LIBRETA} AS libreta, {_JUSTIFICADO} AS justificado
      FROM asistencias a
      JOIN empleados e ON e.id = a.empleado_id
      LEFT JOIN turnos t ON t.id = a.turno_asignado_id
     WHERE a.fecha BETWEEN ? AND ? {{activos}}
"""

# Programado con reloj: tiene horas del horario, no es libreta, no está justificado y no es libre.
_PROG = "x.con_horas = 1 AND x.libreta = 0 AND x.justificado = 0 AND x.estado NOT IN ('LIBRE', 'FERIADO', 'NO_ACTIVO')"

_SQL_HOY = f"""
    SELECT x.area,
           SUM(CASE WHEN {_PROG} THEN 1 ELSE 0 END) AS con_reloj,
           SUM(CASE WHEN {_PROG} AND x.entrada = 1 THEN 1 ELSE 0 END) AS llegaron,
           SUM(CASE WHEN {_PROG} AND x.entrada = 1 AND x.minutos_atraso > 0 THEN 1 ELSE 0 END) AS con_atraso,
           SUM(CASE WHEN {_PROG} AND x.entrada = 1 THEN x.minutos_atraso ELSE 0 END) AS minutos_atraso,
           SUM(CASE WHEN {_PROG} AND x.estado = 'INASISTENCIA' THEN 1 ELSE 0 END) AS faltan,
           SUM(CASE WHEN {_PROG} AND x.entrada = 0 AND x.estado = 'PENDIENTE' THEN 1 ELSE 0 END) AS aun_no_marcan,
           SUM(CASE WHEN x.estado = 'EN_CURSO' THEN 1 ELSE 0 END) AS en_turno,
           SUM(CASE WHEN x.justificado = 1 THEN 1 ELSE 0 END) AS justificados,
           SUM(CASE WHEN x.libreta = 1 AND x.estado = 'PENDIENTE' THEN 1 ELSE 0 END) AS libreta_por_registrar,
           SUM(CASE WHEN x.libreta = 0 AND x.con_horas = 0 AND x.entrada = 1 THEN 1 ELSE 0 END) AS en_dia_libre
      FROM ({_DIAS.format(activos='AND e.activo = 1')}) x
     WHERE x.area IS NOT NULL
     GROUP BY x.area
     ORDER BY x.area
"""

_SQL_TRAMO_AREA = f"""
    SELECT x.area,
           SUM(CASE WHEN {_PROG} THEN 1 ELSE 0 END) AS programados,
           SUM(CASE WHEN {_PROG} AND x.entrada = 1 THEN 1 ELSE 0 END) AS asistidos,
           SUM(CASE WHEN {_PROG} AND x.entrada = 1 AND x.minutos_atraso > 0 THEN 1 ELSE 0 END) AS con_atraso,
           SUM(CASE WHEN {_PROG} AND x.estado = 'INASISTENCIA' THEN 1 ELSE 0 END) AS faltas
      FROM ({_DIAS.format(activos='')}) x
     WHERE x.area IS NOT NULL
     GROUP BY x.area
     ORDER BY x.area
"""

_SQL_HE_PENDIENTES = f"""
    SELECT {_area_de('he.empleado_id', 'he.fecha')} AS area, COUNT(*) AS solicitudes,
           COALESCE(SUM(he.minutos_bruto), 0) AS minutos
      FROM horas_extras he
     WHERE he.fecha BETWEEN ? AND ? AND he.estado = 'PENDIENTE' AND he.minutos_bruto > 0
     GROUP BY 1
"""

# Una jornada especial queda decidida al validarla (EXTRA), aprobarla como hora extra
# (HORAS_EXTRAS), rechazarla (RECHAZADA) o compensarla (COMPENSATORIA).
_SQL_JE_POR_VALIDAR = f"""
    SELECT {_area_de('je.empleado_id', 'je.fecha')} AS area, COUNT(*) AS jornadas
      FROM jornadas_especiales je
     WHERE je.fecha BETWEEN ? AND ?
       AND COALESCE(je.estado, '') NOT IN ('EXTRA', 'HORAS_EXTRAS', 'RECHAZADA', 'COMPENSATORIA')
     GROUP BY 1
"""


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _pct(parte: float, total: float) -> Optional[float]:
    return round(parte * 100.0 / total, 1) if total else None


def visible(area: Optional[str], filtro: Optional[str], permitidas: Optional[List[str]]) -> bool:
    """¿Esta área se muestra? `filtro` = área elegida en la pantalla; `permitidas` = alcance del usuario
    (None = ve todas)."""
    if not area:
        return False
    if filtro and area != filtro:
        return False
    if permitidas is not None and area not in permitidas:
        return False
    return True


def clasificar_area(cerrado: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Estado del cierre de un área a partir de la misma revisión que usa el asistente de cierre.

    `b` trae (de CierreService.bloqueos_cierre más el detalle de cada día bloqueado):
    he_pendientes, he_minutos, por_revisar, fechas_por_revisar, libreta_dias, libreta_personas,
    anomalias, otros_pendientes, en_curso, inasistencias. Puede cerrarse exactamente cuando el
    asistente lo permite: sin horas extra por decidir, sin días en anomalía o pendientes, sin
    jornadas en curso y sin días por revisar (las inasistencias se aceptan al cerrar).
    """
    if cerrado:
        return {"estado": "cerrado", "cerrado": cerrado}
    b = b or {}
    bloqueos = (b.get("he_pendientes", 0) + b.get("por_revisar", 0) + b.get("libreta_dias", 0)
                + b.get("anomalias", 0) + b.get("otros_pendientes", 0) + b.get("en_curso", 0))
    salida = {k: b.get(k, 0) for k in ("he_pendientes", "por_revisar", "libreta_dias", "libreta_personas",
                                         "anomalias", "otros_pendientes", "en_curso", "inasistencias")}
    salida["he_minutos"] = _num(b.get("he_minutos"))
    salida["he_horas"] = round(salida["he_minutos"] / 60.0, 1)
    salida["fechas_por_revisar"] = b.get("fechas_por_revisar", [])
    salida["estado"] = "listo" if bloqueos == 0 else "pendiente"
    return salida


def resumir_contratos(empleados: List[Dict[str, Any]], hoy: str, dias: int) -> Dict[str, Any]:
    """Agrupa por fecha de término los contratos que vencen (o ya vencieron) sin nombrar a nadie."""
    por_fecha: Dict[str, int] = {}
    vencidos = sin_decision = 0
    for e in empleados:
        f = str(e.get("fecha_salida") or "")[:10]
        if not f:
            continue
        if f < hoy:
            vencidos += 1
        else:
            por_fecha[f] = por_fecha.get(f, 0) + 1
        if not (e.get("decision_vencimiento") or "").strip():
            sin_decision += 1
    return {
        "dias": dias,
        "total": sum(por_fecha.values()),
        "vencidos": vencidos,
        "sin_decision": sin_decision,
        "por_fecha": [{"fecha": f, "total": n} for f, n in sorted(por_fecha.items())],
    }


class DashboardPendientes:
    def __init__(self, db=None):
        self.db = db or _db

    async def _tramos(self, hoy: str):
        rows = await self.db.fetch_all(
            "SELECT id, mes_cierre, fecha_inicio, fecha_fin, estado, activo FROM periodos_rrhh ORDER BY fecha_inicio")
        tramos = [dict(r) for r in rows]
        en_curso = next((t for t in tramos if str(t["fecha_inicio"]) <= hoy <= str(t["fecha_fin"])), None)
        pasados_abiertos = [t for t in tramos if str(t["fecha_fin"]) < hoy and (t.get("estado") or "") != "cerrado"]
        return en_curso, pasados_abiertos

    async def _detalle_bloqueados(self, ids: List[int]) -> Dict[int, Dict[str, Any]]:
        if not ids:
            return {}
        ph = ",".join("?" * len(ids))
        rows = await self.db.fetch_all(
            f"""SELECT a.id, a.estado, a.empleado_id, {_LIBRETA} AS libreta,
                       CASE WHEN a.observaciones LIKE ? THEN 1 ELSE 0 END AS en_revision
                  FROM asistencias a LEFT JOIN turnos t ON t.id = a.turno_asignado_id
                 WHERE a.id IN ({ph})""",
            tuple([f"%{MARCA_REVISION_REGLA}%"] + ids))
        return {r["id"]: dict(r) for r in rows}

    async def _tramo_por_cerrar(self, t: Dict[str, Any], filtro, permitidas) -> Optional[Dict[str, Any]]:
        fi, ff = str(t["fecha_inicio"]), str(t["fecha_fin"])
        areas_rows = await self.db.fetch_all(
            f"SELECT DISTINCT {_area_de('a.empleado_id', 'a.fecha')} AS area FROM asistencias a WHERE a.fecha BETWEEN ? AND ?",
            (fi, ff))
        areas = sorted(r["area"] for r in areas_rows if visible(r["area"], filtro, permitidas))
        if not areas:
            return None
        cierres = await self.db.fetch_all(
            "SELECT area, created_at, username, tipo_cierre FROM cierres_periodos "
            "WHERE fecha_inicio <= ? AND fecha_fin >= ? ORDER BY created_at", (ff, fi))
        cerrado_global = next((dict(c) for c in cierres if not c["area"]), None)
        cerrado_area = {c["area"]: dict(c) for c in cierres if c["area"]}

        servicio = CierreService(self.db)
        salida = []
        for area in areas:
            c = cerrado_area.get(area) or cerrado_global
            if c:
                salida.append({"area": area, **clasificar_area(
                    {"fecha": str(c.get("created_at") or ""), "por": c.get("username") or "",
                     "tipo": c.get("tipo_cierre") or ""}, None)})
                continue
            b = await servicio.bloqueos_cierre(fi, ff, area)
            unicos = lambda filas: list({r["id"]: r for r in filas}.values())
            he, anom = unicos(b["he_pendientes"]), unicos(b["anomalias"])
            det = await self._detalle_bloqueados([r["id"] for r in anom])
            lib = [d for d in det.values() if d["estado"] == "PENDIENTE" and d["libreta"] == 1]
            datos = {
                "he_pendientes": len(he),
                "he_minutos": sum(_num(r.get("minutos_bruto")) for r in he),
                "por_revisar": len(b["por_revisar"]),
                "fechas_por_revisar": sorted({str(d.get("fecha"))[:10] for d in b["por_revisar"]}),
                "libreta_dias": len(lib),
                "libreta_personas": len({d["empleado_id"] for d in lib}),
                "anomalias": sum(1 for d in det.values() if d["estado"] != "PENDIENTE" and d["en_revision"] == 0),
                "otros_pendientes": sum(1 for d in det.values() if d["estado"] == "PENDIENTE" and d["libreta"] == 0),
                "en_curso": len(unicos(b["en_curso"])),
                "inasistencias": len(unicos(b["inasistencias"])),
            }
            # Un día por revisar que también está en anomalía se cuenta una sola vez (como por revisar);
            # los que el detalle no encontró se cuentan como anomalía para no esconder un bloqueo.
            datos["anomalias"] += len([r for r in anom if r["id"] not in det])
            salida.append({"area": area, **clasificar_area(None, datos)})
        return {"id": t["id"], "mes": t["mes_cierre"], "fecha_inicio": fi, "fecha_fin": ff, "areas": salida}

    async def resumen(self, area: Optional[str] = None, areas_permitidas: Optional[List[str]] = None) -> Dict[str, Any]:
        filtro = area if area and area != "Todas" else None
        ahora = datetime.now(ZoneInfo(settings.TIMEZONE))
        hoy = ahora.strftime("%Y-%m-%d")

        en_curso, pasados = await self._tramos(hoy)

        hoy_rows = [dict(r) for r in await self.db.fetch_all(_SQL_HOY, (hoy, hoy))
                    if visible(r["area"], filtro, areas_permitidas)]
        campos_hoy = ("con_reloj", "llegaron", "con_atraso", "minutos_atraso", "faltan", "aun_no_marcan",
                      "en_turno", "justificados", "libreta_por_registrar", "en_dia_libre")
        for r in hoy_rows:
            for k in campos_hoy:
                r[k] = int(round(_num(r.get(k))))
        total_hoy = {k: sum(r[k] for r in hoy_rows) for k in campos_hoy}

        por_cerrar = []
        for t in pasados:
            try:
                tr = await self._tramo_por_cerrar(t, filtro, areas_permitidas)
            except Exception as e:
                logger.error(f"Dashboard: no se pudo revisar el tramo {t.get('mes_cierre')}: {e}")
                tr = None
            if tr and any(a["estado"] != "cerrado" for a in tr["areas"]):
                por_cerrar.append(tr)

        # Horas extra por decidir: las del tramo en curso más las que bloquean un tramo por cerrar.
        he_areas: Dict[str, Dict[str, float]] = {}
        he_tramos = []
        for tr in por_cerrar:
            n = sum(a.get("he_pendientes", 0) for a in tr["areas"])
            if n:
                h = round(sum(a.get("he_horas", 0) for a in tr["areas"]), 1)
                he_tramos.append({"mes": tr["mes"], "solicitudes": n, "horas": h})
                for a in tr["areas"]:
                    if a.get("he_pendientes"):
                        acc = he_areas.setdefault(a["area"], {"solicitudes": 0, "minutos": 0.0})
                        acc["solicitudes"] += a["he_pendientes"]
                        acc["minutos"] += a["he_minutos"]
        if en_curso:
            rows = await self.db.fetch_all(_SQL_HE_PENDIENTES, (str(en_curso["fecha_inicio"]), hoy))
            n = m = 0
            for r in rows:
                if not visible(r["area"], filtro, areas_permitidas):
                    continue
                acc = he_areas.setdefault(r["area"], {"solicitudes": 0, "minutos": 0.0})
                acc["solicitudes"] += int(r["solicitudes"])
                acc["minutos"] += _num(r["minutos"])
                n += int(r["solicitudes"])
                m += _num(r["minutos"])
            if n:
                he_tramos.append({"mes": en_curso["mes_cierre"], "solicitudes": n, "horas": round(m / 60.0, 1)})
        he_lista = sorted(({"area": k, "solicitudes": v["solicitudes"], "horas": round(v["minutos"] / 60.0, 1)}
                           for k, v in he_areas.items()), key=lambda x: (-x["horas"], x["area"]))

        # Jornadas especiales sin decidir en los tramos abiertos.
        desde_abierto = min([str(t["fecha_inicio"]) for t in por_cerrar]
                            + ([str(en_curso["fecha_inicio"])] if en_curso else [hoy]))
        je_rows = await self.db.fetch_all(_SQL_JE_POR_VALIDAR, (desde_abierto, hoy))
        je_lista = [{"area": r["area"], "jornadas": int(r["jornadas"])} for r in je_rows
                    if visible(r["area"], filtro, areas_permitidas)]

        # Cómo va el tramo por área (el primero por cerrar; si no hay, el en curso hasta hoy).
        base = por_cerrar[0] if por_cerrar else None
        if base:
            t_ini, t_fin, t_mes = base["fecha_inicio"], base["fecha_fin"], base["mes"]
        elif en_curso:
            t_ini, t_fin, t_mes = str(en_curso["fecha_inicio"]), hoy, en_curso["mes_cierre"]
        else:
            t_ini = t_fin = t_mes = None
        tramo_areas = []
        if t_ini:
            for r in await self.db.fetch_all(_SQL_TRAMO_AREA, (t_ini, t_fin)):
                if not visible(r["area"], filtro, areas_permitidas):
                    continue
                prog, asis, atr = _num(r["programados"]), _num(r["asistidos"]), _num(r["con_atraso"])
                tramo_areas.append({"area": r["area"], "programados": int(prog), "asistidos": int(asis),
                                    "con_atraso": int(atr), "faltas": int(_num(r["faltas"])),
                                    "asistencia_pct": _pct(asis, prog), "dias_con_atraso_pct": _pct(atr, asis)})

        try:
            dias_c = int(float(await ConfiguracionRepository(self.db).get_ajuste(AJUSTE_DIAS_CONTRATOS, DIAS_CONTRATOS_RESPALDO)))
        except (TypeError, ValueError):
            dias_c = DIAS_CONTRATOS_RESPALDO
        emps = await EmpleadoRepository(self.db).get_upcoming_expirations(dias_c, areas=areas_permitidas)
        contratos = resumir_contratos(
            [{"fecha_salida": e.fecha_salida, "decision_vencimiento": e.decision_vencimiento}
             for e in emps if not filtro or e.area == filtro], hoy, dias_c)

        dia_tramo = None
        if en_curso:
            d0 = date.fromisoformat(str(en_curso["fecha_inicio"]))
            dia_tramo = {"dia": (date.fromisoformat(hoy) - d0).days + 1,
                         "dias": (date.fromisoformat(str(en_curso["fecha_fin"])) - d0).days + 1}

        return {
            "generado": ahora.strftime("%Y-%m-%d %H:%M"),
            "hoy": hoy,
            "hoy_por_area": hoy_rows,
            "hoy_total": total_hoy,
            "tramos_por_cerrar": por_cerrar,
            "tramo_en_curso": ({"id": en_curso["id"], "mes": en_curso["mes_cierre"],
                                "fecha_inicio": str(en_curso["fecha_inicio"]), "fecha_fin": str(en_curso["fecha_fin"]),
                                **(dia_tramo or {})} if en_curso else None),
            "horas_extra_por_decidir": {"solicitudes": sum(x["solicitudes"] for x in he_lista),
                                        "horas": round(sum(x["horas"] for x in he_lista), 1),
                                        "por_tramo": he_tramos, "por_area": he_lista},
            "jornadas_por_validar": {"total": sum(x["jornadas"] for x in je_lista), "por_area": je_lista},
            "tramo_por_area": {"mes": t_mes, "fecha_inicio": t_ini, "fecha_fin": t_fin, "areas": tramo_areas},
            "contratos": contratos,
        }


dashboard_pendientes = DashboardPendientes()
