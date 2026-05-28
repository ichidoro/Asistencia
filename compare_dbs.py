import libsql
import os
from backend.core.config import settings

def get_tables_and_columns(conn, label):
    """Obtiene tablas y columnas de una conexión"""
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_litestream_%' ORDER BY name").fetchall()
    result = {}
    for t in tables:
        name = t[0]
        try:
            cols_raw = conn.execute(f"PRAGMA table_info([{name}])").fetchall()
            cols = [(c[1], c[2], c[5]) for c in cols_raw]  # name, type, pk
            count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
            result[name] = {"columns": cols, "count": count}
        except Exception as e:
            result[name] = {"columns": [], "count": -1, "error": str(e)}
    return result

# 1. Turso Cloud (remota)
print("=" * 70)
print("CONECTANDO A TURSO CLOUD...")
print("=" * 70)
cloud_conn = libsql.connect(database=settings.TURSO_DATABASE_URL, auth_token=settings.TURSO_AUTH_TOKEN)
cloud_tables = get_tables_and_columns(cloud_conn, "CLOUD")
cloud_conn.close()

# 2. Base local (si existe)
local_path = settings.LOCAL_DB_PATH
local_tables = {}
if os.path.exists(local_path):
    print("\nCONECTANDO A DB LOCAL...")
    try:
        local_conn = libsql.connect(database=local_path)
        local_tables = get_tables_and_columns(local_conn, "LOCAL")
        local_conn.close()
    except Exception as e:
        print(f"ERROR al abrir DB local: {e}")
else:
    print(f"\nDB LOCAL NO EXISTE: {local_path}")

# 3. Tablas definidas en el código (extraídas del grep)
code_tables = [
    "permisos", "roles", "rol_permisos", "usuarios", "logs_auditoria", "sync_logs",
    "turnos", "turno_dias", "turno_areas", "turno_segmentos", "plantillas_planificacion",
    "asignacion_turnos", "bolsa_horas_resumen", "asistencias", "jornadas_especiales",
    "logs_raw", "horas_extras", "compensaciones_he_inasistencia",
    "areas", "areas_alias", "cargos", "cargos_alias", "empleados", "historial_areas",
    "cat_generos", "bonos", "bono_reglas", "bono_asignaciones",
    "justificacion_tipos", "cat_pagadores", "justificaciones",
    "ajustes", "cierres_periodos", "notificaciones_areas", "estados_asistencia",
    "periodos_empleo", "periodos_rrhh", "feriados"
]

# 4. COMPARACIÓN
print("\n" + "=" * 70)
print("COMPARACIÓN: CÓDIGO vs CLOUD vs LOCAL")
print("=" * 70)

all_tables = sorted(set(code_tables) | set(cloud_tables.keys()) | set(local_tables.keys()))

print(f"\n{'TABLA':<35} {'CÓDIGO':>6} {'CLOUD':>8} {'LOCAL':>8}  NOTAS")
print("-" * 85)

for t in all_tables:
    in_code = "SI" if t in code_tables else "---"
    
    if t in cloud_tables:
        cloud_count = str(cloud_tables[t]['count'])
    else:
        cloud_count = "FALTA"
    
    if t in local_tables:
        local_count = str(local_tables[t]['count'])
    else:
        local_count = "FALTA" if os.path.exists(local_path) else "N/A"
    
    notes = []
    if t in code_tables and t not in cloud_tables:
        notes.append("!! NO EXISTE EN CLOUD")
    if t not in code_tables and t in cloud_tables:
        notes.append("!! NO DEFINIDA EN CODIGO")
    if t in cloud_tables and t in local_tables:
        if cloud_tables[t]['count'] != local_tables[t]['count']:
            notes.append(f"DIFERENCIA: cloud={cloud_tables[t]['count']} local={local_tables[t]['count']}")
    
    note_str = " | ".join(notes) if notes else ""
    print(f"  {t:<33} {in_code:>6} {cloud_count:>8} {local_count:>8}  {note_str}")

# 5. Columnas diferentes
print("\n" + "=" * 70)
print("DIFERENCIAS DE COLUMNAS (CLOUD vs LOCAL)")
print("=" * 70)

if local_tables:
    for t in sorted(set(cloud_tables.keys()) & set(local_tables.keys())):
        cloud_cols = set(c[0] for c in cloud_tables[t].get('columns', []))
        local_cols = set(c[0] for c in local_tables[t].get('columns', []))
        
        only_cloud = cloud_cols - local_cols
        only_local = local_cols - cloud_cols
        
        if only_cloud or only_local:
            print(f"\n  {t}:")
            if only_cloud:
                print(f"    Solo en CLOUD: {', '.join(sorted(only_cloud))}")
            if only_local:
                print(f"    Solo en LOCAL: {', '.join(sorted(only_local))}")

print("\nDone.")
