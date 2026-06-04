from datetime import datetime, date
from typing import List, Dict, Any, Optional
from backend.schemas.turno import TurnoCreate, TurnoResponse, AsignacionCreate, AsignacionBulk
from backend.repositories.turno import TurnoRepository
from backend.repositories.asistencia import AsistenciaRepository

class TurnoService:
    def __init__(self, repository: TurnoRepository):
        self.repository = repository
        
    async def initialize(self):
        """Inicializar tablas del módulo"""
        await self.repository.init_tables()

    async def create_turno(self, turno: TurnoCreate) -> int:
        return await self.repository.create_turno(turno)

    async def get_all_turnos(self, area: Optional[str] = None, include_details: bool = True, areas_permitidas: Optional[List[str]] = None, activo: Optional[bool] = None) -> List[Dict]:
        """
        Obtiene todos los turnos, opcionalmente filtrados por área y con detalles.
        """
        if area:
            # Como el router ya valida si area está en areas_permitidas, 
            # podemos heredar esa validación o simplemente filtrar por áreas
            return await self.repository.get_turnos_by_areas([area], include_details=include_details, activo=activo)
        elif areas_permitidas is not None:
            if not areas_permitidas:
                return []
            return await self.repository.get_turnos_by_areas(areas_permitidas, include_details=include_details, activo=activo)
        else:
            return await self.repository.get_all_turnos(include_details=include_details, activo=activo)

    async def get_stats_por_area(self) -> Dict[str, Any]:
        return await self.repository.get_stats_por_area()

    async def assign_turno(self, asignacion: AsignacionCreate) -> int:
        return await self.repository.create_asignacion(asignacion)

    async def delete_turno(self, turno_id: int) -> bool:
        return await self.repository.delete_turno(turno_id)

    async def update_turno(self, turno_id: int, turno: TurnoCreate) -> bool:
        return await self.repository.update_turno(turno_id, turno)

    async def assign_turno_bulk(self, bulk: AsignacionBulk) -> Dict:
        results = {"success": 0, "errors": 0, "details": []}
        for emp_id in bulk.empleados_ids:
            try:
                asignacion = AsignacionCreate(
                    empleado_id=emp_id,
                    turno_id=bulk.turno_id,
                    fecha_inicio=bulk.fecha_inicio,
                    fecha_fin=bulk.fecha_fin,
                    reemplazar=bulk.reemplazar
                )
                await self.repository.create_asignacion(asignacion)
                results["success"] += 1
            except ValueError as ve:
                results["errors"] += 1
                results["details"].append(f"Emp {emp_id}: {str(ve)}")
            except Exception as e:
                results["errors"] += 1
                results["details"].append(f"Emp {emp_id}: Error interno - {str(e)}")
        return results

    async def get_assignment_matrix(self, month: int, year: int, area: Optional[str] = None) -> List[Dict]:
        """
        Resuelve la matriz de asignaciones para un periodo.
        """
        import calendar
        from datetime import date
        
        # 1. Configurar periodo
        num_days = calendar.monthrange(year, month)[1]
        start_period = date(year, month, 1).isoformat()
        end_period = date(year, month, num_days).isoformat()

        # 2. Obtener Empleados (Directo por SQL para evitar imports circulares/lento)
        query_emps = """
            SELECT e.id, e.nombre, e.apellido_paterno, e.apellido_materno, e.rut, ar.nombre as area, e.cargo, e.fecha_salida 
            FROM empleados e
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas ar ON ha.area_id = ar.id
            WHERE (
                -- Solo considerar empleados que estuvieron contratados en algún momento de este mes
                (e.fecha_salida IS NULL OR e.fecha_salida >= ?)
                AND (e.fecha_ingreso IS NULL OR e.fecha_ingreso <= ?)
                AND (
                    -- Caso A: Empleados actualmente activos
                    e.activo = 1
                    
                    -- Caso B: Inactivos pero que salieron recientemente (en este mes o después)
                    OR (e.activo = 0 AND e.fecha_salida >= ?)
                    
                    -- Caso C: Tienen actividad real confirmada en este mes (justificaciones)
                    OR EXISTS (
                        SELECT 1 FROM justificaciones j 
                        WHERE j.empleado_id = e.id 
                          AND j.fecha_inicio <= ? AND j.fecha_fin >= ?
                    )
                )
            )
        """
        params_emps = [
            start_period, # fecha_salida >= inicio mes
            end_period,   # fecha_ingreso <= fin mes
            start_period, # activo=0 pero salio este mes
            end_period, start_period # justificaciones
        ]
        if area:
            query_emps += " AND ar.nombre = ?"
            params_emps.append(area)
        
        # Orden estricto: Paterno -> Materno -> Nombre
        query_emps += " ORDER BY e.apellido_paterno ASC, e.apellido_materno ASC, e.nombre ASC"
        
        employees = await self.repository.db.fetch_all(query_emps, tuple(params_emps))
        if not employees:
            return []
        
        # 3. Obtener Asignaciones que solapan con el mes
        # ORDER BY fecha_inicio DESC garantiza que el loop tome PRIMERO la asignación
        # más reciente para cada fecha (cuando existan múltiples por soft-close histórico).
        query_assignments = """
            SELECT a.empleado_id, a.turno_id, a.fecha_inicio, a.fecha_fin, t.nombre as turno_nombre 
            FROM asignacion_turnos a
            JOIN turnos t ON a.turno_id = t.id
            WHERE (a.fecha_fin IS NULL OR a.fecha_fin >= ?)
            AND a.fecha_inicio <= ?
            ORDER BY a.fecha_inicio DESC
        """
        all_assignments = await self.repository.db.fetch_all(query_assignments, (start_period, end_period))
        
        # 3.1 Obtener todos los detalles de turnos involucrados para inyectar horarios
        unique_turno_ids = list(set(a['turno_id'] for a in all_assignments))
        turno_details = {}
        turno_weeks_count = {} # Para saber cuántas semanas tiene cada turno
        if unique_turno_ids:
            holders = ",".join(["?"] * len(unique_turno_ids))
            query_dias = f"SELECT * FROM turno_dias WHERE turno_id IN ({holders}) ORDER BY num_semana, dia_semana"
            dias_rows = await self.repository.db.fetch_all(query_dias, tuple(unique_turno_ids))
            for d_row in dias_rows:
                tid = d_row['turno_id']
                sem = d_row['num_semana']
                ds = d_row['dia_semana']
                if tid not in turno_details: turno_details[tid] = {}
                if sem not in turno_details[tid]: turno_details[tid][sem] = {}
                turno_details[tid][sem][ds] = d_row
                
                # Rastrear máximo de semanas por turno
                turno_weeks_count[tid] = max(turno_weeks_count.get(tid, 1), sem)

        # Indexar asignaciones por empleado para O(1) access
        emp_map = {}
        for a in all_assignments:
            eid = a['empleado_id']
            if eid not in emp_map: emp_map[eid] = []
            emp_map[eid].append(a)

        # 4. Construir Matriz
        result = []
        for emp in employees:
            eid = emp['id']
            row = {
                "id": eid,
                "nombre": f"{emp['apellido_paterno']} {emp['apellido_materno'] or ''} {emp['nombre']}".strip().replace('  ', ' '),
                "rut": emp['rut'],
                "area": emp['area'],
                "cargo": emp['cargo'],
                "dias": []
            }
            
            assignments = emp_map.get(eid, [])
            
            for d in range(1, num_days + 1):
                dt_obj = date(year, month, d)
                iso_date = dt_obj.isoformat()
                dia_sem = dt_obj.weekday() # 0=Lunes
                
                # --- NUEVO: Validar si el empleado ya se fue ---
                if emp['fecha_salida'] and iso_date > emp['fecha_salida']:
                    row["dias"].append({
                        "dia": d,
                        "date": iso_date,
                        "turno": None,
                        "observaciones": "Baja de personal"
                    })
                    continue

                active_turno = None
                for assign in assignments:
                    if assign['fecha_inicio'] <= iso_date and (not assign['fecha_fin'] or assign['fecha_fin'] >= iso_date):
                        tid = assign['turno_id']
                        # --- LÓGICA DE ROTACIÓN ---
                        from datetime import datetime
                        f_asig_ini = datetime.strptime(assign['fecha_inicio'], "%Y-%m-%d").date()
                        total_sems = turno_weeks_count.get(tid, 1)
                        
                        # Cálculo de semana activa: (dias_diff // 7) % total_semanas + 1
                        dias_diff = (dt_obj - f_asig_ini).days
                        num_sem_activa = (dias_diff // 7 % total_sems) + 1 if total_sems > 1 else 1
                        
                        # Obtener horario de este día y semana
                        horario_str = "SIN DEF"
                        t_conf = turno_details.get(tid, {}).get(num_sem_activa, {}).get(dia_sem)
                        
                        if t_conf:
                            if t_conf['es_libre']:
                                horario_str = "LIBRE"
                            else:
                                h1 = f"{t_conf['hora_entrada'] or '??'}-{t_conf['hora_salida'] or '??'}"
                                # Turno cortado?
                                if t_conf.get('hora_entrada_2'):
                                    h1 += f" / {t_conf['hora_entrada_2']}-{t_conf['hora_salida_2']}"
                                horario_str = h1
                        
                        active_turno = {
                            "id": tid,
                            "nombre": assign['turno_nombre'],
                            "horario": horario_str
                        }
                        break
                
                row["dias"].append({
                    "dia": d,
                    "date": iso_date,
                    "turno": active_turno
                })
            
            result.append(row)

        return result

    async def update_assignment_date(self, empleado_id: int, nueva_fecha_str: str | date):
        """
        Coordina la actualización de la fecha de inicio de un turno, 
        la limpieza de registros de asistencia basura y el reprocesamiento.
        """
        # 1. Parsear fecha
        if isinstance(nueva_fecha_str, date):
            nueva_fecha = nueva_fecha_str
            nueva_fecha_str = nueva_fecha.isoformat()
        else:
            try:
                nueva_fecha = datetime.strptime(nueva_fecha_str, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError("Formato de fecha inválido. Use YYYY-MM-DD")
            
        # 2. Actualizar fecha en el repositorio raíz
        success = await self.repository.update_assignment_start_date(empleado_id, nueva_fecha)
        if not success:
            raise ValueError("No se encontró una asignación de turno activa para este empleado")
            
        # 3. Limpieza quirúrgica de asistencias previas
        # (Para borrar las inasistencias 'fantasma' generadas por error en el pasado)
        asis_repo = AsistenciaRepository(self.repository.db)
        deleted_count = await asis_repo.delete_before_date(empleado_id, nueva_fecha)
        
        # 4. Gatillar Reprocesamiento 'Mágico'
        # Importación local para evitar circulares
        from backend.services.asistencia_service import AsistenciaService
        from datetime import timedelta
        
        asis_service = AsistenciaService(asis_repo)
        
        # Reprocesar día a día desde la nueva fecha hasta hoy 
        # (procesar_periodo masivo tiene firma distinta y límites de 31 días)
        hoy = datetime.now().date()
        curr = nueva_fecha
        processed_count = 0
        while curr <= hoy:
            await asis_service.procesar_empleado_dia(empleado_id, curr.isoformat(), save=True, force=True)
            curr += timedelta(days=1)
            processed_count += 1

        return {
            "status": "success",
            "message": f"Fecha actualizada a {nueva_fecha_str}. Se eliminaron {deleted_count} registros previos y se reprocesaron {processed_count} días.",
            "deleted_count": deleted_count,
            "processed_count": processed_count
        }
