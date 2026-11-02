from backend.services.velocidades_choferes import calzar_choferes

CHOFERES = [
    {"id": 1, "nombre_completo": "PEREZ SOTO JUAN PABLO", "activo": 1},
    {"id": 2, "nombre_completo": "MUNOZ ROJAS CARLOS", "activo": 1},
    {"id": 3, "nombre_completo": "MUNOZ DIAZ CARLOS", "activo": 1},
    {"id": 4, "nombre_completo": "LOPEZ GARCIA PEDRO", "activo": 1},
    {"id": 5, "nombre_completo": "LOPEZ GARCIA PEDRO LUIS", "activo": 0},
]


def dia(fecha, nombres, vel=88, patente="PKDD13", hora="14:05"):
    return {"fecha": fecha, "patente": patente, "choferes": nombres, "velMax": vel, "hora": hora}


def test_calza_aunque_el_orden_de_apellidos_y_nombre_sea_distinto():
    por_emp, sin = calzar_choferes([dia("2026-10-29", ["Juan Pablo Pérez Soto"])], CHOFERES)
    assert por_emp["1"]["2026-10-29"] == {"vel": 88, "hora": "14:05", "patente": "PKDD13", "comparte": False}
    assert sin == []


def test_un_nombre_corto_ambiguo_no_se_asigna_a_nadie():
    por_emp, sin = calzar_choferes([dia("2026-10-29", ["Carlos"])], CHOFERES)
    assert por_emp == {}
    assert sin == [{"nombre": "Carlos", "dias": ["2026-10-29"]}]


def test_con_nombre_y_apellido_se_resuelve_la_ambiguedad():
    por_emp, _ = calzar_choferes([dia("2026-10-29", ["Carlos Muñoz Diaz"])], CHOFERES)
    assert list(por_emp) == ["3"]


def test_entre_dos_candidatas_gana_la_que_tiene_exactamente_las_mismas_palabras():
    por_emp, _ = calzar_choferes([dia("2026-10-29", ["Pedro Lopez Garcia"])], CHOFERES)
    assert list(por_emp) == ["4"]


def test_sin_velocidad_no_hay_dato_ni_se_reclama_el_nombre():
    por_emp, sin = calzar_choferes([dia("2026-10-29", ["Juan Perez Soto"], vel=None)], CHOFERES)
    assert por_emp == {} and sin == []


def test_dos_camiones_el_mismo_dia_deja_la_velocidad_mas_alta():
    por_emp, _ = calzar_choferes([dia("2026-10-29", ["Juan Perez Soto"], 70, "A"), dia("2026-10-29", ["Juan Perez Soto"], 95, "B")], CHOFERES)
    assert por_emp["1"]["2026-10-29"]["vel"] == 95 and por_emp["1"]["2026-10-29"]["patente"] == "B"


def test_dos_choferes_en_un_camion_comparten_y_se_marca():
    por_emp, _ = calzar_choferes([dia("2026-10-29", ["Juan Perez Soto", "Pedro Lopez Garcia"])], CHOFERES)
    assert por_emp["1"]["2026-10-29"]["comparte"] and por_emp["4"]["2026-10-29"]["comparte"]


def test_decimar_ruta_conserva_extremos_y_el_punto_de_velocidad_maxima():
    from backend.services.gps_nexacol import decimar_ruta
    pts = [{"s": i * 10, "la": -35.0 + i * 1e-4, "lo": -71.0, "v": 40} for i in range(2000)]
    pts[777]["v"] = 99
    out = decimar_ruta(pts, maximo=450)
    assert len(out) <= 460
    assert out[0]["s"] == 0 and out[-1]["s"] == 19990
    assert any(p["v"] == 99 for p in out)
    assert decimar_ruta(pts[:10], maximo=450) == [{k: p[k] for k in ("s", "la", "lo", "v")} for p in pts[:10]]


def test_segundos_sobre_limite_cuenta_solo_lo_que_iba_sobre_el_limite():
    from backend.services.gps_nexacol import segundos_sobre_limite
    pts = [{"s": 0, "v": 60}, {"s": 30, "v": 95}, {"s": 60, "v": 97}, {"s": 90, "v": 80}, {"s": 120, "v": 91}, {"s": 150, "v": 50}]
    # sobre 90: del segundo 30 al 90 (60 s) y del 120 al 150 (30 s)
    assert segundos_sobre_limite(pts, 90) == 90
    assert segundos_sobre_limite(pts, 120) == 0
    # un hueco enorme sin reportar no cuenta entero
    assert segundos_sobre_limite([{"s": 0, "v": 100}, {"s": 7200, "v": 100}], 90) == 15 * 60
