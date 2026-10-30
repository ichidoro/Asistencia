/**
 * Lámina «Velocidad» de la grilla de Marcaciones: la velocidad máxima del GPS de cada chofer de Bolsa Flexible, día por día, y el reporte semanal para que el chofer firme.
 * El chofer sale del plan de Despacho Diario (Nexacol) y la velocidad, del GPS del camión que tenía asignado ese día.
 * Todo lo que toca este archivo vive en window.mxVel*; marcaciones_ui.js solo lo llama (celda, leyenda, tooltip y carga).
 * Carga sin bloquear: la grilla se pinta con esqueletos en las celdas de los choferes y se rellenan en el sitio cuando llega el dato.
 */
(function () {
    'use strict';

    // Hasta 90 km/h está bien; sobre 90 va en rojo (los camiones de carretera tienen tope de 90). Cambiar acá si la regla de la empresa es otra.
    const LIMITE = 90;
    const MAX_DIAS = 62; // lo que acepta Nexacol en una consulta

    const ST = { clave: '', estado: 'idle', datos: {}, sinCalzar: [], diag: null, error: '', ticket: 0 };

    const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const esChofer = emp => typeof window.categoriaCargo === 'function' && window.categoriaCargo(emp && emp.cargo) === 'chofer';
    // Solo los de Bolsa Flexible (pedido del dueño, 30-10-2026): la lámina muestra cifras en la pestaña «Bolsa flexible»; el servidor además solo entrega a esos choferes.
    const enBolsa = () => !!(window._gridFlags && window._gridFlags.esBolsa);
    const nivel = v => (v > LIMITE ? 'x' : 'ok');
    const FLECHA = '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 10V2M2.8 5.2 6 2l3.2 3.2"/></svg>';
    const dmy = f => String(f).split('-').reverse().join('-');
    const ddmm = f => { const p = String(f).split('-'); return p.length === 3 ? `${p[2]}-${p[1]}` : f; };
    const authHead = () => ({ 'Authorization': `Bearer ${localStorage.getItem('access_token')}` });

    // ── Fechas (aritmética en UTC al mediodía: inmune al cambio de hora) ──
    const DIAS_ES = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
    const MESES_ES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
    const sumar = (f, n) => { const d = new Date(f + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
    const lunesDe = f => sumar(f, -((new Date(f + 'T12:00:00Z').getUTCDay() + 6) % 7));
    const diaDe = f => DIAS_ES[new Date(f + 'T12:00:00Z').getUTCDay()];
    const hoyIso = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
    const larga = f => { const [, m, d] = f.split('-').map(Number); return `${d} de ${MESES_ES[m - 1]}`; };

    function periodo() {
        const p = window.stateMarcacionesApp && window.stateMarcacionesApp.data && window.stateMarcacionesApp.data.periodo;
        if (!p || !p.inicio || !p.fin) return null;
        let ini = p.inicio;
        const dias = typeof window.getDatesInRange === 'function' ? window.getDatesInRange(p.inicio, p.fin) : [];
        if (dias.length > MAX_DIAS) ini = dias[dias.length - MAX_DIAS];
        return { ini, fin: p.fin };
    }

    async function pedir(desde, hasta) {
        const r = await fetch(`/api/asistencia/gps/velocidades-choferes/?desde=${desde}&hasta=${hasta}`, { headers: authHead() });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `error ${r.status}`);
        return j;
    }

    // ── Celda ──
    function chip(info) {
        const n = nivel(info.vel);
        const aria = `Velocidad máxima ${info.vel} kilómetros por hora, ${n === 'x' ? `sobre el límite de ${LIMITE}` : 'dentro del límite'}`;
        return `<span class="vel-p vel-${n}" role="img" aria-label="${aria}">${n === 'x' ? FLECHA : ''}${esc(info.vel)}</span>`;
    }

    function interior(empId, fecha, trabajo) {
        if (ST.estado === 'idle' || ST.estado === 'cargando') return trabajo ? '<span class="vel-sk" aria-hidden="true"></span>' : '';
        if (ST.estado === 'error') return ''; // el aviso de la leyenda lo explica; los «—» dirían que no hubo dato
        const info = ST.datos[String(empId)] && ST.datos[String(empId)][fecha];
        if (info) return chip(info);
        return trabajo ? '<span class="vel-v" title="Sin velocidad del GPS ese día" aria-label="Sin dato de GPS">—</span>' : '';
    }

    /** Contenido de la celda de un día. Solo los choferes de Bolsa Flexible llevan algo; el resto de la grilla queda en blanco. */
    window.mxVelCelda = function (emp, fecha, trabajo) {
        if (!esChofer(emp) || !enBolsa()) return '';
        return `<span class="vel-slot" data-t="${trabajo ? 1 : 0}">${interior(emp.id, fecha, trabajo)}</span>`;
    };

    function nombreDe(empId) {
        const el = document.querySelector(`#row-empleado-${empId} .emp-name-link`);
        return el ? el.textContent.trim() : '';
    }

    const BTN_REPORTE = '<button type="button" class="vel-btn" onclick="mxVelReporte()"><i class="bi bi-file-earmark-pdf"></i>Reporte semanal</button>';

    /** Barra de leyenda de la lámina (va donde van los estados). */
    window.mxVelLeyenda = function () {
        if (!enBolsa()) {
            return `<div class="vel-leyenda" id="vel-leyenda">
                <span class="vel-aviso" role="status"><i class="bi bi-info-circle-fill"></i>La velocidad se muestra solo a los choferes de Bolsa Flexible.</span>
                <button type="button" class="vel-enlace" onclick="vaSetTab('bolsa')">Ver Bolsa flexible</button>
                ${BTN_REPORTE}
            </div>`;
        }
        let estado = '';
        if (ST.estado === 'cargando' || ST.estado === 'idle') {
            estado = '<span class="vel-resumen" role="status"><span class="vel-sk" aria-hidden="true"></span>Leyendo el GPS…</span>';
        } else if (ST.estado === 'error') {
            estado = `<span class="vel-aviso vel-err" role="alert"><i class="bi bi-exclamation-triangle-fill"></i>No se pudo leer el GPS: ${esc(ST.error)} <button type="button" onclick="mxVelReintentar()">Reintentar</button></span>`;
        } else {
            let max = null, sobre = 0;
            Object.keys(ST.datos).forEach(id => Object.keys(ST.datos[id]).forEach(f => {
                const i = ST.datos[id][f];
                if (i.vel > LIMITE) sobre++;
                if (!max || i.vel > max.vel) max = { vel: i.vel, id, f };
            }));
            if (max) estado += `<span class="vel-resumen ${max.vel > LIMITE ? 'vel-rojo' : ''}" title="La velocidad más alta registrada en el período">Máxima del período <b>${esc(max.vel)} km/h</b>${nombreDe(max.id) ? ' · ' + esc(nombreDe(max.id)) : ''} · ${esc(ddmm(max.f))}</span>`;
            else {
                const d = ST.diag;
                estado += '<span class="vel-resumen">Ningún chofer con velocidad en este período</span>';
                if (d) estado += `<span class="vel-aviso" tabindex="0" title="Dónde se corta: Nexacol planificó ${d.dias_plan} días con chofer; de esos, ${d.dias_con_gps} tienen velocidad del GPS; hay ${d.choferes} choferes de Logística Tradicional en Asistencia y ${d.con_velocidad} quedaron con velocidad."><i class="bi bi-info-circle-fill"></i>Plan: ${d.dias_plan} días · con GPS: ${d.dias_con_gps} · choferes: ${d.choferes} · con velocidad: ${d.con_velocidad}</span>`;
            }
            if (sobre) estado += `<span class="vel-resumen vel-rojo"><b>${sobre}</b> ${sobre === 1 ? 'día' : 'días'} sobre ${LIMITE}</span>`;
            if (ST.sinCalzar.length) {
                const lista = ST.sinCalzar.map(x => `${x.nombre} (${x.dias.length} ${x.dias.length === 1 ? 'día' : 'días'})`).join(', ');
                estado += `<span class="vel-aviso" tabindex="0" title="Nombres del plan de Despacho que no se pudieron asociar a una sola persona de Asistencia: ${esc(lista)}"><i class="bi bi-person-exclamation"></i>${ST.sinCalzar.length} ${ST.sinCalzar.length === 1 ? 'nombre' : 'nombres'} del plan sin asociar</span>`;
            }
        }
        return `<div class="vel-leyenda" id="vel-leyenda">
            <span class="fw-bold" style="color:#1a2326">Velocidad máxima del GPS · km/h</span>
            <span class="vel-ley"><span class="vel-p vel-ok">${LIMITE}</span>Bien · hasta ${LIMITE}</span>
            <span class="vel-ley"><span class="vel-p vel-x">${FLECHA}${LIMITE + 1}</span>Sobre ${LIMITE}</span>
            <span class="vel-ley"><span class="vel-v" style="font-size:.9rem">—</span>Sin dato</span>
            ${estado}
            ${BTN_REPORTE}
        </div>`;
    };

    /** Rellena en el sitio las celdas de los choferes (sin repintar la grilla) y actualiza la leyenda. */
    function pintar(container) {
        if (!container) return;
        const ley = container.querySelector('#vel-leyenda');
        if (ley) ley.outerHTML = window.mxVelLeyenda();
        container.querySelectorAll('td.col-day[data-tip] .vel-slot').forEach(slot => {
            const td = slot.closest('td');
            const [id, fecha] = String(td.getAttribute('data-tip')).split('|');
            slot.innerHTML = interior(id, fecha, slot.getAttribute('data-t') === '1');
            td._tipHtml = null; // el tooltip se rearma con la velocidad al pasar el mouse
            slot.style.setProperty('--i', Math.min(td.cellIndex, 30));
            slot.classList.add('vel-in');
        });
    }

    /** Pide las velocidades del período mostrado (una vez por período) y rellena las celdas cuando llegan. Solo en la pestaña Bolsa flexible. */
    window.mxVelAsegurar = function (container) {
        const s = window.stateMarcacionesApp;
        if (!s || s.viewMode !== 'velocidad' || !container || !enBolsa()) return;
        const p = periodo();
        if (!p) return;
        const clave = `${p.ini}|${p.fin}`;
        if (ST.clave === clave && ST.estado !== 'idle') return; // ya cargada o en camino
        ST.clave = clave; ST.estado = 'cargando'; ST.error = '';
        const ticket = ++ST.ticket;
        pedir(p.ini, p.fin)
            .then(j => { if (ticket === ST.ticket) { ST.datos = j.velocidades || {}; ST.sinCalzar = j.sin_calzar || []; ST.diag = j.diagnostico || null; ST.estado = 'ok'; } })
            .catch(e => { if (ticket === ST.ticket) { ST.datos = {}; ST.sinCalzar = []; ST.estado = 'error'; ST.error = e.message || 'sin conexión'; } })
            .finally(() => { if (ticket === ST.ticket) pintar(document.getElementById('marcaciones-view-container')); });
    };

    window.mxVelReintentar = function () {
        ST.estado = 'idle'; ST.clave = '';
        const c = document.getElementById('marcaciones-view-container');
        if (c && window.stateMarcacionesApp && window.stateMarcacionesApp.data && typeof window.renderVistaAnalitica === 'function') window.renderVistaAnalitica(window.stateMarcacionesApp.data, c);
        else window.mxVelAsegurar(c);
    };

    /** Pie del tooltip de la celda con la cifra grande y el camión (solo en la lámina Velocidad). */
    window.mxVelTip = function (td, html) {
        const s = window.stateMarcacionesApp;
        if (!s || s.viewMode !== 'velocidad' || !td.querySelector('.vel-slot') || ST.estado !== 'ok') return html;
        const [id, fecha] = String(td.getAttribute('data-tip')).split('|');
        const info = ST.datos[id] && ST.datos[id][fecha];
        if (!info || !/<\/div>\s*$/.test(html)) return html;
        const pie = `<div class="tp-vel vel-${nivel(info.vel)}"><div class="tp-vel-n">${esc(info.vel)}<small>km/h</small></div>`
            + `<div class="tp-vel-t">Velocidad máxima del GPS${info.hora ? ' · ' + esc(info.hora) : ''}</div>`
            + `<div class="tp-vel-s">Camión ${esc(info.patente)}${info.comparte ? ' · lo compartió con otro chofer ese día' : ''}</div></div>`;
        return html.replace(/<\/div>\s*$/, pie + '</div>');
    };

    // ═══════════════ Reporte semanal (PDF con la firma del chofer) ═══════════════

    /** Resume lo de un chofer en la semana: filas por día, máxima, días sobre el límite y patentes. */
    function resumenChofer(velocidades, lunes) {
        const domingo = sumar(lunes, 6);
        const filas = Object.keys(velocidades).filter(f => f >= lunes && f <= domingo).sort().map(f => ({ fecha: f, ...velocidades[f] }));
        const max = filas.reduce((a, r) => (!a || r.vel > a.vel ? r : a), null);
        return { filas, max, sobre: filas.filter(r => r.vel > LIMITE).length, patentes: [...new Set(filas.map(r => r.patente))] };
    }

    const slug = t => String(t).normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '');

    function paginaChofer(doc, nombre, rut, res, lunes) {
        const W = doc.internal.pageSize.getWidth();
        const M = 40, domingo = sumar(lunes, 6);
        const AZUL = [30, 58, 138], TINTA = [26, 35, 38], GRIS = [105, 115, 143], ROJO = [217, 45, 32], VERDE = [18, 112, 63];
        const veh = res.patentes.join(', ');

        // Cabecera
        doc.setFillColor(...AZUL); doc.rect(0, 0, W, 92, 'F');
        doc.setTextColor(186, 200, 235); doc.setFont('helvetica', 'bold'); doc.setFontSize(9); doc.text('AGUACOL SPA', M, 34);
        doc.setTextColor(255, 255, 255); doc.setFontSize(21); doc.text('Reporte semanal de velocidades', M, 62);
        doc.setFontSize(8); doc.setTextColor(186, 200, 235); doc.setFont('helvetica', 'normal');
        doc.text('SEMANA', W - M, 34, { align: 'right' });
        doc.setTextColor(255, 255, 255); doc.setFont('helvetica', 'bold'); doc.setFontSize(11.5);
        doc.text(`${dmy(lunes)}  al  ${dmy(domingo)}`, W - M, 50, { align: 'right' });
        doc.setFont('helvetica', 'normal'); doc.setFontSize(8); doc.setTextColor(186, 200, 235);
        doc.text(`Emitido el ${dmy(hoyIso())}`, W - M, 68, { align: 'right' });

        // Ficha del chofer
        doc.setFillColor(244, 246, 251); doc.roundedRect(M, 112, W - 2 * M, 98, 8, 8, 'F');
        doc.setFont('helvetica', 'bold'); doc.setFontSize(7.5); doc.setTextColor(...GRIS);
        doc.text('CHOFER', M + 18, 132);
        doc.setFontSize(16); doc.setTextColor(...TINTA); doc.text(nombre, M + 18, 152);
        doc.setFontSize(7.5); doc.setTextColor(...GRIS);
        doc.text('RUT', M + 18, 174); doc.text(res.patentes.length === 1 ? 'PATENTE' : 'PATENTES', M + 170, 174); doc.text('DÍAS CON REGISTRO', M + 350, 174);
        doc.setFontSize(10.5); doc.setTextColor(...TINTA);
        doc.text(rut || 'No registrado', M + 18, 190); doc.text(veh, M + 170, 190); doc.text(String(res.filas.length), M + 350, 190);

        // Resumen: la máxima de la semana y los días sobre el límite
        const rojo = res.max.vel > LIMITE;
        doc.setFillColor(...(rojo ? ROJO : [227, 244, 234])); doc.roundedRect(M, 228, 86, 30, 8, 8, 'F');
        doc.setFont('helvetica', 'bold'); doc.setFontSize(13); doc.setTextColor(...(rojo ? [255, 255, 255] : VERDE));
        doc.text(`${res.max.vel} km/h`, M + 43, 248, { align: 'center' });
        doc.setFontSize(10); doc.setTextColor(...TINTA); doc.text('Velocidad máxima de la semana', M + 98, 240);
        doc.setFont('helvetica', 'normal'); doc.setFontSize(8.5); doc.setTextColor(...GRIS);
        doc.text(`${diaDe(res.max.fecha)} ${dmy(res.max.fecha)}${res.max.hora ? ' · ' + res.max.hora : ''} · patente ${res.max.patente}`, M + 98, 253);
        doc.setFont('helvetica', 'bold'); doc.setFontSize(10); doc.setTextColor(...(res.sobre ? ROJO : VERDE));
        doc.text(`${res.sobre} de ${res.filas.length} ${res.filas.length === 1 ? 'día' : 'días'} sobre ${LIMITE} km/h`, W - M, 240, { align: 'right' });
        doc.setFont('helvetica', 'normal'); doc.setFontSize(8.5); doc.setTextColor(...GRIS);
        doc.text(`Límite de referencia: ${LIMITE} km/h`, W - M, 253, { align: 'right' });

        // Detalle por día
        doc.autoTable({
            startY: 276, theme: 'grid', margin: { left: M, right: M },
            head: [['Fecha', 'Día', 'Patente', 'Velocidad máx.', 'Hora', 'Evaluación']],
            body: res.filas.map(r => [dmy(r.fecha), diaDe(r.fecha).replace(/^./, c => c.toUpperCase()), r.patente, `${r.vel} km/h`, r.hora || '—', r.vel > LIMITE ? `Sobre ${LIMITE} km/h` : 'Dentro del límite']),
            styles: { font: 'helvetica', fontSize: 9.5, cellPadding: { top: 6, bottom: 6, left: 8, right: 8 }, lineColor: [228, 232, 241], lineWidth: 0.6, textColor: TINTA, valign: 'middle' },
            headStyles: { fillColor: AZUL, textColor: 255, fontStyle: 'bold', fontSize: 8.5 },
            alternateRowStyles: { fillColor: [249, 250, 253] },
            columnStyles: { 3: { halign: 'right', fontStyle: 'bold' }, 4: { halign: 'center' } },
            didParseCell: d => {
                if (d.section !== 'body') return;
                const r = res.filas[d.row.index];
                if (d.column.index === 3 || d.column.index === 5) {
                    d.cell.styles.textColor = r.vel > LIMITE ? [168, 47, 38] : VERDE;
                    d.cell.styles.fillColor = r.vel > LIMITE ? [253, 236, 234] : [235, 247, 240];
                    if (d.column.index === 5) d.cell.styles.fontStyle = 'bold';
                }
            },
        });
        const yTabla = doc.lastAutoTable.finalY;
        doc.setFont('helvetica', 'normal'); doc.setFontSize(8); doc.setTextColor(...GRIS);
        doc.text('Velocidad máxima registrada por el GPS del vehículo asignado al chofer en la programación de Despacho Diario.', M, yTabla + 16);

        // Declaración y firma
        let yDecl = Math.max(yTabla + 46, 500);
        if (yDecl + 96 + 132 > doc.internal.pageSize.getHeight() - 50) { doc.addPage(); yDecl = 60; }
        doc.setFont('helvetica', 'bold'); doc.setFontSize(8); doc.setTextColor(...GRIS);
        doc.text('DECLARACIÓN DE CONOCIMIENTO', M, yDecl);
        doc.setFont('helvetica', 'normal'); doc.setFontSize(10.5); doc.setTextColor(...TINTA);
        const texto = `Yo, ${nombre}${rut ? ', RUT ' + rut : ''}, declaro haber tomado conocimiento de las velocidades máximas registradas por el GPS ${res.patentes.length === 1 ? 'del vehículo' : 'de los vehículos'} patente ${veh}, asignado${res.patentes.length === 1 ? '' : 's'} a mi nombre en la programación de Despacho Diario durante la semana del ${larga(lunes)} al ${larga(domingo)}, tal como se detallan en este documento.`;
        doc.text(doc.splitTextToSize(texto, W - 2 * M), M, yDecl + 18, { lineHeightFactor: 1.5 });

        const yCaja = Math.max(yDecl + 96, 626);
        doc.setDrawColor(213, 220, 235); doc.setLineWidth(0.8); doc.roundedRect(M, yCaja, W - 2 * M, 132, 10, 10, 'S');
        doc.setDrawColor(...TINTA); doc.setLineWidth(0.7);
        doc.line(M + 24, yCaja + 88, M + 250, yCaja + 88); doc.line(W - M - 190, yCaja + 88, W - M - 24, yCaja + 88);
        doc.setFont('helvetica', 'bold'); doc.setFontSize(9.5); doc.setTextColor(...TINTA);
        doc.text('Firma del chofer', M + 24, yCaja + 102); doc.text('Fecha de firma', W - M - 190, yCaja + 102);
        doc.setFont('helvetica', 'normal'); doc.setFontSize(8.5); doc.setTextColor(...GRIS);
        doc.text(`${nombre}${rut ? '  ·  RUT ' + rut : ''}`, M + 24, yCaja + 116);
        doc.text('día  /  mes  /  año', W - M - 190, yCaja + 116);
    }

    function pieDePagina(doc) {
        const W = doc.internal.pageSize.getWidth(), H = doc.internal.pageSize.getHeight(), n = doc.internal.getNumberOfPages();
        for (let i = 1; i <= n; i++) {
            doc.setPage(i);
            doc.setDrawColor(228, 232, 241); doc.setLineWidth(0.6); doc.line(40, H - 34, W - 40, H - 34);
            doc.setFont('helvetica', 'normal'); doc.setFontSize(7.5); doc.setTextColor(105, 115, 143);
            doc.text('Documento generado por el sistema de asistencia de Aguacol', 40, H - 20);
            doc.text(`Página ${i} de ${n}`, W - 40, H - 20, { align: 'right' });
        }
    }

    async function generarPdf(lunes, datos, ids) {
        await window.ensureLib('jspdf');
        const { jsPDF } = window.jspdf;
        const doc = new jsPDF('p', 'pt', 'a4');
        ids.forEach((id, i) => {
            if (i) doc.addPage();
            const p = (datos.personas || {})[id] || {};
            paginaChofer(doc, p.nombre || `Chofer ${id}`, p.rut || '', resumenChofer(datos.velocidades[id], lunes), lunes);
        });
        pieDePagina(doc);
        const un = ids.length === 1 ? ((datos.personas || {})[ids[0]] || {}).nombre : '';
        doc.save(`Velocidades_${un ? slug(un) : 'choferes'}_${lunes}.pdf`);
    }

    /** Diálogo: elige la semana (lunes a domingo) y los choferes, y descarga el PDF con una hoja por chofer lista para firmar. */
    window.mxVelReporte = function () {
        if (typeof Swal === 'undefined') return;
        let lunes = lunesDe(sumar(hoyIso(), -7)); // por defecto, la última semana completa
        let datos = null, ticket = 0;
        const sel = new Set();

        const html = `<div class="vrep">
            <div class="vr-sem">
                <button type="button" id="vr-ant" aria-label="Semana anterior"><i class="bi bi-chevron-left"></i></button>
                <div class="vr-sem-t" aria-live="polite"><b id="vr-rango"></b><span id="vr-sub"></span></div>
                <button type="button" id="vr-sig" aria-label="Semana siguiente"><i class="bi bi-chevron-right"></i></button>
            </div>
            <div id="vr-cont"></div>
        </div>`;

        Swal.fire({
            title: 'Reporte semanal de velocidades', html, width: 580, showCancelButton: true, focusConfirm: false,
            confirmButtonText: 'Descargar PDF', cancelButtonText: 'Cerrar', confirmButtonColor: '#1e3a8a',
            didOpen: () => {
                const root = Swal.getHtmlContainer();
                const $ = s => root.querySelector(s);
                const confirmar = Swal.getConfirmButton();

                const botonConteo = () => { confirmar.disabled = !datos || sel.size === 0; confirmar.textContent = sel.size ? `Descargar PDF (${sel.size})` : 'Descargar PDF'; };

                const lista = () => {
                    const ids = Object.keys(datos.velocidades || {}).filter(id => resumenChofer(datos.velocidades[id], lunes).max);
                    if (!ids.length) { $('#vr-cont').innerHTML = '<div class="vr-vacio">Ningún chofer de Bolsa Flexible tiene velocidad registrada esa semana.</div>'; botonConteo(); return; }
                    const filas = ids.map(id => ({ id, p: (datos.personas || {})[id] || {}, r: resumenChofer(datos.velocidades[id], lunes) })).filter(f => f.r.max).sort((a, b) => b.r.max.vel - a.r.max.vel);
                    $('#vr-cont').innerHTML = `<div class="vr-top"><label><input type="checkbox" id="vr-todos" ${sel.size === ids.length ? 'checked' : ''}> Todos los choferes</label><span>${ids.length} ${ids.length === 1 ? 'chofer' : 'choferes'}</span></div>
                        <div class="vr-lista">${filas.map(f => `<label class="vr-fila"><input type="checkbox" data-id="${esc(f.id)}" ${sel.has(f.id) ? 'checked' : ''}>
                            <span class="vr-n">${esc(f.p.nombre || 'Chofer ' + f.id)}</span>
                            <span class="vel-p vel-${nivel(f.r.max.vel)}">${nivel(f.r.max.vel) === 'x' ? FLECHA : ''}${esc(f.r.max.vel)}</span>
                            <span class="vr-s">${esc(f.p.rut || 'Sin RUT')} · ${esc(f.r.patentes.join(', '))} · ${f.r.filas.length} ${f.r.filas.length === 1 ? 'día' : 'días'}${f.r.sobre ? ` · ${f.r.sobre} sobre ${LIMITE}` : ''}</span></label>`).join('')}</div>`;
                    $('#vr-todos').addEventListener('change', e => { sel.clear(); if (e.target.checked) ids.forEach(i => sel.add(i)); lista(); });
                    root.querySelectorAll('.vr-fila input').forEach(c => c.addEventListener('change', () => { c.checked ? sel.add(c.dataset.id) : sel.delete(c.dataset.id); $('#vr-todos').checked = sel.size === ids.length; botonConteo(); }));
                    botonConteo();
                };

                const cargar = () => {
                    const dom = sumar(lunes, 6);
                    $('#vr-rango').textContent = `${dmy(lunes)}  al  ${dmy(dom)}`;
                    $('#vr-sub').textContent = `Lunes ${larga(lunes)} a domingo ${larga(dom)}`;
                    $('#vr-sig').disabled = sumar(lunes, 7) > hoyIso();
                    datos = null; sel.clear(); botonConteo();
                    $('#vr-cont').innerHTML = '<div class="vr-carga" aria-hidden="true"><span class="vel-sk"></span><span class="vel-sk"></span><span class="vel-sk"></span></div>';
                    const t = ++ticket;
                    pedir(lunes, dom).then(j => { if (t !== ticket) return; datos = j; Object.keys(j.velocidades || {}).forEach(i => { if (resumenChofer(j.velocidades[i], lunes).max) sel.add(i); }); lista(); })
                        .catch(e => { if (t === ticket) $('#vr-cont').innerHTML = `<div class="vr-vacio" role="alert" style="color:#a82f26">No se pudo leer el GPS: ${esc(e.message)}</div>`; });
                };

                $('#vr-ant').addEventListener('click', () => { lunes = sumar(lunes, -7); cargar(); });
                $('#vr-sig').addEventListener('click', () => { lunes = sumar(lunes, 7); cargar(); });
                cargar();
            },
            preConfirm: async () => {
                if (!datos || !sel.size) { Swal.showValidationMessage('Elige al menos un chofer.'); return false; }
                try { await generarPdf(lunes, datos, Object.keys(datos.velocidades).filter(i => sel.has(i))); return true; }
                catch (e) { Swal.showValidationMessage(`No se pudo generar el PDF: ${e.message}`); return false; }
            },
        });
    };

    // Si el archivo llegó después de pintada la grilla (carga diferida) y la lámina ya está activa, las celdas no tienen su espacio: se pinta una vez más.
    const c0 = document.getElementById('marcaciones-view-container');
    const s0 = window.stateMarcacionesApp;
    if (c0 && s0 && s0.viewMode === 'velocidad' && s0.data && c0.querySelector('.matrix-table-premium') && typeof window.renderVistaAnalitica === 'function') window.renderVistaAnalitica(s0.data, c0);
})();
