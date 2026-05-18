/**
 * UI Module - Reincorporación de Empleados (Wizard)
 * Maneja el flujo de 3 pasos para reactivar empleados inactivos.
 */

let reincState = {
    step: 1,
    empleadoId: null,
    empleadoData: null,
    bioAlbaData: null,
    turnosDisponibles: []
};

// 1. Abrir Wizard
window.openReincorporarWizard = async function(id) {
    reincState.empleadoId = id;
    reincState.step = 1;
    
    // Abrir modal (Bootstrap)
    const modalEl = document.getElementById('modal-reincorporacion-wizard');
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
    modalEl.removeAttribute('aria-hidden');

    // Reset UI
    reincUpdateUI();
    
    // Configurar visibilidad condicional de fecha fin (Paso 2)
    const selectTipo = document.getElementById('reinc-tipo-contrato');
    const containerFin = document.getElementById('reinc-fecha-fin-container');
    
    const updateFinVisibility = () => {
        if (selectTipo.value === 'Temporal') {
            containerFin.classList.remove('d-none');
        } else {
            containerFin.classList.add('d-none');
            document.getElementById('reinc-fecha-fin').value = '';
        }
    };
    
    selectTipo.addEventListener('change', updateFinVisibility);
    updateFinVisibility(); // Inicializar

    try {
        // Cargar datos locales del empleado
        const response = await fetch(`/api/empleados/${id}/`);
        if (!response.ok) throw new Error("No se pudo cargar el empleado");
        reincState.empleadoData = await response.json();
        
        // Paso 0: Sincronización BioAlba
        await reincFetchBioAlbaDiff();
    } catch (error) {
        console.error("Error inicializando wizard:", error);
        document.getElementById('reinc-sync-diff').innerHTML = `
            <div class="alert alert-danger py-2">
                ❌ Error al conectar con BioAlba: ${error.message}
            </div>
            <button class="btn btn-sm btn-outline-primary" onclick="reincFetchBioAlbaDiff()">🔄 Reintentar</button>
        `;
    }
};

