// cumpleanos_ui.js - Gestión de Cumpleaños de Empleados

const API_CUMPLEANOS = '/api/empleados/cumpleanos/';

// Estado local
let bdayList = [];
let currentBdayArea = '';
let currentBdayMonth = new Date().getMonth() + 1; // Por defecto mes actual
let currentBdayView = 'list'; // 'list' o 'grid'

function initCumpleanosUI() {
    console.log("🚀 Inicializando UI de Cumpleaños...");

    const tabBtn = document.getElementById('cumpleanos-tab-emp');
    if (tabBtn) {
        tabBtn.addEventListener('shown.bs.tab', () => {
            loadAllBirthdays();
        });
    }

    // Cargar el widget si estamos en dashboard
    const widget = document.getElementById('cumpleanos-mes-widget');
    if (widget) {
        loadMonthlyBirthdays();
    }
}

/**
 * Carga los cumpleaños del mes actual para el widget superior
 * Separa cumpleaños de HOY vs resto del mes
 */
async function loadMonthlyBirthdays() {
    const listHoy = document.getElementById('cumpleanos-hoy-list');
    const listMes = document.getElementById('cumpleanos-mes-list');
    const widget = document.getElementById('cumpleanos-mes-widget');

    if (!listHoy || !listMes || !widget) return;

    try {
        const month = new Date().getMonth() + 1;
        const today = new Date().getDate();
        const response = await fetch(`${API_CUMPLEANOS}?month=${month}`);
        if (!response.ok) throw new Error("Error API");

        const data = await response.json();

        if (data.length > 0) {
            // Separar cumpleaños de HOY vs resto
            const hoy = data.filter(e => {
                const day = parseInt(e.fecha_nacimiento.substring(8, 10));
                return day === today;
            });

            const resto = data.filter(e => {
                const day = parseInt(e.fecha_nacimiento.substring(8, 10));
                return day !== today;
            });

            // Renderizar cumpleaños de HOY
            if (hoy.length > 0) {
                listHoy.innerHTML = hoy.map(e =>
                    `<div class="mb-1">🎉 <strong>${e.apellido_paterno} ${e.apellido_materno || ''} ${e.nombre}</strong></div>`
                ).join('');
            } else {
                listHoy.innerHTML = '<span class="text-muted fst-italic">✨ Hoy no hay celebraciones, pero pronto habrá motivos para festejar</span>';
            }

            // Renderizar cumpleaños del MES con fecha completa
            const monthNames = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

            if (resto.length > 0) {
                listMes.innerHTML = resto.map(e => {
                    const day = e.fecha_nacimiento.substring(8, 10);
                    const monthIdx = parseInt(e.fecha_nacimiento.substring(5, 7)) - 1;
                    const year = e.fecha_nacimiento.substring(0, 4);
                    return `<div class="mb-1"><strong>${day} ${monthNames[monthIdx]} ${year}</strong>: ${e.apellido_paterno} ${e.apellido_materno || ''} ${e.nombre}</div>`;
                }).join('');
            } else {
                listMes.innerHTML = '<span class="text-muted fst-italic">Solo hay cumpleaños hoy</span>';
            }

            widget.classList.remove('d-none');
        } else {
            widget.classList.add('d-none'); // Ocultar si no hay nada
        }
    } catch (error) {
        console.error("Error cargando widget cumpleaños:", error);
    }
}

/**
 * Carga todos los cumpleaños con filtros
 */
