# -*- coding: utf-8 -*-
"""Días por revisar en la grilla y en la ventana de corrección (versión C mejorada, elegida por el dueño el 06-11-2026).

- La celda dice el estado con la sigla y el color de Configuración → Estados (la sigla admite hasta 7 letras, para REVISAR);
  ya no hay triángulo en la esquina.
- Bajo la fila de la persona, una lista con cada día por revisar: su regla, sus marcas con tipo y hora (la que el sistema
  propone cambiar, marcada), su turno y el botón «Revisar». El título del bloque (que parte plegado) avisa cuántos hay.
- La ventana deja elegida en rojo la marca que el sistema propone cambiar, bloquea la parte de abajo cuando la regla solo
  permite cambiar el tipo de una marca o confirmar, y pregunta «¿Está seguro de la corrección?» antes de guardar.
"""
import os
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "x" * 40)

RAIZ = Path(__file__).resolve().parents[2]


def _leer(rel):
    return (RAIZ / rel).read_text(encoding="utf-8")


GRILLA_JS = _leer("frontend/js/marcaciones_ui.js")
MODAL_JS = _leer("frontend/js/marcaciones_manuales.js")
CONFIG_JS = _leer("frontend/js/configuracion_ui.js")
MATRIZ = _leer("backend/services/asistencia_service.py")
GRILLA_CSS = _leer("frontend/css/grilla-hd.css")
VENTANAS_CSS = _leer("frontend/css/ventanas.css")


# ── Sigla de hasta 7 letras y color «Rojo intenso» ──────────────────────────────

def test_la_sigla_del_estado_admite_hasta_siete_letras():
    from backend.routers import configuracion as C
    assert C.SIGLA_MAX == 7
    assert C._RE_SIGLA.match("REVISAR")
    assert not C._RE_SIGLA.match("REVISARX"), "8 letras no caben en la pastilla"
    assert C._RE_SIGLA.match("ANO") and C._RE_SIGLA.match("C.HE")


def test_el_rojo_intenso_se_puede_elegir_y_se_dibuja():
    from backend.routers import configuracion as C
    assert "color-rojo-intenso" in C._COLORES_ESTADO_VALIDOS
    assert "color-rojo-intenso" in CONFIG_JS, "la pantalla de Estados no ofrece el color"
    assert ".badge-status.color-rojo-intenso" in GRILLA_CSS, "la grilla no sabe dibujar el color"
    assert ".color-rojo-intenso" in _leer("frontend/css/styles.css")


def test_la_pantalla_de_estados_acepta_siete_letras():
    assert 'maxlength="7"' in CONFIG_JS and "{1,7}" in CONFIG_JS
    assert 'maxlength="5"' not in CONFIG_JS and "{1,5}" not in CONFIG_JS


def test_la_sigla_larga_cabe_en_la_pastilla():
    assert "st-largo" in GRILLA_JS and "st-largo" in GRILLA_CSS


# ── La grilla: celda, lista bajo la fila y aviso del bloque ─────────────────────

def test_la_matriz_entrega_la_regla_y_sus_opciones_de_cada_dia():
    assert "revision_secuencia" in MATRIZ and "revision_opciones" in MATRIZ
    assert "secuencia_en_revision" in MATRIZ
    assert "opciones_revision FROM reglas_marcas" in MATRIZ, "las opciones deben salir de la regla guardada"


def test_la_celda_ya_no_lleva_el_triangulo_y_lo_dice_al_lector_de_pantalla():
    assert "border-top:11px solid #dc2626" not in GRILLA_JS, "volvió el triángulo de la esquina"
    assert "rv-celda" in GRILLA_JS and "rv-celda-marco" in GRILLA_CSS
    assert "Una regla de marcaciones dejó este día en revisión." in GRILLA_JS


def test_la_grilla_lista_los_dias_bajo_la_fila():
    for clave in ("mxBandaRevisionHtml", "mxBandasAjustar", "mxBandasCargarMarcas", "mxAvisoBloqueHtml",
                  "mxActualizarAvisoBloque", "mxAvisarCorreccion", "rv-banda"):
        assert clave in GRILLA_JS, f"falta {clave} en la grilla"
    assert "/api/asistencia/marcaciones/dia/" in GRILLA_JS, "las marcas deben salir del mismo servicio que la ventana"
    assert "'RECLASIFICAR'" in GRILLA_JS, "la propuesta solo va cuando la regla permite cambiar el tipo de una marca"
    assert "bandaVieja" in GRILLA_JS, "al recargar una fila hay que quitar su lista vieja"


