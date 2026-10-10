#!/bin/zsh
cd /Users/claygendron/Git/Repos/vfs
SP=/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/347b653a-7845-4856-b8cd-ee69edeba111/scratchpad/conformance
run() { # $1 label $2 class
  PYTHONPATH=$SP/plugin uv run --no-sync pytest tests/storage/test_conformance.py::$2 -p vfs_timing_plugin -p no:cov -q --no-header -p no:cacheprovider > $SP/ab_$1_$2.log 2>&1
  echo "$1 $2 $(grep -E 'passed|failed|error' $SP/ab_$1_$2.log | tail -1) $(grep -E 'protocol wall|protocol cpu|statements' $SP/ab_$1_$2.log | tr -s ' ' | tr '\n' ' ') $(uptime | sed 's/.*load averages: //')" >> $SP/ab_summary.log
}
: > $SP/ab_summary.log
for round in 1 2; do
  for cls in TestMemoryConformance TestSqliteConformance; do
    cp $SP/test_conformance.py.bak tests/storage/test_conformance.py; run base$round $cls
    cp $SP/test_conformance.py.template tests/storage/test_conformance.py; run tmpl$round $cls
  done
done
# stacked: template fixtures + engine skip-create variant
cp $SP/engine.py.skipcreate src/vfs/storage/backends/database/engine.py
for cls in TestMemoryConformance TestSqliteConformance; do run tmplskip $cls; done
cp $SP/engine.py.bak src/vfs/storage/backends/database/engine.py
cp $SP/test_conformance.py.bak tests/storage/test_conformance.py
echo done >> $SP/ab_summary.log
