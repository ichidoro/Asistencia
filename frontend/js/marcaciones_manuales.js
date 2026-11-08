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

    // --- NUEVO: RESUMEN RÁPIDO PARA DISPOSITIVOS TÁCTILES / MÓVIL ---
    const summaryCard = document.getElementById('decision-summary-card');
    const estadoBadge = document.getElementById('decision-estado-badge');
    const turnoLabel = document.getElementById('decision-turno-label');
    const marcasLabel = document.getElementById('decision-marcas-label');
    if (summaryCard && asistGeneral) {
        summaryCard.classList.remove('d-none');
        if (turnoLabel) {
            const turnoNombre = asistGeneral.turno_nombre || asistGeneral.nombre_turno || '';
            const horasTeoricas = (asistGeneral.hora_entrada_teorica && asistGeneral.hora_salida_teorica)
                ? `${asistGeneral.hora_entrada_teorica} - ${asistGeneral.hora_salida_teorica}`
                : '';
            turnoLabel.textContent = turnoNombre || horasTeoricas || (asistGeneral.horas_teoricas === 0 ? 'Día Libre' : 'Sin turno');
        }
        const entStr = asistGeneral.hora_entrada_real || (horaEntrada && horaEntrada !== 'null' ? horaEntrada : '--:--');
        const salStr = asistGeneral.hora_salida_real || (horaSalida && horaSalida !== 'null' ? horaSalida : '--:--');
        if (marcasLabel) {
            marcasLabel.textContent = (entStr === '--:--' && salStr === '--:--') ? 'Sin marcas' : `${entStr} - ${salStr}`;
        }
        if (estadoBadge) {
            estadoBadge.textContent = asistGeneral.estado || 'OK';
            estadoBadge.classList.remove('d-none');
        }
    } else if (summaryCard) {
        summaryCard.classList.add('d-none');
        if (estadoBadge) estadoBadge.classList.add('d-none');
    }

    if (dualBox) {
        // «+2» es solo una segunda jornada del mismo día; trabajar un día libre o un feriado es una jornada especial
        // y no lleva este recuadro de dos jornadas (orden del dueño, 27-10-2026)
        if (jaGeneral && jaGeneral.origen === 'COBERTURA_TURNO' && asistGeneral && (asistGeneral.horas_teoricas > 0 || asistGeneral.hora_entrada_real)) {
            const horasJa = jaGeneral.minutos_trabajados ? (Math.round(jaGeneral.minutos_trabajados / 60.0 * 10) / 10) : 0;
            const estadoJaBadge = jaGeneral.estado === 'HORAS_EXTRAS'
                ? '<span class="badge bg-warning-subtle text-dark border border-warning fw-bold"><i class="bi bi-stopwatch me-1" aria-hidden="true"></i>Horas Extras (50%)</span>'
                : jaGeneral.estado === 'EXTRA'
                ? '<span class="badge bg-success-subtle text-success border border-success-subtle fw-bold">EXTRA Aprobada</span>'
                : jaGeneral.estado === 'COMPENSATORIA'
                ? '<span class="badge bg-primary-subtle text-primary border border-primary-subtle fw-bold">Usada para compensar</span>'
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
            if (titleEl) titleEl.innerText = "Registrar regreso";
            if (subEl) subEl.innerText = "La persona tiene una salida abierta";
            if (iconEl) iconEl.className = "bi bi-door-open mb-1 fs-4";
            btnPermiso.classList.remove('btn-outline-warning');
            btnPermiso.classList.add('btn-warning');
        } else {
            if (titleEl) titleEl.innerText = "Registrar permiso o salida";
            if (subEl) subEl.innerText = "Trámites personales, retiro temprano, salidas parciales";
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
        // Un solo permiso, asignable por rol en Seguridad → Roles: «Compensar Inasistencias»
        const hasPerm = typeof AuthService !== 'undefined' ? AuthService.hasPermission("marcaciones.compensar") : true;
        if (asistJ && (asistJ.estado === 'INASISTENCIA' || asistJ.estado === 'FALTA') && hasPerm) {
            btnCompensarHE.classList.remove('d-none');
        } else {
            btnCompensarHE.classList.add('d-none');
        }
        // Un día ya compensado ofrece deshacerlo desde el mismo lugar
        const btnQuitarComp = document.getElementById('btn-quitar-compensacion');
        if (btnQuitarComp) btnQuitarComp.classList.toggle('d-none', !(asistJ && asistJ.estado === 'INASISTENCIA_COMPENSADA' && hasPerm));
    }


    if (btnValidarJornada) {
        const empMatrixJ = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
        const asistJ = empMatrixJ ? empMatrixJ[dateStr] : null;
        const ja = asistJ ? asistJ.jornada_adicional : null;
        // REGLA: mostrar cuando el estado es JORNADA_ESPECIAL (ambas marcas completas)
        // O cuando hay una jornada adicional (cobertura) pendiente, por validar o rechazada.
        const tieneJornadaAdicionalPorValidar = ja &&
            (ja.estado === 'PENDIENTE' || ja.estado === 'RECHAZADA' || ja.estado === 'JORNADA_ESPECIAL');
        // Una jornada usada para compensar una inasistencia ya se gastó: no se vuelve a validar
        const jaCompensatoria = Boolean(ja && ja.estado === 'COMPENSATORIA');
        // El llamado de un día no laborable se valida aparte (05-11-2026): mientras esté por validar, el botón aparece
        const llamadoPorValidar = Boolean(ja && ja.llamado && ja.llamado.estado === 'PENDIENTE');

        if (asistJ && ((!jaCompensatoria && (asistJ.estado === 'JORNADA_ESPECIAL' || tieneJornadaAdicionalPorValidar)) || llamadoPorValidar)) {
            btnValidarJornada.classList.remove('d-none');
            const titleEl = btnValidarJornada.querySelector('.fw-semibold');
            const subEl = btnValidarJornada.querySelector('.text-muted');
            const horasJa = ja && ja.minutos_trabajados ? (Math.round(ja.minutos_trabajados / 60.0 * 10) / 10) : 0;
            if (ja && ja.llamado) {
                const adic = ja.llamado.tipo === 'ADICIONAL';
                if (titleEl) titleEl.innerText = adic ? "Validar jornada especial y segunda jornada" : "Validar jornada especial y llamado";
                if (subEl) subEl.innerText = (ja.origen === 'FERIADO' ? 'Feriado' : 'Día libre') + ` trabajado (${horasJa}h) y ` + (adic ? 'segunda jornada' : 'llamado de emergencia');
            } else if (ja && ja.origen === 'COBERTURA_TURNO') {
                if (titleEl) titleEl.innerText = "Validar Cobertura (+2)";
                if (subEl) subEl.innerText = `Segunda jornada del día (${horasJa}h)`;
            } else {
                if (titleEl) titleEl.innerText = "Validar Jornada Especial";
                if (subEl) subEl.innerText = ja && ja.origen === 'FERIADO' ? `Feriado trabajado (${horasJa}h)`
                    : (ja ? `Día libre trabajado (${horasJa}h)` : "Día libre o feriado trabajado");
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
        // El llamado de un día no laborable ya decidido también se puede revertir (vuelve a «por validar» junto con la jornada)
        const llamJ = asistJ && asistJ.jornada_adicional ? asistJ.jornada_adicional.llamado : null;
        const llamadoDecidido = Boolean(llamJ && llamJ.estado && llamJ.estado !== 'PENDIENTE');

        if (asistJ && (asistJ.estado === 'EXTRA' || asistJ.estado === 'HORAS_EXTRAS' || tieneJornadaAdicionalAprobada || llamadoDecidido)) {
            btnRevertirHE.classList.remove('d-none');
        } else {
            btnRevertirHE.classList.add('d-none');
        }
    }

    // «Reasignar / Mover Turno» se quitó (27-10-2026): para cubrir una inasistencia queda una sola acción,
    // «Compensar inasistencia», en el día faltado.

    // --- MOSTRAR/OCULTAR BOTÓN MARCACIÓN 180 HORAS (ART. 25 BIS DT) ---
    const btnMarcacion180h = document.getElementById('btn-marcacion-180h');
    if (btnMarcacion180h) {
        const empInfo = stateMarcacionesApp.data && stateMarcacionesApp.data.empleados ? stateMarcacionesApp.data.empleados.find(e => e.id == empId) : null;
        const di = stateMarcacionesApp.data && stateMarcacionesApp.data.matriz && stateMarcacionesApp.data.matriz[empId] ? stateMarcacionesApp.data.matriz[empId][dateStr] : null;
        // Solo la modalidad «Libreta» del horario abre la libreta: una Bolsa Flexible en «Reloj» se marca con el reloj (07-11-2026)
        const isLibreta = Boolean(
            (empInfo && empInfo.modalidad_control && empInfo.modalidad_control.toUpperCase() === 'LIBRETA_180H') ||
            (di && (di.modalidad_control === 'LIBRETA_180H' || di.origen === 'LIBRETA_180H' || di.slots_96))
        );

        // Antes de la fecha de corte el día se controló por reloj: no corresponde cargar libreta
        const diaPorReloj = typeof window.esDiaControlPorReloj === 'function' && window.esDiaControlPorReloj(di, dateStr, empInfo);
        if (isLibreta && !diaPorReloj) {
            btnMarcacion180h.classList.remove('d-none');
        } else {
            btnMarcacion180h.classList.add('d-none');
        }
    }

    // Etapa 3 del orden visual (28-10-2026): las reglas de arriba siguen decidiendo qué botones van, sobre esta
    // ventana, pero se muestran en la tarjeta del día (tarjeta_dia.js). Sin la tarjeta, se abre la ventana de siempre.
    if (window.TarjetaDia && window.TarjetaDia.abrir(empId, dateStr, empNombre)) return;
    if (marcacionesManualesState.decisionInstance) {
        marcacionesManualesState.decisionInstance.show();
    }
}


function closeAsistenciaActionModal() {
    if (window.TarjetaDia) window.TarjetaDia.cerrar();
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

// Compensar inasistencia: una sola ventana con dos formas (una jornada EXTRA o horas extra), y quitar la compensación
function proceedToCompensateHE() {
    closeAsistenciaActionModal();
    if (typeof window.abrirCompensarInasistencia === 'function') {
        window.abrirCompensarInasistencia(
            marcacionesManualesState.currentEmpId,
            marcacionesManualesState.currentDate,
            marcacionesManualesState.currentEmpNombre
        );
    } else {
        console.error("Función abrirCompensarInasistencia no encontrada.");
    }
}
window.proceedToCompensateHE = proceedToCompensateHE;

function proceedToQuitarCompensacion() {
    closeAsistenciaActionModal();
    if (typeof window.quitarCompensacionInasistencia === 'function') {
        window.quitarCompensacionInasistencia(marcacionesManualesState.currentEmpId, marcacionesManualesState.currentDate);
    }
}
window.proceedToQuitarCompensacion = proceedToQuitarCompensacion;


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
            showToast(resData.message || "Listo. Se reasignó el turno.", "success");
        } else {
            Avisos.listo(resData.message || "Listo. Se reasignó el turno.");
        }

        // Refresh UI
        if (typeof window.reloadSingleEmployeeRow === 'function') {
            window.reloadSingleEmployeeRow(empId);
        } else if (typeof loadMarcacionesData === 'function') {
            loadMarcacionesData();
        }
    } catch (err) {
        console.error(err);
        Avisos.error(`No se pudo reasignar el turno. ${err.message}`);
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



// Persona y día de la ventana abierta, para que los avisos digan de quién y de qué día hablan (etapa 4)
function _diaAviso(dateStr) {
    const d = new Date(String(dateStr) + 'T12:00:00');
    if (!dateStr || isNaN(d)) return String(dateStr || '');
    const dias = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
    return `${dias[d.getDay()]} ${String(dateStr).slice(8, 10)}-${String(dateStr).slice(5, 7)}`;
}
function _quienAviso() {
    const n = marcacionesManualesState.currentEmpNombre || '';
    return typeof window.nombreTitulo === 'function' ? window.nombreTitulo(n) : n;
}

async function proceedToRevertExtra() {
    closeAsistenciaActionModal();

    const empIdR = marcacionesManualesState.currentEmpId;
    const dateStrR = marcacionesManualesState.currentDate;
    const empMatrixR = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empIdR] : null;
    const jaR = empMatrixR && empMatrixR[dateStrR] ? empMatrixR[dateStrR].jornada_adicional : null;
    const conLlamado = Boolean(jaR && jaR.llamado);
    const items = conLlamado
        ? ['La jornada especial y ' + (jaR.llamado.tipo === 'ADICIONAL' ? 'la segunda jornada' : 'el llamado de emergencia') + ' vuelven a quedar por validar.', 'Se quita lo aprobado como jornada EXTRA o como horas extra.']
        : ['Se quita la aprobación como horas extra.', 'El día vuelve al estado que tenía antes de validarse.'];
    if (!await uiConfirm(`¿Revertir la jornada del ${_diaAviso(dateStrR)} a especial?`, {
        quien: _quienAviso(),
        items: items,
        confirmText: 'Revertir jornada', danger: true
    })) {
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
                showToast(`Listo. La jornada del ${_diaAviso(dateStr)} de ${_quienAviso()} volvió a ser especial.`, "success");
            } else {
                Avisos.listo(`Listo. La jornada del ${_diaAviso(dateStr)} de ${_quienAviso()} volvió a ser especial.`);
            }
            if (typeof window.reloadSingleEmployeeRow === 'function') window.reloadSingleEmployeeRow(empId);
            else if (typeof loadMarcacionesData === 'function') loadMarcacionesData();
        } else {
            const result = await resp.json();
            if (resp.status === 409) {
                Avisos.error(result.detail, { quien: _quienAviso() });
                if (typeof window.reloadSingleEmployeeRow === 'function') window.reloadSingleEmployeeRow(empId);
                else if (typeof loadMarcacionesData === 'function') loadMarcacionesData();
            } else {
                Avisos.error(result.detail || 'No se pudo revertir la jornada.');
            }
        }
    } catch (e) {
        console.error("Error al revertir jornada:", e);
        Avisos.sinConexion();
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
                showToast("Este día no tiene una justificación para editar.", "warning");
            } else {
                Avisos.falta("Este día no tiene una justificación para editar.");
            }
        }
    } catch (e) {
        if (document.body.contains(loadingDiv)) document.body.removeChild(loadingDiv);
        console.error("Error buscando justificación:", e);
        Avisos.error("No se pudo abrir la justificación de este día.");
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
    _mmQuitarBloqueoRevision();   // lo que dejó un día por revisar abierto antes

    // Set Title
    const titleEl = marcacionesManualesState.manualModal.querySelector('.modal-title');
    if (titleEl) {
        titleEl.innerText = customTitle || "Corregir marcas del día";
    }
    if (window.cabeceraPersona) window.cabeceraPersona(marcacionesManualesState.manualModal, { nombre: empNombre, empId: empId, fecha: dateStr });

    // Reset Form
    const lblFecha = document.getElementById('manual-fecha-display');
    if (lblFecha) {
        lblFecha.value = window.formatFechaDDMMYYYY(dateStr);
    }

    const lblEmp = document.getElementById('manual-empleado-display');
    if (lblEmp) {
        lblEmp.value = window.nombreTitulo(empNombre);
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
    inputEntrada.dataset.teorico = '';
    inputSalida.value = '';
    inputSalida.disabled = false;
    inputSalida.dataset.teorico = '';
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
        // Hora del horario como ayuda; se quita sola si el día trae marcas del reloj (ver _mmQuitarHorasDelHorario)
        inputEntrada.value = asist.hora_entrada_teorica;
        inputEntrada.dataset.teorico = '1';
    }

    if (isValidTime(horaSalida)) {
        inputSalida.value = horaSalida;
        inputSalida.disabled = true;
        hasLockedMarks = true;
    } else if (asist && isValidTime(asist.hora_salida_teorica)) {
        inputSalida.value = asist.hora_salida_teorica;
        inputSalida.dataset.teorico = '1';
    }

    // Segunda jornada sin SALIDA (volvió a marcar ENTRADA 4 h o más después de salir): la primera jornada está completa y lo
    // que falta es la SALIDA de la segunda. Los campos muestran esa segunda jornada; al guardar la SALIDA queda un +2 por aprobar.
    const segundaJornada = (asist && !asist.jornada_adicional)
        ? (String(asist.observaciones || '').match(/Segunda jornada sin SALIDA: ENTRADA de las (\d{2}:\d{2}:\d{2})/) || [])[1]
        : null;
    const lblEnt = document.querySelector('label[for="manual-hora-entrada"]');
    const lblSal = document.querySelector('label[for="manual-hora-salida"]');
    if (lblEnt && lblEnt.dataset.base === undefined) lblEnt.dataset.base = lblEnt.innerHTML;
    if (lblSal && lblSal.dataset.base === undefined) lblSal.dataset.base = lblSal.innerHTML;
    if (lblEnt) lblEnt.innerHTML = lblEnt.dataset.base + (segundaJornada ? ' · segunda jornada' : '');
    if (lblSal) lblSal.innerHTML = lblSal.dataset.base + (segundaJornada ? ' · segunda jornada' : '');
    if (segundaJornada) {
        inputEntrada.value = segundaJornada;
        inputEntrada.disabled = true;
        inputSalida.value = '';
        inputSalida.disabled = false;
    }

    // --- NUEVO: Alerta visual de marca huérfana ---
    const alertDiv = document.getElementById('manual-alert-huerfana') || (() => {
        const div = document.createElement('div');
        div.id = 'manual-alert-huerfana';
        div.className = 'alert alert-warning py-2 mb-3 mt-2';
        div.style.fontSize = '0.85rem';
        // Insertar después del input de fecha
        const containerInfo = lblFecha ? lblFecha.closest('.mm-datos, .row') : null;
        if (containerInfo) {
            containerInfo.insertAdjacentElement('afterend', div);
        }
        return div;
    })();

    if (segundaJornada) {
        alertDiv.className = 'alert alert-warning py-2 mb-3 mt-2';
        alertDiv.innerHTML = '<strong><i class="bi bi-info-circle-fill"></i> Segunda jornada sin SALIDA.</strong> '
            + ((isValidTime(horaEntrada) && isValidTime(horaSalida)) ? 'La jornada de las ' + horaEntrada + ' a las ' + horaSalida + ' está completa. ' : '')
            + 'Volvió a marcar ENTRADA a las ' + segundaJornada + ': ingrese solo la SALIDA de esa segunda jornada. '
            + 'Quedará como +2 por aprobar (jornada especial u horas extra).';
        alertDiv.style.display = 'block';
        if (btnUnlock) btnUnlock.style.display = 'none';
    } else if (isValidTime(horaEntrada) && isValidTime(horaSalida)) {
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

    // El aviso amarillo fijo ("Ingrese la marcación faltante...") solo corresponde cuando de verdad falta una marca
    const avisoFalta = document.getElementById('manual-alert-faltante');
    if (avisoFalta) avisoFalta.style.display = (isValidTime(horaEntrada) && isValidTime(horaSalida) && !segundaJornada) ? 'none' : '';

    // Panel con TODAS las marcaciones del día para elegir cuál es Entrada / Salida (y ver cuál sería la colación)
    cargarPanelMarcacionesDia(empId, dateStr, alertDiv);

    // Auto-focus al primer campo libre
    setTimeout(() => {
        if (!inputEntrada.disabled) inputEntrada.focus();
        else if (!inputSalida.disabled) inputSalida.focus();
    }, 100);
    // El nombre completo en las líneas que necesite: en navegadores sin field-sizing se ajusta el alto cuando la ventana ya se ve
    if (lblEmp && lblEmp.tagName === 'TEXTAREA') {
        lblEmp.style.height = '';
        marcacionesManualesState.manualModal.addEventListener('shown.bs.modal', () => {
            if (lblEmp.scrollHeight > 0 && lblEmp.clientHeight < lblEmp.scrollHeight) lblEmp.style.height = lblEmp.scrollHeight + 'px';
        }, { once: true });
    }

    if (marcacionesManualesState.manualInstance) {
        marcacionesManualesState.manualInstance.show();
    }
}

// ── Marcaciones del día: ver todas y elegir cuál es Entrada / Salida ─────────────────────────────────────
// Caso Catalina Núñez 09-10: el reloj dejó la primera marca como "Salida" y el atraso salió de 273 min. La marca cruda no se
// modifica; lo que se elige acá se guarda aparte (logs_tipo_override) y el día se recalcula con ese tipo.
// Ventana para señalar una pausa como colación: viene de los ajustes de la pestaña
// Reglas de marcaciones (el servidor la entrega en /reglas-marcas/evaluar/); estos
// son solo los valores de respaldo mientras no llega la respuesta.
let MARCAS_COLACION_MIN = 20, MARCAS_COLACION_MAX = 150;

function _marcasMinutos(hora) {
    const [h, m] = String(hora).split(':');
    return parseInt(h, 10) * 60 + parseInt(m, 10);
}

/** Minutos de una marca con su fecha: así el hueco entre dos marcas que cruzan la medianoche no sale negativo. */
function _marcasAbs(m) {
    if (!m.fecha) return _marcasMinutos(m.hora);
    const [y, mo, d] = String(m.fecha).split('-').map(n => parseInt(n, 10));
    const [h, mi] = String(m.hora).split(':').map(n => parseInt(n, 10));
    return Date.UTC(y, mo - 1, d, h, mi) / 60000;
}

/** Entrada/Salida elegidas -> marcas que serían colación (una Salida y la Entrada siguiente, a mitad del día, 20-150 min). */
function _marcasColacion(marcas, tipos) {
    const res = {};
    for (let i = 1; i < marcas.length - 1; i++) {
        if (tipos[i] === 'Salida' && tipos[i + 1] === 'Entrada' && i + 1 <= marcas.length - 2) {
            const gap = _marcasAbs(marcas[i + 1]) - _marcasAbs(marcas[i]);
            if (gap >= MARCAS_COLACION_MIN && gap <= MARCAS_COLACION_MAX) { res[i] = gap; res[i + 1] = gap; }
        }
    }
    return res;
}

async function cargarPanelMarcacionesDia(empId, dateStr, anchorEl) {
    let host = document.getElementById('manual-panel-marcas');
    if (!host) {
        host = document.createElement('div');
        host.id = 'manual-panel-marcas';
        host.className = 'mb-3';
        if (anchorEl) anchorEl.insertAdjacentElement('afterend', host);
    }
    host.style.display = 'none';
    host.innerHTML = '';
    const reqId = `${empId}|${dateStr}`;
    host.dataset.req = reqId;
    try {
        const r = await fetch(`/api/asistencia/marcaciones/dia/?empleado_id=${encodeURIComponent(empId)}&fecha=${encodeURIComponent(dateStr)}`);
        if (!r.ok) return;
        const data = await r.json();
        if (host.dataset.req !== reqId || !data.marcas || data.marcas.length === 0) return; // el modal ya cambió de día
        _mmQuitarHorasDelHorario(data.marcas);
        host._horario = data.horario || null;
        renderPanelMarcasDia(host, empId, dateStr, data);
        cargarReglaDia(empId, dateStr, host, !!data.fecha_cerrada, reqId);
    } catch (e) {
        console.warn('No se pudieron cargar las marcaciones del día', e);
    }
}

/** Qué dice la regla de marcaciones sobre este día: línea informativa en el panel y,
 *  si el día está en revisión y su regla lo permite, el botón «Confirmar que está bien». */
async function cargarReglaDia(empId, dateStr, host, cerrada, reqId) {
    try {
        const r = await fetch(`/api/configuracion/reglas-marcas/evaluar/?empleado_id=${encodeURIComponent(empId)}&fecha=${encodeURIComponent(dateStr)}`,
            { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` } });
        if (!r.ok) return;
        const ev = await r.json();
        if (host.dataset.req !== reqId) return;
        if (ev.ventana_colacion) {
            MARCAS_COLACION_MIN = ev.ventana_colacion.min || MARCAS_COLACION_MIN;
            MARCAS_COLACION_MAX = ev.ventana_colacion.max || MARCAS_COLACION_MAX;
        }
        const cont = host.querySelector('#marcas-regla-info');
        if (!cont) return;
        if (!ev.secuencia) { cont.innerHTML = ''; return; }
        const sec = ev.secuencia.split('').map(c => c === 'E' ? 'ENTRADA' : (c === 'S' ? 'SALIDA' : c)).join(' · ');
        const regla = ev.regla || {};
        // Las salidas que se ofrecen salen de la regla guardada en la base. El servidor ya quitó «Confirmar» cuando el día
        // quedó sin calcular (confirmarlo no le daría horas y seguiría bloqueando el cierre).
        const opciones = regla.opciones_efectivas || regla.opciones_revision || [];
        const puedeEditar = typeof AuthService !== 'undefined' && AuthService.hasPermission('marcaciones.editar');
        const activo = !cerrada && ev.en_revision && puedeEditar;
        const titulo = (regla.numero ? 'Regla ' + regla.numero + ' · ' : 'Regla de marcaciones · ') + sec;
        const mx = host._mx;
        if (mx) mx.enRevision = !!ev.en_revision;
        const btnClasif = host.querySelector('#btn-marcas-guardar');
        if (btnClasif) btnClasif.textContent = (activo && opciones.includes('RECLASIFICAR')) ? 'Guardar el cambio de tipo' : 'Guardar clasificación';
        const lblClasif = btnClasif ? btnClasif.textContent : 'Guardar clasificación';
        // La marca que el sistema propone cambiar (la misma sugerencia de «Usar sugerencia») ya viene elegida y en rojo, solo si la
        // regla permite cambiar el tipo de una marca y la cantidad de marcas no deja dudas (orden del dueño, 06-11-2026). Nada se
        // guarda hasta el botón de guardar y el «Sí» de la pregunta.
        let propuestas = [];
        if (activo && opciones.includes('RECLASIFICAR') && mx && !mx.marcas.some(m => m.dudoso)) {
            propuestas = mx.marcas.map(m => (m.sugerido && m.sugerido !== m.tipo_actual) ? m.sugerido : null);
            if (propuestas.some(Boolean)) {
                mx.propuestas = propuestas;
                mx.selects().forEach((sel, i) => { if (propuestas[i]) sel.value = propuestas[i]; });
                mx.refrescar();
            } else {
                propuestas = [];
            }
        }
        const nProp = propuestas.filter(Boolean).length;
        let txtRev;
        if (nProp === 1) {
            const i = propuestas.findIndex(Boolean);
            txtRev = 'el sistema propone que la marca de las <strong>' + mx.marcas[i].hora + '</strong> sea <strong>'
                + String(propuestas[i]).toUpperCase() + '</strong> (en rojo). Revísela y presione «' + lblClasif + '».';
        } else if (nProp > 1) {
            txtRev = 'el sistema propone cambiar ' + nProp + ' marcas (en rojo). Revíselas y presione «' + lblClasif + '».';
        } else {
            txtRev = 'este día está en <strong>«Días por revisar»</strong>'
                + (regla.sin_calcular ? ' y <strong>sin horas</strong> hasta corregir sus marcas.' : ' (ya tiene sus horas calculadas).');
        }
        // «¿Qué pasó este día?»: un camino por cada opción de la regla; cada uno abre solo lo que hace falta
        const CAMINOS = {
            AGREGAR_SALIDA: ['bi-box-arrow-right', 'Se le olvidó marcar la SALIDA', 'Se propone la SALIDA de su horario'],
            AGREGAR_ENTRADA: ['bi-box-arrow-in-right', 'Se le olvidó marcar la ENTRADA', 'Se propone la ENTRADA de su horario'],
            RECLASIFICAR: ['bi-arrow-left-right', 'Marcó ENTRADA en vez de SALIDA (o al revés)', 'Cambie el tipo en la tabla de abajo'],
            CONFIRMAR: ['bi-check2-circle', 'Las marcas están bien así', 'Queda confirmado con un motivo'],
        };
        const caminos = activo ? opciones.filter(o => CAMINOS[o]) : [];
        const caminosHtml = caminos.length ? `
                <div class="mt-2 fw-semibold">¿Qué pasó este día?</div>
                <div class="d-flex flex-wrap gap-2 mt-1" role="group" aria-label="Qué pasó este día">
                    ${caminos.map(o => `<button type="button" class="btn btn-sm btn-outline-primary text-start mm-camino" data-camino="${o}" aria-pressed="false" style="border:1px solid #93a4d8;">
                        <i class="bi ${CAMINOS[o][0]} me-1" aria-hidden="true"></i><strong>${CAMINOS[o][1]}</strong><br><span class="small">${CAMINOS[o][2]}</span></button>`).join('')}
                </div>` : '';
        cont.innerHTML = `
            <div class="border rounded p-2" style="background:${ev.en_revision ? '#fef2f2' : '#f0fdf4'};">
                <i class="bi ${ev.en_revision ? 'bi-exclamation-triangle-fill text-danger' : 'bi-check-circle-fill text-success'}"></i>
                <strong>${titulo}:</strong>
                ${ev.en_revision ? txtRev
                 : ev.confirmado ? 'este día fue revisado y confirmado. Si cambian sus marcas, vuelve a revisión.'
                 : 'día en revisión ya resuelto.'}
                ${caminosHtml}
            </div>`;
        cont.querySelectorAll('.mm-camino').forEach(b => b.addEventListener('click', () => _mmElegirCamino(b.dataset.camino, empId, dateStr, host)));
        if (activo) {
            // Mientras no se elija qué pasó, la parte de abajo (escribir marcas a mano) queda vacía y bloqueada: las horas del
            // horario no son marcas y no deben guardarse por error
            _mmAplicarBloqueoRevision(caminos.some(o => o.startsWith('AGREGAR_'))
                ? 'Elija en <strong>«¿Qué pasó este día?»</strong>, más abajo: si falta una marca, se abre solo el campo de esa marca.'
                : null);
            if (nProp) _mmMarcarCamino(cont, 'RECLASIFICAR');
            else if (caminos.length === 1 && caminos[0] !== 'CONFIRMAR') _mmElegirCamino(caminos[0], empId, dateStr, host);
        }
    } catch (e) {
        console.warn('No se pudo evaluar la regla del día', e);
    }
}

async function confirmarDiaRevision(empId, dateStr) {
    // El cuadro del motivo se abre DENTRO del modal (si no, el foco del modal no deja escribir)
    const { value: motivo, isConfirmed } = await Swal.fire({
        target: document.querySelector('.modal.show') || 'body',
        title: 'Confirmar que está bien',
        input: 'textarea',
        inputLabel: 'Motivo (obligatorio): por qué este día está correcto tal como está',
        inputPlaceholder: 'Ej: la jefatura confirmó que trabajó ese horario',
        showCancelButton: true,
        confirmButtonText: 'Confirmar',
        cancelButtonText: 'Cancelar',
        inputValidator: (v) => (!v || v.trim().length < 5) ? 'Escriba un motivo (al menos 5 letras).' : undefined,
    });
    if (!isConfirmed) return;
    try {
        const r = await fetch('/api/configuracion/reglas-marcas/confirmar/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('access_token')}` },
            body: JSON.stringify({ empleado_id: parseInt(empId), fecha: dateStr, motivo: motivo.trim() })
        });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) {
            const msg = body.detail || 'No se pudo confirmar.';
            if (typeof showToast === 'function') showToast(msg, 'danger'); else alert(msg);
            return;
        }
        if (typeof showToast === 'function') showToast(body.message || 'Listo. El día quedó confirmado.', 'success');
        const host = document.getElementById('manual-panel-marcas');
        if (host) cargarReglaDia(empId, dateStr, host, false, host.dataset.req);
        if (typeof window.reloadSingleEmployeeRow === 'function') window.reloadSingleEmployeeRow(empId);
        else if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
        if (typeof window.actualizarPorRevisar === 'function') window.actualizarPorRevisar();
    } catch (e) {
        if (typeof showToast === 'function') showToast('No hay conexión con el servidor. El día no quedó confirmado; vuelva a intentarlo.', 'danger');
    }
}

