# -*- coding: utf-8 -*-
"""El motor lee las Reglas de marcaciones SOLO cuando están encendidas.

Garantías que se prueban aquí:
  1. Con el registro vacío (ninguna regla encendida) el motor calcula EXACTAMENTE
     igual que antes: el despliegue no cambia nada.
  2. EXTREMOS lee la primera marca como Entrada y la última como Salida
     (casos reales: Nancy Donoso S·S·E·S y Katherine Galaz E·S·E).
  3. Las reglas jamás tocan el día en curso, ni Bolsa Flexible, ni secuencias
     sin regla encendida.
  4. SOLO_REVISA deja el día en anomalía con el marcador de revisión.
  5. El rebote del ajuste solo reemplaza el 180 por defecto en Ciclo Inteligente.
"""
import os
from datetime import datetime

import pytest

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import quantum_matrix_engine as qme  # noqa: E402
from backend.services.quantum_matrix_engine import QuantumMatrixEngine as Q  # noqa: E402
from backend.services.quantum_matrix_engine import _aplicar_extremos, _rebote_defecto  # noqa: E402

E, S = "Entrada", "Salida"
AHORA = datetime(2026, 10, 19, 12, 0)   # «hoy» del motor en estas pruebas


def L(i, fh, tipo, manual=0):
    return {"id": i, "fecha_hora": fh, "tipo": tipo, "manual": manual, "observaciones": None}


TURNO = {"tipo_programacion": "CICLO_INTELIGENTE", "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0,
         "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "umbral_horas_colacion": 5.5,
         "anclaje_entrada_minutos": 0, "anclaje_salida_minutos": 0}
DIA = {"es_libre": 0, "horas_teoricas": 9.0, "hora_entrada": "07:00", "hora_salida": "16:30", "cruza_medianoche": 0}
TURNO_BOLSA = dict(TURNO, tipo_programacion="BOLSA_FLEXIBLE")


def _dia(monkeypatch, marcas, fecha="2026-10-15", turno=None, dia=None, ahora=AHORA):
    monkeypatch.setattr(qme, "_get_now_local", lambda: ahora)
    return Q.solve_attendance_day(fecha=fecha, empleado_id=1, logs=[dict(m) for m in marcas],
                                  turno_config=turno or TURNO, dia_config=dia or DIA,
                                  global_ajustes={}, todos_ciclos_dia=[dia or DIA], consumidas_previas=set())


@pytest.fixture(autouse=True)
def _registro_limpio():
    """Cada prueba parte sin reglas encendidas y sin rebote propio, y lo deja igual al salir."""
    qme.REGLAS_MARCAS_ACTIVAS = {}
    qme.REGLAS_MARCAS_REBOTE = None
    yield
    qme.REGLAS_MARCAS_ACTIVAS = {}
    qme.REGLAS_MARCAS_REBOTE = None


def _regla(sec, lectura="EXTREMOS", colacion="TURNO", accion="CALCULA"):
    qme.REGLAS_MARCAS_ACTIVAS[sec] = {"secuencia": sec, "lectura": lectura,
                                      "colacion": colacion, "accion": accion}


# Casos reales de Producción
NANCY = [L(1, "2026-10-15 06:49:32", S), L(2, "2026-10-15 13:00:19", S),
         L(3, "2026-10-15 13:26:28", E), L(4, "2026-10-15 16:35:27", S)]          # S·S·E·S
GALAZ = [L(1, "2026-10-15 06:23:42", E), L(2, "2026-10-15 13:06:22", S),
         L(3, "2026-10-15 13:27:53", E)]                                           # E·S·E
DOS_ENTRADAS = [L(1, "2026-10-15 07:01:00", E), L(2, "2026-10-15 16:31:00", E)]    # E·E
NORMAL = [L(1, "2026-10-15 06:58:00", E), L(2, "2026-10-15 13:00:00", S),
          L(3, "2026-10-15 13:30:00", E), L(4, "2026-10-15 16:31:00", S)]          # E·S·E·S


# ── 1. Garantía de no cambio ─────────────────────────────────────────────────

def test_sin_reglas_encendidas_el_motor_calcula_igual_que_antes(monkeypatch):
    base = {m: _dia(monkeypatch, marcas) for m, marcas in
            (("nancy", NANCY), ("galaz", GALAZ), ("ee", DOS_ENTRADAS), ("normal", NORMAL))}
    # Una regla encendida de OTRA secuencia tampoco cambia nada
    _regla("ESSS")
    for nombre, marcas in (("nancy", NANCY), ("galaz", GALAZ), ("ee", DOS_ENTRADAS), ("normal", NORMAL)):
        assert _dia(monkeypatch, marcas) == base[nombre], nombre


def test_sin_reglas_nancy_sigue_mal_como_hoy(monkeypatch):
    r = _dia(monkeypatch, NANCY)
    assert r["hora_entrada_real"] == "13:26:28"          # el motor de hoy ignora la Salida huérfana inicial
    assert "Salida huérfana inicial" in r["observaciones"]


# ── 2. EXTREMOS ──────────────────────────────────────────────────────────────

def test_nancy_con_la_regla_sses_queda_con_su_dia_completo(monkeypatch):
    _regla("SSES", colacion="MEDIDA")
    r = _dia(monkeypatch, NANCY)
    assert r["hora_entrada_real"] == "06:49:32" and r["hora_salida_real"] == "16:35:27"
    assert round(r["minutos_colacion_real"]) == 26        # la pausa 13:00 → 13:26 es la colación medida
    # 06:49:32→13:00:19 más 13:26:28→16:35:27, menos el resto de la colación pactada (este turno
    # de prueba no tiene anclajes; con los anclajes del turno real queda en ~9,1 h, como al corregirla a mano)
    assert abs(r["horas_trabajadas"] - 9.2653) < 0.01
    assert set(r["marcas_consumidas_ids"]) == {1, 2, 3, 4}
    assert "Regla de marcaciones (S · S · E · S)" in r["observaciones"]


