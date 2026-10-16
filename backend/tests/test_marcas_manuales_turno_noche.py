"""Marcaciones manuales de turnos que cruzan la medianoche, y quitar una marca manual con registro.

Caso real, Eduardo Donoso (turno de noche), 11-10-2026: se ingresó a mano Entrada 23:00 y Salida 07:00 y las dos quedaron con fecha 11-10. La Salida
(07:00 del 11) cayó en el turno de la noche anterior, sin Entrada, y el panel del 10-10 pedía "ingrese la Entrada faltante" (falso positivo).
Ahora la Salida igual o anterior a la Entrada va al día siguiente, la marca guarda quién la ingresó, y una marca manual (nunca las del reloj) se
puede quitar con un permiso propio dejando en la auditoría su copia, quién la quitó y por qué.
"""
import asyncio
import json
import os
import types
from contextlib import asynccontextmanager

import pytest
from fastapi import HTTPException

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.routers import asistencia as R  # noqa: E402

E, S = "Entrada", "Salida"


# ── La regla de la fecha de la Salida ───────────────────────────────────────────────────────────────────────────────────────────

def test_turno_de_noche_la_salida_es_del_dia_siguiente():
    assert R.fecha_de_la_salida("2026-10-11", "07:00", "23:00") == "2026-10-12"          # antes: 2026-10-11 (el error del caso Donoso)
    assert R.fecha_de_la_salida("2026-10-31", "07:00:00", "23:00:00") == "2026-11-01"    # cambio de mes


def test_turno_de_dia_la_salida_es_del_mismo_dia():
    assert R.fecha_de_la_salida("2026-10-11", "15:00", "07:00") == "2026-10-11"


def test_salida_a_medianoche_o_igual_a_la_entrada_es_del_dia_siguiente():
    assert R.fecha_de_la_salida("2026-07-06", "00:00", "16:00") == "2026-07-07"          # Salida 00:00 = la medianoche que viene
    assert R.fecha_de_la_salida("2026-10-11", "07:00", "07:00") == "2026-10-12"


def test_sin_entrada_con_que_comparar_no_se_inventa_nada():
    assert R.fecha_de_la_salida("2026-10-11", "07:00") == "2026-10-11"
    assert R.fecha_de_la_salida("2026-10-11", "07:00", None) == "2026-10-11"


def test_el_turno_que_declara_cruzar_la_medianoche_manda():
    assert R.fecha_de_la_salida("2026-10-11", "07:00", None, cruza_medianoche=True) == "2026-10-12"
    assert R.fecha_de_la_salida("2026-10-11", "23:00", None, cruza_medianoche=False) == "2026-10-11"


def test_una_hora_que_no_existe_es_un_error():
    for mala in ("25:00", "7", "abc", "12:61"):
        with pytest.raises(ValueError):
            R.fecha_de_la_salida("2026-10-11", mala, "23:00")


# ── Lo mínimo de la base, del servicio y de las personas ───────────────────────────────────────────────────────────────────────

