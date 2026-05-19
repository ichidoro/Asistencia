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
    if (!modalEl) return;
    const modalInstance = bootstrap.Modal.getInstance(modalEl);
    // Usar dispose() + blur + inert en lugar de hide() para evitar el warning
    // "Blocked aria-hidden on element with focused descendant".
    // hide() pone aria-hidden al FINAL de la animación CSS, cuando FocusTrap ya restauró
    // el foco → el elemento puede tener foco en ese momento → warning.
    // Con dispose() el FocusTrap se destruye inmediatamente → podemos blur con seguridad.
    if (modalInstance) modalInstance.dispose();
    modalEl.querySelectorAll('input, button, select, textarea, a, [tabindex]')
        .forEach(el => el.blur());
    modalEl.blur();
    document.body.setAttribute('tabindex', '-1');
    document.body.focus();
    document.body.removeAttribute('tabindex');
    modalEl.classList.remove('show');
    modalEl.style.display = 'none';
    setTimeout(() => {
        document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
        document.body.classList.remove('modal-open');
        document.body.style.removeProperty('overflow');
        document.body.style.removeProperty('padding-right');
    }, 0);
};

// ── FIX GLOBAL: Prevenir aria-hidden focus warning ───────────────────────────
// Bootstrap emite 'hide.bs.modal' y luego agrega aria-hidden en el MISMO tick.
// Usamos { capture: true } para que nuestro listener corra en FASE DE CAPTURA,
// antes que el listener de Bootstrap (bubbling) → el foco ya está en body
// cuando Bootstrap intenta marcar aria-hidden → cero warnings.
(function _installWizardFocusFix() {
    const install = () => {
        const wizardEl = document.getElementById('modal-sync-wizard');
        if (!wizardEl || wizardEl._focusFixInstalled) return;
        wizardEl._focusFixInstalled = true;

        document.addEventListener('hide.bs.modal', (e) => {
            if (e.target !== wizardEl) return;
            // Sacar foco de TODOS los elementos interactivos del wizard
            wizardEl.querySelectorAll('input, button, select, textarea, a, [tabindex]')
                .forEach(el => el.blur());
            wizardEl.blur();
            // Transferir foco al body de forma segura
            document.body.setAttribute('tabindex', '-1');
            document.body.focus();
            document.body.removeAttribute('tabindex');
        }, true); // <-- capture: true → fase de captura, antes que Bootstrap
    };
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', install);
    } else {
        setTimeout(install, 0);
    }
})();