// 2. Sincronización BioAlba (Paso 1)
async function reincFetchBioAlbaDiff() {
    const container = document.getElementById('reinc-sync-diff');
    container.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border spinner-border-sm text-primary"></div>
            Consultando BioAlba para RUT ${reincState.empleadoData.rut}...
        </div>
    `;

    try {
        // Reutilizamos el endpoint de sync por RUT (si existe) o el general de empleados
        // Simulamos consulta (en producción esto llama al sync de rrhh)
        const response = await fetch(`/api/sync/search/?rut=${reincState.empleadoData.rut}`);
        if (!response.ok) throw new Error("Fallo en sincronización externa");
        
        const results = await response.json();
        const sourceData = results.find(r => r.rut === reincState.empleadoData.rut);
        
        if (!sourceData) {
            container.innerHTML = `
                <div class="alert alert-warning">
                    ⚠️ <strong>Empleado no encontrado en BioAlba.</strong> 
                    Debe estar creado en la fuente de verdad antes de reincorporar.
                </div>
            `;
            return;
        }

        reincState.bioAlbaData = sourceData;
        
        // Mostrar comparativa
        const local = reincState.empleadoData;
        const remote = sourceData;
        
        let diffHTML = '<table class="table table-sm table-borderless mb-0 small">';
        diffHTML += `<tr><td class="text-muted">Nombre:</td><td class="fw-bold">${remote.nombre}</td></tr>`;
        
        // Resaltar cambios de Area/Cargo
        const areaDiff = local.area !== remote.area;
        diffHTML += `<tr><td class="text-muted">Área:</td><td>
            ${areaDiff ? `<span class="text-danger decoration-line-through me-2">${local.area || 'N/A'}</span>` : ''}
            <span class="badge ${areaDiff ? 'bg-warning text-dark' : 'bg-success'}">${remote.area}</span>
        </td></tr>`;
        
        const cargoDiff = local.cargo !== remote.cargo;
        diffHTML += `<tr><td class="text-muted">Cargo:</td><td>
            ${cargoDiff ? `<span class="text-danger decoration-line-through me-2">${local.cargo || 'N/A'}</span>` : ''}
            <span class="badge ${cargoDiff ? 'bg-warning text-dark' : 'bg-success'}">${remote.cargo}</span>
        </td></tr>`;
        
        diffHTML += '</table>';
        
        container.innerHTML = `
            <div class="mb-3">Se han detectado los siguientes datos actualizados:</div>
            ${diffHTML}
            <div class="mt-3 text-muted" style="font-size: 0.8rem;">
                * Al continuar, se actualizarán estos campos automáticamente.
            </div>
        `;

        // Pre-poblar form de paso 2
        document.getElementById('reinc-area').value = remote.area;
        document.getElementById('reinc-cargo').value = remote.cargo;
        document.getElementById('reinc-compania').value = remote.compania || local.compania || '';
        document.getElementById('reinc-area-display').textContent = remote.area;
        
        // Habilitar siguiente
        document.getElementById('btn-reinc-next').disabled = false;

    } catch (err) {
        container.innerHTML = `<div class="text-danger">Error: ${err.message}</div>`;
    }
}

// 3. Navegación entre pasos
function reincUpdateUI() {
    // Panes
    document.querySelectorAll('.reinc-pane').forEach((p, idx) => {
        if (idx + 1 === reincState.step) p.classList.remove('d-none');
        else p.classList.add('d-none');
    });

    // Labels
    document.querySelectorAll('.reinc-step-indicator').forEach((l, idx) => {
        if (idx + 1 < reincState.step) {
            l.className = 'reinc-step-indicator completed';
            l.innerHTML = '✓';
        } else if (idx + 1 === reincState.step) {
            l.className = 'reinc-step-indicator active';
            l.innerHTML = idx + 1;
        } else {
            l.className = 'reinc-step-indicator';
            l.innerHTML = idx + 1;
        }
    });

    // Buttons
    document.getElementById('btn-reinc-prev').disabled = reincState.step === 1;
    
    const btnNext = document.getElementById('btn-reinc-next');
    const btnFinish = document.getElementById('btn-reinc-finish');
    
    if (reincState.step === 3) {
        btnNext.classList.add('d-none');
        btnFinish.classList.remove('d-none');
    } else {
        btnNext.classList.remove('d-none');
        btnFinish.classList.add('d-none');
    }
}

// Botón Siguiente
document.getElementById('btn-reinc-next').addEventListener('click', async () => {
    if (reincState.step === 1) {
        reincState.step = 2;
    } else if (reincState.step === 2) {
        // Validar Paso 2
        const fInicio = document.getElementById('reinc-fecha-inicio').value;
        const tContrato = document.getElementById('reinc-tipo-contrato').value;
        const fFin = document.getElementById('reinc-fecha-fin').value;

        if (!fInicio) {
            alert("Debe indicar la fecha de re-ingreso");
            return;
        }
        if (tContrato === 'Temporal' && !fFin) {
            alert("Debe indicar la fecha de término para contrato temporal");
            return;
        }

        // [VALIDACIÓN V2] Coherencia cronológica: fecha_fin no puede ser anterior a fecha_inicio
        if (fFin && fInicio && fFin < fInicio) {
            alert("La fecha de término no puede ser anterior a la fecha de re-ingreso.");
            return;
        }

        // Cargar turnos para el área detectada
        await reincLoadTurnos(document.getElementById('reinc-area').value);
        reincState.step = 3;
    }
    reincUpdateUI();
});

// Botón Anterior
document.getElementById('btn-reinc-prev').addEventListener('click', () => {
    if (reincState.step > 1) {
        reincState.step--;
        reincUpdateUI();
    }
});

// Cargar Turnos por Área
async function reincLoadTurnos(area) {
    const select = document.getElementById('reinc-turno-id');
    select.innerHTML = '<option value="">-- Cargando turnos... --</option>';
    
    try {
        const response = await fetch(`/api/turnos/?area=${encodeURIComponent(area)}`);
        const turnos = await response.json();
        
        if (turnos.length === 0) {
            select.innerHTML = '<option value="">❌ No hay turnos creados para esta área</option>';
            return;
        }
        
        select.innerHTML = '<option value="">-- Seleccionar Turno --</option>' + 
            turnos.map(t => {
                const tipoPlanificacion = t.tipo_programacion === 'FLEXIBLE_BOLSA'
                    ? 'Flexible (Bolsa de Horas)'
                    : 'Ciclo Inteligente (Smart Match)';
                const horario = t.tipo_programacion === 'DINAMICO_FLEXIBLE'
                    ? '(Múltiples opciones)'
                    : '';
                return `<option value="${t.id}" data-tipo="${tipoPlanificacion}" data-horario="${horario}">${t.nombre}</option>`;
            }).join('');
            
        select.removeEventListener('change', window.updateTurnoInfoLabel);
        select.addEventListener('change', window.updateTurnoInfoLabel);
        select.dispatchEvent(new Event('change'));
            
    } catch (e) {
        select.innerHTML = '<option value="">❌ Error cargando turnos</option>';
    }
}

// 4. Finalizar Reincorporación
window.finishReincorporacion = async function() {
    const btnFinish = document.getElementById('btn-reinc-finish');
    const turnoId = document.getElementById('reinc-turno-id').value;
    
    if (!turnoId) {
        alert("Debe seleccionar un horario para continuar");
        return;
    }

    const payload = {
        fecha_inicio: document.getElementById('reinc-fecha-inicio').value,
        fecha_fin: document.getElementById('reinc-fecha-fin').value || null,
        tipo_contrato: document.getElementById('reinc-tipo-contrato').value,
        area: document.getElementById('reinc-area').value,
        cargo: document.getElementById('reinc-cargo').value,
        compania: document.getElementById('reinc-compania').value,
        turno_id: parseInt(turnoId)
    };

    try {
        btnFinish.disabled = true;
        btnFinish.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Procesando...';

        const response = await fetch(`/api/empleados/${reincState.empleadoId}/reincorporar/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Fallo al reincorporar");
        }

        // Éxito
        const modalEl = document.getElementById('modal-reincorporacion-wizard');
        bootstrap.Modal.getInstance(modalEl).hide();
        
        if (window.showToast) {
            window.showToast("Empleado reincorporado con éxito. Asistencia recalculada.", "success");
        } else {
            alert("¡Éxito! Empleado reincorporado. La lista se actualizará.");
        }
        
        // Recargar lista de empleados
        if (window.loadEmpleados) window.loadEmpleados();
        if (window.loadStats) window.loadStats();

    } catch (error) {
        alert("Error: " + error.message);
    } finally {
        btnFinish.disabled = false;
        btnFinish.innerHTML = '<i class="bi bi-check-circle-fill me-2"></i>Finalizar y Activar';
    }
}
