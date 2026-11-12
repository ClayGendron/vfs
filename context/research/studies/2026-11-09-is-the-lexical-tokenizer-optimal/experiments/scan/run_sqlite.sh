#!/bin/zsh
# Run every scan variant on a fresh copy of the clean 100,000-file SQLite store, one process each.
# Usage: run_sqlite.sh <base db> <scratch dir> <out dir> [variant ...]
set -u
BASE=$1; SCRATCH=$2; OUT=$3; shift 3
HERE=${0:a:h}
REPO=${HERE:h:h:h:h:h:h}
VARIANTS=("$@")
if [[ ${#VARIANTS[@]} -eq 0 ]]; then
  VARIANTS=(scalar_subquery keyset_1024 keyset_4096 keyset_16384 twophase twophase_1000 stream_buffered prefilter_temp prefilter_set exists_subquery)
fi
mkdir -p "$SCRATCH/logs" "$OUT"
for v in "${VARIANTS[@]}"; do
  echo "[$(date +%H:%M:%S)] variant $v"
  (cd "$REPO" && uv run python "$HERE/harness.py" --engine sqlite --source "$BASE" --scratch "$SCRATCH" --variant "$v" --out "$OUT/sqlite_$v.json") > "$SCRATCH/logs/sqlite_$v.log" 2>&1
  grep -E "^reindex:|^scan:|build.lexical_total|^checksum" "$SCRATCH/logs/sqlite_$v.log" | cut -c1-400
done
echo "[$(date +%H:%M:%S)] done"
