import sqlite3, os

src = 'data/local_db/asistencia_local.db'
dst = 'data/local_db/asistencia_local_clean.db'

print('Conectando a DB original...')
conn = sqlite3.connect(src)
conn.execute('PRAGMA journal_mode=WAL')

print('Ejecutando VACUUM INTO para reconstruir DB limpia...')
conn.execute('VACUUM INTO ?', (dst,))
conn.close()

size_orig = os.path.getsize(src)
size_new  = os.path.getsize(dst)
print(f'Original: {size_orig/1024/1024:.1f} MB')
print(f'Limpia:   {size_new/1024/1024:.1f} MB')

print('Verificando integridad de la DB limpia...')
conn2 = sqlite3.connect(dst)
cur = conn2.cursor()
cur.execute('PRAGMA integrity_check')
issues = cur.fetchall()
result = issues[0][0] if issues else 'ok'
print(f'Issues: {len(issues)} -> {result}')

cur.execute('SELECT COUNT(*) FROM turno_dias')
print(f'turno_dias: {cur.fetchone()[0]} filas')
cur.execute('SELECT COUNT(*) FROM historial_areas')
print(f'historial_areas: {cur.fetchone()[0]} filas')
cur.execute('SELECT COUNT(*) FROM asistencias')
print(f'asistencias: {cur.fetchone()[0]} filas')
conn2.close()

print('Reemplazando DB original...')
os.replace(src, src + '.bak')
os.replace(dst, src)
print('Listo. DB reconstruida sin fragmentacion.')
