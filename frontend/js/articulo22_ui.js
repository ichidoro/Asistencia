/**
 * Artículo 22 — diseño B elegido por el dueño (02-11-2026): las personas del Artículo 22 a la izquierda y, a la derecha,
 * el día y la semana de la persona elegida, con su botón para registrar. Se arma con FichaCfg (config_ficha.js); el
 * historial por rango se descarga en Excel desde el encabezado.
 * Las cadenas se arman con «+» (el minificador del servidor junta las plantillas anidadas).
 */
const Articulo22Module = (function () {
    'use strict';
    const DIAS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
    const DIAS_C = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
    const REFRESCO_MS = 60000;

    let fecha = hoyISO(), datos = null, error = null, temporizador = null, preguntando = false, excelAbierto = false;
    const semanas = {};   // 'empleado|lunes' → { t: hora de lectura, regs: registros del historial }

    // ── utilidades ─────────────────────────────────────────────
    function pad(n) { return (n < 10 ? '0' : '') + n; }
    function iso(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
    function hoyISO() { return iso(new Date()); }
    function fechaDe(f) { return new Date(f + 'T12:00:00'); }
    function sumar(f, n) { const d = fechaDe(f); d.setDate(d.getDate() + n); return iso(d); }
    function dmy(f) { return f ? f.split('-').reverse().join('-') : ''; }
    function lunesDe(f) { return sumar(f, -((fechaDe(f).getDay() + 6) % 7)); }
    function minutos(h) { if (!h) return null; const p = String(h).split(':'); return parseInt(p[0], 10) * 60 + parseInt(p[1], 10) + (p[2] ? parseInt(p[2], 10) / 60 : 0); }
    function hhmm(m) { m = Math.floor(m) % 1440; return pad(Math.floor(m / 60)) + ':' + pad(m % 60); }
    function ahoraMin() { const d = new Date(); return d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60; }
    function dur(m) { m = Math.max(0, Math.floor(m || 0)); return Math.floor(m / 60) + 'h ' + pad(m % 60) + 'm'; }
    // Jornada y tiempo fuera se redondean al minuto y el tiempo en planta se trunca, igual que el servidor
    function durR(m) { return dur(Math.round(m || 0)); }
    function esc(s) { return window.FichaCfg ? FichaCfg.esc(s) : String(s == null ? '' : s); }
    function nombre(s) { return window.nombrePersona ? window.nombrePersona(s) : String(s || '').toUpperCase(); }
    function puede(p) { return typeof AuthService === 'undefined' || AuthService.hasPermission(p); }
    function aviso(msg, tipo) { if (typeof showToast === 'function') showToast(msg, tipo || 'success'); }
    function cabeceras() { return { 'Authorization': 'Bearer ' + localStorage.getItem('access_token') }; }
    async function leer(url) {
        const r = await fetch(url, { headers: cabeceras() });
        if (!r.ok) { let m = 'No se pudo leer el Artículo 22.'; try { m = (await r.json()).detail || m; } catch (_) {} throw new Error(m); }
        return r.json();
    }
    function cont() { return document.getElementById('art22-container'); }
    function palabra(t) { return t === 'E' ? 'ENTRADA' : 'SALIDA'; }

    // Mismo cálculo del servidor (_analizar_dia): un tramo es una ENTRADA seguida de una SALIDA; «fuera» es el tiempo
    // entre una SALIDA y la ENTRADA siguiente; la jornada va de la primera ENTRADA a la última SALIDA. Hoy, una ENTRADA
    // sin SALIDA cuenta hasta ahora.
    function analizar(marcas, esHoy) {
        const ms = [];
        let previo = null;
        marcas.forEach(function (m) {
            let v = minutos(m.hora);
            while (previo !== null && v < previo) v += 1440;
            previo = v;
            ms.push({ t: m.tipo, v: v, m: m });
        });
        const tramos = [];
        let enPlanta = 0, fuera = 0, primera = null, ultimaS = null, cierre = null, abierto = null, incompleto = false;
        for (let i = 0; i < ms.length; i++) {
            if (ms[i].t === 'E' && ms[i + 1] && ms[i + 1].t === 'S') {
                if (primera === null) primera = ms[i].v;
                if (cierre !== null) fuera += ms[i].v - cierre;
                enPlanta += ms[i + 1].v - ms[i].v;
                tramos.push([ms[i].v, ms[i + 1].v, false]);
                cierre = ultimaS = ms[i + 1].v;
                i++;
            } else if (ms[i].t === 'E' && i === ms.length - 1 && esHoy) {
                abierto = ms[i].v;
                if (primera === null) primera = ms[i].v;
                if (cierre !== null) fuera += ms[i].v - cierre;
                const ahora = Math.max(ahoraMin(), ms[i].v);
                enPlanta += ahora - ms[i].v;
                tramos.push([ms[i].v, ahora, true]);
            } else {
                incompleto = true;
            }
        }
        const fin = abierto !== null ? Math.max(ahoraMin(), abierto) : ultimaS;
        return { tramos: tramos, enPlanta: enPlanta, fuera: fuera, primera: primera, fin: fin, abierto: abierto, incompleto: incompleto,
                 jornada: (primera !== null && fin !== null) ? fin - primera : null };
    }

    function personas() {
        const esHoy = fecha === hoyISO();
        return ((datos && datos.empleados) || []).map(function (e) {
            const marcas = (e.marcas || []).slice();
            return { id: e.empleado_id, n: nombre(e.nombre), cargo: e.cargo || '', area: e.area || '', marcas: marcas,
                     dentro: !!e.sesion_abierta && esHoy, estadia: e.estadia_total_min || 0, a: analizar(marcas, esHoy) };
        }).sort(function (x, y) { return x.n.localeCompare(y.n, 'es'); });
    }

    // ── pintar ─────────────────────────────────────────────────
    function navDia() {
        const esHoy = fecha === hoyISO();
        return '<div class="ptB-dia" role="group" aria-label="Día">'
            + '<button type="button" data-a22-dia="-1" aria-label="Día anterior"><i class="bi bi-chevron-left" aria-hidden="true"></i></button>'
            + '<span>' + DIAS[fechaDe(fecha).getDay()] + '</span>'
            + '<input type="date" id="a22-fecha" value="' + fecha + '" max="' + hoyISO() + '" aria-label="Elegir día">'
            + '<button type="button" data-a22-dia="1" aria-label="Día siguiente"' + (esHoy ? ' disabled' : '') + '><i class="bi bi-chevron-right" aria-hidden="true"></i></button></div>'
            + (esHoy ? '' : '<button type="button" class="fcB-btn" data-a22-hoy>Hoy</button>');
    }

    function barraExcel(ps) {
        const lunes = lunesDe(fecha), hasta = sumar(lunes, 6) > hoyISO() ? hoyISO() : sumar(lunes, 6);
        return '<div class="ptB-excel' + (excelAbierto ? '' : ' d-none') + '" id="a22-excel">'
            + '<div class="ptB-excel-c"><label for="a22-x-desde">Desde</label><input type="date" class="fcB-inp" id="a22-x-desde" value="' + lunes + '" max="' + hoyISO() + '"></div>'
            + '<div class="ptB-excel-c"><label for="a22-x-hasta">Hasta</label><input type="date" class="fcB-inp" id="a22-x-hasta" value="' + hasta + '" max="' + hoyISO() + '"></div>'
            + '<div class="ptB-excel-c ancho"><label for="a22-x-emp">Persona</label><select class="fcB-inp" id="a22-x-emp"><option value="">Todas</option>'
            + ps.map(function (p) { return '<option value="' + p.id + '">' + esc(p.n) + '</option>'; }).join('') + '</select></div>'
            + '<div class="ptB-excel-b"><button type="button" class="fcB-btn pri" data-a22-descargar><i class="bi bi-download" aria-hidden="true"></i>Descargar Excel</button>'
            + '<button type="button" class="fcB-btn" data-a22-excel>Cerrar</button></div></div>';
    }

    function pintar() {
        const c = cont();
        if (!c || !window.FichaCfg) return;
        if (error && !datos) {
            c.innerHTML = '<div class="fcB"><p class="fcB-vacio">' + esc(error) + ' <button type="button" class="fcB-btn" data-a22-recargar>Reintentar</button></p></div>';
            return;
        }
        const esHoy = fecha === hoyISO(), ps = personas();
        FichaCfg.montar(c, {
            clave: 'art22',
            titulo: 'Artículo 22',
            descripcion: 'Las personas del Artículo 22 a la izquierda; a la derecha, el día y la semana de la persona elegida, con su botón para registrar.',
            acciones: navDia() + '<button type="button" class="fcB-btn" data-a22-excel aria-expanded="' + excelAbierto + '"><i class="bi bi-file-earmark-spreadsheet" aria-hidden="true"></i>Excel</button>',
            antes: barraExcel(ps),
            buscar: 'Buscar persona',
            items: ps,
            id: function (p) { return p.id; },
            etiqueta: function (p) { return p.n; },
            detalle: function (p) { return p.area; },
            estado: esHoy ? function (p) { return p.dentro ? { t: 'En planta', tono: 'si' } : (p.marcas.length ? { t: 'Fuera', tono: 'fuera' } : { t: 'Sin marcas', tono: '' }); } : null,
            sub: function (p) { return p.marcas.length ? dur(p.estadia) + ' · ' + p.marcas.length + (p.marcas.length === 1 ? ' marca' : ' marcas') : (esHoy ? '' : 'Sin marcas'); },
            vacio: datos ? 'No hay personas en el Artículo 22. Se marcan desde la ficha de cada persona, en Empleados.' : 'Cargando…',
            ficha: ficha
        });
    }

    function linea(p) {
        const t = p.a.tramos;
        if (!t.length) return '';
        let ini = Math.min(7 * 60, Math.floor(t[0][0] / 60) * 60), fin = Math.max(21 * 60, Math.ceil(t[t.length - 1][1] / 60) * 60);
        const w = fin - ini;
        const segs = t.map(function (s) {
            return '<span class="ptB-seg' + (s[2] ? ' abierto' : '') + '" style="left:' + ((s[0] - ini) / w * 100).toFixed(2) + '%;width:' + Math.max(0.6, (s[1] - s[0]) / w * 100).toFixed(2) + '%"'
                + ' title="' + hhmm(s[0]) + ' a ' + (s[2] ? 'ahora' : hhmm(s[1])) + '"></span>';
        }).join('');
        let reg = '';
        for (let h = Math.ceil(ini / 60) + 1; h < fin / 60; h += 2) reg += '<span style="left:' + ((h * 60 - ini) / w * 100).toFixed(2) + '%">' + pad(h % 24) + ':00</span>';
        return '<div class="ptB-linea" role="img" aria-label="En planta: ' + esc(t.map(function (s) { return hhmm(s[0]) + ' a ' + (s[2] ? 'ahora' : hhmm(s[1])); }).join(', ')) + '"><span class="ptB-pista"></span>' + segs + '</div>'
            + '<div class="ptB-reglas" aria-hidden="true">' + reg + '</div>';
    }

    function ficha(p, panel) {
        const F = FichaCfg, esHoy = fecha === hoyISO(), a = p.a;
        const diaLargo = DIAS[fechaDe(fecha).getDay()].toLowerCase() + ' ' + dmy(fecha);
        let accion = '';
        if (esHoy && puede('porteria.art22')) {
            const tipo = p.dentro ? 'S' : 'E';
            accion = '<button type="button" class="fcB-btn ' + (tipo === 'E' ? 'ok' : 'pri') + '" data-a22-marcar="' + p.id + '" data-tipo="' + tipo + '">'
                + '<i class="bi bi-box-arrow-' + (tipo === 'E' ? 'in-right' : 'right') + '" aria-hidden="true"></i>Registrar ' + palabra(tipo) + '</button>';
        } else if (!esHoy) {
            accion = '<button type="button" class="fcB-btn" data-a22-hoy>Ir a hoy para registrar</button>';
        }
        let h = F.cabeza(p.n, [p.cargo, p.area].filter(Boolean).join(' · '), accion);
        if (p.marcas.length) {
            h += '<div class="ptB-cifras">'
                + '<div><small>Jornada' + (a.primera !== null ? ' (' + hhmm(a.primera) + ' a ' + (a.abierto !== null ? 'ahora' : hhmm(a.fin)) + ')' : '') + '</small><b class="num">' + (a.jornada !== null ? durR(a.jornada) : '—') + '</b></div>'
                + '<div><small>Tiempo fuera de planta</small><b class="num">' + durR(a.fuera) + '</b></div>'
                + '<div><small>Tiempo en planta</small><b class="num">' + dur(a.enPlanta) + '</b></div></div>'
                + (a.incompleto ? '<p class="fcB-nota ptB-ojo"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i> Hay una marca sin su pareja (una ENTRADA sin SALIDA o al revés): ese tramo no suma horas.</p>' : '')
                + F.seccion('Línea del ' + diaLargo) + linea(p);
        }
        h += F.seccion('Marcas del ' + diaLargo)
            + (p.marcas.length
                ? '<div class="ptB-marcas">' + p.marcas.map(function (m) {
                    return '<div class="ptB-marca"><span class="ptB-mov ' + (m.tipo === 'E' ? 'e' : 's') + '">' + palabra(m.tipo) + '</span><b class="num">' + esc(String(m.hora).substring(0, 5)) + '</b>'
                        + '<small>' + (m.registrado_por_nombre ? 'Registró ' + esc(m.registrado_por_nombre) : '&nbsp;') + '</small>'
                        + (m.observaciones ? '<small class="obs">' + esc(m.observaciones) + '</small>' : '') + '</div>';
                }).join('') + '</div>'
                : '<p class="fcB-nota">' + (esHoy ? 'Todavía no tiene marcas hoy.' : 'No tuvo marcas este día.') + '</p>');
        const lunes = lunesDe(fecha);
        h += F.seccion('Su semana (' + dmy(lunes).slice(0, 5) + ' al ' + dmy(sumar(lunes, 6)) + ')') + '<div class="ptB-semana" id="a22-semana"><p class="fcB-vacio">Cargando la semana…</p></div>';
        panel.innerHTML = h;
        pintarSemana(p);
    }

    async function pintarSemana(p) {
        const lunes = lunesDe(fecha), clave = p.id + '|' + lunes, hoy = hoyISO();
        let s = semanas[clave];
        try {
            if (!s || Date.now() - s.t > 5 * 60000) {
                const d = await leer('/api/articulo22/historial/?desde=' + lunes + '&hasta=' + sumar(lunes, 6) + '&empleado_id=' + p.id + '&limit=20');
                s = semanas[clave] = { t: Date.now(), regs: d.registros || [] };
            }
        } catch (e) {
            const box = document.getElementById('a22-semana');
            if (box) box.innerHTML = '<p class="fcB-vacio">' + esc(e.message) + '</p>';
            return;
        }
        const box = document.getElementById('a22-semana');
        if (!box || FichaCfg.elegidoDe('art22') !== String(p.id)) return;
        const filas = [];
        for (let i = 0; i < 7; i++) {
            const f = sumar(lunes, i);
            let r = s.regs.find(function (x) { return x.fecha === f; }) || null;
            let txt, min = 0, ojo = false;
            if (f === fecha) {
                // El día elegido se toma de las marcas en pantalla (hoy, hasta este minuto)
                min = p.a.enPlanta;
                txt = p.marcas.length ? (p.a.primera !== null ? hhmm(p.a.primera) + ' a ' + (p.a.abierto !== null ? 'ahora' : (p.a.fin !== null ? hhmm(p.a.fin) : '—')) + ' · ' : '') + dur(min) : 'Sin marcas';
                ojo = p.a.incompleto;
            } else if (r) {
                min = r.estadia_min || 0;
                txt = (r.primera_entrada ? r.primera_entrada.substring(0, 5) : '—') + ' a ' + (r.ultima_salida ? r.ultima_salida.substring(0, 5) : 'sin SALIDA') + ' · ' + r.estadia_display;
                ojo = !!r.incompleto;
            } else {
                txt = f > hoy ? '' : 'Sin marcas';
            }
            filas.push({ f: f, txt: txt, min: min, ojo: ojo });
        }
        const max = Math.max(60, Math.max.apply(null, filas.map(function (x) { return x.min; })));
        box.innerHTML = filas.map(function (x) {
            const d = fechaDe(x.f);
            return '<div class="ptB-sd' + (x.f === fecha ? ' hoy' : '') + '"><span>' + DIAS_C[d.getDay()] + ' ' + d.getDate() + '</span>'
                + '<span class="ptB-sb"><span style="width:' + (x.min / max * 100).toFixed(1) + '%"></span></span>'
                + '<span class="num' + (x.ojo ? ' ojo' : '') + '">' + esc(x.txt) + (x.ojo ? ' · marca sin pareja' : '') + '</span></div>';
        }).join('');
    }

    // ── datos y acciones ───────────────────────────────────────
    async function recargar() {
        try {
            datos = await leer('/api/articulo22/estado-dia/?fecha=' + fecha);
            error = null;
        } catch (e) {
            error = e.message;
            if (datos) aviso(e.message, 'danger');
        }
        pintar();
    }

    async function cambiarDia(f) {
        if (!f) return;
        fecha = f > hoyISO() ? hoyISO() : f;
        datos = null;
        pintar();
        await recargar();
    }

    async function marcar(btn) {
        const id = parseInt(btn.dataset.a22Marcar, 10), tipo = btn.dataset.tipo;
        const p = personas().find(function (x) { return x.id === id; });
        if (!p) return;
        const ahora = hhmm(ahoraMin());
        if (typeof uiConfirm === 'function') {
            preguntando = true;
            let si = false;
            try { si = await uiConfirm('¿Registrar la ' + palabra(tipo) + '?', { quien: p.n, items: ['Artículo 22 · hora ' + ahora], confirmText: 'Registrar ' + palabra(tipo) }); }
            finally { preguntando = false; }
            if (!si) return;
        }
        await FichaCfg.trabajando(btn, async function () {
            try {
                const r = await fetch('/api/articulo22/marcar/', { method: 'POST', headers: Object.assign({ 'Content-Type': 'application/json' }, cabeceras()), body: JSON.stringify({ empleado_id: id }) });
                const d = await r.json().catch(function () { return {}; });
                if (!r.ok) throw new Error(d.detail || 'No se pudo registrar.');
                const txt = palabra(d.tipo || tipo) + ' registrada: ' + nombre(d.nombre || p.n) + (d.hora ? ' a las ' + String(d.hora).substring(0, 5) : '');
                const olvidar = function () { Object.keys(semanas).forEach(function (k) { if (k.indexOf(id + '|') === 0) delete semanas[k]; }); };
                if (d.deshacer && window.Avisos && Avisos.conDeshacer) Avisos.conDeshacer(txt, d.deshacer, { alDeshacer: function () { olvidar(); recargar(); } });
                else aviso(txt);
                olvidar();
            } catch (e) { aviso(e.message || 'No se pudo registrar.', 'danger'); }
        });
        await recargar();
    }

    async function descargarExcel(btn) {
        const desde = document.getElementById('a22-x-desde').value, hasta = document.getElementById('a22-x-hasta').value, emp = document.getElementById('a22-x-emp').value;
        if (!desde || !hasta) { aviso('Faltan las fechas. Elija desde y hasta.', 'warning'); return; }
        if (desde > hasta) { aviso('La fecha «desde» es posterior a «hasta».', 'warning'); return; }
        await FichaCfg.trabajando(btn, async function () {
            try {
                const r = await fetch('/api/articulo22/exportar-excel/?desde=' + desde + '&hasta=' + hasta + (emp ? '&empleado_id=' + emp : ''), { headers: cabeceras() });
                if (!r.ok) { let m = 'No se pudo generar el Excel.'; try { m = (await r.json()).detail || m; } catch (_) {} throw new Error(m); }
                const blob = await r.blob(), a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = 'articulo22_' + desde + '_a_' + hasta + (emp ? '_emp' + emp : '') + '.xlsx';
                document.body.appendChild(a); a.click(); a.remove();
                setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
            } catch (e) { aviso(e.message || 'No se pudo descargar el Excel.', 'danger'); }
        });
    }

    let oyentes = false;
    function escuchar() {
        if (oyentes) return;
        oyentes = true;
        document.addEventListener('click', function (ev) {
            const c = cont();
            if (!c || !c.contains(ev.target)) return;
            const b = ev.target.closest('button');
            if (!b) return;
            if (b.dataset.a22Dia) { cambiarDia(sumar(fecha, parseInt(b.dataset.a22Dia, 10))); return; }
            if (b.hasAttribute('data-a22-hoy')) { cambiarDia(hoyISO()); return; }
            if (b.hasAttribute('data-a22-recargar')) { recargar(); return; }
            if (b.hasAttribute('data-a22-excel')) {
                excelAbierto = !excelAbierto;
                const x = document.getElementById('a22-excel');
                if (x) x.classList.toggle('d-none', !excelAbierto);
                c.querySelectorAll('.fcB-acc [data-a22-excel]').forEach(function (k) { k.setAttribute('aria-expanded', excelAbierto); });
                return;
            }
            if (b.hasAttribute('data-a22-descargar')) { descargarExcel(b); return; }
            if (b.dataset.a22Marcar) { marcar(b); }
        });
        document.addEventListener('change', function (ev) {
            if (ev.target && ev.target.id === 'a22-fecha') cambiarDia(ev.target.value);
        });
    }

    async function initTab() {
        escuchar();
        if (fecha !== hoyISO() && !datos) fecha = hoyISO();
        pintar();
        await recargar();
        if (temporizador) clearInterval(temporizador);
        temporizador = setInterval(function () {
            const pane = document.getElementById('tab-ingreso-art22');
            if (!pane || !pane.classList.contains('active') || !document.querySelector('#page-porteria.active') || document.visibilityState !== 'visible') return;
            if (preguntando || fecha !== hoyISO()) return;
            const act = document.activeElement;
            if (act && act.closest && act.closest('#a22-excel')) return;
            recargar();
        }, REFRESCO_MS);
    }

    function destroy() { if (temporizador) { clearInterval(temporizador); temporizador = null; } }

    return { initTab: initTab, recargar: recargar, destroy: destroy };
})();
