"""Resumen semanal por WhatsApp: cuánto lleva cada persona de la Bolsa Flexible frente a su meta (180 h) en el tramo vigente.

Usa los mismos números que la grilla y el cierre (ReportService.datos_periodo: acumBolsa, metaMin), no recalcula reglas.
Hay dos avisos: uno para cada persona (a su propio celular) y uno consolidado para los chats que se asignen (jefatura).
"""
import asyncio
import re
import unicodedata
from datetime import date
from typing import Any, Dict, List

from loguru import logger

from backend.services import whatsapp_service

PAUSA_ENTRE_ENVIOS_SEG = 3  # no ráfagas: un número nuevo que dispara muchos mensajes seguidos arriesga bloqueo
MAX_LINEAS_JEFATURA = 40    # el mensaje de WhatsApp se corta en 4000 caracteres

# Catálogo de avisos automáticos (lunes 08:00). `usa_chats`: van a los chats asignados; si no, a cada persona.
AVISOS = {
    "resumen_personal": {
        "nombre": "Resumen semanal a cada persona",
        "descripcion": "A cada persona de Bolsa Flexible, en su propio WhatsApp: cuánto lleva de su meta de 180 h y cuánto le falta. Se la busca por nombre entre los contactos del teléfono (los números de la ficha no se usan).",
        "usa_chats": False,
    },
    "resumen_jefatura": {
        "nombre": "Resumen semanal a jefatura",
        "descripcion": "A los chats que se asignen: quiénes van más atrás de la meta del período, ordenados de menor a mayor avance.",
        "usa_chats": True,
    },
}


_SIN_VALOR = {"de", "del", "la", "las", "los", "y", "e"}


def _tokens(texto: object) -> set:
    """Palabras del nombre en minúsculas y sin tildes, sin conectores («de», «del»…)."""
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return {w for w in re.split(r"[^a-z0-9]+", t) if len(w) > 1 and w not in _SIN_VALOR}


def buscar_contacto(nombre: str, paterno: str, materno: str, contactos: List[Dict[str, Any]]) -> tuple:
    """Encuentra a la persona entre los contactos del teléfono por su nombre.

    Un contacto sirve si trae el primer nombre Y el apellido paterno (en cualquier orden: «Hans Valenzuela», «Valenzuela Hans»).
    Si varios sirven, gana el que además trae el segundo nombre o el apellido materno; si aun así empatan, es ambiguo y no se envía.
    Devuelve ("ok", contacto) | ("ambiguo", [contactos]) | ("ninguno", None).
    """
    nombres = [w for w in re.split(r"\s+", str(nombre or "").strip()) if w]
    primero = _tokens(nombres[0]) if nombres else set()
    resto = _tokens(" ".join(nombres[1:])) | _tokens(materno)
    pat = _tokens(paterno)
    if not primero or not pat:
        return "ninguno", None
    candidatos = []
    for c in contactos:
        ct = _tokens(c.get("nombre"))
        if primero <= ct and pat <= ct:
            candidatos.append((len(resto & ct), c))
    if not candidatos:
        return "ninguno", None
    mejor = max(p for p, _ in candidatos)
    ganadores = [c for p, c in candidatos if p == mejor]
    return ("ok", ganadores[0]) if len(ganadores) == 1 else ("ambiguo", ganadores)


def resolver_destino(nombre: str, paterno: str, materno: str, manual: Dict[str, Any] | None, contactos: List[Dict[str, Any]]) -> tuple:
    """Lo elegido a mano manda; si no hay, se busca por nombre. Devuelve (estado, contacto) con estado manual | ok | ambiguo | ninguno."""
    if manual and manual.get("destino"):
        return "manual", {"id": manual["destino"], "nombre": manual.get("etiqueta") or manual["destino"]}
    return buscar_contacto(nombre, paterno, materno, contactos)


def _numero_de(jid: str) -> str:
    n = str(jid).split("@")[0]
    return ("+" + n) if jid.endswith("@s.whatsapp.net") else n


def _hhmm(minutos: float) -> str:
    m = round(abs(minutos))
    return f"{m // 60}:{m % 60:02d}"


