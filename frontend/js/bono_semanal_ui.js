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

    // ¿El día es de la semana que sigue? (empieza en este período y se paga en el siguiente, donde cae su domingo)
    function deSemanaSiguiente(r, fecha) {
        const s = r && r.semana_siguiente;
        return !!(s && fecha >= s.desde && fecha <= s.hasta);
    }

    // Con fecha de la semana que sigue, el cierre de este período no la bloquea: la bloquea el cierre del período que paga
    // esa semana (lo revisa el servidor al guardar)
    function puedeEditar(r, fecha) {
        const d = datos();
        const cerrado = !!(d && d.periodo && d.periodo.cerrado) && !(fecha && deSemanaSiguiente(r, fecha));
        const permiso = typeof AuthService !== 'undefined' && AuthService.hasPermission ? AuthService.hasPermission('marcaciones.editar') : false;
        return permiso && !cerrado;
    }

    // Las notas de crédito del día: las de las semanas de este período y las de la semana que sigue
    const notasDelDia = (r, fecha) => (r.notas_credito || []).concat(r.notas_siguiente || []).filter(n => n.fecha === fecha);

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
        const editable = puedeEditar(r, fecha);
        // En la semana que sigue, el aviso al pasar el mouse dice dónde se evalúa y se paga
        const sig = deSemanaSiguiente(r, fecha) ? ' · semana del ' + ddmm(r.semana_siguiente.desde) + ' al ' + ddmm(r.semana_siguiente.hasta)
            + ': se evalúa y se paga en el período siguiente, donde cae su domingo' : '';
        const boton = (clase, texto, tit) => '<span class="bs-dia ' + clase + (editable ? ' bs-click' : '') + '" title="' + esc(tit + sig) + '">' + texto + '</span>';
        // Los estados del día (justificado, inasistencia, libre, feriado…) se ven IGUAL que en el resto de las vistas de la
        // grilla: la misma pastilla de la vista Conceptos, sin marco ni estilo propio (dueño, 23-11-2026). Si el día no tiene
        // registro pero sí justificación, se dibuja la pastilla de ese estado, también la de siempre.
        const estadoNormal = () => {
            const n = typeof normal === 'function' ? normal() : '';
            if (n) return n;
            const sigla = (r.justif || {})[fecha];
            if (!sigla || typeof window._analiticaCellBadge !== 'function') return '';
            const e = Object.entries(window._estadosAsistencia || {}).find(([, x]) => String(x.short_label || '').toUpperCase() === String(sigla).toUpperCase());
            return e ? window._analiticaCellBadge({ estado: e[0] }) : '';
        };
        const ncs = notasDelDia(r, fecha);
        const marcaNc = () => {
            if (!ncs.length) return '';
            // Cuántas notas de crédito tiene el día, con su número y razón al pasar el mouse
            const tit = ncs.map(n => (n.numero ? 'NC ' + n.numero : 'NC sin número') + ' · ' + (n.razon || '') + (n.descuenta && n.monto ? ' · descuenta ' + pesos(n.monto) : '')
                + (n.rol === 'peoneta' ? ' (del chofer con que iba)' : '')).join(' | ');
            return '<span class="bs-ncn" title="' + esc(tit) + '">NC' + (ncs.length > 1 ? '×' + ncs.length : '') + '</span>';
        };
        if (!['cumple', 'ok', 'nc', 'pendiente'].includes(cod)) {
            if (cod === 'fuera') return '<span class="bs-na" title="Sin turno ese día">·</span>';
            const est = estadoNormal();
            return ncs.length ? '<div class="bs-cel">' + est + marcaNc() + '</div>' : est;
        }
        let html;
        // En blanco: el Fill Rate se gana; solo se ve lo que cambia la semana (dueño, 23-11-2026)
        if (cod === 'cumple') html = boton('bs-ok', '✓', 'Cumple' + (editable ? ' · clic para cambiar' : ''));
        else if (cod === 'ok') html = '<span class="bs-vacio' + (editable ? ' bs-click' : '') + '" title="' + esc('Cumple' + (editable ? ' · clic para cambiar' : '') + sig) + '"></span>';
        else if (cod === 'nc') {
            const p = (r.perdidos || []).find(x => x.fecha === fecha);
            html = boton('bs-x', 'N/C', (p ? p.causa : 'No cumple') + (editable ? ' · clic para cambiar' : ''));
        } else html = '<span class="bs-vacio' + (editable ? ' bs-click' : '') + '" title="' + esc('Día por llegar' + (editable ? ' · clic para cambiar' : '') + sig) + '"></span>';
        return '<div class="bs-cel">' + html + marcaNc() + '</div>';
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
            + '<span>Días justificados, libres y feriados: con su estado de siempre (al pasar el mouse dice si cuenta como cumplido, en proporción o hace perder la semana)</span>'
            + '<span><span class="bs-ncn">NC</span> tiene nota de crédito (×2: dos o más)</span>'
            + '<span>«Total semana»: el resultado de cada semana</span>'
            + '<span>Una semana que termina en el período siguiente se marca aquí y se evalúa y paga allá, donde cae su domingo</span>'
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

    // Clic en un día de la vista (dueño, 23-11-2026): «Cumple» o «No cumple», con las notas de crédito del día (cada una
    // con su número y su razón; si alguna es culpa del chofer, no cumple; si no, cumple; si la razón descuenta los
    // productos, pide su valor), comentario y, para un chofer, los peonetas que iban con él ese día (reciben la misma
    // marca). Se abre con lo que ya estaba, para corregirlo.
    window.mxBsMarcar = async function (empId, fecha) {
        const b = bonoSemanal();
        const d = datos();
        if (!b || !d) return;
        const emp = (d.empleados || []).find(e => Number(e.id) === Number(empId)) || { id: empId };
        const r = evalDe(emp);
        if (!r) return;
        const cod = (r.dias || {})[fecha];
        const sigla = (r.justif || {})[fecha];
        if (!['ok', 'nc', 'pendiente', 'cumple'].includes(cod)) {
            if (window.Avisos) window.Avisos.info(cod === 'libre' ? 'Día libre o feriado: no se evalúa.'
                : sigla ? 'Ese día tiene «' + sigla + '»: no trabajó, así que no se evalúa ni puede tener nota de crédito.'
                    : cod === 'justificado' || cod === 'proporcion' || cod === 'pierde' ? 'Día justificado o con inasistencia: lo decide la configuración del bono.'
                        : 'Este día no se evalúa en este período.');
            return;
        }
        if (!puedeEditar(r, fecha)) { if (window.Avisos) window.Avisos.info('Período cerrado o sin permiso para cambiarlo.'); return; }
        const quien = emp.nombre_completo || emp.nombre || '';
        const previa = (r.marcas || {})[fecha] || {};
        const notasPrevias = notasDelDia(r, fecha).filter(n => n.rol === 'chofer');
        const todas = await razones();
        const usadas = new Set(notasPrevias.map(n => n.razon));
        const lista = todas.filter(x => x.activa || usadas.has(x.nombre));
        const esChofer = typeof window.categoriaCargo === 'function' && window.categoriaCargo(emp.cargo || '') === 'chofer';
        let peon = [], propuestos = [];
        if (esChofer) {
            peon = peonetasConBono();
            const guardados = (notasPrevias[0] && notasPrevias[0].peonetas_ids) || [];
            if (guardados.length) propuestos = guardados;
            else {
                try {
                    const rr = await fetch('/api/asistencia/bono-semanal/acompanantes/?chofer_id=' + Number(empId) + '&fecha=' + fecha, { headers: authHead() });
                    propuestos = rr.ok ? ((await rr.json()).peonetas_ids || []) : [];
                } catch (e) { propuestos = []; }
            }
        }
        const nombreDe = p => (window.nombreTitulo ? window.nombreTitulo(p.nombre_completo) : p.nombre_completo);
        const opsPeon = sel => '<option value="">Ninguno</option>' + peon.map(p => '<option value="' + p.id + '"'
            + (Number(sel) === Number(p.id) ? ' selected' : '') + '>' + esc(nombreDe(p)) + '</option>').join('');
        const opsRazon = nombreSel => '<option value="">Elija la razón…</option>' + lista.map(x => '<option value="' + x.id + '" data-culpa="' + (x.culpa_chofer ? 1 : 0) + '" data-desc="' + (x.descuenta_productos ? 1 : 0) + '"'
            + (nombreSel && x.nombre === nombreSel ? ' selected' : '') + '>' + esc(x.nombre) + (x.culpa_chofer ? ' · culpa del chofer' : ' · no es culpa del chofer')
            + (x.descuenta_productos ? ' · descuenta productos' : '') + '</option>').join('');
        // Una fila por nota de crédito: número, razón y, si la razón descuenta los productos, su valor
        const filaNota = (n) => '<div class="bs-nota">'
            + '<input type="text" class="bs-nota-num" maxlength="40" placeholder="N° de la nota" aria-label="Número de la nota de crédito" value="' + esc((n && n.numero) || '') + '">'
            + '<select class="bs-nota-razon" aria-label="Razón de la nota de crédito">' + opsRazon(n && n.razon) + '</select>'
            + '<input type="number" class="bs-nota-monto" min="1" step="1" placeholder="Valor $" aria-label="Valor de los productos a descontar" value="' + (n && n.monto ? Math.round(n.monto) : '') + '">'
            + '<button type="button" class="bs-nota-quitar" aria-label="Quitar esta nota de crédito" title="Quitar"><i class="bi bi-x-lg" aria-hidden="true"></i></button>'
            + '</div>';
        // Encabezado: el nombre de la persona; debajo, el bono y el día (dueño, 23-11-2026)
        const yaMarcado = !!previa.marca;
        const html = '<div class="av-quien">' + esc(b.nombre + ' · ' + window.formatFechaDDMMYYYY(fecha) + (yaMarcado ? ' · editar evaluación' : '')) + '</div>'
            + '<div class="av-tx">' + (yaMarcado ? 'Hoy está marcado <b>«' + (previa.marca === 'cumple' ? 'Cumple' : 'No cumple') + '»</b>' + (previa.usuario ? ' por ' + esc(previa.usuario) : '')
                + (notasPrevias.length ? ', con ' + (notasPrevias.length === 1 ? '1 nota de crédito' : notasPrevias.length + ' notas de crédito') : '') + '. Cambie lo que necesite y guarde, o elimine la marca.'
                : 'Si un día no cumple, la semana no se paga.') + '</div>'
            + '<div class="av-campos">'
            + '<div class="bs-notas-wrap"><span class="bs-notas-tit">Notas de crédito del día</span>'
            + '<div id="bs-notas">' + notasPrevias.map(filaNota).join('') + '</div>'
            + '<button type="button" id="bs-nota-mas" class="bs-nota-mas"><i class="bi bi-plus-lg" aria-hidden="true"></i> Agregar nota de crédito</button>'
            + (lista.length ? '' : '<small>No hay razones: créelas en Configuración › Notas de crédito.</small>') + '</div>'
            + '<div id="bs-efecto" class="av-tx" style="display:none"></div>'
            + '<label for="bs-coment">Comentario<input id="bs-coment" type="text" placeholder="Por ejemplo: no completó la carga" value="' + esc(previa.comentario || '') + '"></label>'
            + (esChofer ? '<label for="bs-p1">Peonetas que iban con el chofer (reciben la misma marca)<select id="bs-p1">' + opsPeon(propuestos[0]) + '</select>'
                + '<select id="bs-p2" style="margin-top:6px">' + opsPeon(propuestos[1]) + '</select>'
                + (propuestos.length ? '<small>' + (notasPrevias.length ? 'Los que se guardaron ese día' : 'Propuestos desde la libreta de ese día') + '; se pueden cambiar.</small>' : '') + '</label>' : '')
            + '</div>'
            + (yaMarcado ? '<div style="margin-top:12px;text-align:left"><button type="button" id="bs-eliminar" class="bs-eliminar">'
                + '<i class="bi bi-trash3" aria-hidden="true"></i> Eliminar marca y sus notas (el día queda sin marcar)</button></div>' : '');
        if (!window.Swal) { if (window.Avisos) window.Avisos.error('No se pudo abrir la ventana.'); return; }
        let eliminar = false;
        const leerNotas = () => Array.from(document.querySelectorAll('#bs-notas .bs-nota')).map(f => {
            const op = f.querySelector('.bs-nota-razon').selectedOptions[0];
            return { numero: (f.querySelector('.bs-nota-num').value || '').trim(), razon_id: op && op.value ? Number(op.value) : null,
                culpa: !!(op && op.dataset.culpa === '1'), descuenta: !!(op && op.dataset.desc === '1'),
                monto: Number(f.querySelector('.bs-nota-monto').value || 0) };
        });
        const validar = (notas) => {
            const vistos = new Set();
            for (const n of notas) {
                if (!n.numero) return 'Cada nota de crédito necesita su número.';
                if (vistos.has(n.numero.toUpperCase())) return 'La nota de crédito ' + n.numero + ' está repetida.';
                vistos.add(n.numero.toUpperCase());
                if (!n.razon_id) return 'Elija la razón de la nota de crédito ' + n.numero + '.';
                if (n.descuenta && !(n.monto > 0)) return 'La nota de crédito ' + n.numero + ' descuenta los productos: indique su valor.';
            }
            return '';
        };
        const peonetasElegidos = () => esChofer ? [...new Set(['bs-p1', 'bs-p2'].map(id => Number(document.getElementById(id).value || 0)).filter(Boolean))] : [];
        const res = await window.Swal.fire({
            title: (window.nombreTitulo ? window.nombreTitulo(quien) : quien),
            html: html, width: 'min(680px, calc(100vw - 32px))',
            showDenyButton: true, showCancelButton: true, reverseButtons: true, focusConfirm: false,
            confirmButtonText: 'No cumple', denyButtonText: 'Cumple', cancelButtonText: 'Cancelar',
            customClass: { confirmButton: 'av-btn av-btn-borra', denyButton: 'av-btn av-btn-pri', title: 'bs-titulo' },
            didOpen: () => {
                // Con notas de crédito, sus razones deciden: se oculta «Cumple» / «No cumple» y queda un solo «Guardar»
                const cont = document.getElementById('bs-notas');
                const pintar = () => {
                    cont.querySelectorAll('.bs-nota').forEach(f => {
                        const op = f.querySelector('.bs-nota-razon').selectedOptions[0];
                        f.querySelector('.bs-nota-monto').style.display = op && op.dataset.desc === '1' ? '' : 'none';
                    });
                    const notas = leerNotas();
                    const efecto = document.getElementById('bs-efecto');
                    const deny = window.Swal.getDenyButton(), conf = window.Swal.getConfirmButton();
                    if (notas.length) {
                        deny.style.display = 'none';
                        conf.textContent = 'Guardar';
                        const conRazon = notas.filter(n => n.razon_id);
                        const culpa = conRazon.some(n => n.culpa);
                        const desc = conRazon.filter(n => n.descuenta).reduce((s, n) => s + (n.monto || 0), 0);
                        efecto.style.display = conRazon.length ? '' : 'none';
                        efecto.textContent = !conRazon.length ? '' : (culpa ? 'Hay una nota por culpa del chofer: el día queda «No cumple» y la semana no se paga.'
                            : 'Ninguna nota es culpa del chofer: el día queda «Cumple».') + (desc > 0 ? ' Valor a descontar al chofer: ' + pesos(desc) + '.' : '');
                    } else {
                        deny.style.display = '';
                        conf.textContent = 'No cumple';
                        efecto.style.display = 'none';
                    }
                };
                document.getElementById('bs-nota-mas').addEventListener('click', () => {
                    cont.insertAdjacentHTML('beforeend', filaNota(null));
                    pintar();
                    const ult = cont.querySelector('.bs-nota:last-child .bs-nota-num');
                    if (ult) ult.focus();
                });
                cont.addEventListener('click', e => {
                    const q = e.target.closest('.bs-nota-quitar');
                    if (q) { q.closest('.bs-nota').remove(); pintar(); }
                });
                cont.addEventListener('change', pintar);
                cont.addEventListener('input', pintar);
                pintar();
                const del = document.getElementById('bs-eliminar');
                if (del) del.addEventListener('click', () => { eliminar = true; window.Swal.close(); });
            },
            preConfirm: () => {
                const notas = leerNotas();
                const error = validar(notas);
                if (error) { window.Swal.showValidationMessage(error); return false; }
                return { notas, comentario: (document.getElementById('bs-coment').value || '').trim() || null, peonetas: peonetasElegidos() };
            },
            preDeny: () => {
                if (leerNotas().length) { window.Swal.showValidationMessage('Con notas de crédito, sus razones deciden: use «Guardar».'); return false; }
                return { notas: [], comentario: (document.getElementById('bs-coment').value || '').trim() || null, peonetas: peonetasElegidos() };
            }
        });
        if (eliminar) {
            const ok = await window.uiConfirm('¿Eliminar la marca del ' + window.formatFechaDDMMYYYY(fecha) + '?',
                { quien, items: ['El día queda sin marcar: cuenta como cumplido.', 'Sus notas de crédito de ese día también se borran.', 'Las marcas de sus peonetas se corrigen en la fila de cada uno.'], confirmText: 'Eliminar marca', danger: true });
            if (!ok) return;
            try {
                const resp = await fetch('/api/asistencia/bono-semanal/no-cumple/', { method: 'POST', headers: authHead(),
                    body: JSON.stringify({ bono_id: r.bono_id, empleado_id: Number(empId), fecha, eliminar: true }) });
                const out = await resp.json().catch(() => ({}));
                if (!resp.ok) throw new Error(out.detail || 'No se pudo eliminar.');
                if (window.Avisos) window.Avisos.listo('Marca eliminada');
                if (typeof window.reloadSingleEmployeeRow === 'function') await window.reloadSingleEmployeeRow(empId);
            } catch (e) {
                if (window.Avisos) window.Avisos.error(e.message || 'No se pudo eliminar.'); else alert(e.message);
            }
            return;
        }
        if (res.isDismissed) return;
        const v = res.value || {};
        const notas = (v.notas || []).map(n => ({ numero: n.numero, razon_id: n.razon_id, monto: n.descuenta ? n.monto : null }));
        const cuerpo = { bono_id: r.bono_id, empleado_id: Number(empId), fecha, no_cumple: !!res.isConfirmed && !notas.length,
            comentario: v.comentario || null, notas, peonetas_ids: v.peonetas || [] };
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
