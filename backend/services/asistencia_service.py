"""
Asistencia Service - EL MOTOR (The Engine) ⚙️
Lógica central para procesar marcaciones y calcular asistencias.

REGLAS DE NEGOCIO FUNDAMENTALES:
  1. Las marcas se consumen en orden cronológico ESTRICTO, una sola vez.
  2. Una marca consumida NO se vuelve a usar jamás.
  3. NO se usan ventanas temporales para buscar marcas.
  4. Los anclajes (entrada/salida) solo afectan el CÁLCULO de horas pagadas,
     NUNCA la búsqueda o consumo de marcas.
  5. El tipo BioAlba (Entrada/Salida) es la fuente de verdad para la clasificación.
"""
import asyncio
import json
import math
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from loguru import logger

from backend.core.config import settings
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.empleado import EmpleadoRepository
from backend.services.quantum_matrix_engine import (
    QuantumPhaseTopology,
    TensorMarkDeduplicator,
    MultiPointScheduleSolver,
    QUBOEnergyOptimizer,
    QuantumMatrixEngine
)
from asyncio import Lock

CHILE_TZ = ZoneInfo(settings.TIMEZONE)

def _get_now_local() -> datetime:
    """Retorna la fecha/hora actual naive en la zona horaria configurada (America/Santiago)"""
    return datetime.now(CHILE_TZ).replace(tzinfo=None)

_reproceso_lock = Lock()
_reproceso_status: Dict[str, Any] = {}
_empleados_en_reproceso: set = set()

# ─── Job Progress Registry ────────────────────────────────────────────────────
# Dict en memoria: {job_id: {...progreso...}}
# No necesita persistencia — vive mientras el proceso esté activo.
_JOB_REGISTRY: Dict[str, Dict[str, Any]] = {}


