"""Etapa B3a del plan de bonos (docs/PLAN_BONOS.md): qué pasa con cada bono en un día con justificación, y con una
inasistencia sin justificar, se configura en la pantalla (decisiones de la persona dueña, 21 y 22-11-2026: «se trata de
las justificaciones que pueden ser configuradas»; la inasistencia sin justificar hace perder el bono y también se
configura). Antes lo decidía el «Goce de sueldo», igual para todos los bonos, y el «Prop.» de la regla.

- Al crear la tabla se llena con lo de hoy (con goce = cuenta como asistido; sin goce = hace perder, o en proporción si
  el bono tenía «Prop.»), así nada cambia hasta que alguien lo configure.
- El cálculo solo lee lo configurado; si falta algo, el bono no se paga y el motivo lo dice.
- Una justificación o un bono nuevo no se guardan sin elegir todos los efectos.
Datos inventados; sin nombres de personas.
"""
import asyncio
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.repositories.configuracion import ConfiguracionRepository
from backend.services.bono_service import BonoService

RAIZ = Path(__file__).resolve().parents[2]
LICENCIA = {"tipo_id": 7, "tipo_nombre": "Licencia de prueba", "fecha_inicio": "2026-10-14", "fecha_fin": "2026-10-15",
            "con_goce_sueldo": 0}


def _matriz(inicio, fin, faltas=(), justificados=()):
    m = {"info": {"tipo_programacion": "CICLO", "turno_dias": {}}}
    d, f = date.fromisoformat(inicio), date.fromisoformat(fin)
    while d <= f:
        k = d.isoformat()
        if d.weekday() >= 5:
            m[k] = {"estado": "LIBRE", "horas_teoricas": 0}
        elif k in justificados:
            m[k] = {"estado": "LICENCIA DE PRUEBA", "horas_teoricas": 0}
        else:
            m[k] = {"estado": "INASISTENCIA" if k in faltas else "OK", "horas_teoricas": 8}
        d += timedelta(days=1)
    return m


def _dias_turno(inicio, fin):
    d, f, n = date.fromisoformat(inicio), date.fromisoformat(fin), 0
    while d <= f:
        n += d.weekday() < 5
        d += timedelta(days=1)
    return n


EMP = {"id": 1, "cargo": "OPERARIO", "tipo_contrato": "Indefinido", "fecha_ingreso": "2020-01-01"}
PI, PF = "2026-09-26", "2026-10-25"


def _bono(efecto_licencia=None, efecto_inas="pierde"):
    efectos = {7: efecto_licencia} if efecto_licencia else {}
    return {"nombre": "Bono de prueba", "activo": 1, "reglas": [{"monto": 70000}], "efecto_inasistencia": efecto_inas,
            "efectos": efectos}


def _calificar(bono, matriz, justif=(LICENCIA,)):
    return BonoService(None)._calificar_bono(EMP, bono, [], list(justif), matriz, "2026-11-22", PI, PF, set())


LIC = _matriz(PI, PF, justificados={"2026-10-14", "2026-10-15"})


def test_licencia_que_descuenta_en_proporcion():
    r = _calificar(_bono("proporcion"), LIC)
    turno = _dias_turno(PI, PF)
    assert r["califica"] is True and r["monto"] == round(70000 * (turno - 2) / turno)
    assert [d["fecha"] for d in r["perdidos"]] == ["2026-10-14", "2026-10-15"]


def test_licencia_que_hace_perder_el_bono():
    r = _calificar(_bono("pierde"), LIC)
    assert r["califica"] is False and r["monto"] == 0
    assert r["perdidos"][0]["causa"] == "Licencia de prueba"


def test_licencia_que_cuenta_como_asistido():
    r = _calificar(_bono("asistido"), LIC)
    assert r["califica"] is True and r["monto"] == 70000


def test_el_goce_de_sueldo_ya_no_decide_el_bono():
    # Con goce de sueldo, pero configurada para hacer perder el bono: lo hace perder
    con_goce = dict(LICENCIA, con_goce_sueldo=1)
    r = _calificar(_bono("pierde"), LIC, justif=(con_goce,))
    assert r["califica"] is False


def test_falta_configurar_no_se_paga_y_lo_dice():
    r = _calificar(_bono(None), LIC)
    assert r["califica"] is False and "Falta configurar" in r["perdidos"][0]["causa"]


