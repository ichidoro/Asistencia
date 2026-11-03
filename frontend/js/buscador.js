// Buscador rápido de la barra superior (Ctrl K): personas, días, acciones y pantallas («Buscar persona, día o acción»).
// Una pantalla se abre como desde el menú; una persona abre su ficha del tramo (o Empleados con su nombre ya buscado);
// una fecha (07-10, 7/10/2026, hoy, ayer) abre ese día de la persona o el tramo en Asistencia; una acción hace lo
// mismo que su botón de siempre (Cerrar el período, Sincronizar, pestañas de Configuración…).
// Solo lee: no guarda nada por sí mismo. Estilos en css/riel.css.
(function () {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const plano = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const titulo = (n) => (typeof window.nombreTitulo === 'function' ? window.nombreTitulo(n) : n) || '';
  const puede = (p) => (typeof AuthService !== 'undefined' && AuthService.hasPermission ? AuthService.hasPermission(p) : true);
  const pad = (n) => String(n).padStart(2, '0');
  const isoLocal = (d) => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  const dmy = (f) => String(f || '').split('-').reverse().join('-');
  const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  const TEXTO = 'Buscar persona, día o acción';
  let velo = null, input = null, lista = null, items = [], marcado = 0, espera = null, turno = 0, personas = [];

  function iniciales(nombre) {
    const p = String(nombre || '').trim().split(/\s+/).filter((t) => t && t !== '.');
    const ini = p.length >= 3 ? p[2][0] + p[0][0] : p.length === 2 ? p[1][0] + p[0][0] : (p[0] || '—').slice(0, 2);
    return ini.toUpperCase();
  }
  function pantallas() {
    return [...document.querySelectorAll('.sidebar-nav .sidebar-item[data-page]')]
      .filter((a) => getComputedStyle(a).display !== 'none' && !a.hidden)
      .map((a) => {
        const t = a.querySelector('.icon + span');
        return { tipo: 'pantalla', titulo: (t ? t.textContent : a.textContent).trim(), page: a.dataset.page, el: a };
      });
  }
  function hayPantalla(page) { return pantallas().some((p) => p.page === page); }

  // Separa una fecha escrita (07-10, 7/10/2026, hoy, ayer, anteayer) del resto del texto, que se busca como nombre.
  // Sin año, una fecha posterior a hoy se entiende del año pasado (lo que se busca ya pasó).
  function partes(texto) {
    let t = String(texto || ''), fecha = null;
    const hoy = new Date(); hoy.setHours(12, 0, 0, 0);
    const m = t.match(/(^|\s)(\d{1,2})[-/.](\d{1,2})(?:[-/.](\d{4}|\d{2}))?(?=\s|$)/);
    if (m) {
      const d = parseInt(m[2], 10), mes = parseInt(m[3], 10);
      let a = m[4] ? parseInt(m[4], 10) : hoy.getFullYear();
      if (a < 100) a += 2000;
      const f = new Date(a, mes - 1, d, 12);
      if (f.getDate() === d && f.getMonth() === mes - 1) {
        if (!m[4] && f > hoy) f.setFullYear(a - 1);
        fecha = isoLocal(f);
        t = t.replace(m[0], ' ');
      }
    } else {
      const w = plano(t).match(/(^|\s)(hoy|ayer|anteayer)(?=\s|$)/);
      if (w) {
        const f = new Date(hoy);
        f.setDate(f.getDate() - { hoy: 0, ayer: 1, anteayer: 2 }[w[2]]);
        fecha = isoLocal(f);
        t = t.replace(new RegExp('(^|\\s)' + w[2] + '(?=\\s|$)', 'i'), ' ');
      }
    }
    return { fecha: fecha, texto: t.replace(/\s+/g, ' ').trim() };
  }
  function diaLargo(f) { const d = new Date(f + 'T12:00:00'); return DIAS[d.getDay()] + ' ' + dmy(f); }

  // ── Acciones: hacen lo mismo que su botón de siempre, en su pantalla ──
  function pestana(sel) { return () => { const b = document.querySelector(sel); if (b) b.click(); }; }
  function hay(sel) { return () => !!document.querySelector(sel); }
  const barraAsistencia = '#page-marcaciones #btn-por-revisar';
  const ACCIONES = [
    { titulo: 'Sincronizar las marcas con BioAlba', palabras: 'sincronizar bioalba marcas reloj traer', page: 'marcaciones', icono: 'cloud-download',
      listo: () => !!document.querySelector(barraAsistencia) && typeof window.syncMarcacionesBioAlba === 'function', run: () => window.syncMarcacionesBioAlba() },
    { titulo: 'Sincronizar solo algunas áreas', palabras: 'sincronizar areas bioalba elegir', page: 'marcaciones', icono: 'funnel',
      listo: () => !!document.querySelector(barraAsistencia) && typeof window.openSyncMarcacionesModal === 'function', run: () => window.openSyncMarcacionesModal() },
    { titulo: 'Ver los días por revisar', palabras: 'revisar por revisar pendientes reglas marcas', page: 'marcaciones', icono: 'exclamation-triangle',
      listo: () => !!document.querySelector(barraAsistencia) && typeof window.abrirPanelPorRevisar === 'function', run: () => window.abrirPanelPorRevisar() },
    { titulo: 'Cerrar el período', palabras: 'cerrar cierre periodo tramo mes', page: 'marcaciones', icono: 'shield-lock', permiso: 'marcaciones.cierre_periodo',
      listo: () => !!document.querySelector(barraAsistencia) && typeof window.openCierrePeriodoModal === 'function', run: () => window.openCierrePeriodoModal() },
    { titulo: 'Historial de cierres', palabras: 'historial cierres periodos cerrados quien cerro', page: 'marcaciones', icono: 'clock-history',
      listo: () => !!document.querySelector(barraAsistencia) && typeof window.openHistorialCierresModal === 'function', run: () => window.openHistorialCierresModal() },
    { titulo: 'Descargar la asistencia en Excel', palabras: 'excel exportar descargar asistencia planilla', page: 'marcaciones', icono: 'file-earmark-spreadsheet',
      listo: () => !!document.querySelector(barraAsistencia) && typeof window.downloadExcelReport === 'function', run: () => window.downloadExcelReport() },
    { titulo: 'Activar el modo perdonazos', palabras: 'perdonazo perdonazos condonar atrasos', page: 'marcaciones', icono: 'gift',
      listo: hay('#perdonazo-switch'), run: () => { const s = document.getElementById('perdonazo-switch'); if (s && !s.checked) s.click(); } },
    { titulo: 'Nueva persona', palabras: 'nueva persona empleado crear agregar ficha', page: 'empleados', icono: 'person-plus', permiso: 'empleados.crear',
      listo: hay('#btn-nuevo-empleado'), run: pestana('#btn-nuevo-empleado') },
    { titulo: 'Contratos por vencer', palabras: 'contratos vencer vencimiento plazo renovar', page: 'empleados', icono: 'file-earmark-text',
      listo: hay('[data-bs-target="#tab-contratos"]'), run: pestana('[data-bs-target="#tab-contratos"]') },
    { titulo: 'Cumpleaños', palabras: 'cumpleanos cumpleaños celebraciones', page: 'empleados', icono: 'gift',
      listo: hay('[data-bs-target="#tab-cumpleanos-emp"]'), run: pestana('[data-bs-target="#tab-cumpleanos-emp"]') },
    { titulo: 'Turnos asignados', palabras: 'turnos asignados horarios personas', page: 'empleados', icono: 'calendar2-week',
      listo: hay('[data-bs-target="#tab-asignaciones-emp"]'), run: pestana('[data-bs-target="#tab-asignaciones-emp"]') },
    { titulo: 'Asignación masiva de turnos', palabras: 'asignacion masiva turnos varias personas', page: 'empleados', icono: 'arrow-repeat',
      listo: hay('#page-empleados [onclick*="loadBulkData"]'), run: pestana('#page-empleados [onclick*="loadBulkData"]') },
    { titulo: 'Registrar una visita', palabras: 'visita visitas cedula registrar porteria', page: 'porteria', icono: 'person-badge', permiso: 'porteria.visitas',
      listo: () => !!window.PorteriaPanel, run: () => window.PorteriaPanel.mostrar('visitas') },
    { titulo: 'Entregar o recibir una llave', palabras: 'llave llaves entregar recibir devolver porteria', page: 'porteria', icono: 'key', permiso: 'porteria.llaves',
      listo: () => !!window.PorteriaPanel, run: () => window.PorteriaPanel.mostrar('llaves') },
    { titulo: 'Artículo 22', palabras: 'articulo 22 art22 entrada salida jefatura porteria', page: 'porteria', icono: 'person-check', permiso: 'porteria.art22',
      listo: () => !!window.PorteriaPanel, run: () => window.PorteriaPanel.mostrar('art22') },
    { titulo: 'Flota: salida o regreso de un vehículo', palabras: 'flota vehiculo camion patente despacho regreso porteria', page: 'porteria', icono: 'truck', permiso: 'porteria.flota',
      listo: () => !!window.PorteriaPanel, run: () => window.PorteriaPanel.mostrar('flota') },
    { titulo: 'Hacer la ronda', palabras: 'ronda rondas qr hallazgo guardia porteria', page: 'porteria', icono: 'shield-check', permiso: 'porteria.rondas',
      listo: () => !!window.PorteriaPanel, run: () => window.PorteriaPanel.mostrar('rondas') }
  ];
  // Configuración: cada pestaña de su menú agrupado («Configuración · Turnos»)
  function accionesConfig() {
    return [...document.querySelectorAll('#page-configuracion .cfg-item[data-bs-target]')]
      .filter((b) => b.style.display !== 'none' && !b.hidden && (!b.dataset.permiso || puede(b.dataset.permiso)))
      .map((b) => {
        const t = b.textContent.replace(/\s+/g, ' ').trim(), sel = '#page-configuracion .cfg-item[data-bs-target="' + b.dataset.bsTarget + '"]';
        return { titulo: 'Configuración · ' + t, palabras: 'configuracion ajustes ' + t, page: 'configuracion', icono: 'gear', listo: hay(sel), run: pestana(sel) };
      });
  }
  function accionesQue(q) {
    const palabras = plano(q).split(' ').filter(Boolean);
    if (!palabras.length || plano(q).length < 2) return [];
    return ACCIONES.concat(accionesConfig())
      .filter((a) => hayPantalla(a.page) && (!a.permiso || puede(a.permiso)))
      .filter((a) => { const h = plano(a.titulo + ' ' + a.palabras); return palabras.every((p) => h.indexOf(p) !== -1); })
      .slice(0, 6)
      .map((a) => Object.assign({ tipo: 'accion' }, a));
  }
  function irYHacer(a) {
    const activa = document.querySelector('#page-' + a.page + '.active');
    const ir = document.querySelector('.sidebar-nav .sidebar-item[data-page="' + a.page + '"]');
    if (!activa && ir) ir.click();
    let n = 0;
    (function intentar() {
      if (a.listo()) { try { a.run(); } catch (e) { console.error('Buscador:', e); } return; }
      if (++n > 50) return;
      setTimeout(intentar, 160);
    })();
  }
  // El tramo que contiene la fecha, elegido en Asistencia como si se eligiera en su lista
  function abrirTramo(fecha) {
    irYHacer({
      page: 'marcaciones',
      listo: () => { const s = document.getElementById('rrhh-periodo-select'); return !!(s && s.options.length > 1 && typeof window.cambiarPeriodoFiltro === 'function'); },
      run: () => {
        const s = document.getElementById('rrhh-periodo-select');
        const op = [...s.options].find((o) => { const p = o.value.split('|'); return p.length === 2 && p[0] <= fecha && fecha <= p[1]; });
        if (!op) { if (typeof showToast === 'function') showToast('No hay un tramo configurado que contenga el ' + dmy(fecha) + '.', 'warning'); return; }
        if (s.value !== op.value) { s.value = op.value; window.cambiarPeriodoFiltro(op.value); }
      }
    });
  }

  function armar() {
    if (velo) return;
    velo = document.createElement('div');
    velo.className = 'bq-velo';
    velo.hidden = true;
    velo.innerHTML = '<div class="bq" role="dialog" aria-modal="true" aria-label="' + TEXTO + '">'
      + '<div class="bq-campo"><i class="bi bi-search" aria-hidden="true"></i>'
      + '<input type="search" placeholder="' + TEXTO + '" aria-label="' + TEXTO + '" autocomplete="off" role="combobox" aria-expanded="true" aria-controls="bq-lista">'
      + '<kbd>Esc</kbd></div>'
      + '<div class="bq-lista" id="bq-lista" role="listbox"></div>'
      + '<div class="bq-pie"><span>↑ ↓ para moverse</span><span>Enter para abrir</span><span>Esc para cerrar</span></div></div>';
    document.body.appendChild(velo);
    input = velo.querySelector('input');
    lista = velo.querySelector('.bq-lista');
    velo.addEventListener('mousedown', (e) => { if (e.target === velo) cerrar(); });
    input.addEventListener('input', () => { pintar(); pedirPersonas(); });
    input.addEventListener('keydown', teclas);
    lista.addEventListener('click', (e) => {
      const b = e.target.closest('.bq-it');
      if (b) abrirItem(items[Number(b.dataset.i)]);
    });
    lista.addEventListener('mousemove', (e) => {
      const b = e.target.closest('.bq-it');
      if (b && Number(b.dataset.i) !== marcado) { marcado = Number(b.dataset.i); marcar(); }
    });
  }

  function abrir() {
    armar();
    personas = [];
    velo.hidden = false;
    input.value = '';
    pintar();
    setTimeout(() => input.focus(), 0);
  }
  function cerrar() {
    if (!velo || velo.hidden) return;
    velo.hidden = true;
    clearTimeout(espera);
    const b = document.getElementById('hd-buscar');
    if (b) b.focus();
  }

  function pedirPersonas() {
    clearTimeout(espera);
    const q = partes(input.value).texto;
    if (q.length < 2 || !puede('empleados.ver')) { personas = []; pintar(); return; }
    const mio = ++turno;
    espera = setTimeout(async () => {
      try {
        const base = typeof API_BASE_URL !== 'undefined' ? API_BASE_URL : '/api';
        const r = await fetch(base + '/empleados/search/?skip=0&limit=8&q=' + encodeURIComponent(q));
        if (!r.ok || mio !== turno) return;
        const d = await r.json();
        personas = (d.empleados || []).map((e) => ({ tipo: 'persona', titulo: titulo(e.nombre_completo), nombre: e.nombre_completo, id: e.id, sub: [e.area, e.cargo].filter(Boolean).join(' · ') + (e.activo === false || e.activo === 0 ? ' · inactiva' : '') }));
        pintar();
      } catch (e) { /* sin conexión: quedan las pantallas y las acciones */ }
    }, 220);
  }

  function boton(i, icono, cuerpo, ir, extra) {
    return '<button type="button" class="bq-it" role="option" id="bq-op-' + i + '" data-i="' + i + '">' + (extra || '<span class="bq-ic"><i class="bi bi-' + icono + '" aria-hidden="true"></i></span>')
      + '<span>' + cuerpo + '</span><span class="bq-ir">' + esc(ir) + '</span></button>';
  }
  function pintar() {
    const crudo = input.value.trim(), pz = partes(crudo), q = plano(pz.texto);
    const verAsistencia = puede('marcaciones.ver') && hayPantalla('marcaciones');
    const pant = pz.fecha ? [] : pantallas().filter((p) => !q || plano(p.titulo).includes(q));
    const acc = pz.fecha ? [] : accionesQue(pz.texto);
    const dias = (pz.fecha && verAsistencia) ? [{ tipo: 'tramo', fecha: pz.fecha }] : [];
    const pers = pz.texto.length >= 2 ? personas : [];
    // Con nombre y fecha, la persona va primero: lo más probable es que se busque su día
    const personasPrimero = !!(pz.fecha && pers.length);
    items = personasPrimero ? [...pers, ...dias] : [...dias, ...pant, ...acc, ...pers];
    marcado = Math.min(marcado, Math.max(0, items.length - 1));
    if (!crudo) marcado = 0;
    let html = '', i = 0;
    const grupoPersonas = () => {
      if (!pers.length) return;
      html += '<div class="bq-grupo">Personas</div>';
      const ir = pz.fecha && puede('marcaciones.ver') ? 'Ver el ' + dmy(pz.fecha).slice(0, 5) : (puede('marcaciones.ver') ? 'Ver su tramo' : 'Ver en Empleados');
      html += pers.map((p) => boton(i++, '', '<b>' + esc(p.titulo) + '</b><small>' + esc(p.sub) + '</small>', ir,
        '<span class="bq-ic vn-av td-t' + ((Math.abs(parseInt(p.id, 10) || 0) % 6) + 1) + '" aria-hidden="true">' + esc(iniciales(p.nombre)) + '</span>')).join('');
    };
    if (personasPrimero) grupoPersonas();
    if (dias.length) {
      html += '<div class="bq-grupo">Día</div>';
      html += boton(i++, 'calendar3', '<b>Abrir el tramo del ' + esc(diaLargo(pz.fecha)) + '</b><small>En Asistencia, con las personas de su área</small>', 'Abrir');
      if (!pz.texto) html += '<div class="bq-nota">Escriba también un nombre para abrir el día de una persona; por ejemplo, «riquelme ' + esc(dmy(pz.fecha).slice(0, 5)) + '».</div>';
    }
    if (pant.length) {
      html += '<div class="bq-grupo">Pantallas</div>';
      html += pant.map((p) => boton(i++, 'window', '<b>' + esc(p.titulo) + '</b>', 'Abrir')).join('');
    }
    if (acc.length) {
      html += '<div class="bq-grupo">Acciones</div>';
      html += acc.map((a) => boton(i++, a.icono, '<b>' + esc(a.titulo) + '</b>', 'Hacer')).join('');
    }
    if (!personasPrimero) grupoPersonas();
    if (!items.length) {
      html = '<div class="bq-vacio">' + (crudo.length >= 2
        ? 'No hay pantallas, acciones ni personas con «' + esc(crudo) + '».'
        : 'Escriba un nombre, una fecha (por ejemplo 07-10) o lo que quiere hacer (por ejemplo «cerrar período»).') + '</div>';
    }
    lista.innerHTML = html;
    marcar();
  }
  function marcar() {
    lista.querySelectorAll('.bq-it').forEach((b) => {
      const si = Number(b.dataset.i) === marcado;
      b.setAttribute('aria-selected', si ? 'true' : 'false');
      if (si) { b.scrollIntoView({ block: 'nearest' }); input.setAttribute('aria-activedescendant', b.id); }
    });
  }
  function teclas(e) {
    if (e.key === 'Escape') { e.preventDefault(); cerrar(); return; }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!items.length) return;
      marcado = (marcado + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length;
      marcar();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (items[marcado]) abrirItem(items[marcado]);
    }
  }

  function abrirItem(it) {
    if (!it) return;
    const fecha = partes(input.value).fecha;
    cerrar();
    if (it.tipo === 'pantalla') { it.el.click(); return; }
    if (it.tipo === 'accion') { irYHacer(it); return; }
    if (it.tipo === 'tramo') { abrirTramo(it.fecha); return; }
    if (puede('marcaciones.ver') && window.FichaPersona) { window.FichaPersona.abrir(it.id, fecha || undefined); return; }
    // Persona sin permiso de asistencia: Empleados con su nombre en el buscador de la lista
    const ir = document.querySelector('.sidebar-nav .sidebar-item[data-page="empleados"]');
    if (ir) ir.click();
    setTimeout(() => {
      const campo = document.getElementById('search-input');
      if (!campo) return;
      campo.value = String(it.nombre || '').trim();
      if (typeof window.loadEmpleados === 'function') window.loadEmpleados();
      else campo.dispatchEvent(new Event('input', { bubbles: true }));
    }, 450);
  }

  function init() {
    const b = document.getElementById('hd-buscar');
    if (b) b.addEventListener('click', abrir);
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (velo && !velo.hidden) cerrar(); else abrir();
      }
    });
  }
  window.Buscador = { abrir, cerrar, partes };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
