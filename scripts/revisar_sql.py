"""Araña de SQL sin ejecutar nada (auditoría del 15-11-2026).

Toma cada consulta escrita como texto fijo en el servidor (lo que se pasa a fetch_all, fetch_one, execute…), la traduce
como lo hace la aplicación (sql_compat) y le pide a una base PostgreSQL que la PREPARE: así se sabe si nombra tablas o
columnas que no existen, también en lo que guarda, sin ejecutarla. La conexión va en modo solo lectura y cada PREPARE se
descarta. Las consultas armadas con f-strings se revisan solo si no tienen partes variables.

Uso (con la copia de práctica encendida):  .venv\\Scripts\\python.exe scripts\\revisar_sql.py
"""
import ast
import asyncio
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
METODOS = ('fetch_all', 'fetch_one', 'execute', 'execute_batch', 'fetchval', 'fetchrow', 'fetch')


def consultas():
    out = []
    for p in sorted((RAIZ / 'backend').rglob('*.py')):
        if 'tests' in p.parts or 'mapa_codigo' in p.parts:
            continue
        try:
            arbol = ast.parse(p.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        for n in ast.walk(arbol):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in METODOS and n.args):
                continue
            a = n.args[0]
            texto = None
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                texto = a.value
            elif isinstance(a, ast.JoinedStr) and all(isinstance(v, ast.Constant) for v in a.values):
                texto = ''.join(v.value for v in a.values)
            out.append((p.relative_to(RAIZ).as_posix(), n.lineno, texto))
    return out


def url_local():
    """La base del .env (o DATABASE_URL). La usa la prueba automática: solo sirve si es una base de este PC."""
    from dotenv import dotenv_values
    return os.environ.get('DATABASE_URL') or dotenv_values(RAIZ / '.env').get('DATABASE_URL')


async def revisar(url):
    """Devuelve (todas las llamadas, las revisables, las que la base rechaza)."""
    from backend.core.sql_compat import convert_placeholders, split_statements, translate_sql
    import asyncpg
    con = await asyncpg.connect(url, server_settings={'default_transaction_read_only': 'on'})
    todas = consultas()
    revisables = [c for c in todas if c[2] and re.match(r'\s*(SELECT|INSERT|UPDATE|DELETE|WITH)\b', c[2], re.I)]
    # Tablas que el propio código crea justo antes de usarlas (CREATE TABLE IF NOT EXISTS): si la base de práctica
    # todavía no pasó por ahí, no existen, y eso no es una falla
    creadas = {m.lower() for _, _, sql in todas if sql
               for m in re.findall(r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+"?(\w+)', sql, re.I)}
    fallas = []
    for archivo, linea, sql in revisables:
        for parte in split_statements(translate_sql(sql)) or [sql]:
            q = convert_placeholders(parte)
            try:
                async with con.transaction():
                    await con.prepare(q)
            except asyncpg.exceptions.UndefinedTableError as e:
                tabla = re.search(r'relation "(\w+)"', str(e))
                if not (tabla and tabla.group(1).lower() in creadas):
                    fallas.append((archivo, linea, type(e).__name__, str(e).split('\n')[0][:160]))
            except asyncpg.exceptions.PostgresError as e:
                fallas.append((archivo, linea, type(e).__name__, str(e).split('\n')[0][:160]))
            except Exception as e:  # noqa: BLE001
                fallas.append((archivo, linea, type(e).__name__, str(e)[:160]))
    await con.close()
    return todas, revisables, fallas


async def main():
    todas, revisables, fallas = await revisar(url_local())
    print(f'{len(todas)} llamadas a la base; {len(revisables)} con SQL fijo revisable; {len(fallas)} que la base rechaza')
    for f in fallas:
        print('  ', f'{f[0]}:{f[1]}', f[2], '|', f[3])


if __name__ == '__main__':
    asyncio.run(main())
