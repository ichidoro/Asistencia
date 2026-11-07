// horarios.js - Gestión de Horarios y Turnos

const API_TURNOS = '/api/turnos/'; // Relativo

// Estado local
let turnosList = [];
let currentTurnoId = null; // Para edición

// ==========================================
// INICIALIZACIÓN
// ==========================================
function initHorarios() {
    // [FIX] Si el contenedor ya existe, no reinicializar todo para evitar parpadeo
    if (document.getElementById('horarios-view')) {
        console.log("📅 Módulo Horarios ya está cargado. Omitiendo renderizado completo.");
        
        // Solo recargar la tabla de turnos si NO hay un modal abierto (para no interrumpir edición)
        const modalEl = document.getElementById('modalTurno');
        const isModalOpen = modalEl && (modalEl.classList.contains('show') || modalEl.style.display === 'block');
        
        if (!isModalOpen) {
            loadTurnos();
        }
        return;
    }

    console.log("Inicializando módulo Horarios...");
    renderHorariosUI();
    loadTurnos();
}

// ==========================================
// API CALLS
// ==========================================
async function loadTurnos() {
    try {
        const response = await fetch(API_TURNOS);
        if (!response.ok) throw new Error("Error cargando turnos");
        turnosList = await response.json();
        renderTurnosTable();
    } catch (error) {
        console.error(error);
        Avisos.error("No se pudo cargar la lista de turnos.");
    }
}

window.sortTurnos = function (key) {
    TableSorter.sort(turnosList, key, 'turnos');
    renderTurnosTable();
};

async function saveTurno() {
    const form = document.getElementById('formTurno');
    const formData = new FormData(form);

    // Si algo falta, se vuelve al paso donde se completa (asistente de 6 pasos)
    for (const n of [1, 2, 3, 5]) {
        if (!twValidar(n)) { twIr(n); return; }
    }
    // La colación del horario es obligatoria: el cálculo la descuenta y la usa para reconocer la pausa de colación.
    if (!document.getElementById('chkColacion').checked || !(parseInt(document.getElementById('numColacion').value, 10) > 0)) {
        Avisos.falta('Falta la colación. Marque «Descontar» y escriba los minutos de colación.');
        return;
    }

    if (formData.get('tipo_programacion') === 'BOLSA_FLEXIBLE' || formData.get('tipo_programacion') === 'FLEXIBLE_BOLSA') {
        const metaInputObj = document.getElementById('input-meta-bolsa');
        if (!metaInputObj || !metaInputObj.value) {
            Avisos.falta('Falta la meta del mes (horas totales) de la bolsa flexible.');
            return;
        }
        if (!formData.get('hora_limite_ficticia')) {
            Avisos.falta('Falta la hora límite de la bolsa flexible.');
            return;
        }
    } else {
        const metaInputObj = document.getElementById('input-meta-jornada');
        if (!metaInputObj || !metaInputObj.value) {
            Avisos.falta('Faltan las horas de la jornada semanal.');
            return;
        }
    }

    // Build object
    const turno = {
        nombre: formData.get('nombre'),
        tipo_programacion: formData.get('tipo_programacion'),
        tolerancia_retraso_alerta: parseInt(formData.get('tolerancia_retraso_alerta') || 0),
        tolerancia_retraso_descuento: parseInt(formData.get('tolerancia_retraso_descuento') || 0),
        tolerancia_salida_adelantada: Math.max(0, parseInt(formData.get('tolerancia_salida_adelantada') || 0, 10) || 0),
        meta_horas_semanales: 0, // Se actualizará abajo
        meta_horas_espera: parseFloat(document.getElementById('input-meta-espera')?.value || 88.0),
        // El selector vive en el bloque de Bolsa Flexible (oculto en los demás tipos, donde no se puede editar): fuera de Bolsa Flexible
        // siempre es reloj, aunque el turno viniera guardado con LIBRETA_180H (caso Tradicional Facturación 2, 2026-10-14).
        modalidad_control: ['BOLSA_FLEXIBLE', 'FLEXIBLE_BOLSA'].includes(formData.get('tipo_programacion'))
            ? (document.getElementById('select-modalidad-control')?.value || 'RELOJ')
            : 'RELOJ',
        libreta_desde: ['BOLSA_FLEXIBLE', 'FLEXIBLE_BOLSA'].includes(formData.get('tipo_programacion'))
            ? (document.getElementById('input-libreta-desde')?.value || null)
            : null,
        hora_limite_ficticia: formData.get('hora_limite_ficticia') || null,
        descuento_colacion_auto: !!document.getElementById('chkColacion').checked,
        minutos_colacion_auto: document.getElementById('chkColacion').checked ? parseInt(document.getElementById('numColacion').value) : 0,
        umbral_horas_colacion: document.getElementById('chkColacion').checked ? (parseFloat(document.getElementById('umbralColacion').value) || 0) : 0,
        tolerancia_exceso_colacion_minutos: Math.max(0, parseInt(document.getElementById('toleranciaExcesoColacion')?.value, 10) || 0),
        anclaje_entrada_minutos: parseInt(formData.get('anclaje_entrada_minutos') || 0),
        anclaje_salida_minutos: Math.max(0, parseInt(formData.get('anclaje_salida_minutos') || 0, 10) || 0),
        ventana_en_curso_minutos: Math.max(0, parseInt(formData.get('ventana_en_curso_minutos') || 0, 10) || 0),
        espera_inasistencia_minutos: Math.max(0, parseInt(formData.get('espera_inasistencia_minutos') || 0, 10) || 0),
        rotacion_dinamica_diaria: ((formData.get('tipo_programacion') === 'CICLO_INTELIGENTE') && ((document.getElementById('chkRotacionDinamicaDiaria')?.checked) || (document.getElementById('chk-rotacion-dinamica-diaria')?.checked))) ? 1 : 0,
        areas: Array.from(document.querySelectorAll('.chk-area-turno:checked')).map(cb => cb.value),
        activo: formData.get('activo') !== 'false',
        dias: []
    };

    if (turno.areas.length === 0) {
        Avisos.falta('Falta el área. Elija al menos una para el turno.');
        return;
    }

    // Collect weeks
    const weekContainers = document.querySelectorAll('.week-container');
    let totalHoras = 0;

    weekContainers.forEach((container, wIdx) => {
        const numSemana = wIdx + 1;
        const rows = container.querySelectorAll('.dias-input-body tr');
        const etiquetaInput = container.querySelector('.etiqueta-input');
        const etiquetaValor = etiquetaInput ? etiquetaInput.value : null;

        rows.forEach(row => {
            const chkLibre = row.querySelector('.chk-libre');
            const isLibre = chkLibre.checked;
            const horasVal = parseFloat(row.querySelector('.hours-calc').value) || 0;
            const horas = isLibre ? 0 : horasVal;
            if (numSemana === 1) totalHoras += horas; // Para meta_horas_semanales en Fijo

            turno.dias.push({
                num_semana: numSemana,
                dia_semana: parseInt(row.dataset.day),
                etiqueta_bloque: etiquetaValor,
                es_libre: isLibre,
                horas_teoricas: horas,
                hora_entrada: isLibre ? null : row.querySelector('.time-in').value,
                hora_salida: isLibre ? null : row.querySelector('.time-out').value,
                cruza_medianoche: row.querySelector('.chk-cruce').checked
            });
        });
    });

    if (turno.tipo_programacion === 'BOLSA_FLEXIBLE' || turno.tipo_programacion === 'FLEXIBLE_BOLSA') {
        const metaInputObj = document.getElementById('input-meta-bolsa');
        turno.meta_horas_semanales = parseFloat(metaInputObj.value);
    } else {
        const metaInputObj = document.getElementById('input-meta-jornada');
        turno.meta_horas_semanales = parseFloat(metaInputObj.value);
    }

    if (turno.tipo_programacion !== 'BOLSA_FLEXIBLE' && turno.tipo_programacion !== 'FLEXIBLE_BOLSA') {
        let hasMismatch = false;
        let mismatchDetails = [];
        
        weekContainers.forEach((container, wIdx) => {
            const numSemana = wIdx + 1;
            const totalSemana = Array.from(container.querySelectorAll('.hours-calc'))
                .reduce((acc, input) => acc + (parseFloat(input.value) || 0), 0);
            
            if (totalSemana !== turno.meta_horas_semanales && totalSemana > 0) {
                hasMismatch = true;
                mismatchDetails.push(`Semana ${numSemana}: <strong>${totalSemana.toFixed(1)} hrs</strong>`);
            }
        });

        if (hasMismatch) {
            const result = await Swal.fire({
                title: "Inconsistencia de Horas",
                html: `La jornada objetivo del turno es de <b>${turno.meta_horas_semanales} hrs</b>, pero la planificación suma diferente:<br><br>` + 
                      mismatchDetails.join('<br>') + 
                      `<br><br>¿Estás seguro de que deseas guardar este turno así?`,
                icon: "warning",
                showCancelButton: true,
                confirmButtonColor: "#f59e0b",
                confirmButtonText: "Sí, guardar igual",
                cancelButtonText: "No, corregir",
                reverseButtons: true
            });
            if (!result.isConfirmed) return;
        }
    }

    try {
        let url = API_TURNOS;
        let method = 'POST';

        if (currentTurnoId) {
            url += `${currentTurnoId}/`;
            method = 'PUT';
        }

        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(turno)
        });

        if (!response.ok) {
            let errMsg = "Error guardando turno";
            try {
                const errData = await response.json();
                errMsg = errData.detail || JSON.stringify(errData);
            } catch (_) {}
            throw new Error(errMsg);
        }
        let respuesta = {};
        try { respuesta = await response.json(); } catch (_) {}

        await loadTurnos();
        window._isSavingTurno = true;
        window._hasTurnos = true;
        closeModalHorario(true);
        const rec = respuesta && respuesta.recalculo;
        const avisoRecalculo = (rec && rec.personas > 0)
            ? ` Se está recalculando el tramo abierto de ${rec.personas} persona${rec.personas === 1 ? '' : 's'}; la grilla se actualiza en unos segundos.`
            : '';
        showNotification((currentTurnoId ? "Listo. Turno guardado." : "Listo. Turno creado.") + avisoRecalculo, "success");

        if (window.isWizardFlow && window.wizardCurrentStep === 'turnos') {
            Swal.fire({
                title: "Turno Guardado",
                text: "¿Desea crear otro turno o continuar al siguiente paso?",
                icon: "success",
                showCancelButton: true,
                confirmButtonText: "Crear otro turno",
                cancelButtonText: "Siguiente paso (Bonos)",
                reverseButtons: true
            }).then((result) => {
                if (result.isConfirmed) {
                    openModalHorario(); // Nuevo turno
                } else {
                    if (typeof window.abrirConfigBonoWizard === 'function') {
                        window.abrirConfigBonoWizard();
                    }
                }
            });
        }

    } catch (error) {
        console.error(error);
        Avisos.error("No se guardó el turno. " + error.message);
    }
}

