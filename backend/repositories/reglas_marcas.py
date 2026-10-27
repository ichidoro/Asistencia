"""
Repositorio de las Reglas de marcaciones (pestaña de Configuración).

Las reglas viven en la tabla `reglas_marcas` y se crean y configuran desde la
pantalla: el código no trae ninguna lista de secuencias. Una regla nueva nace
apagada (activa = 0) y se enciende con «Correr esta regla», que recalcula solo
el tramo abierto y las áreas abiertas. Los períodos cerrados no se tocan.
Los valores que ajustan el cálculo (rebote, marcas repetidas, colación de
referencia, minutos para «no calza con ningún ciclo») son filas de `ajustes`
que se cambian desde la misma pestaña.
"""
import json
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.core.database import Database
from backend.services.reglas_marcas_def import (
    MARCA_REVISION_REGLA, firma_marcas, numerar_sin_numero, secuencia_en_revision, validar_regla,
)

CLAVE_REBOTE = 'reglas_marcas_rebote_segundos'
DESCRIPCION_REBOTE = ('Reglas de marcaciones: segundos entre dos marcas para considerarlas '
                      'un doble toque (rebote). Solo Ciclo Inteligente; el redondeo propio '
                      'de un turno manda sobre este valor.')
CLAVE_COLACION_MIN = 'reglas_marcas_colacion_min_minutos'
CLAVE_COLACION_MAX = 'reglas_marcas_colacion_max_minutos'
CLAVE_REPETIDAS = 'reglas_marcas_repetidas_minutos'
CLAVE_COLACION_REFERENCIA = 'reglas_marcas_colacion_referencia_minutos'

