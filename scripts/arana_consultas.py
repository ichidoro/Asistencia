"""Araña de solo lectura (auditoría del 15-11-2026): llama cada endpoint GET de la copia de práctica como administrador
Si un endpoint pide parámetros (422), reintenta con valores típicos de la propia base (empleado, área, fechas del tramo).

La usa la prueba automática backend/tests/test_arana_consultas.py (etapa 3). A mano:
  PANTALLAS_URL=http://localhost:8001 PANTALLAS_USUARIO=… PANTALLAS_CLAVE=… \
  .venv/Scripts/python.exe scripts/arana_consultas.py . resultado.json
Nunca apuntarla a producción: usa la copia de práctica."""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'scripts'))
from efecto_domino import endpoints  # noqa: E402


def _pedir(url, ruta, cabeceras):
    req = urllib.request.Request(url + ruta, headers=cabeceras)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read(200)
            return r.status, round(time.time() - t0, 2), ''
    except urllib.error.HTTPError as e:
        cuerpo = e.read(400).decode('utf-8', 'replace')
        return e.code, round(time.time() - t0, 2), cuerpo
    except Exception as e:  # noqa: BLE001
        return 0, round(time.time() - t0, 2), str(e)[:200]


def recorrer(url, token):
    """Llama todos los GET y devuelve una lista con ruta, estado, segundos, archivo, función y detalle de las fallas."""
    cabeceras = {'Authorization': 'Bearer ' + token}
    emps = json.loads(urllib.request.urlopen(urllib.request.Request(url + '/api/empleados/', headers=cabeceras),
                                             timeout=30).read())
    lista = emps if isinstance(emps, list) else (emps.get('items') or emps.get('data') or [])
    emp = lista[0] if lista else {}
    eid = emp.get('id', 1)
    area = emp.get('area') or 'PRODUCCION'
    tipicos = {'fecha_inicio': '2026-10-26', 'fecha_fin': '2026-11-25', 'fecha': '2026-11-10', 'desde': '2026-10-26',
               'hasta': '2026-11-25', 'area': area, 'empleado_id': eid, 'mes': 11, 'anio': 2026, 'year': 2026,
               'month': 11, 'q': 'a', 'rut': emp.get('rut', '1'), 'tramo': '', 'id': 1}
    resultados = []
    for (archivo, funcion), ruta in sorted(endpoints().items(), key=lambda x: x[1]):
        metodo, camino = ruta.split(' ', 1)
        if metodo != 'GET':
            continue
        camino = re.sub(r'\{(\w*empleado\w*|emp_id)\}', str(eid), camino)
        camino = re.sub(r'\{[^}]+\}', '1', camino)
        st, seg, cuerpo = _pedir(url, camino, cabeceras)
        if st == 422:
            faltan = re.findall(r'"loc":\["query","(\w+)"\]', cuerpo)
            q = {k: tipicos.get(k, '1') for k in (faltan or [])}
            st, seg, cuerpo = _pedir(url, camino + ('?' + urllib.parse.urlencode(q) if q else ''), cabeceras)
        resultados.append({'ruta': camino, 'estado': st, 'seg': seg, 'archivo': archivo, 'funcion': funcion,
                           'detalle': cuerpo[:200] if st >= 500 or st == 0 else ''})
    return resultados


def es_falla(r):
    """Un 500 o una consulta que no responde es falla. Un 503 «no está configurada» es una integración apagada
    en esta copia (por ejemplo Nexacol), no un error del código."""
    if r['estado'] == 503 and 'no está configurada' in r['detalle']:
        return False
    return r['estado'] >= 500 or r['estado'] == 0


if __name__ == '__main__':
    sys.path.insert(0, str(RAIZ / 'backend' / 'tests'))
    os.environ.setdefault('PANTALLAS_URL', 'http://localhost:8001')
    import test_pantallas as tp  # noqa: E402
    from collections import Counter
    res = recorrer(tp.URL, tp._sesion()['access_token'])
    print('total GET:', len(res), Counter(r['estado'] for r in res))
    for r in res:
        if es_falla(r):
            print('FALLA', r['estado'], r['ruta'], r['funcion'], '|', r['detalle'].replace('\n', ' ')[:180])
    lentos = sorted(res, key=lambda r: -r['seg'])[:5]
    print('más lentos:', [(r['ruta'], r['seg']) for r in lentos])
    if len(sys.argv) > 2:
        json.dump(res, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
