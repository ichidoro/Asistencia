import calendar
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from loguru import logger

from backend.core.database import db
from backend.repositories.productos_4 import Productos4Repository
from backend.repositories.empleado import EmpleadoRepository
from backend.repositories.configuracion import ConfiguracionRepository
from backend.services.bono_service import BonoService
from backend.services.asistencia_service import AsistenciaService
from backend.repositories.asistencia import AsistenciaRepository

class Productos4Service:
    def __init__(self):
        self.db = db
        self.repo = Productos4Repository()
        self.emp_repo = EmpleadoRepository(db)
        self.config_repo = ConfiguracionRepository(db)

    async def evaluar_beneficio_empleados(self, mes: int, anio: int, areas: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Evalua a todos los empleados activos del periodo actual, opcionalmente filtrados por areas (RLS).
        Retorna la lista de empleados indicando si califican o estan bloqueados con su motivo.
        """
        logger.info(f"📋 [Productos4Service] Evaluando calificacion de 4 Productos para {anio}-{mes:02d}. Areas: {areas}")
        
        # 1. Cargar todos los empleados activos filtrados por area si se especifica
        # Nota: Usamos skip=0, limit=1000 para cargar planilla activa de forma eficiente
        empleados = await self.emp_repo.get_all(activo=True, limit=1000, areas=areas)
        
        # 2. Cargar contexto de asistencia masivo (optimizado) para evitar N+1
        fecha_inicio = f"{anio}-{mes:02d}-01"
        last_day = calendar.monthrange(anio, mes)[1]
        fecha_fin = f"{anio}-{mes:02d}-{last_day:02d}"
        
        asistencias_raw = await self.db.fetch_all(
            "SELECT * FROM asistencias WHERE fecha BETWEEN ? AND ?",
            (fecha_inicio, fecha_fin),
        )
        
        just_raw = await self.db.fetch_all(
            """
            SELECT j.*, jt.nombre AS tipo_nombre,
                   jt.con_goce_sueldo, jt.descuenta_remuneracion, jt.pagador,
                   1 AS aplica_bono_pagador
            FROM justificaciones j
            JOIN justificacion_tipos jt ON j.tipo_id = jt.id
            WHERE j.fecha_inicio <= ? AND j.fecha_fin >= ?
            """,
            (fecha_fin, fecha_inicio),
        )
        
        asist_service = AsistenciaService(AsistenciaRepository(self.db))
        matrix_res = await asist_service.get_matrix_data_with_projections(mes, anio)
        matrix_data = matrix_res.get("matrix", {})
        
        # 3. Cargar el Bono de Compromiso y evaluar asistencia
        bonos = await self.config_repo.get_all_bonos()
        compromiso_bono = next((b for b in bonos if str(b.get("nombre")).strip().lower() == "compromiso"), None)
        
        # Cargar feriados para el motor
        feriados_rows = await self.db.fetch_all(
            "SELECT fecha FROM feriados WHERE fecha LIKE ?", (f"{anio}-%",)
        )
        feriados_set = {r['fecha'] for r in feriados_rows}
        hoy_str = datetime.now().strftime("%Y-%m-%d")
        
        bono_service = BonoService(self.db)
        
        # Preparar mapeos de asistencia y justificaciones por empleado
        asist_map = {}
        for a in asistencias_raw:
            asist_map.setdefault(a["empleado_id"], []).append(a)
            
        just_map = {}
        for j in just_raw:
            just_map.setdefault(j["empleado_id"], []).append(j)

        # 4. Cargar asignaciones guardadas en el periodo actual
        asignaciones = await self.repo.get_asignaciones_periodo(mes, anio)
        asignaciones_map = {a["empleado_id"]: a for a in asignaciones}

        resultado_evaluacion = []
        
        for emp in empleados:
            emp_dict = emp.to_dict()
            emp_id = emp.id
            nombre = emp.nombre_completo
            
            # --- Regla 1: Antiguedad (a partir del segundo mes) ---
            fecha_ingreso_str = emp.fecha_ingreso
            if not fecha_ingreso_str:
                resultado_evaluacion.append({
                    "empleado_id": emp_id,
                    "nombre": nombre,
                    "rut": emp.rut_formateado,
                    "cargo": emp.cargo or "Sin Cargo",
                    "area": emp.area or "Sin Area",
                    "califica": False,
                    "motivo": "Fecha de ingreso no registrada en ficha del empleado.",
                    "seleccion": None
                })
                continue
                
            try:
                hire_date = datetime.strptime(fecha_ingreso_str[:10], "%Y-%m-%d")
                diff_months = (anio - hire_date.year) * 12 + (mes - hire_date.month)
                if diff_months < 1:
                    resultado_evaluacion.append({
                        "empleado_id": emp_id,
                        "nombre": nombre,
                        "rut": emp.rut_formateado,
                        "cargo": emp.cargo or "Sin Cargo",
                        "area": emp.area or "Sin Area",
                        "califica": False,
                        "motivo": f"Antiguedad insuficiente. Ingreso el {fecha_ingreso_str[:10]}. Califica a partir del segundo mes.",
                        "seleccion": None
                    })
                    continue
            except Exception as e:
                resultado_evaluacion.append({
                    "empleado_id": emp_id,
                    "nombre": nombre,
                    "rut": emp.rut_formateado,
                    "cargo": emp.cargo or "Sin Cargo",
                    "area": emp.area or "Sin Area",
                    "califica": False,
                    "motivo": f"Error evaluando fecha de ingreso ({fecha_ingreso_str}): {e}",
                    "seleccion": None
                })
                continue

            # --- Regla 2: Asistencia (Heredada del Bono de Compromiso, sin exclusiones de cargo) ---
            califica_asistencia = True
            motivo_asistencia = "Cumple asistencia 100%."
            
            if compromiso_bono and compromiso_bono.get("activo"):
                import copy
                # Modificar las reglas del bono en memoria para que aplique universalmente a cualquier cargo y contrato
                compromiso_beneficio = copy.deepcopy(compromiso_bono)
                compromiso_beneficio["reglas"] = [{
                    "cargo_requerido": None,
                    "cargos_excluidos": None,
                    "tipo_contrato": None,
                    "es_proporcional": 0,
                    "monto": 1000
                }]
                
                # Ejecutar calificacion de bono Compromiso
                res_calif = bono_service._calificar_bono(
                    emp_dict,
                    compromiso_beneficio,
                    asist_map.get(emp_id, []),
                    just_map.get(emp_id, []),
                    matrix_data.get(emp_id),
                    hoy_str,
                    fecha_inicio,
                    fecha_fin,
                    feriados_set
                )
                
                # Para el beneficio de 4 Productos, no se excluye a nadie (aplica es siempre True)
                # Solo se evalua si califica por su asistencia
                if not res_calif.get("califica"):
                    califica_asistencia = False
                    motivo_asistencia = f"No califica por asistencia. Detalle: {res_calif.get('motivo')}"
            else:
                # Si el Bono de Compromiso no esta configurado o esta inactivo,
                # se asume que no hay restriccion de asistencia activa.
                logger.warning("[Productos4Service] Bono de Compromiso inactivo o no configurado. Omite asistencia.")
            
            # Obtener seleccion previa si existe
            prev_asig = asignaciones_map.get(emp_id)
            seleccion = None
            if prev_asig:
                seleccion = {
                    "p1": prev_asig.get("producto1_codigo"),
                    "p2": prev_asig.get("producto2_codigo"),
                    "p3": prev_asig.get("producto3_codigo"),
                    "p4": prev_asig.get("producto4_codigo"),
                    "observaciones": prev_asig.get("observaciones"),
                    "updated_at": prev_asig.get("updated_at")
                }

            resultado_evaluacion.append({
                "empleado_id": emp_id,
                "nombre": nombre,
                "rut": emp.rut_formateado,
                "cargo": emp.cargo or "Sin Cargo",
                "area": emp.area or "Sin Area",
                "califica": califica_asistencia,
                "motivo": motivo_asistencia if not califica_asistencia else "OK",
                "seleccion": seleccion
            })
            
        return resultado_evaluacion

    async def guardar_seleccion_productos(
        self, empleado_id: int, mes: int, anio: int, 
        codigos: List[Optional[int]], observaciones: Optional[str], usuario_creador_id: int
    ) -> Tuple[bool, str]:
        """
        Valida y guarda la seleccion de productos de elaboracion propia para el empleado en el periodo.
        """
        # 0. Verificar el estado del período
        status_info = await self.get_period_status(mes, anio)
        if status_info["status"] != "open":
            return False, status_info["mensaje"]

        # 1. Validar que la lista tenga un maximo de 4 elementos
        if len(codigos) > 4:
            return False, "La seleccion no puede exceder los 4 productos propios."
            
        # Rellenar con None hasta llegar a 4 elementos
        while len(codigos) < 4:
            codigos.append(None)

        # Filtrar codigos no nulos para validacion de limites
        codigos_filtrados = [c for c in codigos if c is not None]
        if not codigos_filtrados:
            return False, "Debe seleccionar al menos un producto propio para guardar la asignacion."
            
        # 2. Validar existencia y max_cantidad de cada producto en un solo viaje de red (IN)
        placeholders = ",".join(["?"] * len(codigos_filtrados))
        query = f"SELECT codigo, max_cantidad, descripcion FROM productos_elaboracion_propia WHERE codigo IN ({placeholders}) AND activo = 1"
        rows = await self.db.fetch_all(query, tuple(codigos_filtrados))
        
        productos_map = {row["codigo"]: row for row in rows}
        
        # Validar si algun codigo seleccionado no existe o esta inactivo
        for code in codigos_filtrados:
            if code not in productos_map:
                return False, f"El codigo de producto {code} no existe en el catalogo activo."

        # Contar ocurrencias seleccionadas
        counts = {}
        for code in codigos_filtrados:
            counts[code] = counts.get(code, 0) + 1
            
        # Validar limites individuales (max_cantidad)
        for code, count in counts.items():
            prod = productos_map[code]
            max_cant = prod["max_cantidad"]
            if count > max_cant:
                return False, f"Seleccion invalida: El producto '{prod['descripcion']}' se selecciono {count} veces, pero su limite maximo es {max_cant}."

        # 3. Guardar en la base de datos
        p1, p2, p3, p4 = codigos[0], codigos[1], codigos[2], codigos[3]
        success = await self.repo.save_asignacion(
            empleado_id=empleado_id,
            mes=mes,
            anio=anio,
            p1=p1,
            p2=p2,
            p3=p3,
            p4=p4,
            observaciones=observaciones,
            usuario_creador_id=usuario_creador_id
        )
        
        if success:
            return True, "Asignacion de 4 Productos guardada exitosamente."
        else:
            return False, "Ocurrio un error al intentar guardar la asignacion en la base de datos."

    async def get_consolidado_periodo(self, mes: int, anio: int, areas: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Obtiene el reporte consolidado de asignaciones del periodo (totales agrupados y desglose).
        """
        # 1. Obtener asignaciones filtradas opcionalmente por área
        asignaciones = await self.repo.get_raw_asignaciones_periodo(mes, anio, areas=areas)

        # 2. Cargar todos los productos (incluidos inactivos para mapeo de histórico)
        productos = await self.repo.get_all_productos(incluir_inactivos=True)
        prod_map = {p["codigo"]: p for p in productos}

        # 3. Procesar consolidación
        resumen_counts = {}
        # Estructura del desglose de áreas por producto: {codigo: {area_nombre: cantidad}}
        desglose_areas = {}
        detalles = []

        for asig in asignaciones:
            codigos_seleccionados = [
                asig.get("producto1_codigo"),
                asig.get("producto2_codigo"),
                asig.get("producto3_codigo"),
                asig.get("producto4_codigo")
            ]
            area_name = asig.get("area_nombre") or "Sin Área"

            prod_list = []
            for code in codigos_seleccionados:
                if code is not None:
                    prod = prod_map.get(code)
                    if prod:
                        prod_list.append({
                            "codigo": prod["codigo"],
                            "descripcion": prod["descripcion"],
                            "unidad": prod["unidad"],
                            "tipo": prod["tipo"],
                            "marca": prod["marca"]
                        })
                    else:
                        prod_list.append({
                            "codigo": code,
                            "descripcion": f"Cód. {code} (No encontrado)",
                            "unidad": "",
                            "tipo": "DESCONOCIDO",
                            "marca": ""
                        })

                    # Sumar a totales del producto
                    resumen_counts[code] = resumen_counts.get(code, 0) + 1

                    # Sumar a desglose por área
                    desglose_areas.setdefault(code, {})
                    desglose_areas[code][area_name] = desglose_areas[code].get(area_name, 0) + 1
                else:
                    prod_list.append(None)

            detalles.append({
                "empleado_id": asig.get("empleado_id"),
                "empleado_nombre": asig.get("empleado_nombre") or "Sin Nombre",
                "empleado_rut": asig.get("empleado_rut") or "Sin RUT",
                "empleado_cargo": asig.get("empleado_cargo") or "Sin Cargo",
                "area": area_name,
                "productos": prod_list,
                "observaciones": asig.get("observaciones") or "",
                "entregado": bool(asig.get("entregado", 0)),
                "fecha_entrega": asig.get("fecha_entrega"),
                "usuario_entrega_nombre": asig.get("usuario_entrega_nombre"),
                "updated_at": asig.get("updated_at")
            })

        # Armar lista ordenada de resumen
        resumen = []
        for code, total in resumen_counts.items():
            prod = prod_map.get(code)
            desglose = desglose_areas.get(code, {})
            # Formatear el desglose como lista de objetos para que sea fácil de mapear en frontend
            desglose_list = [{"area": k, "cantidad": v} for k, v in desglose.items()]

            if prod:
                resumen.append({
                    "codigo": prod["codigo"],
                    "descripcion": prod["descripcion"],
                    "unidad": prod["unidad"],
                    "tipo": prod["tipo"],
                    "marca": prod["marca"],
                    "cantidad_total": total,
                    "desglose_areas": desglose_list
                })
            else:
                resumen.append({
                    "codigo": code,
                    "descripcion": f"Código {code} (No encontrado)",
                    "unidad": "",
                    "tipo": "DESCONOCIDO",
                    "marca": "",
                    "cantidad_total": total,
                    "desglose_areas": desglose_list
                })

        resumen.sort(key=lambda x: x["descripcion"])

        return {
            "resumen": resumen,
            "detalles": detalles
        }

    async def marcar_entrega_producto(
        self, empleado_id: int, mes: int, anio: int, entregado: bool, usuario_entrega_id: int
    ) -> Tuple[bool, str]:
        """
        Registra la entrega física del beneficio a un empleado en base de datos.
        """
        # Verificar que ya exista una asignación guardada
        asig = await self.repo.get_asignacion_empleado(empleado_id, mes, anio)
        if not asig:
            return False, "No se puede marcar la entrega porque el empleado no tiene productos asignados para este periodo."

        success = await self.repo.update_delivery_status(
            empleado_id=empleado_id,
            mes=mes,
            anio=anio,
            entregado=entregado,
            usuario_entrega_id=usuario_entrega_id
        )

        if success:
            msg = "Entrega registrada exitosamente." if entregado else "Entrega revertida a pendiente."
            return True, msg
        else:
            return False, "Error al actualizar el estado de entrega en la base de datos."

    async def get_period_status(self, mes: int, anio: int) -> Dict[str, Any]:
        """
        Determina el estado del periodo actual para la asignacion de 4 productos:
        - 'closed': Si el periodo actual ya fue cerrado.
        - 'blocked_previous': Si el periodo anterior tiene asignaciones y no esta cerrado.
        - 'open': Si esta abierto y se puede operar.
        """
        # 1. ¿Está el periodo actual cerrado?
        is_closed = await self.repo.is_period_closed(mes, anio)
        if is_closed:
            return {
                "status": "closed",
                "mes": mes,
                "anio": anio,
                "mensaje": f"El período {anio}-{mes:02d} se encuentra cerrado para asignación."
            }

        # 2. Calcular periodo anterior
        prev_mes = mes - 1
        prev_anio = anio
        if prev_mes == 0:
            prev_mes = 12
            prev_anio = anio - 1

        # 3. ¿Tiene asignaciones el periodo anterior?
        prev_has_asig = await self.repo.has_assignments_in_period(prev_mes, prev_anio)
        if prev_has_asig:
            # Si tiene asignaciones, ¿está cerrado?
            prev_closed = await self.repo.is_period_closed(prev_mes, prev_anio)
            if not prev_closed:
                return {
                    "status": "blocked_previous",
                    "mes": mes,
                    "anio": anio,
                    "prev_mes": prev_mes,
                    "prev_anio": prev_anio,
                    "mensaje": f"No se pueden realizar asignaciones en {anio}-{mes:02d} hasta que el período anterior ({prev_anio}-{prev_mes:02d}) esté CERRADO."
                }

        # 4. De lo contrario, está abierto
        return {
            "status": "open",
            "mes": mes,
            "anio": anio,
            "mensaje": "El período está abierto."
        }

    async def cerrar_periodo(self, mes: int, anio: int, usuario_id: int) -> Tuple[bool, str]:
        is_closed = await self.repo.is_period_closed(mes, anio)
        if is_closed:
            return False, f"El período {anio}-{mes:02d} ya está cerrado."
            
        success = await self.repo.close_period(mes, anio, usuario_id)
        if success:
            return True, f"Período {anio}-{mes:02d} cerrado exitosamente."
        else:
            return False, "Error al guardar el cierre del período en la base de datos."

    async def reabrir_periodo(self, mes: int, anio: int) -> Tuple[bool, str]:
        is_closed = await self.repo.is_period_closed(mes, anio)
        if not is_closed:
            return False, f"El período {anio}-{mes:02d} ya está abierto."
            
        success = await self.repo.reopen_period(mes, anio)
        if success:
            return True, f"Período {anio}-{mes:02d} reabierto exitosamente."
        else:
            return False, "Error al reabrir el período en la base de datos."

