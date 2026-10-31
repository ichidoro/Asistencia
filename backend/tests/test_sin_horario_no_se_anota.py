# -*- coding: utf-8 -*-
"""Una persona sin ningún horario asignado y sin marcas ese día no queda con feriado, día libre ni inasistencia.

31-10-2026: al guardar el contrato de una persona recién creada (ingresa el 02-11) se recalculó «hoy» antes de que tuviera
horario y quedó con un FERIADO del 31-10. Una fila escrita a mano o con justificación se respeta."""
import asyncio
import os

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import asistencia_service as svc_mod  # noqa: E402


class _SiguioDeLargo(Exception):
    pass


class _Ctx(dict):
    """Contexto del lote que avisa si el motor pasó a buscar el horario del día (es decir, no se detuvo antes)."""

    def __getitem__(self, llave):
        if llave == 'asignaciones':
            raise _SiguioDeLargo()
        return super().__getitem__(llave)


class _Repo:
    def __init__(self, fila=None):
        self.db = object()
        self.fila = fila
        self.borradas = []

    async def get_asistencia(self, empleado_id, fecha):
        return self.fila

    async def delete_asistencia(self, empleado_id, fecha):
        self.borradas.append((empleado_id, fecha))


def _ctx(marcas=(), asistencia_hoy=None):
    return _Ctx({
        'closed_dates': {7: set()},
        'empleados': {7: {'activo': 1, 'fecha_ingreso': '2026-11-02', 'fecha_salida': '2026-11-30'}},
        'periodos_empleo': {7: []},
        'first_assignments': {},
        'logs': {7: list(marcas)},
        'asistencias_hoy': {7: asistencia_hoy} if asistencia_hoy else {},
        'feriados': {'2026-10-31': 'Día Nacional de las Iglesias Evangélicas y Protestantes'},
        'justificaciones': {},
    })


def _servicio(repo, monkeypatch):
    servicio = svc_mod.AsistenciaService(repo)
    he_borradas = []

    async def borrar_he(empleado_id, fecha):
        he_borradas.append((empleado_id, fecha))

    monkeypatch.setattr(servicio.he_repo, 'delete_by_empleado_fecha', borrar_he)
    return servicio, he_borradas


def test_sin_horario_ni_marcas_el_feriado_no_se_anota(monkeypatch):
    servicio, _ = _servicio(_Repo(), monkeypatch)
    res = asyncio.run(servicio.procesar_empleado_dia(7, '2026-10-31', save=False, bulk_ctx=_ctx()))
    assert res is None  # el lote borra la fila que hubiera y no escribe ninguna


def test_al_guardar_de_a_uno_se_borra_el_feriado_que_habia(monkeypatch):
    repo = _Repo(fila={'empleado_id': 7, 'fecha': '2026-10-31', 'estado': 'FERIADO', 'origen': 'FERIADO'})
    servicio, he_borradas = _servicio(repo, monkeypatch)
    res = asyncio.run(servicio.procesar_empleado_dia(7, '2026-10-31', save=True, bulk_ctx=_ctx(asistencia_hoy=repo.fila)))
    assert res is None
    assert repo.borradas == [(7, '2026-10-31')]
    assert he_borradas == [(7, '2026-10-31')]


def test_con_marcas_el_dia_se_calcula_como_siempre(monkeypatch):
    servicio, _ = _servicio(_Repo(), monkeypatch)
    marca = {'id': 1, 'fecha_hora': '2026-10-31 08:00:00'}
    try:
        asyncio.run(servicio.procesar_empleado_dia(7, '2026-10-31', save=False, bulk_ctx=_ctx(marcas=[marca])))
        siguio = False
    except _SiguioDeLargo:
        siguio = True
    assert siguio


def test_una_fila_escrita_a_mano_o_justificada_se_respeta(monkeypatch):
    for fila in ({'origen': 'MANUAL'}, {'origen': 'MOTOR', 'justificacion_id': 12}):
        repo = _Repo(fila=fila)
        servicio, _ = _servicio(repo, monkeypatch)
        try:
            asyncio.run(servicio.procesar_empleado_dia(7, '2026-10-31', save=True, bulk_ctx=_ctx(asistencia_hoy=fila)))
            siguio = False
        except _SiguioDeLargo:
            siguio = True
        assert siguio
        assert repo.borradas == []
