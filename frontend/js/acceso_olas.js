// Fondo de la pantalla de entrada: agua en capas que sigue al mouse (04-11-2026).
// - Cinco capas de olas planas (sin degradados) con distinto ritmo; el puntero las empuja y agita el agua cerca de él.
// - Un clic suelta anillos que se expanden desde el punto (el motivo de ondas de la marca).
// - La tarjeta de vidrio recibe un reflejo que sigue al puntero y se inclina apenas.
// - Sin movimiento (prefers-reduced-motion): una sola imagen fija. Se pausa con la pestaña oculta.
(function () {
  'use strict';
  var reducir = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var tactil = window.matchMedia && window.matchMedia('(hover: none)').matches;
  var cv = document.createElement('canvas');
  cv.className = 'ac-olas';
  cv.setAttribute('aria-hidden', 'true');
  document.body.insertBefore(cv, document.body.firstChild);
  document.body.classList.add('ac-con-olas');
  var ctx = cv.getContext('2d');
  if (!ctx) return;

  // base: altura (fracción del alto), amplitud, largo de onda, velocidad, empuje horizontal del mouse, relleno
  var CAPAS = [
    { y: .40, a: 16, l: 520, v: .30, p: 40, c: 'rgba(52, 84, 204, .30)' },
    { y: .52, a: 20, l: 430, v: -.40, p: 70, c: 'rgba(44, 74, 190, .36)' },
    { y: .64, a: 24, l: 360, v: .50, p: 100, c: 'rgba(34, 58, 164, .44)' },
    { y: .75, a: 22, l: 300, v: -.60, p: 140, c: 'rgba(122, 196, 72, .19)' },
    { y: .86, a: 26, l: 260, v: .75, p: 190, c: 'rgba(15, 28, 92, .62)' }
  ];
  var w = 0, h = 0, dpr = 1, t = 0, ultimo = 0, corriendo = false;
  var mouse = { x: .62, y: .5, px: 0, py: 0 };      // destino (0..1 y píxeles)
  var suave = { x: .62, y: .5, vx: 0, vy: 0 };      // posición con resorte
  var energia = 0, anillos = [];
  var tarjeta = null, marca = null;

  function medir() {
    dpr = Math.min(window.devicePixelRatio || 1, tactil ? 1.5 : 2);
    w = window.innerWidth; h = window.innerHeight;
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    mouse.px = mouse.px || w * .62; mouse.py = mouse.py || h * .5;
    if (!corriendo) dibujar(0);
  }

  function dibujar(dt) {
    t += dt;
    // el puntero se acerca con un resorte (sin saltos) y la energía de lo que se movió se apaga sola
    suave.vx += (mouse.x - suave.x) * .06; suave.vy += (mouse.y - suave.y) * .06;
    suave.vx *= .80; suave.vy *= .80;
    suave.x += suave.vx; suave.y += suave.vy;
    energia *= Math.pow(.94, dt * 60);

    ctx.clearRect(0, 0, w, h);
    var paso = w > 900 ? 8 : 12;
    for (var i = 0; i < CAPAS.length; i++) {
      var c = CAPAS[i], prof = (i + 1) / CAPAS.length;
      var base = h * (w < 820 ? c.y * .82 : c.y) + (suave.y - .5) * 22 * prof;   // en celular suben para pasar detrás de la tarjeta
      var desfase = (suave.x - .5) * c.p;
      var k = Math.PI * 2 / c.l;
      var peso = Math.exp(-Math.pow((base - mouse.py) / 170, 2)) * Math.min(1, energia);
      ctx.beginPath();
      ctx.moveTo(0, h);
      for (var x = 0; x <= w + paso; x += paso) {
        var y = base
          + Math.sin(x * k + t * c.v + desfase * .02 * 6.28 + i) * c.a
          + Math.sin(x * k * 2.1 - t * c.v * .7 + i * 2) * c.a * .35;
        // el agua cerca del puntero se agita: una campana de 150 px que ondula
        var d = (x - mouse.px) / 150;
        y += Math.exp(-d * d) * peso * 26 * Math.sin(x * .05 - t * 5);
        ctx.lineTo(x, y);
      }
      ctx.lineTo(w, h); ctx.closePath();
      ctx.fillStyle = c.c; ctx.fill();
      if (i === 3) { ctx.strokeStyle = 'rgba(160, 222, 110, .30)'; ctx.lineWidth = 1.5; ctx.stroke(); }
    }
    // anillos de los clics
    for (var j = anillos.length - 1; j >= 0; j--) {
      var r = anillos[j]; r.r += dt * 260; r.a -= dt * .55;
      if (r.a <= 0) { anillos.splice(j, 1); continue; }
      ctx.beginPath(); ctx.arc(r.x, r.y, r.r, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(160, 222, 110, ' + (r.a * .5).toFixed(3) + ')'; ctx.lineWidth = 1.5; ctx.stroke();
    }
    reflejo();
  }

  // reflejo del vidrio + inclinación mínima + corrimiento de la marca (solo transform/variables CSS)
  function reflejo() {
    if (tarjeta) {
      var r = tarjeta.getBoundingClientRect();
      tarjeta.style.setProperty('--gx', Math.round(mouse.px - r.left) + 'px');
      tarjeta.style.setProperty('--gy', Math.round(mouse.py - r.top) + 'px');
      if (!tactil) tarjeta.style.transform = 'perspective(900px) rotateY(' + ((suave.x - .5) * 3).toFixed(2) + 'deg) rotateX(' + ((.5 - suave.y) * 3).toFixed(2) + 'deg)';
    }
    if (marca && !tactil) marca.style.transform = 'translate3d(' + ((suave.x - .5) * -10).toFixed(1) + 'px,' + ((suave.y - .5) * -8).toFixed(1) + 'px,0)';
  }

  function cuadro(ahora) {
    if (!corriendo) return;
    var dt = Math.min(.05, (ahora - ultimo) / 1000 || 0); ultimo = ahora;
    dibujar(dt);
    requestAnimationFrame(cuadro);
  }
  function arrancar() { if (corriendo || reducir) return; corriendo = true; ultimo = performance.now(); requestAnimationFrame(cuadro); }
  function parar() { corriendo = false; }

  function mover(e) {
    var nx = e.clientX / w, ny = e.clientY / h;
    var dx = e.clientX - mouse.px, dy = e.clientY - mouse.py;
    energia = Math.min(1.4, energia + Math.sqrt(dx * dx + dy * dy) / 260);
    mouse.x = nx; mouse.y = ny; mouse.px = e.clientX; mouse.py = e.clientY;
  }
  function inicio() {
    tarjeta = document.querySelector('.ac-form');
    marca = document.querySelector('.ac-marca-in');
    medir();
    window.addEventListener('resize', medir);
    if (reducir) { dibujar(0); return; }
    window.addEventListener('pointermove', mover, { passive: true });
    window.addEventListener('pointerdown', function (e) {
      mover(e); energia = 1.4;
      anillos.push({ x: e.clientX, y: e.clientY, r: 8, a: 1 }, { x: e.clientX, y: e.clientY, r: 0, a: .7 });
      if (anillos.length > 12) anillos.splice(0, anillos.length - 12);
    }, { passive: true });
    document.addEventListener('visibilitychange', function () { if (document.hidden) parar(); else arrancar(); });
    arrancar();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', inicio); else inicio();
})();
