/**
 * marcaciones_manuales.js
 * Módulo para gestionar correcciones manuales y validaciones de jornadas especiales.
 */

const marcacionesManualesState = {
    manualModal: null,
    manualInstance: null,
    validationModal: null,
    validationInstance: null,
    decisionModal: null,
    decisionInstance: null,
    currentEmpId: null,
    currentDate: null
};

// Inicialización de Modales
function initMarcacionesManuales() {
    console.log("Inicializando Modales Manuales...");
    // Modal Manual
    const manualModalEl = document.getElementById('modal-marcacion-manual');
    if (manualModalEl) {
        marcacionesManualesState.manualModal = manualModalEl;
        marcacionesManualesState.manualInstance = bootstrap.Modal.getOrCreateInstance(manualModalEl);
    } else {
        console.error("No encontrado: modal-marcacion-manual");
    }

    // Modal Validación
    const valModalEl = document.getElementById('modal-validacion-jornada');
    if (valModalEl) {
        marcacionesManualesState.validationModal = valModalEl;
        marcacionesManualesState.validationInstance = bootstrap.Modal.getOrCreateInstance(valModalEl);
    } else {
        console.error("No encontrado: modal-validacion-jornada");
    }

    // Modal Decisión
    const decModalEl = document.getElementById('modal-decision-asistencia');
    if (decModalEl) {
        marcacionesManualesState.decisionModal = decModalEl;
        marcacionesManualesState.decisionInstance = bootstrap.Modal.getOrCreateInstance(decModalEl);
    }
}

/**
 * Abre el modal de decisión (Justificación vs Manual)
 */
async function openAsistenciaActionModal(empId, dateStr, empNombre, horaEntrada = null, horaSalida = null) {
    if (typeof checkAuditoriaBloqueo === 'function') {
        const isBlocked = await checkAuditoriaBloqueo();
        if (isBlocked) {
            console.warn("⚠️ ACCESO BLOQUEADO: No se permite la edición.");
            return;
        }
    }

    if (!marcacionesManualesState.decisionModal) initMarcacionesManuales();
    if (!marcacionesManualesState.decisionModal) return;

    marcacionesManualesState.currentEmpId = empId;
    marcacionesManualesState.currentDate = dateStr;
    marcacionesManualesState.currentEmpNombre = empNombre;

    // Guardar horas reales para uso posterior en modal manual
    // Robusto: Asegurar que 'null' (string) se convierta a null real
    marcacionesManualesState.currentEntrada = (horaEntrada === 'null' || !horaEntrada || horaEntrada === '--:--') ? null : horaEntrada;
    marcacionesManualesState.currentSalida = (horaSalida === 'null' || !horaSalida || horaSalida === '--:--') ? null : horaSalida;

    document.getElementById('decision-emp-nombre').innerText = empNombre;
    document.getElementById('decision-fecha').innerText = window.formatFechaDDMMYYYY(dateStr);

    // Set avatar initial from employee name
    const avatarEl = document.getElementById('decision-avatar-initial');
    if (avatarEl && empNombre) {
        const parts = empNombre.trim().split(/\s+/);
        avatarEl.textContent = parts.length >= 2 ? (parts[0][0] + parts[1][0]).toUpperCase() : empNombre[0].toUpperCase();
    }

    // --- NUEVO: CAMBIAR TEXTO BOTÓN SI HAY PERMISO ACTIVO ---
    const btnPermiso = document.getElementById('btn-permiso-dynamic');
    if (btnPermiso) {
        const titleEl = btnPermiso.querySelector('.title-permiso');
        const subEl = btnPermiso.querySelector('.sub-permiso');
        const iconEl = btnPermiso.querySelector('i');

        const empMatrix = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
        const asist = empMatrix ? empMatrix[dateStr] : null;

        if (asist && asist.permiso_activo) {
            if (titleEl) titleEl.innerText = "Registrar Regreso";
            if (subEl) subEl.innerText = "El empleado tiene una salida abierta";
            if (iconEl) iconEl.className = "bi bi-door-open mb-1 fs-4";
            btnPermiso.classList.remove('btn-outline-warning');
            btnPermiso.classList.add('btn-warning');
        } else {
            if (titleEl) titleEl.innerText = "Registrar Permiso / Salida";
            if (subEl) subEl.innerText = "Trámites personales, Retiro temprano, Salidas parciales";
            if (iconEl) iconEl.className = "bi bi-clock-history mb-1 fs-4";
            btnPermiso.classList.add('btn-outline-warning');
            btnPermiso.classList.remove('btn-warning');
        }
    }

    // --- NUEVO: MOSTRAR/OCULTAR BOTÓN EDITAR JUSTIFICACIÓN ---
    const btnEditJust = document.getElementById('btn-edit-justificacion');
    if (btnEditJust) {
        const empMatrixJ = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
        const asistJ = empMatrixJ ? empMatrixJ[dateStr] : null;

        // Detectar si tiene justificación activa (estado contiene nombre de justificación como VAC, LIC, etc.)
        const estadosJustificados = ['VACACIONES', 'LICENCIA', 'LIC_COMUN', 'LIC_MUTUAL', 'CUMPLEAÑOS', 'DUELO', 'PERMISO', 'NO NACIDO', 'DEFUNCION'];
        const tieneJustificacion = asistJ && (
            (asistJ.justificacion_id) ||
            (asistJ.estado && estadosJustificados.some(ej => asistJ.estado.toUpperCase().includes(ej))) ||
            (asistJ.nomenclatura && asistJ.nomenclatura.trim() !== '') ||
            (asistJ.observaciones && asistJ.observaciones.toUpperCase().includes('JUSTIFICACI'))
        );

        if (tieneJustificacion) {
            btnEditJust.classList.remove('d-none');
            // Guardar el ID de justificación para uso posterior
            marcacionesManualesState.currentJustificacionId = asistJ.justificacion_id || null;
        } else {
            btnEditJust.classList.add('d-none');
            marcacionesManualesState.currentJustificacionId = null;
        }
    }

    // --- NUEVO: MOSTRAR/OCULTAR BOTONES DE REGLA DE NEGOCIO (DESPACHADOR INTELIGENTE) ---
    const btnGestionarHE = document.getElementById('btn-gestionar-he');
    const btnValidarJornada = document.getElementById('btn-validar-jornada');
    
    if (btnGestionarHE) {
        const empMatrixJ = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
        const asistJ = empMatrixJ ? empMatrixJ[dateStr] : null;
        if (asistJ && (asistJ.estado === 'EXTRA' || asistJ.minutos_extra_bruto > 0)) {
            btnGestionarHE.classList.remove('d-none');
        } else {
            btnGestionarHE.classList.add('d-none');
        }
    }

    const btnCompensarHE = document.getElementById('btn-compensar-he-action');
    if (btnCompensarHE) {
        const empMatrixJ = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
        const asistJ = empMatrixJ ? empMatrixJ[dateStr] : null;
        const hasPerm = typeof AuthService !== 'undefined' ? AuthService.hasPermission("marcaciones.compensar") : true;
        if (asistJ && (asistJ.estado === 'INASISTENCIA' || asistJ.estado === 'FALTA') && hasPerm) {
            btnCompensarHE.classList.remove('d-none');
        } else {
            btnCompensarHE.classList.add('d-none');
        }
    }


    if (btnValidarJornada) {
        const empMatrixJ = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
        const asistJ = empMatrixJ ? empMatrixJ[dateStr] : null;
        // REGLA: mostrar cuando el estado es JORNADA_ESPECIAL (ambas marcas completas)
        // O cuando hay una jornada adicional pendiente o rechazada que el supervisor pueda gestionar.
        const tieneJornadaAdicionalPendienteRechazada = asistJ && asistJ.jornada_adicional &&
            (asistJ.jornada_adicional.estado === 'PENDIENTE' || asistJ.jornada_adicional.estado === 'RECHAZADA');
            
        if (asistJ && (asistJ.estado === 'JORNADA_ESPECIAL' || tieneJornadaAdicionalPendienteRechazada)) {
            btnValidarJornada.classList.remove('d-none');
        } else {
            btnValidarJornada.classList.add('d-none');
        }
    }

    const btnRevertirHE = document.getElementById('btn-revertir-he');
    if (btnRevertirHE) {
        const empMatrixJ = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
        const asistJ = empMatrixJ ? empMatrixJ[dateStr] : null;
        // Solo mostrar si el estado es EXTRA y es producto de una validación de jornada especial.
        // O si tiene una jornada adicional aprobada (estado EXTRA)
        const tieneJornadaAdicionalAprobada = asistJ && asistJ.jornada_adicional && asistJ.jornada_adicional.estado === 'EXTRA';
        
        if (asistJ && (asistJ.estado === 'EXTRA' || tieneJornadaAdicionalAprobada)) {
            btnRevertirHE.classList.remove('d-none');
        } else {
            btnRevertirHE.classList.add('d-none');
        }
    }

    // --- NUEVO: MOSTRAR/OCULTAR BOTÓN REGISTRAR VIAJE LARGO ---
    const btnViajeLargo = document.getElementById('btn-viaje-largo');
    if (btnViajeLargo) {
        const empMatrixJ = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
        const asistJ = empMatrixJ ? empMatrixJ[dateStr] : null;
        
        // Obtener info del turno del empleado
        const empInfo = stateMarcacionesApp.data && stateMarcacionesApp.data.empleados ? stateMarcacionesApp.data.empleados.find(e => e.id == empId) : null;
        const isBolsa = (empInfo && (empInfo.tipo_programacion === 'FLEXIBLE_BOLSA' || (empInfo.area_nombre && empInfo.area_nombre.toUpperCase().includes('LOGISTICA'))));
        
        // REGLA: Mostrar solo si es Bolsa Flexible / Logística Y la celda tiene ANOMALIA o marcación registrada
        const tieneMarcaOAnomalia = asistJ && (asistJ.estado === 'ANOMALIA' || asistJ.hora_entrada_real || asistJ.hora_salida_real || (asistJ.marcas_consumidas_ids && asistJ.marcas_consumidas_ids !== '[]'));

        if (isBolsa && tieneMarcaOAnomalia) {
            btnViajeLargo.classList.remove('d-none');
        } else {
            btnViajeLargo.classList.add('d-none');
        }
    }

    // --- MOSTRAR/OCULTAR BOTÓN REASIGNAR / MOVER TURNO ---
    const btnReasignarTurno = document.getElementById('btn-reasignar-turno');
    if (btnReasignarTurno) {
        const empInfo = stateMarcacionesApp.data && stateMarcacionesApp.data.empleados ? stateMarcacionesApp.data.empleados.find(e => e.id == empId) : null;
        const isNotBolsa = (!empInfo || empInfo.tipo_programacion !== 'FLEXIBLE_BOLSA');
        
        // Mostrar siempre para empleados con turno agendado (no bolsa flexible)
        if (isNotBolsa) {
            btnReasignarTurno.classList.remove('d-none');
        } else {
            btnReasignarTurno.classList.add('d-none');
        }
    }

    if (marcacionesManualesState.decisionInstance) {
        marcacionesManualesState.decisionInstance.show();
    }
}


