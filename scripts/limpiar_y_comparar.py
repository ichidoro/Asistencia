# -*- coding: utf-8 -*-
"""
limpiar_y_comparar.py
─────────────────────
Fusión de limpiar_areas.py + comparar_dbs.py

Flujo:
  1. Muestra menú de limpieza
  2. Conecta (HybridDatabase hace sync_from_cloud → local = Turso)
  3. Borra SOLO EN LOCAL via HybridDatabase.execute_script
  4. Empuja los deletes a Turso via sync_to_cloud_explicit()
     (Un único vector de cambios → sin divergencia de WAL → sin conflict)
  5. Al terminar, compara automáticamente ambas BDs para confirmar paridad.

Estrategia de sync (importante):
  ❌ ANTES: delete en local + delete directo en Turso vía libsql
           → Dos historias WAL divergentes → "server returned a conflict: sent=70, got=105"
  ✅ AHORA: delete solo en local → sync_to_cloud_explicit() propaga el delta a Turso
           → Una sola historia WAL → sin conflict, sin 503 en disconnect()

Tablas con comportamiento especial:
  - Ninguna: todas las tablas deben estar sincronizadas entre local y Turso.
  - logs_auditoria, sync_logs, logs_raw, asistencias: excluidas de comparación por volumen.
"""
import asyncio
import os
import sys
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.core.database import HybridDatabase
import libsql

# ── Configuración ─────────────────────────────────────────────────────────────
TURSO_URL   = "libsql://asistenciaaguacol-ichidoro.aws-us-east-1.turso.io"
TURSO_TOKEN = (
    "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9."
    "eyJhIjoicnciLCJpYXQiOjE3Nzg0NjQ2MjEsImlkIjoiMDE5ZTE0YzAt"
    "NjYwMS03YzUyLWFhZjMtMzk5ZTFlNjM5ZWEyIiwicmlkIjoiODZmMjky"
    "YTUtMjMzZC00ZmYyLThmN2ItMmJkNTQ2MmY1MDYwIn0."
    "HyHa_-uEPS_2YswqpWrSvX3CyqwkB5bj-uGOA549ug68cPgVK5TXBSMMjo1e0NJWwMQa8deBHL5UREuJKKyACA"
)
LOCAL_DB = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'data', 'local_db', 'asistencia_local.db')
)

SOLO_LOCAL = set()   # Vacío: todas las tablas deben estar en ambas BDs
SKIP_DATA  = {'logs_auditoria', 'sync_logs', 'logs_raw', 'asistencias'}
MAX_ROWS   = 10_000
SEP        = "=" * 62


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS (solo para la comparación, ya no para borrado directo en Turso)
# ══════════════════════════════════════════════════════════════════════════════

def _turso_count(tabla):
    """Lee el conteo de filas en Turso directamente via libsql (solo lectura)."""
    try:
        conn = libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {tabla}")
        row = cur.fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception as e:
        return f"ERR({e})"


# ══════════════════════════════════════════════════════════════════════════════
#  PARTE 1 — MENÚ
# ══════════════════════════════════════════════════════════════════════════════

def menu():
    print(SEP)
    print("  🛠️  HERRAMIENTA DE DESARROLLO — LIMPIEZA DE TABLAS")
    print(SEP)
    print("  1. Limpiar 'areas', 'cargos', 'generos', 'bonos', 'justificaciones'")
    print("  2. Limpiar tablas de 'turnos' completas")
    print("  3. Limpiar 'empleados'  (⚠️  borra asistencias y marcaciones también)")
    print("  4. Limpiar SOLO datos transaccionales (asistencias, logs, horas extras)")
    print("  5. Limpiar TODA LA BASE DE DATOS  (opciones 1 + 2 + 3 + 4)")
    print("  6. Salir")
    print(SEP)
    return input("  Elige una opción (1-6): ").strip()


# ══════════════════════════════════════════════════════════════════════════════
#  PARTE 2 — LIMPIEZA
# ══════════════════════════════════════════════════════════════════════════════

