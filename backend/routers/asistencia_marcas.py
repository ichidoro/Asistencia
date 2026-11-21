"""
Router - Asistencia: marcas manuales y marcas del día (agregar, quitar y borrar marcas manuales, ver las marcas de un
día y elegir cuál es Entrada o Salida, y marcas masivas), con sus funciones de apoyo. Separado de routers/asistencia.py en
la etapa 6 de la auditoría, con el mismo código; las direcciones siguen bajo /api/asistencia (asistencia.py incluye este
router).
"""
import json
from fastapi import Query, HTTPException, Depends, Body
from pydantic import BaseModel
from typing import Optional, Dict, Set, Any, List
from datetime import datetime, timedelta
from loguru import logger
from backend.services.asistencia_service import AsistenciaService
from backend.services import quantum_matrix_engine as _motor
from backend.services.reglas_marcas_def import secuencia_en_revision, TIPO_NO_SE_USA, propuesta_una_marca, propuesta_tres_marcas, propuesta_cinco_marcas
from backend.repositories.asistencia import AsistenciaRepository
from backend.repositories.empleado import EmpleadoRepository
from backend.repositories.turno import TurnoRepository
from backend.repositories.seguridad import SeguridadRepository
from backend.core.security import RequirePermission, SecurityContext
from backend.routers.asistencia_comun import get_asistencia_service
from fastapi import APIRouter

router = APIRouter()


# ── Salida de un turno de noche ingresada a mano (2026-10-16) ─────────────────────────────────────────────────────────────────
# Caso Eduardo Donoso 11-10: se ingresó Entrada 23:00 y Salida 07:00 y las dos quedaron con fecha 11-10; la Salida (07:00 del 11) cayó
# en el turno de la noche anterior, sin Entrada, y el panel pedía "ingrese la Entrada faltante" (falso positivo). Una jornada no termina antes
# de empezar: la Salida igual o anterior a la Entrada es la del día siguiente.
def _hora_con_segundos(hora: Any) -> str:
    """'07:00' o '07:00:00' → '07:00:00'. Una hora que no existe (25:00, 7) es un error, no una marca."""
    h = str(hora).strip()
    h = f"{h}:00" if h.count(":") == 1 else h
    try:
        return datetime.strptime(h, "%H:%M:%S").strftime("%H:%M:%S")
    except ValueError:
        raise ValueError(f"Hora inválida: «{hora}». Use el formato HH:MM.") from None


