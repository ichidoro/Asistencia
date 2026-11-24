#!/usr/bin/env bash
# Resumen diario de horas (lunes a viernes) (Bolsa vs meta) por WhatsApp. Llama a POST /api/whatsapp/resumen-semanal/cron.
# franja mediodia = atrasos de hoy del resumen general de bodega:  0 12 * * 1-5 bash /ruta/asistencia/cron-resumen-whatsapp.sh mediodia >> ... 2>&1
# franja manana = resumen a jefatura y horas extras del día anterior (resumen general); franja tarde = resumen a cada persona (viernes y día del cierre).
#   0 20 * * * bash /ruta/asistencia/cron-resumen-whatsapp.sh tarde >> /ruta/asistencia/logs/cron_whatsapp.log 2>&1
# cron sugerido (lunes a viernes 08:00):  0 8 * * 1-5 bash /ruta/asistencia/cron-resumen-whatsapp.sh >> /ruta/asistencia/logs/cron_whatsapp.log 2>&1
FRANJA="${1:-manana}"   # manana | mediodia | tarde
set -euo pipefail
cd "$(dirname "$0")"
envget() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }
[ "$(envget WHATSAPP_ENABLED)" = "true" ] || exit 0
SECRET="$(envget CRON_SECRET)"; PORT="$(envget APP_PORT)"; PORT="${PORT:-8000}"
[ -n "$SECRET" ] || { echo "$(date '+%F %T') FALLO: CRON_SECRET vacio en .env"; exit 1; }
RESP=$(curl -sS -m 1800 -X POST "http://127.0.0.1:${PORT}/api/whatsapp/resumen-semanal/cron" -H 'Content-Type: application/json' \
       -d "{\"cron_secret\":\"${SECRET}\",\"franja\":\"${FRANJA}\"}" || echo '{"status":"error","detail":"sin respuesta"}')
echo "$(date '+%F %T') $RESP" | cut -c1-500
