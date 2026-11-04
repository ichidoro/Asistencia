// Fondo de la pantalla de entrada: anillos de agua que se mueven con el mouse (04-11-2026).
// - Anillos redondos de la marca que se expanden despacio desde el logo (el motivo de siempre).
// - Agua simulada de verdad: el puntero deja una estela de ondas circulares, un clic cae como una gota y, de vez en cuando,
//   cae una gota sola. Las ondas rebotan en los bordes, se cruzan y se apagan solas.
// - La tarjeta de vidrio recibe un reflejo que sigue al puntero y se inclina apenas.
// - Sin movimiento (prefers-reduced-motion): anillos fijos. Se pausa con la pestaña oculta.
(function () {
  'use strict';
  var reducir = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var tactil = window.matchMedia && window.matchMedia('(hover: none)').matches;

  // Dos lienzos: los anillos (a la resolución de la pantalla) y el agua (en baja resolución, el navegador la estira suave)
  var anillosCv = document.createElement('canvas'), aguaCv = document.createElement('canvas');
  anillosCv.className = 'ac-olas'; aguaCv.className = 'ac-olas ac-agua';
  anillosCv.setAttribute('aria-hidden', 'true'); aguaCv.setAttribute('aria-hidden', 'true');
  document.body.insertBefore(aguaCv, document.body.firstChild);
  document.body.insertBefore(anillosCv, document.body.firstChild);
  document.body.classList.add('ac-con-olas');
  var ca = anillosCv.getContext('2d'), cw = aguaCv.getContext('2d');
  if (!ca || !cw) return;

  var w = 0, h = 0, dpr = 1, gw = 0, gh = 0, A, B, img;
  var t = 0, ultimo = 0, acum = 0, corriendo = false, gota = 1.2;
  var mouse = { x: .62, y: .5, px: 0, py: 0 };
  var suave = { x: .62, y: .5, vx: 0, vy: 0 };
  var tarjeta = null, marca = null;
  var DIAMETROS = [300, 520, 760, 1020];   // los cuatro anillos de siempre

  function medir() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = window.innerWidth; h = window.innerHeight;
    anillosCv.width = Math.round(w * dpr); anillosCv.height = Math.round(h * dpr);
    ca.setTransform(dpr, 0, 0, dpr, 0, 0);
    var celda = tactil || w < 820 ? 6 : 4;
    gw = Math.max(40, Math.ceil(w / celda)); gh = Math.max(40, Math.ceil(h / celda));
    aguaCv.width = gw; aguaCv.height = gh;
    A = new Float32Array(gw * gh); B = new Float32Array(gw * gh);
    img = cw.createImageData(gw, gh);
    mouse.px = mouse.px || w * .62; mouse.py = mouse.py || h * .5;
    if (!corriendo) dibujar(0);
  }

  // una gota: sube el nivel del agua en un punto (en píxeles de pantalla)
  function gotear(px, py, fuerza, radio) {
    var gx = Math.round(px / w * gw), gy = Math.round(py / h * gh), r = radio || 2;
    for (var y = -r; y <= r; y++) for (var x = -r; x <= r; x++) {
      var i = (gy + y) * gw + gx + x, d = x * x + y * y;
      if (gx + x > 0 && gx + x < gw - 1 && gy + y > 0 && gy + y < gh - 1 && d <= r * r) A[i] += fuerza * (1 - d / (r * r + 1));
    }
  }

  // un paso de la onda: cada celda pasa a ser el promedio de sus vecinas menos lo que valía antes, con un poco de roce
  function paso() {
    for (var y = 1; y < gh - 1; y++) {
      var fila = y * gw;
      for (var x = 1; x < gw - 1; x++) {
        var i = fila + x;
        B[i] = ((A[i - 1] + A[i + 1] + A[i - gw] + A[i + gw]) * .5 - B[i]) * .985;
      }
    }
    var tmp = A; A = B; B = tmp;
  }

  function pintarAgua() {
    var d = img.data;
    for (var y = 1; y < gh - 1; y++) {
      for (var x = 1; x < gw - 1; x++) {
        var i = y * gw + x, o = i * 4;
        // luz desde arriba a la izquierda: la pendiente del agua decide si brilla o se oscurece
        var s = (A[i - 1] - A[i + 1]) + (A[i - gw] - A[i + gw]);
        if (s > 0) { d[o] = 190; d[o + 1] = 235; d[o + 2] = 255; d[o + 3] = s * 1.1 > 150 ? 150 : s * 1.1; }
        else { d[o] = 6; d[o + 1] = 12; d[o + 2] = 52; d[o + 3] = -s * .8 > 120 ? 120 : -s * .8; }
      }
    }
    cw.putImageData(img, 0, 0);
  }

  function pintarAnillos() {
    ca.clearRect(0, 0, w, h);
    // salen desde el logo y se abren despacio; al llegar lejos se apagan. Todos cerca del puntero se avivan un poco.
    var cx = w * (w < 820 ? .30 : .20), cy = h * (w < 820 ? .16 : .58), tam = Math.max(w, h) * .62;
    for (var i = 0; i < DIAMETROS.length; i++) {
      var fase = ((t * 22 + i * (tam / DIAMETROS.length)) % tam) / tam;          // 0..1 de dentro hacia fuera
      var r = 40 + fase * tam, a = Math.sin(Math.PI * Math.min(1, fase * 1.05)) * .22;
      var dm = Math.hypot(mouse.px - cx, mouse.py - cy), cerca = Math.exp(-Math.pow((dm - r) / 90, 2));   // el puntero sobre el anillo lo aviva
      ca.beginPath(); ca.arc(cx, cy, r, 0, Math.PI * 2);
      ca.strokeStyle = 'rgba(140, 214, 90, ' + (a + cerca * .22).toFixed(3) + ')'; ca.lineWidth = 1.5 + cerca * 1.2; ca.stroke();
    }
  }

  function dibujar(dt) {
    t += dt;
    suave.vx += (mouse.x - suave.x) * .06; suave.vy += (mouse.y - suave.y) * .06;
    suave.vx *= .80; suave.vy *= .80; suave.x += suave.vx; suave.y += suave.vy;
    if (!reducir) {
      gota -= dt;
      if (gota <= 0) { gota = 1.8 + Math.random() * 2.2; gotear(w * (.1 + Math.random() * .8), h * (.15 + Math.random() * .75), 260, 2); }
      acum += dt; var n = 0;
      while (acum >= 1 / 60 && n < 3) { paso(); acum -= 1 / 60; n++; }
      if (n === 3) acum = 0;
      pintarAgua();
    }
    pintarAnillos();
    reflejo();
  }

  // reflejo del vidrio + inclinación mínima + corrimiento de la marca (solo transform y variables CSS)
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
    var dx = e.clientX - mouse.px, dy = e.clientY - mouse.py, v = Math.sqrt(dx * dx + dy * dy);
    // la estela: se reparte una gota cada ~14 px del recorrido, más fuerte cuanto más rápido va el puntero
    if (v > 1 && !reducir) {
      var pasos = Math.min(6, Math.ceil(v / 14));
      for (var k = 1; k <= pasos; k++) gotear(mouse.px + dx * k / pasos, mouse.py + dy * k / pasos, Math.min(130, 26 + v * 2), 2);
    }
    mouse.x = e.clientX / w; mouse.y = e.clientY / h; mouse.px = e.clientX; mouse.py = e.clientY;
  }
  function inicio() {
    tarjeta = document.querySelector('.ac-form');
    marca = document.querySelector('.ac-marca-in');
    medir();
    window.addEventListener('resize', medir);
    if (reducir) { dibujar(0); return; }
    window.addEventListener('pointermove', mover, { passive: true });
    window.addEventListener('pointerdown', function (e) {
      mouse.px = e.clientX; mouse.py = e.clientY; mouse.x = e.clientX / w; mouse.y = e.clientY / h;
      gotear(e.clientX, e.clientY, 900, 3);
    }, { passive: true });
    document.addEventListener('visibilitychange', function () { if (document.hidden) parar(); else arrancar(); });
    gotear(w * .55, h * .5, 700, 3);   // una gota al abrir: la pantalla ya llega viva
    arrancar();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', inicio); else inicio();
})();
