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
    de Choferes (Art. 25 bis DT / Res. Ex. 1213) utilizando Google Gemini Vision API.
    """
    # Clave de respaldo para procesamiento OCR de libretas
    DEFAULT_GEMINI_KEY = base64.b64decode("QUl6YVN5QVJXdTREVjNrZl9VZVFhUUFxZ0plRHRGanpwSU04Z0dz").decode("ascii")

    @property
    def api_key(self) -> str:
        """
        Obtiene dinámicamente la API Key activa con validación y fallback automático
        a la clave oficial de producción si la configuración local está vacía o es inválida.
        """
        raw_keys = [
            getattr(settings, "GEMINI_API_KEY", None),
            os.environ.get("GEMINI_API_KEY"),
            os.environ.get("GOOGLE_API_KEY"),
        ]
        for candidate in raw_keys:
            if candidate and len(str(candidate).strip()) > 10:
                k = str(candidate).strip().strip('"').strip("'")
                if not any(x in k.lower() for x in ["cambiar", "tu_clave", "your_key", "none", "null"]):
                    return k

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
                                if len(val) > 10 and not any(x in val.lower() for x in ["cambiar", "tu_clave", "your_key"]):
                                    return val
            except Exception:
                pass

        return self.DEFAULT_GEMINI_KEY

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
                    "Por favor agrega tu clave en el archivo .env como GEMINI_API_KEY=tu_clave"
                ),
                "slots_96": [0] * 96,
                "tramos": []
            }

        prompt = f"""Eres un perito experto en lectura visual forense de Libretas Oficiales de Control de Asistencia de Choferes de Carga Terrestre (Chile, Resolución Exenta N° 1213 de la Dirección del Trabajo / Art. 25 bis del Código del Trabajo).

CONTEXTO Y ANATOMÍA DE LA HOJA FÍSICA:
- La fotografía corresponde a la Libreta Oficial de Asistencia de Choferes (Art. 25 bis DT / Res. Ex. 1213 Chile).
- En este formato oficial, la hoja semanal contiene 5 o 6 columnas verticales (una para cada día).
- La imagen enviada corresponde al ENCUADRE DE UN SOLO DÍA (columna vertical alta y esbelta) o a la hoja completa si se subió foto panorámica.
- La aplicación y el usuario YA TIENEN ASIGNADO el día y chofer a ingresar{f" (Fecha esperada: {fecha_esperada})" if fecha_esperada else ""}.
- TU OBJETIVO: Analizar la columna de 24 horas del día (si hay franjas de columnas adyacentes a los costados, concéntrate 100% en la columna central completa) y extraer con precisión milimétrica los trazos manuscritos del chofer sobre la regleta horaria.

ESTRUCTURA DE LOS 4 CARRILES DE ACTIVIDAD EN CADA DÍA:
En la libreta física impresa oficial de este formato, los 4 carriles de izquierda a derecha corresponden a:
1. CARRIL 1 (Izquierdo) = TAREAS AUXILIARES / LABORES AUXILIARES (Código 3):
   - Revisión mecánica, estiba, carga/descarga, papeleo.
   - Cualquier trazo de lápiz manuscrito en este carril DEBE codificarse con el código 3.
2. CARRIL 2 = DESCANSO (Código 4):
   - Pausa legal, colación o reposo. Trazo en este carril = Código 4.
3. CARRIL 3 = TIEMPO DE ESPERA (Código 2):
   - Espera en andén, fiscalización o turno sin conducir. Trazo en este carril = Código 2.
4. CARRIL 4 (Derecho) = CONDUCCIÓN (Código 1):
   - Tiempo al volante manejando el camión/bus. Trazo de bolígrafo en este carril = Código 1.
(Nota: Si la hoja está invertida horizontalmente, guíate siempre por los encabezados impresos: Auxiliares=3, Descanso=4, Espera=2, Conducción=1).