# ── La ventana: propuesta en rojo, parte de abajo bloqueada y pregunta ──────────

def test_la_ventana_pregunta_antes_de_guardar_la_clasificacion():
    assert "_mmConfirmarClasificacion" in MODAL_JS
    assert "¿Está seguro de la corrección?" in MODAL_JS
    i = MODAL_JS.index("getElementById('btn-marcas-guardar')") if "getElementById('btn-marcas-guardar')" in MODAL_JS \
        else MODAL_JS.index("#btn-marcas-guardar').addEventListener")
    bloque = MODAL_JS[i:i + 1200]
    assert bloque.index("_mmConfirmarClasificacion") < bloque.index("/api/asistencia/marcaciones/reclasificar/"), \
        "la pregunta debe ir antes de guardar"


def test_la_ventana_deja_elegida_la_propuesta_y_bloquea_la_parte_de_abajo():
    assert "mm-prop" in MODAL_JS and "mm-prop" in VENTANAS_CSS
    assert "Cambio propuesto" in MODAL_JS
    assert "_mmAplicarBloqueoRevision" in MODAL_JS and "_mmQuitarBloqueoRevision" in MODAL_JS
    assert "opciones.filter(o => CAMINOS[o])" in MODAL_JS, "los caminos salen de las opciones de la regla"
    assert "m.dudoso" in MODAL_JS, "con cantidad impar de marcas no se propone nada"


def test_el_nombre_de_la_persona_se_ve_completo_en_la_ventana():
    assert "#modal-marcacion-manual .mm-datos > div:first-child { grid-column: 1 / -1; }" in VENTANAS_CSS


# ── Los textos llegan intactos al navegador (el servidor minifica con rjsmin) ───

def test_los_textos_de_la_grilla_sobreviven_al_minificador():
    rjsmin = pytest.importorskip("rjsmin")
    m = rjsmin.jsmin(GRILLA_JS)
    for frase in (
        " día por revisar", " días por revisar", "regla de marcaciones", "regla ",
        "Mientras queden días por revisar, el cierre del tramo de su área está bloqueado",
        " corregido · el día se volvió a calcular", "Día por revisar: ",
        ". Una regla de marcaciones dejó este día en revisión.", "Días por revisar de ", "Revisar ",
        "El sistema propone cambiarla a ", "turno ",
    ):
        assert frase in m, f"el minificador rompe el texto: {frase!r}"


def test_los_textos_de_la_ventana_sobreviven_al_minificador():
    rjsmin = pytest.importorskip("rjsmin")
    m = rjsmin.jsmin(MODAL_JS)
    for frase in (
        "La marca de las <b>", "</b> pasa de <b>", "</b> a <b>", "<br>Al presionar «",
        "» se guarda y el día se vuelve a calcular.", "Con «No» no se guarda nada.",
        "No cambió el tipo de ninguna marca.", "¿Volver a calcular el día?",
        "Este día tiene <strong>todas sus marcas del reloj</strong>: no hace falta agregar marcas.",
        "Bloqueado: este día no necesita marcas nuevas. Solo si de verdad falta una marca, presione ",
        "el sistema propone que la marca de las <strong>", "</strong> (en rojo). Revísela y presione «",
        "el sistema propone cambiar ", " marcas (en rojo). Revíselas y presione «",
        "Guardar el cambio de tipo", "Guardar la SALIDA", "Guardar la ENTRADA", "¿Qué pasó este día?",
        "Se le olvidó marcar la SALIDA", "Marcó ENTRADA en vez de SALIDA (o al revés)", "Las marcas están bien así",
        " y <strong>sin horas</strong> hasta corregir sus marcas.", "Bloqueado hasta elegir arriba qué pasó este día.",
    ):
        assert frase in m, f"el minificador rompe el texto: {frase!r}"
