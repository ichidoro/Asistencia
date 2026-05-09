// configuracion_ui.js - Interfaz Completa de Configuración (Bonos y Justificaciones)

const API_CONFIG = '/api/configuracion/';

// Estado local
let bonosList = [];
let tiposJustificacionList = [];
let globalCargosList = []; // [NEW] Cache cargos for dropdowns
let pagadoresList = []; // [NEW] Cache pagadores

window.appendCargoToInput = function (element, cargo) {
    // Find the input in the same input-group
    const input = element.closest('.input-group').querySelector('input');
    if (!input) return;

    let current = input.value.trim();
    if (current.length > 0 && !current.endsWith(',')) {
        current += ', ';
    }
    input.value = current + cargo;
    // Keep dropdown open? No, default bootstrap behavior closes it, which feels right.
}


// ══════════════════════════════════════════════════════════════════════════════
// ESTADOS DE ASISTENCIA — Configuración Visual
// ══════════════════════════════════════════════════════════════════════════════

let _estadosConfigList = [];

window.loadEstadosConfig = async function() {
    const container = document.getElementById('estados-config-container');
    if (!container) return;

    container.innerHTML = `<div class="text-center py-5 text-muted">
        <div class="spinner-border spinner-border-sm" role="status"></div> Cargando estados...
    </div>`;

    try {
        const res = await fetch('/api/configuracion/estados/?solo_activos=false');
        if (!res.ok) throw new Error('Error cargando estados');
        _estadosConfigList = await res.json();
        renderEstadosConfig();
    } catch(e) {
        container.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
    }
};

const COLOR_OPTIONS = [
    // ── Colores sólidos ──────────────────────────────────────────
    { value: 'color-verde',    label: '🟢 Verde',         preview: '#10b981' },
    { value: 'color-azul',     label: '🔵 Azul',          preview: '#3b82f6' },
    { value: 'color-rojo',     label: '🔴 Rojo',          preview: '#ef4444' },
    { value: 'color-amarillo', label: '🟡 Amarillo',      preview: '#f59e0b' },
    { value: 'color-naranja',  label: '🟠 Naranja',       preview: '#f97316' },
    { value: 'color-purpura',  label: '🟣 Púrpura',       preview: '#8b5cf6' },
    { value: 'color-rosa',     label: '🩷 Rosa',           preview: '#f472b6' },
    { value: 'color-cian',     label: '🩵 Cian',           preview: '#22d3ee' },
    { value: 'color-lima',     label: '🍏 Lima',           preview: '#a3e635' },
    { value: 'color-indigo',   label: '💜 Índigo',         preview: '#6366f1' },
    { value: 'color-teal',     label: '🌊 Teal',           preview: '#14b8a6' },
    { value: 'color-gris',     label: '⬜ Gris',           preview: '#64748b' },
    { value: 'color-negro',    label: '⬛ Negro',          preview: '#1f2937' },
    // ── Flúor (brillo neon) ──────────────────────────────────────
    { value: 'color-fluor-verde',    label: '💚 Flúor Verde',    preview: '#b3f500' },
    { value: 'color-fluor-azul',     label: '🩵 Flúor Azul',     preview: '#00d4ff' },
    { value: 'color-fluor-amarillo', label: '💛 Flúor Amarillo', preview: '#ffe600' },
    { value: 'color-fluor-rosa',     label: '🩷 Flúor Rosa',     preview: '#ff4dde' },
    // ── Intermitentes (animación) ────────────────────────────────
    { value: 'color-pulso-rojo',  label: '🚨 Pulso Rojo',    preview: '#ef4444' },
    { value: 'color-pulso-verde', label: '✅ Pulso Verde',   preview: '#b3f500' },
    { value: 'color-pulso-azul',  label: '🔔 Pulso Azul',    preview: '#00d4ff' },
    { value: 'color-glitter-oro',   label: '✨ Glitter Oro',   preview: '#f59e0b' },
    { value: 'color-glitter-plata', label: '🪙 Glitter Plata', preview: '#94a3b8' },
];

