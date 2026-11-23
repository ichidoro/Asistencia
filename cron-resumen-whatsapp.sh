#!/usr/bin/env bash
# Resumen semanal de horas (Bolsa vs meta) por WhatsApp. Llama a POST /api/whatsapp/resumen-semanal/cron.
# cron sugerido (lunes 08:00):  0 8 * * 1 bash /ruta/asistencia/cron-resumen-whatsapp.sh >> /ruta/asistencia/logs/cron_whatsapp.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
envget() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }
[ "$(envget WHATSAPP_ENABLED)" = "true" ] || exit 0
SECRET="$(envget CRON_SECRET)"; PORT="$(envget APP_PORT)"; PORT="${PORT:-8000}"
[ -n "$SECRET" ] || { echo "$(date '+%F %T') FALLO: CRON_SECRET vacio en .env"; exit 1; }
RESP=$(curl -sS -m 1800 -X POST "http://127.0.0.1:${PORT}/api/whatsapp/resumen-semanal/cron" -H 'Content-Type: application/json' \
       -d "{\"cron_secret\":\"${SECRET}\"}" || echo '{"status":"error","detail":"sin respuesta"}')
echo "$(date '+%F %T') $RESP" | cut -c1-500
