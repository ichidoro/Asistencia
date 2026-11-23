// configuracion_ui.js - Interfaz Completa de Configuración (Bonos y Justificaciones)

const API_CONFIG = '/api/configuracion/';

// Estado local
let bonosList = [];
let tiposJustificacionList = [];
let globalCargosList = []; // [NEW] Cache cargos for dropdowns
let pagadoresList = []; // [NEW] Cache pagadores
let periodosRRHHList = []; // [NEW] Cache periodos rrhh

// ── Cargos de una regla de bono (etapa B3b del plan de bonos, 22-11-2026) ──
// Se eligen con casillas de la lista de cargos y la regla guarda su identificador: un cambio de nombre no la rompe.
let catalogoCargosBono = [];   // [{id, nombre}] de /api/configuracion/cargos/

async function _cargarCatalogoCargosBono() {
    try {
        const r = await fetch('/api/configuracion/cargos/', { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` } });
        if (r.ok) catalogoCargosBono = (await r.json()).map(function (c) { return { id: c.id, nombre: c.nombre }; })
            .sort(function (a, b) { return String(a.nombre).localeCompare(String(b.nombre), 'es'); });
    } catch (e) { console.error(e); }
}

function _resumenCargos(det) {
    const n = det.querySelectorAll('input[type=checkbox]:checked').length;
    det.querySelector('summary span').textContent = n ? (n === 1 ? '1 cargo' : n + ' cargos') : det.dataset.vacio;
}

// Lista desplegable con casillas: clase = 'rule-cargos-req' o 'rule-cargos-excl'; ids = los elegidos
function _htmlPickerCargos(clase, ids, textoVacio) {
    const esc = window.FichaCfg ? window.FichaCfg.esc : function (x) { return String(x == null ? '' : x); };
    const elegidos = new Set((ids || []).map(Number));
    const n = elegidos.size;
    return '<details class="' + clase + ' border rounded bg-white" data-vacio="' + esc(textoVacio) + '">'
        + '<summary class="small px-2 py-1"><span>' + esc(n ? (n === 1 ? '1 cargo' : n + ' cargos') : textoVacio) + '</span></summary>'
        + '<div class="p-2 border-top" style="max-height: 220px; overflow-y: auto;">'
        + '<input type="search" class="form-control form-control-sm mb-2" placeholder="Buscar cargo..." autocomplete="off" '
        + 'oninput="const q=this.value.toLowerCase();this.parentElement.querySelectorAll(\'.form-check\').forEach(function(x){x.style.display=x.textContent.toLowerCase().indexOf(q)>=0?\'\':\'none\';})">'
        + (catalogoCargosBono.length ? catalogoCargosBono.map(function (c) {
            return '<label class="form-check small d-block mb-1"><input class="form-check-input" type="checkbox" value="' + c.id + '"'
                + (elegidos.has(c.id) ? ' checked' : '') + ' onchange="_resumenCargos(this.closest(\'details\'))"> ' + esc(c.nombre) + '</label>';
        }).join('') : '<span class="text-muted small">No hay cargos en la lista.</span>')
        + '</div></details>';
}

function _leerPickerCargos(det) {
    const ids = Array.from(det.querySelectorAll('input[type=checkbox]:checked')).map(function (x) { return parseInt(x.value, 10); });
    return ids.length ? ids : null;
}

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
    { value: 'color-violeta',  label: 'Violeta intenso', preview: '#7c3aed' },
    { value: 'color-rojo-intenso', label: 'Rojo intenso', preview: '#b0352c' },
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
function _escAttr(v) { return window.Ayuda.esc(v); }
function _estadoSiglaDefecto(codigo) { return codigo === 'JORNADA_ESPECIAL' ? 'ESP' : String(codigo).substring(0, 3); }
// Vista previa idéntica a la grilla HD: la sigla en una pastilla de su color, dentro de una celda de día real (css/configuracion.css)
function _estadoPreviewHtml(color, icono, sigla) {
    // La vista previa usa la clase de la grilla para verse igual, pero no su ancho mínimo de tabla completa (en el teléfono
    // la tabla de una celda quedaba de 1.200 px y se salía de la pantalla)
    return `<table class="matrix-table-premium mb-0 mx-auto" style="width:84px !important;min-width:0 !important;border:0;background:transparent" aria-hidden="true"><tbody><tr>
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
        inp.classList.toggle('is-invalid', dupSig.length > 0 || !/^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ.+\-]{1,7}$/.test(inp.value.trim() || 'X'));
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
                + F.campo('Etiqueta', '<input type="text" class="fcB-inp" style="max-width:120px;text-transform:uppercase" id="estado-short-' + _escAttr(c) + '" maxlength="7" value="' + _escAttr(e.short_label || _estadoSiglaDefecto(c)) + '" oninput="previewEstadoBadge(\'' + _escAttr(c) + '\')">', 'Hasta 7 letras o números. No puede repetirse entre estados activos.', 'estado-short-' + c)
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
    if (shortLabel && !/^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ.+\-]{1,7}$/.test(shortLabel)) { showToast('La etiqueta debe tener de 1 a 7 letras o números (también punto, + o guion).', 'warning'); return; }
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
// EFECTO DE LAS JUSTIFICACIONES EN LOS BONOS (etapa B3a del plan de bonos, 22-11-2026)
// Qué pasa con cada bono en un día con una justificación, y con una inasistencia sin justificar. Se configura aquí;
// el cálculo solo lee lo configurado.
// ==========================================
const EFECTOS_BONO = [['asistido', 'Cuenta como asistido'], ['proporcion', 'Descuenta en proporción'], ['pierde', 'Hace perder el bono']];
const EFECTOS_INASISTENCIA = [['pierde', 'Hace perder el bono'], ['proporcion', 'Descuenta en proporción']];
// Un beneficio en especie (4 Productos, etapa B3d) se recibe o no: sin «Descuenta en proporción»
const sinProporcion = function (ops) { return ops.filter(function (o) { return o[0] !== 'proporcion'; }); };
const opsEfecto = function (b) { return b && b.tipo === 'beneficio' ? sinProporcion(EFECTOS_BONO) : EFECTOS_BONO; };
const nombreEfecto = function (v) { const o = EFECTOS_BONO.find(function (x) { return x[0] === v; }); return o ? o[1] : 'Sin configurar'; };

async function _asegurarBonos() {
    if (!bonosList || !bonosList.length) {
        try { const r = await fetch(`${API_CONFIG}bonos/`); if (r.ok) bonosList = await r.json(); } catch (e) { console.error(e); }
    }
    return (bonosList || []).slice().sort(function (a, b) { return String(a.nombre).localeCompare(String(b.nombre), 'es'); });
}

async function _asegurarTiposJ() {
    if (!tiposJustificacionList || !tiposJustificacionList.length) {
        try { const r = await fetch(`${API_CONFIG}justificaciones/tipos/?all=true`); if (r.ok) tiposJustificacionList = await r.json(); } catch (e) { console.error(e); }
    }
    return (tiposJustificacionList || []).slice().sort(function (a, b) { return String(a.nombre).localeCompare(String(b.nombre), 'es'); });
}

function _htmlSelectEfecto(id, ops, valor, attrs) {
    const esc = window.FichaCfg ? window.FichaCfg.esc : function (x) { return String(x == null ? '' : x); };
    return '<select class="form-select form-select-sm" id="' + esc(id) + '" ' + (attrs || '') + '><option value="">Elegir…</option>'
        + ops.map(function (o) { return '<option value="' + o[0] + '"' + (o[0] === valor ? ' selected' : '') + '>' + esc(o[1]) + '</option>'; }).join('')
        + '</select>';
}

// Filas «nombre · efecto» con un <select> por cada elemento (bonos en la justificación, justificaciones en el bono)
function _htmlFilasEfecto(prefijo, items, valorDe, ops) {
    const esc = window.FichaCfg ? window.FichaCfg.esc : function (x) { return String(x == null ? '' : x); };
    if (!items.length) return '<span class="text-muted small">No hay nada que configurar todavía.</span>';
    return items.map(function (it) {
        const id = prefijo + it.id;
        return '<div class="d-flex align-items-center gap-2 mb-1"><label class="small flex-grow-1 mb-0" for="' + esc(id) + '">' + esc(it.nombre)
            + (it.activo === false ? ' <span class="text-muted">(no se calcula)</span>' : '') + '</label>'
            + '<div style="min-width: 210px">' + _htmlSelectEfecto(id, ops ? ops(it) : EFECTOS_BONO, valorDe(it) || '', 'data-ef-id="' + it.id + '" data-ef-nombre="' + esc(it.nombre) + '"') + '</div></div>';
    }).join('');
}

// Lee los <select> de efecto dentro de raiz. Devuelve {valores: {id: efecto}, falta: nombre del primero sin elegir}
function _leerEfectos(raiz) {
    const valores = {};
    let falta = null;
    raiz.querySelectorAll('select[data-ef-id]').forEach(function (s) {
        if (!s.value && !falta) falta = s.dataset.efNombre;
        if (s.value) valores[s.dataset.efId] = s.value;
    });
    return { valores: valores, falta: falta };
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
        sub: function (b) { if (b.tipo === 'beneficio') return 'Beneficio · 4 Productos'; const n = (b.reglas || []).length; return (b.periodicidad === 'semanal' ? 'Semanal · ' : '') + (n ? n + (n === 1 ? ' regla' : ' reglas') : 'Sin reglas'); },
        apagado: function (b) { return !b.activo; },
        vacio: 'No hay bonos. Cree el primero con «Nuevo bono».',
        ficha: function (b, panel) {
            const reglas = (b.reglas || []).map(function (r) {
                const cond = [r.tipo_contrato || 'Todo contrato', r.cargo_requerido ? 'lo reciben: ' + r.cargo_requerido : 'todos los cargos',
                              r.cargos_excluidos ? 'no lo reciben: ' + r.cargos_excluidos : ''].filter(Boolean).join(' · ');
                return '<div class="fcB-campo"><div class="fcB-et"><span class="num">' + F.esc(b.tipo === 'beneficio' ? 'En especie' : pesos(r.monto) + (b.periodicidad === 'semanal' ? ' por semana' : '')) + '</span></div><div class="fcB-ctl"><span>' + F.esc(cond) + '</span></div></div>';
            }).join('');
            // Efecto de las justificaciones y de la inasistencia sin justificar (etapa B3a)
            const tipos = (tiposJustificacionList || []).slice().sort(function (x, y) { return String(x.nombre).localeCompare(String(y.nombre), 'es'); });
            const porEfecto = {};
            tipos.forEach(function (t) { const e = (b.efectos || {})[t.id]; (porEfecto[e || ''] = porEfecto[e || ''] || []).push(t.nombre); });
            const efectosHtml = EFECTOS_BONO.concat([['', 'Sin configurar']]).filter(function (o) { return porEfecto[o[0]]; }).map(function (o) {
                return F.campo(o[1], '<span>' + F.esc(porEfecto[o[0]].join(', ')) + '</span>');
            }).join('');
            panel.innerHTML = F.cabeza(b.nombre, b.descripcion || '')
                + (b.usa_productos_4 ? '<p class="fcB-nota">Lo usa 4 Productos para decidir quién recibe los productos. No sale en el informe de cierre ni en la grilla, y no se puede eliminar.</p>' : '')
                + F.campo('En uso', '<span class="fcB-sw" aria-disabled="true"><input type="checkbox" disabled' + (b.activo ? ' checked' : '') + '><span aria-hidden="true"></span>' + (b.activo ? 'Se calcula' : 'No se calcula') + '</span>')
                + F.campo('Evaluación', '<span>' + F.esc(b.periodicidad === 'semanal' ? 'Semanal, de lunes a domingo' : 'Por período') + '</span>')
                + F.campo('Áreas', '<span>' + F.esc(b.filtra_areas ? 'Solo ' + ((b.area_nombres || []).join(', ') || 'las elegidas') : 'Todas las áreas') + '</span>')
                + F.campo('Horarios', '<span>' + F.esc((b.turnos_ids || []).length ? 'Solo ' + (b.turnos_ids.length === 1 ? '1 horario' : b.turnos_ids.length + ' horarios') : 'Todos los horarios') + '</span>')
                + F.campo('Inasistencia sin justificar', '<span>' + F.esc(b.efecto_inasistencia ? nombreEfecto(b.efecto_inasistencia) : 'Sin configurar') + '</span>')
                + (b.tipo === 'beneficio' ? F.campo('Antigüedad mínima', '<span>' + F.esc(b.antiguedad_meses == null ? 'Sin configurar'
                    : (b.antiguedad_meses === 0 ? 'Desde el mes en que empieza su turno' : b.antiguedad_meses + (b.antiguedad_meses === 1 ? ' mes' : ' meses') + ' después del mes en que empieza su turno')) + '</span>') : '')
                + F.seccion('Reglas de aplicación')
                + (reglas || '<p class="fcB-nota">Este bono no tiene reglas: no se paga a nadie.</p>')
                + F.seccion('Efecto de las justificaciones')
                + (efectosHtml || '<p class="fcB-nota">No hay justificaciones.</p>')
                + (canEdit ? F.pie(b.usa_productos_4 ? '' : '<button type="button" class="fcB-btn borra" onclick="confirmDeleteBono(' + b.id + ')"><i class="bi bi-trash3" aria-hidden="true"></i>Eliminar bono</button>',
                    '<button type="button" class="fcB-btn pri" onclick="editBono(' + b.id + ')"><i class="bi bi-pencil" aria-hidden="true"></i>Editar bono</button>') : '');
        }
    });
}

