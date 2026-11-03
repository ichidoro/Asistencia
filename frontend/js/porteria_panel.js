/**
 * Portería — panel general (fusión de los diseños A y B elegida por el dueño, 01-11-2026).
 * Arriba, seis cifras que abren cada sección; abajo, el Artículo 22 con la línea del día y las
 * tarjetas de llaves y visitas. Las secciones completas (rondas, llaves, Artículo 22, flota,
 * proveedores y visitas) son las de siempre: se abren desde las cifras y vuelven al panel.
 * Las cadenas se arman con «+» (el minificador del servidor junta las plantillas anidadas).
 */
const PorteriaPanel = (function () {
    'use strict';

    const VISTAS = {
        art22: { pane: 'tab-ingreso-art22', permiso: 'porteria.art22', init: function () { if (typeof Articulo22Module !== 'undefined') Articulo22Module.initTab(); } },
        llaves: { pane: 'tab-entrega-llaves', permiso: 'porteria.llaves', init: function () { if (typeof LlavesModule !== 'undefined') LlavesModule.initTab(); } },
        visitas: { pane: 'tab-control-visitas', permiso: 'porteria.visitas', init: function () { if (typeof VisitasModule !== 'undefined') VisitasModule.initTab(); } },
        flota: { pane: 'tab-flota-aguacol', permiso: 'porteria.flota', init: function () { if (typeof FlotaModule !== 'undefined') FlotaModule.initTab(); } },
        rondas: { pane: 'tab-rondas-nocturnas', permiso: 'porteria.rondas', init: function () { if (typeof PorteriaModule !== 'undefined') PorteriaModule.cargarHistorialRondas(); } },
        proveedores: { pane: 'tab-ingreso-proveedores', permiso: 'porteria.proveedores', init: function () {} }
    };
    const DIAS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
    const REFRESCO_MS = 60000;

    let datos = { a22: null, llaves: null, visitas: null, flota: null, rondas: null, ubicaciones: null };
    let errores = {};
    let filtro = 'todos', busqueda = '', vista = 'panel', listo = false, temporizador = null;

    // ── utilidades ─────────────────────────────────────────────
    function puede(p) { return typeof AuthService === 'undefined' || AuthService.hasPermission(p); }
    function token() { return localStorage.getItem('access_token'); }
    function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
    function nombre(s) { return window.nombrePersona ? window.nombrePersona(s) : String(s || '').toUpperCase(); }
    function iniciales(s) { return window.inicialesDe ? window.inicialesDe(s) : String(s || '').slice(0, 2).toUpperCase(); }
    function frase(s) { const t = String(s || '').trim().toLowerCase(); return t ? t.charAt(0).toUpperCase() + t.slice(1) : ''; }
    function titulo(s) { return String(s || '').toLowerCase().replace(/(^|[\s\-'])([a-záéíóúñü])/g, function (m, a, b) { return a + b.toUpperCase(); }); }
    function pad(n) { return (n < 10 ? '0' : '') + n; }
    function hoyISO() { const d = new Date(); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
    function ahoraMin() { const d = new Date(); return d.getHours() * 60 + d.getMinutes(); }
    function minutos(h) { if (!h) return null; const p = String(h).split(':'); const v = parseInt(p[0], 10) * 60 + parseInt(p[1], 10); return isNaN(v) ? null : v; }
    function hhmm(m) { return pad(Math.floor(m / 60)) + ':' + pad(m % 60); }
    function duracion(m) { m = Math.max(0, Math.round(m)); return m >= 60 ? Math.floor(m / 60) + ' h ' + pad(m % 60) + ' min' : m + ' min'; }
    function rutVisible(r) {
        const s = String(r || '').replace(/[^0-9kK]/g, '');
        if (s.length < 2) return String(r || '');
        return s.slice(0, -1).replace(/\B(?=(\d{3})+(?!\d))/g, '.') + '-' + s.slice(-1).toUpperCase();
    }
    function aviso(msg, tipo) { if (typeof showToast === 'function') showToast(msg, tipo || 'success'); }

    async function leer(url) {
        const r = await fetch(url, { headers: { 'Authorization': 'Bearer ' + token() } });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
    }
    async function enviar(url, cuerpo) {
        const r = await fetch(url, { method: 'POST', headers: { 'Authorization': 'Bearer ' + token(), 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) });
        const d = await r.json().catch(function () { return {}; });
        if (!r.ok) throw new Error(d.detail || 'No se pudo registrar');
        return d;
    }

    // ── datos ──────────────────────────────────────────────────
    async function cargar() {
        const f = hoyISO();
        const pedidos = [
            ['a22', puede('porteria.art22'), '/api/articulo22/estado-dia/?fecha=' + f],
            ['llaves', puede('porteria.llaves'), '/api/llaves/estado/'],
            ['visitas', puede('porteria.visitas'), '/api/visitas/estado-dia/?fecha=' + f],
            ['flota', puede('porteria.flota || configuracion.flota'), '/api/flota/estado-dia/?fecha=' + f],
            ['rondas', puede('porteria.ver || configuracion.ver'), '/api/porteria/rondas/recientes/?limit=200'],
            ['ubicaciones', puede('porteria.ver || porteria.rondas || configuracion.ver'), '/api/porteria/ubicaciones/']
        ];
        const res = await Promise.allSettled(pedidos.map(function (p) { return p[1] ? leer(p[2]) : Promise.resolve(null); }));
        errores = {};
        res.forEach(function (r, i) {
            const k = pedidos[i][0];
            if (r.status === 'fulfilled') datos[k] = r.value;
            else { errores[k] = true; console.warn('Portería: no se pudo leer ' + k, r.reason); }
        });
    }

    // Personas del Artículo 22 con sus tramos en planta (una salida sin entrada previa cuenta desde medianoche,
    // igual que la sección completa del Artículo 22)
    function personas() {
        const d = datos.a22;
        if (!d || !d.empleados) return [];
        const esHoy = d.fecha === hoyISO(), ahora = ahoraMin();
        return d.empleados.map(function (e) {
            const marcas = (e.marcas || []).map(function (m) { return { t: minutos(m.hora), tipo: m.tipo }; })
                .filter(function (m) { return m.t != null; }).sort(function (a, b) { return a.t - b.t; });
            const tramos = []; let abierto = null, total = 0;
            marcas.forEach(function (m) {
                if (m.tipo === 'E') { if (abierto === null) abierto = m.t; return; }
                const ini = abierto === null ? 0 : abierto;
                tramos.push({ a: ini, b: m.t }); total += m.t - ini; abierto = null;
            });
            const dentro = abierto !== null;
            if (dentro) {
                const fin = esHoy ? Math.max(abierto, ahora) : abierto;
                tramos.push({ a: abierto, b: fin, vivo: esHoy }); total += fin - abierto;
            }
            const ult = marcas.length ? marcas[marcas.length - 1] : null;
            return { id: e.empleado_id, n: nombre(e.nombre), cargo: e.cargo, area: e.area, dentro: dentro, tramos: tramos, total: total,
                     desde: ult ? hhmm(ult.t) : '', marcas: marcas.length };
        }).sort(function (a, b) { return a.n.localeCompare(b.n, 'es'); });
    }

    // Rango de la línea del día: de 07:00 a 21:00, más amplio si hay marcas o la hora actual fuera de él
    function rango(ps) {
        let ini = 7 * 60, fin = 21 * 60;
        ps.forEach(function (p) { p.tramos.forEach(function (t) { ini = Math.min(ini, Math.floor(t.a / 60) * 60); fin = Math.max(fin, Math.ceil(t.b / 60) * 60); }); });
        fin = Math.max(fin, Math.ceil(ahoraMin() / 60) * 60);
        return { ini: Math.max(0, ini), fin: Math.min(24 * 60, fin) };
    }

    // ── pintar ─────────────────────────────────────────────────
    function pintarFecha() {
        const d = new Date();
        const f = document.getElementById('ptg-fecha'), h = document.getElementById('ptg-hora');
        if (f) f.textContent = DIAS[d.getDay()] + ' ' + pad(d.getDate()) + '-' + pad(d.getMonth() + 1) + '-' + d.getFullYear();
        if (h) h.textContent = pad(d.getHours()) + ':' + pad(d.getMinutes());
    }

    function cifra(k, n, u, s) {
        const en = document.getElementById('ptg-n-' + k), eu = document.getElementById('ptg-u-' + k), es = document.getElementById('ptg-s-' + k);
        if (en) en.textContent = n; if (eu && u != null) eu.textContent = u; if (es) es.textContent = s || ' ';
    }

    function pintarResumen(ps) {
        if (datos.a22) { const n = ps.filter(function (p) { return p.dentro; }).length; cifra('art22', n, 'en planta', (ps.length - n) + ' fuera de planta'); }
        else cifra('art22', '—', 'en planta', errores.a22 ? 'No se pudo leer' : '');
        if (datos.llaves) cifra('llaves', datos.llaves.fuera, datos.llaves.fuera === 1 ? 'entregada' : 'entregadas', datos.llaves.disponibles + ' en el tablero');
        else cifra('llaves', '—', 'entregadas', errores.llaves ? 'No se pudo leer' : '');
        if (datos.visitas) { const st = datos.visitas.stats || {}; cifra('visitas', st.en_planta || 0, 'en planta', (st.total_visitas || 0) + (st.total_visitas === 1 ? ' registrada hoy' : ' registradas hoy')); }
        else cifra('visitas', '—', 'en planta', errores.visitas ? 'No se pudo leer' : '');
        if (datos.flota) { const st = datos.flota.stats || {}; cifra('flota', st.en_viaje || 0, 'en viaje', (st.en_planta || 0) + ' en planta'); }
        else cifra('flota', '—', 'en viaje', errores.flota ? 'No se pudo leer' : '');
        if (datos.ubicaciones) {
            const activas = datos.ubicaciones.filter(function (u) { return u.activo !== false; });
            const hoy = hoyISO(), vistos = {};
            (datos.rondas || []).forEach(function (r) { if (String(r.fecha_hora || '').slice(0, 10) === hoy) vistos[r.ubicacion_id] = true; });
            cifra('rondas', datos.rondas ? Object.keys(vistos).length : '—', 'de ' + activas.length, 'puntos revisados hoy');
        } else cifra('rondas', '—', '', errores.ubicaciones ? 'No se pudo leer' : '');
    }

    function filaA22(p, r) {
        const pos = function (t) { return ((Math.max(r.ini, Math.min(r.fin, t)) - r.ini) / (r.fin - r.ini) * 100).toFixed(2) + '%'; };
        let barra = '';
        for (let h = Math.ceil((r.ini + 60) / 180) * 3; h * 60 < r.fin; h += 3) barra += '<b style="left:' + pos(h * 60) + '"></b>';
        p.tramos.forEach(function (t) { barra += '<i style="left:' + pos(t.a) + ';width:calc(' + pos(t.b) + ' - ' + pos(t.a) + ')"></i>'; });
        if (datos.a22 && datos.a22.fecha === hoyISO()) barra += '<span class="ahora" style="left:' + pos(ahoraMin()) + '"></span>';
        p.tramos.forEach(function (t) { if (t.vivo) barra += '<u style="left:' + pos(t.b) + '"></u>'; });
        const est = p.dentro
            ? '<div class="ptG-est ok"><i aria-hidden="true"></i><div><b>En planta</b><span class="pt-num">desde ' + p.desde + '</span></div></div>'
            : '<div class="ptG-est"><i aria-hidden="true"></i><div><b>Fuera</b><span class="pt-num">' + (p.desde ? 'salió ' + p.desde : 'sin marcas hoy') + '</span></div></div>';
        const tiempo = p.total ? duracion(p.total) + ' en planta' : 'Sin marcas hoy';
        const btn = p.dentro
            ? '<button type="button" class="ptG-btn sal" data-a22="' + p.id + '" data-tipo="Salida" aria-label="Registrar salida de ' + esc(p.n) + '"><i class="bi bi-box-arrow-right" aria-hidden="true"></i>Salida</button>'
            : '<button type="button" class="ptG-btn ent" data-a22="' + p.id + '" data-tipo="Entrada" aria-label="Registrar entrada de ' + esc(p.n) + '"><i class="bi bi-box-arrow-in-right" aria-hidden="true"></i>Entrada</button>';
        const sub = [frase(p.cargo), titulo(p.area)].filter(Boolean).join(' · ');
        return '<div class="ptG-fila">'
            + '<div class="ptG-quien"><span class="ptG-av' + (p.dentro ? ' dentro' : '') + '" aria-hidden="true">' + esc(iniciales(p.n)) + '</span>'
            + '<div class="t"><div class="ptG-n">' + esc(p.n) + '</div><div class="ptG-s" title="' + esc(sub) + '">' + esc(sub) + '</div></div></div>'
            + est
            + '<div class="ptG-dia"><div class="ptG-barra" role="img" aria-label="' + esc(tiempo) + '">' + barra + '</div><span class="pt-num">' + tiempo + '</span></div>'
            + btn + '</div>';
    }

    function filasA22(ps) {
        const q = busqueda.trim().toLocaleUpperCase('es-CL');
        const r = rango(ps);
        let vis = ps.filter(function (p) { return !q || p.n.indexOf(q) >= 0 || String(p.area || '').toLocaleUpperCase('es-CL').indexOf(q) >= 0; });
        const dentro = vis.filter(function (p) { return p.dentro; }), fuera = vis.filter(function (p) { return !p.dentro; });
        let h = '';
        if (filtro !== 'fuera') {
            h += '<div class="ptG-grupo">En planta <span>' + dentro.length + '</span></div>';
            h += dentro.length ? dentro.map(function (p) { return filaA22(p, r); }).join('') : '<p class="ptG-vacio">' + (q ? 'Nadie en planta con esa búsqueda.' : 'Nadie del Artículo 22 está en planta ahora.') + '</p>';
        }
        if (filtro !== 'dentro') {
            h += '<div class="ptG-grupo">Fuera de planta <span>' + fuera.length + '</span></div>';
            h += fuera.length ? fuera.map(function (p) { return filaA22(p, r); }).join('') : '<p class="ptG-vacio">' + (q ? 'Nadie fuera de planta con esa búsqueda.' : 'Todos están en planta.') + '</p>';
        }
        return h;
    }

    function tarjetaA22(ps) {
        if (!puede('porteria.art22')) return '';
        if (errores.a22) return tarjetaError('Artículo 22', 'ptG-a22');
        const n = ps.filter(function (p) { return p.dentro; }).length;
        const r = rango(ps);
        const pos = function (t) { return ((t - r.ini) / (r.fin - r.ini) * 100).toFixed(2) + '%'; };
        let eje = '';
        for (let h = Math.ceil((r.ini + 60) / 180) * 3; h * 60 < r.fin; h += 3) eje += '<em style="left:' + pos(h * 60) + '">' + pad(h) + '</em>';
        const seg = function (k, t, c) { return '<button type="button" data-f="' + k + '" class="' + (filtro === k ? 'on' : '') + '" aria-pressed="' + (filtro === k) + '">' + t + ' <b>' + c + '</b></button>'; };
        return '<section class="ptG-card ptG-a22" aria-labelledby="ptg-a22-t">'
            + '<header class="ptG-h"><div><h2 id="ptg-a22-t">Artículo 22</h2><p>Personas exentas de jornada: se registra cada entrada y salida.</p></div>'
            + '<div class="ptG-tools"><div class="ptG-seg" role="group" aria-label="Mostrar">' + seg('todos', 'Todos', ps.length) + seg('dentro', 'En planta', n) + seg('fuera', 'Fuera', ps.length - n) + '</div>'
            + '<label class="ptG-buscar"><i class="bi bi-search" aria-hidden="true"></i><input type="search" id="ptg-buscar" placeholder="Buscar persona" aria-label="Buscar persona" autocomplete="off" value="' + esc(busqueda) + '"></label></div></header>'
            + (ps.length ? '<div class="ptG-cab" aria-hidden="true"><span>Persona</span><span>Estado</span><span class="ptG-eje">' + eje + '</span><span></span></div>'
                + '<div id="ptg-a22-filas">' + filasA22(ps) + '</div>'
                : '<p class="ptG-vacio">No hay personas del Artículo 22. Se agregan en Configuración.</p>')
            + '</section>';
    }

    function tarjetaLlaves() {
        if (!puede('porteria.llaves')) return '';
        if (errores.llaves) return tarjetaError('Llaves');
        const d = datos.llaves || { llaves: [], fuera: 0, disponibles: 0 };
        const fuera = d.llaves.filter(function (l) { return l.estado !== 'DISPONIBLE'; });
        const tablero = d.llaves.filter(function (l) { return l.estado === 'DISPONIBLE'; });
        const hoy = hoyISO(), ahora = new Date();
        let h = '<section class="ptG-card" aria-labelledby="ptg-llaves-t"><header class="ptG-h sm"><div class="tt"><span class="ptG-ic" aria-hidden="true"><i class="bi bi-key"></i></span>'
            + '<div><h2 id="ptg-llaves-t">Llaves</h2><p>' + d.fuera + (d.fuera === 1 ? ' entregada' : ' entregadas') + ' · ' + d.disponibles + ' en el tablero</p></div></div>'
            + '<button type="button" class="ptG-btn sal" data-ir="llaves"><i class="bi bi-journal-text" aria-hidden="true"></i>Catálogo e historial</button></header>';
        h += '<div class="ptG-grupo">Entregadas <span>' + fuera.length + '</span></div>';
        if (!fuera.length) h += '<p class="ptG-vacio">Todas las llaves están en el tablero.</p>';
        fuera.forEach(function (l) {
            const quien = l.entregada_a ? nombre(l.entregada_a.nombre) : 'Sin dato';
            const fh = String(l.entregada_hora || '');
            const f = fh.slice(0, 10), hora = fh.slice(11, 16);
            let cuando = '';
            if (hora) {
                const desde = new Date(f + 'T' + hora + ':00');
                cuando = (f === hoy ? 'Desde las ' + hora : 'Desde el ' + f.slice(8, 10) + '-' + f.slice(5, 7) + ' a las ' + hora)
                    + (isNaN(desde) ? '' : ' · hace ' + duracion((ahora - desde) / 60000));
            }
            h += '<div class="ptG-item"><span class="ptG-ic warn" aria-hidden="true"><i class="bi bi-key-fill"></i></span><div class="t">'
                + '<div class="ptG-n2">' + esc(l.nombre) + '</div>' + (l.ubicacion ? '<div class="ptG-s">' + esc(l.ubicacion) + '</div>' : '')
                + '<div class="ptG-s fuerte">' + esc(quien) + '</div>' + (cuando ? '<div class="ptG-s pt-num">' + esc(cuando) + '</div>' : '') + '</div>'
                + (l.entregada_a ? '<button type="button" class="ptG-btn ent" data-llave="' + l.id + '"><i class="bi bi-box-arrow-in-left" aria-hidden="true"></i>Recibir</button>' : '')
                + '</div>';
        });
        if (tablero.length) h += '<div class="ptG-grupo">En el tablero <span>' + tablero.length + '</span><em>Toque una llave para entregarla</em></div><ul class="ptG-tablero">'
            + tablero.map(function (l) { return '<li><button type="button" data-entregar="' + l.id + '" aria-label="Entregar la llave ' + esc(l.nombre) + '">' + esc(l.nombre) + '<i class="bi bi-box-arrow-right" aria-hidden="true"></i></button></li>'; }).join('') + '</ul>';
        return h + '</section>';
    }

    function tarjetaVisitas() {
        if (!puede('porteria.visitas')) return '';
        if (errores.visitas) return tarjetaError('Visitas');
        const d = datos.visitas || { stats: {}, visitantes: [] };
        const st = d.stats || {};
        const dentro = d.visitantes.filter(function (v) { return v.estado === 'en_planta'; });
        const salieron = d.visitantes.filter(function (v) { return v.estado !== 'en_planta'; });
        const ahora = ahoraMin();
        let h = '<section class="ptG-card" aria-labelledby="ptg-vis-t"><header class="ptG-h sm"><div class="tt"><span class="ptG-ic" aria-hidden="true"><i class="bi bi-person-badge"></i></span>'
            + '<div><h2 id="ptg-vis-t">Visitas</h2><p>' + (st.en_planta || 0) + ' en planta · ' + (st.total_visitas || 0) + ' hoy</p></div></div>'
            + '<button type="button" class="ptG-btn pri" data-ir="visitas"><i class="bi bi-upc-scan" aria-hidden="true"></i>Registrar visita</button></header>';
        h += '<div class="ptG-grupo">En planta <span>' + dentro.length + '</span></div>';
        if (!dentro.length) h += '<p class="ptG-vacio">No hay visitas en planta.</p>';
        dentro.forEach(function (v) {
            const n = v.nombre ? nombre(v.nombre) : '';
            const ent = minutos(v.primera_entrada);
            const motivo = [v.motivo ? v.motivo + (v.persona_contacto ? ' con ' + nombre(v.persona_contacto) : '') : (v.persona_contacto ? 'Visita a ' + nombre(v.persona_contacto) : ''), frase(v.area_destino)].filter(Boolean).join(' · ');
            h += '<div class="ptG-item"><span class="ptG-av dentro" aria-hidden="true">' + (n ? esc(iniciales(n)) : '<i class="bi bi-person"></i>') + '</span><div class="t">'
                + '<div class="ptG-n' + (n ? '' : ' sin') + '">' + (n ? esc(n) : 'Sin nombre registrado') + '</div>'
                + '<div class="ptG-s pt-num">' + esc([titulo(v.empresa), 'RUT ' + rutVisible(v.rut)].filter(Boolean).join(' · ')) + '</div>'
                + (motivo ? '<div class="ptG-s fuerte">' + esc(motivo) + '</div>' : '')
                + '<div class="ptG-meta">' + (v.patente ? '<span class="ptG-patente">' + esc(v.patente) + '</span>' : '')
                + (ent != null ? '<span class="pt-num">Entró a las ' + hhmm(ent) + (d.fecha === hoyISO() ? ' · hace ' + duracion(ahora - ent) : '') + '</span>' : '') + '</div></div>'
                + '<button type="button" class="ptG-btn sal" data-visita="' + esc(v.rut) + '" aria-label="Registrar salida de ' + esc(n || 'la visita RUT ' + rutVisible(v.rut)) + '"><i class="bi bi-box-arrow-right" aria-hidden="true"></i>Salida</button></div>';
        });
        if (salieron.length) {
            h += '<div class="ptG-grupo">Salieron hoy <span>' + salieron.length + '</span></div>';
            salieron.forEach(function (v) {
                const n = v.nombre ? nombre(v.nombre) : '';
                const e = minutos(v.primera_entrada), s = minutos(v.ultima_marca);
                h += '<div class="ptG-item compacto"><span class="ptG-av muted" aria-hidden="true">' + (n ? esc(iniciales(n)) : '<i class="bi bi-person"></i>') + '</span><div class="t">'
                    + '<div class="ptG-n' + (n ? '' : ' sin') + '">' + (n ? esc(n) : 'Sin nombre registrado') + '</div><div class="ptG-s pt-num">RUT ' + esc(rutVisible(v.rut)) + '</div></div>'
                    + '<span class="ptG-s pt-num hora">' + (e != null ? hhmm(e) : '') + (s != null ? ' – ' + hhmm(s) : '') + '</span></div>';
            });
        }
        return h + '</section>';
    }

    function tarjetaError(t, extra) {
        return '<section class="ptG-card ' + (extra || '') + '"><header class="ptG-h"><div><h2>' + t + '</h2><p>No se pudo leer esta sección.</p></div>'
            + '<button type="button" class="ptG-btn sal" data-recargar="1"><i class="bi bi-arrow-clockwise" aria-hidden="true"></i>Reintentar</button></header></section>';
    }

    function pintar() {
        const ps = personas();
        pintarFecha();
        pintarResumen(ps);
        const cont = document.getElementById('porteria-panel');
        if (!cont) return;
        const izq = tarjetaA22(ps), der = tarjetaLlaves() + tarjetaVisitas();
        cont.classList.toggle('solo', !izq || !der);
        cont.innerHTML = izq + (der ? '<div class="ptG-der">' + der + '</div>' : '');
    }

    function repintarFilas() {
        const cont = document.getElementById('ptg-a22-filas');
        if (cont) cont.innerHTML = filasA22(personas());
        document.querySelectorAll('#porteria-panel .ptG-seg [data-f]').forEach(function (b) {
            const on = b.dataset.f === filtro; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on);
        });
    }

    async function recargar() {
        await cargar();
        if (vista === 'panel') pintar(); else { pintarFecha(); pintarResumen(personas()); }
    }

    // ── acciones ───────────────────────────────────────────────
    // Antes de registrar se abre la ventana de siempre «¿Registrar la salida?» con el nombre y la hora (el dueño
    // descartó el doble toque en el mismo botón: confunde). Mientras está abierta no se refresca el panel.
    let preguntando = false;
    async function preguntar(titulo, quien, items, boton) {
        if (typeof uiConfirm !== 'function') return true;
        preguntando = true;
        try { return await uiConfirm(titulo, { quien: quien, items: items, confirmText: boton }); }
        finally { preguntando = false; }
    }

    async function ejecutar(btn, accion) {
        const original = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>Guardando';
        try {
            const r = await accion();
            const msg = r && typeof r === 'object' ? r.texto : r;
            if (msg && r && r.deshacer && window.Avisos && Avisos.conDeshacer) Avisos.conDeshacer(msg, r.deshacer);
            else if (msg) aviso(msg, 'success');
            await recargar();
        } catch (e) {
            aviso(e.message || 'No se pudo registrar', 'danger');
            btn.innerHTML = original; btn.disabled = false;
        }
    }
    function horaAhora() { return hhmm(ahoraMin()); }

    async function alHacerClic(ev) {
        const b = ev.target.closest('button');
        if (!b || !b.closest('#porteria-panel')) return;
        if (b.dataset.f) { filtro = b.dataset.f; repintarFilas(); return; }
        if (b.dataset.ir) { mostrar(b.dataset.ir); return; }
        if (b.dataset.recargar) { recargar(); return; }
        if (b.dataset.a22) {
            const tipo = b.dataset.tipo, p = personas().find(function (x) { return String(x.id) === b.dataset.a22; });
            const quien = p ? p.n : '';
            if (!await preguntar('¿Registrar la ' + tipo.toLowerCase() + '?', quien, ['Artículo 22 · hora ' + horaAhora()], 'Registrar ' + tipo.toLowerCase())) return;
            ejecutar(b, async function () {
                const d = await enviar('/api/articulo22/marcar/', { empleado_id: parseInt(b.dataset.a22, 10) });
                return { texto: (d.tipo_label || tipo) + ' registrada: ' + nombre(d.nombre || quien) + (d.hora ? ' a las ' + String(d.hora).substring(0, 5) : ''), deshacer: d.deshacer };
            });
            return;
        }
        if (b.dataset.visita) {
            const v = ((datos.visitas && datos.visitas.visitantes) || []).find(function (x) { return x.rut === b.dataset.visita; });
            const quien = v && v.nombre ? nombre(v.nombre) : 'RUT ' + rutVisible(b.dataset.visita);
            if (!await preguntar('¿Registrar la salida?', quien, ['Visita · hora ' + horaAhora()], 'Registrar salida')) return;
            ejecutar(b, async function () {
                const d = await enviar('/api/visitas/registrar/', { rut: b.dataset.visita });
                return { texto: (d.tipo_label || 'Salida') + ' registrada: ' + quien + (d.hora ? ' a las ' + String(d.hora).substring(0, 5) : ''), deshacer: d.deshacer };
            });
            return;
        }
        if (b.dataset.entregar) {
            const l = ((datos.llaves && datos.llaves.llaves) || []).find(function (x) { return String(x.id) === b.dataset.entregar; });
            if (!l || typeof LlavesModule === 'undefined') return;
            // La entrega usa la misma ventana de la sección Llaves (elegir a quién y observaciones)
            Promise.resolve(LlavesModule.abrirEntrega(l.id, l.nombre)).then(recargar);
            return;
        }
        if (b.dataset.llave) {
            const l = ((datos.llaves && datos.llaves.llaves) || []).find(function (x) { return String(x.id) === b.dataset.llave; });
            if (!l || !l.entregada_a || typeof LlavesModule === 'undefined') return;
            // La devolución usa la misma ventana de la sección Llaves (con observaciones)
            Promise.resolve(LlavesModule.confirmarDevolucion(l.id, l.nombre, l.entregada_a.id, nombre(l.entregada_a.nombre))).then(recargar);
        }
    }

    // ── navegación entre el panel y cada sección ───────────────
    function mostrar(v) {
        const panel = document.getElementById('porteria-panel'), detalle = document.getElementById('porteria-detalle');
        if (!panel || !detalle) return;
        if (v !== 'panel' && (!VISTAS[v] || !puede(VISTAS[v].permiso))) v = 'panel';
        vista = v;
        document.querySelectorAll('#porteria-resumen .ptG-cel').forEach(function (c) {
            const on = c.dataset.ptVista === v; c.classList.toggle('on', on); c.setAttribute('aria-pressed', on);
        });
        if (v === 'panel') {
            detalle.classList.add('d-none'); panel.classList.remove('d-none');
            pintar(); recargar();
            return;
        }
        panel.classList.add('d-none'); detalle.classList.remove('d-none');
        document.querySelectorAll('#porteriaTabsContent > .tab-pane').forEach(function (p) { p.classList.remove('show', 'active'); });
        const pane = document.getElementById(VISTAS[v].pane);
        if (pane) pane.classList.add('show', 'active');
        VISTAS[v].init();
    }

    function vistaInicial() {
        if (puede('porteria.art22') || puede('porteria.llaves') || puede('porteria.visitas')) return 'panel';
        const orden = ['rondas', 'flota', 'proveedores'];
        for (let i = 0; i < orden.length; i++) if (puede(VISTAS[orden[i]].permiso)) return orden[i];
        return 'panel';
    }

    function init() {
        if (!listo) {
            listo = true;
            document.addEventListener('click', alHacerClic);
            document.addEventListener('input', function (ev) {
                if (ev.target && ev.target.id === 'ptg-buscar') { busqueda = ev.target.value; repintarFilas(); }
            });
            const res = document.getElementById('porteria-resumen');
            if (res) res.addEventListener('click', function (ev) {
                const c = ev.target.closest('.ptG-cel');
                if (!c) return;
                mostrar(c.dataset.ptVista === vista ? 'panel' : c.dataset.ptVista);
            });
            temporizador = setInterval(function () {
                if (!document.querySelector('#page-porteria.active') || document.visibilityState !== 'visible') return;
                pintarFecha();
                if (vista === 'panel' && !preguntando) recargar();
            }, REFRESCO_MS);
        }
        mostrar(vista === 'panel' ? vistaInicial() : vista);
    }

    // Lo deshecho desde cualquier aviso de Portería se refleja en el panel si está a la vista
    window.addEventListener('registro-deshecho', function () {
        const p = document.getElementById('porteria-panel');
        if (p && p.offsetParent !== null) recargar();
    });

    return { init: init, mostrar: mostrar, recargar: recargar };
})();
window.PorteriaPanel = PorteriaPanel;
// Si el archivo llega (carga diferida) con Portería ya abierta, se arma solo
if (document.querySelector('#page-porteria.active')) PorteriaPanel.init();
