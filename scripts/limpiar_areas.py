import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Añadir el directorio raíz al path para poder importar módulos del backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.core.database import HybridDatabase

async def limpiar_areas():
    print("📁 Iniciando conexión con la base de datos (Híbrida: Local + Turso Cloud)...")
    db = HybridDatabase()
    
    try:
        await db.connect()
        
        print("🧹 Ejecutando limpieza de la tabla 'areas'...")
        
        script_sql = """
            DELETE FROM areas;
            DELETE FROM sqlite_sequence WHERE name='areas';
        """
        
        # Ejecutamos el script de eliminación
        await db.execute_script(script_sql)
        
        print("☁️ Forzando sincronización hacia Turso Cloud...")
        # Forzamos sincronización a la nube explícitamente para que impacte el server Turso
        await db.sync_to_cloud_explicit()
        
        print("✅ ¡Éxito! La tabla 'areas' ha sido vaciada completamente, tanto a nivel local como en Turso Cloud.")
        print("💡 Ahora puedes ir a la aplicación e iniciar una sincronización para descargar las áreas frescas desde BioAlba.")
        
    except Exception as e:
        print(f"❌ Ocurrió un error al limpiar las áreas: {e}")
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(limpiar_areas())
