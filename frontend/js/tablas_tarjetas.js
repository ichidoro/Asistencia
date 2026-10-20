// ─────────────────────────────────────────────────────────────────────────────
// Tarjetas apiladas en teléfono para las tablas de Configuración (etapa C).
//
// En pantallas chicas una tabla ancha obliga a deslizar de lado. Este módulo
// copia el texto de cada encabezado (th) a sus celdas (atributo data-tt) y
// marca la tabla con la clase tt-tarjetas; el CSS de responsive.css usa esa
// marca SOLO bajo 576 px para dibujar cada fila como una tarjeta apilada
// («Etiqueta: valor», una bajo otra). En escritorio y tablet no cambia nada:
// la clase y los atributos son inertes sin la regla @media.
//
// Es genérico: funciona con cualquier tabla presente o futura dentro de
// #page-configuracion, sin tocar los módulos que las dibujan (un observador
// re-anota cuando una pestaña vuelve a dibujar su tabla).
// ─────────────────────────────────────────────────────────────────────────────
(function () {
    const anotar = () => {
        document.querySelectorAll('#page-configuracion table').forEach(t => {
            const ths = [...t.querySelectorAll('thead th')].map(h => (h.textContent || '').replace(/\s+/g, ' ').trim());
            if (!ths.length || !t.tBodies.length) return;
            t.classList.add('tt-tarjetas');
            t.querySelectorAll('tbody tr').forEach(tr => {
                let soloGrupo = tr.cells.length === 1 && tr.cells[0].colSpan > 1;
                if (soloGrupo) tr.classList.add('tt-grupo'); else tr.classList.remove('tt-grupo');
                [...tr.cells].forEach(td => {
                    if (td.colSpan > 1) { td.removeAttribute('data-tt'); return; }
                    const i = td.cellIndex;
                    if (i < ths.length && ths[i]) td.setAttribute('data-tt', ths[i]);
                    else td.removeAttribute('data-tt');
                });
            });
        });
    };
    const arrancar = () => {
        const cont = document.getElementById('page-configuracion');
        if (!cont) return;
        anotar();
        let pendiente = null;
        // Las pestañas redibujan sus tablas al cargar datos: se vuelve a anotar
        // (con una pequeña espera para no correr una vez por cada fila).
        new MutationObserver(() => {
            if (pendiente) return;
            pendiente = setTimeout(() => { pendiente = null; anotar(); }, 250);
        }).observe(cont, { childList: true, subtree: true });
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', arrancar);
    else arrancar();
})();
