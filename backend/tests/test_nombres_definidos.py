"""Ningún nombre usado en el servidor queda sin definir (auditoría, etapa 4, 16-11-2026).

Al mover consultas de un router a su repositorio se borró una línea `db = …` que más abajo se seguía usando: el
recálculo al cambiar un turno fallaba en silencio (lo atrapó el ensayo antes de subir). Esta prueba revisa todo
backend/ con el analizador de Python (symtable), que entiende funciones internas y lambdas: un nombre que se lee como
global tiene que existir en el módulo o ser propio de Python.
"""
import builtins
import symtable
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _archivos():
    for p in sorted((RAIZ / "backend").rglob("*.py")):
        if "tests" in p.parts or "__pycache__" in p.parts or "mapa_codigo" in p.parts:
            continue
        yield p


def nombres_sin_definir():
    faltan = []
    for p in _archivos():
        texto = p.read_text(encoding="utf-8")
        tabla = symtable.symtable(texto, str(p), "exec")
        del_modulo = {s.get_name() for s in tabla.get_symbols() if s.is_assigned() or s.is_imported()}
        if "__getattr__" in del_modulo or any(s.get_name() == "*" for s in tabla.get_symbols()):
            continue

        def revisar(t):
            for s in t.get_symbols():
                n = s.get_name()
                if s.is_global() and s.is_referenced() and n not in del_modulo and not hasattr(builtins, n) \
                        and n not in ("__file__", "__name__", "__doc__", "__spec__", "__package__"):
                    faltan.append(f"{p.relative_to(RAIZ).as_posix()}: «{n}» en {t.get_name()}")
            for hijo in t.get_children():
                revisar(hijo)
        for hijo in tabla.get_children():
            revisar(hijo)
    return faltan


def test_no_hay_nombres_sin_definir_en_el_servidor():
    faltan = nombres_sin_definir()
    assert faltan == [], "nombres que se usan pero no existen:\n" + "\n".join(faltan)
