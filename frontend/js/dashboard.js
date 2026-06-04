let chartAsistenciaInstance = null;
let chartAusentismoInstance = null;
let chartEdadesInstance = null;
let chartContratosInstance = null;
let isDashboardInitialized = false;
let _dashDebounce = null;

// ─── Utilidades ───
function getFirstBusinessDay() {
    const now = new Date();
    let d = new Date(now.getFullYear(), now.getMonth(), 1);
    while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1);
    return d.toISOString().split('T')[0];
}
function fmtMin(m) {
    if (!m) return '0 min';
    const r = Math.round(m);
    const h = Math.floor(r / 60), min = r % 60;
    return h > 0 ? `${h}h ${min}m` : `${min} min`;
}
function severityBadge(val, thresholds = [10, 5]) {
    if (val >= thresholds[0]) return '<span class="badge" style="background:#fee2e2;color:#991b1b;font-size:0.65rem;">CRÍTICO</span>';
    if (val >= thresholds[1]) return '<span class="badge" style="background:#fef3c7;color:#92400e;font-size:0.65rem;">ALTO</span>';
    return '<span class="badge" style="background:#ecfdf5;color:#065f46;font-size:0.65rem;">MEDIO</span>';
}

// ─── Inicialización ───
async function initDashboard() {
    if (!document.getElementById('dash-area')) {
        setTimeout(initDashboard, 200);
        return;
    }
    if (isDashboardInitialized) return loadDashboard();
    try {
        await populateDashboardFilters();
        setupDashboardEventListeners();
        isDashboardInitialized = true;
        setTimeout(() => loadDashboard(), 300);
    } catch (error) {
        console.error("❌ Error en inicialización de Dashboard:", error);
    }
}

async function updateDashboardPeriodForArea(area) {
    const iniDate = document.getElementById('dash-fecha-inicio');
    const finDate = document.getElementById('dash-fecha-fin');
    if (!iniDate || !finDate) return;
    try {
        const areaName = area || 'Todas';
        const activeResp = await fetch(`/api/configuracion/periodos/activo/${encodeURIComponent(areaName)}/`, {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
        });
        if (activeResp.ok) {
            const activePeriod = await activeResp.json();
            if (activePeriod && activePeriod.fecha_inicio && activePeriod.fecha_fin) {
                iniDate.value = activePeriod.fecha_inicio;
                finDate.value = activePeriod.fecha_fin;
                console.log(`[Dashboard] Periodo activo para ${areaName} cargado:`, activePeriod);
            }
        }
    } catch (e) {
        console.error("Error cargando periodo activo en dashboard:", e);
    }
}

async function populateDashboardFilters() {
    try {
        const iniDate = document.getElementById('dash-fecha-inicio');
        const finDate = document.getElementById('dash-fecha-fin');

        // Fix #B: Reusar caché global de áreas (compartida con Empleados y Reportes).
        // Solo va a la red si es la primera vez en esta sesión.
        const [areasResult, turnosResult] = await Promise.allSettled([
            (async () => {
                if (window._cachedAreas) return { areas: window._cachedAreas };
                const r = await fetch('/api/empleados/stats/');
                if (!r.ok) return {};
                const stats = await r.json();
                window._cachedAreas = stats.areas || [];
                return stats;
            })(),
            fetch('/api/turnos/')
        ]);

        const areaSelect = document.getElementById('dash-area');
        if (areaSelect && areasResult.status === 'fulfilled') {
            const stats = areasResult.value;
            areaSelect.innerHTML = '<option value="Todas">Todas las Áreas</option>';
            (stats.areas || window._cachedAreas || []).forEach(a => {
                const opt = document.createElement('option');
                opt.value = a.area; opt.textContent = a.area;
                areaSelect.appendChild(opt);
            });
        }
        const horarioSelect = document.getElementById('dash-horario');
        if (horarioSelect && turnosResult.status === 'fulfilled') {
            const turnos = await turnosResult.value.json();
            horarioSelect.innerHTML = '<option value="Todos">Todos los Turnos</option>';
            (Array.isArray(turnos) ? turnos : []).forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id; opt.textContent = t.nombre;
                horarioSelect.appendChild(opt);
            });
        }

        // Carga inicial del período según el área por defecto
        if (iniDate && !iniDate.value) {
            const defaultArea = areaSelect ? areaSelect.value : 'Todas';
            await updateDashboardPeriodForArea(defaultArea);
        }
    } catch (e) { console.error("⚠️ Error poblando filtros:", e); }
}

async function updateHorarioFilter(area) {
    const horarioSelect = document.getElementById('dash-horario');
    if (!horarioSelect) return;
    try {
        const url = area === 'Todas' ? '/api/turnos/' : `/api/turnos/?area=${encodeURIComponent(area)}`;
        const res = await fetch(url);
        const turnos = await res.json();
        horarioSelect.innerHTML = '<option value="Todos">Todos los Turnos</option>';
        (Array.isArray(turnos) ? turnos : []).forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.id; opt.textContent = t.nombre;
            horarioSelect.appendChild(opt);
        });
    } catch (e) { console.error("⚠️ Error actualizando horarios:", e); }
}

