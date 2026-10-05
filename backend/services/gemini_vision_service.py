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
            or "gemini-flash-latest"
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

        prompt = f"""Eres un perito experto en lectura visual forense de Libretas Oficiales de Control de Asistencia de Choferes de Carga Terrestre (Chile, Resolución Exenta N° 1213 de la Dirección del Trabajo / Art. 25 bis del Código del Trabajo).

CONTEXTO Y ANATOMÍA DE LA HOJA FÍSICA:
- La fotografía capturada corresponde a una hoja de control de jornada.
- En la hoja física suele haber 5 bloques impresos en paralelo (uno para cada día).
- La aplicación y el usuario YA TIENEN ASIGNADO el día y chofer a ingresar{f" (Fecha esperada: {fecha_esperada})" if fecha_esperada else ""}.
- TU OBJETIVO: Analizar el bloque principal de 24 horas visible en la imagen (o el bloque central/más destacado si hay varios visibles) y extraer con precisión milimétrica los trazos manuscritos del chofer sobre la regleta horaria.

ESTRUCTURA DE LAS 4 FILAS IMPRESAS EN CADA BLOQUE (De arriba hacia abajo):
1. FILA 1 (Superior) = CONDUCCIÓN (Código 1):
   - Tiempo manejando al volante. Línea azul/negra manuscrita en este carril = Código 1.
2. FILA 2 = TIEMPO DE ESPERA (Código 2):
   - Espera en andén, fiscalización o turno sin conducir. Línea en este carril = Código 2.
3. FILA 3 = DESCANSO (Código 4):
   - Pausa legal, colación o reposo. Línea en este carril = Código 4.
4. FILA 4 (Inferior) = TAREAS AUXILIARES / LABORES AUXILIARES (Código 3):
   - ¡PRIORIDAD CRÍTICA! La cuarta fila (la de más abajo) corresponde a TAREAS AUXILIARES (revisión mecánica, estiba, carga/descarga, papeleo).
   - Cualquier trazo horizontal manuscrito en esta cuarta fila DEBE codificarse obligatoriamente con el código 3.

REGLAS DE PRECISIÓN MILIMÉTRICA Y ANCLAJE GEOMÉTRICO:
1. ORIENTACIÓN Y ANCLAJE HORIZONTAL (0 A 23):
   - Las fotos pueden venir en vertical o giradas 90°. Oriéntala mentalmente para que la regleta de 0 a 23 vaya de izquierda a derecha.
   - EXTREMO IZQUIERDO: La línea vertical divisoria que separa los textos ("CONDUCCION", etc.) de la columna "0" es el inicio del día: 00:00.
   - EXTREMO DERECHO: La línea vertical que cierra la columna "23" antes de "DESTINO/Resumen" es el fin del día: 24:00.

2. SUBDIVISIONES DE 15 MINUTOS Y MEDIA HORA:
   - Línea divisoria vertical entre columnas horarias (atraviesa las 4 filas) = :00 (hora en punto).
   - Primer tick corto = :15.
   - Segundo tick (marca central más larga) = :30 (media hora).
   - Tercer tick corto = :45.
   - CRITERIO INCLUSIVO DE HORAS COMPLETAS: Si una línea manuscrita cubre una columna "H" completa hasta rozar o tocar la divisoria con la siguiente hora, abarca los 4 cuartos de hora de esa columna.
     * Ejemplo: Si Conducción cubre columnas 6, 7, 8 y 9 hasta la divisoria con el 10, el tramo va de 06:00 a 10:00 (EXACTAMENTE 4.0 HORAS = 16 slots con código 1). NO recortes a 3.5h ni a 09:30.
     * Ejemplo: Si Tareas Auxiliares inicia en el tick :30 de la columna 10 (10:30) y corre continuo cubriendo 11, 12, 13, 14, 15, 16, 17, 18, 19 hasta la línea divisoria del 20 (20:00), el tramo va de 10:30 a 20:00 (EXACTAMENTE 9.5 HORAS = 38 slots con código 3).

3. TOLERANCIA A HOJAS ARRUGADAS, DOBLADAS O EN ÁNGULO:
   - Sigue el carril de forma topológica local: los ticks de la regleta y la tinta del lápiz se deforman juntos con el papel.
   - Distingue la tinta de bolígrafo pasta (azul/negra orgánica, trazada por el centro del carril) de las líneas finas de imprenta de la cuadrícula.

4. ESPACIOS VACÍOS:
   - Si no hay trazo físico en una fila (ej. Espera o Descanso vacías), sus slots son estrictamente 0.

CÓDIGOS PARA EL ARRAY `slots_96` (Exactamente 96 números de 0 a 4):
- 1: Conducción (Fila 1)
- 2: Espera (Fila 2)
- 3: Tareas Auxiliares (Fila 4)
- 4: Descanso (Fila 3)
- 0: Vacío / Sin actividad

RESPONDE OBLIGATORIAMENTE EN FORMATO JSON ESTRICTO CON ESTE ESQUEMA EXACTO:
{{
  "exito": true,
  "fecha_detectada": "YYYY-MM-DD o null si no se ve clara",
  "conductor_detectado": "Nombre del chofer si está escrito o null",
  "confianza": 0.95,
  "tramos": [
    {{"inicio": "06:00", "fin": "10:00", "actividad": "CONDUCCION", "duracion_horas": 4.0}},
    {{"inicio": "10:30", "fin": "20:00", "actividad": "AUXILIARES", "duracion_horas": 9.5}}
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
        for fallback_m in ["gemini-flash-latest", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite"]:
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

            # Detectar brechas intermedias vacías entre actividades para sugerir autocompletado de descanso
            active_indices = [i for i, s in enumerate(slots) if s in (1, 2, 3)]
            brechas_vacias = []
            if active_indices:
                first_act = min(active_indices)
                last_act = max(active_indices)
                gap_start = None
                for i in range(first_act, last_act + 1):
                    if slots[i] == 0:
                        if gap_start is None:
                            gap_start = i
                    else:
                        if gap_start is not None:
                            h_ini = f"{gap_start * 15 // 60:02d}:{(gap_start * 15) % 60:02d}"
                            h_fin = f"{i * 15 // 60:02d}:{(i * 15) % 60:02d}"
                            gap_len = i - gap_start
                            brechas_vacias.append({
                                "slot_inicio": gap_start,
                                "slot_fin": i - 1,
                                "inicio": h_ini,
                                "fin": h_fin,
                                "minutos": gap_len * 15,
                                "horas": round(gap_len * 15 / 60.0, 1)
                            })
                            gap_start = None

            parsed["brechas_vacias"] = brechas_vacias
            parsed["sugerir_autocompletar_descanso"] = len(brechas_vacias) > 0


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
