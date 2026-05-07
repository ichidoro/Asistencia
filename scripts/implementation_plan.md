# 🏗️ PLAN MAESTRO DE MIGRACIÓN: `asistencias.HE` → `horas_extras`
## Versión 3.1 — Post-Simulación de Caos v2 (Patches Aplicados)
### Última actualización: 2026-05-04

---

> **OBJETIVO**: Desacoplar la lógica financiera de Horas Extras (HE) de la tabla `asistencias`
> (disciplinaria) hacia una tabla dedicada `horas_extras`, preservando integridad de datos,
> decisiones humanas, consistencia Turso y zero downtime.

---

## 📊 MAPA DE DEPENDENCIAS (TELA DE ARAÑA)

### Archivos que ESCRIBEN datos HE (🔴 Modificar obligatorio)
| Archivo | Líneas | Qué hace |
|---------|--------|----------|
| `repositories/asistencia.py` | 135-201 | `upsert_asistencia`: INSERT/UPDATE `estado_he`, `minutos_extra_bruto`, `minutos_extra_autorizados` |
| `routers/asistencia.py` | 1219-1224 | `batch_aprobar_he`: `UPDATE asistencias SET estado_he=?, minutos_extra_autorizados=?` |
| `services/asistencia_service.py` | 1454-1474 | `_calculate_attendance`: Genera `estado_he = last_state` en resultado |
| `services/asistencia_service.py` | 1295, 1313 | **[PATCH v2]** `last_state` sourcing: Lee `asist_actual.get('estado_he')` → migrar a `horas_extras` |
| `services/asistencia_service.py` | 1350-1369 | Preservación HE: Lee/restaura `estado_he` durante retro-recálculo |
| `services/asistencia_service.py` | 1405-1411 | JE Interceptor: Resetea `estado_he=None`, `minutos_extra_autorizados=0` |

### Archivos que LEEN datos HE (🟠 Redirigir en Fase 4)
| Archivo | Líneas | Query/Campo |
|---------|--------|-------------|
| `services/dashboard_service.py` | 164-166 | `SUM(CASE WHEN a.estado_he='APROBADO'...)` — Embudo HE |
| `services/dashboard_service.py` | **200** | **[PATCH v2]** Ratio KPI: `SUM(a.minutos_extra_autorizados) as total_min_extra` |
| `services/dashboard_service.py` | 274, 288 | `estado IN ('EXTRA','DESBORDE_LEY88','H.E_BOLSA')` + cálculo horas_extras |
| `services/dashboard_analytics.py` | 471-473 | Embudo HE analítico: `estado_he` APROBADO/PENDIENTE/RECHAZADO |
| `services/dashboard_analytics.py` | 546-559 | KPI Fatiga Operativa: `a.minutos_extra_bruto > 30` |
| `services/dashboard_analytics.py` | 717 | Productividad: `SUM(a.minutos_extra_bruto)` |
| `services/dashboard_analytics.py` | 854 | Eficiencia: `COALESCE(a.minutos_extra_bruto,0)/60.0` |
| `services/report_service.py` | 103, 580 | Excel: `dia_data.get("estado_he") == "APROBADO"` |
| `services/asistencia_service.py` | 2315-2333 | **[PATCH v2]** Matrix Builder JE override: Fuerza `minutos_extra_bruto=0` en JE |
| `services/asistencia_service.py` | 2451-2461 | Bolsa: `SUM(minutos_extra_autorizados)` de `asistencias` |
| `services/asistencia_service.py` | 2527-2560 | Cierre Global: `estado_he='APROBADO'` de `asistencias` |
| `repositories/asistencia.py` | 242-250 | `get_asistencias_periodo`: `SELECT a.estado_he` |

### Archivo CRÍTICO de Infraestructura (💀 Actualizar ANTES de Fase 5)
| Archivo | Líneas | Riesgo |
|---------|--------|--------|
| `services/asistencia_service.py` | 796-826 | `_asistencia_fingerprint()` incluye `estado_he`, `minutos_extra_bruto`, `minutos_extra_autorizados`. Si se borran columnas sin actualizar → Turso sync storm |