window.startSyncWizard = function(data) {
    console.log("⚡ Iniciando Universal Sync Wizard...", data);
    
    // Si no requiere confirmación, es porque no hay nuevas áreas ni cargos, 
    // pero de todas formas queremos mostrar el paso 4 y 5 si es sincronización inicial.
    // Sin embargo, el Wizard ahora asume todo el control.
    
    window._wizardState.data = data;
    window._wizardState.currentStep = 1;
    window._wizardState.resoluciones = {
        areas: {},
        areas_conocidas: {},
        cargos: {},
        cargos_conocidos: {},
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
        const areasConocidas = window._wizardState.resoluciones.areas_conocidas || {};
        const tieneSeleccion = Object.values(resoluciones).some(v => v !== '_IGNORE_') || Object.values(areasConocidas).some(v => v === true);
        if (!tieneSeleccion) {
            Swal.fire('Atención', 'Debes seleccionar al menos un área para importar.', 'warning');
            return;
        }

        if (btnNext) { btnNext.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Guardando…'; btnNext.disabled = true; }
        try {
            const resp = await fetch('/api/sync/wizard/commit/areas/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
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
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
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
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
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
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
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
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
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

        areasConocidas.forEach((area, idx) => {
            if (!window._wizardState.resoluciones.areas_conocidas) window._wizardState.resoluciones.areas_conocidas = {};
            const isImport = window._wizardState.resoluciones.areas_conocidas[area] !== false; // checked by default
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="text-center align-middle">
                    <input type="checkbox" class="form-check-input check-area-conocida" id="wiz-chk-area-conocida-${idx}" data-area="${area}" ${isImport ? 'checked' : ''}>
                </td>
                <td class="fw-bold align-middle text-success">${area}</td>
                <td class="text-center align-middle">-</td>
                <td class="align-middle text-muted small">Área Existente (Seleccionar para importar emp.)</td>
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

    // Recorrer áreas conocidas
    const areasConocidas = data.areas_conocidas || [];
    if (!window._wizardState.resoluciones.areas_conocidas) window._wizardState.resoluciones.areas_conocidas = {};
    areasConocidas.forEach((area, idx) => {
        const chk = document.getElementById(`wiz-chk-area-conocida-${idx}`);
        if (chk) {
            window._wizardState.resoluciones.areas_conocidas[area] = chk.checked;
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

    // (b) Áreas ya conocidas (solo si el usuario las dejó seleccionadas)
    (data.areas_conocidas || []).forEach(a => {
        if (window._wizardState.resoluciones.areas_conocidas && window._wizardState.resoluciones.areas_conocidas[a] !== false) {
            areasSeleccionadas.add(a);
        }
    });

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

        if (!window._wizardState.resoluciones.cargos_conocidos) window._wizardState.resoluciones.cargos_conocidos = {};
        cargosConocidosFiltrados.forEach((cargo, idx) => {
            const isImport = window._wizardState.resoluciones.cargos_conocidos[cargo] !== false;
            const areasTag = (cargosConocidosPorArea[cargo] || [])
                .filter(a => areasSeleccionadas.has(a))
                .map(a => `<span class="badge bg-secondary me-1" style="font-size:0.7rem;">${a}</span>`)
                .join('');
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="text-center align-middle">
                    <input type="checkbox" class="form-check-input check-cargo-conocido" id="wiz-chk-cargo-conocido-${idx}" data-cargo="${cargo}" ${isImport ? 'checked' : ''}>
                </td>
                <td class="fw-bold align-middle text-success">
                    ${cargo}
                    <div class="mt-1">${areasTag}</div>
                </td>
                <td class="align-middle text-muted small">Cargo Existente (Seleccionar para importar emp.)</td>
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

    // Guardar cargos conocidos (marcados = incluir empleados, desmarcados = ignorar)
    if (!window._wizardState.resoluciones.cargos_conocidos) window._wizardState.resoluciones.cargos_conocidos = {};
    document.querySelectorAll('.check-cargo-conocido[data-cargo]').forEach(chk => {
        window._wizardState.resoluciones.cargos_conocidos[chk.dataset.cargo] = chk.checked;
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

    // Guard: _wizardState.data puede ser null si el paso 1 (API fetch) aún no se completó
    if (!window._wizardState || !window._wizardState.data) return [];

    // Areas Conocidas
    const conocidas = window._wizardState.data.areas_conocidas || [];
    conocidas.forEach(a => {
        if (window._wizardState.resoluciones.areas_conocidas && window._wizardState.resoluciones.areas_conocidas[a] !== false) {
            areasLocalNames.add(a);
        }
    });

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

    // 1. DESTRUIR primero el wizard para matar el FocusTrap de Bootstrap.
    // IMPORTANTE: dispose() debe ir ANTES del blur().
    // Si hacemos blur() primero, el FocusTrap de Bootstrap intercepta el focusout
    // y redirige el foco DE VUELTA al modal antes de que llegue dispose().
    // Con dispose() primero, el FocusTrap ya no existe cuando hacemos blur() → sin warning.
    // Nota: Bootstrap.dispose() NO llama hide() ni setea aria-hidden, por lo que no hay riesgo.
    if (wizardModal) {
        wizardModal.dispose();
    }
    // 2. Ahora que FocusTrap está muerto, blur es seguro.
    if (wizardEl) {
        wizardEl.removeAttribute('aria-hidden'); // Limpiar cualquier aria-hidden residual
        const focusedInWizard = wizardEl.querySelectorAll('input, button, select, textarea, a, [tabindex]');
        focusedInWizard.forEach(el => el.blur());
        wizardEl.blur();
        document.body.focus();
    }
    // 3. Ocultar el DOM del wizard manualmente y marcarlo INERT.
    // 'inert' es la solución definitiva: garantiza que NINGÚN descendiente
    // puede recibir foco por ningún mecanismo (FocusTrap._returnFocusElement,
    // tab navigation, programmatic focus, etc.).
    // Cuando Bootstrap abra el modal hijo y llame setAttribute('aria-hidden', true)
    // en el wizard, no habrá ningún descendiente con foco → cero warning.
    if (wizardEl) {
        wizardEl.classList.remove('show');
        wizardEl.style.display = 'none';
        wizardEl.setAttribute('inert', '');  // ← Fix definitivo
    }

    // 2. Limpiar TODOS los artefactos que Bootstrap deja:
    //    - Backdrops residuales
    //    - Body classes/styles
    //    - Atributos inert/aria-hidden en TODO el DOM
    setTimeout(() => {
        // Remover backdrops de Bootstrap
        document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());

        // Restaurar body
        document.body.classList.remove('modal-open');
        document.body.style.removeProperty('overflow');
        document.body.style.removeProperty('padding-right');

        // Remover inert/aria-hidden de TODO el DOM EXCEPTO del wizard
        // (el wizard permanece inert hasta que se restaure vía _wizardRestoreAfterChild)
        document.querySelectorAll('[inert]').forEach(el => {
            if (el !== wizardEl) el.removeAttribute('inert');
        });
        document.querySelectorAll('[aria-hidden="true"]').forEach(el => {
            if (!el.matches('script, link, style, [data-permanent-aria-hidden]') && el !== wizardEl) {
                el.removeAttribute('aria-hidden');
            }
        });

        // Segundo blur agresivo antes de abrir el modal hijo
        document.body.setAttribute('tabindex', '-1');
        document.body.focus();
        document.body.removeAttribute('tabindex');

        // 5. Ahora abrir el modal hijo en DOM limpio
        openFn();

        const childEl = document.getElementById(childModalId);
        if (!childEl) return;

        // Guard: MutationObserver para prevenir que cualquier cosa re-agregue inert/aria-hidden
        const observer = new MutationObserver(() => {
            if (childEl.hasAttribute('inert')) childEl.removeAttribute('inert');
            if (childEl.hasAttribute('aria-hidden')) childEl.removeAttribute('aria-hidden');
            childEl.querySelectorAll('[inert]').forEach(e => e.removeAttribute('inert'));
            // Limpiar ancestros también
            let p = childEl.parentElement;
            while (p && p !== document.body) {
                if (p.hasAttribute('inert')) p.removeAttribute('inert');
                if (p.hasAttribute('aria-hidden') && !p.matches('script, link, style')) {
                    p.removeAttribute('aria-hidden');
                }
                p = p.parentElement;
            }
        });

        observer.observe(document.body, { 
            attributes: true, 
            attributeFilter: ['inert', 'aria-hidden'],
            subtree: true 
        });

        // 4. Observar cierre del modal-hijo (soporta AMBOS tipos de modal)
        const isBsModal = childEl.classList.contains('fade') || bootstrap.Modal.getInstance(childEl);

        if (isBsModal) {
            const _onHidden = () => {
                childEl.removeEventListener('hidden.bs.modal', _onHidden);
                observer.disconnect(); // Limpiar observer
                _wizardRestoreAfterChild(wizardEl, onCloseFn);
            };
            childEl.addEventListener('hidden.bs.modal', _onHidden);
        } else {
            // Modal custom (display: flex/none): primero esperar a que APAREZCA,
            // luego detectar cuando DESAPAREZCA.
            let appeared = false;
            const checkClose = setInterval(() => {
                const d = childEl.style.display;
                if (!appeared) {
                    // Esperar a que el modal se muestre (flex o block)
                    if (d === 'flex' || d === 'block') {
                        appeared = true;
                        console.log('[Wizard] Modal hijo apareció:', childModalId);
                    }
                } else {
                    // Ya apareció — detectar cuando se cierre
                    if (d === 'none' || d === '') {
                        clearInterval(checkClose);
                        observer.disconnect(); // Limpiar observer
                        console.log('[Wizard] Modal hijo cerrado:', childModalId);
                        _wizardRestoreAfterChild(wizardEl, onCloseFn);
                    }
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

    // Sacar foco de cualquier elemento activo antes de restaurar wizard
    if (document.activeElement) {
        document.activeElement.blur();
    }

    // Quitar 'inert' antes de re-mostrar (fue puesto por _wizardOpenChildModal)
    wizardEl.removeAttribute('inert');

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
    if (typeof window.openModalGestionPagadores !== 'function') {
        Swal.fire('Info', 'El módulo de pagadores aún no está cargado. Inicializa Configuración primero.', 'info');
        return;
    }
    const modalPagEl = document.getElementById('modal-gestion-pagadores');
    if (!modalPagEl) return;

    // CAUSA REAL: Bootstrap FocusTrap redirige cualquier foco fuera del wizard.
    // SOLUCIÓN: Mover el modal DENTRO del wizard. Con position:fixed sigue
    // visual correcto; el FocusTrap permite focus porque está 'dentro' del modal activo.
    const _originalParent = modalPagEl.parentElement;
    const _originalNextSibling = modalPagEl.nextSibling;
    const wizardEl = document.getElementById('modal-sync-wizard');
    const _host = wizardEl || document.body;
    _host.appendChild(modalPagEl);

    modalPagEl.style.zIndex = '2200';
    modalPagEl.removeAttribute('aria-hidden');
    modalPagEl.removeAttribute('inert');

    window._wizardPagadoresCloseCallback = function() {
        modalPagEl.style.zIndex = '';
        if (_originalParent) {
            if (_originalNextSibling) {
                _originalParent.insertBefore(modalPagEl, _originalNextSibling);
            } else {
                _originalParent.appendChild(modalPagEl);
            }
        }
        window._wizardPagadoresCloseCallback = null;
        fetchAndRenderWizardStep3_Pagadores();
    };

    window.openModalGestionPagadores();
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
    if (typeof window.openModalTipoJ !== 'function') {
        Swal.fire('Info', 'El módulo de justificaciones aún no está cargado. Inicializa Configuración primero.', 'info');
        return;
    }
    const modalTipoJEl = document.getElementById('modal-tipo-justificacion');
    if (!modalTipoJEl) return;

    // Mover DENTRO del wizard para que el FocusTrap de Bootstrap permita focus
    const _originalParent = modalTipoJEl.parentElement;
    const _originalNextSibling = modalTipoJEl.nextSibling;
    const wizardEl = document.getElementById('modal-sync-wizard');
    const _host = wizardEl || document.body;
    _host.appendChild(modalTipoJEl);

    modalTipoJEl.style.zIndex = '2200';
    modalTipoJEl.removeAttribute('aria-hidden');
    modalTipoJEl.removeAttribute('inert');

    window._wizardTipoJCloseCallback = function() {
        modalTipoJEl.style.zIndex = '';
        if (_originalParent) {
            if (_originalNextSibling) {
                _originalParent.insertBefore(modalTipoJEl, _originalNextSibling);
            } else {
                _originalParent.appendChild(modalTipoJEl);
            }
        }
        window._wizardTipoJCloseCallback = null;
        fetchAndRenderWizardStep4_TiposJ();
    };

    window.openModalTipoJ();
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
    // Guard: tbody-wizard-turnos puede no existir si el panel "No hay turnos" reemplazó
    // la estructura de la tabla (la función de "no turnos" reemplaza .table-responsive).
    // En ese caso reconstruimos la tabla completa antes de continuar.
    let tbody = document.getElementById('tbody-wizard-turnos');
    if (!tbody) {
        const container = document.getElementById('wizard-step-6');
        const tableSection = container && container.querySelector('.table-responsive');
        if (tableSection) {
            tableSection.innerHTML = `
                <table class="table table-bordered align-middle table-sm">
                    <thead class="table-light sticky-top">
                        <tr><th>Área a sincronizar</th><th>Turno Recomendado / Seleccionado</th></tr>
                    </thead>
                    <tbody id="tbody-wizard-turnos"></tbody>
                </table>`;
            tbody = document.getElementById('tbody-wizard-turnos');
        }
    }
    // Si aún no existe (el DOM del wizard no está cargado), salir silenciosamente
    if (!tbody) return;

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

        // Guard post-await: si el wizard fue cerrado mientras esperábamos la respuesta,
        // el tbody puede haber sido desconectado del DOM → evitar el error 'document.contains of null'
        if (!document.contains(tbody)) return;

        if (!response.ok) throw new Error("Error obteniendo turnos");
        const res = await response.json();

        window._wizardState.turnosDisponibles = res.turnos || [];
        window._wizardState.preAsignacionesTurnos = res.pre_asignaciones || {};

        if (!document.contains(tbody)) return; // Re-check after state update
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

        // Generar radio cards por área
        areasList.forEach((area, idx) => {
            const selectedTurnoId = String(
                window._wizardState.resoluciones.turnos[area] ||
                window._wizardState.preAsignacionesTurnos[area] ||
                (window._wizardState.turnosDisponibles.find(t => t.es_default)?.id) ||
                (window._wizardState.turnosDisponibles[0]?.id) || ''
            );

            const cardsHTML = window._wizardState.turnosDisponibles.map(t => {
                const isChecked = String(t.id) === selectedTurnoId ? 'checked' : '';
                const tipoBadge = t.tipo_programacion === 'FLEXIBLE_BOLSA'
                    ? '<span class="badge bg-warning text-dark">Bolsa de Horas</span>'
                    : '<span class="badge bg-primary">Ciclo Inteligente</span>';
                const semLabel = (t.num_semanas || 1) > 1
                    ? `${t.num_semanas} opciones`
                    : '1 opción';
                const hrsLabel = t.meta_horas_semanales
                    ? `${t.meta_horas_semanales} hrs/sem`
                    : '';

                return `
                <label class="wiz-turno-card${isChecked ? ' selected' : ''}"
                       for="wiz-radio-${idx}-${t.id}">
                    <input type="radio"
                           name="wiz-turno-area-${idx}"
                           id="wiz-radio-${idx}-${t.id}"
                           class="wiz-radio-turno"
                           data-area="${area}"
                           value="${t.id}"
                           ${isChecked}
                           onchange="this.closest('.wiz-turno-cards').querySelectorAll('.wiz-turno-card').forEach(c=>c.classList.remove('selected')); this.closest('.wiz-turno-card').classList.add('selected')">
                    <div class="wiz-turno-card-body">
                        <div class="wiz-turno-card-name">${t.nombre}</div>
                        <div class="wiz-turno-card-meta">
                            ${tipoBadge}
                            ${hrsLabel ? `<span class="text-muted small">${hrsLabel}</span>` : ''}
                            <span class="text-muted small">${semLabel}</span>
                        </div>
                    </div>
                </label>`;
            }).join('');

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="fw-bold align-middle">${area}</td>
                <td><div class="wiz-turno-cards">${cardsHTML}</div></td>
            `;
            tbody.appendChild(tr);
        });

    } catch (e) {
        console.error(e);
        if (document.contains(tbody)) {
            tbody.innerHTML = `<tr><td colspan="2" class="text-danger text-center">Error al cargar turnos.</td></tr>`;
        }
    }
}

function guardarSeleccionesPaso3() {
    const areasList = getConsolidatedAreas();
    areasList.forEach((area, idx) => {
        const radioChecked = document.querySelector(
            `input[name="wiz-turno-area-${idx}"]:checked`
        );
        window._wizardState.resoluciones.turnos[area] =
            radioChecked ? parseInt(radioChecked.value) : null;
    });
    return true;
}

// ==========================================
// PASO 4: BONOS
// ==========================================
async function fetchAndRenderWizardStep4() {
    // Guard: tbody-wizard-bonos puede no existir si el panel "Sin bonos" reemplazó la tabla.
    let tbody = document.getElementById('tbody-wizard-bonos');
    if (!tbody) {
        const container = document.getElementById('wizard-step-5');
        const tableSection = container && container.querySelector('.table-responsive');
        if (tableSection) {
            tableSection.innerHTML = `
                <table class="table table-bordered align-middle table-sm">
                    <thead class="table-light sticky-top">
                        <tr><th>Área</th><th>Bonos Asignados</th></tr>
                    </thead>
                    <tbody id="tbody-wizard-bonos"></tbody>
                </table>`;
            tbody = document.getElementById('tbody-wizard-bonos');
        }
    }
    if (!tbody) return;

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

        // Guard post-await: el wizard puede haberse cerrado mientras esperábamos
        if (!document.contains(tbody)) return;

        if (!response.ok) throw new Error("Error obteniendo bonos");
        const res = await response.json();

        window._wizardState.bonosDisponibles = res.bonos || [];
        window._wizardState.preAsignacionesBonos = res.pre_asignaciones || {};

        if (!document.contains(tbody)) return;
        tbody.innerHTML = '';

        if (areasList.length === 0) {
            tbody.innerHTML = `<tr><td colspan="2" class="text-center text-muted">No hay áreas seleccionadas.</td></tr>`;
            return;
        }

        if (window._wizardState.bonosDisponibles.length === 0) {
            // Sin bonos creados: ofrecer crear uno directamente
            tbody.innerHTML = `
                <tr>
                    <td colspan="2" class="p-0 border-0">
                        <div class="alert alert-info border-0 shadow-sm d-flex align-items-start gap-3 p-4 rounded-3 m-0">
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
                    </td>
                </tr>
            `;
            return;
        }

        areasList.forEach((area, idx) => {
            // Recuperar seleccionados previamente
            let selectedBonosIds = window._wizardState.resoluciones.bonos[area] || window._wizardState.preAsignacionesBonos[area] || [];

            // Construir chips de bonos con checkbox + botón editar
            const bonosCheckboxes = window._wizardState.bonosDisponibles.map(b => {
                const checked = selectedBonosIds.includes(b.id) ? 'checked' : '';
                return `
                    <div class="wiz-bono-chip ${checked ? 'selected' : ''}">
                        <input class="wiz-chk-bono" type="checkbox" id="wiz-bono-${idx}-${b.id}" 
                               data-area="${area}" value="${b.id}" ${checked}
                               onchange="this.closest('.wiz-bono-chip').classList.toggle('selected', this.checked)">
                        <label class="wiz-bono-chip-label" for="wiz-bono-${idx}-${b.id}">${b.nombre}</label>
                        <button type="button" class="wiz-bono-edit-btn" 
                                onclick="window._wizardEditarBono(${b.id})"
                                title="Editar reglas de este bono">
                            <i class="bi bi-pencil-fill"></i>
                        </button>
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
        if (document.contains(tbody)) {
            tbody.innerHTML = `<tr><td colspan="2" class="text-danger text-center">Error al cargar bonos.</td></tr>`;
        }
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
        // Incluir cargos conocidos desmarcados en el paso 2 como ignorados
        const cargosConocidosResol = window._wizardState.resoluciones.cargos_conocidos || {};
        for (const [cargo, activo] of Object.entries(cargosConocidosResol)) {
            if (activo === false && !ignoredCargos.includes(cargo)) {
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

        const tbodyHtml = empList.map((e, idx) => {
            // Tipo: badge según si es nuevo, tiene cambio de área, o ya existe
            let tipoBadge = '';
            if (e.es_nuevo) {
                tipoBadge = '<span class="badge bg-success">NUEVO</span>';
            } else if (e.cambio_area) {
                tipoBadge = '<span class="badge bg-warning text-dark">CAMBIO ÁREA</span>';
            } else {
                tipoBadge = '<span class="badge bg-secondary">EXISTENTE</span>';
            }

            // Estado activo en sistema local (null = no existe localmente)
            let estadoBadge = '';
            if (e.activo_local === null) {
                estadoBadge = '<span class="badge bg-info text-dark">Sin registro</span>';
            } else if (e.activo_local) {
                estadoBadge = '<span class="badge bg-success">Activo</span>';
            } else {
                estadoBadge = '<span class="badge bg-secondary">Inactivo</span>';
            }

            return `
            <tr data-estado="${e.activo_local ? 'activo' : 'inactivo'}">
                <td class="text-center align-middle">
                    <input type="checkbox" class="form-check-input wiz-chk-emp" data-rut="${e.rut}" checked>
                </td>
                <td class="text-nowrap">${e.rut}</td>
                <td>${e.nombre || ''}</td>
                <td class="text-muted small">${e.cargo || '-'}</td>
                <td>${e.area || '<span class="text-danger">Sin Área</span>'}</td>
                <td>${tipoBadge}</td>
                <td>${estadoBadge}</td>
            </tr>`;
        }).join('');

        listContainer.innerHTML = `
            <div class="table-responsive" style="max-height: 300px;">
                <table class="table table-sm table-hover align-middle mb-0" style="font-size: 0.85rem;">
                    <thead class="table-light sticky-top">
                        <tr>
                            <th class="text-center"><input type="checkbox" class="form-check-input" id="wiz-chk-emp-all" checked onchange="document.querySelectorAll('.wiz-chk-emp').forEach(chk => chk.checked = this.checked)"></th>
                            <th>RUT</th>
                            <th>Nombre</th>
                            <th>Cargo</th>
                            <th>Área</th>
                            <th>Tipo</th>
                            <th>Estado Local</th>
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
// BUG-01 FIX: Funciones fantasma del Paso 7 (Preview)
// Declaradas en el HTML pero nunca implementadas
// ==========================================
window.filterWizardEmpleados = function() {
    const searchInput = document.getElementById('wizard-emp-search');
    const typeFilter  = document.getElementById('wizard-emp-filter-type');
    const search = searchInput ? searchInput.value.toLowerCase() : '';
    const type   = typeFilter  ? typeFilter.value : '';

    document.querySelectorAll('#wizard-empleados-list tbody tr').forEach(tr => {
        const text = tr.textContent.toLowerCase();
        const matchText = text.includes(search);
        const matchType = !type || tr.dataset.estado === type;
        tr.style.display = (matchText && matchType) ? '' : 'none';
    });

    // Actualizar contador visible
    const visible = document.querySelectorAll('#wizard-empleados-list tbody tr:not([style*="none"])').length;
    const counter = document.getElementById('wizard-emp-counter');
    if (counter) counter.textContent = `${visible} visibles`;
};

window.toggleAllWizardEmps = function(checked) {
    document.querySelectorAll('.wiz-chk-emp').forEach(chk => {
        // Solo marcar los visibles (no los filtrados)
        const tr = chk.closest('tr');
        if (!tr || tr.style.display !== 'none') {
            chk.checked = checked;
        }
    });
};

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

    // ── IMPORTANTE: Cerrar el wizard ANTES de mostrar el SweetAlert2 ──────────
    // Si mostramos Swal mientras el wizard está abierto, el backdrop del wizard
    // queda sobre el Swal (visualmente oculto) hasta que el usuario cierra el wizard.
    // Cerrando primero el wizard, el Swal aparece limpiamente sobre fondo gris.
    // Usamos el patrón seguro dispose+blur+manual-hide (NO hide() con animación).
    const modalEl = document.getElementById('modal-sync-wizard');
    const modalInstance = modalEl ? bootstrap.Modal.getInstance(modalEl) : null;
    if (modalInstance) modalInstance.dispose();
    if (modalEl) {
        modalEl.querySelectorAll('input, button, select, textarea, a, [tabindex]')
            .forEach(el => el.blur());
        modalEl.blur();
        document.body.setAttribute('tabindex', '-1');
        document.body.focus();
        document.body.removeAttribute('tabindex');
        modalEl.classList.remove('show');
        modalEl.style.display = 'none';
    }
    // Limpiar artefactos Bootstrap (backdrop, body classes)
    document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
    document.body.classList.remove('modal-open');
    document.body.style.removeProperty('overflow');
    document.body.style.removeProperty('padding-right');
    // ─────────────────────────────────────────────────────────────────────────

    // Ahora mostrar confirmación (wizard ya está cerrado, Swal aparece limpio)
    const confirmResult = await Swal.fire({
        title: '¿Iniciar sincronización?',
        text: filterMsg,
        icon: 'question',
        showCancelButton: true,
        confirmButtonText: 'Sí, sincronizar',
        cancelButtonText: 'Cancelar'
    });

    if (!confirmResult.isConfirmed) return;

    // 2. Preparar filtros globales
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

    // 4. Construir payload y llamar función puente en main.js
    const payload = {
        areas: window._syncSelectedAreas.length > 0 ? window._syncSelectedAreas : null,
        ruts: selectedRuts,
        ignored_cargos: ignoredCargos.length > 0 ? ignoredCargos : null
    };

    // Disparar sincronización (pequeño delay para que Swal cierre primero)
    setTimeout(() => {
        if (typeof window._executeSyncFromWizard === 'function') {
            window._executeSyncFromWizard(payload);
        } else {
            console.error('[Wizard] _executeSyncFromWizard no disponible');
            Swal.fire('Error', 'Función de sincronización no disponible.', 'error');
        }
    }, 300);
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

        const wizardModalEl = document.getElementById('modal-sync-wizard');
        const wizardInstance = wizardModalEl ? bootstrap.Modal.getInstance(wizardModalEl) : null;

        // IMPORTANTE: NO usar wizardInstance.hide() aquí.
        // hide() usa animación CSS fade: al FINAL de la animación llama _hideModal()
        // que pone aria-hidden DESPUÉS de que FocusTrap.deactivate() restaura el foco
        // → si _returnFocusElement era btn-close, queda con foco → WARNING.
        // Usamos el mismo patrón seguro de _wizardOpenChildModal:
        // 1. dispose() mata el FocusTrap, 2. blur, 3. inert para neutralizar el elemento.
        if (wizardInstance) wizardInstance.dispose();
        if (wizardModalEl) {
            wizardModalEl.querySelectorAll('input, button, select, textarea, a, [tabindex]')
                .forEach(el => el.blur());
            wizardModalEl.blur();
            document.body.setAttribute('tabindex', '-1');
            document.body.focus();
            document.body.removeAttribute('tabindex');
            wizardModalEl.classList.remove('show');
            wizardModalEl.style.display = 'none';
            wizardModalEl.setAttribute('inert', '');  // ← previene cualquier foco futuro
        }
        // Limpiar artefactos de Bootstrap
        setTimeout(() => {
            document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
            document.body.classList.remove('modal-open');
            document.body.style.removeProperty('overflow');
            document.body.style.removeProperty('padding-right');
        }, 0);

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
                                // Quitar inert antes de re-mostrar
                                wizardModalEl.removeAttribute('inert');
                                window._wizardState.currentStep = 6;
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
window._wizardCrearBono = async function() {
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

    // 1. Inicializar la UI de configuración si aún no se ha hecho
    //    (registra form-bono.onsubmit, loadBonos, loadPagadores, etc.)
    if (typeof initConfiguracionUI === 'function' && !window._config_initialized) {
        initConfiguracionUI(); // dispara loadMetadata() internamente (sin await)
    }

    // 2. RACE CONDITION FIX: esperar explícitamente a que los cargos estén listos.
    //    initConfiguracionUI dispara loadMetadata() sin await; gracias al patrón singleton
    //    en loadMetadata(), este await reutiliza la misma Promise (sin doble petición HTTP).
    if (typeof loadMetadata === 'function' && typeof globalCargosList !== 'undefined' && globalCargosList.length === 0) {
        console.log('[Wizard-Bono] Esperando catálogo de cargos...');
        await loadMetadata();
        console.log(`[Wizard-Bono] Cargos listos: ${globalCargosList.length}`);
    }

    // Mover modal-bono a document.body para evitar que el transform CSS del wizard
    // rompa position:fixed en los dropdowns de cargos (Bootstrap modal usa transform
    // en su animación, lo que hace que fixed children se posicionen relativos al modal).
    const modalBonoEl = document.getElementById('modal-bono');
    if (!modalBonoEl) { openModalBono(); return; }

    const _bonoHost = document.body;
    const _bonoOriginalParent = modalBonoEl.parentElement;
    const _bonoOriginalNext = modalBonoEl.nextSibling;
    _bonoHost.appendChild(modalBonoEl);

    modalBonoEl.style.zIndex = '2200';
    modalBonoEl.removeAttribute('aria-hidden');
    modalBonoEl.removeAttribute('inert');

    window._wizardBonoCloseCallback = function() {
        modalBonoEl.style.zIndex = '';
        if (_bonoOriginalParent) {
            if (_bonoOriginalNext) {
                _bonoOriginalParent.insertBefore(modalBonoEl, _bonoOriginalNext);
            } else {
                _bonoOriginalParent.appendChild(modalBonoEl);
            }
        }
        window._wizardBonoCloseCallback = null;
        window._wizardRefrescarBonos();
    };

    openModalBono();

    // Re-inicializar dropdowns DESPUÉS de que el modal esté visible.
    // Popper.js usa getBoundingClientRect() para calcular posición: si se inicializa
    // con el modal oculto (display:none), todos los coords son 0 y el dropdown
    // aparece en la esquina del viewport.
    setTimeout(() => {
        document.querySelectorAll('#modal-bono [data-bs-toggle="dropdown"]').forEach(btn => {
            const inst = bootstrap.Dropdown.getInstance(btn);
            if (inst) inst.dispose();
            new bootstrap.Dropdown(btn, { popperConfig: { strategy: 'fixed' } });
        });
    }, 50);
};

/**
 * Abre el modal de Edición de Bono directamente sobre el wizard.
 * Reutiliza el mismo modal-bono y el patrón de _wizardCrearBono,
 * pero hace un fetch del bono completo (con reglas) para pre-poblar.
 */
window._wizardEditarBono = async function(bonoId) {
    if (typeof openModalBono !== 'function') {
        Swal.fire('Módulo no cargado', 'El módulo de bonos no está inicializado.', 'info');
        return;
    }

    // Inicializar configuración si no se ha hecho
    if (typeof initConfiguracionUI === 'function' && !window._config_initialized) {
        initConfiguracionUI();
    }
    if (typeof loadMetadata === 'function' && typeof globalCargosList !== 'undefined' && globalCargosList.length === 0) {
        await loadMetadata();
    }

    // Obtener el bono completo (con reglas) desde la API
    let bono = null;
    try {
        const token = localStorage.getItem('token');
        const resp = await fetch(`/api/configuracion/bonos/`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const bonos = await resp.json();
        bono = bonos.find(b => b.id === bonoId);
        if (!bono) throw new Error('Bono no encontrado');
    } catch (e) {
        Swal.fire('Error', 'No se pudo cargar el bono: ' + e.message, 'error');
        return;
    }

    // Mover modal-bono a document.body para evitar que el transform CSS del wizard
    // rompa position:fixed en los dropdowns de cargos.
    const modalBonoEl = document.getElementById('modal-bono');
    if (!modalBonoEl) { openModalBono(bono); return; }

    const _bonoHost = document.body;
    const _bonoOriginalParent = modalBonoEl.parentElement;
    const _bonoOriginalNext = modalBonoEl.nextSibling;
    _bonoHost.appendChild(modalBonoEl);

    modalBonoEl.style.zIndex = '2200';
    modalBonoEl.removeAttribute('aria-hidden');
    modalBonoEl.removeAttribute('inert');

    window._wizardBonoCloseCallback = function() {
        modalBonoEl.style.zIndex = '';
        if (_bonoOriginalParent) {
            if (_bonoOriginalNext) {
                _bonoOriginalParent.insertBefore(modalBonoEl, _bonoOriginalNext);
            } else {
                _bonoOriginalParent.appendChild(modalBonoEl);
            }
        }
        window._wizardBonoCloseCallback = null;
        window._wizardRefrescarBonos();
    };

    openModalBono(bono);

    // Re-inicializar dropdowns DESPUÉS de que el modal esté visible.
    setTimeout(() => {
        document.querySelectorAll('#modal-bono [data-bs-toggle="dropdown"]').forEach(btn => {
            const inst = bootstrap.Dropdown.getInstance(btn);
            if (inst) inst.dispose();
            new bootstrap.Dropdown(btn, { popperConfig: { strategy: 'fixed' } });
        });
    }, 50);
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
