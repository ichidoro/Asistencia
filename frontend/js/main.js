// API Configuration
// Usamos ruta relativa para evitar problemas de CORS/Host
const API_BASE_URL = '/api';

// ── Guardia de Producción: silencia logs en entornos no-desarrollo ──────────
// En producción (IP remota, dominio real) los console.log exponen datos internos.
// Solo se mantienen activos en localhost/127.0.0.1 (desarrollo local).
const _isDev = (
    location.hostname === 'localhost' ||
    location.hostname === '127.0.0.1' ||
    location.hostname.startsWith('192.168.') ||
    location.hostname === ''
);
if (!_isDev) {
    // Silenciar todos los logs en producción
    console.log = () => {};
    console.debug = () => {};
    console.group = () => {};
    console.groupEnd = () => {};
    console.groupCollapsed = () => {};
    console.time = () => {};
    console.timeEnd = () => {};
    // console.warn y console.error se mantienen para errores reales
}

// State
let currentPage = 1;
const pageSize = 10;
let searchQuery = '';
let currentEmpleadoId = null;
let currentAreaFilter = null; // Estado global para filtros
let currentSortBy = 'apellido_paterno'; // Estado global para ordenamiento
let currentSortOrder = 'asc';
let currentStatusFilter = 'todos'; // V13: Status filter chip state
let onboardingQueue = []; // Cola de nuevos empleados para configurar
let _isOnboardingFlow = false; // Flag: true cuando saveEmpleado viene del flujo de sync
let _batchTotalForOnboarding = 0; // Total de empleados en la cola batch (para el spinner)

// ── Batch Loading Overlay ─────────────────────────────────────────────────
const MAX_BATCH_SYNC = 10; // Límite estricto de empleados por sincronización masiva

function showBatchLoadingOverlay(msg) {
  const overlay = document.getElementById('batch-loading-overlay');
  const msgEl   = document.getElementById('batch-loading-msg');
  const empEl   = document.getElementById('batch-loading-emp');
  const cntEl   = document.getElementById('batch-loading-counter');
  const barEl   = document.getElementById('batch-loading-bar');
  if (!overlay) return;
  if (msgEl && msg) msgEl.textContent = msg;
  if (empEl) empEl.textContent = '';
  if (cntEl) cntEl.textContent = '';
  if (barEl) barEl.style.width = '0%';
  overlay.style.display = 'flex';
}

function updateBatchOverlayProgress(idx, total, nombre) {
  const empEl = document.getElementById('batch-loading-emp');
  const cntEl = document.getElementById('batch-loading-counter');
  const barEl = document.getElementById('batch-loading-bar');
  const msgEl = document.getElementById('batch-loading-msg');
  if (msgEl) msgEl.textContent = 'Creando empleados en la aplicación...';
  if (empEl) empEl.textContent = nombre || '';
  if (cntEl) cntEl.textContent = `${idx} / ${total}`;
  if (barEl) barEl.style.width = `${Math.round((idx / total) * 100)}%`;
}

function hideBatchLoadingOverlay() {
  const overlay = document.getElementById('batch-loading-overlay');
  if (overlay) overlay.style.display = 'none';
}
// ─────────────────────────────────────────────────────────────────────────

/**
 * Estado del proceso de onboarding batch.
 * Cuando se incorporan >1 empleado a la vez, el flujo se separa en fases:
 *   'edit'   → se editan todos los empleados (ficha) uno a uno
 *   'bonos'  → se muestran los bonos colectivos de todos los editados
 *   'turnos' → se asigna turno a cada empleado, 1 a 1 (sin sync individual)
 *   'sync'   → llamada única a /batch-sync/ para descargar y procesar todos
 */
const _batch = {
  active: false,
  phase: 'edit',         // fase actual
  editedEmployees: [],   // [{id, nombre, area, bonos_asignados, fecha_inicio}]
  syncPayload: [],       // [{empleado_id, fecha_inicio}] — se llena en fase turnos
};

/**
 * Función global para editar la fecha de asignación desde la tabla principal
 * Definida al inicio para asegurar disponibilidad total.
 */
window.iniciarEdicionFecha = function(id, originalValue, element) {
    if (element.querySelector('input')) return; // Evitar múltiples inputs
    
    // 🛡️ Usar el servicio de autenticación real para verificar el Superusuario
    const user = typeof AuthService !== 'undefined' ? AuthService.getUser() : null;
    
    // Diagnóstico para el explorador
    console.log("🛡️ Verificando permisos para edición de fecha (ID:", id, ")");
    if (user) console.log("Usuario actual:", user.username, "Rol Global:", user.alcance_global);

    // Permitir si es Alcance Global (Super Admin) o tiene rol de administrador
    const isSuperAdmin = user && user.alcance_global === true;
    const isAdmin = user && (user.rol_id === 1 || String(user.username).toLowerCase() === 'admin');
    
    if (!isSuperAdmin && !isAdmin) {
        console.warn("🚫 Acceso denegado: El usuario no tiene rango de Superusuario.");
        if (window.showToast) window.showToast('No tienes permisos de Superusuario para corregir fechas históricas', 'danger');
        return;
    }

    const input = document.createElement('input');
    input.type = 'date';
    input.className = 'form-control form-control-sm';
    // Limpiar el valor si es '-' o no es una fecha válida
    const cleanValue = (originalValue && originalValue.includes('-')) ? originalValue : '';
    input.value = cleanValue;
    
    const handleUpdate = async () => {
        const newDate = input.value;
        if (newDate && newDate !== cleanValue) {
            if (confirm(`¿Desea cambiar la fecha de inicio a ${newDate}?\n\n¡ATENCION!:\nEsta acción eliminará registros de asistencia 'basura' anteriores a esta fecha y reprocesará al empleado.`)) {
                try {
                    // Feedback visual: deshabilitar y mostrar carga
                    element.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
                    
                    const response = await fetch(`/api/turnos/asignacion/update-date/`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ empleado_id: id, nueva_fecha: newDate })
                    });
                    
                    if (response.ok) {
                        const res = await response.json();
                        if (window.showToast) window.showToast(res.message || 'Magia aplicada correctamente', 'success');
                        setTimeout(() => window.location.reload(), 1000); // Dar tiempo al toast
                    } else {
                        const err = await response.json();
                        alert('Error: ' + (err.detail || 'Error desconocido'));
                        element.textContent = originalValue || '-';
                    }
                } catch (error) {
                    console.error("Error en Magia:", error);
                    alert('Error de conexión o proceso');
                    element.textContent = originalValue || '-';
                }
            } else {
                element.textContent = originalValue || '-';
            }
        } else {
            element.textContent = originalValue || '-';
        }
    };

    input.onblur = handleUpdate;
    input.onkeydown = (e) => { 
        if (e.key === 'Enter') handleUpdate(); 
        if (e.key === 'Escape') element.textContent = originalValue || '-'; 
    };
    
    element.textContent = '';
    element.appendChild(input);
    input.focus();
};

// DOM Elements
const navItems = document.querySelectorAll('.sidebar-item');
const pages = document.querySelectorAll('.page');
const btnNuevoEmpleado = document.getElementById('btn-nuevo-empleado');
const btnSync = document.getElementById('btn-sync');
const modal = document.getElementById('modal-empleado');
const btnCloseModal = document.getElementById('btn-close-modal');
const btnCancelModal = document.getElementById('btn-cancel-modal');
const formEmpleado = document.getElementById('form-empleado');
const searchInput = document.getElementById('search-input');
const btnPrev = document.getElementById('btn-prev');
const btnNext = document.getElementById('btn-next');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  initializeApp();
});

async function initializeApp() {
  console.log('🚀 Inicializando aplicación...');

  // Cargar tabla maestra de estados (badges, tooltips) desde BD
  if (typeof window._loadEstadosAsistencia === 'function') {
    window._loadEstadosAsistencia(); // No-await: carga en paralelo, fallback hardcodeado disponible
  }

  // Event listeners
  setupEventListeners();

  // Initialize Modules
  if (typeof initContratosUI === 'function') initContratosUI();
  if (typeof initCumpleanosUI === 'function') initCumpleanosUI();
  if (typeof initAsignacionesUI === 'function') initAsignacionesUI();
  // Initialize Global Alerts System
  if (typeof initAlertsUI === 'function') initAlertsUI();

  console.log('✅ Aplicación base lista (Secuencia de inicio pendiente)');

  // Initialize Turnos Guard
  checkTurnosExist();

  // Start health monitoring
  // Fix #2: Health check adaptativo — empieza en 30s, sube hasta 2min si todo OK,
  // vuelve a 30s inmediatamente si detecta una falla (no pierde sensibilidad)
  let _healthInterval = 30000;
  async function _chequearSaludAdaptativo() {
    const ok = await updateSystemStatus();
    _healthInterval = ok
      ? Math.min(_healthInterval * 1.5, 120000)  // sube hasta 2 min si OK
      : 30000;                                     // vuelve a 30s si falla
    setTimeout(_chequearSaludAdaptativo, _healthInterval);
  }
  _chequearSaludAdaptativo();

  // [FIX] Escuchar el evento 'app:ready' emitido por startup_ui.js cuando el splash termina.
  // Esto resuelve la race condition: startup_ui.js carga ANTES que main.js (orden defer),
  // por lo que no puede llamar switchPage() directamente. El evento garantiza que
  // esta función ya está definida cuando se intenta navegar al dashboard.
  document.addEventListener('app:ready', () => {
    console.log('📊 [app:ready] Recibido → Cargando Dashboard inicial...');
    switchPage('dashboard');
  }, { once: true }); // once:true evita múltiples disparos si se re-emite
}

// Check if any turnos exist
window._hasTurnos = null;
async function checkTurnosExist() {
  try {
    const res = await fetch(`${API_BASE_URL}/turnos/stats/por-area`);
    if (res.ok) {
      const stats = await res.json();
      const globales = stats.globales || 0;
      const locales = Object.values(stats.areas || {}).reduce((a, b) => a + b, 0);
      window._hasTurnos = (globales + locales) > 0;
      return window._hasTurnos;
    }
  } catch (e) {
    console.error("Error al verificar turnos:", e);
  }
  return true; // Fallback to true to prevent locking out on network error
}

