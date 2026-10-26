"""Libro mayor de minutos: cuadre de deuda, horas extra y perdonazos de una persona en un tramo.

Regla del dueño (25-10-2026): cada minuto tiene un solo destino y las sumas siempre cuadran.
  Deuda        = perdonada + cubierta con horas extra + pendiente
  Horas extra  = usadas (para cubrir deuda o una inasistencia) + a pagar + no pagadas + por decidir
  Saldo        = a pagar − pendiente
La deuda se cubre primero con las horas extra aprobadas; lo que sobra se paga. Dentro del tramo el orden de los días
no importa («lo que debo hoy lo pago mañana»). Entre tramos no hay arrastre: lo que no se pagó en el tramo no se paga.

Tres capas:
  · hechos: los días que calculó el motor (tabla asistencias), se recalculan solos con cada marca nueva;
  · decisiones: perdonazos por día, excepciones por día y la POLÍTICA del tramo de cada persona
    («llevar todo a cero» o «pagar horas extra: tantas»), que la aplicación vuelve a repartir cada vez
    que cambian los hechos;
  · estado derivado: este libro, que grilla, ventana de cuadre, cierre y Excel deben leer por igual.
"""
import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

TOLERANCIA_MIN = 0.05           # diferencia que se acepta en una identidad (redondeos de segundos)
ESTADOS_ESPECIALES = ('JORNADA_ESPECIAL', 'EXTRA', 'FERIADO Y JORNADA EXTRA', 'DÍA LIBRE Y JORNADA EXTRA')
POLITICAS = ('CERO', 'PAGAR')

# Personas cuya política se está reaplicando en este momento (evita que un recálculo disparado por el propio
# reparto vuelva a disparar el reparto).
_REAPLICANDO: Set[int] = set()


def _f(v: Any) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def hhmmss(minutos: float) -> str:
    """Minutos (con decimales) → H:MM:SS, con signo si es negativo."""
    seg = int(round(abs(float(minutos or 0.0)) * 60))
    h, r = divmod(seg, 3600)
    m, s = divmod(r, 60)
    signo = '-' if (minutos < 0 and seg > 0) else ''
    return f"{signo}{h}:{m:02d}:{s:02d}"


def es_dia_especial(di: Dict[str, Any], es_bolsa: bool) -> bool:
    """Mismo criterio que la grilla, el cierre y el Excel para dejar fuera del cuadre una jornada especial."""
    estado = di.get('estado') or ''
    return estado in ESTADOS_ESPECIALES or (
        not es_bolsa and _f(di.get('horas_teoricas')) == 0.0 and _f(di.get('horas_trabajadas')) > 0.0
    )


# ── Causas de la deuda (reglas del dueño, 26-10-2026) ─────────────────────────────────────────────
# Toda deuda se paga con horas extra, en este orden: exceso de colación (y lo que no tiene causa), permisos, atrasos y
# salidas adelantadas; las inasistencias compensables van al final. Solo se perdonan atrasos y salidas adelantadas, de
# cualquier tamaño (también los segundos que caen dentro del margen del horario); el exceso de colación y los permisos
# no se perdonan nunca.
ORDEN_PAGO = ('otra', 'colacion', 'permiso', 'atraso', 'salida')
CAUSAS_PERDONABLES = ('atraso', 'salida')
CAUSAS_VACIAS = {'deuda': 0.0, 'colacion': 0.0, 'permiso': 0.0, 'atraso': 0.0, 'salida': 0.0, 'otra': 0.0,
                 'atraso_marcado': 0.0, 'salida_marcada': 0.0}


def _minutos_del_dia(hora: Any) -> Optional[float]:
    """'HH:MM' o 'HH:MM:SS' → minutos desde la medianoche (con segundos)."""
    try:
        partes = str(hora).strip().split(' ')[-1].split(':')
        if len(partes) < 2:
            return None
        h, m = int(partes[0]), int(partes[1])
        s = float(partes[2]) if len(partes) > 2 and partes[2] else 0.0
        return h * 60 + m + s / 60.0
    except (TypeError, ValueError):
        return None


def causas_dia(di: Dict[str, Any]) -> Dict[str, float]:
    """
    Divide la deuda neta de un día (la que dejó el motor después de los perdonazos del interruptor) en sus causas.
    La suma de colacion + permiso + atraso + salida + otra es siempre la deuda neta del día. Función pura.
      · atraso/salida: los minutos marcados por el motor más los segundos de llegar tarde o salir antes que caen dentro
        del margen (el motor no los marca, pero el día sí los debe);
      · si el mismo día la persona compensó parte (se quedó más), lo compensado paga primero lo que no se perdona, igual
        que el interruptor: lo perdonable del día es min(deuda, atraso + salida).
      · atraso_marcado / salida_marcada: la parte que borra la marca del interruptor (sin los segundos del margen).
    """
    cond = int(_f(di.get('deuda_condonada')))
    neta = 0.0 if cond == 5 else _f(di.get('minutos_deuda'))
    if neta <= 0.0:
        return dict(CAUSAS_VACIAS)
    atr = 0.0 if cond in (2, 3) else _f(di.get('minutos_atraso'))
    sal = 0.0 if cond in (1, 3) else _f(di.get('minutos_salida_adelantada'))
    col = _f(di.get('minutos_exceso_colacion'))
    per = max(_f(di.get('minutos_permisos_detectados')), _f(di.get('minutos_permiso_personal_deuda')))
    resto = max(0.0, neta - atr - sal - col - per)
    seg_a = seg_s = 0.0
    if resto > 0.0:
        if atr <= 0.0 and cond not in (2, 3):
            e_real, e_teo = _minutos_del_dia(di.get('hora_entrada_real')), _minutos_del_dia(di.get('hora_entrada_teorica'))
            if e_real is not None and e_teo is not None and 0.0 < e_real - e_teo < 60.0:
                seg_a = min(resto, e_real - e_teo)
        if sal <= 0.0 and cond not in (1, 3):
            s_real, s_teo = _minutos_del_dia(di.get('hora_salida_real')), _minutos_del_dia(di.get('hora_salida_teorica'))
            if s_real is not None and s_teo is not None and 0.0 < s_teo - s_real < 60.0:
                seg_s = min(resto - seg_a, s_teo - s_real)
    perdonable = min(neta, atr + seg_a + sal + seg_s)
    atraso = min(perdonable, atr + seg_a)
    salida = perdonable - atraso
    no_perdonable = neta - perdonable
    colacion = min(no_perdonable, col)
    permiso = min(no_perdonable - colacion, per)
    otra = no_perdonable - colacion - permiso
    return {'deuda': neta, 'colacion': colacion, 'permiso': permiso, 'atraso': atraso, 'salida': salida, 'otra': otra,
            'atraso_marcado': min(atraso, atr), 'salida_marcada': min(salida, sal)}


