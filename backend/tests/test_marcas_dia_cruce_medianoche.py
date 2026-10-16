"""Panel "Marcaciones del día" con turnos que cruzan la medianoche (Ciclo Inteligente).

Caso real, turno Tarde 15:00-23:00 de Planta Mantención 2, 13 y 14-10-2026:
    13-10  Entrada 14:59:59  ·  Salida 00:08:17 (ya del 14 en el calendario)   → el cálculo del 13 cierra a las 00:08:17
    14-10  Entrada 15:05:11  ·  Salida 23:04:45
El cálculo estaba bien, pero el panel listaba las marcas por fecha de calendario: el 13 mostraba solo la Entrada ("hay una sola: confirme
cuál falta") y el 14 mostraba la Salida de las 00:08 como su primera marca ("La primera marca del día está como Salida"). Ahora cada
jornada muestra las marcas que su cálculo usó, aunque caigan al día siguiente, y no las que usó el turno de ayer.
"""
import asyncio
import json
import os
import types

import pytest
from fastapi import HTTPException

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.routers import asistencia as R  # noqa: E402

E, S = "Entrada", "Salida"
# (id, fecha_hora, tipo del reloj)
FOTOS = [(1, "2026-10-13 14:59:59", E), (2, "2026-10-14 00:08:17", S), (3, "2026-10-14 15:05:11", E), (4, "2026-10-14 23:04:45", S)]
USADAS_FOTOS = {"2026-10-13": [1, 2], "2026-10-14": [3, 4]}


class FakeDB:
    """Lo mínimo de la base que usa el panel: las marcas del reloj y las que usó el cálculo de cada día."""

    def __init__(self, marcas, usadas):
        self.marcas, self.usadas, self.overrides, self.ejecutadas = marcas, usadas, {}, []

    async def fetch_all(self, sql, params=()):
        q = " ".join(sql.split())
        if "FROM asistencias" in q:
            _, *fechas = params
            return [{"fecha": f, "marcas_consumidas_ids": json.dumps(self.usadas[f])} for f in fechas if f in self.usadas]
        if "logs_tipo_override o ON" in q:  # la vista con el tipo ya corregido
            _, desde, hasta = params
            return [{"id": i, "fecha_hora": fh, "tipo": self.overrides.get(i, t), "tipo_original": t, "manual": 0, "equipo": "R1"}
                    for i, fh, t in self.marcas if desde <= fh <= hasta]
        if q.startswith("SELECT id, tipo FROM logs_raw WHERE id IN"):
            *ids, _ = params
            return [{"id": i, "tipo": t} for i, _fh, t in self.marcas if i in ids]
        raise AssertionError("consulta no prevista: " + q)

    async def execute(self, sql, params=()):
        self.ejecutadas.append((" ".join(sql.split()), params))


class FakeRepo:
    def __init__(self, db, existentes=(), cerradas=()):
        self.db, self.existentes, self.cerradas = db, set(existentes), set(cerradas)

    async def check_fecha_cerrada(self, fecha, empleado_id=None):
        return fecha in self.cerradas

    async def get_asistencia(self, empleado_id, fecha):
        return {"fecha": fecha} if fecha in self.existentes else None


class FakeService:
    def __init__(self, repo):
        self.repository, self.procesados = repo, []

    async def procesar_empleado_dia(self, empleado_id, fecha, save=True, **kw):
        self.procesados.append(fecha)
        return {"fecha": fecha}


class FakeEmpleados:
    def __init__(self, db):
        pass

    async def get_by_id(self, empleado_id):
        return types.SimpleNamespace(area="MANTENCION")


class FakeUser:
    user_id, username = 1, "supervisor"

    def verificar_acceso_area(self, area, texto):
        pass


@pytest.fixture(autouse=True)
def _sin_base(monkeypatch):
    monkeypatch.setattr(R, "EmpleadoRepository", FakeEmpleados)


def _panel(fecha, marcas=FOTOS, usadas=USADAS_FOTOS):
    db = FakeDB(marcas, usadas)
    svc = FakeService(FakeRepo(db))
    return asyncio.run(R.marcaciones_del_dia(empleado_id=1, fecha=fecha, service=svc, current_user=FakeUser()))


def _horas(resp):
    return [m["hora"] for m in resp["marcas"]]


# ── El panel ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_dia_del_turno_tarde_muestra_la_salida_del_dia_siguiente_junto_a_su_entrada():
    r = _panel("2026-10-13")
    assert _horas(r) == ["14:59:59", "00:08:17"]                       # antes: solo la Entrada
    assert [m["fecha"] for m in r["marcas"]] == ["2026-10-13", "2026-10-14"]
    assert [m["sugerido"] for m in r["marcas"]] == ["Entrada", "Salida"]
    assert not any(m["dudoso"] for m in r["marcas"])                   # antes: "hay una sola: confirme cuál falta"