function closeAsistenciaActionModal() {
    if (marcacionesManualesState.decisionInstance) {
        marcacionesManualesState.decisionInstance.hide();
    }
}

// --- NUEVO: Funciones para el Despachador Inteligente ---
function proceedToHoraExtra() {
    closeAsistenciaActionModal();
    if (typeof openHoraExtraModal === 'function') {
        openHoraExtraModal(
            marcacionesManualesState.currentEmpId,
            marcacionesManualesState.currentDate,
            marcacionesManualesState.currentEmpNombre
        );
    } else {
        console.error("Función openHoraExtraModal no encontrada.");
    }
}

function proceedToCompensateHE() {
    closeAsistenciaActionModal();
    if (typeof abrirModalCompensacionHE === 'function') {
        abrirModalCompensacionHE(
            marcacionesManualesState.currentEmpId,
            marcacionesManualesState.currentDate
        );
    } else {
        console.error("Función abrirModalCompensacionHE no encontrada.");
    }
}
window.proceedToCompensateHE = proceedToCompensateHE;


function proceedToValidation() {
    closeAsistenciaActionModal();
    if (typeof openValidationModal === 'function') {
        openValidationModal(
            marcacionesManualesState.currentEmpId,
            marcacionesManualesState.currentDate,
            marcacionesManualesState.currentEmpNombre
        );
    } else {
        console.error("Función openValidationModal no encontrada.");
    }
}

// --- NUEVO: REASIGNACIÓN MANUAL DE TURNO NOCTURNO A INASISTENCIA ---
let selectedFechaDestinoReasignar = null;

async function proceedToReasignarTurno() {
    closeAsistenciaActionModal();
    const empId = marcacionesManualesState.currentEmpId;
    const dateStr = marcacionesManualesState.currentDate;
    
    // Set labels
    const lblOrigen = document.getElementById('reasignar-origen-lbl');
    if (lblOrigen) lblOrigen.textContent = dateStr;
    const summaryOrigen = document.getElementById('summary-origen-date');
    if (summaryOrigen) summaryOrigen.textContent = dateStr;

    // Reset list and button
    const container = document.getElementById('container-inasistencias-list');
    const resBox = document.getElementById('reasignar-resumen-box');
    const btnConfirm = document.getElementById('btn-confirmar-reasignacion');
    if (resBox) resBox.classList.add('d-none');
    if (btnConfirm) btnConfirm.disabled = true;
    selectedFechaDestinoReasignar = null;

    if (container) {
        container.innerHTML = '<div class="text-center py-4 text-muted"><span class="spinner-border spinner-border-sm me-2"></span> Buscando inasistencias disponibles...</div>';
    }

    const modalEl = document.getElementById('modalSelectorInasistencias');
    let modalInst = bootstrap.Modal.getInstance(modalEl);
    if (!modalInst) {
        modalInst = new bootstrap.Modal(modalEl);
    }
    modalInst.show();

    // Fetch inasistencias limpias
    try {
        const resp = await fetch(`/api/asistencia/inasistencias-disponibles/${empId}/?fecha_origen=${dateStr}`);
        if (!resp.ok) throw new Error("Error consultando inasistencias.");
        const data = await resp.json();
        
        if (!data.inasistencias || data.inasistencias.length === 0) {
            container.innerHTML = `
                <div class="p-3 text-center text-muted">
                    <i class="bi bi-exclamation-triangle text-warning fs-4 d-block mb-1"></i>
                    No se encontraron fechas de Inasistencia limpia disponibles en este período para el empleado.
                </div>
            `;
            return;
        }

        let html = '';
        data.inasistencias.forEach(item => {
            html += `
                <button type="button" class="list-group-item list-group-item-action d-flex align-items-center justify-content-between p-3 inasistencia-opt-item"
                    onclick="selectFechaDestino('${item.fecha}', this)">
                    <div>
                        <div class="fw-bold text-dark" style="font-size:0.88rem;"><i class="bi bi-calendar-event me-2 text-primary"></i> ${item.fecha}</div>
                        <div class="small text-muted" style="font-size:0.75rem;">Estado: <span class="badge bg-danger-subtle text-danger">${item.estado}</span> ${item.observaciones ? '(' + item.observaciones + ')' : ''}</div>
                    </div>
                    <i class="bi bi-circle text-secondary radio-icon" style="font-size:1.1rem;"></i>
                </button>
            `;
        });
        container.innerHTML = html;
    } catch (e) {
        console.error(e);
        container.innerHTML = `<div class="p-3 text-center text-danger">Error al cargar inasistencias: ${e.message}</div>`;
    }
}

function selectFechaDestino(fecha, element) {
    selectedFechaDestinoReasignar = fecha;
    const btnConfirm = document.getElementById('btn-confirmar-reasignacion');
    if (btnConfirm) btnConfirm.disabled = false;

    const summaryTarget = document.getElementById('summary-target-date');
    if (summaryTarget) summaryTarget.textContent = fecha;

    const resBox = document.getElementById('reasignar-resumen-box');
    if (resBox) resBox.classList.remove('d-none');

    // Highlight selected item
    document.querySelectorAll('.inasistencia-opt-item').forEach(el => {
        el.classList.remove('active', 'border-primary');
        const icon = el.querySelector('.radio-icon');
        if (icon) {
            icon.className = 'bi bi-circle text-secondary radio-icon';
        }
    });

    if (element) {
        element.classList.add('active', 'border-primary');
        const icon = element.querySelector('.radio-icon');
        if (icon) {
            icon.className = 'bi bi-check-circle-fill text-primary radio-icon';
        }
    }
}

