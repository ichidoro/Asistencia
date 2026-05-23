/**
 * Módulo de Justificaciones Individuales (Click-to-Justify)
 * Permite gestionar justificaciones directamente desde la matriz de asistencia.
 * 
 * Modos:
 *   - CREATE: Nueva justificación (flujo original)
 *   - EDIT:   Editar justificación existente (pre-carga datos + botón eliminar)
 */

const justIndividualState = {
    modalInstance: null,
    tipos: [],
    editMode: false,          // true = editando, false = creando
    editJustificacionId: null  // ID de la justificación en modo edición
};

// Inicializar el modal al cargar el script o según disponibilidad
function initJustifyModal() {
    const modalEl = document.getElementById('modal-justificacion-individual');
    if (modalEl && !justIndividualState.modalInstance) {
        // ✅ USAR API BOOTSTRAP 5
        justIndividualState.modalInstance = bootstrap.Modal.getOrCreateInstance(modalEl);
    }
}

/**
 * Abre el modal de justificación rápida
 * @param {number} empId ID del empleado
 * @param {string} empNombre Nombre del empleado
 * @param {string} fecha Fecha en formato YYYY-MM-DD
 * @param {object|null} existingJust Justificación existente (modo edición) o null (modo crear)
 */
async function openJustifyModal(empId, empNombre, fecha, existingJust = null) {
    initJustifyModal();

    // Determinar modo
    justIndividualState.editMode = !!existingJust;
    justIndividualState.editJustificacionId = existingJust ? existingJust.id : null;

    // Llenar campos ocultos
    document.getElementById('just-id-empleado').value = empId;

    // Labels visuales
    document.getElementById('just-nombre-empleado').value = empNombre;

    // Mostrar modal usando Bootstrap inmediatamente
    if (justIndividualState.modalInstance) {
        justIndividualState.modalInstance.show();
    }

    // Mostrar indicador de carga en el select
    const select = document.getElementById('just-tipo-id');
    if (select) {
        select.innerHTML = '<option value="">Cargando motivos...</option>';
        select.disabled = true;
    }

    // Cargar tipos de justificación (FORZAR RECARGA para ver cambios recientes)
    await loadJustifyTypes(true);

    const canJustify = typeof AuthService !== 'undefined' && 
        (AuthService.hasPermission('marcaciones.justificar') || AuthService.hasPermission('marcaciones.editar'));

    if (select) {
        select.disabled = !canJustify;
    }

    // Pre-llenar según modo
    if (existingJust) {
        // MODO EDICIÓN: Pre-cargar datos existentes
        document.getElementById('just-fecha-inicio-input').value = existingJust.fecha_inicio;
        document.getElementById('just-fecha-fin-input').value = existingJust.fecha_fin;
        document.getElementById('just-tipo-id').value = existingJust.tipo_id;
        document.getElementById('just-observaciones').value = existingJust.observaciones || '';
    } else {
        // MODO CREAR: Valores por defecto
        document.getElementById('just-fecha-inicio-input').value = fecha;
        document.getElementById('just-fecha-fin-input').value = fecha;
        document.getElementById('just-tipo-id').value = '';
        document.getElementById('just-observaciones').value = '';
    }

    // Habilitar/Deshabilitar otros inputs según permisos
    document.getElementById('just-fecha-inicio-input').disabled = !canJustify;
    document.getElementById('just-fecha-fin-input').disabled = !canJustify;
    document.getElementById('just-observaciones').disabled = !canJustify;

    // Actualizar título y footer según modo
    const titleEl = document.querySelector('#modal-justificacion-individual .modal-header h3');
    if (titleEl) {
        titleEl.textContent = existingJust ? 'Editar Justificación' : 'Justificar Inasistencia';
    }

    // Actualizar footer: agregar botón Eliminar en modo edición
    const footerEl = document.querySelector('#modal-justificacion-individual .modal-footer');
    if (footerEl) {
        if (!canJustify) {
            footerEl.innerHTML = `
                <button type="button" class="btn btn-secondary" onclick="closeModalJustify()">Cerrar</button>
            `;
        } else if (existingJust) {
            footerEl.innerHTML = `
                <button type="button" class="btn btn-danger me-auto" onclick="deleteJustificacionFromModal()">
                    <i class="bi bi-trash"></i> Eliminar
                </button>
                <button type="button" class="btn btn-secondary" onclick="closeModalJustify()">Cancelar</button>
                <button type="submit" class="btn btn-primary" id="btn-just-guardar">Guardar Cambios</button>
            `;
        } else {
            footerEl.innerHTML = `
                <button type="button" class="btn btn-secondary" onclick="closeModalJustify()">Cancelar</button>
                <button type="submit" class="btn btn-primary" id="btn-just-guardar">Guardar</button>
            `;
        }
    }
}

