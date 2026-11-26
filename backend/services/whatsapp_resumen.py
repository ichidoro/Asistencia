"""Resumen diario de horas por WhatsApp (lunes a viernes): cuánto lleva cada persona de la Bolsa Flexible frente a su meta (180 h) en el tramo vigente.

Usa los mismos números que la grilla y el cierre (ReportService.datos_periodo: acumBolsa, metaMin), no recalcula reglas.
Hay dos avisos: uno para cada persona (a su propio celular) y uno consolidado para los chats que se asignen (jefatura).
"""
import asyncio
import re
import unicodedata
from datetime import date, timedelta
from typing import Any, Dict, List

from loguru import logger

from backend.services import whatsapp_service

PAUSA_ENTRE_ENVIOS_SEG = 3  # no ráfagas: un número nuevo que dispara muchos mensajes seguidos arriesga bloqueo
MAX_LINEAS_JEFATURA = 50    # el mensaje de WhatsApp se corta en 4000 caracteres

# Catálogo de avisos automáticos. `franja`: manana (lunes a viernes 08:00) o tarde (20:00: cada viernes y el día del cierre del período). `usa_chats`: van a los chats asignados; si no, a cada persona.
AVISOS = {
    "resumen_personal": {
        "nombre": "Resumen semanal a cada persona",
        "descripcion": "A cada persona de Bolsa Flexible, en su propio WhatsApp, cada viernes a las 20:00: cuánto lleva de su meta de 180 h y cuánto le falta. El día del cierre del período, también a las 20:00, le avisa cómo le fue en el período. Solo le llega a quien tenga un contacto asignado a mano (los números de la ficha no se usan).",
        "usa_chats": False,
        "franja": "tarde",
    },
    "resumen_jefatura": {
        "nombre": "Resumen diario de horas a jefatura",
        "franja": "manana",
        "descripcion": "A las personas que se asignen (de cualquier área): todas las personas del filtro, de más a menos horas, con quiénes ya cumplieron la meta del período y a quiénes les falta.",
        "usa_chats": True,
    },
    "resumen_general": {
        "nombre": "Resumen general de bodega (atrasos y horas extras)",
        "descripcion": "A los chats que se asignen, sobre ayudantes de bodega, inventario, jefe de bodega, operador de grúa y supervisor de carga de Logística Tradicional, según su marcaje (el filtro de área y cargos parte con eso y se puede cambiar como en los demás avisos): a las 12:00 avisa quién marcó atrasado hoy y a las 08:00 quién hizo horas extras el día anterior (el lunes, de viernes a domingo). Si no hay novedades no envía nada.",
        "usa_chats": True,
        "franjas": {"manana": "extras", "mediodia": "atrasos"},
    },
    "exceso_velocidad": {
        "nombre": "Alerta de exceso de velocidad (en vivo)",
        "descripcion": "A los chats que se asignen y también a la jefatura ya configurada en el resumen a jefatura: apenas un camión del grupo Tradicional de la Flota en vivo de Nexacol reporta una velocidad que pasa de 100 km/h (el mensaje siempre dice límite 90 km/h), con patente, chofer, velocidad y ubicación. También le llega al propio chofer (el que Despacho Diario puso en el camión), a su WhatsApp: el contacto fijado a mano, igual que el resumen personal. Se revisa cada minuto y no repite el aviso del mismo camión durante 15 minutos.",
        "usa_chats": True,
        "tambien_a": "resumen_jefatura",  # además de sus propios chats, le llega a la jefatura ya configurada en el resumen a jefatura
        "tiempo_real": True,  # no va en el cron de las 08:00: lo dispara cron-alerta-velocidad.sh
    },
}


