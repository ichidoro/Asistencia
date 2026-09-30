#!/usr/bin/env bash
# Corre EN EL SERVIDOR. Trae lo último de GitHub y reconstruye SOLO si hubo cambios.
#   ./deploy.sh          → actualiza a origin/$BRANCH y recrea el contenedor de la app
#   ./deploy.sh --force  → reconstruye aunque no haya commits nuevos
# La BD (volumen pgdata) NO se toca; solo se reconstruye/reinicia la app.
set -euo pipefail
cd "$(dirname "$0")"

BRANCH="${BRANCH:-$(cat .deploy-branch 2>/dev/null || echo main)}"

git fetch --quiet origin "$BRANCH"
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ] && [ "${1:-}" != "--force" ]; then
  exit 0
fi

# Tag de rollback: volver atrás = git checkout <tag> && docker compose up -d --build app
TAG="pre-deploy-$(date +%Y%m%d-%H%M%S)"
git tag "$TAG"
git tag -l 'pre-deploy-*' | sort | head -n -20 | xargs -r git tag -d >/dev/null

echo "$(date '+%F %T') deploy $LOCAL -> $REMOTE (tag rollback: $TAG)"
git checkout --quiet "$BRANCH" 2>/dev/null || git checkout --quiet -b "$BRANCH" "origin/$BRANCH"
git reset --hard "origin/$BRANCH"

docker compose up -d --build app
docker image prune -f >/dev/null
docker compose ps
