/**
 * Diálogos y accesibilidad base de la interfaz.
 *
 *  - window.Avisos: listo, info, falta, error, ventana   (las cuatro clases de aviso de la etapa 4)
 *  - window.uiConfirm(msg, opts) → Promise<boolean>   (reemplaza confirm() nativo)
 *  - window.uiPedir(opts) → Promise<valores|null>      (reemplaza prompt() nativo)
 *  - window.alert(msg)                                (reemplaza alert() nativo, no bloquea: elige la clase de aviso)
 *  - Swal.fire: todas las ventanas toman el mismo vestido; las tostadas pasan al aviso breve
 *  - Semántica de teclado para elementos con onclick que no son <button>/<a>
 *  - aria-label automático en botones solo-ícono que ya traen title
 *
 * Si SweetAlert2 no está disponible se usa el diálogo nativo como respaldo.
 */
(function () {
    'use strict';

    const nativeAlert = window.alert.bind(window);
    const nativeConfirm = window.confirm.bind(window);
    const hasSwal = () => typeof window.Swal !== 'undefined';

    const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const stripLead = (s) => s.replace(/^[\s\p{Extended_Pictographic}️]+/u, '').trim();

    const DANGER_RE = /elimin|borrar|permanente|desvincul|baja\b|reabrir|revert|cr[ií]tic/i;

    function splitMessage(message) {
        const lines = String(message).split('\n');
        const idx = lines.findIndex((l) => l.trim());
        if (idx < 0) return { title: '', body: '' };
        return { title: stripLead(lines[idx]), body: lines.slice(idx + 1).join('\n').trim() };
    }

    // ── Avisos · etapa 4 del orden visual común (boceto aprobado el 28-10-2026) ──
    // 1 «Listo»: aviso breve abajo a la derecha, se va solo. 2 «Falta un dato»: banda dentro de la ventana abierta.
    // 3 «No se pudo»: ventana con un botón cuando no hay ventana abierta. 4 «¿Seguro?»: confirmación con el nombre
    // de la acción en el botón. Estilos en css/avisos.css; los Swal.fire sueltos toman el mismo vestido.
    const ICONOS = {
        check: '<path d="M20 6 9 17l-5-5"/>',
        info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
        x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
        alerta: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
        error: '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
        listo: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
        pregunta: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
        revertir: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
        borrar: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><path d="M10 11v6"/><path d="M14 11v6"/>',
        personas: '<path d="M18 21a8 8 0 0 0-16 0"/><circle cx="10" cy="8" r="5"/><path d="M22 20c0-3.37-2-6.5-4-8a5 5 0 0 0-.45-8.3"/>',
        sinred: '<path d="M12 20h.01"/><path d="M8.5 16.429a5 5 0 0 1 7 0"/><path d="M5 12.859a10 10 0 0 1 5.17-2.69"/><path d="M19 12.859a10 10 0 0 0-2.007-1.523"/><path d="M2 8.82a15 15 0 0 1 4.177-2.643"/><path d="M22 8.82a15 15 0 0 0-11.288-3.764"/><path d="m2 2 20 20"/>'
    };
    const svg = (n) => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (ICONOS[n] || ICONOS.info) + '</svg>';
    const ICONO_TIPO = { success: 'listo', error: 'error', warning: 'alerta', info: 'info', question: 'pregunta' };

    // Textos técnicos que todavía puedan llegar del navegador o del servidor, dichos en palabras simples.
    function enPalabras(texto) {
        let t = stripLead(String(texto == null ? '' : texto));
        if (/failed to fetch|networkerror|load failed|network request failed|err_internet|error de (conexi[oó]n|red)\b/i.test(t) && t.length < 140) {
            return SIN_CONEXION;
        }
        t = t.replace(/^(⚠️|❌|✅)?\s*error:\s*/i, '');
        if (window.fechasLegibles) t = window.fechasLegibles(t);
        if (/^error interno( del servidor)?\.?$/i.test(t)) return 'El servidor tuvo un problema y no terminó la operación. Vuelva a intentarlo.';
        if (/^(error desconocido|unknown error)\.?$/i.test(t)) return 'No se pudo completar. El servidor no dio el motivo.';
        return t;
    }
    // La primera frase va en negrita cuando el aviso trae más de una («Listo. …», «Falta la hora. …»).
    function rico(texto) {
        const t = esc(texto);
        const m = t.match(/^([^.\n]{2,60}\.)(\s+)([\s\S]+)$/);
        return m ? '<b>' + m[1] + '</b>' + m[2] + m[3] : t;
    }

    // 1 · Aviso breve
    let pila = null;
    function avisoBreve(texto, tipo, duracion) {
        const t = enPalabras(texto);
        if (!t) return;
        if (!pila || !document.body.contains(pila)) {
            pila = document.createElement('div');
            pila.className = 'av-pila';
            pila.setAttribute('aria-live', 'polite');
            document.body.appendChild(pila);
        }
        const el = document.createElement('div');
        el.className = 'av-toast' + (tipo === 'info' ? ' inf' : '');
        el.setAttribute('role', 'status');
        const ms = duracion || (t.length > 90 ? 6000 : 4000);
        el.innerHTML = '<span class="av-t-ic">' + svg(tipo === 'info' ? 'info' : 'check') + '</span><span class="av-t-tx">' + rico(t) +
            '</span><button type="button" class="av-t-x" aria-label="Cerrar aviso">' + svg('x') + '</button><span class="av-t-barra" style="animation-duration:' + ms + 'ms"></span>';
        const cerrar = () => {
            if (el.classList.contains('sale')) return;
            el.classList.add('sale');
            setTimeout(() => el.remove(), 170);
        };
        el.querySelector('.av-t-x').addEventListener('click', cerrar);
        el.querySelector('.av-t-barra').addEventListener('animationend', cerrar);
        pila.appendChild(el);
        while (pila.children.length > 3) pila.firstElementChild.remove();
    }

    // 2 · Banda dentro de la ventana abierta (Bootstrap). Devuelve false si no hay ventana abierta.
    function ventanaAbierta() {
        const abiertas = [...document.querySelectorAll('.modal.show')];
        return abiertas.length ? abiertas[abiertas.length - 1] : null;
    }
    function avisoEnVentana(texto, opts = {}) {
        const modal = opts.ventana || ventanaAbierta();
        const host = modal && (modal.querySelector('.modal-body') || modal.querySelector('.modal-content'));
        if (!host) return false;
        host.querySelectorAll(':scope > .av-banda').forEach((b) => b.remove());
        const err = opts.tipo === 'error';
        const b = document.createElement('div');
        b.className = 'av-banda ' + (err ? 'err' : 'fal');
        b.setAttribute('role', 'alert');
        b.innerHTML = svg(err ? 'error' : 'alerta') + '<span>' + rico(enPalabras(texto)) + '</span>';
        host.prepend(b);
        host.scrollTop = 0;
        modal.scrollTop = 0;
        const campos = (opts.campos || []).map((c) => (typeof c === 'string' ? document.getElementById(c) : c)).filter(Boolean);
        campos.forEach((c) => c.classList.add('av-falta'));
        const limpiar = () => {
            b.remove();
            campos.forEach((c) => c.classList.remove('av-falta'));
            modal.removeEventListener('input', limpiar, true);
            modal.removeEventListener('change', limpiar, true);
        };
        // Se quita cuando la persona corrige algo en la ventana o la cierra
        setTimeout(() => {
            modal.addEventListener('input', limpiar, true);
            modal.addEventListener('change', limpiar, true);
        }, 0);
        modal.addEventListener('hidden.bs.modal', limpiar, { once: true });
        if (campos[0] && typeof campos[0].focus === 'function') { try { campos[0].focus({ preventScroll: true }); } catch (_) { /* sin foco */ } }
        return true;
    }

    // 3 · Ventana de aviso (en cola: no pierde mensajes seguidos)
    let cola = Promise.resolve();
    function cuerpoHtml(cuerpo) {
        const lineas = cuerpo.split('\n').map((l) => l.trim()).filter(Boolean);
        const lista = lineas.filter((l) => /^[-•·]\s*/.test(l));
        if (lista.length >= 2 && lista.length === lineas.length) {
            return '<ul class="av-cs">' + lineas.map((l) => '<li>' + esc(l.replace(/^[-•·]\s*/, '')) + '</li>').join('') + '</ul>';
        }
        return '<div class="av-tx">' + lineas.map(esc).join('\n') + '</div>';
    }
    function partir(texto) {
        const t = enPalabras(texto);
        let { title, body } = splitMessage(t);
        if (!body) {
            const m = title.match(/^([^.]{8,80})\.\s+([\s\S]+)$/);
            if (m) { title = m[1]; body = m[2]; }
        }
        return { titulo: title.replace(/[.:]\s*$/, ''), cuerpo: body };
    }
    function avisoVentana(texto, tipo, opts = {}) {
        if (!hasSwal()) { nativeAlert(enPalabras(texto)); return Promise.resolve(); }
        const { titulo, cuerpo } = partir(texto);
        const icono = opts.icono || (/conexi[oó]n con el servidor/i.test(titulo) ? 'sinred' : /otra persona/i.test(titulo) ? 'personas' : null);
        cola = cola.then(() => window.Swal.fire({
            icon: tipo === 'falta' ? 'warning' : tipo === 'info' ? 'info' : 'error',
            iconHtml: icono ? svg(icono) : undefined,
            title: opts.titulo || titulo,
            html: (opts.quien ? '<div class="av-quien">' + esc(opts.quien) + '</div>' : '') + (cuerpo ? cuerpoHtml(cuerpo) : ''),
            confirmButtonText: 'Entendido'
        })).catch(() => { /* un fallo de render no debe cortar la cola */ });
        return cola;
    }

    // Elige la clase de aviso según lo que pasó (los nombres de tipo son los de showToast)
    function avisar(texto, tipo, duracion) {
        const t = String(texto == null ? '' : texto);
        if (tipo === 'success') return avisoBreve(t, 'listo', duracion);
        if (tipo === 'warning' || tipo === 'falta') return avisoEnVentana(t, { tipo: 'falta' }) || avisoVentana(t, 'falta');
        if (tipo === 'error' || tipo === 'danger') return avisoEnVentana(t, { tipo: 'error' }) || avisoVentana(t, 'error');
        // información: breve si es una línea corta; si trae varias líneas, ventana
        if (t.includes('\n') || t.length > 160) return avisoVentana(t, 'info');
        return avisoBreve(t, 'info', duracion);
    }

    const SIN_CONEXION = 'No hay conexión con el servidor. El cambio no se guardó; revise internet y vuelva a intentarlo.';
    // Encabezado de una ventana de una persona (etapa 6): las iniciales en lugar del ícono y, bajo el título,
    // «Nombre · día dd-mm-aaaa · detalle».
    window.cabeceraPersona = function (modal, o) {
        const cab = modal && modal.querySelector('.modal-header');
        if (!cab) return;
        o = o || {};
        const nombre = window.nombreTitulo ? window.nombreTitulo(o.nombre) : String(o.nombre || '');
        const p = String(o.nombre || '').trim().split(/\s+/).filter(t => t && t !== '.');
        const ini = p.length >= 3 ? p[2][0] + p[0][0] : p.length === 2 ? p[1][0] + p[0][0] : (p[0] || '—').slice(0, 2);
        let av = cab.querySelector('.vn-av');
        if (!av) {
            av = document.createElement('span');
            const icono = cab.querySelector('.rounded-circle');
            if (icono) icono.replaceWith(av);
            else { const t = cab.querySelector('.modal-title'); (t && t.parentElement !== cab ? t.parentElement : t || cab).before(av); }
        }
        av.className = 'vn-av td-t' + ((Math.abs(parseInt(o.empId, 10) || 0) % 6) + 1);
        av.setAttribute('aria-hidden', 'true');
        av.textContent = ini.toUpperCase();
        let dia = '';
        if (o.fecha) {
            try { dia = new Date(String(o.fecha).slice(0, 10) + 'T12:00:00').toLocaleDateString('es-CL', { weekday: 'long' }) + ' '; } catch (e) { dia = ''; }
            dia += window.formatFechaDDMMYYYY ? window.formatFechaDDMMYYYY(o.fecha) : o.fecha;
        }
        const sub = cab.querySelector('.vn-sub') || cab.querySelector('.small');
        if (sub) sub.textContent = [nombre, dia, o.detalle].filter(Boolean).join(' · ');
    };

    window.Avisos = {
        sinConexion: () => avisar(SIN_CONEXION, 'error'),
        listo: (t, d) => avisoBreve(t, 'listo', d),
        info: (t, d) => avisoBreve(t, 'info', d),
        falta: (t, opts = {}) => avisoEnVentana(t, Object.assign({ tipo: 'falta' }, opts)) || avisoVentana(t, 'falta', opts),
        error: (t, opts = {}) => avisoEnVentana(t, Object.assign({ tipo: 'error' }, opts)) || avisoVentana(t, 'error', opts),
        ventana: (t, tipo, opts) => avisoVentana(t, tipo || 'error', opts),
        enVentana: avisoEnVentana,
        avisar
    };

    // 4 · ¿Seguro? — uiConfirm(msg, { titulo, quien, items, confirmText, cancelText, danger, icono })
    window.uiConfirm = function uiConfirm(message, opts = {}) {
        if (!hasSwal()) return Promise.resolve(nativeConfirm(String(message)));
        const { title, body } = splitMessage(message);
        const titulo = opts.titulo || title;
        const items = opts.items || body.split('\n').map((l) => l.replace(/^[-•·]\s*/, '').trim()).filter(Boolean);
        const danger = opts.danger !== undefined ? opts.danger : DANGER_RE.test(String(message));
        const icono = opts.icono || (/elimin|borrar|quitar|desvincul/i.test(titulo) ? 'borrar' : /revert|reabrir|deshacer/i.test(titulo) ? 'revertir' : 'pregunta');
        return window.Swal.fire({
            title: titulo,
            html: (opts.quien ? '<div class="av-quien">' + esc(opts.quien) + '</div>' : '') +
                (items.length ? '<ul class="av-cs">' + items.map((i) => '<li>' + esc(i) + '</li>').join('') + '</ul>' : ''),
            icon: danger ? 'error' : 'question',
            iconHtml: svg(icono),
            customClass: { icon: 'av-ic av-ic-' + (danger ? 'peligro' : 'pregunta'), confirmButton: 'av-btn ' + (danger ? 'av-btn-borra' : 'av-btn-pri') },
            showCancelButton: true,
            focusCancel: danger,
            reverseButtons: true,
            confirmButtonText: opts.confirmText || (danger ? 'Sí, continuar' : 'Confirmar'),
            cancelButtonText: opts.cancelText || 'Cancelar',
            target: ventanaAbierta() || 'body'
        }).then((r) => !!r.isConfirmed);
    };

    // Ventana para escribir uno o más datos (reemplaza prompt()). Devuelve los valores o null si se cancela.
    // campos: [{ nombre, etiqueta, tipo: 'text'|'date'|'textarea', valor, requerido, ayuda }]
    window.uiPedir = function uiPedir(opts = {}) {
        const campos = opts.campos || [];
        if (!hasSwal()) {
            const out = {};
            for (const c of campos) { const v = window.prompt(c.etiqueta, c.valor || ''); if (v === null) return Promise.resolve(null); out[c.nombre] = v; }
            return Promise.resolve(out);
        }
        const html = (opts.texto ? '<div class="av-tx">' + esc(opts.texto) + '</div>' : '') + '<div class="av-campos">' + campos.map((c, i) => {
            const id = 'av-campo-' + i;
            const control = c.tipo === 'textarea'
                ? '<textarea id="' + id + '" placeholder="' + esc(c.ayuda || '') + '">' + esc(c.valor || '') + '</textarea>'
                : '<input id="' + id + '" type="' + (c.tipo === 'date' ? 'date' : 'text') + '" value="' + esc(c.valor || '') + '" placeholder="' + esc(c.ayuda || '') + '">';
            return '<label for="' + id + '">' + esc(c.etiqueta) + control + '</label>';
        }).join('') + '</div>';
        return window.Swal.fire({
            title: opts.titulo || '',
            html,
            icon: 'question',
            iconHtml: svg(opts.icono || 'pregunta'),
            showCancelButton: true,
            reverseButtons: true,
            confirmButtonText: opts.confirmText || 'Guardar',
            cancelButtonText: 'Cancelar',
            target: ventanaAbierta() || 'body',
            focusConfirm: false,
            didOpen: () => { const p = document.getElementById('av-campo-0'); if (p) p.focus(); },
            preConfirm: () => {
                const out = {};
                for (let i = 0; i < campos.length; i++) {
                    const v = (document.getElementById('av-campo-' + i).value || '').trim();
                    if (campos[i].requerido && !v) { window.Swal.showValidationMessage('Falta ' + campos[i].etiqueta.toLowerCase() + '.'); return false; }
                    out[campos[i].nombre] = v;
                }
                return out;
            }
        }).then((r) => (r.isConfirmed ? r.value : null));
    };

    // ── alert() nativo → la clase de aviso que corresponde ──
    function tipoDe(text) {
        if (/^\s*(✅|listo\b|[ée]xito|guardad|correctamente|exitosamente|se (guard|elimin|cre|actualiz|registr)[oó])/i.test(text) || /exitosamente|con [ée]xito|correctamente\.?$/i.test(text)) return 'success';
        if (/error|❌|no se pudo|fall[oó]|fallo|no (se )?puede|inv[aá]lid|no se permite|conflicto/i.test(text)) return 'error';
        if (/⚠️|atenci[oó]n|advertencia|debe |obligatori|seleccione|ingrese|indique|complete|falta/i.test(text)) return 'warning';
        return 'info';
    }
    window.alert = function (message) {
        const text = String(message == null ? '' : message);
        if (!hasSwal()) return nativeAlert(text);
        avisar(text, tipoDe(text));
    };

    // ── Todos los Swal.fire toman el mismo vestido; los que eran tostadas pasan al aviso breve ──
    function vestir(p) {
        const tipo = p.icon;
        const cc = Object.assign({}, p.customClass && typeof p.customClass === 'object' ? p.customClass : {});
        const anchoPropio = p.width && String(p.width) !== '440' && String(p.width) !== '440px';
        cc.popup = ((cc.popup || '') + ' av-dlg' + (tipo || p.iconHtml ? '' : ' av-sin-icono') + (anchoPropio ? ' av-ancha' : '')).trim();
        if (tipo) cc.icon = ((cc.icon || '') + ' av-ic av-ic-' + tipo).trim();
        const rojo = /^#?(dc2626|d33|dc3545|ef4444|e74c3c|c0267a|e11d48|b91c1c)$/i.test(String(p.confirmButtonColor || '').trim());
        if (!/av-btn/.test(cc.confirmButton || '')) cc.confirmButton = ((cc.confirmButton || '') + ' av-btn ' + (rojo ? 'av-btn-borra' : 'av-btn-pri')).trim();
        if (!/av-btn/.test(cc.cancelButton || '')) cc.cancelButton = ((cc.cancelButton || '') + ' av-btn').trim();
        if (!/av-btn/.test(cc.denyButton || '')) cc.denyButton = ((cc.denyButton || '') + ' av-btn').trim();
        const q = Object.assign({}, p, { customClass: cc, buttonsStyling: false });
        if (tipo && !p.iconHtml) q.iconHtml = svg(ICONO_TIPO[tipo] || 'info');
        if (q.reverseButtons === undefined) q.reverseButtons = true;
        if (!q.showClass) q.showClass = { popup: 'av-entra' };
        if (!q.hideClass) q.hideClass = { popup: 'av-sale' };
        if (!q.confirmButtonText || q.confirmButtonText === 'OK') q.confirmButtonText = q.showCancelButton ? 'Confirmar' : 'Entendido';
        if (!q.cancelButtonText || q.cancelButtonText === 'Cancel') q.cancelButtonText = 'Cancelar';
        return q;
    }
    function aParams(args) {
        if (args.length === 1 && args[0] && typeof args[0] === 'object') return Object.assign({}, args[0]);
        return { title: args[0], text: args[1], icon: args[2] };
    }
    function tostadaDeSwal(p) {
        const txt = [p.title, p.text].filter(Boolean).join('. ') || String(p.html || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
        avisar(txt, p.icon === 'success' ? 'success' : p.icon === 'error' ? 'error' : p.icon === 'warning' ? 'warning' : 'info', p.timer);
        return Promise.resolve({ isConfirmed: false, isDenied: false, isDismissed: true, dismiss: 'timer' });
    }
    function vestirSwal() {
        const S = window.Swal;
        if (!S || S.__avisos) return;
        const fire0 = S.fire;
        S.fire = function (...args) {
            const p = aParams(args);
            if (p.toast) return tostadaDeSwal(p);
            return fire0.call(this, vestir(p));
        };
        const mixin0 = S.mixin;
        S.mixin = function (mp) {
            const M = mixin0.call(this, mp);
            M.fire = function (...args) { return S.fire.call(M, Object.assign({}, mp, aParams(args))); };
            return M;
        };
        S.__avisos = true;
    }
    vestirSwal();

    // ── GET idénticos simultáneos comparten una sola petición ────────────────
    // Cada petición cuesta ~300 ms por el túnel; el arranque repetía varias (permisos, cumpleaños…).
    // Solo agrupa las que están en vuelo a la vez: no guarda respuestas, así que nunca sirve datos viejos.
    const nativeFetch = window.fetch.bind(window);
    const inflight = new Map();
    const SKIP = /[?&]_t=|last-change|\/api\/version|\/health|\/ping/;
    window.fetch = function (input, init) {
        try {
            const method = String((init && init.method) || (input && input.method) || 'GET').toUpperCase();
            const url = typeof input === 'string' ? input : (input && input.url);
            const hasSignal = (init && init.signal) || (input && typeof input !== 'string' && input.signal);
            if (method !== 'GET' || !url || hasSignal || (init && init.cache) || SKIP.test(url)) {
                return nativeFetch(input, init);
            }
            let auth = '';
            const h = init && init.headers;
            if (h) auth = typeof h.get === 'function' ? (h.get('Authorization') || '') : (h.Authorization || h.authorization || '');
            const key = url + '|' + auth;
            let p = inflight.get(key);
            if (!p) {
                p = nativeFetch(input, init);
                inflight.set(key, p);
                const done = () => inflight.delete(key);
                p.then(done, done);
            }
            return p.then((r) => r.clone());
        } catch (_) {
            return nativeFetch(input, init);
        }
    };

    // ── Carga diferida de librerías pesadas (se descargan al primer uso) ────
    const LIBS = {
        jspdf: ['/static/js/jspdf.umd.min.js', '/static/js/jspdf.plugin.autotable.min.js'],
        html5qrcode: ['/static/js/libs/html5-qrcode.min.js'],
        tesseract: ['https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js']
    };
    const libPromises = {};
    function loadScript(src) {
        return new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = src;
            s.onload = resolve;
            s.onerror = () => reject(new Error('No se pudo cargar ' + src));
            document.head.appendChild(s);
        });
    }
    window.ensureLib = function ensureLib(key) {
        if (!libPromises[key]) {
            // en serie: autotable necesita jsPDF ya cargado
            libPromises[key] = LIBS[key].reduce((p, src) => p.then(() => loadScript(src)), Promise.resolve())
                .catch((e) => { delete libPromises[key]; throw e; });
        }
        return libPromises[key];
    };

    // ── Teclado y lectores de pantalla ──────────────────────────────────────
    const NATIVE = 'a[href],button,input,select,textarea,summary,[contenteditable="true"]';
    const CLICKABLE = '[onclick]:not(' + NATIVE.split(',').join('):not(') + '):not(tr):not(td):not(th):not(li)';

    function enhance(root) {
        if (!root || root.nodeType !== 1) return;
        const list = [];
        if (root.matches && root.matches(CLICKABLE)) list.push(root);
        root.querySelectorAll && root.querySelectorAll(CLICKABLE).forEach((el) => list.push(el));
        list.forEach((el) => {
            if (!el.hasAttribute('role')) el.setAttribute('role', 'button');
            if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
        });

        const iconOnly = [];
        if (root.matches && root.matches('button[title]:not([aria-label])')) iconOnly.push(root);
        root.querySelectorAll && root.querySelectorAll('button[title]:not([aria-label])').forEach((b) => iconOnly.push(b));
        iconOnly.forEach((b) => {
            if (!b.textContent.trim()) b.setAttribute('aria-label', b.getAttribute('title'));
        });
    }

    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const el = e.target;
        if (!el || el.getAttribute('role') !== 'button' || el.matches(NATIVE)) return;
        e.preventDefault();
        el.click();
    });

    let pending = [];
    let scheduled = false;
    function flush() {
        scheduled = false;
        const nodes = pending; pending = [];
        nodes.forEach(enhance);
    }
    function init() {
        enhance(document.body);
        new MutationObserver((muts) => {
            muts.forEach((m) => m.addedNodes.forEach((n) => { if (n.nodeType === 1) pending.push(n); }));
            if (pending.length && !scheduled) { scheduled = true; requestAnimationFrame(flush); }
        }).observe(document.body, { childList: true, subtree: true });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
