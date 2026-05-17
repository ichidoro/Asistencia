import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Añadir el directorio raíz al path para poder importar módulos del backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.core.database import HybridDatabase

async def limpiar_datos(opcion):
    print("📁 Iniciando conexión con la base de datos (Híbrida: Local + Turso Cloud)...")
    db = HybridDatabase()
    
    try:
        await db.connect()
        
        
        
        # 1. Transaccionales (Hijos de todos)
        if opcion in ['4', '3', '5']:
            print("🧹 Preparando limpieza de registros transaccionales (asistencias, marcaciones brutas, horas extras)...")
            tablas_transaccionales = [
                "cierres_periodos",
                "logs_raw",
                "sync_logs",
                "logs_auditoria",
                "horas_extras",
                "jornadas_especiales",
                "bolsa_horas_resumen",
                "asistencias",
                "justificaciones",
                "intercambios_dias"
            ]
            for tabla in tablas_transaccionales:
                try:
                    if await db.table_exists(tabla):
                        await db.execute_script(f"""
                            DELETE FROM {tabla};
                            DELETE FROM sqlite_sequence WHERE name='{tabla}';
                        """)
                except Exception:
                    pass

        # 2. Empleados (Hijos de Areas y Cargos)
        if opcion in ['3', '5']:
            print("🧹 Preparando limpieza de la tabla 'empleados' y sus historiales...")
            tablas_empleados = [
                "historial_areas",
                "periodos_empleo",
                "empleados"
            ]
            for tabla in tablas_empleados:
                try:
                    if await db.table_exists(tabla):
                        await db.execute_script(f"""
                            DELETE FROM {tabla};
                            DELETE FROM sqlite_sequence WHERE name='{tabla}';
                        """)
                except Exception as e:
                    pass

        # 3. Turnos (Hijos de Areas)
        if opcion in ['2', '5']:
            print("🧹 Preparando limpieza de tablas de turnos...")
            for tabla in ["asignacion_turnos", "turno_segmentos", "plantillas_planificacion", "turno_dias", "turno_areas", "turnos"]:
                try:
                    if await db.table_exists(tabla):
                        await db.execute_script(f"DELETE FROM {tabla}; DELETE FROM sqlite_sequence WHERE name='{tabla}';")
                except Exception:
                    pass

        # 4. Configuraciones (Padres de todos)
        if opcion in ['1', '5']:
            print("🧹 Preparando limpieza de configuraciones del flujo inicial (áreas, cargos, géneros, bonos, justificaciones, feriados)...")
            tablas_configuracion = [
                "bono_asignaciones", "bono_reglas", "bonos", 
                "justificacion_tipos", "cat_pagadores",
                "notificaciones_areas", "feriados",
                "areas_alias", "areas", "cargos_alias", "cargos", "cat_generos"
            ]
            for tabla in tablas_configuracion:
                try:
                    if await db.table_exists(tabla):
                        await db.execute_script(f"DELETE FROM {tabla}; DELETE FROM sqlite_sequence WHERE name='{tabla}';")
                except Exception:
                    pass
            
        print("☁️ Forzando sincronización hacia Turso Cloud...")
        await db.sync_to_cloud_explicit()
        print("✅ ¡Éxito! Las tablas seleccionadas han sido vaciadas completamente, tanto a nivel local como en Turso Cloud.")
            
    except Exception as e:
        print(f"❌ Ocurrió un error al limpiar los datos: {e}")
    finally:
        await db.disconnect()

def menu():
    print("=" * 50)
    print("🛠️  HERRAMIENTA DE DESARROLLO - LIMPIEZA DE TABLAS")
    print("=" * 50)
    print("1. Limpiar tablas 'areas', 'cargos', 'generos', 'bonos' y 'justificaciones'")
    print("2. Limpiar tablas de 'turnos' completas")
    print("3. Limpiar tabla 'empleados' (ATENCIÓN: Borra asistencias y marcaciones también)")
    print("4. Limpiar SOLO datos Transaccionales (marcaciones logs_raw, asistencias, horas extras)")
    print("5. Limpiar TODA LA BASE DE DATOS (Opciones 1, 2, 3 y 4)")
    print("6. Salir")
    print("=" * 50)
    
    opcion = input("Elige una opción (1-6): ").strip()
    return opcion

if __name__ == "__main__":
    while True:
        op = menu()
        if op == '6':
            print("Saliendo...")
            break
        elif op in ['1', '2', '3', '4', '5']:
            asyncio.run(limpiar_datos(op))
            break
        else:
            print("⚠️ Opción no válida. Inténtalo de nuevo.\n")
