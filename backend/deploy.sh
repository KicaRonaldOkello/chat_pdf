#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# VPS deploy script — pull latest image from GHCR and restart the app.
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh                    # pull latest and restart
#   ./deploy.sh --no-pull          # restart without pulling (e.g. after .env change)
#
# Setup (one-time):
#   1. Install Docker + docker compose plugin
#   2. Create a GitHub Personal Access Token (classic) with `read:packages` scope
#   3. docker login ghcr.io -u YOUR_GITHUB_USERNAME
#      (paste the PAT as the password)
#   4. Copy .env.example → .env and fill in your production values
#   5. Set GHCR_OWNER in .env (or export it):
#      echo 'GHCR_OWNER=yourgithubuser' >> .env
#   6. docker compose -f docker-compose.prod.yml up -d
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE_FILE="docker-compose.prod.yml"

pull() {
    echo "==> Pulling latest image from GHCR …"
    docker compose -f "$COMPOSE_FILE" pull api
}

restart() {
    echo "==> Recreating api container with latest image …"
    docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate api
}

prune() {
    echo "==> Removing old images …"
    docker image prune -f
}

case "${1:-}" in
    --no-pull)
        restart
        ;;
    *)
        pull
        restart
        prune
        ;;
esac

echo "✓ Deploy complete.  Check status:"
docker compose -f "$COMPOSE_FILE" ps
