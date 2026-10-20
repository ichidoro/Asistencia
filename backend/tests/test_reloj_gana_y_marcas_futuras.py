"""El reloj gana sobre la marca manual, y una marca manual no puede tener una hora que todavía no ocurre.

Caso real, Maximiliano Badilla (Mantención), sábado 17-10-2026: el usuario ingresó a las 09:28 una Entrada manual 07:00 y una Salida manual 14:00.
Después el reloj marcó Entrada 09:48:58 y Salida 15:44:47. El motor trataba la manual como cualquier otra marca ("dos Entradas seguidas: vale la
primera") y el día salía OK con 8,25 h y 224,8 min de horas extra pendientes, escondiendo 49 min de atraso. Ahora la marca del reloj manda y la
manual solo completa lo que falta; además el ingreso manual rechaza horas que todavía no llegan (ese día habían 57 marcas «anticipadas»).
"""
import asyncio
import os
import types
from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from fastapi import HTTPException

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.routers import asistencia as R  # noqa: E402
from backend.services import quantum_matrix_engine as qme  # noqa: E402
from backend.services.quantum_matrix_engine import QuantumMatrixEngine as Q  # noqa: E402
from backend.services.quantum_matrix_engine import TensorMarkDeduplicator as D  # noqa: E402
from backend.services.quantum_matrix_engine import MultiBlockTensorSolver as M  # noqa: E402

E, S = "Entrada", "Salida"


def L(i, fh, tipo, manual=0, obs=None):
    return {"id": i, "fecha_hora": fh, "tipo": tipo, "manual": manual, "observaciones": obs}


# ── La regla: el reloj gana ──────────────────────────────────────────────────────────────────────────────────────────────────────

BADILLA = [L(116944, "2026-10-17 07:00:00", E, 1), L(116964, "2026-10-17 09:48:58", E), L(116945, "2026-10-17 14:00:00", S, 1), L(116970, "2026-10-17 15:44:47", S)]


def test_caso_badilla_las_dos_manuales_ceden_ante_las_del_reloj():
    quedan, cubiertas = D.apply_clock_priority(BADILLA)
    assert [l["id"] for l in quedan] == [116964, 116970]                    # antes: las 4 marcas, y la Entrada 07:00 mandaba
    assert [(c["manual"]["id"], c["reloj"]["id"]) for c in cubiertas] == [(116944, 116964), (116945, 116970)]


def test_la_manual_que_completa_un_hueco_se_conserva():
    # El reloj marcó la Salida a colación pero no la del final del día: la manual de las 16:00 completa, no pisa (entre ambas hay una Entrada)
    marcas = [L(1, "2026-10-01 07:00:00", E), L(2, "2026-10-01 12:30:00", S), L(3, "2026-10-01 13:00:00", E), L(4, "2026-10-01 16:00:00", S, 1)]
    quedan, cubiertas = D.apply_clock_priority(marcas)
    assert [l["id"] for l in quedan] == [1, 2, 3, 4] and cubiertas == []


def test_manual_sola_o_varias_manuales_sin_reloj_no_se_tocan():
    assert D.apply_clock_priority([L(1, "2026-10-01 07:00:00", E, 1), L(2, "2026-10-01 15:00:00", S, 1)])[1] == []
    assert D.apply_clock_priority([L(1, "2026-10-01 07:00:00", E, 1), L(2, "2026-10-01 07:05:00", E, 1)])[1] == []


def test_la_manual_cede_aunque_este_despues_o_en_medio_de_las_del_reloj():
    marcas = [L(1, "2026-10-01 07:00:00", E), L(2, "2026-10-01 15:00:00", S), L(3, "2026-10-01 15:06:00", S, 1), L(4, "2026-10-01 15:09:00", S)]
    quedan, cubiertas = D.apply_clock_priority(marcas)
    assert [l["id"] for l in quedan] == [1, 2, 4]
    assert cubiertas[0]["manual"]["id"] == 3 and cubiertas[0]["reloj"]["id"] == 4   # en las Salidas manda la última del reloj, como el motor


def test_turno_de_noche_la_manual_de_las_23_cede_ante_la_entrada_real():
    marcas = [L(1, "2026-10-11 22:41:42", E), L(2, "2026-10-11 23:00:00", E, 1), L(3, "2026-10-12 07:06:13", S)]
    quedan, cubiertas = D.apply_clock_priority(marcas)
    assert [l["id"] for l in quedan] == [1, 3] and cubiertas[0]["manual"]["id"] == 2


def test_la_correccion_humana_explicita_sobreescritura_no_se_descarta():
    marcas = [L(1, "2026-10-01 07:00:00", E, 1, "[SOBREESCRITURA] el reloj marcó mal"), L(2, "2026-10-01 07:30:00", E), L(3, "2026-10-01 15:00:00", S)]
    quedan, cubiertas = D.apply_clock_priority(marcas)
    assert [l["id"] for l in quedan] == [1, 2, 3] and cubiertas == []        # esa vía sigue siendo la que manda sobre el reloj (apply_override_mask)


