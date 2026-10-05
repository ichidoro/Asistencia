import os
import json
import base64
import re
from typing import Dict, Any, List, Optional
from loguru import logger
import aiohttp

from backend.core.config import settings


class GeminiVisionService:
    """
    Servicio de reconocimiento visual inteligente para Libretas de Control de Jornada
    de Choferes (Art. 25 bis DT / Res. Ex. 1213) utilizando Google Gemini Vision.
    Aprovecha la cuota gratuita (Free Tier) de Google AI Studio (hasta 1.500 solicitudes/día gratis).
    """

    def __init__(self):
        # Intentar obtener la API Key desde settings, os.environ o fallback
        self.api_key = (
            getattr(settings, "GEMINI_API_KEY", None)
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or ""
        )
        self.model = getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")

    def is_configured(self) -> bool:
        """Verifica si la API Key de Gemini está configurada."""
        return bool(self.api_key and len(self.api_key.strip()) > 10)

    async def parse_libreta_180h_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        fecha_esperada: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analiza una imagen/fotografía de la libreta física de chofer (Art. 25 bis DT)
        y extrae los 96 slots diarios de 15 minutos en sus 4 actividades.
        
        Actividades según Res. Ex. 1213 DT:
          1 = Conducción
          2 = Tiempo de Espera
          3 = Labores Auxiliares
          4 = Descanso
          0 = Sin marcar / Vacío
        """
        if not self.is_configured():
            logger.warning("GeminiVisionService: No se ha configurado GEMINI_API_KEY. Configura la clave en .env.")
            return {
                "exito": False,
                "error": "GEMINI_API_KEY_MISSING",
                "mensaje": (
                    "No se ha configurado la API Key de Google Gemini. "
                    "Por favor agrega tu clave gratuita de Google AI Studio en el archivo .env como GEMINI_API_KEY=tu_clave"
                ),
                "slots_96": [0] * 96,
                "tramos": []
            }

        prompt = f"""Eres un perito experto en lectura visual de planillas oficiales de asistencia laboral según la Resolución Exenta N° 1213 de la Dirección del Trabajo de Chile (Art. 25 bis del Código del Trabajo para choferes de carga/transporte).

La imagen adjunta es una FOTOGRAFÍA de una hoja física de registro de jornada de un conductor.
La hoja contiene una cuadrícula de 24 horas continuas (00:00 a 24:00) dividida en tramos de 15 minutos (96 slots diarios en total: :00, :15, :30, :45), organizada en 4 filas principales:
1. CONDUCCIÓN (fila 1): Tiempo que el chofer pasa al volante manejando.
2. ESPERA (fila 2): Tiempos de espera para carga, descarga o instrucción, sin conducir.
3. LABORES AUXILIARES (fila 3): Mantenimiento del camión, revisión mecánica, estiba, papeleo.
4. DESCANSO (fila 4): Descanso diario, pausas de colación, horas sin prestar servicios.

{f"FECHA ESPERADA DE LA JORNADA: {fecha_esperada}" if fecha_esperada else ""}

INSTRUCCIONES DE LECTURA VISUAL:
1. Orienta mentalmente la foto si está inclinada, con sombras o tomada con celular.
2. Observa con máxima atención las marcas manuscritas (líneas continuas trazadas a lápiz, rayas horizontales, cruces o bloques sombreados) en cada una de las 4 filas.
3. Identifica a qué horas corresponden esas marcas en la regla de 24 horas (desde las 00:00 hasta las 24:00).
4. Para CADA UNO de los 96 tramos de 15 minutos del día (índice 0 = 00:00-00:15, índice 1 = 00:15-00:30, ..., índice 95 = 23:45-24:00), asigna el código numérico:
   - 1: Conducción
   - 2: Espera
   - 3: Labores Auxiliares
   - 4: Descanso
   - 0: Sin marcar (si el tramo está totalmente en blanco)
5. Si un tramo no tiene ninguna marca manuscrita pero claramente el chofer estaba descansando (por ejemplo de madrugada 00:00 a 06:00), identifícalo o márcalo como 4 (Descanso) o déjalo en 0 si está vacío.
6. Extrae los tramos continuos resumidos (ej. Conducción de 08:00 a 13:15).

