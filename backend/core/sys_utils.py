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
