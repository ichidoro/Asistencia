import calendar
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from loguru import logger

from backend.core.database import db
from backend.repositories.beneficio import BeneficioRepository
from backend.repositories.empleado import EmpleadoRepository
from backend.repositories.configuracion import ConfiguracionRepository
from backend.services.bono_service import BonoService
from backend.services.asistencia_service import AsistenciaService
from backend.repositories.asistencia import AsistenciaRepository

class BeneficioService:
    def __init__(self):
        self.db = db
        self.repo = BeneficioRepository()
        self.emp_repo = EmpleadoRepository(db)
        self.config_repo = ConfiguracionRepository(db)

    async def evaluar_beneficio_empleados(self, mes: int, anio: int) -> List[Dict[str, Any]]:
        """
        Evalua a todos los empleados activos del periodo actual.
        Retorna la lista de empleados indicando si califican o estan bloqueados con su motivo.
        """
        logger.info(f"📋 [BeneficioService] Evaluando calificacion de productos propios para {anio}-{mes:02d}")
        
        # 1. Cargar todos los empleados activos
        # Nota: Usamos skip=0, limit=1000 para cargar toda la planilla activa de forma eficiente
        empleados = await self.emp_repo.get_all(activo=True, limit=1000)
        
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
                   COALESCE(cp.aplica_bono, 1) AS aplica_bono_pagador
            FROM justificaciones j
            JOIN justificacion_tipos jt ON j.tipo_id = jt.id
            LEFT JOIN cat_pagadores cp ON jt.pagador = cp.nombre
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

            # --- Regla 2: Asistencia (Heredada del Bono de Compromiso) ---
            califica_asistencia = True
            motivo_asistencia = "Cumple asistencia 100%."
            
            if compromiso_bono and compromiso_bono.get("activo"):
                # Ejecutar calificacion de bono Compromiso
                res_calif = bono_service._calificar_bono(
                    emp_dict,
                    compromiso_bono,
                    asist_map.get(emp_id, []),
                    just_map.get(emp_id, []),
                    matrix_data.get(emp_id),
                    hoy_str,
                    fecha_inicio,
                    fecha_fin,
                    feriados_set
                )
                
                # Si el bono no aplica por cargo/contrato o si no califica por asistencia
                if not res_calif.get("aplica"):
                    califica_asistencia = False
                    motivo_asistencia = res_calif.get("motivo", "No aplica para este Cargo/Contrato.")
                elif not res_calif.get("califica"):
                    califica_asistencia = False
                    motivo_asistencia = f"No califica por asistencia. Detalle: {res_calif.get('motivo')}"
            else:
                # Si el Bono de Compromiso no esta configurado o esta inactivo,
                # se asume que no hay restriccion de asistencia activa.
                logger.warning("[BeneficioService] Bono de Compromiso inactivo o no configurado. Omite asistencia.")
            
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
            return True, "Asignacion de productos propios guardada exitosamente."
        else:
            return False, "Ocurrio un error al intentar guardar la asignacion en la base de datos."
