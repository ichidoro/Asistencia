# -*- coding: utf-8 -*-
"""Reglas de marcaciones (etapa 1): semilla y validación, sin base de datos.

Comprueba que la semilla codifica exactamente lo que decidió el dueño el
20-10-2026 y que la validación rechaza combinaciones incoherentes.
"""
import os
os.environ.setdefault("SECRET_KEY", "test")

from backend.services.reglas_marcas_def import (  # noqa: E402
    ACCIONES, COLACIONES, LECTURAS, NOTAS_FRECUENTES, OPCIONES_REVISION,
    REGLAS_SEMILLA, filas_semilla, grupo_de_secuencia, validar_regla,
)

SEMILLA = {r['secuencia']: r for r in REGLAS_SEMILLA}

SECUENCIAS_ENCONTRADAS = [
    'ESES', 'ES', 'ESSS', 'EES', 'EEES', 'ESS', 'ESESES', 'SSES', 'ESEE', 'ESE',
    'EE', 'SS', 'SES', 'ESESS', 'SSSS', 'EESES', 'EESS', 'ESEES', 'ESSES', 'EEE',
    'ESESSS', 'SSEE', 'EESSS', 'E', 'SSESES', 'EEEEES', 'ESEEES', 'ESSSS',
]


def test_semilla_cubre_las_28_secuencias_encontradas_mas_la_s_sola():
    assert set(SEMILLA) == set(SECUENCIAS_ENCONTRADAS) | {'S'}
    assert len(REGLAS_SEMILLA) == len(SEMILLA), "hay secuencias repetidas en la semilla"


def test_toda_la_semilla_es_valida_y_nace_apagada():
    for r in REGLAS_SEMILLA:
        assert validar_regla(r) == '', f"{r['secuencia']}: {validar_regla(r)}"
        assert r['activa'] == 0, f"{r['secuencia']} no nace apagada"
        assert r['tipo_horario'] == 'CICLO_INTELIGENTE'


def test_decision_una_sola_marca_es_anomalia_y_se_agrega_la_que_falta():
    e, s = SEMILLA['E'], SEMILLA['S']
    for r in (e, s):
        assert r['lectura'] == 'NINGUNA'
        assert r['accion'] == 'SOLO_REVISA'
    assert e['opciones_revision'] == ['AGREGAR_SALIDA']
    assert s['opciones_revision'] == ['AGREGAR_ENTRADA']


def test_decision_es_toma_extremos_colacion_del_turno_y_calcula():
    r = SEMILLA['ES']
    assert (r['lectura'], r['colacion'], r['accion']) == ('EXTREMOS', 'TURNO', 'CALCULA')
    assert r['opciones_revision'] == []


def test_decision_ee_ss_eee_ssss_revisan_corrigen_y_calculan_con_extremos():
    for sec in ('EE', 'SS', 'EEE', 'SSSS'):
        r = SEMILLA[sec]
        assert r['lectura'] == 'EXTREMOS', sec
        assert r['colacion'] == 'TURNO', sec
        assert r['accion'] == 'CALCULA_Y_REVISA', sec
        assert 'RECLASIFICAR' in r['opciones_revision'], sec


def test_decision_ese_falta_la_salida_final():
    r = SEMILLA['ESE']
    assert r['accion'] == 'CALCULA_Y_REVISA'
    assert 'AGREGAR_SALIDA' in r['opciones_revision']


def test_decision_ses_reclasificar_o_agregar_entrada():
    r = SEMILLA['SES']
    assert r['accion'] == 'CALCULA_Y_REVISA'
    assert 'RECLASIFICAR' in r['opciones_revision']
    assert 'AGREGAR_ENTRADA' in r['opciones_revision']


def test_bien_marcadas_calculan_sin_aviso():
    for sec in ('ES', 'ESES', 'ESESES'):
        assert SEMILLA[sec]['accion'] == 'CALCULA', sec
        assert SEMILLA[sec]['opciones_revision'] == [], sec


def test_tipos_repetidos_aprobados_calculan_con_extremos():
    for sec in ('ESS', 'EES', 'ESSS', 'EEES', 'SSES', 'ESEE'):
        r = SEMILLA[sec]
        assert r['lectura'] == 'EXTREMOS', sec
        assert r['accion'] == 'CALCULA', sec


def test_filas_semilla_serializan_opciones_como_json():
    import json
    filas = filas_semilla()
    assert len(filas) == len(REGLAS_SEMILLA)
    for fila in filas:
        assert len(fila) == 8
        json.loads(fila[5])  # opciones_revision legible


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


def test_validacion_rechaza_secuencias_malas():
    assert validar_regla(_base(secuencia='')) != ''
    assert validar_regla(_base(secuencia='EXS')) != ''
    assert validar_regla(_base(secuencia='E' * 13)) != ''


def test_validacion_rechaza_valores_desconocidos():
    assert validar_regla(_base(lectura='OTRA')) != ''
    assert validar_regla(_base(colacion='OTRA')) != ''
    assert validar_regla(_base(accion='OTRA')) != ''
    assert validar_regla(_base(accion='CALCULA_Y_REVISA', opciones_revision=['X'])) != ''


def test_validacion_combinaciones_coherentes():
    # no leer → solo revisión
    assert validar_regla(_base(lectura='NINGUNA', accion='CALCULA')) != ''
    assert validar_regla(_base(lectura='NINGUNA', accion='SOLO_REVISA',
                               opciones_revision=['CONFIRMAR'])) == ''
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


def test_marcador_de_revision_se_lee_de_las_observaciones():
    from backend.services.reglas_marcas_def import secuencia_en_revision
    obs = ("Regla de marcaciones (S · S · E · S): se leyó con la primera marca como Entrada "
           "y la última como Salida. Revisar las marcas (regla S · S · E · S). ")
    assert secuencia_en_revision(obs) == 'SSES'
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


def test_notas_frecuentes_para_la_lista_desplegable():
    """La nota de la pestaña se elige de esta lista (más «Otra (escribir)»).
    Son solo informativas: no cambian el cálculo y la nota sigue siendo texto."""
    assert len(NOTAS_FRECUENTES) == 8
    assert len(set(NOTAS_FRECUENTES)) == len(NOTAS_FRECUENTES), "hay notas repetidas"
    for n in NOTAS_FRECUENTES:
        assert n.strip() == n and n, "nota vacía o con espacios en los bordes"
        assert len(n) <= 300, "la nota no cabe en el campo (300 letras)"
    assert any('Falta la Entrada' in n for n in NOTAS_FRECUENTES)
    assert any('doble toque' in n for n in NOTAS_FRECUENTES)
