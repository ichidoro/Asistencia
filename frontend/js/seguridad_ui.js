/**
 * Control de Acceso al Módulo de Seguridad
 */
(function() {
    if (window.location.pathname.endsWith('index.html') || window.location.pathname === '/') {
        return;
    }

    const userData = localStorage.getItem('user');
    if (!userData) return;

    const isAuthorized = typeof AuthService !== 'undefined'
        ? AuthService.hasPermission('configuracion.seguridad')
        : JSON.parse(userData)?.is_superuser === true;

    if (!isAuthorized) {
        console.error("🚫 Acceso denegado al módulo de Seguridad: permiso 'configuracion.seguridad' requerido.");
        alert("Acceso Restringido: Se requiere permiso de Seguridad.");
        window.location.href = 'index.html';
        return;
    }
    console.log("🛡️ Acceso concedido al módulo de Seguridad.");
})();

// ==========================================
// Módulo de Consola de Seguridad UI (Integrado)
// ==========================================

let cacheSeguridad = {
    roles: [],
    permisos: [],
    usuarios: [],
    areas: []
};

const MAPA_UI_PERMISOS = {
    // ── MÓDULO DASHBOARD (1) ──
    'dashboard.ver':           { module: 'DASHBOARD', action: 'Ver',           description: 'Ver el dashboard analítico de asistencia y fuerza laboral (Lectura)', permissions: ['dashboard.ver'] },

    // ── MÓDULO EMPLEADOS (7) ──
    'empleados.ver':           { module: 'EMPLEADOS', action: 'Ver',           description: 'Ver lista general de empleados, cumpleaños y turnos asignados (Lectura)', permissions: ['empleados.ver'] },
    'empleados.crear':         { module: 'EMPLEADOS', action: 'Crear',         description: 'Crear nuevos empleados (Botón "+ Nuevo Empleado")',                       permissions: ['empleados.crear'] },
    'empleados.editar':        { module: 'EMPLEADOS', action: 'Editar',        description: 'Editar ficha personal, renovar/gestionar contratos y registrar bajas',     permissions: ['empleados.editar'] },
    'empleados.eliminar':      { module: 'EMPLEADOS', action: 'Eliminar',      description: 'Eliminar de forma permanente empleados y su historial del sistema',        permissions: ['empleados.eliminar'] },
    'empleados.reincorporar':  { module: 'EMPLEADOS', action: 'Reincorporar',  description: 'Reincorporar y reactivar empleados inactivos (Asistente con BioAlba)',      permissions: ['empleados.reincorporar'] },
    'empleados.bonos':         { module: 'EMPLEADOS', action: 'Bonos',         description: 'Ver matriz informativa de bonos asignados (Lectura)',                      permissions: ['empleados.bonos'] },
    'empleados.horarios':      { module: 'EMPLEADOS', action: 'Horarios',      description: 'Asignación masiva/individual de turnos y corrección de fecha inicial',     permissions: ['empleados.horarios'] },

    // ── MÓDULO MARCACIONES (7) ──
    'marcaciones.ver':           { module: 'MARCACIONES', action: 'Ver',           description: 'Ver grilla, calendarios e historial',           permissions: ['marcaciones.ver'] },
    'marcaciones.editar':        { module: 'MARCACIONES', action: 'Editar',        description: 'Editar horas, relleno masivo, tramos, perdonazo', permissions: ['marcaciones.editar'] },
    'marcaciones.justificar':    { module: 'MARCACIONES', action: 'Justificar',    description: 'Crear y editar justificaciones de asistencia',  permissions: ['marcaciones.justificar'] },
    'marcaciones.horas_extras':  { module: 'MARCACIONES', action: 'Horas Extras',  description: 'Aprobar/rechazar horas extras',                 permissions: ['marcaciones.horas_extras'] },
    'marcaciones.cierre_periodo':{ module: 'MARCACIONES', action: 'Cierre',        description: 'Cerrar y sellar período ⚠️ Contable',           permissions: ['marcaciones.cierre_periodo'] },
    'marcaciones.bypass_cierre': { module: 'MARCACIONES', action: 'Bypass Cierre', description: 'Editar meses ya cerrados ⚠️ Alto Riesgo',       permissions: ['marcaciones.bypass_cierre'] },
    'marcaciones.sincronizar':   { module: 'MARCACIONES', action: 'Sincronizar',   description: 'Sincronizar y reprocesar desde toolbar',        permissions: ['marcaciones.sincronizar'] },
    'marcaciones.intercambio':   { module: 'MARCACIONES', action: 'Días Compensatorios', description: 'Registrar y revertir intercambios de días (1x1)', permissions: ['marcaciones.intercambio'] },
    'marcaciones.compensar':     { module: 'MARCACIONES', action: 'Compensar Inasistencias', description: 'Compensar inasistencias usando horas extras aprobadas', permissions: ['marcaciones.compensar'] },


    // ── MÓDULO REPORTES (4) ──
    'reportes.ver':         { module: 'REPORTES', action: 'Ver',         description: 'Ver tablas y gráficos de reportes',    permissions: ['reportes.ver'] },
    'reportes.exportar':    { module: 'REPORTES', action: 'Exportar',    description: 'Descargar Excel',                      permissions: ['reportes.exportar'] },
    'reportes.reprocesar':  { module: 'REPORTES', action: 'Reprocesar',  description: 'Disparar motor de cálculo',            permissions: ['reportes.reprocesar'] },
    'reportes.sincronizar': { module: 'REPORTES', action: 'Sincronizar', description: 'Sincronizar BioAlba desde reportes',   permissions: ['reportes.sincronizar'] },

    // ── MÓDULO CONFIGURACIÓN (10) ──
    'configuracion.ver':            { module: 'CONFIGURACIÓN', action: 'Ver',            description: 'Ver todas las pestañas de configuración',       permissions: ['configuracion.ver'] },
    'configuracion.horarios':       { module: 'CONFIGURACIÓN', action: 'Horarios',       description: 'Crear/editar/eliminar turnos',                  permissions: ['configuracion.horarios'] },
    'configuracion.bonos':          { module: 'CONFIGURACIÓN', action: 'Bonos',          description: 'Crear/editar/eliminar bonos y pagadores',       permissions: ['configuracion.bonos'] },
    'configuracion.justificaciones':{ module: 'CONFIGURACIÓN', action: 'Justificaciones',description: 'Crear/editar/eliminar tipos de justificación',  permissions: ['configuracion.justificaciones'] },
    'configuracion.calendario':     { module: 'CONFIGURACIÓN', action: 'Calendario',     description: 'Gestionar feriados',                            permissions: ['configuracion.calendario'] },
    'configuracion.correo':         { module: 'CONFIGURACIÓN', action: 'Correo',         description: 'Configurar SMTP y alertas por área',            permissions: ['configuracion.correo'] },
    'configuracion.estados':        { module: 'CONFIGURACIÓN', action: 'Estados',        description: 'Editar estados de asistencia',                  permissions: ['configuracion.estados'] },
    'configuracion.seguridad':      { module: 'CONFIGURACIÓN', action: 'Seguridad',      description: 'Gestionar usuarios y roles ⚠️ Riesgo Máximo',   permissions: ['configuracion.seguridad'] },
    'configuracion.wizard':         { module: 'CONFIGURACIÓN', action: 'Wizard',         description: '🧙 Wizard de Inicialización BioAlba (header)',   permissions: ['configuracion.wizard'] },
    'configuracion.sistema':        { module: 'CONFIGURACIÓN', action: 'Sistema',        description: 'Diagnóstico de BD y modo ⚠️ Solo Admin',        permissions: ['configuracion.sistema'] },

    // ── MÓDULO 4 PRODUCTOS (4) ──
    'productos_4.asignar':          { module: '4 PRODUCTOS', action: 'Asignar',          description: 'Ver y asignar 4 Productos a empleados (con RLS de área)', permissions: ['productos_4.asignar'] },
    'productos_4.consolidar':       { module: '4 PRODUCTOS', action: 'Consolidar',       description: 'Ver consolidado global de productos propios (sin RLS)', permissions: ['productos_4.consolidar'] },
    'productos_4.entregar':         { module: '4 PRODUCTOS', action: 'Entregar',         description: 'Ver y registrar entregas de productos propios (sin RLS)', permissions: ['productos_4.entregar'] },
    'productos_4.catalogo':         { module: '4 PRODUCTOS', action: 'Catálogo',         description: 'Ver y gestionar el catálogo de productos propios en Configuración', permissions: ['productos_4.catalogo'] },

    // ── MÓDULO PORTERÍA (3) ──
    'porteria.ver':                 { module: 'PORTERÍA', action: 'Ver Historial',  description: 'Ver el historial de rondas nocturnas y fotos de hallazgos (Lectura)', permissions: ['porteria.ver'] },
    'porteria.registrar':           { module: 'PORTERÍA', action: 'Registrar',      description: 'Registrar pasos por puntos de control y reportar hallazgos (Guardia)', permissions: ['porteria.registrar'] },
    'porteria.editar':              { module: 'PORTERÍA', action: 'Editar / Configurar', description: 'Gestionar el catálogo de anomalías/hallazgos y configurar puntos de control', permissions: ['porteria.editar'] },
};

