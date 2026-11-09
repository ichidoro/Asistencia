# -*- coding: utf-8 -*-
"""Informe de cierre en PDF para RR.HH. (decisión del dueño, 09-11-2026).

Un informe por área y tipo de horario; balance de horas en HH:MM:SS que cuadra al segundo; sin perdonazos a la
vista; columnas de ausencias y bonos según lo que existe; en la Bolsa lo que falta para la meta son «no usadas»."""
import asyncio
import os
from datetime import date, timedelta

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import informe_cierre_pdf as icp  # noqa: E402
from backend.services.report_service import ReportService  # noqa: E402

JUSTIF = [{'nombre': 'Vacaciones', 'nomenclatura': 'VAC'}, {'nombre': 'Defuncion Hijo', 'nomenclatura': 'DFHI'},
          {'nombre': 'Licencia Comun', 'nomenclatura': 'LICC'}, {'nombre': 'Descanso Operativo', 'nomenclatura': 'DEOP'}]
ETIQUETA = ReportService(None)._format_concepto_cell
RANGO = [date(2026, 5, 1) + timedelta(days=i) for i in range(12)]


def _dias(estados):
    out = {}
    for d, e in zip(RANGO, estados):
        di = dict(e) if isinstance(e, dict) else {'estado': e, 'horas_teoricas': 9.0}
        di.setdefault('horas_teoricas', 9.0)
        out[f'{d.year}-{d.month:02d}-{d.day:02d}'] = di
    return out


def test_jornadas_programadas_menos_ausencias():
    dd = _dias(['OK', 'ATRASO', 'SALIDA_ADELANTADA', 'VACACIONES', 'DEFUNCION HIJO',
                {'estado': 'LICENCIA', 'nomenclatura': 'LICC'}, 'INASISTENCIA', 'ANOMALIA', 'LIBRE', 'FERIADO',
                {'estado': 'JORNADA_ESPECIAL', 'horas_teoricas': 0.0, 'horas_trabajadas': 6.0},
                {'estado': 'DESCANSO_OPERATIVO', 'nomenclatura': 'DEOP'}])
    j = icp.dias_persona(dd, RANGO, False, ETIQUETA, JUSTIF)
    # La justificación sin nomenclatura en el día se reconoce por el nombre de su tipo
    assert j['aus'] == {'VAC': 1, 'DFHI': 1, 'LICC': 1}
    assert (j['trab'], j['ina'], j['ano']) == (3, 1, 1)
    # Libre, feriado, descanso operativo y la jornada especial en día no programado no son días del balance
    assert j['trab'] + sum(j['aus'].values()) + j['ina'] + j['ano'] == 8


def test_balance_de_horas_cuadra_al_segundo_sin_perdonazos():
    # Fracciones de segundo como las guarda el sistema; el cuadre perdonó 2 min (primero salidas)
    libro = {'causas': {'atraso': 32.633, 'salida': 1.5, 'colacion': 52.27, 'permiso': 0.0, 'otra': 0.39},
             'perdon_cuadre': 2.0, 'tolerado': 0.0, 'perdonado': 5.5, 'compensado_inasistencia': 0.0,
             'cubierto': 58.65, 'pendiente': 24.543,
             'he_trabajadas': 60.017, 'he_no_pagadas': 1.0, 'he_por_decidir': 0.0, 'he_usadas_inasistencia': 0.0,
             'he_a_pagar': 0.37}
    h = icp.horas_ciclo(libro)
    assert h['sad'] == 0 and h['atr'] == round((32.633 - 0.5) * 60)        # 1,5 de salida y 0,5 de atraso perdonados
    assert h['atr'] + h['sad'] + h['col'] + h['h_per'] + h['otros'] == h['total']
    assert h['total'] - h['comp_inas'] - h['cubren'] - h['descontar'] == 0
    assert h['he_trab'] - h['he_noap'] - h['he_decidir'] - h['he_inas'] - h['cubren'] - h['pagar'] == 0
    # Lo que se carga queda igual al sistema
    assert (h['descontar'], h['pagar'], h['cubren']) == (round(24.543 * 60), round(0.37 * 60), round(58.65 * 60))
    assert not any('perdon' in k for k in h)


