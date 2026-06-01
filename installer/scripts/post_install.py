"""
post_install.py — Script de post-instalacion SILENCIOSO.
Inno Setup muestra su propia UI — este script no crea ventanas.

Pasos:
  1. Crear .venv
  2. pip install -r requirements.txt
  3. Generar .env
  4. Registrar servicio Windows (via install_service.py)
  5. Generar abrir_asistencia.pyw (launcher con espera)

Uso: python post_install.py <ruta_instalacion>
"""
import sys, os, subprocess
from pathlib import Path

APP_DIR     = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/Asistencia")
VENV_DIR    = APP_DIR / ".venv"
PYTHON_VENV = VENV_DIR / "Scripts" / "python.exe"
PIP_VENV    = VENV_DIR / "Scripts" / "pip.exe"
REQS_FILE   = APP_DIR / "requirements.txt"
LOG_FILE    = APP_DIR / "logs" / "install.log"


def log(msg):
    print(msg, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


# ── Paso 1: .venv ───────────────────────────────────────────────
def venv_is_healthy():
    """Verifica que el .venv funcione (no apunte a un Python desinstalado)."""
    if not PYTHON_VENV.exists():
        return False
    try:
        r = subprocess.run([str(PYTHON_VENV), "--version"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and "Python" in r.stdout:
            log(f"  .venv existente OK: {r.stdout.strip()}")
            return True
    except Exception:
        pass
    return False


def create_venv():
    log("=== PASO 1: Creando entorno virtual ===")

    if VENV_DIR.exists():
        if venv_is_healthy():
            return True
        log("  .venv existente ROTO (Python desinstalado?). Eliminando...")
        import shutil
        shutil.rmtree(str(VENV_DIR), ignore_errors=True)

    r = subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)],
                       capture_output=True, text=True, cwd=str(APP_DIR))
    if r.returncode != 0:
        log(f"  ERROR: {r.stderr[:200]}")
        return False
    log(f"  .venv creado con: {sys.executable}")
    return True


# ── Paso 2: dependencias ────────────────────────────────────────
def install_deps():
    log("=== PASO 2: Instalando dependencias ===")
    subprocess.run([str(PYTHON_VENV), "-m", "pip", "install", "--upgrade",
                    "pip", "--quiet"], capture_output=True, cwd=str(APP_DIR))
    r = subprocess.run([str(PIP_VENV), "install", "-r", str(REQS_FILE),
                        "--quiet"], capture_output=True, text=True,
                       cwd=str(APP_DIR))
    if r.returncode != 0:
        log(f"  ERROR pip: {r.stderr[:300]}")
        return False
    log("  Dependencias instaladas.")
    return True


# ── Paso 3: .env ────────────────────────────────────────────────
def write_env():
    log("=== PASO 3: Generando .env ===")
    env_path = APP_DIR / ".env"
    if env_path.exists() and env_path.stat().st_size > 100:
        log("  .env ya existe y tiene contenido, conservando.")
        return True
    content = """\
TURSO_DATABASE_URL=libsql://aguacol-ichidoro.aws-us-east-1.turso.io
TURSO_AUTH_TOKEN=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3Nzk5MzY0MTMsImlkIjoiMDE5ZTZjN2EtMDUwMS03MTQ5LTgwNTktNjQ5NDA5NjdjNzg4IiwicmlkIjoiYTdiZDkyNzktMTZkZi00ODAxLTg5MmYtOGIzOWQ5OTczODljIn0.YUdVM2-_vm09RtiPrTsaptXzbKUmtU5ORyEHuudtFrO_hW34_crMNZXIgpEWq7qGeGNHAHRPf9zB69sV4VPLBg
CONTROL_ASISTENCIA_URL=https://bioalba1.controlasistencia.cl
CONTROL_ASISTENCIA_USER=aguacol
CONTROL_ASISTENCIA_PASSWORD=123456
APP_NAME=Sistema de Gestion de Asistencia
APP_VERSION=1.0.0
APP_ENV=production
DEBUG=false
API_HOST=127.0.0.1
API_PORT=8000
API_RELOAD=false
LOG_LEVEL=INFO
LOG_FORMAT=text
LOG_FILE=app.log
SECRET_KEY=f6f0eba50b84406b6a1c7903dd4eb123f22fb97584020c5174878494b0a6dcbd
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
SCRAPER_ENABLED=true
SCRAPER_INTERVAL_MINUTES=60
SCRAPER_REQUEST_DELAY=2
SCRAPER_MAX_RETRIES=3
SCRAPER_TIMEOUT=30
SCRAPER_EMPLEADOS_ACTIVE=true
SCRAPER_MARCACIONES_ACTIVE=true
WS_PING_INTERVAL=30
WS_PING_TIMEOUT=10
WS_MAX_CONNECTIONS=100
TIMEZONE=America/Santiago
FEATURE_NOTIFICACIONES_EMAIL=true
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=operaciones.aguacol.spa@gmail.com
SMTP_PASSWORD=erff ayax grfd umvj
EMAIL_FROM=operaciones.aguacol.spa@gmail.com
FEATURE_EXPORTAR_PDF=true
"""
    try:
        env_path.write_text(content, encoding="utf-8")
        log("  .env generado.")
        return True
    except Exception as ex:
        log(f"  ERROR: {ex}")
        return False


