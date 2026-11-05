"""Revisión de la libreta contra el GPS (05-11-2026): límites desde los ajustes y descanso con que termina el día anterior."""
import asyncio
import json

from backend.services.libreta_revision import (AJUSTES_REVISION, SEMILLAS_REVISION, contexto_revision,
                                               descanso_final_minutos, limites_desde_ajustes)


def test_limites_se_convierten_a_minutos_y_kmh():
    filas = [{"clave": "libreta_conduccion_continua_max_horas", "valor": "5"},
             {"clave": "libreta_descanso_ininterrumpido_horas", "valor": "8,5"},
             {"clave": "libreta_tolerancia_gps_minutos", "valor": "15"},
             {"clave": "gps_velocidad_limite_kmh", "valor": "90"},
             {"clave": "otra_cosa", "valor": "3"}]
    assert limites_desde_ajustes(filas) == {"conduccion_continua_min": 300, "descanso_min": 510, "tolerancia_min": 15, "velocidad_kmh": 90}


def test_limite_que_falta_o_no_es_numero_queda_sin_valor():
    lim = limites_desde_ajustes([{"clave": "libreta_conduccion_continua_max_horas", "valor": "cinco"},
                                 {"clave": "gps_velocidad_limite_kmh", "valor": "0"}])
    assert lim == {"conduccion_continua_min": None, "descanso_min": None, "tolerancia_min": None, "velocidad_kmh": None}


def test_tolerancia_cero_es_valida():
    assert limites_desde_ajustes([{"clave": "libreta_tolerancia_gps_minutos", "valor": "0"}])["tolerancia_min"] == 0


def test_cada_limite_tiene_su_semilla():
    assert {c for c, _, _ in SEMILLAS_REVISION} == set(AJUSTES_REVISION)


def test_descanso_final_cuenta_solo_lo_ultimo_seguido():
    slots = [4] * 26 + [1] * 40 + [4] * 4 + [3] * 5 + [4] * 21
    assert descanso_final_minutos(slots) == 21 * 15
    assert descanso_final_minutos(json.dumps(slots)) == 21 * 15
    assert descanso_final_minutos([1] * 96) == 0
    assert descanso_final_minutos([4] * 96) == 96 * 15
    assert descanso_final_minutos(None) == 0


class _DB:
    def __init__(self, ajustes, asistencia=None):
        self.ajustes, self.asistencia, self.consultas = ajustes, asistencia, []

    async def fetch_all(self, sql, params=()):
        self.consultas.append(sql)
        return [a for a in self.ajustes if a["clave"] in params]

    async def fetch_one(self, sql, params=()):
        self.consultas.append(sql)
        return self.asistencia


class _Repo:
    def __init__(self, libretas):
        self.libretas = libretas

    async def get_libreta_180h(self, empleado_id, fecha):
        return self.libretas.get((empleado_id, fecha))


def test_contexto_con_libreta_del_dia_anterior():
    db = _DB([{"clave": "libreta_descanso_ininterrumpido_horas", "valor": "8"}])
    repo = _Repo({(82, "2026-10-25"): {"slots_96": json.dumps([1] * 76 + [4] * 20)}})
    ctx = asyncio.run(contexto_revision(db, repo, 82, "2026-10-26"))
    assert ctx["limites"]["descanso_min"] == 480 and ctx["limites"]["conduccion_continua_min"] is None
    assert ctx["dia_anterior"] == {"fecha": "2026-10-25", "tiene_libreta": True, "descanso_final_min": 300}
    assert all(s.lstrip().upper().startswith("SELECT") for s in db.consultas)   # solo lectura


def test_contexto_sin_libreta_del_dia_anterior_informa_su_estado():
    db = _DB([], asistencia={"estado": "PENDIENTE"})
    ctx = asyncio.run(contexto_revision(db, _Repo({}), 82, "2026-11-01"))
    assert ctx["dia_anterior"] == {"fecha": "2026-10-31", "tiene_libreta": False, "estado": "PENDIENTE"}
    ctx = asyncio.run(contexto_revision(_DB([]), _Repo({}), 82, "2026-11-01"))
    assert ctx["dia_anterior"]["estado"] is None
