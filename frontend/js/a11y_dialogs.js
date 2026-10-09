/* Da nombre accesible a cualquier diálogo (role="dialog" / "alertdialog" y .modal de Bootstrap).
   Usa el título del propio diálogo (aria-labelledby, que sigue al texto si cambia) y, si no hay, un nombre genérico. */
(function () {
  'use strict';
  var seq = 0;
  var SEL = '[role="dialog"],[role="alertdialog"],.modal';

  function nombrar(el) {
    if (!el || el.nodeType !== 1) return;
    if (el.hasAttribute('aria-label') || el.hasAttribute('aria-labelledby')) return;
    var t = el.querySelector('.modal-title, .swal2-title, .modal-header h1, .modal-header h2, .modal-header h3, .modal-header h4, .modal-header h5, .modal-header h6, h1, h2, h3, h4, h5, h6');
    if (t && (t.textContent || '').trim()) {
      if (!t.id) t.id = 'dlg-t-' + (++seq);
      el.setAttribute('aria-labelledby', t.id);
    } else if (el.getAttribute('role') === 'dialog' || el.getAttribute('role') === 'alertdialog' || el.classList.contains('swal2-popup')) {
      el.setAttribute('aria-label', 'Diálogo');
    }
  }

  function barrer(raiz) {
    if (!raiz || raiz.nodeType !== 1) return;
    if (raiz.matches && raiz.matches(SEL)) nombrar(raiz);
    if (raiz.querySelectorAll) raiz.querySelectorAll(SEL).forEach(nombrar);
  }

  function iniciar() {
    barrer(document.body);
    new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        if (m.type === 'attributes') { nombrar(m.target); return; }
        m.addedNodes.forEach(barrer);
      });
    }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['role'] });
    // Bootstrap pone role="dialog" al mostrar el modal: se nombra justo antes de abrirse
    document.addEventListener('show.bs.modal', function (e) { nombrar(e.target); }, true);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
