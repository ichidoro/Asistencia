# -*- coding: utf-8 -*-
"""El cierre frena con jornadas especiales por validar (dueño, 15-11-2026): se habían cerrado meses con días libres o
feriados trabajados sin decidir, que así no se pagan."""
import os

from backend.services.dashboard_pendientes import clasificar_area

R = os.path.join(os.path.dirname(__file__), '..', '..')


def _leer(*p):
    return open(os.path.join(R, *p), encoding='utf-8').read()


def test_el_cierre_las_revisa_y_no_deja_cerrar():
    src = _leer('backend', 'services', 'cierre_service.py')
    assert "HARD STOP 5: Jornadas especiales por validar" in src
    assert "NOT IN ('EXTRA', 'HORAS_EXTRAS', 'COMPENSATORIA')" in src and "!= 'COBERTURA_TURNO'" in src
    assert "and len(je_por_validar) == 0" in src
    assert 'if evaluacion.get("je_por_validar", 0) > 0:' in src


def test_el_dashboard_no_la_muestra_lista_para_cerrar():
    assert clasificar_area(None, {"je_por_validar": 2})["estado"] == "pendiente"
    assert clasificar_area(None, {})["estado"] == "listo"
    assert clasificar_area(None, {"je_por_validar": 2})["je_por_validar"] == 2


def test_el_asistente_y_el_dashboard_las_muestran():
    js = _leer('frontend', 'js', 'marcaciones_ui.js')
    assert 'const jeN = ev.je_por_validar || 0;' in js and 'ev.detalle_je' in js
    assert "je_por_validar" in _leer('dashboard_build', 'src', 'DashboardApp.jsx')
    assert "je_por_validar" in _leer('frontend', 'js', 'dashboard_react.js')


def test_el_mensaje_del_cierre_dice_si_se_envio_el_correo():
    src = _leer('backend', 'services', 'cierre_service.py')
    assert 'correo = "sin_destinatarios"' in src and 'correo = "enviado" if enviado else "no_enviado"' in src
    assert '"correo": correo}' in src
    js = _leer('frontend', 'js', 'marcaciones_ui.js')
    assert "}[res.correo] || 'El informe no se pudo enviar por correo.')" in js
    assert 'se envió a Recursos Humanos. También queda' not in js