async function deleteTurno(id) {
    if (!await uiConfirm('¿Eliminar este turno?', { items: ['Ya no se podrá asignar a nadie.', 'No se puede deshacer.'], confirmText: 'Eliminar turno', danger: true })) return;

    try {
        const response = await fetch(`${API_TURNOS}${id}/`, { method: 'DELETE' });
        if (!response.ok) throw new Error("Error al eliminar");

        await loadTurnos();
        showNotification("Listo. Turno eliminado.", "success");
    } catch (error) {
        console.error(error);
        Avisos.error("No se pudo eliminar el turno. " + error.message);
    }
}

// Descarga (solo lectura) todos los turnos de Ciclo Inteligente con sus opciones, los 7 días de cada una y todos sus parámetros,
// más cuántas personas tiene cada turno (sin nombres, RUT ni marcas). Sirve para simular fuera de línea cómo se comportaría el motor.
async function exportarTurnosJson(btn) {
    const textoOriginal = btn ? btn.innerHTML : '';
    const avisar = (msg, tipo) => (typeof window.showToast === 'function' ? window.showToast(msg, tipo) : alert(msg));
    try {
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Exportando...';
        }
        const res = await fetch('/api/turnos/export-ciclos/');
        if (!res.ok) {
            let msg = 'No se pudo exportar los turnos';
            try { msg = (await res.json()).detail || msg; } catch (_) { /* respuesta sin JSON */ }
            avisar(msg, 'warning');
            return;
        }
        const blob = await res.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `turnos_ciclo_${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
        avisar('Turnos exportados: revisa tus descargas', 'success');
    } catch (error) {
        console.error(error);
        avisar('Error al exportar los turnos', 'danger');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = textoOriginal;
        }
    }
}
window.exportarTurnosJson = exportarTurnosJson;

// ==========================================
// UI HELPERS
// ==========================================
async function openModalHorario(id = null) {
    currentTurnoId = id;
    const modalTitle = document.getElementById('modalTurnoLabel');
    const form = document.getElementById('formTurno');

    if (modalTitle) modalTitle.textContent = id ? "Editar turno" : "Nuevo turno";

    if (id) {
        // Cargar datos
        const turno = turnosList.find(t => t.id === id);
        if (turno) {
            // Llenar cabecera
            form.nombre.value = turno.nombre;
            form.tipo_programacion.value = turno.tipo_programacion;
            form.tolerancia_retraso_alerta.value = turno.tolerancia_retraso_alerta;
            form.tolerancia_retraso_descuento.value = turno.tolerancia_retraso_descuento;
            if (form.tolerancia_salida_adelantada) form.tolerancia_salida_adelantada.value = String(turno.tolerancia_salida_adelantada || 0);
            if (form.ventana_en_curso_minutos) form.ventana_en_curso_minutos.value = String(turno.ventana_en_curso_minutos || 0);
            if (form.espera_inasistencia_minutos) form.espera_inasistencia_minutos.value = String(turno.espera_inasistencia_minutos || 0);
            if (form.anclaje_entrada_minutos) form.anclaje_entrada_minutos.value = String(turno.anclaje_entrada_minutos || 0);
            if (form.anclaje_salida_minutos) form.anclaje_salida_minutos.value = String(turno.anclaje_salida_minutos || 0);
            if (form.hora_limite_ficticia) form.hora_limite_ficticia.value = turno.hora_limite_ficticia || "";
            if (form.meta_horas_semanales) form.meta_horas_semanales.value = turno.meta_horas_semanales || "";
            if (form.activo) form.activo.value = String(turno.activo !== false);
            
            // Cargar áreas (soporta nuevo modelo areas: List[str] o fallback antiguo area: str)
            let areasToSelect = turno.areas || [];
            if (turno.area && areasToSelect.length === 0) areasToSelect = [turno.area];
            await populateAreaSelect(areasToSelect);

            const inputMetaBol = document.getElementById('input-meta-bolsa');
            if (inputMetaBol) inputMetaBol.value = (turno.tipo_programacion === 'BOLSA_FLEXIBLE' || turno.tipo_programacion === 'FLEXIBLE_BOLSA') ? (turno.meta_horas_semanales || "") : "";

            const inputMetaEsp = document.getElementById('input-meta-espera');
            if (inputMetaEsp) inputMetaEsp.value = (turno.meta_horas_espera !== undefined && turno.meta_horas_espera !== null) ? turno.meta_horas_espera : 88.0;

            const selectModControl = document.getElementById('select-modalidad-control');
            if (selectModControl) selectModControl.value = turno.modalidad_control || 'RELOJ';

            const inputLibretaDesde = document.getElementById('input-libreta-desde');
            if (inputLibretaDesde) inputLibretaDesde.value = turno.libreta_desde || '';

            const chkRotDin = document.getElementById('chkRotacionDinamicaDiaria') || document.getElementById('chk-rotacion-dinamica-diaria');
            if (chkRotDin) chkRotDin.checked = Boolean(turno.rotacion_dinamica_diaria === 1 || turno.rotacion_dinamica_diaria === true);

            const chkColacion = document.getElementById('chkColacion');
            chkColacion.checked = turno.descuento_colacion_auto;
            document.getElementById('numColacion').value = turno.minutos_colacion_auto || "";
            const umbralInput = document.getElementById('umbralColacion');
            if (umbralInput) umbralInput.value = turno.umbral_horas_colacion !== undefined ? turno.umbral_horas_colacion : 0;
            const tolInput = document.getElementById('toleranciaExcesoColacion');
            if (tolInput) tolInput.value = turno.tolerancia_exceso_colacion_minutos !== undefined && turno.tolerancia_exceso_colacion_minutos !== null
                ? turno.tolerancia_exceso_colacion_minutos : 0;
            toggleColacionInput();

            // Llenar Semanas
            const dias_agrupados = {};
            turno.dias.forEach(d => {
                if (!dias_agrupados[d.num_semana]) dias_agrupados[d.num_semana] = [];
                dias_agrupados[d.num_semana].push(d);
            });

            const numSemanas = Object.keys(dias_agrupados).length || 1;
            // [FIX] setupModalListeners ahora NO llama handleTipoProgramacionChange internamente
            setupModalListeners(numSemanas);

            Object.entries(dias_agrupados).forEach(([sem, dias]) => {
                const container = document.getElementById(`week-container-${sem}`);
                if (!container) return;
                
                // Cargar etiqueta_bloque
                const etiquetaInput = container.querySelector('.etiqueta-input');
                if (etiquetaInput && dias.length > 0 && dias[0].etiqueta_bloque) {
                    etiquetaInput.value = dias[0].etiqueta_bloque;
                    document.getElementById(`pill-week-${sem}-tab`).innerText = dias[0].etiqueta_bloque;
                }

                const rows = container.querySelectorAll('.dias-input-body tr');

                dias.forEach(d => {
                    const row = rows[d.dia_semana];
                    if (row) {
                        const chkLibre = row.querySelector('.chk-libre');
                        chkLibre.checked = d.es_libre;
                        row.querySelector('.time-in').value = d.hora_entrada || "08:00";
                        row.querySelector('.time-out').value = d.hora_salida || "18:00";
                        row.querySelector('.chk-cruce').checked = d.cruza_medianoche;

                        row.querySelector('.hours-calc').value = d.horas_teoricas;
                        toggleDiaRow(chkLibre);
                    }
                });
            });


            // [FIX] UNA SOLA llamada al final para aplicar toda la visibilidad de tipo programación
            handleTipoProgramacionChange();
        }
    } else {
        form.reset();
        if (form.activo) form.activo.value = "true";
        if (form.meta_horas_semanales) form.meta_horas_semanales.value = "";
        if (form.tolerancia_retraso_alerta) form.tolerancia_retraso_alerta.value = 0;
        if (form.tolerancia_retraso_descuento) form.tolerancia_retraso_descuento.value = 0;
        if (form.tolerancia_salida_adelantada) form.tolerancia_salida_adelantada.value = 0;
        if (form.ventana_en_curso_minutos) form.ventana_en_curso_minutos.value = 0;
        if (form.espera_inasistencia_minutos) form.espera_inasistencia_minutos.value = 0;

        document.getElementById('chkColacion').checked = false;
        document.getElementById('numColacion').value = "";
        const umbralInput = document.getElementById('umbralColacion');
        if (umbralInput) umbralInput.value = "0";
        const tolInput = document.getElementById('toleranciaExcesoColacion');
        if (tolInput) tolInput.value = "0";
        toggleColacionInput();
        const inputMetaEsp = document.getElementById('input-meta-espera');
        if (inputMetaEsp) inputMetaEsp.value = "88.0";
        const selectModControl = document.getElementById('select-modalidad-control');
        if (selectModControl) selectModControl.value = 'RELOJ';
        const inputLibretaDesde = document.getElementById('input-libreta-desde');
        if (inputLibretaDesde) inputLibretaDesde.value = '';
        // [FIX] setupModalListeners NO llama handleTipoProgramacionChange - llamar aquí una sola vez
        setupModalListeners();
        handleTipoProgramacionChange();
        await populateAreaSelect([]);
    }

    // Limpiar instancia Bootstrap anterior antes de mostrar el modal.
    // getOrCreateInstance sobre un modal que ya tiene .show activo provoca
    // que la animación 'fade' se re-aplique, generando el CLS de 60+.
    const modalEl = document.getElementById('modalTurno');
    const existingInstance = bootstrap.Modal.getInstance(modalEl);
    if (existingInstance) {
        existingInstance.dispose();
    }
    twIr(1);
    const modalInstance = new bootstrap.Modal(modalEl, { backdrop: true, keyboard: true });
    modalInstance.show();
}


/**
 * Puebla el contenedor de áreas del turno con las áreas disponibles en el sistema.
 */
async function populateAreaSelect(selectedAreas = []) {
    const container = document.getElementById('container-areas-turno');
    if (!container) return;

    // Intentar obtener áreas de la API
    let areas = [];
    try {
        const resp = await fetch('/api/empleados/areas/');
        if (resp.ok) {
            areas = await resp.json();
        }
        
        // Si no hay áreas locales (e.g. primera instalación o DB limpia), hacer fallback a BioAlba
        if (!areas || areas.length === 0) {
            console.warn("No hay áreas locales, intentando cargar desde BioAlba...");
            const respBioAlba = await fetch('/api/sync/areas-preview/');
            if (respBioAlba.ok) {
                areas = await respBioAlba.json();
            }
        }
        
        areas.sort();
    } catch (e) { 
        console.error("Error cargando áreas para turno desde API, intentando fallback", e);
        if (window.allEmployeesBulk && window.allEmployeesBulk.length > 0) {
            areas = [...new Set(window.allEmployeesBulk.map(e => e.area).filter(a => a))].sort();
        } else {
            try {
                const resp = await fetch('/api/empleados/search/?limit=500&activo=true');
                const data = await resp.json();
                const emps = data.empleados || data.items || data;
                if (Array.isArray(emps)) {
                    areas = [...new Set(emps.map(e => e.area).filter(a => a))].sort();
                }
            } catch (e2) {
                console.error("Fallo definitivo al cargar áreas", e2);
            }
        }
    }

    // Inyección de salvaguarda para áreas que ya tenía asignadas pero no están en la lista actual
    selectedAreas.forEach(sa => {
        if (!areas.includes(sa)) {
            areas.push(sa);
        }
    });
    areas.sort();

    if (areas.length === 0) {
        container.innerHTML = '<div class="text-center text-muted small py-2">No hay áreas disponibles</div>';
        return;
    }

    const html = areas.map((a, i) => {
        const isChecked = selectedAreas.includes(a);
        return `
            <div class="form-check m-1">
                <input class="form-check-input chk-area-turno" type="checkbox" value="${a}" id="chk-area-turno-${i}" ${isChecked ? 'checked' : ''}>
                <label class="form-check-label small" for="chk-area-turno-${i}">${a}</label>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

// ==========================================
// RENDER UI
// ==========================================
function renderHorariosUI() {
    const container = document.getElementById('horarios-container') || document.getElementById('tab-horarios');
    if (!container) return;

    // Solo inyectar HTML si no existe la sección (evita destruir el modal abierto)
    if (!document.getElementById('horarios-view')) {
        const canEdit = typeof AuthService !== 'undefined' ? AuthService.hasPermission('configuracion.horarios') : true;
        // Diseño B (01-11-2026): lista de turnos y su ficha; el encabezado y las acciones los pone FichaCfg (renderTurnosTable).
        // «Asignación masiva» vive en Empleados: la ficha deja el enlace en la descripción.
        const html = '<div id="horarios-view" class="fade-in"><div id="turnos-fcb"></div></div>';
        container.innerHTML = html;

        // [FIX] Asegurar que el modal viva fuera de main-content para no ser destruido en re-renders
        // Si el modal ya fue inyectado previamente (fuera del main-content), lo reutilizamos
        const existingModal = document.getElementById('modalTurno');
        if (existingModal) {
            existingModal.remove();
        }
        // Crear el modal e insertarlo directamente en body (no en main-content)
        const modalWrapper = document.createElement('div');
        modalWrapper.innerHTML = renderModalHtml();
        document.body.appendChild(modalWrapper.firstElementChild);
            
        const newlyCreatedModal = document.getElementById('modalTurno');
        if (newlyCreatedModal) {
            newlyCreatedModal.addEventListener('hidden.bs.modal', function() {
                if (!window._isSavingTurno && window.isWizardFlow && window.wizardCurrentStep === 'turnos') {
                    Swal.fire({
                        title: "¿Omitir Turnos?",
                        text: "No has guardado el turno actual. ¿Deseas saltar al siguiente paso?",
                        icon: "warning",
                        showCancelButton: true,
                        confirmButtonText: "Sí, ir a Bonos",
                        cancelButtonText: "No, seguir editando",
                        reverseButtons: true
                    }).then((result) => {
                        if (result.isConfirmed) {
                            if (typeof window.abrirConfigBonoWizard === 'function') {
                                window.abrirConfigBonoWizard();
                            }
                        } else {
                            openModalHorario(currentTurnoId);
                        }
                    });
                }
                window._isSavingTurno = false; // reset
            });
        }

        setupModalListeners();
    }
}

let allEmployeesBulk = [];
let bulkSortState = { key: null, direction: 1 }; // 1 asc, -1 desc

async function loadBulkData() {
    // 1. Cargar empleados activos
    try {
        const response = await fetch('/api/empleados/search/?limit=1000&activo=true');
        if (!response.ok) throw new Error("Error cargando empleados");
        const data = await response.json();
        allEmployeesBulk = data.empleados || data;
        renderBulkEmployeeList(allEmployeesBulk);
    } catch (error) {
        console.error("loadBulkData - Error empleados:", error);
    }

    // 2. Poblar select de áreas para filtro
    const areaSelect = document.getElementById('filter-area-bulk');
    if (areaSelect && allEmployeesBulk.length > 0) {
        const areas = [...new Set(allEmployeesBulk.map(e => e.area).filter(a => a))].sort();
        areaSelect.innerHTML = '<option value="">Todas las Áreas</option>' +
            areas.map(a => `<option value="${a}">${a}</option>`).join('');
    }

    // 3. Poblar select de turnos
    // Si turnosList (de horarios.js) está vacío porque el usuario no visitó
    // Configuración primero, lo cargamos directamente desde la API.
    const select = document.getElementById('bulk-turno-id');
    if (select) {
        let lista = (typeof turnosList !== 'undefined' && turnosList.length > 0)
            ? turnosList
            : null;

        if (!lista) {
            try {
                const res = await fetch('/api/turnos/');
                if (res.ok) {
                    lista = await res.json();
                    // Guardar en la variable global para que no repita fetch si el usuario
                    // navega a Configuración después
                    if (typeof turnosList !== 'undefined') {
                        turnosList.splice(0, turnosList.length, ...(lista || []));
                    }
                }
            } catch (e) {
                console.error("loadBulkData - Error cargando turnos:", e);
                lista = [];
            }
        }

        select.innerHTML = '<option value="">Seleccione un turno...</option>' +
            (lista || []).map(t => {
                const tipoPlanificacion = (t.tipo_programacion === 'BOLSA_FLEXIBLE' || t.tipo_programacion === 'FLEXIBLE_BOLSA')
                    ? 'Bolsa Flexible'
                    : 'Ciclo Inteligente';
                return `<option value="${t.id}">${t.nombre} (${tipoPlanificacion})</option>`;
            }).join('');
    }

    // 4. Set fecha hoy
    const fechaInput = document.getElementById('bulk-fecha-inicio');
    if (fechaInput && !fechaInput.value) {
        fechaInput.value = new Date().toISOString().split('T')[0];
    }

    // 5. Resetear cache de áreas para que la primera selección siempre dispare el fetch
    _lastBulkAreas = '';
    const turnoSelect = document.getElementById('bulk-turno-id');
    if (turnoSelect) {
        turnoSelect.innerHTML = '<option value="">Seleccione empleados primero...</option>';
    }
    const areaHint = document.getElementById('bulk-turno-area-hint');
    if (areaHint) areaHint.innerHTML = '';
}

window.sortBulkEmployees = function (key) {
    if (bulkSortState.key === key) {
        bulkSortState.direction *= -1;
    } else {
        bulkSortState.key = key;
        bulkSortState.direction = 1;
    }

    allEmployeesBulk.sort((a, b) => {
        let valA, valB;
        if (key === 'empleado') {
            valA = (a.nombre_completo || a.nombre || '').toLowerCase();
            valB = (b.nombre_completo || b.nombre || '').toLowerCase();
        } else {
            valA = (a[key] || '').toString().toLowerCase();
            valB = (b[key] || '').toString().toLowerCase();
        }

        if (valA < valB) return -1 * bulkSortState.direction;
        if (valA > valB) return 1 * bulkSortState.direction;
        return 0;
    });

    filterBulkEmployees();
    updateSortIcons();
}

function updateSortIcons() {
    ['empleado', 'area', 'cargo'].forEach(k => {
        const icon = document.getElementById(`sort-icon-${k}`);
        if (icon) icon.className = 'bi bi-arrow-down-up small text-muted';
    });

    if (bulkSortState.key) {
        const icon = document.getElementById(`sort-icon-${bulkSortState.key}`);
        if (icon) {
            icon.className = bulkSortState.direction === 1 ? 'bi bi-sort-alpha-down text-primary' : 'bi bi-sort-alpha-up-alt text-primary';
        }
    }
}

function renderBulkEmployeeList(list) {
    const tbody = document.getElementById('bulk-emp-list');
    if (!tbody) return;

    if (list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center p-4">No se encontraron empleados</td></tr>';
        return;
    }

    tbody.innerHTML = list.map(e => `
        <tr onclick="toggleOneBulk(this)" style="cursor: pointer;">
            <td class="ps-3">
                <input type="checkbox" class="form-check-input check-emp-bulk" value="${e.id}" onclick="event.stopPropagation(); updateBulkCount()">
            </td>
            <td>
                <div class="fw-bold">${e.nombre_completo || e.nombre}</div>
                <div class="small text-muted">ID: ${e.id_empleado || e.id}</div>
            </td>
            <td><span class="badge bg-light text-dark border">${e.area || 'Sin Área'}</span></td>
            <td class="small text-muted">${e.cargo || 'Sin Cargo'}</td>
        </tr>
    `).join('');
}

function filterBulkEmployees() {
    const q = document.getElementById('search-emp-bulk').value.toLowerCase();
    const area = document.getElementById('filter-area-bulk').value;

    const filtered = allEmployeesBulk.filter(e => {
        const matchesSearch = (e.nombre_completo || e.nombre || '').toLowerCase().includes(q) ||
            (e.id_empleado || '').toLowerCase().includes(q);

        const matchesArea = !area || (e.area === area);

        return matchesSearch && matchesArea;
    });

    renderBulkEmployeeList(filtered);
}

function toggleAllBulk(chk) {
    document.querySelectorAll('.check-emp-bulk').forEach(c => c.checked = chk.checked);
    updateBulkCount();
}

function toggleOneBulk(row) {
    const chk = row.querySelector('.check-emp-bulk');
    if (chk) {
        chk.checked = !chk.checked;
        updateBulkCount();
    }
}

function updateBulkCount() {
    const checkedBoxes = document.querySelectorAll('.check-emp-bulk:checked');
    const count = checkedBoxes.length;

    // 1. Actualizar contador y visibilidad del resumen
    const summary = document.getElementById('bulk-summary');
    const badge = document.getElementById('bulk-count');
    if (summary && badge) {
        badge.textContent = count;
        summary.style.display = count > 0 ? 'block' : 'none';
    }

    // 2. Analizar tipos de contrato de los seleccionados
    const fechaFinInput = document.getElementById('bulk-fecha-fin');
    const contratoHint = document.getElementById('bulk-contrato-hint');
    const fechaFinHintText = document.getElementById('bulk-fecha-fin-hint');
    if (!fechaFinInput || !contratoHint) return;

    if (count === 0) {
        // Sin selección: restaurar estado normal
        fechaFinInput.disabled = false;
        fechaFinInput.value = '';
        contratoHint.innerHTML = '';
        if (fechaFinHintText) fechaFinHintText.style.display = '';
        return;
    }

    // Obtener IDs seleccionados y cruzar con allEmployeesBulk para obtener tipo_contrato
    const selectedIds = new Set(Array.from(checkedBoxes).map(c => parseInt(c.value)));
    const selectedEmps = allEmployeesBulk.filter(e => selectedIds.has(e.id));

    const INDEFINIDO_TIPOS = ['INDEFINIDO', 'Indefinido', 'indefinido', 'PLAZO INDEFINIDO', 'Plazo Indefinido'];
    const isIndefinido = e => INDEFINIDO_TIPOS.some(t => (e.tipo_contrato || '').includes(t.split(' ')[0].toUpperCase()) || 
                                                         (e.tipo_contrato || '').toUpperCase().includes('INDEFINIDO'));

    const totalSeleccionados = selectedEmps.length;
    const indefinidos = selectedEmps.filter(isIndefinido).length;
    const conFecha = totalSeleccionados - indefinidos;

    if (indefinidos === totalSeleccionados) {
        // ✅ TODOS son indefinidos → bloquear fecha fin
        fechaFinInput.disabled = true;
        fechaFinInput.value = '';
        if (fechaFinHintText) fechaFinHintText.style.display = 'none';
        contratoHint.innerHTML = `
            <div class="d-flex align-items-center gap-2 p-2 rounded" 
                 style="background:rgba(16,185,129,0.12); border:1px solid rgba(16,185,129,0.35);">
                <i class="bi bi-lock-fill text-success fs-6"></i>
                <span class="small fw-bold text-success">
                    Contrato${indefinidos > 1 ? 's' : ''} Indefinido${indefinidos > 1 ? 's' : ''} — Sin fecha de término
                </span>
                <span class="badge bg-success ms-auto">∞ Proyección ilimitada</span>
            </div>`;
    } else if (indefinidos > 0 && conFecha > 0) {
        // ⚠️ MIXTO → advertencia pero sin bloquear
        fechaFinInput.disabled = false;
        if (fechaFinHintText) fechaFinHintText.style.display = '';
        contratoHint.innerHTML = `
            <div class="d-flex align-items-center gap-2 p-2 rounded"
                 style="background:rgba(245,158,11,0.12); border:1px solid rgba(245,158,11,0.35);">
                <i class="bi bi-exclamation-triangle-fill text-warning fs-6"></i>
                <span class="small fw-bold text-warning-emphasis">
                    Selección mixta: ${indefinidos} indefinido${indefinidos > 1 ? 's' : ''} y ${conFecha} con contrato fijo.
                    <br>
                    <span class="fw-normal text-muted">Deja Vigencia Hasta vacía para no afectar a los indefinidos.</span>
                </span>
            </div>`;
    } else {
        // Todos son de plazo fijo u otro → estado normal
        fechaFinInput.disabled = false;
        contratoHint.innerHTML = '';
        if (fechaFinHintText) fechaFinHintText.style.display = '';
    }

    // 3. Filtrar el selector de turno por área(s) de los empleados seleccionados
    _updateBulkTurnosByAreas(selectedEmps);
}

// Cache de la última consulta de áreas para evitar peticiones redundantes
let _lastBulkAreas = '';
let _bulkTurnoDebounce = null;

async function _updateBulkTurnosByAreas(selectedEmps) {
    const select = document.getElementById('bulk-turno-id');
    const areaHint = document.getElementById('bulk-turno-area-hint');
    if (!select) return;

    if (!selectedEmps || selectedEmps.length === 0) {
        // Sin selección → recargar todos los turnos
        if (_lastBulkAreas !== '__all__') {
            _lastBulkAreas = '__all__';
            await _fetchAndPopulateBulkTurnos(null, areaHint);
        }
        return;
    }

    // Obtener áreas únicas y no vacías
    const areas = [...new Set(selectedEmps.map(e => e.area).filter(a => a))];
    const areasKey = areas.sort().join(',');

    // Evitar petición si las áreas no cambiaron
    if (areasKey === _lastBulkAreas) return;

    // Debounce: esperar 300ms antes de hacer la petición (evita flood al marcar varios)
    clearTimeout(_bulkTurnoDebounce);
    _bulkTurnoDebounce = setTimeout(async () => {
        _lastBulkAreas = areasKey;
        await _fetchAndPopulateBulkTurnos(areas, areaHint);
    }, 300);
}

async function _fetchAndPopulateBulkTurnos(areas, hintEl) {
    const select = document.getElementById('bulk-turno-id');
    if (!select) return;

    const prevValue = select.value; // Conservar selección actual si sigue siendo válida

    // Mostrar indicador de carga en el select
    select.innerHTML = '<option value="">Cargando turnos...</option>';
    select.disabled = true;

    try {
        let lista;
        let hintHtml = '';

        if (!areas || areas.length === 0) {
            // Sin área → traer todos
            const res = await fetch('/api/turnos/?activo=true');
            lista = res.ok ? await res.json() : [];
            hintHtml = '';
        } else if (areas.length === 1) {
            // Un área específica
            const res = await fetch(`/api/turnos/?area=${encodeURIComponent(areas[0])}&activo=true`);
            lista = res.ok ? await res.json() : [];
            hintHtml = `
                <div class="d-flex align-items-center gap-1 mt-1" style="font-size:0.78rem;">
                    <i class="bi bi-funnel-fill text-primary" style="font-size: 0.75rem;"></i>
                    <span class="text-muted">Mostrando turnos para <strong class="text-primary">${areas[0]}</strong> + globales</span>
                </div>`;
        } else {
            // Múltiples áreas: traer todos y mostrar advertencia
            const res = await fetch('/api/turnos/?activo=true');
            lista = res.ok ? await res.json() : [];
            hintHtml = `
                <div class="d-flex align-items-center gap-1 mt-1" style="font-size:0.78rem;">
                    <i class="bi bi-exclamation-triangle-fill text-warning" style="font-size: 0.75rem;"></i>
                    <span class="text-muted">Selección de <strong>${areas.length} áreas distintas</strong> — mostrando todos los turnos</span>
                </div>`;
        }

        if (hintEl) hintEl.innerHTML = hintHtml;

        select.innerHTML = '<option value="">Seleccione un turno...</option>' +
            (lista || []).map(t => {
                const tipoPlanificacion = (t.tipo_programacion === 'BOLSA_FLEXIBLE' || t.tipo_programacion === 'FLEXIBLE_BOLSA')
                    ? 'Bolsa Flexible'
                    : 'Ciclo Inteligente';
                return `<option value="${t.id}">${t.nombre} (${tipoPlanificacion})</option>`;
            }).join('');

        // Restaurar selección previa si sigue disponible
        if (prevValue && select.querySelector(`option[value="${prevValue}"]`)) {
            select.value = prevValue;
        }
    } catch (e) {
        console.error('_fetchAndPopulateBulkTurnos error:', e);
        select.innerHTML = '<option value="">Error al cargar turnos</option>';
    } finally {
        select.disabled = false;
    }
}

async function submitBulkAsignacion() {
    const selectedIds = Array.from(document.querySelectorAll('.check-emp-bulk:checked')).map(c => parseInt(c.value));
    const turnoId = document.getElementById('bulk-turno-id').value;
    const fecha = document.getElementById('bulk-fecha-inicio').value;
    const fechaFin = document.getElementById('bulk-fecha-fin').value;
    const reemplazar = document.getElementById('bulk-reemplazar')?.checked || false;

    if (selectedIds.length === 0) return Avisos.falta('Falta elegir a las personas. Marque al menos una.');
    if (!turnoId) return Avisos.falta('Falta elegir el turno.');
    if (!fecha) return Avisos.falta('Falta la fecha de inicio.');

    const accion = reemplazar ? 'reemplazar el horario existente' : 'asignar un turno nuevo';
    const confirmMsg = fechaFin
        ? `¿Desea ${accion} a ${selectedIds.length} empleados desde el ${fecha} hasta el ${fechaFin}?`
        : `¿Desea ${accion} a ${selectedIds.length} empleados de forma indefinida a partir del ${fecha}?`;

    if (!await uiConfirm(confirmMsg)) return;

    // --- UI: Bloquear botón con spinner ---
    const btn = document.querySelector('[onclick="submitBulkAsignacion()"]');
    const btnOriginalHTML = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status"></span>Procesando...`;
    }

    // Ocultar banner previo si existía
    const prevBanner = document.getElementById('bulk-result-banner');
    if (prevBanner) prevBanner.remove();

    try {
        const bodyPayload = {
            empleados_ids: selectedIds,
            turno_id: parseInt(turnoId),
            fecha_inicio: fecha,
            reemplazar: reemplazar
        };
        if (fechaFin) bodyPayload.fecha_fin = fechaFin;

        const response = await fetch('/api/turnos/bulk-assign/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bodyPayload)
        });

        if (!response.ok) throw new Error("Error en la asignación masiva");
        const res = await response.json();

        // --- UI: Banner informativo (no bloqueante) ---
        const esRetroactivo = fecha <= new Date().toISOString().split('T')[0];
        const banner = document.createElement('div');
        banner.id = 'bulk-result-banner';
        banner.className = 'alert alert-success alert-dismissible fade show mt-3 mb-0';
        banner.role = 'alert';
        banner.innerHTML = `
            <div class="d-flex align-items-start gap-2">
                <i class="bi bi-check-circle-fill fs-5 mt-1 flex-shrink-0"></i>
                <div>
                    <strong>${res.success} asignación(es) guardada(s) correctamente.</strong>
                    ${res.errors > 0 ? `<br><span class="text-warning"><i class="bi bi-exclamation-triangle-fill text-warning" aria-hidden="true"></i> ${res.errors} con error.</span>` : ''}
                    ${esRetroactivo ? `
                    <hr class="my-2">
                    <div class="d-flex align-items-center gap-2">
                        <div class="spinner-border spinner-border-sm text-success flex-shrink-0" role="status"></div>
                        <span><strong>Reprocesando marcaciones en segundo plano</strong> desde el <strong>${fecha}</strong> hasta hoy.<br>
                        <small class="text-muted">Este proceso descarga las marcaciones desde BioAlba. Puede tardar unos segundos. 
                        Cuando termine, la grilla de asistencia estará actualizada.</small></span>
                    </div>` : ''}
                </div>
            </div>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Cerrar"></button>
        `;

        // Insertar banner bajo el botón de asignación
        const cardBody = btn ? btn.closest('.card-body') : null;
        if (cardBody) {
            cardBody.appendChild(banner);
        }

        // Si es retroactivo, auto-ocultar spinner del banner después de 15s (estimado)
        if (esRetroactivo) {
            setTimeout(() => {
                const spinner = banner.querySelector('.spinner-border');
                if (spinner) {
                    spinner.replaceWith(Object.assign(document.createElement('i'), {
                        className: 'bi bi-check2-all text-success fs-5 flex-shrink-0'
                    }));
                    const msg = banner.querySelector('strong:last-of-type');
                    if (msg) msg.textContent = 'Reprocesamiento completado (estimado).';
                }
            }, 20000);
        }

        // Refrescar lista y limpiar selección
        loadBulkData();
        const checkAll = document.getElementById('check-all-bulk');
        if (checkAll) checkAll.checked = false;
        updateBulkCount();

    } catch (error) {
        console.error(error);
        Avisos.error("No se pudo asignar el turno. " + error.message);
    } finally {
        // Restaurar botón
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = btnOriginalHTML;
        }
    }
}