function debouncedLoad() {
    clearTimeout(_dashDebounce);
    _dashDebounce = setTimeout(() => loadDashboard(), 400);
}

function setupDashboardEventListeners() {
    const areaSelect = document.getElementById('dash-area');
    const horarioSelect = document.getElementById('dash-horario');
    const iniDate = document.getElementById('dash-fecha-inicio');
    const finDate = document.getElementById('dash-fecha-fin');

    if (areaSelect) areaSelect.addEventListener('change', async () => {
        await updateHorarioFilter(areaSelect.value);
        await updateDashboardPeriodForArea(areaSelect.value);
        loadDashboard();
    });
    if (horarioSelect) horarioSelect.addEventListener('change', () => debouncedLoad());
    [iniDate, finDate].forEach(el => { if (el) el.addEventListener('change', () => debouncedLoad()); });
}

// ─── Carga Principal ───
async function loadDashboard() {
    const area = document.getElementById('dash-area')?.value || 'Todas';
    const horario = document.getElementById('dash-horario')?.value || 'Todos';
    const fechaInicioEl = document.getElementById('dash-fecha-inicio');
    const fechaFinEl = document.getElementById('dash-fecha-fin');
    if (!fechaInicioEl?.value || !fechaFinEl?.value) {
        fechaInicioEl.value = getFirstBusinessDay();
        fechaFinEl.value = new Date().toISOString().split('T')[0];
    }
    const fechaInicio = fechaInicioEl.value, fechaFin = fechaFinEl.value;
    try {
        const url = `/api/dashboard/analytics/?fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}&area=${area}&horario=${horario}&_v=${Date.now()}`;
        // [FIX] El interceptor global de auth.js ya inyecta el header Authorization.
        // No es necesario duplicarlo aquí; evitamos inconsistencias en refresh de token.
        const response = await fetch(url);
        if (response.status === 401) { AuthService.logout(); return; }
        if (response.status === 403) {
            console.warn("🚫 Acceso denegado a Dashboard (403). Redirigiendo.");
            const allowedItem = Array.from(document.querySelectorAll('.sidebar-item')).find(item => {
                const p = item.getAttribute('data-permiso');
                return !p || AuthService.hasPermission(p);
            });
            if (allowedItem) {
                switchPage(allowedItem.getAttribute('data-page'));
            } else {
                AuthService.logout("No tiene permisos para acceder al sistema.");
            }
            return;
        }
        const json = await response.json();
        if (json.status === 'success') {
            const d = json.data;
            renderParidad(d.fuerza_laboral?.hoy?.paridad || {});
            renderEdades(d.fuerza_laboral?.hoy?.edades || {}, d.fuerza_laboral?.edad_promedio || 0);
            renderAntiguedad(d.fuerza_laboral?.hoy?.antiguedad || {}, d.fuerza_laboral?.tasa_rotacion || 0);
            renderContratos(d.fuerza_laboral?.hoy?.contratos || {}, d.fuerza_laboral?.dotacion_activa || 0, d.fuerza_laboral?.contratos_por_vencer || 0);
            renderAsistenciaGlobal(d.matriz_asistencia || {}, d.fugas_operativas?.tasa_global_porcentaje || 0);
            renderAusentismo(d.origen_ausentismo || {});
            renderEmbudoProductividad(d.embudo_productividad || {});
            renderHeatmapGrid(d.heatmap_area_dia || []);
            renderTopInfractores(d.top_infractores || []);
            renderTopDeudores(d.top_deudores || []);
        }
    } catch (error) { console.error("Error cargando dashboard:", error); }
}

// ─── Renderizadores ───

function renderParidad(p) {
    const h = p.Hombres || 0, m = p.Mujeres || 0, t = p.Total || 0;
    const el = (id, v) => { const e = document.getElementById(id); if (e) e.innerText = v; };
    el('lbl-paridad-hombres', h); el('lbl-paridad-mujeres', m); el('lbl-paridad-total', t);
    const pctM = t > 0 ? ((h / t) * 100).toFixed(1) : 0;
    const pctF = t > 0 ? ((m / t) * 100).toFixed(1) : 0;
    el('lbl-paridad-pct-m', pctM + '%'); el('lbl-paridad-pct-f', pctF + '%');
    const barM = document.getElementById('bar-paridad-m');
    const barF = document.getElementById('bar-paridad-f');
    if (barM) barM.style.width = pctM + '%';
    if (barF) barF.style.width = pctF + '%';
}

