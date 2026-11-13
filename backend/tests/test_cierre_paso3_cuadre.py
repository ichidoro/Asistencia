# -*- coding: utf-8 -*-
"""Paso 3 del cierre (dueño, 13-11-2026): las horas extra se cuadran por persona con la ventana de cuadre y el período del
cierre; aprobar día por día queda como excepción y ya no hay «Aprobar Todas»."""
import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'js')


def _js(nombre):
    return open(os.path.join(RAIZ, nombre), encoding='utf-8').read()


def _paso3(js):
    i = js.index('window.cierrePaso3 = async function')
    return js[i:js.index('async function recargarPreEvaluacionCierre', i)]


def test_paso3_lista_personas_y_no_aprueba_todo():
    js = _js('marcaciones_ui.js')
    assert 'window.cierrePaso3(content, btnNext, ev);' in js
    assert 'cierreResolverTodasHE()' not in js          # el botón «Aprobar Todas» ya no se dibuja
    p = _paso3(js)
    assert '/api/cuadre/libro-periodo/?fecha_inicio=' in p
    assert 'Faltan cuadrar (' in p and 'Ya cuadradas (' in p
    assert "cierreResolverHE(" in p                     # el día suelto sigue disponible como excepción


def test_paso3_abre_el_cuadre_con_el_periodo_del_cierre():
    js = _js('marcaciones_ui.js')
    assert re.search(r"openCuadreModal\(empleadoId, nombre, \{ tramo: \{ inicio: s\.fIni, fin: s\.fFin \}, alCambiar: \(\) => recargarPreEvaluacionCierre\(\) \}\)", js)
    # Un rango que no es un período no crea una política con fechas sueltas
    assert 'const esTramo = (s.periodos || []).some(p => p.fecha_inicio === s.fIni && p.fecha_fin === s.fFin);' in _paso3(js)


def test_ventana_de_cuadre_acepta_tramo_y_avisa():
    js = _js('cuadre_ui.js')
    assert 'window.openCuadreModal = async function (empleadoId, nombre, opciones)' in js
    assert 'const p = estado.tramo ||' in js
    assert js.count('avisarCambio();') == 2             # al confirmar y al quitar la política
    assert "(estado.tramo ? '' : '<button type=\"button\" class=\"cq-link\" onclick=\"window.cuadreAjusteManual()\">" in js