function renderTurnosTable() {
    const cont = document.getElementById('turnos-fcb');
    if (!cont || !window.FichaCfg) return;
    const F = window.FichaCfg;
    const canEdit = F.puede('configuracion.horarios');
    const tipoDe = function (t) {
        const isBolsa = (t.tipo_programacion === 'BOLSA_FLEXIBLE' || t.tipo_programacion === 'FLEXIBLE_BOLSA');
        const isLibreta = isBolsa && t.modalidad_control === 'LIBRETA_180H';   // sin modalidad = reloj, igual que el cálculo
        if (isBolsa) return isLibreta ? 'Libreta 180 h, Art. 25 bis' : 'Bolsa flexible';
        return t.rotacion_dinamica_diaria ? 'Ciclo inteligente, elige la opción cada día' : 'Ciclo inteligente';
    };
    const min = function (n) { n = Number(n || 0); return n + (n === 1 ? ' minuto' : ' minutos'); };
    F.montar(cont, {
        clave: 'turnos',
        titulo: 'Turnos',
        descripcion: 'Horarios de trabajo: días, horas, colación y tolerancias. Para asignar un turno a varias personas a la vez use Empleados › Asignación masiva.',
        acciones: canEdit ? '<button type="button" class="fcB-btn" id="btn-exportar-turnos" onclick="exportarTurnosJson(this)" title="Descarga los turnos de Ciclo inteligente con sus opciones y días (sin datos personales)"><i class="bi bi-download" aria-hidden="true"></i>Exportar turnos</button>'
            + '<button type="button" class="fcB-btn pri" onclick="openModalHorario()"><i class="bi bi-plus-lg" aria-hidden="true"></i>Nuevo turno</button>' : '',
        items: turnosList.slice().sort(function (a, b) { return String(a.nombre).localeCompare(String(b.nombre), 'es'); }),
        id: function (t) { return t.id; },
        etiqueta: function (t) { return t.nombre; },
        sub: function (t) { return (t.meta_horas_semanales || 0) + ' h'; },
        apagado: function (t) { return t.activo === false; },
        vacio: 'No hay turnos. Cree el primero con «Nuevo turno».',
        ficha: function (t, panel) {
            const isBolsa = (t.tipo_programacion === 'BOLSA_FLEXIBLE' || t.tipo_programacion === 'FLEXIBLE_BOLSA');
            const areas = (t.areas && t.areas.length) ? t.areas.join(', ') : 'Sin áreas asignadas';
            const colacion = t.descuento_colacion_auto ? (t.minutos_colacion_auto || 0) + ' min' + (t.umbral_horas_colacion ? ', si trabaja ' + t.umbral_horas_colacion + ' h o más' : '') : 'No descuenta';
            const dato = function (txt) { return '<span>' + F.esc(txt) + '</span>'; };
            panel.innerHTML = F.cabeza(t.nombre, tipoDe(t))
                + F.campo('Jornada semanal', dato((t.meta_horas_semanales || 0) + ' horas' + (isBolsa ? ' · espera ' + (t.meta_horas_espera || 88) + ' h' : '')))
                + F.campo('Colación', dato(colacion))
                + F.campo('Tolerancia de atraso', dato('Aviso ' + min(t.tolerancia_retraso_alerta) + ' · descuento ' + min(t.tolerancia_retraso_descuento)))
                + F.campo('Tolerancia de salida adelantada', dato(min(t.tolerancia_salida_adelantada)))
                + F.campo('Áreas', dato(areas))
                + F.campo('En uso', dato(t.activo !== false ? 'Sí' : 'No'))
                + (canEdit ? F.pie('<button type="button" class="fcB-btn borra" onclick="deleteTurno(' + t.id + ')"><i class="bi bi-trash3" aria-hidden="true"></i>Eliminar turno</button>',
                    '<button type="button" class="fcB-btn pri" onclick="openModalHorario(' + t.id + ')"><i class="bi bi-pencil" aria-hidden="true"></i>Editar días y horarios</button>') : '');
        }
    });
}

