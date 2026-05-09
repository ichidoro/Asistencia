import os

def replace_in_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # get_pulse_today
    content = content.replace(
        'area_condition = "AND e.area = ?"',
        'area_condition = "AND ar.nombre = ?"'
    )
    content = content.replace(
        'area_condition = f"AND e.area IN ({placeholders})"',
        'area_condition = f"AND ar.nombre IN ({placeholders})"'
    )
    content = content.replace(
        '''FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            WHERE a.fecha = ? ''',
        '''FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE a.fecha = ? '''
    )

    # get_gender_distribution
    content = content.replace(
        'area_condition = "AND area = ?"',
        'area_condition = "AND ar.nombre = ?"'
    )
    content = content.replace(
        'area_condition = f"AND area IN ({placeholders})"',
        'area_condition = f"AND ar.nombre IN ({placeholders})"'
    )
    content = content.replace(
        '''            SELECT 
                COALESCE(genero, 'No Especificado') as genero,
                COUNT(*) as cantidad
            FROM empleados
            WHERE activo = 1 {area_condition}
            GROUP BY genero''',
        '''            SELECT 
                COALESCE(e.genero, 'No Especificado') as genero,
                COUNT(*) as cantidad
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE e.activo = 1 {area_condition}
            GROUP BY e.genero'''
    )

    # get_period_metrics general
    content = content.replace(
        '''                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                WHERE a.fecha >= ? AND a.fecha <= ? AND e.activo = 1 {area_condition}''',
        '''                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE a.fecha >= ? AND a.fecha <= ? AND e.activo = 1 {area_condition}'''
    )
    
    # get_period_metrics: Embudo de Horas Extras
    content = content.replace(
        '''                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN horas_extras he ON he.empleado_id = a.empleado_id AND he.fecha = a.fecha
                WHERE a.fecha >= ? AND a.fecha <= ? 
                AND a.minutos_extra_bruto > 0
                AND e.activo = 1 {area_condition}''',
        '''                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN horas_extras he ON he.empleado_id = a.empleado_id AND he.fecha = a.fecha
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE a.fecha >= ? AND a.fecha <= ? 
                AND a.minutos_extra_bruto > 0
                AND e.activo = 1 {area_condition}'''
    )

    # get_period_metrics: jornadas_especiales
    content = content.replace(
        '''                FROM jornadas_especiales j
                JOIN empleados e ON j.empleado_id = e.id
                WHERE j.fecha >= ? AND j.fecha <= ?
                AND e.activo = 1 {area_condition}''',
        '''                FROM jornadas_especiales j
                JOIN empleados e ON j.empleado_id = e.id
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE j.fecha >= ? AND j.fecha <= ?
                AND e.activo = 1 {area_condition}'''
    )

    # get_period_metrics: ratios (subquery)
    content = content.replace(
        '''                    COALESCE((SELECT SUM(he2.minutos_autorizados) FROM horas_extras he2
                              JOIN empleados e2 ON he2.empleado_id = e2.id
                              WHERE he2.fecha >= ? AND he2.fecha <= ? AND e2.activo = 1
                              AND he2.estado = 'APROBADO' {area_condition}), 0) as total_min_extra,''',
        '''                    COALESCE((SELECT SUM(he2.minutos_autorizados) FROM horas_extras he2
                              JOIN empleados e2 ON he2.empleado_id = e2.id
                              LEFT JOIN historial_areas ha2 ON e2.id = ha2.empleado_id AND ha2.es_actual = 1 AND ha2.validado = 1
                              LEFT JOIN areas ar2 ON ha2.area_id = ar2.id
                              WHERE he2.fecha >= ? AND he2.fecha <= ? AND e2.activo = 1
                              AND he2.estado = 'APROBADO' {area_condition.replace('ar.nombre', 'ar2.nombre')}), 0) as total_min_extra,'''
    )

    # get_period_metrics: permisos
    content = content.replace(
        '''                FROM justificaciones j
                JOIN justificacion_tipos t ON j.tipo_id = t.id
                JOIN empleados e ON j.empleado_id = e.id
                WHERE j.fecha_inicio >= ? AND j.fecha_inicio <= ? AND e.activo = 1 {area_condition}''',
        '''                FROM justificaciones j
                JOIN justificacion_tipos t ON j.tipo_id = t.id
                JOIN empleados e ON j.empleado_id = e.id
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE j.fecha_inicio >= ? AND j.fecha_inicio <= ? AND e.activo = 1 {area_condition}'''
    )

    # get_period_metrics: dotacion
    content = content.replace(
        '''query_dotacion = f"SELECT COUNT(*) as dotacion FROM empleados e WHERE e.activo = 1 {area_condition}"''',
        '''query_dotacion = f"SELECT COUNT(*) as dotacion FROM empleados e LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1 LEFT JOIN areas ar ON ha.area_id = ar.id WHERE e.activo = 1 {area_condition}"'''
    )

    # get_period_metrics: contratos
    content = content.replace(
        '''query_contratos = f"SELECT tipo_contrato, COUNT(*) as cantidad FROM empleados e WHERE e.activo = 1 {area_condition} GROUP BY tipo_contrato"''',
        '''query_contratos = f"SELECT e.tipo_contrato, COUNT(*) as cantidad FROM empleados e LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1 LEFT JOIN areas ar ON ha.area_id = ar.id WHERE e.activo = 1 {area_condition} GROUP BY e.tipo_contrato"'''
    )

    # get_period_metrics: motivos
    content = content.replace(
        '''                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                WHERE a.fecha >= ? AND a.fecha <= ? 
                AND a.estado NOT IN ('OK', 'ATRASO', 'SALIDA_ADELANTADA', 'ATR_SAD', 'EN_CURSO', 'JORNADA_ESPECIAL', 'EXTRA', 'LIBRE', 'FERIADO', 'PENDIENTE', 'NO_ACTIVO')
                AND e.activo = 1 {area_condition}''',
        '''                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE a.fecha >= ? AND a.fecha <= ? 
                AND a.estado NOT IN ('OK', 'ATRASO', 'SALIDA_ADELANTADA', 'ATR_SAD', 'EN_CURSO', 'JORNADA_ESPECIAL', 'EXTRA', 'LIBRE', 'FERIADO', 'PENDIENTE', 'NO_ACTIVO')
                AND e.activo = 1 {area_condition}'''
    )

    # get_period_metrics: deudores
    content = content.replace(
        '''                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                WHERE a.fecha >= ? AND a.fecha <= ? AND a.minutos_atraso > 0 AND e.activo = 1 {area_condition}''',
        '''                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE a.fecha >= ? AND a.fecha <= ? AND a.minutos_atraso > 0 AND e.activo = 1 {area_condition}'''
    )

    # get_period_metrics: generadores he
    content = content.replace(
        '''                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                WHERE a.fecha >= ? AND a.fecha <= ? 
                AND a.estado IN ('EXTRA', 'OK', 'DESBORDE_LEY88', 'H.E_BOLSA')
                AND a.horas_trabajadas > a.horas_teoricas
                AND e.activo = 1 {area_condition}''',
        '''                FROM asistencias a
                JOIN empleados e ON a.empleado_id = e.id
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas ar ON ha.area_id = ar.id
                WHERE a.fecha >= ? AND a.fecha <= ? 
                AND a.estado IN ('EXTRA', 'OK', 'DESBORDE_LEY88', 'H.E_BOLSA')
                AND a.horas_trabajadas > a.horas_teoricas
                AND e.activo = 1 {area_condition}'''
    )


    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

replace_in_file(r"c:\\Users\\danie\\Proyectos_Python\\Asistencia\\backend\\services\\dashboard_service.py")
