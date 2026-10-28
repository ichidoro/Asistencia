# -*- coding: utf-8 -*-
"""Dashboard «Lo que falta hacer» (estructura B, elegida por el dueño el 27-10-2026).

El Dashboard anterior mostraba números que se contradecían en la misma pantalla: el «En vivo»
contaba solo a quien entraba en una franja fija del reloj (0 de 0 en la tarde), la lista sumaba
como ausentes a los choferes con libreta y a las licencias, y «contratos por vencer» buscaba un
tipo de contrato que no existe en la base. Estas pruebas cuidan las reglas del nuevo.
"""
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services.dashboard_pendientes import (  # noqa: E402
    clasificar_area, resumir_contratos, visible,
)

RAIZ = Path(__file__).resolve().parents[2]


def _leer(rel):
    return (RAIZ / rel).read_text(encoding="utf-8")


def test_el_area_se_muestra_segun_filtro_y_alcance():
    assert visible("PRODUCCION", None, None)
    assert not visible(None, None, None)
    assert not visible("PRODUCCION", "LOGISTICA", None)
    assert visible("LOGISTICA", "LOGISTICA", None)
    assert not visible("PRODUCCION", None, ["LOGISTICA"])
    assert visible("LOGISTICA", None, ["LOGISTICA"])


def test_un_area_cerrada_no_muestra_bloqueos():
    r = clasificar_area({"fecha": "2026-10-27 14:35:59", "por": "rortiz", "tipo": "JEFE_AREA"}, None)
    assert r["estado"] == "cerrado" and r["cerrado"]["por"] == "rortiz"


def test_lista_para_cerrar_igual_que_el_asistente():
    # Caso real (Mantención, octubre 2026): nada que la bloquee
    assert clasificar_area(None, {})["estado"] == "listo"
    # Las inasistencias no bloquean: se aceptan con la casilla al cerrar
    r = clasificar_area(None, {"inasistencias": 4})
    assert r["estado"] == "listo" and r["inasistencias"] == 4


def test_cada_bloqueo_del_asistente_deja_el_area_pendiente():
    for clave in ("he_pendientes", "por_revisar", "libreta_dias", "anomalias", "otros_pendientes", "en_curso"):
        assert clasificar_area(None, {clave: 1})["estado"] == "pendiente", clave


def test_logistica_octubre_libreta_y_dia_por_revisar():
    # Caso real: 280 días de libreta sin registrar de 15 choferes y 1 día por revisar (01-10)
    r = clasificar_area(None, {"libreta_dias": 280, "libreta_personas": 15, "por_revisar": 1,
                               "fechas_por_revisar": ["2026-10-01"], "inasistencias": 4,
                               "he_pendientes": 0, "he_minutos": 0})
    assert r["estado"] == "pendiente"
    assert (r["libreta_dias"], r["libreta_personas"], r["por_revisar"]) == (280, 15, 1)
    assert r["fechas_por_revisar"] == ["2026-10-01"]


def test_horas_extra_en_horas_con_un_decimal():
    r = clasificar_area(None, {"he_pendientes": 3, "he_minutos": 95})
    assert r["he_horas"] == 1.6 and r["he_minutos"] == 95


def test_contratos_se_agrupan_por_fecha_sin_nombres():
    emps = [
        {"fecha_salida": "2026-10-30", "decision_vencimiento": None},
        {"fecha_salida": "2026-10-30", "decision_vencimiento": ""},
        {"fecha_salida": "2026-11-15", "decision_vencimiento": "NO_RENOVAR"},
        {"fecha_salida": "2026-10-20", "decision_vencimiento": None},
        {"fecha_salida": None, "decision_vencimiento": None},
    ]
    r = resumir_contratos(emps, "2026-10-27", 20)
    assert r["dias"] == 20
    assert r["total"] == 3 and r["vencidos"] == 1 and r["sin_decision"] == 3
    assert r["por_fecha"] == [{"fecha": "2026-10-30", "total": 2}, {"fecha": "2026-11-15", "total": 1}]
    assert "nombre" not in str(r)


def test_dashboard_y_cierre_usan_la_misma_revision():
    cierre = _leer("backend/services/cierre_service.py")
    dash = _leer("backend/services/dashboard_pendientes.py")
    assert "async def bloqueos_cierre" in cierre
    inicio = cierre.index("async def evaluar_cierre")
    assert "await self.bloqueos_cierre(" in cierre[inicio:], "el asistente de cierre dejó de usar la revisión compartida"
    assert "bloqueos_cierre(" in dash, "el Dashboard dejó de usar la revisión del cierre"


def test_sin_franjas_fijas_del_reloj_ni_contratos_inventados():
    dash = _leer("backend/services/dashboard_pendientes.py")
    for texto in ("05:00:00", "14:00:00", "22:00:00", "Plazo Fijo"):
        assert texto not in dash, f"volvió un valor fijo al Dashboard: {texto}"
    assert '"vencimiento_dias_alerta"' in dash, "la ventana de contratos ya no sale del ajuste de Configuración"
    assert not (RAIZ / "backend/services/dashboard_service.py").exists()
    assert not (RAIZ / "backend/services/dashboard_analytics.py").exists()


def test_la_pantalla_usa_la_lectura_nueva_y_lleva_a_marcaciones():
    app = _leer("dashboard_build/src/DashboardApp.jsx")
    assert "/dashboard/pendientes/" in app
    assert "/dashboard/pulse/" not in app and "/dashboard/analytics/" not in app
    assert "abrirMarcacionesDesde" in app
    js = _leer("frontend/js/marcaciones_ui.js")
    assert "window.abrirMarcacionesDesde = async function" in js
