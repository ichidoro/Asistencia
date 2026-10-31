# Aguacol Asistencia — contexto del proyecto

Sistema de control de asistencia y horas de Aguacol. Backend en Python 3.13 con FastAPI, base de datos PostgreSQL 16 en Docker, y frontend HTML/CSS/JS estático que sirve el mismo backend (sin paso de compilación).

## Dónde está cada cosa

- `backend/main.py`: entrada de la aplicación (`backend.main:app`).
- `backend/routers/`: endpoints, uno por módulo.
- `backend/services/`: lógica de negocio. El motor de cálculo está en `asistencia_service.py`.
- `backend/scraper/`: lectura de los relojes BioAlba y EasyTime.
- `backend/docs/REGLAS_ASISTENCIA.md`: reglas de negocio canónicas para el cálculo. Si el código y este documento no coinciden, pregunta antes de cambiar una regla.
- `frontend/`: pantallas HTML, CSS y JS.
- `docs/DEPLOY_DOCKER_POSTGRES.md`: despliegue, respaldos y operación.
- `backend/tests/`: pruebas con pytest.

## Reglas de trabajo

- **Una sola rama: `main`.** Cada push a `main` se despliega solo en el servidor en ~1 minuto. No hagas push sin confirmación de la persona dueña.
- **SQL compatible con PostgreSQL.** Los repositorios escriben SQL estilo SQLite. `backend/core/sql_compat.py` y `sql_groupby.py` lo traducen. Si escribes SQL nuevo, revisa esa traducción.
- **Instancia de prueba apagada.** En el `.env` local deben quedar en `false`: `SYNC_ENABLED`, `SCRAPER_ENABLED`, `BACKUP_ENABLED` y `FEATURE_NOTIFICACIONES_EMAIL`. Una copia activa duplicaría marcaciones, correos y respaldos.
- **Secretos fuera de git.** `.env` no se sube. No escribas contraseñas, claves ni tokens en código ni en documentos.
- **Datos reales.** La base de producción tiene datos de personas. Nunca la modifiques desde una sesión de desarrollo.

## Cómo correrlo

- Configuración: copia `.env.example` a `.env` y completa los valores.
- Con Docker: `docker compose up -d --build`.
- Pruebas: `.venv\Scripts\python.exe -m pytest backend\tests`.

## Antes de cerrar un cambio

- Corre las pruebas de la parte que tocaste.
- Si cambias cálculos de asistencia, confirma la regla en `backend/docs/REGLAS_ASISTENCIA.md`.
