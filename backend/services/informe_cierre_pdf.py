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
import math
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
# Estados de un día programado y trabajado: sus horas teóricas son la base del balance (la deuda solo nace en ellos)
ESTADOS_TRABAJADOS = ('OK', 'ATRASO', 'SALIDA_ADELANTADA', 'ATR_SAD')
# Estados de justificación que la grilla muestra con su sigla aunque no traigan nomenclatura
ESTADOS_JUSTIFICADOS = {'VACACIONES', 'LICENCIA', 'LIC_COMUN', 'LIC_MUTUAL', 'LCM', 'LMU', 'CUM', 'DUE'}

# Colores de la app (frontend/css/ventanas.css)
C_NAVY, C_NAVY_SOFT, C_NAVY_RES, C_NAVY_RES_TD = '#1b2f8f', '#e9edfb', '#dfe5f8', '#f3f5fc'
C_INK, C_INK_2, C_LINE, C_LINE_2, C_ZEBRA = '#1a2233', '#4a5468', '#d9deea', '#eef1f7', '#fafbfd'
C_BAJA = '#f1f2f4'                              # fila de una baja del período
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
    out = {'trab': 0, 'aus': {}, 'per': 0, 'comp': 0, 'ina': 0, 'ano': 0, 'dias_aus': {}, 'jextra': 0, 'jextra_dias': [], 'jextra_fechas': []}
    for d in rango_dias:
        k = f'{d.year}-{d.month:02d}-{d.day:02d}'
        di = dias_dict.get(k)
        if not isinstance(di, dict):
            continue
        sigla = (etiqueta(di, es_bolsa)[0] or '').split('\n')[0].strip()
        estado = str(di.get('estado') or '')
        # Jornada extra (jornada especial validada «como jornada extra»): se paga con un monto fijo por jornada, que
        # RR.HH. tramita aparte; sus horas no entran en las horas extra (pedido de la persona dueña, 23-11-2026)
        if estado.upper() in ESTADOS_JORNADA_EXTRA:
            out['jextra'] += 1
            out['jextra_dias'].append(f'{d.day:02d}-{d.month:02d}')
            out['jextra_fechas'].append((f'{d.year}-{d.month:02d}-{d.day:02d}', estado.upper(),
                                         int(round(float(di.get('horas_trabajadas') or 0) * 3600))))
        clave = None
        if sigla in SIGLAS_TRABAJADAS:
            out['trab'] += 1
        elif sigla == 'INA':
            clave = 'ina'
        elif sigla == 'ANO' or estado.startswith('ANOMALIA'):
            clave = 'ano'
        elif sigla == 'PER':
            clave = 'per'
        elif sigla in ('COMP', 'C.HE') and estado == 'INASISTENCIA_COMPENSADA':
            clave = 'comp'
        elif sigla != 'DEOP' and (di.get('nomenclatura') or estado.upper() in ESTADOS_JUSTIFICADOS
                                  or _norm(estado) in por_clave or _norm(sigla) in por_clave):
            cod = por_clave.get(_norm(di.get('nomenclatura'))) or por_clave.get(_norm(estado)) or por_clave.get(_norm(sigla)) or sigla
            out['aus'][cod] = out['aus'].get(cod, 0) + 1
            clave = AUS + cod
        if clave:
            if clave in CLASES_DIA:
                out[clave] += 1
            out['dias_aus'][k] = clave  # día programado que la persona no trabajó, con la misma clase que su jornada
        # LIB, FER, DEOP y las jornadas en días no programados (ESP, EXT, HE, +2) no son días del balance
    return out


# Estados de un día con jornada extra de monto fijo (la jornada especial validada como jornada extra)
ESTADOS_JORNADA_EXTRA = ('EXTRA', 'FERIADO Y JORNADA EXTRA', 'DÍA LIBRE Y JORNADA EXTRA')

# Clase de un día programado no trabajado: las propias y las ausencias justificadas ('aus:' + su código)
CLASES_DIA = ('per', 'comp', 'ina', 'ano')
AUS = 'aus:'


def nombre_clase(clave: str, nombres: Dict[str, str]) -> str:
    """El nombre de una clase de día no trabajado, el mismo en jornadas y en horas. nombres: {código: nombre} de
    justificacion_tipos."""
    if clave.startswith(AUS):
        cod = clave[len(AUS):]
        return nombres.get(cod, cod)
    return {'per': 'Permisos del día', 'comp': 'Inasistencias compensadas', 'ina': 'Inasistencias',
            'ano': 'Sin resolver'}[clave]


def nombres_justif(justif: List[Dict[str, Any]]) -> Dict[str, str]:
    return {(t.get('nomenclatura') or t.get('nombre') or '').strip().upper(): (t.get('nombre') or '').strip() for t in justif}


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
         'pagar': _seg(libro.get('he_a_pagar')), 'sin_desc': _seg(libro.get('perdonado'))}
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


def pesos(n) -> str:
    """Monto en pesos chilenos: $70.000."""
    return '$' + f'{int(round(n or 0)):,}'.replace(',', '.')


def bonos_persona(ev: Dict[str, Any]):
    """Del resultado del cálculo de bonos de una persona (etapa B2 del plan de bonos, 22-11-2026):
    montos = {bono: monto a pagar, 0 si no se paga}, solo los bonos que le corresponden por sus reglas;
    detalle = {bono: {califica, monto, completo, parcial (días del período), asistidos (días asistidos), perdidos}}."""
    montos, detalle = {}, {}
    for b, v in (ev or {}).items():
        if not v or v.get('aplica') is False:
            continue
        califica = bool(v.get('califica'))
        m = int(round(v.get('monto') or 0)) if califica else 0
        asig, per = v.get('dias_asignados'), v.get('dias_periodo')
        asis, lab = v.get('dias_asistidos'), v.get('dias_laborables')
        montos[b] = m
        detalle[b] = {'califica': califica, 'monto': m, 'completo': int(round(v.get('monto_completo') or m)),
                      'parcial': (asig, per) if califica and per and asig is not None and asig != per else None,
                      'asistidos': (asis, lab) if califica and lab and asis is not None and asis != lab else None,
                      'perdidos': list(v.get('perdidos') or []),
                      # Bono semanal (Fill Rate, 23-11-2026): cada semana con su resultado, sus notas de crédito y el
                      # valor a descontar por productos (hoja Fill Rate del cierre)
                      'semanas': list(v.get('semanas') or []) if v.get('semanal') else None,
                      'notas': list(v.get('notas_credito') or []) if v.get('semanal') else [],
                      'descuento': int(v.get('descuento_productos') or 0) if v.get('semanal') else 0}
    return montos, detalle


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
             'activo': r.get('activo') != 'NO', 'baja': e.get('baja_periodo'), 'tipo': 'BOLSA' if es_bolsa else 'CICLO',
             'horario': e.get('turno') or 'Sin horario asignado', 'cargo': e.get('cargo') or '',
             'horas': float(e['meta_horas_semanales']) if e.get('turno') and e.get('meta_horas_semanales') is not None else None,
             'n_atr': int(r.get('cnt_atr') or 0), 'n_sad': int(r.get('cnt_sad') or 0),
             }
        p['bonos'], p['bonos_det'] = bonos_persona(r.get('bonos'))
        p.update(dias_persona(dd, datos['rango_dias'], es_bolsa, etiqueta, justif))
        p.update(horas_bolsa(r) if es_bolsa else horas_ciclo(r.get('libro') or {}))
        if not es_bolsa:
            hd_ = horas_dias(dd, datos['rango_dias'])
            p['h_trab_dias'], p['h_otros'] = hd_['trab'], hd_['otros']
            p.update(horas_ausencias(dd, p['dias_aus']))
            p['he_dia'] = he_por_dia(dd, datos['rango_dias'])
            p['he_mas2'] = he_mas2_persona(dd, datos['rango_dias'], p['he_trab'])
            # Programadas: los días trabajados y los programados que no se trabajaron (vacaciones, licencias, permisos
            # del día, inasistencias…), como las jornadas.
            p['h_prog'] = hd_['prog'] + p['h_prog_aus']
            # Lo no trabajado que no se descuenta (perdonado en el día o en el cuadre, días condonados sin minutos
            # anotados): lo que falta para que programadas − ausencias − no trabajadas dé lo trabajado en el horario.
            causas = p['atr'] + p['sad'] + p['col'] + p['h_per'] + p['otros']
            p['sin_desc'] = sin_descuento(p['h_prog'] - sum(p['h_aus'].values()), causas, p['h_trab_dias'], p['he_trab'],
                                          hd_['margen'])
        out.append(p)
    return out


def sin_descuento(prog: int, causas: int, trab: int, he: int, margen: int) -> int:
    """Lo no trabajado de una persona que no se descuenta: lo que falta para que programadas − no trabajadas dé lo
    trabajado en el horario (trabajado − horas extra). Las horas del día se guardan redondeadas (DECIMALES_HORAS) y las
    causas y horas extra salen de minutos exactos: un resto dentro de ese redondeo no es tiempo de nadie y es 0. Tampoco
    es negativo (un sobrante no es tiempo no trabajado). Se calcula persona a persona: nunca pasa a otra."""
    resto = prog - causas - (trab - he)
    return 0 if resto <= margen else resto