class FakeDB:
    """marcas: {id: {...}} de logs_raw · asistencias: [{fecha, marcas_consumidas_ids}] de un empleado."""

    def __init__(self, marcas=None, asistencias=()):
        self.marcas = {m["id"]: dict(m) for m in (marcas or [])}
        self.asistencias = list(asistencias)
        self.ejecutadas = []

    async def fetch_all(self, sql, params=()):
        q = " ".join(sql.split())
        if q.startswith("SELECT id, tipo FROM logs_raw WHERE empleado_id = ? AND substr(fecha_hora,1,10) = ? AND manual = 0"):
            emp, dia = params
            return [{"id": m["id"], "tipo": m["tipo"]} for m in self.marcas.values()
                    if m["empleado_id"] == emp and m["fecha_hora"][:10] == dia and not m["manual"]]
        if "FROM asistencias WHERE empleado_id = ? AND fecha IN" in q:
            _, *fechas = params
            return [a for a in self.asistencias if a["fecha"] in fechas]
        if "FROM logs_raw WHERE empleado_id = ? AND manual = 1 AND fecha_hora LIKE ?" in q:
            emp, like = params
            return [m for m in self.marcas.values() if m["empleado_id"] == emp and m["manual"] and m["fecha_hora"].startswith(like[:10])]
        raise AssertionError("consulta no prevista: " + q)

    async def fetch_one(self, sql, params=()):
        q = " ".join(sql.split())
        if "FROM logs_raw WHERE id = ?" in q:
            return self.marcas.get(params[0])
        if "substr(fecha_hora,1,10) = ? ORDER BY fecha_hora DESC LIMIT 1" in q:   # la última marca del día, con el tipo ya corregido
            emp, dia = params
            del_dia = sorted((m for m in self.marcas.values() if m["empleado_id"] == emp and m["fecha_hora"][:10] == dia),
                             key=lambda m: m["fecha_hora"])
            return del_dia[-1] if del_dia else None
        raise AssertionError("consulta no prevista: " + q)

    async def execute(self, sql, params=()):
        self.ejecutadas.append((" ".join(sql.split()), params))

    @asynccontextmanager
    async def transaction(self):
        yield self

    def sql(self, empieza):
        return [(s, p) for s, p in self.ejecutadas if s.startswith(empieza)]


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
        return types.SimpleNamespace(area="SEGURIDAD", rut="11111111-1")


class FakeUser:
    user_id, username, is_superuser = 7, "supervisor", False

    def verificar_acceso_area(self, area, texto):
        pass


class UserSinAcceso(FakeUser):
    def verificar_acceso_area(self, area, texto):
        raise HTTPException(status_code=403, detail="Sin acceso a esta área")


@pytest.fixture(autouse=True)
def _sin_base(monkeypatch):
    monkeypatch.setattr(R, "EmpleadoRepository", FakeEmpleados)


def _agregar(fecha="2026-10-11", hora=None, tipo=None, hora_entrada=None, hora_salida=None, marcas=(), existentes=(), cerradas=()):
    db = FakeDB(marcas)
    svc = FakeService(FakeRepo(db, existentes, cerradas))
    resp = asyncio.run(R.agregar_marcacion_manual(empleado_id=2, fecha=fecha, hora=hora, tipo=tipo, hora_entrada=hora_entrada,
                                                  hora_salida=hora_salida, observaciones=None, service=svc, current_user=FakeUser()))
    return resp, db, svc


def _insertadas(db):
    # (fecha_hora, tipo, usuario_id) de lo que se guardó en logs_raw
    return [(p[2], p[3], p[6]) for s, p in db.sql("INSERT OR IGNORE INTO logs_raw")]


def _entrada_sin_cerrar(hora, dia="2026-10-11"):
    return [{"id": 1, "empleado_id": 2, "fecha_hora": f"{dia} {hora}", "tipo": E, "manual": 0}]


# ── Ingresar una marca manual ───────────────────────────────────────────────────────────────────────────────────────────────────

def test_entrada_y_salida_de_noche_la_salida_queda_el_dia_siguiente():
    resp, db, svc = _agregar(hora_entrada="23:00", hora_salida="07:00")
    assert _insertadas(db) == [("2026-10-11 23:00:00", E, 7), ("2026-10-12 07:00:00", S, 7)]   # antes: las dos del 11 · y sin usuario
    assert "12-10" in resp["aviso"] and "8 h 00 min" in resp["aviso"]
    assert svc.procesados == ["2026-10-11"]


def test_turno_de_dia_no_cambia_nada_y_no_avisa():
    resp, db, svc = _agregar(hora_entrada="07:00", hora_salida="15:00")
    assert _insertadas(db) == [("2026-10-11 07:00:00", E, 7), ("2026-10-11 15:00:00", S, 7)]
    assert resp["aviso"] is None


def test_salida_sola_cierra_la_entrada_de_la_noche_con_la_fecha_del_dia_siguiente():
    resp, db, _ = _agregar(hora="07:00", tipo=S, marcas=_entrada_sin_cerrar("22:50:12"))
    assert _insertadas(db) == [("2026-10-12 07:00:00", S, 7)]
    assert "12-10" in resp["aviso"] and "8 h 10 min" in resp["aviso"]      # 22:50 → 07:00 son 490 min


