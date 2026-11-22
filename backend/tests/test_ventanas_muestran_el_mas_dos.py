"""Un día con jornada y +2 muestra las dos partes (pedido de la persona dueña, 21-11-2026; caso 18-07-2026: turno de
sábado 09:00 a 14:00, jornada corrida de 11:30 a 21:52, jornada 04:30:00 + +2 05:21:48).

- Tarjeta del día (al pasar el mouse): el origen de las horas extra dice «+2 · cobertura de turno» con sus minutos; antes
  restaba la hora de salida a la del turno y decía «Salida posterior 07:52:00».
- La línea de la jornada pinta la llegada como atraso solo si el cálculo anotó atraso; en una jornada corrida no lo hay.
- Ventana del día (al hacer clic): «Jornada 04:30:00 + jornada +2 05:21:48 = 09:51:48».
Solo cambia lo que se muestra: el cálculo del +2 no se toca.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
UI = (RAIZ / "frontend" / "js" / "marcaciones_ui.js").read_text(encoding="utf-8")
TD = (RAIZ / "frontend" / "js" / "tarjeta_dia.js").read_text(encoding="utf-8")


def test_la_tarjeta_nombra_el_mas_dos_en_el_origen_de_las_horas_extra():
    assert "+2 · cobertura de turno:" in UI and "Llamado de emergencia:" in UI and "Día libre o feriado:" in UI
    i = UI.index("+2 · cobertura de turno:")
    bloque = UI[UI.rindex("} else if ((Number(e.minutos_extra_mas2)", 0, i):i]
    assert "minutos_extra_llamado" in bloque and "minutos_extra_esp" in bloque
    # el desglose por hora de salida queda solo para los días sin +2, llamado ni día libre
    assert UI.index("+2 · cobertura de turno:") < UI.index("Salida Posterior:")


def test_la_linea_de_la_jornada_no_pinta_atraso_sin_atraso():
    assert "const tarde = dEnt > 0.5 && (Number(e.minutos_atraso) || 0) > 0;" in UI
    tramo = UI[UI.index("const tarde = dEnt > 0.5"):UI.index("// Eventos: con la línea de tiempo")]
    assert "dEnt > 0.5 ?" not in tramo and tramo.count("tarde ?") == 4


def test_la_ventana_del_dia_suma_jornada_y_mas_dos():
    assert "'<div class=\"td-ctx he\"><i class=\"bi bi-stopwatch\"></i><span><b>Jornada ' + hms(turno) + ' + jornada +2 ' + hms(mas2)" in TD
    assert "const total = Number(di.horas_trabajadas) * 60, turno = Math.max(0, total - mas2);" in TD
