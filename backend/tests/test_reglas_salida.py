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
        if 'NO_SE_USA' in ops and len(s) > 1:      # una marca que sobra queda sin usar
            for i in range(len(s)):
                sig.append((s[:i] + s[i + 1:], puede_e, puede_s))
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
    if lec == 'ALTERNADA' and len(sec) % 2 == 1:
        return False
    if lec == 'ORDEN':               # sin orden indicado no se puede guardar (se prueba aparte, con todos los órdenes)
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


def test_las_reglas_entran_en_feriados_con_turno_y_no_en_dias_libres(monkeypatch):
    """Un feriado en que la persona tenía turno entra en las reglas con su horario (decisión del dueño,
    08-11-2026); un día libre de su turno no tiene horario y queda fuera."""
    monkeypatch.setattr(qme, "_get_now_local", lambda: datetime(2026, 10, 19, 12, 0))
    qme.REGLAS_MARCAS_ACTIVAS = {"SES": {"secuencia": "SES", "lectura": "NINGUNA", "colacion": "TURNO", "accion": "SOLO_REVISA",
                                         "opciones_revision": ["AGREGAR_ENTRADA", "RECLASIFICAR"]}}
    logs = [{"id": 1, "fecha_hora": f"{FECHA} 12:47:02", "tipo": S, "manual": 0, "observaciones": None},
            {"id": 2, "fecha_hora": f"{FECHA} 13:17:08", "tipo": E, "manual": 0, "observaciones": None},
            {"id": 3, "fecha_hora": f"{FECHA} 16:35:42", "tipo": S, "manual": 0, "observaciones": None}]
    dia = lambda **k: Q.solve_attendance_day(fecha=FECHA, empleado_id=1, logs=[dict(l) for l in logs], turno_config=TURNO,
                                             global_ajustes={"reglas_marcas_repetidas_minutos": "20"},
                                             todos_ciclos_dia=[DIA], consumidas_previas=set(), **k)
    habil = dia(dia_config=DIA)
    assert MARCA_REVISION_REGLA in (habil["observaciones"] or "")
    feriado = dia(dia_config=DIA, is_holiday=True)
    assert MARCA_REVISION_REGLA in (feriado["observaciones"] or "")
    libre = dia(dia_config=dict(DIA, es_libre=1, horas_teoricas=0))
    assert MARCA_REVISION_REGLA not in (libre["observaciones"] or "")


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
    # si la regla no permite escribir marcas, no se ofrece «Habilitar edición» (con d-none: d-flex le gana a display:none)
    assert "_mmPermitirEscribirMarcas(caminos.some(o => o.startsWith('AGREGAR_')))" in js
    assert "b.classList.toggle('d-none', !permitir)" in js
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(raiz, 'backend', 'routers', 'asistencia.py'), encoding='utf-8') as f:
        router = f.read()
    assert 'horario = {"entrada": (hd or {}).get("hora_entrada_teorica")' in router and '"horario": horario' in router
    # con una sola marca, la hora sale del ciclo que calza con el tipo de esa marca
    assert "ciclo_para_marca_sola(" in router and "FROM turno_dias WHERE turno_id = ? AND dia_semana = ?" in router
    # falta la ENTRADA → la marca es la SALIDA; falta la SALIDA → la marca es la ENTRADA (aunque el reloj la rotule al revés)
    assert '"entrada": como_salida["hora_entrada"], "salida": como_entrada["hora_salida"]' in router


def test_la_pantalla_de_reglas_apaga_confirmar_sin_calculo():
    js = _js('reglas_marcas_ui.js')
    assert "o[0] === 'CONFIRMAR' && sinCalcular" in js
    assert "API + 'vigilante/'" in js
    # el orden lo indica la persona: tabla por marca y el orden viaja al ensayo y al guardar
    assert "data-rmx-orden" in js and "orden_marcas: ordenAEnviar(r)" in js and js.count("orden_marcas: ordenAEnviar(r)") == 2
    # el ensayo envía lo mismo que se guardaría (sin «Confirmar» en una regla que no calcula)
    assert js.count('opcionesAEnviar(r)') >= 3 and 'opciones_revision: opcionesAEnviar(r)' in js


# ── Lectura «como las ordena el sistema» (ALTERNADA) ─────────────────────────

def test_la_lectura_alternada_solo_vale_con_marcas_pares():
    for sec in SECUENCIAS:
        r = {'secuencia': sec, 'lectura': 'ALTERNADA', 'colacion': 'MEDIDA', 'accion': 'CALCULA', 'opciones_revision': []}
        assert (validar_regla(r) == '') == (len(sec) % 2 == 0), sec


def test_la_lectura_alternada_es_la_misma_propuesta_de_la_ventana():
    """Para cada secuencia par, el motor lee las marcas en el mismo orden que propone sugerir_clasificacion_marcas."""
    from backend.routers.asistencia import sugerir_clasificacion_marcas
    from backend.services.quantum_matrix_engine import _aplicar_alternada
    for sec in (s for s in SECUENCIAS if len(s) % 2 == 0):
        marcas = _marcas(sec)
        propuesta = [x['tipo'] for x in sugerir_clasificacion_marcas([m['fecha_hora'] for m in marcas])]
        assert [m['tipo'] for m in _aplicar_alternada(marcas)] == propuesta, sec


