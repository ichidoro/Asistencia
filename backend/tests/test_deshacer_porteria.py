# -*- coding: utf-8 -*-
"""Deshacer un registro de Portería desde el aviso «Listo» (diseño A aprobado por el dueño, 03-11-2026):
- dentro del plazo del ajuste, quien lo registró (o un administrador) y solo si después no hubo otro movimiento;
- el registro no se borra sin rastro: pasa completo a registros_anulados y queda en el registro de cambios."""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

os.environ.setdefault("SECRET_KEY", "x" * 40)

from backend.services.deshacer_porteria import (  # noqa: E402
    deshacer, motivo_no_se_puede, palabra, permiso_deshacer, segundos_para_deshacer)

AHORA = datetime(2026, 10, 22, 16, 30, 5)   # UTC (13:30:05 en Chile)


class Usuario:
    def __init__(self, user_id, admin=False):
        self.user_id, self.username, self.is_superuser = user_id, "guardia" if not admin else "admin", admin


class BaseFalsa:
    """Lo justo para el servicio: filas por tabla, ajustes, registro de anulados y del registro de cambios."""

    def __init__(self, filas, ajustes=None):
        self.filas = filas
        self.ajustes = ajustes or {}
        self.anulados, self.cambios, self.en_transaccion = [], [], False

    async def fetch_one(self, sql, params=()):
        s = " ".join(sql.split())
        if s.startswith("SELECT valor FROM ajustes"):
            return {"valor": self.ajustes[params[0]]} if params[0] in self.ajustes else None
        if s.startswith("SELECT max(id) AS ultimo FROM"):
            tabla = s.split()[5]
            campos = [c.split(" = ")[0] for c in s.split("WHERE ", 1)[1].split(" AND ")]
            ids = [f["id"] for f in self.filas.get(tabla, []) if all(f.get(c) == v for c, v in zip(campos, params))]
            return {"ultimo": max(ids) if ids else None}
        if s.startswith("SELECT * FROM"):
            tabla = s.split()[3]
            return next((dict(f) for f in self.filas.get(tabla, []) if f["id"] == params[0]), None)
        if "FROM empleados" in s:
            return {"apellido_paterno": "BARBOZA", "apellido_materno": "", "nombre": "PEDRO PABLO"}
        return None

    async def execute(self, sql, params=()):
        s = " ".join(sql.split())
        if s.startswith("CREATE TABLE"):
            return None
        assert self.en_transaccion, "mover el registro debe ir dentro de una transacción"
        if s.startswith("INSERT INTO registros_anulados"):
            self.anulados.append(params)
        elif s.startswith("DELETE FROM"):
            tabla = s.split()[2]
            self.filas[tabla] = [f for f in self.filas[tabla] if f["id"] != params[0]]
        elif s.startswith("INSERT INTO logs_auditoria"):
            self.cambios.append(params)

    @asynccontextmanager
    async def transaction(self):
        self.en_transaccion = True
        try:
            yield self
        finally:
            self.en_transaccion = False


def marca(id_, hace_seg, por=15, emp=134, tipo="E"):
    creado = (AHORA - timedelta(seconds=hace_seg)).strftime("%Y-%m-%d %H:%M:%S")
    return {"id": id_, "empleado_id": emp, "fecha": "2026-10-22", "hora": "13:30:00", "tipo": tipo,
            "registrado_por_id": por, "registrado_por_nombre": "Guardia", "observaciones": "", "created_at": creado}


def correr(coro):
    return asyncio.run(coro)


def test_se_deshace_dentro_del_plazo_y_queda_el_rastro():
    db = BaseFalsa({"articulo22_registros": [marca(4300, 60, tipo="S"), marca(4301, 5)]})
    r = correr(deshacer(db, "art22", 4301, Usuario(15), 10, AHORA))
    assert r == {"ok": True, "mensaje": "ENTRADA de las 13:30 anulada.", "tipo": "art22", "id": 4301}
    assert [f["id"] for f in db.filas["articulo22_registros"]] == [4300]
    tabla, reg_id, datos, por_id, por = db.anulados[0]
    assert (tabla, reg_id, por_id) == ("articulo22_registros", 4301, 15) and json.loads(datos)["tipo"] == "E"
    accion, detalle = db.cambios[0][2], db.cambios[0][4]
    assert accion == "DESHACER_REGISTRO_PORTERIA" and "ENTRADA de las 13:30 · BARBOZA PEDRO PABLO" in detalle


