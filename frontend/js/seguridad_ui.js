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
        window.location.href = '/';
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

    // ── MÓDULO CONFIGURACIÓN (11) ──
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
    'configuracion.flota':          { module: 'CONFIGURACIÓN', action: 'Pestaña Flota',     description: 'Gestionar vehículos de la flota (CRUD) de Aguacol', permissions: ['configuracion.flota'] },
    'configuracion.editar':         { module: 'CONFIGURACIÓN', action: 'Áreas, Cargos y Períodos', description: 'Crear, editar y eliminar áreas, cargos y períodos de asistencia; catálogo de Portería', permissions: ['configuracion.editar'] },

    // ── MÓDULO 4 PRODUCTOS (4) ──
    'productos_4.asignar':          { module: '4 PRODUCTOS', action: 'Asignar',          description: 'Ver y asignar 4 Productos a empleados (con RLS de área)', permissions: ['productos_4.asignar'] },
    'productos_4.consolidar':       { module: '4 PRODUCTOS', action: 'Consolidar',       description: 'Ver consolidado global de productos propios (sin RLS)', permissions: ['productos_4.consolidar'] },
    'productos_4.entregar':         { module: '4 PRODUCTOS', action: 'Entregar',         description: 'Ver y registrar entregas de productos propios (sin RLS)', permissions: ['productos_4.entregar'] },
    'productos_4.catalogo':         { module: '4 PRODUCTOS', action: 'Catálogo',         description: 'Ver y gestionar el catálogo de productos propios en Configuración', permissions: ['productos_4.catalogo'] },

    // ── MÓDULO PORTERÍA (9) ──
    'porteria.ver':                 { module: 'PORTERÍA', action: 'Ver Historial',  description: 'Ver el historial de rondas nocturnas y fotos de hallazgos (Lectura)', permissions: ['porteria.ver'] },
    'porteria.registrar':           { module: 'PORTERÍA', action: 'Registrar',      description: 'Registrar pasos por puntos de control y reportar hallazgos (Guardia)', permissions: ['porteria.registrar'] },
    'porteria.editar':              { module: 'PORTERÍA', action: 'Editar / Configurar', description: 'Gestionar el catálogo de anomalías/hallazgos y configurar puntos de control', permissions: ['porteria.editar'] },
    'porteria.rondas':              { module: 'PORTERÍA', action: 'Pestaña Rondas',     description: 'Acceso a pestaña Rondas Nocturnas', permissions: ['porteria.rondas'] },
    'porteria.llaves':              { module: 'PORTERÍA', action: 'Pestaña Llaves',     description: 'Acceso a pestaña Entrega de Llaves', permissions: ['porteria.llaves'] },
    'porteria.art22':               { module: 'PORTERÍA', action: 'Pestaña Art. 22',    description: 'Acceso a pestaña Ingreso Artículo 22 (empleados excluidos)', permissions: ['porteria.art22'] },
    'porteria.proveedores':         { module: 'PORTERÍA', action: 'Pestaña Proveedores',description: 'Acceso a pestaña Ingreso de Proveedores', permissions: ['porteria.proveedores'] },
    'porteria.visitas':             { module: 'PORTERÍA', action: 'Pestaña Visitas',    description: 'Acceso a pestaña Control de Visitas (escaneo cédula)', permissions: ['porteria.visitas'] },
    'porteria.flota':               { module: 'PORTERÍA', action: 'Pestaña Flota',      description: 'Acceso a pestaña Flota Aguacol (control de pesaje/viajes)', permissions: ['porteria.flota'] },
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
            const data = await res.json();
            cacheSeguridad.areas = Array.isArray(data) ? data : [];
        } else {
            console.error("Áreas: respuesta", res.status);
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
// Roles y áreas se cargan en segundo plano al abrir Seguridad. Antes, si el modal se abría antes de que llegaran
// (o una carga fallaba, p. ej. mala señal en el celular) el selector quedaba en "Cargando roles..." y la lista de
// áreas en "Cargando áreas..." para siempre: no se podía asignar rol ni áreas, y el precargado dependía de un
// setTimeout. Ahora el modal espera (y reintenta) los catálogos antes de mostrarse.
async function asegurarCatalogosUsuario() {
    const tareas = [];
    if (cacheSeguridad.roles.length === 0) tareas.push(loadRoles());
    if (cacheSeguridad.areas.length === 0) tareas.push(loadAreasParaSeguridad());
    if (tareas.length) await Promise.allSettled(tareas);
    return cacheSeguridad.roles.length > 0 && cacheSeguridad.areas.length > 0;
}

const escHtml = (t) => String(t ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function prepararModalUsuario(areasUsuario) {
    const ok = await asegurarCatalogosUsuario();
    if (!ok) {
        Swal.fire('No se pudieron cargar los roles o las áreas', 'Revise la conexión e intente nuevamente.', 'error');
        return false;
    }
    poblarModalUsuario(areasUsuario || []);
    return true;
}

function poblarModalUsuario(areasUsuario) {
    const selRol = document.getElementById('user-rol');
    if (selRol) {
        selRol.innerHTML = cacheSeguridad.roles.map(r =>
            `<option value="${r.id}" data-global="${r.alcance_global ? 1 : 0}">${escHtml(r.nombre)}${r.alcance_global ? ' (alcance global)' : ''}</option>`).join('');
        if (!selRol.dataset.listo) {
            selRol.addEventListener('change', actualizarAlcanceAreasUsuario);
            selRol.dataset.listo = '1';
        }
    }

    // Áreas (RLS): el catálogo + las que el usuario ya tiene guardadas aunque ya no estén en el catálogo
    // (así guardar no se las borra sin avisar).
    const chips = document.getElementById('user-areas-chips');
    if (chips) {
        const catalogo = new Set(cacheSeguridad.areas);
        const extras = (areasUsuario || []).filter(a => !catalogo.has(a));
        const todas = [...cacheSeguridad.areas, ...extras];
        chips.innerHTML = todas.map(a => `
            <div class="form-check form-check-inline">
                <input class="form-check-input area-check" type="checkbox" value="${escHtml(a)}" id="area-${escHtml(a.replace(/\s+/g, '-'))}">
                <label class="form-check-label small" for="area-${escHtml(a.replace(/\s+/g, '-'))}">${escHtml(a)}${extras.includes(a) ? ' <span class="text-warning">(fuera del catálogo)</span>' : ''}</label>
            </div>
        `).join('');
    }
}

function rolSeleccionadoEsGlobal() {
    const opt = document.getElementById('user-rol')?.selectedOptions?.[0];
    return !!opt && opt.dataset.global === '1';
}

// Un rol de alcance global ve todas las áreas: se avisa para que no parezca que falta marcar algo.
function actualizarAlcanceAreasUsuario() {
    const nota = document.getElementById('user-areas-note');
    if (nota) {
        nota.textContent = rolSeleccionadoEsGlobal()
            ? 'Este rol tiene alcance global: ve todas las áreas, no es necesario marcar ninguna.'
            : 'Marque las áreas que este usuario podrá ver. Sin áreas no verá ningún empleado.';
    }
}

window.marcarAreasUsuario = function (marcar) {
    document.querySelectorAll('.area-check').forEach(ck => { ck.checked = !!marcar; });
};

window.openUserModal = async function () {
    ensureModalInstances();
    const title = document.getElementById('modalUsuarioTitle');
    if (title) title.textContent = "👤 Nuevo Usuario Operador";
    document.getElementById('formUsuario').reset();
    document.getElementById('user-id').value = "";
    document.getElementById('user-username').disabled = false;
    document.getElementById('user-password').required = true;
    const pwHint = document.getElementById('user-pw-hint');
    if (pwHint) pwHint.textContent = "Contraseña inicial requerida.";

    if (!(await prepararModalUsuario([]))) return;
    actualizarAlcanceAreasUsuario();
    if (modalUserInstance) modalUserInstance.show();
}

window.editUsuario = async function (id) {
    const user = cacheSeguridad.usuarios.find(u => u.id === id);
    if (!user) return;
    ensureModalInstances();

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

    // Primero los catálogos (espera si aún no llegaron), recién ahí se asignan rol y áreas: sin setTimeout.
    const userAreas = Array.isArray(user.areas) ? user.areas : [];
    if (!(await prepararModalUsuario(userAreas))) return;
    document.getElementById('user-rol').value = String(user.rol_id);
    document.querySelectorAll('.area-check').forEach(ck => { ck.checked = userAreas.includes(ck.value); });
    actualizarAlcanceAreasUsuario();

    if (modalUserInstance) modalUserInstance.show();
}

window.saveUsuario = async function () {
    const userId = document.getElementById('user-id').value;
    const areasSelected = Array.from(document.querySelectorAll('.area-check:checked')).map(ck => ck.value);
    const rolId = parseInt(document.getElementById('user-rol').value);
    if (!Number.isInteger(rolId)) {
        Swal.fire('Falta el rol', 'Seleccione el rol del usuario antes de guardar.', 'warning');
        return;
    }
    // Un rol zonal sin áreas deja al usuario sin ver ningún empleado (y guardar así le borra las que tenía).
    if (!rolSeleccionadoEsGlobal() && areasSelected.length === 0) {
        const r = await Swal.fire({
            title: 'Usuario sin áreas',
            text: 'Con este rol y sin ninguna área marcada, el usuario no verá ningún empleado. ¿Guardar igual?',
            icon: 'warning', showCancelButton: true, confirmButtonText: 'Guardar igual', cancelButtonText: 'Volver',
        });
        if (!r.isConfirmed) return;
    }

    const payload = {
        username: document.getElementById('user-username').value,
        nombre_completo: document.getElementById('user-nombre').value,
        email: document.getElementById('user-email').value,
        rol_id: rolId,
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
// Metadatos visuales de cada módulo (icono, tono HSL y qué cubre). El tono (--h) colorea tarjetas, navegación e interruptores.
const RL_MODULOS = {
    'DASHBOARD':     { label: 'Dashboard',     icon: 'bi-speedometer2',   hue: 239, desc: 'Indicadores y métricas del personal' },
    'EMPLEADOS':     { label: 'Empleados',     icon: 'bi-people',         hue: 199, desc: 'Fichas, contratos, bajas, reincorporaciones y turnos' },
    'MARCACIONES':   { label: 'Marcaciones',   icon: 'bi-clock-history',  hue: 160, desc: 'Asistencia diaria, justificaciones, horas extras, cierres y libreta 180h' },
    'REPORTES':      { label: 'Reportes',      icon: 'bi-bar-chart-line', hue: 268, desc: 'Informes, exportaciones y recálculos masivos' },
    'CONFIGURACIÓN': { label: 'Configuración', icon: 'bi-sliders',        hue: 218, desc: 'Parámetros del sistema, catálogos, seguridad y flota' },
    '4 PRODUCTOS':   { label: '4 Productos',   icon: 'bi-box-seam',       hue: 32,  desc: 'Entrega de productos propios a empleados' },
    'PORTERÍA':      { label: 'Portería',      icon: 'bi-shield-check',   hue: 174, desc: 'Rondas, llaves, visitas, proveedores, Art. 22 y flota' }
};
// Permisos que pueden dañar datos, abrir meses cerrados o dar control total: se marcan con un distintivo rojo / ámbar.
const RL_CRITICOS = ['empleados.eliminar', 'configuracion.seguridad', 'marcaciones.bypass_cierre', 'configuracion.sistema', 'configuracion.editar'];
const RL_CONTABLES = ['marcaciones.cierre_periodo', 'marcaciones.horas_extras', 'marcaciones.justificar', 'marcaciones.compensar'];

function rlEsc(t) {
    return String(t ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// { 'MARCACIONES': ['marcaciones.ver', ...], ... } en el orden del catálogo
function rlPorModulo() {
    const mods = {};
    Object.keys(MAPA_UI_PERMISOS).forEach(k => { (mods[MAPA_UI_PERMISOS[k].module] ||= []).push(k); });
    return mods;
}

async function loadRoles() {
    const grid = document.getElementById('roles-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="rl-empty-state"><span class="spinner-border spinner-border-sm me-2"></span>Cargando roles…</div>';

    try {
        const response = await fetch('/api/seguridad/roles/');
        if (!response.ok) throw new Error('Error al cargar roles');
        cacheSeguridad.roles = await response.json();

        const mods = rlPorModulo();
        const totalPerms = Object.keys(MAPA_UI_PERMISOS).length;
        const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
        const totalPermsTxt = document.getElementById('rl-hero-sub');
        if (totalPermsTxt) totalPermsTxt.textContent = `${cacheSeguridad.roles.length} ${cacheSeguridad.roles.length === 1 ? 'rol' : 'roles'} · ${totalPerms} permisos disponibles en ${Object.keys(mods).length} módulos`;

        grid.innerHTML = cacheSeguridad.roles.map((rol, i) => {
            const set = new Set(rol.permisos || []);
            const granted = Object.keys(MAPA_UI_PERMISOS).filter(k => set.has(k)).length;
            const crit = RL_CRITICOS.filter(k => set.has(k)).length;
            const bloqueado = rol.id === 1 && !currentUser.is_superuser;
            const entries = Object.entries(mods);
            const spectrum = entries.map(([m, keys]) => {
                const n = keys.filter(k => set.has(k)).length;
                return `<i style="--h:${RL_MODULOS[m]?.hue ?? 215};--w:${keys.length};--p:${Math.round(n / keys.length * 100)}%"></i>`;
            }).join('');
            const lis = entries.map(([m, keys]) => {
                const n = keys.filter(k => set.has(k)).length;
                const meta = RL_MODULOS[m] || { label: m, icon: 'bi-shield', hue: 215 };
                return `<li class="${n === 0 ? 'is-empty' : ''}" style="--h:${meta.hue}"><i class="bi ${meta.icon}" aria-hidden="true"></i><span class="nm">${rlEsc(meta.label)}</span><span class="n">${n}/${keys.length}</span></li>`;
            }).join('');
            const inicial = rlEsc((rol.nombre || '?').trim().charAt(0).toUpperCase());
            return `
                <article class="rl-card ${rol.alcance_global ? 'is-global' : ''}" style="--i:${i}">
                    <header class="rl-card-head">
                        <span class="rl-avatar" aria-hidden="true">${inicial}</span>
                        <div class="rl-card-title">
                            <h3>${rlEsc(rol.nombre)}</h3>
                            <span class="rl-scope ${rol.alcance_global ? 'is-global' : ''}"><i class="bi ${rol.alcance_global ? 'bi-globe2' : 'bi-diagram-3'}" aria-hidden="true"></i>${rol.alcance_global ? 'Alcance global' : 'Filtrado por áreas'}</span>
                        </div>
                        <div class="rl-count" title="${granted} de ${totalPerms} permisos"><b>${granted}</b><span>/${totalPerms}</span></div>
                    </header>
                    <p class="rl-desc">${rlEsc(rol.descripcion) || 'Sin descripción'}</p>
                    <div class="rl-spectrum" role="img" aria-label="Cobertura de permisos por módulo">${spectrum}</div>
                    <ul class="rl-mods">${lis}</ul>
                    ${crit ? `<div class="rl-flag"><i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i>${crit} permiso${crit > 1 ? 's' : ''} crítico${crit > 1 ? 's' : ''}</div>` : ''}
                    <footer class="rl-card-foot">
                        <button type="button" class="rl-btn rl-btn-primary" ${bloqueado ? 'disabled title="Solo el Súper Admin puede modificar este rol"' : ''} onclick="editRol(${rol.id})"><i class="bi bi-sliders2" aria-hidden="true"></i>Editar permisos</button>
                        <button type="button" class="rl-btn rl-btn-icon rl-btn-danger" aria-label="Eliminar rol" ${rol.id === 1 ? 'disabled title="El rol maestro es inmutable"' : 'title="Eliminar rol"'} onclick="deleteRol(${rol.id})"><i class="bi bi-trash3" aria-hidden="true"></i></button>
                    </footer>
                </article>`;
        }).join('') || '<div class="rl-empty-state">Aún no hay roles. Crea el primero con «Nuevo rol».</div>';
    } catch (error) {
        console.error(error);
        grid.innerHTML = '<div class="rl-empty-state text-danger"><i class="bi bi-lock me-2"></i>No se pudieron cargar los roles (acceso o conexión).</div>';
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
        'configuracion.flota':          { alert: 'Ubicación: Configuración / Flota Aguacol', flow: 'Administrar el catálogo de camiones/vehículos autorizados para pesaje/transporte.' },

        // 4 Productos
        'productos_4.asignar':          { alert: 'Ubicación: Menú lateral / Tab Asignación', flow: 'Visualizar planilla de habilitados y asignar productos a empleados (con RLS de área).' },
        'productos_4.consolidar':       { alert: 'Ubicación: Menú lateral / Tab Consolidado', flow: 'Ver consolidado global acumulado por producto (sin RLS).' },
        'productos_4.entregar':         { alert: 'Ubicación: Menú lateral / Tab Entrega Beneficio', flow: 'Ver listado y registrar entregas físicas de productos (sin RLS).' },
        'productos_4.catalogo':         { alert: 'Ubicación: Configuración / Catálogo Propio', flow: 'Ver y administrar el catálogo de productos de elaboración propia.' },

        // Portería
        'porteria.ver':                 { alert: 'Ubicación: Menú lateral / Portería', flow: 'Ver el historial de rondas nocturnas y fotos de hallazgos (Lectura).' },
        'porteria.registrar':           { alert: 'Ubicación: Menú lateral / Portería', flow: 'Registrar pasos por puntos de control y reportar hallazgos (Guardia).' },
        'porteria.editar':              { alert: 'Ubicación: Configuración / Catálogo de Hallazgos', flow: 'Gestionar el catálogo de anomalías/hallazgos y configurar puntos de control.' },
        'porteria.flota':               { alert: 'Ubicación: Menú lateral / Portería', flow: 'Registrar entradas, salidas, pesajes e historial de viajes de la flota de camiones.' },
    };
    return details[permId] || null;
}

let rl_modulo_activo = null;

function rlNorm(t) {
    return String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}

function renderMatrizPermisos() {
    const container = document.getElementById('roles-permissions-matrix');
    if (!container) return;
    const mods = rlPorModulo();
    const nombres = Object.keys(mods);
    rl_modulo_activo = rl_modulo_activo && mods[rl_modulo_activo] ? rl_modulo_activo : nombres[0];

    const nav = nombres.map(m => {
        const meta = RL_MODULOS[m] || { label: m, icon: 'bi-shield', hue: 215 };
        return `<button type="button" class="rl-nav-item" data-mod="${rlEsc(m)}" style="--h:${meta.hue}" onclick="rlIrModulo('${m}')">
            <span class="ico"><i class="bi ${meta.icon}" aria-hidden="true"></i></span><span class="lbl">${rlEsc(meta.label)}</span><span class="cnt" data-cnt="${rlEsc(m)}">0/${mods[m].length}</span></button>`;
    }).join('');

    const secciones = nombres.map(m => {
        const meta = RL_MODULOS[m] || { label: m, icon: 'bi-shield', hue: 215, desc: '' };
        const rows = mods[m].map(key => {
            const item = MAPA_UI_PERMISOS[key];
            const det = getPermissionDetails(key);
            const nivel = RL_CRITICOS.includes(key) ? 'crit' : RL_CONTABLES.includes(key) ? 'cont' : '';
            const badge = nivel ? `<span class="rl-badge ${nivel}"><i class="bi ${nivel === 'crit' ? 'bi-exclamation-triangle-fill' : 'bi-calculator'}" aria-hidden="true"></i>${nivel === 'crit' ? 'Crítico' : 'Contable'}</span>` : '';
            const nota = nivel && det && det.flow ? `<span class="rl-row-note"><i class="bi bi-info-circle" aria-hidden="true"></i><span>${rlEsc(det.alert)} · ${rlEsc(det.flow)}</span></span>` : '';
            return `<label class="rl-row ${nivel ? 'is-' + (nivel === 'crit' ? 'critico' : 'contable') : ''}" for="perm-ui-${key.replace('.', '-')}" data-q="${rlEsc(rlNorm(item.action + ' ' + item.description + ' ' + key + ' ' + meta.label))}">
                <input class="perm-ui-check rl-check" type="checkbox" value="${key}" id="perm-ui-${key.replace('.', '-')}">
                <span class="rl-switch" aria-hidden="true"></span>
                <span class="rl-row-body"><span class="rl-row-name">${rlEsc(item.action)}${badge}</span><span class="rl-row-desc">${rlEsc(item.description.replace(/\s*⚠️?.*$/u, ''))}</span>${nota}</span>
                <code class="rl-key">${key}</code></label>`;
        }).join('');
        return `<section class="rl-sec" data-mod="${rlEsc(m)}" style="--h:${meta.hue}" ${m === rl_modulo_activo ? '' : 'hidden'}>
            <header class="rl-sec-head"><span class="rl-sec-ico"><i class="bi ${meta.icon}" aria-hidden="true"></i></span>
                <div><h4>${rlEsc(meta.label)}</h4><p>${rlEsc(meta.desc || '')}</p></div>
                <div class="rl-sec-actions"><button type="button" class="rl-link" onclick="rlMarcarModulo('${m}', true)">Marcar todo</button><button type="button" class="rl-link" onclick="rlMarcarModulo('${m}', false)">Quitar todo</button></div></header>
            <div class="rl-rows">${rows}</div></section>`;
    }).join('');

    container.innerHTML = `
        <aside class="rl-m-nav">
            <label class="rl-search"><i class="bi bi-search" aria-hidden="true"></i><input type="search" id="rl-search" placeholder="Buscar permiso…" autocomplete="off" aria-label="Buscar permiso"></label>
            <nav class="rl-nav" aria-label="Módulos">${nav}</nav>
        </aside>
        <div class="rl-m-panel" id="rl-panel">${secciones}<div class="rl-nores" id="rl-nores" hidden>Ningún permiso coincide con la búsqueda.</div></div>`;

    container.onchange = e => { if (e.target.classList.contains('rl-check')) rlRefrescar(); };
    const inp = document.getElementById('rl-search');
    inp.addEventListener('input', rlFiltrar);
    inp.addEventListener('keydown', e => { if (e.key === 'Escape' && inp.value) { e.stopPropagation(); inp.value = ''; rlFiltrar(); } });
    rlIrModulo(rl_modulo_activo, true);
    rlRefrescar();
}

window.rlIrModulo = function (m, silencioso) {
    rl_modulo_activo = m;
    const q = document.getElementById('rl-search');
    if (q && q.value && !silencioso) { q.value = ''; }
    document.querySelectorAll('#roles-permissions-matrix .rl-nav-item').forEach(b => b.classList.toggle('is-active', b.dataset.mod === m));
    document.querySelectorAll('#roles-permissions-matrix .rl-row').forEach(r => { r.hidden = false; });
    document.querySelectorAll('#roles-permissions-matrix .rl-sec').forEach(s => { s.hidden = s.dataset.mod !== m; });
    const nores = document.getElementById('rl-nores'); if (nores) nores.hidden = true;
    const panel = document.getElementById('rl-panel'); if (panel) panel.scrollTop = 0;
};

function rlFiltrar() {
    const q = rlNorm(document.getElementById('rl-search').value.trim());
    if (!q) { rlIrModulo(rl_modulo_activo, true); return; }
    let total = 0;
    document.querySelectorAll('#roles-permissions-matrix .rl-sec').forEach(sec => {
        let vis = 0;
        sec.querySelectorAll('.rl-row').forEach(r => { const ok = r.dataset.q.includes(q); r.hidden = !ok; if (ok) vis++; });
        sec.hidden = vis === 0; total += vis;
    });
    document.querySelectorAll('#roles-permissions-matrix .rl-nav-item').forEach(b => b.classList.remove('is-active'));
    document.getElementById('rl-nores').hidden = total > 0;
}

window.rlMarcarModulo = function (m, on) {
    document.querySelectorAll(`#roles-permissions-matrix .rl-sec[data-mod="${m}"] .rl-check`).forEach(c => { c.checked = on; });
    rlRefrescar();
};

function rlSeleccionados() {
    return Array.from(document.querySelectorAll('#roles-permissions-matrix .rl-check:checked')).map(c => c.value);
}

function rlRefrescar() {
    const sel = new Set(rlSeleccionados());
    const mods = rlPorModulo();
    Object.entries(mods).forEach(([m, keys]) => {
        const n = keys.filter(k => sel.has(k)).length;
        const el = document.querySelector(`#roles-permissions-matrix [data-cnt="${m}"]`);
        if (el) { el.textContent = `${n}/${keys.length}`; el.classList.toggle('has', n > 0); }
    });
    const crit = RL_CRITICOS.filter(k => sel.has(k)).length;
    const res = document.getElementById('rl-resumen');
    if (res) res.innerHTML = `<b>${sel.size}</b> de ${Object.keys(MAPA_UI_PERMISOS).length} permisos` + (crit ? ` · <span class="crit"><i class="bi bi-exclamation-triangle-fill"></i> ${crit} crítico${crit > 1 ? 's' : ''}</span>` : '');
}

window.rlSetAlcance = function (v) {
    document.getElementById('rol-global').value = v;
    rlSyncAlcance();
};
function rlSyncAlcance() {
    const v = document.getElementById('rol-global').value === '1' ? '1' : '0';
    const seg = document.getElementById('rl-seg');
    if (!seg) return;
    seg.dataset.v = v;
    seg.querySelectorAll('button').forEach(b => { const on = b.dataset.v === v; b.classList.toggle('is-on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); });
}

function rlTituloModal(nombre) {
    const t = document.getElementById('modalRolTitle');
    if (t) t.textContent = nombre ? `Editar rol · ${nombre}` : 'Nuevo rol';
    const av = document.getElementById('rl-m-avatar');
    if (av) av.textContent = nombre ? nombre.trim().charAt(0).toUpperCase() : '+';
}

window.openRolModal = function () {
    ensureModalInstances();
    rlTituloModal('');
    document.getElementById('formRol').reset();
    document.getElementById('rol-id').value = '';
    document.getElementById('rol-global').value = '0';
    rl_modulo_activo = null;
    renderMatrizPermisos();
    rlSyncAlcance();
    if (modalRolInstance) modalRolInstance.show();
};

window.editRol = function (id) {
    const rol = cacheSeguridad.roles.find(r => r.id === id);
    if (!rol) { console.error('Rol no encontrado:', id); return; }
    ensureModalInstances();
    rlTituloModal(rol.nombre);
    document.getElementById('rol-id').value = rol.id;
    document.getElementById('rol-nombre').value = rol.nombre;
    document.getElementById('rol-descripcion').value = rol.descripcion || '';
    document.getElementById('rol-global').value = rol.alcance_global ? '1' : '0';
    rl_modulo_activo = null;
    renderMatrizPermisos();
    rlSyncAlcance();
    const activos = new Set(rol.permisos || []);
    Object.keys(MAPA_UI_PERMISOS).forEach(key => {
        const ck = document.getElementById(`perm-ui-${key.replace('.', '-')}`);
        if (ck) ck.checked = activos.has(key);
    });
    rlRefrescar();
    if (modalRolInstance) modalRolInstance.show();
};

window.saveRol = async function () {
    const rolId = document.getElementById('rol-id').value;
    const nombre = document.getElementById('rol-nombre').value.trim();
    if (!nombre) { document.getElementById('rol-nombre').focus(); return; }

    const selectedPerms = rlSeleccionados();
    // Permisos que existen en la BD pero no en el catálogo de la pantalla (p. ej. heredados) se conservan: guardar el
    // rol desde acá no debe quitarlos en silencio.
    const original = cacheSeguridad.roles.find(r => String(r.id) === String(rolId));
    (original?.permisos || []).filter(p => !(p in MAPA_UI_PERMISOS)).forEach(p => selectedPerms.push(p));

    const payload = {
        nombre,
        descripcion: document.getElementById('rol-descripcion').value,
        alcance_global: document.getElementById('rol-global').value === '1',
        permisos: selectedPerms
    };

    try {
        const method = rolId ? 'PUT' : 'POST';
        const url = rolId ? `/api/seguridad/roles/${rolId}/` : '/api/seguridad/roles/';
        const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
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
};

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

