# MANUAL TÉCNICO DE ARQUITECTURA, INSTALACIÓN Y MIGRACIÓN A SERVIDOR LOCAL
## Sistema de Control de Asistencia y Gestión Operacional — Aguacol SPA
**Versión del Sistema:** 4.7.2  
**Fecha de Elaboración:** Septiembre 2026  
**Destinatario:** Ingeniero / Desarrollador de Software Externo  

---

## 1. RESUMEN EJECUTIVO Y FICHA TÉCNICA

El **Sistema de Control de Asistencia y Gestión Operacional Aguacol** es una plataforma integral de misión crítica diseñada para la gestión biométrica, liquidación horaria, control de acceso de portería, asignación de flota de transporte y cálculo de remuneraciones horarias bajo la legislación laboral chilena (Código del Trabajo, Artículos 22 y 25 bis).

### Ficha Técnica
| Parámetro | Especificación |
| :--- | :--- |
| **Lenguaje Backend** | Python 3.11+ / Python 3.13 (Asyncio nativo) |
| **Framework Web** | FastAPI 0.128+ con servidor ASGI Uvicorn |
| **Motor de Base de Datos** | LibSQL / SQLite (Soporta Servidor `sqld` en Docker o archivo `.db` local en modo WAL) |
| **Frontend** | Single Page Application (SPA) con HTML5, Vanilla JavaScript ES6+, Bootstrap 5.3, Bootstrap Icons, Chart.js, jsPDF y React embebido (`dashboard_react.js`) |
| **Protocolo en Tiempo Real** | WebSockets nativos para sincronización de marcaciones y estados |
| **Tareas de Fondo** | APScheduler (AsyncIOScheduler) para scraping, rolling sync de feriados y mantenimiento |
| **Scraper Integrado** | Motor de extracción web con requests / BeautifulSoup4 contra reloj biométrico BioAlba |
| **Integraciones Externas** | Google Drive API v3 (evidencias de portería), SMTP Gmail (notificaciones) |
| **Puertos de Red** | `8000` (Backend FastAPI & Assets Frontend), `8080` (Base de datos si se usa `sqld` Docker), `80/443` (Reverse Proxy Nginx) |

---

## 2. ARQUITECTURA GENERAL DEL SISTEMA

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                CLIENTES / NAVEGADORES WEB                              │
│                (Computadores Administrativos, Portería, Móviles de Supervisión)        │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ HTTP / HTTPS (Puerto 80/443)
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              REVERSE PROXY (NGINX / CADDY)                             │
│                  - Terminación SSL/TLS                                                 │
│                  - Proxy Pass WebSocket (/ws) & HTTP -> 127.0.0.1:8000                 │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          FASTAPI APPLICATION (PUERTO 8000)                             │
│                                                                                        │
│  ┌───────────────────────┐  ┌────────────────────────┐  ┌───────────────────────────┐  │
│  │   ROUTERS / ENDPOINTS │  │   SERVICIOS DE NEGOCIO │  │   SCHEDULER (APSCHEDULER) │  │
│  │   • /api/asistencia   │  │   • AsistenciaService  │  │   • Scraping BioAlba (60m)│  │
│  │   • /api/turnos       │  │   • QuantumMatrixEngine│  │   • Sync Feriados (12h)   │  │
│  │   • /api/empleados    │  │   • ReportService      │  │   • Purga Auditoría (7d)  │  │
│  │   • /api/porteria     │  │   • CierreService      │  │   • Recálculo de Arranque │  │
│  │   • /api/flota        │  │   • BonoService        │  └───────────────────────────┘  │
│  └───────────────────────┘  └────────────────────────┘                                 │
│                                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │                     DATA ACCESS LAYER (REPOSITORIOS ASYNC)                       │  │
│  │  • AsistenciaRepo  • TurnoRepo  • EmpleadoRepo  • PorteriaRepo  • SeguridadRepo  │  │
│  └────────────────────────────────────────┬─────────────────────────────────────────┘  │
└───────────────────────────────────────────┼────────────────────────────────────────────┘
                                            │
                      ┌─────────────────────┴─────────────────────┐
                      ▼                                           ▼