// Modales persistentes (instancias Bootstrap)
let modalUserInstance = null;
let modalRolInstance = null;

function initSeguridadUI() {
    console.log("🛡️ Iniciando Consola de Seguridad");

    // Inicializar instancias si es posible
    ensureModalInstances();

    switchSeguridadTab('auditoria'); // Tab por defecto
    loadPermisosMaestros(); // Cargar catálogo base de permisos (fondo)
    loadAreasParaSeguridad(); // Cargar áreas para RLS
    loadRoles(); // CRÍTICO: Cargar roles para que estén disponibles en el modal de usuario
}

function ensureModalInstances() {
    if (typeof bootstrap !== 'undefined') {
        if (!modalUserInstance) {
            const mUser = document.getElementById('modalUsuario');
            if (mUser) modalUserInstance = new bootstrap.Modal(mUser);
        }
        if (!modalRolInstance) {
            const mRol = document.getElementById('modalRol');
            if (mRol) modalRolInstance = new bootstrap.Modal(mRol);
        }
    }
}

function switchSeguridadTab(tabName) {
    // 1. Activar botón (dentro de tab-seguridad)
    document.querySelectorAll('#tab-seguridad .tab-btn').forEach(b => b.classList.remove('active'));
    const targetBtn = document.querySelector(`#tab-seguridad .tab-btn[data-tab="${tabName}"]`);
    if (targetBtn) targetBtn.classList.add('active');

    // 2. Mostrar vista
    document.querySelectorAll('#tab-seguridad .seguridad-view').forEach(v => v.style.display = 'none');
    const targetView = document.getElementById(`vista-seguridad-${tabName}`);
    if (targetView) targetView.style.display = 'block';

    // 3. Cargar datos si procede
    if (tabName === 'auditoria') loadAuditoria();
    else if (tabName === 'usuarios') loadUsuarios();
    else if (tabName === 'roles') loadRoles();
}

