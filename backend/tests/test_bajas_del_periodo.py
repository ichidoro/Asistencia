"""Bajas del período aparte de la dotación (propuesta B elegida por la persona dueña, 23-11-2026).

Antes, el informe marcaba «Inactivo» según el estado de hoy: en un período ya pasado salía como inactiva gente que trabajó
todo el período y se fue después, y una renuncia con fecha dentro del período no se marcaba hasta que llegaba el día.
Ahora es baja del período quien tiene su salida decidida (inactiva, «No renovar» o «BAJA: …») con fecha dentro del
período. En el informe y el preinforme van al final de su horario, bajo «Bajas del período», y se cuentan aparte
(«12 en dotación · 2 bajas»); se pagan y descuentan como el resto, así que los totales no cambian.
Datos inventados; sin nombres de personas.
"""
import reportlab.platypus

from backend.services import informe_cierre_pdf as icp
from backend.services.bolsa_prorrateo import baja_del_periodo

FI, FF = '2026-10-26', '2026-11-25'


def test_regla_de_la_baja_del_periodo():
    # renuncia decidida dentro del período, aunque la persona siga activa hasta ese día
    assert baja_del_periodo('2026-11-24', 1, 'BAJA: Renuncia Voluntaria', FI, FF) == '2026-11-24'
    # ya inactiva, salida dentro del período
    assert baja_del_periodo('2026-11-02', 0, 'BAJA: Despido', FI, FF) == '2026-11-02'
    # no renovar dentro del período
    assert baja_del_periodo('2026-11-15', 0, 'NO_RENOVAR', FI, FF) == '2026-11-15'
    # se fue después del período: fue dotación de ese período
    assert baja_del_periodo('2026-10-30', 0, 'BAJA: Renuncia Voluntaria', '2026-09-26', '2026-10-25') is None
    # término de contrato sin decidir: no es baja
    assert baja_del_periodo('2026-11-20', 1, None, FI, FF) is None
    assert baja_del_periodo(None, 1, None, FI, FF) is None
    # el primer y el último día del período cuentan
    assert baja_del_periodo(FI, 0, 'BAJA: Despido', FI, FF) == FI
    assert baja_del_periodo(FF, 1, 'BAJA: Despido', FI, FF) == FF


def _persona(i, baja=None, descontar=0):
    return {'emp_id': i, 'rut': '11.111.111-1', 'nombre': f'PERSONA INVENTADA {i}', 'activo': True, 'baja': baja,
            'tipo': 'CICLO', 'horario': 'Horario de prueba', 'horas': 42.0, 'n_atr': 1 if descontar else 0, 'n_sad': 0,
            'trab': 20, 'aus': {}, 'per': 0, 'comp': 0, 'ina': 0, 'ano': 0, 'dias_aus': {},
            'atr': descontar, 'sad': 0, 'col': 0, 'h_per': 0, 'otros': 0, 'total': descontar, 'comp_inas': 0,
            'cubren': 0, 'descontar': descontar, 'he_trab': 3600, 'he_mas2': 0, 'he_noap': 0, 'he_decidir': 0,
            'he_inas': 0, 'pagar': 3600, 'jextra': 0, 'jextra_dias': [], 'bonos': {}, 'bonos_det': {}}


def _informe():
    # la baja va segunda en la lista (por apellido), para ver que el informe la pasa al final de su horario
    ps = [_persona(0), _persona(1, baja='2026-11-14', descontar=600), _persona(2), _persona(3, baja='2026-11-24')]
    return icp.separar_informes(ps)[0]


def test_conteo_aparte_y_totales_iguales():
    inf = _informe()
    chips = icp.resumen(inf)
    assert chips[0] == ('', '2', ' en dotación', False)
    assert chips[1] == ('', '2', ' bajas del período', False)
    r = icp.resumen_tipo(inf, [])
    assert r['personas'] == 4 and r['bajas'] == 2 and r['texto_personas'] == '2 en dotación · 2 bajas'
    # las bajas se pagan y descuentan como el resto: lo que se carga es lo mismo que sin marcarlas
    sin = icp.separar_informes([dict(p, baja=None) for p in inf['personas']])[0]
    assert icp.resumen_tipo(sin, [])['cargar'] == r['cargar']
    assert icp.resumen_tipo(sin, [])['texto_personas'] == '4 personas'


def test_sin_aviso_de_recuperar_horas_para_quien_se_va():
    inf = _informe()
    avisos = icp.para_coordinar(inf, FF, '2026-11-23')
    assert not [a for a in avisos if 'PERSONA INVENTADA 1' in a]


def test_en_el_pdf_las_bajas_van_al_final_de_su_horario(monkeypatch):
    tablas = []

    class Tabla(reportlab.platypus.Table):
        def __init__(self, data, *a, **k):
            tablas.append(data)
            super().__init__(data, *a, **k)

    monkeypatch.setattr(reportlab.platypus, 'Table', Tabla)
    pdf = icp.render_pdf('PRUEBA', FI, FF, 'u', _informe(), [], [], preinforme=True)
    assert pdf.startswith(b'%PDF')
    principal = max(tablas, key=len)
    texto = lambda c: c.text if hasattr(c, 'text') else str(c)
    col_nombre = [texto(f[1]) for f in principal]
    col_rut = [texto(f[0]) for f in principal]
    i_tit = next(i for i, t in enumerate(col_rut) if t.startswith('Bajas del período · 2 personas'))
    debajo = ' '.join(col_nombre[i_tit + 1:])
    encima = ' '.join(col_nombre[:i_tit])
    assert 'PERSONA INVENTADA 1' in debajo and 'PERSONA INVENTADA 3' in debajo
    assert 'Baja 14-11' in debajo and 'Baja 24-11' in debajo
    assert 'PERSONA INVENTADA 0' in encima and 'PERSONA INVENTADA 2' in encima
    assert 'Inactivo' not in ' '.join(col_nombre)
    assert any('Horario de prueba' in t and '2 en dotación · 2 bajas' in t for t in col_rut)
    assert col_rut[-1] == 'Total · 4 personas (2 en dotación + 2 bajas)'
