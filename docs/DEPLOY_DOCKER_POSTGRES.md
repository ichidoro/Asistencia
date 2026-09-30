# Despliegue Docker + PostgreSQL (sin Turso)

La app corre en Docker con su propia BD PostgreSQL 16. Es independiente de Cloud Run/Turso y de cualquier otro sistema del servidor.

## Cómo funciona la compatibilidad

Los repositorios siguen escribiendo SQL estilo SQLite (`?`, `strftime`, `INSERT OR IGNORE`...).
`backend/core/sql_compat.py` y `sql_groupby.py` lo traducen a PostgreSQL al vuelo, y `backend/core/database.py`
(`PostgresDatabase`, asyncpg) mantiene la misma interfaz que tenía `TursoDatabase`. No hay que tocar las queries.

Cosas a saber al escribir SQL nuevo:
- Fechas: se guardan como `TEXT` ISO (`YYYY-MM-DD[ HH:MM:SS]`), igual que antes.
- Columnas `INTEGER` que no son `id`/`*_id` se crean `NUMERIC` (SQLite guardaba decimales ahí, ej. `minutos_atraso = 4.4667`).
- Postgres es estricto con `GROUP BY`; el traductor envuelve en `MIN()` las columnas sueltas (SQLite tomaba una fila cualquiera).
- Si una consulta sin `ORDER BY` depende del orden, ponerle `ORDER BY` explícito (SQLite devolvía orden de inserción).

## Primera instalación (servidor)

```bash
git clone <repo> asistencia && cd asistencia
git checkout postgres            # o la rama que se quiera seguir
echo postgres > .deploy-branch   # rama que sigue el autodeploy
cp .env.example .env             # completar POSTGRES_PASSWORD, SECRET_KEY, CRON_SECRET
docker compose up -d --build     # crea el esquema al arrancar
```

Cargar los datos (una vez, con la app ya arrancada para que exista el esquema):

```bash
# 1) copia de solo lectura desde Turso (en cualquier máquina con python)
pip install libsql
TURSO_URL=libsql://... TURSO_TOKEN=... python scripts/dump_turso.py turso_copy.db
# 2) cargar en Postgres (TRUNCA las tablas destino)
pip install asyncpg
DATABASE_URL=postgresql://asistencia:CLAVE@127.0.0.1:5432/asistencia_db python scripts/load_sqlite_to_postgres.py turso_copy.db
```
(El puerto 5432 no está publicado; para cargar desde el host usar `docker compose exec` con un contenedor auxiliar
o publicar temporalmente `127.0.0.1:5432`.)

## Actualizar desde GitHub

Manual: `./deploy.sh` (solo reconstruye si hay commits nuevos en la rama; `--force` para obligar).
La BD no se toca. Rollback: `git checkout pre-deploy-<fecha> && docker compose up -d --build app`.

Automático (revisa GitHub cada minuto):

```bash
sudo sed -e "s#__USER__#$USER#" -e "s#__DIR__#$PWD#" deploy/asistencia-autodeploy.service > /etc/systemd/system/asistencia-autodeploy.service
sudo cp deploy/asistencia-autodeploy.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now asistencia-autodeploy.timer
```
El servidor necesita poder hacer `git fetch` (deploy key de solo lectura en GitHub → Settings → Deploy keys).

## Respaldos

`./backup-postgres.sh` (pg_dump comprimido en `./backups`, 14 días). Programar en cron a las 02:00.

## Instancia paralela a producción

Mientras esta copia no sea la definitiva: `SYNC_ENABLED`, `SCRAPER_ENABLED`, `BACKUP_ENABLED` y
`FEATURE_NOTIFICACIONES_EMAIL` en `false` (ya vienen así en `.env.example`), para no duplicar marcaciones,
correos ni respaldos de la instancia real.

## Secretos que siguen en el código (`backend/core/config.py`)

`SECRET_KEY`, `CRON_SECRET`, clave de Bioalba y app-password SMTP tienen valores por defecto en el repo (y en su
historial). El `.env` los sobrescribe, pero conviene rotarlos y quitarlos del código. El token de Turso ya no está en el código
actual, pero **sigue en el historial de git**: rotarlo en Turso.

## Operación y rendimiento

- **Postgres** arranca con parámetros ajustados (`docker-compose.yml`, bloque `command`) y `pg_stat_statements`.
  Activarlo una vez: `docker compose exec db psql -U asistencia -d asistencia_db -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements"`;
  luego `select calls, total_exec_time, query from pg_stat_statements order by total_exec_time desc limit 10`.
- **La app corre sin root (uid 1000)**. Si `logs/`, `downloads/` o `backups/` fueron creados por root (instalaciones antiguas):
  `docker run --rm -v "$PWD:/w" alpine chown -R 1000:1000 /w/logs /w/downloads /w/backups`.
- **Respaldos**: `backup-postgres.sh` (diario 02:00) y `restore-test.sh` (domingo 03:00, restaura el último respaldo en una BD
  temporal y compara conteos). Un respaldo que no restaura no sirve: revisar `logs/restore-test.log`.
- **Respuestas grandes** (`/asistencia/matriz`, `/matrix`, `/reporte`) usan `backend/core/fast_json.py` (orjson) en vez de
  `jsonable_encoder` de FastAPI (3× más rápido). Usarlo en endpoints nuevos con payloads de miles de filas.
- **Tooltips de la tabla de Marcaciones** se arman al pasar el mouse (`window.__mxTipReg` + `_getCellTipHtml`). No volver a
  incrustar HTML en atributos por celda: pesaba 12 MB por render.
- **Fechas/horas**: `CURRENT_TIMESTAMP/DATE/TIME` se traducen a TEXT UTC (`YYYY-MM-DD HH:MM:SS`), igual que SQLite.
- **Claves foráneas con huérfanos** (SQLite no las hacía cumplir): `load_sqlite_to_postgres.py` las deja `NOT VALID` para que
  los respaldos restauren sin perder historial.
