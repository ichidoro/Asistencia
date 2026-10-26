// ── Cuadre del tramo: una sola ventana para la deuda, las horas extra y los perdonazos ──────────────
// Regla del dueño (25-10-2026): la deuda se cubre sola con las horas extra; después hay UNA pregunta con dos
// respuestas: «llevar todo a cero» (lo que falte se perdona, lo que sobre no se paga) o «pagar horas extra:
// ¿cuántas?» (todas, un bloque o una cantidad; el resto queda escrito como no pagado). La decisión se guarda
// como política del tramo y la aplicación la vuelve a repartir sola cada vez que cambian las marcas.
// Los textos van con comillas y concatenación: el minificador del servidor come los espacios de las
// plantillas `...` anidadas dentro de ${}.
(function () {
    'use strict';

    function fmt(min) {
        const v = Number(min) || 0;
        if (typeof window.formatExactMinutesToTime === 'function') return window.formatExactMinutesToTime(Math.abs(v));
        const seg = Math.round(Math.abs(v) * 60);
        const h = Math.floor(seg / 3600), m = Math.floor((seg % 3600) / 60), s = seg % 60;
        return h + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    }
    function signo(v) { return v > 0.0083 ? '+' : (v < -0.0083 ? '-' : ''); }
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

    function barra(partes) {
        const total = partes.reduce((s, p) => s + Math.max(0, p.v), 0);
        if (total <= 0) return '<div class="cq-bar cq-bar-vacia">0:00:00</div>';
        let html = '<div class="cq-bar">';
        partes.forEach(function (p) {
            if (p.v <= 0.0083) return;
            const w = Math.max(6, (p.v / total) * 100);
            html += '<div class="cq-seg" style="width:' + w + '%;background:' + p.c + '" title="' + esc(p.t) + ' ' + fmt(p.v) + '">' + (w >= 12 ? fmt(p.v) : '') + '</div>';
        });
        return html + '</div>';
    }

    function chipPolitica(pol) {
        if (!pol) return '<span class="badge rounded-pill text-bg-light border">Política del tramo: por decidir</span>';
        const quien = pol.decidido_por ? (' · ' + esc(pol.decidido_por)) : '';
        if (pol.politica === 'CERO') return '<span class="badge rounded-pill text-bg-dark">Llevar todo a cero' + quien + '</span>';
        const cuanto = (pol.minutos_a_pagar == null) ? 'todas las que sobren' : ('hasta ' + fmt(pol.minutos_a_pagar));
        return '<span class="badge rounded-pill text-bg-success">Pagar horas extra: ' + cuanto + quien + '</span>';
    }

    function render() {
        const d = estado.data, L = d.libro, b = base(L);
        const el = document.getElementById('cq-cuerpo');
        if (!el) return;
        const puede = puedeDecidir();

        // ── Hechos ─────────────────────────────────────────────────────
        let h = '<div class="cq-facts">'
            + fact('Dejó de trabajar', fmt(L.deuda_bruta), (L.perdonado > 0.0083 ? ('ya perdonado ' + fmt(L.perdonado)) : 'sin perdonazos'))
            + fact('Horas extra trabajadas', fmt(L.he_trabajadas), (L.he_por_decidir > 0.0083 ? (fmt(L.he_por_decidir) + ' por decidir') : 'todas con decisión'))
            + fact('Deuda pendiente hoy', fmt(L.pendiente), L.pendiente > 0.0083 ? 'en rojo en la grilla' : 'nada pendiente', L.pendiente > 0.0083 ? 'cq-rojo' : 'cq-verde')
            + fact('Saldo hoy', signo(L.saldo) + fmt(L.saldo), 'a pagar − pendiente', L.saldo < -0.0083 ? 'cq-rojo' : (L.saldo > 0.0083 ? 'cq-verde' : ''))
            + '</div>';

        // ── Paso 1: cubrir (automático) ────────────────────────────────
        h += '<div class="cq-paso"><div class="cq-num cq-num-ok">1</div><div>'
            + '<div class="cq-titulo">Cubrir la deuda con horas extra <span class="badge text-bg-success">automático</span></div>'
            + '<div class="cq-texto">De las <b>' + fmt(b.disp) + '</b> trabajadas de más, <b>' + fmt(b.cubre) + '</b> cubren la deuda. '
            + (b.falta > 0.0083 ? ('Falta por cubrir <b class="cq-rojo">' + fmt(b.falta) + '</b>.') : ('Sobran <b>' + fmt(b.sobran) + '</b>.'))
            + (L.perdon_cuadre > 0.0083 ? (' Ya perdonado por el cuadre a cero: ' + fmt(L.perdon_cuadre) + '.') : '')
            + '</div></div></div>';

        // ── Paso 2: la única pregunta ──────────────────────────────────
        h += '<div class="cq-paso"><div class="cq-num">2</div><div style="min-width:0">';
        if (b.sobran > 0.0083) {
            h += '<div class="cq-titulo">Una sola pregunta: sobran ' + fmt(b.sobran) + ', ¿qué hacemos?</div>'
                + '<div class="cq-opciones">'
                + opcion('CERO', 'Llevar todo a cero', 'saldo 0:00:00', 'No se paga nada. Las ' + fmt(b.sobran) + ' quedan escritas como «no pagadas».')
                + opcionPagar(b.sobran)
                + '</div>';
        } else if (b.falta > 0.0083) {
            h += '<div class="cq-titulo">Una sola pregunta: falta ' + fmt(b.falta) + ' por cubrir, ¿qué hacemos?</div>'
                + '<div class="cq-opciones">'
                + opcion('CERO', 'Llevar todo a cero', 'saldo 0:00:00', 'Se perdonan ' + fmt(b.falta) + ', con tu nombre y la fecha en el registro.')
                + opcion('PAGAR', 'Dejar la deuda', 'saldo -' + fmt(b.falta), 'Se descuenta en el cierre. No hay horas que pagar.')
                + '</div>';
        } else if (b.deuda > 0.0083 || b.disp > 0.0083) {
            h += '<div class="cq-titulo">Las horas extra cubren exactamente la deuda</div>'
                + '<div class="cq-opciones">' + opcion('CERO', 'Confirmar: todo a cero', 'saldo 0:00:00', 'Queda registrado que se cubrió con horas extra.') + '</div>';
        } else {
            h += '<div class="cq-titulo">Nada que cuadrar</div><div class="cq-texto">No hay deuda ni horas extra en el tramo.</div>';
        }
        if (d.politica) h += '<div class="cq-texto text-muted mt-2">Decisión vigente: ' + chipPolitica(d.politica) + ' Elige otra opción para cambiarla, o «Quitar política» para volver a empezar.</div>';
        if (!puede) h += '<div class="cq-texto text-muted mt-2">Solo puedes ver el cuadre; decidirlo requiere el permiso de horas extra.</div>';
        h += '</div></div>';

        // ── Vista previa de la decisión ─────────────────────────────────
        h += '<div id="cq-preview"></div>';

        // ── Resultado actual (las sumas siempre cuadran) ───────────────
        h += '<div class="cq-ident"><div class="cq-eyebrow">Hoy, con lo decidido hasta ahora</div>'
            + fila('Deuda ' + fmt(L.deuda_bruta), barra([{ v: L.perdonado, c: '#6b7280', t: 'perdonado' }, { v: L.cubierto, c: '#2563eb', t: 'cubierto' }, { v: L.pendiente, c: '#dc2626', t: 'pendiente' }]),
                '= perdonado ' + fmt(L.perdonado) + ' + cubierto ' + fmt(L.cubierto) + ' + pendiente ' + fmt(L.pendiente))
            + fila('Horas extra ' + fmt(L.he_trabajadas), barra([{ v: L.he_usadas_deuda + L.he_usadas_inasistencia, c: '#2563eb', t: 'usadas' }, { v: L.he_a_pagar, c: '#16a34a', t: 'a pagar' }, { v: L.he_no_pagadas, c: '#9ca3af', t: 'no pagadas' }, { v: L.he_por_decidir, c: '#d97706', t: 'por decidir' }]),
                '= usadas ' + fmt(L.he_usadas_deuda + L.he_usadas_inasistencia) + ' + a pagar ' + fmt(L.he_a_pagar) + ' + no pagadas ' + fmt(L.he_no_pagadas) + ' + por decidir ' + fmt(L.he_por_decidir))
            + '<div class="cq-legend"><span><i style="background:#6b7280"></i>Perdonado</span><span><i style="background:#2563eb"></i>Cubierto / usadas</span><span><i style="background:#dc2626"></i>Pendiente</span><span><i style="background:#16a34a"></i>A pagar</span><span><i style="background:#9ca3af"></i>No pagadas</span><span><i style="background:#d97706"></i>Por decidir</span></div>'
            + '</div>';

        // ── Día por día ────────────────────────────────────────────────
        h += '<div class="cq-eyebrow">Día por día: cada minuto con su destino</div><div class="table-responsive"><table class="table table-sm cq-tabla"><thead><tr><th>Día</th><th>Marcas</th><th class="text-end">Deuda</th><th class="text-end">Horas extra</th><th>Destino</th></tr></thead><tbody>';
        (d.dias || []).forEach(function (x) {
            const marcas = (x.hora_entrada_real ? x.hora_entrada_real.substring(0, 5) : '—') + ' · ' + (x.hora_salida_real ? x.hora_salida_real.substring(0, 5) : '—');
            let destino = '';
            if (x.especial) destino += chip('jornada especial', 'light');
            if (x.perdonado > 0.0083) destino += chip('perdonado ' + fmt(x.perdonado), 'secondary');
            if (x.deuda > 0.0083) destino += (L.pendiente > 0.0083 ? chip('deuda ' + fmt(x.deuda), 'danger') : chip('cubierta con horas extra', 'primary'));
            if (x.he_bruto > 0.0083) {
                if (x.estado_he === 'APROBADO') {
                    destino += chip('aprobada ' + fmt(x.he_autorizados), 'success');
                    if (x.he_bruto - x.he_autorizados > 0.0083) destino += chip('no pagadas ' + fmt(x.he_bruto - x.he_autorizados), 'secondary');
                } else if (x.estado_he === 'RECHAZADO') destino += chip('no pagada', 'secondary');
                else destino += chip('por decidir', 'warning');
                if (x.excepcion) destino += chip('decidida a mano', 'dark');
            }
            h += '<tr><td class="text-nowrap">' + fechaLarga(x.fecha) + '</td><td class="text-nowrap font-monospace">' + marcas + '</td>'
                + '<td class="text-end font-monospace ' + (x.deuda > 0.0083 ? 'cq-rojo' : '') + '">' + (x.deuda_bruta > 0.0083 ? fmt(x.deuda_bruta) : '') + '</td>'
                + '<td class="text-end font-monospace">' + (x.he_bruto > 0.0083 ? fmt(x.he_bruto) : '') + '</td><td>' + destino + '</td></tr>';
        });
        if (!(d.dias || []).length) h += '<tr><td colspan="5" class="text-muted">Sin días con deuda ni horas extra.</td></tr>';
        h += '</tbody></table></div>';
        el.innerHTML = h;
        document.getElementById('cq-chip').innerHTML = chipPolitica(d.politica);
        const btnQuitar = document.getElementById('cq-quitar');
        if (btnQuitar) btnQuitar.hidden = !(d.politica && puede);
        actualizarPreview();
    }

    function fact(t, v, s, cls) {
        return '<div class="cq-fact"><small>' + t + '</small><span class="cq-valor ' + (cls || '') + '">' + v + '</span><small>' + s + '</small></div>';
    }
    function fila(lbl, bar, eq) { return '<div class="cq-fila"><span class="cq-lbl">' + lbl + '</span><div>' + bar + '<div class="cq-eq">' + eq + '</div></div></div>'; }
    function chip(t, c) { return '<span class="badge rounded-pill text-bg-' + c + ' me-1 mb-1 fw-normal">' + esc(t) + '</span>'; }
    function opcion(codigo, titulo, saldo, texto) {
        const sel = estado.eleccion === codigo ? ' cq-sel' : '';
        return '<button type="button" class="cq-opt' + sel + '" onclick="window.cuadreElegir(\'' + codigo + '\')"><span class="cq-opt-t">' + titulo + '</span><span class="font-monospace">' + saldo + '</span><small>' + texto + '</small></button>';
    }
    function opcionPagar(sobran) {
        const sel = estado.eleccion === 'PAGAR' ? ' cq-sel' : '';
        const b30 = Math.floor(sobran / 30) * 30, b60 = Math.floor(sobran / 60) * 60;
        let botones = boton(null, 'Todas · ' + fmt(sobran));
        if (b60 > 0 && b60 < sobran - 0.0083) botones += boton(b60, fmt(b60));
        if (b30 > 0 && b30 !== b60 && b30 < sobran - 0.0083) botones += boton(b30, fmt(b30));
        botones += '<span class="cq-otra"><input type="text" class="form-control form-control-sm" id="cq-otra" placeholder="Otra: H:MM" style="width:110px" oninput="window.cuadreOtra(this.value)"></span>';
        return '<div class="cq-opt' + sel + '" onclick="window.cuadreElegir(\'PAGAR\', true)"><span class="cq-opt-t">Pagar horas extra: ¿cuántas?</span><div class="cq-botones">' + botones + '</div><small>Lo que no se pague queda escrito como «no pagadas».</small></div>';
    }
    function boton(min, txt) {
        const act = (estado.eleccion === 'PAGAR' && ((min == null && estado.minutos == null) || (min != null && estado.minutos === min))) ? ' btn-primary' : ' btn-outline-primary';
        return '<button type="button" class="btn btn-sm' + act + '" onclick="event.stopPropagation(); window.cuadreMinutos(' + (min == null ? 'null' : min) + ')">' + txt + '</button>';
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
        pv.innerHTML = '<div class="cq-preview"><div class="cq-eyebrow">' + (vigente ? 'Así está decidido hoy' : 'Si confirmas') + '</div>'
            + '<div class="cq-pv-grid">'
            + pv1('Cubierto', fmt(cub)) + pv1('Perdonado ahora', fmt(perd)) + pv1('Pendiente', fmt(pend), pend > 0.0083 ? 'cq-rojo' : '')
            + pv1('A pagar', fmt(pagar), pagar > 0.0083 ? 'cq-verde' : '') + pv1('No pagadas', fmt(nopag)) + pv1('Saldo', signo(saldo) + fmt(saldo), saldo < -0.0083 ? 'cq-rojo' : (saldo > 0.0083 ? 'cq-verde' : ''))
            + '</div>'
            + '<div class="cq-texto">Las marcas de mañana se recalculan solas con la misma decisión. Si aparece deuda nueva, vuelve a verse pendiente y te vuelve a preguntar.</div>'
            + (vigente ? '' : '<textarea class="form-control form-control-sm mt-2" id="cq-motivo" rows="1" placeholder="Motivo (opcional, queda en el registro)"></textarea>') + '</div>';
        if (btn) btn.disabled = !puedeDecidir() || vigente;
    }
    function pv1(t, v, cls) { return '<div><small>' + t + '</small><span class="font-monospace ' + (cls || '') + '">' + v + '</span></div>'; }

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
        document.querySelectorAll('#cq-cuerpo .cq-botones .btn').forEach(function (x) { x.classList.remove('btn-primary'); x.classList.add('btn-outline-primary'); });
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
            render();
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
        s.textContent = '.cq-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}'
            + '.cq-fact{background:#f1f5f9;border-radius:8px;padding:8px 12px;display:grid;gap:2px}.cq-fact small{color:#64748b;font-size:.72rem}'
            + '.cq-valor{font-family:ui-monospace,Consolas,monospace;font-size:1.15rem;font-weight:600}.cq-rojo{color:#b91c1c}.cq-verde{color:#15803d}'
            + '.cq-paso{display:grid;grid-template-columns:30px 1fr;gap:10px;margin:10px 0}.cq-num{width:30px;height:30px;border-radius:50%;background:#e0e7ff;color:#3730a3;display:grid;place-items:center;font-weight:700}'
            + '.cq-num-ok{background:#dcfce7;color:#15803d}.cq-titulo{font-weight:600;font-size:.95rem}.cq-texto{font-size:.85rem;color:#334155}'
            + '.cq-opciones{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin-top:8px}'
            + '.cq-opt{text-align:left;border:1px solid #d9deea;border-radius:8px;padding:10px 12px;background:#fff;display:grid;gap:4px;cursor:pointer;color:#1b2235}'
            + '.cq-opt small{color:#64748b;font-size:.75rem}.cq-opt-t{font-weight:600}.cq-sel{border-color:#2f4bd6;box-shadow:inset 0 0 0 1px #2f4bd6}'
            + '.cq-botones{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.cq-otra input{display:inline-block}'
            + '.cq-ident{margin:14px 0;display:grid;gap:8px}.cq-eyebrow{font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;color:#64748b;font-weight:600;margin-top:8px}'
            + '.cq-fila{display:grid;grid-template-columns:160px 1fr;gap:10px;align-items:center}.cq-lbl{font-weight:600;font-size:.85rem}'
            + '.cq-bar{display:flex;height:20px;border-radius:6px;overflow:hidden;border:1px solid #d9deea;background:#eef1f7}.cq-bar-vacia{display:grid;place-items:center;font-size:.72rem;color:#64748b}'
            + '.cq-seg{display:grid;place-items:center;color:#fff;font-size:.68rem;font-family:ui-monospace,Consolas,monospace;white-space:nowrap;overflow:hidden}'
            + '.cq-eq{font-family:ui-monospace,Consolas,monospace;font-size:.72rem;color:#64748b}.cq-legend{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:.72rem;color:#64748b}'
            + '.cq-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}'
            + '.cq-tabla{font-size:.8rem}.cq-tabla td,.cq-tabla th{vertical-align:middle}'
            + '.cq-preview{background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px 12px;margin-top:8px}.cq-pv-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px}'
            + '.cq-pv-grid small{display:block;color:#64748b;font-size:.7rem}.cq-pv-grid span{font-weight:600}'
            + '@media (max-width:560px){.cq-fila{grid-template-columns:1fr}}';
        document.head.appendChild(s);
    }

    window.openCuadreModal = async function (empleadoId, nombre) {
        estilos();
        estado.empleadoId = Number(empleadoId); estado.nombre = nombre || ''; estado.eleccion = null; estado.minutos = null; estado.data = null;
        let existing = document.getElementById('modalCuadre');
        if (existing) existing.remove();
        const html = '<div class="modal fade" id="modalCuadre" tabindex="-1" aria-labelledby="modalCuadreLabel"><div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content">'
            + '<div class="modal-header"><div><div class="cq-eyebrow" style="margin:0">Cuadre del tramo</div><h5 class="modal-title mb-0" id="modalCuadreLabel">' + esc(nombre) + '</h5><div id="cq-sub" class="text-muted small"></div></div>'
            + '<div class="ms-auto me-3" id="cq-chip"></div><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button></div>'
            + '<div class="modal-body" id="cq-cuerpo"><div class="text-muted p-3">Cargando el libro de minutos…</div></div>'
            + '<div class="modal-footer justify-content-between flex-wrap gap-2">'
            + '<div class="d-flex gap-2"><button type="button" class="btn btn-outline-secondary btn-sm" onclick="window.cuadreAjusteManual()">Ajuste manual por día</button>'
            + '<button type="button" class="btn btn-outline-danger btn-sm" id="cq-quitar" hidden onclick="window.cuadreQuitar()">Quitar política</button></div>'
            + '<div class="d-flex gap-2"><button type="button" class="btn btn-light" data-bs-dismiss="modal">Cerrar</button>'
            + '<button type="button" class="btn btn-primary" id="cq-confirmar" disabled onclick="window.cuadreConfirmar()">Confirmar cuadre</button></div>'
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
            document.getElementById('cq-sub').textContent = 'Tramo ' + data.tramo.inicio + ' al ' + data.tramo.fin + ' · se recalcula cada día con las marcas nuevas'
                + (data.tolerancia_minutos > 0 ? (' · tolerancia ' + data.tolerancia_minutos + ' min por día') : '');
            render();
        } catch (e) {
            document.getElementById('cq-cuerpo').innerHTML = '<div class="alert alert-danger mb-0">No se pudo cargar el cuadre: ' + esc(e.message) + '</div>';
        }
    };
})();
