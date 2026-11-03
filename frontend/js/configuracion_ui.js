// configuracion_ui.js - Interfaz Completa de Configuración (Bonos y Justificaciones)

const API_CONFIG = '/api/configuracion/';

// Estado local
let bonosList = [];
let tiposJustificacionList = [];
let globalCargosList = []; // [NEW] Cache cargos for dropdowns
let pagadoresList = []; // [NEW] Cache pagadores
let periodosRRHHList = []; // [NEW] Cache periodos rrhh

// appendCargoToInput: agrega un cargo al input (multi-valor, coma separado)
// Funciona tanto si el <ul> está en su posición original como si fue movido al body.
// Usa data-target-input en el <ul> para localizar el input por ID.
window.appendCargoToInput = function (element, cargo) {
    // Primero: buscar via data-target-input (funciona aunque el menu esté en body)
    const ul = element.closest('ul[data-target-input]');
    if (ul) {
        const input = document.getElementById(ul.dataset.targetInput);
        if (input) {
            let current = input.value.trim();
            if (current.length > 0 && !current.endsWith(',')) current += ', ';
            input.value = current + cargo;
            _refreshDropdownChecks(ul); // actualizar checkmarks inmediatamente
            return;
        }
    }
    // Fallback: traversal DOM original (cuando el menu no fue movido)
    const input = element.closest('.input-group')?.querySelector('input');
    if (!input) return;
    let current = input.value.trim();
    if (current.length > 0 && !current.endsWith(',')) current += ', ';
    input.value = current + cargo;
};

// selectCargoRequerido: limpia el campo "Cargo Req." (usado por el ítem 'Limpiar selección').
// También usa data-target-input para funcionar cuando el menu está en body.
window.selectCargoRequerido = function(element, cargo) {
    const ul = element.closest('ul[data-target-input]');
    if (ul) {
        const input = document.getElementById(ul.dataset.targetInput);
        if (input) { input.value = cargo; return; }
    }
    // Fallback
    const inputGroup = element.closest('.cargo-req-wrapper');
    if (!inputGroup) return;
    const input = inputGroup.querySelector('.rule-cargo');
    if (input) input.value = cargo;
};

// _refreshDropdownChecks: actualiza checkmarks verdes según el valor actual del input.
// Funciona aunque la <ul> esté en document.body (usa data-target-input).
function _refreshDropdownChecks(ulElement) {
    if (!ulElement) return;
    const targetId = ulElement.dataset?.targetInput;
    const targetInput = targetId ? document.getElementById(targetId) : null;
    const currentVal = targetInput ? targetInput.value : '';
    const selected = currentVal.split(',').map(c => c.trim().toUpperCase()).filter(Boolean);

    ulElement.querySelectorAll('.cargo-item[data-cargo]').forEach(a => {
        const cargo = (a.dataset.cargo || '').trim().toUpperCase();
        const li = a.closest('li');
        const isSelected = selected.includes(cargo);
        let chk = a.querySelector('.cargo-check');
        if (isSelected) {
            if (!chk) {
                chk = document.createElement('i');
                chk.className = 'bi bi-check2 cargo-check text-success fw-bold ms-auto';
                a.appendChild(chk);
            }
            if (li) li.style.background = '#f0fdf4';
        } else {
            chk?.remove();
            if (li) li.style.background = '';
        }
    });
}

