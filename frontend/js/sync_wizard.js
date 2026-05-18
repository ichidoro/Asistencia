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
    },
    // Tracking de sesión: IDs creados en ESTE flujo (para rollback si el usuario retrocede)
    sessionCreated: {
        areas: [],    // [{id, bioalba_name, local_name}]
        cargos: [],   // [{id, bioalba_name, local_name}]
        generos: []   // [{id, nombre}]
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
    // Limpiar tracking de sesión al iniciar nuevo flujo
    window._wizardState.sessionCreated = {
        areas: [],
        cargos: [],
        generos: []
    };

    // FIX: NO pre-poblar áreas. Los checkboxes deben arrancar desmarcados
    // para que el usuario elija explícitamente qué áreas importar.
    // (Antes se pre-poblaba con "_NEW_" haciendo que todos aparecieran marcados)

    // Ocultar todos los steps y mostrar el 1
    updateWizardUI();

    const wizardModal = new bootstrap.Modal(document.getElementById('modal-sync-wizard'));
    wizardModal.show();
};

function updateWizardUI() {
    const TOTAL_STEPS = 7;
    const step = window._wizardState.currentStep;
    
    // Actualizar Stepper Visual — controla clases Bootstrap directamente
    document.querySelectorAll('#modal-sync-wizard .step-indicator').forEach((el, idx) => {
        const stepNum = idx + 1;
        el.classList.remove(
            'active', 'completed',
            'bg-primary', 'bg-light', 'bg-success',
            'text-white', 'text-muted', 'text-success',
            'border', 'border-primary', 'fw-bold'
        );

        if (stepNum < step) {
            el.classList.add('completed', 'bg-primary', 'text-white', 'fw-bold');
            el.innerHTML = '<i class="bi bi-check-lg"></i>';
        } else if (stepNum === step) {
            el.classList.add('active', 'bg-primary', 'text-white', 'fw-bold');
            el.textContent = stepNum;
        } else {
            el.classList.add('bg-light', 'text-muted', 'border');
            el.textContent = stepNum;
        }
    });

    // Progress bar
    const progressBar = document.getElementById('sync-wizard-progress');
    if (progressBar) {
        progressBar.style.width = `${((step - 1) / (TOTAL_STEPS - 1)) * 100}%`;
    }

    // Ocultar/Mostrar Paneles
    for (let i = 1; i <= TOTAL_STEPS; i++) {
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
    
    if (step === TOTAL_STEPS) {
        btnNext.classList.add('d-none');
        btnFinish.classList.remove('d-none');
    } else {
        btnNext.classList.remove('d-none');
        btnFinish.classList.add('d-none');
    }

    // Renderizar Contenido Específico
    if (step === 1) renderWizardStep1();
    if (step === 2) renderWizardStep2();
    if (step === 3) fetchAndRenderWizardStep3_Pagadores();
    if (step === 4) fetchAndRenderWizardStep4_TiposJ();
    if (step === 5) fetchAndRenderWizardStep5_Bonos();
    if (step === 6) fetchAndRenderWizardStep6_Turnos();
    if (step === 7) fetchAndRenderWizardStep7_Preview();
}

window.wizardNextStep = async function() {
    const TOTAL_STEPS = 7;
    const step = window._wizardState.currentStep;
    const btnNext = document.getElementById('btn-wizard-next');
    const originalText = btnNext ? btnNext.innerHTML : '';

    // --- PASO 1 → 2: Persistir áreas inmediatamente ---
    if (step === 1) {
        if (!guardarSeleccionesPaso1()) return;

        const resoluciones = window._wizardState.resoluciones.areas;
        const tieneSeleccion = Object.values(resoluciones).some(v => v !== '_IGNORE_');
        if (!tieneSeleccion) {
            Swal.fire('Atención', 'Debes seleccionar al menos un área para importar.', 'warning');
            return;
        }

        if (btnNext) { btnNext.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Guardando…'; btnNext.disabled = true; }
        try {
            const resp = await fetch('/api/sync/wizard/commit/areas/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ resoluciones })
            });
            if (!resp.ok) throw new Error(await resp.text());
            const result = await resp.json();
            if (result.creadas && result.creadas.length > 0) {
                window._wizardState.sessionCreated.areas = result.creadas;
                console.log('[Wizard] Áreas persistidas en BD:', result.creadas);
            }
        } catch (e) {
            console.error('[Wizard] Error commit areas:', e);
            Swal.fire('Error', 'No se pudieron guardar las áreas: ' + e.message, 'error');
            if (btnNext) { btnNext.innerHTML = originalText; btnNext.disabled = false; }
            return;
        } finally {
            if (btnNext) { btnNext.innerHTML = originalText; btnNext.disabled = false; }
        }
    }

    // --- PASO 2 → 3: Persistir cargos inmediatamente ---
    if (step === 2) {
        if (!guardarSeleccionesPaso2()) return;

        const resoluciones = window._wizardState.resoluciones.cargos;
        const generos = window._wizardState.resoluciones.generos || [];

        if (btnNext) { btnNext.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Guardando…'; btnNext.disabled = true; }
        try {
            const resp = await fetch('/api/sync/wizard/commit/cargos/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ resoluciones, generos })
            });
            if (!resp.ok) throw new Error(await resp.text());
            const result = await resp.json();
            if (result.creados && result.creados.length > 0) {
                window._wizardState.sessionCreated.cargos = result.creados;
            }
            if (result.generos_creados && result.generos_creados.length > 0) {
                window._wizardState.sessionCreated.generos = result.generos_creados;
            }
        } catch (e) {
            console.error('[Wizard] Error commit cargos:', e);
            Swal.fire('Error', 'No se pudieron guardar los cargos: ' + e.message, 'error');
            if (btnNext) { btnNext.innerHTML = originalText; btnNext.disabled = false; }
            return;
        } finally {
            if (btnNext) { btnNext.innerHTML = originalText; btnNext.disabled = false; }
        }
    }

    // --- PASO 3 → 4: Pagadores (datos globales, solo avanzar) ---
    // No requiere commit, los pagadores se crean inline vía POST directo

    // --- PASO 4 → 5: Tipos Justificación (datos globales, solo avanzar) ---
    // No requiere commit, los tipos J se crean vía modal existente

    // --- PASO 5 → 6: Bonos (guardar selecciones en memoria) ---
    if (step === 5) {
        guardarSeleccionesPaso5_Bonos();
    }

    // --- PASO 6 → 7: Persistir asignaciones de turno ---
    if (step === 6) {
        if (!guardarSeleccionesPaso6_Turnos()) return;

        const asignaciones = window._wizardState.resoluciones.turnos;
        if (Object.keys(asignaciones).length > 0) {
            if (btnNext) { btnNext.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Guardando…'; btnNext.disabled = true; }
            try {
                const resp = await fetch('/api/sync/wizard/commit/turnos/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ asignaciones })
                });
                if (!resp.ok) throw new Error(await resp.text());
            } catch (e) {
                console.error('[Wizard] Error commit turnos:', e);
                Swal.fire('Error', 'No se pudieron guardar las asignaciones de turno: ' + e.message, 'error');
                if (btnNext) { btnNext.innerHTML = originalText; btnNext.disabled = false; }
                return;
            } finally {
                if (btnNext) { btnNext.innerHTML = originalText; btnNext.disabled = false; }
            }
        }
    }

    // --- Avanzar ---
    if (step < TOTAL_STEPS) {
        window._wizardState.currentStep++;
        updateWizardUI();
    }
};

window.wizardPrevStep = async function() {
    const step = window._wizardState.currentStep;
    if (step <= 1) return;

    // --- RETROCESO PASO 2 → 1: Rollback de áreas de esta sesión ---
    if (step === 2) {
        const creadas = window._wizardState.sessionCreated.areas;
        if (creadas && creadas.length > 0) {
            const idsParaRollback = creadas.map(a => a.id);
            try {
                const resp = await fetch('/api/sync/wizard/rollback/', {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tipo: 'areas', ids: idsParaRollback })
                });
                if (resp.ok) {
                    console.log('[Wizard] Rollback de áreas completado:', idsParaRollback);
                    window._wizardState.sessionCreated.areas = [];
                }
            } catch (e) {
                console.warn('[Wizard] No se pudo hacer rollback de áreas (continuar de todas formas):', e);
            }
        }
    }

    // --- RETROCESO PASO 3 → 2: Rollback de cargos de esta sesión ---
    if (step === 3) {
        const creados = window._wizardState.sessionCreated.cargos;
        if (creados && creados.length > 0) {
            const idsParaRollback = creados.map(c => c.id);
            try {
                const resp = await fetch('/api/sync/wizard/rollback/', {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tipo: 'cargos', ids: idsParaRollback })
                });
                if (resp.ok) {
                    console.log('[Wizard] Rollback de cargos completado:', idsParaRollback);
                    window._wizardState.sessionCreated.cargos = [];
                }
            } catch (e) {
                console.warn('[Wizard] No se pudo hacer rollback de cargos:', e);
            }
        }
    }

    window._wizardState.currentStep--;
    updateWizardUI();
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
            // FIX: solo marcado si el usuario ya eligió explícitamente (resolucion truthy y no _IGNORE_)
            const isImport = resolucion && resolucion !== "_IGNORE_";
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
    const cargosPorArea = data.nuevos_cargos_por_area || {};
    const cargosConocidos = data.cargos_conocidos || [];
    const cargosConocidosPorArea = data.cargos_conocidos_por_area || {};

    // ── Construir set de áreas seleccionadas en Paso 1 ──
    // Incluye: (a) nuevas áreas que el usuario marcó, (b) áreas ya conocidas (siempre activas)
    const areasSeleccionadas = new Set();

    // (a) Áreas nuevas marcadas por el usuario en Paso 1
    const resolAreas = window._wizardState.resoluciones.areas;
    Object.entries(resolAreas).forEach(([area, res]) => {
        if (res && res !== "_IGNORE_") {
            // La resolución puede ser el nombre original (area) o un alias personalizado
            areasSeleccionadas.add(area);
        }
    });

    // (b) Áreas ya conocidas (siempre se incluyen, el usuario no las puede ignorar)
    (data.areas_conocidas || []).forEach(a => areasSeleccionadas.add(a));

    // ── Filtrar nuevos cargos: solo los que pertenecen a las áreas seleccionadas ──
    const cargosFiltrados = nuevosCargos.filter(cargo => {
        const areasDelCargo = cargosPorArea[cargo] || [];
        return areasDelCargo.some(a => areasSeleccionadas.has(a));
    });

    // ── Filtrar cargos conocidos también por área seleccionada ──
    const cargosConocidosFiltrados = cargosConocidos.filter(cargo => {
        const areasDelCargo = cargosConocidosPorArea[cargo] || [];
        // Si no tiene info de áreas, lo incluimos para no perderlo
        if (areasDelCargo.length === 0) return true;
        return areasDelCargo.some(a => areasSeleccionadas.has(a));
    });

    if (cargosFiltrados.length === 0 && cargosConocidosFiltrados.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted py-3">
            No se detectaron cargos para las áreas seleccionadas.
            ${areasSeleccionadas.size === 0 ? '<br><small class="text-warning">⚠️ No seleccionaste ningún área en el paso anterior.</small>' : ''}
        </td></tr>`;
        return;
    }

    // Nuevos Cargos (filtrados por área)
    if (cargosFiltrados.length > 0) {
        const trTitle = document.createElement('tr');
        trTitle.innerHTML = `<td colspan="4" class="bg-light text-warning fw-bold"><i class="bi bi-briefcase me-2"></i>Cargos Desconocidos</td>`;
        tbody.appendChild(trTitle);

        cargosFiltrados.forEach((cargo, idx) => {
            const resolucion = window._wizardState.resoluciones.cargos[cargo];
            // FIX: checkboxes desmarcados por defecto (solo marcado si hubo decisión previa explícita)
            const isImport = resolucion && resolucion !== "_IGNORE_";
            const customName = (resolucion && resolucion !== "_NEW_" && resolucion !== "_IGNORE_") ? resolucion : "";

            // Mostrar a qué área(s) pertenece este cargo como ayuda visual
            const areasTag = (cargosPorArea[cargo] || [])
                .filter(a => areasSeleccionadas.has(a))
                .map(a => `<span class="badge bg-secondary me-1" style="font-size:0.7rem;">${a}</span>`)
                .join('');

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="text-center align-middle">
                    <input type="checkbox" class="form-check-input check-cargo" id="wiz-chk-cargo-${idx}" data-cargo="${cargo}" ${isImport ? 'checked' : ''}>
                </td>
                <td class="fw-bold align-middle">
                    ${cargo}
                    <div class="mt-1">${areasTag}</div>
                </td>
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

    // Cargos Conocidos (filtrados por área)
    if (cargosConocidosFiltrados.length > 0) {
        const trTitle = document.createElement('tr');
        trTitle.innerHTML = `<td colspan="4" class="bg-light text-success fw-bold"><i class="bi bi-check-circle me-2"></i>Cargos Ya Conocidos</td>`;
        tbody.appendChild(trTitle);

        cargosConocidosFiltrados.forEach((cargo) => {
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
    // FIX: Usar data-cargo para no depender del índice posicional (ahora la lista está filtrada por área)
    const checkboxes = document.querySelectorAll('.check-cargo[data-cargo]');
    
    checkboxes.forEach(chk => {
        const cargo = chk.dataset.cargo;
        const idx = chk.id.replace('wiz-chk-cargo-', '');
        const inp = document.getElementById(`wiz-inp-cargo-${idx}`);
        
        if (chk.checked) {
            let finalName = inp ? inp.value.trim() : '';
            if (finalName === '') finalName = cargo;
            window._wizardState.resoluciones.cargos[cargo] = finalName;
        } else {
            window._wizardState.resoluciones.cargos[cargo] = '_IGNORE_';
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
// PASO 3: PAGADORES (NUEVO)
// ==========================================
async function fetchAndRenderWizardStep3_Pagadores() {
    const container = document.getElementById('wizard-pagadores-content');
    if (!container) return;
    
    container.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';

    try {
        const resp = await fetch('/api/configuracion/pagadores/', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (!resp.ok) throw new Error('Error cargando pagadores');
        const pagadores = await resp.json();

        if (pagadores.length > 0) {
            let html = '<div class="list-group mb-3">';
            pagadores.forEach(p => {
                html += `<div class="list-group-item d-flex justify-content-between align-items-center">
                    <span><i class="bi bi-bank me-2 text-primary"></i>${p.nombre}</span>
                    <span class="badge bg-success"><i class="bi bi-check-lg"></i></span>
                </div>`;
            });
            html += '</div>';
            html += `<div class="alert alert-success border-0 py-2 mb-3">
                <i class="bi bi-check-circle-fill me-2"></i> ${pagadores.length} pagador(es) configurado(s). Puedes continuar o agregar más.
            </div>`;
            html += `<div class="d-flex gap-2">
                <button class="btn btn-outline-primary btn-sm" onclick="window._wizardAbrirPagadores()">
                    <i class="bi bi-plus-circle me-1"></i> Agregar Pagador
                </button>
                <button class="btn btn-outline-secondary btn-sm" onclick="fetchAndRenderWizardStep3_Pagadores()">
                    <i class="bi bi-arrow-clockwise me-1"></i> Actualizar
                </button>
            </div>`;
            container.innerHTML = html;
        } else {
            container.innerHTML = `
                <div class="alert alert-warning border-0 shadow-sm d-flex align-items-start gap-3 p-4 rounded-3">
                    <i class="bi bi-exclamation-triangle-fill fs-3 text-warning flex-shrink-0 mt-1"></i>
                    <div>
                        <h6 class="fw-bold mb-1">No hay pagadores configurados</h6>
                        <p class="mb-2 small text-muted">
                            Los pagadores son necesarios para gestionar justificaciones de licencias médicas y similares.
                            Se recomienda crear al menos uno (ej: "Empresa").
                        </p>
                        <div class="d-flex flex-wrap gap-2 mt-3">
                            <button class="btn btn-primary btn-sm fw-bold" onclick="window._wizardAbrirPagadores()">
                                <i class="bi bi-plus-circle me-1"></i> Crear Pagador
                            </button>
                            <button class="btn btn-outline-secondary btn-sm" onclick="fetchAndRenderWizardStep3_Pagadores()">
                                <i class="bi bi-arrow-clockwise me-1"></i> Actualizar
                            </button>
                        </div>
                        <div class="mt-3 p-2 bg-light rounded border small text-muted">
                            <i class="bi bi-info-circle me-1 text-primary"></i>
                            Puedes omitir este paso y configurar pagadores más adelante desde <strong>Configuración</strong>.
                        </div>
                    </div>
                </div>`;
        }
    } catch (e) {
        console.error('[Wizard] Error cargando pagadores:', e);
        container.innerHTML = `<div class="alert alert-danger">Error al cargar pagadores: ${e.message}</div>`;
    }
}
/**
 * Helper: Abre un modal-hijo sobre el wizard sin conflictos de z-index/Top-Layer.
 * Estrategia: Ocultar temporalmente el wizard → abrir modal-hijo → al cerrar el hijo,
 * restaurar el wizard en el paso correcto.
 * @param {string} childModalId - ID del modal custom a abrir
 * @param {Function} openFn - Función que abre el modal (ej: openModalGestionPagadores)
 * @param {Function} onCloseFn - Callback al cerrar el modal-hijo
 */
function _wizardOpenChildModal(childModalId, openFn, onCloseFn) {
    const wizardEl = document.getElementById('modal-sync-wizard');
    const wizardModal = wizardEl ? bootstrap.Modal.getInstance(wizardEl) : null;

    // 1. Ocultar el wizard via Bootstrap API
    if (wizardModal) {
        wizardModal.hide();
    }

    // 2. Esperar a que Bootstrap termine de ocultar, luego abrir hijo
    setTimeout(() => {
        openFn();

        // 3. Bootstrap 5.3+ agrega 'inert' a todos los hermanos del modal activo.
        //    Como el child modal es un modal CUSTOM (no Bootstrap), debemos remover
        //    'inert' y 'aria-hidden' manualmente para que sea interactivo.
        const childEl = document.getElementById(childModalId);
        if (!childEl) return;

        // Remover inert del child y todos sus ancestros hasta el body
        let el = childEl;
        while (el && el !== document.body) {
            el.removeAttribute('inert');
            el.removeAttribute('aria-hidden');
            el = el.parentElement;
        }
        // También remover inert del childEl directamente (por si acaso)
        childEl.removeAttribute('inert');

        // 4. Observar cierre del modal-hijo (soporta AMBOS tipos de modal)
        const isBsModal = childEl.classList.contains('fade') || bootstrap.Modal.getInstance(childEl);

        if (isBsModal) {
            const _onHidden = () => {
                childEl.removeEventListener('hidden.bs.modal', _onHidden);
                _wizardRestoreAfterChild(wizardEl, onCloseFn);
            };
            childEl.addEventListener('hidden.bs.modal', _onHidden);
        } else {
            // Modal custom (display: flex/none): polling
            const checkClose = setInterval(() => {
                if (childEl.style.display === 'none' || childEl.style.display === '') {
                    clearInterval(checkClose);
                    _wizardRestoreAfterChild(wizardEl, onCloseFn);
                }
            }, 300);
        }
    }, 400);
}

/**
 * Restaura el wizard después de cerrar un modal-hijo.
 */
function _wizardRestoreAfterChild(wizardEl, onCloseFn) {
    if (!wizardEl) return;

    // Destruir instancia anterior para evitar conflictos Bootstrap
    const oldInst = bootstrap.Modal.getInstance(wizardEl);
    if (oldInst) oldInst.dispose();

    // Re-crear y mostrar
    const newInstance = new bootstrap.Modal(wizardEl, { backdrop: 'static', keyboard: false });
    newInstance.show();

    // Refrescar el contenido del paso actual
    setTimeout(() => {
        updateWizardUI();
        if (onCloseFn) onCloseFn();
    }, 350);
}

window._wizardAbrirPagadores = function() {
    if (typeof window.openModalGestionPagadores === 'function') {
        _wizardOpenChildModal(
            'modal-gestion-pagadores',
            () => window.openModalGestionPagadores(),
            () => fetchAndRenderWizardStep3_Pagadores()
        );
    } else {
        Swal.fire('Info', 'El módulo de pagadores aún no está cargado. Inicializa Configuración primero.', 'info');
    }
};

// ==========================================
// PASO 4: TIPOS DE JUSTIFICACIÓN (NUEVO)
// ==========================================
async function fetchAndRenderWizardStep4_TiposJ() {
    const container = document.getElementById('wizard-tiposj-content');
    if (!container) return;
    
    container.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';

    try {
        const resp = await fetch('/api/configuracion/justificaciones/tipos/', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (!resp.ok) throw new Error('Error cargando tipos de justificación');
        const tipos = await resp.json();

        if (tipos.length > 0) {
            let html = '<div class="list-group mb-3" style="max-height: 300px; overflow-y: auto;">';
            tipos.forEach(t => {
                const badge = t.requiere_documento 
                    ? '<span class="badge bg-warning text-dark ms-2">📎 Req. Doc.</span>' 
                    : '';
                html += `<div class="list-group-item d-flex justify-content-between align-items-center">
                    <span><i class="bi bi-file-earmark-check me-2 text-primary"></i>${t.nombre}${badge}</span>
                    <span class="badge bg-success"><i class="bi bi-check-lg"></i></span>
                </div>`;
            });
            html += '</div>';
            html += `<div class="alert alert-success border-0 py-2 mb-3">
                <i class="bi bi-check-circle-fill me-2"></i> ${tipos.length} tipo(s) de justificación configurado(s).
            </div>`;
            html += `<div class="d-flex gap-2">
                <button class="btn btn-outline-primary btn-sm" onclick="window._wizardAbrirTipoJ()">
                    <i class="bi bi-plus-circle me-1"></i> Agregar Tipo
                </button>
                <button class="btn btn-outline-secondary btn-sm" onclick="fetchAndRenderWizardStep4_TiposJ()">
                    <i class="bi bi-arrow-clockwise me-1"></i> Actualizar
                </button>
            </div>`;
            container.innerHTML = html;
        } else {
            container.innerHTML = `
                <div class="alert alert-warning border-0 shadow-sm d-flex align-items-start gap-3 p-4 rounded-3">
                    <i class="bi bi-exclamation-triangle-fill fs-3 text-warning flex-shrink-0 mt-1"></i>
                    <div>
                        <h6 class="fw-bold mb-1">No hay tipos de justificación configurados</h6>
                        <p class="mb-2 small text-muted">
                            Los tipos de justificación permiten categorizar ausencias (Vacaciones, Licencia Médica, Permiso, etc.).
                        </p>
                        <div class="d-flex flex-wrap gap-2 mt-3">
                            <button class="btn btn-primary btn-sm fw-bold" onclick="window._wizardAbrirTipoJ()">
                                <i class="bi bi-plus-circle me-1"></i> Crear Tipo de Justificación
                            </button>
                            <button class="btn btn-outline-secondary btn-sm" onclick="fetchAndRenderWizardStep4_TiposJ()">
                                <i class="bi bi-arrow-clockwise me-1"></i> Actualizar
                            </button>
                        </div>
                        <div class="mt-3 p-2 bg-light rounded border small text-muted">
                            <i class="bi bi-info-circle me-1 text-primary"></i>
                            Puedes omitir este paso y configurar tipos más adelante desde <strong>Configuración</strong>.
                        </div>
                    </div>
                </div>`;
        }
    } catch (e) {
        console.error('[Wizard] Error cargando tipos J:', e);
        container.innerHTML = `<div class="alert alert-danger">Error al cargar tipos de justificación: ${e.message}</div>`;
    }
}

window._wizardAbrirTipoJ = function() {
    if (typeof window.openModalTipoJ === 'function') {
        _wizardOpenChildModal(
            'modal-tipo-justificacion',
            () => window.openModalTipoJ(),
            () => fetchAndRenderWizardStep4_TiposJ()
        );
    } else {
        Swal.fire('Info', 'El módulo de justificaciones aún no está cargado. Inicializa Configuración primero.', 'info');
    }
};

// ==========================================
// PASO 5: BONOS (ex-Paso 4) — Alias
// ==========================================
async function fetchAndRenderWizardStep5_Bonos() { return fetchAndRenderWizardStep4(); }
function guardarSeleccionesPaso5_Bonos() { return guardarSeleccionesPaso4(); }

// ==========================================
// PASO 6: TURNOS (ex-Paso 3) — Alias
// ==========================================
async function fetchAndRenderWizardStep6_Turnos() { return fetchAndRenderWizardStep3(); }
function guardarSeleccionesPaso6_Turnos() { return guardarSeleccionesPaso3(); }

// ==========================================
// PASO 7: PREVIEW EMPLEADOS (ex-Paso 5) — Alias
// ==========================================
async function fetchAndRenderWizardStep7_Preview() { return fetchAndRenderWizardStep5(); }

// ==========================================
// PASO 3 (original): TURNOS (función original preservada para alias)
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

        // ── CASO CRÍTICO: No hay turnos creados en el sistema ────────────────
        if (window._wizardState.turnosDisponibles.length === 0) {
            const container = document.getElementById('wizard-step-6');
            // Reemplazar toda la tabla por un panel de acción guía
            const tableSection = container.querySelector('.table-responsive');
            if (tableSection) {
                tableSection.innerHTML = `
                    <div class="alert alert-warning border-0 shadow-sm d-flex align-items-start gap-3 p-4 rounded-3">
                        <i class="bi bi-exclamation-triangle-fill fs-3 text-warning flex-shrink-0 mt-1"></i>
                        <div>
                            <h6 class="fw-bold mb-1">No existe ningún turno configurado</h6>
                            <p class="mb-2 small text-muted">
                                Para sincronizar empleados necesitas al menos un turno de trabajo. 
                                Debes ir a <strong>Configuración → Turnos</strong> y crear uno antes de continuar.
                            </p>
                            <div class="d-flex flex-wrap gap-2 mt-3">
                                <button class="btn btn-primary btn-sm fw-bold"
                                        onclick="window._wizardIrACrearTurno()">
                                    <i class="bi bi-plus-circle me-1"></i>
                                    Ir a Configuración → Crear Turno ahora
                                </button>
                                <button class="btn btn-outline-secondary btn-sm"
                                        onclick="window._wizardRefrescarTurnos()">
                                    <i class="bi bi-arrow-clockwise me-1"></i>
                                    Ya creé un turno, actualizar
                                </button>
                            </div>
                            <div class="mt-3 p-2 bg-light rounded border small text-muted">
                                <i class="bi bi-info-circle me-1 text-primary"></i>
                                <strong>Ruta:</strong> Módulo <em>Configuración</em> → pestaña <em>🕒 Turnos</em> → botón <em>Nuevo Turno</em>
                            </div>
                        </div>
                    </div>
                `;
            }
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
            // Sin bonos creados: ofrecer crear uno directamente
            const tableSection = document.querySelector('#wizard-step-5 .table-responsive');
            if (tableSection) {
                tableSection.innerHTML = `
                    <div class="alert alert-info border-0 shadow-sm d-flex align-items-start gap-3 p-4 rounded-3">
                        <i class="bi bi-cash-coin fs-3 text-primary flex-shrink-0 mt-1"></i>
                        <div class="w-100">
                            <h6 class="fw-bold mb-1">No hay bonos configurados todavía</h6>
                            <p class="mb-2 small text-muted">
                                Los bonos son opcionales pero recomendados. Puedes crear uno ahora o continuar y configurarlos después.
                            </p>
                            <div class="d-flex flex-wrap gap-2 mt-3">
                                <button class="btn btn-primary btn-sm fw-bold" onclick="window._wizardCrearBono()">
                                    <i class="bi bi-plus-circle me-1"></i>
                                    Crear Bono ahora
                                </button>
                                <button class="btn btn-outline-secondary btn-sm" onclick="window._wizardRefrescarBonos()">
                                    <i class="bi bi-arrow-clockwise me-1"></i>
                                    Ya creé un bono, actualizar
                                </button>
                            </div>
                            <div class="mt-3 p-2 bg-light rounded border small text-muted">
                                <i class="bi bi-info-circle me-1 text-primary"></i>
                                También puedes omitir y presionar <strong>Siguiente Paso</strong> para configurar bonos después.
                            </div>
                        </div>
                    </div>
                `;
            }
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
        // El endpoint retorna una lista directamente O un objeto {empleados: [...]}
        const empList = Array.isArray(res) ? res : (res.empleados || []);

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

        const searchInputs = document.querySelectorAll('#wizard-step-7 .d-flex.gap-2.mb-2, #wizard-step-7 .mb-2');
        searchInputs.forEach(el => el.classList.remove('d-none'));

    } catch (e) {
        console.error(e);
        if (listContainer) listContainer.innerHTML = `<div class="alert alert-danger m-3">Error al generar la previsualización de empleados.</div>`;
    }
}

// ==========================================
// CONFIRMAR IMPORTACIÓN (Paso final del Wizard)
// Lee RUTs del paso 7 y dispara el flujo SSE directamente:
// SSE → procesarColaOnboarding → editar → bonos → turnos → marcaciones → grilla
// ==========================================
window.confirmWizardSync = async function() {
    // 1. Recolectar RUTs seleccionados del paso 7 del wizard
    const checkedBoxes = document.querySelectorAll('.wiz-chk-emp:checked');
    const allBoxes = document.querySelectorAll('.wiz-chk-emp');

    if (checkedBoxes.length === 0) {
        Swal.fire('Sin selección', 'Seleccione al menos un empleado para sincronizar.', 'warning');
        return;
    }

    const selectedRuts = checkedBoxes.length < allBoxes.length
        ? Array.from(checkedBoxes).map(cb => cb.dataset.rut)
        : null;

    const filterMsg = selectedRuts
        ? `${selectedRuts.length} empleado(s) seleccionado(s)`
        : `Todos los ${allBoxes.length} empleado(s)`;

    const confirmResult = await Swal.fire({
        title: '¿Iniciar sincronización?',
        text: filterMsg,
        icon: 'question',
        showCancelButton: true,
        confirmButtonText: 'Sí, sincronizar',
        cancelButtonText: 'Cancelar'
    });

    if (!confirmResult.isConfirmed) return;

    // 2. Preparar filtros globales para el flujo SSE en main.js
    window._syncSelectedAreas = getConsolidatedAreas();

    const ignoredCargos = [];
    for (const [cargo, resolucion] of Object.entries(window._wizardState.resoluciones.cargos)) {
        if (resolucion === "_IGNORE_") {
            ignoredCargos.push(cargo);
        }
    }
    window._ignoredCargos = ignoredCargos;

    // 3. Marcar wizard como completado
    localStorage.setItem('wizard_completed', 'true');

    // 4. Cerrar wizard
    const modalEl = document.getElementById('modal-sync-wizard');
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();

    // 5. Disparar el flujo SSE directamente (bypass de openSyncModalPreview + confirmSync)
    const payload = {
        areas: window._syncSelectedAreas.length > 0 ? window._syncSelectedAreas : null,
        ruts: selectedRuts,
        ignored_cargos: ignoredCargos.length > 0 ? ignoredCargos : null
    };

    const btnSync = document.getElementById('btn-sync');
    if (btnSync) {
        btnSync.innerHTML = '<span>🔄</span><span>Sincronizando...</span>';
        btnSync.disabled = true;
    }

    // Mostrar spinner
    if (typeof showBatchLoadingOverlay === 'function') {
        showBatchLoadingOverlay('Conectando a BioAlba...');
    }

    try {
        const response = await fetch(`${window.API_BASE_URL || ''}/sync/empleados/now/stream/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            if (typeof hideBatchLoadingOverlay === 'function') hideBatchLoadingOverlay();
            const errData = await response.json().catch(() => ({}));
            Swal.fire('Error', errData.detail || 'Error desconocido', 'error');
            return;
        }

        // Leer el stream SSE — REUTILIZA la lógica EXACTA de confirmSync en main.js
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalStats = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            const lines = buffer.split('\n');
            buffer = lines.pop();

            let eventType = null;
            let eventData = null;
            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    eventType = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    try { eventData = JSON.parse(line.slice(6)); } catch { eventData = null; }
                } else if (line === '' && eventType && eventData !== null) {
                    if (eventType === 'start') {
                        const total = eventData.total || '?';
                        if (typeof showBatchLoadingOverlay === 'function')
                            showBatchLoadingOverlay(`Sincronizando ${total} empleado(s)...`);
                    } else if (eventType === 'progress') {
                        if (typeof updateBatchOverlayProgress === 'function')
                            updateBatchOverlayProgress(eventData.idx, eventData.total, eventData.nombre);
                    } else if (eventType === 'done') {
                        finalStats = eventData;
                    } else if (eventType === 'error') {
                        if (typeof hideBatchLoadingOverlay === 'function') hideBatchLoadingOverlay();
                        Swal.fire('Error', eventData.message || 'Error durante sincronización', 'error');
                    }
                    eventType = null;
                    eventData = null;
                }
            }
        }

        // Stream completado — conectar al flujo de onboarding de main.js
        if (finalStats) {
            const stats = finalStats;
            if (typeof loadStats === 'function') await loadStats();
            if (typeof loadEmpleados === 'function') await loadEmpleados();

            if (stats.nuevos_detalles && stats.nuevos_detalles.length > 0) {
                console.log("🆕 [Wizard→SSE] Nuevos empleados para onboarding:", stats.nuevos_detalles);
                window.onboardingQueue = [...stats.nuevos_detalles];
                window._batchTotalForOnboarding = window.onboardingQueue.length;

                if (window.onboardingQueue.length > 1) {
                    window._batch = window._batch || {};
                    window._batch.active = true;
                    window._batch.phase = 'edit';
                    window._batch.editedEmployees = [];
                    window._batch.syncPayload = [];
                    if (typeof showToast === 'function')
                        showToast(`🚀 Batch: editarás ${window.onboardingQueue.length} empleados → bonos → turnos → sync`, 'info');
                } else {
                    window._batch = window._batch || {};
                    window._batch.active = false;
                }

                // Transición al flujo de onboarding (editar → bonos → turnos → marcaciones → grilla)
                const _spinMsg = window._batchTotalForOnboarding > 1
                    ? `Preparando empleado 1 de ${window._batchTotalForOnboarding}...`
                    : `Preparando empleado...`;
                if (typeof showBatchLoadingOverlay === 'function') showBatchLoadingOverlay(_spinMsg);
                setTimeout(() => {
                    if (typeof procesarColaOnboarding === 'function') {
                        procesarColaOnboarding();
                    } else {
                        console.error('[Wizard] procesarColaOnboarding no disponible');
                        if (typeof hideBatchLoadingOverlay === 'function') hideBatchLoadingOverlay();
                    }
                }, 1500);
            } else {
                if (typeof hideBatchLoadingOverlay === 'function') hideBatchLoadingOverlay();
                Swal.fire('Sincronización completada', 
                    `Nuevos: ${stats.empleados_nuevos}\nActualizados: ${stats.empleados_actualizados}\nSin cambios: ${stats.empleados_sin_cambios || 0}\nErrores: ${stats.errores}`,
                    stats.errores > 0 ? 'warning' : 'success');
            }
        } else {
            if (typeof hideBatchLoadingOverlay === 'function') hideBatchLoadingOverlay();
        }

    } catch (error) {
        if (typeof hideBatchLoadingOverlay === 'function') hideBatchLoadingOverlay();
        console.error('[Wizard] Error en sync stream:', error);
        Swal.fire('Error', 'Error de conexión al iniciar sincronización', 'error');
    } finally {
        if (btnSync) {
            btnSync.innerHTML = '<span>🔄</span><span>Sincronizar</span>';
            btnSync.disabled = false;
        }
    }
};

