import urllib.request, json, os

env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

url = env['TURSO_DATABASE_URL'].replace('libsql://', 'https://')
token = env['TURSO_AUTH_TOKEN']

def q(sql):
    p = json.dumps({'requests': [{'type': 'execute', 'stmt': {'sql': sql}}, {'type': 'close'}]}).encode()
    r = urllib.request.Request(url + '/v2/pipeline', data=p,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(r, timeout=30) as resp:
        res = json.loads(resp.read())
    d = res['results'][0]
    if d['type'] == 'error':
        return None, str(d['error'])
    cols = [c['name'] for c in d['response']['result']['cols']]
    rows = [{cols[i]: (row[i]['value'] if row[i]['type'] != 'null' else None)
             for i in range(len(cols))} for row in d['response']['result']['rows']]
    return rows, None

# Schema de logs_auditoria
rows, err = q("SELECT sql FROM sqlite_master WHERE name='logs_auditoria'")
print("Schema logs_auditoria:")
print(rows[0]['sql'] if rows else err)

# Verificar columnas reales
rows, err = q("SELECT * FROM logs_auditoria LIMIT 1")
if rows:
    print("\nColumnas logs_auditoria:", list(rows[0].keys()))
    print("Ejemplo:", rows[0])
else:
    print("Error logs_auditoria:", err)

# Buscar log de empleados faltantes
rows, err = q("SELECT * FROM logs_auditoria LIMIT 5")
if rows:
    print("\nPrimeros logs:")
    for r in rows:
        print(r)

# Estado empleado 11
rows, err = q("SELECT * FROM empleados WHERE id=11")
print(f"\nID 11: {rows}, err={err}")

# Asistencias de faltantes
rows, err = q("SELECT COUNT(*) as c FROM asistencias WHERE empleado_id IN (11,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53)")
print(f"Asistencias de faltantes: {rows[0]['c'] if rows else err}")
