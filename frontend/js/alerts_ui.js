// alerts_ui.js - Gestión de Alertas Globales de Vencimiento
// Este script se encarga de mostrar notificaciones persistentes en la UI

const API_VENCIMIENTOS_ALERTS = '/api/empleados/vencimientos/';
let lastAlertCount = 0;

// Exportaciones anticipadas para asegurar disponibilidad
window.hideMandatoryLock = function () {
    const modalEl = document.getElementById('modal-bloqueo-mandatorio');
    if (modalEl) {
        // Evitar advertencia de accesibilidad: quitar foco de botones internos antes de ocultar
        if (modalEl.contains(document.activeElement)) {
            document.activeElement.blur();
        }
        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.hide();
    }
};
window.refreshAlerts = () => { if (typeof checkContractAlerts === 'function') checkContractAlerts(); };

/**
 * Inicializa el sistema de alertas
 */
async function initAlertsUI() {
    console.log("🔔 Inicializando Sistema de Alertas Globales...");

    // Evitar colisión de backdrops: Si el wizard se abre, ocultar el modal de bloqueo mandatorio
    const wizardEl = document.getElementById('modal-sync-wizard');
    if (wizardEl) {
        wizardEl.addEventListener('show.bs.modal', () => {
            window.hideMandatoryLock();
        });
        wizardEl.addEventListener('hidden.bs.modal', () => {
            checkContractAlerts();
        });
    }

    // Ejecutar inmediatamente
    await checkContractAlerts();

    // Programar chequeo cada 5 minutos (opcional, por ahora solo al cargar/gestionar)
    // setInterval(checkContractAlerts, 5 * 60 * 1000);
}

/**
 * Consulta los vencimientos y actualiza los indicadores visuales
 */
async function checkContractAlerts() {
    try {
        const response = await fetch(`${API_VENCIMIENTOS_ALERTS}?days=45`);
        if (!response.ok) throw new Error("Error fetching alerts");

        const data = await response.json();

        // Contar alertas bloqueantes (Vencidos + Críticos + Alerta Legal)
        const blockingAlerts = data.filter(emp => emp.bloqueante);
        const totalBlocking = blockingAlerts.length;

        console.log(`📊 Alertas encontradas: ${data.length} totales, ${totalBlocking} bloqueantes.`);

        updateAlertBadges(totalBlocking);

        // --- BLOQUEO MANDATORIO ---
        // Se muestra si hay alertas críticas PENDIENTES, a menos que el Wizard Universal esté activo para evitar colisiones de backdrops y bloqueo (velo gris)
        const urgentAlerts = data.filter(emp => emp.bloqueante && !emp.es_procesado);
        const processedAlerts = data.filter(emp => emp.es_procesado);
        
        const wizardEl = document.getElementById('modal-sync-wizard');
        const wizardActive = window._wizardState && (
            window._wizardState.currentStep >= 8 || 
            (wizardEl && (wizardEl.classList.contains('show') || wizardEl.style.display === 'block'))
        );
        
        if (urgentAlerts.length > 0 && !wizardActive) {
            showMandatoryLock(urgentAlerts, processedAlerts);
        } else {
            hideMandatoryLock();
        }

        lastAlertCount = totalBlocking;

    } catch (error) {
        console.error("❌ Error en checkContractAlerts:", error);
    }
}

/**
 * Muestra el modal de bloqueo mandatorio
 */
function showMandatoryLock(urgentAlerts, processedAlerts = []) {
    const modal = document.getElementById('modal-bloqueo-mandatorio');
    const body = document.getElementById('bloqueo-vencimientos-body');
    const btnCerrar = document.getElementById('btn-cerrar-bloqueo');
    if (!modal || !body) return;

    // 1. Detectar Rol y Nivel de Bloqueo
    const userData = (typeof AuthService !== 'undefined') ? AuthService.getUser() : null;
    // El administrador es quien tiene alcance_global o rol_id = 1 (según auth.js)
    const esAdmin = userData && (userData.alcance_global === 1 || userData.alcance_global === true || userData.rol_id === 1);
    
    // Alertas 'Hard' son las que tienen requiere_bloqueo=true (generalmente <= 5 días o vencidas)
    const tieneHardBlocking = urgentAlerts.some(emp => emp.requiere_bloqueo === true);
    
    // Regla de Negocio: 
    // - Admin SIEMPRE puede saltar.
    // - Usuario Normal SIEMPRE bloqueado si hay HardBlocking.
    // - Usuario Normal puede saltar si solo hay SoftBlocking (> 5 días).
    const isStrictlyLocked = tieneHardBlocking && !esAdmin;

    console.log(`[Bloqueo] Admin: ${esAdmin} | HardBlocking: ${tieneHardBlocking} | Locked: ${isStrictlyLocked}`);

    // 2. Configurar Interfaz (Botón X)
    if (btnCerrar) {
        if (esAdmin || !tieneHardBlocking) {
            btnCerrar.classList.remove('d-none'); // X visible si es admin O si solo son avisos ligeros
        } else {
            btnCerrar.classList.add('d-none'); // X oculta si es bloqueo mandatorio crítico
        }
    }

    let html = '';

    // 3. Renderizar PENDIENTES
    html += urgentAlerts.map(emp => renderVencimientoRow(emp, false)).join('');

    // 4. Renderizar PROCESADOS (Si existen)
    if (processedAlerts.length > 0) {
        html += `
            <tr class="bg-light">
                <td colspan="7" class="py-2">
                    <div class="d-flex align-items-center text-muted small fw-bold text-uppercase">
                        <hr class="flex-grow-1 me-2"> 
                        <i class="bi bi-check-circle-fill me-1"></i> Bajas Programadas / Confirmadas
                        <hr class="flex-grow-1 ms-2">
                    </div>
                </td>
            </tr>
        `;
        html += processedAlerts.map(emp => renderVencimientoRow(emp, true)).join('');
    }

    body.innerHTML = html;

    // Listener delegado para los botones procesar (evita problemas de escape en onclick)
    body.querySelectorAll('.btn-procesar-venc').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const dataBase64 = e.currentTarget.getAttribute('data-emp');
            const empObj = JSON.parse(decodeURIComponent(escape(atob(dataBase64))));
            if (typeof openVencimientoModal === 'function') {
                openVencimientoModal(empObj);
            }
        });
    });

    // 5. Gestión de la Instancia de Bootstrap (Crucial para el backdrop dinámico)
    // Destruimos la instancia previa para asegurar que se apliquen los nuevos parámetros de backdrop/keyboard
    let modalInstance = bootstrap.Modal.getInstance(modal);
    if (modalInstance) {
        modalInstance.dispose();
    }

    modalInstance = new bootstrap.Modal(modal, {
        backdrop: isStrictlyLocked ? 'static' : true,
        keyboard: isStrictlyLocked ? false : true
    });
    
    modalInstance.show();
}