// _populateCargoDropdown: puebla un <ul> con la lista de cargos.
// Tanto cargo-req-ul como cargo-dropdown-ul usan appendCargoToInput
// (acumula coma-separado). Solo el ítem 'Limpiar' llama a selectCargoRequerido('').
function _populateCargoDropdown(ulElement, singleSelect = false) {
    if (!ulElement) return;
    const existingItems = ulElement.querySelectorAll('li:not(:first-child)');
    existingItems.forEach(li => li.remove());

    const list = globalCargosList;
    if (list.length === 0) {
        const li = document.createElement('li');
        li.innerHTML = '<span class="dropdown-item text-muted small">No hay cargos disponibles</span>';
        ulElement.appendChild(li);
        return;
    }

    // Leer valor actual del input para marcar ya seleccionados
    const targetId = ulElement.dataset?.targetInput;
    const targetInput = targetId ? document.getElementById(targetId) : null;
    const currentVal = targetInput ? targetInput.value : '';
    const selected = currentVal.split(',').map(c => c.trim().toUpperCase()).filter(Boolean);

    list.forEach(cargo => {
        const li = document.createElement('li');
        const safeC = cargo.replace(/'/g, "\\'");
        const isSelected = selected.includes(cargo.trim().toUpperCase());
        li.innerHTML = `<a class="dropdown-item small py-2 cargo-item d-flex align-items-center justify-content-between"
            href="#" data-cargo="${cargo}"
            onclick="appendCargoToInput(this, '${safeC}'); return false;">
            <span>${cargo}</span>
            ${isSelected ? '<i class="bi bi-check2 cargo-check text-success fw-bold"></i>' : ''}
        </a>`;
        if (isSelected) li.style.background = '#f0fdf4';
        ulElement.appendChild(li);
    });
}

window.filterCargosDropdown = function(inputElement) {
    if (!inputElement) return;
    const ul = inputElement.closest('ul');
    if (!ul) return;
    const isSingle = ul.closest('.cargo-req-wrapper') !== null;
    const existingItems = ul.querySelectorAll('.cargo-item');
    if (existingItems.length === 0 && globalCargosList.length > 0) {
        _populateCargoDropdown(ul, isSingle);
    }
    const filter = (inputElement.value || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    ul.querySelectorAll('.cargo-item').forEach(item => {
        const text = (item.textContent || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        item.parentElement.style.display = text.includes(filter) ? '' : 'none';
    });
};


// ══════════════════════════════════════════════════════════════════════════════
// ESTADOS DE ASISTENCIA — Configuración Visual
// ══════════════════════════════════════════════════════════════════════════════

let _estadosConfigList = [];

window.loadEstadosConfig = async function() {
    const container = document.getElementById('estados-config-container');
    if (!container) return;

    container.innerHTML = `<div class="text-center py-5 text-muted">
        <div class="spinner-border spinner-border-sm" role="status"></div> Cargando estados...
    </div>`;

    try {
        const res = await fetch('/api/configuracion/estados/?solo_activos=false', { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` } });
        if (!res.ok) throw new Error('Error cargando estados');
        _estadosConfigList = await res.json();
        renderEstadosConfig();
    } catch(e) {
        container.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
    }
};

const COLOR_OPTIONS = [
    // ── Colores sólidos ──────────────────────────────────────────
    { value: 'color-verde',    label: 'Verde',         preview: '#10b981' },
    { value: 'color-azul',     label: 'Azul',          preview: '#3b82f6' },
    { value: 'color-rojo',     label: 'Rojo',          preview: '#ef4444' },
    { value: 'color-amarillo', label: 'Amarillo',      preview: '#f59e0b' },
    { value: 'color-naranja',  label: 'Naranja',       preview: '#f97316' },
    { value: 'color-purpura',  label: 'Púrpura',       preview: '#8b5cf6' },
    { value: 'color-rosa',     label: 'Rosa',           preview: '#f472b6' },
    { value: 'color-cian',     label: 'Cian',           preview: '#22d3ee' },
    { value: 'color-lima',     label: 'Lima',           preview: '#a3e635' },
    { value: 'color-indigo',   label: 'Índigo',         preview: '#3f6fd6' },
    { value: 'color-teal',     label: 'Teal',           preview: '#14b8a6' },
    { value: 'color-gris',     label: 'Gris',           preview: '#64748b' },
    { value: 'color-negro',    label: 'Negro',          preview: '#1f2937' },
    // ── Flúor (brillo neon) ──────────────────────────────────────
    { value: 'color-fluor-verde',    label: 'Flúor Verde',    preview: '#b3f500' },
    { value: 'color-fluor-azul',     label: 'Flúor Azul',     preview: '#00d4ff' },
    { value: 'color-fluor-amarillo', label: 'Flúor Amarillo', preview: '#ffe600' },
    { value: 'color-fluor-rosa',     label: 'Flúor Rosa',     preview: '#ff4dde' },
    // ── Intermitentes (animación) ────────────────────────────────
    { value: 'color-pulso-rojo',  label: 'Pulso Rojo',    preview: '#ef4444' },
    { value: 'color-pulso-verde', label: 'Pulso Verde',   preview: '#b3f500' },
    { value: 'color-pulso-azul',  label: 'Pulso Azul',    preview: '#00d4ff' },
    { value: 'color-glitter-oro',   label: 'Glitter Oro',   preview: '#f59e0b' },
    { value: 'color-glitter-plata', label: 'Glitter Plata', preview: '#94a3b8' },
];

// ── Helpers de la pestaña Estados ───────────────────────────────────────────
function _escAttr(v) {
    return String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function _estadoSiglaDefecto(codigo) { return codigo === 'JORNADA_ESPECIAL' ? 'ESP' : String(codigo).substring(0, 3); }
// Vista previa idéntica a la grilla HD: la sigla en una pastilla de su color, dentro de una celda de día real (css/configuracion.css)
function _estadoPreviewHtml(color, icono, sigla) {
    return `<table class="matrix-table-premium mb-0 mx-auto" style="width:84px;border:0;background:transparent" aria-hidden="true"><tbody><tr>
        <td class="col-day text-center p-0" style="height:38px;min-width:0;width:84px;border:1px solid #e2e8f0;background:#fff;position:relative;overflow:visible">
            <span class="badge-status ${_escAttr(color)}"><span><i class="bi ${_escAttr(icono || 'bi-circle')}"></i>${_escAttr(sigla)}</span></span>
        </td></tr></tbody></table>`;
}
const _COLORES_ESPECIALES = /^color-(fluor|pulso|glitter)-/;
// Marca siglas repetidas (bloquea al guardar) y colores repetidos (solo avisa)
window.refreshEstadosAvisos = function() {
    // Lee de la pantalla el estado que se está editando y de los datos los demás (diseño B: una ficha a la vez)
    const val = function (e, campo, porDefecto) {
        const el = document.getElementById(`estado-${campo}-${e.codigo}`);
        if (!el) return porDefecto;
        return el.type === 'checkbox' ? el.checked : el.value;
    };
    const filas = _estadosConfigList.map(e => ({
        e: e,
        activo: !!val(e, 'activo', !!e.activo),
        sigla: String(val(e, 'short', e.short_label || '') || _estadoSiglaDefecto(e.codigo)).trim().toUpperCase(),
        color: val(e, 'color', e.color_clase || '')
    }));
    const sig = {}, col = {};
    filas.filter(x => x.activo).forEach(x => { (sig[x.sigla] = sig[x.sigla] || []).push(x.e.codigo); (col[x.color] = col[x.color] || []).push(x.e.codigo); });
    const nombreDe = c => (_estadosConfigList.find(x => x.codigo === c) || {}).nombre_display || c;
    filas.forEach(x => {
        const inp = document.getElementById(`estado-short-${x.e.codigo}`);
        const aviso = document.getElementById(`estado-aviso-${x.e.codigo}`);
        if (!inp || !aviso) return;
        const dupSig = x.activo && (sig[x.sigla] || []).length > 1 ? sig[x.sigla].filter(c => c !== x.e.codigo) : [];
        const dupCol = x.activo && (col[x.color] || []).length > 1 ? col[x.color].filter(c => c !== x.e.codigo) : [];
        inp.classList.toggle('is-invalid', dupSig.length > 0 || !/^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ.+\-]{1,5}$/.test(inp.value.trim() || 'X'));
        let h = '';
        if (dupSig.length) h += '<p class="fcB-nota" style="color:#a3261c"><i class="bi bi-x-octagon-fill" aria-hidden="true"></i> Etiqueta repetida con ' + dupSig.map(nombreDe).map(_escAttr).join(', ') + '. Cámbiela antes de guardar.</p>';
        if (dupCol.length) h += '<p class="fcB-nota"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i> Mismo color que ' + dupCol.map(nombreDe).map(_escAttr).join(', ') + '.</p>';
        if (_COLORES_ESPECIALES.test(x.color)) h += '<p class="fcB-nota"><i class="bi bi-info-circle" aria-hidden="true"></i> En la grilla se ve como su color base.</p>';
        aviso.innerHTML = h;
    });
};

function renderEstadosConfig() {
    // Diseño B (01-11-2026): lista de estados a la izquierda y su ficha con la vista previa a la derecha.
    const container = document.getElementById('estados-config-container');
    if (!container || !window.FichaCfg) return;
    const F = window.FichaCfg;
    const canEdit = F.puede('configuracion.editar');
    const sinDibujo = l => String(l).replace(/^[^A-Za-zÁÉÍÓÚÑáéíóúñ]+/, '');
    F.montar(container, {
        clave: 'estados',
        titulo: 'Estados',
        descripcion: 'Cómo se ve cada estado en la grilla: su nombre, su etiqueta corta y su color. El código no cambia: lo usa el cálculo.',
        acciones: '<button type="button" class="fcB-btn" onclick="loadEstadosConfig()"><i class="bi bi-arrow-clockwise" aria-hidden="true"></i>Actualizar</button>',
        items: _estadosConfigList,
        id: e => e.codigo,
        etiqueta: e => e.nombre_display || e.codigo,
        sub: e => e.short_label || _estadoSiglaDefecto(e.codigo),
        apagado: e => !e.activo,
        vacio: 'No hay estados.',
        ficha: function (e, panel) {
            const c = e.codigo;
            panel.innerHTML = F.cabeza(e.nombre_display || c, 'Código ' + c + (e.es_sistema ? ' · estado del sistema' : ''))
                + '<div id="estado-aviso-' + _escAttr(c) + '"></div>'
                + F.campo('Vista previa', '<div id="preview-' + _escAttr(c) + '">' + _estadoPreviewHtml(e.color_clase, e.icono_bi, e.short_label || _estadoSiglaDefecto(c)) + '</div>', 'Así se ve en la grilla.')
                + F.campo('Nombre visible', '<input type="text" class="fcB-inp" id="estado-nombre-' + _escAttr(c) + '" maxlength="40" value="' + _escAttr(e.nombre_display || '') + '">', '', 'estado-nombre-' + c)
                + F.campo('Etiqueta', '<input type="text" class="fcB-inp" style="max-width:120px;text-transform:uppercase" id="estado-short-' + _escAttr(c) + '" maxlength="5" value="' + _escAttr(e.short_label || _estadoSiglaDefecto(c)) + '" oninput="previewEstadoBadge(\'' + _escAttr(c) + '\')">', 'Hasta 5 letras o números. No puede repetirse entre estados activos.', 'estado-short-' + c)
                + F.campo('Color', '<select class="fcB-inp" id="estado-color-' + _escAttr(c) + '" onchange="previewEstadoBadge(\'' + _escAttr(c) + '\')">'
                    + COLOR_OPTIONS.map(o => '<option value="' + o.value + '"' + (o.value === e.color_clase ? ' selected' : '') + '>' + _escAttr(sinDibujo(o.label)) + '</option>').join('') + '</select>', '', 'estado-color-' + c)
                + F.campo('Ícono', '<span style="display:inline-grid;place-items:center;width:38px;height:38px;border:1px solid #e6e9f1;border-radius:9px"><i id="estado-icon-preview-' + _escAttr(c) + '" class="bi ' + _escAttr(e.icono_bi || 'bi-circle') + '" aria-hidden="true"></i></span>'
                    + '<input type="text" class="fcB-inp" style="max-width:220px" id="estado-icono-' + _escAttr(c) + '" value="' + _escAttr(e.icono_bi || '') + '" placeholder="bi-circle-fill" oninput="previewEstadoBadge(\'' + _escAttr(c) + '\')">', 'Nombre de un ícono de Bootstrap, por ejemplo bi-clock.', 'estado-icono-' + c)
                + F.campo('Descripción', '<input type="text" class="fcB-inp" id="estado-desc-' + _escAttr(c) + '" maxlength="240" value="' + _escAttr(e.descripcion || '') + '">', 'Se lee al pasar el puntero sobre el estado.', 'estado-desc-' + c)
                + F.campo('En uso', '<label class="fcB-sw"><input type="checkbox" id="estado-activo-' + _escAttr(c) + '"' + (e.activo ? ' checked' : '') + ' onchange="refreshEstadosAvisos()"><span aria-hidden="true"></span>Se muestra en la grilla</label>')
                + (canEdit ? F.pie('', '<button type="button" class="fcB-btn" id="fes-descartar">Descartar</button><button type="button" class="fcB-btn pri" id="fes-guardar">Guardar cambios</button>') : '');
            refreshEstadosAvisos();
            if (!canEdit) { panel.querySelectorAll('input, select').forEach(x => { x.disabled = true; }); return; }
            panel.querySelector('#fes-descartar').onclick = () => F.pintarFicha('estados');
            panel.querySelector('#fes-guardar').onclick = ev => F.trabajando(ev.currentTarget, async () => {
                await saveEstado(c);
                // La lista refleja lo guardado (el servidor deja la etiqueta en mayúsculas)
                const v = id => (document.getElementById(id) || {});
                e.nombre_display = v('estado-nombre-' + c).value || e.nombre_display;
                e.short_label = v('estado-short-' + c).value || e.short_label;
                e.descripcion = v('estado-desc-' + c).value;
                e.color_clase = v('estado-color-' + c).value || e.color_clase;
                e.icono_bi = v('estado-icono-' + c).value;
                e.activo = v('estado-activo-' + c).checked ? 1 : 0;
                container.querySelectorAll('.fcB-it').forEach(b => {
                    if (b.dataset.id !== c) return;
                    b.querySelector('.n').textContent = e.nombre_display || c;
                    const sm = b.querySelector('small'); if (sm) sm.textContent = e.short_label || '';
                    b.classList.toggle('apagado', !e.activo);
                });
            });
        }
    });
}

window.previewEstadoBadge = function(codigo) {
    const color = document.getElementById(`estado-color-${codigo}`)?.value || 'badge-state-neutral';
    const icono = document.getElementById(`estado-icono-${codigo}`)?.value || 'bi-circle';
    const cont = document.getElementById(`preview-${codigo}`);
    const iconPrev = document.getElementById(`estado-icon-preview-${codigo}`);
    if (cont) {
        const displayLabel = document.getElementById(`estado-short-${codigo}`)?.value || _estadoSiglaDefecto(codigo);
        cont.innerHTML = _estadoPreviewHtml(color, icono, displayLabel);
    }
    if (iconPrev) iconPrev.className = `bi ${/^bi-[a-z0-9-]+$/.test(icono) ? icono : 'bi-circle'}`;
    refreshEstadosAvisos();
};

window.saveEstado = async function(codigo) {
    const nombre = document.getElementById(`estado-nombre-${codigo}`)?.value?.trim();
    const shortLabel = document.getElementById(`estado-short-${codigo}`)?.value?.trim();
    const desc = document.getElementById(`estado-desc-${codigo}`)?.value?.trim();
    const color = document.getElementById(`estado-color-${codigo}`)?.value;
    const icono = document.getElementById(`estado-icono-${codigo}`)?.value?.trim();
    const activo = document.getElementById(`estado-activo-${codigo}`)?.checked ? 1 : 0;

    // Validación previa (el servidor vuelve a validar)
    if (!nombre) { showToast('Falta el nombre visible.', 'warning'); return; }
    if (shortLabel && !/^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ.+\-]{1,5}$/.test(shortLabel)) { showToast('La etiqueta debe tener de 1 a 5 letras o números (también punto, + o guion).', 'warning'); return; }
    if (icono && !/^bi-[a-z0-9-]+$/.test(icono)) { showToast('El ícono debe escribirse como bi-nombre (por ejemplo, bi-clock).', 'warning'); return; }
    if (/[<>]/.test(`${nombre}${desc}${shortLabel}`)) { showToast('Los textos no pueden llevar los signos < ni >.', 'warning'); return; }
    refreshEstadosAvisos();
    if (document.getElementById(`estado-short-${codigo}`)?.classList.contains('is-invalid')) { showToast('Corrija la etiqueta antes de guardar: está repetida o no tiene el formato correcto.', 'warning'); return; }

    try {
        const res = await fetch(`/api/configuracion/estados/${codigo}/`, {
            method: 'PUT',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre_display: nombre, short_label: shortLabel, descripcion: desc, color_clase: color, icono_bi: icono, activo })
        });
        const out = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(typeof out.detail === 'string' ? out.detail : 'Error guardando');
        if (out.saved && out.saved.short_label !== undefined) {
            const inp = document.getElementById(`estado-short-${codigo}`);
            if (inp) inp.value = out.saved.short_label;      // el servidor la deja en mayúsculas
        }
        (out.warnings || []).forEach(w => showToast(w, 'warning'));

        // Actualizar caché global para que los badges se vean de inmediato sin recargar la página
        if (window._estadosAsistencia && window._estadosAsistencia[codigo]) {
            window._estadosAsistencia[codigo].nombre_display = nombre;
            window._estadosAsistencia[codigo].short_label = shortLabel;
            window._estadosAsistencia[codigo].color_clase = color;
            window._estadosAsistencia[codigo].icono_bi = icono;
            window._estadosAsistencia[codigo].activo = activo;
        }

        showToast(`Listo. Se guardó el estado ${codigo}.`, 'success');
        previewEstadoBadge(codigo);
    } catch(e) {
        showToast('No se guardó: ' + e.message, 'error');
    }
};
// ==========================================
// INICIALIZACIÓN
// ==========================================
function initConfiguracionUI() {
    // [FIX] Guardar para evitar re-flickering si ya inicializó
    if (window._config_initialized) {
        console.log("⚙️ Configuración (CRUD) ya inicializada. Omitiendo.");
        return;
    }
    
    console.log("Inicializando UI de Configuración (CRUD Completo)...");

    // Configurar listeners de formularios
    const formBono = document.getElementById('form-bono');
    if (formBono) {
        formBono.onsubmit = (e) => {
            e.preventDefault();
            saveBono();
        };
    }

    const formTipoJ = document.getElementById('form-tipo-justificacion');
    if (formTipoJ) {
        formTipoJ.onsubmit = (e) => {
            e.preventDefault();
            saveTipoJustificacion();
        };
    }

    // Datalists Container Check
    if (!document.getElementById('datalists-container')) {
        const div = document.createElement('div');
        div.id = 'datalists-container';
        div.innerHTML = `
            <datalist id="list-cargos"></datalist>
        `;
        document.body.appendChild(div);
    }

    loadBonos();
    loadTiposJustificacion();
    loadPagadores(); // [NEW]
    loadMetadata();
    loadEmailSettings(); // [NEW]
    loadAreaNotificaciones(); // [NEW]

    // [NEW] Escuchar cambio a pestaña de Seguridad
    const seguridadTabBtn = document.getElementById('seguridad-config-tab');
    if (seguridadTabBtn) {
        seguridadTabBtn.addEventListener('shown.bs.tab', () => {
            if (typeof initSeguridadUI === 'function') {
                initSeguridadUI();
            }
        });
    }

    // [NEW] Escuchar cambio a pestañas de Portería en Configuración
    const hallazgosTabBtn = document.getElementById('catalogo-hallazgos-config-tab');
    if (hallazgosTabBtn) {
        hallazgosTabBtn.addEventListener('shown.bs.tab', () => {
            if (typeof PorteriaModule !== 'undefined') {
                PorteriaModule.initAdminTab();
            }
        });
    }

    const ubicacionesTabBtn = document.getElementById('catalogo-ubicaciones-config-tab');
    if (ubicacionesTabBtn) {
        ubicacionesTabBtn.addEventListener('shown.bs.tab', () => {
            if (typeof PorteriaModule !== 'undefined') {
                PorteriaModule.initUbicacionesTab();
            }
        });
    }

    window._config_initialized = true;
}

async function loadMetadata(forceReload = false) {
    // RACE CONDITION FIX: si ya hay una carga en curso, retornar la misma Promise
    // Esto previene que _wizardCrearBono + initConfiguracionUI lancen dos cargas paralelas.
    if (window._metadataPromise && !forceReload) {
        return window._metadataPromise;
    }

    if (forceReload) {
        globalCargosList = [];
    }

    window._metadataPromise = _doLoadMetadata();
    try {
        await window._metadataPromise;
    } finally {
        window._metadataPromise = null; // Limpiar para permitir recargas futuras
    }
}

async function _doLoadMetadata() {
    // FIX DEFINITIVO: cargar cargos del catálogo SIEMPRE, independiente de si
    // /api/empleados/metadata/ falla (sin empleados aún, o token diferente).
    // Antes: si metadata fallaba (L308 return), nunca se cargaba el catálogo.
    let allCargos = new Set();

    // 1. Intentar metadata de empleados (puede estar vacío en instalación nueva)
    try {
        const response = await fetch('/api/empleados/metadata/', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
        });
        if (response.ok) {
            const data = await response.json();
            (data.cargos || []).forEach(c => allCargos.add(c));

            // Populate Areas en Notificaciones
            if (data.areas) {
                const selectAreas = document.getElementById('notif-area-nombre');
                if (selectAreas) {
                    selectAreas.innerHTML =
                        '<option value="" selected disabled>Seleccione un Área...</option>' +
                        data.areas.map(a => `<option value="${a}">${a}</option>`).join('');
                }
            }
        } else {
            console.warn('[loadMetadata] /api/empleados/metadata/ respondió:', response.status, '— continuando con catálogo.');
        }
    } catch (e) {
        console.warn('[loadMetadata] Error en /api/empleados/metadata/:', e.message);
    }

    // 2. SIEMPRE cargar catálogo de cargos (tabla `cargos`, no depende de empleados)
    try {
        const cargosRes = await fetch('/api/configuracion/cargos/', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
        });
        if (cargosRes.ok) {
            const catalogCargos = await cargosRes.json();
            catalogCargos.forEach(c => allCargos.add(c.nombre || c.cargo_nombre || ''));
            console.log(`[loadMetadata] Catálogo de cargos cargado: ${catalogCargos.length} registros.`);
        } else {
            console.warn('[loadMetadata] /api/configuracion/cargos/ respondió:', cargosRes.status);
        }
    } catch (e) {
        console.warn('[loadMetadata] Error en /api/configuracion/cargos/:', e.message);
    }

    // 2.5 Inyectar cargos en memoria del Wizard (si existe)
    if (window._wizardState && window._wizardState.resoluciones && window._wizardState.resoluciones.cargos) {
        Object.values(window._wizardState.resoluciones.cargos).forEach(c => {
            if (c && c !== "_IGNORE_") {
                allCargos.add(c);
            }
        });
    }

    // 3. Actualizar globalCargosList y datalist
    allCargos.delete(''); // limpiar vacíos
    const cargosArray = Array.from(allCargos).sort();
    globalCargosList = cargosArray;
    console.log(`[loadMetadata] globalCargosList actualizado con ${globalCargosList.length} cargos.`);

    let listCargos = document.getElementById('list-cargos');
    if (!listCargos) {
        listCargos = document.createElement('datalist');
        listCargos.id = 'list-cargos';
        document.body.appendChild(listCargos);
    }
    if (listCargos && cargosArray.length > 0) {
        listCargos.innerHTML = cargosArray.map(c => `<option value="${c}">`).join('');
    }
}

// ==========================================
// BONOS: DATOS Y RENDER
// ==========================================
async function loadBonos() {
    try {
        const response = await fetch(`${API_CONFIG}bonos/`);
        if (!response.ok) throw new Error("Error cargando bonos");
        bonosList = await response.json();
        renderBonos();
    } catch (error) {
        console.error(error);
        showToast("No se pudieron cargar los bonos.", "error");
    }
}

function renderBonos() {
    // Diseño B (01-11-2026): lista de bonos y su ficha con las reglas. Las reglas tienen filas que se agregan y quitan:
    // se cambian en el editor de siempre («Editar bono»).
    const container = document.getElementById('tab-bonos');
    if (!container || !window.FichaCfg) return;
    const F = window.FichaCfg;
    const canEdit = F.puede('configuracion.bonos');
    const pesos = function (n) { return '$' + Number(n || 0).toLocaleString('es-CL'); };
    F.montar(container, {
        clave: 'bonos',
        titulo: 'Bonos',
        descripcion: 'Bonos e incentivos que se pagan según asistencia, contrato o cargo.',
        acciones: canEdit ? '<button type="button" class="fcB-btn pri" onclick="openModalBono()"><i class="bi bi-plus-lg" aria-hidden="true"></i>Nuevo bono</button>' : '',
        items: bonosList.slice().sort(function (a, b) { return String(a.nombre).localeCompare(String(b.nombre), 'es'); }),
        id: function (b) { return b.id; },
        etiqueta: function (b) { return b.nombre; },
        sub: function (b) { const n = (b.reglas || []).length; return n ? n + (n === 1 ? ' regla' : ' reglas') : 'Sin reglas'; },
        apagado: function (b) { return !b.activo; },
        vacio: 'No hay bonos. Cree el primero con «Nuevo bono».',
        ficha: function (b, panel) {
            const reglas = (b.reglas || []).map(function (r) {
                const cond = [r.tipo_contrato || 'Todo contrato', r.asistencia_minima < 100 ? 'asistencia sobre ' + r.asistencia_minima + ' %' : 'asistencia completa',
                              r.cargo_requerido ? 'cargo ' + r.cargo_requerido : '', r.es_proporcional ? 'proporcional a los días trabajados' : ''].filter(Boolean).join(' · ');
                return '<div class="fcB-campo"><div class="fcB-et"><span class="num">' + F.esc(pesos(r.monto)) + '</span></div><div class="fcB-ctl"><span>' + F.esc(cond) + '</span></div></div>';
            }).join('');
            panel.innerHTML = F.cabeza(b.nombre, b.descripcion || '')
                + F.campo('En uso', '<span class="fcB-sw" aria-disabled="true"><input type="checkbox" disabled' + (b.activo ? ' checked' : '') + '><span aria-hidden="true"></span>' + (b.activo ? 'Se calcula' : 'No se calcula') + '</span>')
                + F.seccion('Reglas de aplicación')
                + (reglas || '<p class="fcB-nota">Este bono no tiene reglas: no se paga a nadie.</p>')
                + (canEdit ? F.pie('<button type="button" class="fcB-btn borra" onclick="confirmDeleteBono(' + b.id + ')"><i class="bi bi-trash3" aria-hidden="true"></i>Eliminar bono</button>',
                    '<button type="button" class="fcB-btn pri" onclick="editBono(' + b.id + ')"><i class="bi bi-pencil" aria-hidden="true"></i>Editar bono</button>') : '');
        }
    });
}

// ==========================================
// BONOS: MODAL Y FORMULARIO
// ==========================================
async function openModalBono(bono = null) {
    if (globalCargosList.length === 0) {
        await loadMetadata();
    }
    
    const modal = document.getElementById('modal-bono');
    const title = document.getElementById('modal-bono-title');
    const form = document.getElementById('form-bono');
    const container = document.getElementById('reglas-container');
    const areasContainer = document.getElementById('bono-areas-container');

    form.reset();
    container.innerHTML = '';

    if (bono) {
        title.innerText = 'Editar Bono';
        document.getElementById('bono-id').value = bono.id;
        document.getElementById('bono-nombre').value = bono.nombre;
        document.getElementById('bono-descripcion').value = bono.descripcion || '';
        document.getElementById('bono-activo').value = bono.activo ? 'true' : 'false';
        if (bono.reglas) {
            bono.reglas.forEach(r => addBonoReglaRow(r));
        }
    } else {
        title.innerText = 'Crear Nuevo Bono';
        document.getElementById('bono-id').value = '';
        addBonoReglaRow();
    }

    // FIX RACE CONDITION: cargar areas ANTES de mostrar el modal.
    // Si mostramos el modal primero y el fetch es async, el usuario puede
    // marcar checkboxes que luego son destruidos cuando el fetch termina
    // y reemplaza el innerHTML. Cargamos primero, luego mostramos el modal.
    areasContainer.innerHTML = '<span class="text-muted small"><span class="spinner-border spinner-border-sm me-1"></span>Cargando areas...</span>';
    try {
        const areasRes = await fetch(`/api/configuracion/areas/`, {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
        });
        const areasData = areasRes.ok ? await areasRes.json() : [];
        
        let assignedAreaIds = new Set(bono && bono.area_ids ? bono.area_ids : []);
        
        if (areasData.length > 0) {
            areasContainer.innerHTML = areasData.map(a => {
                const areaId = a.id;
                const areaName = a.nombre || a.name;
                const checked = assignedAreaIds.has(areaId) ? 'checked' : '';
                return `<div class="form-check form-check-inline">
                    <input class="form-check-input bono-area-chk" type="checkbox" value="${areaId}" id="bono-area-${areaId}" ${checked}>
                    <label class="form-check-label small" for="bono-area-${areaId}">${areaName}</label>
                </div>`;
            }).join('');
        } else {
            areasContainer.innerHTML = '<span class="text-muted small">No hay areas configuradas aun</span>';
        }
    } catch(e) {
        console.error('[openModalBono] Error cargando areas:', e);
        areasContainer.innerHTML = '<span class="text-muted small text-danger">Error cargando areas</span>';
    }

    // Mostrar modal DESPUES de que las areas esten listas (evita race condition)
    modal.style.display = 'flex';
}

function closeModalBono(fromSave = false) {
    document.getElementById('modal-bono').style.display = 'none';

    // Si se abrió desde el wizard via _wizardCrearBono, ejecutar el callback de cierre
    if (typeof window._wizardBonoCloseCallback === 'function') {
        // Pequeño delay para que el DOM se actualice antes de refrescar el wizard
        setTimeout(window._wizardBonoCloseCallback, 100);
        return; // El callback maneja el flujo del wizard
    }

    if (!fromSave && window.isWizardFlow && window.wizardCurrentStep === 'bonos') {
        Swal.fire({
            title: "¿Omitir Bonos?",
            text: "No has guardado el bono actual. ¿Deseas saltar al siguiente paso?",
            icon: "warning",
            showCancelButton: true,
            confirmButtonText: "Sí, ir a Justificaciones",
            cancelButtonText: "No, seguir editando",
            reverseButtons: true
        }).then((result) => {
            if (result.isConfirmed) {
                if (typeof window.abrirConfigJustificacionWizard === 'function') {
                    window.abrirConfigJustificacionWizard();
                }
            } else {
                openModalBono();
            }
        });
    }
}

function addBonoReglaRow(regla = null) {
    const container = document.getElementById('reglas-container');
    const rowIdx = container.querySelectorAll('.regla-row').length; // ID único basado en el conteo actual
    const div = document.createElement('div');
    div.className = 'regla-row card p-3 mb-2 bg-light border-0 shadow-sm';

    div.innerHTML = `
        <div class="row g-2 mb-2">
            <div class="col-md-6">
                <label for="rule-contrato-${rowIdx}" class="small text-muted fw-bold">1. Tipo Contrato</label>
                <select id="rule-contrato-${rowIdx}" class="rule-contrato form-select form-select-sm">
                    <option value="">Todos los Contratos</option>
                    <option value="Indefinido" ${regla && regla.tipo_contrato === 'Indefinido' ? 'selected' : ''}>Indefinido</option>
                    <option value="Temporal" ${regla && regla.tipo_contrato === 'Temporal' ? 'selected' : ''}>Temporal</option>
                </select>
            </div>
            <div class="col-md-6">
                <label for="rule-monto-${rowIdx}" class="small text-muted fw-bold">2. Monto Base ($)</label>
                <div class="input-group input-group-sm">
                    <span class="input-group-text">$</span>
                    <input type="number" id="rule-monto-${rowIdx}" class="rule-monto form-control font-monospace fw-bold" value="${regla ? regla.monto : 0}" required>
                </div>
            </div>
        </div>
        <div class="row g-2 align-items-end">
            <div class="col-md-2">
                <label for="rule-asistencia-${rowIdx}" class="small text-muted">% Asist.</label>
                <div class="input-group input-group-sm">
                    <input type="number" id="rule-asistencia-${rowIdx}" class="rule-asistencia form-control" value="${regla ? regla.asistencia_minima : 0}" min="0" max="100" step="1">
                </div>
            </div>
            <div class="col-md-2 text-center">
                <label for="rule-proporcional-${rowIdx}" class="small text-muted" title="¿Descontar proporcional?">Prop.</label>
                <div class="form-check form-switch d-flex justify-content-center pt-1">
                    <input id="rule-proporcional-${rowIdx}" class="rule-proporcional form-check-input" type="checkbox" ${regla && regla.es_proporcional ? 'checked' : ''}>
                </div>
            </div>
            <div class="col-md-3">
                <label for="rule-cargo-${rowIdx}" class="small text-muted">Cargo Req. <span class="text-muted" style="font-size: 0.75rem">(multi)</span></label>
                <div class="input-group input-group-sm cargo-req-wrapper">
                    <input type="text" id="rule-cargo-${rowIdx}" class="rule-cargo form-control form-control-sm"
                        placeholder="Todos (o varios)"
                        value="${regla && regla.cargo_requerido ? regla.cargo_requerido : ''}"
                        autocomplete="off"
                        title="Puede ingresar uno o varios cargos separados por coma. Use el botón ▾ para seleccionar de la lista."
                        onclick="this.closest('.cargo-req-wrapper').querySelector('[data-bs-toggle=dropdown]').click()">
                    <button class="btn btn-outline-secondary dropdown-toggle px-2" type="button" data-bs-toggle="dropdown" aria-expanded="false"
                        onclick="_populateCargoDropdown(this.closest('.input-group').querySelector('.cargo-req-ul'), true)">
                        <i class="bi bi-chevron-down"></i>
                    </button>
                    <ul class="dropdown-menu dropdown-menu-end p-0 cargo-req-ul"
                        data-target-input="rule-cargo-${rowIdx}"
                        style="max-height: 300px; overflow-y: auto; width: 240px;">
                        <li class="p-2 position-sticky top-0 bg-white border-bottom z-1">
                            <input type="text" id="search-cargo-req-${rowIdx}" name="search-cargo-req-${rowIdx}" class="form-control form-control-sm" placeholder="Buscar cargo..."
                                onkeyup="filterCargosDropdown(this)"
                                onkeydown="event.stopPropagation()"
                                onclick="event.stopPropagation()"
                                autocomplete="off">
                        </li>
                        <li><a class="dropdown-item small py-2 cargo-item text-muted fst-italic" href="#" onclick="selectCargoRequerido(this, ''); return false;"><i class="bi bi-x-lg me-1" aria-hidden="true"></i>Limpiar selección</a></li>
                    </ul>
                </div>
            </div>
            <div class="col-md-5">
                <label for="rule-excluidos-${rowIdx}" class="small text-muted text-danger">Excluir Cargos</label>
                <div class="input-group input-group-sm">
                    <input type="text" id="rule-excluidos-${rowIdx}" class="rule-excluidos form-control"
                        placeholder="Ej: Gerente, Director"
                        value="${regla && regla.cargos_excluidos ? regla.cargos_excluidos : ''}">
                    <button class="btn btn-outline-secondary dropdown-toggle px-2" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                        <i class="bi bi-plus-circle"></i>
                    </button>
                    <ul class="dropdown-menu dropdown-menu-end p-0 cargo-dropdown-ul"
                        data-target-input="rule-excluidos-${rowIdx}"
                        style="max-height: 300px; overflow-y: auto; width: 250px;">
                        <li class="p-2 position-sticky top-0 bg-white border-bottom z-1">
                            <input type="text" id="search-cargo-excl-${rowIdx}" name="search-cargo-excl-${rowIdx}" class="form-control form-control-sm" placeholder="Buscar cargo..."
                                onkeyup="filterCargosDropdown(this)"
                                onkeydown="event.stopPropagation()"
                                onclick="event.stopPropagation()"
                                autocomplete="off">
                        </li>
                    </ul>
                </div>
            </div>
            <div class="col-md-1 text-end">
                <button type="button" class="btn btn-sm btn-outline-danger w-100" onclick="this.closest('.regla-row').remove()" title="Eliminar regla">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        </div>
    `;
    container.appendChild(div);

    // Poblar AMBOS dropdowns después de estar en el DOM
    // cargo-req-ul: singleSelect=true (un solo cargo)
    // cargo-dropdown-ul: singleSelect=false (multi, coma separado)
    _populateCargoDropdown(div.querySelector('.cargo-req-ul'), true);
    _populateCargoDropdown(div.querySelector('.cargo-dropdown-ul'), false);

    // Bootstrap Dropdown con strategy:'fixed': Popper.js calcula top/left relativos al viewport.
    // El CSS ya tiene #modal-bono .modal-content { overflow: visible !important } y
    // #modal-bono .dropdown-menu { z-index: 2300 !important } — suficiente para que el menu
    // escape el clip de #reglas-container y aparezca sobre el modal.
    // NO movemos el menu al body: eso rompía closest('.input-group') en los onclick.
    div.querySelectorAll('[data-bs-toggle="dropdown"]').forEach(btn => {
        const existing = bootstrap.Dropdown.getInstance(btn);
        if (existing) existing.dispose();

        new bootstrap.Dropdown(btn, {
            popperConfig(defaultConfig) {
                return { ...defaultConfig, strategy: 'fixed' };
            }
        });

        // Mover el menu al body al abrirlo: escapa overflow-y:auto de #reglas-container
        // sin depender de Popper coordinate fix (que falla dentro de modales fixed).
        // El input se localiza via data-target-input en la <ul>, no via closest().
        const menu = btn.closest('.input-group')?.querySelector('.dropdown-menu')
                  || btn.nextElementSibling;
        if (menu) {
            const originalParent = menu.parentElement;
            const originalNextSibling = menu.nextSibling;

            btn.addEventListener('show.bs.dropdown', () => {
                menu.style.zIndex = '9999';
                document.body.appendChild(menu);
                // Refrescar checkmarks: el usuario ve qué cargos ya están seleccionados
                _refreshDropdownChecks(menu);
            }, { passive: true });

            btn.addEventListener('hide.bs.dropdown', () => {
                menu.style.zIndex = '';
                if (originalNextSibling && originalNextSibling.parentElement === originalParent) {
                    originalParent.insertBefore(menu, originalNextSibling);
                } else {
                    originalParent.appendChild(menu);
                }
            }, { passive: true });
        }
    });
}

async function saveBono() {
    const id = document.getElementById('bono-id').value;
    const nombre = document.getElementById('bono-nombre').value;
    const descripcion = document.getElementById('bono-descripcion').value;
    const activo = document.getElementById('bono-activo').value === 'true';

    // Recolectar reglas
    const reglas = [];
    const ruleRows = document.querySelectorAll('.regla-row');
    ruleRows.forEach(row => {
        reglas.push({
            monto: parseFloat(row.querySelector('.rule-monto').value) || 0,
            tipo_contrato: row.querySelector('.rule-contrato').value || null,
            asistencia_minima: parseFloat(row.querySelector('.rule-asistencia').value) || 0.0,
            cargo_requerido: row.querySelector('.rule-cargo').value || null,
            cargos_excluidos: row.querySelector('.rule-excluidos').value || null,
            es_proporcional: row.querySelector('.rule-proporcional').checked
        });
    });
    // Recolectar áreas asignadas — buscar dentro del modal (no en todo el doc)
    const modalBonoEl = document.getElementById('modal-bono');
    const areaChecks = modalBonoEl
        ? modalBonoEl.querySelectorAll('.bono-area-chk:checked')
        : document.querySelectorAll('.bono-area-chk:checked');
    const area_ids = Array.from(areaChecks).map(chk => parseInt(chk.value));
    
    // Diagnóstico: solo visible en consola del dev, no en producción
    const totalAreas = modalBonoEl ? modalBonoEl.querySelectorAll('.bono-area-chk').length : 0;
    console.log(`[saveBono] id=${id || 'nuevo'} | checks marcados=${areaChecks.length}/${totalAreas} | area_ids=${JSON.stringify(area_ids)}`);
    // Enviar null solo si NO hay checkboxes renderizados (modal no cargó áreas)
    // Si hay checkboxes pero ninguno marcado, area_ids=[] es válido (desmarcar todo)
    const area_ids_payload = totalAreas === 0 ? null : area_ids;

    const body = { nombre, descripcion, activo, reglas, area_ids: area_ids_payload };
    const method = id ? 'PUT' : 'POST';
    const url = id ? `${API_CONFIG}bonos/${id}/` : `${API_CONFIG}bonos/`;

    const btnGuardar = document.querySelector('#modal-bono .btn-primary');
    btnGuardar.disabled = true;
    btnGuardar.textContent = 'Guardando...';

    try {
        const response = await fetch(url, {
            method,
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: JSON.stringify(body)
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || "Error al guardar bono");
        }

        showToast(`Listo. Bono ${id ? 'guardado' : 'creado'}.`, "success");
        closeModalBono(true);
        loadBonos();

        if (window.isWizardFlow && window.wizardCurrentStep === 'bonos') {
            Swal.fire({
                title: "Bono Guardado",
                text: "¿Desea crear otro bono o continuar al siguiente paso?",
                icon: "success",
                showCancelButton: true,
                confirmButtonText: "Crear otro bono",
                cancelButtonText: "Siguiente paso (Justificaciones)",
                reverseButtons: true
            }).then((result) => {
                if (result.isConfirmed) {
                    openModalBono();
                } else {
                    if (typeof window.abrirConfigJustificacionWizard === 'function') {
                        window.abrirConfigJustificacionWizard();
                    }
                }
            });
        }

    } catch (error) {
        console.error(error);
        Avisos.error("No se guardó el bono. " + error.message);
    } finally {
        btnGuardar.disabled = false;
        btnGuardar.textContent = 'Guardar Bono';
    }
}

function editBono(id) {
    const bono = bonosList.find(b => b.id === id);
    if (bono) openModalBono(bono);
}

async function confirmDeleteBono(id) {
    if (await uiConfirm('¿Eliminar este bono?', { items: ['Deja de calcularse para todas las personas.', 'No se puede deshacer.'], confirmText: 'Eliminar bono', danger: true })) {
        deleteBono(id);
    }
}

async function deleteBono(id) {
    try {
        const response = await fetch(`${API_CONFIG}bonos/${id}/`, { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` },  method: 'DELETE' });
        if (!response.ok) throw new Error("Error al eliminar");
        showToast("Listo. Bono eliminado.", "success");
        loadBonos();
    } catch (error) {
        alert(error.message);
    }
}

// ==========================================
// JUSTIFICACIONES: DATOS Y RENDER
// ==========================================
async function loadTiposJustificacion() {
    try {
        const response = await fetch(`${API_CONFIG}justificaciones/tipos/?all=true`);
        if (!response.ok) throw new Error("Error cargando tipos");
        tiposJustificacionList = await response.json();
        renderTiposJustificacion();
    } catch (error) {
        console.error(error);
    }
}

// Global scope functions
window.sortJustificaciones = function (key) {
    TableSorter.sort(tiposJustificacionList, key, 'justificaciones');
    renderTiposJustificacion();
};

window.renderTiposJustificacion = function () {
    // Diseño B (01-11-2026): lista de tipos a la izquierda y su ficha a la derecha; se cambia ahí mismo, sin ventana.
    // La ventana «modal-tipo-justificacion» sigue existiendo para el asistente de configuración inicial (sync_wizard).
    const container = document.getElementById('tab-justificaciones');
    if (!container || !window.FichaCfg) return;
    const F = window.FichaCfg;
    const canEdit = F.puede('configuracion.justificaciones');
    const items = tiposJustificacionList.slice().sort(function (a, b) { return String(a.nombre).localeCompare(String(b.nombre), 'es'); });
    F.montar(container, {
        clave: 'just',
        titulo: 'Justificaciones',
        descripcion: 'Tipos de permiso y licencia que se pueden registrar a una persona. Definen si el día se paga y quién lo paga.',
        acciones: canEdit ? '<button type="button" class="fcB-btn pri" onclick="FichaCfg.nuevo(\'just\')"><i class="bi bi-plus-lg" aria-hidden="true"></i>Nuevo tipo</button>' : '',
        items: items,
        id: function (t) { return t.id; },
        etiqueta: function (t) { return t.nombre; },
        sub: function (t) { return t.con_goce_sueldo ? 'Con goce' : 'Sin goce'; },
        apagado: function (t) { return !t.activo; },
        vacio: 'No hay tipos de justificación. Cree el primero con «Nuevo tipo».',
        ficha: function (t, panel) { fichaTipoJ(t, panel, canEdit); }
    });
};

async function pagadoresParaFicha() {
    if (typeof pagadoresList !== 'undefined' && pagadoresList && pagadoresList.length) return pagadoresList;
    try {
        const r = await fetch(API_CONFIG + 'pagadores/', { headers: { 'Authorization': 'Bearer ' + localStorage.getItem('access_token') } });
        return r.ok ? await r.json() : [];
    } catch (e) { return []; }
}

async function fichaTipoJ(t, panel, canEdit) {
    const F = window.FichaCfg, esNuevo = !t;
    t = t || { nombre: '', nomenclatura: '', descripcion: '', con_goce_sueldo: true, dias_corridos: false, pagador: 'Empleador', dias_defecto: null,
               activo: true, min_dias: 1, max_dias: null, frecuencia_anual: null, sobreescribe_feriados: false, es_horas_sindicales: false,
               es_por_horas: false, genera_deuda_horaria: false };
    const pag = await pagadoresParaFicha();
    const opsPag = pag.map(function (p) { return [p.nombre, p.nombre]; });
    if (t.pagador && !opsPag.some(function (o) { return o[0] === t.pagador; })) opsPag.unshift([t.pagador, t.pagador]);
    const ro = !canEdit;
    panel.innerHTML = F.cabeza(esNuevo ? 'Nuevo tipo de justificación' : t.nombre,
            canEdit ? 'Se cambia aquí mismo. Los cambios valen desde que se guardan.' : 'Solo lectura: su usuario no puede cambiar las justificaciones.')
        + F.campo('Nombre', F.texto('fj-nombre', t.nombre), '', 'fj-nombre')
        + F.campo('Sigla', F.texto('fj-sigla', t.nomenclatura || '', ' maxlength="8"'), 'La que se ve en la grilla, por ejemplo LM o VAC.', 'fj-sigla')
        + F.campo('Cómo se cuentan los días', F.seg('fj-periodo', [['true', 'Días hábiles'], ['false', 'Días corridos']], t.dias_corridos ? 'false' : 'true', ro),
            'Hábiles: de lunes a viernes. Corridos: todos los días.')
        + F.campo('Goce de sueldo', F.seg('fj-goce', [['true', 'Sí, se paga'], ['false', 'No se paga']], t.con_goce_sueldo ? 'true' : 'false', ro))
        + F.campo('Quién paga', F.lista('fj-pagador', opsPag, t.pagador || 'Empleador'), '', 'fj-pagador')
        + F.campo('Días por defecto', F.numero('fj-dias', t.dias_defecto, ' min="0"'), 'Los que se proponen al registrarla. Vacío: se eligen a mano.', 'fj-dias')
        + F.campo('En uso', F.interruptor('fj-activo', t.activo, 'Se puede elegir al justificar un día'))
        + F.mas('Más opciones',
            F.campo('Mínimo de días', F.numero('fj-min', t.min_dias || 1, ' min="1"'), '', 'fj-min')
            + F.campo('Máximo de días', F.numero('fj-max', t.max_dias, ' min="1"'), 'Vacío: sin máximo.', 'fj-max')
            + F.campo('Veces al año', F.numero('fj-frec', t.frecuencia_anual, ' min="1"'), 'Vacío: sin límite.', 'fj-frec')
            + F.campo('Si cae en un feriado', F.seg('fj-feriados', [['false', 'Respeta el feriado'], ['true', 'Reemplaza al feriado']], t.sobreescribe_feriados ? 'true' : 'false', ro))
            + F.campo('Horas sindicales', F.seg('fj-sindical', [['false', 'No'], ['true', 'Sí']], t.es_horas_sindicales ? 'true' : 'false', ro))
            + F.campo('Duración', F.seg('fj-parcial', [['false', 'Día completo'], ['true', 'Por horas']], t.es_por_horas ? 'true' : 'false', ro), 'Por horas: un permiso de parte del día.')
            + F.campo('Genera deuda de horas', F.seg('fj-deuda', [['false', 'No'], ['true', 'Sí, se recuperan']], t.genera_deuda_horaria ? 'true' : 'false', ro))
            + F.campo('Descripción', F.area('fj-desc', t.descripcion || ''), '', 'fj-desc'))
        + (canEdit ? F.pie(esNuevo ? '' : '<button type="button" class="fcB-btn borra" id="fj-borrar"><i class="bi bi-trash3" aria-hidden="true"></i>Eliminar tipo</button>',
            '<button type="button" class="fcB-btn" id="fj-descartar">Descartar</button><button type="button" class="fcB-btn pri" id="fj-guardar">' + (esNuevo ? 'Crear tipo' : 'Guardar cambios') + '</button>') : '');
    if (ro) { panel.querySelectorAll('select, input, textarea').forEach(function (e) { e.disabled = true; }); return; }
    panel.querySelector('#fj-descartar').onclick = function () { F.pintarFicha('just'); };
    const borrar = panel.querySelector('#fj-borrar');
    if (borrar) borrar.onclick = function () { confirmDeleteTipoJ(t.id); };
    panel.querySelector('#fj-guardar').onclick = function (ev) { guardarFichaTipoJ(t, panel, ev.currentTarget); };
}

async function guardarFichaTipoJ(t, panel, btn) {
    const F = window.FichaCfg;
    const v = function (id) { return panel.querySelector('#' + id).value.trim(); };
    const num = function (id) { const x = v(id); return x ? parseInt(x, 10) : null; };
    const nombre = v('fj-nombre');
    if (!nombre) { showToast('Falta el nombre del tipo.', 'warning'); panel.querySelector('#fj-nombre').focus(); return; }
    const goce = F.leerSeg(panel, 'fj-goce') === 'true', habiles = F.leerSeg(panel, 'fj-periodo') === 'true';
    const body = {
        nombre: nombre, nomenclatura: v('fj-sigla'), descripcion: v('fj-desc'), con_goce_sueldo: goce,
        dias_habiles: habiles, dias_corridos: !habiles, pagador: panel.querySelector('#fj-pagador').value, dias_defecto: num('fj-dias'),
        activo: panel.querySelector('#fj-activo').checked, min_dias: num('fj-min') || 1, max_dias: num('fj-max'), frecuencia_anual: num('fj-frec'),
        sobreescribe_feriados: F.leerSeg(panel, 'fj-feriados') === 'true', es_horas_sindicales: F.leerSeg(panel, 'fj-sindical') === 'true',
        descuenta_remuneracion: !goce, es_por_horas: F.leerSeg(panel, 'fj-parcial') === 'true', genera_deuda_horaria: F.leerSeg(panel, 'fj-deuda') === 'true'
    };
    await F.trabajando(btn, async function () {
        const r = await fetch(API_CONFIG + 'justificaciones/tipos/' + (t.id ? t.id + '/' : ''), {
            method: t.id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + localStorage.getItem('access_token') },
            body: JSON.stringify(body)
        });
        const d = await r.json().catch(function () { return {}; });
        if (!r.ok) { showToast(d.detail || 'No se pudo guardar el tipo.', 'danger'); return; }
        showToast(t.id ? 'Listo. Cambios guardados.' : 'Listo. Tipo creado.', 'success');
        if (d && d.id) F.recordar('just', d.id);
        await loadTiposJustificacion();
    });
}

// ==========================================
// JUSTIFICACIONES: MODAL Y FORMULARIO
// ==========================================
window.openModalTipoJ = function(tipo = null) {
    const modal = document.getElementById('modal-tipo-justificacion');
    const title = document.getElementById('modal-tipo-j-title');
    const form = document.getElementById('form-tipo-justificacion');

    form.reset();

    if (tipo) {
        title.innerText = 'Editar Tipo de Justificación';
        document.getElementById('tipo-j-id').value = tipo.id;
        document.getElementById('tipo-j-nombre').value = tipo.nombre;
        document.getElementById('tipo-j-nomenclatura').value = tipo.nomenclatura || '';
        document.getElementById('tipo-j-descripcion').value = tipo.descripcion || '';
        document.getElementById('tipo-j-goce').value = tipo.con_goce_sueldo ? 'true' : 'false';
        document.getElementById('tipo-j-periodo').value = tipo.dias_corridos ? 'false' : 'true';
        document.getElementById('tipo-j-pagador').value = tipo.pagador || 'Empleador';
        document.getElementById('tipo-j-dias-defecto').value = tipo.dias_defecto !== undefined && tipo.dias_defecto !== null ? tipo.dias_defecto : '';
        document.getElementById('tipo-j-activo').value = tipo.activo ? 'true' : 'false';

        // Reglas Avanzadas
        document.getElementById('tipo-j-min-dias').value = tipo.min_dias || 1;
        document.getElementById('tipo-j-max-dias').value = tipo.max_dias || '';
        document.getElementById('tipo-j-frecuencia').value = tipo.frecuencia_anual || '';
        document.getElementById('tipo-j-feriados').value = tipo.sobreescribe_feriados ? 'true' : 'false';
        document.getElementById('tipo-j-sindical').value = tipo.es_horas_sindicales ? 'true' : 'false';

        // [NEW] Permisos Parciales y Deuda
        document.getElementById('tipo-j-parcial').value = tipo.es_por_horas ? 'true' : 'false';
        document.getElementById('tipo-j-deuda').value = tipo.genera_deuda_horaria ? 'true' : 'false';

    } else {
        title.innerText = 'Nuevo Tipo de Justificación';
        document.getElementById('tipo-j-id').value = '';
        document.getElementById('tipo-j-nomenclatura').value = '';
        document.getElementById('tipo-j-pagador').value = 'Empleador';
        document.getElementById('tipo-j-dias-defecto').value = '';

        // Default Reglas Avanzadas
        document.getElementById('tipo-j-min-dias').value = 1;
        document.getElementById('tipo-j-max-dias').value = '';
        document.getElementById('tipo-j-frecuencia').value = '';
        document.getElementById('tipo-j-feriados').value = 'false';
        document.getElementById('tipo-j-sindical').value = 'false';

        // [NEW] Permisos Parciales y Deuda
        document.getElementById('tipo-j-parcial').value = 'false';
        document.getElementById('tipo-j-deuda').value = 'false';
    }

    modal.style.display = 'flex';
}

function closeModalTipoJ(fromSave = false) {
    document.getElementById('modal-tipo-justificacion').style.display = 'none';

    // BUG-03 FIX: Si se abrió desde el wizard vía _wizardAbrirTipoJ, ejecutar callback de cierre
    if (typeof window._wizardTipoJCloseCallback === 'function') {
        setTimeout(window._wizardTipoJCloseCallback, 100);
        return; // El callback maneja el flujo del wizard
    }

    if (!fromSave && window.isWizardFlow && window.wizardCurrentStep === 'justificaciones') {
        Swal.fire({
            title: "¿Finalizar Configuración?",
            text: "No has guardado la justificación. ¿Deseas finalizar la configuración inicial?",
            icon: "warning",
            showCancelButton: true,
            confirmButtonText: "Sí, finalizar",
            cancelButtonText: "No, seguir editando",
            reverseButtons: true
        }).then((result) => {
            if (result.isConfirmed) {
                // Finalizar flujo y continuar
                window.isWizardFlow = false;
                window.wizardCurrentStep = null;
                Swal.fire({
                    title: "Configuración lista",
                    text: "Ahora puede sincronizar a las personas.",
                    icon: "success",
                    confirmButtonText: "Ir a Sincronización"
                }).then(() => {
                    const btnSincronizar = document.getElementById('sincronizar-datos');
                    if (btnSincronizar) {
                        btnSincronizar.click();
                    } else if (typeof window.syncEmpleados === 'function') {
                        window.syncEmpleados();
                    }
                });
            } else {
                openModalTipoJ();
            }
        });
    }
}

async function saveTipoJustificacion() {
    const id = document.getElementById('tipo-j-id').value;
    const minDias = document.getElementById('tipo-j-min-dias').value;
    const maxDias = document.getElementById('tipo-j-max-dias').value;
    const frecuencia = document.getElementById('tipo-j-frecuencia').value;
    const diasDefectoVal = document.getElementById('tipo-j-dias-defecto').value;

    const body = {
        nombre: document.getElementById('tipo-j-nombre').value,
        nomenclatura: document.getElementById('tipo-j-nomenclatura').value,
        descripcion: document.getElementById('tipo-j-descripcion').value,
        con_goce_sueldo: document.getElementById('tipo-j-goce').value === 'true',

        // Mapeo UI -> Backend
        dias_habiles: document.getElementById('tipo-j-periodo').value === 'true', // Compatibilidad (inverso de dias_corridos)
        dias_corridos: document.getElementById('tipo-j-periodo').value === 'false', // Fuente de verdad para el motor

        pagador: document.getElementById('tipo-j-pagador').value,
        dias_defecto: diasDefectoVal ? parseInt(diasDefectoVal) : null,
        activo: document.getElementById('tipo-j-activo').value === 'true',

        // Reglas Avanzadas
        min_dias: minDias ? parseInt(minDias) : 1,
        max_dias: maxDias ? parseInt(maxDias) : null,
        frecuencia_anual: frecuencia ? parseInt(frecuencia) : null,
        sobreescribe_feriados: document.getElementById('tipo-j-feriados').value === 'true',
        es_horas_sindicales: document.getElementById('tipo-j-sindical').value === 'true',

        // Mapeo Goce -> Descuenta
        descuenta_remuneracion: document.getElementById('tipo-j-goce').value === 'false',

        // [NEW] Permisos Parciales y Deuda
        es_por_horas: document.getElementById('tipo-j-parcial').value === 'true',
        genera_deuda_horaria: document.getElementById('tipo-j-deuda').value === 'true'
    };

    const method = id ? 'PUT' : 'POST';
    const url = id ? `${API_CONFIG}justificaciones/tipos/${id}/` : `${API_CONFIG}justificaciones/tipos/`;

    try {
        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (!response.ok) throw new Error("Error al guardar");

        showToast("Listo. Cambios guardados.", "success");
        closeModalTipoJ(true);
        loadTiposJustificacion();

        if (window.isWizardFlow && window.wizardCurrentStep === 'justificaciones') {
            Swal.fire({
                title: "Justificación Guardada",
                text: "¿Desea crear otra o continuar a la Sincronización Final?",
                icon: "success",
                showCancelButton: true,
                confirmButtonText: "Crear otra",
                cancelButtonText: "Ir a Sincronización",
                reverseButtons: true
            }).then((result) => {
                if (result.isConfirmed) {
                    openModalTipoJ(); // It's openModalTipoJ according to the definition below
                } else {
                    if (typeof window.irASincronizacionFinal === 'function') {
                        window.irASincronizacionFinal();
                    }
                }
            });
        }

    } catch (error) {
        alert(error.message);
    }
}

function editTipoJ(id) {
    const tipo = tiposJustificacionList.find(t => t.id === id);
    if (tipo) openModalTipoJ(tipo);
}

async function confirmDeleteTipoJ(id) {
    if (await uiConfirm('¿Eliminar este tipo de justificación?', { items: ['Ya no se podrá elegir al justificar un día.'], confirmText: 'Eliminar tipo', danger: true })) {
        deleteTipoJ(id);
    }
}

async function deleteTipoJ(id) {
    try {
        const response = await fetch(`${API_CONFIG}justificaciones/tipos/${id}/`, { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` },  method: 'DELETE' });
        if (!response.ok) throw new Error("No se puede eliminar (posiblemente en uso)");
        showToast("Listo. Tipo de justificación eliminado.", "success");
        loadTiposJustificacion();
    } catch (error) {
        alert(error.message);
    }
}

// ==========================================
// PAGADORES: LÓGICA Y UI [NEW]
// ==========================================
async function loadPagadores() {
    try {
        const response = await fetch(`${API_CONFIG}pagadores/`);
        if (!response.ok) throw new Error("Error cargando pagadores");
        pagadoresList = await response.json();

        // Poblar selects
        const select = document.getElementById('tipo-j-pagador');
        if (select) {
            select.innerHTML = '<option value="">Seleccione...</option>' +
                pagadoresList.map(p => `<option value="${p.nombre}">${p.nombre}</option>`).join('');
        }
    } catch (error) {
        console.error(error);
    }
}

window.openModalGestionPagadores = function () {
    renderPagadoresList();
    document.getElementById('modal-gestion-pagadores').style.display = 'flex';
}

window.closeModalGestionPagadores = async function () {
    document.getElementById('modal-gestion-pagadores').style.display = 'none';
    await loadPagadores();

    // BUG-03 FIX: Si se abrió desde el wizard vía _wizardAbrirPagadores, ejecutar callback de cierre
    if (typeof window._wizardPagadoresCloseCallback === 'function') {
        setTimeout(window._wizardPagadoresCloseCallback, 100);
        return; // El callback maneja el flujo del wizard
    }
    if (window.isWizardFlow && window.wizardCurrentStep === 'justificaciones') {
        if (typeof pagadoresList !== 'undefined' && pagadoresList.length > 0) {
            if (typeof window.openModalTipoJ === 'function') {
                window.openModalTipoJ();
            } else if (typeof openModalTipoJ === 'function') {
                openModalTipoJ();
            }
        } else {
            // Si no crearon ninguno, volver a mostrar el modal del wizard para no dejar la pantalla en negro
            const modalEl = document.getElementById('modal-wizard-configuracion');
            if (modalEl) {
                const m = bootstrap.Modal.getOrCreateInstance(modalEl);
                m.show();
            }
        }
    }
}

function renderPagadoresList() {
    // La ventana «Gestionar pagadores» (desde una justificación) sigue con su tabla; la pestaña usa el diseño B.
    const html = pagadoresList.map(p => `
        <tr>
            <td class="small fw-bold">${p.nombre}</td>
            <td><span class="badge ${p.activo ? 'bg-success' : 'bg-secondary'}">${p.activo ? 'Activo' : 'Inactivo'}</span></td>
            <td class="text-end">
                <button class="btn btn-sm text-danger" onclick="togglePagador(${p.id}, ${!p.activo})" title="Cambiar Estado">
                    <i class="bi bi-power"></i>
                </button>
            </td>
        </tr>
    `).join('') || '<tr><td colspan="3" class="text-center text-muted">No hay pagadores extra.</td></tr>';

    const bodyModal = document.getElementById('pagadores-list-body');
    if (bodyModal) bodyModal.innerHTML = html;
    pagadoresFichaB();
}

function pagadoresFichaB() {
    const cont = document.getElementById('pagadores-fcb');
    if (!cont || !window.FichaCfg) return;
    const F = window.FichaCfg;
    const canEdit = F.puede('configuracion.editar');
    F.montar(cont, {
        clave: 'pagadores',
        titulo: 'Pagadores',
        descripcion: 'Quién paga cada justificación o beneficio: el empleador, Fonasa, la mutual u otra entidad.',
        acciones: canEdit ? '<button type="button" class="fcB-btn pri" onclick="FichaCfg.nuevo(\'pagadores\')"><i class="bi bi-plus-lg" aria-hidden="true"></i>Nuevo pagador</button>' : '',
        items: pagadoresList.slice().sort(function (a, b) { return String(a.nombre).localeCompare(String(b.nombre), 'es'); }),
        id: function (p) { return p.id; },
        etiqueta: function (p) { return p.nombre; },
        apagado: function (p) { return !p.activo; },
        vacio: 'No hay pagadores.',
        ficha: function (p, panel) {
            const nuevo = !p;
            p = p || { nombre: '', activo: true };
            panel.innerHTML = F.cabeza(nuevo ? 'Nuevo pagador' : p.nombre, canEdit ? 'Se cambia aquí mismo.' : 'Solo lectura.')
                + F.campo('Nombre', F.texto('fpag-nombre', p.nombre), '', 'fpag-nombre')
                + F.campo('En uso', F.interruptor('fpag-activo', p.activo, 'Se puede elegir en una justificación'))
                + (canEdit ? F.pie('', '<button type="button" class="fcB-btn" id="fpag-descartar">Descartar</button><button type="button" class="fcB-btn pri" id="fpag-guardar">' + (nuevo ? 'Crear pagador' : 'Guardar cambios') + '</button>') : '');
            if (!canEdit) { panel.querySelectorAll('input').forEach(function (e) { e.disabled = true; }); return; }
            panel.querySelector('#fpag-descartar').onclick = function () { F.pintarFicha('pagadores'); };
            panel.querySelector('#fpag-guardar').onclick = function (ev) {
                const nombre = panel.querySelector('#fpag-nombre').value.trim();
                if (!nombre) { showToast('Falta el nombre del pagador.', 'warning'); return; }
                F.trabajando(ev.currentTarget, async function () {
                    const r = await fetch(API_CONFIG + 'pagadores/' + (p.id ? p.id + '/' : ''), {
                        method: p.id ? 'PUT' : 'POST',
                        headers: { 'Authorization': 'Bearer ' + localStorage.getItem('access_token'), 'Content-Type': 'application/json' },
                        body: JSON.stringify({ nombre: nombre, activo: panel.querySelector('#fpag-activo').checked })
                    });
                    const d = await r.json().catch(function () { return {}; });
                    if (!r.ok) { showToast(d.detail || 'No se pudo guardar el pagador.', 'danger'); return; }
                    showToast(p.id ? 'Listo. Cambios guardados.' : 'Listo. Pagador agregado.', 'success');
                    if (d && d.id) F.recordar('pagadores', d.id);
                    await loadPagadores();
                    renderPagadoresList();
                });
            };
        }
    });
}

window.openTabPagadores = function () {
    renderPagadoresList();
}

window.addPagador = async function () {
    const input = document.getElementById('new-pagador-nombre');
    const nombre = input.value.trim();
    if (!nombre) return;

    try {
        const response = await fetch(`${API_CONFIG}pagadores/`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre, activo: true })
        });
        if (!response.ok) throw new Error("Error al añadir");

        input.value = '';
        showToast("Listo. Pagador agregado.", "success");
        await loadPagadores();
        renderPagadoresList();
    } catch (error) {
        alert(error.message);
    }
}

window.togglePagador = async function (id, nuevoEstado) {
    const p = pagadoresList.find(x => x.id === id);
    if (!p) return;

    try {
        const response = await fetch(`${API_CONFIG}pagadores/${id}/`, {
            method: 'PUT',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre: p.nombre, activo: nuevoEstado })
        });
        if (!response.ok) throw new Error("Error al actualizar");

        await loadPagadores();
        renderPagadoresList();
    } catch (error) {
        alert(error.message);
    }
}

// ==========================================
// AJUSTES GLOBALES: NOTIFICACIONES [NEW]
// ==========================================
async function loadEmailSettings() {
    const emailRRHH = document.getElementById('email-notificaciones-rrhh');
    const emailCierreRRHH = document.getElementById('email-notificaciones-cierre-rrhh');
    if (emailRRHH) {
        try {
            const res = await fetch(`${API_CONFIG}ajustes/email_notificaciones_rrhh/`);
            if (res.ok) {
                const data = await res.json();
                emailRRHH.value = data || '';
            }
        } catch (e) {
            console.error("Error cargando email de notificaciones globales", e);
        }
    }
    if (emailCierreRRHH) {
        try {
            const res = await fetch(`${API_CONFIG}ajustes/email_notificaciones_cierre_rrhh/`);
            if (res.ok) {
                const data = await res.json();
                emailCierreRRHH.value = data || '';
            }
        } catch (e) {
            console.error("Error cargando email de notificaciones de cierre", e);
        }
    }
}

window.saveGlobalAjustes = async function () {
    const emailRRHH = document.getElementById('email-notificaciones-rrhh');
    const emailCierreRRHH = document.getElementById('email-notificaciones-cierre-rrhh');
    if (!emailRRHH && !emailCierreRRHH) return;

    const btn = document.querySelector('#tab-correo .btn-primary');
    if (btn) btn.disabled = true;

    try {
        if (emailRRHH) {
            const response = await fetch(`${API_CONFIG}ajustes/email_notificaciones_rrhh/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(emailRRHH.value.trim())
            });
            if (!response.ok) throw new Error("Error al guardar correos globales");
        }

        if (emailCierreRRHH) {
            const responseCierre = await fetch(`${API_CONFIG}ajustes/email_notificaciones_cierre_rrhh/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(emailCierreRRHH.value.trim())
            });
            if (!responseCierre.ok) throw new Error("Error al guardar correos exclusivos de cierre");
        }

        showToast("Listo. Ajustes de correo guardados.", "success");
    } catch (e) {
        Avisos.error("No se guardaron los ajustes de correo. " + e.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

window.loadAreaNotificaciones = async function () {
    // Diseño B (01-11-2026): la pestaña Correo es una lista («Avisos generales» y cada área) con su ficha
    if (document.getElementById('correo-fcb')) return correoFichaB();
};

async function correoFichaB() {
    const cont = document.getElementById('correo-fcb');
    if (!cont || !window.FichaCfg) return;
    const F = window.FichaCfg, canEdit = F.puede('configuracion.editar');
    const leer = async function (url, porDefecto) {
        try { const r = await fetch(url, { headers: { 'Authorization': 'Bearer ' + localStorage.getItem('access_token') } }); return r.ok ? await r.json() : porDefecto; }
        catch (e) { return porDefecto; }
    };
    const res = await Promise.all([leer(API_CONFIG + 'ajustes/email_notificaciones_rrhh/', ''), leer(API_CONFIG + 'ajustes/email_notificaciones_cierre_rrhh/', ''),
                                   leer(API_CONFIG + 'notificaciones_areas/', []), leer('/api/configuracion/areas/', [])]);
    const porArea = {};
    (res[2] || []).forEach(function (a) { porArea[String(a.area).toUpperCase()] = a.emails; });
    const nombres = (res[3] || []).map(function (a) { return String(a.nombre).toUpperCase(); });
    Object.keys(porArea).forEach(function (a) { if (nombres.indexOf(a) < 0) nombres.push(a); });
    nombres.sort(function (a, b) { return a.localeCompare(b, 'es'); });
    const items = [{ id: 'general', nombre: 'Avisos generales', emails: null }].concat(nombres.map(function (n) { return { id: n, nombre: n, emails: porArea[n] || '' }; }));
    F.montar(cont, {
        clave: 'correo',
        titulo: 'Correo',
        descripcion: 'A quién le llegan los avisos por correo. Un área sin correos propios usa los de «Avisos generales».',
        items: items,
        id: function (x) { return x.id; },
        etiqueta: function (x) { return x.nombre; },
        sub: function (x) { if (x.id === 'general') return ''; const n = x.emails ? x.emails.split(',').filter(function (e) { return e.trim(); }).length : 0; return n ? n + (n === 1 ? ' correo' : ' correos') : 'Usa los generales'; },
        ficha: function (x, panel) {
            if (x.id === 'general') {
                panel.innerHTML = F.cabeza('Avisos generales', 'Para todas las áreas que no tienen correos propios.')
                    + F.campo('Avisos de RRHH', '<input type="text" class="fcB-inp" id="email-notificaciones-rrhh" value="' + F.esc(res[0] || '') + '" placeholder="rrhh@empresa.cl">', 'Separe varios correos con coma.', 'email-notificaciones-rrhh')
                    + F.campo('Avisos de cierre del período', '<input type="text" class="fcB-inp" id="email-notificaciones-cierre-rrhh" value="' + F.esc(res[1] || '') + '" placeholder="gerencia@empresa.cl">', 'Reciben el acta cuando se cierra un tramo.', 'email-notificaciones-cierre-rrhh')
                    + (canEdit ? F.pie('', '<button type="button" class="fcB-btn" id="fco-descartar">Descartar</button><button type="button" class="fcB-btn pri btn-primary" id="fco-guardar">Guardar cambios</button>') : '');
                if (!canEdit) { panel.querySelectorAll('input').forEach(function (e) { e.disabled = true; }); return; }
                panel.querySelector('#fco-descartar').onclick = function () { F.pintarFicha('correo'); };
                panel.querySelector('#fco-guardar').onclick = async function () { await saveGlobalAjustes(); res[0] = panel.querySelector('#email-notificaciones-rrhh').value.trim(); res[1] = panel.querySelector('#email-notificaciones-cierre-rrhh').value.trim(); };
                return;
            }
            panel.innerHTML = F.cabeza(x.nombre, x.emails ? 'Los avisos de las personas de esta área llegan a estos correos.' : 'Esta área todavía usa los correos de «Avisos generales».')
                + F.campo('Correos del área', '<input type="text" class="fcB-inp" id="fco-emails" value="' + F.esc(x.emails || '') + '" placeholder="jefe.area@empresa.cl">', 'Separe varios correos con coma.', 'fco-emails')
                + (canEdit ? F.pie(x.emails ? '<button type="button" class="fcB-btn borra" id="fco-quitar"><i class="bi bi-trash3" aria-hidden="true"></i>Quitar correos del área</button>' : '',
                    '<button type="button" class="fcB-btn" id="fco-descartar">Descartar</button><button type="button" class="fcB-btn pri" id="fco-guardar">Guardar cambios</button>') : '');
            if (!canEdit) { panel.querySelectorAll('input').forEach(function (e) { e.disabled = true; }); return; }
            panel.querySelector('#fco-descartar').onclick = function () { F.pintarFicha('correo'); };
            const quitar = panel.querySelector('#fco-quitar');
            if (quitar) quitar.onclick = function () { deleteAreaNotificaciones(x.nombre); };
            panel.querySelector('#fco-guardar').onclick = function (ev) {
                const emails = panel.querySelector('#fco-emails').value.trim();
                if (!emails) { showToast('Escriba al menos un correo, o use «Quitar correos del área».', 'warning'); return; }
                F.trabajando(ev.currentTarget, async function () {
                    const r = await fetch(API_CONFIG + 'notificaciones_areas/', {
                        method: 'POST',
                        headers: { 'Authorization': 'Bearer ' + localStorage.getItem('access_token'), 'Content-Type': 'application/json' },
                        body: JSON.stringify({ area: x.nombre, emails: emails })
                    });
                    if (!r.ok) { showToast('No se guardaron los correos del área.', 'danger'); return; }
                    showToast('Listo. Se guardaron los correos de aviso del área ' + x.nombre + '.', 'success');
                    await correoFichaB();
                });
            };
        }
    });
}

window.deleteAreaNotificaciones = async function (area) {
    if (!await uiConfirm(`¿Quitar los correos de aviso del área ${area}?`, { items: ['El área deja de recibir los avisos por correo.'], confirmText: 'Quitar correos', danger: true })) return;
    
    try {
        const res = await fetch(`${API_CONFIG}notificaciones_areas/${encodeURIComponent(area)}/`, { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }, 
            method: 'DELETE'
        });
        
        if (!res.ok) throw new Error("Error al eliminar");
        
        showToast("Listo. El área ya no recibe avisos por correo.", "success");
        loadAreaNotificaciones();
    } catch (e) {
        Avisos.error("No se quitaron los correos de aviso del área. " + e.message);
    }
}

// Helper para Notificaciones
function showToast(msg, type = "success") {
    if (window.Avisos) window.Avisos.avisar(msg, type);
    else alert(msg);
}


// ==========================================
// ROBOT BIOALBA LOGS [NEW]
// ==========================================
window.loadRobotSyncLogs = async function() {
    // Diseño B (02-11-2026): ejecuciones del robot a la izquierda y su detalle a la derecha (solo lectura).
    const cont = document.getElementById('robot-fcb');
    if (!cont || !window.FichaCfg) return;
    const F = window.FichaCfg;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    let logs = [];
    try {
        const response = await fetch('/api/sync/logs/', { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }, signal: controller.signal });
        clearTimeout(timeoutId);
        if (!response.ok) throw new Error('No se pudo leer el registro del robot.');
        logs = await response.json() || [];
    } catch (e) {
        cont.innerHTML = '<p class="fcB-vacio">' + F.esc(e.name === 'AbortError' ? 'El servidor tardó demasiado en responder.' : e.message)
            + ' <button type="button" class="fcB-btn" onclick="loadRobotSyncLogs()">Reintentar</button></p>';
        return;
    }
    const cuando = function (raw) {
        if (!raw) return 'Sin fecha';
        const p = String(raw).split(/[\sT]/);
        return (window.formatFechaDDMMYYYY ? window.formatFechaDDMMYYYY(p[0]) : p[0]) + (p[1] ? ' ' + p[1].split('.')[0].slice(0, 5) : '');
    };
    F.montar(cont, {
        clave: 'robot',
        titulo: 'Robot BioAlba',
        descripcion: 'Últimas ejecuciones del robot que trae las marcas desde BioAlba, automáticas o a mano. Solo se consulta: no se cambia nada desde aquí.',
        acciones: '<button type="button" class="fcB-btn" onclick="loadRobotSyncLogs()"><i class="bi bi-arrow-clockwise" aria-hidden="true"></i>Actualizar</button>',
        items: logs,
        id: function (l) { return l.id; },
        etiqueta: function (l) { return cuando(l.fecha_inicio); },
        sub: function (l) { const e = l.errores || 0; return e ? e + (e === 1 ? ' error' : ' errores') : 'Sin errores'; },
        vacio: 'Todavía no hay ejecuciones registradas.',
        ficha: function (l, panel) {
            const e = l.errores || 0;
            const dur = l.duracion_segundos != null ? Number(l.duracion_segundos).toLocaleString('es-CL', { maximumFractionDigits: 1 }) + ' segundos' : 'Sin dato';
            panel.innerHTML = F.cabeza('Ejecución del ' + cuando(l.fecha_inicio), e ? 'Terminó con ' + e + (e === 1 ? ' error.' : ' errores.') : 'Terminó sin errores.')
                + F.campo('Tipo', '<span>' + F.esc(String(l.tipo_sync || 'COMPLETA').charAt(0) + String(l.tipo_sync || 'COMPLETA').slice(1).toLowerCase()) + '</span>')
                + F.campo('Marcas nuevas o días recalculados', '<span class="num">' + F.esc(l.marcaciones_nuevas || l.dias_recalculados || 0) + '</span>')
                + F.campo('Errores', '<span class="num">' + F.esc(e) + '</span>')
                + F.campo('Duración', '<span class="num">' + F.esc(dur) + '</span>')
                + (l.detalle ? F.campo('Detalle', '<pre class="fcB-nota" style="white-space:pre-wrap;margin:0;max-height:320px;overflow:auto;font:500 12.5px/1.5 \'Barlow\',sans-serif;width:100%">' + F.esc(l.detalle) + '</pre>') : '');
        }
    });
}

// ==========================================
// AJUSTES DEL SISTEMA [NEW]
// ==========================================
window.loadAjustesSistema = async function() {
    try {
        const response = await fetch(`${API_CONFIG}ajustes/`);
        if (!response.ok) throw new Error("Error obteniendo ajustes del sistema");
        const ajustes = await response.json();

        // Mapeo de clave de DB a ID de input
        const mapIds = {
            'limite_contratos_temporales': 'ajuste-limite-contratos',
            'vencimiento_dias_alerta': 'ajuste-dias-alerta',
            'dias_alerta_bloqueante': 'ajuste-dias-bloqueante',
            'dia_cierre_rrhh': 'ajuste-dia-cierre',
            'bioalba_dias_volatilidad': 'ajuste-dias-volatilidad',
            'asistencia_emergencia_gap_horas': 'ajuste-emergencia-gap',
            'asistencia_emergencia_jornada_limite_horas': 'ajuste-emergencia-limite',
            'asistencia_max_extras_ordinarias_dia_habil': 'ajuste-max-extras-dia-habil',
            'asistencia_minimo_horas_extra_minutos': 'ajuste-minimo-extras'
        };

        // Rellenar valores
        ajustes.forEach(a => {
            const inputId = mapIds[a.clave];
            if (inputId) {
                const el = document.getElementById(inputId);
                if (el) {
                    if (a.clave === 'asistencia_max_extras_ordinarias_dia_habil') {
                        // En la DB se guarda en minutos, pero en la UI se muestra en horas
                        el.value = (parseFloat(a.valor) / 60.0).toFixed(1);
                    } else {
                        el.value = a.valor;
                    }
                }
            }
        });

        if (window.FichaCfg && FichaCfg.sistemaOriginales) FichaCfg.sistemaOriginales();
    } catch (e) {
        console.error("Error cargando ajustes del sistema", e);
        showToast("No se pudieron cargar los ajustes.", "error");
    }
};

window.saveAjusteSistema = async function(clave, inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;

    const valor = input.value.trim();
    if (!valor) {
        showToast("Falta el valor.", "warning");
        return;
    }

    let valorEnviar = valor;
    if (clave === 'asistencia_max_extras_ordinarias_dia_habil') {
        const hrs = parseFloat(valor);
        if (isNaN(hrs) || hrs < 0) {
            showToast("Las horas deben ser un número igual o mayor que cero.", "warning");
            return;
        }
        // Convertir horas a minutos para almacenar en la DB
        valorEnviar = String(Math.round(hrs * 60));
    }

    // El backend espera int, así que enviaremos como número o string validable
    try {
        const response = await fetch(`${API_CONFIG}ajustes/${clave}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(valorEnviar) // FastAPI lo recibirá
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Error al guardar el ajuste");
        }
        let respuesta = {};
        try { respuesta = await response.json(); } catch (_) {}
        const aviso = (respuesta && respuesta.recalculo)
            ? ' Se está recalculando el tramo abierto; la grilla se actualiza en unos segundos.'
            : '';
        showToast(`Listo. Ajuste guardado.${aviso}`, "success");
        input.dataset.original = valor;
    } catch (e) {
        console.error("Error guardando ajuste:", e);
        showToast(e.message, "error");
    }
};

// ==========================================
// CATÁLOGO DE ÁREAS Y ALIAS (AUDITORÍA)
// ==========================================
// Áreas, Cargos y Géneros con el diseño B (01-11-2026): lista a la izquierda y ficha a la derecha. Se monta dentro del
// contenedor de siempre (…-catalogo-container) para que las funciones que lo buscan sigan funcionando; el encabezado viejo
// de la pestaña se oculta porque la ficha trae el suyo.
function montarCatalogoB(containerId, o) {
    const container = document.getElementById(containerId);
    if (!container || !window.FichaCfg) return null;
    container.className = '';
    const pane = container.closest('.tab-pane');
    if (pane) Array.prototype.forEach.call(pane.children, function (el) { if (el !== container) el.classList.add('d-none'); });
    window.FichaCfg.montar(container, o);
    return container;
}
async function leerCatalogo(url, containerId, nombre) {
    const container = document.getElementById(containerId);
    if (!container) return null;
    try {
        const r = await fetch(url, { headers: { 'Authorization': 'Bearer ' + localStorage.getItem('access_token') } });
        if (!r.ok) throw new Error('No se pudo leer ' + nombre + '.');
        return await r.json();
    } catch (e) {
        container.innerHTML = '<p class="fcB-vacio">' + window.FichaCfg.esc(e.message) + ' <button type="button" class="fcB-btn" onclick="' + (containerId.indexOf('areas') === 0 ? 'cargarCatalogoAreas' : containerId.indexOf('cargos') === 0 ? 'cargarCatalogoCargos' : 'cargarCatalogoGeneros') + '()">Reintentar</button></p>';
        return null;
    }
}
function erroresBioAlba(lista, borrar) {
    const F = window.FichaCfg;
    if (!lista.length) return '<p class="fcB-nota">BioAlba no ha enviado nombres distintos para esta. Todo calza.</p>';
    return '<div class="fcB-chips">' + lista.map(function (al) {
        return '<span class="fcB-chip">' + F.esc(al.alias) + (borrar ? '<button type="button" title="Desvincular «' + F.esc(al.alias) + '»" aria-label="Desvincular ' + F.esc(al.alias) + '" onclick="' + borrar + '(' + al.id + ', \'' + String(al.alias).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;') + '\')"><i class="bi bi-x-lg" aria-hidden="true"></i></button>' : '') + '</span>';
    }).join('') + '</div>';
}

window.cargarCatalogoAreas = async function() {
    const areas = await leerCatalogo('/api/configuracion/areas/', 'areas-catalogo-container', 'las áreas');
    if (!areas) return;
    const F = window.FichaCfg, canEdit = F.puede('configuracion.editar');
    montarCatalogoB('areas-catalogo-container', {
        clave: 'areas',
        titulo: 'Áreas',
        descripcion: 'Áreas de la empresa. Si el reloj o BioAlba traen otro nombre para un área, aquí se ve y se puede desvincular.',
        acciones: (canEdit ? '<button type="button" class="fcB-btn pri" onclick="abrirModalCrearArea()"><i class="bi bi-plus-lg" aria-hidden="true"></i>Crear área</button>' : '')
            + '<button type="button" class="fcB-btn" onclick="cargarCatalogoAreas()"><i class="bi bi-arrow-clockwise" aria-hidden="true"></i>Actualizar</button>',
        items: areas.slice().sort(function (a, b) { return String(a.nombre).localeCompare(String(b.nombre), 'es'); }),
        id: function (a) { return a.id; },
        etiqueta: function (a) { return a.nombre; },
        sub: function (a) { return a.alias.length ? a.alias.length + (a.alias.length === 1 ? ' nombre distinto' : ' nombres distintos') : ''; },
        vacio: 'No hay áreas registradas.',
        ficha: function (a, panel) {
            panel.innerHTML = F.cabeza(a.nombre, canEdit ? 'Los cambios de esta ficha se guardan al tocarlos.' : 'Solo lectura.')
                + F.campo('Control de flota', '<label class="fcB-sw"><input type="checkbox" ' + (a.aplica_flota ? 'checked ' : '') + (canEdit ? '' : 'disabled ') + 'onchange="window.toggleAreaAplicaFlota(' + a.id + ', this.checked)"><span aria-hidden="true"></span>Sus vehículos aparecen en Portería › Flota</label>')
                + F.campo('Nombres distintos que trae BioAlba', erroresBioAlba(a.alias, canEdit ? 'confirmDeleteAlias' : ''), 'Al desvincular uno, las marcas con ese nombre dejan de asignarse a esta área.')
                + (canEdit ? F.pie('<button type="button" class="fcB-btn borra" onclick="window.confirmDeleteArea(' + a.id + ', \'' + String(a.nombre).replace(/'/g, "\\'") + '\')"><i class="bi bi-trash3" aria-hidden="true"></i>Eliminar área</button>', '') : '');
        }
    });
};

window.toggleAreaAplicaFlota = async function(areaId, checked) {
    try {
        const response = await fetch(`/api/configuracion/areas/${areaId}/aplica-flota`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: JSON.stringify({ aplica_flota: checked ? 1 : 0 })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Error al actualizar la configuración de flota para el área");
        }
        
        if(typeof showToast === 'function') {
            showToast("Listo. Se cambió el uso de flota del área.", "success");
        } else if(typeof window.showNotification === 'function') {
            window.showNotification("Habilitación de flota actualizada para el área.", "success");
        }
    } catch(error) {
        console.error(error);
        Avisos.error("No se cambió el uso de flota del área. " + error.message);
        // Revertir switch
        const el = document.getElementById(`switch-flota-${areaId}`);
        if (el) el.checked = !checked;
    }
};

window.confirmDeleteArea = function(areaId, areaNombre) {
    if(typeof Swal !== 'undefined') {
        Swal.fire({
            title: '¿Eliminar Área?',
            html: `¿Está seguro de que desea eliminar el área <b>"${areaNombre}"</b>?<br><br><span class="text-danger small"><i class="bi bi-exclamation-triangle-fill"></i> Esta acción no se puede deshacer y fallará si el área contiene empleados activos o marcaciones en su historial.</span>`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#6c757d',
            confirmButtonText: 'Sí, eliminar área',
            cancelButtonText: 'Cancelar'
        }).then((result) => {
            if (result.isConfirmed) {
                window.deleteArea(areaId);
            }
        });
    } else {
        if(confirm(`¿Eliminar el área "${areaNombre}"?\n\nEsta acción no se puede deshacer y fallará si el área contiene empleados activos o marcaciones en su historial.`)) {
            window.deleteArea(areaId);
        }
    }
};

window.deleteArea = async function(areaId) {
    try {
        const response = await fetch(`/api/configuracion/areas/${areaId}/`, {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` },
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Error al eliminar el área");
        }
        
        cargarCatalogoAreas();
        
        if(typeof showToast === 'function') {
            showToast("Listo. Área eliminada.", "success");
        } else if(typeof Swal !== 'undefined') {
            Swal.fire('Eliminada!', 'El área ha sido eliminada.', 'success');
        }
    } catch(error) {
        console.error(error);
        if(typeof Swal !== 'undefined') {
            Swal.fire('Error al eliminar', error.message, 'error');
        } else if(typeof showToast === 'function') {
            showToast(error.message, "error");
        } else {
            alert(error.message);
        }
    }
};

window.confirmDeleteAlias = function(aliasId, aliasNombre) {
    if(typeof Swal !== 'undefined') {
        Swal.fire({
            title: '¿Desvincular Alias?',
            html: `Se desvinculará el texto erróneo <b>"${aliasNombre}"</b>.<br><br><i>Nota: Si el reloj control vuelve a enviar este texto, el Guardián detendrá la sincronización nuevamente para pedir revisión.</i>`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#6c757d',
            confirmButtonText: 'Sí, desvincular',
            cancelButtonText: 'Cancelar'
        }).then((result) => {
            if (result.isConfirmed) {
                deleteAlias(aliasId);
            }
        });
    } else {
        if(confirm(`¿Desvincular el texto erróneo "${aliasNombre}"?\n\nNota: Si el reloj control vuelve a enviar este texto, el Guardián detendrá la sincronización nuevamente para pedir revisión.`)) {
            deleteAlias(aliasId);
        }
    }
};

window.deleteAlias = async function(aliasId) {
    try {
        const response = await fetch(`/api/configuracion/areas/alias/${aliasId}`, { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }, 
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error("Error al desvincular el alias");
        
        // Remove optimistic DOM Element just in case, but usually we just reload
        const row = document.getElementById(`alias-row-${aliasId}`);
        if(row) {
            row.style.opacity = '0.5';
            setTimeout(() => {
                cargarCatalogoAreas(); // Reload the catalog to update badges
            }, 300);
        } else {
            cargarCatalogoAreas();
        }
        
        if(typeof showToast === 'function') {
            showToast("Listo. Se quitó el texto equivocado del reloj.", "success");
        } else if(typeof Swal !== 'undefined') {
            Swal.fire('Desvinculado!', 'El alias ha sido eliminado.', 'success');
        }
    } catch(error) {
        console.error(error);
        if(typeof showToast === 'function') {
            showToast(error.message, "error");
        } else {
            alert(error.message);
        }
    }
};


// ==========================================
// CATÁLOGO DE CARGOS Y ALIAS (AUDITORÍA)
// ==========================================
window.cargarCatalogoCargos = async function() {
    const cargos = await leerCatalogo('/api/configuracion/cargos/', 'cargos-catalogo-container', 'los cargos');
    if (!cargos) return;
    const F = window.FichaCfg, canEdit = F.puede('configuracion.editar');
    montarCatalogoB('cargos-catalogo-container', {
        clave: 'cargos',
        titulo: 'Cargos',
        descripcion: 'Cargos de la empresa. Un cargo «excluido de asistencia» es del Artículo 22: no se le calculan atrasos ni horas extra.',
        acciones: (canEdit ? '<button type="button" class="fcB-btn pri" onclick="abrirModalCrearCargo()"><i class="bi bi-plus-lg" aria-hidden="true"></i>Crear cargo</button>' : '')
            + '<button type="button" class="fcB-btn" onclick="cargarCatalogoCargos()"><i class="bi bi-arrow-clockwise" aria-hidden="true"></i>Actualizar</button>',
        items: cargos.slice().sort(function (a, b) { return String(a.nombre).localeCompare(String(b.nombre), 'es'); }),
        id: function (c) { return c.id; },
        etiqueta: function (c) { return c.nombre; },
        sub: function (c) { return c.excluido_asistencia ? 'Artículo 22' : (c.alias.length ? c.alias.length + (c.alias.length === 1 ? ' nombre distinto' : ' nombres distintos') : ''); },
        vacio: 'No hay cargos registrados.',
        ficha: function (c, panel) {
            panel.innerHTML = F.cabeza(c.nombre, canEdit ? 'Los cambios de esta ficha se guardan al tocarlos.' : 'Solo lectura.')
                + F.campo('Excluido de asistencia', '<label class="fcB-sw"><input type="checkbox" id="cargo-excluir-' + c.id + '" ' + (c.excluido_asistencia ? 'checked ' : '') + (canEdit ? '' : 'disabled ') + 'onchange="toggleCargoExclusion(' + c.id + ', this.checked)"><span aria-hidden="true"></span>Artículo 22 (sin atrasos ni horas extra)</label>')
                + F.campo('Nombres distintos que trae BioAlba', erroresBioAlba(c.alias, canEdit ? 'confirmDeleteCargoAlias' : ''), 'Al desvincular uno, las personas con ese cargo en BioAlba dejan de asignarse a este.');
        }
    });
};

window.toggleCargoExclusion = async function(cargoId, value) {
    try {
        const response = await fetch(`/api/configuracion/cargos/${cargoId}/excluir/?excluir=${value}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                'Content-Type': 'application/json'
            }
        });
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || 'Error al actualizar exclusión del cargo');
        }
        if (typeof showToast === 'function') {
            showToast("Listo. Se guardó el cargo y sus personas.", "success");
        } else if (typeof Swal !== 'undefined') {
            Swal.fire('Guardado', 'Configuración de cargo actualizada.', 'success');
        }
        cargarCatalogoCargos();
    } catch (error) {
        console.error(error);
        if (typeof showToast === 'function') {
            showToast(error.message, "error");
        } else if (typeof Swal !== 'undefined') {
            Swal.fire('Error', error.message, 'error');
        } else {
            alert(error.message);
        }
        cargarCatalogoCargos();
    }
};

window.confirmDeleteCargoAlias = function(aliasId, aliasNombre) {
    if(typeof Swal !== 'undefined') {
        Swal.fire({
            title: '¿Desvincular Alias?',
            html: `Se desvinculará el texto erróneo <b>"${aliasNombre}"</b>.<br><br><i>Nota: Si el reloj control vuelve a enviar este texto, el Guardián detendrá la sincronización nuevamente para pedir revisión.</i>`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#6c757d',
            confirmButtonText: 'Sí, desvincular',
            cancelButtonText: 'Cancelar'
        }).then((result) => {
            if (result.isConfirmed) {
                deleteCargoAlias(aliasId);
            }
        });
    } else {
        if(confirm(`¿Desvincular el texto erróneo "${aliasNombre}"?\n\nNota: Si el reloj control vuelve a enviar este texto, el Guardián detendrá la sincronización nuevamente para pedir revisión.`)) {
            deleteCargoAlias(aliasId);
        }
    }
};

window.deleteCargoAlias = async function(aliasId) {
    try {
        const response = await fetch(`/api/configuracion/cargos/alias/${aliasId}`, { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }, 
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error("Error al desvincular el alias");
        
        const row = document.getElementById(`cargo-alias-row-${aliasId}`);
        if(row) {
            row.style.opacity = '0.5';
            setTimeout(() => {
                cargarCatalogoCargos();
            }, 300);
        } else {
            cargarCatalogoCargos();
        }
        
        if(typeof showToast === 'function') {
            showToast("Listo. Se quitó el texto equivocado del cargo.", "success");
        } else if(typeof Swal !== 'undefined') {
            Swal.fire('Desvinculado!', 'El alias ha sido eliminado.', 'success');
        }
    } catch(error) {
        console.error(error);
        if(typeof showToast === 'function') {
            showToast(error.message, "error");
        } else {
            alert(error.message);
        }
    }
};

// ==========================================
// CATÁLOGO DE GÉNEROS
// ==========================================
window.cargarCatalogoGeneros = async function() {
    const generos = await leerCatalogo('/api/configuracion/generos/', 'generos-catalogo-container', 'los géneros');
    if (!generos) return;
    montarCatalogoB('generos-catalogo-container', {
        clave: 'generos',
        titulo: 'Géneros',
        descripcion: 'Géneros que se pueden elegir en la ficha de una persona. Esta lista no se cambia desde aquí.',
        items: generos,
        id: function (g) { return g.id; },
        etiqueta: function (g) { return g.nombre; },
        soloLista: true,
        vacio: 'No hay géneros registrados.'
    });
};

// ==========================================
// TRAMOS DE CIERRE (PERIODOS RRHH)
// ==========================================
window.loadPeriodosRRHH = async function() {
    const container = document.getElementById('periodos-config-container');
    if (!container) return;

    container.innerHTML = `
        <div class="text-center py-5">
            <div class="spinner-border text-primary" role="status"></div>
            <div class="text-muted mt-2">Cargando tramos de cierre...</div>
        </div>
    `;

    try {
        const response = await fetch('/api/configuracion/periodos/', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
        });
        if (!response.ok) throw new Error("Error obteniendo los tramos de cierre");
        const periodos = await response.json();
        periodosRRHHList = periodos; // Cache list
        renderPeriodosRRHH(periodos);
    } catch (error) {
        console.error(error);
        container.innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-octagon me-2"></i> ${error.message}</div>`;
    }
};

window.renderPeriodosRRHH = function(periodos) {
    const container = document.getElementById('periodos-config-container');
    if (!container) return;

    const canEdit = typeof AuthService !== 'undefined' ? AuthService.hasPermission('configuracion.editar') : true;
    const esc = (t) => String(t == null ? '' : t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const corta = (f) => { const p = String(f || '').split('-'); return p.length === 3 ? p[2] + '-' + p[1] : f; };

    // Columnas: las áreas que aparecen en algún tramo (cerradas o por cerrar); salen de los datos, no del código
    const areas = [...new Set(periodos.flatMap((p) => (p.areas_cerradas || []).concat(p.areas_pendientes || [])))].sort();

    let html = '<div class="tA-head"><div><h5>Tramos de cierre</h5>'
        + '<p>El tramo vigente es el que usa Asistencia para sus fechas; cada área lo cierra cuando termina su revisión.</p></div>'
        + (canEdit ? '<button type="button" class="btn btn-primary" onclick="openModalPeriodo()"><i class="bi bi-plus-lg me-1" aria-hidden="true"></i>Crear tramo</button>' : '')
        + '</div>';

    if (periodos.length === 0) {
        container.innerHTML = html + '<div class="tA-vacio"><i class="bi bi-calendar3" aria-hidden="true"></i>'
            + '<p>Todavía no hay tramos de cierre.' + (canEdit ? ' Cree el primero con «Crear tramo».' : '') + '</p></div>';
        return;
    }

    html += '<div class="tA-wrap"><table class="tA"><thead><tr><th scope="col">Tramo</th>'
        + areas.map((a) => '<th scope="col">' + esc(a) + '</th>').join('')
        + '<th scope="col"><span class="visually-hidden">Acciones</span></th></tr></thead><tbody>';

    periodos.forEach((p) => {
        const dias = calculateDaysBetween(p.fecha_inicio, p.fecha_fin);
        const cierres = p.cierres || {};
        const cerradas = new Set(p.areas_cerradas || []);
        const pendientes = new Set(p.areas_pendientes || []);
        html += '<tr class="' + (p.activo ? 'vig' : '') + '"><td><div class="mes">' + esc(p.mes_cierre)
            + (p.activo ? ' <span class="tA-vig"><i class="bi bi-star-fill" aria-hidden="true"></i>Vigente</span>' : '') + '</div>'
            + '<div class="rango">' + formatDateDMY(p.fecha_inicio) + ' al ' + formatDateDMY(p.fecha_fin) + ' · ' + dias + ' días</div></td>';
        areas.forEach((a) => {
            if (cerradas.has(a)) {
                const c = cierres[a] || {};
                const acta = "descargarActaCierre('" + p.fecha_inicio + "','" + p.fecha_fin + "','" + esc(a) + "')";
                html += '<td><div class="c-ok" title="' + esc(a) + ': cerrada' + (c.fecha ? ' el ' + formatDateDMY(c.fecha) : '') + (c.por ? ' por ' + esc(c.por) : '') + '">'
                    + '<i class="bi bi-check-circle-fill" aria-hidden="true"></i>'
                    + (c.fecha ? '<b>' + corta(c.fecha) + '</b>' : '<b>Cerrada</b>')
                    + (c.por ? '<small>' + esc(c.por) + '</small>' : '')
                    + '<button type="button" class="tA-acta" onclick="' + acta + '" aria-label="Descargar el acta de cierre de ' + esc(a) + ' (PDF)"><i class="bi bi-file-earmark-pdf" aria-hidden="true"></i>Acta</button>'
                    + '</div></td>';
            } else if (pendientes.has(a)) {
                html += '<td><span class="c-wait"><i class="bi bi-clock" aria-hidden="true"></i>Falta</span></td>';
            } else {
                html += '<td><span class="c-nc" title="Sin cierre en este tramo">—</span></td>';
            }
        });
        let acc = '';
        if (canEdit) {
            acc = (p.activo
                ? '<button type="button" class="tA-ico on" disabled title="Es el tramo vigente" aria-label="Es el tramo vigente"><i class="bi bi-star-fill"></i></button>'
                : '<button type="button" class="tA-ico" onclick="activarPeriodoRRHH(' + p.id + ')" title="Marcar como vigente" aria-label="Marcar como vigente"><i class="bi bi-star"></i></button>')
                + '<button type="button" class="tA-ico" onclick="editPeriodoRRHH(' + p.id + ')" title="Editar" aria-label="Editar"><i class="bi bi-pencil"></i></button>'
                + '<button type="button" class="tA-ico del" onclick="deletePeriodoRRHH(' + p.id + ')" title="Eliminar" aria-label="Eliminar"><i class="bi bi-trash3"></i></button>';
        }
        html += '<td class="acc">' + acc + '</td></tr>';
    });

    html += '</tbody></table></div>'
        + '<div class="tA-leg"><span class="ok"><i class="bi bi-check-circle-fill" aria-hidden="true"></i>Cerrada: fecha y quién cerró; «Acta» descarga el PDF</span>'
        + '<span class="wait"><i class="bi bi-clock" aria-hidden="true"></i>Falta cerrar</span><span>— Sin cierre en ese tramo</span></div>';
    container.innerHTML = html;
};

function calculateDaysBetween(start, end) {
    if (!start || !end) return 0;
    const s = new Date(start + 'T00:00:00');
    const e = new Date(end + 'T00:00:00');
    const diff = e - s;
    return Math.round(diff / (1000 * 60 * 60 * 24)) + 1;
}

function formatDateDMY(dateStr) {
    return window.formatFechaDDMMYYYY(dateStr);
}

window.openModalPeriodo = function(periodo = null) {
    const modal = document.getElementById('modal-periodo');
    const title = document.getElementById('modal-periodo-title');
    const form = document.getElementById('form-periodo');

    form.reset();

    // Populate Year dropdown dynamically
    const yearSelect = document.getElementById('periodo-anio-cierre');
    if (yearSelect) {
        yearSelect.innerHTML = '';
        const currentYear = new Date().getFullYear();
        for (let y = currentYear - 2; y <= currentYear + 3; y++) {
            const opt = document.createElement('option');
            opt.value = y;
            opt.textContent = y;
            yearSelect.appendChild(opt);
        }
    }

    if (periodo) {
        title.innerText = 'Editar Tramo de Cierre';
        document.getElementById('periodo-id').value = periodo.id;
        
        // Parse mes_cierre: e.g. "Mayo 2026" or "Mayo"
        const parts = (periodo.mes_cierre || '').split(' ');
        const mes = parts[0] || '';
        const anio = parts[1] || (periodo.fecha_fin ? periodo.fecha_fin.split('-')[0] : new Date().getFullYear());
        
        document.getElementById('periodo-mes-cierre').value = mes;
        if (yearSelect) {
            yearSelect.value = anio;
        }
        
        document.getElementById('periodo-fecha-inicio').value = periodo.fecha_inicio;
        document.getElementById('periodo-fecha-fin').value = periodo.fecha_fin;
        document.getElementById('periodo-activo').value = periodo.activo;
        document.getElementById('periodo-estado').value = periodo.estado;
    } else {
        title.innerText = 'Crear Nuevo Tramo de Cierre';
        document.getElementById('periodo-id').value = '';
        if (yearSelect) {
            yearSelect.value = new Date().getFullYear();
        }
        document.getElementById('periodo-activo').value = '0';
        document.getElementById('periodo-estado').value = 'abierto';

        // Autocompletar fechas usando dia_cierre_rrhh configurable desde la BD
        (async () => {
            try {
                const ajResp = await fetch('/api/configuracion/ajustes/dia_cierre_rrhh', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
                });
                const ajData = ajResp.ok ? await ajResp.json() : null;
                const diaCierre = ajData ? parseInt(ajData.valor, 10) : 25;
                const diaInicio = diaCierre + 1;

                const hoy = new Date();
                let inicioDate, finDate;

                if (hoy.getDate() > diaCierre) {
                    // Estamos después del cierre: período del mes actual al siguiente
                    inicioDate = new Date(hoy.getFullYear(), hoy.getMonth(), diaInicio);
                    finDate    = new Date(hoy.getFullYear(), hoy.getMonth() + 1, diaCierre);
                } else {
                    // Estamos antes del cierre: período del mes anterior al actual
                    inicioDate = new Date(hoy.getFullYear(), hoy.getMonth() - 1, diaInicio);
                    finDate    = new Date(hoy.getFullYear(), hoy.getMonth(), diaCierre);
                }

                const fmt = d => d.toISOString().split('T')[0];
                document.getElementById('periodo-fecha-inicio').value = fmt(inicioDate);
                document.getElementById('periodo-fecha-fin').value    = fmt(finDate);

                // Autocompletar mes y año del cierre
                const meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
                const mesSelect = document.getElementById('periodo-mes-cierre');
                if (mesSelect) mesSelect.value = meses[finDate.getMonth()];
                if (yearSelect) yearSelect.value = finDate.getFullYear();

                calculatePeriodDays();
            } catch(e) {
                console.warn('No se pudo autocompletar fechas de periodo:', e);
            }
        })();
    }

    // Calcular días
    calculatePeriodDays();

    modal.style.display = 'flex';
};

window.editPeriodoRRHH = function(id) {
    const p = periodosRRHHList.find(item => item.id === id);
    if (p) openModalPeriodo(p);
};

window.closeModalPeriodo = function() {
    document.getElementById('modal-periodo').style.display = 'none';
};

window.calculatePeriodDays = function() {
    const init = document.getElementById('periodo-fecha-inicio').value;
    const fin = document.getElementById('periodo-fecha-fin').value;
    const countInput = document.getElementById('periodo-dias');
    
    if (init && fin) {
        const days = calculateDaysBetween(init, fin);
        countInput.value = days;
        if (days > 35) {
            countInput.classList.add('is-invalid');
            countInput.classList.add('text-danger');
        } else {
            countInput.classList.remove('is-invalid');
            countInput.classList.remove('text-danger');
        }
    } else {
        countInput.value = '0';
    }
};

window.savePeriodoRRHH = async function() {
    const id = document.getElementById('periodo-id').value;
    const mesVal = document.getElementById('periodo-mes-cierre').value;
    const anioVal = document.getElementById('periodo-anio-cierre').value;
    const mes_cierre = `${mesVal} ${anioVal}`.trim();
    const fecha_inicio = document.getElementById('periodo-fecha-inicio').value;
    const fecha_fin = document.getElementById('periodo-fecha-fin').value;
    const activo = parseInt(document.getElementById('periodo-activo').value, 10);
    const estado = document.getElementById('periodo-estado').value;

    const days = calculateDaysBetween(fecha_inicio, fecha_fin);
    if (days <= 0) {
        if (typeof showToast === 'function') {
            showToast("La fecha de inicio no puede ser después de la fecha de fin.", "warning");
        } else {
            Avisos.falta("La fecha de inicio no puede ser después de la fecha de fin.");
        }
        return;
    }

    if (days > 35) {
        if (typeof showToast === 'function') {
            showToast("El tramo no puede tener más de 35 días.", "warning");
        } else {
            Avisos.falta("El tramo no puede tener más de 35 días.");
        }
        return;
    }

    const payload = {
        mes_cierre,
        fecha_inicio,
        fecha_fin,
        activo,
        estado
    };

    const url = id ? `/api/configuracion/periodos/${id}/` : `/api/configuracion/periodos/`;
    const method = id ? 'PUT' : 'POST';

    try {
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Error al guardar el periodo");
        }

        closeModalPeriodo();
        if (typeof showToast === 'function') {
            showToast("Listo. Tramo de cierre guardado.", "success");
        } else if (typeof Swal !== 'undefined') {
            Swal.fire("Éxito", "Tramo de cierre guardado exitosamente.", "success");
        }
        loadPeriodosRRHH();
    } catch (error) {
        console.error(error);
        if (typeof showToast === 'function') {
            showToast(error.message, "error");
        } else {
            alert(error.message);
        }
    }
};

