#!/usr/bin/env bash
# Alerta en vivo de exceso de velocidad (Flota en vivo de Nexacol, cuando pasa de 100 km/h; el mensaje dice límite 90 km/h) por WhatsApp. Llama a POST /api/whatsapp/alerta-velocidad/cron.
# cron sugerido (cada minuto):  * * * * * bash /ruta/asistencia/cron-alerta-velocidad.sh >> /ruta/asistencia/logs/cron_alerta_velocidad.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
envget() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }
[ "$(envget WHATSAPP_ENABLED)" = "true" ] || exit 0
SECRET="$(envget CRON_SECRET)"; PORT="$(envget APP_PORT)"; PORT="${PORT:-8000}"
[ -n "$SECRET" ] || { echo "$(date '+%F %T') FALLO: CRON_SECRET vacio en .env"; exit 1; }
RESP=$(curl -sS -m 50 -X POST "http://127.0.0.1:${PORT}/api/whatsapp/alerta-velocidad/cron" -H 'Content-Type: application/json' \
       -d "{\"cron_secret\":\"${SECRET}\"}" || echo '{"status":"error","detail":"sin respuesta"}')
# Solo se deja registro cuando hubo algo que avisar o falló (cada minuto sin novedad llenaría el log).
case "$RESP" in *'"a_avisar":0'*|*'"activo":false'*) ;; *) echo "$(date '+%F %T') $RESP" | cut -c1-500;; esac
