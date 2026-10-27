# -*- coding: utf-8 -*-
"""Reglas de marcaciones: definiciones y validación, sin base de datos.

Las reglas NO vienen escritas en el código (se crean y configuran desde la
pantalla); aquí se prueba la lógica: cómo se nombran las marcas, la validación
y el marcador de revisión.
"""
import os
os.environ.setdefault("SECRET_KEY", "test")

from backend.services import reglas_marcas_def as DEF  # noqa: E402
from backend.services.reglas_marcas_def import (  # noqa: E402
    ACCIONES, COLACIONES, LECTURAS, OPCIONES_REVISION,
    grupo_de_secuencia, secuencia_en_palabras, secuencia_en_revision, validar_regla,
)


def test_el_codigo_no_trae_reglas_ni_notas_escritas():
    """Orden del dueño (23-10-2026): las reglas y sus notas se configuran desde la
    interfaz; el código solo aporta la lógica."""
    for nombre in ("REGLAS_SEMILLA", "NOTAS_FRECUENTES", "filas_semilla"):
        assert not hasattr(DEF, nombre), f"volvió a aparecer {nombre} en el código"


def test_las_marcas_se_nombran_con_la_palabra_completa():
    assert secuencia_en_palabras("ES") == "ENTRADA · SALIDA"
    assert secuencia_en_palabras("ESES") == "ENTRADA · SALIDA · ENTRADA · SALIDA"
    assert secuencia_en_palabras("S", separador=" ") == "SALIDA"
    assert secuencia_en_palabras("") == ""


def test_grupos_de_pantalla():
    assert grupo_de_secuencia('E') == 'Una sola marca'
    assert grupo_de_secuencia('ES') == 'Bien marcadas'
    assert grupo_de_secuencia('ESESES') == 'Bien marcadas'
    assert grupo_de_secuencia('EE') == 'Se repite un tipo'
    assert grupo_de_secuencia('ESSS') == 'Se repite un tipo'
    assert grupo_de_secuencia('ESE') == 'Falta una marca'
    assert grupo_de_secuencia('SES') == 'Falta una marca'


def _base(**kw):
    d = dict(secuencia='ESES', lectura='RELOJ', colacion='MEDIDA',
             accion='CALCULA', opciones_revision=[])
    d.update(kw)
    return d


def test_validacion_rechaza_secuencias_malas_y_lo_dice_con_palabras():
    assert validar_regla(_base(secuencia='')) != ''
    assert validar_regla(_base(secuencia='EXS')) != ''
    assert validar_regla(_base(secuencia='E' * 13)) != ''
    motivo = validar_regla(_base(secuencia='EXS'))
    assert 'ENTRADA' in motivo and 'SALIDA' in motivo and 'E y S' not in motivo


def test_validacion_rechaza_valores_desconocidos():
    assert validar_regla(_base(lectura='OTRA')) != ''
    assert validar_regla(_base(colacion='OTRA')) != ''
    assert validar_regla(_base(accion='OTRA')) != ''
    assert validar_regla(_base(accion='CALCULA_Y_REVISA', opciones_revision=['X'])) != ''


def test_validacion_combinaciones_coherentes():
    # no leer → solo revisión
    assert validar_regla(_base(lectura='NINGUNA', accion='CALCULA')) != ''
    assert validar_regla(_base(lectura='NINGUNA', accion='SOLO_REVISA',
                               opciones_revision=['RECLASIFICAR'])) == ''
    # calcula sin aviso → sin opciones
    assert validar_regla(_base(opciones_revision=['CONFIRMAR'])) != ''
    # va a revisión → al menos una opción
    assert validar_regla(_base(accion='CALCULA_Y_REVISA', opciones_revision=[])) != ''
    # una sola marca → no se puede leer
    assert validar_regla(_base(secuencia='E', lectura='EXTREMOS',
                               accion='SOLO_REVISA', opciones_revision=['AGREGAR_SALIDA'])) != ''
    assert validar_regla(_base(secuencia='E', lectura='NINGUNA', accion='SOLO_REVISA',
                               opciones_revision=['AGREGAR_SALIDA'])) == ''
    # opciones repetidas
    assert validar_regla(_base(accion='CALCULA_Y_REVISA',
                               opciones_revision=['CONFIRMAR', 'CONFIRMAR'])) != ''


def test_marcador_de_revision_se_lee_con_palabras_y_con_letras():
    nuevo = ("Regla de marcaciones (SALIDA · SALIDA · ENTRADA · SALIDA): se leyó con la primera marca como ENTRADA "
             "y la última como SALIDA. Revisar las marcas (regla SALIDA · SALIDA · ENTRADA · SALIDA). ")
    assert secuencia_en_revision(nuevo) == 'SSES'
    antiguo = "Revisar las marcas (regla S · S · E · S). "          # días anotados antes del cambio
    assert secuencia_en_revision(antiguo) == 'SSES'
    assert secuencia_en_revision('Revisar las marcas (regla ENTRADA). ') == 'E'
    assert secuencia_en_revision('Revisar las marcas (regla E). ') == 'E'
    assert secuencia_en_revision('Salidas seguidas: se tomó la última. ') == ''
    assert secuencia_en_revision(None) == ''


def test_firma_de_marcas_estable_y_ordenada():
    from backend.services.reglas_marcas_def import firma_marcas
    assert firma_marcas([7003, 7001, 7002]) == '7001,7002,7003'
    assert firma_marcas('[7003, 7001]') == '7001,7003'      # como viene de asistencias (texto JSON)
    assert firma_marcas('[]') == '' and firma_marcas(None) == ''
    assert firma_marcas('no-json') == ''


def test_la_regla_creada_desde_la_bandeja_nace_valida():
    # Mismos valores por defecto que usa crear_regla (repositorio): deben pasar la validación
    for sec in ('ESSEES', 'E', 'S'):
        nueva = {'secuencia': sec, 'lectura': 'EXTREMOS', 'colacion': 'TURNO',
                 'accion': 'CALCULA_Y_REVISA', 'opciones_revision': ['RECLASIFICAR', 'CONFIRMAR']}
        if len(sec) == 1:
            nueva.update(lectura='NINGUNA', accion='SOLO_REVISA',
                         opciones_revision=['AGREGAR_SALIDA' if sec == 'E' else 'AGREGAR_ENTRADA'])
        assert validar_regla(nueva) == '', sec


def test_catalogos_sin_sorpresas():
    assert LECTURAS == ('RELOJ', 'EXTREMOS', 'NINGUNA')
    assert COLACIONES == ('TURNO', 'MEDIDA', 'NINGUNA')
    assert ACCIONES == ('CALCULA', 'CALCULA_Y_REVISA', 'SOLO_REVISA')
    assert set(OPCIONES_REVISION) == {'AGREGAR_ENTRADA', 'AGREGAR_SALIDA', 'RECLASIFICAR', 'CONFIRMAR'}