function hideMandatoryLock() {
    const modalEl = document.getElementById('modal-bloqueo-mandatorio');
    if (modalEl) {
        if (modalEl.contains(document.activeElement)) {
            document.activeElement.blur();
        }
        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.hide();
    }
}

/**
 * Actualiza los elementos del DOM con el contador de alertas
 */
function updateAlertBadges(count) {
    console.log(`🎯 Actualizando UI con ${count} alertas bloqueantes.`);

    // 1. Badge en el Sidebar (Item Empleados)
    const sidebarItem = document.querySelector('.sidebar-item[data-page="empleados"]');
    if (sidebarItem) {
        let badge = sidebarItem.querySelector('.badge-alert-count');

        if (count > 0) {
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'badge rounded-pill bg-danger ms-auto badge-alert-count';
                badge.style.fontSize = '0.7rem';
                badge.style.padding = '0.3em 0.6em';
                sidebarItem.appendChild(badge);
                console.log("✅ Badge lateral creado.");
            }
            badge.innerText = count;
            badge.classList.remove('d-none');
        } else if (badge) {
            badge.classList.add('d-none');
        }
    } else {
        console.warn("⚠️ No se encontró sidebar-item[data-page='empleados']");
    }

    // 2. Icono de Campana en el Header
    const notificationContainer = document.getElementById('notification-center');
    if (notificationContainer) {
        const bellBadge = notificationContainer.querySelector('.bell-badge');
        if (count > 0) {
            if (bellBadge) {
                bellBadge.innerText = count;
                bellBadge.classList.remove('d-none');
                console.log("✅ Badge de campana actualizado.");
            }
            notificationContainer.title = `Tienes ${count} alertas de contrato críticas`;
            notificationContainer.classList.add('has-alerts');
        } else {
            if (bellBadge) bellBadge.classList.add('d-none');
            notificationContainer.title = "No hay alertas críticas";
            notificationContainer.classList.remove('has-alerts');
        }
    } else {
        console.warn("⚠️ No se encontró id='notification-center'");
    }
}
/**
 * Renderiza una fila de la tabla de vencimientos
 */
function renderVencimientoRow(emp, isProcessed) {
    const empData = btoa(unescape(encodeURIComponent(JSON.stringify(emp))));
    const opacityClass = isProcessed ? 'opacity-75' : '';
    const badgeClass = isProcessed ? 'bg-success' : (emp.estado_vencimiento === 'VENCIDO' ? 'bg-danger' : 'bg-warning text-dark');
    const estadoText = isProcessed ? (emp.decision_actual || 'PROCESADO') : emp.estado_vencimiento;

    return `
        <tr class="${opacityClass}">
            <td style="white-space: nowrap;">
                <div class="fw-bold ${isProcessed ? 'text-muted' : ''}" style="white-space: nowrap;">${emp.nombre_completo}</div>
                <div class="small text-muted" style="white-space: nowrap;">${emp.area || '-'} - ${emp.cargo || '-'}</div>
            </td>
            <td class="text-center">
                <span class="badge bg-secondary">N° ${emp.cant_contratos || 1}</span>
            </td>
            <td><span class="badge bg-light text-dark border">${emp.tipo_contrato}</span></td>
            <td class="${isProcessed ? 'text-muted' : 'text-danger'} fw-bold" style="white-space: nowrap;">${window.formatFechaDDMMYYYY(emp.fecha_salida) || 'Sin definir'}</td>
            <td class="text-center" style="white-space: nowrap;">
                <span class="badge bg-light text-dark border">
                    ${emp.dias_restantes !== undefined ? (emp.dias_restantes < 0 ? 'Vencido (' + emp.dias_restantes + ')' : emp.dias_restantes + ' días') : '-'}
                </span>
            </td>
            <td>
                <span class="badge ${badgeClass}" style="white-space: nowrap;">
                    ${estadoText}
                </span>
            </td>
            <td class="text-end" style="white-space: nowrap;">
                ${isProcessed ? `
                    <button class="btn btn-outline-secondary btn-sm btn-procesar-venc" data-emp="${empData}">
                        <i class="bi bi-eye"></i> Ver
                    </button>
                ` : `
                    <button class="btn btn-primary btn-sm btn-procesar-venc" data-emp="${empData}">
                        <i class="bi bi-pencil-square"></i> Procesar
                    </button>
                `}
            </td>
        </tr>
    `;
}
