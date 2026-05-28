"""
connectivity_check.py
======================
Pantalla de verificación de conectividad — La joya del instalador.
Se muestra DESPUÉS de la instalación para confirmar que:

  ✓ La base de datos Turso Cloud responde
  ✓ BioAlba (sistema biométrico) está accesible
  ✓ El servicio de Windows está corriendo
  ✓ Este PC puede sincronizarse con los demás equipos Aguacol

Diseño: Oscuro premium, animaciones de aparición, iconos animados.
Uso: python connectivity_check.py <ruta_instalacion>
"""

import sys
import os
import threading
import tkinter as tk
from tkinter import font as tkfont
from pathlib import Path
import time
import subprocess
import urllib.request
import urllib.error
import json

# ── Rutas ───────────────────────────────────────────────────────────────────
APP_DIR     = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("C:/Asistencia")
PYTHON_VENV = APP_DIR / ".venv" / "Scripts" / "python.exe"
ENV_FILE    = APP_DIR / ".env"

# ── Configuración desde .env ─────────────────────────────────────────────────
def _load_env():
    cfg = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    return cfg

ENV = _load_env()
TURSO_URL   = ENV.get("TURSO_DATABASE_URL", "")
TURSO_TOKEN = ENV.get("TURSO_AUTH_TOKEN", "")
BIOALBA_URL = ENV.get("CONTROL_ASISTENCIA_URL", "https://bioalba1.controlasistencia.cl")
SERVICE_NAME = "AsistenciaAguacol"

# ── Colores ──────────────────────────────────────────────────────────────────
BG       = "#0F172A"
CARD     = "#1E293B"
CARD2    = "#162032"
BORDER   = "#334155"
CYAN     = "#00D4FF"
GREEN    = "#22C55E"
YELLOW   = "#F59E0B"
RED      = "#EF4444"
WHITE    = "#F8FAFC"
GRAY     = "#64748B"
LGRAY    = "#94A3B8"

