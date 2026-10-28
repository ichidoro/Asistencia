# -*- coding: utf-8 -*-
"""Dashboard, pestaña «Indicadores» (estructura B «lo que empeoró primero», elegida por el dueño el 27-10-2026).

Cada indicador del tramo se compara con el promedio simple de los tramos anteriores y se ordena desde el que
más empeoró; las áreas que lo explican salen de los mismos datos. Estas pruebas cuidan esas reglas.
"""
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services.dashboard_indicadores import (  # noqa: E402
    INDICADORES, calcular, comparar, donde, gravedad,
)

RAIZ = Path(__file__).resolve().parents[2]
_IND = {i["id"]: i for i in INDICADORES}


def _sumas(**kw):
    base = {c: 0.0 for c in ("programados", "asistidos", "con_atraso", "minutos_atraso", "faltas", "justificados",
                             "licencias", "horas_programadas", "minutos_deuda", "minutos_he", "minutos_je", "marcas",
                             "manuales", "dotacion", "bajas", "ingresos")}
    base.update(kw)
    return base


def test_calculo_de_cada_indicador():
    v = calcular(_sumas(programados=100, asistidos=95, con_atraso=19, minutos_atraso=380, faltas=5, justificados=10,
                        horas_programadas=800, minutos_deuda=600, minutos_he=1200, minutos_je=480, marcas=400,
                        manuales=8, dotacion=50, bajas=2))
    assert round(v["puntualidad"], 1) == 80.0          # 1 − 19/95
    assert round(v["ausentismo"], 1) == round(15 / 110 * 100, 1)  # (5 sin entrada + 10 justificados) / 110
    assert v["faltas"] == 5
    assert v["minutos_atraso"] == 20.0
    assert v["sobretiempo"] == 2.5                     # 20 h / 800 h
    assert v["horas_extra"] == 20.0 and v["jornadas_especiales"] == 8.0 and v["deuda"] == 10.0
    assert v["marcas_manuales"] == 2.0 and v["rotacion"] == 4.0


def test_sin_datos_no_inventa_valores():
    v = calcular(_sumas())
    assert v["puntualidad"] is None and v["ausentismo"] is None and v["minutos_atraso"] is None
    assert v["sobretiempo"] is None and v["marcas_manuales"] is None and v["rotacion"] is None
    # Si trabajaron y nadie llegó tarde, los minutos por atraso son 0 (no «sin dato»)
    assert calcular(_sumas(programados=10, asistidos=10))["minutos_atraso"] == 0.0


def test_comparar_con_el_promedio_de_los_tramos_anteriores():
    # Caso real (octubre 2026): faltas 9 contra 3, 4, 3, 1, 3 → promedio 2,8, empeoró
    c = comparar(9, [3, 4, 3, 1, 3], "bajo")
    assert round(c["promedio"], 1) == 2.8 and c["estado"] == "empeoro"
    # Puntualidad: más es mejor
    assert comparar(66.3, [66.3, 69.6, 64.1, 63.7, 62.2], "alto")["estado"] == "mejoro"
    # Los tramos sin dato no cuentan en el promedio; sin tramos anteriores no hay comparación
    assert comparar(5, [None, 4], "bajo")["promedio"] == 4
    assert comparar(5, [], "bajo")["estado"] == "sin_comparacion"
    assert comparar(None, [1, 2], "bajo")["estado"] == "sin_comparacion"
    # Igual cuando no cambia a un decimal
    assert comparar(2.04, [2.0], "bajo")["estado"] == "igual"


def test_lo_que_mas_empeoro_va_primero():
    a = {"estado": "empeoro", "valor": 686.9, "promedio": 51.1, "cambio": 1244.0}
    b = {"estado": "empeoro", "valor": 9, "promedio": 2.8, "cambio": 221.0}
    c = {"estado": "empeoro", "valor": 7.0, "promedio": 0.0, "cambio": None}
    assert gravedad(c) > gravedad(a) > gravedad(b)


def test_donde_en_una_tasa_son_las_areas_que_empeoraron():
    por_area = {"PRODUCCION": {"valor": 7.2, "promedio": 2.3}, "LOGISTICA": {"valor": 7.0, "promedio": 0.0},
                "MANTENCION": {"valor": 0.8, "promedio": 2.2}, "SEGURIDAD": {"valor": None, "promedio": 1.4}}
    d = donde(_IND["ausentismo"], "empeoro", por_area)
    assert [x["area"] for x in d] == ["LOGISTICA", "PRODUCCION"]
    # Si el indicador mejoró, solo se nombra el área que fue en contra
    d = donde(_IND["puntualidad"], "mejoro", {"PRODUCCION": {"valor": 64.3, "promedio": 67.1},
                                               "MANTENCION": {"valor": 54.6, "promedio": 25.7}})
    assert [x["area"] for x in d] == ["PRODUCCION"]


def test_donde_en_un_total_son_las_areas_que_mas_suman():
    por_area = {"PRODUCCION": {"valor": 570.1, "promedio": None}, "LOGISTICA TRADICIONAL": {"valor": 102.9, "promedio": None},
                "MANTENCION": {"valor": 13.9, "promedio": None}, "SEGURIDAD": {"valor": 0, "promedio": None}}
    d = donde(_IND["jornadas_especiales"], "empeoro", por_area)
    assert [x["area"] for x in d] == ["PRODUCCION", "LOGISTICA TRADICIONAL"]


def test_la_pantalla_tiene_las_dos_pestanas_y_usa_la_lectura_nueva():
    app = (RAIZ / "dashboard_build/src/DashboardApp.jsx").read_text(encoding="utf-8")
    assert "Lo que falta hacer" in app and "Indicadores" in app
    assert "/dashboard/indicadores/" in app and "/dashboard/pendientes/" in app
    api = (RAIZ / "backend/routers/dashboard_api.py").read_text(encoding="utf-8")
    assert '@router.get("/indicadores/")' in api and '@router.get("/pendientes/")' in api
    ind = (RAIZ / "backend/services/dashboard_indicadores.py").read_text(encoding="utf-8")
    assert "from backend.services.dashboard_pendientes import" in ind, "los indicadores dejaron de usar las mismas definiciones"
