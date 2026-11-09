import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Optional
from loguru import logger
from backend.core.config import settings

class NotificationService:
    """
    Servicio para envío de notificaciones por email y otros canales.
    """
    
    def __init__(self, smtp_server: Optional[str] = None, 
                 smtp_port: int = 587, 
                 smtp_user: Optional[str] = None, 
                 smtp_password: Optional[str] = None,
                 email_from: Optional[str] = None):
        self.smtp_server = smtp_server or settings.SMTP_SERVER
        self.smtp_port = smtp_port or settings.SMTP_PORT
        self.smtp_user = smtp_user or settings.SMTP_USER
        self.smtp_password = smtp_password or settings.SMTP_PASSWORD
        self.email_from = email_from or settings.EMAIL_FROM
        self.enabled = settings.FEATURE_NOTIFICACIONES_EMAIL

    async def _send_email(self, to_emails: List[str], subject: str, html_content: str, images: List[dict] = [], attachments: List[dict] = []):
        """
        Método interno para envío de email vía SMTP con soporte para imágenes embebidas y archivos adjuntos.
        images: Lista de dicts {'cid': 'logo', 'path': 'path/to/img.jpg'}
        attachments: Lista de dicts {'filename': 'file.xlsx', 'content': bytes}
        """
        if not self.enabled or not self.smtp_server:
            logger.warning("Notificaciones de email desactivadas o SMTP no configurado.")
            return False

        try:
            # Usar 'mixed' como contenedor raíz cuando hay adjuntos
            msg = MIMEMultipart('mixed')
            msg['From'] = self.email_from
            msg['To'] = ", ".join(to_emails)
            msg['Subject'] = subject

            # Contenedor 'related' para HTML e imágenes incrustadas (inline)
            msg_related = MIMEMultipart('related')
            msg.attach(msg_related)

            # Contenedor 'alternative' para HTML y texto
            msg_alternative = MIMEMultipart('alternative')
            msg_related.attach(msg_alternative)

            # Adjuntar HTML
            msg_alternative.attach(MIMEText(html_content, 'html'))

            # Adjuntar Imágenes (CID)
            from email.mime.image import MIMEImage
            import os

            for img_data in images:
                cid = img_data['cid']
                path = img_data['path']
                
                if os.path.exists(path):
                    with open(path, 'rb') as f:
                        img = MIMEImage(f.read())
                        img.add_header('Content-ID', f'<{cid}>')
                        img.add_header('Content-Disposition', 'inline', filename=os.path.basename(path))
                        msg_related.attach(img)
                else:
                    logger.warning(f"Imagen no encontrada para email: {path}")

            # Adjuntar Archivos
            from email.mime.application import MIMEApplication
            for att_data in attachments:
                filename = att_data['filename']
                content = att_data['content']
                part = MIMEApplication(content, _subtype="pdf" if filename.lower().endswith(".pdf") else "octet-stream", Name=filename)
                part['Content-Disposition'] = f'attachment; filename="{filename}"'
                msg.attach(part)

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.success(f"Email enviado a {to_emails}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Error enviando email: {e}")
            return False

    # ── Correos con la plantilla «Banda azul» (correo_plantilla.py, decisión del dueño 09-11-2026) ──────────────
    _CONTRATO = {
        'RENOVAR': ('Contrato renovado', 'ok', 'Se renovó el contrato de {n}', [
            'Preparar el nuevo contrato o el anexo de prórroga.', 'Actualizar la carpeta personal.', 'Avisar a la jefatura directa.']),
        'NO_RENOVAR': ('Término de contrato', 'rojo', 'Termina el contrato de {n}', [
            'Enviar la carta de aviso dentro del plazo legal.', 'Preparar el finiquito y las vacaciones proporcionales.',
            'Coordinar la devolución de EPP, llaves y herramientas.', 'Cerrar los accesos el último día.']),
        'DESACTIVAR': ('Término de contrato', 'rojo', 'Termina el contrato de {n}', [
            'Enviar la carta de aviso dentro del plazo legal.', 'Preparar el finiquito y las vacaciones proporcionales.',
            'Coordinar la devolución de EPP, llaves y herramientas.', 'Cerrar los accesos el último día.']),
        'INDEFINIDO': ('Contrato indefinido', 'navy', '{n} pasa a contrato indefinido', [
            'Firmar el anexo de contrato indefinido.', 'Revisar los beneficios que cambian con el contrato indefinido.']),
        'BAJA_MANUAL': ('Baja', 'gris', 'Baja de {n}', [
            'Recibir la carta de renuncia o emitir la carta de despido.', 'Calcular el finiquito y los haberes pendientes.',
            'Pedir la devolución de activos y credenciales.']),
    }

    async def send_contract_decision_email(self, employee_data: dict, decision_type: str,
                                          details: str, recipients: List[str]):
        """Avisa a RR.HH. una decisión de contrato (renovar, término, indefinido o baja)."""
        from backend.services import correo_plantilla as cp
        tipo = (decision_type or '').upper()
        etiqueta, tono, titulo_f, pasos = self._CONTRATO.get(
            tipo, ('Decisión de contrato', 'navy', 'Decisión de contrato de {n}', ['Revisar la ficha de la persona.']))
        nombre = employee_data.get('nombre_completo') or ''
        if tipo == 'BAJA_MANUAL' and 'por:' in (details or ''):
            motivo = details.split('por:', 1)[1].strip().rstrip('.')
            if motivo:
                etiqueta = motivo[:1].upper() + motivo[1:]
        filas = [('Decisión', etiqueta)]
        if employee_data.get('cant_contratos'):
            filas.append(('Contrato', f"N° {employee_data['cant_contratos']}"))
        fs = employee_data.get('fecha_salida_fmt')
        if fs and fs != 'No definida':
            filas.append(('Fecha de término', cp.fecha(fs)))
        fi = employee_data.get('fecha_ingreso_fmt')
        if fi and fi != 'No registrada':
            ant = employee_data.get('antiguedad')
            filas.append(('Ingreso', cp.fecha(fi) + (f' · {ant}' if ant and ant != 'No calculada' else '')))
        if details:
            filas.append(('Detalle', details))
        filas.append(('Fecha del aviso', datetime.now().strftime('%d-%m-%Y')))
        detalle_p = ' · '.join(x for x in (str(employee_data.get('cargo') or '').title(), str(employee_data.get('area') or '').title()) if x)
        cuerpo = (cp.persona(nombre, employee_data.get('rut_formateado') or '', detalle_p) + '<div style="height:14px"></div>'
                  + cp.filas(filas, '42%') + cp.pasos(pasos, tono) + cp.boton('Ver la ficha en Asistencia'))
        intro = details or 'Se registró una decisión de contrato en Asistencia.'
        html = cp.correo(etiqueta, tono, titulo_f.format(n=nombre.title()), intro, cuerpo)
        area = str(employee_data.get('area') or '').title()
        subject = ' · '.join(x for x in (etiqueta, nombre, area) if x)
        return await self._send_email(recipients, subject, html, cp.imagenes())

    async def send_justification_email(self, employee_data: dict, type_name: str,
                                     start_date: str, end_date: str, recipients: List[str],
                                     observations: str = None, days_count: int = 1):
        """Avisa a RR.HH. una justificación registrada (vacaciones, licencia, permiso, etc.)."""
        from backend.services import correo_plantilla as cp
        nombre = employee_data.get('nombre_completo') or ''
        desde, hasta = cp.fecha(start_date), cp.fecha(end_date)
        rango = desde if desde == hasta else f'del {desde} al {hasta}'
        filas = [('Tipo', type_name), ('Desde', desde), ('Hasta', hasta), ('Días', str(days_count))]
        if observations:
            filas.append(('Observación', observations))
        detalle_p = ' · '.join(x for x in (str(employee_data.get('cargo') or '').title(), str(employee_data.get('area') or '').title()) if x)
        cuerpo = (cp.persona(nombre, employee_data.get('rut_formateado') or '', detalle_p) + '<div style="height:14px"></div>'
                  + cp.filas(filas, '42%') + cp.boton('Ver en Asistencia'))
        html = cp.correo('Justificación registrada', 'navy', f'{type_name} de {nombre.title()}',
                         'Se registró una justificación en Asistencia. Los días ya aparecen en la grilla con su código.', cuerpo,
                         previa=f'{type_name} de {nombre}: {days_count} {"día" if days_count == 1 else "días"}, {rango}.')
        subject = f'Justificación registrada · {nombre} · {type_name} {rango}'
        return await self._send_email(recipients, subject, html, cp.imagenes())

    async def send_cierre_email(self,
                                  area: str,
                                  fecha_inicio: str,
                                  fecha_fin: str,
                                  user_name: str,
                                  tipo_cierre: str,
                                  resumen: dict,
                                  adjuntos: List[dict],
                                  recipients: List[str],
                                  resumen_tipos: Optional[List[dict]] = None):
        """Avisa a RR.HH. el cierre de un área: balance de horas por tipo de horario y lo que se carga; los PDF del
        informe van adjuntos (el Excel con el detalle día a día se descarga desde la app)."""
        from backend.services import correo_plantilla as cp
        meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        try:
            ff = datetime.strptime(fecha_fin, '%Y-%m-%d')
            mes = f'{meses[ff.month - 1].capitalize()} {ff.year}'
        except Exception:
            mes = 'el período'
        area_t = (area or 'Todas').title()
        nombres = [a['filename'] for a in (adjuntos or [])]
        tipos = resumen_tipos or []
        personas = sum(int(t.get('personas') or 0) for t in tipos) or (resumen or {}).get('total_empleados', '')
        datos = [('Área', area_t), ('Tramo', f'{cp.fecha(fecha_inicio)} al {cp.fecha(fecha_fin)}'), ('Cerró', user_name),
                 ('Fecha del cierre', datetime.now().strftime('%d-%m-%Y %H:%M')), ('Personas', str(personas))]
        cuerpo = cp.filas(datos, '42%', tam=13) + ''.join(cp.bloque_resumen(t) for t in tipos)
        cuerpo += '<div style="height:16px"></div>' + cp.adjuntos_html(nombres)
        son_pdf = bool(nombres) and all(n.lower().endswith('.pdf') for n in nombres)
        if son_pdf:
            nota = 'El Excel con el detalle día a día se descarga desde Asistencia. Horas en HH:MM:SS.'
        elif nombres:
            nota = 'No se pudo generar el informe en PDF: va el Excel del cierre.'
        else:
            nota = 'No se pudo adjuntar el informe; descárguelo desde Asistencia.'
        cuerpo += f'<p style="margin:8px 0 0;font:400 13px {cp.FONT};color:{cp.INK2}">{cp.e(nota)}</p>' + cp.boton('Abrir Tramos de cierre')
        titulos = ' y '.join(t['titulo'] for t in tipos)
        previa = f'Se cerró {mes} ({cp.fecha(fecha_inicio)} al {cp.fecha(fecha_fin)}) para {area_t}.'
        if son_pdf and titulos:
            previa += f' Van {len(nombres)} PDF: {titulos}.'
        html = cp.correo('Cierre de período', 'navy', f'Se cerró {mes} de {area_t}',
                         'El período quedó cerrado y ya no admite cambios. Este es el balance de horas de cada tipo de horario y lo que se '
                         'carga en remuneraciones; el detalle por persona va en los PDF adjuntos.', cuerpo, previa=previa)
        subject = f'Cierre de {mes} · {area_t} · informe adjunto'
        return await self._send_email(recipients, subject, html, cp.imagenes(), list(adjuntos or []))
