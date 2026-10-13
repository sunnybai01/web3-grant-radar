#!/usr/bin/env bash
# Update and (re)start the production stack on the EC2 host.
#
#   scripts/deploy/deploy.sh             # pull latest code, render .env, rebuild, restart
#   SKIP_PULL=1 scripts/deploy/deploy.sh # redeploy the current checkout (e.g. after changing SSM)
set -euo pipefail

cd "$(dirname "$0")/../.."

if [[ "${SKIP_PULL:-0}" != "1" ]]; then
  git pull --ff-only
fi

python3 scripts/deploy/ssm_env.py pull .env

# COMPOSE_FILE in .env selects docker-compose.yml + docker-compose.prod.yml.
docker compose build
docker compose up -d --remove-orphans
docker image prune -f >/dev/null

docker compose ps
