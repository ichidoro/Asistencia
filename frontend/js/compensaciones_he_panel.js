// ============================================================
// SISTEMA DE COMPENSACIONES (INASISTENCIAS POR HORAS EXTRAS)
// ============================================================

(function injectCompensacionStyles() {
    if (document.getElementById('compensacion-he-panel-styles')) return;
    const style = document.createElement('style');
    style.id = 'compensacion-he-panel-styles';
    style.textContent = `
        .badge-he-disponible {
            background: #dcfce7;
            color: #15803d;
            border: 1px solid #bbf7d0;
        }
        .badge-inasistencia-compensada-he {
            background: #ecfdf5;
            color: #047857;
            border: 1px solid #a7f3d0;
            text-decoration: line-through;
        }
    `;
    document.head.appendChild(style);

    // Inyectar el Modal
    if (!document.getElementById('modal-compensar-he')) {
        const modalHTML = `
            <div class="modal fade" id="modal-compensar-he" tabindex="-1">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content border-0 shadow-lg" style="border-radius: 12px; overflow: hidden;">
                        <div class="modal-header" style="background: linear-gradient(135deg, #059669 0%, #047857 100%); color: white; border-bottom: none;">
                            <h5 class="modal-title fw-bold">
                                <i class="bi bi-clock-history me-2"></i> Compensar Inasistencia con H.E.
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body p-4 bg-light">
                            <p class="text-muted small mb-4">
                                <i class="bi bi-info-circle text-success"></i> 
                                Permite compensar o justificar un día de inasistencia utilizando los minutos acumulados en la Bolsa de Horas Extras aprobadas en el periodo.
                            </p>

                            <form id="form-compensar-he">
                                <!-- Empleado -->
                                <div class="mb-3">
                                    <label for="compensar-he-empleado" class="form-label fw-bold text-dark small">Empleado</label>
                                    <select id="compensar-he-empleado" class="form-select border-success shadow-sm" required>
                                        <option value="">Seleccione un empleado...</option>
                                    </select>
                                </div>

                                <div class="row g-3 mb-3">
                                    <div class="col-6">
                                        <label for="compensar-he-fecha-inasistencia" class="form-label fw-bold text-dark small">Fecha Inasistencia</label>
                                        <input type="date" id="compensar-he-fecha-inasistencia" class="form-control" required>
                                        <small class="text-muted" style="font-size:0.65rem;">Día con falta o deuda a cubrir</small>
                                    </div>
                                    <div class="col-6">
                                        <label class="form-label fw-bold text-dark small">Bolsa HE Disponible (Periodo)</label>
                                        <div id="compensar-he-bolsa-badge-container" class="mt-1">
                                            <span class="badge p-2 bg-secondary text-white w-100">Seleccione empleado y fecha...</span>
                                        </div>
                                        <small class="text-muted" style="font-size:0.65rem;">Saldo de HE aprobadas en el periodo</small>
                                    </div>
                                </div>

                                <div class="row g-3 mb-3">
                                    <div class="col-12">
                                        <label for="compensar-he-tiempo" class="form-label fw-bold text-dark small">Tiempo a Compensar (HH:MM:SS)</label>
                                        <input type="text" id="compensar-he-tiempo" class="form-control" required placeholder="00:00:00">
                                        <small class="text-muted" style="font-size:0.65rem;">Se sugiere automáticamente la jornada teórica del turno asignado</small>
                                    </div>
                                </div>

                                <div class="mb-3">
                                    <label for="compensar-he-observaciones" class="form-label fw-bold text-dark small">Observaciones / Justificación</label>
                                    <textarea id="compensar-he-observaciones" class="form-control" rows="2" placeholder="Ej: Compensado según solicitud de jefatura..." required></textarea>
                                </div>
                            </form>

                            <!-- Lista de compensaciones del empleado seleccionado -->
                            <div id="compensaciones-he-list-container" class="mt-4 d-none">
                                <h6 class="fw-bold text-muted small border-bottom pb-2">Compensaciones del Empleado en el Período</h6>
                                <div id="compensaciones-he-list" style="max-height: 150px; overflow-y: auto;"></div>
                            </div>

                        </div>
                        <div class="modal-footer bg-white">
                            <button type="button" class="btn btn-light" data-bs-dismiss="modal">Cancelar</button>
                            <button type="button" class="btn btn-success px-4 fw-bold shadow-sm" onclick="registrarCompensacionHE()">
                                <i class="bi bi-save me-1"></i> Guardar Compensación
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHTML);
    }
})();

// ==========================================
// UTILIDADES DE CONVERSIÓN DE TIEMPO
// ==========================================

function timeStringToMinutes(timeStr) {
    if (!timeStr) return 0;
    const parts = timeStr.split(':');
    const hrs = parseInt(parts[0], 10) || 0;
    const mins = parseInt(parts[1], 10) || 0;
    const secs = parseInt(parts[2], 10) || 0;
    return hrs * 60 + mins + secs / 60;
}

function minutesToTimeString(minutes) {
    if (isNaN(minutes) || minutes < 0) return '00:00:00';
    const hrs = Math.floor(minutes / 60);
    const mins = Math.floor(minutes % 60);
    const secs = Math.round((minutes % 1) * 60);
    return `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function formatMinutesReadable(m) {
    const h = Math.floor(m / 60);
    const min = Math.round(m % 60);
    return h > 0 ? `${h}h ${min}m` : `${min}m`;
}

// ==========================================
// MANEJO DE EVENTOS Y DATOS
// ==========================================

function actualizarMinutosSugeridos(empleadoId, fechaInasistencia) {
    const empMatrix = window.stateMarcacionesApp?.data?.matrix?.[empleadoId];
    const asist = empMatrix?.[fechaInasistencia];
    let minsToCompensate = 540; // Default 9 horas
    if (asist) {
        if (asist.horas_teoricas > 0) {
            minsToCompensate = asist.horas_teoricas * 60;
        } else if (asist.minutos_deuda > 0) {
            minsToCompensate = asist.minutos_deuda;
        }
    }
    document.getElementById('compensar-he-tiempo').value = minutesToTimeString(minsToCompensate);
}

/**
 * Abre el modal de Compensación de Horas Extras
 */
window.abrirModalCompensacionHE = async function(empleadoId = null, fechaInasistencia = null) {
    const modalEl = document.getElementById('modal-compensar-he');
    if (!modalEl) return;

    // Poblar combo de empleados
    const selectEmp = document.getElementById('compensar-he-empleado');
    selectEmp.innerHTML = '<option value="">Seleccione un empleado...</option>';
    
    let empleadosList = window.stateMarcacionesApp?.data?.empleados || [];
    
    if (empleadosList.length === 0) {
        const ddl = document.getElementById('marcacion-empleado');
        if (ddl && ddl.options.length > 1) {
            Array.from(ddl.options).forEach(opt => {
                if (opt.value) {
                    empleadosList.push({ id: opt.value, nombre_completo: opt.text });
                }
            });
        }
    }

    empleadosList.forEach(emp => {
        const option = document.createElement('option');
        option.value = emp.id;
        option.textContent = emp.nombre_completo || emp.nombre;
        if (empleadoId && String(emp.id) === String(empleadoId)) {
            option.selected = true;
        }
        selectEmp.appendChild(option);
    });

    // Event handlers al cambiar de empleado o fecha
    selectEmp.onchange = () => {
        const empId = selectEmp.value;
        const fechaInas = document.getElementById('compensar-he-fecha-inasistencia').value;
        cargarHE_Disponibles(empId, fechaInas);
        cargarCompensacionesEmpleado(empId);
        if (empId && fechaInas) {
            actualizarMinutosSugeridos(empId, fechaInas);
        }
    };

    document.getElementById('compensar-he-fecha-inasistencia').onchange = () => {
        const empId = selectEmp.value;
        const fechaInas = document.getElementById('compensar-he-fecha-inasistencia').value;
        cargarHE_Disponibles(empId, fechaInas);
        if (empId && fechaInas) {
            actualizarMinutosSugeridos(empId, fechaInas);
        }
    };

    // Resetear formulario
    document.getElementById('form-compensar-he').reset();
    
    if (empleadoId) {
        selectEmp.value = empleadoId;
        selectEmp.disabled = true;
        if (fechaInasistencia) {
            const fechaInput = document.getElementById('compensar-he-fecha-inasistencia');
            fechaInput.value = fechaInasistencia;
            fechaInput.disabled = true;
            actualizarMinutosSugeridos(empleadoId, fechaInasistencia);
        }
        await cargarHE_Disponibles(empleadoId, fechaInasistencia);
        await cargarCompensacionesEmpleado(empleadoId);
    } else {
        selectEmp.disabled = false;
        document.getElementById('compensar-he-fecha-inasistencia').disabled = false;
        document.getElementById('compensar-he-bolsa-badge-container').innerHTML = '<span class="badge p-2 bg-secondary text-white w-100">Seleccione empleado y fecha...</span>';
        document.getElementById('compensaciones-he-list-container').classList.add('d-none');
    }

    // Control de permisos para el botón de guardar
    const saveBtn = document.querySelector('#modal-compensar-he .btn-success');
    if (saveBtn) {
        const hasPerm = typeof AuthService !== 'undefined' ? AuthService.hasPermission("marcaciones.compensar") : true;
        if (!hasPerm) {
            saveBtn.disabled = true;
            saveBtn.style.display = 'none';
        } else {
            saveBtn.disabled = false;
            saveBtn.style.display = 'inline-block';
        }
    }

    const modal = new bootstrap.Modal(modalEl);
    modal.show();
};

/**
 * Carga la bolsa de horas extras aprobadas en el periodo correspondiente
 */
async function cargarHE_Disponibles(empleadoId, fechaInasistencia) {
    const container = document.getElementById('compensar-he-bolsa-badge-container');
    if (!empleadoId || !fechaInasistencia) {
        container.innerHTML = '<span class="badge p-2 bg-secondary text-white w-100">Seleccione empleado y fecha...</span>';
        return;
    }

    container.innerHTML = '<span class="badge p-2 bg-light text-muted w-100"><span class="spinner-border spinner-border-sm me-1"></span> Cargando...</span>';

    try {
        const resp = await fetch(`/api/asistencia/compensaciones/bolsa/?empleado_id=${empleadoId}&fecha=${fechaInasistencia}`);
        if (!resp.ok) throw new Error('Error al consultar Bolsa HE');
        
        const jsonBody = await resp.json();
        const bolsa = jsonBody.data || {};
        const minsDisp = bolsa.minutos_disponibles || 0;
        
        container.dataset.minutosDisponibles = minsDisp;

        const classColor = minsDisp > 0 ? 'bg-success text-white' : 'bg-danger text-white';
        const text = minsDisp > 0 ? `${formatMinutesReadable(minsDisp)} disponibles` : 'Sin saldo disponible (0h 0m)';
        
        container.innerHTML = `<span class="badge p-2 ${classColor} w-100 fs-6 fw-bold shadow-sm">${text}</span>`;
    } catch (e) {
        console.error(e);
        container.innerHTML = '<span class="badge p-2 bg-danger text-white w-100">Error al cargar saldo</span>';
    }
}

/**
 * Registra una nueva compensación
 */
window.registrarCompensacionHE = async function() {
    const empleadoId = document.getElementById('compensar-he-empleado').value;
    const fechaInasistencia = document.getElementById('compensar-he-fecha-inasistencia').value;
    const tiempo = document.getElementById('compensar-he-tiempo').value;
    const obs = document.getElementById('compensar-he-observaciones').value;

    if (!empleadoId || !fechaInasistencia || !tiempo || !obs) {
        Swal.fire({ toast: true, position: 'top-end', icon: 'warning', title: 'Complete todos los campos', showConfirmButton: false, timer: 3000 });
        return;
    }

    const minutos = timeStringToMinutes(tiempo);
    if (isNaN(minutos) || minutos <= 0) {
        Swal.fire({ toast: true, position: 'top-end', icon: 'warning', title: 'Ingrese un formato de tiempo válido (HH:MM:SS)', showConfirmButton: false, timer: 3000 });
        return;
    }

    // Validar contra bolsa disponible
    const container = document.getElementById('compensar-he-bolsa-badge-container');
    const minsDisp = parseFloat(container.dataset.minutosDisponibles || 0);
    if (minutos > minsDisp) {
        Swal.fire({ icon: 'warning', title: 'Saldo Insuficiente', text: `No cuenta con suficientes horas extras en la bolsa del periodo. Requerido: ${tiempo} (${Math.round(minutos)} min) · Disponible: ${formatMinutesReadable(minsDisp)}.` });
        return;
    }

    const payload = {
        empleado_id: parseInt(empleadoId, 10),
        fecha_inasistencia: fechaInasistencia,
        minutos: minutos,
        observaciones: obs
    };

    const btn = document.querySelector('#modal-compensar-he .btn-success');
    const ogHtml = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Guardando...';
    btn.disabled = true;

    try {
        const resp = await fetch('/api/asistencia/compensaciones/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await resp.json();

        if (resp.ok) {
            Swal.fire({ toast: true, position: 'top-end', icon: 'success', title: 'Compensación de inasistencia guardada', showConfirmButton: false, timer: 3000 });
            bootstrap.Modal.getInstance(document.getElementById('modal-compensar-he')).hide();
            
            // Recargar datos principales para refrescar la grilla
            if (typeof window.loadMarcacionesData === 'function') {
                window.loadMarcacionesData();
            }
        } else {
            Swal.fire({ icon: 'error', title: 'Error', text: data.detail || 'No se pudo guardar la compensación.' });
        }
    } catch (e) {
        console.error(e);
        Swal.fire({ icon: 'error', title: 'Error de Red', text: 'Imposible conectar con el servidor.' });
    } finally {
        btn.innerHTML = ogHtml;
        btn.disabled = false;
    }
};

/**
 * Carga el historial de compensaciones aplicadas al empleado
 */
async function cargarCompensacionesEmpleado(empleadoId) {
    const listCont = document.getElementById('compensaciones-he-list-container');
    const listEl = document.getElementById('compensaciones-he-list');
    
    if (!empleadoId) {
        listCont.classList.add('d-none');
        return;
    }

    listCont.classList.remove('d-none');
    listEl.innerHTML = '<div class="text-center text-muted small"><span class="spinner-border spinner-border-sm"></span> Buscando...</div>';

    const fIni = window.stateMarcacionesApp?.fechaInicioRRHH || new Date(new Date().setMonth(new Date().getMonth() - 1)).toISOString().split('T')[0];
    const fFin = window.stateMarcacionesApp?.fechaFinRRHH || new Date(new Date().setMonth(new Date().getMonth() + 1)).toISOString().split('T')[0];

    try {
        const resp = await fetch(`/api/asistencia/compensaciones/?fecha_inicio=${fIni}&fecha_fin=${fFin}`);
        if (!resp.ok) throw new Error('Error al listar compensaciones');
        
        const jsonBody = await resp.json();
        const compensaciones = jsonBody.data || [];

        const delEmp = compensaciones.filter(c => String(c.empleado_id) === String(empleadoId));

        if (delEmp.length === 0) {
            listEl.innerHTML = '<div class="text-muted small italic">No hay compensaciones registradas en este período.</div>';
            return;
        }

        listEl.innerHTML = delEmp.map(c => {
            const hasDelPerm = typeof AuthService !== 'undefined' ? AuthService.hasPermission("marcaciones.compensar") : true;
            const deleteBtnHtml = hasDelPerm ? `
                <button class="btn btn-sm btn-outline-danger border-0" onclick="eliminarCompensacionHE(${c.id})" title="Revertir y recalcular">
                    <i class="bi bi-trash"></i>
                </button>
            ` : '';
            return `
            <div class="d-flex justify-content-between align-items-center p-2 mb-2 bg-white border rounded shadow-sm" style="border-left: 3px solid #059669 !important;">
                <div>
                    <div class="fw-bold small text-success">Falta ${c.fecha_inasistencia} cubierta con bolsa de H.E.</div>
                    <div class="text-muted" style="font-size: 0.7rem;">Monto: <b>${minutesToTimeString(c.minutos)}</b> · ${c.observaciones}</div>
                    <div class="text-muted" style="font-size: 0.65rem;">Autorizado por: ${c.registrado_por_nombre || 'Admin'}</div>
                </div>
                ${deleteBtnHtml}
            </div>
            `;
        }).join('');

    } catch (e) {
        console.error(e);
        listEl.innerHTML = '<div class="text-danger small">Error cargando historial de compensaciones</div>';
    }
}

/**
 * Revoca/elimina una compensación activa
 */
window.eliminarCompensacionHE = async function(id) {
    const res = await Swal.fire({
        title: '¿Revertir Compensación?',
        text: "La falta volverá a generar deuda horaria e inasistencia normal, y las horas extras del periodo recuperarán este saldo.",
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#6b7280',
        confirmButtonText: 'Sí, revertir'
    });

    if (!res.isConfirmed) return;

    try {
        const resp = await fetch(`/api/asistencia/compensaciones/${id}/`, { method: 'DELETE' });
        if (resp.ok) {
            Swal.fire({ toast: true, position: 'top-end', icon: 'success', title: 'Revertido con éxito', showConfirmButton: false, timer: 3000 });
            
            // Recargar la lista del modal
            const empId = document.getElementById('compensar-he-empleado').value;
            const fechaInas = document.getElementById('compensar-he-fecha-inasistencia').value;
            if (empId) {
                await cargarHE_Disponibles(empId, fechaInas);
                await cargarCompensacionesEmpleado(empId);
            }
            
            // Recargar datos principales para refrescar la grilla
            if (typeof window.loadMarcacionesData === 'function') {
                window.loadMarcacionesData();
            }
        } else {
            const data = await resp.json();
            Swal.fire({ icon: 'error', title: 'Error', text: data.detail || 'No se pudo eliminar.' });
        }
    } catch (e) {
        console.error(e);
        Swal.fire({ icon: 'error', title: 'Error de Red', text: 'Imposible conectar con el servidor.' });
    }
};
