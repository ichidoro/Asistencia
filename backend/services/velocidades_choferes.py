"""
Velocidad máxima de cada chofer por día, para la grilla de Marcaciones.
Nexacol entrega, por día y camión, el chofer que Despacho Diario planificó y la velocidad máxima del GPS de ese camión (GET /api/reports/camiones-gps-velocidades).
Acá se calza cada nombre del plan con una persona de Asistencia: el plan escribe el nombre como lo eligió quien planifica ("Juan Pérez Soto") y
Asistencia lo guarda con los apellidos primero, así que se comparan las palabras sin importar el orden.
"""
from typing import Any, Dict, List, Tuple

from backend.services.gps_nexacol import _norm


def _palabras(texto: Any) -> frozenset:
    return frozenset(p for p in _norm(texto).split() if len(p) > 1)


def calzar_choferes(dias: List[Dict[str, Any]], choferes: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Dict[str, Any]]], List[Dict[str, Any]]]:
    """
    dias: filas de Nexacol ({fecha, patente, choferes: [nombre], velMax, hora}); choferes: personas con cargo CHOFER ({id, nombre_completo, activo}).
    Devuelve ({id_empleado: {fecha: {vel, hora, patente, comparte}}}, [{nombre, dias}] de los nombres que no se pudieron calzar).
    Un nombre calza con la persona cuyas palabras lo contienen todas; si hay varias, gana la que tiene exactamente las mismas palabras, y si aun así queda
    duda (un nombre corto como "Carlos") no se asigna a nadie: es mejor un hueco que la velocidad de otra persona.
    """
    fichas = [(c, _palabras(c.get("nombre_completo"))) for c in choferes]
    cache: Dict[str, Any] = {}

    def buscar(nombre: str):
        if nombre in cache:
            return cache[nombre]
        pal = _palabras(nombre)
        res = None
        if pal:
            cand = [c for c, p in fichas if pal <= p]
            if len(cand) > 1:
                exactos = [c for c, p in fichas if pal == p]
                activos = [c for c in cand if c.get("activo")]
                cand = exactos if len(exactos) == 1 else activos if len(activos) == 1 else cand
            res = cand[0] if len(cand) == 1 else None
        cache[nombre] = res
        return res

    por_emp: Dict[str, Dict[str, Dict[str, Any]]] = {}
    sin_calzar: Dict[str, set] = {}
    for d in dias:
        if d.get("velMax") is None:
            continue
        nombres = [n for n in (d.get("choferes") or []) if str(n).strip()]
        for n in nombres:
            emp = buscar(n)
            if emp is None:
                sin_calzar.setdefault(n, set()).add(d["fecha"])
                continue
            dia = por_emp.setdefault(str(emp["id"]), {})
            previo = dia.get(d["fecha"])
            # Una persona en dos camiones el mismo día (relevo): queda la velocidad más alta, con su patente.
            if previo is None or d["velMax"] > previo["vel"]:
                dia[d["fecha"]] = {"vel": d["velMax"], "hora": d.get("hora"), "patente": d["patente"], "comparte": len(nombres) > 1}
    return por_emp, [{"nombre": n, "dias": sorted(f)} for n, f in sorted(sin_calzar.items())]
