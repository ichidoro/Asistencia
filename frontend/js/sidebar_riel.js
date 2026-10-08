// Sidebar con riel: modos expanded | rail | auto (solo escritorio). Ver css/sidebar-riel.css
(function () {
  'use strict';
  var KEY = 'sidebar-mode';
  var MODES = ['expanded', 'rail', 'auto'];

  function read() {
    try { var m = localStorage.getItem(KEY); return MODES.indexOf(m) >= 0 ? m : 'expanded'; }
    catch (e) { return 'expanded'; }
  }
  function apply(mode, persist) {
    document.body.setAttribute('data-sidebar', mode);
    if (persist) { try { localStorage.setItem(KEY, mode); } catch (e) {} }
    document.querySelectorAll('.sb-modes button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.mode === mode));
    });
    // la grilla calcula columnas fijas en JS: avisarle que cambió el ancho disponible
    setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 60);
  }
  function init() {
    var sidebar = document.querySelector('.sidebar');
    var footer = sidebar && sidebar.querySelector('.sidebar-footer');
    if (!sidebar || !footer || footer.querySelector('.sb-modes')) return;

    sidebar.querySelectorAll('.sidebar-item').forEach(function (a) {
      var t = a.querySelector('span:not(.icon)');
      if (t) a.setAttribute('data-label', t.textContent.trim());
    });

    var box = document.createElement('div');
    box.className = 'sb-modes';
    box.setAttribute('role', 'group');
    box.setAttribute('aria-label', 'Modo de la barra lateral');
    [
      ['expanded', 'bi-layout-sidebar-inset', 'Expandida'],
      ['rail', 'bi-layout-sidebar', 'Riel (solo íconos)'],
      ['auto', 'bi-eye-slash', 'Auto-ocultar (se abre al pasar el mouse)']
    ].forEach(function (d) {
      var b = document.createElement('button');
      b.type = 'button'; b.dataset.mode = d[0]; b.title = d[2]; b.setAttribute('aria-label', d[2]);
      b.innerHTML = '<i class="bi ' + d[1] + '" aria-hidden="true"></i>';
      b.addEventListener('click', function () { apply(d[0], true); });
      box.appendChild(b);
    });
    footer.appendChild(box);
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
