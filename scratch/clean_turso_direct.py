import sys
import os
import asyncio

sys.path.append(r"c:\Users\danie\Proyectos_Python\Asistencia")

from dotenv import load_dotenv
load_dotenv(r"c:\Users\danie\Proyectos_Python\Asistencia\.env")

from backend.core.database import db

async def clean_turso():
    print("Conectando a Turso Cloud...")
    await db.connect()
    
    # We are in Pure Cloud Mode, so this will run directly against Turso Cloud.
    print("\n--- INICIANDO LIMPIEZA DE REGISTROS PREVIOS A 2026-04-26 ---")
    
    # 1. Asignaciones de turnos
    print("1. Eliminando asignaciones de turnos anteriores al 2026-04-26...")
    q1 = "DELETE FROM asignacion_turnos WHERE fecha_inicio < '2026-04-26'"
    await db.execute(q1)
    print("   -> Completado.")

    # 2. Asistencias
    print("2. Eliminando asistencias anteriores al 2026-04-26...")
    q2 = "DELETE FROM asistencias WHERE fecha < '2026-04-26'"
    await db.execute(q2)
    print("   -> Completado.")

    # 3. Horas extras
    print("3. Eliminando horas extras anteriores al 2026-04-26...")
    q3 = "DELETE FROM horas_extras WHERE fecha < '2026-04-26'"
    await db.execute(q3)
    print("   -> Completado.")

    # 4. Logs raw (marcaciones crudas)
    print("4. Eliminando marcaciones crudas (logs_raw) anteriores al 2026-04-26...")
    q4 = "DELETE FROM logs_raw WHERE SUBSTR(fecha_hora, 1, 10) < '2026-04-26'"
    await db.execute(q4)
    print("   -> Completado.")

    print("\nLimpieza en Turso Cloud finalizada con éxito.")
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(clean_turso())
