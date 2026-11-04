# -*- coding: utf-8 -*-
"""Al arrancar solo se completan los días sin resultado o por definir (orden del dueño, 04-11-2026).

Desde el 30-09-2026 el arranque recalculaba con force todos los días del período abierto con las reglas del momento: cada
subida reescribía días ya revisados y decididos (Logística Tradicional reabierta el 02-11 para decidir un cuadre: el 19-10
de una persona pasó de salida adelantada a «en revisión» y la política del cuadre le rechazó 8 horas extra aprobadas)."""
import asyncio
import os
from datetime import datetime, timedelta

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.core import events  # noqa: E402
from backend.services import asistencia_service as svc_mod  # noqa: E402
from backend.services.calendario_service import CalendarioService  # noqa: E402


class _Repo:
    def __init__(self):
        self.db = object()
        self.guardados = []

    async def batch_upsert_asistencia(self, filas):
        self.guardados.extend((f['empleado_id'], f['fecha']) for f in filas)


def test_procesar_dia_omite_a_quien_ya_tiene_el_dia_y_dice_cuantos_calculo(monkeypatch):
    repo = _Repo()
    servicio = svc_mod.AsistenciaService(repo)
    procesados, cuadre = [], []

    async def contexto(fecha, area=None, empleado_ids=None):
        return {'empleados': {1: {'area': 'LOGISTICA TRADICIONAL'}, 2: {'area': 'LOGISTICA TRADICIONAL'}, 3: {'area': 'PRODUCCION'}},
                'closed_dates': {1: set(), 2: set(), 3: set()}, 'jornadas_especiales': {}}

    async def procesar(emp_id, fecha, save=False, bulk_ctx=None, force=False):
        procesados.append(emp_id)
        return {'empleado_id': emp_id, 'fecha': fecha, 'minutos_extra_bruto': 0}

    async def feriados(self, anio):
        return []

    async def reaplicar(ids, fecha):
        cuadre.extend(ids)

    async def sin_he(*a, **k):
        return None

    monkeypatch.setattr(servicio, 'get_bulk_context', contexto)
    monkeypatch.setattr(servicio, 'procesar_empleado_dia', procesar)
    monkeypatch.setattr(servicio, '_reaplicar_politicas_cuadre', reaplicar)
    monkeypatch.setattr(servicio.he_repo, 'delete_by_empleado_fecha', sin_he)
    monkeypatch.setattr(CalendarioService, 'get_feriados', feriados)

    n = asyncio.run(servicio.procesar_dia('2026-10-19', omitir_ids={1, 3}))
    assert n == 1
    assert procesados == [2]                      # solo quien no tenía el día calculado
    assert repo.guardados == [(2, '2026-10-19')]  # ni se escribe a los demás
    assert cuadre == [2]                          # ni se les vuelve a repartir la política del cuadre


def test_el_arranque_pasa_a_quien_ya_tiene_el_dia_calculado_y_no_usa_force(monkeypatch):
    hoy = datetime.now().date()
    consultas, llamadas = [], []

    class _Db:
        async def fetch_one(self, sql, params=None):
            if 'dia_cierre_rrhh' in sql:
                return {'valor': '25'}
            if 'periodos_rrhh' in sql:
                return {'fecha_fin': (hoy - timedelta(days=3)).strftime('%Y-%m-%d')}
            return None

        async def fetch_all(self, sql, params=None):
            consultas.append((sql, params))
            return [{'empleado_id': 7}, {'empleado_id': 9}]   # ya tienen el día con su resultado

    class _Servicio:
        def __init__(self, repo):
            pass

        async def procesar_dia(self, fecha, force=False, omitir_ids=None, **k):
            llamadas.append((fecha, force, set(omitir_ids or ())))
            return 1

    monkeypatch.setattr(events, 'db', _Db())
    monkeypatch.setattr(svc_mod, 'AsistenciaService', _Servicio)
    asyncio.run(events._recalcular_periodo_activo())

    dias = [(hoy - timedelta(days=d)).strftime('%Y-%m-%d') for d in (2, 1, 0)]
    assert [f for f, _, _ in llamadas] == dias               # solo el período abierto, día por día
    assert all(force is False for _, force, _ in llamadas)   # sin force: respeta lo validado a mano
    assert all(omitir == {7, 9} for _, _, omitir in llamadas)
    for sql, params in consultas:                             # «ya calculado» = cualquier estado que no esté por definir
        assert params[1:] == events.ESTADOS_POR_DEFINIR
        assert 'NOT IN' in sql