async function ejecutarReasignacionTurno() {
    if (!selectedFechaDestinoReasignar) return;

    const empId = marcacionesManualesState.currentEmpId;
    const fechaOrigen = marcacionesManualesState.currentDate;

    const btnConfirm = document.getElementById('btn-confirmar-reasignacion');
    if (btnConfirm) {
        btnConfirm.disabled = true;
        btnConfirm.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Procesando...';
    }

    try {
        const resp = await fetch('/api/asistencia/reasignar-turno/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                empleado_id: parseInt(empId),
                fecha_origen: fechaOrigen,
                fecha_destino: selectedFechaDestinoReasignar,
                motivo: 'Reasignación manual de turno por Supervisor'
            })
        });

        const resData = await resp.json();
        if (!resp.ok) {
            throw new Error(resData.detail || "Error al reasignar el turno.");
        }

        // Success
        const modalEl = document.getElementById('modalSelectorInasistencias');
        const modalInst = bootstrap.Modal.getInstance(modalEl);
        if (modalInst) modalInst.hide();

        if (typeof showToast === 'function') {
            showToast(resData.message || "Turno reasignado exitosamente.", "success");
        } else {
            alert(resData.message || "Turno reasignado exitosamente.");
        }

        // Refresh UI
        if (typeof window.reloadSingleEmployeeRow === 'function') {
            window.reloadSingleEmployeeRow(empId);
        } else if (typeof loadMarcacionesData === 'function') {
            loadMarcacionesData();
        }
    } catch (err) {
        console.error(err);
        alert(`Error: ${err.message}`);
    } finally {
        if (btnConfirm) {
            btnConfirm.disabled = false;
            btnConfirm.innerHTML = '<i class="bi bi-send-check-fill me-1"></i> Confirmar Reasignación';
        }
    }
}
window.proceedToReasignarTurno = proceedToReasignarTurno;
window.selectFechaDestino = selectFechaDestino;
window.ejecutarReasignacionTurno = ejecutarReasignacionTurno;



async function proceedToRevertExtra() {
    closeAsistenciaActionModal();
    
    if (!confirm(`¿Está seguro que desea revertir esta jornada a 'Especial'?\n\nEsto eliminará la autorización de horas extras y restaurará el estado original de la validación.`)) {
        return;
    }

    const empId = marcacionesManualesState.currentEmpId;
    const dateStr = marcacionesManualesState.currentDate;

    const payload = {
        empleado_id: parseInt(empId),
        fecha: dateStr,
        accion: 'REVERTIR',
        last_updated_at: (function () {
            const empMatrix = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
            const asist = empMatrix ? empMatrix[dateStr] : null;
            return asist ? asist.updated_at : null;
        })()
    };

    try {
        const resp = await fetch('/api/asistencia/jornada/validar/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (resp.ok) {
            const result = await resp.json();
            if (typeof showToast === 'function') {
                showToast("Jornada revertida a Especial exitosamente", "success");
            } else {
                alert("Jornada revertida a Especial exitosamente");
            }
            if (typeof window.reloadSingleEmployeeRow === 'function') window.reloadSingleEmployeeRow(empId);
            else if (typeof loadMarcacionesData === 'function') loadMarcacionesData();
        } else {
            const result = await resp.json();
            if (resp.status === 409) {
                alert(`Conflicto de Concurrencia: ${result.detail}`);
                if (typeof window.reloadSingleEmployeeRow === 'function') window.reloadSingleEmployeeRow(empId);
                else if (typeof loadMarcacionesData === 'function') loadMarcacionesData();
            } else {
                alert(`Error: ${result.detail || 'Fallo al revertir'}`);
            }
        }
    } catch (e) {
        console.error("Error al revertir jornada:", e);
        alert("Error de conexión");
    }
}


function proceedToJustify() {
    closeAsistenciaActionModal();
    // Llamar a función de justificaciones_individuales.js
    if (typeof openJustifyModal === 'function') {
        openJustifyModal(
            marcacionesManualesState.currentEmpId,
            marcacionesManualesState.currentEmpNombre,
            marcacionesManualesState.currentDate
        );
    } else {
        console.error("openJustifyModal no definida");
    }
}

async function proceedToEditJustify() {
    closeAsistenciaActionModal();
    const empId = marcacionesManualesState.currentEmpId;
    const dateStr = marcacionesManualesState.currentDate;
    const empNombre = marcacionesManualesState.currentEmpNombre;

    // Mostrar indicador global de carga mientras buscamos
    const loadingDiv = document.createElement('div');
    loadingDiv.id = 'temp-loading-overlay';
    loadingDiv.style.position = 'fixed';
    loadingDiv.style.top = '0';
    loadingDiv.style.left = '0';
    loadingDiv.style.width = '100vw';
    loadingDiv.style.height = '100vh';
    loadingDiv.style.backgroundColor = 'rgba(0,0,0,0.5)';
    loadingDiv.style.zIndex = '9999';
    loadingDiv.style.display = 'flex';
    loadingDiv.style.justifyContent = 'center';
    loadingDiv.style.alignItems = 'center';
    loadingDiv.innerHTML = '<div class="spinner-border text-light" role="status"><span class="visually-hidden">Cargando...</span></div>';
    document.body.appendChild(loadingDiv);

    try {
        // Buscar la justificación activa para este empleado/fecha
        const resp = await fetch(`/api/configuracion/justificaciones/empleado/${empId}/`);
        if (!resp.ok) throw new Error("No se pudieron cargar las justificaciones");
        const justificaciones = await resp.json();

        // Encontrar la justificación que cubre esta fecha
        const justificacion = justificaciones.find(j => {
            return dateStr >= j.fecha_inicio && dateStr <= j.fecha_fin;
        });

        document.body.removeChild(loadingDiv);

        if (justificacion) {
            // Abrir modal en modo edición con datos pre-cargados
            if (typeof openJustifyModal === 'function') {
                openJustifyModal(empId, empNombre, dateStr, justificacion);
            }
        } else {
            if (typeof showToast === 'function') {
                showToast("No se encontró una justificación activa para esta fecha", "warning");
            } else {
                alert("No se encontró una justificación activa para esta fecha");
            }
        }
    } catch (e) {
        if (document.body.contains(loadingDiv)) document.body.removeChild(loadingDiv);
        console.error("Error buscando justificación:", e);
        alert("Error al buscar la justificación existente");
    }
}

function proceedToBulkFill() {
    closeAsistenciaActionModal();
    // Open Bulk Fill Modal with stored context
    if (marcacionesManualesState.currentEmpId && marcacionesManualesState.currentDate) {

        // Get Employee Name from the Decision Modal (which is already populated)
        const empName = document.getElementById('decision-emp-nombre').innerText;

        // Open Modal with specific Employee context
        openBulkFillModal(
            marcacionesManualesState.currentEmpId,
            empName,
            marcacionesManualesState.currentDate
        );
    }
}

function proceedToManualEntry() {
    closeAsistenciaActionModal();
    // Abrir modal manual con título adaptado y horas pre-cargadas
    openManualEntryModal(
        marcacionesManualesState.currentEmpId,
        marcacionesManualesState.currentDate,
        marcacionesManualesState.currentEmpNombre,
        "Ingreso Manual",
        marcacionesManualesState.currentEntrada,
        marcacionesManualesState.currentSalida
    );
}

function proceedToPermission() {
    closeAsistenciaActionModal();
    openPermissionModal(
        marcacionesManualesState.currentEmpId,
        marcacionesManualesState.currentEmpNombre,
        marcacionesManualesState.currentDate
    );
}

/**
 * Abre el modal para corrección manual (Entrada/Salida)
 */