### Frontend (🔵 Verificar post-Fase 4 — Fachada absorbe cambios)
| Archivo | Funciones | Acción |
|---------|-----------|--------|
| `marcaciones_ui.js` | `openHoraExtraModal()` L1215 | Lee `minutos_extra_bruto` del state |
| `marcaciones_ui.js` | `confirmAprobacionHE()` L1316 | POST `/api/asistencia/aprobar-he-batch/` |
| `marcaciones_ui.js` | `calcularMetricasEmpleado()` L620 | Suma HE aprobadas |
| `marcaciones_ui.js` | Modal batch approve L1400 | Aprobación masiva |
| `marcaciones_ui.js` | **[PATCH v2]** Acumuladores grilla L2745-2758 | Suma bruto/aprobado/rechazado/pendiente |
| `marcaciones_ui.js` | **[PATCH v2]** Color estado HE L3181-3183 | Estilo visual por estado |
| `marcaciones_ui.js` | **[PATCH v2]** Resumen empleado L3350-3353 | `estado_he`, `minutos_extra_bruto`, `minutos_extra_autorizados` |
| `marcaciones_manuales.js` | **[PATCH v2]** Guard HE L129 | `asistJ.minutos_extra_bruto > 0` para mostrar botón |

### Nodos SEGUROS (✅ No requieren cambios)
- `sync_service.py` — No toca HE directamente, llama `procesar_dia()`
- `bono_service.py` — Lee `estado` (no `estado_he`), usa `ESTADOS_PRESENCIA`
- `notification_service.py` — Cero referencias HE

### ⚖️ DECISIONES ARQUITECTÓNICAS RESUELTAS (v2)

> **DECISIÓN 1 — `minutos_extra_bruto`**: Se MANTIENE en `asistencias` como dato calculado
> (no financiero). Solo se eliminan `estado_he` y `minutos_extra_autorizados`. Esto reduce
> la complejidad de Fase 4 y 5 en ~40% (queries de Fatiga, Productividad y Eficiencia NO
> necesitan JOIN con horas_extras).

> **DECISIÓN 2 — Nombres API**: NO se cambian. La fachada del matrix builder mapea
> `h.estado → estado_he`, `h.minutos_autorizados → minutos_extra_autorizados` en el dict.
> Frontend NO necesita cambios de campos.

> **DECISIÓN 3 — Orden de escritura**: En doble-escritura, `horas_extras` se escribe PRIMERO,
> `upsert_asistencia` DESPUÉS. Si legacy falla, al menos la tabla nueva tiene el dato.

### Infraestructura Disponible
- `config.py:142` → `FEATURE_HORAS_EXTRAS: bool = True` (kill switch disponible)
- `main.py:239,263` → Feature flag expuesto al frontend
- `seguridad.py:164-165` → Permisos `horas_extras.sugerir`, `horas_extras.aprobar`

---

## ✅ PRE-FLIGHT CHECKLIST

- [ ] Backup completo de la BD SQLite
- [ ] Verificar SQLite version ≥ 3.35.0 (`SELECT sqlite_version()`)
- [ ] Confirmar Turso soporta `CREATE TABLE` y `ALTER TABLE DROP COLUMN`
- [ ] Screenshot de todos los KPIs del dashboard (línea base)
- [ ] Crear rama git: `feature/migration-horas-extras`
- [ ] Documentar rollback para cada fase
- [ ] `FEATURE_HORAS_EXTRAS` configurado como circuit breaker

---

## 🔵 FASE 1: CREACIÓN (No Destructiva)

### Riesgo: ⬜ NULO
### Objetivo: Crear tabla nueva + fix CASCADE en jornadas_especiales

### Paso 1.1: DDL — Crear tabla `horas_extras`

**Archivo**: `repositories/turno.py` (dentro de `create_tables()`)

```sql
CREATE TABLE IF NOT EXISTS horas_extras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empleado_id INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    minutos_bruto REAL DEFAULT 0,
    minutos_autorizados REAL DEFAULT 0,
    estado TEXT DEFAULT 'PENDIENTE' CHECK(estado IN ('PENDIENTE','APROBADO','RECHAZADO')),
    origen TEXT DEFAULT 'SISTEMA',
    comentario TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (empleado_id) REFERENCES empleados(id) ON DELETE CASCADE,
    UNIQUE(empleado_id, fecha)
);
```

> **DECISIÓN**: `UNIQUE(empleado_id, fecha)` mantiene la misma granularidad 1:1 con asistencias.
> `CHECK` constraint con estados estandarizados (ya regularizados en sesión anterior).

### Paso 1.2: Fix CASCADE en `jornadas_especiales`

**Archivo**: `repositories/turno.py`

```python
# En ensure_columns(), agregar verificación:
# Si jornadas_especiales NO tiene ON DELETE CASCADE, recrear con:
# CREATE TABLE jornadas_especiales_new (..., FOREIGN KEY ... ON DELETE CASCADE)
# INSERT INTO jornadas_especiales_new SELECT * FROM jornadas_especiales
# DROP TABLE jornadas_especiales
# ALTER TABLE jornadas_especiales_new RENAME TO jornadas_especiales
```

