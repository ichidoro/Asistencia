from backend.core.database import Database
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from loguru import logger

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
              AND he.minutos_bruto >= 1.0
            {filtro_area}
            ORDER BY e.apellido_paterno, he.fecha
        """
        he_pendientes = await self.db.fetch_all(
            query_he, tuple([fecha_inicio, fecha_fin] + params_area)
        )

        # ── HARD STOP 2: Anomalías sin corregir ───────────────────────────────
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
              AND a.estado = 'ANOMALIA'
              AND NOT EXISTS (
                  SELECT 1 FROM jornadas_especiales je
                  WHERE je.empleado_id = a.empleado_id
                    AND je.fecha = a.fecha
                    AND je.estado = 'EXTRA'
                    AND je.hora_entrada IS NOT NULL
                    AND je.hora_salida IS NOT NULL
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
              AND je.estado != 'RECHAZADA'
              AND a.estado NOT IN ('JORNADA_ESPECIAL', 'EXTRA')
            {filtro_area}
        """
        row_cob = await self.db.fetch_one(q_coberturas, tuple([fecha_inicio, fecha_fin] + params_area))
        if row_cob and row_cob['count_coberturas']:
            resumen['jornadas_especiales'] = (resumen.get('jornadas_especiales') or 0) + row_cob['count_coberturas']

        # ── CÁLCULO OFICIAL DE HABERES, DÉBITOS Y BALANCES (100% IDÉNTICO AL EXCEL) ──
        f_ini = date.fromisoformat(fecha_inicio)
        f_fin = date.fromisoformat(fecha_fin)
        rango_dias = [(f_ini + timedelta(days=i)) for i in range((f_fin - f_ini).days + 1)]

        matrix_data = await self.asistencia_service.get_matrix_data_with_projections(
            f_ini.month, f_ini.year, area=area, fecha_inicio_override=fecha_inicio, fecha_fin_override=fecha_fin
        )
        empleados_matriz = matrix_data.get("empleados", [])
        emp_matrix = matrix_data.get("matrix", {})

        total_he_fijos_min = 0.0
        total_he_fijos_count = 0
        total_exceso_bolsa_min = 0.0

        total_deuda_fijos_min = 0.0
        total_deuda_atrasos_min = 0.0
        total_deuda_colacion_min = 0.0
        total_deuda_salidas_min = 0.0
        total_deuda_permisos_min = 0.0
        total_deficit_bolsa_min = 0.0

        for emp in empleados_matriz:
            emp_id = emp["id"]
            es_bolsa = emp.get("tipo_programacion") in ("BOLSA_FLEXIBLE", "FLEXIBLE_BOLSA")
            dias_dict = emp_matrix.get(str(emp_id)) or emp_matrix.get(emp_id) or {}

            meta_min = emp.get("meta_mensual_minutos") or (40 * 60)
            if emp.get("meta_ajustada_minutos_descuento"):
                meta_min = max(0, meta_min - emp.get("meta_ajustada_minutos_descuento"))

            acum_bolsa = 0
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
                else:
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
                        raw_per = float(di.get("minutos_permiso_personal_deuda") or 0.0)
                        condona_atr = cond_tipo in (2, 3, 5)
                        raw_atr = 0.0 if condona_atr else float(di.get("minutos_atraso") or 0.0)
                        condona_sad = cond_tipo in (1, 3, 5)
                        raw_sad = 0.0 if condona_sad else float(di.get("minutos_salida_adelantada") or 0.0)

                        if cond_tipo == 5:
                            pass
                        else:
                            raw_total = raw_col + raw_per + raw_atr + raw_sad
                            base_deuda = float(di.get("minutos_deuda") or 0.0)
                            if raw_total > 0:
                                eff_deuda = min(base_deuda if base_deuda > 0 else raw_total, raw_total)
                                total_deuda_fijos_min += eff_deuda
                                if eff_deuda >= raw_total:
                                    total_deuda_colacion_min += raw_col
                                    total_deuda_permisos_min += raw_per
                                    total_deuda_atrasos_min += raw_atr
                                    total_deuda_salidas_min += raw_sad
                                else:
                                    factor = eff_deuda / raw_total
                                    total_deuda_colacion_min += raw_col * factor
                                    total_deuda_permisos_min += raw_per * factor
                                    total_deuda_atrasos_min += raw_atr * factor
                                    total_deuda_salidas_min += raw_sad * factor

            if es_bolsa:
                if acum_bolsa > meta_min:
                    total_exceso_bolsa_min += (acum_bolsa - meta_min)
                elif acum_bolsa < meta_min:
                    total_deficit_bolsa_min += (meta_min - acum_bolsa)

        # Haberes (recargo 50% Art. 32 CdT)
        he_fijos_hrs = round(total_he_fijos_min / 60.0, 2)
        he_bolsa_hrs = round(total_exceso_bolsa_min / 60.0, 2)
        he_total_hrs = round(he_fijos_hrs + he_bolsa_hrs, 2)

        # Débitos (tiempo no trabajado 100%)
        deuda_fijos_hrs = round(total_deuda_fijos_min / 60.0, 2)
        deficit_bolsa_hrs = round(total_deficit_bolsa_min / 60.0, 2)
        deuda_total_hrs = round(deuda_fijos_hrs + deficit_bolsa_hrs, 2)

        # Balance Operativo Neto (coincide al 100% con la columna Saldo Neto de Excel)
        balance_operativo_hrs = round(he_total_hrs - deuda_total_hrs, 2)

        resumen['total_empleados'] = len(empleados_matriz)
        resumen['he_aprobadas_fijos_horas'] = he_fijos_hrs
        resumen['he_aprobadas_fijos_count'] = total_he_fijos_count
        resumen['he_exceso_bolsa_horas'] = he_bolsa_hrs
        resumen['he_total_haberes_horas'] = he_total_hrs

        resumen['deuda_fijos_horas'] = deuda_fijos_hrs
        resumen['deuda_atrasos_horas'] = round(total_deuda_atrasos_min / 60.0, 2)
        resumen['deuda_colacion_horas'] = round(total_deuda_colacion_min / 60.0, 2)
        resumen['deuda_salidas_horas'] = round(total_deuda_salidas_min / 60.0, 2)
        resumen['deuda_permisos_horas'] = round(total_deuda_permisos_min / 60.0, 2)
        resumen['deficit_bolsa_horas'] = deficit_bolsa_hrs
        resumen['deuda_total_debitos_horas'] = deuda_total_hrs

        resumen['balance_operativo_horas'] = balance_operativo_hrs

        # Compatibilidad hacia atrás
        resumen['he_aprobadas_horas'] = he_total_hrs
        resumen['he_aprobadas_count'] = total_he_fijos_count
        resumen['deuda_neta_horas'] = deuda_total_hrs

        # Feriados del periodo
        query_feriados = """
            SELECT fecha, descripcion FROM feriados
            WHERE fecha BETWEEN ? AND ?
            ORDER BY fecha
        """
        feriados_periodo = await self.db.fetch_all(query_feriados, (fecha_inicio, fecha_fin))

        # Determinar si puede cerrar
        puede_cerrar = (
            len(he_pendientes) == 0
            and len(anomalias) == 0
            and len(en_curso) == 0
        )

        return {
            "puede_cerrar": puede_cerrar,
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

