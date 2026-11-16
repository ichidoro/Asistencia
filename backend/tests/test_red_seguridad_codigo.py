"""Red de seguridad del código (auditoría del 15-11-2026, etapa 3). Corre siempre, sin la aplicación encendida.

- Sin funciones nuevas sin uso en el servidor: una función cuyo nombre aparece una sola vez en todo el código (su propia
  definición) no la llama nadie. En la etapa 1 se quitaron 18 así.
- Sin dependencias circulares entre módulos del servidor (A importa B y B importa A, de forma directa o por un rodeo):
  hacen que el orden de carga importe y que un cambio chico rompa el arranque.

Lo calcula desde el código, no desde el mapa publicado, para que avise antes de subir y no después.
(Las copias de ayudantes de pantalla las cuida test_ayudantes_unicos.py.)
"""
import ast
import re
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BACKEND = RAIZ / "backend"


def _modulos():
    for p in sorted(BACKEND.rglob("*.py")):
        if "tests" in p.parts or "__pycache__" in p.parts or "mapa_codigo" in p.parts:
            continue
        yield p


def _todo_el_codigo():
    partes = [p.read_text(encoding="utf-8", errors="replace") for p in _modulos()]
    for carpeta, patron in ((RAIZ / "frontend", "*.js"), (RAIZ / "frontend", "*.html"), (RAIZ / "scripts", "*.py"),
                            (BACKEND / "tests", "*.py")):
        partes += [p.read_text(encoding="utf-8", errors="replace") for p in carpeta.rglob(patron)
                   if "node_modules" not in p.parts and ".min." not in p.name]
    return "\n".join(partes)


def funciones_sin_uso():
    todo = _todo_el_codigo()
    cuantas = defaultdict(int)
    for m in re.finditer(r"\b\w+\b", todo):
        cuantas[m.group(0)] += 1
    sin_uso = []
    for p in _modulos():
        rel = p.relative_to(RAIZ).as_posix()
        if "/routers/" in "/" + rel:   # los endpoints los llama el framework por su ruta
            continue
        arbol = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(arbol):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # Con decorador las llama el framework (validadores, eventos, propiedades); los __x__ los llama Python
            if n.decorator_list or n.name.startswith("__"):
                continue
            if cuantas[n.name] <= 1:
                sin_uso.append(f"{rel}:{n.lineno} {n.name}")
    return sin_uso


def _nombre_modulo(p: Path) -> str:
    partes = list(p.relative_to(RAIZ).with_suffix("").parts)
    if partes[-1] == "__init__":
        partes = partes[:-1]
    return ".".join(partes)


def ciclos_de_importacion():
    modulos = {_nombre_modulo(p): p for p in _modulos()}
    aristas = defaultdict(set)
    for nombre, p in modulos.items():
        paquete = nombre if p.name == "__init__.py" else nombre.rsplit(".", 1)[0]
        # Solo los import del nivel superior: los que van dentro de una función ya se cargan tarde a propósito
        for n in ast.parse(p.read_text(encoding="utf-8")).body:
            destinos = []
            if isinstance(n, ast.Import):
                destinos = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                base = n.module or ""
                if n.level:
                    raiz = paquete.split(".")
                    raiz = raiz[: len(raiz) - (n.level - 1)]
                    base = ".".join(raiz + ([base] if base else []))
                destinos = [base] + [base + "." + a.name for a in n.names]
            for d in destinos:
                if d in modulos and d != nombre:
                    aristas[nombre].add(d)
    # Componentes fuertemente conexos (Tarjan): cada uno con más de un módulo es un ciclo
    indice, bajo, pila, en_pila, ciclos, contador = {}, {}, [], set(), [], [0]

    def visitar(v):
        indice[v] = bajo[v] = contador[0]; contador[0] += 1
        pila.append(v); en_pila.add(v)
        for w in sorted(aristas[v]):
            if w not in indice:
                visitar(w); bajo[v] = min(bajo[v], bajo[w])
            elif w in en_pila:
                bajo[v] = min(bajo[v], indice[w])
        if bajo[v] == indice[v]:
            grupo = []
            while True:
                w = pila.pop(); en_pila.discard(w); grupo.append(w)
                if w == v:
                    break
            if len(grupo) > 1:
                ciclos.append(sorted(grupo))

    for v in sorted(modulos):
        if v not in indice:
            visitar(v)
    return ciclos


# Etapa 4 (consultas a los repositorios): routers que ya no hablan directo con la base. Se agrega uno cada vez que se
# ordena; desde entonces sus consultas van en backend/repositories/.
ROUTERS_SIN_SQL = ["flota.py", "llaves.py", "visitas.py", "porteria.py", "productos_4.py", "cierre.py", "sync.py", "empleados.py", "auth.py", "turnos.py"]
LLAMADAS_A_LA_BASE = ("fetch_all", "fetch_one", "execute", "execute_batch", "fetchval", "fetchrow", "fetch")


def test_routers_ordenados_sin_consultas_propias():
    con_sql = []
    for nombre in ROUTERS_SIN_SQL:
        p = BACKEND / "routers" / nombre
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in LLAMADAS_A_LA_BASE):
                continue
            base = n.func.value
            # db.fetch_one(…) o, por el repositorio, repo.db.fetch_one(…)
            if (isinstance(base, ast.Name) and base.id == "db") or (isinstance(base, ast.Attribute) and base.attr == "db"):
                con_sql.append(f"routers/{nombre}:{n.lineno} {ast.unparse(base)}.{n.func.attr}(…)")
    assert con_sql == [], "estas consultas van en su repositorio (backend/repositories/):\n" + "\n".join(con_sql)


def test_sin_funciones_sin_uso_en_el_servidor():
    sin_uso = funciones_sin_uso()
    assert sin_uso == [], "funciones que nadie llama (quitarlas o usarlas):\n" + "\n".join(sin_uso)


def test_sin_dependencias_circulares():
    ciclos = ciclos_de_importacion()
    assert ciclos == [], "módulos que se importan en círculo: " + "; ".join(" ↔ ".join(c) for c in ciclos)
