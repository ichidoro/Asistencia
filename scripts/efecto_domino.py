"""Efecto dominó («hilo rojo») sobre el mapa del código (auditoría del 15-11-2026).

Para una pieza (función, clase o archivo) recorre el grafo de graphify hacia atrás, nivel por nivel: quién la llama, quién
llama a esos, y así hasta llegar a los endpoints del servidor. Después cruza esos endpoints con las URL que piden las
pantallas (frontend/js) y con las pruebas que llegan a la pieza. Así se sabe, antes de cambiarla, qué se puede romper y
qué prueba lo cuidaría.

Solo lee. Uso:  .venv\\Scripts\\python.exe scripts\\efecto_domino.py <texto del nombre o id> [--json]
"""
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
GRAFO = RAIZ / 'graphify-out' / 'graph.json'
# Relaciones que significan «depende de»: si B la tiene hacia A, un cambio en A puede romper B
DEPENDE = ('calls', 'indirect_call', 'uses', 'imports', 'imports_from', 'inherits', 'references')
RE_RUTA = re.compile(r'@router\.(get|post|put|delete|patch)\(\s*["\']([^"\']*)["\']', re.S)
RE_PREFIJO = re.compile(r'APIRouter\([^)]*prefix\s*=\s*["\']([^"\']+)["\']', re.S)
RE_DEF = re.compile(r'^\s*(?:async\s+)?def\s+(\w+)\s*\(', re.M)
RE_FETCH = re.compile(r'[`\'"](/api/[^`\'"?$]*)')


def cargar():
    g = json.loads(GRAFO.read_text(encoding='utf-8'))
    nodos = {n['id']: n for n in g['nodes']}
    atras = defaultdict(set)        # destino -> quienes dependen de él
    for e in g.get('links') or g.get('edges') or []:
        if e.get('relation') in DEPENDE:
            s, t = e.get('_src', e['source']), e.get('_tgt', e['target'])
            if s != t:
                atras[t].add(s)
    # Un método pertenece a su clase y una función a su archivo: subir por «contiene» deja ver al dueño
    duenio = {}
    for e in g.get('links') or g.get('edges') or []:
        if e.get('relation') in ('method', 'contains'):
            duenio[e.get('_tgt', e['target'])] = e.get('_src', e['source'])
    return nodos, atras, duenio


def endpoints():
    """{(archivo, función): 'METODO /api/ruta'} leído de los routers."""
    out = {}
    for p in (RAIZ / 'backend' / 'routers').glob('*.py'):
        t = p.read_text(encoding='utf-8', errors='replace')
        m = RE_PREFIJO.search(t)
        prefijo = '/api' + (m.group(1) if m else '')
        lineas = t.splitlines()
        for i, l in enumerate(lineas):
            r = RE_RUTA.search(l + ''.join(lineas[i + 1:i + 3]))
            if not r or not l.lstrip().startswith('@router.'):
                continue
            for j in range(i + 1, min(i + 15, len(lineas))):
                d = RE_DEF.match(lineas[j])
                if d:
                    out[(p.relative_to(RAIZ).as_posix(), d.group(1))] = f'{r.group(1).upper()} {prefijo}{r.group(2)}'
                    break
    return out


def pantallas_que_piden(ruta: str):
    """Archivos de pantalla que piden esa URL (comparando el tramo fijo de la ruta, sin {parámetros})."""
    fija = re.sub(r'\{[^}]+\}.*$', '', ruta.split(' ', 1)[1]).rstrip('/')
    out = set()
    for p in list((RAIZ / 'frontend' / 'js').rglob('*.js')) + list((RAIZ / 'dashboard_build' / 'src').rglob('*.jsx')):
        if '.min.' in p.name or p.name == 'dashboard_react.js':
            continue
        t = p.read_text(encoding='utf-8', errors='replace')
        for u in RE_FETCH.findall(t):
            if fija and u.rstrip('/').startswith(fija):
                out.add(p.relative_to(RAIZ).as_posix())
                break
    return sorted(out)


def domino(objetivo: str, nodos=None, atras=None, duenio=None, eps=None):
    nodos, atras, duenio = (nodos, atras, duenio) if nodos else cargar()
    eps = eps if eps is not None else endpoints()
    inicio = [i for i, n in nodos.items() if i == objetivo or str(n.get('label', '')).strip('.()') == objetivo]
    if not inicio:
        return {'objetivo': objetivo, 'encontrado': False}
    niveles, visto, cola = defaultdict(list), set(inicio), deque((i, 0) for i in inicio)
    while cola:
        nid, nivel = cola.popleft()
        for q in atras.get(nid, ()):
            if q not in visto:
                visto.add(q)
                niveles[nivel + 1].append(q)
                cola.append((q, nivel + 1))
    afectados = visto - set(inicio)
    archivos = sorted({str(nodos[i].get('source_file') or '') for i in afectados if i in nodos} - {''})
    eps_hit, pruebas = set(), set()
    for i in afectados | set(inicio):
        n = nodos.get(i) or {}
        sf, nom = str(n.get('source_file') or '').replace(chr(92), '/'), str(n.get('label') or '').strip('.()')
        if (sf, nom) in eps:
            eps_hit.add(eps[(sf, nom)])
        if '/tests/' in sf:
            pruebas.add(sf)
    return {
        'objetivo': objetivo, 'encontrado': True,
        'definida_en': sorted({str(nodos[i].get('source_file')) for i in inicio}),
        'niveles': {k: len(v) for k, v in sorted(niveles.items())},
        'piezas_afectadas': len(afectados), 'archivos_afectados': archivos,
        'endpoints': sorted(eps_hit),
        'pantallas': sorted({p for e in eps_hit for p in pantallas_que_piden(e)}),
        'pruebas': sorted(pruebas),
    }


if __name__ == '__main__':
    r = domino(sys.argv[1])
    if '--json' in sys.argv:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        for k, v in r.items():
            print(f'{k}: {v if not isinstance(v, list) or len(v) < 12 else v[:12] + ["…" + str(len(v) - 12) + " más"]}')