function closeModalJustify() {
    if (justIndividualState.modalInstance) {
        justIndividualState.modalInstance.hide();
        document.getElementById('form-justificar-individual').reset();
        justIndividualState.editMode = false;
        justIndividualState.editJustificacionId = null;
    }
}

/**
 * Carga los tipos de justificación activos desde el servidor
 * @param {boolean} force Forzar recarga desde el servidor (ignorar caché)
 */
async function loadJustifyTypes(force = false) {
    try {
        if (!force && justIndividualState.tipos.length > 0) return; // Cache simple

        const resp = await fetch('/api/configuracion/justificaciones/tipos/');
        const tipos = await resp.json();

        // --- FILTRO CRÍTICO: Solo mostrar tipos que NO sean por horas ---
        const tiposDiaCompleto = tipos.filter(t => !t.es_por_horas);

        const select = document.getElementById('just-tipo-id');
        if (select) {
            select.innerHTML = '<option value="">-- Seleccionar Motivo --</option>' +
                tiposDiaCompleto.map(t => `<option value="${t.id}">${t.nombre}</option>`).join('');

            // Agregar evento para auto-calcular fecha_fin
            select.onchange = autoCalcularFechaFin;
        }
        
        const fechaInicioInput = document.getElementById('just-fecha-inicio-input');
        if (fechaInicioInput) {
            fechaInicioInput.onchange = autoCalcularFechaFin;
        }

        justIndividualState.tipos = tipos;
    } catch (e) {
        console.error("Error cargando tipos de justificación:", e);
        showToast("No se pudieron cargar los motivos", "error");
    }
}

async function autoCalcularFechaFin() {
    const empId = document.getElementById('just-id-empleado').value;
    const tipoId = document.getElementById('just-tipo-id').value;
    const fechaInicio = document.getElementById('just-fecha-inicio-input').value;
    
    if (!empId || !tipoId || !fechaInicio) return;
    
    // Check if the selected tipo has min_dias > 0
    const tipo = justIndividualState.tipos.find(t => t.id == tipoId);
    if (!tipo || (!tipo.min_dias && !tipo.max_dias)) return;

    try {
        const resp = await fetch(`/api/configuracion/justificaciones/calcular_fin/?empleado_id=${empId}&tipo_id=${tipoId}&fecha_inicio=${fechaInicio}`);
        if (resp.ok) {
            const data = await resp.json();
            document.getElementById('just-fecha-fin-input').value = data.fecha_fin;
        }
    } catch (e) {
        console.error("Error calculando fecha fin:", e);
    }
}

/**
 * Guarda la justificación (crear nueva o actualizar existente)
 */
