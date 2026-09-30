#!/usr/bin/env bash
# Respaldo diario de la BD (pg_dump comprimido) en ./backups, conserva 14 días.
# cron sugerido:  0 2 * * * /ruta/asistencia/backup-postgres.sh >> /ruta/asistencia/logs/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
envget() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }   # .env no es shell-safe
POSTGRES_USER="$(envget POSTGRES_USER)"; POSTGRES_DB="$(envget POSTGRES_DB)"
mkdir -p backups
OUT="backups/asistencia_$(date +%Y%m%d_%H%M%S).sql.gz"
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-asistencia}" "${POSTGRES_DB:-asistencia_db}" | gzip > "$OUT"
# fotos de rondas de Porteria (se guardan en el servidor, ya no en Drive)
[ -d downloads/porteria_fotos ] && tar czf "backups/fotos_$(date +%Y%m%d).tgz" downloads/porteria_fotos 2>/dev/null || true
find backups \( -name 'asistencia_*.sql.gz' -o -name 'fotos_*.tgz' \) -mtime +14 -delete
echo "$(date '+%F %T') respaldo OK: $OUT ($(du -h "$OUT" | cut -f1))"
