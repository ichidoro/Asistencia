import asyncio

import pytest

from backend.core.config import settings
from backend.services import whatsapp_service as wa


@pytest.mark.parametrize("entrada,esperado", [
    ("9 1234 5678", "56912345678"), ("+56 9 1234 5678", "56912345678"), ("912345678", "56912345678"),
    ("56912345678", "56912345678"),
    ("1234 5678", None), ("", None), (None, None), ("22 345 678", None), ("12345", None), ("+1 415 555 2671", None),
])
def test_normalizar_telefono(entrada, esperado):
    assert wa.normalizar_telefono(entrada) == esperado


def test_apagado_no_envia_ni_llama(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", False)
    monkeypatch.setattr(settings, "WHATSAPP_GATEWAY_TOKEN", "x")

    async def no_debe(*a, **k):
        raise AssertionError("no debía llamar a la puerta")
    monkeypatch.setattr(wa, "_llamar", no_debe)
    assert asyncio.run(wa.enviar("912345678", "hola")) is False


def test_envia_con_numero_normalizado_y_no_lanza_si_falla(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_GATEWAY_TOKEN", "x")
    visto = {}

    async def falso(metodo, ruta, cuerpo=None):
        visto.update(ruta=ruta, cuerpo=cuerpo)
        return 200, {"ok": True}
    monkeypatch.setattr(wa, "_llamar", falso)
    assert asyncio.run(wa.enviar("9 1234 5678", "hola")) is True
    assert visto == {"ruta": "/enviar", "cuerpo": {"to": "56912345678", "text": "hola"}}
    assert asyncio.run(wa.enviar("123", "hola")) is False  # teléfono inválido

    async def roto(*a, **k):
        raise OSError("sin red")
    monkeypatch.setattr(wa, "_llamar", roto)
    assert asyncio.run(wa.enviar("912345678", "hola")) is False


def test_mensaje_semanal_falta_y_cumplida():
    from backend.services.whatsapp_resumen import armar_mensaje
    m = armar_mensaje("HANS ELLIOT", 169 * 60 + 30, 180 * 60, "2026-10-26", "2026-11-25", "2026-11-23")
    assert "Estimado/a Hans" in m and "*169:30 h* de 180:00 h" in m and "*94 %*" in m and "▰▰▰▰▰▰▰▰▰▱" in m
    assert "Pendiente: *10:30 h*" in m and "Plazo: 2 días" in m and "5:15 h por día" in m
    ok = armar_mensaje("Ana", 194 * 60 + 30, 180 * 60, "2026-10-26", "2026-11-25", "2026-11-25")
    assert "Meta cumplida*, con 14:30 h sobre lo exigido" in ok and "Pendiente" not in ok and "Plazo" not in ok


def test_destino_valido_acepta_grupo_o_celular():
    assert wa.destino_valido("120363025246125486@g.us") == "120363025246125486@g.us"
    assert wa.destino_valido("9 1234 5678") == "56912345678"
    assert wa.destino_valido("hola@g.us") is None and wa.destino_valido("123") is None and wa.destino_valido("") is None


def test_enviar_a_un_grupo_lo_manda_tal_cual(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_GATEWAY_TOKEN", "x")
    visto = {}

    async def falso(metodo, ruta, cuerpo=None):
        visto.update(cuerpo=cuerpo)
        return 200, {"ok": True}
    monkeypatch.setattr(wa, "_llamar", falso)
    assert asyncio.run(wa.enviar("120363025246125486@g.us", "hola")) is True
    assert visto["cuerpo"]["to"] == "120363025246125486@g.us"


def test_mensaje_jefatura_ordena_de_menor_a_mayor_avance():
    from backend.services.whatsapp_resumen import armar_mensaje_jefatura
    items = [
        {"nombre": "Ana", "acum": 100 * 60, "meta": 180 * 60},
        {"nombre": "Beto", "acum": 190 * 60, "meta": 180 * 60},
        {"nombre": "Cami", "acum": 50 * 60, "meta": 180 * 60},
    ]
    m = armar_mensaje_jefatura(items, "2026-10-26", "2026-11-25", "2026-11-23")
    assert "Meta cumplida: *1*" in m and "Pendientes: *2*" in m and "Avance promedio: *61 %*" in m
    assert m.index("Cami") < m.index("Ana") and "Beto" not in m
    assert "1. Cami · *28 %* · 50:00 de 180:00 h · faltan 130:00 h" in m


def test_destino_valido_acepta_contacto_del_telefono():
    assert wa.destino_valido("14155552671@s.whatsapp.net") == "14155552671@s.whatsapp.net"
    assert wa.destino_valido("56912345678@s.whatsapp.net") == "56912345678@s.whatsapp.net"
    assert wa.destino_valido("abc@s.whatsapp.net") is None


def test_buscar_contacto_por_nombre_en_cualquier_orden():
    from backend.services.whatsapp_resumen import buscar_contacto
    cs = [{"id": "1@s.whatsapp.net", "nombre": "Hans Valenzuela"}, {"id": "2@s.whatsapp.net", "nombre": "María José Pérez"}, {"id": "3@s.whatsapp.net", "nombre": "Pedro"}]
    assert buscar_contacto("HANS ELLIOT", "VALENZUELA", "VARGAS", cs)[1]["id"] == "1@s.whatsapp.net"
    assert buscar_contacto("Maria Jose", "Perez", "", cs)[0] == "ok"          # sin tildes y con segundo nombre
    assert buscar_contacto("Pedro", "Soto", "", cs) == ("ninguno", None)       # solo el primer nombre no alcanza
    assert buscar_contacto("Hans", "", "", cs) == ("ninguno", None)            # sin apellido no se arriesga
    assert buscar_contacto("Hans", "Vargas", "", cs) == ("ninguno", None)      # el apellido debe estar


def test_buscar_contacto_desempata_o_marca_ambiguo():
    from backend.services.whatsapp_resumen import buscar_contacto
    cs = [{"id": "1@s.whatsapp.net", "nombre": "Juan Soto"}, {"id": "2@s.whatsapp.net", "nombre": "Juan Pablo Soto"}]
    # el contacto que además trae el segundo nombre gana
    assert buscar_contacto("JUAN PABLO", "SOTO", "RIOS", cs)[1]["id"] == "2@s.whatsapp.net"
    # sin nada más para decidir hay dos posibles: no se elige
    estado, lista = buscar_contacto("JUAN", "SOTO", "", [{"id": "1@s.whatsapp.net", "nombre": "Juan Soto"}, {"id": "9@s.whatsapp.net", "nombre": "Soto Juan"}])
    assert estado == "ambiguo" and len(lista) == 2


def test_lo_fijado_a_mano_manda_sobre_la_busqueda_por_nombre():
    from backend.services.whatsapp_resumen import resolver_destino
    cs = [{"id": "1@s.whatsapp.net", "nombre": "Daniel Soto"}]
    # sin nada manual se busca por nombre
    assert resolver_destino("Daniel", "Soto", "", None, cs)[0] == "ok"
    # con asignación manual manda ella, aunque haya un contacto que calce
    est, c = resolver_destino("Daniel", "Soto", "", {"destino": "56911112222", "etiqueta": "Daniel Aguacol"}, cs)
    assert est == "manual" and c == {"id": "56911112222", "nombre": "Daniel Aguacol"}
    # una persona que no está en los contactos pero tiene número a mano sí queda con destino
    assert resolver_destino("Ana", "Rojas", "", {"destino": "56933334444", "etiqueta": ""}, cs)[1]["nombre"] == "56933334444"
    assert resolver_destino("Ana", "Rojas", "", None, cs) == ("ninguno", None)


def test_filtro_por_area_y_cargo_acepta_varios_y_exige_cada_tipo():
    from backend.services.whatsapp_resumen import pasa_filtro
    assert pasa_filtro("Logística", "Chofer", None) is True and pasa_filtro("x", "y", {"areas": [], "cargos": []}) is True
    f = {"areas": ["Logística Tradicional", "Logística Retail"], "cargos": ["Chofer", "Peoneta"]}
    assert pasa_filtro("Logística Tradicional", "chofer", {"areas": ["logistica tradicional"], "cargos": []}) is True  # sin importar tildes ni mayúsculas
    assert pasa_filtro("Logística Tradicional", "Chofer", f) is True
    assert pasa_filtro("Logística Retail", "peoneta", f) is True               # cualquiera de las áreas y de los cargos
    assert pasa_filtro("Producción", "Chofer", f) is False                      # área fuera
    assert pasa_filtro("Logística Tradicional", "Supervisor", f) is False       # cargo fuera
    assert pasa_filtro("Producción", "Operario", {"areas": [], "cargos": ["Operario"]}) is True  # solo cargo
    assert pasa_filtro("  Logística   Retail ", "Chofer", {"areas": ["logística retail"], "cargos": []}) is True  # espacios y mayúsculas


def _camion(pat, v, edad=1, chofer="Juan Pérez", lugar="Ruta 5 Sur, Curicó", f="24-11-2026 10:32:10"):
    return {"patente": pat, "chofer": chofer, "edadMin": edad, "ultimo": {"v": v, "lugar": lugar, "f": f}}


def test_alerta_velocidad_detecta_solo_sobre_95_y_con_reporte_reciente():
    from backend.services.alerta_velocidad import detectar
    flota = [_camion("AA11", 95), _camion("BB22", 96.4), _camion("CC33", 120, edad=10), _camion("DD44", 101), {"patente": "EE55", "ultimo": None}]
    assert [e["patente"] for e in detectar(flota)] == ["DD44", "BB22"]


def test_alerta_velocidad_no_repite_dentro_de_15_min_y_olvida_al_que_baja():
    from backend.services.alerta_velocidad import nuevos
    mem = {}
    e = [{"patente": "AA11"}]
    assert nuevos(e, 1000, mem) == e
    mem["AA11"] = 1000
    assert nuevos(e, 1000 + 14 * 60, mem) == []
    assert nuevos(e, 1000 + 15 * 60, mem) == e
    assert nuevos([], 1000 + 20 * 60, mem) == [] and mem == {}


def test_alerta_velocidad_mensaje():
    from backend.services.alerta_velocidad import armar_mensaje, detectar
    m = armar_mensaje(detectar([_camion("AA11", 102.6)])[0])
    assert "*AA11*" in m and "Juan Pérez" in m and "*103 km/h* (límite 95 km/h)" in m and "10:32" in m and "Curicó" in m


def test_el_aviso_en_vivo_no_entra_al_cron_semanal():
    from backend.services.whatsapp_resumen import AVISOS
    assert AVISOS["exceso_velocidad"]["tiempo_real"] and AVISOS["exceso_velocidad"]["usa_chats"]


def test_alerta_velocidad_calza_al_chofer_con_su_contacto():
    from backend.services.alerta_velocidad import armar_mensaje, armar_mensaje_chofer, contacto_del_chofer, detectar
    choferes = [{"id": 7, "nombre": "Juan", "apellido_paterno": "Pérez", "apellido_materno": "Soto", "activo": 1, "nombre_completo": "Pérez Soto Juan"}]
    contactos = [{"id": "56911112222@s.whatsapp.net", "nombre": "Juan Pérez"}]
    est, c = contacto_del_chofer("Juan Pérez Soto", choferes, {}, contactos)
    assert est == "ok" and c["id"] == "56911112222@s.whatsapp.net"
    est, c = contacto_del_chofer("Juan Pérez Soto", choferes, {7: {"destino": "56999990000", "etiqueta": "Juan"}}, contactos)
    assert est == "manual" and c["id"] == "56999990000"   # lo fijado a mano manda
    assert contacto_del_chofer("Juan Pérez Soto", choferes, {}, [])[0] == "ninguno"
    assert contacto_del_chofer("", choferes, {}, contactos)[0] == "sin_chofer"
    e = detectar([_camion("AA11", 102.6)])[0]
    assert "Estimado/a Juan" in armar_mensaje_chofer(e) and "*102 km/h*" not in armar_mensaje_chofer(e) and "*103 km/h*" in armar_mensaje_chofer(e)
    e.update(estado_chofer="ninguno", destino_chofer=None)
    assert "no enviado (sin contacto en el teléfono)" in armar_mensaje(e)
    e.update(estado_chofer="ok", destino_chofer="x")
    assert "enviado a su WhatsApp" in armar_mensaje(e)


def test_destino_persona_de_asistencia_se_resuelve_por_nombre_o_a_mano():
    import asyncio
    from backend.services.whatsapp_resumen import resolver_destinos_chat

    class DB:
        async def fetch_one(self, q, p=None):
            return {"nombre": "Daniel", "apellido_paterno": "Rojas", "apellido_materno": "Mena"} if p == (5,) else None
    filas = [{"id": 1, "destino": "emp:5", "etiqueta": "Daniel Rojas"}, {"id": 2, "destino": "120363025246125486@g.us", "etiqueta": "Grupo"}, {"id": 3, "destino": "emp:9", "etiqueta": "Fantasma"}]
    contactos = [{"id": "56911112222@s.whatsapp.net", "nombre": "Daniel Rojas"}]
    r = asyncio.run(resolver_destinos_chat(DB(), filas, {}, contactos))
    assert [x["jid"] for x in r] == ["56911112222@s.whatsapp.net", "120363025246125486@g.us", None] and r[0]["estado"] == "ok" and r[2]["estado"] == "ninguno"
    r = asyncio.run(resolver_destinos_chat(DB(), filas[:1], {5: {"destino": "56999990000", "etiqueta": "x"}}, []))
    assert r[0]["jid"] == "56999990000" and r[0]["estado"] == "manual"
    assert asyncio.run(resolver_destinos_chat(DB(), filas[:1], {}, []))[0]["jid"] is None
