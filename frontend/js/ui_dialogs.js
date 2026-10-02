/**
 * Diálogos y accesibilidad base de la interfaz.
 *
 *  - window.uiConfirm(msg, opts) → Promise<boolean>   (reemplaza confirm() nativo)
 *  - window.alert(msg)                                (reemplaza alert() nativo, no bloquea, en cola)
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
    const stripLead = (s) => s.replace(/^[\s⚠️❌✅ℹ️🚨⛔🛑❗]+/u, '').trim();

    const DANGER_RE = /elimin|borrar|permanente|desvincul|baja\b|reabrir|revert|cr[ií]tic/i;

    function splitMessage(message) {
        const lines = String(message).split('\n');
        const idx = lines.findIndex((l) => l.trim());
        if (idx < 0) return { title: '', body: '' };
        return { title: stripLead(lines[idx]), body: lines.slice(idx + 1).join('\n').trim() };
    }

    window.uiConfirm = function uiConfirm(message, opts = {}) {
        if (!hasSwal()) return Promise.resolve(nativeConfirm(String(message)));
        const { title, body } = splitMessage(message);
        const danger = opts.danger !== undefined ? opts.danger : DANGER_RE.test(String(message));
        return window.Swal.fire({
            title,
            html: body ? `<div style="text-align:left; white-space:pre-line; font-size:0.9rem;">${esc(body)}</div>` : undefined,
            icon: 'warning',
            showCancelButton: true,
            focusCancel: danger,
            reverseButtons: true,
            confirmButtonText: opts.confirmText || (danger ? 'Sí, continuar' : 'Confirmar'),
            cancelButtonText: opts.cancelText || 'Cancelar',
            confirmButtonColor: danger ? '#dc2626' : '#059669',
            cancelButtonColor: '#64748b'
        }).then((r) => !!r.isConfirmed);
    };

    // ── alert() nativo → SweetAlert2 en cola (no pierde mensajes seguidos) ──
    let chain = Promise.resolve();
    function iconFor(text) {
        if (/^\s*(✅|éxito|guardad|correctamente|se (guard|elimin|cre|actualiz)[oó])/i.test(text)) return 'success';
        if (/error|❌|no se pudo|fall[oó]|fallo|no (se )?puede|inv[aá]lid/i.test(text)) return 'error';
        if (/⚠️|atenci[oó]n|advertencia|debe |obligatori|seleccione|ingrese/i.test(text)) return 'warning';
        return 'info';
    }
    window.alert = function (message) {
        if (!hasSwal()) return nativeAlert(message);
        const text = String(message == null ? '' : message);
        const icon = iconFor(text);
        const { title, body } = splitMessage(text);
        chain = chain.then(() => window.Swal.fire({
            icon,
            title: body ? title : undefined,
            html: body
                ? `<div style="text-align:left; white-space:pre-line; font-size:0.9rem;">${esc(body)}</div>`
                : `<div style="white-space:pre-line; font-size:0.95rem;">${esc(title)}</div>`,
            confirmButtonText: 'Entendido',
            confirmButtonColor: '#059669'
        })).catch(() => { /* un fallo de render no debe cortar la cola */ });
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
