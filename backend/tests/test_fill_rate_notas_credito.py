"""Fill Rate: varias notas de crédito por día, razones que descuentan productos y hoja aparte en el cierre (dueño, 23-11-2026)."""
import asyncio
import os

import pytest

os.environ.setdefault("SECRET_KEY", "x" * 40)

from fastapi import HTTPException  # noqa: E402

from backend.routers.asistencia_bono_semanal import NotaCredito, _validar_notas  # noqa: E402
from backend.services.bono_semanal import notas_de  # noqa: E402
from backend.services.informe_cierre_pdf import hoja_fill_rate  # noqa: E402

RAZONES = [
    {"id": 1, "nombre": "ERROR CARGA CHOFER", "culpa_chofer": 1, "descuenta_productos": 0, "activa": 1},
    {"id": 2, "nombre": "VENTA NO SOLICITADA", "culpa_chofer": 0, "descuenta_productos": 0, "activa": 1},
    {"id": 3, "nombre": "EXTRAVÍO DE LA CARGA", "culpa_chofer": 1, "descuenta_productos": 1, "activa": 1},
    {"id": 4, "nombre": "VIEJA", "culpa_chofer": 0, "descuenta_productos": 0, "activa": 0},
]


class _Repo:
    def __init__(self, justificados=()):
        self.justificados = set(justificados)

    async def get_razones_nota_credito(self):
        return RAZONES

    async def justificacion_del_dia(self, empleado_id, fecha):
        return {"nombre": "DESCANSO OPERATIVO"} if empleado_id in self.justificados else None


def _validar(notas, personas=(10,), justificados=()):
    return asyncio.run(_validar_notas(_Repo(justificados), [NotaCredito(**n) for n in notas], list(personas),
                                      "2026-11-17", personas[0]))


# ── Validación de las notas del día ──────────────────────────────────

def test_varias_notas_con_numero_y_razon():
    out = _validar([{"numero": "45821", "razon_id": 2}, {"numero": "45822", "razon_id": 1}])
    assert [n["numero"] for n in out] == ["45821", "45822"]
    assert any(n["razon"]["culpa_chofer"] for n in out)


def test_no_se_acepta_nota_en_un_dia_justificado():
    with pytest.raises(HTTPException) as e:
        _validar([{"numero": "1", "razon_id": 2}], justificados={10})
    assert "DESCANSO OPERATIVO" in e.value.detail


def test_tampoco_si_un_peoneta_elegido_esta_justificado():
    with pytest.raises(HTTPException) as e:
        _validar([{"numero": "1", "razon_id": 2}], personas=(10, 20), justificados={20})
    assert "peoneta" in e.value.detail


def test_sin_notas_no_revisa_justificaciones():
    assert _validar([], justificados={10}) == []


def test_numero_repetido_se_rechaza():
    with pytest.raises(HTTPException):
        _validar([{"numero": "45821", "razon_id": 2}, {"numero": " 45821 ", "razon_id": 1}])


def test_razon_inactiva_se_rechaza():
    with pytest.raises(HTTPException):
        _validar([{"numero": "1", "razon_id": 4}])


def test_razon_que_descuenta_pide_el_valor():
    with pytest.raises(HTTPException) as e:
        _validar([{"numero": "9", "razon_id": 3}])
    assert "valor" in e.value.detail
    assert _validar([{"numero": "9", "razon_id": 3, "monto": 18500}])[0]["monto"] == 18500


def test_el_valor_solo_cuenta_si_la_razon_descuenta():
    assert _validar([{"numero": "9", "razon_id": 2, "monto": 5000}])[0]["monto"] == 0


# ── Notas de cada persona ─────────────────────────────────────────────

NOTAS = [
    {"empleado_id": 10, "fecha": "2026-11-12", "numero": "45821", "razon_nombre": "EXTRAVÍO DE LA CARGA", "culpa_chofer": 1,
     "descuenta": 1, "monto": 18500, "peonetas_ids": [20]},
    {"empleado_id": 10, "fecha": "2026-11-12", "numero": "45822", "razon_nombre": "VENTA NO SOLICITADA", "culpa_chofer": 0,
     "descuenta": 0, "monto": 0, "peonetas_ids": [20]},
]


def test_el_chofer_tiene_sus_notas_y_el_peoneta_las_ve_como_acompanante():
    chofer = notas_de(10, NOTAS, {})
    peoneta = notas_de(20, NOTAS, {})
    assert [n["rol"] for n in chofer] == ["chofer", "chofer"]
    assert [n["rol"] for n in peoneta] == ["peoneta", "peoneta"]
    assert notas_de(30, NOTAS, {}) == []


def test_una_marca_de_la_ventana_anterior_se_ve_sin_numero():
    out = notas_de(10, [], {"2026-11-03": {"tiene_nc": True, "razon_nc": "PRODUCTO DETERIORADO", "marca": "cumple"}})
    assert out[0]["numero"] is None and out[0]["razon"] == "PRODUCTO DETERIORADO" and not out[0]["culpa"]


# ── Hoja Fill Rate del cierre ─────────────────────────────────────────