function renderEstadosConfig() {
    const container = document.getElementById('estados-config-container');
    if (!container) return;

    const colorSelect = COLOR_OPTIONS.map(c =>
        `<option value="${c.value}">${c.label}</option>`
    ).join('');

    let html = `
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h5 class="fw-bold mb-1">🎨 Tabla Maestra de Estados</h5>
            <p class="small text-muted mb-0">Define cómo se visualiza cada estado en la grilla y tooltips.
            El <strong>código</strong> es inmutable — lo usa el motor de asistencia.</p>
        </div>
        <button class="btn btn-sm btn-outline-secondary" onclick="loadEstadosConfig()">
            <i class="bi bi-arrow-clockwise"></i> Recargar
        </button>
    </div>
    <div class="alert alert-info py-2 small mb-3">
        <i class="bi bi-info-circle me-1"></i>
        Los cambios se aplican en tiempo real. Recarga la grilla de marcaciones para ver el efecto.
    </div>
    <div class="table-responsive">
    <table class="table table-hover align-middle" id="tabla-estados-config">
        <thead class="table-light">
            <tr>
                <th style="width:110px">Código</th>
                <th style="width:130px">Nombre Display</th>
                <th style="width:80px" class="text-center">Etiqueta (Max 5)</th>
                <th>Descripción</th>
                <th style="width:175px">Color</th>
                <th style="width:165px">Icono (Bootstrap)</th>
                <th style="width:80px" class="text-center">Preview</th>
                <th style="width:80px" class="text-center">Activo</th>
                <th style="width:80px" class="text-center">Guardar</th>
            </tr>
        </thead>
        <tbody>
    `;

    _estadosConfigList.forEach(e => {
        const colorOpts = COLOR_OPTIONS.map(c =>
            `<option value="${c.value}" ${c.value === e.color_clase ? 'selected' : ''}>${c.label}</option>`
        ).join('');

        html += `
        <tr id="estado-row-${e.codigo}">
            <td>
                <span class="badge bg-light text-dark border fw-bold font-monospace">${e.codigo}</span>
                ${e.es_sistema ? '<div class="small text-muted" style="font-size:0.65rem">Sistema</div>' : ''}
            </td>
            <td>
                <input type="text" class="form-control form-control-sm"
                    id="estado-nombre-${e.codigo}" value="${e.nombre_display || ''}"
                    placeholder="Nombre visible">
            </td>
            <td>
                <input type="text" class="form-control form-control-sm text-center font-monospace"
                    id="estado-short-${e.codigo}" value="${e.short_label || (e.codigo === 'JORNADA_ESPECIAL' ? 'ESP' : e.codigo.substring(0,3))}"
                    placeholder="Etiq" maxlength="5"
                    oninput="previewEstadoBadge('${e.codigo}')">
            </td>
            <td>
                <input type="text" class="form-control form-control-sm"
                    id="estado-desc-${e.codigo}" value="${e.descripcion || ''}"
                    placeholder="Descripción del estado">
            </td>
            <td>
                <select class="form-select form-select-sm" id="estado-color-${e.codigo}"
                    onchange="previewEstadoBadge('${e.codigo}')">
                    ${colorOpts}
                </select>
            </td>
            <td>
                <div class="input-group input-group-sm">
                    <span class="input-group-text p-1"><i id="estado-icon-preview-${e.codigo}" class="bi ${e.icono_bi || 'bi-circle'}"></i></span>
                    <input type="text" class="form-control form-control-sm font-monospace"
                        id="estado-icono-${e.codigo}" value="${e.icono_bi || ''}"
                        placeholder="bi-circle-fill"
                        oninput="previewEstadoBadge('${e.codigo}')">
                </div>
            </td>
            <td class="text-center" id="preview-${e.codigo}">
                <span id="estado-preview-badge-${e.codigo}" class="badge-status ${e.color_clase} px-2 py-1" style="font-size:0.75rem">
                    <i class="bi ${e.icono_bi || 'bi-circle'} me-1"></i>${e.short_label || (e.codigo === 'JORNADA_ESPECIAL' ? 'ESP' : e.codigo.substring(0,3))}
                </span>
            </td>
            <td class="text-center">
                <div class="form-check form-switch d-flex justify-content-center">
                    <input class="form-check-input" type="checkbox" role="switch"
                        id="estado-activo-${e.codigo}" ${e.activo ? 'checked' : ''}>
                </div>
            </td>
            <td class="text-center">
                <button class="btn btn-sm btn-primary" onclick="saveEstado('${e.codigo}')" title="Guardar">
                    <i class="bi bi-floppy"></i>
                </button>
            </td>
        </tr>`;
    });

    html += `</tbody></table></div>`;
    container.innerHTML = html;
}

window.previewEstadoBadge = function(codigo) {
    const color = document.getElementById(`estado-color-${codigo}`)?.value || 'badge-state-neutral';
    const icono = document.getElementById(`estado-icono-${codigo}`)?.value || 'bi-circle';
    const badge = document.getElementById(`estado-preview-badge-${codigo}`);
    const iconPrev = document.getElementById(`estado-icon-preview-${codigo}`);
    if (badge) {
        badge.className = `badge-status ${color} px-2 py-1`;
        badge.style.fontSize = '0.75rem';
        const displayLabel = document.getElementById(`estado-short-${codigo}`)?.value || (codigo === 'JORNADA_ESPECIAL' ? 'ESP' : codigo.substring(0,3));
        badge.innerHTML = `<i class="bi ${icono} me-1"></i>${displayLabel}`;
    }
    if (iconPrev) iconPrev.className = `bi ${icono}`;
};

window.saveEstado = async function(codigo) {
    const nombre = document.getElementById(`estado-nombre-${codigo}`)?.value?.trim();
    const shortLabel = document.getElementById(`estado-short-${codigo}`)?.value?.trim();
    const desc = document.getElementById(`estado-desc-${codigo}`)?.value?.trim();
    const color = document.getElementById(`estado-color-${codigo}`)?.value;
    const icono = document.getElementById(`estado-icono-${codigo}`)?.value?.trim();
    const activo = document.getElementById(`estado-activo-${codigo}`)?.checked ? 1 : 0;

    try {
        const res = await fetch(`/api/configuracion/estados/${codigo}/`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre_display: nombre, short_label: shortLabel, descripcion: desc, color_clase: color, icono_bi: icono, activo })
        });
        if (!res.ok) throw new Error((await res.json()).detail || 'Error guardando');

        // Actualizar caché global para que los badges se vean de inmediato sin recargar la página
        if (window._estadosAsistencia && window._estadosAsistencia[codigo]) {
            window._estadosAsistencia[codigo].nombre_display = nombre;
            window._estadosAsistencia[codigo].short_label = shortLabel;
            window._estadosAsistencia[codigo].color_clase = color;
            window._estadosAsistencia[codigo].icono_bi = icono;
            window._estadosAsistencia[codigo].activo = activo;
        }

        showToast(`Estado '${codigo}' guardado correctamente`, 'success');
    } catch(e) {
        alert('Error: ' + e.message);
    }
};
// ==========================================
// INICIALIZACIÓN
// ==========================================
function initConfiguracionUI() {
    // [FIX] Guardar para evitar re-flickering si ya inicializó
    if (window._config_initialized) {
        console.log("⚙️ Configuración (CRUD) ya inicializada. Omitiendo.");
        return;
    }
    
    console.log("Inicializando UI de Configuración (CRUD Completo)...");

    // Configurar listeners de formularios
    const formBono = document.getElementById('form-bono');
    if (formBono) {
        formBono.onsubmit = (e) => {
            e.preventDefault();
            saveBono();
        };
    }

    const formTipoJ = document.getElementById('form-tipo-justificacion');
    if (formTipoJ) {
        formTipoJ.onsubmit = (e) => {
            e.preventDefault();
            saveTipoJustificacion();
        };
    }

    // Datalists Container Check
    if (!document.getElementById('datalists-container')) {
        const div = document.createElement('div');
        div.id = 'datalists-container';
        div.innerHTML = `
            <datalist id="list-cargos"></datalist>
        `;
        document.body.appendChild(div);
    }

    loadBonos();
    loadTiposJustificacion();
    loadPagadores(); // [NEW]
    loadMetadata();
    loadEmailSettings(); // [NEW]
    loadAreaNotificaciones(); // [NEW]

    // [NEW] Escuchar cambio a pestaña de Seguridad
    const seguridadTabBtn = document.getElementById('seguridad-config-tab');
    if (seguridadTabBtn) {
        seguridadTabBtn.addEventListener('shown.bs.tab', () => {
            if (typeof initSeguridadUI === 'function') {
                initSeguridadUI();
            }
        });
    }

    window._config_initialized = true;
}