function setupEventListeners() {
  // Navigation
  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const pageName = item.dataset.page;
      switchPage(pageName);

      // Auto-colapso en móviles
      if (window.innerWidth <= 991) {
        const sidebar = document.querySelector('.sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        if (sidebar?.classList.contains('active')) {
          sidebar.classList.remove('active');
          overlay?.classList.remove('active');
        }
      }
    });
  });

  // Nuevo empleado button
  btnNuevoEmpleado.addEventListener('click', () => {
    openModal();
  });

  // Modal buttons
  btnCloseModal.addEventListener('click', closeModal);
  btnCancelModal.addEventListener('click', closeModal);

  // Form submit
  formEmpleado.addEventListener('submit', async (e) => {
    e.preventDefault();
    await saveEmpleado();
  });

  // Lógica de validación dinámica para Tipo de Contrato y Fecha Término
  const inputTipoContrato = document.getElementById('input-tipo-contrato');
  const inputFechaSalida = document.getElementById('input-fecha-salida');
  
  if (inputTipoContrato && inputFechaSalida) {
      inputTipoContrato.addEventListener('change', () => {
          if (inputTipoContrato.value === 'Indefinido') {
              inputFechaSalida.disabled = true;
              inputFechaSalida.value = ''; // Limpiar valor si pasa a Indefinido
              inputFechaSalida.removeAttribute('required');
          } else {
              inputFechaSalida.disabled = false;
              inputFechaSalida.setAttribute('required', 'required');
          }
      });
  }

  // Lógica para marcar por defecto Artículo 22 según el Cargo
  const inputCargo = document.getElementById('input-cargo');
  if (inputCargo) {
      inputCargo.addEventListener('change', () => {
          const selectedOption = inputCargo.options[inputCargo.selectedIndex];
          if (selectedOption) {
              const exclDefault = selectedOption.getAttribute('data-excluido-default');
              if (exclDefault !== null) {
                  const switchArt22 = document.getElementById('input-excluido-asistencia');
                  if (switchArt22) {
                      switchArt22.checked = (exclDefault === '1');
                  }
              }
          }
      });
  }

  // Search and Filter
  let searchTimeout;
  const handleSearchAndFilter = () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      searchQuery = searchInput.value;
      currentPage = 1;
      loadEmpleados();
    }, 500);
  };

  searchInput.addEventListener('input', handleSearchAndFilter);
  // Filter Area listener removed as element is gone

  // Pagination
  btnPrev.addEventListener('click', () => {
    prevPage();
  });

  btnNext.addEventListener('click', () => {
    nextPage();
  });

  // Sync button (Two-Step workflow + Guardian Pre-Check + Wizard)
  btnSync.addEventListener('click', async () => {
    if (btnSync.disabled) return;
    btnSync.disabled = true;
    const originalHTML = btnSync.innerHTML;
    btnSync.innerHTML = '<span>🔄</span><span>Analizando...</span>';
    
    try {
      showBatchLoadingOverlay("Analizando integridad de áreas con BioAlba...");
      const res = await fetch(`${API_BASE_URL}/sync/guardian/check/`, {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
      });
      if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
      
      const data = await res.json();
      hideBatchLoadingOverlay();
      
      // Siempre abrimos el Wizard Universal de Sincronización para guiar el flujo completo
      if (typeof startSyncWizard === 'function') {
          startSyncWizard(data);
      } else {
          alert('El Wizard Universal no está cargado. Verifique los scripts.');
      }
    } catch (error) {
      hideBatchLoadingOverlay();
      console.error("Error validando guardián:", error);
      alert("Error al verificar la integridad con BioAlba: " + error.message);
    } finally {
      btnSync.innerHTML = originalHTML;
      btnSync.disabled = false;
    }
  });

  // Mobile Sidebar Toggle
  const sidebarToggle = document.getElementById('sidebar-toggle');
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.getElementById('sidebar-overlay');

  if (sidebarToggle && sidebar && overlay) {
    const toggleSidebar = () => {
      sidebar.classList.toggle('active');
      overlay.classList.toggle('active');
    };

    sidebarToggle.addEventListener('click', toggleSidebar);
    overlay.addEventListener('click', toggleSidebar);
  }

  // ── ONBOARDING GUARD: Si el usuario cancela el modal de turno durante el
  // flujo batch, avanzar al siguiente en la cola para no dejar empleados sin turno.
  // Se distingue "cancelación" de "confirmación" usando un flag interno que
  // saveAsignacionIndividual activa antes de cerrar el modal vía código.
  let _turnoModalConfirmed = false; // true si se cerró por confirmar (no por cancelar)
  const _modalTurnoEl = document.getElementById('modal-asignar-turno-individual');
  if (_modalTurnoEl) {
    // Se llama DESPUÉS de que el modal termina de ocultarse completamente
    _modalTurnoEl.addEventListener('hidden.bs.modal', () => {
      const isBatchTurnos = typeof _batch !== 'undefined' && _batch.active && _batch.phase === 'turnos';
      if (isBatchTurnos && !_turnoModalConfirmed) {
        // El usuario cerró SIN confirmar: registrar como omisión y avanzar
        console.warn('[Onboarding] Modal de turno cerrado sin confirmar — avanzando al siguiente empleado');
        if (window.showToast) {
          showToast('⚠️ Asignación omitida. El empleado no tendrá turno asignado hasta regularizar.', 'warning');
        }
        // Avanzar la cola (procesar el siguiente o cerrar el batch si era el último)
        if (typeof procesarColaOnboarding === 'function') {
          setTimeout(procesarColaOnboarding, 400);
        }
      }
      // Resetear la bandera para la próxima apertura
      _turnoModalConfirmed = false;
    });

    // Marcar confirmación cuando el usuario usa el botón Confirmar
    // (saveAsignacionIndividual cierra el modal vía código justo antes)
    const _btnConfirmar = document.getElementById('btn-confirmar-asignacion-individual');
    if (_btnConfirmar) {
      _btnConfirmar.addEventListener('click', () => {
        _turnoModalConfirmed = true;
      }, true); // capture: true para disparar antes del handler de Bootstrap
    }
  }

  // Sincronización Inteligente de Fecha de Área
  const areaFechaInput = document.getElementById('area-pending-fecha');
  const areaRuleSelect = document.getElementById('area-pending-align-rule');
  if (areaFechaInput && areaRuleSelect) {
    areaFechaInput.addEventListener('change', () => {
      // Si el usuario cambia la fecha manualmente, el selector debe marcar "Manual" 
      // para evitar confusión visual entre la regla y la fecha real
      if (areaRuleSelect.value !== 'custom') {
        console.log("🧩 Cambio manual de fecha detectado: Sincronizando selector a 'Manual'");
        areaRuleSelect.value = 'custom';
      }
    });
  }

  // Lógica para cálculo automático de Edad
  const inputFechaNacimiento = document.getElementById('input-fecha-nacimiento');
  const badgeEdad = document.getElementById('badge-edad');
  
  if (inputFechaNacimiento && badgeEdad) {
      inputFechaNacimiento.addEventListener('input', () => {
          const val = inputFechaNacimiento.value;
          if (!val) {
              badgeEdad.style.display = 'none';
              badgeEdad.innerText = '';
              return;
          }
          const hoy = new Date();
          const nacimiento = new Date(val);
          let edad = hoy.getFullYear() - nacimiento.getFullYear();
          const m = hoy.getMonth() - nacimiento.getMonth();
          if (m < 0 || (m === 0 && hoy.getDate() < nacimiento.getDate())) {
              edad--;
          }
          if (!isNaN(edad)) {
              badgeEdad.style.display = 'inline-block';
              badgeEdad.innerText = `${edad} años`;
          } else {
              badgeEdad.style.display = 'none';
              badgeEdad.innerText = '';
          }
      });
  }
}

function switchPage(pageName) {
  // Validar permisos antes de cambiar de página
  const sidebarItem = document.querySelector(`.sidebar-item[data-page="${pageName}"]`);
  if (sidebarItem && typeof AuthService !== 'undefined') {
    const permisoReq = sidebarItem.getAttribute('data-permiso');
    if (permisoReq && !AuthService.hasPermission(permisoReq)) {
      console.warn(`🚫 Acceso denegado a la sección "${pageName}" (falta permiso: ${permisoReq}).`);
      
      // Buscar la primera sección permitida
      const allowedItem = Array.from(document.querySelectorAll('.sidebar-item')).find(item => {
        const p = item.getAttribute('data-permiso');
        return !p || AuthService.hasPermission(p);
      });
      
      if (allowedItem) {
        const fallbackPage = allowedItem.getAttribute('data-page');
        console.log(`➡️ Redirigiendo automáticamente a la sección permitida: "${fallbackPage}"`);
        switchPage(fallbackPage);
      } else {
        AuthService.logout("No tiene permisos para acceder a ninguna sección del sistema.");
      }
      return;
    }
  }

  // Onboarding Guard: Prevent access to empleados if no turnos exist
  if (pageName === 'empleados') {
    if (window._hasTurnos === false) {
      alert("Debes configurar al menos un turno en el sistema antes de gestionar empleados.");
      switchPage('configuracion');
      setTimeout(() => {
        const tabHorarios = document.getElementById('horarios-tab');
        if (tabHorarios) tabHorarios.click();
      }, 100);
      return;
    } else if (window._hasTurnos === null) {
      checkTurnosExist().then(hasTurnos => {
        if (!hasTurnos) {
          alert("Debes configurar al menos un turno en el sistema antes de gestionar empleados.");
          switchPage('configuracion');
          setTimeout(() => {
            const tabHorarios = document.getElementById('horarios-tab');
            if (tabHorarios) tabHorarios.click();
          }, 100);
        } else {
          _executeSwitchPage(pageName);
        }
      });
      return;
    }
  }
  _executeSwitchPage(pageName);
}

function _executeSwitchPage(pageName) {
  const targetPage = document.getElementById(`page-${pageName}`);
  if (targetPage && targetPage.classList.contains('active')) {
      return; // Ya estamos aquí
  }
  console.log(`🔄 Cambiando a página: ${pageName}`);

  // Update nav
  navItems.forEach(item => {
    item.classList.remove('active');
    if (item.dataset.page === pageName) {
      item.classList.add('active');
    }
  });

  // Update pages
  pages.forEach(page => {
    page.classList.remove('active');
  });

  if (targetPage) {
    targetPage.classList.add('active');
  } else {
    console.error(`❌ No se encontró el contenedor id="page-${pageName}"`);
  }

  // Update title
  const titles = {
    'dashboard': 'Dashboard Analítico',
    'empleados': 'Gestión de Empleados',
    'marcaciones': 'Marcaciones de Asistencia',
    'calendario': 'Calendario Mensual',
    'reportes': 'Reportes y Estadísticas',
    'productos_4': '4 Productos',
    'configuracion': 'Panel de Configuración'
  };
  document.getElementById('page-title').textContent = titles[pageName] || pageName;

  // Initialize specific page logic
  if (pageName === 'dashboard') {
    console.log('📊 Inicializando Dashboard...');
    if (typeof initDashboard === 'function') initDashboard();
  } else if (pageName === 'configuracion') {
    console.log('⚙️ Inicializando Configuración...');
    if (typeof initHorarios === 'function') initHorarios();
    if (typeof initConfiguracionUI === 'function') initConfiguracionUI();
  } else if (pageName === 'empleados') {
    loadStats();
    loadEmpleados();
    if (typeof loadMonthlyBirthdays === 'function') loadMonthlyBirthdays();
  } else if (pageName === 'reportes') {
    console.log('📈 Inicializando Reportes...');
    if (typeof initAsistencia === 'function') initAsistencia();
  } else if (pageName === 'marcaciones') {
    console.log('⏰ Inicializando Marcaciones...');
    if (typeof initMarcacionesUI === 'function') initMarcacionesUI();
  } else if (pageName === 'productos_4') {
    console.log('🎁 Inicializando 4 Productos...');
    if (typeof Productos4Module !== 'undefined') Productos4Module.init();
  }
}