def get_reproceso_status() -> Dict[str, Any]:
    return _reproceso_status


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Retorna el estado actual de un job de reproceso por ID."""
    return _JOB_REGISTRY.get(job_id)


def _init_job(job_id: str, empleado_id: int, total_days: int, fecha_inicio: str) -> None:
    _JOB_REGISTRY[job_id] = {
        "status": "syncing",          # fase inicial: BioAlba
        "phase_label": "Descargando marcaciones BioAlba...",
        "empleado_id": empleado_id,
        "current_day": fecha_inicio,
        "day_index": 0,
        "total_days": total_days,
        "pct": 0,
        "procesados": 0,
        "errores": 0,
        "elapsed_ms": 0,
    }


def _update_job(job_id: str, **kwargs) -> None:
    if job_id in _JOB_REGISTRY:
        _JOB_REGISTRY[job_id].update(kwargs)


def _complete_job(job_id: str, procesados: int, errores: int, elapsed_ms: int) -> None:
    if job_id in _JOB_REGISTRY:
        _JOB_REGISTRY[job_id].update({
            "status": "completed",
            "pct": 100,
            "procesados": procesados,
            "errores": errores,
            "elapsed_ms": elapsed_ms,
        })


class AsistenciaService:

    def __init__(self, repository: AsistenciaRepository):
        self.repository = repository
        # FASE 2: Repositorio de Horas Extras para doble-escritura
        from backend.repositories.hora_extra import HoraExtraRepository
        self.he_repo = HoraExtraRepository(repository.db)

    async def is_fecha_cerrada_empleado(self, empleado_id: int, fecha: str) -> bool:
        """
        Verifica si la fecha dada está cerrada para el área del empleado.
        """
        return await self.repository.check_fecha_cerrada(fecha, empleado_id)

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(date_str[:len(fmt.replace("%Y","0000").replace("%m","00").replace("%d","00").replace("%H","00").replace("%M","00").replace("%S","00"))], fmt)
            except Exception:
                pass
        try:
            return datetime.fromisoformat(date_str[:10])
        except Exception:
            return None

    def _apply_rounding(self, dt: datetime, intervalo: int) -> datetime:
        if not intervalo or intervalo <= 0:
            return dt
        total_minutes = dt.hour * 60 + dt.minute
        rounded = round(total_minutes / intervalo) * intervalo
        return dt.replace(hour=rounded // 60, minute=rounded % 60, second=0, microsecond=0)

    @staticmethod
    async def _empty_list_coro():
        return []

    # ─────────────────────────────────────────────────────────────────────────
    # BULK CONTEXT LOADER
    # ─────────────────────────────────────────────────────────────────────────

    async def get_bulk_context(self, fecha: str, area: Optional[str] = None, empleado_ids: Optional[set] = None) -> Dict[str, Any]:
        """
        Recupera TODO el contexto necesario para procesar un día en una sola ráfaga de queries.
        Evita el patrón N+1 de ráfagas individuales por empleado.
        
        Args:
            empleado_ids: Si se especifica, limita el recálculo solo a esos IDs (optimización post-sync).
                          None = procesa todos los empleados activos (comportamiento original).
        """
        db = self.repository.db
        log_msg = f"🚚 Cargando contexto masivo para {fecha}"
        if empleado_ids:
            log_msg += f" ({len(empleado_ids)} empleados del batch)"
        elif area:
            log_msg += f" (Área: {area})"
        else:
            log_msg += " (Área: Todas)"
        log_msg += "..."
        logger.info(log_msg)

        if empleado_ids:
            # Modo batch-scoped: solo los empleados que tuvieron marcaciones nuevas
            # Incluye inactivos con fecha_salida (baja reciente) para procesar sus marcaciones pendientes.
            ph = ','.join('?' * len(empleado_ids))
            q_emp = f"SELECT * FROM empleados WHERE id IN ({ph}) AND (activo = 1 OR (activo = 0 AND fecha_salida IS NOT NULL)) AND (excluido_asistencia = 0 OR excluido_asistencia IS NULL)"
            params_emp = list(empleado_ids)
        else:
            # Modo completo: todos los activos (comportamiento original)
            q_emp = "SELECT * FROM empleados WHERE (activo = 1 OR (fecha_salida IS NOT NULL AND fecha_salida >= ?)) AND (excluido_asistencia = 0 OR excluido_asistencia IS NULL)"
            params_emp = [fecha]
            if area:
                q_emp += " AND area = ?"
                params_emp.append(area)
        empleados_rows = await db.fetch_all(q_emp, tuple(params_emp))
        emp_ids = [e['id'] for e in empleados_rows]
        if not emp_ids:
            return {}

        ids_placeholder = ','.join('?' * len(emp_ids))

        # Asignaciones de turnos vigentes
        q_asig = f"""
            SELECT t.*, a.empleado_id, a.fecha_inicio as asignacion_desde, a.semana_inicio
            FROM turnos t
            JOIN asignacion_turnos a ON t.id = a.turno_id
            WHERE a.empleado_id IN ({ids_placeholder})
              AND a.fecha_inicio <= ?
              AND (a.fecha_fin IS NULL OR a.fecha_fin >= ?)
        """
        asig_rows = await db.fetch_all(q_asig, tuple(emp_ids) + (fecha, fecha))
        asignaciones = {r['empleado_id']: dict(r) for r in asig_rows}

        # Justificaciones
        q_just = f"""
            SELECT j.*, t.nombre as tipo_nombre, t.nomenclatura as tipo_nomenclatura,
                   t.con_goce_sueldo, t.pagador, t.dias_corridos, t.genera_deuda_horaria,
                   t.sobreescribe_feriados, t.descuenta_remuneracion,
                   t.es_horas_sindicales, t.es_por_horas
            FROM justificaciones j
            JOIN justificacion_tipos t ON j.tipo_id = t.id
            WHERE j.empleado_id IN ({ids_placeholder})
              AND (date(j.fecha_inicio) <= date(?) AND date(j.fecha_fin) >= date(?))
        """
        just_rows = await db.fetch_all(q_just, tuple(emp_ids) + (fecha, fecha))
        justificaciones = {}
        for j in just_rows:
            eid = j['empleado_id']
            justificaciones.setdefault(eid, []).append(dict(j))

        # Logs (ventana generosa D-1..D+1 para capturar turnos nocturnos)
        dt = datetime.strptime(fecha, "%Y-%m-%d")
        logs_ini = (dt - timedelta(days=1)).strftime("%Y-%m-%d") + " 00:00:00"
        logs_fin = (dt + timedelta(days=1)).strftime("%Y-%m-%d") + " 23:59:59"
        q_logs = f"""
            SELECT * FROM logs_raw
            WHERE empleado_id IN ({ids_placeholder})
              AND fecha_hora BETWEEN ? AND ?
            ORDER BY fecha_hora ASC
        """
        logs_rows = await db.fetch_all(q_logs, tuple(emp_ids) + (logs_ini, logs_fin))
        logs_map = {}
        for l in logs_rows:
            eid = l['empleado_id']
            logs_map.setdefault(eid, []).append(dict(l))

        # Turnos (dias) - config por semana y día
        turno_ids = list({r['id'] for r in asig_rows})
        turnos_map = {}
        turno_weeks = {}
        if turno_ids:
            t_placeholder = ','.join('?' * len(turno_ids))
            td_rows = await db.fetch_all(
                f"SELECT * FROM turno_dias WHERE turno_id IN ({t_placeholder}) ORDER BY num_semana, dia_semana",
                tuple(turno_ids)
            )
            # Mapa de campos del turno padre (descuento_colacion_auto, anclajes, etc.)
            # Estos campos están en `turnos` no en `turno_dias`, por lo que
            # necesitamos inyectarlos en cada config_dia para que el motor los use.
            CAMPOS_TURNO_PADRE = [
                'descuento_colacion_auto', 'minutos_colacion_auto', 'minutos_colacion',
                'anclaje_entrada_minutos', 'anclaje_salida_minutos',
                'tolerancia_retraso_alerta', 'tolerancia_retraso_descuento',
                'redondeo_minutos', 'meta_horas_semanales',
                'tipo_programacion', 'nombre',
                'rotacion_secuencial', 'semana_fallback_sin_marcas',
                'permite_viajes_largos',
            ]

            # Construir dict {turno_id: {campo: valor}} desde los datos de asig_rows
            # Solo con los turno_ids usados en este contexto
            p_rows = await db.fetch_all(
                f"SELECT * FROM turnos WHERE id IN ({t_placeholder})",
                tuple(turno_ids)
            )
            turno_padre_map = {r['id']: dict(r) for r in p_rows}

            for td in td_rows:
                tid = td['turno_id']
                sem = td['num_semana']
                dsem = td['dia_semana']
                config_dia_dict = dict(td)
                # Inyectar campos del turno padre que no están en turno_dias
                padre = turno_padre_map.get(tid, {})
                for campo in CAMPOS_TURNO_PADRE:
                    if campo in padre:
                        config_dia_dict[campo] = padre[campo]
                turnos_map.setdefault(tid, {}).setdefault(sem, {})[dsem] = config_dia_dict
                turno_weeks[tid] = max(turno_weeks.get(tid, 0), sem)


        # Asistencias ayer y hoy (para continuidad nocturna)
        ayer = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
        asist_rows = await db.fetch_all(
            f"SELECT * FROM asistencias WHERE empleado_id IN ({ids_placeholder}) AND fecha IN (?, ?)",
            tuple(emp_ids) + (ayer, fecha)
        )
        asistencias_ayer = {}
        asistencias_hoy = {}
        for a in asist_rows:
            eid = a['empleado_id']
            if a['fecha'] == ayer:
                asistencias_ayer[eid] = dict(a)
            elif a['fecha'] == fecha:
                asistencias_hoy[eid] = dict(a)

        # Horas Extras
        he_rows = await db.fetch_all(
            f"SELECT estado, minutos_autorizados, empleado_id FROM horas_extras WHERE empleado_id IN ({ids_placeholder}) AND fecha = ?",
            tuple(emp_ids) + (fecha,)
        )
        horas_extras_hoy = {r['empleado_id']: dict(r) for r in he_rows}

        # Periodos de empleo
        per_rows = await db.fetch_all(
            f"SELECT * FROM periodos_empleo WHERE empleado_id IN ({ids_placeholder})",
            tuple(emp_ids)
        )
        periodos_emp = {}
        for p in per_rows:
            eid = p['empleado_id']
            periodos_emp.setdefault(eid, []).append(dict(p))

        # First assignments
        fa_rows = await db.fetch_all(
            f"SELECT empleado_id, MIN(fecha_inicio) as min_fecha FROM asignacion_turnos WHERE empleado_id IN ({ids_placeholder}) GROUP BY empleado_id",
            tuple(emp_ids)
        )
        first_assignments = {r['empleado_id']: r['min_fecha'] for r in fa_rows}

        # ── PRECARGA DE CONTEXTO ADICIONAL (Para evitar N+1 queries secuenciales) ──
        # 1. Cargar áreas históricas en la fecha para los empleados
        q_hist_areas = f"""
            SELECT h.empleado_id, a_table.nombre as area_nombre 
            FROM historial_areas h 
            LEFT JOIN areas a_table ON h.area_id = a_table.id
            WHERE h.empleado_id IN ({ids_placeholder}) 
              AND ? BETWEEN h.fecha_desde AND COALESCE(h.fecha_hasta, '2099-12-31')
              AND h.validado = 1
        """
        hist_areas_rows = await db.fetch_all(q_hist_areas, tuple(emp_ids) + (fecha,))
        hist_areas_map = {r['empleado_id']: r['area_nombre'] for r in hist_areas_rows}

        # 2. Cargar cierres vigentes en la fecha
        closures_rows = await db.fetch_all(
            "SELECT area FROM cierres_periodos WHERE ? BETWEEN fecha_inicio AND fecha_fin",
            (fecha,)
        )
        closed_areas = {r['area'] for r in closures_rows}
        has_global_closure = None in closed_areas or any(x is None for x in closed_areas)

        # 3. Determinar para cada empleado si está cerrado
        closed_dates = {}
        for e in empleados_rows:
            eid = e['id']
            emp_area = hist_areas_map.get(eid) or e['area']
            is_closed = False
            if closures_rows:
                if has_global_closure:
                    is_closed = True
                elif emp_area in closed_areas:
                    is_closed = True
            
            if is_closed:
                closed_dates[eid] = {fecha}
            else:
                closed_dates[eid] = set()

        # 4. Intercambios
        q_intercambios = f"""
            SELECT * FROM intercambios_dias
            WHERE (empleado_solicitante_id IN ({ids_placeholder}) OR empleado_receptor_id IN ({ids_placeholder}))
              AND (fecha_origen = ? OR fecha_destino = ?)
              AND estado = 'APROBADO'
        """
        inter_rows = await db.fetch_all(q_intercambios, tuple(emp_ids) + tuple(emp_ids) + (fecha, fecha))
        intercambios_map = {}
        for row in inter_rows:
            row_dict = dict(row)
            sol_id = row_dict['empleado_solicitante_id']
            rec_id = row_dict['empleado_receptor_id']
            if sol_id in emp_ids:
                intercambios_map.setdefault(sol_id, {})[fecha] = row_dict
            if rec_id in emp_ids:
                intercambios_map.setdefault(rec_id, {})[fecha] = row_dict

        # 5. Compensaciones
        q_compensaciones = f"""
            SELECT * FROM compensaciones_he_inasistencia
            WHERE empleado_id IN ({ids_placeholder})
              AND fecha_inasistencia = ?
        """
        comp_rows = await db.fetch_all(q_compensaciones, tuple(emp_ids) + (fecha,))
        compensaciones_map = {}
        for row in comp_rows:
            row_dict = dict(row)
            eid = row_dict['empleado_id']
            compensaciones_map.setdefault(eid, {}).setdefault(fecha, []).append(row_dict)

        # 6. Jornadas Especiales
        q_jornadas_esp = f"""
            SELECT * FROM jornadas_especiales
            WHERE empleado_id IN ({ids_placeholder})
              AND fecha = ?
        """
        je_rows = await db.fetch_all(q_jornadas_esp, tuple(emp_ids) + (fecha,))
        jornadas_especiales_map = {}
        for row in je_rows:
            row_dict = dict(row)
            eid = row_dict['empleado_id']
            jornadas_especiales_map.setdefault(eid, {})[fecha] = row_dict

        # 7. Último record de asistencia anterior a la fecha para rotativos
        q_rot = f"""
            SELECT a.empleado_id, a.num_semana_ganadora
            FROM asistencias a
            INNER JOIN (
                SELECT empleado_id, MAX(fecha) as max_fecha
                FROM asistencias
                WHERE empleado_id IN ({ids_placeholder}) AND fecha < ?
                GROUP BY empleado_id
            ) m ON a.empleado_id = m.empleado_id AND a.fecha = m.max_fecha
        """
        rot_rows = await db.fetch_all(q_rot, tuple(emp_ids) + (fecha,))
        rot_map = {}
        for r in rot_rows:
            if r['num_semana_ganadora'] is not None:
                rot_map[r['empleado_id']] = r['num_semana_ganadora']

        logger.success(f"✅ Contexto masivo cargado: {len(emp_ids)} empleados")

        # Cargar feriados para el año correspondiente (necesario para ley de víspera)
        from backend.services.calendario_service import CalendarioService
        try:
            anio = int(fecha[:4])
            cal_svc = CalendarioService()
            feriados_raw_bulk = await cal_svc.get_feriados(anio)
            # También cargar feriados del año anterior/siguiente si el período cruza año
            feriados_dict_bulk = {f['fecha']: f['descripcion'] for f in feriados_raw_bulk}
        except Exception as _fe:
            logger.warning(f"No se pudieron cargar feriados en bulk_ctx: {_fe}")
            feriados_dict_bulk = {}

        return {
            'empleados': {e['id']: dict(e) for e in empleados_rows},
            'asignaciones': asignaciones,
            'justificaciones': justificaciones,
            'logs': logs_map,
            'turnos': turnos_map,
            'turnos_weeks': turno_weeks,
            'asistencias_ayer': asistencias_ayer,
            'asistencias_hoy': asistencias_hoy,
            'horas_extras': horas_extras_hoy,
            'feriados': feriados_dict_bulk,
            'periodos_empleo': periodos_emp,
            'first_assignments': first_assignments,
            'closed_dates': closed_dates,
            'intercambios': intercambios_map,
            'compensaciones': compensaciones_map,
            'jornadas_especiales': jornadas_especiales_map,
            'rotativo_last_sem_dict': rot_map,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # PROCESAR PERÍODO (MASIVO)
    # ─────────────────────────────────────────────────────────────────────────

    async def procesar_periodo(
        self,
        fecha_inicio: str,
        fecha_fin: Optional[str] = None,
        areas: Optional[Any] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Procesa asistencia para un rango de fechas.
        areas: str, List[str] o None (todos)
        force: si True, reprocesa días ya calculados
        """
        from backend.services.calendario_service import CalendarioService
        if not fecha_fin:
            fecha_fin = fecha_inicio

        # Normalizar areas → lista o None
        area_filter: Optional[str] = None
        areas_list: Optional[List[str]] = None
        if isinstance(areas, list) and areas:
            areas_list = areas
        elif isinstance(areas, str) and areas:
            area_filter = areas

        dt_ini = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        dt_fin = datetime.strptime(fecha_fin, "%Y-%m-%d")
        current = dt_ini
        total = 0
        errores = 0

        while current <= dt_fin:
            fecha = current.strftime("%Y-%m-%d")
            try:
                await self.procesar_dia(fecha, area=area_filter, areas=areas_list, force=force)
                total += 1
            except Exception as e:
                logger.error(f"❌ Error procesando día {fecha}: {e}")
                errores += 1
            current += timedelta(days=1)

        return {'total_dias': total, 'errores': errores, 'fecha_inicio': fecha_inicio, 'fecha_fin': fecha_fin}

    async def procesar_dia(
        self,
        fecha: str,
        area: Optional[str] = None,
        areas: Optional[List[str]] = None,
        force: bool = False,
        empleado_ids: Optional[set] = None,
        suppress_sync: bool = False,
    ):
        bulk_ctx = await self.get_bulk_context(fecha, area, empleado_ids=empleado_ids)
        if not bulk_ctx:
            return
        from backend.services.calendario_service import CalendarioService
        cal = CalendarioService()
        dt = datetime.strptime(fecha, "%Y-%m-%d")
        feriados_raw = await cal.get_feriados(dt.year)
        bulk_ctx['feriados'] = {f['fecha']: f['descripcion'] for f in feriados_raw}

        emp_ids = list(bulk_ctx.get('empleados', {}).keys())
        # Filtro por áreas si viene lista
        if areas:
            emp_ids = [
                eid for eid in emp_ids
                if bulk_ctx['empleados'].get(eid, {}).get('area') in areas
            ]

        results_to_save = []
        he_to_save = []
        results_to_delete = []
        results_to_delete_he = []
        
        for emp_id in emp_ids:
            resultado = await self.procesar_empleado_dia(emp_id, fecha, save=False, bulk_ctx=bulk_ctx, force=force)
            if resultado:
                results_to_save.append(resultado)
                he_estado = resultado.get('_he_estado')
                minutos_bruto = resultado.get('minutos_extra_bruto', 0)
                if minutos_bruto > 0 or he_estado in ('APROBADO', 'RECHAZADO'):
                    he_to_save.append({
                        'empleado_id': emp_id,
                        'fecha': fecha,
                        'minutos_bruto': minutos_bruto,
                        'minutos_autorizados': resultado.get('_he_minutos_autorizados', 0),
                        'estado': he_estado or 'PENDIENTE'
                    })
                else:
                    results_to_delete_he.append((emp_id, fecha))
            else:
                results_to_delete.append((emp_id, fecha))
                results_to_delete_he.append((emp_id, fecha))
        
        if results_to_save:
            await self.repository.batch_upsert_asistencia(results_to_save, suppress_auto_sync=True)
        if results_to_delete:
            for eid_del, f_str in results_to_delete:
                await self.repository.delete_asistencia(eid_del, f_str)
        if he_to_save:
            await self.he_repo.batch_upsert(he_to_save, suppress_auto_sync=True)
        if results_to_delete_he:
            for eid_del, f_str in results_to_delete_he:
                await self.he_repo.delete_by_empleado_fecha(eid_del, f_str)
        
        if not suppress_sync and (results_to_save or results_to_delete or he_to_save or results_to_delete_he):
            await self.repository.db.sync_to_cloud_explicit()

    # ─────────────────────────────────────────────────────────────────────────
    # REPROCESO PERÍODO EMPLEADO
    # ─────────────────────────────────────────────────────────────────────────

    async def reasignar_bloque_turno(
        self,
        empleado_id: int,
        fecha_origen: str,
        fecha_destino: str,
        motivo: Optional[str] = "Reasignación de turno manual"
    ) -> Dict[str, Any]:
        """
        Reasigna el paquete completo de marcaciones de fecha_origen a fecha_destino.
        Garantiza que la celda de destino no tenga licencias/vacaciones ni marcaciones previas.
        Fuerza el recálculo inmediato de ambas celdas y retorna el estado actualizado.
        """
        db = self.repository.db

        # 1. Obtener registro de fecha_origen
        asist_orig = await db.fetch_one(
            "SELECT * FROM asistencias WHERE empleado_id = ? AND fecha = ?",
            (empleado_id, fecha_origen)
        )
        if not asist_orig:
            raise ValueError("No se encontró registro de asistencia en la fecha de origen.")

        marcas_str = asist_orig.get('marcas_consumidas_ids') or '[]'
        if marcas_str == '[]':
            # Buscar logs_raw sin consumir o asociados a la fecha de origen (rango nocturno)
            raw_orig = await db.fetch_all(
                """SELECT id FROM logs_raw 
                   WHERE empleado_id = ? 
                     AND fecha_hora >= ? 
                     AND fecha_hora <= ?""",
                (empleado_id, f"{fecha_origen} 18:00:00", f"{fecha_destino} 12:00:00")
            )
            if raw_orig:
                ids = [r['id'] for r in raw_orig]
                import json
                marcas_str = json.dumps(ids)
            else:
                raise ValueError("La fecha de origen no contiene marcaciones consumidas ni crudas para trasladar.")


        # 2. Verificar que fecha_destino esté limpia (sin marcaciones propias ni justificaciones)
        just_dest = await db.fetch_one(
            "SELECT * FROM justificaciones WHERE empleado_id = ? AND ? BETWEEN fecha_inicio AND fecha_fin",
            (empleado_id, fecha_destino)
        )

        if just_dest:
            raise ValueError(f"El día de destino ({fecha_destino}) tiene una Justificación/Licencia activa.")

        asist_dest = await db.fetch_one(
            "SELECT * FROM asistencias WHERE empleado_id = ? AND fecha = ?",
            (empleado_id, fecha_destino)
        )
        if asist_dest and asist_dest.get('marcas_consumidas_ids') and asist_dest.get('marcas_consumidas_ids') != '[]':
            raise ValueError(f"El día de destino ({fecha_destino}) ya contiene marcaciones registradas.")

        # 3. Mover marcas_consumidas_ids de origen a destino
        await db.execute(
            """UPDATE asistencias
               SET marcas_consumidas_ids = '[]',
                   estado = 'LIBRE',
                   hora_entrada_real = NULL,
                   hora_salida_real = NULL,
                   horas_trabajadas = 0.0,
                   minutos_atraso = 0,
                   minutos_extra_bruto = 0,
                   minutos_deuda = 0,
                   observaciones = ?
               WHERE empleado_id = ? AND fecha = ?""",
            (f"Marcaciones reasignadas a jornada del {fecha_destino}", empleado_id, fecha_origen)
        )

        if asist_dest:
            await db.execute(
                """UPDATE asistencias
                   SET marcas_consumidas_ids = ?,
                       origen = 'MANUAL',
                       observaciones = ?
                   WHERE empleado_id = ? AND fecha = ?""",
                (marcas_str, f"Reasignado desde {fecha_origen}: {motivo}", empleado_id, fecha_destino)
            )

        else:
            await db.execute(
                """INSERT INTO asistencias (empleado_id, fecha, marcas_consumidas_ids, observaciones, origen)
                   VALUES (?, ?, ?, ?, 'MANUAL')""",
                (empleado_id, fecha_destino, marcas_str, f"Reasignado desde {fecha_origen}: {motivo}")
            )

        # 4. Reprocesar ambas celdas con force=True
        f_min = min(fecha_origen, fecha_destino)
        f_max = max(fecha_origen, fecha_destino)
        await self.reprocesar_periodo_empleado(empleado_id, f_min, f_max, force=True, ignore_closures=True)

        # 5. Retornar celdas actualizadas
        res_orig = await db.fetch_one("SELECT * FROM asistencias WHERE empleado_id = ? AND fecha = ?", (empleado_id, fecha_origen))
        res_dest = await db.fetch_one("SELECT * FROM asistencias WHERE empleado_id = ? AND fecha = ?", (empleado_id, fecha_destino))

        return {
            'success': True,
            'fecha_origen': dict(res_orig) if res_orig else None,
            'fecha_destino': dict(res_dest) if res_dest else None
        }

    async def reprocesar_periodo_empleado(
        self,
        empleado_id: int,
        fecha_inicio: str,
        fecha_fin: str,
        force: bool = False,
        job_id: Optional[str] = None,
        feriados_preloaded: Optional[Dict] = None,
        collect_only: bool = False,
        ignore_closures: bool = False,
    ) -> Dict[str, Any]:
        """
        Parámetros extra para modo batch:
          feriados_preloaded: dict {fecha: descripcion} pre-cargado por el caller
                              para evitar N llamadas a get_feriados() (1 por empleado).
          collect_only:       Si True, NO escribe en la DB. Devuelve los resultados
                              calculados en crudo para que el caller los persista en
                              un solo execute_batch masivo al final del batch.
        """

        import time
        _time = time.time
        t0 = _time()

        logger.info(f"📊 Calculando asistencia empleado {empleado_id}: {fecha_inicio} a {fecha_fin} (Force: {force})")

        start = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        end = datetime.strptime(fecha_fin, "%Y-%m-%d")
        db = self.repository.db

        # Pre-carga ONE-SHOT
        emp_row = await db.fetch_one("SELECT * FROM empleados WHERE id = ?", (empleado_id,))
        if not emp_row:
            return {'error': 'Empleado no encontrado'}

        # Article 22 Compliance - Exclusión en reprocesamientos
        if emp_row.get("excluido_asistencia"):
            logger.info(f"📊 Omitiendo reprocesamiento para empleado {empleado_id} (Art. 22). Limpiando registros residuales...")
            if collect_only:
                delete_list = []
                he_delete_list = []
                curr = start
                while curr <= end:
                    f_str = curr.strftime("%Y-%m-%d")
                    delete_list.append((empleado_id, f_str))
                    he_delete_list.append((empleado_id, f_str))
                    curr += timedelta(days=1)
                return {
                    '_collect': [],
                    '_delete_collect': delete_list,
                    '_he_collect': [],
                    '_he_delete': he_delete_list,
                    'status': 'omitted',
                    'message': 'Empleado excluido por Art. 22'
                }
            else:
                await db.execute("DELETE FROM asistencias WHERE empleado_id = ? AND fecha BETWEEN ? AND ?", (empleado_id, fecha_inicio, fecha_fin))
                await db.execute("DELETE FROM horas_extras WHERE empleado_id = ? AND fecha BETWEEN ? AND ?", (empleado_id, fecha_inicio, fecha_fin))
                return {"status": "omitted", "message": "Empleado excluido por Art. 22"}

        # Pre-cargar periodos cerrados para el empleado
        q_areas = """
            SELECT ha.fecha_desde, ha.fecha_hasta, a.nombre as area_nombre
            FROM historial_areas ha
            JOIN areas a ON ha.area_id = a.id
            WHERE ha.empleado_id = ? AND ha.validado = 1
        """
        areas_rows = await db.fetch_all(q_areas, (empleado_id,))
        emp_areas_history = [dict(r) for r in areas_rows]

        emp_area_actual_row = await db.fetch_one("""
            SELECT a.nombre as area_nombre 
            FROM empleados e 
            LEFT JOIN areas a ON e.area_id = a.id 
            WHERE e.id = ?
        """, (empleado_id,))
        emp_area_actual = emp_area_actual_row['area_nombre'] if emp_area_actual_row else None

        closures_rows = await db.fetch_all("""
            SELECT fecha_inicio, fecha_fin, area 
            FROM cierres_periodos 
            WHERE fecha_inicio <= ? AND fecha_fin >= ?
        """, (fecha_fin, fecha_inicio))
        closures = [dict(r) for r in closures_rows]

        closed_dates = set()
        if not ignore_closures:
            curr_d = start
            while curr_d <= end:
                curr_str = curr_d.strftime("%Y-%m-%d")
                emp_area = None
                for ha in emp_areas_history:
                    desde = ha['fecha_desde']
                    hasta = ha['fecha_hasta']
                    if desde <= curr_str and (not hasta or curr_str <= hasta):
                        emp_area = ha['area_nombre']
                        break
                if not emp_area:
                    emp_area = emp_area_actual
                if emp_area:
                    for cl in closures:
                        if cl['area'] == emp_area and cl['fecha_inicio'] <= curr_str <= cl['fecha_fin']:
                            closed_dates.add(curr_str)
                            break
                curr_d += timedelta(days=1)

        q_asig = """
            SELECT t.*, a.empleado_id, a.fecha_inicio as asignacion_desde, a.fecha_fin as asig_fecha_fin, a.semana_inicio
            FROM turnos t
            JOIN asignacion_turnos a ON t.id = a.turno_id
            WHERE a.empleado_id = ?
            ORDER BY a.fecha_inicio ASC
        """
        asig_rows = await db.fetch_all(q_asig, (empleado_id,))
        # Guardar TODAS las asignaciones históricas para selección dia-a-dia
        all_asignaciones = [dict(a) for a in asig_rows]
        # Orden descendente: más reciente primero → el primer match es el vigente
        all_asignaciones.sort(key=lambda x: x.get('asignacion_desde', ''), reverse=True)

        turno_ids = list({r['id'] for r in asig_rows}) if asig_rows else []
        turno_detalles = {}
        turno_weeks_count = {}
        if turno_ids:
            t_ph = ','.join('?' * len(turno_ids))
            td_rows = await db.fetch_all(
                f"SELECT * FROM turno_dias WHERE turno_id IN ({t_ph}) ORDER BY num_semana, dia_semana",
                tuple(turno_ids)
            )
            # Cargar campos del turno padre que no existen en turno_dias:
            # descuento_colacion_auto, anclajes, tolerancias, etc.
            # Sin esta inyección, config_dia no tiene colación y el descuento queda en 0.
            p_rows = await db.fetch_all(
                f"SELECT * FROM turnos WHERE id IN ({t_ph})",
                tuple(turno_ids)
            )
            turno_padre_map_rep = {r['id']: dict(r) for r in p_rows}
            CAMPOS_TURNO_PADRE = [
                'descuento_colacion_auto', 'minutos_colacion_auto', 'minutos_colacion',
                'anclaje_entrada_minutos', 'anclaje_salida_minutos',
                'tolerancia_retraso_alerta', 'tolerancia_retraso_descuento',
                'redondeo_minutos', 'meta_horas_semanales',
                'tipo_programacion', 'nombre', 'permite_viajes_largos',
                'rotacion_secuencial', 'semana_fallback_sin_marcas',
            ]
            for td in td_rows:
                tid = td['turno_id']
                sem = td['num_semana']
                dsem = td['dia_semana']
                config_dia_dict = dict(td)
                padre = turno_padre_map_rep.get(tid, {})
                for campo in CAMPOS_TURNO_PADRE:
                    if campo in padre:
                        config_dia_dict[campo] = padre[campo]
                turno_detalles.setdefault(tid, {}).setdefault(sem, {})[dsem] = config_dia_dict
                turno_weeks_count[tid] = max(turno_weeks_count.get(tid, 0), sem)

        # Justificaciones del período
        all_justs = await db.fetch_all(
            """
            SELECT j.*, t.nombre as tipo_nombre, t.nomenclatura as tipo_nomenclatura,
                   t.con_goce_sueldo, t.pagador, t.dias_corridos, t.genera_deuda_horaria,
                   t.sobreescribe_feriados, t.descuenta_remuneracion,
                   t.es_horas_sindicales, t.es_por_horas
            FROM justificaciones j JOIN justificacion_tipos t ON j.tipo_id = t.id
            WHERE j.empleado_id = ?
            """,
            (empleado_id,)
        )
        justs = [dict(j) for j in all_justs]

        # Pre-carga de Intercambios del periodo
        q_intercambios = """
            SELECT * FROM intercambios_dias
            WHERE (empleado_solicitante_id = ? OR empleado_receptor_id = ?)
              AND (
                (fecha_origen BETWEEN ? AND ?) 
                OR (fecha_destino BETWEEN ? AND ?)
              )
              AND estado = 'APROBADO'
        """
        inter_rows = await db.fetch_all(q_intercambios, (empleado_id, empleado_id, fecha_inicio, fecha_fin, fecha_inicio, fecha_fin))
        intercambios_por_fecha = {}
        for row in inter_rows:
            row_dict = dict(row)
            intercambios_por_fecha[row_dict['fecha_origen']] = row_dict
            intercambios_por_fecha[row_dict['fecha_destino']] = row_dict

        # Pre-carga de Compensaciones del periodo
        q_compensaciones = """
            SELECT * FROM compensaciones_he_inasistencia
            WHERE empleado_id = ?
              AND fecha_inasistencia BETWEEN ? AND ?
        """
        comp_rows = await db.fetch_all(q_compensaciones, (empleado_id, fecha_inicio, fecha_fin))
        compensaciones_por_fecha = {}
        for row in comp_rows:
            row_dict = dict(row)
            f_inasist = row_dict['fecha_inasistencia']
            if f_inasist not in compensaciones_por_fecha:
                compensaciones_por_fecha[f_inasist] = []
            compensaciones_por_fecha[f_inasist].append(row_dict)

        # Pre-carga de Jornadas Especiales del periodo (+1 dia buffer por nocturnos de ayer)
        ayer_ini_je = (start - timedelta(days=1)).strftime("%Y-%m-%d")
        q_jornadas_esp = """
            SELECT * FROM jornadas_especiales
            WHERE empleado_id = ?
              AND fecha BETWEEN ? AND ?
        """
        je_rows = await db.fetch_all(q_jornadas_esp, (empleado_id, ayer_ini_je, fecha_fin))
        jornadas_especiales_por_fecha = {row['fecha']: dict(row) for row in je_rows}

        # Feriados — reutilizar pre-carga del batch si está disponible
        if feriados_preloaded is not None:
            feriados_dict = feriados_preloaded
        else:
            from backend.services.calendario_service import CalendarioService
            cal_service = CalendarioService()
            feriados_raw = await cal_service.get_feriados(start.year)
            feriados_dict = {f['fecha']: f['descripcion'] for f in feriados_raw}
            if end.year != start.year:
                feriados_raw2 = await cal_service.get_feriados(end.year)
                feriados_dict.update({f['fecha']: f['descripcion'] for f in feriados_raw2})

        # First assignment date
        first_row = await db.fetch_one(
            "SELECT MIN(fecha_inicio) as min_fecha FROM asignacion_turnos WHERE empleado_id = ?",
            (empleado_id,)
        )
        first_assignment = first_row['min_fecha'] if first_row else None

        # Periodos de empleo
        periodos = await db.fetch_all(
            "SELECT * FROM periodos_empleo WHERE empleado_id = ? ORDER BY fecha_inicio ASC",
            (empleado_id,)
        )
        periodos = [dict(p) for p in periodos]

        # Logs del período completo (+1d buffer inicio y fin para nocturnos)
        logs_ini = (start - timedelta(days=1)).strftime("%Y-%m-%d") + " 00:00:00"
        logs_fin = (end + timedelta(days=1)).strftime("%Y-%m-%d") + " 23:59:59"
        all_logs = await db.fetch_all(
            "SELECT * FROM logs_raw WHERE empleado_id = ? AND fecha_hora BETWEEN ? AND ? ORDER BY fecha_hora ASC",
            (empleado_id, logs_ini, logs_fin)
        )
        all_logs = [dict(l) for l in all_logs]

        # Asistencia del día ANTES del inicio (para seed de consumo)
        ayer_ini = (start - timedelta(days=1)).strftime("%Y-%m-%d")
        asistencias_map = {}
        asist_rows = await db.fetch_all(
            "SELECT * FROM asistencias WHERE empleado_id = ? AND fecha >= ? AND fecha <= ?",
            (empleado_id, ayer_ini, end.strftime("%Y-%m-%d"))
        )
        for a in asist_rows:
            asistencias_map[a['fecha']] = dict(a)

        # Horas Extras del período
        he_map = {}
        he_rows = await db.fetch_all(
            "SELECT estado, minutos_autorizados, fecha FROM horas_extras WHERE empleado_id = ? AND fecha >= ? AND fecha <= ?",
            (empleado_id, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        )
        for h in he_rows:
            he_map[h['fecha']] = dict(h)

        # Asignaciones map por empleado — se recalcula por día dentro del loop
        # (No se usa aquí el asigned estático; la selección por fecha ocurre en el loop)

        t_precarga = int((_time() - t0) * 1000)
        total_days = (end - start).days + 1
        logger.info(f"⚡ Pre-carga contexto lista en {t_precarga}ms — iniciando loop de {total_days} días")

        # Inicializar job en registry si fue indicado
        if job_id:
            _init_job(job_id, empleado_id, total_days, fecha_inicio)

        current = start
        stats = {'procesados': 0, 'errores': 0, 'sin_cambio': 0}
        day_index = 0
        results_to_save = []
        results_to_delete = []
        he_to_save = []
        he_to_delete = []
        je_to_save = []
        je_to_delete = []
        marcas_consumidas = {empleado_id: set()}
        manual_rows = await db.fetch_all(
            """SELECT marcas_consumidas_ids FROM asistencias 
               WHERE empleado_id = ? AND origen = 'MANUAL' AND marcas_consumidas_ids IS NOT NULL AND marcas_consumidas_ids != '[]'""",
            (empleado_id,)
        )
        for mr in manual_rows:
            try:
                import json
                m_list = json.loads(mr['marcas_consumidas_ids'])
                for mid in m_list:
                    if mid: marcas_consumidas[empleado_id].add(int(mid))
            except Exception:
                pass
        # En collect_only no hay checkpoints (el caller persiste todo al final).
        # En modo normal se hace checkpoint cada 50 días para limitar exposición al WAL.
        CHECKPOINT_INTERVAL = 50 if not collect_only else 0


        # Inicializar rotativo_offset histórico si es posible
        rotativo_last_sem_dict = {}
        last_asist = await db.fetch_one(
            "SELECT fecha, num_semana_ganadora, turno_asignado_id FROM asistencias WHERE empleado_id = ? AND fecha < ? ORDER BY fecha DESC LIMIT 1",
            (empleado_id, start.strftime("%Y-%m-%d"))
        )
        if last_asist and last_asist['num_semana_ganadora'] and last_asist['turno_asignado_id'] and first_assignment:
            t_id = last_asist['turno_asignado_id']
            tot_sems = turno_weeks_count.get(t_id, 1)
            if tot_sems > 1:
                last_dt = datetime.strptime(last_asist['fecha'], "%Y-%m-%d")
                f_asig_dt = datetime.strptime(first_assignment, "%Y-%m-%d")
                if f_asig_dt.weekday() == 6:
                    f_asig_dt = f_asig_dt + timedelta(days=1)
                else:
                    f_asig_dt = f_asig_dt - timedelta(days=f_asig_dt.weekday())
                d_diff = (last_dt - f_asig_dt).days
                mat_sem = (d_diff // 7) % tot_sems + 1 if d_diff >= 0 else 1
                rotativo_last_sem_dict[empleado_id] = last_asist['num_semana_ganadora']

        # ── FALLBACK: Deducir offset desde los primeros logs cuando no hay asistencias previas ──
        # Para DINAMICO_FLEXIBLE: cada empleado puede iniciar en una semana diferente
        # del ciclo. Si no hay registro histórico, usamos el primer log de Entrada para
        # determinar en qué semana real está el empleado (min_delta contra turno_dias).
        if empleado_id not in rotativo_last_sem_dict and first_assignment and turno_ids:
            _TIPOS_E_INIT = {'entrada', 'e', 'in', 'i', 'ingreso', 'in-entrada'}
            for t_id_init in turno_ids:
                tot_sems_init = turno_weeks_count.get(t_id_init, 1)
                if tot_sems_init <= 1:
                    continue
                # ¿Es turno rotativo?
                tipo_prog_init = None
                for sems_init in turno_detalles.get(t_id_init, {}).values():
                    for cfg_init in sems_init.values():
                        tipo_prog_init = cfg_init.get('tipo_programacion')
                        break
                    if tipo_prog_init:
                        break
                if tipo_prog_init != 'DINAMICO_FLEXIBLE':
                    continue

                f_asig_dt_init = datetime.strptime(first_assignment, "%Y-%m-%d")
                # Mismo ajuste: Domingo → siguiente Lunes
                if f_asig_dt_init.weekday() == 6:
                    f_asig_dt_init = f_asig_dt_init + timedelta(days=1)
                else:
                    f_asig_dt_init = f_asig_dt_init - timedelta(days=f_asig_dt_init.weekday())

                # Buscar el primer log de Entrada disponible
                for log_init in all_logs:
                    tipo_log = str(log_init.get('tipo') or '').strip().lower()
                    if tipo_log not in _TIPOS_E_INIT:
                        continue
                    try:
                        first_log_dt_init = datetime.strptime(log_init['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError):
                        continue

                    log_fecha_init = log_init['fecha_hora'][:10]
                    try:
                        log_dt_init = datetime.strptime(log_fecha_init, "%Y-%m-%d")
                    except ValueError:
                        continue
                    dsem_init = log_dt_init.weekday()

                    d_diff_init = (log_dt_init - f_asig_dt_init).days
                    mat_sem_init = (d_diff_init // 7) % tot_sems_init + 1 if d_diff_init >= 0 else 1

                    # Calcular winner_sem (min_delta) para este log de anclaje
                    winner_init = mat_sem_init
                    min_d_init = None
                    for nsem_init in range(1, tot_sems_init + 1):
                        cfg_init_d = turno_detalles.get(t_id_init, {}).get(nsem_init, {}).get(dsem_init)
                        if not cfg_init_d or cfg_init_d.get('es_libre'):
                            continue
                        ent_str_init = cfg_init_d.get('hora_entrada')
                        sal_str_init = cfg_init_d.get('hora_salida')
                        if not ent_str_init or not sal_str_init:
                            continue
                        try:
                            t_ent_init = datetime.strptime(f"{log_fecha_init} {str(ent_str_init)[:5]}", "%Y-%m-%d %H:%M")
                        except ValueError:
                            continue
                        # Corregir si el turno es nocturno y la entrada es antes de medianoche del día anterior
                        if cfg_init_d.get('cruza_medianoche') and first_log_dt_init.hour < 12:
                            t_ent_init -= timedelta(days=1)
                        diff_s_init = abs((first_log_dt_init - t_ent_init).total_seconds())
                        diff_s_init = min(diff_s_init, 86400 - diff_s_init) # Wrap around 24 hours
                        if min_d_init is None or diff_s_init < min_d_init:
                            min_d_init = diff_s_init
                            winner_init = nsem_init

                    rotativo_last_sem_dict[empleado_id] = winner_init
                    logger.info(
                        f"🔍 [ROTATIVO_INIT] Emp {empleado_id}: primer log={log_init['fecha_hora']} "
                        f"winner_sem={winner_init}"
                    )
                    break  # Solo necesitamos el primer log
                break  # Solo procesamos el primer turno rotativo

        while current <= end:
            fecha_str = current.strftime("%Y-%m-%d")
            ayer_str = (current - timedelta(days=1)).strftime("%Y-%m-%d")
            day_index += 1

            # Bloqueo: saltar días cerrados
            if fecha_str in closed_dates:
                existing_day = asistencias_map.get(fecha_str)
                if existing_day and existing_day.get('num_semana_ganadora'):
                    rotativo_last_sem_dict[empleado_id] = existing_day['num_semana_ganadora']
                
                if job_id:
                    _update_job(job_id,
                        current_day=fecha_str,
                        day_index=day_index,
                        pct=round(day_index / total_days * 100),
                    )
                stats['sin_cambio'] += 1
                stats['procesados'] += 1
                current += timedelta(days=1)
                continue

            # Actualizar progreso en registry
            if job_id:
                _update_job(job_id,
                    current_day=fecha_str,
                    day_index=day_index,
                    pct=round(day_index / total_days * 100),
                )

            # Asistencia de ayer (para seed de consumo nocturno)
            prev_db = asistencias_map.get(ayer_str)

            # Seleccionar la asignación vigente para ESTA fecha específica
            # Misma lógica que get_bulk_context: fecha_inicio <= fecha AND (fecha_fin IS NULL OR fecha_fin >= fecha)
            asigned_for_day = None
            for a in all_asignaciones:  # orden desc → primer match = más reciente vigente
                asig_inicio = a.get('asignacion_desde', '')
                asig_fin = a.get('asig_fecha_fin')  # None = indefinido
                if asig_inicio <= fecha_str and (asig_fin is None or asig_fin >= fecha_str):
                    asigned_for_day = a
                    break
            asigs_map = {empleado_id: asigned_for_day} if asigned_for_day else {}

            # Construir static_ctx para este día
            static_ctx = {
                'empleados': {empleado_id: dict(emp_row)},
                'asignaciones': asigs_map,
                'justificaciones': {empleado_id: justs},
                'logs': {empleado_id: all_logs},  # El motor filtrará por consumo
                'turnos': turno_detalles,
                'turnos_weeks': turno_weeks_count,
                'asistencias_ayer': {empleado_id: prev_db} if prev_db else {},
                'asistencias_hoy': {empleado_id: asistencias_map.get(fecha_str)} if asistencias_map.get(fecha_str) else {},
                'horas_extras': {empleado_id: he_map},  # Guardamos todo el mapa para buscar por fecha en procesar_empleado_dia
                'feriados': feriados_dict,
                'periodos_empleo': {empleado_id: periodos},
                'first_assignments': {empleado_id: first_assignment},
                'rotativo_last_sem_dict': rotativo_last_sem_dict,
                'closed_dates': closed_dates,
                'intercambios': {empleado_id: intercambios_por_fecha},
                'compensaciones': {empleado_id: compensaciones_por_fecha},
                'jornadas_especiales': {empleado_id: jornadas_especiales_por_fecha}
            }

            try:
                # ⚡ OPTIMIZACIÓN: save=False → acumular en RAM, NO commit individual a Turso
                result = await self.procesar_empleado_dia(
                    empleado_id, 
                    fecha_str, 
                    save=False, 
                    force=force, 
                    bulk_ctx=static_ctx,
                    marcas_consumidas_session=marcas_consumidas
                )
                
                # Update offset for next iteration
                # rotativo_offset_dict ya se mutó por referencia en static_ctx
                if result:
                    # ⚡ DELTA: solo guardar si el resultado difiere del existente en DB
                    existing = asistencias_map.get(fecha_str)
                    if existing and self._asistencia_fingerprint(result) == self._asistencia_fingerprint(existing):
                        stats['sin_cambio'] += 1
                    else:
                        results_to_save.append(result)
                    # ── FASE 2: Doble escritura a horas_extras (path batch save=False) ──
                    he_estado = result.get('_he_estado')
                    minutos_bruto = result.get('minutos_extra_bruto', 0)
                    if minutos_bruto > 0 or he_estado in ('APROBADO', 'RECHAZADO'):
                        he_to_save.append({
                            'empleado_id': empleado_id,
                            'fecha': fecha_str,
                            'minutos_bruto': minutos_bruto,
                            'minutos_autorizados': result.get('_he_minutos_autorizados', 0),
                            'estado': he_estado or 'PENDIENTE',
                        })
                    else:
                        # Sin HE ni estado especial: eliminar registro previo (puede ser corrupto)
                        he_to_delete.append((empleado_id, fecha_str))
                    # ── BATCH SAVE FOR JORNADAS ESPECIALES ──
                    if result.get('_jornada_especial'):
                        je_to_save.append(result['_jornada_especial'])
                    else:
                        je_prev = jornadas_especiales_por_fecha.get(fecha_str)
                        if je_prev:
                            je_to_delete.append((empleado_id, fecha_str))
                    asistencias_map[fecha_str] = result
                else:
                    existing = asistencias_map.get(fecha_str)
                    if existing:
                        results_to_delete.append((empleado_id, fecha_str))
                        # No agregamos a stats['sin_cambio'] porque estamos eliminando el registro
                    he_to_delete.append((empleado_id, fecha_str))
                    je_prev = jornadas_especiales_por_fecha.get(fecha_str)
                    if je_prev:
                        je_to_delete.append((empleado_id, fecha_str))
                stats['procesados'] += 1
            except Exception as e:
                import traceback
                logger.error(f"Error calculando asistencia empleado {empleado_id} fecha {fecha_str}: {e}\n{traceback.format_exc()}")
                stats['errores'] += 1
                stats.setdefault('error_list', []).append(f"{fecha_str}: {str(e)}")

            # ⚡ Checkpoint de seguridad: guardar batch parcial cada N días
            # Deshabilitado en collect_only (CHECKPOINT_INTERVAL=0 → modulo nunca es 0)
            if not collect_only and (results_to_save or results_to_delete or je_to_save or je_to_delete) and CHECKPOINT_INTERVAL > 0 and day_index % CHECKPOINT_INTERVAL == 0:
                try:
                    if results_to_save:
                        await self.repository.batch_upsert_asistencia(results_to_save, suppress_auto_sync=True)
                        logger.debug(f"💾 Checkpoint: {len(results_to_save)} días guardados (emp {empleado_id})")
                        results_to_save = []
                    if results_to_delete:
                        for eid_del, f_str in results_to_delete:
                            await self.repository.delete_asistencia(eid_del, f_str)
                        logger.debug(f"🧹 Checkpoint: {len(results_to_delete)} registros residuales eliminados (emp {empleado_id})")
                        results_to_delete = []
                    if he_to_save:
                        await self.he_repo.batch_upsert(he_to_save, suppress_auto_sync=True)
                        he_to_save = []
                    if he_to_delete:
                        for eid_del, f_str in he_to_delete:
                            await self.he_repo.delete_by_empleado_fecha(eid_del, f_str)
                        he_to_delete = []
                    if je_to_save:
                        for je_rec in je_to_save:
                            await self.repository.upsert_jornada_especial(je_rec)
                        je_to_save = []
                    if je_to_delete:
                        for eid_del, f_str in je_to_delete:
                            await self.repository.db.execute("DELETE FROM jornadas_especiales WHERE empleado_id = ? AND fecha = ?", (eid_del, f_str))
                        je_to_delete = []
                except Exception as e:
                    logger.error(f"Error en checkpoint batch (emp {empleado_id}): {e}")

            current += timedelta(days=1)

        if collect_only:
            # ── Modo recolección: devolver resultados en crudo sin tocar la DB ──
            # El caller (_batch_bg) acumula los resultados de todos los empleados
            # y hace UN SOLO execute_batch masivo al final.
            t_total = int((_time() - t0) * 1000)
            logger.info(
                f"📦 Recolectado empleado {empleado_id}: {stats['procesados']} días calculados "
                f"en {t_total}ms ({len(results_to_save)} a guardar, {stats['sin_cambio']} sin cambio)"
            )
            if job_id:
                _complete_job(job_id, stats['procesados'], stats['errores'], t_total)
            # Retornar dict especial con los resultados crudos
            return {
                '_collect': results_to_save,
                '_delete_collect': results_to_delete,
                '_he_collect': he_to_save,
                '_he_delete': he_to_delete,
                '_je_collect': je_to_save,
                '_je_delete': je_to_delete,
                **stats
            }

        # ⚡ BATCH FINAL: guardar todos los resultados restantes en UN SOLO commit local (WAL)
        # suppress_auto_sync=True: NO disparar conn.sync() aquí.
        # El caller (reproceso_masivo_async) hará 1 único sync_to_cloud_explicit() al final.
        if not collect_only and (results_to_save or results_to_delete or je_to_save or je_to_delete):
            try:
                t_save_start = _time()
                if results_to_save:
                    await self.repository.batch_upsert_asistencia(results_to_save, suppress_auto_sync=True)
                if results_to_delete:
                    for eid_del, f_str in results_to_delete:
                        await self.repository.delete_asistencia(eid_del, f_str)
                if he_to_save:
                    await self.he_repo.batch_upsert(he_to_save, suppress_auto_sync=True)
                if he_to_delete:
                    for eid_del, f_str in he_to_delete:
                        await self.he_repo.delete_by_empleado_fecha(eid_del, f_str)
                if je_to_save:
                    for je_rec in je_to_save:
                        await self.repository.upsert_jornada_especial(je_rec)
                if je_to_delete:
                    for eid_del, f_str in je_to_delete:
                        await self.repository.db.execute("DELETE FROM jornadas_especiales WHERE empleado_id = ? AND fecha = ?", (eid_del, f_str))
                t_save = int((_time() - t_save_start) * 1000)
                logger.info(f"💾 Batch final: {len(results_to_save)} upserts, {len(results_to_delete)} deletes en {t_save}ms (emp {empleado_id})")
            except Exception as e:
                logger.error(f"❌ Error en batch final (emp {empleado_id}): {e}")
                # Fallback: guardar uno por uno si el batch falla
                logger.warning(f"🔄 Fallback: guardando día por día...")
                if results_to_save:
                    for result in results_to_save:
                        try:
                            await self.repository.upsert_asistencia(result)
                        except Exception as e2:
                            logger.error(f"Error guardando {result.get('fecha')}: {e2}")
                            stats['errores'] += 1
                if results_to_delete:
                    for eid_del, f_str in results_to_delete:
                        try:
                            await self.repository.delete_asistencia(eid_del, f_str)
                        except Exception as e3:
                            logger.error(f"Error eliminando {f_str}: {e3}")

        t_total = int((_time() - t0) * 1000)
        t_loop = t_total - t_precarga
        saved_count = stats['procesados'] - stats['sin_cambio'] - stats['errores']
        logger.success(
            f"✅ Asistencia empleado {empleado_id}: {stats['procesados']} días en {t_total}ms "
            f"(guardados={saved_count}, sin_cambio={stats['sin_cambio']}, precarga={t_precarga}ms, loop={t_loop}ms)"
        )

        # Marcar job como completado
        if job_id:
            _complete_job(job_id, stats['procesados'], stats['errores'], t_total)

        return stats

    # ─────────────────────────────────────────────────────────────────────────
    # REPROCESO MASIVO ASYNC
    # ─────────────────────────────────────────────────────────────────────────

    async def reproceso_masivo_async(
        self,
        fecha_inicio: str,
        fecha_fin: str,
        area: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        global _reproceso_status, _empleados_en_reproceso
        _reproceso_status = {'estado': 'en_proceso', 'procesados': 0, 'errores': 0, 'total': 0}
        db = self.repository.db
        # FIX: La tabla empleados NO tiene columna 'area' directa.
        # La relación correcta es: empleados → historial_areas → areas (nombre).
        if area:
            q = """
                SELECT e.id FROM empleados e
                LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
                LEFT JOIN areas a ON ha.area_id = a.id
                WHERE e.activo = 1 AND a.nombre = ? AND (e.excluido_asistencia = 0 OR e.excluido_asistencia IS NULL)
            """
            params = [area]
        else:
            q = "SELECT id FROM empleados WHERE activo = 1 AND (excluido_asistencia = 0 OR excluido_asistencia IS NULL)"
            params = []
        emp_rows = await db.fetch_all(q, tuple(params))
        emp_ids = [e['id'] for e in emp_rows]
        _reproceso_status['total'] = len(emp_ids)

        try:
            import time as _time_mod

            # ── PRE-CARGA COMPARTIDA: feriados 1 vez para todos ──────────────
            feriados_dict = {}
            try:
                from backend.services.calendario_service import CalendarioService
                cal_svc = CalendarioService()
                anio_ini = int(fecha_inicio[:4])
                anio_fin = int(fecha_fin[:4])
                for _anio in range(anio_ini, anio_fin + 1):
                    raw = await cal_svc.get_feriados(_anio)
                    feriados_dict.update({f['fecha']: f['descripcion'] for f in raw})
                logger.info(f"[⚡ Masivo] Feriados pre-cargados: {len(feriados_dict)} (años {anio_ini}-{anio_fin})")
            except Exception as fer_err:
                logger.warning(f"⚠️ [Masivo] Pre-carga feriados falló: {fer_err}. Cada empleado los cargará solo.")
                feriados_dict = None

            # ── FASE 1: Calcular en memoria (collect_only=True, 0 writes) ────
            all_results_to_save = []
            all_results_to_delete = []
            all_he_to_save = []
            all_he_to_delete = []
            t0_masivo = _time_mod.time()

            for eid in emp_ids:
                if eid in _empleados_en_reproceso:
                    continue
                _empleados_en_reproceso.add(eid)
                try:
                    r = await self.reprocesar_periodo_empleado(
                        eid, fecha_inicio, fecha_fin, force=force,
                        feriados_preloaded=feriados_dict,
                        collect_only=True,
                    )
                    # Acumular resultados
                    all_results_to_save.extend(r.get('_collect', []))
                    all_results_to_delete.extend(r.get('_delete_collect', []))
                    all_he_to_save.extend(r.get('_he_collect', []))
                    all_he_to_delete.extend(r.get('_he_delete', []))
                    _reproceso_status['procesados'] += r.get('procesados', 0)
                    _reproceso_status['errores'] += r.get('errores', 0)
                except Exception as e:
                    logger.error(f"Error masivo empleado {eid}: {e}")
                    _reproceso_status['errores'] += 1
                finally:
                    _empleados_en_reproceso.discard(eid)

            t_calc = int((_time_mod.time() - t0_masivo) * 1000)
            logger.info(
                f"[⚡ Masivo] Cálculo completado en {t_calc}ms: "
                f"{len(all_results_to_save)} upserts, {len(all_results_to_delete)} deletes, "
                f"{len(all_he_to_save)} HE upserts, {len(all_he_to_delete)} HE deletes"
            )

            # ── FASE 2: 1 SOLO batch_upsert masivo ──────────────────────────
            if all_results_to_save:
                try:
                    t_save = _time_mod.time()
                    await self.repository.batch_upsert_asistencia(
                        all_results_to_save, suppress_auto_sync=True
                    )
                    logger.info(f"💾 [Masivo] {len(all_results_to_save)} asistencias guardadas en {int((_time_mod.time() - t_save)*1000)}ms")
                except Exception as save_err:
                    logger.error(f"❌ [Masivo] Batch upsert falló: {save_err}. Intentando por empleado...")
                    # Fallback: guardar por empleado individual
                    for eid in emp_ids:
                        emp_results = [r for r in all_results_to_save if r.get('empleado_id') == eid]
                        if emp_results:
                            try:
                                await self.repository.batch_upsert_asistencia(emp_results, suppress_auto_sync=True)
                            except Exception as fb_err:
                                logger.error(f"❌ [Masivo Fallback] emp {eid}: {fb_err}")

            if all_results_to_delete:
                for eid_del, f_str in all_results_to_delete:
                    try:
                        await self.repository.delete_asistencia(eid_del, f_str)
                    except Exception:
                        pass

            if all_he_to_save:
                try:
                    await self.he_repo.batch_upsert(all_he_to_save, suppress_auto_sync=True)
                except Exception as he_err:
                    logger.error(f"❌ [Masivo] HE batch upsert falló: {he_err}")

            if all_he_to_delete:
                for eid_del, f_str in all_he_to_delete:
                    try:
                        await self.he_repo.delete_by_empleado_fecha(eid_del, f_str)
                    except Exception:
                        pass

            # ── FASE 3: 1 ÚNICO sync final a Turso Cloud ────────────────────
            try:
                logger.info(f"☁️ [Masivo] Sync final a Turso Cloud ({len(emp_ids)} empleados)...")
                await db.sync_to_cloud_explicit()
                logger.info(f"☁️ [Masivo] Sync final completado.")
            except Exception as sync_err:
                logger.warning(f"⚠️ [Masivo] Sync final falló (datos seguros en WAL): {sync_err}")

            _reproceso_status['estado'] = 'completado'

        except Exception as outer_err:
            logger.error(f"❌ [Reproceso Masivo] Error inesperado: {outer_err}")
            _reproceso_status['estado'] = 'error'
        finally:
            # Liberar el semáforo siempre (éxito o fallo)
            if _reproceso_lock.locked():
                _reproceso_lock.release()

        return _reproceso_status


    # ─────────────────────────────────────────────────────────────────────────
    # VALIDAR JORNADA
    # ─────────────────────────────────────────────────────────────────────────

    async def validar_jornada(
        self,
        empleado_id: int,
        fecha: str,
        accion: str,
        observaciones: Optional[str] = None,
    ) -> Dict[str, Any]:
        db = self.repository.db
        asist = await self.repository.get_asistencia(empleado_id, fecha)
        
        # Buscar en jornadas_especiales primero
        jornada = await db.fetch_one(
            "SELECT * FROM jornadas_especiales WHERE empleado_id = ? AND fecha = ?",
            (empleado_id, fecha)
        )
        
        if not jornada:
            # Fallback: intentamos ver si existe en la tabla de asistencias y se puede convertir a JORNADA_ESPECIAL o EXTRA
            if asist and (asist.get('estado') in ('JORNADA_ESPECIAL', 'EXTRA', 'FERIADO', 'LIBRE', 'ANOMALIA', 'SALIDA_ADELANTADA', 'ATRASO', 'OK') or asist.get('hora_entrada_real')):
                min_trab = int(asist.get('horas_trabajadas', 0) * 60) if 'horas_trabajadas' in asist and asist['horas_trabajadas'] > 0 else 0
                j_record = {
                    'empleado_id': empleado_id,
                    'fecha': fecha,
                    'hora_entrada': asist.get('hora_entrada_real'),
                    'hora_salida': asist.get('hora_salida_real'),
                    'minutos_trabajados': min_trab,
                    'estado': asist.get('estado'),
                    'observaciones': asist.get('observaciones') or ''
                }
                await self.repository.upsert_jornada_especial(j_record)
                jornada = await db.fetch_one(
                    "SELECT * FROM jornadas_especiales WHERE empleado_id = ? AND fecha = ?",
                    (empleado_id, fecha)
                )
        
        if not jornada:
            return {'error': 'No se encontró registro de jornada especial'}
        
        jornada_dict = dict(jornada)

        # ─── TELA DE ARAÑA: Bloquear APROBAR si falta marcación de salida ────
        # Una JE aprobada sin hora_salida genera ANOMALIA en asistencias porque
        # el motor no puede calcular horas trabajadas. El ciclo debe estar completo.
        if accion == 'APROBAR' and not jornada_dict.get('hora_salida'):
            return {
                'error': (
                    'No se puede aprobar la jornada especial: falta la marcación de salida. '
                    'Ingrese la hora de salida en la grilla antes de validar.'
                ),
                'codigo': 'FALTA_SALIDA'
            }

        if accion == 'REVERTIR':
            obs = (jornada_dict.get('observaciones') or '').replace('[VALIDADO]', '').strip()
            update_data = {
                'observaciones': obs,
                'estado': 'JORNADA_ESPECIAL'
            }
            # Al revertir, asistencias vuelve a ANOMALIA si falta salida, o JORNADA_ESPECIAL si está completa
            estado_asistencia = 'JORNADA_ESPECIAL' if jornada_dict.get('hora_salida') else 'ANOMALIA'
            estado_ret = 'REVERTIDO'
            minutos_ret = 0
        else:
            estado_nuevo = 'EXTRA' if accion == 'APROBAR' else 'RECHAZADA'
            minutos_autorizados = jornada_dict.get('minutos_trabajados') or 0 if accion == 'APROBAR' else 0
            update_data = {
                'estado': estado_nuevo,
                'observaciones': (jornada_dict.get('observaciones') or '') + f' [VALIDADO] {observaciones or ""}',
            }
            
            # Al aprobar/rechazar, asistencias refleja el estado final de la JE
            # Si es día hábil ordinario (horas_teoricas > 0), al rechazar la JE preservamos el estado de asistencia
            # para que el reprocesador posterior restaure el flujo ordinario completo con HE pendientes.
            es_dia_habil = asist and float(asist.get('horas_teoricas') or 0.0) > 0.0
            
            if accion == 'APROBAR':
                estado_asistencia = 'EXTRA'
                estado_ret = 'APROBADO'
            else:
                estado_asistencia = asist.get('estado') if es_dia_habil else 'INASISTENCIA'
                estado_ret = 'RECHAZADO'
                
            minutos_ret = minutos_autorizados

        # Actualizar tabla jornadas_especiales
        await db.execute(
            """
            UPDATE jornadas_especiales 
            SET estado = ?, observaciones = ? 
            WHERE empleado_id = ? AND fecha = ?
            """,
            (update_data['estado'], update_data['observaciones'], empleado_id, fecha)
        )

        # ─── EFECTO DOMINÓ: Sincronizar asistencias.estado ───────────────────
        # Sin esta sincronización, la grilla y el cierre leen estados distintos.
        # El estado en asistencias es la fuente de verdad para el motor de cierre.
        await db.execute(
            """
            UPDATE asistencias
            SET estado = ?, updated_at = datetime('now')
            WHERE empleado_id = ? AND fecha = ?
            """,
            (estado_asistencia, empleado_id, fecha)
        )

        # Refrescar recálculo de HE y saldos
        try:
            await self.reprocesar_periodo_empleado(empleado_id, fecha, fecha)
        except Exception as e:
            pass
            
        return {'success': True, 'estado_he': estado_ret, 'minutos_extra_autorizados': minutos_ret}

    # ─────────────────────────────────────────────────────────────────────────
    # DELTA FINGERPRINT (para comparación eficiente de asistencias)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _asistencia_fingerprint(record: dict) -> tuple:
        """
        Genera una tupla inmutable con los campos que definen el estado de una asistencia.
        Dos registros con el mismo fingerprint son idénticos → no necesitan commit a Turso.
        Costo: O(1), ~microsegundos. Campos elegidos: los que afectan grilla y reportes.
        """
        return (
            record.get('turno_asignado_id'),
            record.get('hora_entrada_teorica'),
            record.get('hora_salida_teorica'),
            record.get('horas_teoricas'),
            record.get('hora_entrada_real'),
            record.get('hora_salida_real'),
            record.get('minutos_atraso'),
            record.get('minutos_colacion'),
            record.get('minutos_colacion_real'),
            record.get('horas_trabajadas'),
            record.get('minutos_deuda'),
            record.get('minutos_extra_bruto'),
            record.get('minutos_salida_adelantada'),
            record.get('estado'),
            record.get('observaciones'),
            record.get('hora_salida_colacion'),
            record.get('hora_entrada_colacion'),
            record.get('hora_inicio_permiso'),
            record.get('hora_termino_permiso'),
            record.get('minutos_permisos_detectados'),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # PROCESAR EMPLEADO DÍA (ORQUESTADOR)
    # ─────────────────────────────────────────────────────────────────────────

    async def procesar_empleado_dia(
        self,
        empleado_id: int,
        fecha: str,
        save: bool = True,
        force: bool = False,
        bulk_ctx: Optional[Dict] = None,
        marcas_consumidas_session: Optional[Dict] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Calcula la asistencia para UN empleado en UNA fecha.
        Puede usar un bulk_ctx para evitar consultas a la DB.
        """
        db = self.repository.db

        # Validar si el día está cerrado
        is_closed = False
        if bulk_ctx and 'closed_dates' in bulk_ctx:
            closed_val = bulk_ctx['closed_dates']
            if isinstance(closed_val, dict):
                is_closed = fecha in closed_val.get(empleado_id, set())
            elif isinstance(closed_val, set):
                if closed_val:
                    first_el = next(iter(closed_val))
                    if isinstance(first_el, tuple):
                        is_closed = (empleado_id, fecha) in closed_val
                    else:
                        is_closed = fecha in closed_val
                else:
                    is_closed = False
        else:
            is_closed = await self.is_fecha_cerrada_empleado(empleado_id, fecha)
            
        if is_closed and not force:
            has_raw = await db.fetch_one(
                "SELECT id FROM logs_raw WHERE empleado_id = ? AND fecha_hora LIKE ? LIMIT 1",
                (empleado_id, f"{fecha}%")
            )
            asist_row = await self.repository.get_asistencia(empleado_id, fecha)
            has_consumed = asist_row and asist_row.get('marcas_consumidas_ids') and asist_row['marcas_consumidas_ids'] != '[]'
            if has_raw and not has_consumed:
                logger.info(f"🔄 Auto-forcing recalculo para emp {empleado_id} fecha {fecha}: existen marcas raw sin consumos previas.")
                force = True
            else:
                logger.warning(f"🚫 Intento de procesar día cerrado: emp {empleado_id}, fecha {fecha}. Retornando registro existente.")
                return asist_row

        # Validar período legal de empleo
        if bulk_ctx:
            emp_info = bulk_ctx.get('empleados', {}).get(empleado_id)
        else:
            emp_row = await db.fetch_one(
                "SELECT activo, fecha_ingreso, fecha_salida FROM empleados WHERE id = ?",
                (empleado_id,)
            )
            emp_info = dict(emp_row) if emp_row else None

        if emp_info:
            fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
            f_ingreso = self._parse_date(emp_info.get('fecha_ingreso'))
            f_salida = self._parse_date(emp_info.get('fecha_salida'))

            # Validación 0: Fecha posterior a la baja / término de contrato
            if f_salida and fecha_dt > f_salida:
                if bulk_ctx:
                    logs_emp = bulk_ctx.get('logs', {}).get(empleado_id, [])
                    tiene_marcas = any(str(l.get('fecha_hora', '')).startswith(fecha) for l in logs_emp)
                else:
                    marcas_raw = await db.fetch_all(
                        "SELECT id FROM logs_raw WHERE empleado_id = ? AND fecha_hora LIKE ?",
                        (empleado_id, f"{fecha}%")
                    )
                    tiene_marcas = bool(marcas_raw)

                if tiene_marcas:
                    logger.warning(
                        f"🚨 ANOMALÍA: Empleado {empleado_id} marcó asistencia el {fecha} "
                        f"posterior a su fecha de baja ({f_salida.strftime('%Y-%m-%d')})."
                    )
                    anomalia_record = {
                        'empleado_id': empleado_id,
                        'fecha': fecha,
                        'turno_asignado_id': None,
                        'hora_entrada_teorica': None,
                        'hora_salida_teorica': None,
                        'horas_teoricas': None,
                        'hora_entrada_real': None,
                        'hora_salida_real': None,
                        'minutos_atraso': 0,
                        'minutos_colacion': 0,
                        'horas_trabajadas': 0,
                        'minutos_deuda': 0,
                        'minutos_extra_bruto': 0,
                        'minutos_salida_adelantada': 0,
                        'estado': 'ANOMALIA_CONTRATO_VENCIDO',
                        'observaciones': f"Marcación registrada posterior a fecha de baja ({f_salida.strftime('%Y-%m-%d')}). Requiere revisión de RRHH.",
                        'turno_asignado_id': None,
                    }
                    if save:
                        await self.repository.upsert_asistencia(anomalia_record)
                    return anomalia_record
                else:
                    # Posterior a la baja y sin marcas: descartar día y limpiar residuos
                    if save:
                        asist_del = await self.repository.get_asistencia(empleado_id, fecha)
                        if asist_del:
                            await self.repository.delete_asistencia(empleado_id, fecha)
                        await self.he_repo.delete_by_empleado_fecha(empleado_id, fecha)
                    return None

            if bulk_ctx:
                periodos = bulk_ctx.get('periodos_empleo', {}).get(empleado_id, [])
            else:
                per_rows = await db.fetch_all(
                    "SELECT * FROM periodos_empleo WHERE empleado_id = ?", (empleado_id,)
                )
                periodos = [dict(r) for r in per_rows]

            esta_en_periodo = False
            for p in periodos:
                p_start = self._parse_date(p.get('fecha_inicio'))
                p_end = self._parse_date(p.get('fecha_fin'))
                if p_start and fecha_dt >= p_start:
                    if p_end is None or fecha_dt <= p_end:
                        esta_en_periodo = True
                        break

            # Solo alerta si hay marcas pero no hay período
            if not esta_en_periodo and periodos:
                if bulk_ctx:
                    logs_emp = bulk_ctx.get('logs', {}).get(empleado_id, [])
                    tiene_marcas = any(str(l.get('fecha_hora', '')).startswith(fecha) for l in logs_emp)
                else:
                    marcas_raw = await db.fetch_all(
                        "SELECT id FROM logs_raw WHERE empleado_id = ? AND fecha_hora LIKE ?",
                        (empleado_id, f"{fecha}%")
                    )
                    tiene_marcas = bool(marcas_raw)

                if tiene_marcas:
                    logger.warning(
                        f"🚨 ANOMALÍA CONTRATO: Empleado {empleado_id} marcó asistencia el {fecha} "
                        f"pero NO está dentro de un periodo legal vigente."
                    )
                    anomalia_record = {
                        'empleado_id': empleado_id,
                        'fecha': fecha,
                        'turno_asignado_id': None,
                        'hora_entrada_teorica': None,
                        'hora_salida_teorica': None,
                        'horas_teoricas': None,
                        'hora_entrada_real': None,
                        'hora_salida_real': None,
                        'minutos_atraso': 0,
                        'minutos_colacion': 0,
                        'horas_trabajadas': 0,
                        'minutos_deuda': 0,
                        'minutos_extra_bruto': 0,
                        'minutos_salida_adelantada': 0,
                        'estado': 'ANOMALIA_CONTRATO_VENCIDO',
                        'observaciones': 'Marcación registrada fuera de vigencia de contrato. Requiere revisión de RRHH.',
                        'turno_asignado_id': None,
                    }
                    if save:
                        await self.repository.upsert_asistencia(anomalia_record)
                    return anomalia_record
                else:
                    # Sin contrato y sin marcas: no generar asistencia
                    if save:
                        asist_del = await self.repository.get_asistencia(empleado_id, fecha)
                        if asist_del:
                            await self.repository.delete_asistencia(empleado_id, fecha)
                        await self.he_repo.delete_by_empleado_fecha(empleado_id, fecha)
                    return None

        # 1. Obtener Primera Asignación (para validación de TRABAJO SIN TURNO)
        if bulk_ctx:
            f_primer_turno = bulk_ctx.get('first_assignments', {}).get(empleado_id)
        else:
            res_first = await db.fetch_one(
                "SELECT MIN(fecha_inicio) as min_f FROM asignacion_turnos WHERE empleado_id = ?",
                (empleado_id,)
            )
            f_primer_turno = res_first['min_f'] if res_first else None

        # [REGLA DE NEGOCIO - CORRECCION]: No marcar inasistencia antes de la primera asignación de turno
        # Para saber si hay marcas, usamos un boolean rápido antes de consultar los raw_logs
        if bulk_ctx:
            logs_emp = bulk_ctx.get('logs', {}).get(empleado_id, [])
            marcas_disponibles = any(str(l.get('fecha_hora', '')).startswith(fecha) for l in logs_emp)
        else:
            raw_tmp = await db.fetch_one(
                "SELECT id FROM logs_raw WHERE empleado_id = ? AND fecha_hora LIKE ? LIMIT 1",
                (empleado_id, f"{fecha}%")
            )
            marcas_disponibles = bool(raw_tmp)

        if f_primer_turno and fecha < f_primer_turno:
            if not save:
                return None
            # Si estamos procesando individualmente, nos aseguramos de borrarlo
            asist_actual_del = await self.repository.get_asistencia(empleado_id, fecha)
            if asist_actual_del:
                logger.info(f"🧹 Limpiando registro residual antes de primera asignación: Emp {empleado_id} en {fecha}")
                await self.repository.delete_asistencia(empleado_id, fecha)
            # También eliminamos horas extras si existieran
            await self.he_repo.delete_by_empleado_fecha(empleado_id, fecha)
            return None

        # 2. Obtener Turno Asignado Vigente para el día
        if bulk_ctx:
            asignacion = bulk_ctx['asignaciones'].get(empleado_id)
        else:
            asignacion = await self.repository.get_asignacion_vigente(empleado_id, fecha)

        # 2. Config del día de la semana
        dt = datetime.strptime(fecha, "%Y-%m-%d")
        dia_semana = dt.weekday()  # 0=Lunes

        # 3. Contexto
        if bulk_ctx:
            justificaciones = bulk_ctx['justificaciones'].get(empleado_id, [])
            feriados_dict = bulk_ctx['feriados']
            raw_logs_cached = bulk_ctx['logs'].get(empleado_id)
            if raw_logs_cached is not None:
                raw_logs = raw_logs_cached
            else:
                raw_logs = await self.repository.get_raw_logs(empleado_id, fecha)
        else:
            from backend.repositories.configuracion import ConfiguracionRepository
            from backend.services.calendario_service import CalendarioService
            config_repo = ConfiguracionRepository(self.repository.db)
            cal_service = CalendarioService()
            justificaciones = await config_repo.get_justificaciones_dia_empleado(empleado_id, fecha)
            feriados = await cal_service.get_feriados(dt.year)
            feriados_dict = {f['fecha']: f['descripcion'] for f in feriados}
            raw_logs = await self.repository.get_raw_logs(empleado_id, fecha)

        bonos_asignados = []
        is_holiday = fecha in feriados_dict
        is_weekend = dia_semana >= 5  # 5=Sat, 6=Sun

        # ── PARADIGMA DE CONSUMO (STATE MACHINE) ──────────────────────────────
        if marcas_consumidas_session is None:
            marcas_consumidas_session = {}
        if empleado_id not in marcas_consumidas_session:
            marcas_consumidas_session[empleado_id] = set()
        consumidas_emp = marcas_consumidas_session[empleado_id]

        # ── OVERRIDE REASIGNACION MANUAL DE TURNO ──
        asist_row_manual = await self.repository.get_asistencia(empleado_id, fecha)
        logger.info(f"[MANUAL-REASIG-DEBUG] emp={empleado_id} fecha={fecha} asist_row={asist_row_manual}")
        self_m_ids = []

        if asist_row_manual and asist_row_manual.get('origen') == 'MANUAL' and asist_row_manual.get('marcas_consumidas_ids'):
            try:
                self_m_ids = json.loads(asist_row_manual['marcas_consumidas_ids'])
                for smid in self_m_ids:
                    if smid: consumidas_emp.discard(int(smid))
                
                # Inyectar logs explícitos si no estuviesen presentes en raw_logs
                existing_ids = {int(l['id']) for l in raw_logs if l.get('id')}
                missing_ids = [int(i) for i in self_m_ids if int(i) not in existing_ids]
                if missing_ids:
                    placeholders = ','.join('?' * len(missing_ids))
                    placed_logs_rows = await self.repository.db.fetch_all(
                        f"SELECT * FROM logs_raw WHERE id IN ({placeholders})",
                        tuple(missing_ids)
                    )

                    placed_logs = [dict(r) for r in placed_logs_rows]
                    raw_logs = sorted(raw_logs + placed_logs, key=lambda x: str(x.get('fecha_hora', '')))
                    logs = [l for l in raw_logs if l['id'] not in consumidas_emp]
                    marcas_disponibles = [l for l in raw_logs if l['id'] not in consumidas_emp]


            except Exception as e:
                logger.error(f"Error inyectando logs manuales para {empleado_id} fecha {fecha}: {e}")



        # ── VERIFICAR VIAJE LARGO ACTIVO (BOLSA FLEXIBLE + CANDADO permite_viajes_largos) ─
        active_vl_inicio = None
        active_vl_fin = None
        salida_madrugada_aislada = None
        viaje_largo = None
        is_pvl = bool(asignacion and (asignacion.get('permite_viajes_largos') == 1 or str(asignacion.get('permite_viajes_largos')) in ('1', 'true', 'True') or asignacion.get('permite_viajes_largos') is True))
        if asignacion and asignacion.get('tipo_programacion') == 'FLEXIBLE_BOLSA' and is_pvl:
            viaje_largo = await self.repository.get_viaje_largo_activo(empleado_id, fecha)
        if viaje_largo:
            c_orig = viaje_largo.get('ciudad_origen', 'Planta Aguacol')
            c_dest = viaje_largo.get('ciudad_destino', '')
            h_man = viaje_largo.get('horas_manejo_efectivas', 0.0)
            h_desc = viaje_largo.get('horas_descanso', 0.0)
            h_tot = viaje_largo.get('horas_reconocidas_totales', 0.0)
            
            f_ini = viaje_largo['fecha_inicio']
            f_fin = viaje_largo['fecha_fin']
            vl_entry_id = viaje_largo.get('log_entrada_id')
            vl_exit_id = viaje_largo.get('log_salida_id')
            
            if fecha == f_ini:
                # Consumir todas las marcas del día de inicio de viaje largo
                all_day_logs = [l for l in raw_logs if l.get('fecha_hora', '')[:10] == fecha]
                for l in all_day_logs:
                    consumidas_emp.add(int(l['id']))
                if vl_entry_id: consumidas_emp.add(int(vl_entry_id))
                if vl_exit_id: consumidas_emp.add(int(vl_exit_id))
                
                _TIPOS_E = {'entrada', 'entry', 'e', 'in', '1'}
                _TIPOS_S = {'salida', 'exit', 's', 'out', '2'}
                ents_dia = [l for l in all_day_logs if str(l.get('tipo', '')).strip().lower() in _TIPOS_E]
                sals_dia = [l for l in all_day_logs if str(l.get('tipo', '')).strip().lower() in _TIPOS_S]
                
                h_plant = 0.0
                h_in = viaje_largo.get('fecha_hora_inicio', '')[11:19] if viaje_largo.get('fecha_hora_inicio') else None
                h_out = None
                
                if ents_dia and sals_dia:
                    dt_e1 = datetime.strptime(ents_dia[0]['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                    dt_s1 = datetime.strptime(sals_dia[0]['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                    if dt_s1 > dt_e1:
                        h_plant = max(0.0, (dt_s1 - dt_e1).total_seconds() / 3600.0)
                        h_in = dt_e1.strftime("%H:%M:%S")
                        h_out = dt_s1.strftime("%H:%M:%S")
                elif ents_dia:
                    h_in = ents_dia[0]['fecha_hora'][11:19]
                
                h_trab = round(float(h_tot or 0.0) + h_plant, 2)
                m_ids = json.dumps([l['id'] for l in all_day_logs]) if all_day_logs else (f"[{vl_entry_id}]" if vl_entry_id else '[]')
                obs = f"🚛 VIAJE LARGO ({c_orig} -> {c_dest}): {h_man}h manejo, {h_desc}h descanso."
                if h_plant > 0:
                    obs += f" (+ Turno Planta: {h_plant:.1f}h)"
                
                # REGLA DE NEGOCIO: Si hubo turno ordinario en planta, el estado primario es OK (para Split [OK|VIAJE])
                estado_dia = 'OK' if h_plant > 0 else 'VIAJE_LARGO'
                
                viaje_record = {
                    'empleado_id': empleado_id,
                    'fecha': fecha,
                    'hora_entrada_teorica': None,
                    'hora_salida_teorica': None,
                    'hora_entrada_real': h_in,
                    'hora_salida_real': h_out,
                    'minutos_atraso': 0,
                    'minutos_colacion': 0,
                    'horas_trabajadas': h_trab,
                    'minutos_deuda': 0,
                    'minutos_extra_bruto': 0,
                    'minutos_salida_adelantada': 0,
                    'tiene_anomalia': 0,
                    'alerta_anomalia': 0,
                    'estado': estado_dia,
                    'observaciones': obs,
                    'turno_asignado_id': (asignacion.get('turno_id') or asignacion.get('id')) if asignacion else None,
                    'marcas_consumidas_ids': m_ids,
                }
                if save:
                    await self.repository.upsert_asistencia(viaje_record)
                return viaje_record
            elif fecha == f_fin:
                _TIPOS_E = {'entrada', 'entry', 'e', 'in', '1'}
                _TIPOS_S = {'salida', 'exit', 's', 'out', '2'}
                
                dt_fin_max = viaje_largo.get('fecha_hora_fin') or f"{fecha} 23:59:59"
                
                # Consumir únicamente las marcas que pertenecen al retorno del viaje largo (Salida de retorno)
                # Cualquier Entrada posterior en la misma fecha queda 100% disponible para el siguiente turno
                logs_retorno = [
                    l for l in raw_logs 
                    if l.get('fecha_hora', '').startswith(fecha) 
                    and l.get('fecha_hora', '') <= dt_fin_max 
                    and str(l.get('tipo', '')).strip().lower() in _TIPOS_S
                ]
                for l in logs_retorno:
                    consumidas_emp.add(int(l['id']))
                if vl_exit_id: 
                    consumidas_emp.add(int(vl_exit_id))
                
                h_out = logs_retorno[0]['fecha_hora'][11:19] if logs_retorno else (viaje_largo.get('fecha_hora_fin', '')[11:19] if viaje_largo.get('fecha_hora_fin') else None)
                
                # Verificar si hay marcas posteriores para un turno local en este mismo día
                marcas_locales = [
                    l for l in raw_logs
                    if l.get('fecha_hora', '').startswith(fecha)
                    and int(l['id']) not in consumidas_emp
                ]
                
                if not marcas_locales:
                    m_ids = json.dumps([l['id'] for l in logs_retorno]) if logs_retorno else (f"[{vl_exit_id}]" if vl_exit_id else '[]')
                    obs = f"🚛 RETORNO VIAJE LARGO ({c_dest} -> {c_orig})"
                    
                    viaje_record = {
                        'empleado_id': empleado_id,
                        'fecha': fecha,
                        'hora_entrada_teorica': None,
                        'hora_salida_teorica': None,
                        'hora_entrada_real': None,
                        'hora_salida_real': h_out,
                        'minutos_atraso': 0,
                        'minutos_colacion': 0,
                        'horas_trabajadas': 0.0,
                        'minutos_deuda': 0,
                        'minutos_extra_bruto': 0,
                        'minutos_salida_adelantada': 0,
                        'tiene_anomalia': 0,
                        'alerta_anomalia': 0,
                        'estado': 'VIAJE_LARGO',
                        'observaciones': obs,
                        'turno_asignado_id': (asignacion.get('turno_id') or asignacion.get('id')) if asignacion else None,
                        'marcas_consumidas_ids': m_ids,
                    }
                    if save:
                        await self.repository.upsert_asistencia(viaje_record)
                    return viaje_record
                else:
                    # Hay turno local posterior (ej: 10:22 -> 12:10). Continuar para procesarlo normalmente.
                    pass
            else:
                # Días intermedios en ruta (f_ini < fecha < f_fin)
                h_in = None
                h_out = None
                h_trab = 0.0
                m_ids = '[]'
                obs = f"🚛 VIAJE LARGO EN RUTA ({c_orig} -> {c_dest})"
                viaje_record = {
                    'empleado_id': empleado_id,
                    'fecha': fecha,
                    'hora_entrada_teorica': None,
                    'hora_salida_teorica': None,
                    'hora_entrada_real': h_in,
                    'hora_salida_real': h_out,
                    'minutos_atraso': 0,
                    'minutos_colacion': 0,
                    'horas_trabajadas': h_trab,
                    'minutos_deuda': 0,
                    'minutos_extra_bruto': 0,
                    'minutos_salida_adelantada': 0,
                    'estado': 'VIAJE_LARGO',
                    'observaciones': obs,
                    'turno_asignado_id': (asignacion.get('turno_id') or asignacion.get('id')) if asignacion else None,
                    'marcas_consumidas_ids': m_ids,
                }
                if save:
                    await self.repository.upsert_asistencia(viaje_record)
                return viaje_record

        # 3.1. Asistencia de ayer
        ayer_str = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
        if bulk_ctx:
            asist_ayer = bulk_ctx['asistencias_ayer'].get(empleado_id)
        else:
            asist_ayer = await self.repository.get_asistencia(empleado_id, ayer_str)

        # 3.2. Config de ayer para validar turno programado
        config_ayer = None
        if bulk_ctx and asist_ayer and asist_ayer.get('turno_asignado_id'):
            tid_ayer = asist_ayer['turno_asignado_id']
            dia_semana_ayer = (dt - timedelta(days=1)).weekday()
            sem_gan_ayer = asist_ayer.get('num_semana_ganadora', 1)
            config_ayer = bulk_ctx['turnos'].get(tid_ayer, {}).get(sem_gan_ayer, {}).get(dia_semana_ayer)

        # Siembra (DT-10): Utilizar marcas_consumidas_ids en lugar de heurística de timestamps
        if not consumidas_emp and asist_ayer:
            marcas_ayer_json = asist_ayer.get('marcas_consumidas_ids')
            if marcas_ayer_json and marcas_ayer_json != '[]':
                try:
                    ids_ayer = json.loads(marcas_ayer_json)
                    for id_ayer in ids_ayer:
                        consumidas_emp.add(id_ayer)
                except Exception as e:
                    logger.error(f"Error parsing marcas_consumidas_ids from yesterday for {empleado_id}: {e}")
            else:
                # ── FALLBACK TRANSICIONAL PARA DATOS ANTIGUOS ───────────────────
                if asist_ayer.get('hora_salida_real'):
                    salida_ayer_ts = f"{ayer_str} {asist_ayer['hora_salida_real']}"
                    
                    h_ent_teo_ayer = asist_ayer.get('hora_entrada_teorica')
                    h_sal_teo_ayer = asist_ayer.get('hora_salida_teorica')
                    fue_trasnoche = False
                    
                    if h_ent_teo_ayer and h_sal_teo_ayer and h_sal_teo_ayer < h_ent_teo_ayer:
                        fue_trasnoche = True
                    elif asist_ayer.get('hora_entrada_real') and asist_ayer['hora_entrada_real'] > asist_ayer['hora_salida_real']:
                        fue_trasnoche = True

                    if fue_trasnoche:
                        salida_ayer_ts = f"{fecha} {asist_ayer['hora_salida_real']}"
                        
                    for log in raw_logs:
                        if log['fecha_hora'] <= salida_ayer_ts:
                            consumidas_emp.add(log.get('id'))

                obs_ayer = asist_ayer.get('observaciones') or ''
                if 'procesadas en jornadas_especiales' in obs_ayer and not consumidas_emp:
                    if bulk_ctx and 'jornadas_especiales' in bulk_ctx:
                        je_ayer = bulk_ctx['jornadas_especiales'].get(empleado_id, {}).get(ayer_str)
                    else:
                        je_ayer = await db.fetch_one("SELECT hora_salida, hora_entrada FROM jornadas_especiales WHERE empleado_id = ? AND fecha = ?", (empleado_id, ayer_str))

                    if je_ayer and je_ayer['hora_salida']:
                        hora_salida_je = str(je_ayer['hora_salida'])
                        hora_entrada_je = str(je_ayer['hora_entrada']) if je_ayer['hora_entrada'] else None
                        
                        fue_trasnoche = False
                        if h_ent_teo_ayer and h_sal_teo_ayer and h_sal_teo_ayer < h_ent_teo_ayer:
                            fue_trasnoche = True
                        elif hora_entrada_je and hora_salida_je < hora_entrada_je:
                            fue_trasnoche = True

                        salida_je_ts = f"{fecha} {hora_salida_je}" if fue_trasnoche else f"{ayer_str} {hora_salida_je}"
                        for log in raw_logs:
                            if log['fecha_hora'] <= salida_je_ts:
                                consumidas_emp.add(log.get('id'))

        # Excluir de marcas disponibles cualquier marca que ya forme parte de una Jornada Especial asignada a hoy o ayer
        jes_consumo = await db.fetch_all(
            "SELECT hora_entrada, hora_salida FROM jornadas_especiales WHERE empleado_id = ? AND (fecha = ? OR fecha = ?)",
            (empleado_id, fecha, ayer_str)
        )
        for je_item in jes_consumo:
            h_ent_j = str(je_item['hora_entrada']) if je_item['hora_entrada'] else None
            h_sal_j = str(je_item['hora_salida']) if je_item['hora_salida'] else None
            if h_ent_j and h_sal_j:
                for log in raw_logs:
                    ts_log = log['fecha_hora']
                    if ts_log.endswith(h_ent_j) or ts_log.endswith(h_sal_j):
                        consumidas_emp.add(log.get('id'))
                    elif h_sal_j < h_ent_j and ts_log[:10] == fecha and ts_log[11:] <= h_sal_j:
                        consumidas_emp.add(log.get('id'))

        # Filtrar marcas disponibles (no consumidas)
        marcas_disponibles = [log for log in raw_logs if log.get('id') not in consumidas_emp]
        marcas_disponibles.sort(key=lambda x: x['fecha_hora'])

        # ── AUTO-FIX GENERALIZADO: Normalización Cronológica Par por Desbalance ──
        # Si el número de marcas del día es par y existe desbalance entre E y S, alternar cronológicamente.
        # EXCEPCIÓN: Se omite para FLEXIBLE_BOLSA porque la bolsa flexible maneja sus propias marcas cruzadas
        # de madrugada y su propia inferencia ITS.
        tipo_prog_check = asignacion.get('tipo_programacion') if asignacion else None
        es_bolsa_vl = bool(asignacion and tipo_prog_check == 'FLEXIBLE_BOLSA' and asignacion.get('permite_viajes_largos'))
        marcas_hoy = [m for m in marcas_disponibles if m.get('fecha_hora', '')[:10] == fecha]
        if not es_bolsa_vl and marcas_hoy and len(marcas_hoy) % 2 == 0 and len(marcas_hoy) >= 2:
            _TIPOS_E = {'entrada', 'entry', 'e', 'in', '1'}
            _TIPOS_S = {'salida', 'exit', 's', 'out', '2'}
            num_entradas = sum(1 for l in marcas_hoy if str(l.get('tipo', '') or '').strip().lower() in _TIPOS_E)
            num_salidas  = sum(1 for l in marcas_hoy if str(l.get('tipo', '') or '').strip().lower() in _TIPOS_S)
            
            if num_entradas != num_salidas:
                marcas_hoy_sorted = sorted(marcas_hoy, key=lambda x: x['fecha_hora'])
                corregidas_ids = {}
                for idx, m in enumerate(marcas_hoy_sorted):
                    tipo_nuevo = 'Entrada' if idx % 2 == 0 else 'Salida'
                    corregidas_ids[m['id']] = tipo_nuevo
                    
                for idx, m in enumerate(marcas_disponibles):
                    m_id = m.get('id')
                    if m_id in corregidas_ids:
                        m_corregida = dict(m)
                        m_corregida['tipo'] = corregidas_ids[m_id]
                        m_corregida['_tipo_inferido'] = True
                        marcas_disponibles[idx] = m_corregida
                logger.info(
                    f"⚙️ [Auto-Fix Paridad] Emp {empleado_id} {fecha}: "
                    f"Corregidas {len(corregidas_ids)} marcas a alternancia cronológica por desbalance (E:{num_entradas} vs S:{num_salidas})"
                )

        # Inicializar variables para inyección final
        emergencia_corta_detectada = None
        jornada_adicional_observaciones = ""
        jornada_adicional_minutos = 0
        
        tipo_prog = None
        semana_inicio_cfg = None
        is_bolsa = False
        is_bolsa_viajes_largos = False
        if asignacion:
            tipo_prog = asignacion.get('tipo_programacion')
            semana_inicio_cfg = asignacion.get('semana_inicio')
            is_bolsa = (tipo_prog == 'FLEXIBLE_BOLSA')
            is_bolsa_viajes_largos = bool(
                is_bolsa and
                (asignacion.get('permite_viajes_largos') == 1 or asignacion.get('permite_viajes_largos') is True or str(asignacion.get('permite_viajes_largos')) == '1')
            )

        # ── INTERCEPTOR DE SEGMENTACIÓN TEMPRANO DE EMERGENCIAS Y JORNADAS ADICIONALES ──
        # Ejecutado al inicio para limpiar marcas_disponibles antes del matching rotativo y consumos
        marcas_cand = [m for m in marcas_disponibles if m.get('fecha_hora', '').startswith(fecha)]
        _TIPOS_E = {'entrada', 'entry', 'e', 'in', '1'}
        if len(marcas_cand) % 2 != 0:
            last_m = marcas_cand[-1]
            if str(last_m.get('tipo', '') or '').strip().lower() in _TIPOS_E:
                sig_marcas = [m for m in marcas_disponibles if m['fecha_hora'] > last_m['fecha_hora']]
                if sig_marcas:
                    marcas_cand.append(sig_marcas[0])
        marcas_hoy = marcas_cand
        if not es_bolsa_vl and marcas_hoy and len(marcas_hoy) >= 4 and len(marcas_hoy) % 2 == 0:
            try:
                row_gap = await db.fetch_one("SELECT valor FROM ajustes WHERE clave = 'asistencia_emergencia_gap_horas'")
                row_banda = await db.fetch_one("SELECT valor FROM ajustes WHERE clave = 'asistencia_emergencia_banda_horas'")
                row_limite = await db.fetch_one("SELECT valor FROM ajustes WHERE clave = 'asistencia_emergencia_jornada_limite_horas'")
                
                gap_horas = float(row_gap['valor']) if row_gap else 4.0
                banda_horas = float(row_banda['valor']) if row_banda else 2.0
                limite_horas = float(row_limite['valor']) if row_limite else 3.0
                
                # Dividir marcas de hoy por el gap configurado
                bloques = []
                bloque_actual = []
                for idx_log, log_item in enumerate(marcas_hoy):
                    if idx_log == 0:
                        bloque_actual.append(log_item)
                        continue
                    prev_log = marcas_hoy[idx_log - 1]
                    prev_dt = datetime.strptime(prev_log['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                    curr_dt = datetime.strptime(log_item['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                    gap_hours_real = (curr_dt - prev_dt).total_seconds() / 3600.0
                    
                    _TIPOS_E = {'entrada', 'entry', 'e', 'in', '1'}
                    _TIPOS_S = {'salida', 'exit', 's', 'out', '2'}
                    prev_tipo = str(prev_log.get('tipo', '') or '').strip().lower()
                    curr_tipo = str(log_item.get('tipo', '') or '').strip().lower()
                    
                    if prev_tipo in _TIPOS_S and curr_tipo in _TIPOS_E and gap_hours_real >= gap_horas:
                        bloques.append(bloque_actual)
                        bloque_actual = [log_item]
                    else:
                        bloque_actual.append(log_item)
                if bloque_actual:
                    bloques.append(bloque_actual)
                    
                if len(bloques) > 1:
                    # Calcular la Envolvente Teórica Global del Día
                    tid_asig = asignacion.get('turno_id') or asignacion.get('id')
                    rows_td = await db.fetch_all("SELECT * FROM turno_dias WHERE turno_id = ? AND dia_semana = ?", (tid_asig, dia_semana))
                    td_posibles = [dict(r) for r in rows_td]
                    turnos_activos = [t for t in td_posibles if not t.get('es_libre')]
                    
                    if turnos_activos:
                        min_in_mins = 24 * 60
                        max_out_mins = 0
                        for t_cfg in turnos_activos:
                            h_in = t_cfg['hora_entrada']
                            h_out = t_cfg['hora_salida']
                            in_mins = int(h_in[:2]) * 60 + int(h_in[3:5])
                            out_mins = int(h_out[:2]) * 60 + int(h_out[3:5])
                            if t_cfg.get('cruza_medianoche') or out_mins < in_mins:
                                out_mins += 24 * 60
                            if in_mins < min_in_mins:
                                min_in_mins = in_mins
                            if out_mins > max_out_mins:
                                max_out_mins = out_mins
                                
                        # Clasificar cada bloque por solapamiento temporal con la envolvente
                        bloques_ordinarios = []
                        bloques_extras = []
                        for b in bloques:
                            b_ent = datetime.strptime(b[0]['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                            b_sal = datetime.strptime(b[-1]['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                            b_ent_mins = b_ent.hour * 60 + b_ent.minute
                            b_sal_mins = b_sal.hour * 60 + b_sal.minute
                            if b_sal.date() > b_ent.date():
                                b_sal_mins += 24 * 60
                                
                            start_overlap = max(b_ent_mins, min_in_mins)
                            end_overlap = min(b_sal_mins, max_out_mins)
                            overlap_mins = max(0, end_overlap - start_overlap)
                            
                            if overlap_mins >= 30:
                                bloques_ordinarios.append(b)
                            else:
                                bloques_extras.append(b)
                                
                        if not bloques_ordinarios:
                            bloques_ordinarios = [bloques[0]]
                            bloques_extras = bloques[1:]
                            
                        if bloques_extras:
                            # 1. Limpiar marcas_disponibles para que el resto del motor no las vea
                            extras_ids = {l['id'] for be in bloques_extras for l in be}
                            marcas_disponibles = [m for m in marcas_disponibles if m['id'] not in extras_ids]
                            
                            # 2. Agregar los extras a consumidas_emp para protegerlos de arrastres futuros
                            for eid_log in extras_ids:
                                consumidas_emp.add(eid_log)
                                
                            # 3. Procesar los bloques extras para HE directas o Jornada Especial
                            for be in bloques_extras:
                                be_ent_dt = datetime.strptime(be[0]['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                                be_sal_dt = datetime.strptime(be[-1]['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                                duracion_extra_min = int((be_sal_dt - be_ent_dt).total_seconds() / 60)
                                
                                if (duracion_extra_min / 60.0) < limite_horas:
                                    emergencia_corta_detectada = {
                                        'minutos': duracion_extra_min,
                                        'texto': f"[Llamado de Emergencia: {duracion_extra_min} min de {be[0]['fecha_hora'][11:16]} a {be[-1]['fecha_hora'][11:16]}]"
                                    }
                                    logger.info(f"⚡ [Emergencia Detectada Temprano] Emp {empleado_id} {fecha}: {duracion_extra_min} min.")
                                else:
                                    # Si el bloque extra cruza medianoche y más del 50% de las horas caen al día siguiente (D+1), atribuir visualmente a D+1
                                    fecha_be = fecha
                                    if be_sal_dt.date() > be_ent_dt.date():
                                        midnight_be = datetime.combine(be_sal_dt.date(), datetime.min.time())
                                        mins_d1_be = (be_sal_dt - midnight_be).total_seconds() / 60.0
                                        tot_mins_be = (be_sal_dt - be_ent_dt).total_seconds() / 60.0
                                        if mins_d1_be > (tot_mins_be / 2.0):
                                            fecha_be = be_sal_dt.strftime("%Y-%m-%d")

                                    jornada_adicional_observaciones += f"[Jornada Adicional Pendiente: {be[0]['fecha_hora'][11:16]} - {be[-1]['fecha_hora'][11:16]}] "
                                    jornada_adicional_minutos += duracion_extra_min
                                    logger.info(f"💼 [Jornada Adicional Temprano] Emp {empleado_id} {fecha} (Asignada a {fecha_be}): {duracion_extra_min} min registrada como Horas Extras Pendientes.")
            except Exception as ex_seg:
                logger.error(f"⚠️ Error en interceptor de segmentación temprana de emergencias: {ex_seg}")

        # ── EXTRACCIÓN CRONOLÓGICA (Solo DINAMICO_FLEXIBLE) ─────────────────
        puede_cruzar = False
        block_inteligente = []
        if asist_row_manual and asist_row_manual.get('origen') == 'MANUAL' and self_m_ids and marcas_disponibles:

            self_m_ids_str = {str(x) for x in self_m_ids}
            block_inteligente = [l for l in marcas_disponibles if str(l.get('id')) in self_m_ids_str]
            for l in block_inteligente:
                if l.get('id'): consumidas_emp.add(l.get('id'))
        elif tipo_prog in ('DINAMICO_FLEXIBLE', 'FLEXIBLE_BOLSA'):

            # [DT-1] Algoritmo de balance: Consumir todas las marcas del día calendario actual.
            # Si al finalizar el día el balance es > 0 (Ej: turno nocturno), seguir consumiendo
            # hasta que el balance llegue a 0 o se exceda el límite de 20 horas.
            _TIPOS_E = {'entrada', 'entry', 'e', 'in', '1'}
            _TIPOS_S = {'salida', 'exit', 's', 'out', '2'}

            # [PLAN-v5] Seed: marcar primera Salida residual como consumida
            # Solo cuando semana_inicio está configurado y no hay asistencia del día anterior
            if semana_inicio_cfg is not None and marcas_disponibles:
                if not asist_ayer:
                    primera = next(
                        (l for l in marcas_disponibles if l.get('fecha_hora', '')[:10] == fecha),
                        None
                    )
                    if primera:
                        _tipo_primera = str(primera.get('tipo', '') or '').strip().lower()
                        if _tipo_primera in _TIPOS_S:
                            # Buscar hora_entrada mínima entre todas las semanas para este dia_semana
                            _min_he_seed = None
                            _seed_tid = asignacion.get('turno_id') or asignacion.get('id')
                            _turnos_src = bulk_ctx['turnos'].get(_seed_tid, {}) if bulk_ctx else {}
                            for _s, _dias in _turnos_src.items():
                                _cfg = _dias.get(dia_semana)
                                if _cfg and _cfg.get('hora_entrada') and not _cfg.get('es_libre'):
                                    _he_str = str(_cfg['hora_entrada'])[:5].split(':')
                                    _he_mins = int(_he_str[0]) * 60 + int(_he_str[1])
                                    if _min_he_seed is None or _he_mins < _min_he_seed:
                                        _min_he_seed = _he_mins
                            
                            if _min_he_seed is not None:
                                _p_dt = datetime.strptime(primera['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                                _p_mins = _p_dt.hour * 60 + _p_dt.minute
                                if _p_mins < _min_he_seed:
                                    consumidas_emp.add(primera.get('id'))
                                    marcas_disponibles = [l for l in marcas_disponibles if l.get('id') not in consumidas_emp]
                                    logger.info(
                                        f"[PLAN-v5 SEED] emp={empleado_id} fecha={fecha} | "
                                        f"Marca {primera.get('id')} ({primera['fecha_hora']} {primera.get('tipo')}) "
                                        f"marcada como residual (antes de min_hora_entrada={_min_he_seed}min)"
                                    )

            # ── LIMPIEZA UNIVERSAL DE SALIDA RESIDUAL EN MADRUGADA (< 06:00 AM) ──
            # Si la primera marca disponible del día es una Salida en la madrugada y el empleado
            # tiene marcas posteriores hoy (o turno que inicia más tarde), es un residuo de la noche anterior.
            _m_dia_primera = next(
                (l for l in marcas_disponibles if l.get('fecha_hora', '')[:10] == fecha),
                None
            )
            if _m_dia_primera:
                _p_tipo = str(_m_dia_primera.get('tipo', '') or '').strip().lower()
                _p_h = int(_m_dia_primera.get('fecha_hora', '')[11:13] or '99')
                _hay_posteriores = any(
                    l.get('fecha_hora', '')[:10] == fecha and l.get('id') != _m_dia_primera.get('id')
                    for l in marcas_disponibles
                )
                if _p_tipo in _TIPOS_S and _p_h < 6 and _hay_posteriores:
                    consumidas_emp.add(_m_dia_primera.get('id'))
                    marcas_disponibles = [l for l in marcas_disponibles if l.get('id') not in consumidas_emp]
                    logger.info(
                        f"[SALIDA RESIDUAL MADRUGADA CONSUMIDA] Emp {empleado_id} {fecha}: "
                        f"Marca {_m_dia_primera.get('id')} ({_m_dia_primera['fecha_hora']}) consumida como residual de noche previa"
                    )

            if asist_row_manual and asist_row_manual.get('origen') == 'MANUAL' and self_m_ids and marcas_disponibles:
                ancla = marcas_disponibles[0]
            else:
                ancla = next(
                    (l for l in marcas_disponibles if l.get('fecha_hora', '')[:10] == fecha),
                    None
                )


            puede_cruzar = False  # Inicializar antes de ancla para scope correcto
            if ancla:
                # Determine if the current day's shift can cross midnight
                puede_cruzar = False
                if tipo_prog == 'FLEXIBLE_BOLSA':
                    puede_cruzar = True
                elif asignacion:
                    tid = asignacion.get('turno_id') or asignacion['id']
                    if bulk_ctx:
                        turnos_dict = bulk_ctx.get('turnos', {}).get(tid, {})
                        for sem, sem_dict in turnos_dict.items():
                            cfg = sem_dict.get(dia_semana)
                            if cfg and cfg.get('cruza_medianoche'):
                                puede_cruzar = True
                                break
                    else:
                        rows = await db.fetch_all(
                            "SELECT cruza_medianoche FROM turno_dias WHERE turno_id = ? AND dia_semana = ?",
                            (tid, dia_semana)
                        )
                        for r in rows:
                            if r['cruza_medianoche']:
                                puede_cruzar = True
                                break

                # [FIX CRUCE MEDIANOCHE DIURNO] No descartamos marcas del día siguiente para permitir cruce excepcional
                pass

                # ── Pre-filtro: Doble marcación física (mismo tipo, ≤120s) ──
                # Detecta y consume duplicados ANTES de construir el bloque,
                # para que no contaminen ninguna fase (2 ni 3).
                _marcas_filtradas = []
                for _mf_i, _mf in enumerate(marcas_disponibles):
                    if _mf_i > 0 and _mf.get('id') not in consumidas_emp:
                        _mf_prev = _marcas_filtradas[-1] if _marcas_filtradas else None
                        if _mf_prev:
                            _mf_prev_tipo = str(_mf_prev.get('tipo', '') or '').strip().lower()
                            _mf_curr_tipo = str(_mf.get('tipo', '') or '').strip().lower()
                            if _mf_prev_tipo == _mf_curr_tipo:
                                try:
                                    _mf_prev_dt = datetime.strptime(_mf_prev['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                                    _mf_curr_dt = datetime.strptime(_mf['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                                    _mf_gap = (_mf_curr_dt - _mf_prev_dt).total_seconds()
                                    if 0 < _mf_gap <= 120:
                                        consumidas_emp.add(_mf.get('id'))
                                        logger.info(
                                            f"[BLOCK-DEDUP] emp={empleado_id} fecha={fecha} | "
                                            f"Doble marcación: {_mf_prev['fecha_hora']} → {_mf['fecha_hora']} "
                                            f"({_mf_curr_tipo}, gap={_mf_gap:.0f}s) → consumida y excluida"
                                        )
                                        continue
                                except Exception:
                                    pass
                    _marcas_filtradas.append(_mf)
                marcas_disponibles = _marcas_filtradas

                idx = marcas_disponibles.index(ancla)
                tipo_ancla = str(ancla.get('tipo', '') or '').strip().lower()

                if tipo_ancla in _TIPOS_S:
                    # [ITS] Inferencia de Tipo Secuencial:
                    # Antes de declarar "Salida Huérfana", verificamos si el log
                    # inmediatamente anterior fue una Entrada dentro de las últimas 20 horas.
                    # Si no es así, la Salida es un error de dedo y se corrige a Entrada.
                    es_entrada_vigente = False
                    if idx > 0:
                        prior_log = marcas_disponibles[idx - 1]
                        prior_tipo = str(prior_log.get('tipo', '') or '').strip().lower()
                        try:
                            prior_dt = datetime.strptime(prior_log['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                            ancla_dt = datetime.strptime(ancla['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                            delta_hours = (ancla_dt - prior_dt).total_seconds() / 3600.0
                            if prior_tipo in _TIPOS_E and delta_hours <= 20.0:
                                es_entrada_vigente = True
                        except Exception as ex:
                            logger.error(f"Error calculando delta de tiempo para ITS: {ex}")

                    if not es_entrada_vigente:
                        # Corregir tipo en memoria (no persiste en BD)
                        ancla_corregida = dict(ancla)
                        ancla_corregida['tipo'] = 'Entrada'
                        ancla_corregida['_tipo_inferido'] = True  # trazabilidad
                        idx_en_raw = next(
                            (i for i, l in enumerate(marcas_disponibles) if l.get('id') == ancla.get('id')),
                            None
                        )
                        if idx_en_raw is not None:
                            marcas_disponibles[idx_en_raw] = ancla_corregida
                        ancla = ancla_corregida
                        tipo_ancla = 'entrada'
                        logger.info(
                            f"[ITS] emp={empleado_id} fecha={fecha} | "
                            f"Marca {ancla.get('id')} corregida Salida→Entrada (Validación Cronológica anterior)"
                        )

                if tipo_ancla in _TIPOS_S:
                    # [D9] Salida legítima: el empleado cruzó medianoche
                    block_inteligente = [ancla]
                    consumidas_emp.add(ancla.get('id'))
                else:
                    balance = 0
                    first_log_dt = datetime.strptime(ancla['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                    
                    # Consumir todo el día calendario en una variable temporal para buscar la última Entrada
                    dia_logs_temp = []
                    for i in range(idx, len(marcas_disponibles)):
                        l = marcas_disponibles[i]
                        if l.get('fecha_hora', '').startswith(fecha):
                            dia_logs_temp.append(l)
                        else:
                            break
                            
                    last_entrada_dt = None
                    for l in reversed(dia_logs_temp):
                        if str(l.get('tipo', '') or '').strip().lower() in _TIPOS_E:
                            try:
                                last_entrada_dt = datetime.strptime(l['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                                break
                            except Exception:
                                pass
                                
                    ref_dt = last_entrada_dt if last_entrada_dt else first_log_dt
                    max_dt = ref_dt + timedelta(hours=16)
                    
                    ultimo_idx = -1
                    
                    # 1. Consumir día calendario con checkpoint de pares pre-turno [PLAN-v5]
                    _he_turno = None
                    if semana_inicio_cfg is not None and bulk_ctx:
                        # Buscar hora_entrada mínima entre todas las semanas para este dia_semana
                        for _s_c4, _dias_c4 in bulk_ctx.get('turnos', {}).get(tid, {}).items():
                            _cfg_c4 = _dias_c4.get(dia_semana)
                            if _cfg_c4 and _cfg_c4.get('hora_entrada') and not _cfg_c4.get('es_libre'):
                                _he_str_c4 = str(_cfg_c4['hora_entrada'])[:5].split(':')
                                _he_mins_c4 = int(_he_str_c4[0]) * 60 + int(_he_str_c4[1])
                                if _he_turno is None or _he_mins_c4 < _he_turno:
                                    _he_turno = _he_mins_c4
                    
                    _pre_turno_pair = []  # acumulador del par en construcción
                    _pre_turno_separados = []  # pares completos separados
                    
                    for i in range(idx, len(marcas_disponibles)):
                        l = marcas_disponibles[i]
                        if l.get('fecha_hora', '').startswith(fecha):
                            block_inteligente.append(l)
                            consumidas_emp.add(l.get('id'))
                            ultimo_idx = i
                            
                            t = str(l.get('tipo', '') or '').strip().lower()
                            if t in _TIPOS_E:
                                balance += 1
                            elif t in _TIPOS_S:
                                balance -= 1
                            
                            _pre_turno_pair.append(l)
                            
                            # [PLAN-v5] Checkpoint: par E→S cerrado
                            if balance == 0 and _he_turno is not None and len(_pre_turno_pair) >= 2:
                                # Verificar si TODAS las marcas del par son antes de hora_entrada
                                _all_before = True
                                for _pm in _pre_turno_pair:
                                    _pm_dt = datetime.strptime(_pm['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                                    if _pm['fecha_hora'][:10] != fecha or (_pm_dt.hour * 60 + _pm_dt.minute) >= _he_turno:
                                        _all_before = False
                                        break
                                if _all_before:
                                    _pre_turno_separados.extend(_pre_turno_pair)
                                _pre_turno_pair = []
                        else:
                            break
                    
                    # [PLAN-v5] Remover pares pre-turno del block_inteligente
                    if _pre_turno_separados:
                        _sep_ids = {l.get('id') for l in _pre_turno_separados}
                        block_inteligente = [l for l in block_inteligente if l.get('id') not in _sep_ids]
                        # Marcas quedan consumidas para evitar que el día siguiente las reclame
                        _sep_desc = ', '.join(
                            f"{l['fecha_hora'][11:16]}({l.get('tipo','?')[0]})" for l in _pre_turno_separados
                        )
                        logger.info(
                            f"[PLAN-v5 PRE-TURNO] emp={empleado_id} fecha={fecha} | "
                            f"Separados {len(_pre_turno_separados)} marcas pre-turno: {_sep_desc}"
                        )
                            
                    # 2. Si balance > 0 y (puede cruzar medianoche o hay cruce excepcional diurno), seguir hasta cerrarlo
                    permitir_cruce_excepcional = False
                    if not puede_cruzar and balance > 0 and ultimo_idx != -1 and (ultimo_idx + 1) < len(marcas_disponibles):
                        sig_log = marcas_disponibles[ultimo_idx + 1]
                        sig_tipo = str(sig_log.get('tipo', '') or '').strip().lower()
                        if sig_tipo in _TIPOS_S:
                            permitir_cruce_excepcional = True

                    if (puede_cruzar or permitir_cruce_excepcional) and balance > 0 and ultimo_idx != -1:
                        for i in range(ultimo_idx + 1, len(marcas_disponibles)):
                            l = marcas_disponibles[i]
                            l_dt = datetime.strptime(l['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                            if l_dt > max_dt:
                                break
                                
                            t = str(l.get('tipo', '') or '').strip().lower()
                            
                            # Si es cruce excepcional y no es salida, abortamos para proteger el día siguiente
                            if permitir_cruce_excepcional and t not in _TIPOS_S:
                                break
                                
                            block_inteligente.append(l)
                            consumidas_emp.add(l.get('id'))
                            
                            if t in _TIPOS_E:
                                balance += 1
                            elif t in _TIPOS_S:
                                balance -= 1
                                
                            if balance <= 0:
                                # En cruce excepcional terminamos inmediatamente
                                if permitir_cruce_excepcional:
                                    break
                                    
                                # ── Lookahead de colación nocturna ──
                                # Si la siguiente marca es Entrada dentro de ≤90min,
                                # es vuelta de colación → seguir consumiendo el bloque.
                                # Ej: 06:06S(col) → 06:39E(vuelta col, 33min) → continúa
                                # Ej: 07:13S(fin) → 22:59E(sig turno, 16h) → break
                                if i + 1 < len(marcas_disponibles):
                                    _next_l = marcas_disponibles[i + 1]
                                    if _next_l.get('id') not in consumidas_emp:
                                        _next_dt = datetime.strptime(
                                            _next_l['fecha_hora'], "%Y-%m-%d %H:%M:%S"
                                        )
                                        _next_tipo = str(
                                            _next_l.get('tipo', '') or ''
                                        ).strip().lower()
                                        _gap_min = (
                                            _next_dt - l_dt
                                        ).total_seconds() / 60
                                        if _next_tipo in _TIPOS_E and 0 < _gap_min <= 90:
                                            continue  # Colación → seguir
                                break

        # ── DETERMINACIÓN DE config_dia ────────────────────────────────────────
        config_dia = None
        semana_ganadora = 1
        if asignacion:
            # En las rutas principales (get_bulk_context, reprocesar_periodo_empleado),
            # la query es SELECT t.*, ... por lo que asignacion['id'] = turnos.id = turno_id.
            # En contextos manuales puede existir el campo 'turno_id' separado.
            tid = asignacion.get('turno_id') or asignacion['id']
            f_asig_ini = self._parse_date(asignacion.get('asignacion_desde')) or self._parse_date(asignacion.get('fecha_inicio'))
            semana_inicio_cfg = asignacion.get('semana_inicio')  # [PLAN-v5] Campo configurable por RRHH
            if f_asig_ini:
                # Normalizar al lunes de la semana de trabajo del empleado.
                # Si la asignación empieza el Domingo (weekday=6), el empleado realmente
                # trabaja desde el Lunes SIGUIENTE → sumar 1 día en vez de restar 6.
                if f_asig_ini.weekday() == 6:  # Domingo
                    f_asig_ini = f_asig_ini + timedelta(days=1)
                else:
                    f_asig_ini = f_asig_ini - timedelta(days=f_asig_ini.weekday())

            if bulk_ctx:
                total_sems = bulk_ctx['turnos_weeks'].get(tid, 1)

                if tipo_prog == 'DINAMICO_FLEXIBLE' and total_sems > 1:
                    if block_inteligente:
                        # ──── FIX 5: Marca solitaria → preferir arrastre ────
                        _last_sem_fix5 = bulk_ctx.get('rotativo_last_sem_dict', {}).get(empleado_id)
                        if len(block_inteligente) == 1 and _last_sem_fix5 is not None:
                            # 1 sola marca no es confiable para determinar turno.
                            # Usar el arrastre de la última semana con marcas completas.
                            winner_sem = _last_sem_fix5
                            logger.info(
                                f"[FIX5-MARCA-SOLITARIA] emp={empleado_id} {fecha}: "
                                f"1 marca, usando arrastre sem={_last_sem_fix5} en vez de matching"
                            )
                        else:
                            # ──── Matching normal (2+ marcas o sin arrastre) ────
                            first_log_dt = datetime.strptime(block_inteligente[0]['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                            
                            # Si el colaborador ya trae una semana de rotación activa y ese día es LIBRE en su semana activa,
                            # verificar si las marcas son de trabajo en día libre (no un inicio de turno nocturno 21:00-23:59)
                            _active_sem_cfg = bulk_ctx['turnos'].get(tid, {}).get(_last_sem_fix5, {}).get(dia_semana) if _last_sem_fix5 else None
                            is_day_off_in_active_sem = _active_sem_cfg and _active_sem_cfg.get('es_libre')
                            first_hour = first_log_dt.hour
                            is_night_start = (first_hour >= 21)

                            if is_day_off_in_active_sem and not is_night_start:
                                winner_sem = _last_sem_fix5
                                logger.info(
                                    f"[FIX-DIA-LIBRE-ROTATIVO] emp={empleado_id} {fecha}: "
                                    f"Día libre en semana activa ({_last_sem_fix5}). Mantiene sem={_last_sem_fix5} para evaluar Jornada Especial."
                                )
                            else:
                                winner_sem = 1
                                min_delta = None

                                for num_semana_eval in range(1, total_sems + 1):
                                    sem_config = bulk_ctx['turnos'].get(tid, {}).get(num_semana_eval, {}).get(dia_semana)
                                    if not sem_config or sem_config.get('es_libre'):
                                        continue
                                    
                                    ent_str = sem_config.get('hora_entrada')
                                    sal_str = sem_config.get('hora_salida')
                                    if not ent_str or not sal_str:
                                        continue
                                        
                                    diff_seconds = 0
                                    has_in = False
                                    has_out = False
                                    for log in block_inteligente:
                                        log_dt = datetime.strptime(log['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                                        if log['tipo'] == 'Entrada' and not has_in:
                                            t_in_dt = datetime.strptime(f"{first_log_dt.strftime('%Y-%m-%d')} {ent_str}:00", "%Y-%m-%d %H:%M:%S")
                                            diff_in = abs((log_dt - t_in_dt).total_seconds())
                                            diff_in = min(diff_in, 86400 - diff_in)
                                            diff_seconds += diff_in
                                            has_in = True
                                        elif log['tipo'] == 'Salida' and not has_out:
                                            t_out_dt = datetime.strptime(f"{first_log_dt.strftime('%Y-%m-%d')} {sal_str}:00", "%Y-%m-%d %H:%M:%S")
                                            if sem_config.get('cruza_medianoche'):
                                                t_out_dt += timedelta(days=1)
                                            diff_out = abs((log_dt - t_out_dt).total_seconds())
                                            diff_out = min(diff_out, 86400 - diff_out)
                                            diff_seconds += diff_out
                                            has_out = True
                                            
                                    if not has_in and not has_out:
                                        diff_seconds = float('inf')

                                    if min_delta is None or diff_seconds < min_delta:
                                        logger.info(f"DIA {fecha} Emp {empleado_id}: Eval Sem {num_semana_eval} -> diff={diff_seconds}. NEW MIN_DELTA!")
                                        min_delta = diff_seconds
                                        winner_sem = num_semana_eval
                                    else:
                                        logger.info(f"DIA {fecha} Emp {empleado_id}: Eval Sem {num_semana_eval} -> diff={diff_seconds}. (min is {min_delta})")

                                logger.info(f"DIA {fecha} Emp {empleado_id}: WINNER_SEM FINALLY CHOSEN: {winner_sem}")

                        semana_ganadora = winner_sem
                        config_dia = bulk_ctx['turnos'].get(tid, {}).get(winner_sem, {}).get(dia_semana)
                        
                        if 'rotativo_last_sem_dict' not in bulk_ctx:
                            bulk_ctx['rotativo_last_sem_dict'] = {}
                        bulk_ctx['rotativo_last_sem_dict'][empleado_id] = winner_sem
                    else:
                        # Si no hay logs, resolvemos qué semana del turno corresponde:
                        total_sems = bulk_ctx['turnos_weeks'].get(tid, 1)
                        
                        if total_sems == 1:
                            semana_ganadora = 1
                        else:
                            # Intentar arrastrar la última configuración ganadora en memoria
                            last_matched_sem = bulk_ctx.get('rotativo_last_sem_dict', {}).get(empleado_id)
                            if last_matched_sem is not None:
                                # Verificar coherencia con rotación secuencial:
                                # Si la rotación da LIBRE y el arrastre da NO-LIBRE,
                                # el arrastre está contaminando un día de transición.
                                _ej_dia = next(iter(bulk_ctx['turnos'].get(tid, {}).get(1, {}).values()), {})
                                _es_sec = bool(_ej_dia.get('rotacion_secuencial', True))
                                if _es_sec and f_asig_ini:
                                    _mon_dt = dt - timedelta(days=dt.weekday())
                                    _mon_ini = f_asig_ini - timedelta(days=f_asig_ini.weekday())
                                    _sem_diff = (_mon_dt - _mon_ini).days // 7
                                    _sem_rot = (_sem_diff % total_sems) + 1
                                    _cfg_rot = bulk_ctx['turnos'].get(tid, {}).get(_sem_rot, {}).get(dia_semana)
                                    # ──── FIX 2: Arrastre siempre gana ────
                                    # El arrastre de la última semana con marcas es la
                                    # fuente de verdad. No cambiar semana por coherencia
                                    # con rotación, porque contamina días siguientes.
                                    semana_ganadora = last_matched_sem
                                    logger.info(
                                        f"[FIX2-ARRASTRE] emp={empleado_id} fecha={fecha} | "
                                        f"Usando arrastre sem={last_matched_sem} (sin override de rotación)"
                                    )
                                else:
                                    semana_ganadora = last_matched_sem
                            elif semana_inicio_cfg is not None:
                                # [PLAN-v5] Usar semana_inicio configurado por RRHH
                                # semana_inicio indica la semana del primer LUNES tras fecha_inicio.
                                if f_asig_ini:
                                    monday_dt = dt - timedelta(days=dt.weekday())
                                    monday_ini = f_asig_ini - timedelta(days=f_asig_ini.weekday())
                                    semanas_diff = (monday_dt - monday_ini).days // 7
                                    semana_ganadora = ((int(semana_inicio_cfg) - 1 + semanas_diff) % total_sems) + 1
                                else:
                                    semana_ganadora = int(semana_inicio_cfg)
                            else:
                                # Obtener configuración del turno padre (vía cualquier día de la semana 1)
                                ejemplo_dia = next(iter(bulk_ctx['turnos'].get(tid, {}).get(1, {}).values()), {})
                                es_secuencial = bool(ejemplo_dia.get('rotacion_secuencial', True))
                                fallback_sem = int(ejemplo_dia.get('semana_fallback_sin_marcas', 1))
                                
                                if es_secuencial and f_asig_ini:
                                    # Proyección matemática de rotación fija
                                    monday_dt = dt - timedelta(days=dt.weekday())
                                    monday_ini = f_asig_ini - timedelta(days=f_asig_ini.weekday())
                                    semanas_diff = (monday_dt - monday_ini).days // 7
                                    semana_ganadora = (semanas_diff % total_sems) + 1
                                else:
                                    # Fallback configurable (si es 0, queda None)
                                    semana_ganadora = fallback_sem if fallback_sem > 0 else None

                        if semana_ganadora is not None:
                            config_dia = bulk_ctx['turnos'].get(tid, {}).get(semana_ganadora, {}).get(dia_semana)
                            if 'rotativo_last_sem_dict' not in bulk_ctx:
                                bulk_ctx['rotativo_last_sem_dict'] = {}
                            bulk_ctx['rotativo_last_sem_dict'][empleado_id] = semana_ganadora
                        else:
                            config_dia = None
                else:
                    # Turnos Fijos o normales
                    if f_asig_ini and total_sems > 1:
                        monday_dt = dt - timedelta(days=dt.weekday())
                        monday_ini = f_asig_ini - timedelta(days=f_asig_ini.weekday())
                        semanas_diff = (monday_dt - monday_ini).days // 7
                        num_sem_activa = (semanas_diff % total_sems) + 1
                    else:
                        num_sem_activa = 1
                    semana_ganadora = num_sem_activa
                    config_dia = bulk_ctx['turnos'].get(tid, {}).get(num_sem_activa, {}).get(dia_semana)
            else:
                # Sin bulk_ctx: consultas individuales
                res_weeks = await db.fetch_one(
                    "SELECT MAX(num_semana) as total FROM turno_dias WHERE turno_id = ?", (tid,)
                )
                total_sems = (res_weeks['total'] or 1) if res_weeks else 1

                if tipo_prog == 'DINAMICO_FLEXIBLE' and total_sems > 1:
                    if block_inteligente:
                        first_log_dt = datetime.strptime(block_inteligente[0]['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                        winner_sem = 1
                        min_delta = None
                        for num_semana_eval in range(1, total_sems + 1):
                            todas_semanas = await db.fetch_all(
                                "SELECT * FROM turno_dias WHERE turno_id = ? AND dia_semana = ? AND num_semana = ?",
                                (tid, dia_semana, num_semana_eval)
                            )
                            for sc in todas_semanas:
                                ent_str = sc.get('hora_entrada')
                                sal_str = sc.get('hora_salida')
                                if not ent_str or not sal_str:
                                    continue
                                diff_s = 0
                                has_in = False
                                has_out = False
                                for log in block_inteligente:
                                    log_dt = datetime.strptime(log['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                                    if log['tipo'] == 'Entrada' and not has_in:
                                        t_in_dt = datetime.strptime(f"{first_log_dt.strftime('%Y-%m-%d')} {ent_str}:00", "%Y-%m-%d %H:%M:%S")
                                        diff_in = abs((log_dt - t_in_dt).total_seconds())
                                        diff_in = min(diff_in, 86400 - diff_in)
                                        diff_s += diff_in
                                        has_in = True
                                    elif log['tipo'] == 'Salida' and not has_out:
                                        t_out_dt = datetime.strptime(f"{first_log_dt.strftime('%Y-%m-%d')} {sal_str}:00", "%Y-%m-%d %H:%M:%S")
                                        if sc.get('cruza_medianoche'):
                                            t_out_dt += timedelta(days=1)
                                        diff_out = abs((log_dt - t_out_dt).total_seconds())
                                        diff_out = min(diff_out, 86400 - diff_out)
                                        diff_s += diff_out
                                        has_out = True
                                        
                                if not has_in and not has_out:
                                    diff_s = 43200.0 if sc.get('es_libre') else float('inf')
                                
                                # Si es Domingo y la entrada es nocturna (>=21:00), el turno pertenece al Lunes hábil siguiente
                                if dia_semana == 6 and first_log_dt and first_log_dt.hour >= 21 and sc.get('es_libre'):
                                    diff_s = float('inf')
                                    
                                if min_delta is None or diff_s < min_delta:
                                    logger.info(f"DIA {fecha} Emp {empleado_id}: Eval Sem {num_semana_eval} -> diff={diff_s}. NEW MIN_DELTA!")
                                    min_delta = diff_s
                                    winner_sem = num_semana_eval
                                else:
                                    logger.info(f"DIA {fecha} Emp {empleado_id}: Eval Sem {num_semana_eval} -> diff={diff_s}. (min is {min_delta})")
                        logger.info(f"DIA {fecha} Emp {empleado_id}: WINNER_SEM FINALLY CHOSEN (No Bulk): {winner_sem}")
                        semana_ganadora = winner_sem
                        rows = await db.fetch_all(
                            "SELECT * FROM turno_dias WHERE turno_id = ? AND dia_semana = ? AND num_semana = ?",
                            (tid, dia_semana, winner_sem)
                        )
                    else:
                        # Si no hay logs, resolvemos de forma de rotación o fallback configurable:
                        if total_sems == 1:
                            semana_ganadora = 1
                        else:
                            # Intentar arrastrar la última configuración registrada en la DB
                            last_asist = await db.fetch_one(
                                "SELECT num_semana_ganadora FROM asistencias WHERE empleado_id = ? AND fecha < ? AND num_semana_ganadora IS NOT NULL ORDER BY fecha DESC LIMIT 1",
                                (empleado_id, fecha)
                            )
                            if last_asist and last_asist['num_semana_ganadora']:
                                semana_ganadora = last_asist['num_semana_ganadora']
                            elif semana_inicio_cfg is not None:
                                # [PLAN-v5] Usar semana_inicio configurado por RRHH (ruta no-bulk)
                                if f_asig_ini:
                                    monday_dt = dt - timedelta(days=dt.weekday())
                                    monday_ini = f_asig_ini - timedelta(days=f_asig_ini.weekday())
                                    semanas_diff = (monday_dt - monday_ini).days // 7
                                    semana_ganadora = ((int(semana_inicio_cfg) - 1 + semanas_diff) % total_sems) + 1
                                else:
                                    semana_ganadora = int(semana_inicio_cfg)
                            else:
                                padre_row = await db.fetch_one("SELECT * FROM turnos WHERE id = ?", (tid,))
                                padre = dict(padre_row) if padre_row else {}
                                es_secuencial = bool(padre.get('rotacion_secuencial', True))
                                fallback_sem = int(padre.get('semana_fallback_sin_marcas', 1))
                                
                                if es_secuencial and f_asig_ini:
                                    # Proyección matemática
                                    monday_dt = dt - timedelta(days=dt.weekday())
                                    monday_ini = f_asig_ini - timedelta(days=f_asig_ini.weekday())
                                    semanas_diff = (monday_dt - monday_ini).days // 7
                                    semana_ganadora = (semanas_diff % total_sems) + 1
                                else:
                                    semana_ganadora = fallback_sem if fallback_sem > 0 else None

                        if semana_ganadora is not None:
                            rows = await db.fetch_all(
                                "SELECT * FROM turno_dias WHERE turno_id = ? AND dia_semana = ? AND num_semana = ?",
                                (tid, dia_semana, semana_ganadora)
                            )
                        else:
                            rows = []
                else:
                    rows = await db.fetch_all(
                        "SELECT * FROM turno_dias WHERE turno_id = ? AND dia_semana = ?",
                        (tid, dia_semana)
                    )
                if rows:
                    config_dia = dict(rows[0])
                    # Enriquecer con campos del turno padre que no están en turno_dias.
                    # descuento_colacion_auto, anclajes, tolerancias y tipo viven en `turnos`.
                    # Sin esta inyección la colación y los anclajes no se aplican en este path.
                    padre_row = await db.fetch_one("SELECT * FROM turnos WHERE id = ?", (tid,))
                    if padre_row:
                        padre = dict(padre_row)
                        for campo in (
                            'descuento_colacion_auto', 'minutos_colacion_auto', 'minutos_colacion', 'umbral_horas_colacion',
                            'anclaje_entrada_minutos', 'anclaje_salida_minutos',
                            'tolerancia_retraso_alerta', 'tolerancia_retraso_descuento',
                            'redondeo_minutos', 'meta_horas_semanales',
                            'tipo_programacion', 'nombre',
                            'ventana_en_curso_minutos', 'tolerancia_exceso_colacion_minutos',
                            'rotacion_secuencial', 'semana_fallback_sin_marcas'
                        ):
                            if campo in padre:
                                config_dia[campo] = padre[campo]
        # ── POST-VALIDACIÓN de puede_cruzar ──────────────────────────────────
        # [FIX] puede_cruzar se calculó revisando TODAS las semanas del turno.
        # Si la semana_ganadora NO tiene cruza_medianoche, revertir el consumo
        # de marcas de otros días que el block_inteligente haya absorbido.
        is_day_off_night = bool(config_dia and config_dia.get('es_libre') and block_inteligente and int(block_inteligente[0]['fecha_hora'][11:13]) >= 21)
        if (tipo_prog == 'DINAMICO_FLEXIBLE' and puede_cruzar
                and config_dia and not config_dia.get('cruza_medianoche')
                and not is_day_off_night
                and block_inteligente):
            
            # Verificar si el turno es de tarde (entrada >= 13:00) y la marca de mañana es una salida en la madrugada (< 04:00)
            h_ent_cfg = config_dia.get('hora_entrada') or ''
            primera_m_h = block_inteligente[0]['fecha_hora'][11:13] if block_inteligente else '00'
            es_turno_tarde = (int(h_ent_cfg[:2]) >= 13 if len(h_ent_cfg) >= 2 else False) or (int(primera_m_h) >= 13)

            marcas_a_devolver = []
            for m in block_inteligente:
                if not m['fecha_hora'].startswith(fecha):
                    m_tipo = str(m.get('tipo', '') or '').strip().lower()
                    m_hora = int(m['fecha_hora'][11:13]) if len(m['fecha_hora']) >= 13 else 99
                    # Si es turno de tarde y es una salida antes de las 04:00 AM del día siguiente, es el cierre legítimo de la tarde
                    if es_turno_tarde and m_tipo in ('salida', 'exit', 's', 'out', '2') and m_hora < 4:
                        continue  # RETENER: Es la salida legítima que cruzó medianoche
                    marcas_a_devolver.append(m)

            if marcas_a_devolver:
                logger.info(
                    f"⚙️ [Fix puede_cruzar] Emp {empleado_id} {fecha}: "
                    f"sem_ganadora={semana_ganadora} NO cruza medianoche. "
                    f"Devolviendo {len(marcas_a_devolver)} marca(s) de otros días."
                )
                for m in marcas_a_devolver:
                    block_inteligente.remove(m)
                    consumidas_emp.discard(m.get('id'))
                if not any(not m['fecha_hora'].startswith(fecha) for m in block_inteligente):
                    puede_cruzar = False

        # ── EXTRACCIÓN DE PROPIEDADES BASE ────────────────────────────────────
        if config_dia:
            config_dia = dict(config_dia)  # Copia para no mutar el origen del bulk_ctx
        es_libre_config = bool(config_dia and config_dia.get('es_libre'))
        es_nocturno_pre = bool(config_dia and config_dia.get('cruza_medianoche') and not es_libre_config)

        # ── LEY CHILE: Víspera de festivo ─────────────────────────────────────
        # [BUSINESS_RULE: FERIADOS NOCTURNOS Y VÍSPERA (LEY CHILE)]
        # Art. 35 CT: desde las 21:00 hrs del día hábil anterior a un feriado,
        # ninguna jornada puede iniciar. Aplica a:
        #   a) Turnos NOCTURNOS que inician >= 21:00 en víspera de festivo:
        #      el día previo queda como FERIADO (jornada no exigible).
        #   b) Turnos DIURNOS/TARDE que terminan después de las 21:00 en víspera:
        #      la hora de salida se trunca a 21:00.
        fecha_manana = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
        es_vispera_festivo = (not is_holiday) and (fecha_manana in feriados_dict)

        if es_vispera_festivo and config_dia and not es_libre_config:
            if es_nocturno_pre:
                # Turno nocturno que inicia en la víspera y cruza al festivo:
                # si la hora de inicio cae en zona protegida (>= 21:00), es FERIADO.
                hora_inicio = str(config_dia.get('hora_entrada', '00:00'))[:5]
                if hora_inicio >= '21:00':
                    is_holiday = True
            else:
                # Turnos diurnos/tarde mantienen su horario de salida programado de la plantilla/malla.
                pass

        # ── LEY CHILE: Turno nocturno que INICIA en festivo (criterio mayoría de horas) ───
        # [BUSINESS_RULE: MAYORÍA DE HORAS NOCTURNAS EN FESTIVO]
        # DT Ordinarios N°3686/2016 y N°4660/2018:
        # Los trabajadores en TURNOS ROTATIVOS pueden trabajar en el lapso 21:00-24:00
        # del feriado si el turno incide en dicho período, siempre que el descanso íntegro
        # del día festivo (00:00-24:00) se respete.
        # → Si el turno nocturno inicia en el feriado pero la MAYORÍA de sus horas caen
        #   en el día siguiente (día HÁBIL, no feriado), no se genera JORNADA_ESPECIAL.
        #
        # CONDICIÓN CLAVE: el día siguiente donde caen las horas debe ser un día hábil.
        # Si el día siguiente también es feriado (ej: víspera → feriado al día siguiente),
        # este criterio NO aplica: el día de víspera debe permanecer como FERIADO.
        # Ejemplo correcto:
        #   30/04 (víspera) → is_holiday=True por regla víspera, día sig = 01/05 (FERIADO) → NO aplica ✅
        #   01/05 (feriado) → is_holiday=True por feriados_dict,  día sig = 02/05 (hábil)  → SÍ aplica ✅
        dia_siguiente_es_habil = fecha_manana not in feriados_dict
        
        # [FIX] No anular el Feriado si es un turno dinámico sin marcas 
        # (no sabemos qué turno iba a hacer realmente)
        puede_anular_feriado = True
        if tipo_prog == 'DINAMICO_FLEXIBLE' and not block_inteligente:
            puede_anular_feriado = False
            
        is_holiday_original = is_holiday

        if is_holiday and es_nocturno_pre and config_dia and dia_siguiente_es_habil and puede_anular_feriado:
            hora_ini_str = str(config_dia.get('hora_entrada', '00:00'))[:5]
            hora_fin_str = str(config_dia.get('hora_salida',  '00:00'))[:5]
            try:
                h_ini_mins = int(hora_ini_str[:2]) * 60 + int(hora_ini_str[3:])
                h_fin_mins = int(hora_fin_str[:2]) * 60 + int(hora_fin_str[3:])
                # Minutos que caen en el día festivo (desde inicio hasta medianoche)
                mins_en_festivo = 24 * 60 - h_ini_mins   # e.g. 23:00 → 60 min
                # Minutos que caen en el día siguiente (desde medianoche hasta fin)
                mins_en_dia_sig = h_fin_mins               # e.g. 07:00 → 420 min
                if mins_en_festivo > 0 and mins_en_dia_sig > mins_en_festivo:
                    # Mayoría de horas en día hábil → turno normal, no jornada especial
                    is_holiday = False
                    logger.debug(
                        f"[LEY DT] Emp {empleado_id} {fecha}: turno nocturno inicia en festivo "
                        f"pero {mins_en_dia_sig}min en día hábil vs {mins_en_festivo}min en festivo "
                        f"→ tratado como turno normal."
                    )
            except Exception:
                pass  # Si el parse falla, mantener is_holiday original

        dia_restringido = es_libre_config or is_holiday or is_holiday_original

        # ── LOGS PARA ESTE DÍA ────────────────────────────────────────────────
        is_bolsa = tipo_prog == 'FLEXIBLE_BOLSA'
        
        if tipo_prog in ('DINAMICO_FLEXIBLE', 'FLEXIBLE_BOLSA'):
            logs = block_inteligente
        else:
            # REGLA FUNDAMENTAL: Los días que NO son jornada de trabajo (libres, feriados)
            # NO pueden apropiarse de marcas de turnos futuros.
            # Los días de trabajo nocturno SÍ pueden consumir marcas del día siguiente
            # (el motor de consumo gestiona eso mediante el set consumidas_emp).
            # Los días DIURNOS solo pueden usar marcas de su propio día calendario.
            if es_nocturno_pre:
                # [DT-7] Turnos fijos nocturnos consumen por balance Entrada/Salida
                # Ancla: primera marca del día calendario. Sin ventanas (38h removida).
                ancla = next(
                    (l for l in marcas_disponibles if l.get('fecha_hora', '').startswith(fecha)),
                    None
                )
                logs = []
                if ancla:
                    idx = marcas_disponibles.index(ancla)
                    t_ancla = str(ancla.get('tipo', '') or '').strip().lower()
                    _TIPOS_E = {'entrada', 'entry', 'e', 'in', '1'}
                    _TIPOS_S = {'salida', 'exit', 's', 'out', '2'}

                    if t_ancla in _TIPOS_S:
                        # [ITS] Inferencia de Tipo Secuencial en turno nocturno fijo
                        es_entrada_vigente = False
                        if idx > 0:
                            prior_log = marcas_disponibles[idx - 1]
                            prior_tipo = str(prior_log.get('tipo', '') or '').strip().lower()
                            try:
                                prior_dt = datetime.strptime(prior_log['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                                ancla_dt = datetime.strptime(ancla['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                                delta_hours = (ancla_dt - prior_dt).total_seconds() / 3600.0
                                if prior_tipo in _TIPOS_E and delta_hours <= 20.0:
                                    es_entrada_vigente = True
                            except Exception as ex:
                                logger.error(f"Error calculando delta de tiempo para ITS nocturno: {ex}")

                        if not es_entrada_vigente:
                            # Corregir tipo en memoria
                            ancla_corregida = dict(ancla)
                            ancla_corregida['tipo'] = 'Entrada'
                            ancla_corregida['_tipo_inferido'] = True
                            idx_en_raw = next(
                                (i for i, l in enumerate(marcas_disponibles) if l.get('id') == ancla.get('id')),
                                None
                            )
                            if idx_en_raw is not None:
                                marcas_disponibles[idx_en_raw] = ancla_corregida
                            ancla = ancla_corregida
                            t_ancla = 'entrada'
                            logger.info(
                                f"[ITS-NOCTURNO] emp={empleado_id} fecha={fecha} | "
                                f"Marca {ancla.get('id')} corregida Salida→Entrada (Validación Cronológica anterior)"
                            )

                    if t_ancla in _TIPOS_S:
                        # [D9] Ancla es Salida Huérfana
                        logs = [ancla]
                    else:
                        balance = 0
                        for i in range(idx, len(marcas_disponibles)):
                            l = marcas_disponibles[i]
                            t = str(l.get('tipo', '') or '').strip().lower()
                            if t in _TIPOS_E:
                                balance += 1
                            elif t in _TIPOS_S:
                                balance -= 1
                            
                            logs.append(l)
                            if balance <= 0:
                                break
            elif dia_restringido:
                # Solo marcas que caen físicamente en este día calendario
                logs = [l for l in marcas_disponibles if l.get('fecha_hora', '').startswith(fecha)]
            else:
                # Turnos diurnos: marcas del día calendario actual
                logs = [l for l in marcas_disponibles if l.get('fecha_hora', '').startswith(fecha)]

            # ── HORIZONTE ASIMÉTRICO CUÁNTICO: Turnos de Tarde / Noche que extienden a madrugada ──
            _TIPOS_S_CHK = {'salida', 'exit', 's', 'out', '2'}
            _TIPOS_E_CHK = {'entrada', 'entry', 'e', 'in', '1'}
            
            # Filtro de salida residual temprana en T (00:00 - 05:00) si hoy empieza en la tarde/mañana
            if logs and len(logs) > 1:
                p_m = logs[0]
                p_tipo = str(p_m.get('tipo', '') or '').strip().lower()
                p_hora = p_m.get('fecha_hora', '')[11:13]
                if p_tipo in _TIPOS_S_CHK and p_hora and int(p_hora) < 6:
                    consumidas_emp.add(p_m.get('id'))
                    logs = logs[1:]

            if logs:
                h_ent_cfg_chk = config_dia.get('hora_entrada') if config_dia else None
                h_sal_cfg_chk = config_dia.get('hora_salida') if config_dia else None
                cruza_med_chk = bool(config_dia.get('cruza_medianoche')) if config_dia else False
                is_tarde_o_noche = QuantumPhaseTopology.is_evening_or_night_shift(h_ent_cfg_chk, h_sal_cfg_chk, cruza_medianoche=cruza_med_chk)
                if not is_tarde_o_noche:
                    # Chequear si la primera marca real es de tarde (>= 13:00)
                    prim_fh = logs[0].get('fecha_hora', '')[11:13]
                    if prim_fh and int(prim_fh) >= 13:
                        is_tarde_o_noche = True

                if is_tarde_o_noche:
                    tiene_salida_en_t = any(str(l.get('tipo', '') or '').strip().lower() in _TIPOS_S_CHK for l in logs)
                    if not tiene_salida_en_t:
                        manana_str = (datetime.strptime(fecha, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
                        salida_madrugada = next(
                            (l for l in marcas_disponibles 
                             if l.get('fecha_hora', '').startswith(manana_str) 
                             and int(l.get('fecha_hora', '')[11:13] or '99') < 5
                             and str(l.get('tipo', '') or '').strip().lower() in _TIPOS_S_CHK),
                            None
                        )
                        if salida_madrugada and salida_madrugada not in logs:
                            logs.append(salida_madrugada)
                            consumidas_emp.add(salida_madrugada.get('id'))
                            logger.info(
                                f"[HORIZONTE ASIMÉTRICO] Emp {empleado_id} en {fecha}: "
                                f"Capturada salida en madrugada {salida_madrugada['fecha_hora']} como cierre de turno tarde"
                            )

        # First assignment para validación de TRABAJO SIN TURNO
        if bulk_ctx:
            f_primer_turno = bulk_ctx.get('first_assignments', {}).get(empleado_id)
        else:
            res_first = await db.fetch_one(
                "SELECT MIN(fecha_inicio) as min_f FROM asignacion_turnos WHERE empleado_id = ?",
                (empleado_id,)
            )
            f_primer_turno = res_first['min_f'] if res_first else None

        # ── BOLSA FLEXIBLE: referencia de hora para INASISTENCIA ────────────────
        # hora_limite_ficticia es la hora del turno a partir de la cual,
        # si no hay marcas, se genera INASISTENCIA (reversible al aparecer marca).
        # No existe estado 'EN RUTA' — es o INASISTENCIA o celda vacía.
        esta_en_ruta = False  # Mantenido solo para compatibilidad de firma, ya no se usa

        # ── CALCULAR ASISTENCIA ────────────────────────────────────────────────
        asist_actual = None
        if bulk_ctx:
            asist_actual = bulk_ctx.get('asistencias_hoy', {}).get(empleado_id)
        else:
            asist_actual = await self.repository.get_asistencia(empleado_id, fecha)
        
        # FASE 2 (Fix B1): Sourcing de last_state desde horas_extras con fallback a legacy
        he_previo = None
        if bulk_ctx and 'horas_extras' in bulk_ctx:
            he_previo = bulk_ctx['horas_extras'].get(empleado_id, {}).get(fecha)
        if he_previo is None and (not bulk_ctx or 'horas_extras' not in bulk_ctx):
            he_previo = await self.he_repo.get_estado_previo(empleado_id, fecha)
        last_state = he_previo['estado'] if he_previo else None

        # Verificar override manual
        manual_override = False
        if asist_actual:
            obs_prev = asist_actual.get('observaciones') or ''
            if ('[VALIDADO]' in obs_prev or '[RECHAZADO]' in obs_prev) and not force:
                manual_override = True

        if manual_override:
            logger.debug(f"🛡️ Blindaje Manual Aplicado (MODO OVERRIDE) para {empleado_id} - {fecha}")
            resultado = dict(asist_actual)
        else:
            # ──── FIX 6: Transición entre ciclos (SAB LIBRE + DOM sin marcas) ────
            # En turnos multi-semana, si:
            #   1) No hay marcas
            #   2) El día está configurado como TRABAJA
            #   3) El día ANTERIOR en la misma semana era LIBRE
            # → Es día de transición entre ciclos, tratar como LIBRE.
            # Ejemplo: Noche sem=1 tiene SAB=LIBRE, DOM=TRABAJA(23-07).
            # Si no hay marcas en DOM, es porque el ciclo cambió, no inasistencia.
            if (bulk_ctx and not logs
                    and config_dia and not config_dia.get('es_libre')
                    and total_sems > 1
                    and tipo_prog == 'DINAMICO_FLEXIBLE'):
                dia_semana_num = dt.weekday()  # 0=LUN ... 6=DOM
                if dia_semana_num > 0:  # No aplica a lunes (inicio de ciclo)
                    dia_anterior_num = dia_semana_num - 1
                    cfg_dia_ant = bulk_ctx['turnos'].get(tid, {}).get(
                        semana_ganadora, {}).get(dia_anterior_num)
                    if cfg_dia_ant and cfg_dia_ant.get('es_libre'):
                        logger.info(
                            f"[FIX6-TRANSICION] emp={empleado_id} {fecha} | "
                            f"sem={semana_ganadora} dia={dia_semana_num} sin marcas, "
                            f"día anterior (dia={dia_anterior_num}) es LIBRE → "
                            f"Transición entre ciclos, forzar LIBRE"
                        )
                        config_dia = dict(config_dia)
                        config_dia['es_libre'] = True

            # ──── FIX 7 DESACTIVADO: La regla base debe dejar la inasistencia por horario agendado
            # para que el usuario pueda reasignar explícitamente desde la modal si corresponde.

            resultado = QuantumMatrixEngine.solve_attendance_day(
                fecha=fecha,
                empleado_id=empleado_id,
                logs=logs or [],
                turno_config=asignacion or {},
                dia_config=config_dia,
                is_holiday=is_holiday or is_holiday_original,
                justificaciones=justificaciones,
                global_ajustes=bulk_ctx.get('global_ajustes') if bulk_ctx else None,
                consumidas_previas=None,
                viaje_largo_info=active_vl_inicio or active_vl_fin or viaje_largo,
            )

            if resultado:
                resultado['empleado_id'] = empleado_id
                resultado['fecha'] = fecha
                resultado['turno_asignado_id'] = (asignacion.get('id') or asignacion.get('turno_id')) if asignacion else None
                resultado['hora_entrada_teorica'] = config_dia.get('hora_entrada') if config_dia else None
                resultado['hora_salida_teorica'] = config_dia.get('hora_salida') if config_dia else None
                resultado['horas_teoricas'] = float(config_dia.get('horas_teoricas', 0.0) or 0.0) if config_dia else 0.0
                resultado['origen'] = 'SISTEMA'
                resultado['num_semana_ganadora'] = semana_ganadora

        if resultado is None:
            if save and asist_actual:
                logger.info(f"🧹 Limpiando registro residual por recalculo: Emp {empleado_id} en {fecha}")
                await self.repository.delete_asistencia(empleado_id, fecha)
            return None

        if resultado:
            if emergencia_corta_detectada:
                resultado['minutos_extra_bruto'] = resultado.get('minutos_extra_bruto', 0) + emergencia_corta_detectada['minutos']
                resultado['observaciones'] = (resultado.get('observaciones') or '') + " " + emergencia_corta_detectada['texto']
            if jornada_adicional_observaciones:
                resultado['observaciones'] = (resultado.get('observaciones') or '') + " " + jornada_adicional_observaciones
                resultado['minutos_extra_bruto'] = resultado.get('minutos_extra_bruto', 0) + jornada_adicional_minutos

        # ── INTERCEPTOR: DÍA COMPENSATORIO (Intercambio de Días 1x1) ───────────
        if bulk_ctx and 'intercambios' in bulk_ctx:
            intercambio = bulk_ctx['intercambios'].get(empleado_id, {}).get(fecha)
        else:
            intercambio = await self.repository.get_intercambio_por_fecha(empleado_id, fecha)
        if intercambio:
            if fecha == intercambio['fecha_origen'] and resultado.get('estado') in ('INASISTENCIA', 'FALTA'):
                resultado['estado'] = 'INASISTENCIA_COMPENSADA'
                resultado['minutos_deuda'] = 0
                resultado['deuda_condonada'] = 3
                resultado['observaciones'] = resultado.get('observaciones', '') + ' [Día Compensado por Intercambio]'
            elif fecha == intercambio['fecha_destino'] and resultado.get('estado') in ('JORNADA_ESPECIAL', 'EXTRA', 'OK'):
                # OK puede darse si en Destino le asignan un turno temporal o el motor evalúa OK,
                # pero normalmente será JORNADA_ESPECIAL. Igual forzamos que no genere extras.
                resultado['estado'] = 'JORNADA_COMPENSATORIA'
                resultado['minutos_extra_bruto'] = 0
                resultado['observaciones'] = resultado.get('observaciones', '') + ' [Jornada Trabajada por Compensación]'

        # ── INTERCEPTOR: COMPENSACIÓN CON HORAS EXTRAS ────────────────────────
        if bulk_ctx and 'compensaciones' in bulk_ctx:
            compensaciones = bulk_ctx['compensaciones'].get(empleado_id, {}).get(fecha, [])
        else:
            compensaciones = await self.repository.get_compensacion_por_fecha(empleado_id, fecha)
        if compensaciones and resultado and resultado.get('estado') in ('INASISTENCIA', 'FALTA', 'PENDIENTE'):
            total_compensado = sum(c['minutos'] for c in compensaciones)
            if total_compensado > 0:
                resultado['estado'] = 'INASISTENCIA_COMPENSADA'
                deuda_original = resultado.get('minutos_deuda', 0)
                resultado['minutos_deuda'] = max(0, deuda_original - total_compensado)
                resultado['deuda_condonada'] = 4  # Código de condonación por HE
                resultado['observaciones'] = resultado.get('observaciones', '') + f' [Inasistencia Compensada con Horas Extras: {total_compensado} min]'


        # ── APLICACIÓN DE AGOTAMIENTO ATÓMICO (MEMORIA) ───────────────────────
        # [DT-13] Guard sin chequeo de hora_entrada_real:
        # Si el día es ANOMALIA por Salida Huérfana, hora_entrada_real=None pero los
        # logs DEBEN consumirse para no contaminar los días siguientes (D9).
        if resultado:
            resultado['num_semana_ganadora'] = semana_ganadora
            
            ids_consumidos = []
            if logs:
                # [DT-8] Agotamiento atómico (D10): el motor consume estrictamente
                # los IDs asignados al bloque sin heurísticas de tiempo ni ventanas.
                for log in logs:
                    if log.get('id'):
                        ids_consumidos.append(log.get('id'))
                        consumidas_emp.add(log.get('id'))

                # Consumir también los auth-previos si existían
                m_auth_previo = resultado.get('_log_id_entrada')
                if m_auth_previo:
                    ids_consumidos.append(m_auth_previo)
            resultado['marcas_consumidas_ids'] = json.dumps(ids_consumidos)

        # ── INTERCEPTAR JORNADAS ESPECIALES ───────────────────────────────────
        # Fetch existing to check for manual validation
        if bulk_ctx and 'jornadas_especiales' in bulk_ctx:
            je_prev = bulk_ctx['jornadas_especiales'].get(empleado_id, {}).get(fecha)
        else:
            je_prev = await self.repository.db.fetch_one(
                "SELECT estado, observaciones FROM jornadas_especiales WHERE empleado_id = ? AND fecha = ?",
                (empleado_id, fecha)
            )

        has_validated_je = bool(
            je_prev and (
                '[VALIDADO]' in (je_prev.get('observaciones') or '')
                or '[RECHAZADO]' in (je_prev.get('observaciones') or '')
                or je_prev.get('estado') in ('EXTRA', 'RECHAZADA')
            )
        )

        # ── FASE 2 (Fix B2): PRESERVACIÓN DE DECISIONES HUMANAS ───────────────
        # Fuente primaria: horas_extras (nueva tabla)
        # Fallback transicional: asistencias (legacy) — hasta completar Fase 3
        _pres_estado = None
        _pres_auth = 0
        if he_previo and he_previo['estado'] in ('APROBADO', 'RECHAZADO'):
            _pres_estado = he_previo['estado']
            _pres_auth = he_previo.get('minutos_autorizados') or 0

        if resultado and _pres_estado:
            nuevo_bruto = resultado.get('minutos_extra_bruto', 0)
            is_je_or_extra = bool(has_validated_je or (asist_actual and asist_actual.get('estado') in ('EXTRA', 'JORNADA_ESPECIAL')))
            
            # Mantenemos la decisión si hay HE bruto o si es/era una Jornada Especial / EXTRA
            if nuevo_bruto > 0 or is_je_or_extra:
                resultado['_he_estado'] = _pres_estado
                if _pres_estado == 'APROBADO':
                    resultado['_he_minutos_autorizados'] = _pres_auth if nuevo_bruto == 0 else min(_pres_auth, nuevo_bruto)
                    # Restaurar estado EXTRA si era jornada especial aprobada
                    if is_je_or_extra:
                        resultado['estado'] = 'EXTRA'
                else:
                    resultado['_he_minutos_autorizados'] = 0
                
                if f"Preservando decisión humana previa (Estado HE: {_pres_estado})" not in (resultado.get('observaciones') or ''):
                    resultado['observaciones'] = (resultado.get('observaciones') or '') + f"Preservando decisión humana previa (Estado HE: {_pres_estado}) para {fecha}. "
            else:
                resultado['_he_estado'] = None
                resultado['_he_minutos_autorizados'] = 0

        if resultado and (resultado.get('estado') in ('JORNADA_ESPECIAL', 'EXTRA') or has_validated_je):
            ht = resultado.get('horas_teoricas')
            ht_val = float(ht) if ht is not None else 0.0
            
            is_bolsa = bool(asignacion and asignacion.get('tipo_programacion') == 'FLEXIBLE_BOLSA')
            es_candidato = False
            
            if is_bolsa:
                es_candidato = False
            elif ht_val == 0.0 or has_validated_je:
                # Feriado, Día Libre o JE Validada por usuario
                es_candidato = True
            elif ht_val > 0.0 and resultado.get('estado') == 'EXTRA' and ('Cambio de turno irregular' in (resultado.get('observaciones') or '') or 'Turno de seguridad' in (resultado.get('observaciones') or '')):
                # Desfase total o casos manuales movidos a EXTRA pero que operan como especial
                es_candidato = True
            elif ht_val > 0.0 and resultado.get('estado') == 'JORNADA_ESPECIAL':
                # Anomalia forzada a jornada especial
                es_candidato = True
                
            if es_candidato:
                # [REGLA DE NEGOCIO]: Las jornadas especiales o extras no generan horas extras ordinarias ni deudas horarias
                resultado['minutos_extra_bruto'] = 0.0
                resultado['minutos_extra_autorizados'] = 0.0
                resultado['minutos_deuda'] = 0.0
                resultado['tiene_atraso'] = 0
                resultado['tiene_salida_adelantada'] = 0

                min_trab = int(resultado.get('horas_trabajadas', 0) * 60) if 'horas_trabajadas' in resultado and resultado['horas_trabajadas'] > 0 else 0
                
                estado_je = resultado.get('estado')
                obs_je = resultado.get('observaciones') or ''
                
                if je_prev and ('[VALIDADO]' in (je_prev.get('observaciones') or '') or '[RECHAZADO]' in (je_prev.get('observaciones') or '') or je_prev.get('estado') in ('EXTRA', 'RECHAZADA')):
                    estado_je = je_prev['estado']
                    if estado_je == 'PENDIENTE':
                        estado_je = 'JORNADA_ESPECIAL'
                    # Keep original validation observation
                    obs_je = je_prev.get('observaciones') or ''
                    # Si ya estaba validado en el pasado, preservamos el estado en asistencias (ej: EXTRA o RECHAZADA)
                    resultado['estado'] = estado_je
                    
                j_record = {
                    'empleado_id': empleado_id,
                    'fecha': fecha,
                    'hora_entrada': resultado.get('hora_entrada_real'),
                    'hora_salida': resultado.get('hora_salida_real'),
                    'minutos_trabajados': min_trab,
                    'estado': estado_je,
                    'observaciones': obs_je
                }
                if save:
                    await self.repository.upsert_jornada_especial(j_record)
                else:
                    resultado['_jornada_especial'] = j_record
                
                # NOTA ARQUITECTURA: Ya no borramos los datos de "resultado" (hora_entrada_real, etc)
                # para que "asistencias" se mantenga como la FUENTE DE VERDAD con el registro JORNADA_ESPECIAL completo.
            else:
                # Si el día es hábil ordinario (ht_val > 0) y no es JE validada, limpiar propuesta huérfana
                if save and je_prev and not has_validated_je:
                    await self.repository.db.execute(
                        "DELETE FROM jornadas_especiales WHERE empleado_id = ? AND fecha = ? AND estado NOT IN ('EXTRA', 'RECHAZADA') AND observaciones NOT LIKE '%[VALIDADO]%' AND observaciones NOT LIKE '%[RECHAZADO]%'",
                        (empleado_id, fecha)
                    )

        # ── FASE 2 (Paso D): DOBLE ESCRITURA A horas_extras ───────────────────
        # Fix 3: Post-interceptor JE. Si fue interceptado, minutos_extra_bruto ya es 0
        if save and resultado:
            if resultado.get('minutos_extra_bruto', 0) > 0:
                await self.he_repo.upsert(
                    empleado_id=empleado_id,
                    fecha=fecha,
                    minutos_bruto=resultado.get('minutos_extra_bruto', 0),
                    minutos_autorizados=resultado.get('_he_minutos_autorizados', 0),
                    estado=resultado.get('_he_estado') or 'PENDIENTE',
                )
            else:
                # Ghosting Fix: Si las HE caen a 0 (ej. corrección de turno), limpiar el registro huérfano
                await self.he_repo.delete_by_empleado_fecha(empleado_id, fecha)

        if asist_row_manual and asist_row_manual.get('origen') == 'MANUAL':
            resultado['origen'] = 'MANUAL'
            if asist_row_manual.get('observaciones'):
                obs_prev = asist_row_manual['observaciones']
                if 'Reasignado' in obs_prev or 'reasignada' in obs_prev or '[MANUAL]' in obs_prev:
                    if obs_prev not in (resultado.get('observaciones') or ''):
                        resultado['observaciones'] = f"{obs_prev} | {resultado.get('observaciones', '')}".strip(" |")

        # ── ESCRITURA LEGACY (Paso E): asistencias (DESPUÉS de horas_extras) ──
        if save:

            await self.repository.upsert_asistencia(resultado)
            
            # ── NUEVA REGLA: Segmentar exceso de horas extras diarias en días hábiles ordinarios ──
            try:
                db = self.repository.db
                ht_val = float(resultado.get('horas_teoricas') or 0.0)
                est_asist = resultado.get('estado')
                he_bruta = float(resultado.get('minutos_extra_bruto', 0.0))
                
                # Solo aplica en días hábiles programados (horas_teoricas > 0) y no en libres, feriados o inasistencias
                if ht_val > 0.0 and est_asist not in ('LIBRE', 'FERIADO', 'INASISTENCIA') and he_bruta > 0.0:
                    # Horas Extras brutos permanecen intactas en la columna de Horas Extras Pendientes
                    pass
            except Exception as e_regla:
                logger.error(f"⚠️ Error aplicando regla de exceso de HE en día hábil: {e_regla}")

        # Si existe una jornada especial registrada para esta fecha y la asistencia base era LIBRE,
        # pisar el estado en la tabla asistencias a JORNADA_ESPECIAL
        try:
            ht_val_check = float(resultado.get('horas_teoricas') or 0.0)
            if ht_val_check == 0.0:
                je_check = await self.repository.db.fetch_one(
                    "SELECT id, estado FROM jornadas_especiales WHERE empleado_id = ? AND fecha = ?",
                    (empleado_id, fecha)
                )
                if je_check and resultado and resultado.get('estado') == 'LIBRE':
                    resultado['estado'] = 'JORNADA_ESPECIAL'
                    if save:
                        await self.repository.upsert_asistencia(resultado)
        except Exception as _e_je:
            logger.error(f"Error superponiendo JORNADA_ESPECIAL en asistencia: {_e_je}")

        return resultado

    # ─────────────────────────────────────────────────────────────────────────
    # MATRIZ / DATOS DE GRILLA
    # ─────────────────────────────────────────────────────────────────────────

    async def get_matriz_periodo(
        self,
        fecha_inicio: str,
        fecha_fin: str,
        area: Optional[str] = None,
        turno_id: Optional[int] = None,
        search: Optional[str] = None,
        areas_permitidas: Optional[List] = None,
        empleado_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Vista Matriz por rango de fechas (endpoint /matriz/).
        Devuelve la misma estructura enriquecida que get_matrix_data_with_projections.
        """
        # Derive mes/anio from fecha_inicio for the rich method
        from datetime import datetime as _dt
        dt_ini = _dt.strptime(fecha_inicio, "%Y-%m-%d")
        return await self.get_matrix_data_with_projections(
            mes=dt_ini.month,
            anio=dt_ini.year,
            area=area,
            turno_id=turno_id,
            search=search,
            areas_permitidas=areas_permitidas,
            empleado_id=empleado_id,
            fecha_inicio_override=fecha_inicio,
            fecha_fin_override=fecha_fin,
        )

    async def get_matrix_data_by_range(
        self,
        fecha_inicio: str,
        fecha_fin: str,
        area: Optional[str] = None,
        turno_id: Optional[int] = None,
        areas_permitidas: Optional[List] = None,
    ) -> List[Dict]:
        """Raw list of asistencia rows for a date range (internal helper)."""
        db = self.repository.db
        q = """
            SELECT a.*, e.nombre, e.apellido_paterno, e.apellido_materno, ar.nombre as area, e.rut,
                   he.estado as estado_he, he.minutos_autorizados as minutos_extra_autorizados
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            LEFT JOIN horas_extras he ON he.empleado_id = a.empleado_id AND he.fecha = a.fecha
            WHERE a.fecha BETWEEN ? AND ?
              AND (e.excluido_asistencia = 0 OR e.excluido_asistencia IS NULL)
        """
        params: list = [fecha_inicio, fecha_fin]
        if area and area != 'Todas':
            q += " AND ar.nombre = ?"
            params.append(area)
        if turno_id:
            q += " AND a.turno_asignado_id = ?"
            params.append(turno_id)
        if areas_permitidas:
            placeholders = ','.join('?' * len(areas_permitidas))
            q += f" AND ar.nombre IN ({placeholders})"
            params.extend(areas_permitidas)
        q += " ORDER BY e.apellido_paterno, e.apellido_materno, e.nombre, a.fecha"
        rows = await db.fetch_all(q, tuple(params))
        return [dict(r) for r in rows]

    async def get_matrix_data_with_projections(
        self,
        mes: int,
        anio: int,
        area: Optional[str] = None,
        turno_id: Optional[int] = None,
        search: Optional[str] = None,
        areas_permitidas: Optional[List] = None,
        empleado_id: Optional[int] = None,
        fecha_inicio_override: Optional[str] = None,
        fecha_fin_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Datos enriquecidos para la Vista Equipo (matrix) y Vista Calendario.
        Devuelve: { matrix, empleados, feriados, periodo, data, justificaciones }
        """
        import calendar as cal_mod
        from backend.services.calendario_service import CalendarioService

        if fecha_inicio_override:
            fecha_inicio = fecha_inicio_override
            fecha_fin = fecha_fin_override
        else:
            _, ult_dia = cal_mod.monthrange(anio, mes)
            fecha_inicio = f"{anio:04d}-{mes:02d}-01"
            fecha_fin = f"{anio:04d}-{mes:02d}-{ult_dia:02d}"

        db = self.repository.db

        # Empleados: Solo aquellos con turno asignado vigente en el período.
        # Regla de negocio:
        #   1. Sin turno asignado → no aparece en la grilla.
        #   2. Activos siempre aparecen.
        #   3. Inactivos (baja) aparecen si su fecha_salida cae dentro del período consultado
        #      (tienen marcaciones válidas hasta esa fecha).
        q_emp = """
            SELECT DISTINCT e.*, ar.nombre as area
            FROM empleados e
            INNER JOIN asignacion_turnos ast ON e.id = ast.empleado_id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE (e.activo = 1 OR (e.activo = 0 AND e.fecha_salida IS NOT NULL AND e.fecha_salida >= ?))
              AND (e.excluido_asistencia = 0 OR e.excluido_asistencia IS NULL)
              AND ast.fecha_inicio <= ? AND (ast.fecha_fin IS NULL OR ast.fecha_fin >= ?)
        """
        params_emp: list = [fecha_inicio, fecha_fin, fecha_inicio]
        if area and area != 'Todas':
            q_emp += " AND ar.nombre = ?"
            params_emp.append(area)
        if areas_permitidas:
            ph = ','.join('?' * len(areas_permitidas))
            q_emp += f" AND ar.nombre IN ({ph})"
            params_emp.extend(areas_permitidas)
        if turno_id:
            q_emp += " AND ast.turno_id = ?"
            params_emp.append(turno_id)
        if empleado_id:
            q_emp += " AND e.id = ?"
            params_emp.append(empleado_id)
        if search:
            q_emp += " AND (e.nombre LIKE ? OR e.apellido_paterno LIKE ? OR e.rut LIKE ?)"
            s = f"%{search}%"
            params_emp.extend([s, s, s])
        q_emp += " ORDER BY e.apellido_paterno ASC, e.apellido_materno ASC, e.nombre ASC"
        emp_rows = await db.fetch_all(q_emp, tuple(params_emp))
        empleados = [dict(e) for e in emp_rows]
        emp_ids = [e['id'] for e in empleados]


        if not emp_ids:
            return {
                'matrix': {}, 'empleados': [], 'feriados': [],
                'periodo': {'inicio': fecha_inicio, 'fin': fecha_fin},
                'data': [], 'justificaciones': [],
            }

        ids_ph = ','.join('?' * len(emp_ids))

        cal_svc = CalendarioService()

        q_asist = f"""
            SELECT a.*, t.nombre as turno_nombre,
                   he.estado as estado_he,
                   he.minutos_autorizados as minutos_extra_autorizados,
                   COALESCE((SELECT SUM(minutos) FROM compensaciones_he_inasistencia WHERE empleado_id = a.empleado_id AND fecha_inasistencia = a.fecha), 0.0) as minutos_compensados_he,
                   td.etiqueta_bloque
            FROM asistencias a
            LEFT JOIN turnos t ON a.turno_asignado_id = t.id
            LEFT JOIN horas_extras he ON he.empleado_id = a.empleado_id AND he.fecha = a.fecha
            LEFT JOIN turno_dias td ON td.turno_id = a.turno_asignado_id 
                AND td.num_semana = a.num_semana_ganadora 
                AND td.dia_semana = (CASE strftime('%w', a.fecha) WHEN '0' THEN 6 ELSE CAST(strftime('%w', a.fecha) AS INTEGER) - 1 END)
            WHERE a.empleado_id IN ({ids_ph}) AND a.fecha BETWEEN ? AND ?
            ORDER BY a.empleado_id, a.fecha
        """
        
        q_jornadas = f"""
            SELECT j.* 
            FROM jornadas_especiales j
            WHERE j.empleado_id IN ({ids_ph}) AND j.fecha BETWEEN ? AND ?
        """
        
        q_asig = f"""
            SELECT a.empleado_id, a.turno_id, t.meta_horas_semanales, t.tipo_programacion, t.permite_viajes_largos, t.nombre as turno_nombre
            FROM asignacion_turnos a
            JOIN turnos t ON a.turno_id = t.id
            WHERE a.empleado_id IN ({ids_ph})
              AND a.fecha_inicio <= ? AND (a.fecha_fin IS NULL OR a.fecha_fin >= ?)
        """
        
        q_just = f"""
            SELECT j.*, jt.nombre AS tipo_nombre, jt.con_goce_sueldo, jt.pagador, jt.nomenclatura AS tipo_nomenclatura
            FROM justificaciones j
            JOIN justificacion_tipos jt ON j.tipo_id = jt.id
            WHERE j.empleado_id IN ({ids_ph})
              AND date(j.fecha_inicio) <= date(?) AND date(j.fecha_fin) >= date(?)
        """

        # Cargar asistencias, jornadas, asignación de turnos, justificaciones y feriados en paralelo
        tasks = [
            db.fetch_all(q_asist, tuple(emp_ids) + (fecha_inicio, fecha_fin)),
            db.fetch_all(q_jornadas, tuple(emp_ids) + (fecha_inicio, fecha_fin)),
            db.fetch_all(q_asig, tuple(emp_ids) + (fecha_fin, fecha_inicio)),
            db.fetch_all(q_just, tuple(emp_ids) + (fecha_fin, fecha_inicio)),
            cal_svc.get_feriados(anio)
        ]
        
        asist_rows, jornadas_rows, asig_emp_rows, just_rows, feriados_raw = await asyncio.gather(*tasks)

        asistencias = [dict(a) for a in asist_rows]
        if turno_id:
            asistencias = [a for a in asistencias if a.get('turno_asignado_id') == turno_id or (a.get('turno_asignado_id') is None and a.get('estado') == 'VIAJE_LARGO')]

        jornadas_especiales = [dict(j) for j in jornadas_rows]

        feriados_dict = {f['fecha']: f['descripcion'] for f in feriados_raw}
        feriados_list = [{'fecha': k, 'descripcion': v} for k, v in feriados_dict.items()
                         if fecha_inicio <= k <= fecha_fin]

        turno_ids_emp = {}
        for row in asig_emp_rows:
            turno_ids_emp[row['empleado_id']] = dict(row)

        # Calcular primer_dia_semana por turno (primer día laborable post-descanso)
        all_t_ids = list({r['turno_id'] for r in asig_emp_rows})
        primer_dia_por_turno = {}
        dias_por_turno = {}
        if all_t_ids:
            t_ph = ','.join('?' * len(all_t_ids))
            dias_rows = await db.fetch_all(
                f"SELECT turno_id, dia_semana, hora_entrada, hora_salida, es_libre FROM turno_dias WHERE turno_id IN ({t_ph})",
                tuple(all_t_ids)
            )
            for r in dias_rows:
                tid = r['turno_id']
                if tid not in dias_por_turno:
                    dias_por_turno[tid] = {}
                if r['dia_semana'] not in dias_por_turno[tid]:
                    dias_por_turno[tid][r['dia_semana']] = {
                        'es_libre': r['es_libre'],
                        'hora_entrada': r['hora_entrada'],
                        'hora_salida': r['hora_salida']
                    }
                else:
                    # [BUSINESS_RULE: PROYECCIÓN UI DINAMICO_FLEXIBLE]
                    # Si el turno tiene múltiples semanas (DINAMICO_FLEXIBLE),
                    # el día solo se proyecta como LIBRE absoluto si en *todas*
                    # las semanas es libre. De lo contrario, se cruza con 0 (bit-wise AND).
                    dias_por_turno[tid][r['dia_semana']]['es_libre'] &= r['es_libre']

            for tid, dias_map in dias_por_turno.items():
                primer_dia = 0 # Default Lunes
                for d in range(7):
                    if dias_map.get(d, {}).get('es_libre', 0) == 0:
                        prev_d = (d - 1) % 7
                        if dias_map.get(prev_d, {}).get('es_libre', 0) == 1:
                            primer_dia = d
                            break
                primer_dia_por_turno[tid] = primer_dia

        # Construir matrix: {emp_id: {fecha: asistencia_row, 'info': {...}}}
        matrix: Dict = {}

        for emp in empleados:
            eid = emp['id']
            ap = emp.get('apellido_paterno', '') or ''
            am = emp.get('apellido_materno', '') or ''
            nm = emp.get('nombre', '') or ''
            apellidos = f"{ap} {am}".strip()
            emp['nombre_completo'] = f"{ap} {am} {nm}".strip().replace('  ', ' ')
            # Enriquecer con datos de turno para el acumulado semanal del frontend
            t_info = turno_ids_emp.get(eid, {})
            if t_info:
                emp['meta_horas_semanales'] = t_info.get('meta_horas_semanales') or 45.0
                emp['tipo_programacion'] = t_info.get('tipo_programacion') or 'DINAMICO_FLEXIBLE'
                emp['permite_viajes_largos'] = t_info.get('permite_viajes_largos') or 0
                emp['turno'] = t_info.get('turno_nombre')
                t_id = t_info.get('turno_id')
                emp['primer_dia_semana_turno'] = primer_dia_por_turno.get(t_id, 1)  # default Lunes
                emp['turno_dias'] = dias_por_turno.get(t_id, {})
            matrix[eid] = {'info': emp}


        hoy_str = _get_now_local().strftime("%Y-%m-%d")

        for a in asistencias:
            eid = a['empleado_id']
            if eid in matrix:
                f_asist = a.get('fecha')
                # [FIX EN_CURSO DIAS PASADOS]: Un día pasado NUNCA puede permanecer en EN_CURSO
                # a menos que sea un turno nocturno activo de ayer durante su ventana matutina.
                if a.get('estado') == 'EN_CURSO' and f_asist and f_asist < hoy_str:
                    if a.get('hora_entrada_real') and a.get('hora_salida_real'):
                        a['estado'] = 'ATRASO' if a.get('tiene_atraso') else 'OK'
                    elif a.get('hora_entrada_real') and not a.get('hora_salida_real'):
                        a['estado'] = 'ANOMALIA'
                        a['observaciones'] = (a.get('observaciones') or '').replace('Jornada en curso (falta salida).', 'Solo una marcación (falta salida).')
                    elif not a.get('hora_entrada_real'):
                        a['estado'] = 'INASISTENCIA'

                matrix[eid][f_asist] = a

        # Superponer jornadas especiales — enriquecer marcas, NO pisar asistencias.estado
        # Tabla jornadas_especiales.estado es un estado INTERNO de flujo de validación:
        #   PENDIENTE → interno: ESP con 2 marcas esperando validación de jefe
        #   JORNADA_ESPECIAL → interno: ESP confirmada por motor
        #   EXTRA → validada por jefe  → SÍ se muestra en grilla
        #   RECHAZADA → rechazada por jefe → SÍ se muestra en grilla
        # La grilla siempre toma asistencias.estado como fuente de verdad.
        # Solo EXTRA y RECHAZADA del flujo JE pueden cambiar el estado visual.
        ESTADOS_JE_QUE_PISAN = {'EXTRA', 'RECHAZADA'}

        for j in jornadas_especiales:
            eid = j['empleado_id']
            if eid in matrix:
                is_emp_bolsa = (matrix[eid].get('info', {}).get('tipo_programacion') == 'FLEXIBLE_BOLSA')
                if is_emp_bolsa:
                    continue
                f_str = j['fecha']
                je_estado = j['estado']

                if f_str in matrix[eid]:
                    # Inyectar metadatos para renderizado de Celda Dividida (Split Cell) en el frontend
                    matrix[eid][f_str]['jornada_adicional'] = {
                        'id': j['id'],
                        'estado': j['estado'],
                        'hora_entrada': j['hora_entrada'],
                        'hora_salida': j['hora_salida'],
                        'minutos_trabajados': j['minutos_trabajados'],
                        'observaciones': j.get('observaciones') or ''
                    }
                    
                    # Conservar el estado ordinario a la izquierda. Si la JE está validada (EXTRA/RECHAZADA),
                    # enriquecer o pisar según lógica tradicional
                    if je_estado in ESTADOS_JE_QUE_PISAN:
                        es_dia_habil = float(matrix[eid][f_str].get('horas_teoricas') or 0.0) > 0.0
                        if es_dia_habil:
                            # En día hábil ordinario, NO pisamos la asistencia ordinaria de la mañana.
                            # Queremos conservar el estado ordinario a la izquierda (ej: OK, ATRASO, etc.)
                            pass
                        else:
                            matrix[eid][f_str]['estado'] = je_estado
                            # Enriquecer horas reales SOLO si la JE las tiene definidas.
                            if j['hora_entrada'] is not None:
                                matrix[eid][f_str]['hora_entrada_real'] = j['hora_entrada']
                            if j['hora_salida'] is not None:
                                matrix[eid][f_str]['hora_salida_real'] = j['hora_salida']
                            matrix[eid][f_str]['minutos_extra_bruto'] = 0
                            matrix[eid][f_str]['minutos_extra_autorizados'] = 0
                            matrix[eid][f_str]['minutos_deuda'] = 0
                            matrix[eid][f_str]['horas_trabajadas'] = (j['minutos_trabajados'] or 0) / 60.0
                            matrix[eid][f_str]['observaciones'] = j.get('observaciones') or ''
                    else:
                        # Si la JE está PENDIENTE en un día sin turno ordinario efectivo (LIBRE),
                        # asignar su estado visual como JORNADA_ESPECIAL para sustituir la etiqueta LIBRE
                        if matrix[eid][f_str].get('estado') == 'LIBRE' or not matrix[eid][f_str].get('hora_entrada_real'):
                            matrix[eid][f_str]['estado'] = 'JORNADA_ESPECIAL'
                    # Nota: no existe rama else (JE sin asistencias).
                    # El motor siempre crea ambos registros juntos. Si faltara asistencias
                    # sería un bug de integridad que debe investigarse, no silenciarse.

        # Superponer viajes_largos para adjuntar objeto viaje_largo a las celdas del primer día
        q_vl = f"""
            SELECT * FROM viajes_largos
            WHERE empleado_id IN ({ids_ph})
              AND fecha_inicio <= ? AND fecha_fin >= ?
        """
        vl_rows = await db.fetch_all(q_vl, tuple(emp_ids) + (fecha_fin, fecha_inicio))
        for vl in vl_rows:
            v_dict = dict(vl)
            eid = v_dict['empleado_id']
            f_ini_vl = v_dict['fecha_inicio']
            f_fin_vl = v_dict['fecha_fin']
            if eid in matrix:
                try:
                    d_cur = datetime.strptime(f_ini_vl[:10], '%Y-%m-%d')
                    d_end = datetime.strptime(f_fin_vl[:10], '%Y-%m-%d')

                    # Chequear si cruza domingos o feriados
                    tiene_feriado_en_ruta = False
                    tiene_domingo_en_ruta = False
                    d_chk = d_cur
                    while d_chk <= d_end:
                        ds_c = d_chk.strftime('%Y-%m-%d')
                        if ds_c in feriados_dict:
                            tiene_feriado_en_ruta = True
                        if d_chk.weekday() == 6:
                            tiene_domingo_en_ruta = True
                        d_chk += timedelta(days=1)

                    v_dict['feriado_en_ruta'] = tiene_feriado_en_ruta
                    v_dict['domingo_en_ruta'] = tiene_domingo_en_ruta

                    # Evaluar descanso post-viaje en el día de retorno
                    ds_fin = d_end.strftime('%Y-%m-%d')
                    if ds_fin in matrix[eid]:
                        cell_retorno = matrix[eid][ds_fin]
                        h_salida_vl = v_dict['fecha_fin'][11:16] if (v_dict.get('fecha_fin') and len(v_dict['fecha_fin']) > 10) else None
                        h_ent_local = cell_retorno.get('hora_entrada_real')
                        if h_salida_vl and h_ent_local:
                            try:
                                dt_ret = datetime.strptime(f"{ds_fin} {h_salida_vl[:5]}", "%Y-%m-%d %H:%M")
                                dt_ent = datetime.strptime(f"{ds_fin} {h_ent_local[:5]}", "%Y-%m-%d %H:%M")
                                if dt_ent > dt_ret:
                                    diff_descanso = round((dt_ent - dt_ret).total_seconds() / 3600.0, 1)
                                    v_dict['descanso_post_viaje_horas'] = diff_descanso
                                    if diff_descanso < 8.0:
                                        v_dict['alerta_descanso_post_viaje'] = True
                                    else:
                                        v_dict['cumple_descanso_post_viaje'] = True
                            except Exception:
                                pass

                    while d_cur <= d_end:
                        ds = d_cur.strftime('%Y-%m-%d')
                        if ds in matrix[eid]:
                            cell = matrix[eid][ds]
                            cell['viaje_largo'] = v_dict
                            cell['tiene_viaje_largo'] = 1
                            cell['tiene_anomalia'] = 0
                            cell['alerta_anomalia'] = 0
                            if cell.get('estado') in ('ANOMALIA', 'INASISTENCIA', 'PENDIENTE', None):
                                cell['estado'] = 'VIAJE_LARGO'
                        d_cur += timedelta(days=1)
                except Exception:
                    pass

        # Proyectar feriados no procesados
        cur = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d")
        while cur <= fin_dt:
            f_str = cur.strftime("%Y-%m-%d")
            if f_str in feriados_dict:
                for eid in matrix:
                    if f_str not in matrix[eid]:
                        matrix[eid][f_str] = {
                            'empleado_id': eid,
                            'fecha': f_str,
                            'estado': 'FERIADO',
                            'observaciones': feriados_dict[f_str],
                            'hora_entrada_real': None,
                            'hora_salida_real': None,
                            'horas_trabajadas': 0,
                        }
            cur += timedelta(days=1)

        # Justificaciones del período (precargadas concurrentemente arriba)
        justificaciones = [dict(j) for j in just_rows]

        # Inyectar nomenclaturas y justificaciones en la matriz a partir de justificaciones
        for just in justificaciones:
            eid = just.get('empleado_id')
            if eid in matrix:
                try:
                    cur_dt = datetime.strptime(just['fecha_inicio'][:10], "%Y-%m-%d")
                    end_dt = datetime.strptime(just['fecha_fin'][:10], "%Y-%m-%d")
                    nomen = (just.get('tipo_nomenclatura') or just.get('nomenclatura') or 'DEOP').upper()
                    t_nombre = (just.get('tipo_nombre') or just.get('nombre') or 'DESCANSO OPERATIVO').upper()
                    es_corrido = bool(just.get('dias_corridos'))
                    sobreescribe_fer = bool(just.get('sobreescribe_feriados'))
                    emp_td = matrix[eid].get('info', {}).get('turno_dias', {})

                    while cur_dt <= end_dt:
                        f_str = cur_dt.strftime("%Y-%m-%d")
                        if f_str in matrix[eid]:
                            cell = matrix[eid][f_str]
                            is_fer = (f_str in feriados_dict) or cell.get('estado') == 'FERIADO'
                            weekday_db = cur_dt.weekday()  # 0=Lun .. 6=Dom
                            td_cfg = emp_td.get(str(weekday_db)) or emp_td.get(weekday_db) or {}
                            is_struct_libre = bool(td_cfg.get('es_libre'))
                            is_cell_libre = (cell.get('estado') == 'LIBRE')
                            has_work_punches = bool(cell.get('hora_entrada_real') or cell.get('hora_salida_real'))

                            # Si es feriado y la justificación NO sobreescribe feriados -> Mantener FERIADO
                            if is_fer and not sobreescribe_fer:
                                if not has_work_punches:
                                    cell['estado'] = 'FERIADO'
                                    cell['observaciones'] = feriados_dict.get(f_str, 'Feriado Nacional')
                                    cell.pop('justificacion_id', None)
                                    cell.pop('nomenclatura', None)
                            # Si es día libre (estructural o en celda) sin marcas y la justificación NO es por días corridos -> Mantener LIBRE
                            elif (is_struct_libre or is_cell_libre) and not es_corrido and not has_work_punches:
                                cell['estado'] = 'LIBRE'
                                cell['observaciones'] = 'Día Libre de Turno'
                                cell.pop('justificacion_id', None)
                                cell.pop('nomenclatura', None)
                            else:
                                cell['justificacion_id'] = just.get('id')
                                cell['justificacion'] = just
                                cell['nomenclatura'] = nomen
                                cell['estado'] = t_nombre
                        cur_dt += timedelta(days=1)
                except Exception as _exc:
                    logger.debug(f"[Matrix] Error inyectando justificacion: {_exc}")

        # Determinar si el periodo/rango actual está cerrado
        # Si es un cierre por área específica, se busca en cierres_periodos.
        # Si es global ('Todas' las áreas), se considera cerrado solo si está marcado como cerrado en periodos_rrhh.
        if area and area != 'Todas':
            q_cierre = "SELECT COUNT(*) as count FROM cierres_periodos WHERE fecha_inicio <= ? AND fecha_fin >= ?"
            params_cierre = [fecha_fin, fecha_inicio]
            q_cierre += " AND (area IS NULL OR area = ?)"
            params_cierre.append(area)
            if turno_id:
                q_cierre += " AND (turno_id IS NULL OR turno_id = ?)"
                params_cierre.append(turno_id)
            res_cierre = await db.fetch_one(q_cierre, tuple(params_cierre))
            periodo_cerrado = res_cierre['count'] > 0 if res_cierre else False
        else:
            q_rrhh = "SELECT COUNT(*) as count FROM periodos_rrhh WHERE fecha_inicio <= ? AND fecha_fin >= ? AND estado = 'cerrado'"
            res_rrhh = await db.fetch_one(q_rrhh, (fecha_fin, fecha_inicio))
            periodo_cerrado = res_rrhh['count'] > 0 if res_rrhh else False

        return {
            'matrix': matrix,
            'empleados': empleados,
            'feriados': feriados_list,
            'periodo': {
                'inicio': fecha_inicio, 
                'fin': fecha_fin, 
                'mes': mes, 
                'anio': anio,
                'cerrado': periodo_cerrado
            },
            'data': asistencias,
            'justificaciones': justificaciones,
        }


    async def get_cached_turno_dia(self, turno_id: int, dia_semana: int, num_semana: int = 1) -> Optional[Dict]:
        db = self.repository.db
        rows = await db.fetch_all(
            "SELECT t.*, td.dia_semana, td.hora_entrada, td.hora_salida, td.es_libre "
            "FROM turnos t JOIN turno_dias td ON t.id = td.turno_id "
            "WHERE t.id = ? AND td.dia_semana = ? AND td.num_semana = ?",
            (turno_id, dia_semana, num_semana)
        )
        return dict(rows[0]) if rows else None

    async def get_daily_stats(
        self,
        fecha: str,
        area: Optional[str] = None,
        areas_permitidas: Optional[List] = None,
    ) -> Dict[str, Any]:
        db = self.repository.db
        q = "SELECT estado, COUNT(*) as cnt FROM asistencias WHERE fecha = ?"
        params: list = [fecha]
        if area and area != 'Todas':
            q += " AND empleado_id IN (SELECT e.id FROM empleados e LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1 LEFT JOIN areas a ON ha.area_id = a.id WHERE a.nombre = ?)"
            params.append(area)
        if areas_permitidas:
            ph = ','.join('?' * len(areas_permitidas))
            q += f" AND empleado_id IN (SELECT e.id FROM empleados e LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1 LEFT JOIN areas a ON ha.area_id = a.id WHERE a.nombre IN ({ph}))"
            params.extend(areas_permitidas)
        q += " GROUP BY estado"
        rows = await db.fetch_all(q, tuple(params))
        return {r['estado']: r['cnt'] for r in rows}


    # ─────────────────────────────────────────────────────────────────────────
    # BOLSA DE HORAS
    # ─────────────────────────────────────────────────────────────────────────

    async def recalcular_bolsa_periodo(self, empleado_id: int, fecha_ini: str, fecha_fin: str) -> Dict:
        db = self.repository.db
        # Sumar todas las horas extras aprobadas en el periodo
        row_he = await db.fetch_one(
            "SELECT SUM(minutos_autorizados) as total_he FROM horas_extras WHERE empleado_id = ? AND fecha BETWEEN ? AND ? AND estado = 'APROBADO'",
            (empleado_id, fecha_ini, fecha_fin)
        )
        total_extra_aprobado = (row_he['total_he'] or 0.0) if row_he else 0.0

        # Sumar todas las compensaciones de inasistencia en el periodo
        row_comp = await db.fetch_one(
            "SELECT SUM(minutos) as total_comp FROM compensaciones_he_inasistencia WHERE empleado_id = ? AND fecha_inasistencia BETWEEN ? AND ?",
            (empleado_id, fecha_ini, fecha_fin)
        )
        total_compensado = (row_comp['total_comp'] or 0.0) if row_comp else 0.0

        total_extra = max(0.0, total_extra_aprobado - total_compensado)

        # Deuda sigue leyendo de asistencias (es disciplinaria, no financiera)
        rows_deuda = await db.fetch_all(
            "SELECT minutos_deuda FROM asistencias WHERE empleado_id = ? AND fecha BETWEEN ? AND ?",
            (empleado_id, fecha_ini, fecha_fin)
        )
        total_deuda = sum(int(r.get('minutos_deuda', 0) or 0) for r in rows_deuda)
        saldo = total_extra - total_deuda
        return {'empleado_id': empleado_id, 'fecha_inicio': fecha_ini, 'fecha_fin': fecha_fin,
                'minutos_extra': total_extra, 'minutos_deuda': total_deuda, 'saldo': saldo}

    async def ejecutar_cierre_periodo(
        self, fecha_inicio: str, fecha_fin: str, area: Optional[str] = None, turno_id: Optional[int] = None,
        usuario_id: Optional[int] = None, username: Optional[str] = None, comentarios: Optional[str] = None
    ) -> Dict:
        db = self.repository.db
        
        # 1. Guardar el registro de cierre para blindar el periodo
        q_cierre = """
            INSERT INTO cierres_periodos (fecha_inicio, fecha_fin, usuario_id, username, tipo_cierre, comentarios, area, turno_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params_cierre = (fecha_inicio, fecha_fin, usuario_id, username, 'RRHH', comentarios, area, turno_id)
        res_cierre = await db.execute(q_cierre, params_cierre)
        cierre_id = res_cierre.lastrowid
        
        # 1.1 Si hay un periodo en periodos_rrhh que coincide con el rango cerrado, marcarlo como 'cerrado'
        # Pero solo si todas las áreas activas están cerradas
        try:
            active_areas_res = await db.fetch_all(
                """
                SELECT DISTINCT ar.nombre FROM empleados e
                JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.validado = 1
                    AND (? >= ha.fecha_desde AND (ha.fecha_hasta IS NULL OR ha.fecha_hasta = '' OR ? <= ha.fecha_hasta))
                JOIN areas ar ON ha.area_id = ar.id
                WHERE e.activo = 1
                """,
                (fecha_fin, fecha_inicio)
            )
            active_areas = {r['nombre'] for r in active_areas_res if r['nombre']}

            closed_areas_res = await db.fetch_all(
                "SELECT DISTINCT area FROM cierres_periodos WHERE fecha_inicio = ? AND fecha_fin = ? AND area IS NOT NULL",
                (fecha_inicio, fecha_fin)
            )
            closed_areas = {r['area'] for r in closed_areas_res if r['area']}
            if area:
                closed_areas.add(area)

            should_close_global = active_areas.issubset(closed_areas)

            if should_close_global:
                # Obtener la info del periodo antes de cerrarlo para ver si era el activo
                periodo = await db.fetch_one(
                    "SELECT activo FROM periodos_rrhh WHERE fecha_inicio = ? AND fecha_fin = ?",
                    (fecha_inicio, fecha_fin)
                )
                
                # Marcar como cerrado
                await db.execute(
                    "UPDATE periodos_rrhh SET estado = 'cerrado' WHERE fecha_inicio = ? AND fecha_fin = ?",
                    (fecha_inicio, fecha_fin)
                )
                logger.info(f"✨ periodos_rrhh actualizado a 'cerrado' para el rango {fecha_inicio} a {fecha_fin} (AsistenciaService)")
                
                # Si era el periodo activo/vigente, hacer la transición
                if periodo and (periodo["activo"] == 1 or periodo["activo"] is True):
                    await db.execute(
                        "UPDATE periodos_rrhh SET activo = 0 WHERE fecha_inicio = ? AND fecha_fin = ?",
                        (fecha_inicio, fecha_fin)
                    )
                    logger.info(f"✨ Periodo {fecha_inicio} al {fecha_fin} desmarcado como Vigente.")
                    
                    # Buscar el siguiente periodo abierto
                    next_periodo = await db.fetch_one(
                        "SELECT id, mes_cierre FROM periodos_rrhh WHERE estado = 'abierto' ORDER BY fecha_inicio ASC LIMIT 1"
                    )
                    if next_periodo:
                        await db.execute(
                            "UPDATE periodos_rrhh SET activo = 1 WHERE id = ?",
                            (next_periodo["id"],)
                        )
                        logger.info(f"✨ Siguiente periodo promovido a Vigente: {next_periodo['mes_cierre']} (ID: {next_periodo['id']})")
                    else:
                        logger.info("ℹ️ No hay más periodos abiertos para promover como Vigente.")
            else:
                logger.info(
                    f"ℹ️ Cierre de area '{area}' guardado (AsistenciaService), pero periodos_rrhh permanece 'abierto' "
                    f"porque quedan areas activas por cerrar. "
                    f"Activas: {active_areas} | Cerradas: {closed_areas}"
                )
        except Exception as e_close_rrhh:
            logger.warning(f"⚠️ No se pudo actualizar el estado/vigencia en periodos_rrhh: {e_close_rrhh}")
        
        # 2. Recalcular las bolsas de todos los empleados afectados
        q_emp = "SELECT id FROM empleados WHERE activo = 1 AND (excluido_asistencia = 0 OR excluido_asistencia IS NULL)"
        params_emp = []
        if area:
            q_emp += " AND area = ?"
            params_emp.append(area)
        if turno_id:
            q_emp += " AND id IN (SELECT empleado_id FROM asistencias WHERE fecha BETWEEN ? AND ? AND turno_asignado_id = ?)"
            params_emp.extend([fecha_inicio, fecha_fin, turno_id])

        emp_rows = await db.fetch_all(q_emp, tuple(params_emp))
        resultados = []
        for e in emp_rows:
            r = await self.recalcular_bolsa_periodo(e['id'], fecha_inicio, fecha_fin)
            resultados.append(r)
            
        return {'cierre_id': cierre_id, 'periodo': f"{fecha_inicio} a {fecha_fin}", 'resultados': resultados}

    # ─────────────────────────────────────────────────────────────────────────
    # RESÚMENES RRHH
    # ─────────────────────────────────────────────────────────────────────────

    async def get_period_summary_rrhh(
        self, fecha_inicio: str, fecha_fin: str, area: Optional[str] = None, turno_id: Optional[int] = None
    ) -> Dict:
        db = self.repository.db
        q = """
            SELECT e.id, e.nombre, e.apellido_paterno, e.apellido_materno, ar.nombre as area,
                   COUNT(a.fecha) as dias_procesados,
                   SUM(CASE WHEN a.estado = 'OK' THEN 1 ELSE 0 END) as dias_ok,
                   SUM(CASE WHEN a.estado = 'INASISTENCIA' THEN 1 ELSE 0 END) as inasistencias,
                   SUM(CASE WHEN a.estado = 'ATRASO' THEN 1 ELSE 0 END) as atrasos,
                   SUM(a.horas_trabajadas) as total_horas
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            LEFT JOIN asistencias a ON e.id = a.empleado_id AND a.fecha BETWEEN ? AND ?
            WHERE e.activo = 1 AND (e.excluido_asistencia = 0 OR e.excluido_asistencia IS NULL)
        """
        params = [fecha_inicio, fecha_fin]
        if area:
            q += " AND ar.nombre = ?"
            params.append(area)
        if turno_id:
            q += " AND a.turno_asignado_id = ?"
            params.append(turno_id)
            
        q += " GROUP BY e.id ORDER BY e.apellido_paterno, e.apellido_materno, e.nombre"
        rows = await db.fetch_all(q, tuple(params))
        return {'resumen': [dict(r) for r in rows]}

    async def get_resumen_cierre_global(
        self, fecha_inicio: str, fecha_fin: str, area: Optional[str] = None, turno_id: Optional[int] = None
    ) -> Dict:
        db = self.repository.db
        
        # 1. Calcular total HE aprobadas
        params_he = [fecha_inicio, fecha_fin]
        q_he = """
            SELECT SUM(h.minutos_autorizados) as total_he
            FROM horas_extras h
            JOIN empleados e2 ON h.empleado_id = e2.id
            LEFT JOIN historial_areas ha2 ON e2.id = ha2.empleado_id AND ha2.es_actual = 1 AND ha2.validado = 1
            LEFT JOIN areas ar2 ON ha2.area_id = ar2.id
            WHERE h.fecha BETWEEN ? AND ? AND e2.activo = 1 AND (e2.excluido_asistencia = 0 OR e2.excluido_asistencia IS NULL) AND h.estado = 'APROBADO'
        """
        if area:
            q_he += " AND ar2.nombre = ?"
            params_he.append(area)
            
        # 2. Calcular total compensado
        params_comp = [fecha_inicio, fecha_fin]
        q_comp = """
            SELECT SUM(c.minutos) as total_comp
            FROM compensaciones_he_inasistencia c
            JOIN empleados e3 ON c.empleado_id = e3.id
            LEFT JOIN historial_areas ha3 ON e3.id = ha3.empleado_id AND ha3.es_actual = 1 AND ha3.validado = 1
            LEFT JOIN areas ar3 ON ha3.area_id = ar3.id
            WHERE c.fecha_inasistencia BETWEEN ? AND ? AND e3.activo = 1 AND (e3.excluido_asistencia = 0 OR e3.excluido_asistencia IS NULL)
        """
        if area:
            q_comp += " AND ar3.nombre = ?"
            params_comp.append(area)

        # 3. Calcular total deuda
        params_asis = [fecha_inicio, fecha_fin]
        q_asis = """
            SELECT SUM(CASE WHEN a.minutos_deuda > 0 THEN a.minutos_deuda ELSE 0 END) as total_deuda
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE a.fecha BETWEEN ? AND ? AND e.activo = 1 AND (e.excluido_asistencia = 0 OR e.excluido_asistencia IS NULL)
        """
        if area:
            q_asis += " AND ar.nombre = ?"
            params_asis.append(area)
        if turno_id:
            q_asis += " AND a.turno_asignado_id = ?"
            params_asis.append(turno_id)

        row_he = await db.fetch_one(q_he, tuple(params_he))
        row_comp = await db.fetch_one(q_comp, tuple(params_comp))
        row_asis = await db.fetch_one(q_asis, tuple(params_asis))

        total_he_aprobado = (row_he['total_he'] or 0.0) if row_he else 0.0
        total_compensado = (row_comp['total_comp'] or 0.0) if row_comp else 0.0
        total_he = max(0.0, total_he_aprobado - total_compensado)
        total_deuda = int((row_asis['total_deuda'] or 0) if row_asis else 0)
        total_balance = total_he - total_deuda
        
        # Obtener detalle por empleado para el array 'resumen'
        resumen_empleados = await self.get_period_summary_rrhh(fecha_inicio, fecha_fin, area, turno_id)
        
        return {
            "total_he_aprobado": total_he,
            "total_deuda": total_deuda,
            "total_balance": total_balance,
            "resumen": resumen_empleados.get("resumen", [])
        }

    async def aprobar_horas_extras_batch(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aprueba o rechaza múltiples registros de horas extra a la vez.
        Encapsula el blindaje de cierre y la lógica de negocio.
        """
        params_list = []
        for item in items:
            emp_id = item.get('empleado_id')
            fecha = item.get('fecha')
            
            # Blindaje de Cierre
            if await self.repository.check_fecha_cerrada(fecha, emp_id):
                 raise ValueError(f"El periodo para la fecha {fecha} se encuentra cerrado.")
                 
            estado = item.get('estado')
            minutos = item.get('minutos_autorizados', 0)
            
            # Blindaje: Si es RECHAZADO, forzar 0
            if estado == 'RECHAZADO':
                minutos = 0
                
            if emp_id and fecha and estado:
                params_list.append({
                    'empleado_id': emp_id,
                    'fecha': fecha,
                    'estado': estado,
                    'minutos_autorizados': minutos
                })
                
        if not params_list:
            return {"success": True, "mensaje": "Nada que procesar", "count": 0}
            
        count = await self.he_repo.aprobar_batch(params_list)
        await self.repository.db.sync_to_cloud_explicit()
        
        return {
            "success": True,
            "mensaje": f"Se procesaron {count} registros de horas extra",
            "count": count
        }


# ─────────────────────────────────────────────────────────────────────────────
# HELPER MODULE-LEVEL
# ─────────────────────────────────────────────────────────────────────────────

def asignacion_valida(turno: Dict) -> bool:
    """Verifica si la asignación de turno tiene datos suficientes."""
    return bool(turno and turno.get('id'))
