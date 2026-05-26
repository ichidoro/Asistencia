import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.database import Database

async def main():
    db_path = "data/local_db/asistencia_local.db"
    db = Database(db_path)
    await db.connect()
    
    fecha_inicio = "2026-04-26"
    fecha_fin = "2026-05-25"
    area = "PRODUCCION"
    
    # 1. Obtener empleados activos en PRODUCCION en ese periodo
    q_emp = """
        SELECT DISTINCT e.id, e.nombre, e.apellido_paterno, e.apellido_materno, e.rut
        FROM empleados e
        JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.validado = 1
            AND ? >= ha.fecha_desde
            AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR ? <= ha.fecha_hasta)
        JOIN areas ar ON ha.area_id = ar.id
        WHERE e.activo = 1 AND ar.nombre = ?
        ORDER BY e.apellido_paterno, e.apellido_materno, e.nombre
    """
    employees = await db.fetch_all(q_emp, (fecha_fin, fecha_inicio, area))
    emp_ids = [emp['id'] for emp in employees]
    
    if not emp_ids:
        print(f"No se encontraron empleados para el área {area} en el periodo.")
        await db.disconnect()
        return

    # 2. Consultar asistencias con deudas para estos empleados
    placeholders = ",".join("?" for _ in emp_ids)
    q_asist = f"""
        SELECT a.empleado_id, a.fecha, a.minutos_deuda, a.minutos_atraso, 
               a.minutos_exceso_colacion, a.minutos_salida_adelantada, a.minutos_permiso_personal_deuda,
               a.deuda_condonada, a.estado
        FROM asistencias a
        WHERE a.empleado_id IN ({placeholders})
          AND a.fecha BETWEEN ? AND ?
        ORDER BY a.empleado_id, a.fecha
    """
    asist_rows = await db.fetch_all(q_asist, tuple(emp_ids) + (fecha_inicio, fecha_fin))
    
    # 3. Consultar horas extras aprobadas
    q_he = f"""
        SELECT he.empleado_id, he.fecha, he.minutos_autorizados, he.estado
        FROM horas_extras he
        WHERE he.empleado_id IN ({placeholders})
          AND he.fecha BETWEEN ? AND ?
          AND he.estado = 'APROBADO'
    """
    he_rows = await db.fetch_all(q_he, tuple(emp_ids) + (fecha_inicio, fecha_fin))
    
    # 4. Consultar compensaciones
    q_comp = f"""
        SELECT c.empleado_id, c.fecha_inasistencia, c.minutos
        FROM compensaciones_he_inasistencia c
        WHERE c.empleado_id IN ({placeholders})
          AND c.fecha_inasistencia BETWEEN ? AND ?
    """
    comp_rows = await db.fetch_all(q_comp, tuple(emp_ids) + (fecha_inicio, fecha_fin))

    # Mapeo de datos
    asist_map = {}
    for r in asist_rows:
        emp_id = r['empleado_id']
        if emp_id not in asist_map:
            asist_map[emp_id] = []
        asist_map[emp_id].append(r)
        
    he_map = {}
    for r in he_rows:
        emp_id = r['empleado_id']
        if emp_id not in he_map:
            he_map[emp_id] = []
        he_map[emp_id].append(r)
        
    comp_map = {}
    for r in comp_rows:
        emp_id = r['empleado_id']
        if emp_id not in comp_map:
            comp_map[emp_id] = []
        comp_map[emp_id].append(r)

    # Generar Reporte Markdown
    report_lines = []
    report_lines.append(f"# Auditoría de Deudas y Balanza de Minutos - Área {area}")
    report_lines.append(f"**Periodo**: {fecha_inicio} al {fecha_fin}\n")
    report_lines.append("Este informe contiene un desglose detallado de quién generó las deudas, en qué fechas, qué conceptos las causaron y cómo se balancean individualmente con sus horas extras y compensaciones.\n")
    
    report_lines.append("## Resumen General del Área")
    
    # Totales del área
    tot_he_apr = 0.0
    tot_deuda_orig = 0.0
    tot_comp = 0.0
    tot_deuda_neta = 0.0
    tot_he_neta = 0.0
    
    emp_details = []
    
    for emp in employees:
        emp_id = emp['id']
        rut = emp['rut']
        nombre = f"{emp['apellido_paterno']} {emp.get('apellido_materno') or ''} {emp['nombre']}".strip().replace('  ', ' ')
        
        # Filtrar deudas asistencias
        deudas = asist_map.get(emp_id, [])
        hes = he_map.get(emp_id, [])
        comps = comp_map.get(emp_id, [])
        
        emp_he_total = sum(h['minutos_autorizados'] for h in hes)
        emp_comp_total = sum(c['minutos'] for c in comps)
        
        emp_deuda_total = 0.0
        emp_atr = 0.0
        emp_col = 0.0
        emp_sad = 0.0
        emp_per = 0.0
        
        detalles_dias = []
        
        # Mapear deudas diarias
        for d in deudas:
            condonada = (d['deuda_condonada'] or 0) > 0
            d_total = 0 if condonada else (d['minutos_deuda'] or 0)
            
            d_atr = 0 if condonada else (d['minutos_atraso'] or 0)
            d_col = d['minutos_exceso_colacion'] or 0
            d_sad = 0 if condonada else (d['minutos_salida_adelantada'] or 0)
            d_per = d['minutos_permiso_personal_deuda'] or 0
            
            raw_total = d_atr + d_col + d_sad + d_per
            
            # Prorrateo diario si minutes_deuda es menor por condonación o ajuste
            day_col = 0
            day_per = 0
            day_atr = 0
            day_sad = 0
            
            if d_total > 0 and raw_total > 0:
                if d_total >= raw_total:
                    day_col = d_col
                    day_per = d_per
                    day_atr = d_atr
                    day_sad = d_sad
                else:
                    factor = d_total / raw_total
                    day_col = d_col * factor
                    day_per = d_per * factor
                    day_atr = d_atr * factor
                    day_sad = d_sad * factor
            
            emp_deuda_total += d_total
            emp_atr += day_atr
            emp_col += day_col
            emp_sad += day_sad
            emp_per += day_per
            
            if d_total > 0 or raw_total > 0:
                detalles_dias.append({
                    'fecha': d['fecha'],
                    'estado': d['estado'],
                    'total': d_total,
                    'atraso': day_atr,
                    'colacion': day_col,
                    'salida': day_sad,
                    'permiso': day_per
                })
        
        # Saldo Neto empleado
        saldo_neto = emp_he_total - emp_deuda_total - emp_comp_total
        
        tot_he_apr += emp_he_total
        tot_deuda_orig += emp_deuda_total
        tot_comp += emp_comp_total
        
        if saldo_neto > 0:
            tot_he_neta += saldo_neto
            deuda_neta_emp = 0.0
        else:
            tot_deuda_neta += abs(saldo_neto)
            deuda_neta_emp = abs(saldo_neto)
            
        emp_details.append({
            'rut': rut,
            'nombre': nombre,
            'he_apr': emp_he_total,
            'deuda_orig': emp_deuda_total,
            'comp': emp_comp_total,
            'saldo': saldo_neto,
            'deuda_neta': deuda_neta_emp,
            'atr': emp_atr,
            'col': emp_col,
            'sad': emp_sad,
            'per': emp_per,
            'detalles_dias': detalles_dias
        })
        
    report_lines.append(f"* **Total Colaboradores**: {len(employees)}")
    report_lines.append(f"* **Total Horas Extras Aprobadas**: {round(tot_he_apr/60.0, 2)} hrs ({tot_he_apr} min)")
    report_lines.append(f"* **Total Deuda de Asistencia**: {round(tot_deuda_orig/60.0, 2)} hrs ({tot_deuda_orig} min)")
    report_lines.append(f"* **Total Compensaciones**: {round(tot_comp/60.0, 2)} hrs ({tot_comp} min)")
    report_lines.append(f"* **Total Horas Extras Netas a Pago (Suma de saldos positivos)**: {round(tot_he_neta/60.0, 2)} hrs ({tot_he_neta} min)")
    report_lines.append(f"* **Total Deuda Neta Restante (Suma de saldos negativos)**: {round(tot_deuda_neta/60.0, 2)} hrs ({tot_deuda_neta} min)\n")
    
    report_lines.append("## Tabla de Balance por Empleado (Masa de Minutos)")
    report_lines.append("| Colaborador | RUT | HE Aprobadas (min) | Deuda (min) | Compensaciones (min) | Saldo Neto (min) | HE a Pago | Deuda Neta |")
    report_lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    
    for ed in emp_details:
        sign = "+" if ed['saldo'] > 0 else ("-" if ed['saldo'] < 0 else "")
        he_pago = ed['saldo'] if ed['saldo'] > 0 else 0
        d_neta = abs(ed['saldo']) if ed['saldo'] < 0 else 0
        report_lines.append(
            f"| {ed['nombre']} | {ed['rut']} | {ed['he_apr']:.0f} | {ed['deuda_orig']:.0f} | {ed['comp']:.0f} | {sign}{abs(ed['saldo']):.0f} | {he_pago:.0f} | {d_neta:.0f} |"
        )
        
    report_lines.append("\n## Detalle de Origen de Deudas de Empleados con Saldo Deudor")
    
    for ed in emp_details:
        if ed['saldo'] < 0:
            report_lines.append(f"\n### {ed['nombre']} (RUT: {ed['rut']})")
            report_lines.append(f"* **Deuda Neta Restante**: {ed['deuda_neta']:.0f} min ({round(ed['deuda_neta']/60.0, 2)} hrs)")
            
            # Prorratear
            raw_total = ed['atr'] + ed['col'] + ed['sad'] + ed['per']
            if raw_total > 0:
                factor = ed['deuda_neta'] / raw_total
                net_atr = ed['atr'] * factor
                net_col = ed['col'] * factor
                net_sad = ed['sad'] * factor
                net_per = ed['per'] * factor
            else:
                net_atr = ed['deuda_neta']
                net_col = net_sad = net_per = 0.0
                
            report_lines.append("#### Desglose de Deuda Neta Restante:")
            report_lines.append(f"* **Atrasos Netos**: {net_atr:.1f} min ({round(net_atr/60.0, 2)} hrs)")
            report_lines.append(f"* **Exceso de Colacion**: {net_col:.1f} min ({round(net_col/60.0, 2)} hrs)")
            report_lines.append(f"* **Salidas Adelantadas**: {net_sad:.1f} min ({round(net_sad/60.0, 2)} hrs)")
            report_lines.append(f"* **Permisos con Deuda**: {net_per:.1f} min ({round(net_per/60.0, 2)} hrs)")
            
            report_lines.append("\n#### Historial Diario de Deudas (Días donde generó deuda):")
            report_lines.append("| Fecha | Estado | Deuda Diaria (min) | Atraso | Exceso Colación | Salida Adel. | Permiso |")
            report_lines.append("| --- | --- | --- | --- | --- | --- | --- |")
            for dd in ed['detalles_dias']:
                report_lines.append(
                    f"| {dd['fecha']} | {dd['estado']} | {dd['total']:.0f} | {dd['atraso']:.0f} | {dd['colacion']:.0f} | {dd['salida']:.0f} | {dd['permiso']:.0f} |"
                )
                
    # Escribir reporte a un archivo markdown
    out_path = os.path.join("brain", "c54c6ddd-3bf3-4591-9494-feb09821c7d3", "deudas_analisis_produccion.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    print(f"Report generated successfully at: {out_path}")
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