def test_alternada_mide_la_colacion_cuando_la_vuelta_se_marco_como_salida(monkeypatch):
    """ENTRADA 06:57 · SALIDA 12:54 · SALIDA 13:29 · SALIDA 16:30 (la vuelta de colación quedó como SALIDA).
    Con la lectura alternada se mide la pausa de 35 min, igual que si una persona cambiara la 3.ª a ENTRADA."""
    monkeypatch.setattr(qme, "_get_now_local", lambda: datetime(2026, 10, 19, 12, 0))
    marcas = [{"id": i + 1, "fecha_hora": f"{FECHA} {h}:00", "tipo": t, "manual": 0, "observaciones": None}
              for i, (h, t) in enumerate((("06:57", E), ("12:54", S), ("13:29", S), ("16:30", S)))]
    corregidas = [dict(m, tipo=(E if m["id"] == 3 else m["tipo"])) for m in marcas]

    def calcular(logs):
        return Q.solve_attendance_day(fecha=FECHA, empleado_id=1, logs=[dict(l) for l in logs], turno_config=TURNO,
                                      dia_config=DIA, global_ajustes={"reglas_marcas_repetidas_minutos": "20"},
                                      todos_ciclos_dia=[DIA], consumidas_previas=set())
    qme.REGLAS_MARCAS_ACTIVAS = {"ESSS": {"secuencia": "ESSS", "lectura": "ALTERNADA", "colacion": "MEDIDA",
                                          "accion": "CALCULA"}}
    auto = calcular(marcas)
    qme.REGLAS_MARCAS_ACTIVAS = {}
    a_mano = calcular(corregidas)
    assert auto["estado"] != "ANOMALIA" and MARCA_REVISION_REGLA not in (auto["observaciones"] or "")
    assert auto["horas_trabajadas"] == a_mano["horas_trabajadas"]
    assert auto["minutos_colacion"] == a_mano["minutos_colacion"] == 35
    assert [m["tipo"] for m in marcas] == [E, S, S, S]        # las marcas no se tocan


# ── Lectura «en el orden que indico» (ORDEN): el orden lo define la persona en la pantalla ──────────────

def _todos_los_ordenes(n):
    return [''.join(p) for p in product('ES-', repeat=n)]


def test_el_orden_se_acepta_solo_si_deja_el_dia_calculable():
    """Todas las secuencias de hasta 5 marcas × todos los órdenes posibles: se acepta si y solo si, sin las marcas que
    no se usan, queda ENTRADA · SALIDA repetido (lo que el motor sabe calcular)."""
    from backend.services.reglas_marcas_def import validar_orden
    probados = 0
    for sec in (s for s in SECUENCIAS if len(s) <= 5):
        for orden in _todos_los_ordenes(len(sec)):
            r = {'secuencia': sec, 'lectura': 'ORDEN', 'orden_marcas': orden, 'colacion': 'MEDIDA',
                 'accion': 'CALCULA', 'opciones_revision': []}
            assert (validar_regla(r) == '') == _bien_marcada(orden.replace('-', '')), (sec, orden)
            assert (validar_orden(sec, orden) == '') == _bien_marcada(orden.replace('-', ''))
            probados += 1
        assert validar_regla({'secuencia': sec, 'lectura': 'ORDEN', 'orden_marcas': None, 'colacion': 'MEDIDA',
                              'accion': 'CALCULA', 'opciones_revision': []}) != ''
    assert probados > 300


def test_la_propuesta_del_orden_es_la_de_la_ventana():
    from backend.routers.asistencia import sugerir_clasificacion_marcas
    from backend.services.reglas_marcas_def import orden_propuesto
    for sec in SECUENCIAS:
        marcas = _marcas(sec)
        propuesta = ''.join(x['tipo'][0] for x in sugerir_clasificacion_marcas([m['fecha_hora'] for m in marcas]))
        assert orden_propuesto(sec) == propuesta.upper(), sec


def test_el_motor_lee_el_orden_guardado_y_descarta_las_que_no_se_usan(monkeypatch):
    """ENTRADA 08:00 · ENTRADA 08:12 (doble toque) · SALIDA 14:23 (doble) · SALIDA 16:30 con el orden E--S:
    se calcula de 08:00 a 16:30, igual que si el día tuviera solo esas dos marcas. Las marcas no se tocan."""
    monkeypatch.setattr(qme, "_get_now_local", lambda: datetime(2026, 10, 19, 12, 0))
    marcas = [{"id": i + 1, "fecha_hora": f"{FECHA} {h}:00", "tipo": t, "manual": 0, "observaciones": None}
              for i, (h, t) in enumerate((("08:00", E), ("08:12", E), ("14:23", S), ("16:30", S)))]
    solo_dos = [marcas[0], marcas[3]]

    def calcular(logs):
        return Q.solve_attendance_day(fecha=FECHA, empleado_id=1, logs=[dict(l) for l in logs], turno_config=TURNO,
                                      dia_config=DIA, global_ajustes={"reglas_marcas_repetidas_minutos": "20"},
                                      todos_ciclos_dia=[DIA], consumidas_previas=set())
    qme.REGLAS_MARCAS_ACTIVAS = {"EESS": {"secuencia": "EESS", "lectura": "ORDEN", "orden_marcas": "E--S",
                                          "colacion": "TURNO", "accion": "CALCULA"}}
    por_orden = calcular(marcas)
    qme.REGLAS_MARCAS_ACTIVAS = {}
    a_mano = calcular(solo_dos)
    assert por_orden["horas_trabajadas"] == a_mano["horas_trabajadas"] > 0
    assert por_orden["hora_entrada_real"] == "08:00:00" and por_orden["hora_salida_real"] == "16:30:00"
    assert "orden indicado" in (por_orden["observaciones"] or "")
    assert [m["tipo"] for m in marcas] == [E, E, S, S]