// API Functions
async function loadStats() {
  try {
    const response = await fetch(`${API_BASE_URL}/empleados/stats/`);
    const stats = await response.json();

    document.getElementById('stat-total').textContent = stats.total;
    document.getElementById('stat-activos').textContent = stats.activos;
    document.getElementById('stat-inactivos').textContent = stats.inactivos;

    // Fetch Attendance Stats
    try {
      const attResponse = await fetch(`${API_BASE_URL}/asistencia/stats/`);
      if (attResponse.ok) {
        const attStats = await attResponse.json();
        document.getElementById('stat-presentes').textContent = attStats.presents || 0;
        document.getElementById('stat-atrasos').textContent = attStats.late || 0;
        document.getElementById('stat-inasistencias').textContent = attStats.absent || 0;
      }
    } catch (e) {
      console.warn("No se pudieron cargar estadisticas de asistencia:", e);
    }

    // Populate Areas
    const areasContainer = document.getElementById('areas-breakdown');

    if (stats.areas && stats.areas.length > 0) {
      // Area badges (V13 Modern)
      areasContainer.innerHTML = stats.areas.map(a => {
        const isActive = currentAreaFilter === a.area ? 'active' : '';
        const areaSafe = a.area.replace(/'/g, "\\'");
        const areaClass = getAreaBadgeClass(a.area);
        return `<div class="area-badge ${areaClass} ${isActive}" 
                     style="cursor: pointer; padding: 5px 12px; transition: all 0.2s;${isActive ? ' box-shadow: 0 0 0 2px var(--primary-color); font-weight: 700;' : ''}" 
                     onclick="toggleAreaFilter('${areaSafe}')" title="Filtrar por ${a.area}">
                ${a.area} <strong>(${a.count})</strong>
            </div>`;
      }).join('');
    } else {
      areasContainer.innerHTML = '<span class="text-muted small fst-italic">Sin datos de áreas</span>';
    }

  } catch (error) {
    console.error('Error loading stats:', error);
  }
}

// Fix #3: toggleAreaFilter ya no llama loadStats() — los totales de la empresa
// no cambian al filtrar por área. Solo se actualiza el badge y se recarga la tabla.
window.toggleAreaFilter = function (area) {
  if (currentAreaFilter === area) {
    currentAreaFilter = null; // Toggle off
  } else {
    currentAreaFilter = area; // Set new
  }

  // Actualizar badge UI
  const badgeContainer = document.getElementById('active-filter-container');
  const badgeText = document.getElementById('active-filter-badge');

  if (currentAreaFilter) {
    if (badgeContainer) badgeContainer.style.display = 'flex';
    const areaClass = getAreaBadgeClass(currentAreaFilter);
    if (badgeText) {
      badgeText.className = `area-badge ${areaClass}`;
      badgeText.style.cursor = 'pointer';
      badgeText.innerHTML = `<i class="bi bi-funnel-fill me-1"></i>${currentAreaFilter} <span style="margin-left: 4px;">×</span>`;
    }
  } else {
    if (badgeContainer) badgeContainer.style.display = 'none';
  }

  // Fix #3: Solo recargar la tabla — NO loadStats() (esos conteos no cambian al filtrar)
  currentPage = 1;
  loadEmpleados();
};

// Tab State
let currentEmpleadoTab = 'lista'; // 'lista' or 'matrix'

// Función global para cambiar pestaña
window.switchEmpleadoTab = function (tabName) {
  currentEmpleadoTab = tabName;

  // Update UI btns (V13 emp-inner-tab)
  document.querySelectorAll('.emp-inner-tab').forEach(btn => {
    if (btn.dataset.tab === tabName) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  // Update Content
  if (tabName === 'lista') {
    document.getElementById('tab-content-lista').style.display = 'block';
    document.getElementById('tab-content-matrix').style.display = 'none';
    loadEmpleados(); // Reload list
  } else {
    document.getElementById('tab-content-lista').style.display = 'none';
    document.getElementById('tab-content-matrix').style.display = 'block';
    loadBonosMatrix(); // Load matrix
  }
};

// --- V13: Filtro por Estado (Chips) ---
window.filterByStatus = function(status) {
  currentStatusFilter = status;
  // Update chip UI
  document.querySelectorAll('.emp-filter-chip').forEach(chip => {
    chip.classList.remove('active', 'active-success', 'active-danger');
  });
  const activeChip = document.getElementById(`chip-${status}`);
  if (activeChip) {
    if (status === 'activos') activeChip.classList.add('active-success');
    else if (status === 'inactivos') activeChip.classList.add('active-danger');
    else activeChip.classList.add('active');
  }
  currentPage = 1;
  loadEmpleados();
};

// --- V13: Area Badge Color Mapping ---
function getAreaBadgeClass(area) {
  if (!area) return 'area-badge-default';
  const normalized = area.toLowerCase().trim();
  if (normalized.includes('produccion') || normalized.includes('producción')) return 'area-badge-produccion';
  if (normalized.includes('logistica tradicional') || normalized.includes('logística tradicional')) return 'area-badge-logistica-tradicional';
  if (normalized.includes('seguridad')) return 'area-badge-seguridad';
  if (normalized.includes('mantencion') || normalized.includes('mantención')) return 'area-badge-mantencion';
  if (normalized.includes('logistica') || normalized.includes('logística')) return 'area-badge-logistica';
  return 'area-badge-default';
}

// --- V13: Avatar Color Palette ---
const AVATAR_GRADIENTS = [
  'linear-gradient(135deg, #6366f1, #8b5cf6)',
  'linear-gradient(135deg, #3b82f6, #06b6d4)',
  'linear-gradient(135deg, #10b981, #059669)',
  'linear-gradient(135deg, #f59e0b, #d97706)',
  'linear-gradient(135deg, #ef4444, #dc2626)',
  'linear-gradient(135deg, #ec4899, #be185d)',
  'linear-gradient(135deg, #8b5cf6, #7c3aed)',
  'linear-gradient(135deg, #14b8a6, #0d9488)',
  'linear-gradient(135deg, #f97316, #ea580c)',
  'linear-gradient(135deg, #6366f1, #4f46e5)',
];

function getAvatarGradient(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return AVATAR_GRADIENTS[Math.abs(hash) % AVATAR_GRADIENTS.length];
}

function getInitials(nombre, apellido) {
  const n = (nombre || '').trim();
  const a = (apellido || '').trim();
  return ((a[0] || '') + (n[0] || '')).toUpperCase();
}

async function loadEmpleados() {
  // If matrix tab is active, redirect to matrix loader (if called by filters)
  if (currentEmpleadoTab === 'matrix') {
    loadBonosMatrix();
    return;
  }

  const skip = (currentPage - 1) * pageSize;
  const areaFilter = currentAreaFilter;

  // Base URL
  let url = `${API_BASE_URL}/empleados/search/?skip=${skip}&limit=${pageSize}`;

  // Append Sort Params
  url += `&sort_by=${encodeURIComponent(currentSortBy)}&order=${encodeURIComponent(currentSortOrder)}`;

  const currentSearch = document.getElementById('search-input').value;

  if (currentSearch) {
    url += `&q=${encodeURIComponent(currentSearch)}`;
  }

  if (areaFilter) {
    url += `&area=${encodeURIComponent(areaFilter)}`;
  }

  // V13: Status filter (Chips)
  if (currentStatusFilter === 'activos') {
    url += `&activo=true`;
  } else if (currentStatusFilter === 'inactivos') {
    url += `&activo=false`;
  }

  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();



    renderEmpleados(data.empleados);
    updatePagination(data.total);
  } catch (error) {
    console.error('Error loading empleados:', error);
    showError('Error al cargar empleados: ' + error.message);
  }
}

async function loadBonosMatrix() {
  const skip = (currentPage - 1) * pageSize;
  const areaFilter = currentAreaFilter;

  let url = `${API_BASE_URL}/empleados/matrix/?skip=${skip}&limit=${pageSize}`;

  const currentSearch = document.getElementById('search-input').value;
  if (currentSearch) {
    url += `&q=${encodeURIComponent(currentSearch)}`;
  }
  if (areaFilter) {
    url += `&area=${encodeURIComponent(areaFilter)}`;
  }

  try {
    // Show loading state?
    const tbody = document.getElementById('matrix-body');
    if (tbody) tbody.innerHTML = '<tr><td colspan="10" class="text-center p-4">Cargando matriz...</td></tr>';

    const response = await fetch(url);
    if (!response.ok) throw new Error("Error cargando matriz");

    const data = await response.json();
    renderBonosMatrix(data);
    updatePagination(data.total);

  } catch (error) {
    console.error("Error matriz:", error);
    showError("Error al cargar matriz de bonos");
  }
}

function renderBonosMatrix(data) {
  const headersRow = document.getElementById('matrix-headers');
  const tbody = document.getElementById('matrix-body');

  if (!headersRow || !tbody) return;

  // 1. Render Headers
  // Mantener primera columna "Empleado", "Cargo" y "Contrato" [NEW]
  let headerHTML = `
        <th style="min-width: 250px; position: sticky; left: 0; background: #fff; z-index: 2;">Empleado</th>
        <th style="min-width: 150px;">Cargo</th>
        <th style="min-width: 120px;">Contrato</th>
    `;

  data.columns.forEach(col => {
    headerHTML += `<th class="text-center" style="min-width: 100px;">${col.nombre}</th>`;
  });
  headersRow.innerHTML = headerHTML;

  // 2. Render Body
  if (data.data.length === 0) {
    tbody.innerHTML = `<tr><td colspan="${data.columns.length + 3}" class="text-center p-4">No se encontraron empleados</td></tr>`;
    return;
  }

  tbody.innerHTML = data.data.map(emp => {
    let cells = '';
    data.columns.forEach(col => {
      const hasBono = emp.asignaciones[col.id.toString()] === true;
      // Rojo suave si no, Verde suave si si
      const bgClass = hasBono ? 'bg-success-subtle text-success' : 'text-muted-light';
      const icon = hasBono ? '✅' : '—';
      cells += `<td class="text-center ${bgClass}" style="font-size: 1.1em;">${icon}</td>`;
    });

    return `
            <tr>
                <td style="position: sticky; left: 0; background: #fff; z-index: 1;">
                    <div class="d-flex flex-column">
                        <span class="fw-bold text-dark">${emp.nombre_completo}</span>
                        <span class="small text-muted">${emp.rut}</span>
                    </div>
                </td>
                <td>
                    <span class="badge bg-light text-dark border">${emp.cargo}</span>
                </td>
                <td>
                    <span class="small text-muted">${emp.tipo_contrato || '-'}</span>
                </td>
                ${cells}
            </tr>
        `;
  }).join('');
}

// ==========================================
// TABLE SORTER UTILITY
// ==========================================
window.TableSorter = {
  states: {}, // { tableId: { key: 'name', dir: 1 } }

  sort: function (data, key, tableId) {
    if (!this.states[tableId]) this.states[tableId] = { key: null, dir: 1 };

    const state = this.states[tableId];
    if (state.key === key) {
      state.dir *= -1;
    } else {
      state.key = key;
      state.dir = 1;
    }

    return data.sort((a, b) => {
      let valA = this.getValue(a, key);
      let valB = this.getValue(b, key);

      if (valA < valB) return -1 * state.dir;
      if (valA > valB) return 1 * state.dir;
      return 0;
    });
  },

  getValue: function (obj, key) {
    if (!obj) return '';
    const val = obj[key];
    if (val === null || val === undefined) return '';
    return val.toString().toLowerCase();
  },

  updateIcons: function (tableId, headers) {
    const state = this.states[tableId] || {};
    headers.forEach(h => {
      const icon = document.getElementById(`sort-icon-${tableId}-${h}`);
      if (icon) {
        if (state.key === h) {
          icon.className = state.dir === 1 ? 'bi bi-sort-alpha-down text-primary' : 'bi bi-sort-alpha-up-alt text-primary';
        } else {
          icon.className = 'bi bi-arrow-down-up small text-muted';
        }
      }
    });
  }
};

let currentEmpleadosList = []; // Store for sorting

function renderEmpleados(empleados) {
  currentEmpleadosList = empleados; // Keep reference
  const tbody = document.getElementById('empleados-table-body');

  const sinAsignar = '<span class="text-muted fst-italic" style="font-size:0.75rem;opacity:0.7;">Sin Asignar</span>';

  // V13: Empty State Premium
  if (empleados.length === 0) {
    tbody.innerHTML = `
            <tr>
                <td colspan="10">
                    <div class="emp-empty-state">
                        <i class="bi bi-person-x empty-icon"></i>
                        <h6>No se encontraron empleados</h6>
                        <p>Intenta modificar los filtros o buscar con otros términos</p>
                        <button class="btn btn-sm btn-outline-primary" onclick="document.getElementById('search-input').value=''; filterByStatus('todos'); loadEmpleados();">
                            <i class="bi bi-arrow-counterclockwise me-1"></i>Limpiar búsqueda
                        </button>
                    </div>
                </td>
            </tr>
        `;
    return;
  }

  // Update icons based on global state
  updateSortIcons();

  tbody.innerHTML = empleados.map((empleado, idx) => {
    const estadoText = empleado.activo ? 'Activo' : 'Inactivo';
    const fullName = `${empleado.apellido_paterno || ''} ${empleado.apellido_materno || ''} ${empleado.nombre || ''}`.trim();
    const initials = getInitials(empleado.nombre, empleado.apellido_paterno);
    const avatarBg = getAvatarGradient(fullName);
    const areaBadge = empleado.area 
      ? `<span class="area-badge ${getAreaBadgeClass(empleado.area)}">${empleado.area}</span>` 
      : sinAsignar;
    const animDelay = `animation-delay: ${idx * 0.03}s;`;

    return `
            <tr class="fade-in-row" style="${animDelay}">
                <td>${empleado.rut || sinAsignar}</td>
                <td>
                    <div class="d-flex align-items-center gap-2">
                        <div class="avatar-initials" style="background: ${avatarBg};">${initials}</div>
                        <div>
                            <div class="fw-bold" style="font-size: 0.85rem;">${fullName}</div>
                            <div class="text-muted" style="font-size: 0.68rem;">${empleado.email || ''}</div>
                        </div>
                    </div>
                </td>
                <td><div class="small">${empleado.cargo || sinAsignar}</div></td>
                <td>${areaBadge}</td>
                <td><div class="small">${empleado.tipo_contrato || sinAsignar}</div></td>
                <td><div class="small text-muted">${empleado.fecha_nacimiento || sinAsignar}</div></td>
                <td><div class="small text-muted">${empleado.fecha_ingreso || sinAsignar}</div></td>
                    <td class="text-center align-middle" 
                    style="cursor: pointer;" 
                    data-bs-toggle="tooltip" data-bs-title="Doble clic para corregir fecha"
                    ondblclick="window.iniciarEdicionFecha(${empleado.id}, '${empleado.fecha_asignacion_turno || ''}', this)">
                    <div class="small text-muted">${empleado.fecha_asignacion_turno || sinAsignar}</div>
                </td>
                <td><span class="status-pill ${empleado.activo ? 'status-pill-success' : 'status-pill-danger'}"><span class="pill-dot" style="background: ${empleado.activo ? '#10b981' : '#f43f5e'};"></span>${estadoText}</span></td>
                <td>
                    <div class="action-buttons-container">
                        ${AuthService.hasPermission('empleados.editar') ? `
                        <button class="btn btn-premium-action btn-edit-premium" onclick="editEmpleado(${empleado.id})" data-bs-toggle="tooltip" data-bs-title="Editar ficha">
                            <i class="bi bi-pencil-square"></i>
                        </button>
                        ` : ''}
                        ${empleado.activo && empleado.area && AuthService.hasPermission('empleados.horarios') ? `
                        <button class="btn btn-premium-action" 
                                style="color:#0d9488; background:#f0fdfa; border: 1px solid #99f6e4;"
                                data-bs-toggle="tooltip" data-bs-title="Cambiar turno"
                                onclick="openAsignarTurnoForzado(${empleado.id}, '${new Date().toISOString().split('T')[0]}', '${(empleado.area || '').replace(/'/g, "\\'")}', '${(empleado.apellido_paterno + ' ' + (empleado.apellido_materno || '') + ' ' + empleado.nombre).trim().replace(/'/g, "\\'")}', '${(empleado.cargo || '').replace(/'/g, "\\'")}')"> 
                            <i class="bi bi-arrow-repeat"></i>
                        </button>
                        ` : ''}
                        ${AuthService.hasPermission('empleados.eliminar') ? `
                        <button class="btn btn-premium-action btn-delete-premium" onclick="deleteEmpleado(${empleado.id})" data-bs-toggle="tooltip" data-bs-title="Eliminar permanentemente">
                            <i class="bi bi-trash"></i>
                        </button>
                        ` : ''}
                        ${!empleado.activo && AuthService.hasPermission('empleados.reincorporar') ? `
                            <button class="btn btn-reincorporar-premium" onclick="openReincorporarWizard(${empleado.id})" data-bs-toggle="tooltip" data-bs-title="Reincorporar empleado"><i class="bi bi-rocket-takeoff me-1"></i>Reincorporar</button>
                        ` : ''}
                    </div>
                </td>
            </tr>
        `;
  }).join('');

  // V13: Initialize Bootstrap tooltips
  document.querySelectorAll('#empleados-table-body [data-bs-toggle="tooltip"]').forEach(el => {
    new bootstrap.Tooltip(el, { trigger: 'hover', placement: 'top', delay: { show: 300, hide: 0 } });
  });
}

window.sortEmpleados = function (key) {
  // Map 'nombre' to 'apellido_paterno' for backend consistency
  const actualKey = key === 'nombre' ? 'apellido_paterno' : key;

  if (currentSortBy === actualKey) {
    // Toggle order
    currentSortOrder = currentSortOrder === 'asc' ? 'desc' : 'asc';
  } else {
    // New key, default to asc
    currentSortBy = actualKey;
    currentSortOrder = 'asc';
  }

  // Reload data (which will trigger server-side sort)
  // We keep current page to allow sorting within the current view? 
  // Usually sorting resets to page 1 to avoid confusion, but user might want to stay.
  // Let's reset to page 1 for consistency.
  currentPage = 1;
  loadEmpleados();
};

function updateSortIcons() {
  const headers = ['rut', 'nombre', 'cargo', 'area', 'tipo_contrato', 'fecha_nacimiento', 'fecha_ingreso', 'fecha_asignacion_turno', 'activo'];
  // Map sort keys that differ between display and backend
  const keyMap = { 'nombre': 'apellido_paterno' };

  headers.forEach(h => {
    const icon = document.getElementById(`sort-icon-empleados-${h}`);
    if (!icon) return;

    const backendKey = keyMap[h] || h;
    const th = icon.closest('th');

    if (currentSortBy === backendKey) {
      icon.className = currentSortOrder === 'asc'
        ? 'bi bi-sort-alpha-down sort-icon text-primary'
        : 'bi bi-sort-alpha-up-alt sort-icon text-primary';
      if (th) th.classList.add('sort-active');
    } else {
      icon.className = 'bi bi-arrow-down-up sort-icon text-muted';
      if (th) th.classList.remove('sort-active');
    }
  });
}

function updatePagination(total) {
  const start = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const end = Math.min(currentPage * pageSize, total);

  const startEl = document.getElementById('pagn-start');
  const endEl = document.getElementById('pagn-end');
  const totalEl = document.getElementById('pagn-total');

  if (startEl) startEl.textContent = start;
  if (endEl) endEl.textContent = end;
  if (totalEl) totalEl.textContent = total;

  const totalPages = Math.ceil(total / pageSize);

  // V13: Enhanced Pagination with numbered pages
  const paginationContainer = document.getElementById('emp-pagination-numbers');
  if (paginationContainer) {
    // Remove old page numbers (keep prev/next)
    const prevItem = document.getElementById('page-item-prev');
    const nextItem = document.getElementById('page-item-next');

    // Clear middle items
    while (paginationContainer.children.length > 2) {
      paginationContainer.removeChild(paginationContainer.children[1]);
    }

    // Prev state
    if (prevItem) prevItem.classList.toggle('disabled', currentPage === 1);
    if (nextItem) nextItem.classList.toggle('disabled', currentPage >= totalPages || total === 0);

    // Build numbered pages
    const maxVisible = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    if (endPage - startPage < maxVisible - 1) startPage = Math.max(1, endPage - maxVisible + 1);

    // First page + ellipsis
    if (startPage > 1) {
      insertPageNumber(paginationContainer, nextItem, 1);
      if (startPage > 2) insertPageEllipsis(paginationContainer, nextItem);
    }

    // Middle pages
    for (let i = startPage; i <= endPage; i++) {
      insertPageNumber(paginationContainer, nextItem, i);
    }

    // Ellipsis + last page
    if (endPage < totalPages) {
      if (endPage < totalPages - 1) insertPageEllipsis(paginationContainer, nextItem);
      insertPageNumber(paginationContainer, nextItem, totalPages);
    }
  }
}

function insertPageNumber(container, beforeEl, pageNum) {
  const li = document.createElement('li');
  li.className = `page-item${pageNum === currentPage ? ' active' : ''}`;
  li.innerHTML = `<a class="page-link" href="#" onclick="event.preventDefault(); goToPage(${pageNum});">${pageNum}</a>`;
  container.insertBefore(li, beforeEl);
}

function insertPageEllipsis(container, beforeEl) {
  const li = document.createElement('li');
  li.className = 'page-item disabled';
  li.innerHTML = '<span class="page-link">…</span>';
  container.insertBefore(li, beforeEl);
}

window.goToPage = function(page) {
  currentPage = page;
  loadEmpleados();
};

window.prevPage = function() {
  if (currentPage > 1) {
    currentPage--;
    loadEmpleados();
  }
};

window.nextPage = function() {
  currentPage++;
  loadEmpleados();
};

// Catalog variables for dynamic dropdowns
let catalogsLoaded = false;
let catalogAreas = [];
let catalogCargos = [];
let catalogGeneros = [];

async function loadCatalogsForModal() {
  if (catalogsLoaded) return;
  try {
    const [resAreas, resCargos, resGeneros] = await Promise.all([
      fetch(`${API_BASE_URL}/configuracion/areas/`),
      fetch(`${API_BASE_URL}/configuracion/cargos/`),
      fetch(`${API_BASE_URL}/configuracion/generos/`)
    ]);
    
    if (resAreas.ok) catalogAreas = await resAreas.json();
    if (resCargos.ok) catalogCargos = await resCargos.json();
    if (resGeneros.ok) catalogGeneros = await resGeneros.json();
    
    catalogsLoaded = true;
  } catch (error) {
    console.error("Error loading catalogs for employee modal:", error);
  }
}

function setupDynamicSelects() {
  const selectArea = document.getElementById('input-area');
  const selectCargo = document.getElementById('input-cargo');
  const selectGenero = document.getElementById('input-genero');
  
  if (selectArea) {
    selectArea.innerHTML = '<option value="">-- Seleccionar Área --</option>';
    catalogAreas.forEach(area => {
      selectArea.innerHTML += `<option value="${area.id}">${area.nombre}</option>`;
    });
  }
  
  if (selectCargo) {
    selectCargo.innerHTML = '<option value="">-- Seleccionar Cargo --</option>';
    catalogCargos.forEach(cargo => {
      const defaultExcl = cargo.excluido_asistencia ? '1' : '0';
      selectCargo.innerHTML += `<option value="${cargo.id}" data-excluido-default="${defaultExcl}">${cargo.nombre}</option>`;
    });
  }
  
  if (selectGenero) {
    selectGenero.innerHTML = '<option value="">-- Seleccionar Género --</option>';
    catalogGeneros.forEach(gen => {
      selectGenero.innerHTML += `<option value="${gen.id}">${gen.nombre}</option>`;
    });
  }
}

// Modal Functions
async function openModal(empleadoId = null) {
  currentEmpleadoId = empleadoId;
  const dangerZone = document.getElementById('danger-zone-container');
  const tabHistorial = document.getElementById('tab-li-historial');

  // Reset tabs to first one
  const firstTabEl = document.querySelector('#emp-datos-tab');
  if (firstTabEl) {
    const firstTab = new bootstrap.Tab(firstTabEl);
    firstTab.show();
  }

  // Load catalogs and populate selects
  await loadCatalogsForModal();
  setupDynamicSelects();

  // Reset fields to editable by default (for new manual employee)
  document.getElementById('input-rut').disabled = false;
  document.getElementById('input-nombre').disabled = false;
  document.getElementById('input-apellido-paterno').disabled = false;
  document.getElementById('input-apellido-materno').disabled = false;
  document.getElementById('input-area').disabled = false;
  document.getElementById('input-cargo').disabled = false;
  document.getElementById('input-genero').disabled = false;
  
  // Hide tooltips initially
  const tooltipArea = document.getElementById('tooltip-area-info');
  const tooltipGenero = document.getElementById('tooltip-genero-info');
  if (tooltipArea) tooltipArea.style.display = 'none';
  if (tooltipGenero) tooltipGenero.style.display = 'none';

  if (empleadoId) {
    document.getElementById('modal-title').textContent = 'Editar Empleado';
    if (dangerZone) dangerZone.classList.remove('d-none');
    if (tabHistorial) tabHistorial.style.display = 'block'; // Mostrar si es edición
    await loadEmpleadoData(empleadoId);
  } else {
    document.getElementById('modal-title').textContent = 'Nuevo Empleado';
    if (dangerZone) dangerZone.classList.add('d-none');
    if (tabHistorial) tabHistorial.style.display = 'none'; // Ocultar si es nuevo
    formEmpleado.reset();

    // Estado inicial por defecto (Nuevo)
    const inputTipoContrato = document.getElementById('input-tipo-contrato');
    if (inputTipoContrato) {
        inputTipoContrato.value = 'Indefinido';
        inputTipoContrato.dispatchEvent(new Event('change'));
    }
    
    const inputFechaNacimiento = document.getElementById('input-fecha-nacimiento');
    if (inputFechaNacimiento) {
        inputFechaNacimiento.dispatchEvent(new Event('input'));
    }

    const switchArt22 = document.getElementById('input-excluido-asistencia');
    if (switchArt22) {
        switchArt22.checked = false;
    }
  }

  modal.classList.add('active');
  hideBatchLoadingOverlay(); // Spinner apagado: la ficha ya está visible
}

function closeModal() {
  modal.classList.remove('active');
  formEmpleado.reset();
  currentEmpleadoId = null;
}

async function loadEmpleadoData(id) {
  try {
    const response = await fetch(`${API_BASE_URL}/empleados/${id}/`);
    
    if (!response.ok) {
      console.error(`Error cargando empleado ${id}: HTTP ${response.status}`);
      showError(`Error al cargar empleado (HTTP ${response.status}). Puede que haya sido eliminado.`);
      closeModal();
      return;
    }
    
    const empleado = await response.json();
    window.currentEmpleadoName = `${empleado.apellido_paterno} ${empleado.apellido_materno || ''} ${empleado.nombre}`.trim().replace(/  +/g, ' ');

    document.getElementById('input-rut').value = empleado.rut || '';
    document.getElementById('input-rut').disabled = true; // RUT inmutable en edición
    document.getElementById('input-nombre').value = empleado.nombre || '';
    document.getElementById('input-apellido-paterno').value = empleado.apellido_paterno || '';
    document.getElementById('input-apellido-materno').value = empleado.apellido_materno || '';
    
    // Cargar y resolver Cargo Select (con fallback a texto)
    const selectCargo = document.getElementById('input-cargo');
    if (empleado.cargo_id) {
      selectCargo.value = empleado.cargo_id;
    } else if (empleado.cargo) {
      const nameLower = empleado.cargo.toLowerCase().trim();
      const option = Array.from(selectCargo.options).find(opt => opt.text.toLowerCase().trim() === nameLower);
      if (option) selectCargo.value = option.value;
    } else {
      selectCargo.value = '';
    }
    
    // Cargar y resolver Área Select (con fallback a texto)
    const selectArea = document.getElementById('input-area');
    if (empleado.area_id) {
      selectArea.value = empleado.area_id;
    } else if (empleado.area) {
      const nameLower = empleado.area.toLowerCase().trim();
      const option = Array.from(selectArea.options).find(opt => opt.text.toLowerCase().trim() === nameLower);
      if (option) selectArea.value = option.value;
    } else {
      selectArea.value = '';
    }

    document.getElementById('input-compania').value = empleado.compania || '';
    document.getElementById('input-email').value = empleado.email || '';
    document.getElementById('input-telefono').value = empleado.telefono || '';
    document.getElementById('input-fecha-ingreso').value = empleado.fecha_ingreso || '';
    const inputFechaNacimiento = document.getElementById('input-fecha-nacimiento');
    inputFechaNacimiento.value = empleado.fecha_nacimiento || '';
    inputFechaNacimiento.dispatchEvent(new Event('input')); // Actualizar badge de edad
    document.getElementById('input-fecha-salida').value = empleado.fecha_salida || '';
    const tipoContratoInput = document.getElementById('input-tipo-contrato');
    tipoContratoInput.value = empleado.tipo_contrato || 'Indefinido';
    tipoContratoInput.dispatchEvent(new Event('change')); // Ajustar campos dinámicamente
    // Asegurarnos de que el valor se mantenga si cambió a algo inválido antes (solo por seguridad)
    document.getElementById('input-fecha-salida').value = empleado.tipo_contrato === 'Indefinido' ? '' : (empleado.fecha_salida || '');
    
    document.getElementById('input-cant-contratos').value = empleado.cant_contratos || 1;
    document.getElementById('input-activo').value = empleado.activo.toString();

    // Cargar y resolver Género Select (con fallback a texto)
    const selectGenero = document.getElementById('input-genero');
    if (empleado.genero_id) {
      selectGenero.value = empleado.genero_id;
    } else if (empleado.genero) {
      const nameLower = empleado.genero.toLowerCase().trim();
      const option = Array.from(selectGenero.options).find(opt => opt.text.toLowerCase().trim() === nameLower);
      if (option) selectGenero.value = option.value;
    } else {
      selectGenero.value = '';
    }

    // Switch de Artículo 22
    const switchArt22 = document.getElementById('input-excluido-asistencia');
    if (switchArt22) {
      switchArt22.checked = !!empleado.excluido_asistencia;
    }

    // Control de edición según origen (Manual vs Sincronizado)
    const isManual = !!empleado.es_manual;
    document.getElementById('input-nombre').disabled = !isManual;
    document.getElementById('input-apellido-paterno').disabled = !isManual;
    document.getElementById('input-apellido-materno').disabled = !isManual;
    document.getElementById('input-cargo').disabled = !isManual;
    document.getElementById('input-area').disabled = !isManual;
    document.getElementById('input-genero').disabled = !isManual;
    
    const tooltipArea = document.getElementById('tooltip-area-info');
    const tooltipGenero = document.getElementById('tooltip-genero-info');
    if (tooltipArea) tooltipArea.style.display = isManual ? 'none' : 'inline-block';
    if (tooltipGenero) tooltipGenero.style.display = isManual ? 'none' : 'inline-block';
  } catch (error) {
    console.error('Error loading empleado:', error);
    showError('Error al cargar datos del empleado');
  }
}

let _isSaving = false; // Guard contra doble-click en Guardar

async function saveEmpleado() {
    if (_isSaving) return; // Ignorar clicks mientras ya hay una petición en curso

    const generoIdVal = document.getElementById('input-genero')?.value || null;
    const tipoContrato = document.getElementById('input-tipo-contrato').value || 'Temporal';
    const fechaSalida = document.getElementById('input-fecha-salida').value || null;
    const activo = document.getElementById('input-activo').value === 'true';

    // 🛡️ VALIDACIÓN ESTRICTA (Anti-Dirty Data)
    if (activo) {
        if (!generoIdVal) {
            showError("El GÉNERO es obligatorio para empleados activos.");
            return;
        }
        if (tipoContrato === 'Temporal' && !fechaSalida) {
            showError("La FECHA DE TÉRMINO es obligatoria para contratos Temporales.");
            return;
        }
    }

    const selectCargo = document.getElementById('input-cargo');
    const selectArea = document.getElementById('input-area');
    
    const cargoId = parseInt(selectCargo.value) || null;
    const areaId = parseInt(selectArea.value) || null;
    const generoId = parseInt(generoIdVal) || null;

    const data = {
        rut: document.getElementById('input-rut').value,
        nombre: document.getElementById('input-nombre').value,
        apellido_paterno: document.getElementById('input-apellido-paterno').value,
        apellido_materno: document.getElementById('input-apellido-materno').value,
        cargo_id: cargoId,
        cargo: null,
        area_id: areaId,
        area: null,
        compania: document.getElementById('input-compania').value || null,
        email: document.getElementById('input-email').value || null,
        telefono: document.getElementById('input-telefono').value || null,
        fecha_ingreso: document.getElementById('input-fecha-ingreso').value || null,
        fecha_nacimiento: document.getElementById('input-fecha-nacimiento').value || null,
        fecha_salida: fechaSalida,
        tipo_contrato: tipoContrato,
        cant_contratos: parseInt(document.getElementById('input-cant-contratos').value) || 1,
        activo: activo,
        genero_id: generoId,
        genero: null,
        excluido_asistencia: document.getElementById('input-excluido-asistencia')?.checked || false
    };

    if (!currentEmpleadoId) {
        data.es_manual = true;
    }

    // Bloquear botón durante la operación
    const btnSubmit = formEmpleado.querySelector('[type="submit"], .btn-guardar-empleado, button[onclick*="save"]')
                   || formEmpleado.querySelector('button.btn-primary')
                   || document.getElementById('btn-guardar-empleado');
    const originalText = btnSubmit?.textContent;
    if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Guardando...';
    }
    _isSaving = true;

    try {
    let response;

    if (currentEmpleadoId) {
      // Update
      response = await fetch(`${API_BASE_URL}/empleados/${currentEmpleadoId}/`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });
    } else {
      // Create
      response = await fetch(`${API_BASE_URL}/empleados/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });
    }

    if (response.ok) {
      const savedEmpleado = await response.json();
      const wasEditing = !!currentEmpleadoId;
      closeModal();
      // Fix #B: Invalidar caché de áreas al guardar un empleado
      // (puede haber cambiado de área o ser nuevo en un área distinta)
      window._cachedAreas = null;
      window._cachedMetadata = null;
      await loadStats();
      await loadEmpleados();
      showNotification(
        wasEditing ? 'Empleado actualizado correctamente' : 'Empleado creado correctamente',
        'success'
      );

      // ── Función que dispara el flujo de asignación de turno ─────────────────
      const triggerAsignarTurno = () => {

        // ════════════════════════════════════════════════════════════════════
        // MODO BATCH — fase 'edit': recolectar datos, no abrir turno, seguir
        // ════════════════════════════════════════════════════════════════════
        if (_batch.active && _batch.phase === 'edit') {
          _isOnboardingFlow = false;
          // GUARD: Solo empleados ACTIVOS entran al flujo de asignación de turno.
          // Un inactivo queda registrado en el sistema pero no recibirá modal de turno.
          if (savedEmpleado.activo) {
            _batch.editedEmployees.push({
              id:              savedEmpleado.id,
              nombre:          `${savedEmpleado.apellido_paterno} ${savedEmpleado.apellido_materno || ''} ${savedEmpleado.nombre}`.trim().replace(/  +/g, ' '),
              area:            savedEmpleado.area || '',
              bonos_asignados: savedEmpleado.bonos_asignados || [],
              fecha_inicio:    savedEmpleado.fecha_ingreso
                               || new Date().toISOString().split('T')[0],
            });
            console.log(
              `[Batch] Emp activo registrado: ${savedEmpleado.nombre} (${_batch.editedEmployees.length} en cola)`
            );
          } else {
            console.warn(
              `[Batch] Emp INACTIVO omitido de cola de turnos: ${savedEmpleado.nombre}`
            );
            if (window.showToast) {
              showToast(`⏭️ ${savedEmpleado.nombre} marcado como inactivo — omitido de asignación de turno`, 'warning');
            }
          }
          // Avanzar al siguiente empleado en la cola de edición
          if (onboardingQueue.length > 0) {
            setTimeout(procesarColaOnboarding, 350);
          } else {
            // Todos los empleados editados → pasar a bonos colectivos
            setTimeout(_mostrarBatchBonosModal, 400);
          }
          return;
        }

        // ════════════════════════════════════════════════════════════════════
        // MODO INDIVIDUAL (1 empleado) — flujo original
        // ════════════════════════════════════════════════════════════════════
        if (_isOnboardingFlow && savedEmpleado.activo) {
          _isOnboardingFlow = false;
          const nombre = `${savedEmpleado.apellido_paterno} ${savedEmpleado.apellido_materno || ''} ${savedEmpleado.nombre}`.trim().replace(/  +/g, ' ');
          const hoy = new Date().toISOString().split('T')[0];
          const area = savedEmpleado.area || '';

          const doOpen = () => {
            if (typeof openAsignarTurnoForzado === 'function') {
              openAsignarTurnoForzado(savedEmpleado.id, hoy, area, nombre, savedEmpleado.cargo || '');
            } else {
              showToast(`⚠️ Asigne un turno a ${nombre} en Horarios → Asignación Masiva`, 'warning');
            }
          };

          if (typeof openAsignarTurnoForzado === 'function') {
            setTimeout(doOpen, 300);
          } else {
            switchPage('marcaciones');
            setTimeout(doOpen, 900);
          }
          // La cola avanzará cuando el usuario CONFIRME el turno (ver marcaciones_ui.js)
        }
        else if (onboardingQueue.length > 0) {
          procesarColaOnboarding();
        }
      };

      // ── Modal de Bonos (solo en edición, empleado ACTIVO y si hay bonos asignados) ──
      // GUARD: Un empleado inactivo NO debe ver el modal de bonos ni el de turno.
      // El flujo continúa silenciosamente para no bloquear la cola.
      const bonosAsignados = savedEmpleado.bonos_asignados || [];
      if (wasEditing && bonosAsignados.length > 0 && !_batch.active && savedEmpleado.activo) {
        // Modo individual, empleado activo con bonos: modal de bonos → luego turno
        window._bonosContinuarCallback = triggerAsignarTurno;
        mostrarModalBonos(savedEmpleado, bonosAsignados);
      } else {
        // Batch, sin bonos, o empleado INACTIVO: ir directo al flujo (que ya filtra inactivos)
        triggerAsignarTurno();
      }

    } else {
      const error = await response.json();
      showError(error.detail || 'Error al guardar empleado');
    }
  } catch (error) {
    console.error('Error saving empleado:', error);
    showError('Error al guardar empleado');
  } finally {
    // Siempre re-habilitar el botón al terminar (éxito o error)
    _isSaving = false;
    if (btnSubmit) {
      btnSubmit.disabled = false;
      btnSubmit.textContent = originalText || 'Guardar';
    }
  }
}


/** Muestra el modal de bonos asignados con los datos del empleado */
function mostrarModalBonos(empleado, bonos) {
  const nombre = `${empleado.apellido_paterno} ${empleado.apellido_materno || ''} ${empleado.nombre}`.trim().replace(/  +/g, ' ');
  document.getElementById('bonos-emp-nombre').textContent = nombre;
  document.getElementById('bonos-emp-subtitulo').textContent =
    `Recálculo automático completado · ${empleado.cargo || 'Sin cargo'}`;

  const hoy = new Date().toLocaleDateString('es-CL', { day: '2-digit', month: 'long', year: 'numeric' });
  document.getElementById('bonos-fecha-hoy').textContent = hoy;

  // Inyectar lista de bonos con badges animiados
  const lista = document.getElementById('bonos-lista');
  const sinBonos = document.getElementById('bonos-sin-bonos');
  lista.innerHTML = '';
  lista.classList.remove('d-none');
  sinBonos.classList.add('d-none');

  bonos.forEach((nombre, i) => {
    const item = document.createElement('div');
    item.className = 'bono-item d-flex align-items-center gap-3 p-3 rounded-3 border';
    item.style.cssText = `
      background: linear-gradient(135deg, #fffbeb, #fef3c7);
      border-color: #fcd34d !important;
      animation: bonoFadeIn 0.3s ease ${i * 0.08}s both;
    `;
    item.innerHTML = `
      <div class="rounded-circle d-flex align-items-center justify-content-center flex-shrink-0"
           style="width:36px;height:36px;background:linear-gradient(135deg,#d97706,#f59e0b);">
        <i class="bi bi-currency-dollar text-white fw-bold"></i>
      </div>
      <div class="flex-grow-1">
        <div class="fw-semibold text-dark">${nombre}</div>
        <div class="small text-muted">Activo desde hoy</div>
      </div>
      <span class="badge rounded-pill" style="background:#d97706;">
        <i class="bi bi-check-lg me-1"></i>Asignado
      </span>
    `;
    lista.appendChild(item);
  });

  // Agregar keyframe de animación si no existe
  if (!document.getElementById('bono-anim-style')) {
    const style = document.createElement('style');
    style.id = 'bono-anim-style';
    style.textContent = `
      @keyframes bonoFadeIn {
        from { opacity: 0; transform: translateY(8px); }
        to   { opacity: 1; transform: translateY(0); }
      }
    `;
    document.head.appendChild(style);
  }

  const modalEl = document.getElementById('modal-bonos-asignados');
  if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();
}


/** Cierra el modal de bonos y dispara el siguiente paso del flujo */
window.cerrarModalBonos = function() {
  // FIX ARIA: Mover foco fuera del modal ANTES de ocultarlo.
  // Bootstrap agrega aria-hidden="true" al ocultar, pero si un hijo
  // retiene el foco en ese instante, Chrome emite un warning de accesibilidad.
  if (document.activeElement && document.getElementById('modal-bonos-asignados')?.contains(document.activeElement)) {
    document.activeElement.blur();
  }
  const modalEl = document.getElementById('modal-bonos-asignados');
  if (modalEl) bootstrap.Modal.getInstance(modalEl)?.hide();
  // Dar tiempo para que la animación de cierre termine antes de abrir el siguiente modal
  setTimeout(() => {
    if (typeof window._bonosContinuarCallback === 'function') {
      window._bonosContinuarCallback();
      window._bonosContinuarCallback = null;
    }
  }, 350);
};




// Global Functions (called from HTML onclick)
window.editEmpleado = (id) => {
  openModal(id);
};

window.deleteEmpleado = async (id) => {
  if (!confirm('⚠️ ¡ADVERTENCIA CRÍTICA!\n\nEstás a punto de ELIMINAR PERMANENTEMENTE a este empleado y TODO su historial (asistencias, turnos, bonos, etc.) de la aplicación.\n\nEsta acción NO SE PUEDE DESHACER. ¿Estás absolutamente seguro de continuar?')) {
    return;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/empleados/${id}/?hard=true`, {
      method: 'DELETE'
    });

    if (response.ok) {
      await loadStats();
      await loadEmpleados();
      showNotification('Empleado eliminado permanentemente del sistema', 'success');
    } else {
      showError('Error al eliminar empleado de forma permanente');
    }
  } catch (error) {
    console.error('Error deleting empleado:', error);
    showError('Error al eliminar empleado');
  }
};

// Notification Functions
window.showToast = function (message, type = 'info') {
  let toastEl = document.getElementById('liveToast');
  let toastMessage = document.getElementById('toast-message');
  
  if (!toastEl) {
    const container = document.createElement('div');
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    container.style.zIndex = '9999';
    container.innerHTML = `
      <div id="liveToast" class="toast align-items-center border-0" role="alert" aria-live="assertive" aria-atomic="true">
        <div class="d-flex">
          <div id="toast-message" class="toast-body fw-semibold"></div>
          <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
      </div>
    `;
    document.body.appendChild(container);
    toastEl = document.getElementById('liveToast');
    toastMessage = document.getElementById('toast-message');
  }

  if (!toastEl || !toastMessage) return;

  toastMessage.textContent = message;

  // Set color based on type
  toastEl.classList.remove('bg-primary', 'bg-success', 'bg-danger', 'bg-warning', 'bg-info', 'text-white');
  if (type === 'success') toastEl.classList.add('bg-success', 'text-white');
  else if (type === 'error') toastEl.classList.add('bg-danger', 'text-white');
  else if (type === 'warning') toastEl.classList.add('bg-warning', 'text-dark');
  else if (type === 'info') toastEl.classList.add('bg-info', 'text-white');
  else toastEl.classList.add('bg-primary', 'text-white');

  const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
  toast.show();
}

window.showNotification = function (message, type = 'info') {
  window.showToast(message, type);
}

window.showError = function (message) {
  window.showToast(message, 'error');
}

// --- Health & Sync Monitor ---
async function updateSystemStatus() {
  const dot = document.querySelector('.status-dot');
  const text = document.querySelector('.status span:last-child');
  if (!dot || !text) return true;

  try {
    const res = await fetch(`${API_BASE_URL}/sync/health/`);
    if (!res.ok) throw new Error();
    const health = await res.json();

    if (health.status === 'ok') {
      dot.style.backgroundColor = '#10b981'; // Green
      text.textContent = 'En línea (Nube Sync)';
      dot.classList.remove('status-offline');
      return true;  // ← OK: el intervalo puede crecer
    } else {
      dot.style.backgroundColor = '#f59e0b'; // Amber
      text.textContent = 'Degradado (Solo Local)';
      dot.classList.add('status-offline');
      return false; // ← Degradado: mantener chequeo frecuente
    }
  } catch (e) {
    dot.style.backgroundColor = '#ef4444'; // Red
    text.textContent = 'Fuera de línea (Servidor)';
    dot.classList.add('status-offline');
    return false;   // ← Error: volver a 30s
  }
}

// --- Sync Modal Logic ---

// --- ONBOARDING QUEUE PROCESSOR ---
function procesarColaOnboarding() {

  // ── MODO BATCH: fase 'turnos' ─────────────────────────────────────────────
  // En esta fase la cola fue recargada con los empleados a asignar turno.
  // Abrimos la modal de turno para cada uno; al confirmar, marcaciones_ui.js
  // llama de nuevo a procesarColaOnboarding para el siguiente.
  if (_batch.active && _batch.phase === 'turnos') {
    if (onboardingQueue.length === 0) {
      // Todos los turnos asignados → disparar sync batch
      console.log('[Batch] Todos los turnos asignados. Iniciando Fase Sync...');
      setTimeout(_execBatchSync, 400);
      return;
    }
    const nextEmp = onboardingQueue.shift();
    console.log(`[Batch/Turnos] Asignando turno a: ${nextEmp.nombre}`);
    _isOnboardingFlow = true;  // señal para que saveAsignacionIndividual avance la cola
    const doOpenTurno = () => {
      if (typeof openAsignarTurnoForzado === 'function') {
        openAsignarTurnoForzado(
          nextEmp.id,
          nextEmp.fecha_inicio || new Date().toISOString().split('T')[0],
          nextEmp.area,
          nextEmp.nombre,
          nextEmp.cargo || ''
        );
      }
    };
    if (document.querySelector('.page.active[data-page="marcaciones"]') ||
        document.getElementById('marcaciones-view-container')) {
      setTimeout(doOpenTurno, 300);
    } else {
      switchPage('marcaciones');
      setTimeout(doOpenTurno, 900);
    }
    return;
  }

  // ── MODO SINGLE / BATCH fase 'edit': abrir ficha de edición ───────────────
  if (onboardingQueue.length === 0) {
    console.log('Cola de onboarding (edición) finalizada.');
    _isOnboardingFlow = false;
    return;
  }

  const nextEmp = onboardingQueue.shift();
  // Calcular número actual: total - restantes (el que ya sacamos)
  const _processed = _batchTotalForOnboarding - onboardingQueue.length;
  const _spinMsg = _batchTotalForOnboarding > 1
    ? `Preparando empleado ${_processed} de ${_batchTotalForOnboarding}...\n${nextEmp.nombre}`
    : `Preparando empleado...\n${nextEmp.nombre}`;
  showBatchLoadingOverlay(_spinMsg);
  console.log(`Iniciando onboarding para: ${nextEmp.nombre} (ID: ${nextEmp.id})`);

  if (window.showToast) {
    window.showToast(`⚠️ Configuración obligatoria: ${nextEmp.nombre} — Complete los datos y asigne un turno.`, 'warning');
  }

  _isOnboardingFlow = true;
  if (typeof openModal === 'function') {
    openModal(nextEmp.id);
  }
}

/**
 * Muestra el modal de bonos COLECTIVO al finalizar la fase de edición batch.
 * Lista los bonos de todos los empleados editados en un solo panel.
 */
/**
 * Muestra el modal de bonos COLECTIVO al finalizar la fase de edición batch.
 * Reutiliza el modal #modal-bonos-asignados existente con los IDs reales del HTML:
 *   - modal-bonos-title    → título del header
 *   - bonos-emp-subtitulo  → subtítulo bajo el título
 *   - bonos-emp-nombre     → nombre del empleado (usamos "X empleados")
 *   - bonos-lista          → lista de bonos (inyectamos HTML agrupado por empleado)
 *   - bonos-sin-bonos      → mensaje cuando no hay bonos
 *   - btn-bonos-continuar  → botón que llama cerrarModalBonos() → _bonosContinuarCallback
 */
function _mostrarBatchBonosModal() {
  _batch.phase = 'bonos';
  const employees = _batch.editedEmployees;

  // ── Actualizar header del modal con los IDs reales ──────────────────────
  const titleEl    = document.getElementById('modal-bonos-title');
  const subtitleEl = document.getElementById('bonos-emp-subtitulo');
  const nombreEl   = document.getElementById('bonos-emp-nombre');
  const fechaEl    = document.getElementById('bonos-fecha-hoy');
  const listaEl    = document.getElementById('bonos-lista');
  const sinBonosEl = document.getElementById('bonos-sin-bonos');

  if (!listaEl) {
    // El modal no está en el DOM — ir directo a turnos
    console.warn('[Batch] No se encontró #bonos-lista en el DOM — pasando a turnos directamente');
    _iniciarBatchTurnosPhase();
    return;
  }

  if (titleEl)    titleEl.textContent    = `Bonos Asignados — ${employees.length} empleados`;
  if (subtitleEl) subtitleEl.textContent = 'Incorporación batch completada';
  if (nombreEl)   nombreEl.textContent   = `${employees.length} empleados incorporados`;
  if (fechaEl)    fechaEl.textContent    = new Date().toLocaleDateString('es-CL', {
    day: '2-digit', month: 'long', year: 'numeric'
  });

  // ── Construir lista agrupada por empleado ───────────────────────────────
  listaEl.innerHTML = '';
  listaEl.classList.remove('d-none');
  if (sinBonosEl) sinBonosEl.classList.add('d-none');

  let alguienTieneBonos = false;

  employees.forEach(emp => {
    const bonos = emp.bonos_asignados || [];
    if (bonos.length > 0) alguienTieneBonos = true;

    // Cabecera del empleado
    const empHeader = document.createElement('div');
    empHeader.className = 'fw-semibold text-primary mb-1 mt-2';
    empHeader.innerHTML = `<i class="bi bi-person-fill me-1"></i>${emp.nombre}`;
    listaEl.appendChild(empHeader);

    if (bonos.length === 0) {
      const noBonoEl = document.createElement('div');
      noBonoEl.className = 'text-muted small ms-3 mb-2';
      noBonoEl.textContent = 'Sin bonos asignados';
      listaEl.appendChild(noBonoEl);
    } else {
      bonos.forEach((bono, i) => {
        const bonoNombre = bono?.nombre || bono;
        const item = document.createElement('div');
        item.className = 'bono-item d-flex align-items-center gap-3 p-2 rounded-3 border mb-1';
        item.style.cssText = `
          background: linear-gradient(135deg, #fffbeb, #fef3c7);
          border-color: #fcd34d !important;
          animation: bonoFadeIn 0.3s ease ${i * 0.06}s both;
        `;
        item.innerHTML = `
          <div class="rounded-circle d-flex align-items-center justify-content-center flex-shrink-0"
               style="width:30px;height:30px;background:linear-gradient(135deg,#d97706,#f59e0b);">
            <i class="bi bi-currency-dollar text-white" style="font-size:0.8rem;"></i>
          </div>
          <div class="flex-grow-1">
            <div class="fw-semibold text-dark" style="font-size:0.85rem;">${bonoNombre}</div>
          </div>
          <span class="badge rounded-pill" style="background:#d97706;font-size:0.7rem;">
            <i class="bi bi-check-lg me-1"></i>Asignado
          </span>
        `;
        listaEl.appendChild(item);
      });
    }
  });

  // Si ningún empleado tiene bonos, mostrar mensaje vacío
  if (!alguienTieneBonos) {
    listaEl.classList.add('d-none');
    if (sinBonosEl) sinBonosEl.classList.remove('d-none');
  }

  // ── Registrar callback: al cerrar el modal → iniciar fase turnos ────────
  window._bonosContinuarCallback = () => {
    setTimeout(_iniciarBatchTurnosPhase, 150);
  };

  // ── Mostrar modal ───────────────────────────────────────────────────────
  const modalEl = document.getElementById('modal-bonos-asignados');
  if (modalEl) {
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  } else {
    console.warn('[Batch] No se encontró #modal-bonos-asignados — pasando a turnos');
    _iniciarBatchTurnosPhase();
  }
}


/**
 * Transición a la fase de asignación de turnos del batch.
 * Recarga onboardingQueue con los empleados editados para procesarlos 1 a 1.
 */
function _iniciarBatchTurnosPhase() {
  _batch.phase = 'turnos';
  _batch.syncPayload = []; // resetear payload de sync

  // Recargar la cola con los empleados que necesitan turno
  onboardingQueue = _batch.editedEmployees.map(e => ({ ...e }));
  console.log(`[Batch/Turnos] Iniciando asignación de turnos: ${onboardingQueue.length} empleados`);

  showToast(
    `📋 Asigne turno a cada empleado (${onboardingQueue.length} en total)`,
    'info'
  );

  // Pequeño delay para que cierren bien los modales anteriores
  setTimeout(procesarColaOnboarding, 500);
}

/**
 * Fase final del batch: llama a /api/asistencia/asignaciones/batch-sync/
 * con todos los (empleado_id, fecha_inicio) recopilados durante la fase turnos.
 * Muestra un modal de progreso con el estado del job para cada empleado.
 */
async function _execBatchSync() {
  _batch.phase = 'sync';
  const payload = _batch.syncPayload;

  if (payload.length === 0) {
    showToast('⚠️ No hay datos para sincronizar.', 'warning');
    _resetBatchState();
    return;
  }

  showToast(
    `☁️ Sincronizando ${payload.length} empleado(s) con BioAlba...`,
    'info'
  );

  try {
    const resp = await fetch('/api/asistencia/asignaciones/batch-sync/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: payload }),
    });

    if (!resp.ok) {
      const err = await resp.json();
      showToast('❌ Error en batch-sync: ' + (err.detail || 'Error desconocido'), 'danger');
      _resetBatchState();
      return;
    }

    const batchData = await resp.json();
    const jobIds = batchData.job_ids || {};
    const meses  = batchData.meses_a_descargar || 0;
    const total  = batchData.empleados || 0;

    showToast(
      `✅ Batch iniciado: ${total} empleados, ${meses} mes(es) de BioAlba`,
      'success'
    );

    // Mostrar progreso del job del primer empleado como representativo
    const primerEmpId  = Object.keys(jobIds)[0];
    const primerJobId  = primerEmpId ? jobIds[primerEmpId] : null;
    const primerNombre = _batch.editedEmployees[0]?.nombre || 'Batch';
    const primerFecha  = _batch.syncPayload[0]?.fecha_inicio || new Date().toISOString().split('T')[0];

    if (primerJobId && typeof abrirModalProgresoJob === 'function') {
      setTimeout(() => {
        abrirModalProgresoJob(primerJobId, `Batch (${total} emp.)`, primerFecha, {
          syncBioAlba: true,
          allJobIds: Object.values(jobIds),
          onComplete: () => {
            // BUG-1: Refrescar grilla de asistencia
            if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
            // BUG-1 FIX: Refrescar filtro de áreas para que áreas nuevas (ej: SEGURIDAD)
            // aparezcan inmediatamente sin necesidad de salir y volver al módulo.
            if (typeof loadMarcacionesFilters === 'function') {
              console.log('🔄 [BUG-1 Fix] Refrescando filtros de área post-batch...');
              loadMarcacionesFilters();
            }
          }
        });
      }, 400);
    }

  } catch (e) {
    console.error('[Batch] Error en batch-sync:', e);
    showToast('❌ Error de conexión en batch-sync', 'danger');
  } finally {
    _resetBatchState();
  }
}

/** Resetea el estado batch para la próxima operación. */
function _resetBatchState() {
  _batch.active = false;
  _batch.phase = 'edit';
  _batch.editedEmployees = [];
  _batch.syncPayload = [];
  _isOnboardingFlow = false;
  onboardingQueue = [];
}

window.openSyncModalPreview = function() {
  const modalSync = document.getElementById('modal-sync-areas');
  if (!modalSync) {
    console.error("ERROR CRÍTICO: No se encontró el elemento #modal-sync-areas en el DOM");
    return;
  }
  modalSync.classList.add('active');
  
  const title = document.getElementById('sync-modal-title');
  if (title) {
    title.textContent = window._syncSelectedAreas && window._syncSelectedAreas.length > 0 
      ? `Empleados (${window._syncSelectedAreas.join(', ')})` 
      : 'Todos los Empleados';
  }

  const listContainer = document.getElementById('sync-empleados-list');
  if (listContainer) {
    listContainer.innerHTML = `<div class="text-center p-4">
      <span class="spinner-border spinner-border-sm"></span> Descargando datos de BioAlba...<br>
      <small class="text-muted">Esto puede tardar unos segundos</small>
    </div>`;
  }

  // Llamar al endpoint
  fetchSyncPreviewData();
}

async function fetchSyncPreviewData() {
  const listContainer = document.getElementById('sync-empleados-list');
  try {
    const payload = {
      areas: window._syncSelectedAreas && window._syncSelectedAreas.length > 0 ? window._syncSelectedAreas : null,
      selected_cargos: window._selectedCargos && window._selectedCargos.length > 0 ? window._selectedCargos : null
    };
    const response = await fetch(`${API_BASE_URL}/sync/empleados/preview/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    _syncPreviewData = await response.json();
    
    // Filtrar por cargos seleccionados (si no está ignorado, o si está en la selección)
    if (window._syncSelectedCargos && window._syncSelectedCargos.length > 0 && window._syncSelectedAreas && window._syncSelectedAreas.length > 0) {
       _syncPreviewData = _syncPreviewData.filter(emp => {
           // Si el cargo (antes o después del mapeo) está ignorado, se quita.
           // O si el backend ya lo filtra, mejor. El backend debería filtrarlo con selected_cargos.
           // Por si acaso, si no está en _syncSelectedCargos y tiene un área que pedimos.
           return true; 
       });
    }

    renderSyncEmpleados(_syncPreviewData);

  } catch (error) {
    console.error('Error en preview:', error);
    if (listContainer) {
      listContainer.innerHTML = `<div class="text-danger p-3 text-center">❌ Error: ${error.message}</div>`;
    }
  }
}

window.closeModalSync = function () {
  const modalSync = document.getElementById('modal-sync-areas');
  if (modalSync) modalSync.classList.remove('active');
  const title = document.getElementById('sync-modal-title');
  if (title) title.textContent = 'Sincronizar Empleados';
  const search = document.getElementById('sync-emp-search');
  if (search) search.value = '';
}



function renderSyncEmpleados(empleados) {
  const listContainer = document.getElementById('sync-empleados-list');
  const counter = document.getElementById('sync-emp-counter');

  if (!empleados || empleados.length === 0) {
    listContainer.innerHTML = '<div class="text-center p-3 text-muted">No se encontraron empleados para las áreas seleccionadas.</div>';
    counter.textContent = '0 empleados';
    return;
  }

  counter.textContent = `${empleados.length} empleados`;

  // Usar DOM API en lugar de innerHTML para evitar que nombres con caracteres
  // especiales (comillas, &, etc.) rompan los atributos data-nombre / data-rut
  const wrapper = document.createElement('div');
  wrapper.className = 'list-group list-group-flush';

  empleados.forEach((emp, index) => {
    let badgeHTML = '';
    if (emp.es_nuevo) {
      badgeHTML = '<span class="badge bg-success ms-1">NUEVO</span>';
    } else if (emp.cambio_area) {
      badgeHTML = `<span class="badge bg-warning text-dark ms-1" title="${emp.area_local} → ${emp.area}">ÁREA</span>`;
    } else {
      badgeHTML = '<span class="badge bg-secondary ms-1">EXISTE</span>';
    }

    const areaChangeDetail = emp.cambio_area
      ? `<span class="text-warning" style="font-size:0.7rem;"> (${emp.area_local} → ${emp.area})</span>`
      : '';

    const label = document.createElement('label');
    label.className = 'list-group-item list-group-item-action d-flex align-items-center sync-emp-item py-1 px-2';
    label.style.cssText = 'cursor: pointer; font-size: 0.85rem;';

    // ← dataset preserva correctamente cualquier caracter en el nombre
    label.dataset.nombre = (emp.nombre || '').toLowerCase();
    label.dataset.rut    = (emp.rut    || '').toLowerCase();
    label.dataset.esNuevo = emp.es_nuevo ? 'true' : 'false';
    label.dataset.cambioArea = emp.cambio_area ? 'true' : 'false';

    label.innerHTML = `
      <input class="form-check-input me-2 sync-emp-checkbox" type="checkbox" value="${emp.rut}"
             checked data-index="${index}">
      <div class="flex-grow-1">
        <div class="fw-semibold">${emp.nombre} ${badgeHTML}</div>
        <div class="text-muted" style="font-size:0.75rem;">
          ${emp.rut} · ${emp.area}${areaChangeDetail}${emp.cargo ? ' · ' + emp.cargo : ''}
        </div>
      </div>
    `;
    wrapper.appendChild(label);
  });

  listContainer.innerHTML = '';
  listContainer.appendChild(wrapper);
  updateSyncEmpCounter();

  // Re-attachar listener de contador a los checkboxes recién creados
  listContainer.querySelectorAll('.sync-emp-checkbox').forEach(cb => {
    cb.addEventListener('change', updateSyncEmpCounter);
  });
}



function updateSyncEmpCounter() {
  // Solo contar items VISIBLES (excluye los filtrados con d-none)
  const allVisible   = document.querySelectorAll('.sync-emp-item:not(.d-none) .sync-emp-checkbox');
  const checked      = document.querySelectorAll('.sync-emp-item:not(.d-none) .sync-emp-checkbox:checked');
  const counter      = document.getElementById('sync-emp-counter');
  if (counter) counter.textContent = `${checked.length} / ${allVisible.length} seleccionados`;
}

window.toggleAllSyncEmps = function (checked) {
  // Solo afecta items VISIBLES (los que NO tienen la clase d-none por el filtro)
  document.querySelectorAll('.sync-emp-item:not(.d-none) .sync-emp-checkbox').forEach(cb => {
    cb.checked = checked;
  });
  updateSyncEmpCounter();
}

window.filterSyncEmpleados = function () {
  const query = (document.getElementById('sync-emp-search')?.value || '').toLowerCase().trim();
  const filterType = document.getElementById('sync-emp-filter-type')?.value || 'all';

  document.querySelectorAll('.sync-emp-item').forEach(item => {
    const nombre = (item.dataset.nombre || '').toLowerCase();
    const rut    = (item.dataset.rut    || '').toLowerCase();
    const isNew  = item.dataset.esNuevo === 'true';
    const isChanged = item.dataset.cambioArea === 'true';

    const matchesQuery = !query || nombre.includes(query) || rut.includes(query);
    const matchesType = (filterType === 'all') || (isNew || isChanged);

    item.classList.toggle('d-none', !(matchesQuery && matchesType));
  });
  updateSyncEmpCounter();
}



window.confirmSync = async function () {
  // 1. Recolectar RUTs seleccionados — solo de items VISIBLES (no filtrados)
  const checkedBoxes = document.querySelectorAll('.sync-emp-item:not(.d-none) .sync-emp-checkbox:checked');
  const allBoxes     = document.querySelectorAll('.sync-emp-item:not(.d-none) .sync-emp-checkbox');

  if (checkedBoxes.length === 0) {
    alert('⚠️ Seleccione al menos un empleado para sincronizar.');
    return;
  }

  // ── LÍMITE MÁXIMO DE 10 EMPLEADOS ─────────────────────────────────────────
  if (checkedBoxes.length > MAX_BATCH_SYNC) {
    alert(`⚠️ Límite de sincronización: máximo ${MAX_BATCH_SYNC} empleados por batch.\n` +
          `Has seleccionado ${checkedBoxes.length}. Desmarca algunos e intenta de nuevo.`);
    return;
  }

  // Si están todos los visibles seleccionados, no mandamos filtro de ruts (más eficiente)
  const selectedRuts = checkedBoxes.length < allBoxes.length 
    ? Array.from(checkedBoxes).map(cb => cb.value)
    : null;

  const filterMsg = selectedRuts 
    ? `${selectedRuts.length} empleado(s) seleccionado(s)` 
    : `Todos los ${allBoxes.length} empleado(s)`;

  if (!confirm(`¿Iniciar sincronización?\n(${filterMsg})`)) return;

  closeModalSync();

  // 2. Preparar payload
  const payload = {
    areas: _syncSelectedAreas.length > 0 ? _syncSelectedAreas : null,
    ruts: selectedRuts,
    selected_cargos: window._selectedCargos && window._selectedCargos.length > 0 ? window._selectedCargos : null
  };

  const btnSync = document.getElementById('btn-sync');
  btnSync.innerHTML = '<span>🔄</span><span>Sincronizando...</span>';
  btnSync.disabled = true;

  // 3. Mostrar spinner inicial
  showBatchLoadingOverlay('Conectando a BioAlba...');

  // 4. Usar SSE streaming para ver progreso nombre a nombre
  try {
    const response = await fetch(`${API_BASE_URL}/sync/empleados/now/stream/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      hideBatchLoadingOverlay();
      const errData = await response.json().catch(() => ({}));
      alert(`❌ Error: ${errData.detail || 'Error desconocido'}`);
      return;
    }

    // Leer el stream SSE
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalStats = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Parsear eventos SSE del buffer
      const lines = buffer.split('\n');
      buffer = lines.pop(); // Guardar línea incompleta

      let eventType = null;
      let eventData = null;
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          try { eventData = JSON.parse(line.slice(6)); } catch { eventData = null; }
        } else if (line === '' && eventType && eventData !== null) {
          // Evento completo
          if (eventType === 'start') {
            const total = eventData.total || '?';
            showBatchLoadingOverlay(`Sincronizando ${total} empleado(s)...`);
            console.log(`🚀 [Sync Stream] Total: ${total}`);
          } else if (eventType === 'progress') {
            updateBatchOverlayProgress(eventData.idx, eventData.total, eventData.nombre);
            console.log(`📌 [Sync] ${eventData.idx}/${eventData.total}: ${eventData.nombre}`);
          } else if (eventType === 'requires_confirmation') {
            hideBatchLoadingOverlay();
            
            if (typeof startSyncWizard === 'function') {
                startSyncWizard(eventData);
            } else {
                alert('El Wizard Universal no está cargado. Verifique los scripts.');
            }
            finalStats = null;
          } else if (eventType === 'done') {
            finalStats = eventData;
          } else if (eventType === 'error') {
            hideBatchLoadingOverlay();
            alert(`❌ Error durante sincronización: ${eventData.message || 'Error desconocido'}`);
          }
          // Reset para el próximo evento
          eventType = null;
          eventData = null;
        }
      }
    }

    // 5. Stream completado — procesar resultado final
    if (finalStats) {
      const stats = finalStats;

      await loadStats();
      await loadEmpleados();

      // Cola de Onboarding para nuevos empleados
      if (stats.nuevos_detalles && stats.nuevos_detalles.length > 0) {
        console.log("🆕 Nuevos empleados para onboarding:", stats.nuevos_detalles);
        onboardingQueue = [...stats.nuevos_detalles];
        _batchTotalForOnboarding = onboardingQueue.length;

        if (onboardingQueue.length > 1) {
          _batch.active = true;
          _batch.phase = 'edit';
          _batch.editedEmployees = [];
          _batch.syncPayload = [];
          showToast(`🚀 Batch: editarás ${onboardingQueue.length} empleados → bonos → turnos → sync`, 'info');
        } else {
          _batch.active = false;
        }

        // Transición al flujo de onboarding
        const _spinMsg = _batchTotalForOnboarding > 1
          ? `Preparando empleado 1 de ${_batchTotalForOnboarding}...`
          : `Preparando empleado...`;
        showBatchLoadingOverlay(_spinMsg);
        setTimeout(() => { procesarColaOnboarding(); }, 1500);
      } else {
        // No hay nuevos empleados — cerrar spinner y mostrar resumen
        hideBatchLoadingOverlay();
        let msg = `✅ Sincronización completada:\n` +
          `- Nuevos: ${stats.empleados_nuevos}\n` +
          `- Actualizados: ${stats.empleados_actualizados}\n` +
          `- Sin cambios: ${stats.empleados_sin_cambios || 0}\n` +
          `- Errores: ${stats.errores}`;
        if (stats.errores > 0 && stats.detalles_errores?.length > 0) {
          msg += `\n\nDetalles:\n${stats.detalles_errores.slice(0, 3).join('\n')}`;
        }
        alert(msg);
      }
    } else {
      hideBatchLoadingOverlay();
    }

  } catch (error) {
    hideBatchLoadingOverlay();
    console.error('Error en sync stream:', error);
    alert('❌ Error de conexión al iniciar sincronización');
  } finally {
    btnSync.innerHTML = '<span>🔄</span><span>Sincronizar</span>';
    btnSync.disabled = false;
  }
}

