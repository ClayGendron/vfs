#!/bin/bash
set -e
cd /private/tmp/claude-501/verif-03/repro
export SOURCE_DATE_EPOCH=$(git -C /Users/claygendron/Git/Repos/vfs log -1 --format=%ct)
echo "SDE=$SOURCE_DATE_EPOCH"
for d in a b; do
  ( cd $d && time uvx --from 'maturin>=1.8.4,<2.0' maturin build --release --out ../out-$d -q ) 2>&1 | tail -4
done
uvx --from 'maturin>=1.8.4,<2.0' maturin --version
shasum -a 256 out-a/*.whl out-b/*.whl