def test_el_orden_propuesto_da_lo_mismo_que_la_lectura_alternada(monkeypatch):
    from backend.services.reglas_marcas_def import orden_propuesto
    monkeypatch.setattr(qme, "_get_now_local", lambda: datetime(2026, 10, 19, 12, 0))
    for sec in (s for s in SECUENCIAS if len(s) % 2 == 0 and len(s) <= 6):
        qme.REGLAS_MARCAS_ACTIVAS = {sec: {"secuencia": sec, "lectura": "ALTERNADA", "colacion": "MEDIDA", "accion": "CALCULA"}}
        a = _motor(monkeypatch, sec)
        qme.REGLAS_MARCAS_ACTIVAS = {sec: {"secuencia": sec, "lectura": "ORDEN", "orden_marcas": orden_propuesto(sec),
                                           "colacion": "MEDIDA", "accion": "CALCULA"}}
        b = _motor(monkeypatch, sec)
        assert (a["estado"], a["horas_trabajadas"], a["minutos_colacion"]) == (b["estado"], b["horas_trabajadas"], b["minutos_colacion"]), sec


# ── Propuesta de la marca que falta con un horario de varios ciclos ──────────────────────────────────────

def test_con_una_marca_sola_se_propone_el_ciclo_que_calza_con_su_tipo():
    """Horario con tres ciclos el mismo día (como los de Mantención): Noche 23:00–07:00, Mañana 07:00–15:00,
    Tarde 15:00–23:00. Una SALIDA se compara con la salida de cada ciclo y una ENTRADA con la entrada,
    en el reloj de 24 horas."""
    from backend.routers.asistencia import ciclo_para_marca_sola
    ciclos = [{"hora_entrada": "23:00", "hora_salida": "07:00"},
              {"hora_entrada": "07:00", "hora_salida": "15:00"},
              {"hora_entrada": "15:00", "hora_salida": "23:00"}]
    assert ciclo_para_marca_sola(ciclos, "15:21", "Salida")["hora_entrada"] == "07:00"   # salió de la Mañana
    assert ciclo_para_marca_sola(ciclos, "15:21", "Entrada")["hora_entrada"] == "15:00"  # entró a la Tarde
    assert ciclo_para_marca_sola(ciclos, "22:50", "Entrada")["hora_entrada"] == "23:00"  # entró a la Noche
    assert ciclo_para_marca_sola(ciclos, "06:55", "Salida")["hora_entrada"] == "23:00"   # salió de la Noche
    assert ciclo_para_marca_sola(ciclos, "23:40", "Salida")["hora_entrada"] == "15:00"   # cruza la medianoche
    assert ciclo_para_marca_sola([], "15:21", "Salida") is None
    assert ciclo_para_marca_sola(ciclos, "15:21", "") is None


def test_ventana_marca_el_doble_toque_igual_que_el_calculo():
    """La ventana muestra como «no se usa» la marca que el cálculo deja fuera por doble toque (dos marcas a menos del
    rebote), aunque sean de distinto tipo: así ve las mismas marcas que la regla."""
    from backend.routers.asistencia import marcas_doble_toque
    rows = [
        {"id": 1, "fecha_hora": "2026-08-31 06:58:08", "tipo": "Entrada", "manual": 0},
        {"id": 2, "fecha_hora": "2026-08-31 13:28:29", "tipo": "Salida", "manual": 0},
        {"id": 3, "fecha_hora": "2026-08-31 13:53:09", "tipo": "Entrada", "manual": 0},
        {"id": 4, "fecha_hora": "2026-08-31 13:54:57", "tipo": "Salida", "manual": 0},
    ]
    dt = marcas_doble_toque(rows, 180)
    assert list(dt) == [4]
    assert dt[4] == {"hora": "13:53:09", "segundos": 108}
    # Con una SALIDA escrita después, el doble toque sigue fuera y quedan ENTRADA·SALIDA·ENTRADA·SALIDA
    rows.append({"id": 5, "fecha_hora": "2026-08-31 16:30:00", "tipo": "Salida", "manual": 1})
    assert list(marcas_doble_toque(rows, 180)) == [4]
    # Fuera del rebote no se descarta nada
    assert marcas_doble_toque(rows, 60) == {}
    router = open(os.path.join(os.path.dirname(__file__), "..", "routers", "asistencia.py"), encoding="utf-8").read()
    assert '"doble_toque": doble_toque.get(r["id"])' in router
    js = open(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "js", "marcaciones_manuales.js"), encoding="utf-8").read()
    assert "No se usa · doble toque" in js and "se usan " in js