/**
 * Función puente para el Wizard: ejecuta el flujo SSE completo sin pasar por modal-sync-areas.
 * El wizard llama esta función pasando el payload directamente.
 * Tiene acceso a las variables internas de main.js (onboardingQueue, _batch, etc.)
 */
window._executeSyncFromWizard = async function(payload) {
  const btnSync = document.getElementById('btn-sync');
  if (btnSync) {
    btnSync.innerHTML = '<span>🔄</span><span>Sincronizando...</span>';
    btnSync.disabled = true;
  }

  showBatchLoadingOverlay('Conectando a BioAlba...');

  try {
    const response = await fetch(`${API_BASE_URL}/sync/empleados/now/stream/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      hideBatchLoadingOverlay();
      const errData = await response.json().catch(() => ({}));
      alert(`❌ Error: ${errData.detail || 'Error desconocido'}`);
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalStats = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop();

      let eventType = null;
      let eventData = null;
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          try { eventData = JSON.parse(line.slice(6)); } catch { eventData = null; }
        } else if (line === '' && eventType && eventData !== null) {
          if (eventType === 'start') {
            showBatchLoadingOverlay(`Sincronizando ${eventData.total || '?'} empleado(s)...`);
          } else if (eventType === 'progress') {
            updateBatchOverlayProgress(eventData.idx, eventData.total, eventData.nombre);
          } else if (eventType === 'done') {
            finalStats = eventData;
          } else if (eventType === 'error') {
            hideBatchLoadingOverlay();
            alert(`❌ Error: ${eventData.message || 'Error desconocido'}`);
          }
          eventType = null;
          eventData = null;
        }
      }
    }

    if (finalStats) {
      const stats = finalStats;
      await loadStats();
      await loadEmpleados();

      if (stats.nuevos_detalles && stats.nuevos_detalles.length > 0) {
        console.log("🆕 [Wizard→SSE] Nuevos empleados para onboarding:", stats.nuevos_detalles);
        onboardingQueue = [...stats.nuevos_detalles];
        _batchTotalForOnboarding = onboardingQueue.length;

        if (onboardingQueue.length > 1) {
          _batch.active = true;
          _batch.phase = 'edit';
          _batch.editedEmployees = [];
          _batch.syncPayload = [];
          showToast(`🚀 Batch: editarás ${onboardingQueue.length} empleados → bonos → turnos → sync`, 'info');
        } else {
          _batch.active = false;
        }

        const _spinMsg = _batchTotalForOnboarding > 1
          ? `Preparando empleado 1 de ${_batchTotalForOnboarding}...`
          : `Preparando empleado...`;
        showBatchLoadingOverlay(_spinMsg);
        setTimeout(() => { procesarColaOnboarding(); }, 1500);
      } else {
        hideBatchLoadingOverlay();
        alert(`✅ Sincronización completada:\n` +
          `- Nuevos: ${stats.empleados_nuevos}\n` +
          `- Actualizados: ${stats.empleados_actualizados}\n` +
          `- Sin cambios: ${stats.empleados_sin_cambios || 0}\n` +
          `- Errores: ${stats.errores}`);
      }
    } else {
      hideBatchLoadingOverlay();
    }

  } catch (error) {
    hideBatchLoadingOverlay();
    console.error('[Wizard→SSE] Error:', error);
    alert('❌ Error de conexión al iniciar sincronización');
  } finally {
    if (btnSync) {
      btnSync.innerHTML = '<span>🔄</span><span>Sincronizar</span>';
      btnSync.disabled = false;
    }
  }
};

// ==========================================
// LOGICA DE SYNC ASISTENCIA (Manual por Areas)
// ==========================================
// NOTA: Las funciones de sincronización de asistencia ahora están en marcaciones_ui.js
// El botón de sincronización está en la vista de Marcaciones con dropdown para filtrar por áreas

// ==========================================
// GESTIÓN DE BAJAS / RENUNCIAS
// ==========================================

window.openBajaConfirmation = function () {
  // Fix: Usar variable global currentEmpleadoId en lugar de input oculto no existente
  const empId = currentEmpleadoId;
  const nombre = document.getElementById('input-nombre').value;
  const apellido = document.getElementById('input-apellido-paterno').value;

  if (!empId) return; // No debería pasar si está en edición

  document.getElementById('baja-emp-nombre').textContent = `${nombre} ${apellido}`;
  document.getElementById('baja-fecha').value = new Date().toISOString().split('T')[0];
  document.getElementById('baja-motivo').value = 'Renuncia Voluntaria';

  document.getElementById('modal-baja-confirm').style.display = 'block';
}

window.closeBajaConfirmation = function () {
  document.getElementById('modal-baja-confirm').style.display = 'none';
}

window.confirmarBaja = async function () {
  // Fix: Usar variable global
  const empId = currentEmpleadoId;
  const fecha = document.getElementById('baja-fecha').value;
  const motivo = document.getElementById('baja-motivo').value;

  if (!fecha) return alert("Debe seleccionar una fecha de salida.");

  if (!confirm("¿Está seguro de registrar la baja? Esta acción puede desactivar al empleado.")) return;

  try {
    const response = await fetch(`${API_BASE_URL}/empleados/${empId}/baja/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fecha_inicio: fecha, // Reutilizamos campo fecha_inicio de VencimientoRequest (o nueva_fecha)
        nueva_fecha: fecha,
        accion: 'desactivar', // Dummy
        motivo: motivo
      })
    });

    if (response.ok) {
      alert("Baja registrada exitosamente.");
      closeBajaConfirmation();
      closeModal(); // Cerrar modal de empleado
      loadEmpleados(); // Recargar lista
    } else {
      const err = await response.json();
      alert("Error: " + (err.detail || "No se pudo registrar la baja"));
    }
  } catch (e) {
    console.error(e);
    alert("Error de conexión al registrar baja.");
  }
}
// --- DIAGNÓSTICO (MODO SECRETO 7890) ---
let secretSequence = "";
document.addEventListener('keydown', (e) => {
  // Solo permitimos números
  if (e.key >= '0' && e.key <= '9') {
    secretSequence += e.key;

    if (secretSequence.endsWith("7890")) {
      secretSequence = "";
      openDiagnostico();
    }
    // Limpiar si es muy larga
    if (secretSequence.length > 20) secretSequence = secretSequence.substring(10);
  }
});