// Hook para inicialización controlada
window.initSeguridadUI = initSeguridadUI;
window.switchSeguridadTab = switchSeguridadTab;
window.loadAuditoria = loadAuditoria;
window.loadUsuarios = loadUsuarios;
window.loadRoles = loadRoles;

async function loadPermisosMaestros() {
    try {
        const res = await fetch('/api/seguridad/permisos/');
        if (res.ok) {
            cacheSeguridad.permisos = await res.json();
            renderMatrizPermisos(); // Renderizar preliminarmente
        }
    } catch (e) {
        console.error("Error cargando permisos:", e);
    }
}

async function loadAreasParaSeguridad() {
    try {
        const res = await fetch('/api/empleados/areas/');
        if (res.ok) {
            cacheSeguridad.areas = await res.json();
        }
    } catch (e) {
        console.error("Error cargando áreas:", e);
    }
}

// ================== AUDITORÍA ==================
async function loadAuditoria() {
    const tbody = document.getElementById('table-auditoria');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4"><span class="spinner-border spinner-border-sm"></span> Extrayendo Bitácora Inmutable...</td></tr>';

    try {
        const response = await fetch('/api/seguridad/auditoria/?limit=200');
        if (!response.ok) throw new Error('Error al cargar auditoría');

        const data = await response.json();
        const logs = data.data;

        if (logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4">Sin registros de auditoría</td></tr>';
            return;
        }

        tbody.innerHTML = logs.map(log => {
            const d = new Date(log.created_at);
            let fecha = 'N/A';
            if (!isNaN(d.getTime())) {
                const formattedDatePart = window.formatFechaDDMMYYYY(d);
                const timePart = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
                fecha = `${formattedDatePart} ${timePart}`;
            }
            let badgeColor = 'bg-secondary';
            if (log.accion === 'CREATE' || log.accion === 'LOGIN') badgeColor = 'bg-success';
            if (log.accion === 'UPDATE') badgeColor = 'bg-warning text-dark';
            if (log.accion === 'DELETE') badgeColor = 'bg-danger';
            if (log.detalle?.includes('intentó') || log.detalle?.includes('403')) badgeColor = 'bg-danger shadow-sm border border-dark';

            return `
                <tr>
                    <td class="small text-muted">${fecha}</td>
                    <td class="fw-bold">${log.username} <span class="badge bg-light text-dark border">ID:${log.usuario_id}</span></td>
                    <td><span class="badge ${badgeColor}">${log.accion}</span></td>
                    <td class="fw-bold text-secondary">${log.modulo}</td>
                    <td class="small" style="max-width:300px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${log.detalle || ''}">${log.detalle || '-'}</td>
                    <td class="text-muted font-monospace small">${log.ip_address || '127.0.0.1'}</td>
                </tr>
            `;
        }).join('');
    } catch (error) {
        console.error(error);
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-4">🔒 Error de Acceso a Bitácora. Privilegios Insuficientes.</td></tr>`;
    }
}

