"""
Informe de cierre en PDF para Recursos Humanos: lo que se carga en el sistema de remuneraciones.

Un informe por área y por tipo de horario (Ciclo Inteligente / Bolsa Flexible), con un balance de horas que se lee de
izquierda a derecha y cuadra al segundo:

  · Jornadas del período (días): programadas − ausencias = trabajadas.
  · Ciclo: horas no trabajadas por causa → total; horas extra trabajadas − no aprobadas − las que cubren descuentos;
    a cargar: descontar = total − cubren descuentos; pagar = horas extra que quedan.
  · Bolsa: meta y trabajadas del tramo; lo que pasa la meta son horas extra a pagar y lo que falta son horas no usadas
    (no son descuento).

Las cifras salen del mismo cálculo del Excel de cierre (ReportService._calcular_filas) y, en el Ciclo, del libro mayor
de minutos (cuadre_service.plegar_libro). Los perdonazos no se muestran: las causas van netas de lo perdonado.
"""
import os
import re
import unicodedata
from collections import OrderedDict
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.core.config import settings
from backend.core.rut import rut_visible

TIPOS_BOLSA = ('BOLSA_FLEXIBLE', 'FLEXIBLE_BOLSA')
# Siglas de la grilla (ReportService._format_concepto_cell) que son un día programado y trabajado
SIGLAS_TRABAJADAS = {'OK', 'ATR', 'SAD', 'ATR-SAD'}
# Estados de justificación que la grilla muestra con su sigla aunque no traigan nomenclatura
ESTADOS_JUSTIFICADOS = {'VACACIONES', 'LICENCIA', 'LIC_COMUN', 'LIC_MUTUAL', 'LCM', 'LMU', 'CUM', 'DUE'}

# Colores de la app (frontend/css/ventanas.css)
C_NAVY, C_NAVY_SOFT, C_NAVY_RES, C_NAVY_RES_TD = '#1b2f8f', '#e9edfb', '#dfe5f8', '#f3f5fc'
C_INK, C_INK_2, C_LINE, C_LINE_2, C_ZEBRA = '#1a2233', '#4a5468', '#d9deea', '#eef1f7', '#fafbfd'
C_PINK, C_PINK_SOFT, C_AMBER, C_AMBER_SOFT = '#c0267a', '#fce7ef', '#9a4a08', '#fdf0e1'
C_GREEN, C_GREEN_SOFT, C_CERO = '#16673b', '#e5f3ea', '#b9c0cf'


def _norm(s: Any) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', str(s or '')) if unicodedata.category(c) != 'Mn').upper().strip()


def hms(seg: int, menos: bool = False) -> str:
    """Horas en HH:MM:SS (obligatorio en el informe). Cero se escribe «—»."""
    seg = int(round(seg or 0))
    if not seg:
        return '—'
    t = abs(seg)
    return ('−' if (menos or seg < 0) else '') + f'{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}'


def _seg(minutos: Any) -> int:
    return int(round(float(minutos or 0.0) * 60))


def horas_txt(h: Optional[float]) -> str:
    if h is None:
        return ''
    h = float(h)
    return (f'{h:.0f}' if h.is_integer() else f'{h:.1f}'.replace('.', ',')) + ' horas'


# ───────────────────────────── datos por persona (funciones puras) ─────────────────────────────

