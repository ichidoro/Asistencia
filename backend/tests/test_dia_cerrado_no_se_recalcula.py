# -*- coding: utf-8 -*-
"""Un día cerrado (cierre del área) nunca se vuelve a calcular ni a escribir, tampoco con force.

27-10-2026: el recálculo del arranque (procesar_dia con force) cambió el 19-10 de una persona de un área ya cerrada por su
jefatura y la política del cuadre volvió a repartir sus horas extra (8 aprobadas pasaron a rechazadas)."""
import asyncio
import os

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import asistencia_service as svc_mod  # noqa: E402
from backend.services.calendario_service import CalendarioService  # noqa: E402


class _Repo:
    def __init__(self):
        self.db = object()
        self.guardados = []

    async def batch_upsert_asistencia(self, filas):
        self.guardados.extend((f['empleado_id'], f['fecha']) for f in filas)


def test_procesar_dia_con_force_deja_fuera_los_dias_cerrados(monkeypatch):
    repo = _Repo()
    servicio = svc_mod.AsistenciaService(repo)
    procesados, cuadre = [], []

    async def contexto(fecha, area=None, empleado_ids=None):
        return {'empleados': {1: {'area': 'LOGISTICA TRADICIONAL'}, 2: {'area': 'MANTENCION'}},
                'closed_dates': {1: {fecha}, 2: set()}, 'jornadas_especiales': {}}

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

    asyncio.run(servicio.procesar_dia('2026-10-19', force=True))
    assert procesados == [2]                      # la persona del área cerrada no se calcula
    assert repo.guardados == [(2, '2026-10-19')]  # ni se escribe
    assert cuadre == [2]                          # ni se vuelve a repartir su política del cuadre
