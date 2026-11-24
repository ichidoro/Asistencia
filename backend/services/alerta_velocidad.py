"""Alerta en vivo por exceso de velocidad de los camiones.

Lee la «Flota en vivo» de Nexacol (Logística → Ruta GPS, por la integración de gps_nexacol) y avisa por WhatsApp a los chats asignados
cuando un camión reporta más de LIMITE_KMH. Lo dispara cron-alerta-velocidad.sh cada minuto.
"""
import asyncio
import time
from typing import Any, Dict, List

from loguru import logger

from backend.services import gps_nexacol, whatsapp_service
from backend.services.velocidades_choferes import _buscador
from backend.services.whatsapp_resumen import resolver_destino

LIMITE_KMH = 95        # pedido de la jefatura: sobre esta velocidad se avisa
EDAD_MAX_MIN = 3       # un reporte más viejo no es "en vivo": su velocidad ya no dice dónde va el camión
GRUPO = "TRADICIONAL"  # por ahora solo se avisa de camiones del grupo Tradicional (el grupo que Nexacol trae de la plataforma de GPS; sin grupo cuenta como otro)
REPETIR_MIN = 15       # mientras siga el exceso, se vuelve a avisar del mismo camión solo pasado este tiempo
PAUSA_ENTRE_ENVIOS_SEG = 1

# shortcut: la memoria de lo ya avisado vive en el proceso; si la app se reinicia en pleno exceso se repite un aviso, y con varios workers cada uno avisaría. Migrar a tabla si se escala.
_avisado: Dict[str, float] = {}


def detectar(flota: List[Dict[str, Any]], limite: float = LIMITE_KMH) -> List[Dict[str, Any]]:
    """Camiones del grupo Tradicional con reporte reciente sobre el límite, del más rápido al más lento."""
    out = []
    for c in flota:
        u = c.get("ultimo") or {}
        v = u.get("v")
        edad = c.get("edadMin")
        if str(c.get("grupo") or "").strip().upper() != GRUPO or not isinstance(v, (int, float)) or v <= limite or edad is None or edad > EDAD_MAX_MIN or not c.get("patente"):
            continue
        out.append({"patente": c["patente"], "chofer": c.get("chofer") or "", "vel": int(round(v)), "lugar": (u.get("lugar") or "").strip(), "f": str(u.get("f") or "")})
    return sorted(out, key=lambda e: -e["vel"])


def nuevos(excesos: List[Dict[str, Any]], ahora: float, memoria: Dict[str, float] | None = None) -> List[Dict[str, Any]]:
    """Los que aún no se avisaron en los últimos REPETIR_MIN. Un camión que ya bajó del límite se olvida (si vuelve a pasarse, es otro aviso)."""
    mem = _avisado if memoria is None else memoria
    activos = {e["patente"] for e in excesos}
    for p in [p for p in mem if p not in activos and ahora - mem[p] > 60]:
        del mem[p]
    return [e for e in excesos if ahora - mem.get(e["patente"], -1e12) >= REPETIR_MIN * 60]


def armar_mensaje(e: Dict[str, Any], limite: float = LIMITE_KMH) -> str:
    hora = e["f"][11:16] if len(e["f"]) >= 16 else ""
    lineas = ["🚨 *ALERTA DE EXCESO DE VELOCIDAD*", "", f"▪ Camión: *{e['patente']}*", f"▪ Chofer: {e['chofer'] or 'sin asignar en Despacho Diario'}",
              f"▪ Velocidad: *{e['vel']} km/h* (límite {int(limite)} km/h)"]
    if hora:
        lineas.append(f"▪ Hora del reporte: {hora}")
    if e["lugar"]:
        lineas.append(f"▪ Ubicación: {e['lugar']}")
    if "estado_chofer" in e:
        lineas.append("▪ Aviso al chofer: " + ("enviado a su WhatsApp" if e.get("destino_chofer") else "no enviado (" + {"sin_chofer": "sin chofer asignado", "ambiguo": "contacto ambiguo", "ninguno": "sin contacto en el teléfono"}.get(e["estado_chofer"], "sin contacto") + ")"))
    lineas += ["", "_Aviso automático de Asistencia Aguacol, según la Flota en vivo de Nexacol._"]
    return "\n".join(lineas)


