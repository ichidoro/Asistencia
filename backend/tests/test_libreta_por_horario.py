# -*- coding: utf-8 -*-
"""Cada horario de libreta tiene su propia fecha «Sin reloj a partir de» (orden del dueño, 27-10-2026: «cada área debe tener
su fecha de partida con la libreta»; Logística Transporte desde el 26-09 y Tradicional Transporte sigue desde el 01-10).
Antes era una sola fecha para todos los horarios (ajuste asistencia_libreta_180h_bolsa_desde)."""
import os
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services.libreta_corte import REGIMEN_LIBRETA, REGIMEN_RELOJ, fecha_libreta_del_horario, regimen_del_dia  # noqa: E402
from backend.services.quantum_matrix_engine import QuantumMatrixEngine as Q  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
LOGISTICA = {"modalidad_control": "LIBRETA_180H", "tipo_programacion": "BOLSA_FLEXIBLE", "libreta_desde": "2026-09-26"}
TRADICIONAL = {"modalidad_control": "LIBRETA_180H", "tipo_programacion": "BOLSA_FLEXIBLE", "libreta_desde": "2026-10-01"}


def _regimen(horario, fecha):
    return regimen_del_dia(fecha, horario["modalidad_control"], horario["tipo_programacion"], fecha_libreta_del_horario(horario))


def test_cada_horario_cambia_a_libreta_en_su_propia_fecha():
    assert _regimen(LOGISTICA, "2026-09-26") == REGIMEN_LIBRETA
    assert _regimen(TRADICIONAL, "2026-09-26") == REGIMEN_RELOJ
    assert _regimen(TRADICIONAL, "2026-09-30") == REGIMEN_RELOJ
    assert _regimen(TRADICIONAL, "2026-10-01") == REGIMEN_LIBRETA


def test_el_calculo_del_dia_lee_la_fecha_del_horario():
    assert Q.resolve_control_modality(LOGISTICA, "2026-09-27") is True
    assert Q.resolve_control_modality(TRADICIONAL, "2026-09-27") is False


def test_un_horario_de_reloj_nunca_es_libreta():
    assert Q.resolve_control_modality({"modalidad_control": "RELOJ", "tipo_programacion": "CICLO_INTELIGENTE",
                                       "libreta_desde": "2026-09-26"}, "2026-10-05") is False


def test_un_horario_de_libreta_sin_fecha_es_libreta_siempre():
    assert Q.resolve_control_modality(dict(LOGISTICA, libreta_desde=None), "2026-01-01") is True


def test_la_fecha_del_horario_se_valida_al_guardar():
    from pydantic import ValidationError
    from backend.schemas.turno import TurnoCreate
    base = {"nombre": "Prueba", "dias": [], "tipo_programacion": "BOLSA_FLEXIBLE", "modalidad_control": "LIBRETA_180H"}
    assert TurnoCreate(**base, libreta_desde="2026-09-26").libreta_desde == "2026-09-26"
    assert TurnoCreate(**base, libreta_desde="").libreta_desde is None
    with pytest.raises(ValidationError):
        TurnoCreate(**base, libreta_desde="26-09-2026")


def test_nadie_lee_la_fecha_unica_antigua():
    # Solo la migración de TurnoRepository (que la copia a cada horario y la borra) y el comentario de libreta_corte la nombran.
    permitidos = {"backend/repositories/turno.py", "backend/services/libreta_corte.py"}
    for carpeta in ("backend", "frontend"):
        for p in (RAIZ / carpeta).rglob("*"):
            if p.suffix not in (".py", ".js", ".html") or "tests" in p.parts or "__pycache__" in p.parts:
                continue
            rel = p.relative_to(RAIZ).as_posix()
            if "asistencia_libreta_180h_bolsa_desde" in p.read_text(encoding="utf-8", errors="ignore"):
                assert rel in permitidos, f"{rel} vuelve a leer la fecha única de libreta"


def test_la_leyenda_de_la_linea_violeta_sobrevive_al_minificador():
    rjsmin = pytest.importorskip("rjsmin")
    m = rjsmin.jsmin((RAIZ / "frontend/js/marcaciones_ui.js").read_text(encoding="utf-8"))
    assert " se usa libreta (fecha del horario de cada persona); antes, reloj biométrico" in m