┌───────────────────────────────────────────┐   ┌────────────────────────────────────────┐
│       BASE DE DATOS LOCAL SERVIDOR        │   │        INTEGRACIONES EXTERNAS          │
│   Opción A: LibSQL Server (sqld Docker)   │   │   • BioAlba Scraper (Reloj Biométrico) │
│   Opción B: SQLite Local (asistencia.db)  │   │   • Google Drive API (Fotos Portería)  │
│   (54 tablas, WAL mode, concurrencia)     │   │   • SMTP Gmail (Alertas automáticas)   │
└───────────────────────────────────────────┘   └────────────────────────────────────────┘
```

---

## 3. MAPA DEL ÁRBOL DE DIRECTORIOS

```
/opt/asistencia/   (o C:\Asistencia en Windows)
├── backend/
│   ├── core/                      # Núcleo del sistema
│   │   ├── config.py              # Pydantic Settings: carga de .env y validaciones
│   │   ├── database.py            # Adaptador LibSQL/SQLite asíncrono con locks y reintentos
│   │   ├── events.py              # Ciclo de vida FastAPI (startup, shutdown, scheduler)
│   │   ├── security.py            # JWT, hashing de contraseñas bcrypt
│   │   ├── sys_utils.py           # Utilidades de sistema y liberación de puertos
│   │   └── startup_manager.py     # Gestor de progreso de inicialización
│   ├── models/                    # Modelos de dominio
│   ├── repositories/              # Capa de persistencia SQL directa (30+ tablas)
│   │   ├── asistencia.py          # Operaciones sobre tabla 'asistencias' y 'jornadas_especiales'
│   │   ├── turno.py               # Gestión de turnos, ciclos, horas_extras, logs_raw
│   │   ├── empleado.py            # Empleados, áreas, cargos, historial
│   │   ├── porteria.py            # Rondas, visitas, control de llaves
│   │   ├── flota.py               # Camiones, odómetros, checklist
│   │   ├── configuracion.py       # Ajustes del sistema, bonos, justificaciones, cierres
│   │   └── seguridad.py           # Usuarios, roles, permisos, auditoría
│   ├── routers/                   # Controladores REST API FastAPI
│   ├── schemas/                   # Esquemas Pydantic de entrada/salida
│   ├── scraper/                   # Módulo de extracción biométrica web
│   │   └── bioalba_scraper.py     # Scraper automatizado para bioalba1.controlasistencia.cl
│   ├── services/                  # LÓGICA DE NEGOCIO PURA
│   │   ├── quantum_matrix_engine.py  # MOTOR CUÁNTICO MATRICIAL (QME): Reglas de asistencia
│   │   ├── asistencia_service.py     # Orquestación de recálculos, perdonazos, consolidación
│   │   ├── report_service.py         # Generación de reportes PDF y Excel
│   │   ├── dashboard_analytics.py    # Métricas y analítica del dashboard
│   │   └── google_drive.py           # Conexión Service Account Google Drive
│   └── main.py                    # Punto de entrada FastAPI, middlewares y rutas estáticas
├── frontend/                      # Aplicación cliente SPA
│   ├── index.html                 # Página principal monolítica de la plataforma
│   ├── login.html                 # Pantalla de inicio de sesión
│   ├── css/                       # Hojas de estilo Bootstrap y responsive personalizadas
│   ├── js/                        # Módulos JavaScript Vanilla ES6+
│   │   ├── marcaciones_ui.js      # PANTALLA PRINCIPAL: Grilla analítica matricial y balance
│   │   ├── perdonazo_panel.js     # Panel lateral de condonaciones de jefatura
│   │   ├── dashboard_react.js     # Dashboard ejecutivo interactivo
│   │   ├── horarios.js            # Diseñador visual de turnos de ciclo inteligente
│   │   ├── flota_ui.js            # Módulo de gestión de flota de camiones
│   │   ├── porteria_ui.js         # Módulo de control de acceso y rondas
│   │   └── configuracion_ui.js    # Parámetros globales y mantenedores
│   ├── assets/                    # Logotipos, íconos y sonidos operacionales
│   └── sw.js                      # Service Worker para instalación PWA y caché
├── scripts/                       # Scripts de administración, migraciones y mantenimiento
│   ├── migrar_datos_a_local.py    # SCRIPT CANÓNICO DE MIGRACIÓN: Turso Cloud -> Local
│   ├── reprocesar_ciclo_inteligente_26ago_al_presente.py # Recálculo canónico de asistencia
│   └── deploy_with_envs.py        # Script legacy de despliegue Cloud
├── data/                          # Directorio para la base de datos local (.db / backups)
├── logs/                          # Logs de ejecución rotativos (app.log)
├── downloads/                     # Archivos temporales generados para exportación
├── requirements.txt               # Lista de dependencias de Python
└── .env                           # Archivo de configuración de variables de entorno
```

---

## 4. CATÁLOGO DE VARIABLES DE ENTORNO (`.env`)

El archivo `.env` en la raíz del proyecto es leído por [`backend/core/config.py`](file:///C:/Users/Daniel_Oteiza_Canale/Desktop/Proyectos_Python/Asistencia/backend/core/config.py). A continuación se detalla cada parámetro:

| Variable | Tipo | Por Defecto | ¿Sensible? | Descripción Técnica y Uso |
| :--- | :---: | :---: | :---: | :--- |
| `APP_NAME` | String | `Sistema de Gestión de Asistencia` | No | Nombre público mostrado en el título del sistema. |
| `APP_ENV` | String | `production` | No | Entorno (`production`, `development`). |
| `DEBUG` | Bool | `false` | No | Activa trazas detalladas y logs de depuración. |
| `TIMEZONE` | String | `America/Santiago` | No | Zona horaria oficial para todo cálculo cronológico. |
| `API_HOST` | String | `0.0.0.0` | No | Dirección IP donde escucha FastAPI (`0.0.0.0` para red local). |
| `API_PORT` | Int | `8000` | No | Puerto TCP del servicio web. |
| `API_RELOAD` | Bool | `false` | No | Auto-recarga por cambios de archivo (debe ser `false` en prod). |
| `TURSO_DATABASE_URL` | String | *Obligatorio* | Sí | **URL de la Base de Datos**. En servidor local puede ser `http://127.0.0.1:8080` (si se usa `sqld` en Docker) o `data/asistencia_local.db` (archivo directo SQLite). |
| `TURSO_AUTH_TOKEN` | String | `""` | Sí | Token de autenticación de base de datos. Vacío `""` si es local sin token. |
| `SECRET_KEY` | String | *64 caracteres* | Sí | Clave criptográfica para firma de tokens JWT de sesión. |
| `ALGORITHM` | String | `HS256` | No | Algoritmo criptográfico de tokens. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Int | `10080` | No | Duración de la sesión de usuario en minutos (7 días = 10080). |
| `CRON_SECRET` | String | *String secreto* | Sí | Clave de autorización para endpoints disparados por cron externo. |
| `CONTROL_ASISTENCIA_URL` | String | `https://bioalba1.controlasistencia.cl` | No | URL del portal del reloj biométrico. |
| `CONTROL_ASISTENCIA_USER` | String | `aguacol` | Sí | Usuario de acceso para descarga de marcaciones biométricas. |
| `CONTROL_ASISTENCIA_PASSWORD` | String | `123456` | Sí | Contraseña de acceso al portal de marcaciones. |
| `SCRAPER_ENABLED` | Bool | `true` | No | Activa la descarga automática periódica de marcaciones del reloj. |
| `SCRAPER_INTERVAL_MINUTES` | Int | `60` | No | Frecuencia de ejecución del scraper (cada 60 minutos). |
| `SMTP_SERVER` | String | `smtp.gmail.com` | No | Servidor de correo para envío de alertas. |
| `SMTP_PORT` | Int | `587` | No | Puerto SMTP (587 para TLS/STARTTLS). |
| `SMTP_USER` | String | `operaciones.aguacol.spa@gmail.com` | Sí | Cuenta de correo emisora de notificaciones. |
| `SMTP_PASSWORD` | String | `erff ayax grfd umvj` | Sí | Contraseña de aplicación de Google (App Password de 16 letras). |
| `EMAIL_FROM` | String | `operaciones.aguacol.spa@gmail.com` | No | Remitente visible en los correos. |
| `FEATURE_NOTIFICACIONES_EMAIL` | Bool | `true` | No | Habilita o suspende el envío de correos. |
| `GOOGLE_DRIVE_FOLDER_ID` | String | `1Y3YeLP9l1O5IZdLVlvCDqUjfLRehv_Rp` | No | ID de la carpeta en Google Drive donde se suben fotos de portería. |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON_PATH` | String | `asistencia-13c58-230b9fe62f70.json` | Sí | Ruta al archivo JSON con las llaves de la Service Account de Google. |

### Plantilla Recomendada para Servidor Local (`.env`)
```env
# ==============================================================================
# CONFIGURACIÓN DEL SERVIDOR LOCAL - AGUACOL ASISTENCIA
# ==============================================================================
APP_NAME="Sistema de Gestión de Asistencia Aguacol"
APP_ENV=production
DEBUG=false
TIMEZONE=America/Santiago

