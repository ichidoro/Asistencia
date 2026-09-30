#!/usr/bin/env bash
# Respaldo diario de la BD (pg_dump comprimido) en ./backups, conserva 14 días.
# cron sugerido:  0 2 * * * /ruta/asistencia/backup-postgres.sh >> /ruta/asistencia/logs/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a
mkdir -p backups
OUT="backups/asistencia_$(date +%Y%m%d_%H%M%S).sql.gz"
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-asistencia}" "${POSTGRES_DB:-asistencia_db}" | gzip > "$OUT"
find backups -name 'asistencia_*.sql.gz' -mtime +14 -delete
echo "$(date '+%F %T') respaldo OK: $OUT ($(du -h "$OUT" | cut -f1))"