// ================== USUARIOS ==================
async function loadUsuarios() {
    const tbody = document.getElementById('table-usuarios');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4"><span class="spinner-border spinner-border-sm"></span> Cargando Fuerza Laboral...</td></tr>';

    try {
        const response = await fetch('/api/seguridad/usuarios/');
        if (!response.ok) throw new Error('Error Cargando Usuarios');

        cacheSeguridad.usuarios = await response.json();

        tbody.innerHTML = cacheSeguridad.usuarios.map(user => {
            const badgeAcceso = user.activo
                ? '<span class="badge bg-success"><i class="bi bi-check-circle me-1"></i>Activo</span>'
                : '<span class="badge bg-danger"><i class="bi bi-x-circle me-1"></i>Bloqueado</span>';
            const badgeDios = user.is_superuser
                ? '<span class="badge bg-dark mt-1"><i class="fa-solid fa-crown text-warning me-1"></i>Súper Admin / God Mode</span>'
                : '';

            let areasHtml = user.alcance_global || user.is_superuser
                ? '<span class="badge bg-primary">Global (Ve Todo)</span>'
                : user.areas?.map(a => `<span class="badge bg-info text-dark me-1">${a}</span>`).join('') || '<span class="badge bg-secondary">Sin Áreas Acceso</span>';

            const selfAdminBlock = (user.id === 9) ? `disabled title="El usuario raíz es inmutable"` : '';

            return `
                <tr>
                    <td>
                        <div class="fw-bold">${user.username}</div>
                        <div class="small text-muted">ID: ${user.id}</div>
                    </td>
                    <td>
                        <div>${user.nombre_completo}</div>
                        <div class="small text-muted">${user.email || 'Sin correo'}</div>
                    </td>
                    <td>
                        <span class="badge bg-secondary">${user.rol_nombre.toUpperCase()}</span>
                        <div>${badgeDios}</div>
                    </td>
                    <td>${areasHtml}</td>
                    <td>${badgeAcceso}<br><div class="small text-muted mt-1">Acceso: ${user.ultimo_acceso ? window.formatFechaDDMMYYYY(user.ultimo_acceso) : 'Nunca'}</div></td>
                    <td class="text-end">
                        <button class="btn btn-sm btn-outline-primary" ${selfAdminBlock} onclick="editUsuario(${user.id})"><i class="bi bi-pencil"></i></button>
                    </td>
                </tr>
            `;
        }).join('');
    } catch (error) {
        console.error(error);
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-4">🔒 Error de Acceso.</td></tr>`;
    }
}

// Modales Usuarios
window.openUserModal = function () {
    ensureModalInstances();
    const title = document.getElementById('modalUsuarioTitle');
    if (title) title.textContent = "👤 Nuevo Usuario Operador";
    document.getElementById('formUsuario').reset();
    document.getElementById('user-id').value = "";
    document.getElementById('user-username').disabled = false;
    document.getElementById('user-password').required = true;
    const pwHint = document.getElementById('user-pw-hint');
    if (pwHint) pwHint.textContent = "Contraseña inicial requerida.";

    populateUserModal();
    if (modalUserInstance) modalUserInstance.show();
}

function populateUserModal() {
    // Roles - Usar cacheSeguridad.roles (debe estar cargado por loadRoles)
    const selRol = document.getElementById('user-rol');
    if (selRol) {
        if (cacheSeguridad.roles.length === 0) {
            selRol.innerHTML = '<option value="">Cargando roles...</option>';
        } else {
            selRol.innerHTML = cacheSeguridad.roles.map(r => `<option value="${r.id}">${r.nombre}</option>`).join('');
        }
    }

    // Áreas (RLS)
    const chips = document.getElementById('user-areas-chips');
    if (chips) {
        if (cacheSeguridad.areas.length === 0) {
            chips.innerHTML = '<div class="text-muted small">Cargando áreas...</div>';
        } else {
            chips.innerHTML = cacheSeguridad.areas.map(a => `
                <div class="form-check form-check-inline">
                    <input class="form-check-input area-check" type="checkbox" value="${a}" id="area-${a.replace(/\s+/g, '-')}">
                    <label class="form-check-label small" for="area-${a.replace(/\s+/g, '-')}">${a}</label>
                </div>
            `).join('');
        }
    }
}

