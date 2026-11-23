"""Etapa B2 del plan de bonos (docs/PLAN_BONOS.md): el informe de cierre muestra cuánto pagar por cada bono (pedido de la
persona dueña, 21-11-2026: «poner los valores en el informe de cierre» para que RR.HH. sepa qué pagar).

- PDF: el monto de cada bono por persona, el total por bono y por persona, el total de bonos en el resumen de arriba y
  un detalle con los bonos que no se pagan (causa y días) y los que se pagan en parte.
- Las columnas son los bonos que les corresponden a las personas del informe según las reglas de cada bono (decisión
  del 22-11-2026), no las áreas marcadas en el bono.
- Excel: el monto en vez de SÍ, una columna «Total bonos» y la suma en la fila de totales.
Datos inventados; sin nombres de personas.
"""
import asyncio
from datetime import date
from io import BytesIO

from backend.services import informe_cierre_pdf as icp

EV = {
    'Compromiso': {'aplica': True, 'califica': False, 'monto': 0, 'motivo': 'x',
                   'perdidos': [{'fecha': '2026-10-08', 'causa': 'Inasistencia sin justificar'},
                                {'fecha': '2026-10-15', 'causa': 'Licencia Común'},
                                {'fecha': '2026-10-16', 'causa': 'Licencia Común'}]},
    'Cloro': {'aplica': True, 'califica': True, 'monto': 22727, 'monto_completo': 50000, 'proporcional': True,
              'dias_asignados': 10, 'dias_periodo': 22},
    'Transporte': {'aplica': True, 'califica': True, 'monto': 30000, 'monto_completo': 30000},
    'Retail': {'aplica': False, 'califica': False, 'monto': 0},
}


def test_monto_y_detalle_de_cada_bono_de_la_persona():
    montos, det = icp.bonos_persona(EV)
    assert montos == {'Compromiso': 0, 'Cloro': 22727, 'Transporte': 30000}     # Retail no le corresponde
    assert det['Cloro']['parcial'] == (10, 22) and det['Transporte']['parcial'] is None
    assert icp.pesos(8110000) == '$8.110.000' and icp.pesos(0) == '$0'


def _inf():
    p = {'emp_id': 1, 'rut': '1-9', 'nombre': 'PERSONA UNO', 'activo': True, 'tipo': 'CICLO', 'horario': 'H', 'horas': 42.0,
         'n_atr': 0, 'n_sad': 0, 'trab': 20, 'aus': {}, 'per': 0, 'comp': 0, 'ina': 1, 'ano': 0, 'atr': 0, 'sad': 0,
         'col': 0, 'h_per': 0, 'otros': 0, 'total': 0, 'comp_inas': 0, 'cubren': 0, 'descontar': 0, 'he_trab': 0,
         'he_noap': 0, 'he_decidir': 0, 'he_inas': 0, 'pagar': 0}
    q = dict(p, emp_id=2, nombre='PERSONA DOS', ina=0)
    p['bonos'], p['bonos_det'] = icp.bonos_persona(EV)
    q['bonos'], q['bonos_det'] = icp.bonos_persona({'Transporte': EV['Transporte'], 'Compromiso': {
        'aplica': True, 'califica': True, 'monto': 70000, 'monto_completo': 70000}})
    return icp.separar_informes([p, q])[0]


def test_columnas_de_bonos_en_pesos_con_su_total():
    inf = _inf()
    cols = [c for c in icp.columnas(inf, [], ['Compromiso', 'Transporte', 'Operador Linea', 'Cloro']) if c['grupo'] == 'Bonos']
    assert [c['titulo'] for c in cols] == ['Compromiso', 'Transporte', 'Cloro', 'Total']   # nadie tiene Operador Linea
    total = cols[-1]
    assert {p['nombre']: total['valor'](p) for p in inf['personas']} == {'PERSONA UNO': 52727, 'PERSONA DOS': 100000}