function openManualEntryModal(empId, dateStr, empNombre, customTitle = null, horaEntrada = null, horaSalida = null) {
    if (!marcacionesManualesState.manualModal) initMarcacionesManuales();

    if (!marcacionesManualesState.manualModal) {
        console.error("Modal NO encontrado. Asegurate de incluir el HTML en index.html");
        return;
    }

    marcacionesManualesState.currentEmpId = empId;
    marcacionesManualesState.currentDate = dateStr;

    // Set Title
    const titleEl = marcacionesManualesState.manualModal.querySelector('.modal-title');
    if (titleEl) {
        titleEl.innerText = customTitle || "Corregir Anomalía de Asistencia";
    }

    // Reset Form
    const lblFecha = document.getElementById('manual-fecha-display');
    if (lblFecha) {
        lblFecha.value = window.formatFechaDDMMYYYY(dateStr);
    }

    const lblEmp = document.getElementById('manual-empleado-display');
    if (lblEmp) {
        lblEmp.value = empNombre;
    }

    // Manejo de Inputs de Hora
    const inputEntrada = document.getElementById('manual-hora-entrada');
    const inputSalida = document.getElementById('manual-hora-salida');
    const divTramos = document.getElementById('divTramosBolsa');
    const inputCond = document.getElementById('manual-minutos-conduccion');
    const inputEsp = document.getElementById('manual-minutos-espera');
    const btnUnlock = document.getElementById('btn-unlock-manual');

    // Elementos de visualización adicionales
    const lblArea = document.getElementById('manual-area-display');
    const lblCargo = document.getElementById('manual-cargo-display');
    const lblTurno = document.getElementById('manual-turno-display');

    // Resetear estados
    inputEntrada.value = '';
    inputEntrada.disabled = false;
    inputSalida.value = '';
    inputSalida.disabled = false;
    if (inputCond) inputCond.value = '';
    if (inputEsp) inputEsp.value = '';
    if (btnUnlock) btnUnlock.style.display = 'none';

    if (lblArea) lblArea.value = '';
    if (lblCargo) lblCargo.value = '';
    if (lblTurno) lblTurno.value = '';

    // Lógica Bolsa Flexible
    const empMatrix = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
    const asist = empMatrix ? empMatrix[dateStr] : null;
    const info = empMatrix ? empMatrix.info : null;

    if (info) {
        if (lblArea) lblArea.value = info.area || '';
        if (lblCargo) lblCargo.value = info.cargo || '';
        if (lblTurno) lblTurno.value = info.nombre_turno || info.turno || (asist ? asist.turno_nombre : '') || '';
    } else if (stateMarcacionesApp.data && stateMarcacionesApp.data.empleados) {
        const eData = stateMarcacionesApp.data.empleados.find(e => String(e.id) === String(empId));
        if (eData) {
            if (lblArea) lblArea.value = eData.area || '';
            if (lblCargo) lblCargo.value = eData.cargo || '';
            if (lblTurno) lblTurno.value = eData.nombre_turno || eData.turno || (asist ? asist.turno_nombre : '') || '';
        }
    }

    marcacionesManualesState.isBolsaFija = (asist && asist.tipo_programacion === 'FLEXIBLE_BOLSA');

    if (divTramos) {
        divTramos.style.display = marcacionesManualesState.isBolsaFija ? 'flex' : 'none';
        if (marcacionesManualesState.isBolsaFija && asist) {
            if (inputCond && asist.minutos_conduccion_b !== undefined && asist.minutos_conduccion_b !== null) inputCond.value = asist.minutos_conduccion_b;
            if (inputEsp && asist.minutos_espera_b !== undefined && asist.minutos_espera_b !== null) inputEsp.value = asist.minutos_espera_b;
        }
    }

    // Lógica Inteligente : Bloquear si ya existe
    const isValidTime = (t) => t && typeof t === 'string' && t.includes(':') && t !== 'null' && t !== '--:--';

    let hasLockedMarks = false;
    let marcaHuerfanaMsj = '';
    
    if (isValidTime(horaEntrada)) {
        inputEntrada.value = horaEntrada;
        inputEntrada.disabled = true;
        hasLockedMarks = true;
    } else if (asist && isValidTime(asist.hora_entrada_teorica)) {
        // Pre-fill theoretical time if real is missing
        inputEntrada.value = asist.hora_entrada_teorica;
    }

    if (isValidTime(horaSalida)) {
        inputSalida.value = horaSalida;
        inputSalida.disabled = true;
        hasLockedMarks = true;
    } else if (asist && isValidTime(asist.hora_salida_teorica)) {
        // Pre-fill theoretical time if real is missing
        inputSalida.value = asist.hora_salida_teorica;
    }

    // --- NUEVO: Alerta visual de marca huérfana ---
    const alertDiv = document.getElementById('manual-alert-huerfana') || (() => {
        const div = document.createElement('div');
        div.id = 'manual-alert-huerfana';
        div.className = 'alert alert-warning py-2 mb-3 mt-2';
        div.style.fontSize = '0.85rem';
        // Insertar después del input de fecha
        const containerInfo = lblFecha ? lblFecha.closest('.row') : null;
        if (containerInfo) {
            containerInfo.insertAdjacentElement('afterend', div);
        }
        return div;
    })();

    if (hasLockedMarks && (!isValidTime(horaEntrada) || !isValidTime(horaSalida))) {
        if (isValidTime(horaEntrada)) {
            marcaHuerfanaMsj = `<strong><i class="bi bi-info-circle-fill"></i> Marca huérfana de ENTRADA detectada a las ${horaEntrada}.</strong> Por favor, ingrese la hora de SALIDA manual.`;
        } else if (isValidTime(horaSalida)) {
            marcaHuerfanaMsj = `<strong><i class="bi bi-info-circle-fill"></i> Marca huérfana de SALIDA detectada a las ${horaSalida}.</strong> Por favor, ingrese la hora de ENTRADA manual.`;
        }
        alertDiv.innerHTML = marcaHuerfanaMsj;
        alertDiv.style.display = 'block';
    } else {
        alertDiv.style.display = 'none';
    }

    // Mostrar botón de desbloqueo solo si hay marcas bloqueadas
    if (btnUnlock && hasLockedMarks) {
        btnUnlock.style.display = 'flex';
    }

    // Auto-focus al primer campo libre
    setTimeout(() => {
        if (!inputEntrada.disabled) inputEntrada.focus();
        else if (!inputSalida.disabled) inputSalida.focus();
    }, 100);

    if (marcacionesManualesState.manualInstance) {
        marcacionesManualesState.manualInstance.show();
    }
}

function closeManualEntryModal() {
    if (marcacionesManualesState.manualInstance) {
        marcacionesManualesState.manualInstance.hide();
        // Reset inputs
        const inputEntrada = document.getElementById('manual-hora-entrada');
        const inputSalida = document.getElementById('manual-hora-salida');
        if (inputEntrada) inputEntrada.value = '';
        if (inputSalida) inputSalida.value = '';
        document.getElementById('manual-observaciones').value = '';
    }
}

/**
 * Permite desbloquear los campos de hora entrada/salida para sobrescribir una marca biométrica.
 */
function unlockManualMarks() {
    const inputEntrada = document.getElementById('manual-hora-entrada');
    const inputSalida = document.getElementById('manual-hora-salida');

    if (inputEntrada && inputEntrada.disabled) {
        inputEntrada.disabled = false;
        inputEntrada.classList.add('border-warning');
    }
    if (inputSalida && inputSalida.disabled) {
        inputSalida.disabled = false;
        inputSalida.classList.add('border-warning');
    }

    // Add visual cue
    const obs = document.getElementById('manual-observaciones');
    if (obs && !obs.value) {
        obs.value = "[SOBREESCRITURA] ";
    }

    if (typeof showToast === 'function') {
        showToast("Campos desbloqueados. La nueva marca se registrará como manual.", "warning");
    } else {
        alert("Campos desbloqueados. La nueva marca se registrará como manual.");
    }
}

/**
 * Guarda la marcación manual llamando al backend
 */
async function saveManualEntry() {
    const empId = marcacionesManualesState.currentEmpId;
    const dateStr = marcacionesManualesState.currentDate;
    const obs = document.getElementById('manual-observaciones').value;

    const inputEntrada = document.getElementById('manual-hora-entrada');
    const inputSalida = document.getElementById('manual-hora-salida');
    const inputCond = document.getElementById('manual-minutos-conduccion');
    const inputEsp = document.getElementById('manual-minutos-espera');

    const nuevaEntrada = (!inputEntrada.disabled && inputEntrada.value) ? inputEntrada.value : null;
    const nuevaSalida = (!inputSalida.disabled && inputSalida.value) ? inputSalida.value : null;

    let tramosConduccion = null;
    let tramosEspera = null;
    let enviaTramos = false;

    if (marcacionesManualesState.isBolsaFija) {
        tramosConduccion = inputCond && inputCond.value !== "" ? parseInt(inputCond.value) : null;
        tramosEspera = inputEsp && inputEsp.value !== "" ? parseInt(inputEsp.value) : null;
        if (tramosConduccion !== null || tramosEspera !== null) enviaTramos = true;
    }

    if (!nuevaEntrada && !nuevaSalida && !enviaTramos) {
        if (typeof showToast === 'function') showToast("Debe ingresar al menos una hora válida o un tramo de conducción.", "warning");
        else alert("Debe ingresar al menos una hora válida o un tramo de conducción.");
        return;
    }

    const promises = [];

    // Preparar Request de Marcación Manual (Entrada / Salida o Ambas juntas)
    if (nuevaEntrada && nuevaSalida) {
        let urlBoth = `/api/asistencia/marcaciones/manual/?empleado_id=${empId}&fecha=${encodeURIComponent(dateStr)}&hora_entrada=${encodeURIComponent(nuevaEntrada)}&hora_salida=${encodeURIComponent(nuevaSalida)}`;
        if (obs) urlBoth += `&observaciones=${encodeURIComponent(obs)}`;
        promises.push(fetch(urlBoth, { method: 'POST' }).then(r => r.json().then(data => ({ status: r.status, body: data, type: 'Entrada y Salida' }))));
    } else if (nuevaEntrada) {
        let urlEnt = `/api/asistencia/marcaciones/manual/?empleado_id=${empId}&fecha=${encodeURIComponent(dateStr)}&hora=${encodeURIComponent(nuevaEntrada)}&tipo=Entrada`;
        if (obs) urlEnt += `&observaciones=${encodeURIComponent(obs)}`;
        promises.push(fetch(urlEnt, { method: 'POST' }).then(r => r.json().then(data => ({ status: r.status, body: data, type: 'Entrada' }))));
    } else if (nuevaSalida) {
        let urlSal = `/api/asistencia/marcaciones/manual/?empleado_id=${empId}&fecha=${encodeURIComponent(dateStr)}&hora=${encodeURIComponent(nuevaSalida)}&tipo=Salida`;
        if (obs) urlSal += `&observaciones=${encodeURIComponent(obs)}`;
        promises.push(fetch(urlSal, { method: 'POST' }).then(r => r.json().then(data => ({ status: r.status, body: data, type: 'Salida' }))));
    }

    // Preparar Request Tramos (Bolsa Flexible)
    if (enviaTramos) {
        promises.push(
            fetch('/api/asistencia/tramos/', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    empleado_id: parseInt(empId),
                    fecha: dateStr,
                    minutos_conduccion_b: tramosConduccion,
                    minutos_espera_b: tramosEspera
                })
            }).then(r => r.json().then(data => ({ status: r.status, body: data, type: 'Tramos Bolsa' })))
        );
    }

    try {
        const results = await Promise.all(promises);
        let errors = [];
        let successCount = 0;

        results.forEach(res => {
            if (res.status === 200) {
                successCount++;
            } else {
                errors.push(`${res.type}: ${res.body.detail || 'Error'}`);
            }
        });

        if (errors.length > 0) {
            alert(`Errores al guardar:\n${errors.join('\n')}`);
        }

        if (successCount > 0) {
            if (typeof showToast === 'function') showToast(`Se guardaron ${successCount} marcaciones.`, "success");
            closeManualEntryModal();
            if (typeof window.reloadSingleEmployeeRow === 'function') {
                window.reloadSingleEmployeeRow(empId);
            } else if (typeof window.loadMarcacionesData === 'function') {
                window.loadMarcacionesData();
            }
            if (typeof recargarPreEvaluacionCierre === 'function' && document.getElementById('modal-cierre-wizard')?.classList.contains('show')) {
                recargarPreEvaluacionCierre();
            }
        }

    } catch (e) {
        console.error("Error saving manual entry:", e);
        alert("Error de conexión al guardar marcaciones.");
    }
}