async function loadAllBirthdays() {
    const container = document.getElementById('cumpleanos-list-container');
    if (!container) return;

    container.innerHTML = `
        <div class="text-center py-5">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="mt-2 text-muted">Explorando constelación de celebraciones...</p>
        </div>
    `;

    try {
        let params = new URLSearchParams();
        if (currentBdayArea) params.append('area', currentBdayArea);
        if (currentBdayMonth && currentBdayMonth !== 'todo') params.append('month', currentBdayMonth);

        const response = await fetch(`${API_CUMPLEANOS}?${params.toString()}`);
        if (!response.ok) throw new Error("Error loading birthdays");

        bdayList = await response.json();

        if (currentBdayView === 'grid') {
            renderCelebrationUniverse();
        } else {
            renderBirthdaysTable();
        }
    } catch (error) {
        console.error(error);
        if (typeof showToast === 'function') showToast("Error al cargar cumpleaños", "error");
    }
}

function switchBdayView(mode) {
    currentBdayView = mode;

    // UI Feedback
    const btnList = document.getElementById('btn-bday-list');
    const btnGrid = document.getElementById('btn-bday-grid');

    if (mode === 'grid') {
        btnGrid.classList.add('active');
        btnList.classList.remove('active');
        renderCelebrationUniverse();
    } else {
        btnList.classList.add('active');
        btnGrid.classList.remove('active');
        renderBirthdaysTable();
    }
}

function renderBirthdaysTable() {
    const container = document.getElementById('cumpleanos-list-container');
    if (!container) return;

    const monthsNames = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

    let html = renderBdayFilters(monthsNames);

    html += `
        <div class="table-responsive card border-0 shadow-sm animate__animated animate__fadeIn">
            <table class="table table-hover align-middle mb-0">
                <thead class="bg-light">
                    <tr>
                        <th style="width: 150px;">Fecha</th>
                        <th>Empleado</th>
                        <th>Área / Cargo</th>
                        <th class="text-center">Edad</th>
                    </tr>
                </thead>
                <tbody>
    `;

    if (bdayList.length === 0) {
        html += `<tr><td colspan="4" class="text-center py-5 text-muted">No se encontraron celebraciones.</td></tr>`;
    } else {
        bdayList.forEach(e => {
            const dateStr = e.fecha_nacimiento;
            const mIdx = parseInt(dateStr.substring(5, 7)) - 1;
            const day = dateStr.substring(8, 10);
            const isToday = (mIdx === new Date().getMonth() && parseInt(day) === new Date().getDate());

            html += `
                <tr class="${isToday ? 'table-warning' : ''}">
                    <td><span class="fw-bold">${day} ${monthsNames[mIdx]}</span></td>
                    <td>
                        <div class="fw-bold">${e.nombre_completo || (e.apellido_paterno + ' ' + (e.apellido_materno || '') + ' ' + e.nombre)}</div>
                        <small class="text-muted">${e.rut}</small>
                    </td>
                    <td><span class="badge bg-light text-dark border">${e.area || '-'}</span></td>
                    <td class="text-center">${e.fecha_nacimiento ? (new Date().getFullYear() - parseInt(dateStr.substring(0, 4))) : '-'}</td>
                </tr>
            `;
        });
    }

    html += `</tbody></table></div>`;
    container.innerHTML = html;
    syncFiltersUI();
}

