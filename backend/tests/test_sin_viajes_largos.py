# -*- coding: utf-8 -*-
"""Los viajes largos se quitaron (orden del dueño, 07-11-2026): la libreta Art. 25 bis registra cada día la conducción,
la espera y el descanso, y ya no quedaban horarios ni registros con viajes largos.

Esta prueba evita que vuelvan a aparecer por error. El código nunca creaba la tabla `viajes_largos`, así que en una
base nueva (servidor nuevo o prueba de restauración) la tabla de Marcaciones fallaba con «Error cargando datos».
La columna `turnos.permite_viajes_largos` y la tabla quedan en la base de producción, sin uso."""
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

RAIZ = Path(__file__).resolve().parents[2]
# Únicos lugares que pueden nombrarlos:
# - turno.py conserva la migración de la columna, para no tocar la base;
# - seguridad_ui.js traduce acciones antiguas de la auditoría (CREATE_VIAJE_LARGO) que siguen guardadas.
PERMITIDOS = {"backend/repositories/turno.py", "frontend/js/seguridad_ui.js"}
PALABRAS = ("viajes_largos", "viaje_largo", "VIAJE_LARGO", "ViajeLargo", "ViajesLargos")


def test_el_codigo_ya_no_usa_viajes_largos():
    usos = []
    for carpeta in ("backend", "frontend"):
        for p in (RAIZ / carpeta).rglob("*"):
            if p.suffix not in (".py", ".js", ".html", ".css") or "tests" in p.parts or "__pycache__" in p.parts:
                continue
            if ".min." in p.name:
                continue
            rel = p.relative_to(RAIZ).as_posix()
            if rel in PERMITIDOS:
                continue
            texto = p.read_text(encoding="utf-8", errors="ignore")
            usos += [f"{rel}: {w}" for w in PALABRAS if w in texto]
    assert not usos, "Vuelven a aparecer los viajes largos:\n  " + "\n  ".join(usos)


def test_el_horario_ya_no_guarda_la_casilla_de_viajes():
    from backend.schemas.turno import TurnoCreate
    assert "permite_viajes_largos" not in TurnoCreate.model_fields
