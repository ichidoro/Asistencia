/* Apila los modales: el que se abre queda por encima de los que ya estaban abiertos (con su velo justo debajo).
   Los z-index fijos de la hoja de estilos (2050/2100/2150, !important) y el velo de apilados (2090/2140) hacían que un
   segundo modal quedara tapado por el primero o por su propio velo: no se podía tocar, marcar casillas ni hacer scroll.
   Sirve para modales Bootstrap (.fade) y custom (.modal.active). El z-index en línea se quita al cerrar. */
(function () {
  'use strict';
  var PASO = 20;

  function z(el) { return parseInt(getComputedStyle(el).zIndex, 10) || 0; }

  function abiertos(excepto) {
    return Array.prototype.filter.call(document.querySelectorAll('.modal.show, .modal:not(.fade).active'), function (m) {
      return m !== excepto;
    });
  }

  function subir(m) {
    var otros = abiertos(m);
    if (!otros.length) return;                       // modal solo: se queda con el z-index de la hoja de estilos
    m.style.removeProperty('z-index');
    var tope = Math.max.apply(null, otros.map(z));
    if (z(m) > tope) return;                         // ya está por encima (ej. 2150 sobre 2050)
    m.style.setProperty('z-index', String(tope + PASO), 'important');
  }

  document.addEventListener('show.bs.modal', function (e) {
    var m = e.target;
    setTimeout(function () {                          // el velo se crea justo después de este evento
      subir(m);
      var vs = document.querySelectorAll('.modal-backdrop'), v = vs[vs.length - 1];
      if (v && vs.length > 1) v.style.setProperty('z-index', String(z(m) - 1), 'important');
    }, 0);
  }, true);
  document.addEventListener('hidden.bs.modal', function (e) { e.target.style.removeProperty('z-index'); }, true);

  // Modales custom: se abren poniendo/quitando la clase .active
  new MutationObserver(function (muts) {
    muts.forEach(function (r) {
      var m = r.target;
      if (m.classList.contains('fade') || !m.classList.contains('modal')) return;
      if (m.classList.contains('active')) subir(m); else m.style.removeProperty('z-index');
    });
  }).observe(document.documentElement, { subtree: true, attributes: true, attributeFilter: ['class'] });
})();
