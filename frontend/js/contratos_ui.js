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
            const tbody = document.getElementById('tabla-contratos');
            if (tbody && (tbody.children.length === 0 || tbody.querySelector('.spinner-border'))) {
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

async function loadContratosUI() {
    const tbody = document.getElementById('tabla-contratos');
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4"><span class="spinner-border spinner-border-sm"></span> Buscando vencimientos...</td></tr>`;

    try {
        const response = await fetch(`${API_CONTRATOS}?days=45`);
        if (!response.ok) throw new Error("Error al obtener contratos");

        const empleados = await response.json();

        if (empleados.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted"><i class="bi bi-check-circle-fill text-success me-2"></i>Todo en orden. No hay contratos por vencer en los próximos 45 días.</td></tr>`;
            return;
        }

        _vencContratosData = empleados; // Cache for sorting

        renderContratosTable(empleados);

    } catch (error) {
        console.error("Error cargando contratos:", error);
        tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-danger"><i class="bi bi-exclamation-triangle-fill me-2"></i>Error al cargar datos: ${error.message}</td></tr>`;
    }
}

function renderContratosTable(empleados) {
    const tbody = document.getElementById('tabla-contratos');
    tbody.innerHTML = '';

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    empleados.forEach((emp, idx) => {
        let pillClass = 'status-pill-success';
        let pillDotColor = '#10b981';
        let badgeText = 'Vigente';
        let rowClass = 'fade-in-row';
        let diffDaysText = '-';
        let fechaFmt = 'Sin fecha';
        let diffDaysNumeric = 999;

        if (emp.fecha_salida) {
            const fechaFin = new Date(emp.fecha_salida + 'T00:00:00');
            diffDaysNumeric = Math.ceil((fechaFin - today) / (1000 * 60 * 60 * 24));

            fechaFmt = fechaFin.toLocaleDateString('es-CL', { day: '2-digit', month: 'short', year: 'numeric' });
            diffDaysText = `${diffDaysNumeric} días`;

            if (diffDaysNumeric < 0) {
                pillClass = 'status-pill-muted';
                pillDotColor = '#94a3b8';
                badgeText = 'Vencido';
                rowClass += ' row-urgency-expired';
            } else if (diffDaysNumeric <= 15) {
                pillClass = 'status-pill-critical';
                pillDotColor = '#ef4444';
                badgeText = 'Crítico';
                rowClass += ' row-urgency-critical';
            } else if (diffDaysNumeric <= 30) {
                pillClass = 'status-pill-warning';
                pillDotColor = '#f59e0b';
                badgeText = 'Próximo';
                rowClass += ' row-urgency-warning';
            }
        } else if (emp.tipo_contrato === 'Temporal') {
            pillClass = 'status-pill-info';
            pillDotColor = '#0ea5e9';
            badgeText = 'Sin Fecha';
            rowClass += ' row-urgency-info';
            fechaFmt = '<span class="text-danger fw-bold" style="font-size:0.8rem;">Dato Faltante</span>';
            diffDaysText = 'N/A';
        }

        // Detectar alerta legal (segundo contrato)
        const isSecondContract = emp.tipo_contrato === 'Temporal' && emp.cant_contratos >= 2;
        const legalAlertIcon = isSecondContract ? `<span class="text-danger ms-1" title="Alerta Legal: 2° Contrato"><i class="bi bi-exclamation-triangle-fill"></i></span>` : '';

        let tr = document.createElement('tr');
        tr.className = rowClass;
        tr.style.animationDelay = `${idx * 0.03}s`;

        // Data Base64 para evitar errores de escape
        const empData = btoa(unescape(encodeURIComponent(JSON.stringify(emp))));

        tr.innerHTML = `
            <td>
                <div class="fw-bold" style="font-size: 0.85rem;">${emp.nombre_completo}</div>
                <div class="text-muted" style="font-size: 0.72rem;">${emp.rut_formateado}</div>
            </td>
            <td class="text-center">
                <span class="status-pill status-pill-muted">N° ${emp.cant_contratos || 1}</span>
                ${legalAlertIcon}
            </td>
            <td><div class="small">${emp.cargo || '-'}</div></td>
            <td>${emp.area ? `<span class="area-badge ${typeof getAreaBadgeClass === 'function' ? getAreaBadgeClass(emp.area) : 'area-badge-default'}">${emp.area}</span>` : '<span class="text-muted small">Sin Área</span>'}</td>
            <td><div class="small">${fechaFmt}</div></td>
            <td class="fw-bold ${diffDaysNumeric <= 15 ? 'text-danger' : (diffDaysNumeric <= 30 ? 'text-warning' : 'text-success')}">
                ${diffDaysText}
            </td>
            <td><span class="status-pill ${pillClass}"><span class="pill-dot" style="background:${pillDotColor};"></span>${badgeText}</span></td>
            <td>
                <button class="btn-action-modern btn-action-primary btn-gestionar-venc" data-emp="${empData}">
                    <i class="bi bi-gear-fill"></i> Gestionar
                </button>
            </td>
        `;

        tr.querySelector('.btn-gestionar-venc').addEventListener('click', (e) => {
            const dataBase64 = e.currentTarget.getAttribute('data-emp');
            const empObj = JSON.parse(decodeURIComponent(escape(atob(dataBase64))));
            openVencimientoModal(empObj);
        });

        tbody.appendChild(tr);
    });
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
        alert("Para renovar debe ingresar la nueva fecha de término.");
        return;
    }

    // Mapeo detallado para confirmación humana
    let confirmMsg = "";
    const nombre = currentEmpleadoVencimiento.nombre_completo;
    const fechaSalida = currentEmpleadoVencimiento.fecha_salida || "hoy";

    if (action === 'renovar') {
        const fNueva = nuevaFecha.split('-').reverse().join('/');
        confirmMsg = `¿Confirmar RENOVACIÓN de contrato para ${nombre} hasta el ${fNueva}?`;
    } else if (action === 'indefinido') {
        confirmMsg = `¿Confirmar PASO A CONTRATO INDEFINIDO (Planta) para ${nombre}?`;
    } else if (action === 'desactivar') {
        // Formatear fecha para el mensaje: DD/MM/YYYY
        const fParte = fechaSalida.split('-');
        const fFmt = fParte.length === 3 ? `${fParte[2]}/${fParte[1]}/${fParte[0]}` : fechaSalida;

        // Determinar si es programada o inmediata basándose en la fecha
        const hoy = new Date();
        hoy.setHours(0, 0, 0, 0);
        const fVenc = new Date(fechaSalida + 'T00:00:00');

        if (fVenc > hoy) {
            confirmMsg = `¿Confirmar BAJA PROGRAMADA para ${nombre}?\n\nEl contrato finalizará y el empleado será desactivado automáticamente el día: ${fFmt}.`;
        } else {
            confirmMsg = `¿Confirmar BAJA INMEDIATA para ${nombre}?\n\nEl empleado será desactivado del sistema hoy mismo.`;
        }
    } else {
        confirmMsg = `¿Está seguro de procesar esta acción (${action}) para ${nombre}?`;
    }

    if (!confirm(confirmMsg)) return;

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
                showNotification("Operación completada con éxito", "success");
            } else if (typeof showToast === 'function') {
                showToast("Operación completada con éxito");
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
        alert("ERROR: " + error.message);
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
                    <div class="text-muted" style="font-size: 0.72rem;">${rutFormatted}</div>
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

// Helper para formatear fechas (YYYY-MM-DD -> DD/MM/YYYY)
function formatDate(dateString) {
    if (!dateString) return '-';
    // Si la fecha viene como YYYY-MM-DD
    const parts = dateString.split('-');
    if (parts.length === 3) {
        return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }
    return dateString;
}