function renderCelebrationUniverse() {
    const container = document.getElementById('cumpleanos-list-container');
    if (!container) return;

    const monthsNames = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

    // Determinar qué estamos mostrando
    const isFiltered = (currentBdayMonth && currentBdayMonth !== 'todo');
    const displayTitle = isFiltered ? `Celebraciones de ${monthsNames[currentBdayMonth - 1]}` : "Universo Anual de Celebraciones";

    let html = renderBdayFilters(monthsNames);

    html += `
        <div class="celebration-universe animate__animated animate__fadeIn">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h4 class="fw-bold text-dark mb-0">${displayTitle}</h4>
                <span class="badge bg-white text-primary shadow-sm px-3 py-2 rounded-pill">
                    ${bdayList.length} Personas
                </span>
            </div>
            <div class="celebration-grid">
    `;

    if (bdayList.length === 0) {
        html += `
            <div class="col-12 text-center py-5">
                <div class="display-1 mb-3">✨</div>
                <h5 class="text-muted">No hay alineaciones estelares este mes.</h5>
                <p class="small text-muted">Intenta cambiar el filtro de área o mes.</p>
            </div>
        `;
    } else {
        bdayList.forEach((e, index) => {
            const dateStr = e.fecha_nacimiento;
            const mIdx = parseInt(dateStr.substring(5, 7)) - 1;
            const day = dateStr.substring(8, 10);
            const isToday = (mIdx === new Date().getMonth() && parseInt(day) === new Date().getDate());

            // Lógica innovadora: Icono dinámico según mes
            const icons = ["❄️", "❤️", "🍀", "🌸", "☀️", "🏝️", "⛱️", "🌴", "🍎", "🎃", "🍂", "🎄"];
            const icon = icons[mIdx];

            html += `
                <div class="bday-card-innovative ${isToday ? 'is-today' : ''}" style="--item-index: ${index}">
                    <div class="bday-card-icon">${icon}</div>
                    <div class="bday-card-info">
                        <div class="bday-card-date">${day} ${monthsNames[mIdx].substring(0, 3)}</div>
                        <div class="bday-card-name text-truncate" title="${e.nombre_completo || (e.apellido_paterno + ' ' + (e.apellido_materno || '') + ' ' + e.nombre).trim()}">
                            ${e.nombre.split(' ')[0]} ${e.apellido_paterno}
                        </div>
                        <div class="bday-card-meta">
                            <i class="bi bi-briefcase-fill me-1"></i> ${e.cargo || 'Staff'}
                            <br>
                            <i class="bi bi-geo-alt-fill me-1"></i> ${e.area || 'General'}
                        </div>
                    </div>
                </div>
            `;
        });
    }

    html += `</div></div>`;
    container.innerHTML = html;
    syncFiltersUI();
}

function renderBdayFilters(monthsNames) {
    return `
        <div class="card border-0 shadow-sm mb-4">
            <div class="card-body p-3">
                <div class="row g-3 align-items-end">
                    <div class="col-md-5">
                        <label for="bday-month-filter" class="form-label small fw-bold text-muted">Mes</label>
                        <select class="form-select" id="bday-month-filter" onchange="filterBdaysByMonth(this.value)">
                            <option value="todo">Vista General (Todos)</option>
                            ${monthsNames.map((m, i) => `<option value="${i + 1}" ${currentBdayMonth == (i + 1) ? 'selected' : ''}>${m}</option>`).join('')}
                        </select>
                    </div>
                    <div class="col-md-5">
                        <label for="bday-area-filter" class="form-label small fw-bold text-muted">Área</label>
                        <select class="form-select" id="bday-area-filter" onchange="filterBdaysByArea(this.value)">
                            <option value="">Todas las Áreas</option>
                            ${getUniqueAreasFromList()}
                        </select>
                    </div>
                    <div class="col-md-2 text-end">
                        <button class="btn btn-primary w-100" onclick="loadAllBirthdays()">
                            <i class="bi bi-arrow-clockwise"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function syncFiltersUI() {
    if (document.getElementById('bday-month-filter')) document.getElementById('bday-month-filter').value = currentBdayMonth || 'todo';
    if (document.getElementById('bday-area-filter')) document.getElementById('bday-area-filter').value = currentBdayArea || '';
}

function getUniqueAreasFromList() {
    const areas = [...new Set(bdayList.map(e => e.area).filter(a => a))].sort();
    return areas.map(a => `<option value="${a}" ${currentBdayArea === a ? 'selected' : ''}>${a}</option>`).join('');
}

function filterBdaysByArea(area) {
    currentBdayArea = area;
    loadAllBirthdays();
}

function filterBdaysByMonth(month) {
    currentBdayMonth = month;
    loadAllBirthdays();
}

// Inyectar al cargar
document.addEventListener('DOMContentLoaded', () => {
    initCumpleanosUI();
});
