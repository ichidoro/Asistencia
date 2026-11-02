from backend.core.rut import _dv, rut_sin_prefijo, rut_visible


def con_dv(cuerpo: str) -> str:
    return cuerpo + _dv(cuerpo)


def test_un_rut_normal_no_se_toca():
    r = con_dv("12345678")
    assert rut_sin_prefijo(r) == r
    assert rut_visible(r) == f"12.345.678-{_dv('12345678')}"
    assert rut_sin_prefijo("12.345.678-" + _dv("12345678")) == r


def test_se_quita_el_nueve_antepuesto_a_un_rut_de_8_digitos():
    r = con_dv("12345678")
    assert rut_sin_prefijo("9" + r) == r


def test_se_quita_el_prefijo_de_un_rut_de_7_digitos_aunque_quede_de_9_caracteres():
    from backend.core.rut import _valido
    quitados = 0
    for cuerpo in range(7000001, 7000200):
        r = con_dv(str(cuerpo))
        s = "9" + r  # 9 caracteres: con el 9 delante el verificador casi siempre no calza, y sí calza el del RUT sin él
        if not _valido(s):
            assert rut_sin_prefijo(s) == r
            quitados += 1
    assert quitados > 150


def test_otros_prefijos_y_dv_k():
    r = con_dv("11111112")  # termina en K si corresponde
    assert rut_sin_prefijo("99" + r) == r
    assert rut_sin_prefijo("") == "" and rut_visible(None) == ""
    assert rut_visible("5") == "5"
