/**
 * Control de Visitas — Portería
 * Keyboard Wedge Integration para escaneo de cédula chilena
 * Auto-detect: PDF417 (antigua) + QR (nueva) + Manual
 */
const VisitasModule = (() => {
    let _fechaActual = new Date().toISOString().slice(0, 10);
    let _refreshInterval = null;
    let _wedgeBuffer = '';
    let _wedgeTimer = null;
    const WEDGE_TIMEOUT_MS = 80; // Keyboard wedge escribe ~10-30 chars en <50ms

    // ════════════════════════════════════════════════
    // INIT
    // ════════════════════════════════════════════════
    async function initTab() {
        const container = document.getElementById('visitas-container');
        if (!container) return;

        const hoy = new Date();
        const diasSemana = ['Domingo','Lunes','Martes','Miércoles','Jueves','Viernes','Sábado'];
        const meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
        const fechaDisplay = `${diasSemana[hoy.getDay()]} ${hoy.getDate()} ${meses[hoy.getMonth()]} ${hoy.getFullYear()}`;

        container.innerHTML = `
            <style>
                .vis-kpi { position:relative; overflow:hidden; border-radius:12px; padding:1.25rem 1.5rem; color:#fff; transition:transform 0.3s; }
                .vis-kpi:hover { transform:translateY(-2px); }
                .vis-kpi .kpi-icon { position:absolute; right:-10px; top:-10px; font-size:5rem; opacity:0.08; }
                .vis-kpi .kpi-number { font-size:2.25rem; font-weight:800; line-height:1; }
                .vis-kpi .kpi-label { font-size:0.7rem; font-weight:600; text-transform:uppercase; letter-spacing:0.08em; opacity:0.9; }
                .vis-kpi .kpi-sub { font-size:0.8rem; font-weight:500; opacity:0.8; margin-top:2px; }
                .vis-scan-zone { background:#fff; border:2px dashed #c7d2fe; border-radius:16px; padding:1.5rem; text-align:center; transition:all 0.3s; position:relative; }
                .vis-scan-zone.active { border-color:#6366f1; background:#eef2ff; box-shadow:0 0 0 4px rgba(99,102,241,0.1); }
                .vis-scan-zone.success { border-color:#10b981; background:#d1fae5; }
                .vis-scan-zone.error { border-color:#f43f5e; background:#ffe4e6; }
                .vis-scan-input { width:100%; font-size:1rem; padding:12px 16px; border:1px solid #e2e8f0; border-radius:10px; text-align:center; font-family:'Inter',sans-serif; font-weight:500; transition:all 0.2s; caret-color:#6366f1; }
                .vis-scan-input:focus { outline:none; border-color:#6366f1; box-shadow:0 0 0 3px rgba(99,102,241,0.15); }
                .vis-scan-input::placeholder { color:#94a3b8; font-weight:400; }
                .vis-result-card { background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:1.2rem; margin-top:1rem; display:none; }
                .vis-result-card.show { display:block; animation: visSlideIn 0.3s ease-out; }
                @keyframes visSlideIn { from { opacity:0; transform:translateY(-8px); } to { opacity:1; transform:translateY(0); } }
                .vis-visitor-row { display:flex; align-items:center; padding:0.8rem 1rem; border-left:4px solid transparent; transition:background 0.15s; }
                .vis-visitor-row:hover { background:#f8fafc; }
                .vis-visitor-row:not(:last-child) { border-bottom:1px solid #f1f5f9; }
                .vis-visitor-row.en_planta { border-left-color:var(--success-color); }
                .vis-visitor-row.fuera { border-left-color:#94a3b8; }
                .vis-avatar { width:38px; height:38px; border-radius:50%; background:#eef2ff; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:0.7rem; color:#4338ca; flex-shrink:0; border:1px solid #c7d2fe; }
                .vis-section-header { background:rgba(248,250,252,0.5); padding:0.9rem 1.2rem; border-bottom:1px solid #e2e8f0; display:flex; justify-content:space-between; align-items:center; }
                .vis-section-title { font-size:1rem; font-weight:600; color:#1e293b; display:flex; align-items:center; gap:8px; }
                .vis-status-pill { display:inline-flex; align-items:center; gap:4px; padding:3px 10px; border-radius:999px; font-size:0.68rem; font-weight:600; }
                .vis-status-en_planta { background:#d1fae5; color:#065f46; border:1px solid #a7f3d0; }
                .vis-status-en_planta .dot { width:6px; height:6px; border-radius:50%; background:#10b981; }
                .vis-status-fuera { background:#f1f5f9; color:#475569; border:1px solid #e2e8f0; }
                .vis-status-fuera .dot { width:6px; height:6px; border-radius:50%; background:#94a3b8; }
                .vis-hist-table thead th { font-size:0.68rem; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; color:#64748b; padding:10px 12px; background:#f8fafc; }
                .vis-hist-table tbody td { padding:10px 12px; font-size:0.82rem; }
                .vis-hist-table tbody tr:hover { background:rgba(248,250,252,0.5); }
                .vis-hint { font-size:0.72rem; color:#94a3b8; margin-top:6px; }
                .vis-pulse { animation: visPulse 2s infinite; }
                @keyframes visPulse { 0%, 100% { opacity:1; } 50% { opacity:0.5; } }
            </style>

            <!-- ENCABEZADO -->
            <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
                <div class="d-flex align-items-center gap-3">
                    <div style="background:#fff; padding:8px; border-radius:10px; box-shadow:var(--shadow-sm); border:1px solid #e2e8f0; color:var(--primary-color); display:flex;">
                        <i class="bi bi-person-badge-fill" style="font-size:1.3rem"></i>
                    </div>
                    <div>
                        <h4 class="fw-bold mb-0" style="color:#1e293b; letter-spacing:-0.02em">Control de Visitas</h4>
                        <p class="mb-0" style="font-size:0.82rem; color:#64748b; font-weight:500">Registro de ingreso y salida de visitantes</p>
                    </div>
                </div>
                <span style="background:#fff; padding:6px 16px; border-radius:999px; box-shadow:var(--shadow-sm); border:1px solid #e2e8f0; font-size:0.85rem; font-weight:600; color:#475569">
                    <i class="bi bi-calendar3 me-1" style="color:#94a3b8"></i>${fechaDisplay}
                </span>
            </div>

            <!-- KPI STATS -->
            <div class="row g-3 mb-4">
                <div class="col-md-4">
                    <div class="vis-kpi" style="background:var(--primary-color)">
                        <i class="bi bi-people-fill kpi-icon"></i>
                        <div class="kpi-label">Visitas Hoy</div>
                        <div class="d-flex align-items-baseline gap-2 mt-2">
                            <span class="kpi-number" id="vis-stat-total">—</span>
                            <span class="kpi-sub">registradas</span>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="vis-kpi" style="background:var(--success-color)">
                        <i class="bi bi-building-fill-check kpi-icon"></i>
                        <div class="kpi-label">En Planta</div>
                        <div class="d-flex align-items-baseline gap-2 mt-2">
                            <span class="kpi-number" id="vis-stat-enplanta">—</span>
                            <span class="kpi-sub">ahora mismo</span>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="vis-kpi" style="background:#64748b">
                        <i class="bi bi-box-arrow-right kpi-icon"></i>
                        <div class="kpi-label">Salieron</div>
                        <div class="d-flex align-items-baseline gap-2 mt-2">
                            <span class="kpi-number" id="vis-stat-salieron">—</span>
                            <span class="kpi-sub">retirados</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ZONA DE ESCANEO -->
            <div class="card border-0 shadow-sm mb-4" style="border-radius:12px; overflow:hidden">
                <div class="vis-section-header">
                    <span class="vis-section-title">
                        <i class="bi bi-upc-scan" style="color:var(--primary-color)"></i>Escanear Cédula
                    </span>
                    <button class="btn btn-sm btn-outline-secondary" style="font-size:0.75rem; border-radius:6px" onclick="VisitasModule.toggleManual()">
                        <i class="bi bi-keyboard me-1"></i>Ingreso Manual
                    </button>
                </div>
                <div class="card-body p-4">
                    <div class="vis-scan-zone" id="vis-scan-zone">
                        <div class="mb-3">
                            <i class="bi bi-credit-card-2-front vis-pulse" style="font-size:2.5rem; color:var(--primary-color)"></i>
                        </div>
                        <input type="text" class="vis-scan-input" id="vis-scan-input"
                            placeholder="🔍 Toque aquí y escanee la cédula con el teclado scanner..."
                            autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false">
                        <div class="vis-hint" id="vis-scan-hint">
                            <i class="bi bi-info-circle me-1"></i>El campo detecta automáticamente cuando el scanner termina de escribir
                        </div>
                    </div>

                    <!-- Resultado del parseo -->
                    <div class="vis-result-card" id="vis-result-card">
                        <div class="d-flex justify-content-between align-items-start mb-3">
                            <div>
                                <span class="badge" id="vis-result-tipo" style="font-size:0.7rem">—</span>
                                <span class="badge bg-light text-dark border ms-1" id="vis-result-parse" style="font-size:0.65rem">—</span>
                            </div>
                            <button class="btn btn-sm btn-outline-danger" onclick="VisitasModule.cancelarRegistro()" style="font-size:0.72rem">
                                <i class="bi bi-x-lg"></i>
                            </button>
                        </div>
                        <div class="row g-2 mb-3">
                            <div class="col-md-4">
                                <label class="form-label" style="font-size:0.65rem; font-weight:600; text-transform:uppercase; color:#64748b">RUT</label>
                                <input type="text" class="form-control form-control-sm fw-bold" id="vis-rut" style="font-size:1rem">
                            </div>
                            <div class="col-md-4">
                                <label class="form-label" style="font-size:0.65rem; font-weight:600; text-transform:uppercase; color:#64748b">Nombre</label>
                                <input type="text" class="form-control form-control-sm" id="vis-nombre">
                            </div>
                            <div class="col-md-4">
                                <label class="form-label" style="font-size:0.65rem; font-weight:600; text-transform:uppercase; color:#64748b">Empresa</label>
                                <input type="text" class="form-control form-control-sm" id="vis-empresa">
                            </div>
                        </div>
                        <div class="row g-2 mb-3">
                            <div class="col-md-4">
                                <label class="form-label" style="font-size:0.65rem; font-weight:600; text-transform:uppercase; color:#64748b">Motivo</label>
                                <select class="form-select form-select-sm" id="vis-motivo">
                                    <option value="">Seleccionar...</option>
                                    <option value="Reunión">Reunión</option>
                                    <option value="Entrega">Entrega / Despacho</option>
                                    <option value="Servicio">Servicio Técnico</option>
                                    <option value="Auditoría">Auditoría</option>
                                    <option value="Capacitación">Capacitación</option>
                                    <option value="Otro">Otro</option>
                                </select>
                            </div>
                            <div class="col-md-4">
                                <label class="form-label" style="font-size:0.65rem; font-weight:600; text-transform:uppercase; color:#64748b">Área destino</label>
                                <input type="text" class="form-control form-control-sm" id="vis-area">
                            </div>
                            <div class="col-md-4">
                                <label class="form-label" style="font-size:0.65rem; font-weight:600; text-transform:uppercase; color:#64748b">Contacto interno</label>
                                <input type="text" class="form-control form-control-sm" id="vis-contacto">
                            </div>
                        </div>
                        <div class="row g-2 mb-3">
                            <div class="col-md-4">
                                <label class="form-label" style="font-size:0.65rem; font-weight:600; text-transform:uppercase; color:#64748b">Patente vehículo</label>
                                <input type="text" class="form-control form-control-sm" id="vis-patente" placeholder="Opcional">
                            </div>
                            <div class="col-md-8">
                                <label class="form-label" style="font-size:0.65rem; font-weight:600; text-transform:uppercase; color:#64748b">Observaciones</label>
                                <input type="text" class="form-control form-control-sm" id="vis-obs" placeholder="Opcional">
                            </div>
                        </div>
                        <button class="btn btn-primary fw-bold w-100" id="vis-btn-registrar" onclick="VisitasModule.registrarVisita()" style="border-radius:8px; padding:10px">
                            <i class="bi bi-check-circle me-1"></i>Registrar Ingreso
                        </button>
                    </div>
                </div>
            </div>

            <!-- VISITANTES DEL DÍA -->
            <div class="card border-0 shadow-sm mb-4" style="border-radius:12px; overflow:hidden">
                <div class="vis-section-header">
                    <span class="vis-section-title">
                        <i class="bi bi-people" style="color:var(--primary-color)"></i>Visitantes del Día
                    </span>
                    <button class="btn btn-sm text-primary fw-semibold" style="font-size:0.8rem" onclick="VisitasModule.cargarEstadoDia()">
                        <i class="bi bi-arrow-clockwise me-1"></i>Actualizar
                    </button>
                </div>
                <div id="vis-estado-body">
                    <div class="text-center py-4 text-muted">Cargando...</div>
                </div>
            </div>

            <!-- HISTORIAL -->
            <div class="card border-0 shadow-sm" style="border-radius:12px; overflow:hidden">
                <div class="vis-section-header" style="flex-wrap:wrap; gap:12px">
                    <span class="vis-section-title">
                        <i class="bi bi-clock-history" style="color:var(--primary-color)"></i>Historial
                    </span>
                    <div class="d-flex align-items-center gap-2" style="background:#f8fafc; padding:6px 10px; border-radius:8px; border:1px solid #f1f5f9">
                        <label style="font-size:0.65rem; font-weight:600; text-transform:uppercase; color:#64748b">Desde</label>
                        <input type="date" class="form-control form-control-sm" id="vis-hist-desde" style="font-size:0.82rem; border-color:#e2e8f0; border-radius:6px; max-width:140px">
                        <label style="font-size:0.65rem; font-weight:600; text-transform:uppercase; color:#64748b">Hasta</label>
                        <input type="date" class="form-control form-control-sm" id="vis-hist-hasta" style="font-size:0.82rem; border-color:#e2e8f0; border-radius:6px; max-width:140px">
                        <button class="btn btn-sm btn-primary fw-bold" onclick="VisitasModule.cargarHistorial()" style="border-radius:6px; font-size:0.8rem; white-space:nowrap">
                            <i class="bi bi-search me-1"></i>Consultar
                        </button>
                    </div>
                </div>
                <div class="table-responsive" style="max-height:350px">
                    <table class="table mb-0 vis-hist-table">
                        <thead><tr>
                            <th>Fecha</th><th>RUT</th><th>Nombre</th><th>Empresa</th>
                            <th>Área</th><th>1ª Entrada</th><th>Últ. Salida</th>
                            <th class="text-center">Marcas</th><th>Tipo</th>
                        </tr></thead>
                        <tbody id="vis-historial-tbody">
                            <tr><td colspan="9" class="text-center py-4 text-muted">Presione Consultar</td></tr>
                        </tbody>
                    </table>
                </div>
                <div id="vis-historial-pagination" class="d-flex justify-content-between align-items-center px-3 py-2 border-top" style="font-size:0.78rem; color:#64748b; background:#fff"></div>
            </div>
        `;

        // Defaults historial
        const hasta = document.getElementById('vis-hist-hasta');
        const desde = document.getElementById('vis-hist-desde');
        if (hasta) hasta.value = _fechaActual;
        if (desde) { const d = new Date(); d.setDate(d.getDate()-7); desde.value = d.toISOString().slice(0,10); }

        // Setup keyboard wedge listener
        _setupWedgeListener();

        // Focus en campo de escaneo
        setTimeout(() => { document.getElementById('vis-scan-input')?.focus(); }, 300);

        await cargarEstadoDia();
        if (_refreshInterval) clearInterval(_refreshInterval);
        _refreshInterval = setInterval(() => cargarEstadoDia(), 60000);
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
                setTimeout(() => input.focus(), 200);
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
                showToast(`✅ RUT detectado: ${data.rut} (${data.tipo_documento})`, 'info');
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
        tipoEl.textContent = data.tipo_documento;

        // Parse status + visitante conocido
        if (data.visitante_conocido) {
            parseEl.textContent = `🔁 Visitante conocido (${data.visitas_previas} visitas)`;
            parseEl.className = 'badge bg-primary-subtle text-primary border border-primary-subtle ms-1';
        } else {
            parseEl.textContent = data.parse_ok ? '✅ RUT Válido — Nueva visita' : '⚠️ Requiere verificación';
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

    function toggleManual() {
        const resultCard = document.getElementById('vis-result-card');
        if (resultCard?.classList.contains('show')) {
            cancelarRegistro();
        } else {
            _mostrarFormulario({ rut: '', nombre: '', tipo_documento: 'MANUAL', parse_ok: false }, '');
        }
    }

    function cancelarRegistro() {
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
            if (typeof showToast === 'function') showToast('Ingrese el RUT del visitante', 'warning');
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

            const icon = data.tipo_marca === 'E' ? '🟢' : '🔴';
            if (typeof showToast === 'function') {
                showToast(`${icon} ${data.tipo_label}: ${data.rut} ${nombre || ''} — ${data.hora.substring(0,5)}`, 'success');
            }

            cancelarRegistro();
            await cargarEstadoDia();

        } catch (e) {
            console.error(e);
            if (typeof Swal !== 'undefined') Swal.fire('Error', e.message, 'error');
        }
    }

    // ════════════════════════════════════════════════
    // ESTADO DEL DÍA
    // ════════════════════════════════════════════════
    async function cargarEstadoDia() {
        try {
            const res = await fetch(`/api/visitas/estado-dia/?fecha=${_fechaActual}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
            });
            if (!res.ok) throw new Error("Error");
            const data = await res.json();

            document.getElementById('vis-stat-total').textContent = data.stats.total_visitas;
            document.getElementById('vis-stat-enplanta').textContent = data.stats.en_planta;
            document.getElementById('vis-stat-salieron').textContent = data.stats.salieron;

            const body = document.getElementById('vis-estado-body');
            if (!data.visitantes.length) {
                body.innerHTML = '<div class="text-center py-4 text-muted" style="font-size:0.85rem">Sin visitas registradas hoy</div>';
                return;
            }

            body.innerHTML = data.visitantes.map(v => {
                const initials = (v.nombre || v.rut || '??').substring(0,2).toUpperCase();
                const statusClass = `vis-status-${v.estado}`;
                const statusLabel = v.estado === 'en_planta' ? 'En Planta' : 'Salió';
                const marcasHtml = v.marcas.map(m => {
                    const isE = m.tipo === 'E';
                    const cls = isE ? 'art22-mark-e' : 'art22-mark-s';
                    return `<span class="art22-mark ${cls}" style="font-size:0.68rem; padding:2px 6px"><i class="bi bi-${isE ? 'box-arrow-in-right' : 'box-arrow-right'}" style="font-size:0.6rem"></i>${m.hora.substring(0,5)}</span>`;
                }).join(' ');

                return `<div class="vis-visitor-row ${v.estado}">
                    <div style="width:8%"><div class="vis-avatar">${initials}</div></div>
                    <div style="width:18%">
                        <div style="font-weight:600; color:#1e293b; font-size:0.85rem">${v.rut}</div>
                        <div style="font-size:0.72rem; color:#64748b">${v.nombre || 'Sin nombre'}</div>
                    </div>
                    <div style="width:15%">
                        <div style="font-size:0.78rem; color:#475569">${v.empresa || ''}</div>
                        <div style="font-size:0.68rem; color:#94a3b8">${v.motivo || ''}</div>
                    </div>
                    <div style="width:12%">
                        <span class="art22-area-badge">${v.area_destino || '—'}</span>
                    </div>
                    <div style="width:27%; display:flex; flex-wrap:wrap; gap:3px">${marcasHtml}</div>
                    <div style="width:10%; text-align:center">
                        <span class="vis-status-pill ${statusClass}"><span class="dot"></span>${statusLabel}</span>
                    </div>
                    <div style="width:10%; text-align:right">
                        <button class="${v.estado === 'en_planta' ? 'art22-btn-salida' : 'art22-btn-entrada'}"
                            onclick="VisitasModule.marcarVisitante('${v.rut}')" style="font-size:0.7rem; padding:4px 10px">
                            ${v.estado === 'en_planta' ? 'Salida' : 'Re-entrada'} <i class="bi bi-${v.estado === 'en_planta' ? 'box-arrow-right' : 'box-arrow-in-right'}"></i>
                        </button>
                    </div>
                </div>`;
            }).join('');

        } catch (e) {
            console.error(e);
            const body = document.getElementById('vis-estado-body');
            if (body) body.innerHTML = '<div class="text-center py-4 text-danger">Error al cargar</div>';
        }
    }

    async function marcarVisitante(rut) {
        try {
            const res = await fetch('/api/visitas/registrar/', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ rut })
            });
            if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Error'); }
            const data = await res.json();
            const icon = data.tipo_marca === 'E' ? '🟢' : '🔴';
            if (typeof showToast === 'function') showToast(`${icon} ${data.tipo_label}: ${data.rut} — ${data.hora.substring(0,5)}`, 'success');
            await cargarEstadoDia();
        } catch (e) { console.error(e); if (typeof Swal !== 'undefined') Swal.fire('Error', e.message, 'error'); }
    }

    // ════════════════════════════════════════════════
    // HISTORIAL
    // ════════════════════════════════════════════════
    async function cargarHistorial(page = 1) {
        const desde = document.getElementById('vis-hist-desde')?.value;
        const hasta = document.getElementById('vis-hist-hasta')?.value;
        const tbody = document.getElementById('vis-historial-tbody');
        if (!desde || !hasta) return;
        tbody.innerHTML = '<tr><td colspan="9" class="text-center py-4"><div class="spinner-border spinner-border-sm text-primary"></div></td></tr>';

        try {
            const res = await fetch(`/api/visitas/historial/?desde=${desde}&hasta=${hasta}&page=${page}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
            });
            if (!res.ok) throw new Error("Error");
            const data = await res.json();
            if (!data.registros.length) { tbody.innerHTML = '<tr><td colspan="9" class="text-center py-4 text-muted">Sin registros</td></tr>'; return; }

            tbody.innerHTML = data.registros.map(r => {
                const f = r.fecha.split('-');
                const ms = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
                return `<tr>
                    <td style="font-weight:500; color:#475569">${parseInt(f[2])} ${ms[parseInt(f[1])]} ${f[0]}</td>
                    <td style="font-weight:600; color:#1e293b">${r.rut}</td>
                    <td>${r.nombre || '—'}</td>
                    <td style="color:#475569">${r.empresa || '—'}</td>
                    <td><span class="art22-area-badge">${r.area_destino || '—'}</span></td>
                    <td style="color:#065f46; font-weight:500">${r.primera_entrada ? r.primera_entrada.substring(0,5) : '—'}</td>
                    <td style="color:#9f1239; font-weight:500">${r.ultima_salida ? r.ultima_salida.substring(0,5) : '—'}</td>
                    <td class="text-center"><span class="art22-marcas-circle">${r.total_marcas}</span></td>
                    <td><span class="badge bg-light text-dark border" style="font-size:0.65rem">${r.tipo_documento}</span></td>
                </tr>`;
            }).join('');
        } catch (e) { tbody.innerHTML = '<tr><td colspan="9" class="text-center py-4 text-danger">Error</td></tr>'; }
    }

    function destroy() { if (_refreshInterval) { clearInterval(_refreshInterval); _refreshInterval = null; } }

    return { initTab, cargarEstadoDia, cargarHistorial, registrarVisita, marcarVisitante, toggleManual, cancelarRegistro, destroy };
})();
