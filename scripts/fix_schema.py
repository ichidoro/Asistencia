import sqlite3
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

db_path = "data/local_db/asistencia_local.db"

def fix_schema():
    print("Iniciando reparación de esquema SQLite...")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # We must disable foreign keys to alter tables
    cursor.execute("PRAGMA foreign_keys=OFF;")
    
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND sql LIKE '%empleados_old%';")
    tables = cursor.fetchall()
    
    if not tables:
        print("✅ No se encontraron tablas con dependencias rotas a 'empleados_old'.")
    
    for table in tables:
        name = table['name']
        sql = table['sql']
        
        print(f"🔧 Reparando tabla: {name}...")
        
        # Replace 'empleados_old' with 'empleados'
        new_sql = sql.replace('"empleados_old"', 'empleados')
        new_sql = new_sql.replace('empleados_old', 'empleados')
        
        # We need to recreate the table
        # 1. Rename current table
        cursor.execute(f"ALTER TABLE {name} RENAME TO {name}_temp_fix;")
        
        # 2. Create new table with corrected sql
        cursor.execute(new_sql)
        
        # 3. Copy data
        cursor.execute(f"PRAGMA table_info({name})")
        columns = [col['name'] for col in cursor.fetchall()]
        col_names = ", ".join(columns)
        
        cursor.execute(f"INSERT INTO {name} ({col_names}) SELECT {col_names} FROM {name}_temp_fix;")
        
        # 4. Drop temp table
        cursor.execute(f"DROP TABLE {name}_temp_fix;")
        
        print(f"✅ Tabla {name} reparada correctamente!")
        
    conn.commit()
    cursor.execute("PRAGMA foreign_keys=ON;")
    conn.close()
    print("✨ Reparación finalizada con éxito. Ahora ya puedes correr limpiar_areas.py sin problemas.")

if __name__ == "__main__":
    fix_schema()
