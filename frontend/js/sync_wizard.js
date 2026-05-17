/**
 * Universal Synchronization Wizard
 * Centraliza la validación de Áreas, Cargos, Géneros, Turnos y Bonos.
 */

window._wizardState = {
    currentStep: 1,
    data: null, 
    turnosDisponibles: [],
    bonosDisponibles: [],
    preAsignacionesTurnos: {},
    preAsignacionesBonos: {},
    resoluciones: {
        areas: {},    // area_bioalba -> area_local / _NEW_ / _IGNORE_
        cargos: {},   // cargo_bioalba -> cargo_local / _NEW_ / _IGNORE_
        generos: [],  // array de nombres de géneros
        turnos: {},   // area_local_name -> turno_id
        bonos: {}     // area_local_name -> [bono_id1, bono_id2]
    }
};

window.closeSyncWizard = function() {
    const modalEl = document.getElementById('modal-sync-wizard');
    if (modalEl) {
        const modalInstance = bootstrap.Modal.getInstance(modalEl);
        if (modalInstance) {
            modalInstance.hide();
        }
    }
};

window.startSyncWizard = function(data) {
    console.log("⚡ Iniciando Universal Sync Wizard...", data);
    
    // Si no requiere confirmación, es porque no hay nuevas áreas ni cargos, 
    // pero de todas formas queremos mostrar el paso 4 y 5 si es sincronización inicial.
    // Sin embargo, el Wizard ahora asume todo el control.
    
    window._wizardState.data = data;
    window._wizardState.currentStep = 1;
    window._wizardState.resoluciones = {
        areas: {},
        cargos: {},
        generos: data.nuevos_generos || [],
        turnos: {},
        bonos: {}
    };

    // Pre-poblar áreas con _NEW_ por defecto (para áreas nuevas detectadas)
    if (data.nuevas_areas) {
        data.nuevas_areas.forEach(area => {
            window._wizardState.resoluciones.areas[area] = "_NEW_";
        });
    }

    // Ocultar todos los steps y mostrar el 1
    updateWizardUI();

    const wizardModal = new bootstrap.Modal(document.getElementById('modal-sync-wizard'));
    wizardModal.show();
};

function updateWizardUI() {
    const step = window._wizardState.currentStep;
    
    // Actualizar Stepper Visual
    document.querySelectorAll('.step-indicator').forEach((el, idx) => {
        if (idx + 1 === step) {
            el.classList.add('active');
            el.classList.remove('completed');
        } else if (idx + 1 < step) {
            el.classList.add('completed');
            el.classList.remove('active');
        } else {
            el.classList.remove('active', 'completed');
        }
    });

    // Ocultar/Mostrar Paneles
    for (let i = 1; i <= 5; i++) {
        const pane = document.getElementById(`wizard-step-${i}`);
        if (pane) {
            if (i === step) pane.classList.remove('d-none');
            else pane.classList.add('d-none');
        }
    }

    // Botones
    document.getElementById('btn-wizard-prev').disabled = (step === 1);
    
    const btnNext = document.getElementById('btn-wizard-next');
    const btnFinish = document.getElementById('btn-wizard-finish');
    
    if (step === 5) {
        btnNext.classList.add('d-none');
        btnFinish.classList.remove('d-none');
    } else {
        btnNext.classList.remove('d-none');
        btnFinish.classList.add('d-none');
    }

    // Renderizar Contenido Específico
    if (step === 1) renderWizardStep1();
    if (step === 2) renderWizardStep2();
    if (step === 3) fetchAndRenderWizardStep3();
    if (step === 4) fetchAndRenderWizardStep4();
    if (step === 5) fetchAndRenderWizardStep5();
}

window.wizardNextStep = function() {
    // Validar paso actual antes de avanzar
    if (window._wizardState.currentStep === 1) {
        if (!guardarSeleccionesPaso1()) return;
    }
    if (window._wizardState.currentStep === 2) {
        if (!guardarSeleccionesPaso2()) return;
    }
    if (window._wizardState.currentStep === 3) {
        if (!guardarSeleccionesPaso3()) return;
    }
    if (window._wizardState.currentStep === 4) {
        if (!guardarSeleccionesPaso4()) return;
        finalizeWizardAndPreview();
        return;
    }

    if (window._wizardState.currentStep < 5) {
        window._wizardState.currentStep++;
        updateWizardUI();
    }
};

