#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="$(cd "$(dirname "$0")/.." && pwd)/docker/mssql/docker-compose.yml"

echo "=> Building and starting grover-mssql-2025 (linux/amd64 via Rosetta)..."
docker compose -f "$COMPOSE_FILE" up -d --build

echo "=> Waiting for container health..."
CID="$(docker compose -f "$COMPOSE_FILE" ps -q mssql)"
for i in {1..60}; do
  STATUS="$(docker inspect -f '{{.State.Health.Status}}' "$CID" 2>/dev/null || echo starting)"
  if [ "$STATUS" = "healthy" ]; then
    echo "=> grover-mssql-2025 is healthy."
    exit 0
  fi
  if [ "$STATUS" = "unhealthy" ]; then
    echo "!! container reported unhealthy; dumping logs" >&2
    docker compose -f "$COMPOSE_FILE" logs --tail=80 mssql >&2
    exit 1
  fi
  sleep 3
done

echo "!! timeout waiting for health" >&2
docker compose -f "$COMPOSE_FILE" logs --tail=80 mssql >&2
exit 1
