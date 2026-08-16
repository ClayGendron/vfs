"""Linux-tree grep benchmark: vfs indexed grep vs ripgrep vs grep -E.

One corpus, three tools. The UTF-8 text files of a linux checkout are
mirrored into a scratch tree (so all three tools search byte-identical
inputs — no .git, no binaries), written into a file-backed sqlite
``DatabaseStorage``, and reindexed once. Each query then runs on:

- **vfs** — ``DatabaseStorage.grep`` through the live pipeline (index
  candidates, budgets, Python verify), in-process, median of 3;
- **rg**  — ``rg -uu --line-number --no-heading`` over the mirror
  (multithreaded, the field ceiling), median of 3;
- **grep** — ``/usr/bin/grep -rEn`` over the mirror (the single-thread
  baseline), median of 3.

Every query is pre-flight checked against ``build_code_gram_query`` —
only patterns the planner can index (no ``GramAny``, no ``allow_scan``)
are admitted, per the study's question: how does the *indexed* tier
compare on patterns vfs actually serves. Word/fixed/case modes ride the
tools' native flags (``-w``/``-F``/``-i`` vs ``word_regexp``/
``fixed_strings``/``case_mode``); the two regex spellings differ only
where POSIX ERE lacks perl classes (``\\s`` → ``[[:space:]]``).

Matching-line counts are reported per tool as the parity check;
divergences are printed loudly, and vfs budget-truncation warnings are
flagged in the table.

Env knobs: ``LINUX`` (checkout path, default ``~/Git/Repos/linux``),
``WORKDIR`` (scratch root; mirror and sqlite are reused across runs via
marker files — delete the markers to rebuild), ``RUNS`` (per-tool
repetitions, default 3), ``TOOLS`` (comma list from ``vfs,rg,grep``,
default all three — skipped legs print ``-``), ``RG_ROOT`` (run the rg
leg over this tree instead of the mirror, with ``.git`` excluded — the
ecologically honest baseline on machines where scratch-mirror file
opens carry extra kernel tax; counts may then differ from vfs by rg's
own binary-file handling).

Landed-run record (2026-08-16, linux checkout ``faeab1661``, 93,760
text files / 1.59 GB, sqlite file store, M-series laptop, vfs+rg legs;
the grep leg was skipped by request). Build: write 45 s, reindex 672 s
(~2.4 MB/s — the pure-Python trigram extraction loop dominates; named
improvement target), db 5.0 GB. Queries, median of 3: selective
literals and every spec-100-rescued class (group/factored alternation,
anchored group, classes, ``-O[0-3]``) answer in 0.7–2.0 s; hot
literals 1.8–2.4 s; verify-heavy rows (word mode, hot alternation)
4.7–5.9 s; the wrapped wildcard ``.*alloc_page.*`` is the recorded
outlier at 102 s (common-trigram conjunction admits a huge candidate
set, then the leading-``.*`` Python verify pays per line). Nine hot
rows truncated at the 4 MB candidate budget with the designed loud
warning — every vfs/rg count divergence coincides with a truncation
flag; all 16 untruncated rows match rg line-for-line. Also recorded:
a ~700 ms fixed per-call floor at this corpus size (ladder's zero-hit
was 1.7 ms at 10K docs) — second named improvement target,
unattributed as of this run.

The rg leg needed three passes to be honest (all medians recorded in
this file's history): over the scratch mirror, rg burned ~44 s of
*system* time per query (~4.4 s wall at 900% CPU) — ruled out as
sandbox overhead (identical unsandboxed) and as provenance-xattr cost
(stripping bought ~1 s); a sequential ``cat`` of the same mirror
costs only 3.7 s system, so the tax is specific to rg's parallel
opens under the scratch path and stays unattributed. The recorded
honest baseline runs rg where users run it — the original checkout
via ``RG_ROOT`` with ``.git`` excluded: **3.0–3.6 s per query,
selectivity-independent** (the 94K-file tree walk dominates; macOS
APFS), with row counts identical to the mirror run on all 25 queries.
Net: vfs answers selective queries 3–5× ahead of rg on this machine
(0.7–1.0 s vs ~3.4 s), hot literals ~1.5–1.9×, loses on verify-heavy
rows (4.9–5.9 s), and loses badly on the wrapped-wildcard pathology
(102 s).

Run:  WORKDIR=/path/to/scratch uv run python \
      context/research/studies/2026-08-16-linux-grep-benchmark/benchmark.py
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path as OsPath

from vfs.models import Entry
from vfs.models.code_grams import build_code_gram_query
from vfs.paths import Path
from vfs.results import Severity
from vfs.storage.backends.database import DatabaseStorage

LINUX = OsPath(os.environ.get("LINUX", str(OsPath.home() / "Git/Repos/linux")))
WORKDIR = OsPath(os.environ.get("WORKDIR") or tempfile.mkdtemp(prefix="vfs-linux-bench-"))
RUNS = int(os.environ.get("RUNS", "3"))
TOOLS = frozenset(os.environ.get("TOOLS", "vfs,rg,grep").split(","))
GREP = "/usr/bin/grep"
RG = "rg"
BATCH_ENTRIES = 500
BATCH_BYTES = 32_000_000

# (label, vfs pattern, grep -E spelling, extra flags, vfs kwargs).
# Flags map to native modes on all three tools; None grep-pattern means
# same spelling as vfs. All patterns must plan indexable (pre-flighted).
QUERIES: tuple[tuple[str, str, str | None, tuple[str, ...], dict], ...] = (
    ("zero-hit", "xyzzy_no_such_symbol_42", None, (), {}),
    ("rare literal", "randomize_kstack_offset", None, (), {}),
    ("medium literal", "raw_spin_lock_irqsave", None, (), {}),
    ("medium literal 2", "napi_gro_receive", None, (), {}),
    ("medium literal 3", "cgroup_subsys_state", None, (), {}),
    ("hot literal", "EXPORT_SYMBOL_GPL", None, (), {}),
    ("hot literal 2", "kmalloc", None, (), {}),
    ("ultra-hot literal", "GFP_KERNEL", None, (), {}),
    ("phrase", "static int __init", None, (), {}),
    ("fixed string", "!= NULL", None, ("-F",), {"fixed_strings": True}),
    ("fixed string 2", "if (ret < 0)", None, ("-F",), {"fixed_strings": True}),
    ("escaped call", r"mutex_lock\(&", None, (), {}),
    ("regex classes", r"static\s+int\s+\w+_probe", "static[[:space:]]+int[[:space:]]+[[:alnum:]_]+_probe", (), {}),
    ("wrapped wildcard", ".*alloc_page.*", None, (), {}),
    ("folded", "copyright", None, ("-i",), {"case_mode": "insensitive"}),
    ("folded 2", "deadlock", None, ("-i",), {"case_mode": "insensitive"}),
    ("word", "kfree", None, ("-w",), {"word_regexp": True}),
    ("word 2", "pr_debug", None, ("-w",), {"word_regexp": True}),
    ("alternation", "TODO|FIXME", None, (), {}),
    ("factored alternation", "kzalloc|kcalloc", None, (), {}),
    ("group alternation", "devm_(kzalloc|kmalloc)", None, (), {}),
    ("anchored group", "^(EXPORT_SYMBOL|MODULE_LICENSE)", None, (), {}),
    ("anchored literal", "^#include <linux/module.h>", None, (), {}),
    ("small class", "ext[234]", None, (), {}),
    ("rescued class", "-O[0-3]", None, (), {}),
)


def mirror() -> OsPath:
    """Copy the linux tree's UTF-8 text files into the scratch mirror."""
    dest = WORKDIR / "mirror"
    marker = WORKDIR / "mirror.done"
    if marker.exists():
        return dest
    t0 = time.perf_counter()
    n = 0
    for src in LINUX.rglob("*"):
        if ".git" in src.parts or src.is_symlink() or not src.is_file():
            continue
        data = src.read_bytes()
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        out = dest / src.relative_to(LINUX)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        n += 1
    marker.write_text(str(n))
    print(f"mirror: {n} text files in {time.perf_counter() - t0:.0f}s", flush=True)
    return dest