window.wizardPrevStep = function() {
    if (window._wizardState.currentStep > 1) {
        window._wizardState.currentStep--;
        updateWizardUI();
    }
};

// ==========================================
// PASO 1: ÁREAS
// ==========================================
function renderWizardStep1() {
    const tbody = document.getElementById('tbody-wizard-areas');
    tbody.innerHTML = '';
    
    const data = window._wizardState.data;
    const nuevasAreas = data.nuevas_areas || [];
    const conteoNuevas = data.nuevas_areas_conteo || {};
    const areasConocidas = data.areas_conocidas || [];
    
    if (nuevasAreas.length === 0 && areasConocidas.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">No se detectaron áreas nuevas para mapear.</td></tr>`;
        return;
    }

    // Nuevas Áreas
    if (nuevasAreas.length > 0) {
        const trTitle = document.createElement('tr');
        trTitle.innerHTML = `<td colspan="4" class="bg-light text-warning fw-bold"><i class="bi bi-shield-exclamation me-2"></i>Áreas Desconocidas (Nuevas)</td>`;
        tbody.appendChild(trTitle);

        nuevasAreas.forEach((area, idx) => {
            const conteo = conteoNuevas[area] || 0;
            const tr = document.createElement('tr');
            
            // Ver si ya tiene resolución guardada
            const resolucion = window._wizardState.resoluciones.areas[area];
            const isImport = resolucion !== "_IGNORE_";
            const customName = (resolucion && resolucion !== "_NEW_" && resolucion !== "_IGNORE_") ? resolucion : "";

            tr.innerHTML = `
                <td class="text-center align-middle">
                    <input type="checkbox" class="form-check-input check-area" id="wiz-chk-area-${idx}" data-area="${area}" ${isImport ? 'checked' : ''}>
                </td>
                <td class="fw-bold align-middle">${area}</td>
                <td class="text-center align-middle">
                    ${conteo > 0 ? `<span class="badge bg-secondary rounded-pill">${conteo} emp</span>` : `<span class="text-muted small">-</span>`}
                </td>
                <td class="align-middle">
                    <input type="text" class="form-control form-control-sm input-area-name" id="wiz-inp-area-${idx}" 
                           placeholder="Nombre final (dejar vacío para usar el mismo)" 
                           value="${customName}" ${!isImport ? 'disabled' : ''}>
                </td>
            `;
            
            const chk = tr.querySelector('.check-area');
            const inp = tr.querySelector('.input-area-name');
            chk.addEventListener('change', (e) => {
                inp.disabled = !e.target.checked;
            });

            tbody.appendChild(tr);
        });
    }

    // Áreas Conocidas (Informático)
    if (areasConocidas.length > 0) {
        const trTitle = document.createElement('tr');
        trTitle.innerHTML = `<td colspan="4" class="bg-light text-success fw-bold"><i class="bi bi-check-circle me-2"></i>Áreas Ya Conocidas</td>`;
        tbody.appendChild(trTitle);

        areasConocidas.forEach((area) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="text-center align-middle"><i class="bi bi-check2 text-success"></i></td>
                <td class="fw-bold align-middle">${area}</td>
                <td class="text-center align-middle">-</td>
                <td class="align-middle text-muted small">Mapeo Automático</td>
            `;
            tbody.appendChild(tr);
        });
    }
}

function guardarSeleccionesPaso1() {
    const data = window._wizardState.data;
    const nuevasAreas = data.nuevas_areas || [];
    
    // Recorrer los checkboxes de áreas nuevas
    nuevasAreas.forEach((area, idx) => {
        const chk = document.getElementById(`wiz-chk-area-${idx}`);
        const inp = document.getElementById(`wiz-inp-area-${idx}`);
        
        if (chk && chk.checked) {
            let finalName = inp.value.trim();
            if (finalName === "") finalName = area; // Usa el mismo si está en blanco (significa _NEW_ pero con el mismo nombre)
            window._wizardState.resoluciones.areas[area] = finalName;
        } else if (chk) {
            window._wizardState.resoluciones.areas[area] = "_IGNORE_";
        }
    });
    return true;
}

// ==========================================
// PASO 2: CARGOS Y GÉNEROS
// ==========================================
function renderWizardStep2() {
    renderWizardGeneros();
    const tbody = document.getElementById('tbody-wizard-cargos');
    tbody.innerHTML = '';
    
    const data = window._wizardState.data;
    const nuevosCargos = data.nuevos_cargos || [];
    const cargosConocidos = data.cargos_conocidos || [];
    
    if (nuevosCargos.length === 0 && cargosConocidos.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">No se detectaron cargos nuevos para mapear.</td></tr>`;
        return;
    }

    // Nuevos Cargos
    if (nuevosCargos.length > 0) {
        const trTitle = document.createElement('tr');
        trTitle.innerHTML = `<td colspan="4" class="bg-light text-warning fw-bold"><i class="bi bi-briefcase me-2"></i>Cargos Desconocidos</td>`;
        tbody.appendChild(trTitle);

        nuevosCargos.forEach((cargo, idx) => {
            const resolucion = window._wizardState.resoluciones.cargos[cargo];
            // Por defecto, marcamos para importar (a menos que ya esté explícitamente en _IGNORE_)
            const isImport = resolucion !== "_IGNORE_";
            const customName = (resolucion && resolucion !== "_NEW_" && resolucion !== "_IGNORE_") ? resolucion : "";

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="text-center align-middle">
                    <input type="checkbox" class="form-check-input check-cargo" id="wiz-chk-cargo-${idx}" data-cargo="${cargo}" ${isImport ? 'checked' : ''}>
                </td>
                <td class="fw-bold align-middle">${cargo}</td>
                <td class="align-middle">
                    <input type="text" class="form-control form-control-sm input-cargo-name" id="wiz-inp-cargo-${idx}" 
                           placeholder="Nombre final (dejar vacío para usar el mismo)" 
                           value="${customName}" ${!isImport ? 'disabled' : ''}>
                </td>
            `;
            
            const chk = tr.querySelector('.check-cargo');
            const inp = tr.querySelector('.input-cargo-name');
            chk.addEventListener('change', (e) => {
                inp.disabled = !e.target.checked;
            });

            tbody.appendChild(tr);
        });
    }

    // Cargos Conocidos
    if (cargosConocidos.length > 0) {
        const trTitle = document.createElement('tr');
        trTitle.innerHTML = `<td colspan="4" class="bg-light text-success fw-bold"><i class="bi bi-check-circle me-2"></i>Cargos Ya Conocidos</td>`;
        tbody.appendChild(trTitle);

        cargosConocidos.forEach((cargo) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="text-center align-middle"><i class="bi bi-check2 text-success"></i></td>
                <td class="fw-bold align-middle">${cargo}</td>
                <td class="align-middle text-muted small">Mapeo Automático</td>
            `;
            tbody.appendChild(tr);
        });
    }
}

function guardarSeleccionesPaso2() {
    const data = window._wizardState.data;
    const nuevosCargos = data.nuevos_cargos || [];
    
    nuevosCargos.forEach((cargo, idx) => {
        const chk = document.getElementById(`wiz-chk-cargo-${idx}`);
        const inp = document.getElementById(`wiz-inp-cargo-${idx}`);
        
        if (chk && chk.checked) {
            let finalName = inp.value.trim();
            if (finalName === "") finalName = cargo;
            window._wizardState.resoluciones.cargos[cargo] = finalName;
        } else if (chk) {
            window._wizardState.resoluciones.cargos[cargo] = "_IGNORE_";
        }
    });
    return true;
}

// ==========================================
// GÉNEROS (Parte del Paso 2)
// ==========================================
function renderWizardGeneros() {
    const container = document.getElementById('tbody-wizard-generos');
    container.innerHTML = '';
    
    const generos = window._wizardState.data.nuevos_generos || [];
    
    if (generos.length === 0) {
        container.innerHTML = `<tr><td colspan="2" class="text-muted text-center py-3">No hay géneros nuevos que registrar.</td></tr>`;
        return;
    }

    container.innerHTML = generos.map(g => `
        <tr>
            <td class="fw-bold align-middle">${g}</td>
            <td class="align-middle text-muted small">Se agregará automáticamente</td>
        </tr>
    `).join('');
}

// ==========================================
// Utils: Obtener lista consolidada de áreas (Nuevas resueltas + Conocidas)
// ==========================================
function getConsolidatedAreas() {
    const areasLocalNames = new Set();
    
    // Areas Conocidas
    const conocidas = window._wizardState.data.areas_conocidas || [];
    conocidas.forEach(a => areasLocalNames.add(a));
    
    // Areas Nuevas Resueltas (que no sean _IGNORE_)
    const nuevas = window._wizardState.data.nuevas_areas || [];
    nuevas.forEach(a => {
        const res = window._wizardState.resoluciones.areas[a];
        if (res && res !== "_IGNORE_") {
            areasLocalNames.add(res === "_NEW_" ? a : res);
        }
    });
    
    return Array.from(areasLocalNames);
}

// ==========================================
// PASO 3: TURNOS
// ==========================================
async function fetchAndRenderWizardStep3() {
    const tbody = document.getElementById('tbody-wizard-turnos');
    tbody.innerHTML = `<tr><td colspan="2" class="text-center py-4"><div class="spinner-border text-primary"></div></td></tr>`;
    
    const areasList = getConsolidatedAreas();

    try {
        const response = await fetch(`${API_BASE_URL}/sync/wizard/turnos/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({ areas: areasList })
        });
        
        if (!response.ok) throw new Error("Error obteniendo turnos");
        const res = await response.json();
        
        window._wizardState.turnosDisponibles = res.turnos || [];
        window._wizardState.preAsignacionesTurnos = res.pre_asignaciones || {};

        tbody.innerHTML = '';
        
        if (areasList.length === 0) {
            tbody.innerHTML = `<tr><td colspan="2" class="text-center text-muted">No hay áreas seleccionadas.</td></tr>`;
            return;
        }

        // Crear options HTML
        const turnosOptionsHTML = window._wizardState.turnosDisponibles.map(t => {
            const isDef = t.es_default ? ' (Por Defecto)' : '';
            return `<option value="${t.id}">${t.nombre}${isDef}</option>`;
        }).join('');

        areasList.forEach((area, idx) => {
            // Ver si ya lo teníamos guardado en memoria en esta sesión, si no usar la pre-asignación de DB
            let selectedTurnoId = window._wizardState.resoluciones.turnos[area] || window._wizardState.preAsignacionesTurnos[area] || "";
            
            // Si sigue vacío y hay turno por defecto, seleccionarlo
            if (!selectedTurnoId) {
                const defTurno = window._wizardState.turnosDisponibles.find(t => t.es_default);
                if (defTurno) selectedTurnoId = defTurno.id;
            }

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="fw-bold align-middle">${area}</td>
                <td class="align-middle">
                    <select class="form-select form-select-sm wiz-sel-turno" data-area="${area}" id="wiz-sel-turno-${idx}">
                        <option value="">-- Sin Turno Fijo (Rotativo) --</option>
                        ${turnosOptionsHTML}
                    </select>
                </td>
            `;
            tbody.appendChild(tr);

            // Asignar valor seleccionado
            if (selectedTurnoId) {
                const sel = tr.querySelector(`#wiz-sel-turno-${idx}`);
                sel.value = selectedTurnoId;
            }
        });

    } catch (e) {
        console.error(e);
        tbody.innerHTML = `<tr><td colspan="2" class="text-danger text-center">Error al cargar turnos.</td></tr>`;
    }
}