def test_resumen_de_arriba_suma_los_bonos_a_pagar():
    r = icp.resumen(_inf())
    assert ('Bonos a pagar ', '$152.727', '', False) in r


def test_detalle_de_bonos_no_pagados_y_en_parte():
    d = icp.detalle_bonos(_inf())
    assert d['no_pagados'] == ['<b>PERSONA UNO</b>: Compromiso. Inasistencia sin justificar el 08-10; '
                               'Licencia Común el 15-10 y 16-10.']
    assert d['en_parte'] == ['<b>PERSONA UNO</b>: Cloro $22.727 de $50.000, por 10 de 22 días de turno del período.']


def test_pdf_con_bonos_se_dibuja():
    pdf = icp.render_pdf('AREA DE PRUEBA', '2026-09-26', '2026-10-25', 'usuario', _inf(), [], ['Compromiso', 'Transporte', 'Cloro'])
    assert pdf.startswith(b'%PDF') and len(pdf) > 2000


def test_el_informe_toma_todos_los_bonos_activos_no_las_areas_marcadas():
    from pathlib import Path
    fuente = (Path(__file__).resolve().parents[1] / 'services' / 'informe_cierre_pdf.py').read_text(encoding='utf-8')
    # todos los bonos en pesos activos (el beneficio de 4 Productos no sale en el informe, etapa B3d)
    assert "FROM bonos WHERE activo = 1 AND COALESCE(tipo, 'pesos') <> 'beneficio' ORDER BY id" in fuente and 'FROM area_bonos' not in fuente


def test_excel_muestra_el_monto_y_el_total_de_bonos():
    from openpyxl import load_workbook
    from backend.services.report_service import ReportService
    fila = {'emp_id': 1, 'nombre': 'PERSONA UNO', 'rut': '1-9', 'activo': 'SÍ', 'esBolsa': False, 'he_bruto': 0,
            'he_apr': 0, 'he_rec': 0, 'he_pend': 0, 'he_mas2': 0, 'd_tot': 0, 'min_col': 0, 'min_per': 0, 'min_atr': 0,
            'min_sad': 0, 'cnt_atr': 0, 'cnt_sad': 0, 'cnt_inas': 0, 'cnt_esp': 0, 'cnt_per': 0, 'tot_incidencias': 0,
            'cnt_efectivos': 0, 'saldo': 0, 'libro': {}, 'metaMin': 0, 'acumBolsa': 0, 'saldoMeta': 0, 'bonos': EV}

    class _Repo:
        class db:
            @staticmethod
            async def fetch_one(*a, **k):
                return None

    class _Svc:
        repository = _Repo()

    rs = ReportService(_Svc())

    async def _calc(md, rd):
        return {'filas': [fila], 'hay_bolsa': False, 'lista_bonos': ['Cloro', 'Compromiso', 'Transporte']}
    rs._calcular_filas = _calc
    md = {'empleados': [{'id': 1, 'nombre': 'UNO', 'apellido_paterno': 'PERSONA', 'tipo_programacion': 'CICLO'}],
          'matrix': {}, 'feriados': []}
    libro = asyncio.run(rs._generate_excel_workbook(md, [date(2026, 10, 1)], 'AREA'))
    ws = load_workbook(BytesIO(libro.getvalue())).active
    filas = [[c.value for c in r] for r in ws.iter_rows()]
    cab = next(r for r in filas if 'Total bonos' in r)
    i = {t: cab.index(t) for t in ('Cloro', 'Compromiso', 'Transporte', 'Total bonos')}
    persona = next(r for r in filas if 'PERSONA UNO' in r)
    assert [persona[i[t]] for t in ('Cloro', 'Compromiso', 'Transporte', 'Total bonos')] == [22727, 'NO', 30000, 52727]
    totales = next(r for r in filas if 'TOTALES' in r)
    assert totales[i['Total bonos']] == 52727 and totales[i['Cloro']] == 22727
