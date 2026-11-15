# -*- coding: utf-8 -*-
"""Configuración → Mapa del código (dueño, 15-11-2026): solo el súper administrador lo ve, no está en /static (público) y la
pantalla dice si el mapa quedó atrás del código."""
import hashlib
import json
import os

import pytest
from fastapi import HTTPException

from backend.routers import mapa_codigo as mc

R = os.path.join(os.path.dirname(__file__), '..', '..')


def _md5(b: bytes) -> str:
    return hashlib.md5(b.replace(b'\r\n', b'\n')).hexdigest()


def test_dice_si_el_mapa_esta_al_dia(tmp_path):
    carpeta, raiz = tmp_path / 'mapa', tmp_path / 'raiz'
    carpeta.mkdir(); (raiz / 'backend').mkdir(parents=True)
    (raiz / 'backend' / 'a.py').write_bytes(b'x = 1\r\n')       # el PC guarda CRLF; el servidor, LF
    (raiz / 'backend' / 'b.py').write_bytes(b'y = 2\n')
    (carpeta / 'graph.html').write_text('<html></html>', encoding='utf-8')
    meta = {'armado': '2026-11-15T20:00:00+00:00', 'commit': 'abc1234',
            'archivos': {'backend/a.py': _md5(b'x = 1\n'), 'backend/b.py': _md5(b'y = 2\n'), 'backend/c.py': 'zzz'}}
    (carpeta / 'meta.json').write_text(json.dumps(meta), encoding='utf-8')
    e = mc.estado_del_mapa(carpeta, raiz)
    assert e['publicado'] and e['cambiados'] == [] and e['borrados'] == ['backend/c.py'] and not e['al_dia']
    (raiz / 'backend' / 'b.py').write_bytes(b'y = 3\n')
    assert mc.estado_del_mapa(carpeta, raiz)['cambiados'] == ['backend/b.py']


def test_sin_mapa_publicado(tmp_path):
    assert mc.estado_del_mapa(tmp_path, tmp_path) == {'publicado': False}


def test_solo_super_administrador():
    class U:
        is_superuser = False
    with pytest.raises(HTTPException):
        mc._solo_super(U())


def test_no_va_por_static_ni_trae_la_carpeta_de_trabajo():
    assert not os.path.exists(os.path.join(R, 'frontend', 'mapa_codigo'))
    ignora = open(os.path.join(R, '.graphifyignore'), encoding='utf-8').read()
    assert '/.claude/' in ignora and '/docs/PLAN_PENDIENTE_local.md' in ignora
    carpeta = os.path.join(R, 'backend', 'mapa_codigo')
    for nombre in ('graph.html', 'GRAPH_REPORT.md'):
        f = os.path.join(carpeta, nombre)
        if os.path.exists(f):
            texto = open(f, encoding='utf-8', errors='replace').read()
            assert '.claude/' not in texto and 'PLAN_PENDIENTE_local' not in texto


def test_hallazgos_se_calculan_sin_umbrales(tmp_path):
    import sys
    sys.path.insert(0, os.path.join(R, 'scripts'))
    from hallazgos_codigo import analizar
    (tmp_path / 'backend' / 'routers').mkdir(parents=True)
    (tmp_path / 'frontend' / 'js').mkdir(parents=True)
    (tmp_path / 'frontend' / 'js' / 'a.js').write_text('function esc(t){return t}\nconst fmt = (m) => m;', encoding='utf-8')
    (tmp_path / 'frontend' / 'js' / 'b.js').write_text('function esc(t){return t}', encoding='utf-8')
    (tmp_path / 'backend' / 'routers' / 'r.py').write_text('async def f(db):\n    await db.fetch_all("x")\n    await db.execute("y")\n', encoding='utf-8')
    h = analizar(tmp_path)
    assert h['repetidas']['top'][0] == {'nombre': 'esc', 'archivos': ['frontend/js/a.js', 'frontend/js/b.js']}
    assert h['sql_en_routers']['top'] == [{'archivo': 'backend/routers/r.py', 'consultas': 2}]
    assert h['funciones_largas']['top'][0]['funcion'] == 'f'