def plegar_libro(dias: List[Dict[str, Any]], es_bolsa: bool = False, tolerancia_min: float = 0.0,
                 perdon_cuadre: float = 0.0, hay_politica: bool = False,
                 guiados: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Pliega los días de una persona en los totales del libro. Función pura: solo lee los dicts.
      tolerancia_min: deuda de un día por debajo de este valor se deja pasar (se informa como «tolerado»).
      perdon_cuadre:  minutos que la guía del cuadre perdonó en la cuenta del tramo (parte de un día o segundos dentro
                      del margen). Solo puede borrar atrasos y salidas pendientes, nunca colación ni permisos.
      hay_politica:   con política registrada, una aprobación parcial es una decisión, no un hallazgo.
      guiados:        {fecha: {'tipo', 'minutos_marca'}} de los perdonazos que puso la guía con la marca del interruptor.
                      Lista congelada: si después la marca borra más minutos que los aprobados (cambió una marca), el
                      exceso vuelve a ser deuda pendiente; si la marca del día ya no es la de la guía, se avisa.
    Las horas extra aprobadas pagan la deuda en el orden ORDEN_PAGO; lo que sobra compensa inasistencias (al final) y
    lo que queda se paga. Devuelve minutos (float), el detalle por causa y la lista de hallazgos del verificador.
    """
    deuda_bruta = deuda_neta = perdonado = tolerado = comp_inasistencia = 0.0
    he_trabajadas = he_aprobadas = he_no_pagadas = he_por_decidir = he_compensado = he_jornadas_especiales = 0.0
    causas = {k: 0.0 for k in ORDEN_PAGO}
    guiados = guiados or {}
    hallazgos: List[Dict[str, Any]] = []
    dias_parciales: List[str] = []
    dias_segundos: List[str] = []
    dias_perdonados: List[str] = []
    dias_aprobado_sobre_trabajado: List[str] = []
    dias_guiados_cambiados: List[str] = []
    dias_guiados_reabiertos: List[str] = []

    for di in dias:
        if not isinstance(di, dict) or not di.get('fecha'):
            continue
        fecha = str(di['fecha'])[:10]
        esp = es_dia_especial(di, es_bolsa)
        # Horas extra usadas para cubrir una inasistencia (se cuentan en todos los días, como la grilla)
        he_compensado += _f(di.get('minutos_compensados_he'))

        if esp:
            ja = di.get('jornada_adicional') or {}
            if ja.get('estado') == 'HORAS_EXTRAS':
                # Jornada adicional aprobada como horas extra: trabajada y aprobada por igual
                m = _f(ja.get('minutos_autorizados')) or _f(ja.get('minutos_trabajados'))
                he_trabajadas += m
                he_aprobadas += m
                he_jornadas_especiales += m
            continue

        cond = int(_f(di.get('deuda_condonada')))
        neta_d = 0.0 if cond == 5 else _f(di.get('minutos_deuda'))
        bruta_d = di.get('minutos_deuda_bruta')
        bruta_d = _f(bruta_d) if bruta_d is not None else neta_d
        if bruta_d < neta_d:          # días calculados antes de guardar la deuda bruta
            bruta_d = neta_d
        quitado_d = bruta_d - neta_d
        comp_d = min(_f(di.get('minutos_compensados_he')), quitado_d)
        perdonado_d = quitado_d - comp_d
        causas_d = causas_dia(di)
        g = guiados.get(fecha)
        if g and int(_f(g.get('tipo'))) > 0:
            if cond != int(_f(g.get('tipo'))):
                dias_guiados_cambiados.append(fecha)
            else:
                exceso = perdonado_d - _f(g.get('minutos_marca'))
                if exceso > TOLERANCIA_MIN:
                    # La marca borra hoy más de lo aprobado (cambió una marca): el exceso vuelve a deuda pendiente
                    dias_guiados_reabiertos.append(fecha)
                    perdonado_d -= exceso
                    neta_d += exceso
                    causas_d = dict(causas_d)
                    causas_d['atraso' if int(_f(g.get('tipo'))) in (2, 3) else 'salida'] += exceso
                    causas_d['deuda'] += exceso
        if tolerancia_min > 0 and 0.0 < neta_d <= tolerancia_min:
            tolerado += neta_d
            neta_d = 0.0
            causas_d = dict(CAUSAS_VACIAS)
        elif 0.0 < neta_d < 1.0:
            dias_segundos.append(fecha)
        for k in ORDEN_PAGO:
            causas[k] += causas_d[k]
        deuda_bruta += bruta_d
        deuda_neta += neta_d
        comp_inasistencia += comp_d
        perdonado += perdonado_d
        if perdonado_d >= 1.0:
            dias_perdonados.append(fecha)

        bruto_d = _f(di.get('minutos_extra_bruto'))
        estado_he = di.get('estado_he')
        aut_d = _f(di.get('minutos_extra_autorizados')) if estado_he == 'APROBADO' else 0.0
        if aut_d > bruto_d + TOLERANCIA_MIN:
            # Una aprobación anterior quedó por sobre lo que hoy calcula el motor (p. ej. cambió un umbral):
            # lo trabajado se cuenta como lo aprobado, igual que hace el Excel, y se avisa.
            dias_aprobado_sobre_trabajado.append(fecha)
            bruto_d = aut_d
        he_trabajadas += bruto_d
        if estado_he == 'APROBADO':
            he_aprobadas += aut_d
            resto = max(0.0, bruto_d - aut_d)
            he_no_pagadas += resto
            if resto >= 1.0 and aut_d > 0.0:
                dias_parciales.append(fecha)
        elif estado_he == 'RECHAZADO':
            he_no_pagadas += bruto_d
        elif bruto_d >= 1.0:
            he_por_decidir += bruto_d

    # Pago con horas extra sobre los totales del tramo (sin importar el orden de los días), causa por causa
    disponible = he_aprobadas
    cubierto_causa: Dict[str, float] = {}
    for k in ORDEN_PAGO:
        pago = min(disponible, causas[k])
        cubierto_causa[k] = pago
        disponible -= pago
    usadas_deuda = sum(cubierto_causa.values())
    # Inasistencias compensables al final: solo con las horas extra que sobran después de pagar toda la deuda
    comp_respaldado = min(he_compensado, disponible)
    disponible -= comp_respaldado
    if he_compensado - comp_respaldado > TOLERANCIA_MIN:
        hallazgos.append({'codigo': 'compensacion_sin_respaldo', 'detalle': f'{hhmmss(he_compensado - comp_respaldado)} compensados en inasistencias sin horas extra que sobren después de pagar la deuda'})
    a_pagar = disponible
    pendiente_causa = {k: causas[k] - cubierto_causa[k] for k in ORDEN_PAGO}
    # Perdón de la guía en la cuenta del tramo: solo atrasos y salidas, empezando por las salidas (lo último que se paga)
    perdon_aplicado = min(max(0.0, _f(perdon_cuadre)), pendiente_causa['atraso'] + pendiente_causa['salida'])
    p_sal = min(perdon_aplicado, pendiente_causa['salida'])
    pendiente_causa['salida'] -= p_sal
    pendiente_causa['atraso'] -= (perdon_aplicado - p_sal)
    pendiente = sum(pendiente_causa.values())
    saldo = a_pagar - pendiente
    if abs(sum(causas.values()) - deuda_neta) > TOLERANCIA_MIN:
        hallazgos.append({'codigo': 'causas_no_cuadran', 'detalle': f'la deuda por causa no suma la deuda del tramo por {hhmmss(sum(causas.values()) - deuda_neta)}'})
    if dias_guiados_cambiados:
        hallazgos.append({'codigo': 'perdonazo_guiado_cambiado', 'detalle': f'{len(dias_guiados_cambiados)} día(s) perdonados por el cuadre tienen hoy otra marca de perdonazo', 'dias': dias_guiados_cambiados})
    if dias_guiados_reabiertos:
        hallazgos.append({'codigo': 'perdonazo_guiado_reabierto', 'detalle': f'{len(dias_guiados_reabiertos)} día(s) perdonados por el cuadre deben hoy más que lo aprobado: la diferencia volvió a deuda', 'dias': dias_guiados_reabiertos})

    # Identidades
    perdonado_total = perdonado + tolerado + perdon_aplicado
    dif_deuda = deuda_bruta - (perdonado_total + comp_inasistencia + usadas_deuda + pendiente)
    dif_he = he_trabajadas - (comp_respaldado + usadas_deuda + a_pagar + he_no_pagadas + he_por_decidir)
    if abs(dif_deuda) > TOLERANCIA_MIN:
        hallazgos.append({'codigo': 'identidad_deuda', 'detalle': f'la deuda no cuadra por {hhmmss(dif_deuda)}'})
    if abs(dif_he) > TOLERANCIA_MIN:
        hallazgos.append({'codigo': 'identidad_horas_extra', 'detalle': f'las horas extra no cuadran por {hhmmss(dif_he)}'})
    if dias_parciales and not hay_politica:
        hallazgos.append({'codigo': 'aprobacion_parcial', 'detalle': f'{len(dias_parciales)} día(s) aprobados en parte sin decir qué pasa con el resto', 'dias': dias_parciales})
    if dias_aprobado_sobre_trabajado:
        hallazgos.append({'codigo': 'aprobado_sobre_trabajado', 'detalle': f'{len(dias_aprobado_sobre_trabajado)} día(s) con más minutos aprobados que trabajados', 'dias': dias_aprobado_sobre_trabajado})
    if dias_perdonados and a_pagar >= 1.0:
        hallazgos.append({'codigo': 'perdonazo_con_horas_a_pagar', 'detalle': f'se perdonaron {hhmmss(perdonado)} y además quedan {hhmmss(a_pagar)} de horas extra a pagar', 'dias': dias_perdonados})
    if dias_segundos:
        hallazgos.append({'codigo': 'deuda_de_segundos', 'detalle': f'{len(dias_segundos)} día(s) con menos de un minuto de deuda', 'dias': dias_segundos})
    if saldo < -TOLERANCIA_MIN:
        hallazgos.append({'codigo': 'saldo_negativo', 'detalle': f'quedan {hhmmss(pendiente)} sin cubrir'})

    return {
        'deuda_bruta': deuda_bruta, 'perdonado': perdonado_total, 'perdonado_dias': perdonado, 'tolerado': tolerado,
        'perdon_cuadre': perdon_aplicado, 'compensado_inasistencia': comp_inasistencia,
        'cubierto': usadas_deuda, 'pendiente': pendiente, 'deuda_neta': deuda_neta,
        'he_trabajadas': he_trabajadas, 'he_aprobadas': he_aprobadas, 'he_jornadas_especiales': he_jornadas_especiales,
        'he_usadas_inasistencia': comp_respaldado, 'he_usadas_deuda': usadas_deuda, 'he_a_pagar': a_pagar,
        'he_no_pagadas': he_no_pagadas, 'he_por_decidir': he_por_decidir,
        'saldo': saldo,
        'causas': causas, 'cubierto_causa': cubierto_causa, 'pendiente_causa': pendiente_causa,
        'pendiente_perdonable': pendiente_causa['atraso'] + pendiente_causa['salida'],
        'pendiente_no_perdonable': pendiente_causa['otra'] + pendiente_causa['colacion'] + pendiente_causa['permiso'],
        # El saldo tal como lo calculan hoy la grilla, el cierre y el Excel (sin tolerancia ni perdón del tramo)
        'saldo_formula_actual': he_aprobadas - (deuda_neta + tolerado) - he_compensado,
        'hallazgos': hallazgos,
    }


ESTADOS_QUE_PASAN_A_OK = ('ATRASO', 'SALIDA_ADELANTADA')


def simular_sin_guia(dias: List[Dict[str, Any]], filas_guia: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Copia de los días como estarían si se deshicieran los perdonazos que puso la guía (para mostrar la propuesta y la
    vista previa de otra decisión sin tocar la base). Solo se deshacen los días cuya marca sigue siendo la de la guía."""
    por_fecha = {str(f['fecha'])[:10]: f for f in (filas_guia or []) if int(_f(f.get('tipo'))) > 0}
    if not por_fecha:
        return dias
    salida = []
    for di in dias:
        f = por_fecha.get(str(di.get('fecha'))[:10]) if isinstance(di, dict) else None
        if f and int(_f(di.get('deuda_condonada'))) == int(_f(f.get('tipo'))):
            d = dict(di)
            d['deuda_condonada'] = 0
            d['minutos_deuda'] = _f(di.get('minutos_deuda')) + _f(f.get('minutos_marca'))
            if int(_f(f.get('tipo'))) in (1, 3):
                # El motor deja en cero los minutos de salida adelantada del día perdonado: se reponen
                d['minutos_salida_adelantada'] = max(_f(di.get('minutos_salida_adelantada')), _f(f.get('minutos_salida')))
            salida.append(d)
        else:
            salida.append(di)
    return salida


def mapa_guiados(filas: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Filas activas de cuadre_perdonazos → {fecha: {'tipo', 'minutos_marca'}} (solo las que pusieron una marca)."""
    return {str(f['fecha'])[:10]: {'tipo': int(_f(f.get('tipo'))), 'minutos_marca': _f(f.get('minutos_marca'))}
            for f in (filas or []) if int(_f(f.get('tipo'))) > 0}


def presupuesto_he(dias: List[Dict[str, Any]], libro: Dict[str, Any], filas_he: List[Dict[str, Any]], es_bolsa: bool = False) -> float:
    """Minutos de horas extra con que la decisión del cuadre pagará deuda (el mismo reparto que escribe la política):
    las filas de días normales, las decididas a mano y las jornadas especiales aprobadas como horas extra."""
    especiales = {str(d.get('fecha'))[:10] for d in dias if isinstance(d, dict) and es_dia_especial(d, es_bolsa)}
    filas = marcar_filas_fijas([r for r in (filas_he or []) if str(r['fecha'])[:10] not in especiales])
    _, resumen = asignar_minutos(filas, _f(libro.get('deuda_neta')), 'CERO', None, _f(libro.get('he_jornadas_especiales')))
    return _f(resumen.get('cubierto'))


def plan_perdonazo(dias: List[Dict[str, Any]], libro: Dict[str, Any], presupuesto: float, es_bolsa: bool = False) -> Dict[str, Any]:
    """
    Qué atrasos y salidas adelantadas perdona la guía del cuadre para que la cuenta cierre exacta. Función pura.
    `libro` debe venir sin perdón de la guía (recién revocado) y `presupuesto` son los minutos de horas extra que pagarán
    deuda (presupuesto_he). Pagan primero lo que no se perdona (lo sin causa, el exceso de colación y los permisos),
    luego los atrasos por fecha y luego las salidas por fecha; lo que no alcanzan de atrasos y salidas se perdona.
      · día completo con minutos marcados por el motor → se perdona con la misma marca del interruptor (1 salida,
        2 atraso, 3 ambos) y el día deja de contar como atraso o salida;
      · día del borde (perdonado solo en parte) y segundos dentro del margen → se perdonan en la cuenta del cuadre
        (el día no cambia);
      · un día que ya tiene una marca del interruptor no se toca: su parte que quede se perdona en la cuenta del cuadre.
    """
    causas_t = libro.get('causas') or {}
    no_perdonable = _f(causas_t.get('otra')) + _f(causas_t.get('colacion')) + _f(causas_t.get('permiso'))
    queda_no_perdonable = max(0.0, no_perdonable - _f(presupuesto))
    presupuesto = max(0.0, _f(presupuesto) - no_perdonable)
    por_dia: Dict[str, Tuple[Dict[str, Any], Dict[str, float], int]] = {}
    for di in dias:
        if not isinstance(di, dict) or not di.get('fecha') or es_dia_especial(di, es_bolsa):
            continue
        por_dia[str(di['fecha'])[:10]] = (di, causas_dia(di), int(_f(di.get('deuda_condonada'))))
    perd: Dict[str, Dict[str, Any]] = {}
    for causa in CAUSAS_PERDONABLES:
        for fecha in sorted(por_dia):
            m = por_dia[fecha][1][causa]
            if m <= 1e-6:
                continue
            pago = min(presupuesto, m)
            presupuesto -= pago
            sin_pagar = m - pago
            if sin_pagar > 1e-6:
                e = perd.setdefault(fecha, {'atraso': 0.0, 'salida': 0.0, 'atraso_completo': False, 'salida_completo': False})
                e[causa] += sin_pagar
                e[causa + '_completo'] = pago <= 1e-6
    filas: List[Dict[str, Any]] = []
    for fecha in sorted(perd):
        e = perd[fecha]
        di, c, cond = por_dia[fecha]
        marca_a = e['atraso_completo'] and c['atraso_marcado'] > 1e-6 and cond == 0
        marca_s = e['salida_completo'] and c['salida_marcada'] > 1e-6 and cond == 0
        tipo = 3 if (marca_a and marca_s) else (2 if marca_a else (1 if marca_s else 0))
        minutos_marca = (c['atraso_marcado'] if marca_a else 0.0) + (c['salida_marcada'] if marca_s else 0.0)
        total = e['atraso'] + e['salida']
        estado = di.get('estado') or ''
        completo_dia = total >= (c['atraso'] + c['salida']) - 1e-6
        if tipo and estado in ESTADOS_QUE_PASAN_A_OK and completo_dia:
            efecto = 'pasa_a_ok'
        elif tipo:
            efecto = 'marca'
        elif not completo_dia or cond:
            efecto = 'parcial'
        else:
            efecto = 'segundos'
        filas.append({'fecha': fecha, 'estado_antes': estado, 'tipo': tipo,
                      'atraso': round(e['atraso'], 4), 'salida': round(e['salida'], 4),
                      'minutos_marca': round(minutos_marca, 4), 'minutos_cuadre': round(total - minutos_marca, 4),
                      'total': round(total, 4), 'efecto': efecto,
                      'hora_entrada_real': di.get('hora_entrada_real'), 'hora_salida_real': di.get('hora_salida_real')})
    return {'dias': filas, 'total': sum(f['total'] for f in filas), 'por_marca': sum(f['minutos_marca'] for f in filas),
            'por_cuadre': sum(f['minutos_cuadre'] for f in filas), 'queda_no_perdonable': queda_no_perdonable}


def aviso_inasistencia(dias: List[Dict[str, Any]], libro: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Aviso (no decide nada): las inasistencias compensables van al final, después de pagar toda la deuda. Si perdonar los
    atrasos y salidas, en vez de pagarlos, dejara horas extra suficientes para compensar una inasistencia completa, se
    avisa para que quien decide lo vea antes de confirmar.
    """
    inas = [d for d in dias if isinstance(d, dict) and (d.get('estado') in ('INASISTENCIA', 'FALTA'))
            and _f(d.get('minutos_compensados_he')) < 1.0 and _f(d.get('horas_teoricas')) > 0.0]
    if not inas:
        return None
    causas = libro.get('causas') or {}
    he = max(0.0, _f(libro.get('he_trabajadas')) - _f(libro.get('he_usadas_inasistencia')))
    no_perdonable = _f(causas.get('otra')) + _f(causas.get('colacion')) + _f(causas.get('permiso'))
    perdonable = _f(causas.get('atraso')) + _f(causas.get('salida'))
    libres_pagando = max(0.0, he - no_perdonable - perdonable)
    libres_perdonando = max(0.0, he - no_perdonable)
    for d in sorted(inas, key=lambda x: _f(x.get('horas_teoricas'))):
        m = _f(d.get('horas_teoricas')) * 60.0
        if libres_perdonando >= m - TOLERANCIA_MIN and libres_pagando < m - TOLERANCIA_MIN:
            return {'fecha': str(d.get('fecha'))[:10], 'minutos_inasistencia': m,
                    'libres_pagando': libres_pagando, 'libres_perdonando': libres_perdonando}
    return None


def calendario_tramo(dias: List[Dict[str, Any]], detalle: List[Dict[str, Any]], fecha_inicio: str, fecha_fin: str) -> List[Dict[str, Any]]:
    """Un registro por cada fecha del tramo, para la línea de días de la ventana de cuadre.

    Toma el estado y las marcas de cada día de la matriz y los minutos (deuda, perdonado, horas extra) del detalle del
    libro, para que la línea y las sumas nunca difieran. Un día sin registro (futuro o sin calcular) va con estado None."""
    por_fecha = {str(d.get('fecha'))[:10]: d for d in dias}
    det = {x['fecha']: x for x in detalle}
    salida: List[Dict[str, Any]] = []
    d = date.fromisoformat(str(fecha_inicio)[:10])
    fin = date.fromisoformat(str(fecha_fin)[:10])
    while d <= fin:
        f = d.isoformat()
        di = por_fecha.get(f) or {}
        x = det.get(f) or {}
        salida.append({
            'fecha': f, 'estado': di.get('estado'),
            'hora_entrada_real': di.get('hora_entrada_real'), 'hora_salida_real': di.get('hora_salida_real'),
            'deuda_bruta': _f(x.get('deuda_bruta')), 'deuda': _f(x.get('deuda')), 'perdonado': _f(x.get('perdonado')),
            'he_bruto': _f(x.get('he_bruto')), 'he_autorizados': _f(x.get('he_autorizados')), 'estado_he': x.get('estado_he'),
            'especial': bool(x.get('especial')), 'excepcion': int(_f(x.get('excepcion'))),
        })
        d += timedelta(days=1)
    return salida


# Horas extra que nacen de validar una jornada especial (cobertura de turno, día libre, feriado): las decide su propia
# pantalla y el motor las conserva por su origen. La política del cuadre las cuenta como aprobadas fijas y nunca las reescribe.
ORIGENES_FIJOS = ('COBERTURA_TURNO', 'DIA_LIBRE', 'FERIADO', 'JORNADA_ESPECIAL')


def marcar_filas_fijas(filas_he: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Copia de las filas con `excepcion = 1` en las que vienen de una jornada especial validada (ORIGENES_FIJOS)."""
    return [{**r, 'excepcion': 1} if (r.get('origen') or '') in ORIGENES_FIJOS else dict(r) for r in filas_he]


def asignar_minutos(filas_he: List[Dict[str, Any]], deuda_a_cubrir: float, politica: str,
                    minutos_a_pagar: Optional[float] = None, aprobadas_fijas: float = 0.0) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """
    Reparte las horas extra del tramo según la política, día por día en orden de fecha. Función pura.
      filas_he: [{fecha, minutos_bruto, minutos_autorizados, estado, excepcion}], una por día con horas extra.
      Las filas con excepción (decididas a mano) no se tocan: lo que tienen aprobado cuenta primero.
      aprobadas_fijas: minutos aprobados que no reparte la política (jornadas especiales aprobadas como horas extra).
      politica 'CERO': se cubre la deuda y no se paga nada más. 'PAGAR': se cubre y se paga hasta
      minutos_a_pagar (None = todo lo que sobre).
    Devuelve (reparto de las filas sin excepción, resumen).
    """
    if politica not in POLITICAS:
        raise ValueError(f"Política desconocida: {politica}")
    filas = sorted(filas_he, key=lambda r: str(r.get('fecha')))
    fijo = _f(aprobadas_fijas) + sum(_f(r.get('minutos_autorizados')) for r in filas
                                     if int(_f(r.get('excepcion'))) and r.get('estado') == 'APROBADO')
    deuda = max(0.0, _f(deuda_a_cubrir))
    cubierto_fijo = min(fijo, deuda)
    pagado_fijo = fijo - cubierto_fijo
    restante_deuda = deuda - cubierto_fijo
    if politica == 'CERO':
        restante_pago: Optional[float] = 0.0
    elif minutos_a_pagar is None:
        restante_pago = None                         # sin tope: todo lo que sobre
    else:
        restante_pago = max(0.0, _f(minutos_a_pagar) - pagado_fijo)

    reparto: List[Dict[str, Any]] = []
    a_pagar = pagado_fijo
    no_pagadas = 0.0
    for r in filas:
        if int(_f(r.get('excepcion'))):
            continue
        bruto = max(0.0, _f(r.get('minutos_bruto')))
        usa = min(bruto, restante_deuda)
        restante_deuda -= usa
        sobra = bruto - usa
        paga = sobra if restante_pago is None else min(sobra, restante_pago)
        if restante_pago is not None:
            restante_pago -= paga
        a_pagar += paga
        aut = round(usa + paga, 3)
        no_pagadas += max(0.0, bruto - aut)
        reparto.append({'fecha': str(r.get('fecha'))[:10], 'estado': 'APROBADO' if aut >= 0.005 else 'RECHAZADO',
                        'minutos_autorizados': aut if aut >= 0.005 else 0.0, 'usadas': round(usa, 3), 'a_pagar': round(paga, 3)})
    resumen = {'cubierto': deuda - restante_deuda, 'pendiente': restante_deuda, 'a_pagar': a_pagar, 'no_pagadas': no_pagadas}
    return reparto, resumen


class CuadreService:
    """Libro mayor de minutos y política del tramo, con los mismos días que ven la grilla y el cierre."""

    def __init__(self, asistencia_service):
        from backend.repositories.cuadre import CuadreRepository
        self.asistencia_service = asistencia_service
        self.db = asistencia_service.repository.db
        self.repo = CuadreRepository(self.db)

    # ── tramo ─────────────────────────────────────────────────────────────
    async def tramo_de(self, fecha: str) -> Tuple[str, str]:
        """Tramo de RRHH que contiene la fecha (tabla periodos_rrhh); si no hay, el ciclo del día de cierre configurado."""
        row = await self.db.fetch_one(
            "SELECT fecha_inicio, fecha_fin FROM periodos_rrhh WHERE fecha_inicio <= ? AND fecha_fin >= ? ORDER BY fecha_inicio DESC LIMIT 1",
            (fecha, fecha))
        if row:
            return str(row['fecha_inicio'])[:10], str(row['fecha_fin'])[:10]
        aj = await self.db.fetch_one("SELECT valor FROM ajustes WHERE clave = 'dia_cierre_rrhh'")
        try:
            dc = int(aj['valor']) if aj else 25
        except (TypeError, ValueError):
            dc = 25
        f = date.fromisoformat(fecha[:10])
        if f.day > dc:
            ini = f.replace(day=dc + 1)
            sig = (f.replace(day=1) + timedelta(days=32)).replace(day=1)
            fin = sig.replace(day=dc)
        else:
            ant = (f.replace(day=1) - timedelta(days=1)).replace(day=dc + 1)
            ini, fin = ant, f.replace(day=dc)
        return ini.isoformat(), fin.isoformat()

    # ── hechos ────────────────────────────────────────────────────────────
    async def _dias_empleado(self, empleado_id: int, fecha_inicio: str, fecha_fin: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        f_ini = date.fromisoformat(fecha_inicio)
        data = await self.asistencia_service.get_matrix_data_with_projections(
            f_ini.month, f_ini.year, empleado_id=empleado_id, fecha_inicio_override=fecha_inicio, fecha_fin_override=fecha_fin)
        matrix = data.get('matrix', {}) or {}
        celdas = matrix.get(empleado_id) or matrix.get(str(empleado_id)) or {}
        empleados = data.get('empleados', []) or []
        if isinstance(empleados, dict):
            empleados = list(empleados.values())
        info = next((e for e in empleados if e.get('id') == empleado_id), None) or (celdas.get('info') or {})
        dias = [v for k, v in celdas.items() if k != 'info' and isinstance(v, dict)]
        dias.sort(key=lambda d: str(d.get('fecha')))
        return dias, info

    @staticmethod
    def _es_bolsa(info: Dict[str, Any]) -> bool:
        return (info.get('tipo_programacion') or '') in ('BOLSA_FLEXIBLE', 'FLEXIBLE_BOLSA')

    # ── libro de una persona ──────────────────────────────────────────────
    async def libro_empleado(self, empleado_id: int, fecha_inicio: str, fecha_fin: str) -> Dict[str, Any]:
        dias, info = await self._dias_empleado(empleado_id, fecha_inicio, fecha_fin)
        es_bolsa = self._es_bolsa(info)
        politica = await self.repo.get_politica(empleado_id, fecha_inicio, fecha_fin)
        tolerancia = await self.repo.tolerancia_minutos()
        guiados_filas = await self.repo.perdonazos_activos(empleado_id, fecha_inicio, fecha_fin)
        guiados = mapa_guiados(guiados_filas)
        libro = plegar_libro(dias, es_bolsa=es_bolsa, tolerancia_min=tolerancia, guiados=guiados,
                             perdon_cuadre=_f(politica.get('minutos_perdonados')) if politica else 0.0, hay_politica=bool(politica))
        lista_he = await self.repo.filas_he(empleado_id, fecha_inicio, fecha_fin)
        # Lo que perdonaría «Perdonar atrasos y salidas» si se decidiera ahora desde cero (como si se deshiciera la guía)
        dias_sin_guia = simular_sin_guia(dias, guiados_filas)
        base_sin_guia = plegar_libro(dias_sin_guia, es_bolsa=es_bolsa, tolerancia_min=tolerancia)
        propuesta = plan_perdonazo(dias_sin_guia, base_sin_guia, presupuesto_he(dias_sin_guia, base_sin_guia, lista_he, es_bolsa), es_bolsa)
        aviso = aviso_inasistencia(dias_sin_guia, base_sin_guia)
        sin_guia = {'deuda_neta': base_sin_guia['deuda_neta'], 'perdonado': base_sin_guia['perdonado'],
                    'he_trabajadas': base_sin_guia['he_trabajadas'], 'he_usadas_inasistencia': base_sin_guia['he_usadas_inasistencia']}
        guia_activa = ({'dias': len(guiados_filas), 'minutos_marca': sum(_f(f.get('minutos_marca')) for f in guiados_filas),
                        'minutos_cuadre': sum(_f(f.get('minutos_cuadre')) for f in guiados_filas)} if guiados_filas else None)
        filas_he = {r['fecha'][:10] if isinstance(r['fecha'], str) else str(r['fecha'])[:10]: r for r in lista_he}
        detalle = []
        for di in dias:
            fecha = str(di.get('fecha'))[:10]
            esp = es_dia_especial(di, es_bolsa)
            neta = 0.0 if int(_f(di.get('deuda_condonada'))) == 5 else _f(di.get('minutos_deuda'))
            bruta = di.get('minutos_deuda_bruta')
            bruta = max(_f(bruta) if bruta is not None else neta, neta)
            he_bruto = 0.0 if esp else _f(di.get('minutos_extra_bruto'))
            ja = di.get('jornada_adicional') or {}
            if esp and ja.get('estado') == 'HORAS_EXTRAS':
                he_bruto = _f(ja.get('minutos_autorizados')) or _f(ja.get('minutos_trabajados'))
            if bruta < 0.5 and he_bruto < 0.5 and not esp:
                continue
            fila = filas_he.get(fecha) or {}
            detalle.append({
                'fecha': fecha, 'estado': di.get('estado'), 'hora_entrada_real': di.get('hora_entrada_real'), 'hora_salida_real': di.get('hora_salida_real'),
                'horas_teoricas': _f(di.get('horas_teoricas')), 'horas_trabajadas': _f(di.get('horas_trabajadas')),
                'deuda_bruta': bruta, 'deuda': neta, 'perdonado': max(0.0, bruta - neta), 'deuda_condonada': int(_f(di.get('deuda_condonada'))),
                'he_bruto': he_bruto, 'he_autorizados': _f(di.get('minutos_extra_autorizados')) if di.get('estado_he') == 'APROBADO' else 0.0,
                'estado_he': di.get('estado_he') or ('PENDIENTE' if he_bruto >= 1.0 else None),
                'excepcion': int(_f(fila.get('excepcion'))), 'origen_he': fila.get('origen'), 'especial': esp,
                'causas': {k: round(v, 4) for k, v in causas_dia(di).items()} if not esp else dict(CAUSAS_VACIAS),
            })
        nombre = f"{info.get('apellido_paterno', '')} {info.get('apellido_materno', '') or ''} {info.get('nombre', '')}".strip().replace('  ', ' ')
        return {'empleado_id': empleado_id, 'nombre': nombre or info.get('nombre_completo'), 'es_bolsa': es_bolsa,
                'cargo': info.get('cargo') or '', 'area': info.get('area') or '', 'turno': info.get('turno') or '',
                'tramo': {'inicio': fecha_inicio, 'fin': fecha_fin}, 'politica': politica, 'tolerancia_minutos': tolerancia,
                'libro': libro, 'dias': detalle, 'calendario': calendario_tramo(dias, detalle, fecha_inicio, fecha_fin),
                'perdonazos_guiados': guiados_filas, 'guia_activa': guia_activa, 'propuesta': propuesta,
                'aviso_inasistencia': aviso, 'sin_guia': sin_guia}

    # ── política del tramo ────────────────────────────────────────────────
    async def _base_para_reparto(self, empleado_id: int, fecha_inicio: str, fecha_fin: str) -> Tuple[float, float, List[Dict[str, Any]]]:
        dias, info = await self._dias_empleado(empleado_id, fecha_inicio, fecha_fin)
        tolerancia = await self.repo.tolerancia_minutos()
        guiados = mapa_guiados(await self.repo.perdonazos_activos(empleado_id, fecha_inicio, fecha_fin))
        base = plegar_libro(dias, es_bolsa=self._es_bolsa(info), tolerancia_min=tolerancia, guiados=guiados)
        filas = await self.repo.filas_he(empleado_id, fecha_inicio, fecha_fin)
        # Las filas de horas extra solo valen para días que el cálculo trata como jornada normal
        especiales = {str(d.get('fecha'))[:10] for d in dias if es_dia_especial(d, self._es_bolsa(info))}
        filas = marcar_filas_fijas([r for r in filas if str(r['fecha'])[:10] not in especiales])
        return base['deuda_neta'], base['he_jornadas_especiales'], filas

    async def aplicar_politica(self, empleado_id: int, fecha_inicio: str, fecha_fin: str,
                               politica: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, float]]:
        p = politica or await self.repo.get_politica(empleado_id, fecha_inicio, fecha_fin)
        if not p:
            return None
        deuda, fijas, filas = await self._base_para_reparto(empleado_id, fecha_inicio, fecha_fin)
        reparto, resumen = asignar_minutos(filas, deuda, p['politica'], p.get('minutos_a_pagar'), fijas)
        await self.repo.escribir_reparto(empleado_id, reparto)
        return resumen

    async def decidir_politica(self, empleado_id: int, fecha_inicio: str, fecha_fin: str, politica: str,
                               minutos_a_pagar: Optional[float], usuario: str, usuario_id: Optional[int], motivo: Optional[str]) -> Dict[str, Any]:
        if politica not in POLITICAS:
            raise ValueError("La política debe ser CERO (llevar todo a cero) o PAGAR (pagar horas extra).")
        if politica == 'PAGAR' and minutos_a_pagar is not None and _f(minutos_a_pagar) < 0:
            raise ValueError("Los minutos a pagar no pueden ser negativos.")
        _REAPLICANDO.add(int(empleado_id))
        try:
            # Candado (punto 1 del dueño): toda decisión nueva parte deshaciendo los perdonazos que puso la guía, para que
            # las horas extra que cubrían esos atrasos nunca se paguen además de haberlos perdonado.
            revocados = await self._revocar_guiados(empleado_id, fecha_inicio, fecha_fin, usuario, usuario_id, 'nueva decisión del cuadre')
            perdonados, plan = 0.0, None
            if politica == 'CERO':
                # «Perdonar atrasos y salidas»: las horas extra pagan colación, permisos, atrasos y salidas en ese orden;
                # lo que no alcanzan de atrasos y salidas se perdona por día. El exceso de colación y los permisos nunca.
                dias, info = await self._dias_empleado(empleado_id, fecha_inicio, fecha_fin)
                es_bolsa = self._es_bolsa(info)
                base = plegar_libro(dias, es_bolsa=es_bolsa, tolerancia_min=await self.repo.tolerancia_minutos())
                lista_he = await self.repo.filas_he(empleado_id, fecha_inicio, fecha_fin)
                plan = plan_perdonazo(dias, base, presupuesto_he(dias, base, lista_he, es_bolsa), es_bolsa)
                perdonados = await self._aplicar_plan(empleado_id, fecha_inicio, fecha_fin, plan, usuario)
            deuda, fijas, filas = await self._base_para_reparto(empleado_id, fecha_inicio, fecha_fin)
            _, resumen = asignar_minutos(filas, deuda, politica, minutos_a_pagar, fijas)
            await self.repo.guardar_politica(empleado_id, fecha_inicio, fecha_fin, politica, minutos_a_pagar, perdonados, usuario, motivo)
            await self.aplicar_politica(empleado_id, fecha_inicio, fecha_fin)
        finally:
            _REAPLICANDO.discard(int(empleado_id))
        await self._auditar(usuario_id, usuario, 'DECIDIR_CUADRE', {
            'empleado_id': empleado_id, 'tramo': [fecha_inicio, fecha_fin], 'politica': politica, 'minutos_a_pagar': minutos_a_pagar,
            'minutos_perdonados_en_el_cuadre': round(perdonados, 2), 'cubierto': round(resumen['cubierto'], 2), 'a_pagar': round(resumen['a_pagar'], 2),
            'no_pagadas': round(resumen['no_pagadas'], 2), 'motivo': motivo, 'perdonazos_guiados_revocados': revocados,
            'perdonazo_guiado': ({'dias': [{k: f[k] for k in ('fecha', 'tipo', 'atraso', 'salida', 'minutos_marca', 'minutos_cuadre', 'efecto')} for f in plan['dias']],
                                  'total': round(plan['total'], 2)} if plan else None)})
        return await self.libro_empleado(empleado_id, fecha_inicio, fecha_fin)

    async def quitar_politica(self, empleado_id: int, fecha_inicio: str, fecha_fin: str, usuario: str, usuario_id: Optional[int]) -> Dict[str, Any]:
        _REAPLICANDO.add(int(empleado_id))
        try:
            revocados = await self._revocar_guiados(empleado_id, fecha_inicio, fecha_fin, usuario, usuario_id, 'se quitó la política del cuadre')
            await self.repo.quitar_politica(empleado_id, fecha_inicio, fecha_fin)
        finally:
            _REAPLICANDO.discard(int(empleado_id))
        await self._auditar(usuario_id, usuario, 'QUITAR_POLITICA_CUADRE', {'empleado_id': empleado_id, 'tramo': [fecha_inicio, fecha_fin],
                                                                             'perdonazos_guiados_revocados': revocados})
        return await self.libro_empleado(empleado_id, fecha_inicio, fecha_fin)

    async def _aplicar_plan(self, empleado_id: int, fecha_inicio: str, fecha_fin: str, plan: Dict[str, Any], usuario: str) -> float:
        """Pone las marcas del interruptor de los días completos, guarda cada perdonazo con su origen y recalcula esos
        días. Devuelve los minutos que se perdonan en la cuenta del cuadre (parte de un día y segundos del margen)."""
        fechas: List[str] = []
        for f in plan['dias']:
            if int(f['tipo']) <= 0:
                continue
            if await self.repo.marca_del_dia(empleado_id, f['fecha']) != 0:
                # Alguien puso una marca del interruptor en este día: no se pisa; se perdona en la cuenta del cuadre
                f['minutos_cuadre'] = round(f['minutos_cuadre'] + f['minutos_marca'], 4)
                f['minutos_marca'], f['tipo'], f['efecto'] = 0.0, 0, 'parcial'
                continue
            await self.repo.poner_marca(empleado_id, f['fecha'], int(f['tipo']))
            fechas.append(f['fecha'])
        if plan['dias']:
            await self.repo.guardar_perdonazos(empleado_id, fecha_inicio, fecha_fin, plan['dias'], usuario)
        for fecha in fechas:
            await self.asistencia_service.procesar_dia(fecha=fecha, force=True, empleado_ids={int(empleado_id)})
        return float(sum(_f(f['minutos_cuadre']) for f in plan['dias']))

    async def _revocar_guiados(self, empleado_id: int, fecha_inicio: str, fecha_fin: str, usuario: str,
                               usuario_id: Optional[int], motivo: str) -> int:
        """Deshace los perdonazos que puso la guía del cuadre: quita solo las marcas que siguen siendo las de la guía
        (una marca que puso o cambió el interruptor no se toca) y recalcula esos días."""
        filas = await self.repo.perdonazos_activos(empleado_id, fecha_inicio, fecha_fin)
        if not filas:
            return 0
        fechas: List[str] = []
        for f in filas:
            tipo = int(_f(f.get('tipo')))
            fecha = str(f['fecha'])[:10]
            if tipo > 0 and await self.repo.marca_del_dia(empleado_id, fecha) == tipo:
                await self.repo.poner_marca(empleado_id, fecha, 0)
                fechas.append(fecha)
        await self.repo.desactivar_perdonazos([int(f['id']) for f in filas], usuario)
        for fecha in fechas:
            await self.asistencia_service.procesar_dia(fecha=fecha, force=True, empleado_ids={int(empleado_id)})
        await self._auditar(usuario_id, usuario, 'REVOCAR_PERDONAZOS_GUIADOS', {
            'empleado_id': empleado_id, 'tramo': [fecha_inicio, fecha_fin], 'motivo': motivo,
            'dias': [str(f['fecha'])[:10] for f in filas], 'marcas_quitadas': fechas})
        return len(filas)

    async def reaplicar_para(self, empleado_ids: List[int], fecha: str) -> int:
        """Tras recalcular un día, vuelve a repartir las horas extra de quienes tienen política en ese tramo."""
        ids = [int(e) for e in empleado_ids if e is not None and int(e) not in _REAPLICANDO]
        if not ids:
            return 0
        politicas = await self.repo.politicas_que_cubren(ids, fecha)
        n = 0
        for p in politicas:
            eid = int(p['empleado_id'])
            if eid in _REAPLICANDO:
                continue
            _REAPLICANDO.add(eid)
            try:
                await self.aplicar_politica(eid, str(p['fecha_inicio'])[:10], str(p['fecha_fin'])[:10], p)
                n += 1
            except Exception as e:
                logger.warning(f"[Cuadre] No se pudo reaplicar la política de {eid}: {e}")
            finally:
                _REAPLICANDO.discard(eid)
        return n

    async def _auditar(self, usuario_id: Optional[int], usuario: str, accion: str, detalle: Dict[str, Any]) -> None:
        try:
            from backend.repositories.seguridad import SeguridadRepository
            await SeguridadRepository(self.db).log_auditoria(usuario_id, usuario, accion, 'MARCACIONES', json.dumps(detalle, ensure_ascii=False, default=str))
        except Exception as e:
            logger.warning(f"[Cuadre] Auditoría no registrada ({accion}): {e}")

    # ── libro de todo un tramo ────────────────────────────────────────────
    async def libro_periodo(self, fecha_inicio: str, fecha_fin: str, area: Optional[str] = None) -> Dict[str, Any]:
        f_ini = date.fromisoformat(fecha_inicio)
        matrix_data = await self.asistencia_service.get_matrix_data_with_projections(
            f_ini.month, f_ini.year, area=area, fecha_inicio_override=fecha_inicio, fecha_fin_override=fecha_fin
        )
        empleados = matrix_data.get('empleados', []) or []
        matrix = matrix_data.get('matrix', {}) or {}
        if isinstance(empleados, dict):
            empleados = list(empleados.values())
        tolerancia = await self.repo.tolerancia_minutos()
        politicas = {int(p['empleado_id']): p for p in await self.repo.politicas_del_tramo(fecha_inicio, fecha_fin)}
        guiados_tramo = await self.repo.perdonazos_del_tramo(fecha_inicio, fecha_fin)

        filas: List[Dict[str, Any]] = []
        for emp in empleados:
            eid = emp.get('id')
            celdas = matrix.get(eid) or matrix.get(str(eid)) or {}
            dias = [v for k, v in celdas.items() if k != 'info' and isinstance(v, dict)]
            tipo = (emp.get('tipo_programacion') or (celdas.get('info') or {}).get('tipo_programacion') or '')
            if tipo in ('BOLSA_FLEXIBLE', 'FLEXIBLE_BOLSA'):
                continue  # Bolsa Flexible tiene su propia meta mensual; el libro es de Ciclo Inteligente
            p = politicas.get(int(eid)) if eid is not None else None
            libro = plegar_libro(dias, es_bolsa=False, tolerancia_min=tolerancia,
                                 guiados=mapa_guiados(guiados_tramo.get(int(eid), [])) if eid is not None else None,
                                 perdon_cuadre=_f(p.get('minutos_perdonados')) if p else 0.0, hay_politica=bool(p))
            nombre = f"{emp.get('apellido_paterno', '')} {emp.get('apellido_materno', '') or ''} {emp.get('nombre', '')}".strip().replace('  ', ' ')
            filas.append({'empleado_id': eid, 'nombre': nombre, 'area': emp.get('area'), 'turno': emp.get('turno_nombre') or emp.get('turno'),
                          'politica': (p or {}).get('politica'), 'minutos_a_pagar': (p or {}).get('minutos_a_pagar'), **libro})

        claves = ('deuda_bruta', 'perdonado', 'tolerado', 'perdon_cuadre', 'compensado_inasistencia', 'cubierto', 'pendiente', 'he_trabajadas',
                  'he_aprobadas', 'he_usadas_inasistencia', 'he_usadas_deuda', 'he_a_pagar', 'he_no_pagadas', 'he_por_decidir', 'saldo')
        totales = {k: sum(_f(f[k]) for f in filas) for k in claves}
        conteo: Dict[str, int] = {}
        for f in filas:
            for h in f['hallazgos']:
                conteo[h['codigo']] = conteo.get(h['codigo'], 0) + 1
        return {'desde': fecha_inicio, 'hasta': fecha_fin, 'personas': len(filas), 'tolerancia_minutos': tolerancia,
                'filas': filas, 'totales': totales, 'hallazgos': conteo}
