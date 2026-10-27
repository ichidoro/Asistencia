from backend.services.gps_nexacol import _tokens_calle, cruzar_entregas, paso_coherente, pasos_por_direccion, tramos_movimiento

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


def test_misma_calle_y_comuna_no_es_calza():
    # La parada está en la misma calle, pero el GPS no da el número ni la cuadra: se dice «misma calle», no «calza»
    r = cruzar_entregas([entrega("AV BERNARDO O'HIGGINS 1234", "San Fernando")], PARADAS)
    it = r["entregas"][0]
    assert it["estado"] == "calle" and it["via"] == "direccion" and it["parada_idx"] == 0
    assert r["paradas"][0]["cliente"] == "X" and r["paradas"][1] is None


def test_la_comuna_se_compara_por_palabras():
    paradas = [{"desde": "10:00:00", "hasta": "10:20:00", "min": 20, "lugar": "San Guillermo, Villa Mostazal, San Francisco de Mostazal, Región del Libertador"}]
    assert estados([entrega("SAN GUILLERMO 49", "San Francisco Mostazal")], paradas) == ["calle"]


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
    # "18 ORIENTE" NO es "6 Oriente" ni "Barrio Norte"; "1 SUR" NO es "Culenar Sur" (esto salía como coincidencia por comparar solo "oriente"/"sur")
    assert estados([entrega("18 ORIENTE 480", "Talca"), entrega("1 SUR 2227", "Talca"), entrega("17 ORIENTE 801", "Talca")], TALCA) == ["comuna", "comuna", "comuna"]
    assert estados([entrega("6 ORIENTE 55", "Talca")], TALCA) == ["calle"]
    # "16 1/2 NORTE" es la parada «16½ Norte»
    assert estados([entrega("16 1/2 NORTE 1795 B", "Talca")], TALCA) == ["calle"]


def test_esquina_que_coincide_con_una_sola_calle_se_avisa():
    # «14 Norte con 6 Oriente» y la parada «6 Oriente»: coincide UNA de las dos calles, y no se sabe en qué cuadra paró
    it = cruzar_entregas([entrega("14 NORTE 6 ORIENTE 1297", "Talca")], TALCA)["entregas"][0]
    assert it["estado"] == "calle" and it["esquina"] is True and it["coincide"] == ["6 oriente"]
    assert cruzar_entregas([entrega("6 ORIENTE 55", "Talca")], TALCA)["entregas"][0]["esquina"] is False
    # una parada que coincide con las dos calles de la esquina se prefiere
    paradas = TALCA + [{"desde": "12:00:00", "hasta": "12:05:00", "min": 5, "lugar": "6 Oriente, 14 Norte, Talca, Región del Maule"}]
    it = cruzar_entregas([entrega("14 NORTE 6 ORIENTE 1297", "Talca")], paradas)["entregas"][0]
    assert it["parada_idx"] == 3 and sorted(it["coincide"]) == ["14 norte", "6 oriente"]


def test_numeros_en_letras():
    paradas = [{"desde": "10:00:00", "hasta": "10:20:00", "min": 20, "lugar": "2 Sur, Población Ferroviaria, Talca, Región del Maule"}]
    assert estados([entrega("DOS SUR 1773 A1", "Talca")], paradas) == ["calle"]


def test_misma_comuna_no_inventa_la_parada():
    paradas = [{"desde": "09:25:00", "hasta": "09:33:00", "min": 9, "lugar": "Cruce J-60, Dollimo, Constitución, Región del Maule"},
               {"desde": "10:30:00", "hasta": "10:59:00", "min": 29, "lugar": "Freire, Población La Poza, Constitución, Región del Maule"}]
    r = cruzar_entregas([entrega("KM 5 CAMINO SAN JAVIER", "Constitución")], paradas)
    it = r["entregas"][0]
    assert it["estado"] == "comuna" and it["parada"] is None and it["parada_idx"] is None
    assert [p["desde"] for p in it["paradas_comuna"]] == ["09:25:00", "10:30:00"]
    assert r["paradas"] == [None, None]


