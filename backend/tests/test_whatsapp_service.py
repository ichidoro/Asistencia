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
    assert "Hola Hans" in m and "169:30 h de 180:00 h (94 %)" in m
    assert "Le faltan 10:30 h" in m and "Quedan 2 día(s)" in m and "5:15 h por día" in m
    ok = armar_mensaje("Ana", 194 * 60 + 30, 180 * 60, "2026-10-26", "2026-11-25", "2026-11-25")
    assert "Ya cumplió la meta: 14:30 h sobre lo exigido" in ok and "Le faltan" not in ok and "Quedan" not in ok
