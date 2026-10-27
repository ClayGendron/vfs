"""Parse every corpus command with (a) Python's shlex as a floor and (b) just-bash-py.

One JSON line per (id, dialect); a 20 s alarm per command records a hang.
Run from the vfs root:  uv run python -I .../run_py.py corpus.jsonl
"""

from __future__ import annotations

import json
import shlex
import signal
import sys
from pathlib import Path

sys.path.insert(0, "/Users/claygendron/Git/Repos/just-bash-py/src")
from just_bash.parser import parse as jbpy_parse  # noqa: E402


class Hang(Exception):
    pass


def _alarm(signum, frame):  # noqa: ARG001
    raise Hang("TIMEOUT (parser hang)")


signal.signal(signal.SIGALRM, _alarm)
rows = [json.loads(l) for l in Path(sys.argv[1]).read_text().splitlines() if l.strip()]
for r in rows:
    try:
        shlex.split(r["cmd"])
        print(json.dumps({"id": r["id"], "dialect": "shlex", "ok": True}))
    except ValueError as e:
        print(json.dumps({"id": r["id"], "dialect": "shlex", "ok": False, "error": str(e)}))
    signal.alarm(20)
    try:
        jbpy_parse(r["cmd"])
        print(json.dumps({"id": r["id"], "dialect": "just-bash-py", "ok": True}))
    except Exception as e:  # noqa: BLE001 - any parser failure is the datum
        print(json.dumps({"id": r["id"], "dialect": "just-bash-py", "ok": False, "error": f"{type(e).__name__}: {e}"}))
    finally:
        signal.alarm(0)
    sys.stdout.flush()