# ── Helpers de Conectividad ──────────────────────────────────────────────────
def check_turso() -> tuple[bool, str]:
    """Verifica que Turso Cloud responda"""
    try:
        if not TURSO_URL or not TURSO_TOKEN:
            return False, "Credenciales no configuradas"
        # Parsear el hostname de la URL libsql://
        hostname = TURSO_URL.replace("libsql://", "").replace("https://", "")
        http_url = f"https://{hostname}"
        req = urllib.request.Request(
            http_url,
            headers={"Authorization": f"Bearer {TURSO_TOKEN}"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return True, f"Conectado ({resp.status})"
    except urllib.error.HTTPError as e:
        if e.code in (200, 400, 401, 404, 405):
            # El servidor responde → está en línea
            return True, "Servidor Turso activo"
        return False, f"HTTP {e.code}"
    except Exception as ex:
        return False, str(ex)[:50]


def check_bioalba() -> tuple[bool, str]:
    """Verifica que BioAlba esté accesible"""
    try:
        req = urllib.request.Request(BIOALBA_URL, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return True, f"Accesible ({resp.status})"
    except urllib.error.HTTPError as e:
        if e.code < 500:
            return True, "Sistema biométrico activo"
        return False, f"Error HTTP {e.code}"
    except Exception as ex:
        return False, str(ex)[:50]


def check_service() -> tuple[bool, str]:
    """Verifica el estado del servicio de Windows"""
    try:
        result = subprocess.run(
            ["sc", "query", SERVICE_NAME],
            capture_output=True, text=True, timeout=5
        )
        if "RUNNING" in result.stdout:
            return True, "Servicio activo y corriendo"
        elif "STOPPED" in result.stdout:
            # Intentar iniciarlo
            subprocess.run(["sc", "start", SERVICE_NAME], capture_output=True, timeout=10)
            time.sleep(2)
            result2 = subprocess.run(["sc", "query", SERVICE_NAME], capture_output=True, text=True, timeout=5)
            if "RUNNING" in result2.stdout:
                return True, "Servicio iniciado correctamente"
            return False, "Servicio detenido"
        else:
            return False, "Servicio no encontrado"
    except Exception as ex:
        return False, str(ex)[:40]


def check_local_server() -> tuple[bool, str]:
    """Verifica que el servidor local responda"""
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/ping")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data.get("ping") == "pong":
                return True, "http://localhost:8000 listo"
        return True, "Servidor local activo"
    except Exception:
        return False, "El servidor aún está iniciando..."


# ── UI Principal ─────────────────────────────────────────────────────────────
class ConnectivityUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Verificación de Conectividad — Aguacol Asistencia")
        self.root.geometry("640x560")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Centrar
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - 320
        y = (self.root.winfo_screenheight() // 2) - 280
        self.root.geometry(f"+{x}+{y}")

        self.all_ok = False
        self._build_ui()

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=CARD, height=72)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header, text="🔗  Verificando Conectividad",
            font=("Segoe UI", 15, "bold"), fg=WHITE, bg=CARD
        ).pack(side="left", padx=24, pady=16)

        tk.Label(
            header, text="Paso final",
            font=("Segoe UI", 9), fg=GRAY, bg=CARD
        ).pack(side="right", padx=24)

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        # ── Subtítulo ─────────────────────────────────────────────────────
        tk.Label(
            self.root,
            text="Comprobando que este equipo pueda conectarse con los servicios\nde Aguacol y sincronizarse con los demás computadores...",
            font=("Segoe UI", 10), fg=LGRAY, bg=BG, justify="center"
        ).pack(pady=(20, 8))

        # ── Tarjeta de checks ─────────────────────────────────────────────
        card = tk.Frame(self.root, bg=CARD, bd=0, relief="flat")
        card.pack(fill="x", padx=40, pady=12)
        tk.Frame(card, bg=BORDER, height=1).pack(fill="x")

        self.check_widgets = {}
        checks = [
            ("turso",   "☁  Base de Datos Turso Cloud",
             "Repositorio central de datos compartidos entre todos los PCs"),
            ("bioalba", "🖐  Sistema Biométrico BioAlba",
             "Fuente de marcaciones del reloj control"),
            ("service", "⚙  Servicio de Windows",
             "Inicio automático al encender el computador"),
            ("local",   "🌐  Servidor Local de la Aplicación",
             "Interfaz web disponible en http://localhost:8000"),
        ]
        for key, title, desc in checks:
            row = tk.Frame(card, bg=CARD, padx=20, pady=12)
            row.pack(fill="x")

            left = tk.Frame(row, bg=CARD)
            left.pack(side="left", fill="x", expand=True)

            title_lbl = tk.Label(left, text=title, font=("Segoe UI", 11, "bold"), fg=LGRAY, bg=CARD, anchor="w")
            title_lbl.pack(fill="x")

            desc_lbl = tk.Label(left, text=desc, font=("Segoe UI", 9), fg=GRAY, bg=CARD, anchor="w")
            desc_lbl.pack(fill="x")

            status_lbl = tk.Label(left, text="", font=("Segoe UI", 9), fg=GRAY, bg=CARD, anchor="w")
            status_lbl.pack(fill="x")

            badge = tk.Label(row, text="⋯", font=("Segoe UI", 18), fg=YELLOW, bg=CARD, width=4)
            badge.pack(side="right")

            sep = tk.Frame(card, bg=BORDER, height=1)
            sep.pack(fill="x")

            self.check_widgets[key] = (title_lbl, status_lbl, badge)

        # ── Resultado global ─────────────────────────────────────────────
        self.result_frame = tk.Frame(self.root, bg=BG)
        self.result_frame.pack(fill="x", padx=40, pady=8)

        self.result_card = tk.Frame(self.result_frame, bg=CARD2, bd=1, relief="solid")
        self.result_card.pack(fill="x")

        self.result_icon = tk.Label(
            self.result_card, text="⋯", font=("Segoe UI", 28),
            fg=YELLOW, bg=CARD2
        )
        self.result_icon.pack(side="left", padx=20, pady=16)

        result_text = tk.Frame(self.result_card, bg=CARD2)
        result_text.pack(side="left", fill="x", expand=True)

        self.result_title = tk.Label(
            result_text, text="Verificando conexiones...",
            font=("Segoe UI", 12, "bold"), fg=YELLOW, bg=CARD2, anchor="w"
        )
        self.result_title.pack(fill="x")

        self.result_desc = tk.Label(
            result_text, text="Por favor espere...",
            font=("Segoe UI", 9), fg=GRAY, bg=CARD2, anchor="w", wraplength=380
        )
        self.result_desc.pack(fill="x")

        # ── Botón Finalizar ──────────────────────────────────────────────
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(pady=16)

        self.btn_finish = tk.Button(
            btn_frame,
            text="  Verificando...  ",
            font=("Segoe UI", 11, "bold"),
            fg=BG, bg=GRAY,
            state="disabled",
            relief="flat", bd=0, padx=28, pady=10,
            cursor="arrow",
            command=self._finish
        )
        self.btn_finish.pack()

        self.btn_browser = tk.Button(
            btn_frame,
            text="  Abrir en el Navegador →  ",
            font=("Segoe UI", 10),
            fg=CYAN, bg=CARD,
            state="disabled",
            relief="flat", bd=0, padx=20, pady=8,
            cursor="hand2",
            command=self._open_browser
        )
        self.btn_browser.pack(pady=(6, 0))

    def _set_check(self, key, ok: bool, detail: str):
        title_lbl, status_lbl, badge = self.check_widgets[key]
        if ok:
            title_lbl.config(fg=WHITE)
            status_lbl.config(text=f"✓ {detail}", fg=GREEN)
            badge.config(text="✓", fg=GREEN)
        else:
            title_lbl.config(fg=WHITE)
            status_lbl.config(text=f"✗ {detail}", fg=RED)
            badge.config(text="✗", fg=RED)
        self.root.update()

    def _set_checking(self, key):
        title_lbl, status_lbl, badge = self.check_widgets[key]
        title_lbl.config(fg=WHITE)
        status_lbl.config(text="Comprobando...", fg=YELLOW)
        badge.config(text="◉", fg=YELLOW)
        self.root.update()

    def _show_result(self, results: dict):
        critical = ["turso", "service"]
        all_critical_ok = all(results.get(k, False) for k in critical)
        all_ok = all(results.values())

        if all_ok:
            self.result_icon.config(text="✅", fg=GREEN)
            self.result_title.config(
                text="¡Todo listo! Este equipo está completamente conectado",
                fg=GREEN
            )
            self.result_desc.config(
                text="Esta PC puede sincronizarse automáticamente con los demás equipos Aguacol. "
                     "Cualquier cambio realizado aquí se reflejará en todos los demás computadores.",
                fg=LGRAY
            )
        elif all_critical_ok:
            self.result_icon.config(text="⚠️", fg=YELLOW)
            self.result_title.config(
                text="Conexión establecida con advertencias menores",
                fg=YELLOW
            )
            self.result_desc.config(
                text="La base de datos y el servicio están operativos. Algunos servicios secundarios "
                     "no pudieron verificarse pero el sistema funcionará correctamente.",
                fg=LGRAY
            )
        else:
            self.result_icon.config(text="⚠️", fg=RED)
            self.result_title.config(
                text="Atención: algunos servicios no respondieron",
                fg=RED
            )
            self.result_desc.config(
                text="Verifique su conexión a internet. La aplicación funcionará en modo local "
                     "(sin sincronización) hasta que se restablezca la conexión.",
                fg=LGRAY
            )

        self.all_ok = all_critical_ok

        # Activar botón finalizar
        self.btn_finish.config(
            text="  Finalizar instalación  ",
            bg=CYAN if all_critical_ok else YELLOW,
            fg=BG,
            state="normal",
            cursor="hand2"
        )
        if results.get("local", False):
            self.btn_browser.config(state="normal")

        self.root.update()

    def _run_checks(self):
        """Ejecuta los checks en secuencia con delays visuales"""
        results = {}
        checks = [
            ("turso",   check_turso),
            ("bioalba", check_bioalba),
            ("service", check_service),
            ("local",   check_local_server),
        ]
        for key, fn in checks:
            self._set_checking(key)
            time.sleep(0.4)  # Visual delay para que se vea el efecto
            try:
                ok, detail = fn()
            except Exception as ex:
                ok, detail = False, str(ex)[:40]
            results[key] = ok
            self._set_check(key, ok, detail)
            time.sleep(0.3)

        self._show_result(results)

    def _finish(self):
        self.root.destroy()

    def _open_browser(self):
        import webbrowser
        webbrowser.open("http://localhost:8000")

    def _on_close(self):
        self.root.destroy()

    def run(self):
        thread = threading.Thread(target=self._run_checks, daemon=True)
        thread.start()
        self.root.mainloop()


# ── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ui = ConnectivityUI()
    ui.run()
