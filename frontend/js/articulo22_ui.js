/**
 * Módulo Artículo 22 — Control de Presencia en Planta
 * Diseño Enterprise inspirado en Stitch/Linear/Stripe
 */
const Articulo22Module = (() => {
    // Fecha local del navegador (NO usar toISOString que convierte a UTC)
    let _fechaActual = (() => {
        const d = new Date();
        return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    })();
    let _refreshInterval = null;

    // ════════════════════════════════════════════════
    // INIT
    // ════════════════════════════════════════════════
    async function initTab() {
        const container = document.getElementById('art22-container');
        if (!container) return;

        const hoy = new Date();
        const diasSemana = ['Domingo','Lunes','Martes','Miércoles','Jueves','Viernes','Sábado'];
        const meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
        const fechaDisplay = `${diasSemana[hoy.getDay()]} ${hoy.getDate()} ${meses[hoy.getMonth()]} ${hoy.getFullYear()}`;

        container.innerHTML = `
            <style>
                .art22-kpi { position: relative; overflow: hidden; border-radius: 16px; padding: 1.25rem 1.5rem; color: #fff; transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1); border: 1px solid rgba(255,255,255,0.1); }
                .art22-kpi:hover { transform: translateY(-2px); box-shadow: 0 10px 20px -10px rgba(0,0,0,0.15); }
                .art22-kpi .kpi-icon { position: absolute; right: -10px; top: -10px; font-size: 5rem; opacity: 0.08; }
                .art22-kpi .kpi-number { font-size: 2.25rem; font-weight: 800; line-height: 1; }
                .art22-kpi .kpi-label { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; opacity: 0.9; }
                .art22-kpi .kpi-sub { font-size: 0.8rem; font-weight: 500; opacity: 0.8; margin-top: 2px; }
                #art22-estado-body { display: grid; grid-template-columns: 1fr; gap: 20px; padding: 20px !important; background: #f8fafc; }
                @media (min-width: 992px) { #art22-estado-body { grid-template-columns: 1fr 1fr; } }
                .art22-emp-card { background: #ffffff; border-radius: 16px; margin: 0; padding: 0; border: 1px solid #e2e8f0; border-left: 5px solid #cbd5e1; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 2px 8px rgba(0,0,0,0.02); overflow: hidden; }
                .art22-emp-card:hover { box-shadow: 0 12px 24px -10px rgba(0,0,0,0.08); transform: translateY(-2px); border-color: #cbd5e1; }
                .art22-emp-card.estado-en_planta { border-left-color: #10b981; }
                .art22-emp-card.estado-fuera { border-left-color: #f43f5e; }
                .art22-emp-card.estado-sin_registro { border-left-color: #cbd5e1; }
                .art22-card-header { display: flex; flex-direction: column; padding: 18px 20px 14px 20px; gap: 12px; }
                .art22-card-top { display: flex; justify-content: space-between; align-items: center; width: 100%; gap: 12px; }
                .art22-card-identity { display: flex; align-items: center; gap: 12px; min-width: 0; flex: 1; }
                .art22-card-info { min-width: 0; flex: 1; }
                .art22-card-name { font-weight: 700; color: #0f172a; font-size: 0.9rem; line-height: 1.2; letter-spacing: -0.01em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
                .art22-card-cargo { font-size: 0.74rem; color: #64748b; margin-top: 2px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
                .art22-card-meta-row { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; width: 100%; padding-top: 10px; border-top: 1px dashed #e2e8f0; }
                .art22-card-estadia { display: flex; align-items: center; gap: 6px; }
                .art22-gantt-container { position: relative; padding: 68px 24px 68px 24px; border-top: 1px solid #f1f5f9; background: rgba(248,250,252,0.65); min-height: 154px; }
                .art22-gantt-backdrop { position: relative; height: 22px; width: 100%; margin: 10px 0; }
                .art22-gantt-track { height: 14px; background: #e2e8f0; border-radius: 7px; position: absolute; top: 2px; left: 0; width: 100%; overflow: hidden; display: flex; box-shadow: inset 0 1px 2px rgba(0,0,0,0.06); border: 1px solid #cbd5e1; }
                .art22-gantt-segment { height: 100%; position: absolute; background: linear-gradient(180deg, #10b981 0%, #059669 100%); border-right: 1px solid rgba(255,255,255,0.2); border-left: 1px solid rgba(255,255,255,0.2); transition: all 0.3s ease; }
                .art22-gantt-segment.ongoing { background: repeating-linear-gradient(45deg, #10b981, #10b981 8px, #34d399 8px, #34d399 16px); border-right: none; }
                .art22-gantt-grid-line { position: absolute; top: 0; bottom: 0; width: 1px; background: rgba(148, 163, 184, 0.15); z-index: 1; }
                .art22-gantt-grid-label { position: absolute; font-size: 0.58rem; font-weight: 700; color: #94a3b8; top: -16px; transform: translateX(-50%); font-family: 'JetBrains Mono', monospace; }
                @media (max-width: 768px) { .art22-gantt-grid-label.h-sub { display: none !important; } }
                .art22-gantt-marker { position: absolute; top: 9px; display: flex; align-items: center; z-index: 3; }
                .art22-gantt-marker.dir-down { flex-direction: column; }
                .art22-gantt-marker.dir-up { flex-direction: column-reverse; transform: translateY(-100%); margin-top: 10px; }
                .art22-gantt-dot { width: 10px; height: 10px; border-radius: 50%; border: 2px solid #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.15); }
                .art22-gantt-dot.e { background-color: #10b981; }
                .art22-gantt-dot.s { background-color: #f43f5e; }
                .art22-gantt-marker-line { width: 1.5px; background-color: #cbd5e1; z-index: 1; }
                .art22-gantt-marker.level-1 .art22-gantt-marker-line { height: 10px; }
                .art22-gantt-marker.level-2 .art22-gantt-marker-line { height: 22px; }
                .art22-gantt-marker.level-3 .art22-gantt-marker-line { height: 34px; }
                .art22-gantt-bubble { font-family: 'Inter', system-ui, -apple-system, sans-serif; font-size: 0.62rem; font-weight: 600; white-space: nowrap; padding: 4px 8px; border-radius: 8px; display: flex; flex-direction: column; align-items: center; gap: 2px; z-index: 2; box-shadow: 0 4px 10px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); transition: all 0.2s ease; }
                .art22-gantt-bubble.e { background-color: rgba(240, 253, 244, 0.95); color: #16a34a; border: 1px solid rgba(134, 239, 172, 0.5); }
                .art22-gantt-bubble.s { background-color: rgba(254, 242, 242, 0.95); color: #dc2626; border: 1px solid rgba(254, 202, 202, 0.5); }
                .art22-gantt-bubble .bubble-label { font-size: 0.56rem; font-weight: 500; opacity: 0.85; text-transform: uppercase; letter-spacing: 0.03em; display: flex; align-items: center; gap: 4px; }
                .art22-gantt-bubble .bubble-time { font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; font-weight: 700; }
                .art22-gantt-pulse-ring { position: absolute; top: 9px; transform: translate(-50%, -50%); width: 18px; height: 18px; border-radius: 50%; border: 2px solid #10b981; animation: gantt-ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite; pointer-events: none; z-index: 2; }
                @keyframes gantt-ping { 75%, 100% { transform: translate(-50%, -50%) scale(1.8); opacity: 0; } }
                .art22-gantt-empty-text { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 0.72rem; font-weight: 600; color: #64748b; font-style: italic; z-index: 2; pointer-events: none; }
                .art22-gantt-track.empty { background: repeating-linear-gradient(-45deg, #f1f5f9, #f1f5f9 6px, #e2e8f0 6px, #e2e8f0 12px); border: 1px dashed #cbd5e1; }
                .art22-avatar { width: 46px; height: 46px; border-radius: 12px; background: linear-gradient(135deg, #f1f5f9, #e2e8f0); display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.95rem; color: #475569; flex-shrink: 0; border: 1px solid #e2e8f0; }
                .art22-area-badge { display: inline-block; padding: 2px 8px; background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 0.64rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 6px; }
                .art22-estadia-label { font-size: 0.6rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; }
                .art22-estadia-val { font-size: 0.95rem; font-weight: 800; color: #1e293b; letter-spacing: -0.01em; }
                .art22-status-pill { display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; border-radius: 8px; font-size: 0.72rem; font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,0.02); }
                .art22-status-pill .dot { width: 7px; height: 7px; border-radius: 50%; }
                .art22-status-en_planta { background: #d1fae5; color: #065f46; border: 1px solid #a7f3d0; }
                .art22-status-en_planta .dot { background: #10b981; animation: art22-pulse 2s infinite; }
                .art22-status-fuera { background: #ffe4e6; color: #9f1239; border: 1px solid #fda4af; }
                .art22-status-fuera .dot { background: #f43f5e; }
                .art22-status-sin_registro { background: #f8fafc; color: #64748b; border: 1px solid #e2e8f0; }
                .art22-status-sin_registro .dot { background: #94a3b8; }
                .art22-btn-entrada { background-color: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; font-weight: 600; font-size: 0.74rem; padding: 6px 14px; border-radius: 8px; cursor: pointer; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 1px 2px rgba(22, 163, 74, 0.05); display: inline-flex; align-items: center; gap: 6px; }
                .art22-btn-entrada:hover { background-color: #dcfce7; border-color: #86efac; color: #15803d; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(22, 163, 74, 0.1); }
                .art22-btn-salida { background-color: #fef2f2; color: #dc2626; border: 1px solid #fecaca; font-weight: 600; font-size: 0.74rem; padding: 6px 14px; border-radius: 8px; cursor: pointer; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 1px 2px rgba(220, 38, 38, 0.05); display: inline-flex; align-items: center; gap: 6px; }
                .art22-btn-salida:hover { background-color: #fee2e2; border-color: #fca5a5; color: #b91c1c; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(220, 38, 38, 0.1); }
                .art22-section-header { background: rgba(248,250,252,0.5); padding: 0.9rem 1.2rem; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center; }
                .art22-section-title { font-size: 1rem; font-weight: 600; color: #1e293b; display: flex; align-items: center; gap: 8px; }
                .art22-filter-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; background: #f8fafc; padding: 8px 12px; border-radius: 8px; border: 1px solid #f1f5f9; }
                .art22-filter-bar label { font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #64748b; }
                .art22-hist-table thead tr { background: #f8fafc; border-bottom: 1px solid #e2e8f0; }
                .art22-hist-table thead th { font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #64748b; padding: 10px 14px; }
                .art22-hist-table tbody td { padding: 10px 14px; font-size: 0.82rem; }
                .art22-hist-table tbody tr { transition: background 0.15s; }
                .art22-hist-table tbody tr:hover { background: rgba(248,250,252,0.5); }
                .art22-hist-table tbody tr:not(:last-child) td { border-bottom: 1px solid #f1f5f9; }
                .art22-marcas-circle { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 50%; font-size: 0.72rem; font-weight: 700; background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
            </style>

            <!-- ENCABEZADO -->
            <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
                <div class="d-flex align-items-center gap-3">
                    <div style="background:#fff; padding:8px; border-radius:10px; box-shadow: var(--shadow-sm); border:1px solid #e2e8f0; color:var(--primary-color); display:flex; align-items:center; justify-content:center;">
                        <i class="bi bi-clipboard-check-fill" style="font-size:1.3rem"></i>
                    </div>
                    <div>
                        <h4 class="fw-bold mb-0" style="color:#1e293b; letter-spacing:-0.02em">Control de Presencia — Artículo 22</h4>
                        <p class="mb-0" style="font-size:0.82rem; color:#64748b; font-weight:500">Gestión de personal exento de jornada laboral</p>
                    </div>
                </div>
                <div class="d-flex align-items-center gap-2">
                    <span style="background:#fff; padding:6px 16px; border-radius:999px; box-shadow:var(--shadow-sm); border:1px solid #e2e8f0; font-size:0.85rem; font-weight:600; color:#475569">
                        <i class="bi bi-calendar3 me-1" style="color:#94a3b8"></i>${fechaDisplay}
                    </span>
                    <button class="btn btn-sm btn-light border" onclick="Articulo22Module.cargarEstadoDia()" style="border-radius:8px">
                        <i class="bi bi-arrow-clockwise"></i>
                    </button>
                </div>
            </div>

            <!-- KPI STATS -->
            <div class="row g-3 mb-4">
                <div class="col-md-4">
                    <div class="art22-kpi" style="background: var(--primary-color)">
                        <i class="bi bi-people-fill kpi-icon"></i>
                        <div class="kpi-label">Total Art. 22</div>
                        <div class="d-flex align-items-baseline gap-2 mt-2">
                            <span class="kpi-number" id="art22-stat-total">—</span>
                            <span class="kpi-sub">empleados</span>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="art22-kpi" style="background: var(--success-color)">
                        <i class="bi bi-building-fill kpi-icon"></i>
                        <div class="kpi-label">En Planta</div>
                        <div class="d-flex align-items-baseline gap-2 mt-2">
                            <span class="kpi-number" id="art22-stat-presentes">—</span>
                            <span class="kpi-sub">activos ahora</span>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="art22-kpi" style="background: var(--warning-color)">
                        <i class="bi bi-clock-history kpi-icon"></i>
                        <div class="kpi-label">Sin Registro</div>
                        <div class="d-flex align-items-baseline gap-2 mt-2">
                            <span class="kpi-number" id="art22-stat-sin">—</span>
                            <span class="kpi-sub">pendientes hoy</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ESTADO DEL DÍA -->
            <div class="card border-0 shadow-sm mb-4" style="border-radius:12px; overflow:hidden">
                <div class="art22-section-header">
                    <span class="art22-section-title">
                        <i class="bi bi-list-check" style="color:var(--primary-color)"></i>Estado del Día
                    </span>
                    <button class="btn btn-sm text-primary fw-semibold" style="font-size:0.8rem" onclick="Articulo22Module.cargarEstadoDia()">
                        <i class="bi bi-arrow-clockwise me-1"></i>Actualizar
                    </button>
                </div>
                <div id="art22-estado-body">
                    <div class="text-center py-5 text-muted">
                        <div class="spinner-border spinner-border-sm text-primary"></div> Cargando...
                    </div>
                </div>
            </div>

            <!-- HISTORIAL -->
            <div class="card border-0 shadow-sm" style="border-radius:12px; overflow:hidden">
                <div class="art22-section-header" style="flex-wrap:wrap; gap:12px;">
                    <span class="art22-section-title">
                        <i class="bi bi-clock-history" style="color:var(--primary-color)"></i>Historial de Ingresos
                    </span>
                    <div class="art22-filter-bar">
                        <div class="d-flex align-items-center gap-2">
                            <label>Desde</label>
                            <input type="date" class="form-control form-control-sm" id="art22-hist-desde" style="font-size:0.82rem; border-color:#e2e8f0; border-radius:6px;">
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            <label>Hasta</label>
                            <input type="date" class="form-control form-control-sm" id="art22-hist-hasta" style="font-size:0.82rem; border-color:#e2e8f0; border-radius:6px;">
                        </div>
                        <button class="btn btn-sm btn-primary fw-bold px-3" onclick="Articulo22Module.cargarHistorial()" style="border-radius:6px; font-size:0.8rem">
                            <i class="bi bi-search me-1"></i>Consultar
                        </button>
                    </div>
                </div>
                <div class="table-responsive" style="max-height:400px; overflow-y:auto;">
                    <table class="table mb-0 art22-hist-table">
                        <thead>
                            <tr>
                                <th>Fecha</th>
                                <th>Nombre</th>
                                <th>Cargo / Área</th>
                                <th>1ª Entrada</th>
                                <th>Últ. Salida</th>
                                <th class="text-center">Marcas</th>
                                <th class="text-end">Estadía</th>
                            </tr>
                        </thead>
                        <tbody id="art22-historial-tbody">
                            <tr><td colspan="7" class="text-center py-4 text-muted" style="font-size:0.85rem">Seleccione fechas y presione Consultar</td></tr>
                        </tbody>
                    </table>
                </div>
                <div id="art22-historial-pagination" class="d-flex justify-content-between align-items-center px-3 py-2 border-top" style="font-size:0.78rem; color:#64748b; background:#fff;"></div>
            </div>
        `;

        const hasta = document.getElementById('art22-hist-hasta');
        const desde = document.getElementById('art22-hist-desde');
        if (hasta) hasta.value = _fechaActual;
        if (desde) { const d = new Date(); d.setDate(d.getDate()-7); desde.value = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; }

        await cargarEstadoDia();
        if (_refreshInterval) clearInterval(_refreshInterval);
        _refreshInterval = setInterval(() => cargarEstadoDia(), 60000);
    }

    // ════════════════════════════════════════════════
    // CARGAR ESTADO DEL DÍA
    // ════════════════════════════════════════════════
    async function cargarEstadoDia() {
        try {
            const res = await fetch(`/api/articulo22/estado-dia/?fecha=${_fechaActual}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
            });
            if (!res.ok) throw new Error("Error API");
            const data = await res.json();

            document.getElementById('art22-stat-total').textContent = data.stats.total;
            document.getElementById('art22-stat-presentes').textContent = data.stats.en_planta;
            document.getElementById('art22-stat-sin').textContent = data.stats.sin_registro;

            const body = document.getElementById('art22-estado-body');
            if (!data.empleados.length) {
                body.innerHTML = '<div class="text-center py-5 text-muted">No hay empleados Art. 22 configurados</div>';
                return;
            }
            body.innerHTML = data.empleados.map(emp => renderEmpleadoCard(emp)).join('');
        } catch (e) {
            console.error(e);
            const body = document.getElementById('art22-estado-body');
            if (body) body.innerHTML = '<div class="text-center py-5 text-danger fw-bold">Error al cargar estado</div>';
        }
    }

    function renderEmpleadoCard(emp) {
        // Avatar initials
        const parts = (emp.nombre || '').split(',');
        const initials = parts.length > 1
            ? (parts[0].trim()[0] || '') + (parts[1].trim()[0] || '')
            : (emp.nombre || '').substring(0,2);

        // Marks timeline — Gantt style
        let marcasHtml = '';
        if (emp.marcas && emp.marcas.length > 0) {
            const segments = [];
            let currentEntradaMinutes = null;

            // Sort marks by time to be absolutely sure
            const sortedMarcas = [...emp.marcas].sort((a, b) => a.hora.localeCompare(b.hora));

            sortedMarcas.forEach(m => {
                const parts = m.hora.split(':');
                const minutes = parseInt(parts[0]) * 60 + parseInt(parts[1]);
                if (m.tipo === 'E') {
                    if (currentEntradaMinutes === null) {
                        currentEntradaMinutes = minutes;
                    }
                } else if (m.tipo === 'S') {
                    if (currentEntradaMinutes !== null) {
                        segments.push({ start: currentEntradaMinutes, end: minutes, ongoing: false });
                        currentEntradaMinutes = null;
                    } else {
                        // Salida sin entrada previa hoy -> asumir dentro desde medianoche
                        segments.push({ start: 0, end: minutes, ongoing: false });
                    }
                }
            });

            // If still inside at the end of marks list
            if (currentEntradaMinutes !== null) {
                const todayStr = (() => {
                    const d = new Date();
                    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
                })();
                let endMin = 1440;
                let isOngoing = false;
                if (_fechaActual === todayStr && emp.estado === 'en_planta') {
                    const now = new Date();
                    endMin = Math.min(now.getHours() * 60 + now.getMinutes(), 1440);
                    isOngoing = true;
                }
                segments.push({ start: currentEntradaMinutes, end: endMin, ongoing: isOngoing });
            }

            const nowPct = (() => {
                const now = new Date();
                return ((Math.min(now.getHours() * 60 + now.getMinutes(), 1440) / 1440) * 100).toFixed(2);
            })();

            const todayStr = (() => {
                const d = new Date();
                return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
            })();
            const isToday = (_fechaActual === todayStr);

            marcasHtml = `
                <div class="art22-gantt-backdrop">
                    <!-- Regla de tiempo de fondo -->
                    <span class="art22-gantt-grid-label h-main" style="left: 0%;">00:00</span>
                    <span class="art22-gantt-grid-label h-sub" style="left: 12.5%;">03:00</span>
                    <span class="art22-gantt-grid-label h-main" style="left: 25%;">06:00</span>
                    <span class="art22-gantt-grid-label h-sub" style="left: 37.5%;">09:00</span>
                    <span class="art22-gantt-grid-label h-main" style="left: 50%;">12:00</span>
                    <span class="art22-gantt-grid-label h-sub" style="left: 62.5%;">15:00</span>
                    <span class="art22-gantt-grid-label h-main" style="left: 75%;">18:00</span>
                    <span class="art22-gantt-grid-label h-sub" style="left: 87.5%;">21:00</span>
                    <span class="art22-gantt-grid-label h-main" style="left: 100%;">24:00</span>

                    <!-- Pista Gantt -->
                    <div class="art22-gantt-track">
                        <div class="art22-gantt-grid-line" style="left: 12.5%;"></div>
                        <div class="art22-gantt-grid-line" style="left: 25%;"></div>
                        <div class="art22-gantt-grid-line" style="left: 37.5%;"></div>
                        <div class="art22-gantt-grid-line" style="left: 50%;"></div>
                        <div class="art22-gantt-grid-line" style="left: 62.5%;"></div>
                        <div class="art22-gantt-grid-line" style="left: 75%;"></div>
                        <div class="art22-gantt-grid-line" style="left: 87.5%;"></div>
                        ${segments.map(seg => {
                            const startPct = ((seg.start / 1440) * 100).toFixed(2);
                            const widthPct = (((seg.end - seg.start) / 1440) * 100).toFixed(2);
                            const cls = seg.ongoing ? 'ongoing' : '';
                            return `<div class="art22-gantt-segment ${cls}" style="left: ${startPct}%; width: ${widthPct}%;"></div>`;
                        }).join('')}
                    </div>

                    <!-- Hitos de marcaciones y pulso AHORA unificados -->
                    ${(() => {
                        const items = sortedMarcas.map(m => {
                            const parts = m.hora.split(':');
                            return {
                                minutes: parseInt(parts[0]) * 60 + parseInt(parts[1]),
                                label: m.tipo === 'E' ? 'Entrada' : 'Salida',
                                timeStr: m.hora.substring(0, 5),
                                isAhora: false,
                                tipo: m.tipo
                            };
                        });

                        if (isToday && emp.estado === 'en_planta') {
                            const now = new Date();
                            const nowMinutes = now.getHours() * 60 + now.getMinutes();
                            items.push({
                                minutes: nowMinutes,
                                label: 'AHORA',
                                timeStr: '',
                                isAhora: true,
                                tipo: 'E'
                            });
                        }

                        // Sort all items (punch marks + AHORA) chronologically
                        items.sort((a, b) => a.minutes - b.minutes);

                        const heightClasses = ['level-1', 'level-2', 'level-3'];
                        let upCount = 0;
                        let downCount = 0;

                        return items.map((item, index) => {
                            const pct = ((item.minutes / 1440) * 100).toFixed(2);
                            const cls = item.tipo === 'E' ? 'e' : 's';
                            const isUp = (item.tipo === 'E');
                            const dirCls = isUp ? 'dir-up' : 'dir-down';
                            const heightCls = isUp ? heightClasses[upCount++ % 3] : heightClasses[downCount++ % 3];

                            if (item.isAhora) {
                                // Overlap protection: calculate distance to previous mark
                                const prevMark = items[index - 1];
                                const hideAhoraBubble = prevMark && (item.minutes - prevMark.minutes) < 75;

                                return `
                                    <div class="art22-gantt-pulse-ring" style="left: ${pct}%"></div>
                                    <div class="art22-gantt-marker ${dirCls} ${hideAhoraBubble ? '' : heightCls}" style="left: ${pct}%">
                                        <div class="art22-gantt-dot e" style="background-color: #34d399; width: 8px; height: 8px; box-shadow: 0 0 8px #10b981;"></div>
                                        ${hideAhoraBubble ? '' : `
                                            <div class="art22-gantt-marker-line"></div>
                                            <div class="art22-gantt-bubble e" style="background-color: rgba(6, 95, 70, 0.95); color: #ffffff; border: 1px solid rgba(16, 185, 129, 0.5);">
                                                <span class="bubble-label" style="color: rgba(255,255,255,0.85);">AHORA</span>
                                                <span class="bubble-time">${item.timeStr}</span>
                                            </div>
                                        `}
                                    </div>
                                `;
                            } else {
                                return `
                                    <div class="art22-gantt-marker ${dirCls} ${heightCls}" style="left: ${pct}%">
                                        <div class="art22-gantt-dot ${cls}"></div>
                                        <div class="art22-gantt-marker-line"></div>
                                        <div class="art22-gantt-bubble ${cls}">
                                            <span class="bubble-label"><i class="bi ${item.tipo === 'E' ? 'bi-box-arrow-in-right' : 'bi-box-arrow-right'}"></i> ${item.label}</span>
                                            <span class="bubble-time">${item.timeStr}</span>
                                        </div>
                                    </div>
                                `;
                            }
                        }).join('');
                    })()}
                </div>
            `;
        } else {
            marcasHtml = `
                <div class="art22-gantt-backdrop" style="margin-bottom: 5px;">
                    <!-- Regla de tiempo de fondo -->
                    <span class="art22-gantt-grid-label h-main" style="left: 0%;">00:00</span>
                    <span class="art22-gantt-grid-label h-sub" style="left: 12.5%;">03:00</span>
                    <span class="art22-gantt-grid-label h-main" style="left: 25%;">06:00</span>
                    <span class="art22-gantt-grid-label h-sub" style="left: 37.5%;">09:00</span>
                    <span class="art22-gantt-grid-label h-main" style="left: 50%;">12:00</span>
                    <span class="art22-gantt-grid-label h-sub" style="left: 62.5%;">15:00</span>
                    <span class="art22-gantt-grid-label h-main" style="left: 75%;">18:00</span>
                    <span class="art22-gantt-grid-label h-sub" style="left: 87.5%;">21:00</span>
                    <span class="art22-gantt-grid-label h-main" style="left: 100%;">24:00</span>

                    <div class="art22-gantt-track empty">
                        <div class="art22-gantt-empty-text">Sin registros de marcación hoy</div>
                    </div>
                </div>
            `;
        }

        // Estadía
        const estadiaHtml = emp.estadia_display !== '—'
            ? `<span class="art22-estadia-val">${emp.estadia_display}</span>`
            : '<span style="color:#94a3b8">—</span>';

        // Status pill
        const statusClass = `art22-status-${emp.estado}`;
        const statusLabel = emp.estado === 'en_planta' ? 'En Planta' : emp.estado === 'fuera' ? 'Fuera' : 'Sin registro';

        // Action button
        const proximaTipo = (!emp.marcas || emp.marcas.length === 0 || emp.marcas[emp.marcas.length - 1].tipo === 'S') ? 'Entrada' : 'Salida';
        const btnClass = proximaTipo === 'Entrada' ? 'art22-btn-entrada' : 'art22-btn-salida';
        const btnIcon = proximaTipo === 'Entrada' ? 'bi-box-arrow-in-right' : 'bi-box-arrow-right';

        return `
            <div class="art22-emp-card estado-${emp.estado}">
                <div class="art22-card-header">
                    <div class="art22-card-top">
                        <div class="art22-card-identity">
                            <div class="art22-avatar">${initials.toUpperCase()}</div>
                            <div class="art22-card-info">
                                <div class="art22-card-name">${emp.nombre}</div>
                                <div class="art22-card-cargo">${emp.cargo || ''}</div>
                            </div>
                        </div>
                        <button class="${btnClass}" onclick="Articulo22Module.marcar(${emp.empleado_id}, this)">
                            <i class="bi ${btnIcon} me-1"></i> ${proximaTipo}
                        </button>
                    </div>
                    <div class="art22-card-meta-row">
                        <span class="art22-area-badge" style="margin-top: 0;">${emp.area || ''}</span>
                        <div class="art22-card-estadia">
                            <div class="art22-estadia-label">Estadía:</div>
                            ${estadiaHtml}
                        </div>
                        <span class="art22-status-pill ${statusClass}"><span class="dot"></span>${statusLabel}</span>
                    </div>
                </div>
                <div class="art22-gantt-container">
                    ${marcasHtml}
                </div>
            </div>`;
    }

    // ════════════════════════════════════════════════
    // MARCAR
    // ════════════════════════════════════════════════
    async function marcar(empleadoId, btn) {
        let originalHtml = "";
        if (btn) {
            btn.disabled = true;
            originalHtml = btn.innerHTML;
            btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>`;
        }
        try {
            const res = await fetch('/api/articulo22/marcar/', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ empleado_id: empleadoId })
            });
            if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Error'); }
            const data = await res.json();
            if (typeof showToast === 'function') {
                const icon = data.tipo === 'E' ? '🟢' : '🔴';
                showToast(`${icon} ${data.tipo_label}: ${data.nombre} a las ${data.hora.substring(0,5)}`, 'success');
            }
            await cargarEstadoDia();
        } catch (e) {
            console.error(e);
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalHtml;
            }
            if (typeof Swal !== 'undefined') Swal.fire('Error', e.message, 'error');
        }
    }

    // ════════════════════════════════════════════════
    // HISTORIAL
    // ════════════════════════════════════════════════
    async function cargarHistorial(page = 1) {
        const desde = document.getElementById('art22-hist-desde')?.value;
        const hasta = document.getElementById('art22-hist-hasta')?.value;
        const tbody = document.getElementById('art22-historial-tbody');
        const pagDiv = document.getElementById('art22-historial-pagination');
        if (!desde || !hasta) { if (typeof showToast === 'function') showToast('Seleccione rango de fechas', 'warning'); return; }
        tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4"><div class="spinner-border spinner-border-sm text-primary"></div></td></tr>';

        try {
            const res = await fetch(`/api/articulo22/historial/?desde=${desde}&hasta=${hasta}&page=${page}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
            });
            if (!res.ok) throw new Error("Error");
            const data = await res.json();

            if (!data.registros.length) {
                tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">No hay registros en el período</td></tr>';
                pagDiv.innerHTML = '';
                return;
            }

            tbody.innerHTML = data.registros.map(r => {
                const f = r.fecha.split('-');
                const meses = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
                const fechaFmt = `${parseInt(f[2])} ${meses[parseInt(f[1])]} ${f[0]}`;
                return `<tr>
                    <td style="font-weight:500; color:#475569; white-space:nowrap">${fechaFmt}</td>
                    <td style="font-weight:600; color:#1e293b">${r.nombre}</td>
                    <td style="color:#475569">${r.cargo || ''}<br><span style="font-size:0.72rem; color:#94a3b8">${r.area || ''}</span></td>
                    <td style="color:#065f46; font-weight:500">${r.primera_entrada ? r.primera_entrada.substring(0,5) : '<span style="color:#94a3b8; font-style:italic">—</span>'}</td>
                    <td style="color:#9f1239; font-weight:500">${r.ultima_salida ? r.ultima_salida.substring(0,5) : '<span style="color:#94a3b8; font-style:italic">—</span>'}</td>
                    <td class="text-center"><span class="art22-marcas-circle">${r.total_marcas}</span></td>
                    <td class="text-end" style="font-weight:700; color:#1e293b">${r.estadia_display}</td>
                </tr>`;
            }).join('');

            if (data.pages > 1) {
                let p = `<span>Mostrando ${data.page} de ${data.pages} (${data.total} registros)</span><div class="d-flex gap-1">`;
                for (let i = 1; i <= Math.min(data.pages, 5); i++) {
                    const cls = i === data.page ? 'btn-primary' : 'btn-outline-secondary';
                    p += `<button class="btn btn-sm ${cls}" style="min-width:30px; font-size:0.75rem; padding:2px 8px; border-radius:4px" onclick="Articulo22Module.cargarHistorial(${i})">${i}</button>`;
                }
                p += '</div>';
                pagDiv.innerHTML = p;
            } else { pagDiv.innerHTML = `<span>${data.total} registro(s)</span>`; }
        } catch (e) { console.error(e); tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-danger">Error al cargar</td></tr>'; }
    }

    function destroy() { if (_refreshInterval) { clearInterval(_refreshInterval); _refreshInterval = null; } }

    return { initTab, cargarEstadoDia, marcar, cargarHistorial, destroy };
})();
