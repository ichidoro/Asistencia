# -*- coding: utf-8 -*-
"""Libreta Art. 25 bis: orden dentro del tramo, chofer y acompañantes, día validado y patente (plan del dueño, 04-11-2026).

- Un día NUEVO (o la inasistencia) solo se crea si los días anteriores del tramo ya tienen libreta; editar un día que ya tiene libreta no
  se frena por el orden.
- Chofer → acompañantes: copia automática mientras el día del chofer no está validado y el del acompañante sigue igual al del chofer; si
  no, solo a quienes se elijan (`replicar_a`). Sacar a un acompañante de la lista borra su copia. «Reasignar turno» no se frena por el orden.
- Peoneta enlazado: su cambio solo pasa al chofer si se elige; al chofer no se le cambia la patente.
- Día validado: solo con el permiso «Editar libreta validada»; sigue validado y queda en la auditoría.
- Período cerrado, día futuro y persona sin libreta también se rechazan; la patente se pide para validar el día de quien maneja.
"""
import asyncio
import json
import os
from datetime import datetime

import pytest
from fastapi import HTTPException

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.routers import asistencia as asist  # noqa: E402
from backend.schemas.asistencia import Libreta180hRequest  # noqa: E402
from backend.services import libreta_orden  # noqa: E402
from backend.services.velocidades_choferes import calzar_choferes, patentes_planificadas  # noqa: E402

HOY = datetime(2026, 11, 4, 12, 0)
NOMBRES = {10: ("JAIME ESTEBAN", "SOTO", "ROJAS"), 20: ("RODRIGO ESTEBAN", "VALENZUELA", "GALVEZ"), 30: ("JUAN", "PIÑA", "LONCOÑANCO"),
           40: ("RICHARD ALBERTO", "DROGUETT", "ARAVENA")}
TRAMOS_A = [1] * 8 + [0] * 88
TRAMOS_B = [1] * 12 + [0] * 84


class _Db:
    def __init__(self):
        self.auditoria = []

    async def fetch_all(self, sql, params=()):
        if "FROM empleados WHERE id IN" in sql:
            return [{"id": i, "nombre": NOMBRES[i][0], "apellido_paterno": NOMBRES[i][1], "apellido_materno": NOMBRES[i][2]} for i in params if i in NOMBRES]
        return []

    async def execute(self, sql, params=()):
        if "logs_auditoria" in sql:
            self.auditoria.append(params)


class _Repo:
    def __init__(self):
        self.db = _Db()
        self.libretas = {}       # (empleado, fecha) -> fila
        self.enlaces = {}        # (acompañante, fecha) -> chofer
        self.cerrados = set()    # (empleado, fecha)
        self.borrados = []

    async def get_libreta_180h(self, e, f):
        return self.libretas.get((e, f))

    async def get_libreta_borradores_180h(self, e, excepto):
        return [{"fecha": f, "observaciones": r.get("observaciones")} for (emp, f), r in sorted(self.libretas.items())
                if emp == e and f != excepto and not r.get("cerrado")]

    async def check_rango_cerrado(self, ini, fin, e=None):
        return (e, ini) in self.cerrados

    async def get_asignacion_vigente(self, e, f):
        return {"turno_id": 1}

    async def get_acompanantes_ocupados_180h(self, f, chofer):
        return {}

    async def upsert_libreta_180h(self, data):
        previo = self.libretas.get((data["empleado_id"], data["fecha"]), {})
        self.libretas[(data["empleado_id"], data["fecha"])] = {**previo, **data}

    async def set_acompanantes_180h(self, chofer, f, ids):
        for k in [k for k, v in self.enlaces.items() if v == chofer and k[1] == f]:
            del self.enlaces[k]
        for a in ids:
            self.enlaces[(a, f)] = chofer

    async def get_chofer_de_acompanante_180h(self, a, f):
        return self.enlaces.get((a, f))

    async def get_acompanantes_180h(self, chofer, f):
        return [a for (a, ff), c in self.enlaces.items() if c == chofer and ff == f]

    async def delete_libreta_180h(self, e, f):
        self.borrados.append((e, f))
        return self.libretas.pop((e, f), None) is not None


