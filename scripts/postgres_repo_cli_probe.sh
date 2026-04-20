#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export VFS_REPO_DB_URL="${VFS_REPO_DB_URL:-postgresql+asyncpg://localhost/vfs_repo_case}"
export VFS_REPO_MOUNT="${VFS_REPO_MOUNT:-repo}"

cd "$ROOT_DIR"
exec uv run python scripts/postgres_repo_cli_probe.py "$@"
