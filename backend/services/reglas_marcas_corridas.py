"""
«Correr esta regla» / «Apagar esta regla»: encendido gradual de las Reglas de
marcaciones, regla por regla, en segundo plano.

Una corrida:
  1. Busca los días candidatos: SOLO el tramo abierto, SOLO jornadas terminadas
     (nunca hoy) y nunca días cubiertos por un cierre de área o turno. Los
     períodos cerrados no se tocan jamás.
  2. Toma la foto «antes» de esos días.
  3. Enciende (o apaga) la regla, refresca el motor y recalcula SOLO esos días,
     uno por uno, con el mismo motor de siempre.
  4. Toma la foto «después» y entrega el detalle de qué cambió, día por día.

Corre como tarea en segundo plano (una corrida a la vez): la pantalla pregunta
el avance cada pocos segundos, porque la petición web no puede esperar minutos.
"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from backend.core.database import db
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.reglas_marcas import ReglasMarcasRepository
from backend.repositories.seguridad import SeguridadRepository
from backend.services import quantum_matrix_engine as qme
from backend.services.asistencia_service import AsistenciaService
from backend.services.reglas_marcas_runtime import cargar as cargar_reglas

JOBS: Dict[str, Dict[str, Any]] = {}
_MAX_JOBS_GUARDADOS = 20

CAMPOS_FOTO = ('estado', 'hora_entrada_real', 'hora_salida_real', 'horas_trabajadas',
               'minutos_atraso', 'minutos_salida_adelantada', 'minutos_deuda',
               'minutos_extra_bruto', 'minutos_colacion', 'observaciones')


def _hay_corrida_en_curso() -> Optional[Dict[str, Any]]:
    for j in JOBS.values():
        if j.get('estado') == 'en_curso':
            return j
    return None


def job_publico(j: Dict[str, Any]) -> Dict[str, Any]:
    return {k: j.get(k) for k in ('id', 'regla_id', 'secuencia', 'encender', 'estado',
                                  'avance', 'total', 'resultado', 'error', 'inicio', 'fin')}


async def _candidatos(repo: ReglasMarcasRepository, regla: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Días del tramo abierto (jornadas terminadas, sin cierres de área o turno) cuya
    secuencia de marcas consumidas es exactamente la de la regla. Incluye días con
    marcas manuales: la regla también los leerá."""
    desde = await repo.inicio_tramo_abierto()
    hoy = datetime.now().strftime("%Y-%m-%d")
    rows = await repo.db.fetch_all("""
        WITH ci AS (SELECT id FROM turnos WHERE tipo_programacion = ?),
        a AS (SELECT a.id AS aid, a.empleado_id, a.fecha, a.turno_asignado_id,
                     a.marcas_consumidas_ids AS ids
                FROM asistencias a
               WHERE a.turno_asignado_id IN (SELECT id FROM ci)
                 AND a.fecha >= ? AND a.fecha < ?
                 AND a.marcas_consumidas_ids ~ '^\\[ *[0-9]'),
        x AS (SELECT a.aid, a.empleado_id, a.fecha, a.turno_asignado_id,
                     CASE WHEN LOWER(COALESCE(o.tipo, l.tipo)) IN ('entrada','entry','e','in','1') THEN 'E'
                          WHEN LOWER(COALESCE(o.tipo, l.tipo)) IN ('salida','exit','s','out','0','2') THEN 'S'
                          ELSE '?' END AS t,
                     l.fecha_hora
                FROM a
               CROSS JOIN LATERAL jsonb_array_elements_text(a.ids::jsonb) j(v)
                JOIN logs_raw l ON l.id = j.v::bigint
                LEFT JOIN logs_tipo_override o ON o.log_id = l.id),
        d AS (SELECT aid, empleado_id, fecha, turno_asignado_id,
                     STRING_AGG(t, '' ORDER BY fecha_hora) AS pat
                FROM x GROUP BY aid, empleado_id, fecha, turno_asignado_id)
        SELECT d.empleado_id, d.fecha,
               e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS persona
          FROM d
          JOIN empleados e ON e.id = d.empleado_id
         WHERE d.pat = ?
           AND NOT EXISTS (
                SELECT 1 FROM cierres_periodos cp
                 WHERE cp.fecha_inicio <= d.fecha AND cp.fecha_fin >= d.fecha
                   AND (cp.area IS NULL OR cp.turno_id = d.turno_asignado_id
                        OR cp.area = (SELECT ar.nombre FROM historial_areas h
                                        LEFT JOIN areas ar ON ar.id = h.area_id
                                       WHERE h.empleado_id = d.empleado_id
                                         AND d.fecha BETWEEN h.fecha_desde AND COALESCE(h.fecha_hasta, '2099-12-31')
                                       LIMIT 1)))
         ORDER BY d.fecha, persona
    """, (regla['tipo_horario'], desde, hoy, regla['secuencia']))
    return [dict(r) for r in rows]


