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


def test_ninguna_pantalla_lee_la_llave_de_sesion_muerta():
    """La sesión del frontend vive en localStorage bajo 'access_token'
    (AuthService.TOKEN_KEY). Una llave 'token' no la escribe nadie: leerla da
    null, y las llamadas solo funcionaban porque el interceptor global de
    auth.js corrige el Authorization de cada fetch. Nadie debe volver a
    depender de esa casualidad."""
    import pathlib
    import re
    raiz = pathlib.Path(__file__).resolve().parents[2] / "frontend"
    patron = re.compile(r"getItem\((['\"])token\1\)")
    malos = sorted({f.name for f in list(raiz.rglob("*.js")) + list(raiz.glob("*.html"))
                    if patron.search(f.read_text(encoding="utf-8", errors="ignore"))})
    assert not malos, f"Vuelven a leer la llave muerta 'token': {malos} (use 'access_token')"


def test_el_ensayo_no_guarda_y_viaja_en_contexto():
    """El «Ensayar con los días reales» del asistente calcula con el motor de verdad
    pero sin escribir (collect_only) y la regla propuesta viaja en una variable de
    contexto: ninguna otra tarea del servidor la ve."""
    assert "REGLAS_MARCAS_ENSAYO" in MOTOR and "ContextVar" in MOTOR
    corridas = _leer("backend/services/reglas_marcas_corridas.py")
    assert "collect_only=True" in corridas, "el ensayo debe calcular sin escribir en la base"
    assert "REGLAS_MARCAS_ENSAYO.set" in corridas and "REGLAS_MARCAS_ENSAYO.reset" in corridas
    router = _leer("backend/routers/reglas_marcas.py")
    assert "/ensayo/" in router and "dias-ejemplo" in router
    pestana_js = _leer("frontend/js/reglas_marcas_ui.js")
    assert "rm-ensayar" in pestana_js, "la pestaña perdió el botón de ensayo"
    assert "rmx-paso" in pestana_js, "la pestaña perdió el asistente por pasos"
    assert "No aplica: sin cálculo no hay colación que descontar" in pestana_js, \
        "la pestaña perdió el aviso de que la colación no aplica cuando el día no se calcula"
    assert "collect_only" in DOC and "REGLAS_MARCAS_ENSAYO" in DOC, "el documento perdió el ensayo"


def test_las_reglas_y_sus_notas_no_estan_escritas_en_el_codigo():
    """Orden del dueño (23-10-2026): las reglas se crean y configuran desde la
    interfaz; el código no trae una lista de secuencias ni de notas."""
    assert not hasattr(DEF, "REGLAS_SEMILLA") and not hasattr(DEF, "NOTAS_FRECUENTES")
    assert "INSERT OR IGNORE INTO reglas_marcas" not in REPO, "el repositorio volvió a sembrar reglas"
    assert "filas_semilla" not in REPO
    assert "notas_frecuentes" not in _leer("backend/routers/reglas_marcas.py")
    assert "notas_frecuentes" not in _leer("frontend/js/reglas_marcas_ui.js")


def test_ninguna_pantalla_ni_anotacion_usa_las_iniciales():
    """ENTRADA y SALIDA se escriben siempre con la palabra completa."""
    import pathlib
    raiz = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "js"
    malos = sorted(f.name for f in raiz.glob("*.js")
                   if ".split('').join(' · ')" in f.read_text(encoding="utf-8", errors="ignore"))
    assert not malos, f"vuelven las iniciales unidas con puntos en: {malos}"
    assert "secuencia_en_palabras(secuencia_dia)" in MOTOR, "el motor anota las reglas sin la palabra completa"
    assert "' · '.join(secuencia_dia)" not in MOTOR


def test_lo_configurable_no_vuelve_a_quedar_escrito_en_el_motor():
    for clave in ("reglas_marcas_repetidas_minutos", "reglas_marcas_colacion_referencia_minutos",
                  "reglas_marcas_fuera_ciclo_minutos"):
        assert clave in MOTOR, f"el motor ya no lee el ajuste {clave}"
        assert clave in REPO, f"la pestaña ya no ofrece el ajuste {clave}"
    assert ">= 1200.0" not in MOTOR, "volvieron los 20 minutos escritos para las marcas repetidas"
    assert "else 60.0" not in MOTOR, "volvió la colación de referencia escrita en el motor"
    assert "avisa_fuera_de_ciclo" in MOTOR and "avisa_fuera_de_ciclo" in REPO


