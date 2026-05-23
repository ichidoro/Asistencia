"""
Migración de permisos V2: actualiza la BD existente para reflejar
los 28 permisos del plan V2 (sin permisos transversales, todo en módulos reales).

Ejecutar: python -m backend.scripts.migrate_permisos_v2
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.core.database import db
from loguru import logger


PERMISOS_V2 = [
    # ── Empleados (7) ──
    ('empleados.ver',                'Empleados',      'Ver la lista general de empleados, cumpleaños y turnos asignados (Lectura)'),
    ('empleados.crear',              'Empleados',      'Crear nuevos empleados (Botón "+ Nuevo Empleado")'),
    ('empleados.editar',             'Empleados',      'Editar ficha personal, renovar/gestionar contratos y registrar bajas (desactivaciones)'),
    ('empleados.eliminar',           'Empleados',      'Eliminar de forma permanente empleados y su historial (Icono papelera roja)'),
    ('empleados.reincorporar',       'Empleados',      'Reincorporar y reactivar empleados inactivos (Asistente con BioAlba)'),
    ('empleados.bonos',              'Empleados',      'Ver matriz informativa de bonos asignados (Lectura)'),
    ('empleados.horarios',           'Empleados',      'Asignación masiva/individual de turnos y corrección de fecha inicial'),

    # ── Marcaciones (7) ──
    ('marcaciones.ver',              'Marcaciones',    'Ver la grilla de asistencia, calendarios y filtros'),
    ('marcaciones.editar',           'Marcaciones',    'Editar horas de entrada/salida, relleno masivo, tramos, perdonazo'),
    ('marcaciones.justificar',       'Marcaciones',    'Doble-clic en celda de estado → crear/editar justificación'),
    ('marcaciones.horas_extras',     'Marcaciones',    'Modal de aprobación masiva → aprobar/rechazar horas extras'),
    ('marcaciones.cierre_periodo',   'Marcaciones',    'Botón "Cerrar Período" → sellar mes para liquidación'),
    ('marcaciones.bypass_cierre',    'Marcaciones',    'Desbloquear edición de meses ya cerrados (alto riesgo)'),
    ('marcaciones.sincronizar',      'Marcaciones',    'Botón "Sincronizar" en toolbar → descargar marcaciones y reprocesar'),

    # ── Reportes (4) ──
    ('reportes.ver',                 'Reportes',       'Ver tablas de reporte, gráficos de línea y filtros de período'),
    ('reportes.exportar',            'Reportes',       'Botón "Descargar Excel" → exportar reporte consolidado'),
    ('reportes.reprocesar',          'Reportes',       'Botón "Reprocesar" → disparar motor de cálculo desde reportes'),
    ('reportes.sincronizar',         'Reportes',       'Botón "Sincronizar" → descargar marcaciones desde reportes'),

    # ── Configuración (10) ──
    ('configuracion.ver',            'Configuración',  'Acceso de solo lectura a todas las pestañas de configuración'),
    ('configuracion.horarios',       'Configuración',  'Pestaña Horarios → crear, editar y eliminar turnos'),
    ('configuracion.bonos',          'Configuración',  'Pestaña Bonos → crear, editar y eliminar bonos y pagadores'),
    ('configuracion.justificaciones','Configuración',  'Pestaña Justificaciones → crear, editar y eliminar tipos'),
    ('configuracion.calendario',     'Configuración',  'Pestaña Calendario → gestionar feriados'),
    ('configuracion.correo',         'Configuración',  'Pestaña Correo → configurar SMTP y notificaciones por área'),
    ('configuracion.estados',        'Configuración',  'Pestaña Estados → editar estados de asistencia'),
    ('configuracion.seguridad',      'Configuración',  'Pestaña Seguridad → gestionar usuarios, roles y ver auditoría'),
    ('configuracion.wizard',         'Configuración',  'Botón "Empleados" del header → Wizard de inicialización BioAlba'),
    ('configuracion.sistema',        'Configuración',  'Pestaña Sistema → diagnóstico de BD y modo de conexión'),
]

# Permisos que ya no existen (incluye legado pre-V1 y V1)
PERMISOS_OBSOLETOS = [
    # V1 obsoletos
    'marcaciones.procesar',
    'marcaciones.sincronizar_biometrico',
    'empleados.sincronizar_biometrico',
    'sincronizacion.ejecutar',
    'sistema.diagnostico',
    # Legado pre-V1 (permisos agrupados del diseño original)
    'seguridad.ver',
    'seguridad.editar',
    'bonos.editar',
    'bonos.ver',
    'asistencia.editar',
    'asistencia.ver',
    'asistencia.procesar',
    'horarios.ver',
    'horarios.editar',
    'horas_extras.aprobar',
    'horas_extras.sugerir',
    'configuracion.editar',
]

# Mapeo de permisos antiguos → nuevos para migrar rol_permisos
RENOMBRAMIENTOS = {
    'marcaciones.sincronizar_biometrico': 'marcaciones.sincronizar',
    'empleados.sincronizar_biometrico': 'configuracion.wizard',
    'sincronizacion.ejecutar': 'configuracion.wizard',
    'sistema.diagnostico': 'configuracion.sistema',
    'marcaciones.procesar': None,  # Se elimina sin reemplazo
}


async def migrate():
    await db.connect()
    
    logger.info("🔄 Iniciando migración de permisos a V2...")
    
    # 1. Obtener permisos actuales
    current = await db.fetch_all("SELECT id FROM permisos")
    current_ids = {r['id'] for r in current}
    v2_ids = {p[0] for p in PERMISOS_V2}
    
    logger.info(f"📊 Permisos actuales: {len(current_ids)} | Permisos V2: {len(v2_ids)}")
    
    # 2. Insertar permisos nuevos que no existen
    nuevos = v2_ids - current_ids
    for perm_id, modulo, desc in PERMISOS_V2:
        if perm_id in nuevos:
            await db.execute(
                "INSERT INTO permisos (id, modulo, descripcion) VALUES (?, ?, ?)",
                (perm_id, modulo, desc)
            )
            logger.info(f"  ✅ Nuevo permiso: {perm_id}")
    
    # 3. Actualizar descripciones de permisos existentes
    for perm_id, modulo, desc in PERMISOS_V2:
        if perm_id in current_ids:
            await db.execute(
                "UPDATE permisos SET modulo = ?, descripcion = ? WHERE id = ?",
                (modulo, desc, perm_id)
            )
    logger.info(f"  📝 Descripciones actualizadas para {len(current_ids & v2_ids)} permisos existentes")
    
    # 4. Migrar rol_permisos: renombrar permisos antiguos → nuevos
    for old_perm, new_perm in RENOMBRAMIENTOS.items():
        if new_perm is None:
            continue  # Se elimina sin reemplazo
        
        # Buscar roles que tienen el permiso antiguo
        roles_con_old = await db.fetch_all(
            "SELECT rol_id FROM rol_permisos WHERE permiso_id = ?", (old_perm,)
        )
        for row in roles_con_old:
            rid = row['rol_id']
            # Verificar si ya tiene el nuevo
            existing = await db.fetch_one(
                "SELECT 1 FROM rol_permisos WHERE rol_id = ? AND permiso_id = ?",
                (rid, new_perm)
            )
            if not existing:
                await db.execute(
                    "INSERT INTO rol_permisos (rol_id, permiso_id) VALUES (?, ?)",
                    (rid, new_perm)
                )
                logger.info(f"  🔀 Rol {rid}: {old_perm} → {new_perm}")
    
    # 5. Asegurar que el rol Super Admin (id=1) tenga TODOS los permisos V2
    for perm_id, _, _ in PERMISOS_V2:
        existing = await db.fetch_one(
            "SELECT 1 FROM rol_permisos WHERE rol_id = 1 AND permiso_id = ?", (perm_id,)
        )
        if not existing:
            await db.execute(
                "INSERT INTO rol_permisos (rol_id, permiso_id) VALUES (1, ?)", (perm_id,)
            )
            logger.info(f"  👑 Super Admin: +{perm_id}")
    
    # 6. Eliminar permisos obsoletos de rol_permisos y permisos
    for old_perm in PERMISOS_OBSOLETOS:
        await db.execute("DELETE FROM rol_permisos WHERE permiso_id = ?", (old_perm,))
        await db.execute("DELETE FROM permisos WHERE id = ?", (old_perm,))
        if old_perm in current_ids:
            logger.info(f"  🗑️ Eliminado: {old_perm}")
    
    # 7. Verificación final
    final = await db.fetch_all("SELECT id FROM permisos ORDER BY id")
    final_ids = {r['id'] for r in final}
    
    missing = v2_ids - final_ids
    extra = final_ids - v2_ids
    
    if missing:
        logger.error(f"❌ Permisos faltantes: {missing}")
    if extra:
        logger.warning(f"⚠️ Permisos extra (no en V2): {extra}")
    
    logger.info(f"✅ Migración completada: {len(final_ids)} permisos en BD")
    
    # Mostrar resumen
    sa_perms = await db.fetch_all("SELECT permiso_id FROM rol_permisos WHERE rol_id = 1")
    logger.info(f"👑 Super Admin tiene {len(sa_perms)} permisos")


if __name__ == "__main__":
    asyncio.run(migrate())
