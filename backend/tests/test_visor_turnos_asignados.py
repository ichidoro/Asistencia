# -*- coding: utf-8 -*-
"""Visor «Turnos asignados» (Personas): el horario de cada día.

31-10-2026: la hora del día quedaba dentro del «if es_libre», así que los días de trabajo salían «SIN DEF» y los libres
«??-??» para todos. En un turno con varias opciones por día (p. ej. Planta Mantención 2) la opción sale de las marcas:
un día ya calculado muestra el horario que eligió el cálculo y uno sin calcular dice «ROTATIVO», sin adivinar."""
import asyncio
import os

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services.turno_service import TurnoService  # noqa: E402

EMPLEADO = {'id': 7, 'nombre': 'MAURICIO', 'apellido_paterno': 'RIQUELME', 'apellido_materno': 'SOTO', 'rut': '1-9',
            'area': 'MANTENCION', 'cargo': 'TECNICO', 'fecha_salida': None}


class _Db:
    def __init__(self, turno_id, dias, asistencias):
        self.turno_id, self.dias, self.asistencias = turno_id, dias, asistencias

    async def fetch_all(self, sql, params=()):
        if 'FROM empleados' in sql:
            return [EMPLEADO]
        if 'FROM asignacion_turnos' in sql:
            return [{'empleado_id': 7, 'turno_id': self.turno_id, 'fecha_inicio': '2026-09-01', 'fecha_fin': None, 'turno_nombre': 'X'}]
        if 'FROM turno_dias' in sql:
            return self.dias
        if 'FROM asistencias' in sql:
            return self.asistencias
        return []


class _Repo:
    def __init__(self, db):
        self.db = db


def _dia(sem, dia_semana, libre=False, ent='07:00', sal='15:00'):
    return {'turno_id': 1, 'num_semana': sem, 'dia_semana': dia_semana, 'es_libre': 1 if libre else 0,
            'hora_entrada': None if libre else ent, 'hora_salida': None if libre else sal}


def _horarios(db):
    filas = asyncio.run(TurnoService(_Repo(db)).get_assignment_matrix(10, 2026))
    return {d['date']: (d['turno'] or {}).get('horario') for d in filas[0]['dias']}


def test_turno_de_una_opcion_muestra_su_hora_y_los_libres():
    dias = [_dia(1, ds) for ds in range(5)] + [_dia(1, 5, libre=True), _dia(1, 6, libre=True)]
    h = _horarios(_Db(1, dias, []))
    assert h['2026-10-05'] == '07:00-15:00'   # lunes
    assert h['2026-10-04'] == 'LIBRE'         # domingo


def test_turno_con_varias_opciones_usa_lo_calculado_y_no_adivina_lo_demas():
    dias = [_dia(1, ds) for ds in range(7)] + [_dia(2, ds, ent='15:00', sal='23:00') for ds in range(7)]
    asist = [{'empleado_id': 7, 'fecha': '2026-10-07', 'hora_entrada_teorica': '15:00:00', 'hora_salida_teorica': '23:00:00', 'estado': 'ATRASO'},
             {'empleado_id': 7, 'fecha': '2026-10-11', 'hora_entrada_teorica': None, 'hora_salida_teorica': None, 'estado': 'LIBRE'}]
    h = _horarios(_Db(1, dias, asist))
    assert h['2026-10-07'] == '15:00-23:00'   # lo que eligió el cálculo ese día
    assert h['2026-10-11'] == 'LIBRE'
    assert h['2026-10-29'] == 'ROTATIVO'      # sin calcular: no se inventa la opción