window.editUsuario = function (id) {
    const user = cacheSeguridad.usuarios.find(u => u.id === id);
    if (!user) return;

    document.getElementById('modalUsuarioTitle').textContent = `👤 Editando: ${user.username}`;
    document.getElementById('user-id').value = user.id;
    document.getElementById('user-username').value = user.username;
    document.getElementById('user-username').disabled = true;
    document.getElementById('user-nombre').value = user.nombre_completo;
    document.getElementById('user-email').value = user.email || "";
    document.getElementById('user-password').value = "";
    document.getElementById('user-password').required = false;
    document.getElementById('user-pw-hint').textContent = "Dejar vacío para mantener contraseña actual.";
    document.getElementById('user-activo').value = user.activo ? "1" : "0";

    // Poblar y LUEGO asignar valor
    populateUserModal();

    // Pequeño delay o asignación directa si ya hay roles
    if (cacheSeguridad.roles.length > 0) {
        document.getElementById('user-rol').value = user.rol_id;
    } else {
        // Fallback: intentar asignar cuando terminen de cargar (raro pero posible)
        setTimeout(() => {
            document.getElementById('user-rol').value = user.rol_id;
        }, 500);
    }

    // Check areas
    const user_areas = user.areas || [];
    setTimeout(() => {
        document.querySelectorAll('.area-check').forEach(ck => {
            ck.checked = user_areas.includes(ck.value);
        });
    }, 50);

    if (modalUserInstance) modalUserInstance.show();
}

window.saveUsuario = async function () {
    const userId = document.getElementById('user-id').value;
    const areasSelected = Array.from(document.querySelectorAll('.area-check:checked')).map(ck => ck.value);

    const payload = {
        username: document.getElementById('user-username').value,
        nombre_completo: document.getElementById('user-nombre').value,
        email: document.getElementById('user-email').value,
        rol_id: parseInt(document.getElementById('user-rol').value),
        activo: document.getElementById('user-activo').value === "1",
        areas: areasSelected
    };

    const password = document.getElementById('user-password').value;
    if (password) payload.password = password;

    try {
        const method = userId ? 'PUT' : 'POST';
        const url = userId ? `/api/seguridad/usuarios/${userId}/` : '/api/seguridad/usuarios/';

        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            Swal.fire('Éxito', userId ? 'Usuario actualizado' : 'Usuario creado', 'success');
            if (modalUserInstance) modalUserInstance.hide();
            loadUsuarios();
        } else {
            const err = await res.json();
            Swal.fire('Error', err.detail || 'No se pudo guardar', 'error');
        }
    } catch (e) {
        Swal.fire('Error', 'Fallo de conexión', 'error');
    }
}

