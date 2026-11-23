"""
Router - Asistencia: libreta del Art. 25 bis (Marcación dinámica 180 horas): ver, guardar, borrar, reasignar el turno del
acompañante, inasistencia, purgar marcas del reloj y lectura de la foto (OCR). Separado de routers/asistencia.py en la
etapa 6 de la auditoría, con el mismo código; las direcciones siguen bajo /api/asistencia (asistencia.py incluye este router).
"""
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from loguru import logger
from pydantic import BaseModel

from backend.core.security import RequirePermission, SecurityContext
from backend.repositories.empleado import EmpleadoRepository
from backend.repositories.seguridad import SeguridadRepository
from backend.routers.asistencia_comun import get_asistencia_service
from backend.schemas.asistencia import Libreta180hRequest
from backend.services import libreta_orden
from backend.services import quantum_matrix_engine as _motor  # su reloj (_get_now_local) es el único: las pruebas lo fijan en un solo lugar
from backend.services.asistencia_service import AsistenciaService
from backend.services.gemini_vision_service import gemini_vision_service
from backend.services.quantum_matrix_engine import MARCA_INASISTENCIA_LIBRETA, QuantumMatrixEngine, libreta_es_inasistencia

router = APIRouter()


# ═════════════════════════════════════════════════════════════════════
# MARCACIÓN DINÁMICA 180 HORAS (ART. 25 BIS DT)
# ═════════════════════════════════════════════════════════════════════

# Por qué no se puede ingresar un día de libreta directamente (guardar, validar, inasistencia, reasignar). Orden del dueño, 04-11-2026.
_BLOQUEO_STATUS = {"PERIODO_CERRADO": 403, "FECHA_FUTURA": 400, "SIN_LIBRETA": 400, "PENDIENTE_ANTERIOR": 409}
# Quien lo tenga en su rol puede editar un día de libreta ya validado (se asigna en Configuración → Seguridad → Roles)
PERMISO_EDITAR_LIBRETA_VALIDADA = "marcaciones.editar_libreta_validada"


async def _libreta_bloqueo(service: AsistenciaService, empleado_id: int, fecha: str, con_orden: bool = True) -> Optional[Dict[str, Any]]:
    """None si el día se puede ingresar; si no, el motivo y el texto: período cerrado, día futuro, persona sin libreta ese día (resguardo
    del servidor: la pantalla solo abre la libreta a horarios de libreta) o, con `con_orden` (crear un día nuevo), días anteriores del
    tramo todavía pendientes (la libreta se llena en orden)."""
    repo = service.repository
    if await repo.check_rango_cerrado(fecha, fecha, empleado_id):
        return {"motivo": "PERIODO_CERRADO", "mensaje": "La fecha se encuentra en un período cerrado."}
    if str(fecha)[:10] > _motor._get_now_local().date().isoformat():
        return {"motivo": "FECHA_FUTURA", "mensaje": "No se puede ingresar la libreta de un día que todavía no llega."}
    asignacion = await repo.get_asignacion_vigente(empleado_id, fecha)
    if not QuantumMatrixEngine.resolve_control_modality(asignacion or {}, fecha):
        return {"motivo": "SIN_LIBRETA", "mensaje": "Este empleado no se controla con libreta 180h ese día."}
    pendientes = await libreta_orden.pendientes_anteriores(service, empleado_id, fecha) if con_orden else []
    if pendientes:
        return {"motivo": "PENDIENTE_ANTERIOR", "mensaje": libreta_orden.mensaje_pendiente(pendientes), "pendientes": pendientes}
    return None


async def _exigir_libreta_ingresable(service: AsistenciaService, empleado_id: int, fecha: str, con_orden: bool = True) -> None:
    b = await _libreta_bloqueo(service, empleado_id, fecha, con_orden)
    if b:
        raise HTTPException(status_code=_BLOQUEO_STATUS[b["motivo"]], detail=b["mensaje"])


async def _enlazados_libreta(service: AsistenciaService, empleado_id: int, fecha: str, row: Optional[Dict[str, Any]],
                             chofer_id: Optional[int]) -> List[Dict[str, Any]]:
    """Quienes andan enlazados con esta persona ese día, para la pregunta «¿A quién más le aplico este cambio?»: sus acompañantes si es
    chofer; el chofer y los otros acompañantes si es peoneta. Con si su día está validado o es distinto al de esta persona."""
    repo = service.repository
    if chofer_id is not None:
        ids = [(chofer_id, 'chofer')] + [(a, 'acompañante') for a in await repo.get_acompanantes_180h(chofer_id, fecha) if a != empleado_id]
    else:
        ids = [(a, 'acompañante') for a in await repo.get_acompanantes_180h(empleado_id, fecha)]
    nombres = await _nombres_personas(repo.db, [i for i, _ in ids])
    res = []
    for i, rol in ids:
        lib = await repo.get_libreta_180h(i, fecha)
        res.append({"empleado_id": i, "nombre": nombres.get(i, ""), "rol": rol, "tiene_libreta": bool(lib),
                    "validado": bool(lib) and int(lib.get('cerrado') or 0) == 1,
                    "distinto": bool(lib) and bool(row) and not libreta_orden.mismos_tramos(lib, row)})
    return res


async def _nombres_personas(db, ids: List[int]) -> Dict[int, str]:
    if not ids:
        return {}
    filas = await EmpleadoRepository(db).get_nombres_por_ids(ids)
    return {int(f["id"]): libreta_orden.nombre_persona(dict(f)) for f in filas}


