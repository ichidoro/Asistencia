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
        bonos_activos = [b for b in bonos if b.get("activo")]

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
        Nueva lógica:
          • El empleado PARTE con el bono adjudicado.
          • Solo lo PIERDE por:
              1. Inasistencia injustificada.
              2. Justificación sin goce de sueldo (o pagador externo).
          • Ingreso o salida a mitad del período → monto proporcional a sus días de turno en el período.
          • TRANSPORTE (es_proporcional=1) → siempre proporcional, nunca pérdida total.
        """

        def _match_cargo(emp_cargo: str, req_val: str) -> bool:
            if not req_val or str(req_val).strip().upper() in ("NONE", "NULL", ""):
                return True
            cargo_emp  = (emp_cargo or "").strip().upper()
            cargos_req = [c.strip().upper() for c in str(req_val).split(",")]
            return cargo_emp in cargos_req

        # ── 0. Exclusión de empleados sin asistencia (Art 22) ──────────────
        if empleado.get("excluido_asistencia"):
            return {"aplica": False, "califica": False, "monto": 0,
                    "motivo": "Excluido de asistencia (Art 22)"}

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

        # ── 2. Días del período que le corresponden: desde su ingreso y hasta su salida ─────
        fecha_desde = max((empleado.get("fecha_ingreso") or periodo_inicio)[:10], periodo_inicio)
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
                    if not j_dia:
                        return {"aplica": True, "califica": False, "monto": 0,
                                "proporcional": False,
                                "motivo": f"Inasistencia injustificada el {a['fecha']}"}
            return {"aplica": True, "califica": True, "monto": monto_completo,
                    "proporcional": False, "motivo": "OK (Fallback sin proyecciones)"}

        # ── 4. Recorrer los días del período en la matriz ─────────────────
        #    La matriz puede traer días fuera del período: no cuentan.
        dias_laborables  = 0   # días de turno ya transcurridos (hasta hoy) que le corresponden: se revisan
        dias_asistidos   = 0
        dias_asignados   = 0   # días de turno del período que le corresponden (desde su ingreso, hasta su salida)
        dias_periodo     = 0   # días de turno de todo el período (para el proporcional por ingreso o salida)
        motivo_perdida   = ""

        for fecha, dia_data in emp_matrix_data.items():
            if fecha == "info" or not (periodo_inicio <= fecha <= periodo_fin):
                continue

            info = emp_matrix_data.get('info', {})
            estado        = (dia_data.get("estado") or "").upper()
            horas_teoricas = dia_data.get("horas_teoricas") or 0
            es_bolsa      = (info.get("tipo_programacion") == "BOLSA_FLEXIBLE")
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
                es_laborable_turno = (
                    estado not in ESTADOS_NO_LABORABLES
                    and (estado in ESTADOS_PRESENCIA
                         or estado in ("INASISTENCIA", "FALTA"))
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
            dias_asignados += 1

            # Solo se revisan los días que ya pasaron
            if fecha > hoy_str:
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
                "dias_asignados": dias_asignados,
                "dias_periodo": dias_periodo,
                "motivo": (
                    f"Proporcional {dias_asignados}/{dias_periodo} días de turno del período "
                    f"(ingreso {(empleado.get('fecha_ingreso') or '?')[:10]}"
                    f"{', salida ' + salida[:10] if salida else ''})"
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
            "dias_asignados": dias_asignados,
            "dias_periodo": dias_periodo,
            "motivo": (
                f"Transporte proporcional: {dias_asistidos}/{dias_laborables} días "
                f"asistidos × factor ingreso o salida {factor_ingreso:.2f} "
                f"= ${monto_final:,.0f}"
            ),
        }
