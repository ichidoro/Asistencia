# -*- coding: utf-8 -*-
"""Ningún día por revisar queda sin salida.

Se recorren TODAS las combinaciones posibles de una regla (secuencias de 1 a 6 marcas × lectura × qué hace el
sistema × cada subconjunto de opciones de revisión) y se comprueba:
  1. Toda regla que la validación acepta tiene un camino que termina con el día calculado: o el día ya se
     calculó y basta confirmarlo, o con las opciones permitidas la persona puede dejarlo bien marcado
     (ENTRADA · SALIDA repetido) y el motor real lo calcula.
  2. Toda regla que la validación rechaza por «sin salida» de verdad no tiene camino.
  3. «Confirmar» nunca se ofrece ni se acepta en un día que quedó sin calcular.
El camino se busca aquí con una búsqueda propia (marca por marca), distinta de la del módulo, para que la
prueba no se valide a sí misma. Las marcas del motor se generan con matemática a partir del horario de prueba.
"""
import asyncio
import json
import os
from datetime import datetime, timedelta
from itertools import combinations, product

import pytest

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import quantum_matrix_engine as qme  # noqa: E402
from backend.services.quantum_matrix_engine import QuantumMatrixEngine as Q  # noqa: E402
from backend.services.reglas_marcas_def import (  # noqa: E402
    ACCIONES, LECTURAS, MARCA_REVISION_REGLA, OPCIONES_REVISION,
    no_calcula, opciones_efectivas, secuencias_alcanzables, validar_regla,
)

MAX_MARCAS = 6
SECUENCIAS = [''.join(p) for n in range(1, MAX_MARCAS + 1) for p in product('ES', repeat=n)]
SUBCONJUNTOS = [list(c) for k in range(len(OPCIONES_REVISION) + 1) for c in combinations(OPCIONES_REVISION, k)]


def _bien_marcada(s):
    return len(s) >= 2 and len(s) % 2 == 0 and all(c == 'ES'[i % 2] for i, c in enumerate(s))


def _camino_propio(sec, opciones):
    """Búsqueda propia: en una corrección se puede escribir a lo más una ENTRADA y una SALIDA (a cualquier hora) y,
    si se permite cambiar el tipo, cambiar marcas una por una. ¿Se llega a un día bien marcado?"""
    ops = set(opciones)
    inicio = (sec, 'AGREGAR_ENTRADA' in ops, 'AGREGAR_SALIDA' in ops)
    vistos, cola = {inicio}, [inicio]
    while cola:
        s, puede_e, puede_s = cola.pop()
        if _bien_marcada(s):
            return True
        sig = []
        for i in range(len(s) + 1):
            if puede_e:
                sig.append((s[:i] + 'E' + s[i:], False, puede_s))
            if puede_s:
                sig.append((s[:i] + 'S' + s[i:], puede_e, False))
        if 'RECLASIFICAR' in ops:
            for i in range(len(s)):
                sig.append((s[:i] + ('S' if s[i] == 'E' else 'E') + s[i + 1:], puede_e, puede_s))
        for x in sig:
            if x not in vistos:
                vistos.add(x)
                cola.append(x)
    return False


def _todas():
    for sec, lectura, accion, ops in product(SECUENCIAS, LECTURAS, ACCIONES, SUBCONJUNTOS):
        yield {'secuencia': sec, 'lectura': lectura, 'colacion': 'TURNO', 'accion': accion, 'opciones_revision': ops}


def _coherente_sin_salida(r):
    """Las reglas que pasan todas las validaciones de forma (las de antes) y solo podrían caer por la salida."""
    sec, lec, acc, ops = r['secuencia'], r['lectura'], r['accion'], r['opciones_revision']
    if len(sec) == 1 and lec != 'NINGUNA':
        return False
    if lec == 'NINGUNA' and acc != 'SOLO_REVISA':
        return False
    if (acc == 'CALCULA') != (not ops):
        return False
    return True


