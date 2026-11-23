"""Resumen semanal por WhatsApp: cuánto lleva cada persona de la Bolsa Flexible frente a su meta (180 h) en el tramo vigente.

Usa los mismos números que la grilla y el cierre (ReportService.datos_periodo: acumBolsa, metaMin), no recalcula reglas.
Hay dos avisos: uno para cada persona (a su propio celular) y uno consolidado para los chats que se asignen (jefatura).
"""
import asyncio
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
        "descripcion": "A cada persona de Bolsa Flexible, en su propio celular: cuánto lleva de su meta de 180 h y cuánto le falta.",
        "usa_chats": False,
    },
    "resumen_jefatura": {
        "nombre": "Resumen semanal a jefatura",
        "descripcion": "A los chats que se asignen: quiénes van más atrás de la meta del período, ordenados de menor a mayor avance.",
        "usa_chats": True,
    },
}


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


async def construir(asistencia_service, hoy: str) -> Dict[str, Any]:
    """Una fila por persona activa en Bolsa Flexible (teléfono None si no tiene uno válido) y el tramo vigente."""
    from backend.services.cuadre_service import CuadreService
    from backend.services.report_service import ReportService
    db = asistencia_service.repository.db
    inicio, fin = await CuadreService(asistencia_service).tramo_de(hoy)
    datos = await ReportService(asistencia_service).datos_periodo(inicio, fin, None)
    contactos = {int(r["id"]): r for r in await db.fetch_all("SELECT id, nombre, telefono FROM empleados")}
    personas = []
    for f in datos["filas"]:
        if not f.get("esBolsa") or f.get("activo") != "SÍ":
            continue
        c = contactos.get(int(f["emp_id"])) or {}
        personas.append({
            "emp_id": f["emp_id"], "nombre": f["nombre"], "acum": f["acumBolsa"], "meta": f["metaMin"],
            "telefono": whatsapp_service.normalizar_telefono(c.get("telefono")),
            "mensaje": armar_mensaje(c.get("nombre") or "", f["acumBolsa"], f["metaMin"], inicio, fin, hoy),
        })
    return {"inicio": inicio, "fin": fin, "personas": personas}


async def enviar_resumen(asistencia_service, hoy: str, simular: bool = True, aviso: str = "resumen_personal",
                         destinos: List[str] | None = None) -> Dict[str, Any]:
    """simular=True no envía nada: devuelve a quién y qué se enviaría. `destinos` solo para el aviso a chats."""
    base = await construir(asistencia_service, hoy)
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
    res = {"simulado": simular, "aviso": aviso, "personas": len(personas), "con_telefono": len(con_tel),
           "sin_telefono": [i["nombre"] for i in personas if not i["telefono"]]}
    if simular:
        res["vista_previa"] = [{"nombre": i["nombre"], "telefono": i["telefono"], "mensaje": i["mensaje"]} for i in personas[:5]]
        return res
    enviados = fallidos = 0
    for i in con_tel:
        if await whatsapp_service.enviar(i["telefono"], i["mensaje"]):
            enviados += 1
        else:
            fallidos += 1
        await asyncio.sleep(PAUSA_ENTRE_ENVIOS_SEG)
    logger.info(f"WhatsApp resumen semanal: {enviados} enviados, {fallidos} fallidos, {len(personas) - len(con_tel)} sin teléfono")
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
        out[aviso] = await enviar_resumen(asistencia_service, hoy, simular=False, aviso=aviso, destinos=chats)
    return out
