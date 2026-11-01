/**
 * Configuración con el diseño B elegido por el dueño (01-11-2026): lista a la izquierda y ficha a la derecha; se cambia ahí
 * mismo, sin ventanas, y se guarda con un solo botón. FichaCfg arma la estructura; cada pestaña le pasa sus datos y cómo
 * dibujar su ficha. Las cadenas se arman con «+» (el minificador del servidor junta las plantillas anidadas).
 */
window.FichaCfg = (function () {
    'use strict';
    const elegido = {};       // clave de pestaña → id del elemento elegido ('nuevo' = ficha de uno nuevo)
    const opciones = {};      // clave de pestaña → opciones con que se montó

    function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
    function puede(p) { return typeof AuthService === 'undefined' || !p || AuthService.hasPermission(p); }

    function montar(cont, o) {
        if (!cont) return;
        opciones[o.clave] = Object.assign({}, o, { cont: cont });
        const items = o.items || [];
        let sel = elegido[o.clave];
        if (sel !== 'nuevo' && !items.some(function (x) { return String(o.id(x)) === String(sel); })) sel = items.length ? String(o.id(items[0])) : null;
        elegido[o.clave] = sel;
        let lista = items.map(function (x) {
            const id = String(o.id(x)), on = id === String(sel);
            return '<button type="button" class="fcB-it' + (on ? ' sel' : '') + (o.apagado && o.apagado(x) ? ' apagado' : '') + '" data-fcb="' + esc(o.clave) + '" data-id="' + esc(id) + '" aria-pressed="' + on + '">'
                + '<span class="n">' + esc(o.etiqueta(x)) + '</span>' + (o.sub ? '<small>' + esc(o.sub(x)) + '</small>' : '') + '</button>';
        }).join('');
        if (!items.length) lista = '<p class="fcB-vacio">' + esc(o.vacio || 'Todavía no hay nada aquí.') + '</p>';
        cont.innerHTML = '<div class="fcB">'
            + '<div class="fcB-h"><div><h2>' + esc(o.titulo) + '</h2>' + (o.descripcion ? '<p>' + esc(o.descripcion) + '</p>' : '') + '</div>'
            + (o.acciones ? '<div class="fcB-acc">' + o.acciones + '</div>' : '') + '</div>'
            + (o.antes || '')
            + '<div class="fcB-md' + (o.soloLista ? ' solo' : '') + '"><nav class="fcB-lista" aria-label="' + esc(o.titulo) + '">' + lista + '</nav>'
            + (o.soloLista ? '' : '<section class="fcB-ficha" aria-live="polite"></section>') + '</div></div>';
        pintarFicha(o.clave);
    }

    function pintarFicha(clave) {
        const o = opciones[clave];
        if (!o || o.soloLista) return;
        const panel = o.cont.querySelector('.fcB-ficha');
        if (!panel) return;
        const sel = elegido[clave];
        const item = sel === 'nuevo' ? null : (o.items || []).find(function (x) { return String(o.id(x)) === String(sel); });
        if (sel !== 'nuevo' && !item) { panel.innerHTML = '<p class="fcB-vacio">' + esc(o.vacioFicha || 'Elija uno de la lista.') + '</p>'; return; }
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
    function cabeza(titulo, sub) { return '<div class="fcB-fh"><h3>' + esc(titulo) + '</h3>' + (sub ? '<p>' + esc(sub) + '</p>' : '') + '</div>'; }
    function seccion(titulo) { return '<div class="fcB-sec">' + esc(titulo) + '</div>'; }
    function mas(titulo, contenido) { return '<details class="fcB-mas"><summary>' + esc(titulo) + '</summary>' + contenido + '</details>'; }

    async function trabajando(btn, accion) {
        const original = btn ? btn.innerHTML : '';
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>Guardando'; }
        try { return await accion(); }
        finally { if (btn && btn.isConnected) { btn.disabled = false; btn.innerHTML = original; } }
    }

    return { montar: montar, elegir: elegir, nuevo: nuevo, recordar: recordar, pintarFicha: pintarFicha, esc: esc, puede: puede,
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
