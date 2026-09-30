"""Copia SOLO LECTURA de Turso a un SQLite local. Uso: TURSO_URL=... TURSO_TOKEN=... python scripts/dump_turso.py [salida.db]
Requiere: pip install libsql"""
import sqlite3, sys, os, libsql
url = os.environ['TURSO_URL']; tok = os.environ['TURSO_TOKEN']
OUT = sys.argv[1] if len(sys.argv) > 1 else 'turso_copy.db'
c = libsql.connect(database=url, auth_token=tok)
cur = c.cursor()
cur.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'libsql_%'")
objs = cur.fetchall()
out = sqlite3.connect(OUT)
tables = [o for o in objs if o[0]=='table']
for t in tables:
    out.execute(t[3])
tot=0
for t in tables:
    name=t[1]
    rows=[]
    try:
        cur.execute(f'SELECT * FROM "{name}"'); rows = cur.fetchall()
    except Exception as e:
        print('!! FALLO', name, str(e)[:80], '-> paginando por rowid')
        off=0; step=500
        while True:
            try:
                cur.execute(f'SELECT * FROM "{name}" ORDER BY rowid LIMIT {step} OFFSET {off}'); part=cur.fetchall()
            except Exception as e2:
                try:
                    part=[]
                    for i in range(step):
                        cur.execute(f'SELECT * FROM "{name}" ORDER BY rowid LIMIT 1 OFFSET {off+i}')
                        r=cur.fetchall()
                        if not r: break
                        part+=r
                except Exception as e3:
                    print('   corte en offset', off, str(e3)[:60]); break
            if not part: break
            rows+=part; off+=len(part)
            if len(part)<step: break
        print('   rescatadas', len(rows))
    if rows:
        out.executemany(f'INSERT INTO "{name}" VALUES ({",".join("?"*len(rows[0]))})', rows)
    tot+=len(rows)
    print(name, len(rows))
for o in objs:
    if o[0] in ('index','view','trigger'):
        try: out.execute(o[3])
        except Exception as e: print('skip',o[1],e)
out.commit()
print('TOTAL', tot, 'tables', len(tables))
