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
        "descripcion": "A las personas de Artículo 22 que se asignen: quiénes van más atrás de la meta del período, ordenados de menor a mayor avance.",
        "usa_chats": True,
        "solo_art22": True,  # los destinatarios se eligen entre el personal de Artículo 22 (jefatura)
    },
    "exceso_velocidad": {
        "nombre": "Alerta de exceso de velocidad (en vivo)",
        "descripcion": "A los chats que se asignen: apenas un camión de la Flota en vivo de Nexacol reporta más de 95 km/h, con patente, chofer, velocidad y ubicación. También le llega al propio chofer (el que Despacho Diario puso en el camión), a su WhatsApp: el contacto fijado a mano o el que se encuentra por nombre en el teléfono, igual que el resumen personal. Se revisa cada minuto y no repite el aviso del mismo camión durante 15 minutos.",
        "usa_chats": True,
        "tiempo_real": True,  # no va en el cron del lunes: lo dispara cron-alerta-velocidad.sh
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


def _norm(t: object) -> str:
    """Mayúsculas, sin tildes ni espacios sobrantes: «Logística  Retail» y «logistica retail» son lo mismo."""
    sin_tildes = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.upper().split())


def pasa_filtro(area: object, cargo: object, filtro: Dict[str, List[str]] | None) -> bool:
    """Sin filtro entran todas. Con filtro de áreas y/o cargos entra quien cumple CADA uno que se haya puesto (varias áreas o cargos = cualquiera de ellos)."""
    if not filtro:
        return True
    areas, cargos = {_norm(x) for x in filtro.get("areas") or []}, {_norm(x) for x in filtro.get("cargos") or []}
    return (not areas or _norm(area) in areas) and (not cargos or _norm(cargo) in cargos)  # los dos filtros se encadenan con Y


def _numero_de(jid: str) -> str:
    n = str(jid).split("@")[0]
    return ("+" + n) if jid.endswith("@s.whatsapp.net") else n


def _hhmm(minutos: float) -> str:
    m = round(abs(minutos))
    return f"{m // 60}:{m % 60:02d}"


