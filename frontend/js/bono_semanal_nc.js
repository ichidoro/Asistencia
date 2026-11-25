/**
 * Piezas de la ventana del Fill Rate (25-11-2026): lista desplegable que se ordena sola (con búsqueda y teclado) y la
 * tarjeta de la nota de crédito, que busca la nota en Nexacol por su número y muestra el detalle completo de sus
 * productos. Las usa bono_semanal_ui.js (window.mxBsUi).
 */
(function () {
    'use strict';

    const esc = s => window.Ayuda.esc(s);
    const pesos = n => '$' + Math.round(Number(n || 0)).toLocaleString('es-CL');
    const num = (n, d) => Number(n || 0).toLocaleString('es-CL', { maximumFractionDigits: d == null ? 2 : d });
    const ddmmyyyy = f => (f && window.formatFechaDDMMYYYY) ? window.formatFechaDDMMYYYY(String(f).slice(0, 10)) : (f || '');
    const authHead = () => ({ 'Authorization': `Bearer ${localStorage.getItem('access_token')}`, 'Content-Type': 'application/json' });
    const sinTilde = t => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const TONOS = { ok: 'bs-tag ok', mal: 'bs-tag mal', warn: 'bs-tag warn', neutro: 'bs-tag' };
    const tag = (t, tono) => '<span class="' + (TONOS[tono] || TONOS.neutro) + '">' + esc(t) + '</span>';
    const reducido = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // ── Lista flotante ──────────────────────────────────────────────────────────────────────────────────────────
    // Se cuelga del contenedor de la ventana (no del cuadro, que recorta lo que sobresale) y se ubica junto a su ancla,
    // arriba o abajo según el espacio. El teclado lo maneja quien la abre (mover / elegir / cerrar).
    let abierta = null;
    function cerrarLista() { if (abierta) abierta.cerrar(); }
    document.addEventListener('pointerdown', e => { if (abierta && !abierta.el.contains(e.target) && !abierta.ancla.contains(e.target)) cerrarLista(); }, true);
    window.addEventListener('resize', cerrarLista);
    document.addEventListener('scroll', e => { if (abierta && Date.now() - abierta.t0 > 350 && !abierta.el.contains(e.target)) cerrarLista(); }, true);

    function abrirLista(ancla, { onElegir, onCerrar, claseExtra }) {
        cerrarLista();
        const el = document.createElement('div');
        el.className = 'bs-lista' + (claseExtra ? ' ' + claseExtra : '');
        el.id = 'bs-lista-' + Math.random().toString(36).slice(2, 8);
        const cuerpo = document.createElement('div');   // lo único que se repinta: el buscador de arriba (si hay) se conserva
        cuerpo.className = 'bs-lista-ops';
        cuerpo.setAttribute('role', 'listbox');
        el.appendChild(cuerpo);
        const padre = (window.Swal && window.Swal.getContainer && window.Swal.getContainer()) || document.body;
        padre.appendChild(el);
        let items = [], idx = -1;
        const ubicar = () => {
            const r = ancla.getBoundingClientRect();
            const alto = Math.min(el.scrollHeight, 288);
            const abajo = window.innerHeight - r.bottom - 12, arriba = r.top - 12;
            const sube = abajo < Math.min(alto, 200) && arriba > abajo;
            el.style.left = Math.max(8, Math.min(r.left, window.innerWidth - r.width - 8)) + 'px';
            el.style.width = r.width + 'px';
            el.style.maxHeight = Math.max(140, Math.min(288, sube ? arriba : abajo)) + 'px';
            el.style.top = sube ? 'auto' : (r.bottom + 6) + 'px';
            el.style.bottom = sube ? (window.innerHeight - r.top + 6) + 'px' : 'auto';
            el.dataset.sube = sube ? '1' : '0';
        };
        const marcar = () => {
            cuerpo.querySelectorAll('.bs-op').forEach((o, i) => o.classList.toggle('act', i === idx));
            const o = cuerpo.querySelectorAll('.bs-op')[idx];
            if (o) {
                ancla.setAttribute('aria-activedescendant', o.id);
                // se mueve solo la lista (scrollIntoView movería también la ventana y cerraría la lista)
                if (o.offsetTop < cuerpo.scrollTop) cuerpo.scrollTop = o.offsetTop - 6;
                else if (o.offsetTop + o.offsetHeight > cuerpo.scrollTop + cuerpo.clientHeight) cuerpo.scrollTop = o.offsetTop + o.offsetHeight - cuerpo.clientHeight + 6;
            }
        };
        const api = {
            el, ancla, abierta: true, t0: Date.now(),
            // items: [{ id, html, off }] o un aviso suelto { aviso: 'texto', cargando }
            poner(lista, activo) {
                items = lista.filter(x => !x.aviso);
                let n = 0;
                cuerpo.innerHTML = lista.map(x => x.aviso
                    ? '<div class="bs-aviso' + (x.cargando ? ' carga' : '') + '">' + (x.cargando ? '<i class="bs-giro" aria-hidden="true"></i>' : '') + esc(x.aviso) + '</div>'
                    : '<div class="bs-op' + (x.off ? ' off' : '') + (x.sel ? ' sel' : '') + '" role="option" id="' + el.id + '-' + (n++) + '" aria-selected="' + (x.sel ? 'true' : 'false') + '" aria-disabled="' + (x.off ? 'true' : 'false') + '" data-i="' + (n - 1) + '">' + x.html + '</div>').join('');
                idx = typeof activo === 'number' ? activo : items.findIndex(x => x.sel && !x.off);
                if (idx < 0) idx = items.findIndex(x => !x.off);
                marcar(); ubicar();
            },
            mover(d) {
                if (!items.length) return;
                let i = idx;
                for (let k = 0; k < items.length; k++) { i = (i + d + items.length) % items.length; if (!items[i].off) break; }
                idx = i; marcar();
            },
            elegir() { const x = items[idx]; if (x && !x.off) { cerrarLista(); onElegir(x); } },
            cerrar() {
                if (abierta !== api) return;
                abierta = null; api.abierta = false;
                ancla.setAttribute('aria-expanded', 'false'); ancla.removeAttribute('aria-activedescendant');
                el.classList.add('sale');
                setTimeout(() => el.remove(), reducido() ? 0 : 110);
                if (onCerrar) onCerrar();
            }
        };
        // mousedown (no click): el campo no pierde el foco ni cierra la lista antes de elegir
        el.addEventListener('mousedown', e => {
            if (e.target.closest('.bs-lista-q')) return;
            e.preventDefault();
            const o = e.target.closest('.bs-op');
            if (!o) return;
            idx = Number(o.dataset.i); api.elegir();
        });
        ancla.setAttribute('aria-expanded', 'true');
        ancla.setAttribute('aria-controls', el.id);
        abierta = api;
        return api;
    }

    // ── Lista desplegable ───────────────────────────────────────────────────────────────────────────────────────
    // opciones: [{ valor, etiqueta, tags: [{ t, tono }], off, extra }]; vacio: texto de la opción «sin elegir» (null = sin esa opción)
    function crearSelect({ opciones, valor, placeholder, vacio, buscar, ariaLabel, onCambio, aviso }) {
        let ops = opciones || [], val = valor == null ? '' : String(valor), lista = null, filtro = '';
        const el = document.createElement('div');
        el.className = 'bs-sel';
        el.innerHTML = '<button type="button" class="bs-sel-btn" role="combobox" aria-haspopup="listbox" aria-expanded="false"' + (ariaLabel ? ' aria-label="' + esc(ariaLabel) + '"' : '') + '>'
            + '<span class="bs-sel-val"></span><i class="bi bi-chevron-down" aria-hidden="true"></i></button>';
        const btn = el.querySelector('.bs-sel-btn'), vista = el.querySelector('.bs-sel-val');
        const actual = () => ops.find(o => String(o.valor) === val);
        const pintar = () => {
            const o = actual();
            vista.innerHTML = o ? '<span class="bs-sel-txt">' + esc(o.etiqueta) + '</span>' + (o.tags || []).map(t => tag(t.t, t.tono)).join('')
                : '<span class="bs-sel-ph">' + esc(vacio && val === '' ? vacio : (placeholder || 'Elija…')) + '</span>';
            el.classList.toggle('vacio', !o);
        };
        const items = () => {
            const q = sinTilde(filtro).trim();
            const base = [];
            if (vacio != null) base.push({ id: '', html: '<span class="bs-op-t">' + esc(vacio) + '</span>', sel: val === '' });
            ops.forEach(o => {
                if (q && !sinTilde(o.etiqueta).includes(q)) return;
                base.push({ id: String(o.valor), off: !!o.off, sel: String(o.valor) === val,
                    html: '<span class="bs-op-t">' + esc(o.etiqueta) + '</span>' + (o.tags || []).map(t => tag(t.t, t.tono)).join('') + (o.off && o.extra ? '<span class="bs-op-x">' + esc(o.extra) + '</span>' : '') });
            });
            return base.length ? base : [{ aviso: aviso || 'Sin resultados' }];
        };
        const elegir = x => { if (val !== x.id) { val = x.id; pintar(); if (onCambio) onCambio(val); } btn.focus(); };
        const abrir = () => {
            filtro = '';
            lista = abrirLista(btn, { onElegir: elegir, onCerrar: () => { lista = null; } });
            lista.poner(items());
            if (buscar) {
                const bus = document.createElement('input');
                bus.type = 'search'; bus.className = 'bs-lista-q'; bus.placeholder = 'Buscar…'; bus.setAttribute('aria-label', 'Buscar en la lista');
                lista.el.prepend(bus);
                bus.addEventListener('input', () => { filtro = bus.value; lista.poner(items(), 0); });
                bus.addEventListener('keydown', teclas);
                setTimeout(() => bus.focus({ preventScroll: true }), 0);
            }
        };
        function teclas(e) {
            if (!lista) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); lista.mover(1); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); lista.mover(-1); }
            else if (e.key === 'Enter') { e.preventDefault(); lista.elegir(); }
            else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); lista.cerrar(); btn.focus(); }
            else if (e.key === 'Tab') lista.cerrar();
        }
        btn.addEventListener('click', () => (lista ? lista.cerrar() : abrir()));
        btn.addEventListener('keydown', e => {
            if (!lista && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { e.preventDefault(); abrir(); return; }
            teclas(e);
        });
        pintar();
        return {
            el, get: () => val, opcion: actual,
            set(v) { val = v == null ? '' : String(v); pintar(); },
            poner(nuevas) { ops = nuevas; if (val !== '' && !actual()) val = ''; pintar(); },
            desactivar(on) { btn.disabled = !!on; el.classList.toggle('off', !!on); }
        };
    }

    // ── Tarjeta de nota de crédito ──────────────────────────────────────────────────────────────────────────────
    // previa: { numero, razon, monto, detalle } de una nota ya guardada; razones: las de Configuración › Notas de crédito
    function crearNota({ razones, previa, alCambiar, alQuitar }) {
        let nc = (previa && previa.detalle && previa.detalle.folio) ? previa.detalle : null;   // la nota de Nexacol elegida
        let manual = nc ? '' : String((previa && previa.numero) || '');
        let cargando = false, errorDetalle = '', ctlBusca = null;
        const razonPrevia = previa && previa.razon ? razones.find(r => r.nombre === previa.razon) : null;
        const el = document.createElement('div');
        el.className = 'bs-nc';
        el.innerHTML = '<div class="bs-nc-fila"><div class="bs-nc-cab"></div>'
            + '<button type="button" class="bs-nota-quitar" aria-label="Quitar esta nota de crédito" title="Quitar"><i class="bi bi-x-lg" aria-hidden="true"></i></button></div>'
            + '<div class="bs-nc-det" aria-live="polite"><div class="bs-nc-det-in"></div></div>'
            + '<div class="bs-nc-abajo"><div class="bs-nc-razon"><span class="bs-mini">Razón</span></div>'
            + '<label class="bs-nc-monto"><span class="bs-mini">Valor a descontar</span><span class="bs-nc-peso"><b>$</b>'
            + '<input type="number" class="bs-nota-monto" min="1" step="1" inputmode="numeric" aria-label="Valor de los productos a descontar" value="' + (previa && previa.monto ? Math.round(previa.monto) : '') + '"></span>'
            + '<button type="button" class="bs-nc-total" hidden>Usar el subtotal de la nota</button></label></div>';
        const cab = el.querySelector('.bs-nc-cab'), det = el.querySelector('.bs-nc-det'), detIn = el.querySelector('.bs-nc-det-in');
        const montoWrap = el.querySelector('.bs-nc-monto'), monto = el.querySelector('.bs-nota-monto'), btnTotal = el.querySelector('.bs-nc-total');
        const razonSel = crearSelect({
            ariaLabel: 'Razón de la nota de crédito', placeholder: 'Elija la razón…',
            valor: razonPrevia ? razonPrevia.id : '',
            opciones: razones.map(x => ({ valor: x.id, etiqueta: x.nombre,
                tags: [x.culpa_chofer ? { t: 'Culpa del chofer', tono: 'mal' } : { t: 'No es culpa', tono: 'ok' }].concat(x.descuenta_productos ? [{ t: 'Descuenta', tono: 'warn' }] : []) })),
            onCambio: () => { sync(); }
        });
        el.querySelector('.bs-nc-razon').appendChild(razonSel.el);

        // El valor a descontar es el subtotal de las líneas de productos de la nota (no el monto total de la nota)
        const subtotal = () => nc ? Math.round((nc.items || []).reduce((t, i) => t + (Number(i.subtotal) || 0), 0)) : 0;
        const razonActual = () => { const v = razonSel.get(); return v ? razones.find(r => String(r.id) === v) : null; };
        const nota = () => {
            const r = razonActual();
            const q = el.querySelector('.bs-nc-q');
            return { numero: nc ? nc.folio : (q ? q.value.trim() : manual.trim()), desde_nexacol: !!nc, razon_id: r ? r.id : null, culpa: !!(r && r.culpa_chofer),
                descuenta: !!(r && r.descuenta_productos), monto: Number(monto.value || 0) };
        };
        const sync = () => {
            const r = razonActual();
            const desc = !!(r && r.descuenta_productos);
            montoWrap.classList.toggle('ver', desc);
            btnTotal.hidden = !(desc && subtotal());
            if (desc && subtotal() && !Number(monto.value)) monto.value = subtotal();
            if (alCambiar) alCambiar();
        };

        // Cabecera: o el buscador (sin nota elegida) o la nota elegida con su botón «Cambiar»
        function pintarCab() {
            if (nc || cargando) {
                cab.innerHTML = '<div class="bs-nc-elegida"><span class="bs-nc-num">' + esc(nc ? nc.folio : 'Trayendo el detalle…') + '</span>'
                    + (nc ? tag(nc.cia, 'neutro') : '') + '<button type="button" class="bs-nc-cambiar"' + (cargando ? ' disabled' : '') + '>Cambiar</button></div>';
                cab.querySelector('.bs-nc-cambiar').addEventListener('click', () => { nc = null; manual = ''; errorDetalle = ''; pintarCab(); pintarDet(); sync(); const q = cab.querySelector('.bs-nc-q'); if (q) q.focus(); });
                return;
            }
            cab.innerHTML = '<div class="bs-nc-busca"><i class="bi bi-search" aria-hidden="true"></i>'
                + '<input type="text" class="bs-nc-q" maxlength="60" autocomplete="off" role="combobox" aria-haspopup="listbox" aria-expanded="false" aria-label="Número de la nota de crédito" placeholder="Buscar nota de crédito por su número">'
                + '</div>' + (manual ? '<div class="bs-nc-manual">Sin detalle de Nexacol: queda registrada solo con su número.</div>' : '');
            const q = cab.querySelector('.bs-nc-q');
            q.value = manual;
            enlazarBuscador(q);
        }

        function enlazarBuscador(q) {
            let lista = null, timer = 0, seq = 0;
            const cerrar = () => { if (lista) lista.cerrar(); lista = null; };
            const usarManual = x => { manual = x.id.slice(1); nc = null; pintarCab(); pintarDet(); sync(); };
            const elegir = async x => {
                if (x.id[0] === '#') return usarManual(x);
                cargando = true; errorDetalle = ''; manual = ''; pintarCab(); pintarDet();
                try {
                    const r = await fetch('/api/asistencia/bono-semanal/nc/detalle/?folio=' + encodeURIComponent(x.id), { headers: authHead() });
                    const out = await r.json().catch(() => ({}));
                    if (!r.ok || !out.nc || !out.nc.folio) throw new Error(out.detail || 'No se pudo traer el detalle de la nota.');
                    nc = out.nc;
                } catch (e) { errorDetalle = e.message || 'No se pudo traer el detalle de la nota.'; manual = x.id; }
                cargando = false; pintarCab(); pintarDet(); sync();
            };
            const mostrar = async () => {
                const t = q.value.trim(), mi = ++seq;
                if (!lista || !lista.abierta) lista = abrirLista(q, { onElegir: elegir, claseExtra: 'bs-lista-nc' });
                if (t.length < 2) { lista.poner([{ aviso: 'Escriba al menos 2 dígitos del número de la nota.' }]); return; }
                lista.poner([{ aviso: 'Buscando en Nexacol…', cargando: true }]);
                const manualItem = { id: '#' + t, html: '<span class="bs-op-t">Usar «' + esc(t) + '» sin buscar en Nexacol</span>' };
                try {
                    const r = await fetch('/api/asistencia/bono-semanal/nc/buscar/?q=' + encodeURIComponent(t), { headers: authHead() });
                    const out = await r.json().catch(() => ({}));
                    if (mi !== seq || !lista || !lista.abierta) return;
                    if (!r.ok) throw new Error(out.detail || 'Nexacol no respondió.');
                    const res = out.resultados || [];
                    lista.poner((res.length ? res.map(n => ({ id: n.folio, html: filaResultado(n, t) })) : [{ aviso: 'Ninguna nota de crédito coincide con «' + t + '».' }]).concat([manualItem]));
                } catch (e) {
                    if (mi !== seq || !lista || !lista.abierta) return;
                    lista.poner([{ aviso: (e.message || 'No se pudo consultar Nexacol.') }, manualItem]);
                }
            };
            q.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(mostrar, 220); });
            q.addEventListener('focus', () => { if (q.value.trim().length >= 2 && (!lista || !lista.abierta)) mostrar(); });
            q.addEventListener('keydown', e => {
                if (e.key === 'ArrowDown') { e.preventDefault(); if (!lista || !lista.abierta) mostrar(); else lista.mover(1); }
                else if (e.key === 'ArrowUp' && lista && lista.abierta) { e.preventDefault(); lista.mover(-1); }
                else if (e.key === 'Enter') { e.preventDefault(); if (lista && lista.abierta) lista.elegir(); }
                else if (e.key === 'Escape' && lista && lista.abierta) { e.preventDefault(); e.stopPropagation(); cerrar(); }
            });
            q.addEventListener('blur', () => { if (nc || cargando) return; manual = q.value.trim(); setTimeout(() => { if (lista && lista.abierta && document.activeElement !== q) cerrar(); }, 0); sync(); });
        }

        // El número escrito, con lo que coincide resaltado
        const resaltar = (folio, t) => {
            const i = sinTilde(folio).lastIndexOf(sinTilde(t));
            return i < 0 ? esc(folio) : esc(folio.slice(0, i)) + '<mark>' + esc(folio.slice(i, i + t.length)) + '</mark>' + esc(folio.slice(i + t.length));
        };
        const filaResultado = (n, t) => '<span class="bs-res"><span class="bs-res-1"><b>' + resaltar(n.folio, t) + '</b>' + tag(n.cia, 'neutro') + '<span class="bs-res-m">' + pesos(n.monto) + '</span></span>'
            + '<span class="bs-res-2">' + esc(n.cliente || 'Sin cliente') + ' · ' + esc(ddmmyyyy(n.fecha)) + ' · ' + n.lineas + (n.lineas === 1 ? ' producto' : ' productos') + '</span></span>';

        // Detalle de la nota elegida: quién, factura original, chofer y todas las líneas de productos
        function pintarDet() {
            let html = '';
            if (cargando) html = '<div class="bs-nc-ficha cargando"><i class="bs-giro" aria-hidden="true"></i>Trayendo el detalle completo de la nota…</div>';
            else if (errorDetalle) html = '<div class="bs-nc-ficha error">' + esc(errorDetalle) + ' La nota queda registrada con su número.</div>';
            else if (nc) {
                const items = nc.items || [];
                const total = items.reduce((s, i) => s + (Number(i.subtotal) || 0), 0), kilos = items.reduce((s, i) => s + (Number(i.kilos) || 0), 0);
                const dato = (k, v) => v ? '<div><dt>' + k + '</dt><dd>' + esc(v) + '</dd></div>' : '';
                html = '<div class="bs-nc-ficha"><dl class="bs-nc-datos">'
                    + dato('Cliente', nc.cliente) + dato('Fecha', ddmmyyyy(nc.fecha)) + dato('Monto de la nota', nc.monto ? pesos(nc.monto) : '')
                    + dato('Factura original', nc.factura_original ? nc.factura_original + (nc.fecha_factura ? ' · ' + ddmmyyyy(nc.fecha_factura) : '') : '')
                    + dato('Chofer', nc.chofer) + dato('Patente', nc.patente) + dato('Motivo en Nexacol', nc.motivo)
                    + '</dl>'
                    + (items.length ? '<div class="bs-nc-prod" tabindex="0" role="region" aria-label="Productos de la nota de crédito"><table><thead><tr><th scope="col">Producto</th><th scope="col" class="n">Cant.</th><th scope="col" class="n">Precio</th><th scope="col" class="n">Subtotal</th></tr></thead><tbody>'
                        + items.map(i => '<tr><td><span class="bs-p-n">' + esc(i.producto) + '</span><span class="bs-p-c">' + esc(i.codigo) + '</span></td><td class="n">' + num(i.cantidad) + '</td><td class="n">' + pesos(i.precio) + '</td><td class="n">' + pesos(i.subtotal) + '</td></tr>').join('')
                        + '</tbody></table></div><div class="bs-nc-pie"><span>' + items.length + (items.length === 1 ? ' producto' : ' productos') + (kilos > 0 ? ' · ' + num(kilos, 1) + ' kg' : '') + '</span><b>Total de las líneas ' + pesos(total) + '</b></div>'
                        : '<div class="bs-nc-vacia">La nota no tiene líneas de productos en Nexacol.</div>')
                    + '</div>';
            }
            detIn.innerHTML = html;
            det.classList.toggle('abierto', !!html);
        }

        btnTotal.addEventListener('click', () => { if (subtotal()) { monto.value = subtotal(); sync(); } });
        monto.addEventListener('input', () => { if (alCambiar) alCambiar(); });
        el.querySelector('.bs-nota-quitar').addEventListener('click', () => {
            el.classList.add('sale');
            const fin = () => { el.remove(); if (alQuitar) alQuitar(); };
            reducido() ? fin() : setTimeout(fin, 150);
        });
        pintarCab(); pintarDet(); sync();
        // Nota ya guardada sin el detalle de Nexacol (guardada antes o cuando falló la consulta): se vuelve a traer al abrir,
        // para que la ficha completa siempre se vea abierta y no solo la razón.
        if (!nc && previa && manual && /^[A-Za-z0-9-]+$/.test(manual)) {
            const folio = manual;
            cargando = true; pintarCab(); pintarDet();
            fetch('/api/asistencia/bono-semanal/nc/detalle/?folio=' + encodeURIComponent(folio), { headers: authHead() })
                .then(r => r.json().catch(() => ({})).then(out => ({ ok: r.ok, out })))
                .then(({ ok, out }) => { if (ok && out.nc && out.nc.folio) { nc = out.nc; manual = ''; } })
                .catch(() => {})
                .finally(() => { cargando = false; if (!el.isConnected && !el.parentNode) return; pintarCab(); pintarDet(); sync(); });
        }
        return { el, leer: nota, foco: () => { const q = el.querySelector('.bs-nc-q'); if (q) q.focus(); } };
    }

    window.mxBsUi = { crearSelect, crearNota, cerrarListas: cerrarLista };
})();
