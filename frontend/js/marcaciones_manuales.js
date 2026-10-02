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

    // --- NUEVO: MOSTRAR DETALLE DUAL (TURNO BASE VS COBERTURA +2) SI EXISTE ---
    const dualBox = document.getElementById('decision-dual-split-box');
    const empMatrixGeneral = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
    const asistGeneral = empMatrixGeneral ? empMatrixGeneral[dateStr] : null;
    const jaGeneral = asistGeneral ? asistGeneral.jornada_adicional : null;

    if (dualBox) {
        if (jaGeneral && asistGeneral && (asistGeneral.horas_teoricas > 0 || asistGeneral.hora_entrada_real)) {
            const horasJa = jaGeneral.minutos_trabajados ? (Math.round(jaGeneral.minutos_trabajados / 60.0 * 10) / 10) : 0;
            const estadoJaBadge = jaGeneral.estado === 'HORAS_EXTRAS'
                ? '<span class="badge bg-warning-subtle text-dark border border-warning fw-bold">⏱️ Horas Extras (50%)</span>'
                : jaGeneral.estado === 'EXTRA'
                ? '<span class="badge bg-success-subtle text-success border border-success-subtle fw-bold">EXTRA Aprobada</span>'
                : jaGeneral.estado === 'RECHAZADA'
                ? '<span class="badge bg-danger-subtle text-danger border border-danger-subtle fw-bold">Rechazada</span>'
                : '<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle fw-bold">Pendiente Validación</span>';

            const estadoBaseBadge = asistGeneral.estado === 'OK'
                ? '<span class="badge bg-success-subtle text-success border border-success-subtle fw-bold">OK</span>'
                : `<span class="badge bg-info-subtle text-info-emphasis border border-info-subtle fw-bold">${asistGeneral.estado || 'OK'}</span>`;

            dualBox.innerHTML = `
                <div class="p-2 rounded-3 border" style="background:#f8fafc; font-size:0.75rem;">
                    <div class="d-flex justify-content-between align-items-center mb-1 pb-1 border-bottom">
                        <span class="text-secondary"><i class="bi bi-clock me-1 text-primary"></i> Turno Base:</span>
                        <div class="text-end">
                            ${estadoBaseBadge}
                            <span class="ms-1 text-muted" style="font-size: 0.75rem;">${asistGeneral.hora_entrada_real || '--:--'} a ${asistGeneral.hora_salida_real || '--:--'}</span>
                        </div>
                    </div>
                    <div class="d-flex justify-content-between align-items-center">
                        <span class="text-secondary"><i class="bi bi-plus-circle me-1" style="color:#8b5cf6;"></i> Cobertura (+2):</span>
                        <div class="text-end">
                            ${estadoJaBadge}
                            <span class="ms-1 text-muted" style="font-size: 0.75rem;">${jaGeneral.hora_entrada || '--:--'} a ${jaGeneral.hora_salida || '--:--'} (${horasJa}h)</span>
                        </div>
                    </div>
                </div>
            `;
            dualBox.classList.remove('d-none');
        } else {
            dualBox.innerHTML = '';
            dualBox.classList.add('d-none');
        }
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
        const ja = asistJ ? asistJ.jornada_adicional : null;
        // REGLA: mostrar cuando el estado es JORNADA_ESPECIAL (ambas marcas completas)
        // O cuando hay una jornada adicional (cobertura) pendiente, por validar o rechazada.
        const tieneJornadaAdicionalPorValidar = ja &&
            (ja.estado === 'PENDIENTE' || ja.estado === 'RECHAZADA' || ja.estado === 'JORNADA_ESPECIAL');
            
        if (asistJ && (asistJ.estado === 'JORNADA_ESPECIAL' || tieneJornadaAdicionalPorValidar)) {
            btnValidarJornada.classList.remove('d-none');
            const titleEl = btnValidarJornada.querySelector('.fw-semibold');
            const subEl = btnValidarJornada.querySelector('.text-muted');
            if (ja) {
                const horasJa = ja.minutos_trabajados ? (Math.round(ja.minutos_trabajados / 60.0 * 10) / 10) : 0;
                if (titleEl) titleEl.innerText = "Validar Cobertura (+2)";
                if (subEl) subEl.innerText = `Aprobar o rechazar cobertura (${horasJa}h)`;
            } else {
                if (titleEl) titleEl.innerText = "Validar Jornada Especial";
                if (subEl) subEl.innerText = "Aprobar día libre trabajado";
            }
        } else {
            btnValidarJornada.classList.add('d-none');
        }
    }

    const btnRevertirHE = document.getElementById('btn-revertir-he');
    if (btnRevertirHE) {
        const empMatrixJ = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
        const asistJ = empMatrixJ ? empMatrixJ[dateStr] : null;
        // Solo mostrar si el estado es EXTRA o HORAS_EXTRAS y es producto de una validación de jornada especial.
        // O si tiene una jornada adicional aprobada (estado EXTRA o HORAS_EXTRAS)
        const tieneJornadaAdicionalAprobada = asistJ && asistJ.jornada_adicional && (asistJ.jornada_adicional.estado === 'EXTRA' || asistJ.jornada_adicional.estado === 'HORAS_EXTRAS');
        
        if (asistJ && (asistJ.estado === 'EXTRA' || asistJ.estado === 'HORAS_EXTRAS' || tieneJornadaAdicionalAprobada)) {
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
        const permiteViajes = Boolean(empInfo && (empInfo.permite_viajes_largos === 1 || empInfo.permite_viajes_largos === true));
        
        // REGLA: Mostrar solo si el turno tiene explícitamente permite_viajes_largos activo Y la celda tiene ANOMALIA o marcación
        const tieneMarcaOAnomalia = asistJ && (asistJ.estado === 'ANOMALIA' || asistJ.tiene_anomalia || asistJ.alerta_anomalia || asistJ.hora_entrada_real || asistJ.hora_salida_real || (asistJ.marcas_consumidas_ids && asistJ.marcas_consumidas_ids !== '[]'));

        if (permiteViajes && tieneMarcaOAnomalia) {
            btnViajeLargo.classList.remove('d-none');
        } else {
            btnViajeLargo.classList.add('d-none');
        }
    }

    // --- MOSTRAR/OCULTAR BOTÓN REASIGNAR / MOVER TURNO ---
    const btnReasignarTurno = document.getElementById('btn-reasignar-turno');
    if (btnReasignarTurno) {
        const empInfo = stateMarcacionesApp.data && stateMarcacionesApp.data.empleados ? stateMarcacionesApp.data.empleados.find(e => e.id == empId) : null;
        const isNotBolsa = (!empInfo || (empInfo.tipo_programacion !== 'BOLSA_FLEXIBLE' && empInfo.tipo_programacion !== 'FLEXIBLE_BOLSA'));
        
        // Mostrar siempre para empleados con turno agendado (no bolsa flexible)
        if (isNotBolsa) {
            btnReasignarTurno.classList.remove('d-none');
        } else {
            btnReasignarTurno.classList.add('d-none');
        }
    }

    // --- MOSTRAR/OCULTAR BOTÓN MARCACIÓN 180 HORAS (ART. 25 BIS DT) ---
    const btnMarcacion180h = document.getElementById('btn-marcacion-180h');
    if (btnMarcacion180h) {
        const empInfo = stateMarcacionesApp.data && stateMarcacionesApp.data.empleados ? stateMarcacionesApp.data.empleados.find(e => e.id == empId) : null;
        const isBolsa = Boolean(empInfo && (empInfo.tipo_programacion === 'BOLSA_FLEXIBLE' || empInfo.tipo_programacion === 'FLEXIBLE_BOLSA'));
        const isLibreta = Boolean(empInfo && (empInfo.modalidad_control === 'LIBRETA_180H' || isBolsa));

        if (isLibreta) {
            btnMarcacion180h.classList.remove('d-none');
        } else {
            btnMarcacion180h.classList.add('d-none');
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
    
    if (!await uiConfirm(`¿Está seguro que desea revertir esta jornada a 'Especial'?\n\nEsto eliminará la autorización de horas extras y restaurará el estado original de la validación.`)) {
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

    marcacionesManualesState.isBolsaFija = (asist && (asist.tipo_programacion === 'BOLSA_FLEXIBLE' || asist.tipo_programacion === 'FLEXIBLE_BOLSA'));

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

    if (isValidTime(horaEntrada) && isValidTime(horaSalida)) {
        alertDiv.className = 'alert alert-info py-2 mb-3 mt-2';
        alertDiv.innerHTML = '<strong><i class="bi bi-shield-check"></i> Marcaciones Completas.</strong> Esta jornada cuenta con marcaciones biométricas válidas de Entrada y Salida. Si desea condonar un atraso o salida anticipada, utilice la función oficial de <strong>Perdonazo</strong>.';
        alertDiv.style.display = 'block';
        if (btnUnlock) btnUnlock.style.display = 'none';
    } else if (hasLockedMarks && (!isValidTime(horaEntrada) || !isValidTime(horaSalida))) {
        alertDiv.className = 'alert alert-warning py-2 mb-3 mt-2';
        if (isValidTime(horaEntrada)) {
            marcaHuerfanaMsj = `<strong><i class="bi bi-info-circle-fill"></i> Marca de ENTRADA detectada a las ${horaEntrada}.</strong> Ingrese únicamente la hora de SALIDA faltante.`;
        } else if (isValidTime(horaSalida)) {
            marcaHuerfanaMsj = `<strong><i class="bi bi-info-circle-fill"></i> Marca de SALIDA detectada a las ${horaSalida}.</strong> Ingrese únicamente la hora de ENTRADA faltante.`;
        }
        alertDiv.innerHTML = marcaHuerfanaMsj;
        alertDiv.style.display = 'block';
        if (btnUnlock) btnUnlock.style.display = 'none';
    } else {
        alertDiv.style.display = 'none';
        if (btnUnlock) btnUnlock.style.display = 'none';
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
 * Blindado: No permite sobreescribir si ya existen ambas marcas en el reloj.
 */
function unlockManualMarks() {
    if (typeof Swal !== 'undefined') {
        Swal.fire({
            icon: 'info',
            title: 'Marcaciones Biométricas Registradas',
            text: 'No se permite sobreescribir marcas biométricas válidas del reloj. Si desea justificar o perdonar un atraso o salida anticipada, utilice la función de Perdonazo.'
        });
    } else {
        alert("No se permite sobreescribir marcas biométricas válidas. Utilice el Perdonazo.");
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

    let nuevaEntrada = (!inputEntrada.disabled && inputEntrada.value) ? inputEntrada.value.trim() : null;
    let nuevaSalida = (!inputSalida.disabled && inputSalida.value) ? inputSalida.value.trim() : null;

    // Blindaje: si se ingresó entrada matutina y la salida es 00:00 por omisión o reset de campo, no enviar salida
    if (nuevaEntrada && nuevaSalida === "00:00" && nuevaEntrada >= "06:00" && nuevaEntrada <= "12:00") {
        nuevaSalida = null;
    }

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

    // Detectar si es cobertura (+2) en día hábil o jornada libre pura
    const empMatrix = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
    const asist = empMatrix ? empMatrix[dateStr] : null;
    const ja = asist ? asist.jornada_adicional : null;
    const empInfo = stateMarcacionesApp.data && stateMarcacionesApp.data.empleados ? stateMarcacionesApp.data.empleados.find(e => e.id == empId) : null;
    const isBolsa = Boolean(asist && asist._esBolsa) || Boolean(empInfo && (empInfo.tipo_programacion === 'BOLSA_FLEXIBLE' || empInfo.tipo_programacion === 'FLEXIBLE_BOLSA'));

    // REGLA DE NEGOCIO: La bifurcación a Horas Extras aplica EXCLUSIVAMENTE a Ciclos Inteligentes en días hábiles programados
    const esDiaHabilProgramado = Boolean(
        !isBolsa &&
        asist &&
        (asist.horas_teoricas || 0) > 0 &&
        asist.estado !== 'LIBRE' &&
        asist.estado !== 'FERIADO' &&
        ja &&
        (ja.origen === 'COBERTURA_TURNO' || (asist.observaciones && asist.observaciones.includes('(+2)')))
    );

    const alertBox = document.getElementById('val-alert-box');
    const promptText = document.getElementById('val-prompt-text');
    const extraInfo = document.getElementById('val-extra-info');
    const footerNote = document.getElementById('val-footer-note');

    if (ja && asist && (asist.horas_teoricas > 0 || asist.hora_entrada_real)) {
        const horasJa = ja.minutos_trabajados ? (Math.round(ja.minutos_trabajados / 60.0 * 10) / 10) : 0;
        if (alertBox) {
            alertBox.className = "alert alert-warning py-2 mb-3";
            alertBox.innerHTML = '<i class="bi bi-lightning-fill me-2 text-warning"></i> <strong>Cobertura de Turno (+2) Detectada</strong><br><small class="text-muted">El trabajador cubrió un turno adicional fuera de su jornada ordinaria.</small>';
        }
        if (promptText) {
            promptText.innerHTML = `¿Desea validar la <strong>cobertura adicional (${horasJa}h)</strong> como Jornada Especial?`;
        }
        if (extraInfo) {
            extraInfo.innerHTML = `
                <div class="mt-2 pt-2 border-top small">
                    <div><strong>Turno Base:</strong> <span class="badge bg-success-subtle text-success">${asist.estado || 'OK'}</span> (${asist.hora_entrada_real || '--:--'} - ${asist.hora_salida_real || '--:--'}) <span class="text-muted">(Se conserva intacto)</span></div>
                    <div><strong>Bloque Cobertura (+2):</strong> ${ja.hora_entrada || '--:--'} a ${ja.hora_salida || '--:--'} (${horasJa} hrs netas)</div>
                </div>
            `;
            extraInfo.classList.remove('d-none');
        }
        if (footerNote) {
            if (esDiaHabilProgramado) {
                footerNote.innerHTML = `
                    <div class="small text-muted mt-2 border-top pt-2">
                        <div>• <strong>Validar Jornada:</strong> Aprueba la cobertura como Jornada Especial (EXTRA) para pago plano/bono de faena. No genera horas extras al 50%.</div>
                        <div>• <strong>Validar como Horas Extras:</strong> Pasa la cobertura directamente al acumulador de Horas Extras al 50% legal.</div>
                    </div>
                `;
            } else {
                footerNote.innerHTML = `Al validar, la cobertura se aprueba como Jornada Especial (EXTRA). En días libres o festivos no genera horas extras al 50%. El turno base ordinario (${asist.estado || 'OK'}) permanecerá intacto.`;
            }
        }
    } else {
        if (alertBox) {
            alertBox.className = "alert alert-info py-2 mb-3";
            alertBox.innerHTML = '<i class="bi bi-info-circle-fill me-2"></i> Día libre o festivo detectado con marcaciones.';
        }
        if (promptText) {
            promptText.innerHTML = '¿Desea validar esta jornada como <strong>trabajada</strong>?';
        }
        if (extraInfo) {
            extraInfo.innerHTML = '';
            extraInfo.classList.add('d-none');
        }
        if (footerNote) {
            footerNote.innerHTML = 'Al validar, el estado cambiará a <strong>EXTRA</strong>.';
        }
    }

    const footer = marcacionesManualesState.validationModal.querySelector('.modal-footer');
    if (footer) {
        let btnHeHtml = '';
        if (esDiaHabilProgramado) {
            btnHeHtml = `
            <button type="button" class="btn btn-warning text-dark fw-bold px-3" onclick="validateJornada('APROBAR_COMO_HE')" title="Aprobar cobertura (+2) e inyectar al 50% en la bolsa de Horas Extras">
                ⏱️ Validar como Horas Extras
            </button>`;
        }
        footer.innerHTML = `
            <button type="button" class="btn btn-outline-danger me-auto" onclick="deleteManualJornada('${empId}', '${dateStr}')" title="Elimina las marcaciones manuales creadas en este día">
                <i class="bi bi-trash"></i> Eliminar Ingreso Manual
            </button>
            <button type="button" class="btn btn-secondary" onclick="closeValidationModal()">Cancelar</button>
            <button type="button" class="btn btn-danger" onclick="validateJornada('RECHAZAR')">
                ❌ Rechazar Jornada
            </button>
            ${btnHeHtml}
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
 * Llama al endpoint de validación (Aprobar, Aprobar como HE, o Rechazar)
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
            let msg = "Jornada validada exitosamente";
            if (accion === 'APROBAR_COMO_HE') {
                msg = "Cobertura (+2) validada exitosamente como Horas Extras al 50%";
            } else if (accion === 'APROBAR') {
                msg = "Jornada validada exitosamente como Jornada Especial";
            } else if (accion === 'RECHAZAR') {
                msg = "Jornada rechazada correctamente";
            }
            if (typeof showToast === 'function') showToast(msg, accion === 'RECHAZAR' ? "info" : "success");
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
    if (!await uiConfirm(`¿Está seguro que desea eliminar TODAS las marcaciones manuales ingresadas para el día ${window.formatFechaDDMMYYYY(fecha)}? Esta acción no se puede deshacer.`)) {
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

async function proceedToViajeLargo(customStartId, customRetId) {
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

        // Obtener viaje_largo existente de la respuesta o de la matriz
        const empMatrixJ = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
        const asistJ = empMatrixJ ? empMatrixJ[dateStr] : null;
        const vlExistente = data.viaje_existente || (asistJ ? (asistJ.viaje_largo || null) : null);

        const effectiveStartId = customStartId || (vlExistente ? vlExistente.log_entrada_id : null);
        const effectiveRetId = customRetId || (vlExistente ? vlExistente.log_salida_id : null);

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

        // Resetear toggle de retorno manual
        const checkRetManual = document.getElementById('vl-check-retorno-manual');
        const boxRetManual = document.getElementById('vl-box-retorno-manual');
        const contSelectRet = document.getElementById('vl-container-select-retorno');
        if (checkRetManual) checkRetManual.checked = false;
        if (boxRetManual) boxRetManual.style.display = 'none';
        if (contSelectRet) contSelectRet.style.display = 'block';
        
        // Reset campos retorno manual
        const inRetFecha = document.getElementById('vl-manual-retorno-fecha');
        const inRetHora = document.getElementById('vl-manual-retorno-hora');
        if (inRetFecha) inRetFecha.value = '';
        if (inRetHora) inRetHora.value = '';

        // Poblar Selector INICIO (#vl-select-inicio)
        const selectIni = document.getElementById('vl-select-inicio');
        selectIni.innerHTML = '';
        let htmlOptsIni = '';
        for (let i = 0; i < candInicio.length; i++) {
            const c = candInicio[i];
            const tagStr = c.consumida ? '(Turno Ordinario)' : '(Anomalía Libre)';
            const isSel = (effectiveStartId && effectiveStartId == c.id) ? 'selected' : (!effectiveStartId && i === 0 ? 'selected' : '');
            htmlOptsIni += `<option value="${c.id}" data-fecha="${c.fecha}" data-fecha-hora="${c.fecha_hora}" ${isSel}>${c.fecha_hora} — ${c.tipo} ${tagStr}</option>`;
        }
        selectIni.innerHTML = htmlOptsIni;

        // Poblar Selector RETORNO (#vl-select-retorno) dinámicamente según Inicio seleccionado
        window.updateViajeLargoCandidatosRetorno(effectiveRetId);
        
        // Si no hay candidatos de retorno disponibles, activar retorno manual automáticamente
        if (candRetorno.length === 0 || selectIni.options.length === 0) {
            if (checkRetManual) {
                checkRetManual.checked = true;
                window.toggleViajeLargoRetornoManual();
            }
        }
        
        window.onViajeLargoDestinoChange();

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

window.toggleViajeLargoRetornoManual = function() {
    const isManual = document.getElementById('vl-check-retorno-manual')?.checked;
    const boxRetManual = document.getElementById('vl-box-retorno-manual');
    const contSelectRet = document.getElementById('vl-container-select-retorno');
    const inRetFecha = document.getElementById('vl-manual-retorno-fecha');
    const inRetHora = document.getElementById('vl-manual-retorno-hora');
    const fechaIni = document.getElementById('vl-fecha-ini')?.value;

    if (isManual) {
        if (boxRetManual) boxRetManual.style.display = 'block';
        if (contSelectRet) contSelectRet.style.display = 'none';
        if (inRetFecha && !inRetFecha.value && fechaIni) {
            // Sugerir fecha fin como día siguiente o subsiguiente
            const d = new Date(fechaIni + 'T00:00:00');
            d.setDate(d.getDate() + 2);
            inRetFecha.value = d.toISOString().substring(0, 10);
        }
        if (inRetHora && !inRetHora.value) {
            inRetHora.value = '01:45:00';
        }
    } else {
        if (boxRetManual) boxRetManual.style.display = 'none';
        if (contSelectRet) contSelectRet.style.display = 'block';
    }
    window.updateViajeLargoCalculos();
};

async function proceedToViajeLargoConSugerencia(empId, dateStr, startLogId, retLogId) {
    marcacionesManualesState.currentEmpId = empId;
    marcacionesManualesState.currentDate = dateStr;
    const empMatrix = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
    const info = empMatrix && empMatrix.info ? empMatrix.info : null;
    marcacionesManualesState.currentEmpNombre = info ? `${info.nombre} ${info.apellido_paterno}` : `Empleado ${empId}`;
    await proceedToViajeLargo(startLogId, retLogId);
}
window.proceedToViajeLargoConSugerencia = proceedToViajeLargoConSugerencia;

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
            const tagStr = c.tag || (c.consumida ? '(Consumida)' : '(Anomalía Libre)');
            const isSel = (preselectedRetId && preselectedRetId == c.id) ? 'selected' : (!preselectedRetId && (c.recomendado || i === 0) ? 'selected' : '');
            const starIcon = c.recomendado ? '⭐ ' : '';
            htmlOptsRet += `<option value="${c.id}" data-fecha="${c.fecha}" data-fecha-hora="${c.fecha_hora}" data-horas="${diffHours}" ${isSel}>${starIcon}${c.fecha_hora} — ${c.tipo} ${tagStr} (${diffHours}h transcurridas)</option>`;
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
    const isManual = document.getElementById('vl-check-retorno-manual')?.checked;
    let totalReloj = 0;

    const selectIni = document.getElementById('vl-select-inicio');
    const optIni = selectIni && selectIni.selectedIndex >= 0 ? selectIni.options[selectIni.selectedIndex] : null;
    const fhIniStr = optIni ? optIni.getAttribute('data-fecha-hora') : null;

    if (isManual) {
        const inRetFecha = document.getElementById('vl-manual-retorno-fecha')?.value;
        const inRetHora = document.getElementById('vl-manual-retorno-hora')?.value;
        if (fhIniStr && inRetFecha && inRetHora) {
            const dtIni = new Date(fhIniStr.replace(' ', 'T'));
            const dtRet = new Date(`${inRetFecha}T${inRetHora.length === 5 ? inRetHora + ':00' : inRetHora}`);
            if (dtRet > dtIni) {
                totalReloj = (dtRet - dtIni) / (1000 * 3600);
            }
        }
    } else {
        const selectRet = document.getElementById('vl-select-retorno');
        if (selectRet && selectRet.selectedIndex >= 0) {
            const opt = selectRet.options[selectRet.selectedIndex];
            if (opt) {
                totalReloj = parseFloat(opt.getAttribute('data-horas')) || 0;
            }
        }
    }

    document.getElementById('vl-txt-duracion').innerText = `${totalReloj.toFixed(1)}h reloj`;

    const elManejo = document.getElementById('vl-hrs-manejo');
    const elDescanso = document.getElementById('vl-hrs-descanso');
    const elReconocidas = document.getElementById('vl-hrs-reconocidas');

    let hManejo = parseFloat(elManejo.value);
    let hDescanso = parseFloat(elDescanso.value);

    if (sourceField === 'descanso') {
        if (elDescanso.value.trim() === '') {
            // Si el usuario vacía el descanso, el manejo vuelve al 100% de las horas reloj
            hManejo = totalReloj;
            elManejo.value = hManejo.toFixed(1);
            elReconocidas.value = hManejo.toFixed(1);
        } else if (!isNaN(hDescanso) && totalReloj >= 0) {
            hManejo = Math.max(0, totalReloj - hDescanso);
            elManejo.value = hManejo.toFixed(1);
            elReconocidas.value = hManejo.toFixed(1);
        }
    } else if (sourceField === 'manejo') {
        if (elManejo.value.trim() === '') {
            // Si el usuario vacía el manejo, el descanso absorbe el total reloj
            hDescanso = totalReloj;
            elDescanso.value = hDescanso.toFixed(1);
            elReconocidas.value = '0.0';
        } else if (!isNaN(hManejo) && totalReloj >= 0) {
            hDescanso = Math.max(0, totalReloj - hManejo);
            elDescanso.value = hDescanso.toFixed(1);
            elReconocidas.value = hManejo.toFixed(1);
        }
    } else if (sourceField === 'reconocidas') {
        // El usuario ajusta directamente la acreditación especial a la bolsa
    } else {
        // Inicializar por defecto con el totalReloj SOLO si no hay un valor ingresado/cargado previamente
        if (!elManejo.value || isNaN(parseFloat(elManejo.value))) {
            elManejo.value = totalReloj.toFixed(1);
            elDescanso.value = '0.0';
            elReconocidas.value = totalReloj.toFixed(1);
        }
    }

    // Actualizar sugerencias y alertas de ruta
    window.onViajeLargoDestinoChange();
    if (typeof window.evaluarAlertasContextualesViajeLargo === 'function') {
        window.evaluarAlertasContextualesViajeLargo();
    }
}

// ── CATÁLOGO DE DISTANCIAS VIALES DESDE SAN FERNANDO (CHILE) ──────────────
const DISTANCIAS_CHILE_SAN_FERNANDO = {
    "arica": { nombre: "Arica", km_ida: 2190, vel_prom: 65, horas_descarga: 4 },
    "iquique": { nombre: "Iquique", km_ida: 1900, vel_prom: 65, horas_descarga: 4 },
    "antofagasta": { nombre: "Antofagasta", km_ida: 1500, vel_prom: 68, horas_descarga: 4 },
    "calama": { nombre: "Calama", km_ida: 1680, vel_prom: 68, horas_descarga: 4 },
    "copiapo": { nombre: "Copiapó", km_ida: 940, vel_prom: 70, horas_descarga: 3 },
    "vallenar": { nombre: "Vallenar", km_ida: 790, vel_prom: 70, horas_descarga: 3 },
    "la serena": { nombre: "La Serena / Coquimbo", km_ida: 610, vel_prom: 70, horas_descarga: 3 },
    "coquimbo": { nombre: "Coquimbo / La Serena", km_ida: 610, vel_prom: 70, horas_descarga: 3 },
    "ovalle": { nombre: "Ovalle", km_ida: 550, vel_prom: 68, horas_descarga: 2.5 },
    "illapel": { nombre: "Illapel", km_ida: 430, vel_prom: 68, horas_descarga: 2 },
    "los vilos": { nombre: "Los Vilos", km_ida: 360, vel_prom: 70, horas_descarga: 2 },
    "valparaiso": { nombre: "Valparaíso / Viña del Mar", km_ida: 250, vel_prom: 68, horas_descarga: 2 },
    "vina del mar": { nombre: "Viña del Mar / Valparaíso", km_ida: 250, vel_prom: 68, horas_descarga: 2 },
    "san antonio": { nombre: "San Antonio", km_ida: 160, vel_prom: 65, horas_descarga: 2 },
    "santiago": { nombre: "Santiago (RM)", km_ida: 140, vel_prom: 65, horas_descarga: 2 },
    "rancagua": { nombre: "Rancagua", km_ida: 55, vel_prom: 60, horas_descarga: 1.5 },
    "curico": { nombre: "Curicó", km_ida: 55, vel_prom: 65, horas_descarga: 1.5 },
    "talca": { nombre: "Talca", km_ida: 115, vel_prom: 70, horas_descarga: 2 },
    "linares": { nombre: "Linares", km_ida: 165, vel_prom: 70, horas_descarga: 2 },
    "parral": { nombre: "Parral", km_ida: 210, vel_prom: 70, horas_descarga: 2 },
    "chillan": { nombre: "Chillán", km_ida: 270, vel_prom: 70, horas_descarga: 2 },
    "concepcion": { nombre: "Concepción / Talcahuano", km_ida: 370, vel_prom: 70, horas_descarga: 3 },
    "talcahuano": { nombre: "Talcahuano / Concepción", km_ida: 370, vel_prom: 70, horas_descarga: 3 },
    "los angeles": { nombre: "Los Ángeles", km_ida: 380, vel_prom: 70, horas_descarga: 2.5 },
    "temuco": { nombre: "Temuco", km_ida: 540, vel_prom: 70, horas_descarga: 3 },
    "villarrica": { nombre: "Villarrica / Pucón", km_ida: 620, vel_prom: 68, horas_descarga: 2.5 },
    "pucon": { nombre: "Pucón / Villarrica", km_ida: 620, vel_prom: 68, horas_descarga: 2.5 },
    "valdivia": { nombre: "Valdivia", km_ida: 710, vel_prom: 70, horas_descarga: 3 },
    "osorno": { nombre: "Osorno", km_ida: 790, vel_prom: 70, horas_descarga: 3 },
    "puerto montt": { nombre: "Puerto Montt / Pto. Varas", km_ida: 890, vel_prom: 70, horas_descarga: 3 },
    "puerto varas": { nombre: "Puerto Varas / Pto. Montt", km_ida: 890, vel_prom: 70, horas_descarga: 3 },
    "castro": { nombre: "Castro (Chiloé)", km_ida: 980, vel_prom: 65, horas_descarga: 4 },
    "ancud": { nombre: "Ancud (Chiloé)", km_ida: 950, vel_prom: 65, horas_descarga: 4 },
    "coyhaique": { nombre: "Coyhaique", km_ida: 1550, vel_prom: 60, horas_descarga: 5 },
    "punta arenas": { nombre: "Punta Arenas", km_ida: 2850, vel_prom: 65, horas_descarga: 6 }
};

window.buscarRutaInfo = function(destinoRaw) {
    if (!destinoRaw) return null;
    const cleanStr = String(destinoRaw).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
    for (const [k, v] of Object.entries(DISTANCIAS_CHILE_SAN_FERNANDO)) {
        const kClean = k.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        if (cleanStr.includes(kClean) || kClean.includes(cleanStr)) {
            return v;
        }
    }
    return null;
};

window.onViajeLargoDestinoChange = function() {
    const inputDest = document.getElementById('vl-ciudad-destino');
    const cardSug = document.getElementById('vl-sugerencia-ruta-card');
    const txtDist = document.getElementById('vl-ruta-distancia-txt');
    const txtEst = document.getElementById('vl-ruta-estimado-txt');
    if (!inputDest || !cardSug) return;

    const val = inputDest.value.trim();
    if (!val) {
        cardSug.style.display = 'none';
        return;
    }

    const selectRet = document.getElementById('vl-select-retorno');
    const optRet = selectRet && selectRet.selectedIndex >= 0 ? selectRet.options[selectRet.selectedIndex] : null;
    const totalReloj = optRet ? (parseFloat(optRet.getAttribute('data-horas')) || 0) : 0;

    const ruta = window.buscarRutaInfo(val);
    if (ruta) {
        const kmTotal = ruta.km_ida * 2;
        const horasManejoPuras = (kmTotal / ruta.vel_prom);
        let horasManejoSugeridas = Math.round((horasManejoPuras + (ruta.horas_descarga || 2)) * 2) / 2;
        
        if (totalReloj > 0 && horasManejoSugeridas > totalReloj) {
            horasManejoSugeridas = Math.min(totalReloj, Math.max(8.0, Math.round((totalReloj * 0.45) * 2) / 2));
        }
        
        const horasDescansoSugeridas = totalReloj > 0 ? Math.max(0, Math.round((totalReloj - horasManejoSugeridas) * 2) / 2) : 0;

        cardSug.style.display = 'block';
        txtDist.innerHTML = `<i class="bi bi-geo-alt-fill me-1"></i> San Fernando ➔ ${ruta.nombre}: <strong>~${ruta.km_ida.toLocaleString()} km</strong> (Ida y Vuelta: <strong>~${kmTotal.toLocaleString()} km</strong>)`;
        txtEst.innerHTML = `⏱️ Estimado Transporte: <strong>${horasManejoSugeridas.toFixed(1)}h</strong> manejo / servicio (${ruta.vel_prom} km/h) &nbsp;|&nbsp; 🛌 <strong>${horasDescansoSugeridas.toFixed(1)}h</strong> descanso sugerido`;
        
        window._vl_sug_manejo = horasManejoSugeridas;
        window._vl_sug_descanso = horasDescansoSugeridas;
    } else {
        if (totalReloj > 0) {
            const hManejoProp = Math.round((totalReloj * 0.45) * 2) / 2;
            const hDescProp = Math.max(0, Math.round((totalReloj - hManejoProp) * 2) / 2);
            cardSug.style.display = 'block';
            txtDist.innerHTML = `<i class="bi bi-geo-alt-fill me-1"></i> San Fernando ➔ ${val} (Destino Personalizado)`;
            txtEst.innerHTML = `⏱️ Proporción Estándar Transporte: <strong>${hManejoProp.toFixed(1)}h</strong> manejo (~45%) &nbsp;|&nbsp; 🛌 <strong>${hDescProp.toFixed(1)}h</strong> descanso (~55%)`;
            window._vl_sug_manejo = hManejoProp;
            window._vl_sug_descanso = hDescProp;
        } else {
            cardSug.style.display = 'none';
        }
    }
    window.evaluarAlertasContextualesViajeLargo();
};

window.evaluarAlertasContextualesViajeLargo = function() {
    const cardAlerta = document.getElementById('vl-alerta-contextual');
    const icoAlerta = document.getElementById('vl-alerta-icono');
    const titAlerta = document.getElementById('vl-alerta-titulo');
    const cpoAlerta = document.getElementById('vl-alerta-cuerpo');
    if (!cardAlerta || !icoAlerta || !titAlerta || !cpoAlerta) return;

    const selectRet = document.getElementById('vl-select-retorno');
    const optRet = selectRet && selectRet.selectedIndex >= 0 ? selectRet.options[selectRet.selectedIndex] : null;
    const totalReloj = optRet ? (parseFloat(optRet.getAttribute('data-horas')) || 0) : 0;

    const elManejo = document.getElementById('vl-hrs-manejo');
    const elDescanso = document.getElementById('vl-hrs-descanso');
    const hManejo = elManejo ? (parseFloat(elManejo.value) || 0) : 0;
    const hDescanso = elDescanso ? (parseFloat(elDescanso.value) || 0) : 0;

    const inputDest = document.getElementById('vl-ciudad-destino');
    const destVal = inputDest ? inputDest.value.trim() : '';
    const ruta = window.buscarRutaInfo(destVal);

    if (totalReloj >= 20 && hDescanso >= 0.65 * totalReloj) {
        const pct = Math.round((hDescanso / totalReloj) * 100);
        cardAlerta.style.display = 'block';
        cardAlerta.style.background = '#fffbeb';
        cardAlerta.style.borderColor = '#fde68a';
        icoAlerta.innerHTML = `<i class="bi bi-exclamation-triangle-fill text-warning"></i>`;
        titAlerta.className = 'fw-bold text-warning-emphasis';
        titAlerta.innerText = `Aviso: Tiempo Detenido Elevado (${pct}% del viaje)`;
        cpoAlerta.innerText = `Para los kilómetros de esta ruta, el camión estuvo detenido ${hDescanso.toFixed(1)}h de las ${totalReloj.toFixed(1)}h reloj. Posibles causas: Espera prolongada en andén de cliente, pernoctaciones en cabina o ruta con entregas intermedias.`;
    } else if (totalReloj >= 24 && hDescanso < (totalReloj / 24.0) * 7.5) {
        const reqMin = ((totalReloj / 24.0) * 8.0).toFixed(1);
        cardAlerta.style.display = 'block';
        cardAlerta.style.background = '#fef2f2';
        cardAlerta.style.borderColor = '#fecaca';
        icoAlerta.innerHTML = `<i class="bi bi-slash-circle-fill text-danger"></i>`;
        titAlerta.className = 'fw-bold text-danger';
        titAlerta.innerText = `Alerta Legal: Descanso Reducido`;
        cpoAlerta.innerText = `Por normativa laboral, un viaje de ${totalReloj.toFixed(1)}h requiere un descanso acumulado mínimo de al menos ${reqMin}h (8h por cada 24h). Verifique registros de descanso antes del cierre.`;
    } else if (ruta && hManejo > 0) {
        const kmTotal = ruta.km_ida * 2;
        const vel = kmTotal / hManejo;
        if (vel > 85) {
            cardAlerta.style.display = 'block';
            cardAlerta.style.background = '#eff6ff';
            cardAlerta.style.borderColor = '#bfdbfe';
            icoAlerta.innerHTML = `<i class="bi bi-info-circle-fill text-primary"></i>`;
            titAlerta.className = 'fw-bold text-primary';
            titAlerta.innerText = `Información: Velocidad Promedio Elevada (~${Math.round(vel)} km/h)`;
            cpoAlerta.innerText = `La velocidad calculada para los ${kmTotal} km supera el promedio habitual de camiones de carga pesada con acoplado.`;
        } else {
            cardAlerta.style.display = 'none';
        }
    } else {
        cardAlerta.style.display = 'none';
    }
};

window.aplicarSugerenciaRuta = function() {
    if (window._vl_sug_manejo != null && window._vl_sug_descanso != null) {
        document.getElementById('vl-hrs-manejo').value = window._vl_sug_manejo.toFixed(1);
        document.getElementById('vl-hrs-descanso').value = window._vl_sug_descanso.toFixed(1);
        document.getElementById('vl-hrs-reconocidas').value = window._vl_sug_manejo.toFixed(1);

        // Auto-completar observaciones técnicas
        const inputDest = document.getElementById('vl-ciudad-destino');
        const destVal = inputDest ? inputDest.value.trim() : 'Destino';
        const ruta = window.buscarRutaInfo(destVal);
        const nomRuta = ruta ? ruta.nombre : destVal;
        const kmStr = ruta ? `~${(ruta.km_ida * 2).toLocaleString()} km I/V` : '';
        const obsEl = document.getElementById('vl-observaciones');
        if (obsEl && !obsEl.value) {
            obsEl.value = `Ruta San Fernando ➔ ${nomRuta} (${kmStr}). Estimación de ruta: ~${window._vl_sug_manejo.toFixed(1)}h conducción/servicio + ~${window._vl_sug_descanso.toFixed(1)}h descanso/esperas en ruta.`;
        }
        window.evaluarAlertasContextualesViajeLargo();
    }
};

async function submitViajeLargo() {
    const empId = parseInt(document.getElementById('vl-emp-id').value);
    const fechaIni = document.getElementById('vl-fecha-ini').value;
    const logEntradaId = parseInt(document.getElementById('vl-log-entrada-id').value);

    const isManualRetorno = document.getElementById('vl-check-retorno-manual')?.checked;
    let fechaRetornoManual = null;
    let horaRetornoManual = null;

    let logSalidaId = null;
    let fechaFin = fechaIni;

    if (isManualRetorno) {
        fechaRetornoManual = document.getElementById('vl-manual-retorno-fecha')?.value;
        horaRetornoManual = document.getElementById('vl-manual-retorno-hora')?.value;
        if (!fechaRetornoManual || !horaRetornoManual) {
            alert("Por favor ingrese la Fecha y Hora del Retorno Manual.");
            return;
        }
        fechaFin = fechaRetornoManual;
        logSalidaId = null;
    } else {
        const selectRet = document.getElementById('vl-select-retorno');
        const optRet = (selectRet && selectRet.selectedIndex >= 0) ? selectRet.options[selectRet.selectedIndex] : null;
        logSalidaId = selectRet ? parseInt(selectRet.value) : null;
        const optRetFh = optRet ? optRet.getAttribute('data-fecha-hora') : null;
        fechaFin = (optRet && optRet.getAttribute('data-fecha')) ? optRet.getAttribute('data-fecha') : (optRetFh ? optRetFh.substring(0, 10) : fechaIni);
        
        if (!logSalidaId) {
            alert("Por favor seleccione una marcación de retorno o active 'El chofer olvidó marcar retorno'.");
            return;
        }
    }

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
        fecha_retorno_manual: fechaRetornoManual,
        hora_retorno_manual: horaRetornoManual,
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

// =========================================================================
// MARCACIÓN DINÁMICA 180 HORAS (ART. 25 BIS DT) - LIBRETA DIGITAL
// =========================================================================

let m180_slots = new Array(96).fill(0);
let m180_brush_mode = false;  // Modo Pincel (marcar al pasar el cursor)
let m180_grid_initialized = false;
let m180_drag = null;         // { act, mode, startSlot, curSlot, track, pointerId }
let m180_brush_stroke = false;
let m180_history = [];
let m180_dirty = false;
let m180_force_close = false;
let m180_prev_keys = new Set();
let m180_locked = false;      // día cerrado: solo lectura

const M180_ACTIVIDADES = {
    1: { id: 1, name: 'Conducción', short: 'COND', color: '#059669', soft: '#ecfdf5', ink: '#065f46' },
    2: { id: 2, name: 'Espera', short: 'ESP', color: '#d97706', soft: '#fffbeb', ink: '#92400e' },
    3: { id: 3, name: 'Labores auxiliares', short: 'AUX', color: '#4f46e5', soft: '#eef2ff', ink: '#3730a3' },
    4: { id: 4, name: 'Descanso', short: 'DESC', color: '#0284c7', soft: '#f0f9ff', ink: '#075985' }
};

function formatMinToHHMM(minutos) {
    const mins = Math.max(0, Math.round(minutos));
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

function formatSlotToHHMM(slot) {
    if (slot >= 96) return '24:00';
    const h = Math.floor(slot / 4);
    const m = (slot % 4) * 15;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

function m180Runs(act) {
    const runs = [];
    let start = -1;
    for (let s = 0; s <= 96; s++) {
        const on = s < 96 && m180_slots[s] === act;
        if (on && start < 0) start = s;
        if (!on && start >= 0) { runs.push([start, s]); start = -1; }
    }
    return runs;
}

function m180CurrentKeys() {
    const keys = new Set();
    [1, 2, 3, 4].forEach(act => m180Runs(act).forEach(([a, b]) => keys.add(`${act}:${a}:${b}`)));
    return keys;
}

function initLibreta180hGrid() {
    const ruler = document.getElementById('m180-ruler');
    const lanes = document.getElementById('m180-lanes');
    if (!ruler || !lanes) return;

    let rulerHtml = '';
    for (let h = 0; h < 24; h++) {
        rulerHtml += `<span class="m180-ruler-h">${String(h).padStart(2, '0')}<small>:00</small></span>`;
    }
    ruler.innerHTML = rulerHtml;

    lanes.innerHTML = [1, 2, 3, 4].map(actId => {
        const c = M180_ACTIVIDADES[actId];
        return `<div class="m180-lane" data-act="${actId}" style="--c:${c.color}; --soft:${c.soft}; --ink:${c.ink};">
            <div class="m180-lane-label"><span class="m180-lane-dot"></span><span>${actId}. ${c.name}</span></div>
            <div class="m180-track" data-act="${actId}">
                <div class="m180-blocks"></div>
                <div class="m180-hover"></div>
                <div class="m180-ghost"><span></span></div>
            </div>
            <div class="m180-lane-total" id="m180-tot-act-${actId}">00:00</div>
        </div>`;
    }).join('');

    lanes.querySelectorAll('.m180-track').forEach(setupLibretaTrack);

    // Ctrl+Z deshace mientras la libreta está abierta
    document.addEventListener('keydown', (e) => {
        const modalEl = document.getElementById('modalMarcacion180h');
        if (!modalEl || !modalEl.classList.contains('show')) return;
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
            e.preventDefault();
            libreta180hUndo();
        }
    });

    m180_grid_initialized = true;
}

function m180SlotFromEvent(track, e) {
    const rect = track.getBoundingClientRect();
    const x = Math.min(Math.max(e.clientX - rect.left, 0), rect.width - 0.01);
    return Math.floor((x / rect.width) * 96);
}

function m180SetReadout(txt) {
    const el = document.getElementById('m180-readout');
    if (el) el.textContent = txt || 'Arrastre sobre una fila para marcar un rango · clic sobre un tramo marcado para quitarlo';
}

function m180RenderGhost() {
    const d = m180_drag;
    if (!d) return;
    const a = Math.min(d.startSlot, d.curSlot);
    const b = Math.max(d.startSlot, d.curSlot) + 1;
    const g = d.track.querySelector('.m180-ghost');
    g.style.left = `${(a / 96) * 100}%`;
    g.style.width = `${((b - a) / 96) * 100}%`;
    g.classList.toggle('is-erase', d.mode === 'erase');
    g.classList.add('is-on');
    g.firstElementChild.textContent = `${formatSlotToHHMM(a)} – ${formatSlotToHHMM(b)} · ${formatMinToHHMM((b - a) * 15)}`;
    m180SetReadout(`${d.mode === 'erase' ? 'Quitando' : 'Marcando'} ${M180_ACTIVIDADES[d.act].name.toLowerCase()}: ${formatSlotToHHMM(a)} – ${formatSlotToHHMM(b)} (${formatMinToHHMM((b - a) * 15)})`);
}

function m180ClearGhost() {
    document.querySelectorAll('#m180-lanes .m180-ghost').forEach(g => g.classList.remove('is-on'));
}

function m180PushHistory() {
    m180_history.push(m180_slots.slice());
    if (m180_history.length > 60) m180_history.shift();
    m180_dirty = true;
    m180UpdateUndoBtn();
}

function m180UpdateUndoBtn() {
    const btn = document.getElementById('m180-btn-undo');
    if (btn) btn.disabled = m180_history.length === 0;
}

function m180ApplyRange(act, a, bExcl, mode) {
    for (let s = a; s < bExcl; s++) {
        if (mode === 'erase') {
            if (m180_slots[s] === act) m180_slots[s] = 0;
        } else {
            m180_slots[s] = act;
        }
    }
}

function setupLibretaTrack(track) {
    const act = parseInt(track.dataset.act);
    const scroller = document.getElementById('m180-grid-scroll');

    track.addEventListener('pointerdown', (e) => {
        if (m180_locked) return;
        if (e.button !== undefined && e.button !== 0) return;
        const slot = m180SlotFromEvent(track, e);
        const mode = m180_slots[slot] === act ? 'erase' : 'paint';
        m180_drag = { act, mode, startSlot: slot, curSlot: slot, track, pointerId: e.pointerId };
        try { track.setPointerCapture(e.pointerId); } catch (_) { /* noop */ }
        m180RenderGhost();
    });

    track.addEventListener('pointermove', (e) => {
        const slot = m180SlotFromEvent(track, e);
        const hov = track.querySelector('.m180-hover');
        hov.style.left = `${(slot / 96) * 100}%`;
        hov.style.width = `${100 / 96}%`;
        hov.classList.add('is-on');

        if (m180_drag && m180_drag.track === track) {
            if (slot !== m180_drag.curSlot) {
                m180_drag.curSlot = slot;
                m180RenderGhost();
            }
            // Auto-scroll horizontal al acercarse a los bordes durante el arrastre
            if (scroller) {
                const r = scroller.getBoundingClientRect();
                if (e.clientX > r.right - 48) scroller.scrollLeft += 14;
                else if (e.clientX < r.left + 48 + 170) scroller.scrollLeft -= 14;
            }
            return;
        }

        if (m180_brush_mode && !m180_locked && e.pointerType !== 'touch') {
            // Modo pincel: pinta el tramo bajo el cursor sin necesidad de presionar
            if (m180_slots[slot] !== act) {
                if (!m180_brush_stroke) { m180PushHistory(); m180_brush_stroke = true; }
                m180_slots[slot] = act;
                m180RenderBlocks();
            }
            m180SetReadout(`${formatSlotToHHMM(slot)} – ${formatSlotToHHMM(slot + 1)} · ${M180_ACTIVIDADES[act].name}`);
        } else {
            const actLeida = m180_slots[slot];
            m180SetReadout(`${formatSlotToHHMM(slot)} – ${formatSlotToHHMM(slot + 1)}` + (m180_locked && actLeida ? ` · ${M180_ACTIVIDADES[actLeida].name}` : ''));
        }
    });

    track.addEventListener('pointerleave', () => {
        track.querySelector('.m180-hover').classList.remove('is-on');
        m180_brush_stroke = false;
        if (!m180_drag) m180SetReadout('');
    });

    const finish = (commit) => {
        const d = m180_drag;
        if (!d || d.track !== track) return;
        m180_drag = null;
        try { track.releasePointerCapture(d.pointerId); } catch (_) { /* noop */ }
        m180ClearGhost();
        m180SetReadout('');
        if (!commit) return;
        const a = Math.min(d.startSlot, d.curSlot);
        const b = Math.max(d.startSlot, d.curSlot) + 1;
        m180PushHistory();
        m180ApplyRange(d.act, a, b, d.mode);
        m180RenderBlocks();
    };
    track.addEventListener('pointerup', () => finish(true));
    track.addEventListener('pointercancel', () => finish(false));
}

function m180RenderBlocks() {
    [1, 2, 3, 4].forEach(act => {
        const c = M180_ACTIVIDADES[act];
        const host = document.querySelector(`.m180-track[data-act="${act}"] .m180-blocks`);
        if (!host) return;
        host.innerHTML = m180Runs(act).map(([a, b]) => {
            const isNew = !m180_prev_keys.has(`${act}:${a}:${b}`);
            const dur = formatMinToHHMM((b - a) * 15);
            return `<div class="m180-block${isNew ? ' is-new' : ''}" style="left:${(a / 96) * 100}%; width:${((b - a) / 96) * 100}%;" title="${formatSlotToHHMM(a)} – ${formatSlotToHHMM(b)} · ${c.name} (${dur})"><b>${c.short}</b><i>${dur}</i></div>`;
        }).join('');
    });
    m180_prev_keys = m180CurrentKeys();

    // Barra resumen de 24h (todas las actividades en una sola línea)
    const ov = document.getElementById('m180-overview');
    if (ov) {
        let html = '';
        let s = 0;
        while (s < 96) {
            const act = m180_slots[s];
            let e = s;
            while (e < 96 && m180_slots[e] === act) e++;
            html += `<span class="${act ? '' : 'is-empty'}" style="width:${((e - s) / 96) * 100}%; ${act ? `background:${M180_ACTIVIDADES[act].color};` : ''}"></span>`;
            s = e;
        }
        ov.innerHTML = html;
    }
    recalcLibretaTotales();
}

function refreshAllSlotsVisuals() {
    m180_prev_keys = m180CurrentKeys(); // carga inicial: sin animación de entrada masiva
    m180RenderBlocks();
}

function toggleLibretaBrushMode(enabled) {
    m180_brush_mode = Boolean(enabled);
    const chk = document.getElementById('m180-toggle-brush');
    if (chk) chk.checked = m180_brush_mode;
    const container = document.getElementById('m180-grid-scroll');
    if (container) container.classList.toggle('is-brush', m180_brush_mode);
}

function setLibretaActividad(actId) {
    /* compat: la marcación es directa por fila, no hay actividad "seleccionada" */
}

function libreta180hUndo() {
    if (m180_locked || !m180_history.length) return;
    m180_slots = m180_history.pop();
    m180UpdateUndoBtn();
    m180RenderBlocks();
}

function libreta180hAutoDescanso() {
    if (m180_locked) return;
    const empty = m180_slots.filter(s => s === 0).length;
    if (!empty) return;
    m180PushHistory();
    for (let s = 0; s < 96; s++) {
        if (m180_slots[s] === 0) m180_slots[s] = 4;
    }
    m180RenderBlocks();
    if (typeof showToast === 'function') {
        showToast(`Se rellenaron ${empty} tramos (${(empty * 15) / 60} hrs) como Descanso`, "info");
    }
}

function limpiarGrilla180h() {
    if (m180_locked || !m180_slots.some(s => s !== 0)) return;
    m180PushHistory();
    m180_slots.fill(0);
    m180RenderBlocks();
    if (typeof showToast === 'function') {
        showToast("Grilla reiniciada · Ctrl+Z para deshacer", "info");
    }
}

function recalcLibretaTotales() {
    let cntCond = 0, cntEsp = 0, cntAux = 0, cntDesc = 0;
    let maxConsecCond = 0, curConsecCond = 0;

    for (let s = 0; s < 96; s++) {
        const act = m180_slots[s];
        if (act === 1) {
            cntCond++;
            curConsecCond++;
            if (curConsecCond > maxConsecCond) maxConsecCond = curConsecCond;
        } else {
            curConsecCond = 0;
            if (act === 2) cntEsp++;
            else if (act === 3) cntAux++;
            else if (act === 4) cntDesc++;
        }
    }

    const minCond = cntCond * 15;
    const minEsp = cntEsp * 15;
    const minAux = cntAux * 15;
    const minDesc = cntDesc * 15;
    const minEfec = minCond + minAux;
    const minTot = minCond + minEsp + minAux + minDesc;

    const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    setTxt('m180-tot-act-1', formatMinToHHMM(minCond));
    setTxt('m180-tot-act-2', formatMinToHHMM(minEsp));
    setTxt('m180-tot-act-3', formatMinToHHMM(minAux));
    setTxt('m180-tot-act-4', formatMinToHHMM(minDesc));

    const hrs = ' <span class="fs-6 fw-normal text-muted">hrs</span>';
    const elEfectiva = document.getElementById('m180-res-jornada-efectiva');
    if (elEfectiva) elEfectiva.innerHTML = formatMinToHHMM(minEfec) + hrs;
    const elEspera = document.getElementById('m180-res-horas-espera');
    if (elEspera) elEspera.innerHTML = formatMinToHHMM(minEsp) + hrs;
    const elDesc = document.getElementById('m180-res-horas-descanso');
    if (elDesc) elDesc.innerHTML = formatMinToHHMM(minDesc) + hrs;

    setTxt('m180-tot-acumulado-dia', `${formatMinToHHMM(minTot)} / 24h`);
    const prog = document.getElementById('m180-progress-fill');
    if (prog) prog.style.transform = `scaleX(${Math.min(minTot / 1440, 1)})`;

    const msgCuadre = document.getElementById('m180-msg-cuadre');
    if (msgCuadre) {
        if (minTot === 1440) {
            msgCuadre.className = 'badge bg-success-subtle text-success border border-success-subtle px-2 py-1';
            msgCuadre.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i> Cuadre completo: 24:00 hrs';
        } else if (minTot < 1440) {
            const faltan = 1440 - minTot;
            msgCuadre.className = 'badge bg-warning-subtle text-warning-emphasis border border-warning-subtle px-2 py-1';
            msgCuadre.innerHTML = `<i class="bi bi-exclamation-triangle-fill me-1"></i> Faltan ${formatMinToHHMM(faltan)} hrs por registrar (${faltan / 15} tramos)`;
        } else {
            msgCuadre.className = 'badge bg-danger text-white px-2 py-1';
            msgCuadre.innerHTML = 'Exceso de tramos (> 24:00 hrs)';
        }
    }

    const alertaFatiga = document.getElementById('m180-alerta-fatiga');
    if (alertaFatiga) {
        if (maxConsecCond > 20) {
            alertaFatiga.classList.remove('d-none');
            alertaFatiga.innerHTML = `<i class="bi bi-exclamation-triangle-fill me-1"></i> Alerta Art. 25 bis: conducción continua de ${(maxConsecCond * 15 / 60).toFixed(2)} hrs (límite legal: 5.0 hrs continuas sin descanso).`;
        } else {
            alertaFatiga.classList.add('d-none');
        }
    }
}

function m180SetLocked(locked) {
    m180_locked = Boolean(locked);
    const modalEl = document.getElementById('modalMarcacion180h');
    if (modalEl) modalEl.classList.toggle('m180-locked', m180_locked);
    const banner = document.getElementById('m180-lock-banner');
    if (banner) banner.classList.toggle('d-none', !m180_locked);
    const obs = document.getElementById('m180-observaciones');
    if (obs) obs.disabled = m180_locked;
    if (m180_locked) toggleLibretaBrushMode(false);
    const brush = document.getElementById('m180-toggle-brush');
    if (brush) brush.disabled = m180_locked;
    document.querySelectorAll('#modalMarcacion180h .m180-edit-btn').forEach(b => b.classList.toggle('d-none', m180_locked));
    const wrap = document.getElementById('m180-brush-wrap');
    if (wrap) wrap.classList.toggle('d-none', m180_locked);
    const grp = document.getElementById('m180-save-group');
    if (grp) grp.classList.toggle('d-none', m180_locked);
    const cancel = document.getElementById('m180-btn-cancel');
    if (cancel) cancel.textContent = m180_locked ? 'Cerrar' : 'Cancelar';
    const reabrir = document.getElementById('m180-btn-reabrir');
    if (reabrir) reabrir.classList.toggle('d-none', !(m180_locked && m180EsSuperAdmin()));
}

function m180EsSuperAdmin() {
    try { return JSON.parse(localStorage.getItem('user'))?.is_superuser === true; } catch (_) { return false; }
}

async function libreta180hReabrir() {
    if (!m180_locked || !m180EsSuperAdmin()) return;
    const empId = parseInt(document.getElementById('m180-empleado-id').value);
    const dateStr = document.getElementById('m180-fecha-str').value;
    const ok = await uiConfirm('¿Reabrir este día?\n\nVuelve a borrador y se podrá editar de nuevo. Queda registrado quién lo reabrió.', { confirmText: 'Reabrir día', danger: false });
    if (!ok) return;
    const btn = document.getElementById('m180-btn-reabrir');
    if (btn) btn.disabled = true;
    try {
        const resp = await fetch('/api/asistencia/libreta-180h/reabrir/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ empleado_id: empId, fecha: dateStr })
        });
        if (!resp.ok) {
            let msg = `Error ${resp.status}`;
            try { const d = await resp.json(); if (typeof d.detail === 'string') msg = d.detail; } catch (_) { /* sin cuerpo */ }
            throw new Error(msg);
        }
        m180SetBadge('borrador');
        m180SetLocked(false);
        if (typeof showToast === 'function') showToast('Día reabierto: ya puedes editarlo', 'success');
        if (typeof window.reloadSingleEmployeeRow === 'function') window.reloadSingleEmployeeRow(empId);
    } catch (e) {
        Swal.fire({ icon: 'error', title: 'No se pudo reabrir', text: e.message, confirmButtonColor: '#059669' });
    } finally {
        if (btn) btn.disabled = false;
    }
}

function m180SetBadge(kind) {
    const badge = document.getElementById('m180-badge-estado');
    if (!badge) return;
    if (kind === 'cerrado') {
        badge.className = 'badge bg-success-subtle text-success-emphasis border border-success px-2 py-1';
        badge.textContent = 'DÍA CERRADO';
    } else if (kind === 'borrador') {
        badge.className = 'badge bg-warning-subtle text-warning-emphasis border border-warning px-2 py-1';
        badge.textContent = 'BORRADOR / ABIERTO';
    } else {
        badge.className = 'badge bg-secondary-subtle text-secondary-emphasis border border-secondary px-2 py-1';
        badge.textContent = 'SIN REGISTRO';
    }
}

function m180AttachCloseGuard(modalEl) {
    if (modalEl.dataset.m180Guard) return;
    modalEl.dataset.m180Guard = '1';
    modalEl.addEventListener('hide.bs.modal', (e) => {
        if (!m180_dirty || m180_force_close || m180_locked) return;
        e.preventDefault();
        Swal.fire({
            title: 'Hay cambios sin guardar',
            text: 'Si cierras ahora se perderán los tramos marcados.',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#dc2626',
            confirmButtonText: 'Descartar y cerrar',
            cancelButtonText: 'Seguir editando'
        }).then(r => {
            if (r.isConfirmed) {
                m180_force_close = true;
                bootstrap.Modal.getOrCreateInstance(modalEl).hide();
            }
        });
    });
}

async function proceedToMarcacion180h() {
    closeAsistenciaActionModal();

    const empId = marcacionesManualesState.currentEmpId;
    const dateStr = marcacionesManualesState.currentDate;
    const empNombre = marcacionesManualesState.currentEmpNombre;

    document.getElementById('m180-empleado-id').value = empId;
    document.getElementById('m180-fecha-str').value = dateStr;
    document.getElementById('m180-conductor-nombre').textContent = empNombre;
    document.getElementById('m180-fecha-display').textContent = window.formatFechaDDMMYYYY(dateStr);

    if (!m180_grid_initialized) {
        initLibreta180hGrid();
    }

    m180_history = [];
    m180_dirty = false;
    m180_force_close = false;
    m180UpdateUndoBtn();
    m180_slots = new Array(96).fill(0);
    document.getElementById('m180-observaciones').value = '';
    m180SetBadge('sin');
    m180SetLocked(false);

    try {
        const resp = await fetch(`/api/asistencia/libreta-180h/?empleado_id=${empId}&fecha=${dateStr}`);
        if (resp.ok) {
            const data = await resp.json();
            if (data.has_data && Array.isArray(data.slots_96) && data.slots_96.length === 96) {
                m180_slots = data.slots_96.map(v => Number(v) || 0);
                document.getElementById('m180-observaciones').value = data.observaciones || '';
                m180SetBadge(Number(data.cerrado) ? 'cerrado' : 'borrador');
                m180SetLocked(Number(data.cerrado) === 1);
            }
        } else {
            console.warn(`GET libreta-180h returned status ${resp.status}`);
            if (typeof showToast === 'function') showToast('No se pudo cargar el registro guardado de este día', 'warning');
        }
    } catch (e) {
        console.warn("No se pudo cargar registro previo de libreta 180h:", e);
        if (typeof showToast === 'function') showToast('No se pudo cargar el registro guardado de este día', 'warning');
    }

    refreshAllSlotsVisuals();

    const modalEl = document.getElementById('modalMarcacion180h');
    if (modalEl) {
        m180AttachCloseGuard(modalEl);
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
}

async function guardarLibreta180h(cerrarDia = false) {
    if (m180_locked) return;
    const empId = parseInt(document.getElementById('m180-empleado-id').value);
    const dateStr = document.getElementById('m180-fecha-str').value;
    const obs = document.getElementById('m180-observaciones').value.trim();

    const minTot = m180_slots.filter(s => s > 0).length * 15;
    if (cerrarDia && minTot < 1440) {
        const result = await Swal.fire({
            title: "Jornada diaria incompleta",
            html: `Se han registrado <b>${formatMinToHHMM(minTot)} hrs</b> de las 24:00 hrs requeridas por la Libreta del Art. 25 bis DT.<br><br>¿Deseas rellenar automáticamente los tramos vacíos con <b>Descanso</b> antes de cerrar el día?`,
            icon: "warning",
            showCancelButton: true,
            showDenyButton: true,
            confirmButtonColor: "#059669",
            denyButtonColor: "#3b82f6",
            confirmButtonText: "Rellenar descanso y cerrar",
            denyButtonText: "Cerrar con faltante",
            cancelButtonText: "Seguir editando"
        });

        if (result.isConfirmed) {
            libreta180hAutoDescanso();
        } else if (!result.isDenied) {
            return;
        }
    }

    const payload = {
        empleado_id: empId,
        fecha: dateStr,
        slots_96: m180_slots,
        cerrado: Boolean(cerrarDia),
        observaciones: obs
    };

    const buttons = document.querySelectorAll('#modalMarcacion180h .m180-save-btn');
    try {
        buttons.forEach(b => b.disabled = true);

        const resp = await fetch('/api/asistencia/libreta-180h/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!resp.ok) {
            let errMsg = `Error ${resp.status} al guardar Libreta 180h`;
            try {
                const errData = await resp.json();
                if (typeof errData.detail === 'string') {
                    errMsg = errData.detail;
                } else if (Array.isArray(errData.detail)) {
                    errMsg = errData.detail.map(d => `${d.loc ? d.loc.join('.') : ''}: ${d.msg}`).join('\n');
                } else if (errData.detail) {
                    errMsg = JSON.stringify(errData.detail);
                } else {
                    errMsg = JSON.stringify(errData);
                }
            } catch (_) {
                errMsg = `Error ${resp.status}: ${resp.statusText || 'Error interno del servidor'}`;
            }
            throw new Error(errMsg);
        }

        m180_dirty = false;
        if (typeof showToast === 'function') {
            showToast(cerrarDia ? "Día cerrado y guardado en la Libreta Art. 25 bis" : "Borrador de Libreta 180h guardado", "success");
        }

        const modalEl = document.getElementById('modalMarcacion180h');
        if (modalEl) {
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
        }

        if (typeof window.reloadSingleEmployeeRow === 'function') {
            await window.reloadSingleEmployeeRow(empId);
        } else if (typeof window.loadMarcacionesData === 'function') {
            window.loadMarcacionesData();
        }

    } catch (e) {
        console.error("Error guardando Libreta 180h:", e);
        Swal.fire({ icon: 'error', title: 'No se pudo guardar', text: e.message, confirmButtonColor: '#059669' });
    } finally {
        buttons.forEach(b => b.disabled = false);
    }
}

window.proceedToMarcacion180h = proceedToMarcacion180h;
window.setLibretaActividad = setLibretaActividad;
window.libreta180hAutoDescanso = libreta180hAutoDescanso;
window.libreta180hUndo = libreta180hUndo;
window.limpiarGrilla180h = limpiarGrilla180h;
window.guardarLibreta180h = guardarLibreta180h;
window.libreta180hReabrir = libreta180hReabrir;
window.toggleLibretaBrushMode = toggleLibretaBrushMode;


