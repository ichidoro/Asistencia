# -*- coding: utf-8 -*-
"""Dashboard, pestaña «Indicadores»: «Ver detalle» y lenguaje neutro (pedido del dueño, 27-10-2026).

«Ver detalle» debe mostrar los registros que forman el número (quién, qué día, quién ingresó la marca), no la
grilla; y la pantalla no usa el concepto en negativo («empeoró»): dice «Para mejorar» y «En buen camino».
"""
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services.dashboard_detalle import _causa, _prog, agrupar  # noqa: E402
from backend.services.dashboard_indicadores import INDICADORES  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]


def _dia(**kw):
    base = {"empleado_id": 1, "persona": "PERSONA, UNO", "area": "PRODUCCION", "fecha": "2026-10-01", "estado": "OK",
            "libreta": 0, "justificado": 0, "horas_teoricas": 8.5, "entrada": 1}
    base.update(kw)
    return base


def test_agrupa_por_persona_ordena_y_conserva_cada_registro():
    filas = [_dia(empleado_id=1, persona="A", fecha="2026-10-02"), _dia(empleado_id=2, persona="B"),
             _dia(empleado_id=1, persona="A", fecha="2026-10-01")]
    out = agrupar(filas, lambda fs: {"n": len(fs)}, lambda f: {"fecha": f["fecha"]}, "n")
    assert [p["persona"] for p in out] == ["A", "B"]
    assert out[0]["valores"] == {"n": 2}
    assert [r["fecha"] for r in out[0]["registros"]] == ["2026-10-01", "2026-10-02"]  # en orden de fecha


def test_programado_igual_que_el_indicador():
    assert _prog(_dia())
    assert not _prog(_dia(libreta=1))
    assert not _prog(_dia(justificado=1))
    assert not _prog(_dia(horas_teoricas=0))
    assert not _prog(_dia(estado="LIBRE"))


def test_causa_legible_de_un_dia_sin_trabajar():
    assert _causa("INASISTENCIA") == "Falta sin aviso"
    assert _causa("PENDIENTE") == "Sin marca de entrada"
    assert _causa("LICENCIA COMUN") == "Licencia comun"
    assert _causa("VACACIONES") == "Vacaciones"


def test_hay_detalle_para_cada_indicador():
    src = (RAIZ / "backend/services/dashboard_detalle.py").read_text(encoding="utf-8")
    for i in INDICADORES:
        assert f'"{i["id"]}"' in src, f"el indicador {i['id']} no tiene detalle"


def test_ver_detalle_abre_el_panel_y_no_la_grilla():
    app = (RAIZ / "dashboard_build/src/DashboardApp.jsx").read_text(encoding="utf-8")
    assert "const verDetalle = (i) => setDetalleDe(i);" in app
    assert "/dashboard/indicadores/detalle/" in app and "<PanelDetalle" in app
    api = (RAIZ / "backend/routers/dashboard_api.py").read_text(encoding="utf-8")
    assert '@router.get("/indicadores/detalle/")' in api


def test_sin_concepto_en_negativo():
    ind = (RAIZ / "dashboard_build/src/Indicadores.jsx").read_text(encoding="utf-8")
    for palabra in ("Empeor", "empeoraron"):
        assert palabra not in ind, f"volvió el concepto en negativo: {palabra}"
    assert "Para mejorar" in ind and "En buen camino" in ind