function renderPanelMarcasDia(host, empId, dateStr, data) {
    const marcas = data.marcas;
    const cerrada = !!data.fecha_cerrada;
    const dudoso = marcas.some(m => m.dudoso);
    // Quitar una marca manual (nunca las del reloj): solo quien tenga el permiso que asigna el administrador al rol
    const puedeQuitar = typeof AuthService !== 'undefined' && AuthService.hasPermission('marcaciones.eliminar_manual');
    host.style.display = 'block';
    host.innerHTML = `
        <div class="border rounded p-2" style="background:#f8fafc;">
            <div class="d-flex justify-content-between align-items-center mb-1">
                <strong><i class="bi bi-list-check"></i> Marcaciones del día (${marcas.length})</strong>
                <button type="button" class="btn btn-sm btn-outline-secondary" id="btn-marcas-sugerir"${cerrada ? ' disabled' : ''}>Usar sugerencia</button>
            </div>
            <div class="small text-muted mb-2">Elija cuál marca es ENTRADA y cuál es SALIDA. La colación se detecta sola cuando una SALIDA y la ENTRADA siguiente quedan a mitad del día, entre ${MARCAS_COLACION_MIN} y ${MARCAS_COLACION_MAX} minutos.</div>
            <div id="marcas-regla-info" class="small mb-2"></div>
            <table class="table table-sm align-middle mb-1" style="font-size:.9rem;">
                <thead><tr><th>Hora</th><th>El reloj dijo</th><th>Es</th><th></th>${puedeQuitar ? '<th></th>' : ''}</tr></thead>
                <tbody id="marcas-dia-body"></tbody>
            </table>
            <div id="marcas-dia-aviso" class="small mb-2"></div>
            <div class="text-end">
                <button type="button" class="btn btn-sm btn-primary" id="btn-marcas-guardar"${cerrada ? ' disabled' : ''}>Guardar clasificación</button>
            </div>
            ${cerrada ? '<div class="small text-danger mt-1">El período está cerrado: no se puede modificar.</div>' : ''}
        </div>`;
    const body = host.querySelector('#marcas-dia-body');
    // Turno que cruza la medianoche: la Salida de las 00:08 del día siguiente es de esta jornada y se avisa con su fecha
    const etiquetaOtroDia = (m) => {
        if (!m.fecha || m.fecha === dateStr) return '';
        const [, mo, d] = m.fecha.split('-');
        return `<div class="small text-muted fw-normal">${d}-${mo} · ${m.fecha > dateStr ? 'día siguiente' : 'día anterior'}</div>`;
    };
    body.innerHTML = marcas.map((m, i) => `
        <tr data-i="${i}">
            <td class="fw-semibold">${m.hora}${etiquetaOtroDia(m)}<div class="mm-prop-txt">Cambio propuesto</div></td>
            <td>${m.tipo_reloj ? String(m.tipo_reloj).toUpperCase() : '—'}${m.manual ? ' <span class="badge bg-secondary">manual</span>' : ''}${m.corregida ? ' <span class="badge bg-warning text-dark">corregida</span>' : ''}</td>
            <td><div class="mm-seg" role="radiogroup" aria-label="Tipo de la marca de las ${m.hora}">
                <button type="button" class="mm-seg-b" role="radio" data-v="Entrada"${cerrada ? ' disabled' : ''}>ENTRADA</button>
                <button type="button" class="mm-seg-b" role="radio" data-v="Salida"${cerrada ? ' disabled' : ''}>SALIDA</button>
            </div><select class="form-select form-select-sm marca-tipo visually-hidden" tabindex="-1" aria-hidden="true"${cerrada ? ' disabled' : ''}>
                <option value="Entrada"${m.tipo_actual === 'Entrada' ? ' selected' : ''}>Entrada</option>
                <option value="Salida"${m.tipo_actual === 'Salida' ? ' selected' : ''}>Salida</option>
            </select></td>
            <td class="marca-etiqueta"></td>
            ${puedeQuitar ? `<td class="text-end">${m.manual ? `<button type="button" class="btn btn-sm btn-outline-danger btn-quitar-marca" title="Quitar esta marcación manual"${cerrada ? ' disabled' : ''}><i class="bi bi-trash"></i> Quitar</button>` : ''}</td>` : ''}
        </tr>`).join('');
    body.querySelectorAll('.btn-quitar-marca').forEach((btn) => {
        btn.addEventListener('click', () => quitarMarcaManual(empId, marcas[parseInt(btn.closest('tr').dataset.i)]));
    });

    const selects = () => Array.from(body.querySelectorAll('select.marca-tipo'));
    const tipos = () => selects().map(sel => sel.value);
    const refrescar = () => {
        const ts = tipos();
        const col = _marcasColacion(marcas, ts);
        body.querySelectorAll('tr').forEach((tr, i) => {
            tr.querySelector('.marca-etiqueta').innerHTML = col[i] !== undefined
                ? `<span class="vn-pill">Colación · ${col[i]} min</span>` : '';
            tr.querySelectorAll('.mm-seg-b').forEach((b) => b.setAttribute('aria-checked', b.dataset.v === ts[i] ? 'true' : 'false'));
            // El cambio que propone el sistema se ve en rojo mientras siga elegido (y sea distinto de lo que rige hoy)
            const prop = host._mx && host._mx.propuestas ? host._mx.propuestas[i] : null;
            tr.classList.toggle('mm-prop', !!(prop && ts[i] === prop && ts[i] !== marcas[i].tipo_actual));
        });
        const avisos = [];
        if (ts[0] === 'Salida') avisos.push('La primera marca del día está como SALIDA.');
        if (ts.length > 1 && ts[ts.length - 1] === 'Entrada') avisos.push('La última marca del día está como ENTRADA.');
        for (let i = 1; i < ts.length; i++) if (ts[i] === ts[i - 1]) { avisos.push('Hay dos marcas seguidas del mismo tipo: revise que alternen ENTRADA y SALIDA.'); break; }
        if (dudoso) avisos.push('La cantidad de marcas es impar o hay una sola: confirme cuál falta.');
        host.querySelector('#marcas-dia-aviso').innerHTML = avisos.length
            ? `<span class="text-warning-emphasis"><i class="bi bi-exclamation-triangle"></i> ${avisos.join(' ')}</span>` : '';
    };
    // La regla del día (cargarReglaDia) usa esto para dejar elegida la marca que el sistema propone cambiar
    host._mx = { marcas, selects, refrescar, propuestas: [], enRevision: false };
    selects().forEach(sel => sel.addEventListener('change', refrescar));
    body.addEventListener('click', (e) => {
        const b = e.target.closest('.mm-seg-b');
        if (!b || b.disabled) return;
        const sel = b.closest('td').querySelector('select.marca-tipo');
        if (sel && sel.value !== b.dataset.v) { sel.value = b.dataset.v; refrescar(); }
    });
    host.querySelector('#btn-marcas-sugerir').addEventListener('click', () => {
        selects().forEach((sel, i) => { sel.value = marcas[i].sugerido; });
        refrescar();
    });
    host.querySelector('#btn-marcas-guardar').addEventListener('click', async (ev) => {
        const btn = ev.currentTarget;
        const ts = tipos();
        // Antes de guardar, la pregunta con lo que cambia (orden del dueño, 06-11-2026): sin el «Sí» no se guarda ni se recalcula nada
        const cambios = marcas.map((m, i) => ({ m, nuevo: ts[i] })).filter(x => x.nuevo !== x.m.tipo_actual);
        if (!(await _mmConfirmarClasificacion(cambios, dateStr))) return;
        btn.disabled = true;
        try {
            const r = await fetch('/api/asistencia/marcaciones/reclasificar/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ empleado_id: parseInt(empId), fecha: dateStr, marcas: marcas.map((m, i) => ({ id: m.id, tipo: ts[i] })) })
            });
            const resp = await r.json().catch(() => ({}));
            if (!r.ok) {
                const msg = resp.detail || 'No se pudo guardar la clasificación.';
                if (typeof showToast === 'function') showToast(msg, 'danger'); else alert(msg);
                btn.disabled = false;
                return;
            }
            if (typeof showToast === 'function') showToast('Listo. Se guardó el tipo de cada marca y se volvió a calcular el día.', 'success');
            // Un día por revisar: la grilla confirma en la fila de la persona que quedó corregido (marcaciones_ui.js → mxAvisarCorreccion)
            if (host._mx && host._mx.enRevision) window._rvUltimaCorreccion = { empId: parseInt(empId), fecha: dateStr };
            closeManualEntryModal();
            if (typeof window.reloadSingleEmployeeRow === 'function') window.reloadSingleEmployeeRow(empId);
            else if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
            if (typeof window.actualizarPorRevisar === 'function') window.actualizarPorRevisar();
        } catch (e) {
            console.error('Error al clasificar marcaciones', e);
            Avisos.sinConexion();
            btn.disabled = false;
        }
    });
    refrescar();
}

/**
 * Quita UNA marcación manual (las del reloj no se pueden quitar). Pide el motivo, que queda en la auditoría junto con quién la quitó.
 */
async function quitarMarcaManual(empId, marca) {
    if (!marca) return;
    const fechaTxt = typeof window.formatFechaDDMMYYYY === 'function' ? window.formatFechaDDMMYYYY(marca.fecha) : marca.fecha;
    let motivo = '';
    if (typeof Swal !== 'undefined') {
        // El cuadro se abre DENTRO del modal que está a la vista: Bootstrap atrapa el foco dentro de su modal y, si el cuadro
        // quedara afuera, lo que se escribe se iría al campo del modal y no al «Motivo».
        const modalAbierto = document.querySelector('.modal.show');
        const r = await Swal.fire({
            target: modalAbierto || 'body',
            icon: 'warning',
            title: 'Quitar marcación manual',
            html: `Se quitará la marcación manual <b>${marca.tipo_actual} de las ${marca.hora}</b> del ${fechaTxt}.<br>Las marcas del reloj no se tocan. Quedará registrado quién la quitó y por qué.`,
            input: 'textarea',
            inputLabel: 'Motivo (obligatorio)',
            inputPlaceholder: 'Ej.: la Salida quedó con la fecha equivocada',
            inputValidator: (v) => (!v || v.trim().length < 5) ? 'Escriba el motivo (al menos 5 letras).' : undefined,
            showCancelButton: true,
            reverseButtons: true,
            confirmButtonText: 'Quitar marcación',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#dc2626'
        });
        if (!r.isConfirmed) return;
        motivo = String(r.value || '').trim();
    } else {
        motivo = String(window.prompt(`Motivo para quitar la marcación manual ${marca.tipo_actual} de las ${marca.hora} (${fechaTxt}):`) || '').trim();
        if (motivo.length < 5) return;
    }
    try {
        const resp = await fetch(`/api/asistencia/marcaciones/manual/${encodeURIComponent(marca.id)}/?motivo=${encodeURIComponent(motivo)}`, { method: 'DELETE' });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            const msg = data.detail || 'No se pudo quitar la marcación.';
            if (typeof showToast === 'function') showToast(msg, 'danger'); else alert(msg);
            return;
        }
        if (typeof showToast === 'function') showToast('Listo. Se quitó la marca manual.', 'success');
        closeManualEntryModal();
        if (typeof window.reloadSingleEmployeeRow === 'function') window.reloadSingleEmployeeRow(empId);
        else if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
        if (typeof window.actualizarPorRevisar === 'function') window.actualizarPorRevisar();
    } catch (e) {
        console.error('Error al quitar la marcación manual', e);
        Avisos.sinConexion();
    }
}

/** Pregunta antes de guardar la clasificación: dice qué marca cambia y de qué a qué. Devuelve true solo con el «Sí». */
async function _mmConfirmarClasificacion(cambios, dateStr) {
    const T = (t) => String(t || '').toUpperCase();
    const cuando = (m) => m.hora + (m.fecha && m.fecha !== dateStr ? ' del ' + m.fecha.substring(8, 10) + '-' + m.fecha.substring(5, 7) : '');
    const hay = cambios.length > 0;
    const lineas = cambios.map(x => 'La marca de las <b>' + cuando(x.m) + '</b> pasa de <b>' + T(x.m.tipo_actual) + '</b> a <b>' + T(x.nuevo) + '</b>.');
    const si = hay ? 'Sí, corregir' : 'Sí, recalcular';
    const html = (hay ? lineas.join('<br>') : 'No cambió el tipo de ninguna marca.')
        + '<br>Al presionar «' + si + '» se guarda y el día se vuelve a calcular.'
        + '<br><span style="color:#64748b;font-size:.9em">Con «No» no se guarda nada.</span>';
    if (typeof Swal === 'undefined') {
        return window.confirm((hay ? cambios.map(x => 'La marca de las ' + cuando(x.m) + ' pasa de ' + T(x.m.tipo_actual) + ' a ' + T(x.nuevo) + '.').join('\n') : 'No cambió el tipo de ninguna marca.')
            + '\n¿Guardar y volver a calcular el día?');
    }
    const r = await Swal.fire({
        target: document.querySelector('.modal.show') || 'body',   // dentro de la ventana: Bootstrap no deja salir el foco
        icon: 'question',
        title: hay ? '¿Está seguro de la corrección?' : '¿Volver a calcular el día?',
        html,
        showCancelButton: true,
        reverseButtons: true,
        confirmButtonText: si,
        cancelButtonText: 'No',
        allowOutsideClick: false,
    });
    return !!r.isConfirmed;
}

/** Día por revisar con todas sus marcas del reloj (la regla solo permite cambiar el tipo de una marca o confirmar): la parte de
 *  abajo, que escribe marcas a mano, queda vacía y bloqueada (variante elegida por el dueño, 06-11-2026). */
function _mmAplicarBloqueoRevision(texto) {
    const modal = marcacionesManualesState.manualModal;
    if (!modal || marcacionesManualesState.bloqueoRevision) return;
    marcacionesManualesState.bloqueoRevision = true;
    const avisoFalta = document.getElementById('manual-alert-faltante');
    if (avisoFalta) {
        avisoFalta.style.display = 'none';
        if (!document.getElementById('mm-alert-revision')) {
            avisoFalta.insertAdjacentHTML('beforebegin', '<div class="alert alert-info py-2 mb-3" id="mm-alert-revision">'
                + '<i class="bi bi-info-circle-fill me-2" aria-hidden="true"></i>' + (texto || 'Este día tiene <strong>todas sus marcas del reloj</strong>: no hace falta agregar marcas.') + '</div>');
        }
    }
    const huerfana = document.getElementById('manual-alert-huerfana');
    if (huerfana) huerfana.style.display = 'none';
    const ent = document.getElementById('manual-hora-entrada'), sal = document.getElementById('manual-hora-salida');
    [ent, sal].forEach(i => { if (i) { i.value = ''; i.disabled = true; } });
    const obs = document.getElementById('manual-observaciones');
    if (obs) obs.disabled = true;
    const guardar = modal.querySelector('.modal-footer button[onclick="saveManualEntry()"]');
    if (guardar) guardar.disabled = true;
    const fila = ent ? ent.closest('.row') : null;
    if (fila && !document.getElementById('mm-bloqueo-nota')) {
        fila.insertAdjacentHTML('afterend', '<div class="mm-bloqueo-nota" id="mm-bloqueo-nota"><i class="bi bi-lock-fill me-1" aria-hidden="true"></i>'
            + (texto ? 'Bloqueado hasta elegir arriba qué pasó este día.'
                     : 'Bloqueado: este día no necesita marcas nuevas. Solo si de verdad falta una marca, presione <strong>Habilitar edición</strong>.') + '</div>');
    }
}

function _mmQuitarBloqueoRevision() {
    marcacionesManualesState.bloqueoRevision = false;
    _mmEtiquetaGuardar(null);
    ['mm-alert-revision', 'mm-bloqueo-nota', 'mm-propuesta-nota'].forEach(id => { const el = document.getElementById(id); if (el) el.remove(); });
    const obs = document.getElementById('manual-observaciones');
    if (obs) obs.disabled = false;
    const modal = marcacionesManualesState.manualModal;
    const guardar = modal ? modal.querySelector('.modal-footer button[onclick="saveManualEntry()"]') : null;
    if (guardar) guardar.disabled = false;
}

/** Si el día trae marcas del reloj, los campos de abajo no llevan las horas del horario: esas horas no son marcas y,
 *  si alguien presiona «Guardar», quedarían como marcas manuales que nadie hizo. */
function _mmQuitarHorasDelHorario(marcas) {
    if (!marcas || !marcas.length) return;
    ['manual-hora-entrada', 'manual-hora-salida'].forEach(id => {
        const i = document.getElementById(id);
        if (i && i.dataset.teorico === '1') { i.value = ''; i.dataset.teorico = ''; }
    });
}

/** Texto del botón «Guardar» del pie: dice qué se va a guardar. null lo devuelve a su texto original. */
function _mmEtiquetaGuardar(texto) {
    const modal = marcacionesManualesState.manualModal;
    const b = modal ? modal.querySelector('.modal-footer button[onclick="saveManualEntry()"]') : null;
    if (!b) return;
    if (b.dataset.base === undefined) b.dataset.base = b.textContent;
    b.textContent = texto || b.dataset.base;
}

/** Hora de ENTRADA o SALIDA del horario asignado ese día: primero la que entrega el servidor con las marcas del día,
 *  si no, la de la grilla cargada. HH:MM:SS para el campo de hora. */
function _mmHoraDelHorario(host, empId, dateStr, cual) {
    let h = host && host._horario ? host._horario[cual] : null;
    if (!h) {
        const m = (typeof stateMarcacionesApp !== 'undefined' && stateMarcacionesApp.data && stateMarcacionesApp.data.matrix) ? stateMarcacionesApp.data.matrix[empId] : null;
        const a = m ? m[dateStr] : null;
        h = a ? a['hora_' + cual + '_teorica'] : null;
    }
    const t = String(h || '').match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?/);
    return t ? t[1].padStart(2, '0') + ':' + t[2] + ':' + (t[3] || '00') : '';
}

function _mmNotaPropuesta(input, hora, palabra) {
    const vieja = document.getElementById('mm-propuesta-nota');
    if (vieja) vieja.remove();
    const fila = input ? input.closest('.row') : null;
    if (!fila) return;
    fila.insertAdjacentHTML('afterend', '<div class="mm-bloqueo-nota" id="mm-propuesta-nota"><i class="bi bi-lightbulb me-1" aria-hidden="true"></i>'
        + (hora ? 'Se propone la ' + palabra + ' de su horario asignado (<strong>' + hora.slice(0, 5) + '</strong>). Cámbiela si la hora real fue otra y presione «Guardar la ' + palabra + '».'
                : 'Su horario no tiene hora de ' + palabra + ' para este día: escriba la hora real.') + '</div>');
}

function _mmMarcarCamino(cont, camino) {
    if (!cont) return;
    cont.querySelectorAll('.mm-camino').forEach(b => {
        const sel = b.dataset.camino === camino;
        b.classList.toggle('btn-primary', sel);
        b.classList.toggle('btn-outline-primary', !sel);
        b.setAttribute('aria-pressed', sel ? 'true' : 'false');
    });
}

/** Un camino de «¿Qué pasó este día?». Cada uno abre solo lo que hace falta:
 *  · falta la SALIDA (o la ENTRADA): solo ese campo, vacío, y el botón dice qué guarda; el otro campo queda cerrado,
 *    así no se crea una marca manual que sobra;
 *  · tipo equivocado: la tabla de marcas y su botón; la parte de abajo queda bloqueada;
 *  · está bien así: confirmar con motivo (solo existe si el día ya tiene sus horas). */
