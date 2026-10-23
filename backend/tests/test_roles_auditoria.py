# -*- coding: utf-8 -*-
"""Blindaje del alcance de los roles (sin base de datos).

El 13-10-2026 un guardado desde Seguridad → Roles dejó al rol «Jefe de Area»
con alcance global sin que nadie lo notara: la auditoría solo decía «Rol
modificado» y hubo que fechar el cambio comparando respaldos. Estas pruebas
cuidan las dos defensas que se agregaron: la auditoría con el detalle de qué
cambió y la confirmación en pantalla antes de dejar un rol global.
"""
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.repositories.seguridad import detalle_cambio_rol  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]


def test_el_caso_del_13_de_octubre_quedaria_retratado():
    d = detalle_cambio_rol(
        "Jefe de Area", 2, antes_global=False, despues_global=True,
        permisos_antes=["marcaciones.ver", "empleados.ver"],
        permisos_despues=["marcaciones.ver", "empleados.ver", "empleados.eliminar", "empleados.reincorporar"],
    )
    assert "Jefe de Area (2)" in d
    assert "por áreas → GLOBAL" in d
    assert "+empleados.eliminar" in d and "+empleados.reincorporar" in d


def test_sin_cambios_y_vuelta_a_por_areas():
    d = detalle_cambio_rol("Jefe de Area", 2, True, False, ["a.b"], ["a.b"])
    assert "global → por áreas" in d and "sin cambios (1)" in d
    d2 = detalle_cambio_rol("Guardia", 3, False, False, ["a.b"], ["a.b", "c.d"])
    assert "por áreas (sin cambio)" in d2 and "+c.d" in d2


def test_muchos_cambios_se_resumen_en_conteos():
    antes = [f"p.{i}" for i in range(12)]
    d = detalle_cambio_rol("X", 5, False, False, antes, ["p.0"])
    assert "-11" in d and "(quedan 1)" in d
    # y quitar un permiso se escribe con su signo
    d2 = detalle_cambio_rol("X", 5, False, False, ["a.b", "c.d"], ["a.b"])
    assert "-c.d" in d2


def test_la_pantalla_pide_confirmacion_antes_de_dejar_un_rol_global():
    js = (RAIZ / "frontend/js/seguridad_ui.js").read_text(encoding="utf-8")
    assert "¿Dejar este rol con alcance global?" in js, \
        "la pantalla perdió la confirmación al pasar un rol a alcance global"
    assert "TODAS las áreas" in js
    assert "eraGlobal" in js and "conf.isConfirmed" in js
    # y el servidor escribe el detalle del cambio en la auditoría
    router = (RAIZ / "backend/routers/seguridad.py").read_text(encoding="utf-8")
    assert "detalle_cambio_rol" in router and "permisos_antes" in router
