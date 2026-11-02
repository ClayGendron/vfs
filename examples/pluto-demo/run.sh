#!/usr/bin/env bash
# One command: build the web app if needed, then serve the Halyard workspace on http://127.0.0.1:8765.
# Set ANTHROPIC_API_KEY for a live agent; without it Atlas replays a scripted transcript against the real kernel.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"

if [[ "${1:-}" == "--rebuild" || ! -f "$here/web/build/index.html" ]]; then
  echo "building the web app"
  (cd "$here/web" && bun install --frozen-lockfile && bun run build)
fi

cd "$repo"
uv sync --all-extras --group dev --group demo --quiet
echo "Halyard workspace: http://127.0.0.1:${PLUTO_PORT:-8765}"
PYTHONPATH="$here/server" exec uv run python -m pluto_demo
