"""Assert the Rust tokenizer is byte-identical to ``vfs.models.lexical.tokenize``
over every covered chunk of the store; time the Python pass while at it.

    uv run --no-sync python tokenizer_parity.py
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import time

from common import RUSTBENCH, SCAN, SCRATCH, STORE, dump_json
from vfs.models.lexical import tokenize


def main() -> None:
    dump = SCRATCH / "rust_tokens.txt"
    t0 = time.perf_counter()
    rust_stat = subprocess.run([str(RUSTBENCH), "tokens", str(STORE), str(dump)], check=True, capture_output=True, text=True).stdout
    rust_wall = time.perf_counter() - t0
    rust_tokens: dict[int, list[str]] = {}
    current: list[str] | None = None
    with dump.open(encoding="utf-8") as fh:
        for line in fh:
            line = line[:-1]
            if line.startswith("#") and line[1:].isdigit():
                current = rust_tokens.setdefault(int(line[1:]), [])
            else:
                assert current is not None
                current.append(line)
    store = sqlite3.connect(STORE)
    divergences: list[dict] = []
    n_chunks = n_tokens = 0
    py_seconds = 0.0
    for chunk_id, _entry_id, content in store.execute(SCAN):
        t1 = time.perf_counter()
        expected = tokenize(content)
        py_seconds += time.perf_counter() - t1
        got = rust_tokens.get(chunk_id)
        n_chunks += 1
        n_tokens += len(expected)
        if got != expected:
            first = next((i for i, (a, b) in enumerate(zip(expected, got or [])) if a != b), min(len(expected), len(got or [])))
            divergences.append({"chunk_id": chunk_id, "index": first, "expected": expected[first : first + 3], "got": (got or [])[first : first + 3], "len_expected": len(expected), "len_got": len(got or [])})
            if len(divergences) >= 20:
                break
    payload = {
        "chunks": n_chunks,
        "tokens": n_tokens,
        "python_tokenize_s": round(py_seconds, 3),
        "rust_tokens_cmd_wall_s": round(rust_wall, 3),
        "rust_report": rust_stat.strip(),
        "divergent_chunks": len(divergences),
        "divergences": divergences,
        "identical": not divergences and len(rust_tokens) == n_chunks,
    }
    out = dump_json("tokenizer_parity.json", payload)
    print({k: v for k, v in payload.items() if k != "divergences"}, out)
    if divergences:
        print(divergences[:5])
        sys.exit(1)


if __name__ == "__main__":
    main()
