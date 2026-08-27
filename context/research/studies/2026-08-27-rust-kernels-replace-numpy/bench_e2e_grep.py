"""End-to-end ``DatabaseStorage.grep`` on the full linux store under three arms.

The index ladder's post-fetch algebra (site 2, which owns site 1) is
swapped per arm by monkeypatching ``grep_mod._index_doc_ids`` (the
fetch half is the live code in every arm) and ``grep_mod.np`` (the
allow-list intersect in ``grep_rows``). Everything else — planner,
blob fetch, entry resolution, content fetch, the Rust verify — is the
live tree. Stage timers wrap the live functions so the memo can say
what share of user-visible latency the numpy sites are.

    uv run --project <repo> --with <wheel> python bench_e2e_grep.py
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
from array import array
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import vfs_kernels_rs as rs

import kernels_py as kp
import vfs.storage.backends.database.grep as grep_mod
from benchlib import DB, dump, machine
from vfs.storage.backends.database import DatabaseStorage

RUNS = 3
QUERIES = [
    ("zero_hit", "xyzzy_no_such_symbol_42", {}),
    ("rare_ident", "randomize_kstack_offset", {}),
    ("medium_ident", "kmalloc", {}),
    ("word_heavy", "pr_debug", {"word_regexp": True}),
    ("regex_probe", r"static\s+int\s+\w+_probe", {}),
    ("punct_neq_null", "!= NULL", {}),
    ("hot_ident", "return", {}),
    ("scoped_medium", "kmalloc", {"globs": ("/drivers/net/**",)}),
]

stage: dict[str, float] = {}


class IdSeq:
    """The minimal ``DocIds`` surface ``grep_rows`` touches: size, slice, tolist."""

    __slots__ = ("_seq",)

    def __init__(self, seq) -> None:
        self._seq = seq

    @property
    def size(self) -> int:
        return len(self._seq)

    def __getitem__(self, s):
        return IdSeq(self._seq[s])

    def tolist(self) -> list[int]:
        return list(self._seq)


class FakeNp:
    """``grep_rows``' three numpy touches, served by the arm's kernel."""

    int64 = np.int64

    def __init__(self, arm: str) -> None:
        self.arm = arm

    def empty(self, n, dtype=None):
        return IdSeq([]) if self.arm == "stdlib" else IdSeq(array("q"))

    def asarray(self, seq, dtype=None):
        ids = sorted(seq)
        return IdSeq(ids) if self.arm == "stdlib" else IdSeq(array("q", ids))

    def intersect1d(self, a, b, assume_unique=False):
        if self.arm == "stdlib":
            return IdSeq(sorted(kp.intersect_sorted(a.tolist(), b.tolist())))
        out = array("q")
        out.frombytes(rs.intersect_sorted(a._seq.tobytes(), b._seq.tobytes()))
        return IdSeq(out)


live_index_doc_ids = grep_mod._index_doc_ids
live_entries = grep_mod._entries_for_docs
live_content = grep_mod._content_for_entries
live_np = grep_mod.np


def make_index_doc_ids(arm: str):
    async def index_doc_ids(session, tables, membership_budget, epoch, plan, deadline, allow_size):
        t0 = time.perf_counter()
        if arm == "numpy":
            out = await live_index_doc_ids(session, tables, membership_budget, epoch, plan, deadline, allow_size)
            stage["index_total"] = stage.get("index_total", 0.0) + (time.perf_counter() - t0)
            return out
        if epoch is None:
            return IdSeq([])
        groups = grep_mod._plan_groups(plan)
        grams = sorted({g for group in groups for g in group})
        meta = await grep_mod._posting_meta(session, tables, membership_budget, epoch, grams)
        chosen = grep_mod._choose_grams(groups, meta)
        if allow_size is not None and grep_mod._ladder_defers(chosen, meta, allow_size):
            return None
        wanted = sorted({g for gc in chosen if gc for g in gc})
        blobs = await grep_mod._posting_blobs(session, tables, membership_budget, epoch, wanted)
        t1 = time.perf_counter()
        parts = []
        for gc in chosen:
            if monotonic() > deadline:
                break
            if not gc:
                continue
            group_blobs = [blobs[g] for g in gc]
            parts.append(kp.intersect_rarest(group_blobs) if arm == "stdlib" else rs.intersect_rarest(group_blobs))
        if arm == "stdlib":
            out = IdSeq(kp.union_sorted(parts) if parts else [])
        else:
            merged = array("q")
            merged.frombytes(rs.union_sorted(parts) if parts else b"")
            out = IdSeq(merged)
        now = time.perf_counter()
        stage["index_algebra"] = stage.get("index_algebra", 0.0) + (now - t1)
        stage["index_total"] = stage.get("index_total", 0.0) + (now - t0)
        return out

    return index_doc_ids


async def timed_entries(*args, **kwargs):
    t0 = time.perf_counter()
    out = await live_entries(*args, **kwargs)
    stage["entries"] = stage.get("entries", 0.0) + (time.perf_counter() - t0)
    return out


async def timed_content(*args, **kwargs):
    t0 = time.perf_counter()
    out = await live_content(*args, **kwargs)
    stage["content"] = stage.get("content", 0.0) + (time.perf_counter() - t0)
    return out


async def one(storage, pattern, kwargs):
    stage.clear()
    t0 = time.perf_counter()
    result = await storage.grep(pattern=pattern, **kwargs)
    total = time.perf_counter() - t0
    assert result.success, result.errors
    lines = sum(len(o.matches or ()) for o in result.observations)
    warnings = [e.message for e in result.errors] if result.errors else []
    return total, lines, len(result.observations), dict(stage), warnings


async def main() -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    grep_mod._entries_for_docs = timed_entries
    grep_mod._content_for_entries = timed_content
    rows = []
    for label, pattern, kwargs in QUERIES:
        arms_out = {}
        counts = set()
        for arm in ("numpy", "stdlib", "rust"):
            grep_mod._index_doc_ids = make_index_doc_ids(arm)
            grep_mod.np = live_np if arm == "numpy" else FakeNp(arm)
            samples = []
            await one(storage, pattern, kwargs)  # warm
            for _ in range(RUNS):
                samples.append(await one(storage, pattern, kwargs))
            counts.add((samples[0][1], samples[0][2]))
            med = statistics.median(s[0] for s in samples)
            stages = {k: statistics.median(s[3].get(k, 0.0) for s in samples) for k in ("index_total", "index_algebra", "entries", "content")}
            arms_out[arm] = {
                "total_s": round(med, 4),
                "index_total_ms": round(stages["index_total"] * 1000, 2),
                "index_algebra_ms": round(stages["index_algebra"] * 1000, 2),
                "entries_ms": round(stages["entries"] * 1000, 2),
                "content_ms": round(stages["content"] * 1000, 2),
                "lines": samples[0][1],
                "files": samples[0][2],
                "warnings": samples[0][4],
            }
        assert len(counts) == 1, (label, counts)
        rows.append({"label": label, "pattern": pattern, "kwargs": {k: list(v) if isinstance(v, tuple) else v for k, v in kwargs.items()}, "arms": arms_out})
        n, s, r = arms_out["numpy"], arms_out["stdlib"], arms_out["rust"]
        print(
            f"{label:<15} files={n['files']:>6} lines={n['lines']:>7} | total np={n['total_s']:.3f}s py={s['total_s']:.3f}s "
            f"rs={r['total_s']:.3f}s | index np={n['index_total_ms']:.1f} py={s['index_total_ms']:.1f} (alg {s['index_algebra_ms']:.1f}) "
            f"rs={r['index_total_ms']:.1f} (alg {r['index_algebra_ms']:.2f}) ms | entries={n['entries_ms']:.0f} content={n['content_ms']:.0f} ms "
            f"{n['warnings']}",
            flush=True,
        )
    grep_mod._index_doc_ids = live_index_doc_ids
    grep_mod._entries_for_docs = live_entries
    grep_mod._content_for_entries = live_content
    grep_mod.np = live_np
    await storage.close()
    dump("e2e_grep.json", {"machine": machine(), "runs": RUNS, "rows": rows})


asyncio.run(main())