// ==========================================
// BONOS: MODAL Y FORMULARIO
// ==========================================
async function openModalBono(bono = null) {
    await _cargarCatalogoCargosBono();

    const modal = document.getElementById('modal-bono');
    const title = document.getElementById('modal-bono-title');
    const form = document.getElementById('form-bono');
    const container = document.getElementById('reglas-container');
    const areasContainer = document.getElementById('bono-areas-container');

    form.reset();
    container.innerHTML = '';
    document.getElementById('bono-vista-previa').innerHTML = '';

    if (bono) {
        title.innerText = 'Editar Bono';
        document.getElementById('bono-id').value = bono.id;
        document.getElementById('bono-nombre').value = bono.nombre;
        document.getElementById('bono-descripcion').value = bono.descripcion || '';
        document.getElementById('bono-activo').value = bono.activo ? 'true' : 'false';
        if (bono.reglas) {
            bono.reglas.forEach(r => addBonoReglaRow(r, bono.tipo === 'beneficio'));
        }
    } else {
        title.innerText = 'Crear Nuevo Bono';
        document.getElementById('bono-id').value = '';
        addBonoReglaRow();
    }

    // Efecto de la inasistencia sin justificar y de cada justificación en este bono (etapa B3a)
    // Beneficio en especie (4 Productos, etapa B3d): sin monto en pesos ni «Descuenta en proporción»
    const esBeneficio = !!(bono && bono.tipo === 'beneficio');
    document.getElementById('bono-tipo').value = bono ? (bono.tipo || 'pesos') : 'pesos';
    document.getElementById('bono-nota-beneficio').style.display = esBeneficio ? '' : 'none';
    document.getElementById('bono-antiguedad-wrap').style.display = esBeneficio ? '' : 'none';
    document.getElementById('bono-antiguedad').value = esBeneficio && bono.antiguedad_meses != null ? bono.antiguedad_meses : '';
    // Bono semanal (Fill Rate, 23-11-2026): se evalúa de lunes a domingo y solo lo tienen los horarios elegidos
    document.getElementById('bono-semanal-wrap').style.display = esBeneficio ? 'none' : '';
    document.getElementById('bono-periodicidad').value = bono && bono.periodicidad === 'semanal' ? 'semanal' : 'mensual';
    await _pintarHorariosBono(bono ? (bono.turnos_ids || []) : []);
    document.getElementById('bono-filtra-areas').value = bono && bono.filtra_areas ? 'solo' : 'todas';
    document.getElementById('bono-filtra-turnos').value = bono && (bono.turnos_ids || []).length ? 'solo' : 'todos';
    window._bonoPeriodicidadCambio();
    document.getElementById('bono-efecto-inas-wrap').innerHTML =
        _htmlSelectEfecto('bono-efecto-inas', esBeneficio ? sinProporcion(EFECTOS_INASISTENCIA) : EFECTOS_INASISTENCIA, bono ? (bono.efecto_inasistencia || '') : '');
    const tiposJ = await _asegurarTiposJ();
    document.getElementById('bono-efectos-container').innerHTML =
        _htmlFilasEfecto('bono-ef-', tiposJ, function (t) { return bono ? (bono.efectos || {})[t.id] : ''; }, function () { return opsEfecto(bono); });

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

// Horarios del bono semanal: una casilla por horario en uso
async function _pintarHorariosBono(elegidos) {
    const cont = document.getElementById('bono-turnos-container');
    const esc = window.FichaCfg ? window.FichaCfg.esc : function (x) { return String(x == null ? '' : x); };
    cont.innerHTML = '<span class="text-muted small">Cargando horarios…</span>';
    try {
        const r = await fetch('/api/turnos/?activo=true', { headers: { 'Authorization': 'Bearer ' + localStorage.getItem('access_token') } });
        const lista = r.ok ? await r.json() : [];
        const sel = new Set((elegidos || []).map(Number));
        const items = (Array.isArray(lista) ? lista : (lista.items || [])).slice().sort(function (a, b) { return String(a.nombre).localeCompare(String(b.nombre), 'es'); });
        cont.innerHTML = items.length ? items.map(function (t) {
            return '<div class="form-check form-check-inline m-0"><input class="form-check-input bono-turno-chk" type="checkbox" value="' + t.id + '" id="bono-turno-' + t.id + '"'
                + (sel.has(Number(t.id)) ? ' checked' : '') + '><label class="form-check-label small" for="bono-turno-' + t.id + '">' + esc(t.nombre) + '</label></div>';
        }).join('') : '<span class="text-muted small">No hay horarios en uso.</span>';
    } catch (e) {
        console.error('[openModalBono] Error cargando horarios:', e);
        cont.innerHTML = '<span class="text-muted small text-danger">No se pudieron cargar los horarios.</span>';
    }
}

window._bonoPeriodicidadCambio = function () {
    const semanal = document.getElementById('bono-periodicidad').value === 'semanal';
    document.getElementById('bono-nota-semanal').style.display = semanal ? '' : 'none';
    window._bonoAlcanceCambio();
};

// ¿A quién se le paga? Las casillas de áreas y de horarios se ven solo con «solo estas»
window._bonoAlcanceCambio = function () {
    document.getElementById('bono-areas-container').style.display = document.getElementById('bono-filtra-areas').value === 'solo' ? '' : 'none';
    document.getElementById('bono-turnos-container').style.display = document.getElementById('bono-filtra-turnos').value === 'solo' ? '' : 'none';
};

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

function addBonoReglaRow(regla = null, beneficio = document.getElementById('bono-tipo') && document.getElementById('bono-tipo').value === 'beneficio') {
    const container = document.getElementById('reglas-container');
    const rowIdx = container.querySelectorAll('.regla-row').length; // ID único basado en el conteo actual
    const div = document.createElement('div');
    div.className = 'regla-row card p-3 mb-2 bg-light border-0 shadow-sm';
    // «Prop.» ya no se muestra (etapa B3a: lo reemplaza el efecto de cada justificación); se guarda el valor que tenía
    div.dataset.prop = regla && regla.es_proporcional ? '1' : '0';

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
            <div class="col-md-6" ${beneficio ? 'style="display:none"' : ''}>
                <label for="rule-monto-${rowIdx}" class="small text-muted fw-bold">2. Monto Base ($)</label>
                <div class="input-group input-group-sm">
                    <span class="input-group-text">$</span>
                    <input type="number" id="rule-monto-${rowIdx}" class="rule-monto form-control font-monospace fw-bold" value="${regla ? regla.monto : 0}" required>
                </div>
            </div>
        </div>
        <div class="row g-2 align-items-start">
            <div class="col-md-5">
                <span class="small text-muted d-block mb-1">3. Cargos que lo reciben</span>
                ${_htmlPickerCargos('rule-cargos-req', regla ? regla.cargos_req_ids : null, 'Todos los cargos')}
            </div>
            <div class="col-md-6">
                <span class="small text-muted text-danger d-block mb-1">4. Cargos que no lo reciben</span>
                ${_htmlPickerCargos('rule-cargos-excl', regla ? regla.cargos_excl_ids : null, 'Ninguno')}
            </div>
            <div class="col-md-1 text-end">
                <button type="button" class="btn btn-sm btn-outline-danger w-100" onclick="this.closest('.regla-row').remove()" title="Eliminar regla">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        </div>
    `;
    container.appendChild(div);

}

// Lo que dice la ventana del bono, listo para enviar. Devuelve null (y avisa) si falta elegir algo.
function _leerFormularioBono() {
    const nombre = document.getElementById('bono-nombre').value;
    const descripcion = document.getElementById('bono-descripcion').value;
    const activo = document.getElementById('bono-activo').value === 'true';

    // Recolectar reglas
    const reglas = [];
    document.querySelectorAll('#modal-bono .regla-row').forEach(row => {
        reglas.push({
            monto: parseFloat(row.querySelector('.rule-monto').value) || 0,
            tipo_contrato: row.querySelector('.rule-contrato').value || null,
            // Cargos elegidos de la lista (etapa B3b); la «asistencia mínima» ya no existe en las reglas de Aguacol
            cargos_req_ids: _leerPickerCargos(row.querySelector('.rule-cargos-req')),
            cargos_excl_ids: _leerPickerCargos(row.querySelector('.rule-cargos-excl')),
            es_proporcional: row.dataset.prop === '1'
        });
    });
    // Efectos (etapa B3a): no se guarda sin elegirlos todos
    const efectoInas = document.getElementById('bono-efecto-inas').value;
    if (!efectoInas) { showToast('Falta elegir qué hace una inasistencia sin justificar con el bono.', 'warning'); return null; }
    const efJ = _leerEfectos(document.getElementById('bono-efectos-container'));
    if (efJ.falta) { showToast('Falta elegir el efecto de «' + efJ.falta + '» en el bono.', 'warning'); return null; }
    // Áreas asignadas: dentro de la ventana. null solo si no se dibujaron (no tocar las guardadas)
    const modalBonoEl = document.getElementById('modal-bono');
    const area_ids = Array.from(modalBonoEl.querySelectorAll('.bono-area-chk:checked')).map(chk => parseInt(chk.value));
    const totalAreas = modalBonoEl.querySelectorAll('.bono-area-chk').length;
    const tipo = document.getElementById('bono-tipo').value || 'pesos';
    if (tipo === 'beneficio') reglas.forEach(function (r) { r.monto = 0; });
    let antiguedad_meses = null;
    if (tipo === 'beneficio') {
        const v = document.getElementById('bono-antiguedad').value;
        if (v === '' || isNaN(parseInt(v, 10)) || parseInt(v, 10) < 0) { showToast('Falta la antigüedad mínima en meses (0 o más).', 'warning'); return null; }
        antiguedad_meses = parseInt(v, 10);
    }
    const periodicidad = tipo === 'beneficio' ? 'mensual' : (document.getElementById('bono-periodicidad').value || 'mensual');
    // ¿A quién se le paga? (23-11-2026): áreas y horarios, «todos» o «solo estos»
    const filtra_areas = document.getElementById('bono-filtra-areas').value === 'solo';
    if (filtra_areas && !area_ids.length) { showToast('Elija al menos un área, o «Todas las áreas».', 'warning'); return null; }
    const soloHorarios = document.getElementById('bono-filtra-turnos').value === 'solo';
    const turnos_ids = soloHorarios
        ? Array.from(modalBonoEl.querySelectorAll('.bono-turno-chk:checked')).map(function (c) { return parseInt(c.value, 10); }) : [];
    if (soloHorarios && !turnos_ids.length) { showToast('Elija al menos un horario, o «Todos los horarios».', 'warning'); return null; }
    return { nombre, descripcion, activo, tipo, antiguedad_meses, reglas, periodicidad, turnos_ids, filtra_areas, area_ids: totalAreas === 0 ? null : area_ids, efecto_inasistencia: efectoInas, efectos: efJ.valores };
}

// ── Vista previa del bono (etapa B3c del plan de bonos) ──
// Quién lo recibe y cuánto en el período vigente con lo que se está editando, sin guardarlo; y quién calza con dos reglas.
async function _pedirVistaPreviaBono(body) {
    const r = await fetch(`${API_CONFIG}bonos/vista-previa/`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }, body: JSON.stringify(body) });
    const d = await r.json().catch(function () { return {}; });
    if (!r.ok) throw new Error(d.detail || 'No se pudo calcular la vista previa.');
    return d;
}

function _pintarVistaPreviaBono(d) {
    const esc = window.FichaCfg ? window.FichaCfg.esc : function (x) { return String(x == null ? '' : x); };
    const pesos = function (n) { return '$' + Number(n || 0).toLocaleString('es-CL'); };
    const fecha = function (f) { return String(f).slice(8, 10) + '-' + String(f).slice(5, 7) + '-' + String(f).slice(0, 4); };
    const cont = document.getElementById('bono-vista-previa');
    const pisan = d.pisan.length ? '<div class="alert alert-warning small py-2 mb-2"><b>' + (d.pisan.length === 1 ? '1 persona calza' : d.pisan.length + ' personas calzan')
        + ' con más de una regla.</b> Se usa la primera que calza: ' + d.pisan.map(function (p) { return esc(p.nombre) + ' (reglas ' + p.reglas.join(' y ') + ')'; }).join(', ') + '.</div>' : '';
    const filas = d.personas.map(function (p) {
        return '<tr><td>' + esc(p.nombre) + '</td><td>' + esc(p.area) + '</td><td class="text-center">' + (p.regla || '—') + '</td>'
            + '<td class="text-end ' + (p.califica ? '' : 'text-danger fw-bold') + '">' + (p.califica ? (d.beneficio ? 'Recibe' : pesos(p.monto)) : '—') + '</td>'
            + '<td class="small text-muted">' + esc(p.califica && p.motivo.indexOf('Proporcional') !== 0 ? '' : p.motivo) + '</td></tr>';
    }).join('');
    cont.innerHTML = '<div class="border rounded p-2 bg-white">'
        + '<div class="fw-bold small mb-1">Vista previa · período ' + fecha(d.fecha_inicio) + ' al ' + fecha(d.fecha_fin) + ' (días revisados hasta hoy) · no se ha guardado</div>'
        + '<div class="small mb-2">' + d.reciben + (d.reciben === 1 ? ' persona lo recibe' : ' personas lo reciben') + (d.beneficio ? '' : ' · total <b>' + pesos(d.total) + '</b>')
        + (d.no_cobran ? ' · <span class="text-danger">' + d.no_cobran + ' no lo ' + (d.no_cobran === 1 ? 'cobra' : 'cobran') + '</span>' : '') + '</div>'
        + pisan
        + (filas ? '<div style="max-height: 240px; overflow-y: auto;"><table class="table table-sm small mb-0"><thead><tr><th>Persona</th><th>Área</th><th class="text-center">Regla</th><th class="text-end">Monto</th><th>Motivo</th></tr></thead><tbody>'
            + filas + '</tbody></table></div>' : '<div class="small text-muted">Con estas reglas no le corresponde a nadie.</div>')
        + '</div>';
}

window.vistaPreviaBono = async function () {
    const body = _leerFormularioBono();
    if (!body) return;
    const cont = document.getElementById('bono-vista-previa');
    cont.innerHTML = '<span class="text-muted small"><span class="spinner-border spinner-border-sm me-1"></span>Calculando…</span>';
    try { _pintarVistaPreviaBono(await _pedirVistaPreviaBono(body)); }
    catch (e) { cont.innerHTML = '<span class="text-danger small">' + e.message + '</span>'; }
};

async function saveBono() {
    const id = document.getElementById('bono-id').value;
    const body = _leerFormularioBono();
    if (!body) return;
    // Aviso de reglas que se pisan (etapa B3c): si alguien calza con más de una regla, se pregunta antes de guardar
    try {
        const vp = await _pedirVistaPreviaBono(body);
        if (vp.pisan.length) {
            _pintarVistaPreviaBono(vp);
            const ok = await uiConfirm('¿Guardar con reglas que se pisan?', { items: [
                (vp.pisan.length === 1 ? '1 persona calza' : vp.pisan.length + ' personas calzan') + ' con más de una regla de este bono.',
                'Se le aplica la primera que calza. El detalle quedó en la vista previa.'], confirmText: 'Guardar igual' });
            if (!ok) return;
        }
    } catch (e) { console.warn('[saveBono] vista previa:', e.message); }

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
    const bonosEf = await _asegurarBonos();
    const opsPag = pag.map(function (p) { return [p.nombre, p.nombre]; });
    if (t.pagador && !opsPag.some(function (o) { return o[0] === t.pagador; })) opsPag.unshift([t.pagador, t.pagador]);
    const ro = !canEdit;
    panel.innerHTML = F.cabeza(esNuevo ? 'Nuevo tipo de justificación' : t.nombre,
            canEdit ? 'Se cambia aquí mismo. Los cambios valen desde que se guardan.' : 'Solo lectura: su usuario no puede cambiar las justificaciones.')
        + F.campo('Nombre', F.texto('fj-nombre', t.nombre), '', 'fj-nombre')
        + F.campo('Sigla', F.texto('fj-sigla', t.nomenclatura || '', ' maxlength="8"'), 'La que se ve en la grilla, por ejemplo LM o VAC.', 'fj-sigla')
        + F.campo('Cómo se cuentan los días', F.seg('fj-periodo', [['true', 'Días hábiles'], ['false', 'Días corridos']], t.dias_corridos ? 'false' : 'true', ro),
            'Hábiles: de lunes a viernes. Corridos: todos los días.')
        + F.campo('Goce de sueldo', F.seg('fj-goce', [['true', 'Sí, se paga'], ['false', 'No se paga']], t.con_goce_sueldo ? 'true' : 'false', ro),
            'Solo dice si el día se paga en el sueldo. Lo que pasa con cada bono se elige en «Efecto en los bonos».')
        + F.campo('Quién paga', F.lista('fj-pagador', opsPag, t.pagador || 'Empleador'), '', 'fj-pagador')
        + F.campo('Días por defecto', F.numero('fj-dias', t.dias_defecto, ' min="0"'), 'Los que se proponen al registrarla. Vacío: se eligen a mano.', 'fj-dias')
        + F.campo('En uso', F.interruptor('fj-activo', t.activo, 'Se puede elegir al justificar un día'))
        + F.seccion('Efecto en los bonos')
        + '<p class="fcB-nota">Qué pasa con cada bono en un día con esta justificación.</p>'
        + (bonosEf.length ? bonosEf.map(function (b) {
            return F.campo(b.nombre + (b.activo ? '' : ' (no se calcula)'),
                F.lista('fj-ef-' + b.id, [['', 'Elegir…']].concat(opsEfecto(b)), esNuevo ? '' : ((b.efectos || {})[t.id] || '')), '', 'fj-ef-' + b.id);
        }).join('') : '<p class="fcB-nota">No hay bonos.</p>')
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
    // Efecto en cada bono (etapa B3a): no se guarda sin elegirlo en todos
    const efectos_bonos = {};
    for (const b of (bonosList || [])) {
        const sel = panel.querySelector('#fj-ef-' + b.id), e = sel ? sel.value : '';
        if (!e) { showToast('Falta elegir el efecto en el bono «' + b.nombre + '».', 'warning'); return; }
        efectos_bonos[b.id] = e;
    }
    const body = {
        nombre: nombre, nomenclatura: v('fj-sigla'), descripcion: v('fj-desc'), con_goce_sueldo: goce,
        dias_habiles: habiles, dias_corridos: !habiles, pagador: panel.querySelector('#fj-pagador').value, dias_defecto: num('fj-dias'),
        activo: panel.querySelector('#fj-activo').checked, min_dias: num('fj-min') || 1, max_dias: num('fj-max'), frecuencia_anual: num('fj-frec'),
        sobreescribe_feriados: F.leerSeg(panel, 'fj-feriados') === 'true', es_horas_sindicales: F.leerSeg(panel, 'fj-sindical') === 'true',
        descuenta_remuneracion: !goce, es_por_horas: F.leerSeg(panel, 'fj-parcial') === 'true', genera_deuda_horaria: F.leerSeg(panel, 'fj-deuda') === 'true',
        efectos_bonos: efectos_bonos
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
        await loadBonos();
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

    // Efecto en cada bono (etapa B3a)
    const cont = document.getElementById('tipo-j-efectos');
    cont.innerHTML = '<span class="text-muted small">Cargando bonos…</span>';
    _asegurarBonos().then(function (bonos) {
        cont.innerHTML = _htmlFilasEfecto('tipo-j-ef-', bonos, function (b) { return tipo ? (b.efectos || {})[tipo.id] : ''; }, opsEfecto);
    });

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
    // Efecto en cada bono (etapa B3a): no se guarda sin elegirlo en todos
    const efT = _leerEfectos(document.getElementById('tipo-j-efectos'));
    if (efT.falta) { showToast('Falta elegir el efecto en el bono «' + efT.falta + '».', 'warning'); return; }
    body.efectos_bonos = efT.valores;

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
        bonosList = [];
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
                    + F.campo('Avisos de cierre del período', '<input type="text" class="fcB-inp" id="email-notificaciones-cierre-rrhh" value="' + F.esc(res[1] || '') + '" placeholder="gerencia@empresa.cl">', 'Reciben el informe de cierre (PDF) cuando se cierra un tramo.', 'email-notificaciones-cierre-rrhh')
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
// showToast es el de main.js (auditoría 15-11-2026: esta copia la reemplazaba el de main.js al terminar la carga)


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
            'asistencia_minimo_horas_extra_minutos': 'ajuste-minimo-extras',
            'porteria_deshacer_segundos': 'ajuste-deshacer-segundos',
            'libreta_conduccion_continua_max_horas': 'ajuste-libreta-cond-continua',
            'libreta_descanso_ininterrumpido_horas': 'ajuste-libreta-descanso',
            'libreta_tolerancia_gps_minutos': 'ajuste-libreta-tolerancia',
            'gps_velocidad_limite_kmh': 'ajuste-gps-velocidad'
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
                + F.campo('Nombres distintos que trae BioAlba', erroresBioAlba(c.alias, canEdit ? 'confirmDeleteCargoAlias' : ''), 'Al desvincular uno, las personas con ese cargo en BioAlba dejan de asignarse a este.')
                + (canEdit ? F.pie('<button type="button" class="fcB-btn" onclick="unirCargo(' + c.id + ')"><i class="bi bi-intersect" aria-hidden="true"></i>Unir con otro cargo</button>',
                    '<button type="button" class="fcB-btn pri" onclick="renombrarCargo(' + c.id + ')"><i class="bi bi-pencil" aria-hidden="true"></i>Renombrar</button>') : '');
        }
    });
};

// ── Renombrar y unir cargos (etapa B3b del plan de bonos) ──
async function _usoCargo(cargoId) {
    const r = await fetch(`/api/configuracion/cargos/${cargoId}/uso/`, { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` } });
    return r.ok ? await r.json() : { personas: 0, activas: 0, reglas: [] };
}

