/**
 * Asistencia JS - Lógica para reportes y procesamiento
 */

const API_ASISTENCIA = '/api/asistencia/';

// Fix #B/#E: Caché global de áreas — compartido entre Reportes, Dashboard y Empleados.
// Se invalida cuando se agrega/edita un área.
window._cachedAreas = window._cachedAreas || null;
async function getAreasCache() {
    if (window._cachedAreas) return window._cachedAreas;
    try {
        const r = await fetch('/api/empleados/stats/');
        if (r.ok) {
            const stats = await r.json();
            window._cachedAreas = stats.areas || [];
        }
    } catch (e) {
        console.warn('Error cargando áreas:', e);
    }
    return window._cachedAreas || [];
}

function initAsistencia() {
    // Set default dates (current month)
    const now = new Date();
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().split('T')[0];
    const lastDay = now.toISOString().split('T')[0];

    const inicioInput = document.getElementById('rep-fecha-inicio');
    const finInput = document.getElementById('rep-fecha-fin');
    if (inicioInput) inicioInput.value = firstDay;
    if (finInput) finInput.value = lastDay;

    // Listener para actualizar turnos cuando cambia el área
    const areaSelect = document.getElementById('rep-area');
    if (areaSelect) {
        areaSelect.addEventListener('change', () => {
             console.log("Área de reporte cambiada, actualizando horarios...");
             populateReportTurns();
        });
    }

    // Poplar Áreas y Turnos
    populateReportAreas();
    populateReportTurns();
    loadReporte();
}

async function populateReportAreas() {
    try {
        // Fix #E: reusar caché de áreas — no repetir la llamada HTTP
        const areas = await getAreasCache();
        const select = document.getElementById('rep-area');
        if (select && areas.length) {
            const currentVal = select.value;
            select.innerHTML = '<option value="">Todas</option>' +
                areas.map(a => `<option value="${a.area}">${a.area}</option>`).join('');
            select.value = currentVal;
        }
    } catch (e) {
        console.warn("No se pudieron cargar áreas para reporte", e);
    }
}

async function populateReportTurns() {
    try {
        const area = document.getElementById('rep-area')?.value || "";
        const response = await fetch(`${API_ASISTENCIA}filters-data/?area=${encodeURIComponent(area)}`);
        if (!response.ok) return;
        const data = await response.json();
        const select = document.getElementById('rep-turno');
        if (select && data.turnos) {
            const currentVal = select.value;
            select.innerHTML = '<option value="">Todos</option>' +
                data.turnos.map(t => `<option value="${t.id}">${t.nombre}</option>`).join('');
            
            // Intentar mantener selección previa si sigue existiendo en el nuevo set filtrado
            if (currentVal && data.turnos.find(t => t.id == currentVal)) {
                select.value = currentVal;
            } else {
                select.value = "";
            }
        }
    } catch (e) {
        console.warn("No se pudieron cargar turnos para reporte", e);
    }
}

async function loadReporte() {
    // 🛡️ BLOQUEO DE SEGURIDAD (Muro de Asistencia)
    if (typeof window.checkAuditoriaBloqueo === 'function') {
        const isBlocked = await window.checkAuditoriaBloqueo();
        if (isBlocked) {
            console.warn("⚠️ ACCESO RESTRINGIDO: Regularice anomalías para ver reportes.");
            return;
        }
    }

    const inicio = document.getElementById('rep-fecha-inicio').value;
    const fin = document.getElementById('rep-fecha-fin').value;
    const area = document.getElementById('rep-area').value;
    const turnoId = document.getElementById('rep-turno').value;

    if (!inicio || !fin) return;

    // Cargar Gráfico en paralelo
    loadChartData(inicio, fin);

    const tbody = document.getElementById('reporte-body');
    tbody.innerHTML = '<tr><td colspan="9" class="text-center p-4"><div class="spinner-border spinner-border-sm text-primary"></div> Cargando...</td></tr>';

    try {
        let url = `${API_ASISTENCIA}reporte/?fecha_inicio=${inicio}&fecha_fin=${fin}`;
        if (area) url += `&area=${encodeURIComponent(area)}`;
        if (turnoId) url += `&turno_id=${turnoId}`;

        const response = await fetch(url);
        if (!response.ok) throw new Error("Error cargando reporte");

        const data = await response.json();
        renderReporte(data);
    } catch (error) {
        console.error(error);
        tbody.innerHTML = `<tr><td colspan="9" class="text-center text-danger p-4">Error: ${error.message}</td></tr>`;
    }
}

