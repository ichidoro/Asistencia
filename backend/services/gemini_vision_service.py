import os
import json
import base64
import re
import asyncio
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

    @property
    def api_key(self) -> str:
        """
        Obtiene dinámicamente la API Key desde settings, variables de entorno
        o buscando directamente en archivos .env en el servidor.
        """
        key = (
            getattr(settings, "GEMINI_API_KEY", None)
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )
        if key and len(str(key).strip()) > 10:
            return str(key).strip()

        # Intento de lectura directa de posibles archivos .env
        candidates = [
            os.path.join(os.getcwd(), ".env"),
            os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
            os.path.join(os.path.dirname(__file__), "..", ".env"),
            ".env"
        ]
        for env_file in candidates:
            try:
                if os.path.isfile(env_file):
                    with open(env_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("GEMINI_API_KEY="):
                                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                                if len(val) > 10:
                                    return val
            except Exception:
                pass

        return ""

    @property
    def model(self) -> str:
        """Obtiene dinámicamente el modelo configurado."""
        return (
            getattr(settings, "GEMINI_MODEL", None)
            or os.environ.get("GEMINI_MODEL")
            or "gemini-3.6-flash"
        )

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

        # Modelos a intentar en orden de preferencia y resiliencia ante alta demanda
        candidate_models = [self.model]
        for fallback_m in ["gemini-3.6-flash", "gemini-flash-latest", "gemini-3.1-flash-lite"]:
            if fallback_m not in candidate_models:
                candidate_models.append(fallback_m)

        timeout = aiohttp.ClientTimeout(total=40)
        last_error = ""
        last_status = 500

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for idx, model_name in enumerate(candidate_models):
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
                    logger.info(f"📸 GeminiVision: Intento {idx+1}/{len(candidate_models)} con {model_name} ({len(image_bytes)/1024:.1f} KB)...")

                    try:
                        async with session.post(url, json=payload) as resp:
                            if resp.status == 200:
                                resp_data = await resp.json()
                                logger.info(f"✅ GeminiVision: Modelo {model_name} respondió exitosamente (HTTP 200).")
                                return self._process_gemini_response(resp_data)

                            last_status = resp.status
                            last_error = await resp.text()
                            logger.warning(f"⚠️ GeminiVision: Modelo {model_name} devolvió HTTP {resp.status}: {last_error[:160]}")

                            # Si es error 503 (sobrecarga/alta demanda) o 429 (límite temporal de peticiones)
                            # esperar una breve pausa con backoff antes de probar el siguiente modelo del pool
                            if resp.status in (429, 503) and idx < len(candidate_models) - 1:
                                backoff_wait = 1.5 * (idx + 1)
                                logger.info(f"⏳ Alta demanda en {model_name}. Esperando {backoff_wait}s antes de intentar con {candidate_models[idx+1]}...")
                                await asyncio.sleep(backoff_wait)
                                continue

                    except aiohttp.ClientError as req_err:
                        logger.warning(f"⚠️ GeminiVision: Error de red con {model_name}: {req_err}")
                        last_error = str(req_err)
                        if idx < len(candidate_models) - 1:
                            await asyncio.sleep(1.0)
                            continue

            # Si todos los modelos de la cascada fallaron por saturación
            logger.error(f"❌ Todos los modelos ({candidate_models}) fallaron. Último status: {last_status}")
            es_demanda = "overload" in last_error.lower() or "demand" in last_error.lower() or last_status in (429, 503)
            msg_usuario = (
                "Google Gemini reporta alta demanda temporal en sus servidores gratuitos (HTTP 503/429). "
                "Por favor espera 5 segundos y vuelve a presionar Escanear."
                if es_demanda else f"Error ({last_status}) comunicando con Gemini Vision: {last_error[:180]}"
            )
            return {
                "exito": False,
                "error": "MODEL_OVERLOADED" if es_demanda else f"API_ERROR_{last_status}",
                "mensaje": msg_usuario,
                "slots_96": [0] * 96,
                "tramos": []
            }

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