function _textoUso(u) {
    return [(u.personas === 1 ? '1 persona' : u.personas + ' personas') + ' (' + u.activas + (u.activas === 1 ? ' activa)' : ' activas)'),
            u.reglas.length ? 'Reglas de bono: ' + u.reglas.join(', ') + '.' : 'Ninguna regla de bono lo nombra.'];
}

window.renombrarCargo = async function (cargoId) {
    const cargo = (await (await fetch('/api/configuracion/cargos/', { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` } })).json())
        .find(function (c) { return c.id === cargoId; });
    if (!cargo) return;
    const u = await _usoCargo(cargoId);
    const v = await uiPedir({ titulo: 'Renombrar cargo', texto: 'El nombre actual («' + cargo.nombre + '») queda como nombre de BioAlba, así la sincronización lo sigue reconociendo. ' + _textoUso(u).join(' '),
        campos: [{ nombre: 'nombre', etiqueta: 'Nombre nuevo', valor: cargo.nombre, requerido: true }], confirmText: 'Renombrar' });
    if (!v || v.nombre === cargo.nombre) return;
    const r = await fetch(`/api/configuracion/cargos/${cargoId}/renombrar/`, { method: 'PUT',
        headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ nombre: v.nombre }) });
    const d = await r.json().catch(function () { return {}; });
    if (!r.ok) { showToast(d.detail || 'No se pudo renombrar el cargo.', 'danger'); return; }
    showToast('Listo. El cargo se llama «' + d.nombre + '».', 'success');
    cargarCatalogoCargos();
};

window.unirCargo = async function (cargoId) {
    const cargos = await (await fetch('/api/configuracion/cargos/', { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` } })).json();
    const origen = cargos.find(function (c) { return c.id === cargoId; });
    if (!origen) return;
    const opciones = {};
    cargos.filter(function (c) { return c.id !== cargoId; }).sort(function (a, b) { return String(a.nombre).localeCompare(String(b.nombre), 'es'); })
        .forEach(function (c) { opciones[c.id] = c.nombre; });
    const u = await _usoCargo(cargoId);
    const elegido = await Swal.fire({ title: 'Unir «' + origen.nombre + '» con otro cargo', input: 'select', inputOptions: opciones,
        inputPlaceholder: 'Elija el cargo que queda', showCancelButton: true, confirmButtonText: 'Seguir', cancelButtonText: 'Cancelar', reverseButtons: true,
        inputValidator: function (x) { return x ? null : 'Elija el cargo que queda.'; } });
    if (!elegido.isConfirmed) return;
    const destino = opciones[elegido.value];
    const ok = await uiConfirm('¿Unir «' + origen.nombre + '» en «' + destino + '»?', { items: _textoUso(u).concat(['Todo pasa a «' + destino + '» y «' + origen.nombre + '» queda como nombre de BioAlba.', '«' + origen.nombre + '» se borra de la lista. No se puede deshacer desde la pantalla.']),
        confirmText: 'Unir cargos', danger: true });
    if (!ok) return;
    const r = await fetch(`/api/configuracion/cargos/${cargoId}/unir/`, { method: 'POST',
        headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ destino_id: parseInt(elegido.value, 10) }) });
    const d = await r.json().catch(function () { return {}; });
    if (!r.ok) { showToast(d.detail || 'No se pudieron unir los cargos.', 'danger'); return; }
    showToast('Listo. «' + d.origen + '» quedó unido en «' + d.destino + '».', 'success');
    cargarCatalogoCargos();
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
// RAZONES DE NOTA DE CRÉDITO (Fill Rate, 23-11-2026)
// Cada razón dice si es culpa del chofer: entonces el día no cumple el Fill Rate y se pierde la semana. No se borran:
// las que ya se usaron quedan en el historial; se desactivan.
// ==========================================
window.cargarRazonesNotaCredito = async function () {
    const razones = await leerCatalogo('/api/configuracion/razones-nota-credito/', 'razones-nc-container', 'las razones de nota de crédito');
    if (!razones) return;
    const F = window.FichaCfg, canEdit = F.puede('configuracion.editar');
    montarCatalogoB('razones-nc-container', {
        clave: 'razones-nc',
        titulo: 'Notas de crédito',
        descripcion: 'Razones de nota de crédito que se eligen al evaluar el Fill Rate de un día. Si la razón es culpa del chofer, ese día no cumple y la semana no se paga.',
        acciones: (canEdit ? '<button type="button" class="fcB-btn pri" onclick="window.nuevaRazonNotaCredito()"><i class="bi bi-plus-lg" aria-hidden="true"></i>Nueva razón</button>' : '')
            + '<button type="button" class="fcB-btn" onclick="cargarRazonesNotaCredito()"><i class="bi bi-arrow-clockwise" aria-hidden="true"></i>Actualizar</button>',
        items: razones,
        id: function (r) { return r.id; },
        etiqueta: function (r) { return r.nombre; },
        sub: function (r) { return (r.culpa_chofer ? 'Culpa del chofer' : 'No es culpa del chofer') + (r.usos ? ' · usada ' + r.usos + (r.usos === 1 ? ' vez' : ' veces') : ''); },
        apagado: function (r) { return !r.activa; },
        vacio: 'Todavía no hay razones. Cree la primera con «Nueva razón».',
        ficha: function (r, panel) {
            panel.innerHTML = F.cabeza(r.nombre, canEdit ? 'Cambie lo que necesite y guarde.' : 'Solo lectura.')
                + F.campo('Nombre', F.texto('rnc-nombre', r.nombre, canEdit ? ' maxlength="120"' : ' disabled'))
                + F.campo('¿Es culpa del chofer?', F.seg('rnc-culpa', [['1', 'Sí: no cumple'], ['0', 'No: cumple']], r.culpa_chofer ? '1' : '0', !canEdit),
                    'Si es culpa del chofer, el día no cumple y la semana no se paga.')
                + F.campo('En uso', F.interruptor('rnc-activa', !!r.activa, 'Se puede elegir al evaluar un día'))
                + F.campo('Historial', '<span>' + (r.usos ? 'Usada en ' + r.usos + (r.usos === 1 ? ' día' : ' días') + ': se guarda tal como estaba ese día.' : 'Aún no se usa.') + '</span>')
                + (canEdit ? F.pie('', '<button type="button" class="fcB-btn pri" onclick="window.guardarRazonNotaCredito(' + r.id + ', this)"><i class="bi bi-check2" aria-hidden="true"></i>Guardar</button>') : '');
            if (!canEdit) { const sw = panel.querySelector('#rnc-activa'); if (sw) sw.disabled = true; }
        }
    });
};

