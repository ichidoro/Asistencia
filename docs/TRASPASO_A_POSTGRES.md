# Traspaso: apagar Turso y Google Cloud Run, dejar el servidor como principal

Objetivo: que el servidor (Docker + PostgreSQL) sea **la única instalación**, y dar de baja Cloud Run y Turso.
El orden importa: si se apaga algo antes de tiempo se pierden marcaciones o decisiones hechas en el sistema.

## Qué hacía cada servicio de Google / Turso y quién lo reemplaza

| Hoy (nube) | Qué hace | Reemplazo en el servidor |
|---|---|---|
| **Turso** | Base de datos | PostgreSQL 16 en Docker (`asistencia_db`) |
| **Cloud Run** | Corre la app | Contenedor `asistencia_app` (puerto 8000) |
| **Cloud Scheduler** | Llama `POST /api/sync/cron/` con `CRON_SECRET` para traer marcaciones de BioAlba | `cron-sync.sh` en el cron del servidor (activar con `SYNC_CRON_ENABLED=true`) |
| **Bot BioAlba** | Descarga marcaciones (está dentro de la app: `backend/scraper/bioalba_scraper.py`) | Mismo código; probado: inicia sesión desde el servidor |
| **Google Drive** | Fotos de las rondas de Portería | Se guardan en `downloads/porteria_fotos/` (incluidas en el respaldo). Drive sigue funcionando si se configuran sus credenciales |
| **Gmail SMTP** | Correos de cierres y notificaciones | Igual (no depende de Google Cloud); se activa con `FEATURE_NOTIFICACIONES_EMAIL=true` |
| Respaldos | (Turso los hacía por su lado) | `backup-postgres.sh` diario + `restore-test.sh` semanal |

> **Cuidado:** si las credenciales de Drive (cuenta de servicio) viven en el proyecto de Google Cloud, **no borrar ese proyecto**
> sin antes migrar las fotos ya subidas (las fotos antiguas se abren por su enlace de Drive).

## Datos que hay que sacar de Cloud Run antes (los pone quien administra Google Cloud, directo en `~/asistencia/.env`)

Variables reales de producción (pueden diferir de los valores por defecto del código):

- `CONTROL_ASISTENCIA_USER`, `CONTROL_ASISTENCIA_PASSWORD`, `CONTROL_ASISTENCIA_URL` (BioAlba)
- `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`
- `SECRET_KEY` (si se quiere que **no se cierren las sesiones** de los usuarios; si no, todos vuelven a iniciar sesión)
- `CRON_SECRET`
- (Opcional) `GOOGLE_DRIVE_FOLDER_ID` y `GOOGLE_APPLICATION_CREDENTIALS_JSON`
- La **frecuencia real** del job en Cloud Scheduler (por defecto se propone cada 15 min).

Forma de verlas: consola de Google Cloud → Cloud Run → servicio → *Editar y desplegar nueva revisión* → Variables, o
`gcloud run services describe <servicio> --region <región> --format=export`.

## Pasos del traspaso (en este orden)

1. **Preparar (sin cortar nada)**
   - Copiar las variables de arriba al `.env` del servidor.
   - Probar una sincronización manual y comparar con lo que produjo Cloud Run los mismos días.
   - Elegir el momento: ideal fuera del horario de marcaciones/cierres.
2. **Congelar producción:** avisar que no se editen cierres, aprobaciones ni justificaciones. Dejar Cloud Run solo para consulta.
3. **Carga final de datos:** volcar Turso (solo lectura) y cargar en Postgres, que **reemplaza** lo que había:
   `scripts/dump_turso.py` → `scripts/load_sqlite_to_postgres.py` (ver `DEPLOY_DOCKER_POSTGRES.md`).
   Recalcular el día actual y comparar conteos con Turso (empleados, asistencias, horas extras, justificaciones).
4. **Encender lo que hacía la nube** en el `.env` del servidor y reiniciar (`docker compose up -d`):
   - `SYNC_CRON_ENABLED=true` (sincronización BioAlba cada 15 min)
   - `FEATURE_NOTIFICACIONES_EMAIL=true` (solo después de verificar una sincronización)
   - `SYNC_ENABLED=true`, `SCRAPER_ENABLED=true`, `BACKUP_ENABLED=true` si se usan esas funciones
5. **Apuntar la dirección de siempre al servidor:** un túnel de Cloudflare con nombre fijo (necesita el dominio) o el DNS actual.
   Mientras tanto, el enlace temporal `trycloudflare` sirve para pruebas.
6. **Apagar Cloud Run.** Antes, **desactivar el disparador de despliegue automático** (Cloud Build/GitHub) que apunta a `main`, y
   Cloud Scheduler; si no, el primero podría republicar una versión sin Turso o el segundo seguir llamando a una app apagada.
7. **Dejar `postgres` como principal en GitHub:** mezclar `postgres` en `main` (o cambiar la rama por defecto) y cambiar
   `.deploy-branch` del servidor si corresponde.
8. **Período de gracia (2–4 semanas):** dejar Turso sin tocar, solo como respaldo de último recurso.
9. **Dar de baja Turso y rotar credenciales**, recién entonces: token de Turso, `SECRET_KEY`, clave BioAlba y app-password de
   Gmail (todas están en el historial público del repositorio). **No rotar el token de Turso antes del paso 6**: Cloud Run lo usa.

## Si algo sale mal

Mientras Turso y Cloud Run sigan existiendo, volver atrás es solo repuntar la dirección a Cloud Run. Por eso los pasos 8–9 van al final.