// ==========================================
// HISTORIAL DE ÁREAS & VALIDACIÓN
// ==========================================

window.loadHistorialAreas = async function (empleadoId) {
  if (!empleadoId) return;

  const tbody = document.getElementById('historial-areas-tbody');
  if (!tbody) return;

  tbody.innerHTML = '<tr><td colspan="4" class="text-center py-3"><span class="spinner-border spinner-border-sm"></span> Cargando historial...</td></tr>';

  try {
    const response = await fetch(`${API_BASE_URL}/empleados/${empleadoId}/historial-areas/`);
    if (!response.ok) throw new Error("Error al cargar historial");

    const historial = await response.json();

    if (historial.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="text-center py-3 text-muted">Sin registros de cambios de área</td></tr>';
      return;
    }

    tbody.innerHTML = historial.map((reg, index) => {
      const badgeClass = reg.es_actual ? 'bg-success' : (reg.validado ? 'bg-secondary' : 'bg-warning text-dark cursor-pointer');
      const estadoText = reg.es_actual ? 'Actual' : (reg.validado ? 'Histórico' : 'Pendiente');
      // Intentar obtener el nombre del empleado para el modal
      const empName = window.currentEmpleadoName || (typeof matrix_data !== 'undefined' ? matrix_data[reg.empleado_id]?.info?.nombre_completo : null) || 'Empleado';

      // Área anterior es la que sigue en el historial (ya que está ordenado DESC por fecha)
      const areaAnterior = historial[index + 1] ? historial[index + 1].area : '';

      const dblClickAttr = !reg.validado ? `ondblclick="openConfirmarAreaModal(${reg.id}, '${empName}', '${areaAnterior}', '${reg.area}')"` : '';

      return `
                <tr ${dblClickAttr}>
                    <td class="fw-bold">${reg.area}</td>
                    <td>${reg.fecha_desde || '-'}</td>
                    <td>${reg.fecha_hasta || (reg.es_actual ? '<span class="text-muted">vigente</span>' : '-')}</td>
                    <td class="text-center">
                        <span class="badge ${badgeClass}" title="${!reg.validado ? 'Doble clic para confirmar cambio' : ''}">${estadoText}</span>
                    </td>
                </tr>
            `;
    }).join('');

  } catch (e) {
    console.error(e);
    tbody.innerHTML = '<tr><td colspan="4" class="text-center py-3 text-danger">Error al cargar historial</td></tr>';
  }
}