def test_toda_regla_aceptada_tiene_salida():
    aceptadas = 0
    for r in _todas():
        if validar_regla(r):
            continue
        aceptadas += 1
        if r['accion'] == 'CALCULA':
            continue                                    # se calcula sin revisión
        ef = opciones_efectivas(r)
        if 'CONFIRMAR' in ef:
            assert not no_calcula(r), r                 # confirmar solo existe si el día ya tiene horas
            continue
        assert _camino_propio(r['secuencia'], ef), r
    assert aceptadas > 1000                             # la búsqueda recorrió de verdad las combinaciones


def test_lo_rechazado_por_falta_de_salida_de_verdad_no_tiene_salida():
    for r in _todas():
        if not _coherente_sin_salida(r):
            continue
        sec, ops = r['secuencia'], r['opciones_revision']
        if no_calcula(r) and ('CONFIRMAR' in ops or _bien_marcada(sec)):
            assert validar_regla(r) != '', r            # confirmar sin horas, o un día bien marcado sin calcular
            continue
        if r['accion'] == 'CALCULA' or 'CONFIRMAR' in opciones_efectivas(r):
            assert validar_regla(r) == '', r
            continue
        assert (validar_regla(r) == '') == _camino_propio(sec, ops), r


def test_la_busqueda_del_modulo_coincide_con_la_propia():
    for sec, ops in product(SECUENCIAS, SUBCONJUNTOS):
        del_modulo = any(_bien_marcada(s) for s in secuencias_alcanzables(sec, ops))
        assert del_modulo == _camino_propio(sec, ops), (sec, ops)


def test_confirmar_solo_con_el_dia_calculado():
    base = {'secuencia': 'ESE', 'lectura': 'EXTREMOS', 'colacion': 'TURNO',
            'opciones_revision': ['AGREGAR_SALIDA', 'RECLASIFICAR', 'CONFIRMAR']}
    assert 'CONFIRMAR' in opciones_efectivas(dict(base, accion='CALCULA_Y_REVISA'))
    assert 'CONFIRMAR' not in opciones_efectivas(dict(base, accion='CALCULA_Y_REVISA'), 'ANOMALIA')
    assert 'CONFIRMAR' not in opciones_efectivas(dict(base, accion='SOLO_REVISA'))
    assert 'CONFIRMAR' not in opciones_efectivas(dict(base, accion='SOLO_REVISA', lectura='NINGUNA'))
    assert opciones_efectivas(dict(base, accion='SOLO_REVISA')) == ['AGREGAR_SALIDA', 'RECLASIFICAR']


# ── El camino termina con el motor real calculando el día ─────────────────────

E, S = "Entrada", "Salida"
TURNO = {"tipo_programacion": "CICLO_INTELIGENTE", "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0,
         "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "umbral_horas_colacion": 5.5,
         "anclaje_entrada_minutos": 0, "anclaje_salida_minutos": 0}
DIA = {"es_libre": 0, "horas_teoricas": 9.0, "hora_entrada": "07:00", "hora_salida": "16:30", "cruza_medianoche": 0}
FECHA = "2026-10-15"


def _marcas(sec):
    """Una marca cada hora desde la ENTRADA del horario de prueba (separadas lo suficiente para no ser un doble toque
    ni una marca repetida, y sin huecos de 4 horas que el motor leería como una segunda jornada)."""
    ini = datetime.strptime(f"{FECHA} {DIA['hora_entrada']}", "%Y-%m-%d %H:%M")
    paso = timedelta(hours=1)
    return [{"id": i + 1, "fecha_hora": (ini + paso * i).strftime("%Y-%m-%d %H:%M:%S"),
             "tipo": E if c == 'E' else S, "manual": 0, "observaciones": None} for i, c in enumerate(sec)]


def _motor(monkeypatch, sec):
    monkeypatch.setattr(qme, "_get_now_local", lambda: datetime(2026, 10, 19, 12, 0))
    return Q.solve_attendance_day(fecha=FECHA, empleado_id=1, logs=_marcas(sec), turno_config=TURNO, dia_config=DIA,
                                  global_ajustes={"reglas_marcas_repetidas_minutos": "20"},
                                  todos_ciclos_dia=[DIA], consumidas_previas=set())