def test_bolsa_no_usadas_no_es_descuento():
    sobre = icp.horas_bolsa({'metaMin': 10800, 'acumBolsa': 11720, 'he_apr': 0})
    bajo = icp.horas_bolsa({'metaMin': 10800, 'acumBolsa': 10000, 'he_apr': 0})
    assert (sobre['pagar'], sobre['no_usadas']) == (920 * 60, 0)
    assert (bajo['pagar'], bajo['no_usadas']) == (0, 800 * 60)


def _persona(tipo, horario, horas, aus=None, otros=0, bonos=None):
    p = {'emp_id': 1, 'rut': '1.111.111-1', 'nombre': 'PERSONA DE PRUEBA', 'activo': True, 'tipo': tipo, 'horario': horario,
         'horas': horas, 'n_atr': 1, 'n_sad': 0, 'bonos': bonos or {}, 'trab': 18, 'aus': aus or {}, 'per': 0, 'comp': 0,
         'ina': 0, 'ano': 0}
    if tipo == 'BOLSA':
        p.update({'meta': 648000, 'acum': 600000, 'no_usadas': 48000, 'pagar': 0})
    else:
        p.update({'atr': 60, 'sad': 0, 'col': 0, 'h_per': 0, 'otros': otros, 'total': 60 + otros, 'comp_inas': 0,
                  'cubren': 60, 'descontar': otros, 'he_trab': 60, 'he_noap': 0, 'he_decidir': 0, 'he_inas': 0, 'pagar': 0})
    return p


def test_un_informe_por_tipo_de_horario_y_columnas_segun_datos():
    ps = [_persona('CICLO', 'Horario B', 42.0, {'VAC': 1}, bonos={'Bono 1': True}),
          _persona('CICLO', 'Horario A', 42.0), _persona('BOLSA', 'Horario C', 180.0)]
    infs = icp.separar_informes(ps)
    assert [(i['tipo'], i['titulo_horas']) for i in infs] == [('CICLO', '42 horas'), ('BOLSA', '180 horas')]
    assert [p['horario'] for p in infs[0]['personas']] == ['Horario A', 'Horario B']
    cols = icp.columnas(infs[0], JUSTIF, ['Bono 1', 'Bono 2'])
    tit = [c['titulo'] for c in cols]
    dias = [c['titulo'] for c in cols if c['grupo'].startswith('Jornadas')]
    assert dias[0] == 'Programadas' and dias[-1] == 'Trabajadas' and 'VAC' in dias and 'DFHI' not in dias
    assert 'Otros' not in tit and 'Perdonado' not in tit and 'No aprobadas' not in tit
    assert tit[-4:] == ['Descontar', 'Pagar', 'Bono 1', 'Bono 2']
    assert not any('50' in t for t in tit)
    bolsa = [c['titulo'] for c in icp.columnas(infs[1], JUSTIF, [])]
    assert 'No usadas' in bolsa and 'Descontar' not in bolsa


def test_render_pdf_y_nombre_de_archivo():
    inf = icp.separar_informes([_persona('CICLO', 'Horario A', 42.0, otros=5)])[0]
    pdf = icp.render_pdf('AREA DE PRUEBA', '2026-04-26', '2026-05-25', 'usuario', inf, JUSTIF, ['Bono 1'])
    assert pdf.startswith(b'%PDF') and len(pdf) > 2000
    assert icp.nombre_archivo('ÁREA DE PRUEBA', inf, '2026-04-26', '2026-05-25') == 'Informe_cierre_AREA_DE_PRUEBA_42h_2026-04-26_2026-05-25.pdf'
    assert icp.hms(3725) == '01:02:05' and icp.hms(-61) == '−00:01:01' and icp.hms(0) == '—'