function renderModalHtml() {
    // Asistente de 6 pasos (orden del dueño, 07-11-2026): se arma el horario en el orden en que se piensa.
    // Los campos conservan sus id y name: saveTurno, openModalHorario y los cálculos no cambian.
    const pasos = TW_PASOS.map((p, i) => `
                    <li><button type="button" class="tw-paso" data-paso="${i + 1}" onclick="twIr(${i + 1})">
                        <span class="tw-barra" aria-hidden="true"></span>
                        <span class="tw-nombre"><span class="tw-num">${i + 1}</span> ${p}</span>
                    </button></li>`).join('');
    return `
    <!-- Sin clase 'fade': la animación Bootstrap de fade causaba Layout Shifts masivos (CLS 60+) -->
    <div class="modal tw-modal" id="modalTurno" tabindex="-1" aria-labelledby="modalTurnoLabel">
        <div class="modal-dialog modal-xl modal-dialog-scrollable modal-fullscreen-lg-down">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="vn-tit">
                        <h5 class="modal-title" id="modalTurnoLabel">Nuevo turno</h5>
                        <div class="vn-sub" id="tw-sub" aria-live="polite">Paso 1 de 6 · Qué horario es</div>
                    </div>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button>
                </div>
                <nav class="tw-pasos" aria-label="Pasos para crear el turno">
                    <ol>${pasos}
                    </ol>
                </nav>
                <div class="modal-body">
                    <form id="formTurno" novalidate onsubmit="return false;">

                        <section class="tw-panel" data-paso="1" aria-labelledby="tw-t1">
                            <h6 class="tw-preg" id="tw-t1">¿Qué horario es?</h6>
                            <p class="tw-ayuda">Un nombre que se reconozca al asignarlo y el tipo de horario.</p>
                            <div class="tw-grid-2">
                                <div>
                                    <label for="input-nombre-turno" class="form-label">Nombre del turno</label>
                                    <input type="text" id="input-nombre-turno" class="form-control" name="nombre" required placeholder="Ej.: Operativo mañana" autocomplete="off">
                                </div>
                                <div>
                                    <label for="input-activo-turno" class="form-label">Estado</label>
                                    <select id="input-activo-turno" class="form-select" name="activo">
                                        <option value="true">Activo: se puede asignar</option>
                                        <option value="false">Inactivo: no se puede asignar</option>
                                    </select>
                                </div>
                            </div>
                            <span class="form-label tw-mt" id="tw-tipo-lbl">Tipo de horario</span>
                            <select id="input-tipo-programacion" class="visually-hidden" name="tipo_programacion" tabindex="-1" aria-hidden="true" onchange="onTipoProgramacionCambiado()">
                                <option value="CICLO_INTELIGENTE">Ciclo inteligente</option>
                                <option value="BOLSA_FLEXIBLE">Bolsa flexible</option>
                            </select>
                            <div class="tw-grid-2" role="radiogroup" aria-labelledby="tw-tipo-lbl">
                                <button type="button" class="vn-op tw-tipo" role="radio" aria-checked="true" data-tipo="CICLO_INTELIGENTE" onclick="twElegirTipo('CICLO_INTELIGENTE')">
                                    <span class="vn-rd" aria-hidden="true"></span>
                                    <span><b>Ciclo inteligente</b><span class="vn-t">Días y horas fijos. Si tiene varias opciones (mañana, tarde, noche), el sistema elige la del día.</span></span>
                                    <span></span>
                                </button>
                                <button type="button" class="vn-op tw-tipo" role="radio" aria-checked="false" data-tipo="BOLSA_FLEXIBLE" onclick="twElegirTipo('BOLSA_FLEXIBLE')">
                                    <span class="vn-rd" aria-hidden="true"></span>
                                    <span><b>Bolsa flexible</b><span class="vn-t">Meta de horas al mes, sin horario diario. Choferes con libreta Art. 25 bis.</span></span>
                                    <span></span>
                                </button>
                            </div>
                        </section>

                        <section class="tw-panel" data-paso="2" aria-labelledby="tw-t2" hidden>
                            <h6 class="tw-preg" id="tw-t2">¿Para qué áreas es?</h6>
                            <p class="tw-ayuda">Solo esas áreas verán este turno al asignarlo. Elija al menos una.</p>
                            <div id="container-areas-turno" class="tw-areas" role="group" aria-labelledby="tw-t2">
                                <div class="text-muted small py-2">Cargando áreas…</div>
                            </div>
                        </section>

                        <section class="tw-panel" data-paso="3" aria-labelledby="tw-t3" hidden>
                            <h6 class="tw-preg" id="tw-t3">¿Cuánto se trabaja?</h6>
                            <p class="tw-ayuda" id="tw-ayuda-3">Las horas de la semana contra las que se compara el horario.</p>
                            <div class="tw-grid-2" id="div-meta-jornada">
                                <div>
                                    <label for="input-meta-jornada" class="form-label">Horas por semana</label>
                                    <div class="input-group">
                                        <input type="number" id="input-meta-jornada" class="form-control" name="meta_horas_semanales" value="" step="0.5" min="0" oninput="updateAllCalculations()" required>
                                        <span class="input-group-text">horas</span>
                                    </div>
                                </div>
                                <div id="divRotacionDinamica" class="vn-check">
                                    <input class="form-check-input" type="checkbox" id="chkRotacionDinamicaDiaria" name="rotacion_dinamica_diaria">
                                    <label class="form-check-label" for="chkRotacionDinamicaDiaria">
                                        <strong>Elegir la opción cada día según la llegada</strong><br>
                                        <span>Para turnos rotativos sin semanas fijas (por ejemplo, mantención).</span>
                                    </label>
                                </div>
                            </div>
                            <div id="divLineaFicticia" class="tw-bolsa" style="display:none;">
                                <div class="tw-grid-3">
                                    <div id="colMetaBolsa">
                                        <label for="input-meta-bolsa" class="form-label">Meta del mes</label>
                                        <div class="input-group">
                                            <input type="number" id="input-meta-bolsa" class="form-control" value="" step="0.5" min="0" required>
                                            <span class="input-group-text">horas</span>
                                        </div>
                                        <div class="form-text">Art. 25 bis: 180 horas al mes.</div>
                                    </div>
                                    <div id="colMetaEspera">
                                        <label for="input-meta-espera" class="form-label">Tope de espera pagada</label>
                                        <div class="input-group">
                                            <input type="number" id="input-meta-espera" class="form-control" value="88.0" step="0.5" min="0" required>
                                            <span class="input-group-text">horas</span>
                                        </div>
                                        <div class="form-text">Art. 25 bis: hasta 88 horas al mes.</div>
                                    </div>
                                    <div>
                                        <label for="input-hora-ficticia" class="form-label">Hora límite para avisar inasistencia</label>
                                        <input type="time" id="input-hora-ficticia" class="form-control" name="hora_limite_ficticia" value="" required>
                                        <div class="form-text">Si a esa hora no hay marca, se avisa inasistencia (se puede corregir).</div>
                                    </div>
                                </div>
                                <div class="tw-grid-2 tw-mt" id="divModalidadControl">
                                    <div>
                                        <label for="select-modalidad-control" class="form-label">Cómo se registra la asistencia</label>
                                        <select id="select-modalidad-control" name="modalidad_control" class="form-select">
                                            <option value="RELOJ">Reloj control</option>
                                            <option value="LIBRETA_180H">Libreta Art. 25 bis (sin reloj)</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label for="input-libreta-desde" class="form-label">Sin reloj a partir de</label>
                                        <input type="date" id="input-libreta-desde" class="form-control">
                                        <div class="form-text">Antes de esta fecha se usa el reloj. Vacío: siempre con libreta.</div>
                                    </div>
                                </div>
                            </div>
                        </section>

                        <section class="tw-panel" data-paso="4" aria-labelledby="tw-t4" hidden>
                            <div class="tw-cab">
                                <div>
                                    <h6 class="tw-preg" id="tw-t4">¿Qué días y a qué hora se trabaja?</h6>
                                    <p class="tw-ayuda" id="tw-ayuda-4">Marque los días libres y escriba la entrada y la salida. Las horas del día se calculan solas.</p>
                                </div>
                                <span class="vn-pill" id="tw-total" aria-live="polite"></span>
                            </div>
                            <div id="wrapper-semanas">
                                <ul class="nav nav-pills tw-opciones" id="pills-tab-weeks" role="tablist">
                                    <!-- JS Tabs -->
                                </ul>
                                <div class="tab-content" id="pills-tabContent-weeks">
                                    <!-- JS Content -->
                                </div>
                                <div id="btn-add-week-container" class="tw-acciones-opcion" style="display:none;">
                                    <button type="button" class="btn btn-sm btn-outline-primary" onclick="addWeekTab()">
                                        <i class="bi bi-plus-lg" aria-hidden="true"></i> Agregar opción
                                    </button>
                                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="removeLastWeekTab()">
                                        <i class="bi bi-dash-lg" aria-hidden="true"></i> Quitar la última opción
                                    </button>
                                </div>
                            </div>
                        </section>

                        <section class="tw-panel" data-paso="5" aria-labelledby="tw-t5" hidden>
                            <h6 class="tw-preg" id="tw-t5">Colación y tolerancias</h6>
                            <p class="tw-ayuda">La colación es obligatoria: el cálculo la descuenta y la usa para reconocer la pausa.</p>
                            <div class="tw-grid-4">
                                <div class="vn-check tw-check-alto">
                                    <input class="form-check-input" type="checkbox" id="chkColacion" name="descuento_colacion_auto" onchange="toggleColacionInput()">
                                    <label class="form-check-label" for="chkColacion"><strong>Descontar</strong></label>
                                </div>
                                <div id="divColacionTime" style="display:none;">
                                    <label for="numColacion" class="form-label">Minutos de colación</label>
                                    <div class="input-group">
                                        <input type="number" class="form-control" id="numColacion" value="" min="0" oninput="updateAllCalculations()" required>
                                        <span class="input-group-text">min</span>
                                    </div>
                                </div>
                                <div id="divColacionUmbral" style="display:none;">
                                    <label for="umbralColacion" class="form-label">Si trabajó al menos</label>
                                    <div class="input-group">
                                        <input type="number" class="form-control" id="umbralColacion" value="0" step="0.5" min="0" required>
                                        <span class="input-group-text">horas</span>
                                    </div>
                                </div>
                                <div id="divColacionTolerancia" style="display:none;">
                                    <label for="toleranciaExcesoColacion" class="form-label">Margen antes de exceso</label>
                                    <div class="input-group">
                                        <input type="number" class="form-control" id="toleranciaExcesoColacion" name="tolerancia_exceso_colacion_minutos" min="0" step="1" value="0">
                                        <span class="input-group-text">min</span>
                                    </div>
                                </div>
                            </div>
                            <p class="form-text">Sin marca de colación se restan los minutos, si la persona estuvo al menos esas horas. Con la pausa marcada se resta lo mayor entre la pausa y los minutos. Lo que pase de la colación más el margen queda como exceso.</p>

                            <h6 class="tw-sub">Tolerancias</h6>
                            <p class="tw-ayuda">Con 0 no hay margen. La deuda del día siempre cuenta el tiempo que falta; las tolerancias solo deciden si el día se marca como atraso o salida adelantada.</p>
                            <div class="tw-grid-2">
                                <fieldset class="tw-grupo gobernanza-col">
                                    <legend>Entrada</legend>
                                    <div>
                                        <label for="input-tol-alerta" class="form-label">Avisar atraso desde</label>
                                        <div class="input-group"><input type="number" id="input-tol-alerta" class="form-control" name="tolerancia_retraso_alerta" min="0" step="1" value="0"><span class="input-group-text">min</span></div>
                                        <div class="form-text">Aviso amarillo, sin marcar atraso.</div>
                                    </div>
                                    <div>
                                        <label for="input-tol-desc" class="form-label">Marcar atraso desde</label>
                                        <div class="input-group"><input type="number" id="input-tol-desc" class="form-control" name="tolerancia_retraso_descuento" min="0" step="1" value="0"><span class="input-group-text">min</span></div>
                                        <div class="form-text">Desde aquí el día queda en ATRASO.</div>
                                    </div>
                                    <div>
                                        <label for="input-anclaje" class="form-label">Llegada anticipada se cuenta en punto</label>
                                        <div class="input-group"><input type="number" id="input-anclaje" class="form-control" name="anclaje_entrada_minutos" min="0" step="1" value="0"><span class="input-group-text">min</span></div>
                                        <div class="form-text">Marcas hasta este tiempo antes se toman a la hora.</div>
                                    </div>
                                </fieldset>
                                <fieldset class="tw-grupo gobernanza-col">
                                    <legend>Salida</legend>
                                    <div>
                                        <label for="input-tol-salida" class="form-label">Marcar salida adelantada desde</label>
                                        <div class="input-group"><input type="number" id="input-tol-salida" class="form-control" name="tolerancia_salida_adelantada" min="0" step="1" value="0"><span class="input-group-text">min</span></div>
                                        <div class="form-text">Desde aquí el día queda en SALIDA ADELANTADA.</div>
                                    </div>
                                    <div>
                                        <label for="input-anclaje-salida" class="form-label">Salida tardía se cuenta en punto</label>
                                        <div class="input-group"><input type="number" id="input-anclaje-salida" class="form-control" name="anclaje_salida_minutos" min="0" step="1" value="0"><span class="input-group-text">min</span></div>
                                        <div class="form-text">Marcas hasta este tiempo después se toman a la hora.</div>
                                    </div>
                                </fieldset>
                            </div>
                            <fieldset class="tw-grupo tw-hoy">
                                <legend>Día de hoy</legend>
                                <div>
                                    <label for="input-ventana-en-curso" class="form-label">Esperar la salida hasta</label>
                                    <div class="input-group"><input type="number" id="input-ventana-en-curso" class="form-control" name="ventana_en_curso_minutos" min="0" step="1" value="0"><span class="input-group-text">min después</span></div>
                                    <div class="form-text">Con entrada y sin salida, el día sigue «en curso» hasta entonces; después queda «falta salida».</div>
                                </div>
                                <div class="gobernanza-col">
                                    <label for="input-espera-inasistencia" class="form-label">Marcar inasistencia a los</label>
                                    <div class="input-group"><input type="number" id="input-espera-inasistencia" class="form-control" name="espera_inasistencia_minutos" min="0" step="1" value="0"><span class="input-group-text">min después</span></div>
                                    <div class="form-text">Sin ninguna marca, la inasistencia aparece entonces.</div>
                                </div>
                            </fieldset>
                        </section>

                        <section class="tw-panel" data-paso="6" aria-labelledby="tw-t6" hidden>
                            <h6 class="tw-preg" id="tw-t6">Revise antes de guardar</h6>
                            <p class="tw-ayuda">Use «Cambiar» para volver a un paso. Al guardar se recalcula el tramo abierto de las personas con este turno.</p>
                            <div id="tw-resumen" class="tw-resumen"></div>
                        </section>
                    </form>
                </div>
                <div class="modal-footer tw-pie">
                    <button type="button" class="btn btn-outline-secondary" id="tw-atras" onclick="twIr(twPaso - 1)"><i class="bi bi-chevron-left" aria-hidden="true"></i> Atrás</button>
                    <span class="tw-espacio"></span>
                    <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancelar</button>
                    <button type="button" class="btn btn-outline-primary" id="tw-guardar-ya" onclick="saveTurno()" hidden>Guardar cambios</button>
                    <button type="button" class="btn btn-primary" id="tw-siguiente" onclick="twSiguiente()">Siguiente <i class="bi bi-chevron-right" aria-hidden="true"></i></button>
                    <button type="button" class="btn btn-primary" id="tw-guardar" onclick="saveTurno()" hidden>Guardar turno</button>
                </div>
            </div>
        </div>
    </div>
    `;
}