### Paso 1.3: Crear repositorio `hora_extra.py`

**Archivo NUEVO**: `repositories/hora_extra.py`

```python
class HoraExtraRepository:
    def __init__(self, db):
        self.db = db

    async def upsert(self, data: dict) -> None:
        """Inserta o actualiza un registro HE."""
        query = """
            INSERT INTO horas_extras (empleado_id, fecha, minutos_bruto, minutos_autorizados, estado, origen, comentario, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(empleado_id, fecha) DO UPDATE SET
                minutos_bruto=excluded.minutos_bruto,
                minutos_autorizados=CASE 
                    WHEN horas_extras.estado IN ('APROBADO','RECHAZADO') THEN horas_extras.minutos_autorizados
                    ELSE excluded.minutos_autorizados
                END,
                estado=CASE
                    WHEN horas_extras.estado IN ('APROBADO','RECHAZADO') THEN horas_extras.estado
                    ELSE excluded.estado
                END,
                updated_at=datetime('now')
        """
        # El CASE en ON CONFLICT ES el Upsert Inteligente:
        # Si un humano ya aprobó/rechazó, NO sobreescribimos su decisión.
        await self.db.execute(query, (...))

    async def aprobar_batch(self, items: list) -> int:
        """Aprueba/rechaza múltiples HE."""
        query = """UPDATE horas_extras SET estado=?, minutos_autorizados=?, updated_at=datetime('now')
                   WHERE empleado_id=? AND fecha=?"""
        await self.db.executemany(query, items)
        return len(items)

    async def get_by_periodo(self, fecha_ini, fecha_fin, empleado_id=None):
        """Lee HE de un periodo."""
        q = "SELECT * FROM horas_extras WHERE fecha BETWEEN ? AND ?"
        params = [fecha_ini, fecha_fin]
        if empleado_id:
            q += " AND empleado_id = ?"
            params.append(empleado_id)
        return await self.db.fetch_all(q, tuple(params))

    async def get_estado_previo(self, empleado_id, fecha):
        """Lee estado previo para preservación de decisiones humanas."""
        row = await self.db.fetch_one(
            "SELECT estado, minutos_autorizados FROM horas_extras WHERE empleado_id=? AND fecha=?",
            (empleado_id, fecha))
        return row
```

### Paso 1.4: Verificación

```sql
-- Confirmar tabla creada
SELECT name FROM sqlite_master WHERE type='table' AND name='horas_extras';
-- Confirmar estructura
PRAGMA table_info(horas_extras);
-- Confirmar CASCADE en JE
SELECT sql FROM sqlite_master WHERE name='jornadas_especiales';
```

### ✅ GATE: Fase 1 completada cuando la tabla existe y la app sigue funcionando sin cambios visibles.

---

## 🟡 FASE 2: DOBLE ESCRITURA + INTELIGENCIA

### Riesgo: 🟠 ALTO
### Objetivo: Escribir en AMBAS tablas simultáneamente. Preservar decisiones humanas.

### 💣 MINAS EN ESTA FASE:
1. **Orden JE → HE**: El interceptor JE DEBE correr ANTES de escribir en `horas_extras`
2. **Preservación**: Leer estado previo de `horas_extras` (nueva), NO de `asistencias`
3. **Batch approve**: Debe hacer dual-write
4. **[PATCH v2] `last_state` sourcing (L1295)**: Debe migrar a leer de `horas_extras` en ESTA fase, no esperar a Fase 4

### Paso 2.1: Inyectar doble-escritura en `procesar_dia_empleado_v2`

**Archivo**: `services/asistencia_service.py` — Después de L1420

**ORDEN OBLIGATORIO de ejecución (INVIOLABLE):**
```
0. [PATCH v2] last_state sourcing: Lee de horas_extras (NO de asistencias)
   he_previo = await self.he_repo.get_estado_previo(empleado_id, fecha)
   last_state = he_previo['estado'] if he_previo else (asist_actual.get('estado_he') if asist_actual else None)
   # Fallback a asistencias durante transición, prioridad a horas_extras
1. _calculate_attendance(last_state=last_state) → genera resultado con estado_he
2. Preservación HE → Lee de horas_extras via he_repo.get_estado_previo()
3. JE Interceptor (L1371-1416) → Si es JE, limpia HE del resultado
4. SI resultado.minutos_extra_bruto > 0 Y NO fue interceptado como JE:
     → he_repo.upsert() [PRIMERO - Decisión 3]
5. upsert_asistencia(resultado) [DESPUÉS - legacy]
```

