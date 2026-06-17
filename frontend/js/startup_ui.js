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

            // 🥚 Easter Egg — Solo para ncarrasco en cada carga (slideshow)
            try {
                const u = JSON.parse(localStorage.getItem('auth_user_data') || '{}');
                if (u.username && u.username.toLowerCase() === 'ncarrasco') {
                    const totalSlides = 4;
                    let currentSlide = 1;
                    const ov = document.createElement('div');
                    ov.id = 'easter-egg-overlay';
                    ov.innerHTML = `
                        <style>
                            #easter-egg-overlay {
                                position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,0.88);
                                display:flex;align-items:center;justify-content:center;flex-direction:column;gap:16px;
                                animation:eeIn .5s ease-out;cursor:pointer;
                            }
                            @keyframes eeIn{from{opacity:0}to{opacity:1}}
                            @keyframes eeImg{0%{transform:scale(.3) rotate(-10deg);opacity:0}60%{transform:scale(1.03) rotate(1deg);opacity:1}100%{transform:scale(1) rotate(0);opacity:1}}
                            @keyframes eeGlow{0%{box-shadow:0 0 20px rgba(255,215,0,.3)}50%{box-shadow:0 0 50px rgba(255,215,0,.6),0 0 80px rgba(255,165,0,.2)}100%{box-shadow:0 0 20px rgba(255,215,0,.3)}}
                            @keyframes eeTxt{from{transform:translateY(15px);opacity:0}to{transform:translateY(0);opacity:1}}
                            @keyframes eeFade{from{opacity:0;transform:scale(.95)}to{opacity:1;transform:scale(1)}}
                            #easter-egg-overlay .ee-img{max-width:85vw;max-height:65vh;border-radius:16px;animation:eeImg .7s cubic-bezier(.34,1.56,.64,1),eeGlow 2.5s ease-in-out infinite;transition:opacity .3s}
                            #easter-egg-overlay .ee-n{font-size:1.4rem;font-weight:600;background:linear-gradient(135deg,#FFD700,#FF8C00);-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:eeTxt .5s ease-out .6s both;opacity:0}
                            #easter-egg-overlay .ee-t{color:#fff;font-size:1rem;font-weight:300;text-align:center;letter-spacing:.5px;animation:eeTxt .5s ease-out .4s both;opacity:0}
                            #easter-egg-overlay .ee-dots{display:flex;gap:8px;animation:eeTxt .4s ease-out 1s both;opacity:0}
                            #easter-egg-overlay .ee-dot{width:10px;height:10px;border-radius:50%;background:rgba(255,255,255,.3);transition:all .3s}
                            #easter-egg-overlay .ee-dot.active{background:#FFD700;transform:scale(1.3)}
                            #easter-egg-overlay .ee-h{font-size:.7rem;color:rgba(255,255,255,.35);animation:eeTxt .4s ease-out 1.2s both;opacity:0}
                        </style>
                        <img class="ee-img" src="/huevo_1.jpg" alt="🥚">
                        <div class="ee-n">¡Encontraste el Huevo de Pascua! 🥚✨</div>
                        <div class="ee-t">Un secreto escondido solo para ti</div>
                        <div class="ee-dots">
                            <span class="ee-dot active"></span>
                            <span class="ee-dot"></span>
                            <span class="ee-dot"></span>
                            <span class="ee-dot"></span>
                        </div>
                        <div class="ee-h">Toca para ver la siguiente ▸</div>
                    `;
                    document.body.appendChild(ov);

                    // 🎵 Música de fondo
                    const audio = new Audio('/cancion.mp3');
                    audio.loop = true;
                    audio.volume = 1.0;
                    audio.play().catch(() => {});

                    const img = ov.querySelector('.ee-img');
                    const dots = ov.querySelectorAll('.ee-dot');
                    const hint = ov.querySelector('.ee-h');

                    ov.addEventListener('click', () => {
                        if (currentSlide < totalSlides) {
                            currentSlide++;
                            // Crossfade
                            img.style.opacity = '0';
                            img.style.transform = 'scale(0.95)';
                            setTimeout(() => {
                                img.src = `/huevo_${currentSlide}.jpg`;
                                img.style.opacity = '1';
                                img.style.transform = 'scale(1)';
                            }, 300);
                            // Actualizar dots
                            dots.forEach((d, i) => d.classList.toggle('active', i === currentSlide - 1));
                            // Último slide
                            if (currentSlide === totalSlides) {
                                hint.textContent = 'Toca para continuar ✓';
                            }
                        } else {
                            // Fade out audio
                            const fadeAudio = setInterval(() => {
                                if (audio.volume > 0.05) { audio.volume -= 0.05; }
                                else { clearInterval(fadeAudio); audio.pause(); }
                            }, 50);
                            ov.style.transition = 'opacity 0.4s';
                            ov.style.opacity = '0';
                            setTimeout(() => ov.remove(), 400);
                        }
                    });
                }
            } catch(e) { /* silencioso */ }
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
