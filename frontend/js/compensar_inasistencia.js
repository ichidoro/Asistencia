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
        if (typeof window.reloadSingleEmployeeRow === 'function') window.reloadSingleEmployeeRow(parseInt(empId, 10));
        else if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData();
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
            recargar(estado.empId);
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