def test_salida_sola_de_un_turno_de_dia_queda_en_su_fecha():
    resp, db, _ = _agregar(hora="15:00", tipo=S, marcas=_entrada_sin_cerrar("07:00:05"))
    assert _insertadas(db) == [("2026-10-11 15:00:00", S, 7)]
    assert resp["aviso"] is None


def test_salida_sola_sin_ninguna_entrada_no_inventa_el_dia_siguiente():
    _, db, _ = _agregar(hora="07:00", tipo=S)
    assert _insertadas(db) == [("2026-10-11 07:00:00", S, 7)]


def test_entrada_sola_queda_en_su_fecha():
    _, db, _ = _agregar(hora="23:00", tipo=E)
    assert _insertadas(db) == [("2026-10-11 23:00:00", E, 7)]


def test_si_el_dia_siguiente_esta_cerrado_no_se_agrega_nada():
    with pytest.raises(HTTPException) as e:
        _agregar(hora_entrada="23:00", hora_salida="07:00", cerradas={"2026-10-12"})
    assert e.value.status_code == 403 and "12-10" in e.value.detail


def test_se_recalcula_el_dia_siguiente_solo_si_ya_estaba_calculado_y_abierto():
    _, _, svc = _agregar(hora_entrada="23:00", hora_salida="07:00", existentes={"2026-10-12"})
    assert svc.procesados == ["2026-10-11", "2026-10-12"]
    _, _, svc = _agregar(hora_entrada="23:00", hora_salida="07:00")
    assert svc.procesados == ["2026-10-11"]


def test_una_hora_inventada_es_un_error_claro_y_no_guarda_nada():
    for kw in ({"hora_entrada": "23:00", "hora_salida": "99:99"}, {"hora": "7", "tipo": E}):
        with pytest.raises(HTTPException) as e:
            _agregar(**kw)
        assert e.value.status_code == 400 and "Hora inválida" in e.value.detail


def test_la_salida_00_00_de_una_entrada_matutina_sigue_ignorandose():
    _, db, _ = _agregar(hora_entrada="07:23", hora_salida="00:00")
    assert _insertadas(db) == [("2026-10-11 07:23:00", E, 7)]       # el blindaje de antes no cambia


# ── Quitar una marca manual ─────────────────────────────────────────────────────────────────────────────────────────────────────

# Las dos marcas del caso Donoso, ya guardadas (manual) y la Salida del 11 usada por el cálculo del 10
DONOSO = [
    {"id": 116704, "empleado_id": 2, "fecha_hora": "2026-10-11 23:00:00", "tipo": E, "manual": 1, "observaciones": "Marcación manual",
     "usuario_id": None, "created_at": "2026-10-16 03:58:32"},
    {"id": 116705, "empleado_id": 2, "fecha_hora": "2026-10-11 07:00:00", "tipo": S, "manual": 1, "observaciones": "Marcación manual",
     "usuario_id": None, "created_at": "2026-10-16 03:58:32"},
    {"id": 115771, "empleado_id": 2, "fecha_hora": "2026-10-10 04:23:53", "tipo": S, "manual": 0, "observaciones": None,
     "usuario_id": None, "created_at": "2026-10-10 07:25:08"},
]
USADAS_DONOSO = [{"fecha": "2026-10-10", "marcas_consumidas_ids": json.dumps([116705])},
                 {"fecha": "2026-10-11", "marcas_consumidas_ids": json.dumps([116704])}]


def _quitar(log_id, motivo="La Salida quedó con la fecha equivocada", cerradas=(), usuario=None, asistencias=USADAS_DONOSO):
    db = FakeDB(DONOSO, asistencias)
    svc = FakeService(FakeRepo(db, cerradas=cerradas))
    resp = asyncio.run(R.quitar_marcacion_manual(log_id=log_id, motivo=motivo, service=svc, current_user=usuario or FakeUser()))
    return resp, db, svc


