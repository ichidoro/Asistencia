# -*- coding: utf-8 -*-
"""Registrar un contrato anterior ya terminado (dueño, 10-11-2026): solo agrega ese período cerrado."""
import asyncio
import os

import pytest

from backend.services.empleado_service import EmpleadoService


class _Db:
    def __init__(self, periodos):
        self.periodos = periodos
        self.sql = []

    async def fetch_all(self, q, p=()):
        return [dict(x) for x in self.periodos]

    async def execute(self, q, p=()):
        self.sql.append((q, p))


class _Repo:
    def __init__(self, db):
        self.db = db

    async def get_by_id(self, _):
        return object()


def _servicio(periodos):
    s = EmpleadoService.__new__(EmpleadoService)
    s.repository = _Repo(_Db(periodos))
    return s


def _correr(s, ini, fin, tipo='Temporal'):
    return asyncio.run(s.registrar_periodo_anterior(1, ini, fin, tipo, 'prueba', None, 'prueba'))


VIGENTE = [{'id': 1, 'fecha_inicio': '2026-08-03', 'fecha_fin': '2027-03-19'}]


def test_agrega_solo_el_periodo_cerrado():
    s = _servicio(VIGENTE)
    d = _correr(s, '2026-04-27', '2026-06-15')
    inserts = [x for x in s.repository.db.sql if x[0].startswith('INSERT INTO periodos_empleo')]
    assert len(inserts) == 1 and inserts[0][1] == (1, '2026-04-27', '2026-06-15', 'Temporal')
    assert 'es_activo) VALUES (?, ?, ?, ?, 0)' in inserts[0][0]
    assert not any('UPDATE' in q or 'empleados' in q.split('INTO')[-1].split('(')[0] for q, _ in s.repository.db.sql)
    assert d['baja'] == '2026-06-15'


@pytest.mark.parametrize('ini,fin', [('2026-07-01', '2026-08-10'), ('2026-08-03', '2026-08-20'), ('2026-09-01', '2026-09-30')])
def test_no_se_cruza_con_otro_contrato(ini, fin):
    with pytest.raises(ValueError, match='Se cruza'):
        _correr(_servicio(VIGENTE), ini, fin)


def test_fechas_y_tipo_validos():
    with pytest.raises(ValueError):
        _correr(_servicio([]), '2026-06-15', '2026-04-27')
    with pytest.raises(ValueError):
        _correr(_servicio([]), '2026-04-27', '2099-01-01')
    with pytest.raises(ValueError):
        _correr(_servicio([]), '2026-04-27', '2026-06-15', 'Otro')


def test_endpoint_existe():
    src = open(os.path.join(os.path.dirname(__file__), '..', 'routers', 'empleados.py'), encoding='utf-8').read()
    assert '"/{empleado_id}/periodo-anterior/"' in src and 'RequirePermission("empleados.editar")' in src