window.deletePeriodoRRHH = async function(id) {
    const action = async () => {
        try {
            const response = await fetch(`/api/configuracion/periodos/${id}/`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || "Error al eliminar el periodo");
            }

            if (typeof showToast === 'function') {
                showToast("Listo. Tramo de cierre eliminado.", "success");
            } else if (typeof Swal !== 'undefined') {
                Swal.fire("Eliminado", "Tramo de cierre eliminado exitosamente.", "success");
            }
            loadPeriodosRRHH();
        } catch (error) {
            console.error(error);
            if (typeof showToast === 'function') {
                showToast(error.message, "error");
            } else {
                alert(error.message);
            }
        }
    };

    if (typeof Swal !== 'undefined') {
        Swal.fire({
            title: '¿Eliminar tramo de cierre?',
            text: "Esta acción no se puede deshacer.",
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#3085d6',
            confirmButtonText: 'Sí, eliminar',
            cancelButtonText: 'Cancelar'
        }).then((result) => {
            if (result.isConfirmed) {
                action();
            }
        });
    } else {
        if (confirm("¿Está seguro que desea eliminar este tramo de cierre?")) {
            action();
        }
    }
};

window.activarPeriodoRRHH = async function(id) {
    try {
        const response = await fetch(`/api/configuracion/periodos/${id}/activar/`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Error al activar el periodo");
        }

        if (typeof showToast === 'function') {
            showToast("Listo. Tramo de cierre activado.", "success");
        } else if (typeof Swal !== 'undefined') {
            Swal.fire("Activado", "El tramo de cierre ahora está vigente.", "success");
        }
        loadPeriodosRRHH();
    } catch (error) {
        console.error(error);
        if (typeof showToast === 'function') {
            showToast(error.message, "error");
        } else {
            alert(error.message);
        }
    }
};

