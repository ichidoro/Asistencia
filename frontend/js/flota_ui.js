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
    let _catalogoAreasCached = []; // Cache local para evitar llamadas repetidas

    // ════════════════════════════════════════════════
    // INIT CONTROL TAB (PORTERÍA)
    // ════════════════════════════════════════════════
    async function initTab() {
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
                
                .flota-card { background: #fff; border-radius: 10px; margin: 6px 12px; padding: 0; border-left: 4px solid transparent; transition: all 0.2s ease; box-shadow: 0 1px 3px rgba(0,0,0,0.04); overflow: hidden; }
                .flota-card:hover { box-shadow: 0 3px 12px rgba(0,0,0,0.07); transform: translateY(-1px); }
                .flota-card.estado-en_planta { border-left-color: #10b981; }
                .flota-card.estado-fuera { border-left-color: #f43f5e; }
                .flota-card.estado-sin_registro { border-left-color: #cbd5e1; }
                
                .flota-card-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 16px 8px 16px; gap: 12px; }
                .flota-card-identity { display: flex; align-items: center; gap: 12px; flex: 1; min-width: 0; }
                .flota-card-info { min-width: 0; }
                .flota-card-name { font-weight: 700; color: #1e293b; font-size: 1.05rem; line-height: 1.2; letter-spacing: 0.05em; }
                .flota-card-cargo { font-size: 0.72rem; color: #64748b; margin-top: 1px; }
                .flota-card-metrics { display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
                .flota-card-metric-item { text-align: center; padding: 0 8px; border-right: 1px solid #f1f5f9; }
                .flota-card-metric-item:last-child { border-right: none; }
                
                .flota-card-timeline { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; padding: 6px 16px 12px 16px; border-top: 1px solid #f1f5f9; background: rgba(248,250,252,0.5); min-height: 32px; }
                .flota-avatar { width: 42px; height: 42px; border-radius: 50%; background: linear-gradient(135deg, #3b82f6, #1d4ed8); display: flex; align-items: center; justify-content: center; font-size: 1.3rem; color: #fff; flex-shrink: 0; border: 2px solid #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
                .flota-area-badge { display: inline-block; padding: 2px 8px; background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; border-radius: 6px; font-size: 0.62rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 3px; }
                
                .flota-mark { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 6px; font-size: 0.74rem; font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
                .flota-mark-e { background: linear-gradient(135deg, #d1fae5, #a7f3d0); color: #065f46; border: 1px solid #6ee7b7; }
                .flota-mark-s { background: linear-gradient(135deg, #ffe4e6, #fecdd3); color: #9f1239; border: 1px solid #fda4af; }
                .flota-mark-arrow { color: #94a3b8; font-size: 0.7rem; margin: 0 2px; }
                
                .flota-val-label { font-size: 0.6rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; }
                .flota-val-num { font-size: 0.9rem; font-weight: 800; color: #1e293b; letter-spacing: -0.01em; }
                
                .flota-status-pill { display: inline-flex; align-items: center; gap: 5px; padding: 5px 12px; border-radius: 999px; font-size: 0.7rem; font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,0.06); }
                .flota-status-pill .dot { width: 7px; height: 7px; border-radius: 50%; animation: flota-pulse 2s infinite; }
                @keyframes flota-pulse { 0%,100% { opacity:1; } 50% { opacity:0.5; } }
                .flota-status-en_planta { background: linear-gradient(135deg, #d1fae5, #a7f3d0); color: #065f46; border: 1px solid #6ee7b7; }
                .flota-status-en_planta .dot { background: #10b981; box-shadow: 0 0 4px rgba(16,185,129,0.5); }
                .flota-status-fuera { background: linear-gradient(135deg, #ffe4e6, #fecdd3); color: #9f1239; border: 1px solid #fda4af; }
                .flota-status-fuera .dot { background: #f43f5e; box-shadow: 0 0 4px rgba(244,63,94,0.5); }
                .flota-status-sin_registro { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
                .flota-status-sin_registro .dot { background: #94a3b8; animation: none; }
                
                .flota-btn-entrada { background: linear-gradient(135deg, #10b981, #059669); color: #fff; border: none; font-weight: 700; font-size: 0.78rem; padding: 8px 18px; border-radius: 8px; cursor: pointer; transition: all 0.25s ease; box-shadow: 0 2px 6px rgba(16,185,129,0.3); letter-spacing: 0.02em; }
                .flota-btn-entrada:hover { background: linear-gradient(135deg, #059669, #047857); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(16,185,129,0.4); }
                .flota-btn-entrada:active { transform: translateY(0); box-shadow: 0 1px 3px rgba(16,185,129,0.3); }
                .flota-btn-salida { background: linear-gradient(135deg, #f43f5e, #e11d48); color: #fff; border: none; font-weight: 700; font-size: 0.78rem; padding: 8px 18px; border-radius: 8px; cursor: pointer; transition: all 0.25s ease; box-shadow: 0 2px 6px rgba(244,63,94,0.3); letter-spacing: 0.02em; }
                .flota-btn-salida:hover { background: linear-gradient(135deg, #e11d48, #be123c); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(244,63,94,0.4); }
                .flota-btn-salida:active { transform: translateY(0); box-shadow: 0 1px 3px rgba(244,63,94,0.3); }
                
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
                        <div class="kpi-label">En Viaje</div>
                        <div class="d-flex align-items-baseline gap-2 mt-2">
                            <span class="kpi-number" id="flota-stat-viaje">—</span>
                            <span class="kpi-sub">fuera de planta</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ESTADO DEL DÍA -->
            <div class="card border-0 shadow-sm mb-4" style="border-radius:12px; overflow:hidden">
                <div class="flota-section-header">
                    <span class="flota-section-title">
                        <i class="bi bi-list-check" style="color:#3b82f6"></i>Monitoreo de la Flota (Hoy)
                    </span>
                    <button class="btn btn-sm text-primary fw-semibold" style="font-size:0.8rem" onclick="FlotaModule.cargarEstadoDia()">
                        <i class="bi bi-arrow-clockwise me-1"></i>Actualizar
                    </button>
                </div>
                <div id="flota-estado-body" style="background:#f8fafc; padding:6px 0">
                    <div class="text-center py-5 text-muted">
                        <div class="spinner-border spinner-border-sm text-primary"></div> Cargando...
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
    }

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

            const body = document.getElementById('flota-estado-body');
            if (!data.vehiculos.length) {
                body.innerHTML = '<div class="text-center py-5 text-muted">No hay vehículos configurados en el catálogo de flota.</div>';
                return;
            }
            body.innerHTML = data.vehiculos.map(veh => renderVehiculoCard(veh)).join('');
        } catch (e) {
            console.error(e);
            const body = document.getElementById('flota-estado-body');
            if (body) body.innerHTML = '<div class="text-center py-5 text-danger fw-bold">Error al conectar con la base de datos central</div>';
        }
    }

    function renderVehiculoCard(veh) {
        // Timeline de marcas cronológicas (ordenadas por id en el backend)
        let marcasHtml = '';
        if (veh.marcas && veh.marcas.length > 0) {
            marcasHtml = veh.marcas.map((m, i) => {
                const isE = m.tipo === 'ENTRADA';
                const cls = isE ? 'flota-mark-e' : 'flota-mark-s';
                const icon = isE ? 'bi-box-arrow-in-right' : 'bi-box-arrow-right';
                const label = isE ? 'E' : 'S';
                const arrow = i < veh.marcas.length - 1 ? '<span class="flota-mark-arrow">→</span>' : '';
                return `<span class="flota-mark ${cls}" title="Registrado por: ${m.registrado_por_nombre || 'Desconocido'}\nObservaciones: ${m.observaciones || 'Sin observaciones'}"><i class="bi ${icon}" style="font-size:0.6rem"></i>${m.hora.substring(0,5)} ${label}</span>${arrow}`;
            }).join('');
        } else {
            marcasHtml = '<span style="font-size:0.78rem; color:#94a3b8; font-style:italic">Sin movimientos hoy</span>';
        }

        // Tiempos
        const estadiaHtml = veh.estadia_display !== '—'
            ? `<span class="flota-val-num text-success">${veh.estadia_display}</span>`
            : '<span style="color:#94a3b8">—</span>';
            
        const viajeHtml = veh.viaje_display !== '—'
            ? `<span class="flota-val-num text-danger">${veh.viaje_display}</span>`
            : '<span style="color:#94a3b8">—</span>';

        // Badge de estado
        const statusClass = `flota-status-${veh.estado}`;
        const statusLabel = veh.estado === 'en_planta' ? 'En Planta' : veh.estado === 'fuera' ? 'En Viaje' : 'Sin registro';

        // Acción
        const proximaTipo = (veh.estado === 'en_planta') ? 'Salida' : 'Entrada';
        const btnClass = proximaTipo === 'Entrada' ? 'flota-btn-entrada' : 'flota-btn-salida';
        const btnIcon = proximaTipo === 'Entrada' ? 'bi-box-arrow-in-right' : 'bi-box-arrow-right';

        return `
            <div class="flota-card estado-${veh.estado}">
                <div class="flota-card-header">
                    <div class="flota-card-identity">
                        <div class="flota-avatar">🚚</div>
                        <div class="flota-card-info">
                            <div class="flota-card-name">${veh.patente}</div>
                            <span class="flota-area-badge">${veh.area}</span>
                        </div>
                    </div>
                    <div class="flota-card-metrics">
                        <div class="flota-card-metric-item">
                            <div class="flota-val-label">Estadía Planta</div>
                            ${estadiaHtml}
                        </div>
                        <div class="flota-card-metric-item">
                            <div class="flota-val-label">En Viaje</div>
                            ${viajeHtml}
                        </div>
                        <div class="flota-card-metric-item">
                            <div class="flota-val-label">Viajes</div>
                            <span class="flota-val-num">${veh.viajes_completados}</span>
                        </div>
                        <span class="flota-status-pill ${statusClass}"><span class="dot"></span>${statusLabel}</span>
                        <button class="${btnClass}" onclick="FlotaModule.marcar(${veh.id}, '${veh.patente}')">
                            ${proximaTipo} <i class="bi ${btnIcon}"></i>
                        </button>
                    </div>
                </div>
                <div class="flota-card-timeline">
                    ${marcasHtml}
                </div>
            </div>`;
    }

    // ════════════════════════════════════════════════
    // MARCAR MOVIMIENTO (CON MODAL SWAL2)
    // ════════════════════════════════════════════════
    async function marcar(flotaId, patente) {
        if (typeof Swal === 'undefined') {
            const obs = prompt("Ingrese observaciones / Chofer (Opcional):");
            if (obs === null) return; // canceló
            await ejecutarMarca(flotaId, obs);
            return;
        }

        // Modal SweetAlert2 para Chofer y Observaciones
        Swal.fire({
            title: `📝 Registrar Marca: ${patente}`,
            html: `
                <div class="text-start">
                    <div class="mb-3">
                        <label class="form-label small fw-bold text-muted">Chofer del Vehículo</label>
                        <input type="text" id="swal-flota-chofer" class="form-control" placeholder="Ej: Juan Gómez">
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
                const chofer = document.getElementById('swal-flota-chofer').value.strip ? document.getElementById('swal-flota-chofer').value.strip() : document.getElementById('swal-flota-chofer').value;
                const obs = document.getElementById('swal-flota-obs').value.strip ? document.getElementById('swal-flota-obs').value.strip() : document.getElementById('swal-flota-obs').value;
                
                let observacionesFinal = "";
                if (chofer) observacionesFinal += `Chofer: ${chofer}. `;
                if (obs) observacionesFinal += obs;
                return observacionesFinal;
            }
        }).then(async (result) => {
            if (result.isConfirmed) {
                await ejecutarMarca(flotaId, result.value);
            }
        });
    }

    async function ejecutarMarca(flotaId, observaciones) {
        try {
            const res = await fetch('/api/flota/marcar/', {
                method: 'POST',
                headers: { 
                    'Authorization': `Bearer ${localStorage.getItem('token')}`, 
                    'Content-Type': 'application/json' 
                },
                body: JSON.stringify({ flota_id: flotaId, observaciones: observaciones })
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
                    <td style="font-weight:700; color:#1e293b; letter-spacing:0.02em">${r.patente}</td>
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
                        <td class="ps-4 fw-bold text-dark font-monospace fs-5">${v.patente}</td>
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
        // Cargar áreas con cache local
        let areas = [];
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
        } catch (error) {
            console.error("Error al obtener áreas para catálogo:", error);
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
            preConfirm: () => {
                const pat = document.getElementById('swal-vehiculo-patente').value.strip ? document.getElementById('swal-vehiculo-patente').value.strip() : document.getElementById('swal-vehiculo-patente').value;
                const area = document.getElementById('swal-vehiculo-area').value;
                
                if (!pat) {
                    Swal.showValidationMessage('La patente es requerida');
                    return false;
                }
                return { patente: pat.replace(/\s+/g, '').toUpperCase(), area_id: parseInt(area) };
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
        _catalogoAreasCached = [];
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
        destroy 
    };
})();