def test_una_marca_de_tipo_desconocido_corta_la_racha():
    marcas = [L(1, "2026-10-01 07:00:00", E, 1), L(2, "2026-10-01 07:10:00", "otro"), L(3, "2026-10-01 07:20:00", E)]
    assert D.apply_clock_priority(marcas)[1] == []


def test_sin_marcas():
    assert D.apply_clock_priority([]) == ([], [])


# ── Rebote entre una manual y una del reloj ─────────────────────────────────────────────────────────────────────────────────────

def test_rebote_manual_contra_reloj_del_mismo_tipo_queda_la_del_reloj():
    # Caso Chacón 01-10: Salida manual 20:00:00 y Salida del reloj 20:00:28 (28 s): antes quedaba la manual y se perdía la del reloj
    r = D.deduplicate_and_sort([L(1, "2026-10-01 11:16:00", E), L(2, "2026-10-01 20:00:00", S, 1), L(3, "2026-10-01 20:00:28", S)])
    assert [l["id"] for l in r] == [1, 3]


def test_rebote_entre_tipos_distintos_y_sobreescritura_siguen_como_antes():
    r = D.deduplicate_and_sort([L(1, "2026-10-01 07:23:37", E, 1), L(2, "2026-10-01 07:23:37", S)])
    assert [l["id"] for l in r] == [1]                                        # una manual que re-rotula una marca del reloj sigue valiendo
    r = D.deduplicate_and_sort([L(1, "2026-10-01 20:00:00", S, 1, "[SOBREESCRITURA]"), L(2, "2026-10-01 20:00:28", S)])
    assert [l["id"] for l in r] == [1]


# ── Dentro del cálculo del día ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_segment_blocks_deja_la_manual_como_consumida_y_anotada():
    res = M.segment_blocks(BADILLA)
    assert [l["id"] for l in res["bloque_principal"]] == [116964, 116970]
    assert {116944, 116945} <= set(res["marcas_consumidas_ids"])             # ningún día vecino la toma como suya
    assert len(res["manuales_cubiertas"]) == 2


