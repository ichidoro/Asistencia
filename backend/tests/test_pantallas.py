# -*- coding: utf-8 -*-
"""Pantallas (adaptación a dispositivos, etapa D): abre las páginas de la
aplicación en tres tamaños (teléfono 375, tablet 768, escritorio 1920) y FALLA
si hay contenido inalcanzable: un elemento que sobresale del borde derecho sin
ningún marco deslizable que permita llegar a él. En teléfono recorre además las
pestañas de Configuración una por una.

NO corre en la pasada normal de `pytest backend/tests` (se salta sola): necesita
la aplicación ENCENDIDA y Playwright instalado. Nunca apuntarla a producción:
usa la copia de práctica. Cómo correrla antes de una subida que toque pantallas:

  1) Levantar la copia de práctica (base desechable + uvicorn en el puerto 8001).
  2) En la carpeta del proyecto:
       PANTALLAS_URL=http://localhost:8001 PANTALLAS_USUARIO=admin \
       PANTALLAS_CLAVE=<la clave de la copia> \
       .venv/Scripts/python.exe -m pytest backend/tests/test_pantallas.py -q
  (Playwright local: `pip install playwright` y `playwright install chromium`;
   no va en requirements.txt porque el servidor no lo necesita.)

Solo navega y mide: no guarda nada en la aplicación.
"""
import json
import os
import urllib.parse
import urllib.request

import pytest

URL = os.environ.get("PANTALLAS_URL", "").rstrip("/")
USUARIO = os.environ.get("PANTALLAS_USUARIO", "admin")
CLAVE = os.environ.get("PANTALLAS_CLAVE", "")

pytestmark = pytest.mark.skipif(
    not URL, reason="Defina PANTALLAS_URL (y PANTALLAS_CLAVE) con la copia de práctica encendida")

TAMANOS = {"telefono": (375, 812), "tablet": (768, 1024), "escritorio": (1920, 1080)}
PAGINAS = ["dashboard", "empleados", "marcaciones", "reportes", "productos_4", "porteria", "configuracion"]

# Un elemento está CORTADO si sobresale del borde derecho; es INALCANZABLE si
# además ningún ancestro con deslizador lateral (overflow-x auto/scroll con
# recorrido real) puede traerlo a la vista. Se informa solo el ancestro más
# alto de cada grupo, con su ruta y cuántos píxeles quedan fuera.
DETECTOR = r"""
() => {
  const vw = document.documentElement.clientWidth;
  const alcanzable = (el) => {
    let p = el.parentElement;
    while (p && p !== document.body) {
      const cs = getComputedStyle(p);
      if ((cs.overflowX === 'auto' || cs.overflowX === 'scroll') && p.scrollWidth > p.clientWidth + 10) return true;
      p = p.parentElement;
    }
    return false;
  };
  const out = []; const vistos = [];
  for (const el of document.querySelectorAll('.page.active *')) {
    const r = el.getBoundingClientRect();
    if (r.width > 30 && r.right > vw + 6 && r.left < vw && !alcanzable(el)) {
      if (vistos.some(v => v.contains(el))) continue;
      vistos.push(el);
      const ruta = []; let e = el;
      for (let i = 0; i < 3 && e && e !== document.body; i++) {
        ruta.unshift(e.id ? '#' + e.id : e.tagName.toLowerCase() + (e.className ? '.' + String(e.className).trim().split(/\s+/)[0] : ''));
        e = e.parentElement;
      }
      if (out.length < 8) out.push(ruta.join(' > ') + ' +' + Math.round(r.right - vw) + 'px');
    }
  }
  return out;
}
"""

CERRAR_AVISOS = """
() => { const c = document.querySelector('.modal.show .btn-close'); if (c) c.click(); }
"""