# Ajustes que la pestaña deja cambiar: clave → (descripción, mínimo, máximo).
# El valor de cada uno vive en la tabla `ajustes`, no aquí.
AJUSTES_EDITABLES = {
    CLAVE_REBOTE: ('Segundos entre dos marcas para considerarlas un doble toque (rebote).', 0, 1800),
    CLAVE_REPETIDAS: ('Minutos entre dos ENTRADAS o dos SALIDAS seguidas para juntarlas en una '
                      '(se queda la primera ENTRADA o la última SALIDA).', 0, 240),
    CLAVE_COLACION_REFERENCIA: ('Minutos de colación de referencia para elegir cuál pausa es la colación '
                                'cuando el horario no tiene colación configurada.', 0, 240),
}

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
        # La opción «avisar si las marcas no calzan con ningún ciclo del horario» y sus minutos se quitaron (27-10-2026):
        # esos días se calculan solos (salida adelantada solo si salió antes más de lo que llegó antes). Estaba apagada en todas.
        try:
            if 'avisa_fuera_de_ciclo' in set(await self.db.get_column_names("reglas_marcas")):
                await self.db.execute("ALTER TABLE reglas_marcas DROP COLUMN avisa_fuera_de_ciclo")
                await self.db.execute("DELETE FROM ajustes WHERE clave = 'reglas_marcas_fuera_ciclo_minutos'")
                logger.info("[Migration] Opción de ciclos quitada de las reglas de marcaciones")
        except Exception as e:
            logger.warning(f"Quitar la opción de ciclos de las reglas: {e}")
        # «¿Cuál pausa es la colación?» (por regla; solo se pregunta cuando el día tiene dos pausas o más).
        # Parte en la forma de siempre (PARECIDA): ninguna regla cambia hasta que alguien elija otra cosa.
        try:
            if 'eleccion_colacion' not in set(await self.db.get_column_names("reglas_marcas")):
                await self.db.execute("ALTER TABLE reglas_marcas ADD COLUMN eleccion_colacion TEXT DEFAULT 'PARECIDA'")
        except Exception as e:
            logger.warning(f"Columna eleccion_colacion: {e}")
        # Número de cada regla («Regla N»): se guarda una vez en el orden de la pantalla y no se mueve.
        try:
            if 'numero' not in set(await self.db.get_column_names("reglas_marcas")):
                await self.db.execute("ALTER TABLE reglas_marcas ADD COLUMN numero INTEGER")
            filas = [dict(r) for r in await self.db.fetch_all(
                "SELECT id, tipo_horario, secuencia, numero FROM reglas_marcas")]
            for tipo in sorted({f['tipo_horario'] for f in filas}):
                del_tipo = [f for f in filas if f['tipo_horario'] == tipo]
                ultimo = max([f['numero'] or 0 for f in del_tipo] + [0])
                for rid, numero in numerar_sin_numero(del_tipo, ultimo).items():
                    await self.db.execute("UPDATE reglas_marcas SET numero = ? WHERE id = ?", (numero, rid))
        except Exception as e:
            logger.warning(f"Número de las reglas: {e}")
        # Valor inicial de cada ajuste de la pestaña (solo si la fila no existe: lo que
        # se configure desde la pantalla nunca se pisa). El cálculo los lee de `ajustes`.
        try:
            await self.db.executemany(
                "INSERT OR IGNORE INTO ajustes (clave, valor, descripcion) VALUES (?, ?, ?)",
                [
                    (CLAVE_REBOTE, '180', DESCRIPCION_REBOTE),
                    (CLAVE_COLACION_MIN, '20',
                     'Reglas de marcaciones: minutos mínimos de una pausa para que la pantalla la señale como colación.'),
                    (CLAVE_COLACION_MAX, '150',
                     'Reglas de marcaciones: minutos máximos de una pausa para que la pantalla la señale como colación.'),
                    (CLAVE_REPETIDAS, '20', 'Reglas de marcaciones: ' + AJUSTES_EDITABLES[CLAVE_REPETIDAS][0]),
                    (CLAVE_COLACION_REFERENCIA, '60', 'Reglas de marcaciones: ' + AJUSTES_EDITABLES[CLAVE_COLACION_REFERENCIA][0]),
                ]
            )
        except Exception as e:
            logger.warning(f"Valores iniciales de los ajustes de reglas: {e}")
        # Confirmaciones de «Días por revisar»: quién miró un día en revisión y lo dio
        # por bueno. Vale mientras las marcas del día no cambien (la firma coincide).
        if not await self.db.table_exists("revisiones_marcas"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS revisiones_marcas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    fecha TEXT NOT NULL,
                    secuencia TEXT,
                    firma TEXT NOT NULL,
                    usuario_id INTEGER,
                    username TEXT,
                    motivo TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (empleado_id, fecha, firma)
                )
            """)

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
            "SELECT * FROM reglas_marcas WHERE tipo_horario = ? ORDER BY numero, id",
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

    async def dias_ejemplo(self, tipo_horario: str, secuencia: str, desde_abierto: str,
                           hoy: str, limite: int = 3) -> List[Dict[str, Any]]:
        """Los días de ejemplo del asistente: los más recientes del tramo abierto con
        esta secuencia (jornadas terminadas, marcas del reloj sin manuales, nunca días
        cubiertos por un cierre). Cada fila trae además `total`: cuántos días hay."""
        rows = await self.db.fetch_all("""
            WITH ci AS (SELECT id FROM turnos WHERE tipo_programacion = ?),
            a AS (SELECT a.id AS aid, a.empleado_id, a.fecha, a.turno_asignado_id,
                         a.estado, a.horas_trabajadas, a.marcas_consumidas_ids AS ids
                    FROM asistencias a
                   WHERE a.turno_asignado_id IN (SELECT id FROM ci)
                     AND a.horas_teoricas > 0 AND a.fecha >= ? AND a.fecha < ?
                     AND a.marcas_consumidas_ids ~ '^\\[ *[0-9]'),
            x AS (SELECT a.aid, a.empleado_id, a.fecha, a.turno_asignado_id, a.estado,
                         a.horas_trabajadas, l.fecha_hora, COALESCE(l.manual, 0) AS man,
                         CASE WHEN LOWER(COALESCE(o.tipo, l.tipo)) IN ('entrada','entry','e','in','1') THEN 'E'
                              WHEN LOWER(COALESCE(o.tipo, l.tipo)) IN ('salida','exit','s','out','0','2') THEN 'S'
                              ELSE '?' END AS t
                    FROM a
                   CROSS JOIN LATERAL jsonb_array_elements_text(a.ids::jsonb) j(v)
                    JOIN logs_raw l ON l.id = j.v::bigint
                    LEFT JOIN logs_tipo_override o ON o.log_id = l.id),
            d AS (SELECT aid, empleado_id, fecha, turno_asignado_id, estado, horas_trabajadas,
                         STRING_AGG(t, '' ORDER BY fecha_hora) AS pat, SUM(man) AS manuales,
                         STRING_AGG(SUBSTR(fecha_hora, 12, 8) || ' ' ||
                                    CASE t WHEN 'E' THEN 'Ent' ELSE 'Sal' END,
                                    ' · ' ORDER BY fecha_hora) AS marcas,
                         STRING_AGG(SUBSTR(fecha_hora, 1, 19) || '|' || t, ',' ORDER BY fecha_hora) AS marcas_completas
                    FROM x
                   GROUP BY aid, empleado_id, fecha, turno_asignado_id, estado, horas_trabajadas)
            SELECT d.empleado_id,
                   e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS persona,
                   d.fecha, d.estado, ROUND(d.horas_trabajadas::numeric, 2) AS horas, d.marcas,
                   d.marcas_completas, tu.nombre AS horario,
                   z.hora_entrada_teorica, z.hora_salida_teorica, z.horas_teoricas,
                   z.minutos_colacion, z.minutos_colacion_real, z.minutos_exceso_colacion,
                   z.minutos_atraso, z.minutos_salida_adelantada, z.minutos_deuda, z.minutos_extra_bruto,
                   z.hora_salida_colacion, z.hora_entrada_colacion, z.minutos_permisos_detectados,
                   tu.umbral_horas_colacion,
                   COUNT(*) OVER () AS total
              FROM d JOIN empleados e ON e.id = d.empleado_id
              JOIN asistencias z ON z.id = d.aid
              LEFT JOIN turnos tu ON tu.id = z.turno_asignado_id
             WHERE d.pat = ? AND d.manuales = 0
               AND NOT EXISTS (
                    SELECT 1 FROM cierres_periodos cp
                     WHERE cp.fecha_inicio <= d.fecha AND cp.fecha_fin >= d.fecha
                       AND (cp.area IS NULL OR cp.turno_id = d.turno_asignado_id
                            OR cp.area = (SELECT ar.nombre FROM historial_areas h
                                            LEFT JOIN areas ar ON ar.id = h.area_id
                                           WHERE h.empleado_id = d.empleado_id
                                             AND d.fecha BETWEEN h.fecha_desde AND COALESCE(h.fecha_hasta, '2099-12-31')
                                           LIMIT 1)))
             ORDER BY d.fecha DESC, persona
             LIMIT ?
        """, (tipo_horario, desde_abierto, hoy, secuencia, limite))
        return [dict(r) for r in rows]

    async def horarios(self, tipo_horario: str) -> List[Dict[str, Any]]:
        """Los horarios de este tipo con lo que usan las reglas (colación, mínimo de
        horas, tolerancia de exceso, márgenes y ciclos). Todo sale de Configuración →
        Horarios: la pestaña de reglas solo lo muestra."""
        rows = await self.db.fetch_all("""
            SELECT t.id, t.nombre, t.descuento_colacion_auto, t.minutos_colacion_auto,
                   t.umbral_horas_colacion, t.tolerancia_exceso_colacion_minutos,
                   t.anclaje_entrada_minutos, t.anclaje_salida_minutos, t.rotacion_dinamica_diaria,
                   (SELECT STRING_AGG(DISTINCT SUBSTR(CAST(d.hora_entrada AS TEXT), 1, 5) || '–' ||
                                      SUBSTR(CAST(d.hora_salida AS TEXT), 1, 5) ||
                                      COALESCE(' ' || NULLIF(d.etiqueta_bloque, ''), ''), ' · ')
                      FROM turno_dias d
                     WHERE d.turno_id = t.id AND d.hora_entrada IS NOT NULL
                       AND COALESCE(CAST(d.es_libre AS INTEGER), 0) = 0) AS ciclos
              FROM turnos t
             WHERE t.tipo_programacion = ? AND COALESCE(CAST(t.activo AS INTEGER), 1) = 1
             ORDER BY t.nombre
        """, (tipo_horario,))
        return [dict(r) for r in rows]

    async def cortes_colacion(self, tipo_horario: str) -> List[Dict[str, Any]]:
        """Hora de corte de cada horario y ciclo (ENTRADA + «Mínimo para descontar») y, para saber si ese mínimo
        sirve como corte, cuántas colaciones reales terminan antes: se cuentan los días de 4 marcas, donde la única
        pausa es la colación. Todo sale de Horarios y de los días guardados; aquí no hay ningún número propio."""
        rows = await self.db.fetch_all("""
            WITH t AS (SELECT id, nombre, COALESCE(umbral_horas_colacion, 0) AS umbral FROM turnos
                        WHERE tipo_programacion = ? AND COALESCE(CAST(activo AS INTEGER), 1) = 1),
            e AS (SELECT DISTINCT d.turno_id, SUBSTR(CAST(d.hora_entrada AS TEXT), 1, 5) AS entrada
                    FROM turno_dias d JOIN t ON t.id = d.turno_id
                   WHERE d.hora_entrada IS NOT NULL AND CAST(d.hora_entrada AS TEXT) <> ''
                     AND COALESCE(CAST(d.es_libre AS INTEGER), 0) = 0),
            c AS (SELECT a.turno_asignado_id AS turno_id, SUBSTR(CAST(a.hora_entrada_teorica AS TEXT), 1, 5) AS entrada,
                         MOD(CAST(EXTRACT(EPOCH FROM (CAST(a.hora_entrada_colacion AS TIME) - CAST(a.hora_entrada_teorica AS TIME))) AS INTEGER) + 86400, 86400) AS seg_fin
                    FROM asistencias a JOIN t ON t.id = a.turno_asignado_id
                   WHERE a.hora_entrada_colacion IS NOT NULL AND a.hora_salida_colacion IS NOT NULL
                     AND a.hora_entrada_teorica IS NOT NULL AND a.marcas_consumidas_ids ~ '^\\[ *[0-9]'
                     AND jsonb_array_length(a.marcas_consumidas_ids::jsonb) = 4)
            SELECT t.id, t.nombre, t.umbral, e.entrada,
                   COUNT(c.seg_fin) AS colaciones,
                   COUNT(c.seg_fin) FILTER (WHERE c.seg_fin <= t.umbral * 3600) AS antes_del_corte
              FROM t JOIN e ON e.turno_id = t.id
              LEFT JOIN c ON c.turno_id = t.id AND c.entrada = e.entrada
             GROUP BY t.id, t.nombre, t.umbral, e.entrada
             ORDER BY t.nombre, e.entrada
        """, (tipo_horario,))
        return [dict(r) for r in rows]

    async def ajustes_reglas(self) -> Dict[str, Optional[float]]:
        """Valores actuales de los ajustes de la pestaña (None si la fila no existe)."""
        out: Dict[str, Optional[float]] = {}
        for clave in AJUSTES_EDITABLES:
            r = await self.db.fetch_one("SELECT valor FROM ajustes WHERE clave = ?", (clave,))
            try:
                out[clave] = float(r['valor']) if r and r.get('valor') not in (None, '') else None
            except (TypeError, ValueError):
                out[clave] = None
        return out

    async def guardar_ajuste(self, clave: str, valor: float) -> None:
        descripcion = 'Reglas de marcaciones: ' + AJUSTES_EDITABLES[clave][0]
        texto = str(int(valor)) if float(valor).is_integer() else str(valor)
        await self.db.execute(
            "INSERT OR IGNORE INTO ajustes (clave, valor, descripcion) VALUES (?, ?, ?)",
            (clave, texto, descripcion))
        await self.db.execute(
            "UPDATE ajustes SET valor = ?, updated_at = CURRENT_TIMESTAMP WHERE clave = ?",
            (texto, clave))

    async def ventana_colacion(self) -> Dict[str, int]:
        out = {'min': 20, 'max': 150}
        for clave, campo in ((CLAVE_COLACION_MIN, 'min'), (CLAVE_COLACION_MAX, 'max')):
            try:
                r = await self.db.fetch_one("SELECT valor FROM ajustes WHERE clave = ?", (clave,))
                if r and r.get('valor') is not None:
                    out[campo] = int(float(r['valor']))
            except Exception:
                pass
        return out

    # ── Días por revisar ─────────────────────────────────────────────────────
    # Un día está «por revisar» cuando sus observaciones traen el marcador que
    # escribe el motor y no existe una confirmación cuya firma (las marcas que el
    # día usó) siga coincidiendo. Siempre tramo abierto, nunca hoy, nunca días
    # cubiertos por un cierre de área, de turno o global.

    _SQL_POR_REVISAR = """
        SELECT a.empleado_id, a.fecha, a.estado,
               ROUND(a.horas_trabajadas::numeric, 2) AS horas,
               ROUND(a.minutos_deuda::numeric, 0) AS deuda,
               a.hora_entrada_real, a.hora_salida_real,
               a.observaciones, a.marcas_consumidas_ids,
               e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS persona,
               (SELECT ar.nombre FROM historial_areas h LEFT JOIN areas ar ON ar.id = h.area_id
                 WHERE h.empleado_id = a.empleado_id
                   AND a.fecha BETWEEN h.fecha_desde AND COALESCE(h.fecha_hasta, '2099-12-31')
                 LIMIT 1) AS area
          FROM asistencias a
          JOIN empleados e ON e.id = a.empleado_id
         WHERE a.fecha >= ? AND a.fecha < ?
           AND a.observaciones LIKE ?
           AND NOT EXISTS (
                SELECT 1 FROM revisiones_marcas rv
                 WHERE rv.empleado_id = a.empleado_id AND rv.fecha = a.fecha
                   AND rv.firma = (SELECT COALESCE(STRING_AGG(j.v, ',' ORDER BY j.v::bigint), '')
                                     FROM jsonb_array_elements_text(a.marcas_consumidas_ids::jsonb) j(v)))
           AND NOT EXISTS (
                SELECT 1 FROM cierres_periodos cp
                 WHERE cp.fecha_inicio <= a.fecha AND cp.fecha_fin >= a.fecha
                   AND (cp.area IS NULL OR cp.turno_id = a.turno_asignado_id
                        OR cp.area = (SELECT ar2.nombre FROM historial_areas h2
                                        LEFT JOIN areas ar2 ON ar2.id = h2.area_id
                                       WHERE h2.empleado_id = a.empleado_id
                                         AND a.fecha BETWEEN h2.fecha_desde AND COALESCE(h2.fecha_hasta, '2099-12-31')
                                       LIMIT 1)))
         ORDER BY a.fecha, persona
    """

    async def dias_por_revisar(self, desde: Optional[str] = None,
                               hasta: Optional[str] = None,
                               area: Optional[str] = None) -> List[Dict[str, Any]]:
        from datetime import datetime as _dt
        desde = desde or await self.inicio_tramo_abierto()
        hasta = hasta or _dt.now().strftime('%Y-%m-%d')
        rows = await self.db.fetch_all(self._SQL_POR_REVISAR,
                                       (desde, hasta, f'%{MARCA_REVISION_REGLA}%'))
        out = []
        for r in rows:
            d = dict(r)
            if area and (d.get('area') or '') != area:
                continue
            d['secuencia'] = secuencia_en_revision(d.get('observaciones'))
            d.pop('observaciones', None)
            d.pop('marcas_consumidas_ids', None)
            out.append(d)
        return out

    async def confirmar_dia(self, empleado_id: int, fecha: str, usuario_id: int,
                            username: str, motivo: str) -> Dict[str, Any]:
        a = await self.db.fetch_one(
            "SELECT observaciones, marcas_consumidas_ids FROM asistencias WHERE empleado_id = ? AND fecha = ?",
            (empleado_id, fecha))
        if not a:
            return {'error': 'Ese día no tiene asistencia calculada.'}
        sec = secuencia_en_revision(a.get('observaciones'))
        if not sec:
            return {'error': 'Ese día no está en revisión por una regla de marcaciones.'}
        firma = firma_marcas(a.get('marcas_consumidas_ids'))
        if not firma:
            return {'error': 'No se pudo leer qué marcas usó el día; recalcúlelo primero.'}
        await self.db.execute(
            """INSERT OR IGNORE INTO revisiones_marcas
               (empleado_id, fecha, secuencia, firma, usuario_id, username, motivo)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (empleado_id, fecha, sec, firma, usuario_id, username, motivo))
        return {'secuencia': sec, 'firma': firma}

    async def evaluar_dia(self, empleado_id: int, fecha: str) -> Dict[str, Any]:
        """Qué dice la regla sobre este día, para el cuadro Ingreso Manual."""
        a = await self.db.fetch_one(
            "SELECT observaciones, marcas_consumidas_ids, estado FROM asistencias WHERE empleado_id = ? AND fecha = ?",
            (empleado_id, fecha))
        sec = secuencia_en_revision(a.get('observaciones')) if a else ''
        confirmado = False
        if a and sec:
            firma = firma_marcas(a.get('marcas_consumidas_ids'))
            r = await self.db.fetch_one(
                "SELECT username, created_at FROM revisiones_marcas WHERE empleado_id = ? AND fecha = ? AND firma = ?",
                (empleado_id, fecha, firma))
            confirmado = bool(r)
        regla = None
        if sec:
            rr = await self.db.fetch_one(
                "SELECT secuencia, lectura, colacion, accion, opciones_revision, activa "
                "FROM reglas_marcas WHERE tipo_horario = 'CICLO_INTELIGENTE' AND secuencia = ?", (sec,))
            if rr:
                regla = dict(rr)
                try:
                    regla['opciones_revision'] = json.loads(regla.get('opciones_revision') or '[]')
                except Exception:
                    regla['opciones_revision'] = []
        return {'en_revision': bool(sec) and not confirmado, 'confirmado': confirmado,
                'secuencia': sec, 'regla': regla,
                'ventana_colacion': await self.ventana_colacion()}

    async def pendientes_para_cierre(self, fecha_inicio: str, fecha_fin: str,
                                     area: str) -> List[Dict[str, Any]]:
        """Días por revisar dentro del rango de un cierre de área (bloquean el cierre)."""
        from datetime import datetime as _dt, timedelta as _td
        tope = (_dt.strptime(fecha_fin, '%Y-%m-%d') + _td(days=1)).strftime('%Y-%m-%d')
        return await self.dias_por_revisar(desde=fecha_inicio, hasta=tope, area=area)

    async def crear_regla(self, tipo_horario: str, secuencia: str, username: str) -> Dict[str, Any]:
        """Crea, desde la bandeja, una regla APAGADA para una secuencia nueva (nace en revisión)."""
        nueva = {'secuencia': secuencia, 'lectura': 'EXTREMOS', 'colacion': 'TURNO',
                 'accion': 'CALCULA_Y_REVISA', 'opciones_revision': ['RECLASIFICAR', 'CONFIRMAR']}
        if len(secuencia) == 1:
            nueva.update(lectura='NINGUNA', accion='SOLO_REVISA',
                         opciones_revision=['AGREGAR_SALIDA' if secuencia == 'E' else 'AGREGAR_ENTRADA'])
        motivo = validar_regla(nueva)
        if motivo:
            return {'error': motivo}
        existente = await self.db.fetch_one(
            "SELECT id FROM reglas_marcas WHERE tipo_horario = ? AND secuencia = ?",
            (tipo_horario, secuencia))
        if existente:
            return {'error': 'Esa secuencia ya tiene su regla.'}
        ultimo = await self.db.fetch_one(
            "SELECT COALESCE(MAX(numero), 0) AS n FROM reglas_marcas WHERE tipo_horario = ?", (tipo_horario,))
        await self.db.execute(
            """INSERT INTO reglas_marcas (tipo_horario, secuencia, lectura, colacion, accion,
                                          opciones_revision, activa, nota, updated_by, numero)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
            (tipo_horario, secuencia, nueva['lectura'], nueva['colacion'], nueva['accion'],
             json.dumps(nueva['opciones_revision']),
             'Creada desde la bandeja de secuencias sin regla.', username, int(ultimo['n']) + 1))
        creado = await self.db.fetch_one(
            "SELECT id FROM reglas_marcas WHERE tipo_horario = ? AND secuencia = ?",
            (tipo_horario, secuencia))
        return {'regla': await self.obtener(creado['id'])}

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
            'eleccion_colacion': cambios.get('eleccion_colacion') or actual.get('eleccion_colacion') or 'PARECIDA',
        }
        motivo = validar_regla(nueva)
        if motivo:
            return {'error': motivo}
        nota = cambios.get('nota', actual.get('nota'))
        await self.db.execute(
            """UPDATE reglas_marcas
                  SET lectura = ?, colacion = ?, accion = ?, opciones_revision = ?,
                      eleccion_colacion = ?, nota = ?, updated_by = ?,
                      updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
            (nueva['lectura'], nueva['colacion'], nueva['accion'],
             json.dumps(nueva['opciones_revision']), nueva['eleccion_colacion'],
             nota, username, regla_id)
        )
        despues = await self.obtener(regla_id)
        return {'antes': actual, 'despues': despues}
