# -*- coding: utf-8 -*-
"""Guardián de valores fijos en el cálculo (orden del dueño, 26-10-2026: llevar la aplicación a cero valores escritos en
el código; todo lo que sea una regla se configura desde la pantalla).

Lee los archivos del cálculo y lista cada número escrito en el código, salvo los que nunca son reglas: 0, 1 (enteros),
las conversiones de unidades (60, 3600, 1440, 24, 100), los decimales de un redondeo y las posiciones de un texto.
Cada número que queda tiene que estar en `valores_fijos_motor.json` con su tipo y su motivo:
  · codigo     — un código o tipo, no una cantidad (p. ej. el tipo 3 de perdonazo).
  · logica     — aritmética del propio cálculo (pasos de a dos, fechas, bloques de 15 minutos).
  · precision  — margen para errores de redondeo de la computadora, muy por debajo de un segundo.
  · algoritmo  — peso interno de un cálculo, sin significado para el negocio.
  · respaldo   — valor que se usa solo si falta el ajuste en la base (el ajuste existe y se edita en la pantalla).
  · pendiente  — regla del negocio que todavía está escrita en el código: hay que pasarla a la configuración.
La prueba falla si aparece un número nuevo (hay que pasarlo a la configuración, o declararlo con su motivo), si la lista
trae líneas que ya no existen o si una línea quedó «sin_revisar».

Para rehacer la lista después de un cambio:  python backend/tests/test_guardian_valores_fijos.py --actualizar
(conserva los motivos de las líneas que no cambiaron; las nuevas quedan «sin_revisar» y la prueba falla hasta revisarlas).
"""
import io
import json
import pathlib
import sys
import tokenize

RAIZ = pathlib.Path(__file__).resolve().parents[2]
ARCHIVOS = ["backend/services/quantum_matrix_engine.py", "backend/services/cuadre_service.py"]
LISTA = pathlib.Path(__file__).with_name("valores_fijos_motor.json")
NUNCA_REGLA = {"0", "0.0", "1", "60", "60.0", "3600", "3600.0", "1440", "1440.0", "24", "24.0", "100", "100.0"}
TIPOS = {"codigo", "logica", "precision", "algoritmo", "respaldo", "pendiente"}


def numeros_del_archivo(rel):
    """{línea de código sin espacios al borde: [números]} de un archivo."""
    src = (RAIZ / rel).read_text(encoding="utf-8")
    lineas = src.splitlines()
    toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT)]
    out = {}
    for i, t in enumerate(toks):
        if t.type != tokenize.NUMBER or t.string in NUNCA_REGLA:
            continue
        ant = toks[i - 1].string if i else ""
        sig = toks[i + 1].string if i + 1 < len(toks) else ""
        linea = lineas[t.start[0] - 1].strip()
        if ant in ("[", ":") and sig in (":", "]"):          # posición dentro de un texto: fh[11:16]
            continue
        if ant == "," and sig == ")" and "round(" in linea and t.string.isdigit() and int(t.string) <= 6:
            continue                                         # decimales de un redondeo: round(x, 2)
        out.setdefault(linea, set()).add(t.string)
    return {k: sorted(v) for k, v in out.items()}


def estado_actual():
    return {(rel, linea): nums for rel in ARCHIVOS for linea, nums in numeros_del_archivo(rel).items()}


def cargar_lista():
    if not LISTA.exists():
        return []
    return json.loads(LISTA.read_text(encoding="utf-8"))


def test_no_aparecen_valores_fijos_nuevos_en_el_calculo():
    actual = estado_actual()
    lista = cargar_lista()
    declarados = {(e["archivo"], e["linea"]): e for e in lista}
    nuevos = [f"{rel}: {linea}  →  {nums}" for (rel, linea), nums in actual.items()
              if (rel, linea) not in declarados or declarados[(rel, linea)]["numeros"] != nums]
    sobran = [f"{e['archivo']}: {e['linea']}" for e in lista if (e["archivo"], e["linea"]) not in actual]
    sin_revisar = [f"{e['archivo']}: {e['linea']}" for e in lista if e.get("tipo") not in TIPOS or not e.get("motivo")]
    mensaje = []
    if nuevos:
        mensaje.append("Números nuevos escritos en el cálculo (pásalos a la configuración o decláralos con su motivo):\n  "
                       + "\n  ".join(nuevos))
    if sobran:
        mensaje.append("La lista trae líneas que ya no existen (rehaz la lista con --actualizar):\n  " + "\n  ".join(sobran))
    if sin_revisar:
        mensaje.append("Líneas sin tipo o sin motivo:\n  " + "\n  ".join(sin_revisar))
    assert not mensaje, "\n\n".join(mensaje)


def test_la_lista_de_pendientes_se_informa():
    """No falla: deja a la vista cuántas reglas siguen escritas en el código (para no afirmar «cero» antes de tiempo)."""
    pendientes = [e for e in cargar_lista() if e.get("tipo") == "pendiente"]
    print(f"\nReglas del negocio aún escritas en el código: {len(pendientes)}")
    for e in pendientes:
        print(f"  · {e['archivo']}: {e['motivo']}")


def actualizar():
    previos = {(e["archivo"], e["linea"]): e for e in cargar_lista()}
    nueva = []
    for (rel, linea), nums in estado_actual().items():
        p = previos.get((rel, linea))
        if p and p["numeros"] == nums:
            nueva.append(p)
        else:
            nueva.append({"archivo": rel, "linea": linea, "numeros": nums, "tipo": "sin_revisar", "motivo": ""})
    LISTA.write_text(json.dumps(nueva, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Lista rehecha: {len(nueva)} líneas, {sum(1 for e in nueva if e['tipo'] == 'sin_revisar')} sin revisar")


if __name__ == "__main__":
    if "--actualizar" in sys.argv:
        actualizar()
