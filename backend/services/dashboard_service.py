import sqlite3
from datetime import datetime
from typing import List, Optional
from loguru import logger
from backend.core.database import db

class DashboardService:
    def __init__(self):
        self.db = db

    async def get_pulse_today(self, area: Optional[str] = None, areas_permitidas: Optional[List[str]] = None):
        """
        Calcula las métricas de asistencia 'Real-Time' del día de hoy.
        [REAL_TIME_PULSE_ENGINE]: Calcula para el 'Turno Actual' en base a la hora vigente.
        """
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        current_hour = now.hour
        
        # Determinar el bloque de turno teórico usando heurística (Mañana: 05:00 - 13:59, Tarde: 14:00 - 21:59, Noche: 22:00 - 04:59)
        if 5 <= current_hour < 14:
            turno_nombre = "Mañana"
            hora_inicio_teorica_start = "05:00:00"
            hora_inicio_teorica_end = "13:59:59"
        elif 14 <= current_hour < 22:
            turno_nombre = "Tarde"
            hora_inicio_teorica_start = "14:00:00"
            hora_inicio_teorica_end = "21:59:59"
        else:
            turno_nombre = "Noche"
            hora_inicio_teorica_start = "22:00:00"
            hora_inicio_teorica_end = "23:59:59"
            # Si estamos pasando la medianoche (madrugada), la fecha del turno en BD es probabilísticamente el día anterior.
            if current_hour < 5:
                today_str = (now).strftime("%Y-%m-%d") # TODO: Ajustar a (now - timedelta(days=1)) si marca estricto
                hora_inicio_teorica_start = "00:00:00"
                hora_inicio_teorica_end = "04:59:59"
        
        # Filtro de área y RLS
        area_condition = ""
        params = [today_str, hora_inicio_teorica_start, hora_inicio_teorica_end]
        
        if area:
            area_condition = "AND ar.nombre = ?"
            params.append(area)
        elif areas_permitidas:
            placeholders = ",".join(["?"] * len(areas_permitidas))
            area_condition = f"AND ar.nombre IN ({placeholders})"
            params.extend(areas_permitidas)

        # 1. Total de Empleados esperados PARA ESTE TURNO ESPECIFICO
        query_pulse = f"""
            SELECT 
                COUNT(*) as total_esperados,
                SUM(CASE WHEN a.hora_entrada_real IS NOT NULL THEN 1 ELSE 0 END) as total_presentes,
                SUM(CASE WHEN a.minutos_atraso > 0 THEN 1 ELSE 0 END) as total_atrasos,
                SUM(CASE WHEN a.estado = 'EN_CURSO' THEN 1 ELSE 0 END) as alertas_en_curso
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE a.fecha = ? 
              AND a.hora_entrada_teorica >= ? AND a.hora_entrada_teorica <= ?
              AND e.activo = 1 {area_condition}
        """
        
        try:
            result = await self.db.fetch_one(query_pulse, tuple(params))
            if not result:
                return {
                    "turno_actual": turno_nombre,
                    "esperados": 0, "presentes": 0, "atrasos": 0, "alertas_en_curso": 0, "tasa_asistencia": 0
                }
            
            esperados = result.get('total_esperados', 0) or 0
            presentes = result.get('total_presentes', 0) or 0
            atrasos = result.get('total_atrasos', 0) or 0
            alertas = result.get('alertas_en_curso', 0) or 0
            
            tasa_asistencia = round((presentes / esperados * 100), 1) if esperados > 0 else 0
            
            return {
                "turno_actual": turno_nombre,
                "esperados": esperados,
                "presentes": presentes,
                "atrasos": atrasos,
                "alertas_en_curso": alertas,
                "tasa_asistencia": tasa_asistencia
            }
        except Exception as e:
            logger.error(f"Error getting today's pulse: {e}")
            return {
                "turno_actual": "N/A",
                "esperados": 0, "presentes": 0, "atrasos": 0, "alertas_en_curso": 0, "tasa_asistencia": 0
            }

    async def get_gender_distribution(self, area: Optional[str] = None, areas_permitidas: Optional[List[str]] = None):
        """
        Calcula la distribución de dotación por género con RLS.
        """
        area_condition = ""
        params = []
        
        if area:
            area_condition = "AND ar.nombre = ?"
            params.append(area)
        elif areas_permitidas:
            placeholders = ",".join(["?"] * len(areas_permitidas))
            area_condition = f"AND ar.nombre IN ({placeholders})"
            params.extend(areas_permitidas)

        query = f"""
            SELECT 
                COALESCE(e.genero, 'No Especificado') as genero,
                COUNT(*) as cantidad
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE e.activo = 1 {area_condition}
            GROUP BY e.genero
        """
        
        try:
            results = await self.db.fetch_all(query, tuple(params))
            return [dict(r) for r in results]
        except Exception as e:
            logger.error(f"Error getting gender distribution: {e}")
            return []

    async def get_period_metrics(self, fecha_inicio: str, fecha_fin: str, area: Optional[str] = None, areas_permitidas: Optional[List[str]] = None):
        """
        Calcula las métricas consolidadas y KPIs para un período específico con RLS.
        """
        area_condition = ""
        params = [fecha_inicio, fecha_fin]
        
        if area:
            area_condition = "AND ar.nombre = ?"
            params.append(area)
        elif areas_permitidas:
            placeholders = ",".join(["?"] * len(areas_permitidas))
            area_condition = f"AND ar.nombre IN ({placeholders})"
            params.extend(areas_permitidas)

        try:
            # 1. KPIs Globales
            query_kpis = f"""
                SELECT 
                    COUNT(*) as total_turnos,
                    SUM(CASE WHEN a.estado = 'INASISTENCIA' OR a.estado LIKE '%FALTA%' THEN 1 ELSE 0 END) as inasistencias,
                    SUM(CASE WHEN a.minutos_atraso > 0 THEN 1 ELSE 0 END) as total_llegadas_tarde,
                    SUM(a.horas_trabajadas) as total_horas_trabajadas
                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE a.fecha >= ? AND a.fecha <= ? AND e.activo = 1 {area_condition}
            """
            kpi_result = await self.db.fetch_one(query_kpis, tuple(params))
            
            total_turnos = kpi_result.get('total_turnos', 0) or 0
            inasistencias = kpi_result.get('inasistencias', 0) or 0
            tasa_ausentismo = round((inasistencias / total_turnos * 100), 1) if total_turnos > 0 else 0
            
            # Embudo de Horas Extras (V2)
            # Utilizamos minutos_extra_bruto y estado_he (APROBADO, RECHAZADO, PENDIENTE)
            query_he_funnel = f"""
                SELECT 
                    SUM(a.minutos_extra_bruto) as total_bruto_min,
                    SUM(CASE WHEN he.estado = 'APROBADO' THEN he.minutos_bruto ELSE 0 END) as total_aprobadas_min,
                    SUM(CASE WHEN he.estado = 'PENDIENTE' OR he.estado IS NULL THEN a.minutos_extra_bruto ELSE 0 END) as total_pendientes_min,
                    SUM(CASE WHEN he.estado = 'RECHAZADO' THEN he.minutos_bruto ELSE 0 END) as total_rechazadas_min
                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN horas_extras he ON he.empleado_id = a.empleado_id AND he.fecha = a.fecha
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE a.fecha >= ? AND a.fecha <= ? 
                AND a.minutos_extra_bruto > 0
                AND e.activo = 1 {area_condition}
            """
            he_result = await self.db.fetch_one(query_he_funnel, tuple(params))
            
            # Convertimos a horas con 1 decimal
            def to_hrs(mins): return round((mins or 0) / 60, 1)
            
            # Consulta para volumen de horas de jornadas especiales
            query_jornadas_especiales = f"""
                SELECT SUM(j.minutos_trabajados) as total_minutos
                FROM jornadas_especiales j
                JOIN empleados e ON j.empleado_id = e.id
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE j.fecha >= ? AND j.fecha <= ?
                AND e.activo = 1 {area_condition}
            """
            je_result = await self.db.fetch_one(query_jornadas_especiales, tuple(params))
            total_je_min = je_result.get('total_minutos') or 0

            embudo_he = {
                "total": to_hrs(he_result.get('total_bruto_min')),
                "aprobadas": to_hrs(he_result.get('total_aprobadas_min')),
                "pendientes": to_hrs(he_result.get('total_pendientes_min')),
                "rechazadas": to_hrs(he_result.get('total_rechazadas_min')),
                "jornadas_especiales": to_hrs(total_je_min)
            }

            # [DASHBOARD_RATIO_KPI_ENGINE]: Ratios de impacto y desviación
            query_ratios = f"""
                SELECT 
                    COALESCE((SELECT SUM(he2.minutos_autorizados) FROM horas_extras he2
                              JOIN empleados e2 ON he2.empleado_id = e2.id
                              LEFT JOIN historial_areas ha2 ON e2.id = ha2.empleado_id AND ha2.es_actual = 1 AND ha2.validado = 1
                              LEFT JOIN areas ar2 ON ha2.area_id = ar2.id
                              WHERE he2.fecha >= ? AND he2.fecha <= ? AND e2.activo = 1
                              AND he2.estado = 'APROBADO' {area_condition.replace('ar.nombre', 'ar2.nombre')}), 0) as total_min_extra,
                    SUM(a.horas_teoricas * 60) as total_min_teoricos,
                    SUM(a.minutos_atraso + a.minutos_salida_adelantada) as total_min_desviacion
                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE a.fecha >= ? AND a.fecha <= ? AND e.activo = 1 {area_condition}
            """
            ratio_result = await self.db.fetch_one(query_ratios, tuple(params + params))
            
            min_extra = ratio_result.get('total_min_extra', 0) or 0
            min_teoricos = ratio_result.get('total_min_teoricos', 0) or 0
            min_desviacion = ratio_result.get('total_min_desviacion', 0) or 0
            
            ratio_impacto_he = round((min_extra / min_teoricos * 100), 1) if min_teoricos > 0 else 0
            ratio_desviacion = round((min_desviacion / min_teoricos * 100), 1) if min_teoricos > 0 else 0

            # 1.2 Intensidad de Permisos vs Justificaciones
            query_permisos = f"""
                SELECT 
                    SUM(CASE WHEN t.es_por_horas = 1 THEN 1 ELSE 0 END) as total_permisos,
                    SUM(CASE WHEN t.es_por_horas = 0 THEN 1 ELSE 0 END) as total_justificaciones
                FROM justificaciones j
                JOIN justificacion_tipos t ON j.tipo_id = t.id
                JOIN empleados e ON j.empleado_id = e.id
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE j.fecha_inicio >= ? AND j.fecha_inicio <= ? AND e.activo = 1 {area_condition}
            """
            permisos_result = await self.db.fetch_one(query_permisos, tuple(params))
            total_permisos = permisos_result.get('total_permisos', 0) or 0
            total_justificaciones = permisos_result.get('total_justificaciones', 0) or 0
            
            # Obtener dotación activa para el ratio
            query_dotacion = f"SELECT COUNT(*) as dotacion FROM empleados e LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1 LEFT JOIN areas ar ON ha.area_id = ar.id WHERE e.activo = 1 {area_condition}"
            dotacion_result = await self.db.fetch_one(query_dotacion, tuple(params[2:])) 
            dotacion = dotacion_result.get('dotacion', 1) or 1
            
            intensidad_permisos = round((total_permisos / dotacion * 100), 1)

            # 1.3 Composición de Dotación (Indefinidos vs Temporales)
            query_contratos = f"SELECT e.tipo_contrato, COUNT(*) as cantidad FROM empleados e LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1 LEFT JOIN areas ar ON ha.area_id = ar.id WHERE e.activo = 1 {area_condition} GROUP BY e.tipo_contrato"
            contratos_result = await self.db.fetch_all(query_contratos, tuple(params[2:]))
            composicion_contratos = {row['tipo_contrato'] or 'No Especificado': row['cantidad'] for row in contratos_result}

            # 2. Distribución de Motivos de Ausencia (Justificaciones y Faltas)
            query_motivos = f"""
                SELECT a.estado, COUNT(*) as cantidad
                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE a.fecha >= ? AND a.fecha <= ? 
                AND a.estado NOT IN ('OK', 'ATRASO', 'SALIDA_ADELANTADA', 'ATR_SAD', 'EN_CURSO', 'JORNADA_ESPECIAL', 'EXTRA', 'LIBRE', 'FERIADO', 'PENDIENTE', 'NO_ACTIVO')
                AND e.activo = 1 {area_condition}
                GROUP BY a.estado
                ORDER BY cantidad DESC
            """
            motivos = await self.db.fetch_all(query_motivos, tuple(params))
            
            # 3. TOP 5 Deudores de Tiempo (Atrasos y salidas tempranas)
            # Usando un JOIN con una subquery o agregación
            query_deudores = f"""
                SELECT e.apellido_paterno || ' ' || COALESCE(NULLIF(e.apellido_materno,''),'') || ' ' || e.nombre as empleado, SUM(a.minutos_deuda) as deuda_minutos
                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE a.fecha >= ? AND a.fecha <= ? AND a.minutos_deuda > 0 AND e.activo = 1 {area_condition}
                GROUP BY e.id
                ORDER BY deuda_minutos DESC
                LIMIT 5
            """
            top_deudores = await self.db.fetch_all(query_deudores, tuple(params))
            
            # 4. TOP 5 Generadores Horas Extras
            query_generadores_he = f"""
                SELECT e.apellido_paterno || ' ' || COALESCE(NULLIF(e.apellido_materno,''),'') || ' ' || e.nombre as empleado, SUM(a.horas_trabajadas - a.horas_teoricas) as sum_he
                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE a.fecha >= ? AND a.fecha <= ? 
                AND a.estado IN ('EXTRA', 'OK', 'DESBORDE_LEY88', 'H.E_BOLSA')
                AND a.horas_trabajadas > a.horas_teoricas
                AND e.activo = 1 {area_condition}
                GROUP BY e.id
                ORDER BY sum_he DESC
                LIMIT 5
            """
            top_he = await self.db.fetch_all(query_generadores_he, tuple(params))
            # 5. Tendencia Diaria (Daily Trend)
            query_trend = f"""
                SELECT 
                    a.fecha,
                    SUM(CASE WHEN a.estado = 'INASISTENCIA' OR a.estado LIKE '%FALTA%' THEN 1 ELSE 0 END) as inasistencias,
                    SUM(a.minutos_atraso) as minutos_atraso,
                    SUM(CASE WHEN a.horas_trabajadas > a.horas_teoricas AND a.estado IN ('EXTRA', 'OK', 'DESBORDE_LEY88', 'H.E_BOLSA') THEN (a.horas_trabajadas - a.horas_teoricas) ELSE 0 END) as horas_extras
                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE a.fecha >= ? AND a.fecha <= ? AND e.activo = 1 {area_condition}
                GROUP BY a.fecha
                ORDER BY a.fecha ASC
            """
            daily_trend_rows = await self.db.fetch_all(query_trend, tuple(params))
            daily_trend = [dict(r) for r in daily_trend_rows]

            return {
                "kpis": {
                    "tasa_ausentismo": tasa_ausentismo,
                    "embudo_he": embudo_he,
                    "total_llegadas_tarde": kpi_result.get('total_llegadas_tarde', 0) or 0,
                    "ratio_impacto_he": ratio_impacto_he,
                    "ratio_desviacion": ratio_desviacion,
                    "intensidad_permisos": intensidad_permisos,
                    "total_justificaciones": total_justificaciones
                },
                "composicion_contratos": composicion_contratos,
                "motivos": [dict(m) for m in motivos],
                "top_deudores": [dict(d) for d in top_deudores],
                "top_he": [dict(h) for h in top_he],
                "daily_trend": daily_trend
            }

        except Exception as e:
            logger.error(f"Error calculating period metrics: {e}")
            return {"kpis": {}, "motivos": [], "top_deudores": [], "top_he": []}

dashboard_service = DashboardService()