class _Servicio:
    def __init__(self):
        self.repository = _Repo()
        self.recalculados = []

    async def procesar_empleado_dia(self, e, f, save=True, force=False):
        self.recalculados.append((e, f))
        return {"estado": "OK"}


class _Usuario:
    def __init__(self, permisos=()):
        self.user_id, self.username, self._p = 9, "admin", set(permisos)

    def check_permission(self, p):
        return p in self._p


ADMIN = _Usuario([asist.PERMISO_EDITAR_LIBRETA_VALIDADA])


@pytest.fixture
def entorno(monkeypatch):
    servicio = _Servicio()
    pendientes = {}   # empleado -> días pendientes anteriores (para cualquier fecha)
    posteriores = {}

    async def pend(svc, e, f):
        return [p for p in pendientes.get(e, []) if p < f]

    async def post(svc, e, f):
        return posteriores.get(e, 0)

    monkeypatch.setattr(libreta_orden, "pendientes_anteriores", pend)
    monkeypatch.setattr(libreta_orden, "libretas_posteriores", post)
    monkeypatch.setattr(asist._motor, "_get_now_local", lambda: HOY)
    monkeypatch.setattr(asist.QuantumMatrixEngine, "resolve_control_modality", staticmethod(lambda a, f: True))
    return servicio, pendientes, posteriores


def _guardar(servicio, usuario=None, **k):
    datos = {"empleado_id": 10, "fecha": "2026-11-03", "slots_96": TRAMOS_A, "cerrado": True, **k}
    return asyncio.run(asist.save_libreta_180h(Libreta180hRequest(**datos), service=servicio, current_user=usuario or _Usuario()))


def _fila(e, f="2026-11-03", tramos=TRAMOS_A, cerrado=0, **k):
    return {"empleado_id": e, "fecha": f, "slots_96": json.dumps(tramos), "cerrado": cerrado, "observaciones": "", **k}


def _error(fn):
    with pytest.raises(HTTPException) as e:
        fn()
    return e.value


# ── Textos y datos ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_mensaje_dice_el_primer_dia_pendiente_con_su_dia_de_la_semana():
    assert libreta_orden.mensaje_pendiente(["2026-11-02"]) == "Primero completa el lunes 02-11-2026: la libreta se llena en orden dentro del tramo."
    assert "(y 2 días más después de ese)" in libreta_orden.mensaje_pendiente(["2026-11-02", "2026-11-03", "2026-11-05"])


def test_patente_normalizada_y_sin_camion_no_guarda_patente():
    assert libreta_orden.normalizar_patente(" kxzt12 ", "55", "PLAN") == {"patente": "KXZT12", "vehiculo_id": "55", "patente_origen": "PLAN"}
    assert libreta_orden.normalizar_patente("KXZT12", "55", "SIN_CAMION") == {"patente": None, "vehiculo_id": None, "patente_origen": "SIN_CAMION"}
    assert libreta_orden.normalizar_patente("KXZT12", None, "cualquiera")["patente_origen"] == "MANUAL"