def resolver_destino(nombre: str, paterno: str, materno: str, manual: Dict[str, Any] | None, contactos: List[Dict[str, Any]]) -> tuple:
    """Solo vale el contacto que se fijó a mano para la persona: nunca se asigna uno por coincidencia de nombre.
    Devuelve (estado, contacto) con estado manual | ninguno. Los tres avisos pasan por aquí."""
    if manual and manual.get("destino"):
        return "manual", {"id": manual["destino"], "nombre": manual.get("etiqueta") or manual["destino"]}
    return "ninguno", None


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
        "*RESUMEN DIARIO DE HORAS*",
        f"Bolsa Flexible · Período {_dm(inicio)} al {_dm(fin)}",
        "",
        saludo,
        "A continuación, el estado de su bolsa de horas:",
        "",
        f"{_barra(pct)}  *{pct} %*",
        f"▪ Acumulado: *{_hhmm(acum_min)} h* de {_hhmm(meta_min)} h",
    ]
    if acum_min >= meta_min:
        lineas.append(f"✅ *Meta cumplida*, con {_hhmm(acum_min - meta_min)} h de horas extras.")
    else:
        falta = meta_min - acum_min
        lineas.append(f"▪ Pendiente: *{_hhmm(falta)} h*")
        if dias > 0:
            lineas.append(f"▪ Plazo: {_dias(dias)} (promedio requerido: {_hhmm(falta / dias)} h por día)")
    lineas += ["", "_Mensaje automático de Asistencia Aguacol. Ante dudas, consulte con su jefatura._"]
    return "\n".join(lineas)


def armar_mensaje_cierre(nombre: str, acum_min: float, meta_min: float, inicio: str, fin: str) -> str:
    """Lo que recibe cada persona el día que cierra el período: cómo le fue."""
    pct = round(acum_min / meta_min * 100) if meta_min > 0 else 0
    partes = (nombre or "").split()
    lineas = [
        "*CIERRE DEL PERÍODO · BOLSA DE HORAS*",
        f"Período {_dm(inicio)} al {_dm(fin)}",
        "",
        f"Estimado/a {partes[0].capitalize()}," if partes else "Estimado/a,",
        "Hoy cerró el período. Este fue su resultado:",
        "",
    ]
    if meta_min > 0 and acum_min >= meta_min:
        lineas += [f"{_barra(pct)}  *{pct} %*", f"▪ Horas del período: *{_hhmm(acum_min)} h* de {_hhmm(meta_min)} h",
                   f"✅ *Meta cumplida*, con {_hhmm(acum_min - meta_min)} h de horas extras."]
    elif meta_min > 0:
        lineas += [f"{_barra(pct)}  *{_pct_pendiente(acum_min, meta_min)} %*", f"▪ Horas del período: *{_hhmm(acum_min)} h* de {_hhmm(meta_min)} h",
                   f"▪ No alcanzó la meta: faltaron *{_hhmm(meta_min - acum_min)} h*."]
    else:
        lineas.append(f"▪ Horas del período: *{_hhmm(acum_min)} h*")
    lineas += ["", "_Mensaje automático de Asistencia Aguacol. Ante dudas, consulte con su jefatura._"]
    return "\n".join(lineas)


RITMO_ALTO_H = 10  # sobre estas horas diarias para llegar a la meta se marca el caso como difícil de alcanzar


def _nombre_propio(n: object) -> str:
    """«PIÑA LONCOÑANCO JUAN» → «Piña Loncoñanco Juan» (la ficha viene en mayúsculas)."""
    return " ".join(w.capitalize() for w in str(n or "").split())


def _pct_pendiente(acum: float, meta: float) -> int:
    """Avance de quien aún no llega: se trunca y nunca pasa de 99 (179:45 de 180:00 no es «100 %»)."""
    return min(99, int(acum / meta * 100))