def _persona(emp_id, nombre, cargo, semanas, notas, descuento, monto):
    return {"emp_id": emp_id, "rut": f"{emp_id}-K", "nombre": nombre, "cargo": cargo,
            "bonos_det": {"Fill Rate": {"semanas": semanas, "notas": notas, "descuento": descuento, "monto": monto}}}


SEM_OK = {"desde": "2026-11-09", "hasta": "2026-11-15", "estado": "pierde", "monto": 0, "monto_completo": 40000,
          "perdidos": [{"fecha": "2026-11-12", "causa": "No cumple"}], "dias_turno": 5}
SEM_PR = {"desde": "2026-11-02", "hasta": "2026-11-08", "estado": "proporcional", "monto": 32000, "monto_completo": 40000,
          "perdidos": [], "dias_turno": 5, "dias_proporcion": 1}


def test_hoja_con_semanas_notas_y_descuento_aparte():
    inf = {"personas": [
        _persona(10, "C.E.S.R.", "CHOFER", [SEM_PR, SEM_OK], notas_de(10, NOTAS, {}), 18500, 32000),
        _persona(20, "M.G.S.", "PEONETA", [SEM_PR, SEM_OK], notas_de(20, NOTAS, {}), 0, 24000),
        {"emp_id": 30, "rut": "30-K", "nombre": "SIN BONO", "bonos_det": {"Otro": {"semanas": None}}},
    ]}
    hojas = hoja_fill_rate(inf)
    assert len(hojas) == 1
    h = hojas[0]
    assert [f["nombre"] for f in h["filas"]] == ["C.E.S.R.", "M.G.S."]
    assert h["total_bono"] == 56000 and h["total_descuento"] == 18500      # el descuento no se resta del bono
    assert h["n_notas"] == 2 and h["n_descuentan"] == 1                   # las notas del chofer, sin repetir las del peoneta
    extravio = next(x for x in h["notas"] if x["numero"] == "45821")
    assert extravio["efecto"] == "Pierde la semana y descuenta" and extravio["monto"] == 18500
    assert extravio["quienes"] == ["C.E.S.R.", "M.G.S."]
    assert next(x for x in h["notas"] if x["numero"] == "45822")["efecto"] == "No afecta"
    celda = h["filas"][0]["celdas"]["2026-11-09"]
    assert celda["texto"] == "$0" and celda["nota"] == "No cumple 12-11"
    assert h["filas"][0]["celdas"]["2026-11-02"]["nota"] == "4 de 5 días"


def test_las_notas_sin_numero_se_cuentan_y_no_se_listan():
    viejas = notas_de(10, [], {"2026-11-03": {"tiene_nc": True, "razon_nc": "X", "marca": "cumple"}})
    h = hoja_fill_rate({"personas": [_persona(10, "C.E.S.R.", "CHOFER", [SEM_PR], viejas, 0, 32000)]})[0]
    assert h["notas"] == [] and h["sin_numero"] == 1 and h["n_notas"] == 0


def test_sin_bono_semanal_no_hay_hoja():
    assert hoja_fill_rate({"personas": [{"emp_id": 1, "rut": "1", "nombre": "X", "bonos_det": {}}]}) == []


# ── Semana que empieza en el período y termina en el siguiente (dueño, 23-11-2026) ──

from backend.services.bono_semanal import domingo_de, semana_siguiente, semanas_del_periodo  # noqa: E402


def test_la_semana_del_23_al_29_de_noviembre_es_la_que_sigue():
    lunes, domingo = semana_siguiente("2026-10-26", "2026-11-25")
    assert (lunes.isoformat(), domingo.isoformat()) == ("2026-11-23", "2026-11-29")
    # noviembre no la paga; diciembre sí, completa
    assert all(d.isoformat() <= "2026-11-22" for _, d in semanas_del_periodo("2026-10-26", "2026-11-25"))
    assert semanas_del_periodo("2026-11-26", "2026-12-25")[0][0].isoformat() == "2026-11-23"


def test_si_el_periodo_termina_en_domingo_no_hay_semana_que_siga():
    assert semana_siguiente("2026-10-26", "2026-11-22") is None


def test_el_bloqueo_lo_decide_el_domingo_de_la_semana():
    assert domingo_de("2026-11-24") == "2026-11-29"
    assert domingo_de("2026-11-29") == "2026-11-29"
    assert domingo_de("2026-11-16") == "2026-11-22"



def test_la_hoja_muestra_pendiente_la_semana_con_dias_sin_evaluar():
    sem = {"desde": "2026-11-16", "hasta": "2026-11-22", "estado": "por_evaluar", "monto": 0, "monto_completo": 40000,
           "perdidos": [], "dias_turno": 5, "faltan": ["2026-11-20", "2026-11-21"]}
    h = hoja_fill_rate({"personas": [_persona(10, "C.E.S.R.", "CHOFER", [sem], [], 0, 0)]})[0]
    c = h["filas"][0]["celdas"]["2026-11-16"]
    assert c["texto"] == "Pendiente" and c["nota"] == "Faltan 2 días"
