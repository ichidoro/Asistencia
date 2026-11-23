"""Etapa B3c del plan de bonos (docs/PLAN_BONOS.md): la ventana del bono muestra, para el período vigente y con lo que
se está editando (sin guardarlo), quién lo recibe y cuánto; y avisa si alguien calza con más de una regla del mismo
bono (vacío L: se usaba la primera sin aviso). Al guardar con reglas que se pisan, pregunta antes.
Datos inventados; sin nombres de personas.
"""
import asyncio
from pathlib import Path

from backend.services import bono_service as bs

RAIZ = Path(__file__).resolve().parents[2]
BONO = {"nombre": "Bono", "reglas": [{"monto": 1000, "tipo_contrato": "Indefinido"}, {"monto": 500, "cargos_req_ids": [6]}],
        "efecto_inasistencia": "pierde", "efectos": {}}


def test_reglas_que_calzan():
    uno = {"cargo_id": 6, "tipo_contrato": "Indefinido"}
    assert bs.BonoService.reglas_que_calzan(uno, BONO) == [0, 1]                           # se pisan
    assert bs.BonoService.reglas_que_calzan({"cargo_id": 6, "tipo_contrato": "Temporal"}, BONO) == [1]
    assert bs.BonoService.reglas_que_calzan({"cargo_id": 7, "tipo_contrato": "Temporal"}, BONO) == []


class _DB:
    async def fetch_all(self, q, p=()):
        return []


def test_vista_previa(monkeypatch):
    m = {"info": {"tipo_programacion": "CICLO", "turno_dias": {}},
         "2026-10-27": {"estado": "OK", "horas_teoricas": 8}, "2026-10-28": {"estado": "INASISTENCIA", "horas_teoricas": 8}}
    datos = {"empleados": [{"id": 1, "nombre": "UNO", "apellido_paterno": "PERSONA", "cargo_id": 6, "tipo_contrato": "Indefinido",
                            "fecha_ingreso": "2020-01-01", "area": "AREA A"},
                           {"id": 2, "nombre": "DOS", "apellido_paterno": "PERSONA", "cargo_id": 7, "tipo_contrato": "Indefinido",
                            "fecha_ingreso": "2020-01-01", "area": "AREA A"},
                           {"id": 3, "nombre": "TRES", "apellido_paterno": "PERSONA", "cargo_id": 7, "tipo_contrato": "Temporal",
                            "fecha_ingreso": "2020-01-01", "area": "AREA B"}],
             "matrix": {1: m, 2: {k: v for k, v in m.items() if k != "2026-10-28"}, 3: m}, "data": [], "justificaciones": []}

    class _Srv:
        def __init__(self, *a):
            pass

        async def get_matriz_periodo(self, fi, ff, area, turno, search, areas_permitidas=None):
            return datos
    monkeypatch.setattr(bs, "AsistenciaService", _Srv)
    monkeypatch.setattr(bs, "AsistenciaRepository", lambda db: None)
    d = asyncio.run(bs.BonoService(_DB()).vista_previa(BONO, "2026-10-26", "2026-11-25"))
    assert [(p["nombre"], p["regla"], p["califica"], p["monto"]) for p in d["personas"]] == [
        ("PERSONA DOS", 1, True, 1000), ("PERSONA UNO", 1, False, 0)]          # TRES no calza con ninguna regla
    assert d["pisan"] == [{"nombre": "PERSONA UNO", "reglas": [1, 2]}]
    assert (d["total"], d["reciben"], d["no_cobran"]) == (1000, 1, 1)
    assert d["personas"][1]["motivo"] == "Inasistencia sin justificar: 1 día"     # resumido por causa


def test_pantalla_y_ruta():
    js = (RAIZ / "frontend" / "js" / "configuracion_ui.js").read_text(encoding="utf-8")
    html = (RAIZ / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'onclick="vistaPreviaBono()"' in html and 'id="bono-vista-previa"' in html
    assert "¿Guardar con reglas que se pisan?" in js
    rutas = (RAIZ / "backend" / "routers" / "configuracion.py").read_text(encoding="utf-8")
    assert '@router.post("/bonos/vista-previa/"' in rutas
