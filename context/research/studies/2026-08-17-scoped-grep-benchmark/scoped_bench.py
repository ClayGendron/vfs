"""Scoped grep benchmark: the usage-mined scope shapes vs rg's positional form.

The spec 104 §6 gate, extending the 25-row linux ladder
(``../2026-08-16-linux-grep-benchmark/benchmark.py`` — run it first;
this study reuses its ``WORKDIR`` store and mirror). Every row is one
of the scope shapes the usage-mining pass showed agents actually issue
— shallow directory scope (1–3 segments), bare extension (both the
``ext`` channel and the ``*.ext`` glob spelling), directory +
extension, exclusion, stem wildcard, basename literal, and the
scoped-wide recall stress — with rg compared in its **positional-path
form** (walk pruning enabled; the hardest fair comparison) and a
recall column: vfs matching-line counts must equal rg's, not merely
beat its wall time.

Run:  WORKDIR=/path/to/scratch uv run python \
      context/research/studies/2026-08-17-scoped-grep-benchmark/scoped_bench.py

Landed-run record (2026-08-17, the same linux corpus and machine as
the ladder study: 93,760 text files, sqlite file store rebuilt through
the spec 104 write path, M-series laptop, median of 3):

- Build, bounding §2's overhead in context: write 53 s (45 s
  pre-104 — segment maintenance ≈ 85 µs/file at ETL batch scale),
  reindex 196 s (191 s — the re-convergence collect pass ≈ 5 s, zero
  drift found), db 5.0 GB.
- The unscoped 25-row ladder re-ran with **zero regressions and
  identical match counts on every row**; saturated rows ran 11–19 %
  *faster* (the per-candidate ``Path`` construction and name-arm glob
  left the hot loop; gateless calls skip the Python gate entirely) —
  e.g. ``copyright -i`` 1,461 → 1,182 ms, ``EXPORT_SYMBOL_GPL``
  424 → 350 ms.
- The scoped rows (the landed run's table): **recall OK on every row**
  — vfs line counts equal rg's positional-path counts exactly, no
  truncation anywhere scoped. vfs beats rg positional outright on 6
  of 12 rows and stays within 2.3× on the rest:

  ====================================================== ======= ======= ======
  row (pattern @ scope)                                  vfs ms  rg ms   lines
  ====================================================== ======= ======= ======
  dir 1-seg:  EXPORT_SYMBOL_GPL @ drivers/**              303.7  1021.2  13,073
  dir 2-seg:  kzalloc @ drivers/net/**                    146.9   119.1   3,938
  dir 3-seg:  mutex_lock @ drivers/gpu/drm/**             215.4   144.1   2,506
  scoped-wide: copyright -i @ fs/ext4/**                   26.6    11.9      47
  rare @ dir: napi_gro_receive @ drivers/net/**            71.4   105.7     148
  ultra-hot @ dir: GFP_KERNEL @ mm/**                      15.9    15.0     372
  bare ext (channel): cgroup_subsys_state ext=h           112.7   744.9     129
  bare ext (glob):    cgroup_subsys_state @ *.h           119.5   721.8     129
  dir+ext:    spin_lock @ kernel/**/*.c                    28.3    18.5   1,260
  exclusion:  napi_gro_receive NOT drivers/**              13.5  1856.3      19
  stem:       probe @ spi-*.c                              40.9    98.7     601
  basename:   obj- @ Makefile                             169.3   151.3  19,210
  ====================================================== ======= ======= ======

- The recall-stress row: ``copyright -i`` under ``fs/ext4/**``
  answers in 27 ms with exact recall, where the unscoped spelling is
  the ladder's loudest row (1,182 ms, truncated at 40,926 matching
  files) — nomination starts from the scope's ~80 entries instead of
  the corpus's 58k, and the candidate budget now counts scoped
  candidates, so the truncation that silently cost recall before
  spec 104 cannot recur.
- The asymmetry rows show the two engines' complements: rg's walk
  pruning wins nothing on shapes that prune no walk — a bare
  extension (745 ms: the whole tree walked, filtered per file) and
  especially an exclusion (1,856 ms: everything outside ``drivers``
  walked) — while vfs's content index nominates the pattern's few
  candidates first and answers both from the same 13–120 ms shape.
  Shapes with no allow-list at all (bare ext, stem, basename — every
  arm unbounded) ride pure column pushdown and still hold exact
  recall; the stem row is the recorded degradation class (ADR 040:
  path trigrams are the costed escalation) and answers in 41 ms.
- **No budget re-derivation**: candidate cost stays fetch-dominated
  (~75 µs/candidate, the spec 103 sweep's basis), scoped rows
  under-fill ``CANDIDATE_BUDGET`` = 25,000 rather than saturate it,
  and the one row that saturates (unscoped ``copyright -i``) is bulk
  retrieval, not search. All budgets stand as derived.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path as OsPath

from vfs.models.code_grams import build_code_gram_query
from vfs.results import Severity
from vfs.storage.backends.database import DatabaseStorage

WORKDIR = OsPath(os.environ.get("WORKDIR", ""))
RUNS = int(os.environ.get("RUNS", "3"))
RG = "rg"

# (label, vfs pattern, vfs kwargs, rg args appended to the shared flags).
# rg runs -uu from the mirror root: positional paths prune the walk, -g
# globs filter it — the field's own scoped forms, never a post-filter.
QUERIES: tuple[tuple[str, str, dict, list[str]], ...] = (
    (
        "dir 1-seg: EXPORT_SYMBOL_GPL @ drivers/**",
        "EXPORT_SYMBOL_GPL",
        {"globs": ("drivers/**",)},
        ["-e", "EXPORT_SYMBOL_GPL", "drivers"],
    ),
    ("dir 2-seg: kzalloc @ drivers/net/**", "kzalloc", {"globs": ("drivers/net/**",)}, ["-e", "kzalloc", "drivers/net"]),
    (
        "dir 3-seg: mutex_lock @ drivers/gpu/drm/**",
        "mutex_lock",
        {"globs": ("drivers/gpu/drm/**",)},
        ["-e", "mutex_lock", "drivers/gpu/drm"],
    ),
    (
        "scoped-wide: copyright -i @ fs/ext4/**",
        "copyright",
        {"globs": ("fs/ext4/**",), "case_mode": "insensitive"},
        ["-i", "-e", "copyright", "fs/ext4"],
    ),
    (
        "rare @ dir: napi_gro_receive @ drivers/net/**",
        "napi_gro_receive",
        {"globs": ("drivers/net/**",)},
        ["-e", "napi_gro_receive", "drivers/net"],
    ),
    ("ultra-hot @ dir: GFP_KERNEL @ mm/**", "GFP_KERNEL", {"globs": ("mm/**",)}, ["-e", "GFP_KERNEL", "mm"]),
    (
        "bare ext (channel): cgroup_subsys_state ext=h",
        "cgroup_subsys_state",
        {"ext": ("h",)},
        ["-g", "*.h", "-e", "cgroup_subsys_state"],
    ),
    (
        "bare ext (glob): cgroup_subsys_state @ *.h",
        "cgroup_subsys_state",
        {"globs": ("*.h",)},
        ["-g", "*.h", "-e", "cgroup_subsys_state"],
    ),
    (
        "dir+ext: spin_lock @ kernel/**/*.c",
        "spin_lock",
        {"globs": ("kernel/**/*.c",)},
        ["-g", "*.c", "-e", "spin_lock", "kernel"],
    ),
    (
        "exclusion: napi_gro_receive NOT drivers/**",
        "napi_gro_receive",
        {"globs_not": ("drivers/**",)},
        ["-g", "!drivers/**", "-e", "napi_gro_receive"],
    ),
    ("stem: probe @ spi-*.c", "probe", {"globs": ("spi-*.c",)}, ["-g", "spi-*.c", "-e", "probe"]),
    ("basename: obj- @ Makefile", "obj-", {"globs": ("Makefile",)}, ["-g", "Makefile", "-e", "obj-"]),
)


def run_rg(mirror: OsPath, args: list[str]) -> tuple[float, int]:
    """Median wall ms and matching-line count for one rg invocation."""
    times: list[float] = []
    count = 0
    for _ in range(RUNS):
        t0 = time.perf_counter()
        proc = subprocess.run(
            [RG, "-uu", "--line-number", "--no-heading", *args], capture_output=True, cwd=mirror, check=False
        )
        times.append((time.perf_counter() - t0) * 1000)
        assert proc.returncode in (0, 1), (args, proc.stderr[:500])
        count = proc.stdout.count(b"\n")
    return statistics.median(times), count


async def run_vfs(storage: DatabaseStorage, pattern: str, kwargs: dict) -> tuple[float, int, bool]:
    """Median wall ms, matching-line count, and truncation flag for one grep."""
    times: list[float] = []
    result = None
    for _ in range(RUNS):
        t0 = time.perf_counter()
        result = await storage.grep(pattern=pattern, **kwargs)
        times.append((time.perf_counter() - t0) * 1000)
    assert result is not None and result.success is True, (pattern, result and result.errors)
    count = sum(len(o.matches or ()) for o in result.observations)
    truncated = any(e.severity is Severity.warning for e in result.errors)
    return statistics.median(times), count, truncated


async def main() -> int:
    if not WORKDIR.is_dir() or not (WORKDIR / "build.done").exists():
        print("WORKDIR must hold the ladder study's built store — run benchmark.py first", file=sys.stderr)
        return 2
    mirror = WORKDIR / "mirror"
    for _label, pattern, _kwargs, _rg in QUERIES:
        assert not build_code_gram_query(pattern).is_any(), f"pattern {pattern!r} does not plan indexable"
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{WORKDIR}/linux.sqlite")
    rows: list[dict[str, object]] = []
    print(f"{'row':48s} {'vfs ms':>8s} {'rg ms':>8s} {'lines':>7s}  recall")
    for label, pattern, kwargs, rg_args in QUERIES:
        vfs_ms, vfs_count, truncated = await run_vfs(storage, pattern, kwargs)
        rg_ms, rg_count = run_rg(mirror, rg_args)
        verdict = "TRUNC" if truncated else ("OK" if vfs_count == rg_count else f"MISMATCH rg={rg_count}")
        print(f"{label:48s} {vfs_ms:8.1f} {rg_ms:8.1f} {vfs_count:7d}  {verdict}", flush=True)
        rows.append(
            {
                "label": label,
                "pattern": pattern,
                "vfs_ms": vfs_ms,
                "rg_ms": rg_ms,
                "vfs_count": vfs_count,
                "rg_count": rg_count,
                "truncated": truncated,
            }
        )
    await storage.close()
    out = WORKDIR / "scoped_results.json"
    out.write_text(json.dumps(rows, indent=2))
    print(f"\nresults written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
