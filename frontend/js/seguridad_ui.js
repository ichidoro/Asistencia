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
            const fecha = new Date(log.created_at).toLocaleString();
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

            const selfAdminBlock = (user.id === 1) ? `disabled title="El usuario raíz es inmutable"` : '';

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
                    <td>${badgeAcceso}<br><div class="small text-muted mt-1">Acceso: ${user.ultimo_acceso ? new Date(user.ultimo_acceso).toLocaleDateString() : 'Nunca'}</div></td>
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
                        <div class="card-footer bg-white border-top">
                            <button class="btn btn-sm btn-outline-success w-100" ${disableEdit} onclick="editRol(${rol.id})"><i class="bi bi-shield-check me-1"></i>Editar Matriz</button>
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
        // Permisos destructivos o de alto impacto
        'empleados.crear': {
            alert: 'Accion Irreversible',
            flow: 'Abre el modal de creacion de empleado nuevo (boton sobre la lista)'
        },
        'empleados.eliminar': {
            alert: 'Accion Destructiva',
            flow: 'Activa el boton rojo de papelera en la tabla de Empleados'
        },
        'empleados.bonos': {
            alert: 'Riesgo Financiero',
            flow: 'Permite decidir quien recibe bonos y de cuanto dinero'
        },
        'empleados.sincronizar_biometrico': {
            alert: 'Integracion Externa',
            flow: 'Trae empleados desde el reloj BioAlba (boton en el header)'
        },
        'marcaciones.justificar': {
            alert: 'Impacto en Remuneracion',
            flow: 'Permite asignar justificaciones que cambian el estado de asistencia del empleado'
        },
        'marcaciones.bypass_cierre': {
            alert: 'Alerta Contable',
            flow: 'Permite editar asistencia incluso si el mes ya esta bloqueado y cerrado'
        },
        'marcaciones.procesar': {
            alert: 'Calculo Masivo',
            flow: 'Dispara el recalculo de asistencia del periodo desde el modulo Marcaciones'
        },
        'marcaciones.cierre_periodo': {
            alert: 'Cierre Contable',
            flow: 'Bloquea el mes y congela los datos de asistencia para liquidacion'
        },
        'reportes.reprocesar': {
            alert: 'Calculo Masivo',
            flow: 'Dispara el recalculo de asistencia del periodo desde el modulo Reportes'
        },
        'reportes.sincronizar': {
            alert: 'Integracion Externa',
            flow: 'Sincroniza marcaciones BioAlba desde la pantalla de Reportes'
        },
        'configuracion.ver': {
            alert: 'Solo Lectura',
            flow: 'Acceso al módulo de configuración y al panel Robot BioAlba sin poder modificar nada'
        },
        'configuracion.seguridad': {
            alert: 'Riesgo Máximo',
            flow: 'Permite a esta persona crear otros usuarios con cualquier nivel de acceso'
        },
        'configuracion.horarios': {
            alert: 'Impacto Operativo',
            flow: 'Permite crear, editar y eliminar turnos y horarios que afectan a todos los empleados'
        },
        'configuracion.bonos': {
            alert: 'Riesgo Financiero',
            flow: 'Permite crear, editar y eliminar bonos, reglas de cálculo y pagadores'
        },
        'configuracion.justificaciones': {
            alert: 'Impacto en Remuneración',
            flow: 'Permite crear tipos de justificación que determinan si una ausencia es pagada o no'
        },
        'configuracion.calendario': {
            alert: 'Impacto Masivo',
            flow: 'Permite agregar feriados que afectan el cálculo de asistencia de todos los empleados'
        },
        'configuracion.correo': {
            alert: 'Comunicaciones del Sistema',
            flow: 'Permite cambiar servidor SMTP y los destinatarios de notificaciones automáticas'
        },
        'configuracion.estados': {
            alert: 'Lógica de Negocio',
            flow: 'Permite editar los estados de asistencia que clasifican cada marcación del sistema'
        },
        'marcaciones.horas_extras': {
            alert: 'Autorizacion Financiera',
            flow: 'Activa el boton para aprobar que las horas extras se paguen en sueldo'
        }
    };
    return details[permId] || null;
}

