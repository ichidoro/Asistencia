"""Libro mayor de minutos: cuadre de deuda, horas extra y perdonazos de una persona en un tramo.

Regla del dueño (25-10-2026): cada minuto tiene un solo destino y las sumas siempre cuadran.
  Deuda        = perdonada + cubierta con horas extra + pendiente
  Horas extra  = usadas (para cubrir deuda o una inasistencia) + a pagar + no pagadas + por decidir
  Saldo        = a pagar − pendiente
La deuda se cubre primero con las horas extra aprobadas; lo que sobra se paga. Dentro del tramo el orden de los días
no importa («lo que debo hoy lo pago mañana»). Entre tramos no hay arrastre: lo que no se pagó en el tramo no se paga.

Aquí no se decide nada: se PLIEGAN los hechos que calculó el motor (días de `asistencias`) y las decisiones ya
registradas (perdonazos, aprobaciones de horas extra) en esos totales, y se comprueba que cuadren. El mismo cálculo
debe alimentar la grilla, la ventana de cuadre, el cierre y el Excel.
"""
from typing import Any, Dict, List, Optional

TOLERANCIA_MIN = 0.05           # diferencia que se acepta en una identidad (redondeos de segundos)
ESTADOS_ESPECIALES = ('JORNADA_ESPECIAL', 'EXTRA', 'FERIADO Y JORNADA EXTRA', 'DÍA LIBRE Y JORNADA EXTRA')


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


def plegar_libro(dias: List[Dict[str, Any]], es_bolsa: bool = False) -> Dict[str, Any]:
    """
    Pliega los días de una persona en los totales del libro. Función pura: solo lee los dicts.
    Devuelve minutos (float) y la lista de hallazgos del verificador.
    """
    deuda_bruta = deuda_neta = perdonado = comp_inasistencia = 0.0
    he_trabajadas = he_aprobadas = he_no_pagadas = he_por_decidir = he_compensado = 0.0
    hallazgos: List[Dict[str, Any]] = []
    dias_parciales: List[str] = []
    dias_segundos: List[str] = []
    dias_perdonados: List[str] = []
    dias_aprobado_sobre_trabajado: List[str] = []

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
        deuda_bruta += bruta_d
        deuda_neta += neta_d
        comp_inasistencia += comp_d
        perdonado += perdonado_d
        if perdonado_d >= 1.0:
            dias_perdonados.append(fecha)
        if 0.0 < neta_d < 1.0:
            dias_segundos.append(fecha)

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

    # Cobertura sobre los totales del tramo (sin importar el orden de los días)
    aprobadas_disponibles = he_aprobadas - he_compensado
    if aprobadas_disponibles < -TOLERANCIA_MIN:
        hallazgos.append({'codigo': 'compensado_sobre_aprobado', 'detalle': f'{hhmmss(-aprobadas_disponibles)} compensados sin horas aprobadas que los respalden'})
    aprobadas_disponibles = max(0.0, aprobadas_disponibles)
    usadas_deuda = min(aprobadas_disponibles, deuda_neta)
    a_pagar = aprobadas_disponibles - usadas_deuda
    pendiente = deuda_neta - usadas_deuda
    saldo = a_pagar - pendiente

    # Identidades
    dif_deuda = deuda_bruta - (perdonado + comp_inasistencia + usadas_deuda + pendiente)
    dif_he = he_trabajadas - (he_compensado + usadas_deuda + a_pagar + he_no_pagadas + he_por_decidir)
    if abs(dif_deuda) > TOLERANCIA_MIN:
        hallazgos.append({'codigo': 'identidad_deuda', 'detalle': f'la deuda no cuadra por {hhmmss(dif_deuda)}'})
    if abs(dif_he) > TOLERANCIA_MIN:
        hallazgos.append({'codigo': 'identidad_horas_extra', 'detalle': f'las horas extra no cuadran por {hhmmss(dif_he)}'})
    if dias_parciales:
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
        'deuda_bruta': deuda_bruta, 'perdonado': perdonado, 'compensado_inasistencia': comp_inasistencia,
        'cubierto': usadas_deuda, 'pendiente': pendiente, 'deuda_neta': deuda_neta,
        'he_trabajadas': he_trabajadas, 'he_aprobadas': he_aprobadas, 'he_usadas_inasistencia': he_compensado,
        'he_usadas_deuda': usadas_deuda, 'he_a_pagar': a_pagar, 'he_no_pagadas': he_no_pagadas, 'he_por_decidir': he_por_decidir,
        'saldo': saldo,
        # El saldo tal como lo calculan hoy la grilla, el cierre y el Excel (debe ser el mismo número)
        'saldo_formula_actual': he_aprobadas - deuda_neta - he_compensado,
        'hallazgos': hallazgos,
    }


class CuadreService:
    """Libro mayor de minutos de todas las personas de un tramo, con los mismos días que ven la grilla y el cierre."""

    def __init__(self, asistencia_service):
        self.asistencia_service = asistencia_service

    async def libro_periodo(self, fecha_inicio: str, fecha_fin: str, area: Optional[str] = None) -> Dict[str, Any]:
        from datetime import date
        f_ini = date.fromisoformat(fecha_inicio)
        matrix_data = await self.asistencia_service.get_matrix_data_with_projections(
            f_ini.month, f_ini.year, area=area, fecha_inicio_override=fecha_inicio, fecha_fin_override=fecha_fin
        )
        empleados = matrix_data.get('empleados', []) or []
        matrix = matrix_data.get('matrix', {}) or {}
        if isinstance(empleados, dict):
            empleados = list(empleados.values())

        filas: List[Dict[str, Any]] = []
        for emp in empleados:
            eid = emp.get('id')
            celdas = matrix.get(eid) or matrix.get(str(eid)) or {}
            dias = [v for k, v in celdas.items() if k != 'info' and isinstance(v, dict)]
            tipo = (emp.get('tipo_programacion') or (celdas.get('info') or {}).get('tipo_programacion') or '')
            es_bolsa = tipo in ('BOLSA_FLEXIBLE', 'FLEXIBLE_BOLSA')
            if es_bolsa:
                continue  # Bolsa Flexible tiene su propia meta mensual; el libro es de Ciclo Inteligente
            libro = plegar_libro(dias, es_bolsa=False)
            nombre = f"{emp.get('apellido_paterno', '')} {emp.get('apellido_materno', '') or ''} {emp.get('nombre', '')}".strip().replace('  ', ' ')
            filas.append({'empleado_id': eid, 'nombre': nombre, 'area': emp.get('area'), 'turno': emp.get('turno_nombre') or emp.get('turno'), **libro})

        claves = ('deuda_bruta', 'perdonado', 'compensado_inasistencia', 'cubierto', 'pendiente', 'he_trabajadas',
                  'he_aprobadas', 'he_usadas_inasistencia', 'he_usadas_deuda', 'he_a_pagar', 'he_no_pagadas', 'he_por_decidir', 'saldo')
        totales = {k: sum(_f(f[k]) for f in filas) for k in claves}
        conteo: Dict[str, int] = {}
        for f in filas:
            for h in f['hallazgos']:
                conteo[h['codigo']] = conteo.get(h['codigo'], 0) + 1
        return {'desde': fecha_inicio, 'hasta': fecha_fin, 'personas': len(filas), 'filas': filas, 'totales': totales, 'hallazgos': conteo}
