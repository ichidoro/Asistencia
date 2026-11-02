/**
 * Control de Visitas — Portería
 * Keyboard Wedge + Cámara OCR (MRZ) para escaneo de cédula chilena
 * Auto-detect: PDF417 (antigua) + QR (nueva) + MRZ (cámara) + Manual
 */
const VisitasModule = (() => {
    let _refreshInterval = null;
    let _wedgeBuffer = '';
    let _wedgeTimer = null;
    const WEDGE_TIMEOUT_MS = 80; // Keyboard wedge escribe ~10-30 chars en <50ms

    // ── Cámara MRZ ──
    let _cameraStream = null;
    let _ocrWorker = null;
    let _ocrProcessing = false;

    // ════════════════════════════════════════════════
    // INIT
    // ════════════════════════════════════════════════
    // ── Diseño B (02-11-2026): registro arriba; abajo, las visitas del día elegido en lista y ficha ──
    const _DIAS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
    let _fecha = _hoy(), _datos = null, _error = null, _preguntando = false;
    function _pad(n) { return (n < 10 ? '0' : '') + n; }
    function _hoy() { const d = new Date(); return d.getFullYear() + '-' + _pad(d.getMonth() + 1) + '-' + _pad(d.getDate()); }
    function _fechaDe(x) { return new Date(x + 'T12:00:00'); }
    function _sumar(x, n) { const d = _fechaDe(x); d.setDate(d.getDate() + n); return d.getFullYear() + '-' + _pad(d.getMonth() + 1) + '-' + _pad(d.getDate()); }
    function _dmy(x) { return x ? String(x).split('-').reverse().join('-') : ''; }
    function _esc(t) { return window.FichaCfg ? FichaCfg.esc(t) : String(t == null ? '' : t); }
    function _nombre(t) { return window.nombrePersona ? window.nombrePersona(t) : String(t || '').toUpperCase(); }
    function _titulo(t) { return String(t || '').toLowerCase().replace(/(^|[\s\-'])([a-záéíóúñü])/g, function (m, a, b) { return a + b.toUpperCase(); }); }
    function _rut(r) {
        const t = String(r || '').replace(/[^0-9kK]/g, '');
        if (t.length < 2) return String(r || '');
        return t.slice(0, -1).replace(/\B(?=(\d{3})+(?!\d))/g, '.') + '-' + t.slice(-1).toUpperCase();
    }
    function _min(h) { if (!h) return null; const p = String(h).split(':'); return parseInt(p[0], 10) * 60 + parseInt(p[1], 10); }
    function _dur(m) { m = Math.max(0, Math.floor(m || 0)); return Math.floor(m / 60) + 'h ' + _pad(m % 60) + 'm'; }
    function _aviso(m, t) { if (typeof showToast === 'function') showToast(m, t || 'success'); }

    const _REGISTRO = `
            <section class="ptB-reg" id="vis-registro" aria-label="Registrar visita">
                <div class="ptB-reg-top">
                    <div class="vis-scan-zone" id="vis-scan-zone">
                        <i class="bi bi-upc-scan" aria-hidden="true"></i>
                        <input type="text" class="vis-scan-input" id="vis-scan-input" placeholder="Pase la cédula por el lector"
                            aria-label="Lectura de la cédula" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false">
                    </div>
                    <div class="ptB-reg-b">
                        <button type="button" class="fcB-btn" onclick="VisitasModule.iniciarCamara()"><i class="bi bi-camera" aria-hidden="true"></i>Escanear con cámara</button>
                        <button type="button" class="fcB-btn" onclick="VisitasModule.toggleManual()"><i class="bi bi-keyboard" aria-hidden="true"></i>Ingreso manual</button>
                    </div>
                </div>
                <p class="vis-hint" id="vis-scan-hint">El lector escribe solo: al terminar se abre el formulario con el RUT para completar los datos.</p>
                <div class="vis-camera-container" id="vis-camera-container">
                    <div class="vis-ocr-status" id="vis-ocr-status"><div class="vis-ocr-spinner"></div><span id="vis-ocr-text">Leyendo la cédula…</span></div>
                    <video id="vis-camera-video" autoplay playsinline muted></video>
                    <div class="vis-camera-guide"><span class="vis-camera-guide-text">Alinee las 3 líneas de la cédula aquí</span></div>
                    <div class="vis-camera-controls">
                        <button type="button" class="vis-camera-btn capture" onclick="VisitasModule.capturarMRZ()"><i class="bi bi-camera" aria-hidden="true"></i>Capturar</button>
                        <button type="button" class="vis-camera-btn stop" onclick="VisitasModule.detenerCamara()"><i class="bi bi-x-lg" aria-hidden="true"></i>Cerrar</button>
                    </div>
                    <canvas id="vis-camera-canvas" style="display:none"></canvas>
                </div>
                <div class="vis-result-card" id="vis-result-card">
                    <div class="ptB-res-h"><div><span class="badge" id="vis-result-tipo">—</span> <span class="badge" id="vis-result-parse">—</span></div></div>
                    <div class="ptB-res-g">
                        <div><label for="vis-rut">RUT</label><input type="text" class="fcB-inp" id="vis-rut"></div>
                        <div><label for="vis-nombre">Nombre</label><input type="text" class="fcB-inp" id="vis-nombre"></div>
                        <div><label for="vis-empresa">Empresa</label><input type="text" class="fcB-inp" id="vis-empresa"></div>
                        <div><label for="vis-motivo">Motivo</label><select class="fcB-inp" id="vis-motivo">
                            <option value="">Seleccionar…</option><option value="Reunión">Reunión</option><option value="Entrega">Entrega / Despacho</option>
                            <option value="Servicio">Servicio Técnico</option><option value="Auditoría">Auditoría</option><option value="Capacitación">Capacitación</option><option value="Otro">Otro</option></select></div>
                        <div><label for="vis-area">Área destino</label><input type="text" class="fcB-inp" id="vis-area"></div>
                        <div><label for="vis-contacto">Contacto interno</label><input type="text" class="fcB-inp" id="vis-contacto"></div>
                        <div><label for="vis-patente">Patente del vehículo</label><input type="text" class="fcB-inp" id="vis-patente" placeholder="Opcional"></div>
                        <div class="ancho"><label for="vis-obs">Observaciones</label><input type="text" class="fcB-inp" id="vis-obs" placeholder="Opcional"></div>
                    </div>
                    <div class="fcB-pie"><div><button type="button" class="fcB-btn" onclick="VisitasModule.cancelarRegistro()">Cancelar</button></div>
                        <div class="fcB-pie-d"><button type="button" class="fcB-btn ok" id="vis-btn-registrar" onclick="VisitasModule.registrarVisita()"><i class="bi bi-box-arrow-in-right" aria-hidden="true"></i>Registrar ENTRADA</button></div></div>
                </div>
            </section>`;

    async function initTab() {
        const container = document.getElementById('visitas-container');
        if (!container) return;
        if (!document.getElementById('vis-registro')) {
            container.innerHTML = '<div id="vis-cab"></div>' + _REGISTRO + '<div id="vis-fcb"></div>';
            _setupWedgeListener();
            container.addEventListener('click', _alHacerClic);
            container.addEventListener('change', function (ev) { if (ev.target && ev.target.id === 'vis-fecha') _cambiarDia(ev.target.value); });
        }
        if (!_datos) _fecha = _hoy();
        _pintarCabecera();
        _pintar();
        setTimeout(() => { document.getElementById('vis-scan-input')?.focus(); }, 300);
        await cargarEstadoDia();
        if (_refreshInterval) clearInterval(_refreshInterval);
        _refreshInterval = setInterval(() => {
            const pane = document.getElementById('tab-control-visitas');
            if (!pane || !pane.classList.contains('active') || document.visibilityState !== 'visible') return;
            if (_preguntando || _fecha !== _hoy()) return;
            cargarEstadoDia();
        }, 60000);
    }

    function _pintarCabecera() {
        const c = document.getElementById('vis-cab');
        if (!c) return;
        const esHoy = _fecha === _hoy();
        c.innerHTML = '<div class="fcB"><div class="fcB-h"><div><h2>Visitas</h2><p>Arriba se registra la visita con la cédula. Abajo, las visitas del día elegido: toque una para ver sus datos y registrar su salida.</p></div>'
            + '<div class="fcB-acc"><div class="ptB-dia" role="group" aria-label="Día">'
            + '<button type="button" data-vis-dia="-1" aria-label="Día anterior"><i class="bi bi-chevron-left" aria-hidden="true"></i></button>'
            + '<span>' + _DIAS[_fechaDe(_fecha).getDay()] + '</span>'
            + '<input type="date" id="vis-fecha" value="' + _fecha + '" max="' + _hoy() + '" aria-label="Elegir día">'
            + '<button type="button" data-vis-dia="1" aria-label="Día siguiente"' + (esHoy ? ' disabled' : '') + '><i class="bi bi-chevron-right" aria-hidden="true"></i></button></div>'
            + (esHoy ? '' : '<button type="button" class="fcB-btn" data-vis-hoy>Hoy</button>') + '</div></div></div>';
    }

    function _pintar() {
        const c = document.getElementById('vis-fcb');
        if (!c || !window.FichaCfg) return;
        if (_error && !_datos) {
            c.innerHTML = '<div class="fcB"><p class="fcB-vacio">' + _esc(_error) + ' <button type="button" class="fcB-btn" data-vis-recargar>Reintentar</button></p></div>';
            return;
        }
        const esHoy = _fecha === _hoy();
        const lista = ((_datos && _datos.visitantes) || []).slice().sort(function (a, b) { return String(b.ultima_marca || '').localeCompare(String(a.ultima_marca || '')); });
        FichaCfg.montar(c, {
            clave: 'visitas',
            buscar: 'Buscar por nombre, RUT o empresa',
            items: lista,
            id: function (v) { return v.rut; },
            etiqueta: function (v) { return v.nombre ? _nombre(v.nombre) : 'Sin nombre registrado'; },
            detalle: function (v) { return [_titulo(v.empresa), 'RUT ' + _rut(v.rut)].filter(Boolean).join(' · '); },
            estado: function (v) { return v.estado === 'en_planta' ? { t: 'En planta', tono: 'si' } : { t: 'Salió', tono: '' }; },
            sub: function (v) {
                const m = v.marcas || [], ini = m.length ? String(m[0].hora).slice(0, 5) : '', fin = m.length ? String(m[m.length - 1].hora).slice(0, 5) : '';
                return v.estado === 'en_planta' ? 'desde ' + ini : ini + ' a ' + fin;
            },
            vacio: _datos ? (esHoy ? 'Todavía no hay visitas hoy. Se registran arriba, con la cédula.' : 'No hubo visitas este día.') : 'Cargando…',
            ficha: _ficha
        });
    }

    function _ficha(v, panel) {
        const F = FichaCfg, esHoy = _fecha === _hoy(), m = v.marcas || [];
        let dentro = 0, abierto = null;
        for (let i = 0; i < m.length; i++) {
            if (m[i].tipo === 'E' && m[i + 1] && m[i + 1].tipo === 'S') { dentro += _min(m[i + 1].hora) - _min(m[i].hora); i++; }
            else if (m[i].tipo === 'E' && i === m.length - 1 && esHoy) { abierto = _min(m[i].hora); const d = new Date(); dentro += Math.max(0, d.getHours() * 60 + d.getMinutes() - abierto); }
        }
        const datos = [['Empresa', _titulo(v.empresa)], ['Motivo', v.motivo], ['Área destino', _titulo(v.area_destino)], ['Contacto interno', v.persona_contacto ? _nombre(v.persona_contacto) : ''],
                       ['Patente del vehículo', String(v.patente || '').toUpperCase()], ['Cómo se registró', v.tipo_documento === 'MANUAL' ? 'Ingreso manual' : (v.tipo_documento ? 'Lectura de cédula (' + v.tipo_documento + ')' : '')]];
        let accion;
        if (esHoy) {
            const tipo = v.estado === 'en_planta' ? 'S' : 'E';
            accion = '<button type="button" class="fcB-btn ' + (tipo === 'E' ? 'ok' : 'pri') + '" data-vis-marcar="' + _esc(v.rut) + '" data-tipo="' + tipo + '">'
                + '<i class="bi bi-box-arrow-' + (tipo === 'E' ? 'in-right' : 'right') + '" aria-hidden="true"></i>Registrar ' + (tipo === 'E' ? 'ENTRADA' : 'SALIDA') + '</button>';
        } else {
            accion = '<button type="button" class="fcB-btn" data-vis-hoy>Ir a hoy para registrar</button>';
        }
        let h = F.cabeza(v.nombre ? _nombre(v.nombre) : 'Sin nombre registrado', 'RUT ' + _rut(v.rut), accion)
            + '<div class="ptB-cifras"><div><small>Estado</small><b>' + (v.estado === 'en_planta' ? 'En planta' : 'Salió') + '</b></div>'
            + '<div><small>Llegó</small><b class="num">' + (m.length ? String(m[0].hora).slice(0, 5) : '—') + '</b></div>'
            + '<div><small>Tiempo en planta' + (abierto !== null ? ' (hasta ahora)' : '') + '</small><b class="num">' + _dur(dentro) + '</b></div></div>'
            + F.seccion('Datos de la visita')
            + datos.map(function (d) { return F.campo(d[0], '<span' + (d[1] ? '' : ' class="ptB-sin"') + '>' + _esc(d[1] || 'Sin dato') + '</span>'); }).join('')
            + F.seccion('Marcas del ' + _DIAS[_fechaDe(_fecha).getDay()].toLowerCase() + ' ' + _dmy(_fecha))
            + '<div class="ptB-marcas">' + m.map(function (x) {
                return '<div class="ptB-marca"><span class="ptB-mov ' + (x.tipo === 'E' ? 'e' : 's') + '">' + (x.tipo === 'E' ? 'ENTRADA' : 'SALIDA') + '</span><b class="num">' + _esc(String(x.hora).slice(0, 5)) + '</b></div>';
            }).join('') + '</div>';
        panel.innerHTML = h;
    }

    async function _cambiarDia(x) {
        if (!x) return;
        _fecha = x > _hoy() ? _hoy() : x;
        _datos = null;
        _pintarCabecera();
        _pintar();
        await cargarEstadoDia();
    }

    function _alHacerClic(ev) {
        const b = ev.target.closest('button');
        if (!b) return;
        if (b.dataset.visDia) { _cambiarDia(_sumar(_fecha, parseInt(b.dataset.visDia, 10))); return; }
        if (b.hasAttribute('data-vis-hoy')) { _cambiarDia(_hoy()); return; }
        if (b.hasAttribute('data-vis-recargar')) { cargarEstadoDia(); return; }
        if (b.dataset.visMarcar) marcarVisitante(b.dataset.visMarcar, b);
    }

    // ════════════════════════════════════════════════
    // KEYBOARD WEDGE LISTENER
    // El wedge escribe chars muy rápido (<50ms entre chars)
    // y termina con Enter. Detectamos esa velocidad.
    // ════════════════════════════════════════════════
    function _setupWedgeListener() {
        const input = document.getElementById('vis-scan-input');
        if (!input) return;

        // El wedge simula tecleo ultra-rápido. Detectamos:
        // 1. Chars llegan en ráfaga (<80ms entre cada uno)
        // 2. Enter o pausa >80ms = fin del scan
        input.addEventListener('input', (e) => {
            const zone = document.getElementById('vis-scan-zone');
            zone?.classList.add('active');
            zone?.classList.remove('success', 'error');

            // Reset timer con cada char
            if (_wedgeTimer) clearTimeout(_wedgeTimer);

            // Si hay suficiente contenido y pasa el timeout → procesar
            _wedgeTimer = setTimeout(() => {
                const val = input.value.trim();
                if (val.length >= 7) { // RUT mínimo 7 chars
                    _procesarScan(val);
                }
            }, WEDGE_TIMEOUT_MS);
        });

        // Enter también dispara procesamiento
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (_wedgeTimer) clearTimeout(_wedgeTimer);
                const val = input.value.trim();
                if (val.length >= 7) {
                    _procesarScan(val);
                }
            }
        });

        // Mantener focus
        input.addEventListener('blur', () => {
            // Si no hay resultado visible, re-enfocar
            const resultCard = document.getElementById('vis-result-card');
            if (!resultCard?.classList.contains('show')) {
                setTimeout(() => {
                    const a = document.activeElement;
                    if (a && a !== document.body && a.matches && a.matches('input, select, textarea, button, a, [contenteditable]')) return;
                    if (input.offsetParent !== null) input.focus();
                }, 200);
            }
        });
    }

    async function _procesarScan(rawString) {
        const zone = document.getElementById('vis-scan-zone');
        const input = document.getElementById('vis-scan-input');

        // Solo PARSEAR — NO registrar. El portero debe completar datos primero.
        try {
            const res = await fetch('/api/visitas/parsear/', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ raw_scan: rawString })
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Error');
            }

            const data = await res.json();

            zone?.classList.remove('active');
            zone?.classList.add(data.parse_ok ? 'success' : 'error');

            if (data.parse_ok && typeof showToast === 'function') {
                showToast(`RUT leído: ${data.rut} (${data.tipo_documento}).`, 'info');
            }

            // SIEMPRE mostrar formulario para que el portero complete nombre/empresa
            _mostrarFormulario(data, rawString);

        } catch (e) {
            console.error(e);
            zone?.classList.remove('active');
            zone?.classList.add('error');
            _mostrarFormulario({ rut: '', nombre: '', tipo_documento: 'ERROR', parse_ok: false }, rawString);
        }
    }

    function _mostrarFormulario(data, rawScan) {
        const resultCard = document.getElementById('vis-result-card');
        const tipoEl = document.getElementById('vis-result-tipo');
        const parseEl = document.getElementById('vis-result-parse');

        document.getElementById('vis-rut').value = data.rut === 'PENDIENTE' ? '' : (data.rut || '');
        document.getElementById('vis-nombre').value = data.nombre || '';
        document.getElementById('vis-empresa').value = data.empresa || '';
        document.getElementById('vis-area').value = data.area_destino || '';
        document.getElementById('vis-contacto').value = data.persona_contacto || '';
        document.getElementById('vis-scan-input').dataset.rawScan = rawScan;

        // Motivo select
        const motivoSel = document.getElementById('vis-motivo');
        if (motivoSel && data.motivo) {
            for (let opt of motivoSel.options) {
                if (opt.value === data.motivo) { opt.selected = true; break; }
            }
        }

        // Badges de tipo
        const tipoColors = { 'PDF417': 'bg-info', 'QR': 'bg-primary', 'MANUAL': 'bg-secondary', 'AUTO': 'bg-success', 'ERROR': 'bg-danger', 'DESCONOCIDO': 'bg-warning' };
        tipoEl.className = `badge ${tipoColors[data.tipo_documento] || 'bg-secondary'}`;
        const tipoTexto = { 'PDF417': 'Cédula antigua', 'QR': 'Cédula nueva', 'MANUAL': 'Ingreso manual', 'AUTO': 'Lectura automática', 'ERROR': 'No se pudo leer', 'DESCONOCIDO': 'Formato desconocido' };
        tipoEl.textContent = tipoTexto[data.tipo_documento] || data.tipo_documento;

        // Parse status + visitante conocido
        if (data.visitante_conocido) {
            parseEl.textContent = 'Visitante conocido (' + data.visitas_previas + (data.visitas_previas === 1 ? ' visita)' : ' visitas)');
            parseEl.className = 'badge bg-primary-subtle text-primary border border-primary-subtle ms-1';
        } else {
            parseEl.textContent = data.parse_ok ? 'RUT válido · visita nueva' : (data.tipo_documento === 'MANUAL' ? 'Escriba los datos de la visita' : 'Revise el RUT');
            parseEl.className = `badge ${data.parse_ok ? 'bg-success-subtle text-success border border-success-subtle' : 'bg-warning-subtle text-warning border border-warning-subtle'} ms-1`;
        }

        resultCard?.classList.add('show');

        // Focus: si visitante conocido → botón registrar. Si nuevo → nombre.
        if (data.visitante_conocido && data.nombre) {
            document.getElementById('vis-btn-registrar')?.focus();
        } else if (!data.rut || data.rut === 'PENDIENTE') {
            document.getElementById('vis-rut')?.focus();
        } else {
            document.getElementById('vis-nombre')?.focus();
        }
    }

    // ════════════════════════════════════════════════
    // CÁMARA MRZ — OCR con Tesseract.js
    // ════════════════════════════════════════════════
    async function iniciarCamara() {
        const container = document.getElementById('vis-camera-container');
        const video = document.getElementById('vis-camera-video');
        if (!container || !video) return;

        // Cerrar cámara previa si existe
        if (_cameraStream) detenerCamara();

        try {
            // Cámara trasera con resolución alta para leer MRZ
            _cameraStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    facingMode: { ideal: 'environment' },
                    width: { ideal: 1920 },
                    height: { ideal: 1080 },
                    focusMode: { ideal: 'continuous' }
                },
                audio: false
            });
            video.srcObject = _cameraStream;
            container.classList.add('active');
            if (typeof showToast === 'function') showToast('Cámara lista. Ponga la cédula con sus 3 líneas a la vista.', 'info');
        } catch (err) {
            console.error('Error accediendo a la cámara:', err);
            if (typeof showToast === 'function') showToast('No se pudo abrir la cámara. ' + err.message, 'danger');
        }
    }

    function detenerCamara() {
        const container = document.getElementById('vis-camera-container');
        const video = document.getElementById('vis-camera-video');
        if (_cameraStream) {
            _cameraStream.getTracks().forEach(t => t.stop());
            _cameraStream = null;
        }
        if (video) video.srcObject = null;
        container?.classList.remove('active');
        _ocrProcessing = false;
        const status = document.getElementById('vis-ocr-status');
        status?.classList.remove('show');
    }

    async function capturarMRZ() {
        if (_ocrProcessing) return;
        _ocrProcessing = true;

        const video = document.getElementById('vis-camera-video');
        const canvas = document.getElementById('vis-camera-canvas');
        const status = document.getElementById('vis-ocr-status');
        const statusText = document.getElementById('vis-ocr-text');
        if (!video || !canvas) return;

        // Mostrar indicador de procesamiento
        status?.classList.add('show');
        statusText.textContent = 'Capturando imagen...';

        // Capturar frame completo del video
        const vw = video.videoWidth;
        const vh = video.videoHeight;

        // Recortar solo la zona MRZ (parte inferior de la imagen, donde está la guía)
        // La guía está en bottom:18%, height:22% → crop desde 60% al 100% del alto
        const cropTop = Math.floor(vh * 0.55);
        const cropHeight = vh - cropTop;

        canvas.width = vw;
        canvas.height = cropHeight;
        const ctx = canvas.getContext('2d');

        // Mejorar contraste para OCR: fondo claro, texto oscuro
        ctx.filter = 'contrast(1.8) grayscale(1)';
        ctx.drawImage(video, 0, cropTop, vw, cropHeight, 0, 0, vw, cropHeight);
        ctx.filter = 'none';

        const imageData = canvas.toDataURL('image/png');

        // OCR con Tesseract.js
        statusText.textContent = 'Procesando OCR...';
        try {
            if (typeof Tesseract === 'undefined') { try { await window.ensureLib('tesseract'); } catch (_) { /* se informa abajo */ } }
            if (typeof Tesseract === 'undefined') {
                throw new Error('Tesseract.js no cargó. Verifique su conexión a internet.');
            }

            const result = await Tesseract.recognize(imageData, 'eng', {
                logger: m => {
                    if (m.status === 'recognizing text') {
                        const pct = Math.round((m.progress || 0) * 100);
                        statusText.textContent = `Leyendo texto... ${pct}%`;
                    }
                }
            });

            const textoOCR = result.data.text;
            console.log('OCR raw:', textoOCR);

            // Parsear MRZ del texto reconocido
            const mrzData = _parsearMRZ(textoOCR);

            if (mrzData) {
                statusText.textContent = 'Cédula leída';
                setTimeout(() => {
                    detenerCamara();
                    // Mostrar formulario con datos extraídos
                    _mostrarFormulario({
                        rut: mrzData.rut,
                        nombre: mrzData.nombre,
                        tipo_documento: 'MRZ',
                        parse_ok: true,
                        empresa: '',
                        area_destino: '',
                        persona_contacto: ''
                    }, `MRZ:${textoOCR}`);
                    if (typeof showToast === 'function') {
                        showToast(`Listo. RUT ${mrzData.rut}, ${mrzData.nombre}.`, 'success');
                    }
                }, 600);
            } else {
                statusText.textContent = 'No se pudo leer la cédula: intente de nuevo';
                if (typeof showToast === 'function') showToast('No se pudo leer la cédula. Acomódela y vuelva a intentarlo.', 'warning');
                _ocrProcessing = false;
                setTimeout(() => status?.classList.remove('show'), 2500);
            }
        } catch (err) {
            console.error('Error OCR:', err);
            statusText.textContent = '❌ Error: ' + err.message;
            if (typeof showToast === 'function') showToast('No se pudo leer la imagen. ' + err.message, 'danger');
            _ocrProcessing = false;
            setTimeout(() => status?.classList.remove('show'), 3000);
        }
    }

    /**
     * Parsea las 3 líneas MRZ (formato ICAO TD1) de la cédula chilena.
     * 
     * Línea 1: I<CHL[DocNum][Check][Optional]   (30 chars)
     * Línea 2: [DOB 6][Check][Sex][Exp 6][Check][Nat 3][RUT en optional]  (30 chars)
     * Línea 3: [APELLIDOS]<<[NOMBRES]  (30 chars)
     * 
     * Retorna: { rut, nombre } o null si no se detecta.
     */
    function _parsearMRZ(textoOCR) {
        if (!textoOCR) return null;

        // Limpiar texto: reemplazar caracteres OCR comunes por <
        let texto = textoOCR
            .replace(/[«»<‹›]/g, '<')
            .replace(/[\r\n]+/g, '\n')
            .trim();

        // Buscar líneas que parezcan MRZ (chars alfanuméricos + <, ~30 chars)
        const lineas = texto.split('\n')
            .map(l => l.replace(/\s+/g, '').toUpperCase())
            .filter(l => l.length >= 25 && /^[A-Z0-9<]{25,}$/.test(l));

        console.log('MRZ líneas candidatas:', lineas);

        // Necesitamos al menos 2 líneas (línea 2 para RUT, línea 3 para nombre)
        // Identificar cada línea por su contenido
        let linea1 = null, linea2 = null, linea3 = null;

        for (const l of lineas) {
            if (/^I[A-Z<]?CHL/.test(l) || /^INCHL/.test(l)) {
                linea1 = l;
            } else if (/CHL[0-9]/.test(l) && /^[0-9]/.test(l)) {
                linea2 = l;
            } else if (/<</.test(l) && /^[A-Z]/.test(l)) {
                linea3 = l;
            }
        }

        // Fallback: si tenemos 3 líneas consecutivas, asignar por orden
        if ((!linea1 || !linea2 || !linea3) && lineas.length >= 3) {
            const idx = lineas.findIndex(l => /^I[A-Z<]?CHL/.test(l) || /^INCHL/.test(l));
            if (idx >= 0 && idx + 2 < lineas.length) {
                linea1 = lineas[idx];
                linea2 = lineas[idx + 1];
                linea3 = lineas[idx + 2];
            }
        }

        // Si tenemos al menos línea 2 y 3, podemos extraer datos
        let rut = null;
        let nombre = null;

        // ── Extraer RUT de línea 2 ──
        if (linea2 && linea2.length >= 28) {
            // Posiciones 16-18 = nacionalidad (CHL)
            // Posiciones 19-27 = RUT sin DV (hasta 9 dígitos)
            // Posición 28 = separador (<)
            // Posición 29 = DV
            const chlIdx = linea2.indexOf('CHL', 14);
            if (chlIdx >= 0) {
                const afterCHL = linea2.substring(chlIdx + 3);
                // Extraer dígitos del RUT + DV
                const match = afterCHL.match(/^(\d{7,9})[<](\d|[A-Z])/);
                if (match) {
                    const cuerpo = match[1];
                    let dv = match[2];
                    // Validar DV
                    const dvCalc = _calcularDV(parseInt(cuerpo));
                    if (dvCalc !== null) {
                        dv = dvCalc; // Usar DV calculado para mayor precisión
                    }
                    rut = _formatearRut(cuerpo, dv);
                }
            }
        }

        // Fallback: buscar patrón de RUT en cualquier línea
        if (!rut) {
            for (const l of lineas) {
                const m = l.match(/(\d{7,9})[<](\d|[A-Z])/);
                if (m) {
                    const cuerpo = m[1];
                    const dvCalc = _calcularDV(parseInt(cuerpo));
                    rut = _formatearRut(cuerpo, dvCalc || m[2]);
                    break;
                }
            }
        }

        // ── Extraer nombre de línea 3 ──
        if (linea3) {
            // Limpiar ruido OCR: los caracteres < de relleno a veces se leen como letras.
            // Ej: "GONZALEZ<<ANTONIOFE<<<<<<" → el "FE" es ruido de "<<"
            // Regla: fragmentos de 1-2 chars justo antes de 2+ < son ruido OCR.
            let cleanLine = linea3
                .replace(/([A-Z]{1,2})(<{2,})/g, '$2')  // "FE<<<" → "<<<" 
                .replace(/<([A-Z]{1,2})(<{2,})/g, '<<$2'); // "<FE<<" → "<<<<<"

            // Formato: APELLIDO1<APELLIDO2<<NOMBRE1<NOMBRE2
            const partes = cleanLine.split('<<').filter(Boolean);
            if (partes.length >= 2) {
                const apellidos = partes[0].replace(/</g, ' ').trim();
                const nombres = partes.slice(1).join(' ').replace(/</g, ' ').trim();
                nombre = `${nombres} ${apellidos}`;
            } else if (partes.length === 1) {
                nombre = partes[0].replace(/</g, ' ').trim();
            }
            // Limpieza final: eliminar fragmentos sueltos de 1-2 chars al final del nombre
            if (nombre) {
                nombre = nombre.replace(/\s+[A-Z]{1,2}$/i, '').trim();
            }
        }

        if (rut) {
            console.log(`MRZ parsed → RUT: ${rut}, Nombre: ${nombre || '(no detectado)'}`);
            return { rut, nombre: nombre || '' };
        }

        return null;
    }

    /**
     * Calcula el dígito verificador de un RUT chileno (módulo 11).
     */
    function _calcularDV(cuerpo) {
        if (!cuerpo || cuerpo < 1000000) return null;
        let suma = 0;
        let mul = 2;
        let rutStr = cuerpo.toString();
        for (let i = rutStr.length - 1; i >= 0; i--) {
            suma += parseInt(rutStr[i]) * mul;
            mul = mul === 7 ? 2 : mul + 1;
        }
        const resto = 11 - (suma % 11);
        if (resto === 11) return '0';
        if (resto === 10) return 'K';
        return resto.toString();
    }

    /**
     * Formatea RUT: 12345678-9 → 12.345.678-9
     */
    function _formatearRut(cuerpo, dv) {
        const c = cuerpo.toString();
        const formatted = c.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
        return `${formatted}-${dv}`;
    }

    function toggleManual() {
        detenerCamara(); // Cerrar cámara si está abierta
        const resultCard = document.getElementById('vis-result-card');
        if (resultCard?.classList.contains('show')) {
            cancelarRegistro();
        } else {
            _mostrarFormulario({ rut: '', nombre: '', tipo_documento: 'MANUAL', parse_ok: false }, '');
        }
    }

    function cancelarRegistro() {
        detenerCamara();
        document.getElementById('vis-result-card')?.classList.remove('show');
        _resetScanZone();
    }

    function _resetScanZone() {
        const input = document.getElementById('vis-scan-input');
        const zone = document.getElementById('vis-scan-zone');
        if (input) { input.value = ''; input.dataset.rawScan = ''; }
        zone?.classList.remove('active', 'success', 'error');
        setTimeout(() => input?.focus(), 200);
    }

    // ════════════════════════════════════════════════
    // REGISTRAR VISITA (desde formulario)
    // ════════════════════════════════════════════════
    async function registrarVisita() {
        const rut = document.getElementById('vis-rut')?.value.trim();
        const nombre = document.getElementById('vis-nombre')?.value.trim();
        const empresa = document.getElementById('vis-empresa')?.value.trim();
        const motivo = document.getElementById('vis-motivo')?.value;
        const area = document.getElementById('vis-area')?.value.trim();
        const contacto = document.getElementById('vis-contacto')?.value.trim();
        const patente = document.getElementById('vis-patente')?.value.trim();
        const obs = document.getElementById('vis-obs')?.value.trim();
        const rawScan = document.getElementById('vis-scan-input')?.dataset.rawScan || '';

        if (!rut) {
            if (typeof showToast === 'function') showToast('Falta el RUT de la visita.', 'warning');
            document.getElementById('vis-rut')?.focus();
            return;
        }

        try {
            const res = await fetch('/api/visitas/registrar/', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    rut, nombre, empresa, motivo,
                    area_destino: area,
                    persona_contacto: contacto,
                    patente_vehiculo: patente,
                    observaciones: obs,
                    raw_scan: rawScan
                })
            });

            if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Error'); }
            const data = await res.json();

            if (typeof showToast === 'function') {
                showToast((data.tipo_marca === 'E' ? 'ENTRADA' : 'SALIDA') + ' registrada: ' + (nombre ? _nombre(nombre) : 'RUT ' + _rut(data.rut)) + ' a las ' + String(data.hora).substring(0, 5), 'success');
            }

            cancelarRegistro();
            if (_fecha !== _hoy()) { _fecha = _hoy(); _datos = null; _pintarCabecera(); }
            await cargarEstadoDia();

        } catch (e) {
            console.error(e);
            if (typeof Swal !== 'undefined') Swal.fire('Error', e.message, 'error');
        }
    }

    // ════════════════════════════════════════════════
    // VISITAS DEL DÍA (diseño B)
    // ════════════════════════════════════════════════
    async function cargarEstadoDia() {
        try {
            const res = await fetch('/api/visitas/estado-dia/?fecha=' + _fecha, { headers: { 'Authorization': 'Bearer ' + localStorage.getItem('access_token') } });
            if (!res.ok) { let m = 'No se pudieron leer las visitas.'; try { m = (await res.json()).detail || m; } catch (_) {} throw new Error(m); }
            _datos = await res.json();
            _error = null;
        } catch (e) {
            _error = e.message;
            if (_datos) _aviso(e.message, 'danger');
        }
        _pintar();
    }

    async function marcarVisitante(rut, btn) {
        const v = ((_datos && _datos.visitantes) || []).find(function (x) { return x.rut === rut; });
        const tipo = v && v.estado === 'en_planta' ? 'SALIDA' : 'ENTRADA';
        const quien = v && v.nombre ? _nombre(v.nombre) : 'RUT ' + _rut(rut);
        if (typeof uiConfirm === 'function') {
            _preguntando = true;
            let si = false;
            try {
                const d = new Date();
                si = await uiConfirm('¿Registrar la ' + tipo + '?', { quien: quien, items: ['Visita · hora ' + _pad(d.getHours()) + ':' + _pad(d.getMinutes())], confirmText: 'Registrar ' + tipo });
            } finally { _preguntando = false; }
            if (!si) return;
        }
        const accion = async function () {
            try {
                const res = await fetch('/api/visitas/registrar/', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + localStorage.getItem('access_token'), 'Content-Type': 'application/json' },
                    body: JSON.stringify({ rut: rut })
                });
                const data = await res.json().catch(function () { return {}; });
                if (!res.ok) throw new Error(data.detail || 'No se pudo registrar.');
                _aviso((data.tipo_marca === 'E' ? 'ENTRADA' : 'SALIDA') + ' registrada: ' + quien + (data.hora ? ' a las ' + String(data.hora).substring(0, 5) : ''));
            } catch (e) { _aviso(e.message || 'No se pudo registrar.', 'danger'); }
        };
        if (btn && window.FichaCfg) await FichaCfg.trabajando(btn, accion); else await accion();
        await cargarEstadoDia();
    }

    function destroy() {
        if (_refreshInterval) { clearInterval(_refreshInterval); _refreshInterval = null; }
        detenerCamara();
    }

    return { initTab, cargarEstadoDia, registrarVisita, marcarVisitante, toggleManual, cancelarRegistro, iniciarCamara, capturarMRZ, detenerCamara, destroy };
})();
