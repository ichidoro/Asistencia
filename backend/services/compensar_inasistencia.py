# -*- coding: utf-8 -*-
"""Compensar una inasistencia: una sola acción, desde el día faltado (reglas del dueño, 27-10-2026).

- Con una jornada EXTRA (validada con el monto fijo; venga de un día libre, de un feriado o de un +2): cubre la
  inasistencia COMPLETA sin importar sus horas y se gasta: deja de pagarse con el monto fijo y queda COMPENSATORIA.
- Con horas extra: minuto a minuto; las horas extra que sobran después de pagar la deuda del tramo deben cubrir todo
  el turno del día faltado.
- La jornada (o las horas extra) y la inasistencia van en el mismo tramo, y ninguno de los dos días puede estar cerrado.

Reemplaza a «Días Compensatorios» (barra de la grilla) y a «Reasignar / Mover» (modal de acciones)."""
import json
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger

ESTADOS_INASISTENCIA = ('INASISTENCIA', 'FALTA')
TIPO_DE_JORNADA = {'FERIADO': 'feriado', 'DIA_LIBRE': 'día libre', 'COBERTURA_TURNO': '+2'}
TAG_COMPENSA = '[COMPENSA_INASISTENCIA {fecha}]'


def evaluar_opciones(dia: Optional[Dict[str, Any]], jornadas: Iterable[Dict[str, Any]], disponibles_min: float,
                     cerradas: Iterable[str] = (), usadas: Iterable[str] = (), justificada: bool = False,
                     es_bolsa: bool = False) -> Dict[str, Any]:
    """Con qué se puede compensar un día faltado. Sin base de datos: recibe el día, las jornadas especiales del tramo y
    las horas extra disponibles, y devuelve lo que la ventana muestra (y lo que el servidor exige al guardar)."""
    dia = dia or {}
    cerradas, usadas = set(cerradas), set(usadas)
    requerido = int(round(float(dia.get('horas_teoricas') or 0.0) * 60.0))
    estado = dia.get('estado') or ''
    bloqueo = None
    if estado == 'INASISTENCIA_COMPENSADA':
        bloqueo = 'Esta inasistencia ya está compensada.'
    elif estado not in ESTADOS_INASISTENCIA:
        bloqueo = 'Este día no es una inasistencia.'
    elif es_bolsa:
        bloqueo = 'En Bolsa Flexible las inasistencias no se compensan por aquí.'
    elif justificada:
        bloqueo = 'El día tiene una justificación (licencia, vacaciones o permiso): no se compensa.'
    elif not requerido:
        bloqueo = 'El día no tiene horas de turno que cubrir.'
    elif dia.get('fecha') in cerradas:
        bloqueo = 'El tramo de este día está cerrado.'

    extras: List[Dict[str, Any]] = []
    por_validar: List[Dict[str, Any]] = []
    for j in jornadas:
        if j.get('fecha') in cerradas or j.get('fecha') in usadas or j.get('fecha') == dia.get('fecha'):
            continue
        item = {'fecha': j.get('fecha'), 'origen': j.get('origen'),
                'tipo': TIPO_DE_JORNADA.get(j.get('origen'), 'jornada especial'),
                'minutos': int(round(float(j.get('minutos_trabajados') or 0.0))),
                'hora_entrada': j.get('hora_entrada'), 'hora_salida': j.get('hora_salida')}
        if j.get('estado') == 'EXTRA':
            extras.append(item)
        elif j.get('estado') in ('JORNADA_ESPECIAL', 'PENDIENTE'):
            por_validar.append(item)

    disponibles = max(0.0, float(disponibles_min or 0.0))
    return {
        'fecha': dia.get('fecha'),
        'requerido_min': requerido,
        'turno': f"{dia.get('hora_entrada_teorica') or '--:--'} a {dia.get('hora_salida_teorica') or '--:--'}",
        'bloqueo': bloqueo,
        'extras': extras,
        'por_validar': por_validar,
        'horas_extra': {'disponibles_min': round(disponibles, 2), 'alcanza': bool(requerido) and round(disponibles) >= requerido},
    }


async def bolsa_despues_de_deuda(service, empleado_id: int, fecha: str, bolsa: Dict[str, Any]) -> Dict[str, Any]:
    """Regla del dueño (26-10-2026): las inasistencias compensables van al final; solo se compensan con las horas extra
    que sobran después de pagar toda la deuda (exceso de colación, permisos, atrasos y salidas adelantadas)."""
    try:
        from backend.services.cuadre_service import CuadreService
        cs = CuadreService(service)
        t_ini, t_fin = await cs.tramo_de(str(fecha)[:10])
        lib = await cs.libro_empleado(int(empleado_id), t_ini, t_fin)
        if lib.get('es_bolsa'):
            return bolsa
        sobran = max(0.0, float(lib['libro'].get('he_a_pagar') or 0.0))
        bolsa = dict(bolsa)
        bolsa["minutos_disponibles"] = round(min(float(bolsa.get("minutos_disponibles") or 0.0), sobran), 2)
        bolsa["regla"] = "Solo se compensan inasistencias con las horas extra que sobran después de pagar toda la deuda."
    except Exception as e_cuadre:
        logger.warning(f"[Cuadre] No se pudo revisar la deuda antes de compensar: {e_cuadre}")
    return bolsa


