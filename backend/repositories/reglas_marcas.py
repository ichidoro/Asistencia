"""
Repositorio de las Reglas de marcaciones (pestaña de Configuración).

Etapa 1: la tabla y su pantalla. El motor de cálculo TODAVÍA NO lee esta tabla:
todas las reglas nacen apagadas (activa = 0) y el botón «Correr esta regla»
se habilitará en la etapa siguiente, regla por regla, solo sobre el tramo
abierto y las áreas abiertas. Los períodos cerrados no se tocan.
"""
import json
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.core.database import Database
from backend.services.reglas_marcas_def import filas_semilla, validar_regla

CLAVE_REBOTE = 'reglas_marcas_rebote_segundos'
DESCRIPCION_REBOTE = ('Reglas de marcaciones: segundos entre dos marcas para considerarlas '
                      'un doble toque (rebote). Todavía no conectado al cálculo.')

# La cuenta de jornadas por secuencia recorre todo el historial: se guarda 10 minutos.
_CONTEOS_TTL = 600.0
_conteos_cache: Dict[str, Any] = {}


class ReglasMarcasRepository:

    def __init__(self, db: Database):
        self.db = db

    async def init_tables(self):
        if not await self.db.table_exists("reglas_marcas"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS reglas_marcas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo_horario TEXT NOT NULL,
                    secuencia TEXT NOT NULL,
                    lectura TEXT NOT NULL,
                    colacion TEXT NOT NULL,
                    accion TEXT NOT NULL,
                    opciones_revision TEXT DEFAULT '[]',
                    activa INTEGER DEFAULT 0,
                    nota TEXT,
                    updated_by TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (tipo_horario, secuencia)
                )
            """)
        # Semilla idempotente: nunca pisa lo que el dueño ya editó.
        try:
            await self.db.executemany(
                """INSERT OR IGNORE INTO reglas_marcas
                   (tipo_horario, secuencia, lectura, colacion, accion, opciones_revision, activa, nota)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                filas_semilla()
            )
        except Exception as e:
            logger.warning(f"Semilla reglas_marcas: {e}")
        try:
            await self.db.execute(
                "INSERT OR IGNORE INTO ajustes (clave, valor, descripcion) VALUES (?, ?, ?)",
                (CLAVE_REBOTE, '180', DESCRIPCION_REBOTE)
            )
        except Exception as e:
            logger.warning(f"Semilla ajuste rebote: {e}")

    # ── Lectura ──────────────────────────────────────────────────────────────

    async def tipos_horario(self) -> List[Dict[str, Any]]:
        """Tipos de horario reales (salen de los turnos, no de un catálogo)."""
        rows = await self.db.fetch_all("""
            SELECT t.tipo_programacion AS tipo,
                   COUNT(*) AS turnos,
                   (SELECT COUNT(DISTINCT a.empleado_id) FROM asignacion_turnos a
                     JOIN turnos x ON x.id = a.turno_id
                    WHERE x.tipo_programacion = t.tipo_programacion
                      AND (a.fecha_fin IS NULL OR a.fecha_fin >= date('now', '-30 days'))) AS personas
            FROM turnos t GROUP BY t.tipo_programacion ORDER BY 2 DESC
        """)
        return [dict(r) for r in rows]

    async def listar(self, tipo_horario: str) -> List[Dict[str, Any]]:
        rows = await self.db.fetch_all(
            "SELECT * FROM reglas_marcas WHERE tipo_horario = ? ORDER BY id",
            (tipo_horario,)
        )
        out = []
        for r in rows:
            d = dict(r)
            try:
                d['opciones_revision'] = json.loads(d.get('opciones_revision') or '[]')
            except Exception:
                d['opciones_revision'] = []
            out.append(d)
        return out

    async def obtener(self, regla_id: int) -> Optional[Dict[str, Any]]:
        r = await self.db.fetch_one("SELECT * FROM reglas_marcas WHERE id = ?", (regla_id,))
        if not r:
            return None
        d = dict(r)
        try:
            d['opciones_revision'] = json.loads(d.get('opciones_revision') or '[]')
        except Exception:
            d['opciones_revision'] = []
        return d

    async def rebote_segundos(self) -> int:
        r = await self.db.fetch_one("SELECT valor FROM ajustes WHERE clave = ?", (CLAVE_REBOTE,))
        try:
            return int(float(r['valor'])) if r else 180
        except Exception:
            return 180

    async def inicio_tramo_abierto(self) -> str:
        """Primer día del tramo de cierre que sigue abierto (si no hay, últimos 30 días)."""
        try:
            r = await self.db.fetch_one(
                "SELECT MIN(fecha_inicio) AS d FROM periodos_rrhh WHERE COALESCE(estado,'') != 'cerrado'"
            )
            if r and r.get('d'):
                return str(r['d'])[:10]
        except Exception as e:
            logger.warning(f"inicio_tramo_abierto: {e}")
        r2 = await self.db.fetch_one("SELECT date('now', '-30 days') AS d")
        return str(r2['d'])[:10]

    async def conteos(self, tipo_horario: str, desde_abierto: str) -> Dict[str, Any]:
        """Jornadas por secuencia (historial completo y tramo abierto), como las ve el
        motor: las marcas que cada día consumió, sin días con marcas manuales."""
        clave = f"{tipo_horario}|{desde_abierto}"
        hit = _conteos_cache.get(clave)
        if hit and (time.monotonic() - hit[0]) < _CONTEOS_TTL:
            return hit[1]
        rows = await self.db.fetch_all("""
            WITH ci AS (SELECT id FROM turnos WHERE tipo_programacion = ?),
            a AS (SELECT a.id AS aid, a.fecha, a.marcas_consumidas_ids AS ids
                    FROM asistencias a
                   WHERE a.turno_asignado_id IN (SELECT id FROM ci)
                     AND a.horas_teoricas > 0
                     AND a.marcas_consumidas_ids ~ '^\\[ *[0-9]'),
            x AS (SELECT a.aid, a.fecha, l.fecha_hora, COALESCE(l.manual, 0) AS man,
                         CASE WHEN LOWER(COALESCE(o.tipo, l.tipo)) IN ('entrada','entry','e','in','1') THEN 'E'
                              WHEN LOWER(COALESCE(o.tipo, l.tipo)) IN ('salida','exit','s','out','0','2') THEN 'S'
                              ELSE '?' END AS t
                    FROM a
                   CROSS JOIN LATERAL jsonb_array_elements_text(a.ids::jsonb) j(v)
                    JOIN logs_raw l ON l.id = j.v::bigint
                    LEFT JOIN logs_tipo_override o ON o.log_id = l.id),
            d AS (SELECT aid, fecha, STRING_AGG(t, '' ORDER BY fecha_hora) AS pat,
                         SUM(man) AS manuales
                    FROM x GROUP BY aid, fecha)
            SELECT pat, COUNT(*) AS dias,
                   COUNT(*) FILTER (WHERE fecha >= ?) AS dias_abiertos
              FROM d WHERE manuales = 0 GROUP BY pat
        """, (tipo_horario, desde_abierto))
        por_sec = {r['pat']: {'dias': int(r['dias']), 'dias_abiertos': int(r['dias_abiertos'])}
                   for r in rows}
        total = sum(v['dias'] for v in por_sec.values())
        total_abiertos = sum(v['dias_abiertos'] for v in por_sec.values())
        data = {'por_secuencia': por_sec, 'total': total, 'total_abiertos': total_abiertos}
        _conteos_cache[clave] = (time.monotonic(), data)
        return data

    async def dias_de_secuencia(self, tipo_horario: str, secuencia: str,
                                desde_abierto: str) -> List[Dict[str, Any]]:
        """Los días del tramo abierto cuya secuencia es exactamente esta (solo lectura)."""
        rows = await self.db.fetch_all("""
            WITH ci AS (SELECT id FROM turnos WHERE tipo_programacion = ?),
            a AS (SELECT a.id AS aid, a.empleado_id, a.fecha, a.estado, a.horas_trabajadas,
                         a.minutos_deuda, a.marcas_consumidas_ids AS ids
                    FROM asistencias a
                   WHERE a.turno_asignado_id IN (SELECT id FROM ci)
                     AND a.horas_teoricas > 0 AND a.fecha >= ?
                     AND a.marcas_consumidas_ids ~ '^\\[ *[0-9]'),
            x AS (SELECT a.aid, a.empleado_id, a.fecha, a.estado, a.horas_trabajadas,
                         a.minutos_deuda, l.fecha_hora, COALESCE(l.manual, 0) AS man,
                         CASE WHEN LOWER(COALESCE(o.tipo, l.tipo)) IN ('entrada','entry','e','in','1') THEN 'E'
                              WHEN LOWER(COALESCE(o.tipo, l.tipo)) IN ('salida','exit','s','out','0','2') THEN 'S'
                              ELSE '?' END AS t
                    FROM a
                   CROSS JOIN LATERAL jsonb_array_elements_text(a.ids::jsonb) j(v)
                    JOIN logs_raw l ON l.id = j.v::bigint
                    LEFT JOIN logs_tipo_override o ON o.log_id = l.id),
            d AS (SELECT aid, empleado_id, fecha, estado, horas_trabajadas, minutos_deuda,
                         STRING_AGG(t, '' ORDER BY fecha_hora) AS pat, SUM(man) AS manuales,
                         STRING_AGG(SUBSTR(fecha_hora, 12, 8) || ' ' ||
                                    CASE t WHEN 'E' THEN 'Ent' ELSE 'Sal' END,
                                    ' · ' ORDER BY fecha_hora) AS marcas
                    FROM x
                   GROUP BY aid, empleado_id, fecha, estado, horas_trabajadas, minutos_deuda)
            SELECT e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS persona,
                   d.fecha, d.estado, ROUND(d.horas_trabajadas::numeric, 2) AS horas,
                   ROUND(d.minutos_deuda::numeric, 0) AS deuda, d.marcas
              FROM d JOIN empleados e ON e.id = d.empleado_id
             WHERE d.pat = ? AND d.manuales = 0
             ORDER BY d.fecha, persona
        """, (tipo_horario, desde_abierto, secuencia))
        return [dict(r) for r in rows]

    # ── Escritura ────────────────────────────────────────────────────────────

    async def actualizar(self, regla_id: int, cambios: Dict[str, Any],
                         username: str) -> Dict[str, Any]:
        """Actualiza una regla. Devuelve {'error': ...} o {'antes': ..., 'despues': ...}."""
        actual = await self.obtener(regla_id)
        if not actual:
            return {'error': 'La regla no existe.'}
        if cambios.get('activa') not in (None, actual.get('activa')):
            return {'error': 'Las reglas se encienden y apagan con «Correr esta regla» '
                             'y «Apagar esta regla», no desde aquí.'}
        if actual.get('activa'):
            return {'error': 'Esta regla está encendida y el motor la está usando: '
                             'apáguela antes de cambiarla, para que el cambio corra con su propio antes y después.'}
        nueva = {
            'secuencia': actual['secuencia'],
            'lectura': cambios.get('lectura', actual['lectura']),
            'colacion': cambios.get('colacion', actual['colacion']),
            'accion': cambios.get('accion', actual['accion']),
            'opciones_revision': cambios.get('opciones_revision', actual['opciones_revision']),
        }
        motivo = validar_regla(nueva)
        if motivo:
            return {'error': motivo}
        nota = cambios.get('nota', actual.get('nota'))
        await self.db.execute(
            """UPDATE reglas_marcas
                  SET lectura = ?, colacion = ?, accion = ?, opciones_revision = ?,
                      nota = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
            (nueva['lectura'], nueva['colacion'], nueva['accion'],
             json.dumps(nueva['opciones_revision']), nota, username, regla_id)
        )
        despues = await self.obtener(regla_id)
        return {'antes': actual, 'despues': despues}

    async def guardar_rebote(self, segundos: int) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO ajustes (clave, valor, descripcion) VALUES (?, ?, ?)",
            (CLAVE_REBOTE, str(segundos), DESCRIPCION_REBOTE)
        )
        await self.db.execute(
            "UPDATE ajustes SET valor = ?, updated_at = CURRENT_TIMESTAMP WHERE clave = ?",
            (str(segundos), CLAVE_REBOTE)
        )
