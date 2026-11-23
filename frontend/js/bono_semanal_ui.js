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
        obtiene: ['bs-ok', ''], proporcional: ['bs-pr', ''], pierde: ['bs-x', ''], en_curso: ['bs-curso', 'en curso'],
        sin_turno: ['bs-nada', 'sin turno']
    };

    function chipSemana(r, fecha) {
        const s = (r.semanas || []).find(x => x.hasta === fecha);
        if (!s) return '';
        const c = SEM[s.estado] || SEM.sin_turno;
        const tit = 'Semana ' + ddmm(s.desde) + ' al ' + ddmm(s.hasta) + ': '
            + (s.estado === 'pierde' ? 'no se paga (' + (s.perdidos || []).map(p => ddmm(p.fecha) + ' ' + p.causa).join('; ') + ')'
                : s.estado === 'proporcional' ? pesos(s.monto) + ' de ' + pesos(s.monto_completo) + ' (' + s.dias_proporcion + ' de ' + s.dias_turno + ' días en proporción)'
                    : s.estado === 'en_curso' ? 'en curso: ' + pesos(s.monto) + ' si cumple los días que faltan'
                        : s.estado === 'sin_turno' ? 'sin días de turno' : pesos(s.monto));
        return '<span class="bs-sem ' + c[0] + '" title="' + esc(tit) + '">' + esc(c[1] || pesos(s.monto)) + '</span>';
    }

    // Contenido de la celda de un día en la vista Fill Rate. normal(): lo que mostraría la vista Conceptos.
    window.mxBsCelda = function (emp, fecha, di, normal) {
        const r = evalDe(emp);
        if (!r) return '<span class="bs-na">·</span>';
        const cod = (r.dias || {})[fecha];
        const editable = puedeEditar();
        const boton = (clase, texto, tit) => editable
            ? '<button type="button" class="bs-dia ' + clase + '" title="' + esc(tit) + '" onclick="event.stopPropagation(); window.mxBsMarcar(' + Number(emp.id) + ', \'' + fecha + '\')">' + texto + '</button>'
            : '<span class="bs-dia ' + clase + '" title="' + esc(tit) + '">' + texto + '</span>';
        let html;
        if (cod === 'ok') html = boton('bs-ok', '✓', 'Cumple' + (editable ? ' · clic para marcar «no cumple»' : ''));
        else if (cod === 'nc') {
            const p = (r.perdidos || []).find(x => x.fecha === fecha);
            html = boton('bs-x', 'N/C', (p ? p.causa : 'No cumple') + (editable ? ' · clic para quitar' : ''));
        } else if (cod === 'pendiente') html = boton('bs-pend', '·', 'Día por llegar' + (editable ? ' · clic para marcar «no cumple»' : ''));
        else if (cod === 'pierde' || cod === 'proporcion') {
            const p = (r.perdidos || []).find(x => x.fecha === fecha);
            html = '<span class="bs-just ' + (cod === 'pierde' ? 'bs-x' : 'bs-pr') + '" title="' + esc(cod === 'pierde' ? 'Hace perder la semana: ' + (p ? p.causa : '') : 'Descuenta en proporción') + '">'
                + (typeof normal === 'function' ? normal() : '') + '</span>';
        } else if (cod === 'libre') html = '<span class="bs-libre">' + (typeof normal === 'function' ? normal() : '') + '</span>';
        else if (cod === 'fuera') html = '<span class="bs-na" title="Sin turno ese día">·</span>';
        else html = '<span class="bs-na" title="Esta semana termina en el período siguiente y se evalúa ahí">' + (typeof normal === 'function' ? normal() : '') + '</span>';
        return '<div class="bs-cel">' + html + chipSemana(r, fecha) + '</div>';
    };

    window.mxBsLeyenda = function () {
        const b = bonoSemanal();
        return '<span class="bs-ley"><b>' + esc(b ? b.nombre : 'Fill Rate') + '</b> · semana de lunes a domingo:</span>'
            + '<span><span class="bs-dia bs-ok">✓</span> cumple</span>'
            + '<span><span class="bs-dia bs-x">N/C</span> no cumple: pierde la semana</span>'
            + '<span><span class="bs-just bs-pr">DEOP</span> justificación en proporción</span>'
            + '<span><span class="bs-sem bs-ok">$40.000</span> resultado de la semana, en el domingo</span>'
            + (puedeEditar() ? '<span class="text-muted">Clic en un día para marcar o quitar «no cumple»</span>' : '');
    };

    // Clic en un día: marca «no cumple» (con comentario) o lo quita
    window.mxBsMarcar = async function (empId, fecha) {
        const b = bonoSemanal();
        const d = datos();
        if (!b || !d) return;
        const emp = (d.empleados || []).find(e => Number(e.id) === Number(empId)) || { id: empId };
        const r = evalDe(emp) || {};
        const marcado = (r.dias || {})[fecha] === 'nc';
        const quien = emp.nombre_completo || emp.nombre || '';
        let comentario = null;
        if (marcado) {
            const ok = await window.uiConfirm('¿Quitar el «no cumple» del ' + window.formatFechaDDMMYYYY(fecha) + '?',
                { quien, items: ['La semana vuelve a contar ese día como cumplido.'], confirmText: 'Quitar', danger: false });
            if (!ok) return;
        } else {
            const v = await window.uiPedir({ titulo: 'No cumple · ' + window.formatFechaDDMMYYYY(fecha),
                texto: quien + ': la semana de este día no se paga en ' + b.nombre + '.',
                campos: [{ nombre: 'comentario', etiqueta: 'Comentario', tipo: 'text', ayuda: 'Por ejemplo: no completó la carga' }],
                confirmText: 'Marcar no cumple' });
            if (v === null) return;
            comentario = v.comentario || null;
        }
        try {
            const resp = await fetch('/api/asistencia/bono-semanal/no-cumple/', { method: 'POST', headers: authHead(),
                body: JSON.stringify({ bono_id: r.bono_id, empleado_id: Number(empId), fecha, no_cumple: !marcado, comentario }) });
            const res = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(res.detail || 'No se pudo guardar.');
            if (window.Avisos) window.Avisos.listo(marcado ? 'Se quitó el «no cumple»' : 'Marcado «no cumple»');
            if (typeof window.reloadSingleEmployeeRow === 'function') await window.reloadSingleEmployeeRow(empId);
        } catch (e) {
            if (window.Avisos) window.Avisos.error(e.message || 'No se pudo guardar.'); else alert(e.message);
        }
    };
})();
