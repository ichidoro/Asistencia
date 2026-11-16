// Ayudantes de pantalla comunes (auditoría del código, etapa 2, 15-11-2026).
// Antes cada pantalla tenía su propia copia y no todas respondían igual (algunas mostraban «null», otras no escapaban
// la comilla simple o no escapaban nada si no se había cargado otro archivo). Ahora hay una sola versión de cada uno; las
// pantallas la llaman con window.Ayuda.<nombre>. Se carga antes que todo lo demás (index.html y login.html).
(function () {
    'use strict';
    var MAPA_HTML = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

    // Texto seguro para poner dentro de HTML (contenido o atributos). Sin valor → texto vacío.
    function esc(t) {
        return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) { return MAPA_HTML[c]; });
    }

    // «AAAA-MM-DD…» → «DD-MM». Lo que no tenga esa forma se devuelve tal cual (sin valor → texto vacío).
    function ddmm(f) {
        var s = String(f == null ? '' : f);
        var m = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(s);
        if (!m) return s;
        var dos = function (x) { return (x.length < 2 ? '0' : '') + x; };
        return dos(m[3]) + '-' + dos(m[2]);
    }

    // Iniciales de una persona escrita «APELLIDO APELLIDO NOMBRE …» → nombre + apellido (las del encabezado de las ventanas)
    function iniciales(s) {
        var p = String(s || '').trim().split(/\s+/).filter(function (t) { return t && t !== '.'; });
        return (p.length >= 3 ? p[2][0] + p[0][0] : p.length === 2 ? p[1][0] + p[0][0] : (p[0] || '—').slice(0, 2)).toUpperCase();
    }

    window.Ayuda = Object.freeze({ esc: esc, ddmm: ddmm, iniciales: iniciales });
})();
