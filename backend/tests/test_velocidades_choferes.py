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
