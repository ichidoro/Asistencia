// horarios.js - Gestión de Horarios y Turnos

const API_TURNOS = '/api/turnos/'; // Relativo

// Estado local
let turnosList = [];
let currentTurnoId = null; // Para edición

// ==========================================
// INICIALIZACIÓN
// ==========================================
function initHorarios() {
    // [FIX] Si el contenedor ya existe, no reinicializar todo para evitar parpadeo
    if (document.getElementById('horarios-view')) {
        console.log("📅 Módulo Horarios ya está cargado. Omitiendo renderizado completo.");
        
        // Solo recargar la tabla de turnos si NO hay un modal abierto (para no interrumpir edición)
        const modalEl = document.getElementById('modalTurno');
        const isModalOpen = modalEl && (modalEl.classList.contains('show') || modalEl.style.display === 'block');
        
        if (!isModalOpen) {
            loadTurnos();
        }
        return;
    }

    console.log("Inicializando módulo Horarios...");
    renderHorariosUI();
    loadTurnos();
}

// ==========================================
// API CALLS
// ==========================================
async function loadTurnos() {
    try {
        const response = await fetch(API_TURNOS);
        if (!response.ok) throw new Error("Error cargando turnos");
        turnosList = await response.json();
        renderTurnosTable();
    } catch (error) {
        console.error(error);
        alert("Error al cargar listado de turnos");
    }
}

window.sortTurnos = function (key) {
    TableSorter.sort(turnosList, key, 'turnos');
    renderTurnosTable();
};

async function saveTurno() {
    const form = document.getElementById('formTurno');
    const formData = new FormData(form);

    // Build object
    const turno = {
        nombre: formData.get('nombre'),
        tipo_programacion: formData.get('tipo_programacion'),
        tolerancia_retraso_alerta: parseInt(formData.get('tolerancia_retraso_alerta')),
        tolerancia_retraso_descuento: parseInt(formData.get('tolerancia_retraso_descuento')),
        redondeo_minutos: parseInt(formData.get('redondeo_minutos') || 0),
        meta_horas_semanales: 0, // Se actualizará abajo
        hora_limite_ficticia: formData.get('hora_limite_ficticia') || null,
        descuento_colacion_auto: !!document.getElementById('chkColacion').checked,
        minutos_colacion_auto: document.getElementById('chkColacion').checked ? (parseInt(document.getElementById('numColacion').value) || 0) : 0,
        anclaje_entrada_minutos: parseInt(formData.get('anclaje_entrada_minutos') || 0),
        anclaje_salida_minutos: parseInt(formData.get('anclaje_salida_minutos') || 0),
        es_turno_cortado: !!document.getElementById('chkCortado').checked,
        areas: Array.from(document.querySelectorAll('.chk-area-turno:checked')).map(cb => cb.value),
        dias: []
    };

    if (turno.areas.length === 0) {
        alert("Debe seleccionar al menos un área para el turno.");
        return;
    }

    // Collect weeks
    const weekContainers = document.querySelectorAll('.week-container');
    let totalHoras = 0;

    weekContainers.forEach((container, wIdx) => {
        const numSemana = wIdx + 1;
        const rows = container.querySelectorAll('.dias-input-body tr');
        const etiquetaInput = container.querySelector('.etiqueta-input');
        const etiquetaValor = etiquetaInput ? etiquetaInput.value : null;

        rows.forEach(row => {
            const chkLibre = row.querySelector('.chk-libre');
            const isLibre = chkLibre.checked;
            const horasVal = parseFloat(row.querySelector('.hours-calc').value) || 0;
            const horas = isLibre ? 0 : horasVal;
            if (numSemana === 1) totalHoras += horas; // Para meta_horas_semanales en Fijo

            turno.dias.push({
                num_semana: numSemana,
                dia_semana: parseInt(row.dataset.day),
                etiqueta_bloque: etiquetaValor,
                es_libre: isLibre,
                horas_teoricas: horas,
                hora_entrada: isLibre ? null : row.querySelector('.time-in').value,
                hora_salida: isLibre ? null : row.querySelector('.time-out').value,
                cruza_medianoche: row.querySelector('.chk-cruce').checked,
                hora_entrada_2: isLibre || !turno.es_turno_cortado ? null : row.querySelector('.time-in-2').value,
                hora_salida_2: isLibre || !turno.es_turno_cortado ? null : row.querySelector('.time-out-2').value,
                cruza_medianoche_2: !turno.es_turno_cortado ? false : row.querySelector('.chk-cruce-2').checked
            });
        });
    });

    if (turno.tipo_programacion === 'FLEXIBLE_BOLSA') {
        const metaInputObj = document.getElementById('input-meta-bolsa');
        turno.meta_horas_semanales = metaInputObj ? parseFloat(metaInputObj.value) || 176 : 176;
    } else {
        turno.meta_horas_semanales = totalHoras;
    }

    try {
        let url = API_TURNOS;
        let method = 'POST';

        if (currentTurnoId) {
            url += `${currentTurnoId}/`;
            method = 'PUT';
        }

        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(turno)
        });

        if (!response.ok) throw new Error("Error guardando turno");

        await loadTurnos();
        closeModalHorario();
        showNotification(currentTurnoId ? "Turno actualizado" : "Turno creado", "success");

    } catch (error) {
        console.error(error);
        alert("Error al guardar: " + error.message);
    }
}

async function deleteTurno(id) {
    if (!confirm("¿Estás seguro de eliminar este turno? Esta acción no se puede deshacer.")) return;

    try {
        const response = await fetch(`${API_TURNOS}${id}/`, { method: 'DELETE' });
        if (!response.ok) throw new Error("Error al eliminar");

        await loadTurnos();
        showNotification("Turno eliminado", "success");
    } catch (error) {
        console.error(error);
        alert("Error eliminando turno: " + error.message);
    }
}

