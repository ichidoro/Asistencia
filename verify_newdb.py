import urllib.request, json

env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

TURSO_URL = env['TURSO_DATABASE_URL'].replace('libsql://', 'https://')
TURSO_TOKEN = env['TURSO_AUTH_TOKEN']

def q(sql):
    payload = json.dumps({'requests': [{'type': 'execute', 'stmt': {'sql': sql}}, {'type': 'close'}]}).encode()
    req = urllib.request.Request(f'{TURSO_URL}/v2/pipeline', data=payload,
        headers={'Authorization': f'Bearer {TURSO_TOKEN}', 'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.loads(r.read())
    r2 = res['results'][0]
    if r2['type'] == 'error': return []
    d = r2['response']['result']
    cols = [c['name'] for c in d['cols']]
    return [{cols[i]: (row[i]['value'] if row[i]['type'] != 'null' else None) for i in range(len(cols))} for row in d['rows']]

print('=== NUEVA BD: libsql://aguacol-ichidoro ===')
print()
tablas = q("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%' AND name NOT LIKE 'libsql%' ORDER BY name")

todos_vacios = True
for t in tablas:
    nombre = t['name']
    cnt = q(f"SELECT COUNT(*) as c FROM [{nombre}]")
    n = cnt[0]['c'] if cnt else '?'
    estado = 'OK (vacia)' if str(n) == '0' else f'TIENE DATOS: {n}'
    if str(n) != '0':
        todos_vacios = False
    print(f'  {nombre:<40} {estado}')

print()
print(f'Total tablas: {len(tablas)}')
print(f'Estado: {"LIMPIA - solo estructura" if todos_vacios else "ADVERTENCIA - hay datos"}')
