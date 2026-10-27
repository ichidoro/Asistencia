# -*- coding: utf-8 -*-
"""Recálculo del tramo abierto al guardar un turno o un ajuste (orden del dueño, 26-10-2026)."""
import asyncio
import os
from datetime import date

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import recalculo_service as rs  # noqa: E402


def test_el_rango_empieza_el_dia_siguiente_al_ultimo_cierre():
    assert rs.calcular_rango(date(2026, 10, 26), "2026-09-25", 25) == (date(2026, 9, 26), date(2026, 10, 26))


def test_sin_cierres_empieza_el_dia_siguiente_al_dia_de_cierre_del_mes_anterior():
    assert rs.calcular_rango(date(2026, 10, 26), None, 25) == (date(2026, 9, 26), date(2026, 10, 26))


def test_un_dia_de_cierre_que_el_mes_anterior_no_tiene_no_rompe():
    # Marzo 2027: febrero tiene 28 días; con cierre el 28, el inicio sería el 29 de febrero, que no existe
    inicio, fin = rs.calcular_rango(date(2027, 3, 10), None, 28)
    assert inicio == date(2027, 2, 28) and fin == date(2027, 3, 10)


def test_solo_los_ajustes_que_usa_el_motor_recalculan():
    assert "asistencia_minimo_horas_extra_minutos" in rs.CLAVES_AJUSTE_QUE_RECALCULAN
    assert "asistencia_max_extras_ordinarias_dia_habil" in rs.CLAVES_AJUSTE_QUE_RECALCULAN
    assert "dia_cierre_rrhh" not in rs.CLAVES_AJUSTE_QUE_RECALCULAN
    assert asyncio.run(rs.recalcular_por_ajuste(None, "vencimiento_dias_alerta")) is None


def test_un_turno_sin_personas_no_lanza_nada(monkeypatch):
    lanzados = []
    monkeypatch.setattr(rs.asyncio, "create_task", lambda c: lanzados.append(c))
    rs.lanzar([], "prueba")
    assert lanzados == []


def test_el_arranque_no_vuelve_a_calcular_el_ultimo_dia_cerrado():
    # Orden del dueño (27-10-2026): un día cerrado nunca se recalcula; antes el arranque guardaba de nuevo el último día
    # cerrado (25-09) en cada despliegue y cambiaba días ya pagados.
    from pathlib import Path
    eventos = (Path(__file__).resolve().parents[1] / "core" / "events.py").read_text(encoding="utf-8")
    assert 'dias_a_recalc.append(ultimo_cierre["fecha_fin"])' not in eventos
