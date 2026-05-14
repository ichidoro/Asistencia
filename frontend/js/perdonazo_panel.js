// ============================================================
// NUEVA UX: SWITCH PERDONAZOS + PANEL LATERAL POR FECHA
// Archivo separado para las funciones del sistema Perdonazo
// ============================================================

// Inyectar CSS del panel lateral una sola vez al cargar
(function injectPerdonazoStyles() {
    if (document.getElementById('perdonazo-panel-styles')) return;
    const style = document.createElement('style');
    style.id = 'perdonazo-panel-styles';
    style.textContent = `
        #panel-perdonazo {
            position: fixed;
            top: 0; right: -460px;
            width: 440px;
            height: 100vh;
            background: #fff;
            box-shadow: -4px 0 32px rgba(0,0,0,0.15);
            z-index: 9999;
            transition: right 0.35s cubic-bezier(.4,0,.2,1);
            display: flex; flex-direction: column;
            border-left: 3px solid #10b981;
            font-family: 'Inter', sans-serif;
            overflow: hidden;
        }
        #panel-perdonazo.abierto { right: 0; }
        #panel-perdonazo .panel-header {
            background: linear-gradient(135deg, #064e3b 0%, #047857 100%);
            color: white; padding: 18px 20px 14px;
            flex-shrink: 0;
        }
        #panel-perdonazo .panel-body {
            flex: 1; overflow-y: auto; padding: 16px;
        }
        #panel-perdonazo .panel-footer {
            padding: 12px 16px;
            border-top: 1px solid #e2e8f0;
            background: #f8fafc;
            flex-shrink: 0;
        }
        #panel-perdonazo .emp-row {
            display: flex; align-items: center; gap: 10px;
            padding: 8px 10px; border-radius: 8px;
            border: 1px solid #e2e8f0;
            margin-bottom: 6px; background: #fff;
            transition: background 0.15s, border-color 0.15s;
            cursor: pointer;
        }
        #panel-perdonazo .emp-row:hover { background: #f0fdf4; border-color: #86efac; }
        #panel-perdonazo .emp-row.seleccionado { background: #dcfce7; border-color: #22c55e; }
        #panel-perdonazo .badge-estado {
            font-size: 0.6rem; font-weight: 700; padding: 2px 6px;
            border-radius: 999px; display: inline-block;
        }
        #panel-perdonazo .badge-deuda { background: #fee2e2; color: #dc2626; }
        #panel-perdonazo .badge-condonado { background: #dcfce7; color: #16a34a; }
        .perdonazo-overlay {
            position: fixed; inset: 0;
            background: rgba(0,0,0,0.3);
            z-index: 9998;
            display: none;
        }
        .perdonazo-overlay.visible { display: block; }
    `;
    document.head.appendChild(style);

    // Crear overlay
    if (!document.getElementById('perdonazo-overlay')) {
        const overlay = document.createElement('div');
        overlay.id = 'perdonazo-overlay';
        overlay.className = 'perdonazo-overlay';
        overlay.onclick = () => window.cerrarPanelPerdonazo();
        document.body.appendChild(overlay);
    }
    // Crear panel lateral
    if (!document.getElementById('panel-perdonazo')) {
        const panel = document.createElement('div');
        panel.id = 'panel-perdonazo';
        panel.innerHTML = `
            <div class="panel-header">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                    <div>
                        <div style="font-size:0.7rem;opacity:0.8;letter-spacing:1px;text-transform:uppercase;">Perdonazo por Día</div>
                        <div id="panel-perdonazo-titulo" style="font-size:1.1rem;font-weight:800;margin-top:2px;">Cargando...</div>
                    </div>
                    <button onclick="cerrarPanelPerdonazo()" style="background:rgba(255,255,255,0.2);border:none;color:white;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:1rem;">✕</button>
                </div>
            </div>
            <div class="panel-body" id="panel-perdonazo-body">
                <div style="text-align:center;padding:40px;color:#94a3b8;">Cargando empleados...</div>
            </div>
            <div class="panel-footer">
                <div style="margin-bottom:10px;">
                    <label style="font-size:0.75rem;font-weight:700;color:#374151;display:block;margin-bottom:5px;">¿Qué deuda condonar?</label>
                    <select id="panel-tipo-condonacion" style="width:100%;padding:6px 10px;border:1px solid #d1fae5;border-radius:8px;font-size:0.8rem;background:#f0fdf4;color:#047857;font-weight:600;">
                        <option value="1">Solo Salida Adelantada</option>
                        <option value="2">Solo Atraso</option>
                        <option value="3">Atraso + Salida Adelantada</option>
                    </select>
                </div>
                <div style="display:flex;gap:8px;">
                    <button onclick="ejecutarPerdonazoPanelSeleccionados()" style="flex:1;background:linear-gradient(135deg,#10b981,#059669);color:white;border:none;border-radius:8px;padding:10px;font-weight:700;cursor:pointer;font-size:0.85rem;">
                        <i class="bi bi-gift-fill me-1"></i> Aplicar Perdonazo
                    </button>
                    <button onclick="revocarPerdonazoPanelSeleccionados()" style="background:#fee2e2;color:#dc2626;border:1px solid #fca5a5;border-radius:8px;padding:10px;font-weight:600;cursor:pointer;font-size:0.8rem;">
                        <i class="bi bi-x-circle"></i> Revocar
                    </button>
                </div>
                <div id="panel-seleccion-info" style="text-align:center;font-size:0.7rem;color:#6b7280;margin-top:6px;">Seleccione empleados arriba</div>
            </div>
        `;
        document.body.appendChild(panel);
    }
})();

