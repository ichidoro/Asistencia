from backend.core.database import Database
from datetime import datetime
from loguru import logger

class CierreService:
    def __init__(self, db: Database):
        self.db = db

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

        # 1. Obtener horas extras aprobadas agrupadas por empleado
        query_he_emp = f"""
            SELECT he.empleado_id, 
                   SUM(he.minutos_autorizados) AS he_minutos, 
                   COUNT(*) AS he_count
            FROM horas_extras he INDEXED BY idx_he_fecha
            JOIN empleados e ON he.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.validado = 1
                AND he.fecha >= ha.fecha_desde
                AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR he.fecha <= ha.fecha_hasta)
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE he.fecha BETWEEN ? AND ?
              AND he.estado = 'APROBADO'
              {filtro_area}
            GROUP BY he.empleado_id
        """

        # 2. Obtener minutos de deuda total y componentes acumulados por empleado
        query_deuda_emp = f"""
            SELECT a.empleado_id, 
                   SUM(CASE WHEN COALESCE(a.deuda_condonada, 0) > 0 THEN 0 ELSE a.minutos_deuda END) AS deuda_minutos,
                   SUM(CASE WHEN COALESCE(a.deuda_condonada, 0) > 0 THEN 0 ELSE a.minutos_atraso END) AS minutos_atraso,
                   SUM(a.minutos_exceso_colacion) AS minutos_exceso_colacion,
                   SUM(CASE WHEN COALESCE(a.deuda_condonada, 0) > 0 THEN 0 ELSE a.minutos_salida_adelantada END) AS minutos_salida_adelantada,
                   SUM(a.minutos_permiso_personal_deuda) AS minutos_permiso_personal_deuda
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.validado = 1
                AND a.fecha >= ha.fecha_desde
                AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR a.fecha <= ha.fecha_hasta)
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE a.fecha BETWEEN ? AND ?
              {filtro_area}
            GROUP BY a.empleado_id
        """

        # 3. Obtener compensaciones realizadas por empleado
        query_comp_emp = f"""
            SELECT comp.empleado_id, 
                   SUM(comp.minutos) AS total_comp
            FROM compensaciones_he_inasistencia comp
            JOIN empleados e ON comp.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.validado = 1
                AND comp.fecha_inasistencia >= ha.fecha_desde
                AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR comp.fecha_inasistencia <= ha.fecha_hasta)
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE comp.fecha_inasistencia BETWEEN ? AND ?
              {filtro_area}
            GROUP BY comp.empleado_id
        """

        he_emp_rows = await self.db.fetch_all(query_he_emp, tuple([fecha_inicio, fecha_fin] + params_area))
        deuda_emp_rows = await self.db.fetch_all(query_deuda_emp, tuple([fecha_inicio, fecha_fin] + params_area))
        comp_emp_rows = await self.db.fetch_all(query_comp_emp, tuple([fecha_inicio, fecha_fin] + params_area))

        he_map = {r['empleado_id']: (r['he_minutos'] or 0.0, r['he_count'] or 0) for r in he_emp_rows}
        deuda_map = {
            r['empleado_id']: {
                'total': r['deuda_minutos'] or 0.0,
                'atraso': r['minutos_atraso'] or 0.0,
                'colacion': r['minutos_exceso_colacion'] or 0.0,
                'salida': r['minutos_salida_adelantada'] or 0.0,
                'permiso': r['minutos_permiso_personal_deuda'] or 0.0
            } for r in deuda_emp_rows
        }
        comp_map = {r['empleado_id']: r['total_comp'] or 0.0 for r in comp_emp_rows}

        todos_empleados = set(he_map.keys()) | set(deuda_map.keys()) | set(comp_map.keys())

        total_neto_he = 0.0
        total_he_count = 0
        total_deuda_neta = 0.0

        total_deuda_atrasos = 0.0
        total_deuda_colacion = 0.0
        total_deuda_salidas = 0.0
        total_deuda_permisos = 0.0

        for emp_id in todos_empleados:
            emp_he, emp_cnt = he_map.get(emp_id, (0.0, 0))
            d_info = deuda_map.get(emp_id, {'total': 0.0, 'atraso': 0.0, 'colacion': 0.0, 'salida': 0.0, 'permiso': 0.0})
            emp_deuda_total = d_info['total']
            emp_comp = comp_map.get(emp_id, 0.0)

            saldo_neto_emp = emp_he - emp_deuda_total - emp_comp
            total_he_count += emp_cnt

            if saldo_neto_emp > 0:
                total_neto_he += saldo_neto_emp
            elif saldo_neto_emp < 0:
                deuda_restante = abs(saldo_neto_emp)
                total_deuda_neta += deuda_restante

                # Prorratear la deuda restante entre sus componentes originales
                raw_atr = d_info['atraso']
                raw_col = d_info['colacion']
                raw_sad = d_info['salida']
                raw_per = d_info['permiso']
                raw_total = raw_atr + raw_col + raw_sad + raw_per

                if raw_total > 0:
                    factor = deuda_restante / raw_total
                    total_deuda_atrasos += raw_atr * factor
                    total_deuda_colacion += raw_col * factor
                    total_deuda_salidas += raw_sad * factor
                    total_deuda_permisos += raw_per * factor
                else:
                    total_deuda_atrasos += deuda_restante

        resumen['he_aprobadas_horas'] = round(total_neto_he / 60.0, 2)
        resumen['he_aprobadas_count'] = total_he_count
        resumen['deuda_neta_horas'] = round(total_deuda_neta / 60.0, 2)
        resumen['deuda_atrasos_horas'] = round(total_deuda_atrasos / 60.0, 2)
        resumen['deuda_colacion_horas'] = round(total_deuda_colacion / 60.0, 2)
        resumen['deuda_salidas_horas'] = round(total_deuda_salidas / 60.0, 2)
        resumen['deuda_permisos_horas'] = round(total_deuda_permisos / 60.0, 2)

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
                recipients = await config_service.get_destinatarios_rrhh(area)
                
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