def test_patentes_planificadas_calza_nombres_sin_orden_y_no_adivina():
    personas = [{"id": 10, "nombre_completo": "SOTO ROJAS JAIME ESTEBAN", "activo": 1},
                {"id": 11, "nombre_completo": "SOTO PEREZ CARLOS", "activo": 1},
                {"id": 12, "nombre_completo": "MUÑOZ DIAZ CARLOS", "activo": 1}]
    dias = [{"fecha": "2026-11-03", "patente": "AA1111", "choferes": ["Jaime Soto Rojas"], "velMax": None},
            {"fecha": "2026-11-03", "patente": "BB2222", "choferes": ["Jaime Esteban Soto"], "velMax": 80},
            {"fecha": "2026-11-03", "patente": "CC3333", "choferes": ["Carlos"], "velMax": 70},
            {"fecha": "2026-11-02", "patente": "DD4444", "choferes": ["Jaime Soto Rojas"], "velMax": 60}]
    assert patentes_planificadas(dias, personas, 10, "2026-11-03") == ["AA1111", "BB2222"]   # relevo: los dos camiones, sin exigir velocidad
    assert patentes_planificadas(dias, personas, 11, "2026-11-03") == []                     # «Carlos» es ambiguo: no se asigna
    por_emp, _ = calzar_choferes(dias, personas)                                             # el reporte de velocidades sigue igual
    assert por_emp["10"]["2026-11-03"]["patente"] == "BB2222"


def test_mismos_tramos_compara_lo_guardado_con_lo_nuevo():
    assert libreta_orden.mismos_tramos(_fila(1), {"slots_96": TRAMOS_A})
    assert not libreta_orden.mismos_tramos(_fila(1), {"slots_96": TRAMOS_B})


# ── Orden dentro del tramo ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_no_se_crea_un_dia_con_un_dia_anterior_pendiente(entorno):
    servicio, pendientes, _ = entorno
    pendientes[10] = ["2026-11-02"]
    e = _error(lambda: _guardar(servicio))
    assert e.status_code == 409 and "Primero completa el lunes 02-11-2026" in e.detail
    assert servicio.repository.libretas == {}


def test_editar_un_dia_que_ya_tiene_libreta_no_se_frena_por_el_orden(entorno):
    servicio, pendientes, _ = entorno
    pendientes[10] = ["2026-11-02"]
    servicio.repository.libretas[(10, "2026-11-03")] = _fila(10)
    _guardar(servicio, slots_96=TRAMOS_B, cerrado=False)
    assert libreta_orden.mismos_tramos(servicio.repository.libretas[(10, "2026-11-03")], {"slots_96": TRAMOS_B})


def test_sin_pendientes_el_dia_nuevo_queda_en_borrador(entorno):
    servicio, _, _ = entorno
    r = _guardar(servicio)
    assert r["data"]["forzado_borrador"] is True and servicio.repository.libretas[(10, "2026-11-03")]["cerrado"] == 0


def test_inasistencia_va_en_orden_y_reasignar_no(entorno):
    servicio, pendientes, _ = entorno
    pendientes[20] = ["2026-11-02"]
    req = asist.Libreta180hInasistenciaRequest(empleado_id=20, fecha="2026-11-03")
    assert _error(lambda: asyncio.run(asist.marcar_inasistencia_libreta_180h(req, service=servicio, current_user=_Usuario()))).status_code == 409
    servicio.repository.enlaces[(20, "2026-11-03")] = 10
    servicio.repository.libretas[(10, "2026-11-03")] = _fila(10)
    req2 = asist.Libreta180hReasignarRequest(empleado_id=20, fecha="2026-11-03")
    asyncio.run(asist.reasignar_turno_acompanante_180h(req2, service=servicio, current_user=_Usuario()))   # es la copia del chofer
    assert (20, "2026-11-03") in servicio.repository.libretas


def test_un_borrador_posterior_no_frena_completar_un_dia_anterior(entorno):
    servicio, _, _ = entorno
    servicio.repository.libretas[(10, "2026-11-04")] = _fila(10, "2026-11-04")
    _guardar(servicio, fecha="2026-11-03")
    servicio.repository.libretas[(10, "2026-11-01")] = _fila(10, "2026-11-01")
    e = _error(lambda: _guardar(servicio, fecha="2026-11-02"))
    assert e.status_code == 409 and "borrador del 01-11-2026" in e.detail