**Pseudocódigo del cambio en `procesar_dia_empleado_v2` (~L1350):**
```python
# === NUEVA LÓGICA DE PRESERVACIÓN (reemplaza L1350-1369) ===
if resultado and resultado.get('minutos_extra_bruto', 0) > 0:
    # Leer decisión previa de la tabla NUEVA (horas_extras)
    he_previo = await self.he_repo.get_estado_previo(empleado_id, fecha)
    if he_previo and he_previo['estado'] in ('APROBADO', 'RECHAZADO'):
        nuevo_bruto = resultado.get('minutos_extra_bruto', 0)
        if nuevo_bruto > 0:
            resultado['estado_he'] = he_previo['estado']
            if he_previo['estado'] == 'APROBADO':
                resultado['minutos_extra_autorizados'] = min(he_previo['minutos_autorizados'], nuevo_bruto)
            else:
                resultado['minutos_extra_autorizados'] = 0
            resultado['observaciones'] += f"Preservando decisión humana ({he_previo['estado']}). "
        else:
            resultado['estado_he'] = None
            resultado['minutos_extra_autorizados'] = 0

# === JE INTERCEPTOR (sin cambios, L1371-1416) ===
# ... (código existente que limpia HE si es JE) ...

# === DOBLE ESCRITURA (NUEVO, después del interceptor) ===
# [PATCH v2] DECISIÓN 3: horas_extras PRIMERO, legacy DESPUÉS
fue_interceptado_je = resultado.get('estado') in ('LIBRE', 'INASISTENCIA') and 'jornadas_especiales' in (resultado.get('observaciones') or '')
if save and resultado.get('minutos_extra_bruto', 0) > 0 and not fue_interceptado_je:
    await self.he_repo.upsert({
        'empleado_id': empleado_id,
        'fecha': fecha,
        'minutos_bruto': resultado.get('minutos_extra_bruto', 0),
        'minutos_autorizados': resultado.get('minutos_extra_autorizados', 0),
        'estado': resultado.get('estado_he') or 'PENDIENTE',
        'origen': resultado.get('origen', 'SISTEMA'),
    })

# === ESCRITURA LEGACY (DESPUÉS de horas_extras) ===
if save:
    await self.repository.upsert_asistencia(resultado)
```

### Paso 2.2: Dual-write en Batch Approve

**Archivo**: `routers/asistencia.py` — Reemplazar L1219-1224

```python
# ANTES (solo asistencias):
# UPDATE asistencias SET estado_he=?, minutos_extra_autorizados=? WHERE ...

# DESPUÉS (dual-write):
query_legacy = """UPDATE asistencias SET estado_he=?, minutos_extra_autorizados=? WHERE empleado_id=? AND fecha=?"""
query_new = """UPDATE horas_extras SET estado=?, minutos_autorizados=?, updated_at=datetime('now') WHERE empleado_id=? AND fecha=?"""

await db.executemany(query_new, params_list)     # PRIMERO nueva tabla
await db.executemany(query_legacy, params_list)   # DESPUÉS legacy

# Blindaje de cierre ya existe en L1204 ✓
```

### Paso 2.3: Inyectar `he_repo` en `AsistenciaService`

**Archivo**: `services/asistencia_service.py` — Constructor

```python
def __init__(self, repository):
    self.repository = repository
    # NUEVO: Repositorio de Horas Extras para doble-escritura
    from backend.repositories.hora_extra import HoraExtraRepository
    self.he_repo = HoraExtraRepository(repository.db)
```

### Paso 2.4: Verificación de Fase 2

```sql
-- Tras procesar un día con HE:
SELECT * FROM horas_extras WHERE fecha = '2026-05-03' LIMIT 5;
-- Comparar con:
SELECT empleado_id, fecha, minutos_extra_bruto, minutos_extra_autorizados, estado_he 
FROM asistencias WHERE fecha = '2026-05-03' AND minutos_extra_bruto > 0;
-- Los datos DEBEN coincidir
```

**Test de preservación:**
```
1. Aprobar una HE manualmente via UI
2. Forzar recálculo del mismo día
3. Verificar que horas_extras.estado sigue = 'APROBADO'
4. Verificar que asistencias.estado_he sigue = 'APROBADO'
```

### ✅ GATE: Fase 2 completada cuando ambas tablas tienen datos idénticos y la preservación funciona.

---

## 🟢 FASE 3: MIGRACIÓN HISTÓRICA

