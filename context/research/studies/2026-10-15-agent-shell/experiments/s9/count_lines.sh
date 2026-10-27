#!/usr/bin/env bash
# Count source lines by top-level area for each peer repo (read-only).
# Usage: count_lines.sh > loc.txt
set -u
ROOT=~/Git/Repos
count() {
  # $1 repo, $2 dir (relative), $3 extension glob (find -name pattern)
  local repo=$1 dir=$2 pat=$3
  local n
  n=$(find "$ROOT/$repo/$dir" -type f -name "$pat" \
        -not -path '*/node_modules/*' -not -path '*/target/*' -not -path '*/dist/*' \
        -not -path '*/.venv/*' -not -path '*/__pycache__/*' 2>/dev/null \
      | xargs cat 2>/dev/null | wc -l | tr -d ' ')
  local f
  f=$(find "$ROOT/$repo/$dir" -type f -name "$pat" \
        -not -path '*/node_modules/*' -not -path '*/target/*' -not -path '*/dist/*' \
        -not -path '*/.venv/*' -not -path '*/__pycache__/*' 2>/dev/null | wc -l | tr -d ' ')
  printf '%-14s %-55s %-8s %8s lines %5s files\n' "$repo" "$dir" "$pat" "$n" "$f"
}
for repo in just-bash bashkit just-bash-py lifo amla-sandbox; do
  echo "=== $repo @ $(cd $ROOT/$repo && git rev-parse --short HEAD)"
done
echo
echo "--- just-bash (TypeScript)"
for d in packages/just-bash/src/parser packages/just-bash/src/interpreter packages/just-bash/src/commands \
         packages/just-bash/src/fs packages/just-bash/src/network packages/just-bash/src/utils \
         packages/just-bash/src/python packages/just-bash/src/shell-commands packages/just-bash/src \
         packages/bash-tool/src packages/executor/src packages/benchmark packages/toolpacks examples; do
  [ -d "$ROOT/just-bash/$d" ] && count just-bash "$d" '*.ts'
done
count just-bash packages/just-bash/src '*.test.ts'
count just-bash packages/just-bash/src '*.sh'
echo
echo "--- bashkit (Rust)"
for d in crates; do :; done
for d in $(cd $ROOT/bashkit && ls -d crates/*/ 2>/dev/null); do count bashkit "$d" '*.rs'; done
for d in $(cd $ROOT/bashkit && ls -d crates/bashkit/src/*/ 2>/dev/null); do count bashkit "$d" '*.rs'; done
count bashkit crates '*.py'
count bashkit contracts '*'
count bashkit docs '*.md'
echo
echo "--- just-bash-py (Python)"
for d in $(cd $ROOT/just-bash-py && ls -d src/*/*/ 2>/dev/null); do count just-bash-py "$d" '*.py'; done
count just-bash-py src '*.py'
count just-bash-py tests '*.py'
echo
echo "--- lifo (TypeScript)"
for d in $(cd $ROOT/lifo && ls -d packages/*/ 2>/dev/null); do count lifo "$d" '*.ts'; done
for d in $(cd $ROOT/lifo && ls -d packages/lifo-core/src/*/ 2>/dev/null); do count lifo "$d" '*.ts'; done
count lifo packages '*.test.ts'
echo
echo "--- amla-sandbox (Python side only)"
for d in $(cd $ROOT/amla-sandbox && ls -d src/*/ 2>/dev/null); do count amla-sandbox "$d" '*.py'; done
count amla-sandbox tests '*.py'
count amla-sandbox docs '*.md'
