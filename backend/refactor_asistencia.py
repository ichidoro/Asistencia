import os

def replace_in_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # _get_raw_asistencias
    content = content.replace(
        '''            SELECT a.*, e.nombre, e.apellido_paterno, e.apellido_materno, e.area, e.rut,
                   he.estado as estado_he, he.minutos_autorizados as minutos_extra_autorizados
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN horas_extras he ON he.empleado_id = a.empleado_id AND he.fecha = a.fecha
            WHERE a.fecha BETWEEN ? AND ?''',
        '''            SELECT a.*, e.nombre, e.apellido_paterno, e.apellido_materno, ar.nombre as area, e.rut,
                   he.estado as estado_he, he.minutos_autorizados as minutos_extra_autorizados
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            LEFT JOIN horas_extras he ON he.empleado_id = a.empleado_id AND he.fecha = a.fecha
            WHERE a.fecha BETWEEN ? AND ?'''
    )
    content = content.replace('q += " AND e.area = ?"', 'q += " AND ar.nombre = ?"')
    content = content.replace('q += f" AND e.area IN ({placeholders})"', 'q += f" AND ar.nombre IN ({placeholders})"')

    # get_matrix_data_with_projections
    content = content.replace(
        '''            SELECT DISTINCT e.*
            FROM empleados e
            INNER JOIN asignacion_turnos ast ON e.id = ast.empleado_id
            WHERE e.activo = 1
              AND ast.fecha_inicio <= ? AND (ast.fecha_fin IS NULL OR ast.fecha_fin >= ?)''',
        '''            SELECT DISTINCT e.*, ar.nombre as area
            FROM empleados e
            INNER JOIN asignacion_turnos ast ON e.id = ast.empleado_id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE e.activo = 1
              AND ast.fecha_inicio <= ? AND (ast.fecha_fin IS NULL OR ast.fecha_fin >= ?)'''
    )
    content = content.replace('q_emp += " AND e.area = ?"', 'q_emp += " AND ar.nombre = ?"')
    content = content.replace('q_emp += f" AND e.area IN ({ph})"', 'q_emp += f" AND ar.nombre IN ({ph})"')


    # get_period_summary_rrhh
    content = content.replace(
        '''            SELECT e.id, e.nombre, e.apellido_paterno, e.apellido_materno, e.area,
                   e.rut,
                   COALESCE((SELECT SUM(h.minutos_autorizados) FROM horas_extras h
                             WHERE h.empleado_id = e.id AND h.fecha BETWEEN ? AND ?
                             AND h.estado = 'APROBADO'), 0) as total_he_aprobado
            FROM empleados e
            WHERE e.activo = 1''',
        '''            SELECT e.id, e.nombre, e.apellido_paterno, e.apellido_materno, ar.nombre as area,
                   e.rut,
                   COALESCE((SELECT SUM(h.minutos_autorizados) FROM horas_extras h
                             WHERE h.empleado_id = e.id AND h.fecha BETWEEN ? AND ?
                             AND h.estado = 'APROBADO'), 0) as total_he_aprobado
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE e.activo = 1'''
    )
    content = content.replace('q += " AND e.area = ?"', 'q += " AND ar.nombre = ?"')

    # get_resumen_cierre_global
    content = content.replace(
        '''            SELECT 
                COALESCE((SELECT SUM(h.minutos_autorizados) FROM horas_extras h
                          JOIN empleados e2 ON h.empleado_id = e2.id
                          WHERE h.fecha BETWEEN ? AND ? AND e2.activo = 1
                          AND h.estado = 'APROBADO'), 0) as total_he_aprobado,
                SUM(CASE WHEN a.minutos_deuda > 0 THEN a.minutos_deuda ELSE 0 END) as total_deuda
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            WHERE a.fecha BETWEEN ? AND ?
              AND e.activo = 1''',
        '''            SELECT 
                COALESCE((SELECT SUM(h.minutos_autorizados) FROM horas_extras h
                          JOIN empleados e2 ON h.empleado_id = e2.id
                          LEFT JOIN historial_areas ha2 ON e2.id = ha2.empleado_id AND ha2.es_actual = 1 AND ha2.validado = 1
                          LEFT JOIN areas ar2 ON ha2.area_id = ar2.id
                          WHERE h.fecha BETWEEN ? AND ? AND e2.activo = 1
                          AND h.estado = 'APROBADO' {area_condition_sub}), 0) as total_he_aprobado,
                SUM(CASE WHEN a.minutos_deuda > 0 THEN a.minutos_deuda ELSE 0 END) as total_deuda
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE a.fecha BETWEEN ? AND ?
              AND e.activo = 1'''
    )
    
    # We need to manually fix the parameters of get_resumen_cierre_global
    content = content.replace(
        '''        params = [fecha_inicio, fecha_fin, fecha_inicio, fecha_fin]
        if area:
            q_sum += " AND e.area = ?"
            params.append(area)''',
        '''        params = [fecha_inicio, fecha_fin]
        area_cond_sub = ""
        if area:
            area_cond_sub = " AND ar2.nombre = ?"
            params.append(area)
        q_sum = q_sum.format(area_condition_sub=area_cond_sub)
        params.extend([fecha_inicio, fecha_fin])
        
        if area:
            q_sum += " AND ar.nombre = ?"
            params.append(area)'''
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

replace_in_file(r"c:\\Users\\danie\\Proyectos_Python\\Asistencia\\backend\\services\\asistencia_service.py")