/**
 * Abre el modal para validar una jornada especial
 */
function openValidationModal(empId, dateStr, empNombre) {
    if (!marcacionesManualesState.validationModal) initMarcacionesManuales();

    if (!marcacionesManualesState.validationModal) return;

    marcacionesManualesState.currentEmpId = empId;
    marcacionesManualesState.currentDate = dateStr;

    document.getElementById('val-fecha-display').innerText = window.formatFechaDDMMYYYY(dateStr);
    document.getElementById('val-empleado-display').innerText = empNombre;

    const footer = marcacionesManualesState.validationModal.querySelector('.modal-footer');
    if (footer) {
        footer.innerHTML = `
            <button type="button" class="btn btn-outline-danger me-auto" onclick="deleteManualJornada('${empId}', '${dateStr}')" title="Elimina las marcaciones manuales creadas en este día">
                <i class="bi bi-trash"></i> Eliminar Ingreso Manual
            </button>
            <button type="button" class="btn btn-secondary" onclick="closeValidationModal()">Cancelar</button>
            <button type="button" class="btn btn-danger" onclick="validateJornada('RECHAZAR')">
                ❌ Rechazar Jornada
            </button>
            <button type="button" class="btn btn-success" onclick="validateJornada('APROBAR')">
                ✅ Validar Jornada
            </button>
        `;
    }

    if (marcacionesManualesState.validationInstance) {
        marcacionesManualesState.validationInstance.show();
    }
}

function closeValidationModal() {
    if (marcacionesManualesState.validationInstance) {
        marcacionesManualesState.validationInstance.hide();
    }
}

/**
 * Llama al endpoint de validación (Aprobar o Rechazar)
 */
async function validateJornada(accion = 'APROBAR') {
    const payload = {
        empleado_id: parseInt(marcacionesManualesState.currentEmpId),
        fecha: marcacionesManualesState.currentDate,
        accion: accion,
        last_updated_at: (function () {
            const empMatrix = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[marcacionesManualesState.currentEmpId] : null;
            const asist = empMatrix ? empMatrix[marcacionesManualesState.currentDate] : null;
            return asist ? asist.updated_at : null;
        })()
    };

    try {
        const resp = await fetch('/api/asistencia/jornada/validar/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (resp.ok) {
            const msg = accion === 'APROBAR' ? "Jornada validada exitosamente" : "Jornada rechazada correctamente";
            if (typeof showToast === 'function') showToast(msg, accion === 'APROBAR' ? "success" : "info");
            else alert(msg);

            closeValidationModal();
            if (typeof window.reloadSingleEmployeeRow === 'function') {
                window.reloadSingleEmployeeRow(payload.empleado_id);
            } else if (typeof loadMarcacionesData === 'function') {
                loadMarcacionesData();
            }
            if (typeof recargarPreEvaluacionCierre === 'function' && document.getElementById('modal-cierre-wizard')?.classList.contains('show')) {
                recargarPreEvaluacionCierre();
            }
        } else {
            const result = await resp.json();
            if (resp.status === 409) {
                alert(`Conflicto de Concurrencia: ${result.detail}`);
                if (typeof window.reloadSingleEmployeeRow === 'function') {
                    window.reloadSingleEmployeeRow(payload.empleado_id);
                } else if (typeof loadMarcacionesData === 'function') {
                    loadMarcacionesData();
                }
            } else {
                alert(`Error: ${result.detail || 'Fallo al validar'}`);
            }
        }
    } catch (e) {
        console.error("Error validating jornada:", e);
        alert("Error de conexión");
    }
}

/**
 * Llama al endpoint para eliminar el ingreso manual que generó la jornada especial
 * @param {string|number} empId 
 * @param {string} fecha 
 */