function guardarSeleccionesPaso3() {
    const areasList = getConsolidatedAreas();
    areasList.forEach((area, idx) => {
        const sel = document.getElementById(`wiz-sel-turno-${idx}`);
        if (sel) {
            window._wizardState.resoluciones.turnos[area] = sel.value ? parseInt(sel.value) : null;
        }
    });
    return true;
}

// ==========================================
// PASO 4: BONOS
// ==========================================
async function fetchAndRenderWizardStep4() {
    const tbody = document.getElementById('tbody-wizard-bonos');
    tbody.innerHTML = `<tr><td colspan="2" class="text-center py-4"><div class="spinner-border text-primary"></div></td></tr>`;
    
    const areasList = getConsolidatedAreas();

    try {
        const response = await fetch(`${API_BASE_URL}/sync/wizard/bonos/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({ areas: areasList })
        });
        
        if (!response.ok) throw new Error("Error obteniendo bonos");
        const res = await response.json();
        
        window._wizardState.bonosDisponibles = res.bonos || [];
        window._wizardState.preAsignacionesBonos = res.pre_asignaciones || {};

        tbody.innerHTML = '';
        
        if (areasList.length === 0) {
            tbody.innerHTML = `<tr><td colspan="2" class="text-center text-muted">No hay áreas seleccionadas.</td></tr>`;
            return;
        }

        if (window._wizardState.bonosDisponibles.length === 0) {
            tbody.innerHTML = `<tr><td colspan="2" class="text-center text-muted">No hay bonos creados en el catálogo.</td></tr>`;
            return;
        }

        areasList.forEach((area, idx) => {
            // Recuperar seleccionados previamente
            let selectedBonosIds = window._wizardState.resoluciones.bonos[area] || window._wizardState.preAsignacionesBonos[area] || [];

            // Construir checkboxes de bonos
            const bonosCheckboxes = window._wizardState.bonosDisponibles.map(b => {
                const checked = selectedBonosIds.includes(b.id) ? 'checked' : '';
                return `
                    <div class="form-check form-check-inline">
                        <input class="form-check-input wiz-chk-bono" type="checkbox" id="wiz-bono-${idx}-${b.id}" data-area="${area}" value="${b.id}" ${checked}>
                        <label class="form-check-label small" for="wiz-bono-${idx}-${b.id}">${b.nombre}</label>
                    </div>
                `;
            }).join('');

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="fw-bold align-middle">${area}</td>
                <td class="align-middle">
                    <div class="d-flex flex-wrap gap-2">
                        ${bonosCheckboxes}
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });

    } catch (e) {
        console.error(e);
        tbody.innerHTML = `<tr><td colspan="2" class="text-danger text-center">Error al cargar bonos.</td></tr>`;
    }
}

function guardarSeleccionesPaso4() {
    const areasList = getConsolidatedAreas();
    areasList.forEach((area, idx) => {
        const checkboxes = document.querySelectorAll(`.wiz-chk-bono[data-area="${area}"]`);
        const bonosIds = [];
        checkboxes.forEach(chk => {
            if (chk.checked) bonosIds.push(parseInt(chk.value));
        });
        window._wizardState.resoluciones.bonos[area] = bonosIds;
    });
    return true;
}

// ==========================================
// PASO 5: EMPLEADOS (PREVIEW MOCK)
// ==========================================
async function fetchAndRenderWizardStep5() {
    const listContainer = document.getElementById('wizard-empleados-list');
    const counter = document.getElementById('wizard-emp-counter');
    
    if (listContainer) {
        listContainer.innerHTML = `
            <div class="text-center p-5">
                <span class="spinner-border text-primary"></span>
                <h5 class="mt-3">Generando previsualización...</h5>
            </div>
        `;
    }

    try {
        const areasList = getConsolidatedAreas();
        const ignoredCargos = [];
        for (const [cargo, resolucion] of Object.entries(window._wizardState.resoluciones.cargos)) {
            if (resolucion === "_IGNORE_") {
                ignoredCargos.push(cargo);
            }
        }

        const requestBody = {
            areas: areasList,
            ignored_cargos: ignoredCargos
        };

        const response = await fetch(`${API_BASE_URL}/sync/empleados/preview/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) throw new Error("Error en preview");
        const res = await response.json();
        const empList = res.empleados || [];

        if (counter) counter.textContent = `${empList.length} listos`;
        
        if (empList.length === 0) {
            listContainer.innerHTML = `<div class="alert alert-warning m-3">No se encontraron empleados para sincronizar con la configuración actual.</div>`;
            return;
        }

        const tbodyHtml = empList.map((e, idx) => `
            <tr>
                <td class="text-center align-middle">
                    <input type="checkbox" class="form-check-input wiz-chk-emp" data-rut="${e.rut}" checked>
                </td>
                <td>${e.rut}</td>
                <td>${e.nombre} ${e.apellido_paterno}</td>
                <td>${e.area || '<span class="text-danger">Sin Área</span>'}</td>
                <td>
                    ${e.activo 
                        ? '<span class="badge bg-success">Activo</span>' 
                        : '<span class="badge bg-secondary">Inactivo</span>'}
                </td>
            </tr>
        `).join('');

        listContainer.innerHTML = `
            <div class="table-responsive" style="max-height: 300px;">
                <table class="table table-sm table-hover align-middle mb-0" style="font-size: 0.9rem;">
                    <thead class="table-light sticky-top">
                        <tr>
                            <th class="text-center"><input type="checkbox" class="form-check-input" id="wiz-chk-emp-all" checked onchange="document.querySelectorAll('.wiz-chk-emp').forEach(chk => chk.checked = this.checked)"></th>
                            <th>RUT</th>
                            <th>Nombre</th>
                            <th>Área</th>
                            <th>Estado</th>
                        </tr>
                    </thead>
                    <tbody>${tbodyHtml}</tbody>
                </table>
            </div>
        `;

        const searchInputs = document.querySelectorAll('#wizard-step-5 .d-flex.gap-2.mb-2, #wizard-step-5 .mb-2');
        searchInputs.forEach(el => el.classList.remove('d-none'));

    } catch (e) {
        console.error(e);
        if (listContainer) listContainer.innerHTML = `<div class="alert alert-danger m-3">Error al generar la previsualización de empleados.</div>`;
    }
}

