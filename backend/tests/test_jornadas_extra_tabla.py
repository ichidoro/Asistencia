"""Jornadas extra (monto fijo) del informe de cierre como tabla (dueño, 23-11-2026: la lista era poco práctica).

Una fila por persona y una columna por cada fecha con jornada extra (fecha completa con el año y día de la semana); en la
celda, las horas de esa jornada. «FERIADO» o «DÍA LIBRE» van escritos sobre la fecha, en el encabezado, no como letras en
las celdas. Al final, jornadas y horas de cada persona, y una fila de total. Datos inventados; sin nombres de personas.
"""
import reportlab.platypus

from backend.services import informe_cierre_pdf as icp
from backend.tests.test_bajas_del_periodo import _persona

FI, FF = '2026-09-26', '2026-10-25'


def _con_jx(i, fechas):
    p = _persona(i)
    p.update(jextra=len(fechas), jextra_dias=[f[0][8:] + '-' + f[0][5:7] for f in fechas], jextra_fechas=fechas)
    return p


def test_tabla_con_una_columna_por_fecha(monkeypatch):
    tablas = []

    class Tabla(reportlab.platypus.Table):
        def __init__(self, data, *a, **k):
            tablas.append(data)
            super().__init__(data, *a, **k)

    monkeypatch.setattr(reportlab.platypus, 'Table', Tabla)
    ps = [_con_jx(0, [('2026-10-03', 'EXTRA', 8 * 3600), ('2026-10-12', 'FERIADO Y JORNADA EXTRA', 6 * 3600)]),
          _con_jx(1, [('2026-09-26', 'DÍA LIBRE Y JORNADA EXTRA', 8 * 3600 + 1800)]),
          _persona(2)]
    inf = icp.separar_informes(ps)[0]
    assert icp.render_pdf('PRUEBA', FI, FF, 'u', inf, [], [], preinforme=True).startswith(b'%PDF')
    texto = lambda c: c.text if hasattr(c, 'text') else str(c)
    t = next(d for d in tablas if texto(d[0][-1]) == 'HORAS')
    cab = [texto(c) for c in t[0]]
    assert cab[:2] == ['RUT', 'NOMBRE'] and cab[-2:] == ['JORNADAS', 'HORAS']
    # una columna por fecha, en orden, con el año; feriado y día libre escritos en el encabezado
    assert 'DÍA LIBRE' in cab[2] and '26-09-2026' in cab[2]
    assert 'SÁB' in cab[3] and '03-10-2026' in cab[3] and 'FERIADO' not in cab[3]
    assert 'FERIADO' in cab[4] and '12-10-2026' in cab[4]
    # solo quienes tienen jornadas extra, con las horas en su fecha y sin letras en las celdas
    nombres = [texto(f[1]) for f in t[1:-1]]
    assert nombres == ['PERSONA INVENTADA 0', 'PERSONA INVENTADA 1']
    assert t[1][2:] == ['', '08:00:00', '06:00:00', '2', '14:00:00']
    assert t[2][2:] == ['08:30:00', '', '', '1', '08:30:00']
    assert t[-1][0] == 'Total · 2 personas' and t[-1][-2:] == ['3', '22:30:00']
