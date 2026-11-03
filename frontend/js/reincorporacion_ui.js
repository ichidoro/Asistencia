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
    reincState.empleadoData = null;
    reincState.bioAlbaData = null;
    reincState.nombre = '';
    
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
    
    selectTipo.onchange = updateFinVisibility;  // una sola vez aunque el asistente se abra varias veces
    if (window.chipsDesdeSelect) window.chipsDesdeSelect(selectTipo);  // «A plazo fijo» / «Indefinido» como fichas
    updateFinVisibility(); // Inicializar

    try {
        // Cargar datos locales del empleado
        const response = await fetch(`/api/empleados/${id}/`);
        if (!response.ok) throw new Error("No se pudo cargar el empleado");
        reincState.empleadoData = await response.json();
        const emp = reincState.empleadoData;
        const nom = emp.nombre_completo || [emp.apellido_paterno, emp.apellido_materno, emp.nombre].filter(Boolean).join(' ');
        reincState.nombre = window.nombreTitulo ? window.nombreTitulo(nom) : nom;
        reincUpdateUI();
        
        // Paso 0: Sincronización BioAlba
        await reincFetchBioAlbaDiff();
    } catch (error) {
        console.error("Error inicializando wizard:", error);
        document.getElementById('reinc-sync-diff').innerHTML =
            '<div class="vn-ban a"><i class="bi bi-wifi-off" aria-hidden="true"></i><div><b>No se pudo consultar BioAlba</b>' + String(error.message || '').replace(/</g, '&lt;') + '</div></div>'
            + '<div><button type="button" class="btn btn-light btn-sm" onclick="reincFetchBioAlbaDiff()"><i class="bi bi-arrow-clockwise me-1" aria-hidden="true"></i>Reintentar</button></div>';
    }
};

// 2. Sincronización BioAlba (Paso 1)
async function reincFetchBioAlbaDiff() {
    const container = document.getElementById('reinc-sync-diff');
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
    container.innerHTML = '<div class="vn-nota"><span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Buscando a la persona en BioAlba (RUT ' + esc(reincState.empleadoData.rut) + ')…</div>';

    try {
        const response = await fetch(`/api/sync/search/?rut=${reincState.empleadoData.rut}`);
        if (!response.ok) throw new Error("BioAlba no respondió");

        const results = await response.json();
        const sourceData = results.find(r => r.rut === reincState.empleadoData.rut);

        if (!sourceData) {
            container.innerHTML = '<div class="vn-ban a"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i><div><b>La persona no está en BioAlba</b>Debe crearse allí antes de reincorporarla.</div></div>';
            reincUpdateUI();
            return;
        }

        reincState.bioAlbaData = sourceData;
        const local = reincState.empleadoData;
        const remote = sourceData;
        // Área y cargo como quedarán; si cambiaron, debajo dice cómo estaban
        const dato = (nuevo, antes) => esc(nuevo || '—') + (antes !== nuevo ? '<span>antes: ' + esc(antes || 'sin dato') + '</span>' : '');
        container.innerHTML = '<div class="vn-kvs">'
            + '<div><span>Nombre</span><b>' + esc(window.nombreTitulo ? window.nombreTitulo(remote.nombre) : remote.nombre) + '</b></div>'
            + '<div><span>Área</span><b>' + dato(remote.area, local.area) + '</b></div>'
            + '<div><span>Cargo</span><b>' + dato(remote.cargo, local.cargo) + '</b></div>'
            + '</div><div class="form-text">Al seguir, el área y el cargo quedan como en BioAlba.</div>';

        // Datos del paso 2 (vienen de BioAlba)
        document.getElementById('reinc-area').value = remote.area;
        document.getElementById('reinc-cargo').value = remote.cargo;
        document.getElementById('reinc-compania').value = remote.compania || local.compania || '';
        document.getElementById('reinc-area-display').textContent = remote.area;
        reincUpdateUI();

    } catch (err) {
        container.innerHTML = '<div class="vn-ban a"><i class="bi bi-wifi-off" aria-hidden="true"></i><div><b>No se pudo consultar BioAlba</b>' + esc(err.message) + '</div></div>'
            + '<div><button type="button" class="btn btn-light btn-sm" onclick="reincFetchBioAlbaDiff()"><i class="bi bi-arrow-clockwise me-1" aria-hidden="true"></i>Reintentar</button></div>';
        reincUpdateUI();
    }
}

