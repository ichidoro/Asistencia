from typing import List, Dict, Any, Optional
from datetime import date, datetime
from loguru import logger

from backend.core.database import Database
from backend.repositories.configuracion import ConfiguracionRepository
from backend.services.asistencia_service import AsistenciaService
from backend.repositories.asistencia import AsistenciaRepository


# ── Estados que significan que el empleado SÍ estuvo presente ese día ──────
ESTADOS_PRESENCIA = frozenset([
    "OK", "ATRASO", "SALIDA_ADELANTADA", "ATR_SAD",
    "EXTRA", "EN_CURSO", "ANOMALIA", "JORNADA_ESPECIAL",
    "BOL", "BOLSA", "VACACIONES",
    "PER", "PER_ATR", "PER_SAD", "PER_ATR_SAD", "PERMISO",
    "INASISTENCIA_COMPENSADA", "JORNADA_COMPENSATORIA"
])

# ── Estados que NO son laborables (no cuentan para ningún cálculo) ──────────
ESTADOS_NO_LABORABLES = frozenset(["LIBRE", "FERIADO"])


class BonoService:
    def __init__(self, db: Database):
        self.db = db
        self.config_repo = ConfiguracionRepository(db)


    # ──────────────────────────────────────────────────────────────────────
    # EVALUACIÓN DIRECTA (recibe datos ya cargados — reutilizable)
    # ──────────────────────────────────────────────────────────────────────
    async def evaluar_bonos_directo(
        self,
        empleados:          List[Dict[str, Any]],
        asistencias_list:   List[Dict[str, Any]],
        justificaciones_list: List[Dict[str, Any]],
        matrix_data:        Dict[int, Any] = None,
        *,
        fecha_inicio: str,
        fecha_fin:    str,
    ) -> Dict[int, Dict[str, Any]]:
        """Evalúa los bonos con los datos ya cargados, para el período de cierre [fecha_inicio, fecha_fin] (AAAA-MM-DD),
        las fechas de la tabla de períodos, sean las que sean (etapa B1 del plan de bonos, 22-11-2026: antes usaba el
        mes calendario)."""
        bonos = await self.config_repo.get_all_bonos()
        # Solo los bonos en pesos: el beneficio en especie (4 Productos) lo evalúa su propia pantalla (etapa B3d)
        bonos_activos = [b for b in bonos if b.get("activo") and b.get("tipo") != "beneficio"]

        # Feriados del período (puede cruzar el año), para no contar como de turno un feriado dentro de una justificación
        feriados_rows = await self.db.fetch_all(
            "SELECT fecha FROM feriados WHERE fecha BETWEEN ? AND ?", (fecha_inicio, fecha_fin)
        )
        feriados_set = {r['fecha'] for r in feriados_rows}

        # Índices por empleado_id para O(1) lookup
        asist_map: Dict[int, list] = {}
        for a in asistencias_list:
            asist_map.setdefault(a["empleado_id"], []).append(a)

        just_map: Dict[int, list] = {}
        for j in justificaciones_list:
            just_map.setdefault(j["empleado_id"], []).append(j)

        # El cargo de cada día del período (historial de cargos, etapa B4)
        empleados = await self.con_tramos_de_cargo(empleados, fecha_inicio, fecha_fin)

        hoy_str = datetime.now().strftime("%Y-%m-%d")

        resultados: Dict[int, Dict[str, Any]] = {}
        for emp in empleados:
            emp_id = emp["id"]
            resultados[emp_id] = {
                bono["nombre"]: self._calificar_bono(
                    emp,
                    bono,
                    asist_map.get(emp_id, []),
                    just_map.get(emp_id, []),
                    matrix_data.get(emp_id) if matrix_data else None,
                    hoy_str,
                    fecha_inicio,
                    fecha_fin,
                    feriados_set,
                )
                for bono in bonos_activos
            }

        return resultados

    async def con_tramos_de_cargo(self, empleados: List[Dict[str, Any]], fecha_inicio: str, fecha_fin: str) -> List[Dict[str, Any]]:
        """Copia de cada persona con sus tramos de cargo del período («_tramos_cargo»), para que el bono use el cargo de
        cada día (etapa B4 del plan de bonos)."""
        from backend.repositories.empleado import EmpleadoRepository
        try:
            tramos = await EmpleadoRepository(self.db).get_tramos_cargo([e["id"] for e in empleados], fecha_inicio, fecha_fin)
        except Exception as e:
            logger.error(f"[BonoService] No se pudo leer el historial de cargos: {e}")
            tramos = {}
        return [dict(e, _tramos_cargo=tramos.get(e["id"], [])) for e in empleados]

    async def vista_previa(self, bono: Dict[str, Any], fecha_inicio: str, fecha_fin: str,
                           areas_permitidas: Optional[List] = None) -> Dict[str, Any]:
        """Quién recibe el bono y cuánto en el período [fecha_inicio, fecha_fin] con la configuración que se está editando,
        sin guardarla (etapa B3c del plan de bonos). También las personas con las que calza más de una regla."""
        srv = AsistenciaService(AsistenciaRepository(self.db))
        data = await srv.get_matriz_periodo(fecha_inicio, fecha_fin, None, None, None, areas_permitidas=areas_permitidas)
        feriados = {r['fecha'] for r in await self.db.fetch_all(
            "SELECT fecha FROM feriados WHERE fecha BETWEEN ? AND ?", (fecha_inicio, fecha_fin))}
        just: Dict[int, list] = {}
        for j in data.get("justificaciones", []):
            just.setdefault(j["empleado_id"], []).append(j)
        asist: Dict[int, list] = {}
        for a in data.get("data", []):
            asist.setdefault(a["empleado_id"], []).append(a)
        matrix = data.get("matrix", {})
        hoy = datetime.now().strftime("%Y-%m-%d")
        personas, pisan = [], []
        for emp in await self.con_tramos_de_cargo(data.get("empleados", []), fecha_inicio, fecha_fin):
            nombre = " ".join(x for x in (emp.get("apellido_paterno"), emp.get("apellido_materno"), emp.get("nombre")) if x)
            calzan = self.reglas_que_calzan(emp, bono)
            if len(calzan) > 1 and not emp.get("excluido_asistencia"):
                pisan.append({"nombre": nombre, "reglas": [i + 1 for i in calzan]})
            r = self._calificar_bono(emp, bono, asist.get(emp["id"], []), just.get(emp["id"], []),
                                     matrix.get(emp["id"]) or matrix.get(str(emp["id"])), hoy, fecha_inicio, fecha_fin, feriados)
            if not r.get("aplica"):
                continue
            if bono.get("tipo") == "beneficio":
                r = dict(r, monto=0)
            personas.append({"nombre": nombre, "area": emp.get("area") or "", "regla": calzan[0] + 1 if calzan else None,
                             "califica": bool(r.get("califica")), "monto": int(round(r.get("monto") or 0)),
                             "motivo": self._motivo_corto(r)})
        personas.sort(key=lambda p: p["nombre"])
        return {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin, "hoy": hoy, "personas": personas, "pisan": pisan,
                "total": sum(p["monto"] for p in personas),
                "beneficio": bono.get("tipo") == "beneficio",
                "reciben": sum(1 for p in personas if p["califica"] and (p["monto"] > 0 or bono.get("tipo") == "beneficio")),
                "no_cobran": sum(1 for p in personas if not p["califica"])}

    @staticmethod
    def _motivo_corto(r: Dict[str, Any]) -> str:
        """Los días que no cuentan, agrupados por causa («Inasistencia sin justificar: 3 días»), para la vista previa."""
        cuenta: Dict[str, int] = {}
        for d in r.get("perdidos") or []:
            cuenta[d["causa"]] = cuenta.get(d["causa"], 0) + 1
        if not cuenta:
            return r.get("motivo") or ""
        partes = "; ".join(f"{c}: {n} {'día' if n == 1 else 'días'}" for c, n in cuenta.items())
        return partes if not r.get("califica") else f"{r.get('motivo')} ({partes})"

    @staticmethod
    def reglas_que_calzan(empleado: Dict[str, Any], bono: Dict[str, Any]) -> List[int]:
        """Posiciones de las reglas del bono que calzan con la persona por contrato y cargo. Se usa la primera; si hay
        más de una, las reglas se pisan (la vista previa lo avisa, etapa B3c del plan de bonos). Los cargos de la regla
        son los elegidos de la lista (etapa B3b): se compara el cargo de la persona, no su nombre escrito."""
        cargo_id = empleado.get("cargo_id")
        contrato = (empleado.get("tipo_contrato") or "").strip().upper()
        out = []
        for i, regla in enumerate(bono.get("reglas") or []):
            requeridos = regla.get("cargos_req_ids")
            if requeridos and cargo_id not in requeridos:
                continue
            if cargo_id in (regla.get("cargos_excl_ids") or []):
                continue
            if regla.get("tipo_contrato") and contrato != regla["tipo_contrato"].strip().upper():
                continue
            out.append(i)
        return out

    # ──────────────────────────────────────────────────────────────────────
    # MOTOR CENTRAL DE CALIFICACIÓN
    # ──────────────────────────────────────────────────────────────────────
    def _calificar_bono(
        self,
        empleado:       Dict[str, Any],
        bono:           Dict[str, Any],
        asistencias:    List[Dict[str, Any]],
        justificaciones: List[Dict[str, Any]],
        emp_matrix_data: Optional[Dict[str, Any]],
        hoy_str:   str,
        periodo_inicio: str,
        periodo_fin:    str,
        feriados_set: Optional[set] = None,
    ) -> Dict[str, Any]:
        """
        La persona parte con el bono. Cada día de turno del período que ya pasó:
          • con presencia → cuenta como asistido;
          • con justificación → lo que diga la configuración de esa justificación en este bono (etapa B3a del plan de
            bonos, 22-11-2026): cuenta como asistido, descuenta en proporción o hace perder el bono;
          • sin presencia ni justificación (inasistencia sin justificar) → lo que diga el bono: descuenta en proporción o
            hace perder el bono.
        Un día que hace perder el bono lo deja en 0. Si no, se paga monto × días asistidos / días revisados.
        Ingreso o salida a mitad del período → además, monto proporcional a sus días de turno en el período.
        Nada de esto está escrito en el código: sale de bono["efectos"] y bono["efecto_inasistencia"].
        """

        # ── 0. Exclusión de empleados sin asistencia (Art 22) ──────────────
        if empleado.get("excluido_asistencia"):
            return {"aplica": False, "califica": False, "monto": 0,
                    "motivo": "Excluido de asistencia (Art 22)"}

        # ── 1. Filtro estructural: cargo / contrato (la primera regla que calza) ──
        # Con el historial de cargos (etapa B4) la regla se elige con el cargo de cada día; sin cambios de labor en el
        # período es una sola regla para todo el período, como antes.
        tramos = [t for t in (empleado.get("_tramos_cargo") or [])
                  if t["desde"] <= periodo_fin and (t["hasta"] is None or t["hasta"] >= periodo_inicio)]
        cargos_periodo = {t["cargo_id"] for t in tramos}
        por_dia = bool(tramos) and cargos_periodo != {empleado.get("cargo_id")}
        regla_de_cargo: Dict[Any, Any] = {}

        def _regla_con_cargo(cid):
            if cid not in regla_de_cargo:
                c = self.reglas_que_calzan(dict(empleado, cargo_id=cid), bono)
                regla_de_cargo[cid] = bono["reglas"][c[0]] if c else None
            return regla_de_cargo[cid]

        def _cargo_del_dia(fecha):
            for t in tramos:
                if t["desde"] <= fecha and (t["hasta"] is None or fecha <= t["hasta"]):
                    return t["cargo_id"]
            # Antes del primer tramo (el historial partió desde la fecha de ingreso de la ficha, que puede ser posterior al
            # inicio del turno): el cargo de ese primer tramo, no el de hoy (23-11-2026)
            if tramos and fecha < tramos[0]["desde"]:
                return tramos[0]["cargo_id"]
            return empleado.get("cargo_id")

        if por_dia:
            reglas_usadas = [r for r in (_regla_con_cargo(c) for c in cargos_periodo | {empleado.get("cargo_id")}) if r]
            regla_activa = reglas_usadas[0] if reglas_usadas else None
        else:
            calzan = self.reglas_que_calzan(empleado, bono)
            regla_activa = bono["reglas"][calzan[0]] if calzan else None

        if regla_activa is None:
            return {"aplica": False, "califica": False, "monto": 0,
                    "motivo": "No aplica por Cargo/Contrato"}

        monto_completo = regla_activa.get("monto", 0)
        efectos = bono.get("efectos") or {}
        efecto_inas = bono.get("efecto_inasistencia")

        def _efecto_justificacion(j):
            """(efecto, causa) de un día con esta justificación. Si falta configurarlo, el bono no se paga y el motivo
            lo dice: no hay un valor escondido en el código."""
            nombre = j.get("tipo_nombre") or "la justificación"
            ef = efectos.get(j.get("tipo_id")) or efectos.get(str(j.get("tipo_id")))
            if ef in ("asistido", "proporcion", "pierde"):
                return ef, nombre
            return "pierde", f"Falta configurar el efecto de «{nombre}» en este bono"

        def _efecto_inasistencia():
            if efecto_inas in ("proporcion", "pierde"):
                return efecto_inas, "Inasistencia sin justificar"
            return "pierde", "Falta configurar el efecto de la inasistencia sin justificar en este bono"

        # ── 2. Días del período que le corresponden: desde el inicio de su turno y hasta su salida ─────
        # Desde el inicio del turno continuo, no desde la fecha de ingreso de la ficha, que es solo referencial (dueño,
        # 23-11-2026; ver inicio_turno.py). La grilla lo trae en «inicio_turno»
        inicio = empleado.get("inicio_turno") if "inicio_turno" in empleado else empleado.get("fecha_ingreso")
        fecha_desde = max((inicio or periodo_inicio)[:10], periodo_inicio)
        # La salida cuenta solo si la persona ya está inactiva (igual que la grilla): en una activa es el término de su
        # contrato, que puede renovarse
        salida = empleado.get("fecha_salida") if not empleado.get("activo", 1) else None
        fecha_hasta = min((salida or periodo_fin)[:10], periodo_fin)

        # ── 3. Si no hay matrix_data → fallback simplificado ──────────────
        if not emp_matrix_data:
            logger.warning(
                f"[BonoService] Bono '{bono['nombre']}' sin projecciones "
                f"para empleado {empleado['id']} — usando fallback"
            )
            for a in asistencias:
                if fecha_desde <= a["fecha"] <= fecha_hasta and a["estado"] in ("FALTA", "INASISTENCIA"):
                    j_dia = next(
                        (j for j in justificaciones
                         if j["fecha_inicio"] <= a["fecha"] <= j["fecha_fin"]), None
                    )
                    ef, causa = _efecto_justificacion(j_dia) if j_dia else _efecto_inasistencia()
                    if ef == "pierde":
                        return {"aplica": True, "califica": False, "monto": 0,
                                "proporcional": False,
                                "perdidos": [{"fecha": a["fecha"], "causa": causa}],
                                "motivo": f"{causa} el {a['fecha']}"}
            return {"aplica": True, "califica": True, "monto": monto_completo,
                    "proporcional": False, "motivo": "OK (Fallback sin proyecciones)"}

        # ── 4. Recorrer los días del período en la matriz ─────────────────
        #    La matriz puede traer días fuera del período: no cuentan.
        dias_laborables  = 0   # días de turno ya transcurridos (hasta hoy) que le corresponden: se revisan
        dias_asistidos   = 0
        dias_asignados   = 0   # días de turno del período que le corresponden (desde el inicio de su turno, hasta su salida)
        dias_periodo     = 0   # días de turno de todo el período (para el proporcional por ingreso o salida)
        suma_montos      = 0.0  # con cambio de labor: el monto de la regla de cada día asignado
        reglas_dias      = set()
        pierde           = []  # días que hacen perder el bono, con su causa (para el informe de cierre)
        descuenta        = []  # días que descuentan en proporción, con su causa

        for fecha, dia_data in emp_matrix_data.items():
            if fecha == "info" or not (periodo_inicio <= fecha <= periodo_fin):
                continue

            info = emp_matrix_data.get('info', {})
            estado        = (dia_data.get("estado") or "").upper()
            horas_teoricas = dia_data.get("horas_teoricas") or 0
            # Los dos nombres con que se guarda la Bolsa Flexible, igual que el resto del sistema (etapa B6)
            es_bolsa      = (info.get("tipo_programacion") in ("BOLSA_FLEXIBLE", "FLEXIBLE_BOLSA"))
            j_dia = next(
                (j for j in justificaciones
                 if j["fecha_inicio"] <= fecha <= j["fecha_fin"]), None
            )

            turno_dias = info.get('turno_dias', {})
            try:
                dia_semana = datetime.strptime(fecha, "%Y-%m-%d").weekday()
                dia_config = turno_dias.get(dia_semana) or turno_dias.get(str(dia_semana), {})
                es_libre_turno = bool(dia_config.get('es_libre', False))
            except Exception:
                es_libre_turno = False

            es_feriado = feriados_set is not None and fecha in feriados_set

            if es_bolsa:
                # Bolsa Flexible no tiene horas de turno por día: cuentan los días con presencia o inasistencia y, igual que
                # en Ciclo, un día justificado que en su horario no es libre ni feriado (vacío M del plan de bonos,
                # 22-11-2026: antes se saltaba y lo configurado en la justificación no alcanzaba a las personas de Bolsa)
                es_laborable_turno = (
                    estado not in ESTADOS_NO_LABORABLES
                    and (estado in ESTADOS_PRESENCIA
                         or estado in ("INASISTENCIA", "FALTA")
                         or (j_dia is not None and not es_libre_turno and not es_feriado))
                )
            else:
                es_laborable_turno = (
                    estado not in ESTADOS_NO_LABORABLES
                    and (
                        (horas_teoricas > 0) or
                        (j_dia is not None and not es_libre_turno and not es_feriado)
                    )
                )

            if not es_laborable_turno:
                continue

            dias_periodo += 1
            if fecha < fecha_desde or fecha > fecha_hasta:
                continue
            if por_dia:
                regla_dia = _regla_con_cargo(_cargo_del_dia(fecha))
                if regla_dia is None:
                    continue          # ese día su cargo no recibe este bono
                suma_montos += regla_dia.get("monto", 0) or 0
                reglas_dias.add(id(regla_dia))
                monto_completo = regla_dia.get("monto", 0)
            dias_asignados += 1

            # Solo se revisan los días que ya pasaron
            if fecha > hoy_str:
                continue

            dias_laborables += 1

            if estado in ESTADOS_PRESENCIA:
                dias_asistidos += 1
                continue
            ef, causa = _efecto_justificacion(j_dia) if j_dia else _efecto_inasistencia()
            if ef == "asistido":
                dias_asistidos += 1
            elif ef == "proporcion":
                descuenta.append({"fecha": fecha, "causa": causa})
            else:
                pierde.append({"fecha": fecha, "causa": causa})

        # ── 5. Calcular resultado ─────────────────────────────────────────
        if dias_laborables == 0:
            # El período no ha comenzado aún o todos los días son libres hasta hoy
            # → proyectamos como "califica" con monto 0 (aún sin datos)
            return {
                "aplica": True, "califica": True, "monto": 0,
                "proporcional": False,
                "motivo": "Pendiente: sin días laborables registrados aún."
            }

        # Factor de proporcionalidad por ingreso o salida a mitad del período
        if dias_periodo > 0 and dias_asignados != dias_periodo:
            factor_ingreso = dias_asignados / dias_periodo
        else:
            factor_ingreso = 1.0

        # ── 5a. Un día que hace perder el bono lo deja en 0 ──────────────
        if pierde:
            return {
                "aplica": True, "califica": False, "monto": 0,
                "proporcional": False,
                "perdidos": pierde,
                "motivo": " ".join(f"{d['fecha']}: {d['causa']}." for d in pierde),
            }

        # ── 5b. Se paga por los días asistidos (y por ingreso o salida) ──
        factor_asistencia = dias_asistidos / dias_laborables
        factor_total = factor_asistencia * factor_ingreso
        if por_dia and len(reglas_dias) > 1:
            # Cambio de labor entre reglas con montos distintos: cada día vale el monto de la regla de su cargo
            monto_final = round(suma_montos / dias_periodo * factor_asistencia) if dias_periodo else 0
        else:
            monto_final = round(monto_completo * factor_total)
        partes = []
        if descuenta:
            partes.append(f"{dias_asistidos}/{dias_laborables} días asistidos")
        if factor_ingreso < 1.0:
            partes.append(f"{dias_asignados}/{dias_periodo} días de turno del período (turno desde "
                          f"{(inicio or '?')[:10]}{', salida ' + salida[:10] if salida else ''})")
        return {
            "aplica": True, "califica": True,
            "monto": monto_final,
            "monto_completo": monto_completo,
            "proporcional": factor_total < 1.0,
            "factor": round(factor_total, 4),
            "dias_asistidos": dias_asistidos,
            "dias_laborables": dias_laborables,
            "dias_asignados": dias_asignados,
            "dias_periodo": dias_periodo,
            "perdidos": descuenta,
            "motivo": ("Proporcional: " + " × ".join(partes)) if partes
                      else f"Asistencia completa {dias_asistidos}/{dias_laborables}",
        }