async def build(mirror_root: OsPath) -> DatabaseStorage:
    """Write the mirror into sqlite and reindex once; reused across runs."""
    url = f"sqlite+aiosqlite:///{WORKDIR}/linux.sqlite"
    storage = DatabaseStorage(url=url)
    marker = WORKDIR / "build.done"
    if marker.exists():
        return storage
    t0 = time.perf_counter()
    batch: list[Entry] = []
    pending = 0
    written = 0

    async def flush() -> None:
        nonlocal batch, pending, written
        if batch:
            result = await storage.write(entries=batch, parents=True)
            assert result.success is True, result.errors
            written += len(batch)
            batch, pending = [], 0
            print(f"  write: {written} files", flush=True)

    for src in sorted(mirror_root.rglob("*")):
        if not src.is_file():
            continue
        content = src.read_text(encoding="utf-8")
        batch.append(Entry(path=Path("/" + str(src.relative_to(mirror_root))), content=content))
        pending += len(content)
        if len(batch) >= BATCH_ENTRIES or pending >= BATCH_BYTES:
            await flush()
    await flush()
    t1 = time.perf_counter()
    print(f"write: {written} files in {t1 - t0:.0f}s; reindexing...", flush=True)
    result = await storage.reindex()
    assert result.success is True, result.errors
    t2 = time.perf_counter()
    db_bytes = sum(f.stat().st_size for f in WORKDIR.glob("linux.sqlite*"))
    print(f"reindex: {t2 - t1:.0f}s; db {db_bytes / 1e9:.1f} GB", flush=True)
    marker.write_text(f"write={t1 - t0:.0f}s reindex={t2 - t1:.0f}s db={db_bytes}")
    return storage


