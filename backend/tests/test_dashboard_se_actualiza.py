# -*- coding: utf-8 -*-
"""El Dashboard vuelve a pedir sus datos al entrar y al cerrar o reabrir un período (dueño, 13-11-2026)."""
import os

R = os.path.join(os.path.dirname(__file__), '..', '..')


def _leer(*p):
    return open(os.path.join(R, *p), encoding='utf-8').read()


def test_fuente_del_dashboard():
    app = _leer('dashboard_build', 'src', 'DashboardApp.jsx')
    assert "[cargar, vista, visita]" in app and "[cargarIndicadores, vista, visita]" in app
    assert "addEventListener('aguacol:periodos-cambiaron'" in app and "removeEventListener('aguacol:periodos-cambiaron'" in app
    assert '<DashboardApp visita={++visitas} />' in _leer('dashboard_build', 'src', 'main.jsx')


def test_bundle_armado_y_avisos():
    assert 'aguacol:periodos-cambiaron' in _leer('frontend', 'js', 'dashboard_react.js')
    js = _leer('frontend', 'js', 'marcaciones_ui.js')
    assert js.count("window.dispatchEvent(new CustomEvent('aguacol:periodos-cambiaron'))") == 2   # al sellar y al reabrir