// 3. Navegación entre pasos
const REINC_PASOS = ['BioAlba', 'Contrato', 'Horario'];
function reincUpdateUI() {
    document.querySelectorAll('.reinc-pane').forEach((p, idx) => p.classList.toggle('d-none', idx + 1 !== reincState.step));

    // Pasos: hechos con ✓, el actual en azul
    document.querySelectorAll('.reinc-step-indicator').forEach((l, idx) => {
        const paso = l.parentElement;
        const hecho = idx + 1 < reincState.step;
        paso.classList.toggle('ok', hecho);
        paso.classList.toggle('cur', idx + 1 === reincState.step);
        l.innerHTML = hecho ? '<i class="bi bi-check-lg" aria-hidden="true"></i>' : String(idx + 1);
        const linea = paso.nextElementSibling;
        if (linea && linea.classList.contains('vn-sl')) linea.classList.toggle('ok', hecho);
    });
    const sub = document.getElementById('reinc-sub');
    if (sub) sub.textContent = [reincState.nombre, 'Paso ' + reincState.step + ' de 3 · ' + REINC_PASOS[reincState.step - 1]].filter(Boolean).join(' · ');

    document.getElementById('btn-reinc-prev').disabled = reincState.step === 1;
    const btnNext = document.getElementById('btn-reinc-next');
    const btnFinish = document.getElementById('btn-reinc-finish');
    btnNext.classList.toggle('d-none', reincState.step === 3);
    btnFinish.classList.toggle('d-none', reincState.step !== 3);
    // Sin la persona en BioAlba no se sigue: el área y el cargo salen de ahí
    btnNext.disabled = reincState.step === 1 && !reincState.bioAlbaData;
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
            Avisos.falta('Falta la fecha de reingreso.');
            return;
        }
        if (tContrato === 'Temporal' && !fFin) {
            Avisos.falta('Falta la fecha de término. Es obligatoria en un contrato temporal.');
            return;
        }

        // [VALIDACIÓN V2] Coherencia cronológica: fecha_fin no puede ser anterior a fecha_inicio
        if (fFin && fInicio && fFin < fInicio) {
            Avisos.falta('La fecha de término no puede ser anterior a la de reingreso.');
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
    select.innerHTML = '<option value="">Cargando turnos…</option>';
    
    try {
        const response = await fetch(`/api/turnos/?area=${encodeURIComponent(area)}&activo=true`);
        const turnos = await response.json();
        
        if (turnos.length === 0) {
            select.innerHTML = '<option value="">No hay turnos creados para esta área</option>';
            return;
        }
        
        select.innerHTML = '<option value="">Elegir turno</option>' + 
            turnos.map(t => {
                const tipoPlanificacion = (t.tipo_programacion === 'BOLSA_FLEXIBLE' || t.tipo_programacion === 'FLEXIBLE_BOLSA')
                    ? 'Bolsa Flexible'
                    : 'Ciclo Inteligente';
                const horario = (t.tipo_programacion === 'CICLO_INTELIGENTE' || t.tipo_programacion === 'DINAMICO_FLEXIBLE')
                    ? '(Múltiples opciones)'
                    : '';
                return `<option value="${t.id}" data-tipo="${tipoPlanificacion}" data-horario="${horario}">${t.nombre}</option>`;
            }).join('');
            
        select.removeEventListener('change', window.updateTurnoInfoLabel);
        select.addEventListener('change', window.updateTurnoInfoLabel);
        select.dispatchEvent(new Event('change'));
            
    } catch (e) {
        select.innerHTML = '<option value="">No se pudieron cargar los turnos</option>';
    }
}

// 4. Finalizar Reincorporación
window.finishReincorporacion = async function() {
    const btnFinish = document.getElementById('btn-reinc-finish');
    const turnoId = document.getElementById('reinc-turno-id').value;
    
    if (!turnoId) {
        Avisos.falta('Falta elegir el horario para seguir.');
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
        btnFinish.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>Reincorporando…';

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
            window.showToast("Listo: persona reincorporada y asistencia recalculada.", "success");
        } else {
            Avisos.listo("Listo. Persona reincorporada.");
        }
        
        // Recargar lista de empleados
        if (window.loadEmpleados) window.loadEmpleados();
        if (window.loadStats) window.loadStats();

    } catch (error) {
        Avisos.error("No se pudo reincorporar a la persona. " + error.message);
    } finally {
        btnFinish.disabled = false;
        btnFinish.textContent = 'Reincorporar';
    }
}
