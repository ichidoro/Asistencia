"""
Sync Service - Servicio de Sincronización
Orquesta el scraping y sincronización de datos
"""

from typing import List, Dict, Any, Optional, Tuple
import asyncio
import time
import json
import hashlib
import inspect
import calendar
from loguru import logger
from datetime import datetime, timedelta

from backend.scraper.bioalba_scraper import BioAlbaScraper
from backend.services.empleado_service import EmpleadoService
from backend.repositories.empleado import EmpleadoRepository
from backend.repositories.turno import TurnoRepository
from backend.core.database import db
from backend.schemas.empleado import EmpleadoCreate

# Singleton: una sola instancia del scraper compartida por todos los SyncService.
# Esto asegura que la sesión HTTP y el login se reutilizan entre operaciones,
# reduciendo de N logins a 1 por ciclo de vida de la app.
_shared_scraper = BioAlbaScraper()

# ── TTL Cache de módulo ─────────────────────────────────────────────────────────
# PERF-3: Cache de empleados BioAlba — TTL 90s
# Útil cuando preview_empleados y sync_empleados ocurren en secuencia rápida.
# Con TTL corto (90s) no se deja data obsoleta en memoria por mucho tiempo.
# ⚠️ NO cachear marcaciones: ruts_set filtra en el parser (RAM cítica), cachear el
# mes completo sin filtro anularía esa optimización y subiría RAM/tiempo de parseo.
_empleados_cache: Optional[Tuple[float, List[Dict]]] = None  # (timestamp, data)
_EMPLEADOS_TTL = 90  # segundos


def _get_empleados_cache() -> Optional[List[Dict]]:
    """Retorna empleados cacheados si el TTL no expiró, si no None."""
    global _empleados_cache
    if _empleados_cache is None:
        return None
    ts, data = _empleados_cache
    if time.monotonic() - ts > _EMPLEADOS_TTL:
        _empleados_cache = None
        return None
    logger.debug(f"⚡ [Cache] Empleados BioAlba desde caché ({len(data)} registros, TTL restante: {int(_EMPLEADOS_TTL - (time.monotonic() - ts))}s)")
    return data


def _set_empleados_cache(data: List[Dict]) -> None:
    """Guarda empleados en caché con timestamp actual."""
    global _empleados_cache
    _empleados_cache = (time.monotonic(), data)
    logger.debug(f"⚡ [Cache] Empleados BioAlba almacenados ({len(data)} registros, TTL={_EMPLEADOS_TTL}s)")


