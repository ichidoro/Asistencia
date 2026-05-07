// ─────────────────────────────────────────────────────────────────────────────
// CIERRE DE PERIODO UI — Semáforo v2 (4 niveles: 3 Hard Stops + 1 Soft Stop)
// Tela de araña: evaluar → semáforo → botón → acta PDF
// ─────────────────────────────────────────────────────────────────────────────

async function initCierreUI() {
    const areaSelect = document.getElementById('cierre-area');
    if (!areaSelect) return;
    areaSelect.innerHTML = '';

    try {
        const res = await fetch('/api/empleados/areas', {
            headers: { 'Authorization': `Bearer ${AuthService.token}` }
        });
        const areas = await res.json();

        let validAreas = areas;
        if (AuthService.session && AuthService.session.rol_global !== 1) {
            validAreas = areas.filter(a => AuthService.session.areas.includes(a.nombre));
        }

        validAreas.forEach(a => {
            const opt = document.createElement('option');
            opt.value = a.nombre;
            opt.textContent = a.nombre;
            areaSelect.appendChild(opt);
        });

        // Fechas iniciales: mes anterior completo
        const hoy = new Date();
        const primerDia = new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1);
        const ultimoDia = new Date(hoy.getFullYear(), hoy.getMonth(), 0);
        document.getElementById('cierre-fecha-inicio').value = primerDia.toISOString().split('T')[0];
        document.getElementById('cierre-fecha-fin').value = ultimoDia.toISOString().split('T')[0];

        // Listeners
        const chk = document.getElementById('cierre-chk-aceptar-ina');
        if (chk) chk.addEventListener('change', checkCierreButtonState);
    } catch (e) {
        console.error('Error init Cierre UI:', e);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// EVALUAR — llama a /api/cierre/pre-evaluacion y renderiza el semáforo
// ─────────────────────────────────────────────────────────────────────────────
async function evaluarCierre() {
    const fInicio = document.getElementById('cierre-fecha-inicio').value;
    const fFin    = document.getElementById('cierre-fecha-fin').value;
    const area    = document.getElementById('cierre-area').value;

    if (!fInicio || !fFin || !area) {
        alerts.warning('Por favor complete las fechas y el área.');
        return;
    }

    const btnEvaluar = document.getElementById('btn-evaluar-cierre');
    if (btnEvaluar) { btnEvaluar.disabled = true; btnEvaluar.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Evaluando...'; }

    try {
        const res = await fetch(
            `/api/cierre/pre-evaluacion?fecha_inicio=${fInicio}&fecha_fin=${fFin}&area=${encodeURIComponent(area)}`,
            { headers: { 'Authorization': `Bearer ${AuthService.token}` } }
        );
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error al evaluar cierre');

        window.currentEvaluacion = data;

        // Limpiar zona de resultados
        const zona = document.getElementById('cierre-resultados');
        if (zona) {
            zona.classList.remove('d-none');
            zona.innerHTML = _renderSemaforo(data, fInicio, fFin, area);
        }

        // Re-enganchar listener del checkbox (se recreó)
        const chk = document.getElementById('cierre-chk-aceptar-ina');
        if (chk) chk.addEventListener('change', checkCierreButtonState);

        checkCierreButtonState();

    } catch (e) {
        alerts.error(e.message);
    } finally {
        if (btnEvaluar) { btnEvaluar.disabled = false; btnEvaluar.innerHTML = '<i class="bi bi-search"></i> Evaluar'; }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// RENDER SEMÁFORO — construye el HTML de los 4 niveles
// ─────────────────────────────────────────────────────────────────────────────
function _renderSemaforo(data, fInicio, fFin, area) {
    const blocks = [];

    // ── HARD STOP 1: Horas extras pendientes ──────────────────────────────
    if (data.he_pendientes > 0) {
        const detalleRows = (data.detalle_he || []).map(r =>
            `<li>${r.nombre_completo} — ${r.fecha}</li>`
        ).join('');
        blocks.push(`
        <div class="alert alert-danger border-0 shadow-sm mb-3" id="cierre-alert-he">
            <div class="d-flex align-items-start gap-2">
                <i class="bi bi-octagon-fill fs-4 text-danger"></i>
                <div class="flex-fill">
                    <strong>🔴 BLOQUEO CRÍTICO — Horas Extras Pendientes</strong>
                    <p class="mb-1 mt-1">No puedes cerrar el mes. Tienes <strong>${data.he_pendientes}</strong> hora(s) extra pendiente(s) de validación.</p>
                    <p class="mb-2 small text-muted">Aprueba o rechaza cada una antes de continuar. Haz doble clic en el nombre del empleado en la grilla de marcaciones para abrir el panel de validación.</p>
                    <details>
                        <summary class="small text-danger fw-bold" style="cursor:pointer">Ver listado (${data.he_pendientes})</summary>
                        <ul class="mt-2 small mb-0">${detalleRows}</ul>
                    </details>
                </div>
            </div>
        </div>`);
    }

    // ── HARD STOP 2: Anomalías sin corregir ───────────────────────────────
    if (data.anomalias > 0) {
        const detalleRows = (data.detalle_anomalias || []).map(r =>
            `<li>${r.nombre_completo} — ${r.fecha} ${r.hora_entrada_real ? '(Ent: ' + r.hora_entrada_real + ')' : ''} ${r.hora_salida_real ? '(Sal: ' + r.hora_salida_real + ')' : ''}</li>`
        ).join('');
        blocks.push(`
        <div class="alert alert-danger border-0 shadow-sm mb-3" id="cierre-alert-anomalias">
            <div class="d-flex align-items-start gap-2">
                <i class="bi bi-exclamation-octagon-fill fs-4 text-danger"></i>
                <div class="flex-fill">
                    <strong>🔴 BLOQUEO CRÍTICO — Anomalías Sin Corregir</strong>
                    <p class="mb-1 mt-1">Existen <strong>${data.anomalias}</strong> marcación(es) incompletas que deben resolverse.</p>
                    <p class="mb-2 small text-muted">En la grilla de marcaciones, localiza la celda amarilla/roja con el ícono ⚠️, agrega la marcación faltante (entrada o salida) y el motor recalculará automáticamente.</p>
                    <details>
                        <summary class="small text-danger fw-bold" style="cursor:pointer">Ver listado (${data.anomalias})</summary>
                        <ul class="mt-2 small mb-0">${detalleRows}</ul>
                    </details>
                </div>
            </div>
        </div>`);
    }

    // ── HARD STOP 3: Turnos EN_CURSO activos ──────────────────────────────
    if (data.en_curso > 0) {
        const detalleRows = (data.detalle_en_curso || []).map(r =>
            `<li>${r.nombre_completo} — ${r.fecha}${r.hora_salida_teorica ? ' (salida teórica: ' + r.hora_salida_teorica + ')' : ''}</li>`
        ).join('');
        const mensajeHora = data.ultimo_fin_estimado
            ? `El último turno activo finaliza aprox. a las <strong>${data.ultimo_fin_estimado}</strong>. Puedes intentar el cierre después de esa hora.`
            : 'Espera a que finalicen todos los turnos activos antes de cerrar.';
        blocks.push(`
        <div class="alert alert-danger border-0 shadow-sm mb-3" id="cierre-alert-en-curso">
            <div class="d-flex align-items-start gap-2">
                <i class="bi bi-clock-fill fs-4 text-danger"></i>
                <div class="flex-fill">
                    <strong>🔴 BLOQUEO CRÍTICO — Turnos Activos (EN CURSO)</strong>
                    <p class="mb-1 mt-1">Hay <strong>${data.en_curso}</strong> empleado(s) con turno activo en el periodo.</p>
                    <p class="mb-2 small text-muted">${mensajeHora}</p>
                    <details>
                        <summary class="small text-danger fw-bold" style="cursor:pointer">Ver listado (${data.en_curso})</summary>
                        <ul class="mt-2 small mb-0">${detalleRows}</ul>
                    </details>
                </div>
            </div>
        </div>`);
    }

    // ── SOFT STOP: Inasistencias injustificadas ────────────────────────────
    if (data.inasistencias_injustificadas > 0) {
        const detalleRows = (data.detalle_ina || []).map(r =>
            `<li>${r.nombre_completo} — ${r.fecha}</li>`
        ).join('');
        blocks.push(`
        <div class="alert alert-warning border-0 shadow-sm mb-3" id="cierre-alert-ina">
            <div class="d-flex align-items-start gap-2">
                <i class="bi bi-exclamation-triangle-fill fs-4 text-warning"></i>
                <div class="flex-fill">
                    <strong>⚠️ ADVERTENCIA — Inasistencias Sin Justificar</strong>
                    <p class="mb-1 mt-1">Existen <strong>${data.inasistencias_injustificadas}</strong> inasistencia(s) sin justificación en el periodo.</p>
                    <details class="mb-2">
                        <summary class="small text-warning fw-bold" style="cursor:pointer">Ver listado (${data.inasistencias_injustificadas})</summary>
                        <ul class="mt-2 small mb-0">${detalleRows}</ul>
                    </details>
                    <div class="form-check mt-1">
                        <input class="form-check-input" type="checkbox" id="cierre-chk-aceptar-ina">
                        <label class="form-check-label small" for="cierre-chk-aceptar-ina">
                            Comprendo que hay inasistencias injustificadas y asumo la responsabilidad de este cierre.
                        </label>
                    </div>
                </div>
            </div>
        </div>`);
    }

    // ── VERDE: Todo OK ─────────────────────────────────────────────────────
    if (data.he_pendientes === 0 && data.anomalias === 0 && data.en_curso === 0 && data.inasistencias_injustificadas === 0) {
        blocks.push(`
        <div class="alert alert-success border-0 shadow-sm mb-3" id="cierre-alert-ok">
            <div class="d-flex align-items-center gap-2">
                <i class="bi bi-check-circle-fill fs-4 text-success"></i>
                <div>
                    <strong>✅ Periodo listo para cerrar</strong>
                    <p class="mb-0 small">No se encontraron bloqueos. Puedes sellar el periodo.</p>
                </div>
            </div>
        </div>`);
    }

    // ── Resumen ejecutivo ──────────────────────────────────────────────────
    const rsm = data.resumen || {};
    const feriados = (data.feriados_periodo || []).map(f => `${f.fecha}: ${f.descripcion}`).join(' | ') || 'Ninguno';
    blocks.push(`
    <div class="card border-0 shadow-sm mb-3">
        <div class="card-header py-2 bg-transparent fw-bold small">📊 Resumen del Periodo — ${fInicio} al ${fFin}</div>
        <div class="card-body py-2">
            <div class="row row-cols-2 row-cols-md-4 g-2 small">
                <div class="col"><span class="text-muted">Empleados:</span> <strong>${rsm.total_empleados || 0}</strong></div>
                <div class="col"><span class="text-muted">Días OK:</span> <strong>${rsm.dias_ok || 0}</strong></div>
                <div class="col"><span class="text-muted">Con novedad:</span> <strong>${rsm.dias_con_novedad || 0}</strong></div>
                <div class="col"><span class="text-muted">Inasistencias:</span> <strong>${rsm.inasistencias || 0}</strong></div>
                <div class="col"><span class="text-muted">HE aprobadas:</span> <strong>${data.resumen?.he_aprobadas_horas || 0} hrs</strong></div>
                <div class="col"><span class="text-muted">Jornadas Esp.:</span> <strong>${rsm.jornadas_especiales || 0}</strong></div>
                <div class="col"><span class="text-muted">Días Libres:</span> <strong>${rsm.dias_libres_programados || 0}</strong></div>
                <div class="col"><span class="text-muted">Feriados caídos:</span> <strong>${rsm.dias_feriado || 0}</strong></div>
            </div>
            <div class="mt-2 small text-muted">
                <strong>Feriados del periodo:</strong> ${feriados}
            </div>
        </div>
    </div>`);

    // ── Botón ejecutar ─────────────────────────────────────────────────────
    blocks.push(`
    <div class="d-flex justify-content-end mt-3">
        <button id="btn-ejecutar-cierre" class="btn btn-primary px-4" onclick="confirmarCierre()" disabled>
            <i class="bi bi-lock-fill me-1"></i> Sellar Periodo
        </button>
    </div>`);

    return blocks.join('');
}

// ─────────────────────────────────────────────────────────────────────────────
// CHECK BUTTON STATE — habilita/deshabilita el botón de cierre
// ─────────────────────────────────────────────────────────────────────────────
function checkCierreButtonState() {
    const btn = document.getElementById('btn-ejecutar-cierre');
    if (!btn || !window.currentEvaluacion) return;

    const ev  = window.currentEvaluacion;
    const chk = document.getElementById('cierre-chk-aceptar-ina');
    const inaOk = ev.inasistencias_injustificadas === 0 || (chk && chk.checked);

    const puedeEjecutar = (
        ev.he_pendientes === 0 &&
        ev.anomalias === 0 &&
        ev.en_curso === 0 &&
        inaOk
    );

    btn.disabled = !puedeEjecutar;
}

// ─────────────────────────────────────────────────────────────────────────────
// CONFIRMAR CIERRE
// ─────────────────────────────────────────────────────────────────────────────
async function confirmarCierre() {
    const fInicio   = document.getElementById('cierre-fecha-inicio').value;
    const fFin      = document.getElementById('cierre-fecha-fin').value;
    const area      = document.getElementById('cierre-area').value;
    const chk       = document.getElementById('cierre-chk-aceptar-ina');
    const aceptarIna = chk ? chk.checked : false;

    if (!confirm(`¿Está seguro de sellar el periodo ${fInicio} al ${fFin} para el área "${area}"?\n\nEsta acción no se puede deshacer.`)) return;

    const btn = document.getElementById('btn-ejecutar-cierre');
    const oldHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Sellando...';

    try {
        const res = await fetch('/api/cierre/ejecutar', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${AuthService.token}`
            },
            body: JSON.stringify({
                fecha_inicio: fInicio,
                fecha_fin: fFin,
                area: area,
                aceptar_inasistencias: aceptarIna
            })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error al sellar periodo');

        alerts.success(data.message || 'Periodo sellado correctamente.');
        document.getElementById('cierre-resultados').classList.add('d-none');
        window.currentEvaluacion = null;

        // Generar acta PDF
        mostrarActaPDF(fInicio, fFin, area);

    } catch (e) {
        alerts.error(e.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = oldHtml;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// ACTA PDF — genera e imprime el acta de cierre
// ─────────────────────────────────────────────────────────────────────────────
async function mostrarActaPDF(fInicio, fFin, area) {
    try {
        const res = await fetch(
            `/api/cierre/acta-resumen?fecha_inicio=${fInicio}&fecha_fin=${fFin}&area=${encodeURIComponent(area)}`,
            { headers: { 'Authorization': `Bearer ${AuthService.token}` } }
        );
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error al obtener acta');

        const rsm = data.resumen || {};
        const feriados = (data.feriados || []).map(f => `${f.fecha}: ${f.descripcion}`).join('<br>') || 'Ninguno';

        const heFilas = (data.he_detalle || []).map(r =>
            `<tr><td>${r.nombre_completo}</td><td>${r.fecha}</td><td>${r.horas_aprobadas}</td></tr>`
        ).join('') || '<tr><td colspan="3" class="text-center text-muted">Sin HE aprobadas</td></tr>';

        const inaFilas = (data.inasistencias_aceptadas || []).map(r =>
            `<tr><td>${r.nombre_completo}</td><td>${r.fecha}</td></tr>`
        ).join('') || '<tr><td colspan="2" class="text-center text-muted">Sin inasistencias</td></tr>';

        const printWindow = window.open('', '_blank');
        printWindow.document.write(`<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Acta de Cierre — ${area} — ${fInicio} al ${fFin}</title>
<style>
  @media print { @page { size: A4; margin: 20mm; } }
  body { font-family: Arial, sans-serif; color: #1a1a1a; font-size: 11pt; margin: 0; padding: 0; }
  .page { padding: 30px 40px; }
  .header { text-align: center; border-bottom: 3px solid #1a237e; padding-bottom: 16px; margin-bottom: 24px; }
  .header h1 { font-size: 15pt; color: #1a237e; margin: 0 0 4px 0; }
  .header p { margin: 2px 0; font-size: 10pt; color: #555; }
  .section { margin-bottom: 20px; }
  .section-title { font-size: 11pt; font-weight: bold; color: #1a237e; border-bottom: 1px solid #c5cae9; padding-bottom: 4px; margin-bottom: 10px; }
  table { width: 100%; border-collapse: collapse; font-size: 10pt; }
  th { background: #1a237e; color: #fff; padding: 5px 8px; text-align: left; }
  td { padding: 4px 8px; border-bottom: 1px solid #e8eaf6; }
  tr:nth-child(even) td { background: #f5f5f5; }
  .metrics-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
  .metric { background: #e8eaf6; border-radius: 6px; padding: 10px 12px; }
  .metric .val { font-size: 14pt; font-weight: bold; color: #1a237e; }
  .metric .lbl { font-size: 8pt; color: #555; }
  .firma-box { margin-top: 60px; text-align: center; }
  .firma-line { display: inline-block; width: 220px; border-top: 1px solid #333; padding-top: 6px; font-size: 10pt; }
  .footer { margin-top: 30px; text-align: center; font-size: 8pt; color: #888; border-top: 1px solid #ddd; padding-top: 10px; }
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <h1>ACTA DE CIERRE DE ASISTENCIA</h1>
    <p>Área: <strong>${data.area}</strong></p>
    <p>Periodo: <strong>${fInicio}</strong> al <strong>${fFin}</strong></p>
    <p>Generado por: ${data.generado_por} &nbsp;|&nbsp; Fecha: ${data.fecha_generacion}</p>
  </div>

  <div class="section">
    <div class="section-title">1. Resumen Ejecutivo</div>
    <div class="metrics-grid">
      <div class="metric"><div class="val">${rsm.total_empleados || 0}</div><div class="lbl">Empleados</div></div>
      <div class="metric"><div class="val">${rsm.dias_ok || 0}</div><div class="lbl">Días OK</div></div>
      <div class="metric"><div class="val">${rsm.dias_con_novedad || 0}</div><div class="lbl">Con Novedad</div></div>
      <div class="metric"><div class="val">${data.total_he_horas || 0} hrs</div><div class="lbl">HE Aprobadas</div></div>
      <div class="metric"><div class="val">${rsm.jornadas_especiales || 0}</div><div class="lbl">Jornadas Esp.</div></div>
      <div class="metric"><div class="val">${rsm.dias_libres_programados || 0}</div><div class="lbl">Días Libres</div></div>
      <div class="metric"><div class="val">${rsm.dias_feriado || 0}</div><div class="lbl">Feriados Caídos</div></div>
      <div class="metric"><div class="val">${rsm.inasistencias || 0}</div><div class="lbl">Inasistencias</div></div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">2. Feriados del Periodo</div>
    <p style="font-size:10pt">${feriados}</p>
  </div>

  <div class="section">
    <div class="section-title">3. Horas Extras Aprobadas — Total: ${data.total_he_horas || 0} hrs</div>
    <table>
      <thead><tr><th>Empleado</th><th>Fecha</th><th>Horas Aprobadas</th></tr></thead>
      <tbody>${heFilas}</tbody>
    </table>
  </div>

  <div class="section">
    <div class="section-title">4. Inasistencias Reconocidas por Jefatura</div>
    <table>
      <thead><tr><th>Empleado</th><th>Fecha</th></tr></thead>
      <tbody>${inaFilas}</tbody>
    </table>
  </div>

  <div class="section">
    <div class="section-title">5. Declaración de Cierre</div>
    <p>Por medio del presente documento, el suscrito certifica que ha revisado y validado el registro de asistencia del periodo indicado para el área a su cargo. Los datos contenidos en este acta constituyen el sustento para el cálculo de remuneraciones del periodo.</p>
  </div>

  <div class="firma-box">
    <div class="firma-line">
      ${data.generado_por}<br>
      <span style="font-size:9pt;color:#555">Jefe de Área</span>
    </div>
  </div>

  <div class="footer">
    Documento generado automáticamente por el Sistema de Asistencia — ${data.fecha_generacion}
  </div>
</div>
<script>window.onload = function() { window.print(); }</script>
</body>
</html>`);
        printWindow.document.close();

    } catch (e) {
        console.error('Error acta PDF:', e);
        alerts.error('No se pudo generar el acta PDF: ' + e.message);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// INIT — hook al sidebar
// ─────────────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const navItems = document.querySelectorAll('.sidebar-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            const page = e.currentTarget.getAttribute('data-page');
            if (page === 'cierre') initCierreUI();
        });
    });
});