/**
 * Activa/desactiva el modo Perdonazos (llamado desde el switch)
 */
window.toggleModoPerdonazo = function(activo) {
    window._perdonazoState.activo = activo;
    window._perdonazoState.seleccionados.clear();
    document.body.classList.toggle('modo-perdonazo', activo);
    // Re-renderizar toolbar para reflejar estado visual del switch
    const container = document.getElementById('page-marcaciones');
    if (container && typeof renderMarcacionesToolbar === 'function') {
        renderMarcacionesToolbar(container);
    }
    if (activo) {
        Swal.fire({
            icon: 'info',
            title: 'Modo Perdonazos activo',
            html: 'Haz <b>clic en el encabezado de una fecha</b> para gestionar los perdonazos de ese día.',
            timer: 3500,
            showConfirmButton: false,
            toast: true,
            position: 'top-end'
        });
    }
};

/**
 * Cierra el panel lateral de perdonazos
 */
window.cerrarPanelPerdonazo = function() {
    const panel = document.getElementById('panel-perdonazo');
    const overlay = document.getElementById('perdonazo-overlay');
    if (panel) panel.classList.remove('abierto');
    if (overlay) overlay.classList.remove('visible');
    window._perdonazoState.seleccionados.clear();
};

/**
 * Abre el panel lateral con los empleados que tienen deuda en la fecha dada.
 * @param {string} fecha - Fecha en formato YYYY-MM-DD
 */
