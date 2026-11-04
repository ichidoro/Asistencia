// Menú lateral que se abre al acercar el mouse (solo escritorio). Ver css/fluidez.css
// Ya no hay botón ni modos: siempre cerrado con íconos y se despliega encima del contenido al pasar el puntero
// o al navegar con Tab (04-11-2026). La preferencia vieja «sidebar-mode» se ignora.
(function () {
  'use strict';
  function init() {
    document.body.setAttribute('data-sidebar', 'fluido');
    var sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;
    sidebar.querySelectorAll('.sidebar-item').forEach(function (a) {
      var t = a.querySelector('span:not(.icon)');
      if (t) a.setAttribute('data-label', t.textContent.trim());
    });
    // Un clic con el mouse deja el foco en el enlace; se suelta para que el menú se cierre al sacar el puntero
    sidebar.addEventListener('click', function (e) {
      var a = e.target.closest('.sidebar-item');
      if (a && e.detail > 0) a.blur();
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