def test_correo_de_cierre_adjunta_los_pdf():
    from backend.services.notification_service import NotificationService
    ns = NotificationService()
    enviado = {}

    async def falso(to, subject, html, images=[], attachments=[]):
        enviado.update(to=to, html=html, att=attachments)
        return True
    ns._send_email = falso
    adj = [{'filename': 'Informe_cierre_A_42h.pdf', 'content': b'%PDF-1'}, {'filename': 'Informe_cierre_A_180h.pdf', 'content': b'%PDF-2'}]
    asyncio.run(ns.send_cierre_email(area='A', fecha_inicio='2026-04-26', fecha_fin='2026-05-25', user_name='u',
                                     tipo_cierre='JEFE_AREA', resumen={}, adjuntos=adj, recipients=['rrhh@ejemplo.cl']))
    assert [a['filename'] for a in enviado['att']] == ['Informe_cierre_A_42h.pdf', 'Informe_cierre_A_180h.pdf']
    assert 'Excel con el detalle' in enviado['html'] and '.xlsx' not in enviado['html']


def test_cierre_usa_el_informe_pdf():
    src = open(os.path.join(os.path.dirname(__file__), '..', 'services', 'cierre_service.py'), encoding='utf-8').read()
    assert 'cierre_completo' in src and 'adjuntos=adjuntos' in src and 'resumen_tipos=resumen_tipos' in src and 'excel_content' not in src


def test_preinforme_lo_dice_y_no_lleva_firmas():
    inf = icp.separar_informes([_persona('CICLO', 'Horario A', 42.0)])[0]
    pre = icp.render_pdf('AREA DE PRUEBA', '2026-04-26', '2026-05-25', 'quien sea', inf, JUSTIF, [], preinforme=True)
    fin = icp.render_pdf('AREA DE PRUEBA', '2026-04-26', '2026-05-25', 'quien sea', inf, JUSTIF, [])
    assert pre.startswith(b'%PDF') and b'Preinforme de cierre' in pre and b'Preinforme' not in fin
    assert icp.nombre_archivo('A', inf, '2026-04-26', '2026-05-25', True).startswith('Preinforme_cierre_A_42h')


def test_preinforme_si_el_area_no_esta_cerrada():
    llamadas = {}

    class DB:
        def __init__(self, fila):
            self.fila = fila

        async def fetch_one(self, q, p=()):
            return self.fila

    async def falso(db, svc, fi, ff, area, cerro, preinforme=False, **kw):
        llamadas.update(cerro=cerro, preinforme=preinforme)
        return [{'filename': 'x.pdf', 'titulo': '42 horas', 'content': b'%PDF'}]
    orig = icp.generar_informes_cierre
    icp.generar_informes_cierre = falso
    try:
        r = asyncio.run(icp.informes_del_area(DB(None), None, '2026-04-26', '2026-05-25', 'A'))
        assert r['preinforme'] is True and llamadas['preinforme'] is True
        r = asyncio.run(icp.informes_del_area(DB({'username': 'u1', 'nombre_completo': 'Nombre De Prueba'}), None, '2026-04-26', '2026-05-25', 'A'))
        assert r['preinforme'] is False and llamadas == {'cerro': 'Nombre De Prueba', 'preinforme': False}
    finally:
        icp.generar_informes_cierre = orig


def test_la_app_descarga_el_informe_en_tramos_al_sellar_y_en_la_previsualizacion():
    raiz = os.path.join(os.path.dirname(__file__), '..', '..')
    js = open(os.path.join(raiz, 'frontend', 'js', 'marcaciones_ui.js'), encoding='utf-8').read()
    cfg = open(os.path.join(raiz, 'frontend', 'js', 'configuracion_ui.js'), encoding='utf-8').read()
    rt = open(os.path.join(raiz, 'backend', 'routers', 'cierre.py'), encoding='utf-8').read()
    assert '"/informe-pdf"' in rt and 'informes_del_area' in rt
    assert "window.descargarInformeCierre = async function" in js and "/api/cierre/informe-pdf?" in js
    assert "Descargar preinforme (PDF)" in js and "Descargar informe (PDF)" in js
    assert "window.descargarActaCierre(s.fIni" not in js
    assert "descargarInformeCierre(" in cfg and ">Informe</button>" in cfg