def test_propuesta_tres_marcas_con_el_horario():
    """Regla 6 (E·E·E) y cualquier día de 3 marcas: falta una o sobra una; una o dos opciones completas que salen de comparar
    con el horario y, para la marca de colación, con la hora a la que sale y vuelve de colación su mismo horario."""
    from backend.services.reglas_marcas_def import propuesta_tres_marcas
    p = lambda m, e, s, col=0, tip=None: propuesta_tres_marcas(m, e, s, 20, 150, col, tip)
    resumen = lambda r: [(o['clave'], o['tipos'], o['marca']) for o in r['opciones']]
    # Falta la SALIDA final: entrada a la hora y una colación de 28 min al final → una sola opción, completa
    r = p(['2026-05-18 06:58:56', '2026-05-18 13:31:31', '2026-05-18 13:59:23'], '07:00', '16:30')
    assert r['combinacion'] == 1
    assert resumen(r) == [('FALTA_SALIDA', ['Entrada', 'Salida', 'Entrada'], {'tipo': 'Salida', 'hora': '16:30'})]
    assert '16:30' in r['opciones'][0]['motivo']
    r = p(['2026-08-11 07:54:39', '2026-08-11 15:19:20', '2026-08-11 15:41:55'], '08:00', '17:30')
    assert resumen(r) == [('FALTA_SALIDA', ['Entrada', 'Salida', 'Entrada'], {'tipo': 'Salida', 'hora': '17:30'})]
    # Están la entrada y la salida (ninguna pausa es colación: 154 min > 150): la del medio no se usa, siempre
    marcas_medio = ['2026-06-11 07:01:30', '2026-06-11 12:56:55', '2026-06-11 15:30:21']
    assert resumen(p(marcas_medio, '07:00', '15:30')) == [('SOBRA_MEDIO', ['Entrada', 'No se usa', 'Salida'], None)]
    # … y, con la colación de su horario (30 min) y a qué hora sale (13:00) y vuelve (13:31) su horario, la marca de
    # colación que calza: 12:56 está más cerca de la salida → faltó la vuelta, a las 13:26
    tip = {'sale': 13 * 60, 'vuelve': 13 * 60 + 31}
    r = p(marcas_medio, '07:00', '15:30', 30, tip)
    assert resumen(r) == [('SOBRA_MEDIO', ['Entrada', 'No se usa', 'Salida'], None),
                          ('FALTA_VUELTA', ['Entrada', 'Salida', 'Salida'], {'tipo': 'Entrada', 'hora': '13:26'})]
    assert 'salió a las 12:56' in r['opciones'][1]['motivo'] and '13:00' in r['opciones'][1]['motivo']
    # Si la del medio queda más cerca de la hora en que vuelven, faltó la salida a colación (esa hora − 30)
    r = p(['2026-06-11 07:01:30', '2026-06-11 13:35:00', '2026-06-11 15:30:21'], '07:00', '15:30', 30, tip)
    assert resumen(r)[1] == ('FALTA_SALIDA_COLACION', ['Entrada', 'Entrada', 'Salida'], {'tipo': 'Salida', 'hora': '13:05'})
    # Sin datos de su horario o sin minutos de colación: solo «no se usa»
    assert len(p(marcas_medio, '07:00', '15:30', 30, None)['opciones']) == 1
    assert len(p(marcas_medio, '07:00', '15:30', 0, tip)['opciones']) == 1
    # Pausa de 148 min que termina a la hora de salida: la última ES la salida → sobra la del medio (no falta nada)
    assert p(['2026-04-27 07:01:00', '2026-04-27 14:03:00', '2026-04-27 16:31:00'], '07:00', '16:30')['combinacion'] == 6
    # Pausa al comienzo y salida a la hora: falta la ENTRADA aunque la segunda pausa también mida como colación
    assert p(['2026-05-14 12:58:00', '2026-05-14 13:32:00', '2026-05-14 15:33:00'], '07:00', '15:30')['combinacion'] == 2
    # Falta la ENTRADA inicial
    r = p(['2026-06-11 12:30:00', '2026-06-11 13:00:00', '2026-06-11 15:31:00'], '07:00', '15:30')
    assert resumen(r) == [('FALTA_ENTRADA', ['Salida', 'Entrada', 'Salida'], {'tipo': 'Entrada', 'hora': '07:00'})]
    # Turno de noche (cruza la medianoche): falta la SALIDA
    r = p(['2026-06-11 22:58:00', '2026-06-12 03:00:00', '2026-06-12 03:30:00'], '23:00', '07:00')
    assert r['combinacion'] == 1 and r['opciones'][0]['marca']['hora'] == '07:00'
    # Dos pausas de colación seguidas: no se puede saber → sin propuesta
    assert p(['2026-06-11 13:00:00', '2026-06-11 13:30:00', '2026-06-11 14:00:00'], '07:00', '15:30') is None
    # Sin horario, o sin 3 marcas: sin propuesta
    assert p(['2026-06-11 07:00:00', '2026-06-11 12:00:00', '2026-06-11 15:30:00'], None, '15:30') is None
    assert p(['2026-06-11 07:00:00', '2026-06-11 15:30:00'], '07:00', '15:30') is None


