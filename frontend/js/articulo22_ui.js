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
                .art22-kpi { position: relative; overflow: hidden; border-radius: 12px; padding: 1.25rem 1.5rem; color: #fff; transition: transform 0.3s; }
                .art22-kpi:hover { transform: translateY(-2px); }
                .art22-kpi .kpi-icon { position: absolute; right: -10px; top: -10px; font-size: 5rem; opacity: 0.08; }
                .art22-kpi .kpi-number { font-size: 2.25rem; font-weight: 800; line-height: 1; }
                .art22-kpi .kpi-label { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; opacity: 0.9; }
                .art22-kpi .kpi-sub { font-size: 0.8rem; font-weight: 500; opacity: 0.8; margin-top: 2px; }
                .art22-emp-card { background: #fff; border-radius: 10px; margin: 6px 12px; padding: 0; border-left: 4px solid transparent; transition: all 0.2s ease; box-shadow: 0 1px 3px rgba(0,0,0,0.04); overflow: hidden; }
                .art22-emp-card:hover { box-shadow: 0 3px 12px rgba(0,0,0,0.07); transform: translateY(-1px); }
                .art22-emp-card.estado-en_planta { border-left-color: #10b981; }
                .art22-emp-card.estado-fuera { border-left-color: #f43f5e; }
                .art22-emp-card.estado-sin_registro { border-left-color: #cbd5e1; }
                .art22-card-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 16px 8px 16px; gap: 12px; }
                .art22-card-identity { display: flex; align-items: center; gap: 12px; flex: 1; min-width: 0; }
                .art22-card-info { min-width: 0; }
                .art22-card-name { font-weight: 600; color: #1e293b; font-size: 0.85rem; line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
                .art22-card-cargo { font-size: 0.72rem; color: #64748b; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
                .art22-card-metrics { display: flex; align-items: center; gap: 14px; flex-shrink: 0; }
                .art22-card-estadia { text-align: center; padding: 0 10px; }
                .art22-card-timeline { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; padding: 6px 16px 12px 16px; border-top: 1px solid #f1f5f9; background: rgba(248,250,252,0.5); min-height: 32px; }
                .art22-avatar { width: 42px; height: 42px; border-radius: 50%; background: linear-gradient(135deg, #e2e8f0, #cbd5e1); display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.75rem; color: #475569; flex-shrink: 0; border: 2px solid #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
                .art22-area-badge { display: inline-block; padding: 2px 8px; background: #eef2ff; color: #4338ca; border: 1px solid #c7d2fe; border-radius: 6px; font-size: 0.62rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 3px; }
                .art22-mark { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 6px; font-size: 0.74rem; font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
                .art22-mark-e { background: linear-gradient(135deg, #d1fae5, #a7f3d0); color: #065f46; border: 1px solid #6ee7b7; }
                .art22-mark-s { background: linear-gradient(135deg, #ffe4e6, #fecdd3); color: #9f1239; border: 1px solid #fda4af; }
                .art22-mark-arrow { color: #94a3b8; font-size: 0.7rem; margin: 0 2px; }
                .art22-estadia-label { font-size: 0.6rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; }
                .art22-estadia-val { font-size: 0.95rem; font-weight: 800; color: #1e293b; letter-spacing: -0.01em; }
                .art22-status-pill { display: inline-flex; align-items: center; gap: 5px; padding: 5px 12px; border-radius: 999px; font-size: 0.7rem; font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,0.06); }
                .art22-status-pill .dot { width: 7px; height: 7px; border-radius: 50%; animation: art22-pulse 2s infinite; }
                @keyframes art22-pulse { 0%,100% { opacity:1; } 50% { opacity:0.5; } }
                .art22-status-en_planta { background: linear-gradient(135deg, #d1fae5, #a7f3d0); color: #065f46; border: 1px solid #6ee7b7; }
                .art22-status-en_planta .dot { background: #10b981; box-shadow: 0 0 4px rgba(16,185,129,0.5); }
                .art22-status-fuera { background: linear-gradient(135deg, #ffe4e6, #fecdd3); color: #9f1239; border: 1px solid #fda4af; }
                .art22-status-fuera .dot { background: #f43f5e; box-shadow: 0 0 4px rgba(244,63,94,0.5); }
                .art22-status-sin_registro { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
                .art22-status-sin_registro .dot { background: #94a3b8; animation: none; }
                .art22-btn-entrada { background: linear-gradient(135deg, #10b981, #059669); color: #fff; border: none; font-weight: 700; font-size: 0.78rem; padding: 8px 18px; border-radius: 8px; cursor: pointer; transition: all 0.25s ease; box-shadow: 0 2px 6px rgba(16,185,129,0.3); letter-spacing: 0.02em; }
                .art22-btn-entrada:hover { background: linear-gradient(135deg, #059669, #047857); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(16,185,129,0.4); }
                .art22-btn-entrada:active { transform: translateY(0); box-shadow: 0 1px 3px rgba(16,185,129,0.3); }
                .art22-btn-salida { background: linear-gradient(135deg, #f43f5e, #e11d48); color: #fff; border: none; font-weight: 700; font-size: 0.78rem; padding: 8px 18px; border-radius: 8px; cursor: pointer; transition: all 0.25s ease; box-shadow: 0 2px 6px rgba(244,63,94,0.3); letter-spacing: 0.02em; }
                .art22-btn-salida:hover { background: linear-gradient(135deg, #e11d48, #be123c); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(244,63,94,0.4); }
                .art22-btn-salida:active { transform: translateY(0); box-shadow: 0 1px 3px rgba(244,63,94,0.3); }
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
                <div id="art22-estado-body" style="background:#f8fafc; padding:6px 0">
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

        // Marks timeline — compact dots on a horizontal line
        let marcasHtml = '';
        if (emp.marcas && emp.marcas.length > 0) {
            marcasHtml = emp.marcas.map((m, i) => {
                const isE = m.tipo === 'E';
                const cls = isE ? 'art22-mark-e' : 'art22-mark-s';
                const icon = isE ? 'bi-box-arrow-in-right' : 'bi-box-arrow-right';
                const label = isE ? 'E' : 'S';
                const arrow = i < emp.marcas.length - 1 ? '<span class="art22-mark-arrow">→</span>' : '';
                return `<span class="art22-mark ${cls}"><i class="bi ${icon}" style="font-size:0.6rem"></i>${m.hora.substring(0,5)} ${label}</span>${arrow}`;
            }).join('');
        } else {
            marcasHtml = '<span style="font-size:0.78rem; color:#94a3b8; font-style:italic">Sin marcaciones hoy</span>';
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
                    <div class="art22-card-identity">
                        <div class="art22-avatar">${initials.toUpperCase()}</div>
                        <div class="art22-card-info">
                            <div class="art22-card-name">${emp.nombre}</div>
                            <div class="art22-card-cargo">${emp.cargo || ''}</div>
                            <span class="art22-area-badge">${emp.area || ''}</span>
                        </div>
                    </div>
                    <div class="art22-card-metrics">
                        <div class="art22-card-estadia">
                            <div class="art22-estadia-label">Estadía</div>
                            ${estadiaHtml}
                        </div>
                        <span class="art22-status-pill ${statusClass}"><span class="dot"></span>${statusLabel}</span>
                        <button class="${btnClass}" onclick="Articulo22Module.marcar(${emp.empleado_id})">
                            ${proximaTipo} <i class="bi ${btnIcon}"></i>
                        </button>
                    </div>
                </div>
                <div class="art22-card-timeline">
                    ${marcasHtml}
                </div>
            </div>`;
    }

    // ════════════════════════════════════════════════
    // MARCAR
    // ════════════════════════════════════════════════
    async function marcar(empleadoId) {
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
