"""Resumen semanal por WhatsApp: cuánto lleva cada persona de la Bolsa Flexible frente a su meta (180 h) en el tramo vigente.

Usa los mismos números que la grilla y el cierre (ReportService.datos_periodo: acumBolsa, metaMin), no recalcula reglas.
"""
import asyncio
from datetime import date
from typing import Any, Dict, List

from loguru import logger

from backend.services import whatsapp_service

PAUSA_ENTRE_ENVIOS_SEG = 3  # no ráfagas: un número nuevo que dispara muchos mensajes seguidos arriesga bloqueo


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


async def construir(asistencia_service, hoy: str) -> List[Dict[str, Any]]:
    """Un mensaje por persona activa en Bolsa Flexible, con su teléfono (None si no tiene uno válido)."""
    from backend.services.cuadre_service import CuadreService
    from backend.services.report_service import ReportService
    db = asistencia_service.repository.db
    inicio, fin = await CuadreService(asistencia_service).tramo_de(hoy)
    datos = await ReportService(asistencia_service).datos_periodo(inicio, fin, None)
    contactos = {int(r["id"]): r for r in await db.fetch_all("SELECT id, nombre, telefono FROM empleados")}
    salida = []
    for f in datos["filas"]:
        if not f.get("esBolsa") or f.get("activo") != "SÍ":
            continue
        c = contactos.get(int(f["emp_id"])) or {}
        salida.append({
            "emp_id": f["emp_id"], "nombre": f["nombre"],
            "telefono": whatsapp_service.normalizar_telefono(c.get("telefono")),
            "mensaje": armar_mensaje(c.get("nombre") or "", f["acumBolsa"], f["metaMin"], inicio, fin, hoy),
        })
    return salida


async def enviar_resumen(asistencia_service, hoy: str, simular: bool = True) -> Dict[str, Any]:
    """simular=True no envía nada: devuelve a quién y qué se enviaría."""
    items = await construir(asistencia_service, hoy)
    con_tel = [i for i in items if i["telefono"]]
    res: Dict[str, Any] = {"simulado": simular, "personas": len(items), "con_telefono": len(con_tel),
                           "sin_telefono": [i["nombre"] for i in items if not i["telefono"]]}
    if simular:
        res["vista_previa"] = [{"nombre": i["nombre"], "telefono": i["telefono"], "mensaje": i["mensaje"]} for i in items[:5]]
        return res
    enviados = fallidos = 0
    for i in con_tel:
        if await whatsapp_service.enviar(i["telefono"], i["mensaje"]):
            enviados += 1
        else:
            fallidos += 1
        await asyncio.sleep(PAUSA_ENTRE_ENVIOS_SEG)
    logger.info(f"WhatsApp resumen semanal: {enviados} enviados, {fallidos} fallidos, {len(items) - len(con_tel)} sin teléfono")
    res.update(enviados=enviados, fallidos=fallidos)
    return res
