# -*- coding: utf-8 -*-
"""Con el equipo en modo oscuro, la aplicación refuerza el modo claro (styles.css). Ese refuerzo no puede tapar
el estado de una casilla ni el texto de una etiqueta.

Caso real (07-11-2026): en «Asignar turno oficial», la casilla «Descargar las marcas desde BioAlba» estaba
marcada pero se veía vacía (fondo blanco forzado bajo un ✓ blanco), y se descargaron marcas que se creían
desactivadas. La etiqueta «Tipo Planificación» se veía vacía (texto del mismo color que su fondo).
"""
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _bloque_oscuro():
    with open(os.path.join(RAIZ, 'frontend', 'css', 'styles.css'), encoding='utf-8') as f:
        css = f.read()
    ini = css.index('@media (prefers-color-scheme: dark)')
    nivel, i = 0, css.index('{', ini)
    for j in range(i, len(css)):
        nivel += {'{': 1, '}': -1}.get(css[j], 0)
        if nivel == 0:
            return css[i:j]
    raise AssertionError('bloque sin cerrar')


def _reglas(bloque):
    bloque = re.sub(r'/\*.*?\*/', '', bloque, flags=re.S)   # los comentarios no son selectores
    return [(sel.strip(), cuerpo) for sel, cuerpo in re.findall(r'([^{}]+)\{([^{}]*)\}', bloque)]


def test_el_fondo_forzado_no_alcanza_a_casillas_ni_botones_de_opcion():
    for sel, cuerpo in _reglas(_bloque_oscuro()):
        if 'background' not in cuerpo:
            continue
        for s in (x.strip() for x in sel.split(',')):
            if re.fullmatch(r'input(\[[^\]]*\])?', s) or s == 'input':
                raise AssertionError(f'«{s}» fuerza el fondo de todas las casillas: excluya checkbox y radio')
            if s.startswith('input') and ':not' in s:
                assert 'checkbox' in s and 'radio' in s, s


def test_las_etiquetas_conservan_su_color_de_texto():
    for sel, cuerpo in _reglas(_bloque_oscuro()):
        sels = [x.strip() for x in sel.split(',')]
        if '.badge' in sels:
            assert 'color: inherit' not in cuerpo, '«.badge» con color heredado deja el texto del color del fondo'
