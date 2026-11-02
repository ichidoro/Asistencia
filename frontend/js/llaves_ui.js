/**
 * Llaves — diseño B elegido por el dueño (02-11-2026): las llaves a la izquierda con su estado y, a la derecha, la llave
 * elegida: dónde está, quién la tuvo, quién la pide más y su botón para entregarla o recibirla. El nombre y la
 * ubicación se cambian en la misma ficha. Se arma con FichaCfg (config_ficha.js). La entrega y la devolución usan la
 * misma ventana desde el panel y desde aquí (abrirEntrega, confirmarDevolucion).
 * Las cadenas se arman con «+» (el minificador del servidor junta las plantillas anidadas).
 */
const LlavesModule = (function () {
    'use strict';
    let datos = null, error = null;
    const movs = {};   // id de llave → { t: hora de lectura, regs: movimientos (del más antiguo al más nuevo), total }

    // ── utilidades ─────────────────────────────────────────────
    function pad(n) { return (n < 10 ? '0' : '') + n; }
    function hoyISO() { const d = new Date(); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
    function dmy(f) { return f ? String(f).slice(0, 10).split('-').reverse().join('-') : ''; }
    function esc(s) { return window.FichaCfg ? FichaCfg.esc(s) : String(s == null ? '' : s); }
    function nombre(s) { return window.nombrePersona ? window.nombrePersona(String(s || '').replace(/\bNone\b/g, '')) : String(s || '').toUpperCase(); }
    function aviso(msg, tipo) { if (typeof showToast === 'function') showToast(msg, tipo || 'success'); }
    function token() { return localStorage.getItem('access_token') || localStorage.getItem('auth_token'); }
    function cabeceras(json) { const h = { 'Authorization': 'Bearer ' + token() }; if (json) h['Content-Type'] = 'application/json'; return h; }
    async function pedir(url, metodo, cuerpo) {
        const r = await fetch(url, { method: metodo || 'GET', headers: cabeceras(!!cuerpo), body: cuerpo ? JSON.stringify(cuerpo) : undefined });
        const d = await r.json().catch(function () { return {}; });
        if (!r.ok) throw new Error(d.detail || 'No se pudo completar la operación.');
        return d;
    }
    function cont() { return document.getElementById('llaves-container'); }
    function fechaHora(f, h) { return new Date(String(f).slice(0, 10) + 'T' + String(h || '00:00:00').slice(0, 8)); }
    function duracion(min) {
        min = Math.max(0, Math.round(min));
        const d = Math.floor(min / 1440), h = Math.floor((min % 1440) / 60), m = min % 60;
        return (d ? d + (d === 1 ? ' día ' : ' días ') : '') + h + 'h ' + pad(m) + 'm';
    }
    function cuando(f, h) {
        const hoy = hoyISO();
        return (String(f).slice(0, 10) === hoy ? 'hoy' : dmy(f)) + ' a las ' + String(h || '').slice(0, 5);
    }

    // ── pintar ─────────────────────────────────────────────────
    function pintar() {
        const c = cont();
        if (!c || !window.FichaCfg) return;
        if (error && !datos) {
            c.innerHTML = '<div class="fcB"><p class="fcB-vacio">' + esc(error) + ' <button type="button" class="fcB-btn" data-ll-recargar>Reintentar</button></p></div>';
            return;
        }
        const llaves = (datos && datos.llaves) || [];
        FichaCfg.montar(c, {
            clave: 'llaves',
            titulo: 'Llaves',
            descripcion: (datos ? llaves.length + (llaves.length === 1 ? ' llave' : ' llaves') + ': ' + (datos.fuera || 0) + ' entregada' + (datos.fuera === 1 ? '' : 's') + ' y ' + (datos.disponibles || 0) + ' en el tablero. ' : '')
                + 'Elija una llave para ver quién la tuvo y para entregarla o recibirla.',
            acciones: '<button type="button" class="fcB-btn ent" data-ll-nueva><i class="bi bi-plus-lg" aria-hidden="true"></i>Nueva llave</button>',
            buscar: 'Buscar llave',
            items: llaves,
            id: function (l) { return l.id; },
            etiqueta: function (l) { return l.nombre; },
            detalle: function (l) { return l.ubicacion || ''; },
            estado: function (l) { return l.estado === 'DISPONIBLE' ? { t: 'En el tablero', tono: 'si' } : { t: 'Entregada', tono: 'fuera' }; },
            sub: function (l) {
                if (l.estado === 'DISPONIBLE' || !l.entregada_hora) return '';
                const fh = String(l.entregada_hora);
                return 'desde ' + (fh.slice(0, 10) === hoyISO() ? '' : dmy(fh).slice(0, 5) + ' ') + fh.slice(11, 16);
            },
            vacio: datos ? 'Todavía no hay llaves. Cree la primera con «Nueva llave».' : 'Cargando…',
            ficha: ficha
        });
    }

    function campos(l) {
        const F = FichaCfg;
        return F.campo('Nombre', F.texto('ll-nombre', l ? l.nombre : '', ' maxlength="80" placeholder="Ej.: Bodega Tradicional"'), 'Como la conocen en portería.', 'll-nombre')
            + F.campo('Ubicación', F.texto('ll-ubicacion', l ? l.ubicacion : '', ' maxlength="120" placeholder="Ej.: Galpón Tradicional"'), 'Qué abre o dónde está la puerta.', 'll-ubicacion');
    }

    function ficha(l, panel) {
        const F = FichaCfg;
        if (!l) {
            panel.innerHTML = F.cabeza('Nueva llave', 'Queda en el tablero, lista para entregarse.') + campos(null)
                + F.pie('<button type="button" class="fcB-btn" data-ll-cancelar>Cancelar</button>',
                    '<button type="button" class="fcB-btn pri" data-ll-crear><i class="bi bi-check-lg" aria-hidden="true"></i>Crear llave</button>');
            const i = panel.querySelector('#ll-nombre'); if (i) i.focus();
            return;
        }
        const fuera = l.estado !== 'DISPONIBLE';
        const accion = fuera
            ? (l.entregada_a ? '<button type="button" class="fcB-btn ok" data-ll-recibir="' + l.id + '"><i class="bi bi-box-arrow-in-left" aria-hidden="true"></i>Recibir llave</button>' : '')
            : '<button type="button" class="fcB-btn pri" data-ll-entregar="' + l.id + '"><i class="bi bi-box-arrow-right" aria-hidden="true"></i>Entregar llave</button>';
        let h = F.cabeza(l.nombre, l.ubicacion || '', accion);
        if (fuera && l.entregada_a) {
            const fh = String(l.entregada_hora || ''), desde = fechaHora(fh.slice(0, 10), fh.slice(11));
            h += '<div class="ptB-aviso"><i class="bi bi-key-fill" aria-hidden="true"></i><div><b>Entregada a ' + esc(nombre(l.entregada_a.nombre)) + '</b>'
                + '<span>Desde ' + esc(cuando(fh.slice(0, 10), fh.slice(11))) + (isNaN(desde) ? '' : ' · hace ' + duracion((Date.now() - desde) / 60000)) + '</span></div></div>';
        }
        h += '<div class="ptB-cifras" id="ll-cifras"><div><small>Estado</small><b>' + (fuera ? 'Entregada' : 'En el tablero') + '</b></div>'
            + '<div><small>' + (fuera ? 'Salió' : 'Volvió') + '</small><b class="num" id="ll-ultima">—</b></div>'
            + '<div><small>Entregas registradas</small><b class="num" id="ll-cuenta">—</b></div></div>'
            + F.seccion('Últimas salidas') + '<div class="ptB-movs" id="ll-salidas"><p class="fcB-vacio">Cargando los movimientos…</p></div>'
            + F.seccion('Quién la pide más') + '<div class="ptB-quien" id="ll-quien"></div>'
            + F.mas('Cambiar nombre o ubicación', campos(l)
                + F.pie('<button type="button" class="fcB-btn borra" data-ll-eliminar="' + l.id + '"><i class="bi bi-trash3" aria-hidden="true"></i>Eliminar llave</button>',
                    '<button type="button" class="fcB-btn pri" data-ll-guardar="' + l.id + '"><i class="bi bi-check-lg" aria-hidden="true"></i>Guardar cambios</button>'));
        panel.innerHTML = h;
        pintarMovimientos(l);
    }

    async function pintarMovimientos(l) {
        let m = movs[l.id];
        try {
            if (!m || Date.now() - m.t > 2 * 60000) {
                const d = await pedir('/api/llaves/historial/?llave_id=' + l.id + '&page=1&page_size=100');
                m = movs[l.id] = { t: Date.now(), regs: (d.registros || []).slice().reverse(), total: d.total || 0 };
            }
        } catch (e) {
            const b = document.getElementById('ll-salidas');
            if (b) b.innerHTML = '<p class="fcB-vacio">' + esc(e.message) + '</p>';
            return;
        }
        if (FichaCfg.elegidoDe('llaves') !== String(l.id)) return;
        const regs = m.regs.slice().sort(function (a, b) { return fechaHora(a.fecha, a.hora) - fechaHora(b.fecha, b.hora); });
        const salidas = [];
        let abierta = null;
        regs.forEach(function (r) {
            if (r.tipo === 'ENTREGA') { if (abierta) salidas.push({ e: abierta, d: null }); abierta = r; }
            else if (abierta) { salidas.push({ e: abierta, d: r }); abierta = null; }
        });
        if (abierta) salidas.push({ e: abierta, d: null, ahora: true });
        const entregas = regs.filter(function (r) { return r.tipo === 'ENTREGA'; }).length;
        const ult = regs[regs.length - 1];
        const ue = document.getElementById('ll-ultima'), uc = document.getElementById('ll-cuenta');
        if (ue) ue.textContent = ult ? (String(ult.fecha) === hoyISO() ? 'Hoy ' : dmy(ult.fecha) + ' ') + String(ult.hora).slice(0, 5) : 'Sin movimientos';
        if (uc) uc.textContent = entregas + (m.total > regs.length ? '+' : '');
        const box = document.getElementById('ll-salidas');
        if (box) {
            const ultimas = salidas.slice(-8).reverse();
            box.innerHTML = ultimas.length ? ultimas.map(function (s) {
                const ini = fechaHora(s.e.fecha, s.e.hora), fin = s.d ? fechaHora(s.d.fecha, s.d.hora) : null;
                const mismoDia = s.d && String(s.d.fecha) === String(s.e.fecha);
                const tramo = s.d
                    ? (mismoDia ? dmy(s.e.fecha) + ' · ' + String(s.e.hora).slice(0, 5) + ' a ' + String(s.d.hora).slice(0, 5)
                                : dmy(s.e.fecha).slice(0, 5) + ' ' + String(s.e.hora).slice(0, 5) + ' a ' + dmy(s.d.fecha).slice(0, 5) + ' ' + String(s.d.hora).slice(0, 5))
                    : dmy(s.e.fecha) + ' · desde las ' + String(s.e.hora).slice(0, 5);
                const t = s.d ? duracion((fin - ini) / 60000) + ' fuera' : (s.ahora ? 'Sigue entregada' : 'Sin DEVOLUCIÓN registrada');
                const obs = [s.e.observaciones, s.d && s.d.observaciones].filter(Boolean).join(' · ');
                return '<div class="ptB-mv"><span class="num">' + esc(tramo) + '</span><span>' + esc(nombre(s.e.empleado)) + (obs ? '<small>' + esc(obs) + '</small>' : '') + '</span>'
                    + '<span class="num' + ((!s.d || !mismoDia) ? ' ojo' : '') + '">' + esc(t) + '</span></div>';
            }).join('') : '<p class="fcB-nota">Esta llave todavía no se ha entregado.</p>';
        }
        const q = document.getElementById('ll-quien');
        if (q) {
            const cuenta = {};
            regs.forEach(function (r) { if (r.tipo === 'ENTREGA') { const n = nombre(r.empleado); cuenta[n] = (cuenta[n] || 0) + 1; } });
            const top = Object.keys(cuenta).sort(function (a, b) { return cuenta[b] - cuenta[a] || a.localeCompare(b, 'es'); }).slice(0, 3);
            q.innerHTML = top.length ? top.map(function (n) { return '<div class="ptB-qd"><span>' + esc(n) + '</span><span class="num">' + cuenta[n] + (cuenta[n] === 1 ? ' vez' : ' veces') + '</span></div>'; }).join('')
                : '<p class="fcB-nota">Sin entregas registradas.</p>';
        }
    }

    // ── datos y acciones ───────────────────────────────────────
    async function recargar() {
        try { datos = await pedir('/api/llaves/estado/'); error = null; }
        catch (e) { error = e.message; if (datos) aviso(e.message, 'danger'); }
        pintar();
    }
    function tras(llaveId) { delete movs[llaveId]; if (cont() && cont().offsetParent !== null) return recargar(); }

    async function abrirEntrega(llaveId, llaveNombre) {
        let autorizados;
        try { autorizados = await pedir('/api/llaves/autorizados/'); }
        catch (e) { aviso(e.message, 'danger'); return; }
        if (!autorizados.length) { aviso('No hay personas autorizadas para recibir llaves en sus áreas. Se autorizan en la ficha de cada persona.', 'warning'); return; }
        const ops = autorizados.map(function (e) { return { id: e.id, n: nombre(e.nombre), a: e.area || '' }; })
            .sort(function (a, b) { return a.n.localeCompare(b.n, 'es'); })
            .map(function (e) { return '<option value="' + e.id + '">' + esc(e.n) + (e.a ? ' · ' + esc(e.a) : '') + '</option>'; }).join('');
        const r = await Swal.fire({
            title: 'Entregar llave',
            html: '<div class="av-quien">' + esc(llaveNombre) + '</div><div class="ptB-sw">'
                + '<label for="swal-empleado">Persona que la recibe</label><select id="swal-empleado" class="form-select">' + ops + '</select>'
                + '<label for="swal-obs">Observaciones</label><input id="swal-obs" class="form-control" placeholder="Opcional"></div>',
            showCancelButton: true, reverseButtons: true, focusConfirm: false,
            confirmButtonText: 'Entregar llave', cancelButtonText: 'Cancelar',
            customClass: { confirmButton: 'av-btn av-btn-pri' },
            preConfirm: function () { return { empleado_id: parseInt(document.getElementById('swal-empleado').value, 10), observaciones: document.getElementById('swal-obs').value.trim() }; }
        });
        if (!r.isConfirmed || !r.value) return;
        try {
            const d = await pedir('/api/llaves/registrar/', 'POST', { llave_id: llaveId, empleado_id: r.value.empleado_id, tipo: 'ENTREGA', observaciones: r.value.observaciones });
            aviso(d.message || 'ENTREGA registrada.');
        } catch (e) { aviso(e.message, 'danger'); }
        await tras(llaveId);
    }

    async function confirmarDevolucion(llaveId, llaveNombre, empleadoId, empleadoNombre) {
        const r = await Swal.fire({
            title: '¿Recibir la llave?',
            html: '<div class="av-quien">' + esc(llaveNombre) + '</div><div class="ptB-sw"><p>La devuelve ' + esc(nombre(empleadoNombre)) + '.</p>'
                + '<label for="swal-obs-dev">Observaciones</label><input id="swal-obs-dev" class="form-control" placeholder="Opcional"></div>',
            showCancelButton: true, reverseButtons: true, focusConfirm: false,
            confirmButtonText: 'Recibir llave', cancelButtonText: 'Cancelar',
            customClass: { confirmButton: 'av-btn av-btn-pri' },
            preConfirm: function () { return { observaciones: document.getElementById('swal-obs-dev').value.trim() }; }
        });
        if (!r.isConfirmed) return;
        try {
            const d = await pedir('/api/llaves/registrar/', 'POST', { llave_id: llaveId, empleado_id: empleadoId, tipo: 'DEVOLUCION', observaciones: (r.value && r.value.observaciones) || '' });
            aviso(d.message || 'DEVOLUCIÓN registrada.');
        } catch (e) { aviso(e.message, 'danger'); }
        await tras(llaveId);
    }

    function leerCampos(raiz) {
        const n = raiz.querySelector('#ll-nombre'), u = raiz.querySelector('#ll-ubicacion');
        const v = { nombre: n ? n.value.trim() : '', ubicacion: u ? u.value.trim() : '' };
        if (!v.nombre || !v.ubicacion) { aviso('Falta el nombre o la ubicación de la llave.', 'warning'); (v.nombre ? u : n).focus(); return null; }
        return v;
    }

    let oyentes = false;
    function escuchar() {
        if (oyentes) return;
        oyentes = true;
        document.addEventListener('click', async function (ev) {
            const c = cont();
            if (!c || !c.contains(ev.target)) return;
            const b = ev.target.closest('button');
            if (!b) return;
            const l = function (id) { return ((datos && datos.llaves) || []).find(function (x) { return String(x.id) === String(id); }); };
            if (b.hasAttribute('data-ll-recargar')) { recargar(); return; }
            if (b.hasAttribute('data-ll-nueva')) { FichaCfg.nuevo('llaves'); return; }
            if (b.hasAttribute('data-ll-cancelar')) { const k = (datos && datos.llaves && datos.llaves[0]); if (k) FichaCfg.elegir('llaves', String(k.id)); return; }
            if (b.dataset.llEntregar) { const k = l(b.dataset.llEntregar); if (k) abrirEntrega(k.id, k.nombre); return; }
            if (b.dataset.llRecibir) { const k = l(b.dataset.llRecibir); if (k && k.entregada_a) confirmarDevolucion(k.id, k.nombre, k.entregada_a.id, k.entregada_a.nombre); return; }
            if (b.hasAttribute('data-ll-crear')) {
                const v = leerCampos(c.querySelector('.fcB-ficha'));
                if (!v) return;
                await FichaCfg.trabajando(b, async function () {
                    try {
                        await pedir('/api/llaves/maestro/', 'POST', v);
                        aviso('Llave creada: ' + v.nombre + '.');
                        await recargar();
                        const k = ((datos && datos.llaves) || []).filter(function (x) { return x.nombre === v.nombre; }).pop();
                        if (k) FichaCfg.elegir('llaves', String(k.id));
                    } catch (e) { aviso(e.message, 'danger'); }
                });
                return;
            }
            if (b.dataset.llGuardar) {
                const v = leerCampos(c.querySelector('.fcB-ficha'));
                if (!v) return;
                await FichaCfg.trabajando(b, async function () {
                    try { await pedir('/api/llaves/maestro/' + b.dataset.llGuardar + '/', 'PUT', v); aviso('Llave actualizada.'); await recargar(); }
                    catch (e) { aviso(e.message, 'danger'); }
                });
                return;
            }
            if (b.dataset.llEliminar) {
                const k = l(b.dataset.llEliminar);
                if (!k) return;
                if (k.estado !== 'DISPONIBLE') { aviso('La llave está entregada: recíbala antes de eliminarla.', 'warning'); return; }
                const si = typeof uiConfirm === 'function' ? await uiConfirm('¿Eliminar la llave?', { quien: k.nombre, items: ['Deja de aparecer en el tablero y en el panel', 'Su historial de entregas se conserva'], confirmText: 'Eliminar llave', danger: true }) : true;
                if (!si) return;
                try { await pedir('/api/llaves/maestro/' + k.id + '/', 'DELETE'); aviso('Llave eliminada: ' + k.nombre + '.'); await recargar(); }
                catch (e) { aviso(e.message, 'danger'); }
            }
        });
    }

    async function initTab() {
        escuchar();
        pintar();
        await recargar();
    }

    return { initTab: initTab, recargar: recargar, abrirEntrega: abrirEntrega, confirmarDevolucion: confirmarDevolucion };
})();