def armar_mensaje_chofer(e: Dict[str, Any], limite: float = LIMITE_KMH) -> str:
    """Lo que recibe el propio chofer en su WhatsApp."""
    nombre = (e["chofer"].split() or [""])[0].capitalize()
    hora = e["f"][11:16] if len(e["f"]) >= 16 else ""
    lineas = ["⚠️ *AVISO DE VELOCIDAD*", "", f"Estimado/a {nombre}," if nombre else "Estimado/a,",
              f"El camión *{e['patente']}* registró *{e['vel']} km/h*" + (f" a las {hora}" if hora else "") + f", sobre el límite de {int(limite)} km/h."]
    if e["lugar"]:
        lineas.append(f"▪ Ubicación: {e['lugar']}")
    lineas += ["", "Le pedimos reducir la velocidad y conducir con precaución. Su jefatura también recibió este aviso.", "", "_Aviso automático de Asistencia Aguacol._"]
    return "\n".join(lineas)


def contacto_del_chofer(nombre: str, choferes: List[Dict[str, Any]], manuales: Dict[Any, Any], contactos: List[Dict[str, Any]]) -> tuple:
    """El WhatsApp del chofer que Despacho Diario puso en el camión: se calza con la persona de Asistencia y se usa el mismo contacto que en el resumen personal
    (el fijado a mano, o el del teléfono encontrado por nombre). Devuelve (estado, contacto): manual | ok | ambiguo | ninguno | sin_chofer."""
    emp = _buscador(choferes)(nombre) if str(nombre).strip() else None
    if emp is None:
        return "sin_chofer", None
    return resolver_destino(emp.get("nombre") or "", emp.get("apellido_paterno") or "", emp.get("apellido_materno") or "", (manuales or {}).get(int(emp["id"])), contactos)


async def revisar(destinos: List[str], simular: bool = True, choferes: List[Dict[str, Any]] | None = None, manuales: Dict[Any, Any] | None = None) -> Dict[str, Any]:
    """Una pasada: lee la flota; por cada camión nuevo sobre el límite avisa a cada chat de jefatura y, si se le encuentra contacto, al chofer.
    simular=True no envía ni recuerda nada."""
    flota = (await gps_nexacol._get("/api/reports/camiones-gps-flota", {})).get("flota") or []
    excesos = detectar(flota)
    ahora = time.time()
    por_avisar = nuevos(excesos, ahora)
    contactos = await whatsapp_service.contactos() if por_avisar and choferes is not None else []  # no se consulta el teléfono si no hay nada que avisar
    for e in por_avisar:
        e["estado_chofer"], hallado = contacto_del_chofer(e["chofer"], choferes or [], manuales or {}, contactos)
        e["destino_chofer"] = hallado["id"] if hallado else None
    res: Dict[str, Any] = {"simulado": simular, "aviso": "exceso_velocidad", "limite": LIMITE_KMH, "sobre_limite": len(excesos), "a_avisar": len(por_avisar),
                           "vista_previa": [{"patente": e["patente"], "chofer": e["chofer"], "chofer_recibe": e["destino_chofer"] is not None, "estado_chofer": e["estado_chofer"],
                                             "mensaje_jefatura": armar_mensaje(e), "mensaje_chofer": armar_mensaje_chofer(e)} for e in por_avisar[:2]]}
    if simular:
        return res
    enviados = fallidos = choferes_avisados = 0
    for e in por_avisar:
        ok = False
        if e["destino_chofer"] and await whatsapp_service.enviar(e["destino_chofer"], armar_mensaje_chofer(e)):
            choferes_avisados += 1
            ok = True
        for d in destinos:
            if await whatsapp_service.enviar(d, armar_mensaje(e)):
                enviados += 1
                ok = True
            else:
                fallidos += 1
        if ok:
            _avisado[e["patente"]] = ahora  # si nadie lo recibió se reintenta en la próxima pasada
        await asyncio.sleep(PAUSA_ENTRE_ENVIOS_SEG)
    if por_avisar:
        logger.info(f"Alerta de velocidad: {len(por_avisar)} camión(es), {enviados} a jefatura, {choferes_avisados} a choferes, {fallidos} fallidos")
    res.update(enviados=enviados, fallidos=fallidos, choferes_avisados=choferes_avisados)
    return res