# ── Chofer → acompañantes ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_la_copia_se_hace_aunque_el_acompanante_tenga_un_dia_pendiente_y_se_avisa(entorno):
    servicio, pendientes, _ = entorno
    pendientes[20] = ["2026-11-02"]
    servicio.repository.enlaces[(20, "2026-11-02")] = 30
    r = _guardar(servicio, acompanantes=[20], patente="KXZT12", vehiculo_id="55", patente_origen="PLAN")
    copia = servicio.repository.libretas[(20, "2026-11-03")]
    assert copia["slots_96"] == TRAMOS_A and copia["patente"] == "KXZT12" and copia["patente_origen"] == "CHOFER"
    aviso = r["data"]["acompanantes_con_pendientes"][0]
    assert aviso["mensaje"] == ("Se copió el día a VALENZUELA GALVEZ RODRIGO ESTEBAN. Le queda pendiente el lunes 02-11-2026 "
                                "(con PIÑA LONCOÑANCO JUAN).")


def test_el_chofer_edita_su_borrador_y_la_copia_igual_se_actualiza_pero_la_ajustada_no(entorno):
    servicio, _, _ = entorno
    repo = servicio.repository
    repo.libretas[(10, "2026-11-03")] = _fila(10)
    repo.libretas[(20, "2026-11-03")] = _fila(20)                       # igual al chofer
    repo.libretas[(40, "2026-11-03")] = _fila(40, tramos=[3] * 10 + [0] * 86)   # ajustada aparte
    repo.enlaces.update({(20, "2026-11-03"): 10, (40, "2026-11-03"): 10})
    r = _guardar(servicio, slots_96=TRAMOS_B, cerrado=False, acompanantes=[20, 40])
    assert libreta_orden.mismos_tramos(repo.libretas[(20, "2026-11-03")], {"slots_96": TRAMOS_B})
    assert libreta_orden.mismos_tramos(repo.libretas[(40, "2026-11-03")], {"slots_96": [3] * 10 + [0] * 86})
    assert [n["motivo"] for n in r["data"]["no_copiados"]] == ["AJUSTADO"]
    r2 = _guardar(servicio, slots_96=TRAMOS_B, cerrado=False, acompanantes=[20, 40], replicar_a=[40])   # se eligió copiarle
    assert libreta_orden.mismos_tramos(repo.libretas[(40, "2026-11-03")], {"slots_96": TRAMOS_B}) and r2["data"]["no_copiados"] == []


def test_sacar_a_un_acompanante_borra_su_copia_salvo_si_esta_validada(entorno):
    servicio, _, _ = entorno
    repo = servicio.repository
    repo.libretas[(10, "2026-11-03")] = _fila(10)
    repo.libretas[(20, "2026-11-03")] = _fila(20)
    repo.libretas[(40, "2026-11-03")] = _fila(40, cerrado=1)
    repo.enlaces.update({(20, "2026-11-03"): 10, (40, "2026-11-03"): 10})
    r = _guardar(servicio, cerrado=False, acompanantes=[])
    assert (20, "2026-11-03") not in repo.libretas and (40, "2026-11-03") in repo.libretas
    estado = {s["empleado_id"]: s["borrado"] for s in r["data"]["sacados"]}
    assert estado == {20: True, 40: False}


def test_el_acompanante_de_un_periodo_cerrado_no_se_toca(entorno):
    servicio, _, _ = entorno
    servicio.repository.cerrados.add((20, "2026-11-03"))
    r = _guardar(servicio, acompanantes=[20])
    assert (20, "2026-11-03") not in servicio.repository.libretas and r["data"]["acompanantes_omitidos"] == [20]