// ==========================================
// FINALIZAR CONFIGURACIÓN Y PREVIEW (Paso 4 -> 5)
// ==========================================
async function finalizeWizardAndPreview() {
    const payload = {
        areas_resoluciones: window._wizardState.resoluciones.areas,
        cargos_resoluciones: window._wizardState.resoluciones.cargos,
        generos_nuevos: window._wizardState.resoluciones.generos,
        turnos_asignaciones: window._wizardState.resoluciones.turnos,
        bonos_asignaciones: window._wizardState.resoluciones.bonos
    };

    console.log("Enviando Mega-Payload a /wizard/finalize/:", payload);
    
    const btnNext = document.getElementById('btn-wizard-next');
    const originalText = btnNext.innerHTML;
    btnNext.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Procesando...`;
    btnNext.disabled = true;

    try {
        const response = await fetch(`${API_BASE_URL}/sync/wizard/finalize/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || `Error HTTP: ${response.status}`);
        }

        // Éxito, ahora podemos avanzar a Step 5 para el Preview
        localStorage.setItem('wizard_completed', 'true');
        window._wizardState.currentStep = 5;
        updateWizardUI();
    } catch (e) {
        console.error("Error en finalize_wizard_sync:", e);
        Swal.fire('Error', 'No se pudo aplicar la configuración inicial: ' + e.message, 'error');
    } finally {
        btnNext.innerHTML = originalText;
        btnNext.disabled = false;
    }
}

