"""Tres fallas que ya existían, vistas en el ensayo de la etapa 4 (parte 5) y arregladas el 16-11-2026.

1. Confirmar un cambio de área pendiente daba error 500: leía pendiente['area'], que esa tabla no tiene (tiene area_id).
   Además, al arreglarlo no se puede usar update_empleado: abriría otro registro del historial desde hoy y cerraría el
   confirmado con fecha de ayer. Se anota solo la ficha (set_area_actual).
2. Crear o editar un empleado con un área que no existe daba error 500: ahora responde «El área seleccionada no existe».
3. Cambiar un turno que no existe respondía «Turno actualizado correctamente»: ahora «Turno no encontrado».
"""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

from backend.repositories.empleado import EmpleadoRepository
from backend.repositories.turno import TurnoRepository

RAIZ = Path(__file__).resolve().parents[2]


class BaseQueAnota:
    """Anota cada sentencia; un UPDATE de turnos no toca filas (el turno no existe)."""

    def __init__(self):
        self.sentencias = []

    async def execute(self, sql, params=()):
        s = " ".join(sql.split())
        self.sentencias.append((s, params))
        return SimpleNamespace(rowcount=0 if s.startswith("UPDATE turnos SET") else 1, lastrowid=None)


def _turno_minimo():
    return SimpleNamespace(
        nombre="X", tipo_programacion="CICLO_INTELIGENTE", meta_horas_semanales=44, tolerancia_retraso_alerta=0,
        tolerancia_retraso_descuento=0, tolerancia_salida_adelantada=0, descuento_colacion_auto=True,
        minutos_colacion_auto=30, umbral_horas_colacion=4, anclaje_entrada_minutos=0, anclaje_salida_minutos=0,
        hora_limite_ficticia=None, ventana_en_curso_minutos=0, espera_inasistencia_minutos=0,
        tolerancia_exceso_colacion_minutos=0, turno_padre_id=None, fecha_vigencia=None, activo=True,
        rotacion_dinamica_diaria=False, meta_horas_espera=88, modalidad_control="RELOJ", libreta_desde=None,
        areas=["Área de Prueba"], dias=[SimpleNamespace(dia_semana=0, num_semana=1, es_libre=False, horas_teoricas=8,
                                                        hora_entrada="08:00", hora_salida="17:00",
                                                        cruza_medianoche=False, etiqueta_bloque=None)])


def test_cambiar_un_turno_que_no_existe_no_toca_dias_ni_areas():
    db = BaseQueAnota()
    resultado = asyncio.run(TurnoRepository(db).update_turno(999999, _turno_minimo()))
    assert resultado is False
    # Solo se intentó el UPDATE del turno: no se borraron ni crearon días ni áreas de un turno inexistente
    assert [s for s, _ in db.sentencias] and all(s.startswith("UPDATE turnos SET") for s, _ in db.sentencias)


def test_set_area_actual_solo_toca_la_ficha():
    db = BaseQueAnota()
    asyncio.run(EmpleadoRepository(db).set_area_actual(7, 3))
    assert len(db.sentencias) == 1
    sql, params = db.sentencias[0]
    assert sql.startswith("UPDATE empleados SET area_id = ?") and params == (3, 7)


def _funcion(nombre):
    arbol = ast.parse((RAIZ / "backend" / "routers" / "empleados.py").read_text(encoding="utf-8"))
    return next(n for n in ast.walk(arbol) if isinstance(n, ast.AsyncFunctionDef) and n.name == nombre)


def test_confirmar_cambio_de_area_lee_area_id_y_no_usa_update_empleado():
    f = _funcion("confirmar_cambio_area")
    leidos = {n.slice.value for n in ast.walk(f) if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
              and n.value.id == "pendiente" and isinstance(n.slice, ast.Constant)}
    assert "area_id" in leidos and "area" not in leidos
    llamadas = {n.func.attr for n in ast.walk(f) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "set_area_actual" in llamadas and "update_empleado" not in llamadas


def test_alta_y_edicion_avisan_si_el_area_no_existe():
    for nombre in ("crear_empleado", "actualizar_empleado"):
        f = _funcion(nombre)
        avisos = [n for n in ast.walk(f) if isinstance(n, ast.Constant) and n.value == "El área seleccionada no existe."]
        assert avisos, f"{nombre} no avisa cuando el área no existe"