// ==========================================
// HELPERS: Acciones desde el panel "Sin Turnos"
// ==========================================

/**
 * Abre el modal de Nuevo Turno DIRECTAMENTE sobre el wizard (sin cerrarlo).
 * Bootstrap soporta modales apilados. Al guardar el turno, el wizard
 * recarga el Paso 3 automáticamente vía _wizardRefrescarTurnos.
 */
window._wizardIrACrearTurno = function() {
    const form = document.getElementById('formTurno');

    if (!form) {
        // El formulario del modal de Turno no está en el DOM todavía.
        // Necesitamos navegar a Configuración → Turnos para que el HTML se renderice.

        // 1. Ocultar el wizard SIN destruirlo (el estado se preserva en window._wizardState)
        const wizardModalEl = document.getElementById('modal-sync-wizard');
        const wizardInstance = wizardModalEl ? bootstrap.Modal.getInstance(wizardModalEl) : null;
        if (wizardInstance) wizardInstance.hide();

        // 2. Navegar a Configuración para cargar el DOM del modal de turno
        if (typeof switchPage === 'function') {
            switchPage('configuracion');
        }

        // 3. Activar pestaña Turnos y abrir el modal
        setTimeout(() => {
            const tabHorarios = document.getElementById('horarios-tab');
            if (tabHorarios) tabHorarios.click();

            setTimeout(() => {
                if (typeof openModalHorario === 'function') {
                    openModalHorario();
                    const modalTurnoEl = document.getElementById('modalTurno');
                    if (modalTurnoEl) {
                        modalTurnoEl.addEventListener('hidden.bs.modal', function _onClose() {
                            modalTurnoEl.removeEventListener('hidden.bs.modal', _onClose);
                            // 4. Volver al wizard en el Paso 6 (Turnos) y refrescar la lista
                            if (wizardModalEl) {
                                window._wizardState.currentStep = 6;
                                // Destruir instancia anterior para evitar conflicto Bootstrap
                                const oldInst = bootstrap.Modal.getInstance(wizardModalEl);
                                if (oldInst) oldInst.dispose();
                                const newInstance = new bootstrap.Modal(wizardModalEl, { backdrop: 'static', keyboard: false });
                                newInstance.show();
                                setTimeout(() => window._wizardRefrescarTurnos(), 350);
                            }
                        });
                    }
                }
            }, 400);
        }, 200);
        return;
    }

    // El formulario ya está en el DOM → abrir modal directamente usando helper
    _wizardOpenChildModal(
        'modalTurno',
        () => openModalHorario(),
        () => window._wizardRefrescarTurnos()
    );
};

