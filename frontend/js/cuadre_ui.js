// ── Cuadre del tramo: una sola ventana para la deuda, las horas extra y los perdonazos ──────────────
// Regla del dueño (25-10-2026): la deuda se cubre sola con las horas extra; después hay UNA pregunta con dos
// respuestas: «llevar todo a cero» (lo que falte se perdona, lo que sobre no se paga) o «pagar horas extra:
// ¿cuántas?» (todas, un bloque o una cantidad; el resto queda escrito como no pagado). La decisión se guarda
// como política del tramo y la aplicación la vuelve a repartir sola cada vez que cambian las marcas.
// Diseño aprobado por el dueño el 25-10-2026 (boceto en Claude Design): misma distribución y lógica, terminación
// más pulcra y simétrica (columnas iguales, números en JetBrains Mono, etiquetas de color suaves).
// Los textos van con comillas y concatenación: el minificador del servidor come los espacios de las
// plantillas `...` anidadas dentro de ${}.
(function () {
    'use strict';

    const MENOS = '−';

    function fmt(min) {
        const v = Number(min) || 0;
        if (typeof window.formatExactMinutesToTime === 'function') return window.formatExactMinutesToTime(Math.abs(v));
        const seg = Math.round(Math.abs(v) * 60);
        const h = Math.floor(seg / 3600), m = Math.floor((seg % 3600) / 60), s = seg % 60;
        return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    }
    function signo(v) { return v > 0.0083 ? '+' : (v < -0.0083 ? MENOS : ''); }
    function token() {
        return (typeof AuthService !== 'undefined' && typeof AuthService.getToken === 'function') ? AuthService.getToken() : localStorage.getItem('access_token');
    }
    function puedeDecidir() {
        return typeof AuthService === 'undefined' || typeof AuthService.hasPermission !== 'function' || AuthService.hasPermission('marcaciones.horas_extras');
    }
    function esc(t) { return String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
    function fechaLarga(f) {
        const d = new Date(f + 'T00:00:00');
        const dias = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
        return dias[d.getDay()] + ' ' + String(d.getDate()).padStart(2, '0') + '-' + String(d.getMonth() + 1).padStart(2, '0');
    }
    function fechaDMA(f) { const p = String(f || '').substring(0, 10).split('-'); return p.length === 3 ? (p[2] + '-' + p[1] + '-' + p[0]) : String(f || ''); }
    function mono(t, cls) { return '<b class="cq-mono' + (cls ? ' ' + cls : '') + '">' + t + '</b>'; }
    function toast(msg, tipo) { if (typeof showToast === 'function') showToast(msg, tipo || 'info'); }

    const estado = { data: null, eleccion: null, minutos: null, empleadoId: null, nombre: '' };

    async function cargar(empleadoId) {
        const p = (window.stateMarcacionesApp && window.stateMarcacionesApp.data && window.stateMarcacionesApp.data.periodo) || {};
        const ini = p.inicio || window.stateMarcacionesApp?.fechaInicioRRHH, fin = p.fin || window.stateMarcacionesApp?.fechaFinRRHH;
        if (!ini || !fin) throw new Error('No se conoce el tramo abierto.');
        const r = await fetch('/api/cuadre/libro/?empleado_id=' + empleadoId + '&fecha_inicio=' + ini + '&fecha_fin=' + fin,
            { headers: { 'Authorization': 'Bearer ' + token() } });
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || ('Error ' + r.status)); }
        return r.json();
    }

    // Base de la pregunta: qué pasa si TODAS las horas extra trabajadas se usan para cubrir la deuda.
    // Se plantea siempre sobre los números crudos (sin el perdón del cuadre), para poder cambiar la decisión.
    function base(libro) {
        const disp = Math.max(0, (libro.he_trabajadas || 0) - (libro.he_usadas_inasistencia || 0));
        const deuda = Math.max(0, (libro.deuda_neta || 0));
        const cubre = Math.min(disp, deuda);
        return { disp, deuda, cubre, sobran: disp - cubre, falta: deuda - cubre };
    }
    function tomarPolitica(data) {
        const p = data && data.politica;
        estado.eleccion = p ? p.politica : null;
        estado.minutos = (p && p.politica === 'PAGAR' && p.minutos_a_pagar != null) ? Number(p.minutos_a_pagar) : null;
    }
    function esLaVigente() {
        const p = estado.data && estado.data.politica;
        if (!p || !estado.eleccion) return false;
        if (p.politica !== estado.eleccion) return false;
        if (p.politica !== 'PAGAR') return true;
        const pm = (p.minutos_a_pagar == null) ? null : Number(p.minutos_a_pagar);
        return pm === estado.minutos;
    }

    // Barra de 12 px sin texto: cada tramo mide lo que vale (mínimo 4 px para que se vea); el detalle va en la suma de abajo
    function barra(partes) {
        const total = partes.reduce((s, p) => s + Math.max(0, p.v), 0);
        if (total <= 0.0083) return '<div class="cq-bar"></div>';
        let html = '<div class="cq-bar">';
        partes.forEach(function (p) {
            if (p.v <= 0.0083) return;
            html += '<div class="cq-seg" style="flex:' + p.v.toFixed(3) + ' 0 0;background:' + p.c + '" title="' + esc(p.t) + ' ' + fmt(p.v) + '"></div>';
        });
        return html + '</div>';
    }

    function chipPolitica(pol) {
        if (!pol) return '<span class="cq-chip-pol cq-pol-nada"><i></i>Política del tramo: por decidir</span>';
        const quien = pol.decidido_por ? (' · ' + esc(pol.decidido_por)) : '';
        if (pol.politica === 'CERO') return '<span class="cq-chip-pol cq-pol-cero"><i></i>Llevar todo a cero' + quien + '</span>';
        const cuanto = (pol.minutos_a_pagar == null) ? 'todas las que sobren' : ('hasta ' + fmt(pol.minutos_a_pagar));
        return '<span class="cq-chip-pol cq-pol-pagar"><i></i>Pagar horas extra: ' + cuanto + quien + '</span>';
    }

    function render() {
        const d = estado.data, L = d.libro, b = base(L);
        const el = document.getElementById('cq-cuerpo');
        if (!el) return;
        const puede = puedeDecidir();

        // ── Hechos ─────────────────────────────────────────────────────
        let h = '<section class="cq-facts">'
            + fact('Dejó de trabajar', fmt(L.deuda_bruta), (L.perdonado > 0.0083 ? ('ya perdonado ' + fmt(L.perdonado)) : 'sin perdonazos'))
            + fact('Horas extra trabajadas', fmt(L.he_trabajadas), (L.he_por_decidir > 0.0083 ? (fmt(L.he_por_decidir) + ' por decidir') : 'todas con decisión'))
            + fact('Deuda pendiente hoy', fmt(L.pendiente), L.pendiente > 0.0083 ? 'en rojo en la grilla' : 'nada pendiente', L.pendiente > 0.0083 ? 'cq-rojo' : 'cq-verde')
            + fact('Saldo hoy', signo(L.saldo) + fmt(L.saldo), 'a pagar ' + MENOS + ' pendiente', L.saldo < -0.0083 ? 'cq-rojo' : (L.saldo > 0.0083 ? 'cq-verde' : ''))
            + '</section>';

        // ── Paso 1: cubrir (automático) ────────────────────────────────
        h += '<section class="cq-pasos"><div class="cq-paso"><div class="cq-rail"><div class="cq-num cq-num-ok">1</div><div class="cq-linea"></div></div>'
            + '<div class="cq-paso-cuerpo cq-paso-1"><div class="cq-titulo-fila"><span class="cq-titulo">Cubrir la deuda con horas extra</span><span class="cq-badge">Automático</span></div>'
            + '<div class="cq-texto">De las ' + mono(fmt(b.disp)) + ' trabajadas de más, ' + mono(fmt(b.cubre)) + ' cubren la deuda. '
            + (b.falta > 0.0083 ? ('Falta por cubrir ' + mono(fmt(b.falta), 'cq-rojo') + '.') : ('Sobran ' + mono(fmt(b.sobran), 'cq-verde') + '.'))
            + (L.perdon_cuadre > 0.0083 ? (' Ya perdonado por el cuadre a cero: ' + mono(fmt(L.perdon_cuadre)) + '.') : '')
            + '</div></div></div>';

        // ── Paso 2: la única pregunta ──────────────────────────────────
        h += '<div class="cq-paso"><div class="cq-rail"><div class="cq-num">2</div></div><div class="cq-paso-cuerpo">';
        if (b.sobran > 0.0083) {
            h += '<div class="cq-titulo">Una sola pregunta: sobran ' + fmt(b.sobran) + ', ¿qué hacemos?</div>'
                + '<div class="cq-opciones">'
                + opcion('CERO', 'Llevar todo a cero', 'saldo 00:00:00', '', 'No se paga nada. Las ' + fmt(b.sobran) + ' quedan escritas como «no pagadas».')
                + opcionPagar(b.sobran)
                + '</div>';
        } else if (b.falta > 0.0083) {
            h += '<div class="cq-titulo">Una sola pregunta: falta ' + fmt(b.falta) + ' por cubrir, ¿qué hacemos?</div>'
                + '<div class="cq-opciones">'
                + opcion('CERO', 'Llevar todo a cero', 'saldo 00:00:00', '', 'Se perdonan ' + fmt(b.falta) + ', con tu nombre y la fecha en el registro.')
                + opcion('PAGAR', 'Dejar la deuda', 'saldo ' + MENOS + fmt(b.falta), 'cq-rojo', 'Se descuenta en el cierre. No hay horas que pagar.')
                + '</div>';
        } else if (b.deuda > 0.0083 || b.disp > 0.0083) {
            h += '<div class="cq-titulo">Las horas extra cubren exactamente la deuda</div>'
                + '<div class="cq-opciones">' + opcion('CERO', 'Confirmar: todo a cero', 'saldo 00:00:00', '', 'Queda registrado que se cubrió con horas extra.') + '</div>';
        } else {
            h += '<div class="cq-titulo">Nada que cuadrar</div><div class="cq-texto">No hay deuda ni horas extra en el tramo.</div>';
        }
        if (d.politica) h += '<div class="cq-nota">Decisión vigente: ' + chipPolitica(d.politica) + ' Elige otra opción para cambiarla, o «Quitar política» para volver a empezar.</div>';
        if (!puede) h += '<div class="cq-nota">Solo puedes ver el cuadre; decidirlo requiere el permiso de horas extra.</div>';
        h += '</div></div></section>';

        // ── Vista previa de la decisión ─────────────────────────────────
        h += '<div id="cq-preview"></div>';

        // ── Resultado actual (las sumas siempre cuadran) ───────────────
        const usadas = L.he_usadas_deuda + L.he_usadas_inasistencia;
        h += '<section class="cq-ident"><div class="cq-eyebrow">Hoy, con lo decidido hasta ahora</div><div class="cq-filas">'
            + fila('Deuda', fmt(L.deuda_bruta), barra([{ v: L.perdonado, c: '#7A8296', t: 'perdonado' }, { v: L.cubierto, c: '#3B5BDB', t: 'cubierto' }, { v: L.pendiente, c: '#D64535', t: 'pendiente' }]),
                'perdonado ' + fmt(L.perdonado) + ' + cubierto ' + fmt(L.cubierto) + ' + pendiente ' + fmt(L.pendiente))
            + fila('Horas extra', fmt(L.he_trabajadas), barra([{ v: usadas, c: '#3B5BDB', t: 'usadas' }, { v: L.he_a_pagar, c: '#2F9E5E', t: 'a pagar' }, { v: L.he_no_pagadas, c: '#C9CED9', t: 'no pagadas' }, { v: L.he_por_decidir, c: '#E0A030', t: 'por decidir' }]),
                'usadas ' + fmt(usadas) + ' + a pagar ' + fmt(L.he_a_pagar) + ' + no pagadas ' + fmt(L.he_no_pagadas) + ' + por decidir ' + fmt(L.he_por_decidir))
            + '</div><div class="cq-legend">'
            + '<span><i style="background:#7A8296"></i>Perdonado</span><span><i style="background:#3B5BDB"></i>Cubierto / usadas</span><span><i style="background:#D64535"></i>Pendiente</span>'
            + '<span><i style="background:#2F9E5E"></i>A pagar</span><span><i style="background:#C9CED9"></i>No pagadas</span><span><i style="background:#E0A030"></i>Por decidir</span>'
            + '</div></section>';

        // ── Día por día ────────────────────────────────────────────────
        h += '<section class="cq-dias"><div class="cq-eyebrow">Día por día: cada minuto con su destino</div><div class="cq-tabla-caja"><table class="cq-tabla">'
            + '<colgroup><col style="width:112px"><col style="width:152px"><col style="width:112px"><col style="width:112px"><col></colgroup>'
            + '<thead><tr><th>Día</th><th>Marcas</th><th class="cq-der">Deuda</th><th class="cq-der">Horas extra</th><th class="cq-destino">Destino</th></tr></thead><tbody>';
        (d.dias || []).forEach(function (x) {
            const marcas = (x.hora_entrada_real ? x.hora_entrada_real.substring(0, 5) : '—') + ' – ' + (x.hora_salida_real ? x.hora_salida_real.substring(0, 5) : '—');
            let destino = '';
            if (x.especial) destino += chip('Jornada especial', 'e');
            if (x.perdonado > 0.0083) destino += chip('Perdonado', 'p', fmt(x.perdonado));
            if (x.deuda > 0.0083) destino += (L.pendiente > 0.0083 ? chip('Deuda', 'd', fmt(x.deuda)) : chip('Cubierta con horas extra', 'c'));
            if (x.he_bruto > 0.0083) {
                if (x.estado_he === 'APROBADO') {
                    destino += chip('Aprobada', 'a', fmt(x.he_autorizados));
                    if (x.he_bruto - x.he_autorizados > 0.0083) destino += chip('No pagadas', 'n', fmt(x.he_bruto - x.he_autorizados));
                } else if (x.estado_he === 'RECHAZADO') destino += chip('No pagada', 'n');
                else destino += chip('Por decidir', 'x', fmt(x.he_bruto));
                if (x.excepcion) destino += chip('Decidida a mano', 'm');
            }
            h += '<tr><td>' + fechaLarga(x.fecha) + '</td><td class="cq-mono-td">' + marcas + '</td>'
                + '<td class="cq-mono-td cq-der ' + (x.deuda > 0.0083 ? 'cq-rojo' : '') + '">' + (x.deuda_bruta > 0.0083 ? fmt(x.deuda_bruta) : '') + '</td>'
                + '<td class="cq-mono-td cq-der">' + (x.he_bruto > 0.0083 ? fmt(x.he_bruto) : '') + '</td><td class="cq-destino"><div class="cq-chips">' + destino + '</div></td></tr>';
        });
        if (!(d.dias || []).length) h += '<tr><td colspan="5" class="cq-vacio">Sin días con deuda ni horas extra.</td></tr>';
        h += '</tbody></table></div></section>';
        el.innerHTML = h;
        document.getElementById('cq-chip').innerHTML = chipPolitica(d.politica);
        const btnQuitar = document.getElementById('cq-quitar');
        if (btnQuitar) btnQuitar.hidden = !(d.politica && puede);
        actualizarPreview();
    }

    function fact(t, v, s, cls) {
        return '<div class="cq-fact"><span class="cq-fact-t">' + t + '</span><span class="cq-valor ' + (cls || '') + '">' + v + '</span><span class="cq-fact-s">' + s + '</span></div>';
    }
    function fila(nombre, valor, bar, eq) {
        return '<div class="cq-lbl"><span>' + nombre + '</span><span class="cq-mono">' + valor + '</span></div><div class="cq-fila-bar">' + bar + '<div class="cq-eq">' + eq + '</div></div>';
    }
    function chip(t, tipo, num) { return '<span class="cq-chip cq-chip-' + tipo + '">' + esc(t) + (num ? ' <span class="cq-mono">' + num + '</span>' : '') + '</span>'; }
    function radio(sel) { return '<span class="cq-radio' + (sel ? ' cq-radio-on' : '') + '" aria-hidden="true"></span>'; }
    function opcion(codigo, titulo, saldo, saldoCls, texto) {
        const sel = estado.eleccion === codigo;
        return '<button type="button" class="cq-opt' + (sel ? ' cq-sel' : '') + '" aria-pressed="' + sel + '" onclick="window.cuadreElegir(\'' + codigo + '\')">'
            + '<span class="cq-opt-cab"><span class="cq-opt-t">' + titulo + '</span>' + radio(sel) + '</span>'
            + '<span class="cq-opt-saldo ' + (saldoCls || '') + '">' + saldo + '</span><span class="cq-opt-s">' + texto + '</span></button>';
    }
    function opcionPagar(sobran) {
        const sel = estado.eleccion === 'PAGAR';
        const b30 = Math.floor(sobran / 30) * 30, b60 = Math.floor(sobran / 60) * 60;
        // De mayor a menor: Todas, el bloque de media hora más grande, el de hora entera, y «Otra»
        let botones = boton(null, 'Todas');
        if (b30 > 0 && b30 !== b60 && b30 < sobran - 0.0083) botones += boton(b30, fmt(b30));
        if (b60 > 0 && b60 < sobran - 0.0083) botones += boton(b60, fmt(b60));
        botones += '<label class="cq-otra"><span class="visually-hidden">Otra cantidad de horas extra a pagar</span><input type="text" id="cq-otra" placeholder="Otra H:MM" oninput="window.cuadreOtra(this.value)" onclick="event.stopPropagation()"></label>';
        return '<div class="cq-opt cq-opt-pagar' + (sel ? ' cq-sel' : '') + '" onclick="window.cuadreElegir(\'PAGAR\', true)">'
            + '<span class="cq-opt-cab"><span class="cq-opt-t">Pagar horas extra: ¿cuántas?</span>' + radio(sel) + '</span>'
            + '<div class="cq-botones">' + botones + '</div>'
            + '<span class="cq-opt-s">«Todas» son las ' + fmt(sobran) + '. Lo que no se pague queda escrito como «no pagadas».</span></div>';
    }
    function boton(min, txt) {
        const act = (estado.eleccion === 'PAGAR' && ((min == null && estado.minutos == null) || (min != null && estado.minutos === min)));
        return '<button type="button" class="cq-bloque' + (act ? ' cq-bloque-act' : '') + '" aria-pressed="' + act + '" onclick="event.stopPropagation(); window.cuadreMinutos(' + (min == null ? 'null' : min) + ')">' + txt + '</button>';
    }

    function actualizarPreview() {
        const pv = document.getElementById('cq-preview'), btn = document.getElementById('cq-confirmar');
        if (!pv || !estado.data) return;
        const L = estado.data.libro, b = base(L);
        if (!estado.eleccion) { pv.innerHTML = ''; if (btn) btn.disabled = true; return; }
        let cub = b.cubre, pend = b.falta, perd = 0, pagar = 0, nopag = 0;
        if (estado.eleccion === 'CERO') { perd = b.falta; pend = 0; nopag = b.sobran; }
        else { pagar = (estado.minutos == null) ? b.sobran : Math.min(b.sobran, Math.max(0, estado.minutos)); nopag = b.sobran - pagar; }
        const saldo = pagar - pend;
        const vigente = esLaVigente();
        pv.innerHTML = '<section class="cq-preview"><div class="cq-eyebrow cq-eyebrow-azul">' + (vigente ? 'Así está decidido hoy' : 'Si confirmas') + '</div>'
            + '<div class="cq-pv-grid">'
            + pv1('Cubierto', fmt(cub)) + pv1('Perdonado ahora', fmt(perd)) + pv1('Pendiente', fmt(pend), pend > 0.0083 ? 'cq-rojo' : '')
            + pv1('A pagar', fmt(pagar), pagar > 0.0083 ? 'cq-verde' : '') + pv1('No pagadas', fmt(nopag)) + pv1('Saldo', signo(saldo) + fmt(saldo), saldo < -0.0083 ? 'cq-rojo' : (saldo > 0.0083 ? 'cq-verde' : ''))
            + '</div>'
            + '<div class="cq-pv-nota">Las marcas de mañana se recalculan solas con la misma decisión. Si aparece deuda nueva, vuelve a verse pendiente y te vuelve a preguntar.</div>'
            + (vigente ? '' : '<label class="cq-motivo">Motivo (opcional, queda en el registro)<textarea id="cq-motivo" rows="2"></textarea></label>') + '</section>';
        if (btn) btn.disabled = !puedeDecidir() || vigente;
    }
    function pv1(t, v, cls) { return '<div><span class="cq-pv-t">' + t + '</span><span class="cq-pv-v ' + (cls || '') + '">' + v + '</span></div>'; }

    window.cuadreElegir = function (codigo, soloSiNoEsta) {
        if (soloSiNoEsta && estado.eleccion === codigo) return;
        estado.eleccion = codigo;
        if (codigo === 'CERO') estado.minutos = null;
        render();
    };
    window.cuadreMinutos = function (min) { estado.eleccion = 'PAGAR'; estado.minutos = min; render(); };
    window.cuadreOtra = function (txt) {
        const t = String(txt || '').trim();
        const m = /^(\d{1,3})(?::(\d{1,2}))?$/.exec(t);
        if (!m) return;
        estado.eleccion = 'PAGAR';
        estado.minutos = parseInt(m[1], 10) * 60 + (m[2] ? parseInt(m[2], 10) : 0);
        actualizarPreview();
        document.querySelectorAll('#cq-cuerpo .cq-bloque').forEach(function (x) { x.classList.remove('cq-bloque-act'); x.setAttribute('aria-pressed', 'false'); });
    };

    window.cuadreConfirmar = async function () {
        if (!estado.eleccion) return;
        const btn = document.getElementById('cq-confirmar');
        if (btn) { btn.disabled = true; btn.textContent = 'Guardando…'; }
        const d = estado.data;
        const body = { empleado_id: estado.empleadoId, fecha_inicio: d.tramo.inicio, fecha_fin: d.tramo.fin, politica: estado.eleccion,
                       minutos_a_pagar: estado.eleccion === 'PAGAR' ? estado.minutos : null,
                       motivo: (document.getElementById('cq-motivo') || {}).value || null };
        try {
            const r = await fetch('/api/cuadre/politica/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token() }, body: JSON.stringify(body) });
            const j = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(j.detail || ('Error ' + r.status));
            estado.data = j; tomarPolitica(j);
            toast('Cuadre guardado: ' + (body.politica === 'CERO' ? 'todo a cero' : 'pagar horas extra'), 'success');
            // Orden del dueño (25-10-2026): al confirmar, la ventana se cierra y la grilla muestra el resultado
            const mEl = document.getElementById('modalCuadre');
            if (mEl) { const m = bootstrap.Modal.getInstance(mEl); if (m) m.hide(); }
            if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData({ silent: true });
        } catch (e) {
            toast('No se pudo guardar el cuadre: ' + e.message, 'danger');
        } finally {
            if (btn) { btn.textContent = 'Confirmar cuadre'; btn.disabled = !estado.eleccion || esLaVigente() || !puedeDecidir(); }
        }
    };

    window.cuadreQuitar = async function () {
        const d = estado.data;
        try {
            const r = await fetch('/api/cuadre/politica/?empleado_id=' + estado.empleadoId + '&fecha_inicio=' + d.tramo.inicio + '&fecha_fin=' + d.tramo.fin,
                { method: 'DELETE', headers: { 'Authorization': 'Bearer ' + token() } });
            const j = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(j.detail || ('Error ' + r.status));
            estado.data = j; tomarPolitica(j);
            toast('Política quitada: las horas quedan como estaban; decide de nuevo.', 'info');
            render();
            if (typeof window.loadMarcacionesData === 'function') window.loadMarcacionesData({ silent: true });
        } catch (e) { toast('No se pudo quitar la política: ' + e.message, 'danger'); }
    };

    window.cuadreAjusteManual = function () {
        const mEl = document.getElementById('modalCuadre');
        if (mEl) { const m = bootstrap.Modal.getInstance(mEl); if (m) m.hide(); }
        if (typeof window.openBatchApprovalModal === 'function') window.openBatchApprovalModal(estado.empleadoId, estado.nombre);
    };

    function estilos() {
        if (document.getElementById('cq-estilos')) return;
        const s = document.createElement('style');
        s.id = 'cq-estilos';
        const M = "'JetBrains Mono',ui-monospace,Consolas,monospace";
        s.textContent = ''
            // Ventana
            + '#modalCuadre .modal-dialog{max-width:900px}'
            + '#modalCuadre .modal-content{border:0;border-radius:16px;overflow:hidden;font-family:"Barlow","Segoe UI",system-ui,sans-serif;color:#141B2D;font-size:14px;line-height:1.45;box-shadow:0 24px 64px rgba(20,27,45,.22)}'
            + '#modalCuadre .modal-header{padding:24px 32px 20px;border-bottom:1px solid #E4E7EF;align-items:flex-start;gap:16px}'
            + '#modalCuadre .modal-body{padding:24px 32px 28px;display:flex;flex-direction:column;gap:28px}'
            + '#modalCuadre .modal-footer{padding:16px 32px;border-top:1px solid #E4E7EF;background:#FBFBFD;justify-content:space-between;gap:16px;flex-wrap:wrap}'
            + '#modalCuadre .modal-footer>*{margin:0}'
            + '.cq-cab{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}'
            + '.cq-nombre{margin:0;font-family:"Barlow Semi Condensed","Barlow",sans-serif;font-weight:700;font-size:24px;line-height:1.15;letter-spacing:.01em;color:#141B2D}'
            + '.cq-sub{font-size:13px;color:#5B6478}'
            + '.cq-cab-der{display:flex;align-items:center;gap:12px;padding-top:4px}'
            + '.cq-cerrar{width:36px;height:36px;display:grid;place-items:center;border:1px solid #E4E7EF;border-radius:10px;background:#fff;color:#3A4256;padding:0;cursor:pointer}'
            + '.cq-cerrar:hover{background:#F6F7FA}'
            + '.cq-eyebrow{font-size:11px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:#6B7489}'
            + '.cq-eyebrow-azul{color:#1B2F8F}'
            + '.cq-mono{font-family:' + M + ';font-weight:600}'
            + '.cq-rojo{color:#B42318!important}.cq-verde{color:#1E6B3E!important}'
            // Política
            + '.cq-chip-pol{display:inline-flex;align-items:center;gap:8px;height:28px;padding:0 12px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap;vertical-align:middle}'
            + '.cq-chip-pol i{width:6px;height:6px;border-radius:50%;display:inline-block}'
            + '.cq-pol-nada{background:#F1F2F6;border:1px solid #E1E4EB;color:#4A5368}.cq-pol-nada i{background:#A15C07}'
            + '.cq-pol-cero{background:#EEF1FB;border:1px solid #D5DBF3;color:#1B2F8F}.cq-pol-cero i{background:#1B2F8F}'
            + '.cq-pol-pagar{background:#E8F4EC;border:1px solid #CDE6D6;color:#1E6B3E}.cq-pol-pagar i{background:#1E6B3E}'
            // Hechos
            + '.cq-facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}'
            + '.cq-fact{background:#F6F7FA;border:1px solid #ECEEF4;border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:6px}'
            + '.cq-fact-t{font-size:12px;font-weight:500;color:#5B6478}.cq-fact-s{font-size:12px;color:#6B7489}'
            + '.cq-valor{font-family:' + M + ';font-size:22px;font-weight:600;letter-spacing:-.01em;color:#141B2D}'
            // Pasos
            + '.cq-pasos{display:flex;flex-direction:column}'
            + '.cq-paso{display:grid;grid-template-columns:32px minmax(0,1fr);column-gap:16px}'
            + '.cq-rail{display:flex;flex-direction:column;align-items:center}'
            + '.cq-num{width:32px;height:32px;border-radius:50%;background:#EEF1FB;color:#1B2F8F;display:grid;place-items:center;font-weight:700;font-size:14px;flex:none}'
            + '.cq-num-ok{background:#E8F4EC;color:#1E6B3E}'
            + '.cq-linea{flex:1;width:2px;background:#E4E7EF;margin:6px 0}'
            + '.cq-paso-cuerpo{display:flex;flex-direction:column;gap:12px;padding-top:5px;min-width:0}'
            + '.cq-paso-1{gap:4px;padding-bottom:24px}'
            + '.cq-titulo-fila{display:flex;align-items:center;gap:10px;flex-wrap:wrap}'
            + '.cq-titulo{font-size:15px;font-weight:600;color:#141B2D}'
            + '.cq-badge{display:inline-flex;align-items:center;height:20px;padding:0 8px;border-radius:999px;background:#E8F4EC;color:#1E6B3E;font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase}'
            + '.cq-texto{font-size:14px;color:#3A4256}'
            + '.cq-nota{font-size:13px;color:#5B6478;display:flex;align-items:center;gap:8px;flex-wrap:wrap}'
            // Opciones
            + '.cq-opciones{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}'
            + '.cq-opt{text-align:left;border:1px solid #DDE1EA;border-radius:12px;padding:16px;background:#fff;display:flex;flex-direction:column;gap:8px;cursor:pointer;color:#141B2D;font-family:inherit;transition:border-color .12s,background .12s}'
            + '.cq-opt:hover{border-color:#B9C2D8}'
            + '.cq-sel,.cq-sel:hover{border:1.5px solid #1B2F8F;padding:15.5px;background:#F4F6FD}'
            + '.cq-opt-cab{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%}'
            + '.cq-opt-t{font-size:15px;font-weight:600}'
            + '.cq-opt-saldo{font-family:' + M + ';font-size:18px;font-weight:500;color:#141B2D}'
            + '.cq-opt-s{font-size:13px;color:#5B6478}'
            + '.cq-radio{width:18px;height:18px;border-radius:50%;border:1.5px solid #B8BFCC;box-sizing:border-box;flex:none;display:grid;place-items:center}'
            + '.cq-radio-on{border:0;background:#1B2F8F}.cq-radio-on::after{content:"";width:6px;height:6px;border-radius:50%;background:#fff}'
            + '.cq-botones{display:flex;gap:8px}'
            + '.cq-botones>*{flex:1 1 0;min-width:0}'
            + '.cq-bloque{height:36px;border:1px solid #CBD2E1;border-radius:8px;background:#fff;color:#1B2F8F;font-family:' + M + ';font-size:12px;font-weight:500;cursor:pointer;padding:0 4px;white-space:nowrap}'
            + '.cq-bloque:hover{border-color:#1B2F8F}'
            + '.cq-bloque-act,.cq-bloque-act:hover{background:#1B2F8F;border-color:#1B2F8F;color:#fff;font-weight:600}'
            + '.cq-botones>.cq-otra{display:block;margin:0;flex:1.3 1 0}'
            + '.cq-otra input{width:100%;box-sizing:border-box;height:36px;border:1px solid #CBD2E1;border-radius:8px;padding:0 6px;text-align:center;font-family:' + M + ';font-size:12px;background:#fff;color:#141B2D}'
            + '.cq-otra input:focus,.cq-motivo textarea:focus{outline:2px solid #C7D0F3;border-color:#1B2F8F}'
            // Vista previa
            + '#cq-preview:empty{display:none}'
            + '.cq-preview{border:1px solid #D5DBF3;background:#F7F9FE;border-radius:12px;padding:16px 20px;display:flex;flex-direction:column;gap:14px}'
            + '.cq-pv-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr))}'
            + '.cq-pv-grid>div{display:flex;flex-direction:column;gap:4px;padding:0 12px;border-left:1px solid #DDE3F5}'
            + '.cq-pv-grid>div:first-child{padding-left:0;border-left:0}.cq-pv-grid>div:last-child{padding-right:0}'
            + '.cq-pv-t{font-size:12px;color:#5B6478}.cq-pv-v{font-family:' + M + ';font-size:16px;font-weight:600;color:#141B2D}'
            + '.cq-pv-nota{font-size:13px;color:#5B6478;padding-top:12px;border-top:1px solid #DDE3F5}'
            + '.cq-motivo{display:flex;flex-direction:column;gap:6px;font-size:12px;font-weight:500;color:#3A4256;margin:0}'
            + '.cq-motivo textarea{font-family:inherit;font-size:14px;color:#141B2D;border:1px solid #CDD3E2;border-radius:8px;padding:8px 12px;background:#fff;resize:vertical}'
            // Libro de hoy
            + '.cq-ident{display:flex;flex-direction:column;gap:14px}'
            + '.cq-filas{display:grid;grid-template-columns:168px minmax(0,1fr);column-gap:20px;row-gap:16px;align-items:start}'
            + '.cq-lbl{display:flex;flex-direction:column;gap:2px;font-size:13px;font-weight:600}.cq-lbl .cq-mono{font-weight:400;color:#3A4256}'
            + '.cq-fila-bar{display:flex;flex-direction:column;gap:8px;padding-top:3px;min-width:0}'
            + '.cq-bar{display:flex;gap:2px;height:12px;border-radius:6px;overflow:hidden;background:#EEF0F5}'
            + '.cq-seg{min-width:4px}'
            + '.cq-eq{font-family:' + M + ';font-size:12px;color:#5B6478}'
            + '.cq-legend{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;padding-top:12px;border-top:1px solid #EEF0F5}'
            + '.cq-legend span{display:inline-flex;align-items:center;gap:8px;font-size:12px;color:#5B6478}'
            + '.cq-legend i{width:10px;height:10px;border-radius:3px;display:inline-block;flex:none}'
            // Día por día
            + '.cq-dias{display:flex;flex-direction:column;gap:12px}'
            + '.cq-tabla-caja{border:1px solid #E4E7EF;border-radius:12px;overflow:auto}'
            + '.cq-tabla{width:100%;min-width:640px;border-collapse:collapse;table-layout:fixed;font-size:13.5px;margin:0}'
            + '.cq-tabla th{height:36px;padding:0 16px;background:#F6F7FA;border-bottom:1px solid #E4E7EF;font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#6B7489;text-align:left;white-space:nowrap}'
            + '.cq-tabla td{height:40px;padding:6px 16px;border-top:1px solid #EEF0F5;color:#141B2D;vertical-align:middle}'
            + '.cq-tabla tbody tr:first-child td{border-top:0}'
            + '.cq-tabla .cq-der{text-align:right}.cq-tabla .cq-destino{padding-left:28px}'
            + '.cq-mono-td{font-family:' + M + ';font-size:13px;color:#3A4256;white-space:nowrap}'
            + '.cq-vacio{color:#6B7489;text-align:center}'
            + '.cq-chips{display:flex;flex-wrap:wrap;gap:6px}'
            + '.cq-chip{display:inline-flex;align-items:center;gap:6px;height:24px;padding:0 10px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}'
            + '.cq-chip .cq-mono{font-weight:500}'
            + '.cq-chip-d{background:#FDEDEB;color:#B42318}'
            + '.cq-chip-p{background:#EEF0F4;color:#4A5368}'
            + '.cq-chip-c{background:#EDF1FE;color:#2C46B8}'
            + '.cq-chip-a{background:#E8F4EC;color:#1E6B3E}'
            + '.cq-chip-n{background:#F1F2F6;color:#5B6478}'
            + '.cq-chip-x{background:#FDF3E3;color:#A15C07}'
            + '.cq-chip-e{background:#F1F2F6;border:1px solid #E1E4EB;color:#4A5368}'
            + '.cq-chip-m{background:#EEF1FB;color:#1B2F8F}'
            // Pie
            + '.cq-pie-izq,.cq-pie-der{display:flex;align-items:center;gap:12px}.cq-pie-izq{gap:4px}'
            + '.cq-link{height:40px;padding:0 12px;border:0;border-radius:8px;background:transparent;color:#3A4256;font-family:inherit;font-size:14px;font-weight:500;cursor:pointer}'
            + '.cq-link:hover{background:#F1F2F6}'
            + '.cq-link-rojo{color:#B42318;position:relative;margin-left:9px}'
            + '.cq-link-rojo::before{content:"";position:absolute;left:-7px;top:10px;bottom:10px;width:1px;background:#E4E7EF}'
            + '.cq-link-rojo:hover{background:#FDEDEB}'
            + '.cq-btn-sec{height:40px;padding:0 20px;border:1px solid #D6DAE3;border-radius:10px;background:#fff;color:#141B2D;font-family:inherit;font-size:14px;font-weight:600;cursor:pointer}'
            + '.cq-btn-sec:hover{background:#F6F7FA}'
            + '.cq-btn-pri{height:40px;padding:0 22px;border:0;border-radius:10px;background:#1B2F8F;color:#fff;font-family:inherit;font-size:14px;font-weight:600;cursor:pointer}'
            + '.cq-btn-pri:hover{background:#14236B}'
            + '.cq-btn-pri:disabled{opacity:.4;cursor:not-allowed;background:#1B2F8F}'
            // Pantallas angostas
            + '@media (max-width:760px){'
            + '#modalCuadre .modal-header,#modalCuadre .modal-footer{padding-left:16px;padding-right:16px}#modalCuadre .modal-body{padding:20px 16px;gap:24px}'
            + '#modalCuadre .modal-header{flex-wrap:wrap;position:relative;row-gap:10px}.cq-cab{flex:1 1 100%;padding-right:48px}.cq-cab-der{flex:1 1 100%;padding-top:0}'
            + '.cq-cerrar{position:absolute;top:16px;right:16px}.cq-chip-pol{white-space:normal;height:auto;min-height:28px;padding:4px 12px}'
            + '.cq-facts{grid-template-columns:repeat(2,minmax(0,1fr))}.cq-opciones{grid-template-columns:1fr}'
            + '.cq-pv-grid{grid-template-columns:repeat(3,minmax(0,1fr));row-gap:12px}.cq-pv-grid>div:nth-child(4){padding-left:0;border-left:0}'
            + '.cq-filas{grid-template-columns:1fr;row-gap:8px}.cq-legend{grid-template-columns:repeat(3,minmax(0,1fr))}.cq-botones{flex-wrap:wrap}.cq-botones>*{flex:1 1 40%}}';
        document.head.appendChild(s);
    }

    window.openCuadreModal = async function (empleadoId, nombre) {
        estilos();
        estado.empleadoId = Number(empleadoId); estado.nombre = nombre || ''; estado.eleccion = null; estado.minutos = null; estado.data = null;
        let existing = document.getElementById('modalCuadre');
        if (existing) existing.remove();
        const html = '<div class="modal fade" id="modalCuadre" tabindex="-1" aria-labelledby="modalCuadreLabel"><div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content">'
            + '<div class="modal-header"><div class="cq-cab"><div class="cq-eyebrow">Cuadre del tramo</div><h5 class="cq-nombre" id="modalCuadreLabel">' + esc(nombre) + '</h5><div id="cq-sub" class="cq-sub"></div></div>'
            + '<div class="cq-cab-der"><div id="cq-chip"></div><button type="button" class="cq-cerrar" data-bs-dismiss="modal" aria-label="Cerrar">'
            + '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M2 2l10 10M12 2L2 12"></path></svg></button></div></div>'
            + '<div class="modal-body" id="cq-cuerpo"><div class="cq-sub">Cargando el libro de minutos…</div></div>'
            + '<div class="modal-footer">'
            + '<div class="cq-pie-izq"><button type="button" class="cq-link" onclick="window.cuadreAjusteManual()">Ajuste manual por día</button>'
            + '<button type="button" class="cq-link cq-link-rojo" id="cq-quitar" hidden onclick="window.cuadreQuitar()">Quitar política</button></div>'
            + '<div class="cq-pie-der"><button type="button" class="cq-btn-sec" data-bs-dismiss="modal">Cerrar</button>'
            + '<button type="button" class="cq-btn-pri" id="cq-confirmar" disabled onclick="window.cuadreConfirmar()">Confirmar cuadre</button></div>'
            + '</div></div></div></div>';
        document.body.insertAdjacentHTML('beforeend', html);
        const el = document.getElementById('modalCuadre');
        el.addEventListener('hidden.bs.modal', function () { el.remove(); });
        new bootstrap.Modal(el).show();
        try {
            const data = await cargar(estado.empleadoId);
            if (data.es_bolsa) {
                document.getElementById('cq-cuerpo').innerHTML = '<div class="alert alert-info mb-0">Esta persona tiene Bolsa Flexible: su balance se gestiona en la columna de la bolsa al cierre.</div>';
                return;
            }
            estado.data = data; tomarPolitica(data);
            document.getElementById('cq-sub').textContent = 'Tramo ' + fechaDMA(data.tramo.inicio) + ' al ' + fechaDMA(data.tramo.fin) + ' · se recalcula cada día con las marcas nuevas'
                + (data.tolerancia_minutos > 0 ? (' · tolerancia ' + data.tolerancia_minutos + ' min por día') : '');
            render();
        } catch (e) {
            document.getElementById('cq-cuerpo').innerHTML = '<div class="alert alert-danger mb-0">No se pudo cargar el cuadre: ' + esc(e.message) + '</div>';
        }
    };
})();