def test_una_sola_parada_en_la_comuna_se_muestra_sin_marcarla():
    it = cruzar_entregas([entrega("Los Aromos 9", "Curicó")], PARADAS)["entregas"][0]
    assert it["estado"] == "comuna" and it["parada_idx"] == 1 and it["parada"]["desde"] == "11:00:00"
    assert cruzar_entregas([entrega("Los Aromos 9", "Curicó")], PARADAS)["paradas"] == [None, None]


def test_resumen():
    r = cruzar_entregas([entrega("AV BERNARDO O'HIGGINS 1", "San Fernando"), entrega("X 1", "Curicó"), entrega("Y 1", "Romeral")], PARADAS)
    assert r["resumen"] == {"total": 3, "calza": 0, "calle": 1, "cercana": 0, "comuna": 1, "lejos": 0, "sin_parada": 1}


def test_tramos_de_conduccion_con_su_hora_exacta():
    pts = [{"s": s, "v": v} for s, v in ((3600, 20), (3630, 25), (3660, 0), (4000, 0), (4030, 30), (4060, 40), (4090, 0))]
    # anda de 3600 a 3660 (llega a la parada), está detenido hasta 4030, y vuelve a andar de 4030 a 4090: el primero dura 60 s (< 2 min) y no se dibuja
    assert tramos_movimiento(pts) == []
    pts = [{"s": s, "v": v} for s, v in ((3600, 20), (3700, 25), (3760, 18), (3800, 0), (4200, 0), (4230, 30), (4400, 35), (4440, 0))]
    assert tramos_movimiento(pts) == [[3600, 3800], [4230, 4440]]
    # un hueco de más de 15 min sin reportes no cuenta como conducción
    assert tramos_movimiento([{"s": 1000, "v": 30}, {"s": 3000, "v": 30}]) == []


PASOS = [
    {"nombre": "Ruta 5 Sur", "desde": 24000, "hasta": 28000, "la": -35.0, "lo": -71.2},
    {"nombre": "Calle 14 Norte", "desde": 31620, "hasta": 31680, "la": -35.42, "lo": -71.65},
    {"nombre": "6 Oriente", "desde": 31680, "hasta": 33000, "la": -35.42, "lo": -71.65},
    {"nombre": "Pasaje 16½ Norte B", "desde": 33120, "hasta": 33200, "la": -35.42, "lo": -71.65},
    {"nombre": "Calle 14 Norte", "desde": 50000, "hasta": 50100, "la": -34.0, "lo": -70.9},   # otra ciudad: 160 km de Talca
]


def paso(calle, comuna="Talca", **k):
    e = {"cliente": "X", "calle": calle, "comuna": comuna, "comuna_la": -35.4264, "comuna_lo": -71.6554, **k}
    return pasos_por_direccion([e], PASOS)[0]


def test_paso_por_la_calle_y_por_la_esquina():
    r = paso("14 NORTE 6 ORIENTE 1297")
    assert r["estado"] == "paso" and r["esquina"] is True and r["coincide"] == ["14 norte", "6 oriente"]
    assert [x["desde"] for x in r["pasadas"]] == ["08:47", "08:48"]   # la «14 Norte» de otra ciudad no cuenta
    assert paso("16 1/2 NORTE 1795 B")["estado"] == "paso"


def test_no_paso_por_la_calle():
    r = paso("17 ORIENTE 801")
    assert r["estado"] == "no_paso" and r["pasadas"] == []


def test_una_esquina_con_una_sola_calle_recorrida_no_es_esquina():
    r = paso("14 NORTE 1 SUR 55")
    assert r["estado"] == "paso" and r["esquina"] is False


def test_la_calle_de_otra_ciudad_no_cuenta():
    assert pasos_por_direccion([{"calle": "14 NORTE 5", "comuna": "Curicó", "comuna_la": -34.98, "comuna_lo": -71.23}], PASOS)[0]["estado"] == "no_paso"


