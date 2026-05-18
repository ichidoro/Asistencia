# -*- coding: utf-8 -*-
"""
limpiar_areas.py
────────────────
Herramienta de desarrollo para limpiar tablas de la base de datos.
Borra en LOCAL (HybridDatabase) Y directamente en TURSO vía libsql,
garantizando que ambas BDs queden limpias sin depender del WAL sync.

Todas las tablas deben quedar idénticas en ambas BDs.
feriados se borra también en Turso: el startup lo reinsertará y lo pusheá
a Turso al arrancar el servidor.
"""
import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.core.database import HybridDatabase
import libsql

TURSO_URL   = "libsql://asistenciaaguacol-ichidoro.aws-us-east-1.turso.io"
TURSO_TOKEN = (
    "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9."
    "eyJhIjoicnciLCJpYXQiOjE3Nzg0NjQ2MjEsImlkIjoiMDE5ZTE0YzAt"
    "NjYwMS03YzUyLWFhZjMtMzk5ZTFlNjM5ZWEyIiwicmlkIjoiODZmMjky"
    "YTUtMjMzZC00ZmYyLThmN2ItMmJkNTQ2MmY1MDYwIn0."
    "HyHa_-uEPS_2YswqpWrSvX3CyqwkB5bj-uGOA549ug68cPgVK5TXBSMMjo1e0NJWwMQa8deBHL5UREuJKKyACA"
)

# Sin excepciones: todas las tablas se borran en LOCAL y en TURSO.
# feriados se borra también en Turso; el startup lo reinsertará y re-pusheará a Turso.
SOLO_LOCAL = set()  # Vacío: sin excepciones


def _turso_delete(tabla):
    """Borra directamente en Turso via libsql (sin pasar por WAL)."""
    try:
        conn = libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {tabla}")
        try:
            cur.execute(f"DELETE FROM sqlite_sequence WHERE name='{tabla}'")
        except Exception:
            pass
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"    ⚠️  Turso directo {tabla}: {e}")
        return False


async def limpiar_datos(opcion):
    print(f"\n  📁 Conectando a la base de datos...")
    db = HybridDatabase()
    try:
        await db.connect()

        # ── Transaccionales ─────────────────────────────────────────────────
        if opcion in ['4', '3', '5']:
            print("  🧹 Limpiando registros transaccionales...")
            for tabla in [
                "cierres_periodos", "logs_raw", "sync_logs", "logs_auditoria",
                "horas_extras", "jornadas_especiales", "bolsa_horas_resumen",
                "asistencias", "justificaciones", "intercambios_dias"
            ]:
                try:
                    if await db.table_exists(tabla):
                        await db.execute_script(
                            f"DELETE FROM {tabla}; "
                            f"DELETE FROM sqlite_sequence WHERE name='{tabla}';"
                        )
                    if tabla not in SOLO_LOCAL:
                        _turso_delete(tabla)
                except Exception:
                    pass

        # ── Empleados ────────────────────────────────────────────────────────
        if opcion in ['3', '5']:
            print("  🧹 Limpiando tabla 'empleados' e historiales...")
            for tabla in ["historial_areas", "periodos_empleo", "empleados"]:
                try:
                    if await db.table_exists(tabla):
                        await db.execute_script(
                            f"DELETE FROM {tabla}; "
                            f"DELETE FROM sqlite_sequence WHERE name='{tabla}';"
                        )
                    if tabla not in SOLO_LOCAL:
                        _turso_delete(tabla)
                except Exception as e:
                    pass

        # ── Turnos ───────────────────────────────────────────────────────────
        if opcion in ['2', '5']:
            print("  🧹 Limpiando tablas de turnos...")
            for tabla in [
                "asignacion_turnos", "turno_segmentos", "plantillas_planificacion",
                "turno_dias", "turno_areas", "turnos"
            ]:
                try:
                    if await db.table_exists(tabla):
                        await db.execute_script(
                            f"DELETE FROM {tabla}; "
                            f"DELETE FROM sqlite_sequence WHERE name='{tabla}';"
                        )
                    if tabla not in SOLO_LOCAL:
                        _turso_delete(tabla)
                except Exception:
                    pass

        # ── Configuración ────────────────────────────────────────────────────
        if opcion in ['1', '5']:
            print("  🧹 Limpiando configuraciones (áreas, cargos, bonos, etc.)...")
            for tabla in [
                "area_bonos", "bono_asignaciones", "bono_reglas", "bonos",
                "justificacion_tipos", "cat_pagadores",
                "notificaciones_areas", "feriados",
                "areas_alias", "areas", "cargos_alias", "cargos", "cat_generos"
            ]:
                try:
                    if await db.table_exists(tabla):
                        await db.execute_script(
                            f"DELETE FROM {tabla}; "
                            f"DELETE FROM sqlite_sequence WHERE name='{tabla}';"
                        )
                    # feriados solo vive en local → no borrar en Turso
                    if tabla not in SOLO_LOCAL:
                        _turso_delete(tabla)
                except Exception:
                    pass

        # ── Sync final ───────────────────────────────────────────────────────
        print("\n  ☁️  Sincronizando WAL local → Turso Cloud...")
        await db.sync_to_cloud_explicit()
        print("  ✅ Limpieza completada.\n")

    except Exception as e:
        print(f"\n  ❌ Error: {e}")
    finally:
        await db.disconnect()


def menu():
    print("=" * 50)
    print("  🛠️  HERRAMIENTA DE DESARROLLO — LIMPIEZA DE TABLAS")
    print("=" * 50)
    print("  1. Limpiar 'areas', 'cargos', 'generos', 'bonos', 'justificaciones'")
    print("  2. Limpiar tablas de 'turnos' completas")
    print("  3. Limpiar 'empleados'  (⚠️  borra asistencias y marcaciones también)")
    print("  4. Limpiar SOLO datos transaccionales (asistencias, logs, horas extras)")
    print("  5. Limpiar TODA LA BASE DE DATOS  (opciones 1 + 2 + 3 + 4)")
    print("  6. Salir")
    print("=" * 50)
    return input("  Elige una opción (1-6): ").strip()


if __name__ == "__main__":
    while True:
        op = menu()
        if op == '6':
            print("\n  Saliendo...\n")
            break
        elif op in ['1', '2', '3', '4', '5']:
            asyncio.run(limpiar_datos(op))
            break
        else:
            print("\n  ⚠️  Opción no válida. Inténtalo de nuevo.\n")
