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
import math
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger

from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.empleado import EmpleadoRepository
from asyncio import Lock

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
            # GUARD activo=1: si un empleado se desactiva durante el sync (raro pero posible),
            # no debe ser procesado aunque su ID ya esté en el set del batch.
            ph = ','.join('?' * len(empleado_ids))
            q_emp = f"SELECT * FROM empleados WHERE id IN ({ph}) AND activo = 1"
            params_emp = list(empleado_ids)
        else:
            # Modo completo: todos los activos (comportamiento original)
            q_emp = "SELECT * FROM empleados WHERE activo = 1 OR (fecha_salida IS NOT NULL AND fecha_salida >= ?)"
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
            SELECT t.*, a.empleado_id, a.fecha_inicio as asignacion_desde
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
                'redondeo_minutos', 'es_turno_cortado', 'meta_horas_semanales',
                'tipo_programacion', 'nombre',
                'rotacion_secuencial', 'semana_fallback_sin_marcas',
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
                elif he_estado == 'PENDIENTE':
                    results_to_delete_he.append((emp_id, fecha))
            else:
                results_to_delete.append((emp_id, fecha))
        
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
        
        if results_to_save or results_to_delete or he_to_save or results_to_delete_he:
            await self.repository.db.sync_to_cloud_explicit()

    # ─────────────────────────────────────────────────────────────────────────
    # REPROCESO PERÍODO EMPLEADO
    # ─────────────────────────────────────────────────────────────────────────

    async def reprocesar_periodo_empleado(
        self,
        empleado_id: int,
        fecha_inicio: str,
        fecha_fin: str,
        force: bool = False,
        job_id: Optional[str] = None,
        feriados_preloaded: Optional[Dict] = None,
        collect_only: bool = False,
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
            SELECT t.*, a.empleado_id, a.fecha_inicio as asignacion_desde, a.fecha_fin as asig_fecha_fin
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
                'redondeo_minutos', 'es_turno_cortado', 'meta_horas_semanales',
                'tipo_programacion', 'nombre',
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
        marcas_consumidas = {}
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
                'horas_extras': {empleado_id: he_map.get(fecha_str)} if he_map.get(fecha_str) else {},
                'feriados': feriados_dict,
                'periodos_empleo': {empleado_id: periodos},
                'first_assignments': {empleado_id: first_assignment},
                'rotativo_last_sem_dict': rotativo_last_sem_dict,
                'closed_dates': closed_dates
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
                    asistencias_map[fecha_str] = result
                else:
                    existing = asistencias_map.get(fecha_str)
                    if existing:
                        results_to_delete.append((empleado_id, fecha_str))
                        # No agregamos a stats['sin_cambio'] porque estamos eliminando el registro
                stats['procesados'] += 1
            except Exception as e:
                logger.error(f"Error calculando asistencia empleado {empleado_id} fecha {fecha_str}: {e}")
                stats['errores'] += 1

            # ⚡ Checkpoint de seguridad: guardar batch parcial cada N días
            # Deshabilitado en collect_only (CHECKPOINT_INTERVAL=0 → modulo nunca es 0)
            if not collect_only and (results_to_save or results_to_delete) and CHECKPOINT_INTERVAL > 0 and day_index % CHECKPOINT_INTERVAL == 0:
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
            return {'_collect': results_to_save, '_he_collect': he_to_save, '_he_delete': he_to_delete, **stats}

        # ⚡ BATCH FINAL: guardar todos los resultados restantes en UN SOLO commit local (WAL)
        # suppress_auto_sync=True: NO disparar conn.sync() aquí.
        # El caller (reproceso_masivo_async) hará 1 único sync_to_cloud_explicit() al final.
        if not collect_only and (results_to_save or results_to_delete):
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
        q = "SELECT id FROM empleados WHERE activo = 1"
        params = []
        if area:
            q += " AND area = ?"
            params.append(area)
        emp_rows = await db.fetch_all(q, tuple(params))
        emp_ids = [e['id'] for e in emp_rows]
        _reproceso_status['total'] = len(emp_ids)

        try:
            for eid in emp_ids:
                if eid in _empleados_en_reproceso:
                    continue
                _empleados_en_reproceso.add(eid)
                try:
                    r = await self.reprocesar_periodo_empleado(eid, fecha_inicio, fecha_fin, force=force)
                    _reproceso_status['procesados'] += r.get('procesados', 0)
                    _reproceso_status['errores'] += r.get('errores', 0)
                except Exception as e:
                    logger.error(f"Error masivo empleado {eid}: {e}")
                    _reproceso_status['errores'] += 1
                finally:
                    _empleados_en_reproceso.discard(eid)

            # ── 1 ÚNICO sync final a Turso Cloud (patrón batch) ──────────────
            # Todos los batch_upsert anteriores usaron suppress_auto_sync=True (WAL local).
            # Este único conn.sync() consolida TODO el WAL en 1 sola operación de red.
            # Elimina los N×429 "Too Many Requests" que ocurrían con N syncs simultáneos.
            try:
                logger.info(f"☁️ [Reproceso Masivo] Iniciando sync final único a Turso Cloud ({len(emp_ids)} empleados)...")
                await db.sync_to_cloud_explicit()
                logger.info(f"☁️ [Reproceso Masivo] Sync final completado.")
            except Exception as sync_err:
                logger.warning(f"⚠️ [Reproceso Masivo] Sync final falló (datos seguros en WAL local): {sync_err}")

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
        
        # Buscar en jornadas_especiales primero
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
            estado_asistencia = 'JORNADA_ESPECIAL' if accion == 'APROBAR' else 'INASISTENCIA'
            estado_ret = 'APROBADO' if accion == 'APROBAR' else 'RECHAZADO'
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
            is_closed = fecha in bulk_ctx['closed_dates']
        else:
            is_closed = await self.is_fecha_cerrada_empleado(empleado_id, fecha)
            
        if is_closed:
            logger.warning(f"🚫 Intento de procesar día cerrado: emp {empleado_id}, fecha {fecha}. Retornando registro existente.")
            return await self.repository.get_asistencia(empleado_id, fecha)

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
                    tiene_marcas = bool(bulk_ctx.get('logs', {}).get(empleado_id))
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
            marcas_disponibles = bool(bulk_ctx.get('logs', {}).get(empleado_id))
        else:
            raw_tmp = await db.fetch_one(
                "SELECT id FROM logs_raw WHERE empleado_id = ? AND fecha_hora LIKE ? LIMIT 1",
                (empleado_id, f"{fecha}%")
            )
            marcas_disponibles = bool(raw_tmp)

        if f_primer_turno and fecha < f_primer_turno:
            if not marcas_disponibles:
                if not save:
                    return None
                # Si estamos procesando individualmente, nos aseguramos de borrarlo
                asist_actual_del = await self.repository.get_asistencia(empleado_id, fecha)
                if asist_actual_del:
                    logger.info(f"🧹 Limpiando registro residual antes de primera asignación: Emp {empleado_id} en {fecha}")
                    await self.repository.delete_asistencia(empleado_id, fecha)
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

        # ── PARADIGMA DE CONSUMO (STATE MACHINE) ──────────────────────────────
        if marcas_consumidas_session is None:
            marcas_consumidas_session = {}
        if empleado_id not in marcas_consumidas_session:
            marcas_consumidas_session[empleado_id] = set()
        consumidas_emp = marcas_consumidas_session[empleado_id]

        # Siembra (DT-10): Utilizar marcas_consumidas_ids en lugar de heurística de timestamps
        if not consumidas_emp and asist_ayer:
            marcas_ayer_json = asist_ayer.get('marcas_consumidas_ids')
            if marcas_ayer_json and marcas_ayer_json != '[]':
                try:
                    import json
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

        # Filtrar marcas disponibles (no consumidas)
        marcas_disponibles = [log for log in raw_logs if log.get('id') not in consumidas_emp]
        marcas_disponibles.sort(key=lambda x: x['fecha_hora'])

        # ── AUTO-FIX GENERALIZADO: Normalización Cronológica Par por Desbalance ──
        # Si el número de marcas del día es par y existe desbalance entre E y S, alternar cronológicamente
        marcas_hoy = [m for m in marcas_disponibles if m.get('fecha_hora', '')[:10] == fecha]
        if marcas_hoy and len(marcas_hoy) % 2 == 0 and len(marcas_hoy) >= 2:
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

        # ── EXTRACCIÓN CRONOLÓGICA (Solo DINAMICO_FLEXIBLE) ─────────────────
        tipo_prog = None
        if asignacion:
            tipo_prog = asignacion.get('tipo_programacion')
            
        block_inteligente = []
        if tipo_prog == 'DINAMICO_FLEXIBLE':
            # [DT-1] Algoritmo de balance: Consumir todas las marcas del día calendario actual.
            # Si al finalizar el día el balance es > 0 (Ej: turno nocturno), seguir consumiendo
            # hasta que el balance llegue a 0 o se exceda el límite de 20 horas.
            _TIPOS_E = {'entrada', 'entry', 'e', 'in', '1'}
            _TIPOS_S = {'salida', 'exit', 's', 'out', '2'}

            ancla = next(
                (l for l in marcas_disponibles if l.get('fecha_hora', '')[:10] == fecha),
                None
            )

            if ancla:
                # Determine if the current day's shift can cross midnight
                puede_cruzar = False
                if asignacion:
                    tid = asignacion.get('turno_id') or asignacion['id']
                    if bulk_ctx:
                        turnos_dict = bulk_ctx.get('turnos', {}).get(tid, {})
                        for sem, sem_dict in turnos_dict.items():
                            cfg = sem_dict.get(dia_semana)
                            if cfg and (cfg.get('cruza_medianoche') or cfg.get('cruza_medianoche_2')):
                                puede_cruzar = True
                                break
                    else:
                        rows = await db.fetch_all(
                            "SELECT cruza_medianoche, cruza_medianoche_2 FROM turno_dias WHERE turno_id = ? AND dia_semana = ?",
                            (tid, dia_semana)
                        )
                        for r in rows:
                            if r['cruza_medianoche'] or r['cruza_medianoche_2']:
                                puede_cruzar = True
                                break

                if not puede_cruzar:
                    marcas_disponibles = [l for l in marcas_disponibles if l.get('fecha_hora', '').startswith(fecha)]

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
                    max_dt = first_log_dt + timedelta(hours=20)
                    
                    ultimo_idx = -1
                    
                    # 1. Consumir todo el día calendario
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
                        else:
                            break
                            
                    # 2. Si balance > 0 y puede cruzar medianoche, seguir hasta cerrarlo (turno nocturno)
                    if puede_cruzar and balance > 0 and ultimo_idx != -1:
                        for i in range(ultimo_idx + 1, len(marcas_disponibles)):
                            l = marcas_disponibles[i]
                            l_dt = datetime.strptime(l['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                            if l_dt > max_dt:
                                break
                                
                            block_inteligente.append(l)
                            consumidas_emp.add(l.get('id'))
                            
                            t = str(l.get('tipo', '') or '').strip().lower()
                            if t in _TIPOS_E:
                                balance += 1
                            elif t in _TIPOS_S:
                                balance -= 1
                                
                            if balance <= 0:
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
                        first_log_dt = datetime.strptime(block_inteligente[0]['fecha_hora'], "%Y-%m-%d %H:%M:%S")
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
                                semana_ganadora = last_matched_sem
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
                            'redondeo_minutos', 'es_turno_cortado', 'meta_horas_semanales',
                            'tipo_programacion', 'nombre',
                            'ventana_en_curso_minutos', 'tolerancia_exceso_colacion_minutos',
                            'rotacion_secuencial', 'semana_fallback_sin_marcas'
                        ):
                            if campo in padre:
                                config_dia[campo] = padre[campo]
        # ── SELECCIÓN DE OPCIÓN PARA DINAMICO_FLEXIBLE ───────────────────────
        if config_dia:
            config_dia = dict(config_dia)  # Copia para no mutar el origen del bulk_ctx
            if tipo_prog == 'DINAMICO_FLEXIBLE' and config_dia.get('hora_entrada_2') and config_dia.get('hora_salida_2') and block_inteligente:
                first_log_dt = datetime.strptime(block_inteligente[0]['fecha_hora'], "%Y-%m-%d %H:%M:%S")
                ent_str_1 = config_dia.get('hora_entrada')
                ent_str_2 = config_dia.get('hora_entrada_2')
                
                if ent_str_1 and ent_str_2:
                    t_in_dt_1 = datetime.strptime(f"{first_log_dt.strftime('%Y-%m-%d')} {ent_str_1}:00", "%Y-%m-%d %H:%M:%S")
                    t_in_dt_2 = datetime.strptime(f"{first_log_dt.strftime('%Y-%m-%d')} {ent_str_2}:00", "%Y-%m-%d %H:%M:%S")
                    
                    diff_1 = abs((first_log_dt - t_in_dt_1).total_seconds())
                    diff_2 = abs((first_log_dt - t_in_dt_2).total_seconds())
                    
                    diff_1 = min(diff_1, 86400 - diff_1)
                    diff_2 = min(diff_2, 86400 - diff_2)
                    
                    if diff_2 < diff_1:
                        config_dia['hora_entrada'] = config_dia['hora_entrada_2']
                        config_dia['hora_salida'] = config_dia['hora_salida_2']
                        if 'cruza_medianoche_2' in config_dia:
                            config_dia['cruza_medianoche'] = config_dia['cruza_medianoche_2']

        # ── EXTRACCIÓN DE PROPIEDADES BASE ────────────────────────────────────
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
                # Turno diurno/tarde: truncar salida a las 21:00
                salida_str = str(config_dia.get('hora_salida', '00:00'))[:5]
                if salida_str > '21:00':
                    # config_dia = dict(config_dia)  # copia para no mutar el origen del bulk_ctx (ya copiado)
                    config_dia['hora_salida'] = '21:00'
                    if config_dia.get('hora_entrada'):
                        t_ent = datetime.strptime(str(config_dia['hora_entrada'])[:5], "%H:%M")
                        t_sal = datetime.strptime('21:00', "%H:%M")
                        minutos_trabajo = (t_sal - t_ent).seconds / 60
                        if config_dia.get('descuento_colacion_auto'):
                            minutos_trabajo -= float(config_dia.get('minutos_colacion_auto', 0))
                        config_dia['horas_teoricas'] = max(0.0, minutos_trabajo / 60.0)

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

        dia_restringido = es_libre_config or is_holiday

        # ── LOGS PARA ESTE DÍA ────────────────────────────────────────────────
        is_bolsa = tipo_prog == 'FLEXIBLE_BOLSA'
        
        if tipo_prog == 'DINAMICO_FLEXIBLE':
            logs = block_inteligente
        elif is_bolsa:
            # Bolsa Flexible Inteligente: empareja Entradas con Salidas sin importar el día, pero respetando cruce_medianoche dinámico
            puede_cruzar = False
            if asignacion:
                tid = asignacion.get('turno_id') or asignacion['id']
                if bulk_ctx:
                    turnos_dict = bulk_ctx.get('turnos', {}).get(tid, {})
                    for sem, sem_dict in turnos_dict.items():
                        cfg = sem_dict.get(dia_semana)
                        if cfg and (cfg.get('cruza_medianoche') or cfg.get('cruza_medianoche_2')):
                            puede_cruzar = True
                            break
                else:
                    rows = await db.fetch_all(
                        "SELECT cruza_medianoche, cruza_medianoche_2 FROM turno_dias WHERE turno_id = ? AND dia_semana = ?",
                        (tid, dia_semana)
                    )
                    for r in rows:
                        if r['cruza_medianoche'] or r['cruza_medianoche_2']:
                            puede_cruzar = True
                            break

            if not puede_cruzar:
                marcas_disponibles = [l for l in marcas_disponibles if l.get('fecha_hora', '').startswith(fecha)]

            marcas_hoy = [l for l in marcas_disponibles if l.get('fecha_hora', '').startswith(fecha)]
            logs = []
            if marcas_hoy:
                idx_inicio = marcas_disponibles.index(marcas_hoy[0])
                balance = 0
                ultimo_idx = -1
                
                # Consumir marcas de este día calendario
                for i in range(idx_inicio, len(marcas_disponibles)):
                    log = marcas_disponibles[i]
                    if log.get('fecha_hora', '').startswith(fecha):
                        logs.append(log)
                        ultimo_idx = i
                        t_m = str(log.get('tipo', '') or '').strip().lower()
                        if t_m in {'entrada', 'entry', 'e', 'in', '1'}:  # [DT-16b] '' removido — D8
                            balance += 1
                        elif t_m in {'salida', 'exit', 's', 'out', '2'}:
                            balance -= 1
                    else:
                        break
                        
                # Si quedó una Entrada sin Salida, seguir consumiendo hasta cerrar el bloque (límite dinámico de calendario)
                if balance > 0 and ultimo_idx != -1 and logs:
                    fecha_limite = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
                    for i in range(ultimo_idx + 1, len(marcas_disponibles)):
                        log = marcas_disponibles[i]
                        log_fecha = log['fecha_hora'][:10]
                        
                        # Restricción 1: No cruzar más allá del día D+1
                        if log_fecha > fecha_limite:
                            break
                            
                        t_m = str(log.get('tipo', '') or '').strip().lower()
                        # Restricción 2: Si es el día siguiente y es una Entrada, detenerse (comienza una nueva jornada)
                        if log_fecha == fecha_limite and t_m in {'entrada', 'entry', 'e', 'in', '1'}:
                            break
                            
                        logs.append(log)
                        if t_m in {'entrada', 'entry', 'e', 'in', '1'}:
                            balance += 1
                        elif t_m in {'salida', 'exit', 's', 'out', '2'}:
                            balance -= 1

                        if balance <= 0:
                            break
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
                # Turnos diurnos: SOLO marcas del día calendario actual
                # Evita que un día sin marcas adyacentes robe marcas de días adyacentes
                logs = [l for l in marcas_disponibles if l.get('fecha_hora', '').startswith(fecha)]

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
        
        # FASE 2 (Fix B1): Sourcing de last_state desde horas_extras con fallback a legacy
        he_previo = None
        if bulk_ctx and 'horas_extras' in bulk_ctx:
            he_previo = bulk_ctx['horas_extras'].get(empleado_id)
        if he_previo is None:
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
            resultado = self._calculate_attendance(
                emp_id=empleado_id,
                fecha=fecha,
                turno=asignacion or {},
                config_dia=config_dia,
                logs=logs,
                justificaciones=justificaciones,
                bonos_asignados=bonos_asignados,
                is_holiday=is_holiday,
                is_weekend=is_weekend,
                last_state=last_state,
                esta_en_ruta=esta_en_ruta,
            )

        if resultado is None:
            if save and asist_actual:
                logger.info(f"🧹 Limpiando registro residual por recalculo: Emp {empleado_id} en {fecha}")
                await self.repository.delete_asistencia(empleado_id, fecha)
            return None

        # ── INTERCEPTOR: DÍA COMPENSATORIO (Intercambio de Días 1x1) ───────────
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
                    consumidas_emp.add(m_auth_previo)

            import json
            resultado['marcas_consumidas_ids'] = json.dumps(ids_consumidos)

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
            
            # Solo si hay HE bruto mantenemos la decisión. Si cayó a 0, se resetea.
            if nuevo_bruto > 0:
                resultado['_he_estado'] = _pres_estado
                if _pres_estado == 'APROBADO':
                    resultado['_he_minutos_autorizados'] = min(_pres_auth, nuevo_bruto)
                    # Restaurar estado EXTRA si era jornada especial aprobada
                    if asist_actual and asist_actual.get('estado') == 'EXTRA':
                        resultado['estado'] = 'EXTRA'
                else:
                    resultado['_he_minutos_autorizados'] = 0
                
                resultado['observaciones'] = (resultado.get('observaciones') or '') + f"Preservando decisión humana previa (Estado HE: {_pres_estado}) para {fecha}. "
            else:
                resultado['_he_estado'] = None
                resultado['_he_minutos_autorizados'] = 0

        # ── INTERCEPTAR JORNADAS ESPECIALES ───────────────────────────────────
        if save and resultado and resultado.get('estado') in ('JORNADA_ESPECIAL', 'EXTRA'):
            ht = resultado.get('horas_teoricas')
            ht_val = float(ht) if ht is not None else 0.0
            
            es_candidato = False
            
            if ht_val == 0.0:
                # Feriado o Día Libre
                es_candidato = True
            elif ht_val > 0.0 and resultado.get('estado') == 'EXTRA' and ('Cambio de turno irregular' in (resultado.get('observaciones') or '') or 'Turno de seguridad' in (resultado.get('observaciones') or '')):
                # Desfase total o casos manuales movidos a EXTRA pero que operan como especial
                es_candidato = True
            elif ht_val > 0.0 and resultado.get('estado') == 'JORNADA_ESPECIAL':
                # Anomalia forzada a jornada especial
                es_candidato = True
                
            if es_candidato:
                min_trab = int(resultado.get('horas_trabajadas', 0) * 60) if 'horas_trabajadas' in resultado and resultado['horas_trabajadas'] > 0 else resultado.get('minutos_extra_bruto', 0)
                
                # Fetch existing to check for manual validation
                je_prev = await self.repository.db.fetch_one(
                    "SELECT estado, observaciones FROM jornadas_especiales WHERE empleado_id = ? AND fecha = ?",
                    (empleado_id, fecha)
                )
                
                estado_je = resultado.get('estado')
                obs_je = resultado.get('observaciones') or ''
                
                if je_prev and ('[VALIDADO]' in (je_prev['observaciones'] or '') or '[RECHAZADO]' in (je_prev['observaciones'] or '')):
                    estado_je = je_prev['estado']
                    if estado_je == 'PENDIENTE':
                        estado_je = 'JORNADA_ESPECIAL'
                    # Keep original validation observation
                    obs_je = je_prev['observaciones']
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
                await self.repository.upsert_jornada_especial(j_record)
                
                # NOTA ARQUITECTURA: Ya no borramos los datos de "resultado" (hora_entrada_real, etc)
                # para que "asistencias" se mantenga como la FUENTE DE VERDAD con el registro JORNADA_ESPECIAL completo.

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

        # ── ESCRITURA LEGACY (Paso E): asistencias (DESPUÉS de horas_extras) ──
        if save:
            await self.repository.upsert_asistencia(resultado)

        return resultado

    # ─────────────────────────────────────────────────────────────────────────
    # _CALCULATE_ATTENDANCE — EL MOTOR REAL
    # ─────────────────────────────────────────────────────────────────────────

    def _calculate_attendance(
        self,
        emp_id: int,
        fecha: str,
        turno: Dict,
        config_dia: Optional[Dict],
        logs: List[Dict],
        justificaciones: List[Dict],
        bonos_asignados: List[Dict],
        is_holiday: bool,
        is_weekend: bool,
        last_state: Optional[str] = None,
        esta_en_ruta: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Implementa la lógica de redondeo y cálculo.

        REGLAS FUNDAMENTALES:
          - Las marcas se consumen en orden cronológico estricto (ya filtradas por consumidas_emp).
          - NO se usan ventanas temporales para encontrar marcas.
          - El tipo BioAlba (Entrada/Salida) manda.
          - El anclaje (entrada/salida) solo afecta el CÁLCULO de horas pagadas,
            nunca la búsqueda o consumo de marcas.
          - Una marca consumida no vuelve a usarse jamás.
        """
        dt = datetime.strptime(fecha, "%Y-%m-%d")

        # ── ESTRUCTURA BASE DEL RESULTADO ────────────────────────────────────
        res = {
            'empleado_id': emp_id,
            'fecha': fecha,
            'turno_asignado_id': turno.get('id'),
            'hora_entrada_teorica': None,
            'hora_salida_teorica': None,
            'horas_teoricas': None,
            'hora_entrada_real': None,
            'hora_salida_real': None,
            'minutos_atraso': 0,
            'minutos_colacion': 0,
            'minutos_colacion_real': 0,
            'horas_trabajadas': 0.0,
            'minutos_deuda': 0,
            'minutos_extra_bruto': 0,
            'minutos_salida_adelantada': 0,
            'estado': None,
            'observaciones': '',
        }

        # ── BONOS ─────────────────────────────────────────────────────────────
        if bonos_asignados:
            nombres_bonos = ', '.join(b.get('bono_nombre', '') for b in bonos_asignados)
            res['observaciones'] += f"Bonos: {nombres_bonos}. "

        # ── JUSTIFICACIONES ───────────────────────────────────────────────────
        should_apply_just = False
        justificacion_dia = None
        justificaciones_dia = [
            j for j in (justificaciones or [])
            if j.get('fecha_inicio', '') <= fecha <= j.get('fecha_fin', '')
        ]

        if justificaciones_dia:
            justificacion_dia = justificaciones_dia[0]
            should_apply_just = True

        # Licencias corridas (dias_corridos)
        licencia_corrida = None
        for j in (justificaciones or []):
            if j.get('dias_corridos') and j.get('fecha_inicio', '') <= fecha <= j.get('fecha_fin', ''):
                licencia_corrida = j
                break

        # ── FERIADO ────────────────────────────────────────────────────────────
        if is_holiday:
            res['estado'] = 'FERIADO'
            res['observaciones'] = 'Feriado Nacional (Proyección automática)'
            # Si hay marcas en feriado → JORNADA_ESPECIAL (tratado más abajo)
            if not logs:
                return res

        # ── JUSTIFICACIÓN (licencia, vacaciones, etc.) ─────────────────────────
        if should_apply_just and justificacion_dia:
            j = justificacion_dia
            # ── FILTRO DÍAS HÁBILES: Si no es corrido, respetar días libres del turno ──
            es_dia_libre_turno = bool(config_dia and config_dia.get('es_libre'))
            if not j.get('dias_corridos') and es_dia_libre_turno:
                should_apply_just = False
                # No aplicar justificación en día libre → flujo normal lo marcará LIBRE
            else:
                tipo_nombre = j.get('tipo_nombre', 'Sin detalle').upper()
                # Mapeo dinámico: el estado es el nombre de la justificación
                res['estado'] = tipo_nombre
                res['justificacion_id'] = j.get('id')
                if j.get('tipo_nomenclatura'):
                    res['nomenclatura'] = j.get('tipo_nomenclatura').upper()
                
                con_goce = j.get('con_goce_sueldo', True)
                genera_deuda = j.get('genera_deuda_horaria', False)
                obs = tipo_nombre
                if not con_goce:
                    obs += ' (Sin Goce)'
                else:
                    obs += ' (Con Goce de Sueldo)'
                if genera_deuda and config_dia:
                    minutos_teoricos = int((config_dia.get('horas_teoricas', 0) or 0) * 60)
                    obs += f' [GENERA DEUDA]'
                    res['minutos_deuda'] = minutos_teoricos
                    res['minutos_permiso_personal_deuda'] = minutos_teoricos
                res['observaciones'] = obs
                if not logs:
                    return res

        # ── SIN TURNO ASIGNADO ─────────────────────────────────────────────────
        if not config_dia and not asignacion_valida(turno):
            if logs:
                h_entrada = logs[0]['fecha_hora'][11:16] if logs else None

                res['hora_entrada_real'] = h_entrada
                res['estado'] = 'ANOMALIA'
                res['observaciones'] = 'TRABAJO SIN TURNO ASIGNADO. '
                return res
            # Sin turno y sin marcas: no hay nada que registrar
            if not is_holiday and not is_weekend:
                return None
            return None

        # ── CONFIG DÍA ────────────────────────────────────────────────────────
        redondeo = int(config_dia.get('redondeo_minutos', 0) or 0) if config_dia else 0
        anclaje_min     = int((config_dia or {}).get('anclaje_entrada_minutos') or
                              turno.get('anclaje_entrada_minutos', 0) or 0) if turno else 0  # [DT-12]
        anclaje_sal_min = int((config_dia or {}).get('anclaje_salida_minutos') or
                              turno.get('anclaje_salida_minutos', 0) or 0) if turno else 0   # [DT-12]
        h_ent_teorica = None
        h_sal_teorica = None

        # Si es día libre (es_libre=True), NO usar motor nocturno aunque cruza_medianoche=1
        # Un día libre no debe capturar marcas del día siguiente
        es_libre_dia = bool(config_dia and config_dia.get('es_libre'))
        es_nocturno = bool(config_dia and config_dia.get('cruza_medianoche') and not es_libre_dia)

        if config_dia:
            if config_dia.get('hora_entrada'):
                h_ent_teorica = datetime.strptime(f"{fecha} {config_dia['hora_entrada']}", "%Y-%m-%d %H:%M")
                res['hora_entrada_teorica'] = config_dia['hora_entrada']
            if config_dia.get('hora_salida'):
                h_sal_teorica = datetime.strptime(f"{fecha} {config_dia['hora_salida']}", "%Y-%m-%d %H:%M")
                res['hora_salida_teorica'] = config_dia['hora_salida']
                if es_nocturno and h_sal_teorica and h_ent_teorica and h_sal_teorica < h_ent_teorica:
                    h_sal_teorica += timedelta(days=1)
            if config_dia.get('horas_teoricas'):
                res['horas_teoricas'] = float(config_dia['horas_teoricas'])

        # ── TIPOS BIOALBA ──────────────────────────────────────────────────────
        TIPOS_ENTRADA = {'entrada', 'entry', 'e', 'in', '1'}
        TIPOS_SALIDA  = {'salida', 'exit', 's', 'out', '2'}

        def tipo_mark(log):
            return str(log.get('tipo', '') or '').strip().lower()

        def _procesar_pares_intermedios(salidas_int, entradas_int):
            pares = []
            for s_int, e_int in zip(salidas_int, entradas_int):
                if e_int > s_int:
                    pares.append((s_int, e_int, (e_int - s_int).total_seconds() / 60))
            if not pares:
                return

            min_auto = int(config_dia.get('minutos_colacion_auto', 0) or 0) if config_dia else 0
            min_normal = int(config_dia.get('minutos_colacion', 0) or 0) if config_dia else 0
            target_col = min_auto if min_auto > 0 else min_normal

            mejor_par = None
            if len(pares) == 1:
                mejor_par = pares[0]
            elif target_col > 0:
                menor_diff = float('inf')
                for p in pares:
                    diff = abs(p[2] - target_col)
                    if diff < menor_diff:
                        menor_diff = diff
                        mejor_par = p
            else:
                mejor_par = max(pares, key=lambda x: x[2])

            minutos_permisos = 0
            if mejor_par:
                res['minutos_colacion_real'] = int(round(mejor_par[2]))
                res['hora_salida_colacion'] = mejor_par[0].strftime("%H:%M:%S")
                res['hora_entrada_colacion'] = mejor_par[1].strftime("%H:%M:%S")

            permisos_puros = []
            for p in pares:
                if p != mejor_par:
                    minutos_permisos += p[2]
                    permisos_puros.append(p)

            if minutos_permisos > 0:
                res['minutos_permisos_detectados'] = int(minutos_permisos)
                res['minutos_permiso_personal_deuda'] = res.get('minutos_permiso_personal_deuda', 0) + int(minutos_permisos)
                res['observaciones'] += f"Permiso detectado en reloj ({int(minutos_permisos)} min). "
                res['hora_inicio_permiso'] = permisos_puros[0][0].strftime("%H:%M:%S")
                res['hora_termino_permiso'] = permisos_puros[-1][1].strftime("%H:%M:%S")

        # Clasificar logs disponibles
        logs_sorted = sorted(logs, key=lambda l: l.get('fecha_hora', ''))

        entrada_real = None
        salida_real  = None
        tiempos_proc = []

        # ── INASISTENCIA / LIBRE / FERIADO (sin marcas) ─────────────────────
        if not logs_sorted:
            if is_holiday:
                return res  # FERIADO ya seteado arriba
            if es_libre_dia:
                res['estado'] = 'LIBRE'
                return res
            # BOLSA FLEXIBLE: si ya pasó la hora_limite_ficticia → INASISTENCIA
            # Si aún no pasó → celda vacía (None), se evaluará más tarde.
            # Nota: is_bolsa se calcula aquí directamente porque la variable del scope
            # externo no está disponible dentro de _calculate_attendance aún.
            _es_bolsa_aqui = turno.get('tipo_programacion') == 'FLEXIBLE_BOLSA' if turno else False
            if _es_bolsa_aqui:
                hora_limite_ficticia = turno.get('hora_limite_ficticia') if turno else None
                if hora_limite_ficticia and fecha == datetime.now().strftime("%Y-%m-%d"):
                    try:
                        limite_dt = datetime.strptime(f"{fecha} {hora_limite_ficticia}", "%Y-%m-%d %H:%M")
                        if datetime.now() < limite_dt:
                            return None  # Aún no llegó la hora límite, celda vacía
                    except Exception as e:
                        logger.error(f"Error parseando hora_limite_ficticia '{hora_limite_ficticia}' para fecha {fecha}: {e}")
                        res['observaciones'] = f"{res.get('observaciones', '')} ⚠️ [ALERTA SISTEMA: Error parsing hora límite]".strip()
                elif fecha > datetime.now().strftime("%Y-%m-%d"):
                    return None  # Fecha futura, celda vacía
                res['estado'] = 'INASISTENCIA'
                res['observaciones'] = 'Inasistencia detectada (Bolsa Flexible sin marcas)'
                logger.info(
                    f"📋 INASISTENCIA: emp={emp_id} fecha={fecha} "
                    f"logs_count={len(logs)} "
                    f"turno={turno.get('nombre') if turno else 'N/A'} "
                    f"tipo_prog={turno.get('tipo_programacion') if turno else 'N/A'}"
                )
                return res
            if config_dia:
                # Determinar la hora de entrada teórica más tardía de entre las alternativas para evitar inasistencias prematuras:
                horas_entrada_candidatas = []
                if config_dia.get('hora_entrada'):
                    horas_entrada_candidatas.append(config_dia.get('hora_entrada'))
                if config_dia.get('hora_entrada_2'):
                    horas_entrada_candidatas.append(config_dia.get('hora_entrada_2'))

                if horas_entrada_candidatas:
                    entrada_mas_tardio_str = max(horas_entrada_candidatas)
                    if len(entrada_mas_tardio_str) > 5:
                        entrada_mas_tardio_str = entrada_mas_tardio_str[:5]
                    try:
                        limite_dt = datetime.strptime(f"{fecha} {entrada_mas_tardio_str}", "%Y-%m-%d %H:%M")
                        hora_limite_alerta = limite_dt + timedelta(minutes=int(turno.get('anclaje_entrada_minutos', 0) or 0))
                        
                        if datetime.now() < hora_limite_alerta:
                            return None
                    except Exception as e:
                        logger.error(f"Error parseando hora_entrada límite '{entrada_mas_tardio_str}': {e}")
                        if h_ent_teorica:
                            hora_limite_alerta = h_ent_teorica + timedelta(minutes=int(turno.get('anclaje_entrada_minutos', 0) or 0))
                            if datetime.now() < hora_limite_alerta:
                                return None
                elif h_ent_teorica:
                    hora_limite_alerta = h_ent_teorica + timedelta(minutes=int(turno.get('anclaje_entrada_minutos', 0) or 0))
                    if datetime.now() < hora_limite_alerta:
                        return None

                res['estado'] = 'INASISTENCIA'
                res['observaciones'] = 'Inasistencia detectada (Día hábil sin marcas)'
                logger.info(
                    f"📋 INASISTENCIA: emp={emp_id} fecha={fecha} "
                    f"logs_count={len(logs)} "
                    f"turno={turno.get('nombre') if turno else 'N/A'} "
                    f"config_dia={'hábil' if config_dia else 'MISSING'}"
                )
                return res
            return None

        # ── TURNO NOCTURNO ────────────────────────────────────────────────────
        if es_nocturno and h_ent_teorica and h_sal_teorica:
            # CONSUMO PURO: usar todos los logs disponibles en orden cronológico.
            # Confiar en el tipo BioAlba. Sin ventanas.
            entradas = [(datetime.strptime(l['fecha_hora'], "%Y-%m-%d %H:%M:%S"), l)
                        for l in logs_sorted if tipo_mark(l) in TIPOS_ENTRADA]
            salidas  = [(datetime.strptime(l['fecha_hora'], "%Y-%m-%d %H:%M:%S"), l)
                        for l in logs_sorted if tipo_mark(l) in TIPOS_SALIDA]

            dt_entrada = None
            dt_salida_fin = None
            entrada_inferida = False

            if entradas:
                dt_entrada = entradas[0][0]

                # ── FALLBACK POSICIONAL: tipos invertidos (nocturno) ──────────
                primera_salida_noc = salidas[0][0] if salidas else None
                if primera_salida_noc and dt_entrada > primera_salida_noc:
                    todos_noc2 = sorted(
                        [(datetime.strptime(l['fecha_hora'], "%Y-%m-%d %H:%M:%S"), l)
                         for l in logs_sorted],
                        key=lambda x: x[0]
                    )
                    if len(todos_noc2) >= 2:
                        dt_entrada    = todos_noc2[0][0]
                        dt_salida_fin = todos_noc2[-1][0]
                        entrada_real  = dt_entrada.strftime("%H:%M:%S")
                        salida_real   = dt_salida_fin.strftime("%H:%M:%S")
                        res['observaciones'] += "[Auto-Fix] Tipos invertidos - posicion cronologica. "
                        if len(todos_noc2) >= 4:
                            sal_int = [t[0] for t in todos_noc2[1:-1:2]]
                            ent_int = [t[0] for t in todos_noc2[2:-1:2]]
                            _procesar_pares_intermedios(sal_int, ent_int)
                        dt_entrada_calculo = dt_entrada
                        tiempos_proc = [
                            self._apply_rounding(dt_entrada_calculo, redondeo),
                            self._apply_rounding(dt_salida_fin, redondeo)
                        ]
                        dt_entrada = None  # evita re-entrar al bloque if dt_entrada is not None
                else:
                    # flujo normal nocturno
                    salidas_post = [(dt_s, l) for dt_s, l in salidas if dt_s > dt_entrada]
                    if salidas_post:
                        dt_salida_fin = salidas_post[-1][0]
                    elif len(entradas) > 1:
                        dt_salida_fin = entradas[-1][0]
                        entradas = entradas[:-1]
                        res['observaciones'] = res.get('observaciones', '') + "[Auto-Fix] Ultima marca tratada como Salida. "
                    else:
                        dt_salida_fin = None

                    # COLACION Y PERMISOS (marcas intermedias nocturno)
                    if len(salidas_post) >= 2 and len(entradas) >= 2:
                        salidas_intermedias = [s[0] for s in salidas_post[:-1]]
                        entradas_intermedias = [e[0] for e in entradas[1:]]
                        _procesar_pares_intermedios(salidas_intermedias, entradas_intermedias)

            elif salidas:
                # Sin entradas tipificadas: fallback posicional si hay >= 2 marcas.
                # Cubre el caso de "error de dedo" (marco Salida como primera marca).
                todos_noc = sorted(
                    [(datetime.strptime(l['fecha_hora'], "%Y-%m-%d %H:%M:%S"), l)
                     for l in logs_sorted],
                    key=lambda x: x[0]
                )
                if len(todos_noc) >= 2:
                    dt_entrada    = todos_noc[0][0]
                    dt_salida_fin = todos_noc[-1][0]
                    entrada_real  = dt_entrada.strftime("%H:%M:%S")
                    salida_real   = dt_salida_fin.strftime("%H:%M:%S")
                    res['observaciones'] += "[Auto-Fix] Tipos invertidos - posicion cronologica. "
                    # Extraer intermedias para colacion
                    if len(todos_noc) >= 4:
                        sal_int = [t[0] for t in todos_noc[1:-1:2]]
                        ent_int = [t[0] for t in todos_noc[2:-1:2]]
                        _procesar_pares_intermedios(sal_int, ent_int)
                    dt_entrada_calculo = dt_entrada
                    tiempos_proc = [
                        self._apply_rounding(dt_entrada_calculo, redondeo),
                        self._apply_rounding(dt_salida_fin, redondeo)
                    ]
                else:
                    # Solo 1 marca: borde frio (entrada antes del sync)
                    dt_salida_fin = salidas[0][0]


            if dt_entrada is not None:
                # ── ANCLAJE DE ENTRADA ────────────────────────────────────────
                # Solo afecta el CÁLCULO de horas pagadas (tiempos_proc).
                # La hora visible en grilla (entrada_real) siempre es la marca física.
                # Regla: si la anticipación está DENTRO del anclaje configurado
                # → no se paga la espera, el cálculo inicia desde h_ent_teorica.
                # Si la anticipación supera el anclaje → se paga desde la hora real.
                if (not entrada_inferida
                        and dt_entrada < h_ent_teorica
                        and dt_salida_fin is not None
                        and dt_salida_fin > h_ent_teorica):
                    anticipacion_min = (h_ent_teorica - dt_entrada).total_seconds() / 60
                    if anticipacion_min <= anclaje_min:
                        dt_entrada_calculo = h_ent_teorica
                        res['observaciones'] += (
                            f"Llegada anticipada {dt_entrada.strftime('%H:%M')} "
                            f"(dentro del anclaje, pago desde {h_ent_teorica.strftime('%H:%M')}). "
                        )
                    else:
                        dt_entrada_calculo = dt_entrada
                        res['observaciones'] += (
                            f"Llegada anticipada {dt_entrada.strftime('%H:%M')} "
                            f"({int(anticipacion_min)} min, fuera del anclaje de {anclaje_min} min). "
                        )
                else:
                    dt_entrada_calculo = dt_entrada

                entrada_real = dt_entrada.strftime("%H:%M:%S")
                salida_real  = dt_salida_fin.strftime("%H:%M:%S") if dt_salida_fin else None

                tiempos_proc = [self._apply_rounding(dt_entrada_calculo, redondeo)]
                if dt_salida_fin:
                    tiempos_proc.append(self._apply_rounding(dt_salida_fin, redondeo))

                logger.debug(
                    f"[NOCTURNO] Emp {emp_id} {fecha}: "
                    f"Entrada={entrada_real}{'(inf)' if entrada_inferida else ''} "
                    f"Salida={salida_real}"
                )
            elif dt_salida_fin is not None:
                # Caso: Hay salida pero no hay entrada (ni siquiera inferida)
                entrada_real = None
                salida_real  = dt_salida_fin.strftime("%H:%M:%S")
                tiempos_proc = []
            else:
                # Sin marcas en absoluto para este turno nocturno
                entrada_real = None
                salida_real  = None
                tiempos_proc = []

        else:
            # ── TURNO DIURNO ──────────────────────────────────────────────────
            # Mismo principio: consumo estricto, confiar en tipos BioAlba.
            entradas = [(datetime.strptime(l['fecha_hora'], "%Y-%m-%d %H:%M:%S"), l)
                        for l in logs_sorted if tipo_mark(l) in TIPOS_ENTRADA]
            salidas  = [(datetime.strptime(l['fecha_hora'], "%Y-%m-%d %H:%M:%S"), l)
                        for l in logs_sorted if tipo_mark(l) in TIPOS_SALIDA]

            dt_entrada = None
            dt_salida_fin = None
            entrada_inferida = False

            if entradas:
                dt_entrada = entradas[0][0]

                # ── FALLBACK POSICIONAL: tipos invertidos ──────────────────────
                # Si la primera entrada es POSTERIOR a la primera salida, significa
                # que el empleado marco Salida al llegar (error de dedo).
                # En ese caso ignoramos los tipos y usamos posicion cronologica:
                # primera marca = entrada, ultima marca = salida.
                primera_salida = salidas[0][0] if salidas else None
                if primera_salida and dt_entrada > primera_salida:
                    todos_diu = sorted(
                        [(datetime.strptime(l['fecha_hora'], "%Y-%m-%d %H:%M:%S"), l)
                         for l in logs_sorted],
                        key=lambda x: x[0]
                    )
                    if len(todos_diu) >= 2:
                        dt_entrada    = todos_diu[0][0]
                        dt_salida_fin = todos_diu[-1][0]
                        entrada_real  = dt_entrada.strftime("%H:%M:%S")
                        salida_real   = dt_salida_fin.strftime("%H:%M:%S")
                        res['observaciones'] += "[Auto-Fix] Tipos invertidos - posicion cronologica. "
                        if len(todos_diu) >= 4:
                            sal_int = [t[0] for t in todos_diu[1:-1:2]]
                            ent_int = [t[0] for t in todos_diu[2:-1:2]]
                            _procesar_pares_intermedios(sal_int, ent_int)
                        dt_entrada_calculo = dt_entrada
                        tiempos_proc = [
                            self._apply_rounding(dt_entrada_calculo, redondeo),
                            self._apply_rounding(dt_salida_fin, redondeo)
                        ]
                        # Saltar el procesamiento normal (ya esta listo)
                        dt_entrada = None  # evita re-entrar al bloque if dt_entrada is not None
                else:
                    # ── FLUJO NORMAL ──────────────────────────────────────────
                    # ULTIMA salida despues de la entrada
                    salidas_post = [(dt_s, l) for dt_s, l in salidas if dt_s > dt_entrada]
                    if salidas_post:
                        dt_salida_fin = salidas_post[-1][0]
                    elif len(entradas) > 1:
                        dt_salida_fin = entradas[-1][0]
                        entradas = entradas[:-1]
                        res['observaciones'] = res.get('observaciones', '') + "[Auto-Fix] Ultima marca tratada como Salida. "
                    else:
                        dt_salida_fin = None

                    # ── COLACION Y PERMISOS REALES (marcas intermedias diurno) ────
                    if len(salidas_post) >= 2 and len(entradas) >= 2:
                        salidas_intermedias = [s[0] for s in salidas_post[:-1]]
                        entradas_intermedias = [e[0] for e in entradas[1:]]
                        _procesar_pares_intermedios(salidas_intermedias, entradas_intermedias)
            elif salidas:
                # Sin entradas tipificadas: fallback posicional si hay >= 2 marcas.
                # Cubre el caso de "error de dedo" (marco Salida como primera marca).
                todos_diu = sorted(
                    [(datetime.strptime(l['fecha_hora'], "%Y-%m-%d %H:%M:%S"), l)
                     for l in logs_sorted],
                    key=lambda x: x[0]
                )
                if len(todos_diu) >= 2:
                    dt_entrada    = todos_diu[0][0]
                    dt_salida_fin = todos_diu[-1][0]
                    entrada_real  = dt_entrada.strftime("%H:%M:%S")
                    salida_real   = dt_salida_fin.strftime("%H:%M:%S")
                    res['observaciones'] += "[Auto-Fix] Tipos invertidos - posicion cronologica. "
                    # Extraer intermedias para colacion
                    if len(todos_diu) >= 4:
                        sal_int = [t[0] for t in todos_diu[1:-1:2]]
                        ent_int = [t[0] for t in todos_diu[2:-1:2]]
                        _procesar_pares_intermedios(sal_int, ent_int)
                    dt_entrada_calculo = dt_entrada
                    tiempos_proc = [
                        self._apply_rounding(dt_entrada_calculo, redondeo),
                        self._apply_rounding(dt_salida_fin, redondeo)
                    ]
                else:
                    # Solo 1 marca: borde frio
                    dt_salida_fin = salidas[0][0]


            if dt_entrada is not None:
                # Anclaje entrada diurno: mismo principio que nocturno.
                # Dentro del anclaje → pago desde h_ent_teorica.
                # Fuera del anclaje → pago desde la hora real.
                if (not entrada_inferida
                        and h_ent_teorica
                        and dt_entrada < h_ent_teorica
                        and dt_salida_fin is not None
                        and (not h_sal_teorica or dt_salida_fin > h_ent_teorica)):
                    anticipacion_min = (h_ent_teorica - dt_entrada).total_seconds() / 60
                    if anticipacion_min <= anclaje_min:
                        dt_entrada_calculo = h_ent_teorica
                        res['observaciones'] += (
                            f"Llegada anticipada {dt_entrada.strftime('%H:%M')} "
                            f"(dentro del anclaje, pago desde {h_ent_teorica.strftime('%H:%M')}). "
                        )
                    else:
                        dt_entrada_calculo = dt_entrada
                        res['observaciones'] += (
                            f"Llegada anticipada {dt_entrada.strftime('%H:%M')} "
                            f"({int(anticipacion_min)} min, fuera del anclaje de {anclaje_min} min). "
                        )
                else:
                    dt_entrada_calculo = dt_entrada

                entrada_real = dt_entrada.strftime("%H:%M:%S")
                salida_real  = dt_salida_fin.strftime("%H:%M:%S") if dt_salida_fin else None

                tiempos_proc = [self._apply_rounding(dt_entrada_calculo, redondeo)]
                if dt_salida_fin:
                    tiempos_proc.append(self._apply_rounding(dt_salida_fin, redondeo))
            elif dt_salida_fin is not None:
                entrada_real = None
                salida_real  = dt_salida_fin.strftime("%H:%M:%S")
                tiempos_proc = []

        # ── ANCLAJE DE SALIDA ─────────────────────────────────────────────────
        # Si el empleado salió DENTRO del margen post-turno configurado (anclaje_sal_min),
        # se ancla a h_sal_teorica para no contar esos minutos extras como trabajados.
        # Si salió mucho después (overtime real) o antes (adelantada), se respeta la marca.
        if anclaje_sal_min > 0 and h_sal_teorica and len(tiempos_proc) >= 2:
            dt_salida_real = tiempos_proc[-1]
            diff_salida = (dt_salida_real - h_sal_teorica).total_seconds() / 60
            if 0 < diff_salida <= anclaje_sal_min:
                tiempos_proc[-1] = h_sal_teorica
                res['observaciones'] += f"Salida dentro del anclaje ({int(diff_salida)} min post-turno, pagado hasta {h_sal_teorica.strftime('%H:%M')}). "

        # ── ACTUALIZAR RESULTADO CON ENTRADA/SALIDA ───────────────────────────
        res['hora_entrada_real'] = entrada_real
        res['hora_salida_real']  = salida_real



        # ── SIN ENTRADA → estados especiales ──────────────────────────────────
        if not entrada_real:
            if config_dia:
                if es_libre_dia or is_holiday:
                    res['estado'] = 'ANOMALIA'
                    res['observaciones'] = 'Solo una marcación (falta entrada en día libre/feriado).'
                    return res
                    
                if h_ent_teorica:
                    hora_limite_alerta = h_ent_teorica + timedelta(minutes=int(turno.get('anclaje_entrada_minutos', 0) or 0))
                    if datetime.now() < hora_limite_alerta:
                        return None
                
                if salida_real:
                    res['estado'] = 'ANOMALIA'
                    res['observaciones'] = 'Solo una marcación (falta entrada).'
                else:
                    res['estado'] = 'INASISTENCIA'
                    res['observaciones'] = 'Inasistencia detectada (Día hábil sin marcas)'
                    logger.info(
                        f"📋 INASISTENCIA: emp={emp_id} fecha={fecha} "
                        f"logs_count={len(logs)} "
                        f"turno={turno.get('nombre') if turno else 'N/A'} "
                        f"config_dia={'hábil' if config_dia else 'MISSING'}"
                    )
            else:
                if salida_real:
                    res['estado'] = 'ANOMALIA'
                    res['observaciones'] = 'Solo una marcación (falta entrada en día libre/no configurado).'
            return res

        # ── EN CURSO (sin salida aún, día de hoy o trasnoche) ─────────────────
        if not salida_real:
            fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
            hoy_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            es_hoy = (fecha_dt >= hoy_dt)
            
            # Determinar si aún está "en curso" (Automatizado: 3 horas de gracia tras la salida teórica)
            en_curso_por_hora = False
            if h_sal_teorica:
                # h_sal_teorica ya tiene +1 día aplicado si cruza medianoche
                limite_ventana = h_sal_teorica + timedelta(hours=3)
                if datetime.now() < limite_ventana:
                    en_curso_por_hora = True
            else:
                # Fallback si no hay salida teórica (ej. Bolsa Flexible)
                if es_hoy:
                    en_curso_por_hora = True

            if en_curso_por_hora:
                res['estado'] = 'EN_CURSO'
                res['observaciones'] += 'Jornada en curso (falta salida).'
                return res

            # Si no es hoy y ya pasó el límite de en curso
            if es_libre_dia or is_holiday:
                res['estado'] = 'ANOMALIA'
                res['observaciones'] += 'Solo una marcación (falta salida en día libre/feriado). '
                return res

            # Sin salida y ya pasó el tiempo → ANOMALIA para día normal
            res['estado'] = 'ANOMALIA'
            res['observaciones'] += 'Solo una marcación (falta salida).'
            return res

        # ── CÁLCULO DE HORAS ───────────────────────────────────────────────────
        if len(tiempos_proc) >= 2:
            r_ent = tiempos_proc[0]
            r_sal = tiempos_proc[-1]
            horas_trabajadas = (r_sal - r_ent).total_seconds() / 3600.0

            minutos_colacion = 0
            colacion_flag = config_dia.get('descuento_colacion_auto') if config_dia else None
            minutos_colacion_permitidos = int(config_dia.get('minutos_colacion_auto', 0) or 0) if config_dia else 0
            umbral_horas = float(config_dia.get('umbral_horas_colacion', 0.0) or 0.0) if config_dia else 0.0
            res['minutos_colacion_auto'] = minutos_colacion_permitidos

            # Si hay marcas intermedias (colación real), usamos ese tiempo.
            # DT-3: El tiempo real medido es la fuente de verdad (sin MAX)
            if res.get('minutos_colacion_real', 0) > 0:
                # Si la colación real es inferior a la programada y descuento_colacion_auto está habilitado,
                # descontamos la programada (piso) para no generar horas extras indebidas.
                if config_dia and int(colacion_flag or 0):
                    minutos_colacion = max(res['minutos_colacion_real'], minutos_colacion_permitidos)
                else:
                    minutos_colacion = res['minutos_colacion_real']
            else:
                # Si no hay marcas intermedias, aplicamos el descuento automático si está configurado
                if config_dia and int(colacion_flag or 0):
                    if umbral_horas > 0 and horas_trabajadas < umbral_horas:
                        logger.info(f"Omite colación auto: Horas trabajadas ({horas_trabajadas:.2f}) < Umbral ({umbral_horas:.2f})")
                        minutos_colacion = 0
                    else:
                        minutos_colacion = minutos_colacion_permitidos
                        if minutos_colacion > 0:
                            mitad_jornada = r_ent + (r_sal - r_ent) / 2
                            inicio_colacion_auto = mitad_jornada - timedelta(minutes=minutos_colacion / 2)
                            fin_colacion_auto = mitad_jornada + timedelta(minutes=minutos_colacion / 2)
                            res['hora_salida_colacion'] = inicio_colacion_auto.strftime("%H:%M:%S")
                            res['hora_entrada_colacion'] = fin_colacion_auto.strftime("%H:%M:%S")

            res['minutos_exceso_colacion'] = max(0, minutos_colacion - minutos_colacion_permitidos)
            
            # Descontar colación y permisos detectados por biometría
            minutos_permisos = res.get('minutos_permisos_detectados', 0)
            horas_trabajadas -= (minutos_colacion + minutos_permisos) / 60.0
            
            res['minutos_colacion'] = minutos_colacion
            res['horas_trabajadas'] = round(max(horas_trabajadas, 0), 4)
        else:
            horas_trabajadas = 0.0
            res['horas_trabajadas'] = 0.0
            res['minutos_exceso_colacion'] = 0

        # ── TIPO DE DÍA (diurno / nocturno / bolsa) ────────────────────────────
        is_bolsa = turno.get('tipo_programacion') == 'FLEXIBLE_BOLSA'

        # ── CÁLCULO DE DIFERENCIAS (atraso, salida adelantada, extras) ────────
        diff_ent = 0  # minutos de atraso (positivo = tarde)
        diff_sal = 0  # minutos de salida adelantada (positivo = se fue antes)

        if h_ent_teorica and len(tiempos_proc) > 0:
            diff_ent = (tiempos_proc[0] - h_ent_teorica).total_seconds() / 60

        if h_sal_teorica and len(tiempos_proc) >= 2:
            diff_sal = (h_sal_teorica - tiempos_proc[-1]).total_seconds() / 60



        tolerancia_retraso = int(turno.get('tolerancia_retraso_descuento', 0) or 0) if turno else 0
        tolerancia_alerta = int(turno.get('tolerancia_retraso_alerta', 0) or 0) if turno else 0

        # Horas extra brutas y Deuda de tiempo total (Lógica Financiera Pura - Modelo Doble Eje)
        ht = config_dia.get('horas_teoricas') if config_dia else None
        horas_teoricas = float(ht) if ht is not None else 0.0  # [DT-11] 8.0 → 0.0: D6 nunca asume horas teóricas
        min_teoricos = float(horas_teoricas * 60)
        
        # Si es feriado o libre, NO exigimos horas teóricas
        if is_holiday or es_libre_dia:
            min_teoricos = 0.0
            res['horas_teoricas'] = 0.0
            
        min_trabajados = float(horas_trabajadas * 60)
        
        # En el modelo de doble eje, las extras son estrictamente el excedente de las horas teóricas
        if is_bolsa:
            minutos_extra_bruto = 0.0
        else:
            minutos_extra_bruto = max(0, min_trabajados - min_teoricos)
        res['minutos_extra_bruto'] = minutos_extra_bruto
        

        # Usar valor exacto (sin truncar a minutos enteros) para precisión matemática y trazabilidad perfecta
        diff_ent_exacto = diff_ent if diff_ent > 0 else 0.0
        diff_sal_exacto = diff_sal if diff_sal > 0 else 0.0

        if diff_ent_exacto > tolerancia_retraso:
            # Atraso como incidencia disciplinaria (no se borra si compensó con extras)
            res['minutos_atraso'] = diff_ent_exacto
        elif diff_ent_exacto > tolerancia_alerta:
            # DT-2: Alerta visual de retraso sin incidencia disciplinaria
            res['alerta_atraso'] = True

        if diff_sal_exacto > 0:
            res['minutos_salida_adelantada'] = diff_sal_exacto

        # ── PERMISOS POR HORA ──────────────────────────────────────────────────
        permisos_hora = [j for j in (justificaciones or []) if j.get('tiene_permiso_hora')]
        minutos_permiso_deuda = 0
        if permisos_hora:
            for p in permisos_hora:
                if p.get('permiso_activo'):
                    res['observaciones'] += f" [PERMISO ACTIVO: {p.get('tipo_nombre', '')}]"
                    h_ini_j = p.get('hora_inicio')
                    h_fin_j = p.get('hora_fin')
                    if h_ini_j and h_fin_j:
                        try:
                            ini_dt = datetime.strptime(f"{fecha} {h_ini_j}", "%Y-%m-%d %H:%M")
                            fin_dt = datetime.strptime(f"{fecha} {h_fin_j}", "%Y-%m-%d %H:%M")
                            min_j = int((fin_dt - ini_dt).total_seconds() / 60)
                            if not p.get('genera_deuda_horaria', False):
                                minutos_permiso_deuda += min_j
                            else:
                                res['minutos_permiso_personal_deuda'] = res.get('minutos_permiso_personal_deuda', 0) + min_j
                        except Exception as e:
                            logger.error(f"Error procesando permiso para fecha {fecha}: {e}")
                            res['observaciones'] += f" ⚠️ [ALERTA SISTEMA: Error leyendo horas de permiso]"

        # Permisos abiertos (sin hora de fin — licencias en curso)
        permisos_abiertos = [j for j in (justificaciones or []) if not j.get('tiene_permiso_hora') and j.get('permiso_activo')]
        for p in permisos_abiertos:
            res['observaciones'] += f" [PERMISO ABIERTO: {p.get('tipo_nombre', '')}]"

        # ── SALDO META (Deuda / Extra) ─────────────────────────────────────────
        if is_bolsa:
            # En FLEXIBLE_BOLSA, la deuda diaria es 0, delegando el cálculo financiero al ciclo semanal/mensual
            # Además, se anulan las incidencias disciplinarias diarias (atrasos y salidas adelantadas)
            minutos_deuda = 0
            res['minutos_atraso'] = 0
            res['minutos_salida_adelantada'] = 0
            res['alerta_atraso'] = False
            hubo_sad_fisico = False
            diff_ent = 0
            diff_sal_exacto = 0
            if minutos_permiso_deuda > 0:
                res['observaciones'] += 'Saldo neutralizado por permiso. '
        elif is_holiday or es_libre_dia:
            # En días libres o feriados (Jornada Especial), la deuda horaria es siempre 0.
            minutos_deuda = 0
            res['minutos_atraso'] = 0
            res['minutos_salida_adelantada'] = 0
        else:
            # Para todos los demás turnos (Fijos, Rotativos), la deuda se basa en el volumen no cumplido (Doble Eje)
            minutos_deuda = max(0, min_teoricos - min_trabajados)
            if minutos_permiso_deuda > 0:
                minutos_deuda = max(0, minutos_deuda - minutos_permiso_deuda)

        res['minutos_deuda'] = minutos_deuda

        # ── DETERMINACIÓN DE ESTADO FINAL ─────────────────────────────────────
        minutos_reales_brutos = int(horas_trabajadas * 60)
        
        # [DT-15] Capturar SAD físico ANTES de la lógica financiera — D7 estricto (P1 aprobado)
        # hubo_sad_fisico = hubo marca de salida antes de la hora teórica
        # Este flag es independiente de si hay deuda o no. Eje Disciplinario != Eje Financiero.
        hubo_sad_fisico = res.get('minutos_salida_adelantada', 0) > 0

        # Una salida adelantada solo cambia el ESTADO (para efectos de deuda) si genera deuda diaria,
        # o si estamos en bolsa (donde la deuda diaria es 0 pero la salida física antes de hora es incidencia
        # a menos que supere la meta diaria)
        has_sad = False
        if hubo_sad_fisico:
            if is_bolsa:
                has_sad = True
            else:
                # [DT-15] NO borrar minutos_salida_adelantada cuando no hay deuda.
                # Los minutos se preservan para reportes del Eje Disciplinario.
                has_sad = minutos_deuda > 0

        has_permiso = res.get('minutos_permisos_detectados', 0) > 0 or res.get('minutos_permiso_personal_deuda', 0) > 0

        # ── Flags independientes (métricas separadas) ─────────────────────────
        # Cada flag puede ser True sin depender del otro.
        # Estadísticas: "cuántos llegaron tarde" = COUNT WHERE tiene_atraso=1
        #               "cuántos salieron antes"  = COUNT WHERE tiene_salida_adelantada=1
        res['tiene_atraso']             = 1 if diff_ent > tolerancia_retraso else 0
        # [DT-15] tiene_salida_adelantada usa hubo_sad_fisico (no has_sad) — D7 estricto
        # El flag es 1 si hubo SAD físico, independientemente de si hay deuda financiera.
        # Permite reportes como "cuántos empleados salieron antes" sin mezclar con deuda.
        res['tiene_salida_adelantada']  = 1 if hubo_sad_fisico else 0
        res['tiene_permiso']            = 1 if has_permiso else 0

        # ── Estado PRIMARIO del día (jerarquía de gravedad) ──────────────────
        # El estado es uno solo; los flags adicionales completan el cuadro.
        if has_permiso:
            res['estado'] = 'PERMISO'
        elif diff_ent > tolerancia_retraso:
            res['estado'] = 'ATRASO'
        elif has_sad:
            res['estado'] = 'SALIDA_ADELANTADA'
        elif is_holiday or es_libre_dia:
            if is_holiday:
                res['estado'] = 'JORNADA_ESPECIAL'
                res['observaciones'] += 'Trabajo en feriado. '
            else:
                res['estado'] = 'JORNADA_ESPECIAL'
                res['observaciones'] += 'Trabajo en día libre. '
        else:
            res['estado'] = 'OK'

        # Turno cortado (turno especial de horas reducidas)
        if config_dia and config_dia.get('es_turno_cortado'):
            if res['estado'] == 'OK':
                h_real_proc = horas_trabajadas
                if h_real_proc < (horas_teoricas * 0.85):
                    res['estado'] = 'SALIDA_ADELANTADA'

        if minutos_deuda > 0 and res['estado'] == 'OK':
            res['observaciones'] += f"Deuda Acumulada: -{minutos_deuda} min. "

        # ── LÓGICA BOLSA FLEXIBLE: Suprimir deudas diarias ───────────────────
        if turno and turno.get('tipo_programacion') == 'FLEXIBLE_BOLSA':
            if res.get('estado') in ('ATRASO', 'SALIDA_ADELANTADA', 'ATR_SAD'):
                res['estado'] = 'OK'
            res['tiene_atraso'] = 0
            res['tiene_salida_adelantada'] = 0
            res['minutos_atraso'] = 0
            res['minutos_salida_adelantada'] = 0
            res['minutos_deuda'] = 0

        return res

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
        # Regla de negocio DOBLE:
        #   1. Sin turno asignado → no aparece en la grilla.
        #   2. Inactivo (activo=0) → no aparece en la grilla.
        q_emp = """
            SELECT DISTINCT e.*, ar.nombre as area
            FROM empleados e
            INNER JOIN asignacion_turnos ast ON e.id = ast.empleado_id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE e.activo = 1
              AND ast.fecha_inicio <= ? AND (ast.fecha_fin IS NULL OR ast.fecha_fin >= ?)
        """
        params_emp: list = [fecha_fin, fecha_inicio]
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

        # Definición de queries para carga masiva concurrente
        q_asist = f"""
            SELECT a.*, t.nombre as turno_nombre,
                   he.estado as estado_he,
                   he.minutos_autorizados as minutos_extra_autorizados,
                   COALESCE((SELECT SUM(minutos) FROM compensaciones_he_inasistencia WHERE empleado_id = a.empleado_id AND fecha_inasistencia = a.fecha), 0.0) as minutos_compensados_he
            FROM asistencias a
            LEFT JOIN turnos t ON a.turno_asignado_id = t.id
            LEFT JOIN horas_extras he ON he.empleado_id = a.empleado_id AND he.fecha = a.fecha
            WHERE a.empleado_id IN ({ids_ph}) AND a.fecha BETWEEN ? AND ?
            ORDER BY a.empleado_id, a.fecha
        """
        
        q_jornadas = f"""
            SELECT j.* 
            FROM jornadas_especiales j
            WHERE j.empleado_id IN ({ids_ph}) AND j.fecha BETWEEN ? AND ?
        """
        
        q_asig = f"""
            SELECT a.empleado_id, a.turno_id, t.meta_horas_semanales, t.tipo_programacion, t.nombre as turno_nombre
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
            asistencias = [a for a in asistencias if a.get('turno_asignado_id') == turno_id]

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
                emp['meta_horas_semanales'] = t_info.get('meta_horas_semanales') or 44.0
                emp['tipo_programacion'] = t_info.get('tipo_programacion') or 'DINAMICO_FLEXIBLE'
                emp['turno'] = t_info.get('turno_nombre')
                t_id = t_info.get('turno_id')
                emp['primer_dia_semana_turno'] = primer_dia_por_turno.get(t_id, 1)  # default Lunes
                emp['turno_dias'] = dias_por_turno.get(t_id, {})
            matrix[eid] = {'info': emp}


        for a in asistencias:
            eid = a['empleado_id']
            if eid in matrix:
                matrix[eid][a['fecha']] = a

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
                f_str = j['fecha']
                je_estado = j['estado']

                if f_str in matrix[eid]:
                    # Solo EXTRA/RECHAZADA cambian el estado visual
                    if je_estado in ESTADOS_JE_QUE_PISAN:
                        matrix[eid][f_str]['estado'] = je_estado
                    # Enriquecer horas reales SOLO si la JE las tiene definidas.
                    # Si JE.hora_entrada es None, la marca biométrica de asistencias
                    # se conserva — no se borra lo que el reloj registró.
                    if j['hora_entrada'] is not None:
                        matrix[eid][f_str]['hora_entrada_real'] = j['hora_entrada']
                    if j['hora_salida'] is not None:
                        matrix[eid][f_str]['hora_salida_real'] = j['hora_salida']
                    matrix[eid][f_str]['minutos_extra_bruto'] = 0
                    matrix[eid][f_str]['minutos_extra_autorizados'] = 0
                    matrix[eid][f_str]['minutos_deuda'] = 0
                    matrix[eid][f_str]['horas_trabajadas'] = (j['minutos_trabajados'] or 0) / 60.0
                    matrix[eid][f_str]['observaciones'] = j.get('observaciones') or ''
                    # Nota: no existe rama else (JE sin asistencias).
                    # El motor siempre crea ambos registros juntos. Si faltara asistencias
                    # sería un bug de integridad que debe investigarse, no silenciarse.


        # Proyectar feriados no procesados
        from datetime import datetime as _dt, timedelta as _td
        cur = _dt.strptime(fecha_inicio, "%Y-%m-%d")
        fin_dt = _dt.strptime(fecha_fin, "%Y-%m-%d")
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
            cur += _td(days=1)

        # Justificaciones del período (precargadas concurrentemente arriba)
        justificaciones = [dict(j) for j in just_rows]

        # Inyectar nomenclaturas en la matriz a partir de justificaciones
        for just in justificaciones:
            eid = just['empleado_id']
            if eid in matrix and just.get('tipo_nomenclatura'):
                try:
                    cur_dt = _dt.strptime(just['fecha_inicio'][:10], "%Y-%m-%d")
                    end_dt = _dt.strptime(just['fecha_fin'][:10], "%Y-%m-%d")
                    nomen = just['tipo_nomenclatura'].upper()
                    while cur_dt <= end_dt:
                        f_str = cur_dt.strftime("%Y-%m-%d")
                        if f_str in matrix[eid]:
                            # Asignar nomenclatura si el estado coincide con el nombre de la justificación
                            est = matrix[eid][f_str].get('estado')
                            if est and str(est).strip().upper() == str(just['tipo_nombre']).strip().upper():
                                matrix[eid][f_str]['nomenclatura'] = nomen
                                matrix[eid][f_str]['justificacion_id'] = just.get('id')
                        cur_dt += _td(days=1)
                except (ValueError, KeyError) as _exc:
                    logger.debug(f"[Matrix] Nomenclatura no inyectada para just_id={just.get('id')} emp={eid}: {_exc}")

        # Determinar si el periodo/rango actual está cerrado
        q_cierre = "SELECT COUNT(*) as count FROM cierres_periodos WHERE fecha_inicio <= ? AND fecha_fin >= ?"
        params_cierre = [fecha_fin, fecha_inicio]
        
        if area and area != 'Todas':
            q_cierre += " AND (area IS NULL OR area = ?)"
            params_cierre.append(area)
        
        if turno_id:
            q_cierre += " AND (turno_id IS NULL OR turno_id = ?)"
            params_cierre.append(turno_id)
            
        res_cierre = await db.fetch_one(q_cierre, tuple(params_cierre))
        periodo_cerrado = res_cierre['count'] > 0 if res_cierre else False

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
        try:
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
        except Exception as e_close_rrhh:
            logger.warning(f"⚠️ No se pudo actualizar el estado/vigencia en periodos_rrhh: {e_close_rrhh}")
        
        # 2. Recalcular las bolsas de todos los empleados afectados
        q_emp = "SELECT id FROM empleados WHERE activo = 1"
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
            WHERE e.activo = 1
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
            WHERE h.fecha BETWEEN ? AND ? AND e2.activo = 1 AND h.estado = 'APROBADO'
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
            WHERE c.fecha_inasistencia BETWEEN ? AND ? AND e3.activo = 1
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
            WHERE a.fecha BETWEEN ? AND ? AND e.activo = 1
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
