from backend.core.database import Database
from backend.services.bolsa_prorrateo import aplicar_prorrateo, fecha_en_vigencia
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from loguru import logger


def bolsa_es_definitiva(fecha_fin: str, tramo_fin, hoy: str) -> bool:
    """¿El déficit de la Bolsa Flexible ya es real para este rango?

    La meta de la Bolsa es mensual (por tramo RRHH): mientras el tramo no
    termine, lo que falta para la meta NO es deuda, es avance. El déficit
    solo se vuelve definitivo cuando el rango evaluado llega al final de su
    tramo y esa fecha ya pasó. `tramo_fin` es el fin del tramo RRHH que
    contiene a `fecha_fin` (None si el rango no cae en ningún tramo: un
    rango histórico fuera de tramos se evalúa como definitivo).
    """
    if fecha_fin >= hoy:
        return False
    if tramo_fin and str(tramo_fin)[:10] > fecha_fin:
        return False
    return True


class CierreService:
    def __init__(self, db: Database, asistencia_service=None):
        self.db = db
        if asistencia_service is None:
            from backend.repositories.asistencia import AsistenciaRepository
            from backend.services.asistencia_service import AsistenciaService
            repo = AsistenciaRepository(self.db)
            self.asistencia_service = AsistenciaService(repo)
        else:
            self.asistencia_service = asistencia_service

    async def calcular_haberes_debitos(self, fecha_inicio: str, fecha_fin: str, area=None):
        """Haberes, débitos, compensaciones, bolsa y espera del rango.

        Una sola lógica (idéntica al Excel) compartida por la previsualización
        del cierre y por el acta de un período ya sellado: lo que se mira para
        sellar es lo mismo que queda escrito en el acta.
        """
        salida: Dict[str, Any] = {}
        f_ini = date.fromisoformat(fecha_inicio)
        f_fin = date.fromisoformat(fecha_fin)
        rango_dias = [(f_ini + timedelta(days=i)) for i in range((f_fin - f_ini).days + 1)]

        # ¿La meta de la Bolsa ya es exigible? Solo cuando el rango llega al final
        # de su tramo RRHH y esa fecha ya pasó; antes se informa como AVANCE.
        from backend.services.quantum_matrix_engine import _get_now_local
        hoy_str = _get_now_local().strftime("%Y-%m-%d")
        tramo_row = await self.db.fetch_one(
            "SELECT fecha_fin FROM periodos_rrhh WHERE fecha_inicio <= ? AND fecha_fin >= ? ORDER BY fecha_inicio DESC LIMIT 1",
            (fecha_fin, fecha_fin)
        )
        tramo_fin_str = str(tramo_row["fecha_fin"])[:10] if tramo_row else None
        bolsa_definitiva = bolsa_es_definitiva(fecha_fin, tramo_fin_str, hoy_str)
        bolsa_dias_restantes = 0
        if tramo_fin_str and tramo_fin_str > fecha_fin:
            bolsa_dias_restantes = (date.fromisoformat(tramo_fin_str) - f_fin).days
        elif fecha_fin >= hoy_str:
            bolsa_dias_restantes = (f_fin - date.fromisoformat(hoy_str)).days + 1

        matrix_data = await self.asistencia_service.get_matrix_data_with_projections(
            f_ini.month, f_ini.year, area=area, fecha_inicio_override=fecha_inicio, fecha_fin_override=fecha_fin
        )
        empleados_matriz = matrix_data.get("empleados", [])
        emp_matrix = matrix_data.get("matrix", {})
        feriados = matrix_data.get("feriados", [])
        feriados_set = {f['fecha'] for f in feriados}

        total_he_fijos_min = 0.0
        total_he_fijos_count = 0
        total_exceso_bolsa_min = 0.0
        total_espera_min = 0.0
        total_exceso_espera_min = 0.0

        total_deuda_fijos_min = 0.0
        total_deuda_atrasos_min = 0.0
        total_deuda_colacion_min = 0.0
        total_deuda_salidas_min = 0.0
        total_deuda_permisos_min = 0.0
        # Libro mayor de minutos (política del tramo y tolerancia): lo que el cuadre a cero perdonó y lo que la
        # tolerancia dejó pasar ya no es deuda; se informa aparte y se descuenta de los débitos (25-10-2026).
        total_perdon_cuadre_min = 0.0
        total_tolerado_min = 0.0
        total_deuda_pendiente_min = 0.0
        total_he_a_pagar_min = 0.0
        total_he_no_pagadas_min = 0.0
        total_he_por_decidir_min = 0.0
        total_deficit_bolsa_min = 0.0
        total_compensado_min = 0.0
        total_meta_bolsa_min = 0.0
        total_acum_bolsa_min = 0.0
        bolsa_personas = 0

        for emp in empleados_matriz:
            emp_id = emp["id"]
            es_bolsa = emp.get("tipo_programacion") in ("BOLSA_FLEXIBLE", "FLEXIBLE_BOLSA")
            dias_dict = emp_matrix.get(str(emp_id)) or emp_matrix.get(emp_id) or {}

            if es_bolsa:
                meta_original = emp.get("meta_mensual_minutos")
                if not meta_original:
                    meta_original = round(float(emp.get("meta_horas_semanales") or 180.0) * 60)
                # Vigencia parcial (ingreso/egreso a mitad del tramo): meta proporcional
                # a los días corridos disponibles (calculada una sola vez en la matriz).
                pror_bolsa = emp.get("bolsa_prorrateo")
                meta_original = aplicar_prorrateo(meta_original, pror_bolsa)

                dias_programados = 0
                dias_justificados = 0
                estados_justificados = ['VACACIONES', 'LICENCIA', 'LIC_COMUN', 'LIC_MUTUAL', 'CUMPLEAÑOS', 'DUELO', 'PERMISO', 'NO NACIDO', 'DEFUNCION']

                for d in rango_dias:
                    f_str = f"{d.year}-{d.month:02d}-{d.day:02d}"
                    if not fecha_en_vigencia(f_str, pror_bolsa):
                        continue
                    is_fer = f_str in feriados_set
                    di_check = dias_dict.get(f_str, {})
                    day_db = d.weekday()
                    turno_dias = emp.get("turno_dias", {})
                    day_info = turno_dias.get(str(day_db), {}) or turno_dias.get(day_db, {})
                    is_structurally_libre = day_info.get("es_libre") == 1
                    is_descanso = is_fer or is_structurally_libre or (di_check.get("estado") == 'LIBRE')

                    if not is_descanso:
                        dias_programados += 1
                        di_estado = (di_check.get("estado") or "").upper()
                        di_nomen = (di_check.get("nomenclatura") or "").strip().upper()
                        is_justificado = (
                            any(ej in di_estado for ej in estados_justificados) or
                            (bool(di_nomen) and di_nomen not in ('DEOP', 'LIB', 'FER', 'OK', 'VIAJE'))
                        )
                        if is_justificado:
                            dias_justificados += 1

                if dias_programados > 0 and dias_justificados > 0:
                    valor_turno_min = meta_original / dias_programados
                    meta_min = round(meta_original - (valor_turno_min * dias_justificados))
                else:
                    meta_min = meta_original

                if emp.get("meta_ajustada_minutos_descuento") and dias_justificados == 0:
                    meta_min = max(0, meta_min - emp.get("meta_ajustada_minutos_descuento"))
            else:
                meta_min = emp.get("meta_mensual_minutos") or round(float(emp.get("meta_horas_semanales") or 45.0) * 60)
                if emp.get("meta_ajustada_minutos_descuento"):
                    meta_min = max(0, meta_min - emp.get("meta_ajustada_minutos_descuento"))

            acum_bolsa = 0
            acum_espera = 0
            viajes_sumados_ids = set()

            for d in rango_dias:
                f_str = f"{d.year}-{d.month:02d}-{d.day:02d}"
                di = dias_dict.get(f_str)
                if not di:
                    continue

                di_estado = di.get("estado") or ""

                vl_min = 0
                if es_bolsa and di.get("viaje_largo") and di["viaje_largo"].get("id") and di["viaje_largo"]["id"] not in viajes_sumados_ids:
                    viajes_sumados_ids.add(di["viaje_largo"]["id"])
                    ya_registrado = (float(di.get("horas_trabajadas") or 0.0) > 0)
                    if not ya_registrado:
                        vl_obj = di["viaje_largo"]
                        vl_hrs = float(vl_obj.get("horas_reconocidas_totales") or vl_obj.get("horas_manejo_efectivas") or 0.0)
                        vl_min = round(vl_hrs * 60)

                trab = round((di.get("horas_trabajadas") or 0.0) * 60) + vl_min
                ja = di.get("jornada_adicional") or {}
                es_ja_he = (ja.get("estado") == 'HORAS_EXTRAS')
                is_esp = di_estado in ['JORNADA_ESPECIAL', 'EXTRA', 'FERIADO Y JORNADA EXTRA', 'DÍA LIBRE Y JORNADA EXTRA'] or (not es_bolsa and float(di.get("horas_teoricas") or 0.0) == 0.0 and float(di.get("horas_trabajadas") or 0.0) > 0.0)

                if es_bolsa:
                    if not is_esp:
                        acum_bolsa += trab
                    if di.get("minutos_espera"):
                        acum_espera += float(di.get("minutos_espera") or 0.0)
                else:
                    # Compensaciones (HE usadas para cubrir una inasistencia): la grilla
                    # y el Excel las restan del saldo; el resumen del cierre hace lo mismo.
                    total_compensado_min += float(di.get("minutos_compensados_he") or 0.0)
                    if not is_esp:
                        if di.get("estado_he") == 'APROBADO':
                            m_aut = float(di.get("minutos_extra_autorizados") or 0.0)
                            if m_aut > 0:
                                total_he_fijos_min += m_aut
                                total_he_fijos_count += 1
                    elif es_ja_he:
                        min_ja_he = float(ja.get("minutos_autorizados") or ja.get("minutos_trabajados") or 0.0)
                        if min_ja_he > 0:
                            total_he_fijos_min += min_ja_he
                            total_he_fijos_count += 1

                    if not is_esp:
                        cond_tipo = int(di.get("deuda_condonada") or 0)
                        raw_col = float(di.get("minutos_exceso_colacion") or 0.0)
                        # Permiso del día: el tomado entre marcas o el ingresado por horas; cuando están los dos son el
                        # mismo permiso (la justificación se ingresa sobre la pausa marcada): el mayor, nunca la suma.
                        raw_per = max(float(di.get("minutos_permisos_detectados") or 0.0),
                                      float(di.get("minutos_permiso_personal_deuda") or 0.0))
                        condona_atr = cond_tipo in (2, 3, 5)
                        raw_atr = 0.0 if condona_atr else float(di.get("minutos_atraso") or 0.0)
                        condona_sad = cond_tipo in (1, 3, 5)
                        raw_sad = 0.0 if condona_sad else float(di.get("minutos_salida_adelantada") or 0.0)

                        if cond_tipo == 5:
                            pass
                        else:
                            base_deuda = float(di.get("minutos_deuda") or 0.0)
                            if base_deuda > 0:
                                total_deuda_fijos_min += base_deuda
                                raw_total = raw_col + raw_per + raw_atr + raw_sad
                                if raw_total > 0:
                                    if base_deuda >= raw_total:
                                        total_deuda_colacion_min += raw_col
                                        total_deuda_permisos_min += raw_per
                                        total_deuda_atrasos_min += raw_atr
                                        total_deuda_salidas_min += raw_sad
                                    else:
                                        # La persona compensó parte el mismo día: se reparte la deuda neta entre sus
                                        # causas, también el permiso, para que la suma no pase de la deuda del día.
                                        factor = base_deuda / raw_total
                                        total_deuda_colacion_min += raw_col * factor
                                        total_deuda_permisos_min += raw_per * factor
                                        total_deuda_atrasos_min += raw_atr * factor
                                        total_deuda_salidas_min += raw_sad * factor

            if not es_bolsa:
                _lib = ((dias_dict.get('info') or {}) if isinstance(dias_dict, dict) else {}).get('libro') or {}
                total_perdon_cuadre_min += float(_lib.get('perdon_cuadre') or 0.0)
                total_tolerado_min += float(_lib.get('tolerado') or 0.0)
                total_deuda_pendiente_min += float(_lib.get('pendiente') or 0.0)
                total_he_a_pagar_min += float(_lib.get('he_a_pagar') or 0.0)
                total_he_no_pagadas_min += float(_lib.get('he_no_pagadas') or 0.0)
                total_he_por_decidir_min += float(_lib.get('he_por_decidir') or 0.0)

            if es_bolsa:
                total_meta_bolsa_min += meta_min
                total_acum_bolsa_min += acum_bolsa
                bolsa_personas += 1
                if acum_bolsa > meta_min:
                    # El exceso ya es real aunque el tramo siga: solo puede crecer
                    total_exceso_bolsa_min += (acum_bolsa - meta_min)
                elif acum_bolsa < meta_min and bolsa_definitiva:
                    # Lo que falta para la meta recién es deuda cuando el tramo terminó
                    total_deficit_bolsa_min += (meta_min - acum_bolsa)

                # 88h Espera (Art. 25 bis); con vigencia parcial se prorratea igual que la meta
                meta_espera_min = round(float(emp.get("meta_horas_espera") if emp.get("meta_horas_espera") is not None else 88.0) * 60)
                meta_espera_min = aplicar_prorrateo(meta_espera_min, emp.get("bolsa_prorrateo"))
                total_espera_min += acum_espera
                if acum_espera > meta_espera_min:
                    total_exceso_espera_min += (acum_espera - meta_espera_min)

        # Haberes (recargo 50% Art. 32 CdT)
        he_fijos_hrs = round(total_he_fijos_min / 60.0, 2)
        he_bolsa_hrs = round(total_exceso_bolsa_min / 60.0, 2)
        he_espera_hrs = round(total_exceso_espera_min / 60.0, 2)
        he_total_hrs = round(he_fijos_hrs + he_bolsa_hrs + he_espera_hrs, 2)

        # Débitos (tiempo no trabajado 100%). Lo perdonado por el cuadre a cero y lo tolerado se descuenta:
        # el libro mayor ya no lo cuenta como deuda y el saldo de la grilla y del Excel tampoco.
        total_deuda_fijos_min = max(0.0, total_deuda_fijos_min - total_perdon_cuadre_min - total_tolerado_min)
        deuda_fijos_hrs = round(total_deuda_fijos_min / 60.0, 2)
        deficit_bolsa_hrs = round(total_deficit_bolsa_min / 60.0, 2)
        deuda_total_hrs = round(deuda_fijos_hrs + deficit_bolsa_hrs, 2)

        # El desglose por categoría no siempre alcanza el total (deuda de jornadas
        # incompletas que no es atraso, colación, salida ni permiso): la diferencia
        # se informa como «otros» para que la cuenta siempre cierre a la vista.
        clasificada_min = (total_deuda_atrasos_min + total_deuda_colacion_min
                           + total_deuda_salidas_min + total_deuda_permisos_min)
        deuda_otros_hrs = round(max(0.0, total_deuda_fijos_min - clasificada_min) / 60.0, 2)

        # Compensaciones: HE ya usadas para cubrir inasistencias (no se pagan de nuevo)
        compensaciones_hrs = round(total_compensado_min / 60.0, 2)

        # Balance Operativo Neto (coincide con la columna Saldo Neto del Excel,
        # que también descuenta las compensaciones)
        balance_operativo_hrs = round(he_total_hrs - deuda_total_hrs - compensaciones_hrs, 2)

        salida['total_empleados'] = len(empleados_matriz)
        salida['he_aprobadas_fijos_horas'] = he_fijos_hrs
        salida['he_aprobadas_fijos_count'] = total_he_fijos_count
        salida['he_exceso_bolsa_horas'] = he_bolsa_hrs
        salida['he_exceso_espera_horas'] = he_espera_hrs
        salida['espera_total_horas'] = round(total_espera_min / 60.0, 2)
        salida['he_total_haberes_horas'] = he_total_hrs

        salida['deuda_fijos_horas'] = deuda_fijos_hrs
        salida['deuda_atrasos_horas'] = round(total_deuda_atrasos_min / 60.0, 2)
        salida['deuda_colacion_horas'] = round(total_deuda_colacion_min / 60.0, 2)
        salida['deuda_salidas_horas'] = round(total_deuda_salidas_min / 60.0, 2)
        salida['deuda_permisos_horas'] = round(total_deuda_permisos_min / 60.0, 2)
        salida['deuda_otros_horas'] = deuda_otros_hrs
        salida['deficit_bolsa_horas'] = deficit_bolsa_hrs
        salida['deuda_total_debitos_horas'] = deuda_total_hrs
        # Libro mayor del tramo (mismos números que la grilla, la ventana de cuadre y el Excel)
        salida['deuda_perdonada_cuadre_horas'] = round(total_perdon_cuadre_min / 60.0, 2)
        salida['deuda_tolerada_horas'] = round(total_tolerado_min / 60.0, 2)
        salida['deuda_pendiente_horas'] = round(total_deuda_pendiente_min / 60.0, 2)
        salida['he_a_pagar_horas'] = round(total_he_a_pagar_min / 60.0, 2)
        salida['he_no_pagadas_horas'] = round(total_he_no_pagadas_min / 60.0, 2)
        salida['he_por_decidir_horas'] = round(total_he_por_decidir_min / 60.0, 2)

        # Avance de la Bolsa: meta grupal (ya prorrateada por vigencias parciales),
        # acumulado y si el déficit ya es definitivo o el tramo sigue corriendo
        salida['bolsa_personas'] = bolsa_personas
        salida['bolsa_meta_total_horas'] = round(total_meta_bolsa_min / 60.0, 2)
        salida['bolsa_acumulado_horas'] = round(total_acum_bolsa_min / 60.0, 2)
        salida['bolsa_definitiva'] = bolsa_definitiva
        salida['bolsa_dias_restantes'] = bolsa_dias_restantes

        salida['compensaciones_horas'] = compensaciones_hrs
        salida['balance_operativo_horas'] = balance_operativo_hrs

        # Compatibilidad hacia atrás
        salida['he_aprobadas_horas'] = he_total_hrs
        salida['he_aprobadas_count'] = total_he_fijos_count
        salida['deuda_neta_horas'] = deuda_total_hrs
        return salida

    async def evaluar_cierre(self, fecha_inicio: str, fecha_fin: str, area: str):
        """
        Evaluación pre-cierre con 4 niveles de semáforo (tela de araña):
        1. HE PENDIENTES       → Hard Stop 1
        2. ANOMALÍAS           → Hard Stop 2
        3. EN_CURSO            → Hard Stop 3
        4. INASISTENCIAS       → Soft Stop (aceptar con checkbox)
        """
        # Validar que no exista solapamiento de periodos cerrados para esta área
        overlap_query = """
            SELECT id, fecha_inicio, fecha_fin FROM cierres_periodos 
            WHERE area = ? AND fecha_inicio <= ? AND fecha_fin >= ?
            LIMIT 1
        """
        solapamiento = await self.db.fetch_one(overlap_query, (area, fecha_fin, fecha_inicio))
        if solapamiento:
            raise ValueError(
                f"El período seleccionado ya se encuentra cerrado para el área '{area}' "
                f"({solapamiento['fecha_inicio']} al {solapamiento['fecha_fin']})."
            )

        params_area = []
        filtro_area = ""
        if area and area != 'Todas':
            filtro_area = " AND ar.nombre = ?"
            params_area = [area]

        # ── HARD STOP 1: Horas extras pendientes ──────────────────────────────
        query_he = f"""
            SELECT he.id, he.fecha, he.empleado_id,
                   e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS nombre_completo,
                   he.minutos_bruto, he.minutos_autorizados, he.origen,
                   asi.hora_entrada_real, asi.hora_salida_real,
                   asi.hora_entrada_teorica, asi.hora_salida_teorica,
                   asi.minutos_colacion_real, asi.minutos_colacion_auto, asi.minutos_colacion,
                   asi.observaciones
            FROM horas_extras he INDEXED BY idx_he_fecha
            JOIN empleados e ON he.empleado_id = e.id
            LEFT JOIN asistencias asi ON he.empleado_id = asi.empleado_id AND he.fecha = asi.fecha
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.validado = 1
                AND he.fecha >= ha.fecha_desde
                AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR he.fecha <= ha.fecha_hasta)
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE he.fecha BETWEEN ? AND ?
              AND he.estado = 'PENDIENTE'
              AND he.minutos_bruto > 0
            {filtro_area}
            ORDER BY e.apellido_paterno, he.fecha
        """
        he_pendientes = await self.db.fetch_all(
            query_he, tuple([fecha_inicio, fecha_fin] + params_area)
        )

        # ── HARD STOP 2: Anomalías sin corregir y Días Pendientes ────────────
        # Excluye anomalías que tienen JE aprobada (EXTRA) con ambas marcas → no son bloqueantes
        query_anomalias = f"""
            SELECT a.id, a.empleado_id, a.fecha, a.hora_entrada_real, a.hora_salida_real,
                   e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS nombre_completo,
                   ar.nombre AS area
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.validado = 1
                AND a.fecha >= ha.fecha_desde
                AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR a.fecha <= ha.fecha_hasta)
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE a.fecha BETWEEN ? AND ?
              AND (
                  (a.estado = 'ANOMALIA' AND NOT EXISTS (
                      SELECT 1 FROM jornadas_especiales je
                      WHERE je.empleado_id = a.empleado_id
                        AND je.fecha = a.fecha
                        AND je.estado = 'EXTRA'
                        AND je.hora_entrada IS NOT NULL
                        AND je.hora_salida IS NOT NULL
                  ))
                  OR a.estado = 'PENDIENTE'
              )
            {filtro_area}
            ORDER BY e.apellido_paterno, a.fecha
        """
        anomalias = await self.db.fetch_all(
            query_anomalias, tuple([fecha_inicio, fecha_fin] + params_area)
        )

        # ── HARD STOP 3: Empleados EN_CURSO en el periodo ─────────────────────
        # Calcula hora estimada de salida para orientar al Jefe
        query_en_curso = f"""
            SELECT a.id, a.fecha, a.hora_entrada_real,
                   a.hora_salida_teorica,
                   e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS nombre_completo,
                   ar.nombre AS area
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.validado = 1
                AND a.fecha >= ha.fecha_desde
                AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR a.fecha <= ha.fecha_hasta)
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE a.fecha BETWEEN ? AND ?
              AND a.estado = 'EN_CURSO'
            {filtro_area}
            ORDER BY a.hora_salida_teorica ASC NULLS LAST
        """
        en_curso = await self.db.fetch_all(
            query_en_curso, tuple([fecha_inicio, fecha_fin] + params_area)
        )

        # Calcular hora estimada del último turno activo para mensaje orientador
        ultimo_fin_estimado = None
        if en_curso:
            salidas = [r['hora_salida_teorica'] for r in en_curso if r['hora_salida_teorica']]
            if salidas:
                ultimo_fin_estimado = max(salidas)

        # ── SOFT STOP: Inasistencias sin justificar ────────────────────────────
        # Solo INASISTENCIA, ya NO incluye ANOMALIA (separadas en Hard Stop 2)
        query_ina = f"""
            SELECT a.id, a.empleado_id, a.fecha,
                   e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS nombre_completo,
                   ar.nombre AS area
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.validado = 1
                AND a.fecha >= ha.fecha_desde
                AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR a.fecha <= ha.fecha_hasta)
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE a.fecha BETWEEN ? AND ?
              AND a.estado = 'INASISTENCIA'
            {filtro_area}
            ORDER BY e.apellido_paterno, a.fecha
        """
        inasistencias = await self.db.fetch_all(
            query_ina, tuple([fecha_inicio, fecha_fin] + params_area)
        )

        # ── Resumen ejecutivo siempre visible ─────────────────────────────────
        query_resumen = f"""
            SELECT
                COUNT(DISTINCT a.empleado_id)                                                      AS total_empleados,
                SUM(CASE WHEN a.estado = 'OK' THEN 1 ELSE 0 END)                                   AS dias_ok,
                SUM(CASE WHEN a.estado IN ('ATRASO','SALIDA_ADELANTADA','ATR_SAD') THEN 1 ELSE 0 END) AS dias_con_novedad,
                SUM(CASE WHEN a.estado = 'VACACIONES' THEN 1 ELSE 0 END)                           AS vacaciones,
                SUM(CASE WHEN a.estado LIKE 'LICENCIA%' THEN 1 ELSE 0 END)                         AS licencias,
                SUM(CASE WHEN a.estado = 'JORNADA_ESPECIAL' THEN 1 ELSE 0 END)                     AS jornadas_especiales,
                SUM(CASE WHEN a.estado = 'LIBRE' THEN 1 ELSE 0 END)                                AS dias_libres,
                SUM(CASE WHEN a.estado = 'FERIADO' THEN 1 ELSE 0 END)                              AS feriados_caidos,
                SUM(CASE WHEN a.estado = 'INASISTENCIA' THEN 1 ELSE 0 END)                         AS inasistencias,
                SUM(CASE WHEN a.estado = 'ANOMALIA' THEN 1 ELSE 0 END)                             AS anomalias
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.validado = 1
                AND a.fecha >= ha.fecha_desde
                AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR a.fecha <= ha.fecha_hasta)
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE a.fecha BETWEEN ? AND ?
            {filtro_area}
        """
        resumen_row = await self.db.fetch_one(
            query_resumen, tuple([fecha_inicio, fecha_fin] + params_area)
        )
        resumen = dict(resumen_row) if resumen_row else {}

        # Consolidar coberturas de turno (+2) que operan en paralelo al turno base
        q_coberturas = f"""
            SELECT COUNT(je.id) as count_coberturas
            FROM jornadas_especiales je
            JOIN empleados e ON je.empleado_id = e.id
            JOIN asistencias a ON je.empleado_id = a.empleado_id AND je.fecha = a.fecha
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.validado = 1
                AND a.fecha >= ha.fecha_desde
                AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR a.fecha <= ha.fecha_hasta)
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE je.fecha BETWEEN ? AND ?
              AND je.origen = 'COBERTURA_TURNO'
              AND je.estado NOT IN ('RECHAZADA', 'COMPENSATORIA')
              AND a.estado NOT IN ('JORNADA_ESPECIAL', 'EXTRA')
            {filtro_area}
        """
        row_cob = await self.db.fetch_one(q_coberturas, tuple([fecha_inicio, fecha_fin] + params_area))
        if row_cob and row_cob['count_coberturas']:
            resumen['jornadas_especiales'] = (resumen.get('jornadas_especiales') or 0) + row_cob['count_coberturas']

        # ── CÁLCULO OFICIAL DE HABERES, DÉBITOS Y BALANCES ──
        # (una sola lógica, compartida con el acta: calcular_haberes_debitos)
        resumen.update(await self.calcular_haberes_debitos(fecha_inicio, fecha_fin, area))

        # Feriados del periodo
        query_feriados = """
            SELECT fecha, descripcion FROM feriados
            WHERE fecha BETWEEN ? AND ?
            ORDER BY fecha
        """
        feriados_periodo = await self.db.fetch_all(query_feriados, (fecha_inicio, fecha_fin))

        # ── HARD STOP 4: Días por revisar (Reglas de marcaciones) ─────────────
        # Días del rango cuya regla los dejó en revisión y nadie corrigió ni
        # confirmó: el cierre se bloquea hasta resolverlos (decisión del dueño).
        try:
            from backend.repositories.reglas_marcas import ReglasMarcasRepository
            por_revisar = await ReglasMarcasRepository(self.db).pendientes_para_cierre(
                fecha_inicio, fecha_fin, area)
        except Exception as e_rev:
            logger.warning(f"Pre-evaluación: no se pudieron leer los días por revisar: {e_rev}")
            por_revisar = []

        # Determinar si puede cerrar
        puede_cerrar = (
            len(he_pendientes) == 0
            and len(anomalias) == 0
            and len(en_curso) == 0
            and len(por_revisar) == 0
        )

        return {
            "puede_cerrar": puede_cerrar,
            "dias_por_revisar": len(por_revisar),
            "detalle_por_revisar": por_revisar,
            # Hard Stops
            "he_pendientes": len(he_pendientes),
            "detalle_he": [dict(r) for r in he_pendientes],
            "anomalias": len(anomalias),
            "detalle_anomalias": [dict(r) for r in anomalias],
            "en_curso": len(en_curso),
            "detalle_en_curso": [dict(r) for r in en_curso],
            "ultimo_fin_estimado": ultimo_fin_estimado,
            # Soft Stop
            "inasistencias_injustificadas": len(inasistencias),
            "detalle_ina": [dict(r) for r in inasistencias],
            # Resumen ejecutivo
            "resumen": resumen,
            "feriados_periodo": [dict(r) for r in feriados_periodo],
        }

    async def ejecutar_cierre(self, fecha_inicio: str, fecha_fin: str, area: str, aceptar_inasistencias: bool, user: dict):
        evaluacion = await self.evaluar_cierre(fecha_inicio, fecha_fin, area)

        # Validar los 3 Hard Stops
        if evaluacion["he_pendientes"] > 0:
            raise ValueError(
                f"No se puede cerrar el periodo. Hay {evaluacion['he_pendientes']} "
                f"horas extras pendientes de validación."
            )
        if evaluacion["anomalias"] > 0:
            raise ValueError(
                f"No se puede cerrar el periodo. Hay {evaluacion['anomalias']} "
                f"anomalías sin corregir. Corrígelas en la grilla antes de cerrar."
            )
        if evaluacion["en_curso"] > 0:
            msg = (
                f"No se puede cerrar el periodo. Hay {evaluacion['en_curso']} "
                f"empleados con turnos activos (EN_CURSO)."
            )
            if evaluacion.get("ultimo_fin_estimado"):
                msg += f" El último turno activo termina aprox. a las {evaluacion['ultimo_fin_estimado']}."
            raise ValueError(msg)
        if evaluacion.get("dias_por_revisar", 0) > 0:
            raise ValueError(
                f"No se puede cerrar el periodo. Hay {evaluacion['dias_por_revisar']} días por revisar "
                f"(Reglas de marcaciones): corrija sus marcas o confírmelos en «Marcaciones del día» antes de cerrar."
            )

        # Validar Soft Stop
        if evaluacion["inasistencias_injustificadas"] > 0 and not aceptar_inasistencias:
            raise ValueError(
                f"Hay {evaluacion['inasistencias_injustificadas']} inasistencias sin justificar. "
                f"Debe aceptarlas explícitamente para continuar."
            )

        # Validar que no exista solapamiento de periodos cerrados para esta área
        overlap_query = """
            SELECT id, fecha_inicio, fecha_fin FROM cierres_periodos 
            WHERE area = ? AND fecha_inicio <= ? AND fecha_fin >= ?
            LIMIT 1
        """
        solapamiento = await self.db.fetch_one(overlap_query, (area, fecha_fin, fecha_inicio))
        if solapamiento:
            raise ValueError(
                f"El periodo seleccionado se solapa con un periodo ya cerrado para esta área "
                f"({solapamiento['fecha_inicio']} al {solapamiento['fecha_fin']})."
            )

        # Determinar tipo de cierre según rol
        tipo_cierre = "SUPER_ADMIN" if user.get("rol_global") == 1 else "JEFE_AREA"

        comentarios = (
            f"Cierre ejecutado por {user.get('username', 'sistema')} "
            f"[{tipo_cierre}] — "
            f"Inasistencias aceptadas: {'SI' if aceptar_inasistencias else 'N/A'}"
        )

        insert_query = """
            INSERT INTO cierres_periodos (fecha_inicio, fecha_fin, usuario_id, username, tipo_cierre, area, comentarios)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        await self.db.execute(insert_query, (
            fecha_inicio,
            fecha_fin,
            user.get("id"),
            user.get("username"),
            tipo_cierre,
            area,
            comentarios
        ))

        # Si hay un periodo en periodos_rrhh que coincide con el rango cerrado, marcarlo como 'cerrado'
        # Pero solo si todas las áreas activas están cerradas
        try:
            active_areas_res = await self.db.fetch_all(
                """
                SELECT DISTINCT ar.nombre FROM empleados e
                JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.validado = 1
                    AND (? >= ha.fecha_desde AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR ? <= ha.fecha_hasta))
                JOIN areas ar ON ha.area_id = ar.id
                JOIN asignacion_turnos at ON e.id = at.empleado_id
                    AND (? >= at.fecha_inicio AND (at.fecha_fin IS NULL OR at.fecha_fin = '' OR ? <= at.fecha_fin))
                WHERE e.activo = 1 AND (e.excluido_asistencia IS NULL OR e.excluido_asistencia = 0)
                """,
                (fecha_fin, fecha_inicio, fecha_fin, fecha_inicio)
            )
            active_areas = {r['nombre'] for r in active_areas_res if r['nombre']}

            closed_areas_res = await self.db.fetch_all(
                "SELECT DISTINCT area FROM cierres_periodos WHERE fecha_inicio = ? AND fecha_fin = ? AND area IS NOT NULL",
                (fecha_inicio, fecha_fin)
            )
            closed_areas = {r['area'] for r in closed_areas_res if r['area']}
            if area:
                closed_areas.add(area)

            should_close_global = active_areas.issubset(closed_areas)

            if should_close_global:
                # 1. Obtener la info del periodo antes de cerrarlo para ver si era el activo
                periodo = await self.db.fetch_one(
                    "SELECT activo FROM periodos_rrhh WHERE fecha_inicio = ? AND fecha_fin = ?",
                    (fecha_inicio, fecha_fin)
                )
                
                # 2. Marcar como cerrado
                await self.db.execute(
                    "UPDATE periodos_rrhh SET estado = 'cerrado' WHERE fecha_inicio = ? AND fecha_fin = ?",
                    (fecha_inicio, fecha_fin)
                )
                logger.info(f"✨ periodos_rrhh actualizado a 'cerrado' para el rango {fecha_inicio} a {fecha_fin} (CierreService)")
                
                # 3. Si era el periodo activo/vigente, hacer la transición
                if periodo and (periodo["activo"] == 1 or periodo["activo"] is True):
                    await self.db.execute(
                        "UPDATE periodos_rrhh SET activo = 0 WHERE fecha_inicio = ? AND fecha_fin = ?",
                        (fecha_inicio, fecha_fin)
                    )
                    logger.info(f"✨ Periodo {fecha_inicio} al {fecha_fin} desmarcado como Vigente.")
                    
                    # Buscar el siguiente periodo abierto
                    next_periodo = await self.db.fetch_one(
                        "SELECT id, mes_cierre FROM periodos_rrhh WHERE estado = 'abierto' ORDER BY fecha_inicio ASC LIMIT 1"
                    )
                    if next_periodo:
                        await self.db.execute(
                            "UPDATE periodos_rrhh SET activo = 1 WHERE id = ?",
                            (next_periodo["id"],)
                        )
                        logger.info(f"✨ Siguiente periodo promovido a Vigente: {next_periodo['mes_cierre']} (ID: {next_periodo['id']})")
                    else:
                        logger.info("ℹ️ No hay más periodos abiertos para promover como Vigente.")
            else:
                logger.info(
                    f"ℹ️ Cierre de area '{area}' guardado, pero periodos_rrhh permanece 'abierto' "
                    f"porque quedan areas activas por cerrar. "
                    f"Activas: {active_areas} | Cerradas: {closed_areas}"
                )
        except Exception as e_close_rrhh:
            logger.warning(f"⚠️ No se pudo actualizar el estado/vigencia en periodos_rrhh: {e_close_rrhh}")

        # Generar Excel oficial del periodo y área y enviar por email a RRHH
        try:
            from backend.repositories.asistencia import AsistenciaRepository
            from backend.services.asistencia_service import AsistenciaService
            from backend.services.report_service import ReportService
            from backend.repositories.configuracion import ConfiguracionRepository
            from backend.services.configuracion_service import ConfiguracionService
            from backend.services.notification_service import NotificationService

            logger.info(f"📬 Generando reporte Excel de cierre para área '{area}' en el rango {fecha_inicio} a {fecha_fin}...")
            asistencia_repo = AsistenciaRepository(self.db)
            asistencia_service = AsistenciaService(asistencia_repo)
            report_service = ReportService(asistencia_service)
            
            excel_file = await report_service.generate_excel_report(fecha_inicio, fecha_fin, area)
            if excel_file:
                excel_bytes = excel_file.getvalue()
                
                config_repo = ConfiguracionRepository(self.db)
                config_service = ConfiguracionService(config_repo)
                recipients = await config_service.get_destinatarios_cierre(area)
                
                if recipients:
                    logger.info(f"📧 Enviando email de notificación de cierre a {recipients}...")
                    notification_service = NotificationService()
                    await notification_service.send_cierre_email(
                        area=area,
                        fecha_inicio=fecha_inicio,
                        fecha_fin=fecha_fin,
                        user_name=user.get("username", "sistema"),
                        tipo_cierre=tipo_cierre,
                        resumen=evaluacion.get("resumen", {}),
                        excel_content=excel_bytes,
                        recipients=recipients
                    )
                else:
                    logger.warning(f"⚠️ No hay destinatarios configurados para recibir la notificación de cierre de área '{area}'.")
            else:
                logger.error("❌ No se pudo generar el reporte Excel de cierre (generate_excel_report retornó None).")
        except Exception as e_email:
            logger.error(f"❌ Error al generar o enviar el correo de cierre con Excel adjunto: {e_email}")

        return {"success": True, "message": "Periodo cerrado exitosamente.", "tipo_cierre": tipo_cierre}

