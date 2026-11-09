#!/bin/sh
# Lines of the six largest Python modules and the two largest Rust files at each
# landing commit since 2026-10-31, read with `git show`, so the memo has a trend.
cd "$(git rev-parse --show-toplevel)" || exit 1
files="src/vfs/base.py src/vfs/storage/backends/database/backend.py src/vfs/storage/backends/database/rights.py src/vfs/storage/backends/database/reads.py src/vfs/storage/backends/database/writes.py src/vfs/storage/backends/database/glean.py src/vfs/pattern_matching/glob.py src/vfs/storage/backends/database/offload.py crates/vfs-core/src/python.rs crates/vfs-core/src/glob.rs"
printf '%-10s %-10s' commit date
for f in $files; do printf ' %-9s' "$(basename "$f" | cut -c1-9)"; done; echo
for c in $(git log --since=2026-10-31 --first-parent --format=%h --reverse) WORKTREE; do
  if [ "$c" = WORKTREE ]; then date=now; else date=$(git show -s --format=%ad --date=short "$c"); fi
  printf '%-10s %-10s' "$c" "$date"
  for f in $files; do
    if [ "$c" = WORKTREE ]; then n=$(wc -l < "$f" 2>/dev/null || echo 0); else n=$(git show "$c:$f" 2>/dev/null | wc -l); fi
    printf ' %9s' "$n"
  done; echo
done
