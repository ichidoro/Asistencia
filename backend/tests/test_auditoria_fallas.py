# -*- coding: utf-8 -*-
"""Tres fallas que encontró la auditoría del 15-11-2026 (efecto dominó, simulación de copias y araña de consultas).
Cada una queda como prueba para que no vuelva."""
import asyncio
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "x" * 40)
from backend.core.config import settings  # noqa: E402


def test_visitas_usa_la_hora_de_chile_con_cambio_de_horario():
    """F1: Visitas guardaba la hora con UTC-4 fijo; desde el horario de verano cada visita quedaba con una hora menos."""
    from backend.routers import visitas
    assert str(visitas.CHILE_TZ) == settings.TIMEZONE
    horas = lambda d: d.utcoffset().total_seconds() / 3600
    assert horas(datetime(2026, 11, 10, 18, 0, tzinfo=visitas.CHILE_TZ)) == -3     # verano
    assert horas(datetime(2026, 7, 1, 12, 0, tzinfo=visitas.CHILE_TZ)) == -4       # invierno


class _DbSoloLee:
    """Guarda las consultas y responde como una base con una inasistencia y ninguna justificación."""
    def __init__(self):
        self.sql = []

    async def fetch_all(self, q, p=()):
        self.sql.append(q)
        return [{'fecha': '2026-11-03', 'estado': 'INASISTENCIA', 'observaciones': ''}]

    async def fetch_one(self, q, p=()):
        self.sql.append(q)
        return None


def test_selector_de_inasistencias_no_pide_columnas_que_no_existen():
    """F2: la consulta pedía justificaciones.estado, columna que la tabla no tiene: la ventana siempre fallaba."""
    import inspect
    from backend.routers import asistencia as r
    src = inspect.getsource(r.get_inasistencias_disponibles)
    consulta = src.split('FROM justificaciones', 1)[1].split('"""', 1)[0]
    assert 'estado' not in consulta


def test_excel_por_rango_recibe_la_matriz_del_periodo():
    """F3: el Excel por rango recibía filas sueltas donde el armado del libro espera la matriz (siempre fallaba)."""
    from backend.services.report_service import ReportService

    pedido = {}

    class _Servicio:
        async def get_matrix_data_with_projections(self, mes, anio, **kw):
            pedido.update(mes=mes, anio=anio, **kw)
            return {'empleados': [], 'matrix': {}}

    svc = ReportService.__new__(ReportService)
    svc.asistencia_service = _Servicio()

    async def _libro(matrix_data, rango_dias, area):
        assert isinstance(matrix_data, dict) and 'empleados' in matrix_data
        return ('libro', len(rango_dias), area)

    svc._generate_excel_workbook = _libro
    out = asyncio.run(svc.generate_excel_custom_range('2026-09-26', '2026-11-25', 'PRODUCCION', turno_id=None))
    assert out == ('libro', 61, 'PRODUCCION')
    assert pedido['fecha_inicio_override'] == '2026-09-26' and pedido['fecha_fin_override'] == '2026-11-25'
    assert pedido['area'] == 'PRODUCCION'


def test_la_purga_del_registro_de_auditoria_usa_su_columna_de_fecha():
    """F4: la purga semanal borraba según una columna «fecha» que logs_auditoria no tiene: fallaba cada semana."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / 'core' / 'events.py').read_text(encoding='utf-8')
    assert "DELETE FROM logs_auditoria WHERE created_at < date('now', '-12 months')" in src
    assert "logs_auditoria WHERE fecha" not in src
