"""
Repository - Asistencia
Capa de acceso a datos para Marcaciones y Procesamiento de Asistencia
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, date
from loguru import logger

from backend.core.database import Database

class AsistenciaRepository:
    def __init__(self, db: Database):
        self.db = db

    async def get_raw_logs(self, empleado_id: int, fecha: str) -> List[Dict[str, Any]]:
        """
        Obtiene todas las marcaciones crudas de un empleado.
        Ventana segura: Ayer 00:00 → Mañana 23:59:59.
        El filtrado fino se realiza en el Service Layer (Paradigma de Consumo).
        """
        from datetime import timedelta
        fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
        ayer = (fecha_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        manana = (fecha_dt + timedelta(days=1)).strftime("%Y-%m-%d")

        query = """
            SELECT * FROM logs_raw
            WHERE empleado_id = ?
              AND fecha_hora BETWEEN ? AND ?
            ORDER BY fecha_hora ASC
        """
        return await self.db.fetch_all(query, (empleado_id, f"{ayer} 00:00:00", f"{manana} 23:59:59"))

    async def get_raw_logs_summary(self, fecha_inicio: str, fecha_fin: str) -> Dict[int, Dict[str, int]]:
        """
        Retorna conteo de marcas por empleado_id y fecha en el periodo.
        """
        query = """
            SELECT empleado_id, substr(fecha_hora, 1, 10) as fecha, COUNT(*) as total
            FROM logs_raw
            WHERE fecha_hora BETWEEN ? AND ?
            GROUP BY empleado_id, fecha
        """
        rows = await self.db.fetch_all(query, (f"{fecha_inicio} 00:00:00", f"{fecha_fin} 23:59:59"))
        
        res = {}
        for r in rows:
            eid = r['empleado_id']
            f = r['fecha']
            if eid not in res: res[eid] = {}
            res[eid][f] = r['total']
        return res

    async def get_asistencia(self, empleado_id: int, fecha: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el registro de asistencia procesada de un empleado para una fecha.
        """
        query = "SELECT * FROM asistencias WHERE empleado_id = ? AND fecha = ?"
        return await self.db.fetch_one(query, (empleado_id, fecha))

    async def get_asignacion_vigente(self, empleado_id: Any, fecha: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el turno asignado a un empleado en una fecha específica.
        """
        # Robustez: Extraer ID si se pasa el objeto completo
        eid = empleado_id['id'] if isinstance(empleado_id, dict) else empleado_id
        
        query = """
            SELECT t.*, a.turno_id, a.id as asignacion_id, a.fecha_inicio as asignacion_desde
            FROM turnos t
            JOIN asignacion_turnos a ON t.id = a.turno_id
            WHERE a.empleado_id = ? 
              AND a.fecha_inicio <= ? 
              AND (a.fecha_fin IS NULL OR a.fecha_fin >= ?)
            ORDER BY a.fecha_inicio DESC, a.id DESC
            LIMIT 1
        """
        return await self.db.fetch_one(query, (eid, fecha, fecha))

    async def delete_asistencia(self, empleado_id: int, fecha: str) -> None:
        """
        Elimina un registro de asistencia (ej. si se borra una justificación futura sin marcas reales).
        """
        query = "DELETE FROM asistencias WHERE empleado_id = ? AND fecha = ?"
        await self.db.execute(query, (empleado_id, fecha))

    async def get_turno_detalle_dia(self, turno_id: int, dia_semana: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene la configuración de entrada/salida para un día específico (0-6).
        """
        query = "SELECT * FROM turno_dias WHERE turno_id = ? AND dia_semana = ?"
        return await self.db.fetch_one(query, (turno_id, dia_semana))

    async def update_asistencia(self, empleado_id: int, fecha: str, update_data: Dict[str, Any]) -> None:
        """
        Actualiza campos específicos de una asistencia existente.
        """
        if not update_data:
            return
        
        set_clauses = []
        params = []
        for k, v in update_data.items():
            set_clauses.append(f"{k} = ?")
            params.append(v)
            
        set_clauses.append("updated_at = datetime('now')")
        
        params.extend([empleado_id, fecha])
        query = f"UPDATE asistencias SET {', '.join(set_clauses)} WHERE empleado_id = ? AND fecha = ?"
        await self.db.execute(query, params)

    async def upsert_asistencia(self, data: Dict[str, Any]) -> None:
        """
        Guarda o actualiza un registro de asistencia procesada (Individual).
        """
        await self.batch_upsert_asistencia([data])

    async def batch_upsert_asistencia(self, data_list: List[Dict[str, Any]], bypass_cierre_check: bool = False, suppress_auto_sync: bool = False) -> None:
        """
        Guarda o actualiza múltiples registros de asistencia procesada.
        Incluye validación de periodos cerrados para integridad histórica.

        suppress_auto_sync=True: No dispara conn.sync() al terminar (WAL local).
        Usar cuando el caller hará sync_to_cloud_explicit() al final del batch masivo.
        """
        if not data_list:
            return

        # Validación de periodos cerrados movida al Servicio para evitar N+1 Queries.
        # Si bypass_cierre_check es False, el repositorio asume que la data ya fue filtrada o validada.
        pass

        query = """
            INSERT INTO asistencias (
                empleado_id, fecha, turno_asignado_id, 
                hora_entrada_teorica, hora_salida_teorica, horas_teoricas,
                hora_entrada_real, hora_salida_real,
                minutos_atraso, minutos_colacion, minutos_colacion_real, horas_trabajadas,
                minutos_deuda, minutos_extra_bruto,
                minutos_salida_adelantada,
                estado, observaciones, origen, updated_at,
                minutos_exceso_colacion, minutos_colacion_auto, minutos_permiso_personal_deuda,
                hora_salida_colacion, hora_entrada_colacion, hora_inicio_permiso,
                hora_termino_permiso, minutos_permisos_detectados,
                tiene_atraso, tiene_salida_adelantada, tiene_permiso
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(empleado_id, fecha) DO UPDATE SET
                turno_asignado_id=excluded.turno_asignado_id,
                hora_entrada_teorica=excluded.hora_entrada_teorica,
                hora_salida_teorica=excluded.hora_salida_teorica,
                horas_teoricas=excluded.horas_teoricas,
                hora_entrada_real=excluded.hora_entrada_real,
                hora_salida_real=excluded.hora_salida_real,
                minutos_atraso=excluded.minutos_atraso,
                minutos_colacion=excluded.minutos_colacion,
                minutos_colacion_real=excluded.minutos_colacion_real,
                horas_trabajadas=excluded.horas_trabajadas,
                minutos_deuda=excluded.minutos_deuda,
                minutos_extra_bruto=excluded.minutos_extra_bruto,
                minutos_salida_adelantada=excluded.minutos_salida_adelantada,
                estado=excluded.estado,
                observaciones=excluded.observaciones,
                origen=excluded.origen,
                minutos_exceso_colacion=excluded.minutos_exceso_colacion,
                minutos_colacion_auto=excluded.minutos_colacion_auto,
                minutos_permiso_personal_deuda=excluded.minutos_permiso_personal_deuda,
                hora_salida_colacion=excluded.hora_salida_colacion,
                hora_entrada_colacion=excluded.hora_entrada_colacion,
                hora_inicio_permiso=excluded.hora_inicio_permiso,
                hora_termino_permiso=excluded.hora_termino_permiso,
                minutos_permisos_detectados=excluded.minutos_permisos_detectados,
                tiene_atraso=excluded.tiene_atraso,
                tiene_salida_adelantada=excluded.tiene_salida_adelantada,
                tiene_permiso=excluded.tiene_permiso,
                updated_at=datetime('now')
        """
        
        params_list = []
        for d in data_list:
            params = (
                d['empleado_id'], d['fecha'], d.get('turno_asignado_id'),
                d.get('hora_entrada_teorica'), d.get('hora_salida_teorica'),
                d.get('horas_teoricas', 0),
                d.get('hora_entrada_real'), d.get('hora_salida_real'),
                d.get('minutos_atraso', 0), d.get('minutos_colacion', 0),
                d.get('minutos_colacion_real', 0),
                d.get('horas_trabajadas', 0), d.get('minutos_deuda', 0),
                d.get('minutos_extra_bruto', 0),
                d.get('minutos_salida_adelantada', 0),
                d.get('estado', 'PENDIENTE'), d.get('observaciones'),
                d.get('origen', 'SISTEMA'),
                d.get('minutos_exceso_colacion', 0), d.get('minutos_colacion_auto', 0),
                d.get('minutos_permiso_personal_deuda', 0),
                d.get('hora_salida_colacion'), d.get('hora_entrada_colacion'),
                d.get('hora_inicio_permiso'), d.get('hora_termino_permiso'),
                d.get('minutos_permisos_detectados', 0),
                d.get('tiene_atraso', 0),
                d.get('tiene_salida_adelantada', 0),
                d.get('tiene_permiso', 0),
            )
            params_list.append(params)

        import asyncio
        chunk_size = 100
        for i in range(0, len(params_list), chunk_size):
            chunk = params_list[i:i + chunk_size]
            await self.db.executemany(query, chunk, suppress_auto_sync=suppress_auto_sync)
            # Pause to allow Turso Sync Rust engine to flush frames cleanly
            await asyncio.sleep(0.2)



    async def upsert_jornada_especial(self, data: Dict[str, Any]) -> None:
        """
        Guarda o actualiza un registro en la tabla de jornadas_especiales.
        """
        query = """
            INSERT INTO jornadas_especiales (
                empleado_id, fecha, hora_entrada, hora_salida, 
                minutos_trabajados, estado, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(empleado_id, fecha) DO UPDATE SET
                hora_entrada=excluded.hora_entrada,
                hora_salida=excluded.hora_salida,
                minutos_trabajados=excluded.minutos_trabajados,
                estado=excluded.estado,
                observaciones=excluded.observaciones
        """
        params = (
            data['empleado_id'],
            data['fecha'],
            data.get('hora_entrada'),
            data.get('hora_salida'),
            data.get('minutos_trabajados', 0),
            data.get('estado', 'JORNADA_ESPECIAL'),
            data.get('observaciones', '')
        )
        await self.db.execute(query, params)



    async def get_asistencias_periodo(self, fecha_inicio: str, fecha_fin: str, area: str = None, empleado_id: int = None, turno_id: int = None, areas_permitidas: Optional[List[str]] = None, empleado_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        """
        Obtiene listado de asistencias procesadas para reportes, matriz o calendario.
        Visibilidad controlada por historial de áreas y vigencia legal del contrato.
        
        [REGLA INVIOLABLE]: Solo se muestran registros cuya fecha esté contenida
        dentro de la vigencia de la ficha maestra (fecha_ingreso → fecha_salida).
        Esto impide que la grilla muestre asistencias de empleados fuera de contrato.
        """
        query = """
            SELECT 
                a.id as asistencia_id, a.fecha, e.id as empleado_id, a.estado, a.observaciones,
                a.hora_entrada_real, a.hora_salida_real, a.minutos_atraso, a.minutos_colacion, a.minutos_colacion_real, a.horas_trabajadas, 
                a.minutos_deuda, a.minutos_extra_bruto,
                he.minutos_autorizados as minutos_extra_autorizados,
                he.estado as estado_he,
                a.minutos_salida_adelantada, a.minutos_exceso_colacion, a.minutos_colacion_auto, a.minutos_permiso_personal_deuda, a.updated_at,
                a.horas_teoricas, a.hora_entrada_teorica, a.hora_salida_teorica, a.turno_asignado_id,
                a.hora_salida_colacion, a.hora_entrada_colacion, a.hora_inicio_permiso, a.hora_termino_permiso, a.minutos_permisos_detectados,
                a.tiene_atraso, a.tiene_salida_adelantada, a.tiene_permiso,
                e.nombre, e.apellido_paterno, e.apellido_materno, e.rut, a_table.nombre as area, e.activo,
                t.nombre as turno_nombre
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            LEFT JOIN horas_extras he ON he.empleado_id = a.empleado_id AND he.fecha = a.fecha
            LEFT JOIN historial_areas h ON e.id = h.empleado_id 
                AND a.fecha BETWEEN h.fecha_desde AND COALESCE(h.fecha_hasta, '2099-12-31')
            LEFT JOIN areas a_table ON h.area_id = a_table.id
            LEFT JOIN turnos t ON a.turno_asignado_id = t.id
            WHERE a.fecha BETWEEN ? AND ?
              AND a.fecha >= COALESCE(e.fecha_ingreso, '1900-01-01')
              AND a.fecha <= COALESCE(e.fecha_salida, '2099-12-31')
        """
        params = [fecha_inicio, fecha_fin]
        
        # Security Data Scoping (RLS) - Según Historial
        if areas_permitidas is not None:
            if not areas_permitidas:
                return []
            if area and area not in areas_permitidas:
                return []
            
            placeholders = ",".join(["?"] * len(areas_permitidas))
            query += f" AND a_table.nombre IN ({placeholders})"
            params.extend(areas_permitidas)
        
        if area:
            query += " AND a_table.nombre = ?"
            params.append(area)
            
        if empleado_id:
            query += " AND e.id = ?"
            params.append(empleado_id)

        if empleado_ids:
            placeholders = ",".join(["?"] * len(empleado_ids))
            query += f" AND e.id IN ({placeholders})"
            params.extend(empleado_ids)

        if turno_id:
            query += " AND a.turno_asignado_id = ?"
            params.append(turno_id)

        query += " ORDER BY e.apellido_paterno ASC, e.apellido_materno ASC, e.nombre ASC, a.fecha ASC"
        return await self.db.fetch_all(query, tuple(params))

    async def get_period_stats(self, fecha_inicio: str, fecha_fin: str, areas_permitidas: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Obtiene estadísticas diarias agrupadas por fecha para el periodo (Charts).
        Usa historial de áreas para el filtrado RLS.
        """
        query = """
            SELECT 
                a.fecha,
                COUNT(*) as total,
                SUM(CASE WHEN a.estado NOT IN ('INASISTENCIA','LIBRE','FERIADO','JORNADA_ESPECIAL','EXTRA') THEN 1 ELSE 0 END) as presentes,
                SUM(CASE WHEN a.tiene_atraso = 1 THEN 1 ELSE 0 END) as atrasos,
                SUM(CASE WHEN a.tiene_salida_adelantada = 1 THEN 1 ELSE 0 END) as salidas_adelantadas,
                SUM(CASE WHEN a.tiene_permiso = 1 THEN 1 ELSE 0 END) as permisos,
                SUM(CASE WHEN a.estado = 'INASISTENCIA' THEN 1 ELSE 0 END) as inasistencias,
                SUM(CASE WHEN a.estado = 'ANOMALIA' THEN 1 ELSE 0 END) as anomalias
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            JOIN historial_areas h ON e.id = h.empleado_id 
                AND a.fecha BETWEEN h.fecha_desde AND COALESCE(h.fecha_hasta, '2099-12-31')
            LEFT JOIN areas a_table ON h.area_id = a_table.id
            WHERE a.fecha BETWEEN ? AND ?
        """
        params = [fecha_inicio, fecha_fin]

        if areas_permitidas:
            placeholders = ",".join(["?"] * len(areas_permitidas))
            query += f" AND a_table.nombre IN ({placeholders})"
            params.extend(areas_permitidas)

        query += " GROUP BY a.fecha ORDER BY a.fecha ASC"
        rows = await self.db.fetch_all(query, tuple(params))
        return [dict(row) for row in rows]
    async def save_cierre_periodo(self, data: Dict[str, Any]) -> int:
        """Registra un nuevo cierre de periodo en el historial"""
        query = """
            INSERT INTO cierres_periodos 
            (fecha_inicio, fecha_fin, usuario_id, username, tipo_cierre, comentarios, area, turno_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get('fecha_inicio'),
            data.get('fecha_fin'),
            data.get('usuario_id'),
            data.get('username'),
            data.get('tipo_cierre', 'RRHH'),
            data.get('comentarios'),
            data.get('area'),
            data.get('turno_id')
        )
        cursor = await self.db.execute(query, params)
        return cursor.lastrowid

    async def get_ultimo_cierre_periodo(self, tipo: str = 'RRHH') -> Optional[Dict[str, Any]]:
        """Obtiene el último periodo cerrado para sugerir el siguiente"""
        query = "SELECT * FROM cierres_periodos WHERE tipo_cierre = ? ORDER BY fecha_fin DESC LIMIT 1"
        return await self.db.fetch_one(query, (tipo,))

    async def get_cierres_historial(self, limit: int = 12) -> List[Dict[str, Any]]:
        """Obtiene al historial de cierres para la tabla de administración"""
        query = "SELECT * FROM cierres_periodos ORDER BY fecha_fin DESC LIMIT ?"
        return await self.db.fetch_all(query, (limit,))

    async def get_cierres_bulk(self, fecha_inicio: str, fecha_fin: str) -> List[Dict[str, Any]]:
        """
        Obtiene todos los cierres que intersectan un rango de fechas.
        Optimización para evitar consultas N+1 en procesamiento masivo.
        """
        query = "SELECT * FROM cierres_periodos WHERE fecha_inicio <= ? AND fecha_fin >= ?"
        return await self.db.fetch_all(query, (fecha_fin, fecha_inicio))

    async def check_fecha_cerrada(self, fecha: str, empleado_id: int = None) -> bool:
        """
        Verifica si una fecha pertenece a un periodo cerrado.
        Si se provee empleado_id, valida específicamente si SU segmento está cerrado.
        """
        if not empleado_id:
            query = "SELECT COUNT(*) as count FROM cierres_periodos WHERE ? BETWEEN fecha_inicio AND fecha_fin"
            res = await self.db.fetch_one(query, (fecha,))
            return res['count'] > 0 if res else False

        # Caso Específico por Empleado (Verifica Área y Turno en esa fecha)
        query = """
            SELECT COUNT(*) as count 
            FROM cierres_periodos cp
            WHERE ? BETWEEN cp.fecha_inicio AND cp.fecha_fin
            AND (
                cp.area IS NULL 
                OR cp.area = (
                    SELECT a_table.nombre FROM historial_areas h 
                    LEFT JOIN areas a_table ON h.area_id = a_table.id
                    WHERE h.empleado_id = ? 
                    AND ? BETWEEN h.fecha_desde AND COALESCE(h.fecha_hasta, '2099-12-31')
                    LIMIT 1
                )
            )
            AND (
                cp.turno_id IS NULL
                OR cp.turno_id = (
                    SELECT a.turno_asignado_id FROM asistencias a
                    WHERE a.empleado_id = ? AND a.fecha = ?
                    LIMIT 1
                )
            )
        """
        res = await self.db.fetch_one(query, (fecha, empleado_id, fecha, empleado_id, fecha))
        return res['count'] > 0 if res else False

    async def check_rango_cerrado(self, fecha_inicio: str, fecha_fin: str, empleado_id: int = None) -> bool:
        """
        Verifica si un rango de fechas se superpone con un periodo cerrado.
        Si se provee empleado_id, valida específicamente si SU segmento está cerrado.
        """
        if not empleado_id:
            query = "SELECT COUNT(*) as count FROM cierres_periodos WHERE fecha_inicio <= ? AND fecha_fin >= ?"
            res = await self.db.fetch_one(query, (fecha_fin, fecha_inicio))
            return res['count'] > 0 if res else False

        # Caso Específico por Empleado (Verifica Área y Turno)
        query = """
            SELECT COUNT(*) as count 
            FROM cierres_periodos cp
            WHERE cp.fecha_inicio <= ? AND cp.fecha_fin >= ?
            AND (
                cp.area IS NULL 
                OR cp.area = (
                    SELECT a_table.nombre FROM historial_areas h 
                    LEFT JOIN areas a_table ON h.area_id = a_table.id
                    WHERE h.empleado_id = ? 
                    AND cp.fecha_fin >= h.fecha_desde AND cp.fecha_inicio <= COALESCE(h.fecha_hasta, '2099-12-31')
                    LIMIT 1
                )
            )
            AND (
                cp.turno_id IS NULL
                OR cp.turno_id IN (
                    SELECT DISTINCT a.turno_id FROM asignacion_turnos a
                    WHERE a.empleado_id = ? 
                    AND a.fecha_inicio <= ? AND (a.fecha_fin IS NULL OR a.fecha_fin >= ?)
                )
            )
        """
        res = await self.db.fetch_one(query, (fecha_fin, fecha_inicio, empleado_id, empleado_id, fecha_fin, fecha_inicio))
        return res['count'] > 0 if res else False

    async def delete_before_date(self, empleado_id: int, start_date: date) -> int:
        """Elimina todos los registros de asistencia de un empleado anteriores a una fecha específica"""
        query = "DELETE FROM asistencias WHERE empleado_id = ? AND fecha < ?"
        cursor = await self.db.execute(query, [empleado_id, start_date.isoformat()])
        return cursor.rowcount
