# -*- coding: utf-8 -*-
"""Recalcular días de una persona (validar, rechazar o revertir una jornada, marcas manuales, justificaciones,
compensar una inasistencia) vuelve a repartir al instante su política del cuadre, una vez por tramo y nunca en
días cerrados.

27-10-2026: a las 20:28 se validaron como horas extra los +2 de Badilla (10-10, 257 min) y González (24-10, 375 min);
el cuadre recién se repartió de nuevo con el arranque de las 22:14 y en ese rato las horas extra del tramo quedaron
aprobadas dos veces."""
import asyncio
import inspect
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import asistencia_service as svc_mod  # noqa: E402
from backend.services.cuadre_service import CuadreService, asignar_minutos  # noqa: E402


def test_los_dias_cerrados_no_entran_al_reparto():
    dias = svc_mod.fechas_abiertas(datetime(2026, 10, 24), datetime(2026, 10, 27), {'2026-10-25'})
    assert dias == ['2026-10-24', '2026-10-26', '2026-10-27']


class _RepoCuadre:
    def __init__(self, politicas):
        self.politicas = politicas
        self.consultas = []

    async def politicas_en_rango(self, empleado_id, desde, hasta):
        self.consultas.append((empleado_id, desde, hasta))
        return [p for p in self.politicas if p['empleado_id'] == empleado_id and p['fecha_inicio'] <= hasta and p['fecha_fin'] >= desde]


def _cuadre(politicas):
    servicio = type('S', (), {'repository': type('R', (), {'db': object()})()})()
    cs = CuadreService(servicio)
    cs.repo = _RepoCuadre(politicas)
    return cs


def test_se_reparte_una_sola_vez_por_tramo():
    cs = _cuadre([{'empleado_id': 38, 'fecha_inicio': '2026-09-26', 'fecha_fin': '2026-10-25'}])
    llamadas = []

    async def reaplicar_para(ids, fecha):
        llamadas.append((tuple(ids), fecha))
        return 1

    cs.reaplicar_para = reaplicar_para
    n = asyncio.run(cs.reaplicar_en_fechas(38, ['2026-10-26', '2026-10-24', '2026-10-25', '2026-10-24']))
    assert n == 1
    assert llamadas == [((38,), '2026-10-24')]        # el tramo de octubre, una vez; noviembre no tiene política
    assert cs.repo.consultas == [(38, '2026-10-24', '2026-10-26')]


def test_sin_politica_no_se_reparte_nada():
    cs = _cuadre([])
    llamadas = []

    async def reaplicar_para(ids, fecha):
        llamadas.append(fecha)
        return 1

    cs.reaplicar_para = reaplicar_para
    assert asyncio.run(cs.reaplicar_en_fechas(36, ['2026-10-10'])) == 0
    assert asyncio.run(cs.reaplicar_en_fechas(36, [])) == 0
    assert llamadas == []


def test_el_recalculo_de_una_persona_reparte_el_cuadre_despues_de_guardar():
    fuente = inspect.getsource(svc_mod.AsistenciaService.reprocesar_periodo_empleado)
    guardar = fuente.index('BATCH FINAL')
    reparto = fuente.index('_reaplicar_cuadre_en_fechas(')
    recoleccion = fuente.index('if collect_only:\n            # ── Modo recolección')
    assert recoleccion < guardar < reparto            # en modo recolección no se reparte: lo hace quien guarda
    assert 'fechas_abiertas(start, end, fechas_cerradas)' in fuente[reparto:reparto + 120]


def test_validar_una_jornada_pasa_por_el_recalculo_de_la_persona():
    fuente = inspect.getsource(svc_mod.AsistenciaService._recalcular_tras_decision_humana)
    assert 'reprocesar_periodo_empleado' in fuente


def test_gonzalez_con_cero_y_un_mas_dos_validado_como_horas_extra():
    """Con «llevar a cero», el +2 validado a mano cuenta primero: cubre la deuda y lo que sobra se paga igual;
    las horas extra calculadas del tramo pasan a no pagadas (números reales de González, tramo de octubre)."""
    filas = [{'fecha': '2026-10-02', 'minutos_bruto': 40.0, 'minutos_autorizados': 40.0, 'estado': 'APROBADO', 'excepcion': 0},
             {'fecha': '2026-10-13', 'minutos_bruto': 76.35, 'minutos_autorizados': 76.35, 'estado': 'APROBADO', 'excepcion': 0}]
    reparto, resumen = asignar_minutos(filas, 159.56, 'CERO', None, 375.0)
    assert all(r['estado'] == 'RECHAZADO' and r['minutos_autorizados'] == 0.0 for r in reparto)
    assert resumen['cubierto'] == 159.56 and resumen['pendiente'] == 0
    assert round(resumen['a_pagar'], 2) == 215.44
