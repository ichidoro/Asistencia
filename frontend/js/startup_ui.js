/**
 * Startup UI Manager
 * Gestiona el Splash Screen y la carga inicial del sistema
 */

const StartupUI = {
    startTime: null,
    minDisplayTime: 1500, // 1.5 segundos mínimo para estética
    isFinished: false, // [FIX] Evita múltiples disparos

    init() {
        if (this.isFinished) return; // Ya terminó, no re-iniciar
        console.log("🚀 Iniciando Startup UI Manager...");
        this.startTime = Date.now();
        this.startStatusCheck();
    },

    startStatusCheck() {
        if (this.isFinished) return;
        this.pollStatus(); // Iniciar inmediatamente el primer ciclo
    },

    async pollStatus() {
        if (this.isFinished) return;

        try {
            const response = await fetch('/api/startup/status');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            
            // Si por alguna razón llegó una respuesta tarde después de haber terminado
            if (this.isFinished) return;

            this.updateSplash(data);

            if (data.ready) {
                const elapsed = Date.now() - this.startTime;
                const remaining = Math.max(0, this.minDisplayTime - elapsed);

                if (remaining > 0) {
                    setTimeout(() => this.finishStartup(), remaining);
                } else {
                    this.finishStartup();
                }
                return; // Detener ciclo de pooling
            }

            if (data.error) {
                this.handleError(data.error);
                return; // Detener ciclo, handleError disparará reintento si es necesario
            }
            
            // Siguiente ciclo si no está listo
            setTimeout(() => this.pollStatus(), 500);

        } catch (error) {
            console.warn("⚠️ Esperando servicios...", error.message);
            const message = document.getElementById('splash-message');
            if (message && !message.innerText.includes("Error")) {
                message.innerText = "Conectando con el servidor...";
            }
            // Reintentar tras error de red
            setTimeout(() => this.pollStatus(), 1000);
        }
    },

    updateSplash(data) {
        const progressBar = document.getElementById('splash-progress');
        const message = document.getElementById('splash-message');

        if (progressBar) progressBar.style.width = `${data.progress}%`;
        if (message) message.innerText = data.message;
    },

    finishStartup() {
        if (this.isFinished) return; // Evitar ejecución múltiple
        this.isFinished = true;

        const proceed = () => {
            const splash = document.getElementById('splash-screen');
            if (splash) {
                splash.classList.add('fade-out');
                
                // 📊 Disparar evento 'app:ready' para que main.js cargue el Dashboard
                // [FIX] Usamos evento custom en lugar de llamar switchPage() directamente.
                // startup_ui.js se carga ANTES que main.js (orden defer), por lo que
                // switchPage no existe aún cuando este setTimeout dispara.
                // El evento garantiza que main.js ya se ejecutó y switchPage está definida.
                setTimeout(() => {
                    console.log("📊 Emitiendo evento app:ready para carga del Dashboard...");
                    document.dispatchEvent(new CustomEvent('app:ready'));
                }, 100);

                setTimeout(() => {
                    document.body.style.overflow = 'auto';
                    splash.style.display = 'none'; // Asegurar que no bloquea clics
                }, 800);
            }
            console.log("✅ Sistema listo, Splash Screen finalizado.");
        };

        if (typeof AuthService !== 'undefined') {
            AuthService.applySecurityToUI().then(proceed).catch(err => {
                console.error("Error aplicando seguridad en startup:", err);
                proceed();
            });
        } else {
            proceed();
        }
    },

    handleError(errorMsg) {
        const message = document.getElementById('splash-message');
        if (message) {
            message.innerHTML = `<span style="color: #ef4444; font-weight: bold;">⚠️ ERROR CRÍTICO: ${errorMsg}</span><br><small>Reintente en unos momentos...</small>`;
        }
        // Permitir reintento automático tras 5s (solo si no ha terminado ya)
        if (!this.isFinished) {
            setTimeout(() => this.startStatusCheck(), 5000);
        }
    }
};

document.addEventListener('DOMContentLoaded', () => StartupUI.init());