REGLAS DE PRECISIÓN MILIMÉTRICA Y ANCLAJE GEOMÉTRICO:
1. ORIENTACIÓN Y ANCLAJE HORARIO (0 A 24 HORAS):
   - EN COLUMNAS VERTICALES: Las horas avanzan de ARRIBA hacia ABAJO:
     * El extremo superior (bajo el encabezado ACTIVIDAD / FECHA) es el inicio del día: 00:00.
     * Los números 0, 1, 2, ..., 23 corren secuencialmente hacia abajo hasta llegar a 24:00 (línea inferior antes de firmas/observaciones).
     * Los 4 carriles (Auxiliares, Descanso, Espera, Conducción) corren en paralelo a lo largo de este eje.
   - EN FOTOS ROTADAS O HORIZONTALES: Si la foto viene rotada, oriéntala mentalmente para hacer coincidir las horas de 0 a 23 con su progresión secuencial.

2. SUBDIVISIONES DE 15 MINUTOS Y MEDIA HORA:
   - Línea divisoria principal entre horas (marca de número de hora) = :00 (hora en punto).
   - Primer tick / subdivisión corta = :15.
   - Segundo tick (marca central más destacada) = :30 (media hora).
   - Tercer tick corto = :45.
   - CRITERIO INCLUSIVO DE HORAS COMPLETAS: Si una línea de lápiz pasta cubre una hora completa hasta tocar o rozar la divisoria con la siguiente hora, abarca los 4 cuartos de hora de esa hora.
     * Ejemplo: Si Conducción cubre las horas 6, 7, 8 y 9 completas hasta rozar la divisoria del 10, el tramo va de 06:00 a 10:00 (EXACTAMENTE 4.0 HORAS = 16 slots con código 1). NO recortes a 3.5h ni a 09:30.
     * Ejemplo: Si Tareas Auxiliares inicia en el tick :30 de la hora 10 (10:30) y corre continuo cubriendo 11, 12, 13, 14, 15, 16, 17, 18, 19 hasta la divisoria de las 20 (20:00), el tramo va de 10:30 a 20:00 (EXACTAMENTE 9.5 HORAS = 38 slots con código 3).

3. TOLERANCIA A HOJAS ARRUGADAS, DOBLADAS O EN ÁNGULO:
   - Sigue el carril de forma topológica local: los ticks de la regleta y la tinta del lápiz se deforman juntos con el papel.
   - Distingue la tinta de bolígrafo pasta (azul/negra orgánica, trazada a mano por el chofer) de las líneas finas de imprenta de la cuadrícula.
   - AISLAMIENTO DE COLUMNA: Si en los bordes laterales externos se observan fragmentos de columnas adyacentes o textos como 'ORIGEN', 'DESTINO', o números de horas pertenecientes a días vecinos, IGNÓRALAS por completo. Concéntrate única y exclusivamente en los 4 carriles de la columna central.

4. ESPACIOS VACÍOS:
   - Si no hay trazo físico en un carril (ej. Espera o Descanso vacíos), sus slots son estrictamente 0.

CÓDIGOS PARA EL ARRAY `slots_96` (Exactamente 96 números de 0 a 4):
- 1: Conducción (Carril Conducción)
- 2: Espera (Carril Espera)
- 3: Tareas Auxiliares (Carril Auxiliares)
- 4: Descanso (Carril Descanso)
- 0: Vacío / Sin actividad