function _mmElegirCamino(camino, empId, dateStr, host) {
    const cont = host ? host.querySelector('#marcas-regla-info') : null;
    _mmMarcarCamino(cont, camino);
    const ent = document.getElementById('manual-hora-entrada'), sal = document.getElementById('manual-hora-salida');
    if (camino === 'AGREGAR_SALIDA' || camino === 'AGREGAR_ENTRADA') {
        _mmQuitarBloqueoRevision();
        const abre = camino === 'AGREGAR_SALIDA' ? sal : ent;
        const cierra = camino === 'AGREGAR_SALIDA' ? ent : sal;
        if (cierra) { cierra.value = ''; cierra.disabled = true; cierra.dataset.teorico = ''; }
        // Se propone la hora del horario asignado ese día (leída de la base); la persona la confirma o la cambia antes de guardar
        const propuesta = _mmHoraDelHorario(host, empId, dateStr, camino === 'AGREGAR_SALIDA' ? 'salida' : 'entrada');
        if (abre) { abre.value = propuesta || ''; abre.disabled = false; abre.dataset.teorico = ''; }
        _mmNotaPropuesta(abre, propuesta, camino === 'AGREGAR_SALIDA' ? 'SALIDA' : 'ENTRADA');
        const huerfana = document.getElementById('manual-alert-huerfana');
        if (huerfana) huerfana.style.display = 'none';
        _mmEtiquetaGuardar(camino === 'AGREGAR_SALIDA' ? 'Guardar la SALIDA' : 'Guardar la ENTRADA');
        if (abre) { abre.scrollIntoView({ block: 'center', behavior: 'smooth' }); setTimeout(() => abre.focus(), 150); }
    } else if (camino === 'RECLASIFICAR') {
        _mmQuitarBloqueoRevision();
        _mmAplicarBloqueoRevision();
        const primero = host ? host.querySelector('.mm-seg-b:not([disabled])') : null;
        if (primero) { primero.scrollIntoView({ block: 'center', behavior: 'smooth' }); setTimeout(() => primero.focus(), 150); }
    } else if (camino === 'CONFIRMAR') {
        confirmarDiaRevision(empId, dateStr);
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
    // Día por revisar con la parte de abajo bloqueada: «Habilitar edición» la abre para escribir la marca que de verdad falte
    if (marcacionesManualesState.bloqueoRevision) {
        _mmQuitarBloqueoRevision();
        const ent = document.getElementById('manual-hora-entrada'), sal = document.getElementById('manual-hora-salida');
        [ent, sal].forEach(i => { if (i) i.disabled = false; });
        const avisoFalta = document.getElementById('manual-alert-faltante');
        if (avisoFalta) avisoFalta.style.display = '';
        if (ent) ent.focus();
        return;
    }
    if (typeof Swal !== 'undefined') {
        Swal.fire({
            icon: 'info',
            title: 'Estas marcas vienen del reloj',
            text: 'Las marcas del reloj no se cambian a mano. Para justificar o perdonar un atraso o una salida anticipada, use Perdonazos.'
        });
    } else {
        Avisos.falta("Las marcas del reloj no se cambian a mano. Para perdonar un atraso, use Perdonazos.");
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
        const msg = marcacionesManualesState.isBolsaFija
            ? "Falta la hora. Escriba la ENTRADA, la SALIDA o un tramo de conducción."
            : "Falta la hora. Escriba la ENTRADA, la SALIDA o las dos antes de guardar.";
        const campos = [inputEntrada, inputSalida].filter(el => el && !el.disabled);
        if (marcacionesManualesState.isBolsaFija && inputCond) campos.push(inputCond);
        if (window.Avisos) window.Avisos.falta(msg, { campos });
        else alert(msg);
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

        const avisos = [];
        results.forEach(res => {
            if (res.status === 200) {
                successCount++;
                if (res.body && res.body.aviso) avisos.push(res.body.aviso);
            } else {
                errors.push(`${res.type}: ${res.body.detail || 'Error'}`);
            }
        });

        if (errors.length > 0) {
            Avisos.error(`No se guardaron todas las marcas.\n${errors.map(e => '- ' + e).join('\n')}`);
        }

        if (successCount > 0) {
            if (typeof showToast === 'function') showToast(successCount === 1 ? "Listo. Se guardó 1 marca." : `Listo. Se guardaron ${successCount} marcas.`, "success");
            // Salida de un turno de noche: quedó el día siguiente; se avisa dónde y cuántas horas dura la jornada
            if (avisos.length) Avisos.ventana(avisos.join('\n\n'), 'info');
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
        Avisos.sinConexion();
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
    document.getElementById('val-empleado-display').innerText = window.nombreTitulo(empNombre);

    // Detectar si es cobertura (+2) en día hábil o jornada libre pura
    const empMatrix = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
    const asist = empMatrix ? empMatrix[dateStr] : null;
    const ja = asist ? asist.jornada_adicional : null;
    const empInfo = stateMarcacionesApp.data && stateMarcacionesApp.data.empleados ? stateMarcacionesApp.data.empleados.find(e => e.id == empId) : null;
    const isBolsa = Boolean(asist && asist._esBolsa) || Boolean(empInfo && (empInfo.tipo_programacion === 'BOLSA_FLEXIBLE' || empInfo.tipo_programacion === 'FLEXIBLE_BOLSA'));

    // Un +2 y una jornada especial (día libre o feriado) se validan igual: EXTRA (monto fijo), horas extra o rechazar
    // (orden del dueño, 27-10-2026). Solo Bolsa Flexible no pasa a horas extra. Desde el 05-11-2026 la ventana es una tabla
    // con una fila por parte del día (la jornada y, en un día no laborable, el llamado de emergencia, que se valida aparte)
    // y una columna por decisión, con un resumen «Quedaría así» (diseño V3 aprobado por el dueño).
    const esMasDos = Boolean(ja && ja.origen === 'COBERTURA_TURNO');
    const permiteHE = Boolean(!isBolsa && (ja || (asist && asist.estado === 'JORNADA_ESPECIAL')));
    const minJa = ja && ja.minutos_trabajados ? Number(ja.minutos_trabajados)
        : (asist && asist.horas_trabajadas ? Math.round(asist.horas_trabajadas * 60) : 0);
    const horasTxt = String(Math.round(minJa / 60.0 * 10) / 10).replace('.', ',') + ' h';
    const hm = (m) => { const t = Math.round(Number(m) || 0); return Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'); };
    const estados = window._estadosAsistencia || {};
    const sigla = (cod, def) => ((estados[cod] || {}).short_label || def);
    const llam = ja && ja.llamado ? ja.llamado : null;
    const esDiaHabilMas2 = Boolean(esMasDos && asist && (asist.horas_teoricas > 0 || asist.hora_entrada_real));
    const tipoDia = (ja && ja.origen === 'FERIADO') || (asist && asist.estado === 'FERIADO') ? 'feriado' : 'día libre';
    const esLlamAdic = Boolean(llam && llam.tipo === 'ADICIONAL');
    const nombreLlam = esLlamAdic ? 'Segunda jornada (+2)' : 'Llamado de emergencia';

    const alertBox = document.getElementById('val-alert-box');
    const promptText = document.getElementById('val-prompt-text');
    const extraInfo = document.getElementById('val-extra-info');
    const footerNote = document.getElementById('val-footer-note');
    const titulo = document.getElementById('val-titulo');
    if (footerNote) { footerNote.innerHTML = ''; footerNote.classList.add('d-none'); }
    if (extraInfo) { extraInfo.innerHTML = ''; extraInfo.className = 'd-none'; }

    if (esDiaHabilMas2) {
        if (titulo) titulo.textContent = 'Validar jornada especial';
        if (window.cabeceraPersona) window.cabeceraPersona(marcacionesManualesState.validationModal, { nombre: empNombre, empId: empId, fecha: dateStr, detalle: 'segunda jornada del mismo día (+2)' });
        if (alertBox) {
            alertBox.className = "alert alert-warning py-2 mb-3";
            alertBox.innerHTML = '<i class="bi bi-lightning-fill me-2 text-warning"></i><strong>Cobertura de turno (+2) detectada.</strong> El trabajador hizo una segunda jornada el mismo día; el turno base se conserva intacto.';
        }
        if (extraInfo) {
            // En una cobertura (se quedó antes o después de su turno) las marcas del día incluyen la cobertura: el turno es
            // la parte que no es de ella
            let tIni = (asist.hora_entrada_real || '--:--').substring(0, 5), tFin = (asist.hora_salida_real || '--:--').substring(0, 5);
            const jIni = (ja.hora_entrada || '').substring(0, 5), jFin = (ja.hora_salida || '').substring(0, 5);
            if (jIni && jFin && jIni === tIni) tIni = jFin;
            else if (jIni && jFin && jFin === tFin) tFin = jIni;
            extraInfo.className = 'vt-ctx';
            extraInfo.innerHTML = '<i class="bi bi-info-circle"></i><span>Turno del día: <b>' + tIni + ' – ' + tFin + ' · ' + window.textoEstado(asist.estado || 'OK')
                + '</b> <small>(se calcula solo, no se valida aquí)</small></span>';
        }
        if (promptText) promptText.textContent = 'Elija cómo se valida la segunda jornada';
    } else {
        if (titulo) titulo.textContent = llam ? ('Validar ' + tipoDia + ' con ' + (esLlamAdic ? 'segunda jornada' : 'llamado de emergencia')) : 'Validar jornada especial';
        if (window.cabeceraPersona) window.cabeceraPersona(marcacionesManualesState.validationModal, { nombre: empNombre, empId: empId, fecha: dateStr, detalle: 'trabajo en ' + tipoDia });
        if (alertBox) {
            alertBox.className = "alert alert-info py-2 mb-3";
            alertBox.innerHTML = llam
                ? '<i class="bi bi-star-fill me-2"></i><strong>' + (tipoDia === 'feriado' ? 'Feriado' : 'Día libre') + ' con ' + nombreLlam.toLowerCase() + '.</strong> Trabajó su ' + tipoDia
                    + ' y además ' + (esLlamAdic ? 'hizo una segunda jornada' : 'tuvo un llamado de emergencia') + ' ese día. Cada parte se valida por separado.'
                : '<i class="bi bi-star-fill me-2"></i><strong>Jornada especial.</strong> Trabajo en ' + tipoDia + ' (no es un +2).';
        }
        if (promptText) promptText.textContent = llam ? 'Elija cómo se valida cada parte del día' : 'Elija cómo se valida la jornada';
    }

    // Partes del día que se validan aquí. Una jornada ya usada para compensar una inasistencia no se vuelve a validar.
    const decisionDe = (estado) => ({ EXTRA: 'APROBAR', HORAS_EXTRAS: 'APROBAR_COMO_HE', RECHAZADA: 'RECHAZAR' }[estado] || null);
    const partes = [];
    if (!(ja && ja.estado === 'COMPENSATORIA')) {
        const esCobertura = Boolean(ja && (ja.observaciones || '').includes('Cobertura de Turno'));
        partes.push({
            parte: 'JORNADA', minutos: minJa, actual: decisionDe(ja && ja.estado),
            tag: esDiaHabilMas2 ? '<span class="vt-tag mas2"><i class="bi bi-plus-lg"></i>+2</span>'
                : '<span class="vt-tag esp"><i class="bi bi-star-fill"></i>' + sigla('JORNADA_ESPECIAL', 'ESP') + '</span>',
            titulo: esDiaHabilMas2 ? (esCobertura ? 'Cobertura de turno' : 'Segunda jornada')
                : (llam ? 'Jornada del ' + tipoDia : 'Trabajo en ' + tipoDia),
            sub: (ja ? (ja.hora_entrada || '--:--').substring(0, 5) + ' – ' + (ja.hora_salida || '--:--').substring(0, 5) + ' · ' : '') + horasTxt,
            nombre: esDiaHabilMas2 ? 'la segunda jornada' : 'la jornada',
        });
    }
    if (llam) {
        const eme = estados['LLAMADO_EMERGENCIA'] || {};
        partes.push({
            parte: 'LLAMADO', minutos: Number(llam.minutos) || 0, actual: decisionDe(llam.estado), eme: true,
            tag: '<span class="vt-tag ' + ((eme.color_clase) || 'color-violeta') + '">'
                + '<i class="bi ' + (eme.icono_bi || 'bi-telephone-inbound-fill') + '"></i>' + (esLlamAdic ? '+2' : (eme.short_label || 'EME')) + '</span>',
            titulo: nombreLlam,
            sub: (llam.hora_entrada || '--:--').substring(0, 5) + ' – ' + (llam.hora_salida || '--:--').substring(0, 5) + ' · ' + hm(llam.minutos),
            nombre: esLlamAdic ? 'la segunda jornada' : 'el llamado',
        });
    }
    const columnas = [{ accion: 'APROBAR', th: 'Jornada EXTRA<small>monto fijo</small>', aria: 'jornada EXTRA' }];
    if (permiteHE) columnas.push({ accion: 'APROBAR_COMO_HE', th: 'Horas extra<small>al 50 %</small>', aria: 'horas extra al 50 %' });
    columnas.push({ accion: 'RECHAZAR', th: 'Rechazar', aria: 'rechazar', rech: true });

    const caja = document.getElementById('val-ops');
    const footer = marcacionesManualesState.validationModal.querySelector('.modal-footer');
    if (caja && footer) {
        const elegidas = {};
        partes.forEach(p => { elegidas[p.parte] = p.actual; });
        caja.setAttribute('role', 'group');
        caja.innerHTML = '<table class="vt-tabla"><thead><tr><th scope="col">Parte del día</th>'
            + columnas.map(c => '<th scope="col">' + c.th + '</th>').join('') + '</tr></thead><tbody>'
            + partes.map(p => '<tr class="' + (p.eme ? 'vt-eme' : '') + '" role="radiogroup" aria-label="' + p.titulo + '" data-parte="' + p.parte + '">'
                + '<td class="vt-parte">' + p.tag + '<b>' + p.titulo + '</b><span class="vt-sub">' + p.sub + '</span></td>'
                + columnas.map(c => '<td><button type="button" class="vt-rd' + (c.rech ? ' vt-rech' : '') + '" role="radio" data-parte="' + p.parte
                    + '" data-accion="' + c.accion + '" aria-checked="' + (elegidas[p.parte] === c.accion ? 'true' : 'false') + '" aria-label="' + p.titulo + ': ' + c.aria + '"></button></td>').join('')
                + '</tr>').join('')
            + '</tbody></table><div class="vt-res" id="val-resumen" aria-live="polite"></div>';
        footer.innerHTML = `
            <button type="button" class="btn btn-outline-danger me-auto" onclick="deleteManualJornada('${empId}', '${dateStr}')" title="Elimina las marcaciones manuales creadas en este día">
                <i class="bi bi-trash"></i> Eliminar ingreso manual
            </button>
            <button type="button" class="btn btn-secondary" onclick="closeValidationModal()">Cancelar</button>
            <button type="button" class="btn btn-primary fw-bold px-4" id="val-confirmar" disabled>Validar</button>`;
        const confirmar = footer.querySelector('#val-confirmar');
        const resumen = caja.querySelector('#val-resumen');
        const textoBoton = partes.length > 1 ? 'Validar las dos' : 'Validar';

        // «Quedaría así»: lo que se paga y cómo se verá en la grilla, con las elecciones de la tabla
        const pintarResumen = () => {
            const faltan = partes.filter(p => !elegidas[p.parte]);
            confirmar.disabled = faltan.length > 0;
            confirmar.textContent = textoBoton;
            if (faltan.length) {
                resumen.className = 'vt-res vt-falta';
                resumen.innerHTML = '<i class="bi bi-hand-index me-1"></i>Elija una opción para ' + faltan.map(p => p.nombre).join(' y ') + '.';
                return;
            }
            const nExtra = partes.filter(p => elegidas[p.parte] === 'APROBAR').length;
            const minHE = partes.filter(p => elegidas[p.parte] === 'APROBAR_COMO_HE').reduce((s, p) => s + p.minutos, 0);
            const pagos = [];
            if (nExtra) pagos.push('<b>' + nExtra + (nExtra === 1 ? ' jornada EXTRA' : ' jornadas EXTRA') + ' (monto fijo)</b>');
            if (minHE > 0) pagos.push('<b>' + hm(minHE) + ' de horas extra al 50 %</b>');
            const lblExt = sigla('EXTRA', 'EXT');
            const celda = (p) => {
                const a = elegidas[p.parte];
                if (a === 'RECHAZAR') return null;
                if (p.parte === 'LLAMADO') {
                    const base = esLlamAdic ? '+2' : sigla('LLAMADO_EMERGENCIA', 'EME');
                    return base + (a === 'APROBAR_COMO_HE' ? ' HE' : ' EXT');
                }
                if (esDiaHabilMas2) return a === 'APROBAR_COMO_HE' ? '+2 HE' : lblExt;
                return a === 'APROBAR_COMO_HE' ? 'HE' : lblExt;
            };
            const enGrilla = [];
            if (esDiaHabilMas2) enGrilla.push(sigla(asist.estado || 'OK', (asist.estado || 'OK').substring(0, 3)));
            partes.forEach(p => { const c = celda(p); if (c) enGrilla.push(c); });
            const rechazadas = partes.filter(p => elegidas[p.parte] === 'RECHAZAR').map(p => p.nombre);
            let txt = 'Quedaría así: ' + (pagos.length ? pagos.join(' + ') : '<b>no se paga nada</b>') + '.';
            if (rechazadas.length && pagos.length) txt += ' Se rechaza ' + rechazadas.join(' y ') + '.';
            if (enGrilla.length === 1) txt += ' En la grilla: ' + enGrilla[0] + '.';
            else if (enGrilla.length > 1) txt += ' En la grilla: ' + enGrilla[0] + ' arriba y ' + enGrilla[1] + ' abajo.';
            else txt += ' En la grilla la jornada queda rechazada.';
            resumen.className = 'vt-res';
            resumen.innerHTML = '<i class="bi bi-check2-circle me-1"></i>' + txt;
        };
        caja.querySelectorAll('.vt-rd').forEach(b => {
            b.addEventListener('click', () => {
                elegidas[b.dataset.parte] = b.dataset.accion;
                caja.querySelectorAll('.vt-rd[data-parte="' + b.dataset.parte + '"]').forEach(x => x.setAttribute('aria-checked', x === b ? 'true' : 'false'));
                pintarResumen();
            });
            b.addEventListener('keydown', (ev) => {
                if (!['ArrowRight', 'ArrowLeft'].includes(ev.key)) return;
                ev.preventDefault();
                const fila = [...caja.querySelectorAll('.vt-rd[data-parte="' + b.dataset.parte + '"]')];
                const sig = fila[(fila.indexOf(b) + (ev.key === 'ArrowRight' ? 1 : fila.length - 1)) % fila.length];
                sig.focus(); sig.click();
            });
        });
        pintarResumen();
        // Solo se envían las partes que cambiaron; la jornada primero y después el llamado
        confirmar.addEventListener('click', () => {
            const cambios = partes.filter(p => elegidas[p.parte] && elegidas[p.parte] !== p.actual).map(p => ({ parte: p.parte, accion: elegidas[p.parte] }));
            if (!cambios.length) { closeValidationModal(); return; }
            confirmar.disabled = true;
            validarPartesDelDia(cambios);
        });
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
 * Valida las partes del día elegidas en la tabla (la jornada y, en un día no laborable, el llamado de emergencia).
 * Cada parte va en su propia llamada; solo la primera lleva la versión del día que se está viendo (la segunda llega
 * después de que la primera ya cambió el día).
 */
async function validarPartesDelDia(cambios) {
    const empId = parseInt(marcacionesManualesState.currentEmpId);
    const fecha = marcacionesManualesState.currentDate;
    const empMatrix = stateMarcacionesApp.data && stateMarcacionesApp.data.matrix ? stateMarcacionesApp.data.matrix[empId] : null;
    const asist = empMatrix ? empMatrix[fecha] : null;
    let hechas = 0;
    const recargar = () => {
        if (typeof window.reloadSingleEmployeeRow === 'function') window.reloadSingleEmployeeRow(empId);
        else if (typeof loadMarcacionesData === 'function') loadMarcacionesData();
        if (typeof recargarPreEvaluacionCierre === 'function' && document.getElementById('modal-cierre-wizard')?.classList.contains('show')) {
            recargarPreEvaluacionCierre();
        }
    };
    try {
        for (const c of cambios) {
            const payload = { empleado_id: empId, fecha: fecha, accion: c.accion, parte: c.parte };
            if (hechas === 0) payload.last_updated_at = asist ? asist.updated_at : null;
            const resp = await fetch('/api/asistencia/jornada/validar/', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
            });
            if (!resp.ok) {
                const result = await resp.json().catch(() => ({}));
                const que = c.parte === 'LLAMADO' ? 'el llamado' : 'la jornada';
                Avisos.error((hechas ? 'La primera parte quedó validada, pero no se pudo validar ' + que + '. ' : '') + (result.detail || 'No se pudo validar ' + que + '.'),
                    resp.status === 409 ? { quien: _quienAviso() } : undefined);
                closeValidationModal();
                recargar();
                return;
            }
            hechas += 1;
        }
        const msg = cambios.length > 1 ? 'Listo. Las dos partes del día quedaron validadas.'
            : (cambios[0].accion === 'RECHAZAR' ? 'Listo. ' + (cambios[0].parte === 'LLAMADO' ? 'Llamado rechazado.' : 'Jornada rechazada.')
                : 'Listo. ' + (cambios[0].parte === 'LLAMADO' ? 'Llamado validado' : 'Jornada validada')
                    + (cambios[0].accion === 'APROBAR_COMO_HE' ? ' como horas extra (50 %).' : ' como jornada EXTRA.'));
        if (typeof showToast === 'function') showToast(msg, cambios.every(c => c.accion === 'RECHAZAR') ? 'info' : 'success');
        else Avisos.listo(msg);
        closeValidationModal();
        recargar();
    } catch (e) {
        console.error('Error validando las partes del día:', e);
        Avisos.sinConexion();
    }
}
window.validarPartesDelDia = validarPartesDelDia;

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
            let msg = "Listo. Jornada validada.";
            if (accion === 'APROBAR_COMO_HE') {
                msg = "Listo. Jornada aprobada como horas extra (50 %).";
            } else if (accion === 'APROBAR') {
                msg = "Listo. Jornada aprobada como jornada especial.";
            } else if (accion === 'RECHAZAR') {
                msg = "Listo. Jornada rechazada.";
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
                Avisos.error(result.detail, { quien: _quienAviso() });
                if (typeof window.reloadSingleEmployeeRow === 'function') {
                    window.reloadSingleEmployeeRow(payload.empleado_id);
                } else if (typeof loadMarcacionesData === 'function') {
                    loadMarcacionesData();
                }
            } else {
                Avisos.error(result.detail || 'No se pudo validar la jornada.');
            }
        }
    } catch (e) {
        console.error("Error validating jornada:", e);
        Avisos.sinConexion();
    }
}

/**
 * Llama al endpoint para eliminar el ingreso manual que generó la jornada especial
 * @param {string|number} empId 
 * @param {string} fecha 
 */
async function deleteManualJornada(empId, fecha) {
    if (!await uiConfirm(`¿Quitar todas las marcas manuales del ${_diaAviso(fecha)}?`, {
        quien: _quienAviso(),
        items: ['Se borran las marcas escritas a mano en este día; las del reloj se mantienen.', 'El día se vuelve a calcular.', 'No se puede deshacer.'],
        confirmText: 'Quitar marcas manuales', danger: true
    })) {
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
                showToast("Listo. Se quitaron las marcas manuales y el día se volvió a calcular.", "success");
            } else {
                Avisos.listo("Listo. Se quitaron las marcas manuales y el día se volvió a calcular.");
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
                showToast(error.detail || 'No se pudieron quitar las marcas manuales.', "error");
            } else {
                Avisos.error(error.detail || 'No se pudieron quitar las marcas manuales.');
            }
        }
    } catch (e) {
        console.error("Error al eliminar ingreso manual:", e);
        if (typeof showToast === 'function') {
            Avisos.sinConexion();
        } else {
            Avisos.sinConexion();
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
    if (empNombre) document.getElementById('fill-empleado-nombre').value = window.nombreTitulo ? window.nombreTitulo(empNombre) : empNombre;

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
        Avisos.falta('Faltan datos. Elija la persona y las fechas de inicio y fin.', { campos: ['fill-empleado-id', 'fill-fecha-inicio', 'fill-fecha-fin'].filter(id => !(document.getElementById(id) || {}).value) });
        return;
    }

    // Loading State
    const btn = document.querySelector('#modal-relleno-masivo button[type="submit"]');
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
            Avisos.listo(result.mensaje ? `Listo. ${result.mensaje}` : 'Listo. Se rellenaron los días según el turno.');
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
            Avisos.error(result.detail || result.mensaje || 'No se pudieron rellenar los días. El servidor no dio el motivo.');
            console.error("Bulk Fill Error:", result);
        }
    } catch (e) {
        console.error("Network error:", e);
        Avisos.sinConexion();
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
    if (window.cabeceraPersona) window.cabeceraPersona(modal, { nombre: empNombre, empId: empId, fecha: dateStr });
    document.getElementById('permiso-sin-tipos').classList.add('d-none');
    document.getElementById('permiso-tipo-id').innerHTML = '<option value="">Cargando...</option>';
    document.getElementById('permiso-info-deuda').classList.add('d-none');
    document.getElementById('form-registro-permiso').reset();

    const inputInicio = document.getElementById('permiso-hora-inicio');
    const inputFin = document.getElementById('permiso-hora-fin');
    const inputTipo = document.getElementById('permiso-tipo-id');
    const btnSubmit = document.getElementById('btn-permiso-registrar');

    // Resetear estados por defecto
    inputInicio.disabled = false;
    inputFin.disabled = false;
    inputTipo.disabled = false;
    if (btnSubmit) {
        btnSubmit.style.display = 'inline-block';
        btnSubmit.innerText = "Registrar";
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
        if (btnSubmit) btnSubmit.innerText = "Registrar regreso";
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
        if (btnSubmit) btnSubmit.innerText = "Registrar";
    }

    // 2. Cargar Tipos de Justificación que sean "Por Horas"
    try {
        const resp = await fetch('/api/configuracion/justificaciones/tipos/');
        const tipos = await resp.json();
        const tiposPorHora = tipos.filter(t => t.es_por_horas);

        if (tiposPorHora.length === 0) {
            inputTipo.innerHTML = '<option value="">Sin tipos por horas</option>';
            document.getElementById('permiso-sin-tipos').classList.remove('d-none');
        } else {
            inputTipo.innerHTML = '<option value="">Elegir</option>' +
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

    bootstrap.Modal.getOrCreateInstance(modal).show();
}

function closePermissionModal() {
    const modal = document.getElementById('modal-registro-permiso');
    if (modal) bootstrap.Modal.getOrCreateInstance(modal).hide();
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
        Avisos.falta('Faltan datos. Elija el tipo de permiso y la hora de inicio.', { campos: [!tipoId && 'permiso-tipo-id', !hIni && 'permiso-hora-inicio'].filter(Boolean) });
        return;
    }

    const mode = marcacionesManualesState.permisoActivoActual ? 'CLOSE' : 'OPEN';

    try {
        let resp;
        const msgOperacion = mode === 'CLOSE' ? "Listo. Se registró el regreso." : "Listo. Se registró el permiso.";

        if (mode === 'CLOSE') {
            if (!hFin) {
                Avisos.falta('Falta la hora de regreso. Escríbala para cerrar el permiso.', { campos: ['permiso-hora-fin'] });
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
            Avisos.error(err.detail || (mode === 'CLOSE' ? "No se pudo registrar el regreso." : "No se pudo registrar el permiso."));
        }
    } catch (e) {
        console.error("Error guardando permiso:", e);
        Avisos.sinConexion();
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
            Avisos.falta('Faltan las fechas. Elija desde y hasta.', { campos: [!fechaInicio && 'perdonazo-fecha-inicio', !fechaFin && 'perdonazo-fecha-fin'].filter(Boolean) });
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
            Avisos.falta("El área elegida no tiene personas activas.");
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
                'Authorization': `Bearer ${window.AuthToken || localStorage.getItem('access_token')}`
            },
            body: JSON.stringify(payload)
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Error en la operación masiva");
        }

        const result = await resp.json();
        Avisos.listo(result.registros_procesados ? `Listo. Se perdonaron ${result.registros_procesados} registros.` : 'Listo. Perdonazo aplicado.');
        closePerdonazoMasivoModal();
        
        // Refrescar si existe la función
        if (typeof loadReporte === 'function') {
            loadReporte();
        } else if (typeof window.loadMarcacionesData === 'function') {
            window.loadMarcacionesData();
        }

    } catch (e) {
        console.error("Error en executePerdonazoMasivo:", e);
        Avisos.error(`No se pudo aplicar el perdonazo. ${e.message}`);
    } finally {
        if (btn) {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    }
}


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
let m180_chofer_id = null;       // si el empleado es peoneta de un chofer ese día: ID del chofer
let m180_chofer_tiene_datos = false;
let m180_acomp = [];          // IDs de peonetas que copian la libreta del chofer
let m180_acomp_ocupados = [];  // peonetas ya asignados a otro chofer ese día
let m180_validado = false;     // el día abierto está validado (solo se edita con el permiso «Editar libreta validada»)
let m180_enlazados = [];       // quienes andan con esta persona ese día (para «¿A quién más le aplico este cambio?»)
let m180_revision_ctx = null;  // límites de Configuración y cómo terminó el día anterior (para «cosas por revisar»)
let m180_patente_origen = null; // de dónde salió el camión elegido: PLAN, MANUAL, CHOFER o SIN_CAMION

function m180Esc(t) {
    return String(t).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function m180AcompNombre(id) {
    const emps = (typeof stateMarcacionesApp !== 'undefined' && stateMarcacionesApp.data && stateMarcacionesApp.data.empleados) || [];
    const e = emps.find(x => x.id == id);
    if (!e) return `Empleado ${id}`;
    return e.nombre_completo || e.nombre || [e.nombres, e.apellidos].filter(Boolean).join(' ') || `Empleado ${id}`;
}

function m180AcompIniciales(nombre) {
    const w = String(nombre).trim().split(/\s+/).filter(Boolean);
    return ((w[0] || '')[0] || '').toUpperCase() + ((w.length > 1 ? w[w.length - 1] : '')[0] || '').toUpperCase();
}

let m180_acomp_activo = -1;

function m180AcompCandidatos() {
    const emps = (typeof stateMarcacionesApp !== 'undefined' && stateMarcacionesApp.data && stateMarcacionesApp.data.empleados) || [];
    const choferId = parseInt(document.getElementById('m180-empleado-id').value);
    let cand = emps.filter(e => /peoneta/i.test(e.cargo || ''));
    if (!cand.length) cand = emps;  // sin cargo "peoneta" reconocible: listar a todos
    return cand.filter(e => e.id != choferId && !m180_acomp.includes(Number(e.id)) && !m180_acomp_ocupados.includes(Number(e.id)))
        .sort((a, b) => m180AcompNombre(a.id).localeCompare(m180AcompNombre(b.id)));
}

function m180AcompRenderPanel() {
    const panel = document.getElementById('m180-acomp-panel');
    const input = document.getElementById('m180-acomp-input');
    if (!panel || !input) return;
    const q = input.value.trim().toLowerCase();
    const lista = m180AcompCandidatos().filter(e => !q || m180AcompNombre(e.id).toLowerCase().includes(q));
    m180_acomp_activo = lista.length ? Math.min(Math.max(m180_acomp_activo, 0), lista.length - 1) : -1;
    if (!lista.length) {
        panel.innerHTML = `<div class="m180-acomp-none">${q ? 'Ningún peoneta coincide con "' + m180Esc(input.value.trim()) + '"' : 'No quedan peonetas por agregar'}</div>`;
        return;
    }
    panel.innerHTML = lista.map((e, i) => {
        const nom = m180AcompNombre(e.id);
        let nomHtml = m180Esc(nom);
        if (q) {
            const ix = nom.toLowerCase().indexOf(q);
            if (ix >= 0) nomHtml = m180Esc(nom.slice(0, ix)) + '<mark>' + m180Esc(nom.slice(ix, ix + q.length)) + '</mark>' + m180Esc(nom.slice(ix + q.length));
        }
        return `<button type="button" role="option" class="m180-acomp-opt${i === m180_acomp_activo ? ' is-active' : ''}" data-id="${e.id}" onmousedown="event.preventDefault(); window.m180AcompAgregar(${e.id})">
            <span class="m180-acomp-av">${m180Esc(m180AcompIniciales(nom))}</span>
            <span><div class="nm">${nomHtml}</div><div class="cg">${m180Esc(e.cargo || 'Sin cargo')}</div></span>
            <i class="bi bi-plus-circle-fill add" aria-hidden="true"></i></button>`;
    }).join('');
    const act = panel.querySelector('.is-active');
    if (act) act.scrollIntoView({ block: 'nearest' });
}

function m180AcompAbrir(abrir) {
    const combo = document.getElementById('m180-acomp-combo');
    const input = document.getElementById('m180-acomp-input');
    if (!combo) return;
    combo.classList.toggle('is-open', abrir);
    if (input) input.setAttribute('aria-expanded', abrir ? 'true' : 'false');
    if (abrir) m180AcompRenderPanel();
}

function m180AcompInitCombo() {
    const input = document.getElementById('m180-acomp-input');
    if (!input || input.dataset.ready) return;
    input.dataset.ready = '1';
    input.addEventListener('focus', () => { m180_acomp_activo = 0; m180AcompAbrir(true); });
    input.addEventListener('blur', () => m180AcompAbrir(false));
    input.addEventListener('input', () => { m180_acomp_activo = 0; m180AcompAbrir(true); });
    input.addEventListener('keydown', ev => {
        const opts = document.querySelectorAll('#m180-acomp-panel .m180-acomp-opt');
        const abierto = document.getElementById('m180-acomp-combo').classList.contains('is-open');
        if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
            ev.preventDefault();
            if (!abierto) return m180AcompAbrir(true);
            if (opts.length) m180_acomp_activo = (m180_acomp_activo + (ev.key === 'ArrowDown' ? 1 : -1) + opts.length) % opts.length;
            m180AcompRenderPanel();
        } else if (ev.key === 'Enter') {
            ev.preventDefault();
            const o = opts[m180_acomp_activo];
            if (o) window.m180AcompAgregar(o.dataset.id);
        } else if (ev.key === 'Escape' && (abierto || input.value)) {
            ev.stopPropagation();
            input.value = '';
            m180AcompAbrir(false);
        }
    });
}

// Tarjeta del peoneta: quién es su chofer ese día, si ya tiene el turno de él y botón para volver a asignárselo.
// Al ser peoneta se oculta el selector de "Acompañantes" (es del chofer y confundía: el peoneta no elige a nadie).
function m180ChoferRender() {
    const box = document.getElementById('m180-chofer-box');
    const acomp = document.getElementById('m180-acomp-box');
    if (!box) return;
    const esPeoneta = m180_chofer_id != null;
    if (acomp) acomp.classList.toggle('d-none', esPeoneta);
    if (!esPeoneta) { box.classList.add('d-none'); box.innerHTML = ''; return; }
    const nom = m180AcompNombre(m180_chofer_id);
    const estado = m180_chofer_tiene_datos
        ? '<span class="m180-chofer-st ok"><i class="bi bi-check-circle-fill" aria-hidden="true"></i> Con el turno del chofer</span>'
        : '<span class="m180-chofer-st warn"><i class="bi bi-exclamation-circle-fill" aria-hidden="true"></i> Sin turno asignado</span>';
    const boton = m180_locked ? '' : `<button type="button" class="m180-chofer-btn" id="m180-btn-reasignar" onclick="window.m180ReasignarTurno()">
            <i class="bi bi-arrow-repeat" aria-hidden="true"></i> ${m180_chofer_tiene_datos ? 'Volver a asignar turno' : 'Asignar turno del chofer'}</button>`;
    box.classList.remove('d-none');
    box.innerHTML = `<div class="m180-chofer-ico"><i class="bi bi-truck" aria-hidden="true"></i></div>
        <div class="m180-chofer-body">
            <div class="m180-chofer-lbl">Chofer de este peoneta hoy</div>
            <div class="m180-chofer-who"><span class="m180-acomp-av">${m180Esc(m180AcompIniciales(nom))}</span><span class="nm">${m180Esc(nom)}</span></div>
            ${estado}
        </div>${boton}`;
}

async function m180ReasignarTurno() {
    const empId = parseInt(document.getElementById('m180-empleado-id').value);
    const dateStr = document.getElementById('m180-fecha-str').value;
    const btn = document.getElementById('m180-btn-reasignar');
    try {
        if (btn) btn.disabled = true;
        const resp = await fetch('/api/asistencia/libreta-180h/reasignar-turno/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getLibretaAuthHeaders() },
            body: JSON.stringify({ empleado_id: empId, fecha: dateStr })
        });
        if (!resp.ok) {
            let msg = `Error ${resp.status} al reasignar`;
            try { const d = await resp.json(); if (d.detail) msg = d.detail; } catch (_) {}
            throw new Error(msg);
        }
        if (typeof showToast === 'function') showToast('Listo. El turno del chofer pasó al peoneta.', 'success');
        m180_dirty = false;
        if (typeof window.reloadSingleEmployeeRow === 'function') await window.reloadSingleEmployeeRow(empId);
        else if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
        await proceedToMarcacion180h();   // recarga la tarjeta con el turno ya asignado
    } catch (err) {
        if (btn) btn.disabled = false;
        Swal.fire({ icon: 'error', title: 'No se pudo reasignar', text: err.message });
    }
}
window.m180ReasignarTurno = m180ReasignarTurno;

