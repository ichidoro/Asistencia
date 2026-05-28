"""
uninstall_service.py
====================
Elimina el servicio de Windows al desinstalar la aplicación.
Inno Setup lo llama automáticamente desde la sección [UninstallRun].
"""

import sys
import subprocess
from pathlib import Path

APP_DIR      = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/Asistencia")
SERVICE_NAME = "AsistenciaAguacol"
NSSM_PATH    = APP_DIR / "assets" / "nssm.exe"


def uninstall_service():
    if NSSM_PATH.exists():
        subprocess.run([str(NSSM_PATH), "stop",   SERVICE_NAME], capture_output=True, timeout=15)
        subprocess.run([str(NSSM_PATH), "remove", SERVICE_NAME, "confirm"], capture_output=True, timeout=15)
    else:
        subprocess.run(["sc", "stop",   SERVICE_NAME], capture_output=True)
        subprocess.run(["sc", "delete", SERVICE_NAME], capture_output=True)
    print(f"✓ Servicio '{SERVICE_NAME}' eliminado.")


if __name__ == "__main__":
    uninstall_service()
