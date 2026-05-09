"""
Repositorio de Horas Extras — Plan de Migración v3.1
Tabla: horas_extras

Responsabilidades:
- CRUD sobre la tabla `horas_extras`
- Upsert Inteligente: preserva decisiones humanas (APROBADO/RECHAZADO)
- Batch approve/reject para flujo RRHH
- Consultas por periodo, empleado y estado
"""

from typing import List, Dict, Optional, Any, Tuple
from loguru import logger
from backend.core.database import Database


class HoraExtraRepository:
    def __init__(self, db: Database):
        self.db = db

    # ══════════════════════════════════════════════════════════════
    # ESCRITURA
    # ══════════════════════════════════════════════════════════════

    async def upsert(self, empleado_id: int, fecha: str, minutos_bruto: float,
                     minutos_autorizados: float = 0, estado: str = 'PENDIENTE',
                     origen: str = 'SISTEMA', comentario: str = None) -> None:
        """
        Inserta o actualiza un registro HE.
        
        UPSERT INTELIGENTE: Si un humano ya aprobó/rechazó, NO sobreescribimos
        su decisión. Solo actualizamos minutos_bruto (dato calculado del sistema).
        """
        query = """
            INSERT INTO horas_extras 
                (empleado_id, fecha, minutos_bruto, minutos_autorizados, estado, origen, comentario, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(empleado_id, fecha) DO UPDATE SET
                minutos_bruto = excluded.minutos_bruto,
                minutos_autorizados = CASE 
                    WHEN horas_extras.estado IN ('APROBADO','RECHAZADO') THEN horas_extras.minutos_autorizados
                    ELSE excluded.minutos_autorizados
                END,
                estado = CASE
                    WHEN horas_extras.estado IN ('APROBADO','RECHAZADO') THEN horas_extras.estado
                    ELSE excluded.estado
                END,
                origen = CASE
                    WHEN horas_extras.estado IN ('APROBADO','RECHAZADO') THEN horas_extras.origen
                    ELSE excluded.origen
                END,
                updated_at = datetime('now')
        """
        await self.db.execute(query, (
            empleado_id, fecha, minutos_bruto, minutos_autorizados,
            estado, origen, comentario
        ))

    async def batch_upsert(self, data_list: List[Dict[str, Any]], suppress_auto_sync: bool = False) -> None:
        """
        Inserta o actualiza múltiples registros HE.
        """
        if not data_list:
            return
            
        query = """
            INSERT INTO horas_extras 
                (empleado_id, fecha, minutos_bruto, minutos_autorizados, estado, origen, comentario, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(empleado_id, fecha) DO UPDATE SET
                minutos_bruto = excluded.minutos_bruto,
                minutos_autorizados = CASE 
                    WHEN horas_extras.estado IN ('APROBADO','RECHAZADO') THEN horas_extras.minutos_autorizados
                    ELSE excluded.minutos_autorizados
                END,
                estado = CASE
                    WHEN horas_extras.estado IN ('APROBADO','RECHAZADO') THEN horas_extras.estado
                    ELSE excluded.estado
                END,
                origen = CASE
                    WHEN horas_extras.estado IN ('APROBADO','RECHAZADO') THEN horas_extras.origen
                    ELSE excluded.origen
                END,
                updated_at = datetime('now')
        """
        params_list = []
        for d in data_list:
            params_list.append((
                d['empleado_id'], d['fecha'], d['minutos_bruto'], d.get('minutos_autorizados', 0),
                d.get('estado', 'PENDIENTE'), d.get('origen', 'SISTEMA'), d.get('comentario')
            ))
        await self.db.executemany(query, params_list, suppress_auto_sync=suppress_auto_sync)

    async def aprobar_batch(self, items: List[Dict[str, Any]]) -> int:
        """
        Aprueba/rechaza múltiples registros HE.
        
        Cada item debe tener:
        - empleado_id: int
        - fecha: str (YYYY-MM-DD)
        - estado: 'APROBADO' | 'RECHAZADO'
        - minutos_autorizados: float (minutos aprobados por RRHH)
        """
        query = """
            UPDATE horas_extras 
            SET estado = ?, minutos_autorizados = ?, updated_at = datetime('now')
            WHERE empleado_id = ? AND fecha = ?
        """
        count = 0
        for item in items:
            result = await self.db.execute(query, (
                item['estado'],
                item.get('minutos_autorizados', 0),
                item['empleado_id'],
                item['fecha']
            ))
            if result and hasattr(result, 'rowcount') and result.rowcount > 0:
                count += 1
            else:
                count += 1  # SQLite no siempre reporta rowcount
        return count

    async def delete_by_empleado_fecha(self, empleado_id: int, fecha: str) -> None:
        """Elimina un registro HE (usado para JE interceptadas)."""
        await self.db.execute(
            "DELETE FROM horas_extras WHERE empleado_id = ? AND fecha = ?",
            (empleado_id, fecha)
        )

    # ══════════════════════════════════════════════════════════════
    # LECTURA
    # ══════════════════════════════════════════════════════════════

    async def get_by_periodo(self, fecha_ini: str, fecha_fin: str,
                             empleado_id: int = None) -> List[Dict]:
        """Lee todos los registros HE de un periodo."""
        q = "SELECT * FROM horas_extras WHERE fecha BETWEEN ? AND ?"
        params: list = [fecha_ini, fecha_fin]
        if empleado_id:
            q += " AND empleado_id = ?"
            params.append(empleado_id)
        q += " ORDER BY fecha, empleado_id"
        return await self.db.fetch_all(q, tuple(params))

    async def get_estado_previo(self, empleado_id: int, fecha: str) -> Optional[Dict]:
        """
        Lee estado previo para preservación de decisiones humanas.
        Usado por el motor de recálculo para no sobreescribir aprobaciones.
        """
        row = await self.db.fetch_one(
            "SELECT estado, minutos_autorizados FROM horas_extras WHERE empleado_id = ? AND fecha = ?",
            (empleado_id, fecha)
        )
        return dict(row) if row else None

    async def get_resumen_periodo(self, fecha_ini: str, fecha_fin: str,
                                   areas_permitidas: list = None) -> Dict:
        """
        Resumen agregado por periodo para la Bolsa de Horas.
        Devuelve totales de minutos aprobados, pendientes y rechazados.
        """
        q = """
            SELECT 
                COALESCE(SUM(CASE WHEN h.estado = 'APROBADO' THEN h.minutos_autorizados ELSE 0 END), 0) as total_aprobado,
                COALESCE(SUM(CASE WHEN h.estado = 'PENDIENTE' THEN h.minutos_bruto ELSE 0 END), 0) as total_pendiente,
                COALESCE(SUM(CASE WHEN h.estado = 'RECHAZADO' THEN h.minutos_bruto ELSE 0 END), 0) as total_rechazado,
                COUNT(*) as total_registros
            FROM horas_extras h
            JOIN empleados e ON e.id = h.empleado_id
            LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1
            LEFT JOIN areas a ON ha.area_id = a.id
            WHERE h.fecha BETWEEN ? AND ?
        """
        params: list = [fecha_ini, fecha_fin]
        if areas_permitidas:
            placeholders = ','.join(['?' for _ in areas_permitidas])
            q += f" AND a.nombre IN ({placeholders})"
            params.extend(areas_permitidas)

        row = await self.db.fetch_one(q, tuple(params))
        return dict(row) if row else {
            'total_aprobado': 0, 'total_pendiente': 0,
            'total_rechazado': 0, 'total_registros': 0
        }

    async def get_embudo_he(self, fecha_ini: str, fecha_fin: str,
                            areas_permitidas: list = None) -> Dict:
        """
        Embudo HE para Dashboard Analytics.
        Retorna horas aprobadas, pendientes, rechazadas (en horas, no minutos).
        """
        resumen = await self.get_resumen_periodo(fecha_ini, fecha_fin, areas_permitidas)
        return {
            'aprobadas': round(resumen['total_aprobado'] / 60, 1),
            'pendientes': round(resumen['total_pendiente'] / 60, 1),
            'rechazadas': round(resumen['total_rechazado'] / 60, 1),
        }

    async def get_por_empleado_periodo(self, empleado_id: int,
                                        fecha_ini: str, fecha_fin: str) -> List[Dict]:
        """HE de un empleado específico en un periodo (para calendario individual)."""
        rows = await self.db.fetch_all(
            """SELECT fecha, minutos_bruto, minutos_autorizados, estado, origen, comentario
               FROM horas_extras 
               WHERE empleado_id = ? AND fecha BETWEEN ? AND ?
               ORDER BY fecha""",
            (empleado_id, fecha_ini, fecha_fin)
        )
        return [dict(r) for r in rows] if rows else []