def _sesion() -> dict:
    datos = urllib.parse.urlencode({"username": USUARIO, "password": CLAVE}).encode()
    req = urllib.request.Request(
        f"{URL}/api/auth/login/", data=datos,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


@pytest.fixture(scope="module")
def navegador():
    pw = pytest.importorskip(
        "playwright.sync_api", reason="Playwright no instalado (pip install playwright; playwright install chromium)")
    sesion = _sesion()
    usuario = {"user_id": sesion.get("user_id"), "username": sesion.get("username", USUARIO),
               "nombre_completo": sesion.get("nombre_completo", ""), "rol": sesion.get("rol", "")}
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        contexto = browser.new_context()
        # La sesión de la app vive en localStorage (AuthService: 'access_token' y
        # 'auth_user_data'): se siembra antes de que cargue el código de la página.
        contexto.add_init_script(
            f"localStorage.setItem('access_token', {json.dumps(sesion['access_token'])});"
            f"localStorage.setItem('auth_user_data', {json.dumps(json.dumps(usuario))});")
        page = contexto.new_page()
        yield page
        browser.close()


def _preparar(page, ancho, alto):
    page.set_viewport_size({"width": ancho, "height": alto})
    page.goto(URL + "/#/dashboard", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)       # arranque de la SPA y primeras cargas
    page.evaluate(CERRAR_AVISOS)


def _medir_pagina(page, nombre):
    page.evaluate("p => switchPage(p)", nombre)
    page.wait_for_timeout(2600)
    page.evaluate(CERRAR_AVISOS)
    return page.evaluate(DETECTOR)


@pytest.mark.parametrize("tamano", list(TAMANOS))
def test_paginas_sin_contenido_inalcanzable(navegador, tamano):
    ancho, alto = TAMANOS[tamano]
    _preparar(navegador, ancho, alto)
    fallas = {}
    for nombre in PAGINAS:
        hallado = _medir_pagina(navegador, nombre)
        if hallado:
            fallas[nombre] = hallado
    assert not fallas, (
        f"Contenido inalcanzable en {tamano} ({ancho}px): " + json.dumps(fallas, ensure_ascii=False, indent=1))


def test_pestanas_de_configuracion_en_telefono(navegador):
    ancho, alto = TAMANOS["telefono"]
    _preparar(navegador, ancho, alto)
    _medir_pagina(navegador, "configuracion")
    pestanas = navegador.evaluate(
        "() => [...document.querySelectorAll('#configTabs [data-bs-toggle], #configTabs button')]"
        ".map(b => b.textContent.replace(/\\s+/g,' ').trim()).filter(Boolean)")
    assert len(pestanas) >= 10, f"El menú de Configuración no cargó (vi {len(pestanas)} pestañas)"
    fallas = {}
    for p in pestanas:
        navegador.evaluate(
            "t => { const b = [...document.querySelectorAll('#configTabs [data-bs-toggle], #configTabs button')]"
            ".find(x => x.textContent.replace(/\\s+/g,' ').trim() === t); if (b) b.click(); }", p)
        navegador.wait_for_timeout(1500)
        navegador.evaluate(CERRAR_AVISOS)
        hallado = navegador.evaluate(DETECTOR)
        if hallado:
            fallas[p] = hallado
    assert not fallas, "Contenido inalcanzable en Configuración (375px): " + json.dumps(fallas, ensure_ascii=False, indent=1)


def test_el_detector_si_detecta(navegador):
    """Autocomprobación: un elemento cortado a propósito debe ser denunciado
    (si esto fallara, los demás pases en verde no probarían nada)."""
    _preparar(navegador, *TAMANOS["telefono"])
    _medir_pagina(navegador, "dashboard")
    navegador.evaluate(
        "() => { const d = document.createElement('div'); d.id = 'prueba-cortado';"
        " d.style.cssText = 'position:relative;width:900px;height:20px;';"
        " document.querySelector('.page.active').appendChild(d); }")
    hallado = navegador.evaluate(DETECTOR)
    navegador.evaluate("() => document.getElementById('prueba-cortado').remove()")
    assert any("prueba-cortado" in h for h in hallado), f"El detector no vio el elemento de prueba: {hallado}"