// ── Asistente de pasos ───────────────────────────────────────────────────────
const TW_PASOS = ['Qué horario es', 'Para qué áreas', 'Cuánto se trabaja', 'Días y horas', 'Colación y tolerancias', 'Revisar y guardar'];
let twPaso = 1;

function twEsBolsa() {
    const t = document.getElementById('input-tipo-programacion')?.value;
    return t === 'BOLSA_FLEXIBLE' || t === 'FLEXIBLE_BOLSA';
}

// Va al paso n (1..6). Se puede saltar a cualquier paso; «Siguiente» revisa el paso actual antes de avanzar.
function twIr(n) {
    n = Math.max(1, Math.min(TW_PASOS.length, n));
    twPaso = n;
    document.querySelectorAll('#modalTurno .tw-panel').forEach(p => { p.hidden = Number(p.dataset.paso) !== n; });
    document.querySelectorAll('#modalTurno .tw-paso').forEach(b => {
        const k = Number(b.dataset.paso);
        b.classList.toggle('hecho', k < n);
        if (k === n) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current');
    });
    const sub = document.getElementById('tw-sub');
    const nombre = document.getElementById('input-nombre-turno')?.value.trim();
    if (sub) sub.textContent = `Paso ${n} de ${TW_PASOS.length} · ${TW_PASOS[n - 1]}` + (nombre && n > 1 ? ` · ${nombre}` : '');
    const atras = document.getElementById('tw-atras');
    const sig = document.getElementById('tw-siguiente');
    const guardar = document.getElementById('tw-guardar');
    const guardarYa = document.getElementById('tw-guardar-ya');
    if (atras) atras.hidden = n === 1;
    if (sig) {
        sig.hidden = n === TW_PASOS.length;
        sig.innerHTML = `<span class="tw-sig-larga">Siguiente: ${TW_PASOS[n] || ''}</span><span class="tw-sig-corta">Siguiente</span> <i class="bi bi-chevron-right" aria-hidden="true"></i>`;
    }
    if (guardar) guardar.hidden = n !== TW_PASOS.length;
    // Al editar un turno se puede guardar desde cualquier paso
    if (guardarYa) guardarYa.hidden = !currentTurnoId || n === TW_PASOS.length;
    if (n === 4) twActualizarTotal();
    if (n === TW_PASOS.length) twResumen();
    const body = document.querySelector('#modalTurno .modal-body');
    if (body) body.scrollTop = 0;
}
window.twIr = twIr;

