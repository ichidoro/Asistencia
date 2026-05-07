/**
 * Visor de Asignaciones de Horarios
 * Rediseñado para mostrar nombres completos y filtrado por área independiente.
 * v2: Agrega filtro por Turno / Horario con dropdown dinámico.
 */

// Estado local
let asignacionesInitialized = false;
// Cache de los datos cargados (para re-filtrar en cliente sin nueva petición al API)
let _asignacionesDataCache = [];
let _asignacionesMonthCache = null;
let _asignacionesYearCache = null;

document.addEventListener('DOMContentLoaded', () => {
    initAsignacionesUI();
});

function initAsignacionesUI() {
    console.log("📋 Inicializando Visor de Asignaciones...");

    // Configurar selectores de fecha con mes/año actual
    const now = new Date();
    const monthSelect = document.getElementById('asignaciones-month');
    const yearInput = document.getElementById('asignaciones-year');

    if (monthSelect && yearInput) {
        monthSelect.value = now.getMonth() + 1;
        yearInput.value = now.getFullYear();
    }

    // Escuchar el click en la pestaña (Bootstrap 5)
    const tabBtn = document.getElementById('asignaciones-tab-emp');
    if (tabBtn) {
        tabBtn.addEventListener('shown.bs.tab', () => {
            if (!asignacionesInitialized) {
                loadAsignacionesAreas();
                loadAsignacionesTurnos();
                loadAsignacionesMatrix();
                asignacionesInitialized = true;
            }
        });
    }
}

async function loadAsignacionesAreas() {
    const areaSelect = document.getElementById('asignaciones-area');
    if (!areaSelect) return;

    try {
        const resp = await fetch('/api/empleados/stats/'); // Reutilizamos para traer áreas
        if (resp.ok) {
            const data = await resp.json();
            if (data.areas) {
                let html = '<option value="">Todas las Áreas</option>';
                data.areas.sort((a, b) => a.area.localeCompare(b.area)).forEach(item => {
                    html += `<option value="${item.area}">${item.area}</option>`;
                });
                areaSelect.innerHTML = html;
            }
        }
    } catch (err) {
        console.error("Error cargando áreas para asignaciones:", err);
    }
}

/**
 * Carga turnos en el dropdown filtrado por área (cascada).
 * area='' → todos los turnos | area='SEGURIDAD' → solo turnos de ese área + globales
 */
async function loadAsignacionesTurnos(area = '') {
    const select = document.getElementById('asignaciones-turno');
    if (!select) return;

    // Indicador de carga
    select.innerHTML = '<option value="">Cargando turnos...</option>';
    select.disabled = true;

    try {
        let url = area ? `/api/turnos/?area=${encodeURIComponent(area)}` : '/api/turnos/';
        const resp = await fetch(url);
        const lista = resp.ok ? await resp.json() : [];

        if (!lista || lista.length === 0) {
            select.innerHTML = '<option value="">Sin turnos para esta área</option>';
            return;
        }

        select.innerHTML = '<option value="">Todos los Turnos</option>' +
            lista
                .sort((a, b) => a.nombre.localeCompare(b.nombre))
                .map(t => `<option value="${t.id}">${t.nombre}</option>`)
                .join('');
    } catch (err) {
        console.error("Error cargando turnos para filtro:", err);
        select.innerHTML = '<option value="">Error al cargar</option>';
    } finally {
        select.disabled = false;
    }
}

/**
 * Llamado SOLO cuando cambia el Área — actualiza turnos en cascada y luego la matriz.
 */
async function onAsignacionesAreaChange() {
    const area = document.getElementById('asignaciones-area')?.value || '';

    // 1. Resetear turno seleccionado
    const turnoSelect = document.getElementById('asignaciones-turno');
    if (turnoSelect) turnoSelect.value = '';

    // 2. Recargar dropdown de turnos filtrado por área (cascada)
    await loadAsignacionesTurnos(area);

    // 3. Recargar la matriz con los nuevos filtros
    await loadAsignacionesMatrix();
}

async function loadAsignacionesMatrix() {
    const month = document.getElementById('asignaciones-month').value;
    const year = document.getElementById('asignaciones-year').value;
    const area = document.getElementById('asignaciones-area').value;
    const turnoFiltro = document.getElementById('asignaciones-turno')?.value || '';

    const container = document.getElementById('asignaciones-matrix-body');
    if (!container) return;

    // Si cambia mes/año/área debemos recargar desde API.
    // Si solo cambia el turno, reutilizamos el cache y filtramos en cliente.
    const needsApiCall = (
        month !== _asignacionesMonthCache ||
        year !== _asignacionesYearCache ||
        area !== (_asignacionesAreaCache || '')
    );

    if (needsApiCall) {
        container.innerHTML = `<tr><td colspan="32" class="text-center py-5">
            <span class="spinner-border spinner-border-sm text-primary"></span> 
            Resolviendo matriz de horarios...
        </td></tr>`;

        try {
            let url = `/api/turnos/asignaciones/matrix/?month=${month}&year=${year}`;
            if (area) url += `&area=${encodeURIComponent(area)}`;

            const resp = await fetch(url);
            if (!resp.ok) throw new Error("Error API");

            _asignacionesDataCache = await resp.json();
            _asignacionesMonthCache = month;
            _asignacionesYearCache = year;
            _asignacionesAreaCache = area;
        } catch (err) {
            console.error("Error loadAsignacionesMatrix:", err);
            container.innerHTML = `<tr><td colspan="32" class="text-center py-5 text-danger">⚠️ Error: ${err.message}</td></tr>`;
            return;
        }
    }

    // Filtrar en cliente por turno si hay selección
    let dataToRender = _asignacionesDataCache;
    if (turnoFiltro) {
        const turnoId = parseInt(turnoFiltro);
        dataToRender = _asignacionesDataCache.filter(emp =>
            emp.dias.some(dia => dia.turno && dia.turno.id === turnoId)
        );
    }

    renderAsignacionesMatrix(dataToRender, month, year, turnoFiltro);
}

