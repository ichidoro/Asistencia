/**
 * Módulo de Portería - Rondas Nocturnas (Offline-first)
 * Maneja IndexedDB local, compresión de fotos en cliente, escaneo de códigos QR,
 * sincronización resiliente con Google Drive y la base de datos de la planta.
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
            else alert("" + msg);
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

        // Estado en la línea de la fecha (porteria.css: ptG-sync ok / pendiente / sin-red)
        const registros = cantLocales === 1 ? '1 registro' : cantLocales + ' registros';
        badge.className = 'ptG-sync ' + (isOnline ? (cantLocales > 0 ? 'pendiente' : 'ok') : 'sin-red');
        if (dot) dot.className = 'ptG-sync-dot';

        if (isOnline) {
            if (cantLocales > 0) {
                text.innerText = 'En línea · ' + registros + ' por subir';
                btn.classList.remove('d-none');
            } else {
                text.innerText = 'En línea · todo sincronizado';
                btn.classList.add('d-none');
            }
        } else {
            text.innerText = cantLocales > 0 ? 'Sin conexión · ' + registros + ' guardados en este equipo' : 'Sin conexión · se guarda en este equipo';
            btn.classList.add('d-none');
        }
    }

    // --- IDENTIFICACIÓN DEL GUARDIA ---
    function actualizarInfoGuardia() {
        const user = AuthService.getUser();
        const nombreEl = document.getElementById('porteria-guardia-nombre');
        const rolEl = document.getElementById('porteria-guardia-rol');

        if (user) {
            if (nombreEl) nombreEl.innerText = `${user.username.toUpperCase()}`;
            if (rolEl) {
                rolEl.innerText = user.rol_nombre || (user.is_superuser ? 'Super Administrador' : 'Guardia');
            }
        } else {
            if (nombreEl) nombreEl.innerText = 'Sesión Expirada o Inválida';
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
        if (statusEl) statusEl.innerText = "Iniciando cámara...";
        
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

    async function iniciarScannerProceso() {
        try { await window.ensureLib('html5qrcode'); } catch (e) { console.error(e); return; }
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
                    if (statusEl) statusEl.innerText = `Cámara activa: ${devices[currentCameraIndex].label}`;
                }).catch(err => {
                    console.error("Error al iniciar cámara:", err);
                    const statusEl = document.getElementById('porteria-scanner-status');
                    if (statusEl) statusEl.innerText = "Error al activar la cámara.";
                });
            } else {
                const statusEl = document.getElementById('porteria-scanner-status');
                if (statusEl) statusEl.innerText = "No se detectaron cámaras.";
            }
        }).catch(err => {
            console.error("Error enumerando cámaras:", err);
            const statusEl = document.getElementById('porteria-scanner-status');
            if (statusEl) statusEl.innerText = "Error de permisos de cámara.";
        });
    }

    function cambiarCamara() {
        if (cameraDevices.length <= 1) {
            showToast("Este equipo tiene una sola cámara.", "info");
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
        if (html5QrCode && html5QrCode.isScanning) {
            html5QrCode.stop().then(() => {
                html5QrCode = null;
                procesarCodigoEscaneado(decodedText);
            }).catch(e => {
                console.error("Error al detener cámara:", e);
                html5QrCode = null;
                procesarCodigoEscaneado(decodedText);
            });
        } else {
            html5QrCode = null;
            procesarCodigoEscaneado(decodedText);
        }
    }

    // Exponer hook para testing automatizado
    window.__simulateQrScan = onQrScanSuccess;

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
        document.getElementById('porteria-foto-preview').removeAttribute('src');
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
            if (!silencioso) showToast("No hay registros pendientes de enviar.", "info");
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
    // Diseño B (02-11-2026): los puntos de ronda a la izquierda (revisado hoy o no) y, a la derecha, las revisiones del
    // punto elegido con su hallazgo, su foto y si ya subió al servidor. Las revisiones guardadas en esta tableta sin
    // conexión aparecen como «En esta tableta».
    let _rondasB = [], _puntosB = [];
    function _escB(t) { return window.FichaCfg ? FichaCfg.esc(t) : String(t == null ? '' : t); }
    function _padB(n) { return (n < 10 ? '0' : '') + n; }
    function _diaB(d) { return d.getFullYear() + '-' + _padB(d.getMonth() + 1) + '-' + _padB(d.getDate()); }
    function _normalB(h) { const t = String((h && (h.hallazgo_nombre || h.detalle_personalizado)) || '').toLowerCase(); return !h || t.indexOf('sin novedad') !== -1 || t.indexOf('todo normal') !== -1; }
    function _cuandoB(fh) {
        const d = new Date(fh);
        if (isNaN(d)) return String(fh || '');
        const hoy = _diaB(new Date()), ay = new Date(); ay.setDate(ay.getDate() - 1);
        const dia = _diaB(d) === hoy ? 'Hoy' : (_diaB(d) === _diaB(ay) ? 'Ayer' : _padB(d.getDate()) + '-' + _padB(d.getMonth() + 1) + '-' + d.getFullYear());
        return dia + ' ' + _padB(d.getHours()) + ':' + _padB(d.getMinutes());
    }

    async function cargarHistorialRondas() {
        const cont = document.getElementById('rondas-fcb');
        if (!cont || !window.FichaCfg) return;
        let remotas = [], ubis = [];
        if (isOnline) {
            try {
                const res = await fetch('/api/porteria/rondas/recientes/?limit=200', { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` } });
                if (res.ok) remotas = await res.json();
            } catch (e) { console.warn('No se pudieron traer las rondas del servidor:', e); }
            try {
                const res = await fetch('/api/porteria/ubicaciones/', { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` } });
                if (res.ok) ubis = await res.json();
            } catch (e) { console.warn('No se pudieron traer los puntos de ronda:', e); }
        }
        if (!ubis.length) ubis = (cachedUbicaciones && cachedUbicaciones.length) ? cachedUbicaciones : await getUbicacionesLocal();
        const locales = await getRondasLocales();
        _rondasB = locales.map(r => ({ uuid_offline: r.uuid_offline, fecha_hora: r.fecha_hora, ubicacion_id: r.ubicacion_id, ubicacion_nombre: r.ubicacion_nombre, usuario_nombre: r.usuario_nombre, sincronizado: false,
                                       hallazgos: (r.hallazgos || []).map(x => ({ hallazgo_nombre: '', detalle_personalizado: x.detalle_personalizado, local: true, tieneFoto: !!x.foto_blob })) }))
            .concat(remotas.map(r => Object.assign({}, r, { sincronizado: true })))
            .sort((a, b) => new Date(b.fecha_hora) - new Date(a.fecha_hora));
        const hoy = _diaB(new Date());
        const puntos = ubis.filter(u => u.activo !== false).map(u => ({ id: String(u.id), nombre: u.nombre, codigo: u.codigo }));
        _rondasB.forEach(r => {
            const id = String(r.ubicacion_id || '');
            if (!puntos.some(p => p.id === id)) {
                const clave = 'n-' + (r.ubicacion_nombre || 'sin-nombre');
                if (!puntos.some(p => p.id === clave)) puntos.push({ id: clave, nombre: r.ubicacion_nombre || 'Punto sin nombre', codigo: '', fuera: true });
            }
        });
        puntos.forEach(p => {
            p.revs = _rondasB.filter(r => String(r.ubicacion_id || '') === p.id || ('n-' + (r.ubicacion_nombre || 'sin-nombre')) === p.id);
            p.hoy = p.revs.filter(r => _diaB(new Date(r.fecha_hora)) === hoy);
        });
        _puntosB = puntos;
        const revisados = puntos.filter(p => !p.fuera && p.hoy.length).length, activos = puntos.filter(p => !p.fuera).length;
        FichaCfg.montar(cont, {
            clave: 'rondas',
            descripcion: '',
            acciones: '',
            antes: '<div class="ptB-rresumen"><b>' + revisados + ' de ' + activos + '</b> puntos revisados hoy'
                + (locales.length ? ' · <span class="ojo">' + locales.length + (locales.length === 1 ? ' revisión espera' : ' revisiones esperan') + ' subir al servidor</span>' : '')
                + '<button type="button" class="fcB-btn" onclick="PorteriaModule.cargarHistorialRondas()"><i class="bi bi-arrow-clockwise" aria-hidden="true"></i>Actualizar</button></div>',
            buscar: 'Buscar punto de ronda',
            items: puntos,
            id: p => p.id,
            etiqueta: p => p.nombre,
            detalle: p => p.codigo ? 'Código ' + p.codigo : (p.fuera ? 'No está en la lista de puntos' : ''),
            estado: p => {
                if (!p.hoy.length) return { t: 'Sin revisar hoy', tono: '' };
                return p.hoy.some(r => !_normalB((r.hallazgos || [])[0])) ? { t: 'Con hallazgo', tono: 'fuera' } : { t: 'Revisado hoy', tono: 'si' };
            },
            sub: p => p.hoy.length ? _cuandoB(p.hoy[0].fecha_hora).replace('Hoy ', '') : (p.revs.length ? 'última: ' + _cuandoB(p.revs[0].fecha_hora).toLowerCase() : 'Nunca revisado'),
            vacio: 'No hay puntos de ronda. Se agregan en Configuración › Ubicaciones de ronda.',
            ficha: _fichaPuntoB
        });
    }

    function _fichaPuntoB(p, panel) {
        const F = FichaCfg;
        const hall = p.revs.filter(r => !_normalB((r.hallazgos || [])[0])).length;
        let h = F.cabeza(p.nombre, p.codigo ? 'Código ' + p.codigo : '')
            + '<div class="ptB-cifras"><div><small>Hoy</small><b>' + (p.hoy.length ? p.hoy.length + (p.hoy.length === 1 ? ' revisión' : ' revisiones') : 'Sin revisar') + '</b></div>'
            + '<div><small>Última revisión</small><b class="num">' + (p.revs.length ? _escB(_cuandoB(p.revs[0].fecha_hora)) : '—') + '</b></div>'
            + '<div><small>Con hallazgo (últimas ' + p.revs.length + ')</small><b class="num">' + hall + '</b></div></div>'
            + F.seccion('Revisiones');
        if (!p.revs.length) {
            h += '<p class="fcB-nota">Este punto todavía no tiene revisiones.</p>';
        } else {
            h += p.revs.slice(0, 30).map(r => {
                const x = (r.hallazgos || [])[0] || null, normal = _normalB(x);
                const txt = x ? (x.hallazgo_nombre ? x.hallazgo_nombre + (x.detalle_personalizado && !normal ? ': ' + x.detalle_personalizado : '') : (x.detalle_personalizado || 'Sin detalle')) : 'Sin novedad';
                let foto = '';
                if (x && x.foto_url) foto = '<a class="fcB-btn" href="' + _escB(x.foto_url) + '" target="_blank" rel="noopener"><i class="bi bi-image" aria-hidden="true"></i>Ver foto</a>';
                else if (x && x.local && x.tieneFoto) foto = '<button type="button" class="fcB-btn" onclick="PorteriaModule.verFotoLocal(\'' + _escB(r.uuid_offline) + '\')"><i class="bi bi-image" aria-hidden="true"></i>Ver foto</button>';
                return '<div class="ptB-rev"><span class="num">' + _escB(_cuandoB(r.fecha_hora)) + '</span>'
                    + '<span><b class="' + (normal ? '' : 'ojo') + '">' + _escB(txt) + '</b><small>' + _escB(String(r.usuario_nombre || 'Guardia').toUpperCase()) + (r.sincronizado ? '' : ' · En esta tableta, sin subir') + '</small></span>'
                    + '<span>' + foto + '</span></div>';
            }).join('');
        }
        panel.innerHTML = h;
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

    // Configuración › Catálogo de hallazgos con el diseño B (01-11-2026): lista a la izquierda y ficha a la derecha.
    async function initAdminTab() {
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
        const container = document.getElementById('catalogo-hallazgos-container');
        if (!container || !window.FichaCfg) return;
        const F = window.FichaCfg, canEdit = F.puede('porteria.editar');
        let list = [];
        try {
            const res = await fetch('/api/porteria/catalogo-hallazgos/?all=true', { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` } });
            if (!res.ok) throw new Error('No se pudo leer el catálogo de hallazgos.');
            list = await res.json();
        } catch (e) {
            container.innerHTML = '<p class="fcB-vacio">' + F.esc(e.message) + ' <button type="button" class="fcB-btn" onclick="PorteriaModule.cargarCatálogoHallazgos()">Reintentar</button></p>';
            return;
        }
        F.montar(container, {
            clave: 'hallazgos',
            titulo: 'Catálogo de hallazgos',
            descripcion: 'Lo que el guardia puede reportar en una ronda, por ejemplo una puerta abierta o una fuga de agua.',
            acciones: canEdit ? '<button type="button" class="fcB-btn pri" onclick="FichaCfg.nuevo(\'hallazgos\')"><i class="bi bi-plus-lg" aria-hidden="true"></i>Nuevo hallazgo</button>' : '',
            items: list.slice().sort(function (a, b) { return String(a.nombre).localeCompare(String(b.nombre), 'es'); }),
            id: function (c) { return c.id; },
            etiqueta: function (c) { return c.nombre; },
            apagado: function (c) { return !c.activo; },
            vacio: 'El catálogo está vacío. Agregue el primer hallazgo.',
            ficha: function (c, panel) {
                const nuevo = !c;
                c = c || { nombre: '', activo: true };
                panel.innerHTML = F.cabeza(nuevo ? 'Nuevo hallazgo' : c.nombre, canEdit ? 'Se cambia aquí mismo.' : 'Solo lectura.')
                    + F.campo('Descripción', F.texto('fha-nombre', c.nombre, ' placeholder="Ej: Fuga de agua en portería"'), '', 'fha-nombre')
                    + (nuevo ? '' : F.campo('En uso', F.interruptor('fha-activo', c.activo, 'El guardia lo puede elegir en una ronda')))
                    + (canEdit ? F.pie(nuevo ? '' : '<button type="button" class="fcB-btn borra" id="fha-borrar"><i class="bi bi-trash3" aria-hidden="true"></i>Eliminar hallazgo</button>',
                        '<button type="button" class="fcB-btn" id="fha-descartar">Descartar</button><button type="button" class="fcB-btn pri" id="fha-guardar">' + (nuevo ? 'Agregar hallazgo' : 'Guardar cambios') + '</button>') : '');
                if (!canEdit) { panel.querySelectorAll('input').forEach(function (e) { e.disabled = true; }); return; }
                panel.querySelector('#fha-descartar').onclick = function () { F.pintarFicha('hallazgos'); };
                const borrar = panel.querySelector('#fha-borrar');
                if (borrar) borrar.onclick = function () { eliminarHallazgoCatalogo(c.id); };
                panel.querySelector('#fha-guardar').onclick = function (ev) {
                    const nombre = panel.querySelector('#fha-nombre').value.trim();
                    if (!nombre) { showToast('Falta describir el hallazgo.', 'warning'); return; }
                    const activo = nuevo ? true : panel.querySelector('#fha-activo').checked;
                    F.trabajando(ev.currentTarget, async function () {
                        const res = await fetch('/api/porteria/catalogo-hallazgos/' + (nuevo ? '' : c.id + '/'), {
                            method: nuevo ? 'POST' : 'PUT',
                            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}`, 'Content-Type': 'application/json' },
                            body: JSON.stringify(nuevo ? { nombre: nombre } : { nombre: nombre, activo: activo })
                        });
                        const d = await res.json().catch(function () { return {}; });
                        if (!res.ok) { showToast(d.detail || 'No se pudo guardar el hallazgo.', 'danger'); return; }
                        showToast('Listo. Hallazgo guardado.', 'success');
                        if (d && d.id) F.recordar('hallazgos', d.id);
                        await cargarCatálogoHallazgos();
                        await cargarCatálogoHallazgosSelect();
                    });
                };
            }
        });
    }

    // La ficha guarda sola; estas tres quedan por compatibilidad con PorteriaModule
    async function guardarHallazgoCatalogo() { await cargarCatálogoHallazgos(); }
    function editarHallazgoCatalogo(id) { if (window.FichaCfg) FichaCfg.elegir('hallazgos', String(id)); }
    function cancelarEdicionCatalogo() { if (window.FichaCfg) FichaCfg.pintarFicha('hallazgos'); }

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

            showToast("Listo. Cambios guardados.", "success");
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

    // Configuración › Ubicaciones de ronda con el diseño B (01-11-2026): lista a la izquierda y ficha con su QR a la derecha.
    async function initUbicacionesTab() {
        await cargarUbicaciones();
    }

    async function cargarUbicaciones() {
        const container = document.getElementById('porteria-ubicaciones-container');
        if (!container || !window.FichaCfg) return;
        const F = window.FichaCfg, canEdit = F.puede('porteria.editar');
        let list = [];
        try {
            const res = await fetch('/api/porteria/ubicaciones/?all=true', { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` } });
            if (!res.ok) throw new Error('No se pudieron leer las ubicaciones.');
            list = await res.json();
        } catch (e) {
            container.innerHTML = '<p class="fcB-vacio">' + F.esc(e.message) + ' <button type="button" class="fcB-btn" onclick="PorteriaModule.cargarUbicaciones()">Reintentar</button></p>';
            return;
        }
        F.montar(container, {
            clave: 'ubicaciones',
            titulo: 'Ubicaciones de ronda',
            descripcion: 'Puntos que el guardia recorre en la ronda. Cada uno tiene un código QR que se imprime y se pega en el lugar.',
            acciones: canEdit ? '<button type="button" class="fcB-btn pri" onclick="FichaCfg.nuevo(\'ubicaciones\')"><i class="bi bi-plus-lg" aria-hidden="true"></i>Nueva ubicación</button>' : '',
            items: list.slice().sort(function (a, b) { return String(a.codigo).localeCompare(String(b.codigo), 'es'); }),
            id: function (c) { return c.id; },
            etiqueta: function (c) { return c.nombre; },
            sub: function (c) { return c.codigo; },
            apagado: function (c) { return !c.activo; },
            vacio: 'No hay ubicaciones. Agregue la primera.',
            ficha: function (c, panel) {
                const nuevo = !c;
                c = c || { nombre: '', codigo: '', activo: true };
                panel.innerHTML = F.cabeza(nuevo ? 'Nueva ubicación' : c.nombre, canEdit ? 'Se cambia aquí mismo.' : 'Solo lectura.')
                    + F.campo('Nombre', F.texto('fub-nombre', c.nombre, ' placeholder="Ej: Bodega de químicos"'), '', 'fub-nombre')
                    + F.campo('Código', F.texto('fub-codigo', c.codigo, ' placeholder="Ej: LOC013" style="max-width:180px;text-transform:uppercase"'), 'Va impreso en el QR.', 'fub-codigo')
                    + (nuevo ? '' : F.campo('En uso', F.interruptor('fub-activo', c.activo, 'Se pide en la ronda')))
                    + (nuevo ? '' : F.campo('Código QR', '<div id="fub-qr" style="width:96px;height:96px;padding:6px;background:#fff;border:1px solid #e6e9f1;border-radius:10px"></div>'
                        + '<button type="button" class="fcB-btn" id="fub-imprimir"><i class="bi bi-printer" aria-hidden="true"></i>Ver e imprimir</button>'))
                    + (canEdit ? F.pie(nuevo ? '' : '<button type="button" class="fcB-btn borra" id="fub-borrar"><i class="bi bi-trash3" aria-hidden="true"></i>Eliminar ubicación</button>',
                        '<button type="button" class="fcB-btn" id="fub-descartar">Descartar</button><button type="button" class="fcB-btn pri" id="fub-guardar">' + (nuevo ? 'Agregar ubicación' : 'Guardar cambios') + '</button>') : '');
                if (!nuevo) {
                    const qr = panel.querySelector('#fub-qr');
                    if (qr && typeof QRCode !== 'undefined') {
                        const texto = (String(c.nombre).toUpperCase() + ' CODIGO ' + String(c.codigo).toUpperCase()).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ñ/gi, 'n');
                        new QRCode(qr, { text: texto, width: 84, height: 84, colorDark: '#000000', colorLight: '#ffffff', correctLevel: QRCode.CorrectLevel.M });
                    }
                    panel.querySelector('#fub-imprimir').onclick = function () { abrirModalQRUbicacion(c.id, c.nombre, c.codigo); };
                }
                if (!canEdit) { panel.querySelectorAll('input').forEach(function (e) { e.disabled = true; }); return; }
                panel.querySelector('#fub-descartar').onclick = function () { F.pintarFicha('ubicaciones'); };
                const borrar = panel.querySelector('#fub-borrar');
                if (borrar) borrar.onclick = function () { eliminarUbicacion(c.id); };
                panel.querySelector('#fub-guardar').onclick = function (ev) {
                    const nombre = panel.querySelector('#fub-nombre').value.trim(), codigo = panel.querySelector('#fub-codigo').value.trim().toUpperCase();
                    if (!nombre || !codigo) { showToast('Faltan datos. Escriba el nombre y el código de la ubicación.', 'warning'); return; }
                    const activo = nuevo ? true : panel.querySelector('#fub-activo').checked;
                    F.trabajando(ev.currentTarget, async function () {
                        const res = await fetch('/api/porteria/ubicaciones/' + (nuevo ? '' : c.id + '/'), {
                            method: nuevo ? 'POST' : 'PUT',
                            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}`, 'Content-Type': 'application/json' },
                            body: JSON.stringify(nuevo ? { nombre: nombre, codigo: codigo } : { nombre: nombre, codigo: codigo, activo: activo })
                        });
                        const d = await res.json().catch(function () { return {}; });
                        if (!res.ok) { showToast(d.detail || 'No se pudo guardar la ubicación.', 'danger'); return; }
                        showToast('Listo. Ubicación guardada.', 'success');
                        if (d && d.id) F.recordar('ubicaciones', d.id);
                        await cargarUbicaciones();
                        await cargarUbicacionesCache();   // el escáner de rondas usa esta lista
                    });
                };
            }
        });
    }

    // La ficha guarda sola; estas tres quedan por compatibilidad con PorteriaModule
    async function guardarUbicacion() { await cargarUbicaciones(); }
    function editarUbicacion(id) { if (window.FichaCfg) FichaCfg.elegir('ubicaciones', String(id)); }
    function cancelarEdicionUbicacion() { if (window.FichaCfg) FichaCfg.pintarFicha('ubicaciones'); }

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

            showToast("Listo. Cambios guardados.", "success");
            await cargarUbicaciones();
            await cargarUbicacionesCache();

        } catch (e) {
            console.error(e);
            Swal.fire("Error", e.message, "error");
        }
    }

    function abrirModalQRUbicacion(id, nombre, codigo) {
        const qrText = `${nombre.toUpperCase()} CODIGO ${codigo.toUpperCase()}`;
        const cleanText = qrText.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ñ/gi, "n");

        // Actualizar textos en el modal
        document.getElementById('modal-qr-ubicacion-nombre').innerText = nombre;
        document.getElementById('modal-qr-ubicacion-codigo').innerText = `Código: ${codigo}`;

        // Limpiar contenedores de QR
        document.getElementById('modal-qr-container').innerHTML = '';
        document.getElementById('qr-print-code').innerHTML = '';

        // Generar QR para pantalla (modal)
        new QRCode(document.getElementById('modal-qr-container'), {
            text: cleanText,
            width: 130,
            height: 130,
            colorDark: "#000000",
            colorLight: "#ffffff",
            correctLevel: QRCode.CorrectLevel.H
        });

        // Generar QR para impresión
        new QRCode(document.getElementById('qr-print-code'), {
            text: cleanText,
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
