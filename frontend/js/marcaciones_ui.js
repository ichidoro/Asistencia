/**
 * marcaciones_ui.js
 * Módulo para visualizar Asistencia: Vista Matriz (Equipo) y Calendario (Personal).
 */

// ── Fix #A: Caché de metadata — evita llamar /api/empleados/metadata/ múltiples veces ──
// Se invalida automáticamente al agregar/editar empleados o áreas.
window._cachedMetadata = window._cachedMetadata || null;
async function getMetadata(forceRefresh = false) {
    if (!forceRefresh && window._cachedMetadata) return window._cachedMetadata;
    try {
        const resp = await fetch('/api/empleados/metadata/');
        if (resp.ok) {
            window._cachedMetadata = await resp.json();
        }
    } catch (e) {
        console.warn('Error cargando metadata:', e);
    }
    return window._cachedMetadata || { areas: [] };
}

// Evitar conflicto con versiones antiguas en caché (script fantasma)
// Usamos un nombre de variable ÚNICO para esta versión
window.stateMarcacionesApp = window.stateMarcacionesApp || {
    year: new Date().getFullYear(),
    month: new Date().getMonth() + 1,
    isModoRRHH: true,
    fechaInicioRRHH: "",
    fechaFinRRHH: "",
    usuarioModificoFechas: false,
    area: "",
    turnoId: "",
    empleadoId: "",
    viewMode: 'conceptos', // 'conceptos', 'horas', 'he', 'acumulado', 'colacion', 'permisos'
    panelMode: 'analitica', // La vista única será siempre Analítica
    data: null,
    autoRefreshEnabled: true,
    autoRefreshIntervalId: null,
    controllers: {
        filters: null
    }
};

// Estado de la Vista Analítica (si no está ya inicializado)
window.vistaAnaliticaState = window.vistaAnaliticaState || {
    soloNegativo: false,
    soloConHE: false,
    showBonos: false,
    showHE: false,
    showDeudas: false,
    showIncidencias: false,
    showSaldoMeta: true  // Visible por defecto cuando hay bolsa flexible
};

// Referencia local
// Referencia local (segura para re-declaración)
// Referencia local (segura para re-declaración)
// var stateMarcacionesApp = window.stateMarcacionesApp;

// ============================================================
// ESTADO CENTRALIZADO DEL SISTEMA PERDONAZO
// ============================================================
window._perdonazoState = window._perdonazoState || {
    activo: false,              // Switch Perdonazos ON/OFF
    seleccionados: new Set(),   // empleado_ids seleccionados via checkbox
};

// ==========================================
// INICIALIZACIÓN
// ==========================================
async function initMarcacionesUI() {
    console.log("Inicializando UI de Marcaciones (BioAlba Integration)...");

    const container = document.getElementById('page-marcaciones');
    if (!container) return; // No estamos en la página correcta o no existe el contenedor

    // Estimar fechas locales temporales para pintar el Toolbar de inmediato si no están cargadas
    let datesAlreadyLoaded = false;
    if (!stateMarcacionesApp.fechaInicioRRHH || !stateMarcacionesApp.fechaFinRRHH) {
        const now = new Date();
        const inicio = new Date(now.getFullYear(), now.getMonth() - 1, 26);
        const fin = new Date(now.getFullYear(), now.getMonth(), 25);
        stateMarcacionesApp.fechaInicioRRHH = inicio.toISOString().split('T')[0];
        stateMarcacionesApp.fechaFinRRHH = fin.toISOString().split('T')[0];
    } else {
        datesAlreadyLoaded = true;
    }

    // 1. Renderizar Estructura Base (Toolbar + Contenedor de Grilla) INMEDIATAMENTE
    renderMarcacionesToolbar(container);
    cargarPeriodosEnToolbar();

    // Colocar un loading spinner en el contenedor de vistas de inmediato
    const viewContainer = document.getElementById('marcaciones-view-container');
    if (viewContainer) {
        viewContainer.innerHTML = `
            <div class="d-flex flex-column align-items-center justify-content-center py-5 text-center" style="min-height: 250px;">
                <div class="spinner-border text-primary mb-3" role="status" style="width: 3rem; height: 3rem;">
                    <span class="visually-hidden">Cargando...</span>
                </div>
                <h6 class="text-muted fw-bold mb-1">Cargando módulo de asistencia...</h6>
                <p class="text-muted small">Por favor, espera mientras se inicializan los filtros y períodos de control.</p>
            </div>
        `;
    }

    // 2. Iniciar cargas asíncronas en paralelo (Promise.all)
    const loadActivePeriodPromise = async () => {
        if (datesAlreadyLoaded) return;
        try {
            const currentAreaName = stateMarcacionesApp.area || 'Todas';
            const activeResp = await fetch(`/api/configuracion/periodos/activo/${encodeURIComponent(currentAreaName)}/`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });
            if (activeResp.ok) {
                const activePeriod = await activeResp.json();
                if (activePeriod && activePeriod.fecha_inicio && activePeriod.fecha_fin) {
                    if (stateMarcacionesApp.usuarioModificoFechas) {
                        console.log("loadActivePeriodPromise: el usuario ya modificó las fechas manualmente. No sobreescribiendo.");
                        return;
                    }
                    stateMarcacionesApp.fechaInicioRRHH = activePeriod.fecha_inicio;
                    stateMarcacionesApp.fechaFinRRHH = activePeriod.fecha_fin;
                    console.log("Periodo activo RRHH cargado (async):", activePeriod);
                    
                    // Actualizar inputs en el DOM si el usuario no los ha modificado
                    const inputInicio = document.getElementById('rrhh-fecha-inicio');
                    const inputFin = document.getElementById('rrhh-fecha-fin');
                    if (inputInicio) inputInicio.value = activePeriod.fecha_inicio;
                    if (inputFin) inputFin.value = activePeriod.fecha_fin;
                    if (window.syncPeriodoDropdownConFechas) window.syncPeriodoDropdownConFechas();
                    return;
                }
            }
        } catch (e) {
            console.error("Error cargando periodo activo desde configuracion:", e);
        }

        // Fallback al último cierre si el período activo no está configurado
        try {
            const resp = await fetch('/api/asistencia/periodo-rrhh/ultimo-cierre/');
            if (resp.ok) {
                const ultimo = await resp.json();
                if (ultimo && ultimo.fecha_fin) {
                    if (stateMarcacionesApp.usuarioModificoFechas) {
                        console.log("Fallback ultimo-cierre: el usuario ya modificó las fechas manualmente. No sobreescribiendo.");
                        return;
                    }
                    const lastFin = new Date(ultimo.fecha_fin);
                    lastFin.setDate(lastFin.getDate() + 1);
                    stateMarcacionesApp.fechaInicioRRHH = lastFin.toISOString().split('T')[0];
                    
                    const nextFin = new Date(lastFin);
                    nextFin.setMonth(nextFin.getMonth() + 1);
                    nextFin.setDate(nextFin.getDate() - 1);
                    stateMarcacionesApp.fechaFinRRHH = nextFin.toISOString().split('T')[0];

                    const inputInicio = document.getElementById('rrhh-fecha-inicio');
                    const inputFin = document.getElementById('rrhh-fecha-fin');
                    if (inputInicio) inputInicio.value = stateMarcacionesApp.fechaInicioRRHH;
                    if (inputFin) inputFin.value = stateMarcacionesApp.fechaFinRRHH;
                    if (window.syncPeriodoDropdownConFechas) window.syncPeriodoDropdownConFechas();
                }
            }
        } catch (e) {
            console.error("Error sugiriendo periodo por defecto:", e);
        }
    };

    const loadMetadataPromise = async () => {
        try {
            // Fix #A: usar caché — no ir a la BD si ya tenemos los datos
            const metadata = await getMetadata();
            const areaSelect = document.getElementById('marcacion-area');
            if (areaSelect && metadata.areas) {
                const currentVal = areaSelect.value;
                areaSelect.innerHTML = '<option value="">Todas las Áreas</option>' +
                    metadata.areas.map(a => `<option value="${a}">${a}</option>`).join('');
                if (currentVal) areaSelect.value = currentVal;
            }
        } catch (e) {
            console.error('Error cargando metadatos de filtros:', e);
        }
    };

    // Await paralelo
    await Promise.all([loadActivePeriodPromise(), loadMetadataPromise()]);

    // 3. Cargar Filtros Dependientes (Turnos y Empleados)
    await loadMarcacionesDependentFilters();

    // Reestablecer vista inicial (reemplaza el spinner de carga)
    if (viewContainer) {
        viewContainer.innerHTML = `
            <div class="text-center py-5 text-muted opacity-50">
                <i class="bi bi-hand-index-thumb mb-2" style="font-size: 2rem;"></i>
                <p>Selecciona filtros para visualizar la asistencia.</p>
            </div>
        `;
    }

    // Iniciar auto-refresh silenciosamente al inicializar la UI
    if (stateMarcacionesApp.autoRefreshEnabled) {
        toggleAutoRefresh(true, true);
    }
}

function renderMarcacionesToolbar(container) {
    container.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <h2 class="mb-0 d-flex align-items-center gap-2">
                <i class="bi bi-calendar-check" style="color:#6366f1"></i>
                <span style="font-weight:700;color:#1e293b">Control de Asistencia</span>
            </h2>
            <div class="d-flex gap-2 align-items-center">
                <div class="btn-group shadow-sm" style="border-radius:8px;overflow:hidden">
                    ${(typeof AuthService !== 'undefined' && AuthService.hasPermission('reportes.exportar')) ? `
                    <button class="btn btn-sm btn-outline-secondary bg-white" onclick="downloadExcelReport()" title="Exportar a Excel">
                        <i class="bi bi-file-earmark-excel text-success"></i> Excel
                    </button>
                    ` : ''}
                    <button class="btn btn-sm btn-outline-secondary bg-white" onclick="window.print()" title="Imprimir Reporte">
                        <i class="bi bi-printer"></i>
                    </button>
                </div>

                <div class="btn-group shadow-sm">
                    <button class="btn btn-sm btn-outline-primary" onclick="syncMarcacionesBioAlba()">
                        <i class="bi bi-cloud-download"></i> Sincronizar BioAlba
                    </button>
                    <button class="btn btn-sm btn-outline-primary dropdown-toggle dropdown-toggle-split" 
                            data-bs-toggle="dropdown" aria-expanded="false">
                        <span class="visually-hidden">Opciones</span>
                    </button>
                    <ul class="dropdown-menu dropdown-menu-end shadow-lg border-0">
                        <li>
                            <a class="dropdown-item py-2" href="#" onclick="syncMarcacionesBioAlba(); return false;">
                                <i class="bi bi-lightning-fill text-warning"></i> Sincronización Rápida
                                <small class="d-block text-muted">Todas las áreas del mes actual</small>
                            </a>
                        </li>
                        <li><hr class="dropdown-divider"></li>
                        <li>
                            <a class="dropdown-item py-2" href="#" onclick="openSyncMarcacionesModal(); return false;">
                                <i class="bi bi-funnel text-primary"></i> Filtrar por Áreas...
                                <small class="d-block text-muted">Seleccionar áreas específicas</small>
                            </a>
                        </li>
                    </ul>
                </div>

                <div class="d-flex align-items-center bg-white border rounded-3 px-3 py-1 shadow-sm" style="height:38px;border-color:#e2e8f0 !important">
                    <div class="form-check form-switch mb-0">
                        <input class="form-check-input" type="checkbox" role="switch" id="auto-refresh-switch" 
                               ${stateMarcacionesApp.autoRefreshEnabled ? 'checked' : ''} onchange="toggleAutoRefresh(this.checked)">
                        <label class="form-check-label small fw-bold text-muted ms-1" for="auto-refresh-switch">
                            <i class="bi bi-broadcast" style="font-size:0.7rem;${stateMarcacionesApp.autoRefreshEnabled ? 'color:#10b981;' : ''}"></i>
                            Auto
                        </label>
                    </div>
                </div>

                ${AuthService.hasPermission("marcaciones.editar") ? `
                <div class="d-flex align-items-center border rounded-3 px-3 py-1 shadow-sm" 
                     id="perdonazo-switch-wrapper"
                     style="height:38px; background: ${_perdonazoState.activo ? '#f0fdf4' : '#fff'}; border-color:${_perdonazoState.activo ? '#86efac' : '#e2e8f0'} !important; transition: background 0.3s;">
                    <div class="form-check form-switch mb-0">
                        <input class="form-check-input" type="checkbox" role="switch" id="perdonazo-switch"
                               ${_perdonazoState.activo ? 'checked' : ''}
                               onchange="toggleModoPerdonazo(this.checked)"
                               style="border-color:${_perdonazoState.activo ? '#10b981' : '#e2e8f0'};">
                        <label class="form-check-label small fw-bold ms-1" for="perdonazo-switch"
                               style="color:${_perdonazoState.activo ? '#047857' : '#64748b'};">
                            <i class="bi bi-gift-fill me-1" style="color:${_perdonazoState.activo ? '#10b981' : '#64748b'}"></i>Perdonazos
                        </label>
                    </div>
                </div>
                ` : ''}

                ${AuthService.hasPermission("marcaciones.intercambio") ? `
                <button class="btn btn-sm btn-outline-primary shadow-sm ms-2" onclick="window.abrirModalIntercambio ? window.abrirModalIntercambio() : console.warn('Intercambios panel not loaded')" title="Registrar Día Compensatorio" style="height:38px; border-color:#e2e8f0; display:flex; align-items:center; gap:5px;">
                    <i class="bi bi-arrow-left-right"></i> <span class="fw-bold">Días Compensatorios</span>
                </button>
                ` : ''}

            </div>
        </div>

        <!-- Toolbar de Filtros -->
        <div class="marcaciones-filter-bar">
            <div class="row g-2 align-items-end">
                <!-- Filtro Período (NUEVO) -->
                <div class="col-md-2">
                    <label for="rrhh-periodo-select" class="form-label small fw-semibold text-muted mb-1">Período de Cierre</label>
                    <select class="form-select form-select-sm" id="rrhh-periodo-select" onchange="window.cambiarPeriodoFiltro(this.value)" style="border-color:#c7d2fe">
                        <option value="custom">-- Rango Personalizado --</option>
                    </select>
                </div>

                <!-- Filtro Tiempo (Dinámico) -->
                <div class="col-md-3">
                    <div id="filter-time-rrhh">
                        <div class="d-flex gap-2">
                            <div class="flex-grow-1">
                                <label for="rrhh-fecha-inicio" class="form-label small fw-semibold text-muted mb-1">Desde</label>
                                <input type="date" class="form-control form-control-sm" id="rrhh-fecha-inicio" 
                                       value="${stateMarcacionesApp.fechaInicioRRHH}" onchange="updateMarcacionesState('fechaInicioRRHH', this.value)" style="border-color:#c7d2fe">
                            </div>
                            <div class="flex-grow-1">
                                <label for="rrhh-fecha-fin" class="form-label small fw-semibold text-muted mb-1">Hasta</label>
                                <input type="date" class="form-control form-control-sm" id="rrhh-fecha-fin" 
                                       value="${stateMarcacionesApp.fechaFinRRHH}" onchange="updateMarcacionesState('fechaFinRRHH', this.value)" style="border-color:#c7d2fe">
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Área -->
                <div class="col-md-2">
                    <label for="marcacion-area" class="form-label small fw-semibold text-muted mb-1">Área</label>
                    <select class="form-select form-select-sm" id="marcacion-area" onchange="updateMarcacionesState('area', this.value)">
                        <option value="">Todas las Áreas</option>
                    </select>
                </div>

                <!-- Horario -->
                <div class="col-md-2">
                    <label for="marcacion-turno" class="form-label small fw-semibold text-muted mb-1">Horario</label>
                    <select class="form-select form-select-sm" id="marcacion-turno" onchange="updateMarcacionesState('turnoId', this.value)">
                        <option value="">Todos los Horarios</option>
                    </select>
                </div>

                <!-- Empleado -->
                <div class="col-md-2">
                    <label class="form-label small fw-semibold text-muted mb-1">Empleado</label>
                    <select class="form-select form-select-sm" id="marcacion-empleado" onchange="updateMarcacionesState('empleadoId', this.value)">
                        <option value="">-- Ver Todo el Equipo --</option>
                    </select>
                </div>

                <!-- Botón Ver -->
                <div class="col-md-1">
                    <button class="btn btn-sm w-100 fw-bold shadow-sm" onclick="loadMarcacionesData()" style="background:linear-gradient(135deg,#6366f1,#4f46e5);color:white;border:none;border-radius:6px;height: 31px;margin-bottom: 2px;" title="Ver">
                        <i class="bi bi-search"></i>
                    </button>
                </div>
            </div>
        </div>

        <!-- Contenedor Principal de Vistas -->
        <div id="marcaciones-view-container" class="position-relative">
            <div class="text-center py-5 text-muted opacity-50">
                <i class="bi bi-hand-index-thumb mb-2" style="font-size: 2rem;"></i>
                <p>Selecciona filtros para visualizar la asistencia.</p>
            </div>
        </div>
    `;
}

window.syncPeriodoDropdownConFechas = function() {
    const select = document.getElementById('rrhh-periodo-select');
    if (!select) return;
    
    const valToFind = `${stateMarcacionesApp.fechaInicioRRHH}|${stateMarcacionesApp.fechaFinRRHH}`;
    let found = false;
    for (let i = 0; i < select.options.length; i++) {
        if (select.options[i].value === valToFind) {
            select.selectedIndex = i;
            found = true;
            break;
        }
    }
    if (!found) {
        select.value = 'custom';
    }
    
    const inputInicio = document.getElementById('rrhh-fecha-inicio');
    const inputFin = document.getElementById('rrhh-fecha-fin');
    if (inputInicio && inputFin) {
        if (found) {
            inputInicio.setAttribute('readonly', 'true');
            inputFin.setAttribute('readonly', 'true');
        } else {
            inputInicio.removeAttribute('readonly');
            inputFin.removeAttribute('readonly');
        }
    }
};

window.cambiarPeriodoFiltro = function(val) {
    const inputInicio = document.getElementById('rrhh-fecha-inicio');
    const inputFin = document.getElementById('rrhh-fecha-fin');
    
    if (val === 'custom') {
        stateMarcacionesApp.usuarioModificoFechas = true;
        if (inputInicio) inputInicio.removeAttribute('readonly');
        if (inputFin) inputFin.removeAttribute('readonly');
    } else {
        const [fIni, fFin] = val.split('|');
        stateMarcacionesApp.fechaInicioRRHH = fIni;
        stateMarcacionesApp.fechaFinRRHH = fFin;
        stateMarcacionesApp.usuarioModificoFechas = false;
        
        if (inputInicio) {
            inputInicio.value = fIni;
            inputInicio.setAttribute('readonly', 'true');
        }
        if (inputFin) {
            inputFin.value = fFin;
            inputFin.setAttribute('readonly', 'true');
        }
        
        loadMarcacionesData();
    }
};

async function cargarPeriodosEnToolbar() {
    try {
        const resp = await fetch('/api/configuracion/periodos/', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (resp.ok) {
            const periodos = await resp.json();
            const select = document.getElementById('rrhh-periodo-select');
            if (select) {
                select.innerHTML = '<option value="custom">-- Rango Personalizado --</option>';
                
                periodos.forEach(p => {
                    const option = document.createElement('option');
                    option.value = `${p.fecha_inicio}|${p.fecha_fin}`;
                    
                    let label = `${p.mes_cierre}`;
                    if (p.estado === 'cerrado') {
                        label += ' (Cerrado)';
                    } else if (p.activo === 1 || p.activo === true) {
                        label += ' (Vigente)';
                    }
                    option.textContent = label;
                    select.appendChild(option);
                });
                
                window.syncPeriodoDropdownConFechas();
            }
        }
    } catch (e) {
        console.error("Error al cargar periodos en toolbar:", e);
    }
}

// ==========================================
// LOGICA DE ESTADO Y CARGA
// ==========================================
async function loadMarcacionesFilters() {
    try {
        // Fix #A: usar caché — no repetir la llamada HTTP si ya tenemos los datos
        const metadata = await getMetadata();

        const areaSelect = document.getElementById('marcacion-area');
        if (areaSelect && metadata.areas) {
            // Preservar valor si existe
            const currentVal = areaSelect.value;
            areaSelect.innerHTML = '<option value="">Todas las Áreas</option>' +
                metadata.areas.map(a => `<option value="${a}">${a}</option>`).join('');
            if (currentVal) areaSelect.value = currentVal;
        }

        // Cargar Dependientes (Empleados y Turnos) en una sola llamada
        await loadMarcacionesDependentFilters();

    } catch (e) {
        console.error("Error cargando filtros:", e);
        showToast("Error cargando filtros", "error");
    }
}

async function loadMarcacionesDependentFilters(onlyEmployees = false) {
    console.time("⏱️ CargaFiltrosDependientes");
    try {
        // Cancelar peticiones anteriores
        if (stateMarcacionesApp.controllers.filters) {
            stateMarcacionesApp.controllers.filters.abort();
        }
        stateMarcacionesApp.controllers.filters = new AbortController();

        const empSelect = document.getElementById('marcacion-empleado');
        const turnoSelect = document.getElementById('marcacion-turno');

        if (!onlyEmployees && turnoSelect) turnoSelect.innerHTML = '<option value="">Cargando horarios...</option>';
        if (empSelect) empSelect.innerHTML = '<option value="">Cargando empleados...</option>';

        // Endpoint consolidado con soporte de cascada
        let url = `/api/asistencia/filters-data/?area=${encodeURIComponent(stateMarcacionesApp.area || '')}`;
        if (onlyEmployees && stateMarcacionesApp.turnoId) {
            url += `&turno_id=${encodeURIComponent(stateMarcacionesApp.turnoId)}`;
        }

        const resp = await fetch(url, { signal: stateMarcacionesApp.controllers.filters.signal });
        const data = await resp.json();
        const empleados = data.empleados || [];
        const turnos = data.turnos || [];

        // Renderizar Turnos (solo si no es carga parcial de empleados)
        if (!onlyEmployees && turnoSelect) {
            const currentTurnoVal = turnoSelect.value;
            turnoSelect.innerHTML = '<option value="">Todos los Horarios</option>' +
                turnos.map(t => `<option value="${t.id}">${t.nombre}</option>`).join('');

            if (currentTurnoVal && turnos.find(t => t.id == currentTurnoVal)) {
                turnoSelect.value = currentTurnoVal;
            } else {
                stateMarcacionesApp.turnoId = "";
            }
        }

        // Renderizar Empleados
        if (empSelect) {
            if (empleados.length === 0) {
                empSelect.innerHTML = '<option value="">-- Sin empleados en esta área/horario --</option>';
            } else {
                empSelect.innerHTML = '<option value="">-- Ver Todo el Equipo (Matriz) --</option>' +
                    empleados.map(e => `<option value="${e.id}">${e.nombre_completo.toUpperCase()}</option>`).join('');
            }

            if (stateMarcacionesApp.empleadoId) empSelect.value = stateMarcacionesApp.empleadoId;
        }

    } catch (e) {
        if (e.name !== 'AbortError') {
            console.error("Error cargando datos de filtros:", e);
        }
    } finally {
        console.timeEnd("⏱️ CargaFiltrosDependientes");
    }
}

let _dependentFiltersDebounceTimer = null;

function updateMarcacionesState(key, value) {
    if (key === 'fechaInicioRRHH' || key === 'fechaFinRRHH') {
        stateMarcacionesApp.usuarioModificoFechas = true;
        stateMarcacionesApp[key] = value;
        if (window.syncPeriodoDropdownConFechas) {
            window.syncPeriodoDropdownConFechas();
        }
    } else if (key === 'month' || key === 'year') {
        stateMarcacionesApp[key] = parseInt(value, 10);
        stateMarcacionesApp.usuarioModificoFechas = false;
    } else {
        stateMarcacionesApp[key] = value;
    }

    let shouldLoadFilters = false;
    let onlyEmployees = false;

    if (key === 'month' || key === 'year') {
        // Nivel 1 cambió: resetear niveles 2-4 y recargar turnos+empleados
        stateMarcacionesApp.area = "";
        stateMarcacionesApp.turnoId = "";
        stateMarcacionesApp.empleadoId = "";
        const areaSelect = document.getElementById('marcacion-area');
        if (areaSelect) areaSelect.value = "";
        shouldLoadFilters = true;
    } else if (key === 'area') {
        // Nivel 2 cambió: resetear niveles 3-4 y recargar turnos+empleados
        stateMarcacionesApp.turnoId = "";
        stateMarcacionesApp.empleadoId = "";
        const turnoSelect = document.getElementById('marcacion-turno');
        const empSelect = document.getElementById('marcacion-empleado');
        if (turnoSelect) turnoSelect.value = "";
        if (empSelect) empSelect.value = "";
        shouldLoadFilters = true;

        // ⚡ CARGA AUTOMÁTICA DEL TRAMO ACTIVO/ABIERTO PARA EL ÁREA SELECCIONADA
        const areaName = value || 'Todas';
        fetch(`/api/configuracion/periodos/activo/${encodeURIComponent(areaName)}/`, {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        })
        .then(r => {
            if (r.ok) return r.json();
            throw new Error();
        })
        .then(activePeriod => {
            if (activePeriod && activePeriod.fecha_inicio && activePeriod.fecha_fin) {
                if (stateMarcacionesApp.usuarioModificoFechas) {
                    console.log("updateMarcacionesState: el usuario ya modificó las fechas manualmente. No sobreescribiendo.");
                    return;
                }
                stateMarcacionesApp.fechaInicioRRHH = activePeriod.fecha_inicio;
                stateMarcacionesApp.fechaFinRRHH = activePeriod.fecha_fin;
                console.log(`Periodo activo para ${areaName} cargado:`, activePeriod);
                
                const inputInicio = document.getElementById('rrhh-fecha-inicio');
                const inputFin = document.getElementById('rrhh-fecha-fin');
                if (inputInicio) inputInicio.value = activePeriod.fecha_inicio;
                if (inputFin) inputFin.value = activePeriod.fecha_fin;
                if (window.syncPeriodoDropdownConFechas) window.syncPeriodoDropdownConFechas();
            }
        })
        .catch(e => {
            console.error("Error actualizando tramo activo por área:", e);
        });
    } else if (key === 'turnoId') {
        // Nivel 3 cambió: resetear nivel 4 y recargar solo empleados (cascade)
        stateMarcacionesApp.empleadoId = "";
        const empSelect = document.getElementById('marcacion-empleado');
        if (empSelect) empSelect.value = "";
        shouldLoadFilters = true;
        onlyEmployees = true;
    }

    if (shouldLoadFilters) {
        if (_dependentFiltersDebounceTimer) {
            clearTimeout(_dependentFiltersDebounceTimer);
        }
        _dependentFiltersDebounceTimer = setTimeout(() => {
            loadMarcacionesDependentFilters(onlyEmployees);
        }, 500);
    }
}


// ── DEBOUNCE GUARD: evitar múltiples cargas simultáneas ──────────────────
let _loadMarcacionesInProgress = false;
let _loadMarcacionesDebounceTimer = null;

// Exponer globalmente para ser visible desde bypassSecurityWall y otros modales
window.loadMarcacionesData = async function() {
    // Invalidar caché de auditoría al recargar datos (estado puede haber cambiado)
    if (typeof _invalidarAuditoriaCache === 'function') _invalidarAuditoriaCache();

    // Guard: si ya está cargando, ignorar la solicitud duplicada
    if (_loadMarcacionesInProgress) {
        console.log('⏳ loadMarcacionesData: ya en progreso, ignorando llamada duplicada');
        return;
    }

    // Debounce: cancelar llamadas rápidas consecutivas (300ms)
    if (_loadMarcacionesDebounceTimer) {
        clearTimeout(_loadMarcacionesDebounceTimer);
    }

    await new Promise(resolve => {
        _loadMarcacionesDebounceTimer = setTimeout(resolve, 300);
    });

    // Verificar nuevamente después del debounce (otra llamada puede haber tomado el lock)
    if (_loadMarcacionesInProgress) {
        console.log('⏳ loadMarcacionesData: tomada por otra llamada durante debounce, saliendo');
        return;
    }

    _loadMarcacionesInProgress = true;
    try {
        return await _loadMarcacionesDataImpl();
    } finally {
        _loadMarcacionesInProgress = false;
        _loadMarcacionesDebounceTimer = null;
    }
};

let _currentMarcacionesAbortController = null;

async function _loadMarcacionesDataImpl() {
    // 🛑 ABORTAR FETCH ANTERIOR SI AÚN ESTÁ EN PROCESO
    if (_currentMarcacionesAbortController) {
        _currentMarcacionesAbortController.abort();
    }
    _currentMarcacionesAbortController = new AbortController();
    const signal = _currentMarcacionesAbortController.signal;

    const container = document.getElementById('marcaciones-view-container');
    container.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary"></div><p class="mt-2">Cargando datos...</p></div>';

    // 🛑 BLOQUEO DE SEGURIDAD (PLAN V29+)
    // El sistema valida SIEMPRE si hay empleados con marcas pero sin turno (Fantasmas)
    // El bloqueo es mandatorio para el área de responsabilidad del usuario.
    const isBlocked = await checkAuditoriaBloqueo();
    if (isBlocked) {
        console.warn("⚠️ ACCESO BLOQUEADO: Se detectaron empleados con marcas pero sin turno asignado.");
        return; 
    }

    // 🐛 DEBUG: Estado completo
    console.group('🔍 DEBUG: loadMarcacionesData');
    console.log('Estado actual:', {
        year: stateMarcacionesApp.year,
        month: stateMarcacionesApp.month,
        area: stateMarcacionesApp.area,
        turnoId: stateMarcacionesApp.turnoId,
        empleadoId: stateMarcacionesApp.empleadoId
    });
    console.log('Fecha actual real:', new Date());
    console.log('Mes actual real (0-indexed):', new Date().getMonth());
    console.log('Mes en estado (+1):', stateMarcacionesApp.month);

    try {
        let url, isCalendar = false;

        if (stateMarcacionesApp.empleadoId) {
            // MODO CALENDARIO (Individual)
            url = `/api/asistencia/calendar/?fecha_inicio=${stateMarcacionesApp.fechaInicioRRHH}&fecha_fin=${stateMarcacionesApp.fechaFinRRHH}&empleado_id=${stateMarcacionesApp.empleadoId}`;
            isCalendar = true;
        } else {
            // MODO MATRIZ (Equipo)
            // Guard: no llamar si las fechas RRHH aún no están configuradas
            if (!stateMarcacionesApp.fechaInicioRRHH || !stateMarcacionesApp.fechaFinRRHH) {
                container.innerHTML = `
                    <div class="d-flex flex-column align-items-center justify-content-center py-5 text-center">
                        <i class="bi bi-calendar-range fs-1 text-primary mb-3"></i>
                        <h5 class="text-muted">Selecciona el período de fechas</h5>
                        <p class="text-muted small">Ingresa las fechas de inicio y fin en el selector de período para cargar la matriz.</p>
                    </div>`;
                console.groupEnd();
                return;
            }
            url = `/api/asistencia/matriz/?fecha_inicio=${stateMarcacionesApp.fechaInicioRRHH}&fecha_fin=${stateMarcacionesApp.fechaFinRRHH}`;
            if (stateMarcacionesApp.area) url += `&area=${encodeURIComponent(stateMarcacionesApp.area)}`;
            if (stateMarcacionesApp.turnoId) url += `&turno_id=${stateMarcacionesApp.turnoId}`;
        }

        console.log('URL generada:', url);

        const resp = await fetch(url, { signal });
        if (!resp.ok) throw new Error("Error fetching data");
        const data = await resp.json();

        // 🛑 PREVENCIÓN DE RACE CONDITIONS: si este no es el fetch más reciente, abortamos silenciosamente el render
        if (signal.aborted) {
            console.log('Fetch de matriz completado pero obsoleto. Render abortado.');
            console.groupEnd();
            return;
        }

        console.log('Datos recibidos:', {
            periodo: data.periodo,
            feriadosCount: data.feriados?.length || 0,
            feriados: data.feriados,
            empleadosCount: Object.keys(data.matrix || {}).length
        });
        console.groupEnd();

        // LIMPIAR CONTAINER EXPLÍCITAMENTE ANTES DE RENDERIZAR
        container.innerHTML = '';
        
        stateMarcacionesApp.data = data;

        if (isCalendar) {
            renderReporteEmpleado(data, container);
        } else {
            renderVistaAnalitica(data, container);
        }

    } catch (e) {
        if (e.name === 'AbortError') {
            console.log('Fetch de matriz abortado por el usuario o nueva solicitud.');
            console.groupEnd();
        } else {
            console.error("Error cargando datos:", e);
            console.groupEnd();
            container.innerHTML = `<div class="alert alert-danger">Error cargando datos: ${e.message}</div>`;
        }
    }
}

async function syncMarcacionesBioAlba(areas = null, fechaInicioOverride = null, fechaFinOverride = null, deepSync = false) {
    const btn = document.querySelector('button[onclick="syncMarcacionesBioAlba()"]');
    const originalContent = btn ? btn.innerHTML : '';
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Conectando...'; }

    // ── RANGO DE FECHAS ─────────────────────────────────────────────────────
    // Prioridad: override del modal → rango RRHH del toolbar → primer día del mes
    let fechaInicio = fechaInicioOverride || stateMarcacionesApp.fechaInicioRRHH;
    let fechaFin    = fechaFinOverride    || stateMarcacionesApp.fechaFinRRHH;

    // Fallback: si todavía no hay fechas, usar primer y último día del mes seleccionado
    if (!fechaInicio) {
        const mes  = stateMarcacionesApp.month;
        const anio = stateMarcacionesApp.year;
        fechaInicio = `${anio}-${String(mes).padStart(2, '0')}-01`;
    }
    if (!fechaFin) {
        // Calcular el último día del mes correctamente evitando problemas de Timezone
        const mes  = stateMarcacionesApp.month;
        const anio = stateMarcacionesApp.year;
        const ultimoDia = new Date(anio, mes, 0).getDate();
        fechaFin = `${anio}-${String(mes).padStart(2, '0')}-${String(ultimoDia).padStart(2, '0')}`;
    }

    console.log(`[Sync BioAlba] Rango: ${fechaInicio} → ${fechaFin}`, areas ? `Áreas: ${areas.join(', ')}` : 'Todas las áreas', `Deep Sync: ${deepSync}`);

    // Mostrar overlay de carga SweetAlert2 sin doble spinner
    Swal.fire({
        title: '<span style="font-size:1.15rem;font-weight:800;color:#1e293b;">⚡ Sincronizando con BioAlba</span>',
        html: `
            <div class="text-center py-2" style="font-family:'Inter',sans-serif;">
                <p id="swal-sync-status" class="mb-1 fw-bold text-slate-700">Conectando con BioAlba...</p>
                <p id="swal-sync-detail" class="text-muted small mb-0">Por favor, no cierres esta ventana. El proceso tardará unos segundos.</p>
            </div>
        `,
        allowOutsideClick: false,
        allowEscapeKey: false,
        showConfirmButton: false,
        didOpen: () => {
            Swal.showLoading();
        }
    });

    try {
        // Construir payload (áreas son body, fechas van en query params)
        const payload = areas ? { areas } : {};

        // Crear AbortController para timeout de 6 minutos
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 360000);

        if (btn) btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Sincronizando...';

        const url = `/api/sync/asistencia/now/stream/?fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}&deep_sync=${deepSync}`;
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify(payload),
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            throw new Error(errData.detail || `Error HTTP ${resp.status}`);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let stats = null;

        const statusEl = document.getElementById('swal-sync-status');
        const detailEl = document.getElementById('swal-sync-detail');

        // Helper para procesar la lectura del stream SSE
        function _processSSELines(lines) {
            let eventType = null;
            let eventData = null;
            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    eventType = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    try { eventData = JSON.parse(line.slice(6)); } catch { eventData = null; }
                } else if (line === '' && eventType && eventData !== null) {
                    if (eventType === 'start') {
                        if (statusEl) statusEl.textContent = eventData.info || 'Verificando periodos...';
                    } else if (eventType === 'info') {
                        if (detailEl) detailEl.textContent = eventData.message || '';
                    } else if (eventType === 'start_recalc') {
                        if (statusEl) statusEl.textContent = 'Iniciando recálculo...';
                        if (detailEl) detailEl.textContent = `Total a procesar: ${eventData.total} empleados`;
                    } else if (eventType === 'progress') {
                        if (eventData.stage === 'download') {
                            if (statusEl) statusEl.textContent = 'Descargando de BioAlba...';
                            if (detailEl) detailEl.textContent = eventData.info || '';
                        } else if (eventData.stage === 'recalc') {
                            if (statusEl) statusEl.textContent = `Recalculando (${eventData.idx}/${eventData.total})`;
                            if (detailEl) detailEl.textContent = eventData.info || '';
                        }
                    } else if (eventType === 'done') {
                        stats = eventData;
                    } else if (eventType === 'error') {
                        throw new Error(eventData.message || 'Error durante la sincronización');
                    }
                    eventType = null;
                    eventData = null;
                }
            }
        }

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            const lines = buffer.split('\n');
            buffer = lines.pop();
            _processSSELines(lines);
        }

        // Procesar buffer residual
        if (buffer.trim()) {
            const remainingLines = buffer.split('\n');
            remainingLines.push('');
            _processSSELines(remainingLines);
        }

        if (!stats) {
            throw new Error('La conexión se cerró sin recibir el reporte de finalización.');
        }

        const nuevas        = stats.marcaciones_nuevas    ?? 0;
        const recalc        = stats.dias_recalculados     ?? 0;
        const bloqueadas    = stats.bloqueados_sin_asig   ?? 0;
        const errores       = stats.errores               ?? 0;
        const duracion      = stats.duracion_segundos     ? parseFloat(stats.duracion_segundos).toFixed(1) : '—';
        const areasLabel    = areas ? `${areas.length} área${areas.length > 1 ? 's' : ''}` : 'Todas las áreas';

        const iconoNuevas   = nuevas > 0 ? '🟢' : '⚪';
        const mensajeExtra  = nuevas === 0
            ? '<p style="color:#64748b;font-size:0.85rem;margin-top:8px;">No hay marcaciones nuevas para el período. Los datos ya estaban actualizados.</p>'
            : '';

        await Swal.fire({
            title: '<span style="font-size:1.1rem;font-weight:800;color:#1e293b;">☁️ Sincronización BioAlba</span>',
            html: `
                <div style="text-align:left;font-family:'Inter',sans-serif;">
                    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;">
                        <span style="background:#e0f2fe;color:#0369a1;font-size:0.7rem;font-weight:700;padding:3px 8px;border-radius:999px;">${areasLabel}</span>
                        <span style="background:#f1f5f9;color:#475569;font-size:0.7rem;font-weight:600;padding:3px 8px;border-radius:999px;">${fechaInicio} → ${fechaFin}</span>
                        <span style="background:#f1f5f9;color:#64748b;font-size:0.7rem;padding:3px 8px;border-radius:999px;">⏱ ${duracion}s</span>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
                        <div style="background:${nuevas > 0 ? '#f0fdf4' : '#f8fafc'};border:1px solid ${nuevas > 0 ? '#86efac' : '#e2e8f0'};border-radius:10px;padding:12px;text-align:center;">
                            <div style="font-size:1.6rem;font-weight:800;color:${nuevas > 0 ? '#16a34a' : '#94a3b8'};">${nuevas}</div>
                            <div style="font-size:0.7rem;color:#64748b;margin-top:2px;">${iconoNuevas} Marcaciones nuevas</div>
                        </div>
                        <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:12px;text-align:center;">
                            <div style="font-size:1.6rem;font-weight:800;color:#2563eb;">${recalc}</div>
                            <div style="font-size:0.7rem;color:#64748b;margin-top:2px;">📅 Días recalculados</div>
                        </div>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                        <div style="background:#fafafa;border:1px solid #e2e8f0;border-radius:8px;padding:8px 12px;display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:0.75rem;color:#64748b;">🔒 Sin asignación</span>
                            <span style="font-weight:700;color:#f59e0b;font-size:0.85rem;">${bloqueadas}</span>
                        </div>
                        <div style="background:#fafafa;border:1px solid #e2e8f0;border-radius:8px;padding:8px 12px;display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:0.75rem;color:#64748b;">❌ Errores</span>
                            <span style="font-weight:700;color:${errores > 0 ? '#dc2626' : '#10b981'};font-size:0.85rem;">${errores}</span>
                        </div>
                    </div>
                    ${mensajeExtra}
                </div>
            `,
            icon: nuevas > 0 ? 'success' : 'info',
            confirmButtonText: 'Entendido',
            confirmButtonColor: '#6366f1',
            showCloseButton: true,
            customClass: { popup: 'shadow-lg' }
        });

        if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
    } catch (e) {
        Swal.close();
        console.error('[Sync BioAlba] Error:', e);
        if (e.name === 'AbortError') {
            showToast('⏱️ Timeout: La sincronización tardó más de 6 minutos.', 'error');
        } else {
            showToast('❌ Error de sincronización: ' + e.message, 'error');
        }
        try { await window.loadMarcacionesData(); } catch (_) {}
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = originalContent; }
    }
}

// ============================================
// MODAL DE SINCRONIZACIÓN POR ÁREAS
// ============================================

function openSyncMarcacionesModal() {
    // Pre-llenar fechas desde el estado actual del toolbar
    const fInicio = stateMarcacionesApp.fechaInicioRRHH || '';
    const fFin    = stateMarcacionesApp.fechaFinRRHH    || '';

    // Destruir modal previo para re-renderizarlo con fechas actualizadas
    const existente = document.getElementById('modal-sync-marcaciones');
    if (existente) {
        bootstrap.Modal.getInstance(existente)?.dispose();
        existente.remove();
    }

    const modalHTML = `
        <div class="modal fade" id="modal-sync-marcaciones" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="bi bi-funnel"></i> Sincronizar por Áreas
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p class="text-muted mb-2">
                            <i class="bi bi-info-circle"></i>
                            Selecciona el rango de fechas y las áreas a sincronizar con BioAlba.
                        </p>
                        <!-- Rango de fechas -->
                        <div class="row g-2 mb-3">
                            <div class="col">
                                <label class="form-label small fw-semibold mb-1">Desde</label>
                                <input type="date" class="form-control form-control-sm" id="sync-areas-fecha-inicio"
                                       value="${fInicio}">
                            </div>
                            <div class="col">
                                <label class="form-label small fw-semibold mb-1">Hasta</label>
                                <input type="date" class="form-control form-control-sm" id="sync-areas-fecha-fin"
                                       value="${fFin}">
                            </div>
                        </div>
                        <!-- Selección de áreas -->
                        <div class="mb-2">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="select-all-areas-sync"
                                       onchange="toggleAllAreasSync(this.checked)">
                                <label class="form-check-label fw-bold" for="select-all-areas-sync">
                                    Seleccionar Todas
                                </label>
                            </div>
                            <hr class="my-2">
                        </div>
                        <div id="areas-sync-list" class="mb-3" style="max-height:260px;overflow-y:auto">
                            <div class="text-center">
                                <div class="spinner-border spinner-border-sm text-primary"></div>
                                <span class="ms-2">Cargando áreas...</span>
                            </div>
                        </div>
                        <!-- Sincronización profunda (Deep Sync) -->
                        <div class="mt-3 pt-2 border-top">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="sync-deep-sync">
                                <label class="form-check-label fw-bold text-danger small" for="sync-deep-sync">
                                    <i class="bi bi-exclamation-triangle"></i> Sincronización profunda (Forzar red)
                                </label>
                                <div class="form-text small">Descarga completa del periodo omitiendo la regla de meses estables.</div>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-primary" onclick="confirmSyncMarcaciones()">
                            <i class="bi bi-cloud-download"></i> Sincronizar
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHTML);

    // Cargar áreas y mostrar modal
    loadAreasForSync();
    bootstrap.Modal.getOrCreateInstance(document.getElementById('modal-sync-marcaciones')).show();
}

async function loadAreasForSync() {
    try {
        // Fix #A: usar caché — no repetir la llamada HTTP
        const data = await getMetadata();
        const areas = data.areas || [];

        const container = document.getElementById('areas-sync-list');
        if (areas.length === 0) {
            container.innerHTML = '<div class="alert alert-warning">No se encontraron áreas</div>';
            return;
        }

        container.innerHTML = areas.map(area => `
            <div class="form-check">
                <input class="form-check-input area-sync-checkbox" type="checkbox"
                       value="${area}" id="area-sync-${area.replace(/\s+/g, '-')}">
                <label class="form-check-label" for="area-sync-${area.replace(/\s+/g, '-')}">
                    ${area}
                </label>
            </div>
        `).join('');
    } catch (e) {
        console.error('Error cargando áreas:', e);
        document.getElementById('areas-sync-list').innerHTML =
            '<div class="alert alert-danger">Error cargando áreas</div>';
    }
}

function toggleAllAreasSync(checked) {
    document.querySelectorAll('.area-sync-checkbox').forEach(cb => cb.checked = checked);
}

async function confirmSyncMarcaciones() {
    const btnConfirm = document.querySelector('#modal-sync-marcaciones .btn-primary');
    if (btnConfirm) btnConfirm.blur();

    // Leer fechas del modal
    const fInicio = document.getElementById('sync-areas-fecha-inicio')?.value || '';
    const fFin    = document.getElementById('sync-areas-fecha-fin')?.value    || '';

    if (!fInicio || !fFin) {
        alert('⚠️ Debes indicar el rango de fechas (Desde / Hasta).');
        return;
    }
    if (fFin < fInicio) {
        alert('⚠️ La fecha "Hasta" no puede ser anterior a "Desde".');
        return;
    }

    const checkboxes   = document.querySelectorAll('.area-sync-checkbox:checked');
    const selectedAreas = Array.from(checkboxes).map(cb => cb.value);

    if (selectedAreas.length === 0) {
        alert('⚠️ Selecciona al menos un área para sincronizar.');
        return;
    }

    // Cerrar modal liberando foco (evita advertencia ARIA)
    const modalEl = document.getElementById('modal-sync-marcaciones');
    if (document.activeElement) document.activeElement.blur();
    
    // Leer el valor de deep_sync antes de cerrar/destruir el modal
    const deepSync = document.getElementById('sync-deep-sync')?.checked || false;
    
    bootstrap.Modal.getInstance(modalEl)?.hide();

    // Sincronizar con áreas Y rango de fechas
    await syncMarcacionesBioAlba(selectedAreas, fInicio, fFin, deepSync);
}


// ==========================================
// RENDERIZADORES
// ==========================================

// ==========================================
// RENDERIZADORES
// ==========================================

// ==========================================
// REPORTE CONSOLIDADO ENTERPRISE (V12)
// ==========================================

function calcularMetricasEmpleado(data) {
    // Clonación profunda para inmutabilidad y no afectar la grilla
    const dataList = Array.isArray(data.data) ? JSON.parse(JSON.stringify(data.data)) : (Array.isArray(data) ? JSON.parse(JSON.stringify(data)) : []);
    const infoMeta = data.info || {};
    const feriadosArray = data.feriados || [];
    
    let esBolsa = false;
    let metaMensualMinutos = 0;
    let minutosTrabajadosAcumulados = 0;
    let minutosDeuda = 0;
    let minutosHE_Aprobado = 0;
    let diasTrabajados = 0;
    let atrasosCount = 0;
    let faltasCount = 0;
    let justificacionesCount = 0;
    let salidasAdelantadasCount = 0;
    let jornadasEspecialesCount = 0;
    let permisosCount = 0;

    dataList.forEach(a => {
        if (a.horas_trabajadas) {
            minutosTrabajadosAcumulados += Math.round(a.horas_trabajadas * 60);
        }
        if (a.minutos_deuda) minutosDeuda += a.minutos_deuda;
        
        const isEsp = a.estado === 'JORNADA_ESPECIAL' || a.estado === 'EXTRA' || a.estado === 'FERIADO Y JORNADA EXTRA' || a.estado === 'DÍA LIBRE Y JORNADA EXTRA';
        
        if (!isEsp && a.estado_he === 'APROBADO' && a.minutos_extra_autorizados) {
            minutosHE_Aprobado += a.minutos_extra_autorizados;
        }
        
        if (a.estado === 'ATRASO') atrasosCount++;
        if (a.estado === 'INASISTENCIA' || (a.estado && a.estado.includes('FALTA'))) faltasCount++;
        if (a.estado && (a.estado.includes('SALIDA_ADELANTADA') || a.estado.includes('SAD'))) salidasAdelantadasCount++;
        if (a.estado === 'JORNADA_ESPECIAL' || a.estado === 'EXTRA' || a.estado === 'FERIADO Y JORNADA EXTRA' || a.estado === 'DÍA LIBRE Y JORNADA EXTRA') jornadasEspecialesCount++;
        if (a.justificacion || a.nomenclatura) justificacionesCount++;
        if (a.tiene_permiso_hora || a.permiso_activo) permisosCount++;
        
        if (['OK', 'ATRASO', 'SALIDA_ADELANTADA', 'JORNADA_ESPECIAL', 'EXTRA', 'FERIADO Y JORNADA EXTRA', 'DÍA LIBRE Y JORNADA EXTRA'].includes(a.estado)) {
            diasTrabajados++;
        }

        if (a.tipo_programacion === 'FLEXIBLE_BOLSA') {
            esBolsa = true;
            if (a.meta_mensual_minutos) metaMensualMinutos = a.meta_mensual_minutos;
            else if (a.meta_horas_semanales) metaMensualMinutos = Math.round(a.meta_horas_semanales * 60);
        }
    });

    if (esBolsa && infoMeta && infoMeta.meta_ajustada_minutos_descuento) {
        metaMensualMinutos = Math.max(0, metaMensualMinutos - infoMeta.meta_ajustada_minutos_descuento);
    }

    return {
        esBolsa,
        metaMensualMinutos,
        minutosTrabajadosAcumulados,
        minutosDeuda,
        saldoBolsa: minutosTrabajadosAcumulados - metaMensualMinutos,
        minutosHE_Aprobado,
        diasTrabajados,
        atrasosCount,
        faltasCount,
        justificacionesCount,
        salidasAdelantadasCount,
        jornadasEspecialesCount,
        permisosCount,
        dataList,
        feriadosArray
    };
}

let pdfDataCache = null;

function renderReporteEmpleado(data, container) {
    // 1. Limpieza de memoria (Sanitización)
    const oldPopovers = container.querySelectorAll('[data-bs-toggle="popover"]');
    oldPopovers.forEach(el => {
        const popover = bootstrap.Popover.getInstance(el);
        if (popover) popover.dispose();
    });
    
    // Guardar data en cache para PDF
    pdfDataCache = data;

    // Calcular Resumen (Saldo, Deuda, etc) para mostrarlo arriba del visor
    const metrics = calcularMetricasEmpleado(data);
    let summaryHtml = '';
    if (metrics.esBolsa) {
        const saldoColor = metrics.saldoBolsa >= 0 ? 'text-success' : 'text-danger';
        const saldoSigno = metrics.saldoBolsa > 0 ? '+' : (metrics.saldoBolsa < 0 ? '-' : '');
        summaryHtml = `
            <div class="row g-2 mb-3">
                <div class="col-md-3">
                    <div class="card border-0 bg-info-subtle shadow-sm h-100">
                        <div class="card-body py-2 text-center">
                            <small class="text-muted d-block">Meta Periodo</small>
                            <span class="fs-5 fw-bold text-dark tabular-nums">${formatMinutesToHHMM(metrics.metaMensualMinutos)}</span>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card border-0 bg-warning-subtle shadow-sm h-100">
                        <div class="card-body py-2 text-center">
                            <small class="text-muted d-block">Avance Real</small>
                            <span class="fs-5 fw-bold text-dark tabular-nums">${formatMinutesToHHMM(metrics.minutosTrabajadosAcumulados)}</span>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card border-0 bg-light shadow-sm h-100">
                        <div class="card-body py-2 text-center">
                            <small class="text-muted d-block">Deuda (No Justif.)</small>
                            <span class="fs-5 fw-bold text-danger tabular-nums">-${formatMinutesToHHMM(metrics.minutosDeuda)}</span>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card border-0 bg-light shadow-sm h-100">
                        <div class="card-body py-2 text-center">
                            <small class="text-muted d-block">Saldo Bolsa</small>
                            <span class="fs-5 fw-bold ${saldoColor} tabular-nums">${saldoSigno}${formatMinutesToHHMM(Math.abs(metrics.saldoBolsa))}</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    const html = `
        <div class="card shadow-sm border-0 bg-white mb-3">
            <div class="card-header bg-light border-bottom-0 d-flex justify-content-between align-items-center py-3 flex-wrap gap-2">
                <div class="d-flex align-items-center">
                    <i class="bi bi-file-earmark-pdf fs-4 text-danger me-2"></i>
                    <h6 class="mb-0 fw-bold">Visor de Reporte Consolidado (Oficial)</h6>
                </div>
                <div class="d-flex align-items-center gap-2">
                    <label class="small text-muted mb-0 fw-bold text-nowrap">Papel:</label>
                    <select id="pdf-format-select" class="form-select form-select-sm shadow-sm" style="width: 130px;" onchange="updateVisorPDF(false)">
                        <option value="a4" selected>A4</option>
                        <option value="letter">Carta (Letter)</option>
                        <option value="legal">Oficio (Legal)</option>
                    </select>
                    <button class="btn btn-sm btn-danger shadow-sm ms-2 text-nowrap" onclick="updateVisorPDF(true)">
                        <i class="bi bi-download me-1"></i> Descargar
                    </button>
                </div>
            </div>
        </div>

        ${summaryHtml}

        <div class="card shadow-sm border-0 bg-light" style="min-height: 600px;">
            <div class="card-body p-0 d-flex justify-content-center align-items-center" id="pdf-iframe-container">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Generando PDF...</span>
                </div>
            </div>
        </div>
    `;

    container.innerHTML = html;

    // Generar PDF inicial asíncronamente
    setTimeout(() => {
        updateVisorPDF(false);
    }, 50);
}

window.updateVisorPDF = function(isDownload = false) {
    if (!pdfDataCache) return;

    // 1. Seguro de vida: Validar rango de fechas para prevenir crasheos de memoria gráfica
    const startDateRaw = new Date(stateMarcacionesApp.fechaInicioRRHH);
    const endDateRaw = new Date(stateMarcacionesApp.fechaFinRRHH);
    const diffTime = Math.abs(endDateRaw - startDateRaw);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)); 
    
    if (diffDays > 93) {
        if (typeof Swal !== 'undefined') {
            Swal.fire('Periodo demasiado largo', 'Para prevenir colapsos de memoria, el reporte PDF está limitado a un máximo de 3 meses. Por favor, ajuste el filtro de fechas.', 'warning');
        } else {
            alert('El periodo es demasiado largo para este formato. Seleccione máximo 3 meses.');
        }
        return;
    }

    const formatSelect = document.getElementById('pdf-format-select');
    const format = formatSelect ? formatSelect.value : 'a4';

    const { jsPDF } = window.jspdf;
    // Forzamos orientación Horizontal (landscape) para que quepan las nuevas columnas
    const doc = new jsPDF('l', 'pt', format);
    
    const data = pdfDataCache;
    const empleadoInfo = data.empleado_info || {};
    
    let nombreEmpleado = 'Empleado no identificado';
    if (empleadoInfo.nombre) {
        nombreEmpleado = `${empleadoInfo.apellido_paterno || ''} ${empleadoInfo.apellido_materno || ''} ${empleadoInfo.nombre || ''}`.trim().replace(/  +/g, ' ');
    } else if (stateMarcacionesApp.data?.empleado_nombre) {
        nombreEmpleado = stateMarcacionesApp.data.empleado_nombre;
    }

    const rut = empleadoInfo.rut || 'No Registrado';
    const cargo = empleadoInfo.cargo || 'No Registrado';
    const area = empleadoInfo.area || stateMarcacionesApp.data?.empleado_area || stateMarcacionesApp.data?.area || 'No Registrada';

    let fechaInicio = '', fechaFin = '';
    if (data.periodo) {
        fechaInicio = window.formatFechaDDMMYYYY(data.periodo.inicio);
        fechaFin = window.formatFechaDDMMYYYY(data.periodo.fin);
    }
    
    // Header
    doc.setFont("helvetica", "bold");
    doc.setFontSize(16);
    doc.text("AGUACOL SPA", 40, 40);
    
    doc.setFontSize(10);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(100);
    doc.text("Reporte Consolidado de Asistencia", 40, 55);
    
    // Adjust header right alignment based on format width
    const pageWidth = doc.internal.pageSize.getWidth();
    doc.text(`Periodo: ${fechaInicio} al ${fechaFin}`, pageWidth - 195, 40);
    doc.text(`Generado: ${window.formatFechaDDMMYYYY(new Date())}`, pageWidth - 195, 55);
    
    doc.line(40, 65, pageWidth - 40, 65); // separator

    // Recalcular métricas para el array del AutoTable y otras lógicas
    const metrics = calcularMetricasEmpleado(data);

    // Info Empleado
    doc.setTextColor(0);
    doc.setFont("helvetica", "bold");
    doc.text("RUT:", 40, 85);
    doc.setFont("helvetica", "normal");
    doc.text(rut, 80, 85);

    doc.setFont("helvetica", "bold");
    doc.text("Nombre:", 40, 100);
    doc.setFont("helvetica", "normal");
    doc.text(nombreEmpleado, 90, 100);

    const midPoint = pageWidth / 2 + 20;
    doc.setFont("helvetica", "bold");
    doc.text("Cargo:", midPoint, 85);
    doc.setFont("helvetica", "normal");
    doc.text(cargo, midPoint + 40, 85);

    doc.setFont("helvetica", "bold");
    doc.text("Área:", midPoint, 100);
    doc.setFont("helvetica", "normal");
    doc.text(area, midPoint + 35, 100);

    const turnoNombre = data.info?.turno || 'No asignado';
    doc.setFont("helvetica", "bold");
    doc.text("Turno Asignado:", 40, 115);
    doc.setFont("helvetica", "normal");
    doc.text(turnoNombre, 125, 115);

    // Lado derecho: Horas del turno o meta de la bolsa
    doc.setFont("helvetica", "bold");
    if (metrics.esBolsa) {
        doc.text("Meta Bolsa (Hrs):", midPoint, 115);
        doc.setFont("helvetica", "normal");
        const metaHrs = (metrics.metaMensualMinutos / 60).toFixed(1);
        doc.text(`${metaHrs} Hrs`, midPoint + 95, 115);
    } else {
        doc.text("Hrs Semanales:", midPoint, 115);
        doc.setFont("helvetica", "normal");
        const hrsSemanales = data.info?.meta_horas_semanales || 45;
        doc.text(`${hrsSemanales} Hrs`, midPoint + 90, 115);
    }

    let startY = 135;
    const turnoDias = data.info?.turno_dias || {};
    if (Object.keys(turnoDias).length > 0) {
        doc.setFont("helvetica", "bold");
        doc.setFontSize(10);
        doc.text("Horario Teórico Día a Día", 40, startY);
        
        const theader = [["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]];
        const tbody = [];
        let row = [];
        for (let i = 0; i < 7; i++) {
            let config = turnoDias[i];
            if (!config || config.es_libre) {
                row.push("Libre");
            } else {
                let e = config.hora_entrada ? config.hora_entrada.substring(0, 5) : "--:--";
                let s = config.hora_salida ? config.hora_salida.substring(0, 5) : "--:--";
                let text = `${e} a ${s}`;
                if (config.hora_entrada_2 && config.hora_salida_2) {
                    let e2 = config.hora_entrada_2.substring(0, 5);
                    let s2 = config.hora_salida_2.substring(0, 5);
                    text += `\no\n${e2} a ${s2}`;
                }
                row.push(text);
            }
        }
        tbody.push(row);

        doc.autoTable({
            startY: startY + 10,
            head: theader,
            body: tbody,
            theme: 'grid',
            headStyles: { fillColor: [41, 128, 185], textColor: 255, halign: 'center', fontSize: 8 },
            bodyStyles: { halign: 'center', fontSize: 8 },
            margin: { left: 40, right: 40 }
        });
        
        startY = doc.lastAutoTable.finalY + 20;
    } else {
        startY = 140;
    }

    const tableBody = metrics.dataList.map(a => {
        let estadoStr = a.estado || '';
        let estadoBadge = estadoStr;

        // Mejorar nomenclaturas a nivel Enterprise
        if (estadoStr === 'OK') estadoBadge = 'Jornada Completa';
        else if (estadoStr === 'ATRASO' || estadoStr === 'ATR') estadoBadge = 'Atraso';
        else if (estadoStr === 'SALIDA_ADELANTADA' || estadoStr === 'SAD') estadoBadge = 'Salida Adelantada';
        else if (estadoStr === 'ATR_SAD') estadoBadge = 'Atraso / Sal. Adelantada';
        else if (estadoStr === 'INASISTENCIA' || estadoStr === 'FALTA') estadoBadge = 'Inasistencia';
        else if (estadoStr === 'INASISTENCIA_COMPENSADA') {
            if (a.deuda_condonada === 3) {
                estadoBadge = 'Compensado por Intercambio';
            } else {
                estadoBadge = 'Compensado con H.E.';
            }
        }
        else if (estadoStr === 'JORNADA_COMPENSATORIA') estadoBadge = 'Jornada Compensatoria';
        else if (estadoStr === 'LIBRE') estadoBadge = 'Día Libre';
        else if (estadoStr === 'NO_ACTIVO') estadoBadge = 'No Activo';

        // Determinar Feriado y buscar su descripción
        let feriadoDesc = null;
        if (Array.isArray(data.feriados)) {
            const ferObj = data.feriados.find(f => f === a.fecha || f.fecha === a.fecha);
            if (ferObj) feriadoDesc = ferObj.descripcion || 'Feriado';
        } else if (data.feriados && typeof data.feriados === 'object') {
            if (data.feriados[a.fecha]) feriadoDesc = data.feriados[a.fecha];
        }

        if (!feriadoDesc && metrics.feriadosArray && metrics.feriadosArray.includes(a.fecha)) {
            feriadoDesc = 'Feriado';
        }

        // Aplicar jerarquía de estados (Feriado -> Permisos -> Estado normal)
        let esJornadaEspecial = estadoStr === 'JORNADA_ESPECIAL' || estadoStr === 'EXTRA';
        let badgeEspecial = estadoStr === 'EXTRA' ? ' - Jornada Extra' : ' - Jornada Especial';

        // Determinar si el día era teóricamente libre
        let diaDate = new Date(a.fecha);
        let diaNum = (diaDate.getUTCDay() + 6) % 7;
        let esLibreTeorico = turnoDias && turnoDias[diaNum] && turnoDias[diaNum].es_libre;

        // Formatear fecha a texto amigable
        const diasSemana = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
        const meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
        let fechaFormateada = `${diasSemana[diaDate.getUTCDay()]} ${diaDate.getUTCDate()} ${meses[diaDate.getUTCMonth()]} ${diaDate.getUTCFullYear()}`.toUpperCase();

        if (feriadoDesc) {
            estadoBadge = feriadoDesc.toUpperCase().includes('FERIADO') ? feriadoDesc : `Feriado: ${feriadoDesc}`;
            if (esJornadaEspecial) estadoBadge += badgeEspecial;
        } else if (a.tiene_permiso_hora) {
            estadoBadge = 'Permiso (Horas)';
            if (esJornadaEspecial) estadoBadge += badgeEspecial;
        } else if (a.permiso_activo) {
            estadoBadge = 'Permiso (Día)';
        } else if (esLibreTeorico && esJornadaEspecial) {
            estadoBadge = 'Día Libre' + badgeEspecial;
        } else if (estadoStr === 'EXTRA') {
            estadoBadge = 'Jornada Extra';
        } else if (estadoStr === 'JORNADA_ESPECIAL') {
            estadoBadge = 'Jornada Especial';
        }
        
        const tiempoColacion = a.minutos_colacion || 0;
        
        return [
            fechaFormateada,
            estadoBadge,
            a.hora_entrada_real || '--:--',
            a.hora_salida_colacion || '--:--',
            a.hora_entrada_colacion || '--:--',
            a.hora_inicio_permiso || '--:--',
            a.hora_termino_permiso || '--:--',
            a.hora_salida_real || '--:--',
            a.horas_trabajadas > 0 ? formatDecimalToTime(a.horas_trabajadas) : '--:--',
            (a.minutos_extra_autorizados > 0) ? formatMinutesToHHMM(a.minutos_extra_autorizados) : '--:--',
            tiempoColacion > 0 ? formatMinutesToHHMM(tiempoColacion) : '--:--',
            a.minutos_atraso > 0 ? formatMinutesToHHMM(a.minutos_atraso) : '--:--',
            a.minutos_salida_adelantada > 0 ? formatMinutesToHHMM(a.minutos_salida_adelantada) : '--:--',
            a.minutos_exceso_colacion > 0 ? formatMinutesToHHMM(a.minutos_exceso_colacion) : '--:--',
            (a.minutos_permisos_detectados > 0 || a.minutos_permiso_personal_deuda > 0) ? formatMinutesToHHMM((a.minutos_permisos_detectados || 0) + (a.minutos_permiso_personal_deuda || 0)) : (a.permiso_activo ? 'Día Completo' : '--:--'),
            a.minutos_deuda > 0 ? formatMinutesToHHMM(a.minutos_deuda) : '--:--'
        ];
    });

    // AutoTable usando los datos directamente
    doc.autoTable({
        head: [
            [
                { content: 'DATOS GENERALES', colSpan: 2, styles: { halign: 'center', fillColor: [230, 230, 230] } },
                { content: 'MARCACIONES', colSpan: 6, styles: { halign: 'center', fillColor: [226, 240, 217] } },
                { content: 'TIEMPOS ACUMULADOS', colSpan: 3, styles: { halign: 'center', fillColor: [255, 242, 204] } },
                { content: 'DEUDAS E INCIDENCIAS', colSpan: 5, styles: { halign: 'center', fillColor: [252, 228, 214] } }
            ],
            ['Fecha', 'Estado', 'Entrada\nTurno', 'Inicio\nColación', 'Fin\nColación', 'Inicio\nPermiso', 'Fin\nPermiso', 'Salida\nTurno', 'Horas\nTrabajadas', 'Horas\nExtras', 'Total\nColación', 'ATRASOS', 'Salida\nAdelantada', 'Exceso\nColación', 'Permisos', 'Deuda']
        ],
        body: tableBody,
        startY: startY,
        theme: 'grid',
        styles: { font: 'helvetica', fontSize: 8, cellPadding: 4, halign: 'center' },
        headStyles: { fillColor: [240, 240, 240], textColor: [0, 0, 0], fontStyle: 'bold', halign: 'center' },
        columnStyles: {
            0: { halign: 'left', fontStyle: 'bold' }, // Fecha
            1: { halign: 'left' } // Estado
        },
        didParseCell: function(data) {
            // Condicional de color para Anomalías
            if (data.section === 'body' && data.column.index === 1) {
                const text = data.cell.text[0] || '';
                if (text === 'Inasistencia' || text.includes('FALTA')) {
                    data.cell.styles.textColor = [220, 53, 69]; // danger
                    data.cell.styles.fontStyle = 'bold';
                } else if (text.includes('Atraso') || text.includes('Salida Adelantada')) {
                    data.cell.styles.textColor = [253, 126, 20]; // warning
                } else if (text === 'Jornada Completa') {
                    data.cell.styles.textColor = [25, 135, 84]; // success
                } else if (text.toLowerCase().includes('feriado') || text.toLowerCase().includes('libre')) {
                    data.cell.styles.textColor = [13, 110, 253]; // blue for free/holiday
                }
            }
        },
        didDrawPage: function(data) {
            // Footer con paginación
            let str = 'Página ' + doc.internal.getNumberOfPages();
            doc.setFontSize(8);
            doc.setFont('helvetica', 'normal');
            doc.setTextColor(150);
            doc.text(str, data.settings.margin.left, doc.internal.pageSize.height - 20);
        }
    });

    // Cuadro Consolidado de métricas
    let finalY = doc.lastAutoTable.finalY + 20;

    if (finalY + 120 > doc.internal.pageSize.height) {
        doc.addPage();
        finalY = 40;
    }

    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);
    doc.setTextColor(0);
    doc.text("Resumen Consolidado del Período", 40, finalY);

    const formatDeuda = (mins) => {
        return formatExactMinutesToTime(mins);
    };

    const formatNeto = (mins) => {
        if (!mins || mins === 0) return '00:00:00';
        let sign = mins < 0 ? '-' : '+';
        let absMins = Math.abs(mins);
        return `${sign}${formatExactMinutesToTime(absMins)}`;
    };

    let saldoNetoMins = metrics.minutosHE_Aprobado - metrics.minutosDeuda;

    const summaryBody = [
        ['Días Trabajados', metrics.diasTrabajados],
        ['Atrasos', metrics.atrasosCount],
        ['Salidas Adelantadas', metrics.salidasAdelantadasCount],
        ['Deuda Total Bruta (HH:mm:ss)', formatDeuda(metrics.minutosDeuda)],
        ['Inasistencias', metrics.faltasCount],
        ['Justificaciones', metrics.justificacionesCount],
        ['Permisos', metrics.permisosCount],
        ['Jornadas Especiales', metrics.jornadasEspecialesCount],
        ['Horas Extras Brutas (HH:mm:ss)', formatDeuda(metrics.minutosHE_Aprobado)],
        ['Saldo Neto (HH:mm:ss)', formatNeto(saldoNetoMins)]
    ];

    doc.autoTable({
        startY: finalY + 10,
        body: summaryBody,
        theme: 'grid',
        tableWidth: 300,
        margin: { left: 40 },
        styles: { fontSize: 8, cellPadding: 3 },
        columnStyles: {
            0: { fontStyle: 'bold', fillColor: [245, 245, 245] },
            1: { halign: 'center' }
        }
    });

    finalY = doc.lastAutoTable.finalY + 50;

    // Validar espacio para firmas
    if (finalY + 50 > doc.internal.pageSize.height) {
        doc.addPage();
        finalY = 60;
    }

    doc.setTextColor(0);
    doc.setDrawColor(0);
    doc.setLineWidth(1);

    // Firmas calculadas dinámicamente según ancho de página
    const centerPoint = pageWidth / 2;
    
    // Firma Empleado (Izquierda)
    const leftMargin = centerPoint - 180;
    doc.line(leftMargin, finalY, leftMargin + 140, finalY);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(9);
    doc.text("Firma Empleado", leftMargin + 35, finalY + 15);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.text(`RUT: ${rut}`, leftMargin + 45, finalY + 25);

    // Firma Jefatura (Derecha)
    const rightMargin = centerPoint + 40;
    doc.line(rightMargin, finalY, rightMargin + 140, finalY);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(9);
    doc.text("Firma Jefatura / RRHH", rightMargin + 15, finalY + 15);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.text("Aguacol SpA", rightMargin + 45, finalY + 25);

    if (isDownload) {
        const safeArea = (area || 'SIN_AREA').replace(/[^a-zA-Z0-9_\-]/g, '_').toUpperCase();
        const safeNombre = nombreEmpleado.trim().replace(/\s+/g, '_').toUpperCase();
        let fInicio = stateMarcacionesApp.fechaInicioRRHH ? stateMarcacionesApp.fechaInicioRRHH.replace(/-/g, '') : 'INICIO';
        let fFin = stateMarcacionesApp.fechaFinRRHH ? stateMarcacionesApp.fechaFinRRHH.replace(/-/g, '') : 'FIN';
        const nombreArchivo = `${safeArea}_${safeNombre}_${fInicio}-${fFin}.pdf`;
        
        doc.save(nombreArchivo);
    } else {
        // FIX 5: Revocar blob URL anterior para evitar memory leak
        if (window._lastPdfBlobUrl) {
            URL.revokeObjectURL(window._lastPdfBlobUrl);
        }
        const blob = doc.output('blob');
        const url = URL.createObjectURL(blob);
        window._lastPdfBlobUrl = url;
        const container = document.getElementById('pdf-iframe-container');
        if (container) {
            container.innerHTML = `<iframe src="${url}" width="100%" height="800px" style="border: none; border-radius: 4px;"></iframe>`;
        }
    }
}

// Deprecated alias for compatibility with external calls if any
window.downloadReportPDF = function() {
    updateVisorPDF(true);
};


// Helpers
function generateMonthOptions(selected) {
    const months = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
    return months.map((m, i) => `<option value="${i + 1}" ${i + 1 === selected ? 'selected' : ''}>${m}</option>`).join('');
}
function generateYearOptions(selected) {
    const start = 2024;
    const end = 2030;
    let html = '';
    for (let y = start; y <= end; y++) {
        html += `<option value="${y}" ${y === selected ? 'selected' : ''}>${y}</option>`;
    }
    return html;
}

// ==========================================
// UTILIDADES DE VISTA
// ==========================================



// ── Helpers de vista única (mutuamente excluyentes) ──────────────────────────


// ── Función Maestra Universal (V15.0) ──────────────────────────
/**
 * Transforma minutos puros (decimales exactos sin truncar) en formato HH:MM:SS
 * protegiendo los cálculos matemáticos de errores visuales en PDF y UI.
 * @param {number} minsFloat 
 */
function formatExactMinutesToTime(minsFloat) {
    if (!minsFloat || minsFloat <= 0) return "00:00:00";
    const totalSecs = Math.round(minsFloat * 60);
    const h = Math.floor(totalSecs / 3600);
    const m = Math.floor((totalSecs % 3600) / 60);
    const s = totalSecs % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// Deprecated: Aliases redirigidos a la nueva función maestra
function formatDecimalToTime(decimalHours) {
    if (!decimalHours || decimalHours <= 0) return "00:00:00";
    return formatExactMinutesToTime(decimalHours * 60);
}

function formatMinutesToHHMM(totalMinutes) {
    return formatExactMinutesToTime(totalMinutes);
}
/**
 * Abre el modal de gestión de horas extra.
 */
function openHoraExtraModal(empleadoId, fecha, nombreEmpleado) {
    // Buscar los datos de este día en el estado global
    const empData = stateMarcacionesApp.data.matrix[empleadoId];
    const asist = empData ? empData[fecha] : null;

    if (!asist || !asist.minutos_extra_bruto) {
        showToast("No existen horas extra para gestionar en este día.", "info");
        return;
    }

    const mExtra = asist.minutos_extra_bruto;
    const mAuth = asist.minutos_extra_autorizados || 0;

    // Crear/Reutilizar modal
    let modalEl = document.getElementById('modal-aprobacion-he');
    if (!modalEl) {
        modalEl = document.createElement('div');
        modalEl.id = 'modal-aprobacion-he';
        // Guardar el valor exacto para usarlo al aprobar completo
        modalEl.dataset.brutoExacto = mExtra;

        const html = `
            <div class="modal-dialog modal-sm">
                <div class="modal-content shadow-lg border-0">
                    <div class="modal-header bg-primary text-white">
                        <h5 class="modal-title"><i class="bi bi-clock-history"></i> Aprobar Horas Extra</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="text-center mb-3">
                            <h6 class="text-muted small mb-1" id="he-modal-emp"></h6>
                            <div class="fw-bold" id="he-modal-fecha"></div>
                        </div>
                        
                        <div class="alert alert-info py-2 px-3 small">
                            <i class="bi bi-info-circle"></i> Total detectado: <strong id="he-modal-bruto-str"></strong>
                        </div>

                        <div class="mb-3">
                            <label for="input-he-minutos" class="form-label small">Modificar a (Minutos):</label>
                            <input type="number" id="input-he-minutos" class="form-control" step="any" placeholder="Ej: 120 para 2 horas">
                            <div class="form-text small text-muted">Deja el valor sugerido para aprobar completo.</div>
                        </div>

                        <div class="d-grid gap-2">
                            <button class="btn btn-success" id="btn-he-aprobar">
                                <i class="bi bi-check-circle"></i> Aprobar Total Completo
                            </button>
                            <button class="btn btn-outline-danger" id="btn-he-rechazar">
                                <i class="bi bi-x-circle"></i> Rechazar
                            </button>
                            <button class="btn btn-link btn-sm text-secondary" id="btn-he-pendiente">
                                Volver a Pendiente
                            </button>
                            <hr class="my-1">
                            <button type="button" class="btn btn-outline-danger btn-sm" id="btn-he-delete-manual" title="Elimina las marcaciones manuales creadas en este día">
                                <i class="bi bi-trash"></i> Eliminar Ingreso Manual
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        modalEl.classList.add('modal', 'fade');
        modalEl.setAttribute('tabindex', '-1');
        modalEl.innerHTML = html;
        document.body.appendChild(modalEl);
    } else {
        modalEl.dataset.brutoExacto = mExtra;
    }

    // Actualizar valores
    document.getElementById('he-modal-emp').innerText = nombreEmpleado;
    document.getElementById('he-modal-fecha').innerText = fecha;
    document.getElementById('he-modal-bruto-str').innerText = formatExactMinutesToTime(mExtra);
    
    // Si ya tiene autorizados, mostramos esos, sino mostramos el bruto exacto
    document.getElementById('input-he-minutos').value = mAuth || mExtra;
    document.getElementById('input-he-minutos').max = mExtra;

    // Asignar eventos dinámicos
    document.getElementById('btn-he-aprobar').onclick = () => confirmAprobacionHE(empleadoId, fecha, 'APROBADO', asist?.updated_at);
    document.getElementById('btn-he-rechazar').onclick = () => confirmAprobacionHE(empleadoId, fecha, 'RECHAZADO', asist?.updated_at);
    document.getElementById('btn-he-pendiente').onclick = () => confirmAprobacionHE(empleadoId, fecha, 'PENDIENTE', asist?.updated_at);

    const deleteManualBtn = document.getElementById('btn-he-delete-manual');
    if (deleteManualBtn) {
        deleteManualBtn.onclick = () => {
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
            if (typeof deleteManualJornada === 'function') {
                deleteManualJornada(empleadoId, fecha);
            } else {
                console.error("deleteManualJornada no está definida");
            }
        };
    }

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}
async function confirmAprobacionHE(empleadoId, fecha, estado, lastUpdatedAt) {
    const inputVal = parseFloat(document.getElementById('input-he-minutos').value);
    const brutoExacto = parseFloat(document.getElementById('modal-aprobacion-he').dataset.brutoExacto);
    
    // Si aprueba, por defecto enviamos el input, pero asegurándonos de que si el usuario no tocó nada (y tiene todo el bruto), mandamos el exacto.
    let minutos = inputVal;
    if (estado === 'APROBADO' && Math.abs(inputVal - brutoExacto) < 1) { 
        // Si la diferencia es menor a 1 minuto (ej. usuario tipea 125 para 125.55), y quería aprobar completo
        // Se envía el bruto exacto para no perder los segundos
        minutos = brutoExacto; 
    }

    try {
        const resp = await fetch('/api/asistencia/aprobar-he-batch/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify([{
                empleado_id: empleadoId,
                fecha: fecha,
                estado: estado,
                minutos_autorizados: estado === 'APROBADO' ? minutos : 0,
                last_updated_at: lastUpdatedAt || null
            }])
        });

        const result = await resp.json();
        if (resp.ok) {
            showToast(result.mensaje, "success");

            const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('modal-aprobacion-he'));
            modal.hide();

            // Recargar datos
            if (typeof window.loadMarcacionesData === 'function') {
                window.loadMarcacionesData();
            }
        } else {
            if (resp.status === 409) {
                // Conflicto de concurrencia
                showToast("Conflicto: " + result.detail, "error");
                // Forzar recarga inmediata para ver cambios externos
                if (typeof window.loadMarcacionesData === 'function') {
                    window.loadMarcacionesData();
                }
            } else {
                showToast("Error: " + result.detail, "error");
            }
        }
    } catch (e) {
        console.error("Error sincronizando BioAlba:", e);
        showToast("Error de conexión", "error");
    }
}

/**
 * ── Auto-Detección de Cambios (Smart Polling) ──────────────────────────────
 * En lugar de recargar la grilla completa cada 60s (costoso),
 * polleamos un endpoint ultraligero (/api/asistencia/last-change/)
 * que solo retorna MAX(updated_at) + COUNT(*).
 * Solo recargamos la grilla cuando detectamos un cambio real.
 * 
 * @param {boolean} enabled 
 */

// Estado interno del change-detector
window._changeDetector = window._changeDetector || {
    lastUpdate: null,
    lastCount: null,
    intervalId: null,
    isChecking: false,
};

function toggleAutoRefresh(enabled, silent = false) {
    stateMarcacionesApp.autoRefreshEnabled = enabled;
    const cd = window._changeDetector;

    // Limpiar anterior si existe
    if (cd.intervalId) {
        clearInterval(cd.intervalId);
        cd.intervalId = null;
    }

    if (enabled) {
        console.log("🔄 Auto-detección activada (30s polling ligero)");
        if (!silent) {
            showToast("Auto-detección de marcaciones activada", "info");
        }

        // Capturar el estado actual como baseline
        cd.lastUpdate = null;
        cd.lastCount = null;

        // Poll cada 30 segundos
        cd.intervalId = setInterval(() => _checkForChanges(), 30000);
        stateMarcacionesApp.autoRefreshIntervalId = cd.intervalId;

        // Primer check inmediato para establecer baseline
        _checkForChanges(true);
    } else {
        console.log("🛑 Auto-detección desactivada");
        showToast("Auto-detección desactivada", "info");
        cd.lastUpdate = null;
        cd.lastCount = null;
    }
}

/**
 * Verifica si hubo cambios usando el endpoint ligero.
 * @param {boolean} isBaseline - true si es la primera llamada (solo captura estado, no recarga)
 */
async function _checkForChanges(isBaseline = false) {
    const cd = window._changeDetector;
    const state = stateMarcacionesApp;

    // No verificar si la página no está visible o no hay datos cargados
    const container = document.getElementById('page-marcaciones');
    if (!container || !container.classList.contains('active')) return;
    if (!state.fechaInicioRRHH || !state.fechaFinRRHH) return;
    if (cd.isChecking) return;

    cd.isChecking = true;

    try {
        let url = `/api/asistencia/last-change/?fecha_inicio=${state.fechaInicioRRHH}&fecha_fin=${state.fechaFinRRHH}`;
        if (state.area) url += `&area=${encodeURIComponent(state.area)}`;

        const resp = await fetch(url);
        if (!resp.ok) return;

        const data = await resp.json();
        const newUpdate = data.last_update;
        const newCount = data.total_records;

        if (isBaseline) {
            // Primer llamada: solo guardar como referencia
            cd.lastUpdate = newUpdate;
            cd.lastCount = newCount;
            console.log(`📡 Baseline capturado: updated=${newUpdate}, records=${newCount}`);
            return;
        }

        // Comparar con el estado anterior
        const hasChanged = (
            (cd.lastUpdate !== null && cd.lastUpdate !== newUpdate) ||
            (cd.lastCount !== null && cd.lastCount !== newCount)
        );

        if (hasChanged) {
            console.log(`🔔 Cambio detectado: updated ${cd.lastUpdate} → ${newUpdate}, records ${cd.lastCount} → ${newCount}`);
            
            // Actualizar referencia ANTES de recargar
            cd.lastUpdate = newUpdate;
            cd.lastCount = newCount;

            // Mostrar toast informativo
            showToast("📡 Nuevas marcaciones detectadas. Actualizando...", "info");

            // Recargar la grilla
            if (typeof window.loadMarcacionesData === 'function') {
                window.loadMarcacionesData();
            }
        } else {
            // Sin cambios, solo actualizar referencia silenciosamente
            cd.lastUpdate = newUpdate;
            cd.lastCount = newCount;
        }

    } catch (e) {
        // Silencioso: no molestar al usuario si el endpoint falla
        console.debug('Change-detection poll error:', e.message);
    } finally {
        cd.isChecking = false;
    }
}

/**
 * Módulo de Aprobación Masiva de Horas Extra
 * Se abre al hacer doble clic en el nombre de un empleado en la grilla analítica
 */
window.openBatchApprovalModal = function (empleadoId, empNombreArg) {
    if (!stateMarcacionesApp.data || !stateMarcacionesApp.data.matrix || !stateMarcacionesApp.data.matrix[empleadoId]) {
        showToast("No se encontraron datos del empleado.", "error");
        return;
    }
    const empData = stateMarcacionesApp.data.matrix[empleadoId];
    
    // Buscar nombre del empleado
    let empNombre = empNombreArg || "Desconocido";
    if (empNombre === "Desconocido") {
        // Fallback: buscar en info o en cualquier día
        if (empData.info && empData.info.nombre_completo) {
            empNombre = empData.info.nombre_completo;
        } else {
            for (const key in empData) {
                if (empData[key]?.empleado) { empNombre = empData[key].empleado; break; }
            }
        }
    }

    // 1. Determinar el rango de fechas dinámico
    let dates = [];
    if (stateMarcacionesApp.data && stateMarcacionesApp.data.periodo) {
        let curr = new Date(stateMarcacionesApp.data.periodo.inicio + 'T00:00:00');
        let end = new Date(stateMarcacionesApp.data.periodo.fin + 'T00:00:00');
        while (curr <= end) {
            dates.push(curr.toISOString().split('T')[0]);
            curr.setDate(curr.getDate() + 1);
        }
    }

    // 2. Encontrar días con HE Detectada usando los campos correctos
    const diasHE = [];
    const dayNames = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
    dates.forEach(dateStr => {
        const di = empData[dateStr];
        if (!di) return;

        // Excluir días especiales para que no se sumen a la bolsa de HE normales
        const isEsp = di.estado === 'JORNADA_ESPECIAL' || di.estado === 'EXTRA' || di.estado === 'FERIADO Y JORNADA EXTRA' || di.estado === 'DÍA LIBRE Y JORNADA EXTRA';
        // Campo correcto: minutos_extra_bruto (usado en renderVistaAnalitica línea 2331)
        const brutoPotencial = isEsp ? 0 : (di.minutos_extra_bruto || 0);
        
        if (brutoPotencial > 0) {
            const dt = new Date(dateStr + 'T00:00:00');
            
            // --- CÁLCULO DE ORIGEN/CONTEXTO DE HORAS EXTRAS ---
            let contextoTags = [];
            
            // 1. Trabajo en Colación (Tomó menos colación de la permitida)
            if (di.minutos_colacion !== undefined && di.minutos_colacion_auto !== undefined) {
                if (di.minutos_colacion_real > 0 && di.minutos_colacion_auto > (di.minutos_colacion || 0)) {
                    let extraMin = di.minutos_colacion_auto - (di.minutos_colacion || 0);
                    contextoTags.push(`<span class="badge bg-info-subtle text-info-emphasis border border-info-subtle mb-1" title="Colación tomada: ${di.minutos_colacion_real}m de ${di.minutos_colacion_auto}m"><i class="bi bi-cup-hot"></i> +${extraMin}m (Colación reducida)</span>`);
                }
            }
            
            // 2. Llegada Temprana Efectiva (Fuera del margen de anclaje)
            if (di.hora_entrada_teorica && di.hora_entrada_real) {
                let entTeo = new Date(`1970-01-01T${di.hora_entrada_teorica}`);
                let entReal = new Date(`1970-01-01T${di.hora_entrada_real}`);
                // Ajuste por si cruza medianoche inversamente
                if (entReal > entTeo && (entReal - entTeo) > 12 * 3600000) entReal.setDate(entReal.getDate() - 1);
                
                let diffEntradaMin = Math.round((entTeo - entReal) / 60000); 
                let obsLlegada = (di.observaciones || '').toLowerCase();
                // Verificamos si hay observación de que quedó FUERA del anclaje
                if (diffEntradaMin > 0 && obsLlegada.includes('llegada anticipada') && obsLlegada.includes('fuera del anclaje')) {
                    contextoTags.push(`<span class="badge bg-primary-subtle text-primary-emphasis border border-primary-subtle mb-1"><i class="bi bi-box-arrow-in-right"></i> +${diffEntradaMin}m (Ingreso Anticipado)</span>`);
                }
            }
            
            // 3. Salida Tardía Efectiva
            if (di.hora_salida_teorica && di.hora_salida_real) {
                let salTeo = new Date(`1970-01-01T${di.hora_salida_teorica}`);
                let salReal = new Date(`1970-01-01T${di.hora_salida_real}`);
                // Ajuste por cruce de medianoche
                if (salReal < salTeo && (salTeo - salReal) > 12 * 3600000) salReal.setDate(salReal.getDate() + 1);
                
                let diffSalidaMin = Math.round((salReal - salTeo) / 60000);
                let obsSalida = (di.observaciones || '').toLowerCase();
                // Si salió tarde y no fue anclado (es decir, el tiempo real se mantuvo y generó horas)
                if (diffSalidaMin > 0 && !obsSalida.includes('salida dentro del anclaje')) {
                    contextoTags.push(`<span class="badge bg-primary-subtle text-primary-emphasis border border-primary-subtle mb-1"><i class="bi bi-box-arrow-right"></i> +${diffSalidaMin}m (Salida Tardía)</span>`);
                }
            }
            
            // 4. Día Libre / Feriado
            if (isEsp) { // Si es Extra por día libre
                contextoTags.push(`<span class="badge bg-success-subtle text-success-emphasis border border-success-subtle mb-1"><i class="bi bi-star-fill"></i> Jornada en Día Libre</span>`);
            }
            
            // Fallback si no identificó nada específico pero hay horas extras
            if (contextoTags.length === 0) {
                contextoTags.push(`<span class="text-muted small">Exceso de jornada</span>`);
            }
            // -----------------------------------------------------

            diasHE.push({
                fecha: dateStr,
                fechaLabel: `${dayNames[dt.getDay()]} ${dt.getDate()}-${String(dt.getMonth()+1).padStart(2,'0')}`,
                bruto: brutoPotencial,
                autorizados: di.minutos_extra_autorizados || 0,
                estado: (di.estado_he === 'N/A' || !di.estado_he) ? 'PENDIENTE' : di.estado_he,
                hora_entrada: di.hora_entrada_real || '--',
                hora_salida: di.hora_salida_real || '--',
                contexto: contextoTags.join('<br>')
            });
        }
    });

    // Calcular totales
    const totalBruto = diasHE.reduce((s, d) => s + d.bruto, 0);
    const totalAprobado = diasHE.reduce((s, d) => s + d.autorizados, 0);

    if (diasHE.length === 0) {
        showToast(`${empNombre} no tiene horas extra detectadas en el periodo.`, 'info');
        return;
    }

    const canApproveHE = typeof AuthService !== 'undefined' && AuthService.hasPermission("marcaciones.horas_extras");

    // 3. Construir filas de la tabla
    const heRows = diasHE.map(d => {
        const estadoBadge = d.estado === 'APROBADO' ? '<span class="badge bg-success">✅ Aprobado</span>' :
                           d.estado === 'RECHAZADO' ? '<span class="badge bg-danger">❌ Rechazado</span>' :
                           '<span class="badge bg-warning text-dark">⏳ Pendiente</span>';
        const checked = d.estado === 'PENDIENTE' ? 'checked' : '';
        const checkboxHtml = canApproveHE 
            ? `<input class="form-check-input check-item-he" type="checkbox" data-fecha="${d.fecha}" data-minutos="${d.bruto}" ${checked}>`
            : `<input class="form-check-input check-item-he" type="checkbox" disabled>`;
        const actionsHtml = canApproveHE
            ? `
                ${d.estado !== 'APROBADO' ? `<button class="btn btn-sm btn-outline-success py-0 px-2" onclick="submitSingleHE(${empleadoId},'${d.fecha}','APROBADO',${d.bruto})" title="Aprobar"><i class="bi bi-check-lg"></i></button>` : ''}
                ${d.estado !== 'RECHAZADO' ? `<button class="btn btn-sm btn-outline-danger py-0 px-2 ms-1" onclick="submitSingleHE(${empleadoId},'${d.fecha}','RECHAZADO',0)" title="Rechazar"><i class="bi bi-x-lg"></i></button>` : ''}
              `
            : `—`;
        return `<tr class="he-approval-row ${d.estado === 'PENDIENTE' ? 'table-warning-subtle' : ''}">
            <td class="text-center">${checkboxHtml}</td>
            <td class="fw-semibold">${d.fechaLabel}</td>
            <td class="font-monospace text-center">${d.hora_entrada}</td>
            <td class="font-monospace text-center">${d.hora_salida}</td>
            <td class="fw-bold text-center" style="color:#1e40af">${formatMinutesToHHMM(d.bruto)}</td>
            <td style="font-size: 0.75rem; line-height: 1.2;" class="align-middle">${d.contexto}</td>
            <td class="text-center">${estadoBadge}</td>
            <td class="text-center">${actionsHtml}</td>
        </tr>`;
    }).join('');

    // 4. Crear Modal
    const modalId = 'modalBatchHE';
    let existing = document.getElementById(modalId);
    if (existing) existing.remove();

    const modalHtml = `
        <div class="modal fade" id="${modalId}" tabindex="-1">
            <div class="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
                <div class="modal-content border-0 shadow-lg" style="border-radius:16px;overflow:hidden">
                    <div class="modal-header border-0 pb-0" style="background:linear-gradient(135deg,#eef2ff 0%,#e0e7ff 100%);padding:20px 24px 16px">
                        <div>
                            <h5 class="modal-title fw-bold mb-1" style="color:#1e293b">
                                <i class="bi bi-clock-history text-primary me-2"></i>Gestión de Horas Extra
                            </h5>
                            <p class="mb-0 text-muted" style="font-size:0.82rem">
                                <i class="bi bi-person-fill me-1"></i>${empNombre}
                                <span class="mx-2">·</span>
                                <span class="fw-semibold">${diasHE.length}</span> días con HE
                                <span class="mx-2">·</span>
                                Total: <span class="fw-bold text-primary">${formatMinutesToHHMM(totalBruto)}</span>
                            </p>
                        </div>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body p-0">
                        <div class="px-3 py-2 bg-light border-bottom d-flex justify-content-between align-items-center flex-wrap gap-2" style="font-size:0.8rem">
                            <div class="d-flex align-items-center gap-2">
                                <input type="checkbox" class="form-check-input" id="check-all-he" checked ${canApproveHE ? '' : 'disabled'} onchange="toggleAllHECells(this)">
                                <label for="check-all-he" class="form-check-label fw-semibold">Seleccionar todos</label>
                            </div>
                            ${canApproveHE ? `
                            <div class="d-flex gap-2">
                                <button class="btn btn-sm btn-approve-all" onclick="submitBatchHE(event, ${empleadoId}, 'APROBADO')">
                                    <i class="bi bi-check-all me-1"></i>Aprobar Seleccionados
                                </button>
                                <button class="btn btn-sm btn-reject-all" onclick="submitBatchHE(event, ${empleadoId}, 'RECHAZADO')">
                                    <i class="bi bi-x-circle me-1"></i>Rechazar Seleccionados
                                </button>
                            </div>
                            ` : ''}
                        </div>
                        <div class="table-responsive" style="max-height:420px;overflow-y:auto">
                            <table class="table table-sm table-hover align-middle mb-0 he-approval-table">
                                <thead class="table-light sticky-top" style="z-index:10">
                                    <tr>
                                        <th style="width:40px" class="text-center"><i class="bi bi-check2-square"></i></th>
                                        <th>Fecha</th>
                                        <th class="text-center">Entrada</th>
                                        <th class="text-center">Salida</th>
                                        <th class="text-center">HE Bruto</th>
                                        <th style="min-width: 140px;">Origen / Motivo</th>
                                        <th class="text-center">Estado</th>
                                        <th class="text-center">Acción</th>
                                    </tr>
                                </thead>
                                <tbody>${heRows}</tbody>
                            </table>
                        </div>
                    </div>
                    <div class="modal-footer border-0 bg-light" style="padding:12px 24px">
                        <div class="d-flex align-items-center gap-3 w-100">
                            <div class="d-flex gap-3" style="font-size:0.78rem">
                                <span><i class="bi bi-clock text-primary me-1"></i>Bruto: <strong>${formatMinutesToHHMM(totalBruto)}</strong></span>
                                <span><i class="bi bi-check-circle text-success me-1"></i>Aprobado: <strong class="text-success">${formatMinutesToHHMM(totalAprobado)}</strong></span>
                            </div>
                            <button type="button" class="btn btn-secondary ms-auto" data-bs-dismiss="modal">Cerrar</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const modal = new bootstrap.Modal(document.getElementById(modalId));
    modal.show();

    document.getElementById(modalId).addEventListener('hidden.bs.modal', function() {
        this.remove();
    });
};

// Acción individual: Aprobar/Rechazar una sola jornada de HE
window.submitSingleHE = async function(empId, fecha, estado, minutos) {
    try {
        const res = await fetch('/api/asistencia/aprobar-he-batch/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify([{
                empleado_id: empId,
                fecha: fecha,
                estado: estado,
                minutos_autorizados: estado === 'APROBADO' ? minutos : 0
            }])
        });
        const data = await res.json();
        if (data.success) {
            showToast(estado === 'APROBADO' ? '✅ HE Aprobada' : '❌ HE Rechazada', 'success');
            await loadMarcacionesData();
            const mEl = document.getElementById('modalBatchHE');
            if (mEl) bootstrap.Modal.getInstance(mEl)?.hide();
        } else {
            showToast('Error: ' + (data.detail || 'Error procesando'), 'danger');
        }
    } catch (e) {
        showToast('Error de conexión: ' + e.message, 'danger');
    }
};

// ==========================================
// ADMIN BYPASS: Salto de Seguridad para Superusuarios
// ==========================================
window.bypassSecurityWall = function() {
    console.log("🚀 INICIANDO BYPASS DE SEGURIDAD...");
    
    // Eliminamos confirm para evitar problemas de foco/bloqueo en el navegador
    console.log("🔓 ADMIN BYPASS ACTIVADO");
    
    // Almacenar bypass en la sesión actual para evitar que checkAuditoriaBloqueo lo vuelva a abrir
    sessionStorage.setItem('security_wall_bypass', 'true');
    // Invalidar caché de auditoría para que la próxima llamada use el bypass
    _auditoriaBloqueoCache = { result: null, timestamp: 0 };
    
    // Cerrar el modal
    const modalEl = document.getElementById('modal-regularizacion-asistencia');
    if (modalEl) {
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
    }
    
    showToast("Acceso desbloqueado mediante Bypass de Administrador", "warning");
    
    // REANUDAR CARGA: Con un pequeño delay para asegurar limpieza visual del modal
    console.log("🔄 Reanudando carga de datos tras bypass (con delay)...");
    setTimeout(() => {
        if (typeof window.loadMarcacionesData === 'function') {
            window.loadMarcacionesData();
        } else {
            console.error("❌ Error: window.loadMarcacionesData no está definida.");
        }
    }, 500);
}

// Modificar checkAuditoriaBloqueo para respetar el bypass de sesión
// ── CACHE TTL: evitar llamadas redundantes al backend ────────────────────
let _auditoriaBloqueoCache = { result: null, timestamp: 0 };
const _AUDITORIA_CACHE_TTL_MS = 60000; // 60 segundos — el estado de bloqueo no cambia entre clicks
let _auditoriaBloqueoInFlight = null;  // Promise para deduplicar llamadas concurrentes

// Invalidar caché cuando se recarga la data de marcaciones
function _invalidarAuditoriaCache() {
    _auditoriaBloqueoCache = { result: null, timestamp: 0 };
}

window.checkAuditoriaBloqueo = async function(fecha) {
    if (sessionStorage.getItem('security_wall_bypass') === 'true') {
        console.log("🔓 Bypass activo en sesión. Ignorando auditoría.");
        return false;
    }

    // Caché TTL: si la última consulta fue hace menos de 5s, reusar resultado
    const now = Date.now();
    if (_auditoriaBloqueoCache.result !== null && (now - _auditoriaBloqueoCache.timestamp) < _AUDITORIA_CACHE_TTL_MS) {
        console.log('🛡️ Auditoría (caché): reutilizando resultado previo');
        return _auditoriaBloqueoCache.result;
    }

    // Deduplicación: si ya hay una llamada en vuelo, esperar su resultado
    if (_auditoriaBloqueoInFlight) {
        console.log('🛡️ Auditoría (dedup): esperando llamada en vuelo');
        return _auditoriaBloqueoInFlight;
    }

    _auditoriaBloqueoInFlight = _checkAuditoriaBloqueoImpl(fecha);
    try {
        const result = await _auditoriaBloqueoInFlight;
        _auditoriaBloqueoCache = { result, timestamp: Date.now() };
        return result;
    } finally {
        _auditoriaBloqueoInFlight = null;
    }
};

async function _checkAuditoriaBloqueoImpl(fecha) {
    try {
        const t = Date.now();
        const resp = await fetch(`/api/asistencia/auditoria-bloqueo/?fecha=${fecha || ''}&_t=${t}`);
        if (!resp.ok) {
            console.error("❌ Error en auditoría:", resp.status);
            return false;
        }
        
        const data = await resp.json();
        console.log("🛡️ Resultado Auditoría (Raw):", data);
        
        if (data.bloqueo) {
            // Abrir el modal con la tabla de anomalías
            openRegularizacionModal(data.anomalias, data.fecha_auditada); 
            
            // Gestionar visibilidad de botones Admin (Bypass)
            const btnBypass = document.getElementById('btn-bypass-seguridad');
            if (btnBypass) {
                const canBypass = (data.can_bypass === true || data.can_bypass === 1);
                console.log("🔑 Aplicando Visibilidad Bypass:", canBypass);
                btnBypass.style.setProperty('display', canBypass ? 'block' : 'none', 'important');
                
                // ASIGNACIÓN EXPLICITA DE EVENTO
                btnBypass.onclick = function() {
                    console.log("🖱️ Click detectado en Botón Bypass");
                    window.bypassSecurityWall();
                };
            }
            
            // Habilitar cierre si es Admin
            const closeBtns = document.querySelectorAll('#modal-regularizacion-asistencia .btn-close, #modal-regularizacion-asistencia [data-bs-dismiss="modal"]');
            closeBtns.forEach(btn => {
                const canBypass = (data.can_bypass === true || data.can_bypass === 1);
                btn.style.setProperty('display', canBypass ? 'block' : 'none', 'important');
                
                // Si puede saltarse el muro, el cierre del modal también debe activar la carga
                if (canBypass) {
                    btn.onclick = function() {
                        console.log("✖️ Cierre de modal detectado (Bypass implícito)");
                        window.bypassSecurityWall();
                    };
                }
            });

            const modalEl = document.getElementById('modal-regularizacion-asistencia');
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl, {
                backdrop: (data.can_bypass) ? true : 'static',
                keyboard: (data.can_bypass) ? true : false
            });
            modal.show();
            return true; 
        }
        return false; 
    } catch (e) {
        console.error("🚨 Error crítico en auditoría:", e);
        return false; 
    }
}

window.toggleAllHECells = function (master) {
    document.querySelectorAll('.check-item-he').forEach(c => c.checked = master.checked);
};

window.submitBatchHE = async function (event, empleadoId, nuevoEstado) {
    const selected = Array.from(document.querySelectorAll('.check-item-he:checked')).map(c => ({
        empleado_id: empleadoId,
        fecha: c.dataset.fecha,
        estado: nuevoEstado,
        minutos_autorizados: nuevoEstado === 'APROBADO' ? parseFloat(c.dataset.minutos) : 0
    }));

    if (selected.length === 0) {
        alert("Por favor seleccione al menos un día.");
        return;
    }

    if (!confirm(`¿Está seguro de marcar ${selected.length} registros como ${nuevoEstado}?`)) return;

    try {
        const btn = event.target;
        const originalText = btn.innerHTML;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Procesando...';
        btn.disabled = true;

        const response = await fetch('/api/asistencia/aprobar-he-batch/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(selected)
        });

        const data = await response.json();
        if (data.success) {
            showToast(data.mensaje, 'success');
            const mEl = document.getElementById('modalBatchHE');
            const mInst = bootstrap.Modal.getInstance(mEl);
            if (mInst) mInst.hide();

            // Refrescar la matriz (usar la función correcta según el contexto)
            if (typeof window.loadMarcacionesData === 'function') {
                window.loadMarcacionesData();
            } else if (typeof loadTeamMatrix === 'function') {
                loadTeamMatrix();
            }
        } else {
            throw new Error(data.detail || 'Error en el servidor');
        }
    } catch (error) {
        console.error("Error en submitBatchHE:", error);
        alert("Error al procesar la aprobación masiva: " + error.message);
    } finally {
        // En caso de error, restaurar botón
        const btn = event.target;
        if (btn && btn.disabled) {
            btn.innerHTML = nuevoEstado === 'APROBADO' ? '✅ Aprobar Seleccionados' : '❌ Rechazar Seleccionados';
            btn.disabled = false;
        }
    }
};

function getStatusHEBadgeClass(estado) {
    switch (estado) {
        case 'APROBADO': return 'bg-success';
        case 'RECHAZADO': return 'bg-danger';
        default: return 'bg-warning text-dark';
    }
}

// ==========================================
// UTILIDADES DE BONOS
// ==========================================
function renderBonoStatus(empId, bonoName, evaluations) {
    if (!evaluations || !evaluations[empId] || !evaluations[empId][bonoName]) {
        return '<span class="text-muted" style="font-size:0.75rem;">—</span>';
    }

    const b = evaluations[empId][bonoName];

    // No aplica por cargo o contrato
    if (b.aplica === false) {
        return '<span class="text-muted" style="font-size:0.75rem;" title="No aplica por cargo/contrato">—</span>';
    }

    // Pendiente: sin días laborables aún (inicio de mes)
    if (b.califica && b.monto === 0 && b.motivo && b.motivo.startsWith('Pendiente')) {
        return `<span class="badge" style="background:#94a3b8;padding:0.4em 0.7em;min-width:55px;font-size:0.85em;" title="${b.motivo}">⏳ …</span>`;
    }

    const montoFmt   = (b.monto || 0).toLocaleString('es-CL');
    const completoFmt = (b.monto_completo || b.monto || 0).toLocaleString('es-CL');

    if (!b.califica) {
        // Perdió el bono
        return `<span class="badge bg-danger" style="opacity:0.8;padding:0.4em 0.8em;min-width:55px;font-size:0.88em;" title="Motivo: ${b.motivo || ''}">✗ NO</span>`;
    }

    if (b.proporcional) {
        // Bono proporcional — ámbar
        const pct = b.factor != null ? Math.round(b.factor * 100) : '';
        const tooltip = `$${montoFmt} de $${completoFmt} completo&#10;${b.motivo || ''}`;
        return `<span class="badge" style="background:#f59e0b;color:#1a1a1a;padding:0.4em 0.7em;min-width:55px;font-size:0.88em;font-weight:700;" title="${tooltip}">≈ $${montoFmt}</span>`;
    }

    // Bono completo — verde
    return `<span class="badge bg-success" style="padding:0.4em 1em;min-width:55px;font-size:0.95em;" title="Monto: $${montoFmt}&#10;${b.motivo || ''}">✓ SÍ</span>`;
}




/**
 * Mantiene el estado local de la regularización para callbacks
 */
const regularizacionState = {
    callbackFinal: null
};

// Apertura del modal de regularización
function openRegularizacionModal(anomalias, fecha) {
    const modalEl = document.getElementById('modal-regularizacion-asistencia');
    if (!modalEl) {
        console.error("No se encontró modal-regularizacion-asistencia en index.html");
        return;
    }

    const tbody = document.getElementById('lista-regularizacion-cuerpo');
    // a.fecha es la fecha MÍNIMA encontrada por el backend (agrupada por empleado)
    tbody.innerHTML = anomalias.map(a => {
        const fullNombre = `${a.apellido_paterno} ${a.apellido_materno || ''} ${a.nombre}`.trim().replace(/  +/g, ' ');
        return `
        <tr>
            <td>
                <div class="fw-bold text-dark">${fullNombre}</div>
                <div class="text-muted" style="font-size: 0.75rem;">RUT: ${a.rut || 'No Registrado'}</div>
            </td>
            <td><span class="badge bg-light text-dark border">${a.area}</span></td>
            <td>
                <div class="text-info small fw-bold"><i class="bi bi-calendar-check-fill me-1"></i>Desde: ${window.formatFechaDDMMYYYY(a.fecha)}</div>
                <div class="text-muted x-small">Pendiente de regularización</div>
            </td>
            <td class="text-end">
                <button class="btn btn-sm btn-primary fw-bold shadow-sm" 
                        onclick="openAsignarTurnoForzado(${a.id}, '${a.fecha}', '${a.area}', '${fullNombre.replace(/'/g, "\\'")}', '${a.cargo || ''}')">
                    <i class="bi bi-pencil-square me-1"></i> Asignar
                </button>
            </td>
        </tr>
    `}).join('');

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}

/**
 * Abre el modal de asignación individual filtrando por área.
 */
// Actualizar etiqueta dinámica de tipo de programación del turno
window.updateTurnoInfoLabel = function(e) {
    const select = e.target;
    let infoDiv = select.nextElementSibling;
    if (!infoDiv || !infoDiv.classList.contains('turno-dynamic-info')) {
        infoDiv = document.createElement('div');
        infoDiv.className = 'turno-dynamic-info form-text text-primary mt-1 fw-bold';
        select.parentNode.insertBefore(infoDiv, select.nextSibling);
    }
    
    if (select.selectedIndex >= 0 && select.value) {
        const option = select.options[select.selectedIndex];
        const tipo = option.getAttribute('data-tipo');
        const horario = option.getAttribute('data-horario');
        if (tipo) {
            infoDiv.innerHTML = `<i class="bi bi-info-square me-1"></i>Tipo Planificación: <span class="badge bg-primary text-white">${tipo}</span> <span>${horario || ''}</span>`;
            return;
        }
    }
    infoDiv.innerHTML = '';
};

async function openAsignarTurnoForzado(empleadoId, fecha, area, nombre, cargo = '') {
    const modalEl = document.getElementById('modal-asignar-turno-individual');
    if (!modalEl) return;

    // Poblar datos básicos
    document.getElementById('asig-indiv-empleado-id').value = empleadoId;
    document.getElementById('asig-indiv-fecha').value = fecha;
    document.getElementById('asig-indiv-nombre').innerText = nombre;
    
    const areaBadge = document.getElementById('asig-indiv-area-badge');
    areaBadge.innerHTML = `<span class="badge bg-info text-dark border"><i class="bi bi-geo-alt me-1"></i> ${area}</span>`;
    
    const cargoBadge = document.getElementById('asig-indiv-cargo');
    if (cargoBadge) {
        if (cargo) {
            cargoBadge.innerHTML = `<i class="bi bi-person-badge me-1"></i>${cargo}`;
            cargoBadge.classList.remove('d-none');
        } else {
            cargoBadge.classList.add('d-none');
            cargoBadge.innerHTML = '';
        }
    }


    // Ocultar la fila BioAlba hasta que RRHH decida buscar (no automático)
    const rowBioAlba = document.getElementById('asig-bioalba-row');
    if (rowBioAlba) rowBioAlba.classList.add('d-none');
    // Guardar el empleadoId para que el botón de búsqueda lo use
    const btnBuscarBioAlba = document.getElementById('asig-btn-buscar-bioalba');
    if (btnBuscarBioAlba) {
        btnBuscarBioAlba.dataset.empleadoId = empleadoId;
        btnBuscarBioAlba.disabled = false;
        btnBuscarBioAlba.innerHTML = '<i class="bi bi-search me-1"></i>Buscar 1ª marca en BioAlba';
    }

    // Cargar Turnos del área
    const selectTurno = document.getElementById('asig-indiv-turno-id');
    selectTurno.innerHTML = '<option value="">Cargando turnos de ' + area + '...</option>';
    
    try {
        const t = Date.now();
        const resp = await fetch(`/api/turnos/?area=${encodeURIComponent(area)}&activo=true&_t=${t}`);
        if (!resp.ok) {
            const errText = await resp.text();
            throw new Error(`Status: ${resp.status} - ${errText}`);
        }
        const turnos = await resp.json();
        
        if (turnos.length === 0) {
            console.warn("\u26a0\ufe0f No se encontraron turnos para el \u00e1rea:", area);
            selectTurno.innerHTML = '<option value="">❌ No hay turnos creados</option>';
            document.getElementById('asig-indiv-alerta-area').innerHTML = `<i class="bi bi-exclamation-triangle-fill me-1"></i> <strong>Error:</strong> No existen turnos configurados para <u>${area}</u>.`;
        } else {
            selectTurno.innerHTML = '<option value="">-- Seleccione el Turno Oficial --</option>' +
                turnos.map(t => {
                    const tipoPlanificacion = t.tipo_programacion === 'FLEXIBLE_BOLSA'
                        ? 'Flexible (Bolsa de Horas)'
                        : 'Ciclo Inteligente (Smart Match)';
                    const horario = t.tipo_programacion === 'DINAMICO_FLEXIBLE'
                        ? '(Múltiples opciones horarias)'
                        : '';
                    return `<option value="${t.id}" data-tipo="${tipoPlanificacion}" data-horario="${horario}">${t.nombre}</option>`;
                }).join('');
            document.getElementById('asig-indiv-alerta-area').innerHTML = `<i class="bi bi-info-circle me-1"></i> Mostrando ${turnos.length} turnos válidos para <strong>${area}</strong>.`;
            
            // Trigger change event to initialize dynamic label
            selectTurno.removeEventListener('change', window.updateTurnoInfoLabel);
            selectTurno.addEventListener('change', window.updateTurnoInfoLabel);
            selectTurno.dispatchEvent(new Event('change'));
        }
    } catch (e) {
        console.error("\u274c Error cargando turnos para:", area, e);
        selectTurno.innerHTML = `<option value="">Error al cargar turnos (${e.message})</option>`;
    }

    // Resetear checkbox BioAlba (siempre marcado al abrir)
    const chkSync = document.getElementById('asig-chk-bioalba-sync');
    if (chkSync) chkSync.checked = true;

    // Restaurar botón confirmar (en caso de que quedara en spinner de uso previo)
    const btnConfirmar = document.getElementById('btn-confirmar-asignacion-individual');
    if (btnConfirmar) {
        btnConfirmar.disabled = false;
        btnConfirmar.innerHTML = '<i class="bi bi-check-lg me-2"></i>Confirmar Asignación';
    }

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}
// Exponer globalmente para que pueda ser llamada desde onclick en main.js
window.openAsignarTurnoForzado = openAsignarTurnoForzado;

// Búsqueda bajo demanda: RRHH decide cuándo buscar la primera marcación en BioAlba
window.buscarPrimeraMarcaBioAlba = async function(btn) {
    const empleadoId = btn?.dataset?.empleadoId;
    if (!empleadoId) return;

    const rowBioAlba = document.getElementById('asig-bioalba-row');
    const valBioAlba = document.getElementById('asig-bioalba-valor');
    const btnUsarFecha = document.getElementById('asig-btn-primera-marca');

    // Estado: buscando
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Consultando BioAlba...';
    if (rowBioAlba) {
        rowBioAlba.classList.remove('d-none');
        if (valBioAlba) valBioAlba.textContent = 'Buscando desde enero 2026...';
        if (btnUsarFecha) btnUsarFecha.classList.add('d-none');
    }

    try {
        const resp = await fetch(`/api/asistencia/empleados/${empleadoId}/primera-marcacion/`);
        const data = resp.ok ? await resp.json() : null;
        const primeraMarca = data?.primera_marcacion || null;

        if (primeraMarca) {
            if (valBioAlba) valBioAlba.textContent = primeraMarca;
            if (btnUsarFecha) {
                btnUsarFecha.dataset.fecha = primeraMarca;
                btnUsarFecha.classList.remove('d-none');
            }
            btn.innerHTML = '<i class="bi bi-check-circle me-1 text-success"></i>BioAlba consultado';
        } else {
            if (valBioAlba) valBioAlba.textContent = data?.motivo || 'Sin marcaciones históricas en BioAlba';
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-search me-1"></i>Buscar 1ª marca en BioAlba';
        }
    } catch (e) {
        if (valBioAlba) valBioAlba.textContent = 'Error conectando a BioAlba';
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i>Reintentar';
    }
};

async function saveAsignacionIndividual() {
    const empleadoId = document.getElementById('asig-indiv-empleado-id').value;
    const fecha = document.getElementById('asig-indiv-fecha').value;
    const turnoId = document.getElementById('asig-indiv-turno-id').value;
    const nombre = document.getElementById('asig-indiv-nombre').innerText;

    // ── Detectar modo batch ───────────────────────────────────────────────────
    const isBatchTurnos = typeof _batch !== 'undefined' && _batch.active && _batch.phase === 'turnos';

    // En batch: nunca sincronizar individualmente; se hace todo junto en Fase Sync
    const syncBioAlba = isBatchTurnos
        ? false
        : (document.getElementById('asig-chk-bioalba-sync')?.checked ?? true);

    if (!fecha) return showToast("Debe seleccionar una fecha de inicio", "warning");
    if (!turnoId) return showToast("Debe seleccionar un turno", "warning");

    // ── Spinner en botón ────────────────────────────────────────────────────
    const btn = document.getElementById('btn-confirmar-asignacion-individual');
    const btnOrigHtml = btn?.innerHTML;
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Procesando...';
    }

    try {
        const resp = await fetch('/api/asistencia/asignaciones/individual/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                empleado_id: parseInt(empleadoId),
                fecha: fecha,
                turno_id: parseInt(turnoId),
                sync_bioalba: syncBioAlba,
                skip_reproceso: isBatchTurnos,  // batch: solo guarda turno, sin reproceso individual
            })
        });

        if (resp.ok) {
            const data = await resp.json();
            const jobId = data.job_id || null;

            showToast("✅ Turno asignado. Iniciando proceso...", "success");

            // Cerrar modal de asignación
            const modalAsig = bootstrap.Modal.getInstance(document.getElementById('modal-asignar-turno-individual'));
            if (modalAsig) modalAsig.hide();

            // ── MODO BATCH: recolectar payload y avanzar cola ────────────────
            if (isBatchTurnos) {
                // Guardar datos para el batch-sync final
                if (typeof _batch !== 'undefined') {
                    _batch.syncPayload.push({
                        empleado_id: parseInt(empleadoId),
                        fecha_inicio: fecha,
                    });
                    console.log(
                        `[Batch/Turnos] Turno registrado para emp ${empleadoId} desde ${fecha}. ` +
                        `Payload: ${_batch.syncPayload.length} / ${_batch.editedEmployees.length}`
                    );
                }
                // Avanzar al siguiente empleado en la cola de turnos
                // (procesarColaOnboarding detectará si quedan más o lanzará batch-sync)
                if (typeof procesarColaOnboarding === 'function') {
                    setTimeout(procesarColaOnboarding, 400);
                }
                return;  // ← No abrir modal de progreso ni calibración en batch
            }

            // ── MODO INDIVIDUAL: flujo original con progreso y calibración ───
            if (jobId) {
                setTimeout(() => abrirModalProgresoJob(jobId, nombre, fecha, {
                    syncBioAlba,
                    onComplete: () => {
                        if (!(typeof _isOnboardingFlow !== 'undefined' && _isOnboardingFlow === false)) {
                            const turnoNombre = document.getElementById('asig-indiv-turno-id').options[
                                document.getElementById('asig-indiv-turno-id').selectedIndex
                            ]?.text || 'Turno Asignado';
                            openCalibracionHistorica({ empleadoId: parseInt(empleadoId), nombre, fecha, turnoNombre });
                        }
                    }
                }), 350);
            }

            // ── Flujo post-asignación sin job_id (fallback) ──────────────────
            if (!jobId) {
                if (typeof _isOnboardingFlow !== 'undefined' && _isOnboardingFlow === false) {
                    const isBlocked = await checkAuditoriaBloqueo();
                    if (!isBlocked) {
                        const modalReg = bootstrap.Modal.getInstance(document.getElementById('modal-regularizacion-asistencia'));
                        if (modalReg) modalReg.hide();
                        showToast("✅ Regularización completada.", "success");
                        if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
                    }
                } else {
                    const turnoNombre = document.getElementById('asig-indiv-turno-id').options[
                        document.getElementById('asig-indiv-turno-id').selectedIndex
                    ]?.text || 'Turno Asignado';
                    setTimeout(() => openCalibracionHistorica({ empleadoId: parseInt(empleadoId), nombre, fecha, turnoNombre }), 350);
                }
            }

        } else {
            const err = await resp.json();
            showToast("❌ " + (err.detail || "No se pudo asignar el turno"), "danger");
        }
    } catch (e) {
        console.error(e);
        showToast("❌ Error de conexión al asignar turno", "danger");
    } finally {
        // Restaurar botón siempre
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = btnOrigHtml || '<i class="bi bi-check-lg me-2"></i>Confirmar Asignación';
        }
    }
}



// =====================================================================
// [RFC PASO 7] MODAL DE CALIBRACIÓN HISTÓRICA
// =====================================================================

// Estado del contexto de calibración
let _calibContext = {};

function openCalibracionHistorica({ empleadoId, nombre, fecha, turnoNombre }) {
    _calibContext = { empleadoId, nombre, fecha, turnoNombre };

    // Poblar resumen del turno asignado
    document.getElementById('calib-emp-nombre').textContent = nombre;
    document.getElementById('calib-turno-nombre').textContent = turnoNombre;
    document.getElementById('calib-fecha-asignacion').textContent = fecha;

    // La fecha ya fue decidida por RRHH en el modal anterior → pasarla al campo oculto
    document.getElementById('calib-fecha-inicio').value = fecha;

    // Guardar el empleadoId para el sync individual
    const calibEmpId = document.getElementById('calib-empleado-id');
    if (calibEmpId) calibEmpId.value = empleadoId || '';

    // Mostrar la fecha en el botón de confirmación
    const displayFecha = document.getElementById('calib-fecha-display');
    if (displayFecha) displayFecha.textContent = fecha;

    // Resetear checkbox a su valor por defecto (marcado)
    const chkBioAlba = document.getElementById('calib-chk-bioalba');
    if (chkBioAlba) chkBioAlba.checked = true;

    const modalEl = document.getElementById('modal-calibracion-historica');
    if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();
}


// Omitir: solo confirmar que el turno quedó asignado; no reprocesar histórico
window.omitirCalibracion = function() {
    const modalEl = document.getElementById('modal-calibracion-historica');
    if (modalEl) bootstrap.Modal.getInstance(modalEl)?.hide();
    showToast("Turno asignado. Sin reproceso retroactivo.", "info");
    // Continuar con el siguiente en la cola de onboarding (si existe)
    if (typeof procesarColaOnboarding === 'function' && typeof onboardingQueue !== 'undefined' && onboardingQueue.length > 0) {
        setTimeout(procesarColaOnboarding, 500);
    }
};

// Confirmar: cierra la modal Y lanza polling de progreso en background
window.confirmarCalibracion = async function() {
    const fechaInicio = document.getElementById('calib-fecha-inicio').value;
    if (!fechaInicio) return showToast("Seleccione una fecha de inicio", "warning");

    const empleadoId = document.getElementById('calib-empleado-id')?.value;
    const syncBioAlba = document.getElementById('calib-chk-bioalba')?.checked ?? true;

    // 1. Cerrar modal de inmediato — NO bloquear al usuario
    const modalEl = document.getElementById('modal-calibracion-historica');
    if (modalEl) bootstrap.Modal.getInstance(modalEl)?.hide();

    // 2. Si el checkbox está marcado, disparar sync individual de BioAlba (fire-and-forget)
    if (syncBioAlba && empleadoId) {
        showToast("☁️ Descargando marcaciones desde BioAlba...", "info");
        // Fire-and-forget — el reproceso en background leerá las marcas cuando terminen de llegar
        fetch(`/api/sync/asistencia/empleado/${empleadoId}/?fecha_inicio=${fechaInicio}`, {
            method: 'POST'
        }).then(r => r.ok
            ? showToast("✅ Marcaciones BioAlba descargadas. El reproceso se actualizará.", "success")
            : showToast("⚠️ No se pudieron descargar marcaciones de BioAlba.", "warning")
        ).catch(() => showToast("⚠️ Error conectando a BioAlba.", "warning"));
    }

    // 3. Iniciar polling de progreso (el reproceso ya está corriendo en background)
    iniciarPollingReproceso(_calibContext.empleadoId, _calibContext.nombre, fechaInicio);

    // 4. Continuar con el siguiente en la cola de onboarding
    if (typeof procesarColaOnboarding === 'function' && typeof onboardingQueue !== 'undefined' && onboardingQueue.length > 0) {
        setTimeout(procesarColaOnboarding, 500);
    }
};


// ==========================================================================
// F2: MODAL DE PROGRESO CON JOB_ID (Polling) — Dos fases: syncing + running
// ==========================================================================

let _reprocesoJobId = null;
let _reprocesoPollingTimer = null;

/**
 * Abre el modal de progreso y comienza el polling al endpoint /api/asistencia/jobs/{job_id}/.
 * Soporta dos fases secuenciales:
 *   Fase 1 (status='syncing'): descarga BioAlba
 *   Fase 2 (status='running'): reproceso día a día
 * @param {string} jobId   - ID del job
 * @param {string} nombre  - Nombre del empleado
 * @param {string} fechaDesde - Fecha de inicio
 * @param {object} opts    - { syncBioAlba: bool, onComplete: fn }
 */
function abrirModalProgresoJob(jobId, nombre, fechaDesde, opts = {}) {
    _reprocesoJobId = jobId;
    if (_reprocesoPollingTimer) clearInterval(_reprocesoPollingTimer);

    const { syncBioAlba = false, onComplete = null, allJobIds = null } = opts;
    let _onCompleteCallback = onComplete;
    const _allJobs = allJobIds || [jobId];  // Todos los jobs del batch

    // ── Resetear estado del modal ───────────────────────────────
    const el = id => document.getElementById(id);
    const syncLabel = syncBioAlba ? ' · Incluye sync BioAlba' : '';
    el('repr-emp-nombre').textContent = `${nombre} · desde ${fechaDesde}${syncLabel}`;
    el('repr-header-title').textContent = syncBioAlba ? 'Sincronizando y Calculando...' : 'Reprocesando Asistencia';
    el('repr-progress-bar').style.width = '2%';
    el('repr-progress-bar').style.background = 'linear-gradient(90deg,#0ea5e9,#2563eb)';
    el('repr-progress-bar').classList.add('progress-bar-animated', 'progress-bar-striped');
    el('repr-pct').textContent = '0%';
    el('repr-pct').className = 'badge rounded-pill bg-info';
    el('repr-day-label').textContent = syncBioAlba ? '☁️ Descargando marcaciones BioAlba...' : 'Iniciando cálculo...';
    el('repr-counter').textContent = syncBioAlba ? 'Fase 1 de 2: Sincronización' : 'Iniciando...';
    el('repr-log').innerHTML = `<span style="color:#38bdf8;">⟳</span> ${syncBioAlba ? 'Conectando a BioAlba...' : 'Esperando inicio del proceso...'}`;
    el('repr-footer-completado').classList.add('d-none');
    el('repr-header-spinner').classList.remove('d-none');
    el('repr-header-ok').classList.add('d-none');

    // ── Abrir modal ─────────────────────────────────────────────
    const modalEl = document.getElementById('modal-reproceso-progreso');
    if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();

    let prevDayIndex = -1;
    let prevPhase = null;

    // ── Polling adaptativo ───────────────────────────────────────────────────
    // Durante 'syncing' (descarga BioAlba, lenta): intervalo crece hasta 4s.
    // Durante 'running' (cálculo día a día, rápido): vuelve a 1.5s.
    // Esto reduce requests innecesarios durante la fase de red sin sacrificar
    // la respuesta visual en la fase de cálculo.
    const POLL_FAST = 1500;   // ms — fase running / completado
    const POLL_SLOW = 4000;   // ms — fase syncing (BioAlba network bound)
    let _currentPollInterval = POLL_FAST;

    function _restartPolling(newInterval) {
        if (newInterval === _currentPollInterval) return; // ya en el intervalo correcto
        clearInterval(_reprocesoPollingTimer);
        _currentPollInterval = newInterval;
        _reprocesoPollingTimer = setInterval(_pollTick, _currentPollInterval);
    }

    async function _pollTick() {
        try {
            const r = await fetch(`/api/asistencia/jobs/${jobId}/`);
            if (!r.ok) return;
            const s = await r.json();

            // Job perdido (típicamente porque Cloud Run reemplazó la instancia durante un deploy)
            if (s.status === 'not_found') {
                clearInterval(_reprocesoPollingTimer);
                const bar = el('repr-progress-bar');
                bar.classList.remove('progress-bar-animated', 'progress-bar-striped');
                bar.style.background = 'linear-gradient(90deg,#f59e0b,#d97706)';
                bar.style.width = '100%';
                el('repr-pct').textContent = '⚠️';
                el('repr-pct').className = 'badge rounded-pill bg-warning text-dark';
                el('repr-header-title').textContent = 'Proceso Interrumpido';
                el('repr-day-label').textContent = 'El servidor se reinició durante el proceso.';
                el('repr-counter').textContent = 'Los datos ya sincronizados están guardados.';
                el('repr-resumen-texto').textContent = 'El proceso fue interrumpido por una actualización del servidor. Los empleados y marcaciones descargados antes de la interrupción se guardaron correctamente. Puede reintentar la sincronización de marcaciones desde la grilla.';
                el('repr-resumen').classList.remove('d-none');
                el('repr-done-actions').classList.remove('d-none');
                const logEl = el('repr-log');
                const warnLine = document.createElement('div');
                warnLine.style.color = '#fbbf24';
                warnLine.textContent = `⚠️ Job ${jobId} no encontrado — el servidor fue reiniciado`;
                logEl.appendChild(warnLine);
                logEl.scrollTop = logEl.scrollHeight;
                return;
            }

            const phase = s.status;      // 'syncing' | 'running' | 'done' | 'completed' | 'error'
            const pct = s.pct ?? 0;
            const isCompleted = phase === 'done' || phase === 'completed';  // backend usa 'done'
            const isError = phase === 'error';
            const isSyncing = phase === 'syncing';
            const isRunning = phase === 'running';

            // ── FASE: syncing (BioAlba) ───────────────────────────
            if (isSyncing) {
                _restartPolling(POLL_SLOW); // BioAlba es lento — reducir requests
                const phaseLabel = s.phase_label || 'Descargando marcaciones BioAlba...';
                el('repr-progress-bar').style.background = 'linear-gradient(90deg,#0ea5e9,#2563eb)';
                // Actualizar barra proporcional al pct reportado por el backend
                el('repr-progress-bar').style.width = `${Math.max(pct, 2)}%`;
                el('repr-pct').className = 'badge rounded-pill bg-info';
                el('repr-pct').textContent = `${pct}%`;
                el('repr-day-label').textContent = `☁️ ${phaseLabel}`;
                el('repr-counter').textContent = 'Fase 1 de 2: Sincronización BioAlba';

                // Agregar entrada al log al cambiar de fase
                if (prevPhase !== 'syncing') {
                    prevPhase = 'syncing';
                    const logEl = el('repr-log');
                    const line = document.createElement('div');
                    line.style.color = '#38bdf8';
                    line.textContent = `☁️ Conectado a BioAlba — descargando marcaciones...`;
                    logEl.appendChild(line);
                    logEl.scrollTop = logEl.scrollHeight;
                }
                return;  // aún en fase 1, no actualizar barra animada de días
            }

            // ── TRANSICION syncing → running ───────────────────────
            if (isRunning && prevPhase !== 'running') {
                prevPhase = 'running';
                el('repr-progress-bar').style.background = 'linear-gradient(90deg,#2563eb,#7c3aed)';
                el('repr-pct').className = 'badge rounded-pill bg-primary';
                el('repr-header-title').textContent = 'Calculando Asistencia...';
                // Log de transición
                const logEl = el('repr-log');
                const sep = document.createElement('div');
                sep.style.cssText = 'color:#64748b;border-top:1px solid #1e293b;margin:4px 0;padding-top:4px;';
                sep.textContent = '✔ BioAlba OK — Iniciando cálculo día a día...';
                logEl.appendChild(sep);
                logEl.scrollTop = logEl.scrollHeight;
            }

            // ── FASE: running (reproceso día a día) ──────────────────
            if (isRunning) {
                _restartPolling(POLL_FAST); // Cálculo es rápido — volver a 1.5s
                el('repr-progress-bar').style.width = `${pct}%`;
                el('repr-pct').textContent = `${pct}%`;
                el('repr-day-label').textContent = `Procesando ${s.current_day || '...'}...`;
                el('repr-counter').textContent = `${syncBioAlba ? 'Fase 2 de 2 — ' : ''}Día ${s.day_index ?? 0} de ${s.total_days ?? '?'}`;

                // Log por cada día nuevo
                if (s.day_index !== prevDayIndex && s.current_day) {
                    prevDayIndex = s.day_index;
                    const logEl = el('repr-log');
                    const line = document.createElement('div');
                    line.style.color = '#94a3b8';
                    line.textContent = `→ [${String(s.day_index).padStart(2, '0')}/${s.total_days}] ${s.current_day}`;
                    logEl.appendChild(line);
                    logEl.scrollTop = logEl.scrollHeight;
                }
                return;
            }

            // ── COMPLETADO ────────────────────────────────────────────
            if (isCompleted || isError) {
                // Si es un batch con múltiples jobs, verificar que TODOS terminaron
                if (_allJobs.length > 1 && isCompleted) {
                    try {
                        const allResponses = await Promise.all(
                            _allJobs.map(jid => fetch(`/api/asistencia/jobs/${jid}/`).then(r => r.json()))
                        );
                        const allDone = allResponses.every(j =>
                            j.status === 'done' || j.status === 'completed' || j.status === 'error'
                        );
                        if (!allDone) {
                            // Actualizar label para mostrar progreso del batch
                            const doneCount = allResponses.filter(j => j.status === 'done' || j.status === 'completed' || j.status === 'error').length;
                            el('repr-day-label').textContent = `⏳ ${doneCount}/${_allJobs.length} empleados completados...`;
                            el('repr-progress-bar').style.width = `${Math.round(50 + 50 * doneCount / _allJobs.length)}%`;
                            return; // Seguir polling hasta que TODOS terminen
                        }
                    } catch (_) { /* error de red, reintentar en siguiente poll */ return; }
                }

                clearInterval(_reprocesoPollingTimer);

                const elapsed = ((s.elapsed_ms || 0) / 1000).toFixed(1);
                const bar = el('repr-progress-bar');
                bar.classList.remove('progress-bar-animated', 'progress-bar-striped');

                if (isError) {
                    bar.style.background = 'linear-gradient(90deg,#dc2626,#ef4444)';
                    el('repr-pct').className = 'badge rounded-pill bg-danger';
                    el('repr-day-label').textContent = '❌ Error en el proceso';
                    el('repr-resumen-texto').textContent = `Error: ${s.error || 'Desconocido'}. Revise la terminal.`;
                    const logEl = el('repr-log');
                    const errLine = document.createElement('div');
                    errLine.style.color = '#fca5a5';
                    errLine.textContent = `❌ ${s.error || 'Error desconocido'}`;
                    logEl.appendChild(errLine);
                } else {
                    bar.style.width = '100%';
                    bar.style.background = 'linear-gradient(90deg,#059669,#10b981)';
                    el('repr-pct').textContent = '100%';
                    el('repr-pct').className = 'badge rounded-pill bg-success';
                    el('repr-header-title').textContent = 'Proceso Completado ✅';
                    el('repr-day-label').textContent = '✅ Todo listo — puede revisar la grilla';
                    const bioAlbaNote = syncBioAlba ? ' (☁️ BioAlba + 🗃️ cálculo)' : '';
                    el('repr-resumen-texto').textContent =
                        `✅ ${s.procesados} días procesados en ${elapsed}s${bioAlbaNote} ⋅ ✕ ${s.errores} errores`;

                    const logEl = el('repr-log');
                    const okLine = document.createElement('div');
                    okLine.style.cssText = 'color:#86efac;font-weight:bold;margin-top:4px;';
                    okLine.textContent = `✔ Completado: ${s.procesados} días (${elapsed}s)`;
                    logEl.appendChild(okLine);
                    logEl.scrollTop = logEl.scrollHeight;

                    // Recargar grilla en background (sin esperar)
                    setTimeout(() => {
                        if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
                    }, 600);

                    // Ejecutar callback onComplete si fue pasado
                    if (_onCompleteCallback) {
                        setTimeout(_onCompleteCallback, 800);
                        _onCompleteCallback = null;
                    }
                }

                el('repr-header-spinner').classList.add('d-none');
                el('repr-header-ok').classList.remove('d-none');
                el('repr-footer-completado').classList.remove('d-none');
            }

        } catch (err) { /* error de red transitorio: ignorar */ }
    }

    // Arrancar polling con intervalo inicial (fast: 1.5s)
    _reprocesoPollingTimer = setInterval(_pollTick, _currentPollInterval);
}



/** Cierra el modal de progreso y detiene el polling. */
window.cerrarModalReproceso = function() {
    if (_reprocesoPollingTimer) {
        clearInterval(_reprocesoPollingTimer);
        _reprocesoPollingTimer = null;
    }
    const modalEl = document.getElementById('modal-reproceso-progreso');
    if (modalEl) bootstrap.Modal.getInstance(modalEl)?.hide();
};


/**
 * Legacy wrapper — usado por confirmarCalibracion (que aún no tiene job_id).
 * Dejamos compatibilidad del nombre original.
 */
function iniciarPollingReproceso(empleadoId, nombre, fechaDesde) {
    // En el flujo de Calibración, el reproceso ya corrió desde saveAsignacionIndividual.
    // Solo mostramos un banner informativo liviano sin polling.
    showToast(`🔄 Reprocesando asistencia de ${nombre} desde ${fechaDesde}. La grilla se actualizará al finalizar.`, 'info');
}




/**
 * Busca los periodos configurados en el modulo de configuracion,
 * muestra el que esta abierto (y los demas si aplica) para que el usuario
 * pueda filtrar la grilla antes de evaluar y cerrar.
 */
async function mostrarSelectorPeriodosParaCierre() {
    let periodos = [];
    try {
        const resp = await fetch('/api/configuracion/periodos/', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (resp.ok) {
            periodos = await resp.json();
        }
    } catch (e) {
        console.error("Error al obtener periodos:", e);
        return showToast("Error al obtener la lista de períodos", "error");
    }

    // Filtrar los que están abiertos
    const periodosAbiertos = periodos.filter(p => p.estado === 'abierto');

    if (periodosAbiertos.length === 0) {
        return Swal.fire({
            title: 'No hay períodos abiertos',
            text: 'Todos los períodos configurados ya se encuentran cerrados en el sistema.',
            icon: 'info',
            confirmButtonText: 'Entendido'
        });
    }

    // Obtener las áreas accesibles desde el select principal de la grilla
    const areaSelectDOM = document.getElementById('marcacion-area');
    let areas = [];
    if (areaSelectDOM) {
        areas = Array.from(areaSelectDOM.options)
            .map(opt => opt.value)
            .filter(val => val !== "" && val !== "Todas");
    }

    // Valor pre-seleccionado actual de la grilla
    const areaActual = stateMarcacionesApp.area || "";

    // Construir las opciones del selector de áreas
    const areaOptionsHtml = areas.map(a => {
        const isSelected = a === areaActual ? 'selected' : '';
        return `<option value="${a}" ${isSelected}>${a}</option>`;
    }).join('');

    // Renderizar una lista de los períodos abiertos
    const listHtml = periodosAbiertos.map(p => {
        const activeBadge = p.activo ? '<span class="badge bg-primary ms-2">Vigente</span>' : '';
        const fIniFormateada = p.fecha_inicio.split('-').reverse().join('-');
        const fFinFormateada = p.fecha_fin.split('-').reverse().join('-');
        return `
            <div class="d-flex justify-content-between align-items-center p-3 mb-2 border rounded bg-white shadow-sm">
                <div>
                    <h6 class="fw-bold mb-1 text-dark">${p.mes_cierre}${activeBadge}</h6>
                    <small class="text-muted"><i class="bi bi-calendar-range"></i> Rango: <strong>${fIniFormateada} al ${fFinFormateada}</strong></small>
                </div>
                <button class="btn btn-sm btn-warning fw-bold px-3 shadow-sm btn-cierre-action" 
                        onclick="cierreFiltrarGrillaYIniciarCierre('${p.fecha_inicio}', '${p.fecha_fin}')"
                        ${!areaActual ? 'disabled' : ''}
                        title="${!areaActual ? 'Debe seleccionar un área primero' : 'Filtrar y Cerrar'}">
                    <i class="bi bi-funnel-fill"></i> Filtrar y Cerrar
                </button>
            </div>
        `;
    }).join('');

    const html = `
        <div class="modal fade" id="modal-seleccionar-periodo-cierre" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content border-0 shadow-lg" style="border-radius:12px;">
                    <div class="modal-header bg-dark text-white border-0" style="border-radius: 12px 12px 0 0;">
                        <h5 class="modal-title fw-bold"><i class="bi bi-calendar-event text-warning me-2"></i> Seleccionar Período y Área</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body bg-light p-4">
                        <!-- Selector de Área -->
                        <div class="card border-0 shadow-sm p-3 mb-4 bg-white">
                            <label for="cierre-area-select" class="form-label small fw-bold text-muted mb-2">
                                <i class="bi bi-geo-alt-fill text-danger me-1"></i> Área para el Cierre:
                            </label>
                            <select class="form-select form-select-sm border-primary-subtle" id="cierre-area-select" onchange="cierreActualizarSeleccionDeArea(this.value)">
                                <option value="">-- Seleccione una Área Específica --</option>
                                ${areaOptionsHtml}
                            </select>
                            <div class="form-text text-muted small mt-2">
                                El cierre se calcula y sella por área. Selecciona el área a cerrar para habilitar el proceso.
                            </div>
                        </div>

                        <p class="text-muted small mb-3">
                            Selecciona el período configurado que deseas cerrar. 
                            <strong>La grilla se filtrará automáticamente</strong> con el área y fechas seleccionadas.
                        </p>
                        <div>
                            ${listHtml}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    const old = document.getElementById('modal-seleccionar-periodo-cierre');
    if (old) old.remove();

    document.body.insertAdjacentHTML('beforeend', html);
    const modal = new bootstrap.Modal(document.getElementById('modal-seleccionar-periodo-cierre'));
    modal.show();
}

window.cierreFiltrarGrillaYIniciarCierre = async function(fIni, fFin) {
    const areaVal = document.getElementById('cierre-area-select')?.value;
    if (!areaVal) {
        return showToast("Debe seleccionar un área específica.", "error");
    }

    // 1. Cerrar modal selector
    const modalEl = document.getElementById('modal-seleccionar-periodo-cierre');
    if (modalEl) {
        bootstrap.Modal.getInstance(modalEl)?.hide();
    }

    // 2. Actualizar fechas y área del estado y DOM
    stateMarcacionesApp.fechaInicioRRHH = fIni;
    stateMarcacionesApp.fechaFinRRHH = fFin;
    stateMarcacionesApp.area = areaVal;
    
    const inputIni = document.getElementById('rrhh-fecha-inicio');
    const inputFin = document.getElementById('rrhh-fecha-fin');
    if (inputIni) inputIni.value = fIni;
    if (inputFin) inputFin.value = fFin;
    
    const selectArea = document.getElementById('marcacion-area');
    if (selectArea) selectArea.value = areaVal;

    // 3. Forzar el recargado de la grilla de asistencia
    showToast(`🔄 Filtrando grilla para área '${areaVal}' y período seleccionado...`, "info");
    await loadMarcacionesData();

    // 4. Lanzar asistente de cierre tras cargar la grilla
    setTimeout(() => {
        openCierrePeriodoModal();
    }, 600);
};

window.cierreActualizarSeleccionDeArea = function(areaVal) {
    // Actualizar state principal
    stateMarcacionesApp.area = areaVal;
    
    // Sincronizar select de la barra de herramientas principal
    const mainAreaSelect = document.getElementById('marcacion-area');
    if (mainAreaSelect) mainAreaSelect.value = areaVal;
    
    // Habilitar/Deshabilitar botones de cierre
    const buttons = document.querySelectorAll('.btn-cierre-action');
    buttons.forEach(btn => {
        if (areaVal) {
            btn.disabled = false;
            btn.title = "Filtrar y Cerrar";
        } else {
            btn.disabled = true;
            btn.title = "Debe seleccionar un área primero";
        }
    });
};

/**
 * [NUEVO] Abre el Asistente Zero-Trust de Cierre de Periodo RRHH.
 */
/**
 * [NUEVO] Abre el Asistente Zero-Trust de Cierre de Periodo RRHH.
 */
async function openCierrePeriodoModal() {
    // Obtener la lista de periodos oficiales configurados para cruzar
    let periodos = [];
    try {
        const resp = await fetch('/api/configuracion/periodos/', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (resp.ok) {
            periodos = await resp.json();
        }
    } catch (e) {
        console.error("Error al obtener periodos:", e);
    }

    // Obtener las áreas desde el select principal
    const areaSelectDOM = document.getElementById('marcacion-area');
    let areas = [];
    if (areaSelectDOM) {
        areas = Array.from(areaSelectDOM.options)
            .map(opt => opt.value)
            .filter(val => val !== "" && val !== "Todas");
    }

    // Priorizar el período correspondiente a las fechas filtradas en la grilla principal
    const periodFromGrid = periodos.find(p => p.fecha_inicio === stateMarcacionesApp.fechaInicioRRHH && p.fecha_fin === stateMarcacionesApp.fechaFinRRHH);
    const vigentePeriodo = periodFromGrid || periodos.find(p => p.estado === 'abierto' && (p.activo === 1 || p.activo === true));
    
    const fIni = stateMarcacionesApp.fechaInicioRRHH || (vigentePeriodo ? vigentePeriodo.fecha_inicio : "");
    const fFin = stateMarcacionesApp.fechaFinRRHH || (vigentePeriodo ? vigentePeriodo.fecha_fin : "");
    const area = (stateMarcacionesApp.area === 'Todas' || !stateMarcacionesApp.area) ? "" : stateMarcacionesApp.area;

    const html = `
        <div class="modal fade" id="modal-cierre-wizard" tabindex="-1" data-bs-backdrop="static">
            <div class="modal-dialog modal-xl">
                <div class="modal-content border-0 shadow-lg">
                    <div class="modal-header bg-dark text-white border-0">
                        <h5 class="modal-title fw-bold"><i class="bi bi-shield-lock-fill text-warning me-2"></i> Asistente de Cierre de Periodo (Zero-Trust)</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body bg-light p-4">
                        <div class="row">
                            <div class="col-md-3">
                                <div class="list-group list-group-flush mb-4 rounded shadow-sm">
                                    <button class="list-group-item list-group-item-action fw-bold" id="wiz-tab-0" disabled><i class="bi bi-gear-fill text-secondary me-2"></i> Parámetros</button>
                                    <button class="list-group-item list-group-item-action fw-bold" id="wiz-tab-1" disabled><i class="bi bi-exclamation-triangle-fill text-danger me-2"></i> 1. Anomalías</button>
                                    <button class="list-group-item list-group-item-action fw-bold" id="wiz-tab-2" disabled><i class="bi bi-clock-fill text-warning me-2"></i> 2. En Curso</button>
                                    <button class="list-group-item list-group-item-action fw-bold" id="wiz-tab-3" disabled><i class="bi bi-calendar-plus text-primary me-2"></i> 3. Horas Extras</button>
                                    <button class="list-group-item list-group-item-action fw-bold" id="wiz-tab-4" disabled><i class="bi bi-person-dash text-info me-2"></i> 4. Inasistencias</button>
                                    <button class="list-group-item list-group-item-action fw-bold" id="wiz-tab-5" disabled><i class="bi bi-file-earmark-pdf text-success me-2"></i> 5. Reporte Final</button>
                                </div>
                                <div class="card border-0 bg-white shadow-sm p-3 mb-3">
                                    <h6 class="fw-bold mb-2 small" style="color: #475569"><i class="bi bi-calendar-check text-primary me-1"></i> Período a Cerrar</h6>
                                    
                                    <div id="cierre-periodo-badge-container" class="mb-2"></div>
                                    
                                    <div class="small text-muted mb-0">
                                        Rango: <strong id="cierre-rango-text">${fIni && fFin ? `${fIni} al ${fFin}` : 'No definido'}</strong><br>
                                        Área: <strong id="cierre-area-sidebar">${area || 'No seleccionada'}</strong>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-9 bg-white border rounded shadow-sm p-4 position-relative" id="wizard-content" style="min-height: 400px;">
                                <!-- Contenido dinámico del paso -->
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer bg-white border-top">
                        <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cerrar</button>
                        <button type="button" class="btn btn-dark fw-bold px-4" id="btn-cierre-wizard-next" style="display:none;" onclick="nextWizardStep()">
                            Siguiente Paso <i class="bi bi-arrow-right"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    const old = document.getElementById('modal-cierre-wizard');
    if (old) old.remove();

    document.body.insertAdjacentHTML('beforeend', html);
    const modal = new bootstrap.Modal(document.getElementById('modal-cierre-wizard'));
    modal.show();

    window.cierreWizardState = { 
        currentStep: 0, 
        evaluacion: null, 
        fIni, 
        fFin, 
        area, 
        aceptarInasistencias: false,
        periodos: periodos,
        areas: areas
    };

    // Actualizar badge e info del periodo en el sidebar
    actualizarInfoPeriodoEnWizard();

    // Renderizar Paso 0
    renderWizardStep(0);
}

/**
 * Actualiza el badge visual del período en el panel lateral del wizard
 */
window.actualizarInfoPeriodoEnWizard = function() {
    const s = window.cierreWizardState;
    const fIni = s.fIni || "";
    const fFin = s.fFin || "";
    const area = s.area || "";
    
    const badgeContainer = document.getElementById('cierre-periodo-badge-container');
    const rangoText = document.getElementById('cierre-rango-text');
    const areaSidebar = document.getElementById('cierre-area-sidebar');
    
    if (rangoText) rangoText.innerHTML = fIni && fFin ? `${fIni} al ${fFin}` : '<i>No definido</i>';
    if (areaSidebar) areaSidebar.textContent = area || 'No seleccionada';
    
    if (!fIni || !fFin) {
        if (badgeContainer) badgeContainer.innerHTML = '';
        return;
    }

    let matchedPeriod = s.periodos.find(p => p.fecha_inicio === fIni && p.fecha_fin === fFin);
    
    if (matchedPeriod) {
        if (badgeContainer) {
            const estadoBadge = matchedPeriod.estado === 'cerrado' 
                ? '<span class="badge bg-danger"><i class="bi bi-lock-fill"></i> Cerrado</span>' 
                : '<span class="badge bg-success"><i class="bi bi-unlock-fill"></i> Abierto</span>';
            badgeContainer.innerHTML = `
                <div class="fw-bold text-success mb-1" style="font-size:0.95rem;">
                    <i class="bi bi-calendar-check-fill"></i> ${matchedPeriod.mes_cierre}
                </div>
                ${estadoBadge} ${matchedPeriod.activo ? '<span class="badge bg-primary">Vigente</span>' : ''}
            `;
        }
    } else {
        if (badgeContainer) {
            badgeContainer.innerHTML = `
                <div class="alert alert-warning py-1 px-2 mb-1 small border-warning">
                    <i class="bi bi-exclamation-triangle-fill"></i> Rango Personalizado
                </div>
                <span class="text-muted small" style="font-size:0.75rem;">No coincide con períodos RRHH configurados.</span>
            `;
        }
    }
}

function updateWizardTabs(step) {
    const tab0 = document.getElementById('wiz-tab-0');
    if (tab0) {
        if (step === 0) {
            tab0.classList.add('active');
            tab0.classList.remove('bg-light', 'text-muted');
        } else {
            tab0.classList.remove('active');
            tab0.classList.add('bg-light', 'text-muted');
        }
    }

    for (let i = 1; i <= 5; i++) {
        const tab = document.getElementById(`wiz-tab-${i}`);
        if (tab) {
            if (i === step) {
                tab.classList.add('active');
                tab.classList.remove('bg-light', 'text-muted');
            } else if (i < step) {
                tab.classList.remove('active');
                tab.classList.add('bg-light', 'text-muted');
            } else {
                tab.classList.remove('active', 'bg-light', 'text-muted');
            }
        }
    }
}

window.cierreWizardCambiarArea = async function(val) {
    window.cierreWizardState.area = val;
    
    if (val) {
        try {
            const resp = await fetch(`/api/configuracion/periodos/activo/${encodeURIComponent(val)}/`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });
            if (resp.ok) {
                const activePeriod = await resp.json();
                if (activePeriod && activePeriod.fecha_inicio && activePeriod.fecha_fin) {
                    window.cierreWizardState.fIni = activePeriod.fecha_inicio;
                    window.cierreWizardState.fFin = activePeriod.fecha_fin;
                }
            }
        } catch (e) {
            console.error("Error al obtener periodo activo para el área en el wizard:", e);
        }
    }
    
    if (typeof renderWizardStep === 'function') {
        renderWizardStep(0);
    }
    actualizarInfoPeriodoEnWizard();
};

window.cierreWizardSeleccionarPeriodo = function(val) {
    if (val === 'custom') {
        const inputIni = document.getElementById('cierre-wizard-fini');
        const inputFin = document.getElementById('cierre-wizard-ffin');
        if (inputIni) inputIni.removeAttribute('readonly');
        if (inputFin) inputFin.removeAttribute('readonly');
    } else {
        const [fIni, fFin] = val.split('|');
        window.cierreWizardState.fIni = fIni;
        window.cierreWizardState.fFin = fFin;
        
        const inputIni = document.getElementById('cierre-wizard-fini');
        const inputFin = document.getElementById('cierre-wizard-ffin');
        if (inputIni) {
            inputIni.value = fIni;
            inputIni.setAttribute('readonly', 'true');
        }
        if (inputFin) {
            inputFin.value = fFin;
            inputFin.setAttribute('readonly', 'true');
        }
        
        if (typeof renderWizardStep === 'function') {
            renderWizardStep(0);
        }
        actualizarInfoPeriodoEnWizard();
    }
};

window.cierreWizardCambiarFechasManual = function() {
    window.cierreWizardState.fIni = document.getElementById('cierre-wizard-fini')?.value || "";
    window.cierreWizardState.fFin = document.getElementById('cierre-wizard-ffin')?.value || "";
    
    const btnIniciar = document.getElementById('btn-cierre-wizard-iniciar');
    if (btnIniciar) {
        btnIniciar.disabled = (!window.cierreWizardState.fIni || !window.cierreWizardState.fFin);
    }
    
    actualizarInfoPeriodoEnWizard();
};

window.cierreWizardConfirmarParametros = async function() {
    const s = window.cierreWizardState;
    const area = s.area;
    const fIni = s.fIni;
    const fFin = s.fFin;

    if (!area) {
        return showToast("Debe seleccionar un área específica.", "warning");
    }
    if (!fIni || !fFin) {
        return showToast("Debe ingresar las fechas de inicio y fin.", "warning");
    }

    if (fIni > fFin) {
        return showToast("La fecha de inicio no puede ser posterior a la fecha de fin.", "warning");
    }

    // Validar bloqueo hoy
    const today = new Date().toISOString().split('T')[0];
    if (today >= fIni && today <= fFin) {
        return showToast("Bloqueo de Seguridad: No se pueden cerrar periodos que incluyan el día de hoy.", "error");
    }

    // Validar límite de 35 días
    const dIni = new Date(fIni);
    const dFin = new Date(fFin);
    const diffTime = Math.abs(dFin - dIni);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1;
    if (diffDays > 35) {
        return showToast(`Límite Estricto: El rango seleccionado (${diffDays} días) supera el máximo permitido (35 días).`, "error");
    }

    // 1. Sincronizar el estado global de la aplicación
    stateMarcacionesApp.area = area;
    stateMarcacionesApp.fechaInicioRRHH = fIni;
    stateMarcacionesApp.fechaFinRRHH = fFin;

    // 2. Sincronizar los filtros en el DOM de la grilla principal
    const mainAreaSelect = document.getElementById('marcacion-area');
    if (mainAreaSelect) mainAreaSelect.value = area;

    const mainFIni = document.getElementById('rrhh-fecha-inicio');
    if (mainFIni) mainFIni.value = fIni;

    const mainFFin = document.getElementById('rrhh-fecha-fin');
    if (mainFFin) mainFFin.value = fFin;

    // 3. Forzar el recargado de la grilla de asistencia en segundo plano
    showToast(`🔄 Filtrando grilla para área '${area}' y rango seleccionado...`, "info");
    if (typeof loadMarcacionesData === 'function') {
        loadMarcacionesData(); // se ejecuta en background
    }

    // 4. Mostrar spinner y proceder con la pre-evaluación
    const content = document.getElementById('wizard-content');
    content.innerHTML = `
        <div class="text-center py-5">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="mt-3 text-muted fw-bold">Pre-evaluando integridad de datos para el área: ${area}...</p>
        </div>
    `;

    try {
        const url = `/api/cierre/pre-evaluacion?fecha_inicio=${fIni}&fecha_fin=${fFin}&area=${encodeURIComponent(area)}`;
        const resp = await fetch(url, { headers: { 'Authorization': `Bearer ${AuthService.getToken()}` } });
        const data = await resp.json();
        
        if (!resp.ok) throw new Error(data.detail || "Fallo en pre-evaluación");
        
        window.cierreWizardState.evaluacion = data;
        renderWizardStep(1);
    } catch (e) {
        content.innerHTML = `
            <div class="alert alert-danger py-4">
                <h5><i class="bi bi-x-circle-fill text-danger me-2"></i> Error de Validación</h5>
                <p class="mb-3">${e.message}</p>
                <div class="d-flex gap-2">
                    <button class="btn btn-sm btn-outline-danger" onclick="cierreWizardConfirmarParametros()">
                        <i class="bi bi-arrow-clockwise"></i> Reintentar
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="renderWizardStep(0)">
                        <i class="bi bi-chevron-left"></i> Volver a Parámetros
                    </button>
                </div>
            </div>
        `;
    }
};

function cierreGetHEContextBadges(a) {
    let tags = [];
    
    // 1. Trabajo en Colación (Tomó menos colación de la permitida)
    if (a.minutos_colacion !== undefined && a.minutos_colacion_auto !== undefined && a.minutos_colacion !== null && a.minutos_colacion_auto !== null) {
        if (a.minutos_colacion_real > 0 && a.minutos_colacion_auto > (a.minutos_colacion || 0)) {
            let extraMin = a.minutos_colacion_auto - (a.minutos_colacion || 0);
            tags.push(`<span class="badge bg-info-subtle text-info-emphasis border border-info-subtle ms-2" title="Colación tomada: ${a.minutos_colacion_real}m de ${a.minutos_colacion_auto}m"><i class="bi bi-cup-hot"></i> +${extraMin}m (Colación reducida)</span>`);
        }
    }
    
    // 2. Llegada Temprana Efectiva (Fuera del margen de anclaje)
    if (a.hora_entrada_teorica && a.hora_entrada_real) {
        let entTeo = new Date(`1970-01-01T${a.hora_entrada_teorica}`);
        let entReal = new Date(`1970-01-01T${a.hora_entrada_real}`);
        if (entReal > entTeo && (entReal - entTeo) > 12 * 3600000) entReal.setDate(entReal.getDate() - 1);
        
        let diffEntradaMin = Math.round((entTeo - entReal) / 60000); 
        let obsLlegada = (a.observaciones || '').toLowerCase();
        if (diffEntradaMin > 0 && obsLlegada.includes('llegada anticipada') && obsLlegada.includes('fuera del anclaje')) {
            tags.push(`<span class="badge bg-primary-subtle text-primary-emphasis border border-primary-subtle ms-2"><i class="bi bi-box-arrow-in-right"></i> +${diffEntradaMin}m (Ingreso Anticipado)</span>`);
        }
    }
    
    // 3. Salida Tardía Efectiva
    if (a.hora_salida_teorica && a.hora_salida_real) {
        let salTeo = new Date(`1970-01-01T${a.hora_salida_teorica}`);
        let salReal = new Date(`1970-01-01T${a.hora_salida_real}`);
        if (salReal < salTeo && (salTeo - salReal) > 12 * 3600000) salReal.setDate(salReal.getDate() + 1);
        
        let diffSalidaMin = Math.round((salReal - salTeo) / 60000);
        let obsSalida = (a.observaciones || '').toLowerCase();
        if (diffSalidaMin > 0 && !obsSalida.includes('salida dentro del anclaje')) {
            tags.push(`<span class="badge bg-primary-subtle text-primary-emphasis border border-primary-subtle ms-2"><i class="bi bi-box-arrow-right"></i> +${diffSalidaMin}m (Salida Tardía)</span>`);
        }
    }
    
    // Fallback si no identificó nada específico pero hay horas extras
    if (tags.length === 0) {
        tags.push(`<span class="badge bg-light text-secondary border border-secondary-subtle ms-2 text-uppercase" style="font-size: 0.65rem;"><i class="bi bi-tag-fill me-1"></i>Exceso Jornada</span>`);
    }
    
    return tags.join('');
}

function renderWizardStep(step) {
    window.cierreWizardState.currentStep = step;
    updateWizardTabs(step);
    const content = document.getElementById('wizard-content');
    const btnNext = document.getElementById('btn-cierre-wizard-next');
    const s = window.cierreWizardState;

    if (step === 0) {
        btnNext.style.display = 'none';

        // Buscar el periodo que corresponde a las fechas configuradas en el wizard (s.fIni / s.fFin)
        let vigente = s.periodos.find(p => p.fecha_inicio === s.fIni && p.fecha_fin === s.fFin);
        
        // Fallback al periodo vigente activo de la DB si no coincide con ninguno
        if (!vigente && (!s.fIni || !s.fFin)) {
            vigente = s.periodos.find(p => p.estado === 'abierto' && (p.activo === 1 || p.activo === true));
            if (vigente) {
                s.fIni = vigente.fecha_inicio;
                s.fFin = vigente.fecha_fin;
            }
        }

        // Opciones de área
        const areasOptions = s.areas.map(a => {
            const isSelected = a === s.area ? 'selected' : '';
            return `<option value="${a}" ${isSelected}>${a}</option>`;
        }).join('');

        // Opciones de período
        const periodosOptions = s.periodos.map(p => {
            const isSelected = (p.fecha_inicio === s.fIni && p.fecha_fin === s.fFin) ? 'selected' : '';
            let label = `${p.mes_cierre}`;
            if (p.estado === 'cerrado') label += ' (Cerrado)';
            else if (p.activo === 1 || p.activo === true) label += ' (Vigente)';
            return `<option value="${p.fecha_inicio}|${p.fecha_fin}" ${isSelected}>${label}</option>`;
        }).join('');
        
        const isCustom = !s.periodos.some(p => p.fecha_inicio === s.fIni && p.fecha_fin === s.fFin);

        let periodInfoHtml = '';
        if (vigente) {
            const fIniFormateada = vigente.fecha_inicio.split('-').reverse().join('-');
            const fFinFormateada = vigente.fecha_fin.split('-').reverse().join('-');
            
            periodInfoHtml = `
                <div class="card border-0 shadow-sm p-3 h-100 bg-white border border-success-subtle" style="border-left: 4px solid #10b981 !important;">
                    <label class="form-label fw-bold text-success small mb-2">
                        <i class="bi bi-calendar-check-fill me-1"></i> Período a Cerrar:
                    </label>
                    <div class="fw-bold text-dark fs-5 mb-1">${vigente.mes_cierre}</div>
                    <div class="small text-muted mb-2">
                        <i class="bi bi-calendar-range me-1"></i> Rango: <strong>${fIniFormateada} al ${fFinFormateada}</strong>
                    </div>
                    ${vigente.estado === 'cerrado' 
                        ? '<span class="badge bg-danger-subtle text-danger border border-danger-subtle align-self-start"><i class="bi bi-lock-fill me-1"></i> Período Cerrado</span>'
                        : '<span class="badge bg-success-subtle text-success border border-success-subtle align-self-start"><i class="bi bi-unlock-fill me-1"></i> Período Abierto & Vigente</span>'
                    }
                </div>
            `;
        } else if (s.fIni && s.fFin) {
            const fIniFormateada = s.fIni.split('-').reverse().join('-');
            const fFinFormateada = s.fFin.split('-').reverse().join('-');
            periodInfoHtml = `
                <div class="card border-0 shadow-sm p-3 h-100 bg-white border border-warning-subtle" style="border-left: 4px solid #f59e0b !important;">
                    <label class="form-label fw-bold text-warning small mb-2">
                        <i class="bi bi-exclamation-triangle-fill me-1"></i> Rango Personalizado:
                    </label>
                    <div class="fw-bold text-dark fs-6 mb-1">Rango Fuera de Calendario</div>
                    <div class="small text-muted mb-2">
                        <i class="bi bi-calendar-range me-1"></i> Rango: <strong>${fIniFormateada} al ${fFinFormateada}</strong>
                    </div>
                    <span class="badge bg-warning-subtle text-warning border border-warning-subtle align-self-start">
                        No oficial
                    </span>
                </div>
            `;
        } else {
            periodInfoHtml = `
                <div class="card border-0 shadow-sm p-3 h-100 bg-white border border-danger-subtle" style="border-left: 4px solid #ef4444 !important;">
                    <label class="form-label fw-bold text-danger small mb-2">
                        <i class="bi bi-exclamation-triangle-fill me-1"></i> Período a Cerrar:
                    </label>
                    <div class="text-danger fw-bold mb-2">Período No Definido</div>
                    <p class="small text-muted mb-0">
                        Seleccione un período oficial o ingrese un rango de fechas válido.
                    </p>
                </div>
            `;
        }

        content.innerHTML = `
            <div class="py-2">
                <h4 class="fw-bold text-dark mb-3"><i class="bi bi-gear-fill text-secondary me-2"></i> Configuración de Cierre de Período</h4>
                <p class="text-muted small">
                    Seleccione el área y el período o rango de fechas que desea evaluar para el cierre. Al continuar, se pre-evaluarán las anomalías y el estado del período.
                </p>
                
                <div class="row g-3 mt-2">
                    <!-- Selección de Área y Período -->
                    <div class="col-md-6">
                        <div class="card border-0 shadow-sm p-3 bg-light mb-3">
                            <label for="cierre-wizard-area-select" class="form-label fw-bold text-secondary small mb-2">
                                <i class="bi bi-geo-alt-fill text-danger me-1"></i> 1. Área a Cerrar:
                            </label>
                            <select class="form-select border-primary-subtle" id="cierre-wizard-area-select" onchange="cierreWizardCambiarArea(this.value)">
                                <option value="">-- Seleccione un Área --</option>
                                ${areasOptions}
                            </select>
                        </div>

                        <div class="card border-0 shadow-sm p-3 bg-light">
                            <label for="cierre-wizard-periodo-select" class="form-label fw-bold text-secondary small mb-2">
                                <i class="bi bi-calendar-check text-primary me-1"></i> 2. Seleccionar Período:
                            </label>
                            <select class="form-select border-primary-subtle mb-3" id="cierre-wizard-periodo-select" onchange="cierreWizardSeleccionarPeriodo(this.value)">
                                ${periodosOptions}
                                <option value="custom" ${isCustom ? 'selected' : ''}>-- Rango Personalizado --</option>
                            </select>

                            <div class="row g-2">
                                <div class="col-6">
                                    <label class="form-label small fw-semibold text-muted mb-1">Fecha Inicio</label>
                                    <input type="date" class="form-control form-control-sm" id="cierre-wizard-fini" value="${s.fIni || ''}" ${!isCustom ? 'readonly' : ''} onchange="cierreWizardCambiarFechasManual()">
                                </div>
                                <div class="col-6">
                                    <label class="form-label small fw-semibold text-muted mb-1">Fecha Fin</label>
                                    <input type="date" class="form-control form-control-sm" id="cierre-wizard-ffin" value="${s.fFin || ''}" ${!isCustom ? 'readonly' : ''} onchange="cierreWizardCambiarFechasManual()">
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Resumen del Período -->
                    <div class="col-md-6">
                        ${periodInfoHtml}
                    </div>
                </div>

                <!-- Botón de Envío -->
                <div class="mt-4 text-end">
                    <button class="btn btn-warning fw-bold px-4 py-2 shadow-sm" 
                            id="btn-cierre-wizard-iniciar" 
                            ${(!s.fIni || !s.fFin) ? 'disabled' : ''} 
                            onclick="cierreWizardConfirmarParametros()">
                        <i class="bi bi-funnel-fill me-1"></i> Filtrar e Iniciar Pre-evaluación
                    </button>
                </div>
            </div>
        `;
        return;
    }

    const ev = s.evaluacion;

    if (step === 1) { // Anomalías
        if (ev.anomalias > 0) {
            const list = ev.detalle_anomalias.map(a => {
                const nameEscaped = (a.nombre_completo || '').replace(/'/g, "\\'");
                return `
                    <li class="d-flex justify-content-between align-items-center py-2 px-3 border-bottom hover-bg-light">
                        <div class="d-flex align-items-center">
                            <i class="bi bi-exclamation-triangle-fill text-danger me-2"></i>
                            <div>
                                <span class="fw-bold text-dark small">${window.formatFechaDDMMYYYY(a.fecha)}</span>
                                <span class="mx-2 text-muted">|</span>
                                <span class="text-secondary small">${a.nombre_completo}</span>
                                ${a.hora_entrada_real || a.hora_salida_real ? `
                                    <span class="badge bg-warning-subtle text-warning-emphasis ms-2" style="font-size: 0.7rem;">
                                        <i class="bi bi-clock-fill me-1"></i>${a.hora_entrada_real || '--:--'} / ${a.hora_salida_real || '--:--'}
                                    </span>
                                ` : ''}
                            </div>
                        </div>
                        <button class="btn btn-sm btn-outline-primary fw-bold py-1 px-3 shadow-sm" 
                                onclick="window.cierreCorregirAnomalia(${a.empleado_id}, '${a.fecha}', '${nameEscaped}', '${a.hora_entrada_real || ''}', '${a.hora_salida_real || ''}')">
                            <i class="bi bi-pencil-square me-1"></i> Corregir
                        </button>
                    </li>
                `;
            }).join('');
            content.innerHTML = `
                <h4 class="text-danger fw-bold"><i class="bi bi-shield-x"></i> HARD STOP: Anomalías Detectadas</h4>
                <p>Se encontraron <strong>${ev.anomalias} anomalías</strong> que bloquean el cierre. Debes solucionarlas antes de continuar.</p>
                <div class="border rounded-3 shadow-sm bg-white" style="max-height:250px; overflow-y:auto;">
                    <ul class="list-unstyled mb-0">${list}</ul>
                </div>
            `;
            btnNext.style.display = 'none';
        } else {
            content.innerHTML = `
                <div class="text-center py-5">
                    <i class="bi bi-check-circle-fill text-success" style="font-size: 4rem;"></i>
                    <h4 class="mt-3">Sin Anomalías</h4>
                    <p class="text-muted">Las marcaciones están íntegras. Puede continuar al siguiente paso.</p>
                </div>
            `;
            btnNext.style.display = 'inline-block';
            btnNext.innerHTML = 'Siguiente Paso <i class="bi bi-arrow-right"></i>';
            btnNext.className = 'btn btn-dark fw-bold px-4';
            btnNext.onclick = () => renderWizardStep(2);
        }
    } else if (step === 2) { // En Curso
        if (ev.en_curso > 0) {
            const list = ev.detalle_en_curso.map(a => `<li>${a.fecha} - ${a.nombre_completo} (Salida teórica: ${a.hora_salida_teorica || 'N/A'})</li>`).join('');
            content.innerHTML = `
                <h4 class="text-warning fw-bold"><i class="bi bi-clock-history"></i> HARD STOP: Turnos en Curso</h4>
                <p>Hay <strong>${ev.en_curso} empleados</strong> con turno activo. No puedes cerrar hasta que terminen su jornada.</p>
                <div class="border rounded p-3 bg-light" style="max-height:200px; overflow-y:auto;"><ul>${list}</ul></div>
            `;
            btnNext.style.display = 'none';
        } else {
            content.innerHTML = `
                <div class="text-center py-5">
                    <i class="bi bi-check-circle-fill text-success" style="font-size: 4rem;"></i>
                    <h4 class="mt-3">Sin Turnos en Curso</h4>
                    <p class="text-muted">Todos los turnos del periodo han finalizado.</p>
                </div>
            `;
            btnNext.style.display = 'inline-block';
            btnNext.onclick = () => renderWizardStep(3);
        }
    } else if (step === 3) { // HE Pendientes
        if (ev.he_pendientes > 0) {
            const canApproveHE = typeof AuthService !== 'undefined' && AuthService.hasPermission("marcaciones.horas_extras");
            const list = ev.detalle_he.map(a => `
                <li class="d-flex justify-content-between align-items-center py-2 px-3 border-bottom hover-bg-light">
                    <div class="d-flex align-items-center">
                        <i class="bi bi-clock-fill text-primary me-2"></i>
                        <div>
                            <span class="fw-bold text-dark small">${a.fecha}</span>
                            <span class="mx-2 text-muted">|</span>
                            <span class="text-secondary small">${a.nombre_completo}</span>
                            <span class="badge bg-light text-primary border border-primary-subtle ms-2">${formatExactMinutesToTime(a.minutos_bruto)}</span>
                            ${cierreGetHEContextBadges(a)}
                        </div>
                    </div>
                    ${canApproveHE ? `
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-sm btn-outline-success fw-bold py-0 px-2" onclick="cierreResolverHE(${a.empleado_id}, '${a.fecha}', ${a.minutos_bruto}, 'APROBADO')" title="Aprobar esta Hora Extra">
                            <i class="bi bi-check-lg"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger fw-bold py-0 px-2" onclick="cierreResolverHE(${a.empleado_id}, '${a.fecha}', ${a.minutos_bruto}, 'RECHAZADO')" title="Rechazar esta Hora Extra">
                            <i class="bi bi-x-lg"></i>
                        </button>
                    </div>
                    ` : ''}
                </li>
            `).join('');

            content.innerHTML = `
                <h4 class="text-primary fw-bold mb-3"><i class="bi bi-exclamation-circle-fill"></i> HARD STOP: Horas Extras Pendientes</h4>
                <div class="d-flex justify-content-between align-items-center mb-3 p-3 bg-primary bg-opacity-10 border border-primary-subtle rounded-3">
                    <div class="small text-primary-emphasis fw-semibold">
                        <i class="bi bi-info-circle-fill me-1"></i> Existen <strong>${ev.he_pendientes} registros</strong> pendientes en el periodo seleccionado.
                    </div>
                    ${canApproveHE ? `
                    <button class="btn btn-sm btn-primary fw-bold px-3 shadow-sm" onclick="cierreResolverTodasHE()">
                        <i class="bi bi-check-all me-1"></i> Aprobar Todas
                    </button>
                    ` : ''}
                </div>
                <div class="border rounded-3 shadow-sm" style="max-height:230px; overflow-y:auto; background:#ffffff;">
                    <ul class="list-unstyled mb-0">${list}</ul>
                </div>
            `;
            btnNext.style.display = 'none';
        } else {
            content.innerHTML = `
                <div class="text-center py-5">
                    <i class="bi bi-check-circle-fill text-success" style="font-size: 4rem;"></i>
                    <h4 class="mt-3">Sin HE Pendientes</h4>
                    <p class="text-muted">Todas las Horas Extras han sido resueltas.</p>
                </div>
            `;
            btnNext.style.display = 'inline-block';
            btnNext.onclick = () => renderWizardStep(4);
        }
    } else if (step === 4) { // Inasistencias (Soft Stop)
        if (ev.inasistencias_injustificadas > 0) {
            const list = ev.detalle_ina.map(a => {
                const nameEscaped = (a.nombre_completo || '').replace(/'/g, "\\'");
                return `
                    <li class="d-flex justify-content-between align-items-center py-2 px-3 border-bottom hover-bg-light">
                        <div class="d-flex align-items-center">
                            <i class="bi bi-calendar-x text-info me-2"></i>
                            <div>
                                <span class="fw-bold text-dark small">${a.fecha}</span>
                                <span class="mx-2 text-muted">|</span>
                                <span class="text-secondary small">${a.nombre_completo}</span>
                            </div>
                        </div>
                        <button class="btn btn-sm btn-outline-info fw-bold py-1 px-3 shadow-sm" 
                                onclick="window.cierreGestionarInasistencia(${a.empleado_id}, '${a.fecha}', '${nameEscaped}')">
                            <i class="bi bi-gear-fill me-1"></i> Gestionar
                        </button>
                    </li>
                `;
            }).join('');
            content.innerHTML = `
                <h4 class="text-info fw-bold"><i class="bi bi-info-circle"></i> SOFT STOP: Inasistencias no justificadas</h4>
                <p>Hay <strong>${ev.inasistencias_injustificadas} inasistencias</strong>. Si cierra ahora, se consolidarán como inasistencias definitivas sin goce de sueldo, o puedes gestionarlas desde aquí.</p>
                <div class="border rounded-3 shadow-sm bg-white mb-3" style="max-height:180px; overflow-y:auto;">
                    <ul class="list-unstyled mb-0">${list}</ul>
                </div>
                <div class="form-check">
                    <input class="form-check-input" type="checkbox" id="chk-aceptar-inasistencias" onchange="window.cierreWizardState.aceptarInasistencias = this.checked; document.getElementById('btn-cierre-wizard-next').disabled = !this.checked;">
                    <label class="form-check-label fw-bold" for="chk-aceptar-inasistencias">
                        Acepto consolidar estas inasistencias.
                    </label>
                </div>
            `;
            btnNext.style.display = 'inline-block';
            btnNext.disabled = true;
            btnNext.onclick = () => renderWizardStep(5);
        } else {
            content.innerHTML = `
                <div class="text-center py-5">
                    <i class="bi bi-check-circle-fill text-success" style="font-size: 4rem;"></i>
                    <h4 class="mt-3">Sin Inasistencias Pendientes</h4>
                    <p class="text-muted">No hay inasistencias injustificadas en el periodo.</p>
                </div>
            `;
            window.cierreWizardState.aceptarInasistencias = true;
            btnNext.style.display = 'inline-block';
            btnNext.disabled = false;
            btnNext.onclick = () => renderWizardStep(5);
        }
    } else if (step === 5) { // Reporte Final
        content.innerHTML = `
            <h4 class="fw-bold mb-4"><i class="bi bi-file-text"></i> Previsualización de Cierre</h4>
            <div class="row mb-3">
                <div class="col-4">
                    <div class="card border-0 bg-light shadow-sm h-100">
                        <div class="card-body py-3">
                            <h6 class="text-muted text-uppercase small fw-bold mb-1" style="font-size: 0.72rem;">HE Netas a Pago</h6>
                            <h3 class="text-success fw-bold mb-0">${ev.resumen.he_aprobadas_horas || 0} <span class="fs-6 text-muted">hrs</span></h3>
                            <small class="text-muted d-block mt-1">(${ev.resumen.he_aprobadas_count || 0} autorizaciones)</small>
                        </div>
                    </div>
                </div>
                <div class="col-4">
                    <div class="card border-0 bg-light shadow-sm h-100">
                        <div class="card-body py-3">
                            <h6 class="text-muted text-uppercase small fw-bold mb-1" style="font-size: 0.72rem;">Deuda Neta Restante</h6>
                            <h3 class="text-danger fw-bold mb-0">${ev.resumen.deuda_neta_horas || 0} <span class="fs-6 text-muted">hrs</span></h3>
                            <small class="text-muted d-block mt-1">Suma de saldos negativos</small>
                        </div>
                    </div>
                </div>
                <div class="col-4">
                    <div class="card border-0 bg-light shadow-sm h-100">
                        <div class="card-body py-3">
                            <h6 class="text-muted text-uppercase small fw-bold mb-1" style="font-size: 0.72rem;">Inasistencias Selladas</h6>
                            <h3 class="text-dark fw-bold mb-0">${ev.inasistencias_injustificadas}</h3>
                            <small class="text-muted d-block mt-1">Aceptadas en paso 4</small>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Desglose de Deuda Neta -->
            <div class="card border-0 shadow-sm mb-4">
                <div class="card-header bg-light border-0 py-2">
                    <h6 class="text-dark fw-bold mb-0 small"><i class="bi bi-pie-chart-fill me-1 text-danger"></i> Detalle de la Deuda Neta Restante del Área</h6>
                </div>
                <div class="card-body p-0">
                    <ul class="list-group list-group-flush small">
                        <li class="list-group-item d-flex justify-content-between align-items-center py-2 px-3">
                            <span><i class="bi bi-clock-history me-2 text-warning"></i> Deuda por Atrasos Netos</span>
                            <span class="fw-bold text-dark">${ev.resumen.deuda_atrasos_horas || 0} hrs</span>
                        </li>
                        <li class="list-group-item d-flex justify-content-between align-items-center py-2 px-3">
                            <span><i class="bi bi-egg-fried me-2 text-info"></i> Deuda por Exceso de Colación</span>
                            <span class="fw-bold text-dark">${ev.resumen.deuda_colacion_horas || 0} hrs</span>
                        </li>
                        <li class="list-group-item d-flex justify-content-between align-items-center py-2 px-3">
                            <span><i class="bi bi-box-arrow-right me-2 text-secondary"></i> Deuda por Salidas Adelantadas</span>
                            <span class="fw-bold text-dark">${ev.resumen.deuda_salidas_horas || 0} hrs</span>
                        </li>
                        <li class="list-group-item d-flex justify-content-between align-items-center py-2 px-3">
                            <span><i class="bi bi-calendar-x me-2 text-danger"></i> Deuda por Permisos Personales</span>
                            <span class="fw-bold text-dark">${ev.resumen.deuda_permisos_horas || 0} hrs</span>
                        </li>
                    </ul>
                </div>
            </div>
            
            <div class="text-center my-3">
                <button class="btn btn-outline-success fw-bold px-4 py-2.5 w-100 shadow-sm" onclick="window.cierreWizardDownloadExcel()">
                    <i class="bi bi-file-earmark-excel-fill me-2"></i> Descargar Excel de Previsualización
                </button>
            </div>

            <div class="alert alert-warning mt-3 border-warning">
                <i class="bi bi-exclamation-triangle-fill me-2"></i><strong>Atención:</strong> Esta acción sellará el periodo. Los empleados en el biométrico NO podrán alterar la asistencia de estas fechas retrospectivamente.
            </div>
        `;
        btnNext.innerHTML = '<i class="bi bi-lock-fill"></i> Sellar Periodo Definitivamente';
        btnNext.className = 'btn btn-warning fw-bold px-4';
        btnNext.disabled = false;
        btnNext.style.display = 'inline-block';
        btnNext.onclick = confirmarCierreRRHH;
    }
}

window.cierreWizardDownloadExcel = function() {
    const s = window.cierreWizardState;
    if (!s || !s.fIni || !s.fFin) {
        showToast("Rango de fechas no válido para exportar.", "error");
        return;
    }
    const token = typeof AuthService !== 'undefined' ? AuthService.getToken() : localStorage.getItem('access_token');
    const tokenParam = token ? `&token=${encodeURIComponent(token)}` : '';
    const url = `/api/reports/asistencia/excel/?fecha_inicio=${s.fIni}&fecha_fin=${s.fFin}&area=${encodeURIComponent(s.area)}${tokenParam}`;
    window.location.href = url;
};

function nextWizardStep() {
    const s = window.cierreWizardState.currentStep;
    if (s < 5) renderWizardStep(s + 1);
}

async function recargarPreEvaluacionCierre() {
    const s = window.cierreWizardState;
    const url = `/api/cierre/pre-evaluacion?fecha_inicio=${s.fIni}&fecha_fin=${s.fFin}&area=${encodeURIComponent(s.area)}`;
    try {
        const resp = await fetch(url, { headers: { 'Authorization': `Bearer ${AuthService.getToken()}` } });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || "Fallo en pre-evaluación");
        
        window.cierreWizardState.evaluacion = data;
        renderWizardStep(s.currentStep);
        
        if (typeof loadMarcacionesData === 'function') {
            loadMarcacionesData();
        }
    } catch (e) {
        showToast("Error al actualizar estado: " + e.message, "error");
    }
}

window.cierreResolverHE = async function(empId, fecha, minutos, estado) {
    if (typeof showBatchLoadingOverlay === 'function') {
        showBatchLoadingOverlay(estado === 'APROBADO' ? 'Procesando aprobación de Hora Extra...' : 'Procesando rechazo de Hora Extra...');
    }
    try {
        const res = await fetch('/api/asistencia/aprobar-he-batch/', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${AuthService.getToken()}`
            },
            body: JSON.stringify([{
                empleado_id: empId,
                fecha: fecha,
                estado: estado,
                minutos_autorizados: estado === 'APROBADO' ? minutos : 0
            }])
        });
        const data = await res.json();
        if (data.success || res.ok) {
            showToast(estado === 'APROBADO' ? '✅ Hora Extra aprobada' : '❌ Hora Extra rechazada', 'success');
            await recargarPreEvaluacionCierre();
        } else {
            showToast('Error: ' + (data.detail || 'Error al procesar'), 'danger');
        }
    } catch (e) {
        showToast('Error de conexión: ' + e.message, 'danger');
    } finally {
        if (typeof hideBatchLoadingOverlay === 'function') {
            hideBatchLoadingOverlay();
        }
    }
};

window.cierreResolverTodasHE = async function() {
    const s = window.cierreWizardState;
    if (!s.evaluacion || !s.evaluacion.detalle_he || s.evaluacion.detalle_he.length === 0) return;
    
    if (!confirm(`¿Está seguro que desea APROBAR todas las horas extras pendientes (${s.evaluacion.detalle_he.length}) de este período?`)) {
        return;
    }

    if (typeof showBatchLoadingOverlay === 'function') {
        showBatchLoadingOverlay(`Aprobando todas las horas extras pendientes (${s.evaluacion.detalle_he.length})...`);
    }

    const items = s.evaluacion.detalle_he.map(a => ({
        empleado_id: a.empleado_id,
        fecha: a.fecha,
        estado: 'APROBADO',
        minutos_autorizados: a.minutos_bruto
    }));

    try {
        const res = await fetch('/api/asistencia/aprobar-he-batch/', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${AuthService.getToken()}`
            },
            body: JSON.stringify(items)
        });
        const data = await res.json();
        if (data.success || res.ok) {
            showToast(`✅ Aprobadas ${items.length} horas extras exitosamente.`, 'success');
            await recargarPreEvaluacionCierre();
        } else {
            showToast('Error: ' + (data.detail || 'Error al procesar lote'), 'danger');
        }
    } catch (e) {
        showToast('Error de conexión: ' + e.message, 'danger');
    } finally {
        if (typeof hideBatchLoadingOverlay === 'function') {
            hideBatchLoadingOverlay();
        }
    }
};

window.cierreCorregirAnomalia = function(empId, fecha, nombreCompleto, horaEntrada, horaSalida) {
    if (typeof openManualEntryModal === 'function') {
        openManualEntryModal(
            empId,
            fecha,
            nombreCompleto,
            "Ingreso Manual (Corrección de Anomalía)",
            horaEntrada || null,
            horaSalida || null
        );
    } else {
        showToast("Error: Modal de ingreso manual no disponible.", "danger");
    }
};

window.cierreGestionarInasistencia = function(empId, fecha, nombreCompleto) {
    if (typeof openAsistenciaActionModal === 'function') {
        openAsistenciaActionModal(
            empId,
            fecha,
            nombreCompleto
        );
    } else {
        showToast("Error: Modal de acciones de asistencia no disponible.", "danger");
    }
};

async function confirmarCierreRRHH() {
    const s = window.cierreWizardState;
    const btn = document.getElementById('btn-cierre-wizard-next');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Sellando...';

    try {
        const resp = await fetch('/api/cierre/ejecutar', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${AuthService.getToken()}`
            },
            body: JSON.stringify({
                fecha_inicio: s.fIni,
                fecha_fin: s.fFin,
                area: s.area,
                aceptar_inasistencias: s.aceptarInasistencias
            })
        });

        const res = await resp.json();
        if (resp.ok) {
            showToast("✅ Periodo cerrado exitosamente", "success");
            const m = bootstrap.Modal.getInstance(document.getElementById('modal-cierre-wizard'));
            if (m) m.hide();
            loadMarcacionesData();
        } else {
            showToast("Error: " + (res.detail || "No se pudo cerrar el periodo"), "error");
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-lock-fill"></i> Sellar Periodo Definitivamente';
        }
    } catch (e) {
        console.error(e);
        showToast("Error de conexión al cerrar periodo", "error");
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-lock-fill"></i> Sellar Periodo Definitivamente';
    }
}

async function openHistorialCierresModal() {
    try {
        const resp = await fetch('/api/asistencia/periodo-rrhh/historial/');
        const historial = await resp.json();

        const user = AuthService.getUser();
        const isSuperAdmin = user && (user.alcance_global === true || user.alcance_global === 1);

        const html = `
            <div class="modal fade" id="modal-historial-cierres" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content border-0 shadow-lg">
                        <div class="modal-header border-0 pb-0">
                            <h5 class="modal-title fw-bold"><i class="bi bi-clock-history me-2 text-primary"></i> Historial de Cierres RRHH</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="table-responsive rounded border">
                                <table class="table table-hover mb-0">
                                    <thead class="table-light">
                                        <tr class="small text-uppercase">
                                            <th>Periodo</th>
                                            <th>Área</th>
                                            <th>Fecha Registro</th>
                                            <th>Usuario</th>
                                            <th>Comentarios</th>
                                            ${isSuperAdmin ? '<th>Acciones</th>' : ''}
                                        </tr>
                                    </thead>
                                    <tbody class="align-middle">
                                        ${historial.length === 0 ? `<tr><td colspan="${isSuperAdmin ? '6' : '5'}" class="text-center py-5 text-muted">No se registran cierres previos.</td></tr>` : 
                                            historial.map(c => `
                                            <tr>
                                                <td><span class="badge bg-info-subtle text-info border border-info-subtle">${window.formatFechaDDMMYYYY(c.fecha_inicio)} al ${window.formatFechaDDMMYYYY(c.fecha_fin)}</span></td>
                                                <td><span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle">${c.area || 'Todas'}</span></td>
                                                <td class="small">${(() => {
                                                    const d = new Date(c.created_at || c.fecha_cierre);
                                                    if (isNaN(d.getTime())) return 'N/A';
                                                    const formattedDatePart = window.formatFechaDDMMYYYY(d);
                                                    const timePart = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
                                                    return `${formattedDatePart} ${timePart}`;
                                                })()}</td>
                                                <td><i class="bi bi-person-circle me-1"></i> ${c.username || c.usuario_cierre || 'N/A'}</td>
                                                <td class="small text-muted italic">${c.comentarios || c.comentario || '--'}</td>
                                                ${isSuperAdmin ? `
                                                    <td>
                                                        <button class="btn btn-sm btn-outline-danger fw-bold py-0" onclick="reabrirPeriodo(${c.id}, '${c.fecha_inicio}', '${c.fecha_fin}', '${c.area}')">
                                                            <i class="bi bi-unlock-fill"></i> Reabrir
                                                        </button>
                                                    </td>
                                                ` : ''}
                                            </tr>
                                            `).join('')
                                        }
                                    </tbody>
                                </table>
                            </div>
                        </div>
                        <div class="modal-footer border-0 pt-0">
                            <button type="button" class="btn btn-secondary px-4" data-bs-dismiss="modal">Cerrar</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        const old = document.getElementById('modal-historial-cierres');
        if (old) old.remove();

        document.body.insertAdjacentHTML('beforeend', html);
        const modal = new bootstrap.Modal(document.getElementById('modal-historial-cierres'));
        modal.show();

    } catch (e) {
        console.error(e);
        showToast("Error al cargar historial", "error");
    }
}

window.reabrirPeriodo = async function(id, fechaInicio, fechaFin, area) {
    if (!confirm(`¿Está seguro que desea reabrir el período cerrado del ${fechaInicio} al ${fechaFin} para el área "${area}"?\n\nEsta acción eliminará el bloqueo y permitirá modificaciones/recálculos.`)) {
        return;
    }
    
    try {
        const resp = await fetch(`/api/cierre/${id}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${AuthService.getToken()}`
            }
        });
        
        const res = await resp.json();
        if (resp.ok) {
            showToast("✅ Periodo reabierto con éxito", "success");
            const m = bootstrap.Modal.getInstance(document.getElementById('modal-historial-cierres'));
            if (m) m.hide();
            loadMarcacionesData();
        } else {
            showToast("Error: " + (res.detail || "No se pudo reabrir el periodo"), "error");
        }
    } catch (e) {
        console.error(e);
        showToast("Error de conexión al reabrir periodo", "error");
    }
};


/* ==========================================
   MERGED FROM vista_analitica.js
   ========================================== */
/**
 * vista_analitica.js
 * Vista Analítica de Marcaciones — Balance de Masas HH/Deudas
 * ISOLADO: No toca ni modifica ninguna lógica existente.
 */

window.vistaAnaliticaState = window.vistaAnaliticaState || {
    soloNegativo: false,
    soloConHE: false,
    showBonos: false,
    showHE: false,
    showDeudas: false,
    showIncidencias: false,
    showSaldoMeta: true  // Visible por defecto cuando hay bolsa flexible
};

window.getStickyLeft = function(key, subIndex, stickyCols, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta) {
    let offset = 0;
    const keys = ['empleado', 'bonos', 'incidencias', 'he', 'deudas', 'saldo', 'bolsa'];
    for (const k of keys) {
        if (k === key) {
            if (k === 'bonos' && showBonos) return offset + subIndex * 65;
            if (k === 'incidencias' && showIncidencias) return offset + subIndex * 65;
            if (k === 'he' && showHE) return offset + subIndex * 65;
            if (k === 'deudas' && showDeudas) return offset + subIndex * 65;
            if (k === 'bolsa' && showSaldoMeta) return offset + subIndex * 72;
            return offset;
        }
        if (stickyCols[k]) {
            offset += stickyCols[k].width;
        }
    }
    return offset;
};

window.getStickyWidthStyle = function(key, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta) {
    let w = 0;
    if (key === 'bonos') w = showBonos ? 65 : 50;
    else if (key === 'incidencias') w = showIncidencias ? 65 : 50;
    else if (key === 'he') w = showHE ? 65 : 50;
    else if (key === 'deudas') w = showDeudas ? 65 : 50;
    else if (key === 'saldo') w = 70;
    else if (key === 'bolsa') w = showSaldoMeta ? 72 : 50;
    return `width:${w}px; min-width:${w}px; max-width:${w}px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;`;
};

window.calcularStatsEmpleado = function(emp, dates, feriadosArray) {
    let he_bruto=0, he_apr=0, he_rec=0, he_pend=0, he_compensado=0, d_tot=0, min_atr=0, min_sad=0, min_col=0, min_per=0;
    let cnt_atr=0, cnt_sad=0, cnt_inas=0, cnt_esp=0, cnt_per=0, cnt_efectivos=0;
    const esBolsa = emp.tipo_programacion === 'FLEXIBLE_BOLSA'
                 || (emp.info && emp.info.tipo_programacion === 'FLEXIBLE_BOLSA');
    emp._esBolsaFlag = esBolsa;
    let acumBolsa=0, excedido=false, metaMin=0;

    if (esBolsa && emp.info) {
        let metaOriginal = emp.info.meta_mensual_minutos
               || Math.round((emp.info.meta_horas_semanales || 0) * 60);

        let diasProgramados = 0;
        let diasJustificados = 0;
        
        dates.forEach(d => {
            const dt = new Date(d+'T00:00:00');
            const isFer = feriadosArray.includes(d);
            const diCheck = emp.dias[d] || {};
            
            const dayDB = (dt.getDay() + 6) % 7; 
            const isStructurallyLibre = (emp.info.turno_dias && emp.info.turno_dias[dayDB] && emp.info.turno_dias[dayDB].es_libre === 1);
            
            const isDescanso = isFer || isStructurallyLibre || (diCheck.estado === 'LIBRE');
            
            if (!isDescanso) {
                diasProgramados++;
                const estadosJustificados = ['VACACIONES', 'LICENCIA', 'LIC_COMUN', 'LIC_MUTUAL', 'CUMPLEAÑOS', 'DUELO', 'PERMISO', 'NO NACIDO', 'DEFUNCION'];
                const isJustificado = diCheck.estado && (
                    estadosJustificados.some(ej => diCheck.estado.toUpperCase().includes(ej)) ||
                    (diCheck.nomenclatura && diCheck.nomenclatura.trim() !== '')
                );
                
                if (isJustificado) {
                    diasJustificados++;
                    diCheck._esDiaJustificadoBolsa = true;
                }
            }
        });

        if (diasProgramados > 0 && diasJustificados > 0) {
            const valorTurnoMin = metaOriginal / diasProgramados;
            metaMin = Math.round(metaOriginal - (valorTurnoMin * diasJustificados));
            emp._metaOriginalBolsa = metaOriginal;
            emp._diasJustificadosBolsa = diasJustificados;
            emp._valorTurnoMinBolsa = valorTurnoMin;
        } else {
            metaMin = metaOriginal;
        }
        
        if (emp.info.meta_ajustada_minutos_descuento && diasJustificados === 0) {
            metaMin = Math.max(0, metaMin - emp.info.meta_ajustada_minutos_descuento);
        }
    }

    let acumSemanal = 0;
    let startDayJS = 1; 
    if (emp.info && emp.info.primer_dia_semana_turno !== undefined) {
        startDayJS = (emp.info.primer_dia_semana_turno + 1) % 7;
    }

    dates.forEach(d => {
        const dt = new Date(d+'T00:00:00');
        if (dt.getDay() === startDayJS) acumSemanal = 0; 

        const di = emp.dias[d];
        if (!di) return;

        if (esBolsa) { di._esBolsa = true; di._metaMinBolsa = metaMin; }

        const trab = Math.round((di.horas_trabajadas||0)*60);
        const isEsp = di.estado === 'JORNADA_ESPECIAL' || di.estado === 'EXTRA' || di.estado === 'FERIADO Y JORNADA EXTRA' || di.estado === 'DÍA LIBRE Y JORNADA EXTRA';
        
        if (!esBolsa && !isEsp) {
            acumSemanal += trab;
        }
        if (!esBolsa) di._acumuladoSemanalSnap = acumSemanal;
        if (!isEsp && !esBolsa) {
            const tieneCondonacion = (di.deuda_condonada || 0) > 0;
            const netDeuda = tieneCondonacion ? 0 : (di.minutos_deuda || 0);

            const rawCol = di.minutos_exceso_colacion || 0;
            const rawPer = di.minutos_permiso_personal_deuda || 0;
            const rawAtr = tieneCondonacion ? 0 : (di.minutos_atraso || 0);
            const rawSad = tieneCondonacion ? 0 : (di.minutos_salida_adelantada || 0);

            const rawTotal = rawCol + rawPer + rawAtr + rawSad;

            let dayCol = 0;
            let dayPer = 0;
            let dayAtr = 0;
            let daySad = 0;

            if (netDeuda > 0 && rawTotal > 0) {
                if (netDeuda >= rawTotal) {
                    dayCol = rawCol;
                    dayPer = rawPer;
                    dayAtr = rawAtr;
                    daySad = rawSad;
                } else {
                    const factor = netDeuda / rawTotal;
                    dayCol = rawCol * factor;
                    dayPer = rawPer * factor;
                    dayAtr = rawAtr * factor;
                    daySad = rawSad * factor;
                }
            }

            d_tot   += netDeuda;
            min_col += dayCol;
            min_per += dayPer;
            min_atr += dayAtr;
            min_sad += daySad;

            if ((di.minutos_atraso||0) > 0 && !tieneCondonacion)  cnt_atr++;
            if ((di.minutos_salida_adelantada||0) > 0 && !tieneCondonacion) cnt_sad++;
            if (di.tiene_permiso_hora || di.permiso_activo) cnt_per++;
        }
        if (di.estado === 'INASISTENCIA') cnt_inas++;
        if (isEsp)                         cnt_esp++;
        if (di.hora_entrada_real && !isEsp && !['LIBRE','FERIADO','INASISTENCIA'].includes(di.estado)) cnt_efectivos++;

        if (!isEsp) {
            if (esBolsa) {
                const snapAntes = acumBolsa; 
                acumBolsa += trab;
                di._acumuladoBolsaSnapPrev = snapAntes; 
                di._acumuladoBolsaSnap = acumBolsa;    
                di._metaMinBolsa = metaMin;             
                if (excedido)                                    he_bruto += trab;
                else if (acumBolsa > metaMin && trab > 0) { he_bruto += acumBolsa - metaMin; excedido = true; }
            } else {
                he_bruto += Math.max(di.minutos_extra_bruto || 0, di.minutos_extra_autorizados || 0);
            }
        } else if (esBolsa) {
            di._acumuladoBolsaSnapPrev = acumBolsa;
            di._acumuladoBolsaSnap = acumBolsa;
            di._metaMinBolsa = metaMin;
        }

        if (!isEsp) {
            if (di.estado_he === 'APROBADO') {
                const apr = di.minutos_extra_autorizados || 0;
                he_apr += apr;
            } else if (di.estado_he === 'RECHAZADO') {
                he_rec += (di.minutos_extra_bruto || 0);
            } else if ((di.minutos_extra_bruto || 0) > 0) {
                he_pend += (di.minutos_extra_bruto || 0);
            }
        }
        he_compensado += (di.minutos_compensados_he || 0);
    });

    he_bruto = Math.round(he_bruto * 10000) / 10000;
    he_apr = Math.round(he_apr * 10000) / 10000;
    he_rec = Math.round(he_rec * 10000) / 10000;
    he_pend = Math.round(he_pend * 10000) / 10000;

    const saldo = he_apr - d_tot - he_compensado;
    const saldoMeta = esBolsa ? (acumBolsa - metaMin) : null; 
    return { emp, he_bruto, he_apr, he_rec, he_pend, d_tot, min_atr, min_sad, min_col, min_per,
             cnt_atr, cnt_sad, cnt_inas, cnt_esp, cnt_per, cnt_efectivos, saldo,
             esBolsa, metaMin, acumBolsa, saldoMeta };
};

window.renderEmployeeRowHtml = function(r, dates, feriadosArray, getFeriadoDesc, hasBonos, showBonos, bonosNombres, bonosEval, showIncidencias, showHE, showDeudas, hayBolsa, showSaldoMeta, s, stickyCols) {
    const { emp } = r;
    const sClass = r.saldo > 0 ? 'text-success' : r.saldo < 0 ? 'text-danger' : 'text-muted';
    const sPrefix = r.saldo > 0 ? '+' : r.saldo < 0 ? '-' : '';
    const nameClass = emp.activo ? '' : 'text-danger opacity-75';

    const empEval = bonosEval[emp.id] || {};
    let bonoCells = '';
    if (hasBonos) {
        const wStyle = window.getStickyWidthStyle('bonos', showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);
        if (showBonos) {
            bonoCells = bonosNombres.map((bName, idx) => {
                const bRes = empEval[bName];
                const borderStyle = idx === 0 ? 'border-left:3px solid #10b981' : 'border-left:1px solid #e2e8f0';
                const cellLeft = window.getStickyLeft('bonos', idx, stickyCols, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);
                const inlineStyle = `position:sticky; z-index:40; ${borderStyle}; left:${cellLeft}px; ${wStyle}`;
                if (!bRes || !bRes.aplica) return `<td class="text-center align-middle sticky-premium-col" style="background:#f8fafc;font-size:0.75rem;${inlineStyle}"></td>`;
                if (bRes.califica) {
                    return `<td class="text-center align-middle text-success fw-bold sticky-premium-col" style="background:#f8fafc;font-size:1.1rem;${inlineStyle}" title="${bRes.motivo||''}"><i class="bi bi-check-circle-fill"></i></td>`;
                } else {
                    return `<td class="text-center align-middle text-danger opacity-75 sticky-premium-col" style="background:#f8fafc;font-size:1.1rem;${inlineStyle}" title="${bRes.motivo||''}"><i class="bi bi-dash-circle-fill"></i></td>`;
                }
            }).join('');
        } else {
            let cntAplica = 0;
            let cntCalifica = 0;
            bonosNombres.forEach(bName => {
                const bRes = empEval[bName];
                if (bRes && bRes.aplica) {
                    cntAplica++;
                    if (bRes.califica) cntCalifica++;
                }
            });
            const cellLeft = window.getStickyLeft('bonos', 0, stickyCols, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);
            const inlineStyle = `position:sticky; z-index:40; left:${cellLeft}px; ${wStyle}`;
            if (cntAplica > 0) {
                const color = cntCalifica === cntAplica ? 'text-success' : (cntCalifica > 0 ? 'text-warning' : 'text-danger');
                bonoCells = `<td class="text-center align-middle fw-bold ${color} sticky-premium-col" style="background:#f8fafc;font-size:0.78rem;border-left:3px solid #10b981;${inlineStyle}" title="${cntCalifica} cumplidos de ${cntAplica} aplicables">${cntCalifica}/${cntAplica}</td>`;
            } else {
                bonoCells = `<td class="text-center align-middle text-muted sticky-premium-col" style="background:#f8fafc;font-size:0.78rem;border-left:3px solid #10b981;${inlineStyle}"></td>`;
            }
        }
    }

    const dayCells = dates.map(d => {
        const di = emp.dias[d];
        const dt = new Date(d+'T00:00:00');
        const feriadoDesc = getFeriadoDesc(d);
        const isFer = !!feriadoDesc;
        const isWE  = (dt.getDay()===0||dt.getDay()===6);
        const bg = isFer ? 'background:#fff9c4;' : isWE ? 'background:#f8f9fa;' : '';
        const empNameEsc = (emp.nombre_completo||'').replace(/'/g,"\\'");
        const hEnt = di && di.hora_entrada_real ? `'${di.hora_entrada_real}'` : 'null';
        const hSal = di && di.hora_salida_real ? `'${di.hora_salida_real}'` : 'null';
        const cellContent = _analiticaCellContent(di, d, emp, stateMarcacionesApp.viewMode, isFer);
        const tooltipData = _buildRichTooltipData(di, d, dt, feriadoDesc, isWE, emp);
        return `<td class="col-day text-center p-0 align-middle cell-clickable" style="${bg}min-width:48px;height:28px;cursor:pointer;position:relative;overflow:visible !important;"
                    onclick="openAsistenciaActionModal(${emp.id},'${d}','${empNameEsc}',${hEnt},${hSal})"
                    ondblclick="openJustifyModal(${emp.id},'${empNameEsc}','${d}')"
                    data-grid-tooltip data-bs-html="true"
                    data-bs-content="${tooltipData}">
                    ${cellContent}
                </td>`;
    }).join('');

    const hasHE = r.he_pend > 0;
    const heIndicator = hasHE ? `<i class="bi bi-clock-history text-warning ms-1" style="font-size:0.68rem" title="Tiene HE pendientes — Doble clic para gestionar"></i>` : '';

    const getStickyLeftLocal = (key, subIndex = 0) => window.getStickyLeft(key, subIndex, stickyCols, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);
    const getStickyWidthStyleLocal = (key) => window.getStickyWidthStyle(key, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);

    return `<tr id="row-empleado-${emp.id}">
        <td class="${nameClass} sticky-col-analitica emp-name-cell text-start ps-2 align-middle" style="position:sticky; left:0; z-index:50; white-space:nowrap;cursor:pointer;font-size:0.75rem; width:260px; min-width:260px; max-width:260px;"
            ondblclick="openBatchApprovalModal(${emp.id},'${(emp.nombre_completo||'').replace(/'/g,"\\'")}')"
            title="${hasHE ? '⚡ Doble clic → Gestionar Horas Extra' : 'Doble clic → Ver Horas Extra'}">
            <div class="emp-name-link">${emp.nombre_completo||'—'}${heIndicator}</div>
            <div class="emp-area-label">${emp.area}${emp.turno?' · '+emp.turno:''}</div>
        </td>
        ${bonoCells}
        ${showIncidencias ? `
        <td class="text-center align-middle sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.78rem;border-left:3px solid #f59e0b;left:${getStickyLeftLocal('incidencias', 0)}px;${getStickyWidthStyleLocal('incidencias')}">${r.cnt_per||''}</td>
        <td class="text-center align-middle sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.78rem;left:${getStickyLeftLocal('incidencias', 1)}px;${getStickyWidthStyleLocal('incidencias')}">${r.cnt_atr||''}</td>
        <td class="text-center align-middle sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.78rem;left:${getStickyLeftLocal('incidencias', 2)}px;${getStickyWidthStyleLocal('incidencias')}">${r.cnt_sad||''}</td>
        <td class="text-center align-middle ${r.cnt_inas>0?'text-danger fw-bold':''} sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.78rem;left:${getStickyLeftLocal('incidencias', 3)}px;${getStickyWidthStyleLocal('incidencias')}">${r.cnt_inas||''}</td>
        <td class="text-center align-middle ${r.cnt_esp>0?'text-info fw-bold':''} sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.78rem;left:${getStickyLeftLocal('incidencias', 4)}px;${getStickyWidthStyleLocal('incidencias')}">${r.cnt_esp>0?r.cnt_esp+' ★':''}</td>
        <td class="text-center align-middle fw-bold sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.78rem;left:${getStickyLeftLocal('incidencias', 5)}px;${getStickyWidthStyleLocal('incidencias')}">${((r.cnt_per||0)+(r.cnt_atr||0)+(r.cnt_sad||0)+(r.cnt_inas||0)+(r.cnt_esp||0))||''}</td>` : `<td class="text-center align-middle fw-bold sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.78rem;border-left:3px solid #f59e0b;color:#f59e0b;left:${getStickyLeftLocal('incidencias')}px;${getStickyWidthStyleLocal('incidencias')}">${((r.cnt_per||0)+(r.cnt_atr||0)+(r.cnt_sad||0)+(r.cnt_inas||0)+(r.cnt_esp||0))>0 ? '<i class="bi bi-flag-fill me-1"></i>' + ((r.cnt_per||0)+(r.cnt_atr||0)+(r.cnt_sad||0)+(r.cnt_inas||0)+(r.cnt_esp||0)) : ''}</td>`}
        ${showHE ? `
        <td class="text-center align-middle tabular-nums text-warning fw-bold sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;border-left:3px solid #3b82f6;left:${getStickyLeftLocal('he', 0)}px;${getStickyWidthStyleLocal('he')}">${r.he_pend>0?_fmtMin(r.he_pend):''}</td>
        <td class="text-center align-middle tabular-nums text-success fw-bold sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;left:${getStickyLeftLocal('he', 1)}px;${getStickyWidthStyleLocal('he')}">${r.he_apr>0?_fmtMin(r.he_apr):''}</td>
        <td class="text-center align-middle tabular-nums text-danger sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;left:${getStickyLeftLocal('he', 2)}px;${getStickyWidthStyleLocal('he')}">${r.he_rec>0?_fmtMin(r.he_rec):''}</td>
        <td class="text-center align-middle tabular-nums fw-bold sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;left:${getStickyLeftLocal('he', 3)}px;${getStickyWidthStyleLocal('he')}">${r.he_bruto>0?_fmtMin(r.he_bruto):''}</td>` : `<td class="text-center align-middle tabular-nums fw-bold sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;border-left:3px solid #3b82f6;color:#3b82f6;left:${getStickyLeftLocal('he')}px;${getStickyWidthStyleLocal('he')}">${r.he_bruto>0 ? '<i class="bi bi-lightning-charge-fill me-1"></i>' + _fmtMin(r.he_bruto):''}</td>`}
        ${showDeudas ? `
        <td class="text-center align-middle tabular-nums ${r.min_col>0?'text-muted fw-bold':''} sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;border-left:3px solid #64748b;left:${getStickyLeftLocal('deudas', 0)}px;${getStickyWidthStyleLocal('deudas')}">${r.min_col>0?_fmtMin(r.min_col):''}</td>
        <td class="text-center align-middle tabular-nums ${r.min_per>0?'text-muted fw-bold':''} sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;left:${getStickyLeftLocal('deudas', 1)}px;${getStickyWidthStyleLocal('deudas')}">${r.min_per>0?_fmtMin(r.min_per):''}</td>
        <td class="text-center align-middle tabular-nums ${r.min_atr>0?'text-muted fw-bold':''} sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;left:${getStickyLeftLocal('deudas', 2)}px;${getStickyWidthStyleLocal('deudas')}">${r.min_atr>0?_fmtMin(r.min_atr):''}</td>
        <td class="text-center align-middle tabular-nums ${r.min_sad>0?'text-muted fw-bold':''} sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;left:${getStickyLeftLocal('deudas', 3)}px;${getStickyWidthStyleLocal('deudas')}">${r.min_sad>0?_fmtMin(r.min_sad):''}</td>
        <td class="text-center align-middle tabular-nums fw-bold text-muted sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;left:${getStickyLeftLocal('deudas', 4)}px;${getStickyWidthStyleLocal('deudas')}">${r.d_tot>0?_fmtMin(r.d_tot):''}</td>` : `<td class="text-center align-middle tabular-nums fw-bold text-muted sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;border-left:3px solid #64748b;left:${getStickyLeftLocal('deudas')}px;${getStickyWidthStyleLocal('deudas')}">${r.d_tot>0 ? '<i class="bi bi-clock-history me-1"></i>' + _fmtMin(r.d_tot):''}</td>`}
        <td class="text-center align-middle tabular-nums fw-bold ${sClass} sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:40; background:#f9fafb;font-size:0.8rem;left:${getStickyLeftLocal('saldo')}px;${getStickyWidthStyleLocal('saldo')}">${sPrefix}${_fmtMin(Math.abs(r.saldo))}</td>
        ${(hayBolsa) ? (
            showSaldoMeta
                ? (r.esBolsa
                    ? (() => {
                        const sm = r.saldoMeta;
                        const smColor = sm >= 0 ? '#10b981' : '#ef4444';
                        const smBg    = sm >= 0 ? '#f0fdf4' : '#fff5f5';
                        const smSign  = sm > 0 ? '+' : sm < 0 ? '-' : '';
                        const metaTooltip = r.emp._diasJustificadosBolsa > 0 
                            ? `Meta original: ${_fmtMin(r.emp._metaOriginalBolsa)} | Descuento por ${r.emp._diasJustificadosBolsa} día(s) justificado(s)`
                            : `Meta mensual del ciclo`;

                        return `<td class="text-center align-middle tabular-nums sticky-premium-col" style="position:sticky; z-index:40; background:#faf5ff;border-left:3px solid #8b5cf6;font-size:0.78rem;left:${getStickyLeftLocal('bolsa', 0)}px;${getStickyWidthStyleLocal('bolsa')}" title="${metaTooltip}">${_fmtMin(r.metaMin)}</td>
                                <td class="text-center align-middle tabular-nums sticky-premium-col" style="position:sticky; z-index:40; background:#faf5ff;font-size:0.78rem;left:${getStickyLeftLocal('bolsa', 1)}px;${getStickyWidthStyleLocal('bolsa')}" title="Horas acumuladas en el ciclo">${_fmtMin(r.acumBolsa)}</td>
                                <td class="text-center align-middle tabular-nums fw-bold sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:40; background:${smBg};color:${smColor};font-size:0.8rem;left:${getStickyLeftLocal('bolsa', 2)}px;${getStickyWidthStyleLocal('bolsa')}" title="Balance: negativo = falta, positivo = excedió">${smSign}${_fmtMin(Math.abs(sm))}</td>`;
                    })()
                    : `<td class="sticky-premium-col" style="position:sticky; z-index:40; background:#faf5ff;border-left:3px solid #8b5cf6;left:${getStickyLeftLocal('bolsa', 0)}px;${getStickyWidthStyleLocal('bolsa')}"></td>
                       <td class="sticky-premium-col" style="position:sticky; z-index:40; background:#faf5ff;left:${getStickyLeftLocal('bolsa', 1)}px;${getStickyWidthStyleLocal('bolsa')}"></td>
                       <td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:40; background:#faf5ff;left:${getStickyLeftLocal('bolsa', 2)}px;${getStickyWidthStyleLocal('bolsa')}"></td>`
                  )
                : `<td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:40; background:#faf5ff;border-left:3px solid #8b5cf6;left:${getStickyLeftLocal('bolsa')}px;${getStickyWidthStyleLocal('bolsa')}"></td>`
        ) : ''}
        ${dayCells}
    </tr>`;
};

window.recalculateTotalsRow = function(dates, feriadosArray, getFeriadoDesc) {
    const s = window.vistaAnaliticaState;
    const hasBonos = (stateMarcacionesApp.data.bonos_nombres || []).length > 0;
    const showBonos = window.vistaAnaliticaState.showBonos;
    const bonosNombres = stateMarcacionesApp.data.bonos_nombres || [];
    const showIncidencias = window.vistaAnaliticaState.showIncidencias !== false;
    const showHE = window.vistaAnaliticaState.showHE !== false;
    const showDeudas = window.vistaAnaliticaState.showDeudas !== false;

    const employees = [];
    if (stateMarcacionesApp.data.empleados) {
        stateMarcacionesApp.data.empleados.forEach(e_raw => {
            const eid = e_raw.id;
            const mEmp = stateMarcacionesApp.data.matrix[eid];
            if (!mEmp) return;
            const info = mEmp.info || {};
            employees.push({
                id: eid, info,
                nombre_completo: info.nombre_completo || e_raw.nombre_completo || e_raw.nombre,
                area: info.area || e_raw.area || '',
                turno: info.turno || info.nombre_turno || '',
                turno_dias: info.turno_dias || {},
                tipo_programacion: info.tipo_programacion || '',
                activo: info.activo !== false,
                dias: mEmp
            });
        });
    }

    const rows = employees.map(emp => window.calcularStatsEmpleado(emp, dates, feriadosArray));

    let visibleRows = rows;
    if (s.soloNegativo) visibleRows = visibleRows.filter(r => r.saldo < 0);
    if (s.soloConHE)    visibleRows = visibleRows.filter(r => r.he_bruto > 0);

    const tot = visibleRows.reduce((acc,r) => {
        acc.he_bruto+=r.he_bruto; acc.he_apr+=r.he_apr; acc.he_rec+=r.he_rec; acc.he_pend+=r.he_pend;
        acc.d_tot+=r.d_tot; acc.saldo+=r.saldo;
        acc.cnt_atr+=r.cnt_atr; acc.cnt_sad+=r.cnt_sad; acc.cnt_inas+=r.cnt_inas;
        acc.cnt_esp+=r.cnt_esp; acc.cnt_per+=r.cnt_per;
        acc.min_col+=(r.min_col||0); acc.min_per+=(r.min_per||0); 
        acc.min_atr+=(r.min_atr||0); acc.min_sad+=(r.min_sad||0);
        return acc;
    }, {he_bruto:0,he_apr:0,he_rec:0,he_pend:0,d_tot:0,saldo:0,cnt_atr:0,cnt_sad:0,cnt_inas:0,cnt_esp:0,cnt_per:0,min_col:0,min_per:0,min_atr:0,min_sad:0});

    const totSClass = tot.saldo > 0 ? 'text-success' : tot.saldo < 0 ? 'text-danger' : 'text-muted';
    const totSPrefix = tot.saldo > 0 ? '+' : tot.saldo < 0 ? '-' : '';

    const hayBolsa = rows.some(r => r.esBolsa);
    const showSaldoMeta = hayBolsa && (window.vistaAnaliticaState.showSaldoMeta !== false);

    const stickyCols = {
        empleado: { width: 260 },
        bonos: { width: hasBonos ? (showBonos ? bonosNombres.length * 65 : 50) : 0 },
        incidencias: { width: showIncidencias ? 6 * 65 : 50 },
        he: { width: showHE ? 4 * 65 : 50 },
        deudas: { width: showDeudas ? 5 * 65 : 50 },
        saldo: { width: 70 }
    };
    if (hayBolsa) {
        stickyCols.bolsa = { width: showSaldoMeta ? 3 * 72 : 50 };
    }

    const getStickyLeftLocal = (key, subIndex = 0) => window.getStickyLeft(key, subIndex, stickyCols, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);
    const getStickyWidthStyleLocal = (key) => window.getStickyWidthStyle(key, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);

    let bonosTotalsCell = '';
    if (hasBonos) {
        if (showBonos) {
            bonosTotalsCell = bonosNombres.map((bName, idx) => {
                const borderStyle = idx === 0 ? 'border-left:3px solid #10b981' : 'border-left:1px solid #e2e8f0';
                return `<td class="sticky-premium-col" style="position:sticky; z-index:60; ${borderStyle};left:${getStickyLeftLocal('bonos', idx)}px;${getStickyWidthStyleLocal('bonos')}"></td>`;
            }).join('');
        } else {
            bonosTotalsCell = `<td class="sticky-premium-col" style="position:sticky; z-index:60; border-left:3px solid #10b981;left:${getStickyLeftLocal('bonos')}px;${getStickyWidthStyleLocal('bonos')}"></td>`;
        }
    }

    const totalsRowHtml = `<tr class="fw-bold text-center" style="font-size:0.78rem; border-top: 2px solid #e2e8f0; background: #f8fafc;">
        <td class="sticky-col-analitica text-start ps-2" style="position:sticky; left:0; z-index:60; background: #f8fafc; color: #475569; font-weight: 800; width:260px; min-width:260px; max-width:260px;">TOTALES</td>
        ${bonosTotalsCell}
        ${showIncidencias ? `
        <td class="sticky-premium-col" style="position:sticky; z-index:60; border-left:3px solid #f59e0b;left:${getStickyLeftLocal('incidencias', 0)}px;${getStickyWidthStyleLocal('incidencias')}">${tot.cnt_per||''}</td>
        <td class="sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('incidencias', 1)}px;${getStickyWidthStyleLocal('incidencias')}">${tot.cnt_atr||''}</td>
        <td class="sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('incidencias', 2)}px;${getStickyWidthStyleLocal('incidencias')}">${tot.cnt_sad||''}</td>
        <td class="sticky-premium-col ${tot.cnt_inas>0?'text-danger':''}" style="position:sticky; z-index:60; left:${getStickyLeftLocal('incidencias', 3)}px;${getStickyWidthStyleLocal('incidencias')}">${tot.cnt_inas||''}</td>
        <td class="sticky-premium-col ${tot.cnt_esp>0?'text-info':''}" style="position:sticky; z-index:60; left:${getStickyLeftLocal('incidencias', 4)}px;${getStickyWidthStyleLocal('incidencias')}">${tot.cnt_esp||''}</td>
        <td class="fw-bold sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('incidencias', 5)}px;${getStickyWidthStyleLocal('incidencias')}">${((tot.cnt_per||0)+(tot.cnt_atr||0)+(tot.cnt_sad||0)+(tot.cnt_inas||0)+(tot.cnt_esp||0))||''}</td>` : `<td style="position:sticky; z-index:60; border-left:3px solid #f59e0b; color:#f59e0b;left:${getStickyLeftLocal('incidencias')}px;${getStickyWidthStyleLocal('incidencias')}" class="fw-bold sticky-premium-col">${((tot.cnt_per||0)+(tot.cnt_atr||0)+(tot.cnt_sad||0)+(tot.cnt_inas||0)+(tot.cnt_esp||0))>0 ? '<i class="bi bi-flag-fill me-1"></i>' + ((tot.cnt_per||0)+(tot.cnt_atr||0)+(tot.cnt_sad||0)+(tot.cnt_inas||0)+(tot.cnt_esp||0)) : ''}</td>`}
        ${showHE ? `
        <td style="position:sticky; z-index:60; border-left:3px solid #3b82f6;left:${getStickyLeftLocal('he', 0)}px;${getStickyWidthStyleLocal('he')}" class="tabular-nums text-warning sticky-premium-col">${tot.he_pend>0?_fmtMin(tot.he_pend):''}</td>
        <td class="tabular-nums text-success sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('he', 1)}px;${getStickyWidthStyleLocal('he')}">${tot.he_apr>0?_fmtMin(tot.he_apr):''}</td>
        <td class="tabular-nums text-danger sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('he', 2)}px;${getStickyWidthStyleLocal('he')}">${tot.he_rec>0?_fmtMin(tot.he_rec):''}</td>
        <td class="tabular-nums fw-bold sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('he', 3)}px;${getStickyWidthStyleLocal('he')}">${tot.he_bruto>0?_fmtMin(tot.he_bruto):''}</td>` : `<td style="position:sticky; z-index:60; border-left:3px solid #3b82f6; color:#3b82f6;left:${getStickyLeftLocal('he')}px;${getStickyWidthStyleLocal('he')}" class="tabular-nums fw-bold sticky-premium-col">${tot.he_bruto>0 ? '<i class="bi bi-lightning-charge-fill me-1"></i>' + _fmtMin(tot.he_bruto):''}</td>`}
        ${showDeudas ? `
        <td style="position:sticky; z-index:60; border-left:3px solid #64748b;left:${getStickyLeftLocal('deudas', 0)}px;${getStickyWidthStyleLocal('deudas')}" class="tabular-nums ${tot.min_col>0?'text-muted fw-bold':''} sticky-premium-col">${tot.min_col>0?_fmtMin(tot.min_col):''}</td>
        <td class="tabular-nums ${tot.min_per>0?'text-muted fw-bold':''} sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('deudas', 1)}px;${getStickyWidthStyleLocal('deudas')}">${tot.min_per>0?_fmtMin(tot.min_per):''}</td>
        <td class="tabular-nums ${tot.min_atr>0?'text-muted fw-bold':''} sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('deudas', 2)}px;${getStickyWidthStyleLocal('deudas')}">${tot.min_atr>0?_fmtMin(tot.min_atr):''}</td>
        <td class="tabular-nums ${tot.min_sad>0?'text-muted fw-bold':''} sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('deudas', 3)}px;${getStickyWidthStyleLocal('deudas')}">${tot.min_sad>0?_fmtMin(tot.min_sad):''}</td>
        <td class="tabular-nums text-muted fw-bold sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('deudas', 4)}px;${getStickyWidthStyleLocal('deudas')}">${tot.d_tot>0?_fmtMin(tot.d_tot):''}</td>` : `<td style="position:sticky; z-index:60; border-left:3px solid #64748b;left:${getStickyLeftLocal('deudas')}px;${getStickyWidthStyleLocal('deudas')}" class="tabular-nums text-muted fw-bold sticky-premium-col">${tot.d_tot>0 ? '<i class="bi bi-clock-history me-1"></i>' + _fmtMin(tot.d_tot):''}</td>`}
        <td class="tabular-nums ${totSClass} sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('saldo')}px;${getStickyWidthStyleLocal('saldo')}">${totSPrefix}${_fmtMin(Math.abs(tot.saldo))}</td>
        ${(hayBolsa) ? (
            showSaldoMeta
                ? `<td class="sticky-premium-col" style="position:sticky; z-index:60; background:#faf5ff;border-left:3px solid #8b5cf6;left:${getStickyLeftLocal('bolsa', 0)}px;${getStickyWidthStyleLocal('bolsa')}"></td>
                   <td class="sticky-premium-col" style="position:sticky; z-index:60; background:#faf5ff;left:${getStickyLeftLocal('bolsa', 1)}px;${getStickyWidthStyleLocal('bolsa')}"></td>
                   <td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; background:#faf5ff;left:${getStickyLeftLocal('bolsa', 2)}px;${getStickyWidthStyleLocal('bolsa')};text-align:center;font-size:0.7rem;color:#8b5cf6" title="Saldo individual — no aplica totalizar"><i class="bi bi-dash"></i></td>`
                : `<td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; background:#faf5ff;border-left:3px solid #8b5cf6;left:${getStickyLeftLocal('bolsa')}px;${getStickyWidthStyleLocal('bolsa')}"></td>`
        ) : ''}
        <td colspan="${dates.length}"></td>
    </tr>`;

    const tfoot = document.querySelector('.matrix-table-premium tfoot');
    if (tfoot) {
        tfoot.innerHTML = totalsRowHtml;
    }
};

window.reloadSingleEmployeeRow = async function(empId) {
    if (!stateMarcacionesApp.data || !stateMarcacionesApp.fechaInicioRRHH || !stateMarcacionesApp.fechaFinRRHH) {
        console.warn("reloadSingleEmployeeRow: stateMarcacionesApp.data or dates not ready, falling back to full reload");
        if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
        return;
    }

    const rowEl = document.getElementById("row-empleado-" + empId);
    if (!rowEl) {
        console.warn(`reloadSingleEmployeeRow: element row-empleado-${empId} not found, doing full client redraw`);
        const container = document.getElementById('marcaciones-view-container');
        if (container) renderVistaAnalitica(stateMarcacionesApp.data, container);
        return;
    }

    const nameCell = rowEl.querySelector('.emp-name-link');
    const originalNameHtml = nameCell ? nameCell.innerHTML : '';
    if (nameCell) {
        nameCell.innerHTML = `<span class="spinner-border spinner-border-sm text-primary me-1" role="status"></span>Actualizando...`;
    }

    try {
        let url = `/api/asistencia/matriz/?fecha_inicio=${stateMarcacionesApp.fechaInicioRRHH}&fecha_fin=${stateMarcacionesApp.fechaFinRRHH}&empleado_id=${empId}`;
        if (stateMarcacionesApp.area) url += `&area=${encodeURIComponent(stateMarcacionesApp.area)}`;
        if (stateMarcacionesApp.turnoId) url += `&turno_id=${stateMarcacionesApp.turnoId}`;

        const resp = await fetch(url);
        if (!resp.ok) throw new Error("Error loading single row data");

        const data = await resp.json();
        if (!data.matrix || !data.matrix[empId]) {
            throw new Error("No data returned for employee " + empId);
        }

        stateMarcacionesApp.data.matrix[empId] = data.matrix[empId];
        if (data.bonos_evaluacion && data.bonos_evaluacion[empId]) {
            stateMarcacionesApp.data.bonos_evaluacion[empId] = data.bonos_evaluacion[empId];
        }

        const dates = [];
        if (stateMarcacionesApp.data.periodo) {
            let curr = new Date(stateMarcacionesApp.data.periodo.inicio + 'T00:00:00');
            const end  = new Date(stateMarcacionesApp.data.periodo.fin   + 'T00:00:00');
            while (curr <= end) { dates.push(curr.toISOString().split('T')[0]); curr.setDate(curr.getDate()+1); }
        } else {
            const y = stateMarcacionesApp.year, m = stateMarcacionesApp.month;
            const daysInMonth = new Date(y, m, 0).getDate();
            for (let i = 1; i <= daysInMonth; i++)
                dates.push(`${y}-${String(m).padStart(2,'0')}-${String(i).padStart(2,'0')}`);
        }

        const feriadosArray = stateMarcacionesApp.data.feriados ? stateMarcacionesApp.data.feriados.map(f => f.fecha || f) : [];
        const getFeriadoDesc = (d) => {
            if (!stateMarcacionesApp.data.feriados) return null;
            const f = stateMarcacionesApp.data.feriados.find(x => (x.fecha || x) === d);
            return f ? (f.descripcion || 'Feriado') : null;
        };

        const empRaw = stateMarcacionesApp.data.empleados.find(e => String(e.id) === String(empId));
        if (!empRaw) {
            window.loadMarcacionesData();
            return;
        }

        const mEmp = data.matrix[empId];
        const info = mEmp.info || {};
        const empObject = {
            id: empId, info,
            nombre_completo: info.nombre_completo || empRaw.nombre_completo || empRaw.nombre,
            area: info.area || empRaw.area || '',
            turno: info.turno || info.nombre_turno || '',
            turno_dias: info.turno_dias || {},
            tipo_programacion: info.tipo_programacion || '',
            activo: info.activo !== false,
            dias: mEmp
        };

        const r = window.calcularStatsEmpleado(empObject, dates, feriadosArray);

        const s = window.vistaAnaliticaState;
        let matchesFilter = true;
        if (s.soloNegativo && !(r.saldo < 0)) matchesFilter = false;
        if (s.soloConHE && !(r.he_bruto > 0)) matchesFilter = false;

        if (!matchesFilter) {
            rowEl.style.display = "none";
        } else {
            rowEl.style.display = "";

            const hasBonos = (stateMarcacionesApp.data.bonos_nombres || []).length > 0;
            const showBonos = window.vistaAnaliticaState.showBonos;
            const bonosNombres = stateMarcacionesApp.data.bonos_nombres || [];
            const bonosEval = stateMarcacionesApp.data.bonos_evaluacion || {};
            const showIncidencias = window.vistaAnaliticaState.showIncidencias !== false;
            const showHE = window.vistaAnaliticaState.showHE !== false;
            const showDeudas = window.vistaAnaliticaState.showDeudas !== false;
            const hayBolsa = stateMarcacionesApp.data.empleados.some(e => {
                const matrixEmp = stateMarcacionesApp.data.matrix[e.id];
                return matrixEmp?.info?.tipo_programacion === 'FLEXIBLE_BOLSA';
            });
            const showSaldoMeta = hayBolsa && (window.vistaAnaliticaState.showSaldoMeta !== false);

            const stickyCols = {
                empleado: { width: 260 },
                bonos: { width: hasBonos ? (showBonos ? bonosNombres.length * 65 : 50) : 0 },
                incidencias: { width: showIncidencias ? 6 * 65 : 50 },
                he: { width: showHE ? 4 * 65 : 50 },
                deudas: { width: showDeudas ? 5 * 65 : 50 },
                saldo: { width: 70 }
            };
            if (hayBolsa) {
                stickyCols.bolsa = { width: showSaldoMeta ? 3 * 72 : 50 };
            }

            const newRowHtml = window.renderEmployeeRowHtml(r, dates, feriadosArray, getFeriadoDesc, hasBonos, showBonos, bonosNombres, bonosEval, showIncidencias, showHE, showDeudas, hayBolsa, showSaldoMeta, s, stickyCols);
            rowEl.outerHTML = newRowHtml;
        }

        window.recalculateTotalsRow(dates, feriadosArray, getFeriadoDesc);
        
        if (typeof showToast === 'function') {
            showToast("Fila actualizada en tiempo real", "success");
        }

    } catch (err) {
        console.error("reloadSingleEmployeeRow failed:", err);
        if (nameCell) nameCell.innerHTML = originalNameHtml;
        if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
    }
};

// ─── PUNTO DE ENTRADA (llamado desde marcaciones_ui.js) ──────────────────────
function renderVistaAnalitica(respData, container) {
    if (!respData) return;
    const { matrix, feriados } = respData;
    const dayNames = ["Dom","Lun","Mar","Mié","Jue","Vie","Sáb"];
    const hasMatrix = matrix && typeof matrix === 'object';
    if (!hasMatrix) {
        container.innerHTML = '<div class="alert alert-info">No hay datos para mostrar.</div>';
        return;
    }

    // ── 1. Organizar empleados (igual que renderTeamMatrix) ──────────────────
    const employees = [];
    if (respData.empleados) {
        respData.empleados.forEach(e_raw => {
            const eid = e_raw.id;
            const mEmp = matrix[eid];
            if (!mEmp) return;
            const info = mEmp.info || {};
            employees.push({
                id: eid, info,
                nombre_completo: info.nombre_completo || e_raw.nombre_completo || e_raw.nombre,
                area: info.area || e_raw.area || '',
                turno: info.turno || info.nombre_turno || '',          // backend envía info.turno
                turno_dias: info.turno_dias || {},                     // necesario para proyección LIBRE y tooltip
                tipo_programacion: info.tipo_programacion || '',
                activo: info.activo !== false,
                dias: mEmp
            });
        });
    }

    // ── 2. Rango de fechas ───────────────────────────────────────────────────
    const dates = [];
    if (respData.periodo) {
        let curr = new Date(respData.periodo.inicio + 'T00:00:00');
        const end  = new Date(respData.periodo.fin   + 'T00:00:00');
        while (curr <= end) { dates.push(curr.toISOString().split('T')[0]); curr.setDate(curr.getDate()+1); }
    } else {
        const y = stateMarcacionesApp.year, m = stateMarcacionesApp.month;
        const daysInMonth = new Date(y, m, 0).getDate();
        for (let i = 1; i <= daysInMonth; i++)
            dates.push(`${y}-${String(m).padStart(2,'0')}-${String(i).padStart(2,'0')}`);
    }

    const feriadosArray = feriados ? feriados.map(f => f.fecha || f) : [];
    const getFeriadoDesc = (d) => {
        if (!feriados) return null;
        const f = feriados.find(x => (x.fecha || x) === d);
        return f ? (f.descripcion || 'Feriado') : null;
    };

    // ── 3. Calcular resumen por empleado ─────────────────────────────────────
    const rows = employees.map(emp => window.calcularStatsEmpleado(emp, dates, feriadosArray));

    // ── 4. Aplicar filtros UI ────────────────────────────────────────────────
    const s = window.vistaAnaliticaState;
    let visibleRows = rows;
    if (s.soloNegativo) visibleRows = visibleRows.filter(r => r.saldo < 0);
    if (s.soloConHE)    visibleRows = visibleRows.filter(r => r.he_bruto > 0);

    // ── 5. Totales ───────────────────────────────────────────────────────────
    const showHE = s.showHE !== false;
    const showDeudas = s.showDeudas !== false;
    const showIncidencias = s.showIncidencias !== false;
    const bonosNombres = respData.bonos_nombres || [];
    const bonosEval = respData.bonos_evaluacion || {};
    const hasBonos = bonosNombres.length > 0;
    const showBonos = window.vistaAnaliticaState.showBonos;
    const hayBolsa = rows.some(r => r.esBolsa);
    const showSaldoMeta = hayBolsa && (window.vistaAnaliticaState.showSaldoMeta !== false);

    // Configuración de anchos dinámicos para columnas sticky
    const stickyCols = {
        empleado: { width: 260 },
        bonos: { 
            width: hasBonos 
                ? (showBonos ? bonosNombres.length * 65 : 50) 
                : 0 
        },
        incidencias: { 
            width: showIncidencias ? 6 * 65 : 50 
        },
        he: { 
            width: showHE ? 4 * 65 : 50 
        },
        deudas: { 
            width: showDeudas ? 5 * 65 : 50 
        },
        saldo: { width: 70 }
    };
    if (hayBolsa) {
        stickyCols.bolsa = {
            width: showSaldoMeta ? 3 * 72 : 50
        };
    }

    const getStickyLeft = (key, subIndex = 0) => {
        let offset = 0;
        const keys = ['empleado', 'bonos', 'incidencias', 'he', 'deudas', 'saldo', 'bolsa'];
        for (const k of keys) {
            if (k === key) {
                if (k === 'bonos' && showBonos) return offset + subIndex * 65;
                if (k === 'incidencias' && showIncidencias) return offset + subIndex * 65;
                if (k === 'he' && showHE) return offset + subIndex * 65;
                if (k === 'deudas' && showDeudas) return offset + subIndex * 65;
                if (k === 'bolsa' && showSaldoMeta) return offset + subIndex * 72;
                return offset;
            }
            if (stickyCols[k]) {
                offset += stickyCols[k].width;
            }
        }
        return offset;
    };

    const getStickyWidthStyle = (key) => {
        let w = 0;
        if (key === 'bonos') w = showBonos ? 65 : 50;
        else if (key === 'incidencias') w = showIncidencias ? 65 : 50;
        else if (key === 'he') w = showHE ? 65 : 50;
        else if (key === 'deudas') w = showDeudas ? 65 : 50;
        else if (key === 'saldo') w = 70;
        else if (key === 'bolsa') w = showSaldoMeta ? 72 : 50;
        return `width:${w}px; min-width:${w}px; max-width:${w}px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;`;
    };

    const tot = visibleRows.reduce((acc,r) => {
        acc.he_bruto+=r.he_bruto; acc.he_apr+=r.he_apr; acc.he_rec+=r.he_rec; acc.he_pend+=r.he_pend;
        acc.d_tot+=r.d_tot; acc.saldo+=r.saldo;
        acc.cnt_atr+=r.cnt_atr; acc.cnt_sad+=r.cnt_sad; acc.cnt_inas+=r.cnt_inas;
        acc.cnt_esp+=r.cnt_esp; acc.cnt_per+=r.cnt_per;
        acc.min_col+=(r.min_col||0); acc.min_per+=(r.min_per||0); 
        acc.min_atr+=(r.min_atr||0); acc.min_sad+=(r.min_sad||0);
        return acc;
    }, {he_bruto:0,he_apr:0,he_rec:0,he_pend:0,d_tot:0,saldo:0,cnt_atr:0,cnt_sad:0,cnt_inas:0,cnt_esp:0,cnt_per:0,min_col:0,min_per:0,min_atr:0,min_sad:0});

    let bonosHeadersTop = '';
    let bonosHeadersSub = '';
    if (hasBonos) {
        if (showBonos) {
            const bonosTopWidth = bonosNombres.length * 65;
            bonosHeadersTop = `<th colspan="${bonosNombres.length}" class="text-start px-2 th-bento th-bento-success sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('bonos')}px; width:${bonosTopWidth}px; min-width:${bonosTopWidth}px; max-width:${bonosTopWidth}px;"><i class="bi bi-trophy-fill me-1" style="font-size:0.75rem;color:#10b981"></i><span class="fw-bold">Bonos</span> <button class="btn btn-sm btn-link text-muted p-0 ms-1" onclick="vaToggleBonos()" title="Contraer"><i class="bi bi-chevron-left"></i></button></th>`;
            bonosHeadersSub = bonosNombres.map((b, idx) => {
                const bShort = b.length > 5 ? b.substring(0,4) + '.' : b;
                return `<th class="text-center px-1 align-middle th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; width:65px; min-width:65px; max-width:65px; left:${getStickyLeft('bonos', idx)}px" title="${b}">${bShort}</th>`;
            }).join('');
        } else {
            bonosHeadersTop = `<th rowspan="2" class="align-middle text-center px-1 th-bento th-bento-success sticky-premium-col" style="position:sticky; z-index:120; width:50px; min-width:50px; max-width:50px; left:${getStickyLeft('bonos')}px"><button class="btn btn-sm btn-link text-muted p-0 mb-1" onclick="vaToggleBonos()" title="Expandir Bonos"><i class="bi bi-chevron-right"></i></button><br><i class="bi bi-trophy-fill d-block mb-1" style="font-size:0.85rem;color:#10b981"></i><span style="font-size:0.65rem;letter-spacing:0.5px">BONOS</span></th>`;
        }
    }

    // ── 6. Cabeceras de días ─────────────────────────────────────────────────
    const monthNamesShort = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
    const dayHeaders = dates.map(d => {
        const dt = new Date(d+'T00:00:00');
        const isFer = feriadosArray.includes(d);
        const isWE  = (dt.getDay()===0||dt.getDay()===6);
        const bg = isFer ? 'background:#fff9c4' : isWE ? 'background:#f8f9fa' : '';
        const dateStrObj = dt.getDate().toString().padStart(2, '0') + '-' + monthNamesShort[dt.getMonth()];
        const dayShortName = dayNames[dt.getDay()].toUpperCase();
        // En modo Perdonazos: encabezado es clickeable para abrir panel lateral
        const perdonazoClick = `onclick="if(window._perdonazoState&&window._perdonazoState.activo){abrirPanelPerdonazoPorFecha('${d}')}"`;
        const perdonazoStyle = window._perdonazoState?.activo
            ? 'cursor:pointer;border-bottom:2px solid #10b981;'
            : '';
        return `<th class="col-day text-center p-1" style="min-width:48px;font-size:0.65rem;white-space:nowrap;${bg}${perdonazoStyle}" ${perdonazoClick}
                    title="${window._perdonazoState?.activo ? 'Clic para gestionar perdonazos del día' : ''}">
                    <div style="font-weight:700;font-size:0.7rem;line-height:1.1">${dateStrObj}</div>
                    <div style="opacity:0.8;font-size:0.6rem;line-height:1.1">${dayShortName}</div>
                    ${window._perdonazoState?.activo ? '<div style="font-size:0.55rem;color:#10b981;font-weight:600;">🎁</div>' : ''}
                </th>`;
    }).join('');


    // ── 7. Filas de empleados ────────────────────────────────────────────────
    const bodyRows = visibleRows.map(r => {
        return window.renderEmployeeRowHtml(r, dates, feriadosArray, getFeriadoDesc, hasBonos, showBonos, bonosNombres, bonosEval, showIncidencias, showHE, showDeudas, hayBolsa, showSaldoMeta, s, stickyCols);
    }).join('');

    // Fila totales
    const totSClass = tot.saldo > 0 ? 'text-success' : tot.saldo < 0 ? 'text-danger' : 'text-muted';
    const totSPrefix = tot.saldo > 0 ? '+' : tot.saldo < 0 ? '-' : '';
    
    let bonosTotalsCell = '';
    if (hasBonos) {
        if (showBonos) {
            bonosTotalsCell = bonosNombres.map((bName, idx) => {
                const borderStyle = idx === 0 ? 'border-left:3px solid #10b981' : 'border-left:1px solid #e2e8f0';
                return `<td class="sticky-premium-col" style="position:sticky; z-index:60; ${borderStyle};left:${getStickyLeft('bonos', idx)}px;${getStickyWidthStyle('bonos')}"></td>`;
            }).join('');
        } else {
            bonosTotalsCell = `<td class="sticky-premium-col" style="position:sticky; z-index:60; border-left:3px solid #10b981;left:${getStickyLeft('bonos')}px;${getStickyWidthStyle('bonos')}"></td>`;
        }
    }

    const totalsRow = `<tr class="fw-bold text-center" style="font-size:0.78rem; border-top: 2px solid #e2e8f0; background: #f8fafc;">
        <td class="sticky-col-analitica text-start ps-2" style="position:sticky; left:0; z-index:60; background: #f8fafc; color: #475569; font-weight: 800; width:260px; min-width:260px; max-width:260px;">TOTALES</td>
        ${bonosTotalsCell}
        ${showIncidencias ? `
        <td class="sticky-premium-col" style="position:sticky; z-index:60; border-left:3px solid #f59e0b;left:${getStickyLeft('incidencias', 0)}px;${getStickyWidthStyle('incidencias')}">${tot.cnt_per||''}</td>
        <td class="sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('incidencias', 1)}px;${getStickyWidthStyle('incidencias')}">${tot.cnt_atr||''}</td>
        <td class="sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('incidencias', 2)}px;${getStickyWidthStyle('incidencias')}">${tot.cnt_sad||''}</td>
        <td class="sticky-premium-col ${tot.cnt_inas>0?'text-danger':''}" style="position:sticky; z-index:60; left:${getStickyLeft('incidencias', 3)}px;${getStickyWidthStyle('incidencias')}">${tot.cnt_inas||''}</td>
        <td class="sticky-premium-col ${tot.cnt_esp>0?'text-info':''}" style="position:sticky; z-index:60; left:${getStickyLeft('incidencias', 4)}px;${getStickyWidthStyle('incidencias')}">${tot.cnt_esp||''}</td>
        <td class="fw-bold sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('incidencias', 5)}px;${getStickyWidthStyle('incidencias')}">${((tot.cnt_per||0)+(tot.cnt_atr||0)+(tot.cnt_sad||0)+(tot.cnt_inas||0)+(tot.cnt_esp||0))||''}</td>` : `<td style="position:sticky; z-index:60; border-left:3px solid #f59e0b; color:#f59e0b;left:${getStickyLeft('incidencias')}px;${getStickyWidthStyle('incidencias')}" class="fw-bold sticky-premium-col">${((tot.cnt_per||0)+(tot.cnt_atr||0)+(tot.cnt_sad||0)+(tot.cnt_inas||0)+(tot.cnt_esp||0))>0 ? '<i class="bi bi-flag-fill me-1"></i>' + ((tot.cnt_per||0)+(tot.cnt_atr||0)+(tot.cnt_sad||0)+(tot.cnt_inas||0)+(tot.cnt_esp||0)) : ''}</td>`}
        ${showHE ? `
        <td style="position:sticky; z-index:60; border-left:3px solid #3b82f6;left:${getStickyLeft('he', 0)}px;${getStickyWidthStyle('he')}" class="tabular-nums text-warning sticky-premium-col">${tot.he_pend>0?_fmtMin(tot.he_pend):''}</td>
        <td class="tabular-nums text-success sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('he', 1)}px;${getStickyWidthStyle('he')}">${tot.he_apr>0?_fmtMin(tot.he_apr):''}</td>
        <td class="tabular-nums text-danger sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('he', 2)}px;${getStickyWidthStyle('he')}">${tot.he_rec>0?_fmtMin(tot.he_rec):''}</td>
        <td class="tabular-nums fw-bold sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('he', 3)}px;${getStickyWidthStyle('he')}">${tot.he_bruto>0?_fmtMin(tot.he_bruto):''}</td>` : `<td style="position:sticky; z-index:60; border-left:3px solid #3b82f6; color:#3b82f6;left:${getStickyLeft('he')}px;${getStickyWidthStyle('he')}" class="tabular-nums fw-bold sticky-premium-col">${tot.he_bruto>0 ? '<i class="bi bi-lightning-charge-fill me-1"></i>' + _fmtMin(tot.he_bruto):''}</td>`}
        ${showDeudas ? `
        <td style="position:sticky; z-index:60; border-left:3px solid #64748b;left:${getStickyLeft('deudas', 0)}px;${getStickyWidthStyle('deudas')}" class="tabular-nums ${tot.min_col>0?'text-muted fw-bold':''} sticky-premium-col">${tot.min_col>0?_fmtMin(tot.min_col):''}</td>
        <td class="tabular-nums ${tot.min_per>0?'text-muted fw-bold':''} sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('deudas', 1)}px;${getStickyWidthStyle('deudas')}">${tot.min_per>0?_fmtMin(tot.min_per):''}</td>
        <td class="tabular-nums ${tot.min_atr>0?'text-muted fw-bold':''} sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('deudas', 2)}px;${getStickyWidthStyle('deudas')}">${tot.min_atr>0?_fmtMin(tot.min_atr):''}</td>
        <td class="tabular-nums ${tot.min_sad>0?'text-muted fw-bold':''} sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('deudas', 3)}px;${getStickyWidthStyle('deudas')}">${tot.min_sad>0?_fmtMin(tot.min_sad):''}</td>
        <td class="tabular-nums text-muted fw-bold sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('deudas', 4)}px;${getStickyWidthStyle('deudas')}">${tot.d_tot>0?_fmtMin(tot.d_tot):''}</td>` : `<td style="position:sticky; z-index:60; border-left:3px solid #64748b;left:${getStickyLeft('deudas')}px;${getStickyWidthStyle('deudas')}" class="tabular-nums text-muted fw-bold sticky-premium-col">${tot.d_tot>0 ? '<i class="bi bi-clock-history me-1"></i>' + _fmtMin(tot.d_tot):''}</td>`}
        <td class="tabular-nums ${totSClass} sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; left:${getStickyLeft('saldo')}px;${getStickyWidthStyle('saldo')}">${totSPrefix}${_fmtMin(Math.abs(tot.saldo))}</td>
        ${(hayBolsa) ? (
            showSaldoMeta
                ? `<td class="sticky-premium-col" style="position:sticky; z-index:60; background:#faf5ff;border-left:3px solid #8b5cf6;left:${getStickyLeft('bolsa', 0)}px;${getStickyWidthStyle('bolsa')}"></td>
                   <td class="sticky-premium-col" style="position:sticky; z-index:60; background:#faf5ff;left:${getStickyLeft('bolsa', 1)}px;${getStickyWidthStyle('bolsa')}"></td>
                   <td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; background:#faf5ff;left:${getStickyLeft('bolsa', 2)}px;${getStickyWidthStyle('bolsa')};text-align:center;font-size:0.7rem;color:#8b5cf6" title="Saldo individual — no aplica totalizar"><i class="bi bi-dash"></i></td>`
                : `<td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; background:#faf5ff;border-left:3px solid #8b5cf6;left:${getStickyLeft('bolsa')}px;${getStickyWidthStyle('bolsa')}"></td>`
        ) : ''}
        <td colspan="${dates.length}"></td>
    </tr>`;

    // ── 8. Switches ──────────────────────────────────────────────────────────
    const isClosed = respData.periodo && respData.periodo.cerrado;
    const closedBadge = isClosed ? `<span class="badge bg-danger ms-2" title="El periodo está cerrado y protegido contra modificaciones"><i class="bi bi-lock-fill"></i> CERRADO</span>` : '';

    const activeVM = stateMarcacionesApp.viewMode || 'conceptos';
    const vmButtons = [
        {key:'conceptos', icon:'bi-grid-3x3-gap',     label:'Conceptos'},
        {key:'horas',     icon:'bi-clock',            label:'Horas'},
        {key:'colacion',  icon:'bi-cup-hot',          label:'Colación'},
        {key:'permisos',  icon:'bi-person-dash',      label:'Permisos'},
        {key:'he',        icon:'bi-arrow-up-circle',  label:'Horas Extras'},
        {key:'acumulado', icon:'bi-graph-up',         label:'Acumulado'}
    ].map(v => `<button class="btn segmented-btn ${activeVM===v.key ? 'active' : ''}" onclick="vaSetViewMode('${v.key}')" title="${v.label}"><i class="bi ${v.icon} me-1 d-none d-sm-inline"></i>${v.label}</button>`).join('');

    const sw = `<div class="va-toolbar-premium">
        <div class="d-flex align-items-center gap-2">
            <i class="bi bi-grid-3x3-gap-fill" style="font-size:1.1rem;color:#6366f1"></i>
            <span class="fw-bold" style="font-size:0.88rem;color:#1e293b">Vista Analítica</span>
            ${closedBadge}
        </div>
        <div style="width:1px;height:24px;background:#cbd5e1"></div>
        <div class="segmented-control" role="group" aria-label="Modo de vista">${vmButtons}</div>
        <div class="ms-auto d-flex align-items-center gap-3">
            <div class="btn-group shadow-sm" style="border-radius:8px;overflow:hidden">
                <button class="btn btn-sm ${isClosed ? 'btn-secondary disabled' : 'btn-warning'} fw-bold" ${isClosed ? 'disabled' : ''} onclick="openCierrePeriodoModal()" title="${isClosed ? 'El periodo ya está cerrado' : 'Cerrar este periodo definitivamente'}">
                    <i class="bi bi-shield-lock-fill me-1"></i> Cerrar Periodo
                </button>
                <button class="btn btn-sm btn-outline-secondary bg-white" onclick="openHistorialCierresModal()" title="Ver historial de cierres">
                    <i class="bi bi-clock-history"></i>
                </button>
            </div>
            <div class="va-stats-chip">
                <i class="bi bi-people-fill"></i>
                <strong>${visibleRows.length}</strong> emp · <strong>${dates.length}</strong> días
            </div>
        </div>
    </div>`;

    // ── 9. HTML final ────────────────────────────────────────────────────────
    // (hayBolsa y showSaldoMeta ya están definidos arriba, antes de bodyRows)

    const incHeadersTop = showIncidencias 
        ? `<th colspan="6" class="text-start px-2 th-bento th-bento-warning sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias')}px; width:390px; min-width:390px; max-width:390px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><i class="bi bi-flag-fill me-1" style="font-size:0.75rem;color:#f59e0b"></i><span class="fw-bold">Incidencias</span> <button class="btn btn-sm btn-link text-muted p-0 ms-1" onclick="vaToggleCol('showIncidencias')" title="Contraer"><i class="bi bi-chevron-left"></i></button></th>` 
        : `<th rowspan="2" class="align-middle px-1 text-center th-bento th-bento-warning sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias')}px; width:50px; min-width:50px; max-width:50px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><button class="btn btn-sm btn-link text-muted p-0 mb-1" onclick="vaToggleCol('showIncidencias')" title="Expandir Incidencias"><i class="bi bi-chevron-right"></i></button><br><i class="bi bi-flag-fill d-block mb-1" style="font-size:0.85rem;color:#f59e0b"></i><span style="font-size:0.65rem;letter-spacing:0.5px">INCID</span></th>`;
    
    const heHeadersTop = showHE 
        ? `<th colspan="4" class="text-start px-2 th-bento th-bento-primary sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('he')}px; width:260px; min-width:260px; max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><i class="bi bi-lightning-charge-fill me-1" style="font-size:0.75rem;color:#3b82f6"></i><span class="fw-bold">Horas Extra</span> <button class="btn btn-sm btn-link text-muted p-0 ms-1" onclick="vaToggleCol('showHE')" title="Contraer"><i class="bi bi-chevron-left"></i></button></th>` 
        : `<th rowspan="2" class="align-middle px-1 text-center th-bento th-bento-primary sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('he')}px; width:50px; min-width:50px; max-width:50px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><button class="btn btn-sm btn-link text-muted p-0 mb-1" onclick="vaToggleCol('showHE')" title="Expandir HE"><i class="bi bi-chevron-right"></i></button><br><i class="bi bi-lightning-charge-fill d-block mb-1" style="font-size:0.85rem;color:#3b82f6"></i><span style="font-size:0.65rem;letter-spacing:0.5px">HR EX</span></th>`;
    
    const deudasHeadersTop = showDeudas 
        ? `<th colspan="5" class="text-start px-2 th-bento th-bento-secondary sticky-premium-col" style="position:sticky; z-index:120; border-left:3px solid #64748b;left:${getStickyLeft('deudas')}px; width:325px; min-width:325px; max-width:325px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><i class="bi bi-clock-history me-1" style="font-size:0.75rem;color:#64748b"></i><span class="fw-bold">Tiempo No Trabajado</span> <button class="btn btn-sm btn-link text-muted p-0 ms-1" onclick="vaToggleCol('showDeudas')" title="Contraer"><i class="bi bi-chevron-left"></i></button></th>` 
        : `<th rowspan="2" class="align-middle px-1 text-center th-bento th-bento-secondary sticky-premium-col" style="position:sticky; z-index:120; border-left:3px solid #64748b;left:${getStickyLeft('deudas')}px; width:50px; min-width:50px; max-width:50px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><button class="btn btn-sm btn-link text-muted p-0 mb-1" onclick="vaToggleCol('showDeudas')" title="Expandir Tiempos"><i class="bi bi-chevron-right"></i></button><br><i class="bi bi-clock-history d-block mb-1" style="font-size:0.85rem;color:#64748b"></i><span style="font-size:0.65rem;letter-spacing:0.5px">NO TRAB</span></th>`;

    // Columna SALDO META — solo visible si hay bolsa flexible en el área
    const saldoMetaHeaderTop = hayBolsa
        ? (showSaldoMeta
            ? `<th colspan="3" class="text-start px-2 sticky-premium-col" style="position:sticky; z-index:120; background:#faf5ff;border-left:3px solid #8b5cf6;font-size:0.68rem;left:${getStickyLeft('bolsa')}px; width:216px; min-width:216px; max-width:216px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><i class="bi bi-bullseye me-1" style="color:#8b5cf6"></i><span class="fw-bold" style="color:#7c3aed">Bolsa Flexible</span> <button class="btn btn-sm btn-link p-0 ms-1" onclick="vaToggleCol('showSaldoMeta')" title="Contraer" style="color:#8b5cf6"><i class="bi bi-chevron-left"></i></button></th>`
            : `<th rowspan="2" class="align-middle px-1 text-center sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:120; background:#faf5ff;border-left:3px solid #8b5cf6;left:${getStickyLeft('bolsa')}px; width:50px; min-width:50px; max-width:50px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><button class="btn btn-sm btn-link p-0 mb-1" onclick="vaToggleCol('showSaldoMeta')" title="Expandir Bolsa Flexible" style="color:#8b5cf6"><i class="bi bi-chevron-right"></i></button><br><i class="bi bi-bullseye d-block mb-1" style="font-size:0.85rem;color:#8b5cf6"></i><span style="font-size:0.65rem;letter-spacing:0.5px;color:#7c3aed">BOLSA</span></th>`)
        : '';
    const saldoMetaHeadersSub = (hayBolsa && showSaldoMeta) ? `
            <th class="text-center px-1 sticky-premium-col" style="position:sticky; z-index:120; background:#faf5ff;border-left:3px solid #8b5cf6;font-size:0.65rem;color:#7c3aed;left:${getStickyLeft('bolsa', 0)}px;${getStickyWidthStyle('bolsa')}" title="Meta mensual del ciclo">META</th>
            <th class="text-center px-1 sticky-premium-col" style="position:sticky; z-index:120; background:#faf5ff;font-size:0.65rem;color:#7c3aed;left:${getStickyLeft('bolsa', 1)}px;${getStickyWidthStyle('bolsa')}" title="Horas acumuladas en el ciclo">ACUM.</th>
            <th class="text-center px-1 sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:120; background:#faf5ff;font-size:0.65rem;color:#7c3aed;left:${getStickyLeft('bolsa', 2)}px;${getStickyWidthStyle('bolsa')}" title="Balance: negativo = falta, positivo = excedió">BALANCE</th>` : '';

    const incHeadersSub = showIncidencias ? `
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias', 0)}px;${getStickyWidthStyle('incidencias')}" title="Días con permiso">PERM</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias', 1)}px;${getStickyWidthStyle('incidencias')}" title="Días con atraso">ATR</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias', 2)}px;${getStickyWidthStyle('incidencias')}" title="Días con salida adelantada">S.ADL</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias', 3)}px;${getStickyWidthStyle('incidencias')}" title="Inasistencias">INA</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias', 4)}px;${getStickyWidthStyle('incidencias')}" title="Jornadas especiales">J.ESP</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias', 5)}px;${getStickyWidthStyle('incidencias')}" title="Total incidencias">TOT</th>` : '';
    const heHeadersSub = showHE ? `
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('he', 0)}px;${getStickyWidthStyle('he')}" title="HE pendientes por revisar">PEND</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('he', 1)}px;${getStickyWidthStyle('he')}" title="HE aprobadas por jefe">APR ✅</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('he', 2)}px;${getStickyWidthStyle('he')}" title="HE rechazadas">RECH ❌</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('he', 3)}px;${getStickyWidthStyle('he')}" title="Total HE brutas calculadas">TOT</th>` : '';
    const deudasHeadersSub = showDeudas ? `
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('deudas', 0)}px;${getStickyWidthStyle('deudas')}" title="Exceso colación (disponible tras nuevo motor)">COL</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('deudas', 1)}px;${getStickyWidthStyle('deudas')}" title="Permisos biométricos sin validar">PER</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('deudas', 2)}px;${getStickyWidthStyle('deudas')}" title="Minutos de atraso">ATR</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('deudas', 3)}px;${getStickyWidthStyle('deudas')}" title="Minutos salida adelantada">S.ADL</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('deudas', 4)}px;${getStickyWidthStyle('deudas')}" title="Total deuda acumulada">TOT</th>` : '';

    container.innerHTML = `
    ${sw}
    <div style="overflow:auto;max-height:calc(100vh - 260px);border-radius:0 0 8px 8px;border:1px solid #dee2e6;border-top:none">
    <table class="table table-bordered table-sm mb-0 matrix-table matrix-table-premium" style="font-size:0.8rem;border-collapse:separate;border-spacing:0">
    <thead style="position:sticky;top:0;z-index:100;box-shadow:0 4px 12px rgba(0,0,0,.05)">
        <tr class="text-center" style="background:#f8f9fa;font-size:0.68rem">
            <th rowspan="2" class="sticky-col-analitica align-middle text-start ps-2" style="position:sticky; left:0; z-index:120; white-space:nowrap; background:#f8f9fa; width:260px; min-width:260px; max-width:260px;">Empleado</th>
            ${bonosHeadersTop}
            ${incHeadersTop}
            ${heHeadersTop}
            ${deudasHeadersTop}
            <th rowspan="2" class="align-middle text-start px-2 sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:120; background:#f0fdf4;left:${getStickyLeft('saldo')}px;${getStickyWidthStyle('saldo')}">Saldo<br>Neto</th>
            ${saldoMetaHeaderTop}
            <th colspan="${dates.length}" class="text-start px-2" style="background:#f0f7ff">Días del período</th>
        </tr>
        <tr class="text-center" style="background:#f8f9fa;font-size:0.7rem">
            ${bonosHeadersSub}
            ${incHeadersSub}
            ${heHeadersSub}
            ${deudasHeadersSub}
            ${saldoMetaHeadersSub}
            ${dayHeaders}
        </tr>
    </thead>
    <tbody id="matrix-tbody">${bodyRows}</tbody>
    <tfoot>${totalsRow}</tfoot>
    </table>
    </div>
    <div class="va-legend-bar d-flex gap-3 flex-wrap align-items-center" style="font-size:0.72rem;color:#6b7280">
        <span class="badge-status badge-state-success"><i class="bi bi-check-circle-fill me-1"></i>OK</span> Normal
        <span class="badge-status badge-state-warning"><i class="bi bi-clock-fill me-1"></i>ATR</span> Atraso
        <span class="badge-status badge-state-info"><i class="bi bi-box-arrow-left me-1"></i>SAD</span> Sal.Adelantada
        <span class="badge-status badge-state-danger"><i class="bi bi-x-circle-fill me-1"></i>INA</span> Inasistencia
        <span class="badge-status badge-state-neutral"><i class="bi bi-cup-hot-fill me-1"></i>LIB</span> Libre (Auto)
        <span class="badge-status badge-state-warning"><i class="bi bi-calendar-heart-fill me-1"></i>FER</span> Feriado
        <span class="badge-status badge-state-warning"><i class="bi bi-exclamation-triangle-fill me-1"></i>PER</span> Permiso
        <span class="ms-auto text-muted" style="font-size:0.68rem"><i class="bi bi-info-circle me-1"></i>Click: Acciones · DblClick celda: Justificar · DblClick nombre: Gestionar HE</span>
    </div>`;

    // ── TOOLTIP VOLANTE (reemplaza Bootstrap Popover) ─────────────────────────
    // Un solo div en el body, pointer-events:none para no interceptar eventos del mouse.
    // Event delegation sobre la tabla: mouseover muestra, mouseout oculta.
    // Garantia: imposible que quede pegado porque nunca hay instancias huerfanas.
    setTimeout(() => {
        // Limpiar tooltip anterior si existe (por re-render)
        let flyTip = document.getElementById('grid-fly-tooltip');
        if (!flyTip) {
            flyTip = document.createElement('div');
            flyTip.id = 'grid-fly-tooltip';
            flyTip.style.cssText = [
                'position:fixed',
                'z-index:9999',
                'display:none',
                'pointer-events:none',
                'max-width:440px',
                'min-width:280px',
                'border-radius:10px',
                'box-shadow:0 8px 32px rgba(0,0,0,0.18)',
                'background:rgba(255,255,255,0.97)',
                'border:1px solid #e2e8f0',
                'padding:0',
                'overflow:hidden',
                'backdrop-filter:blur(8px)',
                'transition:opacity 0.08s ease'
            ].join(';');
            document.body.appendChild(flyTip);
        }

        function _positionFlyTip(e) {
            const PAD = 14;
            const tipW = flyTip.offsetWidth  || 340;
            const tipH = flyTip.offsetHeight || 200;
            let x = e.clientX + PAD;
            let y = e.clientY + PAD;
            if (x + tipW > window.innerWidth  - 8) x = e.clientX - tipW - PAD;
            if (y + tipH > window.innerHeight - 8) y = e.clientY - tipH - PAD;
            flyTip.style.left = Math.max(4, x) + 'px';
            flyTip.style.top  = Math.max(4, y) + 'px';
        }

        function _showFlyTip(td, e) {
            const html = td.getAttribute('data-bs-content');
            if (!html) return;
            flyTip.innerHTML = `<div class="popover-body p-0">${html}</div>`;
            flyTip.style.display = 'block';
            flyTip.style.opacity = '1';
            _positionFlyTip(e);
        }

        function _hideFlyTip() {
            flyTip.style.display = 'none';
        }

        const tableEl = container.querySelector('table.matrix-table');
        if (tableEl) {
            // Eliminar listeners previos clonando el nodo (evita duplicados en re-render)
            const newTable = tableEl; // ya es nuevo por innerHTML

            newTable.addEventListener('mouseover', (e) => {
                const td = e.target.closest('td[data-grid-tooltip]');
                if (!td) { _hideFlyTip(); return; }
                _showFlyTip(td, e);
            });

            newTable.addEventListener('mousemove', (e) => {
                if (flyTip.style.display !== 'none') _positionFlyTip(e);
            });

            newTable.addEventListener('mouseout', (e) => {
                const td = e.target.closest('td[data-grid-tooltip]');
                if (!td) return;
                // Solo ocultar si el mouse sale hacia algo que no es otra celda con tooltip
                const to = e.relatedTarget ? e.relatedTarget.closest('td[data-grid-tooltip]') : null;
                if (!to) _hideFlyTip();
            });

            newTable.addEventListener('mouseleave', _hideFlyTip);
        }

        // Seguridad extra: al hacer scroll en el contenedor ocultar el tooltip
        const tableScroller = container.querySelector('[style*="overflow:auto"]');
        if (tableScroller && !tableScroller._flyTipFixed) {
            tableScroller._flyTipFixed = true;
            tableScroller.addEventListener('scroll', _hideFlyTip, { passive: true });
        }

        // Seguridad extra: click en cualquier lado lo cierra
        document.addEventListener('click', _hideFlyTip, { passive: true, once: false });

    }, 100);
}

// ─── HELPERS INTERNOS ────────────────────────────────────────────────────────
function _fmtMin(min) {
    if (!min || min === 0) return '—';
    if (Math.round(Math.abs(min) * 60) <= 0) return '';
    return formatExactMinutesToTime(Math.abs(min));
}

// ─── CACHÉ DE ESTADOS (cargada desde API) ────────────────────────────────────
// Se carga una vez al iniciar la app. El frontend la usa para badges y tooltips.
window._estadosAsistencia = {}; // { codigo: { nombre_display, color_clase, icono_bi, descripcion } }

window._loadEstadosAsistencia = async function() {
    try {
        const resp = await fetch('/api/configuracion/estados/?solo_activos=true');
        if (!resp.ok) return;
        const lista = await resp.json();
        window._estadosAsistencia = {};
        lista.forEach(e => { window._estadosAsistencia[e.codigo] = e; });
        console.log(`[Estados] ${lista.length} estados cargados desde BD.`);
    } catch(err) {
        console.warn('[Estados] Error cargando estados, usando defaults:', err);
    }
};

// Helpers para obtener datos de estado (con fallback hardcodeado)
function _getEstadoColor(codigo) {
    return (window._estadosAsistencia[codigo] || {}).color_clase || _fallbackEstadoColor(codigo);
}
function _getEstadoIcon(codigo) {
    const ic = (window._estadosAsistencia[codigo] || {}).icono_bi;
    return ic ? `<i class="bi ${ic} me-1"></i>` : '';
}
function _getEstadoNombre(codigo) {
    return (window._estadosAsistencia[codigo] || {}).nombre_display || codigo;
}
function _fallbackEstadoColor(codigo) {
    const m = { OK:'badge-state-success', INASISTENCIA:'badge-state-danger', ATRASO:'badge-state-warning',
                SALIDA_ADELANTADA:'badge-state-info', LIBRE:'badge-state-neutral', FERIADO:'badge-state-warning',
                EXTRA:'badge-state-info', JORNADA_ESPECIAL:'badge-state-info', EN_CURSO:'badge-state-success',
                ANOMALIA:'bg-dark text-white', PERMISO:'badge-state-info' };
    return m[codigo] || 'badge-state-neutral';
}

function _analiticaCellBadge(di) {
    if (!di || !di.estado) return '';
    let est = di.estado;

    // Distinguir entre Compensado por Horas Extras y Compensado por Intercambio (1x1)
    if (est === 'INASISTENCIA_COMPENSADA') {
        if (di.deuda_condonada === 3) {
            est = 'INASISTENCIA_COMPENSADA_INTERCAMBIO';
        } else {
            est = 'INASISTENCIA_COMPENSADA_HE';
        }
    }

    // --- Lógica Bolsa Flexible: Suprimir estados de penalización de tiempo ---
    if (di._esBolsa) {
        if (['ATRASO', 'SALIDA_ADELANTADA', 'ATR_SAD'].includes(est)) {
            est = 'OK'; // Visualmente es un día trabajado normal
        }
        // Suprimir flags secundarios para que no rendericen badges apilados
        di.tiene_atraso = false;
        di.tiene_salida_adelantada = false;
    }

    // Construir badgeMap desde caché de BD (si está disponible) + fallback hardcodeado
    const estadosCache = window._estadosAsistencia || {};
    const badgeMap = {};
    // Primero cargamos los estados desde la caché de BD
    Object.values(estadosCache).forEach(e => {
        const icon = e.icono_bi ? `<i class="bi ${e.icono_bi} me-1"></i>` : '';
        // Para badges cortos usamos short_label o fallback
        const shortLabel = e.short_label || (e.codigo === 'JORNADA_ESPECIAL' ? 'ESP' : (e.codigo.length <= 3 ? e.codigo : e.codigo.substring(0,3)));
        badgeMap[e.codigo] = [e.color_clase, icon + (e._badgeLabel || shortLabel)];
    });

    // Inyectar mappings virtuales para los dos tipos de inasistencia compensada
    badgeMap['INASISTENCIA_COMPENSADA_INTERCAMBIO'] = [
        'badge-compensatorio', 
        '<i class="bi bi-arrow-left-right me-1"></i>COMP'
    ];
    badgeMap['INASISTENCIA_COMPENSADA_HE'] = [
        'badge-inasistencia-compensada-he', 
        '<i class="bi bi-clock-history me-1"></i>C.HE'
    ];

    // Fallback hardcodeado (si la caché aún no cargó)
    if (Object.keys(badgeMap).length === 0) {
        Object.assign(badgeMap, {
            'OK':               ['badge-state-success', '<i class="bi bi-check-circle-fill me-1"></i>OK'],
            'ATRASO':           ['badge-state-warning',  '<i class="bi bi-clock-fill me-1"></i>ATR'],
            'SALIDA_ADELANTADA':['badge-state-info',     '<i class="bi bi-box-arrow-left me-1"></i>SAD'],
            'INASISTENCIA':     ['badge-state-danger',   '<i class="bi bi-x-circle-fill me-1"></i>INA'],
            'LIBRE':            ['badge-state-neutral',  '<i class="bi bi-cup-hot-fill me-1"></i>LIB'],
            'FERIADO':          ['badge-state-warning',  '<i class="bi bi-calendar-heart-fill me-1"></i>FER'],
            'PERMISO':          ['badge-state-info',     '<i class="bi bi-person-check-fill me-1"></i>PER'],
            'EXTRA':            ['badge-state-info',     '<i class="bi bi-plus-circle-fill me-1"></i>EXT'],
            'ANOMALIA':         ['bg-dark text-white',   '<i class="bi bi-exclamation-triangle-fill me-1"></i>ANO'],
            'JORNADA_ESPECIAL': ['badge-state-info',     '<i class="bi bi-star-fill me-1"></i>ESP'],
            'EN_CURSO':         ['badge-state-success',  '<i class="bi bi-play-circle-fill me-1"></i>CUR'],
            'INASISTENCIA_COMPENSADA_INTERCAMBIO': ['badge-compensatorio', '<i class="bi bi-arrow-left-right me-1"></i>COMP'],
            'INASISTENCIA_COMPENSADA_HE':          ['badge-inasistencia-compensada-he', '<i class="bi bi-clock-history me-1"></i>C.HE'],
            'JORNADA_COMPENSATORIA':   ['badge-compensatorio',           '<i class="bi bi-arrow-left-right me-1"></i>COMP']
        });
    }

    const stdBadgeStyle = "width:52px; min-height:22px; display:inline-flex; align-items:center; justify-content:center; flex-direction:column; line-height:1.1;";

    // ── Badge del estado PRIMARIO ─────────────────────────────────────────────
    let pillClass = 'badge-state-neutral';
    let label = (estadosCache[est] && estadosCache[est].short_label) || (est === 'JORNADA_ESPECIAL' ? 'ESP' : (est.length <= 3 ? est : est.substring(0,3)));
    let tooltipTitle = '';

    if (badgeMap[est]) {
        [pillClass, label] = badgeMap[est];
        if (est === 'LIBRE') tooltipTitle = 'Día Libre (Asignación automática)';
        else if (est === 'FERIADO') tooltipTitle = 'Feriado legal / Irrenunciable';
        else if (est === 'INASISTENCIA') tooltipTitle = 'Inasistencia (Generada automáticamente)';
        else if (est === 'INASISTENCIA_COMPENSADA_INTERCAMBIO') tooltipTitle = 'Día Compensado por Intercambio (1x1)';
        else if (est === 'INASISTENCIA_COMPENSADA_HE') tooltipTitle = 'Compensado con Horas Extras';
    } else if (di.nomenclatura) {
        pillClass = 'badge-state-info';
        label = di.nomenclatura;
    }
    
    if (!tooltipTitle && estadosCache[est] && estadosCache[est].descripcion) {
        tooltipTitle = estadosCache[est].descripcion;
    }

    let primaryBadge = '';
    if (di.jornada_adicional) {
        const ja = di.jornada_adicional;
        if ((di.horas_teoricas || 0) === 0 || est === 'LIBRE') {
            let class_esp = _getEstadoColor('JORNADA_ESPECIAL') || 'badge-state-info';
            let label_esp = (estadosCache['JORNADA_ESPECIAL'] || {}).short_label || 'ESP';
            let icon_esp = '<i class="bi bi-star-fill me-1"></i>';
            let title_esp = 'Jornada Adicional Pendiente de Aprobación';
            
            if (ja.estado === 'EXTRA') {
                class_esp = _getEstadoColor('EXTRA') || 'badge-state-info';
                label_esp = (estadosCache['EXTRA'] || {}).short_label || 'EXT';
                title_esp = 'Jornada Adicional Aprobada como Extra';
            } else if (ja.estado === 'RECHAZADA') {
                class_esp = 'badge-state-danger';
                label_esp = 'REC';
                title_esp = 'Jornada Adicional Rechazada';
            }

            primaryBadge = `<div class="badge-status ${class_esp}" style="${stdBadgeStyle}" title="${title_esp}"><span>${icon_esp}${label_esp}</span></div>`;
        } else {
            const class_izq = pillClass;
            const label_izq = label;
            
            let class_der = 'badge-state-neutral';
            let label_der = 'ESP';
            let title_der = 'Jornada Especial Adicional';
            
            if (ja.estado === 'PENDIENTE') {
                class_der = _getEstadoColor('JORNADA_ESPECIAL') || 'badge-state-info';
                label_der = (estadosCache['JORNADA_ESPECIAL'] || {}).short_label || 'ESP';
                title_der = 'Jornada Adicional Pendiente de Aprobación';
            } else if (ja.estado === 'EXTRA') {
                class_der = _getEstadoColor('EXTRA') || 'badge-state-info';
                label_der = (estadosCache['EXTRA'] || {}).short_label || 'EXT';
                title_der = 'Jornada Adicional Aprobada como Extra';
            } else if (ja.estado === 'RECHAZADA') {
                class_der = 'badge-state-danger';
                label_der = 'REC';
                title_der = 'Jornada Adicional Rechazada';
            }
            
            primaryBadge = `
            <div class="d-flex w-100 h-100" style="min-width: 52px; min-height: 22px; border-radius: 4px; overflow: hidden; border: 1px solid rgba(0,0,0,0.08); background-color: #fff;">
                <div class="badge-status ${class_izq}" style="flex: 1; border-radius: 0; min-height: 22px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.62rem; font-weight: 700; line-height: 1.1; padding: 2px;" ${tooltipTitle ? `title="${tooltipTitle}"` : ''}>
                    <span>${label_izq}</span>
                </div>
                <div style="width: 1px; background-color: rgba(0,0,0,0.12); align-self: stretch;"></div>
                <div class="badge-status ${class_der}" style="flex: 1; border-radius: 0; min-height: 22px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.62rem; font-weight: 700; line-height: 1.1; padding: 2px;" title="${title_der}">
                    <span>${label_der}</span>
                </div>
            </div>`;
        }
    } else {
        primaryBadge = `<div class="badge-status ${pillClass}" style="${stdBadgeStyle}" ${tooltipTitle ? `title="${tooltipTitle}"` : ''}><span>${label}</span></div>`;
    }

    // ── Badges secundarios según flags independientes ─────────────────────────
    // Solo se muestran si el flag es verdadero Y el estado primario no lo representa ya
    const extraBadges = [];

    if ((di.tiene_atraso || di.alerta_atraso) && est !== 'ATRASO') {
        const [ac, al] = badgeMap['ATRASO'] || ['badge-state-warning', '<i class="bi bi-clock-fill me-1"></i>ATR'];
        extraBadges.push(`<div class="badge-status ${ac}" style="${stdBadgeStyle}"><span>${al}</span></div>`);
    }
    if (di.tiene_salida_adelantada && est !== 'SALIDA_ADELANTADA') {
        const [sc, sl] = badgeMap['SALIDA_ADELANTADA'] || ['badge-state-info', '<i class="bi bi-box-arrow-left me-1"></i>SAD'];
        extraBadges.push(`<div class="badge-status ${sc}" style="${stdBadgeStyle}"><span>${sl}</span></div>`);
    }
    if (di.tiene_permiso && est !== 'PERMISO') {
        const [pc, pl] = badgeMap['PERMISO'] || ['badge-state-info', '<i class="bi bi-calendar-check-fill me-1"></i>PER'];
        extraBadges.push(`<div class="badge-status ${pc}" style="${stdBadgeStyle}"><span>${pl}</span></div>`);
    }

    // Si hay badges adicionales → contenedor columna; si no → badge simple
    let resultHtml = '';
    if (extraBadges.length > 0) {
        resultHtml = `<div class="d-flex flex-column align-items-center justify-content-center gap-1" style="line-height:1.2; padding:2px 0;">
            ${primaryBadge}
            ${extraBadges.join('\n')}
        </div>`;
    } else {
        resultHtml = primaryBadge;
    }

    const tieneEmergencia = di.observaciones && di.observaciones.includes('[Llamado de Emergencia:');
    const tieneAlertaSistema = di.observaciones && di.observaciones.includes('[ALERTA SISTEMA');
    const tieneHE_Pendientes = di.minutos_extra_bruto > 0 && di.estado_he === 'PENDIENTE';

    if (tieneEmergencia || tieneAlertaSistema || tieneHE_Pendientes) {
        let wrapperHtml = `<div style="position:relative; display:inline-block; width:100%;">
            ${resultHtml}`;
        if (tieneEmergencia) {
            wrapperHtml += `<div title="Llamado de Emergencia (Aprobado Directo)" style="position:absolute; top:-6px; left:-6px; font-size:0.75rem; color:#8b5cf6; z-index:10; filter:drop-shadow(0 0 2px rgba(139,92,246,0.5));"><i class="bi bi-lightning-charge-fill"></i></div>`;
        }
        if (tieneAlertaSistema) {
            wrapperHtml += `<div title="Alerta de Sistema (Ver Tooltip)" style="position:absolute; top:-4px; right:-2px; width:12px; height:12px; background-color:#ef4444; border-radius:50%; box-shadow:0 0 6px #ef4444; border:2px solid white; z-index:10;"></div>`;
        }
        if (tieneHE_Pendientes) {
            const rightOffset = tieneAlertaSistema ? '10px' : '-2px';
            wrapperHtml += `<div title="Horas Extras Pendientes (${_fmtMin(di.minutos_extra_bruto)})" style="position:absolute; top:-4px; right:${rightOffset}; width:12px; height:12px; background-color:#f97316; border-radius:50%; box-shadow:0 0 6px #f97316; border:2px solid white; z-index:10;"></div>`;
        }
        wrapperHtml += `</div>`;
        return wrapperHtml;
    }
    return resultHtml;
}

// ─── TOGGLE DE FILTROS UI (sin llamada al backend) ───────────────────────────
function vaToggleFilter(key, value) {
    window.vistaAnaliticaState[key] = value;
    if (stateMarcacionesApp.data) {
        const container = document.getElementById('marcaciones-view-container');
        renderVistaAnalitica(stateMarcacionesApp.data, container);
    }
}

window.vaToggleBonos = function() {
    window.vistaAnaliticaState.showBonos = !window.vistaAnaliticaState.showBonos;
    if (stateMarcacionesApp.data) {
        const container = document.getElementById('marcaciones-view-container');
        renderVistaAnalitica(stateMarcacionesApp.data, container);
    }
}

window.vaToggleCol = function(key) {
    window.vistaAnaliticaState[key] = !window.vistaAnaliticaState[key];
    if (stateMarcacionesApp.data) {
        const container = document.getElementById('marcaciones-view-container');
        renderVistaAnalitica(stateMarcacionesApp.data, container);
    }
}

// ─── SETTER DE VIEWMODE (6 switches de la grilla) ────────────────────────────────
window.vaSetViewMode = function(mode) {
    stateMarcacionesApp.viewMode = mode;
    if (stateMarcacionesApp.data) {
        const container = document.getElementById('marcaciones-view-container');
        renderVistaAnalitica(stateMarcacionesApp.data, container);
    }
}

// ─── CONTENIDO DE CELDA SEGÚN VIEWMODE ──────────────────────────────────────
function _analiticaCellContent(di, dateStr, emp, viewMode, isFer = false) {
    // Proyección visual de LIBRE o FERIADO para fechas sin datos o guardadas sin marcas
    const est = di ? di.estado : null;
    let esFeriadoPuro = isFer || est === 'FERIADO';
    let esLibrePuro = est === 'LIBRE';

    if (!di || !di.estado) {
        if (emp && emp.turno_dias && dateStr) {
            const dt2 = new Date(dateStr + 'T00:00:00');
            const pyDay = dt2.getDay() === 0 ? 6 : dt2.getDay() - 1;
            const dayInfo = emp.turno_dias[pyDay];
            if (dayInfo && dayInfo.es_libre) {
                esLibrePuro = true;
            }
        }
    }

    if (esFeriadoPuro && (!est || est === 'FERIADO')) {
        return `<div class="badge-status badge-state-warning" style="width:52px; min-height:22px; display:inline-flex; align-items:center; justify-content:center; opacity:0.65;"><span><i class="bi bi-calendar-heart-fill me-1"></i>FER</span></div>`;
    }
    if (esLibrePuro && (!est || est === 'LIBRE')) {
        return `<div class="badge-status badge-state-neutral" style="width:52px; min-height:22px; display:inline-flex; align-items:center; justify-content:center; opacity:0.55;"><span><i class="bi bi-cup-hot-fill me-1"></i>LIB</span></div>`;
    }

    if (!di || !di.estado) {
        return '';
    }
    
    const hasEff = ['OK','ATRASO','SALIDA_ADELANTADA','ATR_SAD','EXTRA','EN_CURSO'].includes(est);

    let resultHtml = '';

    if (viewMode === 'horas' && hasEff) {
        const hrs = est === 'EN_CURSO' ? '>>' : formatDecimalToTime(di.horas_trabajadas);
        const mDeuda = di.minutos_deuda || 0;
        
        let html = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1.2;">`;
        html += `<span class="fw-bold tabular-nums" style="font-size:0.72rem">${hrs}</span>`;
        if (di.tipo_programacion !== 'FLEXIBLE_BOLSA' && mDeuda > 0) {
            html += `<span style="font-size:0.55rem;color:#dc2626;font-weight:700;letter-spacing:-0.2px;margin-top:2px;">DEUDA ${_fmtMin(mDeuda)}</span>`;
        }
        html += `</div>`;
        resultHtml = html;
    }
    else if (viewMode === 'he') {
        // En modo HE: nunca caer al badge de conceptos → return explícito
        if (di._esBolsa) {
            const snapHoy      = di._acumuladoBolsaSnap || 0;
            const snapAyer     = di._acumuladoBolsaSnapPrev || 0;
            const metaMinBolsa = di._metaMinBolsa || 0;
            const trabHoy      = Math.round((di.horas_trabajadas || 0) * 60);
            if (snapHoy > metaMinBolsa && trabHoy > 0) {
                const heEste = snapAyer >= metaMinBolsa ? trabHoy : (snapHoy - metaMinBolsa);
                if (heEste > 0) {
                    const col = di.estado_he === 'APROBADO' ? 'color:#16a34a' : 'color:#f97316';
                    return `<span class="fw-bold tabular-nums" style="font-size:0.72rem;${col}">${_fmtMin(heEste)}</span>`;
                }
            }
            return ''; // Sin HE: celda vacía (no badge)
        } else {
            const heBruto = di.minutos_extra_bruto || 0;
            if (heBruto > 0) {
                const col = di.estado_he === 'APROBADO' ? 'color:#16a34a' : 'color:#dc2626';
                return `<span class="fw-bold tabular-nums" style="font-size:0.72rem;${col}">${_fmtMin(heBruto)}</span>`;
            }
            return ''; // Sin HE: celda vacía (no badge)
        }
    }
    else if (viewMode === 'acumulado') {
        if (di._esBolsa) {
            // FLEXIBLE_BOLSA: SOLO mostrar en días efectivos (no LIBRE/FERIADO)
            if (!hasEff) return ''; // LIBRE / FERIADO → celda vacía
            const snap         = di._acumuladoBolsaSnap || 0;
            const snapAyer     = di._acumuladoBolsaSnapPrev || 0;
            const metaMinBolsa = di._metaMinBolsa || 1;
            if (snap > 0) {
                let color, bg = '';
                if (snapAyer >= metaMinBolsa) {
                    color = '#f97316'; bg = 'background:rgba(249,115,22,0.08)';
                } else if (snap > metaMinBolsa) {
                    color = '#10b981'; bg = 'background:rgba(16,185,129,0.12)';
                } else if (snap / metaMinBolsa >= 0.8) {
                    color = '#d97706';
                } else {
                    color = '#3b82f6';
                }
                const cruzaHoy = snap > metaMinBolsa && snapAyer < metaMinBolsa;
                return `<div style="display:flex;flex-direction:column;align-items:center;line-height:1.2;${bg}">
                    <span class="fw-bold tabular-nums" style="font-size:0.72rem;color:${color}">${_fmtMin(snap)}</span>
                    ${cruzaHoy ? `<span style="font-size:0.5rem;color:#10b981;font-weight:800">&#9733;META</span>` : ''}
                </div>`;
            }
            return '';
        } else if (hasEff && di.horas_trabajadas > 0) {
            // Turnos normales: acumulado semanal
            const snap = di._acumuladoSemanalSnap || 0;
            return snap > 0
                ? `<span class="fw-bold tabular-nums" style="font-size:0.72rem">${_fmtMin(snap)}</span>`
                : `<span style="font-size:0.68rem;color:#9ca3af">—</span>`;
        }
        return ''; // cualquier otro caso → vacío
    }
    else if (viewMode === 'colacion' && hasEff) {
        const mColReal = di.minutos_colacion_real || 0;
        const mColAplicado = di.minutos_colacion || 0;
        const exceso = di.minutos_exceso_colacion || 0;
        
        if (di.hora_entrada_real && di.hora_salida_real) {
            let color = mColAplicado > 0 ? '#1e293b' : '#9ca3af';
            let html = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1.2;">`;
            html += `<span class="fw-bold tabular-nums" style="font-size:0.72rem;color:${color}">${_fmtMin(mColAplicado)}</span>`;
            
            if (exceso > 0) {
                html += `<span style="font-size:0.55rem;color:#dc2626;font-weight:700;letter-spacing:-0.2px;margin-top:2px;">DEUDA ${_fmtMin(exceso)}</span>`;
            } else if (mColReal === 0 && mColAplicado > 0) {
                html += `<span style="font-size:0.55rem;color:#64748b;font-weight:700;letter-spacing:-0.2px;margin-top:2px;">AUTO</span>`;
            }
            html += `</div>`;
            resultHtml = html;
        } else {
            resultHtml = `<span style="font-size:0.68rem;color:#9ca3af">—</span>`;
        }
    }
    else if (viewMode === 'permisos') {
        const mPerm = di.minutos_permisos_detectados || 0;
        const mDeuda = di.minutos_permiso_personal_deuda || 0;
        if (mPerm > 0) return `<span class="fw-bold tabular-nums" style="font-size:0.72rem;color:#2563eb">${_fmtMin(mPerm)}</span>`;
        if (di.tiene_permiso_hora || di.permiso_activo) {
            const mins = mDeuda > 0 ? mDeuda : Math.round((di.horas_teoricas||0)*60);
            if (mins > 0) return `<span class="fw-bold tabular-nums" style="font-size:0.72rem;color:#d97706">${_fmtMin(mins)}</span>`;
            return `<span style="font-size:0.68rem;color:#d97706">PER</span>`;
        }
        return hasEff ? `<span style="font-size:0.68rem;color:#9ca3af">—</span>` : '';
    }

    if (resultHtml !== '') {
        if (est === 'EXTRA') {
            const label = 'EXTRA';
            const color = '#8b5cf6';
            return `<div style="display:flex;flex-direction:column;align-items:center;line-height:1.2;">
                ${resultHtml}
                <span style="font-size:0.55rem;color:${color};font-weight:700;letter-spacing:-0.2px;margin-top:2px;">${label}</span>
            </div>`;
        }
        return resultHtml;
    }

    // default: conceptos
    return _analiticaCellBadge(di);
}

// ─── TOOLTIP DASHBOARD PREMIUM (LIGHT THEME) ────────────────────
function _buildRichTooltipData(di, dateStr, dt, feriadoDesc, isWE, empInfo) {
    const days = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
    const months = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
    const dayName = dt ? days[dt.getDay()] : '';
    let dateFormatted = dateStr;
    if (dt) {
        const dayNum = dt.getDate();
        const monthName = months[dt.getMonth()];
        const year = dt.getFullYear();
        dateFormatted = dayName ? `${dayName} ${dayNum} de ${monthName}, ${year}` : dateStr;
    }
    const empName = empInfo ? (empInfo.nombre_completo || empInfo.nombre || 'Empleado') : 'Empleado';
    const empAreaText = empInfo && empInfo.area ? empInfo.area : 'SIN ÁREA';
    const isFer = !!feriadoDesc;

    if (!di || !di.estado) {
        const fallbackShift = (empInfo && empInfo.turno) ? empInfo.turno : 'SIN PROGRAMACIÓN';
        let scheduleHtml = '';
        if (dt && empInfo && empInfo.turno_dias) {
            const pyDay = dt.getDay() === 0 ? 6 : dt.getDay() - 1;
            const dayInfo = empInfo.turno_dias[pyDay];
            if (dayInfo) {
                if (dayInfo.es_libre) {
                    scheduleHtml = `<div style="color:var(--text-secondary, #64748b); font-weight:500; font-size:0.65rem; text-transform: uppercase; margin-top:2px;"><i class="bi bi-cup-hot-fill me-1"></i> HORARIO: <span style="color:var(--text-primary, #1e293b);">DÍA LIBRE</span></div>`;
                } else if (dayInfo.hora_entrada && dayInfo.hora_salida) {
                    const hEnt = dayInfo.hora_entrada.substring(0, 5);
                    const hSal = dayInfo.hora_salida.substring(0, 5);
                    scheduleHtml = `<div style="color:var(--text-secondary, #64748b); font-weight:500; font-size:0.65rem; text-transform: uppercase; margin-top:2px;"><i class="bi bi-clock-history me-1"></i> HORARIO: <span style="color:var(--text-primary, #1e293b);">${hEnt} - ${hSal}</span></div>`;
                }
            }
        }
        let emptyStateHtml = isFer ? `<div class="badge-status badge-state-warning" style="display:inline-flex; align-items:center; padding: 4px 10px; font-size:0.65rem; font-weight:700; border-radius: 6px; box-shadow:none; white-space:nowrap; text-transform:uppercase;"><i class="bi bi-star-fill me-1"></i>FERIADO</div>` : `<div class="badge-status badge-state-secondary" style="display:inline-flex; align-items:center; padding: 4px 10px; font-size:0.65rem; font-weight:700; border-radius: 6px; box-shadow:none; white-space:nowrap; text-transform:uppercase;">SIN DATOS</div>`;
        
        return _escAttr(`<div style="width: 340px; font-family:'Inter',sans-serif; cursor: default; background:var(--card-bg, #ffffff); color:var(--text-primary, #1e293b); padding:12px; border-radius:6px; margin:0; border:1px solid var(--border-color, #e2e8f0); box-shadow:var(--shadow-premium);">
            <div style="border-bottom: 1px solid var(--border-color, #e2e8f0); padding-bottom: 12px; margin-bottom: 12px;">
                <div style="color: var(--text-secondary, #64748b); font-weight: 700; font-size: 0.65rem; letter-spacing: 0.5px; text-transform: uppercase; margin-bottom: 4px;">
                    <i class="bi bi-clock me-1" style="font-size:0.8rem"></i> REGISTRO DE ASISTENCIA
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div style="color: var(--primary-color, #6366f1); font-weight: 700; font-size: 0.85rem;">
                        ${dateFormatted}
                    </div>
                    <div>
                        ${emptyStateHtml}
                    </div>
                </div>
                <div style="color:var(--text-primary, #1e293b); font-weight:700; font-size:0.9rem; margin-bottom:4px; line-height:1.2;">${empName}</div>
                <div style="color:var(--text-secondary, #64748b); font-weight:500; font-size:0.65rem; margin-bottom:2px; text-transform: uppercase;">ÁREA: <span style="color:var(--text-primary, #1e293b);">${empAreaText}</span></div>
                <div style="color:var(--text-secondary, #64748b); font-weight:500; font-size:0.65rem; text-transform: uppercase; margin-bottom:2px;">TURNO: <span style="color:var(--text-primary, #1e293b);">${fallbackShift}</span></div>
                <div style="color:var(--text-secondary, #64748b); font-weight:500; font-size:0.65rem; text-transform: uppercase; margin-bottom:2px;">CICLO: <span style="color:var(--text-primary, #1e293b);">--</span></div>
                ${scheduleHtml}
                ${isFer ? `<div style="margin-top: 6px; padding: 6px 8px; background-color: rgba(245, 158, 11, 0.1); border-left: 3px solid var(--warning-color, #f59e0b); border-radius: 4px; color: var(--warning-color, #f59e0b); font-size: 0.75rem; font-weight: 600; text-align: left;"><i class="bi bi-star-fill me-1"></i> ${feriadoDesc}</div>` : ''}
            </div>
        </div>`);
    }

    const e = di;
    const est = e.estado;
    
    // Icon mappings
    const iconMap = {
        'OK': '<i class="bi bi-check-circle-fill me-1"></i>',
        'INASISTENCIA': '<i class="bi bi-x-circle-fill me-1"></i>',
        'PERMISO': '<i class="bi bi-calendar-check-fill me-1"></i>',
        'ATRASO': '<i class="bi bi-clock-fill me-1"></i>',
        'SALIDA_ADELANTADA': '<i class="bi bi-box-arrow-left me-1"></i>',
        'LIBRE': '<i class="bi bi-cup-hot-fill me-1"></i>',
        'EN_CURSO': '<i class="bi bi-play-circle-fill me-1"></i>',
        'FERIADO': '<i class="bi bi-star-fill me-1"></i>',
        'JORNADA_ESPECIAL': '<i class="bi bi-star-fill me-1"></i>',
        'EXTRA': '<i class="bi bi-plus-circle-fill me-1"></i>',
        'ANOMALIA': '<i class="bi bi-exclamation-triangle-fill me-1"></i>',
        'PENDIENTE': '<i class="bi bi-exclamation-triangle-fill me-1"></i>'
    };
    
    const stateNameMap = {};
    Object.values(window._estadosAsistencia || {}).forEach(e => {
        stateNameMap[e.codigo] = e.nombre_display || e.codigo;
    });
    if (!stateNameMap['OK']) {
        Object.assign(stateNameMap, {
            'OK': 'OK', 'INASISTENCIA': 'INASISTENCIA',
            'SALIDA_ADELANTADA': 'SALIDA ADELANTADA', 'EN_CURSO': 'EN TURNO',
            'JORNADA_ESPECIAL': 'JORNADA ESPECIAL', 'EXTRA': 'JORNADA EXTRA',
            'ANOMALIA': 'ANOMALÍA (INCOMPLETA)'
        });
    }
    stateNameMap['PENDIENTE'] = 'ANOMALÍA (JE INCOMPLETA)';
    
    const pillClassMap = {
        'OK': 'badge-state-success',
        'INASISTENCIA': 'badge-state-danger',
        'PERMISO': 'badge-state-info',
        'ATRASO': 'badge-state-warning',
        'SALIDA_ADELANTADA': 'badge-state-info',
        'LIBRE': 'badge-state-secondary',
        'EN_CURSO': 'badge-state-success',
        'FERIADO': 'badge-state-warning',
        'JORNADA_ESPECIAL': 'badge-state-info',
        'EXTRA': 'badge-state-info',
        'ANOMALIA': 'bg-dark text-white border-0',
        'PENDIENTE': 'bg-dark text-white border-0'
    };

    let badgeHtml = '';
    const perSuffix = (e.tiene_permiso_hora || e.permiso_activo) ? ' <span style="opacity:0.8;font-size:0.9em;margin-left:4px;">(+PERM)</span>' : '';
    
    if (est === 'ATR_SAD') {
        const b1 = `<div class="badge-status badge-state-warning" style="display:inline-flex; align-items:center; padding: 4px 10px; font-size:0.65rem; font-weight:700; border-radius: 6px; box-shadow:none; white-space:nowrap; text-transform:uppercase;"><i class="bi bi-clock-fill me-1"></i>ATRASO</div>`;
        const b2 = `<div class="badge-status badge-state-info" style="display:inline-flex; align-items:center; padding: 4px 10px; font-size:0.65rem; font-weight:700; border-radius: 6px; box-shadow:none; white-space:nowrap; text-transform:uppercase;"><i class="bi bi-box-arrow-left me-1"></i>SAL. ADEL. ${perSuffix}</div>`;
        badgeHtml = `<div style="display:flex; flex-direction:column; align-items:flex-end; gap: 4px;">${b1}${b2}</div>`;
    } else {
        const fullName = stateNameMap[est] || (e.nomenclatura || est);
        const pillClass = pillClassMap[est] || 'badge-state-info';
        const icon = iconMap[est] || '';
        badgeHtml = `<div class="badge-status ${pillClass}" style="display:inline-flex; align-items:center; padding: 4px 10px; font-size:0.65rem; font-weight:700; border-radius: 6px; box-shadow:none; white-space:nowrap; text-transform:uppercase;">${icon}${fullName}${perSuffix}</div>`;
    }
    
    // Formatters
    const _fM = (m) => {
        if (!m || m <= 0) return '';
        return formatExactMinutesToTime(m);
    };

    // Calculate Extra Hours distribution
    let heBruta = e.minutos_extra_bruto || 0;
    let heAprobada = e.minutos_extra_autorizados || 0;
    let heRechazada = e.estado_he === 'RECHAZADO' ? heBruta : 0;
    let hePendiente = e.estado_he === 'PENDIENTE' ? heBruta : 0;
    let heTotal = heAprobada; 

    // Incidencias Array
    let incidencias = [];
    if (e.minutos_atraso > 0) incidencias.push(`Atraso de ${formatExactMinutesToTime(e.minutos_atraso)} en entrada`);
    else if (e.alerta_atraso) incidencias.push(`Alerta de atraso en entrada (tolerancia superada)`);
    
    if (e.minutos_salida_adelantada > 0) incidencias.push(`Salida anticipada por ${formatExactMinutesToTime(e.minutos_salida_adelantada)}`);
    if (e.minutos_deuda > 0 && e.minutos_atraso === 0 && e.minutos_salida_adelantada === 0) incidencias.push(`Deuda total de ${formatExactMinutesToTime(e.minutos_deuda)}`);
    if (e.tiene_permiso || e.tiene_permiso_hora || e.permiso_activo || e.minutos_permisos_detectados > 0) {
        const hIni  = e.hora_inicio_permiso  ? String(e.hora_inicio_permiso).substring(0,5)  : null;
        const hFin  = e.hora_termino_permiso ? String(e.hora_termino_permiso).substring(0,5) : null;
        const durMin = e.minutos_permisos_detectados || e.minutos_permiso_personal_deuda || 0;
        let permisoTxt = 'Permiso detectado';
        if (hIni && hFin) {
            permisoTxt = `Permiso ${hIni} – ${hFin}`;
            if (durMin > 0) permisoTxt += ` (${formatExactMinutesToTime(durMin)})`;
        } else if (hIni) {
            permisoTxt = `Permiso desde ${hIni}`;
            if (durMin > 0) permisoTxt += ` (${formatExactMinutesToTime(durMin)})`;
        } else if (durMin > 0) {
            permisoTxt = `Permiso de ${formatExactMinutesToTime(durMin)}`;
        }
        incidencias.push(permisoTxt);
    }
    
    if (e._esDiaJustificadoBolsa && empInfo && empInfo._esBolsaFlag && empInfo._valorTurnoMinBolsa) {
        incidencias.push(`Día justificado (Art 25 bis): descuenta ${formatExactMinutesToTime(empInfo._valorTurnoMinBolsa)} a la meta mensual.`);
    }

    let incidenciasHtml = '';
    if (incidencias.length > 0) {
        incidenciasHtml = `
        <div style="background-color: rgba(245,158,11,0.1); border: 1px solid var(--warning-color, #f59e0b); border-radius: 6px; padding: 8px; margin-bottom: 12px;">
            <div style="color: var(--warning-color, #f59e0b); font-weight: 700; font-size: 0.65rem; letter-spacing: 0.5px; margin-bottom: 4px;">
                <i class="bi bi-exclamation-triangle-fill me-1"></i> INCIDENCIAS
            </div>
            <ul style="margin: 0; padding-left: 16px; color: var(--text-primary, #1e293b); font-size: 0.7rem; line-height: 1.4;">
                ${incidencias.map(i => `<li>${i}</li>`).join('')}
            </ul>
        </div>`;
    }

    // Colors
    const isUnderHours = e.horas_trabajadas && e.horas_teoricas && e.horas_trabajadas < e.horas_teoricas;
    const hoursColor = isUnderHours ? 'var(--danger-color, #f43f5e)' : 'var(--text-primary, #1e293b)';
    
    const rowStyles = "display:flex; justify-content:space-between; margin-bottom:4px; align-items:center;";
    const labelStyles = "color:var(--text-secondary, #64748b); font-weight:500; font-size:0.7rem;";
    
    const valMins = (mins, activeColor) => {
        if (!mins || mins <= 0) return `<span style="color:var(--text-secondary, #64748b); font-family:'monospace'; font-size:0.75rem;"></span>`;
        return `<span style="color:${activeColor}; font-family:'monospace'; font-size:0.75rem; font-weight:700;">${formatExactMinutesToTime(mins)}</span>`;
    };

    // Colación Logic
    const colAuto = e.minutos_colacion_auto || 0;
    const colApli = e.minutos_colacion || 0;

    let colRealText = '';
    if (e.minutos_colacion_real > 0) {
        colRealText = `<span style="font-size:0.55rem; color:var(--text-secondary, #64748b); font-family:'Inter',sans-serif; font-weight:normal;">(Marcas)</span>`;
    } else if (colApli > 0) {
        colRealText = `<span style="font-size:0.55rem; color:var(--text-secondary, #64748b); font-family:'Inter',sans-serif; font-weight:normal;">(Auto)</span>`;
    }

    const shiftName = e.turno_nombre || (empInfo && empInfo.turno) || 'SIN PROGRAMACIÓN';
    const cycleName = e.etiqueta_bloque || '--';

    let heBreakdownHtml = '';
    if (heBruta > 0) {
        let txtArr = [];
        if (!e.horas_teoricas || isFer || e.estado === 'LIBRE' || e.estado === 'JORNADA_ESPECIAL') {
            txtArr.push(`<div style="display:flex; justify-content:space-between;"><span style="color:var(--text-secondary,#64748b);">Día Inhábil/Libre:</span> <span style="font-family:monospace;font-weight:700;">${valMins(heBruta, 'var(--success-color, #10b981)')}</span></div>`);
        } else {
            const timeToMins = (t) => {
                if(!t) return 0;
                let p = t.split(':');
                return parseInt(p[0],10)*60 + parseInt(p[1],10);
            };
            let hr_ent = e.hora_entrada_real;
            let ht_ent = e.hora_entrada_teorica;
            const esAncladoEntrada = e.observaciones && e.observaciones.includes("dentro del anclaje");
            if (hr_ent && ht_ent && !esAncladoEntrada) {
                let diff = timeToMins(ht_ent) - timeToMins(hr_ent);
                if (diff > 720) diff -= 1440;
                if (diff < -720) diff += 1440;
                if (diff > 0) {
                    txtArr.push(`<div style="display:flex; justify-content:space-between;"><span style="color:var(--text-secondary,#64748b);">Ingreso Anticipado:</span> <span style="font-family:monospace;font-weight:700;">${valMins(diff, 'var(--success-color, #10b981)')}</span></div>`);
                }
            }
            let hr_sal = e.hora_salida_real;
            let ht_sal = e.hora_salida_teorica;
            const esAncladoSalida = e.observaciones && e.observaciones.includes("Salida dentro del anclaje");
            if (hr_sal && ht_sal && !esAncladoSalida) {
                let diff = timeToMins(hr_sal) - timeToMins(ht_sal);
                if (diff > 720) diff -= 1440;
                if (diff < -720) diff += 1440;
                if (diff > 0) {
                    txtArr.push(`<div style="display:flex; justify-content:space-between;"><span style="color:var(--text-secondary,#64748b);">Salida Posterior:</span> <span style="font-family:monospace;font-weight:700;">${valMins(diff, 'var(--success-color, #10b981)')}</span></div>`);
                }
            }
            if (txtArr.length === 0) {
                txtArr.push(`<div style="display:flex; justify-content:space-between;"><span style="color:var(--text-secondary,#64748b);">Ajuste/Excedente:</span> <span style="font-family:monospace;font-weight:700;">${valMins(heBruta, 'var(--success-color, #10b981)')}</span></div>`);
            }
        }
        
        if (txtArr.length > 0) {
            heBreakdownHtml = `
            <div style="margin-top:8px; padding-top:6px; border-top:1px dashed rgba(16, 185, 129, 0.3);">
                <div style="font-size:0.6rem; color:var(--text-secondary,#64748b); font-weight:700; margin-bottom:4px;">ORIGEN APROXIMADO HE:</div>
                <div style="font-size:0.7rem; display:flex; flex-direction:column; gap:2px;">
                    ${txtArr.join('')}
                </div>
            </div>`;
        }
    }

    // Calculate presence time (Permanencia)
    const rawTimeToMins = (t) => {
        if (!t) return 0;
        const p = t.split(':');
        const h = parseInt(p[0] || '0', 10);
        const m = parseInt(p[1] || '0', 10);
        const s = parseInt(p[2] || '0', 10);
        return h * 60 + m + s / 60;
    };

    let permProgMins = 0;
    if (e.hora_entrada_teorica && e.hora_salida_teorica) {
        let diff = rawTimeToMins(e.hora_salida_teorica) - rawTimeToMins(e.hora_entrada_teorica);
        if (diff < 0) diff += 1440;
        permProgMins = diff;
    }

    let permRealMins = 0;
    if (e.hora_entrada_real && e.hora_salida_real) {
        let diff = rawTimeToMins(e.hora_salida_real) - rawTimeToMins(e.hora_entrada_real);
        if (diff < 0) diff += 1440;
        permRealMins = diff;
    }

    // Build Horas Extras Card (only if bruto or approved/autorizados exist)
    let heCardHtml = '';
    if (heBruta > 0 || heAprobada > 0) {
        let heRows = '';
        if (heBruta > 0) heRows += `<div style="${rowStyles} border-bottom: 1px dashed rgba(16, 185, 129, 0.2); padding-bottom: 2px;"><span style="${labelStyles}">Bruta</span> ${valMins(heBruta, 'var(--success-color, #10b981)')}</div>`;
        if (heAprobada > 0) heRows += `<div style="${rowStyles} border-bottom: 1px dashed rgba(16, 185, 129, 0.2); padding-bottom: 2px;"><span style="${labelStyles}">Autorizada</span> ${valMins(heAprobada, 'var(--success-color, #10b981)')}</div>`;
        heRows += `<div style="${rowStyles} padding-top: 2px;"><span style="${labelStyles} font-weight:700; color:var(--text-primary, #1e293b);">Total</span> ${valMins(heTotal, 'var(--success-color, #10b981)')}</div>`;

        heCardHtml = `
        <div style="flex: 1; border: 1px solid rgba(16, 185, 129, 0.2); background-color: rgba(16, 185, 129, 0.05); border-radius: 6px; padding: 8px;">
            <div style="color: var(--success-color, #10b981); font-weight: 700; font-size: 0.65rem; letter-spacing: 0.5px; margin-bottom: 8px;">
                <i class="bi bi-circle-fill me-1" style="font-size: 0.4rem; vertical-align: middle;"></i> ${(est === 'EXTRA' || est === 'JORNADA_ESPECIAL') ? (stateNameMap[est] || 'HORAS EXTRAS') : 'HORAS EXTRAS'}
            </div>
            ${heRows}
            ${heBreakdownHtml}
        </div>`;
    }

    // Build Deuda Card (only if minutes_deuda > 0)
    let deudaCardHtml = '';
    if (!(e.deuda_condonada > 0 || !e.minutos_deuda || e.minutos_deuda <= 0)) {
        let deudaRows = '';
        if (e.minutos_atraso > 0) {
            deudaRows += `<div style="${rowStyles} border-bottom: 1px dashed rgba(244, 63, 94, 0.2); padding-bottom: 2px;"><span style="${labelStyles}">Atraso</span> ${valMins(e.minutos_atraso, 'var(--danger-color, #f43f5e)')}</div>`;
        }
        if (e.minutos_salida_adelantada > 0) {
            deudaRows += `<div style="${rowStyles} border-bottom: 1px dashed rgba(244, 63, 94, 0.2); padding-bottom: 2px;"><span style="${labelStyles}">Sal. Antic.</span> ${valMins(e.minutos_salida_adelantada, 'var(--danger-color, #f43f5e)')}</div>`;
        }
        if (e.minutos_exceso_colacion > 0) {
            deudaRows += `<div style="${rowStyles} border-bottom: 1px dashed rgba(244, 63, 94, 0.2); padding-bottom: 2px;"><span style="${labelStyles}">Colación</span> ${valMins(e.minutos_exceso_colacion, 'var(--danger-color, #f43f5e)')}</div>`;
        }
        if (e.minutos_permisos_detectados > 0) {
            deudaRows += `<div style="${rowStyles} border-bottom: 1px dashed rgba(244, 63, 94, 0.2); padding-bottom: 2px;"><span style="${labelStyles}">Permisos</span> ${valMins(e.minutos_permisos_detectados, 'var(--danger-color, #f43f5e)')}</div>`;
        }
        deudaRows += `<div style="${rowStyles} padding-top: 2px;"><span style="${labelStyles} font-weight:700; color:var(--text-primary, #1e293b);">Total Comp.</span> ${valMins(e.minutos_deuda, 'var(--danger-color, #f43f5e)')}</div>`;

        deudaCardHtml = `
        <div style="flex: 1; border: 1px solid rgba(244, 63, 94, 0.2); background-color: rgba(244, 63, 94, 0.05); border-radius: 6px; padding: 8px;">
            <div style="color: var(--danger-color, #f43f5e); font-weight: 700; font-size: 0.65rem; letter-spacing: 0.5px; margin-bottom: 8px;">
                <i class="bi bi-circle-fill me-1" style="font-size: 0.4rem; vertical-align: middle;"></i> DEUDA
            </div>
            ${deudaRows}
        </div>`;
    }

    let cardsHtml = '';
    if (heCardHtml || deudaCardHtml) {
        cardsHtml = `
        <div style="display: flex; gap: 10px;">
            ${heCardHtml}
            ${deudaCardHtml}
        </div>`;
    }

    // ── Bloque de Jornada Adicional o Llamados de Emergencia en Tooltip ──
    let bloquesAdicionalesHtml = '';
    
    // 1. Mostrar Jornada Especial Adicional si está inyectada en el registro
    if (e.jornada_adicional) {
        const ja = e.jornada_adicional;
        let estadoLabel = ja.estado;
        let estadoColor = '#64748b'; // gris
        let iconHtml = '<i class="bi bi-clock me-1"></i>';
        
        if (ja.estado === 'PENDIENTE') {
            estadoLabel = 'PENDIENTE DE APROBACIÓN';
            estadoColor = '#0284c7'; // celeste / azul
            iconHtml = '<i class="bi bi-hourglass-split me-1"></i>';
        } else if (ja.estado === 'EXTRA') {
            estadoLabel = 'APROBADA COMO EXTRA';
            estadoColor = '#16a34a'; // verde
            iconHtml = '<i class="bi bi-check-circle-fill me-1"></i>';
        } else if (ja.estado === 'RECHAZADA') {
            estadoLabel = 'RECHAZADA';
            estadoColor = '#dc2626'; // rojo
            iconHtml = '<i class="bi bi-x-circle-fill me-1"></i>';
        }
        
        const hEntJa = ja.hora_entrada ? ja.hora_entrada.substring(0, 5) : '--:--';
        const hSalJa = ja.hora_salida ? ja.hora_salida.substring(0, 5) : '--:--';
        const duracionJa = ja.minutos_trabajados ? formatExactMinutesToTime(ja.minutos_trabajados) : '--:--';
        
        bloquesAdicionalesHtml += `
        <div style="border: 1px solid ${estadoColor}33; background-color: ${estadoColor}08; border-radius: 6px; padding: 8px; margin-bottom: 12px; text-align: left;">
            <div style="color: ${estadoColor}; font-weight: 700; font-size: 0.65rem; letter-spacing: 0.5px; text-transform: uppercase; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;">
                <span><i class="bi bi-calendar-plus me-1"></i> JORNADA ADICIONAL</span>
                <span style="font-size: 0.58rem; background-color: ${estadoColor}1a; padding: 1px 6px; border-radius: 4px; border: 1px solid ${estadoColor}33; display: inline-flex; align-items: center; text-transform: uppercase;">${iconHtml}${estadoLabel}</span>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 0.7rem; color: var(--text-primary, #1e293b); font-family: monospace;">
                <div>Entrada: <span style="font-weight:700;">${hEntJa}</span></div>
                <div>Salida: <span style="font-weight:700;">${hSalJa}</span></div>
                <div>Duración: <span style="font-weight:700; color: ${estadoColor};">${duracionJa}</span></div>
            </div>
        </div>`;
    }
    
    // 2. Mostrar Llamado de Emergencia Corto si existe en observaciones
    if (e.observaciones && e.observaciones.includes('[Llamado de Emergencia:')) {
        const regex = /\[Llamado de Emergencia:\s*([^\]]+)\]/g;
        let match;
        while ((match = regex.exec(e.observaciones)) !== null) {
            const contenido = match[1]; // ej: "38 min de 03:38 a 04:16"
            bloquesAdicionalesHtml += `
            <div style="border: 1px solid rgba(139, 92, 246, 0.3); background-color: rgba(139, 92, 246, 0.06); border-radius: 6px; padding: 8px; margin-bottom: 12px; text-align: left;">
                <div style="color: #7c3aed; font-weight: 700; font-size: 0.65rem; letter-spacing: 0.5px; text-transform: uppercase; margin-bottom: 4px;">
                    <i class="bi bi-lightning-charge-fill me-1"></i> LLAMADO DE EMERGENCIA
                </div>
                <div style="font-size: 0.72rem; color: var(--text-primary, #1e293b); font-weight: 600; line-height: 1.3;">
                    ${contenido}
                </div>
            </div>`;
        }
    }

    const html = `
    <div style="width: 340px; font-family: 'Inter', sans-serif; cursor: default; background-color: var(--card-bg, #ffffff); color: var(--text-primary, #1e293b); padding: 12px; border-radius: 6px; margin: 0; border: 1px solid var(--border-color, #e2e8f0); box-shadow: var(--shadow-premium);">
        
        <!-- Header Principal -->
        <div style="border-bottom: 1px solid var(--border-color, #e2e8f0); padding-bottom: 12px; margin-bottom: 12px;">
            
            <div style="color: var(--text-secondary, #64748b); font-weight: 700; font-size: 0.65rem; letter-spacing: 0.5px; text-transform: uppercase; margin-bottom: 4px;">
                <i class="bi bi-clock me-1" style="font-size:0.8rem"></i> REGISTRO DE ASISTENCIA
            </div>
            
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="color: var(--primary-color, #6366f1); font-weight: 700; font-size: 0.85rem;">
                     ${dateFormatted}
                </div>
                <div>
                    ${badgeHtml}
                </div>
            </div>

            <div style="color:var(--text-primary, #1e293b); font-weight:700; font-size:0.9rem; margin-bottom:4px; line-height:1.2;">${empName}</div>
            <div style="color:var(--text-secondary, #64748b); font-weight:500; font-size:0.65rem; margin-bottom:2px; text-transform: uppercase;">ÁREA: <span style="color:var(--text-primary, #1e293b);">${empAreaText}</span></div>
            <div style="color:var(--text-secondary, #64748b); font-weight:500; font-size:0.65rem; margin-bottom:2px; text-transform: uppercase;">TURNO: <span style="color:var(--text-primary, #1e293b);">${shiftName}</span></div>
            <div style="color:var(--text-secondary, #64748b); font-weight:500; font-size:0.65rem; text-transform: uppercase;">CICLO: <span style="color:var(--text-primary, #1e293b);">${cycleName}</span></div>
            ${isFer ? `<div style="margin-top: 6px; padding: 6px 8px; background-color: rgba(245, 158, 11, 0.1); border-left: 3px solid var(--warning-color, #f59e0b); border-radius: 4px; color: var(--warning-color, #f59e0b); font-size: 0.75rem; font-weight: 600; text-align: left;"><i class="bi bi-star-fill me-1"></i> ${feriadoDesc}</div>` : ''}
            
        </div>

        <!-- Tabla Principal (Desglose de cálculo de horas) -->
        <div style="margin-bottom: 12px;">
            <div style="display: flex; margin-bottom: 6px;">
                <div style="width: 32%;"></div>
                <div style="width: 34%; text-align: center; color: var(--text-secondary, #64748b); font-weight: 700; font-size: 0.6rem; letter-spacing: 0.5px;">PROGRAMADO</div>
                <div style="width: 34%; text-align: center; color: var(--primary-color, #6366f1); font-weight: 700; font-size: 0.6rem; letter-spacing: 0.5px;">REAL</div>
            </div>
            
            <!-- Entrada -->
            <div style="display: flex; align-items: center; border-bottom: 1px dashed var(--border-color, #e2e8f0); padding: 4px 0;">
                <div style="width: 32%; color: var(--text-secondary, #64748b); font-size: 0.75rem; font-weight: 500;">Entrada</div>
                <div style="width: 34%; text-align: center; color: var(--text-secondary, #64748b); font-size: 0.75rem; font-family: monospace;">${e.hora_entrada_teorica ? (e.hora_entrada_teorica.length === 5 ? e.hora_entrada_teorica + ':00' : e.hora_entrada_teorica) : '--:--:--'}</div>
                <div style="width: 34%; text-align: center; color: ${e.alerta_atraso ? 'var(--warning-color, #f59e0b)' : 'var(--text-primary, #1e293b)'}; font-size: 0.75rem; font-family: monospace; font-weight: 700;">${e.hora_entrada_real || '--:--:--'}</div>
            </div>
            <!-- Salida -->
            <div style="display: flex; align-items: center; border-bottom: 1px dashed var(--border-color, #e2e8f0); padding: 4px 0;">
                <div style="width: 32%; color: var(--text-secondary, #64748b); font-size: 0.75rem; font-weight: 500;">Salida</div>
                <div style="width: 34%; text-align: center; color: var(--text-secondary, #64748b); font-size: 0.75rem; font-family: monospace;">${e.hora_salida_teorica ? (e.hora_salida_teorica.length === 5 ? e.hora_salida_teorica + ':00' : e.hora_salida_teorica) : '--:--:--'}</div>
                <div style="width: 34%; text-align: center; color: var(--text-primary, #1e293b); font-size: 0.75rem; font-family: monospace; font-weight: 700;">${e.hora_salida_real || '--:--:--'}</div>
            </div>
            <!-- Permanencia -->
            <div style="display: flex; align-items: center; border-bottom: 1px dashed var(--border-color, #e2e8f0); padding: 4px 0;">
                <div style="width: 32%; color: var(--text-secondary, #64748b); font-size: 0.75rem; font-weight: 500;">Permanencia</div>
                <div style="width: 34%; text-align: center; color: var(--text-secondary, #64748b); font-size: 0.75rem; font-family: monospace;">${permProgMins > 0 ? _fM(permProgMins) : '--:--:--'}</div>
                <div style="width: 34%; text-align: center; color: var(--text-primary, #1e293b); font-size: 0.75rem; font-family: monospace; font-weight: 700;">${permRealMins > 0 ? _fM(permRealMins) : '--:--:--'}</div>
            </div>
            <!-- Descuento Colación -->
            <div style="display: flex; align-items: center; border-bottom: 1px dashed var(--border-color, #e2e8f0); padding: 4px 0;">
                <div style="width: 32%; color: var(--text-secondary, #64748b); font-size: 0.75rem; font-weight: 500;">
                    Descuento Colación ${colRealText ? `<span style="font-size:0.55rem; color:var(--text-secondary, #64748b); font-weight:normal; margin-left:2px;">${colRealText}</span>` : ''}
                </div>
                <div style="width: 34%; text-align: center; color: var(--text-secondary, #64748b); font-size: 0.75rem; font-family: monospace;">${colAuto > 0 ? '-' + _fM(colAuto) : '--:--:--'}</div>
                <div style="width: 34%; text-align: center; color: var(--danger-color, #f43f5e); font-size: 0.75rem; font-family: monospace; font-weight: 700;">${colApli > 0 ? '-' + _fM(colApli) : '--:--:--'}</div>
            </div>
            <!-- Horas Efectivas -->
            <div style="display: flex; align-items: center; padding: 4px 0;">
                <div style="width: 32%; color: var(--text-secondary, #64748b); font-size: 0.75rem; font-weight: 700;">Horas Efectivas</div>
                <div style="width: 34%; text-align: center; color: var(--text-secondary, #64748b); font-size: 0.75rem; font-family: monospace; font-weight: 700;">${e.horas_teoricas ? formatDecimalToTime(e.horas_teoricas) : '--:--:--'}</div>
                <div style="width: 34%; text-align: center; color: ${hoursColor}; font-size: 0.75rem; font-family: monospace; font-weight: 700;">${e.horas_trabajadas ? formatDecimalToTime(e.horas_trabajadas) : '--:--:--'}</div>
            </div>
        </div>

        ${incidenciasHtml}

        ${bloquesAdicionalesHtml}

        ${cardsHtml}
    </div>
    `;

    return _escAttr(html);
}

function _escAttr(html) {
    return html.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ============================================================
// NUEVA LÓGICA UNIFICADA DE CONDONACIÓN MASIVA
// Reemplaza: promptCondonacionDeuda, toggleCondonacionDeuda, executeCondonacion
// También reemplaza: executePerdonazoMasivo (marcaciones_manuales.js)
// ============================================================

/**
 * Ejecuta la condonación o revocación para una lista de empleados y rango de fechas.
 * @param {number[]} empleadosIds - IDs de empleados a procesar
 * @param {string} fechaInicio - Fecha inicio (YYYY-MM-DD)
 * @param {string} fechaFin - Fecha fin (YYYY-MM-DD)
 * @param {number} tipo - 0=Revocar, 1=Salida, 2=Atraso, 3=Ambos
 * @param {Function} [onSuccess] - Callback opcional tras éxito
 */
window.executeCondonacionMasiva = async function(empleadosIds, fechaInicio, fechaFin, tipo, onSuccess) {
    if (!empleadosIds || empleadosIds.length === 0) return;
    tipo = parseInt(tipo, 10);
    const isRevoke = tipo === 0;

    try {
        const payload = {
            empleados_ids: empleadosIds.map(id => parseInt(id, 10)),
            fecha_inicio: fechaInicio,
            fecha_fin: fechaFin,
            tipo_condonacion: tipo
        };
        const response = await fetch('/api/asistencia/condonar-deuda/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${window.AuthToken || localStorage.getItem('token')}`
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || 'Error al procesar la condonación');
        }

        const result = await response.json();
        const cuenta = result.registros_procesados || empleadosIds.length;
        const accion = isRevoke ? 'revocada' : 'condonada';
        const tipotxt = { 0:'(Revocar)', 1:'Salida Adelantada', 2:'Atraso', 3:'Atraso + Salida' }[tipo] || '';

        Swal.fire({
            icon: isRevoke ? 'warning' : 'success',
            title: isRevoke ? 'Condonación Revocada' : '✓ Perdonazo Aplicado',
            html: `<b>${cuenta}</b> registro(s) ${accion}.<br><small class="text-muted">${tipotxt}</small>`,
            timer: 2500,
            showConfirmButton: false
        });

        // Cerrar panel lateral si estuviese abierto
        cerrarPanelPerdonazo();
        // Cerrar popovers del tooltip
        document.querySelectorAll('.popover').forEach(p => p.remove());
        // Desactivar modo switch perdonazo y limpiar selecciones
        _perdonazoState.seleccionados.clear();
        if (onSuccess) onSuccess();
        // Refresco forzado desde API (fix bug raíz)
        if (typeof window.loadMarcacionesData === 'function') {
            window.loadMarcacionesData();
        } else {
            location.reload();
        }

    } catch (error) {
        console.error('Error executeCondonacionMasiva:', error);
        Swal.fire('Error', error.message, 'error');
    }
};