/**
 * Recarga el Paso 6 (Turnos) sin cerrar el wizard.
 * Útil si el usuario ya creó un turno en otra pestaña.
 */
window._wizardRefrescarTurnos = function() {
    const step3 = document.getElementById('wizard-step-6');
    const tableSection = step3 && step3.querySelector('.table-responsive');
    if (tableSection) {
        tableSection.innerHTML = `
            <table class="table table-bordered align-middle table-sm">
                <thead class="table-light sticky-top">
                    <tr>
                        <th>Área a sincronizar</th>
                        <th>Turno Recomendado / Seleccionado</th>
                    </tr>
                </thead>
                <tbody id="tbody-wizard-turnos">
                    <tr><td colspan="2" class="text-center py-4"><div class="spinner-border text-primary"></div></td></tr>
                </tbody>
            </table>
        `;
    }
    if (typeof checkTurnosExist === 'function') {
        checkTurnosExist().then(() => fetchAndRenderWizardStep3());
    } else {
        fetchAndRenderWizardStep3();
    }
};

// ==========================================
// HELPERS: Acciones desde el panel "Sin Bonos" (Paso 4)
// ==========================================

/**
 * Abre el modal de Nuevo Bono directamente sobre el wizard.
 * El modal `modal-bono` usa display:flex (no Bootstrap), por lo que
 * siempre está disponible en el DOM sin necesidad de navegar.
 * Al cerrarse, refresca el Paso 4.
 */