// Lógica de Validación de Cambio de Área (Sync)
window.openConfirmarAreaModal = function (historialId, empName, oldArea, newArea) {
  const modalConfirm = document.getElementById('modal-confirmar-area-pendiente');
  if (!modalConfirm) return;

  document.getElementById('area-pending-emp-name').textContent = empName;
  document.getElementById('area-pending-historial-id').value = historialId;
  document.getElementById('area-pending-old').textContent = oldArea || '(Sin área anterior)';
  document.getElementById('area-pending-new').textContent = newArea;
  document.getElementById('area-pending-fecha').value = new Date().toISOString().split('T')[0];
  
  // Reset select de alineación
  document.getElementById('area-pending-align-rule').value = 'custom';
  
  // Cargar turnos compatibles con la nueva área
  loadTurnosForNewArea(newArea);

  // Usar Bootstrap Modal instance
  const bsModal = new bootstrap.Modal(modalConfirm);
  bsModal.show();
}

window.loadTurnosForNewArea = async function(areaName) {
    const turnoSelect = document.getElementById('area-pending-turno');
    if (!turnoSelect) return;

    turnoSelect.innerHTML = '<option value="">⌛ Cargando turnos...</option>';
    console.log(`🔍 Cargando turnos para área: ${areaName}`);
    
    try {
        const resp = await fetch(`${API_BASE_URL}/turnos/?area=${encodeURIComponent(areaName || '')}`);
        if (!resp.ok) throw new Error(`HTTP Error: ${resp.status}`);
        
        const turnos = await resp.json();
        console.log(`✅ Turnos recibidos: ${turnos.length}`);
        
        if (turnos && turnos.length > 0) {
            turnoSelect.innerHTML = '<option value="">-- Seleccionar Turno --</option>';
            turnos.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;

                const tipoPlanificacion = t.tipo_programacion === 'FLEXIBLE_BOLSA'
                    ? 'Flexible (Bolsa de Horas)'
                    : 'Ciclo Inteligente (Smart Match)';
                const horario = t.tipo_programacion === 'DINAMICO_FLEXIBLE'
                    ? '(Múltiples opciones)'
                    : '';

                opt.setAttribute('data-tipo', tipoPlanificacion);
                opt.setAttribute('data-horario', horario);
                opt.textContent = t.nombre;
                turnoSelect.appendChild(opt);
            });
            turnoSelect.removeEventListener('change', window.updateTurnoInfoLabel);
            turnoSelect.addEventListener('change', window.updateTurnoInfoLabel);
            turnoSelect.dispatchEvent(new Event('change'));
        } else {
            console.log("⚠️ No se encontraron turnos específicos. Buscando globales...");
            turnoSelect.innerHTML = '<option value="">⚠️ Sin turnos en esta área</option>';
        }
    } catch (e) {
        console.error("❌ Error cargando turnos para nueva área:", e);
        turnoSelect.innerHTML = '<option value="">❌ Error al cargar turnos</option>';
    } finally {
        // Asegurar que si el dropdown quedó en "Cargando" por un error no controlado, se limpie
        if (turnoSelect.innerHTML.includes('Cargando')) {
            turnoSelect.innerHTML = '<option value="">⚠️ Error de carga (Reintente)</option>';
        }
    }
}

