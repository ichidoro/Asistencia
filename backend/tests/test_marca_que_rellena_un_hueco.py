"""La propuesta de la regla en «Corregir marcas del día» se puede guardar aunque el reloj ya tenga Entrada y Salida.

Caso 19-11-2026 (JJV Produccion): Entrada 06:33 · Entrada 13:29 · Salida 17:34. La ventana propone «Faltó la salida a
colación: SALIDA 12:59», pero el servidor la rechazaba con «Esta jornada ya cuenta con marcaciones biométricas válidas
de Entrada y Salida». Una marca que cae ENTRE dos marcas que la piden completa la secuencia: no pisa al reloj.
Antes de la primera o después de la última sigue bloqueada (no sirve para borrar un atraso: para eso está el Perdonazo).
"""
from pathlib import Path

from backend.routers.asistencia_marcas import _rellena_un_hueco

RAIZ = Path(__file__).resolve().parents[2]
DIA = [{"fecha_hora": "2026-11-19 06:33:37", "tipo": "Entrada"},
       {"fecha_hora": "2026-11-19 13:29:56", "tipo": "Entrada"},
       {"fecha_hora": "2026-11-19 17:34:10", "tipo": "Salida"}]


def test_la_salida_a_colacion_entre_dos_entradas_se_permite():
    assert _rellena_un_hueco(DIA, "2026-11-19 12:59:00", "Salida")


def test_la_vuelta_de_colacion_entre_dos_salidas_se_permite():
    dia = [{"fecha_hora": "2026-11-19 07:00:00", "tipo": "Entrada"},
           {"fecha_hora": "2026-11-19 13:00:00", "tipo": "Salida"},
           {"fecha_hora": "2026-11-19 17:00:00", "tipo": "Salida"}]
    assert _rellena_un_hueco(dia, "2026-11-19 13:30:00", "Entrada")


def test_una_entrada_antes_de_la_primera_marca_sigue_bloqueada():
    # Escribir una Entrada más temprano borraría el atraso: eso es el Perdonazo
    dia = [{"fecha_hora": "2026-11-19 07:20:00", "tipo": "Entrada"}, {"fecha_hora": "2026-11-19 17:00:00", "tipo": "Salida"}]
    assert not _rellena_un_hueco(dia, "2026-11-19 06:55:00", "Entrada")


def test_una_salida_despues_de_la_ultima_sigue_bloqueada():
    dia = [{"fecha_hora": "2026-11-19 07:00:00", "tipo": "Entrada"}, {"fecha_hora": "2026-11-19 15:00:00", "tipo": "Salida"}]
    assert not _rellena_un_hueco(dia, "2026-11-19 17:30:00", "Salida")


def test_una_marca_que_no_alterna_sigue_bloqueada():
    # Una ENTRADA entre dos Entradas no completa nada
    assert not _rellena_un_hueco(DIA, "2026-11-19 12:59:00", "Entrada")
    # Una SALIDA entre una Entrada y una Salida tampoco
    assert not _rellena_un_hueco(DIA, "2026-11-19 15:00:00", "Salida")


def test_el_router_usa_la_excepcion_en_el_bloqueo():
    router = (RAIZ / "backend" / "routers" / "asistencia_marcas.py").read_text(encoding="utf-8")
    assert "get_marcas_del_dia_en_orden(empleado_id, fecha)" in router
    assert "not cierra_entrada and not rellena_hueco" in router
