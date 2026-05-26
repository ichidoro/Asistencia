// ============================================================
// SISTEMA DE INTERCAMBIOS (DÍAS COMPENSATORIOS)
// ============================================================

(function injectIntercambioStyles() {
    if (document.getElementById('intercambio-panel-styles')) return;
    const style = document.createElement('style');
    style.id = 'intercambio-panel-styles';
    style.textContent = `
        .badge-compensatorio {
            background: #e0e7ff;
            color: #4338ca;
            border: 1px solid #c7d2fe;
        }
        .badge-inasistencia-compensada {
            background: #f1f5f9;
            color: #64748b;
            border: 1px solid #cbd5e1;
            text-decoration: line-through;
        }
    `;
    document.head.appendChild(style);

    // Inyectar el Modal
    if (!document.getElementById('modal-intercambio')) {
        const modalHTML = `
            <div class="modal fade" id="modal-intercambio" tabindex="-1">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content border-0 shadow-lg" style="border-radius: 12px; overflow: hidden;">
                        <div class="modal-header" style="background: linear-gradient(135deg, #4f46e5 0%, #3730a3 100%); color: white; border-bottom: none;">
                            <h5 class="modal-title fw-bold">
                                <i class="bi bi-arrow-left-right me-2"></i> Registrar Día Compensatorio
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body p-4 bg-light">
                            <p class="text-muted small mb-4">
                                <i class="bi bi-info-circle text-primary"></i> 
                                Permite intercambiar un día de descanso por un día laboral (1x1) sin generar deuda ni horas extras.
                            </p>

                            <form id="form-intercambio">
                                <!-- Empleado (Auto-seleccionado si se abre desde la grilla, o seleccionable) -->
                                <div class="mb-3">
                                    <label for="intercambio-empleado" class="form-label fw-bold text-dark small">Empleado</label>
                                    <select id="intercambio-empleado" class="form-select border-primary shadow-sm" required>
                                        <option value="">Seleccione un empleado...</option>
                                    </select>
                                </div>

                                <div class="row g-3 mb-3">
                                    <div class="col-6">
                                        <label for="intercambio-fecha-destino" class="form-label fw-bold text-dark small">Fecha Libre (Día a trabajar)</label>
                                        <input type="date" id="intercambio-fecha-destino" class="form-control" required
                                               title="Día que el empleado debía descansar, pero que aceptó trabajar.">
                                        <small class="text-muted" style="font-size:0.65rem;">Se pagará normal (sin H.E.)</small>
                                    </div>
                                    <div class="col-6">
                                        <label for="intercambio-fecha-origen" class="form-label fw-bold text-dark small">Fecha Laboral (Día a faltar)</label>
                                        <input type="date" id="intercambio-fecha-origen" class="form-control" required
                                               title="Día que el empleado debía trabajar, pero que se tomará libre en compensación.">
                                        <small class="text-muted" style="font-size:0.65rem;">Se justificará sin deuda</small>
                                    </div>
                                </div>

                                <div class="mb-3">
                                    <label for="intercambio-observaciones" class="form-label fw-bold text-dark small">Observaciones / Motivo</label>
                                    <textarea id="intercambio-observaciones" class="form-control" rows="2" placeholder="Ej: Trato especial por contingencia en el área..." required></textarea>
                                </div>
                            </form>

                            <!-- Lista de intercambios recientes del empleado seleccionado -->
                            <div id="intercambios-list-container" class="mt-4 d-none">
                                <h6 class="fw-bold text-muted small border-bottom pb-2">Intercambios del Empleado en el Período</h6>
                                <div id="intercambios-list" style="max-height: 150px; overflow-y: auto;"></div>
                            </div>

                        </div>
                        <div class="modal-footer bg-white">
                            <button type="button" class="btn btn-light" data-bs-dismiss="modal">Cancelar</button>
                            <button type="button" class="btn btn-primary px-4 fw-bold shadow-sm" onclick="registrarIntercambio()">
                                <i class="bi bi-save me-1"></i> Guardar Intercambio
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHTML);
    }
})();

/**
 * Abre el modal de Intercambio de Día (Día Compensatorio)
 */
window.abrirModalIntercambio = async function(empleadoId = null, fechaSugerida = null) {
    const modalEl = document.getElementById('modal-intercambio');
    if (!modalEl) return;

    // Poblar combo de empleados desde el state si existe
    const selectEmp = document.getElementById('intercambio-empleado');
    selectEmp.innerHTML = '<option value="">Seleccione un empleado...</option>';
    
    let empleadosList = window.stateMarcacionesApp?.data?.empleados || [];
    
    // Si no hay empleados cargados en memoria, tratar de cargarlos del DOM principal (filtros)
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

    // Event listener para cargar los intercambios al cambiar el empleado
    selectEmp.onchange = () => {
        cargarIntercambiosEmpleado(selectEmp.value);
    };

    // Resetear formulario
    document.getElementById('form-intercambio').reset();
    if (empleadoId) selectEmp.value = empleadoId;
    
    // Si hay una fecha sugerida (ej. click en celda), la ponemos donde falte
    if (fechaSugerida) {
        // Podríamos intentar deducir si es origen o destino, pero por ahora lo dejamos a criterio del usuario.
        // O lo asignamos al destino (el día extra trabajado) como default.
        document.getElementById('intercambio-fecha-destino').value = fechaSugerida;
    }

    if (empleadoId) {
        await cargarIntercambiosEmpleado(empleadoId);
    } else {
        document.getElementById('intercambios-list-container').classList.add('d-none');
    }

    // Control de permisos para el botón de guardar
    const saveBtn = document.querySelector('#modal-intercambio .btn-primary');
    if (saveBtn) {
        const hasPerm = typeof AuthService !== 'undefined' ? AuthService.hasPermission("marcaciones.intercambio") : true;
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
 * Registra un nuevo intercambio (Día Compensatorio)
 */
window.registrarIntercambio = async function() {
    const empleadoId = document.getElementById('intercambio-empleado').value;
    const fechaOrigen = document.getElementById('intercambio-fecha-origen').value;
    const fechaDestino = document.getElementById('intercambio-fecha-destino').value;
    const obs = document.getElementById('intercambio-observaciones').value;

    if (!empleadoId || !fechaOrigen || !fechaDestino || !obs) {
        Swal.fire({ toast: true, position: 'top-end', icon: 'warning', title: 'Complete todos los campos', showConfirmButton: false, timer: 3000 });
        return;
    }

    if (fechaOrigen === fechaDestino) {
        Swal.fire({ toast: true, position: 'top-end', icon: 'warning', title: 'Las fechas deben ser diferentes', showConfirmButton: false, timer: 3000 });
        return;
    }

    const payload = {
        empleado_id: parseInt(empleadoId, 10),
        fecha_origen: fechaOrigen,
        fecha_destino: fechaDestino,
        observaciones: obs
    };

    const btn = document.querySelector('#modal-intercambio .btn-primary');
    const ogHtml = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Guardando...';
    btn.disabled = true;

    try {
        const resp = await fetch('/api/asistencia/intercambios/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await resp.json();

        if (resp.ok) {
            Swal.fire({ toast: true, position: 'top-end', icon: 'success', title: 'Día Compensatorio registrado', showConfirmButton: false, timer: 3000 });
            bootstrap.Modal.getInstance(document.getElementById('modal-intercambio')).hide();
            
            // Recargar datos de marcaciones en background para refrescar la UI
            if (typeof window.loadMarcacionesData === 'function') {
                window.loadMarcacionesData();
            }
        } else {
            Swal.fire({ icon: 'error', title: 'Error', text: data.detail || 'No se pudo registrar.' });
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
 * Carga los intercambios recientes del empleado
 */
async function cargarIntercambiosEmpleado(empleadoId) {
    const listCont = document.getElementById('intercambios-list-container');
    const listEl = document.getElementById('intercambios-list');
    
    if (!empleadoId) {
        listCont.classList.add('d-none');
        return;
    }

    listCont.classList.remove('d-none');
    listEl.innerHTML = '<div class="text-center text-muted small"><span class="spinner-border spinner-border-sm"></span> Buscando...</div>';

    // Rango: +- 1 mes desde hoy o desde el filtro activo
    const fIni = window.stateMarcacionesApp?.fechaInicioRRHH || new Date(new Date().setMonth(new Date().getMonth() - 1)).toISOString().split('T')[0];
    const fFin = window.stateMarcacionesApp?.fechaFinRRHH || new Date(new Date().setMonth(new Date().getMonth() + 1)).toISOString().split('T')[0];

    try {
        const resp = await fetch(`/api/asistencia/intercambios/?fecha_inicio=${fIni}&fecha_fin=${fFin}`);
        if (!resp.ok) throw new Error('Error al listar');
        const jsonBody = await resp.json();
        const intercambios = jsonBody.data || [];

        const delEmp = intercambios.filter(i => String(i.empleado_id) === String(empleadoId));

        if (delEmp.length === 0) {
            listEl.innerHTML = '<div class="text-muted small italic">No hay intercambios registrados en este período.</div>';
            return;
        }

        listEl.innerHTML = delEmp.map(i => {
            const hasDelPerm = typeof AuthService !== 'undefined' ? AuthService.hasPermission("marcaciones.intercambio") : true;
            const deleteBtnHtml = hasDelPerm ? `
                <button class="btn btn-sm btn-outline-danger border-0" onclick="eliminarIntercambio(${i.id})" title="Eliminar y recalcular">
                    <i class="bi bi-trash"></i>
                </button>
            ` : '';
            return `
            <div class="d-flex justify-content-between align-items-center p-2 mb-2 bg-white border rounded shadow-sm">
                <div>
                    <div class="fw-bold small" style="color:#4f46e5;">1x1: Faltó el ${i.fecha_origen} <i class="bi bi-arrow-right"></i> Trabajó el ${i.fecha_destino}</div>
                    <div class="text-muted" style="font-size: 0.7rem;">${i.observaciones}</div>
                    <div class="text-muted" style="font-size: 0.65rem;">Por: ${i.registrado_por_nombre || 'Admin'}</div>
                </div>
                ${deleteBtnHtml}
            </div>
            `;
        }).join('');

    } catch (e) {
        console.error(e);
        listEl.innerHTML = '<div class="text-danger small">Error cargando historial</div>';
    }
}

/**
 * Elimina un intercambio
 */
window.eliminarIntercambio = async function(id) {
    const res = await Swal.fire({
        title: '¿Revertir Intercambio?',
        text: "Las fechas afectadas serán recalculadas a su estado normal (generando deuda u horas extra si corresponde).",
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#6b7280',
        confirmButtonText: 'Sí, revertir'
    });

    if (!res.isConfirmed) return;

    try {
        const resp = await fetch(`/api/asistencia/intercambios/${id}/`, { method: 'DELETE' });
        if (resp.ok) {
            Swal.fire({ toast: true, position: 'top-end', icon: 'success', title: 'Revertido con éxito', showConfirmButton: false, timer: 3000 });
            // Recargar la lista del modal
            const empId = document.getElementById('intercambio-empleado').value;
            if (empId) await cargarIntercambiosEmpleado(empId);
            
            // Recargar datos principales
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