function m180AcompRender() {
    m180AcompInitCombo();
    const cnt = document.getElementById('m180-acomp-count');
    if (cnt) cnt.textContent = m180_acomp.length;
    const chips = document.getElementById('m180-acomp-chips');
    if (chips) {
        chips.innerHTML = m180_acomp.length
            ? `<div class="m180-acomp-list">${m180_acomp.map(id => {
                const nom = m180AcompNombre(id);
                return `<span class="m180-acomp-chip"><span class="m180-acomp-av">${m180Esc(m180AcompIniciales(nom))}</span><span class="nm">${m180Esc(nom)}</span>
                    <button type="button" aria-label="Quitar a ${m180Esc(nom)}" onclick="window.m180AcompQuitar(${id})"><i class="bi bi-x-lg" style="font-size:.7rem" aria-hidden="true"></i></button></span>`;
            }).join('')}</div>`
            : `<div class="m180-acomp-empty"><i class="bi bi-person-plus" aria-hidden="true"></i><span>Sin acompañantes: el horario queda solo para el chofer.</span></div>`;
    }
    const combo = document.getElementById('m180-acomp-combo');
    if (combo && combo.classList.contains('is-open')) m180AcompRenderPanel();
}

window.m180AcompAgregar = function(id) {
    id = Number(id);
    if (!id || m180_locked || m180_acomp.includes(id)) return;
    m180_acomp.push(id);
    m180_dirty = true;
    const inp = document.getElementById('m180-acomp-input');
    if (inp) inp.value = '';
    m180AcompRender();
};
window.m180AcompQuitar = function(id) {
    if (m180_locked) return;
    m180_acomp = m180_acomp.filter(x => x !== Number(id));
    m180_dirty = true;
    m180AcompRender();
};