async def _es_bolsa(db, empleado_id: int, fecha: str) -> bool:
    row = await db.fetch_one("""
        SELECT t.tipo_programacion FROM asignacion_turnos at JOIN turnos t ON at.turno_id = t.id
         WHERE at.empleado_id = ? AND at.fecha_inicio <= ? AND (at.fecha_fin IS NULL OR at.fecha_fin >= ?)
         ORDER BY at.fecha_inicio DESC LIMIT 1""", (empleado_id, fecha, fecha))
    return bool(row and row.get('tipo_programacion') in ('BOLSA_FLEXIBLE', 'FLEXIBLE_BOLSA'))


async def opciones(service, empleado_id: int, fecha: str) -> Dict[str, Any]:
    """Lee de la base lo que `evaluar_opciones` necesita para el día faltado de una persona."""
    repo, db = service.repository, service.repository.db
    dia = await repo.get_asistencia(empleado_id, fecha)
    periodo = await repo.get_periodo_por_fecha(fecha)
    t_ini, t_fin = str(periodo['fecha_inicio'])[:10], str(periodo['fecha_fin'])[:10]
    jornadas = [dict(r) for r in await db.fetch_all("""
        SELECT fecha, estado, origen, minutos_trabajados, hora_entrada, hora_salida FROM jornadas_especiales
         WHERE empleado_id = ? AND fecha BETWEEN ? AND ? ORDER BY fecha""", (empleado_id, t_ini, t_fin))]
    usadas = {str(r['fecha_destino'])[:10] for r in await db.fetch_all(
        "SELECT fecha_destino FROM intercambios_dias WHERE empleado_solicitante_id = ? AND fecha_destino BETWEEN ? AND ?",
        (empleado_id, t_ini, t_fin))}
    cerradas = {f for f in {fecha, *(j['fecha'] for j in jornadas)} if await repo.check_fecha_cerrada(f, empleado_id)}
    justificada = bool(await db.fetch_one(
        "SELECT id FROM justificaciones WHERE empleado_id = ? AND ? BETWEEN fecha_inicio AND fecha_fin", (empleado_id, fecha)))
    bolsa = await bolsa_despues_de_deuda(service, empleado_id, fecha, await repo.get_bolsa_he_disponible(empleado_id, t_ini, t_fin))
    res = evaluar_opciones(dict(dia) if dia else {'fecha': fecha}, jornadas, bolsa.get('minutos_disponibles') or 0.0,
                           cerradas=cerradas, usadas=usadas, justificada=justificada, es_bolsa=await _es_bolsa(db, empleado_id, fecha))
    res['tramo'] = [t_ini, t_fin]
    return res


async def _auditar(db, usuario_id: Optional[int], usuario: str, accion: str, detalle: Dict[str, Any]) -> None:
    try:
        from backend.repositories.seguridad import SeguridadRepository
        await SeguridadRepository(db).log_auditoria(usuario_id, usuario, accion, 'Marcaciones', json.dumps(detalle, ensure_ascii=False, default=str))
    except Exception as e:
        logger.warning(f"[Compensar] Auditoría no registrada ({accion}): {e}")