### Riesgo: 🟡 MEDIO
### Objetivo: Copiar datos HE existentes de `asistencias` → `horas_extras`

### Paso 3.1: Script de migración

**Archivo NUEVO**: `scripts/migrate_he_historical.py`

```sql
INSERT INTO horas_extras (empleado_id, fecha, minutos_bruto, minutos_autorizados, estado, origen, created_at, updated_at)
SELECT 
    empleado_id, 
    fecha, 
    COALESCE(minutos_extra_bruto, 0),
    COALESCE(minutos_extra_autorizados, 0),
    COALESCE(estado_he, 'PENDIENTE'),
    'MIGRACION_HISTORICA',
    datetime('now'),
    datetime('now')
FROM asistencias
WHERE minutos_extra_bruto > 0 OR estado_he IS NOT NULL
ON CONFLICT(empleado_id, fecha) DO NOTHING;
-- DO NOTHING: Si Fase 2 ya escribió el registro (overlap), no sobreescribir
```

### Paso 3.2: Verificación cuantitativa

```sql
-- Conteo origen
SELECT COUNT(*) as total_asist FROM asistencias 
WHERE minutos_extra_bruto > 0 OR estado_he IS NOT NULL;

-- Conteo destino
SELECT COUNT(*) as total_he FROM horas_extras;

-- Deben coincidir (± registros de Fase 2 overlap)

-- Verificación de integridad financiera:
SELECT 
    SUM(COALESCE(minutos_extra_autorizados, 0)) as sum_asist
FROM asistencias WHERE estado_he = 'APROBADO';

SELECT 
    SUM(COALESCE(minutos_autorizados, 0)) as sum_he
FROM horas_extras WHERE estado = 'APROBADO';
-- DEBEN SER IGUALES
```

### ⚠️ RECOMENDACIÓN: Ejecutar fuera de horario laboral por carga de Turso sync.

### ✅ GATE: Fase 3 completada cuando los SUMs coinciden al 100%.

---

## 🟠 FASE 4: REDIRECCIÓN DE LECTURAS

### Riesgo: 🟠 ALTO (Mayor superficie de ataque)
### Objetivo: TODAS las queries SQL y lecturas frontend leen de `horas_extras`

### 💣 MINAS EN ESTA FASE:
1. **15 queries en 5 archivos** — Olvidar una = datos inconsistentes post-Fase 5
2. **KPIs ocultos** — Fatiga Operativa y Productividad no están en queries obvias
3. **Matrix data** — El frontend consume HE vía el matrix endpoint, no directamente

### Paso 4.1: `dashboard_service.py` (4 queries)

**Query 1 — Embudo HE (L160-166):**
```sql
-- ANTES:
SUM(CASE WHEN a.estado_he = 'APROBADO' THEN a.minutos_extra_bruto ELSE 0 END)
-- DESPUÉS:
SUM(CASE WHEN h.estado = 'APROBADO' THEN h.minutos_bruto ELSE 0 END)
-- Agregar: LEFT JOIN horas_extras h ON h.empleado_id = a.empleado_id AND h.fecha = a.fecha
```

**Query 2 — [PATCH v2] Ratio KPI Engine (L200):**
```sql
-- ANTES:
SUM(a.minutos_extra_autorizados) as total_min_extra
-- DESPUÉS:
COALESCE((SELECT SUM(h.minutos_autorizados) FROM horas_extras h
          JOIN empleados e2 ON h.empleado_id = e2.id
          WHERE h.fecha >= ? AND h.fecha <= ? AND e2.activo = 1
          AND h.estado = 'APROBADO'), 0) as total_min_extra
```

**Query 3 — Top HE por Área (L274):**
```sql
-- El filtro a.estado IN ('EXTRA','DESBORDE_LEY88','H.E_BOLSA') se mantiene
-- (es estado de asistencia, no de HE)
-- PERO L288 debe cambiar:
-- ANTES: SUM(CASE WHEN a.horas_trabajadas > a.horas_teoricas ...)
-- DESPUÉS: Leer de horas_extras para el monto real
```

**Query 4 — Embudo corregido (mantener estados masculinos ya regularizados)**

### Paso 4.2: `dashboard_analytics.py` (5 queries)

**Query 1 — Embudo analítico (L471-473):**
```sql
-- Mismo patrón: LEFT JOIN horas_extras h ...
-- Reemplazar a.estado_he → h.estado
-- Reemplazar a.minutos_extra_bruto → h.minutos_bruto
```