@router.get("/libreta-180h/")
async def get_libreta_180h(
    empleado_id: int = Query(...),
    fecha: str = Query(...),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Obtiene la libreta Art. 25 bis del día (96 slots de 15 minutos y desglose de horas).
    """
    try:
        from pathlib import Path
        foto_path = Path("downloads") / "libretas_180h" / f"{empleado_id}_{fecha}.jpg"
        tiene_foto = foto_path.is_file()
        foto_url = f"/api/asistencia/libreta-180h/foto/?empleado_id={empleado_id}&fecha={fecha}" if tiene_foto else None

        row = await service.repository.get_libreta_180h(empleado_id, fecha)
        chofer_id = await service.repository.get_chofer_de_acompanante_180h(empleado_id, fecha)
        validado = bool(row) and int(row.get('cerrado') or 0) == 1
        puede_validado = current_user.check_permission(PERMISO_EDITAR_LIBRETA_VALIDADA)
        # Si el día no se puede ingresar directamente la ventana lo dice al abrirse. El orden solo cuenta para crear un día nuevo propio (la
        # copia del chofer al peoneta nunca se frena); un día validado sin el permiso es de solo lectura y no hace falta revisarlo.
        bloqueo = None if (validado and not puede_validado) else await _libreta_bloqueo(
            service, empleado_id, fecha, con_orden=(not row and chofer_id is None))
        camion = {k: (row or {}).get(k) for k in ("patente", "vehiculo_id", "patente_origen")}
        # «Cosas por revisar» (05-11-2026): límites de Configuración y cómo terminó el día anterior. Si falla, la libreta se abre igual.
        from backend.services.libreta_revision import contexto_revision
        try:
            revision = await contexto_revision(service.repository.db, service.repository, empleado_id, fecha)
        except Exception as e_rev:
            logger.warning(f"[Libreta] sin contexto de revisión (emp={empleado_id}, fecha={fecha}): {e_rev}")
            revision = None
        extra = {"bloqueo": bloqueo, "puede_editar_validado": puede_validado,
                 "enlazados": await _enlazados_libreta(service, empleado_id, fecha, row, chofer_id), **camion, "revision": revision}
        if not row:
            return {
                "has_data": False,
                "empleado_id": empleado_id,
                "fecha": fecha,
                "slots_96": [0] * 96,
                "minutos_conduccion": 0,
                "minutos_espera": 0,
                "minutos_auxiliares": 0,
                "minutos_descanso": 0,
                "minutos_efectivos": 0,
                "horas_efectivas": 0.0,
                "horas_espera": 0.0,
                "horas_descanso": 0.0,
                "cerrado": 0,
                "observaciones": "",
                "acompanantes": await service.repository.get_acompanantes_180h(empleado_id, fecha),
                "acompanantes_ocupados": list((await service.repository.get_acompanantes_ocupados_180h(fecha, empleado_id)).keys()),
                "chofer_id": chofer_id,
                "tiene_foto": tiene_foto,
                "foto_url": foto_url,
                **extra
            }

        raw_s = row.get('slots_96', '[]')
        slots = json.loads(raw_s) if isinstance(raw_s, str) else (raw_s or [0] * 96)
        if len(slots) < 96:
            slots.extend([0] * (96 - len(slots)))

        min_cond = int(row.get('minutos_conduccion') or 0)
        min_esp = int(row.get('minutos_espera') or 0)
        min_aux = int(row.get('minutos_auxiliares') or 0)
        min_desc = int(row.get('minutos_descanso') or 0)
        min_efec = int(row.get('minutos_efectivos') or (min_cond + min_aux))

        return {
            "id": row.get('id'),
            "has_data": True,
            "empleado_id": empleado_id,
            "fecha": fecha,
            "slots_96": slots,
            "minutos_conduccion": min_cond,
            "minutos_espera": min_esp,
            "minutos_auxiliares": min_aux,
            "minutos_descanso": min_desc,
            "minutos_efectivos": min_efec,
            "horas_efectivas": round(min_efec / 60.0, 2),
            "horas_espera": round(min_esp / 60.0, 2),
            "horas_descanso": round(min_desc / 60.0, 2),
            "cerrado": row.get('cerrado', 0),
            "observaciones": row.get('observaciones') or "",
            "acompanantes": await service.repository.get_acompanantes_180h(empleado_id, fecha),
                "acompanantes_ocupados": list((await service.repository.get_acompanantes_ocupados_180h(fecha, empleado_id)).keys()),
            "chofer_id": chofer_id,
            "tiene_foto": tiene_foto,
            "foto_url": foto_url,
            **extra
        }
    except Exception as e:
        logger.exception(f"❌ Error en get_libreta_180h (emp={empleado_id}, fecha={fecha}): {e}")
        raise HTTPException(status_code=500, detail=f"Error obteniendo Libreta 180h: {str(e)}")


@router.get("/libreta-180h/foto/")
async def get_libreta_foto(
    empleado_id: int = Query(...),
    fecha: str = Query(...),
    token: Optional[str] = Query(None, description="Token JWT para previsualización directa en navegador"),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Retorna la fotografía física escaneada de la libreta para auditoría visual.
    """
    from pathlib import Path
    from fastapi.responses import FileResponse
    foto_path = Path("downloads") / "libretas_180h" / f"{empleado_id}_{fecha}.jpg"
    if not foto_path.is_file():
        raise HTTPException(status_code=404, detail="No existe fotografía de respaldo archivada para este día.")
    return FileResponse(str(foto_path), media_type="image/jpeg")


@router.post("/libreta-180h/")
async def save_libreta_180h(
    payload: Libreta180hRequest,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Guarda la libreta diaria de 96 slots, persiste cómputos y sincroniza en asistencias.

    Reglas (orden del dueño, 04-11-2026):
    - Un día NUEVO solo se crea si los días anteriores del tramo ya tienen libreta (la libreta se llena en orden). Editar un día que ya
      tiene libreta no se frena por el orden.
    - Un día validado solo lo cambia quien tiene el permiso «Editar libreta validada» (se asigna en Seguridad → Roles); sigue validado y
      la edición queda en la auditoría con las horas de antes y de después.
    - Chofer → acompañantes: la copia es automática mientras el día del chofer no está validado y el del acompañante sigue igual al del
      chofer (o no existe). Si el chofer edita un día validado, o el acompañante tiene su día validado, ajustado aparte o propio, no se pisa:
      solo se copia a quienes vengan en `replicar_a` (la pantalla lo pregunta). Sacar a un acompañante de la lista borra su copia (si no
      está validada). La copia nunca se frena por el orden: si al acompañante le queda un día anterior pendiente, se avisa.
    - Peoneta enlazado a un chofer: su cambio nunca pasa solo al chofer; solo a quienes vengan en `replicar_a` (el chofer o los otros
      acompañantes de ese día). Al chofer no se le cambia su patente.
    """
    try:
        repo = service.repository
        existente = await repo.get_libreta_180h(payload.empleado_id, payload.fecha)
        validado = bool(existente) and int(existente.get('cerrado') or 0) == 1
        puede_validado = current_user.check_permission(PERMISO_EDITAR_LIBRETA_VALIDADA)
        if validado and not puede_validado:
            raise HTTPException(status_code=409, detail="El día está validado: solo un usuario con el permiso «Editar libreta validada» puede cambiarlo. Sin ese permiso, para corregirlo hay que eliminar el registro del día.")

        # Período cerrado, día futuro o persona sin libreta ese día; y si el día es nuevo, los días anteriores del tramo deben tener libreta
        await _exigir_libreta_ingresable(service, payload.empleado_id, payload.fecha, con_orden=not existente)

        # Un día nuevo no se abre mientras la persona tenga OTRO día en borrador (anterior o posterior): primero se valida (o se borra) ese.
        # Editar un día que ya existe no se frena (es el propio borrador).
        if not existente:
            otro = await _otro_borrador(repo, payload.empleado_id, payload.fecha)
            if otro:
                raise HTTPException(status_code=409, detail=f"Primero valida el borrador del {otro[8:10]}-{otro[5:7]}-{otro[:4]}: no se puede guardar otro día de esta persona hasta entonces.")

        # La primera vez que se guarda un día siempre queda en borrador: solo se valida (se cierra) sobre un borrador ya guardado. Un día ya
        # validado sigue validado al editarlo.
        cerrar_dia = validado or (bool(payload.cerrado) and bool(existente))
        forzado_borrador = bool(payload.cerrado) and not existente

        chofer_id = await repo.get_chofer_de_acompanante_180h(payload.empleado_id, payload.fecha)

        # Camión del día: se guarda si viene; para validar el día de quien maneja hace falta la patente o «No anduvo en camión»
        camion = (libreta_orden.normalizar_patente(payload.patente, payload.vehiculo_id, payload.patente_origen)
                  if (payload.patente or payload.patente_origen) else None)
        # (solo al validar: editar un día que ya estaba validado no pide un dato que no existía cuando se validó)
        if cerrar_dia and not validado and not libreta_es_inasistencia(existente) and chofer_id is None:
            vigente = camion or {k: (existente or {}).get(k) for k in ("patente", "patente_origen")}
            if not (vigente.get('patente') or vigente.get('patente_origen') == 'SIN_CAMION'):
                raise HTTPException(status_code=409, detail="Para validar el día falta la patente del camión: elígela o marca «No anduvo en camión».")

        slots = list(payload.slots_96)
        if len(slots) < 96:
            slots.extend([0] * (96 - len(slots)))
        elif len(slots) > 96:
            slots = slots[:96]

        slots_cond = sum(1 for s in slots if s == 1)
        slots_esp = sum(1 for s in slots if s == 2)
        slots_aux = sum(1 for s in slots if s == 3)
        slots_desc = sum(1 for s in slots if s == 4)

        min_cond = slots_cond * 15
        min_esp = slots_esp * 15
        min_aux = slots_aux * 15
        min_desc = slots_desc * 15
        min_efec = min_cond + min_aux

        val_id = getattr(current_user, 'user_id', None) or getattr(current_user, 'id', None)

        data = {
            'empleado_id': payload.empleado_id,
            'fecha': payload.fecha,
            'slots_96': slots,
            'minutos_conduccion': min_cond,
            'minutos_espera': min_esp,
            'minutos_auxiliares': min_aux,
            'minutos_descanso': min_desc,
            'minutos_efectivos': min_efec,
            'cerrado': 1 if cerrar_dia else 0,
            'validador_id': val_id,
            'observaciones': payload.observaciones or ""
        }
        if camion is not None:
            data.update(camion)

        acomp_ids = [a for a in dict.fromkeys(payload.acompanantes or []) if a != payload.empleado_id]
        if payload.acompanantes is not None:
            ocupados = await repo.get_acompanantes_ocupados_180h(payload.fecha, payload.empleado_id)
            choque = [a for a in acomp_ids if a in ocupados]
            if choque:
                raise HTTPException(status_code=409, detail="Uno o más acompañantes ya están asignados a otro chofer ese día. Reabre la libreta para actualizar la lista.")

        enlazados_antes = await repo.get_acompanantes_180h(payload.empleado_id, payload.fecha) if payload.acompanantes is not None else []
        await repo.upsert_libreta_180h(data)

        replicar = {int(x) for x in (payload.replicar_a or [])}
        no_copiados, sacados, replicados, acomp_pendientes, acomp_omitidos = [], [], [], [], []
        fecha_de: Dict[int, str] = {}  # destino -> fecha del día pendiente o del otro borrador que impidió la copia

        async def copiar(destino: int, base: Dict[str, Any], sin_patente: bool = False) -> Optional[str]:
            """Copia `base` al día de `destino`; devuelve el motivo si no se pudo (validado sin permiso o período cerrado)."""
            ex_d = await repo.get_libreta_180h(destino, payload.fecha)
            destino_validado = bool(ex_d) and int(ex_d.get('cerrado') or 0) == 1
            if destino_validado and not puede_validado:
                return 'VALIDADO'
            if await repo.check_rango_cerrado(payload.fecha, payload.fecha, destino):
                return 'PERIODO_CERRADO'
            # La copia abre un día nuevo en el destino, y un día nuevo cumple las mismas reglas que al guardarlo a mano: la libreta se llena en
            # orden (ningún día anterior del tramo pendiente) y un solo borrador a la vez.
            if not ex_d:
                previos_d = await libreta_orden.pendientes_anteriores(service, destino, payload.fecha)
                if previos_d:
                    fecha_de[destino] = previos_d[0]
                    return 'PENDIENTE_ANTERIOR'
                if not (base.get('cerrado') or destino_validado):
                    otro_d = await _otro_borrador(repo, destino, payload.fecha)
                    if otro_d:
                        fecha_de[destino] = otro_d
                        return 'BORRADOR_PENDIENTE'
            copia = {**base, 'empleado_id': destino, 'cerrado': 1 if (base.get('cerrado') or destino_validado) else 0}
            if sin_patente:
                for k in ('patente', 'vehiculo_id', 'patente_origen'):
                    copia.pop(k, None)
            elif 'patente_origen' in base:
                copia['patente_origen'] = 'SIN_CAMION' if base['patente_origen'] == 'SIN_CAMION' else ('CHOFER' if base.get('patente') else None)
            await repo.upsert_libreta_180h(copia)
            await service.procesar_empleado_dia(destino, payload.fecha, save=True, force=True)
            return None

        # Chofer → acompañantes
        if payload.acompanantes is not None:
            await repo.set_acompanantes_180h(payload.empleado_id, payload.fecha, acomp_ids)
            # Quien salió de la lista pierde la copia que tenía ese día (si no está validada): su día vuelve a quedar pendiente
            for aid in [a for a in enlazados_antes if a not in acomp_ids]:
                lib = await repo.get_libreta_180h(aid, payload.fecha)
                if not lib:
                    continue
                if int(lib.get('cerrado') or 0) == 1 or await repo.check_rango_cerrado(payload.fecha, payload.fecha, aid):
                    sacados.append({"empleado_id": aid, "borrado": False})
                    continue
                await repo.delete_libreta_180h(aid, payload.fecha)
                await service.procesar_empleado_dia(aid, payload.fecha, save=True, force=True)
                sacados.append({"empleado_id": aid, "borrado": True})
            for aid in acomp_ids:
                ex_a = await repo.get_libreta_180h(aid, payload.fecha)
                igual_al_chofer = (not ex_a) or (existente is not None and libreta_orden.mismos_tramos(ex_a, existente)) \
                    or libreta_orden.mismos_tramos(ex_a, data)
                a_validado = bool(ex_a) and int(ex_a.get('cerrado') or 0) == 1
                automatico = not validado and not a_validado and igual_al_chofer
                if not automatico and aid not in replicar:
                    motivo = 'EDICION_VALIDADA' if validado else ('VALIDADO' if a_validado else 'AJUSTADO')
                    no_copiados.append({"empleado_id": aid, "motivo": motivo})
                    continue
                motivo = await copiar(aid, data)
                if motivo:
                    acomp_omitidos.append(aid)
                    no_copiados.append({"empleado_id": aid, "motivo": motivo})
                    continue
                replicados.append(aid)
                previos = await libreta_orden.pendientes_anteriores(service, aid, payload.fecha)
                if previos:
                    acomp_pendientes.append({"empleado_id": aid, "fecha_pendiente": previos[0], "pendientes": len(previos),
                                             "chofer_id": await repo.get_chofer_de_acompanante_180h(aid, previos[0])})

        # Peoneta enlazado → chofer y otros acompañantes de ese día: solo si se eligió en la pregunta
        if chofer_id is not None and replicar:
            otros = [chofer_id] + [a for a in await repo.get_acompanantes_180h(chofer_id, payload.fecha) if a != payload.empleado_id]
            for did in otros:
                if did not in replicar:
                    continue
                motivo = await copiar(did, data, sin_patente=(did == chofer_id))
                if motivo:
                    no_copiados.append({"empleado_id": did, "motivo": motivo})
                else:
                    replicados.append(did)

        # Nombres y textos de los avisos
        ids_nombres = ([a["empleado_id"] for a in acomp_pendientes] + [a["chofer_id"] for a in acomp_pendientes if a["chofer_id"] is not None]
                       + [n["empleado_id"] for n in no_copiados] + [s["empleado_id"] for s in sacados])
        nombres = await _nombres_personas(repo.db, list(dict.fromkeys(ids_nombres)))
        for a in acomp_pendientes:
            a["nombre"] = nombres.get(a["empleado_id"], "")
            a["chofer_nombre"] = nombres.get(a["chofer_id"], "") if a["chofer_id"] is not None else ""
            con = f" (con {a['chofer_nombre']})" if a["chofer_nombre"] else ""
            a["mensaje"] = f"Se copió el día a {a['nombre']}. Le queda pendiente el {libreta_orden.fecha_legible(a['fecha_pendiente'])}{con}."
        textos_motivo = {
            'EDICION_VALIDADA': "no se le copió el cambio (el día del chofer está validado y no se eligió copiarlo)",
            'VALIDADO': "no se le copió: su día está validado",
            'AJUSTADO': "no se le copió: su día tiene horas propias o ajustadas aparte",
            'PERIODO_CERRADO': "no se le copió: su período está cerrado",
        }
        for n in no_copiados:
            n["nombre"] = nombres.get(n["empleado_id"], "")
            if n["motivo"] == 'PENDIENTE_ANTERIOR':
                n["mensaje"] = (f"A {n['nombre']} no se le copió: antes tiene pendiente el {libreta_orden.fecha_legible(fecha_de.get(n['empleado_id'], ''))} "
                                f"(la libreta se llena en orden). Complétalo y luego usa «Reasignar turno» en este día.")
            elif n["motivo"] == 'BORRADOR_PENDIENTE':
                n["mensaje"] = (f"A {n['nombre']} no se le copió: tiene sin validar el borrador del {libreta_orden.fecha_legible(fecha_de.get(n['empleado_id'], ''))}. "
                                f"Valídalo o bórralo y luego usa «Reasignar turno» en este día.")
            else:
                n["mensaje"] = f"A {n['nombre']} {textos_motivo.get(n['motivo'], 'no se le copió')}."
        for s in sacados:
            s["nombre"] = nombres.get(s["empleado_id"], "")
            s["mensaje"] = (f"{s['nombre']} salió de la lista: se borró la copia de este día y vuelve a quedar pendiente." if s["borrado"] else
                            f"{s['nombre']} salió de la lista, pero su día está validado o en un período cerrado: no se borró; hay que borrarlo a mano.")

        # Un día validado que se edita queda en la auditoría con las horas de antes y de después
        if validado:
            try:
                antes = {k: int(existente.get(k) or 0) for k in ('minutos_conduccion', 'minutos_espera', 'minutos_auxiliares', 'minutos_descanso', 'minutos_efectivos')}
                despues = {k: int(data[k]) for k in antes}
                await SeguridadRepository(repo.db).log_auditoria(
                    current_user.user_id, current_user.username, 'EDITAR_LIBRETA_VALIDADA', 'Marcaciones',
                    json.dumps({"empleado_id": payload.empleado_id, "fecha": payload.fecha, "antes": antes, "despues": despues,
                                "replicado_a": replicados}, ensure_ascii=False))
            except Exception as aud_err:
                logger.warning(f"No se pudo registrar la auditoría de la libreta validada editada: {aud_err}")

        # Guardar fotografía de respaldo físico si viene adjunta
        if payload.imagen_base64:
            try:
                import base64
                from pathlib import Path
                b64 = payload.imagen_base64
                if "," in b64:
                    _, b64 = b64.split(",", 1)
                img_data = base64.b64decode(b64)
                libretas_dir = Path("downloads") / "libretas_180h"
                libretas_dir.mkdir(parents=True, exist_ok=True)
                foto_file = libretas_dir / f"{payload.empleado_id}_{payload.fecha}.jpg"
                foto_file.write_bytes(img_data)
                logger.info(f"📸 Foto de respaldo guardada en servidor: {foto_file}")
            except Exception as img_save_err:
                logger.warning(f"⚠️ No se pudo guardar foto de respaldo en disco: {img_save_err}")

        # Proyección atómica al motor de asistencia
        res_dia = await service.procesar_empleado_dia(payload.empleado_id, payload.fecha, save=True, force=True)

        if validado:
            mensaje = "Cambio guardado: el día sigue validado y quedó registrado."
        elif forzado_borrador:
            mensaje = "Borrador guardado: queda abierto hasta que lo valides."
        else:
            mensaje = "Libreta Art. 25 bis guardada exitosamente."
        return {
            "status": "success",
            "message": mensaje,
            "data": {
                "empleado_id": payload.empleado_id,
                "fecha": payload.fecha,
                "minutos_conduccion": min_cond,
                "minutos_espera": min_esp,
                "minutos_auxiliares": min_aux,
                "minutos_descanso": min_desc,
                "minutos_efectivos": min_efec,
                "horas_efectivas": round(min_efec / 60.0, 2),
                "horas_espera": round(min_esp / 60.0, 2),
                "horas_descanso": round(min_desc / 60.0, 2),
                "total_horas_dia": round((min_efec + min_esp + min_desc) / 60.0, 2),
                "cerrado": data['cerrado'],
                "forzado_borrador": forzado_borrador,
                "editado_validado": validado,
                "acompanantes_omitidos": acomp_omitidos,
                "acompanantes_con_pendientes": acomp_pendientes,
                "no_copiados": no_copiados,
                "sacados": sacados,
                "replicados": replicados,
                "resultado_asistencia": res_dia
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Error en save_libreta_180h (emp={payload.empleado_id}, fecha={payload.fecha}): {e}")
        raise HTTPException(status_code=500, detail=f"Error guardando Libreta 180h: {str(e)}")



async def _otro_borrador(repo, empleado_id: int, fecha: str) -> Optional[str]:
    """Fecha (AAAA-MM-DD) de OTRO día de la persona que sigue en borrador, anterior o posterior, o None. Una persona tiene un solo borrador a la vez:
    antes de abrir otro día (por guardado, por copia del chofer o del peoneta, o por «reasignar turno») hay que validar o borrar ese.
    Las inasistencias marcadas no cuentan como borrador."""
    otros = [b for b in await repo.get_libreta_borradores_180h(empleado_id, fecha) if not libreta_es_inasistencia(b)]
    return str(otros[0]['fecha'])[:10] if otros else None


class Libreta180hReasignarRequest(BaseModel):
    empleado_id: int
    fecha: str


@router.post("/libreta-180h/reasignar-turno/")
async def reasignar_turno_acompanante_180h(
    payload: Libreta180hReasignarRequest,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Peoneta (acompañante) enlazado a un chofer ese día: vuelve a copiarle el horario del chofer,
    por ejemplo cuando se le eliminó su registro. Es la misma copia que hace el guardado de la libreta del chofer.
    """
    try:
        repo = service.repository
        chofer_id = await repo.get_chofer_de_acompanante_180h(payload.empleado_id, payload.fecha)
        if chofer_id is None:
            raise HTTPException(status_code=404, detail="Este empleado no está enlazado como acompañante de ningún chofer ese día.")
        lib_chofer = await repo.get_libreta_180h(chofer_id, payload.fecha)
        if not lib_chofer:
            raise HTTPException(status_code=409, detail="El chofer no tiene horario registrado ese día: no hay turno que asignar.")
        propio = await repo.get_libreta_180h(payload.empleado_id, payload.fecha)
        propio_validado = bool(propio) and int(propio.get('cerrado') or 0) == 1
        if propio_validado and not current_user.check_permission(PERMISO_EDITAR_LIBRETA_VALIDADA):
            raise HTTPException(status_code=409, detail="El día del acompañante está validado: solo un usuario con el permiso «Editar libreta validada» puede reasignarle el turno.")
        # Si el día del acompañante ya existe se está corrigiendo; si es nuevo, vale el orden del tramo (como al guardar a mano)
        await _exigir_libreta_ingresable(service, payload.empleado_id, payload.fecha, con_orden=not propio)
        # La copia abre un borrador: un solo borrador por persona
        if not propio and not int(lib_chofer.get('cerrado') or 0):
            otro = await _otro_borrador(repo, payload.empleado_id, payload.fecha)
            if otro:
                raise HTTPException(status_code=409, detail=f"Primero valida el borrador del {otro[8:10]}-{otro[5:7]}-{otro[:4]}: no se puede abrir otro día de esta persona hasta entonces.")

        copia = {**lib_chofer, 'empleado_id': payload.empleado_id, 'cerrado': 1 if (int(lib_chofer.get('cerrado') or 0) or propio_validado) else 0}
        if lib_chofer.get('patente'):
            copia['patente_origen'] = 'CHOFER'
        await repo.upsert_libreta_180h(copia)
        res_dia = await service.procesar_empleado_dia(payload.empleado_id, payload.fecha, save=True, force=True)

        try:
            val_id = getattr(current_user, 'user_id', None) or getattr(current_user, 'id', None)
            val_user = getattr(current_user, 'username', 'sistema')
            await SeguridadRepository(repo.db).log_auditoria(
                val_id, val_user, 'REASIGNAR_TURNO_ACOMPANANTE_180H', 'Marcaciones',
                f"Turno del chofer {chofer_id} reasignado al acompañante {payload.empleado_id} en fecha {payload.fecha}")
        except Exception:
            pass

        return {"status": "success", "message": "Turno del chofer reasignado al acompañante.", "chofer_id": chofer_id, "resultado_asistencia": res_dia}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Error en reasignar_turno_acompanante_180h (emp={payload.empleado_id}, fecha={payload.fecha}): {e}")
        raise HTTPException(status_code=500, detail=f"Error reasignando turno: {str(e)}")


class Libreta180hInasistenciaRequest(BaseModel):
    empleado_id: int
    fecha: str
    observaciones: Optional[str] = None


@router.post("/libreta-180h/inasistencia/")
async def marcar_inasistencia_libreta_180h(
    payload: Libreta180hInasistenciaRequest,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Registra la INASISTENCIA de un día de un empleado que se controla con libreta 180h (bolsa de horas): guarda una libreta vacía con la marca
    de inasistencia y recalcula el día, que queda como INA en Marcaciones. Se deshace con "Borrar registro del día" (DELETE) o guardando la libreta con tramos.
    """
    try:
        repo = service.repository
        # Período cerrado, día futuro, persona sin libreta o días anteriores pendientes (la inasistencia también completa el día)
        await _exigir_libreta_ingresable(service, payload.empleado_id, payload.fecha)
        existente = await repo.get_libreta_180h(payload.empleado_id, payload.fecha)
        if existente:
            if int(existente.get('cerrado') or 0) == 1:
                raise HTTPException(status_code=409, detail="El día está cerrado: la libreta es de solo lectura.")
            if int(existente.get('minutos_efectivos') or 0) > 0 or int(existente.get('minutos_espera') or 0) > 0 or int(existente.get('minutos_descanso') or 0) > 0:
                raise HTTPException(status_code=409, detail="El día ya tiene tramos registrados: bórralos antes de marcar la inasistencia.")

        val_id = getattr(current_user, 'user_id', None) or getattr(current_user, 'id', None)
        nota = (payload.observaciones or '').strip()[:200]
        await repo.upsert_libreta_180h({
            'empleado_id': payload.empleado_id, 'fecha': payload.fecha, 'slots_96': [0] * 96,
            'minutos_conduccion': 0, 'minutos_espera': 0, 'minutos_auxiliares': 0, 'minutos_descanso': 0, 'minutos_efectivos': 0,
            'cerrado': 0, 'validador_id': val_id, 'observaciones': f"{MARCA_INASISTENCIA_LIBRETA} {nota}".strip(),
        })
        res_dia = await service.procesar_empleado_dia(payload.empleado_id, payload.fecha, save=True, force=True)
        estado = (res_dia or {}).get('estado') if isinstance(res_dia, dict) else None
        try:
            await SeguridadRepository(repo.db).log_auditoria(
                current_user.user_id, current_user.username, 'MARCAR_INASISTENCIA_LIBRETA', 'Marcaciones',
                f"Inasistencia del {payload.fecha} registrada desde la libreta 180h (empleado {payload.empleado_id}); día resultante: {estado}")
        except Exception as aud_err:
            logger.warning(f"No se pudo registrar auditoría de la inasistencia de libreta: {aud_err}")
        logger.warning(f"🚫 Inasistencia registrada desde libreta 180h por {current_user.username}: emp={payload.empleado_id} fecha={payload.fecha} -> {estado}")
        return {"status": "success", "message": "Inasistencia registrada en Marcaciones.", "estado": estado}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Error en marcar_inasistencia_libreta_180h (emp={payload.empleado_id}, fecha={payload.fecha}): {e}")
        raise HTTPException(status_code=500, detail=f"Error registrando la inasistencia: {str(e)}")


@router.delete("/libreta-180h/")
async def delete_libreta_180h(
    empleado_id: int = Query(...),
    fecha: str = Query(...),
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Elimina el registro de la libreta Art. 25 bis para un empleado y fecha.
    Elimina la fotografía archivada en el servidor y recalcula la asistencia
    del día devolviéndolo a su estado natural (LIBRE o PENDIENTE).
    """
    try:
        if await service.repository.check_rango_cerrado(fecha, fecha, empleado_id):
            raise HTTPException(status_code=403, detail="La fecha se encuentra en un período cerrado.")
        deleted = await service.repository.delete_libreta_180h(empleado_id, fecha)
        await service.repository.set_acompanantes_180h(empleado_id, fecha, [])
        if not deleted:
            logger.warning(f"⚠️ No se encontró registro de libreta para emp={empleado_id}, fecha={fecha}")

        # Eliminar archivo de foto en disco si existe
        try:
            from pathlib import Path
            libretas_dir = Path("downloads") / "libretas_180h"
            foto_file = libretas_dir / f"{empleado_id}_{fecha}.jpg"
            if foto_file.exists():
                foto_file.unlink(missing_ok=True)
                logger.info(f"🗑️ Fotografía física de libreta eliminada: {foto_file}")
        except Exception as photo_del_err:
            logger.warning(f"⚠️ Error eliminando foto física en disco: {photo_del_err}")

        # Recalcular asistencia para volver al estado natural (LIBRE o PENDIENTE)
        res_dia = await service.procesar_empleado_dia(empleado_id, fecha, save=True, force=True)

        try:
            val_id = getattr(current_user, 'user_id', None) or getattr(current_user, 'id', None)
            val_user = getattr(current_user, 'username', 'sistema')
            await SeguridadRepository(service.repository.db).log_auditoria(
                val_id, val_user, 'DELETE_LIBRETA_180H', 'Marcaciones',
                f"Eliminado registro de Libreta 180h de empleado {empleado_id} en fecha {fecha}")
        except Exception:
            pass

        # Si después hay días con libreta, este vuelve a quedar pendiente y frena los días nuevos de la persona hasta llenarlo otra vez
        posteriores = await libreta_orden.libretas_posteriores(service, empleado_id, fecha)
        aviso = (" Este día vuelve a quedar pendiente: los días nuevos de esta persona no se podrán ingresar hasta volver a llenarlo."
                 if posteriores else "")
        return {
            "status": "success",
            "message": f"Registro de libreta del {fecha} eliminado correctamente.{aviso}",
            "dias_posteriores_con_libreta": posteriores,
            "resultado_asistencia": res_dia
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Error en delete_libreta_180h (emp={empleado_id}, fecha={fecha}): {e}")
        raise HTTPException(status_code=500, detail=f"Error eliminando registro de Libreta 180h: {str(e)}")


class PurgaMarcasRelojRequest(BaseModel):
    fecha_desde: Optional[str] = None   # None = desde la fecha «Sin reloj a partir de» de cada horario


@router.post("/libreta-180h/purgar-marcas-reloj/")
async def purgar_marcas_reloj_libreta_180h(
    payload: Optional[PurgaMarcasRelojRequest] = None,
    service: AsistenciaService = Depends(get_asistencia_service),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Purga todas las marcas biométricas del reloj físico (logs_raw donde manual=0 o NULL)
    para empleados con turnos en modalidad 'LIBRETA_180H', en los días que su horario controla con libreta.
    Recalcula la asistencia para todos los días afectados garantizando que días sin libreta digital
    permanezcan estrictamente como PENDIENTE sin marcas de reloj.
    """
    try:
        f_desde = (payload.fecha_desde if payload and payload.fecha_desde else None)
        resultado = await service.purgar_y_recalcular_libreta_180h(fecha_desde=f_desde)

        try:
            val_id = getattr(current_user, 'user_id', None) or getattr(current_user, 'id', None)
            val_user = getattr(current_user, 'username', 'sistema')
            await SeguridadRepository(service.repository.db).log_auditoria(
                val_id, val_user, 'PURGA_MARCAS_RELOJ_LIBRETA_180H', 'Marcaciones',
                f"Purga de marcas de reloj para turnos Libreta 180h desde {f_desde}: {resultado.get('marcas_purgadas')} marcas eliminadas, {resultado.get('dias_recalculados')} días recalculados.")
        except Exception:
            pass

        return resultado
    except Exception as e:
        logger.error(f"❌ Error en purgar_marcas_reloj_libreta_180h: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error purgando marcas de reloj: {str(e)}")





# ═══════════════════════════════════════════════════════════════════
# ESCANEO INTELIGENTE LIBRETA 180H CON GOOGLE GEMINI VISION (AI)
# ═══════════════════════════════════════════════════════════════════

class LibretaOcrBase64Payload(BaseModel):
    imagen_base64: Optional[str] = None
    image_base64: Optional[str] = None
    mime_type: Optional[str] = "image/jpeg"
    empleado_id: Optional[int] = None
    fecha: Optional[str] = None


@router.get("/libreta-180h/ocr-status/")
async def get_ocr_status(
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.ver"))
):
    """
    Indica si el servicio de reconocimiento visual de Gemini está activo y configurado.
    """
    configured = gemini_vision_service.is_configured()
    return {
        "disponible": configured,
        "modelo": gemini_vision_service.model,
        "mensaje": "Servicio Gemini Vision listo para escaneo" if configured else "GEMINI_API_KEY no configurada en .env"
    }


@router.post("/libreta-180h/ocr-gemini/")
async def ocr_libreta_180h_upload(
    file: UploadFile = File(...),
    empleado_id: Optional[int] = Form(None),
    fecha: Optional[str] = Form(None),
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Escanea y reconoce visualmente la libreta física de chofer (Art. 25 bis DT)
    mediante Google Gemini Vision a partir de una foto subida por multipart/form-data.
    """
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="El archivo de imagen enviado está vacío.")

        mime_type = file.content_type or "image/jpeg"
        resultado = await gemini_vision_service.parse_libreta_180h_image(
            image_bytes=content,
            mime_type=mime_type,
            fecha_esperada=fecha
        )
        return resultado
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Error en ocr_libreta_180h_upload: {e}")
        raise HTTPException(status_code=500, detail=f"Error procesando imagen de libreta con Gemini Vision: {str(e)}")


@router.post("/libreta-180h/ocr-gemini-base64/")
async def ocr_libreta_180h_base64(
    payload: LibretaOcrBase64Payload,
    current_user: SecurityContext = Depends(RequirePermission("marcaciones.editar"))
):
    """
    Escanea la libreta física de chofer a partir de una cadena Base64 capturada directamente por la cámara web/móvil.
    """
    try:
        raw_b64 = payload.imagen_base64 or payload.image_base64
        if not raw_b64:
            raise HTTPException(status_code=400, detail="Se requiere la imagen en Base64 (imagen_base64 o image_base64).")

        if "," in raw_b64:
            header, raw_b64 = raw_b64.split(",", 1)
            if "png" in header:
                mime_type = "image/png"
            elif "webp" in header:
                mime_type = "image/webp"
            else:
                mime_type = "image/jpeg"
        else:
            mime_type = payload.mime_type or "image/jpeg"

        import base64
        try:
            image_bytes = base64.b64decode(raw_b64)
        except Exception as b64_err:
            raise HTTPException(status_code=400, detail=f"Base64 inválido: {b64_err}")

        # Archivar foto en servidor si viene empleado y fecha
        foto_url = None
        if payload.empleado_id and payload.fecha:
            try:
                from pathlib import Path
                libretas_dir = Path("downloads") / "libretas_180h"
                libretas_dir.mkdir(parents=True, exist_ok=True)
                foto_file = libretas_dir / f"{payload.empleado_id}_{payload.fecha}.jpg"
                foto_file.write_bytes(image_bytes)
                foto_url = f"/api/asistencia/libreta-180h/foto/?empleado_id={payload.empleado_id}&fecha={payload.fecha}"
                logger.info(f"📸 Foto de libreta archivada en: {foto_file}")
            except Exception as auto_save_err:
                logger.warning(f"⚠️ Error archivando foto preventivamente: {auto_save_err}")

        resultado = await gemini_vision_service.parse_libreta_180h_image(
            image_bytes=image_bytes,
            mime_type=mime_type,
            fecha_esperada=payload.fecha
        )
        if isinstance(resultado, dict):
            resultado["tiene_foto"] = bool(foto_url)
            resultado["foto_url"] = foto_url
        return resultado
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Error en ocr_libreta_180h_base64: {e}")
        raise HTTPException(status_code=500, detail=f"Error procesando imagen base64 con Gemini Vision: {str(e)}")