def horas_ausencias(dias_dict: Dict[str, Any], dias_aus: Dict[str, str]) -> Dict[str, Any]:
    """Segundos de los días programados que la persona no trabajó, por clase (la de sus jornadas).
    'h_prog_aus': lo programado esos días. 'h_aus': {clase: segundos} sin lo que el libro ya cuenta como no trabajado
    ese día (una inasistencia con deuda queda en sus causas, no dos veces). 'aus_dias': [(fecha, clase, segundos)]."""
    from backend.services.cuadre_service import plegar_libro
    prog, h_aus, aus_dias = 0, {}, []
    for k, clave in dias_aus.items():
        di = dias_dict.get(k) or {}
        teo = int(round(float(di.get('horas_teoricas') or 0.0) * 3600))
        if teo <= 0:
            continue
        en_causas = _seg(sum((plegar_libro([dict(di, fecha=k)]).get('causas') or {}).values()))
        s = max(teo - en_causas, 0)
        prog += teo
        if s:
            h_aus[clave] = h_aus.get(clave, 0) + s
            aus_dias.append((k, clave, s))
    return {'h_prog_aus': prog, 'h_aus': h_aus, 'aus_dias': aus_dias}


def he_por_dia(dias_dict: Dict[str, Any], rango_dias: List) -> Dict[str, int]:
    """Segundos de horas extra trabajadas de cada día, con la misma cuenta del libro mayor (plegar_libro)."""
    from backend.services.cuadre_service import plegar_libro
    out = {}
    for d in rango_dias:
        k = f'{d.year}-{d.month:02d}-{d.day:02d}'
        di = dias_dict.get(k)
        if isinstance(di, dict):
            s = _seg(plegar_libro([dict(di, fecha=k)]).get('he_trabajadas'))
            if s:
                out[k] = s
    return out


def he_mas2_persona(dias_dict: Dict[str, Any], rango_dias: List, he_trab: int) -> int:
    """Segundos de las horas extra trabajadas que vienen de un +2 (cobertura o segunda jornada) o de un llamado de
    emergencia (dueño, 10-11-2026): van dentro de las horas extra, y el informe las muestra aparte. Nunca pasan de las
    horas extra de la persona."""
    tot = 0
    for d in rango_dias:
        di = dias_dict.get(f'{d.year}-{d.month:02d}-{d.day:02d}')
        if isinstance(di, dict):
            tot += _seg(float(di.get('minutos_extra_mas2') or 0.0) + float(di.get('minutos_extra_llamado') or 0.0))
    return min(tot, he_trab)


def coberturas(ps: List[Dict[str, Any]]) -> Dict[str, int]:
    """Cuánto de cada clase de ausencia cubrieron los compañeros con horas extra (dueño, 09-11-2026): el día en que
    alguien del informe (misma área y tipo de horario) no trabajó un turno programado, las horas extra de los demás
    ese mismo día lo cubren, hasta lo programado del ausente; lo que sobra queda fuera de lo programado.
    Devuelve {clase: segundos cubiertos}."""
    por_fecha: Dict[str, List] = {}
    for i, p in enumerate(ps):
        for f, clave, s in p.get('aus_dias') or []:
            por_fecha.setdefault(f, []).append((p.get('nombre') or '', i, clave, s))
    cub: Dict[str, int] = {}
    for f in sorted(por_fecha):
        ausentes = por_fecha[f]
        idx = {i for _, i, _, _ in ausentes}
        disponible = sum((p.get('he_dia') or {}).get(f, 0) for i, p in enumerate(ps) if i not in idx)
        for _, _, clave, s in sorted(ausentes):
            c = min(s, disponible)
            disponible -= c
            if c:
                cub[clave] = cub.get(clave, 0) + c
    return cub


# Horas trabajadas en días que no son de horario: entran al balance después de las horas extra
OTROS_DIAS = {'JORNADA_COMPENSATORIA': 'Jornadas compensatorias', 'INASISTENCIA_COMPENSADA': 'Jornadas compensatorias',
              'JORNADA_ESPECIAL': 'Jornadas especiales', 'EXTRA': 'Jornadas especiales', 'FERIADO Y JORNADA EXTRA': 'Jornadas especiales',
              'DÍA LIBRE Y JORNADA EXTRA': 'Jornadas especiales', 'PERMISO': 'Días con permiso'}


def horas_dias(dias_dict: Dict[str, Any], rango_dias: List) -> Dict[str, Any]:
    """Segundos del período, desde la misma matriz: programados y trabajados en los días con horario trabajados, y lo
    trabajado en los demás días (jornadas compensatorias, especiales, días con permiso u otros).
    'margen': los segundos que puede desviarse la suma por el redondeo con que se guardan las horas de cada día."""
    from backend.services.quantum_matrix_engine import DECIMALES_HORAS
    prog = trab = 0.0
    n = 0
    otros: Dict[str, float] = {}
    for d in rango_dias:
        di = dias_dict.get(f'{d.year}-{d.month:02d}-{d.day:02d}')
        if not isinstance(di, dict):
            continue
        est = di.get('estado') or ''
        h = float(di.get('horas_trabajadas') or 0.0)
        if est in ESTADOS_TRABAJADOS:
            prog += float(di.get('horas_teoricas') or 0.0)
            trab += h
            n += 1
        elif h > 0:
            k = OTROS_DIAS.get(est, 'Otros días trabajados')
            otros[k] = otros.get(k, 0.0) + h
    margen = math.ceil(n * 0.5 * 10 ** -DECIMALES_HORAS * 3600)
    return {'prog': int(round(prog * 3600)), 'trab': int(round(trab * 3600)),
            'otros': {k: int(round(v * 3600)) for k, v in otros.items()}, 'margen': margen}


def pct(parte: float, total: float) -> str:
    return '' if not total else f'{parte / total * 100:.2f}'.replace('.', ',') + ' %'


