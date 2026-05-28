"""
Reparacion de logs_raw: tabla corrompida en Turso Cloud.
Estrategia: crear tabla temporal con solo filas validas, luego intercambiar.
Pasos:
  1. Crear logs_raw_backup con estructura identica
  2. Insertar solo filas con empleado_id valido
  3. DROP logs_raw
  4. Renombrar logs_raw_backup -> logs_raw
"""
import urllib.request, json

env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

TURSO_URL = env['TURSO_DATABASE_URL'].replace('libsql://', 'https://')
TURSO_TOKEN = env['TURSO_AUTH_TOKEN']

def run_pipeline(stmts):
    """Ejecuta multiples statements en un pipeline"""
    requests = [{"type": "execute", "stmt": {"sql": s}} for s in stmts]
    requests.append({"type": "close"})
    payload = json.dumps({"requests": requests}).encode()
    req = urllib.request.Request(f"{TURSO_URL}/v2/pipeline", data=payload,
        headers={"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.loads(r.read())
    return res["results"]

def run(sql):
    results = run_pipeline([sql])
    r2 = results[0]
    if r2["type"] == "error":
        raise Exception(r2["error"]["message"])
    return r2["response"]["result"].get("affected_row_count", 0)

def q(sql):
    results = run_pipeline([sql])
    r2 = results[0]
    if r2["type"] == "error":
        raise Exception(r2["error"]["message"])
    d = r2["response"]["result"]
    cols = [c["name"] for c in d["cols"]]
    return [{cols[i]: (row[i]["value"] if row[i]["type"] != "null" else None) for i in range(len(cols))} for row in d["rows"]]

print("=== REPARACION DE logs_raw ===\n")

# 1. Verificar estado actual
total = q("SELECT COUNT(*) as c FROM logs_raw")[0]["c"]
print(f"  Total logs_raw: {total}")

# 2. Obtener schema de logs_raw
schema = q("SELECT sql FROM sqlite_master WHERE type='table' AND name='logs_raw'")
create_sql = schema[0]["sql"] if schema else None
print(f"  Schema: {create_sql[:80]}...")

# 3. Intentar REINDEX primero (puede reparar indices corruptos)
print("\n  Intentando REINDEX logs_raw...")
try:
    run("REINDEX logs_raw")
    print("  REINDEX completado")
except Exception as e:
    print(f"  REINDEX fallo: {e}")

# 4. Intentar DELETE simple con un ID
print("\n  Probando DELETE simple para empleado_id=38...")
try:
    n = run("DELETE FROM logs_raw WHERE empleado_id = 38")
    print(f"  DELETE exitoso: {n} filas")
    # Si funciona, procesar el resto
    orphan_ids = [39,40,41,42,43,44,45,46,47,48,49,50,51,52,53]
    for oid in orphan_ids:
        try:
            n2 = run(f"DELETE FROM logs_raw WHERE empleado_id = {oid}")
            print(f"  empleado_id={oid}: {n2} eliminados")
        except Exception as e:
            print(f"  ERROR {oid}: {e}")
except Exception as e:
    print(f"  DELETE simple fallo: {e}")
    print("\n  Iniciando estrategia de RECREACION de tabla...\n")

    # 5. Recrear tabla: DROP backup si existe
    try:
        run("DROP TABLE IF EXISTS logs_raw_repair")
        print("  Limpieza previa: OK")
    except: pass

    # 6. Crear tabla nueva con estructura identica
    repair_sql = create_sql.replace("CREATE TABLE logs_raw", "CREATE TABLE logs_raw_repair")
    # Si no hay CREATE TABLE encontrado, usar schema conocido
    if not create_sql or "logs_raw" not in create_sql:
        repair_sql = """CREATE TABLE logs_raw_repair (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER,
            rut TEXT,
            fecha_hora TEXT,
            tipo TEXT,
            equipo TEXT,
            hash_original TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            procesado INTEGER DEFAULT 0
        )"""
    
    try:
        run(repair_sql)
        print("  Tabla logs_raw_repair creada")
    except Exception as e:
        print(f"  ERROR creando tabla: {e}")
        exit(1)

    # 7. Copiar solo filas validas (por bloques de 500 para evitar timeout)
    print("  Copiando filas validas de logs_raw a logs_raw_repair...")
    try:
        n = run("""
            INSERT INTO logs_raw_repair
            SELECT lr.* FROM logs_raw lr
            INNER JOIN empleados e ON lr.empleado_id = e.id
        """)
        print(f"  Filas copiadas (JOIN directo): {n}")
    except Exception as e:
        print(f"  ERROR en copia masiva: {e}")
        # Copiar por empleado_id valido
        emp_ids_str = ",".join([str(r["id"]) for r in q("SELECT id FROM empleados")])
        try:
            n = run(f"INSERT INTO logs_raw_repair SELECT * FROM logs_raw WHERE empleado_id IN ({emp_ids_str})")
            print(f"  Filas copiadas (IN lista): {n}")
        except Exception as e2:
            print(f"  ERROR en copia alternativa: {e2}")
            exit(1)

    # 8. Verificar conteo
    repair_count = q("SELECT COUNT(*) as c FROM logs_raw_repair")[0]["c"]
    print(f"  Filas en logs_raw_repair: {repair_count}")

    # 9. DROP original y renombrar
    print("  Eliminando tabla original corrompida...")
    try:
        run("DROP TABLE logs_raw")
        print("  DROP logs_raw: OK")
    except Exception as e:
        print(f"  ERROR DROP: {e}")
        exit(1)

    print("  Renombrando logs_raw_repair -> logs_raw...")
    try:
        run("ALTER TABLE logs_raw_repair RENAME TO logs_raw")
        print("  RENAME: OK")
    except Exception as e:
        print(f"  ERROR RENAME: {e}")
        exit(1)

# 10. Verificacion final
print("\n=== VERIFICACION FINAL ===\n")
final_count = q("SELECT COUNT(*) as c FROM logs_raw")[0]["c"]
orphans = q("""
    SELECT COUNT(*) as c FROM logs_raw l
    LEFT JOIN empleados e ON l.empleado_id = e.id
    WHERE e.id IS NULL
""")[0]["c"]
print(f"  logs_raw total:    {final_count}")
print(f"  logs_raw huerfanos: {orphans}")
print(f"  Estado: {'OK - tabla limpia' if int(str(orphans)) == 0 else 'AUN HAY HUERFANOS'}")
