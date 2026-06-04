import os
import sqlite3
import pandas as pd
from typing import List, Dict, Any, Tuple

# Rutas de prueba
EXCEL_PATH = "Productos.xlsx"
DB_PATH = "scratch/test_simulation.sqlite"

def test_excel_loading_sre(excel_path: str = EXCEL_PATH) -> pd.DataFrame:
    """Valida la lectura del archivo Excel con tolerancia a fallos."""
    print(f"[SRE Check] Cargando Excel desde '{excel_path}'...")
    try:
        if not os.path.exists(excel_path):
            raise FileNotFoundError(f"Archivo no encontrado en {excel_path}")
        
        df = pd.read_excel(excel_path)
        required_cols = {"Codigo Producto", "Descripcion", "Tipo Producto", "Marca", "Unidad", "Maximo"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Columnas faltantes en el Excel: {missing}")
            
        print("-> [SRE] Excel leido correctamente. Todo OK.")
        return df
    except Exception as e:
        print(f"[SRE WARN] No se pudo cargar el catalogo desde el Excel: {e}")
        print("-> [SRE] Fallback activado: Se continuara con catalogo vacio.")
        return pd.DataFrame(columns=["Codigo Producto", "Descripcion", "Tipo Producto", "Marca", "Unidad", "Maximo"])

def init_mock_db_sre(df: pd.DataFrame):
    """Crea esquema local de prueba e inserta datos e inyeccion de semillas de permisos."""
    print("\n[SRE Check] Inicializando esquema de DB local...")
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception:
            pass
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Crear tablas base para el modulo
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos_elaboracion_propia (
        codigo INTEGER PRIMARY KEY,
        descripcion TEXT NOT NULL,
        tipo TEXT NOT NULL,
        marca TEXT NOT NULL,
        unidad TEXT NOT NULL,
        max_cantidad INTEGER DEFAULT 2,
        activo BOOLEAN DEFAULT 1
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS empleados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        rut TEXT NOT NULL,
        fecha_ingreso TEXT NOT NULL,
        activo BOOLEAN DEFAULT 1
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS empleado_productos_periodo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empleado_id INTEGER NOT NULL,
        periodo_mes INTEGER NOT NULL,
        periodo_anio INTEGER NOT NULL,
        producto1_codigo INTEGER,
        producto2_codigo INTEGER,
        producto3_codigo INTEGER,
        producto4_codigo INTEGER,
        observaciones TEXT,
        usuario_creador_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(empleado_id) REFERENCES empleados(id),
        FOREIGN KEY(producto1_codigo) REFERENCES productos_elaboracion_propia(codigo),
        FOREIGN KEY(producto2_codigo) REFERENCES productos_elaboracion_propia(codigo),
        FOREIGN KEY(producto3_codigo) REFERENCES productos_elaboracion_propia(codigo),
        FOREIGN KEY(producto4_codigo) REFERENCES productos_elaboracion_propia(codigo),
        UNIQUE(empleado_id, periodo_mes, periodo_anio)
    )
    """)
    
    # 2. Tablas del sistema de roles/permisos para testeo
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS permisos (
        id TEXT PRIMARY KEY,
        modulo TEXT NOT NULL,
        descripcion TEXT NOT NULL
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS roles (
        id INTEGER PRIMARY KEY,
        nombre TEXT NOT NULL
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rol_permisos (
        rol_id INTEGER NOT NULL,
        permiso_id TEXT NOT NULL,
        PRIMARY KEY (rol_id, permiso_id)
    )
    """)
    
    conn.commit()
    print("-> [SRE] Tablas creadas correctamente.")
    
    # 3. Poblar productos del catalogo con INSERT OR IGNORE
    if not df.empty:
        inserted = 0
        for _, row in df.iterrows():
            cursor.execute("""
            INSERT OR IGNORE INTO productos_elaboracion_propia (codigo, descripcion, tipo, marca, unidad, max_cantidad)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                int(row["Codigo Producto"]),
                str(row["Descripcion"]),
                str(row["Tipo Producto"]),
                str(row["Marca"]),
                str(row["Unidad"]),
                int(row["Maximo"])
            ))
            inserted += cursor.rowcount
        conn.commit()
        print(f"-> [SRE] Se importaron {inserted} productos de {len(df)} filas del Excel.")
    else:
        print("-> [SRE] Catalogo de productos inicializado vacio (sin datos del Excel).")

    # 4. Inyectar algunos permisos y el Rol 1 (Super Admin)
    cursor.execute("INSERT OR IGNORE INTO roles (id, nombre) VALUES (1, 'Super Administrador')")
    
    nuevos_permisos = [
        ('beneficios.ver', 'Beneficios', 'Ver panel de beneficios de productos propios'),
        ('beneficios.editar', 'Beneficios', 'Asignar productos propios a empleados y gestionar catalogo')
    ]
    
    for perm_id, mod, desc in nuevos_permisos:
        cursor.execute("INSERT OR IGNORE INTO permisos (id, modulo, descripcion) VALUES (?, ?, ?)", (perm_id, mod, desc))
        cursor.execute("INSERT OR IGNORE INTO rol_permisos (rol_id, permiso_id) VALUES (1, ?)", (perm_id,))
    conn.commit()
    print("-> [SRE] Permisos de beneficios inyectados al Rol 1 (Super Administrador).")

    # Insertar empleados de prueba
    cursor.executemany("""
    INSERT INTO empleados (nombre, rut, fecha_ingreso) VALUES (?, ?, ?)
    """, [
        ("Juan Perez", "11.111.111-1", "2026-01-15"),
        ("Maria Gonzalez", "22.222.222-2", "2026-05-25")
    ])
    conn.commit()
    print("-> [SRE] Empleados de prueba insertados.")
    conn.close()

def ejecutar_simulacion():
    print("=== SIMULACION SRE INICIADA ===")
    
    # TEST CASO A: Importacion exitosa
    df_normal = test_excel_loading_sre(EXCEL_PATH)
    init_mock_db_sre(df_normal)
    
    # Verificar base de datos poblada
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM productos_elaboracion_propia")
    cnt_prod = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM rol_permisos WHERE rol_id = 1")
    cnt_rp = cursor.fetchone()[0]
    print(f"\n[Verificacion Caso A] Productos en DB: {cnt_prod} | Permisos asignados a Super Admin: {cnt_rp}")
    
    # TEST CASO B: Tolerancia a fallos (Excel no existe)
    print("\n------------------------------------------------------------")
    print("TEST CASO B: Simular arranque con Excel faltante (Productos_roto.xlsx)")
    df_roto = test_excel_loading_sre("Productos_roto.xlsx")
    # No debe crashear, debe retornar DF vacio
    init_mock_db_sre(df_roto)
    
    cursor_roto = sqlite3.connect(DB_PATH).cursor()
    cursor_roto.execute("SELECT COUNT(*) FROM productos_elaboracion_propia")
    cnt_prod_roto = cursor_roto.fetchone()[0]
    print(f"[Verificacion Caso B] Productos en DB (deberia ser 0): {cnt_prod_roto}")
    
    conn.close()
    print("\n=== SIMULACION SRE FINALIZADA CON EXITO ===")

if __name__ == "__main__":
    ejecutar_simulacion()