// Revisa lo mínimo del paso actual. Devuelve false y muestra qué falta si no está completo.
function twFalta(mensaje, idCampo) {
    Avisos.falta(mensaje);
    const el = idCampo && document.getElementById(idCampo);
    if (el) setTimeout(() => el.focus(), 50);
    return false;
}
function twValidar(n) {
    if (n === 1 && !document.getElementById('input-nombre-turno').value.trim()) {
        return twFalta('Falta el nombre del turno.', 'input-nombre-turno');
    }
    if (n === 2 && !document.querySelector('.chk-area-turno:checked')) {
        return twFalta('Falta el área. Elija al menos una para el turno.');
    }
    if (n === 3) {
        if (twEsBolsa()) {
            if (!document.getElementById('input-meta-bolsa').value) return twFalta('Falta la meta del mes de la bolsa flexible.', 'input-meta-bolsa');
            if (!document.getElementById('input-hora-ficticia').value) return twFalta('Falta la hora límite para avisar inasistencia.', 'input-hora-ficticia');
        } else if (!document.getElementById('input-meta-jornada').value) {
            return twFalta('Faltan las horas por semana.', 'input-meta-jornada');
        }
    }
    if (n === 5 && (!document.getElementById('chkColacion').checked || !(parseInt(document.getElementById('numColacion').value, 10) > 0))) {
        return twFalta('Falta la colación. Marque «Descontar colación» y escriba los minutos.', document.getElementById('chkColacion').checked ? 'numColacion' : 'chkColacion');
    }
    return true;
}
function twSiguiente() {
    if (twValidar(twPaso)) twIr(twPaso + 1);
}
window.twSiguiente = twSiguiente;

