"""
Ejercicio del wizard de sincronizacion con Bioalba.
MODO SEGURO: solo sincroniza empleados ya existentes en la DB local (es_nuevo=False).
NO crea empleados nuevos.
"""
import urllib.request, json

TOKEN = None
BASE_URL = "http://127.0.0.1:8000"

# 1. Login para obtener token
def login():
    # OAuth2PasswordRequestForm requiere form-urlencoded
    import urllib.parse
    form_data = urllib.parse.urlencode({"username": "admin", "password": "aguacol2026"}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/auth/login/", data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read())
    return res.get("access_token")

def get(path, token):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def post(path, data, token):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

print("=== EJERCICIO SYNC WIZARD BIOALBA (MODO SEGURO) ===\n")

# 1. Login
print("PASO 0: Autenticando...")
token = login()
print(f"  Token obtenido: {token[:30]}...")

# 2. Guardian Check (lo mismo que hace el boton Empleados)
print("\nPASO 1: Guardian Check (analisis de areas/cargos en Bioalba vs local)...")
print("  (Esto puede tardar 30-60s mientras descarga el Excel de Bioalba)")
guardian = get("/api/sync/guardian/check/", token)
print(f"  Status: {guardian.get('status')}")
print(f"  Areas conocidas (ya en DB): {guardian.get('areas_conocidas', [])}")
print(f"  Areas NUEVAS (no en DB):    {guardian.get('nuevas_areas', [])}")
print(f"  Cargos conocidos:           {len(guardian.get('cargos_conocidos', []))} cargos")
print(f"  Cargos NUEVOS:              {len(guardian.get('nuevos_cargos', []))} cargos")
print(f"  Generos nuevos:             {guardian.get('nuevos_generos', [])}")

# 3. Preview de empleados - SOLO areas conocidas (las que ya existen en la DB)
areas_conocidas = guardian.get("areas_conocidas", [])
if not areas_conocidas:
    print("\n  No hay areas conocidas para sincronizar. Abortando.")
    exit(0)

print(f"\nPASO 2: Preview de empleados en areas CONOCIDAS: {areas_conocidas}")
# Construir resoluciones solo con areas conocidas (sin crear nada nuevo)
resoluciones_areas = {a: a for a in areas_conocidas}  # mapeo identico

preview_payload = {
    "resoluciones_areas": resoluciones_areas,
    "selected_cargos": guardian.get("cargos_conocidos", [])  # solo cargos existentes
}
print(f"  Payload: {json.dumps(preview_payload, ensure_ascii=False)[:200]}")

preview = post("/api/sync/empleados/preview/", preview_payload, token)
total = len(preview)
nuevos = sum(1 for e in preview if e.get("es_nuevo"))
existentes = sum(1 for e in preview if not e.get("es_nuevo"))
print(f"\n  Total empleados en Bioalba para esas areas: {total}")
print(f"  Empleados NUEVOS (no en local):              {nuevos}")
print(f"  Empleados EXISTENTES (ya en local):          {existentes}")

print("\n  Empleados existentes que se actualizarian:")
for e in preview:
    if not e.get("es_nuevo"):
        cambio = "(CAMBIO AREA)" if e.get("cambio_area") else ""
        print(f"    {e['rut']} | {e['nombre']} | area_bio={e['area']} | area_local={e.get('area_local')} {cambio}")

# 4. Solo sincronizar los EXISTENTES (no nuevos)
existentes_ruts = [e["rut"] for e in preview if not e.get("es_nuevo")]
print(f"\nPASO 3: Sincronizacion SEGURA de {len(existentes_ruts)} empleados existentes")
print("  (Solo actualiza datos, NO crea empleados nuevos)")
print(f"  RUTs a sincronizar: {existentes_ruts[:5]}{'...' if len(existentes_ruts)>5 else ''}")

if not existentes_ruts:
    print("  No hay empleados existentes para sincronizar en estas areas.")
    exit(0)

# El endpoint /now/ acepta ruts + areas + selected_cargos
# Limite: 10 RUTs por batch -> dividir en lotes
MAX_BATCH = 10
cargos_conocidos = guardian.get("cargos_conocidos", [])

total_nuevos = 0
total_actualizados = 0
total_errores = 0

for i in range(0, len(existentes_ruts), MAX_BATCH):
    batch = existentes_ruts[i:i + MAX_BATCH]
    print(f"\n  Batch {i//MAX_BATCH + 1}: sincronizando {len(batch)} empleados...")

    sync_payload = {
        "ruts": batch,
        "areas": areas_conocidas,
        "selected_cargos": cargos_conocidos
    }

    try:
        sync_result = post("/api/sync/empleados/now/", sync_payload, token)
        stats = sync_result.get("stats", {})
        nuevos = stats.get("empleados_nuevos", 0)
        actualizados = stats.get("empleados_actualizados", 0)
        sin_cambios = stats.get("empleados_sin_cambios", 0)
        errores = stats.get("errores", 0)
        total_nuevos += nuevos
        total_actualizados += actualizados
        total_errores += errores
        print(f"    nuevos={nuevos} | actualizados={actualizados} | sin_cambios={sin_cambios} | errores={errores}")
        if errores > 0:
            for det in stats.get("detalles_errores", []):
                print(f"    ERROR: {det}")
    except Exception as e:
        print(f"    ERROR en batch: {e}")

print(f"\n=== RESULTADO FINAL ===")
print(f"  Empleados nuevos (NO deberia haber):  {total_nuevos}")
print(f"  Empleados actualizados:               {total_actualizados}")
print(f"  Errores:                              {total_errores}")
if total_nuevos > 0:
    print("  ADVERTENCIA: Se crearon empleados nuevos. Verificar si era esperado.")
else:
    print("  OK: No se crearon empleados nuevos. Base de datos limpia.")