def test_galaz_con_la_regla_ese_calcula_con_extremos_y_avisa(monkeypatch):
    _regla("ESE", accion="CALCULA_Y_REVISA")
    r = _dia(monkeypatch, GALAZ)
    assert r["hora_entrada_real"] == "06:23:42" and r["hora_salida_real"] == "13:27:53"
    assert qme.MARCA_REVISION_REGLA in r["observaciones"]
    assert r["estado"] in ("SALIDA_ADELANTADA", "ATRASO")  # sigue con su salida anticipada a la vista


def test_dos_entradas_con_la_regla_ee_dia_completo_con_colacion_del_turno(monkeypatch):
    _regla("EE", accion="CALCULA_Y_REVISA")
    r = _dia(monkeypatch, DOS_ENTRADAS)
    assert r["hora_entrada_real"] == "07:01:00" and r["hora_salida_real"] == "16:31:00"
    assert round(r["minutos_colacion"]) == 30             # colación automática del turno
    assert qme.MARCA_REVISION_REGLA in r["observaciones"]


def test_colacion_turno_descarta_la_pausa_y_colacion_medida_la_usa():
    sses = _aplicar_extremos(NANCY, "MEDIDA")
    assert [(l["tipo"], l["id"]) for l in sses] == [(E, 1), (S, 2), (E, 3), (S, 4)]
    solo_extremos = _aplicar_extremos(NANCY, "TURNO")
    assert [(l["tipo"], l["id"]) for l in solo_extremos] == [(E, 1), (S, 4)]
    assert NANCY[0]["tipo"] == S                          # las marcas originales no se tocan


def test_regla_es_sobre_un_dia_bien_marcado_no_cambia_nada(monkeypatch):
    base = _dia(monkeypatch, [L(1, "2026-10-15 07:01:00", E), L(2, "2026-10-15 16:31:00", S)])
    _regla("ES")
    r = _dia(monkeypatch, [L(1, "2026-10-15 07:01:00", E), L(2, "2026-10-15 16:31:00", S)])
    assert r == base
    assert "Regla de marcaciones" not in (r.get("observaciones") or "")


# ── 3. Dónde las reglas NO entran ────────────────────────────────────────────

def test_la_regla_no_toca_el_dia_en_curso(monkeypatch):
    _regla("ESE", accion="CALCULA_Y_REVISA")
    hoy = _dia(monkeypatch, GALAZ, ahora=datetime(2026, 10, 15, 14, 0))   # el 15-10 ES hoy
    assert qme.MARCA_REVISION_REGLA not in (hoy.get("observaciones") or "")


def test_la_regla_no_toca_bolsa_flexible(monkeypatch):
    _regla("SSES", colacion="MEDIDA")
    base_sin = _dia(monkeypatch, NANCY, turno=TURNO_BOLSA)
    qme.REGLAS_MARCAS_ACTIVAS = {}
    assert _dia(monkeypatch, NANCY, turno=TURNO_BOLSA) == base_sin


def test_una_jornada_nocturna_que_termino_ayer_si_entra_y_la_de_anoche_no(monkeypatch):
    _regla("EE", accion="CALCULA_Y_REVISA")
    noche = {"es_libre": 0, "horas_teoricas": 8.0, "hora_entrada": "23:00", "hora_salida": "07:00", "cruza_medianoche": 1}
    marcas = [L(1, "2026-10-17 23:01:00", E), L(2, "2026-10-18 07:02:00", E)]
    r = _dia(monkeypatch, marcas, fecha="2026-10-17", dia=noche)           # terminó el 18, hoy es 19 → entra
    assert qme.MARCA_REVISION_REGLA in r["observaciones"]
    marcas2 = [L(1, "2026-10-18 23:01:00", E), L(2, "2026-10-19 07:02:00", E)]
    r2 = _dia(monkeypatch, marcas2, fecha="2026-10-18", dia=noche)         # terminó HOY 19 → todavía no entra
    assert qme.MARCA_REVISION_REGLA not in (r2.get("observaciones") or "")


# ── 4. SOLO_REVISA ───────────────────────────────────────────────────────────

def test_solo_revisa_deja_el_dia_en_anomalia_sin_horas(monkeypatch):
    _regla("ESE", lectura="NINGUNA", accion="SOLO_REVISA")
    r = _dia(monkeypatch, GALAZ)
    assert r["estado"] == "ANOMALIA" and r["horas_trabajadas"] == 0.0
    assert r["hora_entrada_real"] == "06:23:42" and r["hora_salida_real"] == "13:27:53"
    assert qme.MARCA_REVISION_REGLA in r["observaciones"]
    assert set(r["marcas_consumidas_ids"]) == {1, 2, 3}   # las marcas siguen consumidas por el día


# ── 5. Rebote ────────────────────────────────────────────────────────────────

def test_rebote_del_ajuste_solo_para_ciclo_inteligente():
    assert _rebote_defecto("CICLO_INTELIGENTE") == 180.0
    qme.REGLAS_MARCAS_REBOTE = 240.0
    assert _rebote_defecto("CICLO_INTELIGENTE") == 240.0
    assert _rebote_defecto("BOLSA_FLEXIBLE") == 180.0
    qme.REGLAS_MARCAS_REBOTE = 0
    assert _rebote_defecto("CICLO_INTELIGENTE") == 180.0
