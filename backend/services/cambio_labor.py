"""
Cambio de labor desde una fecha (etapa B4b del plan de bonos, 22-11-2026).

La persona dueña decidió que, si alguien cambia de labor a mitad de período, el bono del cargo se paga en proporción a
los días en cada labor, y que el cambio se avisa por correo a «Avisos generales». Aquí está todo lo del cambio:
validar, mostrar qué bonos gana o pierde antes de guardar, guardar en el historial de cargos, avisar y dejarlo en la
auditoría. El cálculo de bonos ya usa el cargo de cada día (etapa B4a).
"""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from loguru import logger

from backend.core.database import Database


def _dia_antes(fecha: str) -> str:
    return (date.fromisoformat(fecha) - timedelta(days=1)).isoformat()


def tramos_con_cambio(tramos: List[Dict[str, Any]], cargo_id: int, fecha: str) -> List[Dict[str, Any]]:
    """Los tramos de cargo de una persona con un cambio de labor desde `fecha` (sin guardar nada). El tramo que cubre la
    fecha se corta el día antes; el nuevo dura hasta donde llegaba ese tramo. Si la fecha es el primer día de un tramo,
    ese tramo cambia de cargo."""
    out, puesto = [], False
    orden = sorted(tramos, key=lambda t: t["desde"])
    for i, t in enumerate(orden):
        cubre = t["desde"] <= fecha and (t["hasta"] is None or fecha <= t["hasta"])
        if not cubre:
            out.append(dict(t))
            continue
        puesto = True
        if t["desde"] == fecha:
            out.append(dict(t, cargo_id=cargo_id))
        else:
            out.append(dict(t, hasta=_dia_antes(fecha)))
            out.append({"cargo_id": cargo_id, "desde": fecha, "hasta": t["hasta"]})
    if not puesto:
        siguiente = next((t for t in orden if t["desde"] > fecha), None)
        out.append({"cargo_id": cargo_id, "desde": fecha, "hasta": _dia_antes(siguiente["desde"]) if siguiente else None})
    return sorted(out, key=lambda t: t["desde"])


