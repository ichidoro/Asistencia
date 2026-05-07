import os
import sys
import multiprocessing
import threading
import time
import webbrowser
import socket
from loguru import logger

# IMPORTANT FOR WINDOWS COMPILED EXECUTABLES
if sys.platform.startswith('win'):
    multiprocessing.freeze_support()

if getattr(sys, 'frozen', False):
    import builtins
    appdata = os.environ.get('LOCALAPPDATA', os.environ.get('APPDATA', os.path.expanduser("~")))
    log_dir = os.path.join(appdata, "Aguacol_Asistencia", "logs")
    os.makedirs(log_dir, exist_ok=True)
    crash_log_path = os.path.join(log_dir, "crash.log")
    
    class LoggerWriter:
        def __init__(self, filepath):
            self.file = open(filepath, "a", encoding="utf-8")
        def write(self, message):
            if message != '\n':
                self.file.write(message + '\n')
                self.file.flush()
        def flush(self):
            self.file.flush()
        def isatty(self):
            return False

    sys.stdout = LoggerWriter(crash_log_path)
    sys.stderr = LoggerWriter(crash_log_path)


# Calcular el directorio base real (resolviendo el problema de correr desde una subcarpeta o desde un EXE)
if getattr(sys, 'frozen', False):
    # Si está compilado, PyInstaller mete todo en _MEIPASS
    base_path = sys._MEIPASS
else:
    # Si no está compilado, el script original vive en Empaquetado/start_app.py
    # Así que el proyecto base es la carpeta ARRIBA de esta (..)
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if base_path not in sys.path:
    sys.path.insert(0, base_path)

# NOW it is safe to import backend modules
from backend.main import app
from backend.core.config import settings
from backend.core.sys_utils import kill_process_on_port
import uvicorn

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def open_browser():
    logger.info(f"⏳ Esperando a que el puerto {settings.API_PORT} esté listo (Timeout: 60s)...")
    # Esperamos hasta 60 segundos (el inicio con DB Sync puede ser lento)
    for _ in range(120):
        if is_port_in_use(settings.API_PORT):
            break
        time.sleep(0.5)
    else:
        logger.error("🛑 Timeout: Servidor uvicorn no levantó a tiempo para abrir el navegador.")
        return
        
    time.sleep(0.5)  # Da unos milisegundos extra para que el framework inicie completamente
    url = f"http://localhost:{settings.API_PORT}"
    logger.info(f"🌐 Abriendo navegador en {url}...")
    try:
        webbrowser.open(url)
    except Exception as e:
        logger.error(f"No se pudo abrir el navegador: {e}")

if __name__ == "__main__":
    try:
        if kill_process_on_port(settings.API_PORT):
            logger.success(f"✅ Puerto {settings.API_PORT} limpiado y listo.")
    except Exception as e:
        logger.warning(f"Advertencia al limpiar puertos: {e}")

    threading.Thread(target=open_browser, daemon=True).start()
    
    logger.info(f"🚀 Iniciando binario empaquetado y servidor interno...")
    
    # IMPORTANTE para PyInstaller: pasar la instancia `app` y log_config=None
    # para que Uvicorn no intente escribir en sys.stdout (que es None en modo --noconsole)
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=False,
        log_config=None,  # <-- ESTO EVITA EL ERROR DE NULL POINTER (isatty)
        access_log=False
    )
    
    # --- NUCLEAR SHUTDOWN ---
    # Una vez que uvicorn termina (porque se cerró la ventana o se recibió señal),
    # forzamos el cierre de TODO el árbol de procesos/hilos para evitar zombis.
    logger.info("🛑 Cierre Nuclear: Finalizando hilos y procesos...")
    os._exit(0)
