import calendar
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
    # PUNTO DE ENTRADA — carga datos y delega
    # ──────────────────────────────────────────────────────────────────────
    async def evaluar_bonos_mes(
        self, mes: int, anio: int, empleados: List[Dict[str, Any]]
    ) -> Dict[int, Dict[str, Any]]:
        """
        Evalúa todos los bonos activos para una lista de empleados en un mes.
        Retorna {empleado_id: {nombre_bono: resultado}}.
        """
        last_day = calendar.monthrange(anio, mes)[1]
        fecha_inicio = f"{anio}-{mes:02d}-01"
        fecha_fin    = f"{anio}-{mes:02d}-{last_day:02d}"

        asistencias_raw = await self.db.fetch_all(
            "SELECT * FROM asistencias WHERE fecha BETWEEN ? AND ?",
            (fecha_inicio, fecha_fin),
        )

        just_raw = await self.db.fetch_all(
            """
            SELECT j.*, jt.nombre AS tipo_nombre,
                   jt.con_goce_sueldo, jt.descuenta_remuneracion, jt.pagador,
                   COALESCE(cp.aplica_bono, 1) AS aplica_bono_pagador
            FROM justificaciones j
            JOIN justificacion_tipos jt ON j.tipo_id = jt.id
            LEFT JOIN cat_pagadores cp ON jt.pagador = cp.nombre
            WHERE j.fecha_inicio <= ? AND j.fecha_fin >= ?
            """,
            (fecha_fin, fecha_inicio),
        )

        asist_service = AsistenciaService(AsistenciaRepository(self.db))
        matrix_res  = await asist_service.get_matrix_data_with_projections(mes, anio)
        matrix_data = matrix_res.get("matrix", {})

        return await self.evaluar_bonos_directo(
            empleados, asistencias_raw, just_raw, matrix_data, mes, anio
        )

    # ──────────────────────────────────────────────────────────────────────
    # EVALUACIÓN DIRECTA (recibe datos ya cargados — reutilizable)
    # ──────────────────────────────────────────────────────────────────────
    async def evaluar_bonos_directo(
        self,
        empleados:          List[Dict[str, Any]],
        asistencias_list:   List[Dict[str, Any]],
        justificaciones_list: List[Dict[str, Any]],
        matrix_data:        Dict[int, Any] = None,
        mes:  int = None,
        anio: int = None,
    ) -> Dict[int, Dict[str, Any]]:
        """Versión optimizada que recibe los datos ya cargados."""
        bonos = await self.config_repo.get_all_bonos()
        bonos_activos = [b for b in bonos if b.get("activo")]

        # Query feriados for the year to avoid counting holiday days as laborable during justifications
        anio_real = anio or datetime.now().year
        feriados_rows = await self.db.fetch_all(
            "SELECT fecha FROM feriados WHERE fecha LIKE ?", (f"{anio_real}-%",)
        )
        feriados_set = {r['fecha'] for r in feriados_rows}

        # Índices por empleado_id para O(1) lookup
        asist_map: Dict[int, list] = {}
        for a in asistencias_list:
            asist_map.setdefault(a["empleado_id"], []).append(a)

        just_map: Dict[int, list] = {}
        for j in justificaciones_list:
            just_map.setdefault(j["empleado_id"], []).append(j)

        # Contexto temporal
        hoy_str   = datetime.now().strftime("%Y-%m-%d")
        mes_real  = mes  or datetime.now().month
        last_day  = calendar.monthrange(anio_real, mes_real)[1]
        mes_inicio = f"{anio_real}-{mes_real:02d}-01"
        mes_fin    = f"{anio_real}-{mes_real:02d}-{last_day:02d}"

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
                    mes_inicio,
                    mes_fin,
                    feriados_set,
                )
                for bono in bonos_activos
            }

        return resultados

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
        mes_inicio: str,
        mes_fin:    str,
        feriados_set: Optional[set] = None,
    ) -> Dict[str, Any]:
        """
        Nueva lógica:
          • El empleado PARTE con el bono adjudicado.
          • Solo lo PIERDE por:
              1. Inasistencia injustificada.
              2. Justificación sin goce de sueldo (o pagador externo).
          • Ingreso a mitad de mes → monto proporcional a sus días asignados.
          • TRANSPORTE (es_proporcional=1) → siempre proporcional, nunca pérdida total.
        """

        def _match_cargo(emp_cargo: str, req_val: str) -> bool:
            if not req_val or str(req_val).strip().upper() in ("NONE", "NULL", ""):
                return True
            cargo_emp  = (emp_cargo or "").strip().upper()
            cargos_req = [c.strip().upper() for c in str(req_val).split(",")]
            return cargo_emp in cargos_req

        # ── 1. Filtro estructural: cargo / contrato ────────────────────────
        regla_activa = None
        for regla in bono.get("reglas", []):
            if not _match_cargo(empleado.get("cargo"), regla.get("cargo_requerido")):
                continue
            if regla.get("cargos_excluidos"):
                excluidos = [c.strip().upper() for c in str(regla["cargos_excluidos"]).split(",")]
                if (empleado.get("cargo") or "").strip().upper() in excluidos:
                    continue
            if regla.get("tipo_contrato") and (
                (empleado.get("tipo_contrato") or "").strip().upper()
                != regla["tipo_contrato"].strip().upper()
            ):
                continue
            regla_activa = regla
            break  # primera regla que coincide

        if regla_activa is None:
            return {"aplica": False, "califica": False, "monto": 0,
                    "motivo": "No aplica por Cargo/Contrato"}

        es_proporcional_bono = bool(regla_activa.get("es_proporcional", 0))
        monto_completo = regla_activa.get("monto", 0)

        # ── 2. Determinar desde qué fecha aplica el empleado este mes ─────
        #    Si ingresó después del 1° del mes, solo se evalúan sus días.
        fecha_ingreso_emp = empleado.get("fecha_ingreso") or mes_inicio
        # Clamp: si ingresó antes del mes, tomamos el 1° del mes
        fecha_desde = max(fecha_ingreso_emp[:10], mes_inicio)

        # ── 3. Si no hay matrix_data → fallback simplificado ──────────────
        if not emp_matrix_data:
            logger.warning(
                f"[BonoService] Bono '{bono['nombre']}' sin projecciones "
                f"para empleado {empleado['id']} — usando fallback"
            )
            for a in asistencias:
                if a["fecha"] >= fecha_desde and a["estado"] in ("FALTA", "INASISTENCIA"):
                    j_dia = next(
                        (j for j in justificaciones
                         if j["fecha_inicio"] <= a["fecha"] <= j["fecha_fin"]), None
                    )
                    if not j_dia:
                        return {"aplica": True, "califica": False, "monto": 0,
                                "proporcional": False,
                                "motivo": f"Inasistencia injustificada el {a['fecha']}"}
            return {"aplica": True, "califica": True, "monto": monto_completo,
                    "proporcional": False, "motivo": "OK (Fallback sin proyecciones)"}

        # ── 4. Recorrer días del mes en la matriz ─────────────────────────
        #    Solo días dentro del rango [fecha_desde .. hoy] (o fin de mes)
        dias_laborables  = 0
        dias_asistidos   = 0
        dias_mes_completo = 0  # para calcular factor proporcional de ingreso
        motivo_perdida   = ""

        for fecha, dia_data in emp_matrix_data.items():
            if fecha == "info":
                continue

            estado        = (dia_data.get("estado") or "").upper()
            horas_teoricas = dia_data.get("horas_teoricas") or 0
            es_bolsa      = (dia_data.get("tipo_programacion") == "FLEXIBLE_BOLSA")

            # ¿Es un día laborable según el turno?
            j_dia = next(
                (j for j in justificaciones
                 if j["fecha_inicio"] <= fecha <= j["fecha_fin"]), None
            )

            info = emp_matrix_data.get('info', {})
            turno_dias = info.get('turno_dias', {})
            try:
                dia_semana = datetime.strptime(fecha, "%Y-%m-%d").weekday()
                dia_config = turno_dias.get(dia_semana) or turno_dias.get(str(dia_semana), {})
                es_libre_turno = bool(dia_config.get('es_libre', False))
            except Exception:
                es_libre_turno = False

            es_feriado = feriados_set is not None and fecha in feriados_set

            if es_bolsa:
                es_laborable_turno = (
                    estado not in ESTADOS_NO_LABORABLES
                    and (estado in ESTADOS_PRESENCIA
                         or estado in ("INASISTENCIA", "FALTA"))
                )
            else:
                es_laborable_turno = (
                    (horas_teoricas > 0) or
                    (j_dia is not None and not es_libre_turno and not es_feriado)
                )

            if not es_laborable_turno:
                continue

            # Contar días laborables del mes completo (para factor proporcional)
            if mes_inicio <= fecha <= mes_fin:
                dias_mes_completo += 1

            # Solo evaluar días desde el ingreso y hasta hoy
            if fecha < fecha_desde or fecha > hoy_str:
                continue

            dias_laborables += 1

            # ¿Justificación en este día?
            j_dia = next(
                (j for j in justificaciones
                 if j["fecha_inicio"] <= fecha <= j["fecha_fin"]), None
            )

            # ¿Asistió?
            es_presencia = estado in ESTADOS_PRESENCIA

            # ¿Justificación con goce válida para bono?
            es_justificado_valido = False
            if j_dia and j_dia.get("con_goce_sueldo") and j_dia.get("aplica_bono_pagador", 1):
                es_justificado_valido = True

            dia_ok = es_presencia or es_justificado_valido

            if dia_ok:
                dias_asistidos += 1
            else:
                # Día perdido: ¿es inasistencia o justificación sin goce?
                if j_dia:
                    label    = j_dia.get("tipo_nombre", estado)
                    pagador  = j_dia.get("pagador", "")
                    motivo_perdida += f"{fecha}: {label} (pagador: {pagador}). "
                else:
                    motivo_perdida += f"{fecha}: Inasistencia injustificada. "

        # ── 5. Calcular resultado ─────────────────────────────────────────
        if dias_laborables == 0:
            # El mes no ha comenzado aún o todos los días son libres hasta hoy
            # → proyectamos como "califica" con monto 0 (aún sin datos)
            return {
                "aplica": True, "califica": True, "monto": 0,
                "proporcional": False,
                "motivo": "Pendiente: sin días laborables registrados aún."
            }

        # Factor de proporcionalidad por ingreso a mitad de mes
        if dias_mes_completo > 0 and dias_mes_completo != dias_laborables:
            # Empleado no estuvo todo el mes → proporcional
            factor_ingreso = dias_laborables / dias_mes_completo
        else:
            factor_ingreso = 1.0

        es_ingreso_parcial = factor_ingreso < 1.0

        # ── 5a. BONOS DE MUERTE SÚBITA (COMPROMISO, OP. LINEA, CLORO…) ──
        if not es_proporcional_bono:
            if dias_asistidos < dias_laborables:
                return {
                    "aplica": True, "califica": False, "monto": 0,
                    "proporcional": False,
                    "motivo": motivo_perdida.strip(),
                }
            # 100% de asistencia → otorgar (proporcional si ingresó tarde)
            monto_final = round(monto_completo * factor_ingreso)
            return {
                "aplica": True, "califica": True,
                "monto": monto_final,
                "monto_completo": monto_completo,
                "proporcional": es_ingreso_parcial,
                "factor": round(factor_ingreso, 4),
                "dias_laborables": dias_laborables,
                "dias_mes_completo": dias_mes_completo,
                "motivo": (
                    f"Proporcional {dias_laborables}/{dias_mes_completo} días "
                    f"(ingreso {empleado.get('fecha_ingreso', '?')[:10]})"
                    if es_ingreso_parcial
                    else f"Asistencia completa {dias_asistidos}/{dias_laborables}"
                ),
            }

        # ── 5b. BONOS PROPORCIONALES (TRANSPORTE) ─────────────────────────
        #    Siempre se paga en proporción a días asistidos / días laborables asignados
        factor_asistencia = dias_asistidos / dias_laborables if dias_laborables else 0
        # Combinar factor de asistencia con factor de ingreso parcial
        factor_total = factor_asistencia * factor_ingreso
        monto_final  = round(monto_completo * factor_total)

        return {
            "aplica": True, "califica": True,
            "monto": monto_final,
            "monto_completo": monto_completo,
            "proporcional": True,
            "factor": round(factor_total, 4),
            "dias_asistidos": dias_asistidos,
            "dias_laborables": dias_laborables,
            "dias_mes_completo": dias_mes_completo,
            "motivo": (
                f"Transporte proporcional: {dias_asistidos}/{dias_laborables} días "
                f"asistidos × factor ingreso {factor_ingreso:.2f} "
                f"= ${monto_final:,.0f}"
            ),
        }