async function loadMetadata() {
    try {
        const response = await fetch('/api/empleados/metadata/');
        if (!response.ok) return;

        const data = await response.json();

        const listCargos = document.getElementById('list-cargos');

        // Populate Cargos
        if (data.cargos) {
            globalCargosList = data.cargos; // [NEW] Save to global
            if (listCargos) {
                listCargos.innerHTML = data.cargos.map(c => `<option value="${c}">`).join('');
            }
        }

        // Populate Areas in Notificaciones
        if (data.areas) {
            const selectAreas = document.getElementById('notif-area-nombre');
            if (selectAreas) {
                const defaultOption = '<option value="" selected disabled>Seleccione un Área...</option>';
                selectAreas.innerHTML = defaultOption + data.areas.map(a => `<option value="${a}">${a}</option>`).join('');
            }
        }

    } catch (e) {
        console.warn("Could not load metadata for dropdowns", e);
    }
}

// ==========================================
// BONOS: DATOS Y RENDER
// ==========================================
async function loadBonos() {
    try {
        const response = await fetch(`${API_CONFIG}bonos/`);
        if (!response.ok) throw new Error("Error cargando bonos");
        bonosList = await response.json();
        renderBonos();
    } catch (error) {
        console.error(error);
        showToast("Error al cargar bonos", "error");
    }
}

