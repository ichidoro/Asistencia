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
        
        script_sql = ""
        
        if opcion in ['1', '3']:
            print("🧹 Preparando limpieza de la tabla 'areas', 'areas_alias', 'cargos' y 'cargos_alias'...")
            script_sql += """
                DELETE FROM areas_alias;
                DELETE FROM sqlite_sequence WHERE name='areas_alias';
                DELETE FROM areas;
                DELETE FROM sqlite_sequence WHERE name='areas';
                DELETE FROM cargos_alias;
                DELETE FROM sqlite_sequence WHERE name='cargos_alias';
                DELETE FROM cargos;
                DELETE FROM sqlite_sequence WHERE name='cargos';
            """
            
        if opcion in ['2', '3']:
            print("🧹 Preparando limpieza de tablas 'turnos' y 'turno_dias'...")
            script_sql += """
                DELETE FROM asignacion_turnos;
                DELETE FROM sqlite_sequence WHERE name='asignacion_turnos';
                DELETE FROM turno_dias;
                DELETE FROM sqlite_sequence WHERE name='turno_dias';
                DELETE FROM turno_areas;
                DELETE FROM sqlite_sequence WHERE name='turno_areas';
                DELETE FROM turnos;
                DELETE FROM sqlite_sequence WHERE name='turnos';
            """
            
        if script_sql:
            print("⏳ Ejecutando script de eliminación en SQLite...")
            await db.execute_script(script_sql)
            
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
    print("1. Limpiar tablas 'areas' y 'cargos'")
    print("2. Limpiar tablas de 'turnos' (turnos, turno_dias, turno_areas, asignacion_turnos)")
    print("3. Limpiar TODAS las anteriores (areas, cargos y turnos)")
    print("4. Salir")
    print("=" * 50)
    
    opcion = input("Elige una opción (1-4): ").strip()
    return opcion

if __name__ == "__main__":
    while True:
        op = menu()
        if op == '4':
            print("Saliendo...")
            break
        elif op in ['1', '2', '3']:
            asyncio.run(limpiar_datos(op))
            break
        else:
            print("⚠️ Opción no válida. Inténtalo de nuevo.\n")
