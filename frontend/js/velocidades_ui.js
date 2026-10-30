/**
 * Lámina «Velocidad» de la grilla de Marcaciones: la velocidad máxima del GPS de cada chofer, día por día.
 * El chofer sale del plan de Despacho Diario (Nexacol) y la velocidad, del GPS del camión que tenía asignado ese día.
 * Todo lo que toca este archivo vive en window.mxVel*; marcaciones_ui.js solo lo llama (celda, leyenda, tooltip y carga).
 * Carga sin bloquear: la grilla se pinta con esqueletos en las celdas de los choferes y se rellenan en el sitio cuando llega el dato.
 */
(function () {
    'use strict';

    // Los camiones de carretera tienen tope de 90 km/h: sobre eso es «alta»; sobre 100, «exceso». Cambiar acá si la regla de la empresa es otra.
    const ALTA = 90, EXCESO = 100;
    const MAX_DIAS = 62; // lo que acepta Nexacol en una consulta

    const ST = { clave: '', estado: 'idle', datos: {}, sinCalzar: [], error: '', ticket: 0 };

    const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const esChofer = emp => typeof window.categoriaCargo === 'function' && window.categoriaCargo(emp && emp.cargo) === 'chofer';
    const nivel = v => (v > EXCESO ? 'x' : v > ALTA ? 'a' : 'n');
    const FLECHA = '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 10V2M2.8 5.2 6 2l3.2 3.2"/></svg>';
    const ddmm = f => { const p = String(f).split('-'); return p.length === 3 ? `${p[2]}-${p[1]}` : f; };

    function periodo() {
        const p = window.stateMarcacionesApp && window.stateMarcacionesApp.data && window.stateMarcacionesApp.data.periodo;
        if (!p || !p.inicio || !p.fin) return null;
        let ini = p.inicio;
        const dias = typeof window.getDatesInRange === 'function' ? window.getDatesInRange(p.inicio, p.fin) : [];
        if (dias.length > MAX_DIAS) ini = dias[dias.length - MAX_DIAS];
        return { ini, fin: p.fin };
    }

    function chip(info) {
        const n = nivel(info.vel);
        const aria = `Velocidad máxima ${info.vel} kilómetros por hora${n === 'x' ? ', exceso' : n === 'a' ? ', alta' : ''}`;
        const flechas = n === 'x' ? FLECHA + FLECHA : n === 'a' ? FLECHA : '';
        return `<span class="vel-p vel-${n}" role="img" aria-label="${aria}">${flechas}${esc(info.vel)}</span>`;
    }

    function interior(empId, fecha, trabajo) {
        if (ST.estado === 'idle' || ST.estado === 'cargando') return trabajo ? '<span class="vel-sk" aria-hidden="true"></span>' : '';
        if (ST.estado === 'error') return ''; // el aviso de la leyenda lo explica; los «—» dirían que no hubo dato
        const info = ST.datos[String(empId)] && ST.datos[String(empId)][fecha];
        if (info) return chip(info);
        return trabajo ? '<span class="vel-v" title="Sin velocidad del GPS ese día" aria-label="Sin dato de GPS">—</span>' : '';
    }

    /** Contenido de la celda de un día. Solo los choferes llevan algo; el resto de la grilla queda en blanco. */
    window.mxVelCelda = function (emp, fecha, trabajo) {
        if (!esChofer(emp)) return '';
        return `<span class="vel-slot" data-t="${trabajo ? 1 : 0}">${interior(emp.id, fecha, trabajo)}</span>`;
    };

    function nombreDe(empId) {
        const el = document.querySelector(`#row-empleado-${empId} .emp-name-link`);
        return el ? el.textContent.trim() : '';
    }

    /** Barra de leyenda de la lámina (va donde van los estados). */
    window.mxVelLeyenda = function () {
        let estado = '';
        if (ST.estado === 'cargando' || ST.estado === 'idle') {
            estado = '<span class="vel-resumen" role="status"><span class="vel-sk" aria-hidden="true"></span>Leyendo el GPS…</span>';
        } else if (ST.estado === 'error') {
            estado = `<span class="vel-aviso vel-err" role="alert"><i class="bi bi-exclamation-triangle-fill"></i>No se pudo leer el GPS: ${esc(ST.error)} <button type="button" onclick="mxVelReintentar()">Reintentar</button></span>`;
        } else {
            let max = null, sobre = 0;
            Object.keys(ST.datos).forEach(id => Object.keys(ST.datos[id]).forEach(f => {
                const i = ST.datos[id][f];
                if (i.vel > ALTA) sobre++;
                if (!max || i.vel > max.vel) max = { vel: i.vel, id, f };
            }));
            if (max) estado += `<span class="vel-resumen" title="La velocidad más alta registrada en el período">Máxima del período <b>${esc(max.vel)} km/h</b>${nombreDe(max.id) ? ' · ' + esc(nombreDe(max.id)) : ''} · ${esc(ddmm(max.f))}</span>`;
            else estado += '<span class="vel-resumen">Ningún chofer con velocidad en este período</span>';
            if (sobre) estado += `<span class="vel-resumen"><b>${sobre}</b> ${sobre === 1 ? 'día' : 'días'} sobre ${ALTA}</span>`;
            if (ST.sinCalzar.length) {
                const lista = ST.sinCalzar.map(x => `${x.nombre} (${x.dias.length} ${x.dias.length === 1 ? 'día' : 'días'})`).join(', ');
                estado += `<span class="vel-aviso" tabindex="0" title="Nombres del plan de Despacho que no se pudieron asociar a una sola persona de Asistencia: ${esc(lista)}"><i class="bi bi-person-exclamation"></i>${ST.sinCalzar.length} ${ST.sinCalzar.length === 1 ? 'nombre' : 'nombres'} del plan sin asociar</span>`;
            }
        }
        return `<div class="vel-leyenda" id="vel-leyenda">
            <span class="fw-bold" style="color:#1a2326">Velocidad máxima del GPS · km/h</span>
            <span class="vel-ley"><span class="vel-p">${ALTA}</span>Normal</span>
            <span class="vel-ley"><span class="vel-p vel-a">${FLECHA}${ALTA + 1}</span>Alta · más de ${ALTA}</span>
            <span class="vel-ley"><span class="vel-p vel-x">${FLECHA}${FLECHA}${EXCESO + 1}</span>Exceso · más de ${EXCESO}</span>
            <span class="vel-ley"><span class="vel-v" style="font-size:.9rem">—</span>Sin dato</span>
            ${estado}
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

    /** Pide las velocidades del período mostrado (una vez por período) y rellena las celdas cuando llegan. */
    window.mxVelAsegurar = function (container) {
        const s = window.stateMarcacionesApp;
        if (!s || s.viewMode !== 'velocidad' || !container) return;
        const p = periodo();
        if (!p) return;
        const clave = `${p.ini}|${p.fin}`;
        if (ST.clave === clave && ST.estado !== 'idle') return; // ya cargada o en camino
        ST.clave = clave; ST.estado = 'cargando'; ST.error = '';
        const ticket = ++ST.ticket;
        fetch(`/api/asistencia/gps/velocidades-choferes/?desde=${p.ini}&hasta=${p.fin}`, { headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` } })
            .then(async r => {
                const j = await r.json().catch(() => ({}));
                if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `error ${r.status}`);
                return j;
            })
            .then(j => { if (ticket === ST.ticket) { ST.datos = j.velocidades || {}; ST.sinCalzar = j.sin_calzar || []; ST.estado = 'ok'; } })
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

    // Si el archivo llegó después de pintada la grilla (carga diferida) y la lámina ya está activa, las celdas no tienen su espacio: se pinta una vez más.
    const c0 = document.getElementById('marcaciones-view-container');
    const s0 = window.stateMarcacionesApp;
    if (c0 && s0 && s0.viewMode === 'velocidad' && s0.data && c0.querySelector('.matrix-table-premium') && typeof window.renderVistaAnalitica === 'function') window.renderVistaAnalitica(s0.data, c0);
})();