API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=false

# BASE DE DATOS LOCAL
# Opción 1: Servidor sqld (Docker en puerto 8080)
TURSO_DATABASE_URL=http://127.0.0.1:8080
TURSO_AUTH_TOKEN=""

# Opción 2: Archivo directo SQLite (descomentar si no se usa Docker)
# TURSO_DATABASE_URL=data/asistencia_local.db
# TURSO_AUTH_TOKEN=""

# SEGURIDAD Y JWT
SECRET_KEY=f6f0eba50b84406b6a1c7903dd4eb123f22fb97584020c5174878494b0a6dcbd
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080
CRON_SECRET=mi-super-secreto-compartido-para-sincronizacion-auto-123

# SCRAPER BIOMÉTRICO (BIOALBA)
CONTROL_ASISTENCIA_URL=https://bioalba1.controlasistencia.cl
CONTROL_ASISTENCIA_USER=aguacol
CONTROL_ASISTENCIA_PASSWORD=123456
SCRAPER_ENABLED=true
SCRAPER_INTERVAL_MINUTES=60

# CORREO ELECTRÓNICO (GMAIL SMTP)
FEATURE_NOTIFICACIONES_EMAIL=true
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=operaciones.aguacol.spa@gmail.com
SMTP_PASSWORD="erff ayax grfd umvj"
EMAIL_FROM=operaciones.aguacol.spa@gmail.com

