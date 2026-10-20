# -*- coding: utf-8 -*-
"""Guardia de la sección 7 de REGLAS_ASISTENCIA.md (Reglas de marcaciones).

Vigila que el código y el documento no se separen:
  1. El documento describe el MECANISMO completo (valores, dónde no entra,
     encendido gradual, revisión, ajustes). Las reglas del dueño, secuencia por
     secuencia, NO se escriben aquí: viven en la tabla `reglas_marcas` y la
     pestaña siempre muestra su estado real, con quién y cuándo las cambió.
  2. El marcador de revisión tiene UNA sola fuente (reglas_marcas_def).
  3. No vuelven números fijos a las zonas que esta obra parametrizó.
  4. El cierre sigue bloqueándose con días por revisar.
"""
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

RAIZ = Path(__file__).resolve().parents[2]

from backend.services import reglas_marcas_def as DEF  # noqa: E402


def _leer(rel):
    return (RAIZ / rel).read_text(encoding="utf-8")


DOC = _leer("backend/docs/REGLAS_ASISTENCIA.md")
MOTOR = _leer("backend/services/quantum_matrix_engine.py")
REPO = _leer("backend/repositories/reglas_marcas.py")
CIERRE = _leer("backend/services/cierre_service.py")
MATRIZ = _leer("backend/services/asistencia_service.py")
MODAL_JS = _leer("frontend/js/marcaciones_manuales.js")


# ── 1. El documento describe el mecanismo completo ───────────────────────────

def test_el_documento_tiene_la_seccion_de_reglas_de_marcaciones():
    assert "## 7. Reglas de marcaciones configurables" in DOC


def test_el_documento_nombra_cada_valor_posible_de_una_regla():
    for valor in DEF.LECTURAS + DEF.COLACIONES + DEF.ACCIONES + DEF.OPCIONES_REVISION:
        assert f"`{valor}`" in DOC, f"el documento no nombra el valor {valor}"


def test_el_documento_dice_lo_esencial_del_mecanismo():
    for frase in (
        "activa = 0",                      # nacen apagadas: desplegar no cambia nada
        "Bolsa Flexible queda sin reglas",  # dónde nunca entra
        "el día en curso",
        "períodos cerrados",
        "Correr esta regla",
        "Apagar esta regla",
        "Una regla encendida no se edita",
        "firma",                            # la confirmación vale mientras las marcas no cambien
        "reglas_marcas_rebote_segundos",
        "reglas_marcas_colacion_min_minutos",
        DEF.MARCA_REVISION_REGLA,           # el marcador, escrito tal cual
    ):
        assert frase in DOC, f"el documento perdió la frase clave: {frase}"


# ── 2. El marcador de revisión tiene una sola fuente ─────────────────────────

def test_el_marcador_vive_solo_en_reglas_marcas_def():
    literal = "'Revisar las marcas (regla '"
    assert literal in _leer("backend/services/reglas_marcas_def.py")
    for rel in ("backend/services/quantum_matrix_engine.py",
                "backend/repositories/reglas_marcas.py",
                "backend/services/cierre_service.py",
                "backend/services/asistencia_service.py"):
        assert literal not in _leer(rel), f"{rel} escribe el marcador a mano en vez de importarlo"
    assert "MARCA_REVISION_REGLA" in MOTOR and "MARCA_REVISION_REGLA" in REPO


# ── 3. Sin números fijos nuevos en lo parametrizado ──────────────────────────

def test_el_rebote_del_motor_sale_del_ajuste_y_no_de_un_180_suelto():
    # Los 180.0 permitidos en el motor son exactamente estos cuatro, ninguno más:
    # el respaldo dentro de _rebote_defecto, los dos valores por defecto de la
    # firma de bounce_seconds (los llamadores siempre pasan el real) y la distancia
    # de fase de 180 minutos de los turnos nocturnos (otro significado). Si este
    # conteo cambia, alguien metió o sacó un número fijo: revisar antes de subir.
    assert MOTOR.count("180.0") == 4, "cambió un 180.0 en el motor: revisar _rebote_defecto y esta lista"
    assert "_rebote_defecto(tipo_prog)" in MOTOR
    assert "REGLAS_MARCAS_REBOTE" in MOTOR


def test_la_ventana_de_colacion_del_cuadro_ya_no_esta_escrita_en_la_pantalla():
    assert "let MARCAS_COLACION_MIN" in MODAL_JS, "la ventana debe poder actualizarse desde el servidor"
    assert "entre 20 y 150 minutos" not in MODAL_JS, "la ventana volvió a quedar escrita en el texto de la pantalla"
    assert "ventana_colacion" in MODAL_JS
    for clave in (REPO_CLAVES := ("reglas_marcas_colacion_min_minutos", "reglas_marcas_colacion_max_minutos")):
        assert clave in REPO, f"falta el ajuste {clave}"


# ── 4. El cierre bloquea con días por revisar ────────────────────────────────

def test_el_cierre_bloquea_y_lo_dice():
    assert "pendientes_para_cierre" in CIERRE
    inicio = CIERRE.index("puede_cerrar = (")
    bloque = CIERRE[inicio:CIERRE.index("\n        )", inicio)]
    assert "len(por_revisar) == 0" in bloque, "puede_cerrar ya no exige 0 días por revisar"
    assert "días por revisar" in CIERRE and "No se puede cerrar el periodo" in CIERRE
    assert "dias_por_revisar" in CIERRE


def test_la_grilla_marca_los_dias_en_revision():
    assert "revision_marcas" in MATRIZ
    assert "firma_marcas" in MATRIZ


def test_la_grilla_tiene_el_boton_por_revisar():
    grilla_js = _leer("frontend/js/marcaciones_ui.js")
    assert "btn-por-revisar" in grilla_js
    assert "reglas-marcas/por-revisar/" in grilla_js
    assert "Por revisar (" in DOC, "el documento perdió el botón «Por revisar (N)» de la grilla"


# ── 5. La tabla de confirmaciones y su firma existen ─────────────────────────

def test_confirmaciones_con_firma_en_el_repositorio():
    assert "CREATE TABLE IF NOT EXISTS revisiones_marcas" in REPO
    assert "UNIQUE (empleado_id, fecha, firma)" in REPO
    assert "secuencia_en_revision" in REPO and "firma_marcas" in REPO