def dias_persona(dias_dict: Dict[str, Any], rango_dias: List, es_bolsa: bool, etiqueta, justif: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Cuenta las jornadas del período con las mismas siglas de la grilla.
    etiqueta(di, es_bolsa) → (sigla, color, negrita), la de ReportService._format_concepto_cell.
    justif: [{'nombre', 'nomenclatura'}] de justificacion_tipos (la columna de cada ausencia lleva su código)."""
    por_clave = {}
    for t in justif:
        cod = (t.get('nomenclatura') or t.get('nombre') or '').strip().upper()
        if cod:
            por_clave[_norm(cod)] = cod
            por_clave[_norm(t.get('nombre'))] = cod
    out = {'trab': 0, 'aus': {}, 'per': 0, 'comp': 0, 'ina': 0, 'ano': 0}
    for d in rango_dias:
        di = dias_dict.get(f'{d.year}-{d.month:02d}-{d.day:02d}')
        if not isinstance(di, dict):
            continue
        sigla = (etiqueta(di, es_bolsa)[0] or '').split('\n')[0].strip()
        estado = str(di.get('estado') or '')
        if sigla in SIGLAS_TRABAJADAS:
            out['trab'] += 1
        elif sigla == 'INA':
            out['ina'] += 1
        elif sigla == 'ANO' or estado.startswith('ANOMALIA'):
            out['ano'] += 1
        elif sigla == 'PER':
            out['per'] += 1
        elif sigla in ('COMP', 'C.HE') and estado == 'INASISTENCIA_COMPENSADA':
            out['comp'] += 1
        elif sigla != 'DEOP' and (di.get('nomenclatura') or estado.upper() in ESTADOS_JUSTIFICADOS
                                  or _norm(estado) in por_clave or _norm(sigla) in por_clave):
            cod = por_clave.get(_norm(di.get('nomenclatura'))) or por_clave.get(_norm(estado)) or por_clave.get(_norm(sigla)) or sigla
            out['aus'][cod] = out['aus'].get(cod, 0) + 1
        # LIB, FER, DEOP y las jornadas en días no programados (ESP, EXT, HE, +2) no son días del balance
    return out


def horas_ciclo(libro: Dict[str, Any]) -> Dict[str, int]:
    """Horas de una persona de Ciclo en segundos, desde el libro mayor, sin perdonazos a la vista.

    Las causas del libro ya vienen sin lo perdonado en el día; lo perdonado en el cuadre se rebaja como lo hace
    plegar_libro (primero salidas, después atrasos) y lo tolerado, de la causa mayor. Las cifras que se cargan
    (descontar, pagar, cubren descuentos, trabajadas) quedan iguales al sistema; el redondeo a segundos (el sistema
    guarda fracciones) lo absorbe la causa mayor, para que la fila sume a la vista."""
    c = {k: float(v or 0.0) for k, v in (libro.get('causas') or {}).items()}
    for k in ('atraso', 'salida', 'colacion', 'permiso', 'otra'):
        c.setdefault(k, 0.0)
    pc = float(libro.get('perdon_cuadre') or 0.0)
    q = min(pc, c['salida'])
    c['salida'] -= q
    c['atraso'] -= (pc - q)
    tol = float(libro.get('tolerado') or 0.0)
    if tol:
        k = max(('atraso', 'salida', 'colacion', 'permiso', 'otra'), key=lambda x: c[x])
        c[k] -= tol
    s = {'atr': _seg(c['atraso']), 'sad': _seg(c['salida']), 'col': _seg(c['colacion']), 'h_per': _seg(c['permiso']),
         'otros': _seg(c['otra']),
         'comp_inas': _seg(libro.get('compensado_inasistencia')), 'cubren': _seg(libro.get('cubierto')),
         'descontar': _seg(libro.get('pendiente')),
         'he_trab': _seg(libro.get('he_trabajadas')), 'he_noap': _seg(libro.get('he_no_pagadas')),
         'he_decidir': _seg(libro.get('he_por_decidir')), 'he_inas': _seg(libro.get('he_usadas_inasistencia')),
         'pagar': _seg(libro.get('he_a_pagar'))}
    causas = ('atr', 'sad', 'col', 'h_per', 'otros')
    total = s['comp_inas'] + s['cubren'] + s['descontar']
    dif = total - sum(s[k] for k in causas)
    if dif:
        s[max(causas, key=lambda k: s[k])] += dif
    s['total'] = total
    res = s['he_trab'] - s['he_noap'] - s['he_decidir'] - s['he_inas'] - s['cubren'] - s['pagar']
    if res:  # trabajadas − ... − pagar debe dar 0: el sobrante va a «no aprobadas» o, si no hay, sale de «trabajadas»
        if s['he_noap']:
            s['he_noap'] += res
        else:
            s['he_trab'] -= res
    if abs(dif) > 60 or abs(res) > 60:
        logger.warning(f'[InformeCierre] el libro no cuadra por más de un minuto (causas {dif} s, horas extra {res} s)')
    return s


def horas_bolsa(fila: Dict[str, Any]) -> Dict[str, int]:
    meta, acum = _seg(fila.get('metaMin')), _seg(fila.get('acumBolsa'))
    saldo = acum - meta
    return {'meta': meta, 'acum': acum, 'no_usadas': max(-saldo, 0),
            'pagar': max(saldo, 0) + _seg(fila.get('he_apr'))}


def armar_personas(datos: Dict[str, Any], etiqueta, justif: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Una persona por fila del resumen del período, con sus días, horas y bonos."""
    md = datos['matrix_data']
    emps = {e['id']: e for e in md.get('empleados', [])}
    matrix = md.get('matrix', {})
    out = []
    for r in datos['filas']:
        e = emps.get(r['emp_id'], {})
        tipo = e.get('tipo_programacion') or ''
        es_bolsa = tipo in TIPOS_BOLSA
        dd = matrix.get(str(r['emp_id'])) or matrix.get(r['emp_id']) or {}
        p = {'emp_id': r['emp_id'], 'rut': rut_visible(r.get('rut')), 'nombre': r['nombre'],
             'activo': r.get('activo') != 'NO', 'tipo': 'BOLSA' if es_bolsa else 'CICLO',
             'horario': e.get('turno') or 'Sin horario asignado',
             'horas': float(e['meta_horas_semanales']) if e.get('turno') and e.get('meta_horas_semanales') is not None else None,
             'n_atr': int(r.get('cnt_atr') or 0), 'n_sad': int(r.get('cnt_sad') or 0),
             'bonos': {b: bool(v and v.get('aplica') is not False and v.get('califica')) for b, v in (r.get('bonos') or {}).items()}}
        p.update(dias_persona(dd, datos['rango_dias'], es_bolsa, etiqueta, justif))
        p.update(horas_bolsa(r) if es_bolsa else horas_ciclo(r.get('libro') or {}))
        out.append(p)
    return out


def separar_informes(personas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Un informe por tipo de horario; dentro, las personas agrupadas por horario."""
    informes = []
    for tipo in ('CICLO', 'BOLSA'):
        ps = sorted((p for p in personas if p['tipo'] == tipo), key=lambda p: (p['horario'], p['nombre']))
        if ps:
            horas = sorted({p['horas'] for p in ps if p['horas'] is not None})
            informes.append({'tipo': tipo, 'personas': ps, 'horas': horas,
                             'titulo_horas': ' y '.join(horas_txt(h) for h in horas)})
    return informes


# ───────────────────────────── columnas (función pura) ─────────────────────────────

def columnas(inf: Dict[str, Any], justif: List[Dict[str, Any]], bonos: List[str]) -> List[Dict[str, Any]]:
    """Columnas del informe, en el orden del balance. Las que nadie tiene no aparecen (salvo las del balance)."""
    ps, bolsa = inf['personas'], inf['tipo'] == 'BOLSA'
    hay = lambda f: any(f(p) for p in ps)
    orden_cod = [((t.get('nomenclatura') or t.get('nombre') or '').strip().upper()) for t in justif]
    usados = {c for p in ps for c in p['aus']}
    cods = [c for c in orden_cod if c in usados] + sorted(usados - set(orden_cod))
    resta = [(c, (lambda c: lambda p: p['aus'].get(c, 0))(c)) for c in cods]
    if hay(lambda p: p['per']): resta.append(('PER', lambda p: p['per']))
    if hay(lambda p: p['comp']): resta.append(('Comp.', lambda p: p['comp']))
    resta.append(('Inas.', lambda p: p['ina']))
    if hay(lambda p: p['ano']): resta.append(('Sin resolver', lambda p: p['ano']))
    prog = lambda p: p['trab'] + sum(f(p) for _, f in resta)
    col = lambda g, t, f, fmt='n', color='', res=False: {'grupo': g, 'titulo': t, 'valor': f, 'fmt': fmt, 'color': color, 'res': res}
    g = 'Jornadas del período (días)'
    C = [col(g, 'Programadas', prog)] + [col(g, t, f) for t, f in resta] + [col(g, 'Trabajadas', lambda p: p['trab'], color='bal', res=True)]
    if bolsa:
        g = 'Horas del tramo'
        C += [col(g, 'Meta', lambda p: p['meta'], 'h'), col(g, 'Trabajadas', lambda p: p['acum'], 'h'),
              col(g, 'No usadas', lambda p: p['no_usadas'], 'h', 'nu'),
              col('A cargar', 'Horas extra a pagar', lambda p: p['pagar'], 'h', 'he', True)]
    else:
        g = 'Incidentes (cantidad)'
        C += [col(g, 'Atrasos', lambda p: p['n_atr']), col(g, 'Sal. ant.', lambda p: p['n_sad'])]
        g = 'Horas no trabajadas'
        C += [col(g, 'Atrasos', lambda p: p['atr'], 'h', 'ds'), col(g, 'Sal. ant.', lambda p: p['sad'], 'h', 'ds'),
              col(g, 'Colación', lambda p: p['col'], 'h', 'ds'), col(g, 'Permisos', lambda p: p['h_per'], 'h', 'ds')]
        if hay(lambda p: p['otros']): C.append(col(g, 'Otros', lambda p: p['otros'], 'h', 'ds'))
        C.append(col(g, 'Total', lambda p: p['total'], 'h', 'bal'))
        if hay(lambda p: p['comp_inas']): C.append(col('Rebaja', 'Inas. compensadas', lambda p: -p['comp_inas'], 'h', 'cp'))
        g = 'Horas extra'
        C.append(col(g, 'Trabajadas', lambda p: p['he_trab'], 'h'))
        if hay(lambda p: p['he_noap']): C.append(col(g, 'No aprobadas', lambda p: -p['he_noap'], 'h', 'cp'))
        if hay(lambda p: p['he_decidir']): C.append(col(g, 'Por decidir', lambda p: -p['he_decidir'], 'h', 'al'))
        if hay(lambda p: p['he_inas']): C.append(col(g, 'Compensan inas.', lambda p: -p['he_inas'], 'h', 'cp'))
        C.append(col(g, 'Cubren descuentos', lambda p: -p['cubren'], 'h', 'cp'))
        C += [col('A cargar', 'Descontar', lambda p: p['descontar'], 'h', 'tot', True),
              col('A cargar', 'Pagar', lambda p: p['pagar'], 'h', 'he', True)]
    for b in bonos:
        C.append(col('Bonos', b, (lambda b: lambda p: p['bonos'].get(b, False))(b), 'b'))
    return C


def leyenda(inf: Dict[str, Any], justif: List[Dict[str, Any]], cols: List[Dict[str, Any]]) -> List[str]:
    titulos = {c['titulo'] for c in cols}
    usados = {c for p in inf['personas'] for c in p['aus']}
    partes = [f"<b>{(t.get('nomenclatura') or t.get('nombre') or '').strip().upper()}</b> {t.get('nombre')}" for t in justif
              if (t.get('nomenclatura') or t.get('nombre') or '').strip().upper() in usados]
    if 'PER' in titulos: partes.append('<b>PER</b> permiso del día')
    if 'Comp.' in titulos: partes.append('<b>Comp.</b> inasistencia compensada')
    if 'Sin resolver' in titulos: partes.append('<b>Sin resolver</b> jornada con anomalía al cerrar')
    l1 = '<b>Jornadas</b>: programadas − ausencias = trabajadas.' + (' ' + ' · '.join(partes) + '.' if partes else '')
    if inf['tipo'] == 'BOLSA':
        l2 = ('Horas en formato HH:MM:SS. <b>Horas del tramo</b>: trabajadas − meta. Si pasa la meta, la diferencia son '
              '<b>horas extra a pagar</b>; si no la alcanza, son <b>No usadas</b>: no son descuento y no se cargan a la '
              'persona. La meta baja con vacaciones, licencias y permisos del tramo.')
    else:
        l2 = ('Horas en formato HH:MM:SS. <b>Descontar</b> = total de horas no trabajadas'
              + (' − inasistencias compensadas' if 'Inas. compensadas' in titulos else '')
              + ' − horas extra que cubren descuentos. <b>Pagar</b> = horas extra trabajadas'
              + (' − no aprobadas' if 'No aprobadas' in titulos else '') + (' − por decidir' if 'Por decidir' in titulos else '')
              + (' − las que compensan inasistencias' if 'Compensan inas.' in titulos else '') + ' − las que cubren descuentos.'
              + (' <b>Otros</b>: jornada incompleta que no es atraso, salida, colación ni permiso.' if 'Otros' in titulos else ''))
    return [l1, l2 + ' El detalle día a día está en el Excel del cierre, que se descarga desde la aplicación.']


def resumen(inf: Dict[str, Any]) -> List[tuple]:
    """Cifras del resumen de arriba: (texto antes, cifra, texto después, alerta)."""
    ps = inf['personas']
    T = lambda k: sum(p[k] for p in ps)
    out = [('', str(len(ps)), ' personas', False)]
    if inf['tipo'] == 'BOLSA':
        out += [('Horas extra a pagar ', hms(T('pagar')), '', False), ('Horas no usadas ', hms(T('no_usadas')), ' · no se descuentan', False)]
    else:
        out += [('Horas a descontar ', hms(T('descontar')), '', False), ('Horas extra a pagar ', hms(T('pagar')), '', False),
                ('Horas extra que cubren descuentos ', hms(T('cubren')), '', False)]
        if T('he_decidir'):
            out.append(('', hms(T('he_decidir')), ' de horas extra sin decidir', True))
    ano = T('ano')
    if ano:
        out.append(('', str(ano), ' jornada sin resolver' if ano == 1 else ' jornadas sin resolver', True))
    return out


# ───────────────────────────── PDF (reportlab) ─────────────────────────────

_FUENTES = False


def _registrar_fuentes() -> bool:
    """Barlow (la letra de la app). Sin los archivos, Helvetica."""
    global _FUENTES
    if _FUENTES:
        return True
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.fonts import addMapping
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'fonts')
    archivos = {'Barlow': 'barlow-latin-400-normal', 'Barlow-Medium': 'barlow-latin-500-normal',
                'Barlow-SemiBold': 'barlow-latin-600-normal', 'Barlow-Bold': 'barlow-latin-700-normal',
                'BarlowSC-SemiBold': 'barlow-semi-condensed-latin-600-normal', 'BarlowSC-Bold': 'barlow-semi-condensed-latin-700-normal'}
    try:
        for nombre, f in archivos.items():
            pdfmetrics.registerFont(TTFont(nombre, os.path.join(base, f + '.ttf')))
        addMapping('Barlow', 0, 0, 'Barlow'); addMapping('Barlow', 1, 0, 'Barlow-Bold')
        addMapping('Barlow', 0, 1, 'Barlow'); addMapping('Barlow', 1, 1, 'Barlow-Bold')
        _FUENTES = True
    except Exception as e:
        logger.warning(f'[InformeCierre] sin letras Barlow, se usa Helvetica: {e}')
    return _FUENTES


def _f(nombre: str) -> str:
    if _FUENTES:
        return nombre
    return 'Helvetica-Bold' if any(x in nombre for x in ('Bold', 'SemiBold')) else 'Helvetica'


def _check_flowable(size: float = 8.5):
    from reportlab.platypus import Flowable
    from reportlab.lib import colors

    class Check(Flowable):
        def __init__(self):
            super().__init__()
            self.width = self.height = size

        def draw(self):
            c = self.canv
            r = size / 2
            c.setStrokeColor(colors.HexColor(C_GREEN)); c.setFillColor(colors.HexColor(C_GREEN_SOFT)); c.setLineWidth(0.8)
            c.circle(r, r, r - 0.5, stroke=1, fill=1)
            c.setLineWidth(1.2); c.setLineCap(1); c.setLineJoin(1)
            p = c.beginPath(); p.moveTo(size * .29, size * .52); p.lineTo(size * .44, size * .36); p.lineTo(size * .72, size * .66)
            c.drawPath(p, stroke=1, fill=0)
    return Check()


def render_pdf(area: str, fecha_inicio: str, fecha_fin: str, cerro: str, inf: Dict[str, Any],
               justif: List[Dict[str, Any]], bonos: List[str], preinforme: bool = False) -> bytes:
    """Un informe (área × tipo de horario) en A4 horizontal. Con preinforme=True es el del período aún sin cerrar:
    lo dice el título y un aviso, «Cerró» queda «Sin cerrar» y no lleva firmas."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether

    _registrar_fuentes()
    H = colors.HexColor
    ancho_pag, alto_pag = landscape(A4)
    mx = 20
    util = ancho_pag - 2 * mx
    fmt_f = lambda f: datetime.strptime(f, '%Y-%m-%d').strftime('%d-%m-%Y')
    emision = datetime.now().strftime('%d-%m-%Y %H:%M')
    ps = inf['personas']
    cols = columnas(inf, justif, bonos)

    # ── texto de cada celda
    def txt(c, p):
        v = c['valor'](p)
        if c['fmt'] == 'b':
            return bool(v)
        if c['fmt'] == 'h':
            return hms(v)
        return '—' if not v else str(v)

    def txt_total(c):
        if c['fmt'] == 'b':
            return str(sum(1 for p in ps if c['valor'](p)))
        s = sum(c['valor'](p) for p in ps)
        return hms(s) if c['fmt'] == 'h' else ('—' if not s else str(s))

    grupos_hor = OrderedDict()
    for p in ps:
        grupos_hor.setdefault(p['horario'], []).append(p)

    # ── anchos: el mayor texto de cada columna en una sola línea; si no cabe, baja la letra
    pad = 2.6
    def medir(cuerpo):
        cab = cuerpo - 1.3
        w_rut = max([stringWidth('RUT', _f('BarlowSC-SemiBold'), cab)] + [stringWidth(p['rut'], _f('Barlow'), cuerpo) for p in ps])
        badge = stringWidth('Inactivo', _f('Barlow-SemiBold'), cuerpo - 1.4) + 8
        w_nom = max([stringWidth('NOMBRE', _f('BarlowSC-SemiBold'), cab), stringWidth(f'Total · {len(ps)} personas', _f('Barlow-Bold'), cuerpo)]
                    + [stringWidth(p['nombre'], _f('Barlow-Medium'), cuerpo) + (0 if p['activo'] else badge) for p in ps])
        ws = [w_rut + 2 * pad, w_nom + 2 * pad]
        for c in cols:
            w = stringWidth(c['titulo'].upper(), _f('BarlowSC-SemiBold'), cab)
            if c['fmt'] == 'b':
                w = max(w, 9)
            else:
                w = max([w, stringWidth(txt_total(c), _f('Barlow-Bold'), cuerpo)] + [stringWidth(txt(c, p), _f('Barlow-Bold'), cuerpo) for p in ps])
            ws.append(w + 2 * pad)
        return ws
    cuerpo = 7.8
    anchos = medir(cuerpo)
    while sum(anchos) > util and cuerpo > 5.6:
        cuerpo -= 0.2
        anchos = medir(cuerpo)
    if sum(anchos) < util:                      # el espacio que sobra va al nombre
        anchos[1] += util - sum(anchos)
    cab = cuerpo - 1.3

    st_nom = ParagraphStyle('nom', fontName=_f('Barlow-Medium'), fontSize=cuerpo, leading=cuerpo + 1.5, textColor=H(C_INK))
    st_hor = ParagraphStyle('hor', fontName=_f('BarlowSC-Bold'), fontSize=cuerpo + 1.2, leading=cuerpo + 3, textColor=H(C_NAVY))

    # ── filas
    spans, prev, primeros = [], None, set()
    for i, c in enumerate(cols):
        if c['grupo'] != prev:
            spans.append([c['grupo'], i, i]); primeros.add(i + 2); prev = c['grupo']
        spans[-1][2] = i
    fila_g = ['', ''] + [''] * len(cols)
    for g, a, b in spans:
        fila_g[a + 2] = g.upper()
    fila_h = ['RUT', 'NOMBRE'] + [c['titulo'].upper() for c in cols]
    data = [fila_g, fila_h]
    estilo = [
        ('FONT', (0, 0), (-1, 0), _f('BarlowSC-SemiBold'), cab - 0.3), ('TEXTCOLOR', (0, 0), (-1, 0), H(C_INK_2)),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONT', (0, 1), (-1, 1), _f('BarlowSC-SemiBold'), cab), ('TEXTCOLOR', (0, 1), (-1, 1), H(C_NAVY)),
        ('BACKGROUND', (0, 1), (-1, 1), H(C_NAVY_SOFT)), ('LINEBELOW', (0, 1), (-1, 1), 0.8, H(C_NAVY)),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), pad), ('RIGHTPADDING', (0, 0), (-1, -1), pad),
        ('TOPPADDING', (0, 0), (-1, -1), 2.6), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.6),
        ('FONT', (0, 2), (-1, -1), _f('Barlow'), cuerpo), ('TEXTCOLOR', (0, 2), (-1, -1), H(C_INK)),
    ]
    for g, a, b in spans:
        estilo += [('SPAN', (a + 2, 0), (b + 2, 0)), ('LINEBELOW', (a + 2, 0), (b + 2, 0), 0.6, H(C_LINE))]
    for i, c in enumerate(cols):
        x = i + 2
        if c['fmt'] == 'b':
            estilo.append(('ALIGN', (x, 1), (x, -1), 'CENTER'))
        if c['res']:
            estilo.append(('BACKGROUND', (x, 1), (x, 1), H(C_NAVY_RES)))
    colores = {'ds': C_PINK, 'tot': C_PINK, 'he': C_GREEN, 'cp': C_INK_2, 'nu': C_INK_2, 'al': C_AMBER, 'bal': C_INK}
    negrita = {'tot', 'he', 'bal', 'nu'}

    fila = 2
    for hor, gp in grupos_hor.items():
        hh = gp[0]['horas']
        data.append([Paragraph(f'{hor}<font name="{_f("Barlow")}" size="{cuerpo}" color="{C_INK_2}">&nbsp;&nbsp;'
                               f'{horas_txt(hh) + " · " if hh else ""}{len(gp)} {"persona" if len(gp) == 1 else "personas"}</font>', st_hor)]
                    + [''] * (len(cols) + 1))
        estilo += [('SPAN', (0, fila), (-1, fila)), ('LINEBELOW', (0, fila), (-1, fila), 0.8, H(C_NAVY)),
                   ('TOPPADDING', (0, fila), (-1, fila), 7), ('BOTTOMPADDING', (0, fila), (-1, fila), 2)]
        fila += 1
        for k, p in enumerate(gp):
            nom = p['nombre'] if p['activo'] else (
                f'{p["nombre"]} <font name="{_f("Barlow-SemiBold")}" size="{cuerpo - 1.4}" color="{C_AMBER}" backColor="{C_AMBER_SOFT}">'
                f'&nbsp;Inactivo&nbsp;</font>')
            celdas = [p['rut'], Paragraph(nom, st_nom)]
            for i, c in enumerate(cols):
                x = i + 2
                t = txt(c, p)
                if c['fmt'] == 'b':
                    celdas.append(_check_flowable() if t else '—')
                    if not t:
                        estilo.append(('TEXTCOLOR', (x, fila), (x, fila), H(C_CERO)))
                    continue
                celdas.append(t)
                if t == '—':
                    estilo.append(('TEXTCOLOR', (x, fila), (x, fila), H(C_CERO)))
                elif c['color']:
                    estilo.append(('TEXTCOLOR', (x, fila), (x, fila), H(colores[c['color']])))
                    if c['color'] in negrita:
                        estilo.append(('FONT', (x, fila), (x, fila), _f('Barlow-Bold'), cuerpo))
                if c['res']:
                    estilo.append(('BACKGROUND', (x, fila), (x, fila), H(C_NAVY_RES_TD)))
            if k % 2 == 1:
                estilo.append(('BACKGROUND', (0, fila), (1, fila), H(C_ZEBRA)))
            estilo.append(('LINEBELOW', (0, fila), (-1, fila), 0.4, H(C_LINE_2)))
            data.append(celdas)
            fila += 1
    data.append([f'Total · {len(ps)} personas', ''] + [txt_total(c) for c in cols])
    estilo += [('SPAN', (0, fila), (1, fila)), ('FONT', (0, fila), (-1, fila), _f('Barlow-Bold'), cuerpo),
               ('LINEABOVE', (0, fila), (-1, fila), 1.1, H(C_INK)), ('TOPPADDING', (0, fila), (-1, fila), 4)]
    for x in sorted(primeros):
        estilo.append(('LINEBEFORE', (x, 1), (x, -1), 0.5, H(C_LINE)))

    tabla = Table(data, colWidths=anchos, repeatRows=2)
    tabla.setStyle(TableStyle(estilo))

    # ── encabezado
    logo_path = os.path.join(str(settings.BASE_DIR), 'frontend', 'assets', 'img', 'logo-aguacol.png')
    nombre_doc = 'Preinforme de cierre' if preinforme else 'Informe de cierre'
    if preinforme:
        cerro = 'Sin cerrar'
    titulo = Paragraph(f'{nombre_doc} · {(area or "Todas").title()} · {inf["titulo_horas"]}',
                       ParagraphStyle('t', fontName=_f('BarlowSC-Bold'), fontSize=15, leading=18, textColor=H(C_NAVY)))
    st_meta = ParagraphStyle('m', fontName=_f('Barlow'), fontSize=8.3, leading=10.5, textColor=H(C_INK_2))
    meta = Table([[Paragraph('Período', st_meta), Paragraph(f'<font name="{_f("Barlow-SemiBold")}" color="{C_INK}">{fmt_f(fecha_inicio)} al {fmt_f(fecha_fin)}</font>', st_meta)],
                  [Paragraph('Emitido', st_meta), Paragraph(f'<font name="{_f("Barlow-SemiBold")}" color="{C_INK}">{emision}</font>', st_meta)],
                  [Paragraph('Cerró', st_meta), Paragraph(f'<font name="{_f("Barlow-SemiBold")}" color="{C_INK}">{cerro}</font>', st_meta)]],
                 colWidths=[38, 125])
    meta.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                              ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    logo = Image(logo_path, width=78, height=78 * 278 / 1001) if os.path.exists(logo_path) else ''
    enc = Table([[logo, titulo, meta]], colWidths=[90, util - 90 - 165, 165])
    enc.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                             ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('LINEBELOW', (0, 0), (-1, 0), 1.6, H(C_NAVY)),
                             ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))

    # ── resumen (recuadros)
    st_chip = ParagraphStyle('c', fontName=_f('Barlow'), fontSize=8.3, leading=10, textColor=H(C_INK))
    chips, est_chips, anchos_chip = [], [], []
    lista_resumen = resumen(inf)
    if preinforme:
        lista_resumen = [('', 'Sin cerrar', ' · preinforme, las cifras pueden cambiar hasta el cierre', True)] + lista_resumen
    for i, (a, num, b, alerta) in enumerate(lista_resumen):
        color = C_PINK if alerta else C_INK
        chips.append(Paragraph(f'<font color="{color}">{a}<font name="{_f("Barlow-Bold")}">{num}</font>{b}</font>', st_chip))
        anchos_chip.append(stringWidth(a + b, _f('Barlow'), 8.3) + stringWidth(num, _f('Barlow-Bold'), 8.3) + 14)
        est_chips += [('BOX', (2 * i, 0), (2 * i, 0), 0.6, H(C_PINK if alerta else C_LINE))]
        if alerta:
            est_chips.append(('BACKGROUND', (2 * i, 0), (2 * i, 0), H(C_PINK_SOFT)))
        chips.append(''); anchos_chip.append(5)
    t_chips = Table([chips], colWidths=anchos_chip, hAlign='LEFT')
    t_chips.setStyle(TableStyle(est_chips + [('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                                             ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))

    st_ley = ParagraphStyle('l', fontName=_f('Barlow'), fontSize=7.2, leading=10, textColor=H(C_INK_2))
    firmas = Table([['Jefatura del área', '', 'Recursos Humanos · recibido', '', 'Cargado en remuneraciones · fecha']],
                   colWidths=[(util - 60) / 3, 30, (util - 60) / 3, 30, (util - 60) / 3])
    firmas.setStyle(TableStyle([('FONT', (0, 0), (-1, -1), _f('Barlow'), 7.8), ('TEXTCOLOR', (0, 0), (-1, -1), H(C_INK)),
                                ('LINEABOVE', (0, 0), (0, 0), 0.8, H(C_INK)), ('LINEABOVE', (2, 0), (2, 0), 0.8, H(C_INK)),
                                ('LINEABOVE', (4, 0), (4, 0), 0.8, H(C_INK)), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                ('TOPPADDING', (0, 0), (-1, -1), 3)]))

    historia = [enc, Spacer(1, 8), t_chips, Spacer(1, 6), tabla, Spacer(1, 7)]
    historia += [Paragraph(x, st_ley) for x in leyenda(inf, justif, cols)]
    if not preinforme:
        historia += [Spacer(1, 26), KeepTogether([firmas])]

    def pie(canvas, doc):
        canvas.saveState()
        canvas.setFont(_f('Barlow'), 7)
        canvas.setFillColor(H(C_INK_2))
        canvas.drawRightString(ancho_pag - mx, 14, f'Página {doc.page}')
        canvas.drawString(mx, 14, f'Aguacol · {nombre_doc}{" (sin cerrar)" if preinforme else ""} · {(area or "Todas").title()} · {inf["titulo_horas"]}')
        canvas.restoreState()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=mx, rightMargin=mx, topMargin=26, bottomMargin=28,
                            title=f'{nombre_doc} {area} {inf["titulo_horas"]}', author='Aguacol Asistencia')
    doc.build(historia, onFirstPage=pie, onLaterPages=pie)
    return buf.getvalue()


def nombre_archivo(area: str, inf: Dict[str, Any], fecha_inicio: str, fecha_fin: str, preinforme: bool = False) -> str:
    a = re.sub(r'[^A-Za-z0-9]+', '_', _norm(area or 'Todas')).strip('_')
    h = '_'.join(f'{x:g}h' for x in inf['horas']) or inf['tipo'].lower()
    return f'{"Preinforme" if preinforme else "Informe"}_cierre_{a}_{h}_{fecha_inicio}_{fecha_fin}.pdf'


# ───────────────────────────── punto de entrada ─────────────────────────────

async def generar_informes_cierre(db, asistencia_service, fecha_inicio: str, fecha_fin: str, area: str, cerro: str,
                                  preinforme: bool = False) -> List[Dict[str, Any]]:
    """Los PDF del cierre de un área: [{'filename', 'titulo', 'content'}], uno por tipo de horario."""
    from backend.services.report_service import ReportService
    rs = ReportService(asistencia_service)
    datos = await rs.datos_periodo(fecha_inicio, fecha_fin, area)
    justif = [dict(r) for r in await db.fetch_all('SELECT nombre, nomenclatura FROM justificacion_tipos ORDER BY id')]
    bonos = [r['nombre'] for r in await db.fetch_all(
        'SELECT b.nombre FROM area_bonos ab JOIN bonos b ON b.id = ab.bono_id JOIN areas a ON a.id = ab.area_id '
        'WHERE a.nombre = ? ORDER BY b.id', (area,))] if area else []
    if not bonos:
        bonos = list(datos.get('lista_bonos') or [])
    personas = armar_personas(datos, rs._format_concepto_cell, justif)
    out = []
    for inf in separar_informes(personas):
        out.append({'filename': nombre_archivo(area, inf, fecha_inicio, fecha_fin, preinforme), 'titulo': inf['titulo_horas'],
                    'content': render_pdf(area, fecha_inicio, fecha_fin, cerro, inf, justif, bonos, preinforme)})
    return out


async def informes_del_area(db, asistencia_service, fecha_inicio: str, fecha_fin: str, area: str) -> Dict[str, Any]:
    """Para descargar desde la app: con el área ya cerrada en ese tramo, el informe definitivo (el mismo del correo:
    un período cerrado ya no se recalcula); si no, el preinforme sin cerrar."""
    cierre = await db.fetch_one(
        "SELECT c.username, u.nombre_completo FROM cierres_periodos c LEFT JOIN usuarios u ON u.id = c.usuario_id "
        "WHERE c.area = ? AND c.fecha_inicio = ? AND c.fecha_fin = ? ORDER BY c.id DESC LIMIT 1",
        (area, fecha_inicio, fecha_fin))
    preinforme = not cierre
    cerro = '' if preinforme else ((cierre.get('nombre_completo') or cierre.get('username') or 'sistema'))
    archivos = await generar_informes_cierre(db, asistencia_service, fecha_inicio, fecha_fin, area, cerro, preinforme)
    return {'preinforme': preinforme, 'archivos': archivos}
