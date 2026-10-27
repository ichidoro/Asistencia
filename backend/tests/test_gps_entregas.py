from backend.services.gps_nexacol import CALZA_M, CERCA_M, cruzar_entregas

PARADAS = [
    {"desde": "09:05:00", "hasta": "09:40:00", "min": 35, "lugar": "Calle A", "la": -34.6000, "lo": -70.9600},
    {"desde": "11:00:00", "hasta": "11:20:00", "min": 20, "lugar": "Calle B", "la": -34.6500, "lo": -70.9000},
]


def entrega(lat, lon, exacto=True, cliente="X"):
    return {"cliente": cliente, "calle": "c", "comuna": "k", "folios": ["1"], "kilos": 10, "lat": lat, "lon": lon, "exacto": exacto}


def estados(entregas, paradas=PARADAS):
    return [e["estado"] for e in cruzar_entregas(entregas, paradas)["entregas"]]


def test_estados_por_distancia():
    # 0,0005° de latitud ≈ 55 m · 0,003° ≈ 333 m · 0,02° ≈ 2,2 km
    assert estados([entrega(-34.6005, -70.9600), entrega(-34.6030, -70.9600), entrega(-34.6200, -70.9600)]) == ["calza", "cercana", "lejos"]
    assert CALZA_M < CERCA_M


def test_no_se_juzga_lo_aproximado_ni_lo_sin_ubicacion():
    assert estados([entrega(-34.6, -70.96, exacto=False), entrega(None, None)]) == ["aprox", "sin_ubicacion"]


def test_camion_sin_paradas():
    assert estados([entrega(-34.6, -70.96)], paradas=[]) == ["sin_parada"]


def test_cada_parada_conoce_su_entrega_y_el_resumen_cuenta():
    r = cruzar_entregas([entrega(-34.6005, -70.9600, cliente="CERCA"), entrega(-34.6500, -70.9200, cliente="LEJOS")], PARADAS)
    assert r["paradas"][0]["cliente"] == "CERCA" and r["paradas"][1] is None
    assert r["resumen"]["total"] == 2 and r["resumen"]["calza"] == 1 and r["resumen"]["lejos"] == 1
