// contratos_ui.js - Gestión de Vencimientos de Contratos

const API_CONTRATOS = '/api/empleados/vencimientos/';
let currentEmpleadoVencimiento = null;

// --- Sorting State ---
let _vencContratosData = []; // Cached data for client-side sorting
let _vencSortKey = null;
let _vencSortDir = 1;
let _historialData = []; // Cached data for historial sorting
let _histSortKey = null;
let _histSortDir = 1;

function initContratosUI() {
    console.log("Inicializando UI de Contratos...");

    // Listener para la pestaña de contratos (Lazy Loading)
    const tabBtn = document.getElementById('contratos-tab');
    if (tabBtn) {
        tabBtn.addEventListener('shown.bs.tab', () => {
            const cont = document.getElementById('contratos-list-container');
            if (cont && (cont.children.length === 0 || cont.querySelector('.spinner-border'))) {
                loadContratosUI();
            }
        });
    }

    // Inicializar listeners del modal
    const radioRenovar = document.getElementById('radio-renovar');
    const radioIndefinido = document.getElementById('radio-indefinido');
    const radioDesactivar = document.getElementById('radio-desactivar');
    const newDateContainer = document.getElementById('new-date-container');

    if (radioRenovar) {
        radioRenovar.addEventListener('change', () => {
            newDateContainer.classList.remove('d-none');
        });
    }
    if (radioIndefinido) {
        radioIndefinido.addEventListener('change', () => {
            newDateContainer.classList.add('d-none');
        });
    }
    if (radioDesactivar) {
        radioDesactivar.addEventListener('change', () => {
            newDateContainer.classList.add('d-none');
        });
    }
}

// Ventana de vencimientos que se pide al servidor (la misma de la barra de días restantes)
const DIAS_VENTANA_CONTRATOS = 45;

async function loadContratosUI() {
    const cont = document.getElementById('contratos-list-container');
    if (!cont) return;

    cont.innerHTML = '<div class="cf-msg"><span class="spinner-border spinner-border-sm"></span> Buscando vencimientos…</div>';

    try {
        const response = await fetch(`${API_CONTRATOS}?days=${DIAS_VENTANA_CONTRATOS}`);
        if (!response.ok) throw new Error("Error al obtener contratos");

        const rawEmpleados = await response.json();
        
        // Deduplicación defensiva por id
        const seenIds = new Set();
        const empleados = [];
        for (const emp of (Array.isArray(rawEmpleados) ? rawEmpleados : [])) {
            if (emp && emp.id && !seenIds.has(emp.id)) {
                seenIds.add(emp.id);
                empleados.push(emp);
            }
        }

        if (empleados.length === 0) {
            const cnt = document.getElementById('contratos-count'); if (cnt) cnt.textContent = '0';
            cont.innerHTML = '<div class="cf-msg"><i class="bi bi-check-circle-fill text-success me-2"></i>Todo en orden. No hay contratos por vencer en los próximos ' + DIAS_VENTANA_CONTRATOS + ' días.</div>';
            return;
        }

        _vencContratosData = empleados; // Cache for sorting

        renderContratosTable(empleados);

    } catch (error) {
        console.error("Error cargando contratos:", error);
        cont.innerHTML = '<div class="cf-msg text-danger"><i class="bi bi-exclamation-triangle-fill me-2"></i>No se pudieron cargar los contratos: ' + error.message + '</div>';
    }
}