// ==========================================
// UI HELPERS
// ==========================================
async function openModalHorario(id = null) {
    currentTurnoId = id;
    const modalTitle = document.getElementById('modalTurnoLabel');
    const form = document.getElementById('formTurno');

    if (modalTitle) modalTitle.textContent = id ? "Editar Turno" : "Nuevo Turno";

    if (id) {
        // Cargar datos
        const turno = turnosList.find(t => t.id === id);
        if (turno) {
            // Llenar cabecera
            form.nombre.value = turno.nombre;
            form.tipo_programacion.value = turno.tipo_programacion;
            form.tolerancia_retraso_alerta.value = turno.tolerancia_retraso_alerta;
            form.tolerancia_retraso_descuento.value = turno.tolerancia_retraso_descuento;
            form.redondeo_minutos.value = String(turno.redondeo_minutos || 0);
            if (form.anclaje_entrada_minutos) form.anclaje_entrada_minutos.value = String(turno.anclaje_entrada_minutos || 0);
            if (form.anclaje_salida_minutos) form.anclaje_salida_minutos.value = String(turno.anclaje_salida_minutos || 0);
            if (form.hora_limite_ficticia) form.hora_limite_ficticia.value = turno.hora_limite_ficticia || "09:00";
            
            // Cargar áreas (soporta nuevo modelo areas: List[str] o fallback antiguo area: str)
            let areasToSelect = turno.areas || [];
            if (turno.area && areasToSelect.length === 0) areasToSelect = [turno.area];
            await populateAreaSelect(areasToSelect);

            const inputMetaBol = document.getElementById('input-meta-bolsa');
            if (inputMetaBol) inputMetaBol.value = turno.tipo_programacion === 'FLEXIBLE_BOLSA' ? turno.meta_horas_semanales : 176;

            const chkColacion = document.getElementById('chkColacion');
            chkColacion.checked = turno.descuento_colacion_auto;
            document.getElementById('numColacion').value = turno.minutos_colacion_auto || 30;
            toggleColacionInput();

            // Llenar Semanas
            const dias_agrupados = {};
            turno.dias.forEach(d => {
                if (!dias_agrupados[d.num_semana]) dias_agrupados[d.num_semana] = [];
                dias_agrupados[d.num_semana].push(d);
            });

            const numSemanas = Object.keys(dias_agrupados).length || 1;
            // [FIX] setupModalListeners ahora NO llama handleTipoProgramacionChange internamente
            setupModalListeners(numSemanas);

            Object.entries(dias_agrupados).forEach(([sem, dias]) => {
                const container = document.getElementById(`week-container-${sem}`);
                if (!container) return;
                
                // Cargar etiqueta_bloque
                const etiquetaInput = container.querySelector('.etiqueta-input');
                if (etiquetaInput && dias.length > 0 && dias[0].etiqueta_bloque) {
                    etiquetaInput.value = dias[0].etiqueta_bloque;
                    document.getElementById(`pill-week-${sem}-tab`).innerText = dias[0].etiqueta_bloque;
                }

                const rows = container.querySelectorAll('.dias-input-body tr');

                dias.forEach(d => {
                    const row = rows[d.dia_semana];
                    if (row) {
                        const chkLibre = row.querySelector('.chk-libre');
                        chkLibre.checked = d.es_libre;
                        row.querySelector('.time-in').value = d.hora_entrada || "08:00";
                        row.querySelector('.time-out').value = d.hora_salida || "18:00";
                        row.querySelector('.chk-cruce').checked = d.cruza_medianoche;
                        if (row.querySelector('.time-in-2')) {
                            row.querySelector('.time-in-2').value = d.hora_entrada_2 || "14:00";
                            row.querySelector('.time-out-2').value = d.hora_salida_2 || "18:00";
                            row.querySelector('.chk-cruce-2').checked = d.cruza_medianoche_2;
                        }
                        row.querySelector('.hours-calc').value = d.horas_teoricas;
                        toggleDiaRow(chkLibre);
                    }
                });
            });

            // [FIX] Setear chkCortado ANTES de llamar handleTipoProgramacionChange (una sola vez al final)
            document.getElementById('chkCortado').checked = turno.es_turno_cortado;
            // Aplicar visibilidad de bloques del turno cortado directamente (sin llamar toggleCortadoUI
            // que volvería a llamar handleTipoProgramacionChange antes de tiempo)
            const isCortado = turno.es_turno_cortado;
            const cols = document.querySelectorAll('.col-bloque-2');
            cols.forEach(c => {
                c.style.display = isCortado ? '' : 'none';
                c.style.visibility = 'visible';
            });
            // [FIX] UNA SOLA llamada al final para aplicar toda la visibilidad de tipo programación
            handleTipoProgramacionChange();
        }
    } else {
        form.reset();
        document.getElementById('chkColacion').checked = false;
        document.getElementById('numColacion').value = 30;
        toggleColacionInput();
        // [FIX] setupModalListeners NO llama handleTipoProgramacionChange - llamar aquí una sola vez
        setupModalListeners();
        handleTipoProgramacionChange();
        await populateAreaSelect([]);
    }

    // Limpiar instancia Bootstrap anterior antes de mostrar el modal.
    // getOrCreateInstance sobre un modal que ya tiene .show activo provoca
    // que la animación 'fade' se re-aplique, generando el CLS de 60+.
    const modalEl = document.getElementById('modalTurno');
    const existingInstance = bootstrap.Modal.getInstance(modalEl);
    if (existingInstance) {
        existingInstance.dispose();
    }
    const modalInstance = new bootstrap.Modal(modalEl, { backdrop: true, keyboard: true });
    modalInstance.show();
}


/**
 * Puebla el contenedor de áreas del turno con las áreas disponibles en el sistema.
 */
