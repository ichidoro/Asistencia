"""Preinforme: «Para coordinar antes del cierre» (frases aprobadas por la persona dueña, 18 y 21-11-2026).

Ciclo Inteligente: quién debe horas que se van a descontar y quién tiene inasistencias sin justificar.
Bolsa Flexible: las horas bajo la meta no se descuentan; el aviso es quién va bajo la meta y quién ya la pasó.
Quien no tiene nada que coordinar no aparece. Solo en el preinforme: el informe de cierre no lo lleva.
"""
import os

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services import informe_cierre_pdf as icp  # noqa: E402

FIN, HOY = "2026-11-25", "2026-11-18"


def _ciclo(nombre, descontar=0, n_atr=0, n_sad=0, ina=(), activo=True):
    return {"nombre": nombre, "horario": "Horario A", "activo": activo, "descontar": descontar, "n_atr": n_atr,
            "n_sad": n_sad, "dias_aus": {f: "ina" for f in ina}}


def _bolsa(nombre, acum, meta=648000):
    return {"nombre": nombre, "horario": "Horario B", "activo": True, "acum": acum, "meta": meta}


def test_ciclo_quien_debe_horas_ordenado_de_mayor_a_menor():
    inf = {"tipo": "CICLO", "personas": [_ciclo("PERSONA UNO", 3600, n_atr=2), _ciclo("PERSONA DOS", 18750, n_atr=4, n_sad=2),
                                         _ciclo("PERSONA TRES")]}
    av = icp.para_coordinar(inf, FIN, HOY)
    assert len(av) == 2
    assert av[0].startswith("<b>PERSONA DOS</b> (Horario A) debe <b>05:12:30</b> al 18-11 (4 atrasos y 2 salidas adelantadas).")
    assert "antes del cierre del 25-11" in av[0] and "pagan primero la deuda del tramo" in av[0]
    assert "(2 atrasos)" in av[1] and "PERSONA TRES" not in " ".join(av)


def test_ciclo_inasistencias_sin_justificar():
    inf = {"tipo": "CICLO", "personas": [_ciclo("PERSONA UNO", ina=["2026-11-12"]),
                                         _ciclo("PERSONA DOS", ina=["2026-11-14", "2026-11-03"])]}
    av = icp.para_coordinar(inf, FIN, HOY)
    assert av[0] == ("<b>PERSONA UNO</b> (Horario A) tiene una inasistencia el 12-11 sin justificar. Se puede compensar "
                     "con una jornada extra o con horas extra del mismo tramo, o justificar, antes del cierre.")
    assert "tiene 2 inasistencias (03-11 y 14-11) sin justificar" in av[1]


def test_bolsa_bajo_la_meta_y_sobre_la_meta():
    inf = {"tipo": "BOLSA", "personas": [_bolsa("PERSONA UNO", 432000), _bolsa("PERSONA DOS", 671400), _bolsa("PERSONA TRES", 648000)]}
    av = icp.para_coordinar(inf, FIN, HOY)
    assert av[0] == ("<b>PERSONA UNO</b> (Horario B) lleva <b>120:00:00</b> de <b>180:00:00</b> al 18-11. Le quedan "
                     "<b>60:00:00</b> de bolsa hasta el 25-11, que se pueden programar con la persona.")
    assert av[1].startswith("<b>PERSONA DOS</b> (Horario B) ya pasó la meta: lleva <b>186:30:00</b>")
    assert "cada hora se paga como hora extra" in av[1] and len(av) == 2


def test_inactivos_no_aparecen_y_el_corte_no_pasa_el_fin_del_periodo():
    inf = {"tipo": "CICLO", "personas": [_ciclo("PERSONA UNO", 600, activo=False), _ciclo("PERSONA DOS", 600)]}
    av = icp.para_coordinar(inf, FIN, "2026-11-28")
    assert len(av) == 1 and "al 25-11" in av[0] and "PERSONA UNO" not in av[0]


def test_solo_el_preinforme_lleva_la_seccion():
    p = {"emp_id": 1, "rut": "1.111.111-1", "nombre": "PERSONA DE PRUEBA", "activo": True, "tipo": "CICLO",
         "horario": "Horario A", "horas": 42.0, "n_atr": 3, "n_sad": 0, "bonos": {}, "trab": 18, "aus": {}, "per": 0,
         "comp": 0, "ina": 0, "ano": 0, "atr": 3600, "sad": 0, "col": 0, "h_per": 0, "otros": 0, "total": 3600,
         "comp_inas": 0, "cubren": 0, "descontar": 3600, "he_trab": 0, "he_noap": 0, "he_decidir": 0, "he_inas": 0, "pagar": 0}
    inf = icp.separar_informes([p])[0]
    pre = icp.render_pdf("AREA DE PRUEBA", "2026-10-26", FIN, "x", inf, [], [], preinforme=True)
    fin = icp.render_pdf("AREA DE PRUEBA", "2026-10-26", FIN, "x", inf, [], [])
    assert pre.startswith(b"%PDF") and fin.startswith(b"%PDF")
    assert len(pre) > len(fin)   # la sección solo va en el preinforme (el texto del PDF va comprimido)