# ── Peoneta enlazado ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_el_peoneta_solo_pasa_su_cambio_al_chofer_si_se_elige_y_no_le_cambia_la_patente(entorno):
    servicio, _, _ = entorno
    repo = servicio.repository
    repo.libretas[(10, "2026-11-03")] = _fila(10, patente="PKDD13", patente_origen="PLAN")
    repo.libretas[(20, "2026-11-03")] = _fila(20, patente="PKDD13", patente_origen="CHOFER")
    repo.enlaces[(20, "2026-11-03")] = 10
    _guardar(servicio, empleado_id=20, slots_96=TRAMOS_B, cerrado=False, acompanantes=[])
    assert libreta_orden.mismos_tramos(repo.libretas[(10, "2026-11-03")], {"slots_96": TRAMOS_A})   # el chofer no cambia solo
    _guardar(servicio, empleado_id=20, slots_96=TRAMOS_B, cerrado=False, acompanantes=[], replicar_a=[10])
    chofer = repo.libretas[(10, "2026-11-03")]
    assert libreta_orden.mismos_tramos(chofer, {"slots_96": TRAMOS_B}) and chofer["patente"] == "PKDD13" and chofer["patente_origen"] == "PLAN"


# ── Día validado ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_un_dia_validado_solo_se_edita_con_el_permiso_sigue_validado_y_queda_registrado(entorno):
    servicio, _, _ = entorno
    repo = servicio.repository
    repo.libretas[(10, "2026-11-03")] = _fila(10, cerrado=1, patente="PKDD13", patente_origen="PLAN", minutos_efectivos=120)
    assert _error(lambda: _guardar(servicio, slots_96=TRAMOS_B)).status_code == 409
    r = _guardar(servicio, ADMIN, slots_96=TRAMOS_B, cerrado=False)
    assert repo.libretas[(10, "2026-11-03")]["cerrado"] == 1 and r["data"]["editado_validado"] is True
    detalle = json.loads(repo.db.auditoria[-1][4])
    assert repo.db.auditoria[-1][2] == "EDITAR_LIBRETA_VALIDADA" and detalle["antes"]["minutos_efectivos"] == 120 and detalle["despues"]["minutos_efectivos"] == 180


def test_al_editar_un_dia_validado_del_chofer_la_copia_solo_va_si_se_elige(entorno):
    servicio, _, _ = entorno
    repo = servicio.repository
    repo.libretas[(10, "2026-11-03")] = _fila(10, cerrado=1, patente="PKDD13", patente_origen="PLAN")
    repo.libretas[(40, "2026-11-03")] = _fila(40, cerrado=1)
    repo.enlaces[(40, "2026-11-03")] = 10
    r = _guardar(servicio, ADMIN, slots_96=TRAMOS_B, acompanantes=[40])
    assert libreta_orden.mismos_tramos(repo.libretas[(40, "2026-11-03")], {"slots_96": TRAMOS_A})
    assert r["data"]["no_copiados"][0]["motivo"] == "EDICION_VALIDADA"
    _guardar(servicio, ADMIN, slots_96=TRAMOS_B, acompanantes=[40], replicar_a=[40])
    copia = repo.libretas[(40, "2026-11-03")]
    assert libreta_orden.mismos_tramos(copia, {"slots_96": TRAMOS_B}) and copia["cerrado"] == 1


# ── Vacíos y patente ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_periodo_cerrado_dia_futuro_y_persona_sin_libreta(entorno, monkeypatch):
    servicio, _, _ = entorno
    servicio.repository.cerrados.add((10, "2026-11-03"))
    assert _error(lambda: _guardar(servicio)).status_code == 403
    assert _error(lambda: _guardar(servicio, fecha="2026-11-05")).status_code == 400
    monkeypatch.setattr(asist.QuantumMatrixEngine, "resolve_control_modality", staticmethod(lambda a, f: False))
    e = _error(lambda: _guardar(servicio, fecha="2026-11-04"))
    assert e.status_code == 400 and "no se controla con libreta" in e.detail