function renderEdades(edadesData, edadPromedio) {
    const elProm = document.getElementById('lbl-edad-promedio');
    if (elProm) elProm.innerText = edadPromedio || 0;
    const ctx = document.getElementById('chart-edades');
    if (!ctx) return;
    if (chartEdadesInstance) chartEdadesInstance.destroy();
    const labels = Object.keys(edadesData);
    const data = Object.values(edadesData);
    chartEdadesInstance = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [{ label: 'Empleados', data, backgroundColor: 'rgba(139,92,246,0.6)', borderColor: '#8b5cf6', borderWidth: 1, borderRadius: 4 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, datalabels: { display: true, anchor: 'end', align: 'top', font: { size: 9, weight: 'bold' }, color: '#6b7280' } }, scales: { y: { beginAtZero: true, display: false }, x: { grid: { display: false }, ticks: { font: { size: 8 }, maxRotation: 45 } } } }
    });
}

function renderAntiguedad(antiData, tasaRotacion) {
    const total = Object.values(antiData).reduce((a, b) => a + b, 0) || 1;
    const r1 = antiData['less_1'] || 0, r2 = antiData['1_3'] || 0, r3 = antiData['3_5'] || 0, r4 = antiData['plus_5'] || 0;
    const pcts = [r1, r2, r3, r4].map(v => Math.round((v / total) * 100));
    ['seniority-1','seniority-2','seniority-3','seniority-4'].forEach((id, i) => {
        const el = document.getElementById(id);
        if (el) { el.innerText = pcts[i] + '%'; document.getElementById('bar-' + id).style.width = pcts[i] + '%'; }
    });
    const badge = document.getElementById('badge-rotacion');
    if (badge) badge.innerText = `Rotación: ${tasaRotacion}%`;
}

function renderContratos(conData, totalActivos, porVencer) {
    const ctx = document.getElementById('chart-contratos');
    if (!ctx) return;
    if (chartContratosInstance) chartContratosInstance.destroy();
    const elTotal = document.getElementById('lbl-contratos-total');
    if (elTotal) elTotal.innerText = totalActivos;
    const elVencer = document.getElementById('badge-vencer');
    if (elVencer) elVencer.innerText = `${porVencer} por vencer`;
    chartContratosInstance = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: Object.keys(conData), datasets: [{ data: Object.values(conData), backgroundColor: ['#10b981','#6366f1','#f59e0b','#0ea5e9','#f43f5e'], borderWidth: 2, borderColor: '#fff' }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: '70%', plugins: { legend: { position: 'right', labels: { boxWidth: 8, font: { size: 9 } } } } }
    });
}

function renderAsistenciaGlobal(matriz, fugasVal) {
    const esperado = matriz.esperado || 1, real = matriz.asistencia_real || 0;
    const pctAsis = ((real / esperado) * 100).toFixed(1);
    const pctPunt = (matriz.puntualidad_pct || 0).toFixed(1);
    const el = (id, v) => { const e = document.getElementById(id); if (e) e.innerText = v; };
    el('kpi-asistencia-real', pctAsis + '%');
    el('kpi-puntualidad', pctPunt + '%');
    el('kpi-fugas-globales', parseFloat(fugasVal).toFixed(1) + '%');
    const ctx = document.getElementById('chart-asistencia');
    if (!ctx) return;
    if (chartAsistenciaInstance) chartAsistenciaInstance.destroy();
    
    const tendencia = matriz.tendencia || [];
    
    // Mostramos todos los días del rango seleccionado (tengan o no marcas)
    const tendenciaFiltrada = tendencia;
    
    const labels = tendenciaFiltrada.map(t => {
        if (!t.fecha) return '';
        const dObj = new Date(t.fecha + 'T12:00:00');
        const fechaStr = dObj.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' });
        const diaSemana = dObj.toLocaleDateString('es-ES', { weekday: 'long' });
        const diaCapitalizado = diaSemana.charAt(0).toUpperCase() + diaSemana.slice(1);
        return [fechaStr, diaCapitalizado];
    });
    const asistencias = tendenciaFiltrada.map(t => t.asistencia || 0);
    const ausenciasJustificadas = tendenciaFiltrada.map(t => t.ausencia_justificada || 0);
    const inasistencias = tendenciaFiltrada.map(t => t.inasistencia || 0);
    const libres = tendenciaFiltrada.map(t => t.libres || 0);

    chartAsistenciaInstance = new Chart(ctx, {
        type: 'bar',
        data: { 
            labels, 
            datasets: [
                { 
                    label: 'Asistencias', 
                    data: asistencias, 
                    backgroundColor: 'hsla(142, 70%, 45%, 0.85)', 
                    borderColor: 'hsla(142, 70%, 45%, 1)', 
                    borderWidth: 1,
                    borderRadius: 4
                },
                { 
                    label: 'Ausencias Justificadas', 
                    data: ausenciasJustificadas, 
                    backgroundColor: 'hsla(200, 80%, 55%, 0.85)', 
                    borderColor: 'hsla(200, 80%, 55%, 1)', 
                    borderWidth: 1,
                    borderRadius: 4
                },
                { 
                    label: 'Inasistencias', 
                    data: inasistencias, 
                    backgroundColor: 'hsla(350, 75%, 55%, 0.85)', 
                    borderColor: 'hsla(350, 75%, 55%, 1)', 
                    borderWidth: 1,
                    borderRadius: 4
                },
                { 
                    label: 'Días Libres / Feriados', 
                    data: libres, 
                    backgroundColor: 'hsla(210, 16%, 82%, 0.75)', 
                    borderColor: 'hsla(210, 16%, 82%, 1)', 
                    borderWidth: 1,
                    borderRadius: 4
                }
            ] 
        },
        options: { 
            responsive: true, 
            maintainAspectRatio: false, 
            interaction: { mode: 'index', intersect: false },
            plugins: { 
                legend: { 
                    position: 'top',
                    labels: { boxWidth: 12, font: { size: 10 } } 
                }, 
                datalabels: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            // Ocultar Días Libres del listado numérico
                            if (context.dataset.label.includes('Días Libres')) {
                                return null;
                            }
                            return context.dataset.label + ': ' + context.raw;
                        },
                        footer: function(tooltipItems) {
                            if (!tooltipItems || tooltipItems.length === 0) return '';
                            const dataIndex = tooltipItems[0].dataIndex;
                            const item = tendenciaFiltrada[dataIndex];
                            if (item) {
                                const req = (item.asistencia || 0) + (item.ausencia_justificada || 0) + (item.inasistencia || 0);
                                if (req === 0) {
                                    return 'Feriado / Día Libre General';
                                }
                            }
                            return '';
                        }
                    }
                }
            },
            scales: { 
                y: { 
                    stacked: true,
                    beginAtZero: true, 
                    grid: { color: '#f1f5f9' },
                    ticks: { font: { size: 9 } }
                }, 
                x: { 
                    stacked: true,
                    grid: { display: false }, 
                    ticks: { font: { size: 9 } } 
                } 
            }
        }
    });
}