def _dm(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


def _barra(pct: float, largo: int = 10) -> str:
    """Barra de avance de texto (WhatsApp no dibuja gráficos): ▰▰▰▰▰▰▰▰▱▱. Tope visual en 100 %."""
    llenos = max(0, min(largo, round(min(pct, 100) / 100 * largo)))
    return "▰" * llenos + "▱" * (largo - llenos)


def _dias(n: int) -> str:
    return f"{n} día" if n == 1 else f"{n} días"


def armar_mensaje(nombre: str, acum_min: float, meta_min: float, inicio: str, fin: str, hoy: str) -> str:
    pct = round(acum_min / meta_min * 100) if meta_min > 0 else 0
    dias = max(0, (date.fromisoformat(fin) - date.fromisoformat(hoy)).days)
    partes = (nombre or "").split()
    saludo = f"Estimado/a {partes[0].capitalize()}," if partes else "Estimado/a,"
    lineas = [
        "*RESUMEN SEMANAL DE HORAS*",
        f"Bolsa Flexible · Período {_dm(inicio)} al {_dm(fin)}",
        "",
        saludo,
        "A continuación, el estado de su bolsa de horas:",
        "",
        f"{_barra(pct)}  *{pct} %*",
        f"▪ Acumulado: *{_hhmm(acum_min)} h* de {_hhmm(meta_min)} h",
    ]
    if acum_min >= meta_min:
        lineas.append(f"✅ *Meta cumplida*, con {_hhmm(acum_min - meta_min)} h sobre lo exigido.")
    else:
        falta = meta_min - acum_min
        lineas.append(f"▪ Pendiente: *{_hhmm(falta)} h*")
        if dias > 0:
            lineas.append(f"▪ Plazo: {_dias(dias)} (promedio requerido: {_hhmm(falta / dias)} h por día)")
    lineas += ["", "_Mensaje automático de Asistencia Aguacol. Ante dudas, consulte con su jefatura._"]
    return "\n".join(lineas)


def armar_mensaje_jefatura(items: List[Dict[str, Any]], inicio: str, fin: str, hoy: str) -> str:
    """Consolidado: las personas que aún no llegan a la meta, de menor a mayor avance."""
    dias = max(0, (date.fromisoformat(fin) - date.fromisoformat(hoy)).days)
    con_meta = [i for i in items if i["meta"] > 0]
    cumplen = [i for i in con_meta if i["acum"] >= i["meta"]]
    atras = sorted((i for i in con_meta if i["acum"] < i["meta"]), key=lambda i: i["acum"] / i["meta"])
    prom = round(sum(min(i["acum"] / i["meta"], 1) for i in con_meta) / len(con_meta) * 100) if con_meta else 0
    lineas = [
        "*RESUMEN SEMANAL · BOLSA DE HORAS*",
        f"Período {_dm(inicio)} al {_dm(fin)} · quedan {_dias(dias)}",
        "",
        f"▪ Personas en seguimiento: *{len(items)}*",
        f"▪ Meta cumplida: *{len(cumplen)}*",
        f"▪ Pendientes: *{len(atras)}*",
        f"▪ Avance promedio: *{prom} %*  {_barra(prom)}",
    ]
    if atras:
        lineas += ["", "*Pendientes, de menor a mayor avance*"]
        for n, i in enumerate(atras[:MAX_LINEAS_JEFATURA], 1):
            lineas.append(f"{n}. {i['nombre']} · *{round(i['acum'] / i['meta'] * 100)} %* · {_hhmm(i['acum'])} de {_hhmm(i['meta'])} h · faltan {_hhmm(i['meta'] - i['acum'])} h")
        if len(atras) > MAX_LINEAS_JEFATURA:
            lineas.append(f"… y {len(atras) - MAX_LINEAS_JEFATURA} más.")
    else:
        lineas += ["", "✅ Todas las personas cumplieron la meta."]
    lineas += ["", "_Mensaje automático de Asistencia Aguacol._"]
    return "\n".join(lineas)


async def construir(asistencia_service, hoy: str, contactos: List[Dict[str, Any]] | None = None, manuales: Dict[int, Dict[str, Any]] | None = None, filtro: Dict[str, List[str]] | None = None) -> Dict[str, Any]:
    """Una fila por persona activa en Bolsa Flexible y el tramo vigente. El destino sale de los contactos del teléfono (por nombre):
    los números de la ficha no se usan porque pueden estar mal. `estado`: ok | ambiguo | ninguno."""
    from backend.services.cuadre_service import CuadreService
    from backend.services.report_service import ReportService
    db = asistencia_service.repository.db
    inicio, fin = await CuadreService(asistencia_service).tramo_de(hoy)
    datos = await ReportService(asistencia_service).datos_periodo(inicio, fin, None)
    fichas = {int(r["id"]): r for r in await db.fetch_all("SELECT e.id, e.nombre, e.apellido_paterno, e.apellido_materno, e.cargo, a.nombre AS area FROM empleados e LEFT JOIN areas a ON a.id = e.area_id")}
    personas = []
    for f in datos["filas"]:
        if not f.get("esBolsa") or f.get("activo") != "SÍ":
            continue
        c = fichas.get(int(f["emp_id"])) or {}
        estado, hallado = resolver_destino(c.get("nombre") or "", c.get("apellido_paterno") or "", c.get("apellido_materno") or "", (manuales or {}).get(int(f["emp_id"])), contactos or [])
        con = estado in ("ok", "manual")
        personas.append({
            "emp_id": f["emp_id"], "nombre": f["nombre"], "acum": f["acumBolsa"], "meta": f["metaMin"], "estado": estado,
            "area": c.get("area") or "", "cargo": c.get("cargo") or "", "incluida": pasa_filtro(c.get("area"), c.get("cargo"), filtro),
            "telefono": hallado["id"] if con else None, "contacto": hallado["nombre"] if con else None,
            "candidatos": [x["nombre"] for x in hallado] if estado == "ambiguo" else [],
            "mensaje": armar_mensaje(c.get("nombre") or "", f["acumBolsa"], f["metaMin"], inicio, fin, hoy),
        })
    return {"inicio": inicio, "fin": fin, "personas": personas}


async def listar_destinatarios(db: Any, repo: Any, aviso: str, filtro: Dict[str, List[str]] | None = None) -> List[Dict[str, Any]]:
    """Para un aviso a chats: todas las personas activas de Asistencia con el contacto que se les encontró y si ya lo reciben (`recibe`).
    Misma forma que listar_personas, para usar la misma tabla en la pantalla."""
    contactos, manuales = await whatsapp_service.contactos(), await repo.destinos_personas()
    asignadas = {str(d["destino"]) for d in await repo.destinos(aviso)}
    out = []
    for f in await repo.empleados_activos(solo_art22=bool(AVISOS.get(aviso, {}).get("solo_art22"))):
        nombre = " ".join(str(f[k] or "").strip() for k in ("nombre", "apellido_paterno", "apellido_materno") if str(f[k] or "").strip())
        estado, hallado = resolver_destino(f["nombre"] or "", f["apellido_paterno"] or "", f["apellido_materno"] or "", manuales.get(int(f["id"])), contactos)
        con = estado in ("ok", "manual")
        out.append({"emp_id": f["id"], "nombre": nombre, "area": f["area"] or "", "cargo": f["cargo"] or "", "incluida": pasa_filtro(f["area"], f["cargo"], filtro),
                    "recibe": PREFIJO_PERSONA + str(f["id"]) in asignadas, "estado": estado, "contacto": hallado["nombre"] if con else None,
                    "numero": _numero_de(hallado["id"]) if con else None, "candidatos": [x["nombre"] for x in hallado] if estado == "ambiguo" else []})
    return out


async def listar_personas(asistencia_service, hoy: str, manuales: Dict[int, Dict[str, Any]], filtro: Dict[str, List[str]] | None = None) -> List[Dict[str, Any]]:
    """Cada persona de Bolsa con el contacto que se le encontró (o su estado), para revisarlo y fijarlo a mano en la pantalla."""
    base = await construir(asistencia_service, hoy, await whatsapp_service.contactos(), manuales, filtro)
    return [{"emp_id": i["emp_id"], "nombre": i["nombre"], "area": i["area"], "cargo": i["cargo"], "incluida": i["incluida"], "estado": i["estado"], "contacto": i["contacto"],
             "numero": _numero_de(i["telefono"]) if i["telefono"] else None, "candidatos": i["candidatos"]} for i in base["personas"]]


async def enviar_resumen(asistencia_service, hoy: str, simular: bool = True, aviso: str = "resumen_personal",
                         destinos: List[str] | None = None, manuales: Dict[int, Dict[str, Any]] | None = None,
                         filtro: Dict[str, List[str]] | None = None) -> Dict[str, Any]:
    """simular=True no envía nada: devuelve a quién y qué se enviaría. `destinos` solo para el aviso a chats."""
    base = await construir(asistencia_service, hoy, await whatsapp_service.contactos(), manuales, filtro)
    personas = [p for p in base["personas"] if p["incluida"]]  # lo que queda fuera del filtro de área y cargo no se cuenta ni se envía
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


PREFIJO_PERSONA = "emp:"  # un destino «emp:123» es una persona de Asistencia: su WhatsApp se resuelve al enviar (contacto fijado a mano o hallado por nombre)


async def resolver_destinos_chat(db: Any, filas: List[Dict[str, Any]], manuales: Dict[int, Dict[str, Any]] | None = None, contactos: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    """Cada destino asignado a un aviso de chats → {id, etiqueta, jid, estado, contacto}. Un grupo o celular va tal cual; una persona de Asistencia
    se busca entre los contactos del teléfono por su nombre (igual que el resumen personal), y si no se encuentra queda sin jid y no se envía."""
    out = []
    for r in filas:
        d = str(r["destino"])
        if not d.startswith(PREFIJO_PERSONA):
            out.append({"id": r.get("id"), "etiqueta": r.get("etiqueta") or d, "jid": d, "estado": "directo", "contacto": None})
            continue
        emp_id = int(d[len(PREFIJO_PERSONA):])
        f = await db.fetch_one("SELECT nombre, apellido_paterno, apellido_materno FROM empleados WHERE id = ?", (emp_id,))
        if contactos is None:
            contactos = await whatsapp_service.contactos()
        if not f:
            out.append({"id": r.get("id"), "etiqueta": r.get("etiqueta") or d, "jid": None, "estado": "ninguno", "contacto": None})
            continue
        estado, hallado = resolver_destino(f["nombre"] or "", f["apellido_paterno"] or "", f["apellido_materno"] or "", (manuales or {}).get(emp_id), contactos)
        out.append({"id": r.get("id"), "etiqueta": r.get("etiqueta") or d, "jid": hallado["id"] if estado in ("ok", "manual") else None, "estado": estado,
                    "contacto": hallado["nombre"] if estado in ("ok", "manual") else None})
    return out


async def destinos_chat(db: Any, repo: Any, aviso: str) -> List[str]:
    """Los WhatsApp a los que realmente se envía un aviso de chats (personas ya resueltas; las que no tienen contacto se omiten)."""
    filas = [dict(r) for r in await repo.destinos(aviso)]
    return [x["jid"] for x in await resolver_destinos_chat(db, filas, await repo.destinos_personas()) if x["jid"]]


async def enviar_automaticos(asistencia_service, repo, hoy: str) -> Dict[str, Any]:
    """Lo que dispara el cron: cada aviso encendido, a sus destinatarios."""
    activos = await repo.avisos_activos()
    out: Dict[str, Any] = {}
    for aviso in AVISOS:
        if not activos.get(aviso) or AVISOS[aviso].get("tiempo_real"):
            continue
        chats = await destinos_chat(asistencia_service.repository.db, repo, aviso) if AVISOS[aviso]["usa_chats"] else None
        out[aviso] = await enviar_resumen(asistencia_service, hoy, simular=False, aviso=aviso, destinos=chats, manuales=await repo.destinos_personas(),
                                          filtro=(await repo.filtros(aviso)).get(aviso))
    return out
