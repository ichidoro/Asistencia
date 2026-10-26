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


def plegar_libro(dias: List[Dict[str, Any]], es_bolsa: bool = False, tolerancia_min: float = 0.0,
                 perdon_cuadre: float = 0.0, hay_politica: bool = False) -> Dict[str, Any]:
    """
    Pliega los días de una persona en los totales del libro. Función pura: solo lee los dicts.
      tolerancia_min: deuda de un día por debajo de este valor se deja pasar (se informa como «tolerado»).
      perdon_cuadre:  minutos perdonados a nivel del tramo por la política «llevar todo a cero».
      hay_politica:   con política registrada, una aprobación parcial es una decisión, no un hallazgo.
    Devuelve minutos (float) y la lista de hallazgos del verificador.
    """
    deuda_bruta = deuda_neta = perdonado = tolerado = comp_inasistencia = 0.0
    he_trabajadas = he_aprobadas = he_no_pagadas = he_por_decidir = he_compensado = he_jornadas_especiales = 0.0
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
        if tolerancia_min > 0 and 0.0 < neta_d <= tolerancia_min:
            tolerado += neta_d
            neta_d = 0.0
        elif 0.0 < neta_d < 1.0:
            dias_segundos.append(fecha)
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

    # Cobertura sobre los totales del tramo (sin importar el orden de los días)
    aprobadas_disponibles = he_aprobadas - he_compensado
    if aprobadas_disponibles < -TOLERANCIA_MIN:
        hallazgos.append({'codigo': 'compensado_sobre_aprobado', 'detalle': f'{hhmmss(-aprobadas_disponibles)} compensados sin horas aprobadas que los respalden'})
    aprobadas_disponibles = max(0.0, aprobadas_disponibles)
    usadas_deuda = min(aprobadas_disponibles, deuda_neta)
    a_pagar = aprobadas_disponibles - usadas_deuda
    pendiente = deuda_neta - usadas_deuda
    # Perdón del tramo («llevar todo a cero»): borra lo que quedó pendiente al decidirlo, nunca más que eso
    perdon_aplicado = min(max(0.0, _f(perdon_cuadre)), pendiente)
    pendiente -= perdon_aplicado
    saldo = a_pagar - pendiente

    # Identidades
    perdonado_total = perdonado + tolerado + perdon_aplicado
    dif_deuda = deuda_bruta - (perdonado_total + comp_inasistencia + usadas_deuda + pendiente)
    dif_he = he_trabajadas - (he_compensado + usadas_deuda + a_pagar + he_no_pagadas + he_por_decidir)
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
        'he_usadas_inasistencia': he_compensado, 'he_usadas_deuda': usadas_deuda, 'he_a_pagar': a_pagar,
        'he_no_pagadas': he_no_pagadas, 'he_por_decidir': he_por_decidir,
        'saldo': saldo,
        # El saldo tal como lo calculan hoy la grilla, el cierre y el Excel (sin tolerancia ni perdón del tramo)
        'saldo_formula_actual': he_aprobadas - (deuda_neta + tolerado) - he_compensado,
        'hallazgos': hallazgos,
    }


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
        libro = plegar_libro(dias, es_bolsa=es_bolsa, tolerancia_min=tolerancia,
                             perdon_cuadre=_f(politica.get('minutos_perdonados')) if politica else 0.0, hay_politica=bool(politica))
        filas_he = {r['fecha'][:10] if isinstance(r['fecha'], str) else str(r['fecha'])[:10]: r
                    for r in await self.repo.filas_he(empleado_id, fecha_inicio, fecha_fin)}
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
            })
        nombre = f"{info.get('apellido_paterno', '')} {info.get('apellido_materno', '') or ''} {info.get('nombre', '')}".strip().replace('  ', ' ')
        return {'empleado_id': empleado_id, 'nombre': nombre or info.get('nombre_completo'), 'es_bolsa': es_bolsa,
                'tramo': {'inicio': fecha_inicio, 'fin': fecha_fin}, 'politica': politica, 'tolerancia_minutos': tolerancia,
                'libro': libro, 'dias': detalle}

    # ── política del tramo ────────────────────────────────────────────────
    async def _base_para_reparto(self, empleado_id: int, fecha_inicio: str, fecha_fin: str) -> Tuple[float, float, List[Dict[str, Any]]]:
        dias, info = await self._dias_empleado(empleado_id, fecha_inicio, fecha_fin)
        tolerancia = await self.repo.tolerancia_minutos()
        base = plegar_libro(dias, es_bolsa=self._es_bolsa(info), tolerancia_min=tolerancia)
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
        deuda, fijas, filas = await self._base_para_reparto(empleado_id, fecha_inicio, fecha_fin)
        _, resumen = asignar_minutos(filas, deuda, politica, minutos_a_pagar, fijas)
        # «Llevar todo a cero» perdona lo que las horas extra no alcanzaron a cubrir HOY; si mañana aparece
        # deuda nueva, vuelve a verse pendiente y hay que decidir de nuevo (no se perdona a ciegas).
        perdonados = resumen['pendiente'] if politica == 'CERO' else 0.0
        await self.repo.guardar_politica(empleado_id, fecha_inicio, fecha_fin, politica, minutos_a_pagar, perdonados, usuario, motivo)
        await self.aplicar_politica(empleado_id, fecha_inicio, fecha_fin)
        await self._auditar(usuario_id, usuario, 'DECIDIR_CUADRE', {
            'empleado_id': empleado_id, 'tramo': [fecha_inicio, fecha_fin], 'politica': politica, 'minutos_a_pagar': minutos_a_pagar,
            'minutos_perdonados': round(perdonados, 2), 'cubierto': round(resumen['cubierto'], 2), 'a_pagar': round(resumen['a_pagar'], 2),
            'no_pagadas': round(resumen['no_pagadas'], 2), 'motivo': motivo})
        return await self.libro_empleado(empleado_id, fecha_inicio, fecha_fin)

    async def quitar_politica(self, empleado_id: int, fecha_inicio: str, fecha_fin: str, usuario: str, usuario_id: Optional[int]) -> Dict[str, Any]:
        await self.repo.quitar_politica(empleado_id, fecha_inicio, fecha_fin)
        await self._auditar(usuario_id, usuario, 'QUITAR_POLITICA_CUADRE', {'empleado_id': empleado_id, 'tramo': [fecha_inicio, fecha_fin]})
        return await self.libro_empleado(empleado_id, fecha_inicio, fecha_fin)

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