const M180_ACTIVIDADES = {
    1: { id: 1, name: 'Conducción', short: 'COND', color: '#059669', soft: '#ecfdf5', ink: '#065f46' },
    2: { id: 2, name: 'Espera', short: 'ESP', color: '#d97706', soft: '#fffbeb', ink: '#92400e' },
    3: { id: 3, name: 'Tareas auxiliares', short: 'AUX', color: '#4f46e5', soft: '#eef2ff', ink: '#3730a3' },
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
        const hh = String(h).padStart(2, '0');
        rulerHtml += `<div class="m180-ruler-h" title="Hora ${hh}:00 a ${String(h + 1).padStart(2, '0')}:00">
            <div class="m180-ruler-header">
                <span class="m180-ruler-num">${hh}</span><small class="m180-ruler-min">:00</small>
            </div>
            <div class="m180-ruler-ticks">
                <span class="m180-tick t-00" title="${hh}:00"></span>
                <span class="m180-tick t-15" title="${hh}:15"></span>
                <span class="m180-tick t-30" title="${hh}:30"></span>
                <span class="m180-tick t-45" title="${hh}:45"></span>
            </div>
        </div>`;
    }
    ruler.innerHTML = rulerHtml;

    // Orden exacto de la libreta física chilena: 1. Conducción, 2. Espera, 3. Descanso, 4. Tareas Auxiliares
    lanes.innerHTML = [1, 2, 4, 3].map((actId, idx) => {
        const c = M180_ACTIVIDADES[actId];
        return `<div class="m180-lane" data-act="${actId}" style="--c:${c.color}; --soft:${c.soft}; --ink:${c.ink};">
            <div class="m180-lane-label"><span class="m180-lane-dot"></span><span>${idx + 1}. ${c.name}</span></div>
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
    if (typeof m180GpsPintar === 'function') m180GpsPintar();   // con GPS, también repinta «cosas por revisar»
    if (!m180_gps && typeof m180RevisionPintar === 'function') m180RevisionPintar();
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
        showToast(`Se marcaron ${empty} tramos libres (${(empty * 15) / 60} h) como descanso.`, "info");
    }
}

function limpiarGrilla180h() {
    if (m180_locked || !m180_slots.some(s => s !== 0)) return;
    m180PushHistory();
    m180_slots.fill(0);
    m180RenderBlocks();
    if (typeof showToast === 'function') {
        showToast("Se borró la libreta del día. Ctrl+Z la recupera.", "info");
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

    // La jornada efectiva, la espera y el descanso los muestra la línea de totales de «cosas por revisar» (m180RevisionPintar)
    void minEfec;

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

    // Límite de Configuración › Sistema › Libreta y GPS de choferes (sin límite configurado no se avisa)
    const alertaFatiga = document.getElementById('m180-alerta-fatiga');
    const limCont = m180_revision_ctx && m180_revision_ctx.limites ? m180_revision_ctx.limites.conduccion_continua_min : null;
    if (alertaFatiga) {
        if (limCont != null && maxConsecCond * 15 > limCont) {
            alertaFatiga.classList.remove('d-none');
            alertaFatiga.innerHTML = `<i class="bi bi-exclamation-triangle-fill me-1"></i> Alerta Art. 25 bis: conducción continua de ${formatMinToHHMM(maxConsecCond * 15)} hrs (límite: ${formatMinToHHMM(limCont)} hrs seguidas sin descanso).`;
        } else {
            alertaFatiga.classList.add('d-none');
        }
    }
}

// «Validar» solo sirve sobre un borrador ya guardado: la primera vez que se guarda un día siempre queda en borrador.
function m180ActualizarValidar() {
    const b = document.getElementById('btn-cerrar-guardar-180h');
    if (!b) return;
    if (m180_validado) { b.disabled = false; b.title = 'Guardar el cambio: el día sigue validado y queda registrado'; return; }
    b.disabled = !m180_chofer_tiene_datos;
    b.title = m180_chofer_tiene_datos ? 'Validar el día: se cierra y ya no se puede editar (solo eliminar)' : 'Primero guarda el borrador; después podrás validarlo';
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
}

function getLibretaAuthHeaders() {
    const token = localStorage.getItem('access_token') || localStorage.getItem('access_token') || window.AuthToken || '';
    return token ? { 'Authorization': `Bearer ${token}` } : {};
}

function m180SetBadge(kind) {
    const badge = document.getElementById('m180-badge-estado');
    if (!badge) return;
    if (kind === 'cerrado') {
        badge.className = 'badge bg-success-subtle text-success-emphasis border border-success px-2 py-1';
        badge.textContent = 'VALIDADO';
    } else if (kind === 'inasistencia') {
        badge.className = 'badge bg-danger-subtle text-danger-emphasis border border-danger px-2 py-1';
        badge.textContent = 'INASISTENCIA';
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

// Día validado abierto por alguien con el permiso «Editar libreta validada»: se puede editar y sigue validado (un solo botón «Guardar cambio»)
function m180ModoValidado(activo) {
    const banner = document.getElementById('m180-valedit-banner');
    if (banner) banner.classList.toggle('d-none', !activo);
    const borrador = document.querySelector('#modalMarcacion180h .m180-save-btn:not(#btn-cerrar-guardar-180h)');
    if (borrador) borrador.classList.toggle('d-none', activo);
    const btn = document.getElementById('btn-cerrar-guardar-180h');
    if (btn) btn.innerHTML = activo ? '<i class="bi bi-check-circle-fill me-1"></i> Guardar cambio' : '<i class="bi bi-check-circle-fill me-1"></i> Validar Día';
    if (activo) {
        m180SetLocked(false);
        const lock = document.getElementById('m180-lock-banner');
        if (lock) lock.classList.add('d-none');
    }
}

// Día que todavía no se puede llenar: la libreta va en orden dentro del tramo (o el período está cerrado, o el día no llega todavía)
function m180MostrarBloqueo(b) {
    const box = document.getElementById('m180-bloqueo');
    if (!box) return;
    if (!b) { box.classList.add('d-none'); box.innerHTML = ''; return; }
    m180SetLocked(true);
    const lock = document.getElementById('m180-lock-banner');
    if (lock) lock.classList.add('d-none');
    let acciones = '';
    if (b.motivo === 'PENDIENTE_ANTERIOR' && Array.isArray(b.pendientes) && b.pendientes.length) {
        const f = String(b.pendientes[0]);
        const corto = f.slice(8, 10) + '-' + f.slice(5, 7);
        acciones = '<div class="m180-bloqueo-acts">'
            + '<button type="button" class="m180-bk-btn pri" onclick="window.m180IrADia(\'' + f + '\')"><i class="bi bi-journal-text" aria-hidden="true"></i>Llenar libreta del ' + corto + '</button>'
            + '<button type="button" class="m180-bk-btn sec" onclick="window.m180JustificarDia(\'' + f + '\')"><i class="bi bi-clipboard2-check" aria-hidden="true"></i>Justificar el ' + corto + '</button>'
            + '<button type="button" class="m180-bk-btn dan" onclick="window.marcarInasistenciaLibreta(\'' + f + '\')"><i class="bi bi-person-x-fill" aria-hidden="true"></i>Marcar inasistencia el ' + corto + '</button>'
            + '</div>';
    }
    const titulo = b.motivo === 'PENDIENTE_ANTERIOR' ? 'Este día todavía no se puede llenar' : 'Este día no se puede llenar';
    box.innerHTML = '<div class="m180-bloqueo-ico"><i class="bi bi-hourglass-split" aria-hidden="true"></i></div>'
        + '<div class="m180-bloqueo-txt"><b>' + titulo + '</b>' + m180Esc(b.mensaje || '') + '</div>' + acciones;
    box.classList.remove('d-none');
}

// Abrir otro día de la misma persona (desde el aviso de día bloqueado)
window.m180IrADia = function (fecha) {
    m180_dirty = false;
    marcacionesManualesState.currentDate = fecha;
    proceedToMarcacion180h();
};

// Justificar un día pendiente (vacaciones, licencia, permiso…) desde el aviso de día bloqueado
window.m180JustificarDia = function (fecha) {
    const empId = parseInt(document.getElementById('m180-empleado-id').value);
    const nombre = document.getElementById('m180-conductor-nombre').textContent || '';
    m180_force_close = true;
    const modalEl = document.getElementById('modalMarcacion180h');
    const modal = modalEl && bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();
    if (typeof openJustifyModal === 'function') openJustifyModal(empId, nombre, fecha);
};

// Camión del día: el guardado con el día; si no hay, el del chofer o el que planificó Despacho Diario (Nexacol); se puede cambiar
const M180_SIN_CAMION = '__SIN_CAMION__';
const M180_OTRA_PATENTE = '__OTRA__';
const M180_OPCIONES_EXTRA = '<option value="' + M180_OTRA_PATENTE + '">Escribir otra patente…</option><option value="' + M180_SIN_CAMION + '">No anduvo en camión</option>';
const M180_ORIGEN_TXT = { PLAN: 'Propuesta de Despacho Diario (Nexacol)', MANUAL: 'Elegido a mano', CHOFER: 'El de su chofer', SIN_CAMION: 'No anduvo en camión' };
function m180PatenteTag(texto, gris) {
    const tag = document.getElementById('m180-patente-origen');
    if (!tag) return;
    tag.classList.toggle('d-none', !texto);
    tag.classList.toggle('gris', !!gris);
    tag.textContent = texto || '';
}
function m180SelPatente(vehiculoId, patente) {
    const sel = document.getElementById('m180-gps-patente');
    if (!sel) return;
    let opt = vehiculoId ? [...sel.options].find(o => o.value === String(vehiculoId)) : null;
    if (!opt) opt = [...sel.options].find(o => (o.dataset.patente || '').toUpperCase() === String(patente || '').toUpperCase());
    if (!opt && patente) {
        opt = document.createElement('option');
        opt.value = 'p:' + patente; opt.dataset.patente = patente; opt.textContent = patente;
        sel.appendChild(opt);
    }
    if (opt) sel.value = opt.value;
}
async function m180PatenteCargar(data, empId, fecha) {
    const sel = document.getElementById('m180-gps-patente');
    if (!sel) return;
    await m180GpsCargarVehiculos();
    sel.disabled = m180_locked || m180_chofer_id != null;   // el peoneta enlazado lleva el camión de su chofer
    if (data.patente_origen === 'SIN_CAMION') { sel.value = M180_SIN_CAMION; m180_patente_origen = 'SIN_CAMION'; m180PatenteTag(M180_ORIGEN_TXT.SIN_CAMION); m180GpsAuto(); return; }
    if (data.patente) {
        m180SelPatente(data.vehiculo_id, data.patente);
        m180_patente_origen = data.patente_origen || 'MANUAL';
        m180PatenteTag(data.patente_origen === 'PLAN' ? 'Guardado con el día · ' + M180_ORIGEN_TXT.PLAN : (M180_ORIGEN_TXT[data.patente_origen] || 'Guardado con el día'));
        m180GpsAuto();
        return;
    }
    try {
        const resp = await fetch('/api/asistencia/libreta-180h/gps/patente-propuesta/?empleado_id=' + encodeURIComponent(empId) + '&fecha=' + encodeURIComponent(fecha), { headers: getLibretaAuthHeaders() });
        const d = await resp.json().catch(() => ({}));
        if (String(document.getElementById('m180-fecha-str').value) !== String(fecha)) return;   // ya se abrió otro día
        if (resp.ok && Array.isArray(d.propuestas) && d.propuestas.length) {
            m180SelPatente(d.propuestas[0].vehiculo_id, d.propuestas[0].patente);
            m180_patente_origen = d.origen || 'PLAN';
            m180PatenteTag(M180_ORIGEN_TXT[m180_patente_origen] || '');
        } else {
            m180PatenteTag(d.mensaje || '', true);
        }
    } catch (_) { m180PatenteTag('No se pudo leer la planificación: elige el camión a mano.', true); }
    m180GpsAuto();   // con camión, el GPS aparece solo; sin camión, la comparación dice qué falta
}
let m180_patente_previa = '';
document.addEventListener('focusin', (e) => { if (e.target && e.target.id === 'm180-gps-patente') m180_patente_previa = e.target.value; });
document.addEventListener('change', async (e) => {
    if (!e.target || e.target.id !== 'm180-gps-patente') return;
    if (e.target.value === M180_OTRA_PATENTE) {   // camión que no está en la lista (o Nexacol no responde)
        const sel = e.target;
        const r = await Swal.fire({ title: 'Patente del camión', input: 'text', inputPlaceholder: 'Ej.: PKDD13', showCancelButton: true,
            confirmButtonText: 'Usar esta patente', cancelButtonText: 'Cancelar', confirmButtonColor: '#059669',
            inputValidator: v => (String(v || '').replace(/[^A-Za-z0-9]/g, '').length >= 4 ? null : 'Escribe la patente completa') });
        if (!r.isConfirmed) { sel.value = m180_patente_previa; return; }
        m180SelPatente(null, String(r.value).toUpperCase().replace(/[^A-Z0-9]/g, ''));
    }
    m180_patente_origen = e.target.value === M180_SIN_CAMION ? 'SIN_CAMION' : (e.target.value ? 'MANUAL' : null);
    m180PatenteTag(m180_patente_origen ? M180_ORIGEN_TXT[m180_patente_origen] : '');
    m180_dirty = true;
    m180GpsAuto();   // otro camión: su GPS se trae solo
});

// «¿A quién más le aplico este cambio?»: con el chofer, los acompañantes de su lista que no reciben la copia solos (su día validado o con
// horas propias, o todos si el día del chofer está validado); con un peoneta enlazado, el chofer y los otros acompañantes de ese día.
// Devuelve la lista elegida ([] = solo esta persona) o null si se canceló.
async function m180PreguntarReplicar() {
    const esPeoneta = m180_chofer_id != null;
    const cand = esPeoneta ? m180_enlazados.slice()
        : m180_enlazados.filter(e => m180_acomp.includes(e.empleado_id) && (m180_validado || e.validado || e.distinto));
    if (!cand.length) return [];
    const nombre = m180Esc(document.getElementById('m180-conductor-nombre').textContent || '');
    const fecha = window.formatFechaDDMMYYYY(document.getElementById('m180-fecha-str').value);
    const texto = esPeoneta ? 'Cambiaste el día de <b>' + nombre + '</b> (' + fecha + '). Su día viene de la copia de su chofer.'
        : (m180_validado ? 'Cambiaste el día validado de <b>' + nombre + '</b> (' + fecha + ').'
            : 'Algunos acompañantes tienen su día validado o con horas propias: no se les copia solo.');
    const filas = cand.map(e => '<label class="m180-rep-chk"><input type="checkbox" class="m180-rep-id" value="' + e.empleado_id + '"> '
        + m180Esc(e.nombre) + ' · ' + m180Esc(e.rol) + (e.validado ? ' · validado' : (e.distinto ? ' · con horas propias' : '')) + '</label>').join('');
    const html = '<div class="m180-rep"><p>' + texto + '</p>'
        + '<label class="m180-rep-opt"><input type="radio" name="m180-rep" value="solo" checked><span>Solo a ' + nombre + '<small>'
        + (esPeoneta ? 'El chofer queda como está' : 'Sus acompañantes quedan como están') + '</small></span></label>'
        + '<label class="m180-rep-opt"><input type="radio" name="m180-rep" value="mas"><span>' + (esPeoneta ? 'También a quienes anduvieron con él ese día' : 'También a sus acompañantes de ese día') + '</span></label>'
        + filas + (m180_validado ? '<div class="m180-rep-nota"><i class="bi bi-shield-check"></i> El día sigue validado. Queda registrado quién lo cambió, cuándo y qué horas cambiaron.</div>' : '') + '</div>';
    const r = await Swal.fire({
        title: '¿A quién más le aplico este cambio?', html, showCancelButton: true, focusConfirm: false,
        confirmButtonText: '<i class="bi bi-check-lg me-1"></i> Guardar cambio', cancelButtonText: 'Cancelar',
        confirmButtonColor: '#059669', cancelButtonColor: '#64748b',
        didOpen: (el) => {
            el.querySelectorAll('.m180-rep-id').forEach(chk => chk.addEventListener('change', () => {
                if (chk.checked) el.querySelector('input[name="m180-rep"][value="mas"]').checked = true;
            }));
            el.querySelector('input[name="m180-rep"][value="mas"]').addEventListener('change', () => {
                if (![...el.querySelectorAll('.m180-rep-id')].some(x => x.checked)) el.querySelectorAll('.m180-rep-id').forEach(x => { x.checked = true; });
            });
            el.querySelector('input[name="m180-rep"][value="solo"]').addEventListener('change', () => el.querySelectorAll('.m180-rep-id').forEach(x => { x.checked = false; }));
        },
        preConfirm: () => {
            const el = Swal.getPopup();
            if (el.querySelector('input[name="m180-rep"]:checked').value === 'solo') return [];
            return [...el.querySelectorAll('.m180-rep-id')].filter(x => x.checked).map(x => parseInt(x.value));
        }
    });
    return r.isConfirmed ? (r.value || []) : null;
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
    m180_acomp = [];
    m180_acomp_ocupados = [];
    document.getElementById('m180-observaciones').value = '';
    m180SetBadge('sin');
    m180SetLocked(false);
    m180_chofer_tiene_datos = false;
    m180ActualizarValidar();
    const btnDelDiaInit = document.getElementById('m180-btn-delete-dia');
    if (btnDelDiaInit) btnDelDiaInit.classList.add('d-none');
    m180_chofer_id = null;
    m180_validado = false;
    m180_enlazados = [];
    m180_revision_ctx = null;
    m180_patente_origen = null;
    m180MostrarBloqueo(null);
    m180ModoValidado(false);
    if (typeof m180GpsReset === 'function') m180GpsReset();

    try {
        const resp = await fetch(`/api/asistencia/libreta-180h/?empleado_id=${empId}&fecha=${dateStr}`, {
            headers: getLibretaAuthHeaders()
        });
        if (resp.ok) {
            const data = await resp.json();
            const btnDelDia = document.getElementById('m180-btn-delete-dia');
            if (btnDelDia) {
                if (data.has_data) {
                    btnDelDia.classList.remove('d-none');
                } else {
                    btnDelDia.classList.add('d-none');
                }
            }

            m180_acomp = (data.acompanantes || []).map(Number);
            m180_acomp_ocupados = (data.acompanantes_ocupados || []).map(Number);
            m180_chofer_id = data.chofer_id != null ? Number(data.chofer_id) : null;
            m180_chofer_tiene_datos = !!data.has_data;
            m180ActualizarValidar();
            if (data.has_data && Array.isArray(data.slots_96) && data.slots_96.length === 96) {
                m180_slots = data.slots_96.map(v => Number(v) || 0);
                // Registros viejos traían "Acompañante del chofer ID n" escrito a mano por el sistema: ya lo dice la tarjeta del chofer.
                const esInasistencia = String(data.observaciones || '').trimStart().startsWith('[INASISTENCIA]');
                document.getElementById('m180-observaciones').value = (data.observaciones || '').replace('[INASISTENCIA]', '').replace(/\s*·?\s*Acompañante del chofer ID \d+/g, '').trim();
                m180SetBadge(Number(data.cerrado) ? 'cerrado' : (esInasistencia ? 'inasistencia' : 'borrador'));
                m180SetLocked(Number(data.cerrado) === 1);
            }

            // Orden del tramo, día validado con permiso, enlazados y camión del día (04-11-2026)
            m180_enlazados = Array.isArray(data.enlazados) ? data.enlazados : [];
            m180_revision_ctx = data.revision || null;
            m180_validado = Number(data.cerrado) === 1;
            if (m180_validado && data.puede_editar_validado) m180ModoValidado(true);
            m180MostrarBloqueo(data.bloqueo || null);
            m180PatenteCargar(data, empId, dateStr);

            // Previsualización de fotografía archivada en el servidor (si existe)
            const previewContainer = document.getElementById('m180-ocr-preview-container');
            const previewImg = document.getElementById('m180-ocr-preview-img');
            if (data.foto_url && previewContainer && previewImg) {
                const authToken = localStorage.getItem('access_token') || localStorage.getItem('access_token') || '';
                const authFotoUrl = authToken ? `${data.foto_url}&token=${encodeURIComponent(authToken)}` : data.foto_url;
                previewImg.src = authFotoUrl;
                previewContainer.classList.remove('d-none');
                const textEl = previewContainer.querySelector('.small');
                if (textEl) {
                    textEl.innerHTML = `
                        <div class="d-flex align-items-center justify-content-between gap-2 flex-wrap">
                            <div><strong class="text-dark">Foto física archivada</strong> · Planilla respaldada en el servidor.</div>
                            <a href="${authFotoUrl}" target="_blank" class="btn btn-xs btn-outline-primary py-0 px-2" style="font-size:0.75rem;"><i class="bi bi-box-arrow-up-right me-1"></i>Ver en Grande</a>
                        </div>
                    `;
                }
            } else if (previewContainer && !window.m180_last_scanned_image) {
                previewContainer.classList.add('d-none');
            }
        } else {
            console.warn(`GET libreta-180h returned status ${resp.status}`);
            if (typeof showToast === 'function') showToast('No se pudo abrir lo guardado de este día. Vuelva a intentarlo.', 'warning');
            if (typeof m180GpsAuto === 'function') m180GpsAuto();
        }
    } catch (e) {
        console.warn("No se pudo cargar registro previo de libreta 180h:", e);
        if (typeof showToast === 'function') showToast('No se pudo abrir lo guardado de este día. Vuelva a intentarlo.', 'warning');
        if (typeof m180GpsAuto === 'function') m180GpsAuto();
    }

    refreshAllSlotsVisuals();
    m180AcompRender();
    m180ChoferRender();

    const modalEl = document.getElementById('modalMarcacion180h');
    if (modalEl) {
        m180AttachCloseGuard(modalEl);
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
}

async function guardarLibreta180h(cerrarDia = false, skipPrompt = false) {
    if (m180_locked) return;
    const empId = parseInt(document.getElementById('m180-empleado-id').value);
    const dateStr = document.getElementById('m180-fecha-str').value;
    const obs = document.getElementById('m180-observaciones').value.trim();

    const minTot = m180_slots.filter(s => s > 0).length * 15;
    if (!skipPrompt) {
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
        } else if (!cerrarDia && minTot < 1440 && minTot > 0) {
            // Preguntar al guardar borrador si desea autollenar el descanso (aplica para móvil o computador)
            const faltanMins = 1440 - minTot;
            const result = await Swal.fire({
                title: "¿Rellenar Descanso en el Borrador?",
                html: `Tienes <b>${formatMinToHHMM(minTot)} hrs</b> registradas y quedan <b>${formatMinToHHMM(faltanMins)} hrs</b> vacías.<br><br>¿Deseas rellenar automáticamente las horas restantes vacías con <b>Descanso</b> antes de guardar el borrador?`,
                icon: "question",
                showCancelButton: true,
                showDenyButton: true,
                confirmButtonColor: "#059669",
                denyButtonColor: "#3b82f6",
                cancelButtonColor: "#64748b",
                confirmButtonText: '<i class="bi bi-moon-stars me-1"></i> Rellenar descanso y guardar',
                denyButtonText: '<i class="bi bi-save me-1"></i> Guardar solo lo marcado',
                cancelButtonText: 'Seguir editando'
            });

            if (result.isConfirmed) {
                libreta180hAutoDescanso();
            } else if (!result.isDenied) {
                return;
            }
        }
    }

    const replicarA = await m180PreguntarReplicar();
    if (replicarA === null) return;

    const payload = {
        empleado_id: empId,
        fecha: dateStr,
        slots_96: m180_slots,
        cerrado: Boolean(cerrarDia),
        observaciones: obs,
        acompanantes: m180_acomp,
        imagen_base64: window.m180_last_scanned_image || null,
        replicar_a: replicarA
    };
    // Camión del día (el peoneta enlazado lleva el de su chofer: no se manda)
    const selP = document.getElementById('m180-gps-patente');
    if (selP && m180_chofer_id == null) {
        if (selP.value === M180_SIN_CAMION) {
            payload.patente_origen = 'SIN_CAMION';
        } else if (selP.value) {
            const opt = selP.selectedOptions[0];
            payload.patente = (opt && (opt.dataset.patente || opt.textContent || '').trim()) || null;
            payload.vehiculo_id = selP.value.startsWith('p:') ? null : selP.value;
            payload.patente_origen = m180_patente_origen || 'MANUAL';
        }
    }

    const buttons = document.querySelectorAll('#modalMarcacion180h .m180-save-btn');
    try {
        buttons.forEach(b => b.disabled = true);

        const resp = await fetch('/api/asistencia/libreta-180h/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getLibretaAuthHeaders()
            },
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
        window.m180_last_scanned_image = null;
        let res = {};
        try { res = await resp.json(); } catch (_) {}
        const d = res.data || {};
        if (typeof showToast === 'function') {
            showToast(d.editado_validado ? 'Listo. ' + (res.message || 'Cambio guardado.')
                : (cerrarDia ? "Listo. Día validado y guardado en la libreta (Art. 25 bis)." : "Listo. Borrador de la libreta guardado: queda abierto hasta que lo valides."), "success");
        }
        // Avisos: acompañantes con un día pendiente, quienes salieron de la lista y a quienes no se pudo copiar
        const avisos = [].concat(
            (d.acompanantes_con_pendientes || []).map(a => a.mensaje),
            (d.sacados || []).map(s => s.mensaje),
            (d.no_copiados || []).filter(n => n.motivo === 'VALIDADO' || n.motivo === 'PERIODO_CERRADO').map(n => n.mensaje)
        ).filter(Boolean);
        if (avisos.length) {
            Swal.fire({ icon: 'info', title: 'Para tener en cuenta', html: '<ul class="text-start mb-0">' + avisos.map(a => '<li>' + m180Esc(a) + '</li>').join('') + '</ul>', confirmButtonColor: '#059669' });
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
        m180ActualizarValidar();
    }
}


async function eliminarRegistroLibretaDia() {
    const empId = parseInt(document.getElementById('m180-empleado-id').value);
    const dateStr = document.getElementById('m180-fecha-str').value;
    const empNombre = document.getElementById('m180-conductor-nombre').textContent || 'el chofer';

    const confirmResult = await Swal.fire({
        title: '¿Eliminar registro del día?',
        html: `Se eliminarán permanentemente las horas y la foto archivada de <b>${empNombre}</b> para el día <b>${window.formatFechaDDMMYYYY(dateStr)}</b>.<br><br>El día volverá a su estado natural (Libre o Pendiente).`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#dc2626',
        cancelButtonColor: '#64748b',
        confirmButtonText: '<i class="bi bi-trash3-fill me-1"></i> Sí, eliminar registro',
        cancelButtonText: 'Cancelar'
    });

    if (!confirmResult.isConfirmed) return;

    const btnDel = document.getElementById('m180-btn-delete-dia');
    try {
        if (btnDel) btnDel.disabled = true;

        const resp = await fetch(`/api/asistencia/libreta-180h/?empleado_id=${empId}&fecha=${dateStr}`, {
            method: 'DELETE',
            headers: getLibretaAuthHeaders()
        });

        if (!resp.ok) {
            let errMsg = `Error ${resp.status} al eliminar`;
            try {
                const errData = await resp.json();
                if (errData.detail) errMsg = errData.detail;
            } catch (_) {}
            throw new Error(errMsg);
        }

        m180_dirty = false;
        window.m180_last_scanned_image = null;
        let resBorrado = {};
        try { resBorrado = await resp.json(); } catch (_) {}
        if (resBorrado.dias_posteriores_con_libreta > 0) {
            Swal.fire({ icon: 'info', title: 'Día borrado', text: resBorrado.message, confirmButtonColor: '#059669' });
        } else if (typeof showToast === 'function') {
            showToast('Listo. Se borró la libreta de este día y el día volvió a como estaba.', 'success');
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
    } catch (err) {
        console.error("Error eliminando registro de libreta:", err);
        Swal.fire({
            icon: 'error',
            title: 'No se pudo eliminar',
            text: err.message,
            confirmButtonColor: '#059669'
        });
    } finally {
        if (btnDel) btnDel.disabled = false;
    }
}


window.proceedToMarcacion180h = proceedToMarcacion180h;
window.setLibretaActividad = setLibretaActividad;
window.libreta180hAutoDescanso = libreta180hAutoDescanso;
window.libreta180hUndo = libreta180hUndo;
window.limpiarGrilla180h = limpiarGrilla180h;
window.guardarLibreta180h = guardarLibreta180h;
window.eliminarRegistroLibretaDia = eliminarRegistroLibretaDia;

// Registra la inasistencia del día en Marcaciones para quien se controla con libreta (bolsa de 180 horas).
async function marcarInasistenciaLibreta(fechaPendiente) {
    const empId = parseInt(document.getElementById('m180-empleado-id').value);
    const otroDia = typeof fechaPendiente === 'string' && fechaPendiente.length >= 10;
    const dateStr = otroDia ? fechaPendiente : document.getElementById('m180-fecha-str').value;
    const empNombre = document.getElementById('m180-conductor-nombre').textContent || 'el chofer';
    if (!otroDia && m180_slots.some(v => v > 0)) {
        Swal.fire({ icon: 'info', title: 'La libreta tiene tramos', text: 'Para marcar la inasistencia el día no debe tener tramos dibujados. Límpialos primero (o usa "Borrar Registro del Día").', confirmButtonColor: '#059669' });
        return;
    }
    const r = await Swal.fire({
        title: '¿Marcar inasistencia?',
        html: `Se registrará la <b>inasistencia</b> de <b>${empNombre}</b> el <b>${window.formatFechaDDMMYYYY(dateStr)}</b> en Marcaciones.<br><br><span class="text-muted small">Se puede deshacer con "Borrar Registro del Día".</span>`,
        icon: 'warning', showCancelButton: true, confirmButtonColor: '#dc2626', cancelButtonColor: '#64748b',
        confirmButtonText: '<i class="bi bi-person-x-fill me-1"></i> Sí, marcar inasistencia', cancelButtonText: 'Cancelar'
    });
    if (!r.isConfirmed) return;
    const btn = document.getElementById('m180-btn-inasistencia');
    try {
        if (btn) btn.disabled = true;
        const resp = await fetch('/api/asistencia/libreta-180h/inasistencia/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getLibretaAuthHeaders() },
            body: JSON.stringify({ empleado_id: empId, fecha: dateStr, observaciones: otroDia ? '' : (document.getElementById('m180-observaciones').value || '').trim() })
        });
        if (!resp.ok) {
            let errMsg = `Error ${resp.status} al registrar la inasistencia`;
            try { const d = await resp.json(); if (d.detail) errMsg = d.detail; } catch (_) {}
            throw new Error(errMsg);
        }
        m180_dirty = false;
        if (typeof showToast === 'function') showToast('Listo. Se registró la inasistencia.', 'success');
        if (otroDia) {   // vuelve a abrir el día que se quería llenar: ya puede estar libre (o muestra el siguiente pendiente)
            if (typeof window.reloadSingleEmployeeRow === 'function') window.reloadSingleEmployeeRow(empId);
            proceedToMarcacion180h();
            return;
        }
        const modalEl = document.getElementById('modalMarcacion180h');
        const modal = modalEl && bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
        if (typeof window.reloadSingleEmployeeRow === 'function') await window.reloadSingleEmployeeRow(empId);
        else if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
    } catch (err) {
        console.error('Error registrando inasistencia de libreta:', err);
        Swal.fire({ icon: 'error', title: 'No se pudo registrar', text: err.message, confirmButtonColor: '#059669' });
    } finally {
        if (btn) btn.disabled = false;
    }
}
window.marcarInasistenciaLibreta = marcarInasistenciaLibreta;

// ── Comparación de la libreta con el GPS del camión (Nexacol → Ruta GPS) ──────────────────────────────────────────────
// El servidor entrega el día del camión en 96 tramos de 15 min (0 sin dato / en planta, 1 en movimiento, 2 detenido) y sus paradas;
// acá se contrasta con los tramos que hay dibujados AHORA en la libreta (se actualiza al editar).
let m180_gps = null;
let m180_gps_vehiculos = null;
const M180_GPS_COLOR = { 0: '#e5e7eb', 1: '#16a34a', 2: '#f59e0b' };

// El GPS se trae solo con el camión del día (guardado con el día, propuesto por Despacho Diario o elegido a mano): sin botón (05-11-2026).
// m180_gps_tok descarta la respuesta de un camión o de un día que ya no está en pantalla.
let m180_gps_tok = 0;
function m180GpsAviso(html) {
    const r = document.getElementById('m180-gps-resultado');
    if (r) r.innerHTML = html ? '<div class="small text-secondary">' + html + '</div>' : '';
}
function m180GpsLimpiar(estadoTxt) {
    m180_gps = null; m180_gps_tok++;
    const e = document.getElementById('m180-gps-estado'); if (e) e.textContent = estadoTxt || '';
    m180GpsTabla(null);
    m180_gps_ent_tok++; m180_gps_ent = null; m180GpsEntregasPintar();
    if (typeof m180RevisionPintar === 'function') m180RevisionPintar();   // sin GPS: solo las reglas de la libreta
}
function m180GpsReset() {
    m180GpsLimpiar('Buscando el camión del día…');
    m180GpsAviso('');
    m180GpsCargarVehiculos();
}
function m180GpsAuto() {
    const sel = document.getElementById('m180-gps-patente');
    if (!sel) return;
    const v = sel.value || '';
    if (!v || v === M180_OTRA_PATENTE) {
        m180GpsLimpiar(); m180GpsAviso('<i class="bi bi-arrow-up-circle me-1"></i>Elige el <b>camión del día</b> (arriba) y el GPS aparece solo.'); return;
    }
    if (v === M180_SIN_CAMION) { m180GpsLimpiar(); m180GpsAviso('Este día no anduvo en camión: no hay GPS que comparar.'); return; }
    if (v.startsWith('p:')) {
        m180GpsLimpiar();
        if (!m180_gps_vehiculos) {   // la lista de camiones del GPS no llegó: no se puede saber si el camión está
            m180GpsAviso('<i class="bi bi-exclamation-circle me-1"></i>El GPS (Nexacol) no respondió: no se pudo leer su lista de camiones.'
                + ' <button type="button" class="btn btn-link btn-sm p-0 align-baseline fw-semibold" style="display:inline;" onclick="window.m180GpsReintentarLista()">Reintentar</button>');
        } else {
            m180GpsAviso('<b>' + m180GpsEsc(v.slice(2)) + '</b> no está en la plataforma de GPS: no hay recorrido que comparar.');
        }
        return;
    }
    m180GpsVer();
}
async function m180GpsReintentarLista() {
    const sel = document.getElementById('m180-gps-patente');
    if (!sel) return;
    const v = sel.value || '';
    const pat = v.startsWith('p:') ? v.slice(2) : '';
    m180GpsLimpiar('Buscando la lista de camiones…'); m180GpsAviso('');
    await m180GpsCargarVehiculos();
    if (pat) m180SelPatente(null, pat);
    m180GpsAuto();
}

const m180GpsEsShell = lugar => /^\s*shell\b/i.test(String(lugar || ''));
const M180_GPS_ICONO_SHELL = '<span class="m180-gps-shell-tag" title="Bencinera Shell"><i class="bi bi-fuel-pump-fill"></i></span> ';

// Tabla "GPS del camión" (tarjeta aparte, mismo formato de la línea de tiempo 24 h): una fila con lo que condujo y otra con lo que estuvo detenido. Sin datos de GPS queda oculta.
function m180GpsTabla(g) {
    const card = document.getElementById('m180-gps-card');
    if (!card) return;
    if (!g || !g.hay_datos) { card.style.display = 'none'; return; }
    const FILAS = { 1: ['b1', 't1', 'COND', 'Conduciendo', g.min_mov_gps], 2: ['b2', 't2', 'DET', 'Detenido', (g.paradas || []).reduce((a, p) => a + (p.min || 0), 0)] };
    [1, 2].forEach(v => {
        const [b, t, corto, largo, min] = FILAS[v];
        let html = '';
        // Conduciendo: la hora exacta de cada tramo en que el camión andaba (como las paradas, sin redondear a 15 min); si el servidor no los trae, los tramos de 15 min
        if (v === 1) {
            const tramos = Array.isArray(g.tramos_mov) ? g.tramos_mov : (g.slots_gps || []).reduce((a, x, i) => { if (x === 1) { const u = a[a.length - 1]; if (u && u[1] === i * 900) u[1] += 900; else a.push([i * 900, i * 900 + 900]); } return a; }, []);
            // Entre una parada y la siguiente el camión iba conduciendo: la fila queda continua, complementaria a Detenido (como la línea de tiempo de la libreta).
            // Solo se dibuja el tramo si el GPS vio movimiento dentro de él (así un hueco sin reportes no se pinta como conducción).
            const rs0 = g.resumen || {}, par = (g.paradas || []).map(p => [m180GpsSeg(p.desde), Math.max(m180GpsSeg(p.hasta), m180GpsSeg(p.desde) + 60)]).sort((a, b) => a[0] - b[0]);
            const puntos = [rs0.primero ? m180GpsSeg(rs0.primero) : null, ...par.flat(), rs0.ultimo ? m180GpsSeg(rs0.ultimo) : null];
            const entre = [];
            if (par.length && puntos[0] != null && puntos[puntos.length - 1] != null) {
                const lim = [[puntos[0], par[0][0]], ...par.slice(1).map((q, k) => [par[k][1], q[0]]), [par[par.length - 1][1], puntos[puntos.length - 1]]];
                lim.forEach(([a, b]) => { if (b - a >= 120 && (!Array.isArray(g.tramos_mov) || g.tramos_mov.some(([x, y]) => x < b && y > a))) entre.push([a, b]); });
            }
            const unidos = entre.length ? entre : tramos.reduce((o, [ini, fin]) => { const u = o[o.length - 1]; if (u && ini - u[1] < 300) u[1] = Math.max(u[1], fin); else o.push([ini, fin]); return o; }, []);
            unidos.forEach(([ini, fin]) => {
                const dur = formatMinToHHMM(Math.max(1, Math.round((fin - ini) / 60))), h = x => String(Math.floor(x / 3600)).padStart(2, '0') + ':' + String(Math.floor(x % 3600 / 60)).padStart(2, '0');
                html += `<div class="m180-block" style="left:${(ini / 86400) * 100}%; width:${((fin - ini) / 86400) * 100}%;" title="${h(ini)} – ${h(fin)} · ${largo} (${dur})"><b>${corto}</b><i>${dur}</i></div>`;
            });
        }
        // Cada parada (desde 5 min) con su hora EXACTA de llegada y salida
        // Numeradas igual que en la tabla de paradas; al pasar el mouse sale la misma información (hora y dirección)
        if (v === 2) (g.paradas || []).forEach((p, pi) => {
            const ini = m180GpsSeg(p.desde), fin = Math.max(m180GpsSeg(p.hasta), ini + 60);
            html += `<div class="m180-block m180-par-real" style="left:${(ini / 86400) * 100}%;width:${((fin - ini) / 86400) * 100}%" data-n="${pi + 1}" data-hora="${p.desde.slice(0, 5)}–${p.hasta.slice(0, 5)}" data-min="${p.min}" data-lugar="${m180GpsEsc(p.lugar)}" aria-label="Parada ${pi + 1}, ${p.desde.slice(0, 5)} a ${p.hasta.slice(0, 5)}, ${m180GpsEsc(p.lugar)}"><b>P${pi + 1}</b><i>${formatMinToHHMM(p.min)}</i></div>`;
        });
        // Paradas en una Shell: ícono sobre el tramo detenido (la plataforma de GPS nombra el lugar, "Shell, Ruta 5 Sur…")
        if (v === 2) (g.paradas || []).filter(p => m180GpsEsShell(p.lugar)).forEach(p => {
            const ini = m180GpsSeg(p.desde), fin = Math.max(m180GpsSeg(p.hasta), ini + 60);
            html += `<div class="m180-gps-shell" style="left:${(((ini + fin) / 2) / 86400) * 100}%;" title="Detenido en Shell · ${p.desde.slice(0, 5)}–${p.hasta.slice(0, 5)} (${p.min} min) · ${m180GpsEsc(p.lugar)}"><i class="bi bi-fuel-pump-fill"></i></div>`;
        });
        // Salida y regreso de la planta (primer y último reporte fuera de ella)
        if (v === 1) {
            const salio = ((g.planta || {}).salidas || 0) > 0, rs = g.resumen || {};
            [[rs.primero, salio ? 'Salió de la planta' : 'Primer reporte', 'bi-box-arrow-right'], [rs.ultimo, salio ? 'Volvió a la planta' : 'Último reporte', 'bi-box-arrow-in-left']].forEach(([hora, nombre, ic]) => {
                if (hora) html += `<div class="m180-gps-hito" style="left:${(m180GpsSeg(hora) / 86400) * 100}%" title="${nombre} ${String(hora).slice(0, 5)}"><i class="bi ${ic}"></i></div>`;
            });
        }
        // Entregas que calzan con una parada (o están muy cerca): ícono de caja sobre la detención
        if (v === 2 && m180_gps_ent && m180_gps_ent.entregas) m180_gps_ent.entregas.filter(e => e.parada && (e.estado === 'calza' || e.estado === 'calle' || e.estado === 'cercana')).forEach(e => {
            const ini = m180GpsSeg(e.parada.desde), fin = Math.max(m180GpsSeg(e.parada.hasta), ini + 60), st = M180_ENT_ESTADO[e.estado];
            html += `<div class="m180-gps-ent" style="left:${(((ini + fin) / 2) / 86400) * 100}%;--c:${st.c}" title="${st.t} · ${m180GpsEsc(e.cliente || '')}${e.dist_m != null ? ' · ' + e.dist_m + ' m de la parada' : ' · por dirección'}"><i class="bi bi-box-seam-fill"></i></div>`;
        });
        document.getElementById('m180-gps-' + b).innerHTML = html;
        document.getElementById('m180-gps-' + t).textContent = formatMinToHHMM(min || 0);
    });
    {
        const pl = g.planta || {}, rs = g.resumen || {}, salio = (pl.salidas || 0) > 0, h5 = x => String(x || '').slice(0, 5), partes = [];
        if (rs.primero) partes.push(`${salio ? 'Salió de la planta' : 'Primer reporte'} <b>${h5(rs.primero)}</b>`);
        if (rs.ultimo) partes.push(`${salio ? 'Volvió a la planta' : 'Último reporte'} <b>${h5(rs.ultimo)}</b>`);
        const sub = document.getElementById('m180-gps-card-sub');
        if (sub) sub.innerHTML = partes.join(' · ') || 'Solo lectura · lo que hizo el camión según el GPS';
    }
    const regla = document.getElementById('m180-ruler');
    if (regla) document.getElementById('m180-gps-ruler').innerHTML = regla.innerHTML;
    document.getElementById('m180-gps-card-titulo').textContent = 'GPS · ' + ((g.vehiculo && g.vehiculo.patente) || 'camión');
    card.style.display = '';
    m180GpsAjustarEtiquetas();
}

// Un bloque muestra solo lo que le cabe: nombre y duración, solo el nombre, o nada (la hora y la dirección salen al pasar el mouse)
function m180GpsAjustarEtiquetas() {
    document.querySelectorAll('#m180-gps-b1 .m180-block, #m180-gps-b2 .m180-block').forEach(el => {
        el.classList.remove('es-corto', 'es-mini');
        if (el.scrollWidth > el.clientWidth) el.classList.add('es-corto');
        if (el.scrollWidth > el.clientWidth) el.classList.add('es-mini');
    });
}
window.addEventListener('resize', () => { if (m180_gps) m180GpsAjustarEtiquetas(); });
// Las dos grillas (libreta y GPS) se desplazan juntas para que la misma hora quede siempre en la misma vertical
(function m180SincronizarDesplazamiento() {
    const a = document.getElementById('m180-grid-scroll'), b = document.querySelector('#m180-gps-card .m180-grid-container');
    if (!a || !b) return;
    let lock = false;
    [[a, b], [b, a]].forEach(([x, y]) => x.addEventListener('scroll', () => { if (lock) return; lock = true; y.scrollLeft = x.scrollLeft; requestAnimationFrame(() => { lock = false; }); }, { passive: true }));
})();

// Tarjeta flotante de una parada de la grilla del GPS: la misma información (hora y dirección) que la tabla de paradas
(function () {
    let tip = null, actual = null;
    const buscar = e => (e.target && e.target.closest ? e.target.closest('.m180-par-real') : null);
    const poner = (el, x, y) => {
        if (!tip) { tip = document.createElement('div'); tip.className = 'm180-par-tip'; document.body.appendChild(tip); }
        if (actual !== el) {
            actual = el;
            tip.innerHTML = `<div class="m180-par-tip-h"><span class="m180-par-n">P${m180GpsEsc(el.dataset.n)}</span> ${m180GpsEsc(el.dataset.hora)} · ${m180GpsEsc(el.dataset.min)} min</div><div>${el.dataset.lugar ? m180GpsEsc(el.dataset.lugar) : 'Sin dirección'}</div>`;
        }
        tip.classList.add('es-visible');
        const r = tip.getBoundingClientRect();
        tip.style.left = Math.max(8, Math.min(x + 14, window.innerWidth - r.width - 8)) + 'px';
        tip.style.top = Math.max(8, y - r.height - 14) + 'px';
    };
    document.addEventListener('mouseover', e => { const el = buscar(e); if (el) poner(el, e.clientX, e.clientY); });
    document.addEventListener('mousemove', e => { if (actual && tip && tip.classList.contains('es-visible')) { const el = buscar(e); if (el) poner(el, e.clientX, e.clientY); } });
    document.addEventListener('mouseout', e => { if (tip && buscar(e)) { tip.classList.remove('es-visible'); actual = null; } });
})();

// ── Facturas del camión contra sus paradas ────────────────────────────────────────────────────────────────
// Nexacol calza las facturas con el camión por su patente; el servidor mide cuánto está cada entrega de la parada más cercana del GPS
// (calza ≤ 150 m · muy cercana ≤ 500 m). Llega después de la ruta, así que la pantalla del GPS no espera por esto.
let m180_gps_ent = null;
let m180_gps_ent_tok = 0;
const M180_ENT_ESTADO = {
    calza:         { t: 'Calza con una parada', c: '#15803d', bg: '#dcfce7', ic: 'bi-check-circle-fill' },
    calle:         { t: 'Misma calle', c: '#0f766e', bg: '#ccfbf1', ic: 'bi-signpost-split-fill' },
    paso:          { t: 'Pasó por la calle', c: '#0e7490', bg: '#cffafe', ic: 'bi-sign-turn-right-fill' },
    cercana:       { t: 'Parada muy cercana', c: '#b45309', bg: '#fef3c7', ic: 'bi-record-circle-fill' },
    lejos:         { t: 'Sin parada cerca', c: '#b91c1c', bg: '#fee2e2', ic: 'bi-x-circle-fill' },
    comuna:        { t: 'Solo coincide la comuna', c: '#1d4ed8', bg: '#dbeafe', ic: 'bi-geo-alt-fill' },
    sin_parada:    { t: 'Sin parada en esa comuna', c: '#b91c1c', bg: '#fee2e2', ic: 'bi-x-circle-fill' },
    aprox:         { t: 'Dirección aproximada', c: '#475569', bg: '#e2e8f0', ic: 'bi-geo-fill' },
    sin_ubicacion: { t: 'No se pudo ubicar', c: '#475569', bg: '#e2e8f0', ic: 'bi-question-circle-fill' }
};

async function m180GpsEntregas(vehiculoId, fecha) {
    const tok = ++m180_gps_ent_tok;
    m180_gps_ent = { cargando: true };
    m180GpsEntregasPintar();
    try {
        const resp = await fetch(`/api/asistencia/libreta-180h/gps/entregas/?vehiculo_id=${encodeURIComponent(vehiculoId)}&fecha=${encodeURIComponent(fecha)}`, { headers: getLibretaAuthHeaders() });
        const d = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(d.detail || `Error ${resp.status}`);
        if (tok !== m180_gps_ent_tok) return;
        m180_gps_ent = d;
    } catch (err) {
        if (tok !== m180_gps_ent_tok) return;
        m180_gps_ent = { error: err.message };
    }
    m180GpsEntregasPintar();
    m180GpsPintar();   // las paradas y la línea de tiempo señalan a qué entrega corresponde cada una
}

function m180GpsEntregasPintar() {
    const card = document.getElementById('m180-gps-entregas');
    if (!card) return;
    const d = m180_gps_ent;
    if (!d) { card.style.display = 'none'; return; }
    const primera = card.style.display === 'none';
    card.style.display = '';
    if (primera) { card.classList.remove('mx-entra'); void card.offsetWidth; card.classList.add('mx-entra'); }
    const body = document.getElementById('m180-ent-body'), sub = document.getElementById('m180-ent-sub');
    const esc = m180GpsEsc;
    if (d.cargando) {
        sub.textContent = 'Buscando las facturas de esta salida…';
        body.innerHTML = '<div class="mx-skel" role="status"><span class="visually-hidden">Cargando facturas…</span>' + Array.from({ length: 4 }, (_, n) => `<div class="mx-skel-fila" style="--d:${n * 80}ms"><i></i><i></i><i></i><i></i><i></i><i></i></div>`).join('') + '</div>';
        return;
    }
    if (d.error) { sub.textContent = ''; body.innerHTML = `<div class="alert alert-warning py-2 small mb-0"><i class="bi bi-exclamation-triangle me-1"></i>No se pudieron cargar las facturas del camión: ${esc(d.error)}</div>`; return; }
    sub.textContent = d.desde ? `Facturas emitidas el ${m180GpsFechaCorta(d.desde)} · calzadas por la patente ${esc(d.patente)}` : `Calzadas por la patente ${esc(d.patente)}`;
    if (!d.salio) { body.innerHTML = '<div class="alert alert-secondary py-2 small mb-0">El camión casi no se movió este día: no salió a repartir.</div>'; return; }
    if (!d.entregas.length) { body.innerHTML = `<div class="alert alert-secondary py-2 small mb-0">No hay facturas emitidas para esta salida de ${esc(d.patente)}.</div>`; return; }
    const r = d.resumen || {}, U = d.umbrales || { calza_m: 150, cerca_m: 500 };
    // En el orden del recorrido del camión: a la hora de su parada; las que solo coinciden en la comuna, a la hora en que el camión llegó por primera vez a esa
    // comuna; las de comunas donde no paró, al final.
    const orden = e => (e.parada ? m180GpsSeg(e.parada.desde)
        : (e.paradas_comuna && e.paradas_comuna.length ? Math.min(...e.paradas_comuna.map(p => m180GpsSeg(p.desde)))
            : (e.paso && e.paso.pasadas && e.paso.pasadas.length ? m180GpsSeg(e.paso.pasadas[0].desde) : 99999)));
    const entregas = d.entregas.slice().sort((a, b) => orden(a) - orden(b));
    const kpi = (n, txt, k) => `<span class="m180-ent-kpi" style="--c:${M180_ENT_ESTADO[k].c};--bg:${M180_ENT_ESTADO[k].bg}"><b>${n}</b> ${txt}</span>`;
    const filas = entregas.map((e, i) => {
        const st = M180_ENT_ESTADO[e.estado] || M180_ENT_ESTADO.sin_ubicacion;
        const pct = e.dist_m == null ? 0 : Math.min(e.dist_m, 1000) / 10;
        const dir = [e.calle, e.comuna].filter(Boolean).map(esc).join(', ');
        // Una fila corta: quién y dónde, cuál fue la parada (o por qué no hay) y un solo estado; el detalle sale al pasar el mouse sobre el estado
        const hora = q => `${esc(String(q.desde).slice(0, 5))}–${esc(String(q.hasta).slice(0, 5))} · ${q.min} min`;
        const par = e.parada
            ? `<div class="m180-ent-hora" title="Parada P${e.parada_idx + 1} del recorrido (la numeración de la grilla y de la tabla de paradas)">${hora(e.parada)}</div>
               ${e.dist_m != null
                    ? `<div class="m180-ent-barra"><span style="width:${pct}%;background:${st.c}"></span><u style="left:${U.calza_m / 10}%"></u><u style="left:${U.cerca_m / 10}%"></u></div><small>${e.dist_m} m de la parada${e.aprendida ? ' · ubicación aprendida' : ''}</small>`
                    : `<small class="m180-ent-lugar" title="${esc(e.parada.lugar)}">${esc(String(e.parada.lugar || '').split(',').slice(0, 2).join(',').trim())}</small>`}`
            : (e.paradas_comuna && e.paradas_comuna.length
                ? `<div class="m180-ent-hora text-muted">Sin parada identificada</div><small class="m180-ent-lugar" title="${esc(e.paradas_comuna.map(q => String(q.desde).slice(0, 5) + ' (' + q.min + ' min)').join(' · '))}">El camión paró ${e.paradas_comuna.length} ${e.paradas_comuna.length === 1 ? 'vez' : 'veces'} en ${esc(e.comuna)}</small>`
                : '<div class="m180-ent-hora text-muted">El camión no paró en esa comuna</div>');
        // Si no hay parada pero el recorrido pasó por la calle, se dice (el caso contrario no se muestra: «no se detectó» era ruido)
        const ps = e.paso;
        const unicos = arr => arr.filter((v, k, a) => a.indexOf(v) === k);
        const pasoHtml = (!ps || ps.estado !== 'paso' || e.parada || ps.origen === 'parada') ? ''
            : `<div class="m180-ent-paso es-si" title="${esc(ps.pasadas.map(x => x.nombre + ' ' + x.desde + '–' + x.hasta).join(' · '))}"><i class="bi bi-sign-turn-right-fill" aria-hidden="true"></i> Pasó por ${esc(unicos(ps.pasadas.map(x => x.nombre)).slice(0, 2).join(' y '))} a las ${esc(unicos(ps.pasadas.map(x => x.desde)).slice(0, 3).join(', '))}${ps.esquina ? ' · por la esquina' : ''}</div>`;
        const tip = e.estado === 'calle' ? 'Hay una parada en la misma calle y comuna que la factura. El GPS no da el número ni la cuadra.' + (e.esquina && (e.coincide || []).length < 2 ? ' Es una esquina y la parada coincide solo con ' + (e.coincide || []).join(', ') + '.' : '')
            : e.estado === 'calza' ? `La parada queda a menos de ${U.calza_m} m de la dirección del cliente.`
            : e.estado === 'cercana' ? `La parada queda a menos de ${U.cerca_m} m de la dirección del cliente.`
            : e.estado === 'comuna' ? 'El camión paró en esa comuna, pero ninguna parada nombra la calle de la factura.'
            : e.estado === 'sin_parada' ? 'El camión no paró en la comuna de la factura.' : '';
        return `<div class="m180-ent-fila" style="--d:${i * 55}ms;--c:${st.c};--bg:${st.bg}">
            <span class="m180-ent-ic"><i class="bi ${st.ic}" aria-hidden="true"></i></span>
            <div class="m180-ent-main"><div class="m180-ent-cli"><span class="m180-ent-n">${i + 1}</span>${esc(e.cliente || 'Sin cliente')}</div><div class="m180-ent-dir">${dir || 'Sin dirección'} · ${e.folios.map(f => 'Folio ' + esc(String(f).replace(/^DTE-JJV-Folio-/, ''))).join(', ')}</div>${pasoHtml}</div>
            <div class="m180-ent-par">${par}</div>
            <span class="m180-ent-badge" title="${esc(tip)}">${st.t}</span></div>`;
    }).join('');
    body.innerHTML = `<div class="m180-ent-kpis">${kpi(r.calle || 0, 'en la misma calle', 'calle')}${r.calza ? kpi(r.calza, 'calzan (≤ ' + U.calza_m + ' m)', 'calza') : ''}${r.cercana ? kpi(r.cercana, 'muy cercanas', 'cercana') : ''}${kpi(r.comuna || 0, 'solo en la comuna', 'comuna')}${kpi((r.lejos || 0) + (r.sin_parada || 0), 'sin parada', 'lejos')}${entregas.some(e => e.paso) ? kpi(entregas.filter(e => e.paso && e.paso.estado === 'paso').length, 'pasó por su calle', 'paso') : ''}<span class="m180-ent-nota">${r.total} ${r.total === 1 ? 'entrega' : 'entregas'} · «misma calle» = la calle y la comuna de la factura están en la dirección de una parada (el GPS no da el número)</span></div><div class="m180-ent-lista">${filas}</div>`;
}
function m180GpsFechaCorta(iso) { const p = String(iso || '').split('-'); return p.length === 3 ? `${p[2]}-${p[1]}-${p[0]}` : iso; }

// Patentes de la plataforma de GPS (una vez por sesión); recuerda la última elegida para ese empleado.
async function m180GpsCargarVehiculos() {
    const sel = document.getElementById('m180-gps-patente');
    if (!sel) return;
    const elegir = () => {
        const emp = document.getElementById('m180-empleado-id').value;
        let guardada = ''; try { guardada = localStorage.getItem('asistencia_gps_patente:' + emp) || ''; } catch (_) {}
        sel.value = '';   // el camión del día lo pone m180PatenteCargar (guardado con el día o propuesto por Despacho Diario)
        void guardada;
    };
    if (m180_gps_vehiculos) { elegir(); return; }
    try {
        const resp = await fetch('/api/asistencia/libreta-180h/gps/vehiculos/', { headers: getLibretaAuthHeaders() });
        const d = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(d.detail || `Error ${resp.status}`);
        m180_gps_vehiculos = d.vehiculos || [];
        sel.innerHTML = '<option value="">Elegir patente…</option>' + m180_gps_vehiculos.map(v => '<option value="' + m180Esc(v.id) + '" data-patente="' + m180Esc(v.patente) + '">' + m180Esc(v.patente) + '</option>').join('')
            + M180_OPCIONES_EXTRA;
        elegir();
    } catch (err) {
        sel.innerHTML = '<option value="">Lista de camiones no disponible</option>' + M180_OPCIONES_EXTRA;
        const e = document.getElementById('m180-gps-estado'); if (e) e.textContent = err.message;
    }
}

// Trae el día del camión elegido (lo llama m180GpsAuto; «Reintentar» solo aparece si el GPS no respondió).
async function m180GpsVer() {
    const sel = document.getElementById('m180-gps-patente');
    const v = sel ? sel.value : '';
    if (!v || v === M180_OTRA_PATENTE || v === M180_SIN_CAMION || v.startsWith('p:')) { m180GpsAuto(); return; }
    const emp = document.getElementById('m180-empleado-id').value;
    const fecha = document.getElementById('m180-fecha-str').value;
    const opt = sel.options[sel.selectedIndex];
    const patente = (opt && (opt.dataset.patente || opt.textContent)) || '';
    try { localStorage.setItem('asistencia_gps_patente:' + emp, v); } catch (_) {}
    m180GpsLimpiar('Trayendo el GPS de ' + patente + '…');
    m180GpsAviso('');
    const tok = m180_gps_tok;
    try {
        const resp = await fetch(`/api/asistencia/libreta-180h/gps/dia/?vehiculo_id=${encodeURIComponent(v)}&fecha=${encodeURIComponent(fecha)}`, { headers: getLibretaAuthHeaders() });
        const d = await resp.json().catch(() => ({}));
        if (tok !== m180_gps_tok) return;   // mientras tanto cambió el camión o se abrió otro día
        if (!resp.ok) throw new Error(d.detail || `Error ${resp.status}`);
        m180_gps = d;
        document.getElementById('m180-gps-estado').textContent = '';
        m180GpsPintar();
        m180GpsEntregas(v, fecha);
    } catch (err) {
        if (tok !== m180_gps_tok) return;
        m180GpsLimpiar();
        m180GpsAviso('<i class="bi bi-exclamation-circle me-1"></i>No se pudo traer el GPS de <b>' + m180GpsEsc(patente) + '</b>: ' + m180GpsEsc(err.message)
            + ' <button type="button" class="btn btn-link btn-sm p-0 align-baseline fw-semibold" style="display:inline;" onclick="window.m180GpsVer()">Reintentar</button>');
    }
}

function m180GpsHora(i) { return String(Math.floor(i / 4)).padStart(2, '0') + ':' + String((i % 4) * 15).padStart(2, '0'); }
function m180GpsSeg(hms) { const p = String(hms || '').split(':').map(Number); return (p[0] || 0) * 3600 + (p[1] || 0) * 60 + (p[2] || 0); }
function m180GpsEsc(t) { return String(t == null ? '' : t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

// Comparación tramo a tramo de la libreta con el GPS: la usan el detalle de paradas y «cosas por revisar».
// Tramos: 0 sin dato / en planta, 1 en movimiento, 2 detenido. Las tareas auxiliares no se juzgan (el camión puede estar andando o detenido).
function m180GpsComparar() {
    const g = m180_gps;
    if (!g || !g.hay_datos) return null;
    const sl = m180_slots;
    const marca = new Array(96).fill('');
    let juzgados = 0, fallan = 0;
    for (let i = 0; i < 96; i++) {
        const act = sl[i] || 0, gp = g.slots_gps[i];
        if (gp === 0 || act === 3) continue;
        juzgados++;
        if (act === 1 && gp === 2) marca[i] = 'cond_detenido';
        else if ((act === 2 || act === 4) && gp === 1) marca[i] = 'espera_mov';
        else if (act === 0 && gp === 1) marca[i] = 'sin_libreta_mov';
        if (marca[i]) fallan++;
    }
    const rangos = [];
    for (let i = 0; i < 96;) {
        if (!marca[i]) { i++; continue; }
        let j = i; while (j < 96 && marca[j] === marca[i]) j++;
        rangos.push({ de: i, a: j, tipo: marca[i] }); i = j;
    }
    // Paradas del GPS contra lo que la libreta tenía en ese momento
    const paradas = (g.paradas || []).map((p, pi) => {
        const ini = m180GpsSeg(p.desde), fin = Math.max(m180GpsSeg(p.hasta), ini + 60);
        const m = { 0: 0, 1: 0, 2: 0, 3: 0, 4: 0 };
        for (let i = 0; i < 96; i++) { const ov = Math.min(fin, (i + 1) * 900) - Math.max(ini, i * 900); if (ov > 0) m[sl[i] || 0] += ov / 60; }
        const total = Object.values(m).reduce((x, y) => x + y, 0) || 1;
        const estado = m[1] / total >= 0.5 ? 'cond' : (m[0] / total >= 0.5 ? 'sin' : 'ok');
        return { n: pi + 1, p, m, estado };
    });
    return { marca, juzgados, fallan, rangos, paradas };
}

// Detalle de las paradas del camión (lo de arriba lo dice «cosas por revisar»)
function m180GpsPintar() {
    const host = document.getElementById('m180-gps-resultado');
    if (!host || !m180_gps) return;
    const g = m180_gps;
    const patente = m180GpsEsc(g.vehiculo && g.vehiculo.patente);
    if (!g.hay_datos) {
        m180GpsTabla(null);
        host.innerHTML = `<div class="alert alert-secondary py-2 small mb-0">${g.todo_el_dia_en_planta ? 'El camión estuvo todo el día dentro de la planta.' : 'El GPS no tiene datos de ' + patente + ' en este día.'}</div>`;
        m180RevisionPintar();
        return;
    }
    const cmp = m180GpsComparar();
    m180GpsTabla(g);
    const filasParadas = cmp.paradas.map(({ n, p, m, estado }) => {
        const badge = estado === 'cond' ? `<span class="badge bg-danger">libreta: conducción</span>`
            : estado === 'sin' ? `<span class="badge bg-warning text-dark">libreta: sin registrar</span>` : `<span class="badge bg-success">calza</span>`;
        const det = [m[2] ? `${Math.round(m[2])} min espera` : '', m[4] ? `${Math.round(m[4])} min descanso` : '', m[3] ? `${Math.round(m[3])} min aux.` : '', m[1] ? `${Math.round(m[1])} min conducción` : '', m[0] ? `${Math.round(m[0])} min sin registrar` : ''].filter(Boolean).join(' · ');
        const ent = m180_gps_ent && m180_gps_ent.paradas && m180_gps_ent.paradas[n - 1];
        const entTag = ent ? '<div class="m180-ent-tag es-' + ent.estado + '"><i class="bi bi-box-seam-fill"></i> ' + (ent.estado === 'calle' ? 'Misma calle' : 'Entrega') + ': '
            + m180GpsEsc(ent.cliente || '') + (ent.dist_m != null ? ' · ' + ent.dist_m + ' m' : '') + '</div>' : '';
        return `<tr><td><span class="m180-par-n">P${n}</span></td><td class="text-nowrap">${p.desde.slice(0, 5)}–${p.hasta.slice(0, 5)}</td><td class="text-end">${p.min} min</td><td>${m180GpsEsShell(p.lugar) ? M180_GPS_ICONO_SHELL : ''}${m180GpsEsc(p.lugar) || '—'}${entTag}</td><td>${badge}<div class="text-muted" style="font-size:.82rem">${det}</div></td></tr>`;
    }).join('');
    host.innerHTML = `<div class="m180-rev-det-t">Paradas del camión ${patente} (${cmp.paradas.length}, desde 5 min)</div>
        ${filasParadas ? `<div class="table-responsive" style="max-height:420px;overflow:auto"><table class="table align-middle mb-0 m180-par-tabla" style="font-size:.95rem"><thead><tr><th>N°</th><th>Hora</th><th class="text-end">Duración</th><th>Lugar</th><th>Libreta en ese tramo</th></tr></thead><tbody>${filasParadas}</tbody></table></div>` : '<div class="text-muted small">Sin paradas de 5 minutos o más fuera de la planta.</div>'}`;
    m180RevisionPintar();
}

// ── «Cosas por revisar» (pedido del dueño, 05-11-2026) ─────────────────────────────────────────────────────────────────────────────────
// Compara la libreta con el GPS del camión y con las reglas del Art. 25 bis. Los límites vienen de Configuración › Sistema › Libreta y GPS
// de choferes (m180_revision_ctx.limites); una regla sin límite configurado no se evalúa. Se repinta al editar la libreta y al llegar el GPS.
const M180_REV_TRABAJO_ASIS = ['OK', 'ATRASO', 'SALIDA_ADELANTADA', 'ATR_SAD', 'EXTRA', 'EN_CURSO', 'PENDIENTE', 'JORNADA_ESPECIAL'];
const M180_REV_EST = {
    ok:  { t: 'En orden', i: 'bi-check-circle-fill' },
    rev: { t: 'Revisar', i: 'bi-exclamation-triangle-fill' },
    mal: { t: 'Fuera de norma', i: 'bi-x-octagon-fill' }
};
function m180RevHora(min) { const m = Math.floor(min); return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0'); }
function m180RevDur(min) { min = Math.round(Math.abs(min)); return Math.floor(min / 60) + ':' + String(min % 60).padStart(2, '0'); }
function m180RevDurTxt(min) { min = Math.round(Math.abs(min)); const h = Math.floor(min / 60), m = min % 60; return (h ? h + ' h' : '') + (h && m ? ' ' : '') + (m || !h ? m + ' min' : ''); }
function m180RevPill(k) { const e = M180_REV_EST[k]; return `<span class="m180-rev-pill es-${k}"><i class="bi ${e.i}" aria-hidden="true"></i>${e.t}</span>`; }
function m180RevTramo(de, a) { return `<button type="button" class="m180-rev-tramo" onclick="window.m180MarcarTramo(${de}, ${a})" title="Marcar este tramo en las líneas de tiempo">${m180GpsHora(de)}–${m180GpsHora(a)}</button>`; }

function m180RevisionPintar() {
    const host = document.getElementById('m180-revision');
    if (!host) return;
    const sl = (m180_slots || []).map(Number);
    const ctx = m180_revision_ctx || {};
    const lim = ctx.limites || {};
    const tol = lim.tolerancia_min;
    const cnt = a => sl.filter(v => v === a).length * 15;
    const L = { cond: cnt(1), esp: cnt(2), aux: cnt(3), desc: cnt(4) };
    L.efec = L.cond + L.aux;
    const trabajo = sl.map((v, i) => (v === 1 || v === 2 || v === 3) ? i : -1).filter(i => i >= 0);
    const g = m180_gps && m180_gps.hay_datos ? m180_gps : null;
    const cmp = g ? m180GpsComparar() : null;
    const r = (g && g.resumen) || {};
    const G = g ? { salida: m180GpsSeg(r.primero) / 60, llegada: m180GpsSeg(r.ultimo) / 60, mov: g.min_mov_gps, vel: r.velMax, km: r.km, patente: (g.vehiculo && g.vehiculo.patente) || '' } : null;

    const tira = () => {
        const it = (t, v, c) => `<span class="m180-rev-tot"><span class="m180-rev-dot" style="background:${c}" aria-hidden="true"></span><span>${t}</span><b>${v}</b></span>`;
        return `<div class="m180-rev-tira">${it('Conducción', m180RevDur(L.cond), M180_ACTIVIDADES[1].color)}${it('Tareas auxiliares', m180RevDur(L.aux), M180_ACTIVIDADES[3].color)}${it('Espera', m180RevDur(L.esp), M180_ACTIVIDADES[2].color)}${it('Descanso', m180RevDur(L.desc), M180_ACTIVIDADES[4].color)}
            <span class="m180-rev-tot es-fuerte"><span>Jornada efectiva</span><b>${m180RevDur(L.efec)}</b></span>${G && G.km != null ? '<span class="m180-rev-tot"><span>Recorrido</span><b>' + String(G.km).replace('.', ',') + ' km</b></span>' : ''}</div>`;
    };
    if (!trabajo.length) {
        host.innerHTML = `<header class="m180-rev-head"><h3 class="m180-rev-big" id="m180-rev-titulo">La libreta todavía no tiene horas de trabajo</h3>
            <p class="m180-rev-sub">Cuando se marquen conducción, espera o tareas, aquí aparece lo que hay que revisar contra el GPS y las reglas del Art. 25 bis.</p></header>${tira()}`;
        return;
    }
    L.ini = trabajo[0] * 15; L.fin = (trabajo[trabajo.length - 1] + 1) * 15;

    const hall = [], orden = [], sinRevisar = [];
    const minDe = rs => rs.reduce((s, x) => s + (x.a - x.de) * 15, 0);

    // 1. Conducción continua (Art. 25 bis)
    const corridas = [];
    for (let i = 0; i < 96;) { if (sl[i] !== 1) { i++; continue; } let j = i; while (j < 96 && sl[j] === 1) j++; corridas.push({ de: i, a: j }); i = j; }
    const maxCont = corridas.reduce((m, c) => Math.max(m, (c.a - c.de) * 15), 0);
    if (lim.conduccion_continua_min == null) sinRevisar.push('conducción continua (falta configurar el límite)');
    else {
        const excesos = corridas.filter(c => (c.a - c.de) * 15 > lim.conduccion_continua_min);
        if (excesos.length) hall.push({ k: 'mal', t: `La libreta marca <b>${m180RevDurTxt(maxCont)}</b> de conducción seguida, sobre el límite de ${m180RevDurTxt(lim.conduccion_continua_min)}`,
            s: 'El Art. 25 bis no permite manejar más tiempo seguido sin un descanso.', tramos: excesos });
        else if (L.cond) orden.push(`Conducción continua máx. ${m180RevDur(maxCont)} (límite ${m180RevDur(lim.conduccion_continua_min)})`);
    }

    // 2. Descanso ininterrumpido antes de empezar: el del comienzo del día más el del final del día anterior
    let lead = 0; while (lead < 96 && sl[lead] === 4) lead++;
    const prev = ctx.dia_anterior || null;
    const fechaPrev = prev && prev.fecha ? window.formatFechaDDMMYYYY(prev.fecha) : 'el día anterior';
    if (lim.descanso_min == null) sinRevisar.push('descanso (falta configurar el mínimo)');
    else if (!prev) sinRevisar.push('descanso antes de empezar (no se pudo leer el día anterior)');
    else if (prev.tiene_libreta) {
        const antes = prev.descanso_final_min + lead * 15;
        if (antes < lim.descanso_min) hall.push({ k: 'mal', t: `Descanso antes de empezar: <b>${m180RevDurTxt(antes)}</b>, bajo el mínimo de ${m180RevDurTxt(lim.descanso_min)} seguidas`,
            s: `Cuenta el descanso del final del ${fechaPrev} (${m180RevDurTxt(prev.descanso_final_min)}) y el del comienzo de este día (${m180RevDurTxt(lead * 15)}).`, tramos: lead ? [{ de: 0, a: lead }] : [] });
        else orden.push(`Descanso antes de empezar ${m180RevDur(antes)} (mínimo ${m180RevDur(lim.descanso_min)})`);
    } else if (M180_REV_TRABAJO_ASIS.includes(String(prev.estado || '').toUpperCase())) {
        sinRevisar.push(`descanso antes de empezar (el ${fechaPrev} no tiene libreta)`);
    } else {
        orden.push(`Descanso antes de empezar: el ${fechaPrev} no trabajó`);
    }

    // 3. Contra el GPS del camión
    if (!g) {
        sinRevisar.push(m180_gps && !m180_gps.hay_datos ? 'comparación con el GPS (no tiene datos de ese día)' : 'comparación con el GPS (sin camión con GPS)');
    } else {
        const condDet = cmp.rangos.filter(x => x.tipo === 'cond_detenido'), espMov = cmp.rangos.filter(x => x.tipo === 'espera_mov'), sinMov = cmp.rangos.filter(x => x.tipo === 'sin_libreta_mov');
        const parCond = cmp.paradas.filter(x => x.estado === 'cond');
        if (condDet.length) hall.push({ k: 'rev', t: `La libreta marca <b>conducción</b> en ${minDe(condDet) / 15} ${minDe(condDet) === 15 ? 'tramo' : 'tramos'} con el camión <b>detenido</b> (${m180RevDurTxt(minDe(condDet))})`,
            s: parCond.length ? `Coinciden con ${parCond.length} ${parCond.length === 1 ? 'parada' : 'paradas'} del camión (${parCond.map(x => 'P' + x.n).join(', ')}). Si fueron entregas, van como tareas auxiliares.` : 'Si el camión estaba detenido trabajando, va como tareas auxiliares o espera.', tramos: condDet });
        if (tol == null) sinRevisar.push('hora de inicio, de término y conducción (falta configurar la tolerancia con el GPS)');
        else {
            const difIni = L.ini - G.salida, difFin = L.fin - G.llegada, difCond = L.cond - G.mov;
            if (difFin > tol) hall.push({ k: 'rev', t: `La libreta termina a las <b>${m180RevHora(L.fin)}</b> y el camión volvió a la planta a las <b>${m180RevHora(G.llegada)}</b>`,
                s: `${m180RevDurTxt(difFin)} de trabajo después de volver. Si fueron tareas en la planta, está bien; si no, sobran horas en la libreta.`, tramos: [] });
            else if (difFin < -tol) hall.push({ k: 'rev', t: `El camión volvió a la planta a las <b>${m180RevHora(G.llegada)}</b> y la libreta termina a las <b>${m180RevHora(L.fin)}</b>`,
                s: `Faltan ${m180RevDurTxt(difFin)} al final del día en la libreta.`, tramos: [] });
            else orden.push(`Término: libreta ${m180RevHora(L.fin)}, camión ${m180RevHora(G.llegada)}`);
            if (difIni < -tol) hall.push({ k: 'rev', t: `La libreta empieza a las <b>${m180RevHora(L.ini)}</b> y el camión salió de la planta a las <b>${m180RevHora(G.salida)}</b>`,
                s: `${m180RevDurTxt(difIni)} de trabajo antes de salir. Si fueron tareas de carga en la planta, está bien.`, tramos: [] });
            else if (difIni > tol) hall.push({ k: 'rev', t: `El camión salió de la planta a las <b>${m180RevHora(G.salida)}</b> y la libreta empieza a las <b>${m180RevHora(L.ini)}</b>`,
                s: `Faltan ${m180RevDurTxt(difIni)} al comienzo del día en la libreta.`, tramos: [] });
            else orden.push(`Inicio de jornada: libreta ${m180RevHora(L.ini)}, camión ${m180RevHora(G.salida)}`);
            if (Math.abs(difCond) > tol) hall.push({ k: 'rev', t: `Conducción: la libreta marca <b>${m180RevDur(L.cond)}</b> y el camión anduvo <b>${m180RevDur(G.mov)}</b>`,
                s: `${m180RevDurTxt(difCond)} de diferencia${difCond > 0 ? ' de más en la libreta' : ' que faltan en la libreta'}.`, tramos: [] });
            else orden.push(`Conducción: libreta ${m180RevDur(L.cond)}, GPS ${m180RevDur(G.mov)}`);
        }
        if (espMov.length) hall.push({ k: 'rev', t: `La libreta marca <b>espera o descanso</b> en ${minDe(espMov) / 15} ${minDe(espMov) === 15 ? 'tramo' : 'tramos'} con el camión <b>andando</b> (${m180RevDurTxt(minDe(espMov))})`,
            s: 'Ese tiempo debería ir como conducción.', tramos: espMov });
        if (sinMov.length) hall.push({ k: 'rev', t: `${minDe(sinMov) / 15} ${minDe(sinMov) === 15 ? 'tramo' : 'tramos'} <b>sin registrar</b> con el camión andando (${m180RevDurTxt(minDe(sinMov))})`,
            s: 'Falta anotar ese tiempo en la libreta.', tramos: sinMov });
        if (lim.velocidad_kmh == null) sinRevisar.push('velocidad (falta configurar el límite)');
        else if (G.vel != null && G.vel > lim.velocidad_kmh) hall.push({ k: 'mal', t: `Velocidad máxima <b>${G.vel} km/h</b>, sobre el límite de ${lim.velocidad_kmh}`,
            s: 'No es un error de la libreta: es para conversarlo con el chofer.', tramos: [] });
    }

    const nRev = hall.filter(h => h.k === 'rev').length, nMal = hall.filter(h => h.k === 'mal').length;
    // Textos con cifras armados con comillas: el compresor de la aplicación borra los espacios de un texto `${}` dentro de otro
    const cuentaPill = (k, n, txt) => n ? '<span class="m180-rev-pill es-' + k + '"><i class="bi ' + M180_REV_EST[k].i + '" aria-hidden="true"></i>' + n + ' ' + txt + '</span>' : '';
    const cuenta = cuentaPill('mal', nMal, 'fuera de norma') + cuentaPill('rev', nRev, 'por revisar') + cuentaPill('ok', orden.length, 'en orden');
    const lineaSin = sinRevisar.length ? '<div class="m180-rev-sin"><i class="bi bi-dash-circle" aria-hidden="true"></i>No se revisó: ' + sinRevisar.join(' · ') + '</div>' : '';
    const titulo = hall.length ? `${hall.length} ${hall.length === 1 ? 'cosa por revisar' : 'cosas por revisar'}` : (g ? 'La libreta calza con el GPS' : 'La libreta cumple las reglas');
    const sub = g ? `Libreta contra el GPS del camión ${m180GpsEsc(G.patente)} · ordenadas por importancia${hall.some(h => h.tramos.length) ? ' · pulsa una hora para marcarla en la línea de tiempo' : ''}`
        : 'Sin el GPS del camión se revisan solo las reglas de la libreta';
    host.innerHTML = `<header class="m180-rev-head"><h3 class="m180-rev-big" id="m180-rev-titulo">${titulo}</h3><p class="m180-rev-sub">${sub}</p>
            <div class="m180-rev-cuenta">${cuenta}</div></header>
        ${hall.length ? `<ol class="m180-rev-lista">${hall.map(h => `<li class="m180-rev-h es-${h.k}"><div class="m180-rev-h-c">${m180RevPill(h.k)}<div class="m180-rev-h-t">${h.t}</div><div class="m180-rev-h-s">${h.s}</div>
            ${h.tramos.length ? `<div class="m180-rev-h-tr">${h.tramos.map(x => m180RevTramo(x.de, x.a)).join('')}</div>` : ''}</div></li>`).join('')}</ol>` : ''}
        ${orden.length ? `<div class="m180-rev-orden"><span class="m180-rev-orden-t"><i class="bi bi-check-circle-fill" aria-hidden="true"></i>En orden</span>${orden.map(o => `<span class="m180-rev-orden-i">${o}</span>`).join('')}</div>` : ''}
        ${lineaSin}
        ${tira()}`;
}

// Marca un tramo en la línea de tiempo de la libreta (y en la del GPS) y la muestra
window.m180MarcarTramo = function (de, a) {
    document.querySelectorAll('#modalMarcacion180h .m180-marca').forEach(x => x.remove());
    clearTimeout(window.m180MarcarTramo._t);
    document.querySelectorAll('#m180-grid-scroll .m180-track, #m180-gps-card .m180-track').forEach(tr => {
        const s = document.createElement('span');
        s.className = 'm180-marca';
        s.style.left = (de / 96 * 100) + '%';
        s.style.width = ((a - de) / 96 * 100) + '%';
        tr.appendChild(s);
    });
    const card = document.getElementById('m180-grid-scroll');
    if (card) (card.closest('.m180-card') || card).scrollIntoView({ behavior: 'smooth', block: 'start' });
    window.m180MarcarTramo._t = setTimeout(() => document.querySelectorAll('#modalMarcacion180h .m180-marca').forEach(x => x.remove()), 8000);
};
window.m180GpsVer = m180GpsVer; window.m180GpsAuto = m180GpsAuto; window.m180RevisionPintar = m180RevisionPintar; window.m180GpsReintentarLista = m180GpsReintentarLista; window.m180GpsPintar = m180GpsPintar; window.m180GpsReset = m180GpsReset; window.m180GpsCargarVehiculos = m180GpsCargarVehiculos;
window.toggleLibretaBrushMode = toggleLibretaBrushMode;

// ═══════════════════════════════════════════════════════════════════
// ESCANEO CON CÁMARA (GEMINI VISION AI) & CONTROLES TÁCTILES 180H
// ═══════════════════════════════════════════════════════════════════

let m180_touch_mode = 'scroll'; // 'scroll' (desplazar libremente con el dedo) o 'paint' (pintar celdas)

window.setLibretaTouchMode = function(mode) {
    m180_touch_mode = mode;
    const container = document.getElementById('m180-grid-scroll');
    const btnScroll = document.getElementById('m180-btn-mode-scroll');
    const btnPaint = document.getElementById('m180-btn-mode-paint');

    if (container) {
        if (mode === 'paint') {
            container.style.touchAction = 'none';
            if (btnPaint) { btnPaint.classList.remove('btn-outline-primary'); btnPaint.classList.add('btn-primary'); }
            if (btnScroll) { btnScroll.classList.remove('btn-primary'); btnScroll.classList.add('btn-outline-primary'); }
        } else {
            container.style.touchAction = 'pan-x pan-y';
            if (btnScroll) { btnScroll.classList.remove('btn-outline-primary'); btnScroll.classList.add('btn-primary'); }
            if (btnPaint) { btnPaint.classList.remove('btn-primary'); btnPaint.classList.add('btn-outline-primary'); }
        }
    }
};

// ═══════════════════════════════════════════════════════════════════
// ESCÁNER INTELIGENTE EN VIVO CON CÁMARA Y RECORTE TÁCTIL (CROPPER.JS)
// ═══════════════════════════════════════════════════════════════════

let scannerStream = null;
let scannerCropperInstance = null;
let scannerFacingMode = "environment"; // trasera por defecto en móviles

window.abrirScannerLibreta = async function() {
    const modalEl = document.getElementById('modalScannerLibreta');
    if (!modalEl) return;
    
    // Resetear banderas de bloqueo de captura
    window._scannerEnProceso = false;
    window._scannerCapturando = false;
    window._scannerProcesandoApi = false;
    const shutterBtn = document.getElementById('scanner-btn-shutter');
    if (shutterBtn) {
        shutterBtn.classList.remove('disabled', 'opacity-50');
        shutterBtn.onclick = (e) => {
            window.scannerCapturarFrameDirecto(e);
        };
        shutterBtn.ontouchend = (e) => {
            window.scannerCapturarFrameDirecto(e);
        };
    }

    // Inhabilitar interacción de velos (backdrops) para que NUNCA bloqueen los toques de la cámara
    document.querySelectorAll('.modal-backdrop').forEach(b => {
        b.style.pointerEvents = 'none';
        b.style.opacity = '0';
    });

    // Asegurar modo 1 Día (columna vertical) inicializado por defecto
    window.scannerModoActual = 'dia';
    const box = document.getElementById('scanner-guide-box');
    if (box) {
        box.classList.remove('scanner-guide-box-panoramic');
        box.classList.add('scanner-guide-box-col-dia');
    }
    const txt = document.getElementById('txt-scanner-mode');
    if (txt) txt.textContent = '1 Día';
    const icon = document.getElementById('icon-scanner-mode');
    if (icon) icon.className = 'bi bi-layout-sidebar-inset text-success';
    const hint = document.getElementById('scanner-hud-hint');
    if (hint) hint.textContent = 'Acerca a la columna de hoy (vertical)';
    const lanes = document.getElementById('scanner-guide-lanes');
    if (lanes) lanes.classList.remove('d-none');
    const timeline = document.getElementById('scanner-guide-timeline');
    if (timeline) timeline.classList.remove('d-none');
    const label = document.getElementById('scanner-guide-label');
    if (label) label.textContent = 'Columna del día (00 a 24h)';

    const bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);
    bsModal.show();
    
    // Mostrar paso 1: cámara
    document.getElementById('scanner-step-camera')?.classList.remove('d-none');
    document.getElementById('scanner-step-crop')?.classList.add('d-none');
    document.getElementById('scanner-step-loading')?.classList.add('d-none');
    
    await iniciarScannerCamara();
};

async function iniciarScannerCamara() {
    detenerScannerCamara();
    const video = document.getElementById('scanner-live-video');
    if (!video) return;

    try {
        const constraints = {
            video: {
                facingMode: { ideal: scannerFacingMode },
                width: { ideal: 1920 },
                height: { ideal: 1080 }
            },
            audio: false
        };

        scannerStream = await navigator.mediaDevices.getUserMedia(constraints);
        video.srcObject = scannerStream;
        await video.play();
    } catch (err) {
        console.warn("⚠️ No se pudo acceder a la cámara en vivo:", err);
        if (typeof showToast === 'function') {
            showToast("No se pudo abrir la cámara. Puede subir una foto de la planilla.", "warning");
        }
        document.getElementById('m180-gallery-input')?.click();
    }
}

function detenerScannerCamara() {
    if (scannerStream) {
        scannerStream.getTracks().forEach(track => track.stop());
        scannerStream = null;
    }
    const video = document.getElementById('scanner-live-video');
    if (video) video.srcObject = null;
}

window.scannerCambiarCamara = async function() {
    scannerFacingMode = scannerFacingMode === "environment" ? "user" : "environment";
    await iniciarScannerCamara();
};

// OpenCV.js (~9 MB) y jscanify solo se descargan cuando alguien usa el modo "Hoja completa" del escáner.
// Antes se cargaban en cada visita a la página aunque nadie escaneara. Si no alcanzan a cargar,
// la captura cae al comportamiento normal (foto sin aplanar), igual que antes.
let _visionDocPromise = null;
window.cargarVisionDocumentos = function () {
    if (_visionDocPromise) return _visionDocPromise;
    const cargar = (src) => new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = src;
        s.async = true;
        s.onload = resolve;
        s.onerror = () => reject(new Error('No se pudo cargar ' + src));
        document.head.appendChild(s);
    });
    _visionDocPromise = cargar('https://docs.opencv.org/4.7.0/opencv.js')
        .then(() => cargar('https://cdn.jsdelivr.net/gh/puffinsoft/jscanify@1.2.0/src/jscanify.min.js'))
        .catch((e) => { console.warn('⚠️ Visión de documentos no disponible:', e.message); _visionDocPromise = null; });
    return _visionDocPromise;
};

let _jscanifyInstance = null;
function getJscanifyInstance() {
    if (typeof jscanify !== 'undefined') {
        if (!_jscanifyInstance) {
            try {
                _jscanifyInstance = new jscanify();
                console.log("✅ jscanify cargado y listo para aplanar documentos");
            } catch (e) {
                console.warn("⚠️ No se pudo inicializar jscanify:", e);
            }
        }
        return _jscanifyInstance;
    }
    return null;
}

window.scannerModoActual = 'dia';

window.scannerToggleModoGuia = function() {
    const box = document.getElementById('scanner-guide-box');
    const txt = document.getElementById('txt-scanner-mode');
    const icon = document.getElementById('icon-scanner-mode');
    const hint = document.getElementById('scanner-hud-hint');
    const lanes = document.getElementById('scanner-guide-lanes');
    const timeline = document.getElementById('scanner-guide-timeline');
    const label = document.getElementById('scanner-guide-label');

    if (window.scannerModoActual === 'dia') {
        window.scannerModoActual = 'hoja';
        if (typeof window.cargarVisionDocumentos === 'function') window.cargarVisionDocumentos();
        if (box) {
            box.classList.remove('scanner-guide-box-col-dia');
            box.classList.add('scanner-guide-box-panoramic');
        }
        if (txt) txt.textContent = 'Hoja';
        if (icon) icon.className = 'bi bi-table text-warning';
        if (hint) hint.textContent = 'Encuadra la hoja completa';
        if (lanes) lanes.classList.add('d-none');
        if (timeline) timeline.classList.add('d-none');
        if (label) label.textContent = 'Hoja completa de asistencia';
    } else {
        window.scannerModoActual = 'dia';
        if (box) {
            box.classList.remove('scanner-guide-box-panoramic');
            box.classList.add('scanner-guide-box-col-dia');
        }
        if (txt) txt.textContent = '1 Día';
        if (icon) icon.className = 'bi bi-layout-sidebar-inset text-success';
        if (hint) hint.textContent = 'Acerca a la columna de hoy (vertical)';
        if (lanes) lanes.classList.remove('d-none');
        if (timeline) timeline.classList.remove('d-none');
        if (label) label.textContent = 'Columna del día (00 a 24h)';
    }
};

let _scannerLastCaptureTime = 0;
window.scannerCapturarFrame = window.scannerCapturarFrameDirecto = function(e) {
    if (e) {
        try { e.preventDefault(); e.stopPropagation(); } catch(_) {}
    }
    const now = Date.now();
    if (now - _scannerLastCaptureTime < 800) {
        return;
    }
    _scannerLastCaptureTime = now;

    if (window._scannerCapturando || window._scannerProcesandoApi) {
        console.warn("⚠️ Captura o procesamiento ya en curso, ignorando pulsación duplicada.");
        return;
    }

    const video = document.getElementById('scanner-live-video');
    const canvas = document.getElementById('scanner-hidden-canvas');
    const shutterBtn = document.getElementById('scanner-btn-shutter');

    if (!video || !canvas) {
        console.error("❌ Elementos de video o canvas no disponibles en el DOM");
        return;
    }

    // 1. Feedback háptico inmediato en smartphones
    if (navigator.vibrate) {
        try { navigator.vibrate([45, 30, 45]); } catch(e){}
    }

    // 2. Feedback visual instantáneo en el botón disparador
    if (shutterBtn) {
        shutterBtn.classList.add('disabled', 'opacity-50');
    }

    window._scannerCapturando = true;

    // 3. Cambiar inmediatamente la vista al spinner para que la pantalla NUNCA quede inmóvil
    document.getElementById('scanner-step-camera')?.classList.add('d-none');
    document.getElementById('scanner-step-crop')?.classList.add('d-none');
    const loadingStep = document.getElementById('scanner-step-loading');
    if (loadingStep) {
        loadingStep.classList.remove('d-none');
        loadingStep.classList.add('d-flex');
    }

    // 4. Procesar la captura y recorte dentro de requestAnimationFrame para asegurar renderizado previo del loader
    requestAnimationFrame(() => {
        try {
            const w = video.videoWidth || video.clientWidth || 1920;
            const h = video.videoHeight || video.clientHeight || 1080;
            canvas.width = w;
            canvas.height = h;

            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0, w, h);

            let finalDataUrl = null;

            // Recorte geométrico exacto de la columna visible en pantalla (1 Día)
            const guideBox = document.getElementById('scanner-guide-box');
            if (window.scannerModoActual === 'dia' && guideBox && typeof video.getBoundingClientRect === 'function') {
                try {
                    const vRect = video.getBoundingClientRect();
                    const gRect = guideBox.getBoundingClientRect();

                    if (vRect.width > 0 && vRect.height > 0 && gRect.width > 0 && gRect.height > 0) {
                        const scale = Math.max(vRect.width / w, vRect.height / h);
                        const renderedW = w * scale;
                        const renderedH = h * scale;
                        const offsetX = (renderedW - vRect.width) / 2;
                        const offsetY = (renderedH - vRect.height) / 2;

                        const gx = gRect.left - vRect.left + offsetX;
                        const gy = gRect.top - vRect.top + offsetY;

                        let cropX = gx / scale;
                        let cropY = gy / scale;
                        let cropW = gRect.width / scale;
                        let cropH = gRect.height / scale;

                        const padY = cropH * 0.015;
                        cropX = Math.max(0, cropX);
                        cropY = Math.max(0, cropY - padY);
                        cropW = Math.min(w - cropX, cropW);
                        cropH = Math.min(h - cropY, cropH + 2 * padY);

                        if (cropW > 60 && cropH > 60) {
                            const cropCanvas = document.createElement('canvas');
                            cropCanvas.width = Math.round(cropW);
                            cropCanvas.height = Math.round(cropH);
                            const cCtx = cropCanvas.getContext('2d');
                            cCtx.drawImage(canvas, cropX, cropY, cropW, cropH, 0, 0, cropCanvas.width, cropCanvas.height);
                            finalDataUrl = cropCanvas.toDataURL('image/jpeg', 0.85);
                            console.log(`📸 Columna 1 Día recortada con éxito: ${cropCanvas.width}x${cropCanvas.height}px`);
                        }
                    }
                } catch (cropErr) {
                    console.warn("⚠️ Fallback recorte inteligente:", cropErr);
                }
            }

            // Modo Hoja Completa: aplanar con jscanify si está disponible
            if (!finalDataUrl && window.scannerModoActual === 'hoja') {
                const scanner = typeof getJscanifyInstance === 'function' ? getJscanifyInstance() : null;
                if (scanner) {
                    try {
                        const paperCanvas = scanner.extractPaper(canvas, 1600, 1000);
                        if (paperCanvas) {
                            finalDataUrl = paperCanvas.toDataURL('image/jpeg', 0.85);
                            console.log("📄 Hoja completa aplanada con OpenCV/jscanify.");
                        }
                    } catch (e) {
                        console.warn("⚠️ Fallback jscanify extractPaper:", e);
                    }
                }
            }

            if (!finalDataUrl) {
                finalDataUrl = canvas.toDataURL('image/jpeg', 0.85);
            }

            detenerScannerCamara();
            window._scannerCapturando = false;

            // Procesar directo con Gemini Vision AI
            window.scannerProcesarConGemini(finalDataUrl);

        } catch (captureErr) {
            console.error("❌ Error en captura de frame:", captureErr);
            window._scannerCapturando = false;
            window._scannerProcesandoApi = false;
            window._scannerEnProceso = false;
            if (shutterBtn) shutterBtn.classList.remove('disabled', 'opacity-50');

            // Restaurar visor de cámara si falló la captura
            document.getElementById('scanner-step-loading')?.classList.add('d-none');
            document.getElementById('scanner-step-camera')?.classList.remove('d-none');

            if (typeof showToast === 'function') {
                showToast("No se pudo tomar la foto. " + (captureErr.message || captureErr), "error");
            }
        }
    });
};

window.m180HandleFileForScanner = function(event) {
    const input = event.target;
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];

    const reader = new FileReader();
    reader.onload = (e) => {
        const modalEl = document.getElementById('modalScannerLibreta');
        if (modalEl) {
            const bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);
            bsModal.show();
        }
        detenerScannerCamara();

        // Procesar directo la imagen subida sin obligar a recortar con los dedos
        window.scannerProcesarConGemini(e.target.result);
    };
    reader.readAsDataURL(file);
    input.value = '';
};


let scannerGuideMode = '1day';
window._scannerRatioLocked = true;

window.scannerSetCameraGuideMode = function(mode) {
    scannerGuideMode = mode;
    const box = document.getElementById('scanner-guide-box');
    const lanes = document.getElementById('scanner-guide-lanes');
    const help = document.getElementById('scanner-guide-help');
    const btn1Day = document.getElementById('scanner-mode-1day-btn');
    const btnPage = document.getElementById('scanner-mode-page-btn');

    if (mode === '1day') {
        box?.classList.add('mode-1day');
        lanes?.classList.remove('d-none');
        if (help) help.innerHTML = '<i class="bi bi-bullseye me-1 text-success"></i> Calza la fila del día dentro del marco verde';
        btn1Day?.classList.remove('btn-outline-light');
        btn1Day?.classList.add('btn-success');
        btnPage?.classList.remove('btn-success');
        btnPage?.classList.add('btn-outline-light');
    } else {
        box?.classList.remove('mode-1day');
        lanes?.classList.add('d-none');
        if (help) help.innerHTML = '<i class="bi bi-arrows-fullscreen me-1 text-warning"></i> Encuadra la hoja completa dentro del marco';
        btnPage?.classList.remove('btn-outline-light');
        btnPage?.classList.add('btn-success');
        btn1Day?.classList.remove('btn-success');
        btn1Day?.classList.add('btn-outline-light');
    }
};

window.scannerToggleAspectRatio = function() {
    if (!scannerCropperInstance) return;
    const btn = document.getElementById('scanner-btn-lock-ratio');
    if (window._scannerRatioLocked) {
        window._scannerRatioLocked = false;
        scannerCropperInstance.setAspectRatio(NaN);
        if (btn) {
            btn.className = 'btn btn-xs btn-outline-light py-0.5 px-2 text-nowrap';
            btn.innerHTML = '<i class="bi bi-unlock me-1"></i> Proporción Libre';
        }
    } else {
        window._scannerRatioLocked = true;
        scannerCropperInstance.setAspectRatio(5.2);
        if (btn) {
            btn.className = 'btn btn-xs btn-success py-0.5 px-2 text-nowrap';
            btn.innerHTML = '<i class="bi bi-lock-fill me-1"></i> Proporción 1 Día (5.2:1)';
        }
    }
};

window.scannerSeleccionarDia = function(diaNum) {
    if (!scannerCropperInstance) return;
    const canvasData = scannerCropperInstance.getCanvasData();
    scannerCropperInstance.setAspectRatio(5.2);
    window._scannerRatioLocked = true;
    const btn = document.getElementById('scanner-btn-lock-ratio');
    if (btn) {
        btn.className = 'btn btn-xs btn-success py-0.5 px-2 text-nowrap';
        btn.innerHTML = '<i class="bi bi-lock-fill me-1"></i> Proporción 1 Día (5.2:1)';
    }

    const w = canvasData.width * 0.94;
    const h = w / 5.2;
    const left = canvasData.left + (canvasData.width - w) / 2;

    const availableH = Math.max(0, canvasData.height - h);
    const stepY = availableH / 4.4;
    const top = canvasData.top + (diaNum - 1) * stepY;

    scannerCropperInstance.setCropBoxData({
        left: left,
        top: Math.max(canvasData.top, Math.min(top, canvasData.top + canvasData.height - h)),
        width: w,
        height: h
    });

    if (typeof showToast === 'function') {
        const nombres = ['', 'Lunes (Día 1)', 'Martes (Día 2)', 'Miércoles (Día 3)', 'Jueves (Día 4)', 'Viernes (Día 5)'];
        showToast(`Marco ajustado al ${nombres[diaNum] || `día ${diaNum}`}.`, 'info');
    }
};

window.scannerMoverCrop = function(dx, dy) {
    if (!scannerCropperInstance) return;
    const box = scannerCropperInstance.getCropBoxData();
    scannerCropperInstance.setCropBoxData({
        left: box.left + dx,
        top: box.top + dy,
        width: box.width,
        height: box.height
    });
};

window.scannerEscalarCrop = function(factor) {
    if (!scannerCropperInstance) return;
    const box = scannerCropperInstance.getCropBoxData();
    const newW = box.width * factor;
    const newH = box.height * factor;
    const dW = newW - box.width;
    const dH = newH - box.height;
    scannerCropperInstance.setCropBoxData({
        left: box.left - dW / 2,
        top: box.top - dH / 2,
        width: newW,
        height: newH
    });
};

window.scannerRotar = function(deg) {
    if (scannerCropperInstance) {
        scannerCropperInstance.rotate(deg);
    }
};

window.scannerResetCrop = function() {
    if (scannerCropperInstance) {
        scannerCropperInstance.reset();
        window.scannerSeleccionarDia(1);
    }
};

window.scannerVolverACamara = async function() {
    if (scannerCropperInstance) {
        scannerCropperInstance.destroy();
        scannerCropperInstance = null;
    }
    document.getElementById('scanner-step-crop')?.classList.add('d-none');
    document.getElementById('scanner-step-loading')?.classList.add('d-none');
    document.getElementById('scanner-step-camera')?.classList.remove('d-none');
    await iniciarScannerCamara();
};

window.scannerProcesarConGemini = async function(directBase64 = null) {
    if (window._scannerProcesandoApi) {
        console.warn("⚠️ Ya se está procesando una planilla con Gemini.");
        return;
    }
    window._scannerProcesandoApi = true;
    window._scannerEnProceso = true;

    let base64Jpeg = directBase64;

    if (!base64Jpeg) {
        if (scannerCropperInstance) {
            const croppedCanvas = scannerCropperInstance.getCroppedCanvas({
                maxWidth: 1800,
                maxHeight: 1400,
                fillColor: '#ffffff',
                imageSmoothingEnabled: true,
                imageSmoothingQuality: 'high'
            });
            if (croppedCanvas) {
                base64Jpeg = croppedCanvas.toDataURL('image/jpeg', 0.88);
            }
        } else {
            const cropImg = document.getElementById('scanner-crop-image');
            if (cropImg) base64Jpeg = cropImg.src;
        }
    }

    if (!base64Jpeg) {
        window._scannerProcesandoApi = false;
        window._scannerEnProceso = false;
        if (typeof showToast === 'function') showToast("No se pudo leer la imagen. Vuelva a intentarlo.", "error");
        return;
    }

    // Guardar referencia en memoria de la foto recién capturada para enviarla al persistir
    window.m180_last_scanned_image = base64Jpeg;

    // Mostrar loader a pantalla completa
    document.getElementById('scanner-step-camera')?.classList.add('d-none');
    document.getElementById('scanner-step-crop')?.classList.add('d-none');
    const loadingStep = document.getElementById('scanner-step-loading');
    if (loadingStep) {
        loadingStep.classList.remove('d-none');
        loadingStep.classList.add('d-flex');
    }

    const empId = document.getElementById('m180-empleado-id')?.value;
    const fecha = document.getElementById('m180-fecha-str')?.value;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    try {
        const token = localStorage.getItem('access_token') || localStorage.getItem('access_token') || '';
        const resp = await fetch('/api/asistencia/libreta-180h/ocr-gemini-base64/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                imagen_base64: base64Jpeg,
                image_base64: base64Jpeg,
                empleado_id: empId ? parseInt(empId) : null,
                fecha: fecha || null
            }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            throw new Error(errData.detail || `Error ${resp.status} al procesar con IA`);
        }

        const data = await resp.json();

        if (!data.exito && data.error === 'GEMINI_API_KEY_MISSING') {
            throw new Error("Falta configurar GEMINI_API_KEY en .env");
        }

        if (!data.exito) {
            throw new Error(data.mensaje || data.error || 'No se pudieron extraer los tramos');
        }

        // Llenar automáticamente los 96 slots en la libreta
        if (Array.isArray(data.slots_96) && data.slots_96.length === 96) {
            m180PushHistory();
            m180_slots = data.slots_96.map(s => Number(s) || 0);
            refreshAllSlotsVisuals();
        }

        // Mostrar previsualización en la tarjeta de la libreta
        const previewImg = document.getElementById('m180-ocr-preview-img');
        const previewContainer = document.getElementById('m180-ocr-preview-container');
        if (previewImg && previewContainer) {
            const authToken = localStorage.getItem('access_token') || localStorage.getItem('access_token') || '';
            const authFotoUrl = (data.foto_url && authToken) ? `${data.foto_url}&token=${encodeURIComponent(authToken)}` : (data.foto_url || base64Jpeg);
            previewImg.src = base64Jpeg || authFotoUrl;
            previewContainer.classList.remove('d-none');
            const textEl = previewContainer.querySelector('.small');
            if (textEl && authFotoUrl) {
                textEl.innerHTML = `
                    <div class="d-flex align-items-center justify-content-between gap-2 flex-wrap">
                        <div><strong class="text-dark">Foto física archivada</strong> · Planilla respaldada en el servidor.</div>
                        <a href="${authFotoUrl}" target="_blank" class="btn btn-xs btn-outline-primary py-0 px-2" style="font-size:0.75rem;"><i class="bi bi-box-arrow-up-right me-1"></i>Ver en Grande</a>
                    </div>
                `;
            }
        }

        // Cálculo exacto de horas basado en los 96 slots volcados
        const condSlots = m180_slots.filter(s => s === 1).length;
        const espSlots = m180_slots.filter(s => s === 2).length;
        const auxSlots = m180_slots.filter(s => s === 3).length;
        const descSlots = m180_slots.filter(s => s === 4).length;

        const calcCondH = (condSlots * 15 / 60).toFixed(1);
        const calcEspH = (espSlots * 15 / 60).toFixed(1);
        const calcAuxH = (auxSlots * 15 / 60).toFixed(1);
        const calcDescH = (descSlots * 15 / 60).toFixed(1);

        const statusBox = document.getElementById('m180-ocr-status-box');
        if (statusBox) {
            statusBox.classList.remove('d-none', 'alert-danger', 'alert-warning');
            statusBox.classList.add('alert-success');
            statusBox.innerHTML = `
                <div class="d-flex align-items-start gap-2">
                    <i class="bi bi-check-circle-fill text-success fs-5 mt-0.5"></i>
                    <div class="small">
                        <strong class="text-success">¡Planilla Procesada con Gemini Vision!</strong><br>
                        <span>Se cargaron en la grilla: <strong>${calcCondH}h</strong> Conducción · <strong>${calcEspH}h</strong> Espera · <strong>${calcAuxH}h</strong> Auxiliares · <strong>${calcDescH}h</strong> Descanso.</span>
                    </div>
                </div>
            `;
        }

        // Cerrar modal del escáner
        window.scannerCerrar();

        // Notificación de éxito con opciones claras de guardado y autollenado
        if (typeof Swal !== 'undefined') {
            const emptySlots = m180_slots.filter(s => s === 0).length;
            const emptyHours = (emptySlots * 15 / 60).toFixed(1);

            const swalRes = await Swal.fire({
                icon: 'success',
                title: 'Planilla leída',
                html: `
                    <p class="text-muted small mb-2">Google Gemini Vision reconoció las marcas de la planilla y las volcó a la grilla de 24 horas:</p>
                    <div class="d-flex justify-content-around text-center p-2 mb-3 bg-light rounded border">
                        <div><strong class="text-success fs-5">${calcCondH}h</strong><div class="text-muted" style="font-size:0.7rem;">Conducción</div></div>
                        <div><strong class="text-warning fs-5">${calcEspH}h</strong><div class="text-muted" style="font-size:0.7rem;">Espera</div></div>
                        <div><strong class="text-info fs-5">${calcDescH}h</strong><div class="text-muted" style="font-size:0.7rem;">Descanso</div></div>
                        <div><strong class="text-primary fs-5">${calcAuxH}h</strong><div class="text-muted" style="font-size:0.7rem;">Tareas Aux.</div></div>
                    </div>
                    ${emptySlots > 0 ? `
                    <div class="alert alert-warning py-2 px-3 small text-start mb-0" style="border-radius:8px;">
                        <i class="bi bi-info-circle-fill me-1 text-warning"></i>
                        Quedan <strong>${emptyHours} hrs</strong> sin marcar. Según la DT los tramos sin marcar corresponden a descanso legal.
                    </div>
                    ` : ''}
                `,
                showCancelButton: true,
                showDenyButton: true,
                confirmButtonText: '<i class="bi bi-moon-stars-fill me-1"></i> Rellenar Descanso y Guardar Borrador',
                confirmButtonColor: '#059669',
                denyButtonText: '<i class="bi bi-save me-1"></i> Guardar Borrador (tal cual)',
                denyButtonColor: '#3b82f6',
                cancelButtonText: '<i class="bi bi-pencil-square me-1"></i> Revisar en Grilla',
                cancelButtonColor: '#64748b',
                focusConfirm: true
            });

            if (swalRes.isConfirmed) {
                // Rellenar automáticamente los vacíos con descanso y guardar en base de datos directamente
                libreta180hAutoDescanso();
                await window.guardarLibreta180h(false, true);
            } else if (swalRes.isDenied) {
                // Guardar como borrador tal como se detectó (sin repetir popups)
                await window.guardarLibreta180h(false, true);
            } else {
                // El usuario eligió revisar en grilla antes de guardar
                m180_dirty = true;
                if (typeof showToast === 'function') {
                    showToast('Se cargaron los tramos de la foto. Para guardarlos, use «Guardar borrador»; después se valida.', 'info', 6000);
                }
            }
        } else if (typeof showToast === 'function') {
            showToast("Listo. Se leyó la planilla de la foto.", "success");
        }

    } catch (err) {
        clearTimeout(timeoutId);
        console.error("❌ Error en scannerProcesarConGemini:", err);
        // Cerrar modal del escáner para que el usuario nunca quede atrapado en pantalla de carga
        window.scannerCerrar();

        const errMsg = err.name === 'AbortError'
            ? 'Tiempo de espera agotado (30s) al conectar con Gemini Vision. Por favor reintenta.'
            : (err.message || 'No se pudo interpretar la planilla física.');

        if (typeof Swal !== 'undefined') {
            Swal.fire({
                icon: 'error',
                title: 'No se pudo leer la planilla',
                text: errMsg,
                confirmButtonColor: '#ef4444'
            });
        } else if (typeof showToast === 'function') {
            showToast(errMsg, "error");
        }
    } finally {
        clearTimeout(timeoutId);
        window._scannerProcesandoApi = false;
        window._scannerCapturando = false;
        window._scannerEnProceso = false;
        const shutterBtn = document.getElementById('scanner-btn-shutter');
        if (shutterBtn) shutterBtn.classList.remove('disabled', 'opacity-50');
    }
};

window.scannerCerrar = function() {
    window._scannerProcesandoApi = false;
    window._scannerCapturando = false;
    window._scannerEnProceso = false;
    const shutterBtn = document.getElementById('scanner-btn-shutter');
    if (shutterBtn) shutterBtn.classList.remove('disabled', 'opacity-50');
    detenerScannerCamara();
    if (scannerCropperInstance) {
        scannerCropperInstance.destroy();
        scannerCropperInstance = null;
    }
    // Restaurar vistas del modal para futuros escaneos
    document.getElementById('scanner-step-loading')?.classList.add('d-none');
    document.getElementById('scanner-step-crop')?.classList.add('d-none');
    document.getElementById('scanner-step-camera')?.classList.remove('d-none');

    // Restaurar eventos de backdrop para el modal de libreta inferior
    document.querySelectorAll('.modal-backdrop').forEach(b => {
        b.style.pointerEvents = '';
        b.style.opacity = '';
    });
    const modalEl = document.getElementById('modalScannerLibreta');
    if (modalEl) {
        const bsModal = bootstrap.Modal.getInstance(modalEl);
        if (bsModal) bsModal.hide();
    }
};



// Fallback de subida directa tradicional
window.m180HandleCameraUpload = async function(event) {
    window.m180HandleFileForScanner(event);
};

window.aplicarTramoRango180h = function() {
    const actId = parseInt(document.getElementById('m180-quick-act').value) || 1;
    const hDesde = document.getElementById('m180-quick-desde').value;
    const hHasta = document.getElementById('m180-quick-hasta').value;

    if (!hDesde || !hHasta) {
        Avisos.falta('Faltan las horas del tramo. Elija desde y hasta.', { campos: [!hDesde && 'm180-quick-desde', !hHasta && 'm180-quick-hasta'].filter(Boolean) });
        return;
    }

    const [dH, dM] = hDesde.split(':').map(Number);
    const [hH, hM] = hHasta.split(':').map(Number);

    const startMin = dH * 60 + dM;
    const endMin = hH * 60 + hM;

    if (endMin <= startMin) {
        Avisos.falta('La hora «hasta» debe ser después de la hora «desde».', { campos: ['m180-quick-hasta'] });
        return;
    }

    const startSlot = Math.max(0, Math.min(95, Math.floor(startMin / 15)));
    const endSlot = Math.max(0, Math.min(96, Math.ceil(endMin / 15)));

    for (let s = startSlot; s < endSlot; s++) {
        m180_slots[s] = actId;
    }

    refreshAllSlotsVisuals();
    recalcLibretaTotales();

    const actName = M180_ACTIVIDADES[actId]?.name || 'Actividad';
    if (typeof showToast === 'function') {
        showToast(`Listo. ${actName} de ${hDesde} a ${hHasta} (${(endSlot - startSlot) * 15 / 60} h).`, "success");
    }
};

window.m180HandleCameraUpload = m180HandleCameraUpload;
window.setLibretaTouchMode = setLibretaTouchMode;
window.aplicarTramoRango180h = aplicarTramoRango180h;



