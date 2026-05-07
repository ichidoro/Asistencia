from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from loguru import logger
from backend.repositories.configuracion import ConfiguracionRepository
from backend.repositories.empleado import EmpleadoRepository
from backend.schemas.bono import BonoCreate, BonoResponse, BonoAsignacionCreate
from backend.schemas.justificacion import JustificacionTipoCreate, JustificacionCreate
from backend.services.notification_service import NotificationService

class ConfiguracionService:
    def __init__(self, repository: ConfiguracionRepository, notification_service: Optional[NotificationService] = None):
        self.repository = repository
        self.notification_service = notification_service

    async def initialize(self):
        """Inicializar tablas si no existen"""
        await self.repository.init_tables()

    # --- BONOS ---
    async def create_bono(self, bono: BonoCreate) -> int:
        bono_id = await self.repository.create_bono(bono)
        if bono_id and bono.activo:
             # Trigger: Recalcular para TODOS los empleados activos
            try:
                emp_repo = EmpleadoRepository(self.repository.db)
                # FIX: Método correcto es get_all, no get_all_empleados
                empleados = await emp_repo.get_all(limit=1000, activo=True)
                
                logger.info(f"Trigger create_bono: Recalculando asignaciones para {len(empleados)} empleados...")
                for emp in empleados:
                    await self.recalculate_assignments(emp)
                logger.success("Trigger create_bono: Recálculo masivo completado.")
                
            except Exception as e:
                logger.error(f"Error en trigger create_bono: {e}")
        return bono_id

    async def update_bono(self, bono_id: int, bono: BonoCreate) -> bool:
        updated = await self.repository.update_bono(bono_id, bono)
        if updated:
            # Trigger: Recalcular para TODOS los empleados activos
            # Esto es pesado, se podría mover a background task en el futuro
            try:
                emp_repo = EmpleadoRepository(self.repository.db)
                # FIX: Método correcto es get_all, no get_all_empleados
                empleados = await emp_repo.get_all(limit=1000, activo=True)
                
                logger.info(f"Trigger update_bono: Recalculando asignaciones para {len(empleados)} empleados...")
                for emp in empleados:
                    await self.recalculate_assignments(emp)
                logger.success("Trigger update_bono: Recálculo masivo completado.")
                
            except Exception as e:
                logger.error(f"Error en trigger update_bono: {e}")
                
        return updated

    async def delete_bono(self, bono_id: int) -> bool:
        return await self.repository.delete_bono(bono_id)

    async def get_all_bonos(self) -> List[Dict]:
        return await self.repository.get_all_bonos()

    async def recalculate_assignments(self, empleado: Any) -> List[str]:
        """
        Recalcular asignaciones de bonos para un empleado.
        Se llama cuando el empleado cambia de Cargo, Contrato, etc.
        Retorna la lista de nombres de bonos asignados.

        OPTIMIZACIÓN BATCH: Toda la lógica de evaluación se hace primero en
        memoria, luego las escrituras a BD van en un único execute_batch()
        → 1 adquisición del _db_lock + 1 commit + 1 sync a Turso por empleado.
        Antes: (2 + N_bonos) llamadas execute() individuales con su propio lock.
        """
        bonos_asignados: List[str] = []
        try:
            empleado_id = empleado.id
            today = date.today()
            yesterday = today - timedelta(days=1)

            logger.info(f"Recalculando asignaciones para Empleado {empleado_id} ({empleado.nombre})...")

            # ── FASE 1: Evaluar qué bonos aplican (SIN tocar la BD) ─────────
            bonos = await self.repository.get_all_bonos()
            bonos_a_asignar: List[Dict] = []

            for bono in bonos:
                if not bono['activo']:
                    continue

                match = False
                for regla in bono.get('reglas', []):
                    # 3.1 Filtro Tipo Contrato
                    if regla['tipo_contrato'] and regla['tipo_contrato'] != "Todos":
                        if regla['tipo_contrato'] != empleado.tipo_contrato:
                            continue

                    # 3.2 Filtro Cargo
                    if regla['cargo_requerido']:
                        cargo_regla = regla['cargo_requerido'].lower().strip()
                        cargo_emp = (empleado.cargo or "").lower().strip()
                        if cargo_regla not in cargo_emp:
                            continue

                    # 3.3 Filtro Cargos Excluidos
                    if regla.get('cargos_excluidos'):
                        excluidos = [c.strip().lower() for c in regla['cargos_excluidos'].split(',')]
                        cargo_emp = (empleado.cargo or "").lower().strip()
                        if any(excl in cargo_emp for excl in excluidos if excl):
                            logger.info(f" -> Skip Bono '{bono['nombre']}' para {empleado.nombre}: Cargo '{empleado.cargo}' excluido.")
                            continue

                    # Si pasa todos los filtros, match
                    match = True
                    break

                if match:
                    bonos_a_asignar.append(bono)
                    bonos_asignados.append(bono['nombre'])
                    logger.info(f" -> Asignado Bono '{bono['nombre']}' a Empleado {empleado_id}")

            # ── FASE 2: Escribir toda la BD en una sola transacción ─────────
            ops = [
                # Limpiar asignaciones de hoy/futuras (idempotencia)
                (
                    "DELETE FROM bono_asignaciones WHERE empleado_id = ? AND date(fecha_desde) >= date(?)",
                    (empleado_id, str(today))
                ),
                # Cerrar asignaciones vigentes hasta ayer
                (
                    "UPDATE bono_asignaciones SET fecha_hasta = ? WHERE empleado_id = ? AND fecha_hasta IS NULL",
                    (str(yesterday), empleado_id)
                ),
            ]
            for bono in bonos_a_asignar:
                ops.append((
                    "INSERT INTO bono_asignaciones (empleado_id, bono_id, fecha_desde, fecha_hasta) VALUES (?, ?, ?, NULL)",
                    (empleado_id, bono['id'], str(today))
                ))

            await self.repository.db.execute_batch(ops)
            logger.success(f"Recálculo completado: {len(bonos_a_asignar)} bonos asignados.")

        except Exception as e:
            logger.error(f"Error recalculando asignaciones: {e}")
            # No lanzamos excepción para no romper el guardado del empleado

        return bonos_asignados

    async def audit_all_assignments(self) -> Dict[str, Any]:
        """
        Auditoría masiva: Asegura que todos los empleados activos tengan los bonos que les corresponden.
        Se llama en el startup para corregir posibles descalces o fallas de red previas.
        """
        try:
            logger.info("🕵️ Iniciando Auditoría Proactiva de Bonos...")
            emp_repo = EmpleadoRepository(self.repository.db)
            
            # 1. Obtener todos los empleados activos
            empleados = await emp_repo.get_all(limit=2000, activo=True)
            if not empleados:
                return {"status": "ok", "checked": 0, "fixed": 0}

            # 2. Obtener todos los bonos activos
            bonos = await self.repository.get_all_bonos()
            bonos_activos = [b for b in bonos if b['activo']]
            if not bonos_activos:
                return {"status": "ok", "checked": len(empleados), "fixed": 0}

            today = date.today()
            fixed_count = 0
            
            # 3. Auditoría por empleado
            # Optimizamos obteniendo sus asignaciones actuales en un solo paso
            emp_ids = [e.id for e in empleados]
            asignaciones_actuales = await self.repository.get_active_asignaciones_batch(emp_ids, str(today))
            
            # Indexar asignaciones por empleado para búsqueda rápida
            asig_map = {}
            for asig in asignaciones_actuales:
                eid = asig['empleado_id']
                if eid not in asig_map:
                    asig_map[eid] = set()
                asig_map[eid].add(asig['bono_id'])

            logger.info(f"🔍 Auditando {len(empleados)} empleados vs {len(bonos_activos)} tipos de bonos...")

            for emp in empleados:
                emp_asig = asig_map.get(emp.id, set())
                
                for bono in bonos_activos:
                    # 3.1 ¿Ya lo tiene asignado?
                    if bono['id'] in emp_asig:
                        continue
                    
                    # 3.2 ¿Cumple las reglas?
                    match = False
                    for regla in bono.get('reglas', []):
                        # Filtro Tipo Contrato
                        if regla['tipo_contrato'] and regla['tipo_contrato'] != "Todos":
                            if regla['tipo_contrato'] != emp.tipo_contrato:
                                continue
                                
                        # Filtro Cargo
                        if regla['cargo_requerido']:
                            cargo_regla = regla['cargo_requerido'].lower().strip()
                            cargo_emp = (emp.cargo or "").lower().strip()
                            if cargo_regla not in cargo_emp:
                                continue

                        # Filtro Cargos Excluidos
                        if regla.get('cargos_excluidos'):
                            excluidos = [c.strip().lower() for c in regla['cargos_excluidos'].split(',')]
                            cargo_emp = (emp.cargo or "").lower().strip()
                            if any(excl in cargo_emp for excl in excluidos if excl):
                                continue
                                
                        match = True
                        break
                    
                    # 3.3 Si cumple pero no lo tiene -> AUTO-FIX
                    if match:
                        logger.warning(f"🩹 AUTO-FIX: Empleado {emp.nombre} (ID {emp.id}) debería tener bono '{bono['nombre']}'. Asignando...")
                        await self.repository.create_asignacion(emp.id, bono['id'], str(today))
                        fixed_count += 1
            
            if fixed_count > 0:
                logger.success(f"✅ Auditoría completada: Se corrigieron {fixed_count} asignaciones faltantes.")
            else:
                logger.info("💎 Auditoría completada: Todos los empleados tienen sus bonos al día.")
                
            return {
                "status": "success",
                "checked": len(empleados),
                "fixed": fixed_count
            }
            
        except Exception as e:
            logger.error(f"❌ Falló auditoría de bonos: {e}")
            return {"status": "error", "error": str(e)}

    # --- JUSTIFICACIONES ---
    async def get_tipos_justificacion(self) -> List[Dict]:
        return await self.repository.get_tipos_justificacion()

    async def get_all_tipos_justificacion(self) -> List[Dict]:
        return await self.repository.get_all_tipos_justificacion()

    async def create_tipo_justificacion(self, tipo: JustificacionTipoCreate) -> int:
        return await self.repository.create_tipo_justificacion(tipo)

    async def update_tipo_justificacion(self, tipo_id: int, tipo: JustificacionTipoCreate) -> bool:
        return await self.repository.update_tipo_justificacion(tipo_id, tipo)

    async def delete_tipo_justificacion(self, tipo_id: int) -> bool:
        return await self.repository.delete_tipo_justificacion(tipo_id)

    async def create_justificacion(self, j: JustificacionCreate) -> int:
        from fastapi import HTTPException
        
        # 1. Obtener reglas del tipo de justificación
        tipos = await self.repository.get_all_tipos_justificacion()
        tipo = next((t for t in tipos if t['id'] == j.tipo_id), None)
        
        if not tipo:
            raise HTTPException(status_code=404, detail="Tipo de justificación no encontrado")

        # 2. Validar Duración
        dias_calendario = (j.fecha_fin - j.fecha_inicio).days + 1
        
        if dias_calendario < 1:
             raise HTTPException(status_code=400, detail="La fecha de fin debe ser igual o posterior a la de inicio")

        # Calcular días efectivos según turno del empleado y configuración del tipo
        dias_solicitados = await self._calcular_dias_habiles(j.empleado_id, j.fecha_inicio, j.fecha_fin, tipo)
        logger.info(f"Justificación: {dias_calendario} días calendario → {dias_solicitados} días efectivos (tipo={tipo['nombre']})")

        if tipo['min_dias'] and dias_solicitados < tipo['min_dias']:
            raise HTTPException(status_code=400, detail=f"Este permiso requiere un mínimo de {tipo['min_dias']} días (calculados {dias_solicitados} días hábiles)")

        if tipo['max_dias'] and dias_solicitados > tipo['max_dias']:
            raise HTTPException(status_code=400, detail=f"Este permiso permite un máximo de {tipo['max_dias']} días (calculados {dias_solicitados} días hábiles)")

        # 3. Validar Frecuencia Anual
        if tipo['frecuencia_anual']:
            year = j.fecha_inicio.year
            count = await self.repository.count_justificaciones_anio(j.empleado_id, j.tipo_id, year)
            if count >= tipo['frecuencia_anual']:
                raise HTTPException(status_code=400, detail=f"Se ha excedido la frecuencia anual permitida ({tipo['frecuencia_anual']}) para este permiso")
        
        justificacion_id = await self.repository.create_justificacion(j)
        
        # Notificar por Email
        if self.notification_service:
            try:
                # Obtener info del empleado
                emp_repo = EmpleadoRepository(self.repository.db)
                emp = await emp_repo.get_by_id(j.empleado_id)
                
                if emp:
                    recipients = await self.get_destinatarios_rrhh(emp.area)
                    if recipients:
                        employee_payload = {
                        "nombre": emp.nombre,
                        "nombre_completo": emp.nombre_completo,
                        "rut_formateado": emp.rut_formateado,
                        "cargo": emp.cargo,
                        "area": emp.area
                    }
                    await self.notification_service.send_justification_email(
                        employee_data=employee_payload,
                        type_name=tipo['nombre'],
                        start_date=str(j.fecha_inicio),
                        end_date=str(j.fecha_fin),
                        recipients=recipients,
                        observations=j.observaciones, # [NEW]
                        days_count=dias_solicitados   # [NEW]
                    )
            except Exception as e:
                logger.error(f"Error al enviar notificación de justificación: {e}")
                
        return justificacion_id

    async def get_justificaciones_empleado(self, empleado_id: int) -> List[Dict]:
        return await self.repository.get_justificaciones_empleado(empleado_id)

    async def cerrar_permiso(self, empleado_id: int, fecha: str, hora_fin: str) -> bool:
        """Cierra un permiso abierto y dispara recalculo de asistencia"""
        success = await self.repository.cerrar_permiso_activo(empleado_id, fecha, hora_fin)
        if success:
            try:
                # Recalcular asistencia para el día cerrado
                from backend.repositories.asistencia import AsistenciaRepository
                from backend.services.asistencia_service import AsistenciaService
                asistencia_repo = AsistenciaRepository(self.repository.db)
                asistencia_service = AsistenciaService(asistencia_repo)
                await asistencia_service.procesar_empleado_dia(empleado_id, fecha)
                logger.info(f"Cierre de permiso: Asistencia recalculada para {empleado_id} el {fecha}")
            except Exception as e:
                logger.error(f"Error recalculando tras cierre de permiso: {e}")
        return success

    async def update_justificacion(self, justificacion_id: int, j: JustificacionCreate) -> bool:
        """Edita una justificación: valida períodos cerrados + solapamiento"""
        from fastapi import HTTPException

        # 1. Obtener datos ANTES de la edición
        old = await self.repository.get_justificacion_by_id(justificacion_id)
        if not old:
            return False

        # 2. Validar período cerrado (rango viejo Y nuevo)
        await self._validar_periodo_cerrado(old['fecha_inicio'], old['fecha_fin'])
        await self._validar_periodo_cerrado(str(j.fecha_inicio), str(j.fecha_fin))

        # 3. Validar solapamiento con otras justificaciones del mismo empleado
        await self._validar_solapamiento(j.empleado_id, justificacion_id,
                                          str(j.fecha_inicio), str(j.fecha_fin))

        # 4. Actualizar en DB
        datos = {
            'tipo_id': j.tipo_id, 'fecha_inicio': j.fecha_inicio,
            'fecha_fin': j.fecha_fin, 'hora_inicio': j.hora_inicio,
            'hora_fin': j.hora_fin, 'observaciones': j.observaciones,
            'documento_url': j.documento_url
        }
        updated = await self.repository.update_justificacion(justificacion_id, datos)
        # El recálculo de asistencia ahora se hace en segundo plano desde el router
        return updated

    async def delete_justificacion(self, justificacion_id: int) -> bool:
        """Elimina una justificación: valida período cerrado"""
        from fastapi import HTTPException

        # 1. Obtener datos antes de borrar
        existing = await self.repository.get_justificacion_by_id(justificacion_id)
        if not existing:
            return False

        # 2. Validar período cerrado
        await self._validar_periodo_cerrado(existing['fecha_inicio'], existing['fecha_fin'])

        # 3. Borrar
        deleted = await self.repository.delete_justificacion(justificacion_id)
        # El recálculo de asistencia ahora se hace en segundo plano desde el router
        return deleted is not None

    # --- HELPERS COMPARTIDOS PARA EDICIÓN/ELIMINACIÓN ---

    async def calcular_fecha_fin_justificacion(self, empleado_id: int, fecha_inicio_str: str, tipo_id: int) -> str:
        """
        Calcula automáticamente la fecha de fin requerida para cumplir con 'min_dias'
        según el turno del empleado (saltando días libres/feriados).
        """
        tipos = await self.repository.get_all_tipos_justificacion()
        tipo = next((t for t in tipos if t['id'] == tipo_id), None)
        if not tipo:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Tipo no encontrado")
            
        target_dias = tipo.get('min_dias') or tipo.get('max_dias')
        if not target_dias:
            return fecha_inicio_str
            
        fecha_inicio = date.fromisoformat(fecha_inicio_str)
        
        if tipo.get('dias_corridos'):
            return str(fecha_inicio + timedelta(days=target_dias - 1))
            
        asignacion = await self.repository.db.fetch_one(
            "SELECT turno_id FROM asignacion_turnos WHERE empleado_id = ? "
            "AND fecha_fin IS NULL ORDER BY fecha_inicio DESC LIMIT 1",
            (empleado_id,)
        )
        if not asignacion:
            return str(fecha_inicio + timedelta(days=target_dias - 1))
            
        turno_id = asignacion['turno_id']
        turno_dias = await self.repository.db.fetch_all(
            "SELECT dia_semana, es_libre FROM turno_dias WHERE turno_id = ?",
            (turno_id,)
        )
        dias_libres_set = {td['dia_semana'] for td in turno_dias if td.get('es_libre')}
        
        feriados_set = set()
        if not tipo.get('sobreescribe_feriados'):
            fecha_max = fecha_inicio + timedelta(days=60)
            feriados = await self.repository.db.fetch_all(
                "SELECT fecha FROM feriados WHERE date(fecha) BETWEEN date(?) AND date(?)",
                (str(fecha_inicio), str(fecha_max))
            )
            feriados_set = {f['fecha'] for f in feriados}
            
        count = 0
        current = fecha_inicio
        while True:
            dia_semana = current.weekday()
            fecha_str = str(current)
            es_libre = dia_semana in dias_libres_set
            es_feriado = fecha_str in feriados_set
            
            if not es_libre and not es_feriado:
                count += 1
                
            if count >= target_dias:
                break
                
            current += timedelta(days=1)
            
        return str(current)

    async def _calcular_dias_habiles(self, empleado_id: int, fecha_inicio: date, fecha_fin: date, tipo: dict) -> int:
        """
        Calcula los días efectivos de una justificación según el turno del empleado.
        - Si dias_corridos=1: cuenta TODOS los días calendario (pisa libres y feriados)
        - Si dias_corridos=0: descuenta días libres del turno y feriados (si sobreescribe_feriados=0)
        Los días hábiles se determinan por la configuración del turno del empleado,
        NO por una regla genérica Lun-Vie.
        """
        # Días corridos → todos los días calendario
        if tipo.get('dias_corridos'):
            return (fecha_fin - fecha_inicio).days + 1

        # Obtener turno activo del empleado
        asignacion = await self.repository.db.fetch_one(
            "SELECT turno_id FROM asignacion_turnos WHERE empleado_id = ? "
            "AND fecha_fin IS NULL ORDER BY fecha_inicio DESC LIMIT 1",
            (empleado_id,)
        )
        if not asignacion:
            # Sin turno asignado → fallback: contar todos los días
            logger.warning(f"Empleado {empleado_id} sin turno activo, usando días calendario como fallback")
            return (fecha_fin - fecha_inicio).days + 1

        turno_id = asignacion['turno_id']

        # Obtener configuración de días del turno (qué días son libres)
        turno_dias = await self.repository.db.fetch_all(
            "SELECT dia_semana, es_libre FROM turno_dias WHERE turno_id = ?",
            (turno_id,)
        )
        dias_libres_set = {td['dia_semana'] for td in turno_dias if td.get('es_libre')}

        # Obtener feriados en el rango (si no sobreescribe feriados)
        feriados_set = set()
        if not tipo.get('sobreescribe_feriados'):
            feriados = await self.repository.db.fetch_all(
                "SELECT fecha FROM feriados WHERE date(fecha) BETWEEN date(?) AND date(?)",
                (str(fecha_inicio), str(fecha_fin))
            )
            feriados_set = {f['fecha'] for f in feriados}

        # Contar días hábiles efectivos
        count = 0
        current = fecha_inicio
        while current <= fecha_fin:
            dia_semana = current.weekday()  # 0=Lun, 6=Dom
            fecha_str = str(current)

            es_libre = dia_semana in dias_libres_set
            es_feriado = fecha_str in feriados_set

            if not es_libre and not es_feriado:
                count += 1

            current += timedelta(days=1)

        logger.debug(f"_calcular_dias_habiles: emp={empleado_id}, rango={fecha_inicio}→{fecha_fin}, "
                     f"libres_turno={dias_libres_set}, feriados={len(feriados_set)}, resultado={count}")
        return count

    async def _validar_periodo_cerrado(self, fecha_inicio: str, fecha_fin: str):
        """Lanza HTTPException si las fechas caen en un período cerrado por RRHH"""
        from fastapi import HTTPException
        try:
            cierre = await self.repository.db.fetch_one("""
                SELECT id FROM cierres_periodos
                WHERE date(fecha_inicio) <= date(?) AND date(fecha_fin) >= date(?)
            """, (str(fecha_fin), str(fecha_inicio)))
            if cierre:
                raise HTTPException(400,
                    "No se puede modificar: la justificación cae en un período cerrado por RRHH")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Error verificando período cerrado: {e}")

    async def _validar_solapamiento(self, empleado_id: int, excluir_id: int,
                                      fecha_inicio: str, fecha_fin: str):
        """Lanza HTTPException si el rango se solapa con otra justificación del mismo empleado"""
        from fastapi import HTTPException
        overlap = await self.repository.db.fetch_one("""
            SELECT id, fecha_inicio, fecha_fin FROM justificaciones
            WHERE empleado_id = ? AND id != ?
              AND date(fecha_inicio) <= date(?) AND date(fecha_fin) >= date(?)
        """, (empleado_id, excluir_id, str(fecha_fin), str(fecha_inicio)))
        if overlap:
            raise HTTPException(400,
                f"Las nuevas fechas se solapan con otra justificación (ID={overlap['id']}, "
                f"{overlap['fecha_inicio']} → {overlap['fecha_fin']})")

    async def _recalcular_dias_justificacion(self, empleado_id, fecha_inicio, fecha_fin):
        """Recalcula asistencia para el rango afectado usando batch con delta/diffing"""
        try:
            from backend.repositories.asistencia import AsistenciaRepository
            from backend.services.asistencia_service import AsistenciaService

            repo = AsistenciaRepository(self.repository.db)
            service = AsistenciaService(repo)

            # ⚡ Usar reprocesar_periodo_empleado: incluye delta/diffing + batch commit
            await service.reprocesar_periodo_empleado(
                empleado_id=empleado_id,
                fecha_inicio=str(fecha_inicio),
                fecha_fin=str(fecha_fin),
                force=True,
            )
            logger.info(f"Recálculo completado para empleado {empleado_id} ({fecha_inicio} → {fecha_fin})")
        except Exception as e:
            logger.error(f"Error recalculando tras edición/eliminación de justificación: {e}")

    # --- AJUSTES GLOBALES ---
    async def get_all_ajustes(self) -> List[Dict]:
        return await self.repository.get_all_ajustes()

    async def get_ajuste(self, clave: str, default: Any = None) -> Any:
        return await self.repository.get_ajuste(clave, default)

    async def set_ajuste(self, clave: str, valor: str) -> bool:
        return await self.repository.set_ajuste(clave, valor)

    # --- NOTIFICACIONES POR AREA ---
    async def get_notificaciones_areas(self) -> List[dict]:
        return await self.repository.get_notificaciones_areas()
        
    async def get_notificaciones_area(self, area: str) -> str:
        return await self.repository.get_notificaciones_area(area)
        
    async def set_notificaciones_area(self, area: str, emails: str) -> bool:
        return await self.repository.set_notificaciones_area(area, emails)
        
    async def delete_notificaciones_area(self, area: str) -> bool:
        return await self.repository.delete_notificaciones_area(area)

    async def get_destinatarios_rrhh(self, area: str = None) -> List[str]:
        """Combina los correos globales con los específicos del área (si se provee)"""
        recipients = set()
        
        # 1. Globales (Ajustes)
        global_str = await self.get_ajuste("email_notificaciones_rrhh", "")
        if global_str:
            for r in global_str.split(","):
                if r.strip():
                    recipients.add(r.strip())
                    
        # 2. Por Área (Si aplica)
        if area:
            area_str = await self.get_notificaciones_area(area)
            if area_str:
                for r in area_str.split(","):
                    if r.strip():
                        recipients.add(r.strip())
                        
        return list(recipients)

    # --- PAGADORES ---
    async def get_all_pagadores(self, solo_activos: bool = True) -> List[Dict]:
        return await self.repository.get_all_pagadores(solo_activos)

    async def create_pagador(self, nombre: str) -> int:
        return await self.repository.create_pagador(nombre)

    async def update_pagador(self, pagador_id: int, nombre: str, activo: bool) -> bool:
        return await self.repository.update_pagador(pagador_id, nombre, activo)
