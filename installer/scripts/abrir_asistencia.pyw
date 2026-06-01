"""
abrir_asistencia.pyw
====================
Lanzador silencioso del Sistema de Asistencia Aguacol.
Extensión .pyw = Python SIN ventana de consola.

1. Verifica si el servidor ya está corriendo en localhost:8000
2. Si no: inicia el servicio de Windows (o pythonw como fallback)
3. Espera a que el servidor esté listo (polling)
4. Abre el navegador en http://localhost:8000
"""

import subprocess
import urllib.request
import webbrowser
import time
import sys
from pathlib import Path

APP_DIR      = Path(__file__).parent
VENV_PYTHONW = APP_DIR / ".venv" / "Scripts" / "pythonw.exe"
MAIN_SCRIPT  = APP_DIR / "backend" / "main.py"
SERVICE_NAME = "AsistenciaAguacol"
APP_URL      = "http://localhost:8000"
MAX_WAIT     = 30  # segundos máximos esperando que arranque


def server_running() -> bool:
    """Retorna True si el servidor ya responde"""
    try:
        with urllib.request.urlopen(f"{APP_URL}/ping", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def start_service() -> bool:
    """Intenta iniciar el servicio de Windows"""
    try:
        result = subprocess.run(
            ["sc", "start", SERVICE_NAME],
            capture_output=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def service_running() -> bool:
    """Retorna True si el servicio de Windows está corriendo"""
    try:
        result = subprocess.run(
            ["sc", "query", SERVICE_NAME],
            capture_output=True, text=True, timeout=5
        )
        return "RUNNING" in result.stdout
    except Exception:
        return False


def start_fallback():
    """Fallback: inicia directamente con pythonw (sin consola)"""
    if VENV_PYTHONW.exists():
        subprocess.Popen(
            [str(VENV_PYTHONW), str(MAIN_SCRIPT)],
            cwd=str(APP_DIR),
            creationflags=0x00000008  # DETACHED_PROCESS
        )


def main():
    # Si el servidor ya responde → abrir directamente
    if server_running():
        webbrowser.open(APP_URL)
        return

    # Intentar arrancar via servicio de Windows
    if service_running():
        pass  # Ya está corriendo pero el servidor no respondió aún
    elif not start_service():
        # Servicio no disponible → fallback directo
        start_fallback()

    # Esperar a que el servidor esté listo
    for _ in range(MAX_WAIT * 2):  # cada 0.5s
        if server_running():
            break
        time.sleep(0.5)

    # Abrir el navegador
    webbrowser.open(APP_URL)


if __name__ == "__main__":
    main()