# ── Paso 4: servicio Windows ────────────────────────────────────
def install_service():
    log("=== PASO 4: Registrando servicio de Windows ===")
    script = APP_DIR / ".installer" / "install_service.py"
    if not script.exists():
        log(f"  ADVERTENCIA: {script} no encontrado.")
        return False
    r = subprocess.run([str(PYTHON_VENV), str(script), str(APP_DIR)],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       cwd=str(APP_DIR))
    log(r.stdout.strip() if r.stdout else "")
    if r.returncode != 0:
        log(f"  ADVERTENCIA: {r.stderr[:200] if r.stderr else 'ver log de servicio'}")
        return False
    return True


# ── Paso 5: launcher .pyw ──────────────────────────────────────
def write_launcher():
    log("=== PASO 5: Generando launcher ===")
    # Hechos verificados:
    # - main.py esta en backend/main.py
    # - uvicorn usa "backend.main:app" -> CWD = raiz app
    # - El launcher espera al servidor antes de abrir browser
    content = f'''"""
abrir_asistencia.pyw
Lanzador silencioso del Sistema de Asistencia Aguacol.
Generado por el instalador. No editar manualmente.
"""
import subprocess, urllib.request, webbrowser, time, sys
from pathlib import Path

APP_DIR      = Path(r"{APP_DIR}")
VENV_PYTHON  = APP_DIR / ".venv" / "Scripts" / "pythonw.exe"
MAIN_SCRIPT  = APP_DIR / "backend" / "main.py"
SERVICE_NAME = "AsistenciaAguacol"
APP_URL      = "http://localhost:8000"

def server_running():
    try:
        with urllib.request.urlopen(f"{{APP_URL}}/ping", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False

def start_service():
    try:
        subprocess.run(["sc", "start", SERVICE_NAME],
                       capture_output=True, timeout=10)
    except Exception:
        pass

def start_direct():
    if VENV_PYTHON.exists() and MAIN_SCRIPT.exists():
        subprocess.Popen(
            [str(VENV_PYTHON), str(MAIN_SCRIPT)],
            cwd=str(APP_DIR),
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )

if not server_running():
    start_service()
    time.sleep(3)
    if not server_running():
        start_direct()
    # Esperar hasta 60 segundos
    for _ in range(120):
        if server_running():
            break
        time.sleep(0.5)

webbrowser.open(APP_URL)
'''
    try:
        (APP_DIR / "abrir_asistencia.pyw").write_text(content, encoding="utf-8")
        log("  Launcher generado.")
        return True
    except Exception as ex:
        log(f"  ERROR: {ex}")
        return False


# ── Main ────────────────────────────────────────────────────────
if __name__ == "__main__":
    log(f"\nInstalacion: {APP_DIR}")
    log(f"Python: {sys.executable}\n")

    ok1 = create_venv()
    ok2 = install_deps() if ok1 else False
    ok3 = write_env()
    ok4 = install_service() if ok1 else False
    ok5 = write_launcher()

    log(f"\n{'='*40}")
    log(f"  Entorno virtual : {'OK' if ok1 else 'FALLO'}")
    log(f"  Dependencias    : {'OK' if ok2 else 'FALLO'}")
    log(f"  Configuracion   : {'OK' if ok3 else 'FALLO'}")
    log(f"  Servicio Windows: {'OK' if ok4 else 'ADVERTENCIA'}")
    log(f"  Launcher        : {'OK' if ok5 else 'FALLO'}")
    log(f"{'='*40}")

    if not ok1 or not ok2:
        log("\nERROR CRITICO: Instalacion incompleta.")
        sys.exit(1)

    log("\nInstalacion completada.")
    sys.exit(0)