def test_boton_preinforme_en_la_barra_de_la_grilla():
    raiz = os.path.join(os.path.dirname(__file__), '..', '..')
    js = open(os.path.join(raiz, 'frontend', 'js', 'marcaciones_ui.js'), encoding='utf-8').read()
    i_excel = js.index('onclick="downloadExcelReport()"')
    i_pre = js.index('onclick="window.descargarPreinformeGrilla(this)"')
    i_impr = js.index('onclick="window.print()"')
    assert i_excel < i_pre < i_impr, 'el botón Preinforme va al lado del Excel, en la barra de la grilla'
    assert "hasPermission('marcaciones.cierre_periodo')" in js[i_excel:i_pre]
    f = js[js.index('window.descargarPreinformeGrilla = function'):js.index('// ── INFORME DE CIERRE (PDF)')]
    assert "marcacion-area" in f and "st.fechaInicioRRHH" in f and "descargarInformeCierre(" in f


def test_la_descarga_la_entrega_el_servidor_como_adjunto():
    raiz = os.path.join(os.path.dirname(__file__), '..', '..')
    js = open(os.path.join(raiz, 'frontend', 'js', 'marcaciones_ui.js'), encoding='utf-8').read()
    rt = open(os.path.join(raiz, 'backend', 'routers', 'cierre.py'), encoding='utf-8').read()
    f = js[js.index('window.descargarInformeCierre = async function'):]
    f = f[:f.index('\n};')]
    # Sin armar archivos en memoria (algunos navegadores lo bloquean sin avisar): marco oculto al adjunto del servidor
    assert "/api/cierre/informe-pdf/archivo?" in f and "createElement('iframe')" in f
    assert 'createObjectURL' not in f and 'atob(' not in f
    assert '"/informe-pdf/archivo"' in rt and 'attachment; filename=' in rt and 'solo_lista=True' in rt


def test_generar_un_solo_tipo_o_solo_la_lista():
    async def run():
        class DB:
            async def fetch_all(self, q, p=()):
                return [{'nombre': 'Vacaciones', 'nomenclatura': 'VAC'}] if 'justificacion_tipos' in q else []

        class RS:
            def __init__(self, svc):
                pass
            async def datos_periodo(self, fi, ff, area):
                return {'lista_bonos': []}
            _format_concepto_cell = None
        orig_ap = icp.armar_personas
        import backend.services.report_service as rsmod
        rs_orig = rsmod.ReportService
        rsmod.ReportService = RS
        icp.armar_personas = lambda datos, et, j: [_persona('CICLO', 'H', 42.0), _persona('BOLSA', 'B', 180.0)]
        try:
            todos = await icp.generar_informes_cierre(DB(), None, '2026-04-26', '2026-05-25', 'A', 'x', solo_lista=True)
            uno = await icp.generar_informes_cierre(DB(), None, '2026-04-26', '2026-05-25', 'A', 'x', tipo='BOLSA')
        finally:
            rsmod.ReportService = rs_orig
            icp.armar_personas = orig_ap
        return todos, uno
    todos, uno = asyncio.run(run())
    assert [(a['tipo'], a['content']) for a in todos] == [('CICLO', None), ('BOLSA', None)]
    assert [a['tipo'] for a in uno] == ['BOLSA'] and uno[0]['content'].startswith(b'%PDF')


def test_resumen_parte_de_las_horas_totales_y_cuadra_con_sin_descuento():
    p = _persona('CICLO', 'Horario A', 42.0)
    # 100 h programadas; no trabajado: 60 s de atraso + 300 s sin descuento; 60 s de horas extra
    p.update({'h_prog': 360000, 'sin_desc': 300, 'total': 60, 'cubren': 60, 'descontar': 0})
    r = icp.resumen_tipo(icp.separar_informes([p])[0], JUSTIF)
    tx = {f['t']: f for f in r['balance']}
    assert tx['Programadas en días trabajados']['q'] == '100 %'
    assert tx['Horas no trabajadas']['v'] == '− 00:06:00' and tx['Sin descuento']['v'] == '00:05:00'
    assert tx['Trabajadas en el horario']['v'] == icp.hms(360000 - 360)
    assert tx['Total trabajado']['v'] == icp.hms(360000 - 360 + 60)
    nt = r['de_donde'][0]
    assert nt['t'] == 'De las 00:06:00 no trabajadas' and [f['t'] for f in nt['filas']][0] == 'Sin descuento'
    assert not any('erdon' in f['t'] for f in r['balance'] + nt['filas'])
    assert r['cargar'][0]['t'] == 'Descontar' and 'de lo programado' in r['cargar'][0]['q']