class CambioLaborService:
    def __init__(self, db: Database):
        self.db = db

    async def _persona(self, empleado_id: int) -> Dict[str, Any]:
        emp = await self.db.fetch_one(
            "SELECT e.*, a.nombre AS area_nombre FROM empleados e LEFT JOIN areas a ON a.id = e.area_id WHERE e.id = ?", (empleado_id,))
        if not emp:
            raise HTTPException(status_code=404, detail="La persona no existe.")
        return emp

    async def _tramos(self, empleado_id: int) -> List[Dict[str, Any]]:
        filas = await self.db.fetch_all(
            "SELECT cargo_id, fecha_desde, fecha_hasta FROM historial_cargos WHERE empleado_id = ? ORDER BY fecha_desde", (empleado_id,))
        return [{"cargo_id": f["cargo_id"], "desde": str(f["fecha_desde"])[:10],
                 "hasta": str(f["fecha_hasta"])[:10] if f["fecha_hasta"] else None} for f in filas]

    async def _inicio_turno(self, empleado_id: int, fecha: str) -> Optional[str]:
        """Inicio del turno continuo de la persona vigente en `fecha` (dueño, 23-11-2026: el historial de cargos parte
        desde la asignación de turno, no desde la fecha de ingreso de la ficha, que es solo referencial)."""
        from backend.services.inicio_turno import inicios_de_turno
        return (await inicios_de_turno(self.db, [empleado_id], fecha, fecha)).get(empleado_id)

    async def _tramos_o_inicial(self, emp: Dict[str, Any]) -> List[Dict[str, Any]]:
        tramos = await self._tramos(emp["id"])
        if not tramos and emp.get("cargo_id"):
            hoy = datetime.now().strftime("%Y-%m-%d")
            desde = await self._inicio_turno(emp["id"], hoy) or "2000-01-01"
            tramos = [{"cargo_id": emp["cargo_id"], "desde": desde, "hasta": None}]
        return tramos

    async def validar(self, empleado_id: int, cargo_id: int, fecha: str) -> Dict[str, Any]:
        """Revisa el pedido y devuelve la persona, el cargo nuevo, el período de la fecha y los tramos de hoy."""
        try:
            fecha = date.fromisoformat(str(fecha)[:10]).isoformat()
        except ValueError:
            raise HTTPException(status_code=400, detail="La fecha no es válida.")
        emp = await self._persona(empleado_id)
        cargo = await self.db.fetch_one("SELECT id, nombre FROM cargos WHERE id = ?", (cargo_id,))
        if not cargo:
            raise HTTPException(status_code=400, detail="Elija un cargo de la lista.")
        if not await self._inicio_turno(empleado_id, fecha):
            raise HTTPException(status_code=400, detail="La persona no tiene turno asignado en esa fecha.")
        area = emp.get("area_nombre") or ""
        cerrado = await self.db.fetch_one(
            "SELECT fecha_inicio, fecha_fin FROM cierres_periodos WHERE area = ? AND fecha_inicio <= ? AND fecha_fin >= ? LIMIT 1",
            (area, fecha, fecha))
        if cerrado:
            raise HTTPException(status_code=400, detail=f"El período del {str(cerrado['fecha_inicio'])[:10]} al {str(cerrado['fecha_fin'])[:10]} "
                                                        f"ya está cerrado para {area}: no se puede cambiar la labor en esa fecha.")
        periodo = await self.db.fetch_one(
            "SELECT fecha_inicio, fecha_fin, mes_cierre FROM periodos_rrhh WHERE fecha_inicio <= ? AND fecha_fin >= ? ORDER BY fecha_inicio LIMIT 1",
            (fecha, fecha))
        if not periodo:
            raise HTTPException(status_code=400, detail="No hay un período de cierre que incluya esa fecha.")
        tramos = await self._tramos_o_inicial(emp)
        vigente = next((t for t in tramos if t["desde"] <= fecha and (t["hasta"] is None or fecha <= t["hasta"])), None)
        if vigente and vigente["cargo_id"] == cargo_id:
            raise HTTPException(status_code=400, detail=f"Desde esa fecha la persona ya tiene el cargo «{cargo['nombre']}».")
        nombres = {c["id"]: c["nombre"] for c in await self.db.fetch_all("SELECT id, nombre FROM cargos")}
        return {"emp": emp, "cargo": cargo, "fecha": fecha, "tramos": tramos,
                "anterior": nombres.get(vigente["cargo_id"]) if vigente else (emp.get("cargo") or ""),
                "periodo": {"inicio": str(periodo["fecha_inicio"])[:10], "fin": str(periodo["fecha_fin"])[:10],
                            "nombre": periodo.get("mes_cierre") or ""}}

    async def vista_previa(self, empleado_id: int, cargo_id: int, fecha: str, areas_permitidas=None) -> Dict[str, Any]:
        """Qué bonos tiene la persona en el período de la fecha, hoy y con el cambio (sin guardar)."""
        from backend.repositories.asistencia import AsistenciaRepository
        from backend.repositories.configuracion import ConfiguracionRepository
        from backend.services.asistencia_service import AsistenciaService
        from backend.services.bono_service import BonoService
        v = await self.validar(empleado_id, cargo_id, fecha)
        fi, ff = v["periodo"]["inicio"], v["periodo"]["fin"]
        data = await AsistenciaService(AsistenciaRepository(self.db)).get_matriz_periodo(
            fi, ff, None, None, None, areas_permitidas=areas_permitidas, empleado_id=empleado_id)
        emp = next((e for e in data.get("empleados", []) if e["id"] == empleado_id), None)
        cambios = []
        if emp:
            matrix = data.get("matrix", {})
            m = matrix.get(empleado_id) or matrix.get(str(empleado_id))
            just = [j for j in data.get("justificaciones", []) if j["empleado_id"] == empleado_id]
            asist = [a for a in data.get("data", []) if a["empleado_id"] == empleado_id]
            feriados = {r["fecha"] for r in await self.db.fetch_all("SELECT fecha FROM feriados WHERE fecha BETWEEN ? AND ?", (fi, ff))}
            hoy = datetime.now().strftime("%Y-%m-%d")
            bs = BonoService(self.db)
            antes = dict(emp, _tramos_cargo=v["tramos"])
            despues = dict(emp, _tramos_cargo=tramos_con_cambio(v["tramos"], cargo_id, v["fecha"]))
            for b in await ConfiguracionRepository(self.db).get_all_bonos():
                if not b.get("activo"):
                    continue
                if b.get("periodicidad") == "semanal":
                    # Bono semanal (Fill Rate): el monto de la semana sale de la regla de su cargo
                    from backend.services.bono_semanal import evaluar_bono_semanal
                    ra = (await evaluar_bono_semanal(self.db, bs, b, [antes], fi, ff, hoy)).get(empleado_id, {})
                    rd = (await evaluar_bono_semanal(self.db, bs, b, [dict(despues, cargo_id=cargo_id)], fi, ff, hoy)).get(empleado_id, {})
                else:
                    ra = bs._calificar_bono(antes, b, asist, just, m, hoy, fi, ff, feriados)
                    rd = bs._calificar_bono(despues, b, asist, just, m, hoy, fi, ff, feriados)
                if not ra.get("aplica") and not rd.get("aplica"):
                    continue
                corto = lambda r: {"aplica": bool(r.get("aplica")), "califica": bool(r.get("califica")),
                                   "monto": int(round(r.get("monto") or 0))}
                cambios.append({"bono": b["nombre"], "beneficio": b.get("tipo") == "beneficio", "antes": corto(ra), "despues": corto(rd)})
        return {"persona": " ".join(x for x in (v["emp"].get("nombre"), v["emp"].get("apellido_paterno"), v["emp"].get("apellido_materno")) if x),
                "anterior": v["anterior"], "nuevo": v["cargo"]["nombre"], "fecha": v["fecha"], "periodo": v["periodo"],
                "sin_turno": emp is None, "bonos": cambios}

    async def guardar(self, empleado_id: int, cargo_id: int, fecha: str, motivo: str, usuario_id: Optional[int],
                      usuario: str, vista: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Guarda el cambio en el historial de cargos y, si ya rige hoy, en la ficha. Lo deja en la auditoría y avisa."""
        motivo = (motivo or "").strip()
        if not motivo:
            raise HTTPException(status_code=400, detail="Falta el motivo del cambio de labor.")
        v = await self.validar(empleado_id, cargo_id, fecha)
        emp, fecha = v["emp"], v["fecha"]
        hoy = datetime.now().strftime("%Y-%m-%d")
        async with self.db.transaction():
            if not await self._tramos(empleado_id) and emp.get("cargo_id"):
                desde = await self._inicio_turno(empleado_id, fecha) or "2000-01-01"
                await self.db.execute("INSERT INTO historial_cargos (empleado_id, cargo_id, fecha_desde, motivo) VALUES (?, ?, ?, ?)",
                                      (empleado_id, emp["cargo_id"], desde, "Cargo de la ficha al crear el historial"))
            filas = await self.db.fetch_all(
                "SELECT id, cargo_id, fecha_desde, fecha_hasta FROM historial_cargos WHERE empleado_id = ? ORDER BY fecha_desde", (empleado_id,))
            cubre = next((f for f in filas if str(f["fecha_desde"])[:10] <= fecha and (not f["fecha_hasta"] or fecha <= str(f["fecha_hasta"])[:10])), None)
            if cubre and str(cubre["fecha_desde"])[:10] == fecha:
                await self.db.execute("UPDATE historial_cargos SET cargo_id = ?, motivo = ?, usuario = ? WHERE id = ?",
                                      (cargo_id, motivo, usuario, cubre["id"]))
            else:
                hasta = None
                if cubre:
                    hasta = str(cubre["fecha_hasta"])[:10] if cubre["fecha_hasta"] else None
                    await self.db.execute("UPDATE historial_cargos SET fecha_hasta = ? WHERE id = ?", (_dia_antes(fecha), cubre["id"]))
                else:
                    sig = next((f for f in filas if str(f["fecha_desde"])[:10] > fecha), None)
                    hasta = _dia_antes(str(sig["fecha_desde"])[:10]) if sig else None
                await self.db.execute(
                    "INSERT INTO historial_cargos (empleado_id, cargo_id, fecha_desde, fecha_hasta, motivo, usuario) VALUES (?, ?, ?, ?, ?, ?)",
                    (empleado_id, cargo_id, fecha, hasta, motivo, usuario))
            if fecha <= hoy:
                await self.aplicar_cargos_vigentes(empleado_id)
        from backend.repositories.seguridad import SeguridadRepository
        nombre = " ".join(x for x in (emp.get("nombre"), emp.get("apellido_paterno"), emp.get("apellido_materno")) if x)
        await SeguridadRepository(self.db).log_auditoria(
            usuario_id, usuario, "CAMBIO_LABOR", "Empleados",
            f"Cambio de labor de {nombre} (ID {empleado_id}): '{v['anterior']}' a '{v['cargo']['nombre']}' desde {fecha}. Motivo: {motivo}")
        enviado = await self._avisar(v, nombre, motivo, usuario, vista)
        return {"ok": True, "anterior": v["anterior"], "nuevo": v["cargo"]["nombre"], "fecha": fecha, "correo": enviado}

    async def aplicar_cargos_vigentes(self, empleado_id: Optional[int] = None) -> int:
        """La ficha muestra el cargo que rige hoy según el historial (un cambio con fecha futura se aplica cuando llega).
        Devuelve cuántas fichas cambió."""
        hoy = datetime.now().strftime("%Y-%m-%d")
        filtro, params = ("AND h.empleado_id = ?", (hoy, hoy, empleado_id)) if empleado_id else ("", (hoy, hoy))
        filas = await self.db.fetch_all(
            "SELECT h.empleado_id, h.cargo_id, c.nombre FROM historial_cargos h JOIN cargos c ON c.id = h.cargo_id "
            f"JOIN empleados e ON e.id = h.empleado_id WHERE h.fecha_desde <= ? AND (h.fecha_hasta IS NULL OR h.fecha_hasta >= ?) {filtro} "
            "AND e.cargo_id <> h.cargo_id", params)
        for f in filas:
            await self.db.execute("UPDATE empleados SET cargo_id = ?, cargo = ?, cargo_local = 1 WHERE id = ?", (f["cargo_id"], f["nombre"], f["empleado_id"]))
        if filas:
            logger.info(f"🔁 Cargo de la ficha puesto al día con el historial de cargos: {len(filas)} personas")
        return len(filas)

    async def _avisar(self, v, nombre, motivo, usuario, vista) -> bool:
        """Correo a «Avisos generales» (los mismos que reciben los avisos de justificaciones del área)."""
        try:
            from backend.repositories.configuracion import ConfiguracionRepository
            from backend.services.configuracion_service import ConfiguracionService
            from backend.services.notification_service import NotificationService
            from backend.core.rut import rut_visible
            destinatarios = await ConfiguracionService(ConfiguracionRepository(self.db)).get_destinatarios_rrhh(v["emp"].get("area_nombre"))
            if not destinatarios:
                return False
            return bool(await NotificationService().send_cambio_labor_email(
                {"nombre_completo": nombre, "rut_formateado": rut_visible(v["emp"].get("rut")), "area": v["emp"].get("area_nombre") or ""},
                v["anterior"], v["cargo"]["nombre"], v["fecha"], motivo, usuario, (vista or {}).get("bonos") or [], destinatarios))
        except Exception as e:
            logger.error(f"No se pudo avisar el cambio de labor por correo: {e}")
            return False