AHORA_MOTOR = datetime(2026, 10, 19, 12, 0)
TURNO = {"tipo_programacion": "CICLO_INTELIGENTE", "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0,
         "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "umbral_horas_colacion": 5.5, "anclaje_entrada_minutos": 0, "anclaje_salida_minutos": 0}
SABADO = {"es_libre": 0, "horas_teoricas": 4.5, "descuento_colacion_auto": 1, "minutos_colacion_auto": 30, "anclaje_entrada_minutos": 0,
          "anclaje_salida_minutos": 0, "tolerancia_retraso_alerta": 0, "tolerancia_retraso_descuento": 0,
          "hora_entrada": "09:00", "hora_salida": "14:00", "cruza_medianoche": 0}


def _dia(monkeypatch, marcas):
    monkeypatch.setattr(qme, "_get_now_local", lambda: AHORA_MOTOR)
    return Q.solve_attendance_day(fecha="2026-10-17", empleado_id=36, logs=[dict(m) for m in marcas], turno_config=TURNO, dia_config=SABADO,
                                  global_ajustes={}, todos_ciclos_dia=[SABADO], consumidas_previas=set())


def test_el_dia_de_badilla_se_calcula_con_el_reloj_y_muestra_el_atraso(monkeypatch):
    r = _dia(monkeypatch, BADILLA)
    assert r["hora_entrada_real"] == "09:48:58" and r["hora_salida_real"] == "15:44:47"   # antes: 07:00:00 → 15:44:47
    assert round(r["minutos_atraso"]) == 49 and r["estado"] == "ATRASO"                  # antes: OK sin atraso
    assert abs(r["horas_trabajadas"] - 5.4303) < 0.01                                     # antes: 8,25 h
    assert set(r["marcas_consumidas_ids"]) == {116944, 116945, 116964, 116970}
    assert "Marca manual de las 07:00:00 (Entrada) sin usar: el reloj ya marcó a las 09:48:58." in r["observaciones"]
    assert "Marca manual de las 14:00:00 (Salida) sin usar: el reloj ya marcó a las 15:44:47." in r["observaciones"]


def test_el_dia_con_solo_marcas_manuales_sigue_igual(monkeypatch):
    r = _dia(monkeypatch, [L(1, "2026-10-17 09:00:00", E, 1), L(2, "2026-10-17 14:00:00", S, 1)])
    assert r["hora_entrada_real"] == "09:00:00" and r["hora_salida_real"] == "14:00:00" and "sin usar" not in r["observaciones"]


def test_la_manual_que_completa_la_salida_que_falta_sigue_valiendo(monkeypatch):
    r = _dia(monkeypatch, [L(1, "2026-10-17 09:00:00", E), L(2, "2026-10-17 14:00:00", S, 1)])
    assert r["hora_entrada_real"] == "09:00:00" and r["hora_salida_real"] == "14:00:00" and "sin usar" not in r["observaciones"]


# ── Una marca manual no puede tener una hora que todavía no ocurre ─────────────────────────────────────────────────────────────────

def test_el_limite_es_el_minuto_actual():
    ahora = datetime(2026, 10, 17, 9, 28, 30)
    assert not R._marca_en_el_futuro("2026-10-17 09:28:00", ahora)          # el formulario manda HH:MM: la hora de este minuto vale
    assert not R._marca_en_el_futuro("2026-10-17 07:00:00", ahora)
    assert R._marca_en_el_futuro("2026-10-17 09:29:00", ahora)
    assert R._marca_en_el_futuro("2026-10-17 14:00:00", ahora)
    assert R._marca_en_el_futuro("2026-10-18 07:00:00", ahora)


class FakeDB:
    def __init__(self):
        self.ejecutadas = []

    async def fetch_all(self, sql, params=()):
        return []

    async def fetch_one(self, sql, params=()):
        return None

    async def execute(self, sql, params=()):
        self.ejecutadas.append((" ".join(sql.split()), params))

    @asynccontextmanager
    async def transaction(self):
        yield self


class FakeRepo:
    def __init__(self, db):
        self.db = db

    async def check_fecha_cerrada(self, fecha, empleado_id=None):
        return False

    async def get_asistencia(self, empleado_id, fecha):
        return None


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
        return types.SimpleNamespace(area="MANTENCION", rut="11111111-1")


class FakeUser:
    user_id, username, is_superuser = 17, "jefe", False

    def verificar_acceso_area(self, area, texto):
        pass


@pytest.fixture(autouse=True)
def _sin_base(monkeypatch):
    monkeypatch.setattr(R, "EmpleadoRepository", FakeEmpleados)


def _ingresar(monkeypatch, ahora, fecha="2026-10-17", **kw):
    monkeypatch.setattr(qme, "_get_now_local", lambda: ahora)
    db = FakeDB()
    svc = FakeService(FakeRepo(db))
    args = dict(empleado_id=36, fecha=fecha, hora=None, tipo=None, hora_entrada=None, hora_salida=None, observaciones=None)
    args.update(kw)
    resp = asyncio.run(R.agregar_marcacion_manual(service=svc, current_user=FakeUser(), **args))
    return resp, db


def _insertadas(db):
    return [(p[2], p[3]) for s, p in db.ejecutadas if s.startswith("INSERT OR IGNORE INTO logs_raw")]


def test_el_caso_del_17_10_se_rechaza_la_salida_de_las_14_ingresada_a_las_09_28(monkeypatch):
    ahora = datetime(2026, 10, 17, 9, 28, 30)
    with pytest.raises(HTTPException) as e:
        _ingresar(monkeypatch, ahora, hora_entrada="07:00", hora_salida="14:00")
    assert e.value.status_code == 400
    assert "La marca de las 14:00 del 17-10 todavía no ocurre" in e.value.detail and "ahora son las 09:28 del 17-10" in e.value.detail


def test_si_alguna_marca_es_futura_no_se_guarda_ninguna_pero_la_pasada_se_puede_ingresar_sola(monkeypatch):
    ahora = datetime(2026, 10, 17, 9, 28, 30)
    resp, db = _ingresar(monkeypatch, ahora, hora="07:00", tipo=E)
    assert resp["success"] and _insertadas(db) == [("2026-10-17 07:00:00", E)]
    for kw in ({"hora": "14:00", "tipo": S}, {"hora": "09:29", "tipo": E}):
        with pytest.raises(HTTPException) as e:
            _ingresar(monkeypatch, ahora, **kw)
        assert e.value.status_code == 400


def test_la_hora_de_este_mismo_minuto_se_acepta(monkeypatch):
    resp, db = _ingresar(monkeypatch, datetime(2026, 10, 17, 9, 28, 30), hora="09:28", tipo=E)
    assert _insertadas(db) == [("2026-10-17 09:28:00", E)]


def test_dias_pasados_se_ingresan_completos_aunque_la_hora_sea_mas_tarde_que_la_actual(monkeypatch):
    resp, db = _ingresar(monkeypatch, datetime(2026, 10, 17, 9, 28, 30), fecha="2026-10-11", hora_entrada="23:00", hora_salida="07:00")
    assert _insertadas(db) == [("2026-10-11 23:00:00", E), ("2026-10-12 07:00:00", S)]


def test_el_turno_de_noche_de_hoy_no_deja_ingresar_su_salida_de_manana(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _ingresar(monkeypatch, datetime(2026, 10, 17, 23, 30, 0), hora_entrada="23:00", hora_salida="07:00")   # la Salida cae el 18-10 07:00
    assert "07:00 del 18-10" in e.value.detail