function renderBonos() {
    const container = document.getElementById('tab-bonos');
    if (!container) return;

    let h5Title = `
        <div class="d-flex justify-content-between align-items-center mb-4">
            <h5 class="mb-0 fw-bold">Listado de Bonos e Incentivos</h5>
            <button class="btn btn-primary btn-sm" onclick="openModalBono()">
                <i class="bi bi-plus-circle"></i> Nuevo Bono
            </button>
        </div>
    `;

    if (bonosList.length === 0) {
        container.innerHTML = h5Title + `
            <div class="empty-state py-5 card border-0 shadow-sm">
                <div class="stat-icon mb-3" style="font-size: 3rem;">💰</div>
                <h3>Sin Bonos Configurados</h3>
                <p class="text-muted">Presione el botón para crear su primer bono genérico.</p>
            </div>
        `;
        return;
    }

    let html = h5Title + `<div class="row g-4">`;

    bonosList.forEach(bono => {
        html += `
            <div class="col-md-6">
                <div class="card h-100 border-0 shadow-sm hover-up">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <h6 class="card-title fw-bold mb-0">${bono.nombre}</h6>
                            <span class="badge ${bono.activo ? 'bg-success' : 'bg-secondary'}">
                                ${bono.activo ? 'Activo' : 'Inactivo'}
                            </span>
                        </div>
                        <p class="small text-muted mb-3" style="min-height: 40px;">${bono.descripcion || 'Sin descripción'}</p>
                        
                        <div class="rules-preview mb-3">
                            <p class="small fw-bold mb-1">Reglas de Aplicación:</p>
                            ${bono.reglas && bono.reglas.length > 0 ? bono.reglas.map(r => `
                                <div class="rule-item-mini small p-2 bg-light rounded mb-1">
                                    <div class="d-flex justify-content-between mb-1">
                                        <span class="fw-bold text-primary">$${r.monto.toLocaleString('es-CL')}</span>
                                        <span class="badge bg-white text-dark border">${r.tipo_contrato || 'Todo Contrato'}</span>
                                    </div>
                                    <div class="d-flex flex-wrap gap-2 text-muted" style="font-size: 0.75rem;">
                                        ${r.asistencia_minima < 100 ? `<span class="text-danger"><i class="bi bi-graph-down"></i> >${r.asistencia_minima}% Asist.</span>` : '<span><i class="bi bi-check-all"></i> 100% Asist.</span>'}
                                        ${r.cargo_requerido ? `<span><i class="bi bi-person-badge"></i> ${r.cargo_requerido}</span>` : ''}
                                        ${r.es_proporcional ? '<span class="text-info" title="Monto proporcional a días trabajados"><i class="bi bi-pie-chart"></i> Prop.</span>' : ''}
                                    </div>
                                </div>
                            `).join('') : '<p class="text-muted small italic">Sin reglas definidas</p>'}
                        </div>

                        <div class="d-flex gap-2">
                            <button class="btn btn-outline-primary btn-sm flex-grow-1" onclick="editBono(${bono.id})">
                                <i class="bi bi-pencil"></i> Editar
                            </button>
                            <button class="btn btn-outline-danger btn-sm" onclick="confirmDeleteBono(${bono.id})">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    });

    html += `</div>`;
    container.innerHTML = html;
}

// ==========================================
// BONOS: MODAL Y FORMULARIO
// ==========================================
function openModalBono(bono = null) {
    const modal = document.getElementById('modal-bono');
    const title = document.getElementById('modal-bono-title');
    const form = document.getElementById('form-bono');
    const container = document.getElementById('reglas-container');

    form.reset();
    container.innerHTML = '';

    if (bono) {
        title.innerText = 'Editar Bono';
        document.getElementById('bono-id').value = bono.id;
        document.getElementById('bono-nombre').value = bono.nombre;
        document.getElementById('bono-descripcion').value = bono.descripcion || '';
        document.getElementById('bono-activo').value = bono.activo ? 'true' : 'false';

        if (bono.reglas) {
            bono.reglas.forEach(r => addBonoReglaRow(r));
        }
    } else {
        title.innerText = 'Crear Nuevo Bono';
        document.getElementById('bono-id').value = '';
        addBonoReglaRow(); // Iniciar con una fila vacía
    }

    modal.style.display = 'flex';
}

function closeModalBono() {
    document.getElementById('modal-bono').style.display = 'none';
}

function addBonoReglaRow(regla = null) {
    const container = document.getElementById('reglas-container');
    const rowIdx = container.querySelectorAll('.regla-row').length; // ID único basado en el conteo actual
    const div = document.createElement('div');
    div.className = 'regla-row card p-3 mb-2 bg-light border-0 shadow-sm';

    div.innerHTML = `
        <div class="row g-2 mb-2">
            <div class="col-md-6">
                <label for="rule-contrato-${rowIdx}" class="small text-muted fw-bold">1. Tipo Contrato</label>
                <select id="rule-contrato-${rowIdx}" class="rule-contrato form-select form-select-sm">
                    <option value="">Todos los Contratos</option>
                    <option value="Indefinido" ${regla && regla.tipo_contrato === 'Indefinido' ? 'selected' : ''}>Indefinido</option>
                    <option value="Temporal" ${regla && regla.tipo_contrato === 'Temporal' ? 'selected' : ''}>Temporal</option>
                </select>
            </div>
            <div class="col-md-6">
                <label for="rule-monto-${rowIdx}" class="small text-muted fw-bold">2. Monto Base ($)</label>
                <div class="input-group input-group-sm">
                    <span class="input-group-text">$</span>
                    <input type="number" id="rule-monto-${rowIdx}" class="rule-monto form-control font-monospace fw-bold" value="${regla ? regla.monto : 0}" required>
                </div>
            </div>
        </div>
        <div class="row g-2 align-items-end">
            <div class="col-md-2">
                <label for="rule-asistencia-${rowIdx}" class="small text-muted">% Asist.</label>
                <div class="input-group input-group-sm">
                    <input type="number" id="rule-asistencia-${rowIdx}" class="rule-asistencia form-control" value="${regla ? regla.asistencia_minima : 100}" min="0" max="100" step="1">
                </div>
            </div>
            <div class="col-md-2 text-center">
                <label for="rule-proporcional-${rowIdx}" class="small text-muted" title="¿Descontar proporcional?">Prop.</label>
                <div class="form-check form-switch d-flex justify-content-center pt-1">
                    <input id="rule-proporcional-${rowIdx}" class="rule-proporcional form-check-input" type="checkbox" ${regla && regla.es_proporcional ? 'checked' : ''}>
                </div>
            </div>
            <div class="col-md-3">
                <label for="rule-cargo-${rowIdx}" class="small text-muted">Cargo Req.</label>
                <input type="text" id="rule-cargo-${rowIdx}" class="rule-cargo form-control form-control-sm" placeholder="Todos" value="${regla && regla.cargo_requerido ? regla.cargo_requerido : ''}" list="list-cargos" autocomplete="off">
            </div>
            <div class="col-md-5">
                <label for="rule-excluidos-${rowIdx}" class="small text-muted text-danger">Excluir Cargos</label>
                <div class="input-group input-group-sm">
                    <input type="text" id="rule-excluidos-${rowIdx}" class="rule-excluidos form-control" 
                        placeholder="Ej: Gerente, Director" 
                        value="${regla && regla.cargos_excluidos ? regla.cargos_excluidos : ''}">
                    
                    <button class="btn btn-outline-secondary dropdown-toggle px-2" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                        <i class="bi bi-plus-circle"></i>
                    </button>
                    <ul class="dropdown-menu dropdown-menu-end p-0" style="max-height: 300px; overflow-y: auto;">
                        ${globalCargosList.map(c =>
        `<li><a class="dropdown-item small py-2" href="#" onclick="appendCargoToInput(this, '${c}'); return false;">${c}</a></li>`
    ).join('') || '<li><span class="dropdown-item text-muted">Cargando...</span></li>'}
                    </ul>
                </div>
            </div>
            <div class="col-md-1 text-end">
                <button type="button" class="btn btn-sm btn-outline-danger w-100" onclick="this.closest('.regla-row').remove()" title="Eliminar regla">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        </div>
    `;
    container.appendChild(div);
}

async function saveBono() {
    const id = document.getElementById('bono-id').value;
    const nombre = document.getElementById('bono-nombre').value;
    const descripcion = document.getElementById('bono-descripcion').value;
    const activo = document.getElementById('bono-activo').value === 'true';

    // Recolectar reglas
    const reglas = [];
    const ruleRows = document.querySelectorAll('.regla-row');
    ruleRows.forEach(row => {
        reglas.push({
            monto: parseFloat(row.querySelector('.rule-monto').value) || 0,
            tipo_contrato: row.querySelector('.rule-contrato').value || null,
            asistencia_minima: parseFloat(row.querySelector('.rule-asistencia').value) || 100.0,
            cargo_requerido: row.querySelector('.rule-cargo').value || null,
            cargos_excluidos: row.querySelector('.rule-excluidos').value || null,
            es_proporcional: row.querySelector('.rule-proporcional').checked
        });
    });

    const body = { nombre, descripcion, activo, reglas };
    const method = id ? 'PUT' : 'POST';
    const url = id ? `${API_CONFIG}bonos/${id}/` : `${API_CONFIG}bonos/`;

    const btnGuardar = document.querySelector('#modal-bono .btn-primary');
    btnGuardar.disabled = true;
    btnGuardar.textContent = 'Guardando...';

    try {
        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || "Error al guardar bono");
        }

        showToast(`Bono ${id ? 'actualizado' : 'creado'} correctamente`, "success");
        closeModalBono();
        loadBonos();
    } catch (error) {
        console.error(error);
        alert("Error al guardar bono: " + error.message);
    } finally {
        btnGuardar.disabled = false;
        btnGuardar.textContent = 'Guardar Bono';
    }
}

function editBono(id) {
    const bono = bonosList.find(b => b.id === id);
    if (bono) openModalBono(bono);
}

function confirmDeleteBono(id) {
    if (confirm("¿Está seguro de eliminar este bono? Esta acción no se puede deshacer.")) {
        deleteBono(id);
    }
}

async function deleteBono(id) {
    try {
        const response = await fetch(`${API_CONFIG}bonos/${id}/`, { method: 'DELETE' });
        if (!response.ok) throw new Error("Error al eliminar");
        showToast("Bono eliminado", "success");
        loadBonos();
    } catch (error) {
        alert(error.message);
    }
}

// ==========================================
// JUSTIFICACIONES: DATOS Y RENDER
// ==========================================
async function loadTiposJustificacion() {
    try {
        const response = await fetch(`${API_CONFIG}justificaciones/tipos/?all=true`);
        if (!response.ok) throw new Error("Error cargando tipos");
        tiposJustificacionList = await response.json();
        renderTiposJustificacion();
    } catch (error) {
        console.error(error);
    }
}

// Global scope functions
window.sortJustificaciones = function (key) {
    TableSorter.sort(tiposJustificacionList, key, 'justificaciones');
    renderTiposJustificacion();
};

window.renderTiposJustificacion = function () {
    const container = document.getElementById('tab-justificaciones');
    if (!container) return;

    let h5Title = `
        <div class="d-flex justify-content-between align-items-center mb-4">
            <h5 class="mb-0 fw-bold">Configuración de Justificaciones e Inasistencias</h5>
            <button class="btn btn-primary btn-sm" onclick="openModalTipoJ()">
                <i class="bi bi-plus-circle"></i> Nuevo Tipo
            </button>
        </div>
    `;

    let html = h5Title + `
        <div class="table-responsive card border-0 shadow-sm p-3">
            <table class="table table-hover align-middle">
                <thead class="table-light">
                    <tr>
                        <th style="cursor: pointer;" onclick="sortJustificaciones('nombre')" title="Ordenar por Nombre">
                            Nombre y Descripción <i id="sort-icon-justificaciones-nombre" class="bi bi-arrow-down-up small text-muted"></i>
                        </th>
                        <th style="cursor: pointer;" onclick="sortJustificaciones('dias_habiles')" title="Ordenar por Cálculo">
                            Cálculo <i id="sort-icon-justificaciones-dias_habiles" class="bi bi-arrow-down-up small text-muted"></i>
                        </th>
                        <th style="cursor: pointer;" onclick="sortJustificaciones('con_goce_sueldo')" title="Ordenar por Goce">
                            Goce Sueldo <i id="sort-icon-justificaciones-con_goce_sueldo" class="bi bi-arrow-down-up small text-muted"></i>
                        </th>
                        <th style="cursor: pointer;" onclick="sortJustificaciones('activo')" title="Ordenar por Estado">
                            Estado <i id="sort-icon-justificaciones-activo" class="bi bi-arrow-down-up small text-muted"></i>
                        </th>
                        <th>Acciones</th>
                    </tr>
                </thead>
                <tbody id="justificaciones-table-body">
    `;

    tiposJustificacionList.forEach(tipo => {
        html += `
            <tr>
                <td>
                    <div class="fw-bold text-primary">${tipo.nombre}</div>
                    <div class="small text-muted" style="font-size: 0.75rem;">${tipo.descripcion || 'Sin descripción'}</div>
                </td>
                <td>
                    <span class="badge ${tipo.dias_habiles ? 'bg-outline-primary bordered' : 'bg-outline-info bordered'}" 
                          style="color: #666; border: 1px solid #ddd;">
                        ${tipo.dias_habiles ? 'Hábiles' : 'Corridos'}
                    </span>
                </td>
                <td>
                    <span class="badge ${tipo.con_goce_sueldo ? 'bg-success' : 'bg-danger'}">
                        ${tipo.con_goce_sueldo ? 'Sí' : 'No'}
                    </span>
                    <div class="small text-muted" style="font-size: 0.7rem;">Pagador: ${tipo.pagador}</div>
                </td>
                <td>
                    <span class="badge ${tipo.activo ? 'bg-light text-success' : 'bg-light text-muted'}">
                        ${tipo.activo ? 'Activo' : 'Inactivo'}
                    </span>
                </td>
                <td>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-light" onclick="editTipoJ(${tipo.id})"><i class="bi bi-pencil"></i></button>
                        <button class="btn btn-sm btn-light text-danger" onclick="confirmDeleteTipoJ(${tipo.id})"><i class="bi bi-trash"></i></button>
                    </div>
                </td>
            </tr>
        `;
    });

    html += `</tbody></table></div>`;
    container.innerHTML = html;

    // Update icons AFTER render
    if (window.TableSorter) {
        TableSorter.updateIcons('justificaciones', ['nombre', 'dias_habiles', 'con_goce_sueldo', 'activo']);
    }
}

// ==========================================
// JUSTIFICACIONES: MODAL Y FORMULARIO
// ==========================================
function openModalTipoJ(tipo = null) {
    const modal = document.getElementById('modal-tipo-justificacion');
    const title = document.getElementById('modal-tipo-j-title');
    const form = document.getElementById('form-tipo-justificacion');

    form.reset();

    if (tipo) {
        title.innerText = 'Editar Tipo de Justificación';
        document.getElementById('tipo-j-id').value = tipo.id;
        document.getElementById('tipo-j-nombre').value = tipo.nombre;
        document.getElementById('tipo-j-nomenclatura').value = tipo.nomenclatura || '';
        document.getElementById('tipo-j-descripcion').value = tipo.descripcion || '';
        document.getElementById('tipo-j-goce').value = tipo.con_goce_sueldo ? 'true' : 'false';
        document.getElementById('tipo-j-periodo').value = tipo.dias_habiles ? 'true' : 'false';
        document.getElementById('tipo-j-pagador').value = tipo.pagador || 'Empleador';
        document.getElementById('tipo-j-dias-defecto').value = tipo.dias_defecto !== undefined && tipo.dias_defecto !== null ? tipo.dias_defecto : '';
        document.getElementById('tipo-j-activo').value = tipo.activo ? 'true' : 'false';

        // Reglas Avanzadas
        document.getElementById('tipo-j-min-dias').value = tipo.min_dias || 1;
        document.getElementById('tipo-j-max-dias').value = tipo.max_dias || '';
        document.getElementById('tipo-j-frecuencia').value = tipo.frecuencia_anual || '';
        document.getElementById('tipo-j-feriados').value = tipo.sobreescribe_feriados ? 'true' : 'false';
        document.getElementById('tipo-j-sindical').value = tipo.es_horas_sindicales ? 'true' : 'false';

        // [NEW] Permisos Parciales y Deuda
        document.getElementById('tipo-j-parcial').value = tipo.es_por_horas ? 'true' : 'false';
        document.getElementById('tipo-j-deuda').value = tipo.genera_deuda_horaria ? 'true' : 'false';

    } else {
        title.innerText = 'Nuevo Tipo de Justificación';
        document.getElementById('tipo-j-id').value = '';
        document.getElementById('tipo-j-nomenclatura').value = '';
        document.getElementById('tipo-j-pagador').value = 'Empleador';
        document.getElementById('tipo-j-dias-defecto').value = '';

        // Default Reglas Avanzadas
        document.getElementById('tipo-j-min-dias').value = 1;
        document.getElementById('tipo-j-max-dias').value = '';
        document.getElementById('tipo-j-frecuencia').value = '';
        document.getElementById('tipo-j-feriados').value = 'false';
        document.getElementById('tipo-j-sindical').value = 'false';

        // [NEW] Permisos Parciales y Deuda
        document.getElementById('tipo-j-parcial').value = 'false';
        document.getElementById('tipo-j-deuda').value = 'false';
    }

    modal.style.display = 'flex';
}

function closeModalTipoJ() {
    document.getElementById('modal-tipo-justificacion').style.display = 'none';
}

async function saveTipoJustificacion() {
    const id = document.getElementById('tipo-j-id').value;
    const minDias = document.getElementById('tipo-j-min-dias').value;
    const maxDias = document.getElementById('tipo-j-max-dias').value;
    const frecuencia = document.getElementById('tipo-j-frecuencia').value;
    const diasDefectoVal = document.getElementById('tipo-j-dias-defecto').value;

    const body = {
        nombre: document.getElementById('tipo-j-nombre').value,
        nomenclatura: document.getElementById('tipo-j-nomenclatura').value,
        descripcion: document.getElementById('tipo-j-descripcion').value,
        con_goce_sueldo: document.getElementById('tipo-j-goce').value === 'true',

        // Mapeo UI -> Backend
        dias_hábiles: document.getElementById('tipo-j-periodo').value === 'true', // Legacy field validation
        dias_corridos: document.getElementById('tipo-j-periodo').value === 'false', // Inverso de dias_habiles en UI antigua

        pagador: document.getElementById('tipo-j-pagador').value,
        dias_defecto: diasDefectoVal ? parseInt(diasDefectoVal) : null,
        activo: document.getElementById('tipo-j-activo').value === 'true',

        // Reglas Avanzadas
        min_dias: minDias ? parseInt(minDias) : 1,
        max_dias: maxDias ? parseInt(maxDias) : null,
        frecuencia_anual: frecuencia ? parseInt(frecuencia) : null,
        sobreescribe_feriados: document.getElementById('tipo-j-feriados').value === 'true',
        es_horas_sindicales: document.getElementById('tipo-j-sindical').value === 'true',

        // Mapeo Goce -> Descuenta
        descuenta_remuneracion: document.getElementById('tipo-j-goce').value === 'false',

        // [NEW] Permisos Parciales y Deuda
        es_por_horas: document.getElementById('tipo-j-parcial').value === 'true',
        genera_deuda_horaria: document.getElementById('tipo-j-deuda').value === 'true'
    };

    const method = id ? 'PUT' : 'POST';
    const url = id ? `${API_CONFIG}justificaciones/tipos/${id}/` : `${API_CONFIG}justificaciones/tipos/`;

    try {
        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (!response.ok) throw new Error("Error al guardar");

        showToast("Configuración guardada", "success");
        closeModalTipoJ();
        loadTiposJustificacion();
    } catch (error) {
        alert(error.message);
    }
}

function editTipoJ(id) {
    const tipo = tiposJustificacionList.find(t => t.id === id);
    if (tipo) openModalTipoJ(tipo);
}

function confirmDeleteTipoJ(id) {
    if (confirm("¿Eliminar este tipo de justificación?")) {
        deleteTipoJ(id);
    }
}

async function deleteTipoJ(id) {
    try {
        const response = await fetch(`${API_CONFIG}justificaciones/tipos/${id}/`, { method: 'DELETE' });
        if (!response.ok) throw new Error("No se puede eliminar (posiblemente en uso)");
        showToast("Tipo eliminado", "success");
        loadTiposJustificacion();
    } catch (error) {
        alert(error.message);
    }
}

// ==========================================
// PAGADORES: LÓGICA Y UI [NEW]
// ==========================================
async function loadPagadores() {
    try {
        const response = await fetch(`${API_CONFIG}pagadores/`);
        if (!response.ok) throw new Error("Error cargando pagadores");
        pagadoresList = await response.json();

        // Poblar selects
        const select = document.getElementById('tipo-j-pagador');
        if (select) {
            select.innerHTML = '<option value="">Seleccione...</option>' +
                pagadoresList.map(p => `<option value="${p.nombre}">${p.nombre}</option>`).join('');
        }
    } catch (error) {
        console.error(error);
    }
}

window.openModalGestionPagadores = function () {
    renderPagadoresList();
    document.getElementById('modal-gestion-pagadores').style.display = 'flex';
}

window.closeModalGestionPagadores = function () {
    document.getElementById('modal-gestion-pagadores').style.display = 'none';
    loadPagadores(); // Recargar select al cerrar por si hubo cambios
}

function renderPagadoresList() {
    const body = document.getElementById('pagadores-list-body');
    if (!body) return;

    body.innerHTML = pagadoresList.map(p => `
        <tr>
            <td class="small fw-bold">${p.nombre}</td>
            <td><span class="badge ${p.activo ? 'bg-success' : 'bg-secondary'}">${p.activo ? 'Activo' : 'Inactivo'}</span></td>
            <td class="text-end">
                <button class="btn btn-sm text-danger" onclick="togglePagador(${p.id}, ${!p.activo})" title="Cambiar Estado">
                    <i class="bi bi-power"></i>
                </button>
            </td>
        </tr>
    `).join('') || '<tr><td colspan="3" class="text-center text-muted">No hay pagadores extra.</td></tr>';
}

window.addPagador = async function () {
    const input = document.getElementById('new-pagador-nombre');
    const nombre = input.value.trim();
    if (!nombre) return;

    try {
        const response = await fetch(`${API_CONFIG}pagadores/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre, activo: true })
        });
        if (!response.ok) throw new Error("Error al añadir");

        input.value = '';
        showToast("Pagador añadido", "success");
        await loadPagadores();
        renderPagadoresList();
    } catch (error) {
        alert(error.message);
    }
}

