// Sidebar con riel: modos expanded | rail | auto (solo escritorio). Ver css/sidebar-riel.css
// El modo se elige en el menú «Menú lateral · Cómo se muestra» del pie (diseño HD aprobado, 03-11-2026).
(function () {
  'use strict';
  var KEY = 'sidebar-mode';
  var MODES = ['expanded', 'rail', 'auto'];
  var OPCIONES = [
    ['expanded', 'Expandido', 'Íconos con su nombre completo'],
    ['rail', 'Riel', 'Ícono y nombre corto'],
    ['auto', 'Se oculta solo', 'Se abre al pasar el puntero']
  ];

  function read() {
    try { var m = localStorage.getItem(KEY); return MODES.indexOf(m) >= 0 ? m : 'rail'; }
    catch (e) { return 'rail'; }
  }
  function apply(mode, persist) {
    document.body.setAttribute('data-sidebar', mode);
    if (persist) { try { localStorage.setItem(KEY, mode); } catch (e) {} }
    document.querySelectorAll('.sb-menu [data-mode]').forEach(function (b) {
      b.setAttribute('aria-checked', String(b.dataset.mode === mode));
    });
    // la grilla calcula columnas fijas en JS: avisarle que cambió el ancho disponible
    setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 60);
  }
  function init() {
    var sidebar = document.querySelector('.sidebar');
    var footer = sidebar && sidebar.querySelector('.sidebar-footer');
    if (!sidebar || !footer || footer.querySelector('.sb-modo')) return;

    sidebar.querySelectorAll('.sidebar-item').forEach(function (a) {
      var t = a.querySelector('span:not(.icon)');
      if (t) a.setAttribute('data-label', t.textContent.trim());
    });

    var box = document.createElement('div');
    box.className = 'sb-modo';
    box.innerHTML = '<button type="button" class="sb-modo-b" aria-haspopup="menu" aria-expanded="false" title="Cómo se muestra el menú lateral">'
      + '<i class="bi bi-layout-sidebar" aria-hidden="true"></i><span>Menú lateral</span></button>'
      + '<div class="sb-menu" role="menu" aria-label="Cómo se muestra el menú lateral" hidden>'
      + '<div class="sb-menu-h"><b>Menú lateral</b><span>Cómo se muestra</span></div>'
      + OPCIONES.map(function (o) {
        return '<button type="button" role="menuitemradio" data-mode="' + o[0] + '" aria-checked="false"><span><b>' + o[1] + '</b><small>' + o[2] + '</small></span><i class="bi bi-check-lg" aria-hidden="true"></i></button>';
      }).join('') + '</div>';
    footer.appendChild(box);
    var boton = box.querySelector('.sb-modo-b'), menu = box.querySelector('.sb-menu');
    function abrir(si) {
      menu.hidden = !si;
      boton.setAttribute('aria-expanded', String(si));
      if (si) {
        // El menú sale a la derecha del pie, fuera del riel, para que no se corte
        var r = boton.getBoundingClientRect();
        menu.style.left = Math.round(r.right + 10) + 'px';
        menu.style.bottom = Math.max(12, Math.round(window.innerHeight - r.bottom)) + 'px';
        var marcado = menu.querySelector('[aria-checked="true"]') || menu.querySelector('[data-mode]');
        if (marcado) marcado.focus();
      }
    }
    boton.addEventListener('click', function () { abrir(menu.hidden); });
    menu.addEventListener('click', function (e) {
      var b = e.target.closest('[data-mode]');
      if (!b) return;
      apply(b.dataset.mode, true);
      abrir(false);
      boton.focus();
    });
    document.addEventListener('click', function (e) { if (!menu.hidden && !box.contains(e.target)) abrir(false); });
    document.addEventListener('keydown', function (e) {
      if (menu.hidden) return;
      if (e.key === 'Escape') { abrir(false); boton.focus(); return; }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        var bs = Array.prototype.slice.call(menu.querySelectorAll('[data-mode]'));
        var i = bs.indexOf(document.activeElement);
        bs[(i + (e.key === 'ArrowDown' ? 1 : bs.length - 1)) % bs.length].focus();
        e.preventDefault();
      }
    });
    apply(read(), false);

    // Ctrl+B alterna expandida ↔ riel
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'b') {
        var t = e.target;
        if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
        e.preventDefault();
        apply(document.body.getAttribute('data-sidebar') === 'expanded' ? 'rail' : 'expanded', true);
      }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
