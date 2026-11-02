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
                if (d && d.dias_plan === 0) estado += `<span class="vel-aviso" role="status"><i class="bi bi-info-circle-fill"></i>Despacho Diario no tiene choferes asignados a un camión en estas fechas. Prueba con el período actual.</span>`;
                else if (d) estado += `<span class="vel-aviso" tabindex="0" title="Dónde se corta: Nexacol planificó ${d.dias_plan} días con chofer; de esos, ${d.dias_con_gps} tienen velocidad del GPS; hay ${d.choferes} choferes de Logística Tradicional en Asistencia y ${d.con_velocidad} quedaron con velocidad."><i class="bi bi-info-circle-fill"></i>Plan: ${d.dias_plan} días · con GPS: ${d.dias_con_gps} · choferes: ${d.choferes} · con velocidad: ${d.con_velocidad}</span>`;
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

    // ── Logo y ruta del reporte ──
    let _logo = null;
    /** Logo de Aguacol como imagen para el PDF (una sola vez); si no carga, el reporte sale con el texto «AGUACOL SPA». */
    async function cargarLogo() {
        if (_logo !== null) return _logo || null;
        try {
            const blob = await (await fetch('/static/assets/img/logo-aguacol.png')).blob();
            const url = await new Promise((ok, mal) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = mal; r.readAsDataURL(blob); });
            const img = await new Promise((ok, mal) => { const i = new Image(); i.onload = () => ok(i); i.onerror = mal; i.src = url; });
            _logo = { url, w: img.naturalWidth, h: img.naturalHeight };
        } catch (_) { _logo = false; }
        return _logo || null;
    }

    /** Ruta del camión el día de la velocidad máxima (puntos reducidos); null si el GPS no la entrega: el reporte sale igual, sin mapa. */
    async function pedirRuta(patente, fecha) {
        try {
            const r = await fetch('/api/asistencia/gps/ruta-velocidad/?patente=' + encodeURIComponent(patente) + '&fecha=' + fecha, { headers: authHead() });
            const j = await r.json().catch(() => ({}));
            return r.ok && j.puntos && j.puntos.length > 1 ? j : null;
        } catch (_) { return null; }
    }

    /** Dibuja la ruta como trazo vectorial (sin mapa de fondo): rojo donde iba sobre el límite, con el punto de la velocidad máxima marcado. */
    function dibujarRuta(doc, x, y, w, h, ruta, res) {
        const AZUL = [30, 58, 138], ROJO = [217, 45, 32], VERDE = [18, 112, 63], GRIS = [105, 115, 143], TINTA = [26, 35, 38];
        const pts = ruta.puntos;
        doc.setFillColor(244, 246, 251); doc.setDrawColor(213, 220, 235); doc.setLineWidth(0.8); doc.roundedRect(x, y, w, h, 8, 8, 'FD');
        doc.setFont('helvetica', 'bold'); doc.setFontSize(7.5); doc.setTextColor(...GRIS);
        doc.text('RUTA DEL ' + dmy(ruta.fecha) + '  ·  CAMIÓN ' + ruta.patente + (ruta.km ? '  ·  ' + Math.round(ruta.km) + ' KM' : ''), x + 14, y + 16);
        doc.setFont('helvetica', 'normal'); doc.setFontSize(7.5);
        doc.setDrawColor(...AZUL); doc.setLineWidth(1.6); doc.line(w + x - 168, y + 13, w + x - 154, y + 13);
        doc.setTextColor(...GRIS); doc.text('Dentro del límite', w + x - 150, y + 16);
        doc.setDrawColor(...ROJO); doc.line(w + x - 80, y + 13, w + x - 66, y + 13);
        doc.text('Sobre ' + LIMITE + ' km/h', w + x - 62, y + 16);

        const px = x + 16, py = y + 28, pw = w - 32, ph = h - 40;
        const las = pts.map(p => p.la), los = pts.map(p => p.lo);
        const minLa = Math.min(...las), maxLa = Math.max(...las), minLo = Math.min(...los), maxLo = Math.max(...los);
        const k = Math.cos(((minLa + maxLa) / 2) * Math.PI / 180); // un grado de longitud mide menos que uno de latitud
        const dx = Math.max((maxLo - minLo) * k, 1e-6), dy = Math.max(maxLa - minLa, 1e-6);
        const sc = Math.min(pw / dx, ph / dy);
        const X = lo => px + (pw - dx * sc) / 2 + (lo - minLo) * k * sc;
        const Y = la => py + (ph - dy * sc) / 2 + (maxLa - la) * sc;

        doc.setLineWidth(1.6);
        for (let i = 1; i < pts.length; i++) {
            const a = pts[i - 1], b = pts[i];
            doc.setDrawColor(...(Math.max(a.v, b.v) > LIMITE ? ROJO : AZUL));
            doc.line(X(a.lo), Y(a.la), X(b.lo), Y(b.la));
        }
        const marca = (p, col, r) => { doc.setFillColor(...col); doc.setDrawColor(255, 255, 255); doc.setLineWidth(1.4); doc.circle(X(p.lo), Y(p.la), r, 'FD'); };
        marca(pts[0], VERDE, 4); marca(pts[pts.length - 1], TINTA, 4);
        const m = ruta.punto_max || pts.reduce((a, p) => (p.v > a.v ? p : a), pts[0]);
        marca(m, ROJO, 6);
        const txt = 'MÁX. ' + res.max.vel + ' km/h' + (res.max.hora ? ' · ' + res.max.hora : '');
        doc.setFont('helvetica', 'bold'); doc.setFontSize(8.5);
        const tw = doc.getTextWidth(txt) + 14, mx = X(m.lo), my = Y(m.la);
        const lx = mx > x + w / 2 ? mx - tw - 10 : mx + 10, ly = Math.min(Math.max(my - 9, y + 22), y + h - 22);
        doc.setFillColor(...ROJO); doc.roundedRect(lx, ly, tw, 17, 4, 4, 'F');
        doc.setTextColor(255, 255, 255); doc.text(txt, lx + 7, ly + 11.5);
        doc.setFont('helvetica', 'normal'); doc.setFontSize(7); doc.setTextColor(...GRIS);
        doc.text('Inicio', X(pts[0].lo) + 7, Y(pts[0].la) + 3); doc.text('Fin', X(pts[pts.length - 1].lo) + 7, Y(pts[pts.length - 1].la) + 3);
    }

    function paginaChofer(doc, nombre, rut, res, lunes, ruta, logo) {
        const W = doc.internal.pageSize.getWidth();
        const M = 40, domingo = sumar(lunes, 6);
        const AZUL = [30, 58, 138], TINTA = [26, 35, 38], GRIS = [105, 115, 143], ROJO = [217, 45, 32], VERDE = [18, 112, 63];
        const veh = res.patentes.join(', ');

        // Cabecera
        doc.setFillColor(...AZUL); doc.rect(0, 0, W, 92, 'F');
        if (logo) doc.addImage(logo.url, 'PNG', M, 14, 108, 108 * logo.h / logo.w);
        else { doc.setTextColor(186, 200, 235); doc.setFont('helvetica', 'bold'); doc.setFontSize(9); doc.text('AGUACOL SPA', M, 34); }
        doc.setTextColor(255, 255, 255); doc.setFont('helvetica', 'bold'); doc.setFontSize(logo ? 19 : 21); doc.text('Reporte semanal de velocidades', M, logo ? 74 : 62);
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

        // Ruta del día de la velocidad máxima (si el GPS la entregó) y detalle por día, más compacto para que la firma quede en la misma hoja
        const compacto = !!ruta;
        if (compacto) dibujarRuta(doc, M, 270, W - 2 * M, 118, ruta, res);
        doc.autoTable({
            startY: compacto ? 400 : 276, theme: 'grid', margin: { left: M, right: M },
            head: [['Fecha', 'Día', 'Patente', 'Velocidad máx.', 'Hora', 'Evaluación']],
            body: res.filas.map(r => [dmy(r.fecha), diaDe(r.fecha).replace(/^./, c => c.toUpperCase()), r.patente, `${r.vel} km/h`, r.hora || '—', r.vel > LIMITE ? `Sobre ${LIMITE} km/h` : 'Dentro del límite']),
            styles: { font: 'helvetica', fontSize: compacto ? 9 : 9.5, cellPadding: compacto ? { top: 3.5, bottom: 3.5, left: 8, right: 8 } : { top: 6, bottom: 6, left: 8, right: 8 }, lineColor: [228, 232, 241], lineWidth: 0.6, textColor: TINTA, valign: 'middle' },
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
        let yDecl = compacto ? yTabla + 36 : Math.max(yTabla + 46, 500);
        const altoCaja = compacto ? 118 : 132;
        if (yDecl + 96 + altoCaja > doc.internal.pageSize.getHeight() - 50) { doc.addPage(); yDecl = 60; }
        doc.setFont('helvetica', 'bold'); doc.setFontSize(8); doc.setTextColor(...GRIS);
        doc.text('DECLARACIÓN DE CONOCIMIENTO', M, yDecl);
        doc.setFont('helvetica', 'normal'); doc.setFontSize(10.5); doc.setTextColor(...TINTA);
        const texto = `Yo, ${nombre}${rut ? ', RUT ' + rut : ''}, declaro haber tomado conocimiento de las velocidades máximas registradas por el GPS ${res.patentes.length === 1 ? 'del vehículo' : 'de los vehículos'} patente ${veh}, asignado${res.patentes.length === 1 ? '' : 's'} a mi nombre en la programación de Despacho Diario durante la semana del ${larga(lunes)} al ${larga(domingo)}, tal como se detallan en este documento.`;
        doc.text(doc.splitTextToSize(texto, W - 2 * M), M, yDecl + 18, { lineHeightFactor: 1.5 });

        const yCaja = compacto ? yDecl + 80 : Math.max(yDecl + 96, 626);
        doc.setDrawColor(213, 220, 235); doc.setLineWidth(0.8); doc.roundedRect(M, yCaja, W - 2 * M, altoCaja, 10, 10, 'S');
        doc.setDrawColor(...TINTA); doc.setLineWidth(0.7);
        const yLin = yCaja + altoCaja - 44;
        doc.line(M + 24, yLin, M + 250, yLin); doc.line(W - M - 190, yLin, W - M - 24, yLin);
        doc.setFont('helvetica', 'bold'); doc.setFontSize(9.5); doc.setTextColor(...TINTA);
        doc.text('Firma del chofer', M + 24, yLin + 14); doc.text('Fecha de firma', W - M - 190, yLin + 14);
        doc.setFont('helvetica', 'normal'); doc.setFontSize(8.5); doc.setTextColor(...GRIS);
        doc.text(`${nombre}${rut ? '  ·  RUT ' + rut : ''}`, M + 24, yLin + 28);
        doc.text('día  /  mes  /  año', W - M - 190, yLin + 28);
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
        const logo = await cargarLogo();
        const res = ids.map(id => resumenChofer(datos.velocidades[id], lunes));
        // La ruta de cada chofer (la del día de su velocidad máxima) se pide en paralelo; si alguna falla, esa hoja sale sin mapa.
        const rutas = await Promise.all(res.map(r => pedirRuta(r.max.patente, r.max.fecha)));
        ids.forEach((id, i) => {
            if (i) doc.addPage();
            const p = (datos.personas || {})[id] || {};
            paginaChofer(doc, p.nombre || `Chofer ${id}`, p.rut || '', res[i], lunes, rutas[i], logo);
        });
        pieDePagina(doc);
        const un = ids.length === 1 ? ((datos.personas || {})[ids[0]] || {}).nombre : '';
        return { blob: doc.output('blob'), nombre: `Velocidades_${un ? slug(un) : 'choferes'}_${lunes}.pdf` };
    }

    /** Diálogo: elige la semana (lunes a domingo) y uno o todos los choferes, y abre el PDF (una hoja por chofer, lista para firmar) en una pestaña nueva, con el visor del navegador para descargarlo o imprimirlo. */
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
            confirmButtonText: 'Abrir PDF', cancelButtonText: 'Cerrar', confirmButtonColor: '#1e3a8a',
            didOpen: () => {
                const root = Swal.getHtmlContainer();
                const $ = s => root.querySelector(s);
                const confirmar = Swal.getConfirmButton();

                // «Todos» imprime una hoja por chofer; «Solo uno» elige a uno de la lista (con buscador si son varios).
                let modo = 'todos';
                const botonConteo = () => {
                    confirmar.disabled = !datos || sel.size === 0;
                    confirmar.textContent = sel.size > 1 ? `Abrir PDF (${sel.size} choferes)` : 'Abrir PDF';
                };

                const lista = () => {
                    const ids = Object.keys(datos.velocidades || {}).filter(id => resumenChofer(datos.velocidades[id], lunes).max);
                    if (!ids.length) { sel.clear(); $('#vr-cont').innerHTML = '<div class="vr-vacio">Ningún chofer de Bolsa Flexible tiene velocidad registrada esa semana.</div>'; botonConteo(); return; }
                    const filas = ids.map(id => ({ id, p: (datos.personas || {})[id] || {}, r: resumenChofer(datos.velocidades[id], lunes) })).filter(f => f.r.max)
                        .sort((a, b) => (modo === 'uno' ? String(a.p.nombre || '').localeCompare(String(b.p.nombre || ''), 'es') : b.r.max.vel - a.r.max.vel));
                    if (modo === 'todos') { sel.clear(); filas.forEach(f => sel.add(f.id)); }
                    else { const k = filas.find(f => sel.has(f.id)); sel.clear(); sel.add((k || filas[0]).id); }
                    const fila = f => {
                        const q = esc(`${f.p.nombre || ''} ${f.p.rut || ''}`.toLowerCase());
                        const cuerpo = `<span class="vr-n">${esc(f.p.nombre || 'Chofer ' + f.id)}</span>
                            <span class="vel-p vel-${nivel(f.r.max.vel)}">${nivel(f.r.max.vel) === 'x' ? FLECHA : ''}${esc(f.r.max.vel)}</span>
                            <span class="vr-s">${esc(f.p.rut || 'Sin RUT')} · ${esc(f.r.patentes.join(', '))} · ${f.r.filas.length} ${f.r.filas.length === 1 ? 'día' : 'días'}${f.r.sobre ? ` · ${f.r.sobre} sobre ${LIMITE}` : ''}</span>`;
                        return modo === 'uno'
                            ? `<label class="vr-fila" data-q="${q}"><input type="radio" name="vr-uno" data-id="${esc(f.id)}" ${sel.has(f.id) ? 'checked' : ''}>${cuerpo}</label>`
                            : `<div class="vr-fila vr-fija" data-q="${q}"><i class="bi bi-check-circle-fill vr-ok" aria-hidden="true"></i>${cuerpo}</div>`;
                    };
                    $('#vr-cont').innerHTML = `<div class="vr-modo" role="group" aria-label="Qué choferes imprimir">
                            <button type="button" data-m="todos" aria-pressed="${modo === 'todos'}">Todos <span>${ids.length}</span></button>
                            <button type="button" data-m="uno" aria-pressed="${modo === 'uno'}">Solo uno</button>
                        </div>
                        ${modo === 'uno' && ids.length > 4 ? '<input type="search" id="vr-buscar" class="vr-buscar" placeholder="Buscar por nombre o RUT" autocomplete="off" aria-label="Buscar chofer">' : ''}
                        <div class="vr-lista">${filas.map(fila).join('')}<div class="vr-vacio" id="vr-sin" hidden>Ningún chofer coincide.</div></div>`;
                    root.querySelectorAll('.vr-modo button').forEach(b => b.addEventListener('click', () => { if (modo !== b.dataset.m) { modo = b.dataset.m; lista(); } }));
                    root.querySelectorAll('.vr-fila input').forEach(c => c.addEventListener('change', () => { sel.clear(); sel.add(c.dataset.id); botonConteo(); }));
                    const buscar = $('#vr-buscar');
                    if (buscar) buscar.addEventListener('input', () => {
                        const t = buscar.value.trim().toLowerCase(); let n = 0;
                        root.querySelectorAll('.vr-fila').forEach(f => { const ok = !t || f.dataset.q.includes(t); f.hidden = !ok; if (ok) n++; });
                        $('#vr-sin').hidden = n > 0;
                    });
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
                    pedir(lunes, dom).then(j => { if (t !== ticket) return; datos = j; lista(); })
                        .catch(e => { if (t === ticket) $('#vr-cont').innerHTML = `<div class="vr-vacio" role="alert" style="color:#a82f26">No se pudo leer el GPS: ${esc(e.message)}</div>`; });
                };

                $('#vr-ant').addEventListener('click', () => { lunes = sumar(lunes, -7); cargar(); });
                $('#vr-sig').addEventListener('click', () => { lunes = sumar(lunes, 7); cargar(); });
                cargar();
            },
            preConfirm: async () => {
                if (!datos || !sel.size) { Swal.showValidationMessage('Elige al menos un chofer.'); return false; }
                // La pestaña se abre en el mismo clic (después de generar el PDF el navegador podría bloquearla) y recibe el PDF cuando está listo.
                const pestana = window.open('', '_blank');
                if (pestana) pestana.document.title = 'Reporte de velocidades';
                try {
                    const pdf = await generarPdf(lunes, datos, Object.keys(datos.velocidades).filter(i => sel.has(i)));
                    const url = URL.createObjectURL(new Blob([pdf.blob], { type: 'application/pdf' }));
                    if (pestana) pestana.location.href = url; else window.open(url, '_blank');
                    setTimeout(() => URL.revokeObjectURL(url), 10 * 60 * 1000);
                    return true;
                } catch (e) { if (pestana) pestana.close(); Swal.showValidationMessage(`No se pudo generar el PDF: ${e.message}`); return false; }
            },
        });
    };

    // Si el archivo llegó después de pintada la grilla (carga diferida) y la lámina ya está activa, las celdas no tienen su espacio: se pinta una vez más.
    const c0 = document.getElementById('marcaciones-view-container');
    const s0 = window.stateMarcacionesApp;
    if (c0 && s0 && s0.viewMode === 'velocidad' && s0.data && c0.querySelector('.matrix-table-premium') && typeof window.renderVistaAnalitica === 'function') window.renderVistaAnalitica(s0.data, c0);
})();
