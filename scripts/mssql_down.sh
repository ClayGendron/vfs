#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="$(cd "$(dirname "$0")/.." && pwd)/docker/mssql/docker-compose.yml"

CLEAN=0
for arg in "$@"; do
  case "$arg" in
    --clean) CLEAN=1 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

if [ "$CLEAN" = "1" ]; then
  echo "=> Stopping and removing container + volume..."
  docker compose -f "$COMPOSE_FILE" down -v
else
  echo "=> Stopping container (volume preserved)..."
  docker compose -f "$COMPOSE_FILE" down
fi
