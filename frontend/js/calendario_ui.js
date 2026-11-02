// calendario_ui.js - Gestión de Feriados Nacionales y Personalizados

const API_CALENDARIO = '/api/configuracion/feriados/';

// Estado local
let feriadosList = [];
let currentYear = new Date().getFullYear();

// ==========================================
// INICIALIZACIÓN
// ==========================================
function initCalendarioUI() {
    console.log("Inicializando UI de Calendario...");

    // Listener para el tab de calendario si es necesario
    const tabBtn = document.getElementById('calendario-tab');
    if (tabBtn) {
        tabBtn.addEventListener('shown.bs.tab', () => {
            loadFeriados();
        });
    }
}

async function loadFeriados() {
    const container = document.getElementById('calendario-container');
    if (!container) return;

    try {
        const response = await fetch(`${API_CALENDARIO}?year=${currentYear}`);
        if (!response.ok) throw new Error("Error al cargar feriados");

        feriadosList = await response.json();
        renderCalendario();
    } catch (error) {
        console.error(error);
        showToast("No se pudieron cargar los feriados.", "error");
    }
}

function renderCalendario() {
    // Diseño B (02-11-2026): feriados del año a la izquierda y su ficha a la derecha; uno nuevo se crea en la ficha.
    const container = document.getElementById('calendario-container');
    if (!container || !window.FichaCfg) return;
    const F = window.FichaCfg;
    const canEdit = F.puede('configuracion.editar');
    const ddmm = function (iso) { return String(iso || '').slice(8, 10) + '-' + String(iso || '').slice(5, 7); };
    const largo = function (iso) {
        const d = new Date(iso + 'T00:00:00');
        const t = d.toLocaleDateString('es-CL', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
        return t.charAt(0).toUpperCase() + t.slice(1);
    };
    F.montar(container, {
        clave: 'calendario',
        titulo: 'Calendario ' + currentYear,
        descripcion: 'Feriados del año. Un día feriado no se cuenta como inasistencia y lo trabajado ese día es jornada especial.',
        acciones: '<span class="fcB-seg" role="group" aria-label="Año"><button type="button" onclick="changeCalendarYear(-1)" aria-label="Año anterior"><i class="bi bi-chevron-left" aria-hidden="true"></i></button>'
            + '<button type="button" class="on" aria-pressed="true" disabled>' + currentYear + '</button>'
            + '<button type="button" onclick="changeCalendarYear(1)" aria-label="Año siguiente"><i class="bi bi-chevron-right" aria-hidden="true"></i></button></span>'
            + (canEdit ? '<button type="button" class="fcB-btn" onclick="syncChileHolidays()"><i class="bi bi-arrow-repeat" aria-hidden="true"></i>Traer feriados de Chile</button>'
                + '<button type="button" class="fcB-btn pri" onclick="FichaCfg.nuevo(\'calendario\')"><i class="bi bi-plus-lg" aria-hidden="true"></i>Nuevo feriado</button>' : ''),
        items: feriadosList.slice().sort(function (a, b) { return String(a.fecha).localeCompare(String(b.fecha)); }),
        id: function (x) { return x.id; },
        etiqueta: function (x) { return x.descripcion; },
        sub: function (x) { return ddmm(x.fecha); },
        vacio: 'No hay feriados para ' + currentYear + '. Use «Traer feriados de Chile» para cargar los oficiales.',
        ficha: function (x, panel) {
            if (!x) {
                panel.innerHTML = F.cabeza('Nuevo feriado', 'Para un feriado que no está en la lista oficial, por ejemplo uno regional.')
                    + F.campo('Fecha', '<input type="date" class="fcB-inp" style="max-width:200px" id="fcal-fecha" value="' + currentYear + '-01-01">', '', 'fcal-fecha')
                    + F.campo('Descripción', F.texto('fcal-desc', '', ' placeholder="Ej: Día de la Región"'), '', 'fcal-desc')
                    + F.pie('', '<button type="button" class="fcB-btn" id="fcal-descartar">Descartar</button><button type="button" class="fcB-btn pri" id="fcal-guardar">Guardar feriado</button>');
                panel.querySelector('#fcal-descartar').onclick = function () { const p = feriadosList[0]; F.elegir('calendario', p ? String(p.id) : null); };
                panel.querySelector('#fcal-guardar').onclick = function (ev) {
                    const fecha = panel.querySelector('#fcal-fecha').value, descripcion = panel.querySelector('#fcal-desc').value.trim();
                    if (!fecha || !descripcion) { showToast('Faltan datos. Escriba la fecha y la descripción.', 'warning'); return; }
                    F.trabajando(ev.currentTarget, async function () {
                        const r = await fetch(API_CALENDARIO, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fecha: fecha, descripcion: descripcion }) });
                        if (!r.ok) { showToast('No se guardó el feriado.', 'danger'); return; }
                        showToast('Listo. Feriado guardado.', 'success');
                        const d = await r.json().catch(function () { return {}; });
                        if (d && d.id) F.recordar('calendario', d.id);
                        if (Number(fecha.slice(0, 4)) !== currentYear) currentYear = Number(fecha.slice(0, 4));
                        await loadFeriados();
                    });
                };
                return;
            }
            panel.innerHTML = F.cabeza(x.descripcion, largo(x.fecha))
                + F.campo('Fecha', '<span class="num">' + F.esc(window.formatFechaDDMMYYYY ? window.formatFechaDDMMYYYY(x.fecha) : x.fecha) + '</span>')
                + F.campo('Origen', '<span>' + (x.es_nacional ? 'Feriado oficial de Chile' : 'Agregado a mano') + '</span>')
                + (canEdit ? F.pie('<button type="button" class="fcB-btn borra" onclick="deleteFeriado(' + x.id + ')"><i class="bi bi-trash3" aria-hidden="true"></i>Eliminar feriado</button>', '') : '');
        }
    });
}