// ==========================================
// CONFIRMAR IMPORTACIÓN (Paso 5)
// ==========================================
window.confirmWizardSync = async function() {
    // Aquí disparamos el POST a /sync/empleados/ REAL
    const areasList = getConsolidatedAreas();
    const ignoredCargos = [];
    for (const [cargo, resolucion] of Object.entries(window._wizardState.resoluciones.cargos)) {
        if (resolucion === "_IGNORE_") {
            ignoredCargos.push(cargo);
        }
    }

    const payload = {
        areas: areasList,
        ignored_cargos: ignoredCargos
    };

    const btn = document.getElementById('btn-wizard-finish');
    const originalText = btn.innerHTML;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Sincronizando...`;
    btn.disabled = true;

    try {
        const response = await fetch(`${API_BASE_URL}/sync/empleados/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || `Error HTTP: ${response.status}`);
        }

        const data = await response.json();
        
        // Exito!
        const modalEl = document.getElementById('modal-sync-wizard');
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
        
        Swal.fire({
            title: "Sincronización Iniciada",
            text: "La descarga de empleados está en progreso en segundo plano.",
            icon: "success"
        });

        // Mostrar UI de Progreso (si existe la función en main.js)
        if (typeof showBatchLoadingOverlay === 'function') {
            showBatchLoadingOverlay();
            if (typeof startProgressPolling === 'function') {
                startProgressPolling();
            }
        }
    } catch (e) {
        console.error("Error iniciando sync empleados:", e);
        Swal.fire('Error', 'No se pudo iniciar la sincronización: ' + e.message, 'error');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
};
