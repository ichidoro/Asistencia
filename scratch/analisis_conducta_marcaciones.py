import sys
import os
import asyncio
from datetime import datetime

sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\danie\Proyectos_Python\Asistencia\.env")

from backend.core.database import db

async def analyze_clockings():
    await db.connect()
    
    print("==================================================================")
    print("ANALISIS DE LA CONDUCTA DE LAS MARCACIONES (LOGS_RAW)")
    print("==================================================================")
    
    # 1. Total de marcaciones crudas
    total_raw = await db.fetch_one("SELECT COUNT(*) as c FROM logs_raw")
    print(f"Total de marcaciones en logs_raw: {total_raw['c'] if total_raw else 0}")
    
    # 2. Distribución horaria (a qué horas se marca más)
    print("\n1. Distribucion por Hora del Dia (Top 10 horas con mas actividad):")
    query_hours = """
        SELECT SUBSTR(fecha_hora, 12, 2) as hora, COUNT(*) as cantidad
        FROM logs_raw
        GROUP BY hora
        ORDER BY cantidad DESC
    """
    hours_dist = await db.fetch_all(query_hours)
    for row in hours_dist:
        hora = row['hora']
        cantidad = row['cantidad']
        bar = "#" * min(int(cantidad / 10) + 1, 30) # representación visual simple con #
        print(f"   Hora {hora} : {cantidad:>4} marcaciones {bar}")
        
    # 3. Análisis de duplicados o marcaciones continuas (Duplicados en menos de 5 minutos)
    print("\n2. Analisis de Marcaciones Continuas (Duplicados en menos de 5 minutos):")
    query_duplicates = """
        SELECT lr1.empleado_id, e.nombre, e.apellido_paterno, lr1.fecha_hora as hora1, lr2.fecha_hora as hora2, lr1.tipo
        FROM logs_raw lr1
        JOIN logs_raw lr2 ON lr1.empleado_id = lr2.empleado_id 
                         AND lr1.rowid < lr2.rowid
                         AND SUBSTR(lr1.fecha_hora, 1, 10) = SUBSTR(lr2.fecha_hora, 1, 10)
        JOIN empleados e ON lr1.empleado_id = e.id
        WHERE 
            (strftime('%s', lr2.fecha_hora) - strftime('%s', lr1.fecha_hora)) BETWEEN 1 AND 300
        ORDER BY lr1.fecha_hora DESC
        LIMIT 10
    """
    duplicates = await db.fetch_all(query_duplicates)
    if duplicates:
        print(f"   Encontradas marcaciones muy seguidas. Ejemplo de los ultimos 10 casos:")
        for dup in duplicates:
            # Reemplazar acentos para evitar problemas de codificación si es necesario
            nombre = dup['nombre'].encode('ascii', 'ignore').decode('ascii')
            apellido = dup['apellido_paterno'].encode('ascii', 'ignore').decode('ascii')
            print(f"   - {nombre} {apellido} (ID: {dup['empleado_id']})")
            print(f"     Marcacion 1: {dup['hora1']} ({dup['tipo']})")
            print(f"     Marcacion 2: {dup['hora2']}")
            print(f"     Diferencia: en menos de 5 minutos")
    else:
        print("   No se detectaron duplicados inmediatos en la muestra.")
        
    # 4. Distribución por día de la semana
    print("\n3. Distribucion por Dia de la Semana:")
    query_days = """
        SELECT 
            CASE strftime('%w', fecha_hora)
                WHEN '0' THEN 'Domingo'
                WHEN '1' THEN 'Lunes'
                WHEN '2' THEN 'Martes'
                WHEN '3' THEN 'Miercoles'
                WHEN '4' THEN 'Jueves'
                WHEN '5' THEN 'Viernes'
                WHEN '6' THEN 'Sabado'
            END as dia_nom,
            COUNT(*) as cantidad
        FROM logs_raw
        GROUP BY strftime('%w', fecha_hora)
        ORDER BY strftime('%w', fecha_hora) ASC
    """
    days_dist = await db.fetch_all(query_days)
    for day in days_dist:
        print(f"   {day['dia_nom']:<10} : {day['cantidad']:>4} marcaciones")
        
    # 5. Análisis de marcas consecutivas del mismo tipo (ej. Entrada seguido de Entrada)
    print("\n4. Secuencia Anomala de Tipos de Marcacion (Ej: Entrada -> Entrada):")
    query_sequence = """
        WITH OrderedLogs AS (
            SELECT 
                empleado_id, 
                fecha_hora, 
                tipo,
                LAG(tipo, 1) OVER (PARTITION BY empleado_id ORDER BY fecha_hora) as tipo_prev,
                LAG(fecha_hora, 1) OVER (PARTITION BY empleado_id ORDER BY fecha_hora) as fecha_prev
            FROM logs_raw
        )
        SELECT ol.*, e.nombre, e.apellido_paterno
        FROM OrderedLogs ol
        JOIN empleados e ON ol.empleado_id = e.id
        WHERE ol.tipo = ol.tipo_prev AND SUBSTR(ol.fecha_hora, 1, 10) = SUBSTR(ol.fecha_prev, 1, 10)
        LIMIT 10
    """
    anomalous = await db.fetch_all(query_sequence)
    if anomalous:
        print("   Ejemplos de marcas sucesivas del mismo tipo en el mismo dia:")
        for row in anomalous:
            nombre = row['nombre'].encode('ascii', 'ignore').decode('ascii')
            apellido = row['apellido_paterno'].encode('ascii', 'ignore').decode('ascii')
            print(f"   - {nombre} {apellido} (ID: {row['empleado_id']})")
            print(f"     Marca previa: {row['fecha_prev']} ({row['tipo_prev']})")
            print(f"     Marca actual: {row['fecha_hora']} ({row['tipo']})")
    else:
        print("   No hay secuencias repetitivas anomalas en el mismo dia.")

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(analyze_clockings())
