#!/bin/zsh
cd /Users/claygendron/Git/Repos/vfs
SP=/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/347b653a-7845-4856-b8cd-ee69edeba111/scratchpad/conformance
: > $SP/ab2_summary.log
PYTHONPATH=$SP/plugin uv run --no-sync pytest tests/storage/test_conformance.py::TestMemoryConformance -p vfs_verbseq_plugin -p no:cov -q --no-header -p no:cacheprovider > $SP/verbseq_memory.log 2>&1
sed -n '/verb sequence/,$p' $SP/verbseq_memory.log >> $SP/ab2_summary.log
run() {
  PYTHONPATH=$SP/plugin uv run --no-sync pytest tests/storage/test_conformance.py::TestSqliteConformance -p vfs_timing_plugin -p no:cov -q --no-header -p no:cacheprovider > $SP/ab2_$1.log 2>&1
  echo "$1 $(grep -E 'passed|failed|error' $SP/ab2_$1.log | tail -1) $(grep -E 'protocol wall|protocol cpu' $SP/ab2_$1.log | tr -s ' ' | tr '\n' ' ') $(uptime | sed 's/.*load averages: //')" >> $SP/ab2_summary.log
}
run syncfull_base
sed -i '' 's/"PRAGMA synchronous = FULL"/"PRAGMA synchronous = OFF"/' src/vfs/storage/backends/database/dialects.py
run syncoff
cp $SP/dialects.py.bak src/vfs/storage/backends/database/dialects.py
run syncfull_base2
sed -i '' 's/"PRAGMA synchronous = FULL"/"PRAGMA synchronous = OFF"/' src/vfs/storage/backends/database/dialects.py
run syncoff2
cp $SP/dialects.py.bak src/vfs/storage/backends/database/dialects.py
echo done >> $SP/ab2_summary.log
