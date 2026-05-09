import sys
import os
import asyncio
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from backend.core.database import db

async def migrate():
    print("Iniciando migración de áreas...")
    await db.connect()
    
    # 1. Crear areas
    print("Creando tabla areas...")
    await db.execute("""
    CREATE TABLE IF NOT EXISTS areas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    
    # 2. Crear areas_alias
    print("Creando tabla areas_alias...")
    await db.execute("""
    CREATE TABLE IF NOT EXISTS areas_alias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alias TEXT NOT NULL UNIQUE,
        area_id INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (area_id) REFERENCES areas (id) ON DELETE CASCADE
    )
    """)
    
    # Check if we need to migrate
    cols = await db.get_column_names("empleados")
    if "area_id" in cols:
        print("La tabla empleados ya tiene area_id. Abortando migración para evitar duplicidad.")
        return

    # 3. Insertar areas únicas desde empleados
    print("Extrayendo áreas únicas actuales...")
    areas_actuales = await db.fetch_all("SELECT DISTINCT area FROM empleados WHERE area IS NOT NULL AND area != ''")
    for a in areas_actuales:
        try:
            await db.execute("INSERT OR IGNORE INTO areas (nombre) VALUES (?)", (a['area'],))
        except Exception as e:
            pass

    # 4. Renombrar y recrear empleados
    print("Renombrando empleados a empleados_old...")
    await db.execute("ALTER TABLE empleados RENAME TO empleados_old")
    
    print("Creando nueva tabla empleados con area_id...")
    await db.execute("""
    CREATE TABLE empleados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rut TEXT NOT NULL UNIQUE,
        nombre TEXT NOT NULL,
        apellido_paterno TEXT NOT NULL,
        apellido_materno TEXT NOT NULL,
        cargo TEXT,
        area_id INTEGER,
        compania TEXT,
        email TEXT,
        telefono TEXT,
        genero TEXT,
        activo INTEGER DEFAULT 1,
        fecha_nacimiento TEXT,
        fecha_ingreso TEXT,
        fecha_salida TEXT,
        tipo_contrato TEXT DEFAULT 'Indefinido',
        cant_contratos INTEGER DEFAULT 1,
        decision_vencimiento TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (area_id) REFERENCES areas (id)
    )
    """)
    
    print("Migrando datos de empleados_old a empleados...")
    await db.execute("""
    INSERT INTO empleados (
        id, rut, nombre, apellido_paterno, apellido_materno, cargo, compania, email, telefono, genero, activo,
        fecha_nacimiento, fecha_ingreso, fecha_salida, tipo_contrato, cant_contratos, decision_vencimiento,
        created_at, updated_at, area_id
    )
    SELECT 
        e.id, e.rut, e.nombre, e.apellido_paterno, e.apellido_materno, e.cargo, e.compania, e.email, e.telefono, e.genero, e.activo,
        e.fecha_nacimiento, e.fecha_ingreso, e.fecha_salida, e.tipo_contrato, e.cant_contratos, e.decision_vencimiento,
        e.created_at, e.updated_at, a.id
    FROM empleados_old e
    LEFT JOIN areas a ON e.area = a.nombre
    """)
    
    print("Renombrando historial_areas a historial_areas_old...")
    await db.execute("ALTER TABLE historial_areas RENAME TO historial_areas_old")
    
    print("Creando nueva tabla historial_areas con area_id...")
    await db.execute("""
    CREATE TABLE historial_areas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empleado_id INTEGER NOT NULL,
        area_id INTEGER NOT NULL,
        fecha_desde TEXT NOT NULL,
        fecha_hasta TEXT,
        es_actual INTEGER DEFAULT 1,
        validado INTEGER DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (empleado_id) REFERENCES empleados (id),
        FOREIGN KEY (area_id) REFERENCES areas (id)
    )
    """)
    
    print("Migrando datos de historial_areas_old a historial_areas...")
    await db.execute("""
    INSERT INTO historial_areas (
        id, empleado_id, fecha_desde, fecha_hasta, es_actual, validado, created_at, area_id
    )
    SELECT 
        h.id, h.empleado_id, h.fecha_desde, h.fecha_hasta, h.es_actual, h.validado, h.created_at, a.id
    FROM historial_areas_old h
    LEFT JOIN areas a ON h.area = a.nombre
    """)
    
    print("Limpiando tablas viejas...")
    await db.execute("DROP TABLE empleados_old")
    await db.execute("DROP TABLE historial_areas_old")
    
    print("Recreando índices...")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_empleados_rut ON empleados(rut)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_empleados_activo ON empleados(activo)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_empleados_area_id ON empleados(area_id)")
    
    await db.execute("CREATE INDEX IF NOT EXISTS idx_historial_emp ON historial_areas(empleado_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_historial_area_id ON historial_areas(area_id)")
    
    # Limpiar schema cache
    await db.clear_schema_cache()
    
    print("✅ Migración completada exitosamente!")

if __name__ == "__main__":
    asyncio.run(migrate())