def test_entrada_entrada_salida_falta_la_salida_a_colacion():
    """Regla 9 (E·E·S): con los tipos del reloj, la del medio es la vuelta de colación → faltó la salida a colación, a la
    hora de la vuelta − los minutos de colación del horario; la segunda opción es que la del medio no se usa."""
    from backend.services.reglas_marcas_def import propuesta_tres_marcas
    ees = ['Entrada', 'Entrada', 'Salida']
    p = lambda m, e, s, col, tip=None: propuesta_tres_marcas(m, e, s, 20, 150, col, tip, tipos=ees)
    resumen = lambda r: [(o['clave'], o['tipos'], o['marca']) for o in r['opciones']]
    tip = {'sale': 13 * 60, 'vuelve': 13 * 60 + 31}
    esperado = lambda h, medio: [('FALTA_SALIDA_COLACION', ees, {'tipo': 'Salida', 'hora': h}),
                                 ('SOBRA_MEDIO', ['Entrada', 'No se usa', 'Salida'], None)]
    # La del medio a la hora en que vuelven de colación
    r = p(['2026-05-27 06:46:10', '2026-05-27 13:30:05', '2026-05-27 15:33:00'], '07:00', '15:30', 30, tip)
    assert resumen(r) == esperado('13:00', '13:30')
    assert 'volvió a las 13:30' in r['opciones'][0]['motivo'] and '30 min' in r['opciones'][0]['motivo']
    # Vuelve antes de la hora en que suelen salir: igual falta la salida a colación (el reloj dijo ENTRADA)
    r = p(['2026-08-12 06:52:00', '2026-08-12 12:59:00', '2026-08-12 15:39:00'], '07:00', '15:30', 30, tip)
    assert resumen(r) == esperado('12:29', '12:59')
    # Sale del turno antes de su horario: la salida del turno no se reemplaza por la del horario
    r = p(['2026-10-30 06:49:00', '2026-10-30 13:32:00', '2026-10-30 14:23:00'], '07:00', '15:30', 30, tip)
    assert resumen(r) == esperado('13:02', '13:32')
    # Horario con 60 min de colación
    r = p(['2026-09-03 07:59:00', '2026-09-03 16:33:00', '2026-09-03 18:23:00'], '08:00', '17:00', 60)
    assert r['opciones'][0]['marca'] == {'tipo': 'Salida', 'hora': '15:33'}
    # La salida a colación quedaría antes de la llegada, o el horario no tiene minutos de colación: decide la persona
    assert p(['2026-08-07 06:12:00', '2026-08-07 06:21:00', '2026-08-07 15:11:00'], '11:30', '20:00', 30) is None
    assert p(['2026-05-27 06:46:10', '2026-05-27 13:30:05', '2026-05-27 15:33:00'], '07:00', '15:30', 0) is None
    # Sin los tipos, la propuesta sigue siendo la de siempre (reglas 6 y 27)
    r = propuesta_tres_marcas(['2026-08-12 06:52:00', '2026-08-12 12:59:00', '2026-08-12 15:39:00'], '07:00', '15:30',
                              20, 150, 30, tip)
    assert r['combinacion'] == 6 and r['opciones'][0]['clave'] == 'SOBRA_MEDIO'


def test_entrada_salida_salida_falta_la_vuelta_de_colacion():
    """Regla 8 (E·S·S): con los tipos del reloj, la del medio es la salida a colación → faltó la vuelta, a esa hora + los
    minutos de colación del horario. Si la vuelta no cabe antes de la última marca, la del medio es la vuelta y faltó la
    salida a colación. La segunda opción es siempre que la del medio no se usa."""
    from backend.services.reglas_marcas_def import propuesta_tres_marcas
    ess = ['Entrada', 'Salida', 'Salida']
    p = lambda m, e, s, col, tip=None: propuesta_tres_marcas(m, e, s, 20, 150, col, tip, tipos=ess)
    resumen = lambda r: [(o['clave'], o['tipos'], o['marca']) for o in r['opciones']]
    sobra = ('SOBRA_MEDIO', ['Entrada', 'No se usa', 'Salida'], None)
    tip = {'sale': 13 * 60, 'vuelve': 13 * 60 + 31}
    # Faltó la vuelta, aunque la del medio quede cerca de la hora en que su horario vuelve de colación
    r = p(['2026-08-25 06:57:00', '2026-08-25 13:28:00', '2026-08-25 16:29:00'], '07:00', '16:30', 30, tip)
    assert r['combinacion'] == 8
    assert resumen(r) == [('FALTA_VUELTA', ess, {'tipo': 'Entrada', 'hora': '13:58'}), sobra]
    assert 'salió a las 13:28' in r['opciones'][0]['motivo'] and '30 min' in r['opciones'][0]['motivo']
    # Horario con 60 min de colación; salida del turno lejos de su horario: no se toca
    r = p(['2026-05-22 07:47:00', '2026-05-22 13:18:00', '2026-05-22 20:15:00'], '07:00', '15:00', 60)
    assert r['opciones'][0]['marca'] == {'tipo': 'Entrada', 'hora': '14:18'}
    # La vuelta caería después de la última marca: la del medio pasa a ENTRADA y falta la salida a colación
    r = p(['2026-09-11 07:01:00', '2026-09-11 16:16:00', '2026-09-11 16:25:00'], '11:30', '20:00', 30)
    assert resumen(r) == [('FALTA_SALIDA_COLACION', ['Entrada', 'Entrada', 'Salida'], {'tipo': 'Salida', 'hora': '15:46'}),
                          sobra]
    # Turno de noche que cruza la medianoche
    r = p(['2026-06-03 20:58:00', '2026-06-03 23:50:00', '2026-06-04 05:56:00'], '21:00', '06:00', 30)
    assert r['opciones'][0]['marca'] == {'tipo': 'Entrada', 'hora': '00:20'}
    # Ninguna de las dos cabe, o el horario no tiene minutos de colación: decide la persona
    assert p(['2026-09-11 16:00:00', '2026-09-11 16:16:00', '2026-09-11 16:25:00'], '11:30', '20:00', 30) is None
    assert p(['2026-08-25 06:57:00', '2026-08-25 13:28:00', '2026-08-25 16:29:00'], '07:00', '16:30', 0) is None
    # En la ventana, la marca que no se usa arrastra su doble toque (si no, la descartada vuelve a contar)
    base = os.path.join(os.path.dirname(__file__), "..")
    router = open(os.path.join(base, "routers", "asistencia.py"), encoding="utf-8").read()
    assert "tipos_op[str(id_dt)] = TIPO_NO_SE_USA" in router and "doble_toque=None):" in router

