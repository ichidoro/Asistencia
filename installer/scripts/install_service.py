"""
install_service.py — Registra la app como Servicio de Windows via NSSM.
NSSM bundleado en assets/nssm.exe. NO se descarga en runtime.

Hechos confirmados:
- main.py esta en backend/main.py (12162 bytes)
- uvicorn usa "backend.main:app" -> CWD DEBE ser la raiz (padre de backend/)
- NSSM necesita admin para install/set/start

Uso: python install_service.py <ruta_instalacion>
"""
import sys, os, subprocess
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace") if hasattr(sys.stdout, "reconfigure") else None

APP_DIR      = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/Asistencia")
VENV_PYTHON  = APP_DIR / ".venv" / "Scripts" / "python.exe"
MAIN_SCRIPT  = APP_DIR / "backend" / "main.py"
SERVICE_NAME = "AsistenciaAguacol"
SERVICE_DISPLAY = "Sistema de Asistencia Aguacol"
SERVICE_DESC = "Sistema de Gestion de Asistencia - Aguacol SPA - Inicio automatico"
NSSM_PATH    = APP_DIR / "assets" / "nssm.exe"
LOG_DIR      = APP_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE     = LOG_DIR / "service_install.log"


def log(msg):
    print(msg, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def run_nssm(args, desc):
    cmd = [str(NSSM_PATH)] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        if r.returncode == 0:
            log(f"  OK: {desc}")
            return True
        else:
            stderr = r.stderr.strip().replace("\x00", "")[:120]
            log(f"  FALLO: {desc} -> {stderr}")
            return False
    except Exception as ex:
        log(f"  ERROR: {desc} -> {ex}")
        return False


def install():
    log(f"\n{'='*60}")
    log(f"Instalando servicio: {SERVICE_NAME}")
    log(f"  APP_DIR:     {APP_DIR}")
    log(f"  VENV_PYTHON: {VENV_PYTHON}")
    log(f"  MAIN_SCRIPT: {MAIN_SCRIPT}")
    log(f"  NSSM_PATH:   {NSSM_PATH}")
    log(f"{'='*60}")

    # Validaciones
    if not VENV_PYTHON.exists():
        log(f"  CRITICO: {VENV_PYTHON} no existe")
        sys.exit(1)
    if not MAIN_SCRIPT.exists():
        log(f"  CRITICO: {MAIN_SCRIPT} no existe")
        sys.exit(1)
    if not NSSM_PATH.exists():
        log(f"  CRITICO: {NSSM_PATH} no existe")
        sys.exit(1)

    # 1. Detener y eliminar servicio previo (ignora errores si no existe)
    log("\n--- Limpiando servicio anterior ---")
    subprocess.run([str(NSSM_PATH), "stop", SERVICE_NAME],
                   capture_output=True, timeout=15)
    subprocess.run([str(NSSM_PATH), "remove", SERVICE_NAME, "confirm"],
                   capture_output=True, timeout=15)

    # 2. Instalar servicio nuevo
    log("\n--- Registrando servicio ---")
    if not run_nssm(["install", SERVICE_NAME, str(VENV_PYTHON)],
                    "Registrar servicio"):
        log("  No se pudo registrar. Abortando.")
        sys.exit(1)

    # 3. Configurar parametros (documentacion NSSM verificada)
    log("\n--- Configurando parametros ---")
    configs = [
        # AppDirectory = raiz del proyecto (CWD para imports "backend.xxx")
        (["set", SERVICE_NAME, "AppDirectory", str(APP_DIR)],
         "AppDirectory (CWD)"),
        # AppParameters = ruta al script main.py
        (["set", SERVICE_NAME, "AppParameters", str(MAIN_SCRIPT)],
         "AppParameters (script)"),
        # Metadatos del servicio
        (["set", SERVICE_NAME, "DisplayName", SERVICE_DISPLAY],
         "DisplayName"),
        (["set", SERVICE_NAME, "Description", SERVICE_DESC],
         "Description"),
        # Inicio automatico al encender el PC
        (["set", SERVICE_NAME, "Start", "SERVICE_AUTO_START"],
         "Start = AUTO"),
        # Logs con rotacion
        (["set", SERVICE_NAME, "AppStdout", str(LOG_DIR / "service.log")],
         "AppStdout"),
        (["set", SERVICE_NAME, "AppStderr", str(LOG_DIR / "service_err.log")],
         "AppStderr"),
        (["set", SERVICE_NAME, "AppRotateFiles", "1"],
         "AppRotateFiles (rotacion ON)"),
        (["set", SERVICE_NAME, "AppRotateBytes", "5242880"],
         "AppRotateBytes (5MB max)"),
        # Reintentar si falla (5 segundos de delay)
        (["set", SERVICE_NAME, "AppRestartDelay", "5000"],
         "AppRestartDelay (5s)"),
        # Ejecutar como LocalSystem
        (["set", SERVICE_NAME, "ObjectName", "LocalSystem"],
         "ObjectName"),
        # Sin consola visible
        (["set", SERVICE_NAME, "AppNoConsole", "1"],
         "AppNoConsole"),
        # CRITICO: forzar UTF-8 para evitar crashes de encoding
        (["set", SERVICE_NAME, "AppEnvironmentExtra", "PYTHONUTF8=1"],
         "PYTHONUTF8=1 (encoding)"),
    ]

    for args, desc in configs:
        run_nssm(args, desc)

    # 4. Iniciar el servicio
    log("\n--- Iniciando servicio ---")
    ok = run_nssm(["start", SERVICE_NAME], "Iniciar servicio")

    if ok:
        log(f"\nServicio '{SERVICE_NAME}' instalado y arrancado.")
        log("Se iniciara automaticamente en cada arranque del sistema.")
    else:
        log(f"\nADVERTENCIA: Servicio registrado pero no se pudo iniciar ahora.")
        log("Se iniciara automaticamente en el proximo arranque.")

    sys.exit(0)


if __name__ == "__main__":
    install()
