# -*- coding: utf-8 -*-
"""El cierre y sus informes usan siempre las fechas del período configurado (dueño, 26-11-2026).

Un preinforme de diciembre salió «al 26-12» con el período configurado hasta el domingo 27-12: al Fill Rate le faltó la
quinta semana (21-12 al 27-12), que con el fin en domingo se paga completa en diciembre."""
import asyncio
import os

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.repositories.configuracion import ConfiguracionRepository  # noqa: E402
from backend.routers import cierre  # noqa: E402
from backend.services.bono_semanal import semanas_del_periodo, semana_siguiente  # noqa: E402

PERIODOS = [{"fecha_inicio": "2026-11-26", "fecha_fin": "2026-12-27"}]


def _periodos(monkeypatch, periodos):
    async def que_empieza(self, fecha_inicio):
        return next((p for p in periodos if p["fecha_inicio"] == fecha_inicio), None)
    monkeypatch.setattr(ConfiguracionRepository, "periodo_rrhh_que_empieza", que_empieza)


def test_el_fin_sale_del_periodo_configurado(monkeypatch):
    _periodos(monkeypatch, PERIODOS)
    assert asyncio.run(cierre.fechas_del_periodo(None, "2026-11-26", "2026-12-26")) == ("2026-11-26", "2026-12-27")


def test_sin_periodo_configurado_se_usan_las_fechas_recibidas(monkeypatch):
    _periodos(monkeypatch, PERIODOS)
    assert asyncio.run(cierre.fechas_del_periodo(None, "2026-12-01", "2026-12-15")) == ("2026-12-01", "2026-12-15")


def test_con_el_fin_en_domingo_la_ultima_semana_se_paga_completa_y_no_queda_cortada():
    sem = semanas_del_periodo("2026-11-26", "2026-12-27")
    assert [(a.isoformat(), b.isoformat()) for a, b in sem][-1] == ("2026-12-21", "2026-12-27")
    assert len(sem) == 5
    assert semana_siguiente("2026-11-26", "2026-12-27") is None


def test_una_semana_cortada_no_se_paga_en_el_periodo_donde_se_corta():
    # Noviembre cierra el miércoles 25: la semana del 23 al 29 no se paga en noviembre (se marca ahí y se paga en
    # diciembre, donde cae su domingo)
    sem = semanas_del_periodo("2026-10-26", "2026-11-25")
    assert all(b.isoformat() <= "2026-11-25" for _, b in sem)
    sig = semana_siguiente("2026-10-26", "2026-11-25")
    assert (sig[0].isoformat(), sig[1].isoformat()) == ("2026-11-23", "2026-11-29")