# GOOGLE DRIVE (FOTOS PORTERÍA)
GOOGLE_DRIVE_FOLDER_ID=1Y3YeLP9l1O5IZdLVlvCDqUjfLRehv_Rp
GOOGLE_APPLICATION_CREDENTIALS_JSON_PATH=asistencia-13c58-230b9fe62f70.json
```

---

## 5. ESTRATEGIA Y DESPLIEGUE DE LA NUEVA BASE DE DATOS LOCAL

El sistema utiliza la biblioteca oficial `libsql`, la cual es 100% compatible tanto con servidores remotos/locales de LibSQL (`sqld`) como con bases de datos estándar SQLite 3. Para el servidor local existen dos opciones arquitectónicas:

### Opción A (Recomendada): Servidor LibSQL (`sqld`) en Contenedor Docker
**¿Por qué es la opción preferida?**
1. Mantiene exactamente el mismo protocolo de red y comportamiento transaccional que Turso Cloud.
2. Soporta alta concurrencia con aislamiento WAL multihilo.
3. Permite que otras herramientas o réplicas en la red local se conecten al puerto `8080`.

**Comando para iniciar la base de datos local:**
```bash
# Crear directorio para persistencia de datos
mkdir -p /opt/asistencia/db_data

# Iniciar contenedor Docker de sqld
docker run -d \
  --name aguacol-libsql \
  --restart always \
  -p 127.0.0.1:8080:8080 \
  -v /opt/asistencia/db_data:/var/lib/sqld \
  ghcr.io/tursodatabase/libsql-server:latest
