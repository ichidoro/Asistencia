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


class CatalogCache:
    """
    Pre-carga catálogos (áreas, cargos, géneros) en memoria con queries bulk.
    Reemplaza cientos de queries individuales por ~5 queries totales.
    Uso:
        cache = await CatalogCache.load(db)
        area_id = cache.find_area_id("BODEGA")
        cargo_id = cache.find_cargo_id("OPERADOR")
        genero_id = cache.find_genero_id("Masculino")
    """
    def __init__(self):
        self._areas_by_name: Dict[str, int] = {}      # nombre -> id
        self._areas_by_alias: Dict[str, int] = {}      # alias -> area_id
        self._areas_by_id: Dict[int, str] = {}          # id -> nombre
        self._cargos_by_name: Dict[str, int] = {}
        self._cargos_by_alias: Dict[str, int] = {}
        self._cargos_by_id: Dict[int, str] = {}
        self._generos_by_name: Dict[str, int] = {}      # nombre_lower -> id

    @classmethod
    async def load(cls, database) -> "CatalogCache":
        """Carga todos los catálogos con 5 queries bulk."""
        cache = cls()
        
        # 1. Áreas (1 query)
        areas = await database.fetch_all("SELECT id, nombre FROM areas")
        for a in areas:
            cache._areas_by_name[a["nombre"]] = a["id"]
            cache._areas_by_id[a["id"]] = a["nombre"]
        
        # 2. Alias de áreas (1 query)
        aliases_a = await database.fetch_all("SELECT alias, area_id FROM areas_alias")
        for al in aliases_a:
            cache._areas_by_alias[al["alias"]] = al["area_id"]
        
        # 3. Cargos (1 query)
        cargos = await database.fetch_all("SELECT id, nombre FROM cargos")
        for c in cargos:
            cache._cargos_by_name[c["nombre"]] = c["id"]
            cache._cargos_by_id[c["id"]] = c["nombre"]
        
        # 4. Alias de cargos (1 query)
        aliases_c = await database.fetch_all("SELECT alias, cargo_id FROM cargos_alias")
        for al in aliases_c:
            cache._cargos_by_alias[al["alias"]] = al["cargo_id"]
        
        # 5. Géneros (1 query)
        generos = await database.fetch_all("SELECT id, nombre FROM cat_generos")
        for g in generos:
            cache._generos_by_name[g["nombre"].lower()] = g["id"]
        
        logger.info(f"⚡ CatalogCache cargado: {len(cache._areas_by_name)} áreas, "
                     f"{len(cache._areas_by_alias)} alias áreas, "
                     f"{len(cache._cargos_by_name)} cargos, "
                     f"{len(cache._cargos_by_alias)} alias cargos, "
                     f"{len(cache._generos_by_name)} géneros (5 queries)")
        return cache
    
    def find_area_id(self, name_or_alias: str) -> Optional[int]:
        """Busca área por nombre o alias — O(1) en memoria."""
        return self._areas_by_name.get(name_or_alias) or self._areas_by_alias.get(name_or_alias)
    
    def find_cargo_id(self, name_or_alias: str) -> Optional[int]:
        """Busca cargo por nombre o alias — O(1) en memoria."""
        return self._cargos_by_name.get(name_or_alias) or self._cargos_by_alias.get(name_or_alias)
    
    def find_genero_id(self, nombre: str) -> Optional[int]:
        """Busca género por nombre — O(1) en memoria."""
        return self._generos_by_name.get(nombre.lower()) if nombre else None
    
    def get_area_name(self, area_id: int) -> Optional[str]:
        """Obtiene nombre de área por ID — O(1) en memoria."""
        return self._areas_by_id.get(area_id)


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
                        if isinstance(area, dict) and 'nombre' in area:
                            areas_set.add(str(area['nombre']).strip())
                        elif hasattr(area, 'nombre'):
                            areas_set.add(str(area.nombre).strip())
                        else:
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

    async def check_guardian_areas(self) -> Dict[str, Any]:
        """
        Guardián de Áreas (Pre-Check): Descarga empleados, extrae áreas, verifica contra DB local.
        Retorna status: requires_confirmation siempre que haya datos, para abrir el unificado Modal de Sincronización.
        OPTIMIZADO: Usa CatalogCache (5 queries bulk) en vez de queries individuales por empleado.
        """
        try:
            logger.info("🛡️ Guardián de Áreas: Verificando integridad de catálogo y preparando selector...")
            
            empleados_bioalba = _get_empleados_cache()
            if empleados_bioalba is None:
                async with self.scraper:
                    empleados_bioalba = await self.scraper.get_empleados()
                if empleados_bioalba:
                    _set_empleados_cache(empleados_bioalba)
            
            if not empleados_bioalba:
                return {"status": "ok"}
            
            await db.connect()
            
            # ⚡ Pre-cargar TODOS los catálogos con 5 queries bulk
            cache = await CatalogCache.load(db)
            
            areas_desconocidas = set()
            areas_conocidas = set()
            areas_conteo = {}
            
            cargos_desconocidos = {}
            cargos_conocidos = set()
            cargos_conocidos_por_area = {}
            generos_desconocidos = set()
            
            # ⚡ Loop sin queries — todo se resuelve en memoria
            for emp_data in empleados_bioalba:
                area_raw = str(emp_data.get('area', '')).strip()
                if area_raw and area_raw not in ['---', 'None']:
                    area_id = cache.find_area_id(area_raw)
                    if not area_id:
                        areas_desconocidas.add(area_raw)
                    else:
                        areas_conocidas.add(area_raw)
                    areas_conteo[area_raw] = areas_conteo.get(area_raw, 0) + 1

                cargo_raw = str(emp_data.get('cargo', '')).strip()
                if cargo_raw and cargo_raw not in ['---', 'None']:
                    cargo_id = cache.find_cargo_id(cargo_raw)
                    if not cargo_id:
                        if cargo_raw not in cargos_desconocidos:
                            cargos_desconocidos[cargo_raw] = set()
                        cargos_desconocidos[cargo_raw].add(area_raw)
                    else:
                        cargos_conocidos.add(cargo_raw)
                        if cargo_raw not in cargos_conocidos_por_area:
                            cargos_conocidos_por_area[cargo_raw] = set()
                        cargos_conocidos_por_area[cargo_raw].add(area_raw)
                        
                genero_raw = str(emp_data.get('genero', '')).strip()
                if genero_raw and genero_raw not in ['---', 'None']:
                    if not cache.find_genero_id(genero_raw):
                        generos_desconocidos.add(genero_raw)
                        
            # Siempre retornamos requires_confirmation para que el Guardián actúe como Selector Principal.
            res = {
                "status": "requires_confirmation",
                "nuevas_areas": sorted(list(areas_desconocidas)),
                "areas_conocidas": sorted(list(areas_conocidas)),
                "nuevas_areas_conteo": areas_conteo,
                "nuevos_cargos": sorted(list(cargos_desconocidos.keys())),
                "nuevos_cargos_por_area": {k: list(v) for k, v in cargos_desconocidos.items()},
                "cargos_conocidos": sorted(list(cargos_conocidos)),
                "cargos_conocidos_por_area": {k: list(v) for k, v in cargos_conocidos_por_area.items()},
                "nuevos_generos": sorted(list(generos_desconocidos))
            }
            
            if areas_desconocidas or cargos_desconocidos or generos_desconocidos:
                logger.warning(f"⚠️ Guardián detectó {len(areas_desconocidas)} áreas, {len(cargos_desconocidos)} cargos y {len(generos_desconocidos)} géneros desconocidos.")
            
            return res
                
        except Exception as e:
            logger.error(f"❌ Error en check_guardian_areas: {e}")
            return {"status": "error", "message": str(e)}


    async def commit_wizard_areas(self, areas: Dict[str, str]) -> Dict[str, Any]:
        from backend.repositories.area import AreaRepository
        await db.connect()
        creadas = []
        async with db.transaction():
            area_repo = AreaRepository(db)
            for area_bioalba, resolucion in areas.items():
                if resolucion == "_IGNORE_":
                    continue
                nombre_local = area_bioalba if resolucion == "_NEW_" else resolucion
                existing = await area_repo.get_area_by_name(nombre_local)
                if existing:
                    area_id = existing['id']
                else:
                    area_id = await area_repo.create_area(nombre_local)
                    creadas.append({"id": area_id, "nombre": nombre_local, "bioalba": area_bioalba})
                
                if area_bioalba != nombre_local:
                    existing_alias_id = await area_repo.find_area_id_by_name_or_alias(area_bioalba)
                    if not existing_alias_id:
                        await area_repo.create_alias(area_bioalba, area_id)
        return {"creadas": creadas}

    async def commit_wizard_cargos(self, cargos: Dict[str, str]) -> Dict[str, Any]:
        from backend.repositories.cargo import CargoRepository
        await db.connect()
        creados = []
        async with db.transaction():
            cargo_repo = CargoRepository(db)
            for cargo_bioalba, resolucion in cargos.items():
                if resolucion == "_IGNORE_":
                    continue
                nombre_local = cargo_bioalba if resolucion == "_NEW_" else resolucion
                existing = await cargo_repo.get_cargo_by_name(nombre_local)
                if existing:
                    cargo_id = existing['id']
                else:
                    cargo_id = await cargo_repo.create_cargo(nombre_local)
                    creados.append({"id": cargo_id, "nombre": nombre_local, "bioalba": cargo_bioalba})
                
                if cargo_bioalba != nombre_local:
                    existing_alias_id = await cargo_repo.find_cargo_id_by_name_or_alias(cargo_bioalba)
                    if not existing_alias_id:
                        await cargo_repo.create_alias(cargo_bioalba, cargo_id)
        return {"creados": creados}

    async def commit_wizard_all(
        self,
        areas: Dict[str, str],
        cargos: Dict[str, str],
        generos: List[str],
        turnos: Dict[str, Optional[int]],
        bonos: Optional[Dict[str, List[int]]] = None
    ) -> Dict[str, Any]:
        """
        Mega-Commit del Wizard de Sincronización.
        Guarda en una sola transacción ACID todas las resoluciones de áreas, cargos, géneros,
        asignaciones de turnos y bonos por área.
        Si cualquier paso falla, se hace rollback automático de todo.
        """
        from backend.repositories.area import AreaRepository
        from backend.repositories.cargo import CargoRepository
        
        await db.connect()
        creados = {"areas": 0, "cargos": 0, "generos": 0, "turnos": 0, "bonos": 0}

        async with db.transaction():
            area_repo = AreaRepository(db)
            cargo_repo = CargoRepository(db)
            
            # 1. AREAS
            for area_bioalba, resolucion in areas.items():
                if resolucion == "_IGNORE_":
                    continue
                nombre_local = area_bioalba if resolucion == "_NEW_" else resolucion
                existing = await area_repo.get_area_by_name(nombre_local)
                if existing:
                    area_id = existing['id']
                else:
                    area_id = await area_repo.create_area(nombre_local)
                    creados["areas"] += 1
                if area_bioalba != nombre_local:
                    existing_alias_id = await area_repo.find_area_id_by_name_or_alias(area_bioalba)
                    if not existing_alias_id:
                        await area_repo.create_alias(area_bioalba, area_id)

            # 2. CARGOS
            for cargo_bioalba, resolucion in cargos.items():
                if resolucion == "_IGNORE_":
                    continue
                nombre_local = cargo_bioalba if resolucion == "_NEW_" else resolucion
                existing = await cargo_repo.get_cargo_by_name(nombre_local)
                if existing:
                    cargo_id = existing['id']
                else:
                    cargo_id = await cargo_repo.create_cargo(nombre_local)
                    creados["cargos"] += 1
                if cargo_bioalba != nombre_local:
                    existing_alias_id = await cargo_repo.find_cargo_id_by_name_or_alias(cargo_bioalba)
                    if not existing_alias_id:
                        await cargo_repo.create_alias(cargo_bioalba, cargo_id)

            # 3. GENEROS
            for genero in generos:
                existente = await db.fetch_one("SELECT id FROM cat_generos WHERE nombre COLLATE NOCASE = ?", (genero,))
                if not existente:
                    await db.execute("INSERT INTO cat_generos (nombre) VALUES (?)", (genero,))
                    creados["generos"] += 1

            # 4. TURNOS (Aditivo: un área puede tener múltiples turnos)
            for area_name, turno_id in turnos.items():
                if not turno_id:
                    continue
                area_id = await area_repo.find_area_id_by_name_or_alias(area_name)
                if area_id:
                    # Verificar si ya existe la relación antes de insertar
                    existing = await db.fetch_one(
                        "SELECT 1 FROM turno_areas WHERE area_id = ? AND turno_id = ?",
                        (area_id, turno_id)
                    )
                    if not existing:
                        await db.execute(
                            "INSERT OR IGNORE INTO turno_areas (area_id, turno_id) VALUES (?, ?)",
                            (area_id, turno_id)
                        )
                        creados["turnos"] += 1
                    else:
                        logger.debug(f"Turno {turno_id} ya asignado a área {area_name} (area_id={area_id})")


            # 5. BONOS POR ÁREA
            if bonos:
                for area_name, bono_ids in bonos.items():
                    area_id = await area_repo.find_area_id_by_name_or_alias(area_name)
                    if area_id:
                        # Limpiar asignaciones anteriores para esta área
                        await db.execute("DELETE FROM area_bonos WHERE area_id = ?", (area_id,))
                        for bono_id in bono_ids:
                            await db.execute(
                                "INSERT OR IGNORE INTO area_bonos (area_id, bono_id) VALUES (?, ?)",
                                (area_id, bono_id)
                            )
                            creados["bonos"] += 1

        logger.info(f"✅ [WizardCommitAll] Transacción exitosa. Creados: {creados}")
        return {"status": "ok", "stats": creados}


    # ELIMINADO: finalize_wizard_sync() — código muerto (80 líneas)
    # Reemplazado por commits progresivos:
    #   commit_wizard_areas(), commit_wizard_cargos(), commit_wizard_turnos()
    # Los bonos son globales y se gestionan desde configuración.

    async def preview_empleados(self, resoluciones_areas: Dict[str, str] = None, selected_cargos: List[str] = None) -> List[Dict[str, Any]]:
        """
        Previsualizar empleados que serán sincronizados.
        Descarga BioAlba, filtra por áreas, y cruza con DB local para identificar nuevos vs existentes.
        Usa cache de módulo (TTL 90s) para no re-descargar si sync ocurre inmediatamente después.
        """
        try:
            logger.info(f"🔍 Generando preview de empleados (áreas en memoria: {resoluciones_areas or 'TODAS'})...")
            
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
            if resoluciones_areas:
                empleados_bioalba = [
                    e for e in empleados_bioalba 
                    if str(e.get('area', '')).strip() in resoluciones_areas and resoluciones_areas[str(e.get('area', '')).strip()] != "_IGNORE_"
                ]

            # Filtrar cargos seleccionados (Whitelist)
            if selected_cargos is not None and len(selected_cargos) > 0:
                empleados_bioalba = [
                    e for e in empleados_bioalba 
                    if str(e.get('cargo', '')).strip() in selected_cargos
                ]
            
            # Cruzar con DB local para detectar nuevos vs existentes
            await db.connect()
            rows = await db.fetch_all("SELECT e.rut, e.nombre, e.apellido_paterno, a.nombre as area, e.activo FROM empleados e LEFT JOIN historial_areas ha ON e.id = ha.empleado_id AND ha.es_actual = 1 AND ha.validado = 1 LEFT JOIN areas a ON ha.area_id = a.id")
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
                
                # Traducir el área de BioAlba a su nombre local si existe en resoluciones
                area_bioalba = str(emp.get('area', 'Sin Asignar')).strip()
                area_local_esperada = resoluciones_areas.get(area_bioalba, area_bioalba) if resoluciones_areas else area_bioalba
                if area_local_esperada == "_NEW_":
                    area_local_esperada = area_bioalba
                
                item = {
                    'rut': emp.get('rut', rut),
                    'nombre': nombre_completo,
                    'area': area_bioalba,
                    'cargo': emp.get('cargo', ''),
                    'es_nuevo': local is None,
                    'activo_local': local['activo'] if local else None,
                    'area_local': local['area'] if local else None,
                    'cambio_area': bool(local and local['area'] and local['area'] != area_local_esperada)
                }
                resultado.append(item)
            
            # Ordenar: nuevos primero, luego por nombre
            resultado.sort(key=lambda x: (not x['es_nuevo'], x['nombre']))
            
            logger.success(f"✅ Preview: {len(resultado)} empleados ({sum(1 for r in resultado if r['es_nuevo'])} nuevos)")
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error en preview: {e}")
            return []

    async def sync_empleados(self, areas: List[str] = None, ruts: List[str] = None, selected_cargos: List[str] = None) -> Dict[str, Any]:
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
                
            # Filtrar por cargos seleccionados (Whitelist)
            if selected_cargos is not None and len(selected_cargos) > 0:
                empleados_bioalba = [
                    e for e in empleados_bioalba 
                    if str(e.get('cargo', '')).strip() in selected_cargos
                ]

            # Filtro ignorados removido, ahora es puro whitelist
            await db.connect()
            repo = EmpleadoRepository(db)
            service = EmpleadoService(repo)
            from backend.repositories.area import AreaRepository
            from backend.repositories.cargo import CargoRepository
            area_repo = AreaRepository(db)
            cargo_repo = CargoRepository(db)
            
            # ⚡ GUARDIÁN DE ÁREAS (OPTIMIZADO con CatalogCache)
            # Pre-cargar todos los catálogos con 5 queries bulk
            cache = await CatalogCache.load(db)
            
            areas_desconocidas = set()
            areas_conocidas = set()
            areas_conteo = {}
            cargos_desconocidos = {}
            cargos_conocidos = set()
            cargos_conocidos_por_area = {}
            generos_desconocidos = set()

            # Preparar set de RUTs seleccionados para el guardián
            ruts_seleccionados = None
            if ruts and len(ruts) > 0:
                ruts_seleccionados = set(
                    r.replace('.', '').replace('-', '').strip().upper() for r in ruts
                )

            # ⚡ Loop sin queries — todo se resuelve en memoria
            for emp_data in empleados_bioalba:
                # Si el usuario seleccionó RUTs específicos, ignorar los demás en el Guardián
                if ruts_seleccionados:
                    emp_rut = str(emp_data.get('rut', '')).replace('.', '').replace('-', '').strip().upper()
                    if emp_rut not in ruts_seleccionados:
                        continue

                area_raw = str(emp_data.get('area', '')).strip()
                
                # Si el usuario seleccionó áreas específicas, el Guardián ignora las demás
                if areas and len(areas) > 0 and area_raw not in areas:
                    continue
                    
                if area_raw and area_raw not in ['---', 'None']:
                    area_id = cache.find_area_id(area_raw)
                    if not area_id:
                        areas_desconocidas.add(area_raw)
                        areas_conteo[area_raw] = areas_conteo.get(area_raw, 0) + 1
                    else:
                        areas_conocidas.add(area_raw)
            
                cargo_raw = str(emp_data.get('cargo', '')).strip()
                if cargo_raw and cargo_raw not in ['---', 'None']:
                    cargo_id = cache.find_cargo_id(cargo_raw)
                    if not cargo_id:
                        if cargo_raw not in cargos_desconocidos:
                            cargos_desconocidos[cargo_raw] = set()
                        cargos_desconocidos[cargo_raw].add(area_raw)
                    else:
                        cargos_conocidos.add(cargo_raw)
                        if cargo_raw not in cargos_conocidos_por_area:
                            cargos_conocidos_por_area[cargo_raw] = set()
                        cargos_conocidos_por_area[cargo_raw].add(area_raw)

                genero_raw = str(emp_data.get('genero', '')).strip()
                if genero_raw and genero_raw not in ['---', 'None']:
                    if not cache.find_genero_id(genero_raw):
                        generos_desconocidos.add(genero_raw)

            if areas_desconocidas or cargos_desconocidos or generos_desconocidos:
                logger.warning(f"⚠️ Guardián detectó {len(areas_desconocidas)} áreas, {len(cargos_desconocidos)} cargos y {len(generos_desconocidos)} géneros desconocidos.")
                res = {"status": "requires_confirmation"}
                if areas_desconocidas:
                    res["nuevas_areas"] = sorted(list(areas_desconocidas))
                    res["nuevas_areas_conteo"] = areas_conteo
                if cargos_desconocidos:
                    res["nuevos_cargos"] = sorted(list(cargos_desconocidos.keys()))
                    res["nuevos_cargos_por_area"] = {k: list(v) for k, v in cargos_desconocidos.items()}
                
                # Agregamos los conocidos también, para poder filtrarlos
                res["cargos_conocidos"] = sorted(list(cargos_conocidos))
                res["cargos_conocidos_por_area"] = {k: list(v) for k, v in cargos_conocidos_por_area.items()}
                res["areas_conocidas"] = sorted(list(areas_conocidas))
                
                if generos_desconocidos:
                    res["nuevos_generos"] = sorted(list(generos_desconocidos))
                return res
            # --------------------------------
            
            if ruts_seleccionados:
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

            # --- AUDITORÍA DE SEGURIDAD (GUARDIÁN DE TURNOS) ---
            # ⚡ OPTIMIZADO: Usa CatalogCache para resolver áreas sin queries
            from backend.repositories.turno import TurnoRepository
            turno_repo = TurnoRepository(db)
            turnos_stats = await turno_repo.get_stats_por_area()
            
            emp_validos = []
            
            for emp_data in emp_filtrados:
                area_raw = str(emp_data.get('area', '')).strip()
                area_id = cache.find_area_id(area_raw)
                real_area_name = cache.get_area_name(area_id) if area_id else None
                
                if real_area_name:
                    turnos_globales = turnos_stats.get('globales', 0)
                    turnos_area = turnos_stats.get('areas', {}).get(real_area_name, 0)
                    if turnos_globales == 0 and turnos_area == 0:
                        logger.warning(f"⚠️ Sincronización bloqueada para {emp_data.get('rut')} porque su área ({real_area_name}) no tiene turnos configurados.")
                        self.stats['errores'] += 1
                        self.stats['detalles_errores'].append(f"{emp_data.get('rut', 'Desconocido')}: Área sin turnos configurados ({real_area_name})")
                        continue
                        
                emp_validos.append(emp_data)
                
            emp_filtrados = emp_validos


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

    async def sync_marcaciones(self, fecha_inicio: str = None, fecha_fin: str = None, areas: List[str] = None, ruts: List[str] = None, force_recalculate: bool = False, skip_recalc: bool = False, deep_sync: bool = False) -> Dict[str, Any]:
        """
        Sincronizar marcaciones de asistencia desde BioAlba y RECALCULAR ASISTENCIA.
        Soporta rangos multi-mes: si fecha_inicio y fecha_fin abarcan más de un mes,
        descarga todos los meses involucrados desde BioAlba.
        ruts: Lista de RUTs limpios (sin puntos/guiones) para filtrar marcaciones individuales.
        force_recalculate: Si es True, recalcula todo el rango incluso si no hay marcas nuevas.
        skip_recalc: Si es True, sólo guarda las marcaciones raw y omite el recálculo de asistencia.
                     Usar cuando el caller realizará el reproceso completo por su cuenta.
        deep_sync: Si es True, fuerza la descarga completa de red de todos los meses sin omitir estables.
        """
        try:
            import calendar
            from datetime import timedelta as _td

            # Helper para invocar el callback de progreso de asistencia
            import inspect as _inspect
            async def _call_cb(event_type: str, data: Dict[str, Any]):
                cb = getattr(self, '_asist_progress_callback', None)
                if cb and _inspect.iscoroutinefunction(cb):
                    await cb(event_type, data)

            await _call_cb('start', {'info': 'Conectando con BioAlba y verificando períodos cerrados...'})

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
                f"meses: {len(meses_a_sincronizar)}, Force Recalc: {force_recalculate}, Deep Sync: {deep_sync})..."
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

            # --- DETECCIÓN DE PERÍODOS CERRADOS ---
            closed_pairs = set()
            try:
                # 1. Consultar cierres en la base de datos
                closures_rows = await db.fetch_all("""
                    SELECT fecha_inicio, fecha_fin, area, turno_id
                    FROM cierres_periodos 
                    WHERE fecha_inicio <= ? AND fecha_fin >= ?
                """, (fecha_fin, fecha_inicio))
                
                rrhh_closures = await db.fetch_all("""
                    SELECT fecha_inicio, fecha_fin
                    FROM periodos_rrhh
                    WHERE estado = 'cerrado' AND fecha_inicio <= ? AND fecha_fin >= ?
                """, (fecha_fin, fecha_inicio))

                # 2. Obtener empleados y sus áreas correspondientes a valid_ruts
                rut_list = list(valid_ruts)
                emp_rows = []
                if rut_list:
                    if len(rut_list) < 900:
                        placeholders = ','.join('?' for _ in rut_list)
                        emp_rows = await db.fetch_all(f"""
                            SELECT e.id, e.rut, e.nombre, e.apellido_paterno, a.nombre as area_nombre
                            FROM empleados e
                            LEFT JOIN areas a ON e.area_id = a.id
                            WHERE REPLACE(REPLACE(e.rut, '.', ''), '-', '') IN ({placeholders})
                        """, tuple(rut_list))
                    else:
                        emp_rows = await db.fetch_all("""
                            SELECT e.id, e.rut, e.nombre, e.apellido_paterno, a.nombre as area_nombre
                            FROM empleados e
                            LEFT JOIN areas a ON e.area_id = a.id
                        """)

                emp_id_to_rut = {}
                emp_id_to_name = {}
                rut_to_current_area = {}
                emp_ids = []
                for r in emp_rows:
                    rut_clean = str(r['rut']).replace('.', '').replace('-', '').strip().upper()
                    emp_id_to_rut[r['id']] = rut_clean
                    emp_id_to_name[r['id']] = f"{r.get('nombre','') or ''} {r.get('apellido_paterno','') or ''}".strip()
                    rut_to_current_area[rut_clean] = r['area_nombre']
                    emp_ids.append(r['id'])

                # Historial de áreas para los empleados involucrados
                emp_history = {}
                if emp_ids:
                    if len(emp_ids) < 900:
                        placeholders = ','.join('?' for _ in emp_ids)
                        hist_rows = await db.fetch_all(f"""
                            SELECT ha.empleado_id, ha.fecha_desde, ha.fecha_hasta, a.nombre as area_nombre
                            FROM historial_areas ha
                            JOIN areas a ON ha.area_id = a.id
                            WHERE ha.validado = 1 AND ha.empleado_id IN ({placeholders})
                        """, tuple(emp_ids))
                    else:
                        hist_rows = await db.fetch_all("""
                            SELECT ha.empleado_id, ha.fecha_desde, ha.fecha_hasta, a.nombre as area_nombre
                            FROM historial_areas ha
                            JOIN areas a ON ha.area_id = a.id
                            WHERE ha.validado = 1
                        """)
                    for h in hist_rows:
                        eid = h['empleado_id']
                        if eid not in emp_history:
                            emp_history[eid] = []
                        emp_history[eid].append({
                            'desde': h['fecha_desde'],
                            'hasta': h['fecha_hasta'],
                            'area': h['area_nombre']
                        })

                # Calcular días en el rango
                dt_ini_c = datetime.strptime(fecha_inicio, "%Y-%m-%d")
                dt_fin_c = datetime.strptime(fecha_fin, "%Y-%m-%d")
                days_in_range = []
                curr_dt = dt_ini_c
                while curr_dt <= dt_fin_c:
                    days_in_range.append(curr_dt.strftime("%Y-%m-%d"))
                    curr_dt += _td(days=1)

                # Días cerrados globalmente (periodos_rrhh)
                globally_closed_days = set()
                for r_c in rrhh_closures:
                    c_start = datetime.strptime(r_c['fecha_inicio'], "%Y-%m-%d")
                    c_end = datetime.strptime(r_c['fecha_fin'], "%Y-%m-%d")
                    curr_c = max(c_start, dt_ini_c)
                    limit_c = min(c_end, dt_fin_c)
                    while curr_c <= limit_c:
                        globally_closed_days.add(curr_c.strftime("%Y-%m-%d"))
                        curr_c += _td(days=1)

                # Cruzar empleados y días
                for emp_id, rut_clean in emp_id_to_rut.items():
                    history = emp_history.get(emp_id, [])
                    curr_area = rut_to_current_area.get(rut_clean)
                    
                    for day_str in days_in_range:
                        if day_str in globally_closed_days:
                            closed_pairs.add((rut_clean, day_str))
                            continue
                            
                        # Determinar área en este día
                        emp_area = None
                        for h in history:
                            desde = h['desde']
                            hasta = h['hasta']
                            if desde <= day_str and (not hasta or day_str <= hasta):
                                emp_area = h['area']
                                break
                        if not emp_area:
                            emp_area = curr_area
                            
                        is_closed = False
                        if emp_area:
                            for cl in closures_rows:
                                is_global_closure = (cl['area'] is None or cl['area'] == '' or cl['area'] == 'Todas')
                                cl_area_upper = str(cl['area'] or '').strip().upper()
                                emp_area_upper = str(emp_area).strip().upper()
                                if (is_global_closure or cl_area_upper == emp_area_upper) and cl['fecha_inicio'] <= day_str <= cl['fecha_fin']:
                                    is_closed = True
                                    break
                        
                        if is_closed:
                            closed_pairs.add((rut_clean, day_str))

                # Early Exit Check (100% cerrado)
                total_combinations = len(valid_ruts) * len(days_in_range)
                if len(closed_pairs) == total_combinations and total_combinations > 0:
                    logger.warning("🚫 [Early Exit] El período seleccionado está completamente cerrado para los empleados y áreas consultadas. Sync cancelado.")
                    self.stats['fin'] = datetime.now().isoformat()
                    self.stats['duracion_segundos'] = (datetime.now() - start_time).total_seconds()
                    self.stats['mensaje'] = "El período seleccionado está completamente cerrado. Sincronización cancelada."
                    return self.stats
                elif len(closed_pairs) > 0:
                    logger.info(f"🛡️ Período parcialmente cerrado: se filtrarán marcaciones para {len(closed_pairs)} de {total_combinations} combinaciones (Empleado x Día).")
            except Exception as e_closure:
                logger.error(f"⚠️ Error al calcular períodos cerrados para sync: {e_closure}. Continuando sin filtros de cierres.")

            # Leer bioalba_dias_volatilidad de la base de datos
            try:
                row_vol = await db.fetch_one("SELECT valor FROM ajustes WHERE clave = 'bioalba_dias_volatilidad'")
                dias_volatilidad = int(row_vol['valor']) if row_vol else 7
            except Exception as e_vol:
                logger.warning(f"⚠️ No se pudo leer bioalba_dias_volatilidad de DB, usando default=7: {e_vol}")
                dias_volatilidad = 7

            # Obtener IDs de empleados correspondientes a valid_ruts para check de logs_raw
            valid_emp_ids = set()
            if valid_ruts:
                try:
                    rut_list = list(valid_ruts)
                    if len(rut_list) < 900:
                        placeholders = ','.join('?' for _ in rut_list)
                        rows_emp = await db.fetch_all(
                            f"SELECT id FROM empleados WHERE REPLACE(REPLACE(rut, '.', ''), '-', '') IN ({placeholders})",
                            tuple(rut_list)
                        )
                    else:
                        rows_emp = await db.fetch_all("SELECT id FROM empleados")
                    valid_emp_ids = {r['id'] for r in rows_emp}
                except Exception as e_emp:
                    logger.warning(f"⚠️ Error obteniendo IDs de empleados para validación de logs_raw: {e_emp}")

            # 2. Descargar marcaciones de BioAlba para CADA MES del rango
            # BioAlba solo expone un Excel mensual, por lo que iteramos.
            marcaciones_bioalba = []
            async with self.scraper:
                for mes_iter, anio_iter in meses_a_sincronizar:
                    # Determinar si el mes es estable (fuera de la ventana de volatilidad)
                    _, last_day = calendar.monthrange(anio_iter, mes_iter)
                    fecha_fin_mes_iter = datetime(anio_iter, mes_iter, last_day)
                    
                    es_estable = False
                    if not ((anio_iter > now.year) or (anio_iter == now.year and mes_iter >= now.month)):
                        if dias_volatilidad == 0:
                            es_estable = True
                        else:
                            limite_volatilidad = fecha_fin_mes_iter + _td(days=dias_volatilidad)
                            hoy_inicio_dia = now.replace(hour=0, minute=0, second=0, microsecond=0)
                            es_estable = limite_volatilidad < hoy_inicio_dia

                    omitir_descarga = False
                    if es_estable and not deep_sync and valid_emp_ids:
                        primer_dia_mes = f"{anio_iter}-{mes_iter:02d}-01"
                        ultimo_dia_mes = f"{anio_iter}-{mes_iter:02d}-{last_day} 23:59:59"
                        
                        try:
                            emp_list = list(valid_emp_ids)
                            if len(emp_list) < 900:
                                placeholders = ','.join('?' for _ in emp_list)
                                query_check = f"SELECT COUNT(*) as count FROM logs_raw WHERE empleado_id IN ({placeholders}) AND fecha_hora >= ? AND fecha_hora <= ?"
                                params = emp_list + [primer_dia_mes, ultimo_dia_mes]
                            else:
                                query_check = "SELECT COUNT(*) as count FROM logs_raw WHERE fecha_hora >= ? AND fecha_hora <= ?"
                                params = [primer_dia_mes, ultimo_dia_mes]
                                
                            res_check = await db.fetch_one(query_check, tuple(params))
                            if res_check and res_check['count'] > 0:
                                omitir_descarga = True
                        except Exception as e_check:
                            logger.warning(f"⚠️ Error verificando logs_raw para el mes {anio_iter}-{mes_iter:02d}: {e_check}")

                    if omitir_descarga:
                        logger.info(f"⏭️ Omitiendo scraping para mes estable: {anio_iter}-{mes_iter:02d} (ya existen marcaciones locales y deep_sync=False)")
                        continue

                    logger.info(f"📥 Descargando BioAlba: {anio_iter}-{mes_iter:02d}...")
                    await _call_cb('progress', {'stage': 'download', 'info': f"Descargando marcaciones de BioAlba para {anio_iter}-{mes_iter:02d}..."})
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
            
            # Obtener el primer turno asignado para cada empleado para el filtro de seguridad
            first_rows = await db.fetch_all("""
                SELECT e.rut, MIN(ast.fecha_inicio) as min_f
                FROM asignacion_turnos ast
                JOIN empleados e ON ast.empleado_id = e.id
                GROUP BY e.rut
            """)
            first_assignments_map = {}
            for r in first_rows:
                r_key = str(r['rut']).replace(".", "").replace("-", "").strip()
                first_assignments_map[r_key] = r['min_f']

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
            count_tipo_invalido = 0
            count_closed_blocked = 0

            # Tipos válidos reconocidos por el motor de asistencia (D8)
            _TIPOS_VALIDOS = {'entrada', 'entry', 'e', 'in', '1', 'salida', 'exit', 's', 'out', '2'}

            # 4. Procesar y Filtrar
            logs_to_save = []
            ruts_afectados = set()  # RUTs que tuvieron marcaciones nuevas en este batch
            for log_data in marcaciones_bioalba:
                try:
                    rut = str(log_data.get('rut', '')).strip()
                    rut_clean = rut.replace(".", "").replace("-", "").strip()
                    
                    # FILTRO 1: Solo empleados sincronizados (comparar RUT limpio vs set limpio)
                    if rut_clean not in valid_ruts:
                        count_filtered += 1
                        continue

                    fecha_hora = log_data.get('fecha_hora')
                    fecha_str = fecha_hora.split(' ')[0] if fecha_hora else None
                    
                    # FILTRO DE PERIODOS CERRADOS
                    if (rut_clean, fecha_str) in closed_pairs:
                        count_closed_blocked += 1
                        continue
                    
                    # REGLA 2+3: BIOALBA GATE — Solo marcaciones con turno activo en esa fecha
                    # Si el empleado no tiene turno asignado O la fecha es anterior a su fecha_inicio,
                    # la marcación se descarta. count_gate_blocked queda para observabilidad en sync_logs.
                    if not fecha_str or rut_clean not in asig_map_gate or fecha_str not in asig_map_gate[rut_clean]:
                        count_gate_blocked += 1
                        continue  # [RFC PASO 1] Descarte estricto: no llega a logs_to_save

                    # Barrera de seguridad adicional: no permitir marcaciones previas al primer turno asignado
                    first_assign_date = first_assignments_map.get(rut_clean)
                    if first_assign_date and fecha_str < first_assign_date:
                        count_gate_blocked += 1
                        continue

                    tipo = log_data.get('tipo')

                    # [D8 SANITIZACIÓN]: Marcas con tipo desconocido no ingresan a logs_raw.
                    # El motor solo reconoce Entrada/Salida. Tipo vacío, nulo o desconocido
                    # corrompería el balance del motor → descarte silencioso.
                    tipo_norm = str(tipo or '').strip().lower()
                    if tipo_norm not in _TIPOS_VALIDOS:
                        count_tipo_invalido += 1
                        logger.debug(
                            f"⚠️ [D8] Marcación descartada: RUT={rut_clean}, "
                            f"fecha={fecha_hora}, tipo='{tipo}' (tipo inválido)"
                        )
                        continue

                    # [ATOMIC_HASH_PROTECTION]: SHA256 Sovereign Hash
                    raw_string = f"{rut}|{fecha_hora}|{tipo or ''}"
                    hash_val = hashlib.sha256(raw_string.encode()).hexdigest()

                    if hash_val in existing_hashes:
                        count_skipped += 1
                        continue  # Skip duplicate

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
                # [FIX-INAS-A] Al sincronizar por ÁREA, solo recalcular empleados que
                # tuvieron marcas NUEVAS en este sync. Procesar todos los empleados (None)
                # sobreescribe estados correctos de empleados DINAMICO_FLEXIBLE cuyos
                # logs están en días adyacentes, generando INASISTENCIA falsas.
                # La regla de negocio: si no hubo marcas nuevas para un empleado,
                # su estado calculado anterior debe respetarse.
                if ruts_afectados:
                    empleados_afectados_ids = {
                        rut_to_emp_id[r] for r in ruts_afectados if r in rut_to_emp_id
                    } or None
                else:
                    # Sin marcas nuevas para nadie → no recalcular (evita trabajo inútil)
                    empleados_afectados_ids = None

            if not logs_to_save and not force_recalculate:
                logger.info("⚡ [No-Op Rápido] No hay marcaciones nuevas y force_recalculate=False. Omitiendo recálculo y finalizando de inmediato.")
                self.stats['fin'] = datetime.now().isoformat()
                self.stats['duracion_segundos'] = (datetime.now() - start_time).total_seconds()
                return self.stats

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

            # B. Recalcular Asistencia (Por empleado sobre todo el período para preservar coherencia de Dinámicos Flexibles)
            if fechas_afectadas and not skip_recalc:
                if empleados_afectados_ids:
                    emp_ids_to_recalc = empleados_afectados_ids
                else:
                    # Fallback: todos los empleados con asignación de turno activa en el período
                    emp_ids_to_recalc = set(rut_to_emp_id.values())

                n_emp = len(emp_ids_to_recalc)
                logger.info(f"⚡ Recalculando período {fecha_inicio} → {fecha_fin} para {n_emp} empleados afectados...")
                await _call_cb('start_recalc', {'total': n_emp})
                from backend.services.asistencia_service import AsistenciaService
                from backend.repositories.asistencia import AsistenciaRepository
                
                asist_repo = AsistenciaRepository(db)
                asist_service = AsistenciaService(asist_repo)
                
                # Pre-cargar feriados del período para el batch
                feriados_batch = {}
                try:
                    from backend.services.calendario_service import CalendarioService
                    cal_svc = CalendarioService()
                    anio_ini = dt_ini.year
                    anio_fin = dt_fin.year
                    for _anio in range(anio_ini, anio_fin + 1):
                        raw = await cal_svc.get_feriados(_anio)
                        feriados_batch.update({f['fecha']: f['descripcion'] for f in raw})
                except Exception as fer_err:
                    logger.warning(f"⚠️ No se pudieron pre-cargar feriados: {fer_err}")
                    feriados_batch = None

                for idx, emp_id in enumerate(sorted(list(emp_ids_to_recalc)), start=1):
                    try:
                        emp_name = emp_id_to_name.get(emp_id, f"ID {emp_id}")
                        await _call_cb('progress', {
                            'stage': 'recalc',
                            'idx': idx,
                            'total': n_emp,
                            'info': f"Recalculando asistencia: {emp_name}",
                            'nombre': emp_name
                        })
                        # Reprocesar el período completo para este empleado
                        await asist_service.reprocesar_periodo_empleado(
                            empleado_id=emp_id,
                            fecha_inicio=fecha_inicio,
                            fecha_fin=fecha_fin,
                            force=force_recalculate,
                            feriados_preloaded=feriados_batch
                        )
                        # Pequeña pausa para permitir que el sync engine de LibSQL respire
                        await asyncio.sleep(0.05)
                    except Exception as calc_err:
                        logger.error(f"❌ Error recalculando empleado {emp_id}: {calc_err}")
                        self.stats['errores'] += 1
                
                self.stats['dias_recalculados'] += len(fechas_afectadas)
            elif fechas_afectadas and skip_recalc:
                logger.info(f"⏭️ skip_recalc=True → omitiendo recálculo de {len(fechas_afectadas)} días (el caller lo hará)")

            # C. VALIDACIÓN DE INTEGRIDAD POST-SYNC
            # Detecta discrepancias: logs_raw tiene marcaciones PERO asistencias dice INASISTENCIA.
            # [FIX-INAS-B] Ampliada para DINAMICO_FLEXIBLE: el motor asigna marcas de días
            # adyacentes (D-1→D+2) como jornada del día D. La query usa UNION para mantener
            # el JOIN exacto para turnos normales y la ventana amplia para DINAMICO_FLEXIBLE.
            if not skip_recalc:
                try:
                    integrity_mismatches = await db.fetch_all("""
                        -- Caso 1: Turnos normales — marcas en el mismo día exacto
                        SELECT DISTINCT a.empleado_id, a.fecha
                        FROM asistencias a
                        INNER JOIN logs_raw lr ON a.empleado_id = lr.empleado_id
                            AND a.fecha = date(lr.fecha_hora)
                        LEFT JOIN turnos t ON a.turno_asignado_id = t.id
                        WHERE a.estado = 'INASISTENCIA'
                          AND a.fecha >= ?
                          AND lr.tipo IN ('Entrada', 'Salida', 'entrada', 'salida', 'entry', 'exit', 'e', 's', 'in', 'out', '1', '2')
                          AND (t.tipo_programacion IS NULL OR t.tipo_programacion != 'DINAMICO_FLEXIBLE')

                        UNION

                        -- Caso 2: DINAMICO_FLEXIBLE — marcas en ventana D-1 a D+2
                        -- El motor asigna estas marcas como jornada del día D aunque
                        -- el timestamp sea de un día adyacente (turno día a día).
                        SELECT DISTINCT a.empleado_id, a.fecha
                        FROM asistencias a
                        INNER JOIN logs_raw lr ON a.empleado_id = lr.empleado_id
                            AND date(lr.fecha_hora) BETWEEN date(a.fecha, '-1 day') AND date(a.fecha, '+2 days')
                        INNER JOIN turnos t ON a.turno_asignado_id = t.id
                            AND t.tipo_programacion = 'DINAMICO_FLEXIBLE'
                        WHERE a.estado = 'INASISTENCIA'
                          AND a.fecha >= ?
                          AND lr.tipo IN ('Entrada', 'Salida', 'entrada', 'salida', 'entry', 'exit', 'e', 's', 'in', 'out', '1', '2')
                    """, (fecha_ini_mes, fecha_ini_mes))
                    
                    if integrity_mismatches:
                        logger.warning(f"🔍 Integridad: {len(integrity_mismatches)} discrepancias detectadas (INASISTENCIA con logs)")
                        
                        # Si no se instanció antes en la rama B, instanciar ahora
                        if 'asist_service' not in locals():
                            from backend.services.asistencia_service import AsistenciaService
                            from backend.repositories.asistencia import AsistenciaRepository
                            asist_repo = AsistenciaRepository(db)
                            asist_service = AsistenciaService(asist_repo)
                            
                        for mismatch in integrity_mismatches[:50]:  # Cap de seguridad
                            try:
                                await asist_service.procesar_dia(
                                    mismatch['fecha'],
                                    empleado_ids={mismatch['empleado_id']}
                                )
                            except Exception as fix_err:
                                logger.error(f"❌ Error corrigiendo {mismatch['empleado_id']}@{mismatch['fecha']}: {fix_err}")
                except Exception as integ_err:
                    logger.error(f"⚠️ Error en validación de integridad: {integ_err}")

            
            # Finalizar
            self.stats['fin'] = datetime.now().isoformat()
            self.stats['duracion_segundos'] = (datetime.now() - start_time).total_seconds()
            self.stats['bloqueados_sin_asig'] = count_gate_blocked
            self.stats['filtrados_area'] = count_filtered
            self.stats['tipo_invalido_descartado'] = count_tipo_invalido
            self.stats['bloqueados_por_cierre'] = count_closed_blocked
            
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
                    json.dumps({
                        "bloqueados_sin_asig": count_gate_blocked, 
                        "filtrados_area": count_filtered,
                        "bloqueados_por_cierre": count_closed_blocked
                    })
                ))
            except Exception as e_log:
                logger.error(f"Error grabando sync_log (marcaciones): {e_log}")

            logger.success(
                f"✅ Sync Completo: {self.stats['marcaciones_nuevas']} nuevas, "
                f"{count_skipped} duplicadas, "
                f"{count_gate_blocked} bloqueadas por Bioalba Gate (Sin Asignación), "
                f"{count_closed_blocked} bloqueadas por Período Cerrado, "
                f"{count_tipo_invalido} descartadas por tipo inválido (D8), "
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
            # Recuperar Area ID y Cargo ID
            from backend.repositories.area import AreaRepository
            from backend.repositories.cargo import CargoRepository
            
            area_repo = AreaRepository(db)
            area_raw = str(emp_data.get('area', '')).strip()
            area_id_res = await area_repo.find_area_id_by_name_or_alias(area_raw) if area_raw and area_raw not in ['---', 'None'] else None
            
            # FALLBACK: Si no se encontró el área, crearla o asignar 'Sin Asignar'
            if not area_id_res:
                nombre_area_nueva = area_raw if area_raw and area_raw not in ['---', 'None'] else 'Sin Asignar'
                area_id_res = await area_repo.find_area_id_by_name_or_alias(nombre_area_nueva)
                if not area_id_res:
                    logger.info(f"Creando área faltante durante sync update: {nombre_area_nueva}")
                    area_id_res = await area_repo.create_area(nombre_area_nueva)

            if area_id_res:
                emp_data['area_id'] = area_id_res
                # También actualizar el virtual si se quiere para consistencia del diff
                area_real = await area_repo.get_area_by_id(area_id_res)
                if area_real:
                    emp_data['area'] = area_real['nombre']
                    
            cargo_repo = CargoRepository(db)
            cargo_raw = str(emp_data.get('cargo', '')).strip()
            cargo_id_res = await cargo_repo.find_cargo_id_by_name_or_alias(cargo_raw) if cargo_raw and cargo_raw not in ['---', 'None'] else None
            
            if cargo_id_res:
                emp_data['cargo_id'] = cargo_id_res
                cargo_real = await cargo_repo.get_cargo_by_id(cargo_id_res)
                if cargo_real:
                    emp_data['cargo'] = cargo_real['nombre']
                    
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
                        
                        if not area_id_val:
                            nombre_area_nueva = nueva_area if nueva_area and nueva_area not in ['---', 'None'] else 'Sin Asignar'
                            logger.info(f"Creando área faltante para historial pendiente: {nombre_area_nueva}")
                            area_id_val = await area_repo.create_area(nombre_area_nueva)

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
                    
                    if not area_id_val:
                        area_id_val = await area_repo.find_area_id_by_name_or_alias('Sin Asignar')
                        if not area_id_val:
                            area_id_val = await area_repo.create_area('Sin Asignar')

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
                from backend.repositories.cargo import CargoRepository
                
                area_repo = AreaRepository(db)
                area_raw = str(emp_data.get('area', '')).strip()
                area_id_res = await area_repo.find_area_id_by_name_or_alias(area_raw) if area_raw and area_raw not in ['---', 'None'] else None
                
                # FALLBACK: Si no se encontró el área, crearla o asignar 'Sin Asignar'
                if not area_id_res:
                    nombre_area_nueva = area_raw if area_raw and area_raw not in ['---', 'None'] else 'Sin Asignar'
                    # Buscar nuevamente por si 'Sin Asignar' ya existe
                    area_id_res = await area_repo.find_area_id_by_name_or_alias(nombre_area_nueva)
                    if not area_id_res:
                        logger.info(f"Creando área faltante durante sync: {nombre_area_nueva}")
                        area_id_res = await area_repo.create_area(nombre_area_nueva)
                
                area_virtual = emp_data.get('area')
                if area_id_res:
                    area_real = await area_repo.get_area_by_id(area_id_res)
                    if area_real:
                        area_virtual = area_real['nombre']

                cargo_repo = CargoRepository(db)
                cargo_raw = str(emp_data.get('cargo', '')).strip()
                cargo_id_res = await cargo_repo.find_cargo_id_by_name_or_alias(cargo_raw) if cargo_raw and cargo_raw not in ['---', 'None'] else None
                cargo_virtual = emp_data.get('cargo')
                if cargo_id_res:
                    cargo_real = await cargo_repo.get_cargo_by_id(cargo_id_res)
                    if cargo_real:
                        cargo_virtual = cargo_real['nombre']

                empleado_create = EmpleadoCreate(
                    rut=emp_data['rut'],
                    nombre=emp_data.get('nombre', ''),
                    apellido_paterno=emp_data.get('apellido_paterno', ''),
                    apellido_materno=emp_data.get('apellido_materno', ''),
                    cargo=cargo_virtual,
                    cargo_id=cargo_id_res,
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
                        'rut': nuevo_emp.rut,
                        'bioalba_data': {
                            'rut': emp_data.get('rut'),
                            'nombre': emp_data.get('nombre'),
                            'apellido_paterno': emp_data.get('apellido_paterno'),
                            'apellido_materno': emp_data.get('apellido_materno'),
                            'cargo': emp_data.get('cargo'),
                            'area': emp_data.get('area'),
                            'compania': emp_data.get('compania'),
                            'email': emp_data.get('email'),
                            'telefono': emp_data.get('telefono'),
                            'genero': emp_data.get('genero'),
                            'fecha_ingreso': emp_data.get('fecha_ingreso')
                        }
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
            'cargo_id': 'cargo_id',
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