function renderMatrizPermisos() {
    const container = document.getElementById('roles-permissions-matrix');
    if (!container) return;

    if (cacheSeguridad.permisos.length === 0) {
        container.innerHTML = '<div class="col-12 text-center text-muted">Cargando catálogo de permisos...</div>';
        return;
    }

    // Agrupar por prefijo (modulo)
    const groups = {};
    cacheSeguridad.permisos.forEach(p => {
        const groupName = p.modulo || 'Otros';
        if (!groups[groupName]) groups[groupName] = [];
        groups[groupName].push(p);
    });

    // Diseño Horizontal/Responsivo
    container.innerHTML = Object.entries(groups).map(([group, perms]) => `
        <div class="col-12 mb-4">
            <div class="card border-0 shadow-sm bg-white" style="border-radius: 12px; overflow: hidden;">
                <div class="card-header bg-light pt-3 pb-2 px-4 border-bottom">
                    <h6 class="fw-bold text-uppercase mb-0 text-primary" style="letter-spacing: 0.5px; font-size: 0.9rem;">
                        <i class="bi bi-shield-lock-fill me-2 opacity-75"></i>Módulo ${group}
                    </h6>
                </div>
                <div class="card-body px-4 pt-3 pb-4">
                    <div class="row g-3">
                    ${perms.map(p => {
                        const simpleId = p.id.split('.')[1] || p.id;
                        const idSafe = p.id.replace(/\\./g, '-');
                        const extra = getPermissionDetails(p.id);
                        
                        const extraHtml = extra ? `
                            <div class="mt-2 p-2 rounded" style="background: #fffbeb; border-left: 3px solid #f59e0b;">
                                <div class="text-danger fw-bold mb-1" style="font-size:0.7rem;"><i class="bi bi-exclamation-triangle-fill me-1"></i>${extra.alert}</div>
                                <div class="text-secondary font-monospace d-flex align-items-center" style="font-size:0.65rem; line-height: 1.2;">
                                    <i class="bi bi-arrow-return-right text-primary me-1"></i> ${extra.flow}
                                </div>
                            </div>
                        ` : '';

                        return `
                            <div class="col-md-6 col-lg-4">
                                <label class="d-flex gap-2 p-3 border rounded shadow-sm cell-clickable h-100 m-0" for="perm-${idSafe}" style="background: #f8fafc; cursor: pointer; transition: all 0.2s;">
                                    <input class="form-check-input perm-check flex-shrink-0 mt-1 shadow-none" type="checkbox" value="${p.id}" id="perm-${idSafe}" style="width: 1.25rem; height: 1.25rem; cursor: pointer;">
                                    <div class="w-100">
                                        <div class="fw-bold text-dark mb-1" style="text-transform: capitalize; font-size: 0.9rem;">${simpleId.replace(/_/g, ' ')}</div>
                                        <div class="text-muted" style="font-size:0.8rem; line-height: 1.3;">${p.descripcion}</div>
                                        ${extraHtml}
                                    </div>
                                </label>
                            </div>
                        `;
                    }).join('')}
                    </div>
                </div>
            </div>
        </div>
    `).join('');
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
        const checks = document.querySelectorAll('.perm-check');
        console.log(`Marcando ${activePerms.length} permisos en ${checks.length} checkboxes`);

        checks.forEach(ck => {
            ck.checked = activePerms.includes(ck.value);
        });
    }, 50);

    if (modalRolInstance) modalRolInstance.show();
}

window.saveRol = async function () {
    const rolId = document.getElementById('rol-id').value;
    const selectedPerms = Array.from(document.querySelectorAll('.perm-check:checked')).map(ck => ck.value);

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
