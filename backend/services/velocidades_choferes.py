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


def _buscador(personas: List[Dict[str, Any]]):
    """Calce de un nombre del plan con una persona: la que tiene todas sus palabras; si hay varias, la que tiene exactamente las mismas o la
    única activa; si aun así queda duda no se asigna a nadie."""
    fichas = [(c, _palabras(c.get("nombre_completo"))) for c in personas]
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

    return buscar


def patentes_planificadas(dias: List[Dict[str, Any]], personas: List[Dict[str, Any]], empleado_id: Any, fecha: str) -> List[str]:
    """Patentes de los camiones que Despacho Diario planificó para la persona ese día (una por camión, en el orden del plan). Mismo calce de
    nombres que el reporte de velocidades, contra todas las `personas` dadas (así un nombre corto no se asigna a quien no corresponde); no
    exige velocidad: basta con que el camión esté planificado."""
    buscar = _buscador(personas)
    res: List[str] = []
    for d in dias:
        if str(d.get("fecha") or "")[:10] != str(fecha)[:10] or not d.get("patente"):
            continue
        for n in (d.get("choferes") or []):
            emp = buscar(n) if str(n).strip() else None
            if emp is not None and str(emp["id"]) == str(empleado_id) and d["patente"] not in res:
                res.append(d["patente"])
    return res


def calzar_choferes(dias: List[Dict[str, Any]], choferes: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Dict[str, Any]]], List[Dict[str, Any]]]:
    """
    dias: filas de Nexacol ({fecha, patente, choferes: [nombre], velMax, hora}); choferes: personas con cargo CHOFER ({id, nombre_completo, activo}).
    Devuelve ({id_empleado: {fecha: {vel, hora, patente, comparte}}}, [{nombre, dias}] de los nombres que no se pudieron calzar).
    Un nombre calza con la persona cuyas palabras lo contienen todas; si hay varias, gana la que tiene exactamente las mismas palabras, y si aun así queda
    duda (un nombre corto como "Carlos") no se asigna a nadie: es mejor un hueco que la velocidad de otra persona.
    """
    buscar = _buscador(choferes)
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