def test_correos_con_la_plantilla_banda_azul():
    from backend.services import correo_plantilla as cp
    from backend.services.notification_service import NotificationService
    ns = NotificationService(); enviados = []

    async def falso(to, subject, html, images=[], attachments=[]):
        enviados.append((subject, html, images)); return True
    ns._send_email = falso
    emp = {'nombre_completo': 'PERSONA DE PRUEBA', 'rut_formateado': '1.111.111-1', 'cargo': 'OPERARIO', 'area': 'AREA',
           'fecha_salida_fmt': '30/11/2026', 'fecha_ingreso_fmt': '01/03/2025', 'antiguedad': '1 año'}
    asyncio.run(ns.send_contract_decision_email(emp, 'renovar', 'Contrato renovado.', ['x@ejemplo.cl']))
    asyncio.run(ns.send_justification_email(emp, 'Vacaciones', '2026-11-10', '2026-11-14', ['x@ejemplo.cl'], None, 5))
    for subject, html, images in enviados:
        assert 'cid:logo_aguacol' in html and '50%' not in html and '50 %' not in html
        assert all(ord(ch) < 0x1F300 for ch in subject + html), 'sin emojis'
        assert '2026-11-10' not in html and '/2026' not in html, 'fechas en dd-mm-aaaa'
    assert enviados[0][0].startswith('Contrato renovado · PERSONA DE PRUEBA')
    assert '10-11-2026' in enviados[1][1] and 'Justificación registrada' in enviados[1][0]
    assert cp.ruta_logo().endswith('logo-aguacol.png')
    assert cp.fecha('2026-05-04') == '04-05-2026' and cp.fecha('30/11/2026') == '30-11-2026'


def test_aviso_de_sincronizacion_sin_emojis():
    src = open(os.path.join(os.path.dirname(__file__), '..', 'services', 'sync_monitor.py'), encoding='utf-8').read()
    assert '⚠️' not in src and '✅' not in src and 'correo_plantilla' in src


def test_menos_de_un_minuto_sin_descuento_es_redondeo():
    p = _persona('CICLO', 'Horario A', 42.0)
    p.update({'h_prog': 36000, 'sin_desc': -1, 'total': 60, 'cubren': 60, 'descontar': 0})
    r = icp.resumen_tipo(icp.separar_informes([p])[0], JUSTIF)
    assert 'Sin descuento' not in {f['t'] for f in r['balance']}
    assert {f['t']: f['v'] for f in r['balance']}['Atrasos'] == '00:00:59'


def test_horas_de_otros_dias_entran_al_balance():
    from datetime import date
    dd = {'2026-05-01': {'estado': 'OK', 'horas_teoricas': 8, 'horas_trabajadas': 8},
          '2026-05-02': {'estado': 'JORNADA_COMPENSATORIA', 'horas_teoricas': 0, 'horas_trabajadas': 4},
          '2026-05-03': {'estado': 'PERMISO', 'horas_teoricas': 8, 'horas_trabajadas': 2}}
    h = icp.horas_dias(dd, [date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3)])
    assert h == {'prog': 8 * 3600, 'trab': 8 * 3600, 'otros': {'Jornadas compensatorias': 4 * 3600, 'Días con permiso': 2 * 3600}}


def test_resumen_de_un_area_cerrada_desde_tramos():
    raiz = os.path.join(os.path.dirname(__file__), '..', '..')
    js = open(os.path.join(raiz, 'frontend', 'js', 'marcaciones_ui.js'), encoding='utf-8').read()
    cfg = open(os.path.join(raiz, 'frontend', 'js', 'configuracion_ui.js'), encoding='utf-8').read()
    assert "window.verResumenCierre = function" in js and "window.cargarResumenCierre(st, 'cz-resumen-vista')" in js
    assert "verResumenCierre('" in cfg and ">Resumen</button>" in cfg and ">Informe</button>" in cfg