def _dm(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


def armar_mensaje(nombre: str, acum_min: float, meta_min: float, inicio: str, fin: str, hoy: str) -> str:
    pct = round(acum_min / meta_min * 100) if meta_min > 0 else 0
    dias = max(0, (date.fromisoformat(fin) - date.fromisoformat(hoy)).days)
    partes = (nombre or "").split()
    saludo = f"Hola {partes[0].capitalize()}" if partes else "Hola"
    lineas = [
        f"{saludo}, este es su resumen semanal de horas (período {_dm(inicio)} al {_dm(fin)}).",
        f"• Lleva {_hhmm(acum_min)} h de {_hhmm(meta_min)} h ({pct} %).",
    ]
    if acum_min >= meta_min:
        lineas.append(f"• Ya cumplió la meta: {_hhmm(acum_min - meta_min)} h sobre lo exigido.")
    else:
        falta = meta_min - acum_min
        lineas.append(f"• Le faltan {_hhmm(falta)} h para la meta.")
        if dias > 0:
            lineas.append(f"• Quedan {dias} día(s) del período: unas {_hhmm(falta / dias)} h por día.")
    lineas.append("Mensaje automático de Asistencia Aguacol. Ante dudas, consulte con su jefatura.")
    return "\n".join(lineas)


def armar_mensaje_jefatura(items: List[Dict[str, Any]], inicio: str, fin: str, hoy: str) -> str:
    """Consolidado: las personas que aún no llegan a la meta, de menor a mayor avance."""
    dias = max(0, (date.fromisoformat(fin) - date.fromisoformat(hoy)).days)
    cumplen = [i for i in items if i["meta"] > 0 and i["acum"] >= i["meta"]]
    atras = sorted((i for i in items if i["meta"] > 0 and i["acum"] < i["meta"]), key=lambda i: i["acum"] / i["meta"])
    lineas = [f"Resumen semanal de horas de Bolsa (período {_dm(inicio)} al {_dm(fin)}, quedan {dias} día(s)).",
              f"{len(cumplen)} de {len(items)} ya cumplieron la meta; {len(atras)} aún no."]
    for i in atras[:MAX_LINEAS_JEFATURA]:
        lineas.append(f"• {i['nombre']}: {_hhmm(i['acum'])} de {_hhmm(i['meta'])} h ({round(i['acum'] / i['meta'] * 100)} %), faltan {_hhmm(i['meta'] - i['acum'])} h")
    if len(atras) > MAX_LINEAS_JEFATURA:
        lineas.append(f"… y {len(atras) - MAX_LINEAS_JEFATURA} más.")
    return "\n".join(lineas)


async def construir(asistencia_service, hoy: str, contactos: List[Dict[str, Any]] | None = None, manuales: Dict[int, Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Una fila por persona activa en Bolsa Flexible y el tramo vigente. El destino sale de los contactos del teléfono (por nombre):
    los números de la ficha no se usan porque pueden estar mal. `estado`: ok | ambiguo | ninguno."""
    from backend.services.cuadre_service import CuadreService
    from backend.services.report_service import ReportService
    db = asistencia_service.repository.db
    inicio, fin = await CuadreService(asistencia_service).tramo_de(hoy)
    datos = await ReportService(asistencia_service).datos_periodo(inicio, fin, None)
    fichas = {int(r["id"]): r for r in await db.fetch_all("SELECT id, nombre, apellido_paterno, apellido_materno FROM empleados")}
    personas = []
    for f in datos["filas"]:
        if not f.get("esBolsa") or f.get("activo") != "SÍ":
            continue
        c = fichas.get(int(f["emp_id"])) or {}
        estado, hallado = resolver_destino(c.get("nombre") or "", c.get("apellido_paterno") or "", c.get("apellido_materno") or "", (manuales or {}).get(int(f["emp_id"])), contactos or [])
        con = estado in ("ok", "manual")
        personas.append({
            "emp_id": f["emp_id"], "nombre": f["nombre"], "acum": f["acumBolsa"], "meta": f["metaMin"], "estado": estado,
            "telefono": hallado["id"] if con else None, "contacto": hallado["nombre"] if con else None,
            "candidatos": [x["nombre"] for x in hallado] if estado == "ambiguo" else [],
            "mensaje": armar_mensaje(c.get("nombre") or "", f["acumBolsa"], f["metaMin"], inicio, fin, hoy),
        })
    return {"inicio": inicio, "fin": fin, "personas": personas}


async def listar_personas(asistencia_service, hoy: str, manuales: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cada persona de Bolsa con el contacto que se le encontró (o su estado), para revisarlo y fijarlo a mano en la pantalla."""
    base = await construir(asistencia_service, hoy, await whatsapp_service.contactos(), manuales)
    return [{"emp_id": i["emp_id"], "nombre": i["nombre"], "estado": i["estado"], "contacto": i["contacto"],
             "numero": _numero_de(i["telefono"]) if i["telefono"] else None, "candidatos": i["candidatos"]} for i in base["personas"]]


async def enviar_resumen(asistencia_service, hoy: str, simular: bool = True, aviso: str = "resumen_personal",
                         destinos: List[str] | None = None, manuales: Dict[int, Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """simular=True no envía nada: devuelve a quién y qué se enviaría. `destinos` solo para el aviso a chats."""
    base = await construir(asistencia_service, hoy, await whatsapp_service.contactos(), manuales)
    personas = base["personas"]
    if aviso == "resumen_jefatura":
        texto = armar_mensaje_jefatura(personas, base["inicio"], base["fin"], hoy)
        chats = destinos or []
        res: Dict[str, Any] = {"simulado": simular, "aviso": aviso, "personas": len(personas), "chats": len(chats), "vista_previa": [{"nombre": "Mensaje consolidado", "telefono": ", ".join(chats) or "(sin chats asignados)", "mensaje": texto}]}
        if simular:
            return res
        enviados = fallidos = 0
        for d in chats:
            if await whatsapp_service.enviar(d, texto):
                enviados += 1
            else:
                fallidos += 1
            await asyncio.sleep(PAUSA_ENTRE_ENVIOS_SEG)
        logger.info(f"WhatsApp resumen jefatura: {enviados} enviados, {fallidos} fallidos")
        res.update(enviados=enviados, fallidos=fallidos)
        return res

    con_tel = [i for i in personas if i["telefono"]]
    res = {"simulado": simular, "aviso": aviso, "personas": len(personas), "con_contacto": len(con_tel),
           "sin_contacto": [i["nombre"] for i in personas if i["estado"] == "ninguno"], "manuales": sum(1 for i in personas if i["estado"] == "manual"),
           "ambiguos": [f"{i['nombre']} (¿{' o '.join(i['candidatos'])}?)" for i in personas if i["estado"] == "ambiguo"]}
    if simular:
        res["coincidencias"] = [{"persona": i["nombre"], "contacto": i["contacto"], "numero": _numero_de(i["telefono"])} for i in con_tel]
        res["vista_previa"] = [{"nombre": i["nombre"], "telefono": _numero_de(i["telefono"]), "mensaje": i["mensaje"]} for i in con_tel[:2]]
        return res
    enviados = fallidos = 0
    for i in con_tel:
        if await whatsapp_service.enviar(i["telefono"], i["mensaje"]):
            enviados += 1
        else:
            fallidos += 1
        await asyncio.sleep(PAUSA_ENTRE_ENVIOS_SEG)
    logger.info(f"WhatsApp resumen semanal: {enviados} enviados, {fallidos} fallidos, {len(personas) - len(con_tel)} sin contacto")
    res.update(enviados=enviados, fallidos=fallidos)
    return res


async def enviar_automaticos(asistencia_service, repo, hoy: str) -> Dict[str, Any]:
    """Lo que dispara el cron: cada aviso encendido, a sus destinatarios."""
    activos = await repo.avisos_activos()
    out: Dict[str, Any] = {}
    for aviso in AVISOS:
        if not activos.get(aviso):
            continue
        chats = [d["destino"] for d in await repo.destinos(aviso)] if AVISOS[aviso]["usa_chats"] else None
        out[aviso] = await enviar_resumen(asistencia_service, hoy, simular=False, aviso=aviso, destinos=chats, manuales=await repo.destinos_personas())
    return out
