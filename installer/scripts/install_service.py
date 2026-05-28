"""
install_service.py
==================
Registra la aplicación como Servicio de Windows usando NSSM.
El servicio arranca automáticamente al encender el PC.

Usa NSSM (Non-Sucking Service Manager) — lo descarga si no está.
Uso: python install_service.py <ruta_instalacion>
"""

import sys
import os
import subprocess
import urllib.request
import zipfile
import io
from pathlib import Path

APP_DIR      = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/Asistencia")
VENV_PYTHON  = APP_DIR / ".venv" / "Scripts" / "python.exe"
MAIN_SCRIPT  = APP_DIR / "backend" / "main.py"
SERVICE_NAME = "AsistenciaAguacol"
SERVICE_DESC = "Sistema de Asistencia Aguacol - Inicio automático"
NSSM_URL     = "https://nssm.cc/release/nssm-2.24.zip"
NSSM_PATH    = APP_DIR / "assets" / "nssm.exe"

LOG_DIR      = APP_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def _download_nssm() -> bool:
    """Descarga NSSM si no está presente"""
    if NSSM_PATH.exists():
        return True
    try:
        print(f"Descargando NSSM desde {NSSM_URL}...")
        NSSM_PATH.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(NSSM_URL, timeout=30) as resp:
            data = resp.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            # Buscar nssm.exe de 64 bits
            for name in z.namelist():
                if "win64" in name.lower() and name.endswith("nssm.exe"):
                    with z.open(name) as src, open(NSSM_PATH, "wb") as dst:
                        dst.write(src.read())
                    print(f"NSSM extraído en {NSSM_PATH}")
                    return True
        return False
    except Exception as ex:
        print(f"No se pudo descargar NSSM: {ex}")
        return False


def _run(cmd: list, desc: str) -> bool:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"✓ {desc}")
            return True
        else:
            print(f"✗ {desc}: {result.stderr.strip()[:80]}")
            return False
    except Exception as ex:
        print(f"✗ {desc}: {ex}")
        return False


def install_service():
    """Registra o actualiza el servicio de Windows"""
    if not VENV_PYTHON.exists():
        print(f"✗ Python virtualenv no encontrado en {VENV_PYTHON}")
        sys.exit(1)

    # Descargar NSSM si necesario
    if not _download_nssm():
        print("✗ NSSM no disponible — usando alternativa con sc.exe")
        _install_via_sc()
        return

    nssm = str(NSSM_PATH)

    # Eliminar servicio previo si existe
    subprocess.run([nssm, "stop",   SERVICE_NAME], capture_output=True, timeout=15)
    subprocess.run([nssm, "remove", SERVICE_NAME, "confirm"], capture_output=True, timeout=15)

    # Instalar nuevo servicio
    _run([nssm, "install",    SERVICE_NAME, str(VENV_PYTHON)], "Registrar servicio")
    _run([nssm, "set", SERVICE_NAME, "AppDirectory",   str(APP_DIR)],           "Directorio de trabajo")
    _run([nssm, "set", SERVICE_NAME, "AppParameters",  str(MAIN_SCRIPT)],       "Script de inicio")
    _run([nssm, "set", SERVICE_NAME, "DisplayName",    SERVICE_DESC],            "Nombre del servicio")
    _run([nssm, "set", SERVICE_NAME, "Description",    "Sistema de Gestión de Asistencia - Aguacol SPA"], "Descripción")
    _run([nssm, "set", SERVICE_NAME, "Start",          "SERVICE_AUTO_START"],    "Inicio automático")
    _run([nssm, "set", SERVICE_NAME, "AppStdout",      str(LOG_DIR / "service.log")], "Log stdout")
    _run([nssm, "set", SERVICE_NAME, "AppStderr",      str(LOG_DIR / "service_error.log")], "Log stderr")
    _run([nssm, "set", SERVICE_NAME, "AppRestartDelay", "5000"],                 "Reintentar en 5s si falla")
    _run([nssm, "set", SERVICE_NAME, "ObjectName",     "LocalSystem"],           "Cuenta del servicio")

    # Iniciar el servicio
    _run([nssm, "start", SERVICE_NAME], "Iniciar servicio")

    print(f"\n✅ Servicio '{SERVICE_NAME}' instalado y arrancado.")
    print(f"   El sistema iniciará automáticamente cada vez que se encienda el PC.")


def _install_via_sc():
    """Alternativa: usa sc.exe + un wrapper .bat para crear el servicio"""
    wrapper_bat = APP_DIR / "service_wrapper.bat"
    wrapper_content = f"""@echo off
cd /d "{APP_DIR}"
"{VENV_PYTHON}" "{MAIN_SCRIPT}"
"""
    wrapper_bat.write_text(wrapper_content, encoding="utf-8")

    # Crear servicio con sc.exe usando cmd.exe como ejecutable
    cmd_path = os.path.join(os.environ.get("SYSTEMROOT", "C:\\Windows"), "System32", "cmd.exe")
    bin_path = f'"{cmd_path}" /c "{wrapper_bat}"'

    subprocess.run(["sc", "stop",   SERVICE_NAME], capture_output=True)
    subprocess.run(["sc", "delete", SERVICE_NAME], capture_output=True)
    _run(
        ["sc", "create", SERVICE_NAME, f"binPath={bin_path}", "start=auto", "DisplayName=Asistencia Aguacol"],
        "Registrar servicio (alternativa)"
    )
    _run(["sc", "description", SERVICE_NAME, "Sistema de Gestión de Asistencia - Aguacol SPA"], "Descripción")
    _run(["sc", "start", SERVICE_NAME], "Iniciar servicio")


if __name__ == "__main__":
    install_service()
