from backend.core.database import Database
from datetime import datetime

class CierreService:
    def __init__(self, db: Database):
        self.db = db

    async def evaluar_cierre(self, fecha_inicio: str, fecha_fin: str, area: str):
        """
        Evaluación pre-cierre con 4 niveles de semáforo (tela de araña):
        1. HE PENDIENTES       → Hard Stop 1
        2. ANOMALÍAS           → Hard Stop 2
        3. EN_CURSO            → Hard Stop 3
        4. INASISTENCIAS       → Soft Stop (aceptar con checkbox)
        """
        params_area = []
        filtro_area = ""
        if area and area != 'Todas':
            filtro_area = " AND e.area = ?"
            params_area = [area]

        # ── HARD STOP 1: Horas extras pendientes ──────────────────────────────
        query_he = f"""
            SELECT he.id, he.fecha,
                   e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS nombre_completo,
                   he.minutos_autorizados
            FROM horas_extras he
            JOIN empleados e ON he.empleado_id = e.id
            WHERE he.fecha BETWEEN ? AND ?
              AND he.estado = 'PENDIENTE'
            {filtro_area}
            ORDER BY e.apellido_paterno, he.fecha
        """
        he_pendientes = await self.db.fetch_all(
            query_he, tuple([fecha_inicio, fecha_fin] + params_area)
        )

        # ── HARD STOP 2: Anomalías sin corregir ───────────────────────────────
        # Excluye anomalías que tienen JE aprobada (EXTRA) con ambas marcas → no son bloqueantes
        query_anomalias = f"""
            SELECT a.id, a.fecha, a.hora_entrada_real, a.hora_salida_real,
                   e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS nombre_completo,
                   e.area
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            WHERE a.fecha BETWEEN ? AND ?
              AND a.estado = 'ANOMALIA'
              AND NOT EXISTS (
                  SELECT 1 FROM jornadas_especiales je
                  WHERE je.empleado_id = a.empleado_id
                    AND je.fecha = a.fecha
                    AND je.estado = 'EXTRA'
                    AND je.hora_entrada IS NOT NULL
                    AND je.hora_salida IS NOT NULL
              )
            {filtro_area}
            ORDER BY e.apellido_paterno, a.fecha
        """
        anomalias = await self.db.fetch_all(
            query_anomalias, tuple([fecha_inicio, fecha_fin] + params_area)
        )

        # ── HARD STOP 3: Empleados EN_CURSO en el periodo ─────────────────────
        # Calcula hora estimada de salida para orientar al Jefe
        query_en_curso = f"""
            SELECT a.id, a.fecha, a.hora_entrada_real,
                   a.hora_salida_teorica,
                   e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS nombre_completo,
                   e.area
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            WHERE a.fecha BETWEEN ? AND ?
              AND a.estado = 'EN_CURSO'
            {filtro_area}
            ORDER BY a.hora_salida_teorica ASC NULLS LAST
        """
        en_curso = await self.db.fetch_all(
            query_en_curso, tuple([fecha_inicio, fecha_fin] + params_area)
        )

        # Calcular hora estimada del último turno activo para mensaje orientador
        ultimo_fin_estimado = None
        if en_curso:
            salidas = [r['hora_salida_teorica'] for r in en_curso if r['hora_salida_teorica']]
            if salidas:
                ultimo_fin_estimado = max(salidas)

        # ── SOFT STOP: Inasistencias sin justificar ────────────────────────────
        # Solo INASISTENCIA, ya NO incluye ANOMALIA (separadas en Hard Stop 2)
        query_ina = f"""
            SELECT a.id, a.fecha,
                   e.apellido_paterno || ' ' || e.apellido_materno || ', ' || e.nombre AS nombre_completo,
                   e.area
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            WHERE a.fecha BETWEEN ? AND ?
              AND a.estado = 'INASISTENCIA'
            {filtro_area}
            ORDER BY e.apellido_paterno, a.fecha
        """
        inasistencias = await self.db.fetch_all(
            query_ina, tuple([fecha_inicio, fecha_fin] + params_area)
        )

        # ── Resumen ejecutivo siempre visible ─────────────────────────────────
        query_resumen = f"""
            SELECT
                COUNT(DISTINCT a.empleado_id)                                                      AS total_empleados,
                SUM(CASE WHEN a.estado = 'OK' THEN 1 ELSE 0 END)                                   AS dias_ok,
                SUM(CASE WHEN a.estado IN ('ATRASO','SALIDA_ADELANTADA','ATR_SAD') THEN 1 ELSE 0 END) AS dias_con_novedad,
                SUM(CASE WHEN a.estado = 'VACACIONES' THEN 1 ELSE 0 END)                           AS vacaciones,
                SUM(CASE WHEN a.estado LIKE 'LICENCIA%' THEN 1 ELSE 0 END)                         AS licencias,
                SUM(CASE WHEN a.estado = 'JORNADA_ESPECIAL' THEN 1 ELSE 0 END)                     AS jornadas_especiales,
                SUM(CASE WHEN a.estado = 'LIBRE' THEN 1 ELSE 0 END)                                AS dias_libres,
                SUM(CASE WHEN a.estado = 'FERIADO' THEN 1 ELSE 0 END)                              AS feriados_caidos,
                SUM(CASE WHEN a.estado = 'INASISTENCIA' THEN 1 ELSE 0 END)                         AS inasistencias,
                SUM(CASE WHEN a.estado = 'ANOMALIA' THEN 1 ELSE 0 END)                             AS anomalias
            FROM asistencias a
            JOIN empleados e ON a.empleado_id = e.id
            WHERE a.fecha BETWEEN ? AND ?
            {filtro_area}
        """
        resumen_row = await self.db.fetch_one(
            query_resumen, tuple([fecha_inicio, fecha_fin] + params_area)
        )
        resumen = dict(resumen_row) if resumen_row else {}

        # HE aprobadas para el resumen
        query_he_aprobadas = f"""
            SELECT ROUND(SUM(he.minutos_autorizados) / 60.0, 2) AS he_horas,
                   COUNT(*) AS he_count
            FROM horas_extras he
            JOIN empleados e ON he.empleado_id = e.id
            WHERE he.fecha BETWEEN ? AND ?
              AND he.estado = 'APROBADO'
            {filtro_area}
        """
        he_row = await self.db.fetch_one(
            query_he_aprobadas, tuple([fecha_inicio, fecha_fin] + params_area)
        )
        resumen['he_aprobadas_horas'] = (he_row['he_horas'] or 0.0) if he_row else 0.0
        resumen['he_aprobadas_count'] = (he_row['he_count'] or 0) if he_row else 0

        # Feriados del periodo
        query_feriados = """
            SELECT fecha, descripcion FROM feriados
            WHERE fecha BETWEEN ? AND ?
            ORDER BY fecha
        """
        feriados_periodo = await self.db.fetch_all(query_feriados, (fecha_inicio, fecha_fin))

        # Determinar si puede cerrar
        puede_cerrar = (
            len(he_pendientes) == 0
            and len(anomalias) == 0
            and len(en_curso) == 0
        )

        return {
            "puede_cerrar": puede_cerrar,
            # Hard Stops
            "he_pendientes": len(he_pendientes),
            "detalle_he": [dict(r) for r in he_pendientes],
            "anomalias": len(anomalias),
            "detalle_anomalias": [dict(r) for r in anomalias],
            "en_curso": len(en_curso),
            "detalle_en_curso": [dict(r) for r in en_curso],
            "ultimo_fin_estimado": ultimo_fin_estimado,
            # Soft Stop
            "inasistencias_injustificadas": len(inasistencias),
            "detalle_ina": [dict(r) for r in inasistencias],
            # Resumen ejecutivo
            "resumen": resumen,
            "feriados_periodo": [dict(r) for r in feriados_periodo],
        }

    async def ejecutar_cierre(self, fecha_inicio: str, fecha_fin: str, area: str, aceptar_inasistencias: bool, user: dict):
        evaluacion = await self.evaluar_cierre(fecha_inicio, fecha_fin, area)

        # Validar los 3 Hard Stops
        if evaluacion["he_pendientes"] > 0:
            raise ValueError(
                f"No se puede cerrar el periodo. Hay {evaluacion['he_pendientes']} "
                f"horas extras pendientes de validación."
            )
        if evaluacion["anomalias"] > 0:
            raise ValueError(
                f"No se puede cerrar el periodo. Hay {evaluacion['anomalias']} "
                f"anomalías sin corregir. Corrígelas en la grilla antes de cerrar."
            )
        if evaluacion["en_curso"] > 0:
            msg = (
                f"No se puede cerrar el periodo. Hay {evaluacion['en_curso']} "
                f"empleados con turnos activos (EN_CURSO)."
            )
            if evaluacion.get("ultimo_fin_estimado"):
                msg += f" El último turno activo termina aprox. a las {evaluacion['ultimo_fin_estimado']}."
            raise ValueError(msg)

        # Validar Soft Stop
        if evaluacion["inasistencias_injustificadas"] > 0 and not aceptar_inasistencias:
            raise ValueError(
                f"Hay {evaluacion['inasistencias_injustificadas']} inasistencias sin justificar. "
                f"Debe aceptarlas explícitamente para continuar."
            )

        # Validar que no exista ya un cierre para ese periodo y área
        check_query = "SELECT id FROM cierres_periodos WHERE fecha_inicio = ? AND fecha_fin = ? AND area = ?"
        existe = await self.db.fetch_one(check_query, (fecha_inicio, fecha_fin, area))
        if existe:
            raise ValueError("El periodo seleccionado ya se encuentra cerrado para esta área.")

        # Determinar tipo de cierre según rol
        tipo_cierre = "SUPER_ADMIN" if user.is_superuser else "JEFE_AREA"

        comentarios = (
            f"Cierre ejecutado por {user.username or 'sistema'} "
            f"[{tipo_cierre}] — "
            f"Inasistencias aceptadas: {'SI' if aceptar_inasistencias else 'N/A'}"
        )

        insert_query = """
            INSERT INTO cierres_periodos (fecha_inicio, fecha_fin, usuario_id, username, tipo_cierre, area, comentarios)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        await self.db.execute(insert_query, (
            fecha_inicio,
            fecha_fin,
            user.user_id,
            user.username,
            tipo_cierre,
            area,
            comentarios
        ))

        return {"success": True, "message": "Periodo cerrado exitosamente.", "tipo_cierre": tipo_cierre}

    async def revertir_cierre(self, fecha_inicio: str, fecha_fin: str, area: str, user: dict):
        # Primero buscar si existe
        check_query = "SELECT id FROM cierres_periodos WHERE fecha_inicio = ? AND fecha_fin = ? AND area = ?"
        existe = await self.db.fetch_one(check_query, (fecha_inicio, fecha_fin, area))
        if not existe:
            raise ValueError("No se encontró un cierre para revertir en este periodo y área.")
            
        delete_query = "DELETE FROM cierres_periodos WHERE fecha_inicio = ? AND fecha_fin = ? AND area = ?"
        await self.db.execute(delete_query, (fecha_inicio, fecha_fin, area))
        
        return {"success": True, "message": "Cierre revertido exitosamente."}