window.applyAlignmentRule = function() {
    const ruleSelect = document.getElementById('area-pending-align-rule');
    const dateInput = document.getElementById('area-pending-fecha');
    if (!ruleSelect || !dateInput) return;
    
    const rule = ruleSelect.value;
    const today = new Date();
    console.log(`📏 Aplicando regla de alineación: ${rule}`);
    
    if (rule === 'today') {
        dateInput.value = today.toISOString().split('T')[0];
    } else if (rule === 'monday') {
        const day = today.getDay(); 
        const diff = (day === 1) ? 0 : (day === 0 ? 1 : 8 - day);
        const nextMonday = new Date();
        nextMonday.setDate(today.getDate() + diff);
        dateInput.value = nextMonday.toISOString().split('T')[0];
    } else if (rule === 'month') {
        dateInput.value = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0];
    } else if (rule === 'next_month') {
        dateInput.value = new Date(today.getFullYear(), today.getMonth() + 1, 1).toISOString().split('T')[0];
    }
}

window.closeConfirmarAreaModal = function () {
  const modalConfirm = document.getElementById('modal-confirmar-area-pendiente');
  if (modalConfirm) {
    const bsModal = bootstrap.Modal.getOrCreateInstance(modalConfirm);
    if (bsModal) bsModal.hide();
  }
}

