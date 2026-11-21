"""Las horas extra de un día libre o feriado se tratan igual que cualquier hora extra (persona dueña, 21-11-2026).

Una jornada especial pasada a horas extra queda en horas_extras como cualquier otra. Antes el cuadre la dejaba fuera
del reparto: había que aprobarla aparte con ✓ y, al aprobarla, se pagaba por fuera del tope de «Pagar hasta». Ahora la
política la reparte: primero cubre la deuda y después se paga hasta el tope.

Caso de prueba con los minutos del 21-11-2026 (Planta Mantencion 2, Julio): 03:52:01 de horas extra en días normales,
15:00:00 de un día libre y 06:30:00 de un feriado; deuda 05:31:32; política «Pagar hasta 19:00:00».
"""
from pathlib import Path

from backend.services.cuadre_service import asignar_minutos, filas_para_reparto, presupuesto_he

RAIZ = Path(__file__).resolve().parents[2]
NORMAL = 3 * 60 + 52 + 1 / 60
DEUDA = 5 * 60 + 31 + 32 / 60


def _filas():
    return [{'fecha': '2026-06-28', 'minutos_bruto': 900.0, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'origen': 'SISTEMA', 'excepcion': 0},
            {'fecha': '2026-07-10', 'minutos_bruto': NORMAL, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'origen': 'SISTEMA', 'excepcion': 0},
            {'fecha': '2026-07-16', 'minutos_bruto': 390.0, 'minutos_autorizados': 0, 'estado': 'PENDIENTE', 'origen': 'SISTEMA', 'excepcion': 0}]


def test_el_reparto_incluye_las_horas_extra_de_dias_libres_y_feriados():
    reparto, resumen = asignar_minutos(filas_para_reparto(_filas()), DEUDA, 'PAGAR', 19 * 60.0)
    assert sorted(r['fecha'] for r in reparto) == ['2026-06-28', '2026-07-10', '2026-07-16']
    assert abs(resumen['cubierto'] - DEUDA) < 0.01
    assert abs(resumen['a_pagar'] - 19 * 60.0) < 0.01                       # el tope también cuenta esas horas
    assert abs(resumen['no_pagadas'] - (50 + 29 / 60)) < 0.02               # 00:50:29 sin pagar
    assert all(r['estado'] == 'APROBADO' for r in reparto[:2])


def test_el_mas_dos_y_lo_decidido_a_mano_siguen_fijos():
    filas = _filas() + [{'fecha': '2026-07-02', 'minutos_bruto': 60.0, 'minutos_autorizados': 60.0, 'estado': 'APROBADO',
                         'origen': 'COBERTURA_TURNO', 'excepcion': 0}]
    filas[1]['excepcion'] = 1
    marcadas = {r['fecha']: r['excepcion'] for r in filas_para_reparto(filas)}
    assert marcadas['2026-07-02'] == 1 and marcadas['2026-07-10'] == 1 and marcadas['2026-06-28'] == 0


def test_el_presupuesto_de_la_guia_cuenta_esas_horas():
    dias = [{'fecha': '2026-06-28', 'estado': 'JORNADA_ESPECIAL', 'horas_teoricas': 0.0, 'horas_trabajadas': 15.0}]
    assert abs(presupuesto_he(dias, {'deuda_neta': DEUDA}, _filas()) - DEUDA) < 0.01


def test_la_ventana_deja_confirmar_de_nuevo_si_quedan_horas_por_decidir():
    js = (RAIZ / "frontend" / "js" / "cuadre_ui.js").read_text(encoding="utf-8")
    assert "if (L && Number(L.he_por_decidir) >= 1) return false;" in js
    cierre = (RAIZ / "frontend" / "js" / "marcaciones_ui.js").read_text(encoding="utf-8")
    assert "el cuadre no los reparte" not in cierre and "confirma de nuevo para que el cuadre las reparta" in cierre