// ================== ROLES ==================
async function loadRoles() {
    const grid = document.getElementById('roles-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="col-12 text-center py-5"><span class="spinner-border spinner-border-sm"></span> Calculando Matriz RBAC...</div>';

    try {
        const response = await fetch('/api/seguridad/roles/');
        if (!response.ok) throw new Error('Error al cargar roles');

        cacheSeguridad.roles = await response.json();

        grid.innerHTML = cacheSeguridad.roles.map(rol => {
            const esGlobal = rol.alcance_global ? '<span class="badge bg-primary">Alcance Global</span>' : '<span class="badge bg-secondary">Alcance Zonal</span>';
            const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
            const disableEdit = (rol.id === 1 && !currentUser.is_superuser) ? 'disabled title="Solo el Súper Admin puede modificar este rol"' : '';

            return `
                <div class="col-md-6 p-2">
                    <div class="card h-100 border shadow-sm">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <h5 class="fw-bold text-primary mb-0">${rol.nombre}</h5>
                                <span class="badge bg-dark">${rol.permisos.length} Permisos</span>
                            </div>
                            <p class="text-muted small mb-3">${rol.descripcion || 'Sin descripción'}</p>
                            <div class="mb-3">${esGlobal}</div>
                            <h6 class="fw-bold small">Permisos:</h6>
                            <div class="d-flex flex-wrap gap-1" style="max-height: 160px; overflow-y: auto;">
                                ${rol.permisos.map(p => `<span class="badge bg-light text-dark border" style="font-size:0.7rem">${p}</span>`).join('')}
                            </div>
                        </div>
                        <div class="card-footer bg-white border-top d-flex gap-2">
                            <button class="btn btn-sm btn-outline-success flex-grow-1" ${disableEdit} onclick="editRol(${rol.id})"><i class="bi bi-shield-check me-1"></i>Editar Matriz</button>
                            <button class="btn btn-sm btn-outline-danger" ${rol.id === 1 ? 'disabled title="El Rol Maestro es inmutable"' : ''} onclick="deleteRol(${rol.id})"><i class="bi bi-trash"></i></button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

    } catch (error) {
        console.error(error);
        grid.innerHTML = `<div class="col-12 text-center text-danger py-5">🔒 Error de Acceso a Roles.</div>`;
    }
}

function getPermissionDetails(permId) {
    const details = {
        // Dashboard
        'dashboard.ver':           { alert: 'Ubicación: Menú lateral (Dashboard)',   flow: 'Visualizar métricas diarias, KPIs de paridad, edades y productividad.' },
        // Empleados
        'empleados.ver':           { alert: 'Ubicación: Menú lateral y pestañas',   flow: 'Visualizar lista general, visor de turnos y cumpleaños (Lectura).' },
        'empleados.crear':         { alert: 'Ubicación: Botón "+ Nuevo Empleado"',  flow: 'Habilitar el botón de cabecera para abrir la modal de creación.' },
        'empleados.editar':        { alert: 'Ubicación: Lista, Ficha y Contratos',  flow: 'Editar datos personales, dar de baja, renovar o pasar contratos a indefinido.' },
        'empleados.eliminar':      { alert: 'Ubicación: Lista (Papelera roja)',     flow: 'Borrado físico definitivo e irreversible del empleado y su historial (Destructiva).' },
        'empleados.reincorporar':  { alert: 'Ubicación: Lista (Fila de inactivos)',  flow: 'Iniciar asistente con BioAlba para reactivar y recontratar empleado.' },
        'empleados.bonos':         { alert: 'Ubicación: Pestaña Bonos Asignados',   flow: 'Visualización de la matriz de bonos activos. Nota: Es de sólo lectura.' },
        'empleados.horarios':      { alert: 'Ubicación: Lista y Asignación Masiva', flow: 'Asignar turnos masivo/individual y corregir fecha inicial (doble-clic).' },
        // Marcaciones
        'marcaciones.justificar':    { alert: 'Impacto en Remuneración',  flow: 'Justificaciones que cambian el estado de asistencia' },
        'marcaciones.bypass_cierre': { alert: 'Alerta Contable',          flow: 'Editar asistencia incluso si el mes ya está bloqueado' },
        'marcaciones.cierre_periodo':{ alert: 'Cierre Contable',          flow: 'Congela datos de asistencia para liquidación' },
        'marcaciones.horas_extras':  { alert: 'Autorización Financiera',  flow: 'Aprobar que las horas extras se paguen en sueldo' },
        'marcaciones.sincronizar':   { alert: 'Integración BioAlba',     flow: 'Descarga marcaciones y reprocesar asistencia masivamente' },
        'marcaciones.intercambio':   { alert: 'Operativo',                flow: 'Intercambiar un día de descanso trabajado por un día laboral libre (1x1)' },
        'marcaciones.compensar':     { alert: 'Operativo',                flow: 'Compensar inasistencias con saldos de horas extras aprobadas' },

        // Reportes
        'reportes.reprocesar':  { alert: 'Cálculo Masivo',        flow: 'Dispara recálculo de asistencia desde Reportes' },
        'reportes.sincronizar': { alert: 'Integración Externa',   flow: 'Sincroniza marcaciones BioAlba desde Reportes' },
        // Configuración
        'configuracion.ver':            { alert: 'Solo Lectura',          flow: 'Acceso al módulo sin poder modificar nada' },
        'configuracion.seguridad':      { alert: 'Riesgo Máximo',         flow: 'Puede crear usuarios con cualquier nivel de acceso' },
        'configuracion.horarios':       { alert: 'Impacto Operativo',     flow: 'Turnos y horarios afectan a todos los empleados' },
        'configuracion.bonos':          { alert: 'Riesgo Financiero',     flow: 'Crear/editar bonos, reglas de cálculo y pagadores' },
        'configuracion.justificaciones':{ alert: 'Impacto en Remuneración', flow: 'Tipos que determinan si una ausencia es pagada' },
        'configuracion.calendario':     { alert: 'Impacto Masivo',        flow: 'Feriados afectan el cálculo de todos los empleados' },
        'configuracion.correo':         { alert: 'Comunicaciones',        flow: 'Cambiar servidor SMTP y destinatarios de alertas' },
        'configuracion.estados':        { alert: 'Lógica de Negocio',     flow: 'Estados que clasifican cada marcación del sistema' },
        'configuracion.wizard':         { alert: 'Setup del Sistema',     flow: 'Wizard de inicialización que conecta BioAlba' },
        'configuracion.sistema':        { alert: 'Solo Admin',            flow: 'Diagnóstico de BD, modo de conexión y velocidad' },

        // 4 Productos
        'productos_4.asignar':          { alert: 'Ubicación: Menú lateral / Tab Asignación', flow: 'Visualizar planilla de habilitados y asignar productos a empleados (con RLS de área).' },
        'productos_4.consolidar':       { alert: 'Ubicación: Menú lateral / Tab Consolidado', flow: 'Ver consolidado global acumulado por producto (sin RLS).' },
        'productos_4.entregar':         { alert: 'Ubicación: Menú lateral / Tab Entrega Beneficio', flow: 'Ver listado y registrar entregas físicas de productos (sin RLS).' },
        'productos_4.catalogo':         { alert: 'Ubicación: Configuración / Catálogo Propio', flow: 'Ver y administrar el catálogo de productos de elaboración propia.' },

        // Portería
        'porteria.ver':                 { alert: 'Ubicación: Menú lateral / Portería', flow: 'Ver el historial de rondas nocturnas y fotos de hallazgos (Lectura).' },
        'porteria.registrar':           { alert: 'Ubicación: Menú lateral / Portería', flow: 'Registrar pasos por puntos de control y reportar hallazgos (Guardia).' },
        'porteria.editar':              { alert: 'Ubicación: Configuración / Catálogo de Hallazgos', flow: 'Gestionar el catálogo de anomalías/hallazgos y configurar puntos de control.' },
    };
    return details[permId] || null;
}

function renderMatrizPermisos() {
    const container = document.getElementById('roles-permissions-matrix');
    if (!container) return;

    // Group by module
    const modules = {};
    Object.keys(MAPA_UI_PERMISOS).forEach(key => {
        const item = MAPA_UI_PERMISOS[key];
        if (!modules[item.module]) {
            modules[item.module] = [];
        }
        modules[item.module].push({ key, ...item });
    });

    // Module icons
    const moduleIcons = {
        'DASHBOARD': '📊',
        'EMPLEADOS': '👥',
        'MARCACIONES': '🕐',
        'REPORTES': '📊',
        'CONFIGURACIÓN': '⚙️',
        '4 PRODUCTOS': '🎁',
        'PORTERÍA': '🛡️'
    };

    // Render HTML
    container.innerHTML = Object.entries(modules).map(([moduleName, items]) => {
        const cardsHtml = items.map(item => {
            const idSafe = item.key.replace('.', '-');
            const details = getPermissionDetails(item.key);
            
            let alertHtml = '';
            if (details && details.alert) {
                alertHtml = `
                    <div class="mt-2 px-2 py-1 rounded" style="font-size: 0.72rem; background-color: #fef3c7; border-left: 3px solid #f59e0b;">
                        <strong style="color: #b45309;">⚠️ ${details.alert}</strong>
                        <div class="text-muted" style="font-size: 0.7rem; line-height: 1.3;">${details.flow}</div>
                    </div>
                `;
            }

            return `
                <div class="col-md-4 col-lg-3">
                    <div class="d-flex align-items-start gap-2 p-3 border rounded shadow-sm h-100" style="background: #f8fafc; transition: all 0.2s;">
                        <input class="form-check-input perm-ui-check flex-shrink-0 mt-1" type="checkbox" value="${item.key}" id="perm-ui-${idSafe}" style="width: 1.15rem; height: 1.15rem; cursor: pointer;">
                        <div class="w-100">
                            <label class="form-check-label fw-bold text-dark mb-1" for="perm-ui-${idSafe}" style="font-size: 0.9rem; cursor: pointer;">
                                ${item.action}
                            </label>
                            <div class="text-muted" style="font-size: 0.78rem; line-height: 1.3;">
                                ${item.description}
                            </div>
                            ${alertHtml}
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        return `
            <div class="col-12 mb-4">
                <div class="card border-0 shadow-sm bg-white" style="border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0 !important;">
                    <div class="card-header bg-white pt-3 pb-2 px-4 border-bottom-0">
                        <h6 class="fw-bold mb-0 text-primary d-flex align-items-center" style="font-size: 0.95rem; color: #0d6efd !important;">
                            <span class="me-2">${moduleIcons[moduleName] || '🛡️'}</span>MÓDULO ${moduleName}
                            <span class="badge bg-light text-secondary ms-2" style="font-size: 0.7rem;">${items.length} permisos</span>
                        </h6>
                    </div>
                    <div class="card-body px-4 pt-2 pb-4">
                        <div class="row g-3">
                            ${cardsHtml}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

window.openRolModal = function () {
    ensureModalInstances();
    const title = document.getElementById('modalRolTitle');
    if (title) title.textContent = "🔑 Nuevo Rol de Seguridad";
    document.getElementById('formRol').reset();
    document.getElementById('rol-id').value = "";

    renderMatrizPermisos();
    if (modalRolInstance) modalRolInstance.show();
}


window.editRol = function (id) {
    const rol = cacheSeguridad.roles.find(r => r.id === id);
    if (!rol) {
        console.error("Rol no encontrado:", id);
        return;
    }

    console.log(`Editando Rol: ${rol.nombre}`, rol.permisos);

    document.getElementById('modalRolTitle').textContent = `🔑 Editando Matriz: ${rol.nombre}`;
    document.getElementById('rol-id').value = rol.id;
    document.getElementById('rol-nombre').value = rol.nombre;
    document.getElementById('rol-descripcion').value = rol.descripcion || "";
    document.getElementById('rol-global').value = rol.alcance_global ? "1" : "0";

    renderMatrizPermisos();

    // Pequeño delay para asegurar que el DOM de la matriz se renderizó antes de marcar
    setTimeout(() => {
        const activePerms = rol.permisos || [];
        console.log(`Marcando permisos en UI checkboxes para activePerms:`, activePerms);

        Object.keys(MAPA_UI_PERMISOS).forEach(key => {
            const idSafe = key.replace('.', '-');
            const ck = document.getElementById(`perm-ui-${idSafe}`);
            if (ck) {
                // 1:1 mapping: el key del checkbox ES el permiso
                ck.checked = activePerms.includes(key);
            }
        });
    }, 50);

    if (modalRolInstance) modalRolInstance.show();
}

window.saveRol = async function () {
    const rolId = document.getElementById('rol-id').value;
    
    // 1:1 mapping: cada checkbox checked = 1 permiso exacto
    const selectedPerms = [];
    Object.keys(MAPA_UI_PERMISOS).forEach(key => {
        const idSafe = key.replace('.', '-');
        const ck = document.getElementById(`perm-ui-${idSafe}`);
        if (ck && ck.checked) {
            selectedPerms.push(key); // key = permiso backend
        }
    });

    const payload = {
        nombre: document.getElementById('rol-nombre').value,
        descripcion: document.getElementById('rol-descripcion').value,
        alcance_global: document.getElementById('rol-global').value === "1",
        permisos: selectedPerms
    };

    try {
        const method = rolId ? 'PUT' : 'POST';
        const url = rolId ? `/api/seguridad/roles/${rolId}/` : '/api/seguridad/roles/';

        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            Swal.fire('Éxito', 'Rol guardado correctamente', 'success');
            if (modalRolInstance) modalRolInstance.hide();
            loadRoles();
        } else {
            const err = await res.json();
            Swal.fire('Error', err.detail || 'Fallo al guardar rol', 'error');
        }
    } catch (e) {
        Swal.fire('Error', 'Fallo de red', 'error');
    }
}

window.deleteRol = async function (id) {
    const rol = cacheSeguridad.roles.find(r => r.id === id);
    if (!rol) return;

    const result = await Swal.fire({
        title: '¿Confirmar eliminación?',
        text: `¿Está seguro de que desea eliminar el rol "${rol.nombre}"? Esta acción no se puede deshacer y fallará si hay usuarios asociados.`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#3085d6',
        confirmButtonText: 'Sí, eliminar',
        cancelButtonText: 'Cancelar'
    });

    if (result.isConfirmed) {
        try {
            const res = await fetch(`/api/seguridad/roles/${id}/`, {
                method: 'DELETE'
            });

            if (res.ok) {
                Swal.fire('Eliminado', 'El rol ha sido eliminado exitosamente.', 'success');
                loadRoles();
            } else {
                const err = await res.json();
                Swal.fire('Error', err.detail || 'No se pudo eliminar el rol.', 'error');
            }
        } catch (e) {
            Swal.fire('Error', 'Fallo de red al intentar eliminar el rol.', 'error');
        }
    }
}

