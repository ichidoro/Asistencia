
"""
SIMULACION: Verifica el fix del sync BioAlba con fechas 2026-03-26 a 2026-04-26
Hace la llamada HTTP real al servidor corriendo en 127.0.0.1:8000
"""
import sqlite3, json, requests, time
from datetime import datetime

DB = 'data/local_db/asistencia_local.db'
FECHA_INICIO = '2026-03-26'
FECHA_FIN    = '2026-04-26'
BASE_URL     = 'http://127.0.0.1:8000/api'

print('=' * 60)
print(f'SIMULACION DE SYNC BIOALBA')
print(f'  Rango:  {FECHA_INICIO} → {FECHA_FIN}')
print(f'  Inicio: {datetime.now().strftime("%H:%M:%S")}')
print('=' * 60)

# ─── ESTADO PRE-SYNC ───────────────────────────────────────────
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""
    SELECT COUNT(*) as cnt, MIN(fecha_hora) as min_fh, MAX(fecha_hora) as max_fh
    FROM logs_raw
    WHERE fecha_hora >= ? AND fecha_hora <= ?
""", (FECHA_INICIO, FECHA_FIN + ' 23:59:59'))
pre_logs = cur.fetchone()

cur.execute("""
    SELECT COUNT(*) as cnt FROM asistencias
    WHERE fecha >= ? AND fecha <= ?
""", (FECHA_INICIO, FECHA_FIN))
pre_asist = cur.fetchone()

print()
print('ESTADO PRE-SYNC:')
print(f'  logs_raw en rango: {pre_logs["cnt"]}')
print(f'  asistencias en rango: {pre_asist["cnt"]}')
conn.close()

# ─── CONSTRUCCION DEL REQUEST (como lo haría el frontend corregido) ──
print()
print('PAYLOAD QUE ENVIARIA EL FRONTEND CORREGIDO:')

# Caso 1: Botón principal (todas las áreas)
url_all = f'{BASE_URL}/sync/asistencia/now/?fecha_inicio={FECHA_INICIO}&fecha_fin={FECHA_FIN}'
payload_all = {}  # sin filtro de áreas
print(f'  [Caso 1 - Botón Principal]')
print(f'    URL:     POST {url_all}')
print(f'    Body:    {json.dumps(payload_all)}')

# Caso 2: Modal por áreas (ej. SEGURIDAD + PRODUCCION)
areas_seleccionadas = ['SEGURIDAD', 'PRODUCCION']
url_areas = f'{BASE_URL}/sync/asistencia/now/?fecha_inicio={FECHA_INICIO}&fecha_fin={FECHA_FIN}'
payload_areas = {'areas': areas_seleccionadas}
print(f'  [Caso 2 - Modal Áreas ({", ".join(areas_seleccionadas)})]')
print(f'    URL:     POST {url_areas}')
print(f'    Body:    {json.dumps(payload_areas)}')

# ─── COMPORTAMIENTO ANTERIOR (BUG) ─────────────────────────────
print()
print('COMPORTAMIENTO ANTERIOR (BUG):')
mes_actual = datetime.now().month
anio_actual = datetime.now().year
url_bug = f'{BASE_URL}/sync/asistencia/now/?fecha_inicio={anio_actual}-{str(mes_actual).zfill(2)}-01'
print(f'  URL (bug): POST {url_bug}')
print(f'  Body (bug): {{}}  ← areas siempre ignoradas en llamada directa')
print(f'  → Solo sincronizaba desde 01/{str(mes_actual).zfill(2)}/{anio_actual}, sin fecha_fin')

# ─── LLAMADA REAL AL SERVIDOR ───────────────────────────────────
print()
print('EJECUTANDO LLAMADA REAL AL SERVIDOR...')
print(f'  Endpoint: {url_areas}')
print(f'  Payload:  {json.dumps(payload_areas)}')

try:
    t0 = time.time()
    # Primero verificamos que el servidor responde
    health = requests.get(f'{BASE_URL}/sync/health/', timeout=5)
    print(f'  Health check: {health.status_code} - {health.json().get("status","?")}')
    
    # Ahora ejecutamos con SOLO SEGURIDAD (más rápido para simular)
    resp = requests.post(
        f'{BASE_URL}/sync/asistencia/now/?fecha_inicio={FECHA_INICIO}&fecha_fin={FECHA_FIN}',
        json={'areas': ['SEGURIDAD']},
        timeout=120  # 2 min máximo para la simulación
    )
    elapsed = time.time() - t0
    
    print(f'  Status: {resp.status_code} (en {elapsed:.1f}s)')
    
    if resp.status_code == 200:
        data = resp.json()
        stats = data.get('stats', data)
        filters = data.get('filters', {})
        print()
        print('RESULTADO DEL SYNC:')
        print(f'  Áreas filtradas: {filters.get("areas", "todas")}')
        print(f'  Marcaciones nuevas: {stats.get("marcaciones_nuevas", "?")}')
        print(f'  Marcaciones actualizadas: {stats.get("marcaciones_actualizadas", "?")}')
        print(f'  Días recalculados: {stats.get("dias_recalculados", "?")}')
        print(f'  Errores: {stats.get("errores", "?")}')
        if 'detalles_error' in stats:
            print(f'  Detalles error: {stats["detalles_error"]}')
    else:
        print(f'  ERROR: {resp.text[:500]}')
        
except requests.exceptions.Timeout:
    print('  TIMEOUT - El sync tardó más de 120s (es normal en sync completo)')
except Exception as e:
    print(f'  Error de conexión: {e}')

# ─── ESTADO POST-SYNC ───────────────────────────────────────────
print()
print('ESTADO POST-SYNC:')
conn2 = sqlite3.connect(DB)
conn2.row_factory = sqlite3.Row
cur2 = conn2.cursor()

cur2.execute("""
    SELECT COUNT(*) as cnt, MIN(fecha_hora) as min_fh, MAX(fecha_hora) as max_fh
    FROM logs_raw
    WHERE fecha_hora >= ? AND fecha_hora <= ?
""", (FECHA_INICIO, FECHA_FIN + ' 23:59:59'))
post_logs = cur2.fetchone()

cur2.execute("""
    SELECT COUNT(*) as cnt FROM asistencias
    WHERE fecha >= ? AND fecha <= ?
""", (FECHA_INICIO, FECHA_FIN))
post_asist = cur2.fetchone()

print(f'  logs_raw en rango: {post_logs["cnt"]} (antes: {pre_logs["cnt"]}, delta: +{post_logs["cnt"] - pre_logs["cnt"]})')
print(f'  asistencias en rango: {post_asist["cnt"]} (antes: {pre_asist["cnt"]}, delta: +{post_asist["cnt"] - pre_asist["cnt"]})')

# ─── VERIFICAR sync_logs ───────────────────────────────────────
print()
print('SYNC_LOGS (últimas entradas):')
try:
    cur2.execute("PRAGMA table_info(sync_logs)")
    cols = [r[1] for r in cur2.fetchall()]
    print(f'  Columnas: {cols}')
    cur2.execute('SELECT * FROM sync_logs ORDER BY id DESC LIMIT 3')
    for r in cur2.fetchall():
        print(f'  {dict(r)}')
except Exception as e:
    print(f'  Error: {e}')

conn2.close()

print()
print('=== SIMULACION COMPLETADA ===')
print(f'  Fin: {datetime.now().strftime("%H:%M:%S")}')