window._wizardCrearBono = function() {
    if (typeof openModalBono !== 'function') {
        Swal.fire({
            title: 'Módulo no cargado',
            html: `<p>El módulo de bonos aún no está inicializado.</p>
                   <p class="text-muted small">Ve a <strong>Configuración → Bonos</strong>, crea el bono y usa <em>"Ya creé un bono, actualizar"</em>.</p>`,
            icon: 'info',
            confirmButtonText: 'Entendido'
        });
        return;
    }

    // Inicializar la UI de configuración si aún no se ha hecho
    if (typeof initConfiguracionUI === 'function' && !window._config_initialized) {
        initConfiguracionUI();
    }

    // Usar el helper centralizado para esconder wizard → abrir modal-bono → restaurar
    _wizardOpenChildModal(
        'modal-bono',
        () => openModalBono(),
        () => window._wizardRefrescarBonos()
    );
};

/**
 * Recarga el Paso 4 (Bonos) sin cerrar el wizard.
 */
window._wizardRefrescarBonos = function() {
    const step4 = document.getElementById('wizard-step-5');
    // Restaurar la tabla original antes de llamar a fetchAndRenderWizardStep4
    const tableSection = step4 && step4.querySelector('.table-responsive');
    if (tableSection) {
        tableSection.innerHTML = `
            <table class="table table-bordered align-middle table-sm">
                <thead class="table-light sticky-top">
                    <tr>
                        <th>Área</th>
                        <th>Bonos Asignados</th>
                    </tr>
                </thead>
                <tbody id="tbody-wizard-bonos">
                    <tr><td colspan="2" class="text-center py-4"><div class="spinner-border text-primary"></div></td></tr>
                </tbody>
            </table>
        `;
    }
    fetchAndRenderWizardStep4();
};