window.executeConfirmarCambioArea = async function () {
  const historialId = document.getElementById('area-pending-historial-id').value;
  const fecha = document.getElementById('area-pending-fecha').value;
  const turnoId = document.getElementById('area-pending-turno').value;

  if (!fecha) {
    alert("Debe seleccionar una fecha de cambio.");
    return;
  }

  if (!turnoId) {
    alert("Debe seleccionar un turno de la nueva área para completar la transición.");
    return;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/empleados/confirmar-cambio-area/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        historial_id: parseInt(historialId),
        fecha_efectiva: fecha,
        turno_id: parseInt(turnoId)
      })
    });

    if (response.ok) {
      showNotification("Área validada correctamente. La visibilidad ha sido actualizada.", "success");
      closeConfirmarAreaModal();
      // Si el modal de empleado está abierto y es el mismo empleado, recargar historial y area
      if (modal.classList.contains('active') && currentEmpleadoId) {
        loadHistorialAreas(currentEmpleadoId);
        // Actualizar campo de área en Datos Básicos para feedback inmediato
        const areaField = document.getElementById('input-area');
        const newAreaName = document.getElementById('area-pending-new').textContent;
        if (areaField && newAreaName) {
          areaField.value = newAreaName;
        }
      }
      // Recargar lista por si acaso cambió el área actual en la grilla
      loadEmpleados();
    } else {
      const err = await response.json();
      alert("Error: " + (err.detail || "No se pudo validar el área"));
    }
  } catch (e) {
    console.error(e);
    alert("Error de conexión al validar área.");
  }
}

async function openDiagnostico() {
  // Usar bootstrap global si está disponible
  const modalDiagEl = document.getElementById('modal-diagnostico');
  if (!modalDiagEl) return;

  const modalDiag = bootstrap.Modal.getOrCreateInstance(modalDiagEl);

  // Cargar estado inicial
  try {
    const resp = await fetch('/api/configuracion/diagnostico/db-mode/');
    const data = await resp.json();

    const switchDb = document.getElementById('switch-db-mode');
    const badgeDb = document.getElementById('badge-db-mode');

    if (data.mode === 'cloud') {
      switchDb.checked = true;
      badgeDb.textContent = 'Modo Nube Pura';
      badgeDb.className = 'badge bg-warning text-dark';
    } else {
      switchDb.checked = false;
      badgeDb.textContent = 'Modo Híbrido';
      badgeDb.className = 'badge bg-primary';
    }

  } catch (e) {
    console.error("Error cargando modo diagnóstico", e);
  }

  modalDiagEl.removeAttribute('aria-hidden');
  modalDiag.show();
}

window.toggleDbMode = async function () {
  const isCloud = document.getElementById('switch-db-mode').checked;
  const mode = isCloud ? 'cloud' : 'hybrid';

  try {
    const resp = await fetch('/api/configuracion/diagnostico/db-mode/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode })
    });

    if (resp.ok) {
      const badgeDb = document.getElementById('badge-db-mode');
      if (isCloud) {
        badgeDb.textContent = 'Modo Nube Pura';
        badgeDb.className = 'badge bg-warning text-dark';
        alert("✅ CONFIGURACIÓN: Modo Nube Pura ACTIVADO (Lectura directa de Turso)");
      } else {
        badgeDb.textContent = 'Modo Híbrido';
        badgeDb.className = 'badge bg-primary';
        alert("✅ CONFIGURACIÓN: Modo Híbrido RESTAURADO (Lectura local veloz)");
      }
    }
  } catch (e) {
    console.error("Error cambiando modo DB", e);
    alert("Error al cambiar modo de base de datos");
  }
}

async function setSyncSpeed(speed) {
  try {
    const resp = await fetch("/api/sync/speed/" + speed + "/");
    if (resp.ok) {
      alert("Velocidad de sincronización cambiada a: " + speed);
    } else {
      const err = await resp.json();
      alert("Error: " + (err.message || "No se pudo cambiar la velocidad"));
    }
  } catch (e) {
    console.error("Error cambiando velocidad sync", e);
    alert("Error al cambiar velocidad de sincronización");
  }
}

