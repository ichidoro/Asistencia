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
                    <label for="panel-tipo-condonacion" style="font-size:0.75rem;font-weight:700;color:#374151;display:block;margin-bottom:5px;">¿Qué deuda condonar?</label>
                    <select id="panel-tipo-condonacion" onchange="renderizarListaPerdonazo()" style="width:100%;padding:6px 10px;border:1px solid #d1fae5;border-radius:8px;font-size:0.8rem;background:#f0fdf4;color:#047857;font-weight:600;">
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

    // ── Actualizar visualmente SOLO el wrapper del switch, sin destruir el toolbar ──
    const wrapper = document.getElementById('perdonazo-switch-wrapper');
    if (wrapper) {
        wrapper.style.background = activo ? '#f0fdf4' : '#fff';
        wrapper.style.borderColor = activo ? '#86efac' : '#e2e8f0';
    }
    const lbl = document.querySelector('label[for="perdonazo-switch"]');
    if (lbl) {
        lbl.style.color = activo ? '#047857' : '#64748b';
        const ico = lbl.querySelector('i.bi-gift-fill');
        if (ico) ico.style.color = activo ? '#10b981' : '#64748b';
    }

    // ── Re-renderizar SOLO el cuerpo de la grilla para agregar/quitar los click en encabezados ──
    if (typeof window.loadMarcacionesData === 'function') {
        // Solo si ya hay datos cargados (evitar carga vacía en el primer toggle)
        if (window.stateMarcacionesApp.data) {
            window.loadMarcacionesData();
        }
    }

    if (activo) {
        Swal.fire({
            icon: 'info',
            title: '🎁 Modo Perdonazos activo',
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
    if (!panel) return;

    // Título humanizado
    const fechaDisplay = new Date(fecha + 'T12:00:00').toLocaleDateString('es-CL', {
        weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
    });
    titulo.textContent = fechaDisplay;
    panel.dataset.fechaActual = fecha;

    panel.classList.add('abierto');
    overlay.classList.add('visible');
    window._perdonazoState.seleccionados.clear();
    window.renderizarListaPerdonazo();
};

/** Renderiza la lista dividida en Atrasos (arriba) y Salidas Adelantadas (abajo) con filtros reactivos */
window.renderizarListaPerdonazo = function() {
    const panel = document.getElementById('panel-perdonazo');
    if (!panel) return;
    const fecha = panel.dataset.fechaActual;
    if (!fecha) return;

    const body = document.getElementById('panel-perdonazo-body');
    const tipo = parseInt(document.getElementById('panel-tipo-condonacion')?.value || '3', 10);

    const matrix = window.stateMarcacionesApp.data?.matrix;
    const empleados = window.stateMarcacionesApp.data?.empleados || [];

    if (!matrix) {
        body.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8;">No hay datos cargados</div>';
        return;
    }

    // Formateador de minutos
    const fmtMin = (m) => {
        if (!m || m <= 0) return '';
        const h = Math.floor(m / 60); const min = m % 60;
        return h > 0 ? `${h}h ${min}m` : `${min}m`;
    };

    // Clasificar
    const atrasosPendientes = [];
    const atrasosCondonados = [];
    const salidasPendientes = [];
    const salidasCondonadas = [];

    for (const emp of empleados) {
        const asist = matrix[emp.id]?.[fecha];
        if (!asist) continue;

        // Atrasos
        if (asist.deuda_condonada === 2 || asist.deuda_condonada === 3) {
            atrasosCondonados.push({ emp, asist });
        } else if (asist.minutos_atraso > 0) {
            atrasosPendientes.push({ emp, asist });
        }

        // Salidas Adelantadas
        if (asist.deuda_condonada === 1 || asist.deuda_condonada === 3) {
            salidasCondonadas.push({ emp, asist });
        } else if (asist.minutos_salida_adelantada > 0) {
            salidasPendientes.push({ emp, asist });
        }
    }

    let html = '';

    // Botones de selección rápida al principio
    html += `
    <div style="display:flex; justify-content:space-between; align-items:center; padding: 4px 10px; margin-bottom: 10px; font-size:0.8rem; border-bottom: 1px solid #f1f5f9; flex-shrink:0;">
        <span style="color:#64748b; font-weight:600;">Selección rápida:</span>
        <div style="display:flex; gap:12px;">
            <button onclick="seleccionarTodosPanel(true)" style="background:none; border:none; color:#10b981; font-weight:700; cursor:pointer; font-size:0.75rem; padding: 2px 4px;">Seleccionar todos</button>
            <button onclick="seleccionarTodosPanel(false)" style="background:none; border:none; color:#64748b; font-weight:700; cursor:pointer; font-size:0.75rem; padding: 2px 4px;">Deseleccionar todos</button>
        </div>
    </div>
    `;

    const hasAtrasos = atrasosPendientes.length > 0 || atrasosCondonados.length > 0;
    const hasSalidas = salidasPendientes.length > 0 || salidasCondonadas.length > 0;

    if ((tipo === 2 && !hasAtrasos) || (tipo === 1 && !hasSalidas) || (tipo === 3 && !hasAtrasos && !hasSalidas)) {
        html += '<div style="text-align:center;padding:40px;color:#94a3b8;"><i class="bi bi-check-circle" style="font-size:2rem;display:block;margin-bottom:10px;"></i>Sin incidencias ni deudas del tipo seleccionado</div>';
        body.innerHTML = html;
        return;
    }

    // Renderizar Atrasos (si tipo es 2 o 3)
    if (tipo === 2 || tipo === 3) {
        if (hasAtrasos) {
            html += `<div style="font-size:0.7rem;font-weight:800;color:#374151;background:#f1f5f9;padding:6px 10px;border-radius:6px;letter-spacing:1px;text-transform:uppercase;margin:10px 0 6px;display:flex;justify-content:space-between;align-items:center;">
                <span>⏳ ATRASOS</span>
                <span style="font-size:0.6rem;background:#e2e8f0;padding:2px 6px;border-radius:999px;color:#475569;">Pendientes: ${atrasosPendientes.length}</span>
            </div>`;

            // Pendientes
            for (const { emp, asist } of atrasosPendientes) {
                const isSel = window._perdonazoState.seleccionados.has(emp.id);
                html += `
                <div class="emp-row panel-emp-${emp.id} ${isSel ? 'seleccionado' : ''}" onclick="toggleSeleccionEmpPanel(${emp.id})">
                    <input type="checkbox" class="form-check-input cb-panel-${emp.id}" ${isSel ? 'checked' : ''} style="width:16px;height:16px;" onclick="event.stopPropagation();toggleSeleccionEmpPanel(${emp.id})">
                    <div style="flex:1;">
                        <div style="font-weight:600;font-size:0.8rem;color:#1e293b;">${emp.nombre_completo || emp.nombre || 'Empleado'}</div>
                        <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:3px;">
                            <span class="badge-estado badge-deuda">Atraso ${fmtMin(asist.minutos_atraso)}</span>
                        </div>
                    </div>
                </div>`;
            }

            // Condonados
            if (atrasosCondonados.length > 0) {
                html += `<div style="font-size:0.65rem;font-weight:700;color:#16a34a;margin:6px 0 4px;padding-left:10px;">Atrasos Condonados (${atrasosCondonados.length})</div>`;
                for (const { emp, asist } of atrasosCondonados) {
                    const isSel = window._perdonazoState.seleccionados.has(emp.id);
                    html += `
                    <div class="emp-row panel-emp-${emp.id} ${isSel ? 'seleccionado' : ''}" onclick="toggleSeleccionEmpPanel(${emp.id})">
                        <input type="checkbox" class="form-check-input cb-panel-${emp.id}" ${isSel ? 'checked' : ''} style="width:16px;height:16px;" onclick="event.stopPropagation();toggleSeleccionEmpPanel(${emp.id})">
                        <div style="flex:1;">
                            <div style="font-weight:600;font-size:0.8rem;color:#1e293b;">${emp.nombre_completo || emp.nombre || 'Empleado'}</div>
                            <div style="margin-top:3px;">
                                <span class="badge-estado badge-condonado">&#10003; Atraso Condonado</span>
                            </div>
                        </div>
                    </div>`;
                }
            }
        } else if (tipo === 3) {
            html += `<div style="font-size:0.7rem;font-weight:800;color:#94a3b8;padding:6px 10px;letter-spacing:1px;text-transform:uppercase;">⏳ Sin atrasos este día</div>`;
        }
    }

    // Renderizar Salidas Adelantadas (si tipo es 1 o 3)
    if (tipo === 1 || tipo === 3) {
        if (hasSalidas) {
            html += `<div style="font-size:0.7rem;font-weight:800;color:#374151;background:#f1f5f9;padding:6px 10px;border-radius:6px;letter-spacing:1px;text-transform:uppercase;margin:18px 0 6px;display:flex;justify-content:space-between;align-items:center;">
                <span>🚶 SALIDAS ADELANTADAS</span>
                <span style="font-size:0.6rem;background:#e2e8f0;padding:2px 6px;border-radius:999px;color:#475569;">Pendientes: ${salidasPendientes.length}</span>
            </div>`;

            // Pendientes
            for (const { emp, asist } of salidasPendientes) {
                const isSel = window._perdonazoState.seleccionados.has(emp.id);
                html += `
                <div class="emp-row panel-emp-${emp.id} ${isSel ? 'seleccionado' : ''}" onclick="toggleSeleccionEmpPanel(${emp.id})">
                    <input type="checkbox" class="form-check-input cb-panel-${emp.id}" ${isSel ? 'checked' : ''} style="width:16px;height:16px;" onclick="event.stopPropagation();toggleSeleccionEmpPanel(${emp.id})">
                    <div style="flex:1;">
                        <div style="font-weight:600;font-size:0.8rem;color:#1e293b;">${emp.nombre_completo || emp.nombre || 'Empleado'}</div>
                        <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:3px;">
                            <span class="badge-estado badge-deuda">Sal.Ant. ${fmtMin(asist.minutos_salida_adelantada)}</span>
                        </div>
                    </div>
                </div>`;
            }

            // Condonados
            if (salidasCondonadas.length > 0) {
                html += `<div style="font-size:0.65rem;font-weight:700;color:#16a34a;margin:6px 0 4px;padding-left:10px;">Salidas Condonadas (${salidasCondonadas.length})</div>`;
                for (const { emp, asist } of salidasCondonadas) {
                    const isSel = window._perdonazoState.seleccionados.has(emp.id);
                    html += `
                    <div class="emp-row panel-emp-${emp.id} ${isSel ? 'seleccionado' : ''}" onclick="toggleSeleccionEmpPanel(${emp.id})">
                        <input type="checkbox" class="form-check-input cb-panel-${emp.id}" ${isSel ? 'checked' : ''} style="width:16px;height:16px;" onclick="event.stopPropagation();toggleSeleccionEmpPanel(${emp.id})">
                        <div style="flex:1;">
                            <div style="font-weight:600;font-size:0.8rem;color:#1e293b;">${emp.nombre_completo || emp.nombre || 'Empleado'}</div>
                            <div style="margin-top:3px;">
                                <span class="badge-estado badge-condonado">&#10003; Salida Condonada</span>
                            </div>
                        </div>
                    </div>`;
                }
            }
        } else if (tipo === 3) {
            html += `<div style="font-size:0.7rem;font-weight:800;color:#94a3b8;padding:6px 10px;letter-spacing:1px;text-transform:uppercase;margin-top:10px;">🚶 Sin salidas adelantadas este día</div>`;
        }
    }

    body.innerHTML = html;
    _actualizarInfoSeleccion();
};

/** Toggle de selección de empleado en el panel (soporta duplicados en diferentes secciones) */
window.toggleSeleccionEmpPanel = function(empId) {
    const rows = document.querySelectorAll(`.panel-emp-${empId}`);
    const cbs = document.querySelectorAll(`.cb-panel-${empId}`);
    if (window._perdonazoState.seleccionados.has(empId)) {
        window._perdonazoState.seleccionados.delete(empId);
        rows.forEach(r => r.classList.remove('seleccionado'));
        cbs.forEach(c => c.checked = false);
    } else {
        window._perdonazoState.seleccionados.add(empId);
        rows.forEach(r => r.classList.add('seleccionado'));
        cbs.forEach(c => c.checked = true);
    }
    _actualizarInfoSeleccion();
};

/** Selecciona o deselecciona todos los empleados visibles actualmente */
window.seleccionarTodosPanel = function(status) {
    const checkboxes = document.querySelectorAll('#panel-perdonazo-body .emp-row input[type="checkbox"]');
    for (const cb of checkboxes) {
        const classList = Array.from(cb.classList);
        const empClass = classList.find(c => c.startsWith('cb-panel-'));
        if (empClass) {
            const empId = parseInt(empClass.replace('cb-panel-', ''), 10);
            if (status) {
                window._perdonazoState.seleccionados.add(empId);
            } else {
                window._perdonazoState.seleccionados.delete(empId);
            }
        }
    }
    
    // Sincronizar todos los elementos visuales
    const allRows = document.querySelectorAll('#panel-perdonazo-body .emp-row');
    allRows.forEach(row => {
        const classList = Array.from(row.classList);
        const empClass = classList.find(c => c.startsWith('panel-emp-'));
        if (empClass) {
            const empId = parseInt(empClass.replace('panel-emp-', ''), 10);
            const isSel = window._perdonazoState.seleccionados.has(empId);
            row.classList.toggle('seleccionado', isSel);
            const cb = row.querySelector('input[type="checkbox"]');
            if (cb) cb.checked = isSel;
        }
    });
    
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

    // Obtener los botones para colocar spinner y deshabilitar
    const btnAplicar = document.querySelector('#panel-perdonazo button[onclick="ejecutarPerdonazoPanelSeleccionados()"]');
    const btnRevocar = document.querySelector('#panel-perdonazo button[onclick="revocarPerdonazoPanelSeleccionados()"]');
    let originalHTML = '';
    if (btnAplicar) {
        originalHTML = btnAplicar.innerHTML;
        btnAplicar.disabled = true;
        if (btnRevocar) btnRevocar.disabled = true;
        btnAplicar.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Aplicando...';
    }

    try {
        await window.executeCondonacionMasiva(empIds, fecha, fecha, tipo);
    } catch (err) {
        console.error("Error al aplicar perdonazo masivo:", err);
    } finally {
        if (btnAplicar) {
            btnAplicar.disabled = false;
            btnAplicar.innerHTML = originalHTML;
        }
        if (btnRevocar) btnRevocar.disabled = false;
    }
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

    // Obtener los botones para colocar spinner y deshabilitar
    const btnAplicar = document.querySelector('#panel-perdonazo button[onclick="ejecutarPerdonazoPanelSeleccionados()"]');
    const btnRevocar = document.querySelector('#panel-perdonazo button[onclick="revocarPerdonazoPanelSeleccionados()"]');
    let originalHTML = '';
    if (btnRevocar) {
        originalHTML = btnRevocar.innerHTML;
        btnRevocar.disabled = true;
        if (btnAplicar) btnAplicar.disabled = true;
        btnRevocar.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>...';
    }

    try {
        await window.executeCondonacionMasiva(empIds, fecha, fecha, 0);
    } catch (err) {
        console.error("Error al revocar perdonazo masivo:", err);
    } finally {
        if (btnRevocar) {
            btnRevocar.disabled = false;
            btnRevocar.innerHTML = originalHTML;
        }
        if (btnAplicar) btnAplicar.disabled = false;
    }
};
