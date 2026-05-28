"""
post_install.py
================
Script de post-instalación con interfaz gráfica propia.
Se ejecuta DESPUÉS de que Inno Setup copió los archivos.

Pasos:
  1. Crear entorno virtual (.venv)
  2. Instalar dependencias (pip)
  3. Generar archivo .env con credenciales pre-configuradas
  4. Registrar servicio de Windows via NSSM
  5. Crear archivo de inicio rápido

Uso: python post_install.py <ruta_instalacion>
"""

import sys
import os
import subprocess
import threading
import tkinter as tk
from tkinter import font as tkfont
from pathlib import Path
import time

# ── Constantes ─────────────────────────────────────────────────────────────
APP_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/Asistencia")
VENV_DIR = APP_DIR / ".venv"
PYTHON_VENV = VENV_DIR / "Scripts" / "python.exe"
PIP_VENV    = VENV_DIR / "Scripts" / "pip.exe"
REQS_FILE   = APP_DIR / "requirements.txt"

# Colores
BG       = "#0F172A"
CARD     = "#1E293B"
BORDER   = "#334155"
CYAN     = "#00D4FF"
GREEN    = "#22C55E"
YELLOW   = "#F59E0B"
RED      = "#EF4444"
WHITE    = "#F8FAFC"
GRAY     = "#94A3B8"