async function populateAreaSelect(selectedAreas = []) {
    const container = document.getElementById('container-areas-turno');
    if (!container) return;

    // Intentar obtener áreas de la API
    let areas = [];
    try {
        const resp = await fetch('/api/empleados/areas/');
        if (resp.ok) {
            areas = await resp.json();
        }
        
        // Si no hay áreas locales (e.g. primera instalación o DB limpia), hacer fallback a BioAlba
        if (!areas || areas.length === 0) {
            console.warn("No hay áreas locales, intentando cargar desde BioAlba...");
            const respBioAlba = await fetch('/api/sync/areas-preview/');
            if (respBioAlba.ok) {
                areas = await respBioAlba.json();
            }
        }
        
        areas.sort();
    } catch (e) { 
        console.error("Error cargando áreas para turno desde API, intentando fallback", e);
        if (window.allEmployeesBulk && window.allEmployeesBulk.length > 0) {
            areas = [...new Set(window.allEmployeesBulk.map(e => e.area).filter(a => a))].sort();
        } else {
            try {
                const resp = await fetch('/api/empleados/search/?limit=500&activo=true');
                const data = await resp.json();
                const emps = data.empleados || data.items || data;
                if (Array.isArray(emps)) {
                    areas = [...new Set(emps.map(e => e.area).filter(a => a))].sort();
                }
            } catch (e2) {
                console.error("Fallo definitivo al cargar áreas", e2);
            }
        }
    }

    // Inyección de salvaguarda para áreas que ya tenía asignadas pero no están en la lista actual
    selectedAreas.forEach(sa => {
        if (!areas.includes(sa)) {
            areas.push(sa);
        }
    });
    areas.sort();

    if (areas.length === 0) {
        container.innerHTML = '<div class="text-center text-muted small py-2">No hay áreas disponibles</div>';
        return;
    }

    const html = areas.map((a, i) => {
        const isChecked = selectedAreas.includes(a);
        return `
            <div class="form-check m-1">
                <input class="form-check-input chk-area-turno" type="checkbox" value="${a}" id="chk-area-turno-${i}" ${isChecked ? 'checked' : ''}>
                <label class="form-check-label small" for="chk-area-turno-${i}">${a}</label>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

// ==========================================
// RENDER UI
// ==========================================
function renderHorariosUI() {
    const container = document.getElementById('main-content');
    if (!container) return;

    // Solo inyectar HTML si no existe la sección (evita destruir el modal abierto)
    if (!document.getElementById('horarios-view')) {
        const html = `
            <div id="horarios-view" class="fade-in">
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <h2>📅 Configuración de Turnos</h2>
                    <button class="btn btn-primary" onclick="openModalHorario()">
                        <i class="bi bi-plus-lg"></i> Nuevo Turno
                    </button>
                </div>

                <!-- Tabs Navigation -->
                <ul class="nav nav-tabs mb-3" id="horariosTabs" role="tablist">
                    <li class="nav-item">
                        <button class="nav-link active" id="catalogo-tab" data-bs-toggle="tab" data-bs-target="#catalogo" type="button">Catálogo de Turnos</button>
                    </li>
                    <li class="nav-item">
                        <button class="nav-link" id="asignacion-tab" data-bs-toggle="tab" data-bs-target="#asignacion" type="button">Asignación Masiva</button>
                    </li>
                </ul>

                <div class="tab-content" id="horariosTabsContent">
                    <!-- Tab Catálogo -->
                    <div class="tab-pane fade show active" id="catalogo" role="tabpanel">
                        <div class="card shadow-sm">
                            <div class="card-body">
                                <div class="table-responsive">
                                    <table class="table table-hover align-middle">
                                        <thead class="table-light">
                                            <tr>
                                                <th style="cursor: pointer;" onclick="sortTurnos('nombre')" title="Ordenar por Nombre">
                                                    Nombre <i id="sort-icon-turnos-nombre" class="bi bi-arrow-down-up small text-muted"></i>
                                                </th>
                                                <th style="cursor: pointer;" onclick="sortTurnos('tipo_programacion')" title="Ordenar por Tipo">
                                                    Tipo <i id="sort-icon-turnos-tipo_programacion" class="bi bi-arrow-down-up small text-muted"></i>
                                                </th>
                                                <th style="cursor: pointer;" onclick="sortTurnos('meta_horas_semanales')" title="Ordenar por Horas">
                                                    Horas Semanales <i id="sort-icon-turnos-meta_horas_semanales" class="bi bi-arrow-down-up small text-muted"></i>
                                                </th>
                                                <th>Tolerancias (Alerta/Desc)</th>
                                                <th>Acciones</th>
                                            </tr>
                                        </thead>
                                        <tbody id="turnos-table-body">
                                            <!-- JS Render -->
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Tab Asignación: Redirige al Módulo Empleados -->
                    <div class="tab-pane fade" id="asignacion" role="tabpanel">
                        <div class="d-flex flex-column align-items-center justify-content-center py-5 text-center">
                            <div class="mb-4" style="font-size: 4rem;">🔄</div>
                            <h4 class="fw-bold mb-2">Asignación Masiva de Horarios</h4>
                            <p class="text-muted mb-4" style="max-width: 480px;">
                                Esta funcionalidad fue movida al módulo <strong>Empleados</strong> para una mejor experiencia.
                                Encontrarás la pestaña <strong>"Asignación Masiva"</strong> directamente junto a los turnos asignados.
                            </p>
                            <button class="btn btn-primary btn-lg px-5" onclick="switchPage('empleados'); setTimeout(() => document.getElementById('asignacion-masiva-tab-emp')?.click(), 300);">
                                <i class="bi bi-people-fill me-2"></i> Ir a Módulo Empleados
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        container.innerHTML = html;

        // [FIX] Asegurar que el modal viva fuera de main-content para no ser destruido en re-renders
        // Si el modal ya fue inyectado previamente (fuera del main-content), lo reutilizamos
        const existingModal = document.getElementById('modalTurno');
        if (!existingModal) {
            // Crear el modal e insertarlo directamente en body (no en main-content)
            const modalWrapper = document.createElement('div');
            modalWrapper.innerHTML = renderModalHtml();
            document.body.appendChild(modalWrapper.firstElementChild);
        }

        setupModalListeners();
    }
}

let allEmployeesBulk = [];
let bulkSortState = { key: null, direction: 1 }; // 1 asc, -1 desc

async function loadBulkData() {
    // 1. Cargar empleados activos
    try {
        const response = await fetch('/api/empleados/search/?limit=1000&activo=true');
        if (!response.ok) throw new Error("Error cargando empleados");
        const data = await response.json();
        allEmployeesBulk = data.empleados || data;
        renderBulkEmployeeList(allEmployeesBulk);
    } catch (error) {
        console.error("loadBulkData - Error empleados:", error);
    }

    // 2. Poblar select de áreas para filtro
    const areaSelect = document.getElementById('filter-area-bulk');
    if (areaSelect && allEmployeesBulk.length > 0) {
        const areas = [...new Set(allEmployeesBulk.map(e => e.area).filter(a => a))].sort();
        areaSelect.innerHTML = '<option value="">Todas las Áreas</option>' +
            areas.map(a => `<option value="${a}">${a}</option>`).join('');
    }

    // 3. Poblar select de turnos
    // Si turnosList (de horarios.js) está vacío porque el usuario no visitó
    // Configuración primero, lo cargamos directamente desde la API.
    const select = document.getElementById('bulk-turno-id');
    if (select) {
        let lista = (typeof turnosList !== 'undefined' && turnosList.length > 0)
            ? turnosList
            : null;

        if (!lista) {
            try {
                const res = await fetch('/api/turnos/');
                if (res.ok) {
                    lista = await res.json();
                    // Guardar en la variable global para que no repita fetch si el usuario
                    // navega a Configuración después
                    if (typeof turnosList !== 'undefined') {
                        turnosList.splice(0, turnosList.length, ...(lista || []));
                    }
                }
            } catch (e) {
                console.error("loadBulkData - Error cargando turnos:", e);
                lista = [];
            }
        }

        select.innerHTML = '<option value="">Seleccione un turno...</option>' +
            (lista || []).map(t =>
                `<option value="${t.id}">${t.nombre} (${t.tipo_programacion})</option>`
            ).join('');
    }

    // 4. Set fecha hoy
    const fechaInput = document.getElementById('bulk-fecha-inicio');
    if (fechaInput && !fechaInput.value) {
        fechaInput.value = new Date().toISOString().split('T')[0];
    }

    // 5. Resetear cache de áreas para que la primera selección siempre dispare el fetch
    _lastBulkAreas = '';
    const turnoSelect = document.getElementById('bulk-turno-id');
    if (turnoSelect) {
        turnoSelect.innerHTML = '<option value="">Seleccione empleados primero...</option>';
    }
    const areaHint = document.getElementById('bulk-turno-area-hint');
    if (areaHint) areaHint.innerHTML = '';
}

window.sortBulkEmployees = function (key) {
    if (bulkSortState.key === key) {
        bulkSortState.direction *= -1;
    } else {
        bulkSortState.key = key;
        bulkSortState.direction = 1;
    }

    allEmployeesBulk.sort((a, b) => {
        let valA, valB;
        if (key === 'empleado') {
            valA = (a.nombre_completo || a.nombre || '').toLowerCase();
            valB = (b.nombre_completo || b.nombre || '').toLowerCase();
        } else {
            valA = (a[key] || '').toString().toLowerCase();
            valB = (b[key] || '').toString().toLowerCase();
        }

        if (valA < valB) return -1 * bulkSortState.direction;
        if (valA > valB) return 1 * bulkSortState.direction;
        return 0;
    });

    filterBulkEmployees();
    updateSortIcons();
}

function updateSortIcons() {
    ['empleado', 'area', 'cargo'].forEach(k => {
        const icon = document.getElementById(`sort-icon-${k}`);
        if (icon) icon.className = 'bi bi-arrow-down-up small text-muted';
    });

    if (bulkSortState.key) {
        const icon = document.getElementById(`sort-icon-${bulkSortState.key}`);
        if (icon) {
            icon.className = bulkSortState.direction === 1 ? 'bi bi-sort-alpha-down text-primary' : 'bi bi-sort-alpha-up-alt text-primary';
        }
    }
}

function renderBulkEmployeeList(list) {
    const tbody = document.getElementById('bulk-emp-list');
    if (!tbody) return;

    if (list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center p-4">No se encontraron empleados</td></tr>';
        return;
    }

    tbody.innerHTML = list.map(e => `
        <tr onclick="toggleOneBulk(this)" style="cursor: pointer;">
            <td class="ps-3">
                <input type="checkbox" class="form-check-input check-emp-bulk" value="${e.id}" onclick="event.stopPropagation(); updateBulkCount()">
            </td>
            <td>
                <div class="fw-bold">${e.nombre_completo || e.nombre}</div>
                <div class="small text-muted">ID: ${e.id_empleado || e.id}</div>
            </td>
            <td><span class="badge bg-light text-dark border">${e.area || 'Sin Área'}</span></td>
            <td class="small text-muted">${e.cargo || 'Sin Cargo'}</td>
        </tr>
    `).join('');
}

function filterBulkEmployees() {
    const q = document.getElementById('search-emp-bulk').value.toLowerCase();
    const area = document.getElementById('filter-area-bulk').value;

    const filtered = allEmployeesBulk.filter(e => {
        const matchesSearch = (e.nombre_completo || e.nombre || '').toLowerCase().includes(q) ||
            (e.id_empleado || '').toLowerCase().includes(q);

        const matchesArea = !area || (e.area === area);

        return matchesSearch && matchesArea;
    });

    renderBulkEmployeeList(filtered);
}

function toggleAllBulk(chk) {
    document.querySelectorAll('.check-emp-bulk').forEach(c => c.checked = chk.checked);
    updateBulkCount();
}

function toggleOneBulk(row) {
    const chk = row.querySelector('.check-emp-bulk');
    if (chk) {
        chk.checked = !chk.checked;
        updateBulkCount();
    }
}

function updateBulkCount() {
    const checkedBoxes = document.querySelectorAll('.check-emp-bulk:checked');
    const count = checkedBoxes.length;

    // 1. Actualizar contador y visibilidad del resumen
    const summary = document.getElementById('bulk-summary');
    const badge = document.getElementById('bulk-count');
    if (summary && badge) {
        badge.textContent = count;
        summary.style.display = count > 0 ? 'block' : 'none';
    }

    // 2. Analizar tipos de contrato de los seleccionados
    const fechaFinInput = document.getElementById('bulk-fecha-fin');
    const contratoHint = document.getElementById('bulk-contrato-hint');
    const fechaFinHintText = document.getElementById('bulk-fecha-fin-hint');
    if (!fechaFinInput || !contratoHint) return;

    if (count === 0) {
        // Sin selección: restaurar estado normal
        fechaFinInput.disabled = false;
        fechaFinInput.value = '';
        contratoHint.innerHTML = '';
        if (fechaFinHintText) fechaFinHintText.style.display = '';
        return;
    }

    // Obtener IDs seleccionados y cruzar con allEmployeesBulk para obtener tipo_contrato
    const selectedIds = new Set(Array.from(checkedBoxes).map(c => parseInt(c.value)));
    const selectedEmps = allEmployeesBulk.filter(e => selectedIds.has(e.id));

    const INDEFINIDO_TIPOS = ['INDEFINIDO', 'Indefinido', 'indefinido', 'PLAZO INDEFINIDO', 'Plazo Indefinido'];
    const isIndefinido = e => INDEFINIDO_TIPOS.some(t => (e.tipo_contrato || '').includes(t.split(' ')[0].toUpperCase()) || 
                                                         (e.tipo_contrato || '').toUpperCase().includes('INDEFINIDO'));

    const totalSeleccionados = selectedEmps.length;
    const indefinidos = selectedEmps.filter(isIndefinido).length;
    const conFecha = totalSeleccionados - indefinidos;

    if (indefinidos === totalSeleccionados) {
        // ✅ TODOS son indefinidos → bloquear fecha fin
        fechaFinInput.disabled = true;
        fechaFinInput.value = '';
        if (fechaFinHintText) fechaFinHintText.style.display = 'none';
        contratoHint.innerHTML = `
            <div class="d-flex align-items-center gap-2 p-2 rounded" 
                 style="background:rgba(16,185,129,0.12); border:1px solid rgba(16,185,129,0.35);">
                <i class="bi bi-lock-fill text-success fs-6"></i>
                <span class="small fw-bold text-success">
                    Contrato${indefinidos > 1 ? 's' : ''} Indefinido${indefinidos > 1 ? 's' : ''} — Sin fecha de término
                </span>
                <span class="badge bg-success ms-auto">∞ Proyección ilimitada</span>
            </div>`;
    } else if (indefinidos > 0 && conFecha > 0) {
        // ⚠️ MIXTO → advertencia pero sin bloquear
        fechaFinInput.disabled = false;
        if (fechaFinHintText) fechaFinHintText.style.display = '';
        contratoHint.innerHTML = `
            <div class="d-flex align-items-center gap-2 p-2 rounded"
                 style="background:rgba(245,158,11,0.12); border:1px solid rgba(245,158,11,0.35);">
                <i class="bi bi-exclamation-triangle-fill text-warning fs-6"></i>
                <span class="small fw-bold text-warning-emphasis">
                    Selección mixta: ${indefinidos} indefinido${indefinidos > 1 ? 's' : ''} y ${conFecha} con contrato fijo.
                    <br>
                    <span class="fw-normal text-muted">Deja Vigencia Hasta vacía para no afectar a los indefinidos.</span>
                </span>
            </div>`;
    } else {
        // Todos son de plazo fijo u otro → estado normal
        fechaFinInput.disabled = false;
        contratoHint.innerHTML = '';
        if (fechaFinHintText) fechaFinHintText.style.display = '';
    }

    // 3. Filtrar el selector de turno por área(s) de los empleados seleccionados
    _updateBulkTurnosByAreas(selectedEmps);
}

// Cache de la última consulta de áreas para evitar peticiones redundantes
let _lastBulkAreas = '';
let _bulkTurnoDebounce = null;

async function _updateBulkTurnosByAreas(selectedEmps) {
    const select = document.getElementById('bulk-turno-id');
    const areaHint = document.getElementById('bulk-turno-area-hint');
    if (!select) return;

    if (!selectedEmps || selectedEmps.length === 0) {
        // Sin selección → recargar todos los turnos
        if (_lastBulkAreas !== '__all__') {
            _lastBulkAreas = '__all__';
            await _fetchAndPopulateBulkTurnos(null, areaHint);
        }
        return;
    }

    // Obtener áreas únicas y no vacías
    const areas = [...new Set(selectedEmps.map(e => e.area).filter(a => a))];
    const areasKey = areas.sort().join(',');

    // Evitar petición si las áreas no cambiaron
    if (areasKey === _lastBulkAreas) return;

    // Debounce: esperar 300ms antes de hacer la petición (evita flood al marcar varios)
    clearTimeout(_bulkTurnoDebounce);
    _bulkTurnoDebounce = setTimeout(async () => {
        _lastBulkAreas = areasKey;
        await _fetchAndPopulateBulkTurnos(areas, areaHint);
    }, 300);
}

async function _fetchAndPopulateBulkTurnos(areas, hintEl) {
    const select = document.getElementById('bulk-turno-id');
    if (!select) return;

    const prevValue = select.value; // Conservar selección actual si sigue siendo válida

    // Mostrar indicador de carga en el select
    select.innerHTML = '<option value="">Cargando turnos...</option>';
    select.disabled = true;

    try {
        let lista;
        let hintHtml = '';

        if (!areas || areas.length === 0) {
            // Sin área → traer todos
            const res = await fetch('/api/turnos/');
            lista = res.ok ? await res.json() : [];
            hintHtml = '';
        } else if (areas.length === 1) {
            // Un área específica
            const res = await fetch(`/api/turnos/?area=${encodeURIComponent(areas[0])}`);
            lista = res.ok ? await res.json() : [];
            hintHtml = `
                <div class="d-flex align-items-center gap-1 mt-1" style="font-size:0.78rem;">
                    <i class="bi bi-funnel-fill text-primary" style="font-size:0.7rem;"></i>
                    <span class="text-muted">Mostrando turnos para <strong class="text-primary">${areas[0]}</strong> + globales</span>
                </div>`;
        } else {
            // Múltiples áreas: traer todos y mostrar advertencia
            const res = await fetch('/api/turnos/');
            lista = res.ok ? await res.json() : [];
            hintHtml = `
                <div class="d-flex align-items-center gap-1 mt-1" style="font-size:0.78rem;">
                    <i class="bi bi-exclamation-triangle-fill text-warning" style="font-size:0.7rem;"></i>
                    <span class="text-muted">Selección de <strong>${areas.length} áreas distintas</strong> — mostrando todos los turnos</span>
                </div>`;
        }

        if (hintEl) hintEl.innerHTML = hintHtml;

        select.innerHTML = '<option value="">Seleccione un turno...</option>' +
            (lista || []).map(t =>
                `<option value="${t.id}">${t.nombre} (${t.tipo_programacion})</option>`
            ).join('');

        // Restaurar selección previa si sigue disponible
        if (prevValue && select.querySelector(`option[value="${prevValue}"]`)) {
            select.value = prevValue;
        }
    } catch (e) {
        console.error('_fetchAndPopulateBulkTurnos error:', e);
        select.innerHTML = '<option value="">Error al cargar turnos</option>';
    } finally {
        select.disabled = false;
    }
}

async function submitBulkAsignacion() {
    const selectedIds = Array.from(document.querySelectorAll('.check-emp-bulk:checked')).map(c => parseInt(c.value));
    const turnoId = document.getElementById('bulk-turno-id').value;
    const fecha = document.getElementById('bulk-fecha-inicio').value;
    const fechaFin = document.getElementById('bulk-fecha-fin').value;
    const reemplazar = document.getElementById('bulk-reemplazar')?.checked || false;

    if (selectedIds.length === 0) return alert("Seleccione al menos un empleado");
    if (!turnoId) return alert("Seleccione un turno");
    if (!fecha) return alert("Seleccione una fecha de inicio");

    const accion = reemplazar ? 'reemplazar el horario existente' : 'asignar un turno nuevo';
    const confirmMsg = fechaFin
        ? `¿Desea ${accion} a ${selectedIds.length} empleados desde el ${fecha} hasta el ${fechaFin}?`
        : `¿Desea ${accion} a ${selectedIds.length} empleados de forma indefinida a partir del ${fecha}?`;

    if (!confirm(confirmMsg)) return;

    // --- UI: Bloquear botón con spinner ---
    const btn = document.querySelector('[onclick="submitBulkAsignacion()"]');
    const btnOriginalHTML = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status"></span>Procesando...`;
    }

    // Ocultar banner previo si existía
    const prevBanner = document.getElementById('bulk-result-banner');
    if (prevBanner) prevBanner.remove();

    try {
        const bodyPayload = {
            empleados_ids: selectedIds,
            turno_id: parseInt(turnoId),
            fecha_inicio: fecha,
            reemplazar: reemplazar
        };
        if (fechaFin) bodyPayload.fecha_fin = fechaFin;

        const response = await fetch('/api/turnos/bulk-assign/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bodyPayload)
        });

        if (!response.ok) throw new Error("Error en la asignación masiva");
        const res = await response.json();

        // --- UI: Banner informativo (no bloqueante) ---
        const esRetroactivo = fecha <= new Date().toISOString().split('T')[0];
        const banner = document.createElement('div');
        banner.id = 'bulk-result-banner';
        banner.className = 'alert alert-success alert-dismissible fade show mt-3 mb-0';
        banner.role = 'alert';
        banner.innerHTML = `
            <div class="d-flex align-items-start gap-2">
                <i class="bi bi-check-circle-fill fs-5 mt-1 flex-shrink-0"></i>
                <div>
                    <strong>${res.success} asignación(es) guardada(s) correctamente.</strong>
                    ${res.errors > 0 ? `<br><span class="text-warning">⚠️ ${res.errors} con error.</span>` : ''}
                    ${esRetroactivo ? `
                    <hr class="my-2">
                    <div class="d-flex align-items-center gap-2">
                        <div class="spinner-border spinner-border-sm text-success flex-shrink-0" role="status"></div>
                        <span><strong>Reprocesando marcaciones en segundo plano</strong> desde el <strong>${fecha}</strong> hasta hoy.<br>
                        <small class="text-muted">Este proceso descarga las marcaciones desde BioAlba. Puede tardar unos segundos. 
                        Cuando termine, la grilla de asistencia estará actualizada.</small></span>
                    </div>` : ''}
                </div>
            </div>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Cerrar"></button>
        `;

        // Insertar banner bajo el botón de asignación
        const cardBody = btn ? btn.closest('.card-body') : null;
        if (cardBody) {
            cardBody.appendChild(banner);
        }

        // Si es retroactivo, auto-ocultar spinner del banner después de 15s (estimado)
        if (esRetroactivo) {
            setTimeout(() => {
                const spinner = banner.querySelector('.spinner-border');
                if (spinner) {
                    spinner.replaceWith(Object.assign(document.createElement('i'), {
                        className: 'bi bi-check2-all text-success fs-5 flex-shrink-0'
                    }));
                    const msg = banner.querySelector('strong:last-of-type');
                    if (msg) msg.textContent = 'Reprocesamiento completado (estimado).';
                }
            }, 20000);
        }

        // Refrescar lista y limpiar selección
        loadBulkData();
        const checkAll = document.getElementById('check-all-bulk');
        if (checkAll) checkAll.checked = false;
        updateBulkCount();

    } catch (error) {
        console.error(error);
        alert("Error: " + error.message);
    } finally {
        // Restaurar botón
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = btnOriginalHTML;
        }
    }
}


