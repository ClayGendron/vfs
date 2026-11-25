#!/usr/bin/env bash
# Print the shell corpus score: cases passing over cases total, by area and in all.
# `--write` rewrites tests/shell/known_failures.txt from the run.
set -euo pipefail
cd "$(dirname "$0")/.."
exec cargo run -q --release -p vfs-shell --example score -- "$@"