def armar_mensaje_jefatura(items: List[Dict[str, Any]], inicio: str, fin: str, hoy: str) -> str:
    """Consolidado de todas las personas con meta, de más a menos horas: quiénes ya cumplieron y a quiénes les falta (con lo que necesitan por día)."""
    dias = max(0, (date.fromisoformat(fin) - date.fromisoformat(hoy)).days)
    con_meta = [i for i in items if i["meta"] > 0]
    cumplen = [i for i in con_meta if i["acum"] >= i["meta"]]
    atras = sorted((i for i in con_meta if i["acum"] < i["meta"]), key=lambda i: i["acum"] / i["meta"])
    prom = round(sum(min(i["acum"] / i["meta"], 1) for i in con_meta) / len(con_meta) * 100) if con_meta else 0
    plazo = "hoy es el último día" if dias == 0 else f"quedan {_dias(dias)}"
    lineas = [
        "*RESUMEN DIARIO · BOLSA DE HORAS*",
        f"Período {_dm(inicio)} al {_dm(fin)} · {plazo}",
        "",
        f"▪ Con meta cumplida: *{len(cumplen)} de {len(con_meta)}*" + (f" ({round(len(cumplen) / len(con_meta) * 100)} %)" if con_meta else ""),
        f"▪ Pendientes: *{len(atras)}*",
        f"▪ Avance promedio: *{prom} %*  {_barra(prom)}",
    ]
    if con_meta:
        d = max(dias, 1)
        lineas += ["", f"✅ meta cumplida · 🟡 alcanzable · 🔴 requiere más de {RITMO_ALTO_H} h diarias"]
        # Un bloque por cargo (choferes primero, luego peonetas, luego el resto), cada uno de más a menos horas.
        grupos: Dict[str, List[Dict[str, Any]]] = {}
        for i in con_meta:
            grupos.setdefault(_norm(i.get("cargo")), []).append(i)
        orden = [c for c in ("CHOFER", "PEONETA") if c in grupos] + sorted(c for c in grupos if c not in ("CHOFER", "PEONETA"))
        for cargo in orden:
            todos = sorted(grupos[cargo], key=lambda i: i["acum"], reverse=True)
            titulo = {"CHOFER": "Choferes", "PEONETA": "Peonetas"}.get(cargo, _nombre_propio(cargo) if cargo else "Detalle por persona")
            lineas += ["", f"*{titulo}* ({len(todos)}, de más a menos horas)"]
            for i in todos[:MAX_LINEAS_JEFATURA]:
                nombre = _nombre_propio(i["nombre"])
                if i["acum"] >= i["meta"]:
                    lineas.append(f"✅ *{nombre}* · {_hhmm(i['acum'])} h (+{_hhmm(i['acum'] - i['meta'])})")
                else:
                    falta = i["meta"] - i["acum"]
                    marca = "🔴" if falta / d > RITMO_ALTO_H * 60 else "🟡"
                    lineas.append(f"{marca} *{nombre}* · {_hhmm(i['acum'])} h ({_pct_pendiente(i['acum'], i['meta'])} %) · faltan *{_hhmm(falta)} h*" + (f" (≈ {_hhmm(falta / d)} h/día)" if dias > 1 else ""))
            if len(todos) > MAX_LINEAS_JEFATURA:
                lineas.append(f"… y {len(todos) - MAX_LINEAS_JEFATURA} más.")
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
            "mensaje_cierre": armar_mensaje_cierre(c.get("nombre") or "", f["acumBolsa"], f["metaMin"], inicio, fin),
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
        recibe = PREFIJO_PERSONA + str(f["id"]) in asignadas
        if not recibe and estado != "manual":
            estado, hallado = "norecibe", None  # quien no recibe el aviso no muestra el contacto que se le encontraría: parecería asignado
        con = estado in ("ok", "manual")
        out.append({"emp_id": f["id"], "nombre": nombre, "area": f["area"] or "", "cargo": f["cargo"] or "", "incluida": pasa_filtro(f["area"], f["cargo"], filtro),
                    "recibe": recibe, "estado": estado, "contacto": hallado["nombre"] if con else None,
                    "numero": _numero_de(hallado["id"]) if con else None, "candidatos": [x["nombre"] for x in hallado] if estado == "ambiguo" else []})
    return out


async def listar_personas(asistencia_service, hoy: str, manuales: Dict[int, Dict[str, Any]], filtro: Dict[str, List[str]] | None = None) -> List[Dict[str, Any]]:
    """Cada persona de Bolsa con el contacto que se le encontró (o su estado), para revisarlo y fijarlo a mano en la pantalla."""
    base = await construir(asistencia_service, hoy, await whatsapp_service.contactos(), manuales, filtro)
    return [{"emp_id": i["emp_id"], "nombre": i["nombre"], "area": i["area"], "cargo": i["cargo"], "incluida": i["incluida"], "estado": i["estado"], "contacto": i["contacto"],
             "numero": _numero_de(i["telefono"]) if i["telefono"] else None, "candidatos": i["candidatos"]} for i in base["personas"]]