async function _pedirRazonNC(url, metodo, cuerpo) {
    const r = await fetch(url, { method: metodo, headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + localStorage.getItem('access_token') }, body: JSON.stringify(cuerpo) });
    const d = await r.json().catch(function () { return {}; });
    if (!r.ok) throw new Error(d.detail || 'No se pudo guardar.');
    return d;
}

window.nuevaRazonNotaCredito = async function () {
    const v = await uiPedir({ titulo: 'Nueva razón de nota de crédito', confirmText: 'Crear',
        campos: [{ nombre: 'nombre', etiqueta: 'Nombre', tipo: 'text', requerido: true, ayuda: 'Por ejemplo: producto dañado en el traslado' }] });
    if (!v) return;
    const culpa = await uiConfirm('¿Esta razón es culpa del chofer?', { items: ['Sí: el día no cumple y la semana no se paga.', 'No: el día cumple.'],
        confirmText: 'Sí, es culpa del chofer', cancelText: 'No es culpa del chofer', danger: false });
    try {
        await _pedirRazonNC('/api/configuracion/razones-nota-credito/', 'POST', { nombre: v.nombre, culpa_chofer: !!culpa, activa: true });
        showToast('Razón creada.', 'success');
        cargarRazonesNotaCredito();
    } catch (e) { showToast(e.message, 'error'); }
};