def run_external(cmd: list[str], cwd: OsPath) -> tuple[float, int]:
    """One timed run; returns (seconds, matching-line count)."""
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, cwd=cwd, check=False)
    elapsed = time.perf_counter() - t0
    assert proc.returncode in (0, 1), (cmd, proc.returncode, proc.stderr[:500])
    count = proc.stdout.count(b"\n")
    return elapsed, count


async def run_vfs(storage: DatabaseStorage, pattern: str, kwargs: dict) -> tuple[float, int, bool]:
    t0 = time.perf_counter()
    result = await storage.grep(pattern=pattern, **kwargs)
    elapsed = time.perf_counter() - t0
    assert result.success is True, (pattern, result.errors)
    count = sum(len(o.matches or ()) for o in result.observations)
    truncated = any(e.severity is Severity.warning for e in result.errors)
    return elapsed, count, truncated


async def main() -> int:
    WORKDIR.mkdir(parents=True, exist_ok=True)
    for _label, pattern, _g, _flags, kwargs in QUERIES:
        plan = build_code_gram_query(pattern, fixed_strings=bool(kwargs.get("fixed_strings")))
        assert not plan.is_any(), f"not indexable, excluded by design: {pattern!r}"
    print(f"workdir {WORKDIR}; {len(QUERIES)} queries, all planner-indexable", flush=True)

    mirror_root = mirror()
    storage = await build(mirror_root)

    def fmt(ms: float | None) -> str:
        return f"{ms:>8.1f}ms" if ms is not None else "       - "

    rows = []
    for label, pattern, grep_pattern, flags, kwargs in QUERIES:
        vfs_ms = rg_ms = grep_ms = None
        vfs_count = rg_count = grep_count = None
        truncated = False
        if "vfs" in TOOLS:
            times = []
            for _ in range(RUNS):
                elapsed, vfs_count, was_truncated = await run_vfs(storage, pattern, kwargs)
                times.append(elapsed)
                truncated = truncated or was_truncated
            vfs_ms = statistics.median(times) * 1000
        if "rg" in TOOLS:
            rg_root = OsPath(os.environ["RG_ROOT"]) if "RG_ROOT" in os.environ else mirror_root
            rg_extra = ("--glob", "!.git") if rg_root != mirror_root else ()
            times = []
            for _ in range(RUNS):
                elapsed, rg_count = run_external(
                    [RG, "-uu", "--line-number", "--no-heading", *rg_extra, *flags, "-e", pattern, "."], rg_root
                )
                times.append(elapsed)
            rg_ms = statistics.median(times) * 1000
        if "grep" in TOOLS:
            times = []
            for _ in range(RUNS):
                elapsed, grep_count = run_external(
                    [GREP, "-rEn", *flags, "-e", grep_pattern or pattern, "."], mirror_root
                )
                times.append(elapsed)
            grep_ms = statistics.median(times) * 1000
        row = {
            "label": label,
            "pattern": pattern,
            "vfs_ms": vfs_ms,
            "rg_ms": rg_ms,
            "grep_ms": grep_ms,
            "vfs_count": vfs_count,
            "rg_count": rg_count,
            "grep_count": grep_count,
            "truncated": truncated,
        }
        rows.append(row)
        flag = " TRUNCATED" if truncated else ""
        parity = ""
        if vfs_count is not None and rg_count is not None and vfs_count != rg_count:
            parity = f"  PARITY vfs={vfs_count} rg={rg_count}"
        shown = vfs_count if vfs_count is not None else rg_count
        print(
            f"{label:<22} {pattern!r:<38} vfs {fmt(vfs_ms)}  "
            f"rg {fmt(rg_ms)}  grep {fmt(grep_ms)}  "
            f"rows {shown:>7}{flag}{parity}",
            flush=True,
        )

    (WORKDIR / "results.json").write_text(json.dumps(rows, indent=2))
    print(f"\nresults written to {WORKDIR / 'results.json'}", flush=True)
    await storage.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