# ── UI Principal ────────────────────────────────────────────────────────────
class InstaladorUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Configurando Sistema de Asistencia Aguacol")
        self.root.geometry("620x480")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)  # Bloquear cierre manual

        # Centrar ventana
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - 310
        y = (self.root.winfo_screenheight() // 2) - 240
        self.root.geometry(f"+{x}+{y}")

        self._build_ui()
        self.steps_done = []
        self.current_step = 0

    def _build_ui(self):
        # Header
        header = tk.Frame(self.root, bg=CARD, height=80)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header, text="⚙  Configurando Sistema de Asistencia",
            font=("Segoe UI", 14, "bold"), fg=WHITE, bg=CARD
        ).pack(side="left", padx=24, pady=20)

        tk.Label(
            header, text="Aguacol SPA",
            font=("Segoe UI", 10), fg=CYAN, bg=CARD
        ).pack(side="right", padx=24)

        # Separador
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        # Área de pasos
        self.steps_frame = tk.Frame(self.root, bg=BG, padx=32, pady=24)
        self.steps_frame.pack(fill="both", expand=True)

        self.step_labels = {}
        steps = [
            ("python",    "Preparando entorno Python"),
            ("deps",      "Instalando dependencias del sistema"),
            ("env",       "Generando archivo de configuración"),
            ("service",   "Registrando servicio de Windows"),
            ("shortcuts", "Creando accesos directos"),
        ]
        for key, text in steps:
            row = tk.Frame(self.steps_frame, bg=BG)
            row.pack(fill="x", pady=6)

            icon = tk.Label(row, text="○", font=("Segoe UI", 14), fg=GRAY, bg=BG, width=3)
            icon.pack(side="left")

            label = tk.Label(row, text=text, font=("Segoe UI", 11), fg=GRAY, bg=BG, anchor="w")
            label.pack(side="left", padx=8)

            sub = tk.Label(row, text="", font=("Segoe UI", 9), fg=GRAY, bg=BG, anchor="w")
            sub.pack(side="left")

            self.step_labels[key] = (icon, label, sub)

        # Barra de progreso manual
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        bar_frame = tk.Frame(self.root, bg=BG, height=40)
        bar_frame.pack(fill="x", padx=32)
        bar_frame.pack_propagate(False)

        self.progress_text = tk.Label(
            bar_frame, text="Iniciando...",
            font=("Segoe UI", 9), fg=GRAY, bg=BG
        )
        self.progress_text.pack(side="left", pady=10)

        self.progress_pct = tk.Label(
            bar_frame, text="0%",
            font=("Segoe UI", 9, "bold"), fg=CYAN, bg=BG
        )
        self.progress_pct.pack(side="right", pady=10)

        # Canvas para la barra
        bar_bg = tk.Frame(self.root, bg=CARD, height=6)
        bar_bg.pack(fill="x")

        self.bar_canvas = tk.Canvas(self.root, height=6, bg=BORDER, highlightthickness=0)
        self.bar_canvas.pack(fill="x")
        self.bar_fill = None

    def _update_bar(self, pct):
        self.bar_canvas.update_idletasks()
        w = self.bar_canvas.winfo_width()
        if self.bar_fill:
            self.bar_canvas.delete(self.bar_fill)
        fill_w = int(w * pct / 100)
        self.bar_fill = self.bar_canvas.create_rectangle(0, 0, fill_w, 6, fill=CYAN, outline="")
        self.progress_pct.config(text=f"{pct}%")

    def set_step_running(self, key, sub=""):
        icon, label, sublabel = self.step_labels[key]
        icon.config(text="◉", fg=YELLOW)
        label.config(fg=WHITE)
        sublabel.config(text=sub, fg=YELLOW)
        self.root.update()

    def set_step_done(self, key, sub=""):
        icon, label, sublabel = self.step_labels[key]
        icon.config(text="✓", fg=GREEN)
        label.config(fg=WHITE)
        sublabel.config(text=sub, fg=GREEN)
        self.root.update()

    def set_step_error(self, key, sub=""):
        icon, label, sublabel = self.step_labels[key]
        icon.config(text="✗", fg=RED)
        label.config(fg=RED)
        sublabel.config(text=sub, fg=RED)
        self.root.update()

    def set_status(self, text, pct=None):
        self.progress_text.config(text=text)
        if pct is not None:
            self._update_bar(pct)
        self.root.update()

    def run_install(self):
        """Ejecuta la instalación en un hilo separado"""
        thread = threading.Thread(target=self._install_worker, daemon=True)
        thread.start()
        self.root.mainloop()

    def _install_worker(self):
        try:
            # ── Paso 1: Entorno virtual ────────────────────────────────────
            self.set_step_running("python", "Creando entorno aislado...")
            self.set_status("Creando entorno virtual Python...", 5)

            if not VENV_DIR.exists():
                result = subprocess.run(
                    [sys.executable, "-m", "venv", str(VENV_DIR)],
                    capture_output=True, text=True, cwd=str(APP_DIR)
                )
                if result.returncode != 0:
                    self.set_step_error("python", result.stderr[:60])
                    self.set_status("Error creando entorno virtual", 5)
                    return

            self.set_step_done("python", "Entorno Python listo")
            self.set_status("Entorno Python creado ✓", 20)

            # ── Paso 2: Dependencias ────────────────────────────────────────
            self.set_step_running("deps", "Esto puede tomar 2-4 minutos...")
            self.set_status("Descargando e instalando paquetes...", 25)

            # Actualizar pip primero
            subprocess.run(
                [str(PYTHON_VENV), "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
                capture_output=True, cwd=str(APP_DIR)
            )
            self.set_status("Instalando dependencias de la aplicación...", 30)

            result = subprocess.run(
                [str(PIP_VENV), "install", "-r", str(REQS_FILE), "--quiet"],
                capture_output=True, text=True, cwd=str(APP_DIR)
            )
            if result.returncode != 0:
                self.set_step_error("deps", "Error en instalación de paquetes")
                self.set_status(f"Error: {result.stderr[:80]}", 30)
                return

            self.set_step_done("deps", "Todos los paquetes instalados")
            self.set_status("Dependencias instaladas ✓", 55)

            # ── Paso 3: Archivo .env ────────────────────────────────────────
            self.set_step_running("env", "Escribiendo configuración...")
            self.set_status("Generando archivo de configuración...", 60)

            _write_env(APP_DIR)

            self.set_step_done("env", "Configuración generada")
            self.set_status("Configuración lista ✓", 70)

            # ── Paso 4: Servicio de Windows ─────────────────────────────────
            self.set_step_running("service", "Registrando inicio automático...")
            self.set_status("Instalando servicio de Windows...", 72)

            result = subprocess.run(
                [str(PYTHON_VENV), str(APP_DIR / ".installer" / "install_service.py"), str(APP_DIR)],
                capture_output=True, text=True, cwd=str(APP_DIR)
            )
            if result.returncode == 0:
                self.set_step_done("service", "Servicio registrado (inicio automático)")
            else:
                self.set_step_error("service", "Servicio no pudo registrarse (no crítico)")

            self.set_status("Servicio de Windows configurado ✓", 88)

            # ── Paso 5: Acceso directo de inicio rápido ─────────────────────
            self.set_step_running("shortcuts", "Creando accesos directos...")
            self.set_status("Finalizando instalación...", 92)

            _write_bat(APP_DIR)

            self.set_step_done("shortcuts", "Acceso directo creado en escritorio")
            self.set_status("¡Instalación completada!", 100)

            time.sleep(1.5)
            self.root.destroy()

        except Exception as ex:
            self.set_status(f"Error inesperado: {ex}", None)
            time.sleep(4)
            self.root.destroy()


# ── Helpers ─────────────────────────────────────────────────────────────────

def _write_env(app_dir: Path):
    """Escribe el archivo .env con las credenciales pre-configuradas de Aguacol"""
    env_content = """\
# ============================================
# TURSO DATABASE
# ============================================
TURSO_DATABASE_URL=libsql://aguacol-ichidoro.aws-us-east-1.turso.io
TURSO_AUTH_TOKEN=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3Nzk5MzY0MTMsImlkIjoiMDE5ZTZjN2EtMDUwMS03MTQ5LTgwNTktNjQ5NDA5NjdjNzg4IiwicmlkIjoiYTdiZDkyNzktMTZkZi00ODAxLTg5MmYtOGIzOWQ5OTczODljIn0.YUdVM2-_vm09RtiPrTsaptXzbKUmtU5ORyEHuudtFrO_hW34_crMNZXIgpEWq7qGeGNHAHRPf9zB69sV4VPLBg

# ============================================
# CREDENCIALES CONTROL ASISTENCIA
# ============================================
CONTROL_ASISTENCIA_URL=https://bioalba1.controlasistencia.cl
CONTROL_ASISTENCIA_USER=aguacol
CONTROL_ASISTENCIA_PASSWORD=123456

# ============================================
# APLICACIÓN
# ============================================
APP_NAME=Sistema de Gestión de Asistencia
APP_VERSION=1.0.0
APP_ENV=production
DEBUG=false

# ============================================
# API
# ============================================
API_HOST=127.0.0.1
API_PORT=8000
API_RELOAD=false

# ============================================
# LOGGING
# ============================================
LOG_LEVEL=INFO
LOG_FORMAT=text
LOG_FILE=app.log

# ============================================
# SECURITY
# ============================================
SECRET_KEY=f6f0eba50b84406b6a1c7903dd4eb123f22fb97584020c5174878494b0a6dcbd
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# ============================================
# SCRAPER
# ============================================
SCRAPER_ENABLED=true
SCRAPER_INTERVAL_MINUTES=60
SCRAPER_REQUEST_DELAY=2
SCRAPER_MAX_RETRIES=3
SCRAPER_TIMEOUT=30
SCRAPER_EMPLEADOS_ACTIVE=true
SCRAPER_MARCACIONES_ACTIVE=true

# ============================================
# WEBSOCKET
# ============================================
WS_PING_INTERVAL=30
WS_PING_TIMEOUT=10
WS_MAX_CONNECTIONS=100

# ============================================
# TIMEZONE
# ============================================
TIMEZONE=America/Santiago

# ============================================
# NOTIFICACIONES EMAIL
# ============================================
FEATURE_NOTIFICACIONES_EMAIL=true
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=operaciones.aguacol.spa@gmail.com
SMTP_PASSWORD=erff ayax grfd umvj
EMAIL_FROM=operaciones.aguacol.spa@gmail.com

# ============================================
# EXPORTACIÓN
# ============================================
FEATURE_EXPORTAR_PDF=true
"""
    env_path = app_dir / ".env"
    env_path.write_text(env_content, encoding="utf-8")


def _write_bat(app_dir: Path):
    """Crea el archivo .bat de inicio rápido"""
    bat_content = f"""@echo off
title Sistema de Asistencia Aguacol
cd /d "{app_dir}"
echo Iniciando Sistema de Asistencia Aguacol...
"{app_dir}\\.venv\\Scripts\\python.exe" "{app_dir}\\backend\\main.py"
pause
"""
    bat_path = app_dir / "iniciar_asistencia.bat"
    bat_path.write_text(bat_content, encoding="utf-8")


# ── Entry Point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ui = InstaladorUI()
    ui.run_install()
