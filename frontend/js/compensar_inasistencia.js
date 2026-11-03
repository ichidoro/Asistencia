// ============================================================
// COMPENSAR INASISTENCIA — una sola acción, desde el día faltado (reglas del dueño, 27-10-2026)
// Con una jornada EXTRA: cubre el día completo y se gasta (deja de pagarse con el monto fijo).
// Con horas extra: minuto a minuto; deben cubrir todo el turno del día faltado.
// Reemplaza a «Días Compensatorios» y a «Reasignar / Mover». Las reglas las revisa el servidor.
// ============================================================
(function () {
    const MODAL_ID = 'modal-compensar-inasistencia';
    // La hoja de estilos general pone las etiquetas en mayúsculas; las opciones se leen como texto normal
    const ETIQUETA = 'text-transform:none;letter-spacing:normal;font-size:0.85rem;';
    const estado = { empId: null, fecha: null };

    function hm(min) {
        const m = Math.max(0, Math.round(Number(min) || 0));
        return Math.floor(m / 60) + ' h ' + String(m % 60).padStart(2, '0');
    }
    function fechaCorta(f) { return f ? f.slice(8, 10) + '-' + f.slice(5, 7) : ''; }
    function fechaLarga(f) {
        try {
            const dia = new Date(f + 'T12:00:00').toLocaleDateString('es-CL', { weekday: 'long' });
            return dia.charAt(0).toUpperCase() + dia.slice(1) + ' ' + f.slice(8, 10) + '-' + f.slice(5, 7) + '-' + f.slice(0, 4);
        } catch (e) { return f; }
    }
    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }
    function avisar(msg, tipo) {
        if (typeof showToast === 'function') showToast(msg, tipo);
        else alert(msg);
    }
    function recargar(empId) {
        if (typeof window.reloadSingleEmployeeRow === 'function') return window.reloadSingleEmployeeRow(parseInt(empId, 10));
        if (typeof window.loadMarcacionesData === 'function') return window.loadMarcacionesData();
    }

    // Compensar (diseño HD): una flecha punteada une la jornada EXTRA usada con el día faltado, el día faltado muestra su
    // nuevo estado y la jornada se marca un instante. Con «menos movimiento» no hay flecha: solo cambia el estado.
    function animarCompensacion(empId, fechaFalta, fechaJornada) {
        const celda = function (f) { return f ? document.querySelector('#marcaciones-view-container td.col-day[data-tip="' + empId + '|' + f + '"]') : null; };
        const a = celda(fechaFalta);
        if (!a) return;
        const b = celda(fechaJornada);
        const quieto = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        const conFlecha = !quieto && b && aLaVista(a) && aLaVista(b);
        marcar(a, conFlecha ? 'ci-llega-tarde' : 'ci-llega', 1400);
        if (b && !quieto) marcar(b, 'ci-usada', 1500);
        if (conFlecha) dibujarFlecha(b.getBoundingClientRect(), a.getBoundingClientRect());
    }
    function marcar(el, clase, ms) {
        el.classList.remove(clase);
        void el.offsetWidth;
        el.classList.add(clase);
        setTimeout(function () { el.classList.remove(clase); }, ms);
    }
    // Se ve de verdad: dentro de la grilla que se desliza y no tapada por las columnas fijas (nombre, saldo…)
    function aLaVista(el) {
        const r = el.getBoundingClientRect(), x = r.left + r.width / 2;
        let izq = 0, der = window.innerWidth;
        for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
            const ox = getComputedStyle(n).overflowX;
            if (ox === 'auto' || ox === 'scroll') { const c = n.getBoundingClientRect(); izq = Math.max(izq, c.left); der = Math.min(der, c.right); break; }
        }
        el.parentElement.querySelectorAll('td[style*="position:sticky"], .sticky-premium-col, .sticky-col-analitica').forEach(function (s) {
            const sr = s.getBoundingClientRect();
            if (sr.right > izq && sr.left < x) izq = Math.max(izq, sr.right);
        });
        return r.width > 0 && x > izq && x < der && r.bottom > 0 && r.top < window.innerHeight;
    }
    function dibujarFlecha(desde, hasta) {
        const x1 = desde.left + desde.width / 2, x2 = hasta.left + hasta.width / 2;
        const izq = Math.min(x1, x2), ancho = Math.max(Math.abs(x1 - x2), 1);
        const alto = Math.max(22, Math.min(56, ancho * 0.3)), m = 8;
        const sx = x1 - izq + m, ex = x2 - izq + m, y0 = alto + 2, k = (ex - sx) * 0.15;
        const d = 'M' + sx + ' ' + y0 + ' C ' + (sx + k) + ' 2, ' + (ex - k) + ' 2, ' + ex + ' ' + y0;
        // Punta de la flecha según la dirección final de la curva
        const tl = Math.hypot(k, y0 - 2) || 1, tx = k / tl, ty = (y0 - 2) / tl;
        const bx = ex - 7 * tx, by = y0 - 7 * ty;
        const punta = ex + ',' + y0 + ' ' + (bx - 4 * ty) + ',' + (by + 4 * tx) + ' ' + (bx + 4 * ty) + ',' + (by - 4 * tx);
        const w = ancho + 2 * m, h = alto + 6, id = 'ci-m' + Date.now();
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'ci-arco');
        svg.setAttribute('aria-hidden', 'true');
        svg.setAttribute('width', w);
        svg.setAttribute('height', h);
        svg.style.left = (izq - m) + 'px';
        svg.style.top = (Math.min(desde.top, hasta.top) + 4 - y0) + 'px';
        svg.innerHTML = '<defs><mask id="' + id + '" maskUnits="userSpaceOnUse" x="0" y="0" width="' + w + '" height="' + h + '">'
            + '<path class="ci-trazo" d="' + d + '" pathLength="100" fill="none" stroke="#fff" stroke-width="6"/></mask></defs>'
            + '<path d="' + d + '" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="4 4" stroke-linecap="round" mask="url(#' + id + ')"/>'
            + '<polygon class="ci-punta" points="' + punta + '" fill="currentColor"/>';
        document.body.appendChild(svg);
        setTimeout(function () { svg.remove(); }, 1900);
    }

    function asegurarModal() {
        if (document.getElementById(MODAL_ID)) return;
        document.body.insertAdjacentHTML('beforeend',
            '<div class="modal fade" id="' + MODAL_ID + '" tabindex="-1" aria-hidden="true">'
            + '<div class="modal-dialog modal-dialog-centered"><div class="modal-content border-0 shadow-lg" style="border-radius:16px;overflow:hidden;">'
            + '<div class="modal-header border-0 pb-2 pt-4 px-4"><div class="d-flex align-items-center gap-3 w-100">'
            + '<div class="d-flex align-items-center justify-content-center flex-shrink-0" style="width:44px;height:44px;background:#eef2ff;border-radius:12px;">'
            + '<i class="bi bi-arrow-left-right" style="font-size:1.2rem;color:#1b2f8f;"></i></div>'
            + '<div><h6 class="modal-title fw-bold mb-0">Compensar inasistencia</h6><div class="small text-muted" id="ci-subtitulo"></div></div>'
            + '<button type="button" class="btn-close ms-auto mb-auto" data-bs-dismiss="modal" aria-label="Cerrar"></button></div></div>'
            + '<div class="modal-body px-4 pt-2" id="ci-cuerpo"></div>'
            + '<div class="modal-footer border-0 px-4 pb-4">'
            + '<button type="button" class="btn btn-light" data-bs-dismiss="modal">Cancelar</button>'
            + '<button type="button" class="btn btn-primary fw-bold px-4" id="ci-guardar" disabled>Compensar</button></div>'
            + '</div></div></div>');
        document.getElementById('ci-guardar').addEventListener('click', guardar);
        document.getElementById(MODAL_ID).addEventListener('change', actualizarSeleccion);
    }

    function actualizarSeleccion() {
        const modal = document.getElementById(MODAL_ID);
        const sel = modal.querySelector('input[name="ci-opcion"]:checked');
        modal.querySelectorAll('.ci-op').forEach(function (card) {
            const elegida = Boolean(sel && card.contains(sel));
            card.classList.toggle('border-primary', elegida);
            card.style.borderWidth = elegida ? '2px' : '';
        });
        document.getElementById('ci-guardar').disabled = !sel;
    }

    function render(op) {
        document.getElementById('ci-subtitulo').textContent =
            fechaLarga(op.fecha) + ' · turno ' + op.turno + ' · ' + hm(op.requerido_min) + ' por cubrir';
        const cuerpo = document.getElementById('ci-cuerpo');
        if (op.bloqueo) {
            cuerpo.innerHTML = '<div class="alert alert-warning py-2 mb-0 small">' + esc(op.bloqueo) + '</div>';
            actualizarSeleccion();
            return;
        }
        const hayExtras = op.extras.length > 0;
        let html = '<div class="border rounded-3 p-3 mb-2 ci-op">'
            + '<div class="d-flex align-items-center gap-2"><span class="fw-semibold small">Con una jornada EXTRA</span>'
            + '<span class="ms-auto badge ' + (hayExtras ? 'bg-success-subtle text-success' : 'bg-secondary-subtle text-secondary') + '">'
            + (hayExtras ? 'Cubre el día completo' : 'No hay jornadas EXTRA en el tramo') + '</span></div>';
        op.extras.forEach(function (e) {
            html += '<label class="d-flex align-items-center gap-2 mt-2 small" style="' + ETIQUETA + 'cursor:pointer;">'
                + '<input type="radio" name="ci-opcion" value="EXTRA|' + esc(e.fecha) + '">'
                + '<span>' + fechaCorta(e.fecha) + ' · ' + esc(e.tipo) + ' · EXTRA validada · ' + hm(e.minutos) + '</span></label>';
        });
        if (hayExtras) {
            html += '<div class="small text-muted mt-1 ms-4">Esa jornada deja de pagarse con el monto fijo y queda como jornada compensatoria.</div>';
        }
        op.por_validar.forEach(function (e) {
            html += '<div class="small text-muted mt-2"><i class="bi bi-hourglass-split me-1"></i>' + fechaCorta(e.fecha) + ' · ' + esc(e.tipo)
                + ' · ' + hm(e.minutos) + ' · por validar: valídela como EXTRA para poder usarla.</div>';
        });
        html += '</div>';

        const he = op.horas_extra;
        html += '<div class="border rounded-3 p-3 ci-op">'
            + '<label class="d-flex align-items-center gap-2 small mb-0" style="' + ETIQUETA + 'cursor:' + (he.alcanza ? 'pointer' : 'default') + ';">'
            + '<input type="radio" name="ci-opcion" value="HORAS_EXTRA|"' + (he.alcanza ? '' : ' disabled') + '>'
            + '<span class="fw-semibold' + (he.alcanza ? '' : ' text-muted') + '">Con horas extra</span>'
            + '<span class="ms-auto badge ' + (he.alcanza ? 'bg-success-subtle text-success' : 'bg-danger-subtle text-danger') + '">'
            + (he.alcanza ? 'Alcanza' : 'No alcanza') + '</span></label>'
            + '<div class="small text-muted mt-1 ms-4">Disponibles ' + hm(he.disponibles_min) + ' de ' + hm(op.requerido_min)
            + ' (después de pagar la deuda del tramo)</div></div>';
        cuerpo.innerHTML = html;

        const posibles = cuerpo.querySelectorAll('input[name="ci-opcion"]:not([disabled])');
        if (posibles.length === 1) posibles[0].checked = true;
        actualizarSeleccion();
    }

    async function guardar() {
        const sel = document.querySelector('#' + MODAL_ID + ' input[name="ci-opcion"]:checked');
        if (!sel) return;
        const partes = sel.value.split('|');
        const btn = document.getElementById('ci-guardar');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Guardando...';
        try {
            const resp = await fetch('/api/asistencia/compensar-inasistencia/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ empleado_id: parseInt(estado.empId, 10), fecha: estado.fecha, modo: partes[0], fecha_jornada: partes[1] || null })
            });
            const data = await resp.json().catch(function () { return {}; });
            if (!resp.ok) throw new Error(data.detail || 'No se pudo compensar.');
            bootstrap.Modal.getInstance(document.getElementById(MODAL_ID)).hide();
            avisar(data.mensaje || 'Inasistencia compensada.', 'success');
            const empId = estado.empId, fecha = estado.fecha, jornada = partes[0] === 'EXTRA' ? partes[1] : null;
            Promise.resolve(recargar(empId)).then(function () { animarCompensacion(empId, fecha, jornada); });
        } catch (e) {
            avisar(e.message, 'error');
        } finally {
            btn.innerHTML = 'Compensar';
            actualizarSeleccion();
        }
    }

    window.abrirCompensarInasistencia = async function (empId, fecha) {
        asegurarModal();
        estado.empId = empId;
        estado.fecha = fecha;
        document.getElementById('ci-subtitulo').textContent = '';
        document.getElementById('ci-cuerpo').innerHTML =
            '<div class="text-center text-muted py-4 small"><span class="spinner-border spinner-border-sm me-2"></span>Buscando con qué compensar...</div>';
        document.getElementById('ci-guardar').disabled = true;
        bootstrap.Modal.getOrCreateInstance(document.getElementById(MODAL_ID)).show();
        try {
            const resp = await fetch('/api/asistencia/compensar-inasistencia/opciones/?empleado_id=' + encodeURIComponent(empId)
                + '&fecha=' + encodeURIComponent(fecha));
            const data = await resp.json().catch(function () { return {}; });
            if (!resp.ok) throw new Error(data.detail || 'No se pudo consultar con qué compensar.');
            render(data.data);
        } catch (e) {
            document.getElementById('ci-cuerpo').innerHTML = '<div class="alert alert-danger py-2 small mb-0">' + esc(e.message) + '</div>';
        }
    };

    window.quitarCompensacionInasistencia = async function (empId, fecha) {
        const texto = '¿Quitar la compensación del ' + fechaCorta(fecha) + '? La jornada usada vuelve a quedar como EXTRA y las horas extra quedan libres.';
        let ok;
        if (typeof Swal !== 'undefined') {
            const r = await Swal.fire({ icon: 'question', title: 'Quitar compensación', text: texto, showCancelButton: true,
                confirmButtonText: 'Quitar', cancelButtonText: 'Cancelar' });
            ok = r.isConfirmed;
        } else {
            ok = window.confirm(texto);
        }
        if (!ok) return;
        try {
            const resp = await fetch('/api/asistencia/compensar-inasistencia/?empleado_id=' + encodeURIComponent(empId)
                + '&fecha=' + encodeURIComponent(fecha), { method: 'DELETE' });
            const data = await resp.json().catch(function () { return {}; });
            if (!resp.ok) throw new Error(data.detail || 'No se pudo quitar la compensación.');
            avisar(data.mensaje || 'Compensación quitada.', 'success');
            recargar(empId);
        } catch (e) {
            avisar(e.message, 'error');
        }
    };
})();