window.abrirPanelPerdonazoPorFecha = function(fecha) {
    if (!window._perdonazoState.activo) return;
    const panel = document.getElementById('panel-perdonazo');
    const overlay = document.getElementById('perdonazo-overlay');
    const titulo = document.getElementById('panel-perdonazo-titulo');
    const body = document.getElementById('panel-perdonazo-body');
    if (!panel) return;

    // Título humanizado
    const fechaDisplay = new Date(fecha + 'T12:00:00').toLocaleDateString('es-CL', {
        weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
    });
    titulo.textContent = fechaDisplay;
    panel.dataset.fechaActual = fecha;

    // Recopilar empleados con deuda desde datos en memoria
    const matrix = window.stateMarcacionesApp.data?.matrix;
    const empleados = window.stateMarcacionesApp.data?.empleados || [];

    if (!matrix) {
        body.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8;">No hay datos cargados</div>';
        panel.classList.add('abierto');
        overlay.classList.add('visible');
        return;
    }

    const empConDeuda = [];
    const empCondonados = [];

    for (const emp of empleados) {
        const asist = matrix[emp.id]?.[fecha];
        if (!asist) continue;
        if (asist.deuda_condonada > 0) {
            empCondonados.push({ emp, asist });
        } else if (asist.minutos_atraso > 0 || asist.minutos_salida_adelantada > 0) {
            empConDeuda.push({ emp, asist });
        }
    }

    const fmtMin = (m) => {
        if (!m || m <= 0) return '';
        const h = Math.floor(m / 60); const min = m % 60;
        return h > 0 ? `${h}h ${min}m` : `${min}m`;
    };

    let html = '';

    if (empConDeuda.length === 0 && empCondonados.length === 0) {
        html = '<div style="text-align:center;padding:40px;color:#94a3b8;"><i class="bi bi-check-circle" style="font-size:2rem;display:block;margin-bottom:10px;"></i>Sin deudas pendientes este día</div>';
    } else {
        if (empConDeuda.length > 0) {
            html += `<div style="font-size:0.65rem;font-weight:800;color:#dc2626;letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;">
                <i class="bi bi-exclamation-circle-fill me-1"></i> Con Deuda Pendiente (${empConDeuda.length})
            </div>`;
            for (const { emp, asist } of empConDeuda) {
                const badges = [];
                if (asist.minutos_atraso > 0) badges.push(`<span class="badge-estado badge-deuda">Atraso ${fmtMin(asist.minutos_atraso)}</span>`);
                if (asist.minutos_salida_adelantada > 0) badges.push(`<span class="badge-estado badge-deuda">Sal.Ant. ${fmtMin(asist.minutos_salida_adelantada)}</span>`);
                html += `
                <div class="emp-row" id="panel-emp-${emp.id}" onclick="toggleSeleccionEmpPanel(${emp.id})">
                    <input type="checkbox" class="form-check-input" id="cb-panel-${emp.id}" style="width:16px;height:16px;" onclick="event.stopPropagation();toggleSeleccionEmpPanel(${emp.id})">
                    <div style="flex:1;">
                        <div style="font-weight:600;font-size:0.8rem;color:#1e293b;">${emp.nombre_completo || emp.nombre || 'Empleado'}</div>
                        <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:3px;">${badges.join('')}</div>
                    </div>
                </div>`;
            }
        }

        if (empCondonados.length > 0) {
            html += `<div style="font-size:0.65rem;font-weight:800;color:#16a34a;letter-spacing:1px;text-transform:uppercase;margin:12px 0 6px;">
                <i class="bi bi-check-circle-fill me-1"></i> Ya Condonados (${empCondonados.length})
            </div>`;
            const tipos = { 1: 'Salida Adelantada', 2: 'Atraso', 3: 'Atraso + Salida' };
            for (const { emp, asist } of empCondonados) {
                html += `
                <div class="emp-row" id="panel-emp-${emp.id}" onclick="toggleSeleccionEmpPanel(${emp.id})">
                    <input type="checkbox" class="form-check-input" id="cb-panel-${emp.id}" style="width:16px;height:16px;" onclick="event.stopPropagation();toggleSeleccionEmpPanel(${emp.id})">
                    <div style="flex:1;">
                        <div style="font-weight:600;font-size:0.8rem;color:#1e293b;">${emp.nombre_completo || emp.nombre || 'Empleado'}</div>
                        <div style="margin-top:3px;"><span class="badge-estado badge-condonado">&#10003; ${tipos[asist.deuda_condonada] || 'Condonado'}</span></div>
                    </div>
                </div>`;
            }
        }
    }

    body.innerHTML = html;
    panel.classList.add('abierto');
    overlay.classList.add('visible');
    window._perdonazoState.seleccionados.clear();
    _actualizarInfoSeleccion();
};

/** Toggle de selección de empleado en el panel */
window.toggleSeleccionEmpPanel = function(empId) {
    const row = document.getElementById(`panel-emp-${empId}`);
    const cb = document.getElementById(`cb-panel-${empId}`);
    if (window._perdonazoState.seleccionados.has(empId)) {
        window._perdonazoState.seleccionados.delete(empId);
        row?.classList.remove('seleccionado');
        if (cb) cb.checked = false;
    } else {
        window._perdonazoState.seleccionados.add(empId);
        row?.classList.add('seleccionado');
        if (cb) cb.checked = true;
    }
    _actualizarInfoSeleccion();
};

function _actualizarInfoSeleccion() {
    const info = document.getElementById('panel-seleccion-info');
    if (!info) return;
    const n = window._perdonazoState.seleccionados.size;
    info.textContent = n === 0 ? 'Seleccione empleados arriba' : `${n} empleado(s) seleccionado(s)`;
}

/** Aplica el perdonazo para los seleccionados en el panel */
window.ejecutarPerdonazoPanelSeleccionados = async function() {
    const fecha = document.getElementById('panel-perdonazo')?.dataset.fechaActual;
    const tipo = parseInt(document.getElementById('panel-tipo-condonacion')?.value || '3', 10);
    const empIds = [...window._perdonazoState.seleccionados];

    if (empIds.length === 0) {
        Swal.fire({ toast: true, position: 'top-end', icon: 'warning', title: 'Seleccione al menos un empleado', timer: 2000, showConfirmButton: false });
        return;
    }
    if (!fecha) return;
    await window.executeCondonacionMasiva(empIds, fecha, fecha, tipo);
};

/** Revoca el perdonazo para los seleccionados en el panel */
window.revocarPerdonazoPanelSeleccionados = async function() {
    const fecha = document.getElementById('panel-perdonazo')?.dataset.fechaActual;
    const empIds = [...window._perdonazoState.seleccionados];

    if (empIds.length === 0) {
        Swal.fire({ toast: true, position: 'top-end', icon: 'warning', title: 'Seleccione al menos un empleado', timer: 2000, showConfirmButton: false });
        return;
    }
    if (!fecha) return;
    await window.executeCondonacionMasiva(empIds, fecha, fecha, 0);
};