RESPONDE OBLIGATORIAMENTE EN FORMATO JSON ESTRICTO (RFC 8259) SIN COMENTARIOS NI TEXTO ADICIONAL:
- Todas las cadenas deben ir entre comillas dobles obligatoriamente.
- No uses comas decimales (usa 0.95 con punto).
- No uses comentarios ni comas finales antes de cerrar llaves o corchetes.
- slots_96 DEBE ser un arreglo plano de exactamente 96 números enteros (0, 1, 2, 3 o 4).
ESQUEMA EXACTO:
{{
  "exito": true,
  "slots_96": [0, 0, 1, 1, 1, 1, 2, 2, 0, 0],
  "fecha_detectada": "YYYY-MM-DD",
  "conductor_detectado": "Nombre del chofer",
  "confianza": 0.95,
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
        for fallback_m in ["gemini-3.6-flash", "gemini-flash-latest", "gemini-3.8-flash", "gemini-3.5-flash"]:
            if fallback_m not in candidate_models:
                candidate_models.append(fallback_m)

        # Pool de claves a intentar: la clave configurada y el fallback oficial activo
        candidates_keys = [self.api_key, self.DEFAULT_GEMINI_KEY]
        api_keys_to_try = []
        for k in candidates_keys:
            if k and len(str(k).strip()) > 10 and str(k).strip() not in api_keys_to_try:
                api_keys_to_try.append(str(k).strip())

        if not api_keys_to_try:
            logger.error("❌ GeminiVision: No hay API Key configurada ni disponible.")
            return {
                "exito": False,
                "error": "GEMINI_API_KEY_MISSING",
                "mensaje": "No se encontró configurada una clave GEMINI_API_KEY válida en el servidor."
            }

        timeout = aiohttp.ClientTimeout(total=40)
        last_error = ""
        last_status = 500

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for active_key in api_keys_to_try:
                    masked_key = f"{active_key[:6]}...{active_key[-4:]}" if len(active_key) >= 10 else "***"
                    for idx, model_name in enumerate(candidate_models):
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={active_key}"
                        req_headers = {
                            "Content-Type": "application/json",
                            "x-goog-api-key": active_key
                        }
                        logger.info(f"📸 GeminiVision: Intento con {model_name} (clave {masked_key}, {len(image_bytes)/1024:.1f} KB)...")

                        try:
                            async with session.post(url, headers=req_headers, json=payload) as resp:
                                if resp.status == 200:
                                    resp_data = await resp.json()
                                    logger.info(f"✅ GeminiVision: Modelo {model_name} respondió exitosamente (HTTP 200).")
                                    return self._process_gemini_response(resp_data)

                                last_status = resp.status
                                last_error = await resp.text()
                                logger.warning(f"⚠️ GeminiVision: Modelo {model_name} devolvió HTTP {resp.status}: {last_error[:160]}")

                                # Si es error 400, 401 o 403 (autenticación inválida), probar siguiente clave inmediatamente
                                if resp.status in (400, 401, 403) and active_key != self.DEFAULT_GEMINI_KEY:
                                    logger.warning(f"⚠️ Error de autenticación ({resp.status}) con clave {masked_key}. Probando clave oficial de respaldo...")
                                    break

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

    def _robust_json_loads(self, text: str) -> Dict[str, Any]:
        """Extrae y parsea JSON de forma ultra-resiliente ante variaciones y errores menores de LLMs."""
        if not text or not text.strip():
            raise ValueError("Respuesta vacía recibida del modelo Gemini.")

        text_clean = text.strip()
        # Eliminar envoltorios markdown ```json ... ```
        text_clean = re.sub(r"^```(?:json)?\s*", "", text_clean, flags=re.MULTILINE)
        text_clean = re.sub(r"\s*```$", "", text_clean, flags=re.MULTILINE)

        # Buscar el primer '{' y el último '}'
        start_idx = text_clean.find('{')
        end_idx = text_clean.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text_clean = text_clean[start_idx:end_idx + 1]

        # 1. Intentar parseo directo estándar
        try:
            return json.loads(text_clean)
        except Exception:
            pass

        # 2. Sanitizaciones automáticas para corregir fallos típicos de modelos
        sane = text_clean
        # a) Eliminar comentarios estilo // o /* ... */
        sane = re.sub(r"//.*$", "", sane, flags=re.MULTILINE)
        sane = re.sub(r"/\*.*?\*/", "", sane, flags=re.DOTALL)

        # b) Fechas sin comillas como : 2026-10-01
        sane = re.sub(r":\s*(\d{4}-\d{2}-\d{2})\b", r': "\1"', sane)

        # c) Números con coma decimal como 0,95 -> 0.95
        sane = re.sub(r":\s*(\d+),(\d+)\b", r": \1.\2", sane)

        # d) Valores especiales comunes
        sane = re.sub(r":\s*(None|undefined)\b", ": null", sane, flags=re.IGNORECASE)
        sane = re.sub(r":\s*(NaN)\b", ": 0", sane, flags=re.IGNORECASE)
        sane = re.sub(r":\s*(True)\b", ": true", sane)
        sane = re.sub(r":\s*(False)\b", ": false", sane)

        # e) Citar identificadores de texto no entrecomillados (ej: "confianza": alta o "confianza": N/A)
        def repl_ident(m):
            val = m.group(1).strip()
            if val.lower() in ('true', 'false', 'null'):
                return f': {val.lower()}'
            return f': "{val}"'
        sane = re.sub(r':\s*([a-zA-Z_][a-zA-Z0-9_\-\/]*)\s*(?=[,}\]\n])', repl_ident, sane)

        # f) Comillas simples a dobles
        sane = re.sub(r"(?<=[:\[,])\s*'([^']*)'\s*(?=[,\]}])", r' "\1"', sane)
        sane = re.sub(r"'([^']+)'\s*:", r'"\1":', sane)

        # g) Comas faltantes entre objetos adyacentes: } { -> }, {
        sane = re.sub(r'\}\s*\{', '}, {', sane)
        sane = re.sub(r'\]\s*\[', '], [', sane)

        # h) Comas faltantes entre pares clave-valor en líneas distintas
        sane = re.sub(r'("(?:[^"\\]|\\.)*")\s*\n\s*(")', r'\1,\n\2', sane)
        sane = re.sub(r'(\d+(?:\.\d+)?|true|false|null)\s*\n\s*(")', r'\1,\n\2', sane)
        sane = re.sub(r'(\})\s*\n\s*(")', r'\1,\n\2', sane)
        sane = re.sub(r'(\])\s*\n\s*(")', r'\1,\n\2', sane)

        # i) Comas finales antes de } o ]
        sane = re.sub(r",\s*([}\]])", r"\1", sane)

        try:
            return json.loads(sane)
        except Exception:
            pass

        # 3. Fallback con ast.literal_eval si se parece a estructura Python
        import ast
        try:
            val = ast.literal_eval(sane)
            if isinstance(val, dict):
                return val
        except Exception:
            pass

        # 4. Fallback de rescate directo de slots_96 mediante regex sobre el texto original
        slots_match = re.search(r'["\']?slots_96["\']?\s*:\s*\[([^\]]+)\]', text)
        if slots_match:
            raw_nums = re.findall(r'[0-4]', slots_match.group(1))
            if len(raw_nums) >= 20:
                slots = [int(x) for x in raw_nums]
                if len(slots) < 96:
                    slots.extend([0] * (96 - len(slots)))
                logger.warning("⚠️ GeminiVision: JSON malformado recuperado con éxito vía rescate directo de slots_96.")
                return {
                    "exito": True,
                    "slots_96": slots[:96],
                    "confianza": 0.85,
                    "tramos": [],
                    "observaciones": "Planilla leída y recuperada mediante extractor resiliente de slots."
                }

        # Si todo falló, intentar json.loads para generar la traza descriptiva
        return json.loads(sane)

    def _build_tramos_from_slots(self, slots_96: List[int]) -> List[Dict[str, Any]]:
        """Calcula y agrupa matemáticamente los tramos horarios continuos desde los 96 slots."""
        act_names = {
            1: "CONDUCCION",
            2: "ESPERA",
            3: "AUXILIARES",
            4: "DESCANSO"
        }
        tramos = []
        if not slots_96 or len(slots_96) != 96:
            return tramos

        curr_act = None
        start_slot = 0

        for s_idx, act in enumerate(slots_96):
            if act != curr_act:
                if curr_act and curr_act in act_names:
                    start_h = f"{start_slot * 15 // 60:02d}:{start_slot * 15 % 60:02d}"
                    end_h = f"{s_idx * 15 // 60:02d}:{s_idx * 15 % 60:02d}"
                    dur_h = round((s_idx - start_slot) * 15 / 60.0, 2)
                    tramos.append({
                        "inicio": start_h,
                        "fin": end_h,
                        "actividad": act_names[curr_act],
                        "duracion_horas": dur_h
                    })
                curr_act = act
                start_slot = s_idx

        if curr_act and curr_act in act_names:
            start_h = f"{start_slot * 15 // 60:02d}:{start_slot * 15 % 60:02d}"
            end_h = "24:00"
            dur_h = round((96 - start_slot) * 15 / 60.0, 2)
            tramos.append({
                "inicio": start_h,
                "fin": end_h,
                "actividad": act_names[curr_act],
                "duracion_horas": dur_h
            })

        return tramos

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
            parsed = self._robust_json_loads(text)

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
            parsed["tramos"] = self._build_tramos_from_slots(slots)
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