function changeCalendarYear(delta) {
    currentYear += delta;
    loadFeriados();
}

async function syncChileHolidays() {
    // Buscar el botón que disparó el evento
    const btn = document.querySelector('button[onclick="syncChileHolidays()"]');
    const originalHtml = btn.innerHTML;

    // UI Feedback: Spinner y desactivar
    if (btn) {
        btn.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Sincronizando...`;
        btn.disabled = true;
    }

    showToast("Trayendo los feriados de Chile…", "info");

    try {
        const response = await fetch(`${API_CALENDARIO}sync/${currentYear}/`, { method: 'POST' });
        if (!response.ok) throw new Error("Error en sincronización");

        const data = await response.json();
        showToast(`Listo. Se trajeron ${data.count} feriados.`, "success");
        loadFeriados();
    } catch (error) {
        console.error(error);
        showToast("No se pudieron traer los feriados. Revise internet y vuelva a intentarlo.", "error");
    } finally {
        // Restaurar botón
        if (btn) {
            btn.innerHTML = originalHtml;
            btn.disabled = false;
        }
    }
}

async function deleteFeriado(id) {
    if (!await uiConfirm('¿Eliminar este feriado?', { items: ['Los días de ese feriado se vuelven a calcular como día normal.'], confirmText: 'Eliminar feriado', danger: true })) return;

    try {
        const response = await fetch(`${API_CALENDARIO}${id}/`, { method: 'DELETE' });
        if (!response.ok) throw new Error("Error al eliminar");

        showToast("Listo. Feriado eliminado.", "success");
        loadFeriados();
    } catch (error) {
        console.error(error);
        showToast("No se pudo eliminar el feriado.", "error");
    }
}

// Inyectar al cargar
document.addEventListener('DOMContentLoaded', () => {
    initCalendarioUI();
});

// Feriado manual: una ventana con la fecha (selector de fecha) y la descripción
async function openModalFeriado() {
    const datos = await uiPedir({
        titulo: 'Nuevo feriado',
        confirmText: 'Guardar feriado',
        campos: [
            { nombre: 'fecha', etiqueta: 'Fecha', tipo: 'date', valor: `${currentYear}-01-01`, requerido: true },
            { nombre: 'descripcion', etiqueta: 'Descripción', tipo: 'text', ayuda: 'Ej: Día de la Independencia', requerido: true }
        ]
    });
    if (!datos) return;
    const { fecha, descripcion } = datos;

    try {
        const response = await fetch(API_CALENDARIO, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fecha, descripcion })
        });

        if (!response.ok) throw new Error("Error al guardar");

        showToast("Listo. Feriado guardado.", "success");
        loadFeriados();
    } catch (error) {
        console.error(error);
        showToast("No se guardó el feriado.", "error");
    }
}
