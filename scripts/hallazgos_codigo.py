"""Hallazgos del código en palabras, para Configuración → Mapa del código (dueño, 15-11-2026: «para mí el grafo es solo
ver puntos»). Lo llama `publicar_mapa.py` y guarda `backend/mapa_codigo/hallazgos.json`.

Todo sale de medir el código y el grafo: rankings y conteos, sin umbrales escritos aquí. Los archivos que no son nuestros
(bibliotecas, compilados) se saltan con las mismas reglas de `.graphifyignore`.
"""
import ast
import fnmatch
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

EXT = ('.py', '.js', '.jsx')
CARPETAS = ('backend', 'frontend', 'dashboard_build', 'scripts')
RE_JS_FUNC = re.compile(r'\bfunction\s+([A-Za-z_$][\w$]*)\s*\(')
RE_JS_FLECHA = re.compile(r'\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)')
RE_SQL = re.compile(r'\b(?:fetch_all|fetch_one|execute|execute_batch)\s*\(')
CUANTOS = 10   # cuántas filas muestra cada ranking en la pantalla
USOS = ('calls', 'indirect_call', 'references', 'uses', 'imports', 'imports_from', 'inherits')


def _ignorados(raiz: Path) -> List[str]:
    f = raiz / '.graphifyignore'
    if not f.exists():
        return []
    return [l.strip() for l in f.read_text(encoding='utf-8').splitlines() if l.strip() and not l.startswith('#')]


def _se_ignora(rel: str, patrones: List[str]) -> bool:
    for p in patrones:
        p2 = p.lstrip('/')
        if p2.endswith('/') and (rel + '/').startswith(p2):
            return True
        if fnmatch.fnmatch(rel, p2) or rel == p2:
            return True
    return False


def archivos_propios(raiz: Path) -> List[Path]:
    """Código nuestro: sin pruebas, sin bibliotecas comprimidas y sin lo que excluye .graphifyignore."""
    patrones = _ignorados(raiz)
    out = []
    for c in CARPETAS:
        for p in (raiz / c).rglob('*'):
            rel = p.relative_to(raiz).as_posix()
            if (p.suffix not in EXT or not p.is_file() or 'tests' in p.parts or 'node_modules' in p.parts
                    or '__pycache__' in p.parts or '.min.' in p.name or _se_ignora(rel, patrones)):
                continue
            out.append(p)
    return sorted(out)


def _funciones_py(p: Path):
    """(nombre, líneas, de módulo, con decorador) de cada función de un archivo Python."""
    arbol = ast.parse(p.read_text(encoding='utf-8', errors='replace'))
    de_modulo = {id(n) for n in arbol.body}
    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield n.name, n.end_lineno - n.lineno + 1, id(n) in de_modulo, bool(n.decorator_list)


def analizar(raiz: Path, grafo: Dict[str, Any] = None, informe: str = '') -> Dict[str, Any]:
    raiz = Path(raiz)
    archivos = archivos_propios(raiz)
    definidas = defaultdict(set)      # nombre de ayudante -> archivos donde se escribe
    largas, tamanos, sql = [], [], []
    texto_total = {}
    # Las funciones con decorador las llama el propio framework (rutas, validadores, eventos): no son «sin uso»
    con_decorador = set()
    for p in archivos:
        rel = p.relative_to(raiz).as_posix()
        texto = p.read_text(encoding='utf-8', errors='replace')
        texto_total[rel] = texto
        tamanos.append({'archivo': rel, 'lineas': texto.count('\n') + 1})
        if p.suffix == '.py':
            try:
                for nombre, n_lin, de_modulo, decorada in _funciones_py(p):
                    largas.append({'funcion': nombre, 'archivo': rel, 'lineas': n_lin})
                    if decorada:
                        con_decorador.add((rel, nombre))
                    # Un método de una clase es parte de su interfaz; lo repetido son las funciones sueltas
                    if de_modulo and not nombre.startswith('__'):
                        definidas[nombre].add(rel)
            except SyntaxError:
                pass
            if '/routers/' in '/' + rel:
                n = len(RE_SQL.findall(texto))
                if n:
                    sql.append({'archivo': rel, 'consultas': n})
        else:
            for nombre in set(RE_JS_FUNC.findall(texto)) | set(RE_JS_FLECHA.findall(texto)):
                definidas[nombre].add(rel)
    repetidas = sorted(({'nombre': k, 'archivos': sorted(v)} for k, v in definidas.items() if len(v) > 1),
                       key=lambda r: (-len(r['archivos']), r['nombre']))
    largas.sort(key=lambda r: -r['lineas'])
    tamanos.sort(key=lambda r: -r['lineas'])
    sql.sort(key=lambda r: -r['consultas'])

    # Funciones del servidor que nadie llama: sin flechas de entrada en el grafo y sin otra mención en el código
    sin_uso = []
    if grafo:
        entra = defaultdict(int)
        # Solo cuentan los usos (llamar, nombrar, importar, heredar); «contiene» o «es método de» no son uso
        for e in grafo.get('links') or grafo.get('edges') or []:
            if e.get('relation') in USOS:
                entra[e.get('_tgt', e.get('target'))] += 1
        todo = '\n'.join(texto_total.values())
        for n in grafo.get('nodes', []):
            sf = str(n.get('source_file') or '').replace(chr(92), '/')
            lab = str(n.get('label') or '')
            if (not sf.startswith('backend/') or '/routers/' in sf or '/tests/' in sf or not lab.endswith('()')
                    or entra.get(n.get('id'))):
                continue
            nombre = lab.strip('.()')
            if nombre.startswith('__') or (sf, nombre) in con_decorador:
                continue
            if len(re.findall(r'\b' + re.escape(nombre) + r'\b', todo)) <= 1:
                sin_uso.append({'funcion': nombre, 'archivo': sf})
    ciclos = []
    if informe and '## Import Cycles' in informe:
        bloque = informe.split('## Import Cycles', 1)[1].split('\n## ', 1)[0]
        ciclos = [l.strip('- ').strip() for l in bloque.splitlines() if l.strip().startswith('-') and 'None' not in l]
    return {
        'archivos_revisados': len(archivos),
        'repetidas': {'total': len(repetidas), 'top': repetidas[:CUANTOS]},
        'funciones_largas': {'total': len(largas), 'top': largas[:CUANTOS]},
        'archivos_grandes': tamanos[:CUANTOS],
        'sql_en_routers': {'total': sum(r['consultas'] for r in sql), 'top': sql[:CUANTOS]},
        'sin_uso': sorted(sin_uso, key=lambda r: (r['archivo'], r['funcion'])),
        'ciclos': ciclos,
    }


if __name__ == '__main__':
    raiz = Path(__file__).resolve().parents[1]
    g = raiz / 'graphify-out' / 'graph.json'
    print(json.dumps(analizar(raiz, json.loads(g.read_text(encoding='utf-8')) if g.exists() else None), ensure_ascii=False, indent=1)[:3000])