def fecha_de_la_salida(fecha: str, hora_salida: Any, hora_entrada: Any = None, cruza_medianoche: bool = False) -> str:
    """
    Fecha (YYYY-MM-DD) en que cae la Salida de la jornada que empieza en `fecha`.
      · el turno declara que cruza la medianoche → el día siguiente;
      · la Salida es igual o anterior a la Entrada (23:00 → 07:00) → el día siguiente;
      · sin Entrada con la que compararla (y sin el aviso del turno) → la misma fecha: no se inventa nada.
    """
    manana = (datetime.strptime(fecha, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    if cruza_medianoche:
        return manana
    if hora_entrada and _hora_con_segundos(hora_salida) <= _hora_con_segundos(hora_entrada):
        return manana
    return fecha


def _marca_en_el_futuro(fecha_hora: str, ahora: datetime) -> bool:
    """
    True si la marca cae después del minuto actual. Una marca manual registra algo que YA ocurrió: una hora que todavía no llega no se mide,
    se supone (caso 17-10-2026: 22 marcas, entre ellas Salidas de las 14:00 ingresadas a las 09:30). Se compara al minuto, porque el formulario
    manda horas sin segundos: la hora de este mismo minuto es válida.
    """
    return datetime.strptime(str(fecha_hora)[:19], "%Y-%m-%d %H:%M:%S") > ahora.replace(second=59, microsecond=0)


_TIPOS_ENTRADA = ('entrada', 'entry', 'e', 'in', '1')
_TIPOS_SALIDA = ('salida', 'exit', 's', 'out', '2')


async def _hora_de_entrada_sin_cerrar(db, empleado_id: int, fecha: str) -> Optional[str]:
    """Hora (HH:MM:SS) de la última marca de `fecha` si es una Entrada (con el tipo ya corregido por una persona): una Entrada sin Salida."""
    ultima = await AsistenciaRepository(db).get_ultima_marca_del_dia(empleado_id, fecha)
    if ultima and str(ultima["tipo"] or "").strip().lower() in _TIPOS_ENTRADA:
        return str(ultima["fecha_hora"])[11:19]
    return None


def _rellena_un_hueco(marcas: List[Dict[str, Any]], fecha_hora: str, tipo: str) -> bool:
    """True si una marca suelta cae ENTRE dos marcas del día que la piden: una SALIDA entre dos Entradas (faltó la
    salida a colación) o una ENTRADA entre dos Salidas (faltó la vuelta de colación). No pisa al reloj: completa la
    secuencia, igual que la propuesta de la regla en la ventana. Antes de la primera marca o después de la última no
    cuenta, así no sirve para borrar un atraso o una salida adelantada (para eso está el Perdonazo)."""
    t = str(tipo or "").strip().lower()
    if t not in ("entrada", "salida"):
        return False
    opuesto = _TIPOS_SALIDA if t == "entrada" else _TIPOS_ENTRADA
    fh = str(fecha_hora)[:19]
    antes = [m for m in marcas if str(m["fecha_hora"])[:19] < fh]
    despues = [m for m in marcas if str(m["fecha_hora"])[:19] > fh]
    if not antes or not despues:
        return False
    return (str(antes[-1]["tipo"] or "").strip().lower() in opuesto
            and str(despues[0]["tipo"] or "").strip().lower() in opuesto)


def _duracion_texto(fh_desde: str, fh_hasta: str) -> str:
    minutos = _min_abs(fh_hasta) - _min_abs(fh_desde)
    return f"{minutos // 60} h {minutos % 60:02d} min"


@router.post("/marcaciones/manual/")
async def agregar_marcacion_manual(
    empleado_id: int,
    fecha: str,
    hora: Optional[str] = None,
    tipo: Optional[str] = Query(None, pattern="^(Entrada|Salida)$"),
    hora_entrada: Optional[str] = None,
    hora_salida: Optional[str] = None,
    observaciones: Optional[str] = None,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Agrega marcación(es) manual(es) y reprocesa la asistencia del día en una sola transacción.
    Acepta (hora + tipo) para 1 marca, o (hora_entrada + hora_salida) para ambas en 1 sola llamada.
    """
    # RLS: Verificar pertenencia
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    current_user.verificar_acceso_area(emp.area, "este empleado")

    # Blindaje de Cierre
    if await service.repository.check_fecha_cerrada(fecha, empleado_id):
         raise HTTPException(status_code=403, detail="El periodo de esta fecha se encuentra cerrado y no admite modificaciones.")

    try:
        import hashlib
        db = service.repository.db
        rut = emp.rut if emp and emp.rut else str(empleado_id)
        obs_str = observaciones or "Marcación manual"

        # Blindaje: No permitir sobreescribir si ya existen ambas marcas biométricas en el reloj
        bio_logs = await AsistenciaRepository(db).get_marcas_del_reloj_del_dia(empleado_id, fecha)
        has_bio_in = any(str(b.get('tipo', '')).strip().lower() in ('entrada', 'entry', 'e', 'in', '1') for b in bio_logs)
        has_bio_out = any(str(b.get('tipo', '')).strip().lower() in ('salida', 'exit', 's', 'out', '2') for b in bio_logs)
        # Una SALIDA sola que cierra la última ENTRADA del día (segunda jornada, u olvido tras la colación) no pisa al reloj:
        # completa la marca que falta, así que se permite aunque el reloj ya tenga Entrada y Salida ese día.
        solo_salida = bool((hora_salida and not hora_entrada) or (tipo == "Salida" and hora and not hora_entrada and not hora_salida))
        cierra_entrada = solo_salida and bool(await _hora_de_entrada_sin_cerrar(db, empleado_id, fecha))
        # Una marca suelta que rellena un hueco entre dos marcas (la propuesta de la regla en «Corregir marcas del día»,
        # caso 19-11-2026: Entrada · Entrada · Salida, faltaba la salida a colación) tampoco pisa al reloj.
        rellena_hueco = False
        if has_bio_in and has_bio_out and not cierra_entrada and tipo and hora and not hora_entrada and not hora_salida:
            rellena_hueco = _rellena_un_hueco(await AsistenciaRepository(db).get_marcas_del_dia_en_orden(empleado_id, fecha),
                                              f"{fecha} {_hora_con_segundos(hora)}", tipo)
        if has_bio_in and has_bio_out and not cierra_entrada and not rellena_hueco and not getattr(current_user, 'is_superuser', False):
            raise HTTPException(
                status_code=400,
                detail="Esta jornada ya cuenta con marcaciones biométricas válidas de Entrada y Salida en el reloj. Si desea condonar un atraso o salida anticipada, utilice la función oficial de Perdonazo."
            )

        marcas_a_insertar = []
        aviso = None
        hora_entrada_ok = hora_entrada if hora_entrada and str(hora_entrada).strip() not in ('', 'null', 'undefined') else None
        if hora_entrada_ok:
            fh_ent = f"{fecha} {_hora_con_segundos(hora_entrada_ok)}"
            marcas_a_insertar.append((fh_ent, "Entrada"))
        if hora_salida and str(hora_salida).strip() not in ('', 'null', 'undefined'):
            # Blindaje contra artefacto 00:00 de salida cuando se acompaña con entrada matutina diurna
            h_sal_clean = str(hora_salida).strip()
            h_ent_clean = str(hora_entrada).strip() if hora_entrada else ""
            if h_sal_clean in ('00:00', '00:00:00') and h_ent_clean and '06:00' <= h_ent_clean <= '12:00':
                logger.warning(f"Ignorando salida espuria 00:00 para entrada matutina {h_ent_clean} de empleado {empleado_id}")
            else:
                # Sin Entrada en esta petición, se compara con la Entrada que el día dejó sin cerrar (si la hay)
                ent_ref = hora_entrada_ok or await _hora_de_entrada_sin_cerrar(db, empleado_id, fecha)
                fh_sal, aviso = await _armar_salida_manual(service, empleado_id, fecha, hora_salida, ent_ref)
                marcas_a_insertar.append((fh_sal, "Salida"))
        if not hora_entrada and not hora_salida and hora and tipo:
            if tipo == "Salida":
                fh_single, aviso = await _armar_salida_manual(service, empleado_id, fecha, hora,
                                                              await _hora_de_entrada_sin_cerrar(db, empleado_id, fecha))
            else:
                fh_single = f"{fecha} {_hora_con_segundos(hora)}"
            marcas_a_insertar.append((fh_single, tipo))

        if not marcas_a_insertar:
            raise HTTPException(status_code=400, detail="Debe proporcionar 'hora' y 'tipo' o bien 'hora_entrada' / 'hora_salida'")

        # Una marca manual registra algo que ya pasó. Si alguna cae en el futuro no se guarda ninguna (el resto se puede ingresar ahora)
        ahora = _motor._get_now_local()
        futuras = [fh for fh, _ in marcas_a_insertar if _marca_en_el_futuro(fh, ahora)]
        if futuras:
            cuando = ", ".join(f"{fh[11:16]} del {fh[8:10]}-{fh[5:7]}" for fh in futuras)
            raise HTTPException(status_code=400, detail=(
                (f"La marca de las {cuando} todavía no ocurre" if len(futuras) == 1 else f"Las marcas de las {cuando} todavía no ocurren")
                + f" (ahora son las {ahora.strftime('%H:%M')} del {ahora.strftime('%d-%m')}). "
                  "Una marca manual solo registra algo que ya pasó: ingrésela cuando ocurra."))

        for fh, t in marcas_a_insertar:
            raw_string = f"{rut}|{fh}|{t}"
            hash_val = hashlib.sha256(raw_string.encode()).hexdigest()
            await AsistenciaRepository(db).insertar_marca_manual(empleado_id, rut, fh, t, obs_str, hash_val,
                                                                 getattr(current_user, "user_id", None))

        # 2. Reprocesar asistencia del día UNA SOLA VEZ
        resultado = await service.procesar_empleado_dia(empleado_id, fecha, save=True)
        # La Salida de un turno de noche cae al día siguiente: ese día también ve la marca; si ya estaba calculado, se recalcula
        for otro_dia in sorted({fh[:10] for fh, _ in marcas_a_insertar} - {fecha}):
            if (otro_dia <= datetime.now().strftime("%Y-%m-%d") and await service.repository.get_asistencia(empleado_id, otro_dia)
                    and not await service.repository.check_fecha_cerrada(otro_dia, empleado_id)):
                await service.procesar_empleado_dia(empleado_id, otro_dia, save=True)

        return {
            "success": True,
            "mensaje": f"Se agregaron {len(marcas_a_insertar)} marcaciones manuales y se reprocesó la asistencia",
            "aviso": aviso,
            "asistencia": resultado
        }
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _armar_salida_manual(service: AsistenciaService, empleado_id: int, fecha: str, hora_salida: Any, hora_entrada: Optional[str]):
    """
    Fecha y hora completas de una Salida manual de la jornada que empieza en `fecha`, y el aviso si quedó al día siguiente.
    Si ese día siguiente está en un período cerrado no se agrega la marca (no se puede modificar).
    """
    fecha_sal = fecha_de_la_salida(fecha, hora_salida, hora_entrada)
    fh_sal = f"{fecha_sal} {_hora_con_segundos(hora_salida)}"
    if fecha_sal == fecha:
        return fh_sal, None
    if await service.repository.check_fecha_cerrada(fecha_sal, empleado_id):
        raise HTTPException(status_code=403, detail=f"La Salida cae el {fecha_sal[8:]}-{fecha_sal[5:7]} (día siguiente) y ese período está cerrado: no admite modificaciones.")
    aviso = (f"La Salida de las {fh_sal[11:16]} quedó el {fecha_sal[8:]}-{fecha_sal[5:7]} (día siguiente) porque es anterior a la Entrada: "
             "el turno cruza la medianoche.")
    if hora_entrada:
        aviso += f" Jornada de {_duracion_texto(f'{fecha} {_hora_con_segundos(hora_entrada)}', fh_sal)}: revise que sea correcta."
    return fh_sal, aviso

# ── Marcaciones del día: ver todas y elegir cuál es Entrada / Salida (2026-10-14) ─────────────────────────
# Caso Catalina Núñez 09-10: el reloj dejó la primera marca del día como "Salida" y el motor la descartaba (atraso falso de 273 min).
# La marca cruda no se toca: la reclasificación se guarda aparte (logs_tipo_override) y el motor lee el tipo ya corregido.
_COLACION_MIN, _COLACION_MAX = 20, 150  # minutos entre una salida y la siguiente entrada para considerarlas colación


def ciclo_para_marca_sola(ciclos: List[Dict[str, Any]], hora: str, tipo: str) -> Optional[Dict[str, Any]]:
    """De los ciclos del horario para ese día, el que mejor calza con una marca sola según su TIPO: una SALIDA se
    compara con la salida de cada ciclo y una ENTRADA con la entrada (distancia en el reloj de 24 horas). Sirve para
    proponer la marca que falta. Devuelve None si no hay ciclos o el tipo no se reconoce."""
    clave = 'hora_salida' if str(tipo or '').strip().lower().startswith('s') else (
        'hora_entrada' if str(tipo or '').strip().lower().startswith('e') else None)
    if not clave or not ciclos:
        return None

    def minutos(h):
        hh, mm = str(h)[:5].split(':')
        return int(hh) * 60 + int(mm)
    m = minutos(hora)

    def distancia(c):
        d = abs(minutos(c[clave]) - m)
        return min(d, 1440 - d)
    return min(ciclos, key=distancia)


def _min_abs(fh: str) -> int:
    """Minutos de una marca contados desde el año 1 (fecha + hora): sirve para medir huecos que cruzan la medianoche."""
    fh = str(fh)
    return datetime.strptime(fh[:10], "%Y-%m-%d").toordinal() * 1440 + int(fh[11:13]) * 60 + int(fh[14:16])


def _ids_de_json(txt: Any) -> Set[int]:
    """Ids de marcas guardados como texto JSON (asistencias.marcas_consumidas_ids)."""
    try:
        v = json.loads(txt) if isinstance(txt, (str, bytes)) else (txt or [])
    except Exception:
        return set()
    out: Set[int] = set()
    for x in (v if isinstance(v, list) else []):
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            pass
    return out


def marcas_que_pertenecen_al_dia(fecha: str, marcas: List[Dict[str, Any]], ids_dia: Set[int], ids_vecinos: Set[int]) -> List[Dict[str, Any]]:
    """
    De las marcas de ayer, hoy y mañana, cuáles son de la jornada de `fecha` (la columna "marcas del día" del modal):
      · las que usó el cálculo de ese día (`ids_dia`), aunque caigan en la fecha siguiente del calendario: un turno que cruza la
        medianoche cierra con una marca del día siguiente (Entrada 14:59 del 13 · Salida 00:08 del 14 son una sola jornada);
      · las que nadie usó y caen en esa fecha del calendario;
      · nunca las que usó el día anterior o el siguiente (`ids_vecinos`): la Salida de las 00:08 del 14 es del turno del 13.
    Sin cálculo previo del día (`ids_dia` vacío) queda lo que cae en la fecha del calendario menos lo que ya usó un día vecino.
    """
    out = []
    for m in marcas:
        mid = m.get("id")
        if mid in ids_dia or (str(m.get("fecha_hora", ""))[:10] == fecha and mid not in ids_vecinos):
            out.append(m)
    return sorted(out, key=lambda m: str(m.get("fecha_hora", "")))


async def _marcas_del_dia(db, empleado_id: int, fecha: str) -> List[Dict[str, Any]]:
    """Marcas (con el tipo ya corregido por una persona, si lo hubo) que pertenecen a la jornada de `fecha`. Incluye las que
    una persona dejó como «No se usa» (tipo 'No se usa'): el cálculo no las lee, pero la ventana las muestra para poder deshacerlo."""
    f = datetime.strptime(fecha, "%Y-%m-%d")
    ayer, manana = (f - timedelta(days=1)).strftime("%Y-%m-%d"), (f + timedelta(days=1)).strftime("%Y-%m-%d")
    repo = AsistenciaRepository(db)
    rows = await repo.get_marcas_entre(empleado_id, f"{ayer} 00:00:00", f"{manana} 23:59:59")
    asist = await repo.get_marcas_usadas_por_dia(empleado_id, (ayer, fecha, manana))
    usadas = {str(a["fecha"])[:10]: _ids_de_json(a["marcas_consumidas_ids"]) for a in asist}
    return marcas_que_pertenecen_al_dia(fecha, [dict(r) for r in rows], usadas.get(fecha, set()),
                                        usadas.get(ayer, set()) | usadas.get(manana, set()))


def marcas_doble_toque(rows: List[Dict[str, Any]], segundos: float) -> Dict[Any, Dict[str, Any]]:
    """Las marcas que el cálculo descarta como doble toque, con la misma limpieza que usa el motor
    (TensorMarkDeduplicator.deduplicate_and_sort). Devuelve {id descartada: {"hora": hora de la que se usó, "segundos": separación}}
    para que la ventana muestre lo mismo que ve la regla."""
    from backend.services.quantum_matrix_engine import TensorMarkDeduplicator
    descartadas: List[Any] = []
    TensorMarkDeduplicator.deduplicate_and_sort([dict(r) for r in rows], bounce_seconds=segundos, descartadas=descartadas)
    out: Dict[Any, Dict[str, Any]] = {}
    for desc, cons in descartadas:
        try:
            t_d = datetime.strptime(str(desc["fecha_hora"])[:19], "%Y-%m-%d %H:%M:%S")
            t_c = datetime.strptime(str(cons["fecha_hora"])[:19], "%Y-%m-%d %H:%M:%S")
        except (KeyError, ValueError):
            continue
        out[desc.get("id")] = {"hora": str(cons["fecha_hora"])[11:19], "segundos": int(abs((t_d - t_c).total_seconds()))}
    return out


async def _colacion_tipica(db, turno_id, hora_entrada) -> Optional[Dict[str, Any]]:
    """A qué hora salen y vuelven de colación las personas de un horario (mismo horario y misma hora de entrada): la mediana
    de la 2.ª y la 3.ª marca de los días ENTRADA · SALIDA · ENTRADA · SALIDA del reloj, sin marcas manuales, del tramo
    abierto. Se calcula con las marcas reales cada vez (≈70 ms en el horario más grande); None si no hay ningún día así."""
    import statistics
    from backend.repositories.reglas_marcas import ReglasMarcasRepository
    desde = await ReglasMarcasRepository(db).inicio_tramo_abierto()
    filas = await AsistenciaRepository(db).get_marcas_del_reloj_de_un_horario(turno_id, hora_entrada, desde)
    sale, vuelve = [], []
    for f in filas:
        if f["pat"] != "ESES" or int(f["man"] or 0):
            continue
        h = str(f["horas"]).split(",")
        sale.append(int(h[1][:2]) * 60 + int(h[1][3:5]))
        vuelve.append(int(h[2][:2]) * 60 + int(h[2][3:5]))
    if not sale:
        return None
    return {"sale": int(statistics.median(sale)), "vuelve": int(statistics.median(vuelve)), "dias": len(sale)}


async def _propuesta_dia_tres_marcas(service, empleado_id: int, fecha: str, usadas, hd, horario, col_horario: int, tipica=None,
                                     doble_toque=None):
    """Opciones para la ventana (ver propuesta_tres_marcas), con el tipo de cada marca por id, la marca nueva con su fecha y
    lo que pagaría cada una: el día se calcula en memoria con esas marcas (collect_only, no se guarda nada)."""
    from backend.repositories.reglas_marcas import ReglasMarcasRepository
    db = service.repository.db
    vc = await ReglasMarcasRepository(db).ventana_colacion()
    if tipica is None and hd.get("turno_asignado_id"):
        tipica = await _colacion_tipica(db, hd.get("turno_asignado_id"), horario["entrada"])
    fhs = [str(r["fecha_hora"])[:19] for r in usadas]
    if len(usadas) == 1:
        p = propuesta_una_marca(fhs[0], usadas[0]["tipo"], horario["entrada"], horario["salida"])
    elif len(usadas) == 5:
        p = propuesta_cinco_marcas(fhs, [r["tipo"] for r in usadas], col_horario)
    else:
        p = propuesta_tres_marcas(fhs, horario["entrada"], horario["salida"], int(vc.get("min", 20)), int(vc.get("max", 150)),
                                  col_horario, tipica, tipos=[r["tipo"] for r in usadas])
    if not p:
        return None
    marcas_dt = [datetime.strptime(x, "%Y-%m-%d %H:%M:%S") for x in fhs]
    opciones = []
    for op in p["opciones"]:
        marca = None
        if op["marca"]:
            # La marca nueva va en su lugar: después de la marca que la antecede o antes de la que la sigue (turnos de noche)
            hh, mm = map(int, op["marca"]["hora"].split(":"))
            if op["clave"] == "FALTA_ENTRADA":
                ref, antes = marcas_dt[0], True
            elif op["clave"] == "FALTA_SALIDA":
                ref, antes = marcas_dt[-1], False
            elif op["clave"] == "FALTA_VUELTA":
                ref, antes = marcas_dt[1], False
            else:
                ref, antes = marcas_dt[1], True
            dt = ref.replace(hour=hh, minute=mm, second=0)
            if antes and dt > ref:
                dt -= timedelta(days=1)
            if not antes and dt < ref:
                dt += timedelta(days=1)
            marca = dict(op["marca"], fecha_hora=dt.strftime("%Y-%m-%d %H:%M:%S"), fecha=dt.strftime("%Y-%m-%d"))
        tipos_op = {str(r["id"]): t for r, t in zip(usadas, op["tipos"])}
        # Una marca que no se usa arrastra su doble toque: si no, la descartada vuelve a contar y el día cambia de secuencia
        for r, t in zip(usadas, op["tipos"]):
            if t == TIPO_NO_SE_USA:
                for id_dt, info in (doble_toque or {}).items():
                    if str(info.get("hora")) == str(r["fecha_hora"])[11:19]:
                        tipos_op[str(id_dt)] = TIPO_NO_SE_USA
        opciones.append({"clave": op["clave"], "titulo": op["titulo"], "motivo": op["motivo"], "marca": marca,
                         "tipos": tipos_op})

    async def paga(op):
        tipos = op["tipos"]
        base = dict(usadas[0])

        def transformar(logs):
            out = []
            for l in logs:
                t = tipos.get(str(l.get("id")))
                if t == TIPO_NO_SE_USA:
                    continue
                out.append(dict(l, tipo=t) if t else l)
            if op["marca"]:
                out.append(dict(base, id=-1, fecha_hora=op["marca"]["fecha_hora"], tipo=op["marca"]["tipo"],
                                tipo_original=op["marca"]["tipo"], manual=1, observaciones=op["motivo"]))
            return out
        r = await service.reprocesar_periodo_empleado(empleado_id, fecha, fecha, force=True, collect_only=True,
                                                      transformar_logs=transformar)
        fila = next((c for c in (r.get("_collect") or []) if str(c.get("fecha")) == fecha), None)
        if not fila and r.get("sin_cambio"):
            # Con esas marcas el día da lo mismo que ya está guardado: el cálculo no lo devuelve, se lee lo guardado
            fila = await AsistenciaRepository(db).get_resultado_dia(empleado_id, fecha)
        if not fila:
            return None
        return {"horas": round(float(fila.get("horas_trabajadas") or 0), 2), "estado": fila.get("estado"),
                "deuda_min": round(float(fila.get("minutos_deuda") or 0)),
                "atraso_min": round(float(fila.get("minutos_atraso") or 0)),
                "salida_adelantada_min": round(float(fila.get("minutos_salida_adelantada") or 0))}

    for op in opciones:
        try:
            op["resultado"] = await paga(op)
        except Exception as e:
            logger.warning(f"Simulación de la opción {op['clave']} ({empleado_id} {fecha}): {e}")
            op["resultado"] = None
    return {"combinacion": p["combinacion"], "opciones": opciones, "colacion_tipica": tipica}


def sugerir_clasificacion_marcas(horas: List[str]) -> List[Dict[str, Any]]:
    """
    Sugerencia de Entrada/Salida para las marcas de un día (ya ordenadas), y cuáles serían de colación.
      · primera = Entrada, última = Salida, el resto alterna.
      · una Salida seguida de una Entrada a mitad del día, separadas por 20-150 min = colación.
    Con una cantidad impar de marcas no se puede afirmar: se devuelve la alternancia pero con `dudoso`.
    """
    n = len(horas)
    out = [{"tipo": ("Entrada" if i % 2 == 0 else "Salida"), "colacion": False} for i in range(n)]
    if n >= 2:
        out[-1]["tipo"] = "Salida"
    for i in range(1, n - 1):
        if out[i]["tipo"] == "Salida" and out[i + 1]["tipo"] == "Entrada" and i + 1 <= n - 2:
            gap = _min_abs(horas[i + 1]) - _min_abs(horas[i])
            if _COLACION_MIN <= gap <= _COLACION_MAX:
                out[i]["colacion"] = out[i + 1]["colacion"] = True
                out[i]["colacion_min"] = out[i + 1]["colacion_min"] = gap
    dudoso = n % 2 == 1 or n < 2
    for o in out:
        o["dudoso"] = dudoso
    return out


@router.get("/marcaciones/dia/")
async def marcaciones_del_dia(
    empleado_id: int = Query(...),
    fecha: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """Todas las marcaciones de la jornada con lo que dijo el reloj, el tipo que rige hoy y una sugerencia (con la colación marcada).
    Incluye la marca del día siguiente que cerró un turno que cruza la medianoche y deja fuera la que cerró el turno de ayer."""
    emp = await EmpleadoRepository(service.repository.db).get_by_id(empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    current_user.verificar_acceso_area(emp.area, "este empleado")
    # Las marcas de la jornada, no solo las del día del calendario: un turno que cruza la medianoche cierra con una marca de mañana
    rows = await _marcas_del_dia(service.repository.db, empleado_id, fecha)
    # Horario asignado de ese día (lo guarda el cálculo en la asistencia): la ventana lo propone al escribir la marca que falta
    hd = await AsistenciaRepository(service.repository.db).get_horario_y_calculo_dia(empleado_id, fecha)
    turno_repo = TurnoRepository(service.repository.db)
    # Doble toque: las marcas que el cálculo deja fuera antes de aplicar la regla. La sugerencia y la colación se calculan
    # solo con las que se usan, igual que el cálculo.
    doble_toque: Dict[Any, Dict[str, Any]] = {}
    col_horario = 0
    tp = None
    try:
        from backend.services.quantum_matrix_engine import _rebote_defecto
        if hd and hd.get("turno_asignado_id"):
            t = await turno_repo.get_tipo_y_colacion(hd["turno_asignado_id"])
            tp = (t or {}).get("tipo_programacion")
            col_horario = int(float((t or {}).get("minutos_colacion_auto") or 0))
        # Las que una persona dejó como «No se usa» tampoco las lee el cálculo
        doble_toque = marcas_doble_toque([r for r in rows if r["tipo"] != TIPO_NO_SE_USA], _rebote_defecto(tp or ""))
    except Exception as e:
        logger.warning(f"Doble toque en la ventana ({empleado_id} {fecha}): {e}")
    no_usada = lambda r: r["id"] in doble_toque or r["tipo"] == TIPO_NO_SE_USA
    usadas = [r for r in rows if not no_usada(r)]
    sug_usadas = iter(sugerir_clasificacion_marcas([str(r["fecha_hora"]) for r in usadas]))
    sug = [({"tipo": r["tipo"], "colacion": False, "dudoso": len(usadas) % 2 == 1 or len(usadas) < 2}
            if no_usada(r) else next(sug_usadas)) for r in rows]
    horario = {"entrada": (hd or {}).get("hora_entrada_teorica"), "salida": (hd or {}).get("hora_salida_teorica")}
    # Tres marcas que se usan (falta una o sobra una), en un día que una regla dejó en revisión: una o dos opciones completas
    # según el horario del día y la colación de su mismo horario (reglas_marcas_def.propuesta_tres_marcas), cada una con lo
    # que pagaría (simulación sin guardar nada).
    # A qué hora sale y vuelve de colación su horario (marcas reales; Ciclo Inteligente): la ventana lo muestra en «Horario del día»
    tipica = None
    if hd and hd.get("turno_asignado_id") and tp == "CICLO_INTELIGENTE" and horario["entrada"]:
        try:
            tipica = await _colacion_tipica(service.repository.db, hd["turno_asignado_id"], horario["entrada"])
        except Exception as e:
            logger.warning(f"Colación típica ({empleado_id} {fecha}): {e}")
    # Con UNA sola marca, el ciclo del día no es seguro (el cálculo lo elige por la marca más cercana, sin mirar su tipo).
    # La propuesta usa el ciclo del horario asignado que calza con esa marca según lo que falte.
    if len(usadas) == 1 and hd and hd.get("turno_asignado_id"):
        try:
            dia_semana = datetime.strptime(fecha, "%Y-%m-%d").weekday()
            ciclos = await turno_repo.get_ciclos_del_dia(hd["turno_asignado_id"], dia_semana)
            ciclos = [dict(c) for c in ciclos]
            hora_sola = str(usadas[0]["fecha_hora"])[11:16]
            # Si falta la ENTRADA, la marca que hay es la SALIDA: ciclo cuya salida calza. Si falta la SALIDA, la marca
            # que hay es la ENTRADA: ciclo cuya entrada calza. Así sirve aunque el reloj la haya rotulado al revés.
            como_salida = ciclo_para_marca_sola(ciclos, hora_sola, "Salida")
            como_entrada = ciclo_para_marca_sola(ciclos, hora_sola, "Entrada")
            if como_salida and como_entrada:
                horario = {"entrada": como_salida["hora_entrada"], "salida": como_entrada["hora_salida"]}
        except Exception as e:
            logger.warning(f"Ciclo para la marca sola ({empleado_id} {fecha}): {e}")
    # Una, tres o cinco marcas en un día que una regla dejó en revisión: opciones ya resueltas (con una sola marca, con el
    # horario del ciclo que calza con ella)
    propuesta = None
    if len(usadas) in (1, 3, 5) and hd and secuencia_en_revision(hd.get("observaciones")):
        try:
            propuesta = await _propuesta_dia_tres_marcas(service, empleado_id, fecha, usadas, hd, horario, col_horario, tipica,
                                                     doble_toque)
        except Exception as e:
            logger.warning(f"Propuesta de marcas ({empleado_id} {fecha}): {e}")
    return {
        "success": True,
        "fecha_cerrada": bool(await service.repository.check_fecha_cerrada(fecha, empleado_id)),
        "horario": horario,
        "propuesta": propuesta,
        # «Horario del día» y «Cálculo» de la ventana: lo que hoy tiene guardado el día (el ciclo que eligió el cálculo;
        # «horario» puede mezclar dos ciclos para proponer la marca que falta en un día de una sola marca)
        "horario_dia": {"entrada": (hd or {}).get("hora_entrada_teorica"), "salida": (hd or {}).get("hora_salida_teorica")},
        "colacion_min": col_horario,
        "colacion_tipica": tipica,
        "bolsa": tp in ("BOLSA_FLEXIBLE", "FLEXIBLE_BOLSA"),
        "calculo": ({"estado": hd.get("estado"), "horas": round(float(hd.get("horas_trabajadas") or 0), 2),
                     "atraso_min": round(float(hd.get("minutos_atraso") or 0)),
                     "salida_adelantada_min": round(float(hd.get("minutos_salida_adelantada") or 0)),
                     "deuda_min": round(float(hd.get("minutos_deuda") or 0))} if hd else None),
        "marcas": [{
            "id": r["id"], "hora": str(r["fecha_hora"])[11:19], "fecha": str(r["fecha_hora"])[:10],
            "tipo_reloj": r["tipo_original"], "tipo_actual": r["tipo"],
            "corregida": (r["tipo"] != r["tipo_original"]), "manual": bool(r["manual"]), "equipo": r.get("equipo"),
            "sugerido": s["tipo"], "colacion": s["colacion"], "colacion_min": s.get("colacion_min"), "dudoso": s["dudoso"],
            "doble_toque": doble_toque.get(r["id"]), "no_se_usa": r["tipo"] == TIPO_NO_SE_USA,
        } for r, s in zip(rows, sug)],
    }


class MarcaTipoItem(BaseModel):
    id: int
    tipo: str


class ReclasificarMarcasRequest(BaseModel):
    empleado_id: int
    fecha: str
    marcas: List[MarcaTipoItem]


@router.post("/marcaciones/reclasificar/")
async def reclasificar_marcaciones(
    req: ReclasificarMarcasRequest,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """Fija si cada marca del día es Entrada o Salida y reprocesa el día. Las marcas crudas del reloj no se modifican."""
    emp = await EmpleadoRepository(service.repository.db).get_by_id(req.empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    current_user.verificar_acceso_area(emp.area, "este empleado")
    if await service.repository.check_fecha_cerrada(req.fecha, req.empleado_id):
        raise HTTPException(status_code=403, detail="El periodo de esta fecha se encuentra cerrado y no admite modificaciones.")
    if not req.marcas:
        raise HTTPException(status_code=400, detail="No hay marcaciones para clasificar.")
    nuevos = {}
    for m in req.marcas:
        t = (m.tipo or "").strip().capitalize()
        if t not in ("Entrada", "Salida", TIPO_NO_SE_USA):
            raise HTTPException(status_code=400, detail=f"Tipo inválido para la marca {m.id}: debe ser Entrada, Salida o No se usa.")
        nuevos[m.id] = t
    db = service.repository.db
    ids = list(nuevos.keys())
    ph = ",".join("?" * len(ids))
    # Solo marcas de ESTE empleado y de ESTA jornada (no se puede tocar una marca ajena por el id)
    del_dia = {m["id"]: m for m in await _marcas_del_dia(db, req.empleado_id, req.fecha)}
    permitidas = set(del_dia)
    orig = await AsistenciaRepository(db).get_tipos_de_marcas(ids, req.empleado_id)
    orig = {r["id"]: r["tipo"] for r in orig}
    if len(orig) != len(ids) or not set(ids) <= permitidas:
        raise HTTPException(status_code=400, detail="Alguna marca no corresponde a este empleado y día.")
    # «No se usa»: solo marcas del reloj (una manual se quita) y solo si la regla del día ofrece esa opción. Deshacerlo
    # (volver a ENTRADA o SALIDA) siempre se puede.
    nuevas_sin_uso = [i for i, t in nuevos.items() if t == TIPO_NO_SE_USA and del_dia[i]["tipo"] != TIPO_NO_SE_USA]
    if nuevas_sin_uso:
        if any(del_dia[i]["manual"] for i in nuevas_sin_uso):
            raise HTTPException(status_code=400, detail="Una marca manual no se marca como «No se usa»: quítela con «Quitar».")
        from backend.repositories.reglas_marcas import ReglasMarcasRepository
        ev = await ReglasMarcasRepository(db).evaluar_dia(req.empleado_id, req.fecha)
        if not (ev.get("en_revision") and "NO_SE_USA" in ((ev.get("regla") or {}).get("opciones_efectivas") or [])):
            raise HTTPException(status_code=400, detail="La regla de este día no permite dejar una marca sin usar.")
    repo_marcas = AsistenciaRepository(db)
    for log_id, t in nuevos.items():
        await repo_marcas.quitar_correccion_de_tipo(log_id)
        if str(orig[log_id] or "").strip().lower() != t.lower():
            await repo_marcas.corregir_tipo(log_id, t, getattr(current_user, "user_id", None))
    resultado = await service.procesar_empleado_dia(req.empleado_id, req.fecha, save=True)
    # El día siguiente hereda las marcas que usó este día (turnos que cruzan la medianoche): si ya estaba calculado, se recalcula
    manana = (datetime.strptime(req.fecha, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    if (manana <= datetime.now().strftime("%Y-%m-%d") and await service.repository.get_asistencia(req.empleado_id, manana)
            and not await service.repository.check_fecha_cerrada(manana, req.empleado_id)):
        await service.procesar_empleado_dia(req.empleado_id, manana, save=True)
    logger.info(f"🕘 Marcas reclasificadas: empleado {req.empleado_id} {req.fecha} por usuario {getattr(current_user, 'username', '?')}: {nuevos}")
    return {"success": True, "mensaje": "Marcaciones clasificadas y asistencia recalculada", "asistencia": resultado}


# ── Quitar UNA marcación manual, con permiso propio y registro (2026-10-16) ───────────────────────────────────────────────────
# Las marcas del reloj no se tocan nunca. Una marca manual la puso una persona (p. ej. una Salida de turno de noche con la fecha
# equivocada) y otra con el permiso `marcaciones.eliminar_manual` puede quitarla; la copia queda en la auditoría con quién, cuándo y por qué.
_MOTIVO_MIN_LETRAS = 5


@router.delete("/marcaciones/manual/{log_id}/")
async def quitar_marcacion_manual(
    log_id: int,
    motivo: str = Query(..., description="Por qué se quita la marca; queda en la auditoría"),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.eliminar_manual"))
):
    """Quita una marcación manual (nunca una del reloj), guarda su copia en la auditoría y recalcula los días que la usaban."""
    db = service.repository.db
    motivo = (motivo or "").strip()
    if len(motivo) < _MOTIVO_MIN_LETRAS:
        raise HTTPException(status_code=400, detail=f"Indique el motivo (al menos {_MOTIVO_MIN_LETRAS} letras): queda registrado en la auditoría.")
    repo_marcas = AsistenciaRepository(db)
    marca = await repo_marcas.get_marca(log_id)
    if not marca:
        raise HTTPException(status_code=404, detail="Marcación no encontrada")
    if not marca["manual"]:
        raise HTTPException(status_code=400, detail="Solo se pueden quitar marcaciones manuales: las marcas del reloj no se modifican.")
    emp = await EmpleadoRepository(db).get_by_id(marca["empleado_id"])
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    current_user.verificar_acceso_area(emp.area, "este empleado")

    # Días que cuentan esta marca: el de su fecha y, si un turno de noche la usó como Salida, el día anterior
    dia = str(marca["fecha_hora"])[:10]
    ayer = (datetime.strptime(dia, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    calculados = await repo_marcas.get_marcas_usadas_por_dia(marca["empleado_id"], (ayer, dia))
    dias = sorted({dia} | {str(a["fecha"])[:10] for a in calculados if log_id in _ids_de_json(a["marcas_consumidas_ids"])})
    for d in dias:
        if await service.repository.check_fecha_cerrada(d, marca["empleado_id"]):
            raise HTTPException(status_code=403, detail=f"El periodo del {d[8:]}-{d[5:7]} se encuentra cerrado y no admite modificaciones.")

    from backend.repositories.seguridad import SeguridadRepository
    detalle = json.dumps({
        "marca_id": log_id, "empleado_id": marca["empleado_id"], "fecha_hora": str(marca["fecha_hora"]), "tipo": marca["tipo"],
        "observaciones": marca["observaciones"], "ingresada_por_usuario_id": marca["usuario_id"], "ingresada_el": str(marca["created_at"]),
        "motivo": motivo,
    }, ensure_ascii=False)
    async with db.transaction():  # sin copia en la auditoría no se quita nada
        await SeguridadRepository(db).log_auditoria(current_user.user_id, current_user.username, "ELIMINAR_MARCA_MANUAL", "MARCACIONES", detalle)
        await repo_marcas.quitar_correccion_de_tipo(log_id)
        await repo_marcas.borrar_marca_manual(log_id)
    logger.info(f"🗑️ Marca manual {log_id} ({marca['fecha_hora']}) de empleado {marca['empleado_id']} quitada por {current_user.username}: {motivo}")

    for d in dias:
        await service.procesar_empleado_dia(marca["empleado_id"], d, save=True)
    return {"success": True, "mensaje": "Marcación manual quitada y asistencia recalculada", "dias_recalculados": dias}


@router.delete("/marcaciones/manual/")
async def eliminar_jornada_especial_manual(
    empleado_id: int = Query(...),
    fecha: str = Query(...),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Elimina las marcaciones manuales de un día específico y recalcula la asistencia.
    """
    # RLS: Verificar pertenencia
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
         raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    current_user.verificar_acceso_area(emp.area, "este empleado")

    # Blindaje de Cierre
    if await service.repository.check_fecha_cerrada(fecha, empleado_id):
         raise HTTPException(status_code=403, detail="El periodo de esta fecha se encuentra cerrado y no admite modificaciones.")

    try:
        db = service.repository.db
        
        # Eliminar las marcaciones manuales de este día (la copia de lo que se borra queda en la auditoría, con quién y cuándo)
        fecha_like = f"{fecha} %"
        repo_marcas = AsistenciaRepository(db)
        a_borrar = await repo_marcas.get_marcas_manuales_del_dia(empleado_id, fecha_like)
        from backend.repositories.seguridad import SeguridadRepository
        async with db.transaction():
            if a_borrar:
                await SeguridadRepository(db).log_auditoria(
                    current_user.user_id, current_user.username, "ELIMINAR_MARCAS_MANUALES_DEL_DIA", "MARCACIONES",
                    json.dumps({"empleado_id": empleado_id, "fecha": fecha, "marcas": [
                        {"marca_id": m["id"], "fecha_hora": str(m["fecha_hora"]), "tipo": m["tipo"], "observaciones": m["observaciones"],
                         "ingresada_por_usuario_id": m["usuario_id"], "ingresada_el": str(m["created_at"])} for m in a_borrar]}, ensure_ascii=False))
            await repo_marcas.borrar_marcas_manuales_del_dia(empleado_id, fecha_like)
        
        # Reprocesar la asistencia del día
        resultado = await service.procesar_empleado_dia(empleado_id, fecha, save=True)
        
        return {
            "success": True,
            "mensaje": "Marcaciones manuales eliminadas y asistencia recalculada",
            "asistencia": resultado
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/marcaciones/masivas/")
async def agregar_marcaciones_masivas(
    empleado_id: int = Body(...),
    fecha_inicio: str = Body(...),
    fecha_fin: str = Body(...),
    sobrescribir: bool = Body(False),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Relleno Masivo de Asistencia (Auto-Fill) con RLS.

    [AUDITORIA 2025 — OPT N+1] Refactorizado para eliminar N+1 queries.
    Antes:  N días × ~13 queries = 1,170 round-trips para 90 días (~23 min).
    Ahora:  ~8 queries pre-carga + 1 batch insert + 1 reproceso = ~20s para 90 días.

    Estrategia:
    1. Pre-cargar asignación vigente y todos los días de turno de una vez.
    2. Pre-cargar hashes de logs_raw existentes en el rango (para modo no-sobrescribir).
    3. Construir batch de inserts en memoria, ejecutar en 1 solo round-trip.
    4. Llamar reprocesar_periodo_empleado una vez para el período completo.
    """
    # ── RLS ───────────────────────────────────────────────────────────────────
    emp_repo = EmpleadoRepository(service.repository.db)
    emp = await emp_repo.get_by_id(empleado_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")

    current_user.verificar_acceso_area(emp.area, "este empleado")

    repo = AsistenciaRepository(service.repository.db)
    turno_repo = TurnoRepository(service.repository.db)
    # ── Blindaje de Cierre ──
    areas_rows = await emp_repo.get_nombres_areas_validadas_entre(empleado_id, fecha_inicio, fecha_fin)
    emp_areas = [r['area_nombre'] for r in areas_rows]
    
    if emp.area and emp.area not in emp_areas:
        emp_areas.append(emp.area)
        
    if emp_areas:
        closed_overlap = await repo.get_cierre_que_se_cruza(emp_areas, fecha_inicio, fecha_fin)
        if closed_overlap:
            raise HTTPException(
                status_code=403, 
                detail=f"Operación denegada. El rango solicitado contiene días cerrados para el área '{closed_overlap['area']}' (Periodo cerrado: {closed_overlap['fecha_inicio']} a {closed_overlap['fecha_fin']})."
            )

    try:
        import hashlib
        start_date = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        end_date   = datetime.strptime(fecha_fin,   "%Y-%m-%d")

        # ── 1. Pre-carga: asignación de turno vigente en el período ──────────
        asigs = await turno_repo.get_asignaciones_entre(empleado_id, fecha_inicio, fecha_fin)

        if not asigs:
            return {
                "success": True,
                "mensaje": "No hay turno asignado en el período. Ningún día procesado.",
                "dias_procesados": 0, "dias_ignorados": 0, "errores": []
            }

        # ── 2. Pre-carga: detalle de días de TODOS los turnos involucrados ───
        turno_ids = list({a["turno_id"] for a in asigs})
        dias_turno_rows = await turno_repo.get_dias_de_turnos(turno_ids)
        # Mapa: turno_id → {dia_semana → config_dia}
        dias_map: Dict[int, Dict[int, Any]] = {}
        for d in dias_turno_rows:
            dias_map.setdefault(d["turno_id"], {})[d["dia_semana"]] = d

        # ── 3. Pre-carga: hashes de logs_raw existentes en el rango ──────────
        # (para verificar si ya existe una marca sin hacer 1 query por día)
        existing_hashes: set = set()
        if not sobrescribir:
            fecha_like_start = fecha_inicio[:7]   # "YYYY-MM"
            fecha_like_end   = fecha_fin[:7]
            # Cargamos todos los logs_raw del empleado en el rango de meses
            logs_existentes = await repo.get_fechas_hora_marcas_entre(empleado_id, fecha_inicio, fecha_fin)
            # Extraer solo las fechas (YYYY-MM-DD) que tienen log
            fechas_con_log: set = {row["fecha_hora"][:10] for row in logs_existentes}
        else:
            fechas_con_log = set()

        # ── 4. Detectar asignación vigente para cada día (en memoria) ─────────
        # Construir lookup: fecha → (turno_id, asig_id)
        def get_asig_para_fecha(fecha_str: str) -> Optional[Dict]:
            for a in asigs:
                desde = a["asig_desde"]
                hasta = a["asig_hasta"] or "2099-12-31"
                if desde <= fecha_str <= hasta:
                    return a
            return None

        # ── 5. Construir batch de inserts en memoria ───────────────────────────
        batch_logs: list = []
        uid_masivo = getattr(current_user, "user_id", None)  # quién hizo el relleno: queda en cada marca
        dias_procesados = 0
        dias_ignorados  = 0
        dias_futuros    = 0
        ahora_masivo    = _motor._get_now_local()
        errores: list   = []

        current = start_date
        while current <= end_date:
            fecha_str  = current.strftime("%Y-%m-%d")
            dia_semana = current.weekday()   # 0=Lunes

            asig = get_asig_para_fecha(fecha_str)
            if not asig:
                dias_ignorados += 1
                current += timedelta(days=1)
                continue

            config_dia = dias_map.get(asig["turno_id"], {}).get(dia_semana)
            if not config_dia or config_dia.get("es_libre"):
                dias_ignorados += 1
                current += timedelta(days=1)
                continue

            if not sobrescribir and fecha_str in fechas_con_log:
                dias_ignorados += 1
                current += timedelta(days=1)
                continue

            hora_entrada = config_dia.get("hora_entrada")
            hora_salida  = config_dia.get("hora_salida")
            if not hora_entrada or not hora_salida:
                dias_ignorados += 1
                current += timedelta(days=1)
                continue

            # Entrada
            fh_ent  = f"{fecha_str} {hora_entrada}:00"
            rut_str = str(emp.rut) if emp else str(empleado_id)

            # Salida: en un turno que cruza la medianoche cae el día siguiente (Entrada 23:00 del 11 · Salida 07:00 del 12)
            fecha_sal = fecha_de_la_salida(fecha_str, hora_salida, hora_entrada, bool(config_dia.get("cruza_medianoche")))
            fh_sal = f"{fecha_sal} {hora_salida}:00"

            # Una marca manual registra algo que ya pasó: un día cuya Entrada o Salida todavía no ocurre no se rellena
            if _marca_en_el_futuro(fh_ent, ahora_masivo) or _marca_en_el_futuro(fh_sal, ahora_masivo):
                dias_futuros += 1
                current += timedelta(days=1)
                continue

            h_ent   = hashlib.sha256(f"{rut_str}|{fh_ent}|Entrada".encode()).hexdigest()
            batch_logs.append((empleado_id, fh_ent, "Entrada", 1, "Relleno Masivo", h_ent, uid_masivo))
            h_sal  = hashlib.sha256(f"{rut_str}|{fh_sal}|Salida".encode()).hexdigest()
            batch_logs.append((empleado_id, fh_sal, "Salida", 1, "Relleno Masivo", h_sal, uid_masivo))

            dias_procesados += 1
            current += timedelta(days=1)

        # ── 6. Insert batch (1 round-trip para TODOS los días) ────────────────
        if batch_logs:
            await repo.insertar_marcas_relleno(batch_logs)
            logger.info(f"📥 [Relleno Masivo] {len(batch_logs)} marcas teóricas insertadas para empleado {empleado_id}")

            # ── 7. Un solo reproceso para todo el período ─────────────────────
            # Usa el motor optimizado con pre-carga de contexto (OPT3).
            await service.reprocesar_periodo_empleado(
                empleado_id=empleado_id,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                force=True
            )

        return {
            "success": True,
            "mensaje": (f"Proceso completado. Procesados: {dias_procesados}, Ignorados: {dias_ignorados}"
                        + (f", omitidos por ser futuros: {dias_futuros}" if dias_futuros else "")),
            "dias_procesados": dias_procesados,
            "dias_ignorados":  dias_ignorados,
            "dias_futuros_omitidos": dias_futuros,
            "marcas_insertadas": len(batch_logs),
            "errores": errores
        }

    except Exception as e:
        logger.error(f"Error en relleno masivo empleado {empleado_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