async function downloadExcelReport() {
    // 1. Intentar obtener el rango desde los selectores de la vista Marcaciones (Mes y Año)
    const uiMes = document.getElementById('marcacion-mes');
    const uiAnio = document.getElementById('marcacion-anio');

    let inicio, fin;
    let endpoint;
    let areaParam = '';
    let turnoParam = '';

    // Identificar el módulo desde donde el usuario está apretando el botón (Módulo Reportes vs Marcaciones)
    const pageReportes = document.getElementById('page-reportes');
    const isReportes = pageReportes && pageReportes.classList.contains('active');

    if (isReportes) {
        // Modo Reportes: Obtenemos el Rango Libre Sandbox y el filtro de su selector de Áreas
        inicio = document.getElementById('rep-fecha-inicio')?.value;
        fin = document.getElementById('rep-fecha-fin')?.value;
        endpoint = '/api/reports/asistencia/excel-range/';

        const uiArea = document.getElementById('rep-area');
        if (uiArea && uiArea.value) {
            areaParam = `&area=${encodeURIComponent(uiArea.value)}`;
        }
        const uiTurno = document.getElementById('rep-turno');
        if (uiTurno && uiTurno.value) {
            turnoParam = `&turno_id=${uiTurno.value}`;
        }
    } else {
        // Modo Marcaciones: Usar las mismas fechas RRHH que la grilla muestra
        // FIX: Antes usaba mes calendario (1-31), pero la grilla usa el período RRHH
        // (ej: 26/04 al 25/05), lo que causaba discrepancias enormes en el Excel.
        if (typeof stateMarcacionesApp !== 'undefined' && stateMarcacionesApp.fechaInicioRRHH && stateMarcacionesApp.fechaFinRRHH) {
            inicio = stateMarcacionesApp.fechaInicioRRHH;
            fin = stateMarcacionesApp.fechaFinRRHH;
        } else {
            // Fallback: si no hay periodo RRHH cargado, usar mes calendario
            const uiMes = document.getElementById('marcacion-mes');
            const uiAnio = document.getElementById('marcacion-anio');
            const y = parseInt(uiAnio?.value || new Date().getFullYear(), 10);
            const m = parseInt(uiMes?.value || (new Date().getMonth() + 1), 10);

            inicio = `${y}-${String(m).padStart(2, '0')}-01`;
            const lastDay = new Date(y, m, 0).getDate();
            fin = `${y}-${String(m).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
        }
        endpoint = '/api/reports/asistencia/excel/';

        const uiArea = document.getElementById('marcacion-area');
        if (uiArea && uiArea.value) {
            areaParam = `&area=${encodeURIComponent(uiArea.value)}`;
        }
        const uiTurno = document.getElementById('marcacion-turno');
        if (uiTurno && uiTurno.value) {
            turnoParam = `&turno_id=${uiTurno.value}`;
        }
    }

    if (!inicio || !fin) {
        return alert('Seleccione un rango de fechas o un mes/año válido para exportar.');
    }

    // Disparar descarga al endpoint adecuado según el módulo que lo invocó
    const token = typeof AuthService !== 'undefined' ? AuthService.getToken() : localStorage.getItem('access_token');
    const tokenParam = token ? `&token=${encodeURIComponent(token)}` : '';
    window.location.href = `${endpoint}?fecha_inicio=${inicio}&fecha_fin=${fin}${areaParam}${turnoParam}${tokenParam}`;
}

let attendanceChart = null;

async function loadChartData(inicio, fin) {
    try {
        const response = await fetch(`/api/reports/stats/?fecha_inicio=${inicio}&fecha_fin=${fin}`);
        if (!response.ok) return;
        const stats = await response.json();
        renderChart(stats);
    } catch (e) {
        console.error("Error loading charts", e);
    }
}

function renderChart(stats) {
    const ctx = document.getElementById('attendanceChart').getContext('2d');

    if (attendanceChart) {
        attendanceChart.destroy();
    }

    const labels = stats.map(s => s.fecha);
    const dataPresentes = stats.map(s => s.presentes);
    const dataAtrasos = stats.map(s => s.atrasos);
    const dataInasistencias = stats.map(s => s.inasistencias);

    attendanceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Presentes',
                    data: dataPresentes,
                    borderColor: '#2ecc71',
                    backgroundColor: 'rgba(46, 204, 113, 0.1)',
                    fill: true,
                    tension: 0.3
                },
                {
                    label: 'Atrasos',
                    data: dataAtrasos,
                    borderColor: '#f1c40f',
                    backgroundColor: 'rgba(241, 196, 15, 0.1)',
                    fill: true,
                    tension: 0.3
                },
                {
                    label: 'Ausentes',
                    data: dataInasistencias,
                    borderColor: '#e74c3c',
                    backgroundColor: 'rgba(231, 76, 60, 0.1)',
                    fill: true,
                    tension: 0.3
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top' },
                tooltip: { mode: 'index', intersect: false }
            },
            interaction: { mode: 'nearest', axis: 'x', intersect: false },
            scales: {
                y: { beginAtZero: true, ticks: { precision: 0 } }
            }
        }
    });
}


let currentReporteList = [];

window.sortReporte = function (key) {
    // Custom sort for nested or complex fields
    if (key === 'empleado') {
        const tableId = 'reporte';
        if (!TableSorter.states[tableId]) TableSorter.states[tableId] = { key: null, dir: 1 };
        const state = TableSorter.states[tableId];

        if (state.key === 'empleado') state.dir *= -1;
        else { state.key = 'empleado'; state.dir = 1; }

        currentReporteList.sort((a, b) => {
            const valA = (a.apellido_paterno + ' ' + (a.apellido_materno || '') + ' ' + a.nombre).toLowerCase();
            const valB = (b.apellido_paterno + ' ' + (b.apellido_materno || '') + ' ' + b.nombre).toLowerCase();
            if (valA < valB) return -1 * state.dir;
            if (valA > valB) return 1 * state.dir;
            return 0;
        });

        renderReporte(currentReporteList);
        return;
    }

    TableSorter.sort(currentReporteList, key, 'reporte');
    renderReporte(currentReporteList);
}

function renderReporte(list) {
    currentReporteList = list;
    const tbody = document.getElementById('reporte-body');
    if (list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center p-4">No hay datos para este periodo. Haga clic en Procesar si acaba de sincronizar marcaciones.</td></tr>';
        return;
    }

    // Update icons
    if (window.TableSorter) {
        TableSorter.updateIcons('reporte', ['fecha', 'empleado', 'turno_nombre', 'minutos_atraso', 'horas_trabajadas', 'estado']);
    }

    tbody.innerHTML = list.map(row => {
        const estadoClass = {
            'OK': 'bg-success',
            'ATRASO': 'bg-warning text-dark',
            'INASISTENCIA': 'bg-danger',
            'ANOMALIA': 'bg-dark',
            'LIBRE': 'bg-secondary'
        }[row.estado] || 'bg-light text-dark';

        const entTeor = row.hora_entrada_teorica || '--:--:--';
        const entReal = row.hora_entrada_real || '--:--:--';
        const salTeor = row.hora_salida_teorica || '--:--:--';
        const salReal = row.hora_salida_real || '--:--:--';

        return `
            <tr>
                <td class="small fw-bold">${row.fecha}</td>
                <td>
                    <div class="fw-bold">${row.apellido_paterno} ${row.apellido_materno || ''} ${row.nombre}</div>
                    <div class="small text-muted">${row.rut}</div>
                </td>
                <td><small>${row.turno_nombre || 'Sin Turno'}</small></td>
                <td>
                    <div class="small text-muted">T: ${entTeor}</div>
                    <div class="fw-bold">R: ${entReal}</div>
                </td>
                <td>
                    <div class="small text-muted">T: ${salTeor}</div>
                    <div class="fw-bold">R: ${salReal}</div>
                </td>
                <td>${formatExactMinutesToTime(row.minutos_atraso || 0)}</td>
                <td>${formatExactMinutesToTime(row.minutos_colacion || 0)}</td>
                <td class="fw-bold text-primary">${formatExactMinutesToTime((row.horas_trabajadas || 0) * 60)}</td>
                <td><span class="badge ${estadoClass}">${row.estado}</span></td>
            </tr>
        `;
    }).join('');
}

async function triggerEngine() {
    const inicio = document.getElementById('rep-fecha-inicio').value;
    const fin = document.getElementById('rep-fecha-fin').value;
    const area = document.getElementById('rep-area')?.value || '';
    const turnoId = document.getElementById('rep-turno')?.value || '';

    if (!inicio || !fin) return alert("Seleccione un rango de fechas");

    // Armar descripción del filtro para el confirm
    let filtroDesc = `Del ${inicio} al ${fin}`;
    if (area) filtroDesc += ` · Área: ${area}`;
    if (turnoId) {
        const turnoText = document.getElementById('rep-turno')?.selectedOptions[0]?.text || turnoId;
        filtroDesc += ` · Horario: ${turnoText}`;
    }

    if (!confirm(`¿Reprocesar asistencia?\n\n${filtroDesc}\n\nEsta operación recalculará los datos del período con los filtros activos.`)) return;

    // Loader visual en el botón
    const btn = document.querySelector('button[onclick="triggerEngine()"]');
    const originalHtml = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    btn.disabled = true;

    try {
        // ── Construir URL con filtros ──────────────────────────────────────────
        // El endpoint /reproceso-masivo-async/ acepta: fecha_inicio, fecha_fin, area
        // El filtro de turno es solo para la vista, el backend filtra por area.
        let url = `${API_ASISTENCIA}reproceso-masivo-async/?fecha_inicio=${inicio}&fecha_fin=${fin}`;
        if (area) url += `&area=${encodeURIComponent(area)}`;

        const response = await fetch(url, { method: 'POST' });

        if (response.status === 423) {
            const err = await response.json();
            alert(`Ya hay un reprocesamiento en curso:\n${err.detail?.message || ''}`);
            return;
        }
        if (!response.ok) throw new Error(`Error ${response.status} al iniciar reprocesamiento`);

        // ── Polling de progreso ────────────────────────────────────────────────
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Reprocesando...';
        _pollReprocesoPeriodo(inicio, fin, area, () => {
            // Callback al terminar: recargar reporte con los mismos filtros
            btn.innerHTML = originalHtml;
            btn.disabled = false;
            loadReporte();
        });

    } catch (error) {
        console.error(error);
        alert("Error: " + error.message);
        btn.innerHTML = originalHtml;
        btn.disabled = false;
    }
}

/** Polling para reproceso masivo lanzado desde módulo Reportes */
function _pollReprocesoPeriodo(inicio, fin, area, onDone) {
    // Fix #D: Polling adaptativo — empieza en 2s, crece hasta 5s
    // Un reproceso típico de 20 empleados tarda ~45s → antes 22 consultas, ahora ~8
    let pollInterval = 2000;
    let timer = null;

    const tick = async () => {
        try {
            const r = await fetch(`${API_ASISTENCIA}reproceso-masivo-status/`);
            if (!r.ok) {
                timer = setTimeout(tick, pollInterval);
                return;
            }
            const s = await r.json();

            const pct = s.total > 0 ? Math.round((s.procesados / s.total) * 100) : 0;
            console.log(`[Reproceso] ${s.procesados}/${s.total} empleados (${pct}%) — estado: ${s.estado}`);

            if (s.estado === 'completado' || s.estado === 'done' || s.estado === 'completed') {
                showToast(
                    `✅ Reproceso completado: ${s.procesados} días procesados${s.errores > 0 ? ` (${s.errores} errores)` : ''}`,
                    s.errores > 0 ? 'warning' : 'success'
                );
                onDone();
                return; // no reencolar
            }

            // Proceso en curso → aumentar intervalo gradualmente (máx 5s)
            pollInterval = Math.min(pollInterval * 1.3, 5000);
            timer = setTimeout(tick, pollInterval);
        } catch (e) {
            console.warn('[Reproceso] Error en polling:', e);
            timer = setTimeout(tick, pollInterval);
        }
    };

    tick(); // primer tick inmediato
}

function formatExactMinutesToTime(minutos) {
    if (!minutos || isNaN(minutos)) return '00:00:00';
    let isNeg = minutos < 0;
    minutos = Math.abs(minutos);
    const mTotalStr = minutos.toString();
    const parts = mTotalStr.split('.');
    const m = parseInt(parts[0], 10);
    const sStr = parts.length > 1 ? '.' + parts[1] : '0';
    const s = Math.round(parseFloat(sStr) * 60);

    let finalH = Math.floor(m / 60);
    let finalM = m % 60;
    let finalS = s;

    if (finalS === 60) {
        finalS = 0;
        finalM += 1;
    }
    if (finalM === 60) {
        finalM = 0;
        finalH += 1;
    }

    const hh = String(finalH).padStart(2, '0');
    const mm = String(finalM).padStart(2, '0');
    const ss = String(finalS).padStart(2, '0');

    return (isNeg ? '-' : '') + `${hh}:${mm}:${ss}`;
}