```

### Opción B: Archivo SQLite Local Directo (`data/asistencia_local.db`)
Si el servidor no tiene Docker, el sistema puede operar conectándose directamente a un archivo SQLite en disco.
- Configurar en `.env`: `TURSO_DATABASE_URL=data/asistencia_local.db` y `TURSO_AUTH_TOKEN=""`.
- El motor [`backend/core/database.py`](file:///C:/Users/Daniel_Oteiza_Canale/Desktop/Proyectos_Python/Asistencia/backend/core/database.py) detecta automáticamente el archivo local y aplica los PRAGMAs óptimos:
  * `PRAGMA journal_mode=WAL;` (concurrencia de lectura/escritura sin bloqueos).
  * `PRAGMA synchronous=NORMAL;` (alto rendimiento en discos SSD).
  * `PRAGMA foreign_keys=ON;` (integridad referencial activa).

### Procedimiento de Migración de Datos (Turso Cloud $\rightarrow$ Local)
En el repositorio se incluye el script listo para ejecutar: [`scripts/migrar_datos_a_local.py`](file:///C:/Users/Daniel_Oteiza_Canale/Desktop/Proyectos_Python/Asistencia/scripts/migrar_datos_a_local.py).

**Pasos para ejecutar la migración:**
1. Asegurarse de que el archivo `.env` del servidor tenga configuradas las credenciales de Turso Cloud origen.
2. Ejecutar el script:
   ```bash
   python scripts/migrar_datos_a_local.py
   ```
3. El script realiza:
   * Conexión a Turso Cloud y lectura de las 54 tablas activas.
   * Creación automática de las tablas con sus tipos e índices en `data/asistencia_local.db`.
   * Transferencia en bloques de 500 registros de los más de 70.000 registros históricos.
   * Validación cruzada de recuentos.

---

## 6. DICCIONARIO DE DATOS: RESUMEN DE LAS 54 TABLAS ACTIVAS

| Módulo / Subsistema | Tablas Principales | Propósito y Contenido |
| :--- | :--- | :--- |
| **Control de Turnos y Ciclos** | `turnos`, `turno_dias`, `turno_areas`, `asignacion_turnos` | Define horarios teóricos, semanas de rotación (Ciclo Inteligente), días libres y asignación de turnos a colaboradores. |
| **Marcaciones y Asistencia** | `logs_raw`, `asistencias`, `jornadas_especiales`, `viajes_largos`, `intercambios_dias` | `logs_raw` guarda marcas brutas de reloj (huella/facial). `asistencias` almacena el balance diario calculado. `jornadas_especiales` registra trabajo en día libre/feriado. `viajes_largos` consolida jornadas de transporte interurbano. |
| **Horas Extras y Compensación** | `horas_extras`, `compensaciones_he_inasistencia` | Almacena sobretiempos brutos, estado de aprobación de jefatura (`PENDIENTE`, `APROBADO`, `RECHAZADO`), minutos autorizados y compensaciones cruzadas. |
| **Personal y Estructura RRHH** | `empleados`, `areas`, `areas_alias`, `cargos`, `cargos_alias`, `historial_areas`, `cat_generos` | Ficha maestra de colaboradores, contratos, RUT, historial de traslados entre departamentos y equivalencias de alias. |
| **Permisos y Justificaciones** | `justificaciones`, `justificacion_tipos`, `cat_pagadores`, `cierres_periodos`, `periodos_rrhh` | Registro de licencias médicas, permisos administrativos con o sin goce de sueldo, y fechas de congelamiento/cierre mensual de RRHH. |
| **Bonos y Remuneraciones** | `bonos`, `bono_reglas`, `bono_asignaciones`, `area_bonos` | Reglas de bonos de producción/asistencia, factores de cumplimiento y asignación a cargos o áreas. |
| **Portería y Seguridad Física** | `porteria_ubicaciones`, `porteria_catalogo_hallazgos`, `porteria_rondas_registro`, `porteria_rondas_hallazgos`, `visitas_registros`, `llaves_maestro`, `llaves_registros` | Control de bitácora de porteros, rondas con código QR/NFC, catálogo de incidentes, registro de visitas externas con RUT y trazabilidad de préstamo de llaves. |
| **Flota de Transporte** | `flota_aguacol`, `flota_registros` | Catálogo de camiones y camionetas, chofer asignado, kilometrajes, odómetros de inicio/fin y checklists. |
| **Seguridad del Software** | `usuarios`, `roles`, `permisos`, `rol_permisos`, `logs_auditoria`, `sync_logs`, `ajustes` | Autenticación del sistema, control de acceso basado en roles (RBAC), pista de auditoría de cada acción administrativa y ajustes clave-valor. |

---

## 7. REGLAS DE NEGOCIO Y LÓGICA CRÍTICA DEL SOFTWARE (LO QUE NUNCA DEBE ROMPERSE)

> [!CAUTION]
> **ADVERTENCIA CRÍTICA PARA EL DESARROLLADOR EXTERNO:**  
> Este sistema implementa un motor de cálculo matemático con topología modular ($Z_{1440}$). Bajo ninguna circunstancia se deben introducir prorrateos artificiales, umbrales mágicos fijos o alterar la segregación de modelos de turno.

### 1. Dualidad Estricta de Modelos de Turno
El sistema opera con dos motores mutuamente excluyentes:
* **Modelo A: Ciclo Inteligente (12 turnos — Producción, Mantención, Administración, Calidad):**
  * Turnos con horarios rígidos o rotativos semanales (ej. Turno 23 de Mantención, Turno 1 de Planta).
  * Se evalúa cada día de forma independiente: hora de entrada teórica vs real (atraso), pausas de colación (exceso), salidas adelantadas y sobretiempo.
  * **Saldo Neto Diario:** Se calcula el débito neto (`minutos_deuda`) y el crédito (`horas_extras`).
* **Modelo B: Bolsa Flexible (Turnos 9 y 25 — Choferes y Transporte de Flota):**
  * Régimen bajo Artículo 25 bis del Código del Trabajo chileno.
  * **No tienen horario rígido diario de entrada ni salida.** Los choferes realizan viajes largos inter-día o servicios locales de reparto.
  * Operan mediante una **meta mensual acumulativa (180 horas al mes)**.
  * La deuda diaria es siempre `0`. El sobretiempo solo nace cuando el acumulador mensual supera la meta legal.
  * **REGLA ABSOLUTA:** Los turnos 9 y 25 **NUNCA DEBEN SER REPROCESADOS CON LÓGICA DIARIA**.

### 2. Motor Cuántico Matricial (QME — `QuantumMatrixEngine`)
Ubicado en [`backend/services/quantum_matrix_engine.py`](file:///C:/Users/Daniel_Oteiza_Canale/Desktop/Proyectos_Python/Asistencia/backend/services/quantum_matrix_engine.py):
* **Geometría de Fase Circular ($S^1$):** El día de 24 horas equivale a 1440 minutos cíclicos. La distancia entre dos marcas se calcula mediante la geodésica más corta en el círculo unitario (`QuantumPhaseTopology.circular_distance`), resolviendo automáticamente turnos nocturnos que cruzan la medianoche sin condiciones `if` deterministas frágiles.
* **Acumuladores Puros de Reloj en Frontend ([`frontend/js/marcaciones_ui.js`](file:///C:/Users/Daniel_Oteiza_Canale/Desktop/Proyectos_Python/Asistencia/frontend/js/marcaciones_ui.js)):**
  * Las columnas `ATR` (Atrasos), `S.ADL` (Salidas Adelantadas), `COL` (Exceso Colación) y `PER` (Permisos con Deuda) **reflejan fielmente los minutos registrados por el reloj biométrico**, descontando únicamente las condonaciones de jefatura.
  * **Está estrictamente prohibido prorratear estas columnas** con factores del tipo `baseDeuda / rawTotal` o resetearlas a cero cuando el día resulta compensado. La columna `TOTAL TNT` (Tiempo No Trabajado) es la única que totaliza la deuda neta económica.
* **Fórmula Canónica del Saldo Neto:**
  $$\text{Saldo Neto} = \text{HE Aprobadas} - \text{TOTAL TNT} - \text{Compensaciones}$$
* **Selector Tensorial de Salidas Óptimas:**
  Si un colaborador registra una entrada y múltiples marcas de salida consecutivas sin reingreso intermedio (por ejemplo, salida intermedia a las 20:35 y salida definitiva a las 23:20 para un turno que termina a las 23:00), el motor selecciona automáticamente la salida que minimiza la distancia al fin de turno contractual, consumiendo la marca intermedia para que no genere anomalías.

### 3. Condonaciones Humanas ("Perdonazos")
Cuando jefatura valida un perdonazo en [`perdonazo_panel.js`](file:///C:/Users/Daniel_Oteiza_Canale/Desktop/Proyectos_Python/Asistencia/frontend/js/perdonazo_panel.js):
* **Tipo 1:** Condonación de salida adelantada $\rightarrow$ descuenta minutos de `S.ADL` y reduce la deuda neta.
* **Tipo 2:** Condonación de atraso $\rightarrow$ descuenta minutos de `ATR` y reduce la deuda neta.
* **Tipo 3:** Condonación mixta $\rightarrow$ descuenta ambos conceptos de sus columnas y anula la deuda.
* **Tipo 5:** Cierre de faena / Día completo justificado $\rightarrow$ la deuda neta imputable del día pasa a `00:00:00`.

---

## 8. GUÍA PASO A PASO: INSTALACIÓN EN EL SERVIDOR LOCAL

### Escenario A: Servidor Linux (Ubuntu 22.04 / 24.04 LTS)

#### Paso 1: Instalar Paquetes de Sistema
```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git curl nginx
```

#### Paso 2: Clonar el Código del Proyecto
```bash
sudo mkdir -p /opt/asistencia
sudo chown -R $USER:$USER /opt/asistencia
git clone https://github.com/ichidoro/Asistencia.git /opt/asistencia
cd /opt/asistencia
```

#### Paso 3: Crear Entorno Virtual e Instalar Dependencias
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-cloud.txt
```

