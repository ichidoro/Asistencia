"""Las jornadas extra de monto fijo en el informe de cierre (pedido de la persona dueña, 23-11-2026): una jornada
especial validada «como jornada extra» se paga con un monto fijo por jornada que RR.HH. tramita aparte, y sus horas no
van en las horas extra; antes el PDF y el preinforme no la mostraban. Ahora salen la columna «Jornadas extra» (en «A
cargar»), el recuadro del resumen, la sección con los días de cada persona y la línea en el resumen del paso 5 y del
correo. Las jornadas especiales validadas como horas extra y los +2 ya van en las horas extra: no se muestran aparte.
Datos inventados; sin nombres de personas.
"""
from datetime import date

from backend.services import informe_cierre_pdf as icp


def _etiqueta(di, es_bolsa):
    return ({'OK': 'OK', 'EXTRA': 'EXT', 'LIBRE': 'LIB'}.get(di.get('estado'), ''), None, False)


def test_cuenta_las_jornadas_extra_con_sus_dias():
    dias = {'2026-10-03': {'estado': 'EXTRA'}, '2026-10-04': {'estado': 'LIBRE'}, '2026-10-05': {'estado': 'OK'},
            '2026-10-10': {'estado': 'DÍA LIBRE Y JORNADA EXTRA'}, '2026-10-11': {'estado': 'JORNADA_ESPECIAL'}}
    r = icp.dias_persona(dias, [date(2026, 10, d) for d in (3, 4, 5, 10, 11)], False, _etiqueta, [])
    assert r['jextra'] == 2 and r['jextra_dias'] == ['03-10', '10-10']       # la validada como horas extra no cuenta


def _inf(jx):
    p = {'emp_id': 1, 'rut': '1-9', 'nombre': 'PERSONA UNO', 'activo': True, 'tipo': 'CICLO', 'horario': 'H', 'horas': 42.0,
         'n_atr': 0, 'n_sad': 0, 'trab': 20, 'aus': {}, 'per': 0, 'comp': 0, 'ina': 0, 'ano': 0, 'atr': 0, 'sad': 0,
         'col': 0, 'h_per': 0, 'otros': 0, 'total': 0, 'comp_inas': 0, 'cubren': 0, 'descontar': 0, 'he_trab': 0,
         'he_noap': 0, 'he_decidir': 0, 'he_inas': 0, 'pagar': 0, 'bonos': {}, 'bonos_det': {},
         'jextra': jx, 'jextra_dias': ['03-10', '10-10'][:jx]}
    return icp.separar_informes([p])[0]


def test_columna_recuadro_y_resumen():
    inf = _inf(2)
    cols = [c for c in icp.columnas(inf, [], []) if c['titulo'] == 'Jornadas extra']
    assert len(cols) == 1 and cols[0]['grupo'] == 'A cargar' and cols[0]['valor'](inf['personas'][0]) == 2
    assert ('Jornadas extra ', '2', ' · monto fijo', False) in icp.resumen(inf)
    assert any(x['t'] == 'Jornadas extra · monto fijo' and x['v'] == '2' for x in icp.resumen_tipo(inf, [])['cargar'])
    assert icp.render_pdf('AREA', '2026-09-26', '2026-10-25', 'u', inf, [], []).startswith(b'%PDF')
    # sin jornadas extra no aparece nada
    sin = _inf(0)
    assert not [c for c in icp.columnas(sin, [], []) if c['titulo'] == 'Jornadas extra']
    assert not any('Jornadas extra' in str(x) for x in icp.resumen(sin))
