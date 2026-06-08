import os
import json
import io
from typing import Dict, Optional
from loguru import logger
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.auth.exceptions import DefaultCredentialsError

from backend.core.config import settings

class GoogleDriveService:
    def __init__(self):
        self.folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID") or getattr(settings, "GOOGLE_DRIVE_FOLDER_ID", None)
        self.credentials_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        self.credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON_PATH") or getattr(settings, "GOOGLE_APPLICATION_CREDENTIALS_JSON_PATH", None)
        
        self.scopes = ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        self.credentials = None
        self._initialize_credentials()

    def _initialize_credentials(self):
        """Inicializa las credenciales de la Cuenta de Servicio usando variables de entorno o archivo local."""
        try:
            # 1. Intentar desde la variable de entorno JSON (String directo - ideal para producción)
            if self.credentials_json:
                try:
                    info = json.loads(self.credentials_json)
                    self.credentials = service_account.Credentials.from_service_account_info(
                        info, scopes=self.scopes
                    )
                    logger.info("🔑 Google Drive: Credenciales inicializadas desde GOOGLE_APPLICATION_CREDENTIALS_JSON (String)")
                    return
                except Exception as json_err:
                    logger.error(f"❌ Error al parsear GOOGLE_APPLICATION_CREDENTIALS_JSON: {json_err}")

            # 2. Intentar desde el archivo local (ideal para desarrollo local)
            if self.credentials_path and os.path.exists(self.credentials_path):
                try:
                    self.credentials = service_account.Credentials.from_service_account_file(
                        self.credentials_path, scopes=self.scopes
                    )
                    logger.info(f"🔑 Google Drive: Credenciales inicializadas desde archivo '{self.credentials_path}'")
                    return
                except Exception as file_err:
                    logger.error(f"❌ Error al cargar archivo de credenciales de Google: {file_err}")

            # 3. Fallback a credenciales por defecto de Google Cloud (ADC - útil si se asocia al container en Cloud Run)
            try:
                import google.auth
                credentials, project = google.auth.default(scopes=self.scopes)
                self.credentials = credentials
                logger.info("🔑 Google Drive: Utilizando Credenciales por Defecto de Google (ADC)")
            except DefaultCredentialsError:
                logger.warning("⚠️ Google Drive: No se encontraron credenciales de Cuenta de Servicio ni por defecto.")
        except Exception as e:
            logger.error(f"❌ Error crítico inicializando credenciales de Google Drive: {e}")

    def get_service(self):
        """Retorna una instancia activa del servicio de Google Drive API."""
        if not self.credentials:
            self._initialize_credentials()
            if not self.credentials:
                raise RuntimeError("No hay credenciales válidas configuradas para Google Drive API")
        
        return build("drive", "v3", credentials=self.credentials, cache_discovery=False)

    async def upload_photo(self, file_content: bytes, filename: str, mime_type: str = "image/jpeg") -> Optional[Dict[str, str]]:
        """
        Sube una foto a la carpeta designada en Google Drive.
        
        Retorna un diccionario con el 'id' del archivo y su 'web_view_url' si tiene éxito.
        """
        try:
            if not self.folder_id:
                logger.error("❌ Google Drive: GOOGLE_DRIVE_FOLDER_ID no está configurado.")
                return None

            service = self.get_service()

            file_metadata = {
                "name": filename,
                "parents": [self.folder_id]
            }

            # Envolver los bytes del archivo en un stream de memoria
            fh = io.BytesIO(file_content)
            media = MediaIoBaseUpload(fh, mimetype=mime_type, resumable=True)

            # Ejecutar la subida en un hilo separado para no bloquear el loop de FastAPI
            import asyncio
            def _execute_upload():
                # 1. Crear el archivo en Drive
                file = service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, webViewLink, webContentLink"
                ).execute()

                # 2. Hacer el archivo legible para cualquiera con el link (opcional, pero útil para visualizar fotos)
                try:
                    user_permission = {
                        'type': 'anyone',
                        'role': 'reader',
                    }
                    service.permissions().create(
                        fileId=file.get('id'),
                        body=user_permission
                    ).execute()
                except Exception as perm_err:
                    logger.warning(f"⚠️ No se pudo cambiar el permiso de visibilidad en Drive: {perm_err}")

                return file

            file = await asyncio.to_thread(_execute_upload)
            
            logger.info(f"📤 Google Drive: Archivo '{filename}' subido con éxito (ID: {file.get('id')})")
            
            return {
                "id": file.get("id"),
                "web_view_url": file.get("webViewLink"),
                "web_content_url": file.get("webContentLink")
            }

        except Exception as e:
            logger.error(f"❌ Google Drive: Error al subir la foto '{filename}': {e}")
            return None