async function saveJustificacionIndividual() {
    const empId = document.getElementById('just-id-empleado').value;
    const tipoId = document.getElementById('just-tipo-id').value;
    const obs = document.getElementById('just-observaciones').value;

    if (!tipoId) {
        showToast("Debe seleccionar un motivo", "warning");
        return;
    }

    // Leer fechas desde los inputs visuales
    const fechaInicio = document.getElementById('just-fecha-inicio-input').value;
    const fechaFin = document.getElementById('just-fecha-fin-input').value;

    if (!fechaInicio || !fechaFin) {
        showToast("Fechas inválidas", "warning");
        return;
    }

    if (fechaFin < fechaInicio) {
        showToast("La fecha de término no puede ser anterior al inicio", "warning");
        return;
    }

    const payload = {
        empleado_id: parseInt(empId),
        tipo_id: parseInt(tipoId),
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
        observaciones: obs
    };

    // Spinner visual en botón Guardar para evitar doble-click
    const btnGuardar = document.getElementById('btn-just-guardar');
    const btnTextoOriginal = btnGuardar ? btnGuardar.innerHTML : '';
    if (btnGuardar) {
        btnGuardar.disabled = true;
        btnGuardar.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span>Guardando...';
    }

    try {
        let resp;
        let successMsg;

        if (justIndividualState.editMode && justIndividualState.editJustificacionId) {
            // MODO EDICIÓN: PUT
            resp = await fetch(`/api/configuracion/justificaciones/${justIndividualState.editJustificacionId}/`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            successMsg = "Justificación actualizada correctamente";
        } else {
            // MODO CREAR: POST
            resp = await fetch('/api/configuracion/justificaciones/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            successMsg = "Justificación guardada correctamente";
        }

        if (resp.ok) {
            const data = await resp.json();
            showToast(successMsg, "success");
            closeModalJustify();
            // Polling basado en job_id: espera al recálculo completo antes de refrescar
            _pollJustificacionJob(data.job_id);
        } else {
            const error = await resp.json();
            showToast(`Error: ${error.detail || 'No se pudo guardar'}`, "error");
            // Restaurar botón en caso de error
            if (btnGuardar) { btnGuardar.disabled = false; btnGuardar.innerHTML = btnTextoOriginal; }
        }
    } catch (e) {
        console.error("Error guardando justificación:", e);
        showToast("Error de conexión", "error");
        // Restaurar botón en caso de error de conexión
        if (btnGuardar) { btnGuardar.disabled = false; btnGuardar.innerHTML = btnTextoOriginal; }
    }
}

/**
 * Polling ligero: consulta /api/asistencia/jobs/{jobId}/ cada 2s
 * hasta que el recálculo termine (status='done'), luego refresca la grilla.
 * Safety: máximo 60s de polling.
 */
function _pollJustificacionJob(jobId) {
    if (!jobId || typeof window.loadMarcacionesData !== 'function') {
        // Fallback si no hay job_id: refresh a los 5s
        if (typeof window.loadMarcacionesData === 'function') {
            setTimeout(() => window.loadMarcacionesData(), 5000);
        }
        return;
    }

    const POLL_INTERVAL = 1000;   // 1 segundo (respuesta rápida)
    const MAX_POLLS = 60;         // máximo 60 segundos
    let pollCount = 0;

    // SIN refresh prematuro: esperamos al polling para evitar grilla parcial
    const timer = setInterval(async () => {
        pollCount++;
        try {
            const r = await fetch(`/api/asistencia/jobs/${jobId}/`);
            if (r.ok) {
                const job = await r.json();
                if (job.status === 'done' || job.status === 'error') {
                    clearInterval(timer);
                    // Refresh inmediato: el job terminó, los datos ya están en DB
                    window.loadMarcacionesData();
                    if (job.status === 'error') {
                        showToast("⚠️ Error en recálculo de asistencia", "warning");
                    }
                    return;
                }
            }
        } catch (_) { /* red caída — sigue intentando */ }

        if (pollCount >= MAX_POLLS) {
            clearInterval(timer);
            window.loadMarcacionesData(); // refresh final de seguridad
        }
    }, POLL_INTERVAL);
}

/**
 * Elimina la justificación actualmente en edición (llamado desde el modal)
 */
async function deleteJustificacionFromModal() {
    if (!justIndividualState.editJustificacionId) return;

    const confirmDelete = confirm("¿Está seguro que desea ELIMINAR esta justificación?\n\nLa asistencia se recalculará automáticamente.");
    if (!confirmDelete) return;

    try {
        const resp = await fetch(`/api/configuracion/justificaciones/${justIndividualState.editJustificacionId}/`, {
            method: 'DELETE'
        });

        if (resp.ok) {
            const data = await resp.json();
            showToast("Justificación eliminada correctamente", "success");
            closeModalJustify();
            // Polling basado en job_id: espera al recálculo completo
            _pollJustificacionJob(data.job_id);
        } else {
            const error = await resp.json();
            showToast(`Error: ${error.detail || 'No se pudo eliminar'}`, "error");
        }
    } catch (e) {
        console.error("Error eliminando justificación:", e);
        showToast("Error de conexión", "error");
    }
}
