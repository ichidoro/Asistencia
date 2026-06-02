// ==========================================
// Módulo de Autenticación y Seguridad Frontend
// Actúa como Middleware global para la UI
// ==========================================

const AuthService = {
    TOKEN_KEY: 'access_token',
    USER_KEY: 'auth_user_data',

    login: async function (username, password) {
        try {
            const formData = new URLSearchParams();
            formData.append('username', username);
            formData.append('password', password);

            const response = await fetch('/api/auth/login/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Error de autenticación');
            }

            const data = await response.json();

            // Almacenar token y datos del usuario
            localStorage.setItem(this.TOKEN_KEY, data.access_token);
            localStorage.setItem(this.USER_KEY, JSON.stringify({
                user_id: data.user_id,
                username: data.username,
                rol_id: data.rol_id,
                alcance_global: data.alcance_global,
                is_superuser: data.is_superuser || false,
                areas: data.areas
            }));

            return true;
        } catch (error) {
            console.error('Login error:', error);
            throw error;
        }
    },

    logout: function (razon = "") {
        localStorage.removeItem(this.TOKEN_KEY);
        localStorage.removeItem(this.USER_KEY);
        localStorage.removeItem('user_permissions'); // Pre-filtro UI cache

        if (razon) {
            alert(razon);
        }
        window.location.href = '/login.html';
    },

    getToken: function () {
        return localStorage.getItem(this.TOKEN_KEY);
    },

    getUser: function () {
        const data = localStorage.getItem(this.USER_KEY);
        return data ? JSON.parse(data) : null;
    },

    hasPermission: function (permisoReq) {
        const user = this.getUser();
        if (!user) return false;
        if (user.is_superuser) return true;

        const permisosStr = localStorage.getItem('user_permissions');
        if (!permisosStr) return false;

        try {
            const permisosDB = JSON.parse(permisosStr);
            return permisosDB.includes(permisoReq);
        } catch (e) {
            return false;
        }
    },

    initInterceptor: function () {
        // Interceptar window.fetch globalmente para inyectar Token y escuchar 401
        const originalFetch = window.fetch;

        window.fetch = async function () {
            let [resource, config] = arguments;
            if (!config) config = {};
            if (!config.headers) config.headers = {};

            // Normalize URL (Soporte para string, objeto URL o Request)
            const url = (resource instanceof URL) ? resource.href : (typeof resource === 'string' ? resource : resource.url || String(resource));

            // Si es la API interna pero no es login
            if (url.includes('/api/') && !url.includes('/api/auth/login')) {
                const token = AuthService.getToken();
                if (token) {
                    config.headers['Authorization'] = `Bearer ${token}`;
                } else {
                    // Si no hay token e intenta ir a API, redirigir a Login previniendo la carga fallida
                    AuthService.logout();
                }
            }

            try {
                const response = await originalFetch(resource, config);

                // Zero-Trust: Sesión Expirada Detection con 1 retry resiliente.
                // Bajo carga pesada del servidor (batch sync), un 401 transitorio puede ocurrir.
                if (response.status === 401 && !url.includes('/api/auth/login/')) {
                    // Retry silencioso: esperar 300ms y reintentar 1 vez
                    await new Promise(r => setTimeout(r, 300));
                    const retryResponse = await originalFetch(resource, config);
                    if (retryResponse.status === 401) {
                        console.warn("🔐 Muro de Seguridad: " + url + " devolvió 401 (confirmado). Deslogueando.");
                        AuthService.logout("Su sesión ha expirado o su cuenta ha sido desactivada.");
                    }
                    return retryResponse;
                }

                return response;
            } catch (error) {
                throw error;
            }
        };
    },

    requireAuthGuard: function () {
        // Si no está logueado y no está en login.html (endswith permite manejar /login.html o /static/login.html)
        const path = window.location.pathname;
        const isLogin = path.endsWith('/login.html') || path === '/login';

        if (!this.getToken() && !isLogin) {
            window.location.href = '/login.html';
        }
    },

    applySecurityToUI: function () {
        return new Promise((resolve) => {
            // [FIX] Si ya se aplicó en esta carga de página, no repetir para evitar parpadeo (flashing)
            if (this._ui_secured || document.body.getAttribute('data-ui-secured') === 'true') {
                console.log("🛡️ Seguridad UI ya aplicada y blindada. Omitiendo.");
                resolve();
                return;
            }

            const user = this.getUser();
            if (!user) {
                resolve();
                return;
            }

            // 1. Cargar datos en el Header (inmediato, no requiere permisos)
            const usernameEl = document.getElementById('header-username');
            const roleEl = document.getElementById('header-role');

            if (usernameEl) {
                usernameEl.innerHTML = `<i class="fa-solid fa-user-circle me-1"></i> ${user.username} <i class="bi bi-caret-down-fill ms-1 small"></i>`;
            }
            if (roleEl) {
                let roleBadge = user.alcance_global ? '<span class="badge bg-primary">Alcance Global</span>' : '<span class="badge bg-secondary">Zonal</span>';
                roleEl.innerHTML = `Rol: ${roleBadge}`;
            }

            // 2. Refresco silencioso de permisos PRIMERO → luego aplicar blindaje
            // [HILO ROJO] El fetch es asíncrono. El blindaje DEBE ocurrir dentro del .then()
            // para que los permisos actualizados ya estén en localStorage antes de ocultar elementos.
            const applyBlindaje = () => {
                console.log("🛡️ Aplicando Blindaje de Seguridad a la UI...");

                // Blindaje dinámico: oculta TODOS los elementos con data-permiso que no se tengan
                document.querySelectorAll('[data-permiso]').forEach(el => {
                    const permisoReq = el.getAttribute('data-permiso');
                    if (!AuthService.hasPermission(permisoReq)) {
                        el.classList.add('d-none');
                        el.style.display = 'none';
                    }
                });

                AuthService._ui_secured = true;
                document.body.setAttribute('data-ui-secured', 'true');
                resolve();
            };

            if (this.getToken()) {
                fetch('/api/auth/permissions/', {
                    headers: { 'Authorization': `Bearer ${this.getToken()}` }
                }).then(r => r.json()).then(data => {
                    if (data && data.permisos) {
                        localStorage.setItem('user_permissions', JSON.stringify(data.permisos));
                    }
                    if (data && typeof data.is_superuser !== 'undefined') {
                        const stored = JSON.parse(localStorage.getItem(this.USER_KEY) || '{}');
                        stored.is_superuser = data.is_superuser;
                        localStorage.setItem(this.USER_KEY, JSON.stringify(stored));
                    }
                    applyBlindaje();
                }).catch(e => {
                    console.warn('Error refreshing permissions, applying blindaje with cached data', e);
                    applyBlindaje(); // ← blindaje con datos cacheados si falla el fetch
                });
            } else {
                applyBlindaje();
            }
        });
    }
};

// Auto-Iniciar Security Interceptor cuando se cargue el archivo
AuthService.initInterceptor();