@pytest.fixture(autouse=True)
def _registro_limpio():
    qme.REGLAS_MARCAS_ACTIVAS = {}
    qme.REGLAS_MARCAS_REBOTE = None
    yield
    qme.REGLAS_MARCAS_ACTIVAS = {}
    qme.REGLAS_MARCAS_REBOTE = None


def test_revisar_antes_de_calcular_termina_calculado_por_el_motor(monkeypatch):
    """Para cada secuencia de hasta 5 marcas con una regla «Revisar antes de calcular» válida: el motor deja el día
    sin horas; después de la corrección que permiten sus opciones (un día bien marcado) el motor lo calcula."""
    probadas = 0
    for sec in [s for s in SECUENCIAS if len(s) <= 5]:
        for ops in SUBCONJUNTOS:
            regla = {'secuencia': sec, 'lectura': 'NINGUNA', 'colacion': 'TURNO', 'accion': 'SOLO_REVISA',
                     'opciones_revision': ops}
            if validar_regla(regla):
                continue
            destino = min((s for s in secuencias_alcanzables(sec, ops) if _bien_marcada(s)), key=len)
            qme.REGLAS_MARCAS_ACTIVAS = {sec: regla}
            antes = _motor(monkeypatch, sec)
            assert antes["estado"] == "ANOMALIA" and antes["horas_trabajadas"] == 0.0, (sec, ops)
            assert MARCA_REVISION_REGLA in (antes["observaciones"] or "")
            despues = _motor(monkeypatch, destino)
            assert despues["estado"] != "ANOMALIA" and despues["horas_trabajadas"] > 0, (sec, ops, destino, despues)
            probadas += 1
    assert probadas > 100


# ── Repositorio: evaluar y confirmar con los datos del día ────────────────────

class _BaseFalsa:
    """Responde a las consultas del repositorio con un día y una regla; guarda lo que se intentó escribir."""

    def __init__(self, estado, accion, lectura='EXTREMOS', opciones=('AGREGAR_SALIDA', 'RECLASIFICAR', 'CONFIRMAR')):
        self.dia = {'observaciones': MARCA_REVISION_REGLA + 'ENTRADA · SALIDA · ENTRADA). ',
                    'marcas_consumidas_ids': '[11, 12, 13]', 'estado': estado}
        self.regla = {'numero': 26, 'secuencia': 'ESE', 'lectura': lectura, 'colacion': 'TURNO', 'accion': accion,
                      'opciones_revision': json.dumps(list(opciones)), 'activa': 1}
        self.escrituras = []

    async def fetch_one(self, q, params=None):
        if 'FROM asistencias' in q:
            return dict(self.dia)
        if 'FROM reglas_marcas' in q:
            return dict(self.regla)
        if 'FROM revisiones_marcas' in q:
            return None
        if 'periodos_rrhh' in q:
            return {'d': '2026-04-26'}
        return None

    async def fetch_all(self, q, params=None):
        return []

    async def execute(self, q, params=None):
        self.escrituras.append(q)


def _repo(db):
    from backend.repositories.reglas_marcas import ReglasMarcasRepository
    return ReglasMarcasRepository(db)


def test_confirmar_rechaza_un_dia_sin_calcular():
    db = _BaseFalsa('ANOMALIA', 'SOLO_REVISA')
    res = asyncio.run(_repo(db).confirmar_dia(1, FECHA, 1, 'prueba', 'motivo de prueba'))
    assert 'error' in res and not db.escrituras


def test_confirmar_rechaza_si_el_dia_quedo_en_anomalia_aunque_la_regla_calcule():
    db = _BaseFalsa('ANOMALIA', 'CALCULA_Y_REVISA')
    res = asyncio.run(_repo(db).confirmar_dia(1, FECHA, 1, 'prueba', 'motivo de prueba'))
    assert 'error' in res and not db.escrituras


