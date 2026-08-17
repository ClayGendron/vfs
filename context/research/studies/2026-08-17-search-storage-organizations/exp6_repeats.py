"""Experiment 6: repeat rates in the observed agent search workload.

The spec-104 study's raw dataset is NOT in the repo — mine_usage.py re-mines
~/.claude/projects/**/*.jsonl on this machine each run. This script reuses
that study's parser (imported read-only from the studies directory) but
keeps per-call timestamps and session files, then computes exact-repeat
(pattern+scope), pattern-only repeat, and time locality (same session /
within 1h).
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(
    0, "/Users/claygendron/Git/Repos/vfs/context/research/studies/2026-08-17-path-indexing-prior-art"
)
from mine_usage import PROJECTS, extract_bash_searches  # noqa: E402

from common import OUT  # noqa: E402

records = []  # (ts or None, session_file, pattern, scope_key)
n_bash = 0
seen_ids: set[str] = set()
for f in sorted(PROJECTS.rglob("*.jsonl")):
    try:
        fh = f.open("r", encoding="utf-8", errors="replace")
    except OSError:
        continue
    with fh:
        for line in fh:
            if '"tool_use"' not in line or '"Bash"' not in line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = obj.get("message")
            if not isinstance(msg, dict) or not isinstance(msg.get("content"), list):
                continue
            ts = obj.get("timestamp")
            when = None
            if isinstance(ts, str):
                try:
                    when = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    pass
            for b in msg["content"]:
                if not isinstance(b, dict) or b.get("type") != "tool_use" or b.get("name") != "Bash":
                    continue
                tid = b.get("id")
                if tid:
                    if tid in seen_ids:
                        continue
                    seen_ids.add(tid)
                n_bash += 1
                inp = b.get("input") or {}
                cmd = inp.get("command") if isinstance(inp, dict) else None
                if not isinstance(cmd, str):
                    continue
                for rec in extract_bash_searches(cmd):
                    if rec.get("stream_filter"):
                        continue
                    pattern = rec.get("pattern")
                    scope = (
                        tuple(sorted(rec.get("globs", []))),
                        tuple(sorted(rec.get("paths", []))),
                        tuple(sorted(rec.get("types", []))),
                        bool(rec.get("ci")),
                    )
                    records.append((when, str(f), pattern, scope))

n = len(records)
print(f"bash tool calls: {n_bash:,}; file-search invocations: {n:,}")

# Repeat rates: a call is a repeat if its key appeared earlier (global order
# by timestamp where present, else file order).
records.sort(key=lambda r: (r[0] is None, r[0] or 0.0))
exact_seen: dict = {}
pat_seen: dict = {}
exact_repeats = 0
pattern_repeats = 0
exact_same_session = 0
exact_within_1h = 0
pat_within_1h = 0
with_pattern = 0
for when, session, pattern, scope in records:
    if pattern is None:
        continue
    with_pattern += 1
    ek = (pattern, scope)
    if ek in exact_seen:
        exact_repeats += 1
        pw, psession = exact_seen[ek]
        if psession == session:
            exact_same_session += 1
        if when is not None and pw is not None and when - pw <= 3600:
            exact_within_1h += 1
    if pattern in pat_seen:
        pattern_repeats += 1
        pw, _ = pat_seen[pattern]
        if when is not None and pw is not None and when - pw <= 3600:
            pat_within_1h += 1
    exact_seen[ek] = (when, session)
    pat_seen[pattern] = (when, session)

top_exact = Counter((p, s) for _w, _f, p, s in records if p is not None).most_common(8)
have_ts = sum(1 for r in records if r[0] is not None)
out = {
    "raw_dataset_in_repo": False,
    "note": "re-mined live from ~/.claude/projects (same source the memo used)",
    "bash_calls": n_bash,
    "search_invocations": n,
    "with_pattern": with_pattern,
    "with_timestamp": have_ts,
    "exact_repeats": exact_repeats,
    "exact_repeat_rate": exact_repeats / with_pattern,
    "pattern_repeats": pattern_repeats,
    "pattern_repeat_rate": pattern_repeats / with_pattern,
    "exact_repeat_same_session": exact_same_session,
    "exact_repeat_within_1h": exact_within_1h,
    "pattern_repeat_within_1h": pat_within_1h,
    "top_exact": [
        {"pattern": p, "globs": s[0], "paths": s[1], "n": c} for (p, s), c in top_exact
    ],
}
for k, v in out.items():
    if k != "top_exact":
        print(f"{k:28s}: {v}")
for t in out["top_exact"]:
    print("  ", t["n"], repr(t["pattern"])[:60], t["paths"][:2])
with open(f"{OUT}/exp6_repeats.json", "w") as f:
    json.dump(out, f, indent=1)