def resumen_tipo(inf: Dict[str, Any], justif: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Resumen ejecutivo de un tipo de horario (paso 5 del cierre y correo): un balance que parte de las horas
    totales y termina en lo que se carga, cada parte con su porcentaje. Filas: {t, v, q, c} (texto, HH:MM:SS, %, clase).
    Ciclo: programadas (días trabajados y programados no trabajados) − ausencias − no trabajadas (por causa y «sin descuento»)
    = trabajadas en el horario; + horas extra (las que cubren ausencias de compañeros y las de fuera de lo programado)
    = total en el reloj. Bolsa: meta − no usadas + sobre la meta = trabajadas."""
    ps = inf['personas']
    T = lambda k: sum(p.get(k, 0) for p in ps)
    n = len(ps)
    cuenta = lambda k: sum(1 for p in ps if p.get(k))
    fila = lambda t, v, base, c='', signo='': {'t': t, 'v': (signo + hms(v)) if v else '—',
                                              'q': ('100 %' if c == 'base' else pct(v, base)) if base else '', 'c': c}
    # jornadas (días)
    aus = {}
    for p in ps:
        for cod, k in p['aus'].items():
            aus[cod] = aus.get(cod, 0) + k
    nombres = nombres_justif(justif)
    prog_d = sum(p['trab'] + sum(p['aus'].values()) + sum(p[c] for c in CLASES_DIA) for p in ps)
    qd = lambda k: pct(k, prog_d)
    jornadas = ([{'t': 'Programadas', 'v': str(prog_d), 'q': '100 %', 'c': 'base'}]
                + [{'t': nombre_clase(AUS + cod, nombres), 'v': f'− {k}', 'q': qd(k), 'c': ''} for cod, k in aus.items()]
                + [{'t': nombre_clase(c, nombres), 'v': f'− {T(c)}', 'q': qd(T(c)), 'c': ''} for c in CLASES_DIA if T(c)]
                + [{'t': 'Trabajadas', 'v': str(T('trab')), 'q': qd(T('trab')), 'c': 'tot'}])
    out = {'tipo': inf['tipo'], 'titulo': inf['titulo_horas'], 'personas': n, 'bajas': bajas_de(ps),
           'texto_personas': texto_dotacion(n, bajas_de(ps)), 'jornadas': jornadas}
    if inf['tipo'] == 'BOLSA':
        meta = T('meta')
        sobre = sum(max(p['acum'] - p['meta'], 0) for p in ps)
        nou = sum(max(p['meta'] - p['acum'], 0) for p in ps)
        out['balance'] = [fila('Meta del tramo', meta, meta, 'base'), fila('Bajo la meta · no usadas', nou, meta, 'menos', '− '),
                          fila('Sobre la meta', sobre, meta, 'menos', '+ '), fila('Trabajadas', meta - nou + sobre, meta, 'tot')]
        out['cargar'] = [{'t': 'Pagar horas extra', 'v': hms(T('pagar')), 'c': 'he', 'q': pct(T('pagar'), meta) + ' de la meta' if meta else '',
                          'n': f"{cuenta('pagar')} de {n} personas"},
                         {'t': 'No usadas · no se descuentan', 'v': hms(nou), 'c': 'nu', 'q': pct(nou, meta) + ' de la meta' if meta else '',
                          'n': f"{cuenta('no_usadas')} de {n} personas"}]
        if T('jextra'):
            out['cargar'].append({'t': 'Jornadas extra · monto fijo', 'v': str(T('jextra')), 'c': 'he', 'q': '',
                                  'n': f"{cuenta('jextra')} de {n} personas"})
        out['de_donde'] = []
        out['quienes'] = [{'t': 'A quién se pagan horas extra', 'c': 'he', 'filas': _quienes(ps, 'pagar')}]
        return out
    base = T('h_prog')
    sin = T('sin_desc')
    causas = [['Atrasos', T('atr')], ['Salidas anticipadas', T('sad')], ['Colación', T('col')], ['Permisos', T('h_per')], ['Otros', T('otros')]]
    causas = [(t, v) for t, v in causas] + [('Sin descuento', sin)]
    nt = sum(v for _, v in causas)
    he = T('he_trab')
    # Ausencias (días programados no trabajados) por clase, en el orden de las jornadas, y lo que cubrieron los
    # compañeros con horas extra
    h_aus: Dict[str, int] = {}
    for p in ps:
        for c, v in (p.get('h_aus') or {}).items():
            h_aus[c] = h_aus.get(c, 0) + v
    orden_aus = [AUS + cod for cod in aus] + list(CLASES_DIA)
    clases_aus = [c for c in orden_aus if h_aus.get(c)] + [c for c in h_aus if c not in orden_aus and h_aus[c]]
    ta = sum(h_aus.values())
    cub = coberturas(ps)
    tc = min(sum(cub.values()), he)
    otros = {}
    for p in ps:
        for k, v in (p.get('h_otros') or {}).items():
            otros[k] = otros.get(k, 0) + v
    orden = ['Jornadas compensatorias', 'Jornadas especiales', 'Días con permiso', 'Otros días trabajados']
    filas_otros = [fila(f'Horas en {k[0].lower() + k[1:]}', otros[k], base, 'menos', '+ ') for k in orden if otros.get(k)]
    total = base - ta - nt + he + sum(otros.values())
    out['balance'] = ([fila('Programadas', base, base, 'base')]
                      + ([fila('Ausencias', ta, base, 'menos', '− ')] + [fila(nombre_clase(c, nombres), h_aus[c], base, 'det')
                                                                           for c in clases_aus] if ta else [])
                      + [fila('Horas no trabajadas', nt, base, 'menos', '− ')]
                      + [fila(t, v, base, 'det') for t, v in causas if v]
                      + [fila('Trabajadas en el horario', base - ta - nt, base, 'tot'), fila('Horas extra trabajadas', he, base, 'menos', '+ ')]
                      + ([fila('Cubren ausencias de compañeros', tc, base, 'det'), fila('Fuera de lo programado', he - tc, base, 'det')]
                         if tc else [])
                      + ([fila('Incluye de +2 y llamados', min(T('he_mas2'), he), base, 'det')] if T('he_mas2') else [])
                      + filas_otros + [fila('Total en el reloj', total, base, 'tot')])
    out['cargar'] = [{'t': 'Descontar', 'v': hms(T('descontar')), 'c': 'ds', 'q': pct(T('descontar'), base) + ' de lo programado' if base else '',
                      'n': f"{cuenta('descontar')} de {n} personas"},
                     {'t': 'Pagar horas extra', 'v': hms(T('pagar')), 'c': 'he', 'q': pct(T('pagar'), base) + ' de lo programado' if base else '',
                      'n': f"{cuenta('pagar')} de {n} personas"}]
    if T('jextra'):
        out['cargar'].append({'t': 'Jornadas extra · monto fijo', 'v': str(T('jextra')), 'c': 'he', 'q': '',
                              'n': f"{cuenta('jextra')} de {n} personas"})
    nt_rows = ([fila('Sin descuento', sin, nt)] if sin else []) \
        + ([fila('Inasistencias compensadas', T('comp_inas'), nt)] if T('comp_inas') else []) \
        + [fila('Se cubren con horas extra', T('cubren'), nt), fila('Se descuentan', T('descontar'), nt, 'tot')]
    he_rows = ([fila('No aprobadas', T('he_noap'), he)] if T('he_noap') else []) \
        + ([fila('Por decidir', T('he_decidir'), he)] if T('he_decidir') else []) \
        + ([fila('Compensan inasistencias', T('he_inas'), he)] if T('he_inas') else []) \
        + [fila('Cubren descuentos', T('cubren'), he), fila('Se pagan', T('pagar'), he, 'tot')]
    aus_rows = []
    for c in clases_aus:
        nom, v, k = nombre_clase(c, nombres), h_aus[c], min(cub.get(c, 0), h_aus[c])
        aus_rows += [f for f in (fila(f'{nom} · cubiertas con horas extra', k, ta), fila(f'{nom} · sin cubrir', v - k, ta))
                     if f['v'] != '—']
    out['de_donde'] = ([{'t': f'De las {hms(ta)} de ausencias', 'filas': aus_rows}] if ta else []) \
        + ([{'t': f'De las {hms(nt)} no trabajadas', 'filas': nt_rows}] if nt else []) \
        + ([{'t': f'De las {hms(he)} horas extra', 'filas': he_rows}] if he else [])
    out['quienes'] = [{'t': 'A quién se descuenta', 'c': 'ds', 'filas': _quienes(ps, 'descontar')},
                      {'t': 'A quién se pagan horas extra', 'c': 'he', 'filas': _quienes(ps, 'pagar')}]
    return out


def _quienes(ps, k):
    return [{'t': p['nombre'].title(), 'v': hms(p[k])} for p in sorted((p for p in ps if p.get(k)), key=lambda p: -p[k])]


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
        if hay(lambda p: p.get('he_mas2')): C.append(col(g, 'De +2 y EME', lambda p: p.get('he_mas2', 0), 'h', 'cp'))
        if hay(lambda p: p['he_noap']): C.append(col(g, 'No aprobadas', lambda p: -p['he_noap'], 'h', 'cp'))
        if hay(lambda p: p['he_decidir']): C.append(col(g, 'Por decidir', lambda p: -p['he_decidir'], 'h', 'al'))
        if hay(lambda p: p['he_inas']): C.append(col(g, 'Compensan inas.', lambda p: -p['he_inas'], 'h', 'cp'))
        C.append(col(g, 'Cubren descuentos', lambda p: -p['cubren'], 'h', 'cp'))
        C += [col('A cargar', 'Descontar', lambda p: p['descontar'], 'h', 'tot', True),
              col('A cargar', 'Pagar', lambda p: p['pagar'], 'h', 'he', True)]
    # Jornadas extra de monto fijo (23-11-2026): cuántas hizo cada persona, para que RR.HH. las tramite
    if hay(lambda p: p.get('jextra')):
        C.append(col('A cargar', 'Jornadas extra', lambda p: p.get('jextra', 0), 'n', 'he', True))
    # Bonos (etapa B2 del plan de bonos): el monto a pagar de cada bono que le corresponde a alguien del informe, según
    # las reglas de cada bono (decisión de la persona dueña, 22-11-2026: «que se muestre todo lo que corresponde»)
    bonos_inf = [b for b in bonos if any(b in p['bonos'] for p in ps)]
    for b in bonos_inf:
        C.append(dict(col('Bonos', b, (lambda b: lambda p: p['bonos'].get(b))(b), 'm'), bono=b))
    if bonos_inf:
        C.append(col('Bonos', 'Total', lambda p: sum(p['bonos'].values()) if p['bonos'] else None, 'm', 'bal', True))
    return C


def leyenda(inf: Dict[str, Any], justif: List[Dict[str, Any]], cols: List[Dict[str, Any]]) -> List[str]:
    titulos = {c['titulo'] for c in cols}
    hay_bonos = any(c['fmt'] == 'm' for c in cols)
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
              + (' <b>Otros</b>: jornada incompleta que no es atraso, salida, colación ni permiso.' if 'Otros' in titulos else '')
              + (' <b>De +2 y EME</b>: parte de las horas extra trabajadas que viene de un +2 o de un llamado de emergencia '
                 '(no se resta, ya está dentro de ellas).' if 'De +2 y EME' in titulos else ''))
    out = [l1, l2 + ' El detalle día a día está en el Excel del cierre, que se descarga desde la aplicación.']
    if bajas_de(inf['personas']):
        out = list(out) + ['<b>Bajas del período</b>: personas que se van en este período (renuncia, despido, mutuo acuerdo o no renovar), con la fecha de su salida. Van al final de su horario, se pagan y descuentan como el resto y no cuentan en la dotación.']
    if 'Jornadas extra' in titulos:
        out = list(out) + ['<b>Jornadas extra</b>: jornadas especiales validadas como jornada extra; se pagan con un monto fijo por jornada y sus horas no van en las horas extra. Los días están en «Jornadas extra (monto fijo)».']
    semanales = sorted({b for p in inf['personas'] for b, d in (p.get('bonos_det') or {}).items() if d.get('semanas') is not None})
    if semanales:
        out = list(out) + [f'<b>{_y(semanales)}</b>: bono semanal, de lunes a domingo; cada semana se paga en el período donde cae su domingo y un día que no cumple hace perder la semana completa. Las semanas que no se pagan o se pagan en parte están en el detalle de bonos.']
    if hay_bonos:
        out = list(out) + ['<b>Bonos</b> en pesos: el monto a pagar; <b>—</b> no se paga (el motivo va en el detalle de bonos); en blanco, no le corresponde.']
    return out


def bajas_de(ps: List[Dict[str, Any]]) -> int:
    """Cuántas personas de la lista son bajas del período."""
    return sum(1 for p in ps if p.get('baja'))


def texto_dotacion(n: int, nb: int) -> str:
    """«12 en dotación · 2 bajas» (o «14 personas» si no hay bajas): las bajas del período se pagan y descuentan como
    el resto, pero no cuentan en la dotación (dueño, 23-11-2026)."""
    if not nb:
        return f'{n} {"persona" if n == 1 else "personas"}'
    return f'{n - nb} en dotación · {nb} {"baja" if nb == 1 else "bajas"}'


def rotulo_baja(p: Dict[str, Any]) -> str:
    return f'Baja {_dm(p["baja"])}' if p.get('baja') else ''


def resumen(inf: Dict[str, Any]) -> List[tuple]:
    """Cifras del resumen de arriba: (texto antes, cifra, texto después, alerta)."""
    ps = inf['personas']
    T = lambda k: sum(p[k] for p in ps)
    nb = bajas_de(ps)
    out = ([('', str(len(ps) - nb), ' en dotación', False), ('', str(nb), ' baja del período' if nb == 1 else ' bajas del período', False)]
           if nb else [('', str(len(ps)), ' persona' if len(ps) == 1 else ' personas', False)])
    if inf['tipo'] == 'BOLSA':
        out += [('Horas extra a pagar ', hms(T('pagar')), '', False), ('Horas no usadas ', hms(T('no_usadas')), ' · no se descuentan', False)]
    else:
        out += [('Horas a descontar ', hms(T('descontar')), '', False), ('Horas extra a pagar ', hms(T('pagar')), '', False),
                ('Horas extra que cubren descuentos ', hms(T('cubren')), '', False)]
        if T('he_decidir'):
            out.append(('', hms(T('he_decidir')), ' de horas extra sin decidir', True))
    jx = sum(p.get('jextra', 0) for p in ps)
    if jx:
        out.append(('Jornadas extra ', str(jx), ' · monto fijo', False))
    if any(p.get('bonos') for p in ps):
        out.append(('Bonos a pagar ', pesos(sum(sum(p['bonos'].values()) for p in ps)), '', False))
    ano = T('ano')
    if ano:
        out.append(('', str(ano), ' jornada sin resolver' if ano == 1 else ' jornadas sin resolver', True))
    return out


def _y(nombres: List[str]) -> str:
    return nombres[0] if len(nombres) == 1 else ', '.join(nombres[:-1]) + ' y ' + nombres[-1]


def detalle_bonos(inf: Dict[str, Any]) -> Dict[str, List[str]]:
    """Detalle de bonos del informe (etapa B2): por persona, los que no se pagan con su motivo (causa y días) y los que
    se pagan en parte, con los días que cuentan. Texto con <b> para el PDF."""
    no_pagados, en_parte = [], []
    for p in inf['personas']:
        det = p.get('bonos_det') or {}
        por_motivo = OrderedDict()
        for b, d in det.items():
            if d['califica'] or d.get('semanas') is not None:
                continue
            causas = OrderedDict()
            for x in d['perdidos']:
                causas.setdefault(x['causa'], []).append(_dm(x['fecha']))
            motivo = '; '.join(f'{c} el {_y(f)}' for c, f in causas.items()) or 'sin días que cuenten'
            por_motivo.setdefault(motivo, []).append(b)
        for motivo, bs in por_motivo.items():
            no_pagados.append(f'<b>{p["nombre"]}</b>: {_y(bs)}. {motivo[0].upper() + motivo[1:]}.')
        # Bono semanal: qué semanas no se pagan o se pagan en parte, con sus días
        for b, d in det.items():
            semanas = d.get('semanas')
            if semanas is None:
                continue
            perdidas = [s for s in semanas if s['estado'] == 'pierde']
            parciales = [s for s in semanas if s['estado'] == 'proporcional']
            if not perdidas and not parciales:
                continue
            textos = []
            for s in perdidas:
                causas = OrderedDict()
                for x in s.get('perdidos') or []:
                    causas.setdefault(x['causa'], []).append(_dm(x['fecha']))
                textos.append(f'no se paga la semana del {_dm(s["desde"])} al {_dm(s["hasta"])} ('
                              + '; '.join(f'{c[0].lower() + c[1:]} el {_y(f)}' for c, f in causas.items()) + ')')
            for s in parciales:
                textos.append(f'la semana del {_dm(s["desde"])} al {_dm(s["hasta"])} se paga en parte: {pesos(s["monto"])} de '
                              f'{pesos(s["monto_completo"])}' + (f' ({s["dias_proporcion"]} de {s["dias_turno"]} días en proporción)'
                                                                if s.get("dias_proporcion") else ''))
            linea = f'<b>{p["nombre"]}</b>: {b} {pesos(d["monto"])} de {pesos(d["completo"])}: {"; ".join(textos)}.'
            (en_parte if d['monto'] else no_pagados).append(linea)
        for b, d in det.items():
            if d['califica'] and (d['parcial'] or d['asistidos']):
                partes = []
                if d['parcial']:
                    partes.append(f'{d["parcial"][0]} de {d["parcial"][1]} días de turno del período')
                if d['asistidos']:
                    partes.append(f'{d["asistidos"][0]} de {d["asistidos"][1]} días asistidos')
                en_parte.append(f'<b>{p["nombre"]}</b>: {b} {pesos(d["monto"])} de {pesos(d["completo"])}, por {" y ".join(partes)}.')
    return {'no_pagados': no_pagados, 'en_parte': en_parte}


def hoja_fill_rate(inf: Dict[str, Any]) -> List[Dict[str, Any]]:
    """La hoja Fill Rate del cierre (dueño, 23-11-2026), una por bono semanal: por persona, lo ganado en cada semana, el
    total y el valor a descontar por productos; y el detalle de las notas de crédito del tramo (número, razón, efecto,
    quiénes iban en el camión y descuento). El descuento va aparte: no se resta del bono."""
    nombres = {p['emp_id']: p['nombre'] for p in inf['personas']}
    hojas = OrderedDict()
    for p in inf['personas']:
        for b, d in (p.get('bonos_det') or {}).items():
            if d.get('semanas') is None:
                continue
            h = hojas.setdefault(b, {'bono': b, 'semanas': [], 'filas': [], 'notas': [], 'sin_numero': 0})
            if len(d['semanas']) > len(h['semanas']):
                h['semanas'] = [(s['desde'], s['hasta']) for s in d['semanas']]
            celdas = {}
            for s in d['semanas']:
                if s['estado'] == 'pierde':
                    x = (s.get('perdidos') or [{}])[0]
                    # La causa tal como la dio la evaluación: «No cumple», una licencia, una inasistencia…
                    causa = str(x.get('causa') or 'No se paga').split(':')[0]
                    texto, nota = '$0', (f'{causa} {_dm(x["fecha"])}' if x.get('fecha') else causa)
                elif s['estado'] == 'proporcional':
                    texto = pesos(s['monto'])
                    nota = f'{s["dias_turno"] - s.get("dias_proporcion", 0)} de {s["dias_turno"]} días'
                elif s['estado'] == 'en_curso':
                    texto, nota = '$0', 'En curso'
                elif s['estado'] == 'por_evaluar':
                    # Días trabajados sin marcar «Cumple» o «No cumple»: el preinforme la muestra pendiente; el cierre no se
                    # puede hacer así (dueño, 23-11-2026)
                    nf = len(s.get('faltan') or [])
                    texto, nota = 'Pendiente', f'Faltan {nf} {"día" if nf == 1 else "días"}'
                elif s['estado'] == 'sin_turno':
                    texto, nota = '—', 'Sin turno'
                else:
                    texto, nota = pesos(s['monto']), ''
                celdas[s['desde']] = {'estado': s['estado'], 'texto': texto, 'nota': nota}
            h['filas'].append({'emp_id': p['emp_id'], 'rut': p['rut'], 'nombre': p['nombre'], 'cargo': p.get('cargo') or '',
                               'celdas': celdas, 'total': int(d['monto'] or 0), 'descuento': int(d.get('descuento') or 0)})
            for n in d.get('notas') or []:
                if n.get('rol') != 'chofer':
                    continue
                # Marcadas antes de pedir el número (23-11-2026): están en la fila del chofer y de cada peoneta, sin saber
                # quién iba con quién; no se listan (saldrían repetidas), se cuentan para completarlas
                if not n.get('numero'):
                    h['sin_numero'] += 1
                    continue
                if n.get('culpa'):
                    efecto = 'Pierde la semana y descuenta' if n.get('descuenta') else 'Pierde la semana'
                else:
                    efecto = 'Descuenta' if n.get('descuenta') else 'No afecta'
                quienes = [p['nombre']] + [nombres.get(x, 'peoneta de otra área') for x in n.get('peonetas_ids') or []]
                h['notas'].append({'fecha': n['fecha'], 'numero': n.get('numero') or 'sin número', 'razon': n.get('razon') or '',
                                   'efecto': efecto, 'quienes': quienes,
                                   'monto': int(round(n.get('monto') or 0)) if n.get('descuenta') else 0})
    for h in hojas.values():
        h['notas'].sort(key=lambda x: (x['fecha'], x['numero']))
        h['total_bono'] = sum(f['total'] for f in h['filas'])
        h['total_descuento'] = sum(f['descuento'] for f in h['filas'])
        h['n_notas'] = len(h['notas'])
        h['n_descuentan'] = sum(1 for x in h['notas'] if x['monto'])
    return list(hojas.values())


def _dm(fecha: str) -> str:
    return f'{fecha[8:10]}-{fecha[5:7]}'


def _cuantos(n: int, uno: str, varios: str) -> str:
    return f'1 {uno}' if n == 1 else f'{n} {varios}'


def para_coordinar(inf: Dict[str, Any], fecha_fin: str, hoy: str) -> List[str]:
    """Avisos del preinforme para que la jefatura coordine con cada persona antes del cierre (frases aprobadas por la
    persona dueña, 18 y 21-11-2026). Texto con <b> para el PDF; las cifras en HH:MM:SS.

    Ciclo Inteligente: quién debe horas que se van a descontar (atrasos, salidas adelantadas…) y quién tiene
    inasistencias sin justificar. Las horas extra del mismo tramo pagan primero la deuda.
    Bolsa Flexible: las horas bajo la meta no se descuentan, así que el aviso es quién va bajo la meta (horas que todavía
    se pueden programar) y quién ya la pasó (desde ahí se pagan como horas extra).
    Quien no tiene nada que coordinar no aparece; las personas inactivas tampoco. `hoy` y `fecha_fin` en AAAA-MM-DD."""
    from xml.sax.saxutils import escape
    corte = min(hoy, fecha_fin)
    fin = _dm(fecha_fin)
    activos = [p for p in inf['personas'] if p.get('activo', True) and not p.get('baja')]
    quien = lambda p: f'<b>{escape(p["nombre"])}</b> ({escape(p["horario"])})'
    out = []
    if inf['tipo'] == 'BOLSA':
        bajo = sorted((p for p in activos if p.get('meta') and p['acum'] < p['meta']), key=lambda p: p['acum'] - p['meta'])
        sobre = sorted((p for p in activos if p.get('meta') and p['acum'] > p['meta']), key=lambda p: p['meta'] - p['acum'])
        for p in bajo:
            out.append(f'{quien(p)} lleva <b>{hms(p["acum"])}</b> de <b>{hms(p["meta"])}</b> al {_dm(corte)}. Le quedan '
                       f'<b>{hms(p["meta"] - p["acum"])}</b> de bolsa hasta el {fin}, que se pueden programar con la persona.')
        for p in sobre:
            out.append(f'{quien(p)} ya pasó la meta: lleva <b>{hms(p["acum"])}</b> de <b>{hms(p["meta"])}</b>. Desde aquí, '
                       'cada hora se paga como hora extra. Coordinar si hace falta.')
        return out
    for p in sorted((p for p in activos if p.get('descontar', 0) > 0), key=lambda p: -p['descontar']):
        causas = [x for x in (_cuantos(p.get('n_atr', 0), 'atraso', 'atrasos') if p.get('n_atr') else '',
                              _cuantos(p.get('n_sad', 0), 'salida adelantada', 'salidas adelantadas') if p.get('n_sad') else '') if x]
        det = f' ({" y ".join(causas)})' if causas else ''
        out.append(f'{quien(p)} debe <b>{hms(p["descontar"])}</b> al {_dm(corte)}{det}. Se recomienda coordinar con la '
                   f'persona para que recupere esas horas antes del cierre del {fin}, quedándose después de su salida: '
                   'esas horas extra pagan primero la deuda del tramo.')
    for p in activos:
        ina = sorted(k for k, clase in (p.get('dias_aus') or {}).items() if clase == 'ina')
        if not ina:
            continue
        cuando = (f'una inasistencia el {_dm(ina[0])}' if len(ina) == 1
                  else f'{len(ina)} inasistencias ({", ".join(_dm(k) for k in ina[:-1])} y {_dm(ina[-1])})')
        out.append(f'{quien(p)} tiene {cuando} sin justificar. Se puede compensar con una jornada extra o con horas extra '
                   'del mismo tramo, o justificar, antes del cierre.')
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
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether, PageBreak

    _registrar_fuentes()
    H = colors.HexColor
    ancho_pag, alto_pag = landscape(A4)
    mx = 20
    util = ancho_pag - 2 * mx
    fmt_f = lambda f: datetime.strptime(f, '%Y-%m-%d').strftime('%d-%m-%Y')
    emision = datetime.now().strftime('%d-%m-%Y %H:%M')
    ps = inf['personas']
    cols = columnas(inf, justif, bonos)
    nb_inf = bajas_de(ps)
    texto_total = f'Total · {len(ps)} {"persona" if len(ps) == 1 else "personas"}' + (f' ({len(ps) - nb_inf} en dotación + {nb_inf} {"baja" if nb_inf == 1 else "bajas"})'
                                                     if nb_inf else '')

    # ── texto de cada celda (con la tabla muy ancha, los montos van sin «$» y el grupo dice «Bonos ($)»)
    sin_signo = {'si': False}
    monto_txt = lambda v: pesos(v)[1:] if sin_signo['si'] else pesos(v)
    def txt(c, p):
        v = c['valor'](p)
        if c['fmt'] == 'b':
            return bool(v)
        if c['fmt'] == 'h':
            return hms(v)
        if c['fmt'] == 'm':
            return '' if v is None else ('—' if not v else monto_txt(v))
        return '—' if not v else str(v)

    def txt_total(c):
        if c['fmt'] == 'b':
            return str(sum(1 for p in ps if c['valor'](p)))
        if c['fmt'] == 'm':
            s = sum(c['valor'](p) or 0 for p in ps)
            return monto_txt(s) if s else '—'
        s = sum(c['valor'](p) for p in ps)
        return hms(s) if c['fmt'] == 'h' else ('—' if not s else str(s))

    grupos_hor = OrderedDict()
    for p in ps:
        grupos_hor.setdefault(p['horario'], []).append(p)
    # Propuesta B (dueño, 23-11-2026): las bajas del período van al final de su horario, bajo «Bajas del período»
    for k_hor in grupos_hor:
        grupos_hor[k_hor] = [p for p in grupos_hor[k_hor] if not p.get('baja')] + [p for p in grupos_hor[k_hor] if p.get('baja')]

    # ── anchos: el mayor texto de cada columna. Si la tabla no cabe en la hoja se va ajustando, de menos a más
    # (23-11-2026: con los montos de bonos y las jornadas extra, Producción se salía de la hoja): primero los títulos
    # pasan a dos líneas, después baja la letra, después los nombres largos se parten en dos líneas y al final se
    # achica el relleno de las celdas
    def medir(cuerpo, pad, titulos_partidos, tope_nombre):
        cab = cuerpo - 1.3
        # (+1 punto: sin ese margen el párrafo del título corta la palabra que mide justo el ancho de la columna)
        ancho_t = lambda t: 1 + (max(stringWidth(w, _f('BarlowSC-SemiBold'), cab) for w in t.upper().split())
                                 if titulos_partidos else stringWidth(t.upper(), _f('BarlowSC-SemiBold'), cab))
        w_rut = max([ancho_t('RUT')] + [stringWidth(p['rut'], _f('Barlow'), cuerpo) for p in ps])
        badge = max([stringWidth(rotulo_baja(p), _f('Barlow-SemiBold'), cuerpo - 1.4) for p in ps if p.get('baja')] or [0]) + 8
        # La fila de total ocupa RUT y Nombre juntas: al nombre solo le toca lo que el RUT no alcanza a cubrir
        w_total = stringWidth(texto_total, _f('Barlow-Bold'), cuerpo) - w_rut - 2 * pad
        w_nom = max([ancho_t('NOMBRE'), w_total]
                    + [stringWidth(p['nombre'], _f('Barlow-Medium'), cuerpo) + (badge if p.get('baja') else 0) for p in ps])
        if tope_nombre:
            largo_palabra = max([w_total] + [stringWidth(w, _f('Barlow-Medium'), cuerpo) for p in ps for w in p['nombre'].split()])
            w_nom = max(largo_palabra, w_nom * tope_nombre)
        ws = [w_rut + 2 * pad, w_nom + 2 * pad]
        for c in cols:
            w = ancho_t(c['titulo'])
            if c['fmt'] == 'b':
                w = max(w, 9)
            else:
                w = max([w, stringWidth(txt_total(c), _f('Barlow-Bold'), cuerpo)] + [stringWidth(txt(c, p), _f('Barlow-Bold'), cuerpo) for p in ps])
            ws.append(w + 2 * pad)
        return ws
    pasos = [(7.8, 2.6, False, None), (7.8, 2.6, True, None)]
    pasos += [(round(7.6 - 0.2 * i, 1), 2.6, True, None) for i in range(12)]            # letra de 7,6 a 5,4
    pasos += [(5.4, 2.6, True, t) for t in (0.8, 0.65, 0.55)]                          # nombres en dos líneas
    pasos += [(5.4, p, True, 0.55) for p in (2.0, 1.5, 1.2)]                           # menos relleno
    pasos += [(c, 1.2, True, 0.55, True) for c in (5.4, 5.2, 5.0)]                    # montos sin «$» y letra hasta 5
    for paso in pasos:
        cuerpo, pad, titulos_partidos, tope_nombre = paso[:4]
        sin_signo['si'] = len(paso) > 4
        anchos = medir(cuerpo, pad, titulos_partidos, tope_nombre)
        if sum(anchos) <= util:
            break
    if sum(anchos) > util:
        logger.warning(f'[InformeCierre] la tabla no cabe en la hoja ({sum(anchos):.0f} de {util:.0f} puntos)')
    if sum(anchos) < util:                      # el espacio que sobra va al nombre
        anchos[1] += util - sum(anchos)
    cab = cuerpo - 1.3

    st_nom = ParagraphStyle('nom', fontName=_f('Barlow-Medium'), fontSize=cuerpo, leading=cuerpo + 1.5, textColor=H(C_INK))
    st_hor = ParagraphStyle('hor', fontName=_f('BarlowSC-Bold'), fontSize=cuerpo + 1.2, leading=cuerpo + 3, textColor=H(C_NAVY))
    st_bajas = ParagraphStyle('bajas', fontName=_f('BarlowSC-Bold'), fontSize=cuerpo - 0.3, leading=cuerpo + 2, textColor=H(C_INK_2))

    # ── filas
    spans, prev, primeros = [], None, set()
    for i, c in enumerate(cols):
        if c['grupo'] != prev:
            spans.append([c['grupo'], i, i]); primeros.add(i + 2); prev = c['grupo']
        spans[-1][2] = i
    fila_g = ['', ''] + [''] * len(cols)
    for g, a, b in spans:
        fila_g[a + 2] = (g + ' ($)' if g == 'Bonos' and sin_signo['si'] else g).upper()
    # Títulos como párrafos: si hace falta, pasan a dos líneas dentro del ancho de su columna
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    st_tit = lambda al: ParagraphStyle('tit' + str(al), fontName=_f('BarlowSC-SemiBold'), fontSize=cab, leading=cab + 1.2,
                                       textColor=H(C_NAVY), alignment=al)
    st_grupo = ParagraphStyle('grp', fontName=_f('BarlowSC-SemiBold'), fontSize=cab - 0.3, leading=cab + 0.9,
                              textColor=H(C_INK_2), alignment=TA_CENTER)
    fila_g = [Paragraph(x, st_grupo) if x else '' for x in fila_g]
    fila_h = [Paragraph('RUT', st_tit(TA_LEFT)), Paragraph('NOMBRE', st_tit(TA_LEFT))] + [
        Paragraph(c['titulo'].upper(), st_tit(TA_CENTER if c['fmt'] == 'b' else TA_RIGHT)) for c in cols]
    data = [fila_g, fila_h]
    estilo = [
        ('FONT', (0, 0), (-1, 0), _f('BarlowSC-SemiBold'), cab - 0.3), ('TEXTCOLOR', (0, 0), (-1, 0), H(C_INK_2)),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONT', (0, 1), (-1, 1), _f('BarlowSC-SemiBold'), cab), ('TEXTCOLOR', (0, 1), (-1, 1), H(C_NAVY)),
        ('BACKGROUND', (0, 1), (-1, 1), H(C_NAVY_SOFT)), ('LINEBELOW', (0, 1), (-1, 1), 0.8, H(C_NAVY)),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), pad), ('RIGHTPADDING', (0, 0), (-1, -1), pad),
        ('TOPPADDING', (0, 0), (-1, -1), 2.6), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.6), ('VALIGN', (0, 1), (-1, 1), 'BOTTOM'),
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
                               f'{horas_txt(hh) + " · " if hh else ""}{texto_dotacion(len(gp), bajas_de(gp))}</font>', st_hor)]
                    + [''] * (len(cols) + 1))
        estilo += [('SPAN', (0, fila), (-1, fila)), ('LINEBELOW', (0, fila), (-1, fila), 0.8, H(C_NAVY)),
                   ('TOPPADDING', (0, fila), (-1, fila), 7), ('BOTTOMPADDING', (0, fila), (-1, fila), 2)]
        fila += 1
        titulo_bajas = False
        for k, p in enumerate(gp):
            if p.get('baja') and not titulo_bajas:
                titulo_bajas = True
                nb_g = bajas_de(gp)
                data.append([Paragraph(f'Bajas del período · {nb_g} {"persona" if nb_g == 1 else "personas"}'
                                       f'<font name="{_f("Barlow")}" size="{cuerpo}" color="{C_INK_2}">&nbsp;&nbsp;se pagan y descuentan '
                                       'como el resto; no cuentan en la dotación</font>', st_bajas)] + [''] * (len(cols) + 1))
                estilo += [('SPAN', (0, fila), (-1, fila)), ('LINEBELOW', (0, fila), (-1, fila), 0.6, H(C_INK_2)),
                           ('TOPPADDING', (0, fila), (-1, fila), 7), ('BOTTOMPADDING', (0, fila), (-1, fila), 2)]
                fila += 1
            nom = p['nombre'] if not p.get('baja') else (
                f'{p["nombre"]} <font name="{_f("Barlow-SemiBold")}" size="{cuerpo - 1.4}" color="#FFFFFF" backColor="{C_INK_2}">'
                f'&nbsp;{rotulo_baja(p)}&nbsp;</font>')
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
                no_pagado = c.get('bono') and not ((p.get('bonos_det') or {}).get(c['bono']) or {}).get('califica', True)
                if no_pagado:
                    estilo += [('TEXTCOLOR', (x, fila), (x, fila), H(C_PINK)), ('FONT', (x, fila), (x, fila), _f('Barlow-Bold'), cuerpo)]
                elif t == '—':
                    estilo.append(('TEXTCOLOR', (x, fila), (x, fila), H(C_CERO)))
                elif c['color']:
                    estilo.append(('TEXTCOLOR', (x, fila), (x, fila), H(colores[c['color']])))
                    if c['color'] in negrita:
                        estilo.append(('FONT', (x, fila), (x, fila), _f('Barlow-Bold'), cuerpo))
                if c['res']:
                    estilo.append(('BACKGROUND', (x, fila), (x, fila), H(C_NAVY_RES_TD)))
            if k % 2 == 1:
                estilo.append(('BACKGROUND', (0, fila), (1, fila), H(C_ZEBRA)))
            if p.get('baja'):
                estilo.append(('BACKGROUND', (0, fila), (-1, fila), H(C_BAJA)))
            estilo.append(('LINEBELOW', (0, fila), (-1, fila), 0.4, H(C_LINE_2)))
            data.append(celdas)
            fila += 1
    data.append([texto_total, ''] + [txt_total(c) for c in cols])
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
    # Los recuadros pasan a otra fila cuando no caben en el ancho de la hoja (23-11-2026)
    filas_chips, fila_act, ancho_act = [], [], 0.0
    for i in range(0, len(chips), 2):
        if fila_act and ancho_act + anchos_chip[i] + 5 > util:
            filas_chips.append(fila_act); fila_act, ancho_act = [], 0.0
        fila_act.append(i // 2)
        ancho_act += anchos_chip[i] + 5
    if fila_act:
        filas_chips.append(fila_act)
    bloques_chips = []
    for fila_i in filas_chips:
        celdas, anchos_f, est_f = [], [], []
        for j, k in enumerate(fila_i):
            a, num, b, alerta = lista_resumen[k]
            celdas += [chips[2 * k], '']
            anchos_f += [anchos_chip[2 * k], 5]
            est_f.append(('BOX', (2 * j, 0), (2 * j, 0), 0.6, H(C_PINK if alerta else C_LINE)))
            if alerta:
                est_f.append(('BACKGROUND', (2 * j, 0), (2 * j, 0), H(C_PINK_SOFT)))
        tc = Table([celdas], colWidths=anchos_f, hAlign='LEFT')
        tc.setStyle(TableStyle(est_f + [('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                                        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
        bloques_chips.append(tc)
    t_chips = bloques_chips[0] if len(bloques_chips) == 1 else Table([[b] for b in bloques_chips], hAlign='LEFT',
                                                                      style=[('LEFTPADDING', (0, 0), (-1, -1), 0),
                                                                             ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                                                                             ('TOPPADDING', (0, 0), (-1, -1), 0),
                                                                             ('BOTTOMPADDING', (0, 0), (-1, -1), 4)])

    st_ley = ParagraphStyle('l', fontName=_f('Barlow'), fontSize=7.2, leading=10, textColor=H(C_INK_2))
    firmas = Table([['Jefatura del área', '', 'Recursos Humanos · recibido', '', 'Cargado en remuneraciones · fecha']],
                   colWidths=[(util - 60) / 3, 30, (util - 60) / 3, 30, (util - 60) / 3])
    firmas.setStyle(TableStyle([('FONT', (0, 0), (-1, -1), _f('Barlow'), 7.8), ('TEXTCOLOR', (0, 0), (-1, -1), H(C_INK)),
                                ('LINEABOVE', (0, 0), (0, 0), 0.8, H(C_INK)), ('LINEABOVE', (2, 0), (2, 0), 0.8, H(C_INK)),
                                ('LINEABOVE', (4, 0), (4, 0), 0.8, H(C_INK)), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                ('TOPPADDING', (0, 0), (-1, -1), 3)]))

    historia = [enc, Spacer(1, 8), t_chips, Spacer(1, 6), tabla, Spacer(1, 7)]
    historia += [Paragraph(x, st_ley) for x in leyenda(inf, justif, cols)]
    # Jornadas extra (monto fijo) en una tabla (dueño, 23-11-2026: la lista era poco práctica): una fila por persona y una
    # columna por cada fecha con jornada extra (fecha completa y día de la semana); en la celda, las horas de esa jornada.
    # Si las fechas no caben en el ancho de la hoja, la tabla sigue debajo con las fechas que faltan
    con_jx = [p for p in inf['personas'] if p.get('jextra')]
    if con_jx:
        st_jx_t = ParagraphStyle('jxt', fontName=_f('BarlowSC-Bold'), fontSize=10.5, leading=13, textColor=H(C_NAVY), keepWithNext=1)
        st_jx_n = ParagraphStyle('jxn', fontName=_f('Barlow-Medium'), fontSize=7.6, leading=9.5, textColor=H(C_INK))
        st_jx_c = ParagraphStyle('jxc', fontName=_f('BarlowSC-SemiBold'), fontSize=6.8, leading=8.4, textColor=H(C_NAVY))
        st_jx_cr = ParagraphStyle('jxcr', parent=st_jx_c, alignment=2)
        st_jx_cc = ParagraphStyle('jxcc', parent=st_jx_c, alignment=1)
        dias_sem = ('LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM')
        # horas y tipo de cada persona en cada fecha
        celdas_p = {p['emp_id']: {x[0]: (x[2] if len(x) > 2 else 0, x[1]) for x in (p.get('jextra_fechas') or [])} for p in con_jx}
        fechas_jx = sorted({x[0] for p in con_jx for x in (p.get('jextra_fechas') or [])})
        # Feriado o día libre va en el encabezado de la fecha, con la palabra completa (dueño, 23-11-2026): «FERIADO» si
        # la jornada de esa fecha fue en feriado; «DÍA LIBRE» solo si fue día libre para todas las personas de esa fecha
        def tipo_fecha(iso):
            tipos = {c[iso][1] for c in celdas_p.values() if iso in c}
            if 'FERIADO Y JORNADA EXTRA' in tipos:
                return 'FERIADO'
            if tipos == {'DÍA LIBRE Y JORNADA EXTRA'}:
                return 'DÍA LIBRE'
            return ''
        w_rut_jx = max(stringWidth(p['rut'], _f('Barlow'), 7.6) for p in con_jx) + 8
        w_nom_jx = min(max(stringWidth(p['nombre'], _f('Barlow-Medium'), 7.6) for p in con_jx) + 8, 170)
        w_n_jx, w_h_jx, w_f_jx = 44, 52, 50
        por_tabla = max(1, int((util - w_rut_jx - w_nom_jx - w_n_jx - w_h_jx) // w_f_jx))
        bloques_jx = [fechas_jx[i:i + por_tabla] for i in range(0, len(fechas_jx), por_tabla)] or [[]]
        tablas_jx = []
        for nb_, fechas_b in enumerate(bloques_jx):
            ultimo = nb_ == len(bloques_jx) - 1
            cab = [Paragraph('RUT', st_jx_c), Paragraph('NOMBRE', st_jx_c)]
            for iso in fechas_b:
                dt = datetime.strptime(iso, '%Y-%m-%d')
                t_f = tipo_fecha(iso)
                cab.append(Paragraph((f'<font color="{C_AMBER}">{t_f}</font><br/>' if t_f else '')
                                     + f'{dias_sem[dt.weekday()]}<br/>{dt.strftime("%d-%m-%Y")}', st_jx_cc))
            if ultimo:
                cab += [Paragraph('JORNADAS', st_jx_cr), Paragraph('HORAS', st_jx_cr)]
            filas_jx = [cab]
            for p in con_jx:
                c = celdas_p[p['emp_id']]
                fila = [p['rut'], Paragraph(p['nombre'], st_jx_n)]
                for iso in fechas_b:
                    if iso in c:
                        seg, t = c[iso]
                        fila.append(hms(seg) if seg else 'Sí')
                    else:
                        fila.append('')
                if ultimo:
                    fila += [str(p['jextra']), hms(sum(v[0] for v in c.values()))]
                filas_jx.append(fila)
            tot = [f'Total · {len(con_jx)} {"persona" if len(con_jx) == 1 else "personas"}', '']
            for iso in fechas_b:
                n_ = sum(1 for c in celdas_p.values() if iso in c)
                tot.append(f'{n_} · {hms(sum(c[iso][0] for c in celdas_p.values() if iso in c))}' if n_ else '')
            if ultimo:
                tot += [str(sum(p['jextra'] for p in con_jx)), hms(sum(v[0] for c in celdas_p.values() for v in c.values()))]
            filas_jx.append(tot)
            anchos_jx = [w_rut_jx, w_nom_jx] + [w_f_jx] * len(fechas_b) + ([w_n_jx, w_h_jx] if ultimo else [])
            t_jx = Table(filas_jx, colWidths=anchos_jx, repeatRows=1, hAlign='LEFT')
            est_jx = [('FONT', (0, 1), (-1, -1), _f('Barlow'), 7.6), ('TEXTCOLOR', (0, 1), (-1, -1), H(C_INK)),
                      ('BACKGROUND', (0, 0), (-1, 0), H(C_NAVY_SOFT)), ('LINEBELOW', (0, 0), (-1, 0), 0.8, H(C_NAVY)),
                      ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
                      ('ALIGN', (2, 1), (-1, -1), 'CENTER'),
                      ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                      ('TOPPADDING', (0, 0), (-1, -1), 2.6), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.6),
                      ('SPAN', (0, -1), (1, -1)), ('FONT', (0, -1), (-1, -1), _f('Barlow-Bold'), 7.2),
                      ('LINEABOVE', (0, -1), (-1, -1), 1.1, H(C_INK))]
            for x in range(2, 2 + len(fechas_b)):
                est_jx.append(('LINEBEFORE', (x, 0), (x, -1), 0.4, H(C_LINE)))
            if ultimo:
                est_jx += [('ALIGN', (-2, 1), (-1, -1), 'RIGHT'), ('LINEBEFORE', (-2, 0), (-2, -1), 0.6, H(C_LINE)),
                           ('FONT', (-2, 1), (-1, -2), _f('Barlow-Bold'), 7.6)]
            for k in range(1, len(filas_jx) - 1):
                est_jx.append(('LINEBELOW', (0, k), (-1, k), 0.4, H(C_LINE_2)))
                if k % 2 == 0:
                    est_jx.append(('BACKGROUND', (0, k), (-1, k), H(C_ZEBRA)))
            t_jx.setStyle(TableStyle(est_jx))
            tablas_jx += [t_jx, Spacer(1, 6)]
        st_jx_l = ParagraphStyle('jxl', fontName=_f('Barlow'), fontSize=7.4, leading=9.5, textColor=H(C_INK_2))
        nota_jx = 'En cada fecha, las horas de esa jornada extra. La fila Total dice cuántas personas y cuántas horas hubo cada día.'
        historia += [Spacer(1, 10), Paragraph('Jornadas extra (monto fijo)', st_jx_t), Spacer(1, 4)] + tablas_jx + [Paragraph(nota_jx, st_jx_l)]
    det_b = detalle_bonos(inf)
    if det_b['no_pagados'] or det_b['en_parte']:
        st_db_t = ParagraphStyle('dbt', fontName=_f('BarlowSC-Bold'), fontSize=10.5, leading=13, textColor=H(C_NAVY))
        st_db_s = ParagraphStyle('dbs', fontName=_f('Barlow-SemiBold'), fontSize=8.3, leading=11, textColor=H(C_INK))
        st_db = ParagraphStyle('db', fontName=_f('Barlow'), fontSize=8.3, leading=11, textColor=H(C_INK), leftIndent=8,
                               bulletIndent=0, spaceAfter=2)
        historia += [Spacer(1, 10), Paragraph('Detalle de bonos', st_db_t), Spacer(1, 3)]
        for titulo_db, lineas in (('No se pagan', det_b['no_pagados']), ('Se pagan en parte', det_b['en_parte'])):
            if lineas:
                historia += [KeepTogether([Paragraph(titulo_db, st_db_s), Paragraph(lineas[0], st_db, bulletText='•')])]
                historia += [Paragraph(x, st_db, bulletText='•') for x in lineas[1:]]
    if preinforme:
        avisos = para_coordinar(inf, fecha_fin, datetime.now().strftime('%Y-%m-%d'))
        if avisos:
            st_av_t = ParagraphStyle('avt', fontName=_f('BarlowSC-Bold'), fontSize=10.5, leading=13, textColor=H(C_NAVY))
            st_av = ParagraphStyle('av', fontName=_f('Barlow'), fontSize=8.3, leading=11, textColor=H(C_INK), leftIndent=8,
                                   bulletIndent=0, spaceAfter=2.5)
            historia += [Spacer(1, 12), KeepTogether([Paragraph('Para coordinar antes del cierre', st_av_t), Spacer(1, 4),
                                                      Paragraph(avisos[0], st_av, bulletText='•')])]
            historia += [Paragraph(x, st_av, bulletText='•') for x in avisos[1:]]
    if not preinforme:
        historia += [Spacer(1, 26), KeepTogether([firmas])]

    # ── Hoja Fill Rate (dueño, 23-11-2026): en una página aparte, distinta del resumen
    for hoja in hoja_fill_rate(inf):
        st_fr_t = ParagraphStyle('frt', fontName=_f('BarlowSC-Bold'), fontSize=13, leading=16, textColor=H(C_NAVY))
        st_fr_s = ParagraphStyle('frs', fontName=_f('Barlow'), fontSize=8.3, leading=10.5, textColor=H(C_INK_2))
        st_fr_c = ParagraphStyle('frc', fontName=_f('Barlow-SemiBold'), fontSize=7.4, leading=8.8, textColor=H(C_INK_2))
        st_fr_n = ParagraphStyle('frn', fontName=_f('Barlow'), fontSize=7.6, leading=9.2, textColor=H(C_INK))
        st_fr_v = ParagraphStyle('frv', fontName=_f('Barlow'), fontSize=7.6, leading=9.2, textColor=H(C_INK), alignment=1)
        st_fr_h = ParagraphStyle('frh', fontName=_f('BarlowSC-Bold'), fontSize=10.5, leading=13, textColor=H(C_NAVY))
        semanas_h = hoja['semanas']
        cab = [Paragraph('RUT', st_fr_c), Paragraph('NOMBRE', st_fr_c), Paragraph('CARGO', st_fr_c)]
        cab += [Paragraph(f'SEMANA<br/>{_dm(a)} AL {_dm(b)}', st_fr_c) for a, b in semanas_h]
        cab += [Paragraph('BONO', st_fr_c), Paragraph('A DESCONTAR', st_fr_c)]
        filas_fr = [cab]
        for f in hoja['filas']:
            fila = [f['rut'], Paragraph(f['nombre'], st_fr_n), Paragraph(f['cargo'], st_fr_n)]
            for a, _b in semanas_h:
                c = f['celdas'].get(a)
                if not c:
                    fila.append('')
                    continue
                color = C_PINK if c['estado'] == 'pierde' else C_INK
                fila.append(Paragraph(f'<font color="{color}">{c["texto"]}</font>' + (f'<br/><font size="6.6" color="{C_INK_2 if c["estado"] != "pierde" else C_PINK}">{c["nota"]}</font>' if c['nota'] else ''), st_fr_v))
            fila += [pesos(f['total']) if f['total'] else '—', pesos(f['descuento']) if f['descuento'] else '—']
            filas_fr.append(fila)
        n_fr = len(hoja['filas'])
        filas_fr.append([f'Total · {n_fr} {"persona" if n_fr == 1 else "personas"}', '', ''] + [''] * len(semanas_h)
                        + [pesos(hoja['total_bono']) if hoja['total_bono'] else '—',
                           pesos(hoja['total_descuento']) if hoja['total_descuento'] else '—'])
        w_rut, w_car, w_mon = 62, 70, 66
        w_sem = 64
        w_nom = max(120, util - w_rut - w_car - 2 * w_mon - w_sem * len(semanas_h))
        if w_nom + w_rut + w_car + 2 * w_mon + w_sem * len(semanas_h) > util:
            w_sem = max(44, (util - w_rut - w_car - 2 * w_mon - 120) / max(1, len(semanas_h)))
            w_nom = util - w_rut - w_car - 2 * w_mon - w_sem * len(semanas_h)
        t_fr = Table(filas_fr, colWidths=[w_rut, w_nom, w_car] + [w_sem] * len(semanas_h) + [w_mon, w_mon], repeatRows=1, hAlign='LEFT')
        est_fr = [('FONT', (0, 1), (-1, -1), _f('Barlow'), 7.6), ('TEXTCOLOR', (0, 1), (-1, -1), H(C_INK)),
                  ('BACKGROUND', (0, 0), (-1, 0), H(C_NAVY_SOFT)), ('LINEBELOW', (0, 0), (-1, 0), 0.8, H(C_NAVY)),
                  ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
                  ('ALIGN', (-2, 1), (-1, -1), 'RIGHT'), ('TEXTCOLOR', (-1, 1), (-1, -1), H(C_PINK)),
                  ('FONT', (-2, 1), (-1, -1), _f('Barlow-Bold'), 7.6),
                  ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                  ('TOPPADDING', (0, 0), (-1, -1), 2.6), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.6),
                  ('SPAN', (0, -1), (2 + len(semanas_h), -1)), ('FONT', (0, -1), (-1, -1), _f('Barlow-Bold'), 7.4),
                  ('LINEABOVE', (0, -1), (-1, -1), 1.1, H(C_INK)), ('LINEBEFORE', (-2, 0), (-2, -1), 0.6, H(C_LINE))]
        for x in range(3, 3 + len(semanas_h)):
            est_fr.append(('LINEBEFORE', (x, 0), (x, -1), 0.4, H(C_LINE)))
        for k in range(1, len(filas_fr) - 1):
            est_fr.append(('LINEBELOW', (0, k), (-1, k), 0.4, H(C_LINE_2)))
            if k % 2 == 0:
                est_fr.append(('BACKGROUND', (0, k), (-1, k), H(C_ZEBRA)))
        t_fr.setStyle(TableStyle(est_fr))
        sub = (f'Período {fmt_f(fecha_inicio)} al {fmt_f(fecha_fin)} · cada semana va de lunes a domingo y se paga en el período '
               f'donde cae su domingo. El valor a descontar por productos va aparte: no se resta del bono.')
        historia += [PageBreak(), Paragraph(f'{hoja["bono"]} · {(area or "Todas").title()} · {inf["titulo_horas"]}', st_fr_t),
                     Spacer(1, 2), Paragraph(sub, st_fr_s), Spacer(1, 8), t_fr]
        resumen_fr = (f'Bono a pagar: <b>{pesos(hoja["total_bono"])}</b> · A descontar por productos: '
                      f'<b><font color="{C_PINK}">{pesos(hoja["total_descuento"])}</font></b> · Notas de crédito: <b>{hoja["n_notas"]}</b>'
                      + (f' ({hoja["n_descuentan"]} {"descuenta" if hoja["n_descuentan"] == 1 else "descuentan"})' if hoja['n_descuentan'] else ''))
        if hoja['sin_numero']:
            resumen_fr += (f' · <font color="{C_PINK}">{hoja["sin_numero"]} {"día marcado" if hoja["sin_numero"] == 1 else "días marcados"} con nota de '
                           f'crédito sin número (marcados antes de pedirlo, en la fila del chofer y de sus peonetas): conviene completarlos en la grilla</font>')
        historia += [Spacer(1, 6), Paragraph(resumen_fr, st_fr_s)]
        if hoja['notas']:
            cab_n = [Paragraph(x, st_fr_c) for x in ('FECHA', 'N° NOTA', 'RAZÓN', 'EFECTO', 'QUIÉNES IBAN', 'DESCUENTO')]
            filas_n = [cab_n] + [[_dm(x['fecha']), Paragraph(x['numero'], st_fr_n), Paragraph(x['razon'], st_fr_n),
                                  Paragraph(f'<font color="{C_PINK if x["efecto"] != "No afecta" else C_INK_2}">{x["efecto"]}</font>', st_fr_n),
                                  Paragraph(', '.join(x['quienes']), st_fr_n), pesos(x['monto']) if x['monto'] else '—']
                                 for x in hoja['notas']]
            anchos_n = [46, 70, 150, 110, util - 46 - 70 - 150 - 110 - 70, 70]
            t_n = Table(filas_n, colWidths=anchos_n, repeatRows=1, hAlign='LEFT')
            est_n = [('FONT', (0, 1), (-1, -1), _f('Barlow'), 7.6), ('BACKGROUND', (0, 0), (-1, 0), H(C_NAVY_SOFT)),
                     ('LINEBELOW', (0, 0), (-1, 0), 0.8, H(C_NAVY)), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                     ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'), ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                     ('TOPPADDING', (0, 0), (-1, -1), 2.4), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.4)]
            for k in range(1, len(filas_n)):
                est_n.append(('LINEBELOW', (0, k), (-1, k), 0.4, H(C_LINE_2)))
            t_n.setStyle(TableStyle(est_n))
            historia += [Spacer(1, 12), KeepTogether([Paragraph('Notas de crédito del tramo', st_fr_h), Spacer(1, 4), t_n])]

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

async def _personas_del_area(db, asistencia_service, fecha_inicio: str, fecha_fin: str, area: str):
    from backend.services.report_service import ReportService
    rs = ReportService(asistencia_service)
    datos = await rs.datos_periodo(fecha_inicio, fecha_fin, area)
    justif = [dict(r) for r in await db.fetch_all('SELECT nombre, nomenclatura FROM justificacion_tipos ORDER BY id')]
    # Todos los bonos activos, en su orden; el informe muestra los que les corresponden a sus personas (etapa B2)
    bonos = [r['nombre'] for r in await db.fetch_all(
        "SELECT nombre FROM bonos WHERE activo = 1 AND COALESCE(tipo, 'pesos') <> 'beneficio' ORDER BY id")]
    if not bonos:
        bonos = list(datos.get('lista_bonos') or [])
    return armar_personas(datos, rs._format_concepto_cell, justif), justif, bonos


async def resumen_del_area(db, asistencia_service, fecha_inicio: str, fecha_fin: str, area: str) -> List[Dict[str, Any]]:
    """El resumen ejecutivo del área, uno por tipo de horario (paso 5 del cierre)."""
    personas, justif, _ = await _personas_del_area(db, asistencia_service, fecha_inicio, fecha_fin, area)
    return [resumen_tipo(inf, justif) for inf in separar_informes(personas)]


async def cierre_completo(db, asistencia_service, fecha_inicio: str, fecha_fin: str, area: str, cerro: str) -> Dict[str, Any]:
    """Para el correo de cierre, con un solo cálculo: los PDF y el resumen de cada tipo de horario."""
    personas, justif, bonos = await _personas_del_area(db, asistencia_service, fecha_inicio, fecha_fin, area)
    infs = separar_informes(personas)
    return {'archivos': [{'tipo': inf['tipo'], 'filename': nombre_archivo(area, inf, fecha_inicio, fecha_fin), 'titulo': inf['titulo_horas'],
                          'content': render_pdf(area, fecha_inicio, fecha_fin, cerro, inf, justif, bonos)} for inf in infs],
            'resumen': [resumen_tipo(inf, justif) for inf in infs]}


async def generar_informes_cierre(db, asistencia_service, fecha_inicio: str, fecha_fin: str, area: str, cerro: str,
                                  preinforme: bool = False, tipo: Optional[str] = None,
                                  solo_lista: bool = False) -> List[Dict[str, Any]]:
    """Los PDF del cierre de un área: [{'tipo', 'filename', 'titulo', 'content'}], uno por tipo de horario.
    tipo ('CICLO' | 'BOLSA') deja solo ese informe; solo_lista no dibuja los PDF (content None)."""
    personas, justif, bonos = await _personas_del_area(db, asistencia_service, fecha_inicio, fecha_fin, area)
    out = []
    for inf in separar_informes(personas):
        if tipo and inf['tipo'] != tipo:
            continue
        out.append({'tipo': inf['tipo'], 'filename': nombre_archivo(area, inf, fecha_inicio, fecha_fin, preinforme),
                    'titulo': inf['titulo_horas'],
                    'content': None if solo_lista else render_pdf(area, fecha_inicio, fecha_fin, cerro, inf, justif, bonos, preinforme)})
    return out


async def informes_del_area(db, asistencia_service, fecha_inicio: str, fecha_fin: str, area: str,
                            tipo: Optional[str] = None, solo_lista: bool = False) -> Dict[str, Any]:
    """Para descargar desde la app: con el área ya cerrada en ese tramo, el informe definitivo (el mismo del correo:
    un período cerrado ya no se recalcula); si no, el preinforme sin cerrar."""
    cierre = await db.fetch_one(
        "SELECT c.username, u.nombre_completo FROM cierres_periodos c LEFT JOIN usuarios u ON u.id = c.usuario_id "
        "WHERE c.area = ? AND c.fecha_inicio = ? AND c.fecha_fin = ? ORDER BY c.id DESC LIMIT 1",
        (area, fecha_inicio, fecha_fin))
    preinforme = not cierre
    cerro = '' if preinforme else ((cierre.get('nombre_completo') or cierre.get('username') or 'sistema'))
    archivos = await generar_informes_cierre(db, asistencia_service, fecha_inicio, fecha_fin, area, cerro, preinforme,
                                             tipo=tipo, solo_lista=solo_lista)
    return {'preinforme': preinforme, 'archivos': archivos}
