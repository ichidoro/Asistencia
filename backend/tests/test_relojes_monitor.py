# -*- coding: utf-8 -*-
"""Estado de los relojes de marcación bajo «Servidor en línea» (31-10-2026).

Se lee de EasyTime en cada ciclo del cron; si EasyTime no responde se conserva lo último leído y la pantalla lo muestra
como «sin dato», nunca como conectado."""
import asyncio
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import relojes_monitor as mon  # noqa: E402

AHORA = datetime(2026, 10, 31, 9, 0, 0)
LEIDOS = [{"alias": "AGUACOL", "estado": 1, "ultima_actividad": "2026-10-31 08:53:10"},
          {"alias": "AGUACOL 2", "estado": 3, "ultima_actividad": "2026-10-31 08:51:00"}]


def _preparar(monkeypatch, guardado):
    caja = {"valor": dict(guardado)}

    async def cargar():
        return dict(caja["valor"])

    async def guardar(estado):
        caja["valor"] = dict(estado)

    monkeypatch.setattr(mon, "_cargar", cargar)
    monkeypatch.setattr(mon, "_guardar", guardar)
    monkeypatch.setattr(mon, "_ahora", lambda: AHORA)
    monkeypatch.setattr(mon.settings, "EASYTIME_URL", "https://easytime.prueba")
    monkeypatch.setattr(mon.settings, "EASYTIME_PASSWORD", "x")
    return caja


def test_cada_reloj_sale_con_el_grupo_de_su_codigo_de_easytime(monkeypatch):
    _preparar(monkeypatch, {"ok": True, "ultimo_ok": "2026-10-31 08:55:00",
                            "relojes": LEIDOS + [{"alias": "BODEGA", "estado": 0, "ultima_actividad": None},
                                                 {"alias": "RARO", "estado": 9, "ultima_actividad": None}]})
    r = asyncio.run(mon.estado_para_pantalla())
    assert r["vigente"] is True
    assert [(x["alias"], x["grupo"], x["texto"]) for x in r["relojes"]] == [
        ("AGUACOL", "conectado", "En línea"), ("AGUACOL 2", "sin_conexion", "Desconectado"),
        ("BODEGA", "aviso", "No autorizado"), ("RARO", "sin_dato", "Estado 9")]


def test_si_easytime_no_responde_se_conserva_lo_leido_y_queda_sin_dato(monkeypatch):
    caja = _preparar(monkeypatch, {"ok": True, "ultimo_ok": "2026-10-31 08:55:00", "relojes": LEIDOS})

    class _Falla:
        def __init__(self, *a):
            pass

        async def fetch_terminales(self):
            raise RuntimeError("EasyTime: login rechazado")

    import backend.scraper.easytime_scraper as et
    monkeypatch.setattr(et, "EasyTimeClient", _Falla)
    asyncio.run(mon.actualizar())
    assert caja["valor"]["relojes"] == LEIDOS          # lo último leído no se pierde
    assert caja["valor"]["ok"] is False
    assert caja["valor"]["ultimo_ok"] == "2026-10-31 08:55:00"
    r = asyncio.run(mon.estado_para_pantalla())
    assert r["vigente"] is False
    assert {x["grupo"] for x in r["relojes"]} == {"sin_dato"}


def test_una_lectura_buena_reemplaza_lo_guardado(monkeypatch):
    caja = _preparar(monkeypatch, {})

    class _Bien:
        def __init__(self, *a):
            pass

        async def fetch_terminales(self):
            return LEIDOS

    import backend.scraper.easytime_scraper as et
    monkeypatch.setattr(et, "EasyTimeClient", _Bien)
    asyncio.run(mon.actualizar())
    assert caja["valor"]["ok"] is True and caja["valor"]["relojes"] == LEIDOS
    assert caja["valor"]["ultimo_ok"] == "2026-10-31 09:00:00"


def test_lo_guardado_hace_mas_de_tres_ciclos_ya_no_se_muestra_como_vigente(monkeypatch):
    _preparar(monkeypatch, {"ok": True, "ultimo_ok": "2026-10-31 08:40:00", "relojes": LEIDOS})
    r = asyncio.run(mon.estado_para_pantalla())
    assert r["vigente"] is False
    assert {x["grupo"] for x in r["relojes"]} == {"sin_dato"}


def test_sin_consulta_previa_no_se_muestra_nada(monkeypatch):
    _preparar(monkeypatch, {})
    assert asyncio.run(mon.estado_para_pantalla()) is None