def test_cinco_marcas_sobra_una_y_queda_como_la_regla_2():
    """Reglas 16 a 21 (5 marcas): la primera y la última fijas; una del medio no se usa y, si hace falta, otra cambia de
    tipo (queda E·S·E·S). Gana la que cambia menos tipos y, con empate, la colación más parecida a la del horario; si las
    dos primeras empatan en cambios se ofrecen las dos. Al final, siempre, solo la primera y la última."""
    from backend.services.reglas_marcas_def import propuesta_cinco_marcas
    d = lambda *hs: [f'2026-07-02 {h}:00' for h in hs]
    tp = lambda s: ['Entrada' if c == 'E' else 'Salida' for c in s]
    N = 'No se usa'
    ext = ['Entrada', N, N, N, 'Salida']
    resumen = lambda r: [o['tipos'] for o in r['opciones']]
    # E·S·E·S·S: sobra la penúltima salida (la última es la salida del día)
    r = propuesta_cinco_marcas(d('06:53', '12:55', '13:32', '15:30', '15:37'), tp('ESESS'), 30)
    assert r['combinacion'] == 5 and resumen(r) == [['Entrada', 'Salida', 'Entrada', N, 'Salida'], ext]
    assert r['opciones'][0]['titulo'].startswith('La de las 15:30 no se usa')
    # E·E·S·S·S: sobra la segunda entrada y la vuelta estaba marcada como salida
    r = propuesta_cinco_marcas(d('06:48', '06:56', '12:55', '13:32', '15:34'), tp('EESSS'), 30)
    assert resumen(r) == [['Entrada', N, 'Salida', 'Entrada', 'Salida'], ext]
    assert 'la de las 13:32 es ENTRADA' in r['opciones'][0]['titulo']
    # E·S·E·E·S: empate en cambios → las dos, primero la colación más parecida a la del horario (35 vs 20 min, horario 30)
    r = propuesta_cinco_marcas(d('06:55', '12:56', '13:16', '13:31', '16:34'), tp('ESEES'), 30)
    assert resumen(r) == [['Entrada', 'Salida', N, 'Entrada', 'Salida'], ['Entrada', 'Salida', 'Entrada', N, 'Salida'], ext]
    # E·S·S·S·S: tres con un cambio; se ofrecen las dos de colación más parecida (31 y 27 min)
    r = propuesta_cinco_marcas(d('06:51', '13:01', '13:28', '13:32', '15:35'), tp('ESSSS'), 30)
    assert resumen(r)[:2] == [['Entrada', 'Salida', N, 'Entrada', 'Salida'], ['Entrada', 'Salida', 'Entrada', N, 'Salida']]
    # No empieza con ENTRADA o no son 5: decide la persona
    assert propuesta_cinco_marcas(d('06:51', '13:01', '13:28', '13:32', '15:35'), tp('SESES'), 30) is None
    assert propuesta_cinco_marcas(d('06:51', '13:01', '15:35'), tp('ESS'), 30) is None

def test_propuesta_reglas_26_27_6_28_29():
    """Reglas impares con propuesta según los tipos: ESE → faltó la SALIDA del horario; SES → faltó la ENTRADA del horario;
    EEE → la del medio es la salida a colación y gana lo que más se parece (pausa 2.ª–3.ª vs colación, o 3.ª vs salida);
    una marca sola → falta la otra, a la hora del horario."""
    from backend.services.reglas_marcas_def import propuesta_tres_marcas, propuesta_una_marca
    d = lambda *hs: [f'2026-08-11 {h}:00' for h in hs]
    tp = lambda s: ['Entrada' if c == 'E' else 'Salida' for c in s]
    p = lambda m, e, s, col, tipos: propuesta_tres_marcas(m, e, s, 20, 150, col, None, tipos=tp(tipos))
    resumen = lambda r: [(o['clave'], o['tipos'], (o['marca'] or {}).get('hora')) for o in r['opciones']]
    N = 'No se usa'
    # 26 · E·S·E sin la salida final
    r = p(d('07:01', '12:57', '13:19'), '07:00', '15:30', 30, 'ESE')
    assert r['combinacion'] == 26 and resumen(r) == [('FALTA_SALIDA', ['Entrada', 'Salida', 'Entrada'], '15:30')]
    # 27 · S·E·S sin la entrada inicial
    r = p(d('12:58', '13:32', '15:33'), '07:00', '15:30', 30, 'SES')
    assert r['combinacion'] == 27 and resumen(r) == [('FALTA_ENTRADA', ['Salida', 'Entrada', 'Salida'], '07:00')]
    # 6 · E·E·E: pausa de 22 min (colación 30) → la 3.ª es la vuelta, faltó la SALIDA
    r = p(d('07:54', '15:19', '15:41'), '08:00', '17:30', 30, 'EEE')
    assert resumen(r) == [('FALTA_SALIDA', ['Entrada', 'Salida', 'Entrada'], '17:30'), ('SOBRA_MEDIO', ['Entrada', N, 'Salida'], None)]
    # 6 · E·E·E: la 3.ª es justo la salida del horario → faltó la vuelta de colación
    r = p(d('07:01', '12:56', '15:30'), '07:00', '15:30', 30, 'EEE')
    assert resumen(r) == [('FALTA_VUELTA', ['Entrada', 'Salida', 'Salida'], '13:26'), ('SOBRA_MEDIO', ['Entrada', N, 'Salida'], None)]
    # La marca que se escribe debe caer dentro de la jornada: E·S·E que termina después de la salida del horario
    assert p(d('07:01', '12:57', '16:10'), '07:00', '15:30', 30, 'ESE') is None
    # 28 y 29 · una sola marca (también de noche)
    r = propuesta_una_marca('2026-08-11 06:58:00', 'Entrada', '07:00', '16:30')
    assert r['combinacion'] == 28 and resumen(r) == [('FALTA_SALIDA', ['Entrada'], '16:30')]
    r = propuesta_una_marca('2026-06-20 04:07:00', 'Salida', '23:00', '04:00')
    assert r['combinacion'] == 29 and resumen(r) == [('FALTA_ENTRADA', ['Salida'], '23:00')]
    assert propuesta_una_marca('2026-06-20 04:07:00', 'Salida', None, None) is None
    base = os.path.join(os.path.dirname(__file__), "..")
    router = open(os.path.join(base, "routers", "asistencia.py"), encoding="utf-8").read()
    assert "len(usadas) in (1, 3, 5)" in router and "propuesta_una_marca(fhs[0]" in router

