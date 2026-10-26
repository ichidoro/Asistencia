// ── Cuadre del tramo: una sola ventana para la deuda, las horas extra y los perdonazos ──────────────
// Regla del dueño (25-10-2026): la deuda se cubre sola con las horas extra; después hay UNA pregunta con dos
// respuestas: «llevar todo a cero» (lo que falte se perdona, lo que sobre no se paga) o «pagar horas extra:
// ¿cuántas?» (todas, un bloque o una cantidad; el resto queda escrito como no pagado). La decisión se guarda
// como política del tramo y la aplicación la vuelve a repartir sola cada vez que cambian las marcas.
// Estructura elegida por el dueño (25-10-2026, «C · línea del tramo», hecha con la skill Impeccable): arriba los días
// del tramo (horas extra hacia arriba, deuda hacia abajo; tocar un día muestra su detalle), abajo la decisión y la
// cuenta con «Hoy» y «Si confirmas» lado a lado. La lógica (base, política, guardar, quitar) no cambió.
// Los textos van con comillas y concatenación: el minificador del servidor come los espacios de las
// plantillas `...` anidadas dentro de ${}.
(function () {
    'use strict';

    const MENOS = '−';
    const C = { rojo: '#D2463A', azul: '#3D63DD', verde: '#2E9E6B', gris: '#C3CADA', pizarra: '#7D87A6', ambar: '#E09A2A' };

    function fmt(min) {
        const v = Number(min) || 0;
        if (typeof window.formatExactMinutesToTime === 'function') return window.formatExactMinutesToTime(Math.abs(v));
        const seg = Math.round(Math.abs(v) * 60);
        const h = Math.floor(seg / 3600), m = Math.floor((seg % 3600) / 60), s = seg % 60;
        return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    }
    function signo(v) { return v > 0.0083 ? '+' : (v < -0.0083 ? MENOS : ''); }
    function hay(v) { return Math.abs(Number(v) || 0) > 0.0083; }
    function token() {
        return (typeof AuthService !== 'undefined' && typeof AuthService.getToken === 'function') ? AuthService.getToken() : localStorage.getItem('access_token');
    }
    function puedeDecidir() {
        return typeof AuthService === 'undefined' || typeof AuthService.hasPermission !== 'function' || AuthService.hasPermission('marcaciones.horas_extras');
    }
    function esc(t) { return String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
    const DIAS = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
    const LETRA = ['D', 'L', 'M', 'M', 'J', 'V', 'S'];
    function fechaObj(f) { return new Date(String(f).substring(0, 10) + 'T00:00:00'); }
    function fechaLarga(f) { const d = fechaObj(f); return DIAS[d.getDay()] + ' ' + String(d.getDate()).padStart(2, '0') + '-' + String(d.getMonth() + 1).padStart(2, '0'); }
    function fechaDMA(f) { const p = String(f || '').substring(0, 10).split('-'); return p.length === 3 ? (p[2] + '-' + p[1] + '-' + p[0]) : String(f || ''); }
    // Los nombres se guardan en mayúsculas; en la ventana se leen como nombre propio y la labor como frase
    function titulo(s) { return String(s || '').toLowerCase().replace(/(^|[\s\-'])([a-záéíóúñü])/g, function (m, a, b) { return a + b.toUpperCase(); }); }
    function frase(s) { const t = String(s || '').trim().toLowerCase(); return t ? t.charAt(0).toUpperCase() + t.slice(1) : ''; }
    function marcas(x) {
        const e = x.hora_entrada_real ? String(x.hora_entrada_real).substring(0, 5) : '';
        const s = x.hora_salida_real ? String(x.hora_salida_real).substring(0, 5) : '';
        return (e || s) ? ((e || '—') + ' – ' + (s || '—')) : 'Sin marcas';
    }
    const ESTADOS = { OK: 'Jornada normal', ATRASO: 'Atraso', SALIDA_ADELANTADA: 'Salida adelantada', INASISTENCIA: 'Inasistencia', FALTA: 'Inasistencia',
        LIBRE: 'Día libre', FERIADO: 'Feriado', JORNADA_ESPECIAL: 'Jornada especial', EXTRA: 'Jornada especial', PENDIENTE: 'Sin calcular todavía',
        INASISTENCIA_COMPENSADA: 'Inasistencia compensada', JORNADA_COMPENSATORIA: 'Jornada compensatoria' };
    function nombreEstado(e) { if (!e) return 'Sin registro'; return ESTADOS[e] || frase(String(e).replace(/_/g, ' ')); }
    function toast(msg, tipo) { if (typeof showToast === 'function') showToast(msg, tipo || 'info'); }

    const estado = { data: null, eleccion: null, minutos: null, empleadoId: null, nombre: '', diaSel: null, motivo: '' };

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
    // La cuenta se plantea como si se decidiera desde cero: sin los perdonazos de la guía (el servidor la simula en
    // sin_guia), así la vista previa de cualquier opción es exacta aunque ya haya una decisión guardada.
    function base(d) {
        const S = (d && d.sin_guia) || (d && d.libro) || {};
        const disp = Math.max(0, (S.he_trabajadas || 0) - (S.he_usadas_inasistencia || 0));
        const deuda = Math.max(0, (S.deuda_neta || 0));
        const cubre = Math.min(disp, deuda);
        return { disp, deuda, cubre, sobran: disp - cubre, falta: deuda - cubre };
    }
    function propuesta(d) { return (d && d.propuesta) || { dias: [], total: 0, queda_no_perdonable: 0 }; }
    function guiaCambio(d) {
        const p = d && d.politica;
        if (!p || p.politica !== 'CERO') return false;
        const g = d.guia_activa, actual = g ? ((g.minutos_marca || 0) + (g.minutos_cuadre || 0)) : 0;
        return Math.abs((propuesta(d).total || 0) - actual) > 0.0083;
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
        if (p.politica === 'CERO') return !guiaCambio(estado.data);
        if (p.politica !== 'PAGAR') return true;
        const pm = (p.minutos_a_pagar == null) ? null : Number(p.minutos_a_pagar);
        return pm === estado.minutos;
    }

    function textoPolitica(pol) {
        if (!pol) return '<span class="cq-t-ambar">por decidir</span>';
        const quien = pol.decidido_por ? (' · ' + esc(pol.decidido_por)) : '';
        if (pol.politica === 'CERO') return '<span class="cq-t-azul">' + ((estado.data && estado.data.guia_activa) ? 'perdonar atrasos y salidas' : 'sin pagar lo que sobra') + quien + '</span>';
        const cuanto = (pol.minutos_a_pagar == null) ? 'todas las que sobren' : ('hasta ' + fmt(pol.minutos_a_pagar));
        return '<span class="cq-t-verde">pagar horas extra: ' + cuanto + quien + '</span>';
    }

    // ── Línea del tramo ───────────────────────────────────────────────
    function destinoDia(x, L) {
        const partes = [];
        if (x.especial) partes.push({ t: 'Jornada especial', c: C.pizarra });
        if (hay(x.perdonado)) partes.push({ t: 'Perdonado ' + fmt(x.perdonado), c: C.pizarra });
        if (hay(x.deuda)) partes.push(hay(L.pendiente) ? { t: 'Deuda ' + fmt(x.deuda) + ', pendiente', c: C.rojo } : { t: 'Deuda ' + fmt(x.deuda) + ', cubierta con horas extra', c: C.azul });
        if (hay(x.he_bruto)) {
            if (x.estado_he === 'APROBADO' || (x.especial && !x.estado_he)) {
                const aut = x.he_autorizados || x.he_bruto;
                partes.push({ t: 'Horas extra ' + fmt(x.he_bruto) + ', aprobadas ' + fmt(aut), c: C.verde });
                if (x.he_bruto - aut > 0.0083) partes.push({ t: 'No pagadas ' + fmt(x.he_bruto - aut), c: C.gris });
            } else if (x.estado_he === 'RECHAZADO') partes.push({ t: 'Horas extra ' + fmt(x.he_bruto) + ', no pagadas', c: C.gris });
            else partes.push({ t: 'Horas extra ' + fmt(x.he_bruto) + ', por decidir', c: C.ambar });
            if (x.excepcion) partes.push({ t: 'Decidida a mano', c: '#1B2F8F' });
        }
        return partes;
    }
    function barrasDia(x, L, escala) {
        const px = function (v) { return v >= 0.5 ? Math.max(3, Math.round(v * escala)) : 0; };
        let arriba = '', abajo = '';
        if (hay(x.he_bruto)) {
            if (x.estado_he === 'APROBADO' || (x.especial && !x.estado_he)) {
                const aut = Math.min(x.he_bruto, x.he_autorizados || x.he_bruto);
                arriba = '<i style="height:' + px(x.he_bruto - aut) + 'px;background:' + C.gris + '"></i><i style="height:' + px(aut) + 'px;background:' + C.verde + '"></i>';
            } else {
                arriba = '<i style="height:' + px(x.he_bruto) + 'px;background:' + (x.estado_he === 'RECHAZADO' ? C.gris : C.ambar) + '"></i>';
            }
        }
        if (hay(x.deuda) || hay(x.perdonado)) {
            abajo = (hay(x.deuda) ? '<i style="height:' + px(x.deuda) + 'px;background:' + (hay(L.pendiente) ? C.rojo : C.azul) + '"></i>' : '')
                + (hay(x.perdonado) ? '<i style="height:' + px(x.perdonado) + 'px;background:' + C.pizarra + '"></i>' : '');
        }
        return { arriba: arriba, abajo: abajo };
    }
    function lineaTramo(d, L) {
        const cal = d.calendario || [];
        if (!cal.length) return '';
        const max = cal.reduce(function (m, x) { return Math.max(m, x.he_bruto || 0, (x.deuda || 0) + (x.perdonado || 0)); }, 30);
        const escala = 70 / max;
        let tira = '';
        // Días que perdona (o perdonó) la guía: se marcan en la línea cuando la opción está elegida
        const enPlan = {};
        if (estado.eleccion === 'CERO') propuesta(d).dias.forEach(function (f) { enPlan[f.fecha] = true; });
        cal.forEach(function (x, i) {
            const f = fechaObj(x.fecha);
            const libre = !x.estado || x.estado === 'LIBRE' || x.estado === 'FERIADO';
            const marca = (x.estado === 'INASISTENCIA' || x.estado === 'FALTA') ? 'Ina' : (x.estado === 'FERIADO' ? 'Fer' : (x.especial ? 'JE' : ''));
            const b = barrasDia(x, L, escala);
            const sel = estado.diaSel === i;
            const ayuda = fechaLarga(x.fecha) + ': ' + nombreEstado(x.estado) + (hay(x.deuda) ? ', deuda ' + fmt(x.deuda) : '') + (hay(x.he_bruto) ? ', horas extra ' + fmt(x.he_bruto) : '');
            tira += '<button type="button" class="cq-dia' + (libre ? ' cq-dia-libre' : '') + (sel ? ' cq-dia-sel' : '') + (enPlan[x.fecha] ? ' cq-dia-plan' : '') + '" aria-pressed="' + sel + '" aria-label="' + esc(ayuda) + '" title="' + esc(ayuda) + '" onclick="window.cuadreDia(' + i + ')">'
                + '<span class="cq-arriba">' + b.arriba + '</span><span class="cq-eje"></span><span class="cq-abajo">' + b.abajo + '</span>'
                + '<span class="cq-dlab"><span>' + LETRA[f.getDay()] + '</span><b>' + f.getDate() + '</b><em class="' + (marca === 'Ina' ? 'cq-t-rojo' : '') + '">' + marca + '</em></span></button>';
        });
        const conMinutos = (d.dias || []);
        let lista = '';
        conMinutos.forEach(function (x) {
            const partes = destinoDia(x, L).map(function (p) { return '<span class="cq-dest"><i style="background:' + p.c + '"></i>' + esc(p.t) + '</span>'; }).join('');
            lista += '<tr><td>' + fechaLarga(x.fecha) + '</td><td class="cq-sec">' + esc(marcas(x)) + '</td><td class="cq-der">' + (hay(x.deuda_bruta) ? fmt(x.deuda_bruta) : '') + '</td><td class="cq-der">' + (hay(x.he_bruto) ? fmt(x.he_bruto) : '') + '</td><td><div class="cq-dests">' + partes + '</div></td></tr>';
        });
        return '<section class="cq-linea">'
            + '<div class="cq-linea-cab"><h3 class="cq-h3">Los ' + cal.length + ' días del tramo</h3>'
            + '<div class="cq-totales"><span>Trabajó de más <b class="cq-t-ambar">' + fmt(L.he_trabajadas) + '</b></span><span>Debe <b class="cq-t-rojo">' + fmt(L.deuda_bruta) + '</b></span></div></div>'
            + '<div class="cq-tira-caja"><div class="cq-tira" style="grid-template-columns:repeat(' + cal.length + ',minmax(22px,1fr))">' + tira + '</div></div>'
            + '<div class="cq-dia-detalle" id="cq-dia-detalle" aria-live="polite">' + detalleDia(L) + '</div>'
            + '<div class="cq-leyenda"><span><i style="background:' + C.ambar + '"></i>Horas extra por decidir</span><span><i style="background:' + C.verde + '"></i>Aprobadas</span>'
            + '<span><i style="background:' + C.gris + '"></i>No pagadas</span><span><i style="background:' + C.rojo + '"></i>Deuda pendiente</span>'
            + '<span><i style="background:' + C.azul + '"></i>Deuda cubierta</span><span><i style="background:' + C.pizarra + '"></i>Perdonado</span>'
            + '<span><i class="cq-sw-libre"></i>Libre o feriado</span></div>'
            + (conMinutos.length ? ('<details class="cq-lista"><summary>Ver la lista de días con deuda u horas extra (' + conMinutos.length + ')</summary>'
                + '<div class="cq-lista-caja"><table class="cq-tabla"><colgroup><col style="width:96px"><col style="width:120px"><col style="width:92px"><col style="width:92px"><col></colgroup>'
                + '<thead><tr><th>Día</th><th>Marcas</th><th class="cq-der">Deuda</th><th class="cq-der">Horas extra</th><th>Destino</th></tr></thead><tbody>' + lista + '</tbody></table></div></details>') : '')
            + '</section>';
    }
    function detalleDia(L) {
        const cal = (estado.data && estado.data.calendario) || [];
        const x = (estado.diaSel != null) ? cal[estado.diaSel] : null;
        if (!x) return '<span class="cq-sec">Toca un día para ver sus marcas y el destino de sus minutos.</span>';
        const partes = destinoDia(x, L);
        return '<div class="cq-dd-cab"><b>' + fechaLarga(x.fecha) + '</b><span class="cq-sec">' + esc(nombreEstado(x.estado)) + ' · ' + esc(marcas(x)) + '</span></div>'
            + (partes.length ? ('<div class="cq-dests">' + partes.map(function (p) { return '<span class="cq-dest"><i style="background:' + p.c + '"></i>' + esc(p.t) + '</span>'; }).join('') + '</div>')
                : '<span class="cq-sec">Sin deuda ni horas extra este día.</span>');
    }

    // ── Decisión ──────────────────────────────────────────────────────
    function radio(sel) { return '<span class="cq-radio' + (sel ? ' cq-radio-on' : '') + '" aria-hidden="true"></span>'; }
    function opcion(codigo, titulo, texto) {
        const sel = estado.eleccion === codigo;
        return '<button type="button" role="radio" aria-checked="' + sel + '" class="cq-opt' + (sel ? ' cq-sel' : '') + '" onclick="window.cuadreElegir(\'' + codigo + '\')">'
            + radio(sel) + '<span class="cq-opt-t">' + titulo + '</span><span></span><span class="cq-opt-s">' + texto + '</span></button>';
    }
    function opcionPagar(sobran) {
        const sel = estado.eleccion === 'PAGAR';
        const b30 = Math.floor(sobran / 30) * 30, b60 = Math.floor(sobran / 60) * 60;
        // De mayor a menor: Todas, el bloque de media hora más grande, el de hora entera, y «Otra»
        let botones = boton(null, 'Todas');
        if (b30 > 0 && b30 !== b60 && b30 < sobran - 0.0083) botones += boton(b30, fmt(b30));
        if (b60 > 0 && b60 < sobran - 0.0083) botones += boton(b60, fmt(b60));
        botones += '<label class="cq-otra"><span class="visually-hidden">Otra cantidad de horas extra a pagar</span><input type="text" id="cq-otra" placeholder="Otra H:MM" oninput="window.cuadreOtra(this.value)" onclick="event.stopPropagation()"></label>';
        return '<div role="radio" aria-checked="' + sel + '" tabindex="0" class="cq-opt' + (sel ? ' cq-sel' : '') + '" onclick="window.cuadreElegir(\'PAGAR\', true)" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){event.preventDefault();window.cuadreElegir(\'PAGAR\', true);}">'
            + radio(sel) + '<span class="cq-opt-t">Pagar horas extra</span><span></span>'
            + '<div class="cq-seg">' + botones + '</div><span></span>'
            + '<span class="cq-opt-s">«Todas» son las ' + fmt(sobran) + '. Lo que no se pague queda escrito como no pagado.</span></div>';
    }
    function boton(min, txt) {
        const act = (estado.eleccion === 'PAGAR' && ((min == null && estado.minutos == null) || (min != null && estado.minutos === min)));
        return '<button type="button" class="cq-bloque' + (act ? ' cq-bloque-act' : '') + '" aria-pressed="' + act + '" onclick="event.stopPropagation(); window.cuadreMinutos(' + (min == null ? 'null' : min) + ')">' + txt + '</button>';
    }
    function decision(d, L, b) {
        const puede = puedeDecidir();
        let h = '<section class="cq-decision">';
        if (b.sobran > 0.0083) {
            h += '<h3 class="cq-h3 cq-h3-g">¿Qué hacemos con las ' + fmt(b.sobran) + ' que sobran?</h3>'
                + '<p class="cq-p">Las horas extra cubren primero la deuda: ' + fmt(b.cubre) + ' de ' + fmt(b.disp) + '. Eso es automático.</p>'
                + '<div class="cq-opciones" role="radiogroup">' + opcion('CERO', 'No pagar las que sobran', 'Las ' + fmt(b.sobran) + ' que sobran quedan sin pagar. Saldo 00:00:00.') + opcionPagar(b.sobran) + '</div>';
        } else if (b.falta > 0.0083) {
            const prop = propuesta(d);
            h += '<h3 class="cq-h3 cq-h3-g">Falta cubrir ' + fmt(b.falta) + ', ¿qué hacemos?</h3>'
                + '<p class="cq-p">' + (hay(b.disp) ? ('Las ' + fmt(b.disp) + ' de horas extra pagan primero el exceso de colación y los permisos, después los atrasos y por último las salidas adelantadas. ') : 'No hay horas extra para pagar la deuda. ') + 'Eso es automático.</p>';
            if (hay(prop.total)) {
                h += '<div class="cq-opciones" role="radiogroup">'
                    + opcion('CERO', 'Perdonar atrasos y salidas', 'Se perdonan ' + fmt(prop.total) + ' en ' + prop.dias.length + (prop.dias.length === 1 ? ' día. ' : ' días. ')
                        + (hay(prop.queda_no_perdonable) ? ('Quedan ' + fmt(prop.queda_no_perdonable) + ' de exceso de colación y permisos como deuda: no se perdonan.') : 'La cuenta queda en cero.'))
                    + opcion('PAGAR', 'Dejar la deuda', 'Se descuenta en el cierre. No hay horas que pagar.') + '</div>';
                if (estado.eleccion === 'CERO') h += listaPerdon(prop);
            } else {
                h += '<p class="cq-nota">Lo que falta es exceso de colación o permisos: no se perdona.</p>'
                    + '<div class="cq-opciones cq-opciones-1" role="radiogroup">' + opcion('PAGAR', 'Dejar la deuda', 'Se descuenta en el cierre. No hay horas que pagar.') + '</div>';
            }
        } else if (b.deuda > 0.0083 || b.disp > 0.0083) {
            h += '<h3 class="cq-h3 cq-h3-g">Las horas extra cubren justo la deuda</h3>'
                + '<div class="cq-opciones cq-opciones-1" role="radiogroup">' + opcion('CERO', 'Confirmar: todo a cero', 'Queda registrado que se cubrió con horas extra.') + '</div>';
        } else {
            h += '<h3 class="cq-h3 cq-h3-g">Nada que cuadrar</h3><p class="cq-p">No hay deuda ni horas extra en el tramo.</p>';
        }
        if (estado.eleccion && !esLaVigente() && puede) {
            h += '<label class="cq-motivo">Motivo<input type="text" id="cq-motivo" placeholder="Opcional, queda en el registro" value="' + esc(estado.motivo) + '" oninput="window.cuadreMotivo(this.value)"></label>';
        }
        if (d.aviso_inasistencia) {
            const av = d.aviso_inasistencia;
            h += '<p class="cq-aviso">Las horas extra pagan primero los atrasos y salidas, y por eso no alcanzan para compensar la inasistencia del '
                + fechaLarga(av.fecha) + ' (' + fmt(av.minutos_inasistencia) + '). Si se perdonaran los atrasos y salidas, sobrarían ' + fmt(av.libres_perdonando) + ', suficientes para compensarla.</p>';
        }
        if (d.politica) {
            const cuando = d.politica.decidido_en ? (' el ' + fechaDMA(d.politica.decidido_en) + ' ' + String(d.politica.decidido_en).substring(11, 16)) : '';
            h += '<p class="cq-nota">Decidido' + cuando + ': ' + textoPolitica(d.politica) + '. Elige otra opción para cambiarlo, o «Quitar política» para volver a empezar. Al cambiarlo, los perdonazos de esta decisión se deshacen solos.</p>';
            if (guiaCambio(d)) h += '<p class="cq-aviso">La cuenta cambió desde que se decidió: llegaron marcas nuevas o corregidas. Revisa la lista y confirma de nuevo.</p>';
        }
        if (!puede) h += '<p class="cq-nota">Solo puedes ver el cuadre; decidirlo requiere el permiso de horas extra.</p>';
        return h + '</section>';
    }

    // Lista de los días que perdona la guía, para que quien confirma vea exactamente qué pasa con cada uno
    const EFECTO = { pasa_a_ok: 'Se perdona y el día pasa a OK', marca: 'Se perdona con la marca del interruptor',
        parcial: 'Se perdona solo una parte; el resto lo pagan las horas extra', tolerancia: 'Dentro de la tolerancia del turno; el día ya está en OK' };
    function listaPerdon(prop) {
        let filas = '';
        prop.dias.forEach(function (f) {
            const causa = (hay(f.atraso) && hay(f.salida)) ? 'Atraso y salida adelantada' : (hay(f.atraso) ? 'Atraso' : 'Salida adelantada');
            let efecto = EFECTO[f.efecto] || '';
            if (f.efecto === 'marca') {
                // El día tiene las dos causas y solo una se perdona: la otra la pagaron las horas extra y sigue marcada
                if (hay(f.salida) && !hay(f.atraso)) efecto = 'Se perdona la salida; el atraso lo pagan las horas extra y sigue marcado';
                else if (hay(f.atraso) && !hay(f.salida)) efecto = 'Se perdona el atraso; la salida la pagan las horas extra y sigue marcada';
            }
            filas += '<tr><td>' + fechaLarga(f.fecha) + '</td><td>' + causa + '</td><td class="cq-der">' + fmt(f.total) + '</td><td class="cq-sec">' + esc(efecto) + '</td></tr>';
        });
        return '<div class="cq-perdon"><div class="cq-perdon-cab"><b>Días que se perdonan</b><span class="cq-sec">' + prop.dias.length + (prop.dias.length === 1 ? ' día · ' : ' días · ') + fmt(prop.total) + '</span></div>'
            + '<div class="cq-lista-caja"><table class="cq-tabla cq-tabla-perdon"><colgroup><col style="width:96px"><col style="width:170px"><col style="width:92px"><col></colgroup>'
            + '<thead><tr><th>Día</th><th>Causa</th><th class="cq-der">Perdonado</th><th>Qué pasa</th></tr></thead><tbody>' + filas + '</tbody></table></div>'
            + '<p class="cq-nota">El exceso de colación y los permisos nunca se perdonan. Las horas extra pagan primero lo que no se perdona.</p></div>';
    }

    // ── Cuenta: Hoy y Si confirmas lado a lado ─────────────────────────
    function cuentaSi(d, L, b) {
        if (!estado.eleccion) return null;
        let cub = b.cubre, pend = b.falta, perdAhora = 0, pagar = 0, nopag = 0;
        if (estado.eleccion === 'CERO') {
            // Solo se perdonan atrasos y salidas (lo que dice la guía del servidor); colación y permisos quedan como deuda
            const prop = propuesta(d);
            if (hay(b.falta)) { perdAhora = prop.total || 0; pend = prop.queda_no_perdonable || 0; }
            nopag = b.sobran;
        } else { pagar = (estado.minutos == null) ? b.sobran : Math.min(b.sobran, Math.max(0, estado.minutos)); nopag = b.sobran - pagar; }
        const perdPrevio = d.sin_guia ? (d.sin_guia.perdonado || 0) : Math.max(0, (L.perdonado || 0) - (L.perdon_cuadre || 0));
        return { cubierto: cub, perdonado: perdPrevio + perdAhora, pendiente: pend, a_pagar: pagar, no_pagadas: nopag, por_decidir: 0, saldo: pagar - pend };
    }
    function cuenta(d, L, b) {
        const vigente = esLaVigente();
        const hoy = { cubierto: L.cubierto, perdonado: L.perdonado, pendiente: L.pendiente, a_pagar: L.he_a_pagar, no_pagadas: L.he_no_pagadas, por_decidir: L.he_por_decidir, saldo: L.saldo };
        const si = vigente ? hoy : cuentaSi(d, L, b);
        const filas = [['cubierto', 'Cubierto con horas extra', ''], ['perdonado', 'Perdonado', ''], ['pendiente', 'Pendiente', 'rojo'],
            ['a_pagar', 'A pagar', 'verde'], ['no_pagadas', 'No pagadas', ''], ['por_decidir', 'Horas extra por decidir', 'ambar']];
        let h = '<div class="cq-cuenta-cab"><span></span><span>Hoy</span><span class="cq-col-si">' + (vigente ? 'Decidido' : 'Si confirmas') + '</span></div>';
        filas.forEach(function (f) {
            const k = f[0], vh = hoy[k] || 0, vs = si ? (si[k] || 0) : null;
            const cls = function (v) { return (f[2] && hay(v)) ? ' cq-t-' + f[2] : ''; };
            const cambia = si && !vigente && Math.abs(vh - vs) > 0.0083;
            h += '<div class="cq-cuenta-fila' + (k === 'a_pagar' ? ' cq-cuenta-sep' : '') + '"><span>' + f[1] + '</span><span class="' + cls(vh) + '">' + fmt(vh) + '</span>'
                + '<span class="cq-col-si"><b class="' + (cambia ? 'cq-cambia' : '') + cls(vs || 0) + '">' + (si ? fmt(vs) : '—') + '</b></span></div>';
        });
        const sh = hoy.saldo || 0, ss = si ? si.saldo : null;
        const cs = function (v) { return v < -0.0083 ? ' cq-t-rojo' : (v > 0.0083 ? ' cq-t-verde' : ''); };
        h += '<div class="cq-cuenta-saldo"><span><b>Saldo del tramo</b><small>a pagar ' + MENOS + ' pendiente</small></span><span class="' + cs(sh) + '">' + signo(sh) + fmt(sh) + '</span>'
            + '<span class="cq-col-si"><b class="' + (si && !vigente && Math.abs(sh - ss) > 0.0083 ? 'cq-cambia' : '') + (si ? cs(ss) : '') + '">' + (si ? (signo(ss) + fmt(ss)) : '—') + '</b></span></div>';
        h += '<p class="cq-nota">' + (si ? 'Las marcas nuevas se recalculan con esta misma decisión. Si aparece deuda nueva, vuelve a preguntar.' : 'Elige una opción para ver cómo queda la cuenta.') + '</p>';
        return h;
    }
    function actualizarCuenta() {
        const el = document.getElementById('cq-cuenta'), btn = document.getElementById('cq-confirmar');
        if (!el || !estado.data) return;
        const L = estado.data.libro, b = base(estado.data);
        el.innerHTML = cuenta(estado.data, L, b);
        if (btn) btn.disabled = !estado.eleccion || !puedeDecidir() || esLaVigente();
    }

    function render() {
        const d = estado.data, L = d.libro, b = base(d);
        const el = document.getElementById('cq-cuerpo');
        if (!el) return;
        el.innerHTML = lineaTramo(d, L)
            + '<div class="cq-abajo-grid">' + decision(d, L, b) + '<section class="cq-cuenta" id="cq-cuenta" aria-live="polite"></section></div>';
        actualizarCuenta();
        const est = document.getElementById('cq-estado');
        if (est) est.innerHTML = textoPolitica(d.politica);
        const btnQuitar = document.getElementById('cq-quitar');
        if (btnQuitar) btnQuitar.hidden = !(d.politica && puedeDecidir());
    }

    window.cuadreDia = function (i) {
        estado.diaSel = (estado.diaSel === i) ? null : i;
        document.querySelectorAll('#cq-cuerpo .cq-dia').forEach(function (b, k) { const on = k === estado.diaSel; b.classList.toggle('cq-dia-sel', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); });
        const det = document.getElementById('cq-dia-detalle');
        if (det && estado.data) det.innerHTML = detalleDia(estado.data.libro);
    };
    window.cuadreElegir = function (codigo, soloSiNoEsta) {
        if (soloSiNoEsta && estado.eleccion === codigo) return;
        estado.eleccion = codigo;
        if (codigo === 'CERO') estado.minutos = null;
        render();
    };
    window.cuadreMinutos = function (min) { estado.eleccion = 'PAGAR'; estado.minutos = min; render(); };
    window.cuadreMotivo = function (v) { estado.motivo = String(v || ''); };
    window.cuadreOtra = function (txt) {
        const t = String(txt || '').trim();
        const m = /^(\d{1,3})(?::(\d{1,2}))?$/.exec(t);
        if (!m) return;
        estado.eleccion = 'PAGAR';
        estado.minutos = parseInt(m[1], 10) * 60 + (m[2] ? parseInt(m[2], 10) : 0);
        actualizarCuenta();
        document.querySelectorAll('#cq-cuerpo .cq-bloque').forEach(function (x) { x.classList.remove('cq-bloque-act'); x.setAttribute('aria-pressed', 'false'); });
    };

    window.cuadreConfirmar = async function () {
        if (!estado.eleccion) return;
        const btn = document.getElementById('cq-confirmar');
        if (btn) { btn.disabled = true; btn.textContent = 'Guardando…'; }
        const d = estado.data;
        const body = { empleado_id: estado.empleadoId, fecha_inicio: d.tramo.inicio, fecha_fin: d.tramo.fin, politica: estado.eleccion,
                       minutos_a_pagar: estado.eleccion === 'PAGAR' ? estado.minutos : null,
                       motivo: estado.motivo || null };
        try {
            const r = await fetch('/api/cuadre/politica/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token() }, body: JSON.stringify(body) });
            const j = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(j.detail || ('Error ' + r.status));
            estado.data = j; tomarPolitica(j); estado.motivo = '';
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
        s.textContent = ''
            // Ventana (identidad de la aplicación: azul marino, Barlow, cifras tabulares)
            + '#modalCuadre .modal-dialog{max-width:1080px}'
            + '#modalCuadre .modal-content{border:0;border-radius:12px;overflow:hidden;font-family:"Barlow","Segoe UI",system-ui,sans-serif;color:#0F1A3A;font-size:13.5px;line-height:1.5;font-variant-numeric:tabular-nums;box-shadow:0 24px 64px rgba(15,26,58,.24)}'
            + '#modalCuadre .modal-header{padding:22px 32px 18px;border-bottom:1px solid #E8EBF2;align-items:flex-start;gap:16px}'
            + '#modalCuadre .modal-body{padding:20px 32px 26px;display:flex;flex-direction:column;gap:24px}'
            + '#modalCuadre .modal-footer{padding:14px 32px;border-top:1px solid #E8EBF2;background:#FFFFFF;justify-content:space-between;gap:12px;flex-wrap:wrap}'
            + '#modalCuadre .modal-footer>*{margin:0}'
            + '#modalCuadre ::selection{background:#D9E1FA}'
            + '#modalCuadre button:focus-visible,#modalCuadre input:focus-visible,#modalCuadre [tabindex]:focus-visible,#modalCuadre summary:focus-visible{outline:2px solid #1B2F8F;outline-offset:2px}'
            + '.cq-cab{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}'
            + '.cq-nombre{margin:0;font-size:22px;font-weight:600;line-height:1.2;letter-spacing:-.005em;color:#0F1A3A}'
            + '.cq-labor{display:flex;align-items:center;gap:6px;font-size:14px;color:#2B3658;flex-wrap:wrap}.cq-labor b{font-weight:600}.cq-labor svg{flex:none}'
            + '.cq-tramo{font-size:13px;color:#5A6487}'
            + '.cq-cerrar{width:34px;height:34px;border:0;border-radius:8px;background:#F2F4F9;color:#2B3658;display:grid;place-items:center;padding:0;cursor:pointer;flex:none}'
            + '.cq-cerrar:hover{background:#E6EAF3}'
            + '.cq-t-rojo{color:#A3261C!important}.cq-t-ambar{color:#93600A!important}.cq-t-verde{color:#1E7A50!important}.cq-t-azul{color:#1B2F8F!important}'
            + '.cq-t-ambar,.cq-t-verde,.cq-t-azul{font-weight:600}'
            + '.cq-sec{color:#5A6487}'
            + '.cq-h3{margin:0;font-size:15px;font-weight:600;color:#0F1A3A;line-height:1.3}.cq-h3-g{font-size:16px}'
            + '.cq-p{margin:0;font-size:13px;color:#4A5578}'
            + '.cq-nota{margin:0;font-size:12.5px;color:#5A6487}'
            // Línea del tramo
            + '.cq-linea{display:flex;flex-direction:column;gap:10px}'
            + '.cq-linea-cab{display:flex;align-items:baseline;justify-content:space-between;gap:16px;flex-wrap:wrap}'
            + '.cq-totales{display:flex;gap:24px;font-size:13px;color:#5A6487}.cq-totales b{font-size:15px}'
            + '.cq-tira-caja{border:1px solid #E3E7F0;border-radius:10px;padding:12px 12px 6px;overflow-x:auto}'
            + '.cq-tira{display:grid;column-gap:4px;min-width:560px}'
            + '.cq-dia{display:flex;flex-direction:column;align-items:stretch;border:0;border-radius:6px;background:transparent;padding:0;cursor:pointer;font-family:inherit;color:inherit;transition:background-color .15s}'
            + '.cq-dia:hover{background:#F2F5FC}'
            + '.cq-dia-libre{background:#EEF1F6}.cq-dia-libre:hover{background:#E6EAF2}'
            + '.cq-dia-sel,.cq-dia-sel:hover{background:#E3E9FA;box-shadow:inset 0 0 0 1.5px #1B2F8F}'
            + '.cq-dia-plan{box-shadow:inset 0 0 0 1.5px #1B2F8F;background:repeating-linear-gradient(135deg,#F2F5FC,#F2F5FC 4px,#E6ECFA 4px,#E6ECFA 8px)}'
            + '.cq-dia-plan.cq-dia-sel{background:#E3E9FA}'
            + '.cq-aviso{margin:0;font-size:12.5px;color:#7A4B05;background:#FDF5E6;border-radius:8px;padding:8px 12px}'
            + '.cq-perdon{display:flex;flex-direction:column;gap:8px;margin-top:4px}'
            + '.cq-perdon-cab{display:flex;justify-content:space-between;align-items:baseline;gap:12px;font-size:13px}.cq-perdon-cab b{font-weight:600}'
            + '.cq-tabla-perdon{min-width:520px}'
            + '.cq-arriba,.cq-abajo{display:flex;flex-direction:column;align-items:center}'
            + '.cq-arriba{height:74px;justify-content:flex-end}.cq-abajo{height:62px;justify-content:flex-start}'
            + '.cq-arriba i,.cq-abajo i{display:block;width:60%;max-width:16px}'
            + '.cq-arriba i:first-child{border-radius:2px 2px 0 0}.cq-abajo i:last-child{border-radius:0 0 2px 2px}'
            + '.cq-eje{height:1px;background:#0F1A3A;opacity:.7}'
            + '.cq-dlab{display:flex;flex-direction:column;align-items:center;line-height:1.15;padding:4px 0 2px;font-size:10.5px;color:#2B3658}'
            + '.cq-dlab b{font-weight:600;font-size:11.5px}.cq-dlab em{font-style:normal;font-size:9.5px;height:11px;color:#5A6487}'
            + '.cq-dia-libre .cq-dlab{color:#8A93AE}'
            + '.cq-dia-detalle{min-height:44px;border-radius:10px;background:#F4F6FB;padding:10px 14px;display:flex;flex-direction:column;gap:6px;font-size:13px}'
            + '.cq-dd-cab{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}.cq-dd-cab b{font-weight:600}'
            + '.cq-dests{display:flex;flex-wrap:wrap;gap:4px 16px}'
            + '.cq-dest{display:inline-flex;align-items:center;gap:7px;color:#2B3658;font-size:12.5px}.cq-dest i{width:7px;height:7px;border-radius:50%;flex:none}'
            + '.cq-leyenda{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:11.5px;color:#5A6487}'
            + '.cq-leyenda span{display:inline-flex;align-items:center;gap:6px}.cq-leyenda i{width:8px;height:8px;border-radius:2px;display:inline-block}'
            + '.cq-sw-libre{background:#EEF1F6;box-shadow:inset 0 0 0 1px #D6DCE8}'
            + '.cq-lista summary{cursor:pointer;font-size:13px;font-weight:600;color:#1B2F8F;list-style-position:inside;padding:2px 0}'
            + '.cq-lista-caja{margin-top:8px;border:1px solid #E3E7F0;border-radius:10px;overflow:auto}'
            + '.cq-tabla{width:100%;min-width:620px;border-collapse:collapse;table-layout:fixed;font-size:13px;margin:0}'
            + '.cq-tabla th{height:32px;padding:0 14px;background:#F4F6FB;border-bottom:1px solid #E3E7F0;font-size:12px;font-weight:600;color:#5A6487;text-align:left}'
            + '.cq-tabla td{padding:7px 14px;border-top:1px solid #F0F2F7;vertical-align:middle}'
            + '.cq-tabla tbody tr:first-child td{border-top:0}.cq-tabla .cq-der{text-align:right}'
            // Decisión
            + '.cq-abajo-grid{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:28px;align-items:start}'
            + '.cq-decision{display:flex;flex-direction:column;gap:10px}'
            + '.cq-opciones{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.cq-opciones-1{grid-template-columns:minmax(0,1fr)}'
            + '.cq-opt{display:grid;grid-template-columns:16px minmax(0,1fr);column-gap:10px;row-gap:6px;align-content:start;text-align:left;padding:14px;border:1px solid #DDE2EC;border-radius:10px;background:#FFFFFF;cursor:pointer;font-family:inherit;color:#0F1A3A;transition:border-color .15s,background-color .15s}'
            + '.cq-opt:hover{border-color:#B5BFD6}'
            + '.cq-sel,.cq-sel:hover{border-color:#1B2F8F;background:#F7F9FE;box-shadow:0 0 0 3px rgba(27,47,143,.08)}'
            + '.cq-opt-t{font-size:14px;font-weight:600;line-height:1.3}.cq-opt-s{font-size:12.5px;color:#5A6487}'
            + '.cq-radio{width:16px;height:16px;border-radius:50%;border:1.5px solid #B9C1D2;box-sizing:border-box;margin-top:1px;display:grid;place-items:center}'
            + '.cq-radio-on{border:0;background:#1B2F8F}.cq-radio-on::after{content:"";width:6px;height:6px;border-radius:50%;background:#FFFFFF}'
            + '.cq-seg{display:flex;height:32px;border:1px solid #CDD4E3;border-radius:8px;overflow:hidden;background:#FFFFFF}'
            + '.cq-seg>*{flex:1 1 0;min-width:0}.cq-seg>.cq-otra{flex:1.3 1 0}'
            + '.cq-seg>*+*{border-left:1px solid #CDD4E3}'
            + '.cq-bloque{border:0;background:transparent;font-family:inherit;font-size:13px;color:#0F1A3A;cursor:pointer;padding:0 6px;white-space:nowrap}'
            + '.cq-bloque:hover{background:#F2F5FC}'
            + '.cq-bloque-act,.cq-bloque-act:hover{background:#1B2F8F;color:#FFFFFF;font-weight:600}'
            + '.cq-otra{display:flex;margin:0}'
            + '.cq-otra input{width:100%;border:0;outline:0;text-align:center;font-family:inherit;font-size:13px;color:#0F1A3A;background:transparent;padding:0 6px}'
            + '.cq-motivo{display:flex;align-items:center;gap:10px;font-size:12.5px;color:#2B3658;margin:2px 0 0}'
            + '.cq-motivo input{flex:1;height:32px;border:1px solid #D6DCE8;border-radius:8px;padding:0 10px;font-family:inherit;font-size:13px;color:#0F1A3A;background:#FFFFFF}'
            + '.cq-motivo input:focus{border-color:#1B2F8F;outline:2px solid #D9E1FA;outline-offset:0}'
            // Cuenta: Hoy y Si confirmas
            + '.cq-cuenta{display:flex;flex-direction:column}'
            + '.cq-cuenta-cab,.cq-cuenta-fila,.cq-cuenta-saldo{display:grid;grid-template-columns:minmax(0,1fr) 84px 100px;align-items:center;column-gap:8px}'
            + '.cq-cuenta-cab{font-size:12.5px;color:#5A6487;padding-bottom:6px;border-bottom:1px solid #0F1A3A}'
            + '.cq-cuenta-cab>span:nth-child(n+2){text-align:right}.cq-cuenta-cab .cq-col-si{color:#1B2F8F;font-weight:600}'
            + '.cq-cuenta-fila{min-height:30px;font-size:13px;border-bottom:1px solid #F0F2F7}'
            + '.cq-cuenta-fila>span:first-child{color:#4A5578}.cq-cuenta-fila>span:nth-child(n+2){text-align:right}'
            + '.cq-cuenta-sep{border-top:1px solid #E3E7F0}'
            + '.cq-col-si b{font-weight:600;padding:1px 6px;border-radius:4px}'
            + '.cq-cambia{background:#E9EEFB}'
            + '.cq-cuenta-saldo{padding:8px 0 6px;margin-top:2px;border-top:3px double #0F1A3A;font-size:16px;font-weight:700}'
            + '.cq-cuenta-saldo>span:first-child{display:flex;flex-direction:column;font-size:14px}.cq-cuenta-saldo small{font-size:11.5px;font-weight:400;color:#6B7596}'
            + '.cq-cuenta-saldo>span:nth-child(n+2){text-align:right}.cq-cuenta-saldo b{font-weight:700}'
            + '.cq-cuenta .cq-nota{padding-top:8px}'
            // Pie
            + '.cq-pie-izq,.cq-pie-der{display:flex;align-items:center;gap:8px}'
            + '.cq-link,.cq-btn-sec,.cq-btn-pri{white-space:nowrap}'
            + '.cq-link{height:36px;padding:0 10px;border:0;border-radius:8px;background:transparent;color:#2B3658;font-family:inherit;font-size:13.5px;font-weight:500;cursor:pointer}'
            + '.cq-link:hover{background:#F2F4F9}'
            + '.cq-link-rojo{color:#A3261C}.cq-link-rojo:hover{background:#FCEDEB}'
            + '.cq-btn-sec{height:36px;padding:0 16px;border:1px solid #D6DCE8;border-radius:8px;background:#FFFFFF;color:#0F1A3A;font-family:inherit;font-size:13.5px;font-weight:600;cursor:pointer}'
            + '.cq-btn-sec:hover{background:#F4F6FB}'
            + '.cq-btn-pri{height:36px;padding:0 18px;border:0;border-radius:8px;background:#1B2F8F;color:#FFFFFF;font-family:inherit;font-size:13.5px;font-weight:600;cursor:pointer}'
            + '.cq-btn-pri:hover{background:#14236B}.cq-btn-pri:disabled{opacity:.4;cursor:not-allowed;background:#1B2F8F}'
            // Pantallas angostas
            + '@media (max-width:860px){.cq-abajo-grid{grid-template-columns:minmax(0,1fr)}}'
            + '@media (max-width:640px){#modalCuadre .modal-header,#modalCuadre .modal-footer{padding-left:16px;padding-right:16px}#modalCuadre .modal-body{padding:16px;gap:20px}'
            + '.cq-opciones{grid-template-columns:minmax(0,1fr)}.cq-totales{gap:16px}.cq-pie-der{flex:1;justify-content:flex-end}}';
        document.head.appendChild(s);
    }

    window.openCuadreModal = async function (empleadoId, nombre) {
        estilos();
        estado.empleadoId = Number(empleadoId); estado.nombre = nombre || ''; estado.eleccion = null; estado.minutos = null; estado.data = null; estado.diaSel = null; estado.motivo = '';
        let existing = document.getElementById('modalCuadre');
        if (existing) existing.remove();
        const icono = '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="#5A6487" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="5" width="12" height="8.5" rx="1.5"></rect><path d="M6 5V3.8c0-.44.36-.8.8-.8h2.4c.44 0 .8.36.8.8V5M2 8.5h12"></path></svg>';
        const html = '<div class="modal fade" id="modalCuadre" tabindex="-1" aria-labelledby="modalCuadreLabel"><div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content">'
            + '<div class="modal-header"><div class="cq-cab"><h5 class="cq-nombre" id="modalCuadreLabel">' + esc(titulo(nombre)) + '</h5>'
            + '<div class="cq-labor" id="cq-labor">' + icono + '<span class="cq-sec">Cargando…</span></div>'
            + '<div class="cq-tramo" id="cq-sub"></div></div>'
            + '<button type="button" class="cq-cerrar" data-bs-dismiss="modal" aria-label="Cerrar"><svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M1.5 1.5l9 9M10.5 1.5l-9 9"></path></svg></button></div>'
            + '<div class="modal-body" id="cq-cuerpo"><div class="cq-sec">Cargando el tramo…</div></div>'
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
            const partes = [];
            if (data.cargo) partes.push('<b>' + esc(frase(data.cargo)) + '</b>');
            if (data.turno) partes.push('<span class="cq-sec">' + esc(data.turno) + '</span>');
            if (data.area) partes.push('<span class="cq-sec">' + esc(titulo(data.area)) + '</span>');
            document.getElementById('cq-labor').innerHTML = icono + (partes.length ? partes.join('<span class="cq-sec">·</span>') : '<span class="cq-sec">Sin labor registrada</span>');
            if (data.nombre) document.getElementById('modalCuadreLabel').textContent = titulo(data.nombre);
            if (data.es_bolsa) {
                document.getElementById('cq-cuerpo').innerHTML = '<div class="alert alert-info mb-0">Esta persona tiene Bolsa Flexible: su balance se gestiona en la columna de la bolsa al cierre.</div>';
                return;
            }
            estado.data = data; tomarPolitica(data);
            document.getElementById('cq-sub').innerHTML = 'Cuadre del tramo ' + fechaDMA(data.tramo.inicio) + ' al ' + fechaDMA(data.tramo.fin) + ' · <span id="cq-estado"></span>'
                + (data.tolerancia_minutos > 0 ? (' · tolerancia ' + data.tolerancia_minutos + ' min por día') : '');
            render();
        } catch (e) {
            document.getElementById('cq-cuerpo').innerHTML = '<div class="alert alert-danger mb-0">No se pudo cargar el cuadre: ' + esc(e.message) + '</div>';
        }
    };
})();
