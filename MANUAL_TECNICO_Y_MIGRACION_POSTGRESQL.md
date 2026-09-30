# MANUAL DE ARQUITECTURA, DESPLIEGUE ON-PREMISE Y MIGRACIÓN A POSTGRESQL
## Sistema de Control de Asistencia, Operaciones y Portería — AGUACOL SpA

> **Audiencia:** Ingenieros de Software, DevOps, Desarrolladores Backend/Fullstack externos.  
> **Objetivo:** Proporcionar la radiografía técnica integral del software, sus reglas de negocio de misión crítica, la arquitectura de código y el procedimiento paso a paso para migrar la base de datos desde Turso Cloud (LibSQL) a **PostgreSQL 16 On-Premise** alojado en el mismo servidor local junto a la aplicación.

---

## TABLA DE CONTENIDOS
1. [Visión General del Sistema y Reglas de Negocio](#1-visión-general-del-sistema-y-reglas-de-negocio)
2. [Stack Tecnológico y Estructura del Proyecto](#2-stack-tecnológico-y-estructura-del-proyecto)
3. [El Motor de Cálculo: Quantum Matrix Engine (QME)](#3-el-motor-de-cálculo-quantum-matrix-engine-qme)
4. [Catálogo Completo del Modelo de Datos (54 Tablas)](#4-catálogo-completo-del-modelo-de-datos-54-tablas)
5. [Diferencias Críticas de Dialecto: SQLite/LibSQL vs PostgreSQL](#5-diferencias-críticas-de-dialecto-sqlitelibsql-vs-postgresql)
6. [Nueva Capa de Datos: Adaptador PostgreSQL (`asyncpg`)](#6-nueva-capa-de-datos-adaptador-postgresql-asyncpg)
7. [Script de Extracción y Migración ETL de Datos](#7-script-de-extracción-y-migración-etl-de-datos)
8. [Arquitectura de Alojamiento On-Premise (Servidor Local)](#8-arquitectura-de-alojamiento-on-premise-servidor-local)
9. [Manual de Despliegue con Docker Compose](#9-manual-de-despliegue-con-docker-compose)
10. [Manual de Despliegue Bare-Metal (Systemd + Nginx + PostgreSQL)](#10-manual-de-despliegue-bare-metal-systemd--nginx--postgresql)
11. [Variables de Entorno de Producción Local (`.env`)](#11-variables-de-entorno-de-producción-local-env)
12. [Scraper Biométrico, Cron Jobs y Sincronización](#12-scraper-biométrico-cron-jobs-y-sincronización)
13. [Protocolo de Seguridad y Trampas a Evitar](#13-protocolo-de-seguridad-y-trampas-a-evitar)

---

## 1. VISIÓN GENERAL DEL SISTEMA Y REGLAS DE NEGOCIO

El software es una plataforma integral de gestión operacional y laboral para **Aguacol SpA**, una empresa agroindustrial/logística en Chile. El sistema procesa diariamente las marcaciones de reloj control biométrico de más de 98 trabajadores activos bajo normativa estricta de la **Dirección del Trabajo de Chile (DT)**.

### Módulos Principales:
1. **Control de Asistencia y Turnos:**
   - **Ciclo Inteligente (Multi-Semana):** Turnos rotativos complejos (12 turnos) que alternan horarios semanalmente (mañana, tarde, noche) con emparejamiento automático por proximidad de fase circular.
   - **Bolsa Flexible (Transporte / Art. 25 bis):** Choferes de reparto y camiones interurbanos (Turnos 9 y 25). No operan con horario rígido diario sino con **bolsa mensual de horas (180h)** y registro de viajes largos (conducción y descanso).
   - **Artículo 22 (Exentos de Limitación de Jornada):** Registro referencial de presencia sin cobro de atrasos ni horas extras.
2. **Gestión de Horas Extras y Condonaciones:**
   - Aprobación/Rechazo de sobretiempos por jefaturas.
   - Panel de Perdonazos (Condonaciones administrativas): Tipo 1 (Salida), Tipo 2 (Atraso), Tipo 3 (Ambos), Tipo 5 (Cierre de faena).
3. **Control de Portería y Seguridad:**
   - Registro de visitas (cédula de identidad chilena / RUT scan).
   - Préstamo y devolución de llaves maestras con trazabilidad por responsable.
   - Rondas de guardia con escaneo de tags QR/código en ubicaciones críticas y reporte de hallazgos fotográficos.
   - Control de camiones y flota (patentes, odómetro, conductores).
4. **Bono de Producción (4 Productos):**
   - Cálculo mensual de incentivos basado en metas individuales y de línea.

---

## 2. STACK TECNOLÓGICO Y ESTRUCTURA DEL PROYECTO

### Backend:
- **Lenguaje:** Python 3.13 (Async/Await nativo).
- **Framework Web:** FastAPI 0.115+ / Starlette.
- **Servidor ASGI:** Uvicorn con workers asíncronos.
- **Acceso a Datos Actual:** LibSQL / Turso Cloud (driver Rust).
- **Acceso a Datos Destino:** **PostgreSQL 16** con pool asíncrono vía `asyncpg`.
- **Logging:** Loguru con rotación de archivos.
- **Zonas Horarias:** `America/Santiago` con soporte para horario de verano/invierno chileno.

### Frontend:
- **Arquitectura:** Single Page Application (SPA) ligera, servida directamente por FastAPI como archivos estáticos.
- **Tecnologías:** Vanilla JavaScript (ES6+ modular), HTML5, CSS3, Bootstrap 5.3, Bootstrap Icons, SweetAlert2.
- **Módulos React:** Sub-paneles interactivos montados mediante bundle precompilado (`dashboard_react.js`).
- **Cache Busting:** Parametrización por query string dinámico `?v={{ startup_id }}_vX` inyectado por FastAPI en `index.html`.
- **PWA:** Service Worker (`sw.js`) con estrategia de red primero para API y cache-first para tipografías/imágenes.

### Árbol de Directorios:
```
Asistencia/
├── backend/
│   ├── core/                  # Infraestructura base
│   │   ├── config.py          # Configuración Pydantic Settings (.env)
│   │   ├── database.py        # Adaptador de base de datos (A MIGRAR A POSTGRES)
│   │   ├── security.py        # Autenticación JWT y hash bcrypt
│   │   └── events.py          # Ciclo de vida FastAPI (startup / shutdown)
│   ├── models/                # Modelos de dominio
│   ├── repositories/          # 13 Repositorios con queries SQL crudas
│   │   ├── asistencia.py      # CRUD de asistencias y jornadas especiales
│   │   ├── empleado.py        # CRUD empleados y contratos
│   │   ├── turno.py           # Configuración de turnos y rotaciones
│   │   ├── hora_extra.py      # Estados y autorización de sobretiempo
│   │   └── ...
│   ├── services/              # Lógica de negocio pura
│   │   ├── quantum_matrix_engine.py  # MOTOR MATRICIAL CUÁNTICO (CORE)
│   │   ├── asistencia_service.py     # Orquestador de recálculos
│   │   └── ...
│   ├── routers/               # Endpoints REST (18 controladores FastAPI)
│   └── scraper/
│       └── bioalba_scraper.py # Scraper biométrico a Bioalba Cloud
├── frontend/                  # SPA Web
│   ├── index.html             # Shell principal
│   ├── js/                    # Controladores JS (marcaciones_ui.js, etc.)
│   ├── css/                   # Hojas de estilo responsive
│   └── sw.js                  # Service Worker
├── scripts/                   # Scripts de mantenimiento, reprocesos y despliegues
├── Dockerfile                 # Contenedor de aplicación
└── requirements.txt           # Dependencias Python
```

---

## 3. EL MOTOR DE CÁLCULO: QUANTUM MATRIX ENGINE (QME)

> [!IMPORTANT]
> **REGLA DE ORO:** Bajo ninguna circunstancia se debe alterar la formulación matemática de [`quantum_matrix_engine.py`](file:///C:/Users/Daniel_Oteiza_Canale/Desktop/Proyectos_Python/Asistencia/backend/services/quantum_matrix_engine.py). Este motor resuelve paradojas temporales en espacio de Hilbert modular $S^1$ ($Z_{1440}$).

### Componentes Clave:
1. **Dynamic Observation Horizon (`QuantumPhaseTopology`):**
   Maneja la fase continua de 24 horas (0 a 1439 minutos). Determina si un turno cruza medianoche calculando la geodésica más corta en el círculo unitario:
   $$\Delta\theta = (\text{fase}_b - \text{fase}_a) \pmod{1440}$$
2. **Multi-Block Tensor Solver (`MultiBlockTensorSolver`):**
   - Agrupa marcas físicas en bloques de trabajo continuo: $\sum (S_i - E_i)$.
   - Discrimina colación según tiempo pactado vs tiempo real.
   - Detecta jornadas adicionales (+2) y llamados de emergencia por brechas temporales (gaps).
   - **Selector Tensorial de Salida Óptima:** Si un trabajador tiene 1 entrada y múltiples salidas en el día, selecciona la salida cuya fase circular minimice el error cuadrático contra la salida contractual teórica.
3. **Segregación Estricta de Turnos:**
   - **Ciclo Inteligente:** Balance diario estricto:
     $$\text{Saldo Neto} = \text{HE Aprobadas} - \text{TOTAL TNT} - \text{Compensaciones}$$
   - **Bolsa Flexible (Transporte):** Se calcula a mes vencido contra meta (180h). **Queda excluida del cálculo de deuda horaria diaria**.

---

## 4. CATÁLOGO COMPLETO DEL MODELO DE DATOS (54 TABLAS)

La base de datos se estructura en 5 clústeres funcionales:

```mermaid
erDiagram
    EMPLEADOS ||--o{ ASISTENCIAS : tiene
    EMPLEADOS ||--o{ ASIGNACION_TURNOS : asignado
    TURNOS ||--o{ ASIGNACION_TURNOS : define
    TURNOS ||--o{ TURNO_DIAS : compone
    EMPLEADOS ||--o{ HORAS_EXTRAS : genera
    EMPLEADOS ||--o{ JORNADAS_ESPECIALES : registra
    EMPLEADOS ||--o{ JUSTIFICACIONES : solicita
    JUSTIFICACION_TIPOS ||--o{ JUSTIFICACIONES : clasifica
    ASISTENCIAS ||--o{ LOGS_RAW : origina
```

### 1. Tablas de Asistencia y Tiempos (Transaccionales Principales)
| Tabla | Registros Aprox. | Propósito |
| :--- | :---: | :--- |
| `logs_raw` | ~30.000 | Marcaciones biométricas crudas (reloj control). Inmutables. |
| `asistencias` | ~15.000 | Jornadas diarias procesadas por QME (horas trabajadas, atrasos, deudas, colación). |
| `horas_extras` | ~2.500 | Registro de sobretiempos, estado (PENDIENTE, APROBADO, RECHAZADO) y minutos autorizados. |
| `jornadas_especiales` | ~60 | Trabajo en días libres, feriados o cobertura de turnos. |
| `justificaciones` | ~400 | Licencias médicas, permisos administrativos, vacaciones. |
| `justificacion_tipos` | 8 | Catálogo legal de justificaciones (con/sin goce, pagador, días). |
| `intercambios_dias` | ~10 | Permutas 1x1 entre trabajadores aprobadas por supervisores. |
| `compensaciones_he_inasistencia` | ~5 | Cruces donde HE aprobadas compensan inasistencias previas. |
| `cierres_periodos` | ~20 | Cierres mensuales de nómina (congelan datos históricos). |

### 2. Tablas de Estructura Organizacional y Turnos
| Tabla | Registros Aprox. | Propósito |
| :--- | :---: | :--- |
| `empleados` | ~120 | Ficha maestra (RUT, nombres, cargo, área, fecha ingreso, activo). |
| `turnos` | 14 | Configuración general de turnos (Ciclo Inteligente, Bolsa Flexible, Art. 22). |
| `turno_dias` | ~150 | Pauta horaria día a día (Lunes a Domingo) por cada semana del ciclo rotativo. |
| `asignacion_turnos` | ~130 | Historial de asignación de turnos a empleados con vigencia desde/hasta. |
| `areas` | ~10 | Departamentos (Mantención, Planta, Logística, Seguridad, etc.). |
| `cargos` | ~30 | Puestos de trabajo formales. |
| `historial_areas` | ~130 | Trazabilidad de transferencias de trabajadores entre áreas. |
| `feriados` | ~50 | Calendario oficial de feriados nacionales en Chile. |

### 3. Tablas de Seguridad, Portería y Activos
| Tabla | Registros Aprox. | Propósito |
| :--- | :---: | :--- |
| `visitas_registros` | ~250 | Ingresos y salidas de visitas externas y contratistas. |
| `llaves_maestro` | ~15 | Catálogo de llaves de oficinas, talleres y bodegas. |
| `llaves_registros` | ~150 | Registro de entrega y devolución de llaves. |
| `flota_aguacol` | ~20 | Vehículos corporativos (camionetas, camiones). |
| `viajes_largos` | ~15 | Segmentos de ruta de choferes interurbanos (horas manejo y descanso). |
| `porteria_ubicaciones` | ~12 | Puntos de control para rondas nocturnas. |
| `porteria_catalogo_hallazgos` | ~10 | Tipología de incidentes (puerta abierta, fuga de agua, etc.). |

### 4. Tablas de Bonos y Productos
| Tabla | Registros Aprox. | Propósito |
| :--- | :---: | :--- |
| `productos_elaboracion_propia` | ~45 | Catálogo de bidones, botellones, vasos y hielos. |
| `empleado_productos_periodo` | ~300 | Asignación de producción mensual por trabajador. |
| `bonos` y `bono_reglas` | ~10 | Parámetros de calificación y montos a pagar. |

### 5. Tablas de Sistema y Configuración
| Tabla | Registros Aprox. | Propósito |
| :--- | :---: | :--- |
| `usuarios` | ~20 | Cuentas de acceso web (administradores, supervisores, portería). |
| `roles` y `permisos` | ~50 | Matriz RBAC (Role-Based Access Control). |
| `ajustes` | ~40 | Parámetros clave-valor (tolerancias, anclajes, límites de horas). |
| `logs_auditoria` | ~5.000 | Trazabilidad de cada acción ejecutada en el sistema. |
| `sync_logs` | ~12.000 | Bitácora de sincronizaciones con reloj biométrico. |

---

## 5. DIFERENCIAS CRÍTICAS DE DIALECTO: SQLITE/LIBSQL VS POSTGRESQL

Al migrar los repositorios de Python a PostgreSQL, el nuevo programador debe considerar las siguientes transformaciones sintácticas obligatorias:

| Característica | SQLite / Turso LibSQL (Actual) | PostgreSQL 16 (Destino) | Solución Recomendada |
| :--- | :--- | :--- | :--- |
| **Placeholders de Parámetros** | Signo de interrogación `?` | Posicionales `$1, $2, $3...` o `%s` | Utilizar `$1, $2` nativo de `asyncpg` o wrapper automático. |
| **Identificadores Autoincrementales** | `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGSERIAL PRIMARY KEY` o `GENERATED BY DEFAULT AS IDENTITY` | Usar `BIGSERIAL PRIMARY KEY` en DDL. |
| **Fecha y Hora Actual** | `datetime('now')` o `date('now')` | `NOW()` o `CURRENT_TIMESTAMP` | Reemplazar funciones de fecha en SQL. |
| **Aritmética de Fechas** | `date(fecha, '+7 days')` | `fecha + INTERVAL '7 days'` | Usar sintaxis estándar de `INTERVAL`. |
| **Tipos Booleanos** | Enteros `0` o `1` | `BOOLEAN` estricto (`TRUE` / `FALSE`) | Mapear `bool` de Python directamente a `boolean`. |
| **Upsert (On Conflict)** | `ON CONFLICT(a, b) DO UPDATE SET ...` | Idéntico, pero **exige** restricción `UNIQUE(a, b)` explícita | Crear índices únicos explícitos en DDL. |
| **Extracción JSON** | `json_extract(campo, '$.clave')` | Operador nativo `campo->>'clave'` | Convertir columnas JSON a tipo `JSONB`. |
| **Inspección de Esquema** | `PRAGMA table_info(tabla)` | `information_schema.columns` | Reemplazar consultas de metadatos. |
| **Límites y Offsets** | `LIMIT n OFFSET m` | `LIMIT n OFFSET m` | Compatible sin cambios. |

---

## 6. NUEVA CAPA DE DATOS: ADAPTADOR POSTGRESQL (`asyncpg`)

Se debe sustituir la clase `TursoDatabase` en [`backend/core/database.py`](file:///C:/Users/Daniel_Oteiza_Canale/Desktop/Proyectos_Python/Asistencia/backend/core/database.py) por una implementación robusta basada en un pool de conexiones `asyncpg`.

### Implementación Lista para Producción:
```python
"""
PostgresDatabase - Conexión de Alta Concurrencia a PostgreSQL Local vía asyncpg.
Reemplazo directo de TursoDatabase manteniendo la misma firma de métodos.
"""
import asyncpg
import asyncio
from typing import Any, Dict, List, Optional
from loguru import logger
import re

from .config import settings


class PostgresDatabase:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._connected: bool = False

    async def connect(self):
        if self._connected and self.pool:
            return

        dsn = settings.DATABASE_URL  # ej: postgresql://aguacol_user:secreto@localhost:5432/asistencia_db
        try:
            self.pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=5,
                max_size=20,
                max_inactive_connection_lifetime=300.0,
                command_timeout=60.0
            )
            self._connected = True
            logger.info("✅ Conexión establecida con PostgreSQL Local (asyncpg Pool)")
        except Exception as e:
            logger.critical(f"❌ Error fatal conectando a PostgreSQL: {e}")
            raise

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            self._connected = False
            logger.info("👋 Pool de PostgreSQL cerrado")

    def _convert_placeholders(self, query: str) -> str:
        """Convierte placeholders de estilo SQLite '?' a estilo PostgreSQL '$1, $2, ...'"""
        if '?' not in query:
            return query
        parts = query.split('?')
        new_query = []
        for i, part in enumerate(parts[:-1], 1):
            new_query.append(part)
            new_query.append(f"${i}")
        new_query.append(parts[-1])
        return "".join(new_query)

    async def fetch_all(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        query_pg = self._convert_placeholders(query)
        async with self.pool.acquire() as conn:
            records = await conn.fetch(query_pg, *(params or ()))
            return [dict(r) for r in records]

    async def fetch_one(self, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        query_pg = self._convert_placeholders(query)
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(query_pg, *(params or ()))
            return dict(record) if record else None

    async def fetch_val(self, query: str, params: Optional[tuple] = None) -> Any:
        query_pg = self._convert_placeholders(query)
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query_pg, *(params or ()))

    async def execute(self, query: str, params: Optional[tuple] = None) -> str:
        query_pg = self._convert_placeholders(query)
        async with self.pool.acquire() as conn:
            return await conn.execute(query_pg, *(params or ()))

    async def executemany(self, query: str, params_list: List[tuple], suppress_auto_sync: bool = False) -> None:
        query_pg = self._convert_placeholders(query)
        async with self.pool.acquire() as conn:
            await conn.executemany(query_pg, params_list)

    async def get_column_names(self, table_name: str) -> List[str]:
        query = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = $1 
            ORDER BY ordinal_position
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, table_name.lower())
            return [r['column_name'] for r in rows]

    async def sync_to_cloud_explicit(self):
        """En entorno PostgreSQL local no se requiere replicación en la nube."""
        pass
```

---

## 7. SCRIPT DE EXTRACCIÓN Y MIGRACIÓN ETL DE DATOS

Para transferir los datos históricos desde Turso Cloud hacia el nuevo PostgreSQL local sin pérdida de integridad ni inconsistencias en claves foráneas, se debe ejecutar un script ETL estructurado en 3 fases:

1. **Extracción Ordenada:** Lee desde Turso tabla por tabla, priorizando tablas maestras y luego tablas transaccionales.
2. **Generación de DDL en PostgreSQL:** Crea tablas, tipos `BOOLEAN` y restricciones `UNIQUE`.
3. **Carga en Lotes y Ajuste de Secuencias (`setval`):** Inserta los registros y actualiza las secuencias de `BIGSERIAL` al valor máximo existente.

```
┌─────────────────────────────────┐       Extract       ┌─────────────────────────────────┐
│           TURSO CLOUD           │ ──────────────────> │         BUFFER EN MEMORIA       │
│        (SQLite / Hrana)         │                     │        (Tipado y Casts)         │
└─────────────────────────────────┘                     └────────────────┬────────────────┘
                                                                         │ Load
                                                                         ▼
                                                        ┌─────────────────────────────────┐
                                                        │         POSTGRESQL LOCAL        │
                                                        │        (Puertol 5432 LAN)       │
                                                        └─────────────────────────────────┘
```

> **Orden de Inserción Respetando Foreign Keys:**
> 1. `areas`, `cargos`, `roles`, `permisos`, `estados_asistencia`, `justificacion_tipos`, `feriados`, `ajustes`
> 2. `usuarios`, `empleados`, `turnos`, `porteria_ubicaciones`, `flota_aguacol`, `llaves_maestro`
> 3. `turno_dias`, `turno_areas`, `asignacion_turnos`, `historial_areas`, `rol_permisos`
> 4. `logs_raw` (29.000+ filas), `justificaciones`, `visitas_registros`, `llaves_registros`
> 5. `asistencias` (14.000+ filas), `horas_extras`, `jornadas_especiales`, `intercambios_dias`
> 6. `cierres_periodos`, `sync_logs`, `logs_auditoria`

---

## 8. ARQUITECTURA DE ALOJAMIENTO ON-PREMISE (SERVIDOR LOCAL)

En el nuevo servidor físico local (ej. Mini-PC, Servidor Torre o Servidor Rack dedicado con Linux Ubuntu 24.04 LTS), se alojará toda la infraestructura:

```
                               RED LOCAL (LAN EMPRESA)
  ┌─────────────────────────┐    ┌─────────────────────────┐    ┌─────────────────────────┐
  │   Relojes Biométricos   │    │  Terminales de Oficina  │    │   Tablet de Portería    │
  │     (IPs en Planta)     │    │     (Supervisores)      │    │        (Guardia)        │
  └────────────┬────────────┘    └────────────┬────────────┘    └────────────┬────────────┘
               │                              │                              │
               └───────────────────────┐      │      ┌───────────────────────┘
                                       ▼      ▼      ▼
                        ┌───────────────────────────────────────────┐
                        │        SERVIDOR LOCAL ON-PREMISE          │
                        │             (IP FIJA: LAN)                │
                        │                                           │
                        │   ┌───────────────────────────────────┐   │
                        │   │        NGINX REVERSE PROXY        │   │
                        │   │        (Puertos 80 y 443)         │   │
                        │   └─────────────────┬─────────────────┘   │
                        │                     │                     │
                        │         ┌───────────┴───────────┐         │
                        │         ▼                       ▼         │
                        │   ┌───────────┐           ┌───────────┐   │
                        │   │  FASTAPI  │           │ POSTGRES  │   │
                        │   │  BACKEND  │ ◄───────► │    16     │   │
                        │   │  (Uvicorn)│           │ (Puerto   │   │
                        │   │  Port 8000│           │   5432)   │   │
                        │   └───────────┘           └───────────┘   │
                        └───────────────────────────────────────────┘
```

### Especificaciones Recomendadas del Servidor Físico:
- **CPU:** 4 a 8 núcleos (Intel Core i5/i7 o AMD Ryzen / Xeon).
- **RAM:** 16 GB DDR4/DDR5 (8 GB asignados a PostgreSQL y OS, 4 GB a FastAPI/Python).
- **Almacenamiento:** SSD NVMe de 500 GB o 1 TB (I/O rápido para PostgreSQL).
- **Red:** Tarjeta de red Gigabit con **IP estática local** (ej: `192.168.1.100`).
- **UPS / Respaldo Eléctrico:** Obligatorio para evitar corrupciones de escritura ante cortes de luz.

---

## 9. MANUAL DE DESPLIEGUE CON DOCKER COMPOSE (MÉTODO RECOMENDADO)

Este método aísla dependencias, garantiza inicio automático al encender el servidor y facilita respaldos.

### Archivo `docker-compose.yml`:
```yaml
version: '3.8'

services:
  db:
    image: postgres:16-alpine
    container_name: aguacol_postgres
    restart: always
    environment:
      POSTGRES_DB: asistencia_db
      POSTGRES_USER: aguacol_admin
      POSTGRES_PASSWORD: TuPasswordSuperSeguro2026!
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - pgdata_volume:/var/lib/postgresql/data
      - ./backups:/backups
    ports:
      - "127.0.0.1:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U aguacol_admin -d asistencia_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  app:
    build: .
    container_name: aguacol_app
    restart: always
    depends_on:
      db:
        condition: service_healthy
    env_file:
      - .env
    environment:
      - DATABASE_URL=postgresql://aguacol_admin:TuPasswordSuperSeguro2026!@db:5432/asistencia_db
      - APP_ENV=production
      - API_HOST=0.0.0.0
      - API_PORT=8000
    ports:
      - "8000:8000"
    volumes:
      - ./logs:/app/logs
      - ./downloads:/app/downloads

  nginx:
    image: nginx:alpine
    container_name: aguacol_nginx
    restart: always
    depends_on:
      - app
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro

volumes:
  pgdata_volume:
    name: aguacol_pgdata
```

---

## 10. MANUAL DE DESPLIEGUE BARE-METAL (SYSTEMD + NGINX)

Si el servidor correrá sobre Linux Ubuntu nativo sin contenedores:

### 1. Servicio Systemd (`/etc/systemd/system/asistencia.service`):
```ini
[Unit]
Description=Sistema Asistencia Aguacol FastAPI
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=operaciones
WorkingDirectory=/opt/Asistencia
EnvironmentFile=/opt/Asistencia/.env
ExecStart=/opt/Asistencia/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 2. Configuración de Nginx (`/etc/nginx/sites-available/asistencia`):
```nginx
server {
    listen 80;
    server_name 192.168.1.100 asistencia.aguacol.local;

    client_max_body_size 50M;

    # Archivos estáticos de frontend
    location /static/ {
        alias /opt/Asistencia/frontend/;
        expires 7d;
        add_header Cache-Control "public, no-transform";
    }

    # API y páginas dinámicas
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

---

## 11. VARIABLES DE ENTORNO DE PRODUCCIÓN LOCAL (`.env`)

Cree un archivo `.env` en la raíz del proyecto con la siguiente configuración:

```ini
# ============================================
# CONFIGURACIÓN BÁSICA DEL SISTEMA
# ============================================
APP_NAME="Sistema de Gestión de Asistencia - AGUACOL"
APP_VERSION="5.0.0-onpremise"
APP_ENV="production"
DEBUG=false
TIMEZONE="America/Santiago"
API_HOST="0.0.0.0"
API_PORT=8000
API_RELOAD=false

# ============================================
# BASE DE DATOS LOCAL POSTGRESQL (NUEVA)
# ============================================
DATABASE_URL="postgresql://aguacol_admin:TuPasswordSuperSeguro2026!@localhost:5432/asistencia_db"
PGHOST="localhost"
PGPORT=5432
PGUSER="aguacol_admin"
PGPASSWORD="TuPasswordSuperSeguro2026!"
PGDATABASE="asistencia_db"

# ============================================
# SEGURIDAD Y TOKENS JWT
# ============================================
SECRET_KEY="generar_cadena_hex_segura_de_64_caracteres_con_openssl"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=480

# ============================================
# SINCRONIZACIÓN Y SCRAPER BIOALBA
# ============================================
SCRAPER_ENABLED=true
CONTROL_ASISTENCIA_URL="https://bioalba1.controlasistencia.cl"
CONTROL_ASISTENCIA_USER="aguacol"
CONTROL_ASISTENCIA_PASSWORD="tu_password_bioalba"
CRON_SECRET="secreto_para_disparar_sync_desde_curl_o_cron_local"

# ============================================
# NOTIFICACIONES CORREO SMTP
# ============================================
FEATURE_NOTIFICACIONES_EMAIL=true
SMTP_SERVER="smtp.gmail.com"
SMTP_PORT=587
SMTP_USER="operaciones.aguacol.spa@gmail.com"
SMTP_PASSWORD="app_password_de_google"
EMAIL_FROM="operaciones.aguacol.spa@gmail.com"

# ============================================
# GOOGLE DRIVE BACKUPS (OPCIONAL EN LOCAL)
# ============================================
GOOGLE_DRIVE_FOLDER_ID="1Y3YeLP9l1O5IZdLVlvCDqUjfLRehv_Rp"
```

---

## 12. SCRAPER BIOMÉTRICO, CRON JOBS Y SINCRONIZACIÓN

El sistema captura marcaciones desde los relojes biométricos a través de la API/Portal de Bioalba.

### Tarea Programada (Crontab en Linux):
Para sincronizar automáticamente cada 15 minutos en el servidor local:
```bash
# Editar crontab del servidor
crontab -e

# Agregar línea para ejecutar sincronización automática
*/15 * * * * curl -X POST "http://127.0.0.1:8000/api/sync/run?secret=secreto_para_disparar_sync_desde_curl_o_cron_local" >> /opt/Asistencia/logs/cron_sync.log 2>&1
```

---

## 13. PROTOCOLO DE SEGURIDAD Y TRAMPAS A EVITAR

Para el desarrollador que asuma el mantenimiento:

1. ⚠️ **Jamás reintroducir prorrateos en el balance:**
   Las columnas `minutos_atraso`, `minutos_salida_adelantada`, `minutos_exceso_colacion` y `minutos_permiso_personal_deuda` en `frontend/js/marcaciones_ui.js` deben sumar directamente la realidad de reloj menos condonaciones. Nunca usar factores como `factor = baseDeuda / rawTotal`.
2. ⚠️ **Aislamiento de Choferes:**
   Los turnos 9 y 25 (Bolsa Flexible) nunca deben someterse a cálculo de atrasos diarios ni deudas diarias. Se rigen por meta mensual de 180 horas.
3. ⚠️ **Respaldo Automático Diario de PostgreSQL:**
   Implementar una rutina `pg_dump` diaria programada en crontab que conserve respaldos en un disco secundario o NAS de la empresa:
   ```bash
   0 2 * * * pg_dump -U aguacol_admin asistencia_db | gzip > /backups/asistencia_$(date +\%Y\%m\%d).sql.gz
   ```
4. ⚠️ **Preservar Decisiones Humanas:**
   En cualquier re-cálculo masivo, las horas extras en estado `APROBADO` o `RECHAZADO`, las justificaciones y las condonaciones manuales (`deuda_condonada`) tienen prioridad absoluta y jamás deben ser sobrescritas por el cálculo algorítmico.