function getSemanticColorForAbsence(reason) {
    const r = (reason || '').toUpperCase();
    if (r.includes('VACACION') || r.includes('CUMPLEAÑOS') || r.includes('DIA COMPENSATORIO') || r.includes('TRAMITE') || r.includes('ADMINISTRATIVO')) return '#3b82f6';
    if (r.includes('LICENCIA') || r.includes('MUTUAL') || r.includes('DUELO') || r.includes('ENFERMEDAD')) return '#f59e0b';
    if (r.includes('FALTA INJUSTIFICADA') || r.includes('INASISTENCIA') || r.includes('SANCION')) return '#ef4444';
    return '#94a3b8';
}

function renderAusentismo(ausData) {
    const container = document.getElementById('trellis-ausentismo-container');
    if (!container) return;
    
    // Si existía un gráfico Chart.js previo, destruirlo (para evitar fugas de memoria si se alternó entre versiones)
    if (typeof chartAusentismoInstance !== 'undefined' && chartAusentismoInstance) {
        chartAusentismoInstance.destroy();
    }
    
    container.innerHTML = '';
    
    const desgloses = ausData.desglose || [];
    if (desgloses.length === 0) {
        container.innerHTML = '<div class="text-center text-muted w-100 mt-4" style="font-size:0.8rem;">No hay ausentismo en este periodo.</div>';
        return;
    }

    const totalDays = desgloses.reduce((sum, d) => sum + d.dias, 0);
    const maxDays = Math.max(...desgloses.map(d => d.dias), 1); // Escala unificada base

    // Definición de las Categorías Maestras
    const categories = [
        { id: 'Costo Empleador', title: 'COSTO EMPLEADOR', color: '#3b82f6', items: [] },
        { id: 'Descuento a Empleado', title: 'DESCUENTO A EMPLEADO', color: '#ef4444', items: [] },
        { id: 'Costo Externo', title: 'COSTO EXTERNO', color: '#f59e0b', items: [] }
    ];

    // Agrupar
    desgloses.forEach(d => {
        const cat = categories.find(c => c.id === d.pagador);
        if (cat) cat.items.push(d);
    });

    let html = '';

    categories.forEach((cat, index) => {
        if (cat.items.length === 0) return;

        // Ordenar ítems de mayor a menor
        cat.items.sort((a, b) => b.dias - a.dias);

        const catDays = cat.items.reduce((sum, d) => sum + d.dias, 0);
        const catPercent = ((catDays / totalDays) * 100).toFixed(1);

        // Divider (excepto el primero)
        if (index > 0) {
            html += `<hr class="my-1 border-secondary" style="opacity: 0.15;">`;
        }

        // Header de Panel
        html += `
            <div class="mb-1">
                <div class="d-flex align-items-center mb-1">
                    <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background-color: ${cat.color}; margin-right:8px;"></span>
                    <span class="text-secondary fw-bold" style="font-size:0.75rem; letter-spacing:0.5px;">${cat.title} | ${catPercent}% del ausentismo (${catDays} días)</span>
                </div>
        `;

        // Agrupar en Top 2 y Otros para ahorrar espacio
        const MAX_ITEMS = 2;
        let topItems = cat.items.slice(0, MAX_ITEMS);
        let otrosItems = cat.items.slice(MAX_ITEMS);
        
        if (otrosItems.length > 0) {
            const otrosDias = otrosItems.reduce((sum, item) => sum + item.dias, 0);
            topItems.push({ tipo: 'Otros (' + otrosItems.length + ')', dias: otrosDias });
        }

        // Barras
        topItems.forEach(item => {
            const barWidth = (item.dias / maxDays) * 100;
            const safeTipo = item.tipo.replace(/'/g, "\\'");
            const isOtros = item.tipo.startsWith('Otros');
            const clickAction = isOtros ? "" : `onclick="showDesviacionesDetalle('justificacion', '${safeTipo}')"`;
            const cursorStyle = isOtros ? "cursor: default;" : "cursor: pointer; transition: opacity 0.2s;";
            const hoverAction = isOtros ? "" : `onmouseover="this.style.opacity=0.8" onmouseout="this.style.opacity=1"`;

            html += `
                <div class="d-flex align-items-center mb-1" style="${cursorStyle} line-height: 1;" ${hoverAction} ${clickAction}>
                    <div style="width: 120px; font-size: 0.7rem; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; font-family: monospace;" class="${isOtros ? 'text-muted' : 'text-secondary'}" title="${item.tipo}">
                        ${item.tipo}
                    </div>
                    <div class="flex-grow-1 mx-2 bg-light" style="height: 12px; border-radius: 2px;">
                        <div style="width: ${barWidth}%; background-color: ${isOtros ? '#cbd5e1' : cat.color}; height: 100%; border-radius: 2px; opacity: ${isOtros ? '0.7' : '1'}"></div>
                    </div>
                    <div style="width: 30px; text-align: right; font-size: 0.7rem; font-family: monospace;" class="text-muted">
                        ${item.dias}d
                    </div>
                </div>
            `;
        });

        html += `</div>`;
    });

    container.innerHTML = html;
}

function renderEmbudoProductividad(data) {
    const container = document.getElementById('bullet-chart-container');
    if (!container) return;
    
    // Formateador numérico para miles con 1 decimal (ej. 1,500.5)
    const formatNum = (val) => Number(val).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    
    const prog = data.programadas || 0;
    const trabBrutas = data.trabajadas || 0;
    const fuga = data.horas_fuga || 0;
    
    // Sobretiempo (HE + JE)
    const heRegularesHrs = parseFloat((Math.round((data.he_regulares_min || 0) / 60.0 * 10) / 10).toFixed(1));
    const jeHrs = parseFloat((Math.round((data.jornadas_especiales_min || 0) / 60.0 * 10) / 10).toFixed(1));
    const extra = parseFloat((heRegularesHrs + jeHrs).toFixed(1));
    
    // Neto trabajado (dentro de la jornada ordinaria)
    const trabNetas = parseFloat(Math.max(0, trabBrutas - extra).toFixed(1));
    
    // Regla de Cuadratura Estricta: Neto + Fugas + Ausencias = Programadas
    const ausencias = parseFloat(Math.max(0, prog - trabNetas - fuga).toFixed(1));
    
    // Motor de Escalabilidad Visual (Soporte para Turnos Dobles)
    const totalFisico = trabBrutas; // Neto + Sobretiempo
    const maxVal = Math.max(prog, totalFisico);
    const maxScale = maxVal > 0 ? maxVal * 1.08 : 1; // 8% margen derecho para evitar corte de labels
    
    const progPct = (prog / maxScale) * 100;
    const netoPct = (trabNetas / maxScale) * 100;
    const extraPct = (extra / maxScale) * 100;
    
    // Prevención de colisión (Si la barra Neto se acerca a menos del 5% de Programadas, oculta etiqueta Neto sup.)
    const overlapNetoProg = Math.abs(netoPct - progPct) < 5;
    
    // Prevención de colisión para la etiqueta del Total vs Programadas
    const totalPct = netoPct + extraPct;
    const overlapTotalProg = Math.abs(totalPct - progPct) < 15;
    
    // Porcentajes para desglose
    const baseProg = Math.max(prog, 1);
    const fugaPctStr = ((fuga / baseProg) * 100).toFixed(1);
    const ausenciasPctStr = ((ausencias / baseProg) * 100).toFixed(1);
    
    // Cumplimiento estricto (1 decimal exacto)
    const effStr = prog > 0 ? ((trabNetas / prog) * 100).toFixed(1) : "0.0";
    
    const badgeEff = document.getElementById('badge-eficiencia');
    if (badgeEff) {
        badgeEff.innerText = `Indicador de Cumplimiento: ${effStr}%`;
    }
    
    const jeCount = data.jornadas_especiales_count || 0;
    
    let html = `
        <div class="mb-2">
            <div class="d-flex justify-content-between text-muted" style="font-size: 0.72rem; border-bottom: 1px dashed #cbd5e1; padding-bottom: 4px; margin-bottom: 8px;">
                <span>Horas Programadas: <strong style="color: #334155;">${formatNum(prog)} hrs</strong></span>
                <span>Total Físico: <strong style="color: #334155;">${formatNum(trabBrutas)} hrs</strong></span>
            </div>
            
            <!-- Eje Superior -->
            <div class="position-relative" style="height: ${overlapTotalProg ? '28px' : '16px'}; margin-top: 15px; transition: height 0.3s;">
                <div class="position-absolute text-truncate" style="left: 0; top: 0; font-size: 0.65rem; color: #64748b;">0h</div>
                
                ${trabNetas > 0 && !overlapNetoProg ? `
                <div class="position-absolute text-truncate" style="left: ${netoPct}%; top: 0; transform: translateX(-50%); font-size: 0.65rem; color: #64748b; max-width: 40px; text-align: center;">
                    ${formatNum(trabNetas)}h
                </div>` : ''}
                
                <!-- Etiqueta del Marcador Vertical (Prioridad) -->
                <div class="position-absolute text-truncate" style="left: ${progPct}%; top: ${overlapTotalProg ? '12px' : '0'}; transform: translateX(-50%); font-size: 0.65rem; color: #6366f1; font-weight: bold; z-index: 10;">
                    ${formatNum(prog)}h (Programadas)
                </div>
                
                ${extra > 0 ? `
                <div class="position-absolute text-truncate" style="left: ${totalPct}%; top: 0; transform: translateX(-50%); font-size: 0.65rem; color: #64748b; font-weight: bold;">
                    ${formatNum(totalFisico)}h
                </div>` : ''}
            </div>
            
            <!-- Gráfico de Bala -->
            <div class="position-relative" style="height: 32px; margin-bottom: 8px; border-radius: 4px; background: #f8fafc;">
                <!-- Eje punteado horizontal base -->
                <div class="position-absolute" style="left: 0; right: 0; top: 50%; border-top: 1px dashed #cbd5e1; z-index: 0;"></div>
                
                <!-- Barra Neto (Azul oscuro) -->
                <div class="position-absolute d-flex align-items-center" style="left: 0; top: 6px; height: 20px; width: ${netoPct}%; background: #334155; z-index: 1; transition: width 0.5s ease-in-out; overflow: hidden; white-space: nowrap;">
                    <span class="px-1" style="color: #fff; font-size: 0.65rem; z-index: 2;">NETO: ${formatNum(trabNetas)} hrs</span>
                </div>
                
                <!-- Barra Sobretiempo (Naranja/Amarillo texturizado, anclada) -->
                ${extraPct > 0 ? `
                <div class="position-absolute d-flex align-items-center" style="left: ${netoPct}%; top: 6px; height: 20px; width: ${extraPct}%; background: repeating-linear-gradient(45deg, #f59e0b, #f59e0b 4px, #fbbf24 4px, #fbbf24 8px); opacity: 0.95; z-index: 2; border-left: 1px solid #fff; transition: width 0.5s ease-in-out;">
                </div>
                ` : ''}
                
                <!-- Marcador de Jornada Programada (Línea Vertical Absoluta) -->
                <div class="position-absolute d-flex flex-column align-items-center" style="left: ${progPct}%; top: 0; bottom: 0; z-index: 5; transform: translateX(-50%);">
                    <div style="width: 2px; height: 100%; background: #4f46e5; box-shadow: 0 0 2px rgba(0,0,0,0.3);"></div>
                </div>
            </div>
            
            <!-- Etiqueta inferior del Sobretiempo -->
            ${extra > 0 ? `
            <div class="text-end text-truncate" style="font-size: 0.7rem; color: #475569; margin-top: -4px; margin-bottom: 4px;">
                Sobretiempo: <strong>${formatNum(extra)} hrs</strong> <span class="text-muted">(${formatNum(heRegularesHrs)}h HE | ${formatNum(jeHrs)}h JE)</span>
            </div>
            ` : '<div style="height: 12px;"></div>'}
            
            <!-- Desglose Estricto (Neto + Fugas + Ausencias = Programadas) -->
            <div style="border-top: 1px dashed #cbd5e1; margin-top: 10px; padding-top: 8px; font-size: 0.72rem; color: #475569;">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <span>Fugas Registradas:</span>
                    <div>
                        <strong>${formatNum(fuga)} hrs <span class="text-muted">(${fugaPctStr}%)</span></strong>
                        ${fuga > 0 ? `<button class="btn btn-sm btn-link text-primary p-0 ms-1" onclick="showDesviacionesDetalle('fuga')" title="Ver Detalle"><i class="bi bi-search"></i></button>` : ''}
                    </div>
                </div>
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <span title="Diferencia exacta para cuadratura matemática" style="cursor: help; border-bottom: 1px dotted #94a3b8;">Ausencias/Descuadres:</span>
                    <div>
                        <strong>${formatNum(ausencias)} hrs <span class="text-muted">(${ausenciasPctStr}%)</span></strong>
                        ${ausencias > 0 ? `<button class="btn btn-sm btn-link text-primary p-0 ms-1" onclick="showDesviacionesDetalle('ausencia')" title="Ver Detalle"><i class="bi bi-search"></i></button>` : ''}
                    </div>
                </div>
                <div class="d-flex justify-content-between align-items-center mt-2 p-1 rounded" style="background: #f8fafc; border: 1px solid #e2e8f0; overflow: hidden;">
                    <span class="badge text-truncate" style="background: #e0e7ff; color: #4338ca; max-width: 50%;"><i class="bi bi-calendar-event me-1"></i>J. ESPECIALES</span>
                    <span class="text-truncate" style="font-size: 0.7rem; text-align: right; max-width: 48%;">${jeCount} jornada${jeCount !== 1 ? 's' : ''} (+${formatNum(jeHrs)}h)</span>
                </div>
            </div>
        </div>
    `;
    
    container.innerHTML = html;
    
    if (document.getElementById('lbl-fugas-diarias')) {
        document.getElementById('lbl-fugas-diarias').innerText = `${formatNum(fuga)} hrs`;
    }
}

// ============================================
// MODAL DE DETALLES DE DESVIACIONES
// ============================================
async function showDesviacionesDetalle(tipo, motivo = null) {
    const area = document.getElementById('dash-area')?.value || 'Todas';
    const horario = document.getElementById('dash-horario')?.value || 'Todos';
    const fechaInicio = document.getElementById('dash-fecha-inicio')?.value;
    const fechaFin = document.getElementById('dash-fecha-fin')?.value;

    if (!fechaInicio || !fechaFin) {
        showToast("Error", "Filtros de fecha no válidos", "error");
        return;
    }
    
    let titulo = '';
    if (tipo === 'fuga') titulo = 'Detalle de Fugas (Atrasos/Salidas)';
    else if (tipo === 'ausencia') titulo = 'Detalle de Ausencias y Descuadres';
    else if (tipo === 'justificacion') titulo = `Detalle de Ausentismo: ${motivo}`;
    
    document.getElementById('lbl-desviaciones-titulo').innerText = titulo;
    
    const tbody = document.getElementById('tbody-desviaciones-detalle');
    const loading = document.getElementById('loading-desviaciones');
    
    tbody.innerHTML = '';
    loading.classList.remove('d-none');
    
    const modal = new bootstrap.Modal(document.getElementById('modal-desviaciones-detalle'));
    modal.show();
    
    try {
        const token = localStorage.getItem('token');
        const url = new URL(`${window.location.origin}/api/dashboard/desviaciones/detalle/`);
        url.searchParams.append('fecha_inicio', fechaInicio);
        url.searchParams.append('fecha_fin', fechaFin);
        url.searchParams.append('tipo', tipo);
        if (motivo) url.searchParams.append('motivo', motivo);
        if (area !== 'Todas') url.searchParams.append('area', area);
        if (horario !== 'Todos') url.searchParams.append('horario', horario);
        
        const response = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        const res = await response.json();
        loading.classList.add('d-none');
        
        if (res.status === 'success' && res.data.length > 0) {
            tbody.innerHTML = res.data.map(r => {
                const prog = r.horas_teoricas || 0;
                const trab = r.horas_trabajadas || 0;
                const deuda = (r.minutos_deuda || 0) / 60.0;
                const missing = Math.max(0, prog - trab - deuda).toFixed(1);
                
                let valStr = '';
                if (tipo === 'fuga') {
                    valStr = fmtMin(r.minutos_deuda);
                } else {
                    valStr = `${missing} hrs`;
                }
                
                return `
                    <tr>
                        <td>${window.formatFechaDDMMYYYY(r.fecha)}</td>
                        <td class="text-truncate" style="max-width: 150px;" title="${r.empleado}">${r.empleado}</td>
                        <td><span class="badge bg-secondary">${r.estado}</span></td>
                        <td class="text-end">${prog.toFixed(1)}h</td>
                        <td class="text-end">${trab.toFixed(1)}h</td>
                        <td class="text-end text-danger fw-bold">${valStr}</td>
                    </tr>
                `;
            }).join('');
            
            if (res.data.length === 100) {
                tbody.innerHTML += `<tr><td colspan="6" class="text-center text-muted fst-italic">Limitado a los últimos 100 registros...</td></tr>`;
            }
        } else {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No se encontraron registros de ${tipo}</td></tr>`;
        }
    } catch (e) {
        console.error(e);
        loading.classList.add('d-none');
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">Error al cargar datos</td></tr>`;
    }
}

function renderHeatmapGrid(data) {
    const container = document.getElementById('heatmap-grid');
    if (!container) return;
    if (!data || data.length === 0) { container.innerHTML = '<p class="text-center text-muted small py-4">Sin datos de fugas en el periodo</p>'; return; }
    const dias = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
    const areas = [...new Set(data.map(d => d.area))];
    const matrix = {};
    let maxFuga = 0;
    data.forEach(d => {
        const k = `${d.area}_${d.dia}`;
        matrix[k] = d.fugas_min || 0;
        if (matrix[k] > maxFuga) maxFuga = matrix[k];
    });
    const getColor = (v) => {
        if (!v || v === 0) return '#f8fafc';
        const ratio = v / (maxFuga || 1);
        if (ratio > 0.7) return '#fca5a5';
        if (ratio > 0.4) return '#fdba74';
        if (ratio > 0.15) return '#fde68a';
        return '#bbf7d0';
    };
    let html = '<table class="table table-sm mb-0" style="font-size:0.7rem;"><thead><tr><th style="font-size:0.65rem;">Área</th>';
    dias.forEach((d, i) => { if (i > 0 && i < 6) html += `<th class="text-center" style="font-size:0.65rem;">${d}</th>`; });
    html += '</tr></thead><tbody>';
    areas.forEach(area => {
        html += `<tr><td class="fw-bold" style="font-size:0.68rem;white-space:nowrap;">${area}</td>`;
        for (let i = 1; i <= 5; i++) {
            const v = matrix[`${area}_${i}`] || 0;
            html += `<td class="text-center" style="background:${getColor(v)};border-radius:3px;cursor:help;" title="${area} - ${dias[i]}: ${fmtMin(v)}">${v > 0 ? Math.round(v) : '-'}</td>`;
        }
        html += '</tr>';
    });
    html += '</tbody></table>';
    container.innerHTML = html;
}

function renderTopInfractores(data) {
    const tbody = document.getElementById('tabla-infractores');
    if (!tbody) return;
    if (!data || data.length === 0) { tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-3">Sin infractores en el periodo</td></tr>'; return; }
    const maxEv = Math.max(...data.map(d => d.eventos));
    tbody.innerHTML = data.map((r, i) => {
        const nivel = r.eventos >= maxEv * 0.7 ? severityBadge(10) : r.eventos >= maxEv * 0.4 ? severityBadge(7) : severityBadge(2);
        return `<tr style="${i < 3 ? 'border-left:3px solid #ef4444;' : ''}">
            <td class="fw-bold">${i + 1}</td>
            <td style="white-space:nowrap;">${r.nombre || 'N/D'}</td>
            <td><span class="badge bg-light text-dark" style="font-size:0.65rem;">${r.area}</span></td>
            <td class="text-center fw-bold">${r.eventos}</td>
            <td class="text-center" title="${fmtMin(r.min_atraso)}">${fmtMin(r.min_atraso)}</td>
            <td class="text-center" title="${fmtMin(r.min_sad)}">${fmtMin(r.min_sad)}</td>
            <td class="text-center">${nivel}</td>
        </tr>`;
    }).join('');
}

function renderTopDeudores(data) {
    const tbody = document.getElementById('tabla-deudores');
    if (!tbody) return;
    if (!data || data.length === 0) { tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-3">Sin deudores en el periodo</td></tr>'; return; }
    const maxD = Math.max(...data.map(d => d.deuda_min));
    tbody.innerHTML = data.map((r, i) => {
        const pct = ((r.deuda_min / (maxD || 1)) * 100).toFixed(0);
        const impacto = r.deuda_hrs >= 15 ? severityBadge(10) : r.deuda_hrs >= 8 ? severityBadge(7) : severityBadge(2);
        return `<tr style="${i < 3 ? 'border-left:3px solid #f59e0b;' : ''}">
            <td class="fw-bold">${i + 1}</td>
            <td style="white-space:nowrap;">${r.nombre || 'N/D'}</td>
            <td><span class="badge bg-light text-dark" style="font-size:0.65rem;">${r.area}</span></td>
            <td class="text-center fw-bold">${r.deuda_hrs} hrs</td>
            <td class="text-center">${r.dias}</td>
            <td class="text-center">${impacto}</td>
        </tr>`;
    }).join('');
}

// CSS animation
if (!document.getElementById('dash-animations')) {
    const style = document.createElement('style');
    style.id = 'dash-animations';
    style.textContent = `@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}`;
    document.head.appendChild(style);
}

window.initDashboard = initDashboard;
