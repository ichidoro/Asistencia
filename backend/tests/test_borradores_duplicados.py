"""El script que deja un solo borrador por persona: arma el plan sin borrar nada y conserva el más antiguo."""
import asyncio

from backend.scripts import corregir_borradores_duplicados as script
from backend.services.quantum_matrix_engine import MARCA_INASISTENCIA_LIBRETA


def test_el_plan_solo_incluye_a_quien_tiene_mas_de_un_borrador_real(monkeypatch):
    filas = [
        {"empleado_id": 1, "fecha": "2026-11-02", "observaciones": ""},
        {"empleado_id": 1, "fecha": "2026-11-05", "observaciones": ""},
        {"empleado_id": 1, "fecha": "2026-11-09", "observaciones": ""},
        {"empleado_id": 2, "fecha": "2026-11-02", "observaciones": ""},                                    # uno solo
        {"empleado_id": 3, "fecha": "2026-11-02", "observaciones": ""},
        {"empleado_id": 3, "fecha": "2026-11-04", "observaciones": MARCA_INASISTENCIA_LIBRETA + " x"},   # la inasistencia no cuenta
    ]

    async def fetch_all(*a, **k):
        return filas
    monkeypatch.setattr(script.db, "fetch_all", fetch_all)
    plan = asyncio.run(script._plan(None))
    assert plan == {1: ["2026-11-02", "2026-11-05", "2026-11-09"]}   # se conserva el primero y sobran los más recientes
