"""
Repara los indices corruptos DIRECTAMENTE en Turso Cloud via HTTP API.
Ejecuta REINDEX en las tablas afectadas para reconstruir los B-Trees.
"""
import urllib.request
import json
import os

# Leer .env
env_path = '.env'
env = {}
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")

turso_url = env.get('TURSO_DATABASE_URL', '').replace('libsql://', 'https://')
turso_token = env.get('TURSO_AUTH_TOKEN', '')

print(f"Turso URL: {turso_url[:60]}...")

def turso_exec(statements):
    """Ejecuta una lista de statements en Turso via HTTP pipeline."""
    endpoint = f"{turso_url}/v2/pipeline"
    requests = []
    for sql in statements:
        requests.append({
            "type": "execute",
            "stmt": {"sql": sql}
        })
    requests.append({"type": "close"})
    
    payload = json.dumps({"requests": requests}).encode('utf-8')
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            'Authorization': f'Bearer {turso_token}',
            'Content-Type': 'application/json'
        },
        method='POST'
    )
    
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())

# 1. Verificar estado actual
print("\n=== 1. Verificando estado actual en Turso Cloud ===")
result = turso_exec(["SELECT COUNT(*) as c FROM turno_dias"])
print(f"turno_dias en cloud: {result['results'][0]['response']['result']['rows'][0][0]['value']} filas")

result = turso_exec(["SELECT COUNT(*) as c FROM historial_areas"])
print(f"historial_areas en cloud: {result['results'][0]['response']['result']['rows'][0][0]['value']} filas")

# 2. REINDEX en Turso Cloud para reconstruir los indices corruptos
print("\n=== 2. Ejecutando REINDEX en Turso Cloud ===")
reindex_stmts = [
    "REINDEX turno_dias",
    "REINDEX historial_areas", 
    "REINDEX empleados",
    "REINDEX asistencias",
    "REINDEX horas_extras",
]

for stmt in reindex_stmts:
    try:
        result = turso_exec([stmt])
        if result['results'][0]['type'] == 'ok':
            print(f"  OK: {stmt}")
        else:
            print(f"  ERR: {stmt} -> {result['results'][0]}")
    except Exception as e:
        print(f"  ERR: {stmt} -> {e}")

# 3. VACUUM en Turso Cloud
print("\n=== 3. Ejecutando VACUUM en Turso Cloud ===")
try:
    result = turso_exec(["VACUUM"])
    if result['results'][0]['type'] == 'ok':
        print("  VACUUM OK")
    else:
        print(f"  VACUUM resultado: {result['results'][0]}")
except Exception as e:
    print(f"  VACUUM ERROR: {e}")

# 4. Verificar que las queries criticas funcionan en cloud
print("\n=== 4. Verificando queries criticas en Turso Cloud ===")
test_queries = [
    ("JOIN empleados+historial_areas", 
     "SELECT COUNT(*) as c FROM empleados e LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 LEFT JOIN areas a ON ha.area_id = a.id WHERE e.activo = 1"),
    ("turno_dias por turno", 
     "SELECT COUNT(*) as c FROM turno_dias WHERE turno_id = 1"),
    ("asistencias count",
     "SELECT COUNT(*) as c FROM asistencias"),
]

for name, sql in test_queries:
    try:
        result = turso_exec([sql])
        val = result['results'][0]['response']['result']['rows'][0][0]['value']
        print(f"  OK: {name} -> {val} filas")
    except Exception as e:
        print(f"  ERR: {name} -> {e}")

print("\nReparacion en Turso Cloud completada.")
print("Reiniciar el servidor para que sincronice la DB reparada.")
