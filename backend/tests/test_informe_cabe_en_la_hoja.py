"""El informe de cierre y el preinforme caben en la hoja (A4 horizontal) aunque el área tenga muchas columnas (23-11-2026:
en Producción, con los montos de bonos y las jornadas extra, la tabla y los recuadros se salían de la hoja y se cortaban
el RUT, los bonos y el total). La tabla se ajusta de menos a más: títulos en dos líneas, letra más chica, nombres largos
en dos líneas y menos relleno; los recuadros de arriba pasan a otra fila. Datos inventados; sin nombres de personas.
"""
from backend.services import informe_cierre_pdf as icp

BONOS = ['Compromiso', 'Transporte', 'Operador Linea', 'Retail', 'Cloro', 'Supervisor']


def _ancha(n=47):
    ps = []
    for i in range(n):
        ps.append({'emp_id': i, 'rut': '12.345.678-9', 'nombre': f'APELLIDOLARGO DEPRUEBA NOMBRE SEGUNDONOMBRE {i}', 'activo': i % 9,
                   'tipo': 'CICLO', 'horario': 'Produccion', 'horas': 42.0, 'n_atr': 14, 'n_sad': 7, 'trab': 19,
                   'aus': {'VAC': 1, 'CUMP': 1, 'LICC': 1}, 'per': 1, 'comp': 1, 'ina': 1, 'ano': 0,
                   'atr': 26000, 'sad': 12000, 'col': 3000, 'h_per': 5000, 'otros': 900, 'total': 46900, 'comp_inas': 3000,
                   'cubren': 30000, 'descontar': 13900, 'he_trab': 71000, 'he_mas2': 9000, 'he_noap': 3500, 'he_decidir': 0,
                   'he_inas': 2000, 'pagar': 35500, 'jextra': 4, 'jextra_dias': ['03-11', '04-11', '17-11', '18-11'],
                   'bonos': {b: 100000 for b in BONOS},
                   'bonos_det': {b: {'califica': True, 'monto': 100000, 'completo': 100000, 'parcial': None, 'asistidos': None, 'perdidos': []} for b in BONOS}})
    return icp.separar_informes(ps)[0]


def test_la_tabla_cabe_en_la_hoja(monkeypatch):
    avisos = []
    monkeypatch.setattr(icp.logger, 'warning', lambda m, *a, **k: avisos.append(m))
    pdf = icp.render_pdf('PRODUCCION', '2026-10-26', '2026-11-25', 'u', _ancha(), [], BONOS, preinforme=True)
    assert pdf.startswith(b'%PDF')
    assert not [a for a in avisos if 'no cabe en la hoja' in a]