def test_inasistencia_sin_justificar_segun_el_bono():
    m = _matriz(PI, PF, faltas={"2026-10-08"})
    pierde = _calificar(_bono(efecto_inas="pierde"), m, justif=())
    prop = _calificar(_bono(efecto_inas="proporcion"), m, justif=())
    falta = _calificar(_bono(efecto_inas=None), m, justif=())
    turno = _dias_turno(PI, PF)
    assert pierde["califica"] is False and pierde["perdidos"][0]["causa"] == "Inasistencia sin justificar"
    assert prop["califica"] is True and prop["monto"] == round(70000 * (turno - 1) / turno)
    assert falta["califica"] is False and "Falta configurar" in falta["perdidos"][0]["causa"]


def test_el_calculo_no_lee_el_goce_ni_el_prop():
    fuente = (RAIZ / "backend" / "services" / "bono_service.py").read_text(encoding="utf-8")
    assert "con_goce_sueldo" not in fuente and "es_proporcional" not in fuente and "aplica_bono_pagador" not in fuente


# ── la tabla se llena con lo de hoy ───────────────────────────────────────

class _DB:
    def __init__(self, reglas, tipos, bonos, cols_bonos=("id", "nombre")):
        self.reglas, self.tipos, self.bonos, self.cols_bonos = reglas, tipos, bonos, list(cols_bonos)
        self.efectos, self.inas, self.tablas = [], {}, set()

    async def fetch_all(self, q, p=()):
        if "FROM bono_reglas" in q:
            return self.reglas
        if "FROM justificacion_tipos" in q:
            return self.tipos
        if "FROM bonos" in q:
            return self.bonos
        return []

    async def get_column_names(self, t):
        return self.cols_bonos

    async def table_exists(self, t):
        return t in self.tablas

    async def execute(self, q, p=()):
        if q.startswith("UPDATE bonos SET efecto_inasistencia"):
            self.inas[p[1]] = p[0]
        if "CREATE TABLE" in q:
            self.tablas.add("bono_efectos")

    async def execute_batch(self, ops):
        for q, p in ops:
            if q.startswith("INSERT INTO bono_efectos"):
                self.efectos.append(p)


def test_la_tabla_se_llena_con_lo_que_pasa_hoy():
    db = _DB(reglas=[{"bono_id": 1, "es_proporcional": 0}, {"bono_id": 1, "es_proporcional": 0}, {"bono_id": 2, "es_proporcional": 1}],
             tipos=[{"id": 10, "con_goce_sueldo": 1}, {"id": 11, "con_goce_sueldo": 0}],
             bonos=[{"id": 1}, {"id": 2}])
    asyncio.run(ConfiguracionRepository(db)._init_efectos_bonos())
    assert sorted(db.efectos) == [(1, 10, "asistido"), (1, 11, "pierde"), (2, 10, "asistido"), (2, 11, "proporcion")]
    assert db.inas == {1: "pierde", 2: "proporcion"}


def test_la_tabla_no_se_vuelve_a_llenar():
    db = _DB(reglas=[], tipos=[{"id": 10, "con_goce_sueldo": 1}], bonos=[{"id": 1}],
             cols_bonos=("id", "efecto_inasistencia"))
    db.tablas.add("bono_efectos")
    asyncio.run(ConfiguracionRepository(db)._init_efectos_bonos())
    assert db.efectos == [] and db.inas == {}


# ── no se guarda sin elegir todos los efectos ─────────────────────────────

class _Repo:
    def __init__(self):
        self.guardado = {}

    async def get_ids_bonos(self):
        return [1, 2]

    async def get_ids_tipos_justificacion(self):
        return [10, 11]

    async def get_tipos_de_bonos(self):
        return {1: "pesos", 2: "pesos"}

    async def create_tipo_justificacion(self, tipo):
        return 99

    async def set_efectos_de_tipo(self, tipo_id, ef):
        self.guardado[tipo_id] = ef