def test_ventana_de_tres_marcas_con_opciones_y_un_solo_guardar():
    """La ventana muestra las opciones completas (la primera elegida), lo que paga cada una, «Otra cosa» y un solo Guardar;
    la colación de su horario sale de las marcas reales (mediana), sin horas escritas en el código."""
    base = os.path.join(os.path.dirname(__file__), "..")
    router = open(os.path.join(base, "routers", "asistencia.py"), encoding="utf-8").read()
    assert "async def _colacion_tipica(" in router and "statistics.median(sale)" in router
    assert "transformar_logs=transformar" in router and "collect_only=True" in router
    assert "secuencia_en_revision(hd.get(\"observaciones\"))" in router   # solo en días en revisión
    servicio = open(os.path.join(base, "services", "asistencia_service.py"), encoding="utf-8").read()
    assert "transformar_logs solo se usa para simular (collect_only=True)" in servicio
    js = open(os.path.join(base, "..", "frontend", "js", "marcaciones_manuales.js"), encoding="utf-8").read()
    for texto in ("function _mmOpcionesTres(", "Otra cosa:", "marcacionesManualesState.guardarOpcion", "Hora indicada por quien revisó",
                  "_mmOpcionPermitida(op, mx, opciones)", "function _mmPintarDia(", "function _mmLineaTiempo(", "mm-fila-nueva"):
        assert texto in js, texto


def test_ventana_ingreso_manual_en_dos_columnas_conserva_todo():
    """La ventana «Corregir marcas del día» en dos columnas mantiene todos sus elementos (los usa marcaciones_manuales.js) y
    suma «Horario del día» y «Cálculo»."""
    base = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
    html = open(os.path.join(base, "index.html"), encoding="utf-8").read()
    i = html.index('id="modal-marcacion-manual"')
    modal = html[i:html.index('<!-- Modal de Decisión', i)]
    for ident in ("manual-empleado-display", "manual-area-display", "manual-cargo-display", "manual-turno-display",
                  "manual-fecha-display", "manual-alert-faltante", "manual-alert-huerfana", "manual-hora-entrada",
                  "manual-hora-salida", "divTramosBolsa", "manual-minutos-conduccion", "manual-minutos-espera",
                  "manual-observaciones", "btn-unlock-manual", "mm-col-marcas", "mm-h-jornada", "mm-h-colacion", "mm-h-sale",
                  "mm-c-horas", "mm-c-atraso", "mm-c-sal", "mm-c-deuda"):
        assert f'id="{ident}"' in modal, ident
    assert "modal-xl" in modal and 'class="mm-grid"' in modal
    assert 'onclick="saveManualEntry()"' in modal and 'onclick="closeManualEntryModal()"' in modal
    css = open(os.path.join(base, "css", "ventanas.css"), encoding="utf-8").read()
    assert "#modal-marcacion-manual .mm-grid { display: grid; grid-template-columns: 300px minmax(0, 1fr)" in css
    router = open(os.path.join(base, "..", "backend", "routers", "asistencia.py"), encoding="utf-8").read()
    assert '"calculo": ({"estado": hd.get("estado")' in router and '"colacion_tipica": tipica' in router


def test_no_se_usa_es_una_salida_de_la_revision():
    """«Dejar sin usar una marca que sobra» (NO_SE_USA) lleva E·E·E a la regla 1 y la validación lo cuenta como salida."""
    from backend.services.reglas_marcas_def import OPCIONES_REVISION, secuencias_alcanzables, tiene_salida, validar_regla
    assert 'NO_SE_USA' in OPCIONES_REVISION
    assert not tiene_salida('EEE', ['NO_SE_USA'])            # sin cambiar tipos, E·E sigue sin SALIDA
    assert tiene_salida('EEE', ['NO_SE_USA', 'RECLASIFICAR'])
    assert 'ES' in secuencias_alcanzables('EEE', ['NO_SE_USA', 'RECLASIFICAR'])
    assert 'ES' in secuencias_alcanzables('ESE', ['NO_SE_USA'])  # sobra la última ENTRADA
    regla = {'secuencia': 'EEE', 'lectura': 'NINGUNA', 'colacion': 'TURNO', 'accion': 'SOLO_REVISA',
             'opciones_revision': ['RECLASIFICAR', 'NO_SE_USA', 'AGREGAR_SALIDA', 'AGREGAR_ENTRADA']}
    assert validar_regla(regla) == ''


