# -*- coding: utf-8 -*-
"""
limpiar_y_comparar.py
─────────────────────
Herramienta de limpieza y comparación de bases de datos.

Flujo:
  1. Muestra menú de limpieza
  2. Borra DIRECTAMENTE en Turso Cloud via conexión HTTP (libsql sin offline)
  3. Borra DIRECTAMENTE en local via sqlite3
  4. Al terminar, compara ambas BDs para confirmar paridad.

Estrategia de sync (importante):
  ❌ ANTES: delete en local → sync_to_cloud_explicit()
            → conn.sync() en modo offline=True es PULL-ONLY (Turso → Local)
            → Los DELETEs locales nunca llegan a Turso
            → Turso mantiene sus datos, local queda vacío → DIFF permanente

  ✅ AHORA: delete DIRECTO en Turso vía conexión HTTP (sin offline=True)
            + delete en local vía sqlite3 (con PRAGMA foreign_keys=OFF)
            → Ambas bases quedan vacías de forma independiente y verificable
            → Sin conflictos WAL, sin divergencias

Nota sobre FK:
  • Se usa PRAGMA foreign_keys=OFF antes de cada DELETE para evitar errores
    de constraint cuando se borran tablas referenciadas antes que las que las
    referencian (ej: empleados antes de historial_areas).
"""
import asyncio
import os
import sys
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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

SKIP_DATA  = {'logs_auditoria', 'sync_logs', 'logs_raw', 'asistencias'}
MAX_ROWS   = 10_000
SEP        = "=" * 62


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

def _get_tablas_a_borrar(opcion):
    """Retorna lista ordenada de tablas a borrar según opción elegida."""
    transaccionales = [
        "cierres_periodos", "logs_raw", "sync_logs", "logs_auditoria",
        "horas_extras", "jornadas_especiales", "bolsa_horas_resumen",
        "asistencias", "justificaciones", "intercambios_dias"
    ]
    empleados = ["historial_areas", "periodos_empleo", "empleados"]
    turnos = [
        "asignacion_turnos", "turno_segmentos", "plantillas_planificacion",
        "turno_dias", "turno_areas", "turnos"
    ]
    configuracion = [
        "area_bonos", "bono_asignaciones", "bono_reglas", "bonos",
        "justificacion_tipos", "cat_pagadores",
        "notificaciones_areas", "feriados",
        "areas_alias", "areas", "cargos_alias", "cargos", "cat_generos"
    ]

    tablas = []
    if opcion in ['4', '3', '5']:
        tablas += transaccionales
    if opcion in ['3', '5']:
        tablas += empleados
    if opcion in ['2', '5']:
        tablas += turnos
    if opcion in ['1', '5']:
        tablas += configuracion
    return tablas


def _borrar_en_local(tablas):
    """
    Borra directamente en SQLite local usando sqlite3.
    Usa PRAGMA foreign_keys=OFF para evitar errores de constraint.
    """
    print("  📂 Borrando en SQLite LOCAL...")
    try:
        conn = sqlite3.connect(LOCAL_DB)
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("PRAGMA journal_mode = WAL")
        for tabla in tablas:
            try:
                conn.execute(f"DELETE FROM {tabla}")
                # Resetear secuencia de auto-increment
                conn.execute(
                    "DELETE FROM sqlite_sequence WHERE name=?", (tabla,)
                )
                print(f"    ✓ {tabla}")
            except sqlite3.OperationalError as e:
                if "no such table" in str(e).lower():
                    pass  # Tabla no existe, ignorar
                else:
                    print(f"    ⚠️  {tabla}: {e}")
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()
        print("  ✅ Local limpio.\n")
    except Exception as e:
        print(f"  ❌ Error borrando en local: {e}")
        import traceback; traceback.print_exc()


def _borrar_en_turso(tablas):
    """
    Borra directamente en Turso Cloud via conexión HTTP (libsql sin offline=True).
    Esta es la ÚNICA forma confiable de borrar en Turso desde un script externo.
    """
    print("  ☁️  Borrando en TURSO CLOUD (conexión directa HTTP)...")
    try:
        # Conectar directamente a Turso (sin embedded replica, sin offline)
        conn = libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)
        cur = conn.cursor()

        # Deshabilitar FK constraints en Turso (soporte varía, intentamos)
        try:
            cur.execute("PRAGMA foreign_keys = OFF")
        except Exception:
            pass  # Turso puede no soportar este PRAGMA via HTTP, ignorar

        for tabla in tablas:
            try:
                cur.execute(f"DELETE FROM {tabla}")
                # Intentar resetear secuencia (puede no existir en Turso)
                try:
                    cur.execute(
                        "DELETE FROM sqlite_sequence WHERE name=?", (tabla,)
                    )
                except Exception:
                    pass
                print(f"    ✓ {tabla}")
            except Exception as e:
                err_str = str(e).lower()
                if "no such table" in err_str:
                    pass
                else:
                    print(f"    ⚠️  {tabla}: {e}")

        conn.commit()
        try:
            conn.close()
        except Exception:
            pass
        print("  ✅ Turso limpio.\n")
    except Exception as e:
        print(f"  ❌ Error borrando en Turso: {e}")
        import traceback; traceback.print_exc()


def limpiar_datos(opcion):
    """
    Limpia datos borrando directamente en AMBAS bases de datos.
    No usa HybridDatabase ni WAL sync para evitar el problema pull-only.
    """
    tablas = _get_tablas_a_borrar(opcion)
    if not tablas:
        print("  ℹ️  Nada que limpiar.")
        return

    # Mostrar resumen de lo que se borrará
    grupos = []
    if opcion in ['4', '3', '5']: grupos.append("transaccionales")
    if opcion in ['3', '5']:       grupos.append("empleados")
    if opcion in ['2', '5']:       grupos.append("turnos")
    if opcion in ['1', '5']:       grupos.append("configuración")
    print(f"\n  🧹 Limpiando: {', '.join(grupos)} ({len(tablas)} tablas)...\n")

    # 1. Borrar en local
    _borrar_en_local(tablas)

    # 2. Borrar en Turso directamente
    _borrar_en_turso(tablas)


# ══════════════════════════════════════════════════════════════════════════════
#  PARTE 3 — COMPARACIÓN POST-LIMPIEZA
# ══════════════════════════════════════════════════════════════════════════════

def comparar_post_limpieza():
    """
    Compara Turso vs Local tras la limpieza.
    Usa sqlite3 para leer local y libsql HTTP para leer Turso.
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

    limpiar_datos(opcion)
    comparar_post_limpieza()


if __name__ == '__main__':
    main()
