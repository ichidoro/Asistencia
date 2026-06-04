"""
Service - Empleado
Lógica de negocio para gestión de empleados
"""

from typing import List, Optional, Any
from datetime import date, datetime

from fastapi import HTTPException, status
from loguru import logger

from backend.models.empleado import Empleado
from backend.repositories.empleado import EmpleadoRepository
from backend.schemas.empleado import EmpleadoCreate, EmpleadoUpdate, ReincorporarRequest
from backend.services.configuracion_service import ConfiguracionService
from backend.services.notification_service import NotificationService


class EmpleadoService:
    """
    Servicio para lógica de negocio de Empleados.
    Orquesta operaciones entre el Repository y los Controllers/Routers.
    """
    
    async def initialize(self) -> None:
        """Inicializar (crear tablas si es necesario)"""
        await self.repository.create_table()
    
    def __init__(self, repository: EmpleadoRepository, 
                 config_service: Optional[ConfiguracionService] = None,
                 notification_service: Optional[NotificationService] = None,
                 asis_service: Optional[Any] = None):
        self.repository = repository
        self.config_service = config_service
        self.notification_service = notification_service
        self.asis_service = asis_service
    
    async def resolve_catalogs(self, empleado: Empleado) -> None:
        """Resolver nombres de área, cargo y género a partir de sus IDs si no están especificados"""
        db = self.repository.db
        
        # Resolver área
        if empleado.area_id and not empleado.area:
            res_area = await db.fetch_one("SELECT nombre FROM areas WHERE id = ?", (empleado.area_id,))
            if res_area:
                empleado.area = res_area["nombre"]
                
        # Resolver cargo
        if empleado.cargo_id and not empleado.cargo:
            res_cargo = await db.fetch_one("SELECT nombre, excluido_asistencia FROM cargos WHERE id = ?", (empleado.cargo_id,))
            if res_cargo:
                empleado.cargo = res_cargo["nombre"]
                # Si el cargo está excluido por defecto de asistencia, asignar a excluido_asistencia (solo si es manual)
                if empleado.excluido_asistencia is None:
                    empleado.excluido_asistencia = bool(res_cargo["excluido_asistencia"]) if empleado.es_manual else False
                
        # Forzar excluido_asistencia = False para empleados sincronizados de BioAlba
        if not empleado.es_manual:
            empleado.excluido_asistencia = False

        # Resolver género
        if empleado.genero_id and not empleado.genero:
            res_gen = await db.fetch_one("SELECT nombre FROM cat_generos WHERE id = ?", (empleado.genero_id,))
            if res_gen:
                empleado.genero = res_gen["nombre"]

    async def create_empleado(self, empleado_data: EmpleadoCreate) -> Empleado:
        """
        Crear un nuevo empleado.
        
        Validaciones:
        - RUT no debe existir ya en la base de datos
        """
        # Verificar que el RUT no exista
        existing = await self.repository.get_by_rut(empleado_data.rut)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ya existe un empleado con RUT {empleado_data.rut}"
            )
        
        # Crear modelo desde schema
        empleado = Empleado(
            rut=empleado_data.rut,
            nombre=empleado_data.nombre,
            apellido_paterno=empleado_data.apellido_paterno,
            apellido_materno=empleado_data.apellido_materno,
            cargo=empleado_data.cargo,
            cargo_id=empleado_data.cargo_id,
            area_id=empleado_data.area_id,
            area=empleado_data.area,
            compania=empleado_data.compania,
            email=empleado_data.email,
            telefono=empleado_data.telefono,
            genero=empleado_data.genero,
            genero_id=getattr(empleado_data, 'genero_id', None),
            activo=empleado_data.activo,
            es_manual=getattr(empleado_data, 'es_manual', False) or False,
            excluido_asistencia=getattr(empleado_data, 'excluido_asistencia', None),
            fecha_ingreso=empleado_data.fecha_ingreso,
            fecha_salida=empleado_data.fecha_salida,
            fecha_nacimiento=empleado_data.fecha_nacimiento,
            tipo_contrato=empleado_data.tipo_contrato,
            cant_contratos=empleado_data.cant_contratos
        )
        
        # Resolver catálogos antes de guardar
        await self.resolve_catalogs(empleado)
        
        # Crear en DB
        empleado_created = await self.repository.create(empleado)
        
        # Registrar historial de áreas inicial al crear un empleado
        if empleado_created.area_id:
            fecha_desde = empleado_created.fecha_ingreso or date.today().isoformat()
            await self.repository.add_historial_area(
                empleado_id=empleado_created.id,
                area_id=empleado_created.area_id,
                fecha_desde=fecha_desde,
                es_actual=True,
                validado=True
            )
        
        # Trigger Recálculo de Asignaciones (solo si el empleado es activo)
        if self.config_service and empleado_created.activo:
            await self.config_service.recalculate_assignments(empleado_created)
            
        return empleado_created
    
    async def get_empleado(self, empleado_id: int) -> Empleado:
        """
        Obtener un empleado por ID.
        
        Raises:
            HTTPException 404 si no existe
        """
        empleado = await self.repository.get_by_id(empleado_id)
        
        if not empleado:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Empleado con ID {empleado_id} no encontrado"
            )
        
        return empleado
    
    async def get_by_rut(self, rut: str) -> Optional[Empleado]:
        """Obtener empleado por RUT (wrapper del repositorio)"""
        return await self.repository.get_by_rut(rut)

    async def get_distinct_areas(self) -> List[str]:
        """Obtener lista de áreas únicas registradas en el catálogo maestro"""
        try:
            db_areas = await self.repository.get_all_areas()
            return sorted(db_areas)
        except Exception as e:
            logger.error(f"Error obteniendo áreas: {e}")
            return []
    
    async def get_empleado_by_rut(self, rut: str) -> Empleado:
        """
        Obtener un empleado por RUT.
        
        Raises:
            HTTPException 404 si no existe
        """
        empleado = await self.repository.get_by_rut(rut)
        
        if not empleado:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Empleado con RUT {rut} no encontrado"
            )
        
        return empleado
    
    async def get_all_empleados(
        self,
        skip: int = 0,
        limit: int = 100,
        activo: Optional[bool] = None,
        areas_permitidas: Optional[List[str]] = None
    ) -> tuple[List[Empleado], int]:
        """
        Obtener todos los empleados con paginación y RLS.
        """
        empleados = await self.repository.get_all(skip, limit, activo, areas=areas_permitidas)
        total = await self.repository.count(activo, areas=areas_permitidas)
        
        return empleados, total
    
    async def get_expiring_contracts(self, days: Optional[int] = None, areas_permitidas: Optional[List[str]] = None) -> List[dict]:
        """
        Obtener empleados con contratos próximos a vencer con RLS.
        """
        # 1. Obtener ajustes
        dias_normal = days
        if dias_normal is None and self.config_service:
            dias_normal = int(await self.config_service.get_ajuste("vencimiento_dias_alerta", 45))
        elif dias_normal is None:
            dias_normal = 30
            
        dias_blocking = 5
        max_contratos = 2
        if self.config_service:
            dias_blocking = int(await self.config_service.get_ajuste("dias_alerta_bloqueante", 5))
            max_contratos = int(await self.config_service.get_ajuste("limite_contratos_temporales", 2))

        # 2. Consultar repositorio (Con limpieza proactiva de decisiones huérfanas)
        await self.repository.db.execute("UPDATE empleados SET decision_vencimiento = NULL WHERE decision_vencimiento IN ('RENOVAR', 'INDEFINIDO')")
        empleados = await self.repository.get_upcoming_expirations(dias_normal, areas=areas_permitidas)
        
        # 3. Marcar y retornar como dicts para el frontend
        from datetime import date, datetime
        today = date.today()
        
        results = []
        for emp in empleados:
            e_dict = emp.to_dict()
            
            # NUEVO: Marcar si ya tiene una decisión tomada
            e_dict["es_procesado"] = True if emp.decision_vencimiento else False
            e_dict["decision_actual"] = emp.decision_vencimiento
            
            e_dict["bloqueante"] = False
            e_dict["requiere_bloqueo"] = False
            e_dict["estado_vencimiento"] = "Normal" # Vencido, Critico, Alerta Legal, Próximo
            
            # Alerta 1: Límite de contratos (Bloqueo Legal)
            if emp.tipo_contrato == 'Temporal' and (emp.cant_contratos or 1) >= max_contratos:
                e_dict["bloqueante"] = True
                e_dict["estado_vencimiento"] = "Alerta Legal"
                # Por defecto, Alerta Legal NO es bloqueo mandatorio si no ha vencido
            
            # Alerta 2: Por fecha
            if emp.fecha_salida:
                try:
                    fecha_salida = datetime.strptime(emp.fecha_salida, "%Y-%m-%d").date()
                    diff = (fecha_salida - today).days
                    e_dict["dias_restantes"] = diff
                    
                    if diff < 0:
                        e_dict["bloqueante"] = True
                        e_dict["requiere_bloqueo"] = True
                        e_dict["estado_vencimiento"] = "VENCIDO"
                    elif diff <= dias_blocking:
                        e_dict["bloqueante"] = True
                        e_dict["requiere_bloqueo"] = True
                        e_dict["estado_vencimiento"] = "CRÍTICO"
                    elif diff <= dias_normal:
                        # Si no era Alerta Legal por cant_contratos, es Próximo
                        # Ahora MARCADO COMO BLOQUEANTE (Soft) para que aparezca en el modal
                        e_dict["bloqueante"] = True
                        if e_dict["estado_vencimiento"] == "Normal":
                            e_dict["estado_vencimiento"] = "PRÓXIMO"
                except (ValueError, TypeError) as _e:
                    logger.debug(f"[EmpleadoService] fecha_salida mal formateada para emp_id={emp.id}: {emp.fecha_salida!r} -> {_e}")
            
            # Si es temporal sin fecha
            elif emp.tipo_contrato == 'Temporal':
                 e_dict["bloqueante"] = False # No debe bloquear el uso de la aplicación
                 if e_dict["estado_vencimiento"] == "Normal":
                    e_dict["estado_vencimiento"] = "INFO. PENDIENTE"
            
            results.append(e_dict)
            
        return results
        
    async def get_terminated_by_month(self, month: int, year: int, areas_permitidas: Optional[List[str]] = None) -> List[dict]:
        """
        Obtener lista formateada de empleados finiquitados con RLS.
        """
        empleados = await self.repository.get_terminated_by_month(month, year, areas=areas_permitidas)
        
        from datetime import date, datetime
        today = date.today()
        
        results = []
        for emp in empleados:
            e_dict = emp.to_dict()
            
            # Determinar estado del término
            if emp.fecha_salida:
                try:
                    f_salida = datetime.strptime(emp.fecha_salida, "%Y-%m-%d").date()
                    if f_salida < today:
                        e_dict["estado_termino"] = "FINALIZADO"
                        e_dict["color_termino"] = "secondary" # Gris
                    else:
                        e_dict["estado_termino"] = "PROGRAMADO"
                        e_dict["color_termino"] = "primary" # Azul
                except:
                    e_dict["estado_termino"] = "ERROR FECHA"
            
            results.append(e_dict)
            
        return results

    async def get_birthdays(self, month: Optional[int] = None, area: Optional[str] = None, areas_permitidas: Optional[List[str]] = None) -> List[Empleado]:
        """Obtener cumpleaños"""
        return await self.repository.get_birthdays(month, area, areas_permitidas=areas_permitidas)

    async def search_empleados(
        self,
        q: Optional[str] = None,
        area: Optional[str] = None,
        compania: Optional[str] = None,
        activo: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "nombre",
        order: str = "asc",
        areas_permitidas: Optional[List[str]] = None
    ) -> tuple[List[Empleado], int]:
        """
        Buscar empleados con filtros, ordenamiento y Data Scoping.
        """
        empleados = await self.repository.search(
            q=q,
            area=area,
            compania=compania,
            activo=activo,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            order=order,
            areas_permitidas=areas_permitidas
        )
        
        # Obtener total real de coincidencias para paginación
        total = await self.repository.count_search(
            q=q,
            area=area,
            compania=compania,
            activo=activo,
            areas_permitidas=areas_permitidas
        )
        
        return empleados, total
    
    async def update_empleado(
        self,
        empleado_id: int,
        empleado_data: EmpleadoUpdate
    ) -> Empleado:
        """
        Actualizar un empleado.
        
        Solo actualiza los campos que vienen en el request (no None).
        """
        # Verificar que existe
        empleado = await self.get_empleado(empleado_id)
        old_fecha_salida = empleado.fecha_salida
        old_activo = empleado.activo
        old_area_id = empleado.area_id
        
        # Actualizar solo campos que vienen en el request
        update_data = empleado_data.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(empleado, field, value)
            
        # Resolver catálogos
        await self.resolve_catalogs(empleado)
        
        area_changed = False
        if empleado.area_id is not None and empleado.area_id != old_area_id:
            area_changed = True
        
        # Guardar en DB
        empleado_updated = await self.repository.update(empleado_id, empleado)
        
        if not empleado_updated:
            logger.error(f"❌ Falló actualización de empleado {empleado_id} (Repo retornó None)")
            return empleado # Retornamos el objeto en memoria aunque no se haya persistido para no romper el flujo
            
        if area_changed:
            historial = await self.repository.get_historial_areas(empleado_id)
            actual = next((h for h in historial if h.get("es_actual")), None)
            hoy = date.today().isoformat()
            from datetime import timedelta
            ayer = (date.today() - timedelta(days=1)).isoformat()
            if actual:
                await self.repository.update_historial_area(
                    actual["id"],
                    fecha_hasta=ayer,
                    es_actual=0
                )
            await self.repository.add_historial_area(
                empleado_id=empleado_id,
                area_id=empleado_updated.area_id,
                fecha_desde=hoy,
                es_actual=True,
                validado=True
            )
            
        # 1. Auto-ajuste de turnos si la fecha de salida cambió (Extensión o Acortamiento)
        if empleado_updated.fecha_salida != old_fecha_salida:
            await self._adjust_shift_assignments(empleado_id, old_fecha_salida, empleado_updated.fecha_salida)
        
        # 2. Auto-limpieza de asistencias proyectadas si aplicó fecha_salida o se desactivó
        if empleado_updated.fecha_salida:
            await self._clean_ghost_data(empleado_id, empleado_updated.fecha_salida)
        elif not empleado_updated.activo:
            # Si no hay fecha_salida pero se desactivó, usar hoy como fecha de corte
            from datetime import date
            await self._clean_ghost_data(empleado_id, date.today().isoformat())
        
        # Trigger Recálculo de Asignaciones (solo empleados activos)
        bonos_asignados: list = []
        if self.config_service and empleado_updated.activo:
            bonos_asignados = await self.config_service.recalculate_assignments(empleado_updated)
        # Adjuntar al objeto retornado como atributo transitorio (no persiste en DB)
        empleado_updated._bonos_asignados = bonos_asignados
            
        # [AUTO-HEALING] Solo para empleados activos con cambios críticos en el contrato
        if self.asis_service and empleado_updated.activo and (empleado_updated.fecha_salida != old_fecha_salida or empleado_updated.activo != old_activo):
            from datetime import date
            hoy = date.today().strftime("%Y-%m-%d")
            # Si se extendió o activó, reprocesamos desde el mes pasado hasta fin de mes actual para cubrir gaps
            fecha_inicio = old_fecha_salida or empleado_updated.fecha_ingreso or hoy
            if fecha_inicio > hoy: fecha_inicio = hoy
            
            logger.info(f"🔄 Cambio de contrato/estado detectado para {empleado_id}. Gatillando Auto-Healing en background.")
            import asyncio
            asyncio.create_task(
                self.asis_service.reprocesar_periodo_empleado(
                    empleado_id=empleado_id,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=hoy,
                    force=True
                )
            )

        return empleado_updated

    
    async def delete_empleado(self, empleado_id: int, hard: bool = False) -> bool:
        """
        Eliminar un empleado.
        
        Args:
            empleado_id: ID del empleado
            hard: Si True, elimina permanentemente. Si False, soft delete (marca como inactivo)
        """
        # Verificar que existe
        await self.get_empleado(empleado_id)
        
        if hard:
            return await self.repository.hard_delete(empleado_id)
        else:
            # Capturar empleado para tener su fecha_salida antes de la baja (si existiera)
            emp = await self.get_empleado(empleado_id)
            fecha_corte = emp.fecha_salida or date.today().isoformat()
            
            result = await self.repository.delete(empleado_id)
            if result:
                await self._clean_ghost_data(empleado_id, fecha_corte)
            return result
    
    async def activate_empleado(self, empleado_id: int) -> Empleado:
        """Reactivar un empleado inactivo"""
        empleado = await self.get_empleado(empleado_id)
        empleado.activo = True
        
        return await self.repository.update(empleado_id, empleado)
    
    async def get_stats(self, areas_permitidas: Optional[List[str]] = None) -> dict:
        """Obtener estadísticas de empleados con RLS"""
        total = await self.repository.count(areas=areas_permitidas)
        activos = await self.repository.count(activo=True, areas=areas_permitidas)
        inactivos = await self.repository.count(activo=False, areas=areas_permitidas)
        areas = await self.repository.get_stats_by_area(areas=areas_permitidas)
        
        return {
            "total": total,
            "activos": activos,
            "inactivos": inactivos,
            "areas": areas
        }

    async def get_metadata(self, areas_permitidas: Optional[List[str]] = None) -> dict:
        """Obtener metadatos únicos con RLS"""
        return await self.repository.get_unique_metadata(areas=areas_permitidas)

    async def get_lookup(self, area: Optional[str] = None, activo: Optional[bool] = None, areas_permitidas: Optional[List[str]] = None) -> List[dict]:
        """Obtener lista mínima de empleados para dropdowns"""
        return await self.repository.get_lookup(area, activo, areas_permitidas)


    async def get_empleados_matrix(
        self,
        q: Optional[str] = None,
        area: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        areas_permitidas: Optional[List[str]] = None
    ) -> dict:
        """
        Obtener matriz de empleados y sus bonos asignados.
        Retorna estructura optimizada para tabla dinámica con Data Scoping.
        """
        logger.info(f"get_empleados_matrix called with: q={q}, area={area}, skip={skip}, limit={limit}")
        
        # 1. Obtener empleados (reutilizando search)
        empleados, total = await self.search_empleados(
            q=q, area=area, skip=skip, limit=limit, activo=True, areas_permitidas=areas_permitidas
        )

        # 2. Obtener bonos activos
        if not self.config_service:
            # Fallback si no está inyectado (no debería pasar en el endpoint main)
            return {"columns": [], "data": [], "total": 0}

        all_bonos = await self.config_service.repository.get_all_bonos()
        # Filtrar solo activos y ordenar
        active_bonos = [b for b in all_bonos if b['activo']]
        active_bonos.sort(key=lambda x: x['id'])
        
        columns = [{"id": b['id'], "nombre": b['nombre']} for b in active_bonos]
        
        # 3. Construir data (Batch Optimization)
        from datetime import date
        today = date.today().isoformat()
        
        # Obtener asignaciones masivas
        emp_ids = [e.id for e in empleados]
        asignaciones_flat = await self.config_service.repository.get_active_asignaciones_batch(emp_ids, today)
        
        # Agrupar asignaciones por empleado_id
        map_asignaciones = {eid: set() for eid in emp_ids}
        for asig in asignaciones_flat:
            map_asignaciones[asig['empleado_id']].add(asig['bono_id'])

        data = []
        for emp in empleados:
            row = {
                "id": emp.id,
                "nombre_completo": f"{emp.apellido_paterno} {emp.apellido_materno or ''} {emp.nombre}".strip(),
                "rut": emp.rut,
                "cargo": emp.cargo or "Sin Cargo",
                "area": emp.area or "Sin Area",
                "tipo_contrato": emp.tipo_contrato or "Sin Contrato", # [NEW] Requested by User
                "asignaciones": {
                    str(b['id']): (b['id'] in map_asignaciones[emp.id]) for b in active_bonos
                }
            }
            data.append(row)
            
        return {
            "columns": columns,
            "data": data,
            "total": total
        }
    async def procesar_vencimiento(self, empleado_id: int, accion: str, nueva_fecha: Optional[str] = None) -> Empleado:
        """
        Procesar el vencimiento de un contrato.
        Acciones: 'renovar', 'desactivar', 'indefinido'
        """
        empleado = await self.get_empleado(empleado_id)
        old_fecha_salida = empleado.fecha_salida
        
        if accion == "renovar":
            if not nueva_fecha:
                raise HTTPException(status_code=400, detail="Se requiere nueva fecha para renovar")
            empleado.cant_contratos += 1
            empleado.fecha_salida = nueva_fecha
            # Al renovar, la decisión se marca temporalmente pero debe limpiarse para el nuevo periodo de evaluación
            # No queremos que aparezca como "Procesado" en el nuevo contrato hasta que venza de nuevo
            empleado.decision_vencimiento = None 
            logger.info(f"Contrato renovado para {empleado.nombre_completo}. Nuevo N°: {empleado.cant_contratos}. Estado decisión reseteado.")
            
            # Sincronizar tabla legal
            await self.repository.db.execute(
                "UPDATE periodos_empleo SET fecha_fin = ? WHERE empleado_id = ? AND es_activo = 1",
                (nueva_fecha, empleado_id)
            )
        
        elif accion == "desactivar":
            from datetime import date, datetime
            try:
                fecha_venc = datetime.strptime(empleado.fecha_salida, "%Y-%m-%d").date() if empleado.fecha_salida else date.today()
                
                if fecha_venc <= date.today():
                    # Si ya venció o vence hoy, desactivar de inmediato
                    empleado.activo = False
                    empleado.decision_vencimiento = "NO_RENOVAR"
                    logger.info(f"Empleado desactivado inmediatamente por vencimiento: {empleado.nombre_completo}")
                else:
                    # Si es futuro, programar baja (mantener activo)
                    empleado.activo = True
                    empleado.decision_vencimiento = "NO_RENOVAR"
                    logger.info(f"Baja programada para {empleado.nombre_completo} el {empleado.fecha_salida}")
            except Exception as e:
                # Si hay error en fecha, desactivar por seguridad
                empleado.activo = False
                empleado.decision_vencimiento = "NO_RENOVAR"
                logger.error(f"Error procesando fecha de salida, desactivando por seguridad: {e}")
                
        elif accion == "indefinido":
            empleado.tipo_contrato = "Indefinido"
            empleado.fecha_salida = None
            empleado.decision_vencimiento = None # No requiere evaluación futura de vencimiento
            logger.info(f"Contrato cambiado a INDEFINIDO para {empleado.nombre_completo}")
            
            # Sincronizar tabla legal
            await self.repository.db.execute(
                "UPDATE periodos_empleo SET fecha_fin = NULL, tipo_contrato = 'Indefinido' WHERE empleado_id = ? AND es_activo = 1",
                (empleado_id,)
            )
            
        else:
            raise HTTPException(status_code=400, detail=f"Acción '{accion}' no válida")
            
        updated_empleado = await self.repository.update(empleado_id, empleado)
        
        # 1. Auto-ajuste de turnos si la fecha de salida cambió (Extensión o Indefinido)
        if updated_empleado.fecha_salida != old_fecha_salida:
            await self._adjust_shift_assignments(empleado_id, old_fecha_salida, updated_empleado.fecha_salida)

        # 2. Auto-limpieza de asistencias proyectadas si aplicó fecha_salida (Acortamiento)
        if updated_empleado.fecha_salida:
            await self._clean_ghost_data(empleado_id, updated_empleado.fecha_salida)
        
        # Notificar por Email
        if self.notification_service and self.config_service:
            try:
                # Obtener destinatarios combinados (global + área)
                recipients = await self.config_service.get_destinatarios_rrhh(updated_empleado.area)
                if recipients:
                    
                    # Preparar payload enriquecido del empleado
                    from datetime import datetime
                    fecha_salida_fmt = "Por definir / Indefinido"
                    if updated_empleado.fecha_salida:
                        try:
                            fecha_dt = datetime.strptime(updated_empleado.fecha_salida, "%Y-%m-%d")
                            fecha_salida_fmt = fecha_dt.strftime("%d/%m/%Y")
                        except (ValueError, TypeError) as fmt_err:
                            logger.debug(f"[Notif] fecha_salida mal formateada para emp {empleado_id}: {fmt_err}")
                    
                    # Calcular Antigüedad
                    antiguedad_str = "No calculada"
                    fecha_ingreso_fmt = "No registrada"
                    if updated_empleado.fecha_ingreso:
                        try:
                            f_ingreso = datetime.strptime(updated_empleado.fecha_ingreso, "%Y-%m-%d").date()
                            fecha_ingreso_fmt = f_ingreso.strftime("%d/%m/%Y")
                            
                            hoy = date.today()
                            diferencia = hoy - f_ingreso
                            anios = diferencia.days // 365
                            meses = (diferencia.days % 365) // 30
                            
                            antiguedad_parts = []
                            if anios > 0: antiguedad_parts.append(f"{anios} año(s)")
                            if meses > 0: antiguedad_parts.append(f"{meses} mes(es)")
                            
                            if not antiguedad_parts:
                                antiguedad_str = "Menos de 1 mes"
                            else:
                                antiguedad_str = " y ".join(antiguedad_parts)
                        except (ValueError, TypeError) as antig_err:
                            logger.debug(f"[Notif] fecha_ingreso mal formateada para emp {empleado_id}: {antig_err}")

                    employee_payload = {
                        "nombre": updated_empleado.nombre,
                        "nombre_completo": updated_empleado.nombre_completo,
                        "rut_formateado": updated_empleado.rut_formateado,
                        "cargo": updated_empleado.cargo,
                        "area": updated_empleado.area,
                        "fecha_salida_fmt": fecha_salida_fmt,
                        "fecha_ingreso_fmt": fecha_ingreso_fmt,
                        "antiguedad": antiguedad_str
                    }
                    
                    # Traducir detalle para RRHH
                    formatted_details = "Actualización de contrato realizada."
                    if accion == "desactivar" and updated_empleado.activo:
                         formatted_details = f"BAJA PROGRAMADA - El empleado permanecerá activo hasta el {fecha_salida_fmt}."
                    elif accion == "desactivar" and not updated_empleado.activo:
                         formatted_details = f"BAJA INMEDIATA - El empleado ha sido desactivado hoy {datetime.now().strftime('%d/%m/%Y')}."
                    elif accion == "indefinido":
                         formatted_details = "El contrato ha pasado a carácter Indefinido (Planta Permanente)."
                    elif accion == "renovar":
                         formatted_details = f"Contrato renovado (N° {updated_empleado.cant_contratos}). Nueva fecha de término: {fecha_salida_fmt}."

                    await self.notification_service.send_contract_decision_email(
                        employee_data=employee_payload,
                        decision_type=accion,
                        details=formatted_details,
                        recipients=recipients
                    )
            except Exception as e:
                logger.error(f"Error al enviar notificación de contrato: {e}")
                
        # [AUTO-HEALING] Gatillar reprocesamiento profundo para sanar estados (INA, Orphaned, etc)
        if self.asis_service and updated_empleado.activo:
            from datetime import date
            fecha_hoy = date.today()
            hoy_str = fecha_hoy.strftime("%Y-%m-%d")
            
            # Autonomía: Retroceder al menos al inicio del mes actual para limpiar estados erróneos (como INAs por contrato vencido)
            inicio_mes = date(fecha_hoy.year, fecha_hoy.month, 1).strftime("%Y-%m-%d")
            
            # Determinamos el punto de partida más seguro (el inicio del mes o el vencimiento previo si era este mes)
            candidatos = [inicio_mes]
            if old_fecha_salida and old_fecha_salida < hoy_str:
                candidatos.append(old_fecha_salida)
            
            fecha_inicio = min(candidatos)
            
            # No podemos procesar antes de que el empleado entrara a la empresa
            if updated_empleado.fecha_ingreso and fecha_inicio < updated_empleado.fecha_ingreso:
                fecha_inicio = updated_empleado.fecha_ingreso

            logger.info(f"🔄 AUTO-HEALING: Reprocesando asistencia de {updated_empleado.nombre} (ID {empleado_id}) desde {fecha_inicio} hasta hoy en background.")
            import asyncio
            asyncio.create_task(
                self.asis_service.reprocesar_periodo_empleado(
                    empleado_id=empleado_id,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=hoy_str,
                    force=True
                )
            )

        return updated_empleado

    async def _clean_ghost_data(self, empleado_id: int, fecha_salida: str) -> None:
        """Elimina asistencias proyectadas y corta turnos asignados más allá de la fecha de salida."""
        try:
            # Eliminar asistencias posteriores a la baja
            q_del_asis = "DELETE FROM asistencias WHERE empleado_id = ? AND fecha > ?"
            cursor_asis = await self.repository.db.execute(q_del_asis, (empleado_id, fecha_salida))
            filas_asis = cursor_asis.rowcount if cursor_asis else 0
            
            # Cerrar asignaciones de turno
            q_update_turno = """
                UPDATE asignacion_turnos 
                SET fecha_fin = ? 
                WHERE empleado_id = ? 
                  AND (fecha_fin IS NULL OR fecha_fin > ?)
            """
            cursor_turno = await self.repository.db.execute(q_update_turno, (fecha_salida, empleado_id, fecha_salida))
            filas_turno = cursor_turno.rowcount if cursor_turno else 0

            if filas_asis > 0 or filas_turno > 0:
                logger.info(
                    f"\U0001f9f9 Limpieza p\u00f3stumos empleado {empleado_id} (baja: {fecha_salida}): "
                    f"{filas_asis} asistencias eliminadas, {filas_turno} turno(s) cerrado(s)."
                )
            else:
                logger.debug(
                    f"\U0001f50d Limpieza p\u00f3stumos empleado {empleado_id} (baja: {fecha_salida}): "
                    f"sin datos que limpiar (empleado reci\u00e9n creado o ya limpio)."
                )
        except Exception as e:
            logger.error(f"Error limpiando datos fantasmas para el empleado {empleado_id}: {e}")
    async def registrar_baja(self, empleado_id: int, fecha_salida: str, motivo: str) -> Empleado:
        """
        Registrar la baja (renuncia/despido) de un empleado.
        
        Acciones:
        - Actualiza fecha_salida
        - Desactiva el empleado si la fecha es hoy o anterior
        - Envía notificación a RRHH
        """
        empleado = await self.get_empleado(empleado_id)
        
        # 1. Actualizar datos básicos
        empleado.fecha_salida = fecha_salida
        empleado.decision_vencimiento = f"BAJA: {motivo}"
        
        # 2. Determinar si se desactiva inmediatamente
        from datetime import datetime, date
        try:
            f_salida = datetime.strptime(fecha_salida, "%Y-%m-%d").date()
            if f_salida <= date.today():
                empleado.activo = False
                logger.info(f"Empleado {empleado.nombre_completo} desactivado inmediatamente (Baja por {motivo})")
            else:
                # Si es futuro, se mantiene activo hasta que llegue la fecha (o cronjob lo desactive)
                # Por seguridad, si el usuario explícitamente pide baja, podríamos desactivar, 
                # pero la lógica de 'matrix' depende de fecha_salida para cortar proyecciones.
                pass 
                logger.info(f"Baja registrada para {empleado.nombre_completo} con fecha futura {fecha_salida}")
        except Exception as e:
            logger.error(f"Error procesando fecha de baja: {e}")
            empleado.activo = False # Fallback seguro
            
        # 3. Persistir
        updated_empleado = await self.repository.update(empleado_id, empleado)
        
        # Auto-limpieza de turnos y asistencias proyectadas si aplicó fecha_salida
        if updated_empleado.fecha_salida:
             await self._clean_ghost_data(empleado_id, updated_empleado.fecha_salida)
        
        # 4. Notificar a RRHH
        if self.notification_service and self.config_service:
            try:
                recipients = await self.config_service.get_destinatarios_rrhh(updated_empleado.area)
                if recipients:
                    
                    # Reutilizamos la lógica de payload de procesar_vencimiento o creamos una nueva simple
                    # Formatear fechas
                    fecha_salida_fmt = fecha_salida
                    fecha_ingreso_fmt = "No registrada"
                    antiguedad_str = "No calculada"
                    
                    try:
                        f_dt = datetime.strptime(fecha_salida, "%Y-%m-%d")
                        fecha_salida_fmt = f_dt.strftime("%d/%m/%Y")
                        
                        if updated_empleado.fecha_ingreso:
                            f_ing = datetime.strptime(updated_empleado.fecha_ingreso, "%Y-%m-%d").date()
                            fecha_ingreso_fmt = f_ing.strftime("%d/%m/%Y")
                            
                            diff = f_salida - f_ing
                            anios = diff.days // 365
                            meses = (diff.days % 365) // 30
                            antiguedad_parts = []
                            if anios > 0: antiguedad_parts.append(f"{anios} año(s)")
                            if meses > 0: antiguedad_parts.append(f"{meses} mes(es)")
                            antiguedad_str = " y ".join(antiguedad_parts) if antiguedad_parts else "Menos de 1 mes"
                    except (ValueError, TypeError) as fmt_err:
                        logger.debug(f"[Notif Baja] Error formateando fechas emp {empleado_id}: {fmt_err}")

                    employee_payload = {
                        "nombre_completo": updated_empleado.nombre_completo,
                        "rut_formateado": updated_empleado.rut_formateado,
                        "cargo": updated_empleado.cargo,
                        "area": updated_empleado.area,
                        "fecha_salida_fmt": fecha_salida_fmt,
                        "fecha_ingreso_fmt": fecha_ingreso_fmt,
                        "antiguedad": antiguedad_str
                    }
                    
                    details = f"El empleado ha sido dado de baja por: {motivo}."
                    
                    # Usamos el mismo template de decisión de contrato por ahora, o uno genérico
                    await self.notification_service.send_contract_decision_email(
                        employee_data=employee_payload,
                        decision_type="BAJA_MANUAL",
                        details=details,
                        recipients=recipients
                    )
            except Exception as e:
                logger.error(f"Error enviando correo de baja: {e}")
                
        # [AUTO-HEALING] Reprocesar para limpiar marcas posteriores a la baja
        if self.asis_service:
            from datetime import date
            hoy = date.today().strftime("%Y-%m-%d")
            logger.info(f"🔄 Baja registrada para {empleado_id}. Limpiando periodos póstumos en background.")
            import asyncio
            asyncio.create_task(
                self.asis_service.reprocesar_periodo_empleado(
                    empleado_id=empleado_id,
                    fecha_inicio=updated_empleado.fecha_salida,
                    fecha_fin=hoy,
                    force=True
                )
            )

        return updated_empleado

    async def _adjust_shift_assignments(self, empleado_id: int, old_fs: Optional[str], new_fs: Optional[str]) -> None:
        """
        Ajusta inteligentemente las fechas de fin de los turnos asignados tras un cambio de contrato.
        
        Casos:
        1. Extensión Temporal: old_fs=A, new_fs=B (B > A) -> Turnos que terminaban en A ahora terminan en B.
        2. Paso a Indefinido: old_fs=A, new_fs=None -> Turnos que terminaban en A ahora son indefinidos (NULL).
        3. Acortamiento: new_fs < old_fs -> Turnos que terminaban después de new_fs se cortan a new_fs.
        """
        if old_fs == new_fs:
            return

        try:
            # CASO 1 y 2: Extensión o Indefinido (Estirar)
            if old_fs and (not new_fs or new_fs > old_fs):
                query = """
                    UPDATE asignacion_turnos 
                    SET fecha_fin = ?
                    WHERE empleado_id = ? 
                      AND fecha_fin = ?
                """
                await self.repository.db.execute(query, (new_fs, empleado_id, old_fs))
                logger.info(f"🔄 Horarios 'estirados' automáticamente para empleado {empleado_id} (de {old_fs} a {new_fs or 'Indefinido'})")
            
            # CASO 3: Acortamiento (Cortar)
            elif (not old_fs and new_fs) or (old_fs and new_fs and new_fs < old_fs):
                query_cut = """
                    UPDATE asignacion_turnos 
                    SET fecha_fin = ?
                    WHERE empleado_id = ? 
                      AND (fecha_fin IS NULL OR fecha_fin > ?)
                """
                await self.repository.db.execute(query_cut, (new_fs, empleado_id, new_fs))
                logger.info(f"✂️ Horarios cortados preventivamente para empleado {empleado_id} a la fecha {new_fs}")

        except Exception as e:
            logger.error(f"Error ajustando asignaciones de turno para {empleado_id}: {e}")

    async def reincorporar_empleado(self, empleado_id: int, data: ReincorporarRequest) -> Empleado:
        """
        Lógica atómica para el Wizard de Reincorporación.
        Cierra periodos antiguos, abre uno nuevo, actualiza la ficha y asigna turno.
        """
        # 1. Verificar existencia y detectar cambios de área
        empleado = await self.get_empleado(empleado_id)
        area_anterior = empleado.area
        nueva_area = data.area or "Sin Área"
        
        from backend.repositories.area import AreaRepository
        area_repo = AreaRepository(self.repository.db)
        area_id_val = await area_repo.find_area_id_by_name_or_alias(nueva_area)
        
        if area_anterior and area_anterior != nueva_area:
            logger.info(f"🚩 Detección de cambio de área en reincorporación para {empleado.rut}: '{area_anterior}' -> '{nueva_area}'")
            # Podríamos grabar un log de auditoría aquí si fuera necesario
        
        from datetime import datetime, timedelta, date
        
        # Calcular fecha de cierre lógico para registros previos (el día anterior al nuevo ingreso)
        try:
            fecha_obj = datetime.strptime(data.fecha_inicio, '%Y-%m-%d')
            fecha_fin_anterior = (fecha_obj - timedelta(days=1)).strftime('%Y-%m-%d')
        except Exception:
            # Fallback por si la fecha no viene en formato estándar
            fecha_fin_anterior = data.fecha_inicio 

        try:
            async with self.repository.db.transaction():
                # 2. Cerrar periodos antiguos en 'periodos_empleo'
                # Ponemos es_activo=0 para cualquier periodo previo
                await self.repository.db.execute(
                    "UPDATE periodos_empleo SET es_activo = 0 WHERE empleado_id = ? AND es_activo = 1",
                    (empleado_id,)
                )
                
                # Si algún periodo anterior no tiene fecha_fin, lo cerramos lógicamente
                await self.repository.db.execute("""
                    UPDATE periodos_empleo 
                    SET fecha_fin = ? 
                    WHERE empleado_id = ? AND (fecha_fin IS NULL OR fecha_fin >= ?)
                """, (fecha_fin_anterior, empleado_id, data.fecha_inicio))
                
                # 3. Crear nuevo periodo de empleo real (Digital Twin Anchor)
                await self.repository.db.execute("""
                    INSERT INTO periodos_empleo (empleado_id, fecha_inicio, fecha_fin, tipo_contrato, es_activo)
                    VALUES (?, ?, ?, ?, 1)
                """, (empleado_id, data.fecha_inicio, data.fecha_fin, data.tipo_contrato))
                
                # 4. Actualizar ficha maestra (Sync BioAlba Data)
                await self.repository.db.execute("""
                    UPDATE empleados SET 
                        activo = 1,
                        fecha_ingreso = ?,
                        fecha_salida = ?,
                        tipo_contrato = ?,
                        cargo = ?,
                        area_id = ?,
                        compania = ?,
                        cant_contratos = 1,
                        decision_vencimiento = NULL,
                        updated_at = datetime('now')
                    WHERE id = ?
                """, (data.fecha_inicio, data.fecha_fin, data.tipo_contrato, data.cargo, area_id_val, data.compania, empleado_id))
                
                # 5. Cerrar Historial de Area anterior y abrir el nuevo (Paso 2 Wizard)
                await self.repository.db.execute("""
                    UPDATE historial_areas SET es_actual = 0, fecha_hasta = ? 
                    WHERE empleado_id = ? AND es_actual = 1
                """, (fecha_fin_anterior, empleado_id))
                
                await self.repository.db.execute("""
                    INSERT INTO historial_areas (empleado_id, area_id, fecha_desde, es_actual, validado)
                    VALUES (?, ?, ?, 1, 1)
                """, (empleado_id, area_id_val, data.fecha_inicio))
                
                # 6. Asignación Atómica de Turno (Paso 3 Wizard)
                from backend.repositories.turno import TurnoRepository
                from backend.schemas.turno import AsignacionCreate
                turno_repo = TurnoRepository(self.repository.db)
                nueva_asig = AsignacionCreate(
                    empleado_id=empleado_id,
                    turno_id=data.turno_id,
                    fecha_inicio=data.fecha_inicio,
                    fecha_fin=data.fecha_fin,
                    reemplazar=True
                )
                await turno_repo.create_asignacion(nueva_asig)

                logger.success(f"🚀 Reincorporación atómica completada para RUT {empleado.rut} (ID: {empleado_id})")

            # 7. Gatillar reprocesamiento si es retroactivo
            hoy_str = date.today().strftime("%Y-%m-%d")
            if data.fecha_inicio < hoy_str:
                logger.info(f"🔄 Re-ingreso retroactivo ({data.fecha_inicio}). Gatillando reprocesamiento...")
                try:
                    from backend.services.asistencia_service import AsistenciaService
                    from backend.repositories.asistencia import AsistenciaRepository
                    asis_service = AsistenciaService(AsistenciaRepository(self.repository.db))
                    
                    # Reprocesar desde re-ingreso hasta hoy
                    await asis_service.reprocesar_periodo_empleado(
                        empleado_id=empleado_id,
                        fecha_inicio=data.fecha_inicio,
                        fecha_fin=hoy_str,
                        force=True
                    )
                except Exception as e_asis:
                    logger.warning(f"⚠️ Re-ingreso exitoso, pero falló reprocesamiento: {e_asis}")

            return await self.get_empleado(empleado_id)

        except Exception as e:
            logger.error(f"❌ Error fatal en reincorporación de {empleado_id}: {e}")
            raise HTTPException(status_code=500, detail=f"No se pudo completar la reincorporación: {str(e)}")

    async def repair_all_period_inconsistencies(self, deep_repair_from: str = None) -> dict:
        """
        [SCRUBBING] Utilidad masiva para reparar inconsistencias de la base de datos.
        Sincroniza 'empleados.fecha_salida' con 'periodos_empleo.fecha_fin'.
        Limpia inasistencias falsas de Abril.
        """
        from datetime import date
        from typing import Dict, Any
        hoy = date.today().strftime("%Y-%m-%d")
        recalc_start = deep_repair_from or f"{date.today().year}-{date.today().month:02d}-01"
        
        stats = {"detectados": 0, "reparados": 0, "errores": 0, "detalles": []}
        logger.info(f"🧹 Iniciando Scrubbing Masivo (Recálculo desde: {recalc_start})")

        try:
            # 1. Buscar empleados activos con discrepancias o sin periodos activos
            query_inconsistentes = """
                SELECT e.id, e.nombre, e.apellido_paterno, e.rut, e.fecha_ingreso, e.fecha_salida as ficha_fin, 
                       p.id as periodo_id, p.fecha_fin as periodo_fin, p.tipo_contrato as periodo_tipo
                FROM empleados e
                LEFT JOIN periodos_empleo p ON e.id = p.empleado_id AND p.es_activo = 1
                WHERE e.activo = 1 
                  AND (p.id IS NULL OR IFNULL(e.fecha_salida, '') != IFNULL(p.fecha_fin, ''))
            """
            inconsistentes = await self.repository.db.fetch_all(query_inconsistentes)
            stats["detectados"] = len(inconsistentes)
            
            if not inconsistentes:
                logger.info("✅ No se detectaron inconsistencias. Base de datos sana.")
                return stats

            # 2. Reparar uno a uno
            for inc in inconsistentes:
                emp_id = inc["id"]
                rut = inc["rut"]
                stats["reparados"] += 1
                
                try:
                    async with self.repository.db.transaction():
                        if not inc["periodo_id"]:
                            # CASO A: No tiene periodo activo. Creamos uno basado en la ficha.
                            logger.warning(f"🔧 Reparando {rut}: Sin periodo activo. Creando uno...")
                            await self.repository.db.execute("""
                                INSERT INTO periodos_empleo (empleado_id, fecha_inicio, fecha_fin, tipo_contrato, es_activo)
                                VALUES (?, ?, ?, ?, 1)
                            """, (emp_id, inc["fecha_ingreso"] or hoy, inc["ficha_fin"], "Temporal"))
                        else:
                            # CASO B: Desfase de fechas. Sincronizamos periodo con la ficha.
                            logger.info(f"🔧 Reparando {rut}: Desfase detectado (Ficha: {inc['ficha_fin']} vs Periodo: {inc['periodo_fin']})")
                            await self.repository.db.execute("""
                                UPDATE periodos_empleo SET fecha_fin = ? WHERE id = ?
                            """, (inc["ficha_fin"], inc["periodo_id"]))
                    
                    # 3. Gatillar recálculo quirúrgico inmediato para este empleado
                    try:
                        from backend.services.asistencia_service import AsistenciaService
                        from backend.repositories.asistencia import AsistenciaRepository
                        asis_service = AsistenciaService(AsistenciaRepository(self.repository.db))
                        
                        await asis_service.reprocesar_periodo_empleado(
                            empleado_id=emp_id,
                            fecha_inicio=recalc_start,
                            fecha_fin=hoy,
                            force=True
                        )
                        logger.debug(f"✨ Reproceso completado para {rut}")
                    except Exception as e_asis:
                        logger.warning(f"⚠️ {rut} reparado legalmente, pero falló reproceso: {e_asis}")

                except Exception as e_inc:
                    logger.error(f"❌ Error reparando {rut}: {e_inc}")
                    stats["reparados"] -= 1
                    stats["errores"] += 1
                    stats["detalles"].append(f"{rut}: {str(e_inc)}")

            logger.success(f"🧹 Scrubbing finalizado. {stats['reparados']} empleados sanados.")
            return stats

        except Exception as e_global:
            logger.error(f"❌ Error crítico en Scrubbing: {e_global}")
            raise e_global