**Query 2 — Fatiga Operativa (L546-559):**
```sql
-- ANTES: a.minutos_extra_bruto > 30
-- DESPUÉS: h.minutos_bruto > 30
-- Agregar LEFT JOIN horas_extras h ...
```

**Query 3 — Productividad (L717):**
```sql
-- ANTES: SUM(a.minutos_extra_bruto) as minutos_extra
-- DESPUÉS: COALESCE(SUM(h.minutos_bruto), 0) as minutos_extra
```

**Query 4 — Eficiencia (L854):**
```sql
-- ANTES: COALESCE(a.minutos_extra_bruto, 0)/60.0
-- DESPUÉS: COALESCE(h.minutos_bruto, 0)/60.0
```

**Query 5 — Cross-join JE (L733-740):**
```sql
-- Este ya lee de jornadas_especiales directamente → SIN CAMBIOS
```

### Paso 4.3: `report_service.py` (2 puntos)

**Punto 1 (L103) y Punto 2 (L580):**
```python
# ANTES:
if dia_data.get("estado_he") == "APROBADO":
# DESPUÉS (depende de cómo se arme el matrix):
# Si el matrix ya incluye datos de horas_extras → sin cambios aquí
# Si no → agregar HE al matrix en get_matrix_data_with_projections()
```

> **DECISIÓN CLAVE**: Es más eficiente modificar `get_matrix_data_with_projections()` para que
> incluya datos de `horas_extras` en el dict de cada día. Así TODOS los consumidores del matrix
> (report_service, frontend, bolsa) se actualizan de golpe.

### Paso 4.4: `asistencia_service.py` (2 queries)

**Query 1 — Bolsa de Horas (L2451-2461):**
```python
# ANTES:
rows = await db.fetch_all(
    "SELECT * FROM asistencias WHERE empleado_id=? AND fecha BETWEEN ? AND ?", ...)
total_extra = sum(int(r.get('minutos_extra_autorizados', 0) or 0) for r in rows)

# DESPUÉS:
rows_he = await db.fetch_all(
    "SELECT * FROM horas_extras WHERE empleado_id=? AND fecha BETWEEN ? AND ? AND estado='APROBADO'", ...)
total_extra = sum(int(r.get('minutos_autorizados', 0) or 0) for r in rows_he)
# Deuda sigue leyendo de asistencias (es disciplinaria, no financiera)
rows_deuda = await db.fetch_all(
    "SELECT minutos_deuda FROM asistencias WHERE empleado_id=? AND fecha BETWEEN ? AND ?", ...)
total_deuda = sum(int(r.get('minutos_deuda', 0) or 0) for r in rows_deuda)
```

**Query 2 — Resumen Cierre Global (L2527-2560):**
```sql
-- ANTES:
SUM(CASE WHEN a.estado_he = 'APROBADO' THEN a.minutos_extra_autorizados ELSE 0 END)
-- DESPUÉS:
COALESCE((SELECT SUM(h.minutos_autorizados) FROM horas_extras h 
          WHERE h.fecha BETWEEN ? AND ? AND h.estado = 'APROBADO'
          AND h.empleado_id IN (SELECT id FROM empleados WHERE activo=1)), 0)
```

### Paso 4.5: `repositories/asistencia.py` — `get_asistencias_periodo` (L242-250)

```sql
-- Agregar LEFT JOIN para campos financieros:
SELECT a.*, h.estado as estado_he_new, 
       h.minutos_autorizados as he_auth_new
FROM asistencias a
LEFT JOIN horas_extras h ON h.empleado_id = a.empleado_id AND h.fecha = a.fecha
...
-- [DECISIÓN 1] minutos_extra_bruto se mantiene en asistencias → no necesita JOIN
-- [DECISIÓN 2] Fachada: mapear he_auth_new → minutos_extra_autorizados en el dict
```

### Paso 4.6: **[PATCH v2]** Matrix Builder JE Override (L2315-2333)

**Archivo**: `services/asistencia_service.py`

```python
# El JE override fuerza minutos_extra_bruto=0 y minutos_extra_autorizados=0 para días JE.
# CUIDADO: Si el matrix inyecta datos de horas_extras ANTES del JE override,
# los datos de HE se pierden para días que coinciden con JE.
# ORDEN CORRECTO:
#   1. Cargar asistencias en matrix (incluye minutos_extra_bruto)
#   2. Inyectar datos de horas_extras (estado, minutos_autorizados) → fachada
#   3. Aplicar JE override → solo en días con estado='JORNADA_ESPECIAL'/'EXTRA'
#   4. El override YA pone minutos_extra_autorizados=0 para JE → correcto
```