async def compensar(service, empleado_id: int, fecha: str, modo: str, fecha_jornada: Optional[str],
                    observaciones: Optional[str], usuario: str, usuario_id: Optional[int]) -> Dict[str, Any]:
    """Guarda la compensación si las reglas lo permiten (se vuelven a revisar aquí, no se confía en la pantalla)."""
    db = service.repository.db
    op = await opciones(service, empleado_id, fecha)
    if op['bloqueo']:
        raise ValueError(op['bloqueo'])
    motivo = (observaciones or '').strip() or None
    if modo == 'EXTRA':
        jornada = next((e for e in op['extras'] if e['fecha'] == fecha_jornada), None)
        if not jornada:
            raise ValueError('Elija una jornada EXTRA del mismo tramo que no esté usada ni cerrada.')
        async with db.transaction():
            await service.repository.create_intercambio({
                'empleado_solicitante_id': empleado_id, 'empleado_receptor_id': empleado_id, 'fecha_origen': fecha,
                'fecha_destino': fecha_jornada, 'usuario_id': usuario_id,
                'motivo': motivo or f"Inasistencia compensada con la jornada EXTRA del {fecha_jornada}"})
            await db.execute(
                "UPDATE jornadas_especiales SET estado = 'COMPENSATORIA', observaciones = TRIM(COALESCE(observaciones, '') || ' ' || ?), "
                "updated_at = datetime('now') WHERE empleado_id = ? AND fecha = ? AND estado = 'EXTRA'",
                (TAG_COMPENSA.format(fecha=fecha), empleado_id, fecha_jornada))
        for f in sorted({fecha, fecha_jornada}):
            await service.reprocesar_periodo_empleado(empleado_id=empleado_id, fecha_inicio=f, fecha_fin=f, force=True)
        await _auditar(db, usuario_id, usuario, 'COMPENSAR_INASISTENCIA', {
            'empleado_id': empleado_id, 'fecha': fecha, 'con': 'jornada EXTRA', 'jornada': jornada, 'motivo': motivo})
        return {'success': True, 'mensaje': f"Inasistencia del {fecha} compensada con la jornada EXTRA del {fecha_jornada}."}
    if modo == 'HORAS_EXTRA':
        he = op['horas_extra']
        if not he['alcanza']:
            raise ValueError(f"Las horas extra no alcanzan: hay {int(round(he['disponibles_min']))} min y el turno pide {op['requerido_min']} min.")
        async with db.transaction():
            await service.repository.create_compensacion({
                'empleado_id': empleado_id, 'fecha_inasistencia': fecha, 'minutos': op['requerido_min'], 'usuario_id': usuario_id,
                'observaciones': motivo or f"Inasistencia compensada con {op['requerido_min']} min de horas extra"})
        await service.reprocesar_periodo_empleado(empleado_id=empleado_id, fecha_inicio=fecha, fecha_fin=fecha, force=True)
        await _auditar(db, usuario_id, usuario, 'COMPENSAR_INASISTENCIA', {
            'empleado_id': empleado_id, 'fecha': fecha, 'con': 'horas extra', 'minutos': op['requerido_min'], 'motivo': motivo})
        return {'success': True, 'mensaje': f"Inasistencia del {fecha} compensada con {op['requerido_min']} min de horas extra."}
    raise ValueError('Elija con qué compensar: una jornada EXTRA o horas extra.')


async def quitar(service, empleado_id: int, fecha: str, usuario: str, usuario_id: Optional[int]) -> Dict[str, Any]:
    """Deshace la compensación del día faltado: la jornada usada vuelve a ser EXTRA y las horas extra vuelven a quedar libres."""
    repo, db = service.repository, service.repository.db
    if await repo.check_fecha_cerrada(fecha, empleado_id):
        raise ValueError('El tramo de este día está cerrado.')
    inter = [dict(r) for r in await db.fetch_all(
        "SELECT id, fecha_destino FROM intercambios_dias WHERE empleado_solicitante_id = ? AND fecha_origen = ?", (empleado_id, fecha))]
    comps = [dict(r) for r in await db.fetch_all(
        "SELECT id, minutos FROM compensaciones_he_inasistencia WHERE empleado_id = ? AND fecha_inasistencia = ?", (empleado_id, fecha))]
    if not inter and not comps:
        raise ValueError('Este día no tiene una compensación que quitar.')
    destinos = sorted({str(i['fecha_destino'])[:10] for i in inter})
    for d in destinos:
        if await repo.check_fecha_cerrada(d, empleado_id):
            raise ValueError(f"La jornada usada ({d}) está en un tramo cerrado.")
    async with db.transaction():
        for d in destinos:
            await db.execute(
                "UPDATE jornadas_especiales SET estado = 'EXTRA', observaciones = TRIM(REPLACE(COALESCE(observaciones, ''), ?, '')), "
                "updated_at = datetime('now') WHERE empleado_id = ? AND fecha = ? AND estado = 'COMPENSATORIA'",
                (TAG_COMPENSA.format(fecha=fecha), empleado_id, d))
        for i in inter:
            await db.execute("DELETE FROM intercambios_dias WHERE id = ?", (i['id'],))
        for c in comps:
            await db.execute("DELETE FROM compensaciones_he_inasistencia WHERE id = ?", (c['id'],))
    for f in sorted({fecha, *destinos}):
        await service.reprocesar_periodo_empleado(empleado_id=empleado_id, fecha_inicio=f, fecha_fin=f, force=True)
    await _auditar(db, usuario_id, usuario, 'QUITAR_COMPENSACION_INASISTENCIA', {
        'empleado_id': empleado_id, 'fecha': fecha, 'jornadas_devueltas': destinos, 'minutos_devueltos': sum(float(c['minutos'] or 0) for c in comps)})
    return {'success': True, 'mensaje': f"Se quitó la compensación del {fecha}."}