function renderTurnosTable() {
    const tbody = document.getElementById('turnos-table-body');
    if (!tbody) return;

    if (turnosList.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted p-4">No hay turnos creados</td></tr>`;
        return;
    }

    tbody.innerHTML = turnosList.map(t => `
        <tr>
            <td class="fw-bold">${t.nombre}</td>
            <td><span class="badge bg-secondary">${t.tipo_programacion}</span></td>
            <td>${t.meta_horas_semanales} hrs</td>
            <td>${t.tolerancia_retraso_alerta} min / ${t.tolerancia_retraso_descuento} min</td>
            <td>
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-primary" onclick="openModalHorario(${t.id})" title="Editar">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-outline-danger" onclick="deleteTurno(${t.id})" title="Eliminar">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
}

function renderModalHtml() {
    return `
    <!-- Sin clase 'fade': la animación Bootstrap de fade causaba Layout Shifts masivos (CLS 60+) -->
    <div class="modal" id="modalTurno" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="modalTurnoLabel">Nuevo Turno</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body p-4">
                    <form id="formTurno">
                        <div class="row g-3 mb-4">
                            <div class="col-md-4">
                                <label for="input-nombre-turno" class="form-label">Nombre del Turno</label>
                                <input type="text" id="input-nombre-turno" class="form-control" name="nombre" required placeholder="Ej: Operativo Mañana">
                            </div>
                            <div class="col-md-4">
                                <label for="input-tipo-programacion" class="form-label">Tipo Planificación</label>
                                <select id="input-tipo-programacion" class="form-select" name="tipo_programacion" onchange="handleTipoProgramacionChange()">
                                    <option value="FIJO">Horario Fijo</option>
                                    <option value="ROTATIVO">Ciclo Rotativo</option>
                                    <option value="ROTATIVO_INTELIGENTE">Ciclo Inteligente (Smart Match)</option>
                                    <option value="FLEXIBLE_BOLSA">Flexible (Bolsa de Horas)</option>
                                </select>
                            </div>
                            <div class="col-md-4">
                                <label class="form-label fw-bold text-success d-flex justify-content-between align-items-center mb-1">
                                    <span>Áreas de Visibilidad</span>
                                </label>
                                <div id="container-areas-turno" class="border border-success rounded p-2 overflow-auto" style="max-height: 120px; background-color: #f8fff9;">
                                    <div class="text-center text-muted small py-2">Cargando áreas...</div>
                                </div>
                                <div class="form-text small">Selecciona al menos un área a la cual estará asignado este turno.</div>
                            </div>
                        </div>

                        <div class="row g-3 mb-4" id="divLineaFicticia" style="display:none;">
                            <div class="col-md-6 border-start border-danger border-4 ps-3">
                                <label for="input-hora-ficticia" class="form-label fw-bold text-danger">Hora Límite Ficticia (Trigger Inasistencia)</label>
                                <input type="time" id="input-hora-ficticia" class="form-control border-danger" name="hora_limite_ficticia" value="09:00">
                                <div class="form-text small text-danger">Si a esta hora no hay marcación, se emitirá alerta de INASISTENCIA (Reversible).</div>
                            </div>
                            <div class="col-md-6 border-start border-primary border-4 ps-3" id="colMetaBolsa">
                                <label for="input-meta-bolsa" class="form-label fw-bold text-primary">Meta Mensual (Hrs Totales)</label>
                                <div class="input-group">
                                    <input type="number" id="input-meta-bolsa" class="form-control border-primary" value="176" step="0.5">
                                    <span class="input-group-text bg-primary text-white border-primary">Hrs</span>
                                </div>
                                <div class="form-text small text-primary">Para Art. 25 BIS en Chile, usualmente son 176 o 180 horas al mes.</div>
                            </div>
                        </div>

                        <h6>Reglas de Asistencia</h6>
                        <div class="row g-3 mb-4 p-3 bg-light rounded border">
                            <!-- Fila 1: Gobernanza de Tiempos (Sétrica 3 columnas) -->
                            <div class="col-md-3">
                                <label for="input-tol-alerta" class="form-label small fw-bold">Tolerancia Alerta (min)</label>
                                <input type="number" id="input-tol-alerta" class="form-control" name="tolerancia_retraso_alerta" value="5">
                                <div class="form-text small" style="font-size: 0.7rem;">Aviso visual de retraso.</div>
                            </div>
                            <div class="col-md-3">
                                <label for="input-tol-desc" class="form-label small fw-bold">Tol. Descuento (min)</label>
                                <input type="number" id="input-tol-desc" class="form-control" name="tolerancia_retraso_descuento" value="15">
                                <div class="form-text small" style="font-size: 0.7rem;">Criterio para descuento real.</div>
                            </div>
                            <div class="col-md-3">
                                <label for="input-anclaje" class="form-label small fw-bold" title="Minutos antes de la entrada que se anclan al inicio oficial">Anclaje Entrada (min)</label>
                                <input type="number" id="input-anclaje" class="form-control" name="anclaje_entrada_minutos" value="0">
                                <div class="form-text small" style="font-size: 0.7rem;">Captura marcas tempranas.</div>
                            </div>
                            <div class="col-md-3">
                                <label for="input-anclaje-salida" class="form-label small fw-bold" title="Minutos después de la salida que se anclan al fin oficial">Anclaje Salida (min)</label>
                                <input type="number" id="input-anclaje-salida" class="form-control" name="anclaje_salida_minutos" value="0">
                                <div class="form-text small" style="font-size: 0.7rem;">Filtra HE pequeñas.</div>
                            </div>

                            <!-- Fila 2: Ajustes de Cálculo (Simétrica 2 columnas) -->
                            <div class="col-md-6">
                                <label for="input-redondeo" class="form-label small fw-bold">Redondeo de Marcas</label>
                                <select id="input-redondeo" class="form-select" name="redondeo_minutos">
                                    <option value="0">Exacto (Sin Redondeo)</option>
                                    <option value="15">Intervalos de 15 min</option>
                                    <option value="30">Intervalos de 30 min</option>
                                </select>
                                <div class="form-text small">Alinea marcas al bloque más cercano.</div>
                            </div>
                            <div class="col-md-6">
                                <label for="chkColacion" class="form-label small fw-bold">Colación Automática</label>
                                <div class="d-flex align-items-center gap-2">
                                    <div class="form-check mb-0">
                                        <input class="form-check-input" type="checkbox" id="chkColacion" name="descuento_colacion_auto" onchange="toggleColacionInput()">
                                        <label class="form-check-label small" for="chkColacion">Descontar</label>
                                    </div>
                                    <div id="divColacionTime" style="display:none; width: 100px;">
                                        <div class="input-group input-group-sm">
                                            <input type="number" class="form-control" id="numColacion" placeholder="Min" value="30" oninput="updateAllCalculations()">
                                            <span class="input-group-text">min</span>
                                        </div>
                                    </div>
                                </div>
                                <div class="form-text small">Tiempo que se resta de la jornada total.</div>
                            </div>
                        </div>

                        <div class="row g-3 mb-4">
                            <div class="col-md-6">
                                <div class="form-check form-switch p-3 bg-white border rounded">
                                    <input class="form-check-input ms-0 me-2" type="checkbox" id="chkCortado" name="es_turno_cortado" onchange="toggleCortadoUI()">
                                    <label class="form-check-label fw-bold" for="chkCortado">Es Turno Cortado / Partido (Bloque Tarde)</label>
                                </div>
                            </div>
                        </div>

                        <div id="wrapper-semanas">
                            <ul class="nav nav-pills mb-3" id="pills-tab-weeks" role="tablist">
                                <!-- JS Tabs -->
                            </ul>
                            <div class="tab-content" id="pills-tabContent-weeks">
                                <!-- JS Content -->
                            </div>
                            <div id="btn-add-week-container" class="mt-2" style="display:none;">
                                <button type="button" class="btn btn-sm btn-outline-success" onclick="addWeekTab()">
                                    <i class="bi bi-plus-circle"></i> Añadir Semana al Ciclo
                                </button>
                                <button type="button" class="btn btn-sm btn-outline-danger" onclick="removeLastWeekTab()">
                                    <i class="bi bi-dash-circle"></i> Quitar Última Semana
                                </button>
                            </div>
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                    <button type="button" class="btn btn-primary" onclick="saveTurno()">Guardar</button>
                </div>
            </div>
        </div>
    </div>
    `;
}

let activeWeeksCount = 1;

function setupModalListeners(numWeeks = 1) {
    activeWeeksCount = 0; // Reset para addWeekTab
    const tabContainer = document.getElementById('pills-tab-weeks');
    const contentContainer = document.getElementById('pills-tabContent-weeks');
    if (!tabContainer || !contentContainer) return;

    tabContainer.innerHTML = '';
    contentContainer.innerHTML = '';

    for (let i = 1; i <= numWeeks; i++) {
        addWeekTab(false); // false = no llamar handleTipoProgramacionChange internamente
    }

    // Switch to first tab
    const firstTab = tabContainer.querySelector('button');
    if (firstTab) firstTab.click();

    // No llamar handleTipoProgramacionChange aquí:
    // El caller (openModalHorario) es responsable de llamarlo UNA sola vez al final.
}

window.addWeekTab = function (triggerChange = true) {
    activeWeeksCount++;
    const i = activeWeeksCount;
    const tabContainer = document.getElementById('pills-tab-weeks');
    const contentContainer = document.getElementById('pills-tabContent-weeks');

    // Nombre de la pestaña según tipo: Ciclo Inteligente usa la etiqueta, otros usan "Semana"
    const tipoSelect = document.querySelector('select[name="tipo_programacion"]');
    const isInteligente = tipoSelect && tipoSelect.value === 'ROTATIVO_INTELIGENTE';
    const tabName = isInteligente ? `Opción ${i}` : `Semana ${i}`;

    // Create Tab
    const li = document.createElement('li');
    li.className = 'nav-item';
    li.innerHTML = `
        <button class="nav-link ${i === 1 ? 'active' : ''}" id="pill-week-${i}-tab" data-bs-toggle="pill" 
            data-bs-target="#week-container-${i}" type="button" role="tab">${tabName}</button>
    `;
    tabContainer.appendChild(li);

    // Create Content
    const div = document.createElement('div');
    div.className = `tab-pane fade ${i === 1 ? 'show active' : ''} week-container`;
    div.id = `week-container-${i}`;
    div.role = 'tabpanel';

    const dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
    div.innerHTML = `
        <div class="row mb-2 etiqueta-bloque-container" style="${isInteligente ? '' : 'display:none;'}">
            <div class="col-md-4">
                <label class="form-label small fw-bold text-primary">Nombre del Ciclo/Opción</label>
                <input type="text" id="etiqueta-bloque-${i}" class="form-control form-control-sm etiqueta-input" list="etiquetas-sugeridas" placeholder="Ej: Mañana, Tarde, Noche" value="Opción ${i}" oninput="document.getElementById('pill-week-${i}-tab').innerText = this.value || 'Opción ${i}'">
                <datalist id="etiquetas-sugeridas">
                    <option value="Mañana"></option>
                    <option value="Tarde"></option>
                    <option value="Noche"></option>
                    <option value="Jornada Normal"></option>
                </datalist>
            </div>
        </div>
        <div class="table-responsive">
            <table class="table table-sm text-center align-middle">
                <thead>
                    <tr>
                        <th style="width: 100px;">Día</th>
                        <th>Libre</th>
                        <th>Entrada</th>
                        <th>Salida</th>
                        <th>Cruce</th>
                        <th class="col-bloque-2" style="display:none; background-color: #f8f9fa;">Entrada 2</th>
                        <th class="col-bloque-2" style="display:none; background-color: #f8f9fa;">Salida 2</th>
                        <th class="col-bloque-2" style="display:none; background-color: #f8f9fa;">Cruce 2</th>
                        <th class="col-teoricas">Hrs. Teóricas</th>
                    </tr>
                </thead>
                <tbody class="dias-input-body">
                    ${dias.map((dia, index) => `
                        <tr data-day="${index}">
                            <td class="small fw-bold">${dia}</td>
                            <td><input type="checkbox" id="chk-libre-w${i}-d${index}" name="chk-libre-w${i}-d${index}" class="form-check-input chk-libre" onchange="toggleDiaRow(this)"></td>
                            <td><input type="time" id="time-in-w${i}-d${index}" name="time-in-w${i}-d${index}" class="form-control form-control-sm time-in" value="08:00" oninput="updateAllCalculations()"></td>
                            <td><input type="time" id="time-out-w${i}-d${index}" name="time-out-w${i}-d${index}" class="form-control form-control-sm time-out" value="16:00" oninput="updateAllCalculations()"></td>
                            <td><input type="checkbox" id="chk-cruce-w${i}-d${index}" name="chk-cruce-w${i}-d${index}" class="form-check-input chk-cruce" onchange="updateAllCalculations()"></td>
                            <td class="col-bloque-2" style="display:none; background-color: #f8f9fa;"><input type="time" id="time-in-2-w${i}-d${index}" name="time-in-2-w${i}-d${index}" class="form-control form-control-sm time-in-2" value="14:00" oninput="updateAllCalculations()"></td>
                            <td class="col-bloque-2" style="display:none; background-color: #f8f9fa;"><input type="time" id="time-out-2-w${i}-d${index}" name="time-out-2-w${i}-d${index}" class="form-control form-control-sm time-out-2" value="18:00" oninput="updateAllCalculations()"></td>
                            <td class="col-bloque-2" style="display:none; background-color: #f8f9fa;"><input type="checkbox" id="chk-cruce-2-w${i}-d${index}" name="chk-cruce-2-w${i}-d${index}" class="form-check-input chk-cruce-2" onchange="updateAllCalculations()"></td>
                            <td><input type="number" id="hours-calc-w${i}-d${index}" name="hours-calc-w${i}-d${index}" class="form-control form-control-sm hours-calc" value="8" step="0.5"></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
    contentContainer.appendChild(div);

    if (triggerChange) handleTipoProgramacionChange();
}

window.removeLastWeekTab = function () {
    if (activeWeeksCount <= 1) return;
    const tabContainer = document.getElementById('pills-tab-weeks');
    const contentContainer = document.getElementById('pills-tabContent-weeks');

    tabContainer.removeChild(tabContainer.lastChild);
    contentContainer.removeChild(contentContainer.lastChild);
    activeWeeksCount--;

    // Activar la anterior si borramos la activa
    const tabs = tabContainer.querySelectorAll('button');
    tabs[tabs.length - 1].click();
}

function toggleDiaRow(chk) {
    const row = chk.closest('tr');
    const inputs = row.querySelectorAll('input:not(.chk-libre)');
    inputs.forEach(input => {
        input.disabled = chk.checked;
        if (input.classList.contains('hours-calc') && chk.checked) input.value = 0;
    });
    updateAllCalculations();
}

function toggleCortadoUI() {
    const isCortado = document.getElementById('chkCortado').checked;
    const cols = document.querySelectorAll('.col-bloque-2');
    cols.forEach(c => {
        c.style.display = isCortado ? '' : 'none';
        c.style.visibility = 'visible';
    });
    // [FIX] handleTipoProgramacionChange() es segura de llamar aquí porque
    // ya no llama a setupModalListeners (el bucle fue eliminado)
    handleTipoProgramacionChange();
}

function toggleColacionInput() {
    const chk = document.getElementById('chkColacion');
    const div = document.getElementById('divColacionTime');
    if (div) div.style.display = chk.checked ? 'block' : 'none';
    updateAllCalculations();
}

function closeModalHorario() {
    const el = document.getElementById('modalTurno');
    if (el) {
        const modal = bootstrap.Modal.getInstance(el);
        if (modal) modal.hide();
    }
}

// ==========================================
// AUTOMATION LOGIC
// ==========================================
function handleTipoProgramacionChange() {
    const tipoSelect = document.querySelector('select[name="tipo_programacion"]');
    if (!tipoSelect) return;

    const tipo = tipoSelect.value;
    const isFlexible = tipo === 'FLEXIBLE_BOLSA';
    const isRotativo = tipo === 'ROTATIVO' || tipo === 'ROTATIVO_INTELIGENTE';

    // Visibilidad del bloque de Hora Ficticia: sólo visible en modo Bolsa Flexible
    const divLineaFicticia = document.getElementById('divLineaFicticia');
    if (divLineaFicticia) divLineaFicticia.style.display = isFlexible ? 'flex' : 'none';

    // Actualiza el texto de las pestañas de semanas según el tipo de programación activo
    document.querySelectorAll('#pills-tab-weeks .nav-link').forEach((tab, index) => {
        tab.textContent = tipo === 'ROTATIVO_INTELIGENTE' ? `Turno / Opción ${index + 1}` : `Semana ${index + 1}`;
    });

    const divAddWeek = document.getElementById('btn-add-week-container');
    if (divAddWeek) divAddWeek.style.display = isRotativo ? 'block' : 'none';

    // Si cambia a no-rotativo y hay semanas extra visibles, ocultarlas sin destruir el DOM:
    // Ocultamos las semanas extra SIN destruir el DOM (evita el bucle setupModalListeners -> handleTipoProgramacionChange)
    if (!isRotativo && activeWeeksCount > 1) {
        const tabContainer = document.getElementById('pills-tab-weeks');
        const contentContainer = document.getElementById('pills-tabContent-weeks');
        if (tabContainer && contentContainer) {
            // Ocultar tabs extras (dejar solo el primero visible)
            const tabs = tabContainer.querySelectorAll('li');
            tabs.forEach((tab, idx) => { tab.style.display = idx === 0 ? '' : 'none'; });
            // Ocultar paneles extras
            const panes = contentContainer.querySelectorAll('.week-container');
            panes.forEach((pane, idx) => {
                if (idx === 0) {
                    pane.classList.add('show', 'active');
                } else {
                    pane.classList.remove('show', 'active');
                }
            });
            // Activar el primer tab explícitamente
            const firstTabBtn = tabContainer.querySelector('button');
            if (firstTabBtn && !firstTabBtn.classList.contains('active')) firstTabBtn.click();
        }
        // NO llamar setupModalListeners(1) – eso causaba el bucle
    } else if (isRotativo) {
        // Mostrar todos los tabs de semanas cuando se vuelve a rotativo
        const tabContainer = document.getElementById('pills-tab-weeks');
        if (tabContainer) {
            tabContainer.querySelectorAll('li').forEach(tab => { tab.style.display = ''; });
        }
    }

    // Select headers and cells for Entrada, Salida, Cruce
    const indices = [3, 4, 5]; // 1-indexed: Entrada, Salida, Cruce

    const weekContainers = document.querySelectorAll('.week-container');
    if (weekContainers.length === 0) return;

    weekContainers.forEach(tbody => {
        // Table Headers
        const headers = tbody.querySelectorAll('thead th');
        indices.forEach(idx => {
            if (headers[idx - 1]) headers[idx - 1].style.visibility = isFlexible ? 'hidden' : 'visible';
        });

        // Ocultar cabecera Horas Teóricas
        const thTeoricas = tbody.querySelector('.col-teoricas');
        if (thTeoricas) thTeoricas.style.visibility = isFlexible ? 'hidden' : 'visible';

        // Table Cells
        const rows = tbody.querySelectorAll('.dias-input-body tr');
        rows.forEach(row => {
            indices.forEach(idx => {
                const cell = row.querySelector(`td:nth-child(${idx})`);
                if (cell) cell.style.visibility = isFlexible ? 'hidden' : 'visible';
            });

            // Ocultar inputs Hrs teoricas
            const inputTeo = row.querySelector('.hours-calc');
            if (inputTeo && inputTeo.parentElement) {
                inputTeo.parentElement.style.visibility = isFlexible ? 'hidden' : 'visible';
                if (isFlexible && !inputTeo.disabled) {
                    inputTeo.value = 0;
                }
            }

            // Block 2 visibility
            const isCortado = document.getElementById('chkCortado').checked;
            const col2Cells = row.querySelectorAll('.col-bloque-2');
            col2Cells.forEach(c => {
                c.style.display = (isFlexible || !isCortado) ? 'none' : 'table-cell';
                c.style.visibility = 'visible';
            });
        });
    });

    updateAllCalculations();
}

function updateAllCalculations() {
    const tipoSelect = document.querySelector('select[name="tipo_programacion"]');
    if (!tipoSelect) return;

    const tipo = tipoSelect.value;
    if (tipo === 'FLEXIBLE_BOLSA') return; // Flexible is manual

    const isCortado = document.getElementById('chkCortado').checked;
    const colacionAuto = document.getElementById('chkColacion').checked;
    const minutosColacion = colacionAuto ? (parseInt(document.getElementById('numColacion').value) || 0) : 0;

    const containers = document.querySelectorAll('.week-container');
    containers.forEach(container => {
        const rows = container.querySelectorAll('.dias-input-body tr');
        rows.forEach(row => {
            const isLibre = row.querySelector('.chk-libre').checked;
            if (isLibre) {
                row.querySelector('.hours-calc').value = 0;
                return;
            }

            const h1 = calculateDiff(
                row.querySelector('.time-in').value,
                row.querySelector('.time-out').value,
                row.querySelector('.chk-cruce').checked
            );

            let h2 = 0;
            if (isCortado) {
                h2 = calculateDiff(
                    row.querySelector('.time-in-2').value,
                    row.querySelector('.time-out-2').value,
                    row.querySelector('.chk-cruce-2').checked
                );
            }

            let total = h1 + h2;
            if (total > 0) {
                total -= (minutosColacion / 60);
            }

            row.querySelector('.hours-calc').value = Math.max(0, total.toFixed(2));
        });

        // Validación 44 horas
        const totalSemana = Array.from(container.querySelectorAll('.hours-calc'))
            .reduce((acc, input) => acc + (parseFloat(input.value) || 0), 0);

        let alertDiv = container.querySelector('.alert-hours-warning');
        if (totalSemana > 44) {
            if (!alertDiv) {
                alertDiv = document.createElement('div');
                alertDiv.className = 'alert alert-warning p-1 mt-2 small alert-hours-warning';
                container.appendChild(alertDiv);
            }
            alertDiv.innerHTML = `<i class="bi bi-exclamation-triangle"></i> Atención: Esta semana suma <strong>${totalSemana.toFixed(1)}</strong> horas (Máx legal sugerido: 44h).`;
        } else if (alertDiv) {
            alertDiv.remove();
        }
    });
}

function calculateDiff(start, end, crossesMidnight) {
    if (!start || !end) return 0;

    const [h1, m1] = start.split(':').map(Number);
    const [h2, m2] = end.split(':').map(Number);

    let d1 = new Date(2000, 0, 1, h1, m1);
    let d2 = new Date(2000, 0, 1, h2, m2);

    if (crossesMidnight || d2 < d1) {
        d2.setDate(d2.getDate() + 1);
    }

    return (d2 - d1) / (1000 * 60 * 60);
}
