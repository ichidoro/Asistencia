"""Huella del cálculo y días «en curso» con la espera vencida (decisión del dueño, 23-11-2026)."""
import asyncio
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.core import events  # noqa: E402
from backend.services import huella_calculo as hc  # noqa: E402
from backend.services.en_curso_vencido import espera_vencida, vencidos  # noqa: E402

HOY = "2026-11-23"


def _fila(ent="11:30", sal="21:00", ventana=180, estado="EN_CURSO", fecha=HOY, emp=1):
    return {"empleado_id": emp, "fecha": fecha, "estado": estado, "hora_entrada_teorica": ent, "hora_salida_teorica": sal,
            "ventana_en_curso_turno": ventana}


# ── Días «en curso» con la espera vencida ─────────────────────────────

def test_dentro_de_la_espera_no_se_recalcula():
    assert not espera_vencida(_fila(), datetime(2026, 11, 23, 23, 59))


def test_pasada_la_espera_del_horario_se_recalcula():
    assert espera_vencida(_fila(), datetime(2026, 11, 24, 0, 0))


def test_la_espera_sale_del_horario():
    assert espera_vencida(_fila(ventana=30), datetime(2026, 11, 23, 21, 30))
    assert not espera_vencida(_fila(ventana=180), datetime(2026, 11, 23, 21, 30))


def test_turno_de_noche_sale_al_dia_siguiente():
    assert not espera_vencida(_fila(ent="22:00", sal="06:00", ventana=0), datetime(2026, 11, 23, 23, 0))


def test_sin_salida_teorica_no_se_decide():
    assert not espera_vencida(_fila(sal=None), datetime(2026, 11, 24, 12, 0))


def test_solo_los_en_curso_de_hoy():
    ahora = datetime(2026, 11, 23, 23, 0)
    filas = [_fila(ventana=0, emp=1), _fila(ventana=0, estado="OK", emp=2), _fila(ventana=0, fecha="2026-11-22", emp=3),
             _fila(ventana=180, emp=4)]
    assert vencidos(filas, HOY, ahora) == [(1, HOY)]


# ── Huella del cálculo ────────────────────────────────────────────────

def test_la_huella_sigue_las_importaciones_desde_el_motor():
    rutas = {p.relative_to(hc.RAIZ).as_posix() for p in hc.archivos_del_calculo()}
    assert "backend/services/quantum_matrix_engine.py" in rutas
    assert "backend/services/asistencia_service.py" in rutas
    assert "backend/core/sql_compat.py" in rutas          # la traducción de SQL también calcula
    assert "backend/services/huella_calculo.py" not in rutas


def test_la_huella_cambia_si_cambia_un_archivo(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "RAIZ", tmp_path)
    a = tmp_path / "a.py"
    a.write_bytes(b"x = 1\n")
    h1 = hc.huella([a])
    a.write_bytes(b"x = 1\r\n")
    assert hc.huella([a]) == h1                             # los saltos de línea de Windows no cuentan
    a.write_bytes(b"x = 2\n")
    assert hc.huella([a]) != h1


class _Db:
    def __init__(self, guardada):
        self.guardada, self.escrito = guardada, []

    async def fetch_one(self, q, p=None):
        return {"valor": self.guardada} if self.guardada is not None else None

    async def fetch_all(self, q, p=None):
        return [{"empleado_id": 7}]

    async def execute(self, q, p=None):
        self.escrito.append(p)


class _Servicio:
    def __init__(self):
        self.llamadas = []

    async def procesar_dia(self, fecha, force=False, empleado_ids=None):
        self.llamadas.append((force, empleado_ids))
        return len(empleado_ids or ())


def _arranque(monkeypatch, guardada):
    d, s = _Db(guardada), _Servicio()
    monkeypatch.setattr(events, "db", d)
    monkeypatch.setattr(hc, "huella", lambda archivos=None: "nueva")
    asyncio.run(events._recalcular_hoy_si_cambio_el_calculo(s))
    return d, s


def test_misma_huella_no_recalcula_nada(monkeypatch):
    d, s = _arranque(monkeypatch, "nueva")
    assert s.llamadas == [] and d.escrito == []


def test_huella_distinta_recalcula_hoy_sin_forzar_y_la_guarda(monkeypatch):
    d, s = _arranque(monkeypatch, "vieja")
    assert s.llamadas == [(False, {7})]
    assert any(p and "nueva" in p for p in d.escrito)


def test_la_primera_vez_solo_guarda_la_huella(monkeypatch):
    d, s = _arranque(monkeypatch, None)
    assert s.llamadas == [] and any(p and "nueva" in p for p in d.escrito)
