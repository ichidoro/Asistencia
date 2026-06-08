/**
 * Módulo de Portería - Rondas Nocturnas (Offline-first)
 * Maneja IndexedDB local, compresión de fotos en cliente, escaneo de códigos QR,
 * sincronización resiliente con Google Drive y la base de datos de la planta (Turso).
 */

const PorteriaModule = (function () {
    // Variables de estado
    let localDB = null;
    let html5QrCode = null;
    let currentCameraIndex = 0;
    let cameraDevices = [];
    let isOnline = false;
    let checkingNetwork = false;
    let cachedUbicaciones = []; // [NEW] Cache local de ubicaciones

    // Constantes de IndexedDB
    const DB_NAME = 'AsistenciaPorteriaOfflineDB';
    const DB_VERSION = 2; // [UPDATED VERSION]

    // Inicialización del módulo
    async function init() {
        console.log("🛡️ PorteriaModule: Inicializando...");
        try {
            await initIndexedDB();
            actualizarInfoGuardia();
            await cargarCatálogoHallazgosSelect();
            await cargarUbicacionesCache(); // [NEW] Cargar ubicaciones en cache

            // Iniciar monitoreo de conexión
            await verificarConexionRed();
            setInterval(verificarConexionRed, 30000); // Cada 30 segs

            // Cargar datos locales / historial inicial
            actualizarIndicadorSync();
            
            // Escuchar cambios de página para detener/iniciar cámara
            const sidebarItems = document.querySelectorAll('.sidebar-item');
            sidebarItems.forEach(item => {
                item.addEventListener('click', function() {
                    const page = this.getAttribute('data-page');
                    if (page !== 'porteria') {
                        detenerScannerSilencioso();
                    }
                });
            });

        } catch (e) {
            console.error("❌ PorteriaModule: Error en inicialización:", e);
        }
    }

    // Helper para Notificaciones
    function showToast(msg, type = "success") {
        if (type === "error") {
            if (typeof window.showError === 'function') window.showError(msg);
            else alert("⚠️ " + msg);
        } else {
            if (typeof window.showNotification === 'function') window.showNotification(msg, type);
            else alert(msg);
        }
    }

    // --- BASE DE DATOS LOCAL (IndexedDB) ---
    function initIndexedDB() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onupgradeneeded = function (e) {
                const db = e.target.result;
                if (!db.objectStoreNames.contains('rondas')) {
                    db.createObjectStore('rondas', { keyPath: 'uuid_offline' });
                }
                if (!db.objectStoreNames.contains('catalogo_hallazgos')) {
                    db.createObjectStore('catalogo_hallazgos', { keyPath: 'id' });
                }
                if (!db.objectStoreNames.contains('ubicaciones')) {
                    db.createObjectStore('ubicaciones', { keyPath: 'id' });
                }
            };

            request.onsuccess = function (e) {
                localDB = e.target.result;
                resolve(localDB);
            };

            request.onerror = function (e) {
                reject(e.target.error);
            };
        });
    }

    // Guardar ronda en IndexedDB
    function guardarRondaLocal(ronda) {
        return new Promise((resolve, reject) => {
            if (!localDB) return reject("DB no inicializada");
            const tx = localDB.transaction('rondas', 'readwrite');
            const store = tx.objectStore('rondas');
            const req = store.put(ronda);
            req.onsuccess = () => resolve(true);
            req.onerror = () => reject(req.error);
        });
    }

    // Obtener rondas locales pendientes
    function getRondasLocales() {
        return new Promise((resolve, reject) => {
            if (!localDB) return resolve([]);
            const tx = localDB.transaction('rondas', 'readonly');
            const store = tx.objectStore('rondas');
            const req = store.getAll();
            req.onsuccess = () => resolve(req.result || []); // Fixed typo: result instead of value
            req.onerror = () => reject(req.error);
        });
    }

    // Eliminar ronda local
    function eliminarRondaLocal(uuid_offline) {
        return new Promise((resolve, reject) => {
            if (!localDB) return reject("DB no inicializada");
            const tx = localDB.transaction('rondas', 'readwrite');
            const store = tx.objectStore('rondas');
            const req = store.delete(uuid_offline);
            req.onsuccess = () => resolve(true);
            req.onerror = () => reject(req.error);
        });
    }

    // Guardar catálogo localmente
    function guardarCatalogoLocal(items) {
        return new Promise((resolve, reject) => {
            if (!localDB) return reject("DB no inicializada");
            const tx = localDB.transaction('catalogo_hallazgos', 'readwrite');
            const store = tx.objectStore('catalogo_hallazgos');
            
            // Limpiar antes de guardar
            store.clear().onsuccess = () => {
                let pending = items.length;
                if (pending === 0) resolve(true);
                items.forEach(item => {
                    const req = store.put(item);
                    req.onsuccess = () => {
                        pending--;
                        if (pending === 0) resolve(true);
                    };
                    req.onerror = () => reject(req.error);
                });
            };
        });
    }

    // Obtener catálogo local
    function getCatalogoLocal() {
        return new Promise((resolve, reject) => {
            if (!localDB) return resolve([]);
            const tx = localDB.transaction('catalogo_hallazgos', 'readonly');
            const store = tx.objectStore('catalogo_hallazgos');
            const req = store.getAll();
            req.onsuccess = () => resolve(req.result || []); // Fixed typo: result instead of value
            req.onerror = () => reject(req.error);
        });
    }

    // Guardar ubicaciones localmente
    function guardarUbicacionesLocal(items) {
        return new Promise((resolve, reject) => {
            if (!localDB) return reject("DB no inicializada");
            const tx = localDB.transaction('ubicaciones', 'readwrite');
            const store = tx.objectStore('ubicaciones');
            store.clear().onsuccess = () => {
                let pending = items.length;
                if (pending === 0) resolve(true);
                items.forEach(item => {
                    const req = store.put(item);
                    req.onsuccess = () => {
                        pending--;
                        if (pending === 0) resolve(true);
                    };
                    req.onerror = () => reject(req.error);
                });
            };
        });
    }

    // Obtener ubicaciones locales
    function getUbicacionesLocal() {
        return new Promise((resolve, reject) => {
            if (!localDB) return resolve([]);
            const tx = localDB.transaction('ubicaciones', 'readonly');
            const store = tx.objectStore('ubicaciones');
            const req = store.getAll();
            req.onsuccess = () => resolve(req.result || []);
            req.onerror = () => reject(req.error);
        });
    }

    // Cargar ubicaciones en memoria/cache
    async function cargarUbicacionesCache() {
        try {
            // Traer de API primero si estamos online
            const token = localStorage.getItem('access_token');
            if (token && navigator.onLine) { // usar navigator.onLine de apoyo
                const res = await fetch('/api/porteria/ubicaciones/', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (res.ok) {
                    cachedUbicaciones = await res.json();
                    await guardarUbicacionesLocal(cachedUbicaciones);
                    return;
                }
            }
            // Fallback local
            cachedUbicaciones = await getUbicacionesLocal();
        } catch (e) {
            console.warn("Fallo cargando ubicaciones para cache, usando IndexedDB", e);
            cachedUbicaciones = await getUbicacionesLocal();
        }
    }

    // --- MONITOREO DE CONEXIÓN ---
    async function verificarConexionRed() {
        if (checkingNetwork) return;
        checkingNetwork = true;
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                isOnline = false;
                actualizarIndicadorSync();
                checkingNetwork = false;
                return;
            }
            const res = await fetch('/api/porteria/ping/', {
                method: 'GET',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            isOnline = res.ok;
        } catch (e) {
            isOnline = false;
        }
        actualizarIndicadorSync();
        checkingNetwork = false;
    }

    async function actualizarIndicadorSync() {
        const badge = document.getElementById('porteria-sync-badge');
        const text = document.getElementById('porteria-sync-text');
        const btn = document.getElementById('porteria-btn-sync');
        const dot = document.getElementById('porteria-sync-indicator');

        if (!badge) return;

        const locales = await getRondasLocales();
        const cantLocales = locales.length;

        // Reset classes
        badge.className = "d-flex align-items-center gap-2 px-3 py-2 rounded shadow-sm";
        dot.className = "status-dot bg-white";

        if (isOnline) {
            if (cantLocales > 0) {
                badge.classList.add('bg-warning', 'text-dark');
                text.innerText = `En línea - ${cantLocales} registros pendientes`;
                btn.classList.remove('d-none');
            } else {
                badge.classList.add('bg-success', 'text-white');
                text.innerText = "En línea - Sin datos locales";
                btn.classList.add('d-none');
            }
        } else {
            if (cantLocales > 0) {
                badge.classList.add('bg-danger', 'text-white');
                text.innerText = `Desconectado - ${cantLocales} pendientes`;
                btn.classList.add('d-none');
            } else {
                badge.classList.add('bg-secondary', 'text-white');
                text.innerText = "Desconectado - Trabajando local";
                btn.classList.add('d-none');
            }
        }
    }

    // --- IDENTIFICACIÓN DEL GUARDIA ---
    function actualizarInfoGuardia() {
        const user = AuthService.getUser();
        const nombreEl = document.getElementById('porteria-guardia-nombre');
        const rolEl = document.getElementById('porteria-guardia-rol');

        if (user) {
            if (nombreEl) nombreEl.innerText = `👤 ${user.username.toUpperCase()}`;
            if (rolEl) {
                rolEl.innerText = user.rol_nombre || (user.is_superuser ? 'Super Administrador' : 'Guardia');
            }
        } else {
            if (nombreEl) nombreEl.innerText = '👤 Sesión Expirada o Inválida';
        }
    }

    // --- FLUJO DE TRABAJO DEL GUARDIA (ESCANEO) ---
    function iniciarRonda() {
        document.getElementById('porteria-auth-guardia-container').classList.add('d-none');
        document.getElementById('porteria-flujo-ronda-container').classList.remove('d-none');
        document.getElementById('porteria-scanner-container').classList.remove('d-none');
        
        // Reiniciar tarjetas del panel derecho
        document.getElementById('porteria-registro-punto-card').classList.remove('d-none');
        document.getElementById('porteria-formulario-hallazgos-card').classList.add('d-none');
        
        iniciarScanner();
    }

    function iniciarScanner() {
        const statusEl = document.getElementById('porteria-scanner-status');
        if (statusEl) statusEl.innerText = "🎥 Iniciando cámara...";
        
        if (html5QrCode) {
            html5QrCode.stop().then(() => {
                html5QrCode = null;
                iniciarScannerProceso();
            }).catch(() => {
                html5QrCode = null;
                iniciarScannerProceso();
            });
        } else {
            iniciarScannerProceso();
        }
    }

    function iniciarScannerProceso() {
        html5QrCode = new Html5Qrcode("porteria-reader");
        const config = { fps: 10, qrbox: { width: 220, height: 220 } };

        Html5Qrcode.getCameras().then(devices => {
            cameraDevices = devices;
            if (devices && devices.length > 0) {
                // Buscar cámara trasera por defecto
                let selectedIndex = 0;
                for (let i = 0; i < devices.length; i++) {
                    const label = devices[i].label.toLowerCase();
                    if (label.includes('back') || label.includes('trasera') || label.includes('entera') || label.includes('environment')) {
                        selectedIndex = i;
                        break;
                    }
                }
                currentCameraIndex = selectedIndex;
                
                html5QrCode.start(
                    devices[currentCameraIndex].id,
                    config,
                    onQrScanSuccess,
                    onQrScanError
                ).then(() => {
                    const statusEl = document.getElementById('porteria-scanner-status');
                    if (statusEl) statusEl.innerText = `🎥 Cámara activa: ${devices[currentCameraIndex].label}`;
                }).catch(err => {
                    console.error("Error al iniciar cámara:", err);
                    const statusEl = document.getElementById('porteria-scanner-status');
                    if (statusEl) statusEl.innerText = "❌ Error al activar la cámara.";
                });
            } else {
                const statusEl = document.getElementById('porteria-scanner-status');
                if (statusEl) statusEl.innerText = "❌ No se detectaron cámaras.";
            }
        }).catch(err => {
            console.error("Error enumerando cámaras:", err);
            const statusEl = document.getElementById('porteria-scanner-status');
            if (statusEl) statusEl.innerText = "❌ Error de permisos de cámara.";
        });
    }

    function cambiarCamara() {
        if (cameraDevices.length <= 1) {
            showToast("Solo hay una cámara disponible.", "error");
            return;
        }
        currentCameraIndex = (currentCameraIndex + 1) % cameraDevices.length;
        iniciarScanner();
    }

    function detenerScannerSilencioso() {
        if (html5QrCode) {
            html5QrCode.stop().then(() => {
                html5QrCode = null;
                console.log("Scanner detenido.");
            }).catch(e => {
                console.warn("Error deteniendo scanner:", e);
                html5QrCode = null;
            });
        }
    }

    function onQrScanSuccess(decodedText) {
        console.log("🔍 Escaneo exitoso:", decodedText);
        
        // Detener cámara para procesar
        if (html5QrCode) {
            html5QrCode.stop().then(() => {
                html5QrCode = null;
                procesarCodigoEscaneado(decodedText);
            }).catch(e => {
                console.error("Error al detener cámara:", e);
                procesarCodigoEscaneado(decodedText);
            });
        } else {
            procesarCodigoEscaneado(decodedText);
        }
    }

    function onQrScanError(err) {
        // Callback vacío para evitar spam en consola de errores normales de escaneo de cuadros
    }

    function procesarCodigoEscaneado(decodedText) {
        // Regex para parsear "NOMBRE CODIGO CODIGO_ALFANUMERICO"
        const match = decodedText.trim().match(/^(.+)\s+CODIGO\s+([A-Z0-9_-]+)$/i);
        if (!match) {
            Swal.fire({
                title: "Código QR Inválido",
                text: "El código escaneado no tiene el formato de Punto de Control de Portería.",
                icon: "error",
                confirmButtonText: "Escanear de Nuevo"
            }).then(() => {
                iniciarScanner();
            });
            return;
        }

        const ubiNombre = match[1].trim();
        const ubiCodigo = match[2].trim().toUpperCase();

        // Buscar en la cache de ubicaciones
        let ubi = cachedUbicaciones.find(u => u.codigo.toUpperCase() === ubiCodigo);
        if (!ubi) {
            // Fallback temporal si no existe en la cache
            ubi = { id: 0, nombre: ubiNombre, codigo: ubiCodigo };
        }

        // Cargar datos en la UI del formulario usando los nuevos IDs de ubicaciones
        document.getElementById('porteria-form-ubicacion-nombre').innerText = ubi.nombre;
        document.getElementById('porteria-form-ubicacion-codigo').innerText = `Código: ${ubi.codigo}`;
        
        // Guardar estado en memoria
        PorteriaModule._scannedUbicacionId = ubi.id;
        PorteriaModule._scannedUbicacionNombre = ubi.nombre;
        PorteriaModule._scannedUbicacionCodigo = ubi.codigo;
        PorteriaModule._fotoBlob = null;

        // Resetear inputs del formulario
        document.getElementById('porteria-form-hallazgo-select').value = "";
        document.getElementById('porteria-form-observacion').value = "";
        document.getElementById('porteria-foto-input').value = "";
        document.getElementById('porteria-preview-container').classList.add('d-none');
        document.getElementById('porteria-foto-preview').src = "";
        document.getElementById('porteria-form-detalles-opcionales').classList.add('d-none');

        // Mostrar formulario y ocultar tarjeta de espera
        document.getElementById('porteria-registro-punto-card').classList.add('d-none');
        document.getElementById('porteria-formulario-hallazgos-card').classList.remove('d-none');

        // Autoseleccionar primera opción del catálogo para forzar un change
        const select = document.getElementById('porteria-form-hallazgo-select');
        if (select && select.options.length > 0) {
            select.selectedIndex = 0;
            onSelectHallazgoCatalogo(select.value);
        }
    }

    function cancelarEscaneoPunto() {
        document.getElementById('porteria-registro-punto-card').classList.remove('d-none');
        document.getElementById('porteria-formulario-hallazgos-card').classList.add('d-none');
        iniciarScanner();
    }

    // --- FORMULARIO Y CAPTURA ---
    function onSelectHallazgoCatalogo(value) {
        const select = document.getElementById('porteria-form-hallazgo-select');
        const selectedText = select.options[select.selectedIndex]?.text || '';
        const detallesDiv = document.getElementById('porteria-form-detalles-opcionales');

        // Si es "sin novedad" o "todo normal", ocultamos
        if (selectedText.toLowerCase().includes('sin novedad') || selectedText.toLowerCase().includes('todo normal') || selectedText === '') {
            detallesDiv.classList.add('d-none');
            document.getElementById('porteria-form-observacion').value = "";
            eliminarFotoCapturada();
        } else {
            detallesDiv.classList.remove('d-none');
        }
    }

    function procesarFotoCapturada(input) {
        const file = input.files[0];
        if (!file) return;

        // Mostrar un Swal con spinner de compresión rápida
        Swal.fire({
            title: "Procesando Imagen",
            text: "Comprimiendo foto en el cliente...",
            allowOutsideClick: false,
            didOpen: () => {
                Swal.showLoading();
            }
        });

        const reader = new FileReader();
        reader.onload = function (e) {
            const img = new Image();
            img.onload = function () {
                let width = img.width;
                let height = img.height;
                const max_size = 1280;

                // Mantener aspect ratio sin exceder 1280 en el eje mayor
                if (width > height) {
                    if (width > max_size) {
                        height *= max_size / width;
                        width = max_size;
                    }
                } else {
                    if (height > max_size) {
                        width *= max_size / height;
                        height = max_size;
                    }
                }

                const canvas = document.createElement('canvas');
                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);

                // Comprimir a JPEG de calidad 0.75
                canvas.toBlob(function (blob) {
                    PorteriaModule._fotoBlob = blob;

                    const previewImg = document.getElementById('porteria-foto-preview');
                    const previewContainer = document.getElementById('porteria-preview-container');
                    
                    if (previewImg) previewImg.src = URL.createObjectURL(blob);
                    if (previewContainer) previewContainer.classList.remove('d-none');

                    Swal.close();
                    console.log(`Foto original: ${(file.size / 1024).toFixed(1)}KB. Comprimida: ${(blob.size / 1024).toFixed(1)}KB.`);
                }, 'image/jpeg', 0.75);
            };
            img.src = e.target.result;
        };
        reader.readAsDataURL(file);
    }

    function eliminarFotoCapturada() {
        PorteriaModule._fotoBlob = null;
        document.getElementById('porteria-foto-input').value = "";
        const previewContainer = document.getElementById('porteria-preview-container');
        if (previewContainer) previewContainer.classList.add('d-none');
        const previewImg = document.getElementById('porteria-foto-preview');
        if (previewImg) previewImg.src = "";
    }

    async function registrarPuntoControl() {
        const user = AuthService.getUser();
        if (!user) {
            Swal.fire("Error de Sesión", "Debe iniciar sesión nuevamente.", "error");
            return;
        }

        const ubicacionId = PorteriaModule._scannedUbicacionId;
        if (ubicacionId === undefined) {
            Swal.fire("Error", "No se detectó una ubicación válida escaneada.", "error");
            return;
        }

        const select = document.getElementById('porteria-form-hallazgo-select');
        if (!select || select.value === "") {
            Swal.fire("Campo requerido", "Por favor seleccione el estado/hallazgo del punto.", "warning");
            return;
        }

        const hallazgoId = parseInt(select.value, 10);
        const selectedText = select.options[select.selectedIndex].text;
        const esNovedad = !selectedText.toLowerCase().includes('sin novedad') && !selectedText.toLowerCase().includes('todo normal');

        const observacion = document.getElementById('porteria-form-observacion').value.trim();

        // Si es una anomalía, la foto es obligatoria
        if (esNovedad && !PorteriaModule._fotoBlob) {
            Swal.fire("Foto obligatoria", "Debe adjuntar una foto del hallazgo antes de guardar.", "warning");
            return;
        }

        // Crear registro de ronda
        const record = {
            uuid_offline: crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2) + Date.now().toString(36),
            ubicacion_id: ubicacionId,
            ubicacion_nombre: PorteriaModule._scannedUbicacionNombre,
            ubicacion_codigo: PorteriaModule._scannedUbicacionCodigo,
            fecha_hora: new Date().toISOString(),
            usuario_id: user.user_id,
            usuario_nombre: user.username,
            hallazgos: []
        };

        if (esNovedad) {
            record.hallazgos.push({
                hallazgo_id: hallazgoId,
                detalle_personalizado: observacion,
                foto_blob: PorteriaModule._fotoBlob
            });
        } else {
            record.hallazgos.push({
                hallazgo_id: hallazgoId,
                detalle_personalizado: "Todo normal",
                foto_blob: null
            });
        }

        try {
            await guardarRondaLocal(record);
            
            Swal.fire({
                title: "Punto Registrado",
                text: "El punto de control ha sido registrado localmente.",
                icon: "success",
                timer: 1500,
                showConfirmButton: false
            });

            // Volver a estado de escaneo
            document.getElementById('porteria-registro-punto-card').classList.remove('d-none');
            document.getElementById('porteria-formulario-hallazgos-card').classList.add('d-none');
            
            actualizarIndicadorSync();
            
            // Si hay conexión, intentar sincronizar automáticamente en segundo plano
            if (isOnline) {
                sincronizarLoteLocal(true);
            }

            // Reiniciar scanner
            iniciarScanner();

        } catch (e) {
            console.error(e);
            Swal.fire("Error local", "No se pudo almacenar el registro en la tablet.", "error");
        }
    }

    // --- SINCRONIZACIÓN AUTOMÁTICA O MANUAL ---
    async function sincronizarLoteLocal(silencioso = false) {
        if (!isOnline) {
            if (!silencioso) Swal.fire("Sin Conexión", "No tienes conexión activa con el servidor central.", "warning");
            return;
        }

        const locales = await getRondasLocales();
        if (locales.length === 0) {
            if (!silencioso) showToast("No hay registros pendientes de sincronizar.", "success");
            return;
        }

        if (!silencioso) {
            Swal.fire({
                title: "Sincronizando Rondas",
                text: `Subiendo ${locales.length} rondas locales...`,
                allowOutsideClick: false,
                didOpen: () => {
                    Swal.showLoading();
                }
            });
        }

        let sincronizadas = 0;
        let errores = 0;

        for (let ronda of locales) {
            try {
                const hallazgosSincronizados = [];
                
                // 1. Subir fotos a Google Drive si las hay
                for (let h of ronda.hallazgos) {
                    if (h.foto_blob) {
                        const formData = new FormData();
                        const filename = `ronda_${ronda.uuid_offline}_${h.hallazgo_id}.jpg`;
                        formData.append('file', h.foto_blob, filename);

                        const resFoto = await fetch('/api/porteria/upload-foto/', {
                            method: 'POST',
                            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` },
                            body: formData
                        });

                        if (!resFoto.ok) {
                            throw new Error("Fallo al subir la foto a Google Drive.");
                        }

                        const dataFoto = await resFoto.json();
                        hallazgosSincronizados.push({
                            hallazgo_id: h.hallazgo_id,
                            detalle_personalizado: h.detalle_personalizado,
                            google_drive_file_id: dataFoto.google_drive_file_id,
                            foto_url: dataFoto.foto_url
                        });
                    } else {
                        // Sin foto
                        hallazgosSincronizados.push({
                            hallazgo_id: h.hallazgo_id,
                            detalle_personalizado: h.detalle_personalizado,
                            google_drive_file_id: null,
                            foto_url: null
                        });
                    }
                }

                // 2. Enviar registro de ronda al backend
                const payload = {
                    rondas: [{
                        ubicacion_id: ronda.ubicacion_id,
                        fecha_hora: ronda.fecha_hora,
                        uuid_offline: ronda.uuid_offline,
                        usuario_id: ronda.usuario_id,
                        hallazgos: hallazgosSincronizados
                    }]
                };

                const resSync = await fetch('/api/porteria/rondas/sincronizar/', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });

                if (!resSync.ok) {
                    throw new Error("Error en sincronización del registro de ronda.");
                }

                const dataSync = await resSync.json();
                if (dataSync.sincronizadas > 0 || dataSync.duplicadas > 0) {
                    sincronizadas++;
                    // Eliminar de IndexedDB local
                    await eliminarRondaLocal(ronda.uuid_offline);
                } else {
                    errores++;
                }

            } catch (err) {
                console.error(`Error sincronizando ronda ${ronda.uuid_offline}:`, err);
                errores++;
            }
        }

        actualizarIndicadorSync();
        
        if (!silencioso) {
            Swal.close();
            if (errores === 0) {
                Swal.fire("Sincronización Exitosa", `Se sincronizaron ${sincronizadas} rondas correctamente.`, "success");
            } else {
                Swal.fire("Sincronización Parcial", `Sincronizadas: ${sincronizadas}. Fallidas: ${errores}.`, "warning");
            }
        }

        // Recargar historial si se está visualizando esa tab
        if (document.getElementById('historial-rondas-tab').classList.contains('active')) {
            cargarHistorialRondas();
        }
    }

    // --- CARGAR HISTORIAL DE RONDAS ---
    async function cargarHistorialRondas() {
        const tbody = document.getElementById('porteria-historial-tbody');
        if (!tbody) return;

        tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4"><div class="spinner-border spinner-border-sm text-primary" role="status"></div> Cargando historial de rondas...</td></tr>';

        try {
            let backendRondas = [];
            
            // 1. Si estamos online, traer historial del backend
            if (isOnline) {
                try {
                    const res = await fetch('/api/porteria/rondas/recientes/?limit=100', {
                        headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
                    });
                    if (res.ok) {
                        backendRondas = await res.json();
                    }
                } catch (e) {
                    console.warn("Fallo al traer historial remoto:", e);
                }
            }

            // 2. Traer registros locales pendientes
            const locales = await getRondasLocales();

            // Combinar e inyectar en la tabla
            const totalRondas = [];
            
            // Inyectar primero locales (con badge pendiente)
            locales.forEach(r => {
                totalRondas.push({
                    uuid_offline: r.uuid_offline,
                    fecha_hora: r.fecha_hora,
                    ubicacion_nombre: r.ubicacion_nombre,
                    usuario_nombre: r.usuario_nombre,
                    sincronizado: false,
                    hallazgos: r.hallazgos.map(h => ({
                        hallazgo_nombre: h.hallazgo_id ? "Anomalía #" + h.hallazgo_id : "Detalle",
                        detalle_personalizado: h.detalle_personalizado,
                        local: true
                    }))
                });
            });

            // Inyectar remotos
            backendRondas.forEach(r => {
                totalRondas.push({
                    ...r,
                    sincronizado: true
                });
            });

            // Ordenar por fecha descending
            totalRondas.sort((a,b) => new Date(b.fecha_hora) - new Date(a.fecha_hora));

            if (totalRondas.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No se han registrado rondas aún.</td></tr>';
                return;
            }

            tbody.innerHTML = totalRondas.map(r => {
                // Formatear fecha/hora
                const fecha = new Date(r.fecha_hora);
                const fechaFormat = window.formatFechaDDMMYYYY ? window.formatFechaDDMMYYYY(fecha) : fecha.toLocaleDateString();
                const horaFormat = fecha.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

                // Detalle del hallazgo
                let hallazgosText = "Sin novedades";
                let tieneFoto = false;
                let fotoUrl = "";

                if (r.hallazgos && r.hallazgos.length > 0) {
                    const h = r.hallazgos[0];
                    if (h.hallazgo_nombre) {
                        hallazgosText = `<span class="fw-bold">${h.hallazgo_nombre}</span>`;
                        if (h.detalle_personalizado) {
                            hallazgosText += `: ${h.detalle_personalizado}`;
                        }
                    } else {
                        hallazgosText = h.detalle_personalizado || "Sin detalles";
                    }
                    
                    // Verificar si tiene foto
                    if (h.foto_url) {
                        tieneFoto = true;
                        fotoUrl = h.foto_url;
                    } else if (h.local) {
                        tieneFoto = true;
                    }
                }

                // Render de celda evidencia
                let evidenciaHtml = '<span class="text-muted small">Sin foto</span>';
                if (tieneFoto) {
                    if (r.sincronizado) {
                        evidenciaHtml = `<a href="${fotoUrl}" target="_blank" class="btn btn-xs btn-outline-info py-1 px-2 fw-bold"><i class="bi bi-image me-1"></i>Ver Foto</a>`;
                    } else {
                        evidenciaHtml = `<button onclick="PorteriaModule.verFotoLocal('${r.uuid_offline}')" class="btn btn-xs btn-outline-warning py-1 px-2 fw-bold"><i class="bi bi-image me-1"></i>Ver Temp</button>`;
                    }
                }

                // Render de badge sincronizacion
                const syncHtml = r.sincronizado 
                    ? `<span class="badge bg-success py-1 px-2 rounded"><i class="bi bi-cloud-check-fill me-1"></i>Sincronizado</span>`
                    : `<span class="badge bg-warning text-dark py-1 px-2 rounded animate-pulse"><i class="bi bi-cloud-slash-fill me-1"></i>Local</span>`;

                return `
                    <tr>
                        <td class="fw-bold text-dark">${fechaFormat} <span class="text-muted small font-monospace">${horaFormat}</span></td>
                        <td><i class="bi bi-geo-alt-fill text-danger me-1"></i> ${r.ubicacion_nombre || 'Desconocido'}</td>
                        <td>${r.usuario_nombre || 'Guardia'}</td>
                        <td>${hallazgosText}</td>
                        <td>${evidenciaHtml}</td>
                        <td>${syncHtml}</td>
                    </tr>
                `;
            }).join('');

        } catch (e) {
            console.error("Error al cargar historial:", e);
            tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-danger fw-bold">Error cargando historial.</td></tr>';
        }
    }

    async function verFotoLocal(uuid_offline) {
        const locales = await getRondasLocales();
        const ronda = locales.find(r => r.uuid_offline === uuid_offline);
        if (ronda && ronda.hallazgos.length > 0 && ronda.hallazgos[0].foto_blob) {
            const url = URL.createObjectURL(ronda.hallazgos[0].foto_blob);
            Swal.fire({
                title: `Evidencia - ${ronda.area_nombre}`,
                imageUrl: url,
                imageAlt: "Evidencia de la anomalía",
                confirmButtonColor: '#3085d6',
                confirmButtonText: 'Cerrar'
            });
        } else {
            Swal.fire("Error", "No se encontró la foto local para este registro.", "error");
        }
    }

    async function initAdminTab() {
        const container = document.getElementById('catalogo-hallazgos-container');
        if (!container) return;
        
        container.innerHTML = `
            <div class="row g-4">
                <!-- Formulario de Configuración -->
                <div class="col-lg-4">
                    <div class="card border-0 shadow-sm" style="border-radius: 12px;">
                        <div class="card-header bg-white border-bottom border-light pt-3 pb-2 px-3">
                            <h6 class="fw-bold mb-0 text-primary" id="porteria-catalogo-form-title">Agregar Nuevo Hallazgo al Catálogo</h6>
                        </div>
                        <div class="card-body p-3">
                            <form id="form-catalogo-hallazgo" onsubmit="event.preventDefault(); PorteriaModule.guardarHallazgoCatalogo();">
                                <input type="hidden" id="porteria-catalogo-id" value="">
                                
                                <div class="mb-3">
                                    <label for="porteria-catalogo-nombre" class="form-label small fw-bold text-muted mb-1">Descripción de la Anomalía / Hallazgo</label>
                                    <input type="text" class="form-control form-control-sm" id="porteria-catalogo-nombre" placeholder="Ej: Fuga de agua en portería" required>
                                </div>
                                
                                <div class="mb-3 d-none" id="porteria-catalogo-activo-container">
                                    <div class="form-check form-switch">
                                        <input class="form-check-input" type="checkbox" role="switch" id="porteria-catalogo-activo" checked>
                                        <label class="form-check-label small fw-bold" for="porteria-catalogo-activo">Hallazgo Activo</label>
                                    </div>
                                </div>
                                
                                <div class="d-flex gap-2">
                                    <button type="submit" class="btn btn-sm btn-primary flex-grow-1 fw-bold">Guardar Hallazgo</button>
                                    <button type="button" class="btn btn-sm btn-light d-none" id="porteria-catalogo-btn-cancel" onclick="PorteriaModule.cancelarEdicionCatalogo()">Cancelar</button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
                
                <!-- Tabla de Hallazgos -->
                <div class="col-lg-8">
                    <div class="card border-0 shadow-sm" style="border-radius: 12px;">
                        <div class="card-header bg-white border-bottom border-light d-flex justify-content-between align-items-center pt-3 pb-2 px-3">
                            <h6 class="fw-bold mb-0 text-dark">Catálogo de Anomalías de Portería</h6>
                            <button class="btn btn-sm btn-outline-primary fw-bold px-2 py-1" onclick="PorteriaModule.cargarCatálogoHallazgos()"><i class="bi bi-arrow-clockwise"></i></button>
                        </div>
                        <div class="card-body p-3">
                            <div class="table-responsive" style="max-height: 400px; overflow-y: auto;">
                                <table class="table table-hover align-middle mb-0" style="font-size: 0.82rem;">
                                    <thead class="table-light">
                                        <tr>
                                            <th>ID</th>
                                            <th>Descripción</th>
                                            <th>Estado</th>
                                            <th class="text-end" style="width: 100px;">Acciones</th>
                                        </tr>
                                    </thead>
                                    <tbody id="porteria-catalogo-tbody">
                                        <!-- Cargado dinámicamente -->
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        await cargarCatálogoHallazgos();
    }

    // --- CATÁLOGO DE HALLAZGOS (SELECT Y CRUD) ---
    async function cargarCatálogoHallazgosSelect() {
        const select = document.getElementById('porteria-form-hallazgo-select');
        if (!select) return;

        select.innerHTML = '<option value="">-- Cargando opciones --</option>';

        let hallazgos = [];
        try {
            // Traer de API primero
            if (isOnline) {
                const res = await fetch('/api/porteria/catalogo-hallazgos/', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
                });
                if (res.ok) {
                    hallazgos = await res.json();
                    // Respaldar localmente
                    await guardarCatalogoLocal(hallazgos);
                }
            } else {
                // Offline fallback
                hallazgos = await getCatalogoLocal();
            }
        } catch (e) {
            console.warn("Fallo cargando catálogo de hallazgos para select, usando cache", e);
            hallazgos = await getCatalogoLocal();
        }

        if (hallazgos.length === 0) {
            // Valores duros de fallback por si falla la DB completamente
            hallazgos = [
                { id: 1, nombre: "Sin novedad / Todo normal" },
                { id: 2, nombre: "Puerta/Galpón abierto o sin candado" },
                { id: 3, nombre: "Luz encendida innecesariamente" }
            ];
        }

        select.innerHTML = '<option value="" disabled selected>-- Seleccione Hallazgo --</option>' + 
            hallazgos.map(h => `<option value="${h.id}">${h.nombre}</option>`).join('');
    }

    async function cargarCatálogoHallazgos() {
        const tbody = document.getElementById('porteria-catalogo-tbody');
        if (!tbody) return;

        tbody.innerHTML = '<tr><td colspan="4" class="text-center py-3"><div class="spinner-border spinner-border-sm text-primary"></div> Cargando catálogo de hallazgos...</td></tr>';

        try {
            const res = await fetch('/api/porteria/catalogo-hallazgos/?all=true', {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
            });
            if (!res.ok) throw new Error("Error de API");
            
            const list = await res.json();
            
            if (list.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center py-3 text-muted">El catálogo de hallazgos está vacío.</td></tr>';
                return;
            }

            tbody.innerHTML = list.map(c => {
                const badge = c.activo 
                    ? '<span class="badge bg-success">Activo</span>' 
                    : '<span class="badge bg-secondary">Inactivo</span>';

                return `
                    <tr>
                        <td class="fw-bold text-muted" style="width: 60px;">#${c.id}</td>
                        <td class="fw-bold text-dark">${c.nombre}</td>
                        <td>${badge}</td>
                        <td class="text-end">
                            <button class="btn btn-sm btn-outline-primary me-1" onclick="PorteriaModule.editarHallazgoCatalogo(${c.id}, '${c.nombre.replace(/'/g, "\\'")}', ${c.activo})">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger" onclick="PorteriaModule.eliminarHallazgoCatalogo(${c.id})">
                                <i class="bi bi-trash"></i>
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');

        } catch (e) {
            console.error(e);
            tbody.innerHTML = '<tr><td colspan="4" class="text-center py-3 text-danger fw-bold">Error al cargar anomalías del catálogo.</td></tr>';
        }
    }

    async function guardarHallazgoCatalogo() {
        const idInput = document.getElementById('porteria-catalogo-id');
        const nombreInput = document.getElementById('porteria-catalogo-nombre');
        const activoInput = document.getElementById('porteria-catalogo-activo');

        const id = idInput.value;
        const nombre = nombreInput.value.trim();
        const activo = activoInput.checked;

        if (!nombre) {
            showToast("Debe ingresar la descripción de la anomalía.", "error");
            return;
        }

        try {
            let res;
            if (id === "") {
                // Crear
                res = await fetch('/api/porteria/catalogo-hallazgos/', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ nombre })
                });
            } else {
                // Editar
                res = await fetch(`/api/porteria/catalogo-hallazgos/${id}/`, {
                    method: 'PUT',
                    headers: {
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ nombre, activo })
                });
            }

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Error en la operación del catálogo.");
            }

            showToast("Hallazgo guardado correctamente.", "success");
            cancelarEdicionCatalogo();
            await cargarCatálogoHallazgos();
            await cargarCatálogoHallazgosSelect();

        } catch (e) {
            console.error(e);
            Swal.fire("Error", e.message, "error");
        }
    }

    function editarHallazgoCatalogo(id, nombre, activo) {
        document.getElementById('porteria-catalogo-form-title').innerText = "Editar Hallazgo del Catálogo";
        document.getElementById('porteria-catalogo-id').value = id;
        document.getElementById('porteria-catalogo-nombre').value = nombre;
        document.getElementById('porteria-catalogo-activo').checked = activo;

        document.getElementById('porteria-catalogo-activo-container').classList.remove('d-none');
        document.getElementById('porteria-catalogo-btn-cancel').classList.remove('d-none');
    }

    function cancelarEdicionCatalogo() {
        document.getElementById('porteria-catalogo-form-title').innerText = "Agregar Nuevo Hallazgo al Catálogo";
        document.getElementById('porteria-catalogo-id').value = "";
        document.getElementById('porteria-catalogo-nombre').value = "";
        document.getElementById('porteria-catalogo-activo').checked = true;

        document.getElementById('porteria-catalogo-activo-container').classList.add('d-none');
        document.getElementById('porteria-catalogo-btn-cancel').classList.add('d-none');
    }

    async function eliminarHallazgoCatalogo(id) {
        const result = await Swal.fire({
            title: '¿Eliminar Anomalía?',
            text: "Si ya está vinculada a una ronda, se desactivará del catálogo para conservar el historial.",
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#3085d6',
            confirmButtonText: 'Sí, eliminar',
            cancelButtonText: 'Cancelar'
        });

        if (!result.isConfirmed) return;

        try {
            const res = await fetch(`/api/porteria/catalogo-hallazgos/${id}/`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
            });

            if (!res.ok) {
                throw new Error("No se pudo eliminar el hallazgo del catálogo.");
            }

            showToast("Operación completada exitosamente.", "success");
            await cargarCatálogoHallazgos();
            await cargarCatálogoHallazgosSelect();

        } catch (e) {
            console.error(e);
            Swal.fire("Error", e.message, "error");
        }
    }

    function imprimirQRCard() {
        window.print();
    }

    async function initUbicacionesTab() {
        const container = document.getElementById('porteria-ubicaciones-container');
        if (!container) return;

        container.innerHTML = `
            <div class="row g-4">
                <!-- Formulario de Configuración -->
                <div class="col-lg-4">
                    <div class="card border-0 shadow-sm" style="border-radius: 12px;">
                        <div class="card-header bg-white border-bottom border-light pt-3 pb-2 px-3">
                            <h6 class="fw-bold mb-0 text-primary" id="porteria-ubicacion-form-title">Agregar Nueva Ubicación</h6>
                        </div>
                        <div class="card-body p-3">
                            <form id="form-config-ubicacion" onsubmit="event.preventDefault(); PorteriaModule.guardarUbicacion();">
                                <input type="hidden" id="porteria-ubicacion-id" value="">
                                
                                <div class="mb-3">
                                    <label for="porteria-ubicacion-nombre" class="form-label small fw-bold text-muted mb-1">Nombre de la Ubicación</label>
                                    <input type="text" class="form-control form-control-sm" id="porteria-ubicacion-nombre" placeholder="Ej: Control Perimetral Sur" required>
                                </div>

                                <div class="mb-3">
                                    <label for="porteria-ubicacion-codigo" class="form-label small fw-bold text-muted mb-1">Código Único (para el QR)</label>
                                    <input type="text" class="form-control form-control-sm" id="porteria-ubicacion-codigo" placeholder="Ej: LOC006" required>
                                </div>
                                
                                <div class="mb-3 d-none" id="porteria-ubicacion-activo-container">
                                    <div class="form-check form-switch">
                                        <input class="form-check-input" type="checkbox" role="switch" id="porteria-ubicacion-activo" checked>
                                        <label class="form-check-label small fw-bold" for="porteria-ubicacion-activo">Ubicación Activa</label>
                                    </div>
                                </div>
                                
                                <div class="d-flex gap-2">
                                    <button type="submit" class="btn btn-sm btn-primary flex-grow-1 fw-bold">Guardar Ubicación</button>
                                    <button type="button" class="btn btn-sm btn-light d-none" id="porteria-ubicacion-btn-cancel" onclick="PorteriaModule.cancelarEdicionUbicacion()">Cancelar</button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
                
                <!-- Tabla de Ubicaciones -->
                <div class="col-lg-8">
                    <div class="card border-0 shadow-sm" style="border-radius: 12px;">
                        <div class="card-header bg-white border-bottom border-light d-flex justify-content-between align-items-center pt-3 pb-2 px-3">
                            <h6 class="fw-bold mb-0 text-dark">Ubicaciones de Control Perimetral</h6>
                            <button class="btn btn-sm btn-outline-primary fw-bold px-2 py-1" onclick="PorteriaModule.cargarUbicaciones()"><i class="bi bi-arrow-clockwise"></i></button>
                        </div>
                        <div class="card-body p-3">
                            <div class="table-responsive" style="max-height: 400px; overflow-y: auto;">
                                <table class="table table-hover align-middle mb-0" style="font-size: 0.82rem;">
                                    <thead class="table-light">
                                        <tr>
                                            <th>ID</th>
                                            <th>Código</th>
                                            <th>Nombre</th>
                                            <th class="text-center" style="width: 80px;">QR Mini</th>
                                            <th>Estado</th>
                                            <th class="text-end" style="width: 160px;">Acciones</th>
                                        </tr>
                                    </thead>
                                    <tbody id="porteria-ubicaciones-tbody">
                                        <!-- Cargado dinámicamente -->
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        await cargarUbicaciones();
    }

    async function cargarUbicaciones() {
        const tbody = document.getElementById('porteria-ubicaciones-tbody');
        if (!tbody) return;

        tbody.innerHTML = '<tr><td colspan="6" class="text-center py-3"><div class="spinner-border spinner-border-sm text-primary"></div> Cargando ubicaciones...</td></tr>';

        try {
            const res = await fetch('/api/porteria/ubicaciones/?all=true', {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
            });
            if (!res.ok) throw new Error("Error de API");
            
            const list = await res.json();
            
            if (list.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="text-center py-3 text-muted">No hay ubicaciones configuradas.</td></tr>';
                return;
            }

            tbody.innerHTML = list.map(c => {
                const badge = c.activo 
                    ? '<span class="badge bg-success">Activo</span>' 
                    : '<span class="badge bg-secondary">Inactivo</span>';

                return `
                    <tr>
                        <td class="fw-bold text-muted" style="width: 50px;">#${c.id}</td>
                        <td class="fw-bold text-secondary font-monospace" style="width: 80px;">${c.codigo}</td>
                        <td class="fw-bold text-dark">${c.nombre}</td>
                        <td class="text-center py-1">
                            <div id="qr-mini-${c.id}" class="d-inline-flex bg-white p-1 border rounded shadow-sm" style="width: 32px; height: 32px;"></div>
                        </td>
                        <td>${badge}</td>
                        <td class="text-end">
                            <button class="btn btn-xs btn-outline-primary me-1" onclick="PorteriaModule.abrirModalQRUbicacion(${c.id}, '${c.nombre.replace(/'/g, "\\'")}', '${c.codigo}')" title="Ver/Imprimir QR">
                                <i class="bi bi-qr-code"></i> QR
                            </button>
                            <button class="btn btn-xs btn-outline-info me-1" onclick="PorteriaModule.editarUbicacion(${c.id}, '${c.nombre.replace(/'/g, "\\'")}', '${c.codigo}', ${c.activo})" title="Editar">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn btn-xs btn-outline-danger" onclick="PorteriaModule.eliminarUbicacion(${c.id})" title="Eliminar">
                                <i class="bi bi-trash"></i>
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');

            // Generar los QR minis en diferido
            list.forEach(c => {
                const text = `${c.nombre.toUpperCase()} CODIGO ${c.codigo.toUpperCase()}`;
                const container = document.getElementById(`qr-mini-${c.id}`);
                if (container) {
                    new QRCode(container, {
                        text: text,
                        width: 24,
                        height: 24,
                        colorDark: "#000000",
                        colorLight: "#ffffff",
                        correctLevel: QRCode.CorrectLevel.M
                    });
                }
            });

        } catch (e) {
            console.error(e);
            tbody.innerHTML = '<tr><td colspan="6" class="text-center py-3 text-danger fw-bold">Error al cargar ubicaciones.</td></tr>';
        }
    }

    async function guardarUbicacion() {
        const idInput = document.getElementById('porteria-ubicacion-id');
        const nombreInput = document.getElementById('porteria-ubicacion-nombre');
        const codigoInput = document.getElementById('porteria-ubicacion-codigo');
        const activoInput = document.getElementById('porteria-ubicacion-activo');

        const id = idInput.value;
        const nombre = nombreInput.value.trim();
        const codigo = codigoInput.value.trim().toUpperCase();
        const activo = activoInput.checked;

        if (!nombre || !codigo) {
            showToast("Debe ingresar nombre y código para la ubicación.", "error");
            return;
        }

        try {
            let res;
            if (id === "") {
                // Crear
                res = await fetch('/api/porteria/ubicaciones/', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ nombre, codigo })
                });
            } else {
                // Editar
                res = await fetch(`/api/porteria/ubicaciones/${id}/`, {
                    method: 'PUT',
                    headers: {
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ nombre, codigo, activo })
                });
            }

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Error en la operación de ubicaciones.");
            }

            showToast("Ubicación guardada correctamente.", "success");
            cancelarEdicionUbicacion();
            await cargarUbicaciones();
            await cargarUbicacionesCache(); // Refrescar cache de rondas del escáner

        } catch (e) {
            console.error(e);
            Swal.fire("Error", e.message, "error");
        }
    }

    function editarUbicacion(id, nombre, codigo, activo) {
        document.getElementById('porteria-ubicacion-form-title').innerText = "Editar Ubicación";
        document.getElementById('porteria-ubicacion-id').value = id;
        document.getElementById('porteria-ubicacion-nombre').value = nombre;
        document.getElementById('porteria-ubicacion-codigo').value = codigo;
        document.getElementById('porteria-ubicacion-activo').checked = activo;

        document.getElementById('porteria-ubicacion-activo-container').classList.remove('d-none');
        document.getElementById('porteria-ubicacion-btn-cancel').classList.remove('d-none');
    }

    function cancelarEdicionUbicacion() {
        document.getElementById('porteria-ubicacion-form-title').innerText = "Agregar Nueva Ubicación";
        document.getElementById('porteria-ubicacion-id').value = "";
        document.getElementById('porteria-ubicacion-nombre').value = "";
        document.getElementById('porteria-ubicacion-codigo').value = "";
        document.getElementById('porteria-ubicacion-activo').checked = true;

        document.getElementById('porteria-ubicacion-activo-container').classList.add('d-none');
        document.getElementById('porteria-ubicacion-btn-cancel').classList.add('d-none');
    }

    async function eliminarUbicacion(id) {
        const result = await Swal.fire({
            title: '¿Eliminar Ubicación?',
            text: "Si ya está vinculada a una ronda, se desactivará para conservar el historial.",
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#3085d6',
            confirmButtonText: 'Sí, eliminar',
            cancelButtonText: 'Cancelar'
        });

        if (!result.isConfirmed) return;

        try {
            const res = await fetch(`/api/porteria/ubicaciones/${id}/`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
            });

            if (!res.ok) {
                throw new Error("No se pudo eliminar la ubicación.");
            }

            showToast("Operación completada exitosamente.", "success");
            await cargarUbicaciones();
            await cargarUbicacionesCache();

        } catch (e) {
            console.error(e);
            Swal.fire("Error", e.message, "error");
        }
    }

    function abrirModalQRUbicacion(id, nombre, codigo) {
        const qrText = `${nombre.toUpperCase()} CODIGO ${codigo.toUpperCase()}`;

        // Actualizar textos en el modal
        document.getElementById('modal-qr-area-nombre').innerText = nombre;
        document.getElementById('modal-qr-area-codigo').innerText = `Código: ${codigo}`;

        // Limpiar contenedores de QR
        document.getElementById('modal-qr-container').innerHTML = '';
        document.getElementById('qr-print-code').innerHTML = '';

        // Generar QR para pantalla (modal)
        new QRCode(document.getElementById('modal-qr-container'), {
            text: qrText,
            width: 130,
            height: 130,
            colorDark: "#000000",
            colorLight: "#ffffff",
            correctLevel: QRCode.CorrectLevel.H
        });

        // Generar QR para impresión
        new QRCode(document.getElementById('qr-print-code'), {
            text: qrText,
            width: 130,
            height: 130,
            colorDark: "#000000",
            colorLight: "#ffffff",
            correctLevel: QRCode.CorrectLevel.H
        });

        // Cargar textos en la plantilla de impresión
        document.getElementById('qr-print-name').innerText = nombre.toUpperCase();
        document.getElementById('qr-print-code-text').innerText = `CÓDIGO: ${codigo}`;

        // Mostrar el modal
        const modal = new bootstrap.Modal(document.getElementById('modalVerQR'));
        modal.show();
    }

    // Exponer API del módulo
    return {
        init,
        iniciarRonda,
        cambiarCamara,
        onSelectHallazgoCatalogo,
        procesarFotoCapturada,
        eliminarFotoCapturada,
        registrarPuntoControl,
        sincronizarLoteLocal,
        cargarHistorialRondas,
        verFotoLocal,
        cargarCatálogoHallazgos,
        guardarHallazgoCatalogo,
        editarHallazgoCatalogo,
        cancelarEdicionCatalogo,
        eliminarHallazgoCatalogo,
        imprimirQRCard,
        initAdminTab,
        actualizarInfoGuardia,
        initUbicacionesTab,
        cargarUbicaciones,
        guardarUbicacion,
        editarUbicacion,
        cancelarEdicionUbicacion,
        eliminarUbicacion,
        abrirModalQRUbicacion
    };
})();

// Auto-inicializar cuando el documento esté cargado
document.addEventListener('DOMContentLoaded', () => {
    PorteriaModule.init();
});
