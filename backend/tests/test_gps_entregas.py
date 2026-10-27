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


TALCA = [
    {"desde": "08:49:00", "hasta": "09:07:00", "min": 18, "lugar": "6 Oriente, Cancha Rayada, Barrio Norte, Talca, Región del Maule, Chile"},
    {"desde": "09:12:00", "hasta": "09:20:00", "min": 8, "lugar": "Pasaje 16½ Norte B, Don Arturo, Barrio Norte, Talca, Región del Maule, Chile"},
    {"desde": "10:07:00", "hasta": "10:21:00", "min": 15, "lugar": "Arturo Prat, El Culenar Sur, La Florida, Talca, Región del Maule, Chile"},
]


def test_calles_numeradas_se_comparan_por_numero_y_direccion():
    # "18 ORIENTE" NO es "6 Oriente" ni "Barrio Norte"; "1 SUR" NO es "Culenar Sur" (esto salía como «calza» por comparar solo "oriente"/"sur")
    assert estados([entrega("18 ORIENTE 480", "Talca"), entrega("1 SUR 2227", "Talca"), entrega("17 ORIENTE 801", "Talca")], TALCA) == ["comuna", "comuna", "comuna"]
    # "6 ORIENTE" sí es la parada «6 Oriente»; el orden de la esquina no importa
    assert estados([entrega("14 NORTE 6 ORIENTE 1297", "Talca")], TALCA) == ["comuna"]  # falta "14 norte": no se afirma
    assert estados([entrega("6 ORIENTE 1399 ESQUINA 3 NORTE", "Talca")], TALCA) == ["comuna"]
    assert estados([entrega("6 ORIENTE 55", "Talca")], TALCA) == ["calza"]


def test_numeros_en_letras():
    paradas = [{"desde": "10:00:00", "hasta": "10:20:00", "min": 20, "lugar": "2 Sur, Población Ferroviaria, Talca, Región del Maule"}]
    assert estados([entrega("DOS SUR 1773 A1", "Talca")], paradas) == ["calza"]


def test_misma_comuna_no_inventa_la_parada():
    paradas = [{"desde": "09:25:00", "hasta": "09:33:00", "min": 9, "lugar": "Cruce J-60, Dollimo, Constitución, Región del Maule"},
               {"desde": "10:30:00", "hasta": "10:59:00", "min": 29, "lugar": "Freire, Población La Poza, Constitución, Región del Maule"}]
    r = cruzar_entregas([entrega("KM 5 CAMINO SAN JAVIER", "Constitución")], paradas)
    it = r["entregas"][0]
    assert it["estado"] == "comuna" and it["parada"] is None and it["parada_idx"] is None
    assert [p["desde"] for p in it["paradas_comuna"]] == ["09:25:00", "10:30:00"]
    assert r["paradas"] == [None, None]


def test_resumen():
    r = cruzar_entregas([entrega("AV BERNARDO O'HIGGINS 1", "San Fernando"), entrega("X 1", "Curicó"), entrega("Y 1", "Romeral")], PARADAS)
    assert r["resumen"] == {"total": 3, "calza": 1, "cercana": 0, "comuna": 1, "lejos": 0, "sin_parada": 1}
