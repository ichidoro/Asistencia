# -*- coding: utf-8 -*-
"""
limpiar_y_comparar.py
─────────────────────
Fusión de limpiar_areas.py + comparar_dbs.py

Flujo:
  1. Muestra menú de limpieza
  2. Borra en LOCAL (HybridDatabase) Y directamente en TURSO vía libsql
     (doble borrado = no depende de que el WAL sync propague DELETEs)
  3. Al terminar, compara automáticamente ambas BDs para confirmar paridad.

Tablas con comportamiento especial:
  - feriados: solo se borra en local. Turso no los tiene (auto-generados en startup).
              Se excluyen del chequeo de paridad — diferencia esperada y aceptable.
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

# Tablas que solo tienen datos en local — no se borran en Turso, no se comparan
SOLO_LOCAL = {'feriados'}
# Tablas omitidas de comparación fila-a-fila (volumen / operacionales + solo-local)
SKIP_DATA  = {'logs_auditoria', 'sync_logs', 'logs_raw', 'asistencias', 'feriados'}
MAX_ROWS   = 10_000
SEP        = "=" * 62


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _turso_delete(tabla):
    """Borra directamente en Turso via libsql (sin pasar por WAL sync)."""
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
    except Exception as e:
        print(f"    ⚠️  Turso directo '{tabla}': {e}")


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

def _limpiar_tabla_local_y_turso(db_exec, tabla):
    """Limpia una tabla en local (vía HybridDatabase) y en Turso (directo vía libsql)."""
    try:
        import asyncio as _a
        # La llamada ya viene desde dentro de un async context, se usa await afuera
        pass
    except Exception:
        pass
    if tabla not in SOLO_LOCAL:
        _turso_delete(tabla)


async def limpiar_datos(opcion):
    print(f"\n  📁 Conectando a la base de datos...")
    db = HybridDatabase()
    try:
        await db.connect()

        async def _local_delete(tabla):
            """Borra en local."""
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
                if tabla not in SOLO_LOCAL:
                    _turso_delete(tabla)

        # ── Empleados ─────────────────────────────────────────────────────────
        if opcion in ['3', '5']:
            print("  🧹 Limpiando tabla 'empleados' e historiales...")
            for tabla in ["historial_areas", "periodos_empleo", "empleados"]:
                await _local_delete(tabla)
                if tabla not in SOLO_LOCAL:
                    _turso_delete(tabla)

        # ── Turnos ────────────────────────────────────────────────────────────
        if opcion in ['2', '5']:
            print("  🧹 Limpiando tablas de turnos...")
            for tabla in [
                "asignacion_turnos", "turno_segmentos", "plantillas_planificacion",
                "turno_dias", "turno_areas", "turnos"
            ]:
                await _local_delete(tabla)
                if tabla not in SOLO_LOCAL:
                    _turso_delete(tabla)

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
                if tabla not in SOLO_LOCAL:
                    _turso_delete(tabla)

        # ── Sync WAL → Turso ──────────────────────────────────────────────────
        print("\n  ☁️  Sincronizando cambios hacia Turso Cloud...")
        await db.sync_to_cloud_explicit()
        print("  ✅ Limpieza completada y sincronizada con Turso.")

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
    Muestra solo las diferencias. feriados se excluye (dato solo-local esperado).
    """
    print(f"\n{SEP}")
    print("  🔍 VERIFICACIÓN POST-LIMPIEZA: Turso vs Local")
    print(SEP)

    turso = libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)
    local = sqlite3.connect(LOCAL_DB)
    local.row_factory = sqlite3.Row

    def lq(sql):
        cur = local.cursor(); cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, [dict(zip(cols, list(r))) for r in cur.fetchall()]

    def tq(sql):
        cur = turso.cursor(); cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, [dict(zip(cols, list(r))) for r in cur.fetchall()]

    def normalize(v):
        if v is None: return None
        try:
            f = float(v); return int(f) if f == int(f) else f
        except (ValueError, TypeError): return v

    SQL_TABLES = ("SELECT name FROM sqlite_master "
                  "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    _, l_tbl = lq(SQL_TABLES)
    _, t_tbl = tq(SQL_TABLES)
    local_tables = {r['name'] for r in l_tbl}
    turso_tables = {r['name'] for r in t_tbl}
    common       = local_tables & turso_tables

    # ── Conteos ───────────────────────────────────────────────────────────────
    print(f"\n  {'TABLA':<38} {'LOCAL':>7} {'TURSO':>7}  STATUS")
    print(f"  {'-'*38} {'-'*7} {'-'*7}  {'-'*10}")

    count_diffs, row_counts = {}, {}
    for table in sorted(common):
        try:
            _, lr = lq(f"SELECT COUNT(*) as c FROM '{table}'")
            _, tr = tq(f"SELECT COUNT(*) as c FROM '{table}'")
            lc_n, tc_n = lr[0]['c'], tr[0]['c']
            row_counts[table] = (lc_n, tc_n)
            if lc_n == tc_n:
                st = "OK"
            elif table in SKIP_DATA:
                st = "INFO (solo-local esperado)" if table in SOLO_LOCAL else "INFO"
            else:
                diff = lc_n - tc_n
                st = f"DIFF ({'+' if diff>0 else ''}{diff})"
                count_diffs[table] = (lc_n, tc_n)
            print(f"  {table:<38} {lc_n:>7} {tc_n:>7}  {st}")
        except Exception as e:
            print(f"  {table:<38} {'ERR':>7} {'ERR':>7}  {e}")

    # ── Datos fila a fila ─────────────────────────────────────────────────────
    data_diffs = {}
    for table in sorted(common):
        if table in SKIP_DATA: continue
        lc_n, tc_n = row_counts.get(table, (0, 0))
        if max(lc_n, tc_n) == 0 or max(lc_n, tc_n) > MAX_ROWS:
            continue
        try:
            _, l_rows = lq(f"SELECT * FROM '{table}' ORDER BY rowid")
            _, t_rows = tq(f"SELECT * FROM '{table}' ORDER BY rowid")
        except Exception:
            continue

        diffs = []
        for i in range(max(len(l_rows), len(t_rows))):
            if i >= len(l_rows):
                diffs.append({'tipo': 'SOLO_TURSO', 'val': t_rows[i]})
            elif i >= len(t_rows):
                diffs.append({'tipo': 'SOLO_LOCAL', 'val': l_rows[i]})
            else:
                cd = {c: {'L': normalize(l_rows[i].get(c)), 'T': normalize(t_rows[i].get(c))}
                      for c in set(list(l_rows[i]) + list(t_rows[i]))
                      if str(normalize(l_rows[i].get(c))) != str(normalize(t_rows[i].get(c)))}
                if cd:
                    diffs.append({'tipo': 'DIFERENTE', 'cols': cd, 'id': l_rows[i].get('id', i+1)})
        if diffs:
            data_diffs[table] = diffs

    # ── Veredicto ─────────────────────────────────────────────────────────────
    print(f"\n{SEP}\n")
    problems = []
    if count_diffs: problems.append(f"Conteos distintos   : {sorted(count_diffs.keys())}")
    if data_diffs:  problems.append(f"Datos distintos     : {sorted(data_diffs.keys())}")

    if not problems:
        print(f"  ✅  BASES DE DATOS IDÉNTICAS — Turso = Local")
        print(f"      (feriados excluido: dato solo-local, diferencia esperada)\n")
    else:
        print(f"  ❌  BASES DE DATOS NO IDÉNTICAS — {len(problems)} categoría(s) con diferencias:")
        for p in problems:
            print(f"      • {p}")
        if data_diffs:
            print()
            for t, diffs in data_diffs.items():
                tipos = {}
                for d in diffs: tipos[d['tipo']] = tipos.get(d['tipo'], 0) + 1
                print(f"        {t}: {len(diffs)} fila(s) → {tipos}")
        print()

    print(SEP + "\n")
    turso.close()
    local.close()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    while True:
        op = menu()
        if op == '6':
            print("\n  Saliendo...\n")
            break
        elif op in ['1', '2', '3', '4', '5']:
            asyncio.run(limpiar_datos(op))
            comparar_post_limpieza()
            break
        else:
            print("\n  ⚠️  Opción no válida. Inténtalo de nuevo.\n")