#### Paso 4: Configurar Base de Datos Local y Migrar Datos
Si se utiliza Docker para LibSQL:
```bash
docker run -d --name aguacol-db --restart always -p 127.0.0.1:8080:8080 -v /opt/asistencia/data:/var/lib/sqld ghcr.io/tursodatabase/libsql-server:latest
```
Configurar el archivo `.env` en `/opt/asistencia/.env` con la URL de la base de datos local y ejecutar la migración:
```bash
python scripts/migrar_datos_a_local.py
```

#### Paso 5: Crear Servicio Systemd (Inicio Automático 24/7)
Crear el archivo `/etc/systemd/system/asistencia.service`:
```ini
[Unit]
Description=Servicio Sistema Asistencia Aguacol (FastAPI)
After=network.target docker.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/asistencia
EnvironmentFile=/opt/asistencia/.env
ExecStart=/opt/asistencia/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5
StandardOutput=append:/opt/asistencia/logs/service.log
StandardError=append:/opt/asistencia/logs/service_err.log

[Install]
WantedBy=multi-user.target
```
Habilitar e iniciar el servicio:
```bash
sudo systemctl daemon-reload
sudo systemctl enable asistencia
sudo systemctl start asistencia
sudo systemctl status asistencia
```

#### Paso 6: Configurar Nginx como Reverse Proxy con WebSocket
Crear el archivo `/etc/nginx/sites-available/asistencia`:
```nginx
server {
    listen 80;
    server_name asistencia.aguacol.local; # o la IP del servidor local

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```
Activar y reiniciar Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/asistencia /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