def test_el_calculo_no_lee_las_marcas_que_no_se_usan():
    """La marca «No se usa» queda guardada y se ve en la ventana, pero el motor no la lee."""
    from backend.repositories.asistencia import LOGS_CON_TIPO_CORREGIDO, LOGS_CON_TIPO_CORREGIDO_Y_SIN_USO
    assert "<> 'No se usa'" in LOGS_CON_TIPO_CORREGIDO
    assert "No se usa" not in LOGS_CON_TIPO_CORREGIDO_Y_SIN_USO
    router = open(os.path.join(os.path.dirname(__file__), "..", "routers", "asistencia.py"), encoding="utf-8").read()
    assert "FROM {LOGS_CON_TIPO_CORREGIDO_Y_SIN_USO}" in router          # la ventana las muestra
    assert "La regla de este día no permite dejar una marca sin usar." in router
    assert "Una marca manual no se marca como «No se usa»" in router
    js = open(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "js", "marcaciones_manuales.js"), encoding="utf-8").read()
    assert "mm-seg-nsu" in js and "opciones.includes('NO_SE_USA')" in js


def test_el_ciclo_no_se_elige_por_la_vuelta_de_colacion():
    """Opción cada día: si el día empieza con una SALIDA (falta la llegada), la ENTRADA siguiente es la vuelta de colación y
    no sirve para elegir el ciclo; se elige por la última SALIDA (S · E · S que calza con la mañana, no con la tarde)."""
    from backend.services.quantum_matrix_engine import QuantumShiftWeekMatcher
    ciclos = {1: {0: {"hora_entrada": "23:00", "hora_salida": "07:00", "cruza_medianoche": 1, "es_libre": 0}},
              2: {0: {"hora_entrada": "07:00", "hora_salida": "15:00", "es_libre": 0}},
              3: {0: {"hora_entrada": "15:00", "hora_salida": "23:00", "es_libre": 0}}}
    marca = lambda i, h, t: {"id": i, "fecha_hora": f"2026-10-12 {h}", "tipo": t}
    elegir = lambda logs: QuantumShiftWeekMatcher.resolve_winner_week(
        empleado_id=1, fecha_str="2026-10-12", dt=datetime(2026, 10, 12), dia_semana=0, logs=logs, turnos_dict=ciclos,
        total_sems=3, rotacion_dinamica=True)
    assert elegir([marca(1, "12:47:02", "Salida"), marca(2, "13:17:08", "Entrada"), marca(3, "16:35:42", "Salida")]) == 2
    # Con la llegada marcada, manda la llegada como siempre
    assert elegir([marca(1, "14:58:00", "Entrada"), marca(2, "19:30:00", "Salida"), marca(3, "20:00:00", "Entrada"),
                   marca(4, "23:02:00", "Salida")]) == 3
    assert elegir([marca(1, "06:58:00", "Entrada"), marca(2, "15:01:00", "Salida")]) == 2


def test_jornada_abierta_se_mide_con_la_salida_de_la_madrugada_siguiente():
    """Si el día queda abierto (la última marca es una ENTRADA), cada ciclo que cruza la medianoche también se mide con la
    primera SALIDA de la madrugada siguiente que viene antes de la siguiente ENTRADA: quien llegó antes a cubrir parte de la
    tarde y salió al terminar la noche queda en la noche, no en la tarde con la SALIDA sin usar."""
    from backend.services.quantum_matrix_engine import QuantumShiftWeekMatcher
    dia = {1: {0: {"hora_entrada": "23:00", "hora_salida": "07:00", "es_libre": 0}},
           2: {0: {"hora_entrada": "07:00", "hora_salida": "15:00", "es_libre": 0}},
           3: {0: {"hora_entrada": "15:00", "hora_salida": "23:00", "es_libre": 0}}}
    m = lambda i, fh, t: {"id": i, "fecha_hora": fh, "tipo": t}
    elegir = lambda logs: QuantumShiftWeekMatcher.resolve_winner_week(
        empleado_id=1, fecha_str="2026-06-22", dt=datetime(2026, 6, 22), dia_semana=0, logs=logs, turnos_dict=dia,
        total_sems=3, rotacion_dinamica=False)
    assert elegir([m(1, "2026-06-22 18:37:00", "Entrada"), m(2, "2026-06-23 07:05:00", "Salida")]) == 1
    # Si la madrugada siguiente empieza con una ENTRADA, esa SALIDA posterior es de otra jornada: no cuenta
    assert elegir([m(1, "2026-06-22 18:37:00", "Entrada"), m(2, "2026-06-23 06:50:00", "Entrada"),
                   m(3, "2026-06-23 15:05:00", "Salida")]) == 3
    # Un día que cierra con su SALIDA el mismo día sigue como siempre
    assert elegir([m(1, "2026-06-22 14:58:00", "Entrada"), m(2, "2026-06-22 23:03:00", "Salida")]) == 3


def test_una_salida_inicial_sola_no_abre_un_mas_dos():
    """Una SALIDA que es la primera marca del día (sin ENTRADA antes) no cerró ninguna jornada: el hueco desde ella no abre
    una jornada adicional (+2). Un hueco desde una SALIDA que sí cerró una jornada lo sigue abriendo."""
    from backend.services.quantum_matrix_engine import MultiBlockTensorSolver as M
    m = lambda i, h, t: {"id": i, "fecha_hora": f"2026-08-10 {h}", "tipo": t}
    r = M.segment_blocks([m(1, "07:10:13", "Salida"), m(2, "12:57:46", "Entrada"), m(3, "13:30:06", "Entrada"),
                          m(4, "16:30:58", "Salida")], gap_emergencia_horas=4.0)
    assert not r["bloques_extras"] and [l["id"] for l in r["bloque_principal"]] == [1, 2, 3, 4]
    r = M.segment_blocks([m(1, "06:00:00", "Entrada"), m(2, "10:00:00", "Salida"), m(3, "15:00:00", "Entrada"),
                          m(4, "19:00:00", "Salida")], gap_emergencia_horas=4.0)
    assert len(r["bloques_extras"]) == 1