async def _foto(pares: List[Tuple[int, str]]) -> Dict[Tuple[int, str], Dict[str, Any]]:
    out: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for eid, f in pares:
        r = await db.fetch_one(
            "SELECT estado, hora_entrada_real, hora_salida_real, horas_trabajadas, minutos_atraso, "
            "minutos_salida_adelantada, minutos_deuda, minutos_extra_bruto, minutos_colacion, observaciones "
            "FROM asistencias WHERE empleado_id = ? AND fecha = ?", (eid, f))
        out[(eid, f)] = dict(r) if r else {}
    return out


def _num(x) -> float:
    try:
        return round(float(x or 0.0), 2)
    except (TypeError, ValueError):
        return 0.0


def _difiere(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Qué cambió entre la foto antes y después (números redondeados a 2 decimales)."""
    cambios: Dict[str, Any] = {}
    for campo in CAMPOS_FOTO:
        va, vb = a.get(campo), b.get(campo)
        if campo in ('horas_trabajadas', 'minutos_atraso', 'minutos_salida_adelantada',
                     'minutos_deuda', 'minutos_extra_bruto', 'minutos_colacion'):
            if _num(va) != _num(vb):
                cambios[campo] = {'antes': _num(va), 'despues': _num(vb)}
        else:
            if (va or '') != (vb or ''):
                cambios[campo] = {'antes': va, 'despues': vb}
    return cambios


# ── Ensayo del asistente: «cómo quedaría», sin guardar nada ──────────────────
_ensayo_en_curso = False


async def ensayar_regla(regla: Dict[str, Any], propuesta: Dict[str, Any],
                        limite: int = 3) -> Dict[str, Any]:
    """Calcula hasta `limite` días reales (los más recientes del tramo abierto con la
    secuencia de la regla) usando la regla PROPUESTA del editor —esté guardada o no,
    encendida o no— y devuelve el antes → después de cada uno.

    NO guarda nada: el motor corre en modo recolección (collect_only, cero escrituras)
    y la regla propuesta viaja en la variable de contexto REGLAS_MARCAS_ENSAYO, que
    solo ve este cálculo; el resto del servidor sigue leyendo las reglas encendidas."""
    global _ensayo_en_curso
    if _ensayo_en_curso:
        return {'error': 'Ya hay un ensayo en curso. Espere unos segundos y vuelva a intentar.'}
    if _hay_corrida_en_curso():
        return {'error': 'Hay una corrida de regla en curso. Espere a que termine para ensayar.'}
    _ensayo_en_curso = True
    try:
        repo = ReglasMarcasRepository(db)
        desde = await repo.inicio_tramo_abierto()
        hoy = datetime.now().strftime("%Y-%m-%d")
        dias = await repo.dias_ejemplo(regla['tipo_horario'], regla['secuencia'], desde, hoy, limite)
        if not dias:
            return {'dias': [], 'total_candidatos': 0}
        pares = [(d['empleado_id'], d['fecha']) for d in dias]
        antes = await _foto(pares)

        # El mundo tal como está (reglas encendidas) + la regla propuesta en su secuencia.
        reglas_ensayo = dict(qme.REGLAS_MARCAS_ACTIVAS)
        reglas_ensayo[regla['secuencia']] = {
            'secuencia': regla['secuencia'],
            'lectura': propuesta['lectura'],
            'colacion': propuesta['colacion'],
            'accion': propuesta['accion'],
        }
        despues: Dict[Tuple[int, str], Dict[str, Any]] = {}
        service = AsistenciaService(AsistenciaRepository(db))
        token = qme.REGLAS_MARCAS_ENSAYO.set(reglas_ensayo)
        try:
            for eid, f in pares:
                r = await service.reprocesar_periodo_empleado(eid, f, f, force=True, collect_only=True)
                fila = next((c for c in (r.get('_collect') or []) if str(c.get('fecha')) == f), None)
                if fila is not None:
                    despues[(eid, f)] = {campo: fila.get(campo) for campo in CAMPOS_FOTO}
                elif any(p == (eid, f) for p in (r.get('_delete_collect') or [])):
                    despues[(eid, f)] = {}
                else:
                    despues[(eid, f)] = dict(antes.get((eid, f), {}))  # sin cambio
        finally:
            qme.REGLAS_MARCAS_ENSAYO.reset(token)

        detalle = []
        for d in dias:
            clave = (d['empleado_id'], d['fecha'])
            cambios = _difiere(antes.get(clave, {}), despues.get(clave, {}))
            detalle.append({
                'empleado_id': d['empleado_id'], 'persona': d['persona'], 'fecha': d['fecha'],
                'marcas': d['marcas'],
                'antes': antes.get(clave, {}), 'despues': despues.get(clave, {}),
                'cambios': cambios, 'solo_aviso': bool(cambios) and set(cambios) <= {'observaciones'},
            })
        return {'dias': detalle, 'total_candidatos': int(dias[0].get('total') or len(dias))}
    finally:
        _ensayo_en_curso = False


def iniciar_corrida(regla: Dict[str, Any], encender: bool, user_id: int, username: str) -> Dict[str, Any]:
    """Valida y lanza la corrida en segundo plano. Devuelve el job o {'error': ...}."""
    en_curso = _hay_corrida_en_curso()
    if en_curso:
        return {'error': f"Ya hay una corrida en curso (regla {en_curso.get('secuencia')}). Espere a que termine."}
    if encender and regla.get('activa'):
        return {'error': 'Esta regla ya está encendida.'}
    if not encender and not regla.get('activa'):
        return {'error': 'Esta regla ya está apagada.'}
    job_id = uuid.uuid4().hex[:12]
    job = {
        'id': job_id, 'regla_id': regla['id'], 'secuencia': regla['secuencia'],
        'encender': encender, 'estado': 'en_curso', 'avance': 0, 'total': None,
        'resultado': None, 'error': None,
        'inicio': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'fin': None,
    }
    if len(JOBS) >= _MAX_JOBS_GUARDADOS:
        viejos = sorted((j for j in JOBS.values() if j['estado'] != 'en_curso'), key=lambda j: j['inicio'])
        for v in viejos[:len(JOBS) - _MAX_JOBS_GUARDADOS + 1]:
            JOBS.pop(v['id'], None)
    JOBS[job_id] = job
    asyncio.create_task(_ejecutar(job, user_id, username))
    return job


async def _ejecutar(job: Dict[str, Any], user_id: int, username: str) -> None:
    repo = ReglasMarcasRepository(db)
    try:
        regla = await repo.obtener(job['regla_id'])
        if not regla:
            raise RuntimeError('La regla no existe.')
        cand = await _candidatos(repo, regla)
        pares = [(c['empleado_id'], c['fecha']) for c in cand]
        persona_de = {(c['empleado_id'], c['fecha']): c['persona'] for c in cand}
        job['total'] = len(pares)
        antes = await _foto(pares)

        # Encender/apagar y refrescar el motor ANTES de recalcular.
        await db.execute(
            "UPDATE reglas_marcas SET activa = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if job['encender'] else 0, username, regla['id'])
        )
        await cargar_reglas(db)

        service = AsistenciaService(AsistenciaRepository(db))
        for n, (eid, f) in enumerate(pares, 1):
            await service.reprocesar_periodo_empleado(eid, f, f, force=True)
            job['avance'] = n

        despues = await _foto(pares)
        detalle = []
        solo_aviso = 0
        for clave in pares:
            cambios = _difiere(antes.get(clave, {}), despues.get(clave, {}))
            if not cambios:
                continue
            es_solo_aviso = set(cambios) <= {'observaciones'}
            if es_solo_aviso:
                solo_aviso += 1
            detalle.append({
                'empleado_id': clave[0], 'persona': persona_de.get(clave, ''), 'fecha': clave[1],
                'solo_aviso': es_solo_aviso, 'cambios': cambios,
            })
        resultado = {
            'dias_revisados': len(pares),
            'dias_cambiados': len(detalle),
            'dias_solo_aviso': solo_aviso,
            'dias_con_horas_distintas': len(detalle) - solo_aviso,
            'detalle': detalle,
        }
        job['resultado'] = resultado
        job['estado'] = 'termino'
        accion_txt = 'CORRER_REGLA' if job['encender'] else 'APAGAR_REGLA'
        await SeguridadRepository(db).log_auditoria(
            user_id, username, accion_txt, 'REGLAS_MARCAS',
            json.dumps({'regla_id': regla['id'], 'secuencia': regla['secuencia'],
                        'dias_revisados': len(pares), 'dias_cambiados': len(detalle),
                        'dias_solo_aviso': solo_aviso}, ensure_ascii=False)
        )
        logger.success(f"⚙️ Regla {regla['secuencia']} {'encendida' if job['encender'] else 'apagada'}: "
                       f"{len(pares)} días revisados, {len(detalle)} cambiaron ({solo_aviso} solo aviso).")
    except Exception as e:
        logger.exception(f"Corrida de regla falló: {e}")
        job['error'] = (f"{e}. El estado de la regla quedó como se dejó al iniciar; "
                        f"revise y vuelva a correrla o apáguela.")
        job['estado'] = 'fallo'
    finally:
        job['fin'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