// Crear un área o un cargo: ventana con un solo campo (diseño HD). Mismas peticiones y avisos que antes.
function crearEnCatalogo(o) {
    return window.ventanaForm({
        icono: o.icono, tono: 'g', titulo: o.titulo, sub: o.sub,
        cuerpo: '<div class="vn-fld"><label for="vn-cat-nombre">' + o.etiqueta + '</label>'
            + '<input type="text" id="vn-cat-nombre" class="form-control" autocomplete="off" placeholder="' + o.ejemplo + '"></div>',
        confirmButtonText: 'Crear',
        preConfirm: async () => {
            const nombre = document.getElementById('vn-cat-nombre').value.trim();
            if (!nombre) { Swal.showValidationMessage(o.falta); return false; }
            try {
                Swal.showLoading();
                const response = await fetch(o.url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                    },
                    body: JSON.stringify({ nombre: nombre })
                });
                const res = await response.json();
                if (!response.ok) throw new Error(res.detail || o.error);
                return res;
            } catch (error) {
                Swal.showValidationMessage(error.message);
                return false;
            }
        }
    }).then((result) => {
        if (result.isConfirmed) {
            showToast(o.listo, "success");
            o.recargar();
        }
    });
}

window.abrirModalCrearArea = async function() {
    return crearEnCatalogo({
        icono: 'diagram-3', titulo: 'Crear área', sub: 'Se agrega a la lista de áreas',
        etiqueta: 'Nombre del área', ejemplo: 'Ej.: CONTABILIDAD, VENTAS…', falta: 'Falta el nombre del área.',
        url: '/api/configuracion/areas/', error: 'No se pudo crear el área.', listo: 'Listo. Área creada.',
        recargar: () => cargarCatalogoAreas()
    });
};

