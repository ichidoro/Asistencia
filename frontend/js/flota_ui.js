/**
 * Módulo Flota Aguacol — Control de Ingreso/Salida Vehicular
 * Diseño Enterprise inspirado en Stitch/Stripe/Linear
 */
const FlotaModule = (() => {
    let _fechaActual = (() => {
        const d = new Date();
        return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    })();
    let _refreshInterval = null;
    let _tickingInterval = null;
    let _catalogoAreasCached = []; // Cache local para evitar llamadas repetidas
    let _selectedVehiculoId = null;
    let _vehiculosCache = [];

    function injectStyles() {
        let style = document.getElementById('flota-module-styles');
        if (!style) {
            style = document.createElement('style');
            style.id = 'flota-module-styles';
            document.head.appendChild(style);
        }
        style.textContent = `
            /* Placa Patente Chilena Estilo Premium */
            .chilean-plate {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: #ffffff;
                border: 2.5px solid #000000;
                border-radius: 4px;
                padding: 2px 8px;
                min-width: 100px;
                height: 28px;
                box-shadow: inset 0 0 0 1px #1d4ed8, 0 2px 4px rgba(0,0,0,0.08);
                position: relative;
                user-select: none;
                vertical-align: middle;
            }
            .plate-letters, .plate-numbers {
                font-family: 'Trebuchet MS', Arial, sans-serif;
                font-weight: 850;
                font-size: 0.92rem;
                color: #111827;
                letter-spacing: 0.5px;
                line-height: 1;
            }
            .plate-shield {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 6px;
                height: 6px;
                border-radius: 50%;
                background: #1d4ed8;
                margin: 0 5px;
                position: relative;
            }
            .plate-shield::after {
                content: '';
                display: block;
                width: 2px;
                height: 2px;
                background: #ffffff;
                border-radius: 50%;
            }
            .plate-country {
                position: absolute;
                bottom: 1.5px;
                left: 50%;
                transform: translateX(-50%);
                font-family: 'Inter', Arial, sans-serif;
                font-size: 0.38rem;
                font-weight: 900;
                color: #1d4ed8;
                letter-spacing: 1.5px;
                text-transform: uppercase;
                line-height: 1;
            }

            /* Marcas de Movimientos */
            .flota-mark-box {
                display: inline-flex;
                flex-direction: column;
                width: 76px;
                height: 44px;
                border-radius: 8px;
                overflow: hidden;
                border: 1px solid #cbd5e1;
                box-shadow: 0 1px 2px rgba(0,0,0,0.03);
                text-align: center;
                vertical-align: middle;
                transition: all 0.2s;
            }
            .flota-mark-box:hover {
                box-shadow: 0 3px 6px rgba(0,0,0,0.06);
                transform: translateY(-0.5px);
            }
            .flota-mark-box.entrada {
                border-color: #a7f3d0;
            }
            .flota-mark-box.salida {
                border-color: #fecdd3;
            }
            .flota-mark-box .flota-mark-header {
                font-size: 0.55rem;
                font-weight: 900;
                letter-spacing: 0.05em;
                padding: 2px 0;
                color: #ffffff;
                text-transform: uppercase;
                line-height: 1.2;
            }
            .flota-mark-box.entrada .flota-mark-header {
                background-color: #10b981;
            }
            .flota-mark-box.salida .flota-mark-header {
                background-color: #e11d48;
            }
            .flota-mark-box .flota-mark-time {
                font-size: 0.82rem;
                font-weight: 800;
                color: #0f172a;
                background-color: #ffffff;
                padding: 3px 0;
                flex-grow: 1;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .flota-mark-arrow {
                color: #cbd5e1;
                font-size: 0.95rem;
                margin: 0 4px;
                display: inline-flex;
                align-items: center;
                height: 44px;
                vertical-align: middle;
            }

            /* Split Layout de Consola */
            .flota-split-container {
                display: flex;
                gap: 24px;
                align-items: stretch;
            }
            .flota-sidebar-list {
                width: 320px;
                background: #ffffff;
                border-radius: 16px;
                border: 1px solid #e2e8f0;
                padding: 16px;
                display: flex;
                flex-direction: column;
                gap: 10px;
                max-height: 580px;
                overflow-y: auto;
                box-shadow: 0 1px 3px rgba(0,0,0,0.01);
                flex-shrink: 0;
            }
            .flota-detail-panel {
                flex-grow: 1;
                background: #ffffff;
                border-radius: 16px;
                border: 1px solid #e2e8f0;
                padding: 28px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.01);
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                min-height: 580px;
                position: relative;
            }

            /* Elemento de lista lateral - Cards Premium */
            .flota-sidebar-item {
                padding: 12px 14px;
                border-radius: 12px;
                border: 1.5px solid #f1f5f9;
                background: #ffffff;
                cursor: pointer;
                display: flex;
                align-items: center;
                transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            }
            .flota-sidebar-item:hover {
                border-color: #cbd5e1;
                background: #fafbfc;
                transform: translateY(-1px);
            }
            .flota-sidebar-item.active {
                background: #f0f9ff;
                border-color: #3b82f6;
                box-shadow: 0 4px 12px rgba(59, 130, 246, 0.08);
            }
            .truck-avatar-premium {
                width: 44px;
                height: 44px;
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                overflow: hidden;
                padding: 2px;
                transition: all 0.2s;
            }
            .truck-avatar-premium i {
                color: #64748b !important;
                transition: color 0.2s;
            }
            .flota-sidebar-item.active .truck-avatar-premium {
                background: #eff6ff;
                border-color: #bfdbfe;
            }
            .flota-sidebar-item.active .truck-avatar-premium i {
                color: #2563eb !important;
            }

            /* Línea de ruta interactiva */
            .lane-route-track {
                position: relative;
                height: 160px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 0 100px;
                background-color: #fafbfc;
                background-image: radial-gradient(#cbd5e1 1.2px, transparent 1.2px);
                background-size: 20px 20px;
                border-radius: 16px;
                margin: 24px 0 28px 0;
                border: 1px solid #e2e8f0;
            }
            .route-line {
                position: absolute;
                top: 50%;
                left: 132px;
                right: 132px;
                height: 6px;
                background: #e2e8f0;
                transform: translateY(-50%);
                z-index: 1;
                border-radius: 3px;
                transition: all 0.5s ease;
            }
            .route-line.active-despacho {
                background: linear-gradient(90deg, #10b981 0%, #e11d48 100%);
                box-shadow: 0 0 12px rgba(16, 185, 129, 0.45);
                height: 8px;
            }
            .route-line.inactive-planta {
                background-image: linear-gradient(to right, #cbd5e1 50%, transparent 50%);
                background-size: 10px 100%;
                background-color: transparent;
                height: 4px;
            }
            
            .route-node {
                position: relative;
                z-index: 2;
                background: #ffffff;
                width: 64px;
                height: 64px;
                border-radius: 50%;
                border: 3px solid #cbd5e1;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
                font-size: 1.75rem;
                transition: all 0.3s ease;
            }
            .route-node.node-planta.active {
                border-color: #10b981;
                box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.15), 0 4px 10px rgba(16, 185, 129, 0.2);
            }
            .route-node.node-despacho.active {
                border-color: #e11d48;
                box-shadow: 0 0 0 4px rgba(225, 29, 72, 0.15), 0 4px 10px rgba(225, 29, 72, 0.2);
            }
            .node-caption {
                position: absolute;
                top: 72px;
                font-family: 'Inter', system-ui, sans-serif;
                font-size: 0.72rem;
                font-weight: 700;
                color: #475569;
                text-transform: capitalize;
                white-space: nowrap;
            }
            .route-node.active .node-caption {
                color: #0f172a;
                font-weight: 850;
            }

            /* Camión Deslizable */
            .route-truck-indicator {
                position: absolute;
                top: 50%;
                left: 132px;
                transform: translate(-50%, -50%);
                z-index: 3;
                display: flex;
                flex-direction: column;
                align-items: center;
                transition: all 0.8s cubic-bezier(0.25, 0.8, 0.25, 1);
            }
            .route-truck-indicator .truck-bubble {
                width: 48px;
                height: 48px;
                background: #ffffff;
                border: 2.5px solid #cbd5e1;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
                font-size: 1.45rem;
                transition: all 0.8s;
            }
            .estado-en_planta .route-truck-indicator {
                left: 132px;
            }
            .estado-en_planta .route-truck-indicator .truck-bubble {
                border-color: #10b981;
                box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.1);
            }
            .estado-fuera .route-truck-indicator {
                left: 50%;
            }
            .estado-fuera .route-truck-indicator .truck-bubble {
                border-color: #3b82f6;
                box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.1);
            }
            
            .route-truck-indicator .truck-badge-top {
                position: absolute;
                top: -24px;
                font-size: 0.58rem;
                font-weight: 850;
                padding: 2px 7px;
                border-radius: 30px;
                white-space: nowrap;
                color: #ffffff;
                box-shadow: 0 2px 4px rgba(0,0,0,0.08);
                letter-spacing: 0.02em;
            }
            .estado-en_planta .route-truck-indicator .truck-badge-top {
                background: #10b981;
            }
            .estado-fuera .route-truck-indicator .truck-badge-top {
                background: #3b82f6;
            }
            .route-truck-indicator .truck-label-bottom {
                position: absolute;
                bottom: -24px;
                font-size: 0.72rem;
                font-weight: 850;
                color: #1e293b;
                font-family: monospace;
                white-space: nowrap;
            }

            /* Relojes / Widgets */
            .mini-clock-widget {
                position: relative;
                width: 24px;
                height: 24px;
                border: 2px solid currentColor;
                border-radius: 50%;
                display: inline-block;
                vertical-align: middle;
                flex-shrink: 0;
            }
            .mini-clock-widget::after {
                content: '';
                position: absolute;
                top: 50%;
                left: 50%;
                width: 4px;
                height: 4px;
                background: currentColor;
                border-radius: 50%;
                transform: translate(-50%, -50%);
            }
            .mini-clock-widget .hand {
                position: absolute;
                bottom: 50%;
                left: 50%;
                background: currentColor;
                transform-origin: bottom center;
                border-radius: 1px;
            }
            .mini-clock-widget .hour-hand {
                width: 1.8px;
                height: 6px;
                animation: spinHour 12s linear infinite;
            }
            .mini-clock-widget .minute-hand {
                width: 1px;
                height: 9px;
                animation: spinMinute 1.5s linear infinite;
            }
            
            /* Stopwatch Widget Red */
            .stopwatch-widget {
                position: relative;
                width: 26px;
                height: 26px;
                border: 2px solid #ef4444;
                border-radius: 50%;
                display: inline-block;
                background: #fef2f2;
                color: #ef4444;
                vertical-align: middle;
                flex-shrink: 0;
            }
            .stopwatch-widget::before {
                content: '';
                position: absolute;
                top: -3.5px;
                left: 50%;
                transform: translateX(-50%);
                width: 7px;
                height: 2.2px;
                background: #ef4444;
                border-radius: 1px;
            }
            .stopwatch-widget::after {
                content: '';
                position: absolute;
                top: 50%;
                left: 50%;
                width: 3.5px;
                height: 3.5px;
                background: #ef4444;
                border-radius: 50%;
                transform: translate(-50%, -50%);
            }
            .stopwatch-widget .hand {
                position: absolute;
                bottom: 50%;
                left: 50%;
                background: #ef4444;
                transform-origin: bottom center;
                width: 1.2px;
                height: 8.5px;
                animation: spinMinute 2s linear infinite;
            }

            @keyframes spinHour {
                from { transform: translate(-50%, 0) rotate(0deg); }
                to { transform: translate(-50%, 0) rotate(360deg); }
            }
            @keyframes spinMinute {
                from { transform: translate(-50%, 0) rotate(0deg); }
                to { transform: translate(-50%, 0) rotate(360deg); }
            }

            /* Dashboard Cards */
            .flota-dash-cards {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 16px;
                margin-top: 24px;
                margin-bottom: 16px;
            }
            .flota-dash-card {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 16px 18px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
                transition: transform 0.2s, box-shadow 0.2s;
                min-height: 100px;
            }
            .flota-dash-card:hover {
                transform: translateY(-1px);
                box-shadow: 0 8px 12px -3px rgba(0, 0, 0, 0.04);
            }
            .flota-dash-card-label {
                font-size: 0.72rem;
                font-weight: 700;
                color: #64748b;
                letter-spacing: 0.02em;
                margin-bottom: 6px;
                display: flex;
                align-items: center;
                gap: 6px;
            }
            .flota-dash-card-val {
                font-size: 1.4rem;
                font-weight: 850;
                color: #0f172a;
                line-height: 1.2;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .flota-dash-card-sub {
                font-size: 0.65rem;
                color: #94a3b8;
                font-weight: 500;
                margin-top: 5px;
            }
            .flota-dash-card.active-estadia {
                border-color: #bbf7d0;
                background: #f0fdf4;
            }
            .flota-dash-card.active-viaje {
                border-color: #bfdbfe;
                background: #eff6ff;
            }

            /* Botón de acción premium */
            .flota-action-btn-container {
                width: 100%;
                display: flex;
                justify-content: center;
                margin-top: 24px;
            }
            .flota-action-btn {
                width: 100%;
                max-width: 420px;
                height: 48px;
                border-radius: 24px;
                font-family: 'Inter', system-ui, sans-serif;
                font-size: 0.9rem;
                font-weight: 800;
                color: #ffffff !important;
                border: none !important;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                cursor: pointer;
                transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
                letter-spacing: 0.04em;
                text-transform: uppercase;
            }
            .flota-action-btn.btn-a-despacho {
                background: linear-gradient(135deg, #9f1239, #e11d48) !important;
                box-shadow: 0 6px 18px rgba(225, 29, 72, 0.35) !important;
            }
            .flota-action-btn.btn-a-despacho:hover {
                background: linear-gradient(135deg, #e11d48, #f43f5e) !important;
                transform: translateY(-2px);
                box-shadow: 0 8px 22px rgba(225, 29, 72, 0.45) !important;
            }
            .flota-action-btn.btn-a-despacho:active {
                transform: translateY(0);
                box-shadow: 0 4px 8px rgba(225, 29, 72, 0.25) !important;
            }
            .flota-action-btn.btn-retorno {
                background: linear-gradient(135deg, #047857, #10b981) !important;
                box-shadow: 0 6px 18px rgba(16, 185, 129, 0.35) !important;
            }
            .flota-action-btn.btn-retorno:hover {
                background: linear-gradient(135deg, #10b981, #34d399) !important;
                transform: translateY(-2px);
                box-shadow: 0 8px 22px rgba(16, 185, 129, 0.45) !important;
            }
            .flota-action-btn.btn-retorno:active {
                transform: translateY(0);
                box-shadow: 0 4px 8px rgba(16, 185, 129, 0.25) !important;
            }
        `;
    }

    function renderPlacaPatente(patente) {
        const pat = String(patente).toUpperCase().replace(/[^A-Z0-9]/g, '');
        let letters = '';
        let numbers = '';
        
        if (pat.length === 6) {
            if (/^[A-Z]{4}[0-9]{2}$/.test(pat)) {
                letters = pat.substring(0, 2) + " " + pat.substring(2, 4);
                numbers = pat.substring(4, 6);
            } else if (/^[A-Z]{2}[0-9]{4}$/.test(pat)) {
                letters = pat.substring(0, 2);
                numbers = pat.substring(2, 4) + " " + pat.substring(4, 6);
            } else if (/^[A-Z]{3}[0-9]{3}$/.test(pat)) {
                letters = pat.substring(0, 3);
                numbers = pat.substring(3, 6);
            } else {
                letters = pat.substring(0, 3);
                numbers = pat.substring(3, 6);
            }
        } else {
            const mid = Math.ceil(pat.length / 2);
            letters = pat.substring(0, mid);
            numbers = pat.substring(mid);
        }
        
        return `
            <div class="chilean-plate" title="${patente}">
                <span class="plate-letters">${letters}</span>
                <span class="plate-shield"></span>
                <span class="plate-numbers">${numbers}</span>
                <span class="plate-country">CHILE</span>
            </div>
        `;
    }

    // ════════════════════════════════════════════════
    // INIT CONTROL TAB (PORTERÍA)
    // ════════════════════════════════════════════════
    async function initTab() {
        injectStyles();
        const container = document.getElementById('flota-container');
        if (!container) return;

        const hoy = new Date();
        const diasSemana = ['Domingo','Lunes','Martes','Miércoles','Jueves','Viernes','Sábado'];
        const meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
        const fechaDisplay = `${diasSemana[hoy.getDay()]} ${hoy.getDate()} ${meses[hoy.getMonth()]} ${hoy.getFullYear()}`;

        container.innerHTML = `
            <style>
                .flota-kpi { position: relative; overflow: hidden; border-radius: 12px; padding: 1.25rem 1.5rem; color: #fff; transition: transform 0.3s; }
                .flota-kpi:hover { transform: translateY(-2px); }
                .flota-kpi .kpi-icon { position: absolute; right: -10px; top: -10px; font-size: 5rem; opacity: 0.08; }
                .flota-kpi .kpi-number { font-size: 2.25rem; font-weight: 800; line-height: 1; }
                .flota-kpi .kpi-label { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; opacity: 0.9; }
                .flota-kpi .kpi-sub { font-size: 0.8rem; font-weight: 500; opacity: 0.8; margin-top: 2px; }
                
                .flota-section-header { background: rgba(248,250,252,0.5); padding: 0.9rem 1.2rem; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center; }
                .flota-section-title { font-size: 1rem; font-weight: 600; color: #1e293b; display: flex; align-items: center; gap: 8px; }
                .flota-filter-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; background: #f8fafc; padding: 8px 12px; border-radius: 8px; border: 1px solid #f1f5f9; }
                .flota-filter-bar label { font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #64748b; }
                
                .flota-hist-table thead tr { background: #f8fafc; border-bottom: 1px solid #e2e8f0; }
                .flota-hist-table thead th { font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #64748b; padding: 10px 14px; }
                .flota-hist-table tbody td { padding: 10px 14px; font-size: 0.82rem; }
                .flota-hist-table tbody tr { transition: background 0.15s; }
                .flota-hist-table tbody tr:hover { background: rgba(248,250,252,0.5); }
                .flota-hist-table tbody tr:not(:last-child) td { border-bottom: 1px solid #f1f5f9; }
            </style>

            <!-- ENCABEZADO -->
            <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
                <div class="d-flex align-items-center gap-3">
                    <div style="background:#fff; padding:8px; border-radius:10px; box-shadow: var(--shadow-sm); border:1px solid #e2e8f0; color:#3b82f6; display:flex; align-items:center; justify-content:center;">
                        <i class="bi bi-truck" style="font-size:1.3rem"></i>
                    </div>
                    <div>
                        <h4 class="fw-bold mb-0" style="color:#1e293b; letter-spacing:-0.02em">Flota Aguacol</h4>
                        <p class="mb-0" style="font-size:0.82rem; color:#64748b; font-weight:500">Control de ingresos, salidas y tiempos de viaje</p>
                    </div>
                </div>
                <div class="d-flex align-items-center gap-2">
                    <span style="background:#fff; padding:6px 16px; border-radius:999px; box-shadow:var(--shadow-sm); border:1px solid #e2e8f0; font-size:0.85rem; font-weight:600; color:#475569">
                        <i class="bi bi-calendar3 me-1" style="color:#94a3b8"></i>${fechaDisplay}
                    </span>
                    <button class="btn btn-sm btn-light border" onclick="FlotaModule.cargarEstadoDia()" style="border-radius:8px">
                        <i class="bi bi-arrow-clockwise"></i>
                    </button>
                </div>
            </div>

            <!-- KPI STATS -->
            <div class="row g-3 mb-4">
                <div class="col-md-4">
                    <div class="flota-kpi" style="background: linear-gradient(135deg, #1e293b, #334155)">
                        <i class="bi bi-truck kpi-icon"></i>
                        <div class="kpi-label">Total Flota</div>
                        <div class="d-flex align-items-baseline gap-2 mt-2">
                            <span class="kpi-number" id="flota-stat-total">—</span>
                            <span class="kpi-sub">vehículos activos</span>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="flota-kpi" style="background: linear-gradient(135deg, #10b981, #059669)">
                        <i class="bi bi-geo-alt-fill kpi-icon"></i>
                        <div class="kpi-label">En Planta</div>
                        <div class="d-flex align-items-baseline gap-2 mt-2">
                            <span class="kpi-number" id="flota-stat-planta">—</span>
                            <span class="kpi-sub">cargando/descargando</span>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="flota-kpi" style="background: linear-gradient(135deg, #f43f5e, #be123c)">
                        <i class="bi bi-compass-fill kpi-icon"></i>
                        <div class="kpi-label">En Despacho</div>
                        <div class="d-flex align-items-baseline gap-2 mt-2">
                            <span class="kpi-number" id="flota-stat-viaje">—</span>
                            <span class="kpi-sub">fuera de planta</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- CONSOLA DE CONTROL DE FLOTA (DIVIDIDO) -->
            <div class="card border-0 shadow-sm mb-4" style="border-radius:12px; overflow:hidden">
                <div class="flota-section-header">
                    <span class="flota-section-title">
                        <i class="bi bi-list-check" style="color:#3b82f6"></i>Consola de Control de Flota
                    </span>
                    <button class="btn btn-sm text-primary fw-semibold" style="font-size:0.8rem" onclick="FlotaModule.cargarEstadoDia()">
                        <i class="bi bi-arrow-clockwise me-1"></i>Actualizar
                    </button>
                </div>
                <div class="card-body p-3" style="background:#f8fafc;">
                    <div class="flota-split-container" id="flota-split-layout">
                        <div class="text-center py-5 text-muted w-100">
                            <div class="spinner-border spinner-border-sm text-primary"></div> Cargando Consola...
                        </div>
                    </div>
                </div>
            </div>

            <!-- HISTORIAL -->
            <div class="card border-0 shadow-sm" style="border-radius:12px; overflow:hidden">
                <div class="flota-section-header" style="flex-wrap:wrap; gap:12px;">
                    <span class="flota-section-title">
                        <i class="bi bi-clock-history" style="color:#3b82f6"></i>Historial de Movimientos
                    </span>
                    <div class="flota-filter-bar">
                        <div class="d-flex align-items-center gap-2">
                            <label>Desde</label>
                            <input type="date" class="form-control form-control-sm" id="flota-hist-desde" style="font-size:0.82rem; border-color:#e2e8f0; border-radius:6px;">
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            <label>Hasta</label>
                            <input type="date" class="form-control form-control-sm" id="flota-hist-hasta" style="font-size:0.82rem; border-color:#e2e8f0; border-radius:6px;">
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            <label>Buscar Patente</label>
                            <input type="text" class="form-control form-control-sm" id="flota-hist-patente" placeholder="ABCD12" style="font-size:0.82rem; border-color:#e2e8f0; border-radius:6px; max-width: 100px;">
                        </div>
                        <button class="btn btn-sm btn-primary fw-bold px-3" onclick="FlotaModule.cargarHistorial()" style="border-radius:6px; font-size:0.8rem">
                            <i class="bi bi-search me-1"></i>Consultar
                        </button>
                    </div>
                </div>
                <div class="table-responsive" style="max-height:400px; overflow-y:auto;">
                    <table class="table mb-0 flota-hist-table">
                        <thead>
                            <tr>
                                <th>Fecha</th>
                                <th>Hora</th>
                                <th>Patente</th>
                                <th>Área</th>
                                <th>Tipo</th>
                                <th>Registrado Por</th>
                                <th>Observaciones</th>
                            </tr>
                        </thead>
                        <tbody id="flota-historial-tbody">
                            <tr><td colspan="7" class="text-center py-4 text-muted" style="font-size:0.85rem">Seleccione rango y presione Consultar</td></tr>
                        </tbody>
                    </table>
                </div>
                <div id="flota-historial-pagination" class="d-flex justify-content-between align-items-center px-3 py-2 border-top" style="font-size:0.78rem; color:#64748b; background:#fff;"></div>
            </div>
        `;

        const hasta = document.getElementById('flota-hist-hasta');
        const desde = document.getElementById('flota-hist-desde');
        if (hasta) hasta.value = _fechaActual;
        if (desde) { 
            const d = new Date(); 
            d.setDate(d.getDate()-7); 
            desde.value = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; 
        }

        await cargarEstadoDia();
        if (_refreshInterval) clearInterval(_refreshInterval);
        _refreshInterval = setInterval(() => cargarEstadoDia(), 60000); // Autorefresh cada 60s
        
        if (_tickingInterval) clearInterval(_tickingInterval);
        _tickingInterval = setInterval(() => tickLiveClocks(), 1000); // Actualización de segundos
    }

    // ════════════════════════════════════════════════
    // CARGAR ESTADO DEL DÍA (Hoy)
    // ════════════════════════════════════════════════
    // ════════════════════════════════════════════════
    // CARGAR ESTADO DEL DÍA (Hoy)
    // ════════════════════════════════════════════════
    async function cargarEstadoDia() {
        try {
            const res = await fetch(`/api/flota/estado-dia/?fecha=${_fechaActual}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });
            if (!res.ok) throw new Error("Error cargando estado de la flota");
            const data = await res.json();

            document.getElementById('flota-stat-total').textContent = data.stats.total;
            document.getElementById('flota-stat-planta').textContent = data.stats.en_planta;
            document.getElementById('flota-stat-viaje').textContent = data.stats.en_viaje;

            _vehiculosCache = data.vehiculos || [];

            const layout = document.getElementById('flota-split-layout');
            if (!_vehiculosCache.length) {
                if (layout) layout.innerHTML = '<div class="text-center py-5 text-muted w-100">No hay vehículos configurados en el catálogo de flota.</div>';
                return;
            }

            // Seleccionar el primer vehículo por defecto si no hay ninguno seleccionado o el seleccionado ya no existe
            if (!_selectedVehiculoId || !_vehiculosCache.some(v => v.id === _selectedVehiculoId)) {
                _selectedVehiculoId = _vehiculosCache[0].id;
            }

            renderSplitLayout();
        } catch (e) {
            console.error(e);
            const layout = document.getElementById('flota-split-layout');
            if (layout) layout.innerHTML = '<div class="text-center py-5 text-danger fw-bold w-100">Error al conectar con la base de datos central</div>';
        }
    }

    function selectVehiculo(id) {
        _selectedVehiculoId = id;
        renderSplitLayout();
    }

    function renderSplitLayout() {
        const layout = document.getElementById('flota-split-layout');
        if (!layout) return;

        // 1. Renderizar la columna izquierda (Lista de vehículos)
        const sidebarHtml = `
            <div class="flota-sidebar-list">
                <div class="small fw-bold text-muted mb-2 px-1 text-uppercase" style="letter-spacing: 0.05em; font-size: 0.65rem;">UNIDADES EN PATIO</div>
                ${_vehiculosCache.map(v => {
                    const isActive = v.id === _selectedVehiculoId ? 'active' : '';
                    const stateLabel = v.estado === 'en_planta' ? 'EN PLANTA' : 'EN RUTA';
                    const statePillClass = v.estado === 'en_planta' ? 'bg-success-subtle text-success border-success-subtle' : 'bg-warning-subtle text-warning border-warning-subtle';
                    const driverText = v.chofer_activo ? v.chofer_activo : 'Sin chofer';
                    
                    return `
                        <div class="flota-sidebar-item ${isActive}" onclick="FlotaModule.selectVehiculo(${v.id})">
                            <div class="truck-avatar-premium">
                                <i class="bi bi-truck" style="font-size: 1.25rem;"></i>
                            </div>
                            <div class="flex-grow-1 min-width-0 ms-3">
                                <div class="d-flex align-items-center justify-content-between mb-1">
                                    <span class="fw-bold text-muted" style="font-size: 0.7rem; letter-spacing: 0.02em;">Unidad</span>
                                    <span class="badge border ${statePillClass}" style="font-size: 0.58rem; font-weight: 800; padding: 2px 6px;">${stateLabel}</span>
                                </div>
                                <div class="mb-2">
                                    ${renderPlacaPatente(v.patente)}
                                </div>
                                <div class="d-flex align-items-center justify-content-between">
                                    <span class="text-secondary text-truncate" style="font-size: 0.68rem; font-weight: 500; max-width: 130px;" title="${driverText}">
                                        <i class="bi bi-person me-0.5"></i>${driverText}
                                    </span>
                                    <span class="badge bg-light text-secondary border" style="font-size: 0.58rem; padding: 1.5px 5px;">${v.area}</span>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;

        // 2. Obtener el vehículo seleccionado
        const veh = _vehiculosCache.find(v => v.id === _selectedVehiculoId) || _vehiculosCache[0];
        if (!veh) {
            layout.innerHTML = sidebarHtml + `<div class="flota-detail-panel justify-content-center align-items-center text-muted">Seleccione un vehículo de la lista.</div>`;
            return;
        }

        // 3. Renderizar marcas del vehículo
        let marcasHtml = '';
        if (veh.marcas && veh.marcas.length > 0) {
            marcasHtml = veh.marcas.map((m, i) => {
                const isE = m.tipo === 'ENTRADA';
                const boxCls = isE ? 'entrada' : 'salida';
                const label = isE ? 'RETORNO' : 'DESPACHO';
                const timeStr = m.hora.substring(0, 5);
                const arrow = i < veh.marcas.length - 1 ? '<span class="flota-mark-arrow"><i class="bi bi-chevron-right"></i></span>' : '';
                return `
                    <div class="flota-mark-box ${boxCls}" title="Registrado por: ${m.registrado_por_nombre || 'Desconocido'}\nObservaciones: ${m.observaciones || 'Sin observaciones'}">
                        <div class="flota-mark-header">${label}</div>
                        <div class="flota-mark-time">${timeStr}</div>
                    </div>${arrow}
                `;
            }).join('');
        } else {
            marcasHtml = '<span style="font-size:0.75rem; color:#94a3b8; font-style:italic">Sin movimientos registrados hoy</span>';
        }

        // Tiempos y Ticking
        const isEnPlanta = veh.estado === 'en_planta';
        const activeClassEstadia = isEnPlanta ? 'live-ticking-estadia' : '';
        const activeClassViaje = !isEnPlanta ? 'live-ticking-viaje' : '';

        const clockWidgetEstadia = isEnPlanta 
            ? `<div class="mini-clock-widget text-success me-2"><div class="hand hour-hand"></div><div class="hand minute-hand"></div></div>`
            : '';
        const clockWidgetViaje = !isEnPlanta 
            ? `<div class="stopwatch-widget me-2"><div class="hand"></div></div>`
            : '';

        const estadiaVal = veh.estadia_display !== '—' ? veh.estadia_display : '—';
        const viajeVal = veh.viaje_display !== '—' ? veh.viaje_display : '—';

        const estadiaHtml = `
            <div class="flota-dash-card-val ${activeClassEstadia}" id="live-estadia-${veh.id}" data-base-min="${veh.estadia_total_min || 0}" data-start-ms="${new Date().getTime()}" data-active="${isEnPlanta ? 'true' : 'false'}">
                ${clockWidgetEstadia}<span class="time-text">${estadiaVal}</span>
            </div>
        `;

        const viajeHtml = `
            <div class="flota-dash-card-val ${activeClassViaje}" id="live-viaje-${veh.id}" data-base-min="${veh.viaje_total_min || 0}" data-start-ms="${new Date().getTime()}" data-active="${!isEnPlanta ? 'true' : 'false'}">
                ${clockWidgetViaje}<span class="time-text">${viajeVal}</span>
            </div>
        `;

        const statusBadgeClass = isEnPlanta ? 'bg-success-subtle text-success border-success-subtle' : 'bg-warning-subtle text-warning border-warning-subtle';
        const statusBadgeLabel = isEnPlanta ? 'ESTACIONADO EN PLANTA' : 'EN DESPACHO';

        const btnText = isEnPlanta ? 'A DESPACHO' : 'REGISTRAR RETORNO';
        const btnClass = isEnPlanta ? 'btn-a-despacho' : 'btn-retorno';
        const btnIcon = isEnPlanta ? 'bi-box-arrow-right' : 'bi-arrow-left-circle';
        const dbTipo = isEnPlanta ? 'SALIDA' : 'ENTRADA';

        const activeNodePlanta = isEnPlanta ? 'active' : '';
        const activeNodeDespacho = !isEnPlanta ? 'active' : '';
        const activeRouteLine = !isEnPlanta ? 'active-despacho' : 'inactive-planta';

        let horaSalidaVal = veh.ciclo_salida_hora ? veh.ciclo_salida_hora.substring(0, 5) : 'Esperando...';
        let horaRetornoVal = veh.ciclo_retorno_hora ? veh.ciclo_retorno_hora.substring(0, 5) : (isEnPlanta ? 'En espera' : 'Esperando...');
        
        let subTextSalida = veh.ciclo_salida_fecha ? `Despachado: ${veh.ciclo_salida_fecha}` : 'Sin viaje activo';
        let subTextRetorno = veh.ciclo_retorno_fecha ? `Retornado: ${veh.ciclo_retorno_fecha}` : (isEnPlanta ? 'Pendiente de inicio' : 'Registra al presionar Retorno');

        const detailHtml = `
            <div class="flota-detail-panel estado-${veh.estado}">
                <div>
                    <div class="d-flex justify-content-between align-items-center mb-4">
                        <div>
                            <div class="small fw-bold text-muted text-uppercase" style="letter-spacing: 0.05em; font-size: 0.65rem;">DETALLES DEL VIAJE</div>
                            <div class="d-flex align-items-center gap-2 mt-1">
                                <span class="fw-bold text-dark" style="font-size: 1.05rem;">Secuencia de Viaje:</span>
                                ${renderPlacaPatente(veh.patente)}
                            </div>
                        </div>
                        <span class="badge border px-3 py-1.5 fw-extrabold ${statusBadgeClass}" style="font-size:0.7rem; border-radius:30px; letter-spacing:0.04em;">
                            <span class="d-inline-block rounded-circle me-1" style="width:7px; height:7px; background: currentColor; vertical-align: middle;"></span>
                            ${statusBadgeLabel}
                        </span>
                    </div>

                    <div class="lane-route-track">
                        <div class="route-line ${activeRouteLine}"></div>
                        <div class="route-node node-planta active">
                            <i class="bi bi-building" style="z-index: 2;"></i>
                            <span class="node-caption">Planta</span>
                        </div>
                        <div class="route-node node-despacho ${activeNodeDespacho}">
                            <i class="bi bi-shop" style="z-index: 2;"></i>
                            <span class="node-caption">Despacho</span>
                        </div>
                        <div class="route-truck-indicator">
                            <span class="truck-badge-top">${isEnPlanta ? 'EN PLANTA' : 'EN RUTA'}</span>
                            <div class="truck-bubble"><i class="bi bi-truck"></i></div>
                            <span class="truck-label-bottom">${veh.patente}</span>
                        </div>
                    </div>

                    <div class="flota-dash-cards">
                        <div class="flota-dash-card">
                            <div>
                                <span class="flota-dash-card-label"><i class="bi bi-box-arrow-right text-primary"></i> HORA DE SALIDA</span>
                                <span class="flota-dash-card-val">${horaSalidaVal}</span>
                            </div>
                            <span class="flota-dash-card-sub">${subTextSalida}</span>
                        </div>
                        <div class="flota-dash-card ${isEnPlanta ? 'active-estadia' : 'active-viaje'}">
                            <div>
                                <span class="flota-dash-card-label">
                                    <i class="bi bi-clock-history ${isEnPlanta ? 'text-success' : 'text-danger'}"></i> 
                                    ${isEnPlanta ? 'TIEMPO DE ESTADÍA' : 'TIEMPO TRANSCURRIDO'}
                                </span>
                                ${isEnPlanta ? estadiaHtml : viajeHtml}
                            </div>
                            <span class="flota-dash-card-sub">Precisión en segundos</span>
                        </div>
                        <div class="flota-dash-card">
                            <div>
                                <span class="flota-dash-card-label"><i class="bi bi-arrow-left-circle text-success"></i> HORA DE RETORNO</span>
                                <span class="flota-dash-card-val">${horaRetornoVal}</span>
                            </div>
                            <span class="flota-dash-card-sub">${subTextRetorno}</span>
                        </div>
                    </div>
                </div>

                <!-- Botón de Acción y Línea de Tiempo (Abajo del Panel) -->
                <div>
                    <div class="flota-action-btn-container">
                        <button class="flota-action-btn ${btnClass}" onclick="FlotaModule.marcar(${veh.id}, '${veh.patente}', '${veh.chofer_activo || ''}', '${dbTipo}')">
                            <i class="bi ${btnIcon}"></i> ${btnText}
                        </button>
                    </div>

                    <div class="mt-4 pt-3 border-top">
                        <div class="small fw-bold text-muted mb-2 text-uppercase" style="letter-spacing: 0.05em; font-size: 0.65rem;">MOVIMIENTOS DE HOY</div>
                        <div class="d-flex align-items-center gap-2 flex-wrap">
                            ${marcasHtml}
                        </div>
                    </div>
                </div>
            </div>
        `;

        layout.innerHTML = sidebarHtml + detailHtml;
    }

    function tickLiveClocks() {
        const nowMs = new Date().getTime();
        
        // Ticking Estadia (verde)
        document.querySelectorAll('.live-ticking-estadia').forEach(el => {
            if (el.getAttribute('data-active') === 'false') return;
            const baseMin = parseFloat(el.getAttribute('data-base-min') || '0');
            const startMs = parseFloat(el.getAttribute('data-start-ms') || '0');
            const elapsedMin = (nowMs - startMs) / 60000.0;
            const totalMin = baseMin + elapsedMin;
            
            const h = Math.floor(totalMin / 60);
            const m = Math.floor(totalMin % 60);
            const s = Math.floor((totalMin * 60) % 60);
            
            const timeTextEl = el.querySelector('.time-text');
            if (timeTextEl) {
                timeTextEl.textContent = `${h}h ${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`;
            }
        });
        
        // Ticking Viaje (rojo)
        document.querySelectorAll('.live-ticking-viaje').forEach(el => {
            if (el.getAttribute('data-active') === 'false') return;
            const baseMin = parseFloat(el.getAttribute('data-base-min') || '0');
            const startMs = parseFloat(el.getAttribute('data-start-ms') || '0');
            const elapsedMin = (nowMs - startMs) / 60000.0;
            const totalMin = baseMin + elapsedMin;
            
            const h = Math.floor(totalMin / 60);
            const m = Math.floor(totalMin % 60);
            const s = Math.floor((totalMin * 60) % 60);
            
            const timeTextEl = el.querySelector('.time-text');
            if (timeTextEl) {
                timeTextEl.textContent = `${h}h ${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`;
            }
        });
    }

    // ════════════════════════════════════════════════
    // MARCAR MOVIMIENTO (CON MODAL SWAL2)
    // ════════════════════════════════════════════════
    async function marcar(flotaId, patente, choferActivo = '', tipoMarca = null) {
        if (typeof Swal === 'undefined') {
            const obs = prompt("Ingrese observaciones / Chofer (Opcional):");
            if (obs === null) return; // canceló
            await ejecutarMarca(flotaId, obs, tipoMarca);
            return;
        }

        // Modal SweetAlert2 para Chofer y Observaciones
        Swal.fire({
            title: `📝 Registrar Marca: ${patente}`,
            html: `
                <div class="text-start">
                    <div class="mb-3">
                        <label class="form-label small fw-bold text-muted">Chofer del Vehículo</label>
                        <input type="text" id="swal-flota-chofer" class="form-control" placeholder="Ej: Juan Gómez" value="${choferActivo}">
                    </div>
                    <div class="mb-3">
                        <label class="form-label small fw-bold text-muted">Observaciones / Kilometraje</label>
                        <textarea id="swal-flota-obs" class="form-control" rows="2" placeholder="Ej: Kilometraje: 125,400. Carga completa."></textarea>
                    </div>
                </div>
            `,
            icon: 'info',
            showCancelButton: true,
            confirmButtonText: 'Confirmar Marca',
            cancelButtonText: 'Cancelar',
            preConfirm: () => {
                const chofer = document.getElementById('swal-flota-chofer').value.trim ? document.getElementById('swal-flota-chofer').value.trim() : document.getElementById('swal-flota-chofer').value;
                const obs = document.getElementById('swal-flota-obs').value.trim ? document.getElementById('swal-flota-obs').value.trim() : document.getElementById('swal-flota-obs').value;
                
                let observacionesFinal = "";
                if (chofer) observacionesFinal += `Chofer: ${chofer}. `;
                if (obs) observacionesFinal += obs;
                return observacionesFinal;
            }
        }).then(async (result) => {
            if (result.isConfirmed) {
                await ejecutarMarca(flotaId, result.value, tipoMarca);
            }
        });
    }

    async function ejecutarMarca(flotaId, observaciones, tipoMarca = null) {
        try {
            const res = await fetch('/api/flota/marcar/', {
                method: 'POST',
                headers: { 
                    'Authorization': `Bearer ${localStorage.getItem('token')}`, 
                    'Content-Type': 'application/json' 
                },
                body: JSON.stringify({ flota_id: flotaId, observaciones: observaciones, tipo: tipoMarca })
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Error al guardar la marca.');
            }
            const data = await res.json();
            
            const icon = data.tipo === 'ENTRADA' ? '🟢' : '🔴';
            if (typeof showToast === 'function') {
                showToast(`${icon} ${data.tipo_label}: ${data.patente} registrado a las ${data.hora.substring(0,5)}`, 'success');
            } else {
                Swal.fire('Registrado!', `${icon} ${data.tipo_label} guardado.`, 'success');
            }
            await cargarEstadoDia();
        } catch (e) {
            console.error(e);
            Swal.fire('Error', e.message, 'error');
        }
    }

    // ════════════════════════════════════════════════
    // CONSULTAR HISTORIAL
    // ════════════════════════════════════════════════
    async function cargarHistorial(page = 1) {
        const desde = document.getElementById('flota-hist-desde')?.value;
        const hasta = document.getElementById('flota-hist-hasta')?.value;
        const patente = document.getElementById('flota-hist-patente')?.value;
        
        const tbody = document.getElementById('flota-historial-tbody');
        const pagDiv = document.getElementById('flota-historial-pagination');
        if (!desde || !hasta) {
            if (typeof showToast === 'function') showToast('Seleccione rango de fechas', 'warning');
            return;
        }
        tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4"><div class="spinner-border spinner-border-sm text-primary"></div></td></tr>';

        try {
            let url = `/api/flota/historial/?desde=${desde}&hasta=${hasta}&page=${page}`;
            if (patente) url += `&patente=${encodeURIComponent(patente)}`;
            
            const res = await fetch(url, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });
            if (!res.ok) throw new Error("Error al consultar el historial");
            const data = await res.json();

            if (!data.registros.length) {
                tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">No hay registros de movimientos en el rango seleccionado.</td></tr>';
                pagDiv.innerHTML = '';
                return;
            }

            tbody.innerHTML = data.registros.map(r => {
                const f = r.fecha.split('-');
                const meses = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
                const fechaFmt = `${parseInt(f[2])} ${meses[parseInt(f[1])]} ${f[0]}`;
                const labelClass = r.tipo === 'ENTRADA' ? 'badge bg-success-subtle text-success border border-success-subtle' : 'badge bg-danger-subtle text-danger border border-danger-subtle';
                
                return `<tr>
                    <td style="font-weight:500; color:#475569; white-space:nowrap">${fechaFmt}</td>
                    <td style="color:#475569">${r.hora.substring(0,5)}</td>
                    <td>${renderPlacaPatente(r.patente)}</td>
                    <td style="color:#64748b; font-size:0.78rem">${r.area_nombre}</td>
                    <td><span class="${labelClass} px-2 py-1">${r.tipo}</span></td>
                    <td style="color:#64748b">${r.registrado_por_nombre || 'Sistema'}</td>
                    <td style="color:#475569; font-size:0.78rem; max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap" title="${r.observaciones || ''}">${r.observaciones || '—'}</td>
                </tr>`;
            }).join('');

            if (data.pages > 1) {
                let p = `<span>Mostrando página ${data.page} de ${data.pages} (${data.total} registros)</span><div class="d-flex gap-1">`;
                for (let i = 1; i <= Math.min(data.pages, 5); i++) {
                    const cls = i === data.page ? 'btn-primary' : 'btn-outline-secondary';
                    p += `<button class="btn btn-sm ${cls}" style="min-width:30px; font-size:0.75rem; padding:2px 8px; border-radius:4px" onclick="FlotaModule.cargarHistorial(${i})">${i}</button>`;
                }
                p += '</div>';
                pagDiv.innerHTML = p;
            } else {
                pagDiv.innerHTML = `<span>Total: ${data.total} registro(s)</span>`;
            }
        } catch (e) {
            console.error(e);
            tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-danger">Error al cargar historial desde la base de datos</td></tr>';
        }
    }

    // ════════════════════════════════════════════════
    // CONFIG TAB (ADMIN CRUD DE CAMIONES)
    // ════════════════════════════════════════════════
    async function initAdminTab() {
        injectStyles();
        const container = document.getElementById('flota-config-container');
        if (!container) return;

        container.innerHTML = `
            <div class="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h4 class="mb-1 fw-bold text-dark"><i class="bi bi-truck text-secondary me-2"></i>Catálogo de Flota Aguacol</h4>
                    <p class="text-muted mb-0 small">Gestione los vehículos oficiales autorizados de la empresa y asócielos a sus áreas respectivas.</p>
                </div>
                <div class="d-flex gap-2">
                    <button class="btn btn-primary shadow-sm fw-bold" onclick="FlotaModule.abrirModalVehiculo()">
                        <i class="bi bi-plus-circle me-1"></i> Registrar Vehículo
                    </button>
                    <button class="btn btn-light shadow-sm" onclick="FlotaModule.cargarVehiculosAdmin()">
                        <i class="bi bi-arrow-clockwise text-primary"></i> Actualizar
                    </button>
                </div>
            </div>
            <div class="table-responsive shadow-sm border rounded" style="background:#fff;">
                <table class="table mb-0 align-middle">
                    <thead class="table-light">
                        <tr>
                            <th class="ps-4 py-3">Patente</th>
                            <th class="py-3">Área Asignada</th>
                            <th class="py-3">Fecha Registro</th>
                            <th class="py-3">Estado</th>
                            <th class="pe-4 py-3 text-end">Acciones</th>
                        </tr>
                    </thead>
                    <tbody id="flota-admin-tbody">
                        <tr><td colspan="5" class="text-center py-5 text-muted"><div class="spinner-border text-primary spinner-border-sm"></div> Cargando vehículos...</td></tr>
                    </tbody>
                </table>
            </div>
        `;

        await cargarVehiculosAdmin();
    }

    async function cargarVehiculosAdmin() {
        const tbody = document.getElementById('flota-admin-tbody');
        if (!tbody) return;

        try {
            const res = await fetch('/api/flota/maestro/', {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });
            if (!res.ok) throw new Error("Error al obtener catálogo");
            const data = await res.json();

            if (!data.length) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-center py-5 text-muted">No hay vehículos registrados en el catálogo de flota.</td></tr>';
                return;
            }

            const canEdit = typeof AuthService !== 'undefined' ? AuthService.hasPermission('configuracion.flota') : true;

            tbody.innerHTML = data.map(v => {
                const f = v.created_at ? v.created_at.split(' ')[0].split('-') : null;
                const fechaFmt = f ? `${f[2]}/${f[1]}/${f[0]}` : '—';
                const statusBadge = v.activo ? '<span class="badge bg-success-subtle text-success border border-success-subtle">Activo</span>' : '<span class="badge bg-danger-subtle text-danger border border-danger-subtle">Inactivo</span>';

                return `
                    <tr>
                        <td class="ps-4">${renderPlacaPatente(v.patente)}</td>
                        <td class="text-secondary fw-semibold">${v.area_nombre}</td>
                        <td class="text-muted small">${fechaFmt}</td>
                        <td>${statusBadge}</td>
                        <td class="pe-4 text-end">
                            ${canEdit ? `
                                <button class="btn btn-sm btn-outline-primary border-0 me-1" onclick="FlotaModule.abrirModalVehiculo(${v.id}, '${v.patente}', ${v.area_id})" title="Editar">
                                    <i class="bi bi-pencil-square"></i>
                                </button>
                                <button class="btn btn-sm btn-outline-danger border-0" onclick="FlotaModule.eliminarVehiculo(${v.id}, '${v.patente}')" title="Eliminar">
                                    <i class="bi bi-trash"></i>
                                </button>
                            ` : '—'}
                        </td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            console.error(e);
            tbody.innerHTML = '<tr><td colspan="5" class="text-center py-5 text-danger fw-bold">Error al cargar vehículos desde la base de datos central.</td></tr>';
        }
    }

    async function abrirModalVehiculo(id = null, patente = '', areaId = null) {
        // Cargar áreas con cache local y vehículos activos para validación de duplicados
        let areas = [];
        let vehiculosExistentes = [];
        try {
            if (_catalogoAreasCached.length > 0) {
                areas = _catalogoAreasCached;
            } else {
                const res = await fetch('/api/configuracion/areas/', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                });
                if (res.ok) {
                    areas = await res.json();
                    _catalogoAreasCached = areas;
                }
            }
            
            // Cargar maestro de vehículos para validación de duplicados en tiempo real
            const resMaestro = await fetch('/api/flota/maestro/', {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });
            if (resMaestro.ok) {
                vehiculosExistentes = await resMaestro.json();
            }
        } catch (error) {
            console.error("Error al obtener datos para catálogo:", error);
        }

        // Filtrar áreas que tengan aplica_flota == 1
        const areasFiltradas = areas.filter(a => a.aplica_flota === 1);

        if (areasFiltradas.length === 0) {
            Swal.fire({
                title: '⚠️ Sin áreas configuradas',
                html: 'Antes de registrar un vehículo, debes habilitar al menos un área para flota.<br><br>Ve a la pestaña de <b>Áreas</b> y activa la casilla <b>"Aplica para Flota"</b> en el área que desees.',
                icon: 'warning',
                confirmButtonText: 'Entendido'
            });
            return;
        }

        const optionsHtml = areasFiltradas.map(a => `
            <option value="${a.id}" ${areaId === a.id ? 'selected' : ''}>${a.nombre}</option>
        `).join('');

        const titulo = id ? '✏️ Editar Vehículo' : '🚛 Registrar Vehículo en Flota';
        
        Swal.fire({
            title: titulo,
            html: `
                <div class="text-start">
                    <div class="mb-3">
                        <label class="form-label small fw-bold text-muted">Patente del Vehículo</label>
                        <input type="text" id="swal-vehiculo-patente" class="form-control text-uppercase font-monospace" placeholder="Ej: ABCD12" value="${patente}">
                        <div id="swal-vehiculo-patente-error" class="text-danger small mt-1 d-none" style="font-weight: 600;"></div>
                        <div class="form-text text-muted small">Forzado automáticamente a mayúsculas y sin espacios.</div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label small fw-bold text-muted">Área de la Empresa</label>
                        <select id="swal-vehiculo-area" class="form-select">
                            ${optionsHtml}
                        </select>
                    </div>
                </div>
            `,
            showCancelButton: true,
            confirmButtonText: id ? 'Guardar Cambios' : 'Registrar',
            cancelButtonText: 'Cancelar',
            didOpen: () => {
                const inputPatente = document.getElementById('swal-vehiculo-patente');
                const errorDiv = document.getElementById('swal-vehiculo-patente-error');
                const confirmBtn = Swal.getConfirmButton();
                
                const validarPatenteRealtime = () => {
                    const pat = inputPatente.value.replace(/\s+/g, '').toUpperCase();
                    if (!pat) {
                        errorDiv.classList.add('d-none');
                        confirmBtn.disabled = false;
                        return;
                    }
                    
                    // Si estamos editando y coincide con la patente inicial
                    if (id && pat === patente.toUpperCase().replace(/\s+/g, '')) {
                        errorDiv.classList.add('d-none');
                        confirmBtn.disabled = false;
                        return;
                    }
                    
                    const duplicado = vehiculosExistentes.find(v => v.patente === pat && v.id !== id);
                    if (duplicado) {
                        errorDiv.textContent = `⚠️ La patente ${pat} ya está registrada en: ${duplicado.area_nombre}.`;
                        errorDiv.classList.remove('d-none');
                        confirmBtn.disabled = true;
                    } else {
                        errorDiv.classList.add('d-none');
                        confirmBtn.disabled = false;
                    }
                };
                
                inputPatente.addEventListener('input', validarPatenteRealtime);
                inputPatente.addEventListener('change', validarPatenteRealtime);
            },
            preConfirm: () => {
                const pat = document.getElementById('swal-vehiculo-patente').value.strip ? document.getElementById('swal-vehiculo-patente').value.strip() : document.getElementById('swal-vehiculo-patente').value;
                const area = document.getElementById('swal-vehiculo-area').value;
                
                if (!pat) {
                    Swal.showValidationMessage('La patente es requerida');
                    return false;
                }
                
                const cleanedPat = pat.replace(/\s+/g, '').toUpperCase();
                
                // Validación de duplicado final antes de enviar
                const duplicado = vehiculosExistentes.find(v => v.patente === cleanedPat && v.id !== id);
                if (duplicado) {
                    Swal.showValidationMessage(`La patente ${cleanedPat} ya está registrada en: ${duplicado.area_nombre}`);
                    return false;
                }
                
                return { patente: cleanedPat, area_id: parseInt(area) };
            }
        }).then(async (result) => {
            if (result.isConfirmed) {
                const { patente, area_id } = result.value;
                try {
                    const url = id ? `/api/flota/maestro/${id}/` : '/api/flota/maestro/';
                    const method = id ? 'PUT' : 'POST';
                    
                    const response = await fetch(url, {
                        method: method,
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${localStorage.getItem('token')}`
                        },
                        body: JSON.stringify({ patente, area_id })
                    });
                    
                    if (!response.ok) {
                        const err = await response.json();
                        throw new Error(err.detail || 'Error al guardar el vehículo');
                    }
                    
                    if(typeof showToast === 'function') {
                        showToast(id ? "Vehículo actualizado exitosamente." : "Vehículo registrado en la flota.", "success");
                    }
                    await cargarVehiculosAdmin();
                } catch (error) {
                    console.error(error);
                    Swal.fire('Error', error.message, 'error');
                }
            }
        });
    }

    async function eliminarVehiculo(id, patente) {
        Swal.fire({
            title: `¿Eliminar vehículo ${patente}?`,
            text: "Esta acción desactivará el vehículo del catálogo de flota. No se perderá el historial de marcas previas.",
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#6c757d',
            confirmButtonText: 'Sí, eliminar',
            cancelButtonText: 'Cancelar'
        }).then(async (result) => {
            if (result.isConfirmed) {
                try {
                    const response = await fetch(`/api/flota/maestro/${id}/`, {
                        method: 'DELETE',
                        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                    });
                    
                    if (!response.ok) {
                        const err = await response.json();
                        throw new Error(err.detail || 'Error al eliminar el vehículo');
                    }
                    
                    if(typeof showToast === 'function') {
                        showToast("Vehículo eliminado del catálogo.", "success");
                    }
                    await cargarVehiculosAdmin();
                } catch (error) {
                    console.error(error);
                    Swal.fire('Error', error.message, 'error');
                }
            }
        });
    }

    function destroy() {
        if (_refreshInterval) {
            clearInterval(_refreshInterval);
            _refreshInterval = null;
        }
        if (_tickingInterval) {
            clearInterval(_tickingInterval);
            _tickingInterval = null;
        }
        _catalogoAreasCached = [];
        _vehiculosCache = [];
        _selectedVehiculoId = null;
    }

    return { 
        initTab, 
        cargarEstadoDia, 
        marcar, 
        cargarHistorial, 
        initAdminTab, 
        cargarVehiculosAdmin, 
        abrirModalVehiculo, 
        eliminarVehiculo, 
        destroy,
        selectVehiculo
    };
})();