window.togglePagador = async function (id, nuevoEstado) {
    const p = pagadoresList.find(x => x.id === id);
    if (!p) return;

    try {
        const response = await fetch(`${API_CONFIG}pagadores/${id}/`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre: p.nombre, activo: nuevoEstado })
        });
        if (!response.ok) throw new Error("Error al actualizar");

        await loadPagadores();
        renderPagadoresList();
    } catch (error) {
        alert(error.message);
    }
}

// ==========================================
// AJUSTES GLOBALES: NOTIFICACIONES [NEW]
// ==========================================
async function loadEmailSettings() {
    const emailRRHH = document.getElementById('email-notificaciones-rrhh');
    if (emailRRHH) {
        try {
            const res = await fetch(`${API_CONFIG}ajustes/email_notificaciones_rrhh/`);
            if (res.ok) {
                const data = await res.json();
                emailRRHH.value = data || '';
            }
        } catch (e) {
            console.error("Error cargando email de notificaciones", e);
        }
    }
}

window.saveGlobalAjustes = async function () {
    const emailRRHH = document.getElementById('email-notificaciones-rrhh');
    if (!emailRRHH) return;

    const btn = document.querySelector('#tab-correo .btn-primary');
    if (btn) btn.disabled = true;

    try {
        const response = await fetch(`${API_CONFIG}ajustes/email_notificaciones_rrhh/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(emailRRHH.value.trim())
        });

        if (!response.ok) throw new Error("Error al guardar");

        showToast("Proceso Exitoso", "success");
    } catch (e) {
        alert("Error: " + e.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

window.loadAreaNotificaciones = async function () {
    const tbody = document.getElementById('tabla-notificaciones-areas');
    if (!tbody) return;

    try {
        const res = await fetch(`${API_CONFIG}notificaciones_areas/`);
        if (!res.ok) throw new Error("Error cargando configuración por área");
        
        const areas = await res.json();
        
        if (areas.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted py-3">No hay configuraciones por área. Se usará el correo global para todas las áreas.</td></tr>';
            return;
        }

        tbody.innerHTML = areas.map(a => `
            <tr>
                <td class="fw-bold">${a.area}</td>
                <td><i class="bi bi-envelope-at small text-muted me-2"></i> ${a.emails}</td>
                <td class="text-end">
                    <button class="btn btn-sm btn-outline-primary me-1" onclick="editAreaNotificaciones('${a.area}', '${a.emails}')" title="Editar">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteAreaNotificaciones('${a.area}')" title="Eliminar">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            </tr>
        `).join('');

    } catch (e) {
        console.error("Error al cargar configuraciones de áreas", e);
        tbody.innerHTML = '<tr><td colspan="3" class="text-center text-danger py-3">Error al cargar configuraciones.</td></tr>';
    }
}

window.saveAreaNotificaciones = async function () {
    const areaInput = document.getElementById('notif-area-nombre');
    const emailsInput = document.getElementById('notif-area-emails');
    
    if (!areaInput || !emailsInput) return;
    
    const area = areaInput.value.trim().toUpperCase();
    const emails = emailsInput.value.trim();
    
    if (!area || !emails) {
        showToast("Debes ingresar el área y los correos.", "error");
        return;
    }
    
    try {
        const res = await fetch(`${API_CONFIG}notificaciones_areas/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ area, emails })
        });
        
        if (!res.ok) throw new Error("Error al guardar configuración de área.");
        
        showToast(`Notificaciones para área ${area} guardadas.`, "success");
        areaInput.value = '';
        emailsInput.value = '';
        loadAreaNotificaciones();
        
    } catch (e) {
        alert("Error: " + e.message);
    }
}