// Variable de caché de área (no declarada con let arriba para ser compatible con el cierre)
let _asignacionesAreaCache = '';

function renderAsignacionesMatrix(data, month, year, turnoFiltro = '') {
    const headersRow = document.getElementById('asignaciones-matrix-headers');
    const body = document.getElementById('asignaciones-matrix-body');
    const legend = document.getElementById('asignaciones-legend');

    if (!headersRow || !body) return;

    // 1. Headers (Días)
    const numDays = new Date(year, month, 0).getDate();
    let headerHtml = `<th class="sticky-col">Empleado</th>`;

    const dayNames = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];

    for (let d = 1; d <= numDays; d++) {
        const dateObj = new Date(year, month - 1, d);
        const dayName = dayNames[dateObj.getDay()];
        const isWeekend = dateObj.getDay() === 0 || dateObj.getDay() === 6;

        // Formatear fecha como dd-mm-yyyy
        const day = String(d).padStart(2, '0');
        const monthStr = String(month).padStart(2, '0');
        const dateStr = `${day}-${monthStr}-${year}`;

        headerHtml += `<th style="background: ${isWeekend ? '#f8fafc' : ''}; text-align: center; font-size: 10px;">
            <div style="font-weight: 600;">${dateStr}</div>
            <small style="color: #64748b;">${dayName}</small>
        </th>`;
    }
    headersRow.innerHTML = headerHtml;

    // 2. Body (Asignaciones con nombres completos)
    if (data.length === 0) {
        const msg = turnoFiltro
            ? `No hay empleados asignados a este turno en el periodo seleccionado.`
            : `No hay datos para este filtro.`;
        body.innerHTML = `<tr><td colspan="${numDays + 1}" class="text-center py-4 text-muted">
            <i class="bi bi-search me-1"></i>${msg}
        </td></tr>`;
        return;
    }

    const turnosInMatrix = new Map();
    const turnoIdFiltro = turnoFiltro ? parseInt(turnoFiltro) : null;
    let bodyHtml = "";

    data.forEach(emp => {
        bodyHtml += `<tr>`;
        bodyHtml += `<td class="sticky-col">
            <div class="fw-bold text-uppercase" style="font-size: 11px;">${emp.nombre}</div>
            <div class="text-muted" style="font-size: 9px;">${emp.area}</div>
        </td>`;

        emp.dias.forEach(dia => {
            const turno = dia.turno;
            let cellContent = `<span class="turno-empty text-muted" style="opacity:0.3">•</span>`;

            if (turno) {
                // Usar (id % 9) como índice de color — estable sin importar filtros
                const colorIdx = (turno.id % 9);
                const classColor = `t-color-${colorIdx}`;

                // Mostrar el rango horario del día si está disponible, sino el nombre del turno
                const displayLabel = turno.horario || turno.nombre;
                const isLibre = displayLabel === "LIBRE";

                // Resaltar la celda si coincide con el turno filtrado
                // IMPORTANTE: usar outline en lugar de box-shadow inset para evitar
                // que el azul del highlight se mezcle visualmente con el color de fondo.
                const isHighlighted = turnoIdFiltro && turno.id === turnoIdFiltro;
                const isNotMatch   = turnoIdFiltro && !isHighlighted;

                const highlightStyle = isHighlighted
                    ? 'outline: 2px solid #2563eb; outline-offset: -2px;'
                    : '';
                const dimStyle = isNotMatch ? 'opacity: 0.35;' : '';

                cellContent = `
                    <div class="turno-badge-cell ${classColor} ${isLibre ? 'opacity-75' : ''}" 
                         title="${turno.nombre}" 
                         style="width: 100%; height: auto; padding: 4px 2px; font-size: 9px; line-height: 1; ${highlightStyle} ${dimStyle}">
                        ${displayLabel}
                    </div>
                `;


                if (!turnosInMatrix.has(turno.id)) {
                    turnosInMatrix.set(turno.id, { nombre: turno.nombre, class: classColor });
                }
            }

            bodyHtml += `<td>${cellContent}</td>`;
        });

        bodyHtml += `</tr>`;
    });
    body.innerHTML = bodyHtml;

    // 3. Leyenda consolidada
    if (legend) {
        let legendHtml = "<strong>Turnos detectados:</strong>";
        [...turnosInMatrix.values()].sort((a, b) => a.nombre.localeCompare(b.nombre)).forEach((info) => {
            legendHtml += `
                <div class="d-flex align-items-center gap-1">
                    <div class="turno-badge-cell ${info.class}" style="width: auto; height: 20px; font-size: 9px; padding: 0 8px;">
                        ${info.nombre}
                    </div>
                </div>
            `;
        });
        legend.innerHTML = legendHtml;
    }
}
