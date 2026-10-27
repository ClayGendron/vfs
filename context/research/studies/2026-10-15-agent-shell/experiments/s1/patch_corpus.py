"""One-off: rebalance corpus.jsonl toward the e2 construct shares (keyed by id)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PATCH = {
    2: "grep -n \"def route(\" src/vfs/base.py | head -20",
    10: "ls -la context/research/studies/2026-10-15-agent-shell/experiments/*/ | head -30",
    14: "git log -1 --format='%H %s' > /tmp/x/head.txt; cat /tmp/x/head.txt; echo \"pwd=$PWD\"",
    23: "cd /Users/claygendron/Git/Repos/vfs && scripts/ci.sh 2>&1 | tail -30; echo \"ci exit=${PIPESTATUS[0]}\"",
    25: "grep -c \"def \" src/vfs/*.py | sort -t: -k2 -n",
    27: "grep -rn \"TODO\\|FIXME\" src/ tests/ --include=*.py | wc -l",
    32: "ls \"$HOME/Git/Repos\" | head -80; echo \"n=`ls ~/Git/Repos | wc -l`\"",
    33: "cat <<'EOF' > /tmp/x/probe.py\nimport json, sys\nprint(json.dumps({\"argv\": sys.argv}))\nEOF\nuv run python -I /tmp/x/probe.py a b | head",
    34: "cd ~/Git/Repos/oils && git log -1 --format='%h %cs' && grep -c \"^#### \" spec/*.test.sh | tail -3",
    36: "psql \"$VFS_TEST_POSTGRES_URL\" <<'EOF' | head -20\nSELECT count(*) FROM vfs_entries;\nEOF",
    40: "sed -i '' 's/^Status: proposed$/Status: accepted/' context/decisions/080-*.md && grep -n \"^Status\" context/decisions/080-*.md | head",
    41: "perl -0pi -e 's/def _route_single\\(self, op\\)/def _route_single(self, op, *, path)/' src/vfs/base.py && uv run ruff check src/vfs/base.py | tail -3",
    42: "S=/Users/claygendron/Git/Repos/vfs/context/research/studies/2026-10-15-agent-shell/experiments/s1; mkdir -p \"$S\" && ls \"$S\"",
    43: "cp context/specs/active/152-*/spec.md /tmp/x/spec-152.md && head -20 /tmp/x/spec-152.md | cut -c1-120",
    44: "for d in scratch out logs; do rm -rf \"/tmp/x/$d\" && mkdir -p \"/tmp/x/$d\"; done; rm -f /tmp/x/*.log",
    46: "git status --short | head -5 && git add -A && git commit -q -m \"feat(storage): the permission ladder gains list, add and contribute\" && git log --oneline -1",
    50: "cat <<'EOF' | uv run python -\nimport vfs\nprint(vfs.__version__)\nEOF",
    54: "unset VFS_TEST_POSTGRES_URL VFS_TEST_MSSQL_URL; echo \"pg=${VFS_TEST_POSTGRES_URL:-unset}\"; uv run pytest -q | tail -2",
    60: "(cd crates/vfs-core && cargo test | tail -5); echo \"exit=$?\"",
    65: "grep -n \"class .*Error\\|def kind_family(\" src/vfs/results/*.py > /tmp/x/kinds-defs.txt; cat /tmp/x/kinds-defs.txt | head",
    67: "grep -rn \"def test_.*(\" tests/storage/test_grep*.py | cut -d: -f2 | head -3",
    76: "uv run python - <<'EOF' | head\nfrom pathlib import Path\nfor p in sorted(Path('context/decisions').glob('08*.md')):\n    print(p.name)\nEOF",
    81: "if [ -f /tmp/x/ci.log ]; then tail -5 /tmp/x/ci.log | cut -c1-200; else echo \"no log\"; fi",
    91: "grep -rn \"import numpy\\|np\\.\\(array\\|asarray\\)\" src/ pyproject.toml | head; echo \"exit=$?\"",
    92: "cut -c1-160 < /tmp/x/long.txt | head -40",
    94: "for d in .venv target crates/vfs-core/target; do du -sh \"$d\" 2>/dev/null; done | sort -h",
    98: "grep -n \"set -o \\(pipefail\\|errexit\\)\" ~/Git/Repos/oils/spec/errexit*.test.sh | head -20",
}

path = Path(sys.argv[1])
rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
for r in rows:
    if r["id"] in PATCH:
        r["cmd"] = PATCH[r["id"]]
path.write_text("".join(json.dumps(r) + "\n" for r in rows))
print("patched", len(PATCH))