RESPONDE OBLIGATORIAMENTE EN FORMATO JSON ESTRICTO CON ESTE ESQUEMA EXACTO:
{{
  "exito": true,
  "fecha_detectada": "YYYY-MM-DD o null si no se ve la fecha escrita",
  "conductor_detectado": "Nombre del chofer si está escrito o null",
  "confianza": 0.95,
  "tramos": [
    {{"inicio": "08:00", "fin": "13:15", "actividad": "CONDUCCION"}},
    {{"inicio": "13:15", "fin": "14:30", "actividad": "DESCANSO"}},
    {{"inicio": "14:30", "fin": "18:00", "actividad": "ESPERA"}}
  ],
  "slots_96": [4, 4, 4, ..., 1, 1, 1, 2, 2, ...],
  "resumen_horas": {{
    "minutos_conduccion": 315,
    "minutos_espera": 210,
    "minutos_auxiliares": 0,
    "minutos_descanso": 915
  }},
  "observaciones": "Comentarios breves sobre la calidad de la foto o tramos dudosos"
}}"""

        # Codificar imagen a Base64
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")

        # Construir payload para Gemini API
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": img_b64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "max_output_tokens": 4096
            }
        }

        # Intentar llamada directa a la API de Google Gemini (v1beta)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        
        try:
            logger.info(f"📸 GeminiVisionService: Procesando imagen de Libreta 180h con {self.model} ({len(image_bytes)/1024:.1f} KB)...")
            
            timeout = aiohttp.ClientTimeout(total=45)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"❌ Error en respuesta Gemini API ({resp.status}): {err_text}")
                        
                        # Fallback a gemini-1.5-flash si 2.0 no está disponible
                        if self.model != "gemini-1.5-flash":
                            logger.info("Intentando fallback a gemini-1.5-flash...")
                            url_fallback = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
                            async with session.post(url_fallback, json=payload) as resp_fb:
                                if resp_fb.status == 200:
                                    resp_data = await resp_fb.json()
                                    return self._process_gemini_response(resp_data)
                                else:
                                    fb_err = await resp_fb.text()
                                    logger.error(f"❌ Fallback Gemini también falló: {fb_err}")
                        
                        return {
                            "exito": False,
                            "error": f"API_ERROR_{resp.status}",
                            "mensaje": f"Google Gemini API respondió con error ({resp.status}): {err_text[:200]}",
                            "slots_96": [0] * 96,
                            "tramos": []
                        }
                    
                    resp_data = await resp.json()
                    return self._process_gemini_response(resp_data)

        except aiohttp.ClientError as ce:
            logger.exception(f"❌ Error de red comunicando con Gemini API: {ce}")
            return {
                "exito": False,
                "error": "NETWORK_ERROR",
                "mensaje": f"Error de conexión con Google Gemini: {str(ce)}",
                "slots_96": [0] * 96,
                "tramos": []
            }
        except Exception as e:
            logger.exception(f"❌ Error inesperado procesando imagen con Gemini Vision: {e}")
            return {
                "exito": False,
                "error": "UNEXPECTED_ERROR",
                "mensaje": f"Error procesando la imagen: {str(e)}",
                "slots_96": [0] * 96,
                "tramos": []
            }

    def _process_gemini_response(self, resp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extrae y normaliza la respuesta JSON de Gemini."""
        try:
            candidates = resp_data.get("candidates", [])
            if not candidates:
                return {
                    "exito": False,
                    "error": "NO_CANDIDATES",
                    "mensaje": "Gemini no generó ninguna respuesta para la imagen.",
                    "slots_96": [0] * 96,
                    "tramos": []
                }

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                return {
                    "exito": False,
                    "error": "NO_PARTS",
                    "mensaje": "Respuesta vacía de Gemini.",
                    "slots_96": [0] * 96,
                    "tramos": []
                }

            text = parts[0].get("text", "")
            # Limpiar posible markdown wrapper ```json ... ```
            cleaned_text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
            cleaned_text = re.sub(r"\s*```$", "", cleaned_text.strip(), flags=re.MULTILINE)

            parsed = json.loads(cleaned_text)

            # Validar y sanear el array slots_96
            slots = parsed.get("slots_96", [])
            if not isinstance(slots, list):
                slots = [0] * 96
            else:
                # Asegurar exactamente 96 elementos numéricos
                slots = [int(s) if str(s).isdigit() and 0 <= int(s) <= 4 else 0 for s in slots]
                if len(slots) < 96:
                    slots.extend([0] * (96 - len(slots)))
                elif len(slots) > 96:
                    slots = slots[:96]

            parsed["slots_96"] = slots
            parsed["exito"] = True

            # Recalcular totales precisos basados en los slots
            c_min = sum(1 for s in slots if s == 1) * 15
            e_min = sum(1 for s in slots if s == 2) * 15
            a_min = sum(1 for s in slots if s == 3) * 15
            d_min = sum(1 for s in slots if s == 4) * 15

            parsed["resumen_horas"] = {
                "minutos_conduccion": c_min,
                "minutos_espera": e_min,
                "minutos_auxiliares": a_min,
                "minutos_descanso": d_min,
                "horas_conduccion": round(c_min / 60.0, 2),
                "horas_espera": round(e_min / 60.0, 2),
                "horas_auxiliares": round(a_min / 60.0, 2),
                "horas_descanso": round(d_min / 60.0, 2)
            }

            logger.info(
                f"✅ GeminiVision: Éxito en lectura. "
                f"Conducción: {parsed['resumen_horas']['horas_conduccion']}h, "
                f"Espera: {parsed['resumen_horas']['horas_espera']}h, "
                f"Descanso: {parsed['resumen_horas']['horas_descanso']}h"
            )
            return parsed

        except Exception as parse_err:
            logger.exception(f"❌ Error parseando JSON de Gemini Vision: {parse_err}")
            return {
                "exito": False,
                "error": "JSON_PARSE_ERROR",
                "mensaje": f"No se pudo estructurar la lectura de la libreta: {str(parse_err)}",
                "slots_96": [0] * 96,
                "tramos": []
            }


# Instancia singleton para inyección en FastAPI
gemini_vision_service = GeminiVisionService()