def test_borrar_nunca_en_periodo_cerrado_y_avisa_los_dias_posteriores(entorno):
    servicio, _, posteriores = entorno
    servicio.repository.cerrados.add((10, "2026-10-20"))
    e = _error(lambda: asyncio.run(asist.delete_libreta_180h(empleado_id=10, fecha="2026-10-20", service=servicio, current_user=_Usuario())))
    assert e.status_code == 403 and servicio.repository.borrados == []
    posteriores[10] = 2
    r = asyncio.run(asist.delete_libreta_180h(empleado_id=10, fecha="2026-11-02", service=servicio, current_user=_Usuario()))
    assert r["dias_posteriores_con_libreta"] == 2 and "vuelve a quedar pendiente" in r["message"]


def test_validar_pide_la_patente_salvo_sin_camion_o_acompanante(entorno):
    servicio, _, _ = entorno
    _guardar(servicio)
    e = _error(lambda: _guardar(servicio))
    assert e.status_code == 409 and "falta la patente" in e.detail
    _guardar(servicio, patente_origen="SIN_CAMION")
    assert servicio.repository.libretas[(10, "2026-11-03")]["cerrado"] == 1
    servicio.repository.libretas[(20, "2026-11-03")] = _fila(20)
    servicio.repository.enlaces[(20, "2026-11-03")] = 10
    _guardar(servicio, empleado_id=20, acompanantes=[])
    assert servicio.repository.libretas[(20, "2026-11-03")]["cerrado"] == 1


def test_editar_un_dia_validado_antes_de_la_patente_no_la_pide(entorno):
    servicio, _, _ = entorno
    servicio.repository.libretas[(10, "2026-11-03")] = _fila(10, cerrado=1)          # validado cuando no existía la patente
    _guardar(servicio, ADMIN, slots_96=TRAMOS_B)
    assert libreta_orden.mismos_tramos(servicio.repository.libretas[(10, "2026-11-03")], {"slots_96": TRAMOS_B})


def test_sin_campos_de_patente_se_conserva_la_guardada(entorno):
    servicio, _, _ = entorno
    _guardar(servicio, patente="KXZT12", vehiculo_id="55", patente_origen="MANUAL")
    _guardar(servicio)
    fila = servicio.repository.libretas[(10, "2026-11-03")]
    assert fila["patente"] == "KXZT12" and fila["cerrado"] == 1


# ── Lo que la ventana sabe al abrir el día ──────────────────────────────────────────────────────────────────────────────────
def test_al_abrir_la_ventana_recibe_el_bloqueo_los_enlazados_y_el_permiso(entorno):
    servicio, pendientes, _ = entorno
    pendientes[10] = ["2026-11-02"]
    r = asyncio.run(asist.get_libreta_180h(empleado_id=10, fecha="2026-11-03", service=servicio, current_user=_Usuario()))
    assert r["bloqueo"]["motivo"] == "PENDIENTE_ANTERIOR" and r["puede_editar_validado"] is False
    repo = servicio.repository
    repo.libretas[(10, "2026-11-03")] = _fila(10, cerrado=1, patente="KXZT12")
    repo.libretas[(40, "2026-11-03")] = _fila(40, tramos=TRAMOS_B)
    repo.enlaces[(40, "2026-11-03")] = 10
    r2 = asyncio.run(asist.get_libreta_180h(empleado_id=10, fecha="2026-11-03", service=servicio, current_user=ADMIN))
    assert r2["bloqueo"] is None and r2["patente"] == "KXZT12" and r2["puede_editar_validado"] is True
    assert r2["enlazados"] == [{"empleado_id": 40, "nombre": "DROGUETT ARAVENA RICHARD ALBERTO", "rol": "acompañante",
                                "tiene_libreta": True, "validado": False, "distinto": True}]
    r3 = asyncio.run(asist.get_libreta_180h(empleado_id=40, fecha="2026-11-03", service=servicio, current_user=ADMIN))
    assert r3["chofer_id"] == 10 and r3["enlazados"][0]["rol"] == "chofer" and r3["bloqueo"] is None
