/**
 * Módulo Flota Aguacol — Control de Ingreso/Salida Vehicular
 * Diseño Enterprise inspirado en Stitch/Stripe/Linear
 */
const FlotaModule = (() => {
    let _refreshInterval = null;
    let _tickingInterval = null;
    let _catalogoAreasCached = []; // Cache local para evitar llamadas repetidas
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
                font-family: var(--font-sans);
                font-size: 0.75rem;
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
                font-size: 0.75rem;
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
            }            /* Línea de tiempo de Flota estilo Gantt */
            .flota-gantt-container {
                position: relative;
                padding: 68px 24px;
                background-color: #fafbfc;
                background-image: radial-gradient(#cbd5e1 1.2px, transparent 1.2px);
                background-size: 20px 20px;
                border-radius: 16px;
                margin: 24px 0 28px 0;
                border: 1px solid #e2e8f0;
                min-height: 154px;
            }
            .flota-gantt-backdrop {
                position: relative;
                height: 22px;
                width: 100%;
                margin: 10px 0;
            }
            .flota-gantt-track {
                height: 14px;
                background: #e2e8f0;
                border-radius: 7px;
                position: absolute;
                top: 2px;
                left: 0;
                width: 100%;
                overflow: hidden;
                display: flex;
                box-shadow: inset 0 1px 2px rgba(0,0,0,0.06);
                border: 1px solid #cbd5e1;
            }
            .flota-gantt-segment {
                height: 100%;
                position: absolute;
                background: linear-gradient(180deg, #10b981 0%, #059669 100%);
                border-right: 1px solid rgba(255,255,255,0.2);
                border-left: 1px solid rgba(255,255,255,0.2);
                transition: all 0.3s ease;
            }
            .flota-gantt-segment.ongoing {
                background: repeating-linear-gradient(45deg, #10b981, #10b981 8px, #34d399 8px, #34d399 16px);
                border-right: none;
            }
            .flota-gantt-grid-line {
                position: absolute;
                top: 0;
                bottom: 0;
                width: 1px;
                background: rgba(148, 163, 184, 0.15);
                z-index: 1;
            }
            .flota-gantt-grid-label {
                position: absolute;
                font-size: 0.75rem;
                font-weight: 700;
                color: #94a3b8;
                top: -16px;
                transform: translateX(-50%);
                font-family: 'JetBrains Mono', monospace;
            }
            @media (max-width: 768px) {
                .flota-gantt-grid-label.h-sub {
                    display: none !important;
                }
            }
            .flota-gantt-marker {
                position: absolute;
                top: 9px;
                display: flex;
                align-items: center;
                z-index: 3;
            }
            .flota-gantt-marker.dir-down {
                flex-direction: column;
            }
            .flota-gantt-marker.dir-up {
                flex-direction: column-reverse;
                transform: translateY(-100%);
                margin-top: 10px;
            }
            .flota-gantt-dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                border: 2px solid #ffffff;
                box-shadow: 0 1px 3px rgba(0,0,0,0.15);
            }
            .flota-gantt-dot.e {
                background-color: #10b981;
            }
            .flota-gantt-dot.s {
                background-color: #f43f5e;
            }
            .flota-gantt-marker-line {
                width: 1.5px;
                background-color: #cbd5e1;
                z-index: 1;
            }
            .flota-gantt-marker.level-1 .flota-gantt-marker-line {
                height: 10px;
            }
            .flota-gantt-marker.level-2 .flota-gantt-marker-line {
                height: 22px;
            }
            .flota-gantt-marker.level-3 .flota-gantt-marker-line {
                height: 34px;
            }
            .flota-gantt-bubble {
                font-family: var(--font-sans);
                font-size: 0.75rem;
                font-weight: 600;
                white-space: nowrap;
                padding: 4px 8px;
                border-radius: 8px;
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 2px;
                z-index: 2;
                box-shadow: 0 4px 10px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02);
                backdrop-filter: blur(8px);
                -webkit-backdrop-filter: blur(8px);
                transition: all 0.2s ease;
            }
            .flota-gantt-bubble.e {
                background-color: rgba(240, 253, 244, 0.95);
                color: #16a34a;
                border: 1px solid rgba(134, 239, 172, 0.5);
            }
            .flota-gantt-bubble.s {
                background-color: rgba(254, 242, 242, 0.95);
                color: #dc2626;
                border: 1px solid rgba(254, 202, 202, 0.5);
            }
            .flota-gantt-bubble .bubble-label {
                font-size: 0.75rem;
                font-weight: 500;
                opacity: 0.85;
                text-transform: uppercase;
                letter-spacing: 0.03em;
                display: flex;
                align-items: center;
                gap: 4px;
            }
            .flota-gantt-bubble .bubble-time {
                font-family: 'JetBrains Mono', monospace;
                font-size: 0.75rem;
                font-weight: 700;
            }
            .flota-gantt-pulse-ring {
                position: absolute;
                top: 9px;
                transform: translate(-50%, -50%);
                width: 18px;
                height: 18px;
                border-radius: 50%;
                border: 2px solid #10b981;
                animation: gantt-ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;
                pointer-events: none;
                z-index: 2;
            }
            .flota-gantt-empty-text {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                font-size: 0.75rem;
                font-weight: 600;
                color: #64748b;
                font-style: italic;
                z-index: 2;
                pointer-events: none;
            }
            .flota-gantt-track.empty {
                background: repeating-linear-gradient(-45deg, #f1f5f9, #f1f5f9 6px, #e2e8f0 6px, #e2e8f0 12px);
                border: 1px dashed #cbd5e1;
            }     }

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
                font-size: 0.75rem;
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
                font-size: 0.75rem;
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
                font-family: var(--font-sans);
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

            /* Segmented Control / Switcher por Área */
            .flota-segmented-control {
                display: flex;
                background: #f1f5f9;
                border-radius: 10px;
                padding: 3px;
                border: 1px solid #e2e8f0;
                margin-bottom: 12px;
            }
            .flota-segmented-button {
                flex: 1;
                border: none;
                background: none;
                font-size: 0.75rem;
                font-weight: 700;
                color: #64748b;
                padding: 6px 4px;
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
                text-align: center;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .flota-segmented-button:hover {
                color: #0f172a;
            }
            .flota-segmented-button.active {
                background: #ffffff;
                color: #2563eb;
                box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
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
    // PORTERÍA › FLOTA — diseño B (02-11-2026): vehículos a la izquierda y el día del vehículo elegido a la derecha
    // ════════════════════════════════════════════════
    const _DIAS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
    let _fecha = _hoy(), _datos = null, _error = null, _preguntando = false, _oyentes = false;
    function _pad(n) { return (n < 10 ? '0' : '') + n; }
    function _hoy() { const d = new Date(); return d.getFullYear() + '-' + _pad(d.getMonth() + 1) + '-' + _pad(d.getDate()); }
    function _fechaDe(x) { return new Date(x + 'T12:00:00'); }
    function _sumar(x, n) { const d = _fechaDe(x); d.setDate(d.getDate() + n); return d.getFullYear() + '-' + _pad(d.getMonth() + 1) + '-' + _pad(d.getDate()); }
    function _dmy(x) { return x ? String(x).slice(0, 10).split('-').reverse().join('-') : ''; }
    function _esc(t) { return window.FichaCfg ? FichaCfg.esc(t) : String(t == null ? '' : t); }
    function _min(h) { if (!h) return null; const p = String(h).split(':'); return parseInt(p[0], 10) * 60 + parseInt(p[1], 10); }
    function _hhmm(m) { m = Math.floor(m) % 1440; return _pad(Math.floor(m / 60)) + ':' + _pad(m % 60); }
    function _ahora() { const d = new Date(); return d.getHours() * 60 + d.getMinutes(); }
    function _dur(m) { m = Math.max(0, Math.round(m || 0)); return Math.floor(m / 60) + 'h ' + _pad(m % 60) + 'm'; }
    function _aviso(m, t) { if (typeof showToast === 'function') showToast(m, t || 'success'); }
    function _patente(p) {
        const t = String(p || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
        if (/^[A-Z]{4}[0-9]{2}$/.test(t)) return t.slice(0, 2) + ' ' + t.slice(2, 4) + ' ' + t.slice(4);
        if (/^[A-Z]{2}[0-9]{4}$/.test(t)) return t.slice(0, 2) + ' ' + t.slice(2, 4) + ' ' + t.slice(4);
        return t;
    }
    function _cont() { return document.getElementById('flota-container'); }
    function _viajes(v, esHoy) {
        // Un viaje es una SALIDA seguida de su ENTRADA; hoy, una SALIDA sin regreso cuenta hasta ahora
        const m = v.marcas || [], t = [];
        for (let i = 0; i < m.length; i++) {
            if (m[i].tipo !== 'SALIDA') continue;
            const ini = _min(m[i].hora);
            if (m[i + 1] && m[i + 1].tipo === 'ENTRADA') { let fin = _min(m[i + 1].hora); if (fin < ini) fin += 1440; t.push([ini, fin, false]); i++; }
            else if (i === m.length - 1 && esHoy) t.push([ini, Math.max(_ahora(), ini), true]);
        }
        // Volvió hoy de un viaje que empezó otro día: el tramo va desde el comienzo del día
        if (m.length && m[0].tipo === 'ENTRADA' && v.ciclo_salida_fecha && v.ciclo_salida_fecha < _fecha) t.unshift([0, _min(m[0].hora), false]);
        if (!m.length && v.estado === 'fuera' && esHoy) t.push([0, _ahora(), true]);
        return t;
    }

    async function initTab() {
        const c = _cont();
        if (!c) return;
        if (!_oyentes) {
            _oyentes = true;
            c.addEventListener('click', _alHacerClic);
            c.addEventListener('change', function (ev) { if (ev.target && ev.target.id === 'fl-fecha') _cambiarDia(ev.target.value); });
        }
        if (!_datos) _fecha = _hoy();
        _pintar();
        await cargarEstadoDia();
        if (_refreshInterval) clearInterval(_refreshInterval);
        _refreshInterval = setInterval(function () {
            const pane = document.getElementById('tab-flota-aguacol');
            if (!pane || !pane.classList.contains('active') || document.visibilityState !== 'visible') return;
            if (_preguntando || _fecha !== _hoy()) return;
            cargarEstadoDia();
        }, 60000);
    }

    function _navDia() {
        const esHoy = _fecha === _hoy();
        return '<div class="ptB-dia" role="group" aria-label="Día">'
            + '<button type="button" data-fl-dia="-1" aria-label="Día anterior"><i class="bi bi-chevron-left" aria-hidden="true"></i></button>'
            + '<span>' + _DIAS[_fechaDe(_fecha).getDay()] + '</span>'
            + '<input type="date" id="fl-fecha" value="' + _fecha + '" max="' + _hoy() + '" aria-label="Elegir día">'
            + '<button type="button" data-fl-dia="1" aria-label="Día siguiente"' + (esHoy ? ' disabled' : '') + '><i class="bi bi-chevron-right" aria-hidden="true"></i></button></div>'
            + (esHoy ? '' : '<button type="button" class="fcB-btn" data-fl-hoy>Hoy</button>');
    }

    function _pintar() {
        const c = _cont();
        if (!c || !window.FichaCfg) return;
        if (_error && !_datos) {
            c.innerHTML = '<div class="fcB"><p class="fcB-vacio">' + _esc(_error) + ' <button type="button" class="fcB-btn" data-fl-recargar>Reintentar</button></p></div>';
            return;
        }
        const esHoy = _fecha === _hoy(), vs = ((_datos && _datos.vehiculos) || []).slice().sort(function (a, b) { return String(a.patente).localeCompare(String(b.patente)); });
        const st = (_datos && _datos.stats) || {};
        FichaCfg.montar(c, {
            clave: 'flota',
            titulo: 'Flota',
            descripcion: (_datos ? vs.length + (vs.length === 1 ? ' vehículo' : ' vehículos') + (esHoy ? ': ' + (st.en_planta || 0) + ' en planta y ' + (st.en_viaje || 0) + ' en viaje. ' : '. ') : '')
                + 'Elija un vehículo para ver sus viajes del día y registrar su SALIDA o su ENTRADA.',
            acciones: _navDia(),
            buscar: 'Buscar patente o área',
            items: vs,
            id: function (v) { return v.id; },
            etiqueta: function (v) { return _patente(v.patente); },
            detalle: function (v) { return [v.area, v.estado === 'fuera' && v.chofer_activo ? 'Chofer: ' + v.chofer_activo : ''].filter(Boolean).join(' · '); },
            estado: esHoy ? function (v) { return v.estado === 'fuera' ? { t: 'En viaje', tono: 'fuera' } : { t: 'En planta', tono: 'si' }; } : null,
            sub: function (v) {
                const n = v.viajes_completados || 0;
                if (esHoy && v.estado === 'fuera' && v.ciclo_salida_hora) return 'salió ' + (v.ciclo_salida_fecha && v.ciclo_salida_fecha !== _fecha ? _dmy(v.ciclo_salida_fecha).slice(0, 5) + ' ' : '') + String(v.ciclo_salida_hora).slice(0, 5);
                return n ? n + (n === 1 ? ' viaje' : ' viajes') : (esHoy ? '' : 'Sin viajes');
            },
            vacio: _datos ? 'No hay vehículos en la flota. Se agregan en Configuración › Flota Aguacol.' : 'Cargando…',
            ficha: _ficha
        });
    }

    function _linea(t) {
        if (!t.length) return '';
        const ini = Math.min(6 * 60, Math.floor(t[0][0] / 60) * 60), fin = Math.max(22 * 60, Math.ceil(t[t.length - 1][1] / 60) * 60), w = fin - ini;
        const segs = t.map(function (x) {
            return '<span class="ptB-seg viaje' + (x[2] ? ' abierto' : '') + '" style="left:' + ((x[0] - ini) / w * 100).toFixed(2) + '%;width:' + Math.max(0.6, (x[1] - x[0]) / w * 100).toFixed(2) + '%"'
                + ' title="En viaje: ' + _hhmm(x[0]) + ' a ' + (x[2] ? 'ahora' : _hhmm(x[1])) + '"></span>';
        }).join('');
        let reg = '';
        for (let h = Math.ceil(ini / 60) + 2; h < fin / 60; h += 2) reg += '<span style="left:' + ((h * 60 - ini) / w * 100).toFixed(2) + '%">' + _pad(h % 24) + ':00</span>';
        return '<div class="ptB-linea" role="img" aria-label="En viaje: ' + _esc(t.map(function (x) { return _hhmm(x[0]) + ' a ' + (x[2] ? 'ahora' : _hhmm(x[1])); }).join(', ')) + '"><span class="ptB-pista"></span>' + segs + '</div>'
            + '<div class="ptB-reglas" aria-hidden="true">' + reg + '</div>';
    }

    function _ficha(v, panel) {
        const F = FichaCfg, esHoy = _fecha === _hoy(), m = v.marcas || [], fuera = v.estado === 'fuera';
        const t = _viajes(v, esHoy), enViaje = t.reduce(function (a, x) { return a + (x[1] - x[0]); }, 0);
        let accion;
        if (esHoy) {
            accion = fuera
                ? '<button type="button" class="fcB-btn ok" data-fl-marcar="' + v.id + '" data-tipo="ENTRADA"><i class="bi bi-box-arrow-in-left" aria-hidden="true"></i>Registrar ENTRADA (regreso)</button>'
                : '<button type="button" class="fcB-btn pri" data-fl-marcar="' + v.id + '" data-tipo="SALIDA"><i class="bi bi-box-arrow-right" aria-hidden="true"></i>Registrar SALIDA (despacho)</button>';
        } else {
            accion = '<button type="button" class="fcB-btn" data-fl-hoy>Ir a hoy para registrar</button>';
        }
        let h = F.cabeza(_patente(v.patente), v.area || '', accion);
        if (esHoy && fuera) {
            const sal = v.ciclo_salida_hora ? (v.ciclo_salida_fecha && v.ciclo_salida_fecha !== _fecha ? 'el ' + _dmy(v.ciclo_salida_fecha) + ' ' : 'hoy ') + 'a las ' + String(v.ciclo_salida_hora).slice(0, 5) : '';
            h += '<div class="ptB-aviso"><i class="bi bi-truck" aria-hidden="true"></i><div><b>En viaje' + (v.chofer_activo ? ' con ' + _esc(v.chofer_activo) : '') + '</b>'
                + (sal ? '<span>Salió ' + _esc(sal) + '</span>' : '') + '</div></div>';
        }
        h += '<div class="ptB-cifras"><div><small>Estado' + (esHoy ? '' : ' al final del día') + '</small><b>' + (fuera ? 'En viaje' : 'En planta') + '</b></div>'
            + '<div><small>Viajes completados</small><b class="num">' + (v.viajes_completados || 0) + '</b></div>'
            + '<div><small>Tiempo en viaje' + (esHoy && fuera ? ' (hasta ahora)' : '') + '</small><b class="num">' + _dur(enViaje) + '</b></div></div>';
        const dia = _DIAS[_fechaDe(_fecha).getDay()].toLowerCase() + ' ' + _dmy(_fecha);
        if (t.length) h += F.seccion('Viajes del ' + dia) + _linea(t);
        h += F.seccion('Marcas del ' + dia)
            + (m.length ? '<div class="ptB-marcas">' + m.map(function (x) {
                return '<div class="ptB-marca"><span class="ptB-mov ' + (x.tipo === 'ENTRADA' ? 'e' : 's') + '">' + (x.tipo === 'ENTRADA' ? 'ENTRADA' : 'SALIDA') + '</span><b class="num">' + _esc(String(x.hora).slice(0, 5)) + '</b>'
                    + '<small>' + (x.registrado_por_nombre ? 'Registró ' + _esc(x.registrado_por_nombre) : '&nbsp;') + '</small>'
                    + (x.observaciones ? '<small class="obs">' + _esc(x.observaciones) + '</small>' : '') + '</div>';
            }).join('') + '</div>'
            : '<p class="fcB-nota">' + (esHoy ? 'Todavía no tiene marcas hoy.' : 'No tuvo marcas este día.') + '</p>');
        panel.innerHTML = h;
    }

    async function cargarEstadoDia() {
        try {
            const res = await fetch('/api/flota/estado-dia/?fecha=' + _fecha, { headers: { 'Authorization': 'Bearer ' + localStorage.getItem('access_token') } });
            if (!res.ok) { let m = 'No se pudo leer la flota.'; try { m = (await res.json()).detail || m; } catch (_) {} throw new Error(m); }
            _datos = await res.json();
            _vehiculosCache = _datos.vehiculos || [];
            _error = null;
        } catch (e) {
            _error = e.message;
            if (_datos) _aviso(e.message, 'danger');
        }
        _pintar();
    }

    async function _cambiarDia(x) {
        if (!x) return;
        _fecha = x > _hoy() ? _hoy() : x;
        _datos = null;
        _pintar();
        await cargarEstadoDia();
    }

    function _alHacerClic(ev) {
        const b = ev.target.closest('button');
        if (!b || !_cont().contains(b)) return;
        if (b.dataset.flDia) { _cambiarDia(_sumar(_fecha, parseInt(b.dataset.flDia, 10))); return; }
        if (b.hasAttribute('data-fl-hoy')) { _cambiarDia(_hoy()); return; }
        if (b.hasAttribute('data-fl-recargar')) { cargarEstadoDia(); return; }
        if (b.dataset.flMarcar) {
            const v = ((_datos && _datos.vehiculos) || []).find(function (x) { return String(x.id) === b.dataset.flMarcar; });
            if (v) marcar(v.id, v.patente, v.chofer_activo || '', b.dataset.tipo);
        }
    }

    // ════════════════════════════════════════════════
    // MARCAR MOVIMIENTO (chofer y observaciones en la ventana de siempre)
    // ════════════════════════════════════════════════
    async function marcar(flotaId, patente, choferActivo = '', tipoMarca = null) {
        const tipo = tipoMarca === 'ENTRADA' ? 'ENTRADA' : 'SALIDA';
        const d = new Date();
        _preguntando = true;
        let r;
        try {
            r = await Swal.fire({
                title: '¿Registrar la ' + tipo + '?',
                html: '<div class="av-quien">' + _esc(_patente(patente)) + '</div><div class="ptB-sw">'
                    + '<p>' + (tipo === 'SALIDA' ? 'Sale a despacho' : 'Regresa a planta') + ' · hora ' + _pad(d.getHours()) + ':' + _pad(d.getMinutes()) + '</p>'
                    + '<label for="swal-flota-chofer">Chofer</label><input type="text" id="swal-flota-chofer" class="form-control" placeholder="Nombre del chofer" value="' + _esc(choferActivo) + '">'
                    + '<label for="swal-flota-obs">Observaciones o kilometraje</label><textarea id="swal-flota-obs" class="form-control" rows="2" placeholder="Opcional"></textarea></div>',
                showCancelButton: true, reverseButtons: true, focusConfirm: false,
                confirmButtonText: 'Registrar ' + tipo, cancelButtonText: 'Cancelar',
                customClass: { confirmButton: 'av-btn av-btn-pri' },
                preConfirm: function () {
                    const chofer = document.getElementById('swal-flota-chofer').value.trim(), obs = document.getElementById('swal-flota-obs').value.trim();
                    return (chofer ? 'Chofer: ' + chofer + '. ' : '') + obs;
                }
            });
        } finally { _preguntando = false; }
        if (r && r.isConfirmed) await ejecutarMarca(flotaId, r.value || '', tipo);
    }

    async function ejecutarMarca(flotaId, observaciones, tipoMarca = null) {
        try {
            const res = await fetch('/api/flota/marcar/', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + localStorage.getItem('access_token'), 'Content-Type': 'application/json' },
                body: JSON.stringify({ flota_id: flotaId, observaciones: observaciones, tipo: tipoMarca })
            });
            const data = await res.json().catch(function () { return {}; });
            if (!res.ok) throw new Error(data.detail || 'No se pudo registrar.');
            _aviso((data.tipo === 'ENTRADA' ? 'ENTRADA' : 'SALIDA') + ' registrada: ' + _patente(data.patente) + (data.hora ? ' a las ' + String(data.hora).substring(0, 5) : ''));
        } catch (e) {
            _aviso(e.message || 'No se pudo registrar.', 'danger');
        }
        await cargarEstadoDia();
    }

    // ════════════════════════════════════════════════
    // CONFIG TAB (ADMIN CRUD DE CAMIONES)
    // ════════════════════════════════════════════════
    // Configuración › Flota Aguacol con el diseño B (01-11-2026): patentes a la izquierda y la ficha del vehículo a la derecha.
    async function initAdminTab() {
        injectStyles();
        await cargarVehiculosAdmin();
    }

    async function cargarVehiculosAdmin() {
        const container = document.getElementById('flota-config-container');
        if (!container || !window.FichaCfg) return;
        const F = window.FichaCfg, canEdit = F.puede('configuracion.flota');
        let data = [], areas = [];
        try {
            const auth = { headers: { 'Authorization': 'Bearer ' + localStorage.getItem('access_token') } };
            const r = await Promise.all([fetch('/api/flota/maestro/', auth), fetch('/api/configuracion/areas/', auth)]);
            if (!r[0].ok) throw new Error('No se pudo leer la flota.');
            data = await r[0].json();
            areas = r[1].ok ? await r[1].json() : [];
            _catalogoAreasCached = areas;
        } catch (e) {
            container.innerHTML = '<p class="fcB-vacio">' + F.esc(e.message) + ' <button type="button" class="fcB-btn" onclick="FlotaModule.cargarVehiculosAdmin()">Reintentar</button></p>';
            return;
        }
        const areasFlota = areas.filter(function (a) { return a.aplica_flota === 1 || a.aplica_flota === true; });
        F.montar(container, {
            clave: 'flota',
            titulo: 'Flota Aguacol',
            descripcion: 'Vehículos de la empresa que Portería registra al salir y al volver. Solo se asignan a áreas con control de flota.',
            acciones: canEdit ? '<button type="button" class="fcB-btn pri" onclick="FichaCfg.nuevo(\'flota\')"><i class="bi bi-plus-lg" aria-hidden="true"></i>Registrar vehículo</button>' : '',
            items: data.slice().sort(function (a, b) { return String(a.patente).localeCompare(String(b.patente), 'es'); }),
            id: function (v) { return v.id; },
            etiqueta: function (v) { return v.patente; },
            sub: function (v) { return v.area_nombre || ''; },
            apagado: function (v) { return v.activo === 0 || v.activo === false; },
            vacio: 'No hay vehículos registrados.',
            ficha: function (v, panel) {
                const nuevo = !v;
                v = v || { patente: '', area_id: areasFlota.length ? areasFlota[0].id : '' };
                const f = v.created_at ? String(v.created_at).split(' ')[0].split('-') : null;
                const ops = areasFlota.map(function (a) { return [a.id, a.nombre]; });
                if (!nuevo && v.area_id && !ops.some(function (o) { return String(o[0]) === String(v.area_id); })) ops.unshift([v.area_id, v.area_nombre || 'Área sin control de flota']);
                panel.innerHTML = F.cabeza(nuevo ? 'Registrar vehículo' : v.patente, nuevo ? 'Escriba la patente y elija su área.' : (f ? 'Registrado el ' + f[2] + '-' + f[1] + '-' + f[0] + '.' : ''))
                    + F.campo('Patente', F.texto('ffl-patente', v.patente, ' placeholder="Ej: ABCD12" style="max-width:200px;text-transform:uppercase;font-variant-numeric:tabular-nums"'), 'Sin guiones ni espacios.', 'ffl-patente')
                    + F.campo('Área', ops.length ? F.lista('ffl-area', ops, v.area_id) : '<p class="fcB-nota">Ninguna área tiene control de flota. Actívelo en Configuración › Áreas.</p>', '', 'ffl-area')
                    + (canEdit ? F.pie(nuevo ? '' : '<button type="button" class="fcB-btn borra" id="ffl-borrar"><i class="bi bi-trash3" aria-hidden="true"></i>Eliminar vehículo</button>',
                        '<button type="button" class="fcB-btn" id="ffl-descartar">Descartar</button><button type="button" class="fcB-btn pri" id="ffl-guardar"' + (ops.length ? '' : ' disabled') + '>' + (nuevo ? 'Registrar vehículo' : 'Guardar cambios') + '</button>') : '');
                if (!canEdit) { panel.querySelectorAll('input, select').forEach(function (e) { e.disabled = true; }); return; }
                panel.querySelector('#ffl-descartar').onclick = function () { F.pintarFicha('flota'); };
                const borrar = panel.querySelector('#ffl-borrar');
                if (borrar) borrar.onclick = function () { eliminarVehiculo(v.id, v.patente); };
                panel.querySelector('#ffl-guardar').onclick = function (ev) {
                    const patente = panel.querySelector('#ffl-patente').value.toUpperCase().replace(/[\s.-]+/g, '');
                    const sel = panel.querySelector('#ffl-area');
                    if (!patente) { showToast('Falta la patente.', 'warning'); return; }
                    const dup = data.find(function (x) { return x.patente === patente && x.id !== v.id; });
                    if (dup) { showToast('La patente ' + patente + ' ya está registrada en ' + (dup.area_nombre || 'otra área') + '.', 'warning'); return; }
                    F.trabajando(ev.currentTarget, async function () {
                        const r = await fetch(nuevo ? '/api/flota/maestro/' : '/api/flota/maestro/' + v.id + '/', {
                            method: nuevo ? 'POST' : 'PUT',
                            headers: { 'Authorization': 'Bearer ' + localStorage.getItem('access_token'), 'Content-Type': 'application/json' },
                            body: JSON.stringify({ patente: patente, area_id: parseInt(sel.value, 10) })
                        });
                        const d = await r.json().catch(function () { return {}; });
                        if (!r.ok) { showToast(d.detail || 'No se pudo guardar el vehículo.', 'danger'); return; }
                        showToast(nuevo ? 'Listo. Vehículo registrado.' : 'Listo. Cambios guardados.', 'success');
                        if (d && d.id) F.recordar('flota', d.id);
                        await cargarVehiculosAdmin();
                    });
                };
            }
        });
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
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
                });
                if (res.ok) {
                    areas = await res.json();
                    _catalogoAreasCached = areas;
                }
            }
            
            // Cargar maestro de vehículos para validación de duplicados en tiempo real
            const resMaestro = await fetch('/api/flota/maestro/', {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
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
                title: 'Sin áreas configuradas',
                html: 'Antes de registrar un vehículo, debes habilitar al menos un área para flota.<br><br>Ve a la pestaña de <b>Áreas</b> y activa la casilla <b>"Aplica para Flota"</b> en el área que desees.',
                icon: 'warning',
                confirmButtonText: 'Entendido'
            });
            return;
        }

        const optionsHtml = areasFiltradas.map(a => `
            <option value="${a.id}" ${areaId === a.id ? 'selected' : ''}>${a.nombre}</option>
        `).join('');

        const titulo = id ? 'Editar vehículo' : 'Registrar vehículo en la flota';
        
        Swal.fire({
            title: titulo,
            html: `
                <div class="text-start">
                    <div class="mb-3">
                        <label for="swal-vehiculo-patente" class="form-label small fw-bold text-muted">Patente del Vehículo</label>
                        <input type="text" id="swal-vehiculo-patente" class="form-control text-uppercase font-monospace" placeholder="Ej: ABCD12" value="${patente}">
                        <div id="swal-vehiculo-patente-error" class="text-danger small mt-1 d-none" style="font-weight: 600;"></div>
                        <div class="form-text text-muted small">Forzado automáticamente a mayúsculas y sin espacios.</div>
                    </div>
                    <div class="mb-3">
                        <label for="swal-vehiculo-area" class="form-label small fw-bold text-muted">Área de la Empresa</label>
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
                        errorDiv.textContent = `La patente ${pat} ya está registrada en ${duplicado.area_nombre}.`;
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
                            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                        },
                        body: JSON.stringify({ patente, area_id })
                    });
                    
                    if (!response.ok) {
                        const err = await response.json();
                        throw new Error(err.detail || 'Error al guardar el vehículo');
                    }
                    
                    if(typeof showToast === 'function') {
                        showToast(id ? "Listo. Vehículo guardado." : "Listo. Vehículo agregado a la flota.", "success");
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
                        headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
                    });
                    
                    if (!response.ok) {
                        const err = await response.json();
                        throw new Error(err.detail || 'Error al eliminar el vehículo');
                    }
                    
                    if(typeof showToast === 'function') {
                        showToast("Listo. Vehículo quitado de la flota.", "success");
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
    }

    return {
        initTab,
        cargarEstadoDia,
        marcar,
        initAdminTab,
        cargarVehiculosAdmin,
        abrirModalVehiculo,
        eliminarVehiculo,
        destroy
    };
})();