window.abrirModalCrearCargo = async function() {
    return crearEnCatalogo({
        icono: 'person-badge', titulo: 'Crear cargo', sub: 'Se agrega a la lista de cargos',
        etiqueta: 'Nombre del cargo', ejemplo: 'Ej.: ADMINISTRATIVO, OPERARIO…', falta: 'Falta el nombre del cargo.',
        url: '/api/configuracion/cargos/', error: 'No se pudo crear el cargo.', listo: 'Listo. Cargo creado.',
        recargar: () => cargarCatalogoCargos()
    });
};

// ── Configuración: buscador del menú lateral ─────────────────────────────────────────────
// Filtra los ajustes por nombre (y por palabras clave comunes). Enter abre el primero; Esc limpia.
(function initConfigNavSearch() {
    const CLAVES = {
        'horarios-tab': 'turnos horarios jornada', 'periodos-tab': 'tramos cierre periodos liquidacion', 'justificaciones-tab': 'justificaciones permisos licencias',
        'calendario-tab': 'calendario feriados festivos', 'estados-tab': 'estados asistencia colores', 'areas-tab': 'areas departamentos bioalba',
        'cargos-tab': 'cargos puestos', 'generos-tab': 'generos', 'pagadores-tab': 'pagadores empresas', 'bonos-tab': 'bonos beneficios',
        'correo-tab': 'correo email smtp alertas notificaciones', 'robot-bioalba-tab': 'robot bioalba sincronizacion relojes',
        'catalogo-hallazgos-config-tab': 'porteria hallazgos anomalias rondas', 'porteria-ubicaciones-config-tab': 'porteria ubicacion puntos control qr',
        'flota-config-tab': 'flota camiones vehiculos', 'productos-propios-tab': 'productos propios entregas', 'seguridad-config-tab': 'seguridad usuarios roles permisos auditoria',
        'sistema-config-tab': 'sistema base de datos diagnostico'
    };
    const norm = t => String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    function init() {
        const input = document.getElementById('cfg-search');
        const nav = document.getElementById('configTabs');
        if (!input || !nav || input.dataset.ready) return;
        input.dataset.ready = '1';
        const items = () => Array.from(nav.querySelectorAll('.cfg-item'));
        const visibles = () => items().filter(b => !b.classList.contains('d-none') && !b.hidden);
        function filtrar() {
            const q = norm(input.value.trim());
            items().forEach(b => { b.hidden = !!q && !norm(b.textContent + ' ' + (CLAVES[b.id] || '')).includes(q); });
            const nores = document.getElementById('cfg-nores');
            if (nores) nores.hidden = !q || visibles().length > 0;
        }
        input.addEventListener('input', filtrar);
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') { const b = visibles()[0]; if (b) { e.preventDefault(); b.click(); } }
            else if (e.key === 'Escape' && input.value) { e.stopPropagation(); input.value = ''; filtrar(); }
        });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
