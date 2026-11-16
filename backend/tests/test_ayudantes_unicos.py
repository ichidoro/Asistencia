"""Guardián de la etapa 2 de la auditoría del 15-11-2026: un solo ayudante por tarea en las pantallas.

Antes había 43 copias de «escapar texto para HTML», «AAAA-MM-DD → DD-MM» e «iniciales», que no respondían igual,
y cinco funciones globales con el mismo nombre en dos archivos (el que carga último reemplaza al otro sin aviso).
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
JS = RAIZ / "frontend" / "js"
NO_PROPIOS = {"dashboard_react.js", "chart.js"}  # paquetes armados, no se escriben a mano


def _archivos_js():
    for p in sorted(JS.glob("*.js")):
        if p.name in NO_PROPIOS or ".min." in p.name:
            continue
        yield p, p.read_text(encoding="utf-8")


def test_ayudantes_define_las_tres_funciones():
    txt = (JS / "ayudantes.js").read_text(encoding="utf-8")
    assert "window.Ayuda = Object.freeze({ esc: esc, ddmm: ddmm, iniciales: iniciales })" in txt


def test_no_hay_otro_escape_html_fuera_de_ayudantes():
    # Toda copia que escapa HTML completo necesita «&amp;»; solo puede estar en ayudantes.js
    con_copia = [p.name for p, txt in _archivos_js() if p.name != "ayudantes.js" and "&amp;" in txt]
    assert con_copia == [], f"escape HTML propio en: {con_copia} (usar window.Ayuda.esc)"


def test_ddmm_e_iniciales_delegan_en_ayuda():
    # El cuerpo (hasta 3 líneas) debe llamar a window.Ayuda o a window.inicialesDe (que es window.Ayuda.iniciales)
    patron = re.compile(r"function\s+(\w*(?:ddmm|DDMM|[Ii]niciales)\w*)\s*\([^)]*\)\s*\{((?:[^\n]*\n?){1,3})")
    # Otras tareas con nombre parecido: m180AcompIniciales recibe «Nombre Apellido» escrito a mano, y la Ficha arma las
    # iniciales desde los campos nombre y apellido_paterno (no adivina por posición)
    otra_tarea = {("marcaciones_manuales.js", "m180AcompIniciales"), ("ficha_persona.js", "iniciales")}
    malas = []
    for p, txt in _archivos_js():
        if p.name == "ayudantes.js":
            continue
        for m in patron.finditer(txt):
            cuerpo = m.group(2)
            if (p.name, m.group(1)) not in otra_tarea and "window.Ayuda." not in cuerpo and "window.inicialesDe" not in cuerpo:
                malas.append(f"{p.name}: {m.group(1)}")
    assert malas == [], f"copias propias de ddmm/iniciales: {malas}"


def test_ayudantes_carga_antes_que_las_pantallas():
    for html, siguientes in (("index.html", ("ui_dialogs.js", "auth.js")), ("login.html", ("auth.js",))):
        txt = (RAIZ / "frontend" / html).read_text(encoding="utf-8")
        pos = txt.find("/static/js/ayudantes.js")
        assert pos >= 0, f"{html} no carga ayudantes.js"
        for s in siguientes:
            assert pos < txt.find(f"/static/js/{s}"), f"{html}: ayudantes.js debe ir antes de {s}"


def test_sin_funciones_globales_repetidas_entre_archivos():
    # Nivel superior del archivo (columna 0): «function X(», «var|let|const X =» y «window.X =»
    patron = re.compile(r"^(?:async\s+)?function\s+(\w+)\s*\(|^(?:var|let|const)\s+(\w+)\s*=|^window\.(\w+)\s*=", re.M)
    donde = {}
    for p, txt in _archivos_js():
        for m in patron.finditer(txt):
            nombre = next(g for g in m.groups() if g)
            donde.setdefault(nombre, set()).add(p.name)
    # nombreTitulo: auth.js lo define solo si falta (respaldo para login.html, que no carga Marcaciones)
    permitidos = {"nombreTitulo"}
    choques = {n: sorted(a) for n, a in donde.items() if len(a) > 1 and n not in permitidos}
    assert choques == {}, f"nombres globales en más de un archivo: {choques}"