def test_justificacion_nueva_no_se_guarda_sin_efecto_en_cada_bono():
    from fastapi import HTTPException
    from backend.schemas.justificacion import JustificacionTipoCreate
    from backend.services.configuracion_service import ConfiguracionService
    repo = _Repo()
    srv = ConfiguracionService(repo)
    with pytest.raises(HTTPException) as e:
        asyncio.run(srv.create_tipo_justificacion(JustificacionTipoCreate(nombre="Nueva", efectos_bonos={1: "pierde"})))
    assert e.value.status_code == 400 and "Falta elegir" in e.value.detail
    asyncio.run(srv.create_tipo_justificacion(JustificacionTipoCreate(nombre="Nueva", efectos_bonos={1: "pierde", 2: "proporcion"})))
    assert repo.guardado == {99: {1: "pierde", 2: "proporcion"}}


def test_bono_nuevo_no_se_guarda_sin_inasistencia_ni_efectos():
    from fastapi import HTTPException
    from backend.schemas.bono import BonoCreate
    from backend.services.configuracion_service import ConfiguracionService
    srv = ConfiguracionService(_Repo())
    for b in (BonoCreate(nombre="X", efectos={10: "asistido", 11: "pierde"}),
              BonoCreate(nombre="X", efecto_inasistencia="pierde", efectos={10: "asistido"})):
        with pytest.raises(HTTPException) as e:
            asyncio.run(srv._validar_efectos_bono(b, creando=True))
        assert e.value.status_code == 400


def test_las_pantallas_piden_los_efectos():
    js = (RAIZ / "frontend" / "js" / "configuracion_ui.js").read_text(encoding="utf-8")
    html = (RAIZ / "frontend" / "index.html").read_text(encoding="utf-8")
    # ficha de la justificación, ventana antigua (asistente) y ventana del bono
    assert "F.seccion('Efecto en los bonos')" in js and "efectos_bonos: efectos_bonos" in js
    assert 'id="tipo-j-efectos"' in html and "body.efectos_bonos = efT.valores" in js
    assert 'id="bono-efectos-container"' in html and "efecto_inasistencia: efectoInas, efectos: efJ.valores" in js
    # «Prop.» ya no se muestra
    assert "rule-proporcional" not in js


def test_nuevo_abre_la_ficha_aunque_la_lista_este_vacia():
    # Con la lista vacía no había espacio para la ficha y «Nuevo tipo» no abría nada (visto el 22-11-2026 en la copia
    # de práctica, que no tiene justificaciones)
    ficha = (RAIZ / "frontend" / "js" / "config_ficha.js").read_text(encoding="utf-8")
    assert "if (id === 'nuevo' && !o.cont.querySelector('.fcB-ficha')) { montar(o.cont, o); return; }" in ficha


def _matriz_bolsa(justificados):
    # Bolsa Flexible: sin horas de turno por día; lunes a viernes de turno y sábado y domingo libres en su horario
    m = {"info": {"tipo_programacion": "BOLSA_FLEXIBLE",
                  "turno_dias": {d: {"es_libre": 1 if d >= 5 else 0} for d in range(7)}}}
    d, f = date.fromisoformat(PI), date.fromisoformat(PF)
    while d <= f:
        k = d.isoformat()
        if k in justificados:
            m[k] = {"estado": "LICENCIA DE PRUEBA", "horas_teoricas": 0}
        elif d.weekday() >= 5:
            m[k] = {"estado": "LIBRE", "horas_teoricas": 0}
        else:
            m[k] = {"estado": "OK", "horas_teoricas": 0}
        d += timedelta(days=1)
    return m


def test_bolsa_cuenta_los_dias_justificados_como_ciclo():
    # Vacío M: en Bolsa el día justificado se saltaba y la persona no perdía el bono. Ahora se aplica lo configurado,
    # igual que en Ciclo; el sábado y el domingo libres de su horario no cuentan.
    lic = dict(LICENCIA, fecha_inicio="2026-10-16", fecha_fin="2026-10-19")      # viernes a lunes
    m = _matriz_bolsa({"2026-10-16", "2026-10-17", "2026-10-18", "2026-10-19"})
    m["2026-10-17"]["estado"] = m["2026-10-18"]["estado"] = "LIBRE"
    pierde = _calificar(_bono("pierde"), m, justif=(lic,))
    prop = _calificar(_bono("proporcion"), m, justif=(lic,))
    turno = _dias_turno(PI, PF)
    assert pierde["califica"] is False and [d["fecha"] for d in pierde["perdidos"]] == ["2026-10-16", "2026-10-19"]
    assert prop["califica"] is True and prop["monto"] == round(70000 * (turno - 2) / turno)
