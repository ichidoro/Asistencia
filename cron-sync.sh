#!/usr/bin/env bash
# Sincroniza marcaciones desde BioAlba (reemplaza a Google Cloud Scheduler). Llama a POST /api/sync/cron/,
# que descarga ayer+hoy, procesa y recalcula. Se activa con SYNC_CRON_ENABLED=true en .env.
# cron sugerido (cada 15 min):  */15 * * * * bash /ruta/asistencia/cron-sync.sh >> /ruta/asistencia/logs/cron_sync.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
envget() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }   # .env no es shell-safe
[ "$(envget SYNC_CRON_ENABLED)" = "true" ] || exit 0
exec 9>/tmp/asistencia-cron-sync.lock
flock -n 9 || { echo "$(date '+%F %T') sync anterior sigue en curso, se omite"; exit 0; }
SECRET="$(envget CRON_SECRET)"; PORT="$(envget APP_PORT)"; PORT="${PORT:-8000}"
[ -n "$SECRET" ] || { echo "$(date '+%F %T') FALLO: CRON_SECRET vacio en .env"; exit 1; }
RESP=$(curl -sS -m 900 -X POST "http://127.0.0.1:${PORT}/api/sync/cron/" -H 'Content-Type: application/json' \
       -d "{\"cron_secret\":\"${SECRET}\"}" || echo '{"status":"error","detail":"sin respuesta"}')
echo "$(date '+%F %T') $RESP" | cut -c1-500