// Las tarjetas del tipo de horario manejan el selector oculto que leen saveTurno y los cálculos
function twElegirTipo(tipo) {
    const sel = document.getElementById('input-tipo-programacion');
    if (!sel || sel.value === tipo) return;
    sel.value = tipo;
    onTipoProgramacionCambiado();
}
window.twElegirTipo = twElegirTipo;

function twSincronizarTipo() {
    const tipo = document.getElementById('input-tipo-programacion')?.value;
    const bolsa = twEsBolsa();
    document.querySelectorAll('#modalTurno .tw-tipo').forEach(b => {
        const sel = b.dataset.tipo === tipo || (bolsa && b.dataset.tipo === 'BOLSA_FLEXIBLE');
        b.setAttribute('aria-checked', sel ? 'true' : 'false');
        b.tabIndex = sel ? 0 : -1;
    });
    const a3 = document.getElementById('tw-ayuda-3');
    if (a3) a3.textContent = bolsa ? 'La meta del mes, el tope de espera y cómo se registra la asistencia.' : 'Las horas de la semana contra las que se compara el horario.';
    const a4 = document.getElementById('tw-ayuda-4');
    if (a4) a4.textContent = bolsa ? 'Marque los días libres de la semana. La bolsa no tiene horario diario.' : 'Marque los días libres y escriba la entrada y la salida. Las horas del día se calculan solas.';
}

// Total de la primera opción contra las horas por semana
function twActualizarTotal() {
    const pill = document.getElementById('tw-total');
    if (!pill) return;
    if (twEsBolsa()) { pill.hidden = true; return; }
    const cont = document.querySelector('#modalTurno .week-container.active') || document.querySelector('#modalTurno .week-container');
    if (!cont) { pill.hidden = true; return; }
    const total = Array.from(cont.querySelectorAll('.hours-calc')).reduce((a, i) => a + (parseFloat(i.value) || 0), 0);
    const meta = parseFloat(document.getElementById('input-meta-jornada')?.value);
    const fmt = (x) => (Math.round(x * 100) / 100).toLocaleString('es-CL');
    pill.hidden = false;
    pill.textContent = isNaN(meta) ? `${fmt(total)} h por semana` : `${fmt(total)} h de ${fmt(meta)} h por semana`;
    pill.classList.toggle('tw-ok', !isNaN(meta) && Math.abs(total - meta) < 0.01);
    pill.classList.toggle('tw-dif', !isNaN(meta) && Math.abs(total - meta) >= 0.01);
}

function twEsc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// Paso 6: lo que se va a guardar, en datos legibles, con un botón para volver a cada paso
function twResumen() {
    const cont = document.getElementById('tw-resumen');
    if (!cont) return;
    const v = (id) => document.getElementById(id)?.value || '';
    const bolsa = twEsBolsa();
    const areas = Array.from(document.querySelectorAll('.chk-area-turno:checked')).map(c => c.value);
    const opciones = Array.from(document.querySelectorAll('#pills-tab-weeks li')).filter(li => li.style.display !== 'none').map(li => li.textContent.trim());
    const colacion = document.getElementById('chkColacion').checked
        ? `${v('numColacion') || '—'} min si trabajó ${v('umbralColacion') || 0} h; margen ${v('toleranciaExcesoColacion') || 0} min`
        : 'Sin descontar (falta)';
    const tol = bolsa
        ? `Esperar la salida ${v('input-ventana-en-curso') || 0} min`
        : `Atraso desde ${v('input-tol-desc') || 0} min · salida adelantada desde ${v('input-tol-salida') || 0} min`;
    const bloques = [
        [1, 'Qué horario es', [['Nombre', v('input-nombre-turno') || '—'], ['Tipo', bolsa ? 'Bolsa flexible' : 'Ciclo inteligente'], ['Estado', v('input-activo-turno') === 'false' ? 'Inactivo' : 'Activo']]],
        [2, 'Para qué áreas', [['Áreas', areas.length ? areas.join(', ') : 'Ninguna (falta)']]],
        [3, 'Cuánto se trabaja', bolsa
            ? [['Meta del mes', `${v('input-meta-bolsa') || '—'} h`], ['Tope de espera', `${v('input-meta-espera') || '—'} h`], ['Hora límite', v('input-hora-ficticia') || '—'], ['Registro', v('select-modalidad-control') === 'LIBRETA_180H' ? `Libreta${v('input-libreta-desde') ? ' desde ' + v('input-libreta-desde') : ''}` : 'Reloj']]
            : [['Horas por semana', `${v('input-meta-jornada') || '—'} h`], ['Elige la opción cada día', document.getElementById('chkRotacionDinamicaDiaria')?.checked ? 'Sí' : 'No']]],
        [4, 'Días y horas', [['Opciones', opciones.length ? opciones.join(', ') : '—']]],
        [5, 'Colación y tolerancias', [['Colación', colacion], ['Tolerancias', tol]]]
    ];
    cont.innerHTML = bloques.map(([n, titulo, datos]) => `
        <div class="tw-res">
            <div class="tw-res-cab"><b>${twEsc(titulo)}</b><button type="button" class="btn btn-link btn-sm" onclick="twIr(${n})">Cambiar</button></div>
            <div class="vn-kvs">${datos.map(([k, val]) => `<div><span>${twEsc(k)}</span><b>${twEsc(val)}</b></div>`).join('')}</div>
        </div>`).join('');
}

let activeWeeksCount = 1;

function setupModalListeners(numWeeks = 1) {
    activeWeeksCount = 0; // Reset para addWeekTab
    const tabContainer = document.getElementById('pills-tab-weeks');
    const contentContainer = document.getElementById('pills-tabContent-weeks');
    if (!tabContainer || !contentContainer) return;

    tabContainer.innerHTML = '';
    contentContainer.innerHTML = '';

    for (let i = 1; i <= numWeeks; i++) {
        addWeekTab(false); // false = no llamar handleTipoProgramacionChange internamente
    }

    // Switch to first tab
    const firstTab = tabContainer.querySelector('button');
    if (firstTab) firstTab.click();

    // No llamar handleTipoProgramacionChange aquí:
    // El caller (openModalHorario) es responsable de llamarlo UNA sola vez al final.
}

window.addWeekTab = function (triggerChange = true) {
    activeWeeksCount++;
    const i = activeWeeksCount;
    const tabContainer = document.getElementById('pills-tab-weeks');
    const contentContainer = document.getElementById('pills-tabContent-weeks');

    // Nombre de la pestaña según tipo: Ciclo Inteligente usa la etiqueta, otros usan "Semana"
    const tipoSelect = document.querySelector('select[name="tipo_programacion"]');
    const isInteligente = tipoSelect && (tipoSelect.value === 'CICLO_INTELIGENTE' || tipoSelect.value === 'DINAMICO_FLEXIBLE');
    const tabName = isInteligente ? `Opción ${i}` : `Semana ${i}`;

    // Create Tab
    const li = document.createElement('li');
    li.className = 'nav-item';
    li.innerHTML = `
        <button class="nav-link ${i === 1 ? 'active' : ''}" id="pill-week-${i}-tab" data-bs-toggle="pill" 
            data-bs-target="#week-container-${i}" type="button" role="tab">${tabName}</button>
    `;
    tabContainer.appendChild(li);

    // Create Content
    const div = document.createElement('div');
    div.className = `tab-pane fade ${i === 1 ? 'show active' : ''} week-container`;
    div.id = `week-container-${i}`;
    div.role = 'tabpanel';

    const dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
    div.innerHTML = `
        <div class="row mb-2 etiqueta-bloque-container" style="${isInteligente ? '' : 'display:none;'}">
            <div class="col-sm-8 col-md-5">
                <label for="etiqueta-bloque-${i}" class="form-label">Nombre de la opción</label>
                <input type="text" id="etiqueta-bloque-${i}" class="form-control etiqueta-input" list="etiquetas-sugeridas" placeholder="Ej: Mañana, Tarde, Noche" value="" oninput="document.getElementById('pill-week-${i}-tab').innerText = this.value.trim() || 'Opción ${i}'">
                <datalist id="etiquetas-sugeridas">
                    <option value="Mañana"></option>
                    <option value="Tarde"></option>
                    <option value="Noche"></option>
                    <option value="Jornada Normal"></option>
                </datalist>
            </div>
        </div>
        <div class="table-responsive">
            <table class="table table-sm text-center align-middle tw-tabla">
                <thead>
                    <tr>
                        <th scope="col" class="text-start">Día</th>
                        <th scope="col">Libre</th>
                        <th scope="col">Entrada</th>
                        <th scope="col">Salida</th>
                        <th scope="col">Pasa la medianoche</th>
                        <th scope="col" class="col-teoricas">Horas del día</th>
                    </tr>
                </thead>
                <tbody class="dias-input-body">
                    ${dias.map((dia, index) => `
                        <tr data-day="${index}">
                            <td class="text-start fw-semibold">${dia}</td>
                            <td><input type="checkbox" id="chk-libre-w${i}-d${index}" name="chk-libre-w${i}-d${index}" class="form-check-input chk-libre" onchange="toggleDiaRow(this)"></td>
                            <td><input type="time" id="time-in-w${i}-d${index}" name="time-in-w${i}-d${index}" class="form-control form-control-sm time-in" value="08:00" oninput="updateAllCalculations()"></td>
                            <td><input type="time" id="time-out-w${i}-d${index}" name="time-out-w${i}-d${index}" class="form-control form-control-sm time-out" value="16:00" oninput="updateAllCalculations()"></td>
                            <td><input type="checkbox" id="chk-cruce-w${i}-d${index}" name="chk-cruce-w${i}-d${index}" class="form-check-input chk-cruce" onchange="updateAllCalculations()"></td>
                            <td><input type="number" id="hours-calc-w${i}-d${index}" name="hours-calc-w${i}-d${index}" class="form-control form-control-sm hours-calc" value="8" step="0.5"></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
    contentContainer.appendChild(div);

    if (triggerChange) handleTipoProgramacionChange();
}

window.removeLastWeekTab = function () {
    if (activeWeeksCount <= 1) return;
    const tabContainer = document.getElementById('pills-tab-weeks');
    const contentContainer = document.getElementById('pills-tabContent-weeks');

    tabContainer.removeChild(tabContainer.lastChild);
    contentContainer.removeChild(contentContainer.lastChild);
    activeWeeksCount--;

    // Activar la anterior si borramos la activa
    const tabs = tabContainer.querySelectorAll('button');
    tabs[tabs.length - 1].click();
}

function toggleDiaRow(chk) {
    const row = chk.closest('tr');
    const inputs = row.querySelectorAll('input:not(.chk-libre)');
    inputs.forEach(input => {
        input.disabled = chk.checked;
        if (input.classList.contains('hours-calc') && chk.checked) input.value = 0;
    });
    updateAllCalculations();
}



