import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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

    async def _send_email(self, to_emails: List[str], subject: str, html_content: str, images: List[dict] = []):
        """
        Método interno para envío de email vía SMTP con soporte para imágenes embebidas.
        images: Lista de dicts {'cid': 'logo', 'path': 'path/to/img.jpg'}
        """
        if not self.enabled or not self.smtp_server:
            logger.warning("Notificaciones de email desactivadas o SMTP no configurado.")
            return False

        try:
            # Usar 'related' para permitir imágenes embebidas
            msg = MIMEMultipart('related')
            msg['From'] = self.email_from
            msg['To'] = ", ".join(to_emails)
            msg['Subject'] = subject

            # Parte alternativa para HTML y Texto
            msg_alternative = MIMEMultipart('alternative')
            msg.attach(msg_alternative)

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
                        msg.attach(img)
                else:
                    logger.warning(f"Imagen no encontrada para email: {path}")

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

    def _get_logo_html(self):
        """Retorna el HTML del logo embebido o fallback"""
        return """
        <img src="cid:logo_aguacol" alt="Aguacol SPA" style="height: 50px; display: block;" width="180">
        """

    async def send_contract_decision_email(self, employee_data: dict, decision_type: str, 
                                          details: str, recipients: List[str]):
        """Notificar a RRHH sobre una decisión de contrato con diseño Corporativo Aguacol Prime"""
        
        # Mapeo de términos... (se mantiene igual)
        action_map = {
            "RENOVAR": {
                "label": "Extensión de Vínculo Laboral (Renovación)",
                "color": "#10b981", # Emerald
                "icon": "📝",
                "checklist": [
                    "Preparar nuevo contrato o anexo de prórroga.",
                    "Actualizar registros en carpeta personal del empleado.",
                    "Notificar a jefatura directa sobre la continuidad."
                ]
            },
            "NO_RENOVAR": {
                "label": "Término de Contrato Programado (No Renovación)",
                "color": "#ef4444", # Red
                "icon": "⚠️",
                "checklist": [
                    "Emitir y enviar carta certificada de aviso (30 días o plazo legal).",
                    "Preparar cálculo de finiquito y vacaciones proporcionales.",
                    "Coordinar devolución de activos (EPP, llaves, herramientas).",
                    "Cerrar accesos informáticos el último día de funciones."
                ]
            },
            "INDEFINIDO": {
                "label": "Pase a Planta (Contrato Indefinido)",
                "color": "#8b5cf6", # Violet
                "icon": "⭐",
                "checklist": [
                    "Firmar anexo de contrato indefinido.",
                    "Evaluar ajustes de beneficios corporativos por planta.",
                    "Felicitar formalmente al colaborador por su estabilidad."
                ]
            },
            "DESACTIVAR": {
                "label": "Término de Contrato Programado (No Renovación)",
                "color": "#ef4444", 
                "icon": "⚠️",
                "checklist": [
                    "Emitir y enviar carta certificada de aviso (30 días o plazo legal).",
                    "Preparar cálculo de finiquito y vacaciones proporcionales.",
                    "Coordinar devolución de activos (EPP, llaves, herramientas).",
                    "Cerrar accesos informáticos el último día de funciones."
                ]
            },
            "BAJA_MANUAL": {
                "label": "Baja de Empleado (Renuncia / Desvinculación)",
                "color": "#ef4444",
                "icon": "🚪",
                "checklist": [
                    "Recepcionar carta de renuncia o emitir carta de despido.",
                    "Calcular finiquito y haberes pendientes.",
                    "Coordinar entrevista de salida (si aplica).",
                    "Solicitar devolución de activos y credenciales."
                ]
            }
        }

        # Fallback si el tipo no está mapeado
        info = action_map.get(decision_type.upper(), {
            "label": decision_type.upper(),
            "color": "#3b82f6",
            "icon": "ℹ️",
            "checklist": ["Revisar ficha del empleado para determinar pasos a seguir."]
        })

        # OVERRIDE LABEL FOR BAJA_MANUAL IF DETAILS CONTAINS MOTIVE
        # El usuario quiere que el título sea el motivo específico (ej: Renuncia Voluntaria)
        if decision_type.upper() == "BAJA_MANUAL" and "por:" in details:
            try:
                # details formato: "El empleado ha sido dado de baja por: Renuncia Voluntaria."
                motive_part = details.split("por:")[1].strip().rstrip(".")
                if motive_part:
                    info['label'] = motive_part.title() # "Renuncia Voluntaria"
            except:
                pass

        subject = f"{info['icon']} {info['label']}: {employee_data.get('nombre_completo')}"
        
        # Cálculo de fechas para la línea de tiempo
        from datetime import date
        today_fmt = date.today().strftime("%d/%m/%Y")
        fecha_salida_fmt = employee_data.get('fecha_salida_fmt', 'No definida')
        
        # Generar HTML del checklist
        checklist_html = "".join([f'<li style="margin-bottom: 8px;">{item}</li>' for item in info['checklist']])

        # Datos enriquecidos
        entry_date = employee_data.get('fecha_ingreso_fmt', 'No registrada')
        tenure = employee_data.get('antiguedad', 'No calculada')

        html = f"""
        <html>
            <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: 'Segoe UI', Arial, sans-serif;">
                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; padding: 20px 0;">
                    <tr>
                        <td align="center">
                            <table width="650" border="0" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.08);">
                                <!-- Header Corporativo Aguacol -->
                                <tr>
                                    <td align="left" style="background-color: #1e293b; padding: 30px 40px; border-bottom: 4px solid #3b82f6;">
                                        <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                            <tr>
                                                <td align="left">
                                                    {self._get_logo_html()}
                                                </td>
                                                <td align="right" valign="bottom">
                                                    <div style="color: #64748b; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px;">
                                                        Notificación RRHH
                                                    </div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                
                                <!-- Banner de Acción -->
                                <tr>
                                    <td style="padding: 35px 40px 10px 40px;">
                                        <div style="display: inline-block; padding: 6px 14px; border-radius: 8px; background-color: {info['color']}15; color: {info['color']}; font-size: 13px; font-weight: 700; margin-bottom: 15px;">
                                            CONFIRMACIÓN DE GESTIÓN
                                        </div>
                                        <h1 style="color: #0f172a; margin: 0; font-size: 24px; font-weight: 700; line-height: 1.2;">
                                            {info['label']}
                                        </h1>
                                    </td>
                                </tr>

                                <!-- Tarjeta de Identidad del Empleado (ID Card) -->
                                <tr>
                                    <td style="padding: 20px 40px;">
                                        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 25px;">
                                            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                                <tr>
                                                    <td width="70" valign="top">
                                                        <div style="width: 55px; height: 55px; background-color: #314d9b; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 22px; font-weight: bold; text-align: center; line-height: 55px;">
                                                            {employee_data.get('nombre')[0] if employee_data.get('nombre') else 'E'}
                                                        </div>
                                                    </td>
                                                    <td>
                                                        <div style="color: #0f172a; font-size: 18px; font-weight: 700;">{employee_data.get('nombre_completo')}</div>
                                                        <div style="color: #64748b; font-size: 14px;">RUT: {employee_data.get('rut_formateado')}</div>
                                                        <div style="margin-top: 8px;">
                                                            <span style="background-color: #e2e8f0; color: #475569; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">{employee_data.get('cargo') or 'Cargo no definido'}</span>
                                                            <span style="background-color: #e2e8f0; color: #475569; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; margin-left: 5px;">{employee_data.get('area') or 'Área no definida'}</span>
                                                        </div>
                                                    </td>
                                                </tr>
                                            </table>
                                            
                                            <!-- Datos de Antigüedad -->
                                            <div style="margin-top: 15px; padding-top: 15px; border-top: 1px dashed #cbd5e1; font-size: 13px; color: #475569; display: flex; gap: 20px;">
                                                <div><strong>Fecha Ingreso:</strong> {entry_date}</div>
                                                <div><strong>Antigüedad:</strong> {tenure}</div>
                                            </div>
                                        </div>
                                    </td>
                                </tr>

                                <!-- Detalles y Timeline -->
                                <tr>
                                    <td style="padding: 10px 40px 30px 40px;">
                                        <h3 style="color: #334155; font-size: 15px; font-weight: 700; margin-bottom: 12px;">RESUMEN DE LA ACCIÓN</h3>
                                        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="font-size: 14px; border-collapse: separate; border-spacing: 0 10px;">
                                            <tr>
                                                <td width="180" style="color: #64748b;">Efectividad de Decisión:</td>
                                                <td style="color: #1e293b; font-weight: 600;">{today_fmt}</td>
                                            </tr>
                                            <tr>
                                                <td style="color: #64748b;">Fecha Término Contrato:</td>
                                                <td style="color: #1e293b; font-weight: 600;">{fecha_salida_fmt}</td>
                                            </tr>
                                            <tr>
                                                <td style="color: #64748b;">Correlativo Contrato:</td>
                                                <td style="color: #1e293b; font-weight: 600;">Contrato N° {employee_data.get('cant_contratos', 1)}</td>
                                            </tr>
                                            <tr>
                                                <td valign="top" style="color: #64748b;">Comentario/Motivo:</td>
                                                <td style="color: #1e293b; font-style: italic; background-color: #fffbeb; padding: 10px; border-left: 3px solid #fde047; border-radius: 4px;">"{details}"</td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>

                                <!-- Checklist para RRHH -->
                                <tr>
                                    <td style="padding: 0 40px 40px 40px;">
                                        <div style="background-color: {info['color']}05; border: 1px dashed {info['color']}; border-radius: 12px; padding: 25px;">
                                            <h3 style="color: {info['color']}; font-size: 15px; font-weight: 700; margin: 0 0 15px 0;">📋 PRÓXIMOS PASOS (GESTIÓN RRHH)</h3>
                                            <ul style="color: #475569; font-size: 13px; margin: 0; padding-left: 20px; line-height: 1.5;">
                                                {checklist_html}
                                            </ul>
                                        </div>
                                    </td>
                                </tr>

                                <!-- Footer Corporativo -->
                                <tr>
                                    <td style="background-color: #f8fafc; padding: 30px 40px; text-align: center; border-top: 1px solid #e2e8f0;">
                                        <p style="color: #94a3b8; margin: 0; font-size: 13px; line-height: 1.5;">
                                            Este es un documento electrónico generado automáticamente por el Sistema de Asistencia Aguacol.<br>
                                            <strong>© 2026 Aguacol SPA | Departamento de Recursos Humanos</strong>
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
        </html>
        """
        
        # Path al logo
        import os
        logo_path = os.path.join(settings.BASE_DIR, "frontend", "assets", "img", "logo.jpg")
        
        images = []
        if os.path.exists(logo_path):
            images.append({'cid': 'logo_aguacol', 'path': logo_path})
            
        return await self._send_email(recipients, subject, html, images)

    async def send_justification_email(self, employee_data: dict, type_name: str, 
                                     start_date: str, end_date: str, recipients: List[str],
                                     observations: str = None, days_count: int = 1):
        """Notificar a RRHH sobre una nueva justificación con diseño Corporativo Aguacol Prime"""
        subject = f"📅 Justificación: {employee_data.get('nombre_completo')} ({type_name})"
        
        obs_html = ""
        if observations:
            obs_html = f"""
            <tr>
                <td valign="top" style="color: #64748b;">Observaciones:</td>
                <td style="color: #1e293b; font-style: italic; background-color: #fffbeb; padding: 10px; border-left: 3px solid #fde047; border-radius: 4px;">"{observations}"</td>
            </tr>
            """
            
        html = f"""
        <html>
            <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: 'Segoe UI', Arial, sans-serif;">
                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; padding: 20px 0;">
                    <tr>
                        <td align="center">
                            <table width="650" border="0" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.08);">
                                <!-- Header Corporativo Aguacol -->
                                <tr>
                                    <td align="left" style="background-color: #059669; padding: 25px 40px; border-bottom: 5px solid #10b981;">
                                        <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                            <tr>
                                                <td>
                                                    {self._get_logo_html()}
                                                </td>
                                                <td align="right">
                                                    <div style="background-color: rgba(255,255,255,0.1); padding: 5px 15px; border-radius: 20px; color: #ffffff; font-size: 11px; text-transform: uppercase; font-weight: 600;">
                                                        Control de Asistencia
                                                    </div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                
                                <!-- Banner de Acción -->
                                <tr>
                                    <td style="padding: 35px 40px 10px 40px;">
                                        <div style="display: inline-block; padding: 6px 14px; border-radius: 8px; background-color: #f0fdf4; color: #059669; font-size: 13px; font-weight: 700; margin-bottom: 15px;">
                                            NUEVA JUSTIFICACIÓN REGISTRADA
                                        </div>
                                        <h1 style="color: #0f172a; margin: 0; font-size: 24px; font-weight: 700; line-height: 1.2;">
                                            {type_name}
                                        </h1>
                                    </td>
                                </tr>

                                <!-- Tarjeta de Identidad del Empleado -->
                                <tr>
                                    <td style="padding: 20px 40px;">
                                        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 25px;">
                                            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                                <tr>
                                                    <td width="70" valign="top">
                                                        <div style="width: 55px; height: 55px; background-color: #059669; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 22px; font-weight: bold; text-align: center; line-height: 55px;">
                                                            {employee_data.get('nombre')[0] if employee_data.get('nombre') else 'E'}
                                                        </div>
                                                    </td>
                                                    <td>
                                                        <div style="color: #0f172a; font-size: 18px; font-weight: 700;">{employee_data.get('nombre_completo')}</div>
                                                        <div style="color: #64748b; font-size: 14px;">RUT: {employee_data.get('rut_formateado')}</div>
                                                        <div style="margin-top: 8px;">
                                                            <span style="background-color: #e2e8f0; color: #475569; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">{employee_data.get('cargo') or 'Cargo no definido'}</span>
                                                            <span style="background-color: #e2e8f0; color: #475569; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; margin-left: 5px;">{employee_data.get('area') or 'Área no definida'}</span>
                                                        </div>
                                                    </td>
                                                </tr>
                                            </table>
                                        </div>
                                    </td>
                                </tr>

                                <!-- Detalles del Periodo -->
                                <tr>
                                    <td style="padding: 10px 40px 40px 40px;">
                                        <h3 style="color: #334155; font-size: 15px; font-weight: 700; margin-bottom: 12px;">DETALLES DEL PERIODO</h3>
                                        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="font-size: 14px; border-collapse: separate; border-spacing: 0 10px;">
                                            <tr>
                                                <td width="180" style="color: #64748b;">Fecha Inicio:</td>
                                                <td style="color: #1e293b; font-weight: 600;">{start_date}</td>
                                            </tr>
                                            <tr>
                                                <td style="color: #64748b;">Fecha Término:</td>
                                                <td style="color: #1e293b; font-weight: 600;">{end_date}</td>
                                            </tr>
                                            <tr>
                                                <td style="color: #64748b;">Días Solicitados:</td>
                                                <td style="color: #1e293b; font-weight: 600;">{days_count} día(s)</td>
                                            </tr>
                                            {obs_html}
                                        </table>
                                    </td>
                                </tr>

                                <!-- Footer Corporativo -->
                                <tr>
                                    <td style="background-color: #f8fafc; padding: 30px 40px; text-align: center; border-top: 1px solid #e2e8f0;">
                                        <p style="color: #94a3b8; margin: 0; font-size: 13px; line-height: 1.5;">
                                            Este es un documento electrónico generado automáticamente por el Sistema de Asistencia Aguacol.<br>
                                            <strong>© 2026 Aguacol SPA | Departamento de Recursos Humanos</strong>
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
        </html>
        """
        
        # Path al logo
        import os
        logo_path = os.path.join(settings.BASE_DIR, "frontend", "assets", "img", "logo.jpg")
        
        images = []
        if os.path.exists(logo_path):
            images.append({'cid': 'logo_aguacol', 'path': logo_path})

        return await self._send_email(recipients, subject, html, images)
