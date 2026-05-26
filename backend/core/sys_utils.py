import socket
import subprocess
import time
import os
from loguru import logger

def is_port_in_use(port: int) -> bool:
    """Check if a port is currently in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def get_pids_using_port(port: int) -> set:
    """
    Finds PIDs using a port using native Windows 'netstat' command.
    This is more reliable than psutil for some zombie states.
    """
    pids = set()
    try:
        # Run netstat -ano to find PIDs mapping to the port
        cmd = f"netstat -ano | findstr :{port}"
        output = subprocess.check_output(cmd, shell=True).decode()
        
        for line in output.splitlines():
            parts = line.strip().split()
            # Line format: TCP  0.0.0.0:8000  0.0.0.0:0  LISTENING  1234
            if len(parts) > 4 and f":{port}" in parts[1]:
                pid = parts[-1]
                if pid.isdigit() and int(pid) > 0:
                    pids.add(int(pid))
    except subprocess.CalledProcessError:
        pass # Port not found
    except Exception as e:
        logger.error(f"Error checking netstat: {e}")
        
    return pids

def force_kill_pid(pid: int):
    """Uses taskkill /F to aggressively kill a PID"""
    try:
        # /F = Force, /T = Tree (kill children), /PID = Process ID
        subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.warning(f"   💀 Force Killed PID {pid} via taskkill")
    except Exception as e:
        logger.error(f"Failed to taskkill {pid}: {e}")

def kill_process_on_port(port: int) -> bool:
    """
    Nuclear option: Finds any process holding the port and terminates it.
    Combines netstat detection and taskkill.
    Retries up to 3 times to ensure success.
    """
    max_retries = 3
    for attempt in range(max_retries):
        if not is_port_in_use(port):
            # Double check with binding
            if test_port_binding(port):
                return True
            logger.warning(f"⚠️ Port {port} seems free but binding failed. Phantom process?")

        if attempt > 0:
             logger.info(f"🔄 Retry cleanup {attempt+1}/{max_retries}...")

        logger.warning(f"⚠️ Port {port} is occupied. Initiating cleanup protocol...")
        
        # 1. Try native detection
        target_pids = get_pids_using_port(port)
        
        if not target_pids:
            logger.warning("Could not identify PID holding the port (Access Denied?).")
            # If we can't see it, we can't kill it. 
            # But maybe it's closing? Wait and retry.
            time.sleep(1)
            continue
            
        # 2. EXECUTE
        for pid in target_pids:
            if pid == os.getpid():
                continue # Don't kill self
                
            logger.info(f"   🎯 Targeting PID {pid}...")
            # Guarantee death with taskkill
            force_kill_pid(pid)
            
        # 3. Verification wait
        time.sleep(1.5)
        
        # 4. Check if free
        if test_port_binding(port):
            logger.success(f"✅ Port {port} successfully liberated.")
            return True
            
    logger.error(f"❌ Failed to release port {port} after {max_retries} attempts.")
    return False

def test_port_binding(port: int) -> bool:
    """
    Tries to bind to the port to verify it is explicitly available.
    Returns True if bind succeeds (and immediately closes), False otherwise.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            # SO_REUSEADDR helps, but on Windows SO_EXCLUSIVEADDRUSE is default strictly.
            # We just want to see if we CAN bind.
            s.bind(('0.0.0.0', port))
            return True
    except OSError:
        return False
    except Exception:
        return False


# Global to hold lock file handle and prevent GC
_lock_file = None

def ensure_single_instance():
    """
    Garantiza que solo exista una instancia del worker ejecutándose.
    Si detecta otra instancia (zombie o colgada), lee su PID y la termina forzosamente.
    """
    global _lock_file
    import sys
    import os
    import time
    
    local_dir = os.path.join("data", "local_db")
    os.makedirs(local_dir, exist_ok=True)
    lock_path = os.path.join(local_dir, "app.lock")
    pid_path = os.path.join(local_dir, "app.pid")
    
    # Intentar abrir el archivo de bloqueo
    _lock_file = open(lock_path, "w")
    
    # Intentar adquirir el bloqueo de forma exclusiva y no bloqueante
    acquired = False
    
    if sys.platform == "win32":
        import msvcrt
        try:
            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            acquired = True
        except OSError:
            pass
    else:
        import fcntl
        try:
            fcntl.flock(_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            pass
            
    if acquired:
        # Bloqueo adquirido con éxito: guardar el PID actual
        try:
            with open(pid_path, "w") as f:
                f.write(str(os.getpid()))
            logger.info(f"🔒 Instancia única: Bloqueo adquirido exitosamente. PID: {os.getpid()}")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo registrar el PID actual en {pid_path}: {e}")
        return
        
    # Si falló, significa que otra instancia retiene el bloqueo
    logger.warning("⚠️ Conflicto de instancia: Detectado otro proceso del servidor activo o bloqueado.")
    
    old_pid = None
    if os.path.exists(pid_path):
        try:
            with open(pid_path, "r") as f:
                old_pid = int(f.read().strip())
        except Exception as e:
            logger.warning(f"No se pudo leer el PID anterior desde {pid_path}: {e}")
            
    if old_pid and old_pid != os.getpid():
        logger.warning(f"💀 Detectada instancia zombie (PID: {old_pid}). Forzando terminación...")
        try:
            if sys.platform == "win32":
                # Forzar terminación del árbol de procesos en Windows
                subprocess.run(f"taskkill /F /T /PID {old_pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                import signal
                os.kill(old_pid, signal.SIGKILL)
            logger.success(f"💀 Instancia zombie (PID: {old_pid}) terminada de forma agresiva.")
        except Exception as e:
            logger.error(f"No se pudo matar la instancia zombie {old_pid}: {e}")
            
        # Esperar a que el OS libere el socket y el lock de archivos
        time.sleep(1.5)
        
        # Reintentar adquirir el bloqueo
        try:
            if sys.platform == "win32":
                msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                
            # Éxito en el reintento: escribir nuestro PID
            with open(pid_path, "w") as f:
                f.write(str(os.getpid()))
            logger.success(f"🔒 Bloqueo adquirido tras remoción de instancia zombie. PID: {os.getpid()}")
        except OSError as retry_err:
            logger.critical(f"🛑 Falló la adquisición del bloqueo en reintento: {retry_err}")
            # Si aún falla, continuamos de todos modos bajo riesgo de conflicto
    else:
        logger.warning("⚠️ No se pudo determinar el PID anterior para forzar la terminación.")

