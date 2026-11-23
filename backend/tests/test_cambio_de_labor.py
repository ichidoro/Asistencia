"""Etapa B4b del plan de bonos (docs/PLAN_BONOS.md): «Cambiar labor desde una fecha» en la ficha de la persona. Corta el
tramo del historial de cargos el día antes y abre el nuevo; antes de guardar muestra qué bonos gana o pierde en el
período; no deja una fecha dentro de un período cerrado; avisa por correo a «Avisos generales» (decisión de la persona
dueña, 22-11-2026) y queda en la auditoría. Datos inventados; sin nombres de personas.
"""
from pathlib import Path

from backend.services.cambio_labor import tramos_con_cambio

RAIZ = Path(__file__).resolve().parents[2]
HOY = [{"cargo_id": 8, "desde": "2020-01-01", "hasta": None}]


def test_corta_el_tramo_vigente_el_dia_antes():
    assert tramos_con_cambio(HOY, 6, "2026-11-12") == [
        {"cargo_id": 8, "desde": "2020-01-01", "hasta": "2026-11-11"}, {"cargo_id": 6, "desde": "2026-11-12", "hasta": None}]


def test_cambio_en_el_primer_dia_de_un_tramo_lo_reemplaza():
    dos = [{"cargo_id": 8, "desde": "2020-01-01", "hasta": "2026-11-11"}, {"cargo_id": 6, "desde": "2026-11-12", "hasta": None}]
    assert tramos_con_cambio(dos, 7, "2026-11-12")[1] == {"cargo_id": 7, "desde": "2026-11-12", "hasta": None}


def test_cambio_antes_de_un_cambio_futuro_dura_hasta_el():
    dos = [{"cargo_id": 8, "desde": "2020-01-01", "hasta": "2026-11-25"}, {"cargo_id": 6, "desde": "2026-11-26", "hasta": None}]
    r = tramos_con_cambio(dos, 7, "2026-11-12")
    assert r == [{"cargo_id": 8, "desde": "2020-01-01", "hasta": "2026-11-11"}, {"cargo_id": 7, "desde": "2026-11-12", "hasta": "2026-11-25"},
                 {"cargo_id": 6, "desde": "2026-11-26", "hasta": None}]


def test_rutas_correo_y_pantalla():
    rutas = (RAIZ / "backend" / "routers" / "empleados.py").read_text(encoding="utf-8")
    assert '"/{empleado_id}/historial-cargos/"' in rutas and '"/{empleado_id}/cambiar-labor/vista-previa/"' in rutas
    assert '"/{empleado_id}/cambiar-labor/"' in rutas and 'RequirePermission("empleados.editar")' in rutas
    svc = (RAIZ / "backend" / "services" / "cambio_labor.py").read_text(encoding="utf-8")
    assert "FROM cierres_periodos WHERE area = ?" in svc and "get_destinatarios_rrhh" in svc and '"CAMBIO_LABOR"' in svc
    assert "async def send_cambio_labor_email" in (RAIZ / "backend" / "services" / "notification_service.py").read_text(encoding="utf-8")
    assert "CambioLaborService(_db).aplicar_cargos_vigentes()" in (RAIZ / "backend" / "routers" / "sync.py").read_text(encoding="utf-8")
    html = (RAIZ / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (RAIZ / "frontend" / "js" / "main.js").read_text(encoding="utf-8")
    assert 'id="tab-emp-cargos"' in html and 'onclick="abrirCambiarLabor(currentEmpleadoId)"' in html
    assert "window.abrirCambiarLabor = async function" in js and "¿Guardar el cambio de labor?" in js
