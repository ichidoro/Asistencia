/**
 * Vista «Fill Rate» de la grilla de Marcaciones (bono semanal, pedido de la persona dueña, 23-11-2026).
 * Cada día de turno de quien tiene el bono parte en «cumple» (✓); con un clic se marca «no cumple» (N/C), con un
 * comentario, y se pierde la semana completa. Los días con justificación muestran su sigla con el efecto configurado en
 * el bono (proporcional o pierde). En el domingo va el resultado de la semana. El cálculo lo hace el servidor
 * (bono_semanal.py) y llega en bonos_evaluacion de la grilla; este archivo solo lo dibuja y manda las marcas.
 * Todo vive en window.mxBs*; marcaciones_ui.js solo lo llama (botón de la vista, celda y leyenda).
 */
(function () {
    'use strict';

    const esc = s => window.Ayuda.esc(s);
    const pesos = n => '$' + Math.round(Number(n || 0)).toLocaleString('es-CL');
    const ddmm = f => String(f).slice(8, 10) + '-' + String(f).slice(5, 7);
    const authHead = () => ({ 'Authorization': `Bearer ${localStorage.getItem('access_token')}`, 'Content-Type': 'application/json' });

    function datos() {
        return (window.stateMarcacionesApp && window.stateMarcacionesApp.data) || null;
    }

    // El bono semanal de la grilla: el primero que llega en la evaluación de bonos ({nombre, id})
    function bonoSemanal(d) {
        d = d || datos();
        const ev = (d && d.bonos_evaluacion) || {};
        for (const emp of Object.keys(ev)) {
            for (const nombre of Object.keys(ev[emp] || {})) {
                const r = ev[emp][nombre];
                if (r && r.semanal) return { nombre, id: r.bono_id };
            }
        }
        return null;
    }

    function evalDe(emp) {
        const b = bonoSemanal();
        const d = datos();
        if (!b || !d || !d.bonos_evaluacion) return null;
        const e = d.bonos_evaluacion[emp.id] || d.bonos_evaluacion[String(emp.id)] || {};
        const r = e[b.nombre];
        return r && r.semanal && r.aplica !== false ? r : null;
    }

    function puedeEditar() {
        const d = datos();
        const cerrado = !!(d && d.periodo && d.periodo.cerrado);
        const permiso = typeof AuthService !== 'undefined' && AuthService.hasPermission ? AuthService.hasPermission('marcaciones.editar') : false;
        return permiso && !cerrado;
    }

    // ¿Hay alguien en la grilla con el bono semanal? (para mostrar el botón de la vista)
    window.mxBsHay = function (respData) {
        const b = bonoSemanal(respData);
        if (!b) return false;
        const ev = (respData && respData.bonos_evaluacion) || {};
        return Object.keys(ev).some(k => ev[k] && ev[k][b.nombre] && ev[k][b.nombre].aplica !== false);
    };
    window.mxBsNombre = function (respData) {
        const b = bonoSemanal(respData);
        return b ? b.nombre : 'Fill Rate';
    };

    const SEM = {
        obtiene: ['bs-ok', ''], proporcional: ['bs-pr', ''], pierde: ['bs-x', ''], en_curso: ['bs-curso', '$0 · en curso'],
        sin_turno: ['bs-nada', 'sin turno']
    };

    function chipSemana(r, fecha) {
        const s = (r.semanas || []).find(x => x.hasta === fecha);
        if (!s) return '';
        const c = SEM[s.estado] || SEM.sin_turno;
        const tit = 'Semana ' + ddmm(s.desde) + ' al ' + ddmm(s.hasta) + ': '
            + (s.estado === 'pierde' ? 'no se paga (' + (s.perdidos || []).map(p => ddmm(p.fecha) + ' ' + p.causa).join('; ') + ')'
                : s.estado === 'proporcional' ? pesos(s.monto) + ' de ' + pesos(s.monto_completo) + ' (' + s.dias_proporcion + ' de ' + s.dias_turno + ' días en proporción)'
                    : s.estado === 'en_curso' ? 'en curso: parte en $0; si cumple hasta el domingo, ' + pesos(s.monto_posible != null ? s.monto_posible : s.monto_completo)
                        : s.estado === 'sin_turno' ? 'sin días de turno' : pesos(s.monto));
        return '<span class="bs-sem ' + c[0] + '" title="' + esc(tit) + '">' + esc(c[1] || pesos(s.monto)) + '</span>';
    }

    // Contenido de la celda de un día en la vista Fill Rate. normal(): lo que mostraría la vista Conceptos.
    window.mxBsCelda = function (emp, fecha, di, normal) {
        const r = evalDe(emp);
        if (!r) return '<span class="bs-na">·</span>';
        const cod = (r.dias || {})[fecha];
        const editable = puedeEditar();
        const boton = (clase, texto, tit) => '<span class="bs-dia ' + clase + (editable ? ' bs-click' : '') + '" title="' + esc(tit) + '">' + texto + '</span>';
        let html;
        // En blanco: el Fill Rate se gana; solo se ve lo que cambia la semana (dueño, 23-11-2026)
        if (cod === 'cumple') html = boton('bs-ok', '✓', 'Cumple' + (editable ? ' · clic para cambiar' : ''));
        else if (cod === 'ok') html = '<span class="bs-vacio' + (editable ? ' bs-click' : '') + '" title="' + esc('Cumple' + (editable ? ' · clic para cambiar' : '')) + '"></span>';
        else if (cod === 'nc') {
            const p = (r.perdidos || []).find(x => x.fecha === fecha);
            html = boton('bs-x', 'N/C', (p ? p.causa : 'No cumple') + (editable ? ' · clic para cambiar' : ''));
        } else if (cod === 'pendiente') html = '<span class="bs-vacio' + (editable ? ' bs-click' : '') + '" title="' + esc('Día por llegar' + (editable ? ' · clic para cambiar' : '')) + '"></span>';
        else if (cod === 'pierde' || cod === 'proporcion') {
            const p = (r.perdidos || []).find(x => x.fecha === fecha);
            html = '<span class="bs-just ' + (cod === 'pierde' ? 'bs-x' : 'bs-pr') + '" title="' + esc(cod === 'pierde' ? 'Hace perder la semana: ' + (p ? p.causa : '') : 'Descuenta en proporción') + '">'
                + (typeof normal === 'function' ? normal() : '') + '</span>';
        } else if (cod === 'justificado') html = '<span class="bs-just bs-okj" title="Justificado: cuenta como cumplido">' + (typeof normal === 'function' ? normal() : '') + '</span>';
        else if (cod === 'libre') html = '<span class="bs-libre">' + (typeof normal === 'function' ? normal() : '') + '</span>';
        else if (cod === 'fuera') html = '<span class="bs-na" title="Sin turno ese día">·</span>';
        else html = '<span class="bs-na" title="Esta semana termina en el período siguiente y se evalúa ahí">' + (typeof normal === 'function' ? normal() : '') + '</span>';
        return '<div class="bs-cel">' + html + '</div>';
    };

    // Columna «Total semana», después de cada domingo: el resultado de la semana que termina ese día
    window.mxBsSemanaCelda = function (emp, domingo) {
        const r = evalDe(emp);
        const cont = r ? chipSemana(r, domingo) : '';
        return '<td class="col-day bs-sem-td text-center p-0 align-middle">' + (cont || '<span class="bs-na">·</span>') + '</td>';
    };

    window.mxBsLeyenda = function () {
        const b = bonoSemanal();
        return '<span class="bs-ley"><b>' + esc(b ? b.nombre : 'Fill Rate') + '</b> · semana de lunes a domingo:</span>'
            + '<span>En blanco: cumple (sin marcar)</span>'
            + '<span><span class="bs-dia bs-ok">✓</span> marcado «Cumple»</span>'
            + '<span><span class="bs-dia bs-x">N/C</span> no cumple: pierde la semana</span>'
            + '<span><span class="bs-just bs-okj">DEOP</span> justificado que cuenta como cumplido</span>'
            + '<span><span class="bs-just bs-pr">DEOP</span> justificado en proporción</span>'
            + '<span>«Total semana»: el resultado de cada semana</span>'
            + (puedeEditar() ? '<span class="text-muted">Clic en un día: «Cumple» o «No cumple»</span>' : '');
    };

    // Razones de nota de crédito (Configuración › Notas de crédito), leídas una vez
    let RAZONES = null;
    async function razones() {
        if (RAZONES) return RAZONES;
        try {
            const r = await fetch('/api/configuracion/razones-nota-credito/', { headers: authHead() });
            RAZONES = r.ok ? await r.json() : [];
        } catch (e) { RAZONES = []; }
        return RAZONES;
    }

    // Peonetas de la grilla que tienen el bono (para elegir con quién iba el chofer ese día)
    function peonetasConBono() {
        const d = datos();
        const esPeoneta = e => typeof window.categoriaCargo === 'function' && window.categoriaCargo(e.cargo || '') === 'peoneta';
        return ((d && d.empleados) || []).filter(e => esPeoneta(e) && evalDe(e))
            .sort((a, b) => String(a.nombre_completo || '').localeCompare(String(b.nombre_completo || ''), 'es'));
    }

    // Clic en un día de la vista (dueño, 23-11-2026): «Cumple» o «No cumple», con nota de crédito y su razón (si la razón
    // es culpa del chofer, no cumple; si no, cumple), comentario y, para un chofer, los peonetas que iban con él ese día
    // (reciben la misma marca). Se abre con lo que ya estaba, para corregirlo.
    window.mxBsMarcar = async function (empId, fecha) {
        const b = bonoSemanal();
        const d = datos();
        if (!b || !d) return;
        const emp = (d.empleados || []).find(e => Number(e.id) === Number(empId)) || { id: empId };
        const r = evalDe(emp);
        if (!r) return;
        const cod = (r.dias || {})[fecha];
        if (!['ok', 'nc', 'pendiente', 'cumple'].includes(cod)) {
            if (window.Avisos) window.Avisos.info(cod === 'libre' ? 'Día libre o feriado: no se evalúa.'
                : cod === 'justificado' || cod === 'proporcion' || cod === 'pierde' ? 'Día justificado o con inasistencia: lo decide la configuración del bono.'
                    : 'Este día no se evalúa en este período.');
            return;
        }
        if (!puedeEditar()) { if (window.Avisos) window.Avisos.info('Período cerrado o sin permiso para cambiarlo.'); return; }
        const quien = emp.nombre_completo || emp.nombre || '';
        const previa = (r.marcas || {})[fecha] || {};
        const lista = (await razones()).filter(x => x.activa || x.id === previa.razon_nc_id);
        const esChofer = typeof window.categoriaCargo === 'function' && window.categoriaCargo(emp.cargo || '') === 'chofer';
        let peon = [], propuestos = [];
        if (esChofer) {
            peon = peonetasConBono();
            try {
                const rr = await fetch('/api/asistencia/bono-semanal/acompanantes/?chofer_id=' + Number(empId) + '&fecha=' + fecha, { headers: authHead() });
                propuestos = rr.ok ? ((await rr.json()).peonetas_ids || []) : [];
            } catch (e) { propuestos = []; }
        }
        const nombreDe = p => (window.nombreTitulo ? window.nombreTitulo(p.nombre_completo) : p.nombre_completo);
        const opsPeon = sel => '<option value="">Ninguno</option>' + peon.map(p => '<option value="' + p.id + '"'
            + (Number(sel) === Number(p.id) ? ' selected' : '') + '>' + esc(nombreDe(p)) + '</option>').join('');
        const opsRazon = '<option value="">Elija la razón…</option>' + lista.map(x => '<option value="' + x.id + '" data-culpa="' + (x.culpa_chofer ? 1 : 0) + '"'
            + (previa.razon_nc_id === x.id ? ' selected' : '') + '>' + esc(x.nombre) + (x.culpa_chofer ? ' · culpa del chofer' : ' · no es culpa del chofer') + '</option>').join('');
        const html = '<div class="av-quien">' + esc(quien) + '</div><div class="av-tx">Si un día no cumple, la semana no se paga.'
            + (previa.marca ? ' Hoy está marcado «' + (previa.marca === 'cumple' ? 'Cumple' : 'No cumple') + '»' + (previa.usuario ? ' por ' + esc(previa.usuario) : '') + '.' : '') + '</div>'
            + '<div class="av-campos">'
            + '<label for="bs-nc">¿Tiene nota de crédito?<select id="bs-nc"><option value="0">No</option><option value="1"' + (previa.tiene_nc ? ' selected' : '') + '>Sí</option></select></label>'
            + '<label for="bs-razon" id="bs-razon-wrap" style="' + (previa.tiene_nc ? '' : 'display:none') + '">Razón de la nota de crédito<select id="bs-razon">' + opsRazon + '</select>'
            + (lista.length ? '' : '<small>No hay razones: créelas en Configuración › Notas de crédito.</small>') + '</label>'
            + '<div id="bs-efecto" class="av-tx" style="display:none"></div>'
            + '<label for="bs-coment">Comentario<input id="bs-coment" type="text" placeholder="Por ejemplo: no completó la carga" value="' + esc(previa.comentario || '') + '"></label>'
            + (esChofer ? '<label for="bs-p1">Peonetas que iban con el chofer (reciben la misma marca)<select id="bs-p1">' + opsPeon(propuestos[0]) + '</select>'
                + '<select id="bs-p2" style="margin-top:6px">' + opsPeon(propuestos[1]) + '</select>'
                + (propuestos.length ? '<small>Propuestos desde la libreta de ese día; se pueden cambiar.</small>' : '') + '</label>' : '')
            + '</div>';
        if (!window.Swal) { if (window.Avisos) window.Avisos.error('No se pudo abrir la ventana.'); return; }
        const res = await window.Swal.fire({
            title: b.nombre + ' · ' + window.formatFechaDDMMYYYY(fecha),
            html: html,
            showDenyButton: true, showCancelButton: true, reverseButtons: true, focusConfirm: false,
            confirmButtonText: 'No cumple', denyButtonText: 'Cumple', cancelButtonText: 'Cancelar',
            customClass: { confirmButton: 'av-btn av-btn-borra', denyButton: 'av-btn av-btn-pri' },
            didOpen: () => {
                // Con nota de crédito, la razón decide: se oculta «Cumple» / «No cumple» y queda un solo «Guardar»
                const nc = document.getElementById('bs-nc'), razon = document.getElementById('bs-razon');
                const pintar = () => {
                    const con = nc.value === '1';
                    document.getElementById('bs-razon-wrap').style.display = con ? '' : 'none';
                    const op = razon.options[razon.selectedIndex];
                    const efecto = document.getElementById('bs-efecto');
                    const deny = window.Swal.getDenyButton(), conf = window.Swal.getConfirmButton();
                    if (con) {
                        deny.style.display = 'none';
                        conf.textContent = 'Guardar';
                        efecto.style.display = op && op.value ? '' : 'none';
                        efecto.textContent = op && op.value ? (op.dataset.culpa === '1' ? 'Culpa del chofer: el día queda «No cumple» y la semana no se paga.' : 'No es culpa del chofer: el día queda «Cumple».') : '';
                    } else {
                        deny.style.display = '';
                        conf.textContent = 'No cumple';
                        efecto.style.display = 'none';
                    }
                };
                nc.addEventListener('change', pintar);
                razon.addEventListener('change', pintar);
                pintar();
            },
            preConfirm: () => {
                const con = document.getElementById('bs-nc').value === '1';
                const rid = document.getElementById('bs-razon').value;
                if (con && !rid) { window.Swal.showValidationMessage('Elija la razón de la nota de crédito.'); return false; }
                return {
                    tiene_nc: con, razon_nc_id: rid ? Number(rid) : null,
                    comentario: (document.getElementById('bs-coment').value || '').trim() || null,
                    peonetas: esChofer ? [...new Set(['bs-p1', 'bs-p2'].map(id => Number(document.getElementById(id).value || 0)).filter(Boolean))] : []
                };
            },
            preDeny: () => {
                if (document.getElementById('bs-nc').value === '1') { window.Swal.showValidationMessage('Con nota de crédito, la razón decide: use «Guardar».'); return false; }
                return {
                    comentario: (document.getElementById('bs-coment').value || '').trim() || null,
                    peonetas: esChofer ? [...new Set(['bs-p1', 'bs-p2'].map(id => Number(document.getElementById(id).value || 0)).filter(Boolean))] : []
                };
            }
        });
        if (res.isDismissed) return;
        const v = res.value || {};
        const cuerpo = { bono_id: r.bono_id, empleado_id: Number(empId), fecha, no_cumple: !!res.isConfirmed && !v.tiene_nc,
            comentario: v.comentario || null, tiene_nc: !!v.tiene_nc, razon_nc_id: v.razon_nc_id || null, peonetas_ids: v.peonetas || [] };
        try {
            const resp = await fetch('/api/asistencia/bono-semanal/no-cumple/', { method: 'POST', headers: authHead(), body: JSON.stringify(cuerpo) });
            const out = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(out.detail || 'No se pudo guardar.');
            const n = (v.peonetas || []).length;
            if (window.Avisos) window.Avisos.listo((out.no_cumple ? 'Marcado «no cumple»' : 'Marcado «cumple»')
                + (n ? ' · también ' + (n === 1 ? 'su peoneta' : 'sus 2 peonetas') : ''));
            // Las filas a la vista se refrescan; si un peoneta está en otra pestaña, se vuelven a pedir los datos de la grilla
            const personas = out.personas || [Number(empId)];
            if (personas.some(pid => !document.getElementById('row-empleado-' + pid)) && typeof window.loadMarcacionesData === 'function') {
                await window.loadMarcacionesData();
            } else {
                for (const pid of personas) {
                    if (typeof window.reloadSingleEmployeeRow === 'function') await window.reloadSingleEmployeeRow(pid);
                }
            }
        } catch (e) {
            if (window.Avisos) window.Avisos.error(e.message || 'No se pudo guardar.'); else alert(e.message);
        }
    };
})();