def test_dia_siguiente_no_muestra_la_salida_que_cerro_el_turno_de_ayer():
    r = _panel("2026-10-14")
    assert _horas(r) == ["15:05:11", "23:04:45"]                       # antes: 00:08:17 · 15:05:11 · 23:04:45
    assert [m["tipo_actual"] for m in r["marcas"]] == [E, S]
    assert not any(m["dudoso"] for m in r["marcas"])                   # antes: "La primera marca del día está como Salida"


def test_sin_calculo_previo_sigue_como_antes():
    # Si el día aún no se calculó no hay marcas usadas: se muestran las de la fecha del calendario (comportamiento anterior)
    assert _horas(_panel("2026-10-13", usadas={})) == ["14:59:59"]
    assert _horas(_panel("2026-10-14", usadas={})) == ["00:08:17", "15:05:11", "23:04:45"]


def test_turno_noche_la_salida_de_la_manana_es_del_dia_que_empezo_el_turno():
    marcas = [(1, "2026-09-28 22:48:10", E), (2, "2026-09-29 05:40:00", S), (3, "2026-09-29 08:50:00", S),
              (4, "2026-09-29 22:55:00", E), (5, "2026-09-30 07:03:00", S)]
    usadas = {"2026-09-28": [1, 2, 3], "2026-09-29": [4, 5]}
    assert _horas(_panel("2026-09-28", marcas, usadas)) == ["22:48:10", "05:40:00", "08:50:00"]
    assert _horas(_panel("2026-09-29", marcas, usadas)) == ["22:55:00", "07:03:00"]


def test_marca_que_nadie_uso_se_muestra_en_su_fecha_del_calendario():
    marcas = FOTOS + [(5, "2026-10-14 12:00:00", S)]
    assert _horas(_panel("2026-10-14", marcas, USADAS_FOTOS)) == ["12:00:00", "15:05:11", "23:04:45"]


# ── La sugerencia de Entrada/Salida y colación ───────────────────────────────────────────────────────────────────────────────────

def test_colacion_que_cruza_la_medianoche_se_detecta():
    horas = ["2026-09-28 22:00:00", "2026-09-28 23:50:00", "2026-09-29 00:30:00", "2026-09-29 06:00:00"]
    s = R.sugerir_clasificacion_marcas(horas)
    assert [x["tipo"] for x in s] == ["Entrada", "Salida", "Entrada", "Salida"]
    assert s[1]["colacion"] and s[2]["colacion"] and s[1]["colacion_min"] == 40   # antes: hueco negativo, no se detectaba


# ── Guardar la clasificación ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _reclasificar(fecha, marcas_req, existentes=(), cerradas=(), marcas=FOTOS, usadas=USADAS_FOTOS):
    db = FakeDB(marcas, usadas)
    svc = FakeService(FakeRepo(db, existentes, cerradas))
    req = R.ReclasificarMarcasRequest(empleado_id=1, fecha=fecha, marcas=[R.MarcaTipoItem(id=i, tipo=t) for i, t in marcas_req])
    resp = asyncio.run(R.reclasificar_marcaciones(req=req, service=svc, current_user=FakeUser()))
    return resp, db, svc


def test_se_puede_clasificar_la_salida_del_dia_siguiente_desde_el_dia_del_turno_y_se_recalculan_ambos_dias():
    resp, db, svc = _reclasificar("2026-10-13", [(1, "Entrada"), (2, "Salida")], existentes={"2026-10-14"})
    assert resp["success"] and svc.procesados == ["2026-10-13", "2026-10-14"]   # el 14 hereda las marcas que usó el 13


def test_cambiar_el_tipo_de_la_marca_del_dia_siguiente_queda_guardado_aparte():
    _, db, svc = _reclasificar("2026-10-13", [(1, "Entrada"), (2, "Entrada")], existentes={"2026-10-14"})
    inserts = [p for sql, p in db.ejecutadas if sql.startswith("INSERT INTO logs_tipo_override")]
    assert inserts == [(2, "Entrada", 1)]                                        # la marca cruda no se toca; solo se guarda el cambio


def test_no_se_puede_clasificar_desde_un_dia_una_marca_que_es_de_otro_turno():
    with pytest.raises(HTTPException) as e:
        _reclasificar("2026-10-14", [(2, "Salida"), (3, "Entrada"), (4, "Salida")])   # la 00:08 es del turno del 13
    assert e.value.status_code == 400


def test_no_recalcula_el_dia_siguiente_si_esta_cerrado_o_no_existe():
    _, _, svc = _reclasificar("2026-10-13", [(1, "Entrada"), (2, "Salida")], existentes={"2026-10-14"}, cerradas={"2026-10-14"})
    assert svc.procesados == ["2026-10-13"]
    _, _, svc = _reclasificar("2026-10-13", [(1, "Entrada"), (2, "Salida")])
    assert svc.procesados == ["2026-10-13"]
