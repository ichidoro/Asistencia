/**
 * Universal Synchronization Wizard
 * Centraliza la validación de Áreas, Cargos, Géneros, Turnos y Bonos.
 */

// ── INTERCEPTOR SWAL GLOBAL PARA WIZARD ──────────────────────────────────────
// Si el wizard está abierto, redirige las alertas de SweetAlert2 al interior del 
// modal del wizard. Esto evita que queden ocultas por la colisión de z-index y backdrops.
(function _installSwalWizardInterceptor() {
    if (typeof Swal !== 'undefined' && Swal.fire) {
        const originalSwalFire = Swal.fire;
        Swal.fire = function(...args) {
            const wizardEl = document.getElementById('modal-sync-wizard');
            const wizardIsShow = wizardEl && (wizardEl.classList.contains('show') || wizardEl.style.display === 'block');
            
            if (wizardIsShow) {
                if (args.length === 1 && typeof args[0] === 'object' && args[0] !== null) {
                    if (!args[0].target) {
                        args[0].target = '#modal-sync-wizard';
                    }
                } else if (args.length > 0 && typeof args[0] === 'string') {
                    const obj = {
                        title: args[0],
                        target: '#modal-sync-wizard'
                    };
                    if (args.length > 1) {
                        obj.html = args[1];
                    }
                    if (args.length > 2) {
                        obj.icon = args[2];
                    }
                    args = [obj];
                }
            }
            return originalSwalFire.apply(this, args);
        };
    }
})();

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
    },
    // Nuevas propiedades para Onboarding integrado (Pasos 8-10)
    newEmployeesDetalles: null,
    onboardingCompletados: {},
    selectedOnboardingEmpId: null,
    employeesFullData: null,
    turnosIndividualesAsignados: {},
    fechasIndividualesAsignadas: {},
    syncBioalbaIndividuales: {},
    syncPayload: null,
    synchronizedEmployees: []
};

window.closeSyncWizard = async function(force = false) {
    const step = window._wizardState.currentStep;
    
    if (!force && (step === 9 || step === 10)) {
        const confirm = await Swal.fire({
            title: '¿Cerrar asistente?',
            text: 'Si cierras el asistente perderás el progreso no guardado de las fichas y asignaciones.',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Sí, cerrar',
            cancelButtonText: 'No, continuar'
        });
        if (!confirm.isConfirmed) return;
    }

    // Limpiar estado para evitar que F5 lo vuelva a abrir
    window.clearWizardStateFromLocalStorage();

    // FIX: Invalidar cachés de áreas al cerrar el wizard.
    // Áreas nuevas sincronizadas deben aparecer en todos los módulos.
    window._cachedAreas = null;
    window._cachedMetadata = null;
    // Resetear flag de módulos lazy para que recarguen áreas al navegar
    if (typeof asignacionesInitialized !== 'undefined') window.asignacionesInitialized = false;
    // Refrescar datos de fondo para que los selectores se actualicen al navegar
    if (typeof window.loadStats === 'function') window.loadStats();
    if (typeof window.loadEmpleados === 'function') window.loadEmpleados();
    // Refrescar áreas en reportes si existe
    if (typeof window.populateReportAreas === 'function') window.populateReportAreas();

    const modalEl = document.getElementById('modal-sync-wizard');
    if (!modalEl) return;
    const modalInstance = bootstrap.Modal.getInstance(modalEl);
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

    // Limpiar onboarding y detalles de empleados de sesiones anteriores
    window._wizardState.turnosDisponibles = [];
    window._wizardState.bonosDisponibles = [];
    window._wizardState.preAsignacionesTurnos = {};
    window._wizardState.preAsignacionesBonos = {};
    window._wizardState.newEmployeesDetalles = null;
    window._wizardState.onboardingCompletados = {};
    window._wizardState.selectedOnboardingEmpId = null;
    window._wizardState.employeesFullData = null;
    window._wizardState.turnosIndividualesAsignados = {};
    window._wizardState.fechasIndividualesAsignadas = {};
    window._wizardState.syncBioalbaIndividuales = {};
    window._wizardState.syncPayload = null;
    window._wizardState.synchronizedEmployees = [];

    // Limpiar localStorage de sesiones anteriores del wizard
    window.clearWizardStateFromLocalStorage();

    // Guardar estado inicial limpio en localStorage
    saveWizardStateToLocalStorage();

    // FIX: NO pre-poblar áreas. Los checkboxes deben arrancar desmarcados
    // para que el usuario elija explícitamente qué áreas importar.
    // (Antes se pre-poblaba con "_NEW_" haciendo que todos aparecieran marcados)

    // Ocultar todos los steps y mostrar el 1
    updateWizardUI();

    const wizardModal = new bootstrap.Modal(document.getElementById('modal-sync-wizard'));
    wizardModal.show();
};

function updateWizardUI() {
    const TOTAL_STEPS = 10;
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
    const btnPrev = document.getElementById('btn-wizard-prev');
    const btnNext = document.getElementById('btn-wizard-next');
    const btnFinish = document.getElementById('btn-wizard-finish');

    // Deshabilitar "Anterior" en pasos 8 y 9 (sync hecho, no se puede volver)
    btnPrev.disabled = (step === 1 || step === 8 || step === 9);
    
    if (step === 7) {
        // En preview de empleados, el botón siguiente es para "Sincronizar"
        btnNext.classList.add('d-none');
        btnFinish.classList.remove('d-none');
        btnFinish.onclick = window.confirmWizardSync;
        btnFinish.innerHTML = '<i class="bi bi-play-circle"></i> Sincronizar Empleados';
    } else if (step === 8) {
        // En streaming, los botones se controlan por el estado de la sync
        btnNext.classList.add('d-none');
        btnFinish.classList.add('d-none');
    } else if (step === 10) {
        // En paso final
        btnNext.classList.add('d-none');
        btnFinish.classList.remove('d-none');
        btnFinish.onclick = window.finishWizardOnboarding;
        btnFinish.innerHTML = '<i class="bi bi-gear-wide-connected"></i> Finalizar y Recalcular';
    } else {
        btnNext.classList.remove('d-none');
        btnNext.disabled = false;
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
    if (step === 8) {
        if (!window._wizardState.newEmployeesDetalles) {
            window.startWizardSSESync(window._wizardState.syncPayload);
        } else {
            window.renderWizardStep8Completed();
        }
    }
    if (step === 9) renderWizardStep9();
    if (step === 10) renderWizardStep10();
}

window.wizardNextStep = async function() {
    const btnNext = document.getElementById('btn-wizard-next');
    if (btnNext) {
        if (btnNext.getAttribute('data-loading') === 'true') return;
        btnNext.setAttribute('data-loading', 'true');
        btnNext.disabled = true;
    }

    try {
        const TOTAL_STEPS = 10;
        const step = window._wizardState.currentStep;

        // --- PASO 1: Áreas ---
        if (step === 1) {
            if (!guardarSeleccionesPaso1()) return;

            const resoluciones = window._wizardState.resoluciones.areas;
            const areasConocidas = window._wizardState.resoluciones.areas_conocidas || {};
            const tieneSeleccion = Object.values(resoluciones).some(v => v !== '_IGNORE_') || Object.values(areasConocidas).some(v => v === true);
            if (!tieneSeleccion) {
                Swal.fire('Atención', 'Debes seleccionar al menos un área para importar.', 'warning');
                return;
            }
            // Realizar commit parcial para que las áreas existan en BD (necesario para paso 3: Bonos y paso 4: Turnos)
            try {
                const resp = await fetch('/api/sync/wizard/commit/areas/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
                    body: JSON.stringify({ areas: resoluciones })
                });
                if (resp.ok) {
                    const data = await resp.json();
                    window._wizardState.sessionCreated.areas = data.creadas || [];
                    console.log('[Wizard] Áreas persistidas:', data.creadas);
                }
            } catch (e) {
                console.error('[Wizard] Error commiteando áreas:', e);
                Swal.fire('Error', 'No se pudieron guardar las áreas.', 'error');
                return;
            }
        }

        // --- PASO 2: Cargos ---
        if (step === 2) {
            if (!guardarSeleccionesPaso2()) return;
            if (typeof window.loadMetadata === 'function') {
                await window.loadMetadata(true);
            }
            // Realizar commit parcial de cargos
            try {
                const resp = await fetch('/api/sync/wizard/commit/cargos/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
                    body: JSON.stringify({ cargos: window._wizardState.resoluciones.cargos })
                });
                if (resp.ok) {
                    const data = await resp.json();
                    window._wizardState.sessionCreated.cargos = data.creados || [];
                    console.log('[Wizard] Cargos persistidos:', data.creados);
                }
            } catch (e) {
                console.error('[Wizard] Error commiteando cargos:', e);
                Swal.fire('Error', 'No se pudieron guardar los cargos.', 'error');
                return;
            }
        }

        // --- PASO 5: Bonos ---
        if (step === 5) {
            guardarSeleccionesPaso5_Bonos();
        }

        // --- PASO 6: Turnos ---
        if (step === 6) {
            if (!guardarSeleccionesPaso6_Turnos()) return;
        }

        // --- Avanzar ---
        if (step < TOTAL_STEPS) {
            window._wizardState.currentStep++;
            saveWizardStateToLocalStorage();
            updateWizardUI();
        }
    } finally {
        if (btnNext) {
            btnNext.removeAttribute('data-loading');
            btnNext.disabled = false;
        }
    }
};