### Escenario B: Servidor Windows Server (2019 / 2022)

1. **Instalar Python:** Descargar e instalar Python 3.11+ para Windows marcando la opción *"Add python.exe to PATH"*.
2. **Ubicación:** Clonar o extraer el proyecto en `C:\Asistencia`.
3. **Entorno Virtual:**
   ```powershell
   cd C:\Asistencia
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
4. **Configurar `.env`:** Configurar `TURSO_DATABASE_URL=data/asistencia_local.db` y `TURSO_AUTH_TOKEN=""`.
5. **Migrar Datos:**
   ```powershell
   python scripts\migrar_datos_a_local.py
   ```
6. **Instalar como Servicio de Windows:**
   - Se puede utilizar la herramienta **NSSM (Non-Sucking Service Manager)**:
     ```powershell
     nssm.exe install AsistenciaAguacol "C:\Asistencia\.venv\Scripts\uvicorn.exe" "backend.main:app --host 0.0.0.0 --port 8000"
     nssm.exe set AsistenciaAguacol AppDirectory "C:\Asistencia"
     nssm.exe set AsistenciaAguacol AppExit Default Restart
     nssm.exe start AsistenciaAguacol
     ```
   - O ejecutar el instalador automatizado incluido en [`installer/Aguacol_Asistencia_Setup.iss`](file:///C:/Users/Daniel_Oteiza_Canale/Desktop/Proyectos_Python/Asistencia/installer/setup.iss).

---

## 9. OPERACIÓN, MONITOREO Y RESPALDO (RUNBOOK)

### Verificación de Salud
* **Health Check API:** `GET http://<IP-SERVIDOR>:8000/api/startup/status`  
  Respuesta esperada: `{"ready": true, "progress": 100, "message": "Iniciando Dashboard..."}`
