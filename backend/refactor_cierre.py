import os

def replace_in_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # filtro_area
    content = content.replace(
        'filtro_area = " AND e.area = ?"',
        'filtro_area = " AND ar.nombre = ?"'
    )

    # query_he
    content = content.replace(
        '''            FROM horas_extras he
            JOIN empleados e ON he.empleado_id = e.id
            WHERE he.fecha BETWEEN ? AND ?''',
        '''            FROM horas_extras he
            JOIN empleados e ON he.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE he.fecha BETWEEN ? AND ?'''
    )

    # query_anomalias
    content = content.replace(
        '''                   e.area
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            WHERE a.fecha BETWEEN ? AND ?''',
        '''                   ar.nombre AS area
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE a.fecha BETWEEN ? AND ?'''
    )

    # query_en_curso
    content = content.replace(
        '''                   e.area
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            WHERE a.fecha BETWEEN ? AND ?''',
        '''                   ar.nombre AS area
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE a.fecha BETWEEN ? AND ?'''
    )

    # query_ina
    content = content.replace(
        '''                   e.area
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            WHERE a.fecha BETWEEN ? AND ?''',
        '''                   ar.nombre AS area
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE a.fecha BETWEEN ? AND ?'''
    )

    # query_resumen
    content = content.replace(
        '''            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            WHERE a.fecha BETWEEN ? AND ?
            {filtro_area}''',
        '''            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE a.fecha BETWEEN ? AND ?
            {filtro_area}'''
    )

    # query_he_aprobadas
    content = content.replace(
        '''            FROM horas_extras he
            JOIN empleados e ON he.empleado_id = e.id
            WHERE he.fecha BETWEEN ? AND ?
              AND he.estado = 'APROBADO'
            {filtro_area}''',
        '''            FROM horas_extras he
            JOIN empleados e ON he.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE he.fecha BETWEEN ? AND ?
              AND he.estado = 'APROBADO'
            {filtro_area}'''
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

replace_in_file(r"c:\\Users\\danie\\Proyectos_Python\\Asistencia\\backend\\services\\cierre_service.py")