window.editAreaNotificaciones = function(area, emails) {
    const areaInput = document.getElementById('notif-area-nombre');
    const emailsInput = document.getElementById('notif-area-emails');
    if (areaInput && emailsInput) {
        areaInput.value = area;
        emailsInput.value = emails;
        emailsInput.focus();
    }
}

window.deleteAreaNotificaciones = async function (area) {
    if (!confirm(`¿Eliminar notificaciones para el área ${area}?`)) return;
    
    try {
        const res = await fetch(`${API_CONFIG}notificaciones_areas/${encodeURIComponent(area)}/`, {
            method: 'DELETE'
        });
        
        if (!res.ok) throw new Error("Error al eliminar");
        
        showToast("Configuración eliminada.", "success");
        loadAreaNotificaciones();
    } catch (e) {
        alert("Error: " + e.message);
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

// ==========================================
// ROBOT BIOALBA LOGS [NEW]
// ==========================================
window.loadRobotSyncLogs = async function() {
    const tbody = document.getElementById('table-robot-logs');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4"><i class="spinner-border spinner-border-sm text-primary"></i> Cargando logs del robot...</td></tr>';
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout

    try {
        const response = await fetch('/api/sync/logs/', { signal: controller.signal });
        clearTimeout(timeoutId);
        
        if (!response.ok) throw new Error("Error obteniendo logs de sincronización");
        const logs = await response.json();
        
        if (!logs || logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 bg-light text-muted">No existen registros de ejecución.</td></tr>';
            return;
        }

        tbody.innerHTML = logs.map(log => {
            const errores = log.errores || 0;
            const isError = errores > 0;
            const badgeClass = isError ? 'bg-danger' : 'bg-success';
            const statusText = isError ? 'Completado con Errores' : 'Exitoso';
            const duracion = log.duracion_segundos != null ? parseFloat(log.duracion_segundos).toFixed(2) : '0.00';
            
            // Asegurar formato ISO para navegadores estrictos
            const rawFecha = log.fecha_inicio || '';
            const isoFecha = rawFecha.replace(' ', 'T');
            const formattedDate = isoFecha ? new Date(isoFecha + (isoFecha.includes('Z') ? '' : 'Z')).toLocaleString('es-CL') : 'N/A';

            return `
                <tr>
                    <td class="small text-muted text-center" style="width: 60px;">#${log.id}</td>
                    <td class="fw-bold">${formattedDate}</td>
                    <td><span class="badge bg-secondary">${log.tipo_sync || 'COMPLETA'}</span></td>
                    <td class="text-center fw-bold text-success">${log.marcaciones_nuevas || log.dias_recalculados || 0}</td>
                    <td class="text-center ${errores > 0 ? 'fw-bold text-danger' : 'text-muted'}">${errores}</td>
                    <td>${duracion}s</td>
                    <td>
                        <span class="badge ${badgeClass} mb-1">${statusText}</span>
                        ${log.detalle ? `<div class="small text-muted border-start border-3 border-info ps-2 mt-1" style="max-height: 60px; overflow-y: auto; font-size: 0.7rem; white-space: pre-wrap;">${typeof log.detalle === 'object' ? JSON.stringify(log.detalle, null, 2) : log.detalle}</div>` : ''}
                    </td>
                </tr>
            `;
        }).join('');

    } catch (e) {
        console.error(e);
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-danger fw-bold"><i class="bi bi-exclamation-triangle-fill"></i> Error: ${e.message}</td></tr>`;
    }
}

// ==========================================
// AJUSTES DEL SISTEMA [NEW]
// ==========================================
window.loadAjustesSistema = async function() {
    try {
        const response = await fetch(`${API_CONFIG}ajustes/`);
        if (!response.ok) throw new Error("Error obteniendo ajustes del sistema");
        const ajustes = await response.json();

        // Mapeo de clave de DB a ID de input
        const mapIds = {
            'limite_contratos_temporales': 'ajuste-limite-contratos',
            'vencimiento_dias_alerta': 'ajuste-dias-alerta',
            'dias_alerta_bloqueante': 'ajuste-dias-bloqueante',
            'dia_cierre_rrhh': 'ajuste-dia-cierre'
        };

        // Rellenar valores
        ajustes.forEach(a => {
            const inputId = mapIds[a.clave];
            if (inputId) {
                const el = document.getElementById(inputId);
                if (el) el.value = a.valor;
            }
        });

    } catch (e) {
        console.error("Error cargando ajustes del sistema", e);
        showToast("Error al cargar ajustes numéricos", "error");
    }
};

window.saveAjusteSistema = async function(clave, inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;

    const valor = input.value.trim();
    if (!valor) {
        showToast("El valor no puede estar vacío", "error");
        return;
    }

    // El backend espera int, así que enviaremos como número o string validable
    try {
        const response = await fetch(`${API_CONFIG}ajustes/${clave}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(valor) // FastAPI `valor: str = Body(...)` lo recibirá
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Error al guardar el ajuste");
        }

        showToast(`Ajuste actualizado correctamente`, "success");
    } catch (e) {
        console.error("Error guardando ajuste:", e);
        showToast(e.message, "error");
    }
};

// ==========================================
// CATÁLOGO DE ÁREAS Y ALIAS (AUDITORÍA)
// ==========================================
window.cargarCatalogoAreas = async function() {
    const container = document.getElementById('areas-catalogo-container');
    if (!container) return;

    container.innerHTML = `
        <div class="text-center py-5">
            <div class="spinner-border text-primary" role="status"></div>
            <div class="text-muted mt-2">Cargando catálogo...</div>
        </div>
    `;

    try {
        const response = await fetch('/api/configuracion/areas/');
        if (!response.ok) throw new Error("Error obteniendo catálogo de áreas");
        const areas = await response.json();

        if (!areas || areas.length === 0) {
            container.innerHTML = '<div class="col-12"><div class="alert alert-info border-0 shadow-sm"><i class="bi bi-info-circle me-2"></i> No hay áreas registradas.</div></div>';
            return;
        }

        container.innerHTML = areas.map(area => {
            const aliasHtml = area.alias.length > 0 
                ? area.alias.map(al => `
                    <div class="d-flex justify-content-between align-items-center bg-white p-2 mb-2 rounded border border-light shadow-sm" id="alias-row-${al.id}">
                        <div class="text-danger fw-bold small"><i class="bi bi-exclamation-triangle-fill text-warning me-1"></i> ${al.alias}</div>
                        <button class="btn btn-sm btn-outline-danger border-0" onclick="confirmDeleteAlias(${al.id}, '${al.alias}')" title="Desvincular Error">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                  `).join('')
                : `<div class="text-muted small text-center font-monospace py-2 bg-light rounded"><i class="bi bi-check-circle text-success me-1"></i> Área Limpia. Sin errores redirigidos.</div>`;

            const badgeCls = area.alias.length > 0 ? "bg-danger" : "bg-success";
            
            return `
                <div class="col-md-6 col-lg-4">
                    <div class="card h-100 border-0 shadow-sm">
                        <div class="card-header bg-white border-bottom border-light d-flex justify-content-between align-items-center py-3">
                            <h6 class="mb-0 fw-bold text-dark"><i class="bi bi-building me-2 text-primary"></i>${area.nombre}</h6>
                            <span class="badge ${badgeCls} rounded-pill">${area.alias.length} errores</span>
                        </div>
                        <div class="card-body p-3 bg-light" style="max-height: 250px; overflow-y: auto;">
                            ${aliasHtml}
                        </div>
                    </div>
                </div>
            `;
        }).join('');
        
    } catch (error) {
        console.error(error);
        container.innerHTML = `<div class="col-12"><div class="alert alert-danger"><i class="bi bi-exclamation-octagon me-2"></i> ${error.message}</div></div>`;
    }
};

window.confirmDeleteAlias = function(aliasId, aliasNombre) {
    if(typeof Swal !== 'undefined') {
        Swal.fire({
            title: '¿Desvincular Alias?',
            html: `Se desvinculará el texto erróneo <b>"${aliasNombre}"</b>.<br><br><i>Nota: Si el reloj control vuelve a enviar este texto, el Guardián detendrá la sincronización nuevamente para pedir revisión.</i>`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#6c757d',
            confirmButtonText: 'Sí, desvincular',
            cancelButtonText: 'Cancelar'
        }).then((result) => {
            if (result.isConfirmed) {
                deleteAlias(aliasId);
            }
        });
    } else {
        if(confirm(`¿Desvincular el texto erróneo "${aliasNombre}"?\n\nNota: Si el reloj control vuelve a enviar este texto, el Guardián detendrá la sincronización nuevamente para pedir revisión.`)) {
            deleteAlias(aliasId);
        }
    }
};

window.deleteAlias = async function(aliasId) {
    try {
        const response = await fetch(`/api/configuracion/areas/alias/${aliasId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error("Error al desvincular el alias");
        
        // Remove optimistic DOM Element just in case, but usually we just reload
        const row = document.getElementById(`alias-row-${aliasId}`);
        if(row) {
            row.style.opacity = '0.5';
            setTimeout(() => {
                cargarCatalogoAreas(); // Reload the catalog to update badges
            }, 300);
        } else {
            cargarCatalogoAreas();
        }
        
        if(typeof showToast === 'function') {
            showToast("Alias desvinculado exitosamente.", "success");
        } else if(typeof Swal !== 'undefined') {
            Swal.fire('Desvinculado!', 'El alias ha sido eliminado.', 'success');
        }
    } catch(error) {
        console.error(error);
        if(typeof showToast === 'function') {
            showToast(error.message, "error");
        } else {
            alert(error.message);
        }
    }
};
