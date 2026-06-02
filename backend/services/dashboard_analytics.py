import asyncio
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any
from loguru import logger
from backend.core.database import db

class DashboardAnalytics:
    def __init__(self):
        self.db = db

    def _build_base_filters(self, area: Optional[str], horario: Optional[str], areas_permitidas: Optional[List[str]]) -> Dict[str, Any]:
        """
        Construye fragmentos de filtros SQL altamente granulares.
        Retorna un dict con condiciones específicas para cada tipo de tabla/contexto.
        """
        emp_conditions = []
        asis_conditions = []
        just_conditions = []
        params = []
        
        # 1. Filtro de Área
        if area and area != 'Todas':
            emp_conditions.append("(SELECT ar.nombre FROM historial_areas h1 LEFT JOIN areas ar ON h1.area_id = ar.id WHERE h1.empleado_id = e.id AND h1.validado = 1 ORDER BY h1.id DESC LIMIT 1) = ?")
            asis_conditions.append("COALESCE(h.area, 'Sin Área') = ?")
            just_conditions.append("COALESCE(h_j.area, 'Sin Área') = ?")
            params.append(area)
            
        # 2. Filtro de Seguridad RLS
        if areas_permitidas is not None:
            if not areas_permitidas:
                emp_conditions.append("1=0")
                asis_conditions.append("1=0")
                just_conditions.append("1=0")
            elif "TODAS" not in [a.upper() for a in areas_permitidas]:
                placeholders = ",".join(["?"] * len(areas_permitidas))
                emp_conditions.append(f"(SELECT ar.nombre FROM historial_areas h1 LEFT JOIN areas ar ON h1.area_id = ar.id WHERE h1.empleado_id = e.id AND h1.validado = 1 ORDER BY h1.id DESC LIMIT 1) IN ({placeholders})")
                asis_conditions.append(f"COALESCE(h.area, 'Sin Área') IN ({placeholders})")
                just_conditions.append(f"COALESCE(h_j.area, 'Sin Área') IN ({placeholders})")
                params.extend(areas_permitidas)

        # JOINS para Asistencias
        asis_join = """
            LEFT JOIN (
                SELECT h1.empleado_id, ar.nombre as area, h1.fecha_desde, h1.fecha_hasta
                FROM historial_areas h1
                LEFT JOIN areas ar ON h1.area_id = ar.id
                WHERE h1.validado = 1
                AND h1.id = (
                    SELECT MAX(h2.id) FROM historial_areas h2 
                    WHERE h2.empleado_id = h1.empleado_id 
                    AND h2.validado = 1
                )
            ) h ON h.empleado_id = a.empleado_id 
                AND a.fecha >= h.fecha_desde 
                AND a.fecha <= COALESCE(h.fecha_hasta, '2099-12-31')
        """

        # JOINS para Justificaciones (Basado en fecha de inicio)
        just_join = """
            LEFT JOIN (
                SELECT h1.empleado_id, ar.nombre as area, h1.fecha_desde, h1.fecha_hasta
                FROM historial_areas h1
                LEFT JOIN areas ar ON h1.area_id = ar.id
                WHERE h1.validado = 1
                AND h1.id = (
                    SELECT MAX(h2.id) FROM historial_areas h2 
                    WHERE h2.empleado_id = h1.empleado_id 
                    AND h2.validado = 1
                )
            ) h_j ON h_j.empleado_id = j.empleado_id 
                AND j.fecha_inicio >= h_j.fecha_desde 
                AND j.fecha_inicio <= COALESCE(h_j.fecha_hasta, '2099-12-31')
        """

        # 3. Filtro de Horario
        horario_params = []
        horario_emp_cond = ""
        horario_asis_cond = ""

        if horario and horario != 'Todos':
            horario_emp_cond = " AND e.id IN (SELECT empleado_id FROM asignacion_turnos WHERE turno_id = ?)"
            horario_asis_cond = " AND a.turno_asignado_id = ?"
            horario_params.append(horario)

        return {
            "emp_cond": (" AND " + " AND ".join(emp_conditions)) if emp_conditions else "",
            "asis_cond": (" AND " + " AND ".join(asis_conditions)) if asis_conditions else "",
            "just_cond": (" AND " + " AND ".join(just_conditions)) if just_conditions else "",
            "asis_join": asis_join,
            "just_join": just_join,
            "horario_emp_cond": horario_emp_cond,
            "horario_asis_cond": horario_asis_cond,
            "params": params,
            "horario_params": horario_params
        }

    async def _get_fuerza_laboral(self, fecha_inicio: str, fecha_fin: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Obtiene métricas demográficas (Género, Edad, Antigüedad, Contratos) optimizadas en SQL."""
        try:
            # Usar fecha_fin como referencia para Antigüedad/Edad para consistencia con datos simulados/futuros
            current_year = int(fecha_fin[:4])
            
            # 1. ACTUAL: Personal Activo (Métricas unificadas en SQL)
            query_params_act = filters['params'] + filters['horario_params']
            query_actual = f"""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN UPPER(genero) IN ('M', 'MASCULINO', 'HOMBRE', 'MASC') THEN 1 ELSE 0 END) as hombres,
                    SUM(CASE WHEN UPPER(genero) IN ('F', 'FEMENINO', 'MUJER', 'FEME') THEN 1 ELSE 0 END) as mujeres,
                    SUM(CASE WHEN UPPER(genero) NOT IN ('M', 'MASCULINO', 'HOMBRE', 'MASC', 'F', 'FEMENINO', 'MUJER', 'FEME') OR genero IS NULL THEN 1 ELSE 0 END) as no_declarado,
                    
                    -- Contratos
                    SUM(CASE WHEN tipo_contrato IS NOT NULL THEN 1 ELSE 0 END) as con_contrato,
                    
                    -- Cubos de Edad (Simplificado en SQL)
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_nacimiento) AS INTEGER)) BETWEEN 15 AND 19 THEN 1 ELSE 0 END) as e15,
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_nacimiento) AS INTEGER)) BETWEEN 20 AND 24 THEN 1 ELSE 0 END) as e20,
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_nacimiento) AS INTEGER)) BETWEEN 25 AND 29 THEN 1 ELSE 0 END) as e25,
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_nacimiento) AS INTEGER)) BETWEEN 30 AND 34 THEN 1 ELSE 0 END) as e30,
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_nacimiento) AS INTEGER)) BETWEEN 35 AND 39 THEN 1 ELSE 0 END) as e35,
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_nacimiento) AS INTEGER)) BETWEEN 40 AND 44 THEN 1 ELSE 0 END) as e40,
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_nacimiento) AS INTEGER)) BETWEEN 45 AND 49 THEN 1 ELSE 0 END) as e45,
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_nacimiento) AS INTEGER)) BETWEEN 50 AND 54 THEN 1 ELSE 0 END) as e50,
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_nacimiento) AS INTEGER)) BETWEEN 55 AND 59 THEN 1 ELSE 0 END) as e55,
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_nacimiento) AS INTEGER)) BETWEEN 60 AND 64 THEN 1 ELSE 0 END) as e60,
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_nacimiento) AS INTEGER)) >= 65 THEN 1 ELSE 0 END) as e65,
                    SUM(CASE WHEN fecha_nacimiento IS NULL THEN 1 ELSE 0 END) as e_sin_reg,

                    -- Antigüedad (Aprovechando current_year para consistencia con Edades)
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_ingreso) AS INTEGER)) < 1 THEN 1 ELSE 0 END) as a1,
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_ingreso) AS INTEGER)) BETWEEN 1 AND 3 THEN 1 ELSE 0 END) as a3,
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_ingreso) AS INTEGER)) BETWEEN 4 AND 5 THEN 1 ELSE 0 END) as a5,
                    SUM(CASE WHEN ({current_year} - CAST(strftime('%Y', fecha_ingreso) AS INTEGER)) > 5 THEN 1 ELSE 0 END) as a_mas5,
                    SUM(CASE WHEN fecha_ingreso IS NULL THEN 1 ELSE 0 END) as a_sin_reg
                FROM empleados e 
                WHERE e.activo = 1
                {filters['emp_cond']} {filters['horario_emp_cond']}
            """
            res = await self.db.fetch_one(query_actual, tuple(query_params_act))
            
            # Query secundaria para tipos de contrato (un listado agrupado es más limpio)
            query_contratos = f"SELECT tipo_contrato, COUNT(*) as c FROM empleados e WHERE e.activo = 1 {filters['emp_cond']} {filters['horario_emp_cond']} GROUP BY 1"
            rows_contratos = await self.db.fetch_all(query_contratos, tuple(query_params_act))
            contratos_dict = {str(r['tipo_contrato'] or 'No Especificado'): r['c'] for r in rows_contratos}

            # Edad promedio
            query_edad_prom = f"SELECT AVG({current_year} - CAST(strftime('%Y', fecha_nacimiento) AS INTEGER)) as edad_prom FROM empleados e WHERE e.activo = 1 AND fecha_nacimiento IS NOT NULL {filters['emp_cond']} {filters['horario_emp_cond']}"
            res_edad = await self.db.fetch_one(query_edad_prom, tuple(query_params_act))
            edad_promedio = round(res_edad['edad_prom'], 1) if res_edad and res_edad['edad_prom'] else 0

            # Contratos por vencer (Plazo Fijo con fecha_fin en los próximos 30 días)
            query_vencer = f"""
                SELECT COUNT(*) as c 
                FROM empleados e 
                JOIN periodos_empleo pe ON pe.empleado_id = e.id AND pe.es_activo = 1
                WHERE e.activo = 1 
                AND e.tipo_contrato = 'Plazo Fijo' 
                AND pe.fecha_fin IS NOT NULL 
                AND pe.fecha_fin <= date('{fecha_fin}', '+30 days') 
                AND pe.fecha_fin >= '{fecha_inicio}'
                {filters['emp_cond']} {filters['horario_emp_cond']}
            """
            res_vencer = await self.db.fetch_all(query_vencer, tuple(query_params_act))
            contratos_por_vencer = res_vencer[0]['c'] if res_vencer else 0

            def format_res(row, c_dict):
                return {
                    "paridad": { 
                        "Hombres": row['hombres'], 
                        "Mujeres": row['mujeres'], 
                        "No Declarado": row['no_declarado'],
                        "Total": row['total'] 
                    },
                    "contratos": c_dict,
                    "edades": {
                        "15 - 19": row['e15'], "20 - 24": row['e20'], "25 - 29": row['e25'], "30 - 34": row['e30'],
                        "35 - 39": row['e35'], "40 - 44": row['e40'], "45 - 49": row['e45'], "50 - 54": row['e50'],
                        "55 - 59": row['e55'], "60 - 64": row['e60'], "65+": row['e65'], "Sin Registrar": row['e_sin_reg']
                    },
                    "antiguedad": {
                        "less_1": row['a1'], "1_3": row['a3'], "3_5": row['a5'], "plus_5": row['a_mas5'], "none": row['a_sin_reg']
                    },
                    "total": row['total']
                }

            stats_actual = format_res(res, contratos_dict)

            # Para bajas (simplificado solo al total para rotación rápida)
            query_params_rot = [fecha_inicio, fecha_fin] + filters['params'] + filters['horario_params']
            query_rot = f"SELECT COUNT(*) as c FROM empleados e WHERE e.fecha_salida >= ? AND e.fecha_salida <= ? {filters['emp_cond']} {filters['horario_emp_cond']}"
            res_rot = await self.db.fetch_one(query_rot, tuple(query_params_rot))
            bajas_total = res_rot['c'] if res_rot else 0
            dotacion = stats_actual['total'] or 1
            tasa_rotacion = round((bajas_total / dotacion) * 100, 1)

            return {
                "hoy": stats_actual,
                "bajas_periodo": { "total": bajas_total },
                "dotacion_activa": stats_actual['total'],
                "edad_promedio": edad_promedio,
                "tasa_rotacion": tasa_rotacion,
                "contratos_por_vencer": contratos_por_vencer
            }
        except Exception as e:
            logger.error(f"Error _get_fuerza_laboral: {e}")
            return {
                "hoy": {"paridad": {}, "contratos": {}, "edades": {}, "antiguedad": {}, "total": 0},
                "bajas_periodo": {"total": 0},
                "dotacion_activa": 0,
                "edad_promedio": 0,
                "tasa_rotacion": 0,
                "contratos_por_vencer": 0
            }

    async def _get_evolucion_contratos(self, fecha_inicio: str, fecha_fin: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Calcula la evolución del mix de contratos en paralelo."""
        try:
            from datetime import datetime
            from dateutil.relativedelta import relativedelta
            
            start_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            end_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
            
            meses = []
            curr = start_dt.replace(day=1)
            while curr <= end_dt:
                meses.append(curr.strftime('%Y-%m'))
                curr += relativedelta(months=1)
            
            async def get_mes_data(mes):
                try:
                    ref_last_day = (datetime.strptime(mes, '%Y-%m') + relativedelta(months=1, days=-1)).strftime('%Y-%m-%d')
                    query = f"""
                        SELECT tipo_contrato, COUNT(*) as c
                        FROM empleados e
                        WHERE (e.fecha_ingreso IS NULL OR e.fecha_ingreso <= ?)
                        AND (e.activo = 1 OR (e.fecha_salida IS NOT NULL AND e.fecha_salida > ?))
                        {filters['emp_cond']} {filters['horario_emp_cond']}
                        GROUP BY tipo_contrato
                    """
                    params = [ref_last_day, ref_last_day] + filters['params'] + filters['horario_params']
                    rows = await self.db.fetch_all(query, tuple(params))
                    
                    mix = { "Planta": 0, "Temporal": 0 }
                    for r in rows:
                        tipo = str(r['tipo_contrato']).strip().capitalize()
                        if "Indefinido" in tipo or "Planta" in tipo: mix["Planta"] += r['c']
                        else: mix["Temporal"] += r['c']
                    return { "mes": mes, **mix }
                except Exception as e:
                    logger.error(f"Error mes {mes}: {e}")
                    return { "mes": mes, "Planta": 0, "Temporal": 0 }

            # Ejecución en paralelo de todos los meses
            puntos = await asyncio.gather(*(get_mes_data(m) for m in meses))
            return sorted(puntos, key=lambda x: x['mes'])

        except Exception as e:
            logger.error(f"Error _get_evolucion_contratos: {e}")
            return []

    async def _get_matriz_asistencia(self, fecha_inicio: str, fecha_fin: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            params = [fecha_inicio, fecha_fin] + filters['params'] + filters['horario_params']
            
            # 1. Obtener la dotación activa teórica de empleados según los filtros
            query_dotacion = f"""
                SELECT COUNT(*) as dotacion
                FROM empleados e
                WHERE e.activo = 1
                {filters['emp_cond']} {filters['horario_emp_cond']}
            """
            params_dot = filters['params'] + filters['horario_params']
            res_dot = await self.db.fetch_one(query_dotacion, tuple(params_dot))
            dotacion_total_area = res_dot.get('dotacion', 0) if res_dot else 0

            # 2. Total turnos obligatorios (Esperados)
            # Regla: Sumamos registros que NO sean exclusiones, O registros que siendo exclusiones (LIBRE/FERIADO) tengan marca real.
            query_esperado = f"""
                SELECT COUNT(*) as esperado
                FROM asistencias a 
                JOIN empleados e ON a.empleado_id = e.id
                {filters['asis_join']}
                WHERE a.fecha >= ? AND a.fecha <= ? 
                AND a.estado != 'NO_ACTIVO'
                {filters['asis_cond']} {filters['horario_asis_cond']}
            """
            res_esperado = await self.db.fetch_one(query_esperado, tuple(params))
            esperado_total = res_esperado.get('esperado', 0) if res_esperado else 0

            # 3. Desglose detallado de estados reales DIARIOS
            query_estados = f"""
                SELECT a.fecha, a.estado, a.hora_entrada_real, COUNT(*) as qty
                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                {filters['asis_join']}
                WHERE a.fecha >= ? AND a.fecha <= ? 
                AND a.estado != 'NO_ACTIVO'
                {filters['asis_cond']} {filters['horario_asis_cond']}
                GROUP BY a.fecha, a.estado, (a.hora_entrada_real IS NOT NULL)
                ORDER BY a.fecha ASC
            """
            res_estados = await self.db.fetch_all(query_estados, tuple(params))
            
            asistencia_real_total = 0
            
            # Clasificación conceptual pura
            # Los estados compuestos/mixtos (como ATR_SAD, PER_ATR, etc.) o anomalías representan asistencia física (presencia)
            estados_asistencia_puros = ['OK', 'ATRASO', 'SALIDA_ADELANTADA', 'ATR_SAD', 'PER_ATR', 'PER_SAD', 'PER_ATR_SAD', 'EN_CURSO', 'EXTRA', 'ANOMALIA']
            estados_puntual = ['OK']
            estados_inasistencia_pura = ['INASISTENCIA', 'FALTA']
            estados_justificados = ['JORNADA_ESPECIAL', 'PERMISO', 'INASISTENCIA_COMPENSADA', 'JORNADA_COMPENSATORIA']
            
            # Generar lista de todas las fechas del rango
            from datetime import datetime, timedelta
            start_date = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            end_date = datetime.strptime(fecha_fin, '%Y-%m-%d')
            
            tendencia_diaria = {}
            curr = start_date
            while curr <= end_date:
                f_str = curr.strftime('%Y-%m-%d')
                tendencia_diaria[f_str] = {"asistencia": 0, "puntualidad": 0, "ausencia_justificada": 0, "inasistencia": 0, "libres": 0}
                curr += timedelta(days=1)
            
            for r in res_estados:
                fecha = r['fecha']
                est = str(r['estado']).upper()
                qty = r['qty']
                tiene_marca = r['hora_entrada_real'] is not None
                
                if fecha not in tendencia_diaria:
                    tendencia_diaria[fecha] = {"asistencia": 0, "puntualidad": 0, "ausencia_justificada": 0, "inasistencia": 0, "libres": 0}
                    
                # Regla de oro: si hay marca física de entrada, representa asistencia real
                if tiene_marca or est in estados_asistencia_puros:
                    tendencia_diaria[fecha]["asistencia"] += qty
                    asistencia_real_total += qty
                    if est in estados_puntual:
                        tendencia_diaria[fecha]["puntualidad"] += qty
                elif est in estados_inasistencia_pura:
                    tendencia_diaria[fecha]["inasistencia"] += qty
                elif est in estados_justificados:
                    # Sin marcas y con estado de justificación = Ausencia Justificada
                    tendencia_diaria[fecha]["ausencia_justificada"] += qty
                else:
                    if est in ['LIBRE', 'FERIADO']:
                        tendencia_diaria[fecha]["libres"] += qty
                    else:
                        tendencia_diaria[fecha]["ausencia_justificada"] += qty

            # Autocompletar la dotación para cada día con libres programados/futuros
            for f in tendencia_diaria.keys():
                d = tendencia_diaria[f]
                registrados = d["asistencia"] + d["ausencia_justificada"] + d["inasistencia"] + d["libres"]
                diferencia = max(0, dotacion_total_area - registrados)
                d["libres"] += diferencia

            # Transformar a lista ordenada
            puntualidad_total = 0
            tendencia_list = []
            for f in sorted(tendencia_diaria.keys()):
                d = tendencia_diaria[f]
                d['fecha'] = f
                # Esperado diario es la suma de asistencia, ausencia justificada e inasistencia
                d['esperado_diario'] = d['asistencia'] + d['ausencia_justificada'] + d['inasistencia']
                puntualidad_total += d['puntualidad']
                tendencia_list.append(d)

            # Calcular tasa de puntualidad global
            puntualidad_pct = round((puntualidad_total / asistencia_real_total) * 100, 1) if asistencia_real_total > 0 else 0

            return {
                "esperado": esperado_total,
                "asistencia_real": asistencia_real_total,
                "puntualidad_total": puntualidad_total,
                "puntualidad_pct": puntualidad_pct,
                "tendencia": tendencia_list
            }
        except Exception as e:
            logger.error(f"Error _get_matriz_asistencia: {e}")
            return {"esperado": 0, "asistencia_real": 0, "puntualidad_total": 0, "puntualidad_pct": 0, "tendencia": []}

    async def _get_fugas_operativas(self, fecha_inicio: str, fecha_fin: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            params = [fecha_inicio, fecha_fin] + filters['params'] + filters['horario_params']
            
            # Tasa Global
            query_tasa = f"""
                SELECT 
                    SUM(a.minutos_atraso + a.minutos_salida_adelantada) as perdidos,
                    SUM(a.horas_teoricas * 60) as teoricos,
                    SUM(a.minutos_atraso) as atrasos_tot,
                    SUM(a.minutos_salida_adelantada) as salidas_tot
                FROM asistencias a JOIN empleados e ON a.empleado_id = e.id
                {filters['asis_join']}
                WHERE a.fecha >= ? AND a.fecha <= ? AND e.activo = 1 
                {filters['asis_cond']} {filters['horario_asis_cond']}
            """
            res_tasa = await self.db.fetch_one(query_tasa, tuple(params))
            perdidos = res_tasa.get('perdidos') or 0
            teoricos = res_tasa.get('teoricos') or 1
            atrasos = res_tasa.get('atrasos_tot') or 0
            salidas = res_tasa.get('salidas_tot') or 0
            
            tasa = round((perdidos / teoricos) * 100, 2) if teoricos > 0 else 0
            tasa_atrasos = round((atrasos / teoricos) * 100, 2) if teoricos > 0 else 0
            tasa_salidas = round((salidas / teoricos) * 100, 2) if teoricos > 0 else 0

            # Heatmap por Área (Agrupando comportamientos colectivos)
            # IMPORTANTE: Separamos COUNT de eventos (para mostrar en UI) de SUM de minutos (para el índice).
            # SUM(minutos) se usaba incorrectamente como conteo, lo que inflaba los números.
            query_areas = f"""
                SELECT 
                    COALESCE(h.area, 'Sin Área') as area, 
                    -- Minutos acumulados (solo para el índice de eficiencia)
                    SUM(a.minutos_atraso)                as min_atraso,
                    SUM(a.minutos_salida_adelantada)     as min_salida,
                    SUM(a.horas_teoricas * 60)           as teoricos,
                    -- Conteo de EVENTOS (días en que ocurrió) — para mostrar en la tabla
                    SUM(CASE WHEN a.minutos_atraso          > 0 THEN 1 ELSE 0 END) as eventos_atraso,
                    SUM(CASE WHEN a.minutos_salida_adelantada > 0 THEN 1 ELSE 0 END) as eventos_salida
                FROM asistencias a JOIN empleados e ON a.empleado_id = e.id
                {filters['asis_join']}
                WHERE a.fecha >= ? AND a.fecha <= ? 
                AND e.activo = 1 
                {filters['asis_cond']} {filters['horario_asis_cond']}
                GROUP BY 1
                ORDER BY (min_atraso + min_salida) DESC
            """
            res_areas = await self.db.fetch_all(query_areas, tuple(params))
            heatmap_areas = []
            for r in res_areas:
                min_a = r['min_atraso'] or 0
                min_s = r['min_salida'] or 0
                t     = r['teoricos'] or 1
                heatmap_areas.append({
                    "area":              r['area'] or 'Sin Area',
                    # Conteo de eventos para la tabla UI
                    "atrasos":           r['eventos_atraso'] or 0,
                    "salidas_anticipadas": r['eventos_salida'] or 0,
                    # Minutos acumulados (disponibles para tooltip o detalle)
                    "min_atraso":        min_a,
                    "min_salida":        min_s,
                    "tasa_fuga":         round(((min_a + min_s) / t) * 100, 1)
                })

            # Días Críticos (Top 5 días con más fugas en el mes)
            query_dias = f"""
                SELECT 
                    a.fecha,
                    SUM(a.minutos_atraso + a.minutos_salida_adelantada) as perdidos
                FROM asistencias a JOIN empleados e ON a.empleado_id = e.id
                {filters['asis_join']}
                WHERE a.fecha >= ? AND a.fecha <= ?
                AND (a.minutos_atraso > 0 OR a.minutos_salida_adelantada > 0)
                AND e.activo = 1 
                {filters['asis_cond']} {filters['horario_asis_cond']}
                GROUP BY a.fecha
                ORDER BY perdidos DESC LIMIT 5
            """
            res_dias = await self.db.fetch_all(query_dias, tuple(params))
            dias_criticos = [{"fecha": r['fecha'], "perdidos": r['perdidos'] or 0} for r in res_dias]

            # 3. Índice de Recidivismo
            # Empleados con más de 2 eventos de fuga (atraso o salida) en el periodo
            # 🛡️ Corrección de Bindings: La subconsulta requiere sus propios parámetros de filtro
            query_recidivismo = f"""
                WITH eventos_count AS (
                    SELECT a.empleado_id, COUNT(*) as qty
                    FROM asistencias a JOIN empleados e ON a.empleado_id = e.id
                    {filters['asis_join']}
                    WHERE a.fecha >= ? AND a.fecha <= ? 
                    AND (a.minutos_atraso > 5 OR a.minutos_salida_adelantada > 5)
                    AND e.activo = 1 
                    {filters['asis_cond']} {filters['horario_asis_cond']}
                    GROUP BY a.empleado_id
                )
                SELECT 
                    COUNT(*) as recidivistas,
                    (SELECT COUNT(*) FROM empleados e WHERE activo=1 {filters['emp_cond']} {filters['horario_emp_cond']}) as total_activos
                FROM eventos_count
                WHERE qty > 2
            """
            params_rec = tuple(params + filters['params'] + filters['horario_params'])
            res_rec = await self.db.fetch_one(query_recidivismo, params_rec)
            rec_idx = 0
            if res_rec and res_rec.get('total_activos', 0) > 0:
                rec_idx = round((res_rec['recidivistas'] / res_rec['total_activos']) * 100, 1)

            return {
                "tasa_global_porcentaje": tasa,
                "tasa_atrasos": tasa_atrasos,
                "tasa_salidas": tasa_salidas,
                "heatmap_areas": heatmap_areas,
                "dias_criticos": dias_criticos,
                "indice_recidivismo": rec_idx
            }
        except Exception as e:
            logger.error(f"Error _get_fugas_operativas: {e}")
            return {"tasa_global_porcentaje": 0, "tasa_atrasos": 0, "tasa_salidas": 0, "heatmap_areas": [], "dias_criticos": []}

    async def _get_embudo_he(self, fecha_inicio: str, fecha_fin: str, filters: Dict[str, Any]) -> Dict[str, float]:
        try:
            params = [fecha_inicio, fecha_fin] + filters['params'] + filters['horario_params']
            query = f"""
                SELECT 
                    SUM(CASE WHEN he.estado = 'APROBADO' THEN he.minutos_bruto ELSE 0 END) as aprobadas,
                    SUM(CASE WHEN he.estado = 'PENDIENTE' OR he.estado IS NULL THEN a.minutos_extra_bruto ELSE 0 END) as pendientes,
                    SUM(CASE WHEN he.estado = 'RECHAZADO' THEN he.minutos_bruto ELSE 0 END) as rechazadas
                FROM asistencias a JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN horas_extras he ON he.empleado_id = a.empleado_id AND he.fecha = a.fecha
                {filters['asis_join']}
                WHERE a.fecha >= ? AND a.fecha <= ? 
                AND a.minutos_extra_bruto > 0
                AND e.activo = 1 
                {filters['asis_cond']} {filters['horario_asis_cond']}
            """
            res = await self.db.fetch_one(query, tuple(params)) or {}
            def to_h(m): return round((m or 0)/60, 1)
            
            return {
                "aprobadas": to_h(res.get('aprobadas')),
                "pendientes": to_h(res.get('pendientes')),
                "rechazadas": to_h(res.get('rechazadas'))
            }
        except Exception as e:
            logger.error(f"Error _get_embudo_he: {e}")
            return {"aprobadas": 0, "pendientes": 0, "rechazadas": 0}

    async def _get_origen_ausentismo(self, fecha_inicio: str, fecha_fin: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            query = f"""
                SELECT 
                    a.estado as nombre,
                    COALESCE(t.pagador, 'Descuento') as pagador,
                    COUNT(*) as qty
                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN justificacion_tipos t ON UPPER(a.estado) = UPPER(t.nombre)
                {filters.get('asis_join', '')}
                WHERE a.fecha >= ? AND a.fecha <= ?
                AND (t.id IS NOT NULL OR a.estado = 'INASISTENCIA')
                {filters.get('asis_cond', '')} {filters.get('horario_asis_cond', '')}
                GROUP BY a.estado, t.pagador
            """
            # Se usa lógica de rango normal para la tabla de asistencias
            params_range = [fecha_inicio, fecha_fin] + filters['params'] + filters['horario_params']
            res = await self.db.fetch_all(query, tuple(params_range))
            desgloses = []
            for r in res:
                tipo_nombre = str(r['nombre']).upper()
                pagador_db = str(r['pagador']).upper()
                
                # Etiquetar según pagador real
                if "EMPLEADOR" in pagador_db:
                    tag = "Costo Empleador"
                elif "SALUD" in pagador_db or "MUTUAL" in pagador_db or "ISL" in pagador_db or "FONASA" in pagador_db or "ISAPRE" in pagador_db:
                    tag = "Costo Externo"
                else:
                    tag = "Descuento a Empleado"
                    
                desgloses.append({
                    "tipo": tipo_nombre,
                    "dias": int(r['qty']),
                    "pagador": tag
                })
            
            # Ordenar de mayor a menor según la cantidad de días
            desgloses.sort(key=lambda x: x['dias'], reverse=True)

            return {
                "desglose": desgloses
            }
        except Exception as e:
            logger.error(f"Error _get_origen_ausentismo: {e}")
            return {"desglose": []}

    async def _get_kpis_extra(self, fecha_inicio: str, fecha_fin: str, filters: Dict[str, Any]) -> Dict[str, float]:
        try:
            params = [fecha_inicio, fecha_fin] + filters['params'] + filters['horario_params']
            # 1. Fatiga Operativa: % de empleados distintos que hicieron >3 días de horas extras en el rango
            # 🛡️ Corrección de Bindings: La subconsulta requiere sus propios parámetros de filtro
            query_fatiga = f"""
                WITH he_count AS (
                    SELECT a.empleado_id, COUNT(*) as dias_extra
                    FROM asistencias a JOIN empleados e ON a.empleado_id = e.id
                    {filters['asis_join']}
                    WHERE a.fecha >= ? AND a.fecha <= ? AND a.minutos_extra_bruto > 30 AND e.activo = 1 
                    {filters['asis_cond']} {filters['horario_asis_cond']}
                    GROUP BY a.empleado_id
                )
                SELECT 
                    COUNT(*) as emp_fatigados,
                    (SELECT COUNT(*) FROM empleados e WHERE activo=1 {filters['emp_cond']} {filters['horario_emp_cond']}) as dotacion 
                FROM he_count
                WHERE dias_extra >= 3
            """
            params_fatiga = tuple(params + filters['params'] + filters['horario_params'])
            res_fatiga = await self.db.fetch_one(query_fatiga, params_fatiga)
            
            fatiga_idx = 0
            if res_fatiga:
                pad_dot = res_fatiga.get('dotacion') or 1 # previene div/0
                fatigados = res_fatiga.get('emp_fatigados') or 0
                fatiga_idx = round((fatigados / pad_dot) * 100, 1)

            # 2. Adhesión Temprana: % promedio que llegó temprano de los turnos totales
            query_adhesion = f"""
                SELECT 
                    SUM(CASE WHEN a.hora_entrada_real < a.hora_entrada_teorica THEN 1 ELSE 0 END) as tempranos,
                    COUNT(*) as turnos
                FROM asistencias a JOIN empleados e ON a.empleado_id = e.id
                {filters['asis_join']}
                WHERE a.fecha >= ? AND a.fecha <= ? 
                AND a.hora_entrada_real IS NOT NULL AND a.hora_entrada_teorica IS NOT NULL
                AND e.activo = 1 
                {filters['asis_cond']} {filters['horario_asis_cond']}
            """
            res_adhesion = await self.db.fetch_one(query_adhesion, tuple(params))
            
            adhesion_idx = 0
            if res_adhesion:
                turnos = res_adhesion.get('turnos') or 1
                tempranos = res_adhesion.get('tempranos') or 0
                adhesion_idx = round((tempranos / turnos) * 100, 1)

            return {
                "indice_fatiga": fatiga_idx,
                "adhesion_temprana": adhesion_idx
            }
        except Exception as e:
            logger.error(f"Error _get_kpis_extra: {e}")
            return {"indice_fatiga": 0, "adhesion_temprana": 0}

    async def _get_top_infractores(self, fecha_inicio: str, fecha_fin: str, filters: Dict[str, Any]) -> list:
        """Top 10 empleados con más eventos de fuga conductual (>5 min atraso o salida adelantada)."""
        try:
            params = [fecha_inicio, fecha_fin] + filters['params'] + filters['horario_params']
            query = f"""
                SELECT 
                    e.apellido_paterno || ' ' || COALESCE(e.apellido_materno, '') || ' ' || e.nombre as nombre_completo,
                    COALESCE(h.area, 'Sin Área') as area,
                    COUNT(*) as eventos_fuga,
                    SUM(a.minutos_atraso) as total_atraso,
                    SUM(a.minutos_salida_adelantada) as total_sad,
                    SUM(a.minutos_deuda) as total_deuda
                FROM asistencias a 
                JOIN empleados e ON a.empleado_id = e.id
                {filters['asis_join']}
                WHERE a.fecha >= ? AND a.fecha <= ?
                AND e.activo = 1
                AND (a.minutos_atraso > 5 OR a.minutos_salida_adelantada > 5)
                {filters['asis_cond']} {filters['horario_asis_cond']}
                GROUP BY a.empleado_id
                ORDER BY eventos_fuga DESC
                LIMIT 10
            """
            rows = await self.db.fetch_all(query, tuple(params))
            return [{
                "nombre": r['nombre_completo'],
                "area": r['area'] or 'Sin Área',
                "eventos": r['eventos_fuga'],
                "min_atraso": r['total_atraso'] or 0,
                "min_sad": r['total_sad'] or 0,
                "min_deuda": r['total_deuda'] or 0
            } for r in rows]
        except Exception as e:
            logger.error(f"Error _get_top_infractores: {e}")
            return []

    async def _get_top_deudores(self, fecha_inicio: str, fecha_fin: str, filters: Dict[str, Any]) -> list:
        """Top 10 empleados con mayor acumulación de minutos de deuda (impacto financiero)."""
        try:
            params = [fecha_inicio, fecha_fin] + filters['params'] + filters['horario_params']
            query = f"""
                SELECT 
                    e.apellido_paterno || ' ' || COALESCE(e.apellido_materno, '') || ' ' || e.nombre as nombre_completo,
                    COALESCE(h.area, 'Sin Área') as area,
                    SUM(a.minutos_deuda) as total_deuda_min,
                    ROUND(SUM(a.minutos_deuda) / 60.0, 1) as deuda_horas,
                    SUM(CASE WHEN a.minutos_deuda > 0 THEN 1 ELSE 0 END) as dias_deuda
                FROM asistencias a 
                JOIN empleados e ON a.empleado_id = e.id
                {filters['asis_join']}
                WHERE a.fecha >= ? AND a.fecha <= ?
                AND e.activo = 1
                AND a.minutos_deuda > 0
                {filters['asis_cond']} {filters['horario_asis_cond']}
                GROUP BY a.empleado_id
                ORDER BY total_deuda_min DESC
                LIMIT 10
            """
            rows = await self.db.fetch_all(query, tuple(params))
            return [{
                "nombre": r['nombre_completo'],
                "area": r['area'] or 'Sin Área',
                "deuda_min": r['total_deuda_min'] or 0,
                "deuda_hrs": r['deuda_horas'] or 0,
                "dias": r['dias_deuda'] or 0
            } for r in rows]
        except Exception as e:
            logger.error(f"Error _get_top_deudores: {e}")
            return []

    async def _get_heatmap_area_dia(self, fecha_inicio: str, fecha_fin: str, filters: Dict[str, Any]) -> list:
        """Mapa de calor bidimensional: Área × Día de la semana con minutos de fuga totales."""
        try:
            params = [fecha_inicio, fecha_fin] + filters['params'] + filters['horario_params']
            query = f"""
                SELECT 
                    COALESCE(h.area, 'Sin Área') as area,
                    CAST(strftime('%w', a.fecha) AS INTEGER) as dia_semana,
                    SUM(a.minutos_atraso) + SUM(a.minutos_salida_adelantada) as total_fugas,
                    SUM(CASE WHEN a.minutos_atraso > 0 THEN 1 ELSE 0 END) + 
                    SUM(CASE WHEN a.minutos_salida_adelantada > 0 THEN 1 ELSE 0 END) as eventos
                FROM asistencias a 
                JOIN empleados e ON a.empleado_id = e.id
                {filters['asis_join']}
                WHERE a.fecha >= ? AND a.fecha <= ?
                AND e.activo = 1
                AND (a.minutos_atraso > 0 OR a.minutos_salida_adelantada > 0)
                {filters['asis_cond']} {filters['horario_asis_cond']}
                GROUP BY COALESCE(h.area, 'Sin Área'), dia_semana
                ORDER BY COALESCE(h.area, 'Sin Área'), dia_semana
            """
            rows = await self.db.fetch_all(query, tuple(params))
            return [{
                "area": r['area'] or 'Sin Área',
                "dia": r['dia_semana'],
                "fugas_min": r['total_fugas'] or 0,
                "eventos": r['eventos'] or 0
            } for r in rows]
        except Exception as e:
            logger.error(f"Error _get_heatmap_area_dia: {e}")
            return []

    async def _get_embudo_productividad(self, fecha_inicio: str, fecha_fin: str, filters: Dict[str, Any]) -> Dict[str, float]:
        """Embudo de productividad: Horas Programadas → Fugas → Trabajadas → Sobretiempo."""
        try:
            params = [fecha_inicio, fecha_fin] + filters['params'] + filters['horario_params']
            # Duplicamos TODOS los parámetros para las subqueries (mismos filtros de fecha, área, horario)
            params_full = params + params
            
            # Adaptamos los filtros para el alias j en lugar de a
            j_join = filters['asis_join'].replace('a.empleado_id', 'j.empleado_id').replace('a.fecha', 'j.fecha')
            j_cond = filters['asis_cond'].replace('a.', 'j.')
            
            query = f"""
                WITH all_productividad AS (
                    SELECT 
                        SUM(a.horas_teoricas) as programadas,
                        SUM(a.horas_trabajadas) as trabajadas,
                        SUM(a.minutos_deuda) as minutos_fuga,
                        SUM(a.minutos_extra_bruto) as minutos_extra,
                        SUM(CASE WHEN a.horas_trabajadas = 0 AND a.minutos_deuda = 0 THEN a.horas_teoricas ELSE 0 END) as horas_ausencia
                    FROM asistencias a 
                    JOIN empleados e ON a.empleado_id = e.id
                    {filters['asis_join']}
                    WHERE a.fecha >= ? AND a.fecha <= ?
                    AND e.activo = 1
                    AND a.estado NOT IN ('NO_ACTIVO', 'LIBRE', 'FERIADO')
                    {filters['asis_cond']} {filters['horario_asis_cond']}
                )
                SELECT 
                    ROUND(programadas, 1) as programadas,
                    ROUND(trabajadas, 1) as trabajadas_asistencia,
                    ROUND(minutos_fuga / 60.0, 1) as horas_fuga,
                    ROUND(horas_ausencia, 1) as horas_ausencia,
                    
                    minutos_extra as he_regulares_min,
                    COALESCE((
                        SELECT SUM(j.minutos_trabajados) 
                        FROM jornadas_especiales j 
                        JOIN empleados e ON j.empleado_id = e.id 
                        {j_join}
                        WHERE j.fecha >= ? AND j.fecha <= ?
                        AND e.activo = 1
                        {j_cond} {filters['horario_emp_cond']}
                    ), 0) as jornadas_especiales_min,
                    
                    COALESCE((
                        SELECT COUNT(j.id) 
                        FROM jornadas_especiales j 
                        JOIN empleados e ON j.empleado_id = e.id 
                        {j_join}
                        WHERE j.fecha >= ? AND j.fecha <= ?
                        AND e.activo = 1
                        {j_cond} {filters['horario_emp_cond']}
                    ), 0) as jornadas_especiales_count
                FROM all_productividad
            """
            
            # Ajustamos los parámetros porque ahora hay otra subquery que necesita 2 fechas
            params_full_con_count = params_full + [fecha_inicio, fecha_fin]
            res = await self.db.fetch_one(query, tuple(params_full_con_count))
            
            if not res:
                return {"programadas": 0, "trabajadas": 0, "horas_fuga": 0, "horas_ausencia": 0, "he_regulares_min": 0, "jornadas_especiales_min": 0, "jornadas_especiales_count": 0, "eficiencia_pct": 0}
                
            programadas = res.get('programadas') or 0
            trabajadas_asis = res.get('trabajadas_asistencia') or 0
            fuga = res.get('horas_fuga') or 0
            ausencias = res.get('horas_ausencia') or 0
            he_min = res.get('he_regulares_min') or 0
            je_min = res.get('jornadas_especiales_min') or 0
            je_count = res.get('jornadas_especiales_count') or 0
            
            # El Frontend redondeará para evitar el desfase de decimales. Aquí enviamos minutos y las HE regulares.
            trabajadas_totales = round(trabajadas_asis + (je_min / 60.0), 1)
            
            return {
                "programadas": programadas,
                "trabajadas": trabajadas_totales,
                "horas_fuga": fuga,
                "horas_ausencia": ausencias,
                "he_regulares_min": he_min,
                "jornadas_especiales_min": je_min,
                "jornadas_especiales_count": je_count,
                "eficiencia_pct": round((trabajadas_totales / programadas) * 100, 1) if programadas > 0 else 0
            }
        except Exception as e:
            logger.error(f"Error _get_embudo_productividad: {e}")
            return {"programadas": 0, "trabajadas": 0, "horas_fuga": 0, "horas_ausencia": 0, "he_regulares_min": 0, "jornadas_especiales_min": 0, "jornadas_especiales_count": 0, "eficiencia_pct": 0}

    async def get_dashboard_metrics(self, fecha_inicio: str, fecha_fin: str, area: Optional[str] = None, horario: Optional[str] = None, areas_permitidas: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Orquestador principal de métricas de Dashboard.
        Lanza todas las consultas de forma paralela con asyncio.gather.
        """
        filters = self._build_base_filters(area, horario, areas_permitidas)

        # Ejecutamos las consultas magnas simultáneamente con asyncio.gather
        results = await asyncio.gather(
            self._get_fuerza_laboral(fecha_inicio, fecha_fin, filters),
            self._get_matriz_asistencia(fecha_inicio, fecha_fin, filters),
            self._get_fugas_operativas(fecha_inicio, fecha_fin, filters),
            self._get_embudo_he(fecha_inicio, fecha_fin, filters),
            self._get_origen_ausentismo(fecha_inicio, fecha_fin, filters),
            self._get_kpis_extra(fecha_inicio, fecha_fin, filters),
            self._get_evolucion_contratos(fecha_inicio, fecha_fin, filters),
            self._get_top_infractores(fecha_inicio, fecha_fin, filters),
            self._get_top_deudores(fecha_inicio, fecha_fin, filters),
            self._get_heatmap_area_dia(fecha_inicio, fecha_fin, filters),
            self._get_embudo_productividad(fecha_inicio, fecha_fin, filters)
        )

        return {
            "fuerza_laboral": results[0],
            "matriz_asistencia": results[1],
            "fugas_operativas": results[2],
            "embudo_he": results[3],
            "origen_ausentismo": results[4],
            "kpis_extra": results[5],
            "evolucion_contratos": results[6],
            "top_infractores": results[7],
            "top_deudores": results[8],
            "heatmap_area_dia": results[9],
            "embudo_productividad": results[10]
        }

    async def get_desviaciones_detalle(self, fecha_inicio: str, fecha_fin: str, tipo: str, motivo: Optional[str] = None, area: Optional[str] = None, horario: Optional[str] = None, areas_permitidas: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Obtiene el detalle (hasta 100 registros) de las asistencias que provocan fugas, ausencias o justificaciones
        para un rango de fechas y filtros determinados.
        """
        filters = self._build_base_filters(area, horario, areas_permitidas)
        
        query = f"""
            SELECT 
                a.fecha, 
                e.apellido_paterno || ' ' || COALESCE(e.apellido_materno, '') || ' ' || e.nombre as empleado, 
                e.rut, 
                a.estado, 
                a.horas_teoricas, 
                a.horas_trabajadas, 
                a.minutos_deuda
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            {filters['asis_join']}
            WHERE a.fecha >= ? AND a.fecha <= ?
            {filters['asis_cond']}
            {filters['horario_asis_cond']}
        """
        
        params = [fecha_inicio, fecha_fin] + filters['params'] + filters['horario_params']
        
        if tipo == 'fuga':
            query += " AND a.minutos_deuda > 0"
        elif tipo == 'ausencia':
            # Registros que causan vacíos en la cuadratura
            query += " AND a.horas_teoricas > 0 AND (a.horas_teoricas - (MAX(0, a.horas_trabajadas - COALESCE(a.minutos_extra_bruto, 0)/60.0) + a.minutos_deuda/60.0)) > 0.1"
        elif tipo == 'justificacion' and motivo:
            query += " AND UPPER(a.estado) = ?"
            params.append(motivo.upper())
            
        query += " ORDER BY a.fecha DESC LIMIT 100"
        
        try:
            res = await self.db.fetch_all(query, tuple(params))
            return [dict(r) for r in res]
        except Exception as e:
            logger.error(f"Error get_desviaciones_detalle: {e}")
            return []

dashboard_analytics = DashboardAnalytics()
