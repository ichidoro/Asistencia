# -*- coding: utf-8 -*-
"""Columnas PER: el permiso tomado entre marcas se cuenta, sin duplicar la deuda.

Decisión del dueño (24-10-2026): el permiso que la persona toma entre marcas
(salió y volvió dentro de su horario) se cuenta en la columna PER del grupo
Incidencias (días) y en la columna PER de Tiempo no trabajado (minutos), igual
que la ventana del día. Sus minutos ya están en la deuda neta del día (TOT), así
que no se pueden sumar dos veces: TOT y el saldo siguen saliendo de la deuda
neta, y cuando un día tiene además el permiso ingresado por horas (es el mismo
permiso: en la base los 35 días con los dos traen los mismos minutos) se toma el
mayor, nunca la suma.
"""
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "x" * 40)

RAIZ = Path(__file__).resolve().parents[2]


def _leer(rel):
    return (RAIZ / rel).read_text(encoding="utf-8")


def test_la_grilla_cuenta_el_permiso_de_las_marcas_sin_sumar_los_dos():
    js = _leer("frontend/js/marcaciones_ui.js")
    assert ("const rawPer = Math.max(Number(di.minutos_permisos_detectados || 0), "
            "Number(di.minutos_permiso_personal_deuda || 0));") in js
    assert "if (di.tiene_permiso_hora || di.permiso_activo || rawPer > 0) cnt_per++;" in js
    # TOT y el saldo siguen saliendo de la deuda neta del día, no de las columnas
    assert "const dayNetDeuda = (condTipo === 5) ? 0 : Number(di.minutos_deuda || 0);" in js
    assert "d_tot   += dayNetDeuda;" in js
    assert "let rawSaldo = esBolsa ? 0 : (he_apr - d_tot - he_compensado);" in js


def test_el_excel_cuenta_igual_que_la_grilla():
    s = _leer("backend/services/report_service.py")
    assert 'raw_per = max(float(di.get("minutos_permisos_detectados") or 0.0),' in s
    assert 'if di.get("tiene_permiso_hora") or di.get("permiso_activo") or raw_per > 0:' in s
    # El Excel reparte la deuda neta del día entre sus causas: la suma no pasa de TOT
    assert "day_per = raw_per * factor" in s
    assert "d_tot += day_net_deuda" in s


def test_el_resumen_del_cierre_no_pasa_de_la_deuda_del_dia():
    s = _leer("backend/services/cierre_service.py")
    assert 'raw_per = max(float(di.get("minutos_permisos_detectados") or 0.0),' in s
    # Cuando la persona compensó parte el mismo día, el permiso también se reparte (antes iba entero)
    assert "total_deuda_permisos_min += raw_per * factor" in s
    assert "total_deuda_permisos_min += raw_per\n" not in s.split("factor = base_deuda / raw_total", 1)[1].split("total_deuda_salidas_min", 1)[0]


def test_reparto_del_dia_de_becerra_no_duplica():
    """Becerra, 09-10-2026: exceso de colación 5 min, permiso 50 min y deuda neta 48,43 min."""
    col, per, base = 5.0, 50.0, 48.43
    total = col + per
    factor = base / total
    assert round(col * factor + per * factor, 6) == base
    assert col * factor + per * factor <= base + 1e-9
