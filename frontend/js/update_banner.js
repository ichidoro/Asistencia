/**
 * Aviso de "hay una versión nueva" (mismo criterio que el de Nexacol).
 *
 * Cada deploy reinicia la app y cambia su identificador de arranque (/api/version → build). Las pestañas que
 * estaban abiertas siguen con el HTML/JS viejo hasta que se recarguen. Este script compara el build con el
 * que trajo la página (<meta name="app-build">) y, si difiere, muestra una barra con el botón "Recargar ahora".
 *
 * NO recarga sola: un F5 automático a mitad de una edición haría perder lo que la persona tenía escrito.
 * Revisa cada 30 s, y de inmediato al volver a mirar la pestaña (visibilitychange) o reconectar la red.
 */
(function () {
  'use strict';

  var meta = document.querySelector('meta[name="app-build"]');
  var PAGE_BUILD = meta ? meta.getAttribute('content') : null;
  if (!PAGE_BUILD) return;

  var POLL_MS = 30000;
  var SNOOZE_MS = 5 * 60 * 1000;   // "Más tarde" lo oculta 5 min; vuelve a aparecer si sigue desactualizada
  var bar = null;
  var snoozeUntil = 0;
  var newBuild = null;

  function buildBar() {
    var el = document.createElement('div');
    el.className = 'ag-update-bar';
    el.setAttribute('role', 'status');
    el.setAttribute('aria-live', 'polite');

    var icon = document.createElement('i');
    icon.className = 'bi bi-arrow-repeat ag-update-icon';
    icon.setAttribute('aria-hidden', 'true');

    var text = document.createElement('span');
    text.className = 'ag-update-text';
    text.textContent = 'La página se actualizó. Recarga para ver la versión nueva y evitar datos inconsistentes.';

    var reload = document.createElement('button');
    reload.type = 'button';
    reload.className = 'ag-update-btn';
    reload.textContent = 'Recargar ahora';
    reload.addEventListener('click', function () { window.location.reload(); });

    var later = document.createElement('button');
    later.type = 'button';
    later.className = 'ag-update-later';
    later.textContent = 'Más tarde';
    later.setAttribute('aria-label', 'Ocultar el aviso por unos minutos');
    later.addEventListener('click', function () {
      snoozeUntil = Date.now() + SNOOZE_MS;
      hide();
    });

    el.appendChild(icon);
    el.appendChild(text);
    el.appendChild(reload);
    el.appendChild(later);
    return el;
  }

  function show() {
    if (Date.now() < snoozeUntil) return;
    if (!bar) {
      bar = buildBar();
      document.body.appendChild(bar);
    }
    // forzar un frame antes de animar la entrada
    requestAnimationFrame(function () { bar.classList.add('is-visible'); });
  }

  function hide() {
    if (bar) bar.classList.remove('is-visible');
  }

  function check() {
    fetch('/api/version', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || typeof d.build !== 'string') return;
        if (d.build !== PAGE_BUILD) { newBuild = d.build; show(); }
        else if (bar) { hide(); }
      })
      .catch(function () { /* servidor reiniciando o sin red: se reintenta en el próximo ciclo */ });
  }

  setInterval(check, POLL_MS);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') check();
  });
  window.addEventListener('online', check);
  // Chrome puede resucitar una pestaña congelada desde el bfcache: es una foto vieja, se recarga directo.
  window.addEventListener('pageshow', function (e) { if (e.persisted) window.location.reload(); });
  setTimeout(check, 5000);
})();