async def enviar_resumen(asistencia_service, hoy: str, simular: bool = True, aviso: str = "resumen_personal",
                         destinos: List[str] | None = None, manuales: Dict[int, Dict[str, Any]] | None = None,
                         filtro: Dict[str, List[str]] | None = None, tipo: str = "semanal") -> Dict[str, Any]:
    """simular=True no envía nada: devuelve a quién y qué se enviaría. `destinos` solo para el aviso a chats.
    `tipo` (solo resumen personal): semanal | cierre (cómo le fue en el período que hoy termina) | ambos (solo para probar a mano: se ven y se envían los dos)."""
    if aviso == "resumen_general":
        return await enviar_general(asistencia_service, hoy, simular, destinos, filtro, tipo if tipo in ("atrasos", "extras") else "ambos")
    base = await construir(asistencia_service, hoy, await whatsapp_service.contactos(), manuales, filtro)
    personas = [p for p in base["personas"] if p["incluida"]]  # lo que queda fuera del filtro de área y cargo no se cuenta ni se envía
    if aviso == "resumen_jefatura":
        if not personas:
            # Nunca se manda un consolidado vacío ("0 de 0"): se dice por qué no hay nadie.
            en_bolsa = len(base["personas"])
            motivo = ("No hay personas en Bolsa Flexible en este período." if not en_bolsa else
                      f"Hay {en_bolsa} personas en Bolsa Flexible, pero ninguna cumple el filtro de área y cargo de este aviso. Revise el filtro: solo entran quienes están en Bolsa Flexible.")
            return {"simulado": simular, "aviso": aviso, "personas": 0, "chats": len(destinos or []), "enviados": 0, "fallidos": 0, "motivo": motivo, "vista_previa": []}
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

    claves = ["mensaje", "mensaje_cierre"] if tipo == "ambos" else ["mensaje_cierre" if tipo == "cierre" else "mensaje"]
    con_tel = [i for i in personas if i["telefono"]]
    res = {"simulado": simular, "aviso": aviso, "personas": len(personas), "con_contacto": len(con_tel),
           "sin_contacto": [i["nombre"] for i in personas if i["estado"] == "ninguno"], "manuales": sum(1 for i in personas if i["estado"] == "manual"),
           "ambiguos": [f"{i['nombre']} (¿{' o '.join(i['candidatos'])}?)" for i in personas if i["estado"] == "ambiguo"]}
    if simular:
        res["coincidencias"] = [{"persona": i["nombre"], "contacto": i["contacto"], "numero": _numero_de(i["telefono"])} for i in con_tel]
        etiqueta = {"mensaje": " · resumen del viernes", "mensaje_cierre": " · cierre del período"} if tipo == "ambos" else {}
        res["vista_previa"] = [{"nombre": i["nombre"] + etiqueta.get(k, ""), "telefono": _numero_de(i["telefono"]), "mensaje": i[k]}
                               for i in con_tel[:(1 if tipo == "ambos" else 2)] for k in claves]
        return res
    enviados = fallidos = 0
    for i in con_tel:
        for k in claves:
            if await whatsapp_service.enviar(i["telefono"], i[k]):
                enviados += 1
            else:
                fallidos += 1
            await asyncio.sleep(PAUSA_ENTRE_ENVIOS_SEG)
    logger.info(f"WhatsApp resumen personal ({tipo}): {enviados} enviados, {fallidos} fallidos, {len(personas) - len(con_tel)} sin contacto")
    res.update(enviados=enviados, fallidos=fallidos)
    return res


def dias_a_revisar(hoy: str) -> List[date]:
    """Los días cuyas horas extras se informan a las 08:00: el anterior; el lunes, viernes a domingo (no hay envío sábado ni domingo)."""
    d = date.fromisoformat(hoy)
    return [d - timedelta(days=n) for n in ((3, 2, 1) if d.weekday() == 0 else (1,))]