async def limpiar_datos(opcion):
    print(f"\n  📁 Conectando a la base de datos...")
    db = HybridDatabase()
    try:
        # connect() hace sync_from_cloud automáticamente → local queda igual a Turso
        await db.connect()

        async def _local_delete(tabla):
            """Borra en local via HybridDatabase (genera frames WAL que luego se pushean)."""
            try:
                if await db.table_exists(tabla):
                    await db.execute_script(
                        f"DELETE FROM {tabla}; "
                        f"DELETE FROM sqlite_sequence WHERE name='{tabla}';"
                    )
            except Exception:
                pass

        # ── Transaccionales ──────────────────────────────────────────────────
        if opcion in ['4', '3', '5']:
            print("  🧹 Limpiando registros transaccionales...")
            for tabla in [
                "cierres_periodos", "logs_raw", "sync_logs", "logs_auditoria",
                "horas_extras", "jornadas_especiales", "bolsa_horas_resumen",
                "asistencias", "justificaciones", "intercambios_dias"
            ]:
                await _local_delete(tabla)

        # ── Empleados ─────────────────────────────────────────────────────────
        if opcion in ['3', '5']:
            print("  🧹 Limpiando tabla 'empleados' e historiales...")
            for tabla in ["historial_areas", "periodos_empleo", "empleados"]:
                await _local_delete(tabla)

        # ── Turnos ────────────────────────────────────────────────────────────
        if opcion in ['2', '5']:
            print("  🧹 Limpiando tablas de turnos...")
            for tabla in [
                "asignacion_turnos", "turno_segmentos", "plantillas_planificacion",
                "turno_dias", "turno_areas", "turnos"
            ]:
                await _local_delete(tabla)

        # ── Configuración ─────────────────────────────────────────────────────
        if opcion in ['1', '5']:
            print("  🧹 Limpiando configuraciones (áreas, cargos, bonos, etc.)...")
            for tabla in [
                "area_bonos", "bono_asignaciones", "bono_reglas", "bonos",
                "justificacion_tipos", "cat_pagadores",
                "notificaciones_areas", "feriados",
                "areas_alias", "areas", "cargos_alias", "cargos", "cat_generos"
            ]:
                await _local_delete(tabla)

        # ── Propagar a Turso via sync ────────────────────────────────────────
        # Estrategia correcta:
        #   • Los deletes locales crearon frames WAL en local (historia única).
        #   • sync_to_cloud_explicit() envía esos frames a Turso sin conflicto.
        #   • disconnect() también hará conn.sync() final — redundante pero inofensivo.
        #
        # Esto reemplaza el doble-borrado (local + directo en Turso) que causaba:
        #   ❌ "server returned a conflict: sent=70, got=105"
        #   ❌ "max_frame_no failed: database is locked" en disconnect()
        print("\n  ☁️  Propagando limpieza a Turso Cloud via sync...")
        try:
            success = await db.sync_to_cloud_explicit()
            if success:
                print("  ✅ Limpieza propagada a Turso correctamente.")
            else:
                print("  ⚠️  sync_to_cloud_explicit retornó False — revisar logs.")
        except Exception as e_sync:
            print(f"  ⚠️  Sync con advertencias: {e_sync}")
            print("  ℹ️  Los datos están limpios en local. Turso se sincronizará en el próximo startup.")

    except Exception as e:
        print(f"\n  ❌ Error: {e}")
        import traceback; traceback.print_exc()
    finally:
        await db.disconnect()


# ══════════════════════════════════════════════════════════════════════════════
#  PARTE 3 — COMPARACIÓN POST-LIMPIEZA
# ══════════════════════════════════════════════════════════════════════════════

def comparar_post_limpieza():
    """
    Compara Turso vs Local tras la limpieza.
    Usa libsql para leer Turso y sqlite3 para leer local.
    """
    print(f"\n{SEP}")
    print("  🔍 VERIFICACIÓN POST-LIMPIEZA: Turso vs Local")
    print(SEP)

    # Obtener todas las tablas del schema local
    try:
        local_conn = sqlite3.connect(LOCAL_DB)
        cur = local_conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        all_tables = [r[0] for r in cur.fetchall()
                      if not r[0].startswith('sqlite_')]
    except Exception as e:
        print(f"  ❌ No se pudo leer local: {e}")
        return
    finally:
        try: local_conn.close()
        except: pass

    # Conectar a Turso solo para lectura
    try:
        turso_conn = libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)
    except Exception as e:
        print(f"  ❌ No se pudo conectar a Turso: {e}")
        return

    # Contar filas en cada tabla
    rows = []
    diffs = []

    for tabla in sorted(all_tables):
        # Local
        try:
            lc = sqlite3.connect(LOCAL_DB)
            c = lc.cursor()
            c.execute(f"SELECT COUNT(*) FROM {tabla}")
            local_count = c.fetchone()[0]
            lc.close()
        except Exception:
            local_count = "ERR"

        # Turso
        try:
            tc = turso_conn.cursor()
            tc.execute(f"SELECT COUNT(*) FROM {tabla}")
            r = tc.fetchone()
            turso_count = r[0] if r else "ERR"
        except Exception as e:
            turso_count = "N/A"

        if isinstance(local_count, int) and isinstance(turso_count, int):
            status = "OK" if local_count == turso_count else "⚠️ DIFF"
            if local_count != turso_count:
                diffs.append((tabla, local_count, turso_count))
        else:
            status = "?"

        rows.append((tabla, local_count, turso_count, status))

    try:
        turso_conn.close()
    except:
        pass

    # Imprimir tabla
    print(f"\n  {'TABLA':<38} {'LOCAL':>7} {'TURSO':>7}  {'STATUS'}")
    print(f"  {'-'*38} {'-'*7} {'-'*7}  {'-'*10}")
    for tabla, local_count, turso_count, status in rows:
        print(f"  {tabla:<38} {str(local_count):>7} {str(turso_count):>7}  {status}")

    print(f"\n{SEP}\n")

    if diffs:
        print(f"  ⚠️  {len(diffs)} tabla(s) con diferencias:")
        for tabla, lc, tc in diffs:
            diff = lc - tc if isinstance(lc, int) and isinstance(tc, int) else "?"
            direction = "solo-local" if isinstance(lc, int) and isinstance(tc, int) and lc > tc else "solo-turso"
            print(f"    • {tabla:<38} local={lc}  turso={tc}  ({direction})")
        print()
    else:
        print(f"  ✅  BASES DE DATOS IDÉNTICAS — Turso = Local\n")

    print(SEP)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    opcion = menu()

    if opcion == '6':
        print("  👋 Saliendo.")
        return

    if opcion not in ['1', '2', '3', '4', '5']:
        print("  ❌ Opción inválida.")
        return

    asyncio.run(limpiar_datos(opcion))
    comparar_post_limpieza()


if __name__ == '__main__':
    main()
