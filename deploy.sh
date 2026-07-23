#!/usr/bin/env bash
# Deploy the latest production code: pull, rebuild the image and restart.
# Migrations run automatically before the server starts (see compose command).
set -euo pipefail

cd "$(dirname "$0")"

git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