def _hora(v: object) -> str:
    t = str(v or "")
    t = t.split("T")[-1].split(" ")[-1]
    return t[:5]


async def novedades_general(asistencia_service, hoy: str, momento: str, filtro: Dict[str, List[str]] | None = None) -> List[Dict[str, Any]]:
    """Personas con atraso hoy (momento «atrasos») o con horas extras en los días anteriores (momento «extras»), según el marcaje."""
    dias = [date.fromisoformat(hoy)] if momento == "atrasos" else dias_a_revisar(hoy)
    db = asistencia_service.repository.db
    fichas = {int(r["id"]): r for r in await db.fetch_all("SELECT e.id, e.nombre, e.apellido_paterno, e.apellido_materno, e.cargo, e.activo, a.nombre AS area FROM empleados e LEFT JOIN areas a ON a.id = e.area_id")}
    matriz = await asistencia_service.get_matrix_data_with_projections(
        dias[0].month, dias[0].year, area=None, turno_id=None, fecha_inicio_override=dias[0].isoformat(), fecha_fin_override=dias[-1].isoformat())
    celdas = matriz.get("matrix", {})
    out = []
    for emp in matriz.get("empleados", []):
        f = fichas.get(int(emp["id"]))
        if not f or not f["activo"] or not pasa_filtro(f["area"], f["cargo"], filtro):
            continue
        por_dia = celdas.get(str(emp["id"])) or celdas.get(emp["id"]) or {}
        nombre = " ".join(str(f[k] or "").strip() for k in ("apellido_paterno", "apellido_materno", "nombre") if str(f[k] or "").strip())
        for d in dias:
            di = por_dia.get(d.isoformat())
            if not isinstance(di, dict):
                continue
            if momento == "atrasos":
                if (di.get("minutos_atraso") or 0) > 0 and int(di.get("deuda_condonada") or 0) not in (2, 3, 5) and di.get("hora_entrada_real"):
                    out.append({"nombre": nombre, "cargo": f["cargo"] or "", "dia": d, "minutos": round(di["minutos_atraso"]), "entrada": _hora(di.get("hora_entrada_real"))})
            else:
                extra = max(di.get("minutos_extra_bruto") or 0, di.get("minutos_extra_autorizados") or 0)
                if extra > 0:
                    out.append({"nombre": nombre, "cargo": f["cargo"] or "", "dia": d, "minutos": round(extra), "entrada": ""})
    return sorted(out, key=lambda x: (x["dia"], x["nombre"]))


_DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def armar_mensaje_general(momento: str, items: List[Dict[str, Any]], hoy: str) -> str | None:
    """None si no hay novedades en las horas extras (no se envía nada). Los atrasos del mediodía SIEMPRE se informan: sin atrasos, el mensaje lo dice."""
    if not items:
        if momento == "atrasos":
            return "\n".join(["*ATRASOS DE HOY · BODEGA*", f"Marcajes hasta las 12:00 del {_dm(hoy)}", "", "✅ Hoy no hubo atrasos.", "", "_Mensaje automático de Asistencia Aguacol._"])
        return None
    if momento == "atrasos":
        lineas = ["*ATRASOS DE HOY · BODEGA*", f"Marcajes hasta las 12:00 del {_dm(hoy)}", ""]
        for i in items:
            lineas.append(f"▪ *{_nombre_propio(i['nombre'])}* · {_nombre_propio(i['cargo'])} · entró {i['entrada']} ({i['minutos']} min de atraso)")
    else:
        lineas = ["*HORAS EXTRAS · BODEGA*", "Según el marcaje del día anterior" if len({i["dia"] for i in items}) == 1 else "Según el marcaje de los días anteriores", ""]
        dia_actual = None
        for i in items:
            if i["dia"] != dia_actual:
                dia_actual = i["dia"]
                lineas.append(f"*{_DIAS_ES[dia_actual.weekday()].capitalize()} {_dm(dia_actual.isoformat())}*")
            lineas.append(f"▪ *{_nombre_propio(i['nombre'])}* · {_nombre_propio(i['cargo'])} · {_hhmm(i['minutos'])} h")
    lineas += ["", "_Mensaje automático de Asistencia Aguacol._"]
    return "\n".join(lineas)


