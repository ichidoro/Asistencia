// Ficha de la persona (diseño HD): el tramo completo de una persona en una sola vista.
// Calendario del tramo con el estado de cada día, sus cifras (días trabajados, atrasos, inasistencias y horas extra
// aprobadas) y lo que pasó (compensaciones, feriados trabajados, permisos, atrasos). Solo lee:
// GET /api/asistencia/matriz/?empleado_id= y GET /api/configuracion/periodos/. No guarda nada.
// Se abre con window.FichaPersona.abrir(empId) desde Empleados y desde el buscador (Ctrl K).
(function () {
  'use strict';
  const ID = 'modal-ficha-persona';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const titulo = (n) => (typeof window.nombreTitulo === 'function' ? window.nombreTitulo(n) : n) || '';
  const ddmm = (f) => String(f || '').slice(8, 10) + '-' + String(f || '').slice(5, 7);
  const fecha = (f) => (window.formatFechaDDMMYYYY ? window.formatFechaDDMMYYYY(f) : f);
  const hhmm = (h) => String(h || '').slice(0, 5);
  const puede = (p) => (typeof AuthService !== 'undefined' && AuthService.hasPermission ? AuthService.hasPermission(p) : true);
  const DIAS = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM'];
  let estado = { empId: null, periodos: [], tramo: null, datos: null, elegido: null };

  function hms(min) {
    const t = Math.round(Math.max(0, Number(min) || 0) * 60);
    const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
    return h + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  }
  function minSeg(min) {
    const t = Math.round(Math.max(0, Number(min) || 0) * 60);
    const m = Math.floor(t / 60), s = t % 60;
    return (m ? m + ' min' : '') + (m && s ? ' ' : '') + (s ? s + ' s' : '') || '0 s';
  }
  function duracion(horas) {
    const t = Math.round(Math.max(0, Number(horas) || 0) * 60);
    const h = Math.floor(t / 60), m = t % 60;
    return h ? h + ' h' + (m ? ' ' + m + ' min' : '') : m + ' min';
  }
  function iniciales(info) {
    const n = String(info.nombre || '').trim().split(/\s+/)[0] || '';
    const a = String(info.apellido_paterno || '').trim();
    return ((n[0] || '') + (a[0] || '')).toUpperCase() || '—';
  }
  function corta(codigo) {
    const e = (window._estadosAsistencia || {})[codigo];
    if (e && e.short_label) return e.short_label;
    return String(codigo || '—').replace(/_/g, ' ').slice(0, 3).toUpperCase();
  }
  function tono(codigo) {
    switch (codigo) {
      case 'OK': case 'EN_CURSO': return 'ok';
      case 'ATRASO': case 'SALIDA_ADELANTADA': return 'atr';
      case 'INASISTENCIA': return 'ina';
      case 'INASISTENCIA_COMPENSADA': case 'JORNADA_COMPENSATORIA': return 'comp';
      case 'LIBRE': return 'lib';
      case 'FERIADO': return 'fer';
      case 'EXTRA': case 'JORNADA_ESPECIAL': case 'HORAS_EXTRAS': return 'ext';
      case 'ANOMALIA': return 'ano';
      default: return 'jus';
    }
  }
  const trabajo = (d) => Boolean(d && d.hora_entrada_real);

  function asegurar() {
    if (document.getElementById(ID)) return;
    document.body.insertAdjacentHTML('beforeend', `
      <div class="modal fade" id="${ID}" tabindex="-1" aria-hidden="true" aria-labelledby="fp-titulo">
        <div class="modal-dialog modal-xl modal-dialog-centered modal-dialog-scrollable">
          <div class="modal-content">
            <div class="modal-header">
              <span class="vn-av" id="fp-av" aria-hidden="true">—</span>
              <div class="flex-grow-1" style="min-width:0">
                <h5 class="modal-title mb-0" id="fp-titulo">Ficha de la persona</h5>
                <div class="vn-sub" id="fp-sub"></div>
              </div>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button>
            </div>
            <div class="modal-body" id="fp-cuerpo"></div>
            <div class="modal-footer">
              <label class="fp-tramo me-auto"><span>Tramo</span><select class="form-select form-select-sm" id="fp-tramo" aria-label="Tramo"></select></label>
              <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cerrar</button>
              <button type="button" class="btn btn-primary fw-bold" id="fp-cuadre">Cuadre del tramo</button>
            </div>
          </div>
        </div>
      </div>`);
    document.getElementById('fp-tramo').addEventListener('change', (e) => {
      estado.tramo = estado.periodos.find((p) => String(p.id) === e.target.value) || estado.tramo;
      estado.elegido = null;
      cargar();
    });
    document.getElementById('fp-cuadre').addEventListener('click', () => {
      const info = estado.datos && estado.datos.info;
      if (!info || typeof window.openCuadreModal !== 'function') return;
      const nombre = `${info.apellido_paterno || ''} ${info.apellido_materno || ''} ${info.nombre || ''}`.replace(/\s+/g, ' ').trim();
      bootstrap.Modal.getOrCreateInstance(document.getElementById(ID)).hide();
      setTimeout(() => window.openCuadreModal(estado.empId, nombre), 250);
    });
    document.getElementById('fp-cuerpo').addEventListener('click', (e) => {
      const b = e.target.closest('[data-fp-dia]');
      if (!b) return;
      estado.elegido = b.dataset.fpDia;
      pintar();
    });
  }

  async function abrir(empId) {
    if (!empId) return;
    asegurar();
    estado = { empId: Number(empId), periodos: estado.periodos || [], tramo: null, datos: null, elegido: null };
    document.getElementById('fp-cuerpo').innerHTML = '<div class="fp-cargando">Cargando el tramo…</div>';
    document.getElementById('fp-cuadre').hidden = !(puede('marcaciones.ver') && typeof window.openCuadreModal === 'function');
    bootstrap.Modal.getOrCreateInstance(document.getElementById(ID)).show();
    try {
      if (!estado.periodos.length) {
        const r = await fetch('/api/configuracion/periodos/');
        estado.periodos = r.ok ? await r.json() : [];
      }
    } catch (e) { estado.periodos = []; }
    const hoy = new Date().toISOString().slice(0, 10);
    // Por defecto el tramo vigente (el que marca la configuración) o el que contiene hoy
    estado.tramo = estado.periodos.find((p) => p.activo === 1 || p.activo === true)
      || estado.periodos.find((p) => p.fecha_inicio <= hoy && hoy <= p.fecha_fin) || estado.periodos[0] || null;
    const sel = document.getElementById('fp-tramo');
    sel.innerHTML = estado.periodos.map((p) => `<option value="${esc(p.id)}">${esc(p.mes_cierre)} · ${esc(ddmm(p.fecha_inicio))} al ${esc(ddmm(p.fecha_fin))}</option>`).join('');
    if (estado.tramo) sel.value = String(estado.tramo.id);
    await cargar();
  }

  async function cargar() {
    const cuerpo = document.getElementById('fp-cuerpo');
    if (!estado.tramo) { cuerpo.innerHTML = '<div class="fp-cargando">No hay tramos configurados.</div>'; return; }
    cuerpo.innerHTML = '<div class="fp-cargando">Cargando el tramo…</div>';
    try {
      const t = estado.tramo;
      const r = await fetch(`/api/asistencia/matriz/?fecha_inicio=${t.fecha_inicio}&fecha_fin=${t.fecha_fin}&empleado_id=${estado.empId}`);
      if (!r.ok) throw new Error(r.status === 403 ? 'Su usuario no puede ver la asistencia de esta persona.' : 'No se pudo cargar el tramo.');
      const d = await r.json();
      const m = (d.matrix || {})[String(estado.empId)] || {};
      const info = m.info || (d.empleados || [])[0] || {};
      const dias = Object.keys(m).filter((k) => /^\d{4}-\d{2}-\d{2}$/.test(k)).sort().map((k) => m[k]);
      estado.datos = { info, dias, feriados: d.feriados || [], periodo: d.periodo || {} };
      pintar();
    } catch (e) {
      cuerpo.innerHTML = `<div class="fp-cargando">${esc(e.message || 'No se pudo cargar el tramo.')}</div>`;
    }
  }

  function pintar() {
    const { info, dias, feriados } = estado.datos;
    const t = estado.tramo;
    const nombre = `${info.apellido_paterno || ''} ${info.apellido_materno || ''} ${info.nombre || ''}`;
    document.getElementById('fp-titulo').textContent = titulo(nombre);
    const av = document.getElementById('fp-av');
    av.textContent = iniciales(info);
    av.className = 'vn-av td-t' + ((Math.abs(parseInt(estado.empId, 10) || 0) % 6) + 1);
    // El horario de turno que más se repite en el tramo
    const conTurno = dias.filter((d) => d.hora_entrada_teorica && d.horas_teoricas > 0);
    const veces = {};
    conTurno.forEach((d) => { const k = hhmm(d.hora_entrada_teorica) + ' a ' + hhmm(d.hora_salida_teorica); veces[k] = (veces[k] || 0) + 1; });
    const masVeces = Object.keys(veces).sort((a, b) => veces[b] - veces[a])[0];
    const turno = masVeces ? 'Turno ' + masVeces : '';
    document.getElementById('fp-sub').textContent = [info.cargo, info.area || (conTurno[0] && conTurno[0].turno_nombre), turno].filter(Boolean).join(' · ');

    // ── Cifras (cada una sale de los días del tramo) ──
    const fer = new Map(feriados.map((f) => [f.fecha || f, f.descripcion || 'Feriado']));
    const trabajados = dias.filter((d) => trabajo(d) && d.horas_teoricas > 0);
    const especiales = dias.filter((d) => trabajo(d) && !(d.horas_teoricas > 0));
    const atrasos = dias.filter((d) => d.estado === 'ATRASO');
    const inas = dias.filter((d) => d.estado === 'INASISTENCIA' || d.estado === 'INASISTENCIA_COMPENSADA');
    const comp = inas.filter((d) => d.estado === 'INASISTENCIA_COMPENSADA');
    const heAprob = dias.filter((d) => d.estado_he === 'APROBADO' && (d.minutos_extra_autorizados || 0) > 0);
    const heMin = heAprob.reduce((s, d) => s + (Number(d.minutos_extra_autorizados) || 0), 0);
    const hePend = dias.filter((d) => d.estado_he && d.estado_he !== 'APROBADO' && d.estado_he !== 'RECHAZADO' && (d.minutos_extra_bruto || 0) > 0);
    const extraEsp = especiales.length ? 'más ' + (especiales.length === 1
      ? (fer.has(especiales[0].fecha) ? 'el feriado del ' + ddmm(especiales[0].fecha) : 'la jornada especial del ' + ddmm(especiales[0].fecha))
      : especiales.length + ' jornadas especiales') : 'días con turno y marcas';
    const cifras = [
      ['Días trabajados', String(trabajados.length), extraEsp],
      ['Atrasos', String(atrasos.length), trabajados.length ? `de ${trabajados.length} días` : '—'],
      ['Inasistencias', String(inas.length), inas.length ? (comp.length === inas.length ? (comp.length === 1 ? 'compensada' : 'todas compensadas') : `${comp.length} compensada${comp.length === 1 ? '' : 's'}`) : 'ninguna'],
      ['Horas extra aprobadas', hms(heMin), heAprob.length ? `en ${heAprob.length} ${heAprob.length === 1 ? 'día' : 'días'}` + (hePend.length ? ` · ${hePend.length} por decidir` : '') : (hePend.length ? `${hePend.length} por decidir` : 'ninguna')],
    ];

    // ── Calendario del tramo, de lunes a domingo ──
    const porFecha = new Map(dias.map((d) => [d.fecha, d]));
    const ini = new Date(t.fecha_inicio + 'T12:00:00'), fin = new Date(t.fecha_fin + 'T12:00:00');
    const primero = new Date(ini); primero.setDate(primero.getDate() - ((primero.getDay() + 6) % 7));
    let celdas = '';
    for (let x = new Date(primero); x <= fin || (x.getDay() + 6) % 7 !== 0; x.setDate(x.getDate() + 1)) {
      const f = x.toISOString().slice(0, 10);
      const d = porFecha.get(f);
      if (x < ini || x > fin || !d) { celdas += '<span class="fp-d fp-fuera" aria-hidden="true"></span>'; continue; }
      const sel = estado.elegido === f ? ' fp-sel' : '';
      celdas += `<button type="button" class="fp-d fp-${tono(d.estado)}${sel}" data-fp-dia="${f}" aria-label="${esc(window.textoEstado ? window.textoEstado(d.estado) : d.estado)}, ${esc(fecha(f))}">`
        + `<span class="fp-n">${esc(f.slice(8, 10))}</span><span class="fp-e">${esc(corta(d.estado))}</span></button>`;
    }
    const dElegido = estado.elegido && porFecha.get(estado.elegido);
    let detalle = '<div class="fp-detalle fp-vacio">Toque un día para ver sus marcas.</div>';
    if (dElegido) {
      const dia = new Date(dElegido.fecha + 'T12:00:00').toLocaleDateString('es-CL', { weekday: 'long' });
      const marcas = dElegido.hora_entrada_real ? `ENTRADA ${esc(dElegido.hora_entrada_real)} · SALIDA ${esc(dElegido.hora_salida_real || 'sin marca')}` : 'Sin marcas';
      const atr = dElegido.minutos_atraso > 0 ? ` · Atraso de ${esc(minSeg(dElegido.minutos_atraso))}` : '';
      detalle = `<div class="fp-detalle"><b>${esc(dia)} ${esc(fecha(dElegido.fecha))}</b><span class="fp-chip fp-${tono(dElegido.estado)}">${esc(window.textoEstado ? window.textoEstado(dElegido.estado) : dElegido.estado)}</span><span>${marcas}${atr}</span></div>`;
    }

    // ── Lo que pasó en el tramo ──
    const hechos = [];
    comp.forEach((d) => hechos.push(['comp', `${ddmm(d.fecha)} · Inasistencia compensada`, 'El día quedó cubierto con otra jornada del tramo.']));
    inas.filter((d) => d.estado === 'INASISTENCIA').forEach((d) => hechos.push(['ina', `${ddmm(d.fecha)} · Inasistencia sin compensar`, 'No tiene marcas ni justificación.']));
    especiales.forEach((d) => {
      const que = fer.has(d.fecha) ? 'Feriado trabajado' : 'Jornada en día libre';
      const como = d.estado === 'JORNADA_COMPENSATORIA' ? 'Quedó como jornada compensatoria.' : (window.textoEstado ? window.textoEstado(d.estado) + '.' : '');
      hechos.push(['comp', `${ddmm(d.fecha)} · ${que}`, `${duracion(d.horas_trabajadas)}. ${como}`]);
    });
    dias.filter((d) => tono(d.estado) === 'jus' && !trabajo(d)).forEach((d) => hechos.push(['jus', `${ddmm(d.fecha)} · ${window.textoEstado ? window.textoEstado(d.estado) : d.estado}`, 'Día justificado.']));
    if (atrasos.length) {
      const fs = atrasos.map((d) => d.fecha);
      const lista = fs.map(ddmm);
      hechos.push(['atr', `${atrasos.length} ${atrasos.length === 1 ? 'atraso' : 'atrasos'}`, (lista.length > 1 ? lista.slice(0, -1).join(', ') + ' y ' + lista[lista.length - 1] : lista[0]) + '.']);
    }
    if (heAprob.length || hePend.length) {
      hechos.push(['ext', 'Horas extra', (heAprob.length ? `${hms(heMin)} aprobadas en ${heAprob.length} ${heAprob.length === 1 ? 'día' : 'días'}` : 'Ninguna aprobada') + (hePend.length ? `; ${hePend.length} ${hePend.length === 1 ? 'día' : 'días'} por decidir.` : '.')]);
    }
    const listaHechos = hechos.length ? hechos.map(([k, a, b]) => `<li class="fp-h fp-h-${k}"><b>${esc(a)}</b><span>${esc(b)}</span></li>`).join('')
      : '<li class="fp-h"><b>Sin novedades</b><span>Todos los días del tramo están normales.</span></li>';

    document.getElementById('fp-cuerpo').innerHTML = `
      <div class="fp-cifras">${cifras.map(([a, b, c]) => `<div class="fp-cifra"><span>${esc(a)}</span><b>${esc(b)}</b><small>${esc(c)}</small></div>`).join('')}</div>
      <div class="fp-cols">
        <section class="fp-cal" aria-label="Calendario del tramo">
          <h6>${esc(t.mes_cierre)} · tramo ${esc(ddmm(t.fecha_inicio))} al ${esc(ddmm(t.fecha_fin))}</h6>
          <div class="fp-sem">${DIAS.map((x) => `<span>${x}</span>`).join('')}</div>
          <div class="fp-dias">${celdas}</div>
          ${detalle}
        </section>
        <section class="fp-pasos" aria-label="Lo que pasó en el tramo">
          <h6>Lo que pasó en el tramo</h6>
          <ul>${listaHechos}</ul>
        </section>
      </div>`;
  }

  window.FichaPersona = { abrir };
})();