* **Revisión de Logs en Vivo:**
  ```bash
  tail -f /opt/asistencia/logs/app.log
  ```

### Procedimiento de Respaldo Diario Automatizado (Backup)
Crear un cron job en el servidor local para respaldar la base de datos diariamente a las 02:00 AM:
```bash
crontab -e
```
Agregar la siguiente línea:
```cron
0 2 * * * cp /opt/asistencia/data/asistencia_local.db /opt/backups/asistencia_$(date +\%Y\%m\%d).db
```

### Protocolo de Reproceso Canónico de Asistencia
Si por alguna razón administrativa se requiere recalcular un período completo tras cargar marcaciones manuales masivas, **nunca modificar la base de datos a mano**. Utilizar el script certificado:
```bash
python scripts/reprocesar_ciclo_inteligente_26ago_al_presente.py
```
Este script:
1. Valida y aisla a los 67 colaboradores de Ciclo Inteligente.
2. Excluye automáticamente al personal de Bolsa Flexible de transporte.
3. Respeta todas las decisiones humanas preexistentes (horas extras aprobadas/rechazadas y condonaciones).
4. Sincroniza la tabla `asistencias` y `horas_extras` en lotes atómicos.

---

## 10. CONTACTO Y SOPORTE DE ARQUITECTURA
Para dudas respecto a las fórmulas matemáticas del motor cuántico, consultar el archivo [`backend/services/quantum_matrix_engine.py`](file:///C:/Users/Daniel_Oteiza_Canale/Desktop/Proyectos_Python/Asistencia/backend/services/quantum_matrix_engine.py) y las pruebas de simulación en [`scratch/simulate_plan_mantencion.py`](file:///C:/Users/Daniel_Oteiza_Canale/.gemini/antigravity/brain/c0f55747-019e-4a8a-915b-69d111180b2a/scratch/simulate_plan_mantencion.py).
