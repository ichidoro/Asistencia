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

        prompt = f"""Eres un perito experto en lectura visual y análisis forense de planillas oficiales de asistencia laboral según la Resolución Exenta N° 1213 de la Dirección del Trabajo de Chile (Libreta de Control de Jornada de Choferes de Carga Terrestre - Art. 25 bis del Código del Trabajo).

La imagen adjunta es una FOTOGRAFÍA de la hoja física de registro diario de un conductor.

ESTRUCTURA EXACTA DE LAS 4 FILAS IMPRESAS EN LA HOJA FÍSICA (De arriba hacia abajo):
1. FILA 1 (Superior) = CONDUCCIÓN:
   - Corresponde al tiempo manejando el camión al volante.
   - En nuestro sistema se codifica con el número 1.

2. FILA 2 = TIEMPO DE ESPERA:
   - Tiempos de espera para carga, descarga o turno sin conducción.
   - En nuestro sistema se codifica con el número 2.

3. FILA 3 = DESCANSO:
   - ¡ORDEN OFICIAL DE LA HOJA CHILENA! La tercera fila es DESCANSO.
   - En nuestro sistema el descanso se codifica con el número 4.
   - Si no hay trazo manuscrito en esta fila, sus slots son 0.

4. FILA 4 (Inferior) = TAREAS AUXILIARES / LABORES AUXILIARES:
   - ¡ATENCIÓN CRÍTICA! La cuarta fila (la de más abajo) corresponde a TAREAS AUXILIARES (revisión mecánica, estiba, papeleo, mantenimiento).
   - En nuestro sistema las Labores/Tareas Auxiliares se codifican con el número 3.
   - Cualquier línea continua, raya a lápiz o bloque en esta cuarta fila DEBE codificarse como 3 (Labores Auxiliares).

{f"FECHA ESPERADA DE LA JORNADA: {fecha_esperada}" if fecha_esperada else ""}

INSTRUCCIONES DE PRECISIÓN MILIMÉTRICA:
1. ORIENTACIÓN: Si la fotografía fue tomada verticalmente (90 grados) o apaisada, oriéntala mentalmente para que la regla de horas (00 a 24) corra de izquierda a derecha y las 4 filas queden en su orden: 1. Conducción, 2. Espera, 3. Descanso, 4. Tareas Auxiliares.
2. LECTURA DE LA REGLA DE 24 HORAS:
   - La cuadrícula tiene 24 horas continuas (00:00 a 24:00) divididas en 96 tramos de 15 minutos (cada hora tiene 4 divisiones: :00, :15, :30, :45).
   - CRITERIO INCLUSIVO DE BORDES: Si el chofer trazó una línea desde una marca de hora (ej. de 08:00 a 12:00), no recortes los extremos: cuenta las 4 horas completas (16 slots consecutivos de 15 minutos). Si eran 4 horas, deben ser exactamente 16 slots con código 1 (no 14 slots).
3. DETECCIÓN DE TAREAS AUXILIARES (FILA 4):
   - Examina con máxima atención la FILA 4 (Tareas Auxiliares). Si el conductor marcó un tramo largo (por ejemplo de 9.5 horas), cuenta cada uno de los 38 cuartos de hora correspondientes (9.5h * 4 = 38 slots) y asígnales el código 3.
4. VERIFICACIÓN CRUZADA CON TOTALES ESCRITOS:
   - Revisa si en la columna de totales (o al final/inicio de las filas) el conductor escribió números manuscritos con los totales del día (ejemplo: "4" o "04:00" en Conducción, "9.5" o "09:30" en Auxiliares).
   - Si existen esos números, utilízalos para verificar y calibrar que la cantidad de slots coincida exactamente (4h = 16 slots, 9.5h = 38 slots).
5. CASILLAS EN BLANCO:
   - Si una fila o tramo no tiene ninguna línea o marca manuscrita trazada por el chofer, déjalo estrictamente en 0 (Vacío). NO inventes descansos si la fila de descanso está en blanco.

CÓDIGOS DE CADA TRAMO PARA EL ARRAY `slots_96` (Exactamente 96 números de 0 a 4):
- 1: Conducción (Fila 1)
- 2: Espera (Fila 2)
- 3: Tareas / Labores Auxiliares (Fila 4)
- 4: Descanso (Fila 3)
- 0: Sin marcar / Vacío

RESPONDE OBLIGATORIAMENTE EN FORMATO JSON ESTRICTO CON ESTE ESQUEMA EXACTO:
{{
  "exito": true,
  "fecha_detectada": "YYYY-MM-DD o null si no se ve",
  "conductor_detectado": "Nombre del chofer si está escrito o null",
  "confianza": 0.95,
  "tramos": [
    {{"inicio": "HH:MM", "fin": "HH:MM", "actividad": "CONDUCCION", "duracion_horas": 4.0}},
    {{"inicio": "HH:MM", "fin": "HH:MM", "actividad": "AUXILIARES", "duracion_horas": 9.5}}
  ],
  "slots_96": [0, 0, ..., 1, 1, ..., 3, 3, ...],
  "resumen_horas": {{
    "minutos_conduccion": 240,
    "minutos_espera": 0,
    "minutos_auxiliares": 570,
    "minutos_descanso": 0
  }},
  "observaciones": "Detalles observados del trazo y lectura"
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
                f"Auxiliares: {parsed['resumen_horas']['horas_auxiliares']}h, "
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