window.wizardPrevStep = async function() {
    const step = window._wizardState.currentStep;
    if (step <= 1 || step === 8 || step === 9) return;

    window._wizardState.currentStep--;
    saveWizardStateToLocalStorage();
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
                if (e.target.checked) {
                    let changed = false;
                    document.querySelectorAll('.check-area-conocida').forEach(el => {
                        if (el.checked) { el.checked = false; changed = true; }
                    });
                    if (changed) {
                        const Toast = Swal.mixin({ toast: true, position: 'top-end', showConfirmButton: false, timer: 3000 });
                        Toast.fire({ icon: 'info', title: 'Áreas Conocidas desmarcadas para priorizar Nuevas' });
                    }
                }
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
            const chk = tr.querySelector('.check-area-conocida');
            chk.addEventListener('change', (e) => {
                if (e.target.checked) {
                    let changed = false;
                    document.querySelectorAll('.check-area').forEach(el => {
                        if (el.checked) {
                            el.checked = false;
                            changed = true;
                            const inputId = el.id.replace('wiz-chk-area-', 'wiz-inp-area-');
                            const inpObj = document.getElementById(inputId);
                            if (inpObj) inpObj.disabled = true;
                        }
                    });
                    if (changed) {
                        const Toast = Swal.mixin({ toast: true, position: 'top-end', showConfirmButton: false, timer: 3000 });
                        Toast.fire({ icon: 'info', title: 'Áreas Nuevas desmarcadas para priorizar Conocidas' });
                    }
                }
            });
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
                if (e.target.checked) {
                    let changed = false;
                    document.querySelectorAll('.check-cargo-conocido').forEach(el => {
                        if (el.checked) { el.checked = false; changed = true; }
                    });
                    if (changed) {
                        const Toast = Swal.mixin({ toast: true, position: 'top-end', showConfirmButton: false, timer: 3000 });
                        Toast.fire({ icon: 'info', title: 'Cargos Conocidos desmarcados para priorizar Nuevos' });
                    }
                }
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
            const chk = tr.querySelector('.check-cargo-conocido');
            chk.addEventListener('change', (e) => {
                if (e.target.checked) {
                    let changed = false;
                    document.querySelectorAll('.check-cargo').forEach(el => {
                        if (el.checked) {
                            el.checked = false;
                            changed = true;
                            const inputId = el.id.replace('wiz-chk-cargo-', 'wiz-inp-cargo-');
                            const inpObj = document.getElementById(inputId);
                            if (inpObj) inpObj.disabled = true;
                        }
                    });
                    if (changed) {
                        const Toast = Swal.mixin({ toast: true, position: 'top-end', showConfirmButton: false, timer: 3000 });
                        Toast.fire({ icon: 'info', title: 'Cargos Nuevos desmarcados para priorizar Conocidos' });
                    }
                }
            });
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
            // Filtrar turnos: solo los asignados explícitamente al área actual.
            const turnosParaArea = window._wizardState.turnosDisponibles.filter(t => {
                return t.areas && t.areas.some(a => a.toUpperCase() === area.toUpperCase());
            });

            // Selección default: resolución previa > pre-asignación existente > primer turno del área
            const selectedTurnoId = String(
                window._wizardState.resoluciones.turnos[area] ||
                window._wizardState.preAsignacionesTurnos[area] ||
                (turnosParaArea.find(t => t.es_default)?.id) ||
                (turnosParaArea[0]?.id) || ''
            );

        const cardsHTML = turnosParaArea.map(t => {
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
            // Badge de área(s) del turno
            const areasBadges = (t.areas && t.areas.length > 0)
                ? t.areas.map(a => `<span class="badge bg-secondary bg-opacity-25 text-secondary border border-secondary border-opacity-25 small">${a}</span>`).join(' ')
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
                    <div class="wiz-turno-card-areas mt-1">${areasBadges}</div>
                </div>
            </label>`;
        }).join('');

        // Si no hay turnos para esta área, mostrar aviso con opción de crear
        const cardsContent = turnosParaArea.length > 0 ? cardsHTML : `
            <div class="alert alert-warning py-2 px-3 mb-0 small d-flex align-items-center gap-2">
                <i class="bi bi-exclamation-triangle-fill"></i>
                No hay turnos asignados a <strong>${area}</strong>.
                <button class="btn btn-sm btn-outline-primary ms-2" onclick="window._wizardIrACrearTurno()">
                    <i class="bi bi-plus-circle me-1"></i>Crear Turno
                </button>
            </div>`;

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="fw-bold align-middle">${area}</td>
                <td><div class="wiz-turno-cards">${cardsContent}</div></td>
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
        const selectedCargos = [];
        // Cargos nuevos seleccionados
        for (const [cargo, resolucion] of Object.entries(window._wizardState.resoluciones.cargos)) {
            if (resolucion !== "_IGNORE_") {
                selectedCargos.push(cargo);
            }
        }
        // Cargos conocidos activos
        const cargosConocidosResol = window._wizardState.resoluciones.cargos_conocidos || {};
        const cargosConocidosData = (window._wizardState.data && window._wizardState.data.cargos_conocidos) || [];
        cargosConocidosData.forEach(cargo => {
            if (cargosConocidosResol[cargo] !== false && !selectedCargos.includes(cargo)) {
                selectedCargos.push(cargo);
            }
        });

        // Construir el mapa de resoluciones COMPLETO para el backend:
        // incluye tanto las áreas nuevas (resoluciones.areas) como las áreas CONOCIDAS activas.
        // Sin esto, las áreas conocidas no llegan al backend y todos sus empleados quedan filtrados fuera.
        const resolucionesCompletas = { ...window._wizardState.resoluciones.areas };

        // Inyectar áreas conocidas activas con su propio nombre como valor (identidad)
        const areasConocidas = (window._wizardState.data && window._wizardState.data.areas_conocidas) || [];
        const areasConocidosResol = window._wizardState.resoluciones.areas_conocidas || {};
        areasConocidas.forEach(area => {
            // Solo incluir si no fue explícitamente desmarcada por el usuario
            if (areasConocidosResol[area] !== false) {
                resolucionesCompletas[area] = area; // el área ya existe localmente, mapea a sí misma
            }
        });

        const requestBody = {
            resoluciones_areas: resolucionesCompletas,
            selected_cargos: selectedCargos
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

        const MAX_WIZ_SYNC = 10;

        listContainer.innerHTML = `
            <div class="d-flex align-items-center justify-content-between mb-2 px-1">
                <span class="text-muted small">Selecciona los empleados a sincronizar</span>
                <span id="wiz-emp-limit-badge" class="badge bg-primary">0 / ${MAX_WIZ_SYNC} seleccionados</span>
            </div>
            <div class="table-responsive" style="max-height: 280px;">
                <table class="table table-sm table-hover align-middle mb-0" style="font-size: 0.85rem;">
                    <thead class="table-light sticky-top">
                        <tr>
                            <th class="text-center"><input type="checkbox" class="form-check-input" id="wiz-chk-emp-all" checked onchange="window.toggleAllWizardEmps(this.checked)"></th>
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

        // Aplicar límite en tiempo real: cada checkbox llama a wizEnforceSyncLimit
        listContainer.querySelectorAll('.wiz-chk-emp').forEach(chk => {
            chk.addEventListener('change', () => window.wizEnforceSyncLimit());
        });
        // Estado inicial del badge (todos checked al renderizar)
        window.wizEnforceSyncLimit();

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

window.wizEnforceSyncLimit = function() {
    const MAX = 10;
    const allChks = document.querySelectorAll('.wiz-chk-emp');
    const checkedChks = document.querySelectorAll('.wiz-chk-emp:checked');
    const badge = document.getElementById('wiz-emp-limit-badge');

    // Actualizar badge contador
    if (badge) {
        badge.textContent = `${checkedChks.length} / ${MAX} seleccionados`;
        badge.className = checkedChks.length >= MAX
            ? 'badge bg-warning text-dark'
            : 'badge bg-primary';
    }

    // Si superaron el límite, desmarcar el último que se marcó (el que acaba de cambiar)
    if (checkedChks.length > MAX) {
        // Desmarcar el checkbox que acaba de activarse (el evento change ya corrió)
        // Buscamos el último checked que no tenga el atributo data-wiz-locked (temporal)
        const last = Array.from(checkedChks).at(-1);
        if (last) {
            last.checked = false;
            // Mostrar mensaje no-intrusivo en el badge
            if (badge) {
                badge.textContent = `Máx. ${MAX} — deselecciona uno para continuar`;
                badge.className = 'badge bg-danger';
                setTimeout(() => window.wizEnforceSyncLimit(), 2500);
            }
        }
    }

    // Deshabilitar checkboxes sin marcar si ya se alcanzó el límite
    const currentChecked = document.querySelectorAll('.wiz-chk-emp:checked').length;
    allChks.forEach(chk => {
        if (!chk.checked) {
            chk.disabled = currentChecked >= MAX;
            chk.title = currentChecked >= MAX ? `Límite de ${MAX} alcanzado` : '';
        } else {
            chk.disabled = false;
            chk.title = '';
        }
    });
};

window.toggleAllWizardEmps = function(checked) {
    document.querySelectorAll('.wiz-chk-emp').forEach(chk => {
        // Solo marcar los visibles (no los filtrados)
        const tr = chk.closest('tr');
        if (!tr || tr.style.display !== 'none') {
            chk.checked = checked;
        }
    });
    // Re-aplicar límite tras toggle masivo
    window.wizEnforceSyncLimit();
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

    // ── GUARDIA: límite de 10 ───────────────────────────
    if (checkedBoxes.length > 10) {
        Swal.fire({
            title: 'Límite superado',
            html: `Máximo <strong>10 empleados</strong> por sincronización.<br>Tienes <strong>${checkedBoxes.length}</strong> seleccionados. Desmarca algunos.`,
            icon: 'warning',
            confirmButtonText: 'Volver a seleccionar'
        });
        return; // wizard sigue abierto
    }

    const selectedRuts = checkedBoxes.length < allBoxes.length
        ? Array.from(checkedBoxes).map(cb => cb.dataset.rut)
        : null;

    // Registrar todos los empleados seleccionados (nuevos y existentes) para el flujo de onboarding/turnos
    window._wizardState.synchronizedEmployees = Array.from(checkedBoxes).map(cb => {
        const tr = cb.closest('tr');
        const isNuevo = tr ? tr.innerHTML.includes('NUEVO') : false;
        return {
            rut: cb.dataset.rut,
            es_nuevo: isNuevo
        };
    });

    const filterMsg = selectedRuts
        ? `${selectedRuts.length} empleado(s) seleccionado(s)`
        : `Todos los ${allBoxes.length} empleado(s)`;

    // Confirmación del inicio de la sincronización
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

    const selectedCargos = [];
    for (const [cargo, resolucion] of Object.entries(window._wizardState.resoluciones.cargos)) {
        if (resolucion !== "_IGNORE_") {
            selectedCargos.push(cargo);
        }
    }
    
    // Incluir cargos conocidos activos
    const cargosConocidosResol = window._wizardState.resoluciones.cargos_conocidos || {};
    const cargosConocidosData = (window._wizardState.data && window._wizardState.data.cargos_conocidos) || [];
    cargosConocidosData.forEach(cargo => {
        if (cargosConocidosResol[cargo] !== false && !selectedCargos.includes(cargo)) {
            selectedCargos.push(cargo);
        }
    });

    window._selectedCargos = selectedCargos;

    const payload = {
        areas: window._syncSelectedAreas.length > 0 ? window._syncSelectedAreas : null,
        ruts: selectedRuts,
        selected_cargos: selectedCargos.length > 0 ? selectedCargos : null
    };

    // Guardar el payload en el estado para posibles reintentos
    window._wizardState.syncPayload = payload;

    // MEGA-COMMIT DE WIZARD ANTES DE INICIAR SINCRONIZACIÓN
    Swal.fire({
        title: 'Guardando configuración...',
        html: 'Por favor espere mientras se aplican las configuraciones (Áreas, Cargos, Turnos).',
        allowOutsideClick: false,
        didOpen: () => {
            Swal.showLoading();
        }
    });

    try {
        const commitPayload = {
            areas: window._wizardState.resoluciones.areas,
            cargos: window._wizardState.resoluciones.cargos,
            generos: window._wizardState.resoluciones.generos || [],
            turnos: window._wizardState.resoluciones.turnos || {},
            bonos: window._wizardState.resoluciones.bonos || {}
        };

        const resp = await fetch('/api/sync/wizard/commit-all/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
            body: JSON.stringify(commitPayload)
        });

        if (!resp.ok) throw new Error(await resp.text());
        
        // Refrescar metadatos
        if (typeof window.loadMetadata === 'function') {
            await window.loadMetadata(true);
        }
        
        Swal.close();

        // Guardar progreso y avanzar a Paso 8 (Progreso streaming SSE)
        window._wizardState.currentStep = 8;
        saveWizardStateToLocalStorage();
        updateWizardUI();

    } catch (e) {
        console.error('[Wizard] Error en Mega-Commit:', e);
        Swal.fire('Error', 'No se pudieron guardar las configuraciones previas: ' + e.message, 'error');
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
    //    Forzamos la recarga (true) para asegurar que los cargos recién creados 
    //    en el Wizard (Paso 2) estén disponibles en los selectores del bono.
    if (typeof loadMetadata === 'function' && typeof globalCargosList !== 'undefined') {
        console.log('[Wizard-Bono] Forzando actualización del catálogo de cargos...');
        await loadMetadata(true);
        console.log(`[Wizard-Bono] Cargos listos: ${globalCargosList.length}`);
    }

    // Mover modal-bono a document.body para evitar que el transform CSS del wizard
    // rompa position:fixed en los dropdowns de cargos (Bootstrap modal usa transform
    // en su animación, lo que hace que fixed children se posicionen relativos al modal).
    const modalBonoEl = document.getElementById('modal-bono');
    if (!modalBonoEl) { openModalBono(); return; }

    // Mover modal-bono a document.body para que z-index:2200 lo ponga encima del wizard.
    // Tambien ponemos 'inert' en el wizard-dialog para deshabilitar su FocusTrap
    // mientras el modal-bono esta abierto (sin inert, Bootstrap captura focus/clicks).
    const wizardDialog = document.querySelector('#modal-sync-wizard .modal-dialog');
    if (wizardDialog) wizardDialog.setAttribute('inert', '');

    // GUARDAR posición original en variables LOCALES (no globales no definidas)
    const _bonoOriginalParent = modalBonoEl.parentElement;
    const _bonoOriginalNext   = modalBonoEl.nextSibling;

    // Mover al body ANTES de que openModalBono lo muestre
    document.body.appendChild(modalBonoEl);

    modalBonoEl.classList.add('bono-wizard-mode');
    modalBonoEl.removeAttribute('aria-hidden');
    modalBonoEl.removeAttribute('inert');

    window._wizardBonoCloseCallback = function() {
        // Restaurar wizard-dialog (quitar inert para que vuelva a ser interactivo)
        if (wizardDialog) wizardDialog.removeAttribute('inert');
        modalBonoEl.classList.remove('bono-wizard-mode');
        // Restaurar posición original en el DOM
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

    // await: esperar a que openModalBono cargue areas Y muestre el modal
    // (el nuevo fix en openModalBono hace el fetch ANTES de display:flex)
    await openModalBono();

    // Re-inicializar dropdowns despues de que el modal este visible.
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
    if (typeof loadMetadata === 'function' && typeof globalCargosList !== 'undefined') {
        await loadMetadata(true);
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

    // Mover modal-bono a document.body + inert en wizard-dialog para deshabilitar
    // el FocusTrap de Bootstrap mientras el modal-bono esta abierto.
    const modalBonoEl = document.getElementById('modal-bono');
    if (!modalBonoEl) { await openModalBono(bono); return; }

    const wizardDialog = document.querySelector('#modal-sync-wizard .modal-dialog');
    if (wizardDialog) wizardDialog.setAttribute('inert', '');

    const _bonoHost = document.body;
    const _bonoOriginalParent = modalBonoEl.parentElement;
    const _bonoOriginalNext = modalBonoEl.nextSibling;
    _bonoHost.appendChild(modalBonoEl);

    modalBonoEl.classList.add('bono-wizard-mode');
    modalBonoEl.removeAttribute('aria-hidden');
    modalBonoEl.removeAttribute('inert');

    window._wizardBonoCloseCallback = function() {
        if (wizardDialog) wizardDialog.removeAttribute('inert');
        modalBonoEl.classList.remove('bono-wizard-mode');
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

    await openModalBono(bono);

    setTimeout(() => {
        document.querySelectorAll('#modal-bono [data-bs-toggle="dropdown"]').forEach(btn => {
            const inst = bootstrap.Dropdown.getInstance(btn);
            if (inst) inst.dispose();
            new bootstrap.Dropdown(btn, { popperConfig: { strategy: 'fixed' } });
        });
    }, 50);
};


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

// =============================================================================
// LÓGICA PASOS 8, 9 Y 10: SINCRONIZACIÓN SSE, COMPLETAR FICHAS Y TURNOS IND.
// =============================================================================

function saveWizardStateToLocalStorage() {
    localStorage.setItem('wizard_state', JSON.stringify(window._wizardState));
}

window.loadWizardStateFromLocalStorage = function() {
    const raw = localStorage.getItem('wizard_state');
    if (!raw) return null;
    try {
        const state = JSON.parse(raw);
        if (state && typeof state === 'object' && state.currentStep) {
            return {
                currentStep: 1,
                data: null,
                turnosDisponibles: [],
                bonosDisponibles: [],
                preAsignacionesTurnos: {},
                preAsignacionesBonos: {},
                resoluciones: { areas: {}, cargos: {}, generos: [], turnos: {}, bonos: {} },
                sessionCreated: { areas: [], cargos: [], generos: [] },
                newEmployeesDetalles: null,
                onboardingCompletados: {},
                selectedOnboardingEmpId: null,
                employeesFullData: null,
                turnosIndividualesAsignados: {},
                fechasIndividualesAsignadas: {},
                syncBioalbaIndividuales: {},
                syncPayload: null,
                ...state
            };
        }
    } catch (e) {
        console.error('Error parsing wizard state from localStorage:', e);
    }
    return null;
};

window.clearWizardStateFromLocalStorage = function() {
    localStorage.removeItem('wizard_state');
    localStorage.removeItem('wizard_completed');
};

window.startWizardSSESync = async function(payload) {
    const logEl = document.getElementById('wizard-sync-log');
    const progressBar = document.getElementById('wizard-sync-progress-bar');
    const percentEl = document.getElementById('wizard-sync-percent');
    const statusTextEl = document.getElementById('wizard-sync-status-text');
    const errorContainer = document.getElementById('wizard-sync-error-container');
    const btnPrev = document.getElementById('btn-wizard-prev');
    const btnNext = document.getElementById('btn-wizard-next');
    const btnCancel = document.querySelector('#modal-sync-wizard button[onclick="closeSyncWizard()"]');
    const btnCloseHeader = document.querySelector('#modal-sync-wizard .btn-close');

    if (logEl) logEl.innerHTML = '[INFO] Iniciando conexión con servidor...<br>';
    if (progressBar) {
        progressBar.style.width = '0%';
        progressBar.classList.remove('bg-danger');
        progressBar.classList.add('progress-bar-animated', 'progress-bar-striped');
    }
    if (percentEl) percentEl.textContent = '0%';
    if (statusTextEl) statusTextEl.textContent = 'Conectando a BioAlba...';
    if (errorContainer) errorContainer.classList.add('d-none');

    if (btnPrev) btnPrev.disabled = true;
    if (btnNext) btnNext.disabled = true;
    if (btnCancel) btnCancel.disabled = true;
    if (btnCloseHeader) btnCloseHeader.disabled = true;

    try {
        const response = await fetch('/api/sync/empleados/now/stream/', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || `Error HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalStats = null;

        // Helper: procesar líneas SSE y despachar eventos
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
                        statusTextEl.textContent = `Sincronizando ${eventData.total || '?'} empleado(s)...`;
                        logEl.innerHTML += `[INFO] Sincronización iniciada: Total ${eventData.total || '?'} empleados.<br>`;
                    } else if (eventType === 'progress') {
                        const pct = Math.round((eventData.idx / eventData.total) * 100);
                        if (progressBar) progressBar.style.width = `${pct}%`;
                        if (percentEl) percentEl.textContent = `${pct}%`;
                        statusTextEl.textContent = `Procesando: ${eventData.nombre}`;
                        logEl.innerHTML += `[SYNC] (${eventData.idx}/${eventData.total}) Sincronizado: ${eventData.nombre} (${eventData.rut})<br>`;
                        logEl.scrollTop = logEl.scrollHeight;
                    } else if (eventType === 'done') {
                        finalStats = eventData;
                    } else if (eventType === 'error') {
                        throw new Error(eventData.message || 'Error en streaming de datos');
                    }
                    eventType = null;
                    eventData = null;
                }
            }
            // FIX: Si quedó un evento pendiente sin línea vacía final (último chunk),
            // despacharlo igualmente. Esto ocurre cuando el servidor cierra la conexión
            // justo después de emitir el último evento sin trailing newline.
            if (eventType && eventData !== null) {
                if (eventType === 'done') {
                    finalStats = eventData;
                } else if (eventType === 'error') {
                    throw new Error(eventData.message || 'Error en streaming de datos');
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

        // FIX: Procesar buffer residual después de que el stream se cierre.
        // El último evento puede quedar atrapado en el buffer si no termina en \n.
        if (buffer.trim()) {
            const remainingLines = buffer.split('\n');
            remainingLines.push(''); // Agregar línea vacía para forzar despacho del último evento
            _processSSELines(remainingLines);
        }

        if (!finalStats) {
            // FALLBACK: El stream se cerró sin enviar evento 'done'.
            // Esto puede pasar si Cloud Run cierra la conexión prematuramente,
            // o si hay buffering intermedio (proxies, CDN).
            // Los empleados YA se sincronizaron en el backend — solo se perdió la señal.
            console.warn('[Wizard] Stream cerrado sin evento done — activando fallback');
            logEl.innerHTML += `<span class="text-warning">[WARN] El servidor completó la sincronización pero la señal de finalización no llegó. Los datos están guardados.</span><br>`;
            logEl.scrollTop = logEl.scrollHeight;

            if (progressBar) {
                progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
                progressBar.style.width = '100%';
            }
            if (percentEl) percentEl.textContent = '100%';
            statusTextEl.textContent = 'Sincronización completada (señal parcial).';

            // Construir stats mínimos desde los empleados que vimos pasar por progress
            finalStats = {
                empleados_nuevos: (window._wizardState.synchronizedEmployees || []).filter(e => e.es_nuevo).length,
                empleados_actualizados: (window._wizardState.synchronizedEmployees || []).filter(e => !e.es_nuevo).length,
                empleados_sin_cambios: 0,
                nuevos_detalles: []
            };
        }

        if (finalStats) {
            logEl.innerHTML += `[OK] Sincronización completada con éxito.<br>`;
            logEl.innerHTML += `[STATS] Nuevos: ${finalStats.empleados_nuevos}, Actualizados: ${finalStats.empleados_actualizados}, Sin Cambios: ${finalStats.empleados_sin_cambios || 0}<br>`;
            logEl.scrollTop = logEl.scrollHeight;

            if (progressBar) {
                progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
                progressBar.style.width = '100%';
            }
            if (percentEl) percentEl.textContent = '100%';
            statusTextEl.textContent = 'Sincronización finalizada.';

            // FIX: Invalidar cachés de áreas para que TODOS los módulos
            // (Dashboard, Reportes, Marcaciones, Asignaciones) refresquen
            // sus dropdowns y detecten áreas nuevas como MANTENCION.
            window._cachedAreas = null;
            window._cachedMetadata = null;

            if (typeof window.loadEmpleados === 'function') await window.loadEmpleados();
            if (typeof window.loadStats === 'function') await window.loadStats();

            // Resolver todos los empleados sincronizados (tanto nuevos como existentes) para onboarding/turnos
            statusTextEl.textContent = 'Preparando fichas de empleados...';
            window._wizardState.onboardingCompletados = {};
            
            const token = localStorage.getItem('token');
            const syncList = window._wizardState.synchronizedEmployees || [];
            const resolvedEmployees = [];
            
            await Promise.all(syncList.map(async (item) => {
                try {
                    const resp = await fetch(`/api/empleados/rut/${item.rut}/`, {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    if (resp.ok) {
                        const emp = await resp.json();
                        resolvedEmployees.push({
                            id: emp.id,
                            nombre: emp.nombre_completo || `${emp.nombre} ${emp.apellido_paterno}`,
                            rut: emp.rut,
                            es_nuevo: item.es_nuevo,
                            area: emp.area,
                            activo: emp.activo,
                            bioalba_data: {
                                rut: emp.rut,
                                nombre: emp.nombre,
                                apellido_paterno: emp.apellido_paterno,
                                apellido_materno: emp.apellido_materno,
                                cargo: emp.cargo,
                                area: emp.area,
                                compania: emp.compania,
                                email: emp.email,
                                telefono: emp.telefono,
                                genero: emp.genero,
                                fecha_ingreso: emp.fecha_ingreso
                            }
                        });
                        
                        // Para existentes, marcar onboarding completado por defecto (pueden revisarse o avanzar a turnos)
                        if (!item.es_nuevo) {
                            window._wizardState.onboardingCompletados[emp.id] = true;
                        }
                    }
                } catch (e) {
                    console.error('Error al resolver empleado:', e);
                }
            }));

            window._wizardState.newEmployeesDetalles = resolvedEmployees;
            statusTextEl.textContent = 'Sincronización finalizada.';
            saveWizardStateToLocalStorage();

            if (btnCancel) btnCancel.disabled = false;
            if (btnCloseHeader) btnCloseHeader.disabled = false;

            if (window._wizardState.newEmployeesDetalles.length > 0) {
                logEl.innerHTML += `[INFO] Se sincronizaron ${window._wizardState.newEmployeesDetalles.length} empleado(s). Procediendo a completar fichas/turnos.<br>`;
                logEl.scrollTop = logEl.scrollHeight;
                if (btnNext) {
                    btnNext.disabled = false;
                    btnNext.classList.remove('d-none');
                }
            } else {
                logEl.innerHTML += `[INFO] No hay empleados sincronizados que procesar.<br>`;
                logEl.scrollTop = logEl.scrollHeight;
                const btnFinish = document.getElementById('btn-wizard-finish');
                if (btnFinish) {
                    btnFinish.textContent = 'Finalizar Asistente';
                    btnFinish.classList.remove('d-none');
                    btnFinish.onclick = window.closeSyncWizard;
                }
            }
        }
    } catch (err) {
        console.error('[Wizard Sync Error]:', err);
        if (progressBar) {
            progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
            progressBar.classList.add('bg-danger');
        }
        if (statusTextEl) statusTextEl.textContent = 'Error de Sincronización';
        if (logEl) logEl.innerHTML += `<span class="text-danger">[ERROR] ${err.message || err}</span><br>`;
        if (errorContainer) {
            errorContainer.classList.remove('d-none');
            const errTextEl = document.getElementById('wizard-sync-error-text');
            if (errTextEl) errTextEl.textContent = err.message || 'Error al conectar con BioAlba.';
        }
        if (btnCancel) btnCancel.disabled = false;
        if (btnCloseHeader) btnCloseHeader.disabled = false;
    }
};

window.wizardRetrySync = function() {
    if (window._wizardState.syncPayload) {
        window.startWizardSSESync(window._wizardState.syncPayload);
    } else {
        Swal.fire('Error', 'No hay datos de payload para reintentar.', 'error');
    }
};

window.renderWizardStep8Completed = function() {
    const logEl = document.getElementById('wizard-sync-log');
    const progressBar = document.getElementById('wizard-sync-progress-bar');
    const percentEl = document.getElementById('wizard-sync-percent');
    const statusTextEl = document.getElementById('wizard-sync-status-text');
    const btnNext = document.getElementById('btn-wizard-next');

    if (logEl) {
        logEl.innerHTML = `[INFO] Estado de sincronización restaurado de la sesión anterior.<br>`;
        logEl.innerHTML += `[OK] Sincronización completada.<br>`;
    }
    if (progressBar) {
        progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
        progressBar.style.width = '100%';
    }
    if (percentEl) percentEl.textContent = '100%';
    if (statusTextEl) statusTextEl.textContent = 'Sincronización finalizada (Cargada desde caché)';

    if (window._wizardState.newEmployeesDetalles && window._wizardState.newEmployeesDetalles.length > 0) {
        if (btnNext) {
            btnNext.disabled = false;
            btnNext.classList.remove('d-none');
        }
    } else {
        const btnFinish = document.getElementById('btn-wizard-finish');
        if (btnFinish) {
            btnFinish.textContent = 'Finalizar Asistente';
            btnFinish.classList.remove('d-none');
            btnFinish.onclick = window.closeSyncWizard;
        }
    }
};

window.renderWizardStep9 = function() {
    const listEl = document.getElementById('wizard-onboarding-emp-list');
    const formPlaceholder = document.getElementById('wizard-onboarding-form-placeholder');
    const formEl = document.getElementById('form-wizard-empleado');
    const btnNext = document.getElementById('btn-wizard-next');
    const btnPrev = document.getElementById('btn-wizard-prev');

    if (btnPrev) btnPrev.disabled = true; 
    if (btnNext) {
        btnNext.classList.remove('d-none');
        btnNext.disabled = true; 
    }

    if (!listEl) return;
    listEl.innerHTML = '';

    const employees = window._wizardState.newEmployeesDetalles || [];
    if (employees.length === 0) {
        listEl.innerHTML = '<div class="text-muted p-3">Ningún empleado pendiente.</div>';
        return;
    }

    let allCompleted = true;

    employees.forEach(emp => {
        const isCompleted = !!window._wizardState.onboardingCompletados[emp.id];
        if (!isCompleted) allCompleted = false;

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `list-group-item list-group-item-action d-flex justify-content-between align-items-center ${window._wizardState.selectedOnboardingEmpId === emp.id ? 'active' : ''}`;
        
        let statusBadge = `<span class="badge bg-danger rounded-pill">Falta Ficha</span>`;
        if (isCompleted) {
            statusBadge = `<span class="badge bg-success rounded-pill"><i class="bi bi-check-lg"></i> Listo</span>`;
        }

        btn.innerHTML = `
            <div>
                <div class="fw-bold">${emp.nombre}</div>
                <div class="small ${window._wizardState.selectedOnboardingEmpId === emp.id ? 'text-white-50' : 'text-muted'}">${emp.rut}</div>
            </div>
            ${statusBadge}
        `;
        
        btn.onclick = () => {
            window.selectOnboardingEmployee(emp.id);
        };
        listEl.appendChild(btn);
    });

    if (allCompleted) {
        btnNext.disabled = false;
    } else {
        btnNext.disabled = true;
    }

    if (window._wizardState.selectedOnboardingEmpId) {
        formPlaceholder.classList.add('d-none');
        formEl.classList.remove('d-none');
        loadOnboardingEmployeeForm(window._wizardState.selectedOnboardingEmpId);
    } else {
        formPlaceholder.classList.remove('d-none');
        formEl.classList.add('d-none');
    }
};

window.selectOnboardingEmployee = function(empId) {
    window._wizardState.selectedOnboardingEmpId = empId;
    saveWizardStateToLocalStorage();
    renderWizardStep9();
};

async function loadOnboardingEmployeeForm(empId) {
    const formEl = document.getElementById('form-wizard-empleado');
    if (!formEl) return;

    formEl.style.opacity = '0.5';

    try {
        const token = localStorage.getItem('token');
        const resp = await fetch(`/api/empleados/${empId}/`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const empleado = await resp.json();

        const inputId = document.getElementById('input-wizard-id');
        if (inputId) inputId.value = empleado.id;

        // Recuperar y mostrar Datos de Origen BioAlba
        const empDetails = window._wizardState.newEmployeesDetalles ? window._wizardState.newEmployeesDetalles.find(e => e.id === parseInt(empId)) : null;
        const bio = empDetails ? empDetails.bioalba_data : null;

        const rutBio = document.getElementById('text-wizard-rut-bioalba');
        const nombreBio = document.getElementById('text-wizard-nombre-bioalba');
        const areaBio = document.getElementById('text-wizard-area-bioalba');
        const cargoBio = document.getElementById('text-wizard-cargo-bioalba');
        const companiaBio = document.getElementById('text-wizard-compania-bioalba');
        const emailBio = document.getElementById('text-wizard-email-bioalba');
        const telefonoBio = document.getElementById('text-wizard-telefono-bioalba');
        const generoBio = document.getElementById('text-wizard-genero-bioalba');
        const fechaIngresoBio = document.getElementById('text-wizard-fecha-ingreso-bioalba');

        if (bio) {
            const formatName = `${bio.apellido_paterno || ''} ${bio.apellido_materno || ''} ${bio.nombre || ''}`.trim().replace(/\s+/g, ' ');
            if (rutBio) rutBio.textContent = bio.rut || '-';
            if (nombreBio) nombreBio.textContent = formatName || '-';
            if (areaBio) areaBio.textContent = bio.area || 'Sin Asignar';
            if (cargoBio) cargoBio.textContent = bio.cargo || '-';
            if (companiaBio) companiaBio.textContent = bio.compania || '-';
            if (emailBio) emailBio.textContent = bio.email || '-';
            if (telefonoBio) telefonoBio.textContent = bio.telefono || '-';
            if (generoBio) generoBio.textContent = bio.genero || 'No Especificado';
            if (fechaIngresoBio) fechaIngresoBio.textContent = bio.fecha_ingreso || '-';
        } else {
            // Fallback usando el registro local si no está en la cola actual
            if (rutBio) rutBio.textContent = empleado.rut_formateado || empleado.rut || '-';
            if (nombreBio) nombreBio.textContent = empleado.nombre_completo || '-';
            if (areaBio) areaBio.textContent = empleado.area || 'Sin Asignar';
            if (cargoBio) cargoBio.textContent = empleado.cargo || '-';
            if (companiaBio) companiaBio.textContent = empleado.compania || '-';
            if (emailBio) emailBio.textContent = empleado.email || '-';
            if (telefonoBio) telefonoBio.textContent = empleado.telefono || '-';
            if (generoBio) generoBio.textContent = empleado.genero || 'No Especificado';
            if (fechaIngresoBio) fechaIngresoBio.textContent = empleado.fecha_ingreso || '-';
        }

        // Configurar Género Local (Si viene vacío de BioAlba, es editable; si no, queda fijo)
        const wrapperGenero = document.getElementById('wrapper-wizard-genero');
        if (wrapperGenero) {
            const rawGen = empleado.genero || '';
            const normalizedGen = rawGen.trim();
            const hasValidGenero = normalizedGen && normalizedGen !== 'No Especificado' && normalizedGen !== 'Sin Especificar' && normalizedGen !== '-';

            if (hasValidGenero) {
                wrapperGenero.innerHTML = `
                    <label for="input-wizard-genero" class="form-label small mb-1">Género *</label>
                    <input type="text" id="input-wizard-genero" value="${normalizedGen}" readonly class="form-control form-control-sm bg-white" style="cursor: not-allowed;">
                `;
            } else {
                wrapperGenero.innerHTML = `
                    <label for="input-wizard-genero" class="form-label small mb-1">Género *</label>
                    <select id="input-wizard-genero" class="form-select form-select-sm">
                        <option value="">-- Seleccionar --</option>
                        <option value="Masculino">Masculino</option>
                        <option value="Femenino">Femenino</option>
                        <option value="Otro">Otro</option>
                    </select>
                `;
            }
        }

        // Rellenar Inputs Editables locales con sus valores vigentes
        const nombreEl = document.getElementById('input-wizard-nombre');
        if (nombreEl) nombreEl.value = empleado.nombre || '';

        const apePatEl = document.getElementById('input-wizard-apellido-paterno');
        if (apePatEl) apePatEl.value = empleado.apellido_paterno || '';

        const apeMatEl = document.getElementById('input-wizard-apellido-materno');
        if (apeMatEl) apeMatEl.value = empleado.apellido_materno || '';

        const activoEl = document.getElementById('input-wizard-activo');
        if (activoEl) activoEl.value = empleado.activo !== undefined ? empleado.activo.toString() : 'true';

        const cargoEl = document.getElementById('input-wizard-cargo');
        if (cargoEl) cargoEl.value = empleado.cargo || '';

        const companiaEl = document.getElementById('input-wizard-compania');
        if (companiaEl) companiaEl.value = empleado.compania || '';
        
        const inputTipoContrato = document.getElementById('input-wizard-tipo-contrato');
        if (inputTipoContrato) inputTipoContrato.value = empleado.tipo_contrato || 'Temporal';
        
        const cantContratosEl = document.getElementById('input-wizard-cant-contratos');
        if (cantContratosEl) cantContratosEl.value = empleado.cant_contratos || 1;

        const fechaIngresoEl = document.getElementById('input-wizard-fecha-ingreso');
        if (fechaIngresoEl) fechaIngresoEl.value = empleado.fecha_ingreso || '';

        const fechaNacimientoEl = document.getElementById('input-wizard-fecha-nacimiento');
        if (fechaNacimientoEl) fechaNacimientoEl.value = empleado.fecha_nacimiento || '';

        const fechaSalidaEl = document.getElementById('input-wizard-fecha-salida');
        if (fechaSalidaEl) fechaSalidaEl.value = empleado.fecha_salida || '';

        const emailEl = document.getElementById('input-wizard-email');
        if (emailEl) emailEl.value = empleado.email || '';

        const telefonoEl = document.getElementById('input-wizard-telefono');
        if (telefonoEl) telefonoEl.value = empleado.telefono || '';

        window.handleWizardTipoContratoChange();
    } catch (e) {
        console.error('[Wizard Onboarding] Error cargando empleado:', e);
        Swal.fire('Error', 'No se pudo obtener la información del empleado: ' + e.message, 'error');
    } finally {
        formEl.style.opacity = '1';
    }
}

window.handleWizardTipoContratoChange = function() {
    const selectTipo = document.getElementById('input-wizard-tipo-contrato');
    const inputSalida = document.getElementById('input-wizard-fecha-salida');
    if (!selectTipo || !inputSalida) return;

    if (selectTipo.value === 'Indefinido') {
        inputSalida.disabled = true;
        inputSalida.value = '';
        inputSalida.removeAttribute('required');
    } else {
        inputSalida.disabled = false;
        inputSalida.setAttribute('required', 'required');
    }
};

window.saveWizardEmpleadoFicha = async function() {
    const inputId = document.getElementById('input-wizard-id');
    if (!inputId) return;
    const id = inputId.value;
    if (!id) return;

    const nombreEl = document.getElementById('input-wizard-nombre');
    const nombre = nombreEl ? nombreEl.value.trim() : '';

    const apellidoPaternoEl = document.getElementById('input-wizard-apellido-paterno');
    const apellidoPaterno = apellidoPaternoEl ? apellidoPaternoEl.value.trim() : '';

    const apellidoMaternoEl = document.getElementById('input-wizard-apellido-materno');
    const apellidoMaterno = apellidoMaternoEl ? apellidoMaternoEl.value.trim() : '';

    const cargoEl = document.getElementById('input-wizard-cargo');
    const cargo = cargoEl ? cargoEl.value.trim() : '';

    const companiaEl = document.getElementById('input-wizard-compania');
    const compania = companiaEl ? companiaEl.value.trim() : '';

    const generoEl = document.getElementById('input-wizard-genero');
    const genero = generoEl ? (generoEl.value || null) : null;

    const tipoContratoEl = document.getElementById('input-wizard-tipo-contrato');
    const tipoContrato = tipoContratoEl ? tipoContratoEl.value : 'Temporal';

    const fechaSalidaEl = document.getElementById('input-wizard-fecha-salida');
    const fechaSalida = fechaSalidaEl ? (fechaSalidaEl.value || null) : null;

    const fechaIngresoEl = document.getElementById('input-wizard-fecha-ingreso');
    const fechaIngreso = fechaIngresoEl ? (fechaIngresoEl.value || null) : null;

    const fechaNacimientoEl = document.getElementById('input-wizard-fecha-nacimiento');
    const fechaNacimiento = fechaNacimientoEl ? (fechaNacimientoEl.value || null) : null;

    const activoEl = document.getElementById('input-wizard-activo');
    const activo = activoEl ? (activoEl.value === 'true') : true;

    if (!nombre || !apellidoPaterno || !apellidoMaterno) {
        Swal.fire('Atención', 'Nombre, Apellido Paterno y Apellido Materno son obligatorios.', 'warning');
        return;
    }

    if (!cargo) {
        Swal.fire('Atención', 'El Cargo es obligatorio.', 'warning');
        return;
    }

    if (!compania) {
        Swal.fire('Atención', 'La Compañía es obligatoria.', 'warning');
        return;
    }

    if (activo) {
        if (!fechaIngreso) {
            Swal.fire('Atención', 'La Fecha de Ingreso es obligatoria para empleados activos.', 'warning');
            return;
        }
        if (!fechaNacimiento) {
            Swal.fire('Atención', 'La Fecha de Nacimiento es obligatoria para empleados activos.', 'warning');
            return;
        }
        if (!genero || genero === 'No Especificado' || genero === 'Sin Especificar') {
            Swal.fire('Atención', 'El GÉNERO es obligatorio para empleados activos.', 'warning');
            return;
        }
        if (tipoContrato === 'Temporal' && !fechaSalida) {
            Swal.fire('Atención', 'La FECHA DE TÉRMINO es obligatoria para contratos Temporales.', 'warning');
            return;
        }
    }

    if (fechaIngreso && fechaSalida && new Date(fechaSalida) < new Date(fechaIngreso)) {
        Swal.fire('Atención', 'La fecha de término no puede ser anterior a la de ingreso.', 'warning');
        return;
    }
    if (fechaNacimiento && fechaIngreso && new Date(fechaIngreso) < new Date(fechaNacimiento)) {
        Swal.fire('Atención', 'La fecha de ingreso no puede ser anterior a la de nacimiento.', 'warning');
        return;
    }

    const payload = {
        nombre: nombre,
        apellido_paterno: apellidoPaterno,
        apellido_materno: apellidoMaterno,
        genero: genero,
        cargo: document.getElementById('input-wizard-cargo').value.trim() || null,
        compania: document.getElementById('input-wizard-compania').value.trim() || null,
        tipo_contrato: tipoContrato,
        cant_contratos: parseInt(document.getElementById('input-wizard-cant-contratos').value) || 1,
        fecha_ingreso: fechaIngreso,
        fecha_nacimiento: fechaNacimiento,
        fecha_salida: fechaSalida,
        email: document.getElementById('input-wizard-email').value.trim() || null,
        telefono: document.getElementById('input-wizard-telefono').value.trim() || null,
        activo: activo
    };

    Swal.fire({
        title: 'Guardando ficha...',
        allowOutsideClick: false,
        didOpen: () => { Swal.showLoading(); }
    });

    try {
        const token = localStorage.getItem('token');
        const resp = await fetch(`/api/empleados/${id}/`, {
            method: 'PUT',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });

        if (!resp.ok) {
            const errText = await resp.text();
            throw new Error(errText);
        }

        Swal.close();
        
        window._wizardState.onboardingCompletados[id] = true;
        
        if (window._wizardState.employeesFullData) {
            window._wizardState.employeesFullData = window._wizardState.employeesFullData.filter(e => e.id !== parseInt(id));
        }
        
        saveWizardStateToLocalStorage();
        renderWizardStep9();
        showToast('Ficha guardada con éxito', 'success');
    } catch (e) {
        console.error('[Wizard Onboarding] Error guardando empleado:', e);
        Swal.fire('Error', 'No se pudo guardar la ficha: ' + e.message, 'error');
    }
};

async function loadStep10EmployeesData() {
    const employees = window._wizardState.newEmployeesDetalles || [];
    const token = localStorage.getItem('token');
    
    window._wizardState.employeesFullData = [];
    
    await Promise.all(employees.map(async (emp) => {
        try {
            const resp = await fetch(`/api/empleados/${emp.id}/`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (resp.ok) {
                const fullEmp = await resp.json();
                window._wizardState.employeesFullData.push(fullEmp);
            }
        } catch (e) {
            console.error('Error fetching employee details for step 10:', e);
        }
    }));
}

window.renderWizardStep10 = async function() {
    const tbody = document.getElementById('tbody-wizard-turnos-individuales');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4"><span class="spinner-border spinner-border-sm me-2"></span>Cargando datos de asignación...</td></tr>';

    const btnPrev = document.getElementById('btn-wizard-prev');
    const btnNext = document.getElementById('btn-wizard-next');
    const btnFinish = document.getElementById('btn-wizard-finish');

    if (btnPrev) btnPrev.disabled = false; 
    if (btnNext) btnNext.classList.add('d-none');
    if (btnFinish) {
        btnFinish.textContent = 'Finalizar y Recalcular';
        btnFinish.classList.remove('d-none');
        btnFinish.onclick = window.finishWizardOnboarding;
    }

    if (!window._wizardState.employeesFullData || window._wizardState.employeesFullData.length === 0) {
        await loadStep10EmployeesData();
    }

    const employees = window._wizardState.employeesFullData || [];
    const activeEmployees = employees.filter(e => e.activo);

    if (activeEmployees.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Ninguno de los nuevos empleados está activo. No se requieren asignaciones de turno.</td></tr>`;
        return;
    }

    tbody.innerHTML = '';
    
    if (!window._wizardState.turnosDisponibles || window._wizardState.turnosDisponibles.length === 0) {
        try {
            const token = localStorage.getItem('token');
            const response = await fetch('/api/turnos/?activo=true', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (response.ok) {
                const res = await response.json();
                window._wizardState.turnosDisponibles = res.turnos || [];
            }
        } catch (e) {
            console.error('Error fetching turnos:', e);
        }
    }

    activeEmployees.forEach(emp => {
        const tr = document.createElement('tr');
        
        const areaName = emp.area || '';
        const turnosFiltrados = window._wizardState.turnosDisponibles.filter(t => {
            return t.areas && t.areas.some(a => a.toUpperCase() === areaName.toUpperCase());
        });

        const turnosList = turnosFiltrados.length > 0 ? turnosFiltrados : window._wizardState.turnosDisponibles;

        const defaultTurnoId = window._wizardState.turnosIndividualesAsignados?.[emp.id] || 
                               window._wizardState.resoluciones.turnos[areaName] ||
                               (turnosList.find(t => t.es_default)?.id) ||
                               (turnosList[0]?.id) || '';

        const defaultFecha = window._wizardState.fechasIndividualesAsignadas?.[emp.id] || 
                             emp.fecha_ingreso || 
                             new Date().toISOString().split('T')[0];

        const defaultSync = window._wizardState.syncBioalbaIndividuales?.[emp.id] !== false;

        let selectOptions = `<option value="">-- Seleccionar Turno --</option>`;
        turnosList.forEach(t => {
            selectOptions += `<option value="${t.id}" ${String(t.id) === String(defaultTurnoId) ? 'selected' : ''}>${t.nombre}</option>`;
        });

        // Asegurar que las variables queden inicializadas en el estado
        if (!window._wizardState.turnosIndividualesAsignados) window._wizardState.turnosIndividualesAsignados = {};
        window._wizardState.turnosIndividualesAsignados[emp.id] = defaultTurnoId;

        if (!window._wizardState.fechasIndividualesAsignadas) window._wizardState.fechasIndividualesAsignadas = {};
        window._wizardState.fechasIndividualesAsignadas[emp.id] = defaultFecha;

        if (!window._wizardState.syncBioalbaIndividuales) window._wizardState.syncBioalbaIndividuales = {};
        window._wizardState.syncBioalbaIndividuales[emp.id] = defaultSync;

        tr.innerHTML = `
            <td class="fw-bold align-middle">${emp.nombre_completo}</td>
            <td class="align-middle"><span class="badge bg-secondary">${areaName || 'Sin Área'}</span></td>
            <td class="align-middle text-nowrap">
                <div class="d-flex align-items-center gap-1 mb-1">
                    <input type="date" class="form-control form-control-sm input-emp-fecha-asig" 
                           id="input-fecha-emp-${emp.id}" 
                           value="${defaultFecha}" 
                           style="width: 120px;"
                           onchange="window.saveTempIndividualFecha(${emp.id}, this.value)">
                    <button type="button" class="btn btn-outline-secondary btn-sm" 
                            onclick="window.setFechaAsigHoy(${emp.id})" style="padding: 0.15rem 0.35rem; font-size: 0.7rem;">
                        Hoy
                    </button>
                </div>
                <div class="d-flex flex-column gap-1">
                    <a href="javascript:void(0)" class="small text-info text-decoration-none" 
                       id="link-primera-marca-${emp.id}"
                       onclick="window.wizardBuscarPrimeraMarca(${emp.id})">
                        <i class="bi bi-search me-1"></i>Buscar 1ª marca
                    </a>
                    <span class="x-small text-muted d-none" id="txt-primera-marca-${emp.id}"></span>
                </div>
            </td>
            <td class="align-middle">
                <select class="form-select form-select-sm select-emp-turno" id="select-turno-emp-${emp.id}" data-empid="${emp.id}" onchange="window.saveTempIndividualTurno(${emp.id}, this.value)">
                    ${selectOptions}
                </select>
            </td>
            <td class="align-middle text-center">
                <div class="form-check form-switch d-inline-block">
                    <input class="form-check-input chk-emp-sync-bioalba" type="checkbox" role="switch" 
                           id="chk-sync-emp-${emp.id}" ${defaultSync ? 'checked' : ''}
                           onchange="window.saveTempIndividualSyncBioalba(${emp.id}, this.checked)">
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });

    saveWizardStateToLocalStorage();
};

window.saveTempIndividualTurno = function(empId, turnoId) {
    if (!window._wizardState.turnosIndividualesAsignados) {
        window._wizardState.turnosIndividualesAsignados = {};
    }
    window._wizardState.turnosIndividualesAsignados[empId] = turnoId;
    saveWizardStateToLocalStorage();
};

window.saveTempIndividualFecha = function(empId, fecha) {
    if (!window._wizardState.fechasIndividualesAsignadas) {
        window._wizardState.fechasIndividualesAsignadas = {};
    }
    window._wizardState.fechasIndividualesAsignadas[empId] = fecha;
    saveWizardStateToLocalStorage();
};

window.saveTempIndividualSyncBioalba = function(empId, sync) {
    if (!window._wizardState.syncBioalbaIndividuales) {
        window._wizardState.syncBioalbaIndividuales = {};
    }
    window._wizardState.syncBioalbaIndividuales[empId] = sync;
    saveWizardStateToLocalStorage();
};

window.setFechaAsigHoy = function(empId) {
    const todayStr = new Date().toISOString().split('T')[0];
    const input = document.getElementById(`input-fecha-emp-${empId}`);
    if (input) {
        input.value = todayStr;
        window.saveTempIndividualFecha(empId, todayStr);
    }
};

window.wizardBuscarPrimeraMarca = async function(empId) {
    const link = document.getElementById(`link-primera-marca-${empId}`);
    const txt = document.getElementById(`txt-primera-marca-${empId}`);
    const input = document.getElementById(`input-fecha-emp-${empId}`);

    if (link) {
        link.classList.add('pe-none', 'text-muted');
        link.innerHTML = '<span class="spinner-border spinner-border-sm me-1" style="width:10px;height:10px;"></span>Buscando...';
    }
    if (txt) {
        txt.classList.remove('d-none');
        txt.textContent = 'Consultando BioAlba (desde ene 2026)...';
    }

    try {
        const resp = await fetch(`/api/asistencia/empleados/${empId}/primera-marcacion/`);
        const data = resp.ok ? await resp.json() : null;
        const primeraMarca = data?.primera_marcacion || null;

        if (primeraMarca) {
            if (input) {
                input.value = primeraMarca;
                window.saveTempIndividualFecha(empId, primeraMarca);
            }
            if (txt) {
                txt.textContent = `1ª Marca: ${primeraMarca}`;
                txt.className = 'x-small text-success fw-bold';
            }
            if (link) link.classList.add('d-none');
        } else {
            if (txt) {
                txt.textContent = data?.motivo || 'Sin marcas desde ene 2026';
                txt.className = 'x-small text-warning';
            }
            if (link) {
                link.classList.remove('pe-none', 'text-muted');
                link.innerHTML = '<i class="bi bi-search me-1"></i>Buscar 1ª marca';
            }
        }
    } catch (e) {
        if (txt) {
            txt.textContent = 'Error consultando BioAlba';
            txt.className = 'x-small text-danger';
        }
        if (link) {
            link.classList.remove('pe-none', 'text-muted');
            link.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i>Reintentar';
        }
    }
};

window.finishWizardOnboarding = async function() {
    const employees = window._wizardState.employeesFullData || [];
    const activeEmployees = employees.filter(e => e.activo);
    
    for (const emp of activeEmployees) {
        const turnoId = window._wizardState.turnosIndividualesAsignados?.[emp.id];
        if (!turnoId) {
            Swal.fire('Atención', `Debes asignar un turno para el empleado activo: ${emp.nombre_completo}`, 'warning');
            return;
        }
        const fechaAsig = window._wizardState.fechasIndividualesAsignadas?.[emp.id];
        if (!fechaAsig) {
            Swal.fire('Atención', `Debes seleccionar una fecha de inicio de asignación para: ${emp.nombre_completo}`, 'warning');
            return;
        }
    }

    Swal.fire({
        title: 'Aplicando asignaciones...',
        html: 'Por favor espere mientras se configuran los turnos individuales.',
        allowOutsideClick: false,
        didOpen: () => { Swal.showLoading(); }
    });

    try {
        const token = localStorage.getItem('token');
        
        await Promise.all(activeEmployees.map(async (emp) => {
            const turnoId = window._wizardState.turnosIndividualesAsignados[emp.id];
            const fechaAsig = window._wizardState.fechasIndividualesAsignadas[emp.id] || emp.fecha_ingreso || new Date().toISOString().split('T')[0];
            const resp = await fetch('/api/asistencia/asignaciones/individual/', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    empleado_id: emp.id,
                    fecha: fechaAsig,
                    turno_id: parseInt(turnoId),
                    sync_bioalba: false,
                    skip_reproceso: true
                })
            });
            if (!resp.ok) {
                throw new Error(`No se pudo asignar turno a ${emp.nombre_completo}: ${await resp.text()}`);
            }
        }));

        Swal.close();

        if (activeEmployees.length > 0) {
            const batchItems = activeEmployees.map(emp => ({
                empleado_id: emp.id,
                fecha_inicio: window._wizardState.fechasIndividualesAsignadas[emp.id] || emp.fecha_ingreso || new Date().toISOString().split('T')[0],
                sync_bioalba: window._wizardState.syncBioalbaIndividuales?.[emp.id] !== false
            }));

            Swal.fire({
                title: 'Iniciando recálculo...',
                html: 'Preparando recalibración de asistencia histórica.',
                allowOutsideClick: false,
                didOpen: () => { Swal.showLoading(); }
            });

            const resp = await fetch('/api/asistencia/asignaciones/batch-sync/', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ items: batchItems })
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Error en batch-sync');
            }

            const batchData = await resp.json();
            const jobIds = batchData.job_ids || {};
            const total = batchData.empleados || 0;

            Swal.close();

            window.closeSyncWizard(true);
            window.clearWizardStateFromLocalStorage();

            const primerEmpId = Object.keys(jobIds)[0];
            const primerJobId = primerEmpId ? jobIds[primerEmpId] : null;
            const primerFecha = batchItems[0]?.fecha_inicio || new Date().toISOString().split('T')[0];

            if (primerJobId && typeof window.abrirModalProgresoJob === 'function') {
                setTimeout(() => {
                    window.abrirModalProgresoJob(primerJobId, `Batch (${total} emp.)`, primerFecha, {
                        syncBioAlba: batchItems.some(i => i.sync_bioalba),
                        allJobIds: Object.values(jobIds),
                        onComplete: () => {
                            if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
                            if (typeof window.loadMarcacionesFilters === 'function') window.loadMarcacionesFilters();
                        }
                    });
                }, 400);
            }
        } else {
            window.closeSyncWizard(true);
            window.clearWizardStateFromLocalStorage();
            Swal.fire('Onboarding Completado', 'Fichas y turnos asignados correctamente.', 'success');
            if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
            if (typeof window.loadMarcacionesFilters === 'function') window.loadMarcacionesFilters();
        }

    } catch (e) {
        console.error('[Wizard Onboarding Finish Error]:', e);
        Swal.fire('Error', 'Error al finalizar onboarding: ' + e.message, 'error');
    }
};

// =============================================================================
// INICIALIZACIÓN AUTOMÁTICA Y RESTAURACIÓN (F5 RESILIENCE)
// =============================================================================
(function _installWizardF5Restore() {
    const restore = () => {
        const savedState = window.loadWizardStateFromLocalStorage();
        if (savedState && savedState.currentStep >= 8) {
            window._wizardState = savedState;
            console.log('🔄 [Wizard F5 Restore] Restaurando asistente en Paso', savedState.currentStep);
            
            setTimeout(() => {
                const modalEl = document.getElementById('modal-sync-wizard');
                if (modalEl) {
                    updateWizardUI();
                    const wizardModal = new bootstrap.Modal(modalEl);
                    wizardModal.show();
                }
            }, 1000); 
        }
    };
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', restore);
    } else {
        setTimeout(restore, 100);
    }
})();