### Paso 4.7: Frontend — `marcaciones_ui.js`

El frontend NO necesita cambios si el matrix endpoint ya devuelve los campos HE
con los mismos nombres (`minutos_extra_bruto`, `estado_he`, etc.) pero sourced desde
la tabla nueva. La "Fachada" del backend absorbe el cambio.

Si decidimos renombrar campos en el API response:
```javascript
// openHoraExtraModal (L1220): 
const mExtra = asist.minutos_extra_bruto;  // → sin cambio si fachada mantiene nombre
// confirmAprobacionHE (L1329): 
// POST a /api/asistencia/aprobar-he-batch/ → sin cambio, el router hace dual-write
```

### Paso 4.7: Verificación de Fase 4

```
1. Abrir Dashboard → Verificar embudo HE muestra mismos números que screenshot pre-migración
2. Abrir Dashboard Analítico → Verificar Fatiga Operativa, Productividad
3. Generar Excel de periodo → Verificar columna "HE Totales" tiene datos
4. Abrir grilla de marcaciones → Verificar que HE se muestra correctamente
5. Aprobar una HE → Verificar que se refleja en Dashboard inmediatamente
6. Ejecutar cierre de periodo → Verificar resumen de HE coincide
```

### ✅ GATE: Fase 4 completada cuando TODAS las 15 queries leen de `horas_extras` y los números del dashboard coinciden con la línea base.

---

## 🔴 FASE 5: LIMPIEZA DESTRUCTIVA

### Riesgo: 💀 MÁXIMO — SIN RETORNO
### Objetivo: Eliminar columnas HE de `asistencias`, limpiar código legacy

### ⚠️ PRE-REQUISITOS INVIOLABLES:
- [ ] SQLite version ≥ 3.35.0 confirmada
- [ ] Backup completo de la BD
- [ ] Fase 4 Gate pasada al 100%
- [ ] Doble-escritura (Fase 2) desactivada para evitar errores en columnas inexistentes

### 💣 MINAS EN ESTA FASE:
1. **Fingerprint** — DEBE actualizarse ANTES del DROP o Turso explota
2. **LibSQL/Turso** — DROP COLUMN puede comportarse diferente que SQLite vanilla
3. **Sin rollback** — Una vez borradas las columnas, solo el backup puede restaurar

### ORDEN DE EJECUCIÓN (ESTRICTAMENTE SECUENCIAL):

### Paso 5.1: Verificar SQLite Version
```sql
SELECT sqlite_version(); -- Debe retornar ≥ 3.35.0
```

### Paso 5.2: Actualizar Fingerprint
**Archivo**: `services/asistencia_service.py` L796-826

```python
# REMOVER estas 2 líneas del tuple (minutos_extra_bruto SE MANTIENE — Decisión 1):
# record.get('minutos_extra_autorizados'), ← BORRAR  
# record.get('estado_he'),                 ← BORRAR
# MANTENER: record.get('minutos_extra_bruto')  ← dato calculado, no financiero
```

### Paso 5.3: Limpiar `repositories/asistencia.py`

**upsert_asistencia (L135-201):**
- L141: Remover `minutos_extra_autorizados,` del INSERT column list
- L143: Remover `estado_he,` del INSERT column list
- L161: Remover `minutos_extra_autorizados=excluded.minutos_extra_autorizados,` del ON CONFLICT
- L163: Remover `estado_he=excluded.estado_he,` del ON CONFLICT
- L188: Remover `d.get('minutos_extra_autorizados', 0),` del params
- L190: Remover `d.get('estado_he', 'PENDIENTE'),` del params
- **MANTENER**: `minutos_extra_bruto` en INSERT/UPDATE (Decisión 1)

**get_asistencias_periodo (L242-250):**
- Ya usa LEFT JOIN de Fase 4, remover `a.estado_he` y `a.minutos_extra_autorizados` del SELECT
- Mantener `a.minutos_extra_bruto`

### Paso 5.4: Limpiar `services/asistencia_service.py`

**_calculate_attendance (L1471):**
```python
# REMOVER: 'estado_he': last_state,
# REMOVER: 'minutos_extra_autorizados': 0,
# MANTENER: 'minutos_extra_bruto': 0,  ← Se sigue calculando y persistiendo
```

> **[DECISIÓN 1 APLICADA]**: `minutos_extra_bruto` se MANTIENE en `asistencias` como dato calculado.
> Las queries de Fatiga Operativa (L546), Productividad (L717) y Eficiencia (L854) en
> `dashboard_analytics.py` NO necesitan JOIN con `horas_extras` gracias a esta decisión.

