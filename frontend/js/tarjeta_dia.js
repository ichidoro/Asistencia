/**
 * tarjeta_dia.js — Tarjeta del día y semana en el celular (etapa 3 del orden visual común; boceto aprobado
 * por el dueño el 28-10-2026).
 *
 * - Al tocar un día de la grilla aparece una tarjeta junto a él (en el celular sube desde abajo) en lugar de la
 *   ventana «Acciones de asistencia». Muestra el turno, el estado en palabras, las marcas del reloj con su equipo,
 *   la pausa, el +2, la compensación o la regla de marcaciones, y las acciones.
 * - Las acciones NO se deciden aquí: openAsistenciaActionModal (marcaciones_manuales.js) sigue calculando cuáles
 *   corresponden sobre los botones de la ventana de siempre (que queda oculta) y esta tarjeta muestra las visibles,
 *   con la misma función detrás de cada una.
 * - En el celular la grilla se ve por semana: se reutilizan las mismas celdas de la tabla (mismo clic, mismo
 *   doble clic, mismas siglas) y cada persona trae su saldo.
 * Las marcas se nombran siempre con la palabra completa: ENTRADA y SALIDA.
 */
(function () {
    'use strict';

    const esMovil = () => window.matchMedia('(max-width: 768px)').matches;
    const esc = (s) => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const DIAS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
    const DIAS_CORTOS = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
    const DIAS_SEM = ['DOM', 'LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB'];

    // ── Utilidades de formato ────────────────────────────────────────────────────────────────────────────
    const fechaObj = (f) => new Date(String(f).slice(0, 10) + 'T00:00:00');
    const ddmm = (f) => { const p = String(f).slice(0, 10).split('-'); return p[2] + '-' + p[1]; };
    const hhmm = (h) => (h ? String(h).slice(0, 5) : '--:--');
    const segDe = (h) => { const p = String(h || '0:0:0').split(':').map(n => parseInt(n, 10) || 0); return p[0] * 3600 + (p[1] || 0) * 60 + (p[2] || 0); };
    const absSeg = (m) => (m.fecha ? fechaObj(m.fecha).getTime() / 1000 : 0) + segDe(m.hora);

    /** Minutos (con decimales) → «2 min 42 s», «1 h 05 min». */
    function minSeg(min) {
        const t = Math.round(Math.max(0, Number(min) || 0) * 60);
        const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
        if (h) return h + ' h ' + m + ' min';
        if (!m) return s + ' s';
        return m + ' min' + (s ? ' ' + s + ' s' : '');
    }
    /** Minutos enteros → «4 h 17 min», «45 min», «8 h». */
    function hMin(min) {
        const t = Math.round(Math.max(0, Number(min) || 0));
        const h = Math.floor(t / 60), m = t % 60;
        if (!h) return m + ' min';
        return h + ' h' + (m ? ' ' + m + ' min' : '');
    }
    /** Horas con decimales → «7 h 28 min» (conMin) o «7 h 30». */
    function horas(hDec, conMin) {
        const t = Math.round(Math.max(0, Number(hDec) || 0) * 60);
        const h = Math.floor(t / 60), m = t % 60;
        if (conMin) return h ? (h + ' h ' + m + ' min') : (m + ' min');
        return h + ' h' + (m ? ' ' + String(m).padStart(2, '0') : '');
    }
    function frase(txt) { const s = String(txt || '').replace(/_/g, ' ').toLowerCase(); return s.charAt(0).toUpperCase() + s.slice(1); }
    function iniciales(nombre) {
        const p = String(nombre || '').trim().split(/\s+/).filter(Boolean);
        if (p.length >= 3) return (p[2][0] + p[0][0]).toUpperCase();
        if (p.length === 2) return (p[1][0] + p[0][0]).toUpperCase();
        return (p[0] || '—').slice(0, 2).toUpperCase();
    }
    const tono = (id) => 'td-t' + ((Math.abs(parseInt(id, 10) || 0) % 6) + 1);
    const titulo = (n) => (typeof window.nombreTitulo === 'function' ? window.nombreTitulo(n) : n) || '—';
    const puede = (p) => (typeof AuthService !== 'undefined' ? AuthService.hasPermission(p) : true);

    function datos(empId, fecha) {
        const d = (typeof stateMarcacionesApp !== 'undefined' && stateMarcacionesApp.data) ? stateMarcacionesApp.data : null;
        const emp = d && d.matrix ? d.matrix[empId] : null;
        const fer = d && Array.isArray(d.feriados) ? d.feriados.find(x => (x.fecha || x) === fecha) : null;
        return { di: emp ? emp[fecha] : null, info: (emp && emp.info) || {}, dias: emp || {}, feriado: fer ? (fer.descripcion || 'Feriado') : null };
    }

    // ── Qué pasó ese día ─────────────────────────────────────────────────────────────────────────────────
    function textoTurno(di, info, fecha, feriado) {
        if (feriado && !(di && di.horas_teoricas > 0)) return 'Feriado' + (feriado !== 'Feriado' ? ': ' + feriado : '');
        if (di && di.horas_teoricas > 0 && di.hora_entrada_teorica) return 'Turno ' + hhmm(di.hora_entrada_teorica) + ' a ' + hhmm(di.hora_salida_teorica);
        if (di && (di.estado === 'LIBRE' || di.horas_teoricas === 0)) return 'Día libre';
        const td = info.turno_dias || {};
        const dt = fechaObj(fecha); const py = dt.getDay() === 0 ? 6 : dt.getDay() - 1;
        const dia = td[py];
        if (dia && dia.es_libre) return 'Día libre';
        if (dia && dia.hora_entrada && dia.hora_salida) return 'Turno ' + hhmm(dia.hora_entrada) + ' a ' + hhmm(dia.hora_salida);
        return 'Sin turno';
    }

    function nombreEstado(cod) {
        const conf = Object.values(window._estadosAsistencia || {}).find(e => e && e.codigo === cod);
        return frase(conf ? (conf.nombre_display || cod) : cod);
    }

    function fraseDia(di, marcas, regla, feriado) {
        if (!di || !di.estado) return feriado ? 'Feriado' : 'Sin registro de asistencia';
        const e = di.estado, ja = di.jornada_adicional;
        const n = (marcas || []).length;
        if (regla && regla.en_revision) {
            return e === 'ANOMALIA'
                ? (n === 1 ? '1 marca' : n + ' marcas') + ': el día no se calcula hasta revisarlo'
                : 'Día por revisar según su regla de marcaciones';
        }
        if (di.justificacion_id || (di.nomenclatura && String(di.nomenclatura).trim())) return 'Día justificado' + (di.nomenclatura ? ' (' + di.nomenclatura + ')' : '');
        const atr = Number(di.minutos_atraso) || 0, sad = Number(di.minutos_salida_adelantada) || 0;
        switch (e) {
            case 'ATRASO': return 'Atraso de ' + minSeg(atr);
            case 'SALIDA_ADELANTADA': return 'Salida adelantada de ' + minSeg(sad);
            case 'ATR_SAD': return 'Atraso de ' + minSeg(atr) + ' y salida adelantada de ' + minSeg(sad);
            case 'OK': return 'Turno cumplido' + (atr > 0 ? ' · atraso de ' + minSeg(atr) + ' dentro de la tolerancia' : '');
            case 'INASISTENCIA': case 'FALTA': return n ? nombreEstado(e) : 'Día hábil sin marcas';
            case 'INASISTENCIA_COMPENSADA': return 'Inasistencia compensada';
            case 'JORNADA_COMPENSATORIA': return 'Jornada usada para compensar una inasistencia';
            case 'LIBRE': return 'Día libre';
            case 'FERIADO': return feriado || 'Feriado';
            case 'JORNADA_ESPECIAL':
                return (ja && ja.origen === 'FERIADO' ? 'Feriado trabajado' : 'Día libre trabajado') + ', por validar';
            case 'EXTRA': return 'Jornada EXTRA aprobada';
            case 'HORAS_EXTRAS': return 'Aprobada como horas extra (50 %)';
            case 'PERMISO': return 'Permiso' + (di.hora_inicio_permiso ? ' de ' + hhmm(di.hora_inicio_permiso) + ' a ' + hhmm(di.hora_termino_permiso) : '');
            default: return nombreEstado(e);
        }
    }

    function horasDia(di, regla) {
        if (!di || (regla && regla.en_revision && di.estado === 'ANOMALIA')) return '';
        const teo = Number(di.horas_teoricas) || 0, trab = Number(di.horas_trabajadas) || 0;
        if (teo > 0 && trab > 0) return 'Trabajadas<b>' + horas(trab, true) + ' de ' + horas(teo) + '</b>';
        if (teo > 0) return 'Debía<b>' + horas(teo) + '</b>';
        if (trab > 0) return 'Trabajadas<b>' + horas(trab, true) + '</b>';
        return '';
    }

    function pastilla(di, empId, fecha, info, dias, feriado) {
        if (typeof _analiticaCellContent !== 'function') return '';
        const emp = { id: empId, info, nombre_completo: info.nombre_completo, area: info.area, cargo: info.cargo, turno: info.turno || '', turno_dias: info.turno_dias || {}, tipo_programacion: info.tipo_programacion || '', dias };
        try { return _analiticaCellContent(di, fecha, emp, 'conceptos', !!feriado); } catch (e) { return ''; }
    }

    // Una jornada especial, un +2 o un día libre trabajado: cómo quedó
    function estadoJornada(ja) {
        const m = /\[COMPENSA_INASISTENCIA (\d{4}-\d{2}-\d{2})\]/.exec(ja.observaciones || '');
        switch (ja.estado) {
            case 'HORAS_EXTRAS': return 'Aprobada como horas extra (50 %).';
            case 'EXTRA': return 'Aprobada como jornada EXTRA.';
            case 'COMPENSATORIA': return m ? 'Usada para compensar la inasistencia del <span class="nw">' + DIAS[fechaObj(m[1]).getDay()].toLowerCase() + ' ' + ddmm(m[1]) + '</span>.' : 'Usada para compensar una inasistencia.';
            case 'RECHAZADA': return 'Rechazada.';
            default: return 'Por validar.';
        }
    }

    function contexto(empId, fecha, di, dias, regla, cerrada) {
        if (!di) return '';
        const ja = di.jornada_adicional;
        // El día por revisar: motivo y sus salidas, que antes estaban dentro de «Ingreso manual»
        if (regla && regla.secuencia && regla.en_revision) {
            const sec = regla.secuencia.split('').map(c => c === 'E' ? 'ENTRADA' : (c === 'S' ? 'SALIDA' : c)).join(' · ');
            const nombres = new Map(window.REGLAS_OPCIONES_REVISION || []);
            const iconos = { CONFIRMAR: 'bi-check-circle', AGREGAR_SALIDA: 'bi-box-arrow-right', AGREGAR_ENTRADA: 'bi-box-arrow-in-right', RECLASIFICAR: 'bi-arrow-left-right' };
            const ops = ((regla.regla && regla.regla.opciones_revision) || []).filter(o => nombres.has(o))
                .filter(o => o !== 'CONFIRMAR' || (!cerrada && puede('marcaciones.editar')));
            const bts = ops.map(o => '<button type="button" class="td-btn" data-rev="' + esc(o) + '"><i class="bi ' + (iconos[o] || 'bi-pencil') + '"></i>' + esc(nombres.get(o)) + '</button>').join('');
            return '<div class="td-ctx rv"><i class="bi bi-exclamation-triangle"></i><span><b>Regla ' + esc(sec) + ':</b> el día queda en «Días por revisar».'
                + (bts ? '<span class="td-bts">' + bts + '</span>' : '') + '</span></div>';
        }
        if (regla && regla.secuencia && regla.confirmado) {
            return '<div class="td-ctx cp"><i class="bi bi-check-circle"></i><span><b>Día revisado y confirmado.</b> Si cambian sus marcas, vuelve a revisión.</span></div>';
        }
        if (ja && ja.origen === 'COBERTURA_TURNO') {
            return '<div class="td-ctx he"><i class="bi bi-stopwatch"></i><span><b>+2 de ' + hhmm(ja.hora_entrada) + ' a ' + hhmm(ja.hora_salida) + ' · ' + hMin(ja.minutos_trabajados) + '.</b> ' + estadoJornada(ja) + '</span></div>';
        }
        if (ja && (ja.origen === 'FERIADO' || ja.origen === 'DIA_LIBRE')) {
            return '<div class="td-ctx he"><i class="bi bi-stopwatch"></i><span><b>' + (ja.origen === 'FERIADO' ? 'Feriado' : 'Día libre') + ' trabajado · ' + hMin(ja.minutos_trabajados) + '.</b> ' + estadoJornada(ja) + '</span></div>';
        }
        if (di.estado === 'INASISTENCIA_COMPENSADA') {
            const marca = '[COMPENSA_INASISTENCIA ' + fecha + ']';
            const f = Object.keys(dias).find(k => k !== 'info' && dias[k] && dias[k].jornada_adicional && String(dias[k].jornada_adicional.observaciones || '').includes(marca));
            if (f) {
                const j = dias[f].jornada_adicional;
                const que = j.origen === 'FERIADO' ? 'el feriado trabajado' : (j.origen === 'COBERTURA_TURNO' ? 'la segunda jornada (+2)' : 'el día libre trabajado');
                return '<div class="td-ctx cp"><i class="bi bi-link-45deg"></i><span><b>Compensada con ' + que + ' del <span class="nw">' + DIAS[fechaObj(f).getDay()].toLowerCase() + ' ' + ddmm(f) + '</span></b> ('
                    + hhmm(j.hora_entrada) + ' a ' + hhmm(j.hora_salida) + ', ' + hMin(j.minutos_trabajados) + ').</span></div>';
            }
            if (Number(di.minutos_compensados_he) > 0) {
                return '<div class="td-ctx cp"><i class="bi bi-link-45deg"></i><span><b>Compensada con ' + hMin(di.minutos_compensados_he) + ' de horas extra del tramo.</b></span></div>';
            }
        }
        return '';
    }

    // ── Las marcas del reloj ─────────────────────────────────────────────────────────────────────────────
    function lineaMarcas(marcas, di, regla) {
        if (!marcas || !marcas.length) return '<li class="td-vacio"><i class="bi bi-clock"></i>El reloj no registró marcas este día.</li>';
        const ja = di && di.jornada_adicional && di.jornada_adicional.origen === 'COBERTURA_TURNO' ? di.jornada_adicional : null;
        let corte = -1;
        if (ja && ja.hora_entrada) corte = marcas.findIndex(m => m.tipo_actual === 'Entrada' && segDe(m.hora) >= segDe(ja.hora_entrada) && (!m.fecha || !di.fecha || m.fecha === di.fecha));
        const exceso = di ? Math.round(Number(di.minutos_exceso_colacion) || 0) : 0;
        let pausaColacion = -1;
        if (exceso > 0) {
            const ref = di.hora_salida_colacion ? segDe(di.hora_salida_colacion) : null;
            pausaColacion = marcas.findIndex((m, i) => i < marcas.length - 1 && m.tipo_actual === 'Salida' && marcas[i + 1].tipo_actual === 'Entrada' && i + 1 !== corte && (ref === null || Math.abs(segDe(m.hora) - ref) < 60));
        }
        let html = '';
        marcas.forEach((m, i) => {
            if (i === corte) html += '<li class="td-sep"><span>SEGUNDA JORNADA (+2)</span></li>';
            const sal = m.tipo_actual === 'Salida';
            const sug = regla && regla.en_revision && m.sugerido && m.sugerido !== m.tipo_actual ? '<span class="td-sug">el sistema sugiere ' + esc(String(m.sugerido).toUpperCase()) + '</span>' : '';
            const cor = m.corregida ? '<span class="td-cor">tipo elegido a mano</span>' : '';
            const eq = m.manual ? '<span class="td-e man">Ingreso manual' + sug + cor + '</span>' : '<span class="td-e">' + esc(m.equipo || '') + sug + cor + '</span>';
            html += '<li><span class="td-b' + (sal ? ' s' : '') + '"></span><span class="td-k">' + (sal ? 'SALIDA' : 'ENTRADA') + '</span><span class="td-h">' + esc(m.hora) + '</span>' + eq + '</li>';
            const sig = marcas[i + 1];
            if (sal && sig && sig.tipo_actual === 'Entrada' && i + 1 !== corte) {
                const min = Math.round((absSeg(sig) - absSeg(m)) / 60);
                if (min >= 0) {
                    let txt = 'Pausa de ' + hMin(min);
                    if (i === pausaColacion) txt += ' · ' + exceso + ' min sobre los ' + (Number(di.minutos_colacion_auto) || '') + (di.minutos_colacion_auto ? '' : ' permitidos');
                    html += '<li class="td-gap"><span><i class="bi bi-cup-hot"></i>' + txt + '</span></li>';
                }
            }
        });
        return html;
    }

    // ── Acciones: las calcula openAsistenciaActionModal sobre los botones de la ventana de siempre ────────
    const ACCIONES_DIA = [
        { id: 'btn-compensar-he-action', fn: 'proceedToCompensateHE', tono: 'cp', ic: 'bi-calendar-check', t: 'Compensar inasistencia', u: 'Con una jornada EXTRA o con horas extra del tramo' },
        { id: 'btn-quitar-compensacion', fn: 'proceedToQuitarCompensacion', tono: 'ne', ic: 'bi-arrow-counterclockwise', t: 'Quitar compensación', u: 'La jornada o las horas extra quedan libres otra vez' },
        { id: 'btn-validar-jornada', fn: 'proceedToValidation', tono: 'es', ic: 'bi-patch-check', t: null, u: null },
        { id: 'btn-gestionar-he', fn: 'proceedToHoraExtra', tono: 'es', ic: 'bi-stopwatch', t: 'Gestionar horas extra', u: 'Aprobar o rechazar las horas extra del día' },
        { id: 'btn-revertir-he', fn: 'proceedToRevertExtra', tono: 'ne', ic: 'bi-arrow-counterclockwise', t: 'Revertir jornada a especial', u: 'Deshace la aprobación de las horas extra' },
        { id: 'btn-edit-justificacion', fn: 'proceedToEditJustify', tono: 'rj', ic: 'bi-pencil-square', t: 'Editar o eliminar justificación', u: 'Cambiar la justificación de este día' },
        { id: 'btn-viaje-largo', fn: 'proceedToViajeLargo', tono: 'ne', ic: 'bi-truck', t: 'Registrar viaje largo', u: 'Unir la salida y el regreso del viaje' },
        { id: 'btn-marcacion-180h', fn: 'proceedToMarcacion180h', tono: 'ne', ic: 'bi-truck-front', t: 'Marcación 180 horas (Art. 25 bis)', u: 'Libreta: conducción, espera y descanso' },
    ];
    const visible = (id) => { const b = document.getElementById(id); return !!(b && !b.classList.contains('d-none')); };

    function accionesDia(di) {
        const ja = di && di.jornada_adicional;
        return ACCIONES_DIA.filter(a => visible(a.id)).map(a => {
            let t = a.t, u = a.u;
            if (a.id === 'btn-validar-jornada') {
                if (ja && ja.origen === 'COBERTURA_TURNO') { t = 'Validar cobertura (+2)'; u = 'Segunda jornada del día · ' + hMin(ja.minutos_trabajados); }
                else { t = 'Validar jornada especial'; u = ja ? (ja.origen === 'FERIADO' ? 'Feriado' : 'Día libre') + ' trabajado · ' + hMin(ja.minutos_trabajados) : 'Día libre o feriado trabajado'; }
            }
            return '<button type="button" class="td-da ' + a.tono + '" data-fn="' + a.fn + '"><span class="td-ic"><i class="bi ' + a.ic + '"></i></span><span><span class="td-t" style="display:block">' + esc(t) + '</span><span class="td-u" style="display:block">' + esc(u) + '</span></span><i class="bi bi-chevron-right"></i></button>';
        }).join('');
    }

    function accionesSiempre(di) {
        const regreso = !!(di && di.permiso_activo);
        const corto = esMovil();
        return '<button type="button" class="td-btn" data-fn="proceedToJustify"><i class="bi bi-file-earmark-text"></i>' + (corto ? 'Justificar' : 'Justificar ausencia') + '</button>'
            + '<button type="button" class="td-btn' + (regreso ? ' td-on' : '') + '" data-fn="proceedToPermission"><i class="bi bi-door-open"></i>' + (regreso ? 'Registrar regreso' : 'Permiso o salida') + '</button>'
            + '<button type="button" class="td-btn" data-fn="proceedToManualEntry"><i class="bi bi-keyboard"></i>Ingreso manual</button>'
            + '<button type="button" class="td-btn" data-fn="proceedToBulkFill"><i class="bi bi-magic"></i>' + (corto ? 'Relleno' : 'Relleno según turno') + '</button>';
    }

    // ── Abrir, ubicar y cerrar ───────────────────────────────────────────────────────────────────────────
    let tarjeta = null, scrim = null, ancla = null, actual = null, pedido = 0, ultimaCelda = null, rafPos = 0;

    document.addEventListener('click', (e) => {
        const td = e.target && e.target.closest ? e.target.closest('td.cell-clickable') : null;
        if (td) ultimaCelda = td;
    }, true);
    // Doble clic en un día abre «Justificar»: la tarjeta se cierra antes
    document.addEventListener('dblclick', (e) => {
        if (e.target && e.target.closest && e.target.closest('td.cell-clickable')) cerrar(true);
    }, true);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && tarjeta && !document.querySelector('.modal.show, .swal2-container')) { e.stopPropagation(); cerrar(false); }
    }, true);
    document.addEventListener('mousedown', (e) => {
        if (!tarjeta || esMovil() || !tarjeta.classList.contains('td-junto')) return;
        if (tarjeta.contains(e.target) || (ancla && ancla.contains(e.target))) return;
        cerrar(false);
    }, true);
    window.addEventListener('resize', () => { if (tarjeta) cerrar(true); });
    document.addEventListener('scroll', () => {
        if (!tarjeta || !tarjeta.classList.contains('td-junto')) return;
        cancelAnimationFrame(rafPos); rafPos = requestAnimationFrame(ubicar);
    }, true);

    function buscarAncla(empId, fecha) {
        const clave = empId + '|' + fecha;
        if (ultimaCelda && ultimaCelda.isConnected && ultimaCelda.getAttribute('data-tip') === clave && ultimaCelda.offsetParent) return ultimaCelda;
        const tds = document.querySelectorAll('td.cell-clickable[data-tip="' + clave + '"]');
        for (const td of tds) if (td.offsetParent) return td;
        return null;
    }

    function ubicar() {
        if (!tarjeta || !ancla) return;
        if (!ancla.isConnected) { cerrar(true); return; }
        const r = ancla.getBoundingClientRect(), W = tarjeta.offsetWidth, H = tarjeta.offsetHeight, m = 12, sep = 10;
        let left = r.right + sep;
        if (left + W > window.innerWidth - m) left = r.left - sep - W;
        let top = r.top - 14;
        if (left < m) {   // no cabe a ningún lado: debajo (o encima) del día
            left = Math.max(m, Math.min(window.innerWidth - W - m, r.left + r.width / 2 - W / 2));
            top = (r.bottom + sep + H <= window.innerHeight - m) ? r.bottom + sep : r.top - sep - H;
        }
        top = Math.max(m, Math.min(top, window.innerHeight - m - H));
        tarjeta.style.left = Math.round(left) + 'px';
        tarjeta.style.top = Math.round(top) + 'px';
    }

    function cerrar(inmediato) {
        if (!tarjeta) return;
        const t = tarjeta, s = scrim, a = ancla;
        tarjeta = null; scrim = null; ancla = null; actual = null; pedido++;
        document.body.classList.remove('td-abierta');
        document.querySelectorAll('td.col-day.td-sel').forEach(td => td.classList.remove('td-sel'));
        const quitar = () => { t.remove(); if (s) s.remove(); };
        const sinMovimiento = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (!inmediato && t.classList.contains('td-hoja') && !sinMovimiento) {
            t.classList.add('td-baja');
            if (s) { s.style.transition = 'opacity .18s'; s.style.opacity = '0'; }
            setTimeout(quitar, 180);
        } else quitar();
        if (!inmediato && a && a.isConnected && !esMovil()) { try { a.focus({ preventScroll: true }); } catch (_) { } }
    }

    function armar(empId, fecha, nombre, marcasRes) {
        const { di, info, dias, feriado } = datos(empId, fecha);
        const marcas = marcasRes && marcasRes.marcas;
        const regla = marcasRes && marcasRes.regla;
        const cerrada = !!(marcasRes && marcasRes.cerrada);
        const dt = fechaObj(fecha);
        const movil = esMovil();
        const cargo = info.cargo ? info.cargo + ((typeof stateMarcacionesApp !== 'undefined' && stateMarcacionesApp.area) || !info.area ? '' : ' · ' + info.area) : (info.area || '');
        const hh = horasDia(di, regla);
        const dAcc = accionesDia(di);
        const tl = marcasRes ? (marcasRes.error ? '<li class="td-vacio"><i class="bi bi-wifi-off"></i>No se pudieron leer las marcas del día.</li>' : lineaMarcas(marcas, di, regla))
                             : '<li class="td-carga"><span></span><span style="width:78%"></span></li>';
        return '<div class="td-grab" aria-hidden="true"></div>'
            + '<div class="td-dh"><span class="td-av ' + tono(empId) + '" aria-hidden="true">' + esc(iniciales(nombre || info.nombre_completo)) + '</span>'
            + '<div style="min-width:0"><h5 id="td-titulo">' + esc(titulo(nombre || info.nombre_completo)) + '</h5>'
            + (cargo ? '<div class="td-rol">' + esc(cargo) + '</div>' : '')
            + '<div class="td-s2">' + (movil ? DIAS_CORTOS : DIAS)[dt.getDay()] + ' ' + ddmm(fecha) + ' · ' + esc(textoTurno(di, info, fecha, feriado)) + '</div></div>'
            + '<button type="button" class="td-x" data-cerrar aria-label="Cerrar"><i class="bi bi-x-lg"></i></button></div>'
            + '<div class="td-est"><span class="td-pill">' + pastilla(di, empId, fecha, info, dias, feriado) + '</span><span class="td-w">' + esc(fraseDia(di, marcas, regla, feriado)) + '</span>'
            + (hh ? '<span class="td-hh">' + hh + '</span>' : '') + '</div>'
            + '<ul class="td-tl' + (marcasRes ? '' : ' td-cargando') + '">' + tl + '</ul>'
            + (marcasRes ? contexto(empId, fecha, di, dias, regla, cerrada) : '')
            + (dAcc ? '<div class="td-dacc">' + dAcc + '</div>' : '')
            + (movil ? '' : '<div class="td-permt">ACCIONES DE SIEMPRE</div>')
            + '<div class="td-perm">' + accionesSiempre(di) + '</div>';
    }

    function pintar(empId, fecha, nombre, marcasRes) {
        if (!tarjeta) return;
        const foco = document.activeElement && tarjeta.contains(document.activeElement);
        tarjeta.innerHTML = armar(empId, fecha, nombre, marcasRes);
        if (tarjeta.classList.contains('td-junto')) ubicar();
        if (foco) { try { tarjeta.focus({ preventScroll: true }); } catch (_) { } }
    }

    async function leerMarcas(empId, fecha) {
        const q = 'empleado_id=' + encodeURIComponent(empId) + '&fecha=' + encodeURIComponent(fecha);
        const hdr = { headers: { 'Authorization': 'Bearer ' + localStorage.getItem('access_token') } };
        const [rm, rr] = await Promise.all([
            fetch('/api/asistencia/marcaciones/dia/?' + q),
            fetch('/api/configuracion/reglas-marcas/evaluar/?' + q, hdr).catch(() => null),
        ]);
        if (!rm.ok) throw new Error('marcas ' + rm.status);
        const dm = await rm.json();
        const regla = rr && rr.ok ? await rr.json().catch(() => null) : null;
        return { marcas: dm.marcas || [], cerrada: !!dm.fecha_cerrada, regla };
    }

    /** Muestra la tarjeta del día. Devuelve false si no se puede (y entonces se abre la ventana de siempre). */
    function abrir(empId, fecha, nombre) {
        if (typeof document === 'undefined' || !document.body) return false;
        // Abierta desde otra ventana (p. ej. el cierre de RRHH): sigue la ventana de siempre, que se apila encima
        if (document.querySelector('.modal.show')) return false;
        const mismo = tarjeta && actual === empId + '|' + fecha;
        if (tarjeta && !mismo) cerrar(true);
        const movil = esMovil();
        const a = movil ? null : buscarAncla(empId, fecha);
        if (!mismo) {
            tarjeta = document.createElement('div');
            tarjeta.className = 'tdia ' + (movil ? 'td-hoja' : (a ? 'td-junto' : 'td-centro'));
            tarjeta.setAttribute('role', 'dialog');
            tarjeta.setAttribute('aria-labelledby', 'td-titulo');
            tarjeta.tabIndex = -1;
            if (movil || !a) {
                scrim = document.createElement('div');
                scrim.className = 'td-scrim';
                // Un segundo toque rápido sobre el mismo día debe llegar a la celda (doble toque = Justificar)
                scrim.style.pointerEvents = 'none';
                setTimeout(() => { if (scrim) scrim.style.pointerEvents = ''; }, 350);
                scrim.addEventListener('click', () => cerrar(false));
                document.body.appendChild(scrim);
            }
            document.body.appendChild(tarjeta);
            tarjeta.addEventListener('click', alTocar);
            if (movil) arrastrarParaCerrar(tarjeta);
            ancla = a;
            actual = empId + '|' + fecha;
            document.body.classList.add('td-abierta');
        }
        document.querySelectorAll('td.col-day.td-sel').forEach(td => td.classList.remove('td-sel'));
        const sel = movil ? buscarAnclaMovil(empId, fecha) : a;
        if (sel) sel.classList.add('td-sel');
        pintar(empId, fecha, nombre, null);
        if (!mismo) { try { tarjeta.focus({ preventScroll: true }); } catch (_) { } }
        const yo = ++pedido;
        leerMarcas(empId, fecha)
            .then(res => { if (yo === pedido) pintar(empId, fecha, nombre, res); })
            .catch(() => { if (yo === pedido) pintar(empId, fecha, nombre, { error: true, marcas: [] }); });
        return true;
    }

    function buscarAnclaMovil(empId, fecha) {
        const tds = document.querySelectorAll('.sem-cel td.cell-clickable[data-tip="' + empId + '|' + fecha + '"]');
        return tds[0] || null;
    }

    function alTocar(e) {
        const b = e.target.closest('button');
        if (!b || !tarjeta || !tarjeta.contains(b)) return;
        if (b.hasAttribute('data-cerrar')) { cerrar(false); return; }
        const fn = b.getAttribute('data-fn');
        if (fn) {
            if (typeof window[fn] === 'function') window[fn]();
            else { cerrar(true); console.error('Acción no disponible:', fn); }
            return;
        }
        const rev = b.getAttribute('data-rev');
        if (rev) {
            const st = (typeof marcacionesManualesState !== 'undefined') ? marcacionesManualesState : {};
            if (rev === 'CONFIRMAR') {
                const empId = st.currentEmpId, fecha = st.currentDate;
                cerrar(true);
                if (typeof window.confirmarDiaRevision === 'function') window.confirmarDiaRevision(empId, fecha);
                else if (typeof confirmarDiaRevision === 'function') confirmarDiaRevision(empId, fecha);
            } else if (typeof window.proceedToManualEntry === 'function') window.proceedToManualEntry();
            else if (typeof proceedToManualEntry === 'function') proceedToManualEntry();
        }
    }

    // En el celular la hoja se cierra deslizándola hacia abajo
    function arrastrarParaCerrar(el) {
        let y0 = null, dy = 0;
        el.addEventListener('touchstart', (e) => {
            if (el.scrollTop > 0 || e.touches.length !== 1) { y0 = null; return; }
            y0 = e.touches[0].clientY; dy = 0;
        }, { passive: true });
        el.addEventListener('touchmove', (e) => {
            if (y0 === null) return;
            dy = Math.max(0, e.touches[0].clientY - y0);
            el.style.transform = dy ? 'translateY(' + dy + 'px)' : '';
        }, { passive: true });
        el.addEventListener('touchend', () => {
            if (y0 === null) return;
            const lejos = dy > 90;
            el.style.transform = '';
            y0 = null;
            if (lejos) cerrar(false);
        }, { passive: true });
    }

    window.TarjetaDia = { abrir, cerrar: () => cerrar(true), abierta: () => !!tarjeta };

    // ═════════════════════════════════════════════════════════════════════════════════════════════════════
    // SEMANA EN EL CELULAR: los 7 días en la pantalla, con las mismas celdas de la grilla
    // ═════════════════════════════════════════════════════════════════════════════════════════════════════
    let semIdx = null, semClave = '', semDir = '', obsCuerpo = null;
    const hoyIso = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };

    function semanasDe(fechas) {
        const semanas = [];
        fechas.forEach(f => {
            const dt = fechaObj(f);
            const lunes = new Date(dt); lunes.setDate(dt.getDate() - ((dt.getDay() + 6) % 7));
            const k = lunes.getTime();
            let s = semanas[semanas.length - 1];
            if (!s || s.k !== k) { s = { k, dias: [] }; semanas.push(s); }
            s.dias.push(f);
        });
        return semanas.map(s => {
            const base = new Date(s.k), siete = [];
            for (let i = 0; i < 7; i++) {
                const d = new Date(base); d.setDate(base.getDate() + i);
                siete.push(d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'));
            }
            return { siete, enTramo: new Set(s.dias), desde: s.dias[0], hasta: s.dias[s.dias.length - 1] };
        });
    }

    function pintarSemana() {
        const cont = document.getElementById('marcaciones-view-container');
        if (!cont) return;
        const tabla = cont.querySelector('table.matrix-table');
        let sem = cont.querySelector('.sem-cel');
        let volver = cont.querySelector('.sem-volver');
        if (!tabla || typeof stateMarcacionesApp === 'undefined' || !stateMarcacionesApp.data || !stateMarcacionesApp.data.periodo || typeof window.getDatesInRange !== 'function') {
            if (sem) sem.remove();
            if (volver) volver.remove();
            return;
        }
        const scroller = tabla.parentElement;
        scroller.classList.add('sem-oculta');
        if (!sem) { sem = document.createElement('div'); sem.className = 'sem-cel'; scroller.insertAdjacentElement('beforebegin', sem); }
        if (!volver) {
            volver = document.createElement('div'); volver.className = 'sem-volver';
            volver.innerHTML = '<button type="button"><i class="bi bi-calendar-week me-1"></i>Ver por semana</button>';
            volver.querySelector('button').addEventListener('click', () => { document.body.classList.remove('sem-cel-off'); pintarSemana(); });
            sem.insertAdjacentElement('beforebegin', volver);
        }
        vigilarCuerpo(tabla);
        if (!esMovil()) { sem.innerHTML = ''; return; }

        const per = stateMarcacionesApp.data.periodo;
        const fechas = window.getDatesInRange(per.inicio, per.fin);
        const semanas = semanasDe(fechas);
        if (!semanas.length) { sem.innerHTML = ''; return; }
        const clave = per.inicio + '|' + per.fin;
        if (semIdx === null || clave !== semClave) {
            const hoy = hoyIso();
            semIdx = hoy < per.inicio ? 0 : (hoy > per.fin ? semanas.length - 1 : Math.max(0, semanas.findIndex(s => s.siete.includes(hoy))));
            semClave = clave;
        }
        semIdx = Math.max(0, Math.min(semIdx, semanas.length - 1));
        const s = semanas[semIdx];
        const ferSet = new Set((stateMarcacionesApp.data.feriados || []).map(x => x.fecha || x));

        const cab = s.siete.map(f => {
            const d = fechaObj(f);
            const cls = !s.enTramo.has(f) ? 'sem-fuera' : (ferSet.has(f) ? 'dh-fer' : (d.getDay() === 0 ? 'dh-dom' : ''));
            return '<th class="' + cls + '" scope="col">' + DIAS_SEM[d.getDay()] + '<b>' + String(d.getDate()).padStart(2, '0') + '</b></th>';
        }).join('');

        const filas = tabla.querySelectorAll('tbody tr[id^="row-empleado-"]');
        const cuerpo = document.createElement('tbody');
        if (semDir) cuerpo.className = semDir === 'izq' ? 'sem-izq' : 'sem-der';
        filas.forEach(tr => {
            const id = tr.id.replace('row-empleado-', '');
            const m = stateMarcacionesApp.data.matrix && stateMarcacionesApp.data.matrix[id];
            const info = (m && m.info) || {};
            const nombre = info.nombre_completo || (tr.querySelector('.emp-name-link') || {}).title || '';
            const saldoTd = tr.querySelector('td.sticky-saldo-col');
            const saldo = saldoTd ? saldoTd.textContent.trim() : '';
            const saldoCls = saldoTd ? (saldoTd.classList.contains('text-success') ? ' text-success' : (saldoTd.classList.contains('text-danger') ? ' text-danger' : '')) : '';
            const tt = document.createElement('tr');
            tt.className = 'sem-tt';
            tt.innerHTML = '<td colspan="7"><div class="sem-quien" title="Doble toque: Cuadre del tramo"><span class="sem-av ' + tono(id) + '" aria-hidden="true">' + esc(iniciales(nombre)) + '</span>'
                + '<div class="sem-n">' + esc(titulo(nombre)) + (info.cargo ? '<small>' + esc(info.cargo) + '</small>' : '') + '</div>'
                + (saldo ? '<span class="sem-v' + saldoCls + '">' + esc(saldo) + '</span>' : '') + '</div></td>';
            tt.querySelector('.sem-quien').addEventListener('dblclick', () => { if (typeof window.openCuadreModal === 'function') window.openCuadreModal(parseInt(id, 10), nombre); });
            const dias = document.createElement('tr');
            dias.className = 'sem-dias';
            s.siete.forEach(f => {
                const td = s.enTramo.has(f) ? tr.querySelector('td.col-day[data-tip="' + id + '|' + f + '"]') : null;
                if (td) {
                    const c = td.cloneNode(true);
                    c.removeAttribute('id'); c.classList.remove('td-sel');
                    c.querySelectorAll('[id]').forEach(x => x.removeAttribute('id'));
                    dias.appendChild(c);
                } else {
                    const v = document.createElement('td'); v.className = 'sem-fuera'; v.setAttribute('aria-hidden', 'true');
                    dias.appendChild(v);
                }
            });
            cuerpo.appendChild(tt); cuerpo.appendChild(dias);
        });

        sem.innerHTML = '<div class="sem-week"><button type="button" class="sem-a" data-sem="-1" aria-label="Semana anterior"' + (semIdx === 0 ? ' disabled' : '') + '><i class="bi bi-chevron-left"></i></button>'
            + '<div><b>' + ddmm(s.desde) + ' al ' + ddmm(s.hasta) + '</b><span class="sem-m">Semana ' + (semIdx + 1) + ' del tramo</span></div>'
            + '<button type="button" class="sem-a" data-sem="1" aria-label="Semana siguiente"' + (semIdx === semanas.length - 1 ? ' disabled' : '') + '><i class="bi bi-chevron-right"></i></button></div>'
            + '<div class="sem-lista">' + (filas.length ? '<table><thead class="sem-dh"><tr>' + cab + '</tr></thead></table>' : '<div class="sem-vacia">No hay personas con los filtros actuales.</div>') + '</div>'
            + '<div class="sem-pie"><button type="button" data-tramo><i class="bi bi-table me-1"></i>Ver el tramo completo</button></div>';
        const t = sem.querySelector('.sem-lista table');
        if (t) t.appendChild(cuerpo);
        sem.querySelectorAll('[data-sem]').forEach(b => b.addEventListener('click', () => {
            const paso = parseInt(b.getAttribute('data-sem'), 10);
            semIdx += paso; semDir = paso < 0 ? 'izq' : 'der';
            pintarSemana(); semDir = '';
        }));
        sem.querySelector('[data-tramo]').addEventListener('click', () => { document.body.classList.add('sem-cel-off'); });
    }

    // Una fila recargada (reloadSingleEmployeeRow) o un pintado nuevo de la grilla vuelven a armar la semana
    function vigilarCuerpo(tabla) {
        const tb = tabla.tBodies && tabla.tBodies[0];
        if (!tb || (obsCuerpo && obsCuerpo._tb === tb)) return;
        if (obsCuerpo) obsCuerpo.disconnect();
        let raf = 0;
        obsCuerpo = new MutationObserver(() => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => { if (esMovil()) pintarSemana(); }); });
        obsCuerpo._tb = tb;
        obsCuerpo.observe(tb, { childList: true });
    }

    if (typeof renderVistaAnalitica === 'function') {
        const original = renderVistaAnalitica;
        // eslint-disable-next-line no-global-assign
        renderVistaAnalitica = function () {
            const r = original.apply(this, arguments);
            try { pintarSemana(); } catch (e) { console.warn('semana del celular:', e); }
            return r;
        };
    }
    window.matchMedia('(max-width: 768px)').addEventListener('change', () => { try { pintarSemana(); } catch (_) { } });
    // Si la grilla ya estaba pintada cuando llegó este archivo
    try { pintarSemana(); } catch (_) { }
    window.pintarSemanaCelular = pintarSemana;
})();