function renderContratosTable(empleados) {
    const cont = document.getElementById('contratos-list-container');
    if (!cont) return;
    const esc = (t) => String(t == null ? '' : t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const nombre = (e) => window.nombreTitulo ? window.nombreTitulo(e.nombre_completo) : e.nombre_completo;
    const dos = (n) => String(n).padStart(2, '0');
    const corta = (f) => { const p = String(f || '').split('-'); return p.length === 3 ? p[2] + '-' + p[1] : f; };
    const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
    const max = DIAS_VENTANA_CONTRATOS, min = -5;

    const sub = document.getElementById('contratos-sub');
    if (sub) sub.textContent = 'Personas activas con fecha de término en los próximos ' + max + ' días. «Gestionar» permite renovar, pasar a indefinido o no renovar.';
    const cnt = document.getElementById('contratos-count');
    if (cnt) cnt.textContent = empleados.length;

    // Grupos por urgencia, con los mismos cortes de siempre: vencido, 15 días o menos, 30 días o menos
    const filas = empleados.map((emp) => {
        const dias = emp.fecha_salida ? Math.ceil((new Date(emp.fecha_salida + 'T00:00:00') - hoy) / 86400000) : null;
        const grupo = dias === null ? 's' : dias < 0 ? 'v' : dias <= 15 ? 'c' : dias <= 30 ? 'p' : 'o';
        return { emp: emp, dias: dias, grupo: grupo };
    }).sort((x, y) => (x.dias === null ? 1e9 : x.dias) - (y.dias === null ? 1e9 : y.dias));
    const diasTxt = (d) => d === null ? 'Sin fecha de término' : d < 0 ? 'Venció hace ' + (-d) + (d === -1 ? ' día' : ' días') : d === 0 ? 'Vence hoy' : 'En ' + d + (d === 1 ? ' día' : ' días');
    const COL = { v: '#a3261c', c: '#d9534f', p: '#d48a1f', o: '#16673b', s: '#626d8a' };

    // Línea de los próximos días: cuántos contratos vencen cada día (los vencidos hace más de 5 días quedan al borde)
    const pos = (d) => ((Math.max(min, Math.min(max, d)) - min) / (max - min) * 100).toFixed(2) + '%';
    const zona = (a, b, color) => '<div class="cf-zona" style="left:' + pos(a) + ';width:calc(' + pos(b) + ' - ' + pos(a) + ');background:' + color + '"></div>';
    const porDia = {};
    filas.filter((f) => f.dias !== null).forEach((f) => { const k = Math.max(min, f.dias); (porDia[k] = porDia[k] || []).push(f); });
    const nomDia = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'][hoy.getDay()];
    let html = '<section class="cf-linea"><div class="cf-lt">Cuándo vence cada contrato</div>'
        + '<div class="cf-ls">Desde hoy, ' + nomDia + ' ' + dos(hoy.getDate()) + '-' + dos(hoy.getMonth() + 1) + ', hasta ' + max + ' días más</div><div class="cf-eje">'
        + zona(min, 0, '#fdecea') + zona(0, 15, '#fbe3e1') + zona(15, 30, '#fdf1e2') + zona(30, max, '#e7f4ec')
        + '<div class="cf-hoy" style="left:' + pos(0) + '"><span>Hoy</span></div>';
    // En pantallas angostas los días muy cercanos se juntan en una sola marca para que no se monten
    const juntar = cont.clientWidth < 600 ? 4 : 0;
    const grupos = [];
    Object.keys(porDia).map(Number).sort((x, y) => x - y).forEach((k) => {
        const ult = grupos[grupos.length - 1];
        if (ult && k - ult.desde <= juntar) ult.fs = ult.fs.concat(porDia[k]);
        else grupos.push({ desde: k, fs: porDia[k] });
    });
    grupos.forEach((gr) => {
        const fs = gr.fs;
        html += '<div class="cf-marca" style="left:' + pos(gr.desde) + '" title="' + esc(fs.map((f) => nombre(f.emp)).join(', ')) + '">'
            + '<b style="background:' + COL[fs[0].grupo] + '">' + fs.length + '</b><small>' + corta(fs[0].emp.fecha_salida) + '</small></div>';
    });
    html += '<div class="cf-reglas"><span style="left:' + pos(7.5) + '">15 días o menos</span><span style="left:' + pos(22.5) + '">16 a 30 días</span>'
        + '<span style="left:' + pos((30 + max) / 2) + '">31 a ' + max + ' días</span></div></div></section>';

    const G = [['v', 'Vencidos'], ['c', 'Vencen en 15 días o menos'], ['p', 'Vencen en 16 a 30 días'], ['o', 'Vencen en 31 a ' + max + ' días'], ['s', 'Temporales sin fecha de término']];
    G.forEach((g) => {
        const k = g[0];
        const fs = filas.filter((f) => f.grupo === k);
        if (!fs.length) return;
        html += '<div class="cf-gh"><i style="background:' + COL[k] + '"></i>' + g[1] + ' <span>· ' + fs.length + '</span></div><div class="cf-lista">';
        fs.forEach((f) => {
            const e = f.emp;
            const legal = e.tipo_contrato === 'Temporal' && e.cant_contratos >= 2;
            const datos = btoa(unescape(encodeURIComponent(JSON.stringify(e))));
            html += '<div class="cf-fila">'
                + '<div class="cf-fecha"><b>' + (e.fecha_salida ? window.formatFechaDDMMYYYY(e.fecha_salida) : 'Sin fecha') + '</b><small class="g-' + k + '">' + diasTxt(f.dias) + '</small></div>'
                + '<div class="cf-quien"><span class="vn-av vn-av-sm td-t' + ((Math.abs(parseInt(e.id, 10) || 0) % 6) + 1) + '" aria-hidden="true">' + esc(window.inicialesDe ? window.inicialesDe(e.nombre_completo) : '') + '</span>'
                + '<div><div class="cf-n">' + esc(nombre(e)) + '</div><div class="cf-s">' + esc(e.rut_formateado || '') + '</div></div></div>'
                + '<div class="cf-puesto"><div>' + esc(e.cargo || 'Sin cargo') + '</div><div class="cf-s">' + esc(e.area || 'Sin área') + '</div></div>'
                + '<div class="cf-contrato"><div>Contrato N° ' + (e.cant_contratos || 1) + (e.tipo_contrato ? ' · ' + esc(e.tipo_contrato) : '') + '</div>'
                + (legal ? '<span class="cf-legal"><i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i>2.º contrato a plazo</span>' : '') + '</div>'
                + '<button type="button" class="cf-ges btn-gestionar-venc" data-emp="' + datos + '"><i class="bi bi-sliders" aria-hidden="true"></i>Gestionar</button>'
                + '</div>';
        });
        html += '</div>';
    });
    cont.innerHTML = html;
    cont.querySelectorAll('.btn-gestionar-venc').forEach((btn) => btn.addEventListener('click', (ev) => {
        const empObj = JSON.parse(decodeURIComponent(escape(atob(ev.currentTarget.getAttribute('data-emp')))));
        openVencimientoModal(empObj);
    }));
}

// --- Vencimientos Sorting ---
window.sortContratosVenc = function(key) {
    if (_vencSortKey === key) {
        _vencSortDir *= -1;
    } else {
        _vencSortKey = key;
        _vencSortDir = 1;
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    _vencContratosData.sort((a, b) => {
        let valA, valB;
        if (key === 'dias_restantes') {
            valA = a.fecha_salida ? Math.ceil((new Date(a.fecha_salida + 'T00:00:00') - today) / 86400000) : 9999;
            valB = b.fecha_salida ? Math.ceil((new Date(b.fecha_salida + 'T00:00:00') - today) / 86400000) : 9999;
        } else if (key === 'estado') {
            const getState = (emp) => {
                if (!emp.fecha_salida && emp.tipo_contrato === 'Temporal') return 0;
                const d = Math.ceil((new Date(emp.fecha_salida + 'T00:00:00') - today) / 86400000);
                if (d < 0) return 3;
                if (d <= 15) return 1;
                if (d <= 30) return 2;
                return 4;
            };
            valA = getState(a);
            valB = getState(b);
        } else {
            valA = (a[key] || '').toString().toLowerCase();
            valB = (b[key] || '').toString().toLowerCase();
        }
        if (valA < valB) return -1 * _vencSortDir;
        if (valA > valB) return 1 * _vencSortDir;
        return 0;
    });

    renderContratosTable(_vencContratosData);
    _updateVencSortIcons();
};

function _updateVencSortIcons() {
    const cols = ['nombre_completo', 'cant_contratos', 'cargo', 'area', 'fecha_salida', 'dias_restantes', 'estado'];
    cols.forEach(c => {
        const icon = document.getElementById(`sort-icon-venc-${c}`);
        if (!icon) return;
        const th = icon.closest('th');
        if (_vencSortKey === c) {
            icon.className = _vencSortDir === 1
                ? 'bi bi-sort-alpha-down sort-icon text-primary'
                : 'bi bi-sort-alpha-up-alt sort-icon text-primary';
            if (th) th.classList.add('sort-active');
        } else {
            icon.className = 'bi bi-arrow-down-up sort-icon text-muted';
            if (th) th.classList.remove('sort-active');
        }
    });
}

function openVencimientoModal(empleado) {
    currentEmpleadoVencimiento = empleado;

    document.getElementById('venc-emp-nombre').innerText = empleado.nombre_completo;
    document.getElementById('venc-emp-cargo-area').innerText = `${empleado.cargo || 'Sin Cargo'} | ${empleado.area || 'Sin Área'}`;
    document.getElementById('venc-fecha').innerText = empleado.fecha_salida || 'Sin definir';

    const alertaLegal = document.getElementById('venc-alerta-legal');
    const numContratoSpan = document.getElementById('venc-num-contrato');

    if (empleado.cant_contratos >= 2) {
        alertaLegal.classList.remove('d-none');
        numContratoSpan.innerText = `${empleado.cant_contratos}°`;
    } else {
        alertaLegal.classList.add('d-none');
    }

    // Reset radio y fecha
    document.getElementById('radio-renovar').checked = true;
    document.getElementById('new-date-container').classList.remove('d-none');
    document.getElementById('venc-nueva-fecha').value = '';

    let modalEl = document.getElementById('modal-gestion-vencimiento');
    let modal = bootstrap.Modal.getInstance(modalEl);
    if (!modal) {
        modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    }
    modal.show();
}

function closeVencimientoModal() {
    const modalEl = document.getElementById('modal-gestion-vencimiento');
    if (modalEl && modalEl.contains(document.activeElement)) {
        document.activeElement.blur();
    }
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) {
        modal.hide();
        // Limpiar el backdrop de Bootstrap manualmente si se queda pegado
        const backdrop = document.querySelector('.modal-backdrop');
        if (backdrop) backdrop.remove();
        document.body.classList.remove('modal-open');
        document.body.style.overflow = '';
        document.body.style.paddingRight = '';
    }
}

async function confirmProcesarVencimiento() {
    if (!currentEmpleadoVencimiento) return;

    const action = document.querySelector('input[name="venc-action"]:checked').value;
    const nuevaFecha = document.getElementById('venc-nueva-fecha').value;

    if (action === 'renovar' && !nuevaFecha) {
        Avisos.falta('Falta la nueva fecha de término para renovar.');
        return;
    }

    // Mapeo detallado para confirmación humana
    const nombre = window.nombreTitulo(currentEmpleadoVencimiento.nombre_completo);
    const fechaSalida = currentEmpleadoVencimiento.fecha_salida || "hoy";
    let pregunta = '', items = [], boton = 'Confirmar', peligro = false;

    if (action === 'renovar') {
        pregunta = `¿Renovar el contrato de ${nombre}?`;
        items = [`Queda vigente hasta el ${window.formatFechaDDMMYYYY(nuevaFecha)}.`];
        boton = 'Renovar contrato';
    } else if (action === 'indefinido') {
        pregunta = `¿Pasar a ${nombre} a contrato indefinido?`;
        items = ['La persona queda de planta, sin fecha de término.'];
        boton = 'Pasar a indefinido';
    } else if (action === 'desactivar') {
        // Determinar si es programada o inmediata basándose en la fecha
        const hoy = new Date();
        hoy.setHours(0, 0, 0, 0);
        const fVenc = new Date(fechaSalida + 'T00:00:00');

        if (fVenc > hoy) {
            pregunta = `¿Programar la baja de ${nombre}?`;
            items = [`El contrato termina y la persona queda inactiva el ${window.formatFechaDDMMYYYY(fechaSalida)}.`];
        } else {
            pregunta = `¿Dar de baja hoy a ${nombre}?`;
            items = ['La persona queda inactiva desde hoy.'];
        }
        boton = 'Registrar baja';
        peligro = true;
    } else {
        pregunta = `¿Confirmar «${action}» para ${nombre}?`;
    }

    if (!await uiConfirm(pregunta, { items, confirmText: boton, danger: peligro })) return;

    try {
        const response = await fetch(`/api/empleados/${currentEmpleadoVencimiento.id}/procesar-vencimiento/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                accion: action,
                nueva_fecha: nuevaFecha || null
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || "Error al procesar acción");
        }

        // 1. Cerrar primero el modal de gestión
        closeVencimientoModal();

        // 2. Pequeño delay para dejar que Bootstrap termine la animación y el cleanup
        setTimeout(async () => {
            // 3. Notificación (Toast)
            if (typeof showNotification === 'function') {
                showNotification("Listo. Contrato actualizado.", "success");
            } else if (typeof showToast === 'function') {
                showToast("Listo. Contrato actualizado.", "success");
            }

            // 4. Refrescar datos en segundo plano
            loadContratosUI();
            if (typeof refreshAlerts === 'function') {
                refreshAlerts();
            } else if (typeof checkContractAlerts === 'function') {
                checkContractAlerts();
            }
            if (typeof loadEmpleados === 'function') loadEmpleados();
        }, 300);

    } catch (error) {
        console.error("Error:", error);
        Avisos.error("No se pudo actualizar el contrato. " + error.message);
    }
}
// ==========================================
// HISTORIAL DE BAJAS
// ==========================================

async function loadHistorialBajas() {
    const monthSelect = document.getElementById('historial-month');
    const yearSelect = document.getElementById('historial-year');

    // Set default month if not set
    if (!monthSelect.value) {
        monthSelect.value = new Date().getMonth() + 1;
    }

    const month = monthSelect.value;
    const year = yearSelect.value;

    const container = document.getElementById('historial-bajas-container');
    container.innerHTML = `
        <div class="text-center py-5">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Cargando...</span>
            </div>
            <p class="mt-2 text-muted">Consultando historial...</p>
        </div>
    `;

    try {
        const response = await fetch(`${API_BASE_URL}/empleados/historial-bajas/?month=${month}&year=${year}`);
        if (!response.ok) throw new Error('Error al cargar historial');

        const empleados = await response.json();
        renderHistorialTable(empleados);

    } catch (error) {
        console.error("Error loading historial:", error);
        container.innerHTML = `
            <div class="alert alert-danger">
                Error al cargar el historial. Intente nuevamente.
            </div>
        `;
    }
}

function renderHistorialTable(empleados) {
    const container = document.getElementById('historial-bajas-container');

    if (!empleados || empleados.length === 0) {
        container.innerHTML = `
            <div class="emp-empty-state">
                <i class="bi bi-inbox empty-icon"></i>
                <h6>Sin resultados</h6>
                <p>No se encontraron bajas en este periodo.</p>
            </div>
        `;
        return;
    }

    _historialData = empleados; // Cache for sorting

    let html = `
        <div class="table-container">
            <table class="data-table" id="tabla-historial-bajas">
                <thead>
                    <tr>
                        <th class="sortable-header" onclick="sortHistorialBajas('nombre_completo')" title="Ordenar">Empleado <i id="sort-icon-hist-nombre_completo" class="bi bi-arrow-down-up sort-icon text-muted"></i></th>
                        <th class="sortable-header" onclick="sortHistorialBajas('cargo')" title="Ordenar">Cargo <i id="sort-icon-hist-cargo" class="bi bi-arrow-down-up sort-icon text-muted"></i></th>
                        <th class="sortable-header" onclick="sortHistorialBajas('fecha_salida')" title="Ordenar">Fecha Baja <i id="sort-icon-hist-fecha_salida" class="bi bi-arrow-down-up sort-icon text-muted"></i></th>
                        <th class="sortable-header" onclick="sortHistorialBajas('estado_termino')" title="Ordenar">Estado <i id="sort-icon-hist-estado_termino" class="bi bi-arrow-down-up sort-icon text-muted"></i></th>
                    </tr>
                </thead>
                <tbody>
    `;

    empleados.forEach((emp, idx) => {
        const rutFormatted = emp.rut;

        // Estado pill
        const isProgramado = emp.estado_termino === 'PROGRAMADO';
        const pillClass = isProgramado ? 'status-pill-info' : 'status-pill-muted';
        const pillDotColor = isProgramado ? '#0ea5e9' : '#94a3b8';
        const pillIcon = isProgramado ? '<i class="bi bi-calendar2-check me-1"></i>' : '<i class="bi bi-flag-fill me-1"></i>';

        html += `
            <tr class="fade-in-row" style="animation-delay: ${idx * 0.03}s;">
                <td>
                    <div class="fw-bold" style="font-size: 0.85rem;">${emp.nombre_completo}</div>
                    <div class="text-muted" style="font-size: 0.75rem;">${rutFormatted}</div>
                </td>
                <td><div class="small">${emp.cargo || 'Sin Cargo'}</div></td>
                <td class="fw-bold" style="font-size: 0.85rem;">
                    ${formatDate(emp.fecha_salida)}
                </td>
                <td>
                    <span class="status-pill ${pillClass}">
                        <span class="pill-dot" style="background:${pillDotColor};"></span>
                        ${pillIcon}${emp.estado_termino}
                    </span>
                </td>
            </tr>
        `;
    });

    html += `</tbody></table></div>`;
    container.innerHTML = html;
}

// --- Historial Sorting ---
window.sortHistorialBajas = function(key) {
    if (_histSortKey === key) {
        _histSortDir *= -1;
    } else {
        _histSortKey = key;
        _histSortDir = 1;
    }

    _historialData.sort((a, b) => {
        let valA = (a[key] || '').toString().toLowerCase();
        let valB = (b[key] || '').toString().toLowerCase();
        if (valA < valB) return -1 * _histSortDir;
        if (valA > valB) return 1 * _histSortDir;
        return 0;
    });

    renderHistorialTable(_historialData);
    _updateHistSortIcons();
};

function _updateHistSortIcons() {
    const cols = ['nombre_completo', 'cargo', 'fecha_salida', 'estado_termino'];
    cols.forEach(c => {
        const icon = document.getElementById(`sort-icon-hist-${c}`);
        if (!icon) return;
        const th = icon.closest('th');
        if (_histSortKey === c) {
            icon.className = _histSortDir === 1
                ? 'bi bi-sort-alpha-down sort-icon text-primary'
                : 'bi bi-sort-alpha-up-alt sort-icon text-primary';
            if (th) th.classList.add('sort-active');
        } else {
            icon.className = 'bi bi-arrow-down-up sort-icon text-muted';
            if (th) th.classList.remove('sort-active');
        }
    });
}

// Inicializar select de mes al cargar
document.addEventListener('DOMContentLoaded', () => {
    const monthSelect = document.getElementById('historial-month');
    if (monthSelect) {
        monthSelect.value = new Date().getMonth() + 1;
    }
});

function formatDate(dateString) {
    return window.formatFechaDDMMYYYY(dateString) || '-';
}