function toggleColacionInput() {
    const chk = document.getElementById('chkColacion');
    const div = document.getElementById('divColacionTime');
    const divUmbral = document.getElementById('divColacionUmbral');
    const divTol = document.getElementById('divColacionTolerancia');
    if (div) div.style.display = chk.checked ? '' : 'none';
    if (divUmbral) divUmbral.style.display = chk.checked ? '' : 'none';
    if (divTol) divTol.style.display = chk.checked ? '' : 'none';
    updateAllCalculations();
}

function closeModalHorario(fromSave = false) {
    const el = document.getElementById('modalTurno');
    if (el) {
        const modal = bootstrap.Modal.getInstance(el);
        if (modal) modal.hide();
    }

    if (!fromSave && window.isWizardFlow && window.wizardCurrentStep === 'turnos') {
        if (window._isSavingTurno) {
            window._isSavingTurno = false;
            return;
        }
        Swal.fire({
            title: "¿Omitir Horarios?",
            text: "No has guardado el horario actual. ¿Deseas saltar al siguiente paso?",
            icon: "warning",
            showCancelButton: true,
            confirmButtonText: "Sí, ir a Bonos",
            cancelButtonText: "No, seguir editando",
            reverseButtons: true
        }).then((result) => {
            if (result.isConfirmed) {
                if (typeof window.abrirConfigBonoWizard === 'function') {
                    window.abrirConfigBonoWizard();
                }
            } else {
                if (typeof openModalHorario === 'function') {
                    openModalHorario();
                }
            }
        });
    }
}

// ==========================================
// AUTOMATION LOGIC
// ==========================================
// Cambio hecho por la persona en el selector de tipo: la modalidad sugerida sigue al tipo (Bolsa Flexible = libreta; el resto = reloj).
// Se puede cambiar después a mano. No corre al abrir un turno guardado, así no pisa lo que ya tiene.
function onTipoProgramacionCambiado() {
    const tipo = document.querySelector('select[name="tipo_programacion"]')?.value;
    const sel = document.getElementById('select-modalidad-control');
    if (sel) sel.value = (tipo === 'BOLSA_FLEXIBLE' || tipo === 'FLEXIBLE_BOLSA') ? 'LIBRETA_180H' : 'RELOJ';
    handleTipoProgramacionChange();
}
window.onTipoProgramacionCambiado = onTipoProgramacionCambiado;

function handleTipoProgramacionChange() {
    const tipoSelect = document.querySelector('select[name="tipo_programacion"]');
    if (!tipoSelect) return;

    const tipo = tipoSelect.value;
    const isFlexible = tipo === 'BOLSA_FLEXIBLE' || tipo === 'FLEXIBLE_BOLSA';
    const isRotativo = tipo === 'CICLO_INTELIGENTE' || tipo === 'DINAMICO_FLEXIBLE';

    twSincronizarTipo();

    const divRotacionDinamica = document.getElementById('divRotacionDinamica');
    if (divRotacionDinamica) divRotacionDinamica.style.display = isRotativo ? '' : 'none';

    // Visibilidad del bloque de Hora Ficticia: sólo visible en modo Bolsa Flexible
    const divLineaFicticia = document.getElementById('divLineaFicticia');
    if (divLineaFicticia) divLineaFicticia.style.display = isFlexible ? '' : 'none';

    const divMetaJornada = document.getElementById('div-meta-jornada');
    if (divMetaJornada) divMetaJornada.style.display = isFlexible ? 'none' : '';

    // Ocultar Gobernanza de Tiempos si es Flexible
    document.querySelectorAll('.gobernanza-col').forEach(col => {
        col.style.display = isFlexible ? 'none' : '';
    });



    // Actualiza el texto de las pestañas de semanas según el tipo de programación activo
    document.querySelectorAll('#pills-tab-weeks .nav-link').forEach((tab, index) => {
        // Obtenemos el input correspondiente si existe para preservar la etiqueta ingresada
        const etiquetaInput = document.getElementById(`etiqueta-bloque-${index + 1}`);
        const currentEtiqueta = etiquetaInput && etiquetaInput.value.trim() ? etiquetaInput.value.trim() : `Opción ${index + 1}`;
        tab.textContent = (tipo === 'CICLO_INTELIGENTE' || tipo === 'DINAMICO_FLEXIBLE') ? currentEtiqueta : `Semana ${index + 1}`;
    });

    const divAddWeek = document.getElementById('btn-add-week-container');
    if (divAddWeek) divAddWeek.style.display = isRotativo ? 'block' : 'none';

    // Mostrar/ocultar los inputs de nombre del ciclo
    document.querySelectorAll('.etiqueta-bloque-container').forEach(container => {
        container.style.display = (tipo === 'CICLO_INTELIGENTE' || tipo === 'DINAMICO_FLEXIBLE') ? '' : 'none';
    });

    // Si cambia a no-rotativo y hay semanas extra visibles, ocultarlas sin destruir el DOM:
    // Ocultamos las semanas extra SIN destruir el DOM (evita el bucle setupModalListeners -> handleTipoProgramacionChange)
    if (!isRotativo && activeWeeksCount > 1) {
        const tabContainer = document.getElementById('pills-tab-weeks');
        const contentContainer = document.getElementById('pills-tabContent-weeks');
        if (tabContainer && contentContainer) {
            // Ocultar tabs extras (dejar solo el primero visible)
            const tabs = tabContainer.querySelectorAll('li');
            tabs.forEach((tab, idx) => { tab.style.display = idx === 0 ? '' : 'none'; });
            // Ocultar paneles extras
            const panes = contentContainer.querySelectorAll('.week-container');
            panes.forEach((pane, idx) => {
                if (idx === 0) {
                    pane.classList.add('show', 'active');
                } else {
                    pane.classList.remove('show', 'active');
                }
            });
            // Activar el primer tab explícitamente
            const firstTabBtn = tabContainer.querySelector('button');
            if (firstTabBtn && !firstTabBtn.classList.contains('active')) firstTabBtn.click();
        }
        // NO llamar setupModalListeners(1) – eso causaba el bucle
    } else if (isRotativo) {
        // Mostrar todos los tabs de semanas cuando se vuelve a rotativo
        const tabContainer = document.getElementById('pills-tab-weeks');
        if (tabContainer) {
            tabContainer.querySelectorAll('li').forEach(tab => { tab.style.display = ''; });
        }
    }

    // Select headers and cells for Entrada, Salida, Cruce
    const indices = [3, 4, 5]; // 1-indexed: Entrada, Salida, Cruce

    const weekContainers = document.querySelectorAll('.week-container');
    if (weekContainers.length === 0) return;

    weekContainers.forEach(tbody => {
        // Table Headers
        const headers = tbody.querySelectorAll('thead th');
        indices.forEach(idx => {
            if (headers[idx - 1]) headers[idx - 1].style.visibility = isFlexible ? 'hidden' : 'visible';
        });

        // Ocultar cabecera Horas Teóricas
        const thTeoricas = tbody.querySelector('.col-teoricas');
        if (thTeoricas) thTeoricas.style.visibility = isFlexible ? 'hidden' : 'visible';

        // Table Cells
        const rows = tbody.querySelectorAll('.dias-input-body tr');
        rows.forEach(row => {
            indices.forEach(idx => {
                const cell = row.querySelector(`td:nth-child(${idx})`);
                if (cell) cell.style.visibility = isFlexible ? 'hidden' : 'visible';
            });

            // Ocultar inputs Hrs teoricas
            const inputTeo = row.querySelector('.hours-calc');
            if (inputTeo && inputTeo.parentElement) {
                inputTeo.parentElement.style.visibility = isFlexible ? 'hidden' : 'visible';
                if (isFlexible && !inputTeo.disabled) {
                    inputTeo.value = 0;
                }
            }


        });
    });

    updateAllCalculations();
}

function updateAllCalculations() {
    const tipoSelect = document.querySelector('select[name="tipo_programacion"]');
    if (!tipoSelect) return;

    const tipo = tipoSelect.value;
    if (tipo === 'BOLSA_FLEXIBLE' || tipo === 'FLEXIBLE_BOLSA') {
        document.querySelectorAll('.alert-hours-warning').forEach(alert => alert.remove());
        twActualizarTotal();
        return; // Flexible is manual
    }

    const colacionAuto = document.getElementById('chkColacion').checked;
    const minutosColacion = colacionAuto ? (parseInt(document.getElementById('numColacion').value) || 0) : 0;

    const containers = document.querySelectorAll('.week-container');
    containers.forEach(container => {
        const rows = container.querySelectorAll('.dias-input-body tr');
        rows.forEach(row => {
            const isLibre = row.querySelector('.chk-libre').checked;
            if (isLibre) {
                row.querySelector('.hours-calc').value = 0;
                return;
            }

            const tIn = row.querySelector('.time-in')?.value;
            const tOut = row.querySelector('.time-out')?.value;
            const chkCruce = row.querySelector('.chk-cruce');

            // Auto-detección inteligente de cruce de noche
            if (tIn && tOut && chkCruce) {
                if (tOut < tIn && !chkCruce.checked) {
                    chkCruce.checked = true;
                } else if (tOut > tIn && chkCruce.checked && !row.dataset.cruceManual) {
                    chkCruce.checked = false;
                }
            }

            const h1 = calculateDiff(
                tIn,
                tOut,
                chkCruce ? chkCruce.checked : false
            );

            let total = h1;
            if (total > 0) {
                total -= (minutosColacion / 60);
            }

            row.querySelector('.hours-calc').value = Math.max(0, total.toFixed(2));
        });

        // Validación de horas
        const totalSemana = Array.from(container.querySelectorAll('.hours-calc'))
            .reduce((acc, input) => acc + (parseFloat(input.value) || 0), 0);

        const metaInput = document.getElementById('input-meta-jornada');
        const metaHoras = metaInput ? parseFloat(metaInput.value) : NaN;

        let alertDiv = container.querySelector('.alert-hours-warning');
        if (!isNaN(metaHoras) && totalSemana !== metaHoras && totalSemana > 0) {
            if (!alertDiv) {
                alertDiv = document.createElement('div');
                alertDiv.className = 'alert alert-warning p-1 mt-2 small alert-hours-warning';
                container.appendChild(alertDiv);
            }
            alertDiv.innerHTML = `<i class="bi bi-exclamation-triangle"></i> Atención: Esta semana suma <strong>${totalSemana.toFixed(1)}</strong> hrs (Objetivo: ${metaHoras}h).`;
        } else if (alertDiv) {
            alertDiv.remove();
        }
    });
    twActualizarTotal();
}

function calculateDiff(start, end, crossesMidnight) {
    if (!start || !end) return 0;

    const [h1, m1] = start.split(':').map(Number);
    const [h2, m2] = end.split(':').map(Number);

    let d1 = new Date(2000, 0, 1, h1, m1);
    let d2 = new Date(2000, 0, 1, h2, m2);

    if (crossesMidnight || d2 < d1) {
        d2.setDate(d2.getDate() + 1);
    }

    return (d2 - d1) / (1000 * 60 * 60);
}