def test_si_paro_en_la_calle_entonces_paso_por_ella():
    # «Misma calle» (hubo una parada en esa calle) junto a «no se detectó que pasara» era una contradicción
    it = cruzar_entregas([entrega("6 ORIENTE 55", "Talca")], TALCA)["entregas"][0]
    assert it["estado"] == "calle"
    r = paso_coherente(it, {"estado": "no_paso", "pasadas": [], "esquina": False, "coincide": []})
    assert r["estado"] == "paso" and r["origen"] == "parada" and r["pasadas"][0]["desde"] == "08:49"
    # lo que sí se detectó por el recorrido no se pisa; y una entrega sin parada sigue en «no_paso»
    real = {"estado": "paso", "pasadas": [{"nombre": "6 Oriente", "desde": "08:48", "hasta": "08:50"}], "esquina": False, "coincide": ["6 oriente"]}
    assert paso_coherente(it, real) is real
    sin = cruzar_entregas([entrega("Los Aromos 9", "Romeral")], PARADAS)["entregas"][0]
    assert paso_coherente(sin, {"estado": "no_paso"})["estado"] == "no_paso"


def test_comuna_grande_se_acepta_si_es_de_las_dos_mas_cercanas():
    # Un punto de Talca a más de 12 km de su centro (por polígono) sigue siendo de Talca; una calle con el mismo nombre en Curicó, no
    pasos = [{"nombre": "Camino Los Aromos", "desde": 30000, "hasta": 30100, "la": -35.525, "lo": -71.575}]
    e = {"calle": "CAMINO LOS AROMOS 5", "comuna": "Talca", "comuna_la": -35.4264, "comuna_lo": -71.6554}
    assert pasos_por_direccion([e], pasos)[0]["estado"] == "paso"
    assert pasos_por_direccion([{**e, "comuna": "Curicó", "comuna_la": -34.98, "comuna_lo": -71.23}], pasos)[0]["estado"] == "no_paso"


def test_comunas_por_poligono():
    from backend.services import comunas_geo as cg
    assert cg.comuna_en(-35.4264, -71.6554) == "07101"      # Talca
    assert cg.comuna_en(-34.1708, -70.7444) == "06101"      # Rancagua
    assert cg.comuna_en(-34.98, -71.23) == "07301"          # Curicó
    assert cg.comuna_en(-33.0, -60.0) is None               # fuera de los límites
    assert cg.cut_de_nombre("Talca") == "07101"
    assert cg.cut_de_nombre("Sarmiento") == "07301"         # localidad de la comuna de Curicó
    assert cg.cut_de_nombre("San Francisco Mostazal") == cg.cut_de_nombre("Mostazal") is not None


def test_parada_de_la_comuna_aunque_su_direccion_no_la_nombre():
    # La dirección de la parada («Camino X, Chile») no nombra la comuna, pero el punto cae dentro de Curicó
    paradas = [{"desde": "10:00:00", "hasta": "10:20:00", "min": 20, "lugar": "Camino Rural, Chile", "la": -34.98, "lo": -71.23}]
    it = cruzar_entregas([entrega("Los Aromos 9", "Curicó")], paradas)["entregas"][0]
    assert it["estado"] == "comuna"
    # y una calle recorrida dentro de la comuna cuenta; una de igual nombre en otra comuna, no
    e = {"calle": "CAMINO LOS AROMOS 5", "comuna": "Curicó", "comuna_la": -34.98, "comuna_lo": -71.23}
    en = {"nombre": "Camino Los Aromos", "desde": 30000, "hasta": 30100, "la": -34.95, "lo": -71.28}      # dentro de Curicó
    fuera = {"nombre": "Camino Los Aromos", "desde": 30000, "hasta": 30100, "la": -35.4264, "lo": -71.6554}   # Talca
    assert pasos_por_direccion([e], [en])[0]["estado"] == "paso"
    assert pasos_por_direccion([e], [fuera])[0]["estado"] == "no_paso"
