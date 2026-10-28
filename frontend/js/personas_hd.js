// Empleados con el diseño HD «Personas»: la pantalla abre directo en la lista (las tarjetas del estado del día quedan en
// Inicio), el filtro por área pasa bajo el buscador y arriba va el total de personas. Solo mueve lo que ya existe:
// los contadores y los chips de área los sigue llenando main.js por su id. Estilos en css/personas.css.
(function () {
  'use strict';
  function init() {
    const pg = document.getElementById('page-empleados');
    if (!pg || pg.dataset.hd) return;
    pg.dataset.hd = '1';
    pg.classList.add('emp-hd');

    // Total de personas (de los mismos contadores que llena main.js)
    const tarjeta = pg.querySelector('#empleadosTabs');
    if (tarjeta) {
      const resumen = document.createElement('div');
      resumen.className = 'emp-resumen';
      resumen.setAttribute('aria-live', 'polite');
      tarjeta.closest('.card').before(resumen);
      const pintar = () => {
        const n = (id) => (document.getElementById(id) || {}).textContent || '0';
        const tot = n('stat-total'), act = String(n('stat-activos')).replace(/\D/g, '') || '0', ina = String(n('stat-inactivos')).replace(/\D/g, '') || '0';
        resumen.innerHTML = `<span><b>${tot}</b> personas</span><span><b>${act}</b> activas</span><span><b>${ina}</b> inactivas</span>`;
      };
      pintar();
      ['stat-total', 'stat-activos', 'stat-inactivos'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) new MutationObserver(pintar).observe(el, { childList: true, characterData: true, subtree: true });
      });
    }

    // El filtro por área, bajo el buscador de la lista
    const areas = document.getElementById('areas-breakdown');
    const barra = pg.querySelector('#tab-lista-empleados .emp-toolbar');
    if (areas && barra) {
      const fila = document.createElement('div');
      fila.className = 'emp-areas';
      fila.setAttribute('role', 'group');
      fila.setAttribute('aria-label', 'Filtrar por área');
      barra.after(fila);
      fila.appendChild(areas);
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
