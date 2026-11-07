"""Run every mechanism in every setting, each in its own subprocess with a 15 s deadlock deadline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mechanisms import MECHANISMS

HERE = Path(__file__).parent
SETTINGS = ["s1_sync", "s2_sync", "s2_async", "s3_worker"]
EXTRA = {"greenback": ["s2_sync_portal"], "lazy_greenback": ["s2_sync_portal"], "sqla_await_only": ["s2_sync_spawned"]}

rows = []
for name in MECHANISMS:
    for setting in SETTINGS + EXTRA.get(name, []):
        try:
            proc = subprocess.run(
                [sys.executable, str(HERE / "run_one.py"), name, setting],
                capture_output=True, text=True, timeout=15, cwd=HERE,
            )
            line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "{}"
            row = json.loads(line)
            if not row:
                row = {"mechanism": name, "setting": setting, "raised": proc.stderr.strip()[-300:]}
            row["stderr_tail"] = [s for s in proc.stderr.splitlines() if "never awaited" in s or "Error" in s][:3]
        except subprocess.TimeoutExpired:
            row = {"mechanism": name, "setting": setting, "raised": "HANG: no result within 15 s"}
        rows.append(row)
        print(json.dumps(row))

(HERE / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