def test_la_tolerancia_de_exceso_se_configura_en_cada_horario():
    horarios_js = _leer("frontend/js/horarios.js")
    assert "toleranciaExcesoColacion" in horarios_js and "tolerancia_exceso_colacion_minutos" in horarios_js


def test_los_textos_del_asistente_sobreviven_al_minificador():
    import pytest
    rjsmin = pytest.importorskip("rjsmin")
    m = rjsmin.jsmin(_leer("frontend/js/reglas_marcas_ui.js"))
    for frase in (
        "¿El sistema puede calcular estos días solo?",
        "Lo mayor entre la del horario y la pausa medida",
        "Además, avisar si las marcas no calzan con ningún ciclo del horario",
        "Día libre o feriado (jornada especial):",
        "días así en el tramo abierto",
        " con marcas del reloj, más los que tengan marcas manuales). Nunca el día en curso ni períodos cerrados.",
        "; se descuenta lo mayor entre la colación del horario y la pausa medida (bajo el mínimo, solo la pausa)",
        "La primera es la ENTRADA y la última la SALIDA",
    ):
        assert frase in m, f"el minificador rompe el texto: {frase!r}"


def test_la_meta_de_bolsa_se_prorratea_en_todas_las_replicas():
    """La meta de Bolsa Flexible de una vigencia parcial (ingreso/egreso a mitad
    del tramo) se calcula UNA vez en la matriz (bolsa_prorrateo) y la aplican las
    cuatro réplicas: la grilla y la vista individual (marcaciones_ui.js), el
    Excel (report_service) y el resumen de cierre (cierre_service). Además la
    pantalla avisa cuando no se alcanzan los 21 días del art. 25 bis."""
    assert "bolsa_prorrateo" in MATRIZ and "calcular_prorrateo_bolsa" in MATRIZ
    assert "aplicar_prorrateo" in CIERRE and "fecha_en_vigencia" in CIERRE
    excel = _leer("backend/services/report_service.py")
    assert "aplicar_prorrateo" in excel and "fecha_en_vigencia" in excel
    grilla_js = _leer("frontend/js/marcaciones_ui.js")
    assert grilla_js.count("bolsa_prorrateo") >= 2, \
        "la grilla o la vista individual perdió el prorrateo de la meta"
    assert "aviso_21_dias" in grilla_js and "art. 25 bis" in grilla_js, \
        "la pantalla perdió el aviso de los 21 días de la ley"


def test_los_textos_del_prorrateo_sobreviven_al_minificador():
    """El servidor minifica el JS al servirlo (static_minify + rjsmin) y rjsmin
    come los espacios del texto de una plantilla `...` anidada dentro de ${} de
    otra plantilla (así se descubrió «114h:vigencia de 19de 30días» en pantalla).
    Los textos del prorrateo van con comillas y concatenación; esta guardia corre
    el minificador real y comprueba que llegan intactos al navegador."""
    import pytest
    rjsmin = pytest.importorskip("rjsmin")
    m = rjsmin.jsmin(_leer("frontend/js/marcaciones_ui.js"))
    for frase in (
        "Balance de la bolsa; meta ajustada a ",
        " h: vigencia de ",
        "Meta ajustada por ",
        ": proporcional a ",
        " días del tramo",
        "La ley (art. 25 bis del Código del Trabajo) exige repartir las 180 horas en al menos ",
        " días; este período solo le da ",
        " días a esta persona. Es un aviso: no bloquea nada.",
        "Meta original: ",
        " | Descuento por ",
        " día(s) justificado(s)",
        "Período con solo ",
        " días (la ley pide ",
    ):
        assert frase in m, f"el minificador rompe el texto: {frase!r}"


# ── 5. La tabla de confirmaciones y su firma existen ─────────────────────────

def test_confirmaciones_con_firma_en_el_repositorio():
    assert "CREATE TABLE IF NOT EXISTS revisiones_marcas" in REPO
    assert "UNIQUE (empleado_id, fecha, firma)" in REPO
    assert "secuencia_en_revision" in REPO and "firma_marcas" in REPO
