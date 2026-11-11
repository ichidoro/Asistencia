/**
 * marcaciones_ui.js
 * Módulo para visualizar Asistencia: Vista Matriz (Equipo) y Calendario (Personal).
 */

// ── Fix #A: Caché de metadata — evita llamar /api/empleados/metadata/ múltiples veces ──
// Se invalida automáticamente al agregar/editar empleados o áreas.
window._cachedMetadata = window._cachedMetadata || null;
async function getMetadata(forceRefresh = false) {
    if (!forceRefresh && window._cachedMetadata) return window._cachedMetadata;
    try {
        const resp = await fetch('/api/empleados/metadata/');
        if (resp.ok) {
            window._cachedMetadata = await resp.json();
        }
    } catch (e) {
        console.warn('Error cargando metadata:', e);
    }
    return window._cachedMetadata || { areas: [] };
}

// Evitar conflicto con versiones antiguas en caché (script fantasma)
// Usamos un nombre de variable ÚNICO para esta versión
window.stateMarcacionesApp = window.stateMarcacionesApp || {
    year: new Date().getFullYear(),
    month: new Date().getMonth() + 1,
    isModoRRHH: true,
    fechaInicioRRHH: "",
    fechaFinRRHH: "",
    usuarioModificoFechas: false,
    area: "",
    turnoId: "",
    empleadoId: "",
    viewMode: 'conceptos', // 'conceptos', 'horas', 'he', 'acumulado', 'colacion', 'permisos'
    panelMode: 'analitica', // La vista única será siempre Analítica
    data: null,
    autoRefreshEnabled: true,
    autoRefreshIntervalId: null,
    controllers: {
        filters: null
    }
};

// Estado de la Vista Analítica (si no está ya inicializado)
window.vistaAnaliticaState = window.vistaAnaliticaState || {
    soloNegativo: false,
    soloConHE: false,
    showBonos: false,
    showHE: null,         // null = según tipo: ciclo contraído, bolsa abierto (solo tiene la columna Aprobadas)
    showDeudas: false,
    showIncidencias: false,
    showSaldoMeta: null,  // null = según tipo: Bolsa/Espera abiertos en bolsa flexible
    tabTipo: null         // Pestaña activa en áreas con ambos tipos: 'ciclo' | 'bolsa'
};

// ── Filtros recordados ───────────────────────────────────────────────────────────────────────────────
// Lo que la persona elige (período, área, horario, empleado, vista y columnas abiertas) se guarda en este navegador y vuelve al
// recargar o regresar. La clave lleva el usuario: otra cuenta en el mismo navegador entra con los filtros limpios.
const MX_FILTROS_VERSION = 1;
const MX_VISTAS = ['conceptos', 'horas', 'he', 'acumulado', 'colacion', 'permisos', 'velocidad'];
const MX_VA_BOOL = ['showBonos', 'showHE', 'showDeudas', 'showIncidencias', 'showSaldoMeta', 'soloNegativo', 'soloConHE'];
function mxClaveFiltros() {
    let u = 'anon';
    try { const d = JSON.parse(localStorage.getItem('auth_user_data') || '{}'); u = String(d.username || d.email || d.id || 'anon'); } catch (_) {}
    return 'asistencia_marc_filtros:' + u;
}
window.mxGuardarFiltros = function () {
    try {
        const s = stateMarcacionesApp, va = window.vistaAnaliticaState || {};
        const snap = { v: MX_FILTROS_VERSION, area: s.area || '', turnoId: String(s.turnoId || ''), empleadoId: String(s.empleadoId || ''), viewMode: s.viewMode || 'conceptos', va: { tabTipo: va.tabTipo === undefined ? null : va.tabTipo } };
        MX_VA_BOOL.forEach(k => { snap.va[k] = va[k] === undefined ? null : va[k]; });
        // Las fechas solo se recuerdan si la persona las eligió: si no, cada visita sigue el período activo.
        if (s.fechasElegidas) snap.fechas = { ini: s.fechaInicioRRHH, fin: s.fechaFinRRHH, manual: !!s.usuarioModificoFechas };
        localStorage.setItem(mxClaveFiltros(), JSON.stringify(snap));
    } catch (_) { /* sin almacenamiento: los filtros simplemente no se recuerdan */ }
};
window.mxRestaurarFiltros = function () {
    let snap = null;
    try { snap = JSON.parse(localStorage.getItem(mxClaveFiltros()) || 'null'); } catch (_) {}
    if (!snap || snap.v !== MX_FILTROS_VERSION) return;
    const s = stateMarcacionesApp, va = window.vistaAnaliticaState;
    const esFecha = f => /^\d{4}-\d{2}-\d{2}$/.test(String(f || ''));
    if (typeof snap.area === 'string') s.area = snap.area;
    if (typeof snap.turnoId === 'string') s.turnoId = snap.turnoId;
    if (typeof snap.empleadoId === 'string') s.empleadoId = snap.empleadoId;
    if (MX_VISTAS.includes(snap.viewMode)) s.viewMode = snap.viewMode;
    const f = snap.fechas;
    if (f && esFecha(f.ini) && esFecha(f.fin) && f.ini <= f.fin) {
        s.fechaInicioRRHH = f.ini; s.fechaFinRRHH = f.fin; s.usuarioModificoFechas = !!f.manual; s.fechasElegidas = true;
    }
    const v = snap.va || {};
    MX_VA_BOOL.forEach(k => { if (typeof v[k] === 'boolean' || v[k] === null) va[k] = v[k]; });
    if (v.tabTipo === 'ciclo' || v.tabTipo === 'bolsa' || v.tabTipo === null) va.tabTipo = v.tabTipo;
};
window.mxRestablecerFiltros = function () {
    try { localStorage.removeItem(mxClaveFiltros()); } catch (_) {}
    location.reload();
};
// ── Selectores con buscador ───────────────────────────────────────────────────────────────────────────
// El <select> nativo sigue siendo la fuente de verdad (el resto del código lo lee y lo escribe igual); se esconde y encima se
// dibuja un botón con una lista que se puede buscar y recorrer con el teclado. Lo que el código cambie (value, opciones) se refleja solo.
const MX_COMBO_IDS = { 'rrhh-periodo-select': 'bi-calendar3', 'marcacion-area': 'bi-diagram-3', 'marcacion-turno': 'bi-clock', 'marcacion-empleado': 'bi-person' };
let _mxComboAbierto = null;
const mxNorm = t => String(t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
function mxComboCerrar(wrap, devolverFoco) {
    if (!wrap) return;
    wrap.classList.remove('abierto');
    const btn = wrap.querySelector('.mx-combo-btn');
    if (btn) { btn.setAttribute('aria-expanded', 'false'); if (devolverFoco) btn.focus(); }
    if (_mxComboAbierto === wrap) _mxComboAbierto = null;
}
function mxComboRefrescar(sel) {
    const wrap = sel.closest('.mx-combo');
    if (!wrap) return;
    const btn = wrap.querySelector('.mx-combo-btn');
    const o = sel.selectedOptions && sel.selectedOptions[0];
    btn.querySelector('.mx-combo-txt').textContent = o ? o.textContent.trim() : '';
    btn.classList.toggle('es-vacio', !sel.value || sel.value === 'custom');
    btn.classList.toggle('mx-activo', !!sel.value && sel.value !== 'custom' && sel.id !== 'rrhh-periodo-select');
    if (wrap.classList.contains('abierto')) mxComboLista(sel);
}
function mxComboLista(sel) {
    const wrap = sel.closest('.mx-combo'), pop = wrap.querySelector('.mx-combo-pop');
    const esc = x => String(x).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const opciones = [...sel.querySelectorAll('option')];
    const conBuscador = opciones.length > 7;
    let k = 0; // posición para la cascada de entrada (solo las primeras filas se animan)
    const op = o => `<div class="mx-combo-op${o.value === sel.value ? ' es-sel' : ''}${o.value === '' ? ' es-todos' : ''}" style="--i:${Math.min(k++, 11)}" role="option" aria-selected="${o.value === sel.value}" data-v="${esc(o.value)}" data-t="${esc(mxNorm(o.textContent))}">${esc(o.textContent.trim())}<i class="bi bi-check2" aria-hidden="true"></i></div>`;
    const cuerpo = [...sel.children].map(n => n.tagName === 'OPTGROUP'
        ? `<div class="mx-combo-gr" role="group" aria-label="${esc(n.label)}"><div class="mx-combo-gr-t">${esc(n.label)}</div>${[...n.children].map(op).join('')}</div>`
        : op(n)).join('');
    const buscar = pop.querySelector('.mx-combo-q') ? pop.querySelector('.mx-combo-q').value : '';
    pop.innerHTML = (conBuscador ? '<label class="mx-combo-bus"><i class="bi bi-search" aria-hidden="true"></i><input type="text" class="mx-combo-q" placeholder="Buscar…" autocomplete="off" aria-label="Buscar en la lista"></label>' : '')
        + `<div class="mx-combo-lista"><div class="mx-combo-hl" aria-hidden="true"></div>${cuerpo}</div><div class="mx-combo-nada">Sin resultados</div>`;
    const q = pop.querySelector('.mx-combo-q');
    const filtrar = () => {
        const t = mxNorm(q ? q.value : '');
        let n = 0;
        pop.querySelectorAll('.mx-combo-op').forEach(e => { const ok = !t || e.dataset.t.includes(t); e.hidden = !ok; if (ok) n++; });
        pop.querySelectorAll('.mx-combo-gr').forEach(g => { g.hidden = !g.querySelector('.mx-combo-op:not([hidden])'); });
        pop.classList.toggle('sin-resultados', n === 0);
        mxComboMarcar(pop, pop.querySelector('.mx-combo-op:not([hidden])'));
    };
    if (q) { q.value = buscar; q.addEventListener('input', filtrar); }
    pop.querySelectorAll('.mx-combo-op').forEach(e => {
        e.addEventListener('click', () => mxComboElegir(sel, e.dataset.v));
        e.addEventListener('mousemove', () => mxComboMarcar(pop, e, false));
    });
    if (q && buscar) filtrar(); else mxComboMarcar(pop, pop.querySelector('.mx-combo-op.es-sel') || pop.querySelector('.mx-combo-op:not([hidden])'));
}
function mxComboMarcar(pop, el, desplazar = true) {
    pop.querySelectorAll('.mx-combo-op.is-activo').forEach(e => e.classList.remove('is-activo'));
    const hl = pop.querySelector('.mx-combo-hl');
    if (!el) { if (hl) hl.classList.remove('visible'); return; }
    el.classList.add('is-activo');
    if (desplazar) el.scrollIntoView({ block: 'nearest' });
    // Un resalte que se desliza de una opción a otra (en vez de saltar): la primera vez se coloca sin animar
    if (hl) {
        const primera = !hl.classList.contains('visible');
        if (primera) hl.classList.add('sin-trans');
        hl.style.transform = `translateY(${el.offsetTop}px)`;
        hl.style.height = el.offsetHeight + 'px';
        hl.classList.add('visible');
        if (primera) requestAnimationFrame(() => requestAnimationFrame(() => hl.classList.remove('sin-trans')));
    }
}
function mxComboElegir(sel, valor) {
    const wrap = sel.closest('.mx-combo');
    const cambio = sel.value !== valor;
    sel.value = valor;
    mxComboCerrar(wrap, true);
    if (cambio) sel.dispatchEvent(new Event('change', { bubbles: true }));
}
function mxComboAbrir(sel) {
    const wrap = sel.closest('.mx-combo'), btn = wrap.querySelector('.mx-combo-btn'), pop = wrap.querySelector('.mx-combo-pop');
    if (_mxComboAbierto && _mxComboAbierto !== wrap) mxComboCerrar(_mxComboAbierto);
    _mxComboAbierto = wrap;
    mxComboLista(sel);
    // Si no cabe hacia la derecha, la lista se abre alineada al borde derecho del botón
    wrap.classList.toggle('mx-combo-der', btn.getBoundingClientRect().left + 280 > window.innerWidth - 12);
    wrap.classList.add('abierto');
    btn.setAttribute('aria-expanded', 'true');
    const q = pop.querySelector('.mx-combo-q');
    (q || pop).focus({ preventScroll: true });
}
window.mxMejorarSelects = function () {
    Object.keys(MX_COMBO_IDS).forEach(id => {
        const sel = document.getElementById(id);
        if (!sel || sel.dataset.mxCombo) return;
        sel.dataset.mxCombo = '1';
        const wrap = document.createElement('div');
        wrap.className = 'mx-combo';
        sel.parentNode.insertBefore(wrap, sel);
        wrap.appendChild(sel);
        sel.classList.add('mx-select-oculto');
        sel.tabIndex = -1;
        sel.setAttribute('aria-hidden', 'true');
        const btn = document.createElement('button');
        btn.type = 'button'; btn.id = id + '-combo'; btn.className = 'mx-combo-btn';
        btn.setAttribute('aria-haspopup', 'listbox'); btn.setAttribute('aria-expanded', 'false');
        btn.innerHTML = `<i class="bi ${MX_COMBO_IDS[id]} mx-combo-ic" aria-hidden="true"></i><span class="mx-combo-txt"></span><i class="bi bi-chevron-down mx-combo-chev" aria-hidden="true"></i>`;
        const pop = document.createElement('div');
        pop.className = 'mx-combo-pop'; pop.tabIndex = -1; pop.setAttribute('role', 'listbox');
        wrap.append(btn, pop);
        const lab = document.querySelector(`label[for="${id}"]`);
        if (lab) lab.setAttribute('for', btn.id);
        const refrescar = () => mxComboRefrescar(sel);
        new MutationObserver(refrescar).observe(sel, { childList: true, subtree: true, characterData: true });
        ['value', 'selectedIndex'].forEach(p => {
            const d = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, p);
            Object.defineProperty(sel, p, { configurable: true, get() { return d.get.call(this); }, set(v) { d.set.call(this, v); refrescar(); } });
        });
        btn.addEventListener('click', () => (wrap.classList.contains('abierto') ? mxComboCerrar(wrap, true) : mxComboAbrir(sel)));
        btn.addEventListener('keydown', e => { if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); mxComboAbrir(sel); } });
        pop.addEventListener('keydown', e => {
            const visibles = [...pop.querySelectorAll('.mx-combo-op:not([hidden])')];
            const i = visibles.findIndex(x => x.classList.contains('is-activo'));
            if (e.key === 'ArrowDown') { e.preventDefault(); mxComboMarcar(pop, visibles[Math.min(i + 1, visibles.length - 1)]); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); mxComboMarcar(pop, visibles[Math.max(i - 1, 0)]); }
            else if (e.key === 'Home') { e.preventDefault(); mxComboMarcar(pop, visibles[0]); }
            else if (e.key === 'End') { e.preventDefault(); mxComboMarcar(pop, visibles[visibles.length - 1]); }
            else if (e.key === 'Enter') { e.preventDefault(); if (visibles[i]) mxComboElegir(sel, visibles[i].dataset.v); }
            else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); mxComboCerrar(wrap, true); }
            else if (e.key === 'Tab') mxComboCerrar(wrap);
        });
        refrescar();
    });
};
document.addEventListener('click', e => { if (_mxComboAbierto && !_mxComboAbierto.contains(e.target)) mxComboCerrar(_mxComboAbierto); });

// Marca los selectores con un valor elegido y muestra «Restablecer» solo cuando hay algo guardado.
window.mxPintarChips = function () {
    const s = stateMarcacionesApp;
    ['marcacion-area', 'marcacion-turno', 'marcacion-empleado'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle('mx-activo', !!el.value);
    });
    const b = document.getElementById('mx-reset-btn');
    if (b) b.classList.toggle('es-visible', !!(s.area || s.turnoId || s.empleadoId || s.fechasElegidas));
};

// Esqueleto de carga (en vez del círculo que gira) y entrada suave de la grilla. Solo cuando la persona pidió la carga:
// el refresco automático en silencio no anima. Todo con opacidad/transform, que no recalcula el diseño de la tabla.
const MX_SKELETON_HTML = '<div class="mx-skel" role="status" aria-live="polite"><span class="visually-hidden">Cargando asistencia…</span>'
    + '<div class="mx-skel-fila mx-skel-cab"><i></i><i></i><i></i><i></i><i></i><i></i></div>'
    + Array.from({ length: 9 }, (_, n) => `<div class="mx-skel-fila" style="--d:${n * 70}ms"><i></i><i></i><i></i><i></i><i></i><i></i></div>`).join('')
    + '</div>';
window._mxAnimarProximo = false;
window.mxTrasPintar = function (container) {
    if (!container || !window._mxAnimarProximo) return;
    window._mxAnimarProximo = false;
    if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    container.classList.remove('mx-entra');
    void container.offsetWidth;
    container.classList.add('mx-entra');
    container.addEventListener('animationend', e => { if (e.target === container) container.classList.remove('mx-entra'); }, { once: false });
    container.querySelectorAll('tbody tr').forEach((tr, i) => {
        if (i >= 16) return;
        tr.style.animation = `mxFilaIn .45s var(--mx-ease) ${i * 24}ms both`;
        tr.addEventListener('animationend', () => { tr.style.animation = ''; }, { once: true });
    });
};

// Cambiar de vista (diseño HD): la pastilla de la vista elegida se desliza desde la anterior y los días cambian con un
// fundido corto. Con «menos movimiento» la pastilla no viaja y solo queda el fundido.
window.mxVistaCambiada = function (container, desde) {
    if (!container) return;
    const quieto = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    const nuevo = container.querySelector('.va-toolbar-premium .segmented-btn.active');
    const barra = nuevo && nuevo.parentElement;
    if (!quieto && desde && desde.width > 0 && nuevo && barra) {
        const r1 = nuevo.getBoundingClientRect(), rb = barra.getBoundingClientRect();
        const dx = desde.left - r1.left;
        if (Math.abs(dx) > 1 && r1.width > 0) {
            const p = document.createElement('span');
            p.className = 'mx-seg-pasa';
            p.setAttribute('aria-hidden', 'true');
            p.style.cssText = 'left:' + (r1.left - rb.left + barra.scrollLeft) + 'px;top:' + (r1.top - rb.top + barra.scrollTop) + 'px;width:'
                + r1.width + 'px;height:' + r1.height + 'px;transform:translateX(' + dx + 'px) scaleX(' + (desde.width / r1.width) + ')';
            barra.appendChild(p);
            // Sin transición propia mientras la pastilla viaja: al llegar, el botón toma su color de una vez (sin destello)
            nuevo.style.transition = 'none';
            nuevo.classList.add('mx-seg-llega');
            let listo = false;
            const fin = () => {
                if (listo) return;
                listo = true;
                nuevo.classList.remove('mx-seg-llega');
                void nuevo.offsetWidth;
                p.remove();
                requestAnimationFrame(() => { nuevo.style.transition = ''; });
            };
            requestAnimationFrame(() => requestAnimationFrame(() => { p.style.transform = 'none'; }));
            p.addEventListener('transitionend', fin, { once: true });
            setTimeout(fin, 600);
        }
    }
    container.classList.remove('mx-vista-cambia');
    void container.offsetWidth;
    container.classList.add('mx-vista-cambia');
    setTimeout(() => container.classList.remove('mx-vista-cambia'), 400);
};

// ── Generador robusto de rango de fechas (inmune a saltos DST / Timezone offset) ──
window.getDatesInRange = function(fechaInicio, fechaFin) {
    if (!fechaInicio || !fechaFin) return [];
    const dates = [];
    const [y1, m1, d1] = fechaInicio.split('-').map(Number);
    const [y2, m2, d2] = fechaFin.split('-').map(Number);
    let curr = new Date(Date.UTC(y1, m1 - 1, d1, 12, 0, 0));
    const end = new Date(Date.UTC(y2, m2 - 1, d2, 12, 0, 0));
    while (curr <= end) {
        dates.push(curr.toISOString().split('T')[0]);
        curr.setUTCDate(curr.getUTCDate() + 1);
    }
    return dates;
};

window.timeToMinutes = function(tStr) {
    if (!tStr) return 0;
    const parts = String(tStr).trim().split(':').map(Number);
    return (parts[0] || 0) * 60 + (parts[1] || 0);
};

window.circularTimeDiff = function(t1, t2) {
    let diff = (window.timeToMinutes(t2) - window.timeToMinutes(t1)) % 1440;
    if (diff > 720) diff -= 1440;
    if (diff < -720) diff += 1440;
    return diff;
};

// Referencia local
// Referencia local (segura para re-declaración)
// Referencia local (segura para re-declaración)
// var stateMarcacionesApp = window.stateMarcacionesApp;

// ============================================================
// ESTADO CENTRALIZADO DEL SISTEMA PERDONAZO
// ============================================================
window._perdonazoState = window._perdonazoState || {
    activo: false,              // Switch Perdonazos ON/OFF
    seleccionados: new Set(),   // empleado_ids seleccionados via checkbox
};

// ==========================================
// INICIALIZACIÓN
// ==========================================
async function initMarcacionesUI() {
    console.log("Inicializando UI de Marcaciones (BioAlba Integration)...");

    const container = document.getElementById('page-marcaciones');
    if (!container) return; // No estamos en la página correcta o no existe el contenedor
    // Cada vez que se entra a Asistencia, los horarios de la grilla parten plegados
    window._mxDesplegados = new Set();
    try { localStorage.removeItem('mx-horarios-plegados'); } catch (e) { /* lo guardaba la primera versión de los bloques */ }
    if (!stateMarcacionesApp._filtrosRestaurados) { stateMarcacionesApp._filtrosRestaurados = true; window.mxRestaurarFiltros(); }

    // Estimar fechas locales temporales para pintar el Toolbar de inmediato si no están cargadas
    let datesAlreadyLoaded = false;
    if (!stateMarcacionesApp.fechaInicioRRHH || !stateMarcacionesApp.fechaFinRRHH) {
        const now = new Date();
        const inicio = new Date(now.getFullYear(), now.getMonth() - 1, 26);
        const fin = new Date(now.getFullYear(), now.getMonth(), 25);
        stateMarcacionesApp.fechaInicioRRHH = inicio.toISOString().split('T')[0];
        stateMarcacionesApp.fechaFinRRHH = fin.toISOString().split('T')[0];
    } else {
        datesAlreadyLoaded = true;
    }

    // 1. Renderizar Estructura Base (Toolbar + Contenedor de Grilla) INMEDIATAMENTE
    renderMarcacionesToolbar(container);
    cargarPeriodosEnToolbar();

    // Colocar un loading spinner en el contenedor de vistas de inmediato
    const viewContainer = document.getElementById('marcaciones-view-container');
    if (viewContainer) {
        viewContainer.innerHTML = `
            <div class="d-flex flex-column align-items-center justify-content-center py-5 text-center" style="min-height: 250px;">
                <div class="spinner-border text-primary mb-3" role="status" style="width: 3rem; height: 3rem;">
                    <span class="visually-hidden">Cargando...</span>
                </div>
                <h6 class="text-muted fw-bold mb-1">Cargando módulo de asistencia...</h6>
                <p class="text-muted small">Por favor, espera mientras se inicializan los filtros y períodos de control.</p>
            </div>
        `;
    }

    // 2. Iniciar cargas asíncronas en paralelo (Promise.all)
    const loadActivePeriodPromise = async () => {
        if (datesAlreadyLoaded) return;
        try {
            const currentAreaName = stateMarcacionesApp.area || 'Todas';
            const activeResp = await fetch(`/api/configuracion/periodos/activo/${encodeURIComponent(currentAreaName)}/`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
            });
            if (activeResp.ok) {
                const activePeriod = await activeResp.json();
                if (activePeriod && activePeriod.fecha_inicio && activePeriod.fecha_fin) {
                    if (stateMarcacionesApp.usuarioModificoFechas || stateMarcacionesApp.fechasElegidas) {
                        console.log("loadActivePeriodPromise: el usuario ya modificó las fechas manualmente. No sobreescribiendo.");
                        return;
                    }
                    stateMarcacionesApp.fechaInicioRRHH = activePeriod.fecha_inicio;
                    stateMarcacionesApp.fechaFinRRHH = activePeriod.fecha_fin;
                    console.log("Periodo activo RRHH cargado (async):", activePeriod);
                    
                    // Actualizar inputs en el DOM si el usuario no los ha modificado
                    const inputInicio = document.getElementById('rrhh-fecha-inicio');
                    const inputFin = document.getElementById('rrhh-fecha-fin');
                    if (inputInicio) inputInicio.value = activePeriod.fecha_inicio;
                    if (inputFin) inputFin.value = activePeriod.fecha_fin;
                    if (window.syncPeriodoDropdownConFechas) window.syncPeriodoDropdownConFechas();
                    return;
                }
            }
        } catch (e) {
            console.error("Error cargando periodo activo desde configuracion:", e);
        }

        // Fallback al último cierre si el período activo no está configurado
        try {
            const resp = await fetch('/api/asistencia/periodo-rrhh/ultimo-cierre/');
            if (resp.ok) {
                const ultimo = await resp.json();
                if (ultimo && ultimo.fecha_fin) {
                    if (stateMarcacionesApp.usuarioModificoFechas || stateMarcacionesApp.fechasElegidas) {
                        console.log("Fallback ultimo-cierre: el usuario ya modificó las fechas manualmente. No sobreescribiendo.");
                        return;
                    }
                    const lastFin = new Date(ultimo.fecha_fin);
                    lastFin.setDate(lastFin.getDate() + 1);
                    stateMarcacionesApp.fechaInicioRRHH = lastFin.toISOString().split('T')[0];
                    
                    const nextFin = new Date(lastFin);
                    nextFin.setMonth(nextFin.getMonth() + 1);
                    nextFin.setDate(nextFin.getDate() - 1);
                    stateMarcacionesApp.fechaFinRRHH = nextFin.toISOString().split('T')[0];

                    const inputInicio = document.getElementById('rrhh-fecha-inicio');
                    const inputFin = document.getElementById('rrhh-fecha-fin');
                    if (inputInicio) inputInicio.value = stateMarcacionesApp.fechaInicioRRHH;
                    if (inputFin) inputFin.value = stateMarcacionesApp.fechaFinRRHH;
                    if (window.syncPeriodoDropdownConFechas) window.syncPeriodoDropdownConFechas();
                }
            }
        } catch (e) {
            console.error("Error sugiriendo periodo por defecto:", e);
        }
    };

    const loadMetadataPromise = async () => {
        try {
            // Fix #A: usar caché — no ir a la BD si ya tenemos los datos
            const metadata = await getMetadata();
            const areaSelect = document.getElementById('marcacion-area');
            const areasList = (metadata.areas_con_horario && metadata.areas_con_horario.length > 0)
                ? metadata.areas_con_horario
                : (metadata.areas || []);
            if (areaSelect && areasList) {
                const currentVal = stateMarcacionesApp.area || areaSelect.value;
                areaSelect.innerHTML = '<option value="">Todas las Áreas</option>' +
                    areasList.map(a => `<option value="${a}">${a}</option>`).join('');
                if (currentVal && areasList.includes(currentVal)) {
                    areaSelect.value = currentVal;
                }
            }
        } catch (e) {
            console.error('Error cargando metadatos de filtros:', e);
        }
    };

    // Await paralelo
    await Promise.all([loadActivePeriodPromise(), loadMetadataPromise()]);

    // 3. Cargar Filtros Dependientes (Turnos y Empleados)
    await loadMarcacionesDependentFilters();

    // 4. Iniciar auto-refresh silenciosamente al inicializar la UI
    if (stateMarcacionesApp.autoRefreshEnabled) {
        toggleAutoRefresh(true, true);
    }

    // 5. Cargar la matriz de datos automáticamente
    await window.loadMarcacionesData();
}

function renderMarcacionesToolbar(container) {
    container.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-3 mx-page-head">
            <h2 class="mb-0 d-flex align-items-center gap-2 mx-page-title">
                <i class="bi bi-calendar-check" style="color:#3f6fd6"></i>
                <span style="font-weight:700;color:#1e293b">Control de Asistencia</span>
            </h2>
            <div class="d-flex gap-2 align-items-center mx-page-actions">
                <div class="btn-group shadow-sm mx-act-export" style="border-radius:8px;overflow:hidden">
                    ${(typeof AuthService !== 'undefined' && AuthService.hasPermission('reportes.exportar')) ? `
                    <button class="btn btn-sm btn-outline-secondary bg-white" onclick="downloadExcelReport()" title="Exportar a Excel">
                        <i class="bi bi-file-earmark-excel text-success"></i> Excel
                    </button>
                    ` : ''}
                    ${(typeof AuthService !== 'undefined' && AuthService.hasPermission('marcaciones.cierre_periodo')) ? `
                    <button class="btn btn-sm btn-outline-secondary bg-white text-nowrap" onclick="window.descargarPreinformeGrilla(this)" title="Informe de cierre del período y área elegidos, sin cerrar: un PDF por tipo de horario">
                        <i class="bi bi-file-earmark-pdf text-danger"></i> Preinforme
                    </button>
                    ` : ''}
                    <button class="btn btn-sm btn-outline-secondary bg-white" onclick="window.print()" title="Imprimir Reporte">
                        <i class="bi bi-printer"></i>
                    </button>
                </div>

                <div class="btn-group shadow-sm mx-act-sync">
                    <button class="btn btn-sm btn-outline-primary" onclick="syncMarcacionesBioAlba()">
                        <i class="bi bi-cloud-download"></i> Sincronizar BioAlba
                    </button>
                    <button class="btn btn-sm btn-outline-primary dropdown-toggle dropdown-toggle-split" 
                            data-bs-toggle="dropdown" aria-expanded="false">
                        <span class="visually-hidden">Opciones</span>
                    </button>
                    <ul class="dropdown-menu dropdown-menu-end shadow-lg border-0">
                            <li><a class="dropdown-item mx-op" href="#" onclick="syncMarcacionesBioAlba(); return false;"><b>Sincronización rápida</b><small>Todas las áreas del mes actual</small></a></li>
                            <li><a class="dropdown-item mx-op" href="#" onclick="openSyncMarcacionesModal(); return false;"><b>Filtrar por áreas…</b><small>Elegir áreas específicas</small></a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item mx-op" href="#" onclick="openHistorialCierresModal(); return false;"><b>Historial de cierres</b></a></li>
                        </ul>
                </div>

                <div class="d-flex align-items-center bg-white border rounded-3 px-3 py-1 shadow-sm mx-act-switch" style="height:38px;border-color:#e2e8f0 !important">
                    <div class="form-check form-switch mb-0">
                        <input class="form-check-input" type="checkbox" role="switch" id="auto-refresh-switch" 
                               ${stateMarcacionesApp.autoRefreshEnabled ? 'checked' : ''} onchange="toggleAutoRefresh(this.checked)">
                        <label class="form-check-label small fw-bold text-muted ms-1" for="auto-refresh-switch">
                            <i class="bi bi-broadcast" style="font-size: 0.75rem;${stateMarcacionesApp.autoRefreshEnabled ? 'color:#10b981;' : ''}"></i>
                            Auto
                        </label>
                    </div>
                </div>

                ${AuthService.hasPermission("marcaciones.editar") ? `
                <div class="d-flex align-items-center border rounded-3 px-3 py-1 shadow-sm mx-act-switch" 
                     id="perdonazo-switch-wrapper"
                     style="height:38px; background: ${_perdonazoState.activo ? '#f0fdf4' : '#fff'}; border-color:${_perdonazoState.activo ? '#86efac' : '#e2e8f0'} !important; transition: background 0.3s;">
                    <div class="form-check form-switch mb-0">
                        <input class="form-check-input" type="checkbox" role="switch" id="perdonazo-switch"
                               ${_perdonazoState.activo ? 'checked' : ''}
                               onchange="toggleModoPerdonazo(this.checked)"
                               style="border-color:${_perdonazoState.activo ? '#10b981' : '#e2e8f0'};">
                        <label class="form-check-label small fw-bold ms-1" for="perdonazo-switch"
                               style="color:${_perdonazoState.activo ? '#047857' : '#64748b'};">
                            <i class="bi bi-gift-fill me-1" style="color:${_perdonazoState.activo ? '#10b981' : '#64748b'}"></i>Perdonazos
                        </label>
                    </div>
                </div>
                ` : ''}

                <!-- «Días Compensatorios» se quitó de aquí (27-10-2026): compensar una inasistencia se hace desde el día
                     faltado, en Acciones de asistencia → Compensar inasistencia -->

                <!-- Días que una regla de marcaciones dejó en revisión: siempre a la vista (pedido del dueño, 06-11-2026);
                     sin días dice «No hay nada por revisar» (actualizarPorRevisar lo pinta) -->
                <button class="btn btn-sm btn-outline-secondary shadow-sm ms-2 mx-act-wide" id="btn-por-revisar"
                        onclick="abrirPanelPorRevisar()" title="Días que una regla de marcaciones dejó en revisión"
                        style="height:38px; display:flex; align-items:center; gap:5px;">
                    <i class="bi bi-hourglass-split"></i> <span class="fw-bold">Por revisar…</span>
                </button>

            </div>
        </div>

        <!-- Toolbar de Filtros -->
        <div class="marcaciones-filter-bar">
            <div class="row g-2 align-items-end">
                <!-- Filtro Período (NUEVO) -->
                <div class="col-12 col-md-6 col-lg-4 col-xxl-2">
                    <label for="rrhh-periodo-select" class="form-label small fw-semibold text-muted mb-1">Período de Cierre</label>
                    <select class="form-select form-select-sm" id="rrhh-periodo-select" onchange="window.cambiarPeriodoFiltro(this.value)" style="border-color:#c5d3f1">
                        <option value="custom">-- Rango Personalizado --</option>
                    </select>
                </div>

                <!-- Filtro Tiempo (Dinámico) -->
                <div class="col-12 col-md-6 col-lg-5 col-xxl-3">
                    <div id="filter-time-rrhh">
                        <div class="d-flex gap-2">
                            <div class="flex-grow-1">
                                <label for="rrhh-fecha-inicio" class="form-label small fw-semibold text-muted mb-1">Desde</label>
                                <input type="date" class="form-control form-control-sm" id="rrhh-fecha-inicio" 
                                       value="${stateMarcacionesApp.fechaInicioRRHH}" onchange="updateMarcacionesState('fechaInicioRRHH', this.value)" style="border-color:#c5d3f1">
                            </div>
                            <div class="flex-grow-1">
                                <label for="rrhh-fecha-fin" class="form-label small fw-semibold text-muted mb-1">Hasta</label>
                                <input type="date" class="form-control form-control-sm" id="rrhh-fecha-fin" 
                                       value="${stateMarcacionesApp.fechaFinRRHH}" onchange="updateMarcacionesState('fechaFinRRHH', this.value)" style="border-color:#c5d3f1">
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Área -->
                <div class="col-6 col-md-4 col-lg-4 col-xxl-2 order-lg-2 order-xxl-0">
                    <label for="marcacion-area" class="form-label small fw-semibold text-muted mb-1">Área</label>
                    <select class="form-select form-select-sm" id="marcacion-area" onchange="updateMarcacionesState('area', this.value)">
                        <option value="">Todas las Áreas</option>
                    </select>
                </div>

                <!-- Horario -->
                <div class="col-6 col-md-4 col-lg-4 col-xxl-2 order-lg-2 order-xxl-0">
                    <label for="marcacion-turno" class="form-label small fw-semibold text-muted mb-1">Horario</label>
                    <select class="form-select form-select-sm" id="marcacion-turno" onchange="updateMarcacionesState('turnoId', this.value)">
                        <option value="">Todos los Horarios</option>
                    </select>
                </div>

                <!-- Empleado -->
                <div class="col-12 col-md-4 col-lg-4 col-xxl-2 order-lg-2 order-xxl-0">
                    <label for="marcacion-empleado" class="form-label small fw-semibold text-muted mb-1">Empleado</label>
                    <select class="form-select form-select-sm" id="marcacion-empleado" onchange="updateMarcacionesState('empleadoId', this.value)">
                        <option value="">Todo el equipo</option>
                    </select>
                </div>

                <!-- Botón Ver -->
                <div class="col-12 col-lg-3 col-xxl-1 order-lg-1 order-xxl-0 d-flex gap-2 justify-content-lg-end mx-ver-col">
                    <button type="button" id="mx-reset-btn" class="mx-reset-btn" onclick="mxRestablecerFiltros()" title="Restablecer filtros (borra lo guardado y vuelve al período activo)" aria-label="Restablecer filtros"><i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i></button>
                    <button class="btn btn-sm w-100 fw-bold shadow-sm" onclick="loadMarcacionesData()" style="background:linear-gradient(135deg,#3f6fd6,#1b2f8f);color:white;border:none;border-radius:6px;height: 31px;margin-bottom: 2px;" title="Ver">
                        <i class="bi bi-search"></i><span class="d-md-none ms-2">Ver asistencia</span>
                    </button>
                </div>
            </div>
        </div>

        <!-- Contenedor Principal de Vistas -->
        <div id="marcaciones-view-container" class="position-relative">
            <div class="text-center py-5 text-muted opacity-50">
                <i class="bi bi-hand-index-thumb mb-2" style="font-size: 2rem;"></i>
                <p>Selecciona filtros para visualizar la asistencia.</p>
            </div>
        </div>
    `;
    window.mxMejorarSelects();
}

window.syncPeriodoDropdownConFechas = function() {
    const select = document.getElementById('rrhh-periodo-select');
    if (!select) return;
    
    const valToFind = `${stateMarcacionesApp.fechaInicioRRHH}|${stateMarcacionesApp.fechaFinRRHH}`;
    let found = false;
    for (let i = 0; i < select.options.length; i++) {
        if (select.options[i].value === valToFind) {
            select.selectedIndex = i;
            found = true;
            break;
        }
    }
    if (!found) {
        select.value = 'custom';
    }
    
    const inputInicio = document.getElementById('rrhh-fecha-inicio');
    const inputFin = document.getElementById('rrhh-fecha-fin');
    if (inputInicio && inputFin) {
        if (found) {
            inputInicio.setAttribute('readonly', 'true');
            inputFin.setAttribute('readonly', 'true');
        } else {
            inputInicio.removeAttribute('readonly');
            inputFin.removeAttribute('readonly');
        }
    }
};

window.cambiarPeriodoFiltro = function(val) {
    stateMarcacionesApp.fechasElegidas = true;
    const inputInicio = document.getElementById('rrhh-fecha-inicio');
    const inputFin = document.getElementById('rrhh-fecha-fin');
    
    if (val === 'custom') {
        stateMarcacionesApp.usuarioModificoFechas = true;
        if (inputInicio) inputInicio.removeAttribute('readonly');
        if (inputFin) inputFin.removeAttribute('readonly');
    } else {
        const [fIni, fFin] = val.split('|');
        stateMarcacionesApp.fechaInicioRRHH = fIni;
        stateMarcacionesApp.fechaFinRRHH = fFin;
        stateMarcacionesApp.usuarioModificoFechas = false;
        
        if (inputInicio) {
            inputInicio.value = fIni;
            inputInicio.setAttribute('readonly', 'true');
        }
        if (inputFin) {
            inputFin.value = fFin;
            inputFin.setAttribute('readonly', 'true');
        }
        
        loadMarcacionesData();
    }
    mxGuardarFiltros();
    mxPintarChips();
};

// El cierre es por área: con un área elegida, un período está «Cerrado» si esa área ya lo cerró (aunque otras áreas no), y «Vigente»
// si sigue abierto para ella. Sin área (Todas) vale el estado de toda la empresa (dueño, 10-11-2026).
window.mxPeriodoCerradoParaArea = function (p, area) {
    if (!p) return false;
    if (p.estado === 'cerrado') return true;
    const a = String(area || '').trim().toUpperCase();
    if (!a || a === 'TODAS' || a === 'TODOS') return false;
    return (p.areas_cerradas || []).some(x => String(x || '').trim().toUpperCase() === a);
};
window.mxEtiquetaPeriodo = function (p, area) {
    let label = `${p.mes_cierre}`;
    if (window.mxPeriodoCerradoParaArea(p, area)) label += ' (Cerrado)';
    else if (p.activo === 1 || p.activo === true) label += ' (Vigente)';
    return label;
};
// Al cambiar de área se reescriben las etiquetas de la lista de períodos, sin volver a pedirla al servidor
window.mxRefrescarEtiquetasPeriodo = function () {
    const select = document.getElementById('rrhh-periodo-select');
    const periodos = window._mxPeriodos;
    if (!select || !periodos) return;
    const area = stateMarcacionesApp.area;
    [...select.options].forEach(o => {
        const p = periodos.find(x => `${x.fecha_inicio}|${x.fecha_fin}` === o.value);
        if (p) o.textContent = window.mxEtiquetaPeriodo(p, area);
    });
    if (typeof mxComboRefrescar === 'function') mxComboRefrescar(select);
};

async function cargarPeriodosEnToolbar() {
    try {
        const resp = await fetch('/api/configuracion/periodos/', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
        });
        if (resp.ok) {
            const periodos = await resp.json();
            window._mxPeriodos = periodos;
            const select = document.getElementById('rrhh-periodo-select');
            if (select) {
                select.innerHTML = '<option value="custom">-- Rango Personalizado --</option>';
                
                periodos.forEach(p => {
                    const option = document.createElement('option');
                    option.value = `${p.fecha_inicio}|${p.fecha_fin}`;
                    
                    option.textContent = window.mxEtiquetaPeriodo(p, stateMarcacionesApp.area);
                    select.appendChild(option);
                });
                
                window.syncPeriodoDropdownConFechas();
                window.mxRefrescarEtiquetasPeriodo();
            }
        }
    } catch (e) {
        console.error("Error al cargar periodos en toolbar:", e);
    }
}

// ==========================================
// LOGICA DE ESTADO Y CARGA
// ==========================================
async function loadMarcacionesFilters() {
    try {
        // Fix #A: usar caché — no repetir la llamada HTTP si ya tenemos los datos
        const metadata = await getMetadata();

        const areaSelect = document.getElementById('marcacion-area');
        const areasList = (metadata.areas_con_horario && metadata.areas_con_horario.length > 0)
            ? metadata.areas_con_horario
            : (metadata.areas || []);
        if (areaSelect && areasList) {
            // Preservar valor si existe
            const currentVal = areaSelect.value;
            areaSelect.innerHTML = '<option value="">Todas las Áreas</option>' +
                areasList.map(a => `<option value="${a}">${a}</option>`).join('');
            if (currentVal && areasList.includes(currentVal)) {
                areaSelect.value = currentVal;
            } else if (currentVal && !areasList.includes(currentVal)) {
                areaSelect.value = "";
                stateMarcacionesApp.area = "";
            }
        }

        // Cargar Dependientes (Empleados y Turnos) en una sola llamada
        await loadMarcacionesDependentFilters();

    } catch (e) {
        console.error("Error cargando filtros:", e);
        showToast("No se pudieron cargar los filtros. Recargue la página.", "error");
    }
}

async function loadMarcacionesDependentFilters(onlyEmployees = false) {
    console.time("⏱️ CargaFiltrosDependientes");
    let _mxReacotarEmpleados = false;
    try {
        // Cancelar peticiones anteriores
        if (stateMarcacionesApp.controllers.filters) {
            stateMarcacionesApp.controllers.filters.abort();
        }
        stateMarcacionesApp.controllers.filters = new AbortController();

        const empSelect = document.getElementById('marcacion-empleado');
        const turnoSelect = document.getElementById('marcacion-turno');

        if (!onlyEmployees && turnoSelect) turnoSelect.innerHTML = '<option value="">Cargando horarios...</option>';
        if (empSelect) empSelect.innerHTML = '<option value="">Cargando empleados...</option>';

        // Endpoint consolidado con soporte de cascada
        let url = `/api/asistencia/filters-data/?area=${encodeURIComponent(stateMarcacionesApp.area || '')}`;
        if (stateMarcacionesApp.fechaInicioRRHH && stateMarcacionesApp.fechaFinRRHH) {
            url += `&fecha_inicio=${encodeURIComponent(stateMarcacionesApp.fechaInicioRRHH)}&fecha_fin=${encodeURIComponent(stateMarcacionesApp.fechaFinRRHH)}`;
        }
        if (onlyEmployees && stateMarcacionesApp.turnoId) {
            url += `&turno_id=${encodeURIComponent(stateMarcacionesApp.turnoId)}`;
        }

        const resp = await fetch(url, { signal: stateMarcacionesApp.controllers.filters.signal });
        const data = await resp.json();
        const empleados = data.empleados || [];
        const turnos = data.turnos || [];
        const areas = data.areas || [];

        // Renderizar Áreas (solo áreas con horarios asignados)
        if (!onlyEmployees && areas.length > 0) {
            const areaSelect = document.getElementById('marcacion-area');
            if (areaSelect) {
                const currentVal = stateMarcacionesApp.area || areaSelect.value;
                areaSelect.innerHTML = '<option value="">Todas las Áreas</option>' +
                    areas.map(a => `<option value="${a}">${a}</option>`).join('');
                if (currentVal && areas.includes(currentVal)) {
                    areaSelect.value = currentVal;
                } else if (currentVal && !areas.includes(currentVal)) {
                    areaSelect.value = "";
                    stateMarcacionesApp.area = "";
                }
            }
        }

        // Renderizar Turnos (solo si no es carga parcial de empleados)
        if (!onlyEmployees && turnoSelect) {
            const currentTurnoVal = stateMarcacionesApp.turnoId || turnoSelect.value;
            // Agrupado por tipo cuando hay de ambos (misma regla que la grilla: tipo_programacion o 'TRANSPORTE')
            const _esTurnoBolsa = t => t.tipo_programacion === 'BOLSA_FLEXIBLE' || t.tipo_programacion === 'FLEXIBLE_BOLSA'
                                    || String(t.nombre || '').toUpperCase().includes('TRANSPORTE');
            const _optT = t => `<option value="${t.id}">${t.nombre}</option>`;
            const _tB = turnos.filter(_esTurnoBolsa), _tC = turnos.filter(t => !_esTurnoBolsa(t));
            turnoSelect.innerHTML = '<option value="">Todos los Horarios</option>' + ((_tB.length && _tC.length)
                ? `<optgroup label="Ciclo inteligente">${_tC.map(_optT).join('')}</optgroup><optgroup label="Bolsa flexible">${_tB.map(_optT).join('')}</optgroup>`
                : turnos.map(_optT).join(''));

            if (currentTurnoVal && turnos.find(t => t.id == currentTurnoVal)) {
                turnoSelect.value = currentTurnoVal;
            } else {
                stateMarcacionesApp.turnoId = "";
            }
        }

        // Renderizar Empleados
        if (empSelect) {
            if (empleados.length === 0) {
                empSelect.innerHTML = '<option value="">-- Sin empleados en esta área/horario --</option>';
            } else {
                empSelect.innerHTML = '<option value="">Todo el equipo</option>' +
                    empleados.map(e => `<option value="${e.id}">${e.nombre_completo.toUpperCase()}</option>`).join('');
            }

            if (stateMarcacionesApp.empleadoId) {
                if (empleados.some(e => String(e.id) === String(stateMarcacionesApp.empleadoId))) empSelect.value = stateMarcacionesApp.empleadoId;
                else stateMarcacionesApp.empleadoId = ''; // ya no está en esta área/horario/período
            }
            // Con un horario recordado, la lista de empleados se acota a ese horario (como al elegirlo a mano).
            _mxReacotarEmpleados = !onlyEmployees && !!stateMarcacionesApp.turnoId;
        }

    } catch (e) {
        if (e.name !== 'AbortError') {
            console.error("Error cargando datos de filtros:", e);
        }
    } finally {
        console.timeEnd("⏱️ CargaFiltrosDependientes");
    }
    if (_mxReacotarEmpleados) await loadMarcacionesDependentFilters(true);
    window.mxPintarChips();
}

let _dependentFiltersDebounceTimer = null;

function updateMarcacionesState(key, value) {
    if (key === 'fechaInicioRRHH' || key === 'fechaFinRRHH') {
        stateMarcacionesApp.usuarioModificoFechas = true;
        stateMarcacionesApp.fechasElegidas = true;
        stateMarcacionesApp[key] = value;
        if (window.syncPeriodoDropdownConFechas) {
            window.syncPeriodoDropdownConFechas();
        }
    } else if (key === 'month' || key === 'year') {
        stateMarcacionesApp[key] = parseInt(value, 10);
        stateMarcacionesApp.usuarioModificoFechas = false;
    } else {
        stateMarcacionesApp[key] = value;
        if (key === 'area' && window.mxRefrescarEtiquetasPeriodo) window.mxRefrescarEtiquetasPeriodo();
    }

    let shouldLoadFilters = false;
    let onlyEmployees = false;

    if (key === 'month' || key === 'year') {
        // Nivel 1 cambió: resetear niveles 2-4 y recargar turnos+empleados
        stateMarcacionesApp.area = "";
        stateMarcacionesApp.turnoId = "";
        stateMarcacionesApp.empleadoId = "";
        const areaSelect = document.getElementById('marcacion-area');
        if (areaSelect) areaSelect.value = "";
        shouldLoadFilters = true;
    } else if (key === 'fechaInicioRRHH' || key === 'fechaFinRRHH') {
        shouldLoadFilters = true;
    } else if (key === 'area') {
        // Nivel 2 cambió: resetear niveles 3-4 y recargar turnos+empleados
        stateMarcacionesApp.turnoId = "";
        stateMarcacionesApp.empleadoId = "";
        const turnoSelect = document.getElementById('marcacion-turno');
        const empSelect = document.getElementById('marcacion-empleado');
        if (turnoSelect) turnoSelect.value = "";
        if (empSelect) empSelect.value = "";
        shouldLoadFilters = true;

        // ⚡ CARGA AUTOMÁTICA DEL TRAMO ACTIVO/ABIERTO PARA EL ÁREA SELECCIONADA
        const areaName = value || 'Todas';
        fetch(`/api/configuracion/periodos/activo/${encodeURIComponent(areaName)}/`, {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
        })
        .then(r => {
            if (r.ok) return r.json();
            throw new Error();
        })
        .then(activePeriod => {
            if (activePeriod && activePeriod.fecha_inicio && activePeriod.fecha_fin) {
                if (stateMarcacionesApp.usuarioModificoFechas || stateMarcacionesApp.fechasElegidas) {
                    console.log("updateMarcacionesState: el usuario ya modificó las fechas manualmente. No sobreescribiendo.");
                    return;
                }
                stateMarcacionesApp.fechaInicioRRHH = activePeriod.fecha_inicio;
                stateMarcacionesApp.fechaFinRRHH = activePeriod.fecha_fin;
                console.log(`Periodo activo para ${areaName} cargado:`, activePeriod);
                
                const inputInicio = document.getElementById('rrhh-fecha-inicio');
                const inputFin = document.getElementById('rrhh-fecha-fin');
                if (inputInicio) inputInicio.value = activePeriod.fecha_inicio;
                if (inputFin) inputFin.value = activePeriod.fecha_fin;
                if (window.syncPeriodoDropdownConFechas) window.syncPeriodoDropdownConFechas();
            }
        })
        .catch(e => {
            console.error("Error actualizando tramo activo por área:", e);
        });
    } else if (key === 'turnoId') {
        // Nivel 3 cambió: resetear nivel 4 y recargar solo empleados (cascade)
        stateMarcacionesApp.empleadoId = "";
        const empSelect = document.getElementById('marcacion-empleado');
        if (empSelect) empSelect.value = "";
        shouldLoadFilters = true;
        onlyEmployees = true;
    }

    mxGuardarFiltros();
    mxPintarChips();
    // Los filtros se aplican solos al cambiarlos (sin esperar el botón); con fechas incompletas o invertidas no se consulta.
    const fechasOk = !!(stateMarcacionesApp.fechaInicioRRHH && stateMarcacionesApp.fechaFinRRHH && stateMarcacionesApp.fechaInicioRRHH <= stateMarcacionesApp.fechaFinRRHH);
    if (shouldLoadFilters) {
        if (_dependentFiltersDebounceTimer) {
            clearTimeout(_dependentFiltersDebounceTimer);
        }
        _dependentFiltersDebounceTimer = setTimeout(async () => {
            await loadMarcacionesDependentFilters(onlyEmployees);
            mxGuardarFiltros();
            if (fechasOk) window.loadMarcacionesData();
        }, 400);
    } else if (key === 'empleadoId' && fechasOk) {
        window.loadMarcacionesData();
    }
}


// ── DEBOUNCE GUARD: evitar múltiples cargas simultáneas ──────────────────
let _loadMarcacionesInProgress = false;
let _loadMarcacionesDebounceTimer = null;
let _lastLoadMarcacionesCall = 0;
let _loadMarcacionesPendiente = false;

// Exponer globalmente para ser visible desde bypassSecurityWall y otros modales
// ── «Por revisar (N)»: días que una regla de marcaciones dejó en revisión ────
// El botón vive en la barra de la grilla para que cualquiera que vea Marcaciones
// llegue a los días sin pasar por Configuración (no todos entran ahí). Respeta el
// filtro de área elegido. Siempre está a la vista (pedido del dueño, 06-11-2026):
// con días dice «Por revisar (N)»; sin días, «No hay nada por revisar». Si la consulta
// falla no afirma que no hay nada: dice «Por revisar» y el motivo en su ayuda.
window._porRevisarDias = [];
function _pintarBotonPorRevisar(btn, estado, total) {
    const v = {
        hay:   { cls: 'btn-outline-danger',    icono: 'bi-exclamation-triangle-fill', texto: `Por revisar (${total})`,
                 ayuda: 'Días que una regla de marcaciones dejó en revisión' },
        nada:  { cls: 'btn-outline-success',   icono: 'bi-check-circle-fill',         texto: 'No hay nada por revisar',
                 ayuda: 'Ninguna regla de marcaciones dejó días en revisión (con el área elegida en el filtro)' },
        error: { cls: 'btn-outline-secondary', icono: 'bi-question-circle',           texto: 'Por revisar',
                 ayuda: 'No se pudo consultar los días por revisar. Vuelva a intentarlo.' },
    }[estado];
    btn.classList.remove('btn-outline-danger', 'btn-outline-success', 'btn-outline-secondary');
    btn.classList.add(v.cls);
    btn.style.display = 'flex';
    btn.title = v.ayuda;
    btn.querySelector('i').className = `bi ${v.icono}`;
    btn.querySelector('span').textContent = v.texto;
}
window.actualizarPorRevisar = async function () {
    const btn = document.getElementById('btn-por-revisar');
    if (!btn) return;
    try {
        const area = stateMarcacionesApp.area || '';
        const r = await fetch(`/api/configuracion/reglas-marcas/por-revisar/?area=${encodeURIComponent(area)}`,
            { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` } });
        if (!r.ok) { window._porRevisarDias = null; _pintarBotonPorRevisar(btn, 'error'); return; }
        const body = await r.json();
        window._porRevisarDias = body.dias || [];
        _pintarBotonPorRevisar(btn, body.total ? 'hay' : 'nada', body.total);
    } catch (e) {
        window._porRevisarDias = null;
        _pintarBotonPorRevisar(btn, 'error');
    }
};

window.abrirPanelPorRevisar = function () {
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    let m = document.getElementById('por-revisar-modal');
    if (!m) {
        m = document.createElement('div');
        m.id = 'por-revisar-modal';
        m.className = 'modal fade';
        m.tabIndex = -1;
        m.innerHTML = `<div class="modal-dialog modal-lg modal-dialog-scrollable"><div class="modal-content">
            <div class="modal-header"><h5 class="modal-title"><i class="bi bi-exclamation-triangle-fill text-danger me-1"></i> Días por revisar</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button></div>
            <div class="modal-body" id="por-revisar-body"></div></div></div>`;
        document.body.appendChild(m);
    }
    const fallo = window._porRevisarDias === null;   // la última consulta falló: no se afirma que no hay nada
    const dias = window._porRevisarDias || [];
    const cuerpo = fallo ? '<div class="text-muted py-3"><i class="bi bi-question-circle me-1"></i>No se pudo consultar los días por revisar. Vuelva a intentarlo en un momento.</div>' : dias.length ? `
        <div class="text-muted mb-2" style="font-size:.84rem;">Una regla de marcaciones dejó estos días en revisión. «Abrir» muestra sus marcas para corregirlas o confirmar que están bien. Mientras queden días aquí, el cierre del tramo de su área está bloqueado.</div>
        <div class="table-responsive"><table class="table table-sm align-middle" style="font-size:.85rem;">
            <thead><tr><th>Persona</th><th>Área</th><th>Fecha</th><th>Secuencia</th><th>Estado</th><th class="text-end">Horas</th><th class="text-end">Deuda (min)</th><th></th></tr></thead>
            <tbody>${dias.map((d, i) => `
                <tr><td>${esc(d.persona)}</td><td>${esc(d.area || '')}</td><td>${window.formatFechaDDMMYYYY ? window.formatFechaDDMMYYYY(d.fecha) : esc(d.fecha)}</td>
                    <td>${esc((d.secuencia || '').split('').map(c => c === 'E' ? 'ENTRADA' : (c === 'S' ? 'SALIDA' : c)).join(' · '))}</td><td>${esc(d.estado || '')}</td>
                    <td class="text-end">${Number(d.horas || 0).toLocaleString('es-CL')}</td>
                    <td class="text-end">${Number(d.deuda || 0).toLocaleString('es-CL')}</td>
                    <td class="text-end"><button type="button" class="btn btn-sm btn-outline-primary py-0" data-pr-abrir="${i}">Abrir</button></td>
                </tr>`).join('')}</tbody>
        </table></div>` :
        '<div class="text-success py-3"><i class="bi bi-check-circle-fill me-1"></i>No hay nada por revisar con el área elegida en el filtro.</div>';
    document.getElementById('por-revisar-body').innerHTML = cuerpo;
    const inst = bootstrap.Modal.getOrCreateInstance(m);
    m.querySelectorAll('[data-pr-abrir]').forEach(b => b.addEventListener('click', () => {
        const d = dias[parseInt(b.dataset.prAbrir)];
        if (!d) return;
        inst.hide();
        if (typeof openManualEntryModal === 'function') openManualEntryModal(d.empleado_id, d.fecha, d.persona);
    }));
    inst.show();
};

window.loadMarcacionesData = async function(opts) {
    // Invalidar caché de auditoría al recargar datos (estado puede haber cambiado)
    if (typeof _invalidarAuditoriaCache === 'function') _invalidarAuditoriaCache();

    // Guard: si ya está cargando, ignorar la solicitud duplicada
    if (_loadMarcacionesInProgress) {
        console.log('⏳ loadMarcacionesData: ya en progreso, se repite al terminar');
        if (!(opts && opts.silent)) _loadMarcacionesPendiente = true; // el refresco automático sí se descarta
        return;
    }

    // Debounce con borde de entrada: la primera llamada corre de inmediato; solo las ráfagas esperan 300ms
    const _ahoraLoad = Date.now();
    const _esRafaga = (_ahoraLoad - _lastLoadMarcacionesCall) < 300 || !!_loadMarcacionesDebounceTimer;
    _lastLoadMarcacionesCall = _ahoraLoad;
    if (_esRafaga) {
        if (_loadMarcacionesDebounceTimer) {
            clearTimeout(_loadMarcacionesDebounceTimer);
        }
        await new Promise(resolve => {
            _loadMarcacionesDebounceTimer = setTimeout(resolve, 300);
        });
    }

    // Verificar nuevamente después del debounce (otra llamada puede haber tomado el lock)
    if (_loadMarcacionesInProgress) {
        console.log('⏳ loadMarcacionesData: tomada por otra llamada durante debounce, se repite al terminar');
        if (!(opts && opts.silent)) _loadMarcacionesPendiente = true;
        return;
    }

    _loadMarcacionesInProgress = true;
    try {
        const resultado = await _loadMarcacionesDataImpl(opts);
        window.actualizarPorRevisar();   // el conteo del botón «Por revisar» acompaña a la grilla (sin esperar)
        return resultado;
    } finally {
        _loadMarcacionesInProgress = false;
        _loadMarcacionesDebounceTimer = null;
        if (_loadMarcacionesPendiente) { _loadMarcacionesPendiente = false; setTimeout(() => window.loadMarcacionesData(), 0); }
    }
};

let _currentMarcacionesAbortController = null;

// Recarga "silenciosa" (la dispara el detector de cambios cada vez que entran marcaciones nuevas): no pone el spinner que vaciaba la
// grilla y mandaba la vista al tope; guarda dónde estaba el scroll (página y contenedores internos de la grilla) y lo devuelve al
// terminar de dibujar, para que quien esté mirando un empleado más abajo siga ahí.
function _marcSnapScroll(container) {
    const snap = { win: [window.scrollX, window.scrollY], ancestros: [], internos: [] };
    for (let el = container; el && el !== document.documentElement; el = el.parentElement) {
        if (el.scrollTop || el.scrollLeft) snap.ancestros.push([el, el.scrollTop, el.scrollLeft]);
    }
    const divs = container.querySelectorAll('div');
    for (let i = 0; i < divs.length; i++) {
        const d = divs[i];
        if (d.scrollTop || d.scrollLeft) snap.internos.push([i, d.scrollTop, d.scrollLeft]);
    }
    return snap;
}
function _marcRestoreScroll(container, snap) {
    const aplicar = () => {
        snap.ancestros.forEach(([el, t, l]) => { el.scrollTop = t; el.scrollLeft = l; });
        const divs = container.querySelectorAll('div');
        snap.internos.forEach(([i, t, l]) => { const d = divs[i]; if (d) { d.scrollTop = t; d.scrollLeft = l; } });
        if (window.scrollX !== snap.win[0] || window.scrollY !== snap.win[1]) window.scrollTo(snap.win[0], snap.win[1]);
    };
    aplicar();
    requestAnimationFrame(() => { aplicar(); setTimeout(aplicar, 150); });
}

async function _loadMarcacionesDataImpl(opts) {
    const silent = !!(opts && opts.silent);
    // 🛑 ABORTAR FETCH ANTERIOR SI AÚN ESTÁ EN PROCESO
    if (_currentMarcacionesAbortController) {
        _currentMarcacionesAbortController.abort();
    }
    _currentMarcacionesAbortController = new AbortController();
    const signal = _currentMarcacionesAbortController.signal;

    const container = document.getElementById('marcaciones-view-container');
    const scrollSnap = silent ? _marcSnapScroll(container) : null;
    if (!silent) { container.innerHTML = MX_SKELETON_HTML; window._mxAnimarProximo = true; }

    // 🛑 BLOQUEO DE SEGURIDAD (PLAN V29+)
    // El sistema valida SIEMPRE si hay empleados con marcas pero sin turno (Fantasmas)
    // El bloqueo es mandatorio para el área de responsabilidad del usuario.
    // Se lanza en paralelo con la carga de la matriz (cada petición cuesta ~300 ms por el túnel);
    // si resulta bloqueado, se descarta la matriz más abajo.
    const bloqueoPromise = checkAuditoriaBloqueo();

    // 🐛 DEBUG: Estado completo
    console.group('🔍 DEBUG: loadMarcacionesData');
    console.log('Estado actual:', {
        year: stateMarcacionesApp.year,
        month: stateMarcacionesApp.month,
        area: stateMarcacionesApp.area,
        turnoId: stateMarcacionesApp.turnoId,
        empleadoId: stateMarcacionesApp.empleadoId
    });
    console.log('Fecha actual real:', new Date());
    console.log('Mes actual real (0-indexed):', new Date().getMonth());
    console.log('Mes en estado (+1):', stateMarcacionesApp.month);

    try {
        let url, isCalendar = false;

        if (stateMarcacionesApp.empleadoId) {
            // MODO CALENDARIO (Individual)
            url = `/api/asistencia/calendar/?fecha_inicio=${stateMarcacionesApp.fechaInicioRRHH}&fecha_fin=${stateMarcacionesApp.fechaFinRRHH}&empleado_id=${stateMarcacionesApp.empleadoId}`;
            isCalendar = true;
        } else {
            // MODO MATRIZ (Equipo)
            // Guard: no llamar si las fechas RRHH aún no están configuradas
            if (!stateMarcacionesApp.fechaInicioRRHH || !stateMarcacionesApp.fechaFinRRHH) {
                container.innerHTML = `
                    <div class="d-flex flex-column align-items-center justify-content-center py-5 text-center">
                        <i class="bi bi-calendar-range fs-1 text-primary mb-3"></i>
                        <h5 class="text-muted">Selecciona el período de fechas</h5>
                        <p class="text-muted small">Ingresa las fechas de inicio y fin en el selector de período para cargar la matriz.</p>
                    </div>`;
                console.groupEnd();
                return;
            }
            url = `/api/asistencia/matriz/?fecha_inicio=${stateMarcacionesApp.fechaInicioRRHH}&fecha_fin=${stateMarcacionesApp.fechaFinRRHH}`;
            if (stateMarcacionesApp.area) url += `&area=${encodeURIComponent(stateMarcacionesApp.area)}`;
            if (stateMarcacionesApp.turnoId) url += `&turno_id=${stateMarcacionesApp.turnoId}`;
        }

        console.log('URL generada:', url);

        const fetchPromise = fetch(url, { signal });
        fetchPromise.catch(() => { /* si hay bloqueo y se aborta, no dejar el rechazo sin manejar */ });
        if (await bloqueoPromise) {
            console.warn("⚠️ ACCESO BLOQUEADO: Se detectaron empleados con marcas pero sin turno asignado.");
            _currentMarcacionesAbortController.abort();
            console.groupEnd();
            return;
        }
        const resp = await fetchPromise;
        if (!resp.ok) throw new Error("Error fetching data");
        const data = await resp.json();

        // 🛑 PREVENCIÓN DE RACE CONDITIONS: si este no es el fetch más reciente, abortamos silenciosamente el render
        if (signal.aborted) {
            console.log('Fetch de matriz completado pero obsoleto. Render abortado.');
            console.groupEnd();
            return;
        }

        console.log('Datos recibidos:', {
            periodo: data.periodo,
            feriadosCount: data.feriados?.length || 0,
            feriados: data.feriados,
            empleadosCount: Object.keys(data.matrix || {}).length
        });
        console.groupEnd();

        // LIMPIAR CONTAINER EXPLÍCITAMENTE ANTES DE RENDERIZAR
        container.innerHTML = '';
        
        stateMarcacionesApp.data = data;

        if (isCalendar) {
            renderReporteEmpleado(data, container);
        } else {
            renderVistaAnalitica(data, container);
        }
        if (scrollSnap) _marcRestoreScroll(container, scrollSnap);

    } catch (e) {
        if (e.name === 'AbortError') {
            console.log('Fetch de matriz abortado por el usuario o nueva solicitud.');
            console.groupEnd();
        } else {
            console.error("Error cargando datos:", e);
            console.groupEnd();
            container.innerHTML = `<div class="alert alert-danger">Error cargando datos: ${e.message}</div>`;
        }
    }
}

async function syncMarcacionesBioAlba(areas = null, fechaInicioOverride = null, fechaFinOverride = null, deepSync = false) {
    const btn = document.querySelector('button[onclick="syncMarcacionesBioAlba()"]');
    const originalContent = btn ? btn.innerHTML : '';
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Conectando...'; }

    // ── RANGO DE FECHAS ─────────────────────────────────────────────────────
    // Prioridad: override del modal → rango RRHH del toolbar → primer día del mes
    let fechaInicio = fechaInicioOverride || stateMarcacionesApp.fechaInicioRRHH;
    let fechaFin    = fechaFinOverride    || stateMarcacionesApp.fechaFinRRHH;

    // Fallback: si todavía no hay fechas, usar primer y último día del mes seleccionado
    if (!fechaInicio) {
        const mes  = stateMarcacionesApp.month;
        const anio = stateMarcacionesApp.year;
        fechaInicio = `${anio}-${String(mes).padStart(2, '0')}-01`;
    }
    if (!fechaFin) {
        // Calcular el último día del mes correctamente evitando problemas de Timezone
        const mes  = stateMarcacionesApp.month;
        const anio = stateMarcacionesApp.year;
        const ultimoDia = new Date(anio, mes, 0).getDate();
        fechaFin = `${anio}-${String(mes).padStart(2, '0')}-${String(ultimoDia).padStart(2, '0')}`;
    }

    console.log(`[Sync BioAlba] Rango: ${fechaInicio} → ${fechaFin}`, areas ? `Áreas: ${areas.join(', ')}` : 'Todas las áreas', `Deep Sync: ${deepSync}`);

    // Mostrar overlay de carga SweetAlert2 sin doble spinner
    Swal.fire({
        title: '<span style="font-size:1.15rem;font-weight:800;color:#1e293b;"><i class="bi bi-lightning-charge-fill text-warning" aria-hidden="true"></i> Sincronizando con BioAlba</span>',
        html: `
            <div class="text-center py-2" style="font-family: var(--font-sans);">
                <p id="swal-sync-status" class="mb-1 fw-bold text-slate-700">Conectando con BioAlba...</p>
                <p id="swal-sync-detail" class="text-muted small mb-0">Por favor, no cierres esta ventana. El proceso tardará unos segundos.</p>
            </div>
        `,
        allowOutsideClick: false,
        allowEscapeKey: false,
        showConfirmButton: false,
        didOpen: () => {
            Swal.showLoading();
        }
    });

    try {
        // Construir payload (áreas son body, fechas van en query params)
        const payload = areas ? { areas } : {};

        // Crear AbortController para timeout de 6 minutos
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 360000);

        if (btn) btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Sincronizando...';

        const url = `/api/sync/asistencia/now/stream/?fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}&deep_sync=${deepSync}`;
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: JSON.stringify(payload),
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            throw new Error(errData.detail || `Error HTTP ${resp.status}`);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let stats = null;

        const statusEl = document.getElementById('swal-sync-status');
        const detailEl = document.getElementById('swal-sync-detail');

        // Helper para procesar la lectura del stream SSE
        function _processSSELines(lines) {
            let eventType = null;
            let eventData = null;
            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    eventType = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    try { eventData = JSON.parse(line.slice(6)); } catch { eventData = null; }
                } else if (line === '' && eventType && eventData !== null) {
                    if (eventType === 'start') {
                        if (statusEl) statusEl.textContent = eventData.info || 'Verificando periodos...';
                    } else if (eventType === 'info') {
                        if (detailEl) detailEl.textContent = eventData.message || '';
                    } else if (eventType === 'start_recalc') {
                        if (statusEl) statusEl.textContent = 'Iniciando recálculo...';
                        if (detailEl) detailEl.textContent = `Total a procesar: ${eventData.total} empleados`;
                    } else if (eventType === 'progress') {
                        if (eventData.stage === 'download') {
                            if (statusEl) statusEl.textContent = 'Descargando de BioAlba...';
                            if (detailEl) detailEl.textContent = eventData.info || '';
                        } else if (eventData.stage === 'recalc') {
                            if (statusEl) statusEl.textContent = `Recalculando (${eventData.idx}/${eventData.total})`;
                            if (detailEl) detailEl.textContent = eventData.info || '';
                        }
                    } else if (eventType === 'done') {
                        stats = eventData;
                    } else if (eventType === 'error') {
                        throw new Error(eventData.message || 'Error durante la sincronización');
                    }
                    eventType = null;
                    eventData = null;
                }
            }
        }

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            const lines = buffer.split('\n');
            buffer = lines.pop();
            _processSSELines(lines);
        }

        // Procesar buffer residual
        if (buffer.trim()) {
            const remainingLines = buffer.split('\n');
            remainingLines.push('');
            _processSSELines(remainingLines);
        }

        if (!stats) {
            throw new Error('La conexión se cerró sin recibir el reporte de finalización.');
        }

        const nuevas        = stats.marcaciones_nuevas    ?? 0;
        const recalc        = stats.dias_recalculados     ?? 0;
        const bloqueadas    = stats.bloqueados_sin_asig   ?? 0;
        const errores       = stats.errores               ?? 0;
        const duracion      = stats.duracion_segundos     ? parseFloat(stats.duracion_segundos).toFixed(1) : '—';
        const areasLabel    = areas ? `${areas.length} área${areas.length > 1 ? 's' : ''}` : 'Todas las áreas';

        const iconoNuevas   = nuevas > 0 ? '<i class="bi bi-check-circle-fill text-success" aria-hidden="true"></i>' : '<i class="bi bi-dash-circle text-muted" aria-hidden="true"></i>';
        const mensajeExtra  = nuevas === 0
            ? '<p style="color:#64748b;font-size:0.85rem;margin-top:8px;">No hay marcaciones nuevas para el período. Los datos ya estaban actualizados.</p>'
            : '';

        await Swal.fire({
            title: '<span style="font-size:1.1rem;font-weight:800;color:#1e293b;"><i class="bi bi-cloud" aria-hidden="true"></i> Sincronización BioAlba</span>',
            html: `
                <div style="text-align:left;font-family: var(--font-sans);">
                    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;">
                        <span style="background:#e0f2fe;color:#0369a1;font-size: 0.75rem;font-weight:700;padding:3px 8px;border-radius:999px;">${areasLabel}</span>
                        <span style="background:#f1f5f9;color:#475569;font-size: 0.75rem;font-weight:600;padding:3px 8px;border-radius:999px;">${fechaInicio} → ${fechaFin}</span>
                        <span style="background:#f1f5f9;color:#64748b;font-size: 0.75rem;padding:3px 8px;border-radius:999px;"><i class="bi bi-stopwatch" aria-hidden="true"></i> ${duracion}s</span>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
                        <div style="background:${nuevas > 0 ? '#f0fdf4' : '#f8fafc'};border:1px solid ${nuevas > 0 ? '#86efac' : '#e2e8f0'};border-radius:10px;padding:12px;text-align:center;">
                            <div style="font-size:1.6rem;font-weight:800;color:${nuevas > 0 ? '#16a34a' : '#94a3b8'};">${nuevas}</div>
                            <div style="font-size: 0.75rem;color:#64748b;margin-top:2px;">${iconoNuevas} Marcaciones nuevas</div>
                        </div>
                        <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:12px;text-align:center;">
                            <div style="font-size:1.6rem;font-weight:800;color:#2563eb;">${recalc}</div>
                            <div style="font-size: 0.75rem;color:#64748b;margin-top:2px;"><i class="bi bi-calendar3" aria-hidden="true"></i> Días recalculados</div>
                        </div>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                        <div style="background:#fafafa;border:1px solid #e2e8f0;border-radius:8px;padding:8px 12px;display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:0.75rem;color:#64748b;"><i class="bi bi-lock" aria-hidden="true"></i> Sin asignación</span>
                            <span style="font-weight:700;color:#f59e0b;font-size:0.85rem;">${bloqueadas}</span>
                        </div>
                        <div style="background:#fafafa;border:1px solid #e2e8f0;border-radius:8px;padding:8px 12px;display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:0.75rem;color:#64748b;"><i class="bi bi-x-circle-fill text-danger" aria-hidden="true"></i> Errores</span>
                            <span style="font-weight:700;color:${errores > 0 ? '#dc2626' : '#10b981'};font-size:0.85rem;">${errores}</span>
                        </div>
                    </div>
                    ${mensajeExtra}
                </div>
            `,
            icon: nuevas > 0 ? 'success' : 'info',
            confirmButtonText: 'Entendido',
            confirmButtonColor: '#3f6fd6',
            showCloseButton: true,
            customClass: { popup: 'shadow-lg' }
        });

        if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData({ silent: true });
    } catch (e) {
        Swal.close();
        console.error('[Sync BioAlba] Error:', e);
        if (e.name === 'AbortError') {
            showToast('La sincronización tardó más de 6 minutos y se detuvo. Vuelva a intentarlo con menos días o menos áreas.', 'error');
        } else {
            showToast('No se pudo sincronizar con BioAlba. ' + e.message, 'error');
        }
        try { await window.loadMarcacionesData({ silent: true }); } catch (_) {}
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = originalContent; }
    }
}

// ============================================
// MODAL DE SINCRONIZACIÓN POR ÁREAS
// ============================================

function openSyncMarcacionesModal() {
    // Pre-llenar fechas desde el estado actual del toolbar
    const fInicio = stateMarcacionesApp.fechaInicioRRHH || '';
    const fFin    = stateMarcacionesApp.fechaFinRRHH    || '';

    // Destruir modal previo para re-renderizarlo con fechas actualizadas
    const existente = document.getElementById('modal-sync-marcaciones');
    if (existente) {
        bootstrap.Modal.getInstance(existente)?.dispose();
        existente.remove();
    }

    const modalHTML = `
        <div class="modal fade" id="modal-sync-marcaciones" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="bi bi-funnel"></i> Sincronizar por Áreas
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p class="text-muted mb-2">
                            <i class="bi bi-info-circle"></i>
                            Selecciona el rango de fechas y las áreas a sincronizar con BioAlba.
                        </p>
                        <!-- Rango de fechas -->
                        <div class="row g-2 mb-3">
                            <div class="col">
                                <label for="sync-areas-fecha-inicio" class="form-label small fw-semibold mb-1">Desde</label>
                                <input type="date" class="form-control form-control-sm" id="sync-areas-fecha-inicio"
                                       value="${fInicio}">
                            </div>
                            <div class="col">
                                <label for="sync-areas-fecha-fin" class="form-label small fw-semibold mb-1">Hasta</label>
                                <input type="date" class="form-control form-control-sm" id="sync-areas-fecha-fin"
                                       value="${fFin}">
                            </div>
                        </div>
                        <!-- Selección de áreas -->
                        <div class="mb-2">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="select-all-areas-sync"
                                       onchange="toggleAllAreasSync(this.checked)">
                                <label class="form-check-label fw-bold" for="select-all-areas-sync">
                                    Seleccionar Todas
                                </label>
                            </div>
                            <hr class="my-2">
                        </div>
                        <div id="areas-sync-list" class="mb-3" style="max-height:260px;overflow-y:auto">
                            <div class="text-center">
                                <div class="spinner-border spinner-border-sm text-primary"></div>
                                <span class="ms-2">Cargando áreas...</span>
                            </div>
                        </div>
                        <!-- Sincronización profunda (Deep Sync) -->
                        <div class="mt-3 pt-2 border-top">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="sync-deep-sync">
                                <label class="form-check-label fw-bold text-danger small" for="sync-deep-sync">
                                    <i class="bi bi-exclamation-triangle"></i> Sincronización profunda (Forzar red)
                                </label>
                                <div class="form-text small">Descarga completa del periodo omitiendo la regla de meses estables.</div>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-primary" onclick="confirmSyncMarcaciones()">
                            <i class="bi bi-cloud-download"></i> Sincronizar
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHTML);

    // Cargar áreas y mostrar modal
    loadAreasForSync();
    bootstrap.Modal.getOrCreateInstance(document.getElementById('modal-sync-marcaciones')).show();
}

async function loadAreasForSync() {
    try {
        // Fix #A: usar caché — no repetir la llamada HTTP
        const data = await getMetadata();
        const areas = data.areas || [];

        const container = document.getElementById('areas-sync-list');
        if (areas.length === 0) {
            container.innerHTML = '<div class="alert alert-warning">No se encontraron áreas</div>';
            return;
        }

        container.innerHTML = areas.map(area => `
            <div class="form-check">
                <input class="form-check-input area-sync-checkbox" type="checkbox"
                       value="${area}" id="area-sync-${area.replace(/\s+/g, '-')}">
                <label class="form-check-label" for="area-sync-${area.replace(/\s+/g, '-')}">
                    ${area}
                </label>
            </div>
        `).join('');
    } catch (e) {
        console.error('Error cargando áreas:', e);
        document.getElementById('areas-sync-list').innerHTML =
            '<div class="alert alert-danger">Error cargando áreas</div>';
    }
}

function toggleAllAreasSync(checked) {
    document.querySelectorAll('.area-sync-checkbox').forEach(cb => cb.checked = checked);
}

async function confirmSyncMarcaciones() {
    const btnConfirm = document.querySelector('#modal-sync-marcaciones .btn-primary');
    if (btnConfirm) btnConfirm.blur();

    // Leer fechas del modal
    const fInicio = document.getElementById('sync-areas-fecha-inicio')?.value || '';
    const fFin    = document.getElementById('sync-areas-fecha-fin')?.value    || '';

    if (!fInicio || !fFin) {
        Avisos.falta('Faltan las fechas. Elija desde y hasta.');
        return;
    }
    if (fFin < fInicio) {
        Avisos.falta('La fecha «hasta» no puede ser anterior a «desde».');
        return;
    }

    const checkboxes   = document.querySelectorAll('.area-sync-checkbox:checked');
    const selectedAreas = Array.from(checkboxes).map(cb => cb.value);

    if (selectedAreas.length === 0) {
        Avisos.falta('Falta el área. Elija al menos una para sincronizar.');
        return;
    }

    // Cerrar modal liberando foco (evita advertencia ARIA)
    const modalEl = document.getElementById('modal-sync-marcaciones');
    if (document.activeElement) document.activeElement.blur();
    
    // Leer el valor de deep_sync antes de cerrar/destruir el modal
    const deepSync = document.getElementById('sync-deep-sync')?.checked || false;
    
    bootstrap.Modal.getInstance(modalEl)?.hide();

    // Sincronizar con áreas Y rango de fechas
    await syncMarcacionesBioAlba(selectedAreas, fInicio, fFin, deepSync);
}


// ==========================================
// RENDERIZADORES
// ==========================================

// ==========================================
// RENDERIZADORES
// ==========================================

// ==========================================
// REPORTE CONSOLIDADO ENTERPRISE (V12)
// ==========================================

function calcularMetricasEmpleado(data) {
    // Clonación profunda para inmutabilidad y no afectar la grilla
    const dataList = Array.isArray(data.data) ? JSON.parse(JSON.stringify(data.data)) : (Array.isArray(data) ? JSON.parse(JSON.stringify(data)) : []);
    const infoMeta = data.info || {};
    const feriadosArray = data.feriados || [];
    
    let esBolsa = false;
    let metaMensualMinutos = 0;
    let minutosTrabajadosAcumulados = 0;
    let minutosDeuda = 0;
    let minutosHE_Aprobado = 0;
    let diasTrabajados = 0;
    let atrasosCount = 0;
    let faltasCount = 0;
    let justificacionesCount = 0;
    let salidasAdelantadasCount = 0;
    let jornadasEspecialesCount = 0;
    let permisosCount = 0;

    dataList.forEach(a => {
        if (a.horas_trabajadas) {
            minutosTrabajadosAcumulados += Math.round((a.horas_trabajadas || 0) * 60);
        }
        if (a.minutos_deuda) minutosDeuda += a.minutos_deuda;
        
        const isEsp = a.estado === 'JORNADA_ESPECIAL' || a.estado === 'EXTRA' || a.estado === 'FERIADO Y JORNADA EXTRA' || a.estado === 'DÍA LIBRE Y JORNADA EXTRA';
        
        if (!isEsp && a.estado_he === 'APROBADO' && a.minutos_extra_autorizados) {
            minutosHE_Aprobado += a.minutos_extra_autorizados;
        }
        
        if (a.estado === 'ATRASO') atrasosCount++;
        if (a.estado === 'INASISTENCIA' || (a.estado && a.estado.includes('FALTA'))) faltasCount++;
        if (a.estado && (a.estado.includes('SALIDA_ADELANTADA') || a.estado.includes('SAD'))) salidasAdelantadasCount++;
        const tieneJaMetrics = Boolean(a.jornada_adicional && a.jornada_adicional.estado !== 'RECHAZADA');
        if (isEsp || tieneJaMetrics) jornadasEspecialesCount++;
        if (a.justificacion || a.nomenclatura) justificacionesCount++;
        if (a.tiene_permiso_hora || a.permiso_activo) permisosCount++;
        
        if (['OK', 'ATRASO', 'SALIDA_ADELANTADA', 'JORNADA_ESPECIAL', 'EXTRA', 'FERIADO Y JORNADA EXTRA', 'DÍA LIBRE Y JORNADA EXTRA'].includes(a.estado)) {
            diasTrabajados++;
        }

        if (a.tipo_programacion === 'BOLSA_FLEXIBLE' || a.tipo_programacion === 'FLEXIBLE_BOLSA') {
            esBolsa = true;
            if (a.meta_mensual_minutos) metaMensualMinutos = a.meta_mensual_minutos;
            else if (a.meta_horas_semanales) metaMensualMinutos = Math.round(a.meta_horas_semanales * 60);
        }
    });

    // Los días del calendario no traen tipo_programacion (la detección de arriba
    // nunca prendía): el dato vive en info, que el servidor sí entrega.
    if (!esBolsa && infoMeta && (infoMeta.tipo_programacion === 'BOLSA_FLEXIBLE' || infoMeta.tipo_programacion === 'FLEXIBLE_BOLSA')) {
        esBolsa = true;
        if (!metaMensualMinutos) {
            metaMensualMinutos = infoMeta.meta_mensual_minutos || Math.round((infoMeta.meta_horas_semanales || 0) * 60);
        }
    }

    // Vigencia parcial (ingreso/egreso a mitad del tramo): meta proporcional a los
    // días corridos disponibles (el servidor la calcula una sola vez en la matriz).
    const prorrateoBolsa = (esBolsa && infoMeta && infoMeta.bolsa_prorrateo) ? infoMeta.bolsa_prorrateo : null;
    if (prorrateoBolsa && Number.isFinite(prorrateoBolsa.factor) && prorrateoBolsa.factor < 1) {
        metaMensualMinutos = Math.round(metaMensualMinutos * prorrateoBolsa.factor);
    }

    if (esBolsa && infoMeta && infoMeta.meta_ajustada_minutos_descuento) {
        metaMensualMinutos = Math.max(0, metaMensualMinutos - infoMeta.meta_ajustada_minutos_descuento);
    }

    return {
        esBolsa,
        prorrateoBolsa,
        metaMensualMinutos,
        minutosTrabajadosAcumulados,
        minutosDeuda,
        saldoBolsa: minutosTrabajadosAcumulados - metaMensualMinutos,
        minutosHE_Aprobado,
        diasTrabajados,
        atrasosCount,
        faltasCount,
        justificacionesCount,
        salidasAdelantadasCount,
        jornadasEspecialesCount,
        permisosCount,
        dataList,
        feriadosArray
    };
}

let pdfDataCache = null;

function renderReporteEmpleado(data, container) {
    // 1. Limpieza de memoria (Sanitización)
    const oldPopovers = container.querySelectorAll('[data-bs-toggle="popover"]');
    oldPopovers.forEach(el => {
        const popover = bootstrap.Popover.getInstance(el);
        if (popover) popover.dispose();
    });
    
    // Guardar data en cache para PDF
    pdfDataCache = data;

    // Calcular Resumen (Saldo, Deuda, etc) para mostrarlo arriba del visor
    const metrics = calcularMetricasEmpleado(data);
    let summaryHtml = '';
    if (metrics.esBolsa) {
        const saldoColor = metrics.saldoBolsa >= 0 ? 'text-success' : 'text-danger';
        const saldoSigno = metrics.saldoBolsa > 0 ? '+' : (metrics.saldoBolsa < 0 ? '-' : '');
        summaryHtml = `
            <div class="row g-2 mb-3">
                <div class="col-md-3">
                    <div class="card border-0 bg-info-subtle shadow-sm h-100">
                        <div class="card-body py-2 text-center">
                            <small class="text-muted d-block">Meta Periodo</small>
                            <span class="fs-5 fw-bold text-dark tabular-nums">${formatMinutesToHHMM(metrics.metaMensualMinutos)}</span>
                            ${(() => {
                                // Texto con comillas y concatenación: rjsmin daña las plantillas anidadas
                                const pb = metrics.prorrateoBolsa;
                                if (!pb) return '';
                                const _fEs = iso => iso ? iso.split('-').reverse().join('-') : '';
                                let partes = [];
                                if (Number.isFinite(pb.factor) && pb.factor < 1) {
                                    const motivo = [pb.fecha_ingreso ? 'ingreso el ' + _fEs(pb.fecha_ingreso) : '', pb.fecha_salida ? 'egreso el ' + _fEs(pb.fecha_salida) : ''].filter(Boolean).join(' y ');
                                    partes.push('<small class="d-block text-muted" style="font-size:0.68rem;">Ajustada por ' + motivo + ' (' + pb.dias_disponibles + ' de ' + pb.dias_tramo + ' días)</small>');
                                }
                                if (pb.aviso_21_dias) {
                                    partes.push('<small class="d-block" style="font-size:0.68rem;color:#d97706;" title="' +
                                        'La ley (art. 25 bis del Código del Trabajo) exige repartir las 180 horas en al menos ' + pb.dias_minimos_ley +
                                        ' días. Es un aviso: no bloquea nada."><i class="bi bi-exclamation-triangle-fill me-1"></i>' +
                                        'Período con solo ' + pb.dias_disponibles + ' días (la ley pide ' + pb.dias_minimos_ley + ')</small>');
                                }
                                return partes.join('');
                            })()}
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card border-0 bg-warning-subtle shadow-sm h-100">
                        <div class="card-body py-2 text-center">
                            <small class="text-muted d-block">Avance Real</small>
                            <span class="fs-5 fw-bold text-dark tabular-nums">${formatMinutesToHHMM(metrics.minutosTrabajadosAcumulados)}</span>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card border-0 bg-light shadow-sm h-100">
                        <div class="card-body py-2 text-center">
                            <small class="text-muted d-block">Deuda (No Justif.)</small>
                            <span class="fs-5 fw-bold text-danger tabular-nums">-${formatMinutesToHHMM(metrics.minutosDeuda)}</span>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card border-0 bg-light shadow-sm h-100">
                        <div class="card-body py-2 text-center">
                            <small class="text-muted d-block">Saldo Bolsa</small>
                            <span class="fs-5 fw-bold ${saldoColor} tabular-nums">${saldoSigno}${formatMinutesToHHMM(Math.abs(metrics.saldoBolsa))}</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    const html = `
        <div class="card shadow-sm border-0 bg-white mb-3">
            <div class="card-header bg-light border-bottom-0 d-flex justify-content-between align-items-center py-3 flex-wrap gap-2">
                <div class="d-flex align-items-center">
                    <i class="bi bi-file-earmark-pdf fs-4 text-danger me-2"></i>
                    <h6 class="mb-0 fw-bold">Visor de Reporte Consolidado (Oficial)</h6>
                </div>
                <div class="d-flex align-items-center gap-2">
                    <label for="pdf-format-select" class="small text-muted mb-0 fw-bold text-nowrap">Papel:</label>
                    <select id="pdf-format-select" class="form-select form-select-sm shadow-sm" style="width: 130px;" onchange="updateVisorPDF(false)">
                        <option value="a4" selected>A4</option>
                        <option value="letter">Carta (Letter)</option>
                        <option value="legal">Oficio (Legal)</option>
                    </select>
                    <button class="btn btn-sm btn-danger shadow-sm ms-2 text-nowrap" onclick="updateVisorPDF(true)">
                        <i class="bi bi-download me-1"></i> Descargar
                    </button>
                </div>
            </div>
        </div>

        ${summaryHtml}

        <div class="card shadow-sm border-0 bg-light" style="min-height: 600px;">
            <div class="card-body p-0 d-flex justify-content-center align-items-center" id="pdf-iframe-container">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Generando PDF...</span>
                </div>
            </div>
        </div>
    `;

    container.innerHTML = html;

    // Generar PDF inicial asíncronamente
    setTimeout(() => {
        updateVisorPDF(false);
    }, 50);
}

window.updateVisorPDF = async function(isDownload = false) {
    if (!pdfDataCache) return;

    // 1. Seguro de vida: Validar rango de fechas para prevenir crasheos de memoria gráfica
    const startDateRaw = new Date(stateMarcacionesApp.fechaInicioRRHH);
    const endDateRaw = new Date(stateMarcacionesApp.fechaFinRRHH);
    const diffTime = Math.abs(endDateRaw - startDateRaw);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)); 
    
    if (diffDays > 93) {
        if (typeof Swal !== 'undefined') {
            Swal.fire('Periodo demasiado largo', 'Para prevenir colapsos de memoria, el reporte PDF está limitado a un máximo de 3 meses. Por favor, ajuste el filtro de fechas.', 'warning');
        } else {
            Avisos.falta('El período es muy largo para este informe. Elija como máximo 3 meses.');
        }
        return;
    }

    const formatSelect = document.getElementById('pdf-format-select');
    const format = formatSelect ? formatSelect.value : 'a4';

    await window.ensureLib('jspdf');
    const { jsPDF } = window.jspdf;
    // Forzamos orientación Horizontal (landscape) para que quepan las nuevas columnas
    const doc = new jsPDF('l', 'pt', format);
    
    const data = pdfDataCache;
    const empleadoInfo = data.empleado_info || {};
    
    let nombreEmpleado = 'Empleado no identificado';
    if (empleadoInfo.nombre) {
        nombreEmpleado = `${empleadoInfo.apellido_paterno || ''} ${empleadoInfo.apellido_materno || ''} ${empleadoInfo.nombre || ''}`.trim().replace(/  +/g, ' ');
    } else if (stateMarcacionesApp.data?.empleado_nombre) {
        nombreEmpleado = stateMarcacionesApp.data.empleado_nombre;
    }

    const rut = empleadoInfo.rut ? window.rutVista(empleadoInfo.rut) : 'No Registrado';
    const cargo = empleadoInfo.cargo || 'No Registrado';
    const area = empleadoInfo.area || stateMarcacionesApp.data?.empleado_area || stateMarcacionesApp.data?.area || 'No Registrada';

    let fechaInicio = '', fechaFin = '';
    if (data.periodo) {
        fechaInicio = window.formatFechaDDMMYYYY(data.periodo.inicio);
        fechaFin = window.formatFechaDDMMYYYY(data.periodo.fin);
    }
    
    // Header
    doc.setFont("helvetica", "bold");
    doc.setFontSize(16);
    doc.text("AGUACOL SPA", 40, 40);
    
    doc.setFontSize(10);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(100);
    doc.text("Reporte Consolidado de Asistencia", 40, 55);
    
    // Adjust header right alignment based on format width
    const pageWidth = doc.internal.pageSize.getWidth();
    doc.text(`Periodo: ${fechaInicio} al ${fechaFin}`, pageWidth - 195, 40);
    doc.text(`Generado: ${window.formatFechaDDMMYYYY(new Date())}`, pageWidth - 195, 55);
    
    doc.line(40, 65, pageWidth - 40, 65); // separator

    // Recalcular métricas para el array del AutoTable y otras lógicas
    const metrics = calcularMetricasEmpleado(data);

    // Info Empleado
    doc.setTextColor(0);
    doc.setFont("helvetica", "bold");
    doc.text("RUT:", 40, 85);
    doc.setFont("helvetica", "normal");
    doc.text(rut, 80, 85);

    doc.setFont("helvetica", "bold");
    doc.text("Nombre:", 40, 100);
    doc.setFont("helvetica", "normal");
    doc.text(nombreEmpleado, 90, 100);

    const midPoint = pageWidth / 2 + 20;
    doc.setFont("helvetica", "bold");
    doc.text("Cargo:", midPoint, 85);
    doc.setFont("helvetica", "normal");
    doc.text(cargo, midPoint + 40, 85);

    doc.setFont("helvetica", "bold");
    doc.text("Área:", midPoint, 100);
    doc.setFont("helvetica", "normal");
    doc.text(area, midPoint + 35, 100);

    const turnoNombre = data.info?.turno || 'No asignado';
    doc.setFont("helvetica", "bold");
    doc.text("Turno Asignado:", 40, 115);
    doc.setFont("helvetica", "normal");
    doc.text(turnoNombre, 125, 115);

    // Lado derecho: Horas del turno o meta de la bolsa
    doc.setFont("helvetica", "bold");
    if (metrics.esBolsa) {
        doc.text("Meta Bolsa (Hrs):", midPoint, 115);
        doc.setFont("helvetica", "normal");
        const metaHrs = (metrics.metaMensualMinutos / 60).toFixed(1);
        doc.text(`${metaHrs} Hrs`, midPoint + 95, 115);
    } else {
        doc.text("Hrs Semanales:", midPoint, 115);
        doc.setFont("helvetica", "normal");
        const hrsSemanales = data.info?.meta_horas_semanales || 45;
        doc.text(`${hrsSemanales} Hrs`, midPoint + 90, 115);
    }

    let startY = 135;
    const turnoDias = data.info?.turno_dias || {};
    if (Object.keys(turnoDias).length > 0) {
        doc.setFont("helvetica", "bold");
        doc.setFontSize(10);
        doc.text("Horario Teórico Día a Día", 40, startY);
        
        const theader = [["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]];
        const tbody = [];
        let row = [];
        for (let i = 0; i < 7; i++) {
            let config = turnoDias[i];
            if (!config || config.es_libre) {
                row.push("Libre");
            } else {
                let e = config.hora_entrada ? config.hora_entrada.substring(0, 5) : "--:--";
                let s = config.hora_salida ? config.hora_salida.substring(0, 5) : "--:--";
                let text = `${e} a ${s}`;
                row.push(text);
            }
        }
        tbody.push(row);

        doc.autoTable({
            startY: startY + 10,
            head: theader,
            body: tbody,
            theme: 'grid',
            headStyles: { fillColor: [41, 128, 185], textColor: 255, halign: 'center', fontSize: 8 },
            bodyStyles: { halign: 'center', fontSize: 8 },
            margin: { left: 40, right: 40 }
        });
        
        startY = doc.lastAutoTable.finalY + 20;
    } else {
        startY = 140;
    }

    const tableBody = metrics.dataList.map(a => {
        let estadoStr = a.estado || '';
        let estadoBadge = estadoStr;

        // Mejorar nomenclaturas a nivel Enterprise
        if (estadoStr === 'OK') estadoBadge = 'Jornada Completa';
        else if (estadoStr === 'ATRASO' || estadoStr === 'ATR') estadoBadge = 'Atraso';
        else if (estadoStr === 'SALIDA_ADELANTADA' || estadoStr === 'SAD') estadoBadge = 'Salida Adelantada';
        else if (estadoStr === 'ATR_SAD') estadoBadge = 'Atraso / Sal. Adelantada';
        else if (estadoStr === 'INASISTENCIA' || estadoStr === 'FALTA') estadoBadge = 'Inasistencia';
        else if (estadoStr === 'INASISTENCIA_COMPENSADA') {
            if (a.deuda_condonada === 3) {
                estadoBadge = 'Compensado por Intercambio';
            } else {
                estadoBadge = 'Compensado con H.E.';
            }
        }
        else if (estadoStr === 'JORNADA_COMPENSATORIA') estadoBadge = 'Jornada Compensatoria';
        else if (estadoStr === 'LIBRE') estadoBadge = 'Día Libre';
        else if (estadoStr === 'NO_ACTIVO') estadoBadge = 'No Activo';

        // Determinar Feriado y buscar su descripción
        let feriadoDesc = null;
        if (Array.isArray(data.feriados)) {
            const ferObj = data.feriados.find(f => f === a.fecha || f.fecha === a.fecha);
            if (ferObj) feriadoDesc = ferObj.descripcion || 'Feriado';
        } else if (data.feriados && typeof data.feriados === 'object') {
            if (data.feriados[a.fecha]) feriadoDesc = data.feriados[a.fecha];
        }

        if (!feriadoDesc && metrics.feriadosArray && metrics.feriadosArray.includes(a.fecha)) {
            feriadoDesc = 'Feriado';
        }

        // Aplicar jerarquía de estados (Feriado -> Permisos -> Estado normal)
        let esJornadaEspecial = estadoStr === 'JORNADA_ESPECIAL' || estadoStr === 'EXTRA';
        let badgeEspecial = estadoStr === 'EXTRA' ? ' - Jornada Extra' : ' - Jornada Especial';

        // Determinar si el día era teóricamente libre
        let diaDate = new Date(a.fecha);
        let diaNum = (diaDate.getUTCDay() + 6) % 7;
        let esLibreTeorico = turnoDias && turnoDias[diaNum] && turnoDias[diaNum].es_libre;

        // Formatear fecha a texto amigable
        const diasSemana = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
        const meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
        let fechaFormateada = `${diasSemana[diaDate.getUTCDay()]} ${diaDate.getUTCDate()} ${meses[diaDate.getUTCMonth()]} ${diaDate.getUTCFullYear()}`.toUpperCase();

        if (feriadoDesc) {
            estadoBadge = feriadoDesc.toUpperCase().includes('FERIADO') ? feriadoDesc : `Feriado: ${feriadoDesc}`;
            if (esJornadaEspecial) estadoBadge += badgeEspecial;
        } else if (a.tiene_permiso_hora) {
            estadoBadge = 'Permiso (Horas)';
            if (esJornadaEspecial) estadoBadge += badgeEspecial;
        } else if (a.permiso_activo) {
            estadoBadge = 'Permiso (Día)';
        } else if (esLibreTeorico && esJornadaEspecial) {
            estadoBadge = 'Día Libre' + badgeEspecial;
        } else if (estadoStr === 'EXTRA') {
            estadoBadge = 'Jornada Extra';
        } else if (estadoStr === 'JORNADA_ESPECIAL') {
            estadoBadge = 'Jornada Especial';
        }
        
        const tiempoColacion = a.minutos_colacion || 0;
        
        return [
            fechaFormateada,
            estadoBadge,
            a.hora_entrada_real || '--:--',
            a.hora_salida_colacion || '--:--',
            a.hora_entrada_colacion || '--:--',
            a.hora_inicio_permiso || '--:--',
            a.hora_termino_permiso || '--:--',
            a.hora_salida_real || '--:--',
            a.horas_trabajadas > 0 ? formatDecimalToTime(a.horas_trabajadas) : '--:--',
            (a.minutos_extra_autorizados > 0) ? formatMinutesToHHMM(a.minutos_extra_autorizados) : '--:--',
            tiempoColacion > 0 ? formatMinutesToHHMM(tiempoColacion) : '--:--',
            a.minutos_atraso > 0 ? formatMinutesToHHMM(a.minutos_atraso) : '--:--',
            a.minutos_salida_adelantada > 0 ? formatMinutesToHHMM(a.minutos_salida_adelantada) : '--:--',
            a.minutos_exceso_colacion > 0 ? formatMinutesToHHMM(a.minutos_exceso_colacion) : '--:--',
            (a.minutos_permisos_detectados > 0 || a.minutos_permiso_personal_deuda > 0) ? formatMinutesToHHMM((a.minutos_permisos_detectados || 0) + (a.minutos_permiso_personal_deuda || 0)) : (a.permiso_activo ? 'Día Completo' : '--:--'),
            a.minutos_deuda > 0 ? formatMinutesToHHMM(a.minutos_deuda) : '--:--'
        ];
    });

    // AutoTable usando los datos directamente
    doc.autoTable({
        head: [
            [
                { content: 'DATOS GENERALES', colSpan: 2, styles: { halign: 'center', fillColor: [230, 230, 230] } },
                { content: 'MARCACIONES', colSpan: 6, styles: { halign: 'center', fillColor: [226, 240, 217] } },
                { content: 'TIEMPOS ACUMULADOS', colSpan: 3, styles: { halign: 'center', fillColor: [255, 242, 204] } },
                { content: 'DEUDAS E INCIDENCIAS', colSpan: 5, styles: { halign: 'center', fillColor: [252, 228, 214] } }
            ],
            ['Fecha', 'Estado', 'Entrada\nTurno', 'Inicio\nColación', 'Fin\nColación', 'Inicio\nPermiso', 'Fin\nPermiso', 'Salida\nTurno', 'Horas\nTrabajadas', 'Horas\nExtras', 'Total\nColación', 'ATRASOS', 'Salida\nAdelantada', 'Exceso\nColación', 'Permisos', 'Deuda']
        ],
        body: tableBody,
        startY: startY,
        theme: 'grid',
        styles: { font: 'helvetica', fontSize: 8, cellPadding: 4, halign: 'center' },
        headStyles: { fillColor: [240, 240, 240], textColor: [0, 0, 0], fontStyle: 'bold', halign: 'center' },
        columnStyles: {
            0: { halign: 'left', fontStyle: 'bold' }, // Fecha
            1: { halign: 'left' } // Estado
        },
        didParseCell: function(data) {
            // Condicional de color para Anomalías
            if (data.section === 'body' && data.column.index === 1) {
                const text = data.cell.text[0] || '';
                if (text === 'Inasistencia' || text.includes('FALTA')) {
                    data.cell.styles.textColor = [220, 53, 69]; // danger
                    data.cell.styles.fontStyle = 'bold';
                } else if (text.includes('Atraso') || text.includes('Salida Adelantada')) {
                    data.cell.styles.textColor = [253, 126, 20]; // warning
                } else if (text === 'Jornada Completa') {
                    data.cell.styles.textColor = [25, 135, 84]; // success
                } else if (text.toLowerCase().includes('feriado') || text.toLowerCase().includes('libre')) {
                    data.cell.styles.textColor = [13, 110, 253]; // blue for free/holiday
                }
            }
        },
        didDrawPage: function(data) {
            // Footer con paginación
            let str = 'Página ' + doc.internal.getNumberOfPages();
            doc.setFontSize(8);
            doc.setFont('helvetica', 'normal');
            doc.setTextColor(150);
            doc.text(str, data.settings.margin.left, doc.internal.pageSize.height - 20);
        }
    });

    // Cuadro Consolidado de métricas
    let finalY = doc.lastAutoTable.finalY + 20;

    if (finalY + 120 > doc.internal.pageSize.height) {
        doc.addPage();
        finalY = 40;
    }

    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);
    doc.setTextColor(0);
    doc.text("Resumen Consolidado del Período", 40, finalY);

    const formatDeuda = (mins) => {
        return formatExactMinutesToTime(mins);
    };

    const formatNeto = (mins) => {
        if (!mins || mins === 0) return '00:00:00';
        let sign = mins < 0 ? '-' : '+';
        let absMins = Math.abs(mins);
        return `${sign}${formatExactMinutesToTime(absMins)}`;
    };

    let saldoNetoMins = metrics.minutosHE_Aprobado - metrics.minutosDeuda;

    const summaryBody = [
        ['Días Trabajados', metrics.diasTrabajados],
        ['Atrasos', metrics.atrasosCount],
        ['Salidas Adelantadas', metrics.salidasAdelantadasCount],
        ['Deuda Total Bruta (HH:mm:ss)', formatDeuda(metrics.minutosDeuda)],
        ['Inasistencias', metrics.faltasCount],
        ['Justificaciones', metrics.justificacionesCount],
        ['Permisos', metrics.permisosCount],
        ['Jornadas Especiales', metrics.jornadasEspecialesCount],
        ['Horas Extras Brutas (HH:mm:ss)', formatDeuda(metrics.minutosHE_Aprobado)],
        ['Saldo Neto (HH:mm:ss)', formatNeto(saldoNetoMins)]
    ];

    doc.autoTable({
        startY: finalY + 10,
        body: summaryBody,
        theme: 'grid',
        tableWidth: 300,
        margin: { left: 40 },
        styles: { fontSize: 8, cellPadding: 3 },
        columnStyles: {
            0: { fontStyle: 'bold', fillColor: [245, 245, 245] },
            1: { halign: 'center' }
        }
    });

    finalY = doc.lastAutoTable.finalY + 50;

    // Validar espacio para firmas
    if (finalY + 50 > doc.internal.pageSize.height) {
        doc.addPage();
        finalY = 60;
    }

    doc.setTextColor(0);
    doc.setDrawColor(0);
    doc.setLineWidth(1);

    // Firmas calculadas dinámicamente según ancho de página
    const centerPoint = pageWidth / 2;
    
    // Firma Empleado (Izquierda)
    const leftMargin = centerPoint - 180;
    doc.line(leftMargin, finalY, leftMargin + 140, finalY);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(9);
    doc.text("Firma Empleado", leftMargin + 35, finalY + 15);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.text(`RUT: ${rut}`, leftMargin + 45, finalY + 25);

    // Firma Jefatura (Derecha)
    const rightMargin = centerPoint + 40;
    doc.line(rightMargin, finalY, rightMargin + 140, finalY);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(9);
    doc.text("Firma Jefatura / RRHH", rightMargin + 15, finalY + 15);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.text("Aguacol SpA", rightMargin + 45, finalY + 25);

    if (isDownload) {
        const safeArea = (area || 'SIN_AREA').replace(/[^a-zA-Z0-9_\-]/g, '_').toUpperCase();
        const safeNombre = nombreEmpleado.trim().replace(/\s+/g, '_').toUpperCase();
        let fInicio = stateMarcacionesApp.fechaInicioRRHH ? stateMarcacionesApp.fechaInicioRRHH.replace(/-/g, '') : 'INICIO';
        let fFin = stateMarcacionesApp.fechaFinRRHH ? stateMarcacionesApp.fechaFinRRHH.replace(/-/g, '') : 'FIN';
        const nombreArchivo = `${safeArea}_${safeNombre}_${fInicio}-${fFin}.pdf`;
        
        doc.save(nombreArchivo);
    } else {
        // FIX 5: Revocar blob URL anterior para evitar memory leak
        if (window._lastPdfBlobUrl) {
            URL.revokeObjectURL(window._lastPdfBlobUrl);
        }
        const blob = doc.output('blob');
        const url = URL.createObjectURL(blob);
        window._lastPdfBlobUrl = url;
        const container = document.getElementById('pdf-iframe-container');
        if (container) {
            container.innerHTML = `<iframe src="${url}" width="100%" height="800px" style="border: none; border-radius: 4px;"></iframe>`;
        }
    }
}

// Deprecated alias for compatibility with external calls if any
window.downloadReportPDF = function() {
    updateVisorPDF(true);
};


// ==========================================
// UTILIDADES DE VISTA
// ==========================================



// ── Helpers de vista única (mutuamente excluyentes) ──────────────────────────


// ── Función Maestra Universal (V15.0) ──────────────────────────
/**
 * Transforma minutos puros (decimales exactos sin truncar) en formato HH:MM:SS
 * protegiendo los cálculos matemáticos de errores visuales en PDF y UI.
 * @param {number} minsFloat 
 */
function formatExactMinutesToTime(minsFloat) {
    if (!minsFloat || minsFloat <= 0) return "00:00:00";
    const totalSecs = Math.round(minsFloat * 60);
    const h = Math.floor(totalSecs / 3600);
    const m = Math.floor((totalSecs % 3600) / 60);
    const s = totalSecs % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// Deprecated: Aliases redirigidos a la nueva función maestra
function formatDecimalToTime(decimalHours) {
    if (!decimalHours || decimalHours <= 0) return "00:00:00";
    return formatExactMinutesToTime(decimalHours * 60);
}

function formatMinutesToHHMM(totalMinutes) {
    return formatExactMinutesToTime(totalMinutes);
}
/**
 * Abre el modal de gestión de horas extra.
 */
function openHoraExtraModal(empleadoId, fecha, nombreEmpleado) {
    // Buscar los datos de este día en el estado global
    const empData = stateMarcacionesApp.data.matrix[empleadoId];
    const asist = empData ? empData[fecha] : null;

    if (!asist || !asist.minutos_extra_bruto) {
        showToast("Este día no tiene horas extra para revisar.", "info");
        return;
    }

    const mExtra = asist.minutos_extra_bruto;
    const mAuth = asist.minutos_extra_autorizados || 0;

    // Crear/Reutilizar modal
    let modalEl = document.getElementById('modal-aprobacion-he');
    if (!modalEl) {
        modalEl = document.createElement('div');
        modalEl.id = 'modal-aprobacion-he';
        // Guardar el valor exacto para usarlo al aprobar completo
        modalEl.dataset.brutoExacto = mExtra;

        const html = `
            <div class="modal-dialog modal-sm">
                <div class="modal-content shadow-lg border-0">
                    <div class="modal-header bg-primary text-white">
                        <h5 class="modal-title"><i class="bi bi-clock-history"></i> Aprobar Horas Extra</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="text-center mb-3">
                            <h6 class="text-muted small mb-1" id="he-modal-emp"></h6>
                            <div class="fw-bold" id="he-modal-fecha"></div>
                        </div>
                        
                        <div class="alert alert-info py-2 px-3 small">
                            <i class="bi bi-info-circle"></i> Total detectado: <strong id="he-modal-bruto-str"></strong>
                        </div>

                        <div class="mb-3">
                            <label for="input-he-minutos" class="form-label small">Modificar a (Minutos):</label>
                            <input type="number" id="input-he-minutos" class="form-control" step="any" placeholder="Ej: 120 para 2 horas">
                            <div class="form-text small text-muted">Deja el valor sugerido para aprobar completo.</div>
                        </div>

                        <div class="d-grid gap-2">
                            <button class="btn btn-success" id="btn-he-aprobar">
                                <i class="bi bi-check-circle"></i> Aprobar Total Completo
                            </button>
                            <button class="btn btn-outline-danger" id="btn-he-rechazar">
                                <i class="bi bi-x-circle"></i> Rechazar
                            </button>
                            <button class="btn btn-link btn-sm text-secondary" id="btn-he-pendiente">
                                Volver a Pendiente
                            </button>
                            <hr class="my-1">
                            <button type="button" class="btn btn-outline-danger btn-sm" id="btn-he-delete-manual" title="Elimina las marcaciones manuales creadas en este día">
                                <i class="bi bi-trash"></i> Eliminar Ingreso Manual
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        modalEl.classList.add('modal', 'fade');
        modalEl.setAttribute('tabindex', '-1');
        modalEl.innerHTML = html;
        document.body.appendChild(modalEl);
    } else {
        modalEl.dataset.brutoExacto = mExtra;
    }

    // Actualizar valores
    document.getElementById('he-modal-emp').innerText = nombreEmpleado;
    document.getElementById('he-modal-fecha').innerText = fecha;
    document.getElementById('he-modal-bruto-str').innerText = formatExactMinutesToTime(mExtra);
    
    // Si ya tiene autorizados, mostramos esos, sino mostramos el bruto exacto
    document.getElementById('input-he-minutos').value = mAuth || mExtra;
    document.getElementById('input-he-minutos').max = mExtra;

    // Asignar eventos dinámicos
    document.getElementById('btn-he-aprobar').onclick = () => confirmAprobacionHE(empleadoId, fecha, 'APROBADO', asist?.updated_at);
    document.getElementById('btn-he-rechazar').onclick = () => confirmAprobacionHE(empleadoId, fecha, 'RECHAZADO', asist?.updated_at);
    document.getElementById('btn-he-pendiente').onclick = () => confirmAprobacionHE(empleadoId, fecha, 'PENDIENTE', asist?.updated_at);

    const deleteManualBtn = document.getElementById('btn-he-delete-manual');
    if (deleteManualBtn) {
        deleteManualBtn.onclick = () => {
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
            if (typeof deleteManualJornada === 'function') {
                deleteManualJornada(empleadoId, fecha);
            } else {
                console.error("deleteManualJornada no está definida");
            }
        };
    }

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}
async function confirmAprobacionHE(empleadoId, fecha, estado, lastUpdatedAt) {
    const inputVal = parseFloat(document.getElementById('input-he-minutos').value);
    const brutoExacto = parseFloat(document.getElementById('modal-aprobacion-he').dataset.brutoExacto);
    
    // Si aprueba, por defecto enviamos el input, pero asegurándonos de que si el usuario no tocó nada (y tiene todo el bruto), mandamos el exacto.
    let minutos = inputVal;
    if (estado === 'APROBADO' && Math.abs(inputVal - brutoExacto) < 1) { 
        // Si la diferencia es menor a 1 minuto (ej. usuario tipea 125 para 125.55), y quería aprobar completo
        // Se envía el bruto exacto para no perder los segundos
        minutos = brutoExacto; 
    }

    try {
        const resp = await fetch('/api/asistencia/aprobar-he-batch/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify([{
                empleado_id: empleadoId,
                fecha: fecha,
                estado: estado,
                minutos_autorizados: estado === 'APROBADO' ? minutos : 0,
                last_updated_at: lastUpdatedAt || null
            }])
        });

        const result = await resp.json();
        if (resp.ok) {
            showToast(result.mensaje, "success");

            const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('modal-aprobacion-he'));
            modal.hide();

            // Recargar datos
            if (typeof window.loadMarcacionesData === 'function') {
                window.loadMarcacionesData();
            }
        } else {
            if (resp.status === 409) {
                // Conflicto de concurrencia
                showToast(result.detail, "error");
                // Forzar recarga inmediata para ver cambios externos
                if (typeof window.loadMarcacionesData === 'function') {
                    window.loadMarcacionesData();
                }
            } else {
                showToast(result.detail || "No se pudo guardar.", "error");
            }
        }
    } catch (e) {
        console.error("Error sincronizando BioAlba:", e);
        Avisos.sinConexion();
    }
}

/**
 * ── Auto-Detección de Cambios (Smart Polling) ──────────────────────────────
 * En lugar de recargar la grilla completa cada 60s (costoso),
 * polleamos un endpoint ultraligero (/api/asistencia/last-change/)
 * que solo retorna MAX(updated_at) + COUNT(*).
 * Solo recargamos la grilla cuando detectamos un cambio real.
 * 
 * @param {boolean} enabled 
 */

// Estado interno del change-detector
window._changeDetector = window._changeDetector || {
    lastUpdate: null,
    lastCount: null,
    intervalId: null,
    isChecking: false,
};

function toggleAutoRefresh(enabled, silent = false) {
    stateMarcacionesApp.autoRefreshEnabled = enabled;
    const cd = window._changeDetector;

    // Limpiar anterior si existe
    if (cd.intervalId) {
        clearInterval(cd.intervalId);
        cd.intervalId = null;
    }

    if (enabled) {
        console.log("🔄 Auto-detección activada (30s polling ligero)");
        if (!silent) {
            showToast("Detección automática de marcas encendida.", "info");
        }

        // Capturar el estado actual como baseline
        cd.lastUpdate = null;
        cd.lastCount = null;

        // Poll cada 30 segundos
        cd.intervalId = setInterval(() => _checkForChanges(), 30000);
        stateMarcacionesApp.autoRefreshIntervalId = cd.intervalId;

        // Primer check inmediato para establecer baseline
        _checkForChanges(true);
    } else {
        console.log("🛑 Auto-detección desactivada");
        showToast("Detección automática de marcas apagada.", "info");
        cd.lastUpdate = null;
        cd.lastCount = null;
    }
}

/**
 * Verifica si hubo cambios usando el endpoint ligero.
 * @param {boolean} isBaseline - true si es la primera llamada (solo captura estado, no recarga)
 */
async function _checkForChanges(isBaseline = false) {
    const cd = window._changeDetector;
    const state = stateMarcacionesApp;

    // No verificar si la página no está visible o no hay datos cargados
    const container = document.getElementById('page-marcaciones');
    if (!container || !container.classList.contains('active')) return;
    if (!state.fechaInicioRRHH || !state.fechaFinRRHH) return;
    if (cd.isChecking) return;

    cd.isChecking = true;

    try {
        let url = `/api/asistencia/last-change/?fecha_inicio=${state.fechaInicioRRHH}&fecha_fin=${state.fechaFinRRHH}`;
        if (state.area) url += `&area=${encodeURIComponent(state.area)}`;

        const resp = await fetch(url);
        if (!resp.ok) return;

        const data = await resp.json();
        const newUpdate = data.last_update;
        const newCount = data.total_records;

        if (isBaseline) {
            // Primer llamada: solo guardar como referencia
            cd.lastUpdate = newUpdate;
            cd.lastCount = newCount;
            console.log(`📡 Baseline capturado: updated=${newUpdate}, records=${newCount}`);
            return;
        }

        // Comparar con el estado anterior
        const hasChanged = (
            (cd.lastUpdate !== null && cd.lastUpdate !== newUpdate) ||
            (cd.lastCount !== null && cd.lastCount !== newCount)
        );

        if (hasChanged) {
            console.log(`🔔 Cambio detectado: updated ${cd.lastUpdate} → ${newUpdate}, records ${cd.lastCount} → ${newCount}`);
            
            // Actualizar referencia ANTES de recargar
            cd.lastUpdate = newUpdate;
            cd.lastCount = newCount;

            // Sin aviso: la recarga es silenciosa y conserva el scroll (un toast cada 30 s molestaba a quien estaba revisando la grilla).
            // Recargar la grilla
            if (typeof window.loadMarcacionesData === 'function') {
                window.loadMarcacionesData({ silent: true });
            }
        } else {
            // Sin cambios, solo actualizar referencia silenciosamente
            cd.lastUpdate = newUpdate;
            cd.lastCount = newCount;
        }

    } catch (e) {
        // Silencioso: no molestar al usuario si el endpoint falla
        console.debug('Change-detection poll error:', e.message);
    } finally {
        cd.isChecking = false;
    }
}

/**
 * Módulo de Aprobación Masiva de Horas Extra
 * Se abre al hacer doble clic en el nombre de un empleado en la grilla analítica
 */
window.openBatchApprovalModal = function (empleadoId, empNombreArg) {
    if (!stateMarcacionesApp.data || !stateMarcacionesApp.data.matrix || !stateMarcacionesApp.data.matrix[empleadoId]) {
        showToast("No se encontraron los datos de esta persona.", "error");
        return;
    }
    const empData = stateMarcacionesApp.data.matrix[empleadoId];
    
    // Buscar nombre del empleado
    let empNombre = empNombreArg || "Desconocido";
    if (empNombre === "Desconocido") {
        // Fallback: buscar en info o en cualquier día
        if (empData.info && empData.info.nombre_completo) {
            empNombre = empData.info.nombre_completo;
        } else {
            for (const key in empData) {
                if (empData[key]?.empleado) { empNombre = empData[key].empleado; break; }
            }
        }
    }

    if (empData && empData.info && (empData.info.tipo_programacion === 'BOLSA_FLEXIBLE' || empData.info.tipo_programacion === 'FLEXIBLE_BOLSA')) {
        showToast(`${empNombre} tiene turno de bolsa flexible: su saldo se revisa en la columna «Bolsa flexible» al cerrar el mes.`, 'info');
        return;
    }

    // 1. Determinar el rango de fechas dinámico
    let dates = [];
    if (stateMarcacionesApp.data && stateMarcacionesApp.data.periodo) {
        dates = window.getDatesInRange(stateMarcacionesApp.data.periodo.inicio, stateMarcacionesApp.data.periodo.fin);
    }

    // 2. Encontrar días con HE Detectada usando los campos correctos
    const diasHE = [];
    const dayNames = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
    dates.forEach(dateStr => {
        const di = empData[dateStr];
        if (!di) return;

        // Excluir días especiales para que no se sumen a la bolsa de HE normales
        const isEsp = di.estado === 'JORNADA_ESPECIAL' || di.estado === 'EXTRA' || di.estado === 'FERIADO Y JORNADA EXTRA' || di.estado === 'DÍA LIBRE Y JORNADA EXTRA' || (Number(di.horas_teoricas || 0) === 0 && Number(di.horas_trabajadas || 0) > 0);
        // Campo correcto: minutos_extra_bruto (usado en renderVistaAnalitica línea 2331)
        // Desde el 10-11-2026 las horas extra de un día especial (+2, llamado o la jornada especial pasada a horas extra)
        // se aprueban aquí como las demás
        const brutoPotencial = di._esBolsa ? 0 : (di.minutos_extra_bruto || 0);
        
        // El mínimo para contar hora extra lo aplica el motor con el ajuste de Configuración: toda la que existe se lista
        if (brutoPotencial > 0) {
            const dt = new Date(dateStr + 'T00:00:00');
            
            // --- CÁLCULO DE ORIGEN/CONTEXTO DE HORAS EXTRAS ---
            let contextoTags = [];
            
            // 1. Colación: Bajo regla canónica, tomar menos descanso no genera sobretiempo (omitido)
            
            // 2. Llegada Temprana Efectiva (Fuera del margen de anclaje)
            if (di.hora_entrada_teorica && di.hora_entrada_real) {
                let diffEntradaMin = Math.round(-window.circularTimeDiff(di.hora_entrada_teorica, di.hora_entrada_real)); 
                let obsLlegada = (di.observaciones || '').toLowerCase();
                // Verificamos si hay observación de que quedó FUERA del anclaje
                if (diffEntradaMin > 0 && obsLlegada.includes('llegada anticipada') && obsLlegada.includes('fuera del anclaje')) {
                    contextoTags.push(`<span class="badge bg-primary-subtle text-primary-emphasis border border-primary-subtle mb-1"><i class="bi bi-box-arrow-in-right"></i> +${formatExactMinutesToTime(diffEntradaMin)} (Ingreso Anticipado)</span>`);
                }
            }
            
            // 3. Salida Tardía Efectiva
            if (di.hora_salida_teorica && di.hora_salida_real) {
                let diffSalidaMin = Math.round(window.circularTimeDiff(di.hora_salida_teorica, di.hora_salida_real));
                let obsSalida = (di.observaciones || '').toLowerCase();
                // Si salió tarde y no fue anclado (es decir, el tiempo real se mantuvo y generó horas)
                if (diffSalidaMin > 0 && !obsSalida.includes('salida dentro del anclaje')) {
                    contextoTags.push(`<span class="badge bg-primary-subtle text-primary-emphasis border border-primary-subtle mb-1"><i class="bi bi-box-arrow-right"></i> +${formatExactMinutesToTime(diffSalidaMin)} (Salida Tardía)</span>`);
                }
            }
            
            // 4. Desglose: cuánto viene de un +2, de un llamado o de la jornada especial pasada a horas extra (dueño, 10-11-2026)
            const deMas2 = Number(di.minutos_extra_mas2 || 0), deLlam = Number(di.minutos_extra_llamado || 0), deEsp = Number(di.minutos_extra_esp || 0);
            const emeCfgHE = (window._estadosAsistencia || {})['LLAMADO_EMERGENCIA'] || {};
            const espCfgHE = (window._estadosAsistencia || {})['JORNADA_ESPECIAL'] || {};
            if (deMas2 > 0) contextoTags.push(`<span class="badge he-de he-de-mas2 mb-1"><i class="bi bi-plus-lg" aria-hidden="true"></i> ${formatExactMinutesToTime(deMas2)} de +2</span>`);
            if (deLlam > 0) contextoTags.push(`<span class="badge he-de mb-1"><i class="bi ${window._rvEsc(emeCfgHE.icono_bi || 'bi-telephone-inbound-fill')}" aria-hidden="true"></i> ${formatExactMinutesToTime(deLlam)} de ${window._rvEsc(emeCfgHE.short_label || 'EME')}</span>`);
            if (deEsp > 0) contextoTags.push(`<span class="badge he-de mb-1"><i class="bi ${window._rvEsc(espCfgHE.icono_bi || 'bi-star-fill')}" aria-hidden="true"></i> ${formatExactMinutesToTime(deEsp)} de ${window._rvEsc(espCfgHE.short_label || 'ESP')}</span>`);
            const normales = Math.max(0, brutoPotencial - deMas2 - deLlam - deEsp);
            if ((deMas2 || deLlam || deEsp) && normales >= 1) contextoTags.push(`<span class="badge he-de mb-1">${formatExactMinutesToTime(normales)} normales</span>`);
            else if (isEsp && !(deMas2 || deLlam || deEsp)) {
                contextoTags.push(`<span class="badge bg-success-subtle text-success-emphasis border border-success-subtle mb-1"><i class="bi bi-star-fill"></i> Jornada en Día Libre</span>`);
            }
            
            // Fallback si no identificó nada específico pero hay horas extras
            if (contextoTags.length === 0) {
                contextoTags.push(`<span class="text-muted small">Exceso de jornada</span>`);
            }
            // -----------------------------------------------------

            diasHE.push({
                fecha: dateStr,
                fechaLabel: `${dayNames[dt.getDay()]} ${dt.getDate()}-${String(dt.getMonth()+1).padStart(2,'0')}`,
                bruto: brutoPotencial,
                autorizados: di.minutos_extra_autorizados || 0,
                estado: (di.estado_he === 'N/A' || !di.estado_he) ? 'PENDIENTE' : di.estado_he,
                hora_entrada: di.hora_entrada_real || '--',
                hora_salida: di.hora_salida_real || '--',
                contexto: contextoTags.join('<br>')
            });
        }
    });

    // Calcular totales
    const totalBruto = diasHE.reduce((s, d) => s + d.bruto, 0);
    const totalAprobado = diasHE.filter(d => d.estado === 'APROBADO').reduce((s, d) => s + (d.autorizados || d.bruto), 0);
    const totalPendiente = diasHE.filter(d => d.estado === 'PENDIENTE').reduce((s, d) => s + d.bruto, 0);
    const totalRechazado = diasHE.filter(d => d.estado === 'RECHAZADO').reduce((s, d) => s + d.bruto, 0);

    if (diasHE.length === 0) {
        showToast(`${empNombre} no tiene horas extra en este período.`, 'info');
        return;
    }

    // Calcular estadísticas globales del empleado para conocer su Saldo Neto y Deuda real
    const empRaw = (stateMarcacionesApp.empleados || []).find(e => e.id === Number(empleadoId)) || {};
    const info = empData.info || empRaw;
    const empObject = {
        id: empleadoId, info,
        nombre_completo: info.nombre_completo || empRaw.nombre_completo || empRaw.nombre || empNombre,
        area: info.area || empRaw.area || '',
        turno: info.turno || info.nombre_turno || '',
        turno_dias: info.turno_dias || {},
        tipo_programacion: info.tipo_programacion || '',
        activo: info.activo !== false,
        dias: empData
    };
    const feriadosArray = stateMarcacionesApp.data && stateMarcacionesApp.data.feriados 
        ? stateMarcacionesApp.data.feriados.map(f => f.fecha || f) 
        : [];
    let empStats = { saldo: 0, d_tot: 0, he_apr: 0, he_pend: 0, he_rec: 0, he_compensado: 0 };
    if (typeof window.calcularStatsEmpleado === 'function') {
        try {
            empStats = window.calcularStatsEmpleado(empObject, dates, feriadosArray);
        } catch(e) {
            console.warn("No se pudo calcular stats de empleado:", e);
        }
    }

    const rawSaldoMin = empStats.saldo || 0;
    const isCurrentSaldoZero = Math.abs(rawSaldoMin) < 0.0083;
    const currentSaldoColor = isCurrentSaldoZero ? '#475569' : (rawSaldoMin > 0 ? '#15803d' : '#b91c1c');
    const currentSaldoBg = isCurrentSaldoZero ? '#f1f5f9' : (rawSaldoMin > 0 ? '#dcfce7' : '#fee2e2');
    const saldoSign = isCurrentSaldoZero ? '' : (rawSaldoMin > 0 ? '+' : '-');
    const currentSaldoStr = isCurrentSaldoZero ? '00:00:00' : `${saldoSign}${formatExactMinutesToTime(Math.abs(rawSaldoMin))}`;
    const deudaTotalMin = (empStats.d_tot || 0);
    const deudaTotalStr = formatExactMinutesToTime(deudaTotalMin);

    const deudaCompensarMin = deudaTotalMin + (empStats.he_compensado || 0);
    const saldoPotencialBruto = totalBruto - deudaCompensarMin;
    const tieneSaldoPositivo = saldoPotencialBruto > 0.0083;
    const horasEnterasRedondas = tieneSaldoPositivo ? Math.floor(saldoPotencialBruto / 60) : 0;
    const labelRedondeoHora = (tieneSaldoPositivo && horasEnterasRedondas > 0)
        ? `+${String(horasEnterasRedondas).padStart(2,'0')}:00:00`
        : null;

    const bloquesMediaHora = tieneSaldoPositivo ? Math.floor(saldoPotencialBruto / 30) : 0;
    const minutosMediaHora = bloquesMediaHora * 30;
    const esDiferenteDeHora = (minutosMediaHora !== horasEnterasRedondas * 60);
    const labelRedondeoMedia = (tieneSaldoPositivo && esDiferenteDeHora && bloquesMediaHora > 0)
        ? `+${String(Math.floor(minutosMediaHora / 60)).padStart(2,'0')}:${String(minutosMediaHora % 60).padStart(2,'0')}:00`
        : null;

    // ─── MOTOR DE RECOMENDACIÓN INTELIGENTE (COPILOTO DE ASISTENCIA) ──────
    let estrategiaSugerida = 'cero'; // 'cero' | 'todo' | 'redondeo'
    let motivoSugerencia = '';
    let badgeSugerencia = '';

    if (deudaCompensarMin > 0.0083 && totalBruto >= deudaCompensarMin - 0.0083) {
        // Caso 1: Con deuda y sobretiempo suficiente para cubrirla (Gana-Gana)
        estrategiaSugerida = 'cero';
        badgeSugerencia = 'RECOMENDACIÓN ÓPTIMA (Art. 32 Código del Trabajo)';
        const remanenteMin = totalBruto - deudaCompensarMin;
        motivoSugerencia = `<strong>${empNombre}</strong> acumula <strong>${formatExactMinutesToTime(deudaCompensarMin)}</strong> de atrasos y dispone de <strong>${formatExactMinutesToTime(totalBruto)}</strong> de sobretiempo. Se sugiere <strong>1. Compensar Deuda (Saldo Cero)</strong> para absorber sus atrasos a costo $0 para él (Art. 32 CT), liberando además <strong>+${formatExactMinutesToTime(remanenteMin)}</strong> a su favor para pago o descanso.`;
    } else if (deudaCompensarMin <= 0.0083 && totalBruto > 0) {
        // Caso 2: Trabajador puntual sin deuda pendiente
        estrategiaSugerida = 'todo';
        badgeSugerencia = 'RECOMENDACIÓN LEGAL DT (Pago Íntegro 100%)';
        motivoSugerencia = `<strong>${empNombre}</strong> no registra atrasos ni deuda de tiempo no trabajado. Conforme a la doctrina de la Dirección del Trabajo (DT), se recomienda <strong>2. Pagar Todo (100% Íntegro)</strong> autorizando sus <strong>+${formatExactMinutesToTime(totalBruto)}</strong> sin deducciones.`;
    } else if (deudaCompensarMin > totalBruto && totalBruto > 0) {
        // Caso 3: Deuda supera el sobretiempo disponible
        estrategiaSugerida = 'cero';
        badgeSugerencia = 'RECOMENDACIÓN: AMORTIZACIÓN MÁXIMA';
        const deficitMin = deudaCompensarMin - totalBruto;
        motivoSugerencia = `La deuda por atrasos (<strong>${formatExactMinutesToTime(deudaCompensarMin)}</strong>) supera el sobretiempo detectado (<strong>${formatExactMinutesToTime(totalBruto)}</strong>). Se sugiere <strong>Compensar al Máximo</strong> para amortizar toda la deuda posible; el saldo por descontar se reduce a solo <strong>-${formatExactMinutesToTime(deficitMin)}</strong>.`;
    } else {
        estrategiaSugerida = 'cero';
        badgeSugerencia = 'ANÁLISIS DE JORNADA';
        motivoSugerencia = `Revisa las jornadas registradas y selecciona la estrategia operativa adecuada para balancear el ciclo de asistencia.`;
    }

    const canApproveHE = typeof AuthService !== 'undefined' && AuthService.hasPermission("marcaciones.horas_extras");

    // 3. Construir filas de la tabla
    const heRows = diasHE.map(d => {
        const estadoBadge = d.estado === 'APROBADO' ? '<span class="badge bg-success" id="badge-st-' + d.fecha + '"><i class="bi bi-check-circle-fill text-success" aria-hidden="true"></i> Aprobado</span>' :
                           d.estado === 'RECHAZADO' ? '<span class="badge bg-danger" id="badge-st-' + d.fecha + '"><i class="bi bi-x-circle-fill text-danger" aria-hidden="true"></i> Rechazado</span>' :
                           '<span class="badge bg-warning text-dark" id="badge-st-' + d.fecha + '"><i class="bi bi-hourglass-split" aria-hidden="true"></i> Pendiente</span>';
        const checked = (d.estado === 'PENDIENTE' || d.estado === 'APROBADO') ? 'checked' : '';
        const checkboxHtml = canApproveHE 
            ? `<input class="form-check-input check-item-he" type="checkbox" id="chk-he-${d.fecha}" data-fecha="${d.fecha}" data-minutos="${d.bruto}" ${checked} onchange="window.onRowHEChecked('${d.fecha}')">`
            : `<input class="form-check-input check-item-he" type="checkbox" disabled>`;
        
        const defaultMinutosAut = d.estado === 'APROBADO' ? (d.autorizados !== undefined ? d.autorizados : d.bruto) : d.bruto;
        
        const controlHtml = canApproveHE
            ? `
                <div class="d-flex align-items-center justify-content-center gap-1">
                    <select class="form-select form-select-sm select-row-estado py-0 px-2 fw-semibold shadow-xs" id="sel-estado-${d.fecha}" data-fecha="${d.fecha}" data-bruto="${d.bruto}" style="font-size:0.75rem; width:100px; height:26px; border-radius:5px;" onchange="window.onRowHEChange('${d.fecha}')">
                        <option value="APROBADO" ${d.estado === 'APROBADO' ? 'selected' : ''}>Aprobar</option>
                        <option value="PENDIENTE" ${d.estado === 'PENDIENTE' ? 'selected' : ''}>Pendiente</option>
                        <option value="RECHAZADO" ${d.estado === 'RECHAZADO' ? 'selected' : ''}>Rechazar</option>
                    </select>
                    <input type="text" class="form-control form-control-sm text-center font-monospace input-row-time fw-bold py-0 px-1 ${d.estado !== 'APROBADO' ? 'opacity-50' : ''}" id="input-time-${d.fecha}" data-fecha="${d.fecha}" data-bruto="${d.bruto}" value="${d.estado === 'RECHAZADO' ? '00:00:00' : formatExactMinutesToTime(defaultMinutosAut)}" ${d.estado !== 'APROBADO' ? 'disabled' : ''} style="font-size:0.75rem; width:72px; height:26px;" title="Tiempo autorizado (HH:MM:SS)" onchange="window.onRowTimeChange('${d.fecha}')">
                    <input type="hidden" class="input-row-minutos" id="input-min-${d.fecha}" data-fecha="${d.fecha}" data-bruto="${d.bruto}" value="${d.estado === 'RECHAZADO' ? 0 : defaultMinutosAut}">
                </div>
              `
            : `<span class="text-muted">—</span>`;

        return `<tr class="he-approval-row ${d.estado === 'PENDIENTE' ? 'table-warning-subtle' : ''}" id="row-he-${d.fecha}" data-fecha="${d.fecha}" data-bruto="${d.bruto}" data-estado-orig="${d.estado}">
            <td class="text-center align-middle">${checkboxHtml}</td>
            <td class="fw-semibold align-middle">${d.fechaLabel}</td>
            <td class="font-monospace text-center align-middle">${d.hora_entrada}</td>
            <td class="font-monospace text-center align-middle">${d.hora_salida}</td>
            <td class="fw-bold text-center align-middle" style="color:#1e40af">${formatExactMinutesToTime(d.bruto)}</td>
            <td style="font-size: 0.75rem; line-height: 1.2;" class="align-middle">${d.contexto}</td>
            <td class="font-monospace text-center align-middle fw-bold cell-he-acumulado" id="acum-he-${d.fecha}" style="font-size:0.78rem;color:#0f766e;">—</td>
            <td class="text-center align-middle">${estadoBadge}</td>
            <td class="text-center align-middle">${controlHtml}</td>
        </tr>`;
    }).join('');

    // 4. Crear Modal
    const modalId = 'modalBatchHE';
    let existing = document.getElementById(modalId);
    if (existing) existing.remove();

    const modalHtml = `
        <div class="modal fade" id="${modalId}" tabindex="-1" data-saldo-actual="${rawSaldoMin}" data-deuda-total="${deudaTotalMin}" data-compensado="${empStats.he_compensado || 0}">
            <div class="modal-dialog modal-xl modal-dialog-centered modal-dialog-scrollable">
                <div class="modal-content border-0 shadow-lg" style="border-radius:16px;overflow:hidden">
                    <div class="modal-header border-0 pb-0" style="background:linear-gradient(135deg,#eaf0fb 0%,#dfe8fb 100%);padding:18px 24px 14px">
                        <div>
                            <h5 class="modal-title fw-bold mb-1" style="color:#1e293b">
                                <i class="bi bi-clock-history text-primary me-2"></i>Gestión y Cuadre de Horas Extra
                            </h5>
                            <p class="mb-0 text-muted" style="font-size:0.82rem">
                                <i class="bi bi-person-fill me-1"></i>${empNombre}
                                <span class="mx-2">·</span>
                                <span class="fw-semibold">${diasHE.length}</span> jornadas con HE detectada
                                <span class="mx-2">·</span>
                                Total Bruto Detectado: <span class="fw-bold text-primary">${formatExactMinutesToTime(totalBruto)}</span>
                            </p>
                        </div>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    
                    <div class="modal-body p-0">
                        <!-- KPI BAR & SMART BALANCING ASSISTANT -->
                        <div class="p-3 bg-light border-bottom">
                            <!-- BALANZA DE MASA (ORDEN MATEMÁTICO: ENTRADA − SALIDA = BALANCE | INVENTARIO) -->
                            <div class="row g-2 mb-3 align-items-stretch">
                                <!-- 1. ENTRADA (+) : HE Aprobadas -->
                                <div class="col-md-3 col-6">
                                    <div class="p-2 rounded bg-white border text-center shadow-sm h-100 position-relative" style="border-top: 3px solid #16a34a !important;">
                                        <div class="d-flex align-items-center justify-content-center gap-1 mb-1">
                                            <span class="badge bg-success-subtle text-success fw-bold px-1.5 py-0.5 rounded" style="font-size: 0.75rem;">
                                                <i class="bi bi-plus-circle me-1"></i>A Favor (+)
                                            </span>
                                            <span class="text-muted small fw-semibold" style="font-size:0.75rem;">HE Aprobadas</span>
                                        </div>
                                        <div class="fs-5 fw-bold text-success" id="kpi-he-aprobadas">${formatExactMinutesToTime(totalAprobado)}</div>
                                        <div class="text-muted" style="font-size: 0.75rem;">Tiempo extra ganado</div>
                                    </div>
                                </div>

                                <!-- 2. SALIDA (−) : Deuda Tiempo No Trabajado -->
                                <div class="col-md-3 col-6">
                                    <div class="p-2 rounded bg-white border text-center shadow-sm h-100 position-relative" style="border-top: 3px solid #dc2626 !important;">
                                        <div class="d-flex align-items-center justify-content-center gap-1 mb-1">
                                            <span class="badge bg-danger-subtle text-danger fw-bold px-1.5 py-0.5 rounded" style="font-size: 0.75rem;">
                                                <i class="bi bi-dash-circle me-1"></i>Atrasos (−)
                                            </span>
                                            <span class="text-muted small fw-semibold" style="font-size:0.75rem;">Deuda No Trab.</span>
                                        </div>
                                        <div class="fs-5 fw-bold text-danger" id="kpi-deuda-tiempo">${deudaTotalStr}</div>
                                        <div class="text-muted" style="font-size: 0.75rem;">Atrasos y salidas anticipadas</div>
                                    </div>
                                </div>

                                <!-- 3. BALANCE (=) : Saldo Neto Actual -->
                                <div class="col-md-3 col-6">
                                    <div class="p-2 rounded border text-center shadow-sm h-100 position-relative" id="card-saldo-neto-actual" style="background:${currentSaldoBg}; border-color:${currentSaldoColor}50 !important; border-top: 3px solid ${currentSaldoColor} !important;">
                                        <div class="d-flex align-items-center justify-content-center gap-1 mb-1">
                                            <span class="badge fw-bold px-1.5 py-0.5 rounded" style="font-size: 0.75rem; background: ${currentSaldoColor}20; color:${currentSaldoColor}">
                                                <i class="bi bi-calculator me-1"></i>Balance (=)
                                            </span>
                                            <span class="text-muted small fw-semibold" style="font-size:0.75rem;">Saldo Neto Actual</span>
                                        </div>
                                        <div class="fs-5 fw-bold" id="kpi-saldo-neto" style="color:${currentSaldoColor}">${currentSaldoStr}</div>
                                        <div class="text-muted" style="font-size: 0.75rem;">Resultado nómina (+ / −)</div>
                                    </div>
                                </div>

                                <!-- 4. INVENTARIO (📦) : Bolsa Pendiente / Rechazado -->
                                <div class="col-md-3 col-6">
                                    <div class="p-2 rounded bg-white border text-center shadow-sm h-100 position-relative" style="border-top: 3px solid #f59e0b !important;">
                                        <div class="d-flex align-items-center justify-content-center gap-1 mb-1">
                                            <span class="badge bg-warning-subtle text-warning-emphasis fw-bold px-1.5 py-0.5 rounded" style="font-size: 0.75rem;">
                                                <i class="bi bi-inbox me-1"></i>Inventario
                                            </span>
                                            <span class="text-muted small fw-semibold" style="font-size:0.75rem;">Bolsa (Pend / Rech)</span>
                                        </div>
                                        <div class="fs-6 fw-bold text-warning pt-1" id="kpi-bolsa-remanente">
                                            ${formatExactMinutesToTime(totalPendiente)} <span class="text-muted fw-normal" style="font-size:0.75rem;">/ ${formatExactMinutesToTime(totalRechazado)}</span>
                                        </div>
                                        <div class="text-muted" style="font-size: 0.75rem;">Por auditar / Descartadas</div>
                                    </div>
                                </div>
                            </div>

                            <!-- ASISTENTE DE CUADRE CARD (ESTRATEGIA EN 3 CLICS) -->
                            ${canApproveHE ? `
                            <div class="card border-0 shadow-sm mb-3" style="border-radius:12px; background: #ffffff; border: 1px solid #cbd5e1 !important;">
                                <div class="card-header bg-white border-bottom py-2 px-3 d-flex align-items-center justify-content-between">
                                    <div class="d-flex align-items-center gap-2">
                                        <span class="badge bg-primary-subtle text-primary border border-primary-subtle px-2 py-1 fw-bold" style="font-size:0.75rem;">
                                            <i class="bi bi-magic me-1"></i> Asistente de Cuadre y Balance
                                        </span>
                                        <small class="text-muted" style="font-size:0.75rem;">Selecciona una estrategia operativa con 1 solo clic:</small>
                                    </div>
                                    <div class="d-flex align-items-center gap-2">
                                        <button class="btn btn-xs btn-outline-secondary py-1 px-2 text-decoration-none" style="font-size: 0.75rem; border-radius:6px;" type="button" data-bs-toggle="collapse" data-bs-target="#panel-avanzado-he">
                                            <i class="bi bi-sliders me-1"></i>Ajuste Manual / Metas
                                        </button>
                                        <button class="btn btn-xs btn-outline-danger py-1 px-2" style="font-size: 0.75rem; border-radius:6px;" type="button" onclick="window.ejecutarCuadreRapido(${empleadoId}, 'rechazar_todo')" title="Rechazar todas las jornadas y dejar horas extras en cero">
                                            <i class="bi bi-x-circle me-1"></i>Rechazar Todo
                                        </button>
                                    </div>
                                </div>
                                
                                <div class="card-body p-3">
                                    <!-- BANNER DIAGNÓSTICO COPILOTO -->
                                    <div class="alert alert-light border p-2 mb-3 d-flex align-items-center gap-2 shadow-xs" style="background: #f8fafc; border-left: 4px solid #0284c7 !important; border-radius: 8px;">
                                        <div class="d-flex align-items-center justify-content-center bg-primary-subtle text-primary rounded-circle" style="width:34px; height:34px; min-width:34px;">
                                            <i class="bi bi-robot fs-5"></i>
                                        </div>
                                        <div class="flex-grow-1" style="font-size: 0.77rem; line-height: 1.3;">
                                            <div class="d-flex align-items-center gap-2 mb-0.5">
                                                <span class="badge bg-primary text-white fw-bold px-2 py-0.5" style="font-size: 0.75rem;">COPILOTO DE ASISTENCIA</span>
                                                <span class="text-primary fw-semibold" style="font-size: 0.75rem;">Diagnóstico Automático</span>
                                            </div>
                                            <div class="text-dark">
                                                ${motivoSugerencia}
                                            </div>
                                        </div>
                                    </div>

                                    <!-- 3 ESTRATEGIAS PRINCIPALES EN TARJETAS LIMPIAS -->
                                    <div class="row g-2 mb-2">
                                        <!-- Estrategia 1: Compensar Deuda (Saldo Cero) -->
                                        <div class="col-md-4">
                                            <button type="button" class="btn w-100 p-2 text-start shadow-sm btn-estrategia-he h-100 position-relative" id="btn-est-cero" onclick="window.ejecutarCuadreRapido(${empleadoId}, 'cero')" style="border-radius:10px; border-width: ${estrategiaSugerida === 'cero' ? '2px' : '1.5px'};">
                                                ${estrategiaSugerida === 'cero' ? `
                                                <div class="position-absolute top-0 end-0 translate-middle-y me-2" style="z-index: 2;">
                                                    <span class="badge badge-recomendado bg-warning text-dark border border-warning shadow-xs fw-bold px-2 py-0.5" style="font-size: 0.75rem;">
                                                        <i class="bi bi-star-fill text-dark me-1"></i>RECOMENDADO
                                                    </span>
                                                </div>
                                                ` : ''}
                                                <div class="d-flex align-items-center gap-2 mb-1">
                                                    <span class="badge est-icon-badge bg-success text-white p-1 rounded-circle"><i class="bi bi-bullseye fs-6"></i></span>
                                                    <strong class="est-title text-success" style="font-size:0.83rem;">1. Compensar Deuda (Saldo Cero)</strong>
                                                </div>
                                                <div class="est-desc text-muted small" style="font-size: 0.75rem; line-height: 1.2;">
                                                    Absorbe atrasos exactos. Saldo neto resultante: <strong>00:00:00</strong>.
                                                </div>
                                            </button>
                                        </div>

                                        <!-- Estrategia 2: Pagar Todo (Norma Legal DT) -->
                                        <div class="col-md-4">
                                            <button type="button" class="btn w-100 p-2 text-start shadow-sm btn-estrategia-he h-100 position-relative" id="btn-est-todo" onclick="window.ejecutarCuadreRapido(${empleadoId}, 'aprobar_todo')" style="border-radius:10px; border-width: ${estrategiaSugerida === 'todo' ? '2px' : '1.5px'};">
                                                ${estrategiaSugerida === 'todo' ? `
                                                <div class="position-absolute top-0 end-0 translate-middle-y me-2" style="z-index: 2;">
                                                    <span class="badge badge-recomendado bg-warning text-dark border border-warning shadow-xs fw-bold px-2 py-0.5" style="font-size: 0.75rem;">
                                                        <i class="bi bi-star-fill text-dark me-1"></i>RECOMENDADO
                                                    </span>
                                                </div>
                                                ` : ''}
                                                <div class="d-flex align-items-center gap-2 mb-1">
                                                    <span class="badge est-icon-badge bg-primary text-white p-1 rounded-circle"><i class="bi bi-shield-check fs-6"></i></span>
                                                    <strong class="est-title text-primary" style="font-size:0.83rem;">2. Pagar Todo (Norma Legal DT)</strong>
                                                </div>
                                                <div class="est-desc text-muted small" style="font-size: 0.75rem; line-height: 1.2;">
                                                    Autoriza el 100% de minutos efectivos trabajados sin recortes.
                                                </div>
                                            </button>
                                        </div>

                                        <!-- Estrategia 3: Bloques Nómina (+HH:00 o +HH:30) -->
                                        <div class="col-md-4">
                                            <div class="dropdown h-100 position-relative">
                                                <button type="button" class="btn text-dark w-100 p-2 text-start shadow-sm btn-estrategia-he h-100 dropdown-toggle" id="btn-est-redondeo" data-bs-toggle="dropdown" aria-expanded="false" style="border-radius:10px; border-width: 1.5px;">
                                                    <div class="d-flex align-items-center gap-2 mb-1">
                                                        <span class="badge est-icon-badge bg-warning text-dark p-1 rounded-circle"><i class="bi bi-cash-coin fs-6"></i></span>
                                                        <strong class="est-title text-dark" style="font-size:0.83rem;">3. Bloques Nómina (Redondeo)</strong>
                                                    </div>
                                                    <div class="est-desc text-muted small" style="font-size: 0.75rem; line-height: 1.2;">
                                                        Paga horas redondas (+HH:00 / :30) y remanente a banco de tiempo.
                                                    </div>
                                                </button>
                                                <ul class="dropdown-menu dropdown-menu-end shadow border-0 p-1" style="border-radius:8px;">
                                                    ${labelRedondeoHora ? `
                                                    <li>
                                                        <a class="dropdown-item py-2 small fw-semibold" href="javascript:void(0)" onclick="window.ejecutarCuadreRapido(${empleadoId}, 'redondear_hora')">
                                                            <i class="bi bi-hourglass-split me-1 text-warning"></i> Redondear a Horas Enteras (${labelRedondeoHora})
                                                        </a>
                                                    </li>
                                                    ` : ''}
                                                    ${labelRedondeoMedia ? `
                                                    <li>
                                                        <a class="dropdown-item py-2 small fw-semibold" href="javascript:void(0)" onclick="window.ejecutarCuadreRapido(${empleadoId}, 'redondear_media')">
                                                            <i class="bi bi-clock me-1 text-primary"></i> Redondear a Medias Horas (${labelRedondeoMedia})
                                                        </a>
                                                    </li>
                                                    ` : ''}
                                                    ${(!labelRedondeoHora && !labelRedondeoMedia) ? `
                                                    <li><span class="dropdown-item-text text-muted small">No hay saldo positivo suficiente para redondear.</span></li>
                                                    ` : ''}
                                                </ul>
                                            </div>
                                        </div>
                                    </div>

                                    <!-- PANEL AVANZADO COLAPSABLE -->
                                    <div class="collapse pt-2 border-top mb-2" id="panel-avanzado-he">
                                        <div class="row g-2 align-items-center">
                                            <div class="col-md-5">
                                                <label class="form-label small text-muted mb-1 fw-semibold">Saldo Neto Objetivo (+HH:mm:ss)</label>
                                                <div class="input-group input-group-sm">
                                                    <span class="input-group-text bg-white">+</span>
                                                    <input type="text" class="form-control form-control-sm text-center fw-bold text-primary" id="asistente-horas-objetivo" placeholder="08:00:00" value="${labelRedondeoHora ? labelRedondeoHora.replace('+','') : '02:00:00'}">
                                                    <button class="btn btn-outline-primary btn-sm" type="button" onclick="window.ejecutarCuadreRapido(${empleadoId}, 'saldo_objetivo')">
                                                        Fijar Meta
                                                    </button>
                                                </div>
                                            </div>
                                            <div class="col-md-7">
                                                <div class="form-check form-switch mt-3">
                                                    <input class="form-check-input" type="checkbox" id="chk-incluir-rechazadas" checked onchange="window.ejecutarCuadreRapido(${empleadoId}, 'cero')">
                                                    <label class="form-check-label small fw-semibold text-dark" for="chk-incluir-rechazadas">
                                                        Rescatar de RECHAZADAS si falta (Siempre Activo por defecto)
                                                    </label>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <!-- FEEDBACK MESSAGE & BOTÓN PRINCIPAL UNIFICADO -->
                                    <div class="d-flex align-items-center justify-content-between flex-wrap gap-2 pt-2 border-top" id="asistente-feedback-container">
                                        <div id="asistente-feedback" class="flex-grow-1">
                                            <div class="small text-muted">
                                                <i class="bi bi-lightbulb" aria-hidden="true"></i> Haz clic en una de las <strong>3 Estrategias</strong> arriba para previsualizar el cuadre y luego presiona <strong>"Confirmar y Guardar"</strong>.
                                            </div>
                                        </div>
                                        <div>
                                            <button class="btn btn-success fw-bold px-4 py-2 shadow-sm d-flex align-items-center gap-2" type="button" id="btn-aplicar-cuadre" disabled onclick="window.aplicarCuadreHE(${empleadoId})" style="border-radius:8px;">
                                                <i class="bi bi-floppy-fill fs-5"></i>
                                                <div class="text-start">
                                                    <div style="line-height:1.1;">Confirmar y Guardar en BD</div>
                                                    <small class="fw-normal opacity-75" style="font-size: 0.75rem;">Registra en base de datos PostgreSQL</small>
                                                </div>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            ` : ''}
                        </div>

                        <!-- BARRA SUPERIOR DE TABLA -->
                        <div class="px-3 py-2 bg-light border-bottom d-flex justify-content-between align-items-center flex-wrap gap-2" style="font-size:0.8rem">
                            <div class="d-flex align-items-center gap-2">
                                <input type="checkbox" class="form-check-input" id="check-all-he" checked ${canApproveHE ? '' : 'disabled'} onchange="toggleAllHECells(this)">
                                <label for="check-all-he" class="form-check-label fw-semibold">Seleccionar todas las jornadas</label>
                            </div>
                            <div class="text-muted small">
                                <i class="bi bi-info-circle me-1 text-primary"></i>Cada cambio en la tabla actualiza el saldo neto proyectado en vivo.
                            </div>
                        </div>

                        <!-- TABLA DE DETALLE POR JORNADA -->
                        <div class="table-responsive" style="max-height:420px;overflow-y:auto">
                            <table class="table table-sm table-hover align-middle mb-0 he-approval-table">
                                <thead class="table-light sticky-top" style="z-index:10">
                                    <tr>
                                        <th style="width:40px" class="text-center"><i class="bi bi-check2-square"></i></th>
                                        <th>Fecha</th>
                                        <th class="text-center">Entrada</th>
                                        <th class="text-center">Salida</th>
                                        <th class="text-center">HE Bruto</th>
                                        <th style="min-width: 140px;">Origen / Motivo</th>
                                        <th class="text-center" style="min-width: 110px;" title="Horas acumuladas progresivamente según las jornadas seleccionadas">Acumulado <i class="bi bi-calculator" aria-hidden="true"></i></th>
                                        <th class="text-center">Estado Actual</th>
                                        <th class="text-center" style="min-width: 185px;">Acción / Autorizar</th>
                                    </tr>
                                </thead>
                                <tbody>${heRows}</tbody>
                                <tfoot class="table-light sticky-bottom fw-bold" style="position:sticky; bottom:0; z-index:10; background:#f8fafc; border-top:2px solid #cbd5e1; font-size:0.78rem;">
                                    <tr>
                                        <td colspan="4" class="text-end text-muted small py-2">
                                            <i class="bi bi-calculator me-1" style="color:#0f766e"></i>Calculadora Selección:
                                        </td>
                                        <td class="text-center font-monospace py-2" style="color:#1e40af;font-size:0.8rem;" id="calc-total-bruto-sel">
                                            ${formatExactMinutesToTime(totalBruto)}
                                        </td>
                                        <td></td>
                                        <td class="text-center py-2" id="calc-acumulado-final">
                                            <span class="badge font-monospace px-2 py-1 shadow-sm" style="background:#0f766e;color:#ffffff;font-size:0.8rem;" id="badge-total-acumulado">
                                                ${formatExactMinutesToTime(totalBruto)}
                                            </span>
                                        </td>
                                        <td colspan="2" class="py-2">
                                            <div class="d-flex align-items-center justify-content-end gap-2">
                                                <span class="small" style="font-size:0.75rem;">
                                                    Saldo Proy: <strong class="px-2 py-0.5 rounded font-monospace" id="calc-saldo-proyectado" style="background:${currentSaldoBg};color:${currentSaldoColor}">${currentSaldoStr}</strong>
                                                </span>
                                            </div>
                                        </td>
                                    </tr>
                                </tfoot>
                            </table>
                        </div>
                    </div>

                    <div class="modal-footer border-0 bg-light" style="padding:12px 24px">
                        <div class="d-flex align-items-center gap-3 w-100">
                            <div class="d-flex gap-3" style="font-size:0.78rem">
                                <span><i class="bi bi-clock text-primary me-1"></i>Bruto: <strong>${formatMinutesToHHMM(totalBruto)}</strong></span>
                                <span><i class="bi bi-check-circle text-success me-1"></i>Aprobado: <strong class="text-success">${formatMinutesToHHMM(totalAprobado)}</strong></span>
                                <span><i class="bi bi-hourglass-split text-warning me-1"></i>Pendiente: <strong class="text-warning">${formatMinutesToHHMM(totalPendiente)}</strong></span>
                            </div>
                            <button type="button" class="btn btn-secondary ms-auto" data-bs-dismiss="modal">Cerrar</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const modal = new bootstrap.Modal(document.getElementById(modalId));
    modal.show();

    setTimeout(() => {
        if (typeof window.recalcularCalculadoraHE === 'function') {
            window.recalcularCalculadoraHE();
        }
    }, 50);

    document.getElementById(modalId).addEventListener('hidden.bs.modal', function() {
        this.remove();
    });
};

// Acción individual: Aprobar/Rechazar una sola jornada de HE
window.submitSingleHE = async function(empId, fecha, estado, minutos) {
    try {
        const res = await fetch('/api/asistencia/aprobar-he-batch/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify([{
                empleado_id: empId,
                fecha: fecha,
                estado: estado,
                minutos_autorizados: estado === 'APROBADO' ? minutos : 0
            }])
        });
        const data = await res.json();
        if (data.success) {
            showToast(estado === 'APROBADO' ? 'Listo. Horas extra aprobadas.' : 'Listo. Horas extra rechazadas.', 'success');
            await loadMarcacionesData();
            const mEl = document.getElementById('modalBatchHE');
            if (mEl) bootstrap.Modal.getInstance(mEl)?.hide();
        } else {
            showToast(data.detail || 'No se pudieron guardar las horas extra.', 'danger');
        }
    } catch (e) {
        Avisos.sinConexion();
    }
};

// ==========================================
// ADMIN BYPASS: Salto de Seguridad para Superusuarios
// ==========================================
window.bypassSecurityWall = function() {
    console.log("🚀 INICIANDO BYPASS DE SEGURIDAD...");
    
    // Eliminamos confirm para evitar problemas de foco/bloqueo en el navegador
    console.log("🔓 ADMIN BYPASS ACTIVADO");
    
    // Almacenar bypass en la sesión actual para evitar que checkAuditoriaBloqueo lo vuelva a abrir
    sessionStorage.setItem('security_wall_bypass', 'true');
    // Invalidar caché de auditoría para que la próxima llamada use el bypass
    _auditoriaBloqueoCache = { result: null, timestamp: 0 };
    
    // Cerrar el modal
    const modalEl = document.getElementById('modal-regularizacion-asistencia');
    if (modalEl) {
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
    }
    
    showToast("Se abrió con el permiso de administrador.", "warning");
    
    // REANUDAR CARGA: Con un pequeño delay para asegurar limpieza visual del modal
    console.log("🔄 Reanudando carga de datos tras bypass (con delay)...");
    setTimeout(() => {
        if (typeof window.loadMarcacionesData === 'function') {
            window.loadMarcacionesData();
        } else {
            console.error("❌ Error: window.loadMarcacionesData no está definida.");
        }
    }, 500);
}

// Modificar checkAuditoriaBloqueo para respetar el bypass de sesión
// ── CACHE TTL: evitar llamadas redundantes al backend ────────────────────
let _auditoriaBloqueoCache = { result: null, timestamp: 0 };
const _AUDITORIA_CACHE_TTL_MS = 60000; // 60 segundos — el estado de bloqueo no cambia entre clicks
let _auditoriaBloqueoInFlight = null;  // Promise para deduplicar llamadas concurrentes

// Invalidar caché cuando se recarga la data de marcaciones
function _invalidarAuditoriaCache() {
    _auditoriaBloqueoCache = { result: null, timestamp: 0 };
}

window.checkAuditoriaBloqueo = async function(fecha) {
    if (sessionStorage.getItem('security_wall_bypass') === 'true') {
        console.log("🔓 Bypass activo en sesión. Ignorando auditoría.");
        return false;
    }

    // Caché TTL: si la última consulta fue hace menos de 5s, reusar resultado
    const now = Date.now();
    if (_auditoriaBloqueoCache.result !== null && (now - _auditoriaBloqueoCache.timestamp) < _AUDITORIA_CACHE_TTL_MS) {
        console.log('🛡️ Auditoría (caché): reutilizando resultado previo');
        return _auditoriaBloqueoCache.result;
    }

    // Deduplicación: si ya hay una llamada en vuelo, esperar su resultado
    if (_auditoriaBloqueoInFlight) {
        console.log('🛡️ Auditoría (dedup): esperando llamada en vuelo');
        return _auditoriaBloqueoInFlight;
    }

    _auditoriaBloqueoInFlight = _checkAuditoriaBloqueoImpl(fecha);
    try {
        const result = await _auditoriaBloqueoInFlight;
        _auditoriaBloqueoCache = { result, timestamp: Date.now() };
        return result;
    } finally {
        _auditoriaBloqueoInFlight = null;
    }
};

async function _checkAuditoriaBloqueoImpl(fecha) {
    try {
        const t = Date.now();
        const resp = await fetch(`/api/asistencia/auditoria-bloqueo/?fecha=${fecha || ''}&_t=${t}`);
        if (!resp.ok) {
            console.error("❌ Error en auditoría:", resp.status);
            return false;
        }
        
        const data = await resp.json();
        console.log("🛡️ Resultado Auditoría (Raw):", data);
        
        if (data.bloqueo) {
            // Abrir el modal con la tabla de anomalías
            openRegularizacionModal(data.anomalias, data.fecha_auditada); 
            
            // Gestionar visibilidad de botones Admin (Bypass)
            const btnBypass = document.getElementById('btn-bypass-seguridad');
            if (btnBypass) {
                const canBypass = (data.can_bypass === true || data.can_bypass === 1);
                console.log("🔑 Aplicando Visibilidad Bypass:", canBypass);
                btnBypass.style.setProperty('display', canBypass ? 'block' : 'none', 'important');
                
                // ASIGNACIÓN EXPLICITA DE EVENTO
                btnBypass.onclick = function() {
                    console.log("🖱️ Click detectado en Botón Bypass");
                    window.bypassSecurityWall();
                };
            }
            
            // Habilitar cierre si es Admin
            const closeBtns = document.querySelectorAll('#modal-regularizacion-asistencia .btn-close, #modal-regularizacion-asistencia [data-bs-dismiss="modal"]');
            closeBtns.forEach(btn => {
                const canBypass = (data.can_bypass === true || data.can_bypass === 1);
                btn.style.setProperty('display', canBypass ? 'block' : 'none', 'important');
                
                // Si puede saltarse el muro, el cierre del modal también debe activar la carga
                if (canBypass) {
                    btn.onclick = function() {
                        console.log("✖️ Cierre de modal detectado (Bypass implícito)");
                        window.bypassSecurityWall();
                    };
                }
            });

            const modalEl = document.getElementById('modal-regularizacion-asistencia');
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl, {
                backdrop: (data.can_bypass) ? true : 'static',
                keyboard: (data.can_bypass) ? true : false
            });
            modal.show();
            return true; 
        }
        return false; 
    } catch (e) {
        console.error("🚨 Error crítico en auditoría:", e);
        return false; 
    }
}

window.toggleAllHECells = function (master) {
    document.querySelectorAll('.check-item-he').forEach(c => c.checked = master.checked);
    if (typeof window.recalcularCalculadoraHE === 'function') {
        window.recalcularCalculadoraHE();
    }
};

window.submitBatchHE = async function (event, empleadoId, nuevoEstado) {
    const selected = Array.from(document.querySelectorAll('.check-item-he:checked')).map(c => {
        const fecha = c.dataset.fecha;
        const inp = document.getElementById(`input-min-${fecha}`);
        const customMins = inp ? parseFloat(inp.value) : parseFloat(c.dataset.minutos);
        return {
            empleado_id: empleadoId,
            fecha: fecha,
            estado: nuevoEstado,
            minutos_autorizados: nuevoEstado === 'APROBADO' ? (isNaN(customMins) ? (parseFloat(c.dataset.minutos) || 0) : customMins) : 0
        };
    });

    if (selected.length === 0) {
        Avisos.falta('Falta elegir los días. Marque al menos uno.');
        return;
    }

    if (!await uiConfirm(`¿Marcar ${selected.length === 1 ? '1 día' : selected.length + ' días'} como ${String(nuevoEstado).toLowerCase()}?`, { confirmText: 'Marcar ' + (selected.length === 1 ? 'día' : 'días') })) return;

    try {
        const btn = event.target;
        const originalText = btn.innerHTML;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Procesando...';
        btn.disabled = true;

        const response = await fetch('/api/asistencia/aprobar-he-batch/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(selected)
        });

        const data = await response.json();
        if (data.success) {
            showToast(data.mensaje, 'success');
            const mEl = document.getElementById('modalBatchHE');
            const mInst = bootstrap.Modal.getInstance(mEl);
            if (mInst) mInst.hide();

            // Refrescar la matriz (usar la función correcta según el contexto)
            if (typeof window.loadMarcacionesData === 'function') {
                window.loadMarcacionesData();
            } else if (typeof loadTeamMatrix === 'function') {
                loadTeamMatrix();
            }
        } else {
            throw new Error(data.detail || 'Error en el servidor');
        }
    } catch (error) {
        console.error("Error en submitBatchHE:", error);
        Avisos.error("No se pudo aprobar todo junto. " + error.message);
    } finally {
        // En caso de error, restaurar botón
        const btn = event.target;
        if (btn && btn.disabled) {
            btn.innerHTML = nuevoEstado === 'APROBADO' ? '<i class="bi bi-check-circle-fill text-success" aria-hidden="true"></i> Aprobar Seleccionados' : '<i class="bi bi-x-circle-fill text-danger" aria-hidden="true"></i> Rechazar Seleccionados';
            btn.disabled = false;
        }
    }
};

// ─── CONTROLADORES DEL ASISTENTE DE CUADRE DE HORAS EXTRAS ──────────────
window.onRowTimeChange = function(fecha) {
    const timeInp = document.getElementById(`input-time-${fecha}`);
    const minInp = document.getElementById(`input-min-${fecha}`);
    const sel = document.getElementById(`sel-estado-${fecha}`);
    if (!timeInp || !minInp) return;

    let txt = timeInp.value.trim().replace('+', '');
    let mins = 0;
    if (txt.includes(':')) {
        const parts = txt.split(':');
        const h = parseInt(parts[0], 10) || 0;
        const m = parseInt(parts[1], 10) || 0;
        const s = parts[2] ? (parseInt(parts[2], 10) || 0) : 0;
        mins = h * 60 + m + (s / 60.0);
    } else {
        mins = parseFloat(txt) || 0;
    }
    const bruto = parseFloat(minInp.dataset.bruto) || 0;
    if (mins > bruto) mins = bruto;
    if (mins < 0) mins = 0;
    mins = Math.round(mins * 1000) / 1000;
    minInp.value = mins;
    timeInp.value = formatExactMinutesToTime(mins);

    if (mins > 0 && sel && sel.value !== 'APROBADO') {
        sel.value = 'APROBADO';
    } else if (mins === 0 && sel && sel.value === 'APROBADO') {
        sel.value = 'RECHAZADO';
    }
    window.onRowHEChange(fecha);
};

window.onRowHEChange = function(fecha) {
    const sel = document.getElementById(`sel-estado-${fecha}`);
    const inp = document.getElementById(`input-min-${fecha}`);
    const timeInp = document.getElementById(`input-time-${fecha}`);
    const chk = document.getElementById(`chk-he-${fecha}`);
    const row = document.getElementById(`row-he-${fecha}`);
    const badgeSt = document.getElementById(`badge-st-${fecha}`);
    if (!sel || !inp) return;
    
    const estado = sel.value;
    const bruto = parseFloat(inp.dataset.bruto) || 0;
    let mins = parseFloat(inp.value);
    if (isNaN(mins)) mins = (estado === 'APROBADO' ? bruto : 0);
    
    if (estado === 'RECHAZADO') {
        mins = 0;
        inp.value = 0;
        if (timeInp) {
            timeInp.value = '00:00:00';
            timeInp.disabled = true;
            timeInp.classList.add('opacity-50');
        }
    } else if (estado === 'PENDIENTE') {
        inp.value = mins;
        if (timeInp) {
            timeInp.value = formatExactMinutesToTime(mins > 0 ? mins : bruto);
            timeInp.disabled = true;
            timeInp.classList.add('opacity-50');
        }
    } else if (estado === 'APROBADO') {
        if (mins <= 0 && bruto > 0) mins = bruto;
        if (mins > bruto) mins = bruto;
        if (mins < 0) mins = 0;
        mins = Math.round(mins * 1000) / 1000;
        inp.value = mins;
        if (timeInp) {
            timeInp.value = formatExactMinutesToTime(mins);
            timeInp.disabled = false;
            timeInp.classList.remove('opacity-50');
        }
    }
    
    if (badgeSt) {
        if (estado === 'APROBADO') {
            badgeSt.className = 'badge bg-success';
            badgeSt.innerHTML = '<i class="bi bi-check-circle-fill text-success" aria-hidden="true"></i> Aprobado';
        } else if (estado === 'RECHAZADO') {
            badgeSt.className = 'badge bg-danger';
            badgeSt.innerHTML = '<i class="bi bi-x-circle-fill text-danger" aria-hidden="true"></i> Rechazado';
        } else {
            badgeSt.className = 'badge bg-warning text-dark';
            badgeSt.innerHTML = '<i class="bi bi-hourglass-split" aria-hidden="true"></i> Pendiente';
        }
    }
    
    if (chk) chk.checked = true;
    
    if (row) {
        const orig = row.dataset.estadoOrig;
        if (estado !== orig) {
            row.classList.add('table-info');
        } else {
            row.classList.remove('table-info');
        }
    }
    
    const btn = document.getElementById('btn-aplicar-cuadre');
    if (btn) btn.disabled = false;

    if (typeof window.recalcularCalculadoraHE === 'function') {
        window.recalcularCalculadoraHE();
    }
};

window.onRowHEChecked = function(fecha) {
    const btn = document.getElementById('btn-aplicar-cuadre');
    if (btn) btn.disabled = false;

    if (typeof window.recalcularCalculadoraHE === 'function') {
        window.recalcularCalculadoraHE();
    }
};

window.recalcularCalculadoraHE = function() {
    const rows = Array.from(document.querySelectorAll('.he-approval-row'));
    if (rows.length === 0) return;

    const modalEl = document.getElementById('modalBatchHE');
    const deudaTotal = parseFloat(modalEl?.dataset?.deudaTotal || 0);
    const compensado = parseFloat(modalEl?.dataset?.compensado || 0);
    const deudaExacta = deudaTotal + compensado;

    let runningTotalMin = 0;
    let totalBrutoSelMin = 0;
    let countChecked = 0;

    rows.forEach(r => {
        const fecha = r.dataset.fecha;
        const chk = document.getElementById(`chk-he-${fecha}`);
        const acumCell = document.getElementById(`acum-he-${fecha}`);
        const inp = document.getElementById(`input-min-${fecha}`);
        const sel = document.getElementById(`sel-estado-${fecha}`);
        const bruto = parseFloat(r.dataset.bruto) || 0;

        const isChecked = chk ? chk.checked : true;

        if (isChecked) {
            countChecked++;
            totalBrutoSelMin += bruto;

            let mins = bruto;
            if (inp && !isNaN(parseFloat(inp.value))) {
                mins = parseFloat(inp.value);
            }
            if (sel && sel.value === 'RECHAZADO') {
                mins = 0;
            }

            runningTotalMin += mins;

            if (acumCell) {
                acumCell.innerHTML = `<span class="badge font-monospace px-2 py-1 shadow-xs" style="background:#ccfbf1;color:#0f766e;font-size:0.78rem;border:1px solid #99f6e4;">${formatExactMinutesToTime(runningTotalMin)}</span>`;
            }
            r.classList.remove('opacity-50', 'table-secondary');
        } else {
            if (acumCell) {
                acumCell.innerHTML = `<span class="text-muted" style="font-size:0.8rem;">—</span>`;
            }
            r.classList.add('opacity-50', 'table-secondary');
        }
    });

    // Actualizar badge y totales de pie
    const badgeTot = document.getElementById('badge-total-acumulado');
    if (badgeTot) {
        badgeTot.textContent = formatExactMinutesToTime(runningTotalMin);
    }
    const brutoSelEl = document.getElementById('calc-total-bruto-sel');
    if (brutoSelEl) {
        brutoSelEl.textContent = formatExactMinutesToTime(totalBrutoSelMin);
    }

    // Saldo Proyectado
    const saldoProyectado = runningTotalMin - deudaExacta;
    const isSaldoZero = Math.abs(saldoProyectado) < 0.0083;
    const saldoSign = isSaldoZero ? '' : (saldoProyectado > 0 ? '+' : '-');
    const saldoStr = isSaldoZero ? '00:00:00' : `${saldoSign}${formatExactMinutesToTime(Math.abs(saldoProyectado))}`;
    const saldoColor = isSaldoZero ? '#475569' : (saldoProyectado > 0 ? '#15803d' : '#b91c1c');
    const saldoBg = isSaldoZero ? '#f1f5f9' : (saldoProyectado > 0 ? '#dcfce7' : '#fee2e2');

    const saldoProyEl = document.getElementById('calc-saldo-proyectado');
    if (saldoProyEl) {
        saldoProyEl.textContent = saldoStr;
        saldoProyEl.style.color = saldoColor;
        saldoProyEl.style.backgroundColor = saldoBg;
    }

    // Actualizar en vivo los contenedores de la Balanza de Masa superior
    const kpiAprobEl = document.getElementById('kpi-he-aprobadas');
    if (kpiAprobEl) {
        kpiAprobEl.textContent = formatExactMinutesToTime(runningTotalMin);
    }
    const kpiSaldoEl = document.getElementById('kpi-saldo-neto');
    const cardSaldoEl = document.getElementById('card-saldo-neto-actual');
    if (kpiSaldoEl) {
        kpiSaldoEl.textContent = saldoStr;
        kpiSaldoEl.style.color = saldoColor;
    }
    if (cardSaldoEl) {
        cardSaldoEl.style.backgroundColor = saldoBg;
        cardSaldoEl.style.borderColor = `${saldoColor}50`;
        cardSaldoEl.style.borderTopColor = saldoColor;
    }

    let pendMins = 0;
    let rechMins = 0;
    rows.forEach(r => {
        const fecha = r.dataset.fecha;
        const sel = document.getElementById(`sel-estado-${fecha}`);
        const inp = document.getElementById(`input-min-${fecha}`);
        const bruto = parseFloat(r.dataset.bruto) || 0;
        const st = sel ? sel.value : r.dataset.estadoOrig;
        const minsAut = inp ? parseFloat(inp.value) || 0 : 0;
        if (st === 'PENDIENTE') {
            pendMins += bruto;
        } else if (st === 'RECHAZADO') {
            rechMins += bruto;
        } else if (st === 'APROBADO' && bruto > minsAut) {
            rechMins += (bruto - minsAut);
        }
    });
    const kpiBolsaEl = document.getElementById('kpi-bolsa-remanente');
    if (kpiBolsaEl) {
        kpiBolsaEl.innerHTML = `${formatExactMinutesToTime(pendMins)} <span class="text-muted fw-normal" style="font-size:0.75rem;">/ ${formatExactMinutesToTime(rechMins)}</span>`;
    }
};

window.copiarAcumuladoAMeta = function() {
    const el = document.getElementById('calc-saldo-proyectado');
    if (!el) return;
    const txt = el.textContent.trim().replace('+', '');
    const inp = document.getElementById('asistente-horas-objetivo');
    if (inp) {
        inp.value = txt;
        const panel = document.getElementById('panel-avanzado-he');
        if (panel && !panel.classList.contains('show')) {
            try {
                const bsCollapse = new bootstrap.Collapse(panel, { toggle: true });
            } catch (e) {
                panel.classList.add('show');
            }
        }
        inp.classList.add('bg-warning-subtle');
        setTimeout(() => inp.classList.remove('bg-warning-subtle'), 1000);
        showToast(`Se copió +${txt} a «Opciones avanzadas».`, 'info');
    }
};

window.ejecutarCuadreRapido = function(empleadoId, accion) {
    // Resaltar visualmente el botón de estrategia seleccionado
    const marcarBotonActivo = (act) => {
        document.querySelectorAll('.btn-estrategia-he').forEach(b => {
            b.classList.remove('active', 'border-2', 'shadow');
            b.style.fontWeight = 'normal';
        });
        if (act === 'cero') {
            const b = document.getElementById('btn-est-cero');
            if (b) { b.classList.add('active', 'border-2', 'shadow'); b.style.fontWeight = 'bold'; }
        } else if (act === 'aprobar_todo') {
            const b = document.getElementById('btn-est-todo');
            if (b) { b.classList.add('active', 'border-2', 'shadow'); b.style.fontWeight = 'bold'; }
        } else if (act === 'redondear_hora' || act === 'redondear_media') {
            const b = document.getElementById('btn-est-redondeo');
            if (b) { b.classList.add('active', 'border-2', 'shadow'); b.style.fontWeight = 'bold'; }
        }
    };
    marcarBotonActivo(accion);

    const modalEl = document.getElementById('modalBatchHE');
    let currentSaldo = (modalEl && modalEl.dataset.saldoActual !== undefined && modalEl.dataset.saldoActual !== '') 
        ? parseFloat(modalEl.dataset.saldoActual) : NaN;
    let deudaTotal = (modalEl && modalEl.dataset.deudaTotal !== undefined && modalEl.dataset.deudaTotal !== '') 
        ? parseFloat(modalEl.dataset.deudaTotal) : NaN;
    let compensado = (modalEl && modalEl.dataset.compensado !== undefined && modalEl.dataset.compensado !== '') 
        ? parseFloat(modalEl.dataset.compensado) : 0;

    const matrix = stateMarcacionesApp.data?.matrix || stateMarcacionesApp.data || {};
    const empData = matrix[empleadoId] || {};
    const empRaw = (stateMarcacionesApp.data?.empleados || stateMarcacionesApp.empleados || []).find(e => e.id === Number(empleadoId)) || {};
    const info = empData.info || empRaw;
    const dates = (stateMarcacionesApp.data && stateMarcacionesApp.data.periodo) 
        ? window.getDatesInRange(stateMarcacionesApp.data.periodo.inicio, stateMarcacionesApp.data.periodo.fin) 
        : [];
    const feriadosArray = stateMarcacionesApp.data && stateMarcacionesApp.data.feriados 
        ? stateMarcacionesApp.data.feriados.map(f => f.fecha || f) : [];

    if (isNaN(currentSaldo) || isNaN(deudaTotal)) {
        let stats = { saldo: 0, d_tot: 0, he_apr: 0, he_compensado: 0 };
        if (typeof window.calcularStatsEmpleado === 'function' && Object.keys(empData).length > 0) {
            try {
                stats = window.calcularStatsEmpleado({ id: empleadoId, info, dias: empData, tipo_programacion: info.tipo_programacion || '' }, dates, feriadosArray);
            } catch(e) {}
        }
        if (isNaN(currentSaldo)) currentSaldo = stats.saldo || 0;
        if (isNaN(deudaTotal)) deudaTotal = stats.d_tot || 0;
        if (isNaN(compensado)) compensado = stats.he_compensado || 0;
    }

    const rows = Array.from(document.querySelectorAll('.he-approval-row'));
    if (rows.length === 0) return;

    // Rescatar de rechazadas SIEMPRE activo por defecto si no existe el switch o está checked
    const switchRechazadas = document.getElementById('chk-incluir-rechazadas');
    const incluirRechazadas = switchRechazadas ? switchRechazadas.checked : true;

    // Deuda real exacta con segundos (ej: 153.5 min = 02:33:30)
    const deudaExacta = deudaTotal + compensado;

    const parsedRows = rows.map(r => ({
        fecha: r.dataset.fecha,
        bruto: parseFloat(r.dataset.bruto) || 0,
        orig: r.dataset.estadoOrig,
        nuevoEstado: r.dataset.estadoOrig,
        minutosAut: 0
    }));

    let totalAsignado = 0;
    let diasAprobados = 0;
    let diasRescatadosRech = 0;
    let fbMsg = '';

    if (accion === 'cero') {
        // Meta exacta: el total de horas aprobadas debe ser exactamente igual a deudaExacta
        let porAsignar = deudaExacta;

        parsedRows.forEach(r => {
            const esElegible = r.orig === 'PENDIENTE' || r.orig === 'APROBADO' || (incluirRechazadas && r.orig === 'RECHAZADO');
            if (esElegible && porAsignar > 0.0083 && r.bruto > 0) {
                const aAprobar = Math.min(r.bruto, porAsignar);
                r.nuevoEstado = 'APROBADO';
                r.minutosAut = Math.round(aAprobar * 1000) / 1000;
                porAsignar -= aAprobar;
                totalAsignado += aAprobar;
                diasAprobados++;
                if (r.orig === 'RECHAZADO') diasRescatadosRech++;
            } else {
                // Las jornadas que sobran se rechazan para que no sumen al saldo y quede en 00:00:00 exacto
                r.nuevoEstado = 'RECHAZADO';
                r.minutosAut = 0;
            }
        });

        const rawSaldoProy = totalAsignado - deudaExacta;
        const isCero = Math.abs(rawSaldoProy) < 0.0083;
        const saldoSign = isCero ? '' : (rawSaldoProy > 0 ? '+' : '-');
        const projStr = isCero ? '00:00:00' : `${saldoSign}${formatExactMinutesToTime(Math.abs(rawSaldoProy))}`;

        if (porAsignar <= 0.0083) {
            fbMsg = `
                <div class="alert alert-success py-2 px-3 mb-0 small border-0 shadow-sm d-flex align-items-center justify-content-between flex-wrap gap-2">
                    <div>
                        <span class="fs-6 fw-bold text-success me-2"><i class="bi bi-hammer" aria-hidden="true"></i> Compensar Deuda (Art. 32 Código del Trabajo):</span>
                        Se imputan <strong>+${formatExactMinutesToTime(totalAsignado)}</strong> en ${diasAprobados} jornada(s)
                        ${diasRescatadosRech > 0 ? `<span class="badge bg-warning text-dark ms-1"><i class="bi bi-arrow-repeat"></i> ${diasRescatadosRech} rescatada(s) de Rechazo</span>` : ''}
                        · Saldo Neto Proyectado: <span class="badge bg-dark fs-6">${projStr}</span>
                    </div>
                    <div class="text-success small fw-semibold"><i class="bi bi-arrow-right-circle me-1"></i>Previsualización lista. Confirma con el botón verde.</div>
                </div>
            `;
        } else {
            fbMsg = `
                <div class="alert alert-warning py-2 px-3 mb-0 small border-0 shadow-sm">
                    <strong><i class="bi bi-exclamation-triangle-fill text-warning" aria-hidden="true"></i> Horas insuficientes para llegar a cero:</strong> Se aprobó el 100% disponible (+${formatExactMinutesToTime(totalAsignado)}), pero la deuda acumulada es de ${formatExactMinutesToTime(deudaExacta)}. Faltaron <strong>${formatExactMinutesToTime(porAsignar)}</strong> para cero · Saldo Proyectado: <span class="badge bg-danger fs-6">${projStr}</span>
                </div>
            `;
        }

    } else if (accion === 'redondear_hora' || accion === 'redondear_media') {
        const totalBrutoElegible = parsedRows.filter(r => r.orig === 'PENDIENTE' || r.orig === 'APROBADO' || (incluirRechazadas && r.orig === 'RECHAZADO')).reduce((s, r) => s + r.bruto, 0);
        const saldoPotencial = totalBrutoElegible - deudaExacta;

        if (saldoPotencial <= 0.0083) {
            showToast("Esta persona no tiene saldo de horas extra a favor para redondear.", "warning");
            const fb = document.getElementById('asistente-feedback');
            if (fb) fb.innerHTML = `<div class="alert alert-warning py-2 px-3 mb-0 small border-0 shadow-sm"><i class="bi bi-exclamation-triangle-fill text-warning" aria-hidden="true"></i> El sobretiempo disponible no supera la deuda total. Usa <strong>"1. Compensar Deuda (Saldo Cero)"</strong> para absorber la deuda.</div>`;
            return;
        }

        const stepMin = (accion === 'redondear_media') ? 30 : 60;
        const targetSaldoNeto = Math.floor(saldoPotencial / stepMin) * stepMin;
        const metaTotalAprobado = deudaExacta + targetSaldoNeto;
        let porAsignar = metaTotalAprobado;

        parsedRows.forEach(r => {
            const esElegible = r.orig === 'PENDIENTE' || r.orig === 'APROBADO' || (incluirRechazadas && r.orig === 'RECHAZADO');
            if (esElegible && porAsignar > 0.0083 && r.bruto > 0) {
                const aAprobar = Math.min(r.bruto, porAsignar);
                r.nuevoEstado = 'APROBADO';
                r.minutosAut = Math.round(aAprobar * 1000) / 1000;
                porAsignar -= aAprobar;
                totalAsignado += aAprobar;
                diasAprobados++;
                if (r.orig === 'RECHAZADO') diasRescatadosRech++;
            } else {
                r.nuevoEstado = 'RECHAZADO';
                r.minutosAut = 0;
            }
        });

        const rawSaldoProy = totalAsignado - deudaExacta;
        const isCero = Math.abs(rawSaldoProy) < 0.0083;
        const saldoSign = isCero ? '' : (rawSaldoProy > 0 ? '+' : '-');
        const projStr = isCero ? '00:00:00' : `${saldoSign}${formatExactMinutesToTime(Math.abs(rawSaldoProy))}`;
        const minutosRecortados = Math.max(0, saldoPotencial - targetSaldoNeto);

        fbMsg = `
            <div class="alert alert-warning py-2 px-3 mb-0 small border-0 shadow-sm d-flex align-items-center justify-content-between flex-wrap gap-2 text-dark" style="background:#fef3c7;">
                <div>
                    <span class="fs-6 fw-bold text-dark me-2"><i class="bi bi-stopwatch" aria-hidden="true"></i> Bloque Nómina + Banco de Tiempo:</span>
                    Se autorizan <strong>+${formatExactMinutesToTime(totalAsignado)}</strong> en ${diasAprobados} jornada(s)
                    ${diasRescatadosRech > 0 ? `<span class="badge bg-warning text-dark ms-1"><i class="bi bi-arrow-repeat"></i> ${diasRescatadosRech} de Rechazo</span>` : ''}
                    · Saldo Nómina: <span class="badge bg-success fs-6">${projStr}</span>
                    ${minutosRecortados > 0.0083 ? `<span class="badge bg-light text-dark border ms-1 fw-normal">Remanente de ${formatExactMinutesToTime(minutosRecortados)} imputado a descanso/banco</span>` : ''}
                </div>
                <div class="text-dark small fw-semibold"><i class="bi bi-arrow-right-circle me-1"></i>Previsualización lista. Confirma con el botón verde.</div>
            </div>
        `;

    } else if (accion === 'aprobar_todo') {
        parsedRows.forEach(r => {
            const esElegible = r.orig === 'PENDIENTE' || r.orig === 'APROBADO' || (incluirRechazadas && r.orig === 'RECHAZADO');
            if (esElegible) {
                r.nuevoEstado = 'APROBADO';
                r.minutosAut = r.bruto;
                totalAsignado += r.bruto;
                diasAprobados++;
            } else {
                r.nuevoEstado = r.orig;
                r.minutosAut = 0;
            }
        });

        const rawSaldoProy = totalAsignado - deudaExacta;
        const isCero = Math.abs(rawSaldoProy) < 0.0083;
        const saldoSign = isCero ? '' : (rawSaldoProy > 0 ? '+' : '-');
        const projStr = isCero ? '00:00:00' : `${saldoSign}${formatExactMinutesToTime(Math.abs(rawSaldoProy))}`;

        fbMsg = `
            <div class="alert alert-primary py-2 px-3 mb-0 small border-0 shadow-sm d-flex align-items-center justify-content-between flex-wrap gap-2">
                <div>
                    <span class="fs-6 fw-bold text-primary me-2"><i class="bi bi-bank2" aria-hidden="true"></i> Pago 100% Íntegro (Norma Legal DT):</span>
                    Se aprueban <strong>+${formatExactMinutesToTime(totalAsignado)}</strong> en ${diasAprobados} jornadas sin descuentos.
                    · Saldo Neto Proyectado: <span class="badge ${rawSaldoProy >= 0 ? 'bg-success' : 'bg-danger'} fs-6">${projStr}</span>
                </div>
                <div class="text-primary small fw-semibold"><i class="bi bi-arrow-right-circle me-1"></i>Previsualización lista. Confirma con el botón verde.</div>
            </div>
        `;

    } else if (accion === 'rechazar_todo') {
        parsedRows.forEach(r => {
            r.nuevoEstado = 'RECHAZADO';
            r.minutosAut = 0;
        });

        const rawSaldoProy = 0 - deudaExacta;
        const saldoSign = rawSaldoProy > 0 ? '+' : (rawSaldoProy < 0 ? '-' : '');
        const projStr = `${saldoSign}${formatExactMinutesToTime(Math.abs(rawSaldoProy))}`;

        fbMsg = `
            <div class="alert alert-danger py-2 px-3 mb-0 small border-0 shadow-sm d-flex align-items-center justify-content-between flex-wrap gap-2">
                <div>
                    <span class="fs-6 fw-bold text-danger me-2"><i class="bi bi-x-circle-fill text-danger" aria-hidden="true"></i> Rechazo Total:</span>
                    Sobretiempo dejado en 0. Deuda pendiente se mantiene íntegra.
                    · Saldo Neto Proyectado: <span class="badge bg-danger fs-6">${projStr}</span>
                </div>
                <div class="text-danger small fw-semibold"><i class="bi bi-arrow-right-circle me-1"></i>Previsualización lista. Confirma con el botón verde.</div>
            </div>
        `;

    } else if (accion === 'saldo_objetivo') {
        const valStr = (document.getElementById('asistente-horas-objetivo')?.value || '0').trim();
        let targetMins = 0;
        if (valStr.includes(':')) {
            const parts = valStr.replace('+','').split(':');
            const h = parseInt(parts[0], 10) || 0;
            const m = parseInt(parts[1], 10) || 0;
            const s = parts[2] ? (parseInt(parts[2], 10) || 0) : 0;
            targetMins = h * 60 + m + (s / 60.0);
        } else {
            targetMins = (parseFloat(valStr.replace('+','')) || 0) * 60;
        }

        const metaTotalAprobado = deudaExacta + targetMins;
        let porAsignar = metaTotalAprobado;

        parsedRows.forEach(r => {
            const esElegible = r.orig === 'PENDIENTE' || r.orig === 'APROBADO' || (incluirRechazadas && r.orig === 'RECHAZADO');
            if (esElegible && porAsignar > 0.0083 && r.bruto > 0) {
                const aAprobar = Math.min(r.bruto, porAsignar);
                r.nuevoEstado = 'APROBADO';
                r.minutosAut = Math.round(aAprobar * 1000) / 1000;
                porAsignar -= aAprobar;
                totalAsignado += aAprobar;
                diasAprobados++;
                if (r.orig === 'RECHAZADO') diasRescatadosRech++;
            } else {
                r.nuevoEstado = 'RECHAZADO';
                r.minutosAut = 0;
            }
        });

        const rawSaldoProy = totalAsignado - deudaExacta;
        const saldoSign = rawSaldoProy > 0 ? '+' : (rawSaldoProy < 0 ? '-' : '');
        const projStr = `${saldoSign}${formatExactMinutesToTime(Math.abs(rawSaldoProy))}`;

        fbMsg = `
            <div class="alert alert-info py-2 px-3 mb-0 small border-0 shadow-sm d-flex align-items-center justify-content-between flex-wrap gap-2">
                <div>
                    <span class="fs-6 fw-bold text-primary me-2"><i class="bi bi-bullseye" aria-hidden="true"></i> Saldo Objetivo Personalizado:</span>
                    Se autorizan <strong>+${formatExactMinutesToTime(totalAsignado)}</strong> en ${diasAprobados} jornadas.
                    · Saldo Neto Proyectado: <span class="badge bg-primary fs-6">${projStr}</span>
                </div>
                <div class="text-primary small fw-semibold"><i class="bi bi-arrow-right-circle me-1"></i>Previsualización lista. Confirma con el botón verde.</div>
            </div>
        `;
    }

    // Actualizar UI de forma unificada para todas las filas
    parsedRows.forEach(pr => {
        const sel = document.getElementById(`sel-estado-${pr.fecha}`);
        const inp = document.getElementById(`input-min-${pr.fecha}`);
        const timeInp = document.getElementById(`input-time-${pr.fecha}`);
        const chk = document.getElementById(`chk-he-${pr.fecha}`);
        if (sel) sel.value = pr.nuevoEstado;
        if (inp) inp.value = pr.minutosAut;
        if (timeInp) {
            timeInp.value = (pr.nuevoEstado === 'RECHAZADO' && pr.minutosAut === 0) ? '00:00:00' : formatExactMinutesToTime(pr.minutosAut);
            timeInp.disabled = (pr.nuevoEstado !== 'APROBADO');
            if (pr.nuevoEstado !== 'APROBADO') timeInp.classList.add('opacity-50');
            else timeInp.classList.remove('opacity-50');
        }
        if (chk) chk.checked = true;
        window.onRowHEChange(pr.fecha);
    });

    const fb = document.getElementById('asistente-feedback');
    if (fb && fbMsg) fb.innerHTML = fbMsg;

    const btnGuardar = document.getElementById('btn-aplicar-cuadre');
    if (btnGuardar) {
        btnGuardar.disabled = false;
        btnGuardar.classList.remove('opacity-50');
    }

    if (typeof window.recalcularCalculadoraHE === 'function') {
        window.recalcularCalculadoraHE();
    }
};

window.simularCuadreHE = function(empleadoId) {
    window.ejecutarCuadreRapido(empleadoId, 'cero');
};

window.aplicarCuadreHE = async function(empleadoId) {
    const checkedRows = Array.from(document.querySelectorAll('.check-item-he:checked'));
    if (checkedRows.length === 0) {
        showToast("Falta elegir las jornadas. Marque al menos una para guardar.", "warning");
        return;
    }
    
    const items = checkedRows.map(chk => {
        const fecha = chk.dataset.fecha;
        const sel = document.getElementById(`sel-estado-${fecha}`);
        const inp = document.getElementById(`input-min-${fecha}`);
        const estado = sel ? sel.value : 'APROBADO';
        const mins = (estado === 'APROBADO') ? (parseFloat(inp?.value) || 0) : 0;
        return {
            empleado_id: empleadoId,
            fecha: fecha,
            estado: estado,
            minutos_autorizados: mins
        };
    });
    
    const btn = document.getElementById('btn-aplicar-cuadre');
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Registrando en BD...';
    }
    
    try {
        const token = (typeof AuthService !== 'undefined' && typeof AuthService.getToken === 'function') ? AuthService.getToken() : localStorage.getItem('access_token');
        const res = await fetch('/api/asistencia/aprobar-he-batch/', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': token ? `Bearer ${token}` : ''
            },
            body: JSON.stringify(items)
        });
        const data = await res.json();
        if (data.success || res.ok) {
            showToast(`Listo. Cuadre guardado: ${items.length === 1 ? '1 jornada' : items.length + ' jornadas'}.`, 'success');
            const mEl = document.getElementById('modalBatchHE');
            if (mEl) {
                const modal = bootstrap.Modal.getInstance(mEl);
                if (modal) modal.hide();
            }
            if (typeof window.loadMarcacionesData === 'function') {
                await window.loadMarcacionesData();
            }
        } else {
            showToast(data.detail || 'No se guardó el cuadre. El servidor no dio el motivo.', 'danger');
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = origHtml || '<i class="bi bi-floppy-fill me-1"></i>Confirmar y Guardar en BD';
            }
        }
    } catch(err) {
        Avisos.sinConexion();
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml || '<i class="bi bi-floppy-fill me-1"></i>Confirmar y Guardar en BD';
        }
    }
};





/**
 * Mantiene el estado local de la regularización para callbacks
 */
const regularizacionState = {
    callbackFinal: null
};

// Apertura del modal de regularización
function openRegularizacionModal(anomalias, fecha) {
    const modalEl = document.getElementById('modal-regularizacion-asistencia');
    if (!modalEl) {
        console.error("No se encontró modal-regularizacion-asistencia en index.html");
        return;
    }

    const tbody = document.getElementById('lista-regularizacion-cuerpo');
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
    const nombreDe = (a) => `${a.apellido_paterno} ${a.apellido_materno || ''} ${a.nombre}`.trim().replace(/  +/g, ' ');
    // a.fecha es la fecha MÍNIMA encontrada por el backend (agrupada por empleado)
    tbody.innerHTML = anomalias.length ? anomalias.map((a, k) => '<tr>'
        + '<td><b class="vn-nom">' + esc(window.nombreTitulo(nombreDe(a))) + '</b><span class="vn-t">RUT ' + (a.rut ? esc(window.rutVista(a.rut)) : 'sin registrar') + '</span></td>'
        + '<td>' + esc(a.area) + '</td>'
        + '<td class="vn-nw">Desde ' + esc(window.formatFechaDDMMYYYY(a.fecha)) + '</td>'
        + '<td class="vn-acc"><button type="button" class="btn btn-light btn-sm" data-i="' + k + '">Asignar turno</button></td>'
        + '</tr>').join('')
        : '<tr><td colspan="4" class="vn-vacio">No quedan personas sin turno.</td></tr>';
    // El botón toma la persona de la lista (sin datos dentro del onclick: un apóstrofo en el nombre no rompe nada)
    tbody.onclick = (ev) => {
        const b = ev.target.closest('button[data-i]');
        if (!b) return;
        const a = anomalias[Number(b.dataset.i)];
        if (a) openAsignarTurnoForzado(a.id, a.fecha, a.area, nombreDe(a), a.cargo || '');
    };

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}

/**
 * Abre el modal de asignación individual filtrando por área.
 */
// Actualizar etiqueta dinámica de tipo de programación del turno
window.updateTurnoInfoLabel = function(e) {
    const select = e.target;
    let infoDiv = select.nextElementSibling;
    if (!infoDiv || !infoDiv.classList.contains('turno-dynamic-info')) {
        infoDiv = document.createElement('div');
        infoDiv.className = 'turno-dynamic-info form-text text-primary mt-1 fw-bold';
        select.parentNode.insertBefore(infoDiv, select.nextSibling);
    }
    
    if (select.selectedIndex >= 0 && select.value) {
        const option = select.options[select.selectedIndex];
        const tipo = option.getAttribute('data-tipo');
        const horario = option.getAttribute('data-horario');
        if (tipo) {
            infoDiv.innerHTML = `<i class="bi bi-info-square me-1"></i>Tipo Planificación: <span class="badge bg-primary text-white">${tipo}</span> <span>${horario || ''}</span>`;
            return;
        }
    }
    infoDiv.innerHTML = '';
};

async function openAsignarTurnoForzado(empleadoId, fecha, area, nombre, cargo = '') {
    const modalEl = document.getElementById('modal-asignar-turno-individual');
    if (!modalEl) return;

    // Poblar datos básicos
    document.getElementById('asig-indiv-empleado-id').value = empleadoId;
    document.getElementById('asig-indiv-fecha').value = fecha;
    document.getElementById('asig-indiv-nombre').innerText = nombre;
    document.getElementById('asig-indiv-area-badge').textContent = area || '';
    const cargoBadge = document.getElementById('asig-indiv-cargo');
    if (cargoBadge) cargoBadge.textContent = cargo || '';
    // Encabezado de persona (etapa 6): iniciales y «NOMBRE · área · cargo»
    if (window.cabeceraPersona) window.cabeceraPersona(modalEl, { nombre: nombre, empId: empleadoId, detalle: [area, cargo].filter(Boolean).join(' · ') });

    // Ocultar la fila BioAlba hasta que RRHH decida buscar (no automático)
    const rowBioAlba = document.getElementById('asig-bioalba-row');
    if (rowBioAlba) rowBioAlba.classList.add('d-none');
    // Guardar el empleadoId para que el botón de búsqueda lo use
    const btnBuscarBioAlba = document.getElementById('asig-btn-buscar-bioalba');
    if (btnBuscarBioAlba) {
        btnBuscarBioAlba.dataset.empleadoId = empleadoId;
        btnBuscarBioAlba.disabled = false;
        btnBuscarBioAlba.innerHTML = '<i class="bi bi-search me-1" aria-hidden="true"></i>Buscar 1.ª marca en BioAlba';
    }

    // Cargar Turnos del área
    const selectTurno = document.getElementById('asig-indiv-turno-id');
    selectTurno.innerHTML = '<option value="">Cargando turnos de ' + area + '...</option>';
    
    try {
        const t = Date.now();
        const resp = await fetch(`/api/turnos/?area=${encodeURIComponent(area)}&activo=true&_t=${t}`);
        if (!resp.ok) {
            const errText = await resp.text();
            throw new Error(`Status: ${resp.status} - ${errText}`);
        }
        const turnos = await resp.json();
        
        if (turnos.length === 0) {
            console.warn("\u26a0\ufe0f No se encontraron turnos para el \u00e1rea:", area);
            selectTurno.innerHTML = '<option value="">No hay turnos creados</option>';
            const alertaArea = document.getElementById('asig-indiv-alerta-area');
            alertaArea.textContent = 'No hay turnos creados para ' + area + '.';
            alertaArea.classList.add('text-danger');
        } else {
            selectTurno.innerHTML = '<option value="">Elegir turno</option>' +
                turnos.map(t => {
                    const tipoPlanificacion = (t.tipo_programacion === 'BOLSA_FLEXIBLE' || t.tipo_programacion === 'FLEXIBLE_BOLSA')
                        ? 'Bolsa Flexible'
                        : 'Ciclo Inteligente';
                    const horario = (t.tipo_programacion === 'CICLO_INTELIGENTE' || t.tipo_programacion === 'DINAMICO_FLEXIBLE')
                        ? '(Ciclo Rotativo/Fijo)'
                        : '';
                    return `<option value="${t.id}" data-tipo="${tipoPlanificacion}" data-horario="${horario}">${t.nombre}</option>`;
                }).join('');
            const alertaArea = document.getElementById('asig-indiv-alerta-area');
            alertaArea.textContent = 'Solo aparecen los turnos de ' + area + ' (' + turnos.length + ').';
            alertaArea.classList.remove('text-danger');
            
            // Trigger change event to initialize dynamic label
            selectTurno.removeEventListener('change', window.updateTurnoInfoLabel);
            selectTurno.addEventListener('change', window.updateTurnoInfoLabel);
            selectTurno.dispatchEvent(new Event('change'));
        }
    } catch (e) {
        console.error("\u274c Error cargando turnos para:", area, e);
        selectTurno.innerHTML = `<option value="">Error al cargar turnos (${e.message})</option>`;
    }

    // Resetear checkbox BioAlba (siempre marcado al abrir)
    const chkSync = document.getElementById('asig-chk-bioalba-sync');
    if (chkSync) chkSync.checked = true;

    // Restaurar botón confirmar (en caso de que quedara en spinner de uso previo)
    const btnConfirmar = document.getElementById('btn-confirmar-asignacion-individual');
    if (btnConfirmar) {
        btnConfirmar.disabled = false;
        btnConfirmar.textContent = 'Asignar';
    }

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}
// Exponer globalmente para que pueda ser llamada desde onclick en main.js
window.openAsignarTurnoForzado = openAsignarTurnoForzado;

// «Hoy» junto a la fecha de inicio: fecha local (toISOString daría el día siguiente después de las 21:00)
window.asigIndivHoy = function () {
    const d = new Date();
    document.getElementById('asig-indiv-fecha').value = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
};

// Búsqueda bajo demanda: RRHH decide cuándo buscar la primera marcación en BioAlba
window.buscarPrimeraMarcaBioAlba = async function(btn) {
    const empleadoId = btn?.dataset?.empleadoId;
    if (!empleadoId) return;

    const rowBioAlba = document.getElementById('asig-bioalba-row');
    const valBioAlba = document.getElementById('asig-bioalba-valor');
    const btnUsarFecha = document.getElementById('asig-btn-primera-marca');

    // Estado: buscando
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Consultando BioAlba...';
    if (rowBioAlba) {
        rowBioAlba.classList.remove('d-none');
        if (valBioAlba) valBioAlba.textContent = 'Buscando desde enero 2026...';
        if (btnUsarFecha) btnUsarFecha.classList.add('d-none');
    }

    try {
        const resp = await fetch(`/api/asistencia/empleados/${empleadoId}/primera-marcacion/`);
        const data = resp.ok ? await resp.json() : null;
        const primeraMarca = data?.primera_marcacion || null;

        if (primeraMarca) {
            if (valBioAlba) valBioAlba.textContent = window.formatFechaDDMMYYYY ? window.formatFechaDDMMYYYY(primeraMarca) : primeraMarca;
            if (btnUsarFecha) {
                btnUsarFecha.dataset.fecha = primeraMarca;
                btnUsarFecha.classList.remove('d-none');
            }
            btn.innerHTML = '<i class="bi bi-check-circle me-1 text-success"></i>BioAlba consultado';
        } else {
            if (valBioAlba) valBioAlba.textContent = data?.motivo || 'Sin marcaciones históricas en BioAlba';
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-search me-1" aria-hidden="true"></i>Buscar 1.ª marca en BioAlba';
        }
    } catch (e) {
        if (valBioAlba) valBioAlba.textContent = 'Error conectando a BioAlba';
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i>Reintentar';
    }
};

async function saveAsignacionIndividual() {
    const empleadoId = document.getElementById('asig-indiv-empleado-id').value;
    const fecha = document.getElementById('asig-indiv-fecha').value;
    const turnoId = document.getElementById('asig-indiv-turno-id').value;
    const nombre = document.getElementById('asig-indiv-nombre').innerText;

    // ── Detectar modo batch ───────────────────────────────────────────────────
    const isBatchTurnos = typeof _batch !== 'undefined' && _batch.active && _batch.phase === 'turnos';

    // En batch: nunca sincronizar individualmente; se hace todo junto en Fase Sync
    const syncBioAlba = isBatchTurnos
        ? false
        : (document.getElementById('asig-chk-bioalba-sync')?.checked ?? true);

    if (!fecha) return showToast("Falta la fecha de inicio.", "warning");
    if (!turnoId) return showToast("Falta elegir el turno.", "warning");

    // ── Spinner en botón ────────────────────────────────────────────────────
    const btn = document.getElementById('btn-confirmar-asignacion-individual');
    const btnOrigHtml = btn?.innerHTML;
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Procesando...';
    }

    try {
        const resp = await fetch('/api/asistencia/asignaciones/individual/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                empleado_id: parseInt(empleadoId),
                fecha: fecha,
                turno_id: parseInt(turnoId),
                sync_bioalba: syncBioAlba,
                skip_reproceso: isBatchTurnos,  // batch: solo guarda turno, sin reproceso individual
            })
        });

        if (resp.ok) {
            const data = await resp.json();
            const jobId = data.job_id || null;

            showToast("Listo. Turno asignado; se están calculando los días.", "success");

            // Cerrar modal de asignación
            const modalAsig = bootstrap.Modal.getInstance(document.getElementById('modal-asignar-turno-individual'));
            if (modalAsig) modalAsig.hide();

            // ── MODO BATCH: recolectar payload y avanzar cola ────────────────
            if (isBatchTurnos) {
                // Guardar datos para el batch-sync final
                if (typeof _batch !== 'undefined') {
                    _batch.syncPayload.push({
                        empleado_id: parseInt(empleadoId),
                        fecha_inicio: fecha,
                    });
                    console.log(
                        `[Batch/Turnos] Turno registrado para emp ${empleadoId} desde ${fecha}. ` +
                        `Payload: ${_batch.syncPayload.length} / ${_batch.editedEmployees.length}`
                    );
                }
                // Avanzar al siguiente empleado en la cola de turnos
                // (procesarColaOnboarding detectará si quedan más o lanzará batch-sync)
                if (typeof procesarColaOnboarding === 'function') {
                    setTimeout(procesarColaOnboarding, 400);
                }
                return;  // ← No abrir modal de progreso ni calibración en batch
            }

            // ── MODO INDIVIDUAL: flujo original con progreso y calibración ───
            if (jobId) {
                setTimeout(() => abrirModalProgresoJob(jobId, nombre, fecha, {
                    syncBioAlba,
                    onComplete: () => {
                        if (!(typeof _isOnboardingFlow !== 'undefined' && _isOnboardingFlow === false)) {
                            const turnoNombre = document.getElementById('asig-indiv-turno-id').options[
                                document.getElementById('asig-indiv-turno-id').selectedIndex
                            ]?.text || 'Turno Asignado';
                            openCalibracionHistorica({ empleadoId: parseInt(empleadoId), nombre, fecha, turnoNombre });
                        }
                    }
                }), 350);
            }

            // ── Flujo post-asignación sin job_id (fallback) ──────────────────
            if (!jobId) {
                if (typeof _isOnboardingFlow !== 'undefined' && _isOnboardingFlow === false) {
                    const isBlocked = await checkAuditoriaBloqueo();
                    if (!isBlocked) {
                        const modalReg = bootstrap.Modal.getInstance(document.getElementById('modal-regularizacion-asistencia'));
                        if (modalReg) modalReg.hide();
                        showToast("Listo. Los días quedaron calculados con el turno nuevo.", "success");
                        if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
                    }
                } else {
                    const turnoNombre = document.getElementById('asig-indiv-turno-id').options[
                        document.getElementById('asig-indiv-turno-id').selectedIndex
                    ]?.text || 'Turno Asignado';
                    setTimeout(() => openCalibracionHistorica({ empleadoId: parseInt(empleadoId), nombre, fecha, turnoNombre }), 350);
                }
            }

        } else {
            const err = await resp.json();
            showToast(err.detail || "No se pudo asignar el turno.", "danger");
        }
    } catch (e) {
        console.error(e);
        Avisos.sinConexion();
    } finally {
        // Restaurar botón siempre
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = btnOrigHtml || 'Asignar';
        }
    }
}



// =====================================================================
// [RFC PASO 7] MODAL DE CALIBRACIÓN HISTÓRICA
// =====================================================================

// Estado del contexto de calibración
let _calibContext = {};

function openCalibracionHistorica({ empleadoId, nombre, fecha, turnoNombre }) {
    _calibContext = { empleadoId, nombre, fecha, turnoNombre };

    // Poblar resumen del turno asignado
    document.getElementById('calib-emp-nombre').textContent = nombre;
    document.getElementById('calib-turno-nombre').textContent = turnoNombre;
    document.getElementById('calib-fecha-asignacion').textContent = fecha;

    // La fecha ya fue decidida por RRHH en el modal anterior → pasarla al campo oculto
    document.getElementById('calib-fecha-inicio').value = fecha;

    // Guardar el empleadoId para el sync individual
    const calibEmpId = document.getElementById('calib-empleado-id');
    if (calibEmpId) calibEmpId.value = empleadoId || '';

    // Mostrar la fecha en el botón de confirmación
    const displayFecha = document.getElementById('calib-fecha-display');
    if (displayFecha) displayFecha.textContent = fecha;

    // Resetear checkbox a su valor por defecto (marcado)
    const chkBioAlba = document.getElementById('calib-chk-bioalba');
    if (chkBioAlba) chkBioAlba.checked = true;

    const modalEl = document.getElementById('modal-calibracion-historica');
    if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();
}


// Omitir: solo confirmar que el turno quedó asignado; no reprocesar histórico
window.omitirCalibracion = function() {
    const modalEl = document.getElementById('modal-calibracion-historica');
    if (modalEl) bootstrap.Modal.getInstance(modalEl)?.hide();
    showToast("Listo. Turno asignado; los días anteriores no se recalcularon.", "info");
    // Continuar con el siguiente en la cola de onboarding (si existe)
    if (typeof procesarColaOnboarding === 'function' && typeof onboardingQueue !== 'undefined' && onboardingQueue.length > 0) {
        setTimeout(procesarColaOnboarding, 500);
    }
};

// Confirmar: cierra la modal Y lanza polling de progreso en background
window.confirmarCalibracion = async function() {
    const fechaInicio = document.getElementById('calib-fecha-inicio').value;
    if (!fechaInicio) return showToast("Falta la fecha de inicio.", "warning");

    const empleadoId = document.getElementById('calib-empleado-id')?.value;
    const syncBioAlba = document.getElementById('calib-chk-bioalba')?.checked ?? true;

    // 1. Cerrar modal de inmediato — NO bloquear al usuario
    const modalEl = document.getElementById('modal-calibracion-historica');
    if (modalEl) bootstrap.Modal.getInstance(modalEl)?.hide();

    // 2. Si el checkbox está marcado, disparar sync individual de BioAlba (fire-and-forget)
    if (syncBioAlba && empleadoId) {
        showToast("Trayendo las marcas desde BioAlba…", "info");
        // Fire-and-forget — el reproceso en background leerá las marcas cuando terminen de llegar
        fetch(`/api/sync/asistencia/empleado/${empleadoId}/?fecha_inicio=${fechaInicio}`, {
            method: 'POST'
        }).then(r => r.ok
            ? showToast("Listo. Llegaron las marcas de BioAlba; los días se vuelven a calcular.", "success")
            : showToast("No se pudieron traer las marcas de BioAlba.", "warning")
        ).catch(() => showToast("No hay conexión con BioAlba. Vuelva a intentarlo más tarde.", "warning"));
    }

    // 3. Iniciar polling de progreso (el reproceso ya está corriendo en background)
    iniciarPollingReproceso(_calibContext.empleadoId, _calibContext.nombre, fechaInicio);

    // 4. Continuar con el siguiente en la cola de onboarding
    if (typeof procesarColaOnboarding === 'function' && typeof onboardingQueue !== 'undefined' && onboardingQueue.length > 0) {
        setTimeout(procesarColaOnboarding, 500);
    }
};


// ==========================================================================
// F2: MODAL DE PROGRESO CON JOB_ID (Polling) — Dos fases: syncing + running
// ==========================================================================

let _reprocesoJobId = null;
let _reprocesoPollingTimer = null;

/**
 * Abre el modal de progreso y comienza el polling al endpoint /api/asistencia/jobs/{job_id}/.
 * Soporta dos fases secuenciales:
 *   Fase 1 (status='syncing'): descarga BioAlba
 *   Fase 2 (status='running'): reproceso día a día
 * @param {string} jobId   - ID del job
 * @param {string} nombre  - Nombre del empleado
 * @param {string} fechaDesde - Fecha de inicio
 * @param {object} opts    - { syncBioAlba: bool, onComplete: fn }
 */
function abrirModalProgresoJob(jobId, nombre, fechaDesde, opts = {}) {
    _reprocesoJobId = jobId;
    if (_reprocesoPollingTimer) clearInterval(_reprocesoPollingTimer);

    const { syncBioAlba = false, onComplete = null, allJobIds = null } = opts;
    let _onCompleteCallback = onComplete;
    const _allJobs = allJobIds || [jobId];  // Todos los jobs del batch

    // ── Resetear estado del modal ───────────────────────────────
    const el = id => document.getElementById(id);
    const syncLabel = syncBioAlba ? ' · con descarga de BioAlba' : '';
    // «13-10» a partir de «2026-10-13»
    const diaCorto = (f) => { const m = String(f || '').match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? m[3] + '-' + m[2] : String(f || ''); };
    const cerrarDiaEnCurso = (logEl) => {
        const previo = logEl.querySelector('.vn-ahora');
        if (previo) { previo.classList.remove('vn-ahora'); previo.textContent = previo.dataset.dia + ' calculado'; }
    };
    el('repr-emp-nombre').textContent = (window.nombreTitulo ? window.nombreTitulo(nombre) : nombre) + ' · desde el '
        + (window.formatFechaDDMMYYYY ? window.formatFechaDDMMYYYY(fechaDesde) : fechaDesde) + syncLabel;
    el('repr-header-title').textContent = syncBioAlba ? 'Descargando marcas y recalculando' : 'Recalculando asistencia';
    el('repr-progress-bar').style.width = '2%';
    el('repr-progress-bar').dataset.tono = '';
    el('repr-pct').textContent = '0 %';
    el('repr-day-label').textContent = syncBioAlba ? 'Descargando las marcas de BioAlba…' : 'Preparando…';
    el('repr-counter').textContent = syncBioAlba ? 'Paso 1 de 2 · descarga de BioAlba' : '';
    el('repr-log').innerHTML = '<div class="vn-espera">' + (syncBioAlba ? 'Conectando con BioAlba…' : 'Esperando el inicio…') + '</div>';
    el('repr-footer-completado').classList.add('d-none');
    el('repr-header-spinner').classList.remove('d-none');
    el('repr-header-ok').classList.add('d-none');

    // ── Abrir modal ─────────────────────────────────────────────
    const modalEl = document.getElementById('modal-reproceso-progreso');
    if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();

    let prevDayIndex = -1;
    let prevPhase = null;

    // ── Polling adaptativo ───────────────────────────────────────────────────
    // Durante 'syncing' (descarga BioAlba, lenta): intervalo crece hasta 4s.
    // Durante 'running' (cálculo día a día, rápido): vuelve a 1.5s.
    // Esto reduce requests innecesarios durante la fase de red sin sacrificar
    // la respuesta visual en la fase de cálculo.
    const POLL_FAST = 1500;   // ms — fase running / completado
    const POLL_SLOW = 4000;   // ms — fase syncing (BioAlba network bound)
    let _currentPollInterval = POLL_FAST;

    function _restartPolling(newInterval) {
        if (newInterval === _currentPollInterval) return; // ya en el intervalo correcto
        clearInterval(_reprocesoPollingTimer);
        _currentPollInterval = newInterval;
        _reprocesoPollingTimer = setInterval(_pollTick, _currentPollInterval);
    }

    async function _pollTick() {
        try {
            const r = await fetch(`/api/asistencia/jobs/${jobId}/`);
            if (!r.ok) return;
            const s = await r.json();

            // Job perdido (típicamente porque el contenedor se reinició durante un deploy)
            if (s.status === 'not_found') {
                clearInterval(_reprocesoPollingTimer);
                const bar = el('repr-progress-bar');
                bar.dataset.tono = 'atn';
                bar.style.width = '100%';
                el('repr-pct').textContent = '';
                el('repr-header-title').textContent = 'Recálculo interrumpido';
                el('repr-day-label').textContent = 'El servidor se reinició durante el recálculo.';
                el('repr-counter').textContent = 'Lo que alcanzó a descargarse quedó guardado.';
                el('repr-resumen-texto').textContent = 'Se interrumpió por una actualización del servidor. Las personas y marcas descargadas antes quedaron guardadas; puede volver a sincronizar desde la grilla.';
                const logEl = el('repr-log');
                const warnLine = document.createElement('div');
                warnLine.className = 'vn-mal';
                warnLine.textContent = 'El servidor se reinició y el recálculo quedó a medias';
                logEl.appendChild(warnLine);
                logEl.scrollTop = logEl.scrollHeight;
                el('repr-header-spinner').classList.add('d-none');
                el('repr-footer-completado').classList.remove('d-none');
                return;
            }

            const phase = s.status;      // 'syncing' | 'running' | 'done' | 'completed' | 'error'
            const pct = s.pct ?? 0;
            const isCompleted = phase === 'done' || phase === 'completed';  // backend usa 'done'
            const isError = phase === 'error';
            const isSyncing = phase === 'syncing';
            const isRunning = phase === 'running';

            // ── FASE: syncing (BioAlba) ───────────────────────────
            if (isSyncing) {
                _restartPolling(POLL_SLOW); // BioAlba es lento — reducir requests
                const phaseLabel = s.phase_label || 'Descargando las marcas de BioAlba…';
                el('repr-progress-bar').dataset.tono = '';
                // Actualizar barra proporcional al pct reportado por el backend
                el('repr-progress-bar').style.width = `${Math.max(pct, 2)}%`;
                el('repr-pct').textContent = `${pct} %`;
                el('repr-day-label').textContent = `${phaseLabel}`;
                el('repr-counter').textContent = 'Paso 1 de 2 · descarga de BioAlba';

                // Agregar entrada al log al cambiar de fase
                if (prevPhase !== 'syncing') {
                    prevPhase = 'syncing';
                    const logEl = el('repr-log');
                    const line = document.createElement('div');
                    line.textContent = 'Conectado con BioAlba: descargando las marcas…';
                    logEl.appendChild(line);
                    logEl.scrollTop = logEl.scrollHeight;
                }
                return;  // aún en fase 1, no actualizar barra animada de días
            }

            // ── TRANSICION syncing → running ───────────────────────
            if (isRunning && prevPhase !== 'running') {
                prevPhase = 'running';
                el('repr-progress-bar').dataset.tono = '';
                el('repr-header-title').textContent = 'Recalculando asistencia';
                // Log de transición
                const logEl = el('repr-log');
                const sep = document.createElement('div');
                sep.className = 'vn-ok';
                sep.textContent = 'Marcas descargadas · recalculando día a día';
                logEl.appendChild(sep);
                logEl.scrollTop = logEl.scrollHeight;
            }

            // ── FASE: running (reproceso día a día) ──────────────────
            if (isRunning) {
                _restartPolling(POLL_FAST); // Cálculo es rápido — volver a 1.5s
                el('repr-progress-bar').style.width = `${pct}%`;
                el('repr-pct').textContent = `${pct} %`;
                el('repr-day-label').textContent = 'Día ' + (s.day_index ?? 0) + ' de ' + (s.total_days ?? '?');
                el('repr-counter').textContent = syncBioAlba ? 'Paso 2 de 2 · recálculo' : '';

                // Log por cada día nuevo
                if (s.day_index !== prevDayIndex && s.current_day) {
                    prevDayIndex = s.day_index;
                    const logEl = el('repr-log');
                    cerrarDiaEnCurso(logEl);
                    const line = document.createElement('div');
                    line.className = 'vn-ahora';
                    line.dataset.dia = diaCorto(s.current_day);
                    line.textContent = line.dataset.dia + ' calculando…';
                    logEl.appendChild(line);
                    logEl.scrollTop = logEl.scrollHeight;
                }
                return;
            }

            // ── COMPLETADO ────────────────────────────────────────────
            if (isCompleted || isError) {
                // Si es un batch con múltiples jobs, verificar que TODOS terminaron
                if (_allJobs.length > 1 && isCompleted) {
                    try {
                        const allResponses = await Promise.all(
                            _allJobs.map(jid => fetch(`/api/asistencia/jobs/${jid}/`).then(r => r.json()))
                        );
                        const allDone = allResponses.every(j =>
                            j.status === 'done' || j.status === 'completed' || j.status === 'error'
                        );
                        if (!allDone) {
                            // Actualizar label para mostrar progreso del batch
                            const doneCount = allResponses.filter(j => j.status === 'done' || j.status === 'completed' || j.status === 'error').length;
                            el('repr-day-label').textContent = `${doneCount} de ${_allJobs.length} personas listas…`;
                            el('repr-progress-bar').style.width = `${Math.round(50 + 50 * doneCount / _allJobs.length)}%`;
                            return; // Seguir polling hasta que TODOS terminen
                        }
                    } catch (_) { /* error de red, reintentar en siguiente poll */ return; }
                }

                clearInterval(_reprocesoPollingTimer);

                const elapsed = ((s.elapsed_ms || 0) / 1000).toFixed(1);
                const bar = el('repr-progress-bar');
                bar.classList.remove('progress-bar-animated', 'progress-bar-striped');

                if (isError) {
                    bar.dataset.tono = 'mal';
                    el('repr-header-title').textContent = 'No se pudo recalcular';
                    el('repr-day-label').textContent = 'No se pudo terminar';
                    el('repr-resumen-texto').textContent = 'No se pudo recalcular: ' + (s.error || 'error desconocido') + '.';
                    const logEl = el('repr-log');
                    const errLine = document.createElement('div');
                    errLine.className = 'vn-mal';
                    errLine.textContent = `${s.error || 'Error desconocido'}`;
                    logEl.appendChild(errLine);
                } else {
                    bar.style.width = '100%';
                    bar.dataset.tono = '';
                    el('repr-pct').textContent = '100 %';
                    el('repr-header-title').textContent = 'Asistencia recalculada';
                    el('repr-day-label').textContent = 'Listo · la grilla ya muestra el resultado';
                    const bioAlbaNote = syncBioAlba ? ', con la descarga de BioAlba' : '';
                    el('repr-resumen-texto').textContent =
                        `${s.procesados} días recalculados en ${String(elapsed).replace('.', ',')} s${bioAlbaNote}` + (s.errores ? ` · ${s.errores} con error` : ' · sin errores');

                    const logEl = el('repr-log');
                    cerrarDiaEnCurso(logEl);
                    const okLine = document.createElement('div');
                    okLine.className = 'vn-ok';
                    okLine.textContent = `Listo: ${s.procesados} días`;
                    logEl.appendChild(okLine);
                    logEl.scrollTop = logEl.scrollHeight;

                    // Recargar grilla en background (sin esperar)
                    setTimeout(() => {
                        if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
                    }, 600);

                    // Ejecutar callback onComplete si fue pasado
                    if (_onCompleteCallback) {
                        setTimeout(_onCompleteCallback, 800);
                        _onCompleteCallback = null;
                    }
                }

                el('repr-header-spinner').classList.add('d-none');
                el('repr-header-ok').classList.remove('d-none');
                el('repr-footer-completado').classList.remove('d-none');
            }

        } catch (err) { /* error de red transitorio: ignorar */ }
    }

    // Arrancar polling con intervalo inicial (fast: 1.5s)
    _reprocesoPollingTimer = setInterval(_pollTick, _currentPollInterval);
}



/** Cierra el modal de progreso y detiene el polling. */
window.cerrarModalReproceso = function() {
    if (_reprocesoPollingTimer) {
        clearInterval(_reprocesoPollingTimer);
        _reprocesoPollingTimer = null;
    }
    const modalEl = document.getElementById('modal-reproceso-progreso');
    if (modalEl) bootstrap.Modal.getInstance(modalEl)?.hide();
};


/**
 * Legacy wrapper — usado por confirmarCalibracion (que aún no tiene job_id).
 * Dejamos compatibilidad del nombre original.
 */
function iniciarPollingReproceso(empleadoId, nombre, fechaDesde) {
    // En el flujo de Calibración, el reproceso ya corrió desde saveAsignacionIndividual.
    // Solo mostramos un banner informativo liviano sin polling.
    showToast(`Reprocesando a ${nombre} desde el ${(window.formatFechaDDMMYYYY ? window.formatFechaDDMMYYYY(fechaDesde) : fechaDesde)}. La grilla se actualiza al terminar.`, 'info');
}




window.cierreFiltrarGrillaYIniciarCierre = async function(fIni, fFin) {
    const areaVal = document.getElementById('cierre-area-select')?.value;
    if (!areaVal) {
        return showToast("Falta elegir un área.", "warning");
    }

    // 1. Cerrar modal selector
    const modalEl = document.getElementById('modal-seleccionar-periodo-cierre');
    if (modalEl) {
        bootstrap.Modal.getInstance(modalEl)?.hide();
    }

    // 2. Actualizar fechas y área del estado y DOM
    stateMarcacionesApp.fechaInicioRRHH = fIni;
    stateMarcacionesApp.fechaFinRRHH = fFin;
    stateMarcacionesApp.area = areaVal;
    
    const inputIni = document.getElementById('rrhh-fecha-inicio');
    const inputFin = document.getElementById('rrhh-fecha-fin');
    if (inputIni) inputIni.value = fIni;
    if (inputFin) inputFin.value = fFin;
    
    const selectArea = document.getElementById('marcacion-area');
    if (selectArea) selectArea.value = areaVal;

    // 3. Forzar el recargado de la grilla de asistencia
    showToast(`Mostrando el área ${areaVal} en el período elegido…`, "info");
    await loadMarcacionesData();

    // 4. Lanzar asistente de cierre tras cargar la grilla
    setTimeout(() => {
        openCierrePeriodoModal();
    }, 600);
};

// Desde el Dashboard («Lo que falta hacer»): va a Marcaciones, espera la grilla, la filtra por
// el área y el tramo pedidos y, según la acción, abre el asistente de cierre, los días por
// revisar o la columna de horas extra. El Dashboard no cambia nada: solo lleva aquí.
window.abrirMarcacionesDesde = async function({ area = '', desde = '', hasta = '', accion = 'grilla' } = {}) {
    if (typeof switchPage === 'function') switchPage('marcaciones');
    for (let i = 0; i < 40 && !(stateMarcacionesApp.data && stateMarcacionesApp.data.matrix); i++) {
        await new Promise(r => setTimeout(r, 350));
    }
    if (desde && hasta) {
        stateMarcacionesApp.fechaInicioRRHH = desde;
        stateMarcacionesApp.fechaFinRRHH = hasta;
        const inputIni = document.getElementById('rrhh-fecha-inicio');
        const inputFin = document.getElementById('rrhh-fecha-fin');
        if (inputIni) inputIni.value = desde;
        if (inputFin) inputFin.value = hasta;
    }
    stateMarcacionesApp.area = area || 'Todas';
    const selectArea = document.getElementById('marcacion-area');
    if (selectArea) selectArea.value = stateMarcacionesApp.area;
    if (accion === 'he' && window.vistaAnaliticaState) window.vistaAnaliticaState.showHE = true;
    await loadMarcacionesData();
    if (accion === 'cierre') {
        setTimeout(() => openCierrePeriodoModal(), 600);
    } else if (accion === 'revisar') {
        await window.actualizarPorRevisar();
        window.abrirPanelPorRevisar();
    }
};

window.cierreActualizarSeleccionDeArea = function(areaVal) {
    // Actualizar state principal
    stateMarcacionesApp.area = areaVal;
    
    // Sincronizar select de la barra de herramientas principal
    const mainAreaSelect = document.getElementById('marcacion-area');
    if (mainAreaSelect) mainAreaSelect.value = areaVal;
    
    // Habilitar/Deshabilitar botones de cierre
    const buttons = document.querySelectorAll('.btn-cierre-action');
    buttons.forEach(btn => {
        if (areaVal) {
            btn.disabled = false;
            btn.title = "Filtrar y Cerrar";
        } else {
            btn.disabled = true;
            btn.title = "Debe seleccionar un área primero";
        }
    });
};

/**
 * [NUEVO] Abre el Asistente Zero-Trust de Cierre de Periodo RRHH.
 */
/**
 * [NUEVO] Abre el Asistente Zero-Trust de Cierre de Periodo RRHH.
 */
async function openCierrePeriodoModal() {
    // Obtener la lista de periodos oficiales configurados para cruzar
    let periodos = [];
    try {
        const resp = await fetch('/api/configuracion/periodos/', {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
        });
        if (resp.ok) {
            periodos = await resp.json();
        }
    } catch (e) {
        console.error("Error al obtener periodos:", e);
    }

    // Obtener las áreas desde el select principal
    const areaSelectDOM = document.getElementById('marcacion-area');
    let areas = [];
    if (areaSelectDOM) {
        areas = Array.from(areaSelectDOM.options)
            .map(opt => opt.value)
            .filter(val => val !== "" && val !== "Todas");
    }

    // Priorizar el período correspondiente a las fechas filtradas en la grilla principal
    const periodFromGrid = periodos.find(p => p.fecha_inicio === stateMarcacionesApp.fechaInicioRRHH && p.fecha_fin === stateMarcacionesApp.fechaFinRRHH);
    const vigentePeriodo = periodFromGrid || periodos.find(p => p.estado === 'abierto' && (p.activo === 1 || p.activo === true));
    
    const fIni = stateMarcacionesApp.fechaInicioRRHH || (vigentePeriodo ? vigentePeriodo.fecha_inicio : "");
    const fFin = stateMarcacionesApp.fechaFinRRHH || (vigentePeriodo ? vigentePeriodo.fecha_fin : "");
    const area = (stateMarcacionesApp.area === 'Todas' || !stateMarcacionesApp.area) ? "" : stateMarcacionesApp.area;

    const html = `
        <div class="modal fade" id="modal-cierre-wizard" tabindex="-1" data-bs-backdrop="static">
            <div class="modal-dialog modal-xl">
                <div class="modal-content border-0 shadow-lg">
                    <div class="modal-header bg-dark text-white border-0">
                        <h5 class="modal-title fw-bold"><i class="bi bi-shield-lock-fill text-warning me-2"></i> Cierre del período</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body bg-light p-4">
                        <div class="row">
                            <div class="col-md-3">
                                <div class="list-group list-group-flush mb-4 rounded shadow-sm">
                                    <button class="list-group-item list-group-item-action fw-bold" id="wiz-tab-0" disabled><i class="bi bi-gear-fill text-secondary me-2"></i> Parámetros</button>
                                    <button class="list-group-item list-group-item-action fw-bold" id="wiz-tab-1" disabled><i class="bi bi-exclamation-triangle-fill text-danger me-2"></i> 1. Anomalías</button>
                                    <button class="list-group-item list-group-item-action fw-bold" id="wiz-tab-2" disabled><i class="bi bi-clock-fill text-warning me-2"></i> 2. En curso</button>
                                    <button class="list-group-item list-group-item-action fw-bold" id="wiz-tab-3" disabled><i class="bi bi-calendar-plus text-primary me-2"></i> 3. Horas extra</button>
                                    <button class="list-group-item list-group-item-action fw-bold" id="wiz-tab-4" disabled><i class="bi bi-person-dash text-info me-2"></i> 4. Inasistencias</button>
                                    <button class="list-group-item list-group-item-action fw-bold" id="wiz-tab-5" disabled><i class="bi bi-file-earmark-pdf text-success me-2"></i> 5. Resumen antes de sellar</button>
                                </div>
                                <div class="card border-0 bg-white shadow-sm p-3 mb-3">
                                    <h6 class="fw-bold mb-2 small" style="color: #475569"><i class="bi bi-calendar-check text-primary me-1"></i> Período a cerrar</h6>
                                    
                                    <div id="cierre-periodo-badge-container" class="mb-2"></div>
                                    
                                    <div class="small text-muted mb-0">
                                        Tramo: <strong id="cierre-rango-text">${fIni && fFin ? `${window.formatFechaDDMMYYYY(fIni)} al ${window.formatFechaDDMMYYYY(fFin)}` : 'Sin definir'}</strong><br>
                                        Área: <strong id="cierre-area-sidebar">${area || 'No seleccionada'}</strong>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-9 bg-white border rounded shadow-sm p-4 position-relative" id="wizard-content" style="min-height: 400px;">
                                <!-- Contenido dinámico del paso -->
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer bg-white border-top">
                        <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cerrar</button>
                        <button type="button" class="btn btn-dark fw-bold px-4" id="btn-cierre-wizard-next" style="display:none;" onclick="nextWizardStep()">
                            Siguiente Paso <i class="bi bi-arrow-right"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    const old = document.getElementById('modal-cierre-wizard');
    if (old) old.remove();

    document.body.insertAdjacentHTML('beforeend', html);
    const modal = new bootstrap.Modal(document.getElementById('modal-cierre-wizard'));
    modal.show();

    window.cierreWizardState = { 
        currentStep: 0, 
        evaluacion: null, 
        fIni, 
        fFin, 
        area, 
        aceptarInasistencias: false,
        periodos: periodos,
        areas: areas
    };

    // Actualizar badge e info del periodo en el sidebar
    actualizarInfoPeriodoEnWizard();

    // Renderizar Paso 0
    renderWizardStep(0);
}

/**
 * Actualiza el badge visual del período en el panel lateral del wizard
 */
window.actualizarInfoPeriodoEnWizard = function() {
    const s = window.cierreWizardState;
    const fIni = s.fIni || "";
    const fFin = s.fFin || "";
    const area = s.area || "";
    
    const badgeContainer = document.getElementById('cierre-periodo-badge-container');
    const rangoText = document.getElementById('cierre-rango-text');
    const areaSidebar = document.getElementById('cierre-area-sidebar');
    
    if (rangoText) rangoText.innerHTML = fIni && fFin ? `${window.formatFechaDDMMYYYY(fIni)} al ${window.formatFechaDDMMYYYY(fFin)}` : '<i>Sin definir</i>';
    if (areaSidebar) areaSidebar.textContent = area || 'No seleccionada';
    
    if (!fIni || !fFin) {
        if (badgeContainer) badgeContainer.innerHTML = '';
        return;
    }

    let matchedPeriod = s.periodos.find(p => p.fecha_inicio === fIni && p.fecha_fin === fFin);
    
    if (matchedPeriod) {
        if (badgeContainer) {
            const estadoBadge = matchedPeriod.estado === 'cerrado' 
                ? '<span class="badge bg-danger"><i class="bi bi-lock-fill"></i> Cerrado</span>' 
                : '<span class="badge bg-success"><i class="bi bi-unlock-fill"></i> Abierto</span>';
            badgeContainer.innerHTML = `
                <div class="fw-bold text-success mb-1" style="font-size:0.95rem;">
                    <i class="bi bi-calendar-check-fill"></i> ${matchedPeriod.mes_cierre}
                </div>
                ${estadoBadge} ${matchedPeriod.activo ? '<span class="badge bg-primary">Vigente</span>' : ''}
            `;
        }
    } else {
        if (badgeContainer) {
            badgeContainer.innerHTML = `
                <div class="alert alert-warning py-1 px-2 mb-1 small border-warning">
                    <i class="bi bi-exclamation-triangle-fill"></i> Rango Personalizado
                </div>
                <span class="text-muted small" style="font-size:0.75rem;">No coincide con períodos RRHH configurados.</span>
            `;
        }
    }
}

function updateWizardTabs(step) {
    const tab0 = document.getElementById('wiz-tab-0');
    if (tab0) {
        if (step === 0) {
            tab0.classList.add('active');
            tab0.classList.remove('bg-light', 'text-muted');
        } else {
            tab0.classList.remove('active');
            tab0.classList.add('bg-light', 'text-muted');
        }
    }

    for (let i = 1; i <= 5; i++) {
        const tab = document.getElementById(`wiz-tab-${i}`);
        if (tab) {
            if (i === step) {
                tab.classList.add('active');
                tab.classList.remove('bg-light', 'text-muted');
            } else if (i < step) {
                tab.classList.remove('active');
                tab.classList.add('bg-light', 'text-muted');
            } else {
                tab.classList.remove('active', 'bg-light', 'text-muted');
            }
        }
    }
}

window.cierreWizardCambiarArea = async function(val) {
    window.cierreWizardState.area = val;
    
    if (val) {
        try {
            const resp = await fetch(`/api/configuracion/periodos/activo/${encodeURIComponent(val)}/`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
            });
            if (resp.ok) {
                const activePeriod = await resp.json();
                if (activePeriod && activePeriod.fecha_inicio && activePeriod.fecha_fin) {
                    window.cierreWizardState.fIni = activePeriod.fecha_inicio;
                    window.cierreWizardState.fFin = activePeriod.fecha_fin;
                }
            }
        } catch (e) {
            console.error("Error al obtener periodo activo para el área en el wizard:", e);
        }
    }
    
    if (typeof renderWizardStep === 'function') {
        renderWizardStep(0);
    }
    actualizarInfoPeriodoEnWizard();
};

window.cierreWizardSeleccionarPeriodo = function(val) {
    if (val === 'custom') {
        const inputIni = document.getElementById('cierre-wizard-fini');
        const inputFin = document.getElementById('cierre-wizard-ffin');
        if (inputIni) inputIni.removeAttribute('readonly');
        if (inputFin) inputFin.removeAttribute('readonly');
    } else {
        const [fIni, fFin] = val.split('|');
        window.cierreWizardState.fIni = fIni;
        window.cierreWizardState.fFin = fFin;
        
        const inputIni = document.getElementById('cierre-wizard-fini');
        const inputFin = document.getElementById('cierre-wizard-ffin');
        if (inputIni) {
            inputIni.value = fIni;
            inputIni.setAttribute('readonly', 'true');
        }
        if (inputFin) {
            inputFin.value = fFin;
            inputFin.setAttribute('readonly', 'true');
        }
        
        if (typeof renderWizardStep === 'function') {
            renderWizardStep(0);
        }
        actualizarInfoPeriodoEnWizard();
    }
};

window.cierreWizardCambiarFechasManual = function() {
    window.cierreWizardState.fIni = document.getElementById('cierre-wizard-fini')?.value || "";
    window.cierreWizardState.fFin = document.getElementById('cierre-wizard-ffin')?.value || "";
    
    const btnIniciar = document.getElementById('btn-cierre-wizard-iniciar');
    if (btnIniciar) {
        btnIniciar.disabled = (!window.cierreWizardState.fIni || !window.cierreWizardState.fFin);
    }
    
    actualizarInfoPeriodoEnWizard();
};

window.cierreWizardConfirmarParametros = async function() {
    const s = window.cierreWizardState;
    const area = s.area;
    const fIni = s.fIni;
    const fFin = s.fFin;

    if (!area) {
        return showToast("Falta elegir un área.", "warning");
    }
    if (!fIni || !fFin) {
        return showToast("Faltan las fechas de inicio y fin.", "warning");
    }

    if (fIni > fFin) {
        return showToast("La fecha de inicio no puede ser después de la fecha de fin.", "warning");
    }

    // Validar bloqueo hoy
    const today = new Date().toISOString().split('T')[0];
    if (today >= fIni && today <= fFin) {
        return showToast("No se puede cerrar un período que incluye el día de hoy.", "warning");
    }

    // Validar límite de 35 días
    const dIni = new Date(fIni);
    const dFin = new Date(fFin);
    const diffTime = Math.abs(dFin - dIni);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1;
    if (diffDays > 35) {
        return showToast(`El rango elegido tiene ${diffDays} días; el máximo para cerrar es 35.`, "warning");
    }

    // 1. Sincronizar el estado global de la aplicación
    stateMarcacionesApp.area = area;
    stateMarcacionesApp.fechaInicioRRHH = fIni;
    stateMarcacionesApp.fechaFinRRHH = fFin;

    // 2. Sincronizar los filtros en el DOM de la grilla principal
    const mainAreaSelect = document.getElementById('marcacion-area');
    if (mainAreaSelect) mainAreaSelect.value = area;

    const mainFIni = document.getElementById('rrhh-fecha-inicio');
    if (mainFIni) mainFIni.value = fIni;

    const mainFFin = document.getElementById('rrhh-fecha-fin');
    if (mainFFin) mainFFin.value = fFin;

    // 3. Forzar el recargado de la grilla de asistencia en segundo plano
    showToast(`Mostrando el área ${area} en las fechas elegidas…`, "info");
    if (typeof loadMarcacionesData === 'function') {
        loadMarcacionesData(); // se ejecuta en background
    }

    // 4. Mostrar spinner y proceder con la pre-evaluación
    const content = document.getElementById('wizard-content');
    content.innerHTML = `
        <div class="text-center py-5">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="mt-3 text-muted fw-bold">Pre-evaluando integridad de datos para el área: ${area}...</p>
        </div>
    `;

    try {
        const url = `/api/cierre/pre-evaluacion?fecha_inicio=${fIni}&fecha_fin=${fFin}&area=${encodeURIComponent(area)}`;
        const resp = await fetch(url, { headers: { 'Authorization': `Bearer ${AuthService.getToken()}` } });
        const data = await resp.json();
        
        if (!resp.ok) throw new Error(data.detail || "Fallo en pre-evaluación");
        
        window.cierreWizardState.evaluacion = data;
        renderWizardStep(1);
    } catch (e) {
        content.innerHTML = `
            <div class="alert alert-danger py-4">
                <h5><i class="bi bi-x-circle-fill text-danger me-2"></i> Error de Validación</h5>
                <p class="mb-3">${e.message}</p>
                <div class="d-flex gap-2">
                    <button class="btn btn-sm btn-outline-danger" onclick="cierreWizardConfirmarParametros()">
                        <i class="bi bi-arrow-clockwise"></i> Reintentar
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="renderWizardStep(0)">
                        <i class="bi bi-chevron-left"></i> Volver a Parámetros
                    </button>
                </div>
            </div>
        `;
    }
};

function cierreGetHEContextBadges(a) {
    let tags = [];
    
    // 1. Colación: Bajo regla canónica, tomar menos descanso no genera sobretiempo (omitido)
    
    // 2. Llegada Temprana Efectiva (Fuera del margen de anclaje)
    if (a.hora_entrada_teorica && a.hora_entrada_real) {
        let diffEntradaMin = Math.round(-window.circularTimeDiff(a.hora_entrada_teorica, a.hora_entrada_real)); 
        let obsLlegada = (a.observaciones || '').toLowerCase();
        if (diffEntradaMin > 0 && obsLlegada.includes('llegada anticipada') && obsLlegada.includes('fuera del anclaje')) {
            tags.push(`<span class="badge bg-primary-subtle text-primary-emphasis border border-primary-subtle ms-2"><i class="bi bi-box-arrow-in-right"></i> +${formatExactMinutesToTime(diffEntradaMin)} (Ingreso Anticipado)</span>`);
        }
    }
    
    // 3. Salida Tardía Efectiva
    if (a.hora_salida_teorica && a.hora_salida_real) {
        let diffSalidaMin = Math.round(window.circularTimeDiff(a.hora_salida_teorica, a.hora_salida_real));
        let obsSalida = (a.observaciones || '').toLowerCase();
        if (diffSalidaMin > 0 && !obsSalida.includes('salida dentro del anclaje')) {
            tags.push(`<span class="badge bg-primary-subtle text-primary-emphasis border border-primary-subtle ms-2"><i class="bi bi-box-arrow-right"></i> +${formatExactMinutesToTime(diffSalidaMin)} (Salida Tardía)</span>`);
        }
    }
    
    // Fallback si no identificó nada específico pero hay horas extras
    if (tags.length === 0) {
        tags.push(`<span class="badge bg-light text-secondary border border-secondary-subtle ms-2 text-uppercase" style="font-size: 0.6875rem;"><i class="bi bi-tag-fill me-1"></i>Exceso Jornada</span>`);
    }
    
    return tags.join('');
}

function renderWizardStep(step) {
    window.cierreWizardState.currentStep = step;
    updateWizardTabs(step);
    const content = document.getElementById('wizard-content');
    const btnNext = document.getElementById('btn-cierre-wizard-next');
    const s = window.cierreWizardState;

    if (step === 0) {
        btnNext.style.display = 'none';

        // Buscar el periodo que corresponde a las fechas configuradas en el wizard (s.fIni / s.fFin)
        let vigente = s.periodos.find(p => p.fecha_inicio === s.fIni && p.fecha_fin === s.fFin);
        
        // Fallback al periodo vigente activo de la DB si no coincide con ninguno
        if (!vigente && (!s.fIni || !s.fFin)) {
            vigente = s.periodos.find(p => p.estado === 'abierto' && (p.activo === 1 || p.activo === true));
            if (vigente) {
                s.fIni = vigente.fecha_inicio;
                s.fFin = vigente.fecha_fin;
            }
        }

        // Opciones de área
        const areasOptions = s.areas.map(a => {
            const isSelected = a === s.area ? 'selected' : '';
            return `<option value="${a}" ${isSelected}>${a}</option>`;
        }).join('');

        // Opciones de período
        const periodosOptions = s.periodos.map(p => {
            const isSelected = (p.fecha_inicio === s.fIni && p.fecha_fin === s.fFin) ? 'selected' : '';
            const label = window.mxEtiquetaPeriodo(p, s.area);
            return `<option value="${p.fecha_inicio}|${p.fecha_fin}" ${isSelected}>${label}</option>`;
        }).join('');
        
        const isCustom = !s.periodos.some(p => p.fecha_inicio === s.fIni && p.fecha_fin === s.fFin);

        let periodInfoHtml = '';
        if (vigente) {
            const fIniFormateada = vigente.fecha_inicio.split('-').reverse().join('-');
            const fFinFormateada = vigente.fecha_fin.split('-').reverse().join('-');
            
            periodInfoHtml = `
                <div class="card border-0 shadow-sm p-3 h-100 bg-white border border-success-subtle" style="border-left: 4px solid #10b981 !important;">
                    <div class="fw-bold text-success small mb-2">
                        <i class="bi bi-calendar-check-fill me-1"></i> Período a cerrar
                    </div>
                    <div class="fw-bold text-dark fs-5 mb-1">${vigente.mes_cierre}</div>
                    <div class="small text-muted mb-2">
                        <i class="bi bi-calendar-range me-1"></i> Tramo: <strong>${fIniFormateada} al ${fFinFormateada}</strong>
                    </div>
                    ${window.mxPeriodoCerradoParaArea(vigente, s.area) 
                        ? '<span class="badge bg-danger-subtle text-danger border border-danger-subtle align-self-start"><i class="bi bi-lock-fill me-1"></i> Período Cerrado</span>'
                        : '<span class="badge bg-success-subtle text-success border border-success-subtle align-self-start"><i class="bi bi-unlock-fill me-1"></i> Período Abierto & Vigente</span>'
                    }
                </div>
            `;
        } else if (s.fIni && s.fFin) {
            const fIniFormateada = s.fIni.split('-').reverse().join('-');
            const fFinFormateada = s.fFin.split('-').reverse().join('-');
            periodInfoHtml = `
                <div class="card border-0 shadow-sm p-3 h-100 bg-white border border-warning-subtle" style="border-left: 4px solid #f59e0b !important;">
                    <div class="fw-bold text-warning small mb-2">
                        <i class="bi bi-exclamation-triangle-fill me-1"></i> Rango Personalizado:
                    </div>
                    <div class="fw-bold text-dark fs-6 mb-1">Rango Fuera de Calendario</div>
                    <div class="small text-muted mb-2">
                        <i class="bi bi-calendar-range me-1"></i> Tramo: <strong>${fIniFormateada} al ${fFinFormateada}</strong>
                    </div>
                    <span class="badge bg-warning-subtle text-warning border border-warning-subtle align-self-start">
                        No oficial
                    </span>
                </div>
            `;
        } else {
            periodInfoHtml = `
                <div class="card border-0 shadow-sm p-3 h-100 bg-white border border-danger-subtle" style="border-left: 4px solid #ef4444 !important;">
                    <div class="fw-bold text-danger small mb-2">
                        <i class="bi bi-exclamation-triangle-fill me-1"></i> Período a cerrar
                    </div>
                    <div class="text-danger fw-bold mb-2">Período No Definido</div>
                    <p class="small text-muted mb-0">
                        Seleccione un período oficial o ingrese un rango de fechas válido.
                    </p>
                </div>
            `;
        }

        content.innerHTML = `
            <div class="py-2">
                <h4 class="fw-bold text-dark mb-3"><i class="bi bi-gear-fill text-secondary me-2"></i> Elegir área y período</h4>
                <p class="text-muted small">
                    Seleccione el área y el período o rango de fechas que desea evaluar para el cierre. Al continuar, se pre-evaluarán las anomalías y el estado del período.
                </p>
                
                <div class="row g-3 mt-2">
                    <!-- Selección de Área y Período -->
                    <div class="col-md-6">
                        <div class="card border-0 shadow-sm p-3 bg-light mb-3">
                            <label for="cierre-wizard-area-select" class="form-label fw-bold text-secondary small mb-2">
                                <i class="bi bi-geo-alt-fill text-danger me-1"></i> 1. Área
                            </label>
                            <select class="form-select border-primary-subtle" id="cierre-wizard-area-select" onchange="cierreWizardCambiarArea(this.value)">
                                <option value="">-- Seleccione un Área --</option>
                                ${areasOptions}
                            </select>
                        </div>

                        <div class="card border-0 shadow-sm p-3 bg-light">
                            <label for="cierre-wizard-periodo-select" class="form-label fw-bold text-secondary small mb-2">
                                <i class="bi bi-calendar-check text-primary me-1"></i> 2. Período
                            </label>
                            <select class="form-select border-primary-subtle mb-3" id="cierre-wizard-periodo-select" onchange="cierreWizardSeleccionarPeriodo(this.value)">
                                ${periodosOptions}
                                <option value="custom" ${isCustom ? 'selected' : ''}>-- Rango Personalizado --</option>
                            </select>

                            <div class="row g-2">
                                <div class="col-6">
                                    <label for="cierre-wizard-fini" class="form-label small fw-semibold text-muted mb-1">Desde</label>
                                    <input type="date" class="form-control form-control-sm" id="cierre-wizard-fini" value="${s.fIni || ''}" ${!isCustom ? 'readonly' : ''} onchange="cierreWizardCambiarFechasManual()">
                                </div>
                                <div class="col-6">
                                    <label for="cierre-wizard-ffin" class="form-label small fw-semibold text-muted mb-1">Hasta</label>
                                    <input type="date" class="form-control form-control-sm" id="cierre-wizard-ffin" value="${s.fFin || ''}" ${!isCustom ? 'readonly' : ''} onchange="cierreWizardCambiarFechasManual()">
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Resumen del Período -->
                    <div class="col-md-6">
                        ${periodInfoHtml}
                    </div>
                </div>

                <!-- Botón de Envío -->
                <div class="mt-4 text-end">
                    <button class="btn btn-primary fw-bold px-4 py-2 shadow-sm" 
                            id="btn-cierre-wizard-iniciar" 
                            ${(!s.fIni || !s.fFin) ? 'disabled' : ''} 
                            onclick="cierreWizardConfirmarParametros()">
                        <i class="bi bi-search me-1"></i> Revisar el período
                    </button>
                </div>
            </div>
        `;
        return;
    }

    const ev = s.evaluacion;

    if (step === 1) { // Anomalías y Días por revisar (Reglas de marcaciones)
        const porRevisar = ev.dias_por_revisar || 0;
        const porRevisarHtml = porRevisar > 0 ? `
                <h5 class="text-danger fw-bold mt-3"><i class="bi bi-exclamation-triangle-fill"></i> Días por revisar (Reglas de marcaciones)</h5>
                <p class="mb-2">Hay <strong>${porRevisar} días</strong> que una regla dejó en revisión. Corrija sus marcas o confírmelos en «Marcaciones del día» antes de cerrar.</p>
                <div class="border rounded-3 shadow-sm bg-white mb-3" style="max-height:220px; overflow-y:auto;">
                    <ul class="list-unstyled mb-0">${(ev.detalle_por_revisar || []).map(d => {
                        const nEsc = (d.persona || '').replace(/'/g, "\\'");
                        return `
                        <li class="d-flex justify-content-between align-items-center py-2 px-3 border-bottom">
                            <div class="small"><span class="fw-bold">${window.formatFechaDDMMYYYY(d.fecha)}</span>
                                <span class="mx-2 text-muted">|</span>${d.persona}
                                <span class="badge bg-warning-subtle text-warning-emphasis ms-2" style="font-size:0.72rem;">Secuencia ${(d.secuencia || '').split('').map(c => c === 'E' ? 'ENTRADA' : (c === 'S' ? 'SALIDA' : c)).join(' · ')}</span>
                                <span class="text-muted ms-2">${d.estado || ''}</span></div>
                            <button class="btn btn-sm btn-outline-primary fw-bold py-1 px-3" onclick="openManualEntryModal(${d.empleado_id}, '${d.fecha}', '${nEsc}')">
                                <i class="bi bi-pencil-square me-1"></i> Abrir
                            </button>
                        </li>`;
                    }).join('')}</ul>
                </div>` : '';
        if (porRevisar > 0 && !(ev.anomalias > 0)) {
            content.innerHTML = `
                <h4 class="text-danger fw-bold"><i class="bi bi-shield-x"></i> HARD STOP: Días por revisar</h4>
                ${porRevisarHtml}
            `;
            btnNext.style.display = 'none';
        } else if (ev.anomalias > 0) {
            const list = ev.detalle_anomalias.map(a => {
                const nameEscaped = (a.nombre_completo || '').replace(/'/g, "\\'");
                return `
                    <li class="d-flex justify-content-between align-items-center py-2 px-3 border-bottom hover-bg-light">
                        <div class="d-flex align-items-center">
                            <i class="bi bi-exclamation-triangle-fill text-danger me-2"></i>
                            <div>
                                <span class="fw-bold text-dark small">${window.formatFechaDDMMYYYY(a.fecha)}</span>
                                <span class="mx-2 text-muted">|</span>
                                <span class="text-secondary small">${a.nombre_completo}</span>
                                ${a.hora_entrada_real || a.hora_salida_real ? `
                                    <span class="badge bg-warning-subtle text-warning-emphasis ms-2" style="font-size: 0.75rem;">
                                        <i class="bi bi-clock-fill me-1"></i>${a.hora_entrada_real || '--:--'} / ${a.hora_salida_real || '--:--'}
                                    </span>
                                ` : ''}
                            </div>
                        </div>
                        <button class="btn btn-sm btn-outline-primary fw-bold py-1 px-3 shadow-sm" 
                                onclick="window.cierreCorregirAnomalia(${a.empleado_id}, '${a.fecha}', '${nameEscaped}', '${a.hora_entrada_real || ''}', '${a.hora_salida_real || ''}')">
                            <i class="bi bi-pencil-square me-1"></i> Corregir
                        </button>
                    </li>
                `;
            }).join('');
            content.innerHTML = `
                <h4 class="text-danger fw-bold"><i class="bi bi-shield-x"></i> HARD STOP: Anomalías Detectadas</h4>
                <p>Se encontraron <strong>${ev.anomalias} anomalías</strong> que bloquean el cierre. Debes solucionarlas antes de continuar.</p>
                <div class="border rounded-3 shadow-sm bg-white" style="max-height:250px; overflow-y:auto;">
                    <ul class="list-unstyled mb-0">${list}</ul>
                </div>
                ${porRevisarHtml}
            `;
            btnNext.style.display = 'none';
        } else {
            content.innerHTML = `
                <div class="text-center py-5">
                    <i class="bi bi-check-circle-fill text-success" style="font-size: 4rem;"></i>
                    <h4 class="mt-3">Sin Anomalías ni días por revisar</h4>
                    <p class="text-muted">Las marcaciones están íntegras. Puede continuar al siguiente paso.</p>
                </div>
            `;
            btnNext.style.display = 'inline-block';
            btnNext.innerHTML = 'Siguiente Paso <i class="bi bi-arrow-right"></i>';
            btnNext.className = 'btn btn-dark fw-bold px-4';
            btnNext.onclick = () => renderWizardStep(2);
        }
    } else if (step === 2) { // En Curso
        if (ev.en_curso > 0) {
            const list = ev.detalle_en_curso.map(a => `<li>${a.fecha} - ${a.nombre_completo} (Salida teórica: ${a.hora_salida_teorica || 'N/A'})</li>`).join('');
            content.innerHTML = `
                <h4 class="text-warning fw-bold"><i class="bi bi-clock-history"></i> HARD STOP: Turnos en Curso</h4>
                <p>Hay <strong>${ev.en_curso} empleados</strong> con turno activo. No puedes cerrar hasta que terminen su jornada.</p>
                <div class="border rounded p-3 bg-light" style="max-height:200px; overflow-y:auto;"><ul>${list}</ul></div>
            `;
            btnNext.style.display = 'none';
        } else {
            content.innerHTML = `
                <div class="text-center py-5">
                    <i class="bi bi-check-circle-fill text-success" style="font-size: 4rem;"></i>
                    <h4 class="mt-3">Sin Turnos en Curso</h4>
                    <p class="text-muted">Todos los turnos del periodo han finalizado.</p>
                </div>
            `;
            btnNext.style.display = 'inline-block';
            btnNext.onclick = () => renderWizardStep(3);
        }
    } else if (step === 3) { // HE Pendientes
        if (ev.he_pendientes > 0) {
            const canApproveHE = typeof AuthService !== 'undefined' && AuthService.hasPermission("marcaciones.horas_extras");
            const list = ev.detalle_he.map(a => `
                <li class="d-flex justify-content-between align-items-center py-2 px-3 border-bottom hover-bg-light">
                    <div class="d-flex align-items-center">
                        <i class="bi bi-clock-fill text-primary me-2"></i>
                        <div>
                            <span class="fw-bold text-dark small">${a.fecha}</span>
                            <span class="mx-2 text-muted">|</span>
                            <span class="text-secondary small">${a.nombre_completo}</span>
                            <span class="badge bg-light text-primary border border-primary-subtle ms-2">${formatExactMinutesToTime(a.minutos_bruto)}</span>
                            ${cierreGetHEContextBadges(a)}
                        </div>
                    </div>
                    ${canApproveHE ? `
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-sm btn-outline-success fw-bold py-0 px-2" onclick="cierreResolverHE(${a.empleado_id}, '${a.fecha}', ${a.minutos_bruto}, 'APROBADO')" title="Aprobar esta Hora Extra">
                            <i class="bi bi-check-lg"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger fw-bold py-0 px-2" onclick="cierreResolverHE(${a.empleado_id}, '${a.fecha}', ${a.minutos_bruto}, 'RECHAZADO')" title="Rechazar esta Hora Extra">
                            <i class="bi bi-x-lg"></i>
                        </button>
                    </div>
                    ` : ''}
                </li>
            `).join('');

            content.innerHTML = `
                <h4 class="text-primary fw-bold mb-3"><i class="bi bi-exclamation-circle-fill"></i> HARD STOP: Horas Extras Pendientes</h4>
                <div class="d-flex justify-content-between align-items-center mb-3 p-3 bg-primary bg-opacity-10 border border-primary-subtle rounded-3">
                    <div class="small text-primary-emphasis fw-semibold">
                        <i class="bi bi-info-circle-fill me-1"></i> Existen <strong>${ev.he_pendientes} registros</strong> pendientes en el periodo seleccionado.
                    </div>
                    ${canApproveHE ? `
                    <button class="btn btn-sm btn-primary fw-bold px-3 shadow-sm" onclick="cierreResolverTodasHE()">
                        <i class="bi bi-check-all me-1"></i> Aprobar Todas
                    </button>
                    ` : ''}
                </div>
                <div class="border rounded-3 shadow-sm" style="max-height:230px; overflow-y:auto; background:#ffffff;">
                    <ul class="list-unstyled mb-0">${list}</ul>
                </div>
            `;
            btnNext.style.display = 'none';
        } else {
            content.innerHTML = `
                <div class="text-center py-5">
                    <i class="bi bi-check-circle-fill text-success" style="font-size: 4rem;"></i>
                    <h4 class="mt-3">Sin HE Pendientes</h4>
                    <p class="text-muted">Todas las Horas Extras han sido resueltas.</p>
                </div>
            `;
            btnNext.style.display = 'inline-block';
            btnNext.onclick = () => renderWizardStep(4);
        }
    } else if (step === 4) { // Inasistencias (Soft Stop)
        if (ev.inasistencias_injustificadas > 0) {
            const list = ev.detalle_ina.map(a => {
                const nameEscaped = (a.nombre_completo || '').replace(/'/g, "\\'");
                return `
                    <li class="d-flex justify-content-between align-items-center py-2 px-3 border-bottom hover-bg-light">
                        <div class="d-flex align-items-center">
                            <i class="bi bi-calendar-x text-info me-2"></i>
                            <div>
                                <span class="fw-bold text-dark small">${a.fecha}</span>
                                <span class="mx-2 text-muted">|</span>
                                <span class="text-secondary small">${a.nombre_completo}</span>
                            </div>
                        </div>
                        <button class="btn btn-sm btn-outline-info fw-bold py-1 px-3 shadow-sm" 
                                onclick="window.cierreGestionarInasistencia(${a.empleado_id}, '${a.fecha}', '${nameEscaped}')">
                            <i class="bi bi-gear-fill me-1"></i> Gestionar
                        </button>
                    </li>
                `;
            }).join('');
            content.innerHTML = `
                <h4 class="text-info fw-bold"><i class="bi bi-info-circle"></i> SOFT STOP: Inasistencias no justificadas</h4>
                <p>Hay <strong>${ev.inasistencias_injustificadas} inasistencias</strong>. Si cierra ahora, se consolidarán como inasistencias definitivas sin goce de sueldo, o puedes gestionarlas desde aquí.</p>
                <div class="border rounded-3 shadow-sm bg-white mb-3" style="max-height:180px; overflow-y:auto;">
                    <ul class="list-unstyled mb-0">${list}</ul>
                </div>
                <div class="form-check">
                    <input class="form-check-input" type="checkbox" id="chk-aceptar-inasistencias" onchange="window.cierreWizardState.aceptarInasistencias = this.checked; document.getElementById('btn-cierre-wizard-next').disabled = !this.checked;">
                    <label class="form-check-label fw-bold" for="chk-aceptar-inasistencias">
                        Acepto consolidar estas inasistencias.
                    </label>
                </div>
            `;
            btnNext.style.display = 'inline-block';
            btnNext.disabled = true;
            btnNext.onclick = () => renderWizardStep(5);
        } else {
            content.innerHTML = `
                <div class="text-center py-5">
                    <i class="bi bi-check-circle-fill text-success" style="font-size: 4rem;"></i>
                    <h4 class="mt-3">Sin Inasistencias Pendientes</h4>
                    <p class="text-muted">No hay inasistencias injustificadas en el periodo.</p>
                </div>
            `;
            window.cierreWizardState.aceptarInasistencias = true;
            btnNext.style.display = 'inline-block';
            btnNext.disabled = false;
            btnNext.onclick = () => renderWizardStep(5);
        }
    } else if (step === 5) { // Resumen antes de sellar (propuesta A, dueño 09-11-2026)
        // El balance de horas de cada tipo de horario parte de las horas totales y termina en lo que se carga; las
        // cifras son las mismas del informe PDF (GET /api/cierre/resumen).
        content.innerHTML = `
            <h4 class="fw-bold mb-1"><i class="bi bi-file-text"></i> Lo que se va a cargar en remuneraciones</h4>
            <p class="cz-r-sub">Una columna por tipo de horario: la cuenta parte de las horas totales y termina en lo que se descuenta y lo que se paga.</p>
            <div id="cz-resumen" class="cz-r-cols"><div class="text-center py-4 text-muted"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Calculando el resumen del área…</div></div>

            <div class="d-flex flex-wrap gap-2 my-3" id="cz-resumen-bts">
                <button class="btn btn-outline-success fw-bold px-3 py-2.5 flex-fill shadow-sm text-nowrap" onclick="window.cierreWizardDownloadExcel()">
                    <i class="bi bi-file-earmark-excel-fill me-2"></i> Descargar Excel (detalle día a día)
                </button>
            </div>

            <div class="alert alert-warning mt-3 border-warning">
                <i class="bi bi-exclamation-triangle-fill me-2"></i><strong>Al sellar</strong> el período queda cerrado para el área y el informe en PDF se envía a Recursos Humanos. Las marcas de estas fechas ya no se podrán cambiar.
            </div>
        `;
        window.cargarResumenCierre(Object.assign({ que: 'preinforme' }, window.cierreWizardState));
        btnNext.innerHTML = '<i class="bi bi-lock-fill"></i> Sellar Periodo Definitivamente';
        btnNext.className = 'btn btn-warning fw-bold px-4';
        btnNext.disabled = false;
        btnNext.style.display = 'inline-block';
        btnNext.onclick = confirmarCierreRRHH;
    }
}

window.cierreWizardDownloadExcel = function() {
    const s = window.cierreWizardState;
    if (!s || !s.fIni || !s.fFin) {
        showToast("Las fechas no sirven para exportar: revise desde y hasta.", "warning");
        return;
    }
    const token = typeof AuthService !== 'undefined' ? AuthService.getToken() : localStorage.getItem('access_token');
    const tokenParam = token ? `&token=${encodeURIComponent(token)}` : '';
    const url = `/api/reports/asistencia/excel/?fecha_inicio=${s.fIni}&fecha_fin=${s.fFin}&area=${encodeURIComponent(s.area)}${tokenParam}`;
    window.location.href = url;
};

function nextWizardStep() {
    const s = window.cierreWizardState.currentStep;
    if (s < 5) renderWizardStep(s + 1);
}

async function recargarPreEvaluacionCierre() {
    const s = window.cierreWizardState;
    const url = `/api/cierre/pre-evaluacion?fecha_inicio=${s.fIni}&fecha_fin=${s.fFin}&area=${encodeURIComponent(s.area)}`;
    try {
        const resp = await fetch(url, { headers: { 'Authorization': `Bearer ${AuthService.getToken()}` } });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || "Fallo en pre-evaluación");
        
        window.cierreWizardState.evaluacion = data;
        renderWizardStep(s.currentStep);
        
        if (typeof loadMarcacionesData === 'function') {
            loadMarcacionesData();
        }
    } catch (e) {
        showToast("No se pudo cambiar el estado. " + e.message, "error");
    }
}

window.cierreResolverHE = async function(empId, fecha, minutos, estado) {
    if (typeof showBatchLoadingOverlay === 'function') {
        showBatchLoadingOverlay(estado === 'APROBADO' ? 'Procesando aprobación de Hora Extra...' : 'Procesando rechazo de Hora Extra...');
    }
    try {
        const res = await fetch('/api/asistencia/aprobar-he-batch/', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${AuthService.getToken()}`
            },
            body: JSON.stringify([{
                empleado_id: empId,
                fecha: fecha,
                estado: estado,
                minutos_autorizados: estado === 'APROBADO' ? minutos : 0
            }])
        });
        const data = await res.json();
        if (data.success || res.ok) {
            showToast(estado === 'APROBADO' ? 'Listo. Hora extra aprobada.' : 'Listo. Hora extra rechazada.', 'success');
            await recargarPreEvaluacionCierre();
        } else {
            showToast(data.detail || 'No se pudo guardar la hora extra.', 'danger');
        }
    } catch (e) {
        Avisos.sinConexion();
    } finally {
        if (typeof hideBatchLoadingOverlay === 'function') {
            hideBatchLoadingOverlay();
        }
    }
};

window.cierreResolverTodasHE = async function() {
    const s = window.cierreWizardState;
    if (!s.evaluacion || !s.evaluacion.detalle_he || s.evaluacion.detalle_he.length === 0) return;
    
    if (!await uiConfirm(`¿Aprobar las ${s.evaluacion.detalle_he.length} horas extra pendientes de este período?`, { items: ['Quedan aprobadas todas juntas.', 'Cada una se puede revertir después desde su día.'], confirmText: 'Aprobar todas' })) {
        return;
    }

    if (typeof showBatchLoadingOverlay === 'function') {
        showBatchLoadingOverlay(`Aprobando todas las horas extras pendientes (${s.evaluacion.detalle_he.length})...`);
    }

    const items = s.evaluacion.detalle_he.map(a => ({
        empleado_id: a.empleado_id,
        fecha: a.fecha,
        estado: 'APROBADO',
        minutos_autorizados: a.minutos_bruto
    }));

    try {
        const res = await fetch('/api/asistencia/aprobar-he-batch/', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${AuthService.getToken()}`
            },
            body: JSON.stringify(items)
        });
        const data = await res.json();
        if (data.success || res.ok) {
            showToast(`Listo. Se aprobaron ${items.length === 1 ? '1 hora extra' : items.length + ' horas extra'}.`, 'success');
            await recargarPreEvaluacionCierre();
        } else {
            showToast(data.detail || 'No se pudieron aprobar las horas extra.', 'danger');
        }
    } catch (e) {
        Avisos.sinConexion();
    } finally {
        if (typeof hideBatchLoadingOverlay === 'function') {
            hideBatchLoadingOverlay();
        }
    }
};

window.cierreCorregirAnomalia = function(empId, fecha, nombreCompleto, horaEntrada, horaSalida) {
    if (typeof openManualEntryModal === 'function') {
        openManualEntryModal(
            empId,
            fecha,
            nombreCompleto,
            "Ingreso Manual (Corrección de Anomalía)",
            horaEntrada || null,
            horaSalida || null
        );
    } else {
        showToast("La ventana de ingreso manual no terminó de cargar. Recargue la página.", "danger");
    }
};

window.cierreGestionarInasistencia = function(empId, fecha, nombreCompleto) {
    if (typeof openAsistenciaActionModal === 'function') {
        openAsistenciaActionModal(
            empId,
            fecha,
            nombreCompleto
        );
    } else {
        showToast("Las acciones del día no terminaron de cargar. Recargue la página.", "danger");
    }
};

async function confirmarCierreRRHH() {
    const s = window.cierreWizardState;
    const btn = document.getElementById('btn-cierre-wizard-next');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Sellando...';

    try {
        const resp = await fetch('/api/cierre/ejecutar', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${AuthService.getToken()}`
            },
            body: JSON.stringify({
                fecha_inicio: s.fIni,
                fecha_fin: s.fFin,
                area: s.area,
                aceptar_inasistencias: s.aceptarInasistencias
            })
        });

        const res = await resp.json();
        if (resp.ok) {
            const m = bootstrap.Modal.getInstance(document.getElementById('modal-cierre-wizard'));
            if (m) m.hide();
            loadMarcacionesData();
            cargarPeriodosEnToolbar();
            // Sello del cierre (diseño HD): los cinco pasos se completan uno a uno, el candado se cierra y el texto dice
            // qué mes y qué área quedaron cerrados
            const e = window.escHtml || (x => String(x == null ? '' : x));
            const per = (s.periodos || []).find(p => p.fecha_inicio === s.fIni && p.fecha_fin === s.fFin);
            const queMes = per && per.mes_cierre ? per.mes_cierre : 'Tramo ' + window.formatFechaDDMMYYYY(s.fIni) + ' al ' + window.formatFechaDDMMYYYY(s.fFin);
            const pasos = ['Anomalías', 'En curso', 'Horas extra', 'Inasistencias', 'Resumen antes de sellar'];
            Swal.fire({
                title: 'Período cerrado',
                html: '<div class="cz-sello"><div class="cz-pasos" role="list" aria-label="Pasos del cierre">'
                    + pasos.map(p => '<i role="listitem" title="' + p + '" aria-label="' + p + ': listo"></i>').join('')
                    + '</div><b class="cz-que">' + e(queMes) + ' cerrado · ' + e(s.area) + '</b></div>'
                    + '<p class="cz-tx">El informe de cierre, un PDF por tipo de horario, se envió a Recursos Humanos. También queda en Configuración → Tramos de cierre.</p>',
                icon: 'success',
                iconHtml: '<svg class="cz-candado" viewBox="0 0 40 48" aria-hidden="true"><path class="cz-arco" d="M11 22 V14 a9 9 0 0 1 18 0 V22" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><rect x="5" y="21" width="30" height="24" rx="6" fill="currentColor"/></svg>',
                customClass: { popup: 'cz-cerrado' },
                showCancelButton: true,
                confirmButtonText: 'Descargar informe (PDF)',
                cancelButtonText: 'Cerrar'
            }).then(r2 => { if (r2.isConfirmed) window.descargarInformeCierre(s.fIni, s.fFin, s.area); });
        } else {
            showToast(res.detail || "No se pudo cerrar el período.", "error");
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-lock-fill"></i> Sellar Periodo Definitivamente';
        }
    } catch (e) {
        console.error(e);
        Avisos.sinConexion();
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-lock-fill"></i> Sellar Periodo Definitivamente';
    }
}

// Botón «Preinforme» de la barra de la grilla (al lado del Excel): el informe del período y el área elegidos, tal
// como está hoy, sin pasar por los pasos del cierre; sirve para ver si falta corregir algo (dueño, 09-11-2026).
window.descargarPreinformeGrilla = function (btn) {
    const uiArea = document.getElementById('marcacion-area');
    const area = uiArea ? uiArea.value : '';
    if (!area || area === 'Todas') {
        Avisos.falta('Elija un área: el preinforme es por área (un PDF por tipo de horario).');
        return;
    }
    const st = typeof stateMarcacionesApp !== 'undefined' ? stateMarcacionesApp : {};
    if (!st.fechaInicioRRHH || !st.fechaFinRRHH) {
        Avisos.falta('Elija un período de cierre para sacar el preinforme.');
        return;
    }
    return window.descargarInformeCierre(st.fechaInicioRRHH, st.fechaFinRRHH, area, btn);
};

// ── RESUMEN ANTES DE SELLAR (paso 5 del cierre) ─────────────────────────────
// Propuesta A elegida por el dueño (09-11-2026): una columna por tipo de horario con el balance de horas (las horas
// totales son el punto de partida), lo que se carga con su porcentaje, de dónde sale y las jornadas.
window.cargarResumenCierre = async function (st, idCaja) {
    const caja = document.getElementById(idCaja || 'cz-resumen');
    if (!caja || !st) return;
    const e = window.escHtml || (x => String(x == null ? '' : x).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));
    try {
        const resp = await fetch('/api/cierre/resumen?fecha_inicio=' + st.fIni + '&fecha_fin=' + st.fFin + '&area=' + encodeURIComponent(st.area), {
            headers: { 'Authorization': 'Bearer ' + AuthService.getToken() }
        });
        const d = await resp.json();
        if (!resp.ok) throw new Error(d.detail || 'No se pudo preparar el resumen del cierre.');
        const tipos = d.tipos || [];
        if (!tipos.length) {
            caja.innerHTML = '<p class="text-muted py-3">El área no tiene personas en este tramo.</p>';
            return;
        }
        const filas = (rows) => rows.map(r => '<li class="' + e(r.c || '') + '"><span>' + e(r.t) + '</span><i class="cz-r-pc">' + e(r.q || '') + '</i><b>' + e(r.v) + '</b></li>').join('');
        caja.innerHTML = tipos.map(t => {
            const cargar = (t.cargar || []).map(c => '<div class="cz-r-g ' + e(c.c) + '"><span>' + e(c.t) + '</span><b>' + e(c.v) + '</b><small>' + e(c.n) + (c.q ? ' · ' + e(c.q) : '') + '</small></div>').join('');
            const dd = (t.de_donde || []).map(g => '<div><p>' + e(g.t) + '</p>' + g.filas.map(r => '<span class="cz-r-ln">' + e(r.t) + '<i class="cz-r-pc">' + e(r.q || '') + '</i><b>' + e(r.v) + '</b></span>').join('') + '</div>').join('');
            return '<section class="cz-r-col"><header><h5>' + e(t.titulo) + '</h5><span>' + t.personas + ' personas</span></header>'
                + '<h6>Balance de horas</h6><ul class="cz-r-bal">' + filas(t.balance || []) + '</ul>'
                + '<h6>Lo que se carga</h6><div class="cz-r-gg">' + cargar + '</div>'
                + (dd ? '<div class="cz-r-dd">' + dd + '</div>' : '')
                + '<h6>Jornadas</h6><ul class="cz-r-bal cz-r-jor">' + filas(t.jornadas || []) + '</ul></section>';
        }).join('');
        // Un botón de descarga por tipo de horario, al lado del Excel (dueño, 09-11-2026): cada PDF por separado
        const bts = document.getElementById((idCaja || 'cz-resumen') + '-bts');
        if (bts) {
            bts.querySelectorAll('.cz-r-pdf').forEach(b => b.remove());
            const que = st.que || 'informe';
            tipos.forEach(t => {
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'btn btn-outline-primary fw-bold px-3 py-2.5 flex-fill shadow-sm text-nowrap cz-r-pdf';
                b.innerHTML = '<i class="bi bi-file-earmark-pdf-fill me-2" aria-hidden="true"></i> Descargar ' + e(que) + ' ' + e(t.titulo) + ' (PDF)';
                b.addEventListener('click', () => window.descargarInformeTipo(st.fIni, st.fFin, st.area, t.tipo, t.titulo, que));
                bts.appendChild(b);
            });
        }
    } catch (err) {
        console.error(err);
        caja.innerHTML = '<div class="alert alert-danger">' + e(err.message || 'No se pudo preparar el resumen del cierre.') + '</div>';
    }
};

// Ventana «Resumen» de un área ya cerrada (botón de Configuración → Tramos de cierre, dueño 09-11-2026): la misma
// vista del paso 5. Un período cerrado ya no se recalcula, así que muestra las cifras del cierre.
window.verResumenCierre = function (fIni, fFin, area, cerro) {
    const e = window.escHtml || (x => String(x == null ? '' : x));
    const f = window.formatFechaDDMMYYYY || (x => x);
    const viejo = document.getElementById('modal-resumen-cierre');
    if (viejo) viejo.remove();
    const st = { fIni: fIni, fFin: fFin, area: area };
    window._resumenCierreVista = st;
    document.body.insertAdjacentHTML('beforeend', `
        <div class="modal fade" id="modal-resumen-cierre" tabindex="-1" aria-labelledby="modal-resumen-cierre-t" aria-hidden="true">
          <div class="modal-dialog modal-xl modal-dialog-scrollable">
            <div class="modal-content">
              <div class="modal-header">
                <h5 class="modal-title" id="modal-resumen-cierre-t"><i class="bi bi-shield-lock-fill"></i> Resumen del cierre</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button>
              </div>
              <div class="modal-body">
                <div class="cz-r-per"><span class="chip-cerrada"><i class="bi bi-lock-fill"></i> Cerrada</span>
                  <span>Área <b>${e(area)}</b></span><span>Tramo <b>${e(f(fIni))} al ${e(f(fFin))}</b></span>${cerro ? `<span>Cerró <b>${e(cerro)}</b></span>` : ''}</div>
                <h4 class="fw-bold mb-1 mt-3"><i class="bi bi-file-text"></i> Lo que se cargó en remuneraciones</h4>
                <p class="cz-r-sub">Una columna por tipo de horario: la cuenta parte de las horas totales y termina en lo que se descuenta y lo que se paga.</p>
                <div id="cz-resumen-vista" class="cz-r-cols"><div class="text-center py-4 text-muted"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Preparando el resumen del área…</div></div>
                <div class="d-flex flex-wrap gap-2 mt-3" id="cz-resumen-vista-bts">
                  <button class="btn btn-outline-success fw-bold px-3 py-2.5 flex-fill shadow-sm text-nowrap" onclick="window.descargarExcelCierre(window._resumenCierreVista)">
                    <i class="bi bi-file-earmark-excel-fill me-2"></i> Descargar Excel (detalle día a día)
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>`);
    const el = document.getElementById('modal-resumen-cierre');
    el.addEventListener('hidden.bs.modal', () => el.remove());
    new bootstrap.Modal(el).show();
    window.cargarResumenCierre(st, 'cz-resumen-vista');
};

window.descargarExcelCierre = function (st) {
    if (!st || !st.fIni || !st.fFin) return;
    const token = typeof AuthService !== 'undefined' ? AuthService.getToken() : localStorage.getItem('access_token');
    window.location.href = '/api/reports/asistencia/excel/?fecha_inicio=' + st.fIni + '&fecha_fin=' + st.fFin + '&area=' + encodeURIComponent(st.area)
        + (token ? '&token=' + encodeURIComponent(token) : '');
};

// Un informe de cierre (un tipo de horario) descargado directo del servidor, igual que el Excel: los botones «42 horas»,
// «180 horas»… de Tramos de cierre (dueño, 09-11-2026).
window.descargarInformeTipo = function (fIni, fFin, area, tipo, titulo, que) {
    const token = AuthService.getToken();
    const fr = document.createElement('iframe');
    fr.style.display = 'none';
    fr.title = 'Descarga del informe ' + titulo;
    fr.src = '/api/cierre/informe-pdf/archivo?fecha_inicio=' + fIni + '&fecha_fin=' + fFin + '&area=' + encodeURIComponent(area)
        + '&tipo=' + encodeURIComponent(tipo) + (token ? '&token=' + encodeURIComponent(token) : '');
    document.body.appendChild(fr);
    setTimeout(function () { fr.remove(); }, 120000);
    const q = que || 'informe';
    showToast(q.charAt(0).toUpperCase() + q.slice(1) + ' de cierre de ' + area + ' · ' + titulo + ': revise sus descargas en unos segundos.', 'success');
};

// ── INFORME DE CIERRE (PDF) ──────────────────────────────────────────────────
// El informe para RR.HH. (el mismo del correo de cierre), un PDF por tipo de horario del área. Con el área sin cerrar
// es el preinforme. Se descarga desde Tramos de cierre, al sellar y en la previsualización del cierre (09-11-2026).
window.descargarInformeCierre = async function (fIni, fFin, area, btn) {
    if (btn) {
        if (btn.disabled) return;
        btn.disabled = true;
    }
    try {
        showToast('Preparando el informe de cierre de ' + area + '…', 'info');
        const resp = await fetch('/api/cierre/informe-pdf?fecha_inicio=' + fIni + '&fecha_fin=' + fFin + '&area=' + encodeURIComponent(area), {
            headers: { 'Authorization': 'Bearer ' + AuthService.getToken() }
        });
        const d = await resp.json();
        if (!resp.ok) throw new Error(d.detail || 'No se pudo generar el informe de cierre.');
        const archivos = d.archivos || [];
        if (!archivos.length) {
            showToast('El área no tiene personas en ese tramo: no hay informe que descargar.', 'warning');
            return;
        }
        // Cada PDF lo entrega el servidor como archivo adjunto (igual que el Excel), en un marco oculto: así el
        // navegador lo descarga directo, sin armar archivos en memoria (algunos navegadores los bloquean sin avisar).
        const token = AuthService.getToken();
        archivos.forEach(function (a, i) {
            setTimeout(function () {
                const fr = document.createElement('iframe');
                fr.style.display = 'none';
                fr.title = 'Descarga ' + a.filename;
                fr.src = '/api/cierre/informe-pdf/archivo?fecha_inicio=' + fIni + '&fecha_fin=' + fFin + '&area=' + encodeURIComponent(area)
                    + '&tipo=' + encodeURIComponent(a.tipo) + (token ? '&token=' + encodeURIComponent(token) : '');
                document.body.appendChild(fr);
                setTimeout(function () { fr.remove(); }, 120000);
            }, i * 1500);
        });
        const que = d.preinforme ? 'Preinforme' : 'Informe';
        showToast(que + ' de cierre de ' + area + ': se descarga' + (archivos.length === 1 ? ' 1 PDF' : 'n ' + archivos.length + ' PDF, uno por tipo de horario')
            + ' (' + archivos.map(function (a) { return a.titulo; }).join(' y ') + '). Revise sus descargas en unos segundos.', 'success');
    } catch (e) {
        console.error(e);
        showToast(e.message || 'No se pudo generar el informe de cierre.', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
};

async function openHistorialCierresModal() {
    try {
        const resp = await fetch('/api/asistencia/periodo-rrhh/historial/');
        const historial = await resp.json();

        const user = AuthService.getUser();
        const isSuperAdmin = user && (user.alcance_global === true || user.alcance_global === 1);
        const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
        const p2 = (n) => String(n).padStart(2, '0');
        const anioHoy = new Date().getFullYear();
        // «26-09 al 25-10», con el año solo si no es el de hoy
        const tramoTxt = (c) => {
            const a = String(c.fecha_inicio || '').slice(0, 10).split('-'), b = String(c.fecha_fin || '').slice(0, 10).split('-');
            if (a.length < 3 || b.length < 3) return esc((c.fecha_inicio || '') + ' al ' + (c.fecha_fin || ''));
            return a[2] + '-' + a[1] + ' al ' + b[2] + '-' + b[1] + (Number(b[0]) !== anioHoy ? '-' + b[0] : '');
        };
        const cerradoTxt = (c) => {
            const d = new Date(c.created_at || c.fecha_cierre);
            return isNaN(d.getTime()) ? '—' : p2(d.getDate()) + '-' + p2(d.getMonth() + 1) + '-' + d.getFullYear() + ' ' + p2(d.getHours()) + ':' + p2(d.getMinutes());
        };
        // El comentario del cierre en palabras: con qué rol se cerró y si se aceptaron las inasistencias
        const ROLES = { JEFE_AREA: 'Jefe de área', SUPER_ADMIN: 'Administrador', ADMIN: 'Administrador' };
        const notaTxt = (c) => {
            const txt = String(c.comentarios || c.comentario || '').trim();
            if (!txt) return '';
            const rol = txt.match(/\[([A-Z_]+)\]/);
            const ina = txt.match(/inasistencias aceptadas:\s*(si|sí|no)/i);
            if (!rol && !ina) return txt;
            const partes = [];
            if (rol) { const r = ROLES[rol[1]] || rol[1].replace(/_/g, ' ').toLowerCase(); partes.push(r.charAt(0).toUpperCase() + r.slice(1)); }
            if (ina) partes.push('inasistencias aceptadas: ' + (/^n/i.test(ina[1]) ? 'no' : 'sí'));
            return partes.join(' · ');
        };
        const cols = isSuperAdmin ? 5 : 4;
        const filas = historial.length === 0
            ? '<tr><td colspan="' + cols + '" class="vn-vacio">Todavía no hay cierres.</td></tr>'
            : historial.map((c) => {
                const nota = notaTxt(c);
                return '<tr><td class="vn-nw">' + tramoTxt(c) + '</td><td>' + esc(c.area || 'Todas') + '</td><td class="vn-nw">' + cerradoTxt(c) + '</td><td>' + esc(c.username || c.usuario_cierre || '—') + '</td>'
                    + (isSuperAdmin ? '<td class="vn-acc"><button type="button" class="btn btn-light btn-sm" onclick="reabrirPeriodo(' + Number(c.id) + ', \'' + esc(c.fecha_inicio) + '\', \'' + esc(c.fecha_fin) + '\', \'' + esc(c.area) + '\')">Reabrir</button></td>' : '')
                    + '</tr>' + (nota ? '<tr class="vn-gp"><td colspan="' + cols + '">' + esc(nota) + '</td></tr>' : '');
            }).join('');

        const html = '<div class="modal fade" id="modal-historial-cierres" tabindex="-1" aria-labelledby="hc-titulo">'
            + '<div class="modal-dialog modal-dialog-centered modal-lg"><div class="modal-content">'
            + '<div class="modal-header"><span class="vn-ico" aria-hidden="true"><i class="bi bi-clock-history"></i></span>'
            + '<div class="vn-tit"><h5 class="modal-title" id="hc-titulo">Historial de cierres</h5><div class="vn-sub">Cada cierre con su área, fecha y usuario</div></div>'
            + '<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button></div>'
            + '<div class="modal-body"><div class="vn-tbl-caja"><table class="vn-tbl"><thead><tr><th>Tramo</th><th>Área</th><th>Cerrado</th><th>Por</th>'
            + (isSuperAdmin ? '<th><span class="visually-hidden">Reabrir</span></th>' : '') + '</tr></thead><tbody>' + filas + '</tbody></table></div></div>'
            + '<div class="modal-footer"><button type="button" class="btn btn-light" data-bs-dismiss="modal">Cerrar</button></div>'
            + '</div></div></div>';

        const old = document.getElementById('modal-historial-cierres');
        if (old) old.remove();

        document.body.insertAdjacentHTML('beforeend', html);
        const modal = new bootstrap.Modal(document.getElementById('modal-historial-cierres'));
        modal.show();

    } catch (e) {
        console.error(e);
        showToast("No se pudo cargar el historial de cierres.", "error");
    }
}

window.reabrirPeriodo = async function(id, fechaInicio, fechaFin, area) {
    if (!await uiConfirm(`¿Reabrir el período del ${(window.formatFechaDDMMYYYY ? window.formatFechaDDMMYYYY(fechaInicio) : fechaInicio)} al ${(window.formatFechaDDMMYYYY ? window.formatFechaDDMMYYYY(fechaFin) : fechaFin)}?`, { quien: area, items: ['Se quita el cierre: los días se pueden cambiar y recalcular.', 'Queda registrado quién lo reabrió.'], confirmText: 'Reabrir período', danger: true })) {
        return;
    }
    
    try {
        const resp = await fetch(`/api/cierre/${id}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${AuthService.getToken()}`
            }
        });
        
        const res = await resp.json();
        if (resp.ok) {
            showToast("Listo. Período reabierto.", "success");
            const m = bootstrap.Modal.getInstance(document.getElementById('modal-historial-cierres'));
            if (m) m.hide();
            loadMarcacionesData();
        } else {
            showToast(res.detail || "No se pudo reabrir el período.", "error");
        }
    } catch (e) {
        console.error(e);
        Avisos.sinConexion();
    }
};


/* ==========================================
   MERGED FROM vista_analitica.js
   ========================================== */
/**
 * vista_analitica.js
 * Vista Analítica de Marcaciones — Balance de Masas HH/Deudas
 * ISOLADO: No toca ni modifica ninguna lógica existente.
 */

window.vistaAnaliticaState = window.vistaAnaliticaState || {
    soloNegativo: false,
    soloConHE: false,
    showBonos: false,
    showHE: null,         // null = según tipo: ciclo contraído, bolsa abierto (solo tiene la columna Aprobadas)
    showDeudas: false,
    showIncidencias: false,
    showSaldoMeta: null,  // null = según tipo: Bolsa/Espera abiertos en bolsa flexible
    tabTipo: null         // Pestaña activa en áreas con ambos tipos: 'ciclo' | 'bolsa'
};

// ── PLAN DE COLUMNAS POR TIPO DE HORARIO ─────────────────────────────────────
// La grilla muestra UN solo tipo a la vez (si el área tiene ambos, hay pestañas):
//  · Ciclo inteligente: Bonos · Incidencias · Horas extra (4) · Tiempo no trabajado (5) · Saldo neto
//  · Bolsa flexible:    Bonos · Incidencias (sin ATR/S.ADL) · Horas extra (solo aprobadas) · Bolsa 180h · Espera 88h
// Todos los grupos arrancan contraídos; cada uno conserva su botón de expandir/contraer.
window.GRID_COLLAPSED_W = 76;

// ── Corte reloj → libreta (Bolsa flexible) ─────────────────────────────────────
// Antes de la fecha «Sin reloj a partir de» de su horario la persona se controlaba con el reloj biométrico; desde ella,
// con la libreta ingresada a mano. Cada horario tiene su fecha y la entrega el servidor; aquí no se escribe ninguna fecha.
window.getCorteLibreta = function(empInfo) {
    return (empInfo && (empInfo.libreta_desde || (empInfo.info && empInfo.info.libreta_desde))) || null;
};
// Fechas de libreta distintas entre las filas visibles (de menor a mayor)
window.getCortesLibreta = function(rows) {
    return [...new Set((rows || []).map(r => window.getCorteLibreta(r && r.emp)).filter(Boolean))].sort();
};
window._empEsHorarioLibreta = function(empInfo) {
    // Igual que el cálculo (libreta_corte.es_horario_libreta): solo la modalidad «Libreta» decide, no el tipo de horario
    return !!(empInfo && String(empInfo.modalidad_control || '').toUpperCase() === 'LIBRETA_180H');
};
// true si ese día se controló por reloj (horario de libreta, pero anterior al corte y sin libreta cargada)
window.esDiaControlPorReloj = function(di, dateStr, empInfo) {
    if (!window._empEsHorarioLibreta(empInfo)) return false;
    if (di && (di.slots_96 || di.origen === 'LIBRETA_180H')) return false;       // hay libreta real: es libreta
    if (di && di.modalidad_dia) return di.modalidad_dia === 'RELOJ';
    const corte = window.getCorteLibreta(empInfo);
    return !!corte && String(dateStr) < corte;
};
window.getGridFlags = function(allRows) {
    const st = window.vistaAnaliticaState;
    const nB = allRows.filter(r => r.esBolsa).length;
    const nC = allRows.length - nB;
    // Las pestañas "Ciclo inteligente" y "Bolsa flexible" se muestran siempre, aunque una no tenga empleados.
    const tabs = true;
    // Si el usuario no eligió pestaña, abre la que tenga empleados (Ciclo si ambas).
    let tipo = (nC === 0 && nB > 0) ? 'bolsa' : 'ciclo';
    if (st.tabTipo === 'bolsa' || st.tabTipo === 'ciclo') tipo = st.tabTipo;
    const f = { tipo, tabs, nB, nC, total: allRows.length, esBolsa: tipo === 'bolsa' };
    window._gridFlags = f;
    return f;
};
window.getGridShow = function(f, hasBonos) {
    const s = window.vistaAnaliticaState;
    const esBolsa = f.esBolsa;
    return {
        hasBonos,
        showBonos: s.showBonos === true,
        showIncidencias: s.showIncidencias === true,
        showHE: (s.showHE ?? esBolsa) === true,
        showDeudas: !esBolsa && s.showDeudas === true,
        hasInc: !esBolsa,         // "Incidencias": no aplica a bolsa
        hasDeudas: !esBolsa,      // "Tiempo no trabajado": no aplica a bolsa
        hasSaldo: !esBolsa,       // "Saldo neto": no aplica a bolsa (su balance está en 180h / 88h)
        hayBolsa: esBolsa,        // grupos Bolsa (180h) y Espera (88h)
        showSaldoMeta: esBolsa && (s.showSaldoMeta ?? true) === true,
        heFull: !esBolsa,         // HE: ciclo = Pend/Apr/Rech/Tot; bolsa = solo aprobadas (exceso sobre la meta)
        nInc: esBolsa ? 4 : 6     // bolsa: sin ATR ni S.ADL
    };
};
// ── Avance de la bolsa y uso de la espera (diseño C elegido por el dueño, 03-11-2026) ─────────────────────────────
// Bolsa: «64:00 de 180:00 · 36 %», barra con la raya de lo esperado a hoy y una frase en horas. Lo esperado es la parte de
// la meta que corresponde a los días ya transcurridos de su vigencia en el tramo (si entra o sale a mitad del tramo, su
// ventana). Espera: «2:15 de 88:00 · 3 %» y cuánto le queda antes del tope (el tope no es una meta: sin raya). Morado o
// gris = al día; naranjo = atrasado o cerca del tope; rojo = superó el tope. Textos con comillas y concatenación.
window.mxHm = function (min) {
    const m = Math.round(Math.abs(Number(min) || 0));
    return Math.floor(m / 60) + ':' + String(m % 60).padStart(2, '0');
};
window.mxAvanceBolsa = function (r, fIni, fFin, hoyIso) {
    const meta = Number(r.metaMin) || 0, acum = Number(r.acumBolsa) || 0;
    const prb = r.emp && r.emp._prorrateoBolsa;
    const desde = (prb && prb.desde) || fIni, hasta = (prb && prb.hasta) || fFin;
    const dia = (iso) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / 86400000;
    let frac = 1;
    if (desde && hasta && hoyIso) {
        const total = dia(hasta) - dia(desde) + 1;
        frac = total > 0 ? Math.min(total, Math.max(0, dia(hoyIso) - dia(desde) + 1)) / total : 1;
    }
    const dif = acum - meta * frac;
    return { meta: meta, acum: acum, pct: meta > 0 ? Math.round(acum / meta * 100) : null, frac: frac, terminado: frac >= 1, dif: dif, atrasado: dif < 0 };
};
window.mxCeldaAvanceBolsa = function (a, avisoLey) {
    const col = a.atrasado ? '#b45309' : '#5b21b6', fill = a.atrasado ? '#d97706' : '#7c3aed', h = window.mxHm;
    let frase;
    if (!a.terminado) frase = a.dif >= 0 ? 'va +' + h(a.dif) + ' sobre lo esperado' : 'le faltan ' + h(a.dif) + ' para ir al día';
    else frase = a.dif > 0 ? 'superó la meta por ' + h(a.dif) : (a.dif < 0 ? 'faltaron ' + h(a.dif) + ' para la meta' : 'cumplió la meta');
    const marca = a.terminado ? '' : '<span class="mx-av-marca" style="left:calc(' + (a.frac * 100).toFixed(2) + '% - 1px)" title="Esperado a hoy"></span>';
    return '<div class="mx-av"><div class="mx-av-l1"><span>' + (avisoLey || '') + '<b>' + h(a.acum) + '</b> de ' + h(a.meta) + '</span>'
        + '<b style="color:' + col + '">' + (a.pct === null ? '—' : a.pct + ' %') + '</b></div>'
        + '<div class="mx-av-bar"><span class="mx-av-fill" style="width:' + Math.min(100, a.pct || 0) + '%;background:' + fill + '"></span>' + marca + '</div>'
        + '<div class="mx-av-tx" style="color:' + col + '">' + frase + '</div></div>';
};
window.mxCeldaEspera = function (r) {
    const tope = Number(r.metaEsperaMin) || 0, usadas = Number(r.acumEspera) || 0, h = window.mxHm;
    if (!tope) return '<div class="mx-av mx-av-esp"><div class="mx-av-tx">Sin tope definido</div></div>';
    const pct = Math.round(usadas / tope * 100), exceso = usadas - tope;
    const col = pct >= 100 ? '#b91c1c' : (pct >= 75 ? '#b45309' : '#57534e');
    const fill = pct >= 100 ? '#dc2626' : (pct >= 75 ? '#d97706' : '#b45309');
    const frase = exceso > 0 ? 'superó el tope: ' + h(exceso) + ' se pagan como horas extra' : 'le quedan ' + h(tope - usadas) + ' antes del tope';
    return '<div class="mx-av mx-av-esp"><div class="mx-av-l1"><span><b>' + h(usadas) + '</b> de ' + h(tope) + '</span><b style="color:' + col + '">' + pct + ' %</b></div>'
        + '<div class="mx-av-bar"><span class="mx-av-fill" style="width:' + Math.min(100, pct) + '%;background:' + fill + '"></span></div>'
        + '<div class="mx-av-tx" style="color:' + col + '">' + frase + '</div></div>';
};

// ── Grilla por horario (diseño B elegido por el dueño, 03-11-2026) ─────────────────────────────────────────────────
// Con «Todos los horarios» la tabla se arma en bloques, aunque haya un solo horario: uno por horario (orden alfabético),
// con su título plegable, la cantidad de personas y, desde el segundo, su propio encabezado; las personas siguen en
// orden alfabético dentro de su bloque. Con un horario o una persona elegidos en los filtros la grilla queda sin bloques.
window.mxGruposPorHorario = function (rows) {
    if (stateMarcacionesApp.turnoId || stateMarcacionesApp.empleadoId) return null;
    // Bolsa flexible: en vez de un bloque por horario, uno por cargo — Choferes (siempre abierto) y Peonetas (plegado hasta que se abra).
    // Quien tenga otro cargo va en «Otros cargos», también abierto, para que nadie quede escondido tras un bloque plegado.
    if (window._gridFlags && window._gridFlags.esBolsa) {
        const por = { chofer: [], peoneta: [], otros: [] };
        rows.forEach(r => { const c = window.categoriaCargo((r.emp && r.emp.cargo) || ''); (por[c] || por.otros).push(r); });
        return [
            { nombre: 'Choferes', filas: por.chofer, fijo: true },
            { nombre: 'Peonetas', filas: por.peoneta, fijo: false },
            { nombre: 'Otros cargos', filas: por.otros, fijo: true }
        ].filter(g => g.filas.length);
    }
    const mapa = new Map();
    rows.forEach(r => {
        const k = String((r.emp && r.emp.turno) || '').trim() || 'Sin horario';
        if (!mapa.has(k)) mapa.set(k, []);
        mapa.get(k).push(r);
    });
    if (!mapa.size) return null;
    // Dentro de cada bloque, el orden de siempre (el servidor las entrega por apellido paterno, materno y nombre)
    return [...mapa.keys()].sort((a, b) => a.localeCompare(b, 'es')).map(k => ({ nombre: k, filas: mapa.get(k) }));
};
// Los horarios parten plegados cada vez que se entra a Asistencia (initMarcacionesUI vacía la lista); los que la persona
// abre siguen abiertos mientras trabaja, aunque la grilla se vuelva a dibujar
window.mxHorariosDesplegados = function () {
    if (!window._mxDesplegados) window._mxDesplegados = new Set();
    return window._mxDesplegados;
};
window.mxPlegarHorario = function (btn) {
    const tb = btn && btn.closest('tbody.gh-grupo');
    if (!tb) return;
    const plegar = !tb.classList.contains('gh-plegado');
    const set = window.mxHorariosDesplegados();
    const reducir = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const filas = Array.from(tb.querySelectorAll(':scope > tr:not(.gh-titulo):not(.gh-cab)'));
    // Solo se mueven las primeras filas (las que se ven); el resto entra y sale con ellas
    const mover = (desde, hasta, ms, paso) => filas.slice(0, 14).map((tr, i) => tr.animate(
        [{ opacity: desde, transform: desde ? 'none' : 'translateY(-8px)' }, { opacity: hasta, transform: hasta ? 'none' : 'translateY(-6px)' }],
        { duration: ms, delay: i * paso, easing: 'cubic-bezier(.23, 1, .32, 1)', fill: 'both' }));
    const aplicar = () => {
        tb.classList.toggle('gh-plegado', plegar);
        btn.setAttribute('aria-expanded', String(!plegar));
        if (plegar) set.delete(tb.dataset.horario); else set.add(tb.dataset.horario);
        // Las listas de días por revisar se ubican al quedar a la vista (plegadas no tienen medidas)
        if (!plegar && window.mxBandasAjustar) window.mxBandasAjustar(tb);
    };
    (tb._ghAnim || []).forEach(a => a.cancel());
    if (reducir || !filas.length) { aplicar(); return; }
    if (plegar) {
        // sale rápido (el sistema responde); al terminar se ocultan de verdad
        btn.setAttribute('aria-expanded', 'false');
        tb._ghAnim = mover(1, 0, 130, 8);
        Promise.all(tb._ghAnim.map(a => a.finished.catch(() => null))).then(() => {
            if (tb._ghAnim) tb._ghAnim.forEach(a => a.cancel());
            aplicar();
        });
    } else {
        aplicar();
        tb._ghAnim = mover(0, 1, 260, 18);
        tb._ghAnim.forEach(a => { a.onfinish = () => a.cancel(); });
    }
};
window.mxBloqueHorario = function (g, i, htmlDe, cabecera) {
    const e = window.escHtml || (x => String(x));
    // Bloque fijo (siempre abierto y sin botón de plegar): los Choferes y «Otros cargos» de la Bolsa flexible
    const fijo = !!g.fijo;
    const n = g.filas.length, plegado = !fijo && !window.mxHorariosDesplegados().has(g.nombre);
    // Los bloques parten plegados: su título avisa cuántos días por revisar hay dentro y lleva a ellos
    const nRev = g.filas.reduce((a, r) => a + window.mxDiasEnRevision(r.emp, null).length, 0);
    const nVal = window.mxPorValidarBloque(g.filas);
    return '<tbody class="gh-grupo' + (plegado ? ' gh-plegado' : '') + (fijo ? ' gh-fijo' : '') + '"' + (i === 0 ? ' id="matrix-tbody"' : '') + ' data-horario="' + e(g.nombre) + '">'
        // Lo pendiente asoma por arriba del título como hojas de un archivador (propuesta A, dueño 10-11-2026); cada hoja lleva a su día
        + '<tr class="gh-titulo"><td colspan="1"><div class="gh-tit"><div class="gh-hojas">'
        + (nRev ? window.mxAvisoBloqueHtml(nRev) : '') + window.mxAvisoValidarHtml(nVal) + '</div><div class="gh-linea">'
        + (fijo ? '' : '<button type="button" class="gh-plegar" aria-expanded="' + !plegado + '" aria-label="' + e('Plegar o desplegar ' + g.nombre) + '" onclick="window.mxPlegarHorario(this)"><i class="bi bi-chevron-down" aria-hidden="true"></i></button>')
        + '<b>' + e(g.nombre) + '</b><span>' + n + (n === 1 ? ' persona' : ' personas') + '</span></div></div></td></tr>'
        // El encabezado repetido va bajo el encabezado fijo de arriba (capa 55 < 90) y con su mismo aspecto (clase gh-cab)
        + (i > 0 ? cabecera.split('<tr class="').join('<tr class="gh-cab ').replace(/z-index:\s*1\d\d/g, 'z-index:55') : '')
        + g.filas.map(htmlDe).join('') + '</tbody>';
};

// ── Por validar en el título del bloque (dueño, 10-11-2026): cuántos +2, jornadas especiales y llamados de emergencia del bloque
// esperan una decisión. Mismo criterio que la celda de la grilla: una jornada en un día no laborable es ESP; en un día hábil, +2;
// la segunda jornada de un día no laborable es +2 y un llamado es EME. Siglas e íconos de Configuración → Estados.
// Desde el 10-11-2026 el +2 y el llamado de emergencia van directo a horas extra por aprobar y una jornada especial no se
// rechaza: lo único que espera validación es la jornada especial (jornada extra u horas extra).
const MX_DECIDIDO = new Set(['EXTRA', 'HORAS_EXTRAS', 'COMPENSATORIA']);
window.mxPorValidarDia = function (di) {
    const out = [];
    if (!di || typeof di !== 'object') return out;
    const ja = di.jornada_adicional;
    if (ja && ja.origen !== 'COBERTURA_TURNO' && !MX_DECIDIDO.has(ja.estado)) out.push('esp');
    return out;
};
window.mxPorValidarBloque = function (filas) {
    // Además de contar, guarda dónde está cada uno (persona|fecha, en el orden de la grilla) para que la hoja lleve a su celda
    const n = { esp: 0, lugares: { esp: [] } };
    (filas || []).forEach(r => {
        const emp = (r && r.emp) || {};
        const dias = emp.dias || {};
        Object.keys(dias).sort().forEach(d => {
            if (d !== 'info') window.mxPorValidarDia(dias[d]).forEach(k => { n[k] += 1; n.lugares[k].push(emp.id + '|' + d); });
        });
    });
    return n;
};
window.mxAvisoValidarHtml = function (n) {
    if (!n) return '';
    const est = window._estadosAsistencia || {};
    const e = window._rvEsc;
    const tipos = [
        { k: 'esp', sigla: (est['JORNADA_ESPECIAL'] || {}).short_label || 'ESP', ico: (est['JORNADA_ESPECIAL'] || {}).icono_bi || 'bi-star-fill',
          que: n.esp === 1 ? 'jornada especial' : 'jornadas especiales' },
    ];
    const lug = n.lugares || {};
    return tipos.filter(t => n[t.k]).map(t => '<button type="button" class="gh-hoja gh-val gh-val-' + t.k + '" onclick="window.mxIrAPendiente(this)"'
        + ' data-lugares="' + e((lug[t.k] || []).join(',')) + '"'
        + ' title="' + e(n[t.k] + ' ' + t.que + ' por validar. Cada clic lleva al siguiente día en la grilla; Enter abre el día para decidir') + '">'
        + '<i class="bi ' + e(t.ico) + '" aria-hidden="true"></i>' + n[t.k] + ' ' + e(t.sigla) + ' por validar</button>').join('');
};
// Abre el bloque si está plegado y después hace «ir»
window.mxAbrirBloqueY = function (tb, ir) {
    if (tb.classList.contains('gh-plegado')) {
        const pl = tb.querySelector('.gh-plegar');
        if (pl) window.mxPlegarHorario(pl);
        setTimeout(ir, 60);
    } else ir();
};
// Hoja «por validar»: lleva a la celda del siguiente día pendiente de ese tipo, la marca con el anillo azul marino y la deja
// lista para abrirla con Enter (ahí se aprueba, rechaza o compensa). Cada clic avanza al siguiente y vuelve al primero.
window.mxIrAPendiente = function (btn) {
    const tb = btn && btn.closest('tbody.gh-grupo');
    const lugares = String((btn && btn.dataset.lugares) || '').split(',').filter(Boolean);
    if (!tb || !lugares.length) return;
    const quieto = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.mxAbrirBloqueY(tb, () => {
        const desde = Number(btn.dataset.i || 0);
        for (let k = 0; k < lugares.length; k++) {
            const i = (desde + k) % lugares.length;
            const [emp, fecha] = lugares[i].split('|');
            const fila = document.getElementById('row-empleado-' + emp);
            const td = fila && fila.querySelector('td.col-day[data-fecha="' + fecha + '"]');
            if (!td) continue;
            btn.dataset.i = i + 1;
            td.scrollIntoView({ block: 'center', inline: 'center', behavior: quieto ? 'auto' : 'smooth' });
            td.classList.remove('rv-recien');
            void td.offsetWidth;
            td.classList.add('rv-recien');
            setTimeout(() => td.classList.remove('rv-recien'), 1700);
            setTimeout(() => td.focus({ preventScroll: true }), quieto ? 0 : 400);
            return;
        }
    });
};

// ── Días por revisar (Reglas de marcaciones): lista bajo la fila de la persona (versión C mejorada, elegida por el dueño 06-11-2026) ──
// Cada día dice su regla, sus marcas con tipo y hora (la que el sistema propone cambiar, con borde rojo punteado y «→ SALIDA»), su turno
// y el botón «Revisar», que abre la misma ventana de corrección. Los días salen de la grilla (revision_marcas); las marcas y la propuesta,
// del mismo servicio que usa esa ventana (/marcaciones/dia/). Textos con comillas y concatenación: el minificador del servidor (rjsmin)
// come los espacios de las plantillas anidadas.
window.MX_DIAS_CORTOS = ['DOM', 'LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB'];
window.MX_TXT_CIERRE_BLOQUEADO = 'Mientras queden días por revisar, el cierre del tramo de su área está bloqueado';
window.mxFechaCortaRev = function (d) {
    const dt = new Date(d + 'T00:00:00');
    return window.MX_DIAS_CORTOS[dt.getDay()] + ' ' + d.substring(8, 10) + '-' + d.substring(5, 7);
};
window.mxSecuenciaEnPalabras = function (sec) {
    return String(sec || '').split('').map(c => c === 'E' ? 'ENTRADA' : (c === 'S' ? 'SALIDA' : c)).join(' · ');
};
window.mxDiasEnRevision = function (emp, dates) {
    const dias = (emp && emp.dias) || {};
    return (dates || Object.keys(dias).sort()).filter(d => d !== 'info' && dias[d] && dias[d].revision_marcas);
};
window._rvEsc = function (x) {
    return String(x == null ? '' : x).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
};
window.mxAvisoBloqueHtml = function (n) {
    return '<button type="button" class="gh-hoja rv-grupo" onclick="window.mxIrARevisar(this)" title="' + window.MX_TXT_CIERRE_BLOQUEADO + '">'
        + '<i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i>' + n + (n === 1 ? ' día por revisar' : ' días por revisar') + '</button>';
};
window.mxBandaRevisionHtml = function (emp, dates) {
    const fechas = window.mxDiasEnRevision(emp, dates);
    if (!fechas.length) return '';
    const e = window._rvEsc;
    const nombre = window.nombreTitulo(emp.nombre_completo || '');
    const puedeEditar = typeof AuthService !== 'undefined' && AuthService.hasPermission && AuthService.hasPermission('marcaciones.editar');
    const items = fechas.map(d => {
        const di = emp.dias[d];
        const corta = window.mxFechaCortaRev(d);
        const sec = window.mxSecuenciaEnPalabras(di.revision_secuencia);
        const ent = di.hora_entrada_teorica ? String(di.hora_entrada_teorica).substring(0, 5) : '';
        const sal = di.hora_salida_teorica ? String(di.hora_salida_teorica).substring(0, 5) : '';
        const reclasifica = (di.revision_opciones || []).indexOf('RECLASIFICAR') >= 0 ? '1' : '';
        return '<li class="rv-item" data-emp="' + emp.id + '" data-fecha="' + d + '" data-reclasificar="' + reclasifica + '">'
            + '<span class="rv-dia"><b>' + corta + '</b><span>' + (sec ? 'regla ' + e(sec) : 'regla de marcaciones') + '</span></span>'
            + '<span class="rv-marcas" data-cargar="1"></span>'
            + (ent && sal ? '<span class="rv-turno">turno ' + ent + '–' + sal + '</span>' : '')
            + (puedeEditar ? '<button type="button" class="rv-btn" data-rv-emp="' + emp.id + '" data-rv-fecha="' + d + '" aria-label="'
                + e('Revisar ' + corta + ', ' + nombre) + '">Revisar</button>' : '')
            + '</li>';
    }).join('');
    const n = fechas.length;
    return '<tr class="rv-banda" id="rv-banda-' + emp.id + '" data-emp="' + emp.id + '">'
        + '<td class="rv-nom"><span class="rv-nomtxt" title="' + window.MX_TXT_CIERRE_BLOQUEADO + '">'
        + '<i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i>' + n + (n === 1 ? ' día por revisar' : ' días por revisar') + '</span></td>'
        + '<td class="rv-esp"></td>'
        + '<td class="rv-dias"><ul class="rv-lista" aria-label="' + e('Días por revisar de ' + nombre) + '">' + items + '</ul></td>'
        + '</tr>';
};
// Columnas de la fila de la lista (las mismas de la grilla) y su ubicación: el nombre fijo a la izquierda y la lista pegada justo
// después de las columnas que queden fijas (en pantallas anchas también quedan fijas las de resumen)
window.mxBandasAjustar = function (root) {
    const cont = root || document.getElementById('marcaciones-view-container');
    if (!cont) return;
    const opaco = (c, def) => (!c || c === 'transparent' || c === 'rgba(0, 0, 0, 0)') ? def : c;
    cont.querySelectorAll('tr.rv-banda').forEach(band => {
        const fila = document.getElementById('row-empleado-' + band.dataset.emp);
        if (!fila) return;
        const celdas = Array.from(fila.children);
        const nDias = celdas.filter(c => c.classList.contains('col-day')).length;
        const nEsp = celdas.length - 1 - nDias;
        const tdNom = band.querySelector('td.rv-nom'), tdEsp = band.querySelector('td.rv-esp'), tdDias = band.querySelector('td.rv-dias');
        if (tdEsp) { if (nEsp > 0) tdEsp.colSpan = nEsp; else tdEsp.remove(); }
        if (tdDias) tdDias.colSpan = Math.max(1, nDias);
        if (!fila.offsetParent) return;                     // bloque plegado: se ubica al abrirlo
        const fondo = opaco(getComputedStyle(celdas[0]).backgroundColor, '#ffffff');
        if (tdNom) tdNom.style.background = fondo;
        if (tdDias) tdDias.style.background = fondo;
        let fijo = 0;
        celdas.forEach(c => {
            if (c.classList.contains('col-day')) return;
            const cs = getComputedStyle(c);
            if (cs.position === 'sticky') fijo = Math.max(fijo, (parseFloat(cs.left) || 0) + c.offsetWidth);
        });
        if (tdEsp && tdEsp.isConnected && celdas[1]) {
            const cs1 = getComputedStyle(celdas[1]);
            const pegada = cs1.position === 'sticky';
            tdEsp.style.position = pegada ? 'sticky' : '';
            tdEsp.style.left = pegada ? cs1.left : '';
            tdEsp.style.zIndex = pegada ? '40' : '';
            tdEsp.style.background = opaco(cs1.backgroundColor, fondo);
        }
        const ul = band.querySelector('.rv-lista');
        if (ul) ul.style.left = (fijo + 12) + 'px';
    });
};
// Las marcas de cada día por revisar, con la misma propuesta que muestra la ventana de corrección (solo si la regla permite cambiar
// el tipo de una marca y la cantidad de marcas no deja dudas)
window.mxBandasCargarMarcas = function (root) {
    const cont = root || document.getElementById('marcaciones-view-container');
    if (!cont) return;
    cont.querySelectorAll('.rv-item .rv-marcas[data-cargar]').forEach(box => {
        box.removeAttribute('data-cargar');
        const li = box.closest('.rv-item');
        const fecha = li.dataset.fecha;
        fetch('/api/asistencia/marcaciones/dia/?empleado_id=' + encodeURIComponent(li.dataset.emp) + '&fecha=' + encodeURIComponent(fecha))
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (!data || !Array.isArray(data.marcas) || !box.isConnected) return;
                const proponer = li.dataset.reclasificar === '1' && !data.fecha_cerrada && !data.marcas.some(m => m.dudoso);
                box.innerHTML = data.marcas.map(m => {
                    const tipo = String(m.tipo_actual || m.tipo_reloj || '').toUpperCase();
                    const sug = String(m.sugerido || '').toUpperCase();
                    const prop = proponer && sug && sug !== tipo;
                    const otroDia = (m.fecha && m.fecha !== fecha) ? '<span class="rv-marca-otro">' + m.fecha.substring(8, 10) + '-' + m.fecha.substring(5, 7) + '</span>' : '';
                    return '<span class="rv-marca' + (prop ? ' rv-prop' : '') + '"' + (prop ? ' title="El sistema propone cambiarla a ' + sug + '"' : '') + '>'
                        + '<small>' + window._rvEsc(tipo) + '</small><b>' + window._rvEsc(m.hora) + '</b>' + otroDia + (prop ? '<em>→ ' + sug + '</em>' : '') + '</span>';
                }).join('');
            })
            .catch(() => { /* sin las marcas la lista igual dice el día, la regla y el botón */ });
    });
};
// Aviso del bloque: abre el bloque si está plegado y lleva a la primera lista
window.mxIrARevisar = function (btn) {
    const tb = btn && btn.closest('tbody.gh-grupo');
    if (!tb) return;
    const quieto = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    const ir = () => {
        const band = tb.querySelector('tr.rv-banda');
        if (!band) return;
        band.scrollIntoView({ block: 'center', inline: 'nearest', behavior: quieto ? 'auto' : 'smooth' });
        const b = band.querySelector('.rv-btn');
        if (b) setTimeout(() => b.focus({ preventScroll: true }), quieto ? 0 : 400);
    };
    window.mxAbrirBloqueY(tb, ir);
};
// Cuenta de nuevo los días del bloque (tras corregir uno) y actualiza o quita su aviso
window.mxActualizarAvisoBloque = function (tb) {
    if (!tb) return;
    const tit = tb.querySelector('tr.gh-titulo .gh-hojas');
    if (!tit) return;
    const n = tb.querySelectorAll('tr.rv-banda .rv-item').length;
    const chip = tit.querySelector('.rv-grupo');
    if (chip) chip.remove();
    if (n) tit.insertAdjacentHTML('afterbegin', window.mxAvisoBloqueHtml(n));
};
// Tras «Sí, corregir» en la ventana: la celda marca el cambio y la fila confirma, en el mismo lugar, que el día quedó corregido
window.mxAvisarCorreccion = function (empId) {
    const c = window._rvUltimaCorreccion;
    if (!c || String(c.empId) !== String(empId)) return;
    window._rvUltimaCorreccion = null;
    const fila = document.getElementById('row-empleado-' + empId);
    if (!fila) return;
    const celda = fila.querySelector('td.col-day[data-fecha="' + c.fecha + '"]');
    if (celda) { celda.classList.add('rv-recien'); setTimeout(() => celda.classList.remove('rv-recien'), 1700); }
    if (celda && celda.classList.contains('rv-celda')) return;     // sigue por revisar: la lista lo sigue mostrando
    const aviso = '<i class="bi bi-check-circle-fill" aria-hidden="true"></i>' + window.mxFechaCortaRev(c.fecha) + ' corregido · el día se volvió a calcular';
    const band = document.getElementById('rv-banda-' + empId);
    if (band && band.querySelector('.rv-lista')) {
        const li = document.createElement('li');
        li.className = 'rv-hecho'; li.setAttribute('role', 'status'); li.innerHTML = aviso;
        band.querySelector('.rv-lista').prepend(li);
        setTimeout(() => li.remove(), 4500);
        return;
    }
    // No le quedan días por revisar: una fila breve con la confirmación, que se va sola
    const tmp = document.createElement('tr');
    tmp.className = 'rv-banda rv-banda-hecho'; tmp.id = 'rv-banda-' + empId; tmp.dataset.emp = String(empId);
    tmp.innerHTML = '<td class="rv-nom"></td><td class="rv-esp"></td><td class="rv-dias"><ul class="rv-lista"><li class="rv-hecho" role="status">' + aviso + '</li></ul></td>';
    fila.insertAdjacentElement('afterend', tmp);
    fila.classList.add('rv-con-banda');
    window.mxBandasAjustar(fila.closest('tbody') || undefined);
    setTimeout(() => { tmp.remove(); fila.classList.remove('rv-con-banda'); }, 4500);
};
if (!window._rvClickBound) {
    window._rvClickBound = true;
    document.addEventListener('click', ev => {
        const b = ev.target && ev.target.closest && ev.target.closest('.rv-btn[data-rv-emp]');
        if (!b) return;
        const emp = parseInt(b.dataset.rvEmp, 10), fecha = b.dataset.rvFecha;
        const data = (window.stateMarcacionesApp && stateMarcacionesApp.data) || {};
        const m = data.matrix && (data.matrix[emp] || data.matrix[String(emp)]);
        const nombre = (m && m.info && m.info.nombre_completo)
            || ((data.empleados || []).find(x => String(x.id) === String(emp)) || {}).nombre_completo || '';
        if (typeof openManualEntryModal === 'function') openManualEntryModal(emp, fecha, nombre);
    });
}

window.buildStickyCols = function(sh, bonosNombres) {
    const C = window.GRID_COLLAPSED_W;
    // Horas extra del libro mayor: trabajadas, usadas, a pagar, no pagadas, por decidir (5 columnas)
    const heW = window._gridFlags && window._gridFlags.esBolsa ? 130 : 5 * 65;
    const cols = {
        empleado: { width: 260 },
        bonos: { width: sh.hasBonos ? (sh.showBonos ? bonosNombres.length * 65 : C) : 0 },
        incidencias: { width: sh.hasInc ? (sh.showIncidencias ? sh.nInc * 65 : C) : 0 },
        he: { width: sh.showHE ? heW : C },
        // Tiempo no trabajado del libro mayor: deuda, perdonado, cubierto, pendiente (4 columnas)
        deudas: { width: sh.hasDeudas ? (sh.showDeudas ? 4 * 65 : C) : 0 },
        saldo: { width: sh.hasSaldo ? 84 : 0 }
    };
    if (sh.hayBolsa) {
        cols.bolsa = { width: sh.showSaldoMeta ? 3 * 84 : C };
        cols.espera = { width: sh.showSaldoMeta ? 3 * 84 : C };
    }
    return cols;
};

window.getStickyLeft = function(key, subIndex, stickyCols, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta) {
    let offset = 0;
    const he1 = window._gridFlags && window._gridFlags.esBolsa;
    const keys = ['empleado', 'bonos', 'incidencias', 'he', 'deudas', 'saldo', 'bolsa', 'espera'];
    for (const k of keys) {
        if (k === key) {
            if (k === 'bonos' && showBonos) return offset + subIndex * 65;
            if (k === 'incidencias' && showIncidencias) return offset + subIndex * 65;
            if (k === 'he' && showHE) return offset + (he1 ? 0 : subIndex * 65);
            if (k === 'deudas' && showDeudas) return offset + subIndex * 65;
            if (k === 'bolsa' && showSaldoMeta) return offset + subIndex * 84;
            if (k === 'espera' && showSaldoMeta) return offset + subIndex * 84;
            return offset;
        }
        if (stickyCols[k]) {
            offset += stickyCols[k].width;
        }
    }
    return offset;
};

window.getStickyWidthStyle = function(key, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta) {
    const C = window.GRID_COLLAPSED_W;
    const esB = window._gridFlags && window._gridFlags.esBolsa;
    let w = 0;
    if (key === 'bonos') w = showBonos ? 65 : C;
    else if (key === 'incidencias') w = showIncidencias ? 65 : C;
    else if (key === 'he') w = showHE ? (esB ? 130 : 65) : C;
    else if (key === 'deudas') w = showDeudas ? 65 : C;
    else if (key === 'saldo') w = 84;
    else if (key === 'bolsa') w = showSaldoMeta ? 3 * 84 : C;   // «Avance del ciclo»: una columna del ancho de las tres de antes
    else if (key === 'espera') w = showSaldoMeta ? 3 * 84 : C;  // «Uso del tope»
    return `width:${w}px; min-width:${w}px; max-width:${w}px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;`;
};

// ── Libro mayor de minutos (lo calcula el servidor; la grilla solo lo muestra) ──────────────
// Cada minuto de deuda termina perdonado, cubierto o pendiente; cada minuto de hora extra termina
// usado, a pagar, no pagado o por decidir. Sin libro (dato viejo o Bolsa Flexible) las columnas quedan vacías.
window.libroDeFila = function(r) {
    const L = (r && r.libro) || {};
    const n = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
    return {
        deuda_bruta: n(L.deuda_bruta), perdonado: n(L.perdonado), cubierto: n(L.cubierto), pendiente: n(L.pendiente),
        he_trabajadas: n(L.he_trabajadas), he_usadas: n(L.he_usadas_deuda) + n(L.he_usadas_inasistencia),
        he_a_pagar: n(L.he_a_pagar), he_no_pagadas: n(L.he_no_pagadas), he_por_decidir: n(L.he_por_decidir),
        saldo: n(L.saldo), politica: L.politica || null
    };
};
window.totalesConLibro = function(rows) {
    return rows.reduce((acc, r) => {
        acc.he_bruto += r.he_bruto; acc.he_apr += r.he_apr; acc.he_rec += r.he_rec; acc.he_pend += r.he_pend;
        acc.d_tot += r.d_tot; acc.saldo += r.saldo;
        acc.cnt_atr += r.cnt_atr; acc.cnt_sad += r.cnt_sad; acc.cnt_inas += r.cnt_inas;
        acc.cnt_esp += r.cnt_esp; acc.cnt_per += r.cnt_per;
        acc.min_col += (r.min_col || 0); acc.min_per += (r.min_per || 0);
        acc.min_atr += (r.min_atr || 0); acc.min_sad += (r.min_sad || 0);
        const L = window.libroDeFila(r);
        acc.l_deuda_bruta += L.deuda_bruta; acc.l_perdonado += L.perdonado; acc.l_cubierto += L.cubierto; acc.l_pendiente += L.pendiente;
        acc.l_he_trabajadas += L.he_trabajadas; acc.l_he_usadas += L.he_usadas; acc.l_he_a_pagar += L.he_a_pagar;
        acc.l_he_no_pagadas += L.he_no_pagadas; acc.l_he_por_decidir += L.he_por_decidir;
        return acc;
    }, {he_bruto:0,he_apr:0,he_rec:0,he_pend:0,d_tot:0,saldo:0,cnt_atr:0,cnt_sad:0,cnt_inas:0,cnt_esp:0,cnt_per:0,min_col:0,min_per:0,min_atr:0,min_sad:0,
        l_deuda_bruta:0,l_perdonado:0,l_cubierto:0,l_pendiente:0,l_he_trabajadas:0,l_he_usadas:0,l_he_a_pagar:0,l_he_no_pagadas:0,l_he_por_decidir:0});
};

window.calcularStatsEmpleado = function(emp, dates, feriadosArray) {
    let he_bruto=0, he_apr=0, he_rec=0, he_pend=0, he_compensado=0, d_tot=0, min_atr=0, min_sad=0, min_col=0, min_per=0;
    let cnt_atr=0, cnt_sad=0, cnt_inas=0, cnt_esp=0, cnt_per=0, cnt_efectivos=0;
    const esBolsa = emp.tipo_programacion === 'BOLSA_FLEXIBLE'
                 || emp.tipo_programacion === 'FLEXIBLE_BOLSA'
                 || (emp.turno && emp.turno.toUpperCase().includes('TRANSPORTE'))
                 || (emp.info && (emp.info.tipo_programacion === 'BOLSA_FLEXIBLE' || emp.info.tipo_programacion === 'FLEXIBLE_BOLSA' || (emp.info.turno && emp.info.turno.toUpperCase().includes('TRANSPORTE'))));
    emp._esBolsaFlag = esBolsa;
    let acumBolsa=0, excedido=false, metaMin=0;
    let acumEspera=0;

    const prorBolsa = (esBolsa && emp.info && emp.info.bolsa_prorrateo) ? emp.info.bolsa_prorrateo : null;
    emp._prorrateoBolsa = prorBolsa;

    if (esBolsa && emp.info) {
        let metaOriginal = emp.info.meta_mensual_minutos
               || Math.round((emp.info.meta_horas_semanales || 0) * 60);

        // Vigencia parcial (ingreso/egreso a mitad del tramo): meta proporcional a los
        // días corridos disponibles (el servidor la calcula una sola vez en la matriz).
        // Ojo: el factor puede ser 0 (sin vigencia en el tramo) y también se aplica.
        if (prorBolsa && Number.isFinite(prorBolsa.factor) && prorBolsa.factor < 1) {
            metaOriginal = Math.round(metaOriginal * prorBolsa.factor);
        }

        let diasProgramados = 0;
        let diasJustificados = 0;

        dates.forEach(d => {
            // Fuera de la vigencia del contrato no hay días programados
            if (prorBolsa && (d < prorBolsa.desde || d > prorBolsa.hasta)) return;
            const dt = new Date(d+'T00:00:00');
            const isFer = feriadosArray.includes(d);
            const diCheck = emp.dias[d] || {};
            
            const dayDB = (dt.getDay() + 6) % 7; 
            const isStructurallyLibre = (emp.info.turno_dias && emp.info.turno_dias[dayDB] && emp.info.turno_dias[dayDB].es_libre === 1);
            
            const isDescanso = isFer || isStructurallyLibre || (diCheck.estado === 'LIBRE');
            
            if (!isDescanso) {
                diasProgramados++;
                const estadosJustificados = ['VACACIONES', 'LICENCIA', 'LIC_COMUN', 'LIC_MUTUAL', 'CUMPLEAÑOS', 'DUELO', 'PERMISO', 'NO NACIDO', 'DEFUNCION'];
                const nom = diCheck.nomenclatura ? diCheck.nomenclatura.trim().toUpperCase() : '';
                const estUpper = diCheck.estado ? diCheck.estado.toUpperCase() : '';
                const isDEOP = (nom === 'DEOP' || estUpper.includes('DESCANSO') || estUpper.includes('OPERATIVO'));

                const isJustificado = !isDEOP && diCheck.estado && (
                    estadosJustificados.some(ej => estUpper.includes(ej)) ||
                    (nom !== '' && nom !== 'LIB' && nom !== 'FER' && nom !== 'OK')
                );
                
                if (isJustificado) {
                    diasJustificados++;
                    diCheck._esDiaJustificadoBolsa = true;
                }
            }
        });

        if (diasProgramados > 0 && diasJustificados > 0) {
            const valorTurnoMin = metaOriginal / diasProgramados;
            metaMin = Math.round(metaOriginal - (valorTurnoMin * diasJustificados));
            emp._metaOriginalBolsa = metaOriginal;
            emp._diasJustificadosBolsa = diasJustificados;
            emp._valorTurnoMinBolsa = valorTurnoMin;
        } else {
            metaMin = metaOriginal;
        }
        
        if (emp.info.meta_ajustada_minutos_descuento && diasJustificados === 0) {
            metaMin = Math.max(0, metaMin - emp.info.meta_ajustada_minutos_descuento);
        }
    }

    let acumSemanal = 0;
    let startDayJS = 1; 
    if (emp.info && emp.info.primer_dia_semana_turno !== undefined) {
        startDayJS = (emp.info.primer_dia_semana_turno + 1) % 7;
    }

    dates.forEach(d => {
        const dt = new Date(d+'T00:00:00');
        if (dt.getDay() === startDayJS) acumSemanal = 0; 

        const di = emp.dias[d];
        if (!di) return;

        if (esBolsa) {
            di._esBolsa = true;
            di._metaMinBolsa = metaMin;
            if (di.minutos_espera) acumEspera += Number(di.minutos_espera || 0);
        }

        const trab = Math.round((di.horas_trabajadas||0)*60);
        const isEsp = di.estado === 'JORNADA_ESPECIAL' || di.estado === 'EXTRA' || di.estado === 'FERIADO Y JORNADA EXTRA' || di.estado === 'DÍA LIBRE Y JORNADA EXTRA' || (!esBolsa && Number(di.horas_teoricas || 0) === 0 && Number(di.horas_trabajadas || 0) > 0);
        const tieneJa = Boolean(di.jornada_adicional && di.jornada_adicional.estado !== 'RECHAZADA');
        
        if (!esBolsa && !isEsp) {
            acumSemanal += trab;
        }
        if (!esBolsa) di._acumuladoSemanalSnap = acumSemanal;
        if (!isEsp && !esBolsa) {
            const condTipo = Number(di.deuda_condonada || 0);

            // Colación y Permisos NUNCA se perdonan por atraso o salida
            const rawCol = Number(di.minutos_exceso_colacion || 0);
            // Permiso del día: el tomado entre marcas o el ingresado por horas. Cuando están los dos son el mismo
            // permiso (la justificación se ingresa sobre la pausa marcada): se toma el mayor, nunca la suma.
            const rawPer = Math.max(Number(di.minutos_permisos_detectados || 0), Number(di.minutos_permiso_personal_deuda || 0));

            // Atraso condonado solo si condTipo es 2, 3 o 5
            const condonaAtr = (condTipo === 2 || condTipo === 3 || condTipo === 5);
            const rawAtr = condonaAtr ? 0 : Number(di.minutos_atraso || 0);

            // Salida adelantada condonada solo si condTipo es 1, 3 o 5
            const condonaSad = (condTipo === 1 || condTipo === 3 || condTipo === 5);
            const rawSad = condonaSad ? 0 : Number(di.minutos_salida_adelantada || 0);

            // Balance Matricial Limpio y Canónico:
            // - d_tot acumula la deuda neta imputable (minutos_deuda), respetando condonación completa (Tipo 5).
            // - min_col, min_per, min_atr, min_sad acumulan fielmente los eventos reales de reloj descontando condonaciones específicas.
            const dayNetDeuda = (condTipo === 5) ? 0 : Number(di.minutos_deuda || 0);

            d_tot   += dayNetDeuda;
            min_col += rawCol;
            min_per += rawPer;
            min_atr += rawAtr;
            min_sad += rawSad;

            if ((di.minutos_atraso || 0) > 0 && !condonaAtr) cnt_atr++;
            if ((di.minutos_salida_adelantada || 0) > 0 && !condonaSad) cnt_sad++;
            if (di.tiene_permiso_hora || di.permiso_activo || rawPer > 0) cnt_per++;
        }
        const jaEst = di.jornada_adicional ? di.jornada_adicional.estado : null;
        const esJaRechazada = jaEst === 'RECHAZADA';
        const esJaHE = jaEst === 'HORAS_EXTRAS';
        // Una jornada gastada en compensar una inasistencia ya no se paga como jornada especial
        const esCompensatoria = jaEst === 'COMPENSATORIA' || di.estado === 'JORNADA_COMPENSATORIA';
        const tieneJaPendienteOExtra = Boolean(di.jornada_adicional && (jaEst === 'PENDIENTE' || jaEst === 'JORNADA_ESPECIAL' || jaEst === 'EXTRA'));
        const esDiaEspecialValido = !esJaRechazada && !esJaHE && !esCompensatoria && (
            di.estado === 'JORNADA_ESPECIAL' ||
            di.estado === 'EXTRA' ||
            di.estado === 'FERIADO Y JORNADA EXTRA' ||
            di.estado === 'DÍA LIBRE Y JORNADA EXTRA' ||
            (!esBolsa && Number(di.horas_teoricas || 0) === 0 && Number(di.horas_trabajadas || 0) > 0 && di.estado !== 'RECHAZADA')
        );

        if (di.estado === 'INASISTENCIA') cnt_inas++;
        if (tieneJaPendienteOExtra || esDiaEspecialValido) cnt_esp++;
        if (di.hora_entrada_real && !isEsp && !['LIBRE','FERIADO','INASISTENCIA'].includes(di.estado)) cnt_efectivos++;

        if (!isEsp) {
            if (esBolsa) {
                const snapAntes = acumBolsa; 
                acumBolsa += trab;
                di._acumuladoBolsaSnapPrev = snapAntes; 
                di._acumuladoBolsaSnap = acumBolsa;    
                di._metaMinBolsa = metaMin;             
                if (excedido)                                    he_bruto += trab;
                else if (acumBolsa > metaMin && trab > 0) { he_bruto += acumBolsa - metaMin; excedido = true; }
            } else {
                he_bruto += Math.max(di.minutos_extra_bruto || 0, di.minutos_extra_autorizados || 0);
            }
        } else if (esBolsa) {
            di._acumuladoBolsaSnapPrev = acumBolsa;
            di._acumuladoBolsaSnap = acumBolsa;
            di._metaMinBolsa = metaMin;
        }

        if (!isEsp && !esBolsa) {
            if (di.estado_he === 'APROBADO') {
                const apr = di.minutos_extra_autorizados || 0;
                he_apr += apr;
            } else if (di.estado_he === 'RECHAZADO') {
                he_rec += (di.minutos_extra_bruto || 0);
            } else if ((di.minutos_extra_bruto || 0) > 0) {
                he_pend += (di.minutos_extra_bruto || 0);
            }
        }
        he_compensado += (di.minutos_compensados_he || 0);
    });

    if (esBolsa) {
        he_pend = 0;
        he_apr = 0;
        he_rec = 0;
        he_bruto = Math.max(0, acumBolsa - metaMin);
        d_tot = 0;
        min_atr = 0;
        min_sad = 0;
        min_col = 0;
        min_per = 0;
        cnt_atr = 0;
        cnt_sad = 0;
    }

    he_bruto = Math.round(he_bruto * 10000) / 10000;
    he_apr = Math.round(he_apr * 10000) / 10000;
    he_rec = Math.round(he_rec * 10000) / 10000;
    he_pend = Math.round(he_pend * 10000) / 10000;

    let rawSaldo = esBolsa ? 0 : (he_apr - d_tot - he_compensado);
    const saldo = Math.abs(rawSaldo) < 0.0083 ? 0 : Math.round(rawSaldo * 10000) / 10000;
    const saldoMeta = esBolsa ? (acumBolsa - metaMin) : null;
    const metaHorasEspera = (emp.info && emp.info.meta_horas_espera !== undefined && emp.info.meta_horas_espera !== null)
        ? Number(emp.info.meta_horas_espera)
        : 88.0;
    let metaEsperaMin = Math.round(metaHorasEspera * 60);
    // La meta de espera (88 h, art. 25 bis) se prorratea igual que la meta de la bolsa
    if (prorBolsa && Number.isFinite(prorBolsa.factor) && prorBolsa.factor < 1) {
        metaEsperaMin = Math.round(metaEsperaMin * prorBolsa.factor);
    }
    const saldoEspera = esBolsa ? (acumEspera - metaEsperaMin) : null;
    // Libro mayor de minutos del servidor: su saldo manda (incluye tolerancia y el perdón del cuadre a cero)
    const libro = (!esBolsa && emp.info && emp.info.libro) ? emp.info.libro : null;
    const saldoFinal = (libro && Number.isFinite(Number(libro.saldo))) ? Number(libro.saldo) : saldo;
    return { emp, he_bruto, he_apr, he_rec, he_pend, d_tot, min_atr, min_sad, min_col, min_per,
             cnt_atr, cnt_sad, cnt_inas, cnt_esp, cnt_per, cnt_efectivos, saldo: saldoFinal, libro,
             esBolsa, metaMin, acumBolsa, saldoMeta, acumEspera, metaEsperaMin, saldoEspera };
};

window.renderEmployeeRowHtml = function(r, dates, feriadosArray, getFeriadoDesc, hasBonos, showBonos, bonosNombres, bonosEval, showIncidencias, showHE, showDeudas, hayBolsa, showSaldoMeta, s, stickyCols) {
    const { emp } = r;
    const sh = {nInc: hayBolsa ? 4 : 6, hasInc: !hayBolsa, hasDeudas: !hayBolsa, hasSaldo: !hayBolsa, heFull: !hayBolsa};
    const _I = sh.nInc === 6 ? {per:0,atr:1,sad:2,ina:3,esp:4,tot:5} : {per:0,ina:1,esp:2,tot:3};
    const _heFull = sh.heFull;
    const isSaldoZero = Math.abs(r.saldo) < 0.0083;
    const sClass = isSaldoZero ? 'matrix-saldo-zero' : (r.saldo > 0 ? 'text-success' : 'text-danger');
    const sPrefix = isSaldoZero ? '' : (r.saldo > 0 ? '+' : '-');
    const nameClass = emp.activo ? '' : 'text-danger opacity-75';

    const empEval = bonosEval[emp.id] || {};
    let bonoCells = '';
    if (hasBonos) {
        const wStyle = window.getStickyWidthStyle('bonos', showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);
        if (showBonos) {
            bonoCells = bonosNombres.map((bName, idx) => {
                const bRes = empEval[bName];
                const borderStyle = idx === 0 ? 'border-left:3px solid #10b981' : 'border-left:1px solid #e2e8f0';
                const cellLeft = window.getStickyLeft('bonos', idx, stickyCols, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);
                const inlineStyle = `position:sticky; z-index:40; ${borderStyle}; left:${cellLeft}px; ${wStyle}`;
                if (!bRes || !bRes.aplica) return `<td class="text-center align-middle sticky-premium-col" style="background:#f8fafc;font-size:0.75rem;${inlineStyle}"></td>`;
                if (bRes.califica) {
                    return `<td class="text-center align-middle text-success fw-bold sticky-premium-col" style="background:#f8fafc;font-size:1.1rem;${inlineStyle}" title="${bRes.motivo||''}"><i class="bi bi-check-circle-fill"></i></td>`;
                } else {
                    return `<td class="text-center align-middle text-danger opacity-75 sticky-premium-col" style="background:#f8fafc;font-size:1.1rem;${inlineStyle}" title="${bRes.motivo||''}"><i class="bi bi-dash-circle-fill"></i></td>`;
                }
            }).join('');
        } else {
            let cntAplica = 0;
            let cntCalifica = 0;
            bonosNombres.forEach(bName => {
                const bRes = empEval[bName];
                if (bRes && bRes.aplica) {
                    cntAplica++;
                    if (bRes.califica) cntCalifica++;
                }
            });
            const cellLeft = window.getStickyLeft('bonos', 0, stickyCols, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);
            const inlineStyle = `position:sticky; z-index:40; left:${cellLeft}px; ${wStyle}`;
            if (cntAplica > 0) {
                const color = cntCalifica === cntAplica ? 'text-success' : (cntCalifica > 0 ? 'text-warning' : 'text-danger');
                bonoCells = `<td class="text-center align-middle fw-bold ${color} sticky-premium-col" style="background:#f8fafc;font-size:0.78rem;border-left:3px solid #10b981;${inlineStyle}" title="${cntCalifica} cumplidos de ${cntAplica} aplicables">${cntCalifica}/${cntAplica}</td>`;
            } else {
                bonoCells = `<td class="text-center align-middle text-muted sticky-premium-col" style="background:#f8fafc;font-size:0.78rem;border-left:3px solid #10b981;${inlineStyle}"></td>`;
            }
        }
    }

    const dayCells = dates.map(d => {
        const di = emp.dias[d];
        const dt = new Date(d+'T00:00:00');
        const feriadoDesc = getFeriadoDesc(d);
        const isFer = !!feriadoDesc;
        const isWE  = (dt.getDay()===0||dt.getDay()===6);
        const bg = isFer ? 'background:#fff8e6;' : dt.getDay() === 0 ? 'background:#f6f7fa;' : isWE ? 'background:#fafbfd;' : '';
        const empNameEsc = (emp.nombre_completo||'').replace(/'/g,"\\'");
        const hEnt = di && di.hora_entrada_real ? `'${di.hora_entrada_real}'` : 'null';
        const hSal = di && di.hora_salida_real ? `'${di.hora_salida_real}'` : 'null';
        const cellContent = _analiticaCellContent(di, d, emp, stateMarcacionesApp.viewMode, isFer);
        // Rendimiento: antes cada celda llevaba incrustado el HTML completo de su tooltip en
        // data-bs-content (~3 KB × miles de celdas = 12 MB por render). Ahora solo se guardan
        // los datos en memoria y el tooltip se arma al pasar el mouse (ver _getCellTipHtml).
        const tipKey = emp.id + '|' + d;
        (window.__mxTipReg || (window.__mxTipReg = new Map())).set(tipKey, { di, d, dt, feriadoDesc, isWE, emp: Object.assign({}, emp, { stats: r }) });
        const _corteC = (window._gridFlags && window._gridFlags.esBolsa) ? window.getCorteLibreta(emp) : null;
        const corteCelda = (_corteC && d === _corteC) ? 'border-left:3px solid #8b5cf6;' : '';
        // Día por revisar (Reglas de marcaciones): la pastilla del estado (sigla y color de Configuración → Estados) lo dice; si la
        // regla calculó el día y su estado es otro (OK, ATR…), la celda lleva además un marco rojo. La lista bajo la fila explica qué encontró.
        const enRevision = !!(di && di.revision_marcas);
        const claseRev = enRevision ? (' rv-celda' + (di.estado !== 'ANOMALIA' ? ' rv-celda-marco' : '')) : '';
        const nomAria = window.nombreTitulo(emp.nombre_completo).replace(/"/g, '&quot;');
        const ariaCelda = enRevision
            ? 'Día por revisar: ' + nomAria + ', ' + window.formatFechaDDMMYYYY(d) + '. Una regla de marcaciones dejó este día en revisión.'
            : 'Acciones de asistencia: ' + nomAria + ', ' + window.formatFechaDDMMYYYY(d);
        return `<td class="col-day text-center p-0 align-middle cell-clickable${claseRev}" tabindex="0" role="button" aria-label="${ariaCelda}" data-fecha="${d}" style="${bg}${corteCelda}min-width:48px;height:28px;cursor:pointer;position:relative;overflow:visible !important;"
                    onclick="openAsistenciaActionModal(${emp.id},'${d}','${empNameEsc}',${hEnt},${hSal})"
                    ondblclick="openJustifyModal(${emp.id},'${empNameEsc}','${d}')"
                    data-grid-tooltip data-tip="${tipKey}">
                    ${cellContent}
                </td>`;
    }).join('');

    const hasHE = !r.esBolsa && r.he_pend > 0;
    const heIndicator = hasHE ? `<i class="bi bi-clock-history text-warning ms-1" style="font-size: 0.75rem" title="Tiene HE pendientes — Doble clic para gestionar"></i>` : '';

    const getStickyLeftLocal = (key, subIndex = 0) => window.getStickyLeft(key, subIndex, stickyCols, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);
    const getStickyWidthStyleLocal = (key) => window.getStickyWidthStyle(key, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);
    // Libro mayor de minutos de la persona (lo calcula el servidor con los mismos días de la grilla)
    const L = window.libroDeFila(r);
    // Días que una regla dejó por revisar en el tramo visible: la lista va en una fila propia, bajo la de la persona
    const bandaRev = window.mxBandaRevisionHtml ? window.mxBandaRevisionHtml(emp, dates) : '';

    return `<tr id="row-empleado-${emp.id}"${bandaRev ? ' class="rv-con-banda"' : ''}>
        <td class="${nameClass} sticky-col-analitica emp-name-cell text-start ps-2 align-middle" style="position:sticky; left:0; z-index:50; white-space:nowrap;cursor:pointer;font-size:0.75rem; width:260px; min-width:260px; max-width:260px;"
            ondblclick="openCuadreModal(${emp.id},'${(emp.nombre_completo||'').replace(/'/g,"\\'")}')"
            title="${hasHE ? 'Doble clic → Cuadre del tramo (hay horas extra por decidir)' : 'Doble clic → Cuadre del tramo'}">
            <div class="emp-id-row">
                ${cargoIconoHtml(emp.cargo)}
                <div class="emp-id-txt">
                    <div class="emp-name-link" title="${String(emp.nombre_completo || '').replace(/"/g, '&quot;')}">${window.nombreTitulo(emp.nombre_completo)||'—'}${heIndicator}</div>
                    <div class="emp-area-label">${emp.cargo ? emp.cargo + (stateMarcacionesApp.area ? '' : ' · ' + emp.area) : emp.area}${emp.turno?' · '+emp.turno:''}</div>
                    ${r.esBolsa ? (() => { const sm = r.saldoMeta || 0, ab = Math.abs(sm), hh = Math.floor(ab/60), mm = Math.round(ab%60); const t = (sm < 0 ? '\u2212' : sm > 0 ? '+' : '') + String(hh).padStart(2,'0') + ':' + String(mm).padStart(2,'0'); const pb = r.emp._prorrateoBolsa; const metaH = Math.round((r.metaMin || 0) / 60); const tit = (pb && Number.isFinite(pb.factor) && pb.factor < 1) ? ('Balance de la bolsa; meta ajustada a ' + metaH + ' h: vigencia de ' + pb.dias_disponibles + ' de ' + pb.dias_tramo + ' d\u00edas del tramo') : 'Balance de la bolsa de 180 h'; const warn = (pb && pb.aviso_21_dias) ? '\u26a0 ' : ''; return '<span class="gc-bolsa-chip ' + (sm < 0 ? 'neg' : sm > 0 ? 'pos' : '') + '" title="' + tit + '">' + warn + metaH + 'h ' + t + '</span>'; })() : ''}
                </div>
            </div>
        </td>
        ${bonoCells}
        ${!sh.hasInc ? '' : showIncidencias ? `
        <td class="text-center align-middle sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.78rem;border-left:3px solid #f59e0b;left:${getStickyLeftLocal('incidencias', _I.per)}px;${getStickyWidthStyleLocal('incidencias')}">${r.cnt_per||''}</td>
        ${_I.atr!==undefined?`<td class="text-center align-middle sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.78rem;left:${getStickyLeftLocal('incidencias', _I.atr)}px;${getStickyWidthStyleLocal('incidencias')}">${r.cnt_atr||''}</td>`:''}
        ${_I.sad!==undefined?`<td class="text-center align-middle sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.78rem;left:${getStickyLeftLocal('incidencias', _I.sad)}px;${getStickyWidthStyleLocal('incidencias')}">${r.cnt_sad||''}</td>`:''}
        <td class="text-center align-middle ${r.cnt_inas>0?'text-danger fw-bold':''} sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.78rem;left:${getStickyLeftLocal('incidencias', _I.ina)}px;${getStickyWidthStyleLocal('incidencias')}">${r.cnt_inas||''}</td>
        <td class="text-center align-middle ${r.cnt_esp>0?'text-info fw-bold':''} sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.78rem;left:${getStickyLeftLocal('incidencias', _I.esp)}px;${getStickyWidthStyleLocal('incidencias')}">${r.cnt_esp>0?r.cnt_esp+' <i class="bi bi-star-fill" aria-hidden="true"></i>':''}</td>
        <td class="text-center align-middle fw-bold sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.78rem;left:${getStickyLeftLocal('incidencias', _I.tot)}px;${getStickyWidthStyleLocal('incidencias')}">${((r.cnt_per||0)+(r.cnt_atr||0)+(r.cnt_sad||0)+(r.cnt_inas||0)+(r.cnt_esp||0))||''}</td>` : `<td class="text-center align-middle fw-bold sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.78rem;border-left:3px solid #f59e0b;color:#f59e0b;left:${getStickyLeftLocal('incidencias')}px;${getStickyWidthStyleLocal('incidencias')}">${((r.cnt_per||0)+(r.cnt_atr||0)+(r.cnt_sad||0)+(r.cnt_inas||0)+(r.cnt_esp||0))>0 ? '<i class="bi bi-flag-fill me-1"></i>' + ((r.cnt_per||0)+(r.cnt_atr||0)+(r.cnt_sad||0)+(r.cnt_inas||0)+(r.cnt_esp||0)) : ''}</td>`}
        ${showHE ? `
        ${_heFull?`<td class="text-center align-middle tabular-nums fw-bold sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;border-left:3px solid #3b82f6;left:${getStickyLeftLocal('he', 0)}px;${getStickyWidthStyleLocal('he')}">${r.esBolsa ? '—' : (L.he_trabajadas>0?_fmtMin(L.he_trabajadas):'')}</td>`:''}
        ${_heFull?`<td class="text-center align-middle tabular-nums sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;color:#2563eb;left:${getStickyLeftLocal('he', 1)}px;${getStickyWidthStyleLocal('he')}">${r.esBolsa ? '—' : (L.he_usadas>0?_fmtMin(L.he_usadas):'')}</td>`:''}
        ${_heFull?`<td class="text-center align-middle tabular-nums text-success fw-bold sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;left:${getStickyLeftLocal('he', 2)}px;${getStickyWidthStyleLocal('he')}">${r.esBolsa ? '—' : (L.he_a_pagar>0?_fmtMin(L.he_a_pagar):'')}</td>`:''}
        ${_heFull?`<td class="text-center align-middle tabular-nums text-muted sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;left:${getStickyLeftLocal('he', 3)}px;${getStickyWidthStyleLocal('he')}">${r.esBolsa ? '—' : (L.he_no_pagadas>0?_fmtMin(L.he_no_pagadas):'')}</td>`:''}
        <td class="text-center align-middle tabular-nums ${_heFull ? 'text-warning' : ''} fw-bold sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;left:${getStickyLeftLocal('he', 4)}px;${getStickyWidthStyleLocal('he')}">${_heFull ? (L.he_por_decidir>0?_fmtMin(L.he_por_decidir):'') : (r.he_bruto>0?_fmtMin(r.he_bruto):'')}</td>` : `<td class="text-center align-middle tabular-nums fw-bold sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;border-left:3px solid #3b82f6;color:#3b82f6;left:${getStickyLeftLocal('he')}px;${getStickyWidthStyleLocal('he')}">${r.he_bruto>0 ? _fmtMin(r.he_bruto):''}</td>`}
        ${!sh.hasDeudas ? '' : showDeudas ? `
        <td class="text-center align-middle tabular-nums sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;border-left:3px solid #64748b;left:${getStickyLeftLocal('deudas', 0)}px;${getStickyWidthStyleLocal('deudas')}">${r.esBolsa ? '—' : (L.deuda_bruta>0?_fmtMin(L.deuda_bruta):'')}</td>
        <td class="text-center align-middle tabular-nums text-muted sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;left:${getStickyLeftLocal('deudas', 1)}px;${getStickyWidthStyleLocal('deudas')}">${r.esBolsa ? '—' : (L.perdonado>0?_fmtMin(L.perdonado):'')}</td>
        <td class="text-center align-middle tabular-nums sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;color:#2563eb;left:${getStickyLeftLocal('deudas', 2)}px;${getStickyWidthStyleLocal('deudas')}">${r.esBolsa ? '—' : (L.cubierto>0?_fmtMin(L.cubierto):'')}</td>
        <td class="text-center align-middle tabular-nums ${L.pendiente>0?'matrix-cell-deuda-tot':''} sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;left:${getStickyLeftLocal('deudas', 3)}px;${getStickyWidthStyleLocal('deudas')}">${r.esBolsa ? '—' : (L.pendiente>0?_fmtMin(L.pendiente):'')}</td>` : `<td class="text-center align-middle tabular-nums ${L.pendiente>0?'matrix-cell-deuda-tot':''} sticky-premium-col" style="position:sticky; z-index:40; background:#f8fafc;font-size:0.8rem;border-left:3px solid #64748b;left:${getStickyLeftLocal('deudas')}px;${getStickyWidthStyleLocal('deudas')}">${r.esBolsa ? '—' : (L.pendiente>0 ? _fmtMin(L.pendiente):'')}</td>`}
        ${sh.hasSaldo ? `<td class="text-center align-middle tabular-nums fw-bold ${sClass} sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:40; background:#f9fafb;font-size:0.8rem;left:${getStickyLeftLocal('saldo')}px;${getStickyWidthStyleLocal('saldo')}">${r.esBolsa ? '—' : (isSaldoZero ? '00:00:00' : `${sPrefix}${_fmtMin(Math.abs(r.saldo))}`)}</td>` : ''}
        ${(hayBolsa) ? (
            showSaldoMeta
                ? (r.esBolsa
                    ? (() => {
                        // Textos SIEMPRE con comillas y concatenación: el minificador del
                        // servidor (rjsmin) come los espacios del texto de una plantilla
                        // `...` anidada dentro de ${} de otra plantilla (como este bloque).
                        let metaTooltip = r.emp._diasJustificadosBolsa > 0
                            ? 'Meta original: ' + _fmtMin(r.emp._metaOriginalBolsa) + ' | Descuento por ' + r.emp._diasJustificadosBolsa + ' día(s) justificado(s)'
                            : 'Meta mensual del ciclo (180h)';
                        const prb = r.emp._prorrateoBolsa;
                        const _fEs = iso => iso ? iso.split('-').reverse().join('-') : '';
                        let avisoLey = '';
                        if (prb && Number.isFinite(prb.factor) && prb.factor < 1) {
                            const motivo = [prb.fecha_ingreso ? 'ingreso el ' + _fEs(prb.fecha_ingreso) : '', prb.fecha_salida ? 'egreso el ' + _fEs(prb.fecha_salida) : ''].filter(Boolean).join(' y ');
                            metaTooltip = 'Meta ajustada por ' + motivo + ': proporcional a ' + prb.dias_disponibles + ' de ' + prb.dias_tramo + ' días del tramo. ' + metaTooltip;
                        }
                        if (prb && prb.aviso_21_dias) {
                            avisoLey = '<i class="bi bi-exclamation-triangle-fill" style="color:#d97706;margin-right:2px;" title="' +
                                'La ley (art. 25 bis del Código del Trabajo) exige repartir las 180 horas en al menos ' + prb.dias_minimos_ley +
                                ' días; este período solo le da ' + prb.dias_disponibles + ' días a esta persona. Es un aviso: no bloquea nada."></i>';
                        }

                        metaTooltip = metaTooltip + ' · Clic: horas por semana';
                        // Espera: es un TOPE legal (88 h), no una meta — se muestra «usadas X de Y»
                        // y el uso en porcentaje; ya no hay «balance −88:00». Textos con comillas
                        // y concatenación por el minificador.
                        const topeEsp = r.metaEsperaMin || 0;
                        const usoPct = topeEsp > 0 ? Math.round((r.acumEspera / topeEsp) * 100) : null;
                        const excesoEsp = Math.max(0, r.acumEspera - topeEsp);
                        let topeTooltip = 'Tope mensual de espera: ' + _fmtMin(topeEsp) + '. Es un máximo legal, no una meta: lo que pase del tope se paga como horas extra.';
                        if (prb && Number.isFinite(prb.factor) && prb.factor < 1) {
                            topeTooltip = topeTooltip + ' Tope ajustado por la vigencia parcial del contrato.';
                        }
                        const usoTooltip = usoPct === null ? 'Sin tope definido' :
                            (excesoEsp > 0 ? 'Superó el tope: ' + _fmtMin(excesoEsp) + ' se pagan como horas extra'
                                           : 'Espera usada: ' + _fmtMin(r.acumEspera) + ' de ' + _fmtMin(topeEsp));
                        const hoyD = new Date();
                        const hoyIso = hoyD.getFullYear() + '-' + String(hoyD.getMonth() + 1).padStart(2, '0') + '-' + String(hoyD.getDate()).padStart(2, '0');
                        const av = window.mxAvanceBolsa(r, stateMarcacionesApp.fechaInicioRRHH || dates[0], stateMarcacionesApp.fechaFinRRHH || dates[dates.length - 1], hoyIso);

                        return `<td class="align-middle sticky-premium-col" style="position:sticky; z-index:40; background:#faf5ff;border-left:3px solid #8b5cf6;cursor:pointer;left:${getStickyLeftLocal('bolsa', 0)}px;${getStickyWidthStyleLocal('bolsa')}" title="${metaTooltip}" onclick="window.mxSemanasBolsa(${emp.id})">${window.mxCeldaAvanceBolsa(av, avisoLey)}</td>
                                <td class="align-middle sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:40; background:#fffbeb;border-left:3px solid #d97706;left:${getStickyLeftLocal('espera', 0)}px;${getStickyWidthStyleLocal('espera')}" title="${topeTooltip + ' ' + usoTooltip}">${window.mxCeldaEspera(r)}</td>`;
                    })()
                    : `<td class="sticky-premium-col" style="position:sticky; z-index:40; background:#faf5ff;border-left:3px solid #8b5cf6;left:${getStickyLeftLocal('bolsa', 0)}px;${getStickyWidthStyleLocal('bolsa')}"></td>
                       <td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:40; background:#fffbeb;border-left:3px solid #d97706;left:${getStickyLeftLocal('espera', 0)}px;${getStickyWidthStyleLocal('espera')}"></td>`
                  )
                : `<td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:40; background:#faf5ff;border-left:3px solid #8b5cf6;left:${getStickyLeftLocal('bolsa')}px;${getStickyWidthStyleLocal('bolsa')}"></td>
                   <td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:40; background:#fffbeb;border-left:3px solid #d97706;left:${getStickyLeftLocal('espera')}px;${getStickyWidthStyleLocal('espera')}"></td>`
        ) : ''}
        ${dayCells}
    </tr>` + bandaRev;
};

window.recalculateTotalsRow = function(dates, feriadosArray, getFeriadoDesc) {
    const s = window.vistaAnaliticaState;
    const hasBonos = (stateMarcacionesApp.data.bonos_nombres || []).length > 0;
    const bonosNombres = stateMarcacionesApp.data.bonos_nombres || [];

    const employees = [];
    if (stateMarcacionesApp.data.empleados) {
        stateMarcacionesApp.data.empleados.forEach(e_raw => {
            const eid = e_raw.id;
            const mEmp = stateMarcacionesApp.data.matrix[eid];
            if (!mEmp) return;
            const info = mEmp.info || {};
            employees.push({
                id: eid, info,
                nombre_completo: info.nombre_completo || e_raw.nombre_completo || e_raw.nombre,
                area: info.area || e_raw.area || '',
                cargo: info.cargo || e_raw.cargo || '',
                turno: info.turno || info.nombre_turno || '',
                turno_dias: info.turno_dias || {},
                tipo_programacion: info.tipo_programacion || '',
                activo: info.activo !== false,
                dias: mEmp
            });
        });
    }

    const allRows = employees.map(emp => window.calcularStatsEmpleado(emp, dates, feriadosArray));
    const gf = window.getGridFlags(allRows);
    const rows = allRows.filter(r => !!r.esBolsa === gf.esBolsa);

    let visibleRows = rows;
    if (s.soloNegativo) visibleRows = visibleRows.filter(r => r.saldo < 0);
    if (s.soloConHE)    visibleRows = visibleRows.filter(r => r.he_bruto > 0);

    const tot = window.totalesConLibro(visibleRows);

    const totSClass = tot.saldo > 0 ? 'text-success' : tot.saldo < 0 ? 'text-danger' : 'matrix-saldo-zero';
    const totSPrefix = tot.saldo > 0 ? '+' : tot.saldo < 0 ? '-' : '';

    const sh = window.getGridShow(gf, hasBonos);
    const { showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta, hayBolsa } = sh;
    const _I = sh.nInc === 6 ? {per:0,atr:1,sad:2,ina:3,esp:4,tot:5} : {per:0,ina:1,esp:2,tot:3};
    const _heFull = sh.heFull;
    const stickyCols = window.buildStickyCols(sh, bonosNombres);

    const getStickyLeftLocal = (key, subIndex = 0) => window.getStickyLeft(key, subIndex, stickyCols, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);
    const getStickyWidthStyleLocal = (key) => window.getStickyWidthStyle(key, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);

    let bonosTotalsCell = '';
    if (hasBonos) {
        if (showBonos) {
            bonosTotalsCell = bonosNombres.map((bName, idx) => {
                const borderStyle = idx === 0 ? 'border-left:3px solid #10b981' : 'border-left:1px solid #e2e8f0';
                return `<td class="sticky-premium-col" style="position:sticky; z-index:60; ${borderStyle};left:${getStickyLeftLocal('bonos', idx)}px;${getStickyWidthStyleLocal('bonos')}"></td>`;
            }).join('');
        } else {
            bonosTotalsCell = `<td class="sticky-premium-col" style="position:sticky; z-index:60; border-left:3px solid #10b981;left:${getStickyLeftLocal('bonos')}px;${getStickyWidthStyleLocal('bonos')}"></td>`;
        }
    }

    const totalsRowHtml = `<tr class="fw-bold text-center" style="font-size:0.78rem; border-top: 2px solid #e2e8f0; background: #f8fafc;">
        <td class="sticky-col-analitica text-start ps-2" style="position:sticky; left:0; z-index:60; background: #f8fafc; color: #475569; font-weight: 800; width:260px; min-width:260px; max-width:260px;">TOTALES</td>
        ${bonosTotalsCell}
        ${!sh.hasInc ? '' : showIncidencias ? `
        <td class="sticky-premium-col" style="position:sticky; z-index:60; border-left:3px solid #f59e0b;left:${getStickyLeftLocal('incidencias', _I.per)}px;${getStickyWidthStyleLocal('incidencias')}">${tot.cnt_per||''}</td>
        ${_I.atr!==undefined?`<td class="sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('incidencias', _I.atr)}px;${getStickyWidthStyleLocal('incidencias')}">${tot.cnt_atr||''}</td>`:''}
        ${_I.sad!==undefined?`<td class="sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('incidencias', _I.sad)}px;${getStickyWidthStyleLocal('incidencias')}">${tot.cnt_sad||''}</td>`:''}
        <td class="sticky-premium-col ${tot.cnt_inas>0?'text-danger':''}" style="position:sticky; z-index:60; left:${getStickyLeftLocal('incidencias', _I.ina)}px;${getStickyWidthStyleLocal('incidencias')}">${tot.cnt_inas||''}</td>
        <td class="sticky-premium-col ${tot.cnt_esp>0?'text-info':''}" style="position:sticky; z-index:60; left:${getStickyLeftLocal('incidencias', _I.esp)}px;${getStickyWidthStyleLocal('incidencias')}">${tot.cnt_esp||''}</td>
        <td class="fw-bold sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('incidencias', _I.tot)}px;${getStickyWidthStyleLocal('incidencias')}">${((tot.cnt_per||0)+(tot.cnt_atr||0)+(tot.cnt_sad||0)+(tot.cnt_inas||0)+(tot.cnt_esp||0))||''}</td>` : `<td style="position:sticky; z-index:60; border-left:3px solid #f59e0b; color:#f59e0b;left:${getStickyLeftLocal('incidencias')}px;${getStickyWidthStyleLocal('incidencias')}" class="fw-bold sticky-premium-col">${((tot.cnt_per||0)+(tot.cnt_atr||0)+(tot.cnt_sad||0)+(tot.cnt_inas||0)+(tot.cnt_esp||0))>0 ? '<i class="bi bi-flag-fill me-1"></i>' + ((tot.cnt_per||0)+(tot.cnt_atr||0)+(tot.cnt_sad||0)+(tot.cnt_inas||0)+(tot.cnt_esp||0)) : ''}</td>`}
        ${showHE ? `
        ${_heFull?`<td style="position:sticky; z-index:60; border-left:3px solid #3b82f6;left:${getStickyLeftLocal('he', 0)}px;${getStickyWidthStyleLocal('he')}" class="tabular-nums sticky-premium-col">${tot.l_he_trabajadas>0?_fmtMin(tot.l_he_trabajadas):''}</td>`:''}
        ${_heFull?`<td class="tabular-nums sticky-premium-col" style="position:sticky; z-index:60; color:#2563eb;left:${getStickyLeftLocal('he', 1)}px;${getStickyWidthStyleLocal('he')}">${tot.l_he_usadas>0?_fmtMin(tot.l_he_usadas):''}</td>`:''}
        ${_heFull?`<td class="tabular-nums text-success sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('he', 2)}px;${getStickyWidthStyleLocal('he')}">${tot.l_he_a_pagar>0?_fmtMin(tot.l_he_a_pagar):''}</td>`:''}
        ${_heFull?`<td class="tabular-nums text-muted sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('he', 3)}px;${getStickyWidthStyleLocal('he')}">${tot.l_he_no_pagadas>0?_fmtMin(tot.l_he_no_pagadas):''}</td>`:''}
        <td class="tabular-nums ${_heFull ? 'text-warning' : ''} fw-bold sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('he', 4)}px;${getStickyWidthStyleLocal('he')}">${_heFull ? (tot.l_he_por_decidir>0?_fmtMin(tot.l_he_por_decidir):'') : (tot.he_bruto>0?_fmtMin(tot.he_bruto):'')}</td>` : `<td style="position:sticky; z-index:60; border-left:3px solid #3b82f6; color:#3b82f6;left:${getStickyLeftLocal('he')}px;${getStickyWidthStyleLocal('he')}" class="tabular-nums fw-bold sticky-premium-col">${tot.he_bruto>0 ? _fmtMin(tot.he_bruto):''}</td>`}
        ${!sh.hasDeudas ? '' : showDeudas ? `
        <td style="position:sticky; z-index:60; border-left:3px solid #64748b;left:${getStickyLeftLocal('deudas', 0)}px;${getStickyWidthStyleLocal('deudas')}" class="tabular-nums sticky-premium-col">${tot.l_deuda_bruta>0?_fmtMin(tot.l_deuda_bruta):''}</td>
        <td class="tabular-nums text-muted sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('deudas', 1)}px;${getStickyWidthStyleLocal('deudas')}">${tot.l_perdonado>0?_fmtMin(tot.l_perdonado):''}</td>
        <td class="tabular-nums sticky-premium-col" style="position:sticky; z-index:60; color:#2563eb;left:${getStickyLeftLocal('deudas', 2)}px;${getStickyWidthStyleLocal('deudas')}">${tot.l_cubierto>0?_fmtMin(tot.l_cubierto):''}</td>
        <td class="tabular-nums ${tot.l_pendiente>0?'matrix-cell-deuda-tot':''} sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('deudas', 3)}px;${getStickyWidthStyleLocal('deudas')}">${tot.l_pendiente>0?_fmtMin(tot.l_pendiente):''}</td>` : `<td style="position:sticky; z-index:60; border-left:3px solid #64748b;left:${getStickyLeftLocal('deudas')}px;${getStickyWidthStyleLocal('deudas')}" class="tabular-nums ${tot.l_pendiente>0?'matrix-cell-deuda-tot':''} sticky-premium-col">${tot.l_pendiente>0 ? _fmtMin(tot.l_pendiente):''}</td>`}
        ${sh.hasSaldo ? `<td class="tabular-nums ${totSClass} sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; left:${getStickyLeftLocal('saldo')}px;${getStickyWidthStyleLocal('saldo')}">${totSPrefix}${_fmtMin(Math.abs(tot.saldo))}</td>` : ''}
        ${(hayBolsa) ? (
            showSaldoMeta
                ? `<td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; background:#faf5ff;border-left:3px solid #8b5cf6;left:${getStickyLeftLocal('bolsa', 0)}px;${getStickyWidthStyleLocal('bolsa')};text-align:center;font-size: 0.75rem;color:#8b5cf6" title="Avance individual — no aplica totalizar"><i class="bi bi-dash"></i></td>
                   <td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; background:#fffbeb;border-left:3px solid #d97706;left:${getStickyLeftLocal('espera', 0)}px;${getStickyWidthStyleLocal('espera')};text-align:center;font-size: 0.75rem;color:#d97706" title="Uso individual — no aplica totalizar"><i class="bi bi-dash"></i></td>`
                : `<td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; background:#faf5ff;border-left:3px solid #8b5cf6;left:${getStickyLeftLocal('bolsa')}px;${getStickyWidthStyleLocal('bolsa')}"></td>
                   <td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; background:#fffbeb;border-left:3px solid #d97706;left:${getStickyLeftLocal('espera')}px;${getStickyWidthStyleLocal('espera')}"></td>`
        ) : ''}
        <td colspan="${dates.length}"></td>
    </tr>`;

    const tfoot = document.querySelector('.matrix-table-premium tfoot');
    if (tfoot) {
        tfoot.innerHTML = totalsRowHtml;
    }
};

window.reloadSingleEmployeeRow = async function(empId) {
    if (!stateMarcacionesApp.data || !stateMarcacionesApp.fechaInicioRRHH || !stateMarcacionesApp.fechaFinRRHH) {
        console.warn("reloadSingleEmployeeRow: stateMarcacionesApp.data or dates not ready, falling back to full reload");
        if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
        return;
    }

    const rowEl = document.getElementById("row-empleado-" + empId);
    if (!rowEl) {
        console.warn(`reloadSingleEmployeeRow: element row-empleado-${empId} not found, doing full client redraw`);
        const container = document.getElementById('marcaciones-view-container');
        if (container) renderVistaAnalitica(stateMarcacionesApp.data, container);
        return;
    }

    const nameCell = rowEl.querySelector('.emp-name-link');
    const originalNameHtml = nameCell ? nameCell.innerHTML : '';
    if (nameCell) {
        nameCell.innerHTML = `<span class="spinner-border spinner-border-sm text-primary me-1" role="status"></span>Actualizando...`;
    }

    try {
        let url = `/api/asistencia/matriz/?fecha_inicio=${stateMarcacionesApp.fechaInicioRRHH}&fecha_fin=${stateMarcacionesApp.fechaFinRRHH}&empleado_id=${empId}`;
        if (stateMarcacionesApp.area) url += `&area=${encodeURIComponent(stateMarcacionesApp.area)}`;
        if (stateMarcacionesApp.turnoId) url += `&turno_id=${stateMarcacionesApp.turnoId}`;

        const resp = await fetch(url);
        if (!resp.ok) throw new Error("Error loading single row data");

        const data = await resp.json();
        if (!data.matrix || !data.matrix[empId]) {
            throw new Error("No data returned for employee " + empId);
        }

        stateMarcacionesApp.data.matrix[empId] = data.matrix[empId];
        if (data.bonos_evaluacion && data.bonos_evaluacion[empId]) {
            stateMarcacionesApp.data.bonos_evaluacion[empId] = data.bonos_evaluacion[empId];
        }

        let dates = [];
        if (stateMarcacionesApp.data.periodo) {
            dates = window.getDatesInRange(stateMarcacionesApp.data.periodo.inicio, stateMarcacionesApp.data.periodo.fin);
        } else {
            const y = stateMarcacionesApp.year, m = stateMarcacionesApp.month;
            const daysInMonth = new Date(y, m, 0).getDate();
            for (let i = 1; i <= daysInMonth; i++)
                dates.push(`${y}-${String(m).padStart(2,'0')}-${String(i).padStart(2,'0')}`);
        }

        const feriadosArray = stateMarcacionesApp.data.feriados ? stateMarcacionesApp.data.feriados.map(f => f.fecha || f) : [];
        const getFeriadoDesc = (d) => {
            if (!stateMarcacionesApp.data.feriados) return null;
            const f = stateMarcacionesApp.data.feriados.find(x => (x.fecha || x) === d);
            return f ? (f.descripcion || 'Feriado') : null;
        };

        const empRaw = stateMarcacionesApp.data.empleados.find(e => String(e.id) === String(empId));
        if (!empRaw) {
            window.loadMarcacionesData();
            return;
        }

        const mEmp = data.matrix[empId];
        const info = mEmp.info || {};
        const empObject = {
            id: empId, info,
            nombre_completo: info.nombre_completo || empRaw.nombre_completo || empRaw.nombre,
            area: info.area || empRaw.area || '',
            cargo: info.cargo || empRaw.cargo || '',
            turno: info.turno || info.nombre_turno || '',
            turno_dias: info.turno_dias || {},
            tipo_programacion: info.tipo_programacion || '',
            activo: info.activo !== false,
            dias: mEmp
        };

        const r = window.calcularStatsEmpleado(empObject, dates, feriadosArray);

        const s = window.vistaAnaliticaState;
        let matchesFilter = true;
        if (s.soloNegativo && !(r.saldo < 0)) matchesFilter = false;
        if (s.soloConHE && !(r.he_bruto > 0)) matchesFilter = false;

        // La lista de días por revisar va en su propia fila: se quita la vieja y la nueva viene con la fila
        const bandaVieja = document.getElementById('rv-banda-' + empId);
        if (!matchesFilter) {
            rowEl.style.display = "none";
            if (bandaVieja) bandaVieja.style.display = 'none';
        } else {
            rowEl.style.display = "";
            if (bandaVieja) bandaVieja.remove();

            const hasBonos = (stateMarcacionesApp.data.bonos_nombres || []).length > 0;
            const bonosNombres = stateMarcacionesApp.data.bonos_nombres || [];
            const bonosEval = stateMarcacionesApp.data.bonos_evaluacion || {};
            const gf = window._gridFlags || { tipo: r.esBolsa ? 'bolsa' : 'ciclo', esBolsa: !!r.esBolsa };
            const sh = window.getGridShow(gf, hasBonos);
            const { showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta, hayBolsa } = sh;
            const stickyCols = window.buildStickyCols(sh, bonosNombres);

            const newRowHtml = window.renderEmployeeRowHtml(r, dates, feriadosArray, getFeriadoDesc, hasBonos, showBonos, bonosNombres, bonosEval, showIncidencias, showHE, showDeudas, hayBolsa, showSaldoMeta, s, stickyCols);
            rowEl.outerHTML = newRowHtml;
            const filaNueva = document.getElementById('row-empleado-' + empId);
            const tbNuevo = filaNueva ? filaNueva.closest('tbody') : null;
            if (tbNuevo && window.mxBandasAjustar) {
                window.mxBandasAjustar(tbNuevo);
                window.mxBandasCargarMarcas(tbNuevo);
                window.mxAvisarCorreccion(empId);
                window.mxActualizarAvisoBloque(tbNuevo);
            }
        }

        window.recalculateTotalsRow(dates, feriadosArray, getFeriadoDesc);
        

    } catch (err) {
        console.error("reloadSingleEmployeeRow failed:", err);
        if (nameCell) nameCell.innerHTML = originalNameHtml;
        if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
    }
};

// ── Horas por semana de un chofer en Bolsa: la meta (180 h) repartida en las 4 o 5 semanas del tramo (del 26 al 25) ──
// Clic en la celda «Meta» de la grilla. Cada semana trae 7 días desde el inicio del tramo; la última puede ser más corta (5.ª semana).
// Los textos van con comillas y concatenación: el minificador del servidor (rjsmin) come los espacios de las plantillas anidadas.
window.mxSemanasBolsa = function (empId) {
    const st = window.stateMarcacionesApp;
    const data = st && st.data;
    const empData = data && data.matrix && data.matrix[empId];
    if (!empData || !data.periodo) { showToast('No se encontraron los datos de esta persona.', 'error'); return; }
    const dates = window.getDatesInRange(data.periodo.inicio, data.periodo.fin);
    const feriadosArray = data.feriados ? data.feriados.map(f => f.fecha || f) : [];
    const empRaw = (data.empleados || []).find(e => String(e.id) === String(empId)) || {};
    const info = empData.info || empRaw;
    const nombre = info.nombre_completo || empRaw.nombre_completo || empRaw.nombre || '';
    // calcularStatsEmpleado deja en cada día el acumulado de la bolsa antes y después de él: la diferencia son las horas del día
    const r = window.calcularStatsEmpleado({
        id: empId, info, nombre_completo: nombre, area: info.area || empRaw.area || '', turno: info.turno || info.nombre_turno || '',
        turno_dias: info.turno_dias || {}, tipo_programacion: info.tipo_programacion || '', activo: info.activo !== false, dias: empData
    }, dates, feriadosArray);
    if (!r.esBolsa) { showToast('Esta persona no está en Bolsa Flexible.', 'info'); return; }

    const fmt = (min) => { const a = Math.round(Math.abs(min)); return String(Math.floor(a / 60)).padStart(2, '0') + ':' + String(a % 60).padStart(2, '0'); };
    const dm = (iso) => iso.slice(8, 10) + '/' + iso.slice(5, 7);
    const esc = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const semanas = [];
    for (let i = 0; i < dates.length; i += 7) semanas.push(dates.slice(i, i + 7));
    const filas = semanas.map((ds, k) => {
        const trab = ds.reduce((s, d) => { const di = empData[d] || {}; return s + Math.max(0, (di._acumuladoBolsaSnap || 0) - (di._acumuladoBolsaSnapPrev || 0)); }, 0);
        const meta = Math.round(r.metaMin * ds.length / dates.length);
        const pct = meta > 0 ? Math.round(trab / meta * 100) : 0;
        return { n: k + 1, desde: ds[0], hasta: ds[ds.length - 1], dias: ds.length, trab, meta, pct, dif: trab - meta };
    });
    const color = (p) => (p >= 100 ? '#059669' : p >= 75 ? '#d97706' : '#7c3aed');
    const tabla = filas.map(f => {
        const dif = (f.dif > 0 ? '+' : f.dif < 0 ? '−' : '') + fmt(f.dif);
        return '<tr>'
            + '<td class="text-start"><b>Semana ' + f.n + '</b><div class="text-muted" style="font-size:0.72rem;">' + dm(f.desde) + ' al ' + dm(f.hasta) + '</div></td>'
            + '<td class="text-end tabular-nums"><b>' + fmt(f.trab) + '</b></td>'
            + '<td class="text-end tabular-nums text-muted">' + fmt(f.meta) + '</td>'
            + '<td style="min-width:120px;"><div style="height:8px;background:#ede9fe;border-radius:6px;overflow:hidden;"><div class="mx-sem-barra" data-w="' + Math.min(100, f.pct) + '" style="height:100%;width:0;background:' + color(f.pct) + ';border-radius:6px;transition:width 600ms cubic-bezier(.22,1,.36,1);"></div></div>'
            + '<div class="text-end" style="font-size:0.72rem;color:' + color(f.pct) + ';font-weight:700;">' + f.pct + ' % · ' + dif + '</div></td>'
            + '</tr>';
    }).join('');
    const sm = r.saldoMeta || 0;
    const html = '<div class="text-start">'
        + '<table class="table table-sm align-middle mb-2" style="font-size:0.85rem;"><thead><tr class="text-muted" style="font-size:0.72rem;text-transform:uppercase;"><th>Semana</th><th class="text-end">Horas</th><th class="text-end">Meta</th><th>Avance</th></tr></thead><tbody>' + tabla + '</tbody></table>'
        + '<div class="d-flex justify-content-between align-items-center rounded-3 px-3 py-2" style="background:#faf5ff;border:1px solid #e9d5ff;">'
        + '<span><b>Tramo completo</b> <span class="text-muted">' + fmt(r.acumBolsa) + ' de ' + fmt(r.metaMin) + ' h</span></span>'
        + '<b style="color:' + (sm >= 0 ? '#059669' : '#dc2626') + ';">' + (sm > 0 ? '+' : sm < 0 ? '−' : '') + fmt(sm) + '</b></div></div>';
    Swal.fire({
        title: esc(window.nombreTitulo ? window.nombreTitulo(nombre) : nombre) || 'Horas por semana',
        html: html, width: 560, confirmButtonText: 'Cerrar', confirmButtonColor: '#7c3aed',
        didOpen: (el) => { requestAnimationFrame(() => setTimeout(() => el.querySelectorAll('.mx-sem-barra').forEach(b => { b.style.width = b.getAttribute('data-w') + '%'; }), 40)); }
    });
};

// Vista previa al pasar el mouse por las celdas de la grilla (el cuadro flotante #grid-fly-tooltip): en pantallas chicas tapa la
// grilla, así que se puede apagar con el botón de la barra. Se recuerda por navegador (localStorage); encendida por defecto.
window._gridTooltipEnabled = (() => { try { return localStorage.getItem('asistencia_grid_tooltip') !== '0'; } catch (_) { return true; } })();
// ── Estados como chips (opcional): botón "Estados" de la barra de la grilla ──
// Modos: 'linea' (sigla + línea de color, el de siempre) · 'rect' · 'circulo'. Se guarda por navegador.
window._ESTADOS_MODOS = ['linea', 'rect', 'circulo'];
window._estadosModo = function() {
    try {
        const m = localStorage.getItem('asistencia_estados_modo');
        if (window._ESTADOS_MODOS.includes(m)) return m;
        if (localStorage.getItem('asistencia_estados_circulo') === '1') return 'circulo'; // preferencia anterior
    } catch (_) {}
    return 'linea';
};
window._estadosChipBtnProps = function() {
    const m = window._estadosModo();
    const on = m !== 'linea';
    const nombre = { linea: 'sigla + línea', rect: 'rectángulos', circulo: 'círculos' }[m];
    const icono = { linea: 'bi-distribute-vertical', rect: 'bi-square-fill', circulo: 'bi-circle-fill' }[m];
    return {
        on, cls: on ? 'btn-primary' : 'btn-outline-secondary',
        html: `<i class="bi ${icono} me-1"></i> <span class="d-none d-sm-inline">Estados</span>`,
        title: `Estados: ${nombre}. Clic para cambiar (sigla + línea → rectángulos → círculos).`, nombre
    };
};
// El CSS no puede contar ni medir texto: aquí se marca cuántos estados hay por celda (td[data-cnt], máx. 4),
// el largo de cada sigla (badge[data-l]) y los que sobran (badge[data-hide], td[data-more]).
window._marcarEstadosChip = function() {
    document.querySelectorAll('.matrix-table-premium td.col-day').forEach(td => {
        const bs = td.querySelectorAll('.badge-status');
        const total = bs.length;
        const cnt = String(Math.min(4, total));
        if (td.dataset.cnt !== cnt) td.dataset.cnt = cnt;
        if (total > 4) { if (td.dataset.more !== '+' + (total - 4)) td.dataset.more = '+' + (total - 4); }
        else if (td.dataset.more) delete td.dataset.more;
        bs.forEach((b, i) => {
            const sp = b.querySelector(':scope > span');
            if (sp) {
                const n = String(Math.min(5, (sp.textContent || '').trim().length));
                if (b.dataset.l !== n) b.dataset.l = n;
            }
            if (i >= 4) { if (b.dataset.hide === undefined) b.dataset.hide = '1'; }
            else if (b.dataset.hide !== undefined) delete b.dataset.hide;
        });
    });
    document.querySelectorAll('.va-legend-bar .badge-status').forEach(b => {
        const sp = b.querySelector(':scope > span');
        if (!sp) return;
        const n = String(Math.min(5, (sp.textContent || '').trim().length));
        if (b.dataset.l !== n) b.dataset.l = n;
    });
};
window.aplicarEstadosChip = function() {
    const m = window._estadosModo();
    const cl = document.body.classList;
    cl.toggle('estados-chip', m !== 'linea');
    cl.toggle('estados-rect', m === 'rect');
    cl.toggle('estados-circulo', m === 'circulo');
    if (m !== 'linea') {
        window._marcarEstadosChip();
        if (!window._estadosChipObs) {
            let raf = 0;
            window._estadosChipObs = new MutationObserver(() => {
                if (raf) return;
                raf = requestAnimationFrame(() => { raf = 0; window._marcarEstadosChip(); });
            });
            window._estadosChipObs.observe(document.body, { childList: true, subtree: true });
        }
    } else if (window._estadosChipObs) {
        window._estadosChipObs.disconnect();
        window._estadosChipObs = null;
    }
};
window.toggleEstadosChip = function() {
    const sig = { linea: 'rect', rect: 'circulo', circulo: 'linea' }[window._estadosModo()];
    try { localStorage.setItem('asistencia_estados_modo', sig); } catch (_) {}
    window.aplicarEstadosChip();
    const btn = document.getElementById('btn-toggle-estados-circ');
    const b = window._estadosChipBtnProps();
    if (btn) {
        btn.className = `btn btn-sm ${b.cls} fw-bold`;
        btn.innerHTML = b.html;
        btn.title = b.title;
        btn.setAttribute('aria-pressed', String(b.on));
    }
    if (typeof showToast === 'function') showToast(`Estados: ${b.nombre}.`, 'info');
};
window.aplicarEstadosChip();

window._gridTipBtnProps = function() {
    const on = window._gridTooltipEnabled !== false;
    return on
        ? { on, cls: 'btn-primary', html: '<i class="bi bi-chat-square-text-fill me-1"></i> <span class="d-none d-sm-inline">Vista previa</span>', title: 'Vista previa al pasar el mouse: ACTIVADA. Clic para desactivarla (útil en pantallas chicas).' }
        : { on, cls: 'btn-outline-secondary', html: '<i class="bi bi-chat-square-dots me-1"></i> <span class="d-none d-sm-inline">Vista previa</span>', title: 'Vista previa al pasar el mouse: DESACTIVADA. Clic para activarla.' };
};
window.toggleGridTooltip = function() {
    window._gridTooltipEnabled = !(window._gridTooltipEnabled !== false);
    try { localStorage.setItem('asistencia_grid_tooltip', window._gridTooltipEnabled ? '1' : '0'); } catch (_) {}
    const tip = document.getElementById('grid-fly-tooltip');
    if (tip) { tip.classList.remove('tp-pinned'); tip.style.display = 'none'; }
    const btn = document.getElementById('btn-toggle-grid-tip');
    if (btn) {
        const b = window._gridTipBtnProps();
        btn.className = `btn btn-sm ${b.cls} fw-bold`;
        btn.innerHTML = b.html;
        btn.title = b.title;
        btn.setAttribute('aria-pressed', String(b.on));
    }
    if (typeof showToast === 'function') showToast(window._gridTooltipEnabled ? 'Vista previa encendida: al pasar sobre un día se ven sus marcas.' : 'Vista previa apagada.', 'info');
};

window.toggleStickyEmpleado = function() {
    window._stickyUnpinned = !window._stickyUnpinned;
    const table = document.querySelector('.matrix-table-premium');
    const btn = document.getElementById('btn-toggle-sticky-emp');
    if (table) {
        if (window._stickyUnpinned) {
            table.classList.add('unpin-sticky-columns');
        } else {
            table.classList.remove('unpin-sticky-columns');
        }
    }
    if (btn) {
        if (window._stickyUnpinned) {
            btn.className = 'btn btn-sm btn-primary fw-bold';
            btn.innerHTML = '<i class="bi bi-pin-fill me-1"></i> <span class="d-none d-sm-inline">Fijar Nombres</span>';
            btn.title = "Columnas liberadas para desplazamiento táctil libre. Clic para volver a fijar.";
        } else {
            btn.className = 'btn btn-sm btn-outline-secondary fw-bold';
            btn.innerHTML = '<i class="bi bi-pin-angle me-1"></i> <span class="d-none d-sm-inline">Desfijar Nombres</span>';
            btn.title = "Columnas fijadas. Clic para liberar y deslizar del día 1 al 31.";
        }
    }
    if (window.mxBandasAjustar) window.mxBandasAjustar();
};

// ─── PUNTO DE ENTRADA (llamado desde marcaciones_ui.js) ──────────────────────
function renderVistaAnalitica(respData, container) {
    if (!respData) return;
    const { matrix, feriados } = respData;
    const dayNames = ["Dom","Lun","Mar","Mié","Jue","Vie","Sáb"];
    const hasMatrix = matrix && typeof matrix === 'object';
    if (!hasMatrix) {
        container.innerHTML = '<div class="alert alert-info">No hay datos para mostrar.</div>';
        return;
    }
    window.__mxTipReg = new Map();   // datos de tooltips perezosos (se rearman en cada render)

    // ── 1. Organizar empleados (igual que renderTeamMatrix) ──────────────────
    const employees = [];
    if (respData.empleados) {
        respData.empleados.forEach(e_raw => {
            const eid = e_raw.id;
            const mEmp = matrix[eid];
            if (!mEmp) return;
            const info = mEmp.info || {};
            employees.push({
                id: eid, info,
                nombre_completo: info.nombre_completo || e_raw.nombre_completo || e_raw.nombre,
                area: info.area || e_raw.area || '',
                cargo: info.cargo || e_raw.cargo || '',
                turno: info.turno || info.nombre_turno || '',          // backend envía info.turno
                turno_dias: info.turno_dias || {},                     // necesario para proyección LIBRE y tooltip
                tipo_programacion: info.tipo_programacion || '',
                activo: info.activo !== false,
                dias: mEmp
            });
        });
    }

    // ── 2. Rango de fechas ───────────────────────────────────────────────────
    let dates = [];
    if (respData.periodo) {
        dates = window.getDatesInRange(respData.periodo.inicio, respData.periodo.fin);
    } else {
        const y = stateMarcacionesApp.year, m = stateMarcacionesApp.month;
        const daysInMonth = new Date(y, m, 0).getDate();
        for (let i = 1; i <= daysInMonth; i++)
            dates.push(`${y}-${String(m).padStart(2,'0')}-${String(i).padStart(2,'0')}`);
    }

    const feriadosArray = feriados ? feriados.map(f => f.fecha || f) : [];
    const getFeriadoDesc = (d) => {
        if (!feriados) return null;
        const f = feriados.find(x => (x.fecha || x) === d);
        return f ? (f.descripcion || 'Feriado') : null;
    };

    // ── 3. Calcular resumen por empleado ─────────────────────────────────────
    const allRows = employees.map(emp => window.calcularStatsEmpleado(emp, dates, feriadosArray));
    const gf = window.getGridFlags(allRows);                       // tipo activo + ¿hay pestañas?
    const rows = allRows.filter(r => !!r.esBolsa === gf.esBolsa);  // la grilla muestra un solo tipo a la vez

    // ── 4. Aplicar filtros UI ────────────────────────────────────────────────
    const s = window.vistaAnaliticaState;
    let visibleRows = rows;
    if (s.soloNegativo) visibleRows = visibleRows.filter(r => r.saldo < 0);
    if (s.soloConHE)    visibleRows = visibleRows.filter(r => r.he_bruto > 0);

    // ── 5. Totales ───────────────────────────────────────────────────────────
    const bonosNombres = respData.bonos_nombres || [];
    const bonosEval = respData.bonos_evaluacion || {};
    const hasBonos = bonosNombres.length > 0;
    const sh = window.getGridShow(gf, hasBonos);
    const { showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta, hayBolsa } = sh;
    const _I = sh.nInc === 6 ? {per:0,atr:1,sad:2,ina:3,esp:4,tot:5} : {per:0,ina:1,esp:2,tot:3};
    const _heFull = sh.heFull;
    const heCols = _heFull ? 5 : 1, heW = _heFull ? 325 : 130;
    const stickyCols = window.buildStickyCols(sh, bonosNombres);
    const getStickyLeft = (key, subIndex = 0) => window.getStickyLeft(key, subIndex, stickyCols, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);
    const getStickyWidthStyle = (key) => window.getStickyWidthStyle(key, showBonos, showIncidencias, showHE, showDeudas, showSaldoMeta);

    const tot = window.totalesConLibro(visibleRows);

    let bonosHeadersTop = '';
    let bonosHeadersSub = '';
    if (hasBonos) {
        if (showBonos) {
            const bonosTopWidth = bonosNombres.length * 65;
            bonosHeadersTop = `<th colspan="${bonosNombres.length}" class="text-start px-2 th-bento th-bento-success sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('bonos')}px; width:${bonosTopWidth}px; min-width:${bonosTopWidth}px; max-width:${bonosTopWidth}px;"><i class="bi bi-trophy-fill me-1" style="font-size:0.75rem;color:#10b981"></i><span class="fw-bold">Bonos</span> <button class="btn btn-sm btn-link text-muted p-0 ms-1" onclick="vaToggleBonos()" title="Contraer"><i class="bi bi-chevron-left"></i></button></th>`;
            bonosHeadersSub = bonosNombres.map((b, idx) => {
                const bShort = b.length > 5 ? b.substring(0,4) + '.' : b;
                return `<th class="text-center px-1 align-middle th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; width:65px; min-width:65px; max-width:65px; left:${getStickyLeft('bonos', idx)}px" title="${b}">${bShort}</th>`;
            }).join('');
        } else {
            bonosHeadersTop = `<th rowspan="2" class="align-middle text-center px-1 th-bento th-bento-success sticky-premium-col" style="position:sticky; z-index:120; width:76px; min-width:76px; max-width:76px; left:${getStickyLeft('bonos')}px"><button class="btn btn-sm btn-link text-muted p-0 mb-1" onclick="vaToggleBonos()" title="Expandir Bonos"><i class="bi bi-chevron-right"></i></button><br><i class="bi bi-trophy-fill d-block mb-1" style="font-size:0.85rem;color:#10b981"></i><span class="gc-lbl">Bonos</span></th>`;
        }
    }

    // ── 6. Cabeceras de días ─────────────────────────────────────────────────
    const monthNamesShort = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
    const dayHeaders = dates.map(d => {
        const dt = new Date(d+'T00:00:00');
        const isFer = feriadosArray.includes(d);
        const isWE  = (dt.getDay()===0||dt.getDay()===6);
        const bg = isFer ? 'background:#fff9c4' : isWE ? 'background:#f8f9fa' : '';
        const dateStrObj = dt.getDate().toString().padStart(2, '0') + '-' + monthNamesShort[dt.getMonth()];
        const dayShortName = dayNames[dt.getDay()].toUpperCase();
        // En modo Perdonazos: encabezado es clickeable para abrir panel lateral
        const perdonazoClick = `onclick="if(window._perdonazoState&&window._perdonazoState.activo){abrirPanelPerdonazoPorFecha('${d}')}"`;
        const perdonazoStyle = window._perdonazoState?.activo
            ? 'cursor:pointer;border-bottom:2px solid #10b981;'
            : '';
        // La línea del encabezado solo si todas las filas visibles tienen la misma fecha; si no, cada fila marca la suya
        const _cortes = gf.esBolsa ? window.getCortesLibreta(rows) : [];
        const _corte = _cortes.length === 1 ? _cortes[0] : null;
        const esCorte = !!_corte && d === _corte;
        const corteStyle = esCorte ? 'border-left:3px solid #8b5cf6;' : '';
        const titleHdr = esCorte ? 'Desde este día: libreta (antes: reloj biométrico)'
                       : (window._perdonazoState?.activo ? 'Clic para gestionar perdonazos del día' : '');
        const dhClase = isFer ? 'dh-fer' : dt.getDay() === 0 ? 'dh-dom' : isWE ? 'dh-sab' : '';
        return `<th class="col-day text-center p-1 ${dhClase}" style="min-width:48px;font-size: 0.75rem;white-space:nowrap;${perdonazoStyle}${corteStyle}" ${perdonazoClick}
                    title="${titleHdr || (isFer ? (getFeriadoDesc(d) || 'Feriado') : dateStrObj)}">
                    <div class="dh-wd">${dayShortName}</div>
                    <div class="dh-dn">${dt.getDate().toString().padStart(2, '0')}</div>
                    ${window._perdonazoState?.activo ? '<div style="font-size: 0.75rem;color:#10b981;font-weight:600;"><i class="bi bi-gift" aria-hidden="true"></i></div>' : ''}
                </th>`;
    }).join('');


    // ── 7. Filas de empleados ────────────────────────────────────────────────
    const filaHtml = new Map(visibleRows.map(r => [r, window.renderEmployeeRowHtml(r, dates, feriadosArray, getFeriadoDesc, hasBonos, showBonos, bonosNombres, bonosEval, showIncidencias, showHE, showDeudas, hayBolsa, showSaldoMeta, s, stickyCols)]));
    const bodyRows = visibleRows.map(r => filaHtml.get(r)).join('');
    const gruposHorario = window.mxGruposPorHorario(visibleRows);   // null: una sola lista, como siempre

    // Fila totales
    const totSClass = tot.saldo > 0 ? 'text-success' : tot.saldo < 0 ? 'text-danger' : 'matrix-saldo-zero';
    const totSPrefix = tot.saldo > 0 ? '+' : tot.saldo < 0 ? '-' : '';
    
    let bonosTotalsCell = '';
    if (hasBonos) {
        if (showBonos) {
            bonosTotalsCell = bonosNombres.map((bName, idx) => {
                const borderStyle = idx === 0 ? 'border-left:3px solid #10b981' : 'border-left:1px solid #e2e8f0';
                return `<td class="sticky-premium-col" style="position:sticky; z-index:60; ${borderStyle};left:${getStickyLeft('bonos', idx)}px;${getStickyWidthStyle('bonos')}"></td>`;
            }).join('');
        } else {
            bonosTotalsCell = `<td class="sticky-premium-col" style="position:sticky; z-index:60; border-left:3px solid #10b981;left:${getStickyLeft('bonos')}px;${getStickyWidthStyle('bonos')}"></td>`;
        }
    }

    const totalsRow = `<tr class="fw-bold text-center" style="font-size:0.78rem; border-top: 2px solid #e2e8f0; background: #f8fafc;">
        <td class="sticky-col-analitica text-start ps-2" style="position:sticky; left:0; z-index:60; background: #f8fafc; color: #475569; font-weight: 800; width:260px; min-width:260px; max-width:260px;">TOTALES</td>
        ${bonosTotalsCell}
        ${!sh.hasInc ? '' : showIncidencias ? `
        <td class="sticky-premium-col" style="position:sticky; z-index:60; border-left:3px solid #f59e0b;left:${getStickyLeft('incidencias', _I.per)}px;${getStickyWidthStyle('incidencias')}">${tot.cnt_per||''}</td>
        ${_I.atr!==undefined?`<td class="sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('incidencias', _I.atr)}px;${getStickyWidthStyle('incidencias')}">${tot.cnt_atr||''}</td>`:''}
        ${_I.sad!==undefined?`<td class="sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('incidencias', _I.sad)}px;${getStickyWidthStyle('incidencias')}">${tot.cnt_sad||''}</td>`:''}
        <td class="sticky-premium-col ${tot.cnt_inas>0?'text-danger':''}" style="position:sticky; z-index:60; left:${getStickyLeft('incidencias', _I.ina)}px;${getStickyWidthStyle('incidencias')}">${tot.cnt_inas||''}</td>
        <td class="sticky-premium-col ${tot.cnt_esp>0?'text-info':''}" style="position:sticky; z-index:60; left:${getStickyLeft('incidencias', _I.esp)}px;${getStickyWidthStyle('incidencias')}">${tot.cnt_esp||''}</td>
        <td class="fw-bold sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('incidencias', _I.tot)}px;${getStickyWidthStyle('incidencias')}">${((tot.cnt_per||0)+(tot.cnt_atr||0)+(tot.cnt_sad||0)+(tot.cnt_inas||0)+(tot.cnt_esp||0))||''}</td>` : `<td style="position:sticky; z-index:60; border-left:3px solid #f59e0b; color:#f59e0b;left:${getStickyLeft('incidencias')}px;${getStickyWidthStyle('incidencias')}" class="fw-bold sticky-premium-col">${((tot.cnt_per||0)+(tot.cnt_atr||0)+(tot.cnt_sad||0)+(tot.cnt_inas||0)+(tot.cnt_esp||0))>0 ? '<i class="bi bi-flag-fill me-1"></i>' + ((tot.cnt_per||0)+(tot.cnt_atr||0)+(tot.cnt_sad||0)+(tot.cnt_inas||0)+(tot.cnt_esp||0)) : ''}</td>`}
        ${showHE ? `
        ${_heFull?`<td style="position:sticky; z-index:60; border-left:3px solid #3b82f6;left:${getStickyLeft('he', 0)}px;${getStickyWidthStyle('he')}" class="tabular-nums sticky-premium-col">${tot.l_he_trabajadas>0?_fmtMin(tot.l_he_trabajadas):''}</td>`:''}
        ${_heFull?`<td class="tabular-nums sticky-premium-col" style="position:sticky; z-index:60; color:#2563eb;left:${getStickyLeft('he', 1)}px;${getStickyWidthStyle('he')}">${tot.l_he_usadas>0?_fmtMin(tot.l_he_usadas):''}</td>`:''}
        ${_heFull?`<td class="tabular-nums text-success sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('he', 2)}px;${getStickyWidthStyle('he')}">${tot.l_he_a_pagar>0?_fmtMin(tot.l_he_a_pagar):''}</td>`:''}
        ${_heFull?`<td class="tabular-nums text-muted sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('he', 3)}px;${getStickyWidthStyle('he')}">${tot.l_he_no_pagadas>0?_fmtMin(tot.l_he_no_pagadas):''}</td>`:''}
        <td class="tabular-nums ${_heFull ? 'text-warning' : ''} fw-bold sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('he', 4)}px;${getStickyWidthStyle('he')}">${_heFull ? (tot.l_he_por_decidir>0?_fmtMin(tot.l_he_por_decidir):'') : (tot.he_bruto>0?_fmtMin(tot.he_bruto):'')}</td>` : `<td style="position:sticky; z-index:60; border-left:3px solid #3b82f6; color:#3b82f6;left:${getStickyLeft('he')}px;${getStickyWidthStyle('he')}" class="tabular-nums fw-bold sticky-premium-col">${tot.he_bruto>0 ? _fmtMin(tot.he_bruto):''}</td>`}
        ${!sh.hasDeudas ? '' : showDeudas ? `
        <td style="position:sticky; z-index:60; border-left:3px solid #64748b;left:${getStickyLeft('deudas', 0)}px;${getStickyWidthStyle('deudas')}" class="tabular-nums sticky-premium-col">${tot.l_deuda_bruta>0?_fmtMin(tot.l_deuda_bruta):''}</td>
        <td class="tabular-nums text-muted sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('deudas', 1)}px;${getStickyWidthStyle('deudas')}">${tot.l_perdonado>0?_fmtMin(tot.l_perdonado):''}</td>
        <td class="tabular-nums sticky-premium-col" style="position:sticky; z-index:60; color:#2563eb;left:${getStickyLeft('deudas', 2)}px;${getStickyWidthStyle('deudas')}">${tot.l_cubierto>0?_fmtMin(tot.l_cubierto):''}</td>
        <td class="tabular-nums ${tot.l_pendiente>0?'matrix-cell-deuda-tot':''} sticky-premium-col" style="position:sticky; z-index:60; left:${getStickyLeft('deudas', 3)}px;${getStickyWidthStyle('deudas')}">${tot.l_pendiente>0?_fmtMin(tot.l_pendiente):''}</td>` : `<td style="position:sticky; z-index:60; border-left:3px solid #64748b;left:${getStickyLeft('deudas')}px;${getStickyWidthStyle('deudas')}" class="tabular-nums ${tot.l_pendiente>0?'matrix-cell-deuda-tot':''} sticky-premium-col">${tot.l_pendiente>0 ? _fmtMin(tot.l_pendiente):''}</td>`}
        ${sh.hasSaldo ? `<td class="tabular-nums ${totSClass} sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; left:${getStickyLeft('saldo')}px;${getStickyWidthStyle('saldo')}">${totSPrefix}${_fmtMin(Math.abs(tot.saldo))}</td>` : ''}
        ${(hayBolsa) ? (
            showSaldoMeta
                ? `<td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; background:#faf5ff;border-left:3px solid #8b5cf6;left:${getStickyLeft('bolsa', 0)}px;${getStickyWidthStyle('bolsa')};text-align:center;font-size: 0.75rem;color:#8b5cf6" title="Avance individual — no aplica totalizar"><i class="bi bi-dash"></i></td>
                   <td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; background:#fffbeb;border-left:3px solid #d97706;left:${getStickyLeft('espera', 0)}px;${getStickyWidthStyle('espera')};text-align:center;font-size: 0.75rem;color:#d97706" title="Uso individual — no aplica totalizar"><i class="bi bi-dash"></i></td>`
                : `<td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; background:#faf5ff;border-left:3px solid #8b5cf6;left:${getStickyLeft('bolsa')}px;${getStickyWidthStyle('bolsa')}"></td>
                   <td class="sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:60; background:#fffbeb;border-left:3px solid #d97706;left:${getStickyLeft('espera')}px;${getStickyWidthStyle('espera')}"></td>`
        ) : ''}
        <td colspan="${dates.length}"></td>
    </tr>`;

    // ── 8. Switches ──────────────────────────────────────────────────────────
    const isClosed = respData.periodo && respData.periodo.cerrado;
    const closedBadge = isClosed ? `<span class="badge bg-danger ms-2" title="El periodo está cerrado y protegido contra modificaciones"><i class="bi bi-lock-fill"></i> CERRADO</span>` : '';

    const activeVM = stateMarcacionesApp.viewMode || 'conceptos';
    const vmButtons = [
        {key:'conceptos', icon:'bi-grid-3x3-gap',     label:'Conceptos'},
        {key:'horas',     icon:'bi-clock',            label:'Horas'},
        {key:'colacion',  icon:'bi-cup-hot',          label:'Colación'},
        {key:'permisos',  icon:'bi-person-dash',      label:'Permisos'},
        {key:'he',        icon:'bi-arrow-up-circle',  label:'Horas Extras'},
        {key:'acumulado', icon:'bi-graph-up',         label:'Acumulado'},
        {key:'velocidad', icon:'bi-speedometer2',     label:'Velocidad'}
    ].map(v => `<button class="btn segmented-btn ${activeVM===v.key ? 'active' : ''}" onclick="vaSetViewMode('${v.key}')" title="${v.label}"><i class="bi ${v.icon} me-1 d-none d-sm-inline"></i>${v.label}</button>`).join('');

    const isUnpinned = window._stickyUnpinned === true;
    const pinBtnText = isUnpinned ? 'Fijar' : 'Desfijar';
    const pinBtnIcon = isUnpinned ? 'bi-pin-fill' : 'bi-pin-angle';
    const pinBtnClass = isUnpinned ? 'btn-primary' : 'btn-outline-secondary';

    const tipBtn = window._gridTipBtnProps();
    const circBtn = window._estadosChipBtnProps();
    const sw = `<div class="va-toolbar-premium">
        <div class="d-flex align-items-center gap-2">
            <i class="bi bi-grid-3x3-gap-fill" style="font-size:1.1rem;color:#3f6fd6"></i>
            <span class="fw-bold" style="font-size:0.88rem;color:#1e293b">Vista Analítica</span>
            ${closedBadge}
        </div>
        <div style="width:1px;height:24px;background:#cbd5e1"></div>
        <div class="segmented-control" role="group" aria-label="Modo de vista">${vmButtons}</div>
        <div class="ms-auto d-flex align-items-center gap-2">
            <button id="btn-toggle-estados-circ" class="btn btn-sm ${circBtn.cls} fw-bold" onclick="window.toggleEstadosChip()" title="${circBtn.title}" aria-pressed="${circBtn.on}">${circBtn.html}</button>
            <button id="btn-toggle-grid-tip" class="btn btn-sm ${tipBtn.cls} fw-bold" onclick="window.toggleGridTooltip()" title="${tipBtn.title}" aria-pressed="${tipBtn.on}">${tipBtn.html}</button>
            <button id="btn-toggle-leyenda" class="btn btn-sm btn-outline-secondary fw-bold" onclick="window.toggleVaLeyenda()" aria-pressed="false" title="Mostrar u ocultar la leyenda de colores y atajos"><i class="bi bi-info-circle me-1"></i><span class="va-foco-txt">Leyenda</span></button>
            <button id="btn-toggle-foco" class="btn btn-sm btn-outline-secondary fw-bold" onclick="window.toggleVaFoco()" aria-pressed="false" title="Ampliar la tabla: compacta la barra y oculta la leyenda para ver más filas y días"><i class="bi bi-arrows-fullscreen me-1"></i><span class="va-foco-txt">Ampliar tabla</span></button>
            <button id="btn-toggle-sticky-emp" class="btn btn-sm ${pinBtnClass} fw-bold" onclick="window.toggleStickyEmpleado()" title="Fijar o liberar nombres y columnas de resumen para deslizamiento libre en pantallas táctiles">
                <i class="bi ${pinBtnIcon} me-1"></i> <span class="d-none d-sm-inline">${pinBtnText} Nombres</span>
            </button>
            <div class="btn-group shadow-sm" style="border-radius:8px;overflow:hidden">
                <button class="btn btn-sm ${isClosed ? 'btn-secondary disabled' : 'btn-primary'} fw-bold" ${isClosed ? 'disabled' : ''} onclick="openCierrePeriodoModal()" title="${isClosed ? 'El periodo ya está cerrado' : 'Cerrar este periodo definitivamente'}">
                    <i class="bi bi-shield-lock-fill me-1"></i> <span class="d-none d-md-inline">Cerrar Periodo</span>
                </button>
                <button class="btn btn-sm btn-outline-secondary bg-white" onclick="openHistorialCierresModal()" title="Ver historial de cierres">
                    <i class="bi bi-clock-history"></i>
                </button>
            </div>
            <div class="va-stats-chip">
                <i class="bi bi-people-fill"></i>
                <strong>${visibleRows.length}</strong>${(gf.tabs || visibleRows.length !== allRows.length) ? ' de ' + allRows.length : ''} emp · <strong>${dates.length}</strong> días
            </div>
        </div>
    </div>`;

    // ── 9. HTML final ────────────────────────────────────────────────────────
    // (hayBolsa y showSaldoMeta ya están definidos arriba, antes de bodyRows)

    const incHeadersTop = !sh.hasInc ? '' : showIncidencias 
        ? `<th colspan="${sh.nInc}" class="text-start px-2 th-bento th-bento-warning sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias')}px; width:${sh.nInc*65}px; min-width:${sh.nInc*65}px; max-width:${sh.nInc*65}px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><i class="bi bi-flag-fill me-1" style="font-size:0.75rem;color:#f59e0b"></i><span class="fw-bold">Incidencias</span> <button class="btn btn-sm btn-link text-muted p-0 ms-1" onclick="vaToggleCol('showIncidencias')" title="Contraer"><i class="bi bi-chevron-left"></i></button></th>` 
        : `<th rowspan="2" class="align-middle px-1 text-center th-bento th-bento-warning sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias')}px; width:76px; min-width:76px; max-width:76px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><button class="btn btn-sm btn-link text-muted p-0 mb-1" onclick="vaToggleCol('showIncidencias')" title="Expandir Incidencias"><i class="bi bi-chevron-right"></i></button><br><i class="bi bi-flag-fill d-block mb-1" style="font-size:0.85rem;color:#f59e0b"></i><span class="gc-lbl">Incidencias</span></th>`;
    
    const heHeadersTop = showHE 
        ? `<th colspan="${heCols}" class="text-start px-2 th-bento th-bento-primary sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('he')}px; width:${heW}px; min-width:${heW}px; max-width:${heW}px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><i class="bi bi-lightning-charge-fill me-1" style="font-size:0.75rem;color:#3b82f6"></i><span class="fw-bold">Horas Extra</span> <button class="btn btn-sm btn-link text-muted p-0 ms-1" onclick="vaToggleCol('showHE')" title="Contraer"><i class="bi bi-chevron-left"></i></button></th>` 
        : `<th rowspan="2" class="align-middle px-1 text-center th-bento th-bento-primary sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('he')}px; width:76px; min-width:76px; max-width:76px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><button class="btn btn-sm btn-link text-muted p-0 mb-1" onclick="vaToggleCol('showHE')" title="Expandir HE"><i class="bi bi-chevron-right"></i></button><br><i class="bi bi-lightning-charge-fill d-block mb-1" style="font-size:0.85rem;color:#3b82f6"></i><span class="gc-lbl">Horas<br>extra</span></th>`;
    
    const deudasHeadersTop = !sh.hasDeudas ? '' : showDeudas 
        ? `<th colspan="4" class="text-start px-2 th-bento th-bento-secondary sticky-premium-col" style="position:sticky; z-index:120; border-left:3px solid #64748b;left:${getStickyLeft('deudas')}px; width:260px; min-width:260px; max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><i class="bi bi-clock-history me-1" style="font-size:0.75rem;color:#64748b"></i><span class="fw-bold">Tiempo No Trabajado</span> <button class="btn btn-sm btn-link text-muted p-0 ms-1" onclick="vaToggleCol('showDeudas')" title="Contraer"><i class="bi bi-chevron-left"></i></button></th>` 
        : `<th rowspan="2" class="align-middle px-1 text-center th-bento th-bento-secondary sticky-premium-col" style="position:sticky; z-index:120; border-left:3px solid #64748b;left:${getStickyLeft('deudas')}px; width:76px; min-width:76px; max-width:76px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><button class="btn btn-sm btn-link text-muted p-0 mb-1" onclick="vaToggleCol('showDeudas')" title="Expandir Tiempos"><i class="bi bi-chevron-right"></i></button><br><i class="bi bi-clock-history d-block mb-1" style="font-size:0.85rem;color:#64748b"></i><span class="gc-lbl">Tiempo no<br>trabajado</span></th>`;

    // Columna SALDO META (180h) — solo visible si hay bolsa flexible en el área
    const saldoMetaHeaderTop = hayBolsa
        ? (showSaldoMeta
            ? `<th colspan="1" class="text-start px-2 sticky-premium-col" style="position:sticky; z-index:120; background:#faf5ff;border-left:3px solid #8b5cf6;font-size: 0.75rem;left:${getStickyLeft('bolsa')}px; width:252px; min-width:252px; max-width:252px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><i class="bi bi-bullseye me-1" style="color:#8b5cf6"></i><span class="fw-bold" style="color:#7c3aed">Bolsa (180h)</span> <button class="btn btn-sm btn-link p-0 ms-1" onclick="vaToggleCol('showSaldoMeta')" title="Contraer" style="color:#8b5cf6"><i class="bi bi-chevron-left"></i></button></th>`
            : `<th rowspan="2" class="align-middle px-1 text-center sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:120; background:#faf5ff;border-left:3px solid #8b5cf6;left:${getStickyLeft('bolsa')}px; width:76px; min-width:76px; max-width:76px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><button class="btn btn-sm btn-link p-0 mb-1" onclick="vaToggleCol('showSaldoMeta')" title="Expandir Bolsa Flexible" style="color:#8b5cf6"><i class="bi bi-chevron-right"></i></button><br><i class="bi bi-bullseye d-block mb-1" style="font-size:0.85rem;color:#8b5cf6"></i><span class="gc-lbl" style="color:#7c3aed">Bolsa<br>180h</span></th>`)
        : '';
    const saldoMetaHeadersSub = (hayBolsa && showSaldoMeta) ? `
            <th class="text-center px-1 sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:120; background:#faf5ff;border-left:3px solid #8b5cf6;font-size: 0.75rem;color:#7c3aed;left:${getStickyLeft('bolsa', 0)}px;${getStickyWidthStyle('bolsa')}" title="Horas hechas de la meta del ciclo; la raya marca lo esperado a hoy. Clic en una persona: horas por semana">AVANCE DEL CICLO</th>` : '';

    // Columna ESPERA (88h) — grupo gemelo paralelo
    const esperaHeaderTop = hayBolsa
        ? (showSaldoMeta
            ? `<th colspan="1" class="text-start px-2 sticky-premium-col" style="position:sticky; z-index:120; background:#fffbeb;border-left:3px solid #d97706;font-size: 0.75rem;left:${getStickyLeft('espera')}px; width:252px; min-width:252px; max-width:252px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><i class="bi bi-hourglass-split me-1" style="color:#d97706"></i><span class="fw-bold" style="color:#b45309">Espera (tope 88h)</span></th>`
            : `<th rowspan="2" class="align-middle px-1 text-center sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:120; background:#fffbeb;border-left:3px solid #d97706;left:${getStickyLeft('espera')}px; width:76px; min-width:76px; max-width:76px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="Tiempos de Espera (88h)"><button class="btn btn-sm btn-link p-0 mb-1" onclick="vaToggleCol('showSaldoMeta')" title="Expandir Espera (88h)" style="color:#d97706"><i class="bi bi-chevron-right"></i></button><br><i class="bi bi-hourglass-split d-block mb-1" style="font-size:0.85rem;color:#d97706"></i><span class="gc-lbl" style="color:#b45309">Espera<br>88h</span></th>`)
        : '';
    const esperaHeadersSub = (hayBolsa && showSaldoMeta) ? `
            <th class="text-center px-1 sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:120; background:#fffbeb;border-left:3px solid #d97706;font-size: 0.75rem;color:#b45309;left:${getStickyLeft('espera', 0)}px;${getStickyWidthStyle('espera')}" title="Horas de espera usadas del tope mensual (máximo legal, no es una meta); sobre el tope se pagan como horas extra">USO DEL TOPE</th>` : '';

    const incHeadersSub = (sh.hasInc && showIncidencias) ? `
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias', _I.per)}px;${getStickyWidthStyle('incidencias')}" title="Días con permiso">PER</th>
            ${_I.atr!==undefined?`<th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias', _I.atr)}px;${getStickyWidthStyle('incidencias')}" title="Días con atraso">ATR</th>`:''}
            ${_I.sad!==undefined?`<th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias', _I.sad)}px;${getStickyWidthStyle('incidencias')}" title="Días con salida adelantada">S.ADL</th>`:''}
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias', _I.ina)}px;${getStickyWidthStyle('incidencias')}" title="Inasistencias">INA</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias', _I.esp)}px;${getStickyWidthStyle('incidencias')}" title="Jornadas especiales">J.ESP</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('incidencias', _I.tot)}px;${getStickyWidthStyle('incidencias')}" title="Total incidencias">TOT</th>` : '';
    // Libro mayor de minutos (decisión del dueño, 25-10-2026): cada minuto de hora extra termina usado, a pagar,
    // no pagado o por decidir; cada minuto de deuda termina perdonado, cubierto o pendiente. Rojo solo si queda pendiente.
    const heHeadersSub = showHE ? `
            ${_heFull?`<th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('he', 0)}px;${getStickyWidthStyle('he')}" title="Horas extra trabajadas en el tramo">TRAB.</th>`:''}
            ${_heFull?`<th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('he', 1)}px;${getStickyWidthStyle('he')}" title="Horas extra usadas para cubrir deuda o una inasistencia">USADAS</th>`:''}
            ${_heFull?`<th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('he', 2)}px;${getStickyWidthStyle('he')}" title="Horas extra aprobadas que se pagan">A PAGAR</th>`:''}
            ${_heFull?`<th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('he', 3)}px;${getStickyWidthStyle('he')}" title="Horas extra que se decidió no pagar">NO PAG.</th>`:''}
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('he', 4)}px;${getStickyWidthStyle('he')}" title="${_heFull ? 'Horas extra sin decisión todavía' : 'Horas sobre la meta de 180 h: se aprueban automáticamente'}">${_heFull ? 'POR DEC.' : 'APROB.'}</th>` : '';
    const deudasHeadersSub = (sh.hasDeudas && showDeudas) ? `
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('deudas', 0)}px;${getStickyWidthStyle('deudas')}" title="Tiempo que dejó de trabajar (atrasos, salidas adelantadas, permisos, exceso de colación)">DEUDA</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('deudas', 1)}px;${getStickyWidthStyle('deudas')}" title="Deuda perdonada (perdonazos y cuadre a cero)">PERDON.</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('deudas', 2)}px;${getStickyWidthStyle('deudas')}" title="Deuda cubierta con horas extra">CUBIERTO</th>
            <th class="text-center px-1 th-bento-sub sticky-premium-col" style="position:sticky; z-index:120; left:${getStickyLeft('deudas', 3)}px;${getStickyWidthStyle('deudas')};color:#dc2626;font-weight:700" title="Deuda que sigue pendiente">PEND.</th>` : '';

    const tabsHtml = `<div class="gc-tabs" role="tablist" aria-label="Tipo de horario">
        <button type="button" class="gc-tab${gf.nC === 0 ? ' gc-vacia' : ''}" role="tab" data-tipo="ciclo" aria-selected="${!gf.esBolsa}" onclick="vaSetTab('ciclo')">Ciclo inteligente<span class="gc-n">${gf.nC}</span></button>
        <button type="button" class="gc-tab${gf.nB === 0 ? ' gc-vacia' : ''}" role="tab" data-tipo="bolsa" aria-selected="${gf.esBolsa}" onclick="vaSetTab('bolsa')">Bolsa flexible<span class="gc-n">${gf.nB}</span></button>
    </div>`;

    // Pestaña sin información con los filtros actuales: se mantiene la pestaña y se avisa dentro de ella.
    let vaciaHtml = '';
    if (visibleRows.length === 0) {
        const nomTipo = gf.esBolsa ? 'Bolsa flexible' : 'Ciclo inteligente';
        const nOtro = gf.esBolsa ? gf.nC : gf.nB;
        const nomOtro = gf.esBolsa ? 'Ciclo inteligente' : 'Bolsa flexible';
        const porToggle = rows.length > 0;   // hay empleados del tipo, pero los oculta "Solo saldo negativo" / "Solo con HE"
        const msg = porToggle
            ? `Ningún empleado de «${nomTipo}» cumple los filtros «solo saldo negativo» / «solo con HE».`
            : `No existe información en «${nomTipo}» con los filtros actuales.`;
        const salto = nOtro > 0
            ? `<button type="button" class="btn btn-sm btn-outline-primary mt-3" onclick="vaSetTab('${gf.esBolsa ? 'ciclo' : 'bolsa'}')">Ver ${nomOtro} (${nOtro})</button>`
            : (allRows.length === 0 ? `<div class="text-muted mt-2" style="font-size:.8rem">Los filtros (área, búsqueda, estado, período) no devuelven empleados.</div>` : '');
        vaciaHtml = `<div class="gc-vacio" role="status"><i class="bi bi-inbox"></i><div class="gc-vacio-t">${msg}</div>${salto}</div>`;
    }

    // Las dos filas del encabezado: arriba en la tabla y, en la grilla por horario, otra vez en cada bloque
    const cabeceraFilas = `<tr class="text-center" style="background:#f8f9fa;font-size: 0.75rem">
            <th rowspan="2" class="sticky-col-analitica align-middle text-start ps-2" style="position:sticky; left:0; z-index:120; white-space:nowrap; background:#f8f9fa; width:260px; min-width:260px; max-width:260px;">Empleado</th>
            ${bonosHeadersTop}
            ${incHeadersTop}
            ${heHeadersTop}
            ${deudasHeadersTop}
            ${sh.hasSaldo ? `<th rowspan="2" class="align-middle text-start px-2 sticky-premium-col sticky-saldo-col" style="position:sticky; z-index:120; background:#f0fdf4;left:${getStickyLeft('saldo')}px;${getStickyWidthStyle('saldo')}">Saldo<br>Neto</th>` : ''}
            ${saldoMetaHeaderTop}
            ${esperaHeaderTop}
            ${(() => {
                // Los meses sobre los días (en vez de «Días del período»): una celda por mes con su cantidad de días
                const meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
                const grupos = [];
                dates.forEach(d => { const k = d.slice(0, 7); const g = grupos[grupos.length - 1]; if (g && g.k === k) g.n++; else grupos.push({ k, n: 1, t: meses[Number(d.slice(5, 7)) - 1] + ' ' + d.slice(0, 4) }); });
                return grupos.map(g => `<th colspan="${g.n}" class="text-start px-2 dh-mes">${g.t}</th>`).join('');
            })()}
        </tr>
        <tr class="text-center" style="background:#f8f9fa;font-size: 0.75rem">
            ${bonosHeadersSub}
            ${incHeadersSub}
            ${heHeadersSub}
            ${deudasHeadersSub}
            ${saldoMetaHeadersSub}
            ${esperaHeadersSub}
            ${dayHeaders}
        </tr>`;

    container.innerHTML = `
    ${tabsHtml}
    ${sw}
    ${vaciaHtml ? '' : `<div class="va-legend-bar d-flex gap-3 flex-wrap align-items-center" style="font-size: 0.75rem;color:#6b7280">
        ${activeVM === 'velocidad' && window.mxVelLeyenda ? window.mxVelLeyenda() : _leyendaEstadosHtml()}
        ${(() => {
            const cs = gf.esBolsa ? window.getCortesLibreta(rows).filter(c => dates.includes(c)) : [];
            if (!cs.length) return '';
            const fechas = cs.map(c => c.split('-').reverse().join('-')).join(', ');
            return '<span class="text-muted" style="font-size:.75rem"><i class="bi bi-layout-sidebar-inset" style="color:#8b5cf6"></i> '
                + 'Línea violeta: desde ' + fechas + ' se usa libreta (fecha del horario de cada persona); antes, reloj biométrico</span>';
        })()}
        <span class="ms-auto text-muted" style="font-size: 0.75rem"><i class="bi bi-info-circle me-1"></i><span class="tp-kb">Click: Acciones · DblClick celda: Justificar · DblClick nombre: Gestionar HE</span><span class="tp-touch">Toque: acciones · Mantén pulsado: detalle del día · Doble toque: justificar</span></span>
    </div>`}
    ${vaciaHtml || `<div class="va-tablewrap" style="overflow-x:auto;border-radius:0 0 8px 8px;border:1px solid #dee2e6;border-top:none">
    <table class="table table-bordered table-sm mb-0 matrix-table matrix-table-premium ${window._stickyUnpinned ? 'unpin-sticky-columns' : ''} ${sh.hayBolsa ? 'gc-bolsa' : ''}" style="font-size:0.8rem;border-collapse:separate;border-spacing:0">
    <thead style="position:sticky;top:0;z-index:100;box-shadow:0 4px 12px rgba(0,0,0,.05)">
        ${cabeceraFilas}
    </thead>
    ${gruposHorario ? gruposHorario.map((g, i) => window.mxBloqueHorario(g, i, r => filaHtml.get(r), cabeceraFilas)).join('') : `<tbody id="matrix-tbody">${bodyRows}</tbody>`}
    <tfoot>${totalsRow}</tfoot>
    </table>
    </div>`}
`;

    window._gridApplyPinCap();
    window._vaAplicarFoco();

    // Grilla por horario: el título de cada bloque ocupa todo el ancho de la tabla
    const _tablaGh = container.querySelector('.matrix-table-premium');
    if (_tablaGh && _tablaGh.querySelector('.gh-titulo')) {
        const ref = _tablaGh.querySelector('tr[id^="row-empleado-"]');
        const nCol = ref ? [...ref.children].reduce((a, td) => a + (td.colSpan || 1), 0) : 1;
        _tablaGh.querySelectorAll('.gh-titulo > td').forEach(td => { td.colSpan = nCol; });
    }
    // Listas de días por revisar bajo cada fila: columnas, ubicación y marcas de cada día
    if (window.mxBandasAjustar) { window.mxBandasAjustar(container); window.mxBandasCargarMarcas(container); }

    // ── TOOLTIP VOLANTE (reemplaza Bootstrap Popover) ─────────────────────────
    // Un solo div en el body, pointer-events:none para no interceptar eventos del mouse.
    // Event delegation sobre la tabla: mouseover muestra, mouseout oculta.
    // Garantia: imposible que quede pegado porque nunca hay instancias huerfanas.
    setTimeout(() => {
        // Limpiar tooltip anterior si existe (por re-render)
        let flyTip = document.getElementById('grid-fly-tooltip');
        if (!flyTip) {
            flyTip = document.createElement('div');
            flyTip.id = 'grid-fly-tooltip';
            flyTip.style.cssText = [
                'position:fixed',
                'z-index:9999',
                'display:none',
                'pointer-events:none',
                'max-width:460px',
                'min-width:0',
                'border-radius:16px',
                'background:transparent',
                'border:0',
                'padding:0',
                'overflow:visible',
                'transition:opacity 0.08s ease'
            ].join(';');
            document.body.appendChild(flyTip);
        }

        function _positionFlyTip(e) {
            const PAD = 14;
            flyTip.style.maxWidth = Math.min(460, window.innerWidth - 16) + 'px';
            const tipW = flyTip.offsetWidth  || 340;
            const tipH = flyTip.offsetHeight || 200;
            let x = e.clientX + PAD;
            let y = e.clientY + PAD;
            if (x + tipW > window.innerWidth  - 8) x = e.clientX - tipW - PAD;
            if (y + tipH > window.innerHeight - 8) y = e.clientY - tipH - PAD;
            if (x < 4 || x + tipW > window.innerWidth - 4) x = Math.max(4, (window.innerWidth - tipW) / 2);   // pantalla angosta: centrado
            if (y < 4) y = 4;
            flyTip.style.left = Math.max(4, x) + 'px';
            flyTip.style.top  = Math.max(4, y) + 'px';
        }

        function _showFlyTip(td, e) {
            const html = _getCellTipHtml(td);
            if (!html) return;
            flyTip.innerHTML = `<div class="popover-body p-0">${html}</div>`;
            flyTip.style.display = 'block';
            flyTip.style.opacity = '1';
            _positionFlyTip(e);
        }

        function _hideFlyTip() {
            if (flyTip.classList.contains('tp-pinned')) return;   // fijado con Shift: no se oculta solo
            flyTip.style.display = 'none';
        }
        // Shift fija el tooltip (permite leerlo entero, ver todos los tramos y copiar datos).
        // Se suelta con Esc, con otro Shift o haciendo clic fuera.
        function _unpinFlyTip() {
            flyTip.classList.remove('tp-pinned');
            flyTip.style.pointerEvents = 'none';
            flyTip.style.display = 'none';
        }
        if (!flyTip._pinBound) {
            flyTip._pinBound = true;
            document.addEventListener('keydown', (ev) => {
                if (ev.key === 'Shift' && !ev.repeat && flyTip.style.display === 'block') {
                    if (flyTip.classList.contains('tp-pinned')) { _unpinFlyTip(); }
                    else { flyTip.classList.add('tp-pinned'); flyTip.style.pointerEvents = 'auto'; flyTip.style.maxHeight = (window.innerHeight - 16) + 'px'; flyTip.style.overflowY = 'auto'; }
                } else if (ev.key === 'Escape' && flyTip.classList.contains('tp-pinned')) { _unpinFlyTip(); }
            });
            document.addEventListener('mousedown', (ev) => {
                if (flyTip._pinnedAt && Date.now() - flyTip._pinnedAt < 900) return;   // eventos de mouse emulados al soltar el dedo
                if (flyTip.classList.contains('tp-pinned') && !flyTip.contains(ev.target)) _unpinFlyTip();
            }, true);
        }

        const tableEl = container.querySelector('table.matrix-table');
        if (tableEl) {
            // Eliminar listeners previos clonando el nodo (evita duplicados en re-render)
            const newTable = tableEl; // ya es nuevo por innerHTML

            newTable.addEventListener('mouseover', (e) => {
                if (flyTip.classList.contains('tp-pinned')) return;
                if (window._gridTooltipEnabled === false) { _hideFlyTip(); return; }
                const td = e.target.closest('td[data-grid-tooltip]');
                if (!td) { _hideFlyTip(); return; }
                _showFlyTip(td, e);
            });

            newTable.addEventListener('mousemove', (e) => {
                if (window._gridTooltipEnabled !== false && flyTip.style.display !== 'none' && !flyTip.classList.contains('tp-pinned')) _positionFlyTip(e);
            });

            newTable.addEventListener('mouseout', (e) => {
                const td = e.target.closest('td[data-grid-tooltip]');
                if (!td) return;
                // Solo ocultar si el mouse sale hacia algo que no es otra celda con tooltip
                const to = e.relatedTarget ? e.relatedTarget.closest('td[data-grid-tooltip]') : null;
                if (!to) _hideFlyTip();
            });

            newTable.addEventListener('mouseleave', _hideFlyTip);
        }

        // Seguridad extra: al hacer scroll en el contenedor ocultar el tooltip
        const tableScroller = container.querySelector('[style*="overflow:auto"]');
        if (tableScroller && !tableScroller._flyTipFixed) {
            tableScroller._flyTipFixed = true;
            tableScroller.addEventListener('scroll', _hideFlyTip, { passive: true });
        }

        // Seguridad extra: click en cualquier lado lo cierra
        document.addEventListener('click', _hideFlyTip, { passive: true, once: false });

        // ── Pantallas táctiles: mantener pulsada una celda muestra el detalle completo (equivale a Shift) ──
        if (tableEl && !tableEl._lpBound) {
            tableEl._lpBound = true;
            let lpTimer = null, lpStart = null, lpFired = false;
            const LP_MS = 480, LP_MOVE = 10;
            const clearLp = () => { if (lpTimer) { clearTimeout(lpTimer); lpTimer = null; } };
            tableEl.addEventListener('touchstart', (e) => {
                if (e.touches.length !== 1) { clearLp(); return; }
                const td = e.target.closest('td[data-grid-tooltip]');
                if (!td || window._gridTooltipEnabled === false) return;
                const t = e.touches[0];
                lpStart = { x: t.clientX, y: t.clientY };
                lpFired = false;
                clearLp();
                lpTimer = setTimeout(() => {
                    lpTimer = null; lpFired = true;
                    if (navigator.vibrate) { try { navigator.vibrate(12); } catch (_) {} }
                    _showFlyTip(td, { clientX: lpStart.x, clientY: lpStart.y });
                    flyTip._pinnedAt = Date.now();
                    flyTip.classList.add('tp-pinned');
                    flyTip.style.pointerEvents = 'auto';
                    flyTip.style.maxHeight = (window.innerHeight - 16) + 'px';
                    flyTip.style.overflowY = 'auto';
                    _positionFlyTip({ clientX: lpStart.x, clientY: lpStart.y });
                }, LP_MS);
            }, { passive: true });
            tableEl.addEventListener('touchmove', (e) => {
                if (!lpTimer || !lpStart) return;
                const t = e.touches[0];
                if (Math.abs(t.clientX - lpStart.x) > LP_MOVE || Math.abs(t.clientY - lpStart.y) > LP_MOVE) clearLp();
            }, { passive: true });
            ['touchend', 'touchcancel'].forEach(ev => tableEl.addEventListener(ev, clearLp, { passive: true }));
            // Tras una pulsación larga no debe abrirse el modal de acciones
            tableEl.addEventListener('click', (e) => {
                if (lpFired) { e.stopPropagation(); e.preventDefault(); lpFired = false; }
            }, true);
            // El menú contextual del navegador (pulsación larga en Android) estorba
            tableEl.addEventListener('contextmenu', (e) => {
                if (e.target.closest('td[data-grid-tooltip]') && window.matchMedia('(pointer:coarse)').matches) e.preventDefault();
            });
        }
        // Tocar fuera del detalle fijado lo cierra
        if (!flyTip._touchOutBound) {
            flyTip._touchOutBound = true;
            document.addEventListener('touchstart', (ev) => {
                if (flyTip.classList.contains('tp-pinned') && !flyTip.contains(ev.target)) _unpinFlyTip();
            }, { passive: true, capture: true });
        }

    }, 100);
}

// ─── HELPERS INTERNOS ────────────────────────────────────────────────────────
function _fmtMin(min) {
    if (!min || min === 0) return '—';
    if (Math.abs(min) < 0.0083) return '00:00:00';
    return formatExactMinutesToTime(Math.abs(min));
}

// ─── CACHÉ DE ESTADOS (cargada desde API) ────────────────────────────────────
// Se carga una vez al iniciar la app. El frontend la usa para badges y tooltips.
window._estadosAsistencia = {}; // { codigo: { nombre_display, color_clase, icono_bi, descripcion } }

window._loadEstadosAsistencia = async function() {
    try {
        const resp = await fetch('/api/configuracion/estados/?solo_activos=true');
        if (!resp.ok) return;
        const lista = await resp.json();
        window._estadosAsistencia = {};
        // Estos textos se pintan dentro de HTML (badges, leyenda, tooltips): se escapan una sola vez al cargar
        const _esc = v => (typeof v === 'string') ? v.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;') : v;
        lista.forEach(e => {
            ['nombre_display', 'short_label', 'descripcion', 'icono_bi', 'color_clase'].forEach(k => { if (k in e) e[k] = _esc(e[k]); });
            window._estadosAsistencia[e.codigo] = e;
        });
        console.log(`[Estados] ${lista.length} estados cargados desde BD.`);
    } catch(err) {
        console.warn('[Estados] Error cargando estados, usando defaults:', err);
    }
};

// Helpers para obtener datos de estado (con fallback hardcodeado)
function _getEstadoColor(codigo) {
    return (window._estadosAsistencia[codigo] || {}).color_clase || _fallbackEstadoColor(codigo);
}
function _fallbackEstadoColor(codigo) {
    const m = { OK:'badge-state-success', INASISTENCIA:'badge-state-danger', ATRASO:'badge-state-warning',
                SALIDA_ADELANTADA:'badge-state-info', LIBRE:'badge-state-neutral', FERIADO:'badge-state-warning',
                EXTRA:'badge-state-info', JORNADA_ESPECIAL:'badge-state-info', EN_CURSO:'badge-state-success',
                ANOMALIA:'bg-dark text-white', PERMISO:'badge-state-info' };
    return m[codigo] || 'badge-state-neutral';
}

// Leyenda de la grilla: siglas e íconos salen de la tabla maestra de estados (Configuración › Estados),
// con respaldo local; así nunca contradice lo que muestran las celdas.
// Respaldo si auth.js no cargó: el nombre completo en MAYÚSCULAS (orden del dueño, 31-10-2026)
window.nombreTitulo = window.nombreTitulo || function (s) {
    return String(s || '').split(/\s+/).filter(p => p && p !== '.').join(' ').toLocaleUpperCase('es-CL');
};

function _leyendaEstadosHtml() {
    const c = window._estadosAsistencia || {};
    const items = [
        ['OK', 'Normal', '', 'OK', 'bi-check-circle-fill', 'badge-state-success'],
        ['ATRASO', 'Atraso', '', 'ATR', 'bi-clock-fill', 'badge-state-warning'],
        ['SALIDA_ADELANTADA', 'Sal. adelantada', '', 'SAL', 'bi-box-arrow-left', 'badge-state-info'],
        ['INASISTENCIA', 'Inasistencia', '', 'INA', 'bi-x-circle-fill', 'badge-state-danger'],
        ['LIBRE', 'Libre (auto)', '', 'LIB', 'bi-cup-hot-fill', 'badge-state-neutral'],
        ['FERIADO', 'Feriado', 'badge-fer', 'FER', 'bi-calendar-heart-fill', 'badge-state-warning'],
        ['PERMISO', 'Permiso', '', 'PER', 'bi-calendar-check-fill', 'badge-state-info'],
        ['PENDIENTE', 'Pendiente', 'badge-pen', 'PEN', 'bi-hourglass-split', 'badge-state-warning'],
        ['HORAS_EXTRAS', 'Horas extra', 'badge-he', 'HE', 'bi-clock-fill', 'badge-state-warning']
    ];
    return items.map(([cod, txt, extra, sigla, icono, cls]) => {
        const e = c[cod] || {};
        const clase = (cod === 'PENDIENTE' || cod === 'HORAS_EXTRAS') ? cls : (e.color_clase || cls);
        return `<span class="badge-status ${clase} ${extra}"><span><i class="bi ${e.icono_bi || icono} me-1"></i>${e.short_label || sigla}</span></span> ${txt}`;
    }).join('\n        ');
}

function _analiticaCellBadge(di) {
    if (!di || !di.estado) return '';
    let est = di.estado;

    // Distinguir entre Compensado por Horas Extras y Compensado por Intercambio (1x1)
    if (est === 'INASISTENCIA_COMPENSADA') {
        if (di.deuda_condonada === 3) {
            est = 'INASISTENCIA_COMPENSADA_INTERCAMBIO';
        } else {
            est = 'INASISTENCIA_COMPENSADA_HE';
        }
    }

    // --- Lógica Bolsa Flexible / Libreta 180h: Distinguir Borrador vs Cerrado ---
    const hasMinutosActividad = Boolean(
        (di.minutos_conduccion && Number(di.minutos_conduccion) > 0) ||
        (di.minutos_espera && Number(di.minutos_espera) > 0) ||
        (di.minutos_auxiliares && Number(di.minutos_auxiliares) > 0) ||
        (di.minutos_efectivos && Number(di.minutos_efectivos) > 0) ||
        (di.horas_trabajadas && Number(di.horas_trabajadas) > 0)
    );
    const hasRealLibreta = Boolean(di.slots_96 || (di.origen === 'LIBRETA_180H' && hasMinutosActividad));
    const isLibretaCerrada = Boolean(di.libreta_cerrada || di.cerrado);

    if (di._esBolsa || hasRealLibreta) {
        if (hasRealLibreta && hasMinutosActividad && !isLibretaCerrada && est !== 'LIBRE' && est !== 'PENDIENTE' && est !== 'FERIADO') {
            est = 'BORRADOR_180H';
        } else if (['ATRASO', 'SALIDA_ADELANTADA', 'ATR_SAD'].includes(est)) {
            est = 'OK'; // Visualmente es un día trabajado normal
        }
        // Suprimir flags secundarios para que no rendericen badges apilados
        di.tiene_atraso = false;
        di.tiene_salida_adelantada = false;
    }

    // Construir badgeMap desde caché de BD (si está disponible) + fallback hardcodeado
    const estadosCache = window._estadosAsistencia || {};
    const badgeMap = {};
    // Primero cargamos los estados desde la caché de BD
    Object.values(estadosCache).forEach(e => {
        const icon = e.icono_bi ? `<i class="bi ${e.icono_bi} me-1"></i>` : '';
        // Para badges cortos usamos short_label o fallback
        const shortLabel = e.short_label || (e.codigo === 'JORNADA_ESPECIAL' ? 'ESP' : (e.codigo.length <= 3 ? e.codigo : e.codigo.substring(0,3)));
        // Sigla de 6 o 7 letras (p. ej. REVISAR): la pastilla le quita aire para que quepa (grilla-hd.css → .st-largo)
        const largo = String(e._badgeLabel || shortLabel).replace(/<[^>]*>/g, '').length > 5 ? ' st-largo' : '';
        badgeMap[e.codigo] = [e.color_clase + largo, icon + (e._badgeLabel || shortLabel)];
    });

    // Inyectar mappings virtuales para los dos tipos de inasistencia compensada y borrador libreta
    badgeMap['BORRADOR_180H'] = [
        'badge-borrador-libreta', 
        '<i class="bi bi-pencil-square me-1"></i>BOR'
    ];
    badgeMap['INASISTENCIA_COMPENSADA_INTERCAMBIO'] = [
        'badge-compensatorio', 
        '<i class="bi bi-arrow-left-right me-1"></i>COMP'
    ];
    badgeMap['INASISTENCIA_COMPENSADA_HE'] = [
        'badge-inasistencia-compensada-he', 
        '<i class="bi bi-clock-history me-1"></i>C.HE'
    ];
    badgeMap['DESCANSO OPERATIVO'] = [
        'badge-state-info', 
        '<i class="bi bi-pause-circle-fill me-1"></i>DEOP'
    ];
    badgeMap['DESCANSO_OPERATIVO'] = [
        'badge-state-info', 
        '<i class="bi bi-pause-circle-fill me-1"></i>DEOP'
    ];
    badgeMap['DEOP'] = [
        'badge-state-info', 
        '<i class="bi bi-pause-circle-fill me-1"></i>DEOP'
    ];
    badgeMap['PENDIENTE'] = [
        'badge-state-warning', 
        '<i class="bi bi-hourglass-split me-1"></i>PEN'
    ];

    // Fallback hardcodeado (si la caché aún no cargó)
    if (Object.keys(badgeMap).length === 0) {
        Object.assign(badgeMap, {
            'OK':               ['badge-state-success', '<i class="bi bi-check-circle-fill me-1"></i>OK'],
            'ATRASO':           ['badge-state-warning',  '<i class="bi bi-clock-fill me-1"></i>ATR'],
            'SALIDA_ADELANTADA':['badge-state-info',     '<i class="bi bi-box-arrow-left me-1"></i>SAD'],
            'INASISTENCIA':     ['badge-state-danger',   '<i class="bi bi-x-circle-fill me-1"></i>INA'],
            'LIBRE':            ['badge-state-neutral',  '<i class="bi bi-cup-hot-fill me-1"></i>LIB'],
            'FERIADO':          ['badge-state-warning',  '<i class="bi bi-calendar-heart-fill me-1"></i>FER'],
            'PERMISO':          ['badge-state-info',     '<i class="bi bi-person-check-fill me-1"></i>PER'],
            'EXTRA':            ['badge-state-info',     '<i class="bi bi-plus-circle-fill me-1"></i>EXT'],
            'ANOMALIA':         ['bg-dark text-white',   '<i class="bi bi-exclamation-triangle-fill me-1"></i>ANO'],
            'PENDIENTE':        ['badge-state-warning',  '<i class="bi bi-hourglass-split me-1"></i>PEN'],
            'JORNADA_ESPECIAL': ['badge-state-info',     '<i class="bi bi-star-fill me-1"></i>ESP'],
            'EN_CURSO':         ['badge-state-success',  '<i class="bi bi-play-circle-fill me-1"></i>CUR'],
            'INASISTENCIA_COMPENSADA_INTERCAMBIO': ['badge-compensatorio', '<i class="bi bi-arrow-left-right me-1"></i>COMP'],
            'INASISTENCIA_COMPENSADA_HE':          ['badge-inasistencia-compensada-he', '<i class="bi bi-clock-history me-1"></i>C.HE'],
            'JORNADA_COMPENSATORIA':   ['badge-compensatorio',           '<i class="bi bi-arrow-left-right me-1"></i>COMP']
        });
    }


    const stdBadgeStyle = "width:52px; min-height:22px; display:inline-flex; align-items:center; justify-content:center; flex-direction:column; line-height:1.1;";

    // ── Estado PRIMARIO: viene resuelto por el motor cuántico (sin overrides en UI) ──

    // ── Badge del estado PRIMARIO ─────────────────────────────────────────────
    let pillClass = 'badge-state-neutral';
    let label = (estadosCache[est] && estadosCache[est].short_label) || (est === 'JORNADA_ESPECIAL' ? 'ESP' : (est.length <= 3 ? est : est.substring(0,3)));
    let tooltipTitle = '';

    if (di.justificacion_id && di.nomenclatura) {
        // Justificación resuelta por el motor: rótulo = nomenclatura del tipo configurado
        const jInfo = di.justificacion || {};
        const jNombre = (jInfo.tipo_nombre || est || '').toString();
        const goce = (jInfo.con_goce_sueldo === 0 || jInfo.con_goce_sueldo === false) ? 'Sin goce de sueldo' : 'Con goce de sueldo';
        const pagador = jInfo.pagador ? ` · Pagador: ${jInfo.pagador}` : '';
        pillClass = (estadosCache[est] && _getEstadoColor(est)) || 'badge-state-info';
        label = `<i class="bi bi-file-earmark-medical-fill me-1"></i>${di.nomenclatura}`;
        tooltipTitle = `${jNombre} (${di.nomenclatura}) · ${goce}${pagador}`;
    } else if (badgeMap[est]) {
        [pillClass, label] = badgeMap[est];
        // Variantes visuales (grilla en calma): distinguen estados que comparten color base
        if (est === 'FERIADO') pillClass += ' badge-fer'; else if (est === 'PENDIENTE') pillClass += ' badge-pen';
        if (est === 'LIBRE') tooltipTitle = 'Día Libre (Asignación automática)';
        else if (est === 'FERIADO') tooltipTitle = 'Feriado legal / Irrenunciable';
        else if (est === 'INASISTENCIA') tooltipTitle = 'Inasistencia (Generada automáticamente)';
        else if (est === 'INASISTENCIA_COMPENSADA_INTERCAMBIO') tooltipTitle = 'Día Compensado por Intercambio (1x1)';
        else if (est === 'INASISTENCIA_COMPENSADA_HE') tooltipTitle = 'Compensado con Horas Extras';
    } else if (di.nomenclatura) {
        pillClass = 'badge-state-info';
        label = di.nomenclatura;
    }
    
    if (!tooltipTitle && estadosCache[est] && estadosCache[est].descripcion) {
        tooltipTitle = estadosCache[est].descripcion;
    }

    if (di.jornada_adicional) {
        const ja = di.jornada_adicional;
        const esMasDos = (ja.observaciones && ja.observaciones.includes('(+2)')) || (di.observaciones && di.observaciones.includes('(+2)'));
        if ((di.horas_teoricas || 0) === 0 || est === 'LIBRE' || est === 'JORNADA_ESPECIAL') {
            if (ja.estado === 'RECHAZADA') {
                // REGLA DE NEGOCIO: Si fue rechazada en día libre/festivo, no abulta la grilla con badge especial
                primaryBadge = `<div class="badge-status ${pillClass}" style="${stdBadgeStyle}" ${tooltipTitle ? `title="${tooltipTitle} (Jornada rechazada)"` : ''}><span>${label}</span></div>`;
            } else if (ja.estado === 'COMPENSATORIA') {
                // Jornada EXTRA gastada en compensar una inasistencia: la celda muestra su propio estado (COMP)
                primaryBadge = `<div class="badge-status ${pillClass}" style="${stdBadgeStyle}" title="Jornada usada para compensar una inasistencia"><span>${label}</span></div>`;
            } else if (ja.estado === 'HORAS_EXTRAS') {
                const class_esp = 'badge-state-warning badge-he';
                const label_esp = esMasDos ? '+2 HE' : 'HE';
                const icon_esp = '<i class="bi bi-clock-fill me-1"></i>';
                const title_esp = 'Jornada Adicional Aprobada como Horas Extras';
                primaryBadge = `<div class="badge-status ${class_esp}" style="${stdBadgeStyle}" title="${title_esp}"><span>${icon_esp}${label_esp}</span></div>`;
            } else if (ja.estado === 'EXTRA') {
                const class_esp = _getEstadoColor('EXTRA') || 'badge-state-info';
                const label_esp = (estadosCache['EXTRA'] || {}).short_label || 'EXT';
                const title_esp = 'Jornada Adicional Aprobada como Extra';
                primaryBadge = `<div class="badge-status ${class_esp}" style="${stdBadgeStyle}" title="${title_esp}"><span><i class="bi bi-star-fill me-1"></i>${label_esp}</span></div>`;
            } else {
                let class_esp = _getEstadoColor('JORNADA_ESPECIAL') || 'badge-state-info';
                let label_esp = esMasDos ? '+2' : ((estadosCache['JORNADA_ESPECIAL'] || {}).short_label || 'ESP');
                let icon_esp = esMasDos ? '' : '<i class="bi bi-star-fill me-1"></i>';
                let title_esp = esMasDos ? 'Jornada Especial (+2): Cobertura de Turno' : 'Jornada Adicional Pendiente de Aprobación';
                primaryBadge = `<div class="badge-status ${class_esp}" style="${stdBadgeStyle}" title="${title_esp}"><span>${icon_esp}${label_esp}</span></div>`;
            }
            // Llamado de emergencia (o +2) en un día no laborable: su propio estado, debajo de la jornada especial, y se valida
            // aparte (orden del dueño, 05-11-2026). Sigla, color e ícono salen de Configuración → Estados. Rechazado no se muestra.
            const llam = ja.llamado;
            if (llam && llam.estado !== 'RECHAZADA') {
                const eme = estadosCache['LLAMADO_EMERGENCIA'] || {};
                const esAdic = llam.tipo === 'ADICIONAL';
                const sigla = esAdic ? '+2' : (eme.short_label || 'EME');
                const suf = llam.estado === 'HORAS_EXTRAS' ? ' HE' : (llam.estado === 'EXTRA' ? ' EXT' : '');
                const claseL = _getEstadoColor('LLAMADO_EMERGENCIA') || 'color-violeta';
                const icoL = suf ? '' : '<i class="bi ' + (eme.icono_bi || 'bi-telephone-inbound-fill') + ' me-1"></i>';
                const queL = esAdic ? 'Segunda jornada (+2)' : 'Llamado de emergencia';
                const decL = llam.estado === 'HORAS_EXTRAS' ? 'validado como horas extra'
                    : (llam.estado === 'EXTRA' ? 'validado como jornada EXTRA' : 'por validar');
                const titL = queL + ' ' + (llam.hora_entrada || '--:--') + ' a ' + (llam.hora_salida || '--:--') + ' · ' + _fmtMin(llam.minutos) + ' · ' + decL;
                primaryBadge = '<div class="d-flex flex-column align-items-center justify-content-center gap-1 w-100">' + primaryBadge
                    + '<div class="badge-status ' + claseL + '" style="' + stdBadgeStyle + '" title="' + titL + '"><span>' + icoL + sigla + suf + '</span></div></div>';
            }
        } else {
            const class_izq = pillClass;
            const label_izq = label;
            
            if (ja.estado === 'RECHAZADA') {
                // REGLA DE NEGOCIO: Cobertura rechazada desaparece de la celda de la grilla, quedando únicamente el turno ordinario limpio
                primaryBadge = `<div class="badge-status ${class_izq}" style="${stdBadgeStyle}" ${tooltipTitle ? `title="${tooltipTitle} (Cobertura +2 rechazada)"` : ''}><span>${label_izq}</span></div>`;
            } else {
                let class_der = 'badge-state-neutral';
                let label_der = esMasDos ? '+2' : 'ESP';
                let title_der = esMasDos ? 'Jornada Especial (+2): Cobertura de Turno' : 'Jornada Especial Adicional';
                
                if (ja.estado === 'PENDIENTE' || ja.estado === 'JORNADA_ESPECIAL') {
                    class_der = _getEstadoColor('JORNADA_ESPECIAL') || 'badge-state-info';
                    label_der = esMasDos ? '+2' : ((estadosCache['JORNADA_ESPECIAL'] || {}).short_label || 'ESP');
                    title_der = esMasDos ? 'Jornada Especial (+2): Cobertura de Turno' : 'Jornada Adicional Pendiente de Aprobación';
                } else if (ja.estado === 'HORAS_EXTRAS') {
                    class_der = 'badge-state-warning';
                    label_der = esMasDos ? '+2 HE' : 'HE';
                    title_der = 'Jornada Especial (+2): Cobertura Aprobada como Horas Extras';
                } else if (ja.estado === 'EXTRA') {
                    class_der = _getEstadoColor('EXTRA') || 'badge-state-info';
                    label_der = (estadosCache['EXTRA'] || {}).short_label || 'EXT';
                    title_der = 'Jornada Adicional Aprobada como Extra (Bono Plano)';
                } else if (ja.estado === 'COMPENSATORIA') {
                    class_der = 'badge-compensatorio';
                    label_der = 'COMP';
                    title_der = 'Segunda jornada (+2) usada para compensar una inasistencia';
                }
                
                primaryBadge = `
                <div class="d-flex flex-column align-items-center justify-content-center gap-1 w-100">
                    <div class="badge-status ${class_izq}" style="${stdBadgeStyle}" ${tooltipTitle ? `title="${tooltipTitle}"` : ''}>
                        <span>${label_izq}</span>
                    </div>
                    <div class="badge-status ${class_der}" style="${stdBadgeStyle}" title="${title_der}">
                        <span>${label_der}</span>
                    </div>
                </div>`;
            }
        }
    }
    const esRetornoRutaSplit = (
        (di.observaciones && di.observaciones.includes('Retorno de Ruta') && Boolean(di.hora_entrada_real)) ||
        (di.observaciones && di.observaciones.includes('Salida a Ruta') && Boolean(di.hora_salida_real)) ||
        (est !== 'ANOMALIA' && (di.observaciones && (di.observaciones.includes('Retorno de Ruta') || di.observaciones.includes('Salida a Ruta')))) ||
        (est !== 'ANOMALIA' && (di.tiene_anomalia || di.alerta_anomalia) && Boolean(di._esBolsa))
    );

    if (esRetornoRutaSplit && !di.jornada_adicional) {
        const [anc, anl] = badgeMap['ANOMALIA'] || ['bg-dark text-white', '<i class="bi bi-exclamation-triangle-fill me-1"></i>ANO'];
        
        // Si la anomalía es de retorno (en la mañana), va ARRIBA del OK. Si es salida a ruta (en la tarde/noche), va ABAJO del OK.
        const esRetornoManana = (di.observaciones && di.observaciones.includes('Retorno de Ruta')) || (di.hora_salida_real && di.hora_entrada_real && di.hora_salida_real < di.hora_entrada_real);
        
        const badgeAnoHtml = `
            <div class="badge-status ${anc}" style="${stdBadgeStyle}" title="Retorno de Ruta / Anomalía pendiente de unir">
                <span>${anl}</span>
            </div>`;
        const badgeLocalHtml = `
            <div class="badge-status ${pillClass}" style="${stdBadgeStyle}" ${tooltipTitle ? `title="${tooltipTitle}"` : ''}>
                <span>${label}</span>
            </div>`;

        primaryBadge = `
        <div class="d-flex flex-column align-items-center justify-content-center gap-1 w-100">
            ${esRetornoManana ? badgeAnoHtml + badgeLocalHtml : badgeLocalHtml + badgeAnoHtml}
        </div>`;
    } else if (!di.jornada_adicional && est !== 'ANOMALIA' && (di.observaciones || '').includes('Segunda jornada sin SALIDA')) {
        // Segunda jornada sin SALIDA (orden del dueño, 27-10-2026): arriba el estado de la jornada principal y debajo la anomalía;
        // al agregar esa SALIDA la segunda jornada se vuelve +2 (o llamado de emergencia).
        const [anc, anl] = badgeMap['ANOMALIA'] || ['bg-dark text-white', '<i class="bi bi-exclamation-triangle-fill me-1"></i>ANO'];
        const hAno = ((di.observaciones || '').match(/Segunda jornada sin SALIDA: ENTRADA de las (\d{2}:\d{2}:\d{2})/) || [])[1] || '';
        primaryBadge = `
        <div class="d-flex flex-column align-items-center justify-content-center gap-1 w-100">
            <div class="badge-status ${pillClass}" style="${stdBadgeStyle}" ${tooltipTitle ? `title="${tooltipTitle}"` : ''}><span>${label}</span></div>
            <div class="badge-status ${anc}" style="${stdBadgeStyle}" title="Segunda jornada sin SALIDA (ENTRADA ${hAno}): falta su SALIDA"><span>${anl}</span></div>
        </div>`;
    } else if (!di.jornada_adicional) {
        primaryBadge = `<div class="badge-status ${pillClass}" style="${stdBadgeStyle}" ${tooltipTitle ? `title="${tooltipTitle}"` : ''}><span>${label}</span></div>`;
    }

    // +2 (cobertura o segunda jornada): ya no se valida y va a las horas extra del día, pero se ve como un estado más, del
    // mismo tamaño, debajo del estado de la jornada (dueño, 10-11-2026). Color de Configuración → Estados (jornada especial).
    if (!di.jornada_adicional && !di._esBolsa && Number(di.minutos_extra_mas2 || 0) > 0) {
        const claseM2 = _getEstadoColor('JORNADA_ESPECIAL') || 'badge-state-info';
        primaryBadge = `<div class="d-flex flex-column align-items-center justify-content-center gap-1 w-100">${primaryBadge}`
            + `<div class="badge-status ${claseM2}" style="${stdBadgeStyle}" title="+2: ${_fmtMin(di.minutos_extra_mas2)} sumadas a las horas extra del día, por aprobar"><span>+2</span></div></div>`;
    }

    // ── Badges secundarios según flags independientes ─────────────────────────
    // Solo se muestran si el flag es verdadero Y el estado primario no lo representa ya
    const extraBadges = [];

    if ((di.tiene_atraso || di.alerta_atraso) && est !== 'ATRASO' && est !== 'ANOMALIA') {
        const [ac, al] = badgeMap['ATRASO'] || ['badge-state-warning', '<i class="bi bi-clock-fill me-1"></i>ATR'];
        extraBadges.push(`<div class="badge-status ${ac}" style="${stdBadgeStyle}"><span>${al}</span></div>`);
    }
    if (di.tiene_salida_adelantada && est !== 'SALIDA_ADELANTADA' && est !== 'ANOMALIA') {
        const [sc, sl] = badgeMap['SALIDA_ADELANTADA'] || ['badge-state-info', '<i class="bi bi-box-arrow-left me-1"></i>SAD'];
        extraBadges.push(`<div class="badge-status ${sc}" style="${stdBadgeStyle}"><span>${sl}</span></div>`);
    }
    if (di.tiene_permiso && est !== 'PERMISO') {
        const [pc, pl] = badgeMap['PERMISO'] || ['badge-state-info', '<i class="bi bi-calendar-check-fill me-1"></i>PER'];
        extraBadges.push(`<div class="badge-status ${pc}" style="${stdBadgeStyle}"><span>${pl}</span></div>`);
    }
    if ((di.tiene_anomalia || di.alerta_anomalia) && est !== 'ANOMALIA' && !esRetornoRutaSplit) {
        const [anc, anl] = badgeMap['ANOMALIA'] || ['badge-state-dark', '<i class="bi bi-exclamation-triangle-fill me-1"></i>ANO'];
        extraBadges.push(`<div class="badge-status ${anc}" style="${stdBadgeStyle}" title="Marcación Anómala / Libre en el día"><span>${anl}</span></div>`);
    }
    // Badge + 2 EXCLUSIVO para Segundo Turno (Cambio de Turno en la Semana)
    if (di.observaciones && di.observaciones.includes('[Jornada Adicional Pendiente:')) {
        extraBadges.push(`<div class="badge-status" style="${stdBadgeStyle}; background-color: #0284c7; color: #ffffff; font-weight: 800; border: 1px solid #0369a1;" title="Segundo Turno por Cambio de Turno en la Semana"><span><i class="bi bi-plus-lg me-1"></i>+ 2</span></div>`);
    }
    // Si hay badges adicionales → contenedor columna; si no → badge simple
    let resultHtml = '';
    if (extraBadges.length > 0) {
        // Grilla de estados "subrayado segmentado": un segmento por estado (.st-multi) y «+N» en la esquina
        resultHtml = `<div class="st-multi" data-n="+${extraBadges.length}">
            ${primaryBadge}
            ${extraBadges.join('\n')}
        </div>`;
    } else {
        resultHtml = primaryBadge;
    }

    // En un día no laborable el llamado ya tiene su propio estado en la celda (EME): el rayo queda solo para los días hábiles
    const tieneEmergencia = di.observaciones && di.observaciones.includes('[Llamado de Emergencia:') && !(di.jornada_adicional && di.jornada_adicional.llamado);
    const tieneAlertaSistema = di.observaciones && di.observaciones.includes('[ALERTA SISTEMA');
    const tieneHE_Pendientes = !di._esBolsa && di.minutos_extra_bruto > 0 && di.estado_he === 'PENDIENTE';

    if (tieneEmergencia || tieneAlertaSistema || tieneHE_Pendientes) {
        let wrapperHtml = `<div style="position:relative; display:inline-block; width:100%;">
            ${resultHtml}`;
        if (tieneEmergencia) {
            // Nombre e ícono de Configuración → Estados (LLAMADO_EMERGENCIA): el mismo teléfono de la celda (dueño, 09-11-2026)
            const emeCfg = (window._estadosAsistencia || {})['LLAMADO_EMERGENCIA'] || {};
            const emeNom = emeCfg.nombre_display || 'Llamado de emergencia';
            wrapperHtml += `<div title="${emeNom.charAt(0) + emeNom.slice(1).toLowerCase()}: sus minutos suman a las horas extra del día" style="position:absolute; top:-6px; left:-6px; font-size:0.75rem; color:#8b5cf6; z-index:10; filter:drop-shadow(0 0 2px rgba(139,92,246,0.5));"><i class="bi ${emeCfg.icono_bi || 'bi-telephone-inbound-fill'}" aria-hidden="true"></i></div>`;
        }
        if (tieneAlertaSistema) {
            wrapperHtml += `<div title="Alerta de Sistema (Ver Tooltip)" style="position:absolute; top:-4px; right:-2px; width:12px; height:12px; background-color:#ef4444; border-radius:50%; box-shadow:0 0 6px #ef4444; border:2px solid white; z-index:10;"></div>`;
        }
        if (tieneHE_Pendientes) {
            const rightOffset = tieneAlertaSistema ? '10px' : '-2px';
            wrapperHtml += `<div title="Horas Extras Pendientes (${_fmtMin(di.minutos_extra_bruto)})" style="position:absolute; top:-4px; right:${rightOffset}; width:12px; height:12px; background-color:#f97316; border-radius:50%; box-shadow:0 0 6px #f97316; border:2px solid white; z-index:10;"></div>`;
        }
        wrapperHtml += `</div>`;
        return wrapperHtml;
    }
    return resultHtml;
}

// ─── TOGGLE DE FILTROS UI (sin llamada al backend) ───────────────────────────
function vaToggleFilter(key, value) {
    window.vistaAnaliticaState[key] = value;
    if (stateMarcacionesApp.data) {
        const container = document.getElementById('marcaciones-view-container');
        renderVistaAnalitica(stateMarcacionesApp.data, container);
    }
}

// Pestañas por tipo de horario (solo en el navegador: no llama al servidor)
window.vaSetTab = function(tipo) {
    window.mxCambioColumnas();
    window.vistaAnaliticaState.tabTipo = (tipo === 'bolsa') ? 'bolsa' : 'ciclo';
    if (stateMarcacionesApp.data) {
        renderVistaAnalitica(stateMarcacionesApp.data, document.getElementById('marcaciones-view-container'));
    }
};

// Si el bloque fijo (nombre + resúmenes) ocupa más de la mitad del ancho visible, los resúmenes
// dejan de fijarse y se deslizan junto con los días: así nunca tapan los días.
window._gridApplyPinCap = function() {
    const table = document.querySelector('#marcaciones-view-container .matrix-table-premium');
    if (!table) return;
    const wrap = table.parentElement;
    table.classList.remove('gc-unpinned');
    if (window._stickyUnpinned) return;
    // Bolsa flexible: los resúmenes nunca se fijan sobre los días (contraídos dejaban verlos por detrás); se deslizan con ellos.
    if (table.classList.contains('gc-bolsa')) { table.classList.add('gc-unpinned'); return; }
    const visible = wrap.clientWidth;
    const nameTh = table.querySelector('thead th.sticky-col-analitica');
    let pinned = nameTh ? nameTh.getBoundingClientRect().width : 0;
    table.querySelectorAll('thead tr:first-child th.sticky-premium-col').forEach(th => {
        if (getComputedStyle(th).position === 'sticky') pinned += th.getBoundingClientRect().width;
    });
    // se desfija si ocupa más de la mitad, o si dejaría menos de ~7 días visibles (420 px)
    if (visible > 0 && (pinned > visible * 0.5 || visible - pinned < 420)) table.classList.add('gc-unpinned');
};
if (!window._gridPinCapBound) {
    window._gridPinCapBound = true;
    let _t;
    // El zoom del navegador también dispara 'resize': se recalcula el ancho fijado, las bandas, el modo compacto y el alto de la tabla.
    window.addEventListener('resize', () => { clearTimeout(_t); _t = setTimeout(() => { window._gridApplyPinCap(); if (window.mxBandasAjustar) window.mxBandasAjustar(); window._vaAplicarFoco(); }, 150); });
}

// Modo "Ampliar tabla": barra compacta (solo iconos) y leyenda oculta, para que la tabla gane alto. Sin elección de la persona se activa solo en
// pantallas bajas (laptops o zoom alto, < 820 px de alto útil); lo que la persona marque con el botón manda y se recuerda en este navegador.
window._vaFocoActivo = function () {
    if (typeof window._vaFocoMem === 'boolean') return window._vaFocoMem; // respaldo si el navegador bloquea el almacenamiento
    let v = null; try { v = localStorage.getItem('asistencia_va_foco'); } catch (e) { /* sin almacenamiento */ }
    if (v === '1') return true;
    if (v === '0') return false;
    return window.innerHeight < 820;
};
window.toggleVaFoco = function () {
    const on = !window._vaFocoActivo();
    window._vaFocoMem = on;
    try { localStorage.setItem('asistencia_va_foco', on ? '1' : '0'); } catch (e) { /* sin almacenamiento */ }
    window._vaAplicarFoco();
};
window.toggleVaLeyenda = function () {
    const c = document.getElementById('marcaciones-view-container'); if (!c) return;
    c.classList.toggle('va-leyenda-abierta');
    window._vaAplicarFoco();
};
// Encabezado de la tabla siempre visible: la grilla ya no tiene su propio scroll vertical (salen todas las filas y baja la página), así que el
// "sticky" del navegador no alcanza (la caja con scroll horizontal lo ata a sí misma). Se desplaza el encabezado con la página: queda justo debajo
// de la barra superior de la app y no pasa sobre la fila de totales.
window._vaCabeceraSigue = function () {
    const wrap = document.querySelector('#marcaciones-view-container .va-tablewrap'); if (!wrap) return;
    const table = wrap.querySelector('table'), thead = table && table.querySelector(':scope > thead'); if (!thead) return;
    const hdr = document.querySelector('.header');
    const arriba = hdr && getComputedStyle(hdr).position === 'sticky' ? hdr.getBoundingClientRect().height : 0;
    const tf = table.querySelector(':scope > tfoot');
    const libre = wrap.offsetHeight - thead.offsetHeight - (tf ? tf.offsetHeight : 0);
    const d = Math.max(0, Math.min(libre, Math.round(arriba - wrap.getBoundingClientRect().top)));
    thead.style.transform = d ? 'translateY(' + d + 'px)' : '';
};
if (!window._vaCabeceraBound) {
    window._vaCabeceraBound = true;
    let _raf = 0;
    const _pedir = () => { if (_raf) return; _raf = requestAnimationFrame(() => { _raf = 0; window._vaCabeceraSigue(); }); };
    window.addEventListener('scroll', _pedir, { passive: true });
    window.addEventListener('resize', _pedir);
}
// Mejoras de la grilla (se aplican cada vez que se dibuja):
// 1) Barra de desplazamiento horizontal siempre visible al pie de la ventana: con la grilla a todo su largo la barra nativa queda al final de la
//    tabla; esta es una copia sincronizada que se queda pegada abajo mientras la tabla esté en pantalla.
// 2) Cruz al pasar el cursor: se resalta la fila de la persona y la columna del día (y su encabezado) sin pisar el color del estado de cada celda.
window._vaMejorasGrilla = function () {
    const c = document.getElementById('marcaciones-view-container'); if (!c) return;
    const wrap = c.querySelector('.va-tablewrap'), table = wrap && wrap.querySelector('table'); if (!table) return;
    let bar = c.querySelector('.va-hscroll');
    if (!bar) {
        bar = document.createElement('div'); bar.className = 'va-hscroll'; bar.setAttribute('aria-hidden', 'true'); bar.innerHTML = '<div></div>';
        wrap.after(bar);
        bar.addEventListener('scroll', () => { if (wrap.scrollLeft !== bar.scrollLeft) wrap.scrollLeft = bar.scrollLeft; }, { passive: true });
        wrap.addEventListener('scroll', () => { if (bar.scrollLeft !== wrap.scrollLeft) bar.scrollLeft = wrap.scrollLeft; }, { passive: true });
    }
    bar.firstChild.style.width = table.scrollWidth + 'px';
    bar.style.display = table.scrollWidth > wrap.clientWidth + 1 ? '' : 'none';
    bar.scrollLeft = wrap.scrollLeft;

    if (wrap._vaCruz || !(window.matchMedia && window.matchMedia('(hover: hover)').matches)) return; // en táctil no hay cursor
    wrap._vaCruz = true;
    let fila = null, celdas = [], th = null, actual = null;
    const limpiar = () => {
        if (fila) fila.classList.remove('va-hf');
        celdas.forEach(t => t.classList.remove('va-hc')); if (th) th.classList.remove('va-hc');
        fila = null; celdas = []; th = null; actual = null;
    };
    wrap.addEventListener('mouseover', e => {
        const td = e.target.closest && e.target.closest('td'); if (!td || td === actual) return;
        const tr = td.parentElement;
        if (!tr || !tr.id || !tr.id.startsWith('row-empleado-')) { limpiar(); return; } // solo filas de personas (no títulos de bloque ni bandas)
        actual = td;
        if (fila !== tr) { if (fila) fila.classList.remove('va-hf'); fila = tr; tr.classList.add('va-hf'); }
        celdas.forEach(t => t.classList.remove('va-hc')); if (th) th.classList.remove('va-hc'); celdas = []; th = null;
        const f = td.classList.contains('col-day') ? td.dataset.fecha : null;
        if (!f) return;
        celdas = [...table.querySelectorAll('td.col-day[data-fecha="' + f + '"]')]; celdas.forEach(t => t.classList.add('va-hc'));
        th = table.querySelectorAll(':scope > thead th.col-day')[[...tr.querySelectorAll('td.col-day')].indexOf(td)] || null;
        if (th) th.classList.add('va-hc');
    });
    wrap.addEventListener('mouseleave', limpiar);
};
window._vaAplicarFoco = function () {
    const c = document.getElementById('marcaciones-view-container'); if (!c) return;
    const on = window._vaFocoActivo();
    c.classList.toggle('va-foco', on);
    const b = c.querySelector('#btn-toggle-foco');
    if (b) {
        b.setAttribute('aria-pressed', String(on)); b.classList.toggle('btn-primary', on); b.classList.toggle('btn-outline-secondary', !on);
        const t = b.querySelector('.va-foco-txt'); if (t) t.textContent = on ? 'Tabla ampliada' : 'Ampliar tabla';
    }
    const l = c.querySelector('#btn-toggle-leyenda');
    if (l) { const ab = c.classList.contains('va-leyenda-abierta'); l.setAttribute('aria-pressed', String(ab)); l.classList.toggle('btn-primary', ab); l.classList.toggle('btn-outline-secondary', !ab); }
    window._vaCabeceraSigue();
    window._vaMejorasGrilla();
    if (window.mxBandasAjustar) window.mxBandasAjustar(); // el modo compacto cambia el alto de las filas: las bandas de pendientes se vuelven a medir
};

// Contraer o expandir un grupo de columnas (o cambiar de pestaña) vuelve a dibujar la grilla: los días se deslizan desde
// donde estaban hasta su nuevo lugar y las columnas de resumen entran con un corrimiento corto (solo transform y opacity).
// Se llama ANTES de dibujar; la animación se arma al terminar la función que dibuja (microtarea).
window.mxCambioColumnas = function () {
    const c = document.getElementById('marcaciones-view-container');
    if (!c || (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
    const pos = () => {
        const th = c.querySelector('.matrix-table-premium thead th.col-day'), t = c.querySelector('.matrix-table-premium');
        return th && t ? th.getBoundingClientRect().left - t.getBoundingClientRect().left : null;
    };
    const antes = pos();
    queueMicrotask(() => {
        const despues = pos(), dx = (antes !== null && despues !== null) ? antes - despues : 0;
        const opt = { duration: 300, easing: 'cubic-bezier(.23, 1, .32, 1)' };
        if (Math.abs(dx) > 1 && Math.abs(dx) < 700) {
            c.querySelectorAll('.matrix-table-premium .col-day').forEach(el => el.animate([{ transform: 'translateX(' + dx + 'px)' }, { transform: 'none' }], opt));
        }
        c.querySelectorAll('.matrix-table-premium .sticky-premium-col').forEach(el => el.animate(
            [{ opacity: 0, transform: 'translateX(' + (dx > 0 ? -10 : 10) + 'px)' }, { opacity: 1, transform: 'none' }], { duration: 260, easing: opt.easing }));
    });
};
window.vaToggleBonos = function() {
    window.mxCambioColumnas();
    window.vistaAnaliticaState.showBonos = !window.vistaAnaliticaState.showBonos;
    if (stateMarcacionesApp.data) {
        const container = document.getElementById('marcaciones-view-container');
        renderVistaAnalitica(stateMarcacionesApp.data, container);
    }
}

window.vaToggleCol = function(key) {
    window.mxCambioColumnas();
    const st = window.vistaAnaliticaState;
    const esB = !!(window._gridFlags && window._gridFlags.esBolsa);
    // showHE y showSaldoMeta tienen valor por defecto según el tipo (null): se alterna el valor efectivo
    const actual = (key === 'showHE') ? (st.showHE ?? esB)
                 : (key === 'showSaldoMeta') ? (st.showSaldoMeta ?? esB)
                 : st[key];
    st[key] = !actual;
    if (stateMarcacionesApp.data) {
        const container = document.getElementById('marcaciones-view-container');
        renderVistaAnalitica(stateMarcacionesApp.data, container);
    }
}

// ─── SETTER DE VIEWMODE (6 switches de la grilla) ────────────────────────────────
window.vaSetViewMode = function(mode) {
    // Se recuerda dónde estaba la vista elegida para que su pastilla se deslice hasta la nueva (mxVistaCambiada)
    const antes = document.querySelector('#marcaciones-view-container .va-toolbar-premium .segmented-btn.active');
    const desde = antes ? antes.getBoundingClientRect() : null;
    const cambia = mode !== stateMarcacionesApp.viewMode;
    stateMarcacionesApp.viewMode = mode;
    if (stateMarcacionesApp.data) {
        const container = document.getElementById('marcaciones-view-container');
        Promise.resolve(renderVistaAnalitica(stateMarcacionesApp.data, container))
            .then(() => { if (cambia && window.mxVistaCambiada) window.mxVistaCambiada(container, desde); });
    }
}

// ─── CONTENIDO DE CELDA SEGÚN VIEWMODE ──────────────────────────────────────
function _analiticaCellContent(di, dateStr, emp, viewMode, isFer = false) {
    // Lámina Velocidad (velocidades_ui.js): solo los choferes llevan algo. Con velocidad del GPS se ve la velocidad; sin velocidad, el estado del
    // día con la misma etiqueta de la vista normal (pendiente, borrador, descanso operativo, licencia, libre, feriado…) (pedido del dueño 05-11-2026)
    if (viewMode === 'velocidad') {
        if (!window.mxVelCelda) return '';
        const trabajo = !!(di && ['OK','ATRASO','SALIDA_ADELANTADA','ATR_SAD','EXTRA','EN_CURSO'].includes(di.estado));
        return window.mxVelCelda(emp, dateStr, trabajo, () => _analiticaCellContent(di, dateStr, emp, 'conceptos', isFer));
    }
    // Proyección visual de LIBRE o FERIADO para fechas sin datos o guardadas sin marcas
    const est = di ? di.estado : null;
    let esFeriadoPuro = isFer || est === 'FERIADO';
    let esLibrePuro = est === 'LIBRE';

    if (!di || !di.estado) {
        if (emp && emp.turno_dias && dateStr) {
            const dt2 = new Date(dateStr + 'T00:00:00');
            const pyDay = dt2.getDay() === 0 ? 6 : dt2.getDay() - 1;
            const dayInfo = emp.turno_dias[pyDay];
            if (dayInfo && dayInfo.es_libre) {
                esLibrePuro = true;
            }
        }
    }

    if (esFeriadoPuro && (!est || est === 'FERIADO') && !di?.jornada_adicional) {
        return `<div class="badge-status badge-state-warning" style="width:52px; min-height:22px; display:inline-flex; align-items:center; justify-content:center; opacity:0.65;"><span><i class="bi bi-calendar-heart-fill me-1"></i>FER</span></div>`;
    }
    if (esLibrePuro && (!est || est === 'LIBRE') && !di?.jornada_adicional) {
        return `<div class="badge-status badge-state-neutral" style="width:52px; min-height:22px; display:inline-flex; align-items:center; justify-content:center; opacity:0.55;"><span><i class="bi bi-cup-hot-fill me-1"></i>LIB</span></div>`;
    }

    if (!di || !di.estado) {
        return '';
    }
    
    const hasEff = ['OK','ATRASO','SALIDA_ADELANTADA','ATR_SAD','EXTRA','EN_CURSO'].includes(est);

    let resultHtml = '';

    if (viewMode === 'horas' && hasEff) {
        const hrs = est === 'EN_CURSO' ? '>>' : formatDecimalToTime(di.horas_trabajadas);
        const mDeuda = di.minutos_deuda || 0;
        
        let html = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1.2;">`;
        html += `<span class="fw-bold tabular-nums" style="font-size: 0.75rem">${hrs}</span>`;
        if (di.tipo_programacion !== 'BOLSA_FLEXIBLE' && di.tipo_programacion !== 'FLEXIBLE_BOLSA' && mDeuda > 0) {
            html += `<span style="font-size: 0.75rem;color:#dc2626;font-weight:700;letter-spacing:-0.2px;margin-top:2px;">DEUDA ${_fmtMin(mDeuda)}</span>`;
        }
        html += `</div>`;
        resultHtml = html;
    }
    else if (viewMode === 'he') {
        // En modo HE: nunca caer al badge de conceptos → return explícito
        if (di._esBolsa) {
            const snapHoy      = di._acumuladoBolsaSnap || 0;
            const snapAyer     = di._acumuladoBolsaSnapPrev || 0;
            const metaMinBolsa = di._metaMinBolsa || 0;
            const trabHoy      = Math.round((di.horas_trabajadas || 0) * 60);
            if (snapHoy > metaMinBolsa && trabHoy > 0) {
                const heEste = snapAyer >= metaMinBolsa ? trabHoy : (snapHoy - metaMinBolsa);
                if (heEste > 0) {
                    const col = di.estado_he === 'APROBADO' ? 'color:#16a34a' : 'color:#f97316';
                    return `<span class="fw-bold tabular-nums" style="font-size: 0.75rem;${col}">${_fmtMin(heEste)}</span>`;
                }
            }
            return ''; // Sin HE: celda vacía (no badge)
        } else {
            const heBruto = di.minutos_extra_bruto || 0;
            if (heBruto > 0) {
                const col = di.estado_he === 'APROBADO' ? 'color:#16a34a' : 'color:#dc2626';
                return `<span class="fw-bold tabular-nums" style="font-size: 0.75rem;${col}">${_fmtMin(heBruto)}</span>`;
            }
            return ''; // Sin HE: celda vacía (no badge)
        }
    }
    else if (viewMode === 'acumulado') {
        if (di._esBolsa) {
            // BOLSA_FLEXIBLE: SOLO mostrar en días efectivos (no LIBRE/FERIADO)
            if (!hasEff) return ''; // LIBRE / FERIADO → celda vacía
            const snap         = di._acumuladoBolsaSnap || 0;
            const snapAyer     = di._acumuladoBolsaSnapPrev || 0;
            const metaMinBolsa = di._metaMinBolsa || 1;
            if (snap > 0) {
                let color, bg = '';
                if (snapAyer >= metaMinBolsa) {
                    color = '#f97316'; bg = 'background:rgba(249,115,22,0.08)';
                } else if (snap > metaMinBolsa) {
                    color = '#10b981'; bg = 'background:rgba(16,185,129,0.12)';
                } else if (snap / metaMinBolsa >= 0.8) {
                    color = '#d97706';
                } else {
                    color = '#3b82f6';
                }
                const cruzaHoy = snap > metaMinBolsa && snapAyer < metaMinBolsa;
                return `<div style="display:flex;flex-direction:column;align-items:center;line-height:1.2;${bg}">
                    <span class="fw-bold tabular-nums" style="font-size: 0.75rem;color:${color}">${_fmtMin(snap)}</span>
                    ${cruzaHoy ? `<span style="font-size: 0.75rem;color:#10b981;font-weight:800">&#9733;META</span>` : ''}
                </div>`;
            }
            return '';
        } else if (hasEff && di.horas_trabajadas > 0) {
            // Turnos normales: acumulado semanal
            const snap = di._acumuladoSemanalSnap || 0;
            return snap > 0
                ? `<span class="fw-bold tabular-nums" style="font-size: 0.75rem">${_fmtMin(snap)}</span>`
                : `<span style="font-size: 0.75rem;color:#9ca3af">—</span>`;
        }
        return ''; // cualquier otro caso → vacío
    }
    else if (viewMode === 'colacion' && hasEff) {
        const mColReal = di.minutos_colacion_real || 0;
        const mColAplicado = di.minutos_colacion || 0;
        const exceso = di.minutos_exceso_colacion || 0;
        
        if (di.hora_entrada_real && di.hora_salida_real) {
            let color = mColAplicado > 0 ? '#1e293b' : '#9ca3af';
            let html = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1.2;">`;
            html += `<span class="fw-bold tabular-nums" style="font-size: 0.75rem;color:${color}">${_fmtMin(mColAplicado)}</span>`;
            
            if (exceso > 0) {
                html += `<span style="font-size: 0.75rem;color:#dc2626;font-weight:700;letter-spacing:-0.2px;margin-top:2px;">DEUDA ${_fmtMin(exceso)}</span>`;
            } else if (mColReal === 0 && mColAplicado > 0) {
                html += `<span style="font-size: 0.75rem;color:#64748b;font-weight:700;letter-spacing:-0.2px;margin-top:2px;">AUTO</span>`;
            }
            html += `</div>`;
            resultHtml = html;
        } else {
            resultHtml = `<span style="font-size: 0.75rem;color:#9ca3af">—</span>`;
        }
    }
    else if (viewMode === 'permisos') {
        const mPerm = di.minutos_permisos_detectados || 0;
        const mDeuda = di.minutos_permiso_personal_deuda || 0;
        if (mPerm > 0) return `<span class="fw-bold tabular-nums" style="font-size: 0.75rem;color:#2563eb">${_fmtMin(mPerm)}</span>`;
        if (di.tiene_permiso_hora || di.permiso_activo) {
            const mins = mDeuda > 0 ? mDeuda : Math.round((di.horas_teoricas||0)*60);
            if (mins > 0) return `<span class="fw-bold tabular-nums" style="font-size: 0.75rem;color:#d97706">${_fmtMin(mins)}</span>`;
            return `<span style="font-size: 0.75rem;color:#d97706">PER</span>`;
        }
        return hasEff ? `<span style="font-size: 0.75rem;color:#9ca3af">—</span>` : '';
    }

    if (resultHtml !== '') {
        if (est === 'EXTRA') {
            const label = 'EXTRA';
            const color = '#8b5cf6';
            return `<div style="display:flex;flex-direction:column;align-items:center;line-height:1.2;">
                ${resultHtml}
                <span style="font-size: 0.75rem;color:${color};font-weight:700;letter-spacing:-0.2px;margin-top:2px;">${label}</span>
            </div>`;
        }
        return resultHtml;
    }

    // default: conceptos
    return _analiticaCellBadge(di);
}

// ─── PARSER Y RENDERIZADOR DE SLOTS DE LIBRETA ART. 25 BIS (180 HORAS) ────
// ─── TOOLTIP DE CELDAS: helpers de presentación (estilos en css/tooltip-celda.css) ───
function _tpHuman(min) {
    // 9.53 → "9 min 32 s" ; 65 → "1 h 05 min"
    const tot = Math.round((Number(min) || 0) * 60);
    const h = Math.floor(tot / 3600), m = Math.floor((tot % 3600) / 60), s = tot % 60;
    if (h > 0) return `${h} h ${String(m).padStart(2, '0')} min`;
    if (m > 0) return s > 0 ? `${m} min ${String(s).padStart(2, '0')} s` : `${m} min`;
    return `${s} s`;
}
function _tpHM(min) {
    const t = Math.round(Math.abs(Number(min) || 0));
    return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`;
}
function _tpPill(tone, label, icon) {
    const cls = { ok: 'badge-state-success', warn: 'badge-state-warning', bad: 'badge-state-danger',
                  info: 'badge-state-info', he: 'badge-state-warning badge-he', neutral: 'badge-state-neutral' }[tone] || 'badge-state-neutral';
    return `<span class="badge-status ${cls}" style="width:auto;min-height:0">${icon ? `<i class="bi ${icon} me-1"></i>` : ''}${label}</span>`;
}

function _parseSlotsArt25bis(slots_96) {
    // La libreta se guarda como JSON de enteros ([1,1,4,0,...]); también se acepta cadena de letras (M/E/A/D/0)
    if (typeof slots_96 === 'string' && slots_96.trim().startsWith('[')) {
        try { slots_96 = JSON.parse(slots_96); } catch (_) { return null; }
    }
    if (Array.isArray(slots_96)) {
        const codeMap = { 1: 'M', 2: 'E', 3: 'A', 4: 'D' };
        slots_96 = Array.from({ length: 96 }, (_, i) => codeMap[Number(slots_96[i])] || '0').join('');
    }
    if (!slots_96 || typeof slots_96 !== 'string' || slots_96.length < 96) {
        return null;
    }
    const slotTypes = {
        'D': { code: 'D', name: 'Descanso en tierra o litera', short: 'Descanso', icon: 'bi-moon-stars-fill', color: '#0284c7', bg: '#e0f2fe' },
        'M': { code: 'M', name: 'Conducción activa', short: 'Conducción', icon: 'bi-truck', color: '#059669', bg: '#d1fae5' },
        'A': { code: 'A', name: 'Labores auxiliares / carga', short: 'Auxiliares', icon: 'bi-wrench-adjustable-circle-fill', color: '#4f46e5', bg: '#e0e7ff' },
        'E': { code: 'E', name: 'Tiempo de espera (retribuido)', short: 'Espera', icon: 'bi-hourglass-split', color: '#d97706', bg: '#fef3c7' },
        '0': { code: '0', name: 'Sin actividad registrada', short: 'Sin registro', icon: 'bi-dash-circle', color: '#94a3b8', bg: '#f1f5f9' }
    };
    
    // Agrupar en tramos continuos
    const tramos = [];
    let currentCode = slots_96[0];
    let startIdx = 0;
    
    for (let i = 1; i <= 96; i++) {
        const c = i < 96 ? slots_96[i] : null;
        if (c !== currentCode) {
            const count = i - startIdx;
            const hStart = Math.floor(startIdx / 4);
            const mStart = (startIdx % 4) * 15;
            const hEnd = Math.floor(i / 4);
            const mEnd = (i % 4) * 15;
            
            const startStr = `${String(hStart).padStart(2,'0')}:${String(mStart).padStart(2,'0')}`;
            const endStr = `${String(hEnd).padStart(2,'0')}:${String(mEnd).padStart(2,'0')}`;
            const typeInfo = slotTypes[currentCode] || slotTypes['0'];
            const durMin = count * 15;
            const durHrs = (durMin / 60).toFixed(1);
            
            tramos.push({
                code: currentCode,
                startStr,
                endStr,
                count,
                durMin,
                durHrs,
                ...typeInfo
            });
            
            currentCode = c;
            startIdx = i;
        }
    }
    
    // Totales por tipo y fatiga
    let minDescanso = 0, minConduccion = 0, minAuxiliares = 0, minEspera = 0, minSinReg = 0;
    let maxConduccionContinua = 0;
    let currCond = 0;
    
    for (let i = 0; i < 96; i++) {
        const c = slots_96[i];
        if (c === 'D') { minDescanso += 15; currCond = 0; }
        else if (c === 'M') {
            minConduccion += 15;
            currCond += 15;
            if (currCond > maxConduccionContinua) maxConduccionContinua = currCond;
        }
        else if (c === 'A') { minAuxiliares += 15; currCond = 0; }
        else if (c === 'E') { minEspera += 15; currCond = 0; }
        else { minSinReg += 15; currCond = 0; }
    }
    
    return {
        tramos,
        minDescanso,
        minConduccion,
        minAuxiliares,
        minEspera,
        minSinReg,
        minEfectivos: minConduccion + minAuxiliares,
        maxConduccionContinua,
        totalMin: 1440
    };
}

// ─── TOOLTIP EXCLUSIVO ART. 25 BIS / TRANSPORTE (BOLSA 180H Y ESPERA 88H) ────
function _buildTooltipArt25bis(di, dateFormatted, dt, feriadoDesc, isWE, empInfo) {
    di = di || {};
    const empName = empInfo ? (empInfo.nombre_completo || empInfo.nombre || 'Colaborador') : 'Colaborador';
    const empAreaText = empInfo && empInfo.area ? empInfo.area : 'LOGÍSTICA TRADICIONAL';
    const shiftName = (empInfo && empInfo.turno) || (di && di.turno_nombre) || 'TRADICIONAL TRANSPORTE';
    const stats = (empInfo && (empInfo.stats || empInfo._stats)) || {};
    
    const isFer = !!feriadoDesc;
    const est = di.estado;
    const slots_96 = di.slots_96;
    const isCerrado = !!di.libreta_cerrada || !!di.cerrado;
    
    // Parse slots si existen
    const slotsData = _parseSlotsArt25bis(slots_96);
    
    // Minutos del día
    let minCond = Number(di.minutos_conduccion) || 0;
    let minEsp = Number(di.minutos_espera) || 0;
    let minAux = Number(di.minutos_auxiliares) || 0;
    let minDesc = Number(di.minutos_descanso) || 0;
    
    if (slotsData) {
        minCond = slotsData.minConduccion;
        minEsp = slotsData.minEspera;
        minAux = slotsData.minAuxiliares;
        minDesc = slotsData.minDescanso;
    }
    
    const minEfec = minCond + minAux;
    const totalMinReg = minCond + minEsp + minAux + minDesc;
    const isCuadrado = totalMinReg >= 1440;
    const hasData = !!(slotsData || totalMinReg > 0 || di.hora_entrada_real || (di.horas_trabajadas && di.horas_trabajadas > 0));

    // Acumulados mensuales
    const acumBolsaMin = stats.acumBolsa || 0;
    const metaBolsaMin = stats.metaMin || 10800; // 180h = 10800 min
    const saldoBolsaMin = stats.saldoMeta !== null && stats.saldoMeta !== undefined ? stats.saldoMeta : (acumBolsaMin - metaBolsaMin);
    const acumEsperaMin = stats.acumEspera || 0;
    const metaEsperaMin = stats.metaEsperaMin || 5280; // 88h = 5280 min
    const saldoEsperaMin = stats.saldoEspera !== null && stats.saldoEspera !== undefined ? stats.saldoEspera : (acumEsperaMin - metaEsperaMin);
    const sg = (v) => (v > 0 ? '+' : (v < 0 ? '−' : ''));

    const toMin = (t) => { if (!t || typeof t !== 'string') return null; const p = t.split(':'); return (+p[0] || 0) * 60 + (+p[1] || 0) + (+p[2] || 0) / 60; };
    const mEnt = toMin(di.hora_entrada_real), mSal = toMin(di.hora_salida_real);
    const hasSlots = !!(slotsData && slotsData.tramos && slotsData.tramos.length > 0);
    const maxCond = hasSlots ? slotsData.maxConduccionContinua : 0;

    // ── Veredicto ──
    let tone = 'warn', vTitle = '', vSub = '', tagLabel = 'PENDIENTE', tagIcon = 'bi-exclamation-triangle-fill';
    if (hasSlots && maxCond > 300) {
        tone = 'bad'; vTitle = `Conducción continua ${(maxCond / 60).toFixed(1)} h`; vSub = 'Supera el tope de 5 h sin descanso (Art. 25 bis)';
        tagLabel = 'ALERTA'; tagIcon = 'bi-exclamation-octagon-fill';
    } else if (hasSlots) {
        tone = isCuadrado ? 'ok' : 'warn';
        const sinTramos = (minEfec + minEsp + minDesc) === 0;
        vTitle = isCuadrado ? 'Jornada cuadrada · 24:00' : (sinTramos ? 'Libreta sin tramos' : `Registro incompleto · ${_tpHM(totalMinReg)} de 24:00`);
        vSub = sinTramos ? 'Todo el día figura sin registro' : `Efectiva ${_tpHM(minEfec)}${slotsData.minConduccion > 0 ? ' · conducción en norma' : ''}`;
        tagLabel = isCerrado ? 'CERRADO' : 'BORRADOR 180H'; tagIcon = isCerrado ? 'bi-shield-check' : 'bi-pencil-square';
    } else if (est === 'LIBRE' && !hasData) {
        tone = 'neutral'; vTitle = 'Día libre'; vSub = 'Sin libreta Art. 25 bis para este día'; tagLabel = 'LIBRE'; tagIcon = 'bi-cup-hot-fill';
    } else if (isFer && !hasData) {
        tone = 'warn'; vTitle = 'Feriado'; vSub = feriadoDesc; tagLabel = 'FERIADO'; tagIcon = 'bi-star-fill';
    } else if (hasData && totalMinReg > 0) {
        tone = 'info'; vTitle = `Resumen registrado · ${_tpHM(totalMinReg)}`; vSub = 'Sin distribución de 24 h en la libreta'; tagLabel = 'PARCIAL'; tagIcon = 'bi-clipboard-data';
    } else {
        tone = 'warn'; vTitle = 'Falta registrar la libreta';
        vSub = (mEnt !== null && mSal !== null) ? 'Hay marcas de reloj, sin tramos de 24 h' : 'Sin tramos de 24 h registrados';
    }

    // ── Cuerpo ──
    const kpis = (cond, aux, esp, desc) => `
        <div class="tp-sec"><div class="tp-kp">
            <div><span>Efectiva</span><b>${_tpHM(cond + aux)}</b><em>cond. ${_tpHM(cond)} + aux. ${_tpHM(aux)}</em></div>
            <div><span>Espera</span><b style="color:#b45309">${_tpHM(esp)}</b><em>retribuida</em></div>
            <div><span>Descanso</span><b style="color:#0369a1">${_tpHM(desc)}</b><em>tierra / litera</em></div>
        </div></div>`;
    let bodyHtml = '';
    if (hasSlots) {
        let acc = 0, segs = '';
        slotsData.tramos.forEach(t => {
            const left = (acc / 96) * 100, w = (t.count / 96) * 100; acc += t.count;
            segs += `<i style="left:${left.toFixed(3)}%;width:${w.toFixed(3)}%;background:${t.color}" title="${t.short} ${t.startStr}-${t.endStr}"></i>`;
        });
        const marks = [mEnt, mSal].filter(v => v !== null).map(v => `<s style="left:${Math.min(99.5, v / 14.4).toFixed(2)}%"></s>`).join('');
        const visibles = slotsData.tramos.filter(t => !(t.code === '0' && slotsData.tramos.length > 1));
        const rows = visibles.map((t, i) => `
            <div class="tp-tr ${i >= 3 ? 'tp-extra' : ''}"><span><b style="background:${t.color}"></b><span class="tp-mono">${t.startStr}–${t.endStr}</span> ${t.short}</span><span style="color:${t.color};font-weight:700">${_tpHM(t.durMin)}</span></div>`).join('');
        const extraN = Math.max(0, visibles.length - 3);
        if (minEfec + minEsp + minDesc > 0) bodyHtml += kpis(minCond, minAux, minEsp, minDesc);
        bodyHtml += `<div class="tp-sec">
            <div class="tp-lab"><span>Cronología 24 h · libreta DT</span><span>resolución 15 m</span></div>
            <div class="tp-bar">${segs}${marks}</div>
            <div class="tp-tick"><span>00</span><span>06</span><span>12</span><span>18</span><span>24</span></div>
            <div class="tp-lg"><span><b style="background:#059669"></b>Conducción</span><span><b style="background:#4f46e5"></b>Auxiliares</span><span><b style="background:#d97706"></b>Espera</span><span><b style="background:#0284c7"></b>Descanso</span>${marks ? '<span style="margin-left:auto"><b style="background:#14235c;width:2px;height:10px"></b>reloj</span>' : ''}</div>
            <div style="margin-top:8px">${rows}${extraN > 0 ? `<div class="tp-more">+ ${extraN} tramos más · <span class="tp-kb">mantén <kbd style="font-family:var(--font-mono,monospace);font-size:.6rem;border:1px solid #d5dede;border-radius:4px;padding:0 4px">Shift</kbd> para verlos</span><span class="tp-touch">mantén pulsada la celda para verlos</span></div>` : ''}</div>
        </div>`;
        if (slotsData.minConduccion > 0) {
            const bad = maxCond > 300, pct = Math.min(100, Math.round(maxCond / 300 * 100));
            bodyHtml += `<div class="tp-sec"><div class="tp-gauge ${bad ? 'bad' : 'ok'}"><i class="bi ${bad ? 'bi-exclamation-octagon-fill' : 'bi-shield-check'}"></i>Conducción continua máx. <span class="tp-mono">${(maxCond / 60).toFixed(1)} h</span> de 5 h<span class="g"><i style="width:${pct}%"></i></span></div></div>`;
        }
    } else if (hasData && totalMinReg > 0) {
        bodyHtml += kpis(minCond, minAux, minEsp, minDesc);
    } else if (mEnt !== null || mSal !== null) {
        bodyHtml += `<div class="tp-sec"><div class="tp-chip" style="display:inline-block"><i class="bi bi-fingerprint"></i> <span class="tp-mono">${di.hora_entrada_real || '—'} → ${di.hora_salida_real || '—'}</span></div>${(mEnt !== null && mSal !== null) ? ` <span class="tp-sub" style="margin-left:6px">${_tpHuman(Math.max(0, mSal - mEnt + (mSal < mEnt ? 1440 : 0)))} en terminal</span>` : ''}</div>`;
    }

    const barBolsa = Math.max(0, Math.min(100, Math.round(acumBolsaMin / metaBolsaMin * 100)));
    const barEsp = Math.max(0, Math.min(100, Math.round(acumEsperaMin / metaEsperaMin * 100)));
    const acumHtml = `<div class="tp-sec tp-alt">
        <div class="tp-lab" style="color:#7c3aed"><span>Acumulado del ciclo</span><span>Bolsas DT</span></div>
        <div class="tp-pb"><div class="l"><span>Bolsa 180h efectiva</span><span class="tp-mono"><b>${_fmtMin(acumBolsaMin)}</b> / ${_fmtMin(metaBolsaMin)} <b style="color:${saldoBolsaMin >= 0 ? '#0f7a4f' : '#b3261e'}">(${sg(saldoBolsaMin)}${_fmtMin(Math.abs(saldoBolsaMin))})</b></span></div><div class="t"><i style="width:${barBolsa}%;background:#8b5cf6"></i></div></div>
        <div class="tp-pb"><div class="l"><span>Espera usada (tope ${_fmtMin(metaEsperaMin)})</span><span class="tp-mono"><b>${_fmtMin(acumEsperaMin)}</b> de ${_fmtMin(metaEsperaMin)}${acumEsperaMin > metaEsperaMin ? ' <b style="color:#0f7a4f">(+' + _fmtMin(acumEsperaMin - metaEsperaMin) + ' como HE)</b>' : ''}</span></div><div class="t"><i style="width:${barEsp}%;background:#f59e0b"></i></div></div>
    </div>`;

    const subLine = `${empAreaText} · ${shiftName}`;
    const html = `
    <div class="tp tp-${tone}">
        <div class="tp-hd">
            <div class="tp-top"><span><i class="bi bi-truck me-1"></i>Art. 25 bis · Bolsa 180h</span>${_tpPill(tone, tagLabel, tagIcon)}</div>
            <div class="tp-v">${vTitle}${vSub ? `<small>${vSub}</small>` : ''}</div>
            <div class="tp-nm">${empName}</div>
            <div class="tp-sub">${dateFormatted} · ${subLine}</div>
            ${isFer && vTitle !== 'Feriado' ? `<div class="tp-fer"><i class="bi bi-star-fill me-1"></i>${feriadoDesc}</div>` : ''}
        </div>
        ${bodyHtml}
        ${acumHtml}
        <div class="tp-ft">
            ${(mEnt !== null || mSal !== null) && hasSlots ? `<span><i class="bi bi-fingerprint"></i> <span class="tp-mono">${di.hora_entrada_real || '—'} → ${di.hora_salida_real || '—'}</span></span>` : ''}
            <span class="push tp-kb"><kbd>Clic</kbd> libreta</span><span class="tp-kb"><kbd>2 clics</kbd> justificar</span><span class="tp-touch push"><kbd>Toque</kbd> libreta · <kbd>2 toques</kbd> justificar</span><span class="tp-kb"><kbd>Shift</kbd> fijar</span><span class="tp-touch">Mantén pulsado: detalle completo</span>
        </div>
    </div>`;

    return _escAttr(html);
}

// ─── TOOLTIP DASHBOARD PREMIUM (LIGHT THEME) ────────────────────
function _buildRichTooltipData(di, dateStr, dt, feriadoDesc, isWE, empInfo) {
    const days = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
    const months = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
    const dayName = dt ? days[dt.getDay()] : '';
    let dateFormatted = dateStr;
    if (dt) {
        const dayNum = dt.getDate();
        const monthName = months[dt.getMonth()];
        const year = dt.getFullYear();
        dateFormatted = dayName ? `${dayName} ${dayNum} de ${monthName}, ${year}` : dateStr;
    }
    const empName = empInfo ? (empInfo.nombre_completo || empInfo.nombre || 'Empleado') : 'Empleado';
    const empAreaText = empInfo && empInfo.area ? empInfo.area : 'SIN ÁREA';
    const empId = empInfo ? (empInfo.id || empInfo.empleado_id) : (di ? di.empleado_id : null);
    const isFer = !!feriadoDesc;

    // ─────────────────────────────────────────────────────────────────────────
    // DETECCIÓN EXCLUSIVA: HORARIOS ART. 25 BIS (TRANSPORTE / BOLSA FLEXIBLE 180H)
    // ─────────────────────────────────────────────────────────────────────────
    const isEmpBolsa = (empInfo && (empInfo.tipo_programacion === 'BOLSA_FLEXIBLE' || empInfo.tipo_programacion === 'FLEXIBLE_BOLSA' || empInfo._esBolsaFlag || empInfo.modalidad_control === 'LIBRETA_180H' || (empInfo.modalidad_control && empInfo.modalidad_control.toUpperCase() === 'LIBRETA_180H'))) ||
                       (di && (di.tipo_programacion === 'BOLSA_FLEXIBLE' || di.tipo_programacion === 'FLEXIBLE_BOLSA' || di.origen === 'LIBRETA_180H' || di.modalidad_control === 'LIBRETA_180H')) ||
                       (empInfo && empInfo.turno && empInfo.turno.toUpperCase().includes('TRANSPORTE')) ||
                       (di && di.turno_nombre && di.turno_nombre.toUpperCase().includes('TRANSPORTE')) ||
                       (di && di.slots_96);

    // Antes de la fecha de corte el día se controló por reloj: tooltip normal (no pide libreta)
    if (isEmpBolsa && !window.esDiaControlPorReloj(di, dateStr, empInfo)) {
        return _buildTooltipArt25bis(di, dateFormatted, dt, feriadoDesc, isWE, empInfo);
    }

    if (!di || !di.estado) {
        const fallbackShift = (empInfo && empInfo.turno) ? empInfo.turno : 'SIN PROGRAMACIÓN';
        let scheduleHtml = '';
        if (dt && empInfo && empInfo.turno_dias) {
            const pyDay = dt.getDay() === 0 ? 6 : dt.getDay() - 1;
            const dayInfo = empInfo.turno_dias[pyDay];
            if (dayInfo) {
                if (dayInfo.es_libre) {
                    scheduleHtml = `<div style="color:var(--text-secondary, #64748b); font-weight:500; font-size: 0.6875rem; text-transform: uppercase; margin-top:2px;"><i class="bi bi-cup-hot-fill me-1"></i> HORARIO: <span style="color:var(--text-primary, #1e293b);">DÍA LIBRE</span></div>`;
                } else if (dayInfo.hora_entrada && dayInfo.hora_salida) {
                    const hEnt = dayInfo.hora_entrada.substring(0, 5);
                    const hSal = dayInfo.hora_salida.substring(0, 5);
                    scheduleHtml = `<div style="color:var(--text-secondary, #64748b); font-weight:500; font-size: 0.6875rem; text-transform: uppercase; margin-top:2px;"><i class="bi bi-clock-history me-1"></i> HORARIO: <span style="color:var(--text-primary, #1e293b);">${hEnt} - ${hSal}</span></div>`;
                }
            }
        }
        return _escAttr(`<div class="tp ${isFer ? 'tp-warn' : 'tp-neutral'} tp-sm">
            <div class="tp-hd">
                <div class="tp-top"><span><i class="bi bi-calendar3 me-1"></i>${dateFormatted}</span>${_tpPill(isFer ? 'warn' : 'neutral', isFer ? 'FERIADO' : 'SIN DATOS', isFer ? 'bi-star-fill' : '')}</div>
                <div class="tp-v">${isFer ? 'Feriado' : 'Sin datos'}<small>${isFer ? feriadoDesc : 'No hay registro de asistencia para este día'}</small></div>
                <div class="tp-nm">${empName}</div>
                <div class="tp-sub">${empAreaText} · ${fallbackShift}</div>
                ${scheduleHtml ? `<div class="tp-sub" style="margin-top:6px">${scheduleHtml.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()}</div>` : ''}
            </div>
        </div>`);
    }

    const e = di;
    let est = e.estado;
    
    // Icon mappings
    const iconMap = {
        'OK': '<i class="bi bi-check-circle-fill me-1"></i>',
        'INASISTENCIA': '<i class="bi bi-x-circle-fill me-1"></i>',
        'PERMISO': '<i class="bi bi-calendar-check-fill me-1"></i>',
        'ATRASO': '<i class="bi bi-clock-fill me-1"></i>',
        'SALIDA_ADELANTADA': '<i class="bi bi-box-arrow-left me-1"></i>',
        'LIBRE': '<i class="bi bi-cup-hot-fill me-1"></i>',
        'EN_CURSO': '<i class="bi bi-play-circle-fill me-1"></i>',
        'FERIADO': '<i class="bi bi-star-fill me-1"></i>',
        'JORNADA_ESPECIAL': '<i class="bi bi-star-fill me-1"></i>',
        'EXTRA': '<i class="bi bi-plus-circle-fill me-1"></i>',
        'ANOMALIA': '<i class="bi bi-exclamation-triangle-fill me-1"></i>',
        'PENDIENTE': '<i class="bi bi-exclamation-triangle-fill me-1"></i>'
    };
    
    const stateNameMap = {};
    Object.values(window._estadosAsistencia || {}).forEach(e => {
        stateNameMap[e.codigo] = e.nombre_display || e.codigo;
    });
    if (!stateNameMap['OK']) {
        Object.assign(stateNameMap, {
            'OK': 'OK', 'INASISTENCIA': 'INASISTENCIA',
            'SALIDA_ADELANTADA': 'SALIDA ADELANTADA', 'EN_CURSO': 'EN TURNO',
            'JORNADA_ESPECIAL': 'JORNADA ESPECIAL', 'EXTRA': 'JORNADA EXTRA',
            'ANOMALIA': 'ANOMALÍA (INCOMPLETA)'
        });
    }
    stateNameMap['PENDIENTE'] = 'ANOMALÍA (JE INCOMPLETA)';
    
    const pillClassMap = {
        'OK': 'badge-state-success',
        'INASISTENCIA': 'badge-state-danger',
        'PERMISO': 'badge-state-info',
        'ATRASO': 'badge-state-warning',
        'SALIDA_ADELANTADA': 'badge-state-info',
        'LIBRE': 'badge-state-secondary',
        'EN_CURSO': 'badge-state-success',
        'FERIADO': 'badge-state-warning',
        'JORNADA_ESPECIAL': 'badge-state-info',
        'EXTRA': 'badge-state-info',
        'ANOMALIA': 'bg-dark text-white border-0',
        'PENDIENTE': 'bg-dark text-white border-0'
    };

    let badgeHtml = '';
    const perSuffix = (e.tiene_permiso_hora || e.permiso_activo) ? ' <span style="opacity:0.8;font-size:0.9em;margin-left:4px;">(+PER)</span>' : '';
    
    if (est === 'ATR_SAD') {
        const b1 = `<div class="badge-status badge-state-warning" style="display:inline-flex; align-items:center; padding: 4px 10px; font-size: 0.6875rem; font-weight:700; border-radius: 6px; box-shadow:none; white-space:nowrap; text-transform:uppercase;"><i class="bi bi-clock-fill me-1"></i>ATRASO</div>`;
        const b2 = `<div class="badge-status badge-state-info" style="display:inline-flex; align-items:center; padding: 4px 10px; font-size: 0.6875rem; font-weight:700; border-radius: 6px; box-shadow:none; white-space:nowrap; text-transform:uppercase;"><i class="bi bi-box-arrow-left me-1"></i>SAL. ADEL. ${perSuffix}</div>`;
        badgeHtml = `<div style="display:flex; flex-direction:column; align-items:flex-end; gap: 4px;">${b1}${b2}</div>`;
    } else if (e.jornada_adicional && (est === 'LIBRE' || est === 'JORNADA_ESPECIAL')) {
        let label_je = e.jornada_adicional.estado === 'EXTRA' ? 'JORNADA EXTRA' : (e.jornada_adicional.estado === 'RECHAZADA' ? 'RECHAZADA' : 'JORNADA ESPECIAL');
        let icon_je = e.jornada_adicional.estado === 'EXTRA' ? '<i class="bi bi-plus-circle-fill me-1"></i>' : (e.jornada_adicional.estado === 'RECHAZADA' ? '<i class="bi bi-x-circle-fill me-1"></i>' : '<i class="bi bi-star-fill me-1"></i>');
        let class_je = e.jornada_adicional.estado === 'RECHAZADA' ? 'badge-state-danger' : 'badge-state-info';
        badgeHtml = `<div class="badge-status ${class_je}" style="display:inline-flex; align-items:center; padding: 4px 10px; font-size: 0.6875rem; font-weight:700; border-radius: 6px; box-shadow:none; white-space:nowrap; text-transform:uppercase;">${icon_je}${label_je}${perSuffix}</div>`;
    } else {
        const fullName = stateNameMap[est] || (e.nomenclatura || est);
        const pillClass = pillClassMap[est] || 'badge-state-info';
        const icon = iconMap[est] || '';
        badgeHtml = `<div class="badge-status ${pillClass}" style="display:inline-flex; align-items:center; padding: 4px 10px; font-size: 0.6875rem; font-weight:700; border-radius: 6px; box-shadow:none; white-space:nowrap; text-transform:uppercase;">${icon}${fullName}${perSuffix}</div>`;
    }
    
    // Formatters
    const _fM = (m) => {
        if (!m || m <= 0) return '';
        return formatExactMinutesToTime(m);
    };

    // Calculate Extra Hours distribution
    let heBruta = e.minutos_extra_bruto || 0;
    let heAprobada = e.minutos_extra_autorizados || 0;
    let heRechazada = e.estado_he === 'RECHAZADO' ? heBruta : 0;
    let hePendiente = e.estado_he === 'PENDIENTE' ? heBruta : 0;
    let heTotal = heAprobada; 

    // Colors & helpers
    const isUnderHours = e.horas_trabajadas && e.horas_teoricas && e.horas_trabajadas < e.horas_teoricas;
    const hoursColor = isUnderHours ? 'var(--danger-color, #f43f5e)' : 'var(--text-primary, #1e293b)';
    const rowStyles = "display:flex; justify-content:space-between; margin-bottom:4px; align-items:center;";
    const labelStyles = "color:var(--text-secondary, #64748b); font-weight:500; font-size: 0.75rem;";
    
    const valMins = (mins, activeColor) => {
        if (!mins || mins <= 0) return `<span style="color:var(--text-secondary, #64748b); font-family:monospace; font-size:0.75rem;"></span>`;
        return `<span style="color:${activeColor}; font-family:monospace; font-size:0.75rem; font-weight:700;">${formatExactMinutesToTime(mins)}</span>`;
    };

    // Colación Logic
    const colAuto = e.minutos_colacion_auto || 0;
    const colApli = e.minutos_colacion || 0;
    const colRealMins = e.minutos_colacion_real || 0;
    const colExcesoMins = e.minutos_exceso_colacion || 0;

    const shiftName = e.turno_nombre || (empInfo && empInfo.turno) || 'SIN PROGRAMACIÓN';
    const cycleName = e.etiqueta_bloque || '--';

    // Calculate presence time (Permanencia)
    const rawTimeToMins = (t) => {
        if (!t || typeof t !== 'string') return 0;
        const p = t.split(':');
        const h = parseInt(p[0] || '0', 10);
        const m = parseInt(p[1] || '0', 10);
        const s = parseInt(p[2] || '0', 10);
        return h * 60 + m + s / 60;
    };

    let permProgMins = 0;
    if (e.hora_entrada_teorica && e.hora_salida_teorica) {
        let diff = rawTimeToMins(e.hora_salida_teorica) - rawTimeToMins(e.hora_entrada_teorica);
        if (diff < 0) diff += 1440;
        permProgMins = diff;
    }

    let permRealMins = 0;
    if (e.hora_entrada_real && e.hora_salida_real) {
        let diff = rawTimeToMins(e.hora_salida_real) - rawTimeToMins(e.hora_entrada_real);
        if (diff < 0) diff += 1440;
        permRealMins = diff;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // PROPUESTA 1 - COMPONENTE 1: TIMELINE CRONOLÓGICO DE HITOS (2, 4, 6 MARCAS)
    // ─────────────────────────────────────────────────────────────────────────
    const timelineEvents = [];
    let countPhysicalMarks = 0;

    // 1. Hito Entrada
    if (e.hora_entrada_real) {
        countPhysicalMarks++;
        let diffEntHtml = '';
        if (e.hora_entrada_teorica) {
            const diffMin = rawTimeToMins(e.hora_entrada_real) - rawTimeToMins(e.hora_entrada_teorica);
            if (diffMin > 0.5) {
                diffEntHtml = `<span style="color:#f43f5e; font-weight:700; font-family:monospace; font-size: 0.75rem;">+${formatExactMinutesToTime(diffMin)}</span>`;
            } else if (diffMin < -0.5) {
                diffEntHtml = `<span style="color:#10b981; font-weight:700; font-family:monospace; font-size: 0.75rem;">-${formatExactMinutesToTime(Math.abs(diffMin))}</span>`;
            } else {
                diffEntHtml = `<span style="color:#64748b; font-size: 0.75rem;">En punto</span>`;
            }
        }
        timelineEvents.push({
            tipo: 'ENTRADA',
            hora: e.hora_entrada_real,
            color: '#10b981',
            icon: 'bi-box-arrow-in-right',
            titulo: 'Entrada Turno',
            detalle: diffEntHtml,
            order: rawTimeToMins(e.hora_entrada_real)
        });
    } else if (e.hora_entrada_teorica && (e.estado === 'INASISTENCIA' || e.estado === 'ANOMALIA')) {
        timelineEvents.push({
            tipo: 'ENTRADA_FALTANTE',
            hora: '--:--:--',
            color: '#f43f5e',
            icon: 'bi-exclamation-circle-fill',
            titulo: 'Entrada no registrada',
            detalle: `<span style="color:#f43f5e; font-size: 0.75rem;">Teórica ${e.hora_entrada_teorica.substring(0,5)}</span>`,
            order: 0
        });
    }

    // 2. Hito Colación (Biométrica Real vs Automática)
    const hSalCol = e.hora_salida_colacion || e.hora_inicio_colacion;
    const hEntCol = e.hora_entrada_colacion || e.hora_termino_colacion || e.hora_fin_colacion;
    const hasColReal = (hSalCol && hEntCol) || (colRealMins > 0 && hSalCol);

    if (hasColReal) {
        countPhysicalMarks += (hSalCol ? 1 : 0) + (hEntCol ? 1 : 0);
        let durCol = colRealMins > 0 ? colRealMins : (hSalCol && hEntCol ? Math.max(0, rawTimeToMins(hEntCol) - rawTimeToMins(hSalCol)) : 0);
        let colSub = `${Math.round(durCol)} min`;
        if (colExcesoMins > 0) {
            colSub += ` <span style="color:#f43f5e; font-weight:700;">(+${Math.round(colExcesoMins)}m exceso)</span>`;
        }
        if (hSalCol) {
            timelineEvents.push({
                tipo: 'COLACION_SALIDA',
                hora: hSalCol,
                color: '#f59e0b',
                icon: 'bi-cup-hot',
                titulo: 'Salida a Colación',
                detalle: `<span style="color:#64748b; font-size: 0.75rem;">Inicio</span>`,
                order: rawTimeToMins(hSalCol)
            });
        }
        if (hEntCol) {
            timelineEvents.push({
                tipo: 'COLACION_RETORNO',
                hora: hEntCol,
                color: '#f59e0b',
                icon: 'bi-arrow-return-right',
                titulo: 'Retorno Colación',
                detalle: `<span style="font-family:monospace; font-size: 0.75rem; color:#d97706; font-weight:700;">${colSub}</span>`,
                order: rawTimeToMins(hEntCol)
            });
        }
    } else if (colAuto > 0 && e.hora_entrada_real && e.hora_salida_real) {
        // Descuento automático reglamentario por regla de turno
        timelineEvents.push({
            tipo: 'COLACION_AUTO',
            hora: null,
            color: '#f59e0b',
            icon: 'bi-clock-history',
            titulo: 'Descuento Colación Automática',
            detalle: `<span style="font-family:monospace; font-size: 0.75rem; color:#d97706; font-weight:700;">-${formatExactMinutesToTime(colAuto)} (Regla Turno)</span>`,
            order: rawTimeToMins(e.hora_entrada_real) + 240
        });
    }

    // 3. Hito Permisos Intermedios
    const hIniPer = e.hora_inicio_permiso;
    const hFinPer = e.hora_termino_permiso;
    const durPerMin = e.minutos_permisos_detectados || e.minutos_permiso_personal_deuda || 0;

    if ((e.tiene_permiso || e.tiene_permiso_hora || durPerMin > 0) && (hIniPer || hFinPer)) {
        if (hIniPer) countPhysicalMarks++;
        if (hFinPer) countPhysicalMarks++;
        if (hIniPer) {
            timelineEvents.push({
                tipo: 'PERMISO_SALIDA',
                hora: hIniPer,
                color: '#0284c7',
                icon: 'bi-box-arrow-right',
                titulo: 'Salida a Permiso',
                detalle: `<span style="color:#64748b; font-size: 0.75rem;">Permiso Personal</span>`,
                order: rawTimeToMins(hIniPer)
            });
        }
        if (hFinPer) {
            timelineEvents.push({
                tipo: 'PERMISO_RETORNO',
                hora: hFinPer,
                color: '#0284c7',
                icon: 'bi-box-arrow-in-left',
                titulo: 'Retorno de Permiso',
                detalle: `<span style="font-family:monospace; font-size: 0.75rem; color:#0284c7; font-weight:700;">${durPerMin > 0 ? formatExactMinutesToTime(durPerMin) : 'Retorno'}</span>`,
                order: rawTimeToMins(hFinPer)
            });
        }
    }

    // 4. Hito Salida Turno
    if (e.hora_salida_real) {
        countPhysicalMarks++;
        let diffSalHtml = '';
        if (e.hora_salida_teorica) {
            const diffSalMin = rawTimeToMins(e.hora_salida_real) - rawTimeToMins(e.hora_salida_teorica);
            if (diffSalMin > 0.5) {
                diffSalHtml = `<span style="color:#10b981; font-weight:700; font-family:monospace; font-size: 0.75rem;">+${formatExactMinutesToTime(diffSalMin)}</span>`;
            } else if (diffSalMin < -0.5) {
                diffSalHtml = `<span style="color:#f43f5e; font-weight:700; font-family:monospace; font-size: 0.75rem;">-${formatExactMinutesToTime(Math.abs(diffSalMin))}</span>`;
            } else {
                diffSalHtml = `<span style="color:#64748b; font-size: 0.75rem;">En punto</span>`;
            }
        }
        timelineEvents.push({
            tipo: 'SALIDA',
            hora: e.hora_salida_real,
            color: '#f43f5e',
            icon: 'bi-box-arrow-left',
            titulo: 'Salida Turno',
            detalle: diffSalHtml,
            order: rawTimeToMins(e.hora_salida_real)
        });
    } else if (e.hora_entrada_real && !e.hora_salida_real && e.estado !== 'LIBRE') {
        timelineEvents.push({
            tipo: 'SALIDA_PENDIENTE',
            hora: '--:--:--',
            color: e.estado === 'EN_CURSO' ? '#10b981' : '#f59e0b',
            icon: e.estado === 'EN_CURSO' ? 'bi-play-circle-fill' : 'bi-exclamation-triangle-fill',
            titulo: e.estado === 'EN_CURSO' ? 'Turno en curso' : 'Salida no registrada',
            detalle: `<span style="color:#64748b; font-size: 0.75rem;">Teórica ${e.hora_salida_teorica ? e.hora_salida_teorica.substring(0,5) : '--:--'}</span>`,
            order: 9999
        });
    }

    // Ordenar cronológicamente
    timelineEvents.sort((a, b) => (a.order || 0) - (b.order || 0));

    // Etiqueta de cantidad de marcas
    let marksBadgeText = countPhysicalMarks > 0 ? `${countPhysicalMarks} marcas` : 'Sin marcas';
    if (countPhysicalMarks === 2) marksBadgeText = '2 marcas (Básico)';
    else if (countPhysicalMarks === 4 && hasColReal) marksBadgeText = '4 marcas (Colación Real)';
    else if (countPhysicalMarks >= 6) marksBadgeText = `${countPhysicalMarks} marcas (Permiso + Colación)`;

    // Construcción del HTML del Timeline
    let timelineHtml = '';
    if (timelineEvents.length === 0) {
        timelineHtml = `<div style="text-align:center; color:#94a3b8; font-size:0.75rem; padding:8px;">Sin actividad registrada en la jornada</div>`;
    } else {
        timelineHtml = timelineEvents.map((evt, idx) => {
            const isLast = idx === timelineEvents.length - 1;
            const isAuto = evt.tipo === 'COLACION_AUTO';
            const horaText = evt.hora ? `<strong style="font-family:monospace; font-size:0.75rem; color:var(--text-primary, #1e293b);">${evt.hora}</strong>` : '';
            const borderLeftStyle = isLast ? 'border-left: 2px solid transparent;' : 'border-left: 2px solid #e2e8f0;';
            const bulletBg = isAuto ? 'background: #fef3c7; border: 1px dashed #f59e0b;' : `background: ${evt.color};`;
            const bulletInner = isAuto ? `<i class="bi bi-clock-history" style="font-size: 0.75rem; color:#d97706;"></i>` : '';

            return `
            <div style="position:relative; padding-left:18px; padding-bottom:${isLast ? '0px' : '8px'}; ${borderLeftStyle} margin-left:7px;">
                <span style="position:absolute; left:-6px; top:2px; width:10px; height:10px; border-radius:50%; ${bulletBg} display:flex; align-items:center; justify-content:center; box-shadow:0 0 0 2px #ffffff;">
                    ${bulletInner}
                </span>
                <div style="display:flex; justify-content:space-between; align-items:center; line-height:1.2;">
                    <div style="font-size: 0.75rem; color:var(--text-primary, #1e293b);">
                        ${horaText ? `${horaText} — ` : ''}<span style="${isAuto ? 'color:#b45309; font-weight:600;' : 'font-weight:600;'}">${evt.titulo}</span>
                    </div>
                    <div>${evt.detalle || ''}</div>
                </div>
            </div>`;
        }).join('');
    }

    // ─────────────────────────────────────────────────────────────────────────
    // PROPUESTA 1 - COMPONENTE 2: BARRA DE DISTRIBUCIÓN HORARIA
    // ─────────────────────────────────────────────────────────────────────────
    const minEfectivos = Math.max(0, (e.horas_trabajadas || 0) * 60);
    const minPermiso = durPerMin;
    const minColacion = colApli > 0 ? colApli : (colAuto > 0 ? colAuto : 0);
    const minAtr = e.minutos_atraso || 0;
    const esCambioTurnoDoble = e.observaciones && (e.observaciones.includes("cambio de turno") || e.observaciones.includes("Jornada Turno Tarde") || e.observaciones.includes("Jornada Adicional"));
    const minSad = (e.minutos_salida_adelantada || 0) && !esCambioTurnoDoble ? (e.minutos_salida_adelantada || 0) : 0;
    const minExCol = colExcesoMins;
    const minDeudaNeta = (e.deuda_condonada > 0 || esCambioTurnoDoble) ? 0 : (e.minutos_deuda || 0);

    const minTotalDistribucion = minEfectivos + minPermiso + minColacion + minAtr + minSad;
    let timeBarHtml = '';

    if (minTotalDistribucion > 0) {
        const pctEfect = Math.min(100, Math.max(0, Math.round((minEfectivos / minTotalDistribucion) * 100)));
        const pctPerm  = Math.min(100, Math.max(0, Math.round((minPermiso / minTotalDistribucion) * 100)));
        const pctCol   = Math.min(100, Math.max(0, Math.round((minColacion / minTotalDistribucion) * 100)));
        const pctDeuda = Math.max(0, 100 - pctEfect - pctPerm - pctCol);

        const permBadge = minPermiso > 0 ? `<span style="display:inline-flex; align-items:center; gap:3px; color:#0369a1; font-weight:700;"><span style="width:6px; height:6px; border-radius:50%; background:#0284c7;"></span> ${formatExactMinutesToTime(minPermiso).substring(0,5)}h Perm.</span>` : '';
        const colBadge  = minColacion > 0 ? `<span style="display:inline-flex; align-items:center; gap:3px; color:#b45309;"><span style="width:6px; height:6px; border-radius:50%; background:#f59e0b;"></span> ${Math.round(minColacion)}m Col.</span>` : '';
        const balanceBadge = minDeudaNeta > 0 
            ? `<span style="display:inline-flex; align-items:center; gap:3px; color:#dc2626; font-weight:700;"><span style="width:6px; height:6px; border-radius:50%; background:#f43f5e;"></span> -${formatExactMinutesToTime(minDeudaNeta).substring(0,5)}h Deuda</span>`
            : (heTotal > 0 
                ? `<span style="display:inline-flex; align-items:center; gap:3px; color:#15803d; font-weight:700;"><span style="width:6px; height:6px; border-radius:50%; background:#10b981;"></span> +${formatExactMinutesToTime(heTotal).substring(0,5)}h HE</span>`
                : `<span style="display:inline-flex; align-items:center; gap:3px; color:#15803d; font-weight:700;"><span style="width:6px; height:6px; border-radius:50%; background:#10b981;"></span> Conforme</span>`);

        timeBarHtml = `
        <div style="background: var(--bg-secondary, #f8fafc); border: 1px solid var(--border-color, #e2e8f0); border-radius: 8px; padding: 8px 10px; margin-bottom: 12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; font-size: 0.75rem; font-weight:700; color:var(--text-secondary, #64748b); margin-bottom:6px;">
                <span><i class="bi bi-bar-chart-steps me-1"></i> Distribución de Jornada</span>
                <span style="font-family:monospace; color:var(--text-primary, #1e293b);">${permRealMins > 0 ? formatExactMinutesToTime(permRealMins) : (e.horas_teoricas ? formatDecimalToTime(e.horas_teoricas) : '--:--:--')} Planta</span>
            </div>
            <div style="height:7px; width:100%; background:#e2e8f0; border-radius:9999px; overflow:hidden; display:flex;">
                <div style="background:#10b981; width:${pctEfect}%; height:100%;" title="Trabajo Efectivo: ${formatExactMinutesToTime(minEfectivos)}"></div>
                ${pctPerm > 0 ? `<div style="background:#0284c7; width:${pctPerm}%; height:100%;" title="Permiso: ${formatExactMinutesToTime(minPermiso)}"></div>` : ''}
                ${pctCol > 0 ? `<div style="background:#f59e0b; width:${pctCol}%; height:100%;" title="Colación: ${formatExactMinutesToTime(minColacion)}"></div>` : ''}
                ${pctDeuda > 0 ? `<div style="background:#f43f5e; width:${pctDeuda}%; height:100%;" title="Atraso / Deuda"></div>` : ''}
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; font-size: 0.75rem; font-family:monospace; margin-top:6px;">
                <span style="display:inline-flex; align-items:center; gap:3px; color:#15803d; font-weight:700;"><span style="width:6px; height:6px; border-radius:50%; background:#10b981;"></span> ${formatExactMinutesToTime(minEfectivos).substring(0,5)}h Efect.</span>
                ${permBadge}
                ${colBadge}
                ${balanceBadge}
            </div>
        </div>`;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // PROPUESTA 1 - COMPONENTE 3: BALANCE ARITMÉTICO UNIFICADO (SIN DUPLICIDAD)
    // ─────────────────────────────────────────────────────────────────────────
    let balanceCardHtml = '';
    const progHrsFormatted = e.horas_teoricas ? formatDecimalToTime(e.horas_teoricas) : '--:--:--';

    // Desglose de Horas Extras (si aplica)
    let heBreakdownRows = [];
    if (heBruta > 0) {
        if (!e.horas_teoricas || isFer || e.estado === 'LIBRE' || e.estado === 'JORNADA_ESPECIAL') {
            heBreakdownRows.push(`<div style="${rowStyles}"><span style="${labelStyles}">Día Inhábil/Libre:</span> ${valMins(heBruta, 'var(--success-color, #10b981)')}</div>`);
        } else {
            const timeToMins = (t) => {
                if(!t) return 0;
                let p = t.split(':');
                return parseInt(p[0],10)*60 + parseInt(p[1],10);
            };
            let hr_ent = e.hora_entrada_real;
            let ht_ent = e.hora_entrada_teorica;
            const esAncladoEntrada = e.observaciones && e.observaciones.includes("dentro del anclaje");
            if (hr_ent && ht_ent && !esAncladoEntrada) {
                let diff = timeToMins(ht_ent) - timeToMins(hr_ent);
                if (diff > 720) diff -= 1440;
                if (diff < -720) diff += 1440;
                if (diff > 0) {
                    heBreakdownRows.push(`<div style="${rowStyles}"><span style="${labelStyles}">Ingreso Anticipado:</span> ${valMins(diff, 'var(--success-color, #10b981)')}</div>`);
                }
            }
            let hr_sal = e.hora_salida_real;
            let ht_sal = e.hora_salida_teorica;
            const esAncladoSalida = e.observaciones && e.observaciones.includes("Salida dentro del anclaje");
            if (hr_sal && ht_sal && !esAncladoSalida) {
                let diff = timeToMins(hr_sal) - timeToMins(ht_sal);
                if (diff > 720) diff -= 1440;
                if (diff < -720) diff += 1440;
                if (diff > 0) {
                    heBreakdownRows.push(`<div style="${rowStyles}"><span style="${labelStyles}">Salida Posterior:</span> ${valMins(diff, 'var(--success-color, #10b981)')}</div>`);
                }
            }
            if (heBreakdownRows.length === 0) {
                heBreakdownRows.push(`<div style="${rowStyles}"><span style="${labelStyles}">Ajuste/Excedente:</span> ${valMins(heBruta, 'var(--success-color, #10b981)')}</div>`);
            }
        }
    }

    if (minDeudaNeta > 0) {
        // Tarjeta de Deuda Aritmética Limpia
        let deudaRows = '';
        if (minAtr > 0) {
            deudaRows += `<div style="${rowStyles}"><span style="${labelStyles}">Atraso Entrada:</span> <span style="font-family:monospace; font-weight:700; color:#f43f5e; font-size:0.75rem;">+${formatExactMinutesToTime(minAtr)}</span></div>`;
        }
        if (minExCol > 0) {
            deudaRows += `<div style="${rowStyles}"><span style="${labelStyles}">Exceso Colación:</span> <span style="font-family:monospace; font-weight:700; color:#f43f5e; font-size:0.75rem;">+${formatExactMinutesToTime(minExCol)}</span></div>`;
        }
        if (durPerMin > 0) {
            deudaRows += `<div style="${rowStyles}"><span style="${labelStyles}">Permiso Personal:</span> <span style="font-family:monospace; font-weight:700; color:#0284c7; font-size:0.75rem;">+${formatExactMinutesToTime(durPerMin)}</span></div>`;
        }
        if (minSad > 0) {
            deudaRows += `<div style="${rowStyles}"><span style="${labelStyles}">Salida Anticipada:</span> <span style="font-family:monospace; font-weight:700; color:#f43f5e; font-size:0.75rem;">+${formatExactMinutesToTime(minSad)}</span></div>`;
        }

        // Abono si salió después y compensa parcialmente
        const sumaBrutaInc = minAtr + minSad + minExCol + durPerMin;
        if (sumaBrutaInc > minDeudaNeta + 0.05 && minSad === 0) {
            const abono = sumaBrutaInc - minDeudaNeta;
            deudaRows += `<div style="${rowStyles}"><span style="${labelStyles}">Abono Salida Extendida:</span> <span style="font-family:monospace; font-weight:700; color:#10b981; font-size:0.75rem;">-${formatExactMinutesToTime(abono)}</span></div>`;
        }

        balanceCardHtml = `
        <div style="border: 1px solid rgba(244, 63, 94, 0.25); background-color: rgba(244, 63, 94, 0.04); border-radius: 8px; padding: 10px; margin-bottom: 12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="color:#e11d48; font-weight:800; font-size: 0.6875rem; letter-spacing:0.5px; text-transform:uppercase;">
                    <i class="bi bi-calculator-fill me-1"></i> Balance Horario & Deuda
                </span>
                <span style="font-size: 0.75rem; color:#64748b; font-family:monospace;">Prog. ${progHrsFormatted}</span>
            </div>
            ${deudaRows}
            <div style="margin-top:6px; padding-top:6px; border-top:1px solid rgba(244, 63, 94, 0.2); display:flex; justify-content:space-between; align-items:center;">
                <span style="color:var(--text-primary, #1e293b); font-weight:800; font-size:0.75rem;">Deuda Neta del Día:</span>
                <span style="font-family:monospace; font-weight:800; font-size:0.85rem; color:#e11d48; background:rgba(244,63,94,0.12); padding:2px 8px; border-radius:4px;">
                    ${formatExactMinutesToTime(minDeudaNeta)}
                </span>
            </div>
        </div>`;
    } else if (heTotal > 0 || heBruta > 0) {
        // Tarjeta de Horas Extras
        let heRows = '';
        if (heBruta > 0) heRows += `<div style="${rowStyles}"><span style="${labelStyles}">Bruta / Detectada</span> ${valMins(heBruta, 'var(--success-color, #10b981)')}</div>`;
        if (heAprobada > 0) heRows += `<div style="${rowStyles}"><span style="${labelStyles}">Autorizada</span> ${valMins(heAprobada, 'var(--success-color, #10b981)')}</div>`;
        heRows += `<div style="${rowStyles} padding-top:2px; border-top:1px dashed rgba(16, 185, 129, 0.2);"><span style="${labelStyles} font-weight:700; color:var(--text-primary, #1e293b);">Total Aprobado</span> ${valMins(heTotal, 'var(--success-color, #10b981)')}</div>`;

        let origHtml = heBreakdownRows.length > 0 ? `
            <div style="margin-top:6px; padding-top:6px; border-top:1px dashed rgba(16, 185, 129, 0.2); font-size: 0.75rem;">
                <div style="color:#64748b; font-weight:700; margin-bottom:2px; text-transform:uppercase;">Origen Horas Extras:</div>
                ${heBreakdownRows.join('')}
            </div>` : '';

        balanceCardHtml = `
        <div style="border: 1px solid rgba(16, 185, 129, 0.25); background-color: rgba(16, 185, 129, 0.04); border-radius: 8px; padding: 10px; margin-bottom: 12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="color:#059669; font-weight:800; font-size: 0.6875rem; letter-spacing:0.5px; text-transform:uppercase;">
                    <i class="bi bi-plus-circle-fill me-1"></i> ${(est === 'EXTRA' || est === 'JORNADA_ESPECIAL') ? (stateNameMap[est] || 'HORAS EXTRAS') : 'HORAS EXTRAS'}
                </span>
                <span style="font-size: 0.75rem; color:#059669; font-family:monospace; font-weight:700;">+${formatExactMinutesToTime(heTotal)}</span>
            </div>
            ${heRows}
            ${origHtml}
        </div>`;
    } else if (e.estado === 'OK') {
        balanceCardHtml = `
        <div style="border: 1px solid rgba(16, 185, 129, 0.2); background-color: rgba(16, 185, 129, 0.04); border-radius: 8px; padding: 8px 10px; margin-bottom: 12px; display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#059669; font-weight:700; font-size: 0.75rem; display:flex; align-items:center; gap:4px;">
                <i class="bi bi-check-circle-fill text-success"></i> Jornada Conforme & Cuadrada
            </span>
            <span style="font-family:monospace; font-size: 0.75rem; color:#059669; font-weight:700; background:rgba(16,185,129,0.1); padding:2px 6px; border-radius:4px;">0 Deuda</span>
        </div>`;
    }

    // Alertas especiales del sistema (Bolsa o justificaciones)
    let avisosHtml = '';
    if (e._esDiaJustificadoBolsa && empInfo && empInfo._esBolsaFlag && empInfo._valorTurnoMinBolsa) {
        avisosHtml += `
        <div style="background-color: rgba(2, 132, 199, 0.08); border-left: 3px solid #0284c7; border-radius: 4px; padding: 6px 8px; margin-bottom: 10px; font-size: 0.75rem; color: #0369a1;">
            <i class="bi bi-info-circle-fill me-1"></i> Día justificado: descuenta ${formatExactMinutesToTime(empInfo._valorTurnoMinBolsa)} a la meta mensual.
        </div>`;
    } else if (e.deuda_condonada > 0) {
        avisosHtml += `
        <div style="background-color: rgba(16, 185, 129, 0.08); border-left: 3px solid #10b981; border-radius: 4px; padding: 6px 8px; margin-bottom: 10px; font-size: 0.75rem; color: #047857;">
            <i class="bi bi-shield-check me-1"></i> Deuda del día condonada mediante resolución administrativa.
        </div>`;
    }

    // ── Bloque de Jornada Adicional o Llamados de Emergencia en Tooltip ──
    let bloquesAdicionalesHtml = '';
    
    // 1. Mostrar Jornada Especial Adicional si está inyectada en el registro
    if (e.jornada_adicional) {
        const ja = e.jornada_adicional;
        let estadoLabel = ja.estado;
        let estadoColor = '#64748b'; // gris
        let iconHtml = '<i class="bi bi-clock me-1"></i>';
        
        const esMasDos = (ja.observaciones && ja.observaciones.includes('(+2)')) || (e.observaciones && e.observaciones.includes('(+2)'));
        if (ja.estado === 'PENDIENTE' || ja.estado === 'JORNADA_ESPECIAL') {
            estadoLabel = esMasDos ? 'COBERTURA DE TURNO (+2)' : 'PENDIENTE DE APROBACIÓN';
            estadoColor = '#0284c7'; // celeste / azul
            iconHtml = esMasDos ? '<i class="bi bi-person-fill-check me-1"></i>' : '<i class="bi bi-hourglass-split me-1"></i>';
        } else if (ja.estado === 'EXTRA') {
            estadoLabel = 'APROBADA COMO EXTRA';
            estadoColor = '#16a34a'; // verde
            iconHtml = '<i class="bi bi-check-circle-fill me-1"></i>';
        } else if (ja.estado === 'RECHAZADA') {
            estadoLabel = 'RECHAZADA';
            estadoColor = '#dc2626'; // rojo
            iconHtml = '<i class="bi bi-x-circle-fill me-1"></i>';
        }
        
        const hEntJa = ja.hora_entrada ? ja.hora_entrada.substring(0, 5) : '--:--';
        const hSalJa = ja.hora_salida ? ja.hora_salida.substring(0, 5) : '--:--';
        const duracionJa = ja.minutos_trabajados ? formatExactMinutesToTime(ja.minutos_trabajados) : '--:--';
        const cardTitle = esMasDos ? 'JORNADA ESPECIAL (+2)' : 'JORNADA ADICIONAL';
        
        bloquesAdicionalesHtml += `
        <div style="border: 1px solid ${estadoColor}33; background-color: ${estadoColor}08; border-radius: 6px; padding: 8px; margin-bottom: 12px; text-align: left;">
            <div style="color: ${estadoColor}; font-weight: 700; font-size: 0.6875rem; letter-spacing: 0.5px; text-transform: uppercase; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;">
                <span><i class="bi bi-calendar-plus me-1"></i> ${cardTitle}</span>
                <span style="font-size: 0.6875rem; background-color: ${estadoColor}1a; padding: 1px 6px; border-radius: 4px; border: 1px solid ${estadoColor}33; display: inline-flex; align-items: center; text-transform: uppercase;">${iconHtml}${estadoLabel}</span>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-primary, #1e293b); font-family: monospace;">
                <div>Entrada: <span style="font-weight:700;">${hEntJa}</span></div>
                <div>Salida: <span style="font-weight:700;">${hSalJa}</span></div>
                <div>Duración: <span style="font-weight:700; color: ${estadoColor};">${duracionJa}</span></div>
            </div>
        </div>`;
    }

    // 2. Mostrar Llamado de Emergencia Corto si existe en observaciones. Nombre e ícono salen de Configuración → Estados
    // (LLAMADO_EMERGENCIA), los mismos de la celda de la grilla (dueño, 09-11-2026: un solo ícono, el teléfono).
    if (e.observaciones && e.observaciones.includes('[Llamado de Emergencia:')) {
        const regex = /\[Llamado de Emergencia:\s*([^\]]+)\]/g;
        const emeCfg = (window._estadosAsistencia || {})['LLAMADO_EMERGENCIA'] || {};
        const emeIco = emeCfg.icono_bi || 'bi-telephone-inbound-fill';
        const emeNom = emeCfg.nombre_display || 'Llamado de emergencia';
        let match;
        while ((match = regex.exec(e.observaciones)) !== null) {
            const contenido = match[1]; // ej: "38 min de 03:38 a 04:16"
            bloquesAdicionalesHtml += `
            <div style="border: 1px solid rgba(139, 92, 246, 0.3); background-color: rgba(139, 92, 246, 0.06); border-radius: 6px; padding: 8px; margin-bottom: 12px; text-align: left;">
                <div style="color: #7c3aed; font-weight: 700; font-size: 0.6875rem; letter-spacing: 0.5px; text-transform: uppercase; margin-bottom: 4px;">
                    <i class="bi ${emeIco} me-1" aria-hidden="true"></i> ${emeNom}
                </div>
                <div style="font-size: 0.75rem; color: var(--text-primary, #1e293b); font-weight: 600; line-height: 1.3;">
                    ${contenido}
                </div>
            </div>`;
        }
    }

    // 4. Mostrar Tarjeta Secundaria Dinámica de Jornada Adicional (Doble Turno / Cambio de Ciclo)
    if (e.observaciones && e.observaciones.includes('[Jornada Adicional Pendiente:')) {
        const regexJA = /\[Jornada Adicional Pendiente:\s*([^\]]+)\]/g;
        let matchJA;
        while ((matchJA = regexJA.exec(e.observaciones)) !== null) {
            const fullContent = matchJA[1]; // ej: "15:20:15 - 23:31:01 | Colación: 21:58:28 - 22:08:51 (10 min)"
            const partesPipe = fullContent.split('|');
            const horasRangoStr = partesPipe[0] ? partesPipe[0].trim() : '';
            const colacionInfoStr = partesPipe[1] ? partesPipe[1].trim() : '';

            const partesRango = horasRangoStr.split('-');
            const hEntTarde = partesRango[0] ? partesRango[0].trim() : '--:--';
            const hSalTarde = partesRango[1] ? partesRango[1].trim() : '--:--';
            const colTxt = colacionInfoStr ? colacionInfoStr.replace('Colación:', '').trim() : '-';
            
            let durHrsBadge = '';
            let permFormatted = '--:--';
            if (hEntTarde && hSalTarde && hEntTarde !== '--:--' && hSalTarde !== '--:--') {
                const t1 = typeof _parseHora === 'function' ? _parseHora(hEntTarde) : null;
                const t2 = typeof _parseHora === 'function' ? _parseHora(hSalTarde) : null;
                if (t1 !== null && t2 !== null) {
                    let diffSec = t2 - t1;
                    if (diffSec < 0) diffSec += 86400;
                    const diffMin = diffSec / 60;
                    const hrs = (diffMin / 60).toFixed(1);
                    durHrsBadge = `+${hrs} HRS HE PENDIENTES`;
                    permFormatted = typeof _fmtMin === 'function' ? _fmtMin(diffMin) : `${diffMin} min`;
                }
            }
            
            bloquesAdicionalesHtml += `
            <div style="border: 1px solid rgba(2, 132, 199, 0.4); background-color: rgba(2, 132, 199, 0.06); border-radius: 6px; padding: 10px; margin-bottom: 12px; text-align: left;">
                <div style="color: #0284c7; font-weight: 700; font-size: 0.6875rem; letter-spacing: 0.5px; text-transform: uppercase; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;">
                    <span><i class="bi bi-plus-lg me-1" aria-hidden="true"></i> SEGUNDA JORNADA (+2)</span>
                    ${durHrsBadge ? `<span class="badge bg-primary text-white" style="font-size: 0.75rem; padding: 2px 6px;">${durHrsBadge}</span>` : ''}
                </div>
                <div style="font-size: 0.75rem; color: var(--text-primary, #1e293b); display: flex; flex-direction: column; gap: 4px;">
                    <div style="display:flex; justify-content:space-between; border-bottom:1px dashed #cbd5e1; padding-bottom:3px;">
                        <span style="color:#64748b;">Entrada Real Adicional:</span>
                        <strong style="font-family:monospace; color:#0284c7;">${hEntTarde}</strong>
                    </div>
                    <div style="display:flex; justify-content:space-between; border-bottom:1px dashed #cbd5e1; padding-bottom:3px;">
                        <span style="color:#64748b;">Salida Real Adicional:</span>
                        <strong style="font-family:monospace; color:#0284c7;">${hSalTarde}</strong>
                    </div>
                    ${colTxt && colTxt !== '-' ? `
                    <div style="display:flex; justify-content:space-between; border-bottom:1px dashed #cbd5e1; padding-bottom:3px;">
                        <span style="color:#64748b;">Colación:</span>
                        <strong style="font-family:monospace; color:#475569;">${colTxt}</strong>
                    </div>` : ''}
                    <div style="display:flex; justify-content:space-between; padding-top:2px;">
                        <span style="color:#64748b;">Permanencia / HE:</span>
                        <strong style="font-family:monospace; color:#1e293b;">${permFormatted}${durHrsBadge ? ` (${durHrsBadge})` : ''}</strong>
                    </div>
                </div>
            </div>`;
        }
    }



    // ── Veredicto del día (lo primero que se lee) ────────────────────────────
    let tone = 'neutral', vTitle = stateNameMap[est] || (e.nomenclatura || est), vSub = '';
    const jInfo = e.justificacion || {};
    if (e.justificacion_id && (e.nomenclatura || jInfo.tipo_nombre)) {
        tone = 'info';
        vTitle = jInfo.tipo_nombre || e.nomenclatura;
        const goce = (jInfo.con_goce_sueldo === 0 || jInfo.con_goce_sueldo === false) ? 'sin goce de sueldo' : 'con goce de sueldo';
        vSub = `${goce}${jInfo.pagador ? ' · pagador: ' + jInfo.pagador : ''}`;
    } else if (est === 'INASISTENCIA') {
        tone = 'bad'; vTitle = 'Inasistencia'; vSub = 'Sin marcas ni justificación';
    } else if (est === 'ANOMALIA' || est === 'PENDIENTE') {
        tone = 'warn'; vTitle = 'Marcas incompletas'; vSub = 'Revisar entrada/salida del día';
    } else if (est === 'EN_CURSO') {
        tone = 'ok'; vTitle = 'Turno en curso'; vSub = e.hora_salida_teorica ? `Salida teórica ${e.hora_salida_teorica.substring(0, 5)}` : '';
    } else if (est === 'LIBRE' || est === 'FERIADO') {
        tone = est === 'FERIADO' ? 'warn' : 'neutral';
        vTitle = est === 'FERIADO' ? 'Feriado' : 'Día libre';
        vSub = est === 'FERIADO' ? (feriadoDesc || 'Día no laborable') : 'Asignación automática';
        if (e.jornada_adicional) { tone = 'he'; vTitle = `${vTitle} trabajado`; vSub = 'Con jornada adicional'; }
    } else if (minDeudaNeta > 0) {
        tone = minDeudaNeta >= 30 ? 'bad' : 'warn';
        const solo = minAtr > 0 && minSad === 0 && minExCol === 0 && durPerMin === 0 ? 'Atraso de ' : (minSad > 0 && minAtr === 0 && minExCol === 0 && durPerMin === 0 ? 'Salida anticipada de ' : 'Deuda neta de ');
        vTitle = solo + _tpHuman(minDeudaNeta);
        vSub = `Deuda neta del día · <span class="tp-mono">${formatExactMinutesToTime(minDeudaNeta)}</span>`;
    } else if (heTotal > 0) {
        tone = 'he'; vTitle = `Horas extra · ${_tpHuman(heTotal)}`; vSub = 'Autorizadas en el día';
    } else if (heBruta > 0) {
        tone = 'he'; vTitle = `Horas extra por revisar · ${_tpHuman(heBruta)}`; vSub = e.estado_he ? `Estado: ${e.estado_he}` : 'Detectadas, sin autorizar';
    } else if (est === 'OK') {
        tone = 'ok'; vTitle = 'Jornada conforme'; vSub = 'Sin deuda';
    } else if (est === 'SALIDA_ADELANTADA' || est === 'ATRASO' || est === 'ATR_SAD') {
        tone = 'warn';
    } else if (est === 'EXTRA' || est === 'JORNADA_ESPECIAL') {
        tone = 'he'; vSub = e.jornada_adicional ? 'Jornada adicional' : '';
    }
    if (e.deuda_condonada > 0 && minDeudaNeta === 0 && tone !== 'info') { vSub = (vSub ? vSub + ' · ' : '') + 'deuda condonada'; }

    // ── Línea de tiempo turno teórico vs. real ───────────────────────────────
    let stripHtml = '';
    const okStrip = e.hora_entrada_real && e.hora_salida_real && e.hora_entrada_teorica && e.hora_salida_teorica;
    if (okStrip) {
        const base = rawTimeToMins(e.hora_entrada_teorica);
        const norm = (t, floor) => { let x = rawTimeToMins(t) - base; if (x < floor) x += 1440; return x; };
        const ps = 0, pe = norm(e.hora_salida_teorica, 1);
        const rs = norm(e.hora_entrada_real, -720), re = norm(e.hora_salida_real, rs + 1);
        const lo = Math.min(ps, rs) - 25, hi = Math.max(pe, re) + 25, span = Math.max(1, hi - lo);
        const L = (x) => (((x - lo) / span) * 100).toFixed(2);
        const W = (a, b) => (((b - a) / span) * 100).toFixed(2);
        const dEnt = rs - ps, dSal = re - pe;
        const lab = (d) => (Math.abs(d) < 0.5 ? '' : ` <span style="opacity:.7">${d > 0 ? '+' : '−'}${Math.round(Math.abs(d))}m</span>`);
        stripHtml = `
        <div class="tp-sec"><div class="tp-lab"><span>Jornada vs. turno</span><span class="tp-mono" style="text-transform:none">${e.hora_entrada_teorica.substring(0,5)}–${e.hora_salida_teorica.substring(0,5)}</span></div>
            <div class="tp-tl"><div class="r"></div>
                <div class="p" style="left:${L(ps)}%;width:${W(ps, pe)}%"></div>
                ${dEnt > 0.5 ? `<div class="a" style="left:${L(ps)}%;width:${W(ps, rs)}%"></div>` : ''}
                <div class="w" style="left:${L(Math.max(rs, ps))}%;width:${W(Math.max(rs, ps), re)}%"></div>
                <i style="left:${L(rs)}%;--d:${dEnt > 0.5 ? '#f59e0b' : '#10b981'}"></i><i style="left:${L(re)}%;--d:${dSal < -0.5 ? '#f43f5e' : '#10b981'}"></i>
                <u style="left:${L(rs)}%;color:${dEnt > 0.5 ? '#a35a00' : '#0f7a4f'}">${e.hora_entrada_real.substring(0,5)}${lab(dEnt)}</u>
                <u style="left:${L(re)}%;color:${dSal < -0.5 ? '#b3261e' : '#0f7a4f'}">${e.hora_salida_real.substring(0,5)}${lab(dSal)}</u>
            </div>
            <div class="tp-key"><b style="background:#d5e0f7"></b>turno teórico &nbsp; <b style="background:#10b981"></b>trabajado${dEnt > 0.5 ? ' &nbsp; <b style="background:#f59e0b"></b>atraso' : ''}</div>
        </div>`;
    }
    // Eventos: con la línea de tiempo solo se listan los intermedios (colación, permisos); sin ella, todos
    const evList = (okStrip ? timelineEvents.filter(t => t.tipo !== 'ENTRADA' && t.tipo !== 'SALIDA') : timelineEvents).filter(t => t.tipo !== 'COLACION_AUTO');
    const evHtml = evList.length ? evList.map(t => `<div class="tp-ev"><span><i class="bi ${t.icon}" style="color:${t.color}"></i> ${t.hora ? `<strong>${t.hora}</strong> — ` : ''}${t.titulo}</span><span>${t.detalle || ''}</span></div>`).join('') : '';
    const evSection = evHtml ? `<div class="tp-sec"><div class="tp-lab"><span>${okStrip ? 'Intermedias' : 'Trazabilidad de jornada'}</span><span style="text-transform:none">${marksBadgeText}</span></div>${evHtml}</div>`
        : (!okStrip ? `<div class="tp-sec" style="color:#94a3b8;text-align:center">Sin actividad registrada en la jornada</div>` : '');

    // ── KPIs ────────────────────────────────────────────────────────────────
    let kpiHtml = '';
    const tieneMarcas = !!(e.hora_entrada_real || e.hora_salida_real || hasColReal);
    if (tieneMarcas || minEfectivos > 0 || minDeudaNeta > 0 || heTotal > 0) {
        const third = minDeudaNeta > 0 ? `<div><span>Deuda</span><b style="color:#b3261e">${formatExactMinutesToTime(minDeudaNeta).substring(0, 5)}</b><em>neta del día</em></div>`
            : heTotal > 0 ? `<div><span>Horas extra</span><b style="color:#6d28d9">${formatExactMinutesToTime(heTotal).substring(0, 5)}</b><em>autorizadas</em></div>`
            : `<div><span>Programadas</span><b>${progHrsFormatted.substring(0, 5)}</b><em>del turno</em></div>`;
        kpiHtml = `<div class="tp-sec"><div class="tp-kp">
            <div><span>Efectivo</span><b>${formatExactMinutesToTime(minEfectivos).substring(0, 5)}</b><em>trabajado</em></div>
            <div><span>Colación</span><b style="color:#b45309">${minColacion > 0 && tieneMarcas ? Math.round(minColacion) + ' min' : '—'}</b><em>${hasColReal ? 'marcada' : (colAuto > 0 ? 'automática' : '')}</em></div>
            ${third}</div>
            <div class="tp-chips">${marksBadgeText ? `<span class="tp-chip">${marksBadgeText}</span>` : ''}${colAuto > 0 && !hasColReal && tieneMarcas ? '<span class="tp-chip">Descuento colación automático</span>' : ''}${e.deuda_condonada > 0 ? '<span class="tp-chip good">Deuda condonada</span>' : ''}${permBadgeChip(durPerMin)}</div></div>`;
    }
    function permBadgeChip(m) { return m > 0 ? `<span class="tp-chip">Permiso ${Math.round(m)} min</span>` : ''; }

    const extras = [avisosHtml, balanceCardHtml, bloquesAdicionalesHtml].filter(Boolean).join('');
    const html = `
    <div class="tp tp-${tone}">
        <div class="tp-hd">
            <div class="tp-top"><span><i class="bi bi-calendar3 me-1"></i>${dateFormatted}</span>${badgeHtml}</div>
            <div class="tp-v">${vTitle}${vSub ? `<small>${vSub}</small>` : ''}</div>
            <div class="tp-nm">${empName}</div>
            <div class="tp-sub">${empAreaText} · ${shiftName}${cycleName && cycleName !== '--' ? ' · ' + cycleName : ''}</div>
            ${isFer && est !== 'FERIADO' ? `<div class="tp-fer"><i class="bi bi-star-fill me-1"></i>${feriadoDesc}</div>` : ''}
        </div>
        ${stripHtml}
        ${kpiHtml}
        ${evSection}
        ${extras ? `<div class="tp-sec">${extras}</div>` : ''}
        <div class="tp-ft"><span class="tp-kb"><kbd>Clic</kbd> acciones</span><span class="tp-kb"><kbd>2 clics</kbd> justificar</span><span class="tp-touch"><kbd>Toque</kbd> acciones · <kbd>2 toques</kbd> justificar</span><span class="tp-kb"><kbd>Shift</kbd> fijar</span><span class="tp-touch">Mantén pulsado: detalle completo</span></div>
    </div>`;

    return _escAttr(html);
}

// Arma el HTML del tooltip de una celda bajo demanda (hover). Cachea el último por celda.
function _getCellTipHtml(td) {
    if (td._tipHtml) return td._tipHtml;
    const legacy = td.getAttribute('data-bs-content');   // compatibilidad con celdas antiguas
    if (legacy) return legacy;
    const reg = window.__mxTipReg && window.__mxTipReg.get(td.getAttribute('data-tip'));
    if (!reg) return '';
    const escaped = _buildRichTooltipData(reg.di, reg.d, reg.dt, reg.feriadoDesc, reg.isWE, reg.emp);
    // _buildRichTooltipData devuelve el HTML escapado para atributo; aquí se necesita el HTML real
    td._tipHtml = escaped.replace(/&quot;/g, '"').replace(/&#39;/g, "'");
    if (window.mxVelTip) td._tipHtml = window.mxVelTip(td, td._tipHtml);   // pie con la velocidad (solo en la lámina Velocidad)
    return td._tipHtml;
}

function _escAttr(html) {
    return html.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ============================================================
// NUEVA LÓGICA UNIFICADA DE CONDONACIÓN MASIVA
// Reemplaza: promptCondonacionDeuda, toggleCondonacionDeuda, executeCondonacion
// También reemplaza: executePerdonazoMasivo (marcaciones_manuales.js)
// ============================================================

/**
 * Ejecuta la condonación o revocación para una lista de empleados y rango de fechas.
 * @param {number[]} empleadosIds - IDs de empleados a procesar
 * @param {string} fechaInicio - Fecha inicio (YYYY-MM-DD)
 * @param {string} fechaFin - Fecha fin (YYYY-MM-DD)
 * @param {number} tipo - 0=Revocar, 1=Salida, 2=Atraso, 3=Ambos
 * @param {Function} [onSuccess] - Callback opcional tras éxito
 */
window.executeCondonacionMasiva = async function(empleadosIds, fechaInicio, fechaFin, tipo, onSuccess, confirmar) {
    if (!empleadosIds || empleadosIds.length === 0) return;
    tipo = parseInt(tipo, 10);
    const isRevoke = tipo === 0;

    try {
        const payload = {
            empleados_ids: empleadosIds.map(id => parseInt(id, 10)),
            fecha_inicio: fechaInicio,
            fecha_fin: fechaFin,
            tipo_condonacion: tipo,
            confirmar: !!confirmar
        };
        const response = await fetch('/api/asistencia/condonar-deuda/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${window.AuthToken || localStorage.getItem('access_token')}`
            },
            body: JSON.stringify(payload)
        });

        if (response.status === 409) {
            // El libro de minutos dice que esa deuda ya está cubierta con horas extra: perdonarla no cambia el saldo
            // y solo esconde el cruce. Se avisa y la persona decide (regla del dueño, 25-10-2026).
            const errData = await response.json().catch(() => ({}));
            const det = errData.detail || {};
            const avisos = Array.isArray(det.avisos) ? det.avisos : [];
            const lista = avisos.map(a => `<li>${a.texto || a.mensaje || ('<b>' + (a.nombre || ('Empleado ' + a.empleado_id)) + '</b>: la deuda de esos días ya está cubierta con horas extra')}</li>`).join('');
            const r = await Swal.fire({
                icon: 'question',
                title: 'Esa deuda ya está cubierta',
                html: `<div class="text-start small">Las horas extra del tramo ya cubren la deuda de los días elegidos. Un perdonazo no cambia el saldo y deja esas horas extra «no pagadas».<ul class="mt-2 mb-2">${lista}</ul>Si quieres decidir qué se paga, usa <b>Cuadre del tramo</b> (doble clic en la fila).</div>`,
                showCancelButton: true,
                confirmButtonText: 'Perdonar igual',
                cancelButtonText: 'No perdonar',
                confirmButtonColor: '#6b7280'
            });
            if (!r.isConfirmed) return;
            return window.executeCondonacionMasiva(empleadosIds, fechaInicio, fechaFin, tipo, onSuccess, true);
        }

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            const det = errData.detail;
            throw new Error((typeof det === 'string' ? det : (det && (det.mensaje || det.codigo))) || 'Error al procesar la condonación');
        }

        const result = await response.json();
        const cuenta = result.registros_procesados || empleadosIds.length;
        const accion = isRevoke ? 'revocada' : 'condonada';
        const tipotxt = { 0:'(Revocar)', 1:'Salida Adelantada', 2:'Atraso', 3:'Atraso + Salida', 5:'Cierre de Turno / Ausencia Condonada' }[tipo] || '';

        Swal.fire({
            icon: isRevoke ? 'warning' : 'success',
            title: isRevoke ? 'Condonación Revocada' : 'Perdonazo aplicado',
            html: `<b>${cuenta}</b> registro(s) ${accion}.<br><small class="text-muted">${tipotxt}</small>`,
            timer: 2500,
            showConfirmButton: false
        });

        // Cerrar panel lateral si estuviese abierto
        cerrarPanelPerdonazo();
        // Cerrar popovers del tooltip
        document.querySelectorAll('.popover').forEach(p => p.remove());
        // Desactivar modo switch perdonazo y limpiar selecciones
        _perdonazoState.seleccionados.clear();
        if (onSuccess) onSuccess();
        // Refresco forzado desde API (fix bug raíz)
        if (typeof window.loadMarcacionesData === 'function') {
            window.loadMarcacionesData();
        } else {
            location.reload();
        }

    } catch (error) {
        console.error('Error executeCondonacionMasiva:', error);
        Swal.fire('Error', error.message, 'error');
    }
};




// Accesibilidad: las celdas de la matriz se abren también con Enter o Espacio.
document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const td = e.target && e.target.closest ? e.target.closest('td.cell-clickable') : null;
    if (!td || e.target !== td) return;
    e.preventDefault();
    td.click();
});


// ── Íconos por cargo en la grilla de asistencia ─────────────────────────────────────────────────────────
// Una familia de líneas (24px, trazo 1.7, puntas redondas) en una pastilla tintada por categoría. El cargo viene
// del empleado; si no calza con ninguna categoría se muestra la silueta genérica. El detalle va en el tooltip.
const CARGO_ICONOS = {
    chofer:     { nombre: 'Chofer',          svg: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.4"/><path d="M3.4 10.6 9.7 11.3M20.6 10.6 14.3 11.3M12 14.4V21"/>' },
    peoneta:    { nombre: 'Peoneta',         svg: '<path d="M5.5 3v14.8h8.7"/><rect x="9.6" y="6.6" width="10.4" height="11.2" rx="1.7"/><path d="M9.6 12.2H20"/><circle cx="9.2" cy="20.6" r="1.5"/>' },
    bodega:     { nombre: 'Bodega',          svg: '<path d="M3 10.2 12 4l9 6.2V20H3Z"/><path d="M8 20v-6.2h8V20M8 16.9h8"/>' },
    produccion: { nombre: 'Producción',      svg: '<path d="M3 20.5h18M5 20.5V10.2l5 3.3v-3.3l5 3.3V4.5h4v16"/><path d="M8.2 17.4h1.4M13.2 17.4h1.4"/>' },
    mantencion: { nombre: 'Mantención',      svg: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>' },
    supervisor: { nombre: 'Jefatura',        svg: '<path d="m12 3.2 2.6 5.3 5.8.85-4.2 4.1 1 5.8L12 16.5l-5.2 2.75 1-5.8-4.2-4.1 5.8-.85L12 3.2Z"/>' },
    calidad:    { nombre: 'Calidad / Lab.',  svg: '<path d="M9.4 3.2h5.2M10.5 3.2v5.9L5.1 18.3A1.9 1.9 0 0 0 6.7 21h10.6a1.9 1.9 0 0 0 1.6-2.7L13.5 9.1V3.2"/><path d="M7.7 14.8h8.6"/>' },
    ventas:     { nombre: 'Ventas',          svg: '<path d="M3 12.2V4.5A1.5 1.5 0 0 1 4.5 3h7.7a1.5 1.5 0 0 1 1.06.44l7.3 7.3a1.5 1.5 0 0 1 0 2.12l-7.7 7.7a1.5 1.5 0 0 1-2.12 0l-7.3-7.3A1.5 1.5 0 0 1 3 12.2Z"/><circle cx="8" cy="8" r="1.3"/>' },
    admin:      { nombre: 'Administración',  svg: '<rect x="5" y="4.5" width="14" height="16.5" rx="2.2"/><path d="M9 4.5V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v.5M8.6 11h6.8M8.6 15h4.4"/>' },
    seguridad:  { nombre: 'Seguridad',       svg: '<path d="M12 3 4.6 6v5.4c0 4.6 3 8.2 7.4 9.6 4.4-1.4 7.4-5 7.4-9.6V6L12 3Z"/><path d="m9 12 2.2 2.2L15.2 10"/>' },
    otro:       { nombre: '',                svg: '<circle cx="12" cy="8" r="3.6"/><path d="M4.6 20.5c.8-3.9 3.8-6 7.4-6s6.6 2.1 7.4 6"/>' }
};
const CARGO_REGLAS = [
    ['chofer',     /chofer|conductor/],
    ['peoneta',    /peoneta|acompanante|ayudante de (reparto|camion)/],
    ['supervisor', /supervis|jefe|jefa|gerent|encargad|coordinad|director|lider|subgerent/],
    ['calidad',    /calidad|laborator|quimic/],
    ['mantencion', /mantenc|mecanic|electric|tecnico|soldad|gasfit|reparac/],
    ['bodega',     /bodeg|almacen|despach|inventar|logistic|grua|horquill/],
    ['produccion', /operador|operario|produccion|llenad|envas|maquin|etiquet|planta|cocin|mezcl|armador/],
    ['seguridad',  /guardia|porter|seguridad|vigilan|prevenc/],
    ['ventas',     /vendedor|ventas|comercial|ejecutiv|marketing/],
    ['admin',      /administ|asistente|secretar|contab|analista|rrhh|recursos humanos|finanz|compras|adquis|oficina|tesorer|abogad|sistemas|informat/]
];
function categoriaCargo(cargo) {
    const t = String(cargo || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    for (const [cat, re] of CARGO_REGLAS) { if (re.test(t)) return cat; }
    return 'otro';
}
function cargoIconoHtml(cargo) {
    const cat = categoriaCargo(cargo);
    const def = CARGO_ICONOS[cat];
    const etiqueta = String(cargo || '').trim() || 'Sin cargo';
    const esc = etiqueta.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    return `<span class="emp-cargo-ico cg-${cat}" role="img" aria-label="Cargo: ${esc}" title="${esc}"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${def.svg}</svg></span>`;
}
window.cargoIconoHtml = cargoIconoHtml;
window.categoriaCargo = categoriaCargo;

// ── Filtros recordados y entrada suave: se enganchan al pintado de la grilla sin tocar su cuerpo ───────
(function () {
    const original = renderVistaAnalitica;
    renderVistaAnalitica = function () {
        const r = original.apply(this, arguments);
        try { mxGuardarFiltros(); mxPintarChips(); mxTrasPintar(arguments[1]); if (window.mxVelAsegurar) window.mxVelAsegurar(arguments[1]); } catch (e) { console.warn('filtros/animación:', e); }
        return r;
    };
})();