def test_quitar_la_salida_mal_puesta_recalcula_el_dia_del_turno_y_el_de_su_fecha():
    resp, db, svc = _quitar(116705)
    assert db.sql("DELETE FROM logs_raw WHERE id = ? AND manual = 1") == [("DELETE FROM logs_raw WHERE id = ? AND manual = 1", (116705,))]
    assert resp["success"] and svc.procesados == ["2026-10-10", "2026-10-11"]    # el 10 la usaba como su Salida: se libera el falso positivo


def test_queda_en_la_auditoria_la_copia_quien_cuando_y_por_que_antes_de_quitarla():
    _, db, _ = _quitar(116705)
    (sql, p), = db.sql("INSERT INTO logs_auditoria")
    assert p[0:4] == (7, "supervisor", "ELIMINAR_MARCA_MANUAL", "MARCACIONES")
    det = json.loads(p[4])
    assert det["marca_id"] == 116705 and det["fecha_hora"] == "2026-10-11 07:00:00" and det["tipo"] == S
    assert det["motivo"] == "La Salida quedó con la fecha equivocada" and det["ingresada_el"] == "2026-10-16 03:58:32"
    orden = [s.split(" WHERE")[0] for s, _ in db.ejecutadas]
    assert orden.index("INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle, ip_address) VALUES (?, ?, ?, ?, ?, ?)") \
        < orden.index("DELETE FROM logs_raw")                                    # sin copia en la auditoría no se quita nada


def test_las_marcas_del_reloj_no_se_pueden_quitar():
    with pytest.raises(HTTPException) as e:
        _quitar(115771)
    assert e.value.status_code == 400 and "reloj" in e.value.detail


def test_el_motivo_es_obligatorio():
    for motivo in ("", "   ", "ok"):
        with pytest.raises(HTTPException) as e:
            _quitar(116705, motivo=motivo)
        assert e.value.status_code == 400 and "motivo" in e.value.detail


def test_marca_inexistente():
    with pytest.raises(HTTPException) as e:
        _quitar(999)
    assert e.value.status_code == 404


def test_no_se_quita_en_un_periodo_cerrado_ni_se_toca_nada():
    for cerradas in ({"2026-10-10"}, {"2026-10-11"}):                             # el día del turno o el de su fecha
        with pytest.raises(HTTPException) as e:
            _quitar(116705, cerradas=cerradas)
        assert e.value.status_code == 403 and "cerrado" in e.value.detail


def test_sin_acceso_al_area_del_empleado_no_se_quita():
    with pytest.raises(HTTPException) as e:
        _quitar(116705, usuario=UserSinAcceso())
    assert e.value.status_code == 403


def test_una_marca_que_ningun_dia_uso_solo_recalcula_su_propia_fecha():
    _, _, svc = _quitar(116704, asistencias=[])
    assert svc.procesados == ["2026-10-11"]


# ── El botón antiguo «quitar todas las manuales del día» ahora también deja registro ──────────────────────────────────────────

def test_quitar_todas_las_manuales_del_dia_deja_copia_en_la_auditoria():
    db = FakeDB(DONOSO)
    svc = FakeService(FakeRepo(db))
    resp = asyncio.run(R.eliminar_jornada_especial_manual(empleado_id=2, fecha="2026-10-11", service=svc, current_user=FakeUser()))
    assert resp["success"]
    (_, p), = db.sql("INSERT INTO logs_auditoria")
    assert p[2] == "ELIMINAR_MARCAS_MANUALES_DEL_DIA"
    assert sorted(m["marca_id"] for m in json.loads(p[4])["marcas"]) == [116704, 116705]   # solo las manuales; la del reloj no
    assert db.sql("DELETE FROM logs_raw")


def test_quitar_todas_las_manuales_de_un_dia_sin_manuales_no_escribe_auditoria():
    db = FakeDB(DONOSO)
    svc = FakeService(FakeRepo(db))
    asyncio.run(R.eliminar_jornada_especial_manual(empleado_id=2, fecha="2026-10-10", service=svc, current_user=FakeUser()))
    assert not db.sql("INSERT INTO logs_auditoria")