async function deleteManualJornada(empId, fecha) {
    if (!confirm(`¿Está seguro que desea eliminar TODAS las marcaciones manuales ingresadas para el día ${window.formatFechaDDMMYYYY(fecha)}? Esta acción no se puede deshacer.`)) {
        return;
    }

    try {
        const url = `/api/asistencia/marcaciones/manual/?empleado_id=${empId}&fecha=${fecha}`;
        const resp = await fetch(url, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (resp.ok) {
            const data = await resp.json();
            if (typeof showToast === 'function') {
                showToast(data.mensaje || "Marcaciones manuales eliminadas", "success");
            } else {
                alert(data.mensaje || "Marcaciones manuales eliminadas");
            }
            closeValidationModal();
            
            // Refrescar grilla
            if (typeof window.reloadSingleEmployeeRow === 'function') {
                window.reloadSingleEmployeeRow(empId);
            } else if (typeof window.loadMarcacionesData === 'function') {
                window.loadMarcacionesData();
            }
            if (typeof recargarPreEvaluacionCierre === 'function' && document.getElementById('modal-cierre-wizard')?.classList.contains('show')) {
                recargarPreEvaluacionCierre();
            }
        } else {
            const error = await resp.json();
            if (typeof showToast === 'function') {
                showToast(`Error: ${error.detail || 'No se pudo eliminar'}`, "error");
            } else {
                alert(`Error: ${error.detail || 'No se pudo eliminar'}`);
            }
        }
    } catch (e) {
        console.error("Error al eliminar ingreso manual:", e);
        if (typeof showToast === 'function') {
            showToast("Error de conexión con el servidor", "error");
        } else {
            alert("Error de conexión con el servidor");
        }
    }
}

// Event Listeners globales (si se carga después del DOM)
document.addEventListener('DOMContentLoaded', () => {
    initMarcacionesManuales();
});

// Cerrar modales con click fuera
window.addEventListener('click', function (event) {
    if (event.target == marcacionesManualesState.manualModal) {
        closeManualEntryModal();
    }
    if (event.target == marcacionesManualesState.validationModal) {
        closeValidationModal();
    }
    if (event.target == marcacionesManualesState.decisionModal) {
        closeAsistenciaActionModal();
    }
    // New: Close Bulk Fill Modal
    const bulkModal = document.getElementById('modal-relleno-masivo');
    if (bulkModal && event.target == bulkModal) {
        closeBulkFillModal();
    }
});

// ==========================================
// LÓGICA RELLENO MASIVO (BULK FILL)
// ==========================================

let bulkFillModal = null; // Bootstrap Modal Instance if using BS5, or generic element

function openBulkFillModal(empId = null, empNombre = null, startDate = null) {
    const modalEl = document.getElementById('modal-relleno-masivo');
    if (!modalEl) {
        console.error("Modal Relleno Masivo no encontrado en HTML");
        return;
    }

    // Set Employee Name and ID
    if (empId) document.getElementById('fill-empleado-id').value = empId;
    if (empNombre) document.getElementById('fill-empleado-nombre').value = empNombre;

    // Pre-set Fechas
    if (startDate) {
        document.getElementById('fill-fecha-inicio').value = startDate;
        // Default: End date same as start date (or end of week?)
        // Let's set it to same day for safety, user can change it
        document.getElementById('fill-fecha-fin').value = startDate;
    } else {
        const today = new Date().toISOString().split('T')[0];
        document.getElementById('fill-fecha-inicio').value = today;
        document.getElementById('fill-fecha-fin').value = today;
    }

    // Mostrar Modal (Bootstrap 5 Check)
    if (typeof bootstrap !== 'undefined') {
        bulkFillModal = bootstrap.Modal.getOrCreateInstance(modalEl);
        bulkFillModal.show();
    } else {
        modalEl.style.display = 'block';
        modalEl.classList.add('show');
    }
}

function closeBulkFillModal() {
    const modalEl = document.getElementById('modal-relleno-masivo');
    if (bulkFillModal) {
        bulkFillModal.hide();
    } else if (modalEl) {
        modalEl.style.display = 'none';
        modalEl.classList.remove('show');
    }
}

async function executeBulkFill() {
    const empId = document.getElementById('fill-empleado-id').value;
    const fInicio = document.getElementById('fill-fecha-inicio').value;
    const fFin = document.getElementById('fill-fecha-fin').value;
    const sobrescribir = document.getElementById('fill-sobrescribir').checked;

    if (!empId || !fInicio || !fFin) {
        alert("Por favor complete todos los campos requeridos.");
        return;
    }

    // Loading State
    const btn = document.querySelector('#form-relleno-masivo button[type="submit"]');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Procesando...';

    const payload = {
        empleado_id: parseInt(empId),
        fecha_inicio: fInicio,
        fecha_fin: fFin,
        sobrescribir: sobrescribir
    };

    try {
        const resp = await fetch('/api/asistencia/marcaciones/masivas/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await resp.json();

        if (resp.ok && result.success) {
            alert(`✅ ${result.mensaje}`);
            closeBulkFillModal();
            // Recargar Grilla
            if (typeof window.reloadSingleEmployeeRow === 'function') {
                window.reloadSingleEmployeeRow(empId);
            } else if (typeof loadMarcacionesData === 'function') {
                loadMarcacionesData();
            }
            if (typeof recargarPreEvaluacionCierre === 'function' && document.getElementById('modal-cierre-wizard')?.classList.contains('show')) {
                recargarPreEvaluacionCierre();
            }
        } else {
            alert(`⚠️ Error: ${result.detail || result.mensaje || 'Error desconocido'}`);
            console.error("Bulk Fill Error:", result);
        }
    } catch (e) {
        console.error("Network error:", e);
        alert("Error de conexión al servidor.");
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}
// ==========================================
// LÓGICA DE REGISTRO DE PERMISO (RRHH MANUAL)
// ==========================================

async function openPermissionModal(empId, empNombre, dateStr) {
    const modal = document.getElementById('modal-registro-permiso');
    if (!modal) return;

    marcacionesManualesState.currentEmpId = empId;
    marcacionesManualesState.currentDate = dateStr;
    marcacionesManualesState.permisoActivoActual = null;

    document.getElementById('permiso-emp-nombre').innerText = empNombre;
    document.getElementById('permiso-fecha').innerText = window.formatFechaDDMMYYYY(dateStr);
    document.getElementById('permiso-tipo-id').innerHTML = '<option value="">Cargando...</option>';
    document.getElementById('permiso-info-deuda').classList.add('d-none');
    document.getElementById('form-registro-permiso').reset();

    const inputInicio = document.getElementById('permiso-hora-inicio');
    const inputFin = document.getElementById('permiso-hora-fin');
    const inputTipo = document.getElementById('permiso-tipo-id');
    const btnSubmit = document.querySelector('#modal-registro-permiso .modal-footer .btn-warning');

    // Resetear estados por defecto
    inputInicio.disabled = false;
    inputFin.disabled = false;
    inputTipo.disabled = false;
    if (btnSubmit) {
        btnSubmit.style.display = 'inline-block';
        btnSubmit.innerText = "Registrar Salida / Permiso";
    }

    // 1. Verificar si ya hay un permiso en la MATRIZ (ya enriquecido por el backend)
    const empMatrix = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
    const asist = empMatrix ? empMatrix[dateStr] : null;

    if (asist && asist.permiso_activo) {
        // PERMISO ABIERTO (-PEN): Bloquear inicio, permitir fin
        marcacionesManualesState.permisoActivoActual = {
            id: asist.permiso_id,
            tipo_id: asist.permiso_tipo_id,
            hora_inicio: asist.permiso_hora_inicio
        };
        inputInicio.value = asist.permiso_hora_inicio;
        inputInicio.disabled = true;
        inputFin.value = '';
        if (btnSubmit) btnSubmit.innerText = "Registrar Regreso";
    } else if (asist && asist.tiene_permiso_hora && asist.permiso_hora_inicio && asist.permiso_hora_fin) {
        // PERMISO CERRADO (-PER): Bloquear AMBOS
        inputInicio.value = asist.permiso_hora_inicio;
        inputFin.value = asist.permiso_hora_fin;
        inputInicio.disabled = true;
        inputFin.disabled = true;
        inputTipo.disabled = true;
        if (btnSubmit) btnSubmit.style.display = 'none'; // Ocultar porque ya está cerrado
    } else {
        // NUEVO PERMISO: Todo habilitado
        inputInicio.value = '';
        inputFin.value = '';
        if (btnSubmit) btnSubmit.innerText = "Registrar Salida / Permiso";
    }

    // 2. Cargar Tipos de Justificación que sean "Por Horas"
    try {
        const resp = await fetch('/api/configuracion/justificaciones/tipos/');
        const tipos = await resp.json();
        const tiposPorHora = tipos.filter(t => t.es_por_horas);

        if (tiposPorHora.length === 0) {
            inputTipo.innerHTML = '<option value="">No hay tipos "Por Horas" configurados</option>';
        } else {
            inputTipo.innerHTML = '<option value="">Seleccione tipo...</option>' +
                tiposPorHora.map(t => `<option value="${t.id}" data-deuda="${t.genera_deuda_horaria}">${t.nombre}</option>`).join('');

            if (marcacionesManualesState.permisoActivoActual) {
                inputTipo.value = marcacionesManualesState.permisoActivoActual.tipo_id;
                inputTipo.disabled = true; // Bloqueado si ya está activo
            } else if (asist && asist.tiene_permiso_hora && asist.permiso_tipo_id) {
                inputTipo.value = asist.permiso_tipo_id;
                inputTipo.disabled = true; // Bloqueado si ya está cerrado
            }
        }
    } catch (e) {
        console.error("Error cargando tipos de permiso:", e);
    }

    modal.style.display = 'block';
}

function closePermissionModal() {
    const modal = document.getElementById('modal-registro-permiso');
    if (modal) modal.style.display = 'none';
}

window.onPermissionTypeChange = function () {
    const select = document.getElementById('permiso-tipo-id');
    const infoDeuda = document.getElementById('permiso-info-deuda');
    const selectedOption = select.options[select.selectedIndex];

    if (selectedOption && selectedOption.dataset.deuda === 'true') {
        infoDeuda.classList.remove('d-none');
    } else {
        infoDeuda.classList.add('d-none');
    }
}

async function savePermissionEntry() {
    const tipoId = document.getElementById('permiso-tipo-id').value;
    const hIni = document.getElementById('permiso-hora-inicio').value;
    const hFin = document.getElementById('permiso-hora-fin').value;
    const obs = document.getElementById('permiso-observaciones').value;

    if (!tipoId || !hIni) {
        alert("Por favor indique al menos el tipo y la hora de inicio.");
        return;
    }

    const mode = marcacionesManualesState.permisoActivoActual ? 'CLOSE' : 'OPEN';

    try {
        let resp;
        const msgOperacion = mode === 'CLOSE' ? "Regreso registrado" : "Permiso registrado";

        if (mode === 'CLOSE') {
            if (!hFin) {
                alert("Debe indicar la hora de regreso para cerrar el permiso.");
                return;
            }
            resp = await fetch('/api/configuracion/justificaciones/cerrar/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    empleado_id: parseInt(marcacionesManualesState.currentEmpId),
                    fecha: marcacionesManualesState.currentDate,
                    hora_fin: hFin
                })
            });
        } else {
            const payload = {
                empleado_id: parseInt(marcacionesManualesState.currentEmpId),
                tipo_id: parseInt(tipoId),
                fecha_inicio: marcacionesManualesState.currentDate,
                fecha_fin: marcacionesManualesState.currentDate,
                hora_inicio: hIni,
                hora_fin: hFin || null,
                observaciones: obs
            };
            resp = await fetch('/api/configuracion/justificaciones/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        }

        if (resp.ok) {
            if (typeof showToast === 'function') showToast(msgOperacion, "success");
            else alert(msgOperacion);

            closePermissionModal();
            if (typeof window.reloadSingleEmployeeRow === 'function') {
                window.reloadSingleEmployeeRow(marcacionesManualesState.currentEmpId);
            } else if (typeof loadMarcacionesData === 'function') {
                loadMarcacionesData();
            }
            if (typeof recargarPreEvaluacionCierre === 'function' && document.getElementById('modal-cierre-wizard')?.classList.contains('show')) {
                recargarPreEvaluacionCierre();
            }
        } else {
            const err = await resp.json();
            alert("Error: " + (err.detail || "Fallo en la operación"));
        }
    } catch (e) {
        console.error("Error guardando permiso:", e);
        alert("Error de conexión");
    }
}

// Perdonazo masivo: delegado a window.executeCondonacionMasiva (marcaciones_ui.js)
// Las funciones openPerdonazoMasivoModal/closePerdonazoMasivoModal/executePerdonazoMasivo
// han sido reemplazadas por los nuevos flujos UX (switch + panel lateral por fecha)

/** @deprecated - Reemplazada por abrirPanelPerdonazoPorFecha() en perdonazo_panel.js */
function openPerdonazoMasivoModal() {
    console.warn('[DEPRECATED] openPerdonazoMasivoModal: usar el Switch Perdonazos + clic en columna de fecha.');
}

function closePerdonazoMasivoModal() {
    const modalEl = document.getElementById('modal-perdonazo-masivo');
    if (typeof bootstrap !== 'undefined' && modalEl) {
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
    } else if (modalEl) {
        modalEl.style.display = 'none';
        modalEl.classList.remove('show');
    }
}

async function executePerdonazoMasivo() {
    const btn = document.querySelector('#form-perdonazo-masivo button[type="submit"]');
    const originalText = btn.innerHTML;
    
    try {
        const area = document.getElementById('perdonazo-area').value;
        const fechaInicio = document.getElementById('perdonazo-fecha-inicio').value;
        const fechaFin = document.getElementById('perdonazo-fecha-fin').value;
        const condonar = document.getElementById('perdonazo-accion').checked;
        const tipoCondonacionBase = parseInt(document.getElementById('perdonazo-tipo').value) || 1;
        const tipoCondonacion = condonar ? tipoCondonacionBase : 0;

        if (!fechaInicio || !fechaFin) {
            alert("Debe seleccionar un rango de fechas válido.");
            return;
        }

        btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Procesando...';
        btn.disabled = true;

        // 1. Obtener empleados del área (o todos)
        let searchUrl = '/api/empleados/search/?limit=5000&activo=true';
        if (area) {
            searchUrl += `&area=${encodeURIComponent(area)}`;
        }
        
        const empResp = await fetch(searchUrl);
        if (!empResp.ok) throw new Error("Error obteniendo lista de empleados");
        const empData = await empResp.json();
        const emps = empData.empleados || empData.items || empData;
        const empleadosIds = emps.map(e => e.id);

        if (empleadosIds.length === 0) {
            alert("No se encontraron empleados activos para el área seleccionada.");
            return;
        }

        const payload = {
            empleados_ids: empleadosIds,
            fecha_inicio: fechaInicio,
            fecha_fin: fechaFin,
            tipo_condonacion: tipoCondonacion
        };

        const resp = await fetch('/api/asistencia/condonar-deuda/', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${window.AuthToken || localStorage.getItem('token')}`
            },
            body: JSON.stringify(payload)
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Error en la operación masiva");
        }

        const result = await resp.json();
        alert(`Proceso completado.\\nRegistros procesados/condonados: ${result.registros_procesados || 'OK'}`);
        closePerdonazoMasivoModal();
        
        // Refrescar si existe la función
        if (typeof loadReporte === 'function') {
            loadReporte();
        } else if (typeof window.loadMarcacionesData === 'function') {
            window.loadMarcacionesData();
        }

    } catch (e) {
        console.error("Error en executePerdonazoMasivo:", e);
        alert(`Error: ${e.message}`);
    } finally {
        if (btn) {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    }
}


// ─────────────────────────────────────────────────────────────────────────
// FUNCIONES VIAJE LARGO (BOLSA FLEXIBLE)
// ─────────────────────────────────────────────────────────────────────────
function getViajeLargoAuthToken() {
    if (typeof AuthService !== 'undefined' && typeof AuthService.getToken === 'function') {
        const t = AuthService.getToken();
        if (t) return t;
    }
    return localStorage.getItem('access_token') || localStorage.getItem('token') || window.AuthToken || '';
}

async function proceedToViajeLargo() {
    const empId = marcacionesManualesState.currentEmpId;
    const dateStr = marcacionesManualesState.currentDate;
    const empNombre = marcacionesManualesState.currentEmpNombre;

    const token = getViajeLargoAuthToken();
    if (!token) {
        alert("Sesión no válida o expirada. Por favor reinicie sesión.");
        return;
    }

    try {
        // Cargar candidatos de inicio y retorno desde el backend
        const resp = await fetch(`/api/asistencia/viajes-largos/candidatos-retorno/?empleado_id=${empId}&fecha_inicio=${dateStr}`, {
            headers: { 
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!resp.ok) {
            const errJson = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(errJson.detail || `Error HTTP ${resp.status}`);
        }

        const data = await resp.json();
        const candidatosAll = data.candidatos || [];
        const candInicio = (data.candidatos_inicio && data.candidatos_inicio.length > 0) ? data.candidatos_inicio : candidatosAll;
        const candRetorno = (data.candidatos_retorno && data.candidatos_retorno.length > 0) ? data.candidatos_retorno : candidatosAll;

        if (candidatosAll.length === 0) {
            alert("No se encontraron marcaciones registradas para iniciar o unir este viaje. Si el empleado olvidó marcar, use 'Ingreso Manual' primero.");
            return;
        }

        // Guardar lista completa en window para actualización dinámica
        window._vl_candidatos_all = candidatosAll;
        window._vl_candidatos_retorno = candRetorno;

        // Cerrar modal de decisiones únicamente cuando la carga de candidatos sea exitosa
        closeAsistenciaActionModal();

        document.getElementById('vl-emp-id').value = empId;
        document.getElementById('vl-fecha-ini').value = dateStr;

        // Obtener viaje_largo existente de la matriz (si ya fue registrado previamente)
        const empMatrixJ = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
        const asistJ = empMatrixJ ? empMatrixJ[dateStr] : null;
        const vlExistente = asistJ ? (asistJ.viaje_largo || null) : null;

        if (vlExistente) {
            document.getElementById('vl-ciudad-destino').value = vlExistente.ciudad_destino || '';
            document.getElementById('vl-hrs-manejo').value = vlExistente.horas_manejo_efectivas != null ? vlExistente.horas_manejo_efectivas : '';
            document.getElementById('vl-hrs-descanso').value = vlExistente.horas_descanso != null ? vlExistente.horas_descanso : '';
            document.getElementById('vl-hrs-reconocidas').value = vlExistente.horas_reconocidas_totales != null ? vlExistente.horas_reconocidas_totales : '';
            document.getElementById('vl-observaciones').value = vlExistente.observaciones || '';
        } else {
            // Reset campos para nuevo viaje
            document.getElementById('vl-ciudad-destino').value = '';
            document.getElementById('vl-hrs-manejo').value = '';
            document.getElementById('vl-hrs-descanso').value = '';
            document.getElementById('vl-hrs-reconocidas').value = '';
            document.getElementById('vl-observaciones').value = '';
        }

        // Poblar Selector INICIO (#vl-select-inicio)
        const selectIni = document.getElementById('vl-select-inicio');
        selectIni.innerHTML = '';
        let htmlOptsIni = '';
        for (let i = 0; i < candInicio.length; i++) {
            const c = candInicio[i];
            const tagStr = c.consumida ? '(Turno Ordinario)' : '(Anomalía Libre)';
            const isSel = (vlExistente && vlExistente.log_entrada_id == c.id) ? 'selected' : '';
            htmlOptsIni += `<option value="${c.id}" data-fecha="${c.fecha}" data-fecha-hora="${c.fecha_hora}" ${isSel}>${c.fecha_hora} — ${c.tipo} ${tagStr}</option>`;
        }
        selectIni.innerHTML = htmlOptsIni;

        // Poblar Selector RETORNO (#vl-select-retorno) dinámicamente según Inicio seleccionado
        window.updateViajeLargoCandidatosRetorno(vlExistente ? vlExistente.log_salida_id : null);

        // Mostrar Modal Viaje Largo con retardo seguro para evitar choques con el backdrop de Bootstrap
        setTimeout(() => {
            const el = document.getElementById('modalViajeLargo');
            if (el) {
                let modal = bootstrap.Modal.getInstance(el);
                if (!modal) {
                    modal = new bootstrap.Modal(el, { backdrop: 'static', keyboard: true });
                }
                modal.show();
            }
        }, 150);

    } catch (e) {
        console.error("Error abriendo Viaje Largo:", e);
        alert("Error al obtener marcaciones para Viaje Largo: " + e.message);
    }
}

window.updateViajeLargoCandidatosRetorno = function(preselectedRetId) {
    const selectIni = document.getElementById('vl-select-inicio');
    const selectRet = document.getElementById('vl-select-retorno');
    if (!selectIni || !selectRet) return;

    const optIni = selectIni.options[selectIni.selectedIndex];
    if (!optIni) return;

    const fhIniStr = optIni.getAttribute('data-fecha-hora');
    const dtIni = new Date(fhIniStr.replace(' ', 'T'));
    document.getElementById('vl-log-entrada-id').value = optIni.value;

    const candRetorno = window._vl_candidatos_retorno || window._vl_candidatos_all || [];
    let htmlOptsRet = '';

    for (let i = 0; i < candRetorno.length; i++) {
        const c = candRetorno[i];
        const dtRet = new Date(c.fecha_hora.replace(' ', 'T'));
        if (dtRet > dtIni) {
            const diffHours = ((dtRet - dtIni) / (1000 * 3600)).toFixed(1);
            const tagStr = c.consumida ? '(Consumida)' : '(Anomalía Libre)';
            const isSel = (preselectedRetId && preselectedRetId == c.id) ? 'selected' : '';
            htmlOptsRet += `<option value="${c.id}" data-fecha="${c.fecha}" data-fecha-hora="${c.fecha_hora}" data-horas="${diffHours}" ${isSel}>${c.fecha_hora} — ${c.tipo} ${tagStr} (${diffHours}h transcurridas)</option>`;
        }
    }

    if (!htmlOptsRet) {
        // Fallback: si no hay candidata posterior pura, mostrar todas
        const candAll = window._vl_candidatos_all || [];
        for (let i = 0; i < candAll.length; i++) {
            const c = candAll[i];
            if (c.id != optIni.value) {
                const dtRet = new Date(c.fecha_hora.replace(' ', 'T'));
                const diffHours = Math.max(0, ((dtRet - dtIni) / (1000 * 3600))).toFixed(1);
                const isSel = (preselectedRetId && preselectedRetId == c.id) ? 'selected' : '';
                htmlOptsRet += `<option value="${c.id}" data-fecha="${c.fecha}" data-fecha-hora="${c.fecha_hora}" data-horas="${diffHours}" ${isSel}>${c.fecha_hora} — ${c.tipo} (${diffHours}h transcurridas)</option>`;
            }
        }
    }

    selectRet.innerHTML = htmlOptsRet;
    window.updateViajeLargoCalculos();
};

function updateViajeLargoCalculos(sourceField) {
    const selectRet = document.getElementById('vl-select-retorno');
    if (!selectRet || selectRet.selectedIndex < 0) return;
    const opt = selectRet.options[selectRet.selectedIndex];
    if (!opt) {
        document.getElementById('vl-txt-duracion').innerText = '0.0h';
        return;
    }

    const totalReloj = parseFloat(opt.getAttribute('data-horas')) || 0;
    document.getElementById('vl-txt-duracion').innerText = `${totalReloj.toFixed(1)}h reloj`;

    const elManejo = document.getElementById('vl-hrs-manejo');
    const elDescanso = document.getElementById('vl-hrs-descanso');
    const elReconocidas = document.getElementById('vl-hrs-reconocidas');

    if (!elManejo || !elDescanso || !elReconocidas) return;

    let hManejo = parseFloat(elManejo.value);
    let hDescanso = parseFloat(elDescanso.value);

    if (sourceField === 'descanso') {
        if (!isNaN(hDescanso) && totalReloj > 0) {
            hManejo = Math.max(0, totalReloj - hDescanso);
            elManejo.value = hManejo.toFixed(1);
            elReconocidas.value = hManejo.toFixed(1);
        }
    } else if (sourceField === 'manejo') {
        if (!isNaN(hManejo) && totalReloj > 0) {
            hDescanso = Math.max(0, totalReloj - hManejo);
            elDescanso.value = hDescanso.toFixed(1);
            elReconocidas.value = hManejo.toFixed(1);
        }
    } else {
        // Inicializar por defecto con el totalReloj SOLO si no hay un valor ingresado/cargado previamente
        if (!elManejo.value || isNaN(parseFloat(elManejo.value))) {
            elManejo.value = totalReloj.toFixed(1);
            elDescanso.value = '0.0';
            elReconocidas.value = totalReloj.toFixed(1);
        }
    }
}

async function submitViajeLargo() {
    const empId = parseInt(document.getElementById('vl-emp-id').value);
    const fechaIni = document.getElementById('vl-fecha-ini').value;
    const logEntradaId = parseInt(document.getElementById('vl-log-entrada-id').value);
    
    const selectRet = document.getElementById('vl-select-retorno');
    const optRet = (selectRet && selectRet.selectedIndex >= 0) ? selectRet.options[selectRet.selectedIndex] : null;
    const logSalidaId = selectRet ? parseInt(selectRet.value) : 0;
    
    const optRetFh = optRet ? optRet.getAttribute('data-fecha-hora') : null;
    const fechaFin = (optRet && optRet.getAttribute('data-fecha')) ? optRet.getAttribute('data-fecha') : (optRetFh ? optRetFh.substring(0, 10) : fechaIni);

    const ciudadOrigen = document.getElementById('vl-ciudad-origen').value.trim() || 'Planta Aguacol';
    const ciudadDestino = document.getElementById('vl-ciudad-destino').value.trim();
    const hrsManejo = parseFloat(document.getElementById('vl-hrs-manejo').value);
    const hrsDescanso = parseFloat(document.getElementById('vl-hrs-descanso').value) || 0.0;
    const hrsReconocidas = parseFloat(document.getElementById('vl-hrs-reconocidas').value) || hrsManejo;
    const observaciones = document.getElementById('vl-observaciones').value.trim();

    if (!ciudadDestino) {
        alert("Por favor ingrese la Ciudad Destino del viaje.");
        return;
    }
    if (isNaN(hrsManejo) || hrsManejo <= 0) {
        alert("Por favor ingrese las Horas de Manejo Efectivas válidas.");
        return;
    }

    const payload = {
        empleado_id: empId,
        fecha_inicio: fechaIni,
        fecha_fin: fechaFin,
        log_entrada_id: logEntradaId,
        log_salida_id: logSalidaId,
        ciudad_origen: ciudadOrigen,
        ciudad_destino: ciudadDestino,
        horas_manejo_efectivas: hrsManejo,
        horas_descanso: hrsDescanso,
        horas_reconocidas_totales: hrsReconocidas,
        observaciones: observaciones
    };

    const token = getViajeLargoAuthToken();

    try {
        const resp = await fetch('/api/asistencia/viajes-largos/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            let errMsg = "Error registrando viaje largo";
            if (typeof err.detail === 'string') {
                errMsg = err.detail;
            } else if (Array.isArray(err.detail)) {
                errMsg = err.detail.map(d => `${d.loc ? d.loc.join('.') : ''}: ${d.msg}`).join('\n');
            } else if (typeof err.detail === 'object') {
                errMsg = JSON.stringify(err.detail);
            }
            throw new Error(errMsg);
        }

        const resData = await resp.json();
        
        if (typeof showToast === 'function') {
            showToast(`Viaje Largo a ${ciudadDestino} registrado exitosamente`, "success");
        } else {
            alert(`Viaje Largo a ${ciudadDestino} registrado exitosamente`);
        }

        // Cerrar modal
        const el = document.getElementById('modalViajeLargo');
        if (el) {
            const modal = bootstrap.Modal.getInstance(el);
            if (modal) modal.hide();
        }

        // Refrescar grilla completa para actualizar acumulados, bolsa y badges de viaje
        if (typeof window.loadMarcacionesData === 'function') {
            window.loadMarcacionesData();
        }

    } catch (e) {
        console.error("Error al guardar Viaje Largo:", e);
        alert("Error al guardar Viaje Largo: " + e.message);
    }
}

window.proceedToViajeLargo = proceedToViajeLargo;
window.updateViajeLargoCalculos = updateViajeLargoCalculos;
window.submitViajeLargo = submitViajeLargo;


