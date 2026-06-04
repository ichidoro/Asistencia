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
        showToast("Error al cargar feriados", "error");
    }
}

function renderCalendario() {
    const container = document.getElementById('calendario-container');
    if (!container) return;

    let html = `
        <div class="d-flex justify-content-between align-items-center mb-4">
            <div>
                <h5 class="mb-0 fw-bold">Calendario Laboral ${currentYear}</h5>
                <p class="small text-muted mb-0">Gestión de días no laborables y feriados legales de Chile.</p>
            </div>
            <div class="d-flex gap-2">
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-secondary" onclick="changeCalendarYear(-1)">◀</button>
                    <button class="btn btn-outline-secondary disabled fw-bold">${currentYear}</button>
                    <button class="btn btn-outline-secondary" onclick="changeCalendarYear(1)">▶</button>
                </div>
                <button class="btn btn-info btn-sm text-white" onclick="syncChileHolidays()">
                    <i class="bi bi-arrow-repeat"></i> Sincronizar Chile
                </button>
                <button class="btn btn-primary btn-sm" onclick="openModalFeriado()">
                    <i class="bi bi-plus-circle"></i> Nuevo Feriado
                </button>
            </div>
        </div>

        <div class="table-responsive card border-0 shadow-sm">
            <table class="table table-hover align-middle mb-0">
                <thead class="table-light">
                    <tr>
                        <th style="width: 150px;">Fecha</th>
                        <th>Descripción</th>
                        <th style="width: 120px;">Tipo</th>
                        <th style="width: 100px;">Acciones</th>
                    </tr>
                </thead>
                <tbody>
    `;

    if (feriadosList.length === 0) {
        html += `
            <tr>
                <td colspan="4" class="text-center py-5 text-muted">
                    <div class="opacity-50 mb-2" style="font-size: 2rem;">🗓️</div>
                    No hay feriados registrados para este año.<br>
                    <button class="btn btn-link btn-sm" onclick="syncChileHolidays()">Sincronizar feriados oficiales de Chile</button>
                </td>
            </tr>
        `;
    } else {
        feriadosList.forEach(f => {
            const dateObj = new Date(f.fecha + 'T00:00:00');
            const dateStr = dateObj.toLocaleDateString('es-CL', { day: '2-digit', month: 'long', weekday: 'long' });

            html += `
                <tr>
                    <td class="fw-bold text-primary">${window.formatFechaDDMMYYYY(f.fecha)}</td>
                    <td>
                        <div class="fw-bold">${f.descripcion}</div>
                        <div class="small text-muted">${dateStr}</div>
                    </td>
                    <td>
                        <span class="badge ${f.es_nacional ? 'bg-info text-white' : 'bg-warning text-dark'}">
                            ${f.es_nacional ? 'Nacional' : 'Manual'}
                        </span>
                    </td>
                    <td>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteFeriado(${f.id})">
                            <i class="bi bi-trash"></i>
                        </button>
                    </td>
                </tr>
            `;
        });
    }

    html += `
                </tbody>
            </table>
        </div>
    `;

    container.innerHTML = html;
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

    showToast("Conectando con el servicio de feriados de Chile...", "info");

    try {
        const response = await fetch(`${API_CALENDARIO}sync/${currentYear}/`, { method: 'POST' });
        if (!response.ok) throw new Error("Error en sincronización");

        const data = await response.json();
        showToast(`${data.count} feriados sincronizados correctamente`, "success");
        loadFeriados();
    } catch (error) {
        console.error(error);
        showToast("No se pudo sincronizar los feriados. Verifique su conexión.", "error");
    } finally {
        // Restaurar botón
        if (btn) {
            btn.innerHTML = originalHtml;
            btn.disabled = false;
        }
    }
}

async function deleteFeriado(id) {
    if (!confirm("¿Eliminar este feriado?")) return;

    try {
        const response = await fetch(`${API_CALENDARIO}${id}/`, { method: 'DELETE' });
        if (!response.ok) throw new Error("Error al eliminar");

        showToast("Feriado eliminado", "success");
        loadFeriados();
    } catch (error) {
        console.error(error);
        showToast("Error al eliminar feriado", "error");
    }
}

// Inyectar al cargar
document.addEventListener('DOMContentLoaded', () => {
    initCalendarioUI();
});

// Función básica para Feriado Manual (Simple prompt por ahora)
async function openModalFeriado() {
    const fecha = prompt("Ingrese la fecha (YYYY-MM-DD):", `${currentYear}-01-01`);
    if (!fecha) return;

    const descripcion = prompt("Descripción del feriado:");
    if (!descripcion) return;

    try {
        const response = await fetch(API_CALENDARIO, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fecha, descripcion })
        });

        if (!response.ok) throw new Error("Error al guardar");

        showToast("Feriado guardado", "success");
        loadFeriados();
    } catch (error) {
        console.error(error);
        showToast("Error al guardar feriado", "error");
    }
}