def test_confirmar_acepta_un_dia_calculado_con_aviso():
    db = _BaseFalsa('PRESENTE', 'CALCULA_Y_REVISA')
    res = asyncio.run(_repo(db).confirmar_dia(1, FECHA, 1, 'prueba', 'motivo de prueba'))
    assert res == {'secuencia': 'ESE', 'firma': '11,12,13'} and len(db.escrituras) == 1


def test_evaluar_entrega_el_numero_y_las_opciones_que_de_verdad_sirven():
    db = _BaseFalsa('ANOMALIA', 'SOLO_REVISA')
    ev = asyncio.run(_repo(db).evaluar_dia(1, FECHA))
    assert ev['en_revision'] and ev['regla']['numero'] == 26
    assert ev['regla']['opciones_efectivas'] == ['AGREGAR_SALIDA', 'RECLASIFICAR']
    assert ev['regla']['sin_calcular'] is True


def test_un_dia_confirmado_sin_horas_sigue_en_revision():
    db = _BaseFalsa('ANOMALIA', 'SOLO_REVISA')

    async def ya_confirmado(q, params=None):
        if 'FROM revisiones_marcas' in q:
            return {'username': 'prueba', 'created_at': '2026-11-01'}
        if 'FROM asistencias' in q:
            return dict(db.dia)
        if 'FROM reglas_marcas' in q:
            return dict(db.regla)
        return None
    db.fetch_one = ya_confirmado
    ev = asyncio.run(_repo(db).evaluar_dia(1, FECHA))
    assert ev['en_revision'] is True and ev['confirmado'] is False
    from backend.repositories.reglas_marcas import ReglasMarcasRepository
    assert "a.estado = 'ANOMALIA' OR NOT EXISTS" in ReglasMarcasRepository._SQL_POR_REVISAR


def test_el_vigilante_ve_una_regla_guardada_que_no_pasaria_la_validacion():
    db = _BaseFalsa('ANOMALIA', 'SOLO_REVISA')
    original = db.fetch_all

    async def fetch_all(q, params=None):
        if 'FROM reglas_marcas' in q:
            return [dict(db.regla, id=7, eleccion_colacion='PARECIDA')]
        return await original(q, params)
    db.fetch_all = fetch_all
    v = asyncio.run(_repo(db).vigilante())
    assert [r['numero'] for r in v['reglas_invalidas']] == [26]
    assert 'Confirmar' in v['reglas_invalidas'][0]['motivo']
    assert v['confirmados_sin_calcular'] == [] and v['en_revision_sin_salida'] == []


# ── La ventana no ofrece lo que no sirve ──────────────────────────────────────

def _js(nombre):
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(raiz, 'frontend', 'js', nombre), encoding='utf-8') as f:
        return f.read()


def test_la_ventana_usa_las_opciones_de_la_regla_y_no_guarda_horas_del_horario():
    js = _js('marcaciones_manuales.js')
    assert 'opciones_efectivas' in js                    # los caminos salen de la regla guardada
    assert "regla.numero" in js                          # muestra «Regla N»
    assert '_mmQuitarHorasDelHorario(data.marcas)' in js # con marcas del reloj, sin horas del horario
    assert "'Guardar la SALIDA'" in js and "'Guardar la ENTRADA'" in js
    # al elegir «Se le olvidó marcar…» se propone la hora del horario asignado de ese día, leída de la base
    assert "_mmHoraDelHorario(host, empId, dateStr" in js and "host._horario = data.horario" in js
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(raiz, 'backend', 'routers', 'asistencia.py'), encoding='utf-8') as f:
        router = f.read()
    assert '"horario": {"entrada": (hd or {}).get("hora_entrada_teorica")' in router


def test_la_pantalla_de_reglas_apaga_confirmar_sin_calculo():
    js = _js('reglas_marcas_ui.js')
    assert "o[0] === 'CONFIRMAR' && sinCalcular" in js
    assert "API + 'vigilante/'" in js
    # el ensayo envía lo mismo que se guardaría (sin «Confirmar» en una regla que no calcula)
    assert js.count('opcionesAEnviar(r)') >= 3 and 'opciones_revision: opcionesAEnviar(r)' in js