class SyncService:
    """
    Servicio para sincronizar datos desde BioAlba al sistema local.
    
    Funcionalidades:
    - Sincronizar empleados
    - Sincronizar marcaciones
    - Detectar cambios
    - Actualizar/crear registros
    """
    
    def __init__(self):
        self.scraper = _shared_scraper
        self._progress_callback = None  # Inyectable para SSE streaming (asyncio coroutine)
        self.stats = {
            'empleados_nuevos': 0,
            'empleados_actualizados': 0,
            'empleados_sin_cambios': 0,
            'errores': 0,
            'marcaciones_nuevas': 0,
            'marcaciones_duplicadas': 0
        }
    
    async def get_bioalba_areas(self, refresh: bool = False) -> List[str]:
        """
        Obtener lista de áreas disponibles.
        
        Si refresh=False (default): Obtiene las áreas existentes en el catálogo local (Rápido).
        Si refresh=True: Descarga el Excel de BioAlba y extrae todas las áreas únicas (Lento - Deep Scan).
        """
        try:
            if not refresh:
                logger.info("🔍 Obteniendo áreas (DB)...")
                
                areas_set = set()
                # Áreas en Base de Datos Local
                try:
                    from backend.repositories.area import AreaRepository
                    if not db._connected:
                        await db.connect()
                    area_repo = AreaRepository(db)
                    db_areas = await area_repo.get_all_areas()
                    for area in db_areas:
                        areas_set.add(str(area).strip())
                    
                except Exception as db_err:
                    logger.warning(f"⚠️ Error DB Áreas: {db_err}")
                    
                return sorted(list(areas_set))
            
            else:
                # MODO REFRESH: Deep Scan de BioAlba
                logger.info("🚀 INICIANDO ESCANEO PROFUNDO DE ÁREAS DESDE BIOALBA...")
                
                async with self.scraper as scraper:
                    empleados = await scraper.get_empleados()
                    
                    if not empleados:
                        logger.error("❌ No se pudieron descargar empleados para el escaneo de áreas")
                        return await self.get_bioalba_areas(refresh=False)
                    
                    areas_detectadas = set()
                    for emp in empleados:
                        area = emp.get('area')
                        if area:
                            areas_detectadas.add(str(area).strip())
                    
                    logger.success(f"✅ Escaneo profundo completado. {len(areas_detectadas)} áreas detectadas en vivo.")
                    return sorted(list(areas_detectadas))
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo áreas: {e}")
            return []

    async def preview_empleados(self, areas: List[str] = None) -> List[Dict[str, Any]]:
        """
        Previsualizar empleados que serán sincronizados.
        Descarga BioAlba, filtra por áreas, y cruza con DB local para identificar nuevos vs existentes.
        Usa cache de módulo (TTL 90s) para no re-descargar si sync ocurre inmediatamente después.
        """
        try:
            logger.info(f"🔍 Generando preview de empleados (áreas: {areas or 'TODAS'})...")
            
            # PERF-3: Intentar usar cache de empleados BioAlba
            empleados_bioalba = _get_empleados_cache()
            if empleados_bioalba is None:
                async with self.scraper:
                    empleados_bioalba = await self.scraper.get_empleados()
                if empleados_bioalba:
                    _set_empleados_cache(empleados_bioalba)
            
            if not empleados_bioalba:
                return []
            
            # Filtrar por áreas si se especificaron
            if areas and len(areas) > 0:
                empleados_bioalba = [
                    e for e in empleados_bioalba 
                    if str(e.get('area', '')).strip() in areas
                ]
            
            # Cruzar con DB local para detectar nuevos vs existentes
            await db.connect()
            rows = await db.fetch_all("SELECT e.rut, e.nombre, e.apellido_paterno, a.nombre as area, e.activo FROM empleados e LEFT JOIN areas a ON e.area_id = a.id")
            ruts_locales = {}
            for r in rows:
                rut_clean = str(r['rut']).replace('.', '').replace('-', '').strip().upper()
                ruts_locales[rut_clean] = r
            
            resultado = []
            for emp in empleados_bioalba:
                rut = str(emp.get('rut', '')).replace('.', '').replace('-', '').strip().upper()
                if not rut:
                    continue
                
                local = ruts_locales.get(rut)
                nombre_completo = f"{emp.get('apellido_paterno', '')} {emp.get('apellido_materno', '')} {emp.get('nombre', '')}".strip().replace('  ', ' ')
                
                item = {
                    'rut': emp.get('rut', rut),
                    'nombre': nombre_completo,
                    'area': emp.get('area', 'Sin Asignar'),
                    'cargo': emp.get('cargo', ''),
                    'es_nuevo': local is None,
                    'activo_local': local['activo'] if local else None,
                    'area_local': local['area'] if local else None,
                    'cambio_area': bool(local and local['area'] and local['area'] != emp.get('area'))
                }
                resultado.append(item)
            
            # Ordenar: nuevos primero, luego por nombre
            resultado.sort(key=lambda x: (not x['es_nuevo'], x['nombre']))
            
            logger.success(f"✅ Preview: {len(resultado)} empleados ({sum(1 for r in resultado if r['es_nuevo'])} nuevos)")
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error en preview: {e}")
            return []

    async def sync_empleados(self, areas: List[str] = None, ruts: List[str] = None) -> Dict[str, Any]:
        """
        Sincronizar empleados desde BioAlba
        """
        try:
            logger.info("🎬 Iniciando sincronización de empleados...")
            start_time = datetime.now()
            
            # Reset stats
            self.stats = {
                'empleados_nuevos': 0,
                'empleados_actualizados': 0,
                'empleados_sin_cambios': 0,
                'cambios_area': [], # Lista de {id, empleado_id, nombre, area_anterior, area_nueva}
                'filtrados': 0,
                'errores': 0,
                'detalles_errores': [],
                'nuevos_detalles': [], # Lista de {id, nombre, rut} para onboarding
                'inicio': start_time.isoformat(),
                'fin': None,
                'duracion_segundos': 0
            }

            # PERF-3: Consultar cache antes de ir a BioAlba
            # Si preview_empleados fue llamado hace < 90s, la descarga se evita.
            empleados_bioalba = _get_empleados_cache()
            if empleados_bioalba is None:
                async with self.scraper:
                    empleados_bioalba = await self.scraper.get_empleados()
                if empleados_bioalba:
                    _set_empleados_cache(empleados_bioalba)
            
            if not empleados_bioalba:
                logger.warning("No se obtuvieron empleados de BioAlba")
                self.stats['fin'] = datetime.now().isoformat()
                return self.stats
            
            await db.connect()
            repo = EmpleadoRepository(db)
            service = EmpleadoService(repo)
            from backend.repositories.area import AreaRepository
            area_repo = AreaRepository(db)
            
            # --- NUEVO: GUARDIÁN DE ÁREAS ---
            # Validar que todas las áreas de los empleados a sincronizar existan en el catálogo o alias
            areas_desconocidas = set()
            for emp_data in empleados_bioalba:
                area_raw = str(emp_data.get('area', '')).strip()
                if area_raw and area_raw not in ['---', 'None', 'Sin Asignar']:
                    area_id = await area_repo.find_area_id_by_name_or_alias(area_raw)
                    if not area_id:
                        areas_desconocidas.add(area_raw)
            
            if areas_desconocidas:
                logger.warning(f"⚠️ Guardián detectó {len(areas_desconocidas)} áreas desconocidas.")
                return {
                    "status": "requires_confirmation",
                    "nuevas_areas": sorted(list(areas_desconocidas))
                }
            # --------------------------------
            
            # Preparar set de RUTs seleccionados (si existe filtro granular)
            ruts_seleccionados = None
            if ruts and len(ruts) > 0:
                ruts_seleccionados = set(
                    r.replace('.', '').replace('-', '').strip().upper() for r in ruts
                )
                logger.info(f"🎯 Filtro granular activo: {len(ruts_seleccionados)} RUTs seleccionados")

            # Pre-calcular lista filtrada para saber el total ANTES del loop
            emp_filtrados = []
            for emp_data in empleados_bioalba:
                if areas and len(areas) > 0:
                    emp_area = str(emp_data.get('area', '')).strip()
                    if emp_area not in areas:
                        self.stats['filtrados'] += 1
                        continue
                if ruts_seleccionados:
                    emp_rut = str(emp_data.get('rut', '')).replace('.', '').replace('-', '').strip().upper()
                    if emp_rut not in ruts_seleccionados:
                        self.stats['filtrados'] += 1
                        continue
                emp_filtrados.append(emp_data)

            total_a_sync = len(emp_filtrados)
            logger.info(f"📊 Empleados a sincronizar: {total_a_sync} (filtrados: {self.stats['filtrados']})")

            # Helper para invocar el callback SSE de forma segura
            import inspect as _inspect
            async def _call_cb(idx: int, total: int, nombre: str, rut: str):
                cb = self._progress_callback
                if cb and _inspect.iscoroutinefunction(cb):
                    await cb(idx, total, nombre, rut)

            # Emitir evento 'start' (idx=0 = señal especial)
            await _call_cb(0, total_a_sync, '__start__', '__start__')

            async with db.transaction():
                for emp_idx, emp_data in enumerate(emp_filtrados, start=1):
                    # Emitir progreso via callback SSE
                    nombre_raw = (
                        f"{emp_data.get('apellido_paterno','')}"
                        f" {emp_data.get('apellido_materno','')}"
                        f" {emp_data.get('nombre','')}".strip()
                    ).replace('  ', ' ')
                    await _call_cb(emp_idx, total_a_sync, nombre_raw, emp_data.get('rut',''))

                    try:
                        await self._sync_empleado(service, emp_data)
                    except Exception as e:
                        logger.error(f"Error sincronizando empleado {emp_data.get('rut')}: {e}")
                        self.stats['errores'] += 1
                        self.stats['detalles_errores'].append(f"{emp_data.get('rut', 'Desconocido')}: {str(e)}")
            
            # Finalizar
            self.stats['fin'] = datetime.now().isoformat()
            self.stats['duracion_segundos'] = (datetime.now() - start_time).total_seconds()
            
            # --- NUEVO: Grabar log de sincronización ---
            try:
                await db.execute("""
                    INSERT INTO sync_logs (fecha_inicio, fecha_fin, tipo_sync, marcaciones_nuevas, dias_recalculados, errores, duracion_segundos, detalle_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.stats['inicio'],
                    self.stats['fin'],
                    'EMPLEADOS',
                    0,
                    0,
                    self.stats['errores'],
                    self.stats['duracion_segundos'],
                    json.dumps({"nuevos": self.stats['empleados_nuevos'], "actualizados": self.stats['empleados_actualizados']})
                ))
            except Exception as e_log:
                logger.error(f"Error grabando sync_log (empleados): {e_log}")

            logger.success(
                f"✅ Sincronización completada: "
                f"{self.stats['empleados_nuevos']} nuevos, "
                f"{self.stats['empleados_actualizados']} actualizados, "
                f"{self.stats['filtrados']} filtrados, "
                f"{self.stats['errores']} errores"
            )
            
            return self.stats
            
        except Exception as e:
            logger.error(f"❌ Error en sync_empleados: {e}")
            self.stats['error_global'] = str(e)
            return self.stats

    async def search_bioalba_empleado(self, rut: str) -> List[Dict[str, Any]]:
        """
        Busca un empleado por RUT en BioAlba.
        """
        try:
            logger.info(f"🔍 Buscando RUT {rut} en BioAlba...")
            async with self.scraper:
                empleados = await self.scraper.get_empleados()
            
            if not empleados:
                return []
            
            # Normalizar RUT de búsqueda
            rut_busqueda = str(rut).replace(".", "").replace("-", "").strip().upper()
            
            # Filtrar resultados
            resultados = []
            for emp in empleados:
                emp_rut = str(emp.get('rut', '')).replace(".", "").replace("-", "").strip().upper()
                if emp_rut == rut_busqueda:
                    resultados.append(emp)
            
            logger.info(f"✅ Se encontraron {len(resultados)} coincidencias para {rut}")
            return resultados
            
        except Exception as e:
            logger.error(f"❌ Error buscando empleado en BioAlba: {e}")
            return []

    async def sync_marcaciones(self, fecha_inicio: str = None, fecha_fin: str = None, areas: List[str] = None, ruts: List[str] = None, force_recalculate: bool = False, skip_recalc: bool = False) -> Dict[str, Any]:
        """
        Sincronizar marcaciones de asistencia desde BioAlba y RECALCULAR ASISTENCIA.
        Soporta rangos multi-mes: si fecha_inicio y fecha_fin abarcan más de un mes,
        descarga todos los meses involucrados desde BioAlba.
        ruts: Lista de RUTs limpios (sin puntos/guiones) para filtrar marcaciones individuales.
        force_recalculate: Si es True, recalcula todo el rango incluso si no hay marcas nuevas.
        skip_recalc: Si es True, sólo guarda las marcaciones raw y omite el recálculo de asistencia.
                     Usar cuando el caller realizará el reproceso completo por su cuenta.
        """
        try:
            import calendar
            from datetime import timedelta as _td

            # ── Determinar el rango real de fechas ──────────────────────────
            now = datetime.now()
            if fecha_inicio:
                dt_ini = datetime.strptime(fecha_inicio, "%Y-%m-%d")
            else:
                dt_ini = now.replace(day=1)  # primer día del mes actual
                fecha_inicio = dt_ini.strftime("%Y-%m-%d")

            if fecha_fin:
                dt_fin = datetime.strptime(fecha_fin, "%Y-%m-%d")
            else:
                _, last = calendar.monthrange(dt_ini.year, dt_ini.month)
                dt_fin = dt_ini.replace(day=last)
                fecha_fin = dt_fin.strftime("%Y-%m-%d")

            # Construir lista de (mes, anio) que cubre el rango completo
            meses_a_sincronizar = []
            cur = dt_ini.replace(day=1)
            while cur <= dt_fin:
                meses_a_sincronizar.append((cur.month, cur.year))
                if cur.month == 12:
                    cur = cur.replace(year=cur.year + 1, month=1)
                else:
                    cur = cur.replace(month=cur.month + 1)

            logger.info(
                f"🔄 Iniciando sync de marcaciones (rango: {fecha_inicio} → {fecha_fin}, "
                f"meses: {len(meses_a_sincronizar)}, Force: {force_recalculate})..."
            )

            # Reset stats
            self.stats = {
                'marcaciones_nuevas': 0,
                'marcaciones_duplicadas': 0,
                'errores': 0,
                'dias_recalculados': 0,
                'inicio': datetime.now().isoformat(),
                'fin': None,
                'duracion_segundos': 0,
                'filtrados': 0
            }

            start_time = datetime.now()

            # 1. Conectar DB y calcular RUTs válidos ANTES de descargar
            await db.connect()
            turno_repo = TurnoRepository(db)

            from backend.repositories.empleado import EmpleadoRepository
            empleado_repo = EmpleadoRepository(db)

            if ruts and len(ruts) > 0:
                ruts_limpios = set(r.replace('.', '').replace('-', '').strip().upper() for r in ruts)
                logger.info(f"👤 Filtro individual por RUT: {ruts_limpios}")
                valid_ruts = ruts_limpios
            elif areas and len(areas) > 0:
                logger.info(f"👥 Filtrando por áreas específicas (incluyendo cambios pendientes): {areas}")
                valid_ruts = set(await empleado_repo.get_ruts_by_areas_with_pending(areas))
            else:
                logger.info("👥 Filtrando por TODOS los empleados locales (Implicito)")
                valid_ruts = set(await empleado_repo.get_all_ruts())

            logger.info(f"👥 Total empleados válidos para sync: {len(valid_ruts)}")

            # 2. Descargar marcaciones de BioAlba para CADA MES del rango
            # BioAlba solo expone un Excel mensual, por lo que iteramos.
            marcaciones_bioalba = []
            async with self.scraper:
                for mes_iter, anio_iter in meses_a_sincronizar:
                    logger.info(f"📥 Descargando BioAlba: {anio_iter}-{mes_iter:02d}...")
                    lote = await self.scraper.get_marcaciones(
                        mes=mes_iter, anio=anio_iter, ruts_set=valid_ruts
                    )
                    marcaciones_bioalba.extend(lote)
                    logger.info(f"   → {len(lote)} marcaciones obtenidas para {anio_iter}-{mes_iter:02d}")

            # Filtrar sólo marcaciones dentro del rango exacto fecha_inicio..fecha_fin
            # (el Excel mensual puede tener días del mes fuera del rango solicitado)
            marcaciones_bioalba = [
                m for m in marcaciones_bioalba
                if m.get('fecha_hora', '') >= fecha_inicio
                and m.get('fecha_hora', '')[:10] <= fecha_fin
            ]
            logger.info(f"📊 Total marcaciones en rango tras filtro exacto: {len(marcaciones_bioalba)}")

            if not marcaciones_bioalba:
                logger.warning("No se obtuvieron marcaciones de BioAlba para el rango indicado")
                self.stats['fin'] = datetime.now().isoformat()
                return self.stats

            # 3. Obtener Hashes existentes para TODO el rango (no solo un mes)
            existing_hashes = set()
            for mes_iter, anio_iter in meses_a_sincronizar:
                existing_hashes |= await turno_repo.get_existing_hashes(mes_iter, anio_iter)
            logger.debug(f"💾 Hashes existentes en DB (rango completo): {len(existing_hashes)}")

            # [BIOALBA_GATE_PROTECTION]: Soberanía de Turno sobre el RANGO REAL
            # FIX: antes el Gate solo cubría el mes de fecha_inicio, bloqueando
            # todas las marcaciones de meses posteriores aunque el empleado tuviera
            # turno asignado. Ahora opera sobre fecha_inicio..fecha_fin completo.
            fecha_ini_mes = fecha_inicio   # límite inferior real del rango
            fecha_fin_mes = fecha_fin      # límite superior real del rango
            
            logger.info(f"🛡️ Bioalba Gate: Cargando mapa de asignaciones para rango {fecha_ini_mes} → {fecha_fin_mes}...")
            # Obtenemos asignaciones que se crucen con el RANGO COMPLETO (no solo un mes).
            # FIX causa raíz: antes fecha_ini_mes/fecha_fin_mes eran 1er y último día del mes de
            # fecha_inicio, ignorando los meses siguientes del rango multi-mes solicitado.
            if valid_ruts and len(valid_ruts) < 50:
                rut_ph = ','.join('?' * len(valid_ruts))
                gate_params = list(valid_ruts) + [fecha_fin_mes, fecha_ini_mes]
                asigs_raw = await db.fetch_all(f"""
                    SELECT e.id as emp_id, e.rut, ast.fecha_inicio, ast.fecha_fin 
                    FROM asignacion_turnos ast
                    JOIN empleados e ON ast.empleado_id = e.id
                    WHERE e.rut IN ({rut_ph})
                      AND (ast.fecha_inicio <= ? AND (ast.fecha_fin IS NULL OR ast.fecha_fin >= ?))
                """, tuple(gate_params))
            else:
                asigs_raw = await db.fetch_all("""
                    SELECT e.id as emp_id, e.rut, ast.fecha_inicio, ast.fecha_fin 
                    FROM asignacion_turnos ast
                    JOIN empleados e ON ast.empleado_id = e.id
                    WHERE (ast.fecha_inicio <= ? AND (ast.fecha_fin IS NULL OR ast.fecha_fin >= ?))
                """, (fecha_fin_mes, fecha_ini_mes))
            
            # Mapa de [rut_limpio] -> set(fechas_con_turno)
            asig_map_gate = {}
            # Mapa de [rut_limpio] -> empleado_id (para acotar recálculo al batch)
            rut_to_emp_id = {}
            from datetime import timedelta
            for asig in asigs_raw:
                rut_key = str(asig['rut']).replace(".", "").replace("-", "").strip()
                rut_to_emp_id[rut_key] = asig['emp_id']
                if rut_key not in asig_map_gate:
                    asig_map_gate[rut_key] = set()
                
                # Expandir fechas de la asignación dentro del RANGO REAL
                start_dt = max(datetime.strptime(asig['fecha_inicio'], "%Y-%m-%d"), datetime.strptime(fecha_ini_mes, "%Y-%m-%d"))
                end_str = asig['fecha_fin'] or fecha_fin_mes
                end_dt = min(datetime.strptime(end_str, "%Y-%m-%d"), datetime.strptime(fecha_fin_mes, "%Y-%m-%d"))
                
                curr = start_dt
                while curr <= end_dt:
                    asig_map_gate[rut_key].add(curr.strftime("%Y-%m-%d"))
                    curr += timedelta(days=1)
            
            logger.info(f"🛡️ Protection Gate: {len(asig_map_gate)} empleados con asignaciones detectados.")

            fechas_afectadas = set()
            
            # Removido Auto-Repair global

            if force_recalculate:
                # Forzar recálculo para todos los días del rango (puede ser multi-mes)
                curr_force = dt_ini
                while curr_force <= dt_fin:
                    if curr_force <= now:  # no forzar días futuros
                        fechas_afectadas.add(curr_force.strftime("%Y-%m-%d"))
                    curr_force += _td(days=1)
                logger.info(f"⚡ Forzando recálculo para {len(fechas_afectadas)} días del rango.")

            count_skipped = 0
            count_filtered = 0
            count_gate_blocked = 0
            
            # 4. Procesar y Filtrar
            logs_to_save = []
            ruts_afectados = set()  # RUTs que tuvieron marcaciones nuevas en este batch
            for log_data in marcaciones_bioalba:
                try:
                    rut = str(log_data.get('rut', '')).strip()
                    rut_clean = rut.replace(".", "").replace("-", "").strip()
                    
                    # FILTRO 1: Solo empleados sincronizados
                    if rut not in valid_ruts:
                        count_filtered += 1
                        continue

                    fecha_hora = log_data.get('fecha_hora')
                    fecha_str = fecha_hora.split(' ')[0] if fecha_hora else None
                    
                    # REGLA 2+3: BIOALBA GATE — Solo marcaciones con turno activo en esa fecha
                    # Si el empleado no tiene turno asignado O la fecha es anterior a su fecha_inicio,
                    # la marcación se descarta. count_gate_blocked queda para observabilidad en sync_logs.
                    if not fecha_str or rut_clean not in asig_map_gate or fecha_str not in asig_map_gate[rut_clean]:
                        count_gate_blocked += 1
                        continue  # [RFC PASO 1] Descarte estricto: no llega a logs_to_save
                    
                    tipo = log_data.get('tipo')
                    
                    # [ATOMIC_HASH_PROTECTION]: SHA256 Sovereign Hash
                    raw_string = f"{rut}|{fecha_hora}|{tipo or ''}"
                    hash_val = hashlib.sha256(raw_string.encode()).hexdigest()
                    
                    if hash_val in existing_hashes:
                        count_skipped += 1
                        continue # Skip duplicate
                        
                    # Es nuevo -> Acumular para batch
                    logs_to_save.append(log_data)
                    self.stats['marcaciones_nuevas'] += 1
                    ruts_afectados.add(rut_clean)  # Registrar RUT afectado para acotar recálculo
                    
                    if fecha_hora:
                        fecha_str = fecha_hora.split(' ')[0]
                        fechas_afectadas.add(fecha_str)
                        
                except Exception as e:
                    logger.error(f"Error preparando marcación para batch: {e}")
                    self.stats['errores'] += 1
            
            # Construir set de empleado_ids afectados para acotar el recálculo
            if ruts:
                empleados_afectados_ids = {
                    rut_to_emp_id[r] for r in ruts_afectados if r in rut_to_emp_id
                } or None
            else:
                # Al sincronizar el área completa, recalculamos a todos los empleados
                # para asegurar que se generen inasistencias (INA) si no hay marcas
                empleados_afectados_ids = None

            # [ATOMIC_SYNC_TRANSACTION]: WAL-only — sin sync a cloud aquí
            #
            # ARQUITECTURA: Todos los meses escriben en WAL local (~2ms cada uno).
            # El caller (_batch_bg) ejecuta 1 SOLO conn.sync() al final de la
            # Fase B, después del batch_upsert de asistencia. Esto elimina los
            # bloqueos intermedios de 23-87s por mes.
            #
            # En sync individual (scheduler), el scheduler llama conn.sync()
            # automáticamente dentro de su propio ciclo de 30s.
            if logs_to_save:
                logger.info(f"🚀 Guardando batch de {len(logs_to_save)} nuevas marcaciones en WAL local...")
                success = await turno_repo.save_raw_logs(logs_to_save, suppress_auto_sync=True)
                if not success:
                    self.stats['errores'] += len(logs_to_save)

            # B. Recalcular Asistencia (Independiente por día para liberar el motor)
            if fechas_afectadas and not skip_recalc:
                n_emp = len(empleados_afectados_ids) if empleados_afectados_ids else 'todos'
                logger.info(f"⚡ Recalculando {len(fechas_afectadas)} días × {n_emp} empleados afectados...")
                from backend.services.asistencia_service import AsistenciaService
                from backend.repositories.asistencia import AsistenciaRepository
                
                asist_repo = AsistenciaRepository(db)
                asist_service = AsistenciaService(asist_repo)
                
                for fecha in sorted(list(fechas_afectadas)):
                    try:
                        # Pasar empleados_afectados_ids para acotar el recálculo al batch.
                        # Si es None (fallback), procesa todos como antes.
                        await asist_service.procesar_dia(fecha, empleado_ids=empleados_afectados_ids)
                        self.stats['dias_recalculados'] += 1
                        # Pequeña pausa para permitir que el sync engine de LibSQL respire ante la red
                        await asyncio.sleep(0.1)
                    except Exception as calc_err:
                        logger.error(f"❌ Error recalculando día {fecha}: {calc_err}")
                        self.stats['errores'] += 1
            elif fechas_afectadas and skip_recalc:
                logger.info(f"⏭️ skip_recalc=True → omitiendo recálculo de {len(fechas_afectadas)} días (el caller lo hará)")

            
            # Finalizar
            self.stats['fin'] = datetime.now().isoformat()
            self.stats['duracion_segundos'] = (datetime.now() - start_time).total_seconds()
            self.stats['bloqueados_sin_asig'] = count_gate_blocked
            self.stats['filtrados_area'] = count_filtered
            
            # --- NUEVO: Grabar log de sincronización ---
            try:
                await db.execute("""
                    INSERT INTO sync_logs (fecha_inicio, fecha_fin, tipo_sync, marcaciones_nuevas, dias_recalculados, errores, duracion_segundos, detalle_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.stats['inicio'],
                    self.stats['fin'],
                    'MARCACIONES',
                    self.stats['marcaciones_nuevas'],
                    self.stats['dias_recalculados'],
                    self.stats['errores'],
                    self.stats['duracion_segundos'],
                    json.dumps({"bloqueados_sin_asig": count_gate_blocked, "filtrados_area": count_filtered})
                ))
            except Exception as e_log:
                logger.error(f"Error grabando sync_log (marcaciones): {e_log}")

            logger.success(
                f"✅ Sync Completo: {self.stats['marcaciones_nuevas']} nuevas, "
                f"{count_skipped} duplicadas, "
                f"{count_gate_blocked} bloqueadas por Bioalba Gate (Sin Asignación), "
                f"{self.stats['dias_recalculados']} días recal."
            )
            return self.stats
            
        except Exception as e:
            logger.error(f"❌ Error en sync_marcaciones: {e}")
            self.stats['error_global'] = str(e)
            return self.stats

    async def _sync_empleado(
        self,
        service: EmpleadoService,
        emp_data: Dict[str, Any]
    ) -> None:
        """
        Sincronizar un empleado individual
        
        Args:
            service: Servicio de empleados
            emp_data: Datos del empleado desde BioAlba
        """
        rut = emp_data.get('rut')
        
        if not rut:
            logger.warning("Empleado sin RUT, saltando...")
            self.stats['errores'] += 1
            return

        # Filtrar RUTs inválidos (ej. vacíos)
        if len(rut) < 1:
             logger.warning(f"RUT inválido detectado ({rut}), saltando...")
             # No contamos esto como error crítico, solo lo ignoramos
             return
        
        # Normalizar RUT para búsqueda (quitar puntos y guión para coincidir con BD)
        rut_busqueda = rut.replace(".", "").replace("-", "").strip()
        
        # Verificar si el empleado ya existe usando RUT limpio
        try:
            empleado_existente = await service.repository.get_by_rut(rut_busqueda)
        except Exception:
            empleado_existente = None
        
        if empleado_existente:
            # Recuperar Area ID
            from backend.repositories.area import AreaRepository
            area_repo = AreaRepository(db)
            area_raw = str(emp_data.get('area', '')).strip()
            area_id_res = await area_repo.find_area_id_by_name_or_alias(area_raw) if area_raw and area_raw not in ['---', 'None', 'Sin Asignar'] else None
            
            if area_id_res:
                emp_data['area_id'] = area_id_res
                # También actualizar el virtual si se quiere para consistencia del diff
                area_real = await area_repo.get_area_by_id(area_id_res)
                if area_real:
                    emp_data['area'] = area_real['nombre']
                    
            # Empleado existe, verificar si hay cambios
            cambios = self._detectar_cambios(empleado_existente, emp_data)
            
            if cambios:
                # Detectar específicamente cambio de área para historial
                if 'area' in cambios:
                    nueva_area = cambios['area']
                    area_actual = getattr(empleado_existente, 'area', 'Sin Área')
                    
                    logger.info(f"🚩 DETECTADO CAMBIO DE ÁREA: {empleado_existente.rut} ({area_actual} -> {nueva_area})")
                    
                    # 1. Crear registro PENDIENTE en historial_areas
                    # Evitar duplicados: verificar si ya existe un registro pendiente para esta misma área
                    hist_pendientes = await service.repository.get_historial_areas(empleado_existente.id)
                    ya_existe_pendiente = any(h for h in hist_pendientes if h['area'] == nueva_area and not h['validado'])
                    
                    if not ya_existe_pendiente:
                        logger.info(f"📝 Creando registro de cambio de área PENDIENTE para {empleado_existente.rut}")
                        
                        from backend.repositories.area import AreaRepository
                        area_repo = AreaRepository(db)
                        area_id_val = await area_repo.find_area_id_by_name_or_alias(nueva_area)
                        
                        record_id = await service.repository.add_historial_area(
                            empleado_id=empleado_existente.id,
                            area_id=area_id_val,
                            fecha_desde=datetime.now().strftime("%Y-%m-%d"),
                            es_actual=False, # Aún no es el actual "validado"
                            validado=False   # Requiere acción del usuario
                        )
                    else:
                        logger.debug(f"ℹ️ Cambio de área a {nueva_area} ya tiene un registro pendiente para {empleado_existente.rut}. Ignorando duplicado.")
                        # Buscamos el ID del ya existente para reportarlo en las stats si es necesario
                        record_id = next(h['id'] for h in hist_pendientes if h['area'] == nueva_area and not h['validado'])

                    # Registrar en los resultados para que el frontend pida validación
                    self.stats['cambios_area'].append({
                        'historial_id': record_id,
                        'empleado_id': empleado_existente.id,
                        'nombre': empleado_existente.nombre_completo,
                        'area_anterior': area_actual,
                        'area_nueva': nueva_area
                    })
                
                # Hay cambios, actualizar el modelo de empleado (EXCEPTO el área, que se valida manual)
                for campo, valor in cambios.items():
                    if campo == 'area':
                        continue # El área NO se actualiza aquí, se deja para confirmar-cambio-area
                    setattr(empleado_existente, campo, valor)
                
                await service.repository.update(empleado_existente.id, empleado_existente)
                logger.debug(f"Actualizado empleado {rut}: {list(cambios.keys())}")
                self.stats['empleados_actualizados'] += 1
                
                # --- FAIL-SAFE: Asegurar que tenga historial base si por alguna razón falta ---
                hist = await service.repository.get_historial_areas(empleado_existente.id)
                if not hist:
                    logger.warning(f"⚠️ Empleado {rut} sin historial de área. Creando uno base...")
                    
                    from backend.repositories.area import AreaRepository
                    area_repo = AreaRepository(db)
                    area_id_val = empleado_existente.area_id
                    if not area_id_val and empleado_existente.area:
                        area_id_val = await area_repo.find_area_id_by_name_or_alias(empleado_existente.area)
                        
                    await service.repository.add_historial_area(
                        empleado_id=empleado_existente.id,
                        area_id=area_id_val,
                        fecha_desde=empleado_existente.fecha_ingreso or datetime.now().strftime("%Y-%m-%d"),
                        es_actual=True,
                        validado=True
                    )
            else:
                # No hay cambios
                logger.debug(f"Empleado {rut} sin cambios")
                self.stats['empleados_sin_cambios'] += 1
        else:
            # Empleado nuevo, crear
            try:
                from backend.repositories.area import AreaRepository
                area_repo = AreaRepository(db)
                area_raw = str(emp_data.get('area', '')).strip()
                area_id_res = await area_repo.find_area_id_by_name_or_alias(area_raw) if area_raw and area_raw not in ['---', 'None', 'Sin Asignar'] else None
                area_virtual = emp_data.get('area')
                if area_id_res:
                    area_real = await area_repo.get_area_by_id(area_id_res)
                    if area_real:
                        area_virtual = area_real['nombre']

                empleado_create = EmpleadoCreate(
                    rut=emp_data['rut'],
                    nombre=emp_data.get('nombre', ''),
                    apellido_paterno=emp_data.get('apellido_paterno', ''),
                    apellido_materno=emp_data.get('apellido_materno', ''),
                    cargo=emp_data.get('cargo'),
                    area_id=area_id_res,
                    area=area_virtual,
                    compania=emp_data.get('compania'),
                    email=emp_data.get('email'),
                    telefono=emp_data.get('telefono'),
                    activo=emp_data.get('activo', True),
                    fecha_ingreso=emp_data.get('fecha_ingreso'),
                    fecha_nacimiento=emp_data.get('fecha_nacimiento'),
                    genero=emp_data.get('genero'),
                    tipo_contrato=emp_data.get('tipo_contrato', 'Temporal'),
                    cant_contratos=1
                )
                
                # Crear el empleado
                nuevo_emp = await service.create_empleado(empleado_create)
                
                # Registrar para onboarding obligatorio en el frontend
                # REGLA: empleados inactivos NO entran al flujo de asignación de turno
                if nuevo_emp and nuevo_emp.activo:
                    self.stats['nuevos_detalles'].append({
                        'id': nuevo_emp.id,
                        'nombre': nuevo_emp.nombre_completo,
                        'rut': nuevo_emp.rut
                    })
                elif nuevo_emp and not nuevo_emp.activo:
                    logger.info(
                        f"⏭️ Empleado {nuevo_emp.nombre_completo} sincronizado como INACTIVO — "
                        f"omitido del flujo de onboarding (sin asignación de turno requerida)"
                    )

                self.stats['empleados_nuevos'] += 1
                
                # 2. AL CREAR: Insertar su primer registro histórico (Validado por defecto)
                if nuevo_emp and nuevo_emp.id:
                    await service.repository.add_historial_area(
                        empleado_id=nuevo_emp.id,
                        area_id=nuevo_emp.area_id,
                        fecha_desde=nuevo_emp.fecha_ingreso or datetime.now().strftime("%Y-%m-%d"),
                        es_actual=True,
                        validado=True
                    )
                
            except Exception as e:
                if "Ya existe" in str(e) or "UNIQUE constraint" in str(e):
                    # Si falla por duplicado, intentar recuperar y actualizar
                    logger.warning(f"Conflicto de duplicado para {rut}, intentando actualizar...")
                    try:
                        # Buscar de nuevo (puede que get_by_rut fallara por formato, pero ahora sabemos que está)
                        # Intentar buscar por RUT limpio o con puntos si falló antes
                        emp_existente = await service.repository.get_by_rut(rut)
                        
                        if emp_existente:
                            # Actualizar con la lógica existente
                            cambios = self._detectar_cambios(emp_existente, emp_data)
                            if cambios:
                                for campo, valor in cambios.items():
                                    setattr(emp_existente, campo, valor)
                                await service.repository.update(emp_existente.id, emp_existente)
                                self.stats['empleados_actualizados'] += 1
                            else:
                                self.stats['empleados_sin_cambios'] += 1
                        else:
                            # Si aun así no lo encuentra (raro), reportar error
                            raise e
                    except Exception as upload_err:
                        logger.error(f"Error al actualizar duplicado {rut}: {upload_err}")
                        self.stats['errores'] += 1
                else:
                    raise e

    def _detectar_cambios(self, empleado_existente, emp_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detectar cambios entre empleado existente y datos nuevos
        
        Returns:
            Diccionario con campos que cambiaron y sus nuevos valores
        """
        cambios = {}
        
        # Mapeo de campos
        campos_comparar = {
            'nombre': 'nombre',
            'apellido_paterno': 'apellido_paterno',
            'apellido_materno': 'apellido_materno',
            'cargo': 'cargo',
            'area': 'area',
            'compania': 'compania',
            'email': 'email',
            'telefono': 'telefono',
            'fecha_ingreso': 'fecha_ingreso',
            'activo': 'activo',
            'tipo_contrato': 'tipo_contrato',
            'genero': 'genero',
            'fecha_nacimiento': 'fecha_nacimiento'
        }
        
        for campo_modelo, campo_data in campos_comparar.items():
            valor_existente = getattr(empleado_existente, campo_modelo, None)
            valor_nuevo = emp_data.get(campo_data)
            
            # Lógica especial para 'activo': Priorizar inactividad local
            if campo_modelo == 'activo':
                # Si localmente está inactivo (False) y viene activo (True), NO actualizar.
                # Queremos preservar la desactivación manual local.
                if valor_existente is False and valor_nuevo is True:
                    continue
            
            # Comparar normalizando tipos para evitar falsos positivos:
            # None vs '', 0 vs '0', 'foo' vs 'foo ', tipos mixtos, etc.
            if valor_nuevo is not None:
                val_exist_norm = str(valor_existente or '').strip()
                val_nuevo_norm = str(valor_nuevo or '').strip()
                if val_exist_norm != val_nuevo_norm:
                    cambios[campo_modelo] = valor_nuevo
        
        return cambios
    
    async def test_connection(self) -> bool:
        """
        Probar conexión con BioAlba
        
        Returns:
            True si la conexión funciona
        """
        async with self.scraper:
            return await self.scraper.test_connection()



# Testing
if __name__ == "__main__":
    """Test del servicio de sincronización"""
    import asyncio

    async def test():
        service = SyncService()

        logger.info("🧪 Probando conexión...")
        if await service.test_connection():
            logger.success("✅ Conexión OK")

            logger.info("🔄 Iniciando sincronización...")
            stats = await service.sync_empleados()

            logger.info("📊 Resultados:")
            logger.info(f"  Nuevos: {stats['empleados_nuevos']}")
            logger.info(f"  Actualizados: {stats['empleados_actualizados']}")
            logger.info(f"  Sin cambios: {stats['empleados_sin_cambios']}")
            logger.info(f"  Errores: {stats['errores']}")
            logger.info(f"  Duración: {stats['duracion_segundos']:.2f}s")
        else:
            logger.error("❌ Error de conexión")

    asyncio.run(test())
