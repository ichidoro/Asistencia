#!/usr/bin/env bash
# Prueba que el ultimo respaldo SE PUEDE restaurar (un respaldo que no restaura no sirve).
# Restaura en una BD temporal, compara conteos con la BD viva y la borra. Sale con error si algo falla.
# cron sugerido (domingo 03:00):  0 3 * * 0 bash /ruta/asistencia/restore-test.sh >> /ruta/asistencia/logs/restore-test.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a
U="${POSTGRES_USER:-asistencia}"; DB="${POSTGRES_DB:-asistencia_db}"; T="restore_test_$$"
LAST=$(ls -t backups/asistencia_*.sql.gz 2>/dev/null | head -1)
[ -n "$LAST" ] || { echo "$(date '+%F %T') FALLO: no hay respaldos en ./backups"; exit 1; }
psql_() { docker compose exec -T db psql -U "$U" "$@"; }
trap 'psql_ -d postgres -qc "DROP DATABASE IF EXISTS \"$T\"" >/dev/null 2>&1 || true' EXIT
psql_ -d postgres -qc "CREATE DATABASE \"$T\"" >/dev/null
gunzip -c "$LAST" | psql_ -d "$T" -q -v ON_ERROR_STOP=1 >/dev/null
Q="select (select count(*) from empleados)||'/'||(select count(*) from asistencias)||'/'||(select count(*) from logs_raw)"
LIVE=$(psql_ -d "$DB" -Atc "$Q"); REST=$(psql_ -d "$T" -Atc "$Q")
echo "$(date '+%F %T') restauracion OK de $LAST  empleados/asistencias/logs  viva=$LIVE  restaurada=$REST"