async def enviar_general(asistencia_service, hoy: str, simular: bool, destinos: List[str] | None, filtro: Dict[str, List[str]] | None, momento: str) -> Dict[str, Any]:
    """Resumen general de bodega. `momento`: atrasos | extras | ambos (a mano). Los atrasos se envían siempre (también «sin atrasos»); las horas extras, solo si las hubo."""
    momentos = ["extras", "atrasos"] if momento == "ambos" else [momento]
    chats = destinos or []
    mensajes = []
    for m in momentos:
        texto = armar_mensaje_general(m, await novedades_general(asistencia_service, hoy, m, filtro), hoy)
        mensajes.append({"momento": m, "mensaje": texto})
    res: Dict[str, Any] = {"simulado": simular, "aviso": "resumen_general", "chats": len(chats),
                           "con_novedades": sum(1 for x in mensajes if x["mensaje"]),
                           "vista_previa": [{"nombre": {"extras": "Horas extras (día anterior)", "atrasos": "Atrasos de hoy"}[x["momento"]],
                                             "telefono": ", ".join(chats) or "(sin chats asignados)", "mensaje": x["mensaje"] or "Sin novedades: no se enviaría nada."} for x in mensajes]}
    if simular:
        return res
    enviados = fallidos = 0
    for x in mensajes:
        if not x["mensaje"]:
            continue
        for d in chats:
            if await whatsapp_service.enviar(d, x["mensaje"]):
                enviados += 1
            else:
                fallidos += 1
            await asyncio.sleep(PAUSA_ENTRE_ENVIOS_SEG)
    logger.info(f"WhatsApp resumen general: {enviados} enviados, {fallidos} fallidos")
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
    filas = [dict(r) for r in await destinos_de(repo, aviso)]
    return list(dict.fromkeys(x["jid"] for x in await resolver_destinos_chat(db, filas, await repo.destinos_personas()) if x["jid"]))


async def destinos_de(repo: Any, aviso: str) -> List[Any]:
    """Destinos asignados al aviso más los del aviso del que también depende (`tambien_a`), sin repetir."""
    filas = list(await repo.destinos(aviso))
    otro = AVISOS.get(aviso, {}).get("tambien_a")
    if otro:
        vistos = {str(f["destino"]) for f in filas}
        filas += [f for f in await repo.destinos(otro) if str(f["destino"]) not in vistos]
    return filas


async def tipo_de_hoy(asistencia_service, hoy: str) -> str | None:
    """Qué resumen personal toca hoy a las 20:00: «cierre» el último día del período, «semanal» cada viernes, si no nada."""
    from backend.services.cuadre_service import CuadreService
    _, fin = await CuadreService(asistencia_service).tramo_de(hoy)
    if hoy == fin:
        return "cierre"
    return "semanal" if date.fromisoformat(hoy).weekday() == 4 else None


async def enviar_automaticos(asistencia_service, repo, hoy: str, franja: str = "manana") -> Dict[str, Any]:
    """Lo que dispara el cron de cada franja: los avisos encendidos de esa franja, a sus destinatarios."""
    activos = await repo.avisos_activos()
    out: Dict[str, Any] = {}
    for aviso in AVISOS:
        meta = AVISOS[aviso]
        franjas = meta.get("franjas") or {meta.get("franja", "manana"): None}
        if not activos.get(aviso) or meta.get("tiempo_real") or franja not in franjas:
            continue
        tipo = franjas[franja] or "semanal"
        if aviso == "resumen_personal":
            tipo = await tipo_de_hoy(asistencia_service, hoy)
            if tipo is None:
                out[aviso] = {"omitido": "hoy no es viernes ni cierre de período"}
                continue
        chats = await destinos_chat(asistencia_service.repository.db, repo, aviso) if meta["usa_chats"] else None
        out[aviso] = await enviar_resumen(asistencia_service, hoy, simular=False, aviso=aviso, destinos=chats, manuales=await repo.destinos_personas(),
                                          filtro=(await repo.filtros(aviso)).get(aviso), tipo=tipo)
    return out
