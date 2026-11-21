#!/usr/bin/env bash
# Every measurement of the study, one after another on a quiet machine, each under its own deadline.
#
#   L0_SCRATCH=/path/outside/the/repo \
#   VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs \
#     agents/2026-11-21-what-a-log-row-per-call-costs/scripts/run_all.sh
#
# The Postgres server is the container .claude/skills/db_test/SKILL.md starts and tears down.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${L0_SCRATCH:?L0_SCRATCH must name a scratch directory outside the repository}"
: "${VFS_TEST_POSTGRES_URL:?VFS_TEST_POSTGRES_URL must name the Postgres container}"

step() {  # step <deadline seconds> <script> <args...>: the outer timeout backs the script's own deadline
  local deadline=$1; shift
  echo "== $* (deadline ${deadline} s)" >&2
  timeout --kill-after=30 "$((deadline + 60))" uv run python "$@" --deadline "$deadline"
}

for engine in sqlite postgres; do
  step 3000 scripts/measure_calls.py --engine "$engine" --concurrent-calls 6
  step 900 scripts/measure_waits.py --engine "$engine"
  step 1200 scripts/measure_growth.py --engine "$engine"
  step 600 scripts/measure_pool.py --engine "$engine"
done
rm -rf "${L0_SCRATCH:?}"/*
