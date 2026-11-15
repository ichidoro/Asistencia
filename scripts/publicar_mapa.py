"""Publica el mapa del código (graphify) para verlo en Configuración → Mapa del código (dueño, 15-11-2026).

Corre en el PC. Primero rehace el grafo del código con graphify (`graphify update .`, sin IA: solo lee el código) y la página
completa (sin el agrupado por comunidades que graphify usa sobre 5.000 piezas). Después copia de `graphify-out/` (que no va a
git) a `backend/mapa_codigo/`
(que sí va, y el servidor la entrega solo al súper administrador): la página del grafo y su informe. Anota de cuándo es,
sobre qué commit se armó y la huella de cada archivo de backend/ y frontend/ que leyó, para que la pantalla diga cuántos
cambiaron después (mapa desactualizado).

Uso:  .venv\\Scripts\\python.exe scripts\\publicar_mapa.py                    (rehace y publica)
      .venv\\Scripts\\python.exe scripts\\publicar_mapa.py --sin-actualizar   (solo publica lo que hay)
Los documentos (.md) se leen con IA: cuando cambian mucho, antes correr /graphify . --update en Claude Code.
"""
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ORIGEN = RAIZ / 'graphify-out'
DESTINO = RAIZ / 'backend' / 'mapa_codigo'
# Lo que nunca puede aparecer en lo que se publica: la carpeta de trabajo con ensayos de datos reales y el plan con nombres
PROHIBIDO = ('.claude/', '.claude\\\\', '.claude\\', 'PLAN_PENDIENTE_local')


def huella(ruta: Path) -> str:
    """md5 del archivo con los fines de línea unificados (en el servidor los archivos vienen de git con LF)."""
    return hashlib.md5(ruta.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


PAGINA_COMPLETA = r"""
import json
from collections import defaultdict
from pathlib import Path
from graphify.paths import load_node_link_graph
from graphify.export import to_html
G = load_node_link_graph(json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8')))
com, nombres = defaultdict(list), {}
for n, d in G.nodes(data=True):
    if d.get('community') is not None:
        com[int(d['community'])].append(n)
        if d.get('community_name'):
            nombres[int(d['community'])] = d['community_name']
to_html(G, dict(com), 'graphify-out/graph.html', community_labels=nombres or None, node_limit=G.number_of_nodes() + 1)
"""


def actualizar() -> bool:
    """Rehace el grafo del código (sin IA) y su página completa, con el Python donde está instalado graphify."""
    py_f = ORIGEN / '.graphify_python'
    if not py_f.exists():
        print('No está graphify en este PC: corra /graphify . una vez en Claude Code.')
        return False
    py = Path(py_f.read_text(encoding='utf-8').strip())
    exe = py.parent / ('graphify.exe' if sys.platform == 'win32' else 'graphify')
    for paso in ([str(exe), 'update', '.', '--force'], [str(py), '-c', PAGINA_COMPLETA]):
        r = subprocess.run(paso, cwd=RAIZ)
        if r.returncode != 0:
            print('Falló:', ' '.join(paso[:3]))
            return False
    return True


def main() -> int:
    if '--sin-actualizar' not in sys.argv and not actualizar():
        return 1
    grafo, informe, manifiesto = ORIGEN / 'graph.html', ORIGEN / 'GRAPH_REPORT.md', ORIGEN / 'manifest.json'
    for f in (grafo, informe, manifiesto):
        if not f.exists():
            print(f'Falta {f}: primero corra /graphify . --update')
            return 1
    for f in (grafo, informe):
        texto = f.read_text(encoding='utf-8', errors='replace')
        malos = [p for p in PROHIBIDO if p in texto]
        if malos:
            print(f'{f.name} menciona {malos}: revise .graphifyignore y rehaga el grafo. No se publicó nada.')
            return 1
    leidos = json.loads(manifiesto.read_text(encoding='utf-8'))
    archivos = {}
    for rel in sorted(leidos):
        r = rel.replace('\\', '/')
        if r.startswith(('backend/', 'frontend/')) and (RAIZ / r).is_file() and not r.startswith('backend/mapa_codigo/'):
            archivos[r] = huella(RAIZ / r)
    try:
        commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=RAIZ, capture_output=True, text=True,
                                check=True).stdout.strip()
    except Exception:
        commit = ''
    DESTINO.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(grafo, DESTINO / 'graph.html')
    shutil.copyfile(informe, DESTINO / 'GRAPH_REPORT.md')
    meta = {
        'armado': datetime.fromtimestamp(grafo.stat().st_mtime, timezone.utc).isoformat(timespec='seconds'),
        'publicado': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'commit': commit,
        'archivos_leidos': len(leidos),
        'archivos': archivos,
    }
    (DESTINO / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Mapa publicado en {DESTINO} (commit {commit or "?"}, {len(archivos)} archivos con huella).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
