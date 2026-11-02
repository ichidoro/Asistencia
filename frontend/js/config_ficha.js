/**
 * Configuración con el diseño B elegido por el dueño (01-11-2026): lista a la izquierda y ficha a la derecha; se cambia ahí
 * mismo, sin ventanas, y se guarda con un solo botón. FichaCfg arma la estructura; cada pestaña le pasa sus datos y cómo
 * dibujar su ficha. Las cadenas se arman con «+» (el minificador del servidor junta las plantillas anidadas).
 */
window.FichaCfg = (function () {
    'use strict';
    const elegido = {};       // clave de pestaña → id del elemento elegido ('nuevo' = ficha de uno nuevo)
    const opciones = {};      // clave de pestaña → opciones con que se montó
    const buscado = {};       // clave de pestaña → texto escrito en el buscador de la lista

    function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
    function puede(p) { return typeof AuthService === 'undefined' || !p || AuthService.hasPermission(p); }
    function plano(s) { return String(s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, ''); }

    // Opciones extra (Portería, 02-11-2026): detalle(x) = segunda línea bajo el nombre; estado(x) = { t, tono: 'si' | 'fuera' | '' }
    // dibuja un punto de color a la derecha (sub va debajo); buscar = texto del buscador sobre la lista.
    function montar(cont, o) {
        if (!cont) return;
        const conFoco = !!(document.activeElement && cont.contains(document.activeElement) && document.activeElement.matches('.fcB-buscar input'));
        opciones[o.clave] = Object.assign({}, o, { cont: cont });
        const items = o.items || [];
        let sel = elegido[o.clave];
        if (sel !== 'nuevo' && !items.some(function (x) { return String(o.id(x)) === String(sel); })) sel = items.length ? String(o.id(items[0])) : null;
        elegido[o.clave] = sel;
        let lista = items.map(function (x) {
            const id = String(o.id(x)), on = id === String(sel);
            const det = o.detalle ? o.detalle(x) : '', est = o.estado ? o.estado(x) : null, sub = o.sub ? o.sub(x) : '';
            const der = est
                ? '<small class="fcB-r"><span class="fcB-est ' + esc(est.tono || '') + '"><i aria-hidden="true"></i>' + esc(est.t) + '</span>' + (sub ? '<span>' + esc(sub) + '</span>' : '') + '</small>'
                : (o.sub ? '<small>' + esc(sub) + '</small>' : '');
            return '<button type="button" class="fcB-it' + (on ? ' sel' : '') + (o.apagado && o.apagado(x) ? ' apagado' : '') + '" data-fcb="' + esc(o.clave) + '" data-id="' + esc(id) + '" aria-pressed="' + on + '"'
                + (o.buscar ? ' data-texto="' + esc(plano(o.etiqueta(x) + ' ' + det)) + '"' : '') + '>'
                + '<span class="n">' + esc(o.etiqueta(x)) + (det ? '<small class="d">' + esc(det) + '</small>' : '') + '</span>' + der + '</button>';
        }).join('');
        if (!items.length) lista = '<p class="fcB-vacio">' + esc(o.vacio || 'Todavía no hay nada aquí.') + '</p>';
        const buscador = (o.buscar && items.length)
            ? '<div class="fcB-buscar"><i class="bi bi-search" aria-hidden="true"></i><input type="search" data-fcb-buscar="' + esc(o.clave) + '" placeholder="' + esc(o.buscar) + '" aria-label="' + esc(o.buscar) + '" value="' + esc(buscado[o.clave] || '') + '" autocomplete="off"></div>'
              + '<p class="fcB-vacio d-none" data-fcb-nada>No hay coincidencias.</p>'
            : '';
        const cabecera = (o.titulo || o.acciones)
            ? '<div class="fcB-h"><div>' + (o.titulo ? '<h2>' + esc(o.titulo) + '</h2>' : '') + (o.descripcion ? '<p>' + esc(o.descripcion) + '</p>' : '') + '</div>'
              + (o.acciones ? '<div class="fcB-acc">' + o.acciones + '</div>' : '') + '</div>'
            : '';
        // Con la lista vacía no se dibuja la ficha: el aviso de la lista basta (no se repite)
        const solo = o.soloLista || (!items.length && sel !== 'nuevo');
        cont.innerHTML = '<div class="fcB">' + cabecera
            + (o.antes || '')
            + '<div class="fcB-md' + (solo ? ' solo' : '') + '"><nav class="fcB-lista" aria-label="' + esc(o.titulo || o.buscar || 'Lista') + '">' + buscador + lista + '</nav>'
            + (solo ? '' : '<section class="fcB-ficha" aria-live="polite"></section>') + '</div></div>';
        if (o.buscar) filtrar(o.clave);
        if (conFoco) { const i = cont.querySelector('.fcB-buscar input'); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }
        pintarFicha(o.clave);
    }

    function filtrar(clave) {
        const o = opciones[clave];
        if (!o) return;
        const q = plano(buscado[clave] || '').trim();
        let visibles = 0;
        o.cont.querySelectorAll('.fcB-it[data-fcb="' + clave + '"]').forEach(function (b) {
            const ve = !q || (b.dataset.texto || '').indexOf(q) !== -1;
            b.classList.toggle('d-none', !ve);
            if (ve) visibles++;
        });
        const nada = o.cont.querySelector('[data-fcb-nada]');
        if (nada) nada.classList.toggle('d-none', visibles > 0);
    }

    function pintarFicha(clave) {
        const o = opciones[clave];
        if (!o || o.soloLista) return;
        const panel = o.cont.querySelector('.fcB-ficha');
        if (!panel) return;
        const sel = elegido[clave];
        const item = sel === 'nuevo' ? null : (o.items || []).find(function (x) { return String(o.id(x)) === String(sel); });
        if (sel !== 'nuevo' && !item) { panel.innerHTML = '<p class="fcB-vacio">' + esc(o.vacioFicha || ((o.items || []).length ? 'Elija uno de la lista.' : (o.vacio || 'Todavía no hay nada aquí.'))) + '</p>'; return; }
        o.ficha(item || null, panel);
    }

    function elegir(clave, id) {
        elegido[clave] = id;
        const o = opciones[clave];
        if (!o) return;
        o.cont.querySelectorAll('.fcB-it').forEach(function (b) { const on = b.dataset.id === String(id); b.classList.toggle('sel', on); b.setAttribute('aria-pressed', on); });
        pintarFicha(clave);
        // En el celular la ficha queda debajo de la lista: se lleva a la vista
        const panel = o.cont.querySelector('.fcB-ficha');
        if (panel && window.innerWidth < 992) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    function nuevo(clave) { elegir(clave, 'nuevo'); }
    function recordar(clave, id) { elegido[clave] = String(id); }

    document.addEventListener('click', function (ev) {
        const b = ev.target.closest('.fcB-it');
        if (b && b.dataset.fcb) elegir(b.dataset.fcb, b.dataset.id);
        const s = ev.target.closest('.fcB-seg button');
        if (s && !s.disabled) {
            s.parentElement.querySelectorAll('button').forEach(function (x) { const on = x === s; x.classList.toggle('on', on); x.setAttribute('aria-pressed', on); });
        }
    });
    document.addEventListener('input', function (ev) {
        const i = ev.target && ev.target.matches && ev.target.matches('[data-fcb-buscar]') ? ev.target : null;
        if (!i) return;
        buscado[i.dataset.fcbBuscar] = i.value;
        filtrar(i.dataset.fcbBuscar);
    });

    // ── piezas de una ficha ──────────────────────────────────
    function campo(etiqueta, control, ayuda, para) {
        return '<div class="fcB-campo"><div class="fcB-et">' + (para ? '<label for="' + esc(para) + '">' : '<span>') + esc(etiqueta) + (para ? '</label>' : '</span>')
            + (ayuda ? '<p>' + esc(ayuda) + '</p>' : '') + '</div><div class="fcB-ctl">' + control + '</div></div>';
    }
    function texto(id, valor, attrs) { return '<input type="text" class="fcB-inp" id="' + esc(id) + '" value="' + esc(valor) + '"' + (attrs || '') + '>'; }
    function numero(id, valor, attrs) { return '<input type="number" class="fcB-inp num" id="' + esc(id) + '" value="' + esc(valor == null ? '' : valor) + '"' + (attrs || '') + '>'; }
    function area(id, valor) { return '<textarea class="fcB-inp" rows="2" id="' + esc(id) + '">' + esc(valor) + '</textarea>'; }
    // ops: [[valor, texto], ...]
    function seg(id, ops, valor, deshabilitado) {
        return '<div class="fcB-seg" id="' + esc(id) + '" role="group">' + ops.map(function (op) {
            const on = String(op[0]) === String(valor);
            return '<button type="button" data-v="' + esc(op[0]) + '" class="' + (on ? 'on' : '') + '" aria-pressed="' + on + '"' + (deshabilitado ? ' disabled' : '') + '>' + esc(op[1]) + '</button>';
        }).join('') + '</div>';
    }
    function lista(id, ops, valor) {
        return '<select class="fcB-inp" id="' + esc(id) + '">' + ops.map(function (op) {
            return '<option value="' + esc(op[0]) + '"' + (String(op[0]) === String(valor) ? ' selected' : '') + '>' + esc(op[1]) + '</option>';
        }).join('') + '</select>';
    }
    function interruptor(id, activo, texto) {
        return '<label class="fcB-sw"><input type="checkbox" id="' + esc(id) + '"' + (activo ? ' checked' : '') + '><span aria-hidden="true"></span>' + esc(texto || '') + '</label>';
    }
    function leerSeg(raiz, id) { const b = raiz.querySelector('#' + id + ' button.on'); return b ? b.dataset.v : null; }
    function pie(izq, der) { return '<div class="fcB-pie"><div>' + (izq || '') + '</div><div class="fcB-pie-d">' + (der || '') + '</div></div>'; }
    function cabeza(titulo, sub, accion) {
        const t = '<h3>' + esc(titulo) + '</h3>' + (sub ? '<p>' + esc(sub) + '</p>' : '');
        return accion ? '<div class="fcB-fh con"><div>' + t + '</div><div class="fcB-fh-a">' + accion + '</div></div>' : '<div class="fcB-fh">' + t + '</div>';
    }
    function seccion(titulo) { return '<div class="fcB-sec">' + esc(titulo) + '</div>'; }
    function mas(titulo, contenido) { return '<details class="fcB-mas"><summary>' + esc(titulo) + '</summary>' + contenido + '</details>'; }

    async function trabajando(btn, accion) {
        const original = btn ? btn.innerHTML : '';
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>Guardando'; }
        try { return await accion(); }
        finally { if (btn && btn.isConnected) { btn.disabled = false; btn.innerHTML = original; } }
    }

    function elegidoDe(clave) { return elegido[clave]; }

    return { montar: montar, elegir: elegir, nuevo: nuevo, recordar: recordar, pintarFicha: pintarFicha, elegidoDe: elegidoDe, esc: esc, puede: puede,
             campo: campo, texto: texto, numero: numero, area: area, seg: seg, lista: lista, interruptor: interruptor, leerSeg: leerSeg,
             pie: pie, cabeza: cabeza, seccion: seccion, mas: mas, trabajando: trabajando };
})();

// ── Sistema: grupos a la izquierda y un solo «Guardar cambios» (los campos guardan con saveAjusteSistema) ──
(function () {
    'use strict';
    function raiz() { return document.getElementById('sistema-fcb'); }
    function campos(r) { return Array.prototype.slice.call(r.querySelectorAll('[data-clave]')); }
    function cambiados(r) { return campos(r).filter(function (i) { return i.dataset.original !== undefined && i.value.trim() !== i.dataset.original; }); }
    function contar() {
        const r = raiz(), p = document.getElementById('sistema-cambios');
        if (!r || !p) return;
        const n = cambiados(r).length;
        p.textContent = n ? (n === 1 ? '1 cambio sin guardar.' : n + ' cambios sin guardar.') : 'Sin cambios.';
    }
    window.FichaCfg.sistemaOriginales = function () {
        const r = raiz();
        if (!r) return;
        campos(r).forEach(function (i) { i.dataset.original = i.value.trim(); });
        contar();
    };
    window.FichaCfg.sistemaContar = contar;
    document.addEventListener('click', async function (ev) {
        const r = raiz();
        if (!r || !r.contains(ev.target)) return;
        const g = ev.target.closest('[data-grupo-sis]');
        if (g) {
            r.querySelectorAll('[data-grupo-sis]').forEach(function (b) { const on = b === g; b.classList.toggle('sel', on); b.setAttribute('aria-pressed', on); });
            r.querySelectorAll('[data-grupo-sis-panel]').forEach(function (p) { p.classList.toggle('d-none', p.dataset.grupoSisPanel !== g.dataset.grupoSis); });
            return;
        }
        if (ev.target.closest('#sistema-descartar')) {
            campos(r).forEach(function (i) { if (i.dataset.original !== undefined) i.value = i.dataset.original; });
            contar();
            return;
        }
        const gb = ev.target.closest('#sistema-guardar');
        if (gb) {
            const lista = cambiados(r);
            if (!lista.length) { if (typeof showToast === 'function') showToast('No hay cambios que guardar.', 'info'); return; }
            await window.FichaCfg.trabajando(gb, async function () {
                for (let k = 0; k < lista.length; k++) await window.saveAjusteSistema(lista[k].dataset.clave, lista[k].id);
            });
            contar();
        }
    });
    document.addEventListener('input', function (ev) { if (ev.target && ev.target.closest && ev.target.closest('#sistema-fcb')) contar(); });
})();