def test_despues_del_plazo_ya_no_se_puede():
    db = BaseFalsa({"articulo22_registros": [marca(4301, 20)]})
    r = correr(deshacer(db, "art22", 4301, Usuario(15), 10, AHORA))
    assert r["ok"] is False and "plazo" in r["motivo"] and db.anulados == [] and len(db.filas["articulo22_registros"]) == 1


def test_el_margen_de_la_red_cubre_un_toque_al_final_de_la_barra():
    assert motivo_no_se_puede(marca(1, 12), None, 15, False, AHORA, 10) is None


def test_solo_quien_registro_o_un_administrador():
    db = BaseFalsa({"articulo22_registros": [marca(4301, 3, por=15)]})
    assert "Solo quien" in correr(deshacer(db, "art22", 4301, Usuario(99), 10, AHORA))["motivo"]
    assert correr(deshacer(db, "art22", 4301, Usuario(99, admin=True), 10, AHORA))["ok"] is True


def test_no_si_despues_hubo_otro_movimiento_del_mismo_sujeto():
    db = BaseFalsa({"articulo22_registros": [marca(4301, 6), marca(4302, 2, tipo="S"), marca(4303, 1, emp=200)]})
    r = correr(deshacer(db, "art22", 4301, Usuario(15), 10, AHORA))
    assert r["ok"] is False and "otro movimiento" in r["motivo"]


def test_la_visita_se_cuenta_por_rut_y_dia():
    visita = {"id": 9, "rut": "10835956-0", "fecha": "2026-10-22", "hora": "13:31:00", "tipo_marca": "S", "nombre": "GONZALO PACHECO",
              "registrado_por_id": 15, "created_at": (AHORA - timedelta(seconds=4)).strftime("%Y-%m-%d %H:%M:%S")}
    otra = dict(visita, id=10, rut="13718127-4")
    db = BaseFalsa({"visitas_registros": [visita, otra]})
    r = correr(deshacer(db, "visita", 9, Usuario(15), 10, AHORA))
    assert r["mensaje"] == "SALIDA de las 13:31 anulada." and "GONZALO PACHECO" in db.cambios[0][4]


def test_ya_deshecho_o_con_plazo_cero():
    db = BaseFalsa({"articulo22_registros": []})
    assert "ya no existe" in correr(deshacer(db, "art22", 1, Usuario(15), 10, AHORA))["motivo"]
    assert "apagado" in motivo_no_se_puede(marca(1, 1), None, 15, False, AHORA, 0)
    assert permiso_deshacer("art22", 5, 0) is None and permiso_deshacer("art22", None, 10) is None
    assert permiso_deshacer("llave", 7, 10) == {"tipo": "llave", "id": 7, "segundos": 10}


def test_el_plazo_sale_del_ajuste_y_sin_ajuste_no_hay_deshacer():
    assert correr(segundos_para_deshacer(BaseFalsa({}, {"porteria_deshacer_segundos": "10"}))) == 10
    assert correr(segundos_para_deshacer(BaseFalsa({}))) == 0
    assert correr(segundos_para_deshacer(BaseFalsa({}, {"porteria_deshacer_segundos": "abc"}))) == 0


def test_palabras_completas():
    assert [palabra(x) for x in ("E", "S", "ENTREGA", "DEVOLUCION", "SALIDA")] == ["ENTRADA", "SALIDA", "ENTREGA", "DEVOLUCIÓN", "SALIDA"]


def test_telegram_espera_el_plazo_y_no_avisa_una_marca_deshecha(monkeypatch):
    import backend.routers.articulo22 as a22
    enviados = []

    async def avisar_falso(emp, tipo, hora, quien):
        enviados.append((tipo, hora))

    async def sin_espera(_segundos):
        return None

    class Base:
        def __init__(self, existe):
            self.existe = existe

        async def fetch_one(self, sql, params=()):
            return {"id": params[0]} if self.existe else None

    monkeypatch.setattr(a22, "avisar_marca", avisar_falso)
    monkeypatch.setattr(a22.asyncio, "sleep", sin_espera)
    asyncio.run(a22._avisar_tras_plazo(Base(False), 4301, {}, "E", "13:30:00", "Guardia", 10))
    assert enviados == []
    asyncio.run(a22._avisar_tras_plazo(Base(True), 4301, {}, "E", "13:30:00", "Guardia", 10))
    asyncio.run(a22._avisar_tras_plazo(Base(False), 4302, {}, "S", "13:31:00", "Guardia", 0))
    assert enviados == [("E", "13:30:00"), ("S", "13:31:00")]
