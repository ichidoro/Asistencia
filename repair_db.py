"""
Repara la DB local usando el cliente HTTP de Turso para leer los datos correctos
y sqlite3 para reconstruir las tablas corruptas en la replica local.
"""
import sqlite3
import os
import sys

# Leer variables de entorno del .env
env_path = '.env'
env = {}
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")

turso_url = env.get('TURSO_DATABASE_URL', '')
turso_token = env.get('TURSO_AUTH_TOKEN', '')

print(f"Turso URL: {turso_url[:50]}...")
print(f"Token: {turso_token[:20]}...")

if not turso_url or not turso_token:
    print("ERROR: No se encontraron credenciales de Turso en .env")
    sys.exit(1)

# Consultar Turso via HTTP API
import urllib.request
import json

def turso_query(sql, args=None):
    """Ejecuta SQL contra Turso via HTTP API."""
    # Convertir URL libsql:// a https://
    url = turso_url.replace('libsql://', 'https://')
    endpoint = f"{url}/v2/pipeline"
    
    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": sql,
                    "args": [{"type": "text", "value": str(a)} if a is not None else {"type": "null"} for a in (args or [])]
                }
            },
            {"type": "close"}
        ]
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            'Authorization': f'Bearer {turso_token}',
            'Content-Type': 'application/json'
        },
        method='POST'
    )
    
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    
    if result['results'][0]['type'] == 'error':
        raise Exception(result['results'][0]['error']['message'])
    
    rows_data = result['results'][0]['response']['result']
    cols = [c['name'] for c in rows_data['cols']]
    rows = []
    for row in rows_data['rows']:
        r = {}
        for i, col in enumerate(cols):
            val = row[i]
            r[col] = val['value'] if val['type'] != 'null' else None
        rows.append(r)
    return cols, rows

print("\n=== Consultando turno_dias desde Turso Cloud via HTTP ===")
cols_td, rows_td = turso_query("SELECT * FROM turno_dias ORDER BY id")
print(f"turno_dias: {len(rows_td)} filas, columnas: {cols_td}")

print("\n=== Consultando historial_areas desde Turso Cloud via HTTP ===")
cols_ha, rows_ha = turso_query("SELECT * FROM historial_areas ORDER BY id")
print(f"historial_areas: {len(rows_ha)} filas, columnas: {cols_ha}")

print("\n=== Abriendo DB local con sqlite3 ===")
db_path = 'data/local_db/asistencia_local.db'
conn = sqlite3.connect(db_path, timeout=10)
conn.execute("PRAGMA journal_mode=WAL")
cur = conn.cursor()

# Test de lectura de turno_dias antes de reparar
print("\n=== Test pre-reparación ===")
try:
    cur.execute("SELECT COUNT(*) FROM turno_dias")
    print(f"turno_dias local (sqlite3): {cur.fetchone()[0]} filas")
except Exception as e:
    print(f"turno_dias ERROR: {e}")

try:
    cur.execute("SELECT COUNT(*) FROM historial_areas")
    print(f"historial_areas local (sqlite3): {cur.fetchone()[0]} filas")
except Exception as e:
    print(f"historial_areas ERROR: {e}")

# Reconstruir turno_dias: DROP + CREATE + INSERT
print("\n=== Reconstruyendo turno_dias ===")
try:
    # Obtener schema de la tabla
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='turno_dias'")
    schema = cur.fetchone()
    if schema:
        print(f"Schema: {schema[0][:100]}...")
    
    # DROP y recrear
    cur.execute("DROP TABLE IF EXISTS turno_dias_old")
    cur.execute("ALTER TABLE turno_dias RENAME TO turno_dias_old")
    if schema:
        cur.execute(schema[0])
    
    # Re-insertar desde datos del cloud
    inserted = 0
    for row in rows_td:
        vals = [row.get(c) for c in cols_td]
        placeholders = ','.join(['?' for _ in cols_td])
        cols_str = ','.join(f'"{c}"' for c in cols_td)
        cur.execute(f"INSERT INTO turno_dias ({cols_str}) VALUES ({placeholders})", vals)
        inserted += 1
    
    cur.execute("DROP TABLE turno_dias_old")
    conn.commit()
    print(f"turno_dias reconstruida: {inserted} filas insertadas")
except Exception as e:
    conn.rollback()
    print(f"ERROR reconstruyendo turno_dias: {e}")

# Reconstruir historial_areas
print("\n=== Reconstruyendo historial_areas ===")
try:
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='historial_areas'")
    schema = cur.fetchone()
    
    cur.execute("DROP TABLE IF EXISTS historial_areas_old")
    cur.execute("ALTER TABLE historial_areas RENAME TO historial_areas_old")
    if schema:
        cur.execute(schema[0])
    
    inserted = 0
    for row in rows_ha:
        vals = [row.get(c) for c in cols_ha]
        placeholders = ','.join(['?' for _ in cols_ha])
        cols_str = ','.join(f'"{c}"' for c in cols_ha)
        cur.execute(f"INSERT INTO historial_areas ({cols_str}) VALUES ({placeholders})", vals)
        inserted += 1
    
    cur.execute("DROP TABLE historial_areas_old")
    conn.commit()
    print(f"historial_areas reconstruida: {inserted} filas insertadas")
except Exception as e:
    conn.rollback()
    print(f"ERROR reconstruyendo historial_areas: {e}")

# Verificacion final
print("\n=== Verificación post-reparación ===")
try:
    cur.execute("SELECT COUNT(*) FROM turno_dias")
    print(f"turno_dias: {cur.fetchone()[0]} filas OK")
except Exception as e:
    print(f"turno_dias: ERROR - {e}")

try:
    cur.execute("SELECT COUNT(*) FROM historial_areas")
    print(f"historial_areas: {cur.fetchone()[0]} filas OK")
except Exception as e:
    print(f"historial_areas: ERROR - {e}")

try:
    # Test del JOIN que fallaba
    cur.execute("""SELECT COUNT(*) FROM empleados e 
                   LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1
                   LEFT JOIN areas a ON ha.area_id = a.id 
                   WHERE e.activo = 1""")
    print(f"JOIN empleados+historial_areas: {cur.fetchone()[0]} filas OK")
except Exception as e:
    print(f"JOIN empleados+historial_areas: ERROR - {e}")

conn.close()
print("\n✅ Reparación completada.")
