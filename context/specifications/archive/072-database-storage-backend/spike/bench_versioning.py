"""Version-chain spike (W3/R5): reconstruction latency and write-side cost.

Builds agent-edit-shaped version chains over real corpus docs at four size
tiers, then measures: compute_diff cost (the write side of create_version),
apply_diff throughput, reconstruction latency vs chain position for
snapshot intervals {5, 10, 20}, and stored bytes for the diff chain vs an
all-snapshots strategy.

Run: SPIKE_OUT=<dir> uv run python .../bench_versioning.py
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[4] / "src"))
from spikelib import DATA_DIR  # noqa: E402
from vfs.models.versioning import compute_diff, reconstruct_version  # noqa: E402

OUT_DIR = Path(os.environ.get("SPIKE_OUT", DATA_DIR))

CHAIN_LEN = 40
INTERVALS = [5, 10, 20]
SIZE_TIERS = [  # (label, chunks, truncate_bytes)
    ("1KB", 1, 1024),
    ("4KB", 1, None),
    ("32KB", 8, None),
    ("256KB", 64, None),
]
DOCS_PER_TIER = 5
SEED = 72


def load_tier_docs(
    conn: sqlite3.Connection, n_chunks: int, truncate: int | None, count: int
) -> list[str]:
    """Build *count* docs by concatenating *n_chunks* consecutive corpus chunks."""
    docs: list[str] = []
    rng = random.Random(SEED + n_chunks * 31 + (truncate or 0))
    for _ in range(count):
        start = rng.randrange(0, 400_000)
        rows = conn.execute(
            "SELECT content FROM docs WHERE id >= ? ORDER BY id LIMIT ?",
            (start, n_chunks),
        ).fetchall()
        text = "".join(r[0] for r in rows)
        if truncate is not None:  # line-aligned truncation for the small tier
            lines = text.splitlines(keepends=True)
            out, size = [], 0
            for ln in lines:
                out.append(ln)
                size += len(ln)
                if size >= truncate:
                    break
            text = "".join(out)
        docs.append(text)
    return docs


def agent_edit(content: str, rng: random.Random, version: int) -> str:
    """One agent-shaped edit: 1-3 hunks of replace/insert/delete."""
    lines = content.splitlines(keepends=True)
    if not lines:
        return content + f"# v{version}\n"
    for _ in range(rng.randint(1, 3)):
        kind = rng.random()
        at = rng.randrange(0, len(lines))
        span = min(rng.randint(1, 10), len(lines) - at)
        if kind < 0.6:  # replace: mutate the span in place
            repl = [f"{ln.rstrip()}  # edit v{version}\n" for ln in lines[at : at + span]]
            lines[at : at + span] = repl
        elif kind < 0.85:  # insert a few new lines
            new = [f"# inserted line {i} at v{version}\n" for i in range(rng.randint(1, 6))]
            lines[at:at] = new
        elif len(lines) > span:  # delete the span
            del lines[at : at + span]
    return "".join(lines)


def build_chain(base: str, rng: random.Random) -> list[str]:
    """Full content of versions 1..CHAIN_LEN."""
    contents = [base]
    for v in range(2, CHAIN_LEN + 1):
        contents.append(agent_edit(contents[-1], rng, v))
    return contents


def store_chain(contents: list[str], interval: int) -> list[tuple[bool, str]]:
    """(is_snapshot, stored) per version, mirroring create_version's rule."""
    stored: list[tuple[bool, str]] = []
    for i, cur in enumerate(contents):
        v = i + 1
        is_snap = v == 1 or v % interval == 0
        stored.append((True, cur) if is_snap else (False, compute_diff(contents[i - 1], cur)))
    return stored


def reconstruct_target(stored: list[tuple[bool, str]], target_v: int) -> str:
    """Replay from the nearest snapshot at or below target (the backend's read)."""
    snap_idx = max(i for i in range(target_v) if stored[i][0])
    return reconstruct_version(stored[snap_idx:target_v])


def bench_tier(label: str, docs: list[str]) -> dict:
    rng = random.Random(SEED)
    chains = [build_chain(d, rng) for d in docs]
    doc_bytes = statistics.mean(len(c[0]) for c in chains)

    # Write side: compute_diff cost per version (prev content in hand).
    diff_times: list[float] = []
    for contents in chains:
        for i in range(1, CHAIN_LEN):
            t0 = time.perf_counter()
            compute_diff(contents[i - 1], contents[i])
            diff_times.append(time.perf_counter() - t0)

    result: dict = {
        "tier": label,
        "avg_doc_bytes": int(doc_bytes),
        "compute_diff_ms": {
            "mean": statistics.mean(diff_times) * 1e3,
            "p99": statistics.quantiles(diff_times, n=100)[98] * 1e3,
        },
        "intervals": {},
    }

    for interval in INTERVALS:
        stored_chains = [store_chain(c, interval) for c in chains]
        # Reconstruction latency at every chain position, all docs.
        per_position: dict[int, list[float]] = {}
        for contents, stored in zip(chains, stored_chains):
            for v in range(1, CHAIN_LEN + 1):
                t0 = time.perf_counter()
                out = reconstruct_target(stored, v)
                dt = time.perf_counter() - t0
                assert out == contents[v - 1], f"mismatch v{v} interval {interval}"
                per_position.setdefault(v, []).append(dt)
        lat = {v: statistics.mean(ts) * 1e3 for v, ts in per_position.items()}
        worst_v = max(lat, key=lambda v: lat[v])
        diff_bytes = sum(len(s) for st in stored_chains for snap, s in st if not snap)
        snap_bytes = sum(len(s) for st in stored_chains for snap, s in st if snap)
        all_snap_bytes = sum(len(c) for ch in chains for c in ch)
        n_diffs_worst = worst_v - max(
            v for v in range(1, worst_v + 1) if v == 1 or v % interval == 0
        )
        result["intervals"][interval] = {
            "reconstruct_ms_mean": statistics.mean(lat.values()),
            "reconstruct_ms_worst": lat[worst_v],
            "worst_position": worst_v,
            "worst_n_diffs": n_diffs_worst,
            "stored_bytes": diff_bytes + snap_bytes,
            "all_snapshot_bytes": all_snap_bytes,
            "storage_ratio": (diff_bytes + snap_bytes) / all_snap_bytes,
        }
    return result


def main() -> None:
    conn = sqlite3.connect(DATA_DIR / "corpus.db")
    results = []
    for label, n_chunks, truncate in SIZE_TIERS:
        docs = load_tier_docs(conn, n_chunks, truncate, DOCS_PER_TIER)
        t0 = time.monotonic()
        r = bench_tier(label, docs)
        r["bench_seconds"] = round(time.monotonic() - t0, 1)
        results.append(r)
        print(
            f"{label:>6} ({r['avg_doc_bytes']:>7} B): "
            f"diff {r['compute_diff_ms']['mean']:.2f} ms | "
            + " | ".join(
                f"i{i}: worst {r['intervals'][i]['reconstruct_ms_worst']:.2f} ms "
                f"({r['intervals'][i]['worst_n_diffs']} diffs), "
                f"store {r['intervals'][i]['storage_ratio']:.2f}x"
                for i in INTERVALS
            ),
            flush=True,
        )
    out = OUT_DIR / "bench_versioning.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
