"""RUT para mostrar. En la base el RUT puede venir con un prefijo que no es parte del RUT real (por ejemplo un "9" antepuesto): acá se quita siempre
antes de mostrarlo. Solo se usa para mostrar y exportar; el dato guardado no se toca porque con él se cruzan las marcas de los relojes."""
import re
from typing import Any


def _dv(cuerpo: str) -> str:
    suma, mult = 0, 2
    for d in reversed(cuerpo):
        suma += int(d) * mult
        mult = 2 if mult == 7 else mult + 1
    r = 11 - suma % 11
    return "K" if r == 10 else "0" if r == 11 else str(r)


def _valido(s: str) -> bool:
    return len(s) >= 2 and s[:-1].isdigit() and _dv(s[:-1]) == s[-1]


def rut_sin_prefijo(rut: Any) -> str:
    """Solo dígitos y K, sin lo que sobra al frente. Un RUT real tiene a lo más 8 dígitos más el verificador (9 caracteres): lo que pase de ahí es prefijo.
    Con 9 caracteres cuyo verificador no calza, pero calza al sacar el primero, también se saca (es el caso de un RUT de 7 dígitos con un 9 antepuesto)."""
    s = re.sub(r"[^0-9Kk]", "", str(rut or "")).upper()
    while len(s) > 9:
        s = s[1:]
    if len(s) == 9 and not _valido(s) and _valido(s[1:]):
        s = s[1:]
    return s


def rut_visible(rut: Any) -> str:
    """El RUT sin prefijo y con formato XX.XXX.XXX-X."""
    s = rut_sin_prefijo(rut)
    if len(s) < 2:
        return str(rut or "")
    cuerpo = re.sub(r"(?<=\d)(?=(\d{3})+$)", ".", s[:-1])
    return f"{cuerpo}-{s[-1]}"
