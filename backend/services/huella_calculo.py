"""Huella del cálculo: una firma del código que calcula la asistencia (decisión del dueño, 23-11-2026).

Al arrancar con una versión nueva, un día de hoy ya calculado no se volvía a calcular hasta que llegaba una marca nueva, y
seguía mostrando lo que decía el código anterior (el 23-11-2026, la regla de «en curso» con varias marcas no se vio hasta
recalcular a mano). Ahora el arranque compara esta firma con la guardada: si cambió, recalcula una vez el día de hoy; si
no, no hace nada y no cuesta nada.

La firma no sale de una lista escrita a mano (que se olvida): parte del motor y del servicio de asistencia y sigue sus
importaciones dentro de backend (también las que están dentro de funciones). Si un cambio ajeno toca uno de esos archivos,
solo cuesta un recálculo de hoy.
"""
import ast
import hashlib
from pathlib import Path
from typing import Iterable, Set

RAIZ = Path(__file__).resolve().parents[2]
PUNTOS_DE_PARTIDA = ("backend.services.quantum_matrix_engine", "backend.services.asistencia_service")
CLAVE_AJUSTE = "sistema_huella_calculo"


def _archivo(modulo: str) -> Path:
    base = RAIZ.joinpath(*modulo.split("."))
    paquete = base / "__init__.py"
    return paquete if paquete.is_file() else base.with_suffix(".py")


def _importados(archivo: Path) -> Set[str]:
    try:
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    paquete = ".".join(archivo.relative_to(RAIZ).with_suffix("").parts[:-1])
    nombres: Set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.update(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level:
                partes = paquete.split(".")
                base = ".".join(partes[:len(partes) - nodo.level + 1])
                mod = f"{base}.{nodo.module}" if nodo.module else base
            else:
                mod = nodo.module or ""
            nombres.add(mod)
            nombres.update(f"{mod}.{a.name}" for a in nodo.names)   # «from backend.services import x» importa el módulo x
    return {n for n in nombres if n.startswith("backend.") and _archivo(n).is_file()}


def archivos_del_calculo(inicio: Iterable[str] = PUNTOS_DE_PARTIDA) -> Set[Path]:
    """Los archivos que alcanza el cálculo, siguiendo las importaciones desde los puntos de partida."""
    vistos: Set[str] = set()
    pendientes = [m for m in inicio if _archivo(m).is_file()]
    while pendientes:
        m = pendientes.pop()
        if m in vistos:
            continue
        vistos.add(m)
        pendientes.extend(_importados(_archivo(m)) - vistos)
    return {_archivo(m) for m in vistos}


def huella(archivos: Iterable[Path] = None) -> str:
    """Firma de los archivos del cálculo (su ruta y su contenido, sin importar los saltos de línea)."""
    h = hashlib.sha256()
    for p in sorted(archivos if archivos is not None else archivos_del_calculo()):
        h.update(p.relative_to(RAIZ).as_posix().encode("utf-8"))
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()