window.guardarRazonNotaCredito = async function (id, btn) {
    const panel = btn.closest('.fcB-ficha') || document;
    const nombre = (panel.querySelector('#rnc-nombre').value || '').trim();
    if (!nombre) { showToast('Falta el nombre de la razón.', 'warning'); return; }
    try {
        await _pedirRazonNC('/api/configuracion/razones-nota-credito/' + id + '/', 'PUT', {
            nombre: nombre, culpa_chofer: window.FichaCfg.leerSeg(panel, 'rnc-culpa') === '1', activa: panel.querySelector('#rnc-activa').checked });
        showToast('Razón guardada.', 'success');
        window.FichaCfg.recordar('razones-nc', id);
        cargarRazonesNotaCredito();
    } catch (e) { showToast(e.message, 'error'); }
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
    const esc = (t) => window.Ayuda.esc(t);
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
                const acta = "descargarInformeCierre('" + p.fecha_inicio + "','" + p.fecha_fin + "','" + esc(a) + "',this)";
                const resumen = "verResumenCierre('" + p.fecha_inicio + "','" + p.fecha_fin + "','" + esc(a) + "','" + esc((c.por || '').replace(/'/g, '')) + "')";
                html += '<td><div class="c-ok" title="' + esc(a) + ': cerrada' + (c.fecha ? ' el ' + formatDateDMY(c.fecha) : '') + (c.por ? ' por ' + esc(c.por) : '') + '">'
                    + '<i class="bi bi-check-circle-fill" aria-hidden="true"></i>'
                    + (c.fecha ? '<b>' + corta(c.fecha) + '</b>' : '<b>Cerrada</b>')
                    + (c.por ? '<small>' + esc(c.por) + '</small>' : '')
                    + '<span class="tA-bts"><button type="button" class="tA-acta" onclick="' + resumen + '" aria-label="Ver el resumen del cierre de ' + esc(a) + '"><i class="bi bi-file-text" aria-hidden="true"></i>Resumen</button>'
                    + ((c.informes && c.informes.length)
                        ? c.informes.map((inf) => '<button type="button" class="tA-acta" onclick="descargarInformeTipo(\'' + p.fecha_inicio + '\',\'' + p.fecha_fin + '\',\'' + esc(a) + '\',\'' + esc(inf.tipo) + '\',\'' + esc(inf.titulo) + '\')" aria-label="Descargar el informe de cierre de ' + esc(a) + ', ' + esc(inf.titulo) + ' (PDF)"><i class="bi bi-file-earmark-pdf" aria-hidden="true"></i>' + esc(inf.titulo) + '</button>').join('')
                        : '<button type="button" class="tA-acta" onclick="' + acta + '" aria-label="Descargar el informe de cierre de ' + esc(a) + ' (PDF, uno por tipo de horario)"><i class="bi bi-file-earmark-pdf" aria-hidden="true"></i>Informe</button>')
                    + '</span>'
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
        + '<div class="tA-leg"><span class="ok"><i class="bi bi-check-circle-fill" aria-hidden="true"></i>Cerrada: fecha y quién cerró; «Resumen» muestra el balance; cada botón de horas descarga el informe PDF de ese tipo de horario</span>'
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
        'notas-credito-tab': 'notas de credito razones fill rate chofer culpa',
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

// ── Mapa del código (dueño, 15-11-2026) ────────────────────────────────────────────────────────────────────────────
// El grafo de graphify, solo para el súper administrador. El servidor lo entrega con la sesión (no está en /static, que es
// público); la página se arma en un Blob para el iframe. Arriba dice de cuándo es y cuántos archivos cambiaron después.
window.cargarMapaCodigo = async function () {
    const cont = document.getElementById('mapa-codigo-container');
    if (!cont) return;
    const e = window.escHtml || (t => String(t == null ? '' : t));
    const h = { 'Authorization': 'Bearer ' + AuthService.getToken() };
    const fecha = iso => { try { return new Date(iso).toLocaleString('es-CL', { dateStyle: 'medium', timeStyle: 'short' }); } catch (_) { return iso || ''; } };
    cont.innerHTML = '<div class="text-muted py-4"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Cargando el mapa del código…</div>';
    let est;
    try {
        const r = await fetch('/api/configuracion/mapa-codigo/estado/', { headers: h });
        est = await r.json();
        if (!r.ok) throw new Error(est.detail || ('Error ' + r.status));
    } catch (err) {
        cont.innerHTML = '<div class="alert alert-danger">No se pudo leer el mapa: ' + e(err.message) + '</div>';
        return;
    }
    const comoSeActualiza = '<p class="small text-muted mb-0">No se actualiza solo: en el PC de desarrollo, <code>scripts/publicar_mapa.py</code> '
        + 'lo rehace con el código de ese momento, y se sube junto con cada cambio de código.</p>';
    if (!est.publicado) {
        cont.innerHTML = '<div class="fcB-h mb-3"><div><h2>Mapa del código</h2><p>Todavía no hay un mapa publicado.</p></div></div>' + comoSeActualiza;
        return;
    }
    const n = (est.cambiados || []).length + (est.borrados || []).length;
    const aviso = est.al_dia
        ? '<span class="badge rounded-pill bg-success-subtle text-success-emphasis text-start" style="white-space:normal"><i class="bi bi-check-circle me-1" aria-hidden="true"></i>Al día con el código</span>'
        : '<span class="badge rounded-pill bg-warning-subtle text-warning-emphasis text-start" style="white-space:normal"><i class="bi bi-exclamation-triangle me-1" aria-hidden="true"></i>Desactualizado: '
          + n + (n === 1 ? ' archivo cambió' : ' archivos cambiaron') + ' después de armarlo</span>';
    const lista = n ? '<details class="mt-2 small"><summary style="cursor:pointer">Ver cuáles</summary><ul class="mb-0 mt-1">'
        + (est.cambiados || []).map(f => '<li><code>' + e(f) + '</code></li>').join('')
        + (est.borrados || []).map(f => '<li><code>' + e(f) + '</code> (ya no existe)</li>').join('') + '</ul></details>' : '';
    // Lo primero son los hallazgos en palabras (dueño, 15-11-2026: «para mí el grafo es solo ver puntos»); el grafo queda
    // como detalle para quien programa y se pide recién al abrirlo (pesa unos 5 MB).
    cont.innerHTML = '<div class="fcB-h mb-2"><div><h2>Mapa del código</h2><p>Lo que muestra el análisis del código de la aplicación: dónde conviene mejorar. Solo lectura.</p></div></div>'
        + '<div class="border rounded-3 bg-white p-3 mb-3"><div class="d-flex flex-wrap align-items-center gap-3">' + aviso
        + '<span class="small text-nowrap">Armado el <b>' + e(fecha(est.armado)) + '</b></span>'
        + (est.commit ? '<span class="small text-nowrap">sobre el commit <code>' + e(est.commit) + '</code></span>' : '')
        + '<span class="small text-muted text-nowrap">' + e(est.archivos_comparados) + ' archivos comparados</span>'
        + '</div>' + lista + '<div class="mt-2">' + comoSeActualiza + '</div></div>'
        + '<div id="mapa-codigo-hallazgos" class="d-flex flex-column gap-3 mb-3"><div class="text-muted small">Cargando los hallazgos…</div></div>'
        + '<details id="mapa-codigo-grafo-det" class="border rounded-3 bg-white p-3 mb-3"><summary class="fw-semibold" style="cursor:pointer">Ver el grafo (para quien programa)</summary>'
        + '<div class="d-flex justify-content-end my-2"><button type="button" class="btn btn-sm btn-outline-primary" id="mapa-codigo-abrir" disabled><i class="bi bi-box-arrow-up-right me-1" aria-hidden="true"></i>Abrir en otra pestaña</button></div>'
        + '<div class="border rounded-3 overflow-hidden" style="height:72vh;min-height:420px"><iframe id="mapa-codigo-iframe" title="Mapa del código" style="width:100%;height:100%;border:0" sandbox="allow-scripts allow-popups"></iframe></div></details>'
        + '<details class="border rounded-3 bg-white p-3"><summary class="fw-semibold" style="cursor:pointer">Informe técnico del mapa</summary><pre id="mapa-codigo-informe" class="small mt-2 mb-0" style="white-space:pre-wrap">Cargando…</pre></details>';

    const tarjeta = (titulo, porQue, cuerpo) => '<section class="border rounded-3 bg-white p-3"><h3 class="h6 fw-bold mb-1">' + titulo + '</h3>'
        + '<p class="small text-muted mb-2">' + porQue + '</p>' + cuerpo + '</section>';
    const tabla = (cabeza, filas) => filas.length ? '<div class="table-responsive"><table class="table table-sm small mb-0"><thead><tr>'
        + cabeza.map(c => '<th>' + c + '</th>').join('') + '</tr></thead><tbody>' + filas.map(f => '<tr>' + f.map(c => '<td>' + c + '</td>').join('') + '</tr>').join('')
        + '</tbody></table></div>' : '<p class="small mb-0 text-success"><i class="bi bi-check-circle me-1" aria-hidden="true"></i>No se encontró ninguno.</p>';
    const num = v => Number(v || 0).toLocaleString('es-CL');
    const dondeCorto = lista2 => '<span class="text-muted">' + lista2.slice(0, 4).map(a => e(a.split('/').pop())).join(', ') + (lista2.length > 4 ? '…' : '') + '</span>';
    try {
        const r = await fetch('/api/configuracion/mapa-codigo/hallazgos/', { headers: h });
        const hz = await r.json();
        if (!r.ok) throw new Error(hz.detail || ('Error ' + r.status));
        const rep = hz.repetidas || {}, lar = hz.funciones_largas || {}, sql = hz.sql_en_routers || {};
        const sinUso = hz.sin_uso || [], ciclos = hz.ciclos || [];
        document.getElementById('mapa-codigo-hallazgos').innerHTML = [
            tarjeta('1. Funciones con el mismo nombre en varios archivos (' + num(rep.total) + ')',
                'Puede ser la misma ayuda escrita varias veces: si se corrige un error en una, las demás lo siguen teniendo. Revisar las primeras: si hacen lo mismo, conviene dejar una sola.',
                tabla(['Nombre', 'Archivos', 'Dónde'], (rep.top || []).map(x => ['<code>' + e(x.nombre) + '</code>', num(x.archivos.length), dondeCorto(x.archivos)]))),
            tarjeta('2. Las funciones más largas del servidor',
                'Una función muy larga es difícil de leer y de probar por partes; cambiarla es más riesgoso. Las del cálculo se parten en pasos chicos, con la prueba guardiana.',
                tabla(['Función', 'Líneas', 'Archivo'], (lar.top || []).map(x => ['<code>' + e(x.funcion) + '</code>', num(x.lineas), '<span class="text-muted">' + e(x.archivo) + '</span>']))),
            tarjeta('3. Los archivos más grandes',
                'Un archivo enorme mezcla temas: cuesta encontrar las cosas y un cambio toca muchas líneas.',
                tabla(['Archivo', 'Líneas'], (hz.archivos_grandes || []).map(x => [e(x.archivo), num(x.lineas)]))),
            tarjeta('4. Consultas a la base escritas en los routers (' + num(sql.total) + ')',
                'Lo ordenado es que las consultas vivan en los repositorios; repartidas en los routers cuesta revisar su traducción a PostgreSQL.',
                tabla(['Archivo', 'Consultas'], (sql.top || []).map(x => [e(x.archivo), num(x.consultas)]))),
            tarjeta('5. Funciones que nadie usa (' + num(sinUso.length) + ')',
                'Nadie las llama según el grafo y su nombre no aparece en otra parte del código. Son candidatas: revisar una por una antes de borrarlas.',
                tabla(['Función', 'Archivo'], sinUso.map(x => ['<code>' + e(x.funcion) + '</code>', '<span class="text-muted">' + e(x.archivo) + '</span>']))),
            tarjeta('6. Dependencias circulares (' + num(ciclos.length) + ')',
                'Dos archivos que se necesitan mutuamente: un cambio en uno puede romper el otro.',
                tabla(['Ciclo'], ciclos.map(c => ['<code>' + e(c) + '</code>']))),
        ].join('');
    } catch (err) {
        document.getElementById('mapa-codigo-hallazgos').innerHTML = '<div class="alert alert-warning mb-0">No se pudieron leer los hallazgos: ' + e(err.message) + '</div>';
    }

    const det = document.getElementById('mapa-codigo-grafo-det');
    const cargarGrafo = async () => {
        if (!det.open) return;
        det.removeEventListener('toggle', cargarGrafo);
        try {
            const r = await fetch('/api/configuracion/mapa-codigo/grafo/', { headers: h });
            if (!r.ok) throw new Error('Error ' + r.status);
            const url = URL.createObjectURL(new Blob([await r.text()], { type: 'text/html' }));
            if (window._mapaCodigoUrl) URL.revokeObjectURL(window._mapaCodigoUrl);
            window._mapaCodigoUrl = url;
            document.getElementById('mapa-codigo-iframe').src = url;
            const b = document.getElementById('mapa-codigo-abrir');
            b.disabled = false;
            b.onclick = () => window.open(url, '_blank', 'noopener');
        } catch (err) {
            document.getElementById('mapa-codigo-iframe').outerHTML = '<div class="alert alert-danger m-3">No se pudo cargar el grafo: ' + e(err.message) + '</div>';
        }
    };
    det.addEventListener('toggle', cargarGrafo);
    fetch('/api/configuracion/mapa-codigo/informe/', { headers: h }).then(r => r.ok ? r.text() : Promise.reject(r.status))
        .then(t => { document.getElementById('mapa-codigo-informe').textContent = t; })
        .catch(() => { document.getElementById('mapa-codigo-informe').textContent = 'No se pudo cargar el informe.'; });
};


// ── WhatsApp de avisos (Configuración → Administración → WhatsApp) ──
// Los textos van con comillas y concatenación: el minificador del servidor (rjsmin) come los espacios de las plantillas anidadas.
(function () {
    const H = function () { return { 'Authorization': 'Bearer ' + localStorage.getItem('access_token'), 'Content-Type': 'application/json' }; };
    const esc = function (t) { return String(t == null ? '' : t).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
    const TXT = { conectado: 'Conectado', conectando: 'Conectando…', desconectado: 'Desconectado', sin_puerta: 'La puerta de WhatsApp no responde', apagado: 'Apagado (falta WHATSAPP_ENABLED y el token en el servidor)' };
    let timer = null, grupos = null;

    async function api(metodo, ruta, cuerpo) {
        const r = await fetch('/api/whatsapp' + ruta, { method: metodo, headers: H(), body: cuerpo ? JSON.stringify(cuerpo) : undefined });
        const j = await r.json().catch(function () { return {}; });
        return { ok: r.ok, j: j };
    }
    const msg = function (t) { const e = document.getElementById('wa-msg'); if (e) e.innerHTML = t; };

    // ── Estado, QR, cortar conexión y prueba ──
    function pintarEstado(d) {
        const c = document.getElementById('wa-estado');
        if (!c) return;
        const ok = d.estado === 'conectado';
        let h = '<p><b>Estado:</b> <span class="badge ' + (ok ? 'bg-success' : 'bg-secondary') + '">' + esc(TXT[d.estado] || d.estado) + '</span></p>';
        if (d.qr) h += '<div class="mb-3"><img src="' + esc(d.qr) + '" alt="Código QR" width="260" height="260"><div class="text-muted" style="font-size:0.85rem;">En el teléfono: WhatsApp → Dispositivos vinculados → Vincular un dispositivo.</div></div>';
        if (ok) {
            h += '<div class="d-flex flex-wrap gap-2 align-items-center mb-2">'
                + '<input id="wa-tel" class="form-control" placeholder="Celular de prueba, ej. 9 1234 5678" inputmode="tel" style="max-width:260px;">'
                + '<button class="btn btn-outline-primary" id="wa-prueba">Enviar prueba</button>'
                + '<button class="btn btn-outline-danger ms-auto" id="wa-cortar">Cortar conexión</button></div>';
        }
        c.innerHTML = h;
        const b = function (id, fn) { const e = document.getElementById(id); if (e) e.onclick = fn; };
        b('wa-prueba', async function () {
            msg('Enviando…');
            const r = await api('POST', '/prueba', { telefono: document.getElementById('wa-tel').value });
            msg(r.ok ? 'Prueba enviada.' : esc(r.j.detail || 'No se pudo enviar.'));
        });
        b('wa-cortar', async function () {
            if (!window.confirm('Se cerrará la sesión de WhatsApp de este número y dejarán de enviarse los avisos hasta vincularlo de nuevo con un QR. ¿Cortar la conexión?')) return;
            msg('Cortando…');
            const r = await api('POST', '/desconectar');
            grupos = null;
            msg(r.ok ? 'Conexión cortada. En unos segundos aparece un QR nuevo.' : esc(r.j.detail || 'No se pudo cortar.'));
        });
    }

    // ── Avisos automáticos: encender y asignar chats ──
    function pintarAvisos(cfg, conectado) {
        const c = document.getElementById('wa-avisos');
        if (!c) return;
        c.innerHTML = '<h6 class="mt-4 mb-2">Avisos automáticos <span class="text-muted fw-normal" style="font-size:0.85rem;">(lunes 08:00, si el cron está instalado en el servidor)</span></h6>'
            + cfg.avisos.map(function (a) {
                const usaChats = !!a.usa_chats;
                let h = '<div class="border rounded p-3 mb-3" data-aviso="' + esc(a.aviso) + '">'
                    + '<div class="d-flex justify-content-between align-items-start gap-3"><div><b>' + esc(a.nombre) + '</b>'
                    + '<div class="text-muted" style="font-size:0.85rem;">' + esc(a.descripcion) + '</div></div>'
                    + '<div class="form-check form-switch"><input class="form-check-input wa-sw" type="checkbox" role="switch"' + (a.activo ? ' checked' : '') + '><label class="form-check-label" style="font-size:0.85rem;">Automático</label></div></div>';
                if (usaChats) {
                    h += '<div class="mt-2" style="font-size:0.9rem;"><b>Se envía a:</b> ';
                    h += a.destinos.length ? a.destinos.map(function (d) {
                        const nom = d.etiqueta || d.destino;
                        return '<span class="badge bg-light text-dark border me-1">' + esc(nom) + (d.destino.indexOf('@g.us') > 0 ? ' (grupo)' : '') + ' <a href="#" class="wa-quitar text-danger text-decoration-none" data-id="' + d.id + '" title="Quitar">✕</a></span>';
                    }).join('') : '<span class="text-muted">ningún chat asignado</span>';
                    h += '</div><div class="d-flex flex-wrap gap-2 mt-2">'
                        + '<select class="form-select wa-grupo" style="max-width:260px;"><option value="">Agregar un grupo…</option>'
                        + (grupos || []).map(function (g) { return '<option value="' + esc(g.id) + '">' + esc(g.nombre) + '</option>'; }).join('') + '</select>'
                        + '<input class="form-control wa-num" placeholder="o un celular: 9 1234 5678" inputmode="tel" style="max-width:200px;">'
                        + '<input class="form-control wa-eti" placeholder="Nombre (opcional)" style="max-width:170px;">'
                        + '<button class="btn btn-outline-primary wa-add">Asignar</button></div>';
                    if (conectado && grupos && !grupos.length) h += '<div class="text-muted mt-1" style="font-size:0.8rem;">El número no está en ningún grupo: agréguelo a uno en WhatsApp o asigne un celular.</div>';
                }
                h += '<div class="mt-3"><button class="btn btn-sm btn-outline-secondary me-2 wa-sim">Simular (no envía)</button>'
                    + '<button class="btn btn-sm btn-primary wa-env">Enviar ahora</button></div></div>';
                return h;
            }).join('');

        c.querySelectorAll('[data-aviso]').forEach(function (box) {
            const aviso = box.getAttribute('data-aviso');
            box.querySelector('.wa-sw').onchange = async function (ev) {
                const r = await api('PUT', '/avisos/' + aviso, { activo: ev.target.checked });
                if (!r.ok) { msg(esc(r.j.detail || 'No se pudo cambiar.')); ev.target.checked = !ev.target.checked; } else msg('Guardado.');
            };
            box.querySelectorAll('.wa-quitar').forEach(function (a) {
                a.onclick = async function (ev) { ev.preventDefault(); await api('DELETE', '/destinos/' + a.getAttribute('data-id')); cargarAvisos(); };
            });
            const add = box.querySelector('.wa-add');
            if (add) add.onclick = async function () {
                const sel = box.querySelector('.wa-grupo'), num = box.querySelector('.wa-num').value.trim(), eti = box.querySelector('.wa-eti').value.trim();
                const destino = sel.value || num;
                if (!destino) { msg('Elija un grupo o escriba un celular.'); return; }
                const nombreGrupo = sel.value ? sel.options[sel.selectedIndex].text : '';
                const r = await api('POST', '/avisos/' + aviso + '/destinos', { destino: destino, etiqueta: eti || nombreGrupo });
                if (!r.ok) { msg(esc(r.j.detail || 'No se pudo asignar.')); return; }
                msg('Chat asignado.'); cargarAvisos();
            };
            const correr = async function (simular) {
                msg(simular ? 'Calculando…' : 'Enviando… puede tardar unos minutos.');
                const r = await api('POST', '/resumen-semanal', { simular: simular, aviso: aviso });
                if (!r.ok) return msg(esc(r.j.detail || 'Error al calcular el resumen.'));
                const j = r.j;
                let t = '<b>' + j.personas + '</b> personas en Bolsa. ';
                t += j.chats != null ? 'Chats asignados: <b>' + j.chats + '</b>.' : '<b>' + j.con_telefono + '</b> con celular válido.';
                if ((j.sin_telefono || []).length) t += '<div class="text-muted">Sin celular: ' + esc(j.sin_telefono.join(', ')) + '</div>';
                if (simular) t += (j.vista_previa || []).slice(0, 2).map(function (v) { return '<pre class="mt-2 p-2 bg-light border rounded" style="white-space:pre-wrap;">' + esc(v.nombre) + ' → ' + esc(v.telefono || 'sin celular') + '\n\n' + esc(v.mensaje) + '</pre>'; }).join('');
                else t += '<div class="mt-1">Enviados: <b>' + j.enviados + '</b>, fallidos: <b>' + j.fallidos + '</b>.</div>';
                msg(t);
            };
            box.querySelector('.wa-sim').onclick = function () { correr(true); };
            box.querySelector('.wa-env').onclick = function () { if (window.confirm('Se enviará este aviso por WhatsApp ahora mismo. ¿Continuar?')) correr(false); };
        });
    }

    async function cargarAvisos() {
        const [cfg, gr] = await Promise.all([api('GET', '/config'), grupos ? Promise.resolve(null) : api('GET', '/grupos')]);
        if (gr && gr.ok) grupos = gr.j.grupos || [];
        if (cfg.ok) pintarAvisos(cfg.j, true);
    }

    window.cargarWhatsapp = async function () {
        clearInterval(timer);
        const c = document.getElementById('whatsapp-container');
        c.innerHTML = '<div class="p-3" style="max-width:700px;"><h5 class="mb-1">WhatsApp de avisos</h5>'
            + '<p class="text-muted" style="font-size:0.9rem;">Número propio que envía los avisos. Se vincula una vez escaneando un código QR; luego se asigna qué aviso va a qué chat.</p>'
            + '<div id="wa-estado">Consultando…</div><div id="wa-avisos"></div><div id="wa-msg" class="mt-3" style="font-size:0.9rem;"></div></div>';
        grupos = null;
        let ultimo = null;
        const consultar = async function () {
            const tab = document.getElementById('tab-whatsapp');
            if (!tab || !tab.classList.contains('active')) { clearInterval(timer); return; }
            try {
                const r = await api('GET', '/estado');
                if (!r.ok) throw new Error('estado');
                const d = r.j;
                // Se repinta el estado solo si cambió o hay QR (se renueva); así no se pisa lo que la persona esté escribiendo.
                if (ultimo !== d.estado || d.qr) {
                    const cambio = ultimo !== d.estado; ultimo = d.estado; pintarEstado(d);
                    if (cambio) { grupos = null; if (d.estado === 'conectado') cargarAvisos(); else document.getElementById('wa-avisos').innerHTML = ''; }
                }
            } catch (e) { document.getElementById('wa-estado').innerHTML = '<span class="text-muted">No se pudo consultar el estado de WhatsApp.</span>'; }
        };
        await consultar();
        timer = setInterval(consultar, 4000);
    };
})();
