from backend.services.gps_nexacol import _tokens_calle, cruzar_entregas

PARADAS = [
    {"desde": "09:05:00", "hasta": "09:40:00", "min": 35, "lugar": "Shell, Avenida Bernardo OHiggins, El Trapiche, San Fernando, Región del Libertador, Chile", "la": -34.6000, "lo": -70.9600},
    {"desde": "11:00:00", "hasta": "11:20:00", "min": 20, "lugar": "Rosario, Villa Cataluña, Curicó, Región del Maule, Chile", "la": -34.9800, "lo": -71.2300},
]


def entrega(calle, comuna, **k):
    return {"cliente": "X", "calle": calle, "comuna": comuna, "folios": ["1"], "kilos": 10, **k}


def estados(entregas, paradas=PARADAS):
    return [e["estado"] for e in cruzar_entregas(entregas, paradas)["entregas"]]


def test_las_palabras_de_la_calle_ignoran_abreviaturas_y_numeros():
    assert _tokens_calle("AV. BERNARDO O'HIGGINS 1234") == ["bernardo", "ohiggins"]
    assert _tokens_calle("Pasaje Los Aromos 12") == ["aromos"]


def test_calza_por_calle_y_comuna():
    r = cruzar_entregas([entrega("AV BERNARDO O'HIGGINS 1234", "San Fernando")], PARADAS)
    assert r["entregas"][0]["estado"] == "calza" and r["entregas"][0]["via"] == "direccion" and r["entregas"][0]["parada_idx"] == 0
    assert r["paradas"][0]["cliente"] == "X" and r["paradas"][1] is None


def test_la_comuna_se_compara_por_palabras():
    paradas = [{"desde": "10:00:00", "hasta": "10:20:00", "min": 20, "lugar": "San Guillermo, Villa Mostazal, San Francisco de Mostazal, Región del Libertador"}]
    assert estados([entrega("SAN GUILLERMO 49", "San Francisco Mostazal")], paradas) == ["calza"]


def test_misma_comuna_pero_otra_calle():
    assert estados([entrega("Los Aromos 9", "Curicó")]) == ["comuna"]


def test_el_camion_no_paro_en_esa_comuna():
    assert estados([entrega("Los Aromos 9", "Romeral")]) == ["sin_parada"]
    assert estados([entrega("Los Aromos 9", "Romeral")], paradas=[]) == ["sin_parada"]


def test_con_coordenada_exacta_mide_la_distancia():
    # 0,0005° de latitud ≈ 55 m · 0,003° ≈ 333 m · 0,02° ≈ 2,2 km (comuna distinta de las paradas, así que decide la distancia)
    def e(la):
        return entrega("Otra 1", "Romeral", lat=la, lon=-70.9600, exacto=True)
    assert estados([e(-34.6005), e(-34.6030), e(-34.6200)]) == ["calza", "cercana", "lejos"]


def test_coordenada_aproximada_no_se_mide():
    r = cruzar_entregas([entrega("Otra 1", "Romeral", lat=-34.6005, lon=-70.96, exacto=False)], PARADAS)
    assert r["entregas"][0]["estado"] == "sin_parada" and r["entregas"][0]["dist_m"] is None


def test_resumen():
    r = cruzar_entregas([entrega("AV BERNARDO O'HIGGINS 1", "San Fernando"), entrega("X 1", "Curicó"), entrega("Y 1", "Romeral")], PARADAS)
    assert r["resumen"] == {"total": 3, "calza": 1, "cercana": 0, "comuna": 1, "lejos": 0, "sin_parada": 1}
