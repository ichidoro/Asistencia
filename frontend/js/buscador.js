// Buscador rápido de la barra superior (Ctrl K): pantallas del menú y personas. Etapa 7 del orden visual común.
// Una pantalla se abre como desde el menú; una persona abre Empleados con su nombre ya buscado.
// Solo lee: no guarda nada. Estilos en css/riel.css.
(function () {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const plano = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const titulo = (n) => (typeof window.nombreTitulo === 'function' ? window.nombreTitulo(n) : n) || '';
  const puede = (p) => (typeof AuthService !== 'undefined' && AuthService.hasPermission ? AuthService.hasPermission(p) : true);
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

  function armar() {
    if (velo) return;
    velo = document.createElement('div');
    velo.className = 'bq-velo';
    velo.hidden = true;
    velo.innerHTML = '<div class="bq" role="dialog" aria-modal="true" aria-label="Buscar persona o pantalla">'
      + '<div class="bq-campo"><i class="bi bi-search" aria-hidden="true"></i>'
      + '<input type="search" placeholder="Buscar persona o pantalla" aria-label="Buscar persona o pantalla" autocomplete="off" role="combobox" aria-expanded="true" aria-controls="bq-lista">'
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
    const q = input.value.trim();
    if (q.length < 2 || !puede('empleados.ver')) { personas = []; pintar(); return; }
    const mio = ++turno;
    espera = setTimeout(async () => {
      try {
        const base = typeof API_BASE_URL !== 'undefined' ? API_BASE_URL : '/api';
        const r = await fetch(`${base}/empleados/search/?skip=0&limit=8&q=${encodeURIComponent(q)}`);
        if (!r.ok || mio !== turno) return;
        const d = await r.json();
        personas = (d.empleados || []).map((e) => ({ tipo: 'persona', titulo: titulo(e.nombre_completo), nombre: e.nombre_completo, id: e.id, sub: [e.area, e.cargo].filter(Boolean).join(' · ') + (e.activo === false || e.activo === 0 ? ' · inactiva' : '') }));
        pintar();
      } catch (e) { /* sin conexión: quedan solo las pantallas */ }
    }, 220);
  }

  function pintar() {
    const q = plano(input.value.trim());
    const pant = pantallas().filter((p) => !q || plano(p.titulo).includes(q));
    items = [...pant, ...personas];
    marcado = Math.min(marcado, Math.max(0, items.length - 1));
    if (!q) marcado = 0;
    let html = '';
    if (pant.length) {
      html += '<div class="bq-grupo">Pantallas</div>';
      html += pant.map((p, i) => `<button type="button" class="bq-it" role="option" id="bq-op-${i}" data-i="${i}"><span class="bq-ic"><i class="bi bi-window" aria-hidden="true"></i></span><span><b>${esc(p.titulo)}</b></span><span class="bq-ir">Abrir</span></button>`).join('');
    }
    if (personas.length) {
      html += '<div class="bq-grupo">Personas</div>';
      html += personas.map((p, k) => `<button type="button" class="bq-it" role="option" id="bq-op-${pant.length + k}" data-i="${pant.length + k}"><span class="bq-ic vn-av td-t${(Math.abs(parseInt(p.id, 10) || 0) % 6) + 1}" aria-hidden="true">${esc(iniciales(p.nombre))}</span><span><b>${esc(p.titulo)}</b><small>${esc(p.sub)}</small></span><span class="bq-ir">${puede('marcaciones.ver') ? 'Ver su tramo' : 'Ver en Empleados'}</span></button>`).join('');
    }
    if (!items.length) {
      html = `<div class="bq-vacio">${q.length >= 2 ? 'No hay pantallas ni personas con «' + esc(input.value.trim()) + '».' : 'Escriba al menos dos letras para buscar personas.'}</div>`;
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
    cerrar();
    if (it.tipo === 'pantalla') { it.el.click(); return; }
    if (puede('marcaciones.ver') && window.FichaPersona) { window.FichaPersona.abrir(it.id); return; }
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
    const boton = document.getElementById('hd-buscar');
    if (boton) boton.addEventListener('click', abrir);
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (velo && !velo.hidden) cerrar(); else abrir();
      }
    });
  }
  window.Buscador = { abrir, cerrar };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
