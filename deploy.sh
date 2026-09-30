#!/usr/bin/env bash
# Corre EN EL SERVIDOR. Trae lo último de GitHub y reconstruye SOLO si hubo cambios.
#   ./deploy.sh          → actualiza a origin/$BRANCH y recrea el contenedor de la app
#   ./deploy.sh --force  → reconstruye aunque no haya commits nuevos
# Los datos (volumen pgdata) NO se tocan. Compose solo recrea lo que cambio (app, y db si cambio su config).
set -euo pipefail
cd "$(dirname "$0")"

# Una sola instancia a la vez: si un build tarda mas que el intervalo del cron, el siguiente se salta.
exec 9>/tmp/asistencia-deploy.lock
flock -n 9 || exit 0

BRANCH="${BRANCH:-$(cat .deploy-branch 2>/dev/null || echo main)}"

git fetch --quiet origin "$BRANCH"
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ] && [ "${1:-}" != "--force" ]; then
  exit 0
fi

# Tag de rollback: volver atras = git checkout <tag> && docker compose up -d --build
TAG="pre-deploy-$(date +%Y%m%d-%H%M%S)"
git tag "$TAG"
git tag -l 'pre-deploy-*' | sort | head -n -20 | xargs -r git tag -d >/dev/null

echo "$(date '+%F %T') deploy $LOCAL -> $REMOTE (tag rollback: $TAG)"
git checkout --quiet "$BRANCH" 2>/dev/null || git checkout --quiet -b "$BRANCH" "origin/$BRANCH"
git reset --hard "origin/$BRANCH"

docker compose up -d --build   # solo recrea los servicios cuyo codigo o config cambio (la BD y sus datos no se tocan)
docker image prune -f >/dev/null
docker compose ps