**Preservación HE (L1350-1369):**
- Ya fue migrada a leer de `horas_extras` en Fase 2 → Remover todo el bloque legacy

**last_state sourcing (L1295, L1313):**
- [PATCH v2] Ya migrado a `horas_extras` en Fase 2 → Remover fallback a `asist_actual.get('estado_he')`

**JE Interceptor (L1405-1411):**
- Remover líneas que limpian `estado_he` y `minutos_extra_autorizados` de `resultado`
- Mantener limpieza de `minutos_extra_bruto` (se sigue persistiendo)

**Anomalía record (L908-911):**
- L909: Remover `'minutos_extra_autorizados': 0,`
- L911: Remover `'estado_he': None,`
- L908: Mantener `'minutos_extra_bruto': 0,`

**aprobar_horas_extras response (L790):**
- [PATCH v2] Mantener response dict con llaves `estado_he`, `minutos_extra_autorizados`
  (opera sobre jornadas_especiales, no sobre asistencias → no afecta migración)

### Paso 5.5: Limpiar `routers/asistencia.py`

**batch_aprobar_he (L1219-1224):**
- Remover query legacy `UPDATE asistencias SET estado_he=?...`
- Mantener solo `UPDATE horas_extras SET estado=?...`

### Paso 5.6: DROP COLUMNS

```sql
-- Ejecutar en este orden exacto:
-- [DECISIÓN 1] Solo 2 columnas financieras. minutos_extra_bruto SE MANTIENE.
ALTER TABLE asistencias DROP COLUMN estado_he;
ALTER TABLE asistencias DROP COLUMN minutos_extra_autorizados;
```

### Paso 5.7: Sync Turso

```python
# Forzar sync después de DDL destructivo
await db.conn.sync()
```

### Paso 5.8: Actualizar schema check en `turno.py`

**ensure_columns:**
- L215: Remover `("estado_he", "TEXT")` de la lista de columnas esperadas
- L214: Remover `("minutos_extra_autorizados", "INTEGER DEFAULT 0")` de la lista
- L189: Remover `estado_he TEXT,` del CREATE TABLE
- L188: Remover `minutos_extra_autorizados INTEGER DEFAULT 0,` del CREATE TABLE
- **MANTENER**: `minutos_extra_bruto` en schema

### Paso 5.9: Verificación Final

```sql
-- Confirmar columnas eliminadas
PRAGMA table_info(asistencias);
-- No debe aparecer estado_he, minutos_extra_autorizados

-- Confirmar datos intactos en nueva tabla
SELECT COUNT(*) FROM horas_extras;
SELECT SUM(minutos_autorizados) FROM horas_extras WHERE estado = 'APROBADO';

-- Confirmar app funcionando
-- Dashboard, Excel, Grilla, Aprobación HE, Cierre de periodo
```

### ✅ GATE FINAL: Migración completada cuando la app funciona 100% sin columnas HE en asistencias.

---

## 📋 RESUMEN EJECUTIVO

| Fase | Archivos | Riesgo | Rollback |
|------|----------|--------|----------|
| 1. Creación | 3 (+2 nuevos) | ⬜ Nulo | DROP TABLE horas_extras |
| 2. Doble Escritura | 3 | 🟠 Alto | Revertir código, datos en ambas tablas |
| 3. Migración Histórica | 1 (nuevo) | 🟡 Medio | DELETE FROM horas_extras WHERE origen='MIGRACION_HISTORICA' |
| 4. Redirección Lecturas | 5 + frontend | 🟠 Alto | Revertir queries a leer de asistencias |
| 5. Limpieza | 4 + DDL | 💀 Máximo | Solo backup de BD |

**Total**: ~12 archivos, **16 queries SQL** (corregido de 15), ~45 puntos de edición

---

## 🔗 REFERENCIAS CRUZADAS

- [Simulación de Caos v1](file:///C:/Users/danie/.gemini/antigravity/brain/96a727ab-6c91-470a-9532-84ee91b37d9e/artifacts/chaos_simulation_report.md) — 21 nodos, 12 minas terrestres
- [Simulación de Caos v2](file:///C:/Users/danie/.gemini/antigravity/brain/96a727ab-6c91-470a-9532-84ee91b37d9e/artifacts/chaos_simulation_v2.md) — 6 omisiones, 3 conflictos, 3 decisiones resueltas
- Conflicto 1.1 (Estados inconsistentes) — ✅ RESUELTO en sesión anterior
- Regla de negocio JE — ✅ CONFIRMADA como correcta (no es bug)
